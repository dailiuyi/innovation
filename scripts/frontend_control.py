"""Task-local dependency/build reuse with explicit evidence and bounded retries."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
INSTALL_ARGS = ['ci', '--prefer-offline', '--no-audit', '--no-fund', '--include=dev']
BUILD_TIMEOUT = 900


class Blocked(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def has_evidence(state, base):
    value = state.get('log')
    if not isinstance(value, str):
        return False
    path = Path(value)
    return path.resolve().is_relative_to(base.resolve()) and path.is_file()


def hash_files(base, excluded=()):
    """Content hashes include ignored/untracked input, env files, additions and deletions."""
    result = hashlib.sha256()
    count = 0
    if not base.is_dir():
        return None
    resolved_base = base.resolve()
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in excluded)
        for name in sorted(files):
            path = Path(folder) / name
            # npm binary symlinks are allowed only inside this tree.
            if path.is_symlink() and not path.resolve().is_relative_to(resolved_base):
                raise Blocked('File escapes task tree: ' + str(path))
            result.update(path.relative_to(base).as_posix().encode() + b'\0')
            with path.open('rb') as stream:
                result.update(hashlib.file_digest(stream, 'sha256').digest())
            count += 1
        for name in dirs:
            if (Path(folder) / name).is_symlink():
                raise Blocked('Directory symlinks are not supported in cached inputs')
    return {'sha256': result.hexdigest(), 'files': count}


def safe_paths(root):
    root = root.resolve()
    for relative in ('.local/frontend-control', 'frontend/node_modules', 'frontend/dist'):
        if not (root / relative).resolve().is_relative_to(root):
            raise Blocked('Cache/install/output must stay inside this checkout')
    base = root / '.local/frontend-control'
    base.mkdir(parents=True, exist_ok=True)
    return base


@contextmanager
def locked(base):
    with (base / 'operation.lock').open('a+b') as stream:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise Blocked('Another dependency/build operation is running; do not start a duplicate') from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise Blocked('Another dependency/build operation is running; do not start a duplicate') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def runtime(root, env):
    npm = 'npm.cmd' if os.name == 'nt' else 'npm'
    def output(command):
        return subprocess.check_output(command, cwd=root / 'frontend', env=env,
                                       stderr=subprocess.PIPE, timeout=30).decode().strip()
    # Hash, never print npm config or environment values (they may contain secrets).
    return {'node': output(['node', '--version']), 'npm': output([npm, '--version']),
            'platform': platform.platform(), 'machine': platform.machine(),
            'npmConfig': digest(output([npm, 'config', 'list', '--json'])),
            'environment': digest({k: v for k, v in env.items() if k.upper().startswith(
                ('VITE_', 'NODE_', 'NPM_CONFIG_', 'AR_', 'SASS_')) or k.upper() in (
                    'CI', 'PATH', 'LANG', 'LC_ALL', 'TZ', 'SOURCE_DATE_EPOCH')})}


def install_key(root, context):
    files = {}
    for relative in ('frontend/package.json', 'frontend/package-lock.json', 'frontend/.npmrc', '.npmrc'):
        path = root / relative
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    if not files['frontend/package-lock.json']:
        raise Blocked('package-lock.json is required; lockfiles are never regenerated')
    return digest({'files': files, 'runtime': context, 'args': INSTALL_ARGS, 'version': 1})


def package_tree(root):
    # Correctness first: verify installed contents, not just a marker or directory.
    # Vite's disposable development caches are not installed package inputs.
    return hash_files(root / 'frontend/node_modules', ('.vite', '.vite-temp', '.cache'))


def command_runner(command, root, directory, env, timeout, name):
    from harness import Step, run_step
    return run_step(Step(name, command, root, timeout), directory, env)


def ensure_dependencies(root, base, context, env, run=command_runner, retry_reason=None):
    key = install_key(root, context)
    state = read_json(base / 'install.json')
    tree = package_tree(root)
    if (state.get('key') == key and state.get('status') == 'passed'
            and tree and tree == state.get('tree') and has_evidence(state, base)):
        return {'status': 'passed', 'mode': 'reused', 'key': key, 'tree': tree,
                'evidence': state['log']}
    if state.get('key') == key and state.get('status') != 'passed' and not retry_reason:
        raise Blocked('Previous install failed/interrupted; inspect install.json and use --retry-reason after repair')
    attempt = base / ('install-' + uuid.uuid4().hex)
    attempt.mkdir()
    save_json(base / 'install.json', {'key': key, 'status': 'running', 'log': str(attempt / 'install.log')})
    print('RUN dependency install (missing, changed or unverified installation)', flush=True)
    result = run(['npm.cmd' if os.name == 'nt' else 'npm', '--prefix', str(root / 'frontend'),
                  *INSTALL_ARGS], root, attempt, env, 900, 'install')
    tree = package_tree(root) if result['status'] == 'passed' else None
    if result['status'] == 'passed' and (not tree or not (root / 'frontend/node_modules/vite/bin/vite.js').is_file()
                                      or key != install_key(root, context)):
        result.update(status='blocked', reason='Install inputs changed or required packages are missing')
    save_json(base / 'install.json', {**result, 'key': key, 'tree': tree, 'retryReason': retry_reason})
    return {**result, 'mode': 'executed', 'key': key, 'tree': tree}


def build_key(root, context, deps):
    return digest({'source': hash_files(root / 'frontend', ('node_modules', 'dist', '.git')),
                   'runtime': context, 'dependencies': deps['tree'], 'command': 'build:prod',
                   'controller': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


def operate(root, action='build', env=None, retry_reason=None, run=command_runner,
            context=None, timeout=BUILD_TIMEOUT):
    root = root.resolve()
    env = dict(os.environ if env is None else env)
    base = safe_paths(root)
    with locked(base):
        context = runtime(root, env) if context is None else context
        deps = ensure_dependencies(root, base, context, env, run, retry_reason)
        if deps['status'] != 'passed' or action == 'deps':
            return deps
        key = build_key(root, context, deps)
        previous = read_json(base / 'build.json')
        if previous.get('key') == key and previous.get('status') == 'passed' and has_evidence(previous, base):
            output = hash_files(root / 'frontend/dist')
            if output and output == previous.get('output') and (root / 'frontend/dist/index.html').is_file():
                print('REUSE frontend build; verified inputs and dist; evidence=' + previous['log'], flush=True)
                return {**previous, 'mode': 'reused', 'dependencies': deps['mode']}
        if previous.get('key') == key and previous.get('status') != 'passed' and not retry_reason:
            return {**previous, 'status': 'failed' if previous.get('status') == 'failed' else 'blocked', 'mode': 'held',
                    'reason': 'Same build inputs previously failed/timed out/interrupted. Inspect evidence; do not repeat unchanged build.',
                    'nextAction': 'Fix inputs or use --retry-reason describing the changed condition',
                    'dependencies': deps['mode']}
        attempt = base / ('build-' + uuid.uuid4().hex)
        attempt.mkdir()
        save_json(base / 'build.json', {'key': key, 'status': 'running', 'log': str(attempt / 'build.log')})
        result = run(['npm.cmd' if os.name == 'nt' else 'npm', '--prefix', str(root / 'frontend'),
                      'run', 'build:prod'], root, attempt, env, timeout, 'build')
        if result['status'] == 'passed':
            current_deps = {**deps, 'tree': package_tree(root)}
            if key != build_key(root, context, current_deps) or install_key(root, context) != deps['key']:
                result.update(status='blocked', reason='Inputs changed during build; output cannot be reused')
            elif not (root / 'frontend/dist/index.html').is_file():
                result.update(status='failed', reason='Build produced no dist/index.html')
        result.update(key=key, mode='executed', dependencies=deps['mode'], retryReason=retry_reason,
                      output=hash_files(root / 'frontend/dist') if result['status'] == 'passed' else None)
        save_json(base / 'build.json', result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('deps', 'build'))
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--retry-reason', help='Explicit reason after inspecting and repairing a prior failure')
    args = parser.parse_args()
    if args.retry_reason is not None and not args.retry_reason.strip():
        parser.error('--retry-reason must describe a repaired condition')
    try:
        result = operate(args.root, args.action, retry_reason=args.retry_reason)
    except (Blocked, OSError, subprocess.SubprocessError) as exc:
        result = {'status': 'blocked', 'reason': type(exc).__name__ + ': ' + str(exc)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return {'passed': 0, 'failed': 1, 'blocked': 2}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
