"""Read Codex's GPT catalog, or verify a short routed turn against its rollout.

Run inside the Symphony image in an isolated home/workspace. Neither command
uses GitHub credentials or operates on issues. Evidence contains no prompts.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import quote_plus

from symphony_codex_adapter import (BEGIN, END, DEFAULT_MODEL, DEFAULT_EFFORT,
                                    DEEPSEEK_MODEL, DEEPSEEK_EFFORTS, add_catalog_page, select_route)


class RpcClient:
    def __init__(self, command, stderr):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
        self.messages = queue.Queue()
        self.sequence = 1000
        self.synthetic_token = None
        self.synthetic_calls = 0
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        for line in iter(self.process.stdout.readline, b''):
            self.messages.put(json.loads(line))
        self.messages.put(None)

    def send(self, message):
        self.process.stdin.write((json.dumps(message) + '\n').encode())
        self.process.stdin.flush()

    def wait(self, predicate, timeout=90):
        deadline = time.monotonic() + timeout
        while True:
            msg = self.messages.get(timeout=max(0.001, deadline - time.monotonic()))
            if msg is None:
                raise RuntimeError('app_server_exited')
            if 'id' in msg and 'method' in msg:
                params = msg.get('params', {})
                if (self.synthetic_token and msg['method'] == 'item/tool/call'
                        and params.get('tool') == 'routing_probe'
                        and params.get('arguments') == {'token': self.synthetic_token}):
                    self.synthetic_calls += 1
                    self.send({'id': msg['id'], 'result': {'success': True, 'contentItems': [
                        {'type': 'inputText', 'text': 'PROBE_TOOL_OK'}]}})
                else:
                    # Never approve permissions or service-side tools.
                    self.send({'id': msg['id'], 'error': {'code': -32601, 'message': 'Probe rejects this tool'}})
            if predicate(msg):
                return msg

    def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self.send({'id': request_id, 'method': method, 'params': params})
        msg = self.wait(lambda m: m.get('id') == request_id and 'method' not in m)
        if 'error' in msg:
            raise RuntimeError('rpc_failed:' + method)
        return msg['result']

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=8)
        self.thread.join(timeout=2)
        self.process.stdout.close()


def probe(args):
    args.output.parent.mkdir(parents=True, exist_ok=True)
    adapter = Path(__file__).with_name('symphony_codex_adapter.py')
    command = ['codex', 'app-server']
    if args.action in ('smoke', 'exercise'):
        command = [sys.executable, str(adapter), '--audit-log', str(args.output.with_suffix('.audit.jsonl'))]
    with args.output.with_suffix('.stderr.log').open('wb') as stderr:
        client = RpcClient(command, stderr)
        try:
            client.request('initialize', {'clientInfo': {'name': 'symphony-routing-probe', 'version': '1'},
                                          'capabilities': {'experimentalApi': True}})
            client.send({'method': 'initialized'})
            if args.action in ('catalog', 'validate'):
                catalog = {}
                cursor = None
                seen = set()
                while True:
                    params = {'limit': 100, 'includeHidden': False}
                    if cursor:
                        params['cursor'] = cursor
                    cursor = add_catalog_page(catalog, client.request('model/list', params))
                    if cursor is None:
                        break
                    if cursor in seen:
                        raise RuntimeError('repeated_catalog_cursor')
                    seen.add(cursor)
                if args.action == 'validate':
                    labels = []
                    if args.model is not None:
                        labels.append('symphony:model:' + args.model)
                    if args.effort is not None:
                        labels.append('symphony:effort:' + args.effort)
                    return {'status': 'passed', 'selection': select_route(labels, catalog)}
                return {'status': 'passed', 'models': [
                    {'model': model, 'efforts': sorted(efforts)}
                    for model, efforts in catalog.items() if model.startswith('gpt-')] + [
                    {'model': DEEPSEEK_MODEL, 'efforts': sorted(DEEPSEEK_EFFORTS),
                     'provider': 'deepseek', 'source': 'official_provider_configuration'}]}
            policies = {'granular': {'sandbox_approval': False, 'rules': False, 'mcp_elicitations': False,
                                    'request_permissions': False, 'skill_approval': False}}
            thread_params = {'cwd': os.getcwd(), 'approvalPolicy': policies, 'sandbox': 'read-only'}
            if args.action == 'exercise':
                client.synthetic_token = uuid.uuid4().hex
                Path('routing-seed.txt').write_text(client.synthetic_token)
                thread_params.update(sandbox='workspace-write', dynamicTools=[{
                    'name': 'routing_probe', 'description': 'Verify the token read from routing-seed.txt.',
                    'inputSchema': {'type': 'object', 'properties': {'token': {'type': 'string'}},
                                    'required': ['token'], 'additionalProperties': False}}])
            started = client.request('thread/start', thread_params)
            thread_id = started['thread']['id']
            labels = []
            if args.model:
                labels.append('symphony:model:' + args.model)
            if args.effort:
                labels.append('symphony:effort:' + args.effort)
            prompt = '\n'.join([BEGIN, 'issue=GH-routing-probe',
                                 *['label=' + quote_plus(label) for label in labels], END,
                                 'Reply with exactly ROUTING_OK. Do not call any tools.'])
            client.request('turn/start', {'threadId': thread_id, 'cwd': os.getcwd(), 'approvalPolicy': policies,
                                          'sandboxPolicy': {'type': 'readOnly'},
                                          'input': [{'type': 'text', 'text': prompt}]})
            completed = client.wait(lambda m: m.get('method') == 'turn/completed', timeout=180)
            status = completed['params']['turn']['status']
            exercise_ok = True
            if args.action == 'exercise':
                client.request('turn/start', {'threadId': thread_id, 'cwd': os.getcwd(),
                    'approvalPolicy': policies, 'sandboxPolicy': {'type': 'workspaceWrite',
                    'writableRoots': [], 'networkAccess': False}, 'input': [{'type': 'text', 'text':
                    'Use the shell tool to read routing-seed.txt and write its exact content to '
                    'routing-result.txt in the current directory. Then call routing_probe with '
                    'that token. Do not inspect environment variables or credentials.'}]})
                completed = client.wait(lambda m: m.get('method') == 'turn/completed', timeout=180)
                status = completed['params']['turn']['status']
                result_file = Path('routing-result.txt')
                exercise_ok = (client.synthetic_calls > 0 and result_file.is_file()
                               and result_file.read_text().strip() == client.synthetic_token)
            details = client.request('thread/read', {'threadId': thread_id})
            rollout = Path(details['thread']['path'])
            observed = []
            providers = []
            # The rollout writer can lag the completion notification briefly.
            for _ in range(30):
                if rollout.is_file():
                    for line in rollout.read_text(encoding='utf-8').splitlines():
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if event.get('type') == 'turn_context':
                            payload = event['payload']
                            observed.append({'model': payload.get('model'), 'effort': payload.get('effort')})
                        if event.get('type') == 'session_meta':
                            providers.append(event['payload'].get('model_provider'))
                if observed:
                    break
                time.sleep(0.1)
            expected = {'model': args.model or DEFAULT_MODEL, 'effort': args.effort or DEFAULT_EFFORT}
            passed = (status == 'completed' and bool(observed) and exercise_ok
                      and all(row == expected for row in observed))
            if args.action == 'exercise':
                passed = passed and len(observed) >= 2
            if args.model == DEEPSEEK_MODEL:
                passed = passed and bool(providers) and all(p == 'deepseek' for p in providers)
            return {'status': 'passed' if passed else 'failed', 'threadId': thread_id,
                    'turnStatus': status, 'expected': expected, 'observedTurnContexts': observed,
                    'rolloutPath': str(rollout), 'labels': labels, 'observedProviders': providers,
                    'syntheticToolCalls': client.synthetic_calls, 'exercisePassed': exercise_ok}
        finally:
            client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['catalog', 'validate', 'smoke', 'exercise'])
    parser.add_argument('--model')
    parser.add_argument('--effort')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = probe(args)
    except Exception as exc:
        result = {'status': 'failed', 'reason': str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__}
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
