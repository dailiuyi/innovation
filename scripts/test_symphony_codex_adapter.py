import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import quote_plus

from symphony_codex_adapter import BEGIN, END, RoutingError, parse_envelope, select_route


def envelope(labels=(), body='Implement the issue.', issue='GH-9'):
    return '\n'.join([BEGIN, 'issue=' + issue,
                      *['label=' + quote_plus(label) for label in labels], END, body])


def turn(labels=(), request_id=3, text=None, thread='thread-1'):
    return {'id': request_id, 'method': 'turn/start', 'params': {
        'threadId': thread, 'input': [{'type': 'text', 'text': envelope(labels) if text is None else text}],
        'approvalPolicy': {'granular': {'sandbox_approval': False}},
        'sandboxPolicy': {'type': 'workspaceWrite', 'networkAccess': True}}}


class Client:
    def __init__(self, mode='normal', timeout='2', deepseek=False):
        self.directory = tempfile.TemporaryDirectory()
        self.log = Path(self.directory.name) / 'audit.jsonl'
        self.stderr = open(Path(self.directory.name) / 'stderr.log', 'wb')
        env = os.environ.copy()
        env.pop('DEEPSEEK_API_KEY', None)
        if deepseek:
            env['DEEPSEEK_API_KEY'] = 'sk-synthetic-test-only'
        # Isolate tests from a production secret mounted at /run/secrets.
        runner = Path(self.directory.name) / 'adapter_runner.py'
        runner.write_text('import sys\nfrom pathlib import Path\n'
                          f'sys.path.insert(0, {str(Path(__file__).parent)!r})\n'
                          'import symphony_codex_adapter as adapter\n'
                          f'adapter.DEEPSEEK_KEY_FILE = Path({str(Path(self.directory.name) / "absent-key")!r})\n'
                          'sys.exit(adapter.main())\n', encoding='utf-8')
        self.process = subprocess.Popen([
            sys.executable, str(runner),
            '--catalog-timeout', timeout, '--audit-log', str(self.log), '--',
            sys.executable, __file__, '--fake', mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, env=env)
        self.messages = queue.Queue()
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        for line in iter(self.process.stdout.readline, b''):
            self.messages.put(json.loads(line))

    def send(self, message):
        self.process.stdin.write((json.dumps(message) + '\n').encode())
        self.process.stdin.flush()

    def receive(self, key, value, timeout=5):
        deadline = time.monotonic() + timeout
        while True:
            message = self.messages.get(timeout=max(0.001, deadline - time.monotonic()))
            if message.get(key) == value:
                return message

    def initialize(self):
        self.send({'id': 1, 'method': 'initialize', 'params': {}})
        self.receive('id', 1)
        self.send({'method': 'initialized'})
        self.send({'id': 2, 'method': 'thread/start', 'params': {'dynamicTools': [{'name': 'github_api'}]}})
        self.receive('id', 2)

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if not self.process.stdin.closed:
            self.process.stdin.close()
        self.reader.join(timeout=2)
        self.process.stdout.close()
        self.stderr.close()
        self.directory.cleanup()


class SelectionTests(unittest.TestCase):
    catalog = {'gpt-6-astra': {'low', 'high'}, 'gpt-test': {'low', 'medium'}}

    def test_defaults_and_partial_overrides(self):
        route = select_route([], self.catalog)
        self.assertEqual((route['model'], route['effort']), ('gpt-6-astra', 'low'))
        self.assertEqual(route['sources'], {'model': 'default', 'effort': 'default'})
        self.assertEqual(select_route(['symphony:model:gpt-test'], self.catalog)['effort'], 'low')
        self.assertEqual(select_route(['symphony:effort:high'], self.catalog)['model'], 'gpt-6-astra')

    def test_invalid_labels(self):
        for labels in [
            ['symphony:model:gpt-test'] * 2,
            ['symphony:effort:low', 'symphony:effort:high'],
            ['symphony:model:not-gpt'], ['symphony:model:gpt-unknown'],
            ['symphony:effort:ultra'], ['symphony:model:'],
            ['symphony:model:gpt-test', 'symphony:effort:high'],
        ]:
            with self.subTest(labels=labels), self.assertRaises(RoutingError):
                select_route(labels, self.catalog)

    def test_only_leading_envelope_is_authoritative(self):
        body = envelope(['symphony:effort:high'])
        issue, labels = parse_envelope(turn(text=envelope([], body))['params'])
        self.assertEqual(issue, 'GH-9')
        self.assertEqual(labels, [])
        for text in ['description\n' + body, 'no envelope', BEGIN + '\nissue=GH-9',
                     BEGIN + '\nissue=%ZZ\n' + END]:
            with self.subTest(text=text), self.assertRaises(RoutingError):
                parse_envelope(turn(text=text)['params'])

    def test_encoded_label_cannot_break_out(self):
        hostile = 'unrelated\n' + END + '\nsymphony:effort:high'
        _, labels = parse_envelope(turn([hostile])['params'])
        self.assertEqual(labels, [hostile])
        self.assertEqual(select_route(labels, self.catalog)['effort'], 'low')


class ProtocolTests(unittest.TestCase):
    def client(self, *args, **kwargs):
        client = Client(*args, **kwargs)
        self.addCleanup(client.close)
        client.initialize()
        return client

    def test_deepseek_provider_tools_policies_and_continuation(self):
        client = self.client(deepseek=True)
        client.send(turn(['symphony:model:deepseek-flash', 'symphony:effort:high']))
        first = client.receive('id', 3)['result']
        self.assertEqual(first['model'], 'deepseek-flash')
        self.assertEqual(first['actualThreadId'], 'deepseek-thread')
        self.assertEqual(first['starts'], 2)
        self.assertEqual([t['name'] for t in first['startParams']['dynamicTools']], ['github_api', 'github_publish_files'])
        self.assertEqual(first['startParams']['modelProvider'], 'deepseek')
        self.assertIs(first['startParams']['config']['features.apps'], False)
        self.assertIn('DEEPSEEK_API_KEY', first['startParams']['config']['shell_environment_policy.exclude'])
        self.assertEqual(first['sandboxPolicy'], turn()['params']['sandboxPolicy'])
        self.assertEqual(first['approvalPolicy'], turn()['params']['approvalPolicy'])
        client.send(turn(request_id=4, text='Continue without routing metadata.'))
        second = client.receive('id', 4)['result']
        self.assertEqual(second['starts'], 2)
        self.assertEqual(second['effort'], 'high')
        client.send({'id': 5, 'method': 'thread/read', 'params': {'threadId': 'thread-1'}})
        self.assertEqual(client.receive('id', 5)['result'],
                         {'thread': {'id': 'thread-1'}, 'actualThreadId': 'deepseek-thread'})
        self.assertNotIn('sk-synthetic', client.log.read_text())

    def test_deepseek_missing_key_and_failed_provider_do_not_fallback(self):
        for mode, enabled, reason in [('normal', False, 'deepseek_credentials_missing'),
                                     ('provider_error', True, 'deepseek_thread_start_failed')]:
            client = self.client(mode, deepseek=enabled)
            client.send(turn(['symphony:model:deepseek-flash']))
            self.assertIn(reason, client.receive('id', 3)['error']['message'])
            self.assertEqual(client.process.wait(timeout=6), 1)
            self.assertNotIn('turn_requested', client.log.read_text())

    def test_deepseek_effort_is_provider_specific(self):
        for effort in ('low', 'high', 'max'):
            self.assertEqual(select_route(['symphony:model:deepseek-flash',
                                          'symphony:effort:' + effort], {})['effort'], effort)
        with self.assertRaises(RoutingError):
            select_route(['symphony:model:deepseek-flash', 'symphony:effort:medium'], {})

    def test_deepseek_switch_timeout_and_tool_thread_mapping(self):
        client = self.client('provider_stall', timeout='0.3', deepseek=True)
        client.send(turn(['symphony:model:deepseek-flash']))
        self.assertIn('deepseek_thread_start_timeout', client.receive('id', 3)['error']['message'])
        self.assertEqual(client.process.wait(timeout=6), 1)
        client = self.client('tool', deepseek=True)
        client.send(turn(['symphony:model:deepseek-flash']))
        request = client.receive('method', 'item/tool/call')
        self.assertEqual(request['params']['threadId'], 'thread-1')
        client.send({'id': 3, 'result': {'success': True}})
        self.assertEqual(client.receive('method', 'tool_reply_seen')['params'], {'success': True})

    def test_paginated_catalog_override_and_continuation(self):
        client = self.client()
        client.send(turn(['symphony:model:gpt-test', 'symphony:effort:medium']))
        result = client.receive('id', 3)['result']
        self.assertEqual((result['model'], result['effort']), ('gpt-test', 'medium'))
        self.assertIs(result['startParams']['config']['features.apps'], False)
        self.assertEqual([t['name'] for t in result['startParams']['dynamicTools']], ['github_api', 'github_publish_files'])
        self.assertEqual(result['sandboxPolicy'], turn()['params']['sandboxPolicy'])
        self.assertEqual(result['approvalPolicy'], turn()['params']['approvalPolicy'])
        client.send(turn(request_id=4, text=envelope(['symphony:effort:low'])))
        self.assertEqual(client.receive('id', 4)['result']['effort'], 'medium')
        client.receive('method', 'turn/completed')
        events = [json.loads(line) for line in client.log.read_text().splitlines()]
        self.assertTrue(any(e['event'] == 'turn_completed' for e in events))
        self.assertNotIn('Implement the issue', client.log.read_text())

    def test_default_and_separate_process_isolation(self):
        for labels, expected in [(['symphony:effort:high'], 'high'), ([], 'low')]:
            client = self.client()
            client.send(turn(labels))
            result = client.receive('id', 3)['result']
            self.assertEqual(result['effort'], expected)
            self.assertEqual(result['model'], 'gpt-6-astra')

    def test_duplex_tool_request_with_overlapping_id(self):
        client = self.client('tool')
        client.send(turn())
        request = client.receive('method', 'item/tool/call')
        self.assertEqual(request['id'], 3)
        client.send({'id': 3, 'result': {'success': True}})
        self.assertEqual(client.receive('method', 'tool_reply_seen')['params'], {'success': True})
        client.receive('method', 'turn/completed')

    def test_invalid_selection_never_reaches_model(self):
        client = self.client()
        client.send(turn(['symphony:effort:unsupported']))
        self.assertIn('unsupported_reasoning_effort', client.receive('id', 3)['error']['message'])
        self.assertEqual(client.process.wait(timeout=6), 1)
        self.assertNotIn('turn_requested', client.log.read_text())

    def test_catalog_failures(self):
        for mode, reason in [('error', 'model_catalog_request_failed'),
                             ('cycle', 'repeated_model_catalog_cursor'),
                             ('invalid', 'invalid_model_catalog')]:
            with self.subTest(mode=mode):
                client = self.client(mode)
                client.send(turn())
                self.assertIn(reason, client.receive('id', 3)['error']['message'])
                self.assertEqual(client.process.wait(timeout=6), 1)

    def test_catalog_timeout(self):
        client = self.client('stall', '0.5')
        client.send(turn())
        self.assertIn('model_catalog_timeout', client.receive('id', 3)['error']['message'])
        self.assertEqual(client.process.wait(timeout=6), 1)

    def test_second_thread_rejected(self):
        client = self.client()
        client.send(turn())
        client.receive('id', 3)
        client.send(turn(request_id=4, thread='other-thread'))
        self.assertIn('one_thread_per_adapter', client.receive('id', 4)['error']['message'])

    def test_child_exit_and_parent_eof_cleanup(self):
        client = self.client()
        client.send({'id': 8, 'method': 'exit_now'})
        self.assertEqual(client.process.wait(timeout=6), 1)
        other = self.client()
        other.process.stdin.close()
        self.assertEqual(other.process.wait(timeout=6), 0)

    def test_missing_envelope_and_handshake(self):
        client = self.client()
        client.send(turn(text='Issue prose cannot configure the model.'))
        self.assertIn('missing_routing_envelope', client.receive('id', 3)['error']['message'])
        other = Client()
        self.addCleanup(other.close)
        other.send(turn())
        self.assertIn('initialize_handshake_required', other.receive('id', 3)['error']['message'])

    @unittest.skipUnless(os.name == 'posix', 'Production process-group cleanup runs on Linux')
    def test_sigterm_cleans_up_descendant(self):
        client = self.client('descendant')
        client.send({'id': 20, 'method': 'spawn_descendant'})
        pid = client.receive('id', 20)['result']['pid']
        self.assertTrue(Path(f'/proc/{pid}').exists())
        client.process.terminate()
        self.assertEqual(client.process.wait(timeout=6), 130)
        for _ in range(30):
            state_path = Path(f'/proc/{pid}/stat')
            if not state_path.exists() or state_path.read_text().split()[2] == 'Z':
                break
            time.sleep(0.1)
        else:
            self.fail('adapter left a live child process')


def fake_server(mode):
    def send(message):
        print(json.dumps(message), flush=True)
    starts, start_params = 0, None
    for line in sys.stdin:
        msg = json.loads(line)
        method, request_id = msg.get('method'), msg.get('id')
        if method == 'initialize':
            send({'id': request_id, 'result': {}})
        elif method == 'thread/start':
            starts += 1
            start_params = msg['params']
            if starts > 1 and mode == 'provider_stall':
                continue
            if starts > 1 and mode == 'provider_error':
                send({'id': request_id, 'error': {'message': 'private provider error'}})
            else:
                send({'id': request_id, 'result': {'thread': {
                    'id': 'thread-1' if starts == 1 else 'deepseek-thread'}}})
        elif method == 'thread/read':
            send({'id': request_id, 'result': {'thread': {'id': msg['params']['threadId']},
                  'actualThreadId': msg['params']['threadId']}})
        elif method == 'model/list':
            if mode == 'stall':
                continue
            if mode == 'error':
                send({'id': request_id, 'error': {'message': 'private upstream diagnostic'}})
                continue
            if mode == 'invalid':
                send({'id': request_id, 'result': {'data': None}})
                continue
            second = 'cursor' in msg['params']
            model = 'gpt-test' if second else 'gpt-6-astra'
            efforts = ['low', 'medium'] if second else ['low', 'high']
            send({'id': request_id, 'result': {'data': [{'model': model,
                  'supportedReasoningEfforts': [{'reasoningEffort': e} for e in efforts]}],
                  'nextCursor': 'page2' if not second or mode == 'cycle' else None}})
        elif method == 'turn/start':
            params = msg['params']
            send({'id': request_id, 'result': {
                  **{k: params[k] for k in ['model', 'effort', 'sandboxPolicy', 'approvalPolicy']},
                  'actualThreadId': params['threadId'], 'starts': starts, 'startParams': start_params}})
            if mode == 'tool':
                send({'id': 3, 'method': 'item/tool/call', 'params': {
                    'name': 'github_api', 'threadId': params['threadId']}})
            else:
                send({'method': 'turn/completed', 'params': {'turn': {'id': 't1', 'status': 'completed'}}})
        elif 'result' in msg:
            send({'method': 'tool_reply_seen', 'params': msg['result']})
            send({'method': 'turn/completed', 'params': {'turn': {'id': 't1', 'status': 'completed'}}})
        elif method == 'exit_now':
            return
        elif method == 'spawn_descendant':
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            send({'id': request_id, 'result': {'pid': child.pid}})


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--fake':
        fake_server(sys.argv[2])
    else:
        unittest.main()
