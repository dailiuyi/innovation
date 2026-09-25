"""Explicit live DeepSeek exercise in a disposable container, with host tracker transport.

Requires an operator-created synthetic Issue. Never queues it in the daily scheduler,
merges a PR, deploys the application or imports a GitHub token into the agent shell.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from urllib.parse import quote_plus

from symphony_task import save
from symphony_publish import gh_request, REPO


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--issue', type=int, required=True)
    parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--auth-file', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--seccomp', type=Path, required=True)
    args = parser.parse_args()
    if args.issue < 1:
        parser.error('Positive Issue number required')
    home = args.fixture_root.resolve()
    home.mkdir(parents=True, exist_ok=True)
    issue = 'GH-' + str(args.issue)
    workspace = home / 'data/workspaces' / issue
    if workspace.exists():
        parser.error('Fixture already exists; inspect retained evidence, never silently retry')
    workspace.mkdir(parents=True, exist_ok=True)
    bundle = home / 'bundle'
    shutil.copytree(Path(__file__).parent, bundle, ignore=shutil.ignore_patterns('__pycache__'))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.glob('*.py')}
    save(home / 'bundle.json', hashes)
    (home / 'data/codex').mkdir(parents=True)
    plan = {'title': '验收控制链路：补充场景列表操作提示', 'profile': 'frontend',
            'allowedPaths': ['frontend/src/views/demo/scenes.vue'], 'javaModules': [],
            'hostSuites': ['smoke', 'scene-ui'],
            'acceptance': '仅在场景列表现有说明中补充“点击版本与文件可直接管理该场景资源。”，保留四按钮和所有功能。'}
    save(home / 'data/task-control' / issue / 'plan.json', plan)
    image = 'innovation-symphony:0.0.3-java-v2'
    name = 'innovation-control-smoke-' + str(args.issue)
    mounts = ['--mount', f'type=bind,source={home / "data"},target=/data',
              '--mount', f'type=bind,source={bundle},target=/opt/symphony-routing,readonly',
              '--mount', f'type=bind,source={bundle},target=/opt/symphony-execution,readonly']
    common = ['docker', 'run', '--rm', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
              '--security-opt', 'seccomp=' + str(args.seccomp.resolve()), '--memory', '4g', '--cpus', '2',
              '-w', '/data/workspaces/' + issue,
              '-e', 'GIT_CONFIG_COUNT=1', '-e', 'GIT_CONFIG_KEY_0=safe.directory',
              '-e', 'GIT_CONFIG_VALUE_0=/data/workspaces/' + issue,
              *mounts, '--entrypoint', 'python3']
    # Clone with the execution platform's Git/line endings, just like Symphony.
    subprocess.run([*common[:-2], '--entrypoint', 'git', image, 'clone', '--depth', '1',
                    'https://github.com/dailiuyi/innovation-ar-resource-platform.git', '.'], check=True)
    subprocess.run([*common, image, '/opt/symphony-tools/prepare_workspace.py'], check=True)
    command = [*common[:-2], '--name', name, '-i',
               '--mount', f'type=bind,source={home / "data/codex"},target=/home/node/.codex',
               '--mount', f'type=bind,source={args.auth_file.resolve()},target=/home/node/.codex/auth.json,readonly',
               '--mount', f'type=bind,source={args.key_file.resolve()},target=/run/secrets/symphony-deepseek,readonly',
               '--entrypoint', 'python3', image, '/opt/symphony-routing/symphony_codex_adapter.py',
               '--control-root', '/data/task-control', '--execution-root', '/opt/symphony-execution',
               '--audit-log', '/data/control-audit.jsonl']
    metrics = {'issue': args.issue, 'model': 'deepseek-flash', 'effort': 'high', 'commands': [], 'toolCalls': 0}
    started = time.monotonic()
    messages = queue.Queue()
    with (home / 'adapter.stderr.log').open('wb') as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
        def reader():
            for line in iter(process.stdout.readline, b''):
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    messages.put({'fatal': 'invalid_protocol_output'})
            messages.put(None)
        threading.Thread(target=reader, daemon=True).start()
        def send(value):
            process.stdin.write((json.dumps(value) + '\n').encode())
            process.stdin.flush()
        def wait(predicate):
            while True:
                try:
                    msg = messages.get(timeout=30)
                except queue.Empty:
                    print('RUNNING controlled smoke; seconds=' + str(int(time.monotonic() - started)), flush=True)
                    continue
                if msg is None or 'fatal' in msg:
                    raise RuntimeError('Adapter exited; inspect retained stderr/state')
                if msg.get('method') == 'item/started':
                    item = msg.get('params', {}).get('item', {})
                    metrics['toolCalls'] += item.get('type') in ('commandExecution', 'dynamicToolCall', 'fileChange')
                    if item.get('type') == 'commandExecution':
                        metrics['commands'].append(item.get('command', ''))
                if 'id' in msg and 'method' in msg:
                    params = msg.get('params', {})
                    request = params.get('arguments', {})
                    if ((params.get('name') or params.get('tool')) != 'github_api'
                            or not str(request.get('path', '')).startswith(REPO + '/')
                            or (request.get('method', 'GET') != 'GET' and not str(msg['id']).startswith('symphony-control-'))):
                        result = {'status': 403, 'body': {}}
                    else:
                        try:
                            result = gh_request(request)
                        except Exception:
                            result = {'status': 0, 'body': {}}
                    send({'id': msg['id'], 'result': {'success': True, 'contentItems': [
                        {'type': 'inputText', 'text': json.dumps(result)}]}})
                if predicate(msg):
                    if 'error' in msg:
                        raise RuntimeError('Adapter request rejected; inspect state')
                    return msg
        try:
            send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'controlled-smoke', 'version': '1'},
                                                          'capabilities': {'experimentalApi': True}}})
            wait(lambda m: m.get('id') == 1)
            send({'method': 'initialized'})
            policies = {'granular': {k: False for k in ('sandbox_approval', 'rules', 'mcp_elicitations', 'request_permissions', 'skill_approval')}}
            send({'id': 2, 'method': 'thread/start', 'params': {'cwd': '/data/workspaces/' + issue,
                'approvalPolicy': policies, 'sandbox': 'workspace-write', 'dynamicTools': [{
                'name': 'github_api', 'description': 'Read this task repository. Controller owns writes.',
                'inputSchema': {'type': 'object', 'properties': {'method': {'type': 'string'}, 'path': {'type': 'string'},
                                                               'body': {'type': 'object'}}, 'required': ['method', 'path']}}]}})
            thread = wait(lambda m: m.get('id') == 2)['result']['thread']['id']
            prompt = '\n'.join(['[SYMPHONY_ROUTING_V1]', 'issue=' + issue,
                'label=' + quote_plus('symphony:model:deepseek-flash'), 'label=' + quote_plus('symphony:effort:high'),
                '[/SYMPHONY_ROUTING_V1]', plan['acceptance'],
                '这是隔离控制器实跑；仅实现此小改动，不运行检查、不安装环境、不 Git 提交、不操作 GitHub。完成后结束本轮，由控制器处理检查与草稿交付。'])
            send({'id': 3, 'method': 'turn/start', 'params': {'threadId': thread, 'cwd': '/data/workspaces/' + issue,
                'approvalPolicy': policies, 'sandboxPolicy': {'type': 'workspaceWrite',
                    'writableRoots': ['/data/cache/pip', '/data/cache/npm'], 'networkAccess': True},
                'input': [{'type': 'text', 'text': prompt}]}})
            wait(lambda m: m.get('id') == 3)
            wait(lambda m: m.get('method') == 'turn/completed')
            process.wait(timeout=15)
        finally:
            if process.poll() is None:
                process.stdin.close()
                subprocess.run(['docker', 'stop', '-t', '10', name], capture_output=True, timeout=25)
                process.wait(timeout=15)
            metrics['seconds'] = round(time.monotonic() - started, 2)
            save(home / 'metrics.json', metrics)
    state = json.loads((home / 'data/task-control' / issue / 'state.json').read_text(encoding='utf-8'))
    print(json.dumps({'state': state, 'metrics': metrics}, ensure_ascii=False, indent=2))
    return 0 if state['status'] == 'review' and state.get('delivery', {}).get('status') == 'draft_created' else 2


if __name__ == '__main__':
    raise SystemExit(main())
