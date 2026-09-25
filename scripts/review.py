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

from review_runtime import Runtime, account_smoke, request, seed_preview, browser_smoke
import frontend_control

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT
REMOTE = 'https://github.com/dailiuyi/innovation-ar-resource-platform.git'


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
    java = next((RESOURCES / '.local/java21').glob('jdk*/bin/java.exe'), None)
    if java:
        env['JAVA_HOME'] = str(java.parent.parent)
        env['PATH'] = str(java.parent) + os.pathsep + env.get('PATH', '')
    env['PYTHONPATH'] = str(RESOURCES / '.local/python') + os.pathsep + env.get('PYTHONPATH', '')
    return env


def prepare(pr, extra_suites=()):
    sha = remote_head(pr)
    metadata = json.loads(run(['gh', 'pr', 'view', str(pr), '--repo', 'dailiuyi/innovation-ar-resource-platform',
                              '--json', 'headRefOid,files']))
    if metadata['headRefOid'] != sha:
        raise RuntimeError('PR changed while preparing')
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
    suites = set(select_suites([item['path'] for item in metadata['files']])) | set(extra_suites)
    if (home / 'snapshot.json').exists():
        suites.update(read(home / 'snapshot.json').get('requiredSuites', []))
    suites = sorted(suites)
    result = {'pr': pr, 'sha': sha, 'source': str(source), 'state': 'prepared', 'requiredSuites': suites}
    write(home / 'snapshot.json', result)
    return result


def select_suites(paths):
    suites = {'smoke', 'frontend'}
    for path in paths:
        if path.startswith('frontend/'):
            suites.add('scene-ui')
        if path.startswith('backend/'):
            if any(part in path.lower() for part in ('user', 'password', 'login', 'security', 'token', 'auth')):
                suites.add('accounts')
            # Business storage and migrations require their real isolated HTTP/database flow.
            if '/ruoyi-ar/' in path or '/db/' in path:
                suites.add('ingestion')
    return sorted(suites)


def passing(home, suite, sha):
    try:
        report = read(home / ('checks-' + suite + '.json'))
    except (OSError, ValueError):
        raise RuntimeError(suite + ' current-source evidence required') from None
    if report.get('status') != 'passed' or report.get('sha') != sha or report.get('sourceUnchanged') is not True:
        raise RuntimeError(suite + ' current-source evidence required')
    return report


def backend_artifact(source, home, sha, evidence, env, online):
    record = home / 'backend.json'
    if record.exists():
        old = read(record)
        jar = Path(old.get('jar', 'missing'))
        if (old.get('status') == 'passed' and old.get('sha') == sha and jar.is_file()
                and old.get('jarSha256') == sha256(jar)):
            return {**old, 'mode': 'reused'}
    write(record, {'status': 'running', 'sha': sha})
    execute(['mvn.cmd', '-f', source / 'backend/pom.xml',
             '-Dmaven.repo.local=' + str(RESOURCES / '.local/m2'), *([] if online else ['-o']),
             'clean', 'package', '-B', '-ntp'], source, evidence, 'backend-package', env)
    counts = test_counts(list((source / 'backend').glob('*/target/surefire-reports/TEST-*.xml')))
    if not counts['tests'] or any(counts[k] for k in ('failures', 'errors', 'skipped')):
        raise RuntimeError('Java tests missing, failing or skipped')
    jar = source / 'backend/ruoyi-admin/target/ruoyi-admin.jar'
    result = {'status': 'passed', 'sha': sha, 'jar': str(jar), 'jarSha256': sha256(jar),
              'javaCounts': counts, 'mode': 'executed'}
    write(record, result)
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
    if suite == 'auto':
        suites = read(home / 'snapshot.json')['requiredSuites']
        # Frontend prepares dependencies once for browser and runtime suites.
        return [check(pr, sha, item, online) for item in ['frontend', *[s for s in suites if s != 'frontend']]]
    evidence = home / ('check-' + uuid.uuid4().hex[:12])
    evidence.mkdir()
    report = {'pr': pr, 'sha': sha, 'suite': suite, 'status': 'running',
              'startedAt': datetime.now(timezone.utc).isoformat(), 'checks': [], 'evidence': str(evidence)}
    # Invalidate old success as soon as a new run starts.
    write(home / 'checks.json', report)
    write(home / ('checks-' + suite + '.json'), report)
    env = environment()
    try:
        if suite == 'frontend':
            execute([sys.executable, Path(__file__).with_name('agent_check.py'), '--root', source,
                     '--profile', 'frontend'], source, evidence, 'frontend', env, timeout=1800)
            decision = read(source / '.local/frontend-control/handoff.json')
            if decision.get('decision') != 'container_checks_passed' or decision.get('sourceUnchanged') is not True:
                raise RuntimeError('Fresh frontend evidence required')
            report['containerEvidence'] = decision
        elif suite == 'scene-ui':
            frontend_control.operate(source, 'deps', env=env)
            execute([sys.executable, Path(__file__).with_name('verify_scene_list_ui.py'), '--report-dir', evidence,
                     '--root', source, '--channel', 'msedge'], source, evidence, 'scene-ui', env)
            checks = read(evidence / 'validation-scene-list-ui.json')
            if not isinstance(checks, list) or not checks or any(c.get('passed') is not True for c in checks):
                raise RuntimeError('Scene UI assertions missing or failing')
            report['checks'] = checks
        elif suite in ('smoke', 'accounts', 'ingestion'):
            artifact = backend_artifact(source, home, sha, evidence, env, online)
            report['backend'] = artifact
            jar = Path(artifact['jar'])
            if suite == 'ingestion':
                frontend_control.operate(source, 'deps', env=env)
                execute([sys.executable, source / 'scripts/verify_ingestion.py', '--report-dir', evidence,
                         '--backend-jar', jar, '--resources-root', RESOURCES], source, evidence, 'ingestion', env)
                result = read(evidence / 'validation-ingestion.json')
                if result.get('passed') is not True or not result.get('checks') or any(c.get('passed') is not True for c in result['checks']):
                    raise RuntimeError('Ingestion evidence missing or failing')
                report['checks'] = result['checks']
            else:
                with Runtime(source, RESOURCES, evidence / suite, jar,
                             password='Ab1!xy' if suite == 'accounts' else None) as runtime:
                    if suite == 'accounts':
                        report['checks'] = account_smoke(runtime)
                    else:
                        frontend_control.operate(source, 'deps', env=env)
                        fixtures = seed_preview(runtime)
                        runtime.frontend()
                        report['checks'] = browser_smoke(runtime, fixtures)
                    report['postgresVersion'] = runtime.pg_version
        else:
            raise ValueError('Unknown suite')
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
    snapshot = read(home / 'snapshot.json')
    if snapshot.get('sha') != sha or not snapshot.get('requiredSuites'):
        raise RuntimeError('Prepared current-source evidence required')
    for suite in snapshot['requiredSuites']:
        passing(home, suite, sha)
    artifact = read(home / 'backend.json')
    jar = Path(artifact['jar'])
    if artifact.get('status') != 'passed' or artifact.get('sha') != sha or sha256(jar) != artifact['jarSha256']:
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
        deps = frontend_control.operate(source, 'deps', env=environment())
        if deps['status'] != 'passed':
            raise RuntimeError('Preview dependencies are not verified')
        clean(source, sha)
        with Runtime(source, RESOURCES, home / ('preview-' + uuid.uuid4().hex[:12]), jar) as runtime:
            fixtures = seed_preview(runtime)
            runtime.frontend()
            status, login = request(runtime.web, '/dev-api/login', 'POST',
                                    {'username': fixtures['username'], 'password': runtime.password})
            if status != 200 or login.get('code') != 200 or not login.get('token'):
                raise RuntimeError('Preview proxy login failed')
            credentials = runtime.directory / 'credentials.json'
            write(credentials, {'username': fixtures['username'], 'password': runtime.password})
            state.update(status='ready', url=runtime.web, credentialsFile=str(credentials),
                         runtime=str(runtime.directory), pid=os.getpid(), requiredSuites=snapshot['requiredSuites'],
                         fixtures=str(runtime.directory / 'fixtures.json'), manualAcceptance='pending')
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
    global RESOURCES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check', 'serve', 'status', 'stop'))
    parser.add_argument('--pr', type=int, required=True)
    parser.add_argument('--sha')
    parser.add_argument('--suite', choices=('auto', 'smoke', 'scene-ui', 'accounts', 'frontend', 'ingestion'), default='auto')
    parser.add_argument('--require-suite', action='append', default=[],
                        choices=('smoke', 'scene-ui', 'accounts', 'ingestion'),
                        help='Prepared Issue host suite; additive, never removes existing gates')
    parser.add_argument('--resources-root', type=Path, default=ROOT)
    parser.add_argument('--reviewed-sha', help='Explicit attestation by the independent reviewer, not an auto-approval')
    parser.add_argument('--online', action='store_true', help='Explicitly permit missing Maven dependency downloads')
    args = parser.parse_args()
    RESOURCES = args.resources_root.resolve()
    if args.action == 'prepare':
        result = prepare(args.pr, args.require_suite)
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
