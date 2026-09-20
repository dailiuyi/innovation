"""PR review lifecycle. Use one Windows account throughout; never operates daily Demo."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from check_java import test_counts

from review_runtime import Runtime, account_smoke, request

ROOT = Path(__file__).resolve().parents[1]
REMOTE = 'https://github.com/dailiuyi/innovation.git'


def run(args, cwd=ROOT, env=None):
    return subprocess.check_output([str(a) for a in args], cwd=cwd, env=env,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace').strip()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def operation_lock(home):
    marker = home / 'operation.lock'
    with marker.open('x') as file:
        file.write(str(os.getpid()))
    try:
        yield
    finally:
        marker.unlink(missing_ok=True)


def remote_head(pr):
    result = run(['git', 'ls-remote', REMOTE, f'refs/pull/{pr}/head'])
    if not result:
        raise RuntimeError('PR head not found')
    return result.split()[0]


def directory(pr, sha):
    if pr < 1 or len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('Positive PR number and full lowercase commit SHA required')
    return ROOT / '.local/reviews' / f'pr-{pr}' / sha


def clean(source, sha):
    if run(['git', 'rev-parse', 'HEAD'], source) != sha:
        raise RuntimeError('Review checkout HEAD mismatch')
    if run(['git', 'status', '--porcelain', '--untracked-files=normal'], source):
        raise RuntimeError('Review source changed; prepare a clean snapshot, never overwrite changes')


def environment():
    env = dict(os.environ)
    java = next((ROOT / '.local/java21').glob('jdk*/bin/java.exe'), None)
    if java:
        env['JAVA_HOME'] = str(java.parent.parent)
        env['PATH'] = str(java.parent) + os.pathsep + env.get('PATH', '')
    env['PYTHONPATH'] = str(ROOT / '.local/python') + os.pathsep + env.get('PYTHONPATH', '')
    return env


def prepare(pr):
    sha = remote_head(pr)
    home = directory(pr, sha)
    source = home / 'source'
    if not source.exists():
        source.mkdir(parents=True)
        run(['git', 'init', '-q'], source)
        run(['git', 'remote', 'add', 'origin', REMOTE], source)
        run(['git', 'fetch', '--depth=1', 'origin', f'refs/pull/{pr}/head'], source)
        if run(['git', 'rev-parse', 'FETCH_HEAD'], source) != sha:
            raise RuntimeError('PR changed while fetching; run prepare again')
        run(['git', 'checkout', '--detach', sha], source)
    clean(source, sha)
    # Task-local node_modules; never mutate another checkout's install.
    result = {'pr': pr, 'sha': sha, 'source': str(source), 'state': 'prepared'}
    write(home / 'snapshot.json', result)
    return result


def execute(command, source, home, name, env, timeout=600):
    print('RUN ' + name, flush=True)
    with (home / (name + '.log')).open('wb') as log:
        process = subprocess.Popen([str(x) for x in command], cwd=source, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            else:
                process.kill()
            process.wait()
            raise RuntimeError(name + ' interrupted/timed out; inspect log, do not blindly repeat')
    if code:
        raise RuntimeError(name + ' failed; inspect ' + str(home / (name + '.log')))


def check(pr, sha, suite, online=False):
    home = directory(pr, sha)
    source = home / 'source'
    if (home / 'serving.lock').exists():
        raise RuntimeError('Stop the managed preview before rebuilding its source/artifacts')
    clean(source, sha)
    evidence = home / ('check-' + uuid.uuid4().hex[:12])
    evidence.mkdir()
    report = {'pr': pr, 'sha': sha, 'suite': suite, 'status': 'running',
              'startedAt': datetime.now(timezone.utc).isoformat(), 'checks': [], 'evidence': str(evidence)}
    # Invalidate old success as soon as a new run starts.
    write(home / 'checks.json', report)
    env = environment()
    try:
        if suite == 'accounts':
            execute(['mvn.cmd', '-f', source / 'backend/pom.xml',
                     '-Dmaven.repo.local=' + str(ROOT / '.local/m2'), *([] if online else ['-o']),
                     'clean', 'package', '-B', '-ntp'],
                    source, evidence, 'backend-package', env)
            results = list((source / 'backend').glob('*/target/surefire-reports/TEST-*.xml'))
            counts = test_counts(results)
            report['javaTests'] = counts['tests']
            report['javaCounts'] = counts
            if not counts['tests'] or any(counts[k] for k in ('failures', 'errors', 'skipped')):
                raise RuntimeError('Java tests missing, failing or skipped; inspect Surefire results')
            jar = source / 'backend/ruoyi-admin/target/ruoyi-admin.jar'
            # Requirement-specific HTTP path runs before generic repository checks.
            with Runtime(source, ROOT, evidence / 'accounts', jar, password='Ab1!xy') as runtime:
                report['checks'] = account_smoke(runtime)
                report['postgresVersion'] = runtime.pg_version
            report.update(jar=str(jar), jarSha256=sha256(jar))
        else:
            npm = 'npm.cmd' if os.name == 'nt' else 'npm'
            execute([npm, '--prefix', 'frontend', 'ci', '--prefer-offline', '--no-audit', '--no-fund',
                     '--cache', ROOT / '.local/npm-cache'], source, evidence, 'npm-ci', env)
            execute([sys.executable, source / 'scripts/harness.py', 'check', '--profile', 'frontend'],
                    source, evidence, 'frontend', env)
        execute([sys.executable, source / 'scripts/harness.py', 'doctor', '--profile', 'quick'],
                source, evidence, 'doctor', env)
        execute([sys.executable, source / 'scripts/harness.py', 'check', '--profile', 'quick'],
                source, evidence, 'quick', env)
        clean(source, sha)
        report.update(status='passed', sourceUnchanged=True)
    except Exception as error:
        report.update(status='failed', reason=str(error))
        raise
    finally:
        report['finishedAt'] = datetime.now(timezone.utc).isoformat()
        write(evidence / 'report.json', report)
        write(home / ('checks-' + suite + '.json'), report)
        write(home / 'checks.json', report)
    return report


def serve(pr, sha, reviewed_sha):
    home = directory(pr, sha)
    source = home / 'source'
    clean(source, sha)
    if reviewed_sha != sha or remote_head(pr) != sha:
        raise RuntimeError('Independent review and current PR head must match this snapshot')
    report = read(home / 'checks-accounts.json')
    if report.get('status') != 'passed' or report.get('sha') != sha or not report.get('sourceUnchanged'):
        raise RuntimeError('Passing current-source accounts HTTP evidence required')
    frontend = read(home / 'checks-frontend.json')
    if frontend.get('status') != 'passed' or frontend.get('sha') != sha or not frontend.get('sourceUnchanged'):
        raise RuntimeError('Passing current-source frontend evidence required')
    jar = Path(report['jar'])
    if sha256(jar) != report['jarSha256']:
        raise RuntimeError('Tested backend artifact changed')
    marker = home / 'serving.lock'
    # Atomic lock; do not silently reuse stale sessions or replace a live preview.
    with marker.open('x') as file:
        file.write(str(os.getpid()))
    state_path = home / 'instance.json'
    stop_file = home / 'stop.request'
    stop_file.unlink(missing_ok=True)
    state = {'sha': sha, 'pr': pr, 'status': 'starting', 'reviewedSha': reviewed_sha}
    write(state_path, state)
    try:
        npm = 'npm.cmd' if os.name == 'nt' else 'npm'
        execute([npm, '--prefix', 'frontend', 'ci', '--prefer-offline', '--no-audit', '--no-fund',
                 '--cache', ROOT / '.local/npm-cache'], source, home, 'preview-npm', environment())
        clean(source, sha)
        with Runtime(source, ROOT, home / ('preview-' + uuid.uuid4().hex[:12]), jar) as runtime:
            runtime.frontend()
            status, login = request(runtime.web, '/dev-api/login', 'POST',
                                    {'username': 'bootstrap', 'password': runtime.password})
            if status != 200 or login.get('code') != 200 or not login.get('token'):
                raise RuntimeError('Preview proxy login failed')
            credentials = runtime.directory / 'credentials.json'
            write(credentials, {'username': 'bootstrap', 'password': runtime.password})
            state.update(status='ready', url=runtime.web, credentialsFile=str(credentials),
                         runtime=str(runtime.directory), pid=os.getpid())
            write(state_path, state)
            print(json.dumps(state, ensure_ascii=False), flush=True)
            print('Keep this foreground process alive. Stop via review.py stop --pr/--sha.', flush=True)
            while not stop_file.exists():
                if any(p.poll() is not None for p in runtime.processes):
                    raise RuntimeError('Preview process exited')
                time.sleep(1)
    except Exception as error:
        state.update(status='failed', reason=str(error))
        raise
    finally:
        if state['status'] != 'failed':
            state['status'] = 'stopped'
        write(state_path, state)
        marker.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check', 'serve', 'status', 'stop'))
    parser.add_argument('--pr', type=int, required=True)
    parser.add_argument('--sha')
    parser.add_argument('--suite', choices=('accounts', 'frontend'), default='accounts')
    parser.add_argument('--reviewed-sha', help='Explicit attestation by the independent reviewer, not an auto-approval')
    parser.add_argument('--online', action='store_true', help='Explicitly permit missing Maven dependency downloads')
    args = parser.parse_args()
    if args.action == 'prepare':
        result = prepare(args.pr)
    else:
        if not args.sha:
            parser.error('--sha required; use the commit returned by prepare')
        home = directory(args.pr, args.sha)
        if args.action == 'check':
            with operation_lock(home):
                result = check(args.pr, args.sha, args.suite, args.online)
        elif args.action == 'serve':
            with operation_lock(home):
                serve(args.pr, args.sha, args.reviewed_sha)
            return
        elif args.action == 'stop':
            if not (home / 'serving.lock').exists():
                raise RuntimeError('No managed preview to stop')
            (home / 'stop.request').touch()
            result = {'status': 'stop-requested', 'retained': 'All evidence and isolated data'}
        else:
            result = read(home / 'instance.json')
            if result.get('status') == 'ready':
                try:
                    result['healthy'] = request(result['url'], '/dev-api/captchaImage')[0] == 200
                except (OSError, ValueError):
                    result['healthy'] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
