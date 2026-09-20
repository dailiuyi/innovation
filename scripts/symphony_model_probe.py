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
from urllib.parse import quote_plus

from symphony_codex_adapter import BEGIN, END, DEFAULT_MODEL, DEFAULT_EFFORT, add_catalog_page, select_route


class RpcClient:
    def __init__(self, command, stderr):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
        self.messages = queue.Queue()
        self.sequence = 1000
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
                # Smoke requests must never approve tools or permission changes.
                self.send({'id': msg['id'], 'error': {'code': -32601, 'message': 'Probe does not execute tools'}})
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
    if args.action == 'smoke':
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
                    for model, efforts in catalog.items() if model.startswith('gpt-')]}
            policies = {'granular': {'sandbox_approval': False, 'rules': False, 'mcp_elicitations': False,
                                    'request_permissions': False, 'skill_approval': False}}
            started = client.request('thread/start', {'cwd': os.getcwd(), 'approvalPolicy': policies,
                                                       'sandbox': 'read-only'})
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
            details = client.request('thread/read', {'threadId': thread_id})
            rollout = Path(details['thread']['path'])
            observed = []
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
                if observed:
                    break
                time.sleep(0.1)
            expected = {'model': args.model or DEFAULT_MODEL, 'effort': args.effort or DEFAULT_EFFORT}
            passed = status == 'completed' and bool(observed) and all(row == expected for row in observed)
            return {'status': 'passed' if passed else 'failed', 'threadId': thread_id,
                    'turnStatus': status, 'expected': expected, 'observedTurnContexts': observed,
                    'rolloutPath': str(rollout), 'labels': labels}
        finally:
            client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['catalog', 'validate', 'smoke'])
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
