"""Trusted, persistent Issue lifecycle. State lives outside agent writable roots."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import uuid

from symphony_publish import PublishError, REPO, api_response, git, publish, snapshot

TERMINAL = {'review', 'blocked'}
HOST_SUITES = {'smoke', 'scene-ui', 'accounts', 'ingestion'}


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


@contextmanager
def lock(home):
    home.mkdir(parents=True, exist_ok=True)
    with (home / 'owner.lock').open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            stream.write(b'0')
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def validate_plan(plan):
    required = {'title', 'profile', 'allowedPaths', 'javaModules', 'hostSuites', 'acceptance'}
    if not isinstance(plan, dict) or set(plan) != required:
        raise ValueError('Plan requires title/profile/allowedPaths/javaModules/hostSuites/acceptance')
    if plan['profile'] not in ('quick', 'frontend'):
        raise ValueError('Unsupported container profile')
    for field in ('title', 'acceptance'):
        if not isinstance(plan[field], str) or not plan[field].strip() or len(plan[field]) > 6000:
            raise ValueError('Invalid ' + field)
    for field in ('allowedPaths', 'javaModules', 'hostSuites'):
        if not isinstance(plan[field], list) or not all(isinstance(x, str) for x in plan[field]):
            raise ValueError('Invalid ' + field)
    if not plan['allowedPaths'] or any(p.startswith(('/', '.')) or '..' in p or '\\' in p
                                        for p in plan['allowedPaths']):
        raise ValueError('Explicit relative source paths/globs required')
    if any(not re.fullmatch(r'ruoyi-[a-z]+', m) for m in plan['javaModules']):
        raise ValueError('Invalid Java module')
    if not plan['hostSuites'] or not set(plan['hostSuites']) <= HOST_SUITES:
        raise ValueError('Select supported host acceptance suites')
    return plan


def fingerprint(root):
    paths = sorted(set(git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')) - {b''})
    digest = hashlib.sha256()
    for raw in paths:
        path = root / os.fsdecode(raw)
        digest.update(raw + b'\0')
        if path.is_symlink():
            digest.update(b'link:' + os.fsencode(os.readlink(path)))
        elif path.is_file():
            with path.open('rb') as stream:
                digest.update(hashlib.file_digest(stream, 'sha256').digest())
        else:
            digest.update(b'missing')
    return digest.hexdigest()


def changed_paths(root):
    tracked = git(root, 'diff', 'HEAD', '--name-only', '-z')
    added = git(root, 'ls-files', '--others', '--exclude-standard', '-z')
    return sorted(os.fsdecode(p) for p in set((tracked + added).split(b'\0')) - {b''})


class Task:
    def __init__(self, control_root, issue, root):
        if not re.fullmatch(r'GH-[1-9][0-9]*', issue):
            raise ValueError('GH-number required')
        self.home = Path(control_root) / issue
        self.root = Path(root).resolve()
        if self.home.resolve().is_relative_to(self.root):
            raise ValueError('Control state must be outside workspace')
        self.issue = issue
        self.cancel = threading.Event()
        self.process = None
        self.state_path = self.home / 'state.json'
        self.plan = validate_plan(read(self.home / 'plan.json'))
        self.state = read(self.state_path) if self.state_path.exists() else {
            'issue': issue, 'runId': uuid.uuid4().hex, 'status': 'prepared', 'checks': [], 'createdAt': now()}

    def update(self, **fields):
        self.state.update(fields, updatedAt=now())
        save(self.state_path, self.state)

    def begin(self):
        if self.state['status'] != 'prepared':
            if self.state['status'] not in TERMINAL:
                self.update(status='blocked', reason='previous_execution_interrupted; explicit resume required')
            return False
        base = git(self.root, 'rev-parse', 'HEAD').decode().strip()
        self.update(status='coding', baseCommit=base, startedAt=now())
        return True

    def start_check(self):
        if self.state['status'] not in ('coding', 'repair'):
            raise ValueError('Task is not accepting submissions')
        source = fingerprint(self.root)
        previous = self.state['checks']
        if previous and source == previous[-1]['source']:
            self.update(status='blocked', reason='unchanged_failed_submission')
            return False
        if len(previous) >= 2:
            self.update(status='blocked', reason='repair_limit_reached')
            return False
        paths = changed_paths(self.root)
        if git(self.root, 'rev-parse', 'HEAD').decode().strip() != self.state['baseCommit']:
            self.update(status='blocked', reason='agent_changed_git_head')
            return False
        if not paths or any(not any(fnmatch.fnmatchcase(p, pat) for pat in self.plan['allowedPaths']) for p in paths):
            self.update(status='blocked', reason='empty_or_out_of_scope_changes', paths=paths)
            return False
        if any(p.startswith('frontend/') for p in paths) and self.plan['profile'] != 'frontend':
            self.update(status='blocked', reason='frontend_plan_required')
            return False
        if any(p.startswith('backend/') for p in paths) and not self.plan['javaModules']:
            self.update(status='blocked', reason='java_modules_required')
            return False
        previous.append({'source': source, 'startedAt': now(), 'status': 'running'})
        self.update(status='checking', paths=paths)
        return True

    def finish_check(self, result):
        check = self.state['checks'][-1]
        check.update(result, finishedAt=now())
        if fingerprint(self.root) != check['source']:
            check.update(status='blocked', reason='source_changed_during_checks')
        status = check['status']
        if status == 'failed' and len(self.state['checks']) == 1:
            self.update(status='repair', reason='one_repair_remaining')
        else:
            self.update(status='review' if status == 'passed' else 'blocked',
                        reason='checks_passed_host_pending' if status == 'passed' else check.get('reason', 'checks_failed'))
        return self.state['status']

    def preserve(self):
        evidence = self.home / 'runs' / self.state['runId']
        evidence.mkdir(parents=True, exist_ok=True)
        problems = []
        try:
            (evidence / 'changes.patch').write_bytes(git(self.root, 'diff', '--binary', 'HEAD'))
            paths = changed_paths(self.root)
        except (OSError, PublishError, subprocess.SubprocessError) as exc:
            paths = self.state.get('paths', [])
            problems.append(type(exc).__name__)
        # Preserve untracked regular source files using the publisher's path rules.
        for name in paths:
            try:
                file = snapshot(self.root, [name])[0]
            except (PublishError, OSError, subprocess.SubprocessError):
                continue
            target = evidence / 'files' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file['data'])
        try:
            source = fingerprint(self.root)
        except (OSError, PublishError, subprocess.SubprocessError):
            source = None
            problems.append('source_fingerprint_unavailable')
        self.update(evidence=str(evidence), source=source, retainedWorkspace=str(self.root), preservationProblems=problems)
        save(evidence / 'handoff.json', {'plan': self.plan, 'state': self.state})


def run_checks(task, execution_root):
    """Runs while the model is idle. Each underlying process has its own timeout."""
    from harness import Step, run_step, environment
    evidence = task.home / 'runs' / task.state['runId'] / ('check-' + str(len(task.state['checks'])))
    evidence.mkdir(parents=True, exist_ok=True)
    env = environment(task.root)
    env.pop('DEEPSEEK_API_KEY', None)
    env.pop('GITHUB_TOKEN', None)
    python = task.root / '.local/venv/bin/python'
    if os.name == 'nt':
        python = Path(sys.executable)
    commands = [(f'java-{m}', [str(python), str(execution_root / 'check_java.py'), '--root', str(task.root), '--module', m], 600)
                for m in task.plan['javaModules']]
    commands.append(('container', [str(python), str(execution_root / 'agent_check.py'), '--root', str(task.root),
                                  '--profile', task.plan['profile']], 1800))
    results = []
    def own(process):
        task.process = process
        if process is not None and task.cancel.is_set():
            from harness import stop_tree
            stop_tree(process)
    for name, command, timeout in commands:
        if task.cancel.is_set():
            return {'status': 'blocked', 'reason': 'controller_interrupted'}
        result = run_step(Step(name, command, task.root, timeout), evidence, env,
                          process_callback=own, progress_stream=sys.stderr)
        if result.get('exitCode') == 2:
            result['status'] = 'blocked'
        results.append(result)
        if result['status'] != 'passed':
            return {'status': result['status'], 'reason': name + '_' + result['status'],
                    'steps': results, 'evidence': str(evidence)}
    handoff = read(task.root / '.local/frontend-control/handoff.json')
    if handoff.get('decision') != 'container_checks_passed' or handoff.get('sourceUnchanged') is not True:
        return {'status': 'blocked', 'reason': 'missing_current_check_evidence', 'steps': results}
    return {'status': 'passed', 'steps': results, 'evidence': str(evidence), 'handoff': handoff}


def delivery(task):
    """Yield tracker API operations; never give authentication or file bytes to the model."""
    def request(method, path, body=None):
        return {'method': method, 'path': REPO + path, **({'body': body} if body is not None else {})}

    number = task.issue[3:]
    branch = 'codex/issue-' + number
    task.preserve()
    task.update(delivery={'status': 'started', 'branch': branch})  # Durable before network mutation.
    try:
        if task.state.get('preservationProblems'):
            raise PublishError('snapshot_incomplete_workspace_retained')
        paths = changed_paths(task.root)
        if not paths or any(not any(fnmatch.fnmatchcase(p, pat) for pat in task.plan['allowedPaths']) for p in paths):
            raise PublishError('no_publishable_in_scope_changes')
        # A changed branch must never be silently used as a new base.
        head = task.state.get('publishedCommit', task.state['baseCommit'])
        receipt = yield from publish(task.root, {'branch': branch, 'expected_head': head,
                                                'paths': paths, 'message': task.plan['title']})
        task.update(publishedCommit=receipt['commit'], delivery={'status': 'files_published', **receipt})
        prs = api_response((yield request('GET', '/pulls?state=open&head=dailiuyi:' + branch)))
        if len(prs) > 1:
            raise PublishError('ambiguous_existing_pr')
        summary = ('容器检查通过；宿主验收待完成' if task.state['status'] == 'review'
                   else '未通过／待验收：' + task.state.get('reason', 'blocked'))
        body = '\n'.join([f'Refs #{number}', '', summary, '', task.plan['acceptance'], '',
                          '宿主专项：' + ', '.join(task.plan['hostSuites']),
                          '源码指纹：`' + task.state['source'] + '`',
                          '本地证据：`' + task.state['evidence'] + '`',
                          '未执行：独立审查、真实后端与浏览器验收、人工观感；不合并、不部署。'])
        if prs:
            pr = prs[0]
            if not pr.get('draft'):
                raise PublishError('existing_pr_not_draft_manual_handoff_required')
            pr = api_response((yield request('PATCH', '/pulls/' + str(pr['number']), {'body': body})))
        else:
            pr = api_response((yield request('POST', '/pulls', {'title': task.plan['title'], 'head': branch,
                                                              'base': 'main', 'draft': True, 'body': body})))
        task.update(delivery={**task.state['delivery'], 'status': 'draft_created', 'pr': pr['number'], 'url': pr['html_url']})
    except (PublishError, OSError, ValueError, KeyError, TypeError) as exc:
        task.update(status='blocked', reason=str(exc) if isinstance(exc, PublishError) else type(exc).__name__,
                    delivery={**task.state.get('delivery', {}), 'status': 'blocked'})
        if str(exc) in ('github_request_failed_status_0', 'github_request_failed_status_500',
                        'github_request_failed_status_502', 'github_request_failed_status_503',
                        'github_request_failed_status_504', 'publication_head_unconfirmed_inspect_remote'):
            yield from inspect_uncertain_delivery(task, str(exc))
    label = 'symphony:review' if task.state['status'] == 'review' else 'symphony:blocked'
    # Local terminal state precedes remote labels. Label failure cannot restart inference.
    try:
        api_response((yield request('POST', '/issues/' + number + '/labels', {'labels': [label]})))
        opposite = 'symphony:blocked' if label == 'symphony:review' else 'symphony:review'
        reply = yield request('DELETE', '/issues/' + number + '/labels/' + opposite)
        api_response(reply, (200, 204, 404))
        task.update(labelsUpdated=True)
        api_response((yield request('DELETE', '/issues/' + number + '/labels/symphony:ready')), (200, 204, 404))
    except (PublishError, KeyError, TypeError):
        task.update(labelsUpdated=False)
    return task.state


def inspect_uncertain_delivery(task, reason):
    """Exactly one readback per endpoint; never repeat an uncertain write."""
    branch = 'codex/issue-' + task.issue[3:]
    task.update(status='blocked', reason=reason, delivery={**task.state.get('delivery', {}),
                                                        'status': 'uncertain', 'readbackStarted': True})
    observations = {}
    for key, path in [('branch', '/git/ref/heads/' + branch),
                      ('pulls', '/pulls?state=open&head=dailiuyi:' + branch)]:
        reply = yield {'method': 'GET', 'path': REPO + path}
        body = reply.get('body', {})
        if key == 'branch':
            observations[key] = {'status': reply.get('status'), 'sha': body.get('object', {}).get('sha') if isinstance(body, dict) else None}
        else:
            observations[key] = {'status': reply.get('status'), 'items': [
                {k: pr.get(k) for k in ('number', 'html_url', 'draft')} for pr in body] if isinstance(body, list) else []}
        task.update(delivery={**task.state['delivery'], 'observations': observations})
    return task.state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'status', 'resume'))
    parser.add_argument('--state-root', required=True, type=Path)
    parser.add_argument('--issue', required=True)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--reason')
    args = parser.parse_args()
    if not re.fullmatch(r'GH-[1-9][0-9]*', args.issue):
        parser.error('GH-number required')
    home = args.state_root / args.issue
    with lock(home):
        state_file = home / 'state.json'
        if args.action == 'prepare':
            if (home / 'plan.json').exists():
                parser.error('Plan already exists; preserve it and use explicit resume')
            if not args.plan:
                parser.error('--plan required')
            save(home / 'plan.json', validate_plan(read(args.plan)))
        elif args.action == 'resume':
            if not args.reason or not args.reason.strip():
                parser.error('--reason required for operator resume')
            state = read(state_file)
            if state['status'] not in TERMINAL:
                parser.error('Only a terminal task can be resumed')
            save(home / 'history' / (state['runId'] + '.json'), state)
            save(home / 'history' / (state['runId'] + '.plan.json'), read(home / 'plan.json'))
            if args.plan:
                save(home / 'plan.json', validate_plan(read(args.plan)))
            save(state_file, {'issue': args.issue, 'runId': uuid.uuid4().hex, 'status': 'prepared',
                              'checks': [], 'createdAt': now(), 'resumeReason': args.reason,
                              **({'publishedCommit': state['publishedCommit']} if state.get('publishedCommit') else {})})
        print(json.dumps(read(state_file) if state_file.exists() else {'status': 'prepared'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
