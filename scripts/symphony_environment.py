"""Explicit environment baselines and bounded, task-specific probes; never install packages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'deploy/symphony-environment.lock.json'
IMAGE = 'innovation-symphony:0.0.3-java-v2'
EXECUTION_FILES = (
    'agent_check.py', 'frontend_control.py', 'harness.py', 'check_java.py',
    'test_frontend_control.py', 'test_symphony_task.py', 'test_symphony_publish.py',
    'symphony_task.py', 'symphony_publish.py', 'symphony_entrypoint.py',
    'migrate_symphony_workspaces.py', 'test_migrate_symphony_workspaces.py',
    'symphony_environment.py', 'test_symphony_environment_lock.py', 'verify_symphony_concurrency.py',
)
TOOLS = {'python': ['python3', '--version'], 'git': ['git', '--version'],
         'node': ['node', '--version'], 'npm': ['npm', '--version'],
         'java': ['java', '-version'], 'maven': ['mvn', '--version'],
         'codex': ['codex', '--version']}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    data = Path(path).read_bytes()
    # Text fingerprints survive Git's Windows/Linux checkout line endings.
    if Path(path).suffix not in ('.beam', '.tar'):
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def command(args):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=20)
    if result.returncode:
        # Never echo command output: future probes may involve private configuration.
        raise RuntimeError('Command failed: ' + str(args[0]))
    return (result.stdout + result.stderr).strip()


def file_specs(root):
    pairs = [('WORKFLOW.md', '/config/WORKFLOW.md')]
    pairs += [('scripts/' + n, '/opt/symphony-execution/' + n) for n in EXECUTION_FILES]
    pairs += [('scripts/' + n, '/opt/symphony-routing/' + n) for n in (
        'symphony_codex_adapter.py', 'symphony_model_probe.py', 'symphony_publish.py', 'symphony_task.py', 'symphony_environment.py')]
    pairs += [('scripts/symphony_entrypoint.py', '/opt/symphony-entrypoint.py')]
    patch_root = '.local/symphony/data/blocking-fix/'
    manifest = read(root / patch_root / 'manifest.json')
    pairs += [(patch_root + 'manifest.json', '/opt/symphony-patches/manifest.json')]
    for name in sorted({**manifest['verifiedModules'], **manifest.get('preservedModules', {})}):
        pairs.append((patch_root + 'ebin/' + name, '/opt/symphony-patches/' + name))
    pairs += [(name, None) for name in (
        'scripts/symphony.ps1', 'scripts/prepare_symphony_workspace.py',
        'scripts/prepare_symphony_blocking_fix.py', 'scripts/verify_symphony_blocking.exs',
        'scripts/test_symphony_environment.py',
        'deploy/symphony.Dockerfile', 'deploy/symphony-base.Dockerfile',
        'deploy/symphony-seccomp.json', 'scripts/requirements-review.txt')]
    return [{'source': name, 'runtime': target, 'sha256': sha(root / name)} for name, target in pairs]


def freeze(root, output):
    # Explicit operator command only. Ordinary verify/doctor never refresh a baseline.
    image_id = command(['docker', 'image', 'inspect', '--format', '{{.Id}}', IMAGE])
    probe = """import hashlib,json,subprocess
commands=COMMANDS
versions={k:(lambda r:(r.stdout+r.stderr).strip().splitlines()[0])(subprocess.run(v,check=True,capture_output=True,text=True)) for k,v in commands.items()}
paths=['/opt/symphony-validation/installed.txt','/opt/symphony-tools/prepare_workspace.py']
print(json.dumps({'tools':versions,'imageFiles':{p:hashlib.sha256(open(p,'rb').read().replace(bytes([13,10]),bytes([10]))).hexdigest() for p in paths}}))
""".replace('COMMANDS', repr(TOOLS))
    runtime = json.loads(command(['docker', 'run', '--rm', '--network', 'none', '--user', '1000:1000',
                                  '--entrypoint', 'python3', image_id, '-c', probe]))
    value = {'schemaVersion': 1, 'image': IMAGE, 'imageId': image_id,
             'symphonyVersion': '0.0.3', 'codexVersion': '0.154.0',
             'releaseSha256': 'ea35a04a54a6d37c0cafe3f195da871e47614a8c05765b90dbb4cac32e1435ee',
             'files': file_specs(root), **runtime}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return {'status': 'passed', 'lock': str(output), 'imageId': image_id,
            'note': 'Baseline recorded; run tests and doctor before accepting it.'}


def verify_files(baseline, root=None):
    failures = []
    if baseline.get('schemaVersion') != 1:
        raise ValueError('Unsupported environment lock schema')
    for item in baseline['files']:
        path = root / item['source'] if root else (Path(item['runtime']) if item['runtime'] else None)
        if path is None:
            continue
        if not path.is_file() or sha(path) != item['sha256']:
            failures.append('Version mismatch: ' + str(path))
    if root is None:
        for path, expected in baseline['imageFiles'].items():
            if not Path(path).is_file() or sha(path) != expected:
                failures.append('Image content mismatch: ' + path)
    return failures


def verify_host(root, lock):
    baseline = read(lock)
    failures = verify_files(baseline, root)
    image_id = command(['docker', 'image', 'inspect', '--format', '{{.Id}}', baseline['image']])
    if image_id != baseline['imageId']:
        failures.append('Image tag no longer identifies the accepted image')
    return {'status': 'blocked' if failures else 'passed', 'failures': failures,
            'imageId': image_id, 'lockSha256': sha(lock)}


def native_workspace(path):
    # Choose the most specific mount, including nested /data/workspaces.
    matches = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split()
        mount = Path(fields[4].replace('\\040', ' '))
        if path == mount or mount in path.parents:
            matches.append((len(mount.parts), fields[fields.index('-') + 1]))
    return bool(matches) and max(matches)[1] in {'ext4', 'ext3', 'ext2', 'xfs', 'btrfs'}


def task_preflight(workspace, profile, java_modules, lock):
    started = time.monotonic()
    checks = []
    def check(name, fn):
        try:
            value = fn()
            if value is False:
                raise ValueError('Condition not met')
            checks.append({'name': name, 'status': 'passed'})
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
            checks.append({'name': name, 'status': 'blocked', 'reason': str(exc)})
    try:
        baseline = read(lock)
        mismatches = verify_files(baseline)
        if mismatches:
            raise ValueError('; '.join(mismatches))
    except (OSError, ValueError, KeyError) as exc:
        return {'status': 'blocked', 'seconds': round(time.monotonic()-started, 3),
                'checks': [{'name': 'environment version', 'status': 'blocked', 'reason': str(exc)}]}
    checks.append({'name': 'environment version', 'status': 'passed'})
    check('build concurrency configuration', lambda: 1 <= int(os.environ.get('SYMPHONY_BUILD_CONCURRENCY', '1')) <= 4)
    selected = ['python', 'git', 'codex']
    if profile == 'frontend':
        selected += ['node', 'npm']
    if java_modules:
        selected += ['java', 'maven']
    for name in selected:
        def version(name=name):
            return command(TOOLS[name]).splitlines()[0] == baseline['tools'][name]
        check(name + ' version/PATH', version)
    python = Path('/opt/symphony-validation/venv/bin/python')
    if workspace is not None:
        workspace = Path(workspace).resolve(strict=True)
        python = workspace / '.local/venv/bin/python'
        check('Linux native workspace', lambda: native_workspace(workspace))
        def writable():
            with tempfile.TemporaryFile(dir=workspace / '.local') as stream:
                stream.write(b'preflight')
            return True
        check('task-local write', writable)
        for module in java_modules:
            check('Java module ' + module, lambda module=module: (workspace / 'backend' / module / 'pom.xml').is_file())
    check('Python validators', lambda: command([python, '-c', 'import yaml,jsonschema,openapi_spec_validator']) == '')
    return {'status': 'passed' if all(c['status'] == 'passed' for c in checks) else 'blocked',
            'seconds': round(time.monotonic()-started, 3), 'lockSha256': sha(lock), 'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'verify', 'probe'))
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--lock', type=Path, default=LOCK)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--profile', choices=('quick', 'frontend'), default='quick')
    parser.add_argument('--java', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'freeze':
            result = freeze(args.root, args.lock)
        elif args.action == 'verify':
            result = verify_host(args.root, args.lock)
        else:
            profile, modules = args.profile, ['ruoyi-ar'] if args.java else []
            if args.plan:
                from symphony_task import validate_plan
                plan = validate_plan(read(args.plan))
                profile, modules = plan['profile'], plan['javaModules']
            result = task_preflight(args.workspace, profile, modules, args.lock)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        result = {'status': 'blocked', 'reason': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0 if result['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
