"""Symphony stdio bridge: validate issue labels and pin Codex model/effort.

Only the leading workflow-owned envelope is parsed. No tracker credentials,
network requests or shell evaluation are needed by this bridge.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import unquote_plus
import uuid
from symphony_publish import TOOL_NAME, TOOL_SPEC, PublishError, publish

DEFAULT_MODEL = 'gpt-6-astra'
DEFAULT_EFFORT = 'low'
DEEPSEEK_MODEL = 'deepseek-flash'
DEEPSEEK_EFFORTS = {'low', 'high', 'max'}
DEEPSEEK_KEY_FILE = Path('/run/secrets/symphony-deepseek')
WORKSPACE_ROOT = Path('/data/workspaces')


def deepseek_config():
    return {
        'model_providers.deepseek': {
            'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com',
            'env_key': 'DEEPSEEK_API_KEY', 'wire_api': 'responses',
            'requires_openai_auth': False,
        },
        'model_context_window': 1048576,
        'model_auto_compact_token_limit': 900000,
        'model_reasoning_summary': 'none',
    }


def remap_thread(message, source, target):
    """Translate protocol thread references, never prompt or tool content."""
    result = copy.deepcopy(message)
    for obj in (result.get('params'), result.get('result')):
        if not isinstance(obj, dict):
            continue
        if obj.get('threadId') == source:
            obj['threadId'] = target
        if isinstance(obj.get('thread'), dict) and obj['thread'].get('id') == source:
            obj['thread']['id'] = target
    return result
BEGIN = '[SYMPHONY_ROUTING_V1]'
END = '[/SYMPHONY_ROUTING_V1]'


class RoutingError(ValueError):
    pass


def parse_envelope(params):
    inputs = params.get('input', [])
    if not inputs or inputs[0].get('type') != 'text':
        raise RoutingError('missing_routing_envelope')
    text = inputs[0].get('text', '')
    lines = text.splitlines()
    if not lines or lines[0] != BEGIN:
        raise RoutingError('missing_routing_envelope')
    issue = None
    labels = []
    for line in lines[1:]:
        if line == END:
            if not issue:
                raise RoutingError('missing_issue_identifier')
            return issue, labels
        key, separator, encoded = line.partition('=')
        if not separator or key not in ('issue', 'label'):
            raise RoutingError('invalid_routing_envelope')
        if re.search(r'%(?![0-9a-fA-F]{2})', encoded):
            raise RoutingError('invalid_metadata_encoding')
        try:
            value = unquote_plus(encoded, errors='strict')
        except UnicodeError as exc:
            raise RoutingError('invalid_metadata_encoding') from exc
        if key == 'issue':
            if issue is not None or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value):
                raise RoutingError('invalid_issue_identifier')
            issue = value
        else:
            labels.append(value)
    raise RoutingError('unterminated_routing_envelope')


def select_route(labels, catalog):
    values = {}
    sources = {}
    for key, default in [('model', DEFAULT_MODEL), ('effort', DEFAULT_EFFORT)]:
        prefix = f'symphony:{key}:'
        matches = [label[len(prefix):] for label in labels if label.startswith(prefix)]
        if len(matches) > 1:
            raise RoutingError(f'duplicate_{key}_labels')
        values[key] = matches[0] if matches else default
        sources[key] = 'label' if matches else 'default'
    model = values['model']
    if model == DEEPSEEK_MODEL:
        supported = DEEPSEEK_EFFORTS
    elif re.fullmatch(r'gpt-[a-zA-Z0-9._-]+', model) and model in catalog:
        supported = catalog[model]
    else:
        raise RoutingError('unknown_or_non_gpt_model')
    if values['effort'] not in supported:
        raise RoutingError('unsupported_reasoning_effort')
    return {**values, 'sources': sources}


def add_catalog_page(catalog, result):
    if not isinstance(result, dict) or not isinstance(result.get('data'), list):
        raise RoutingError('invalid_model_catalog')
    for entry in result['data']:
        if not isinstance(entry, dict):
            raise RoutingError('invalid_model_catalog')
        model = entry.get('model')
        efforts = entry.get('supportedReasoningEfforts')
        if not isinstance(model, str) or not isinstance(efforts, list):
            raise RoutingError('invalid_model_catalog')
        supported = set()
        for item in efforts:
            if not isinstance(item, dict) or not isinstance(item.get('reasoningEffort'), str):
                raise RoutingError('invalid_model_catalog')
            supported.add(item['reasoningEffort'])
        catalog[model] = supported
    cursor = result.get('nextCursor')
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise RoutingError('invalid_model_catalog_cursor')
    return cursor


def write_message(stream, message):
    stream.write((json.dumps(message, ensure_ascii=True, separators=(',', ':')) + '\n').encode())
    stream.flush()


class Bridge:
    def __init__(self, command, catalog_timeout=30, audit_path=None):
        self.command = command
        self.catalog_timeout = catalog_timeout
        self.audit_path = audit_path
        self.events = queue.Queue(maxsize=256)
        self.catalog = {}
        self.catalog_id = None
        self.catalog_deadline = None
        self.catalog_ready = False
        self.catalog_error = None
        self.cursors = set()
        self.pending_turn = None
        self.route = None
        self.issue = None
        self.thread_id = None
        self.turn_requests = set()
        self.child = None
        self.start_params = None
        self.actual_thread_id = None
        self.switch_id = None
        self.switch_deadline = None
        self.switch_turn = None
        self.publish_job = None
        self.publish_request_id = None
        self.publish_deadline = None
        self.publish_seen = set()
        self.publish_call = None

    def publish_result(self, value, success):
        text = json.dumps(value, ensure_ascii=True)
        write_message(self.child.stdin, {'id': self.publish_call['id'], 'result': {
            'success': success, 'contentItems': [{'type': 'inputText', 'text': text}]}})
        self.publish_job = self.publish_call = self.publish_request_id = None
        self.publish_deadline = None

    def advance_publish(self, response=None):
        try:
            request = next(self.publish_job) if response is None else self.publish_job.send(response)
            self.publish_request_id = 'symphony-publish-' + uuid.uuid4().hex
            self.publish_deadline = time.monotonic() + 90
            params = copy.deepcopy(self.publish_call['params'])
            params.update(name='github_api', tool='github_api', arguments=request)
            params['threadId'] = self.thread_id
            write_message(sys.stdout.buffer, {'id': self.publish_request_id,
                          'method': 'item/tool/call', 'params': params})
        except StopIteration as done:
            self.audit('files_published', commit=done.value['commit'], status=done.value['status'])
            self.publish_result(done.value, True)
        except (PublishError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            self.publish_result({'status': 'blocked',
                                 'reason': str(exc) if isinstance(exc, PublishError) else type(exc).__name__,
                                 'next': 'Stop publishing; inspect remote branch and preserve workspace. No manual blob fallback.'}, False)

    def start_publish(self, message):
        if self.publish_job is not None:
            write_message(self.child.stdin, {'id': message['id'], 'result': {
                'success': False, 'contentItems': [{'type': 'inputText', 'text': 'publication_already_running'}]}})
            return
        self.publish_call = message
        params = message.get('params', {})
        args = params.get('arguments', {})
        key = json.dumps(args, sort_keys=True)
        root = Path((self.start_params or {}).get('cwd', ''))
        # Bind file access to the workflow-owned issue workspace, never a model-supplied root.
        if (not self.issue or not root.is_absolute() or root.name != self.issue or root.is_symlink()
                or root.resolve() != WORKSPACE_ROOT.resolve() / self.issue):
            self.publish_result({'status': 'blocked', 'reason': 'untrusted_workspace_root'}, False)
        elif key in self.publish_seen:
            self.publish_result({'status': 'blocked', 'reason': 'duplicate_publication_request_held'}, False)
        else:
            self.publish_seen.add(key)
            self.publish_job = publish(root, args)
            self.advance_publish()

    def audit(self, event, **fields):
        record = {'time': datetime.now(timezone.utc).isoformat(), 'event': event,
                  'issue': self.issue, 'threadId': self.actual_thread_id or self.thread_id,
                  'parentThreadId': self.thread_id, **fields}
        if self.route:
            record.update(self.route)
        line = json.dumps(record, ensure_ascii=True) + '\n'
        sys.stderr.write(line)
        sys.stderr.flush()
        if self.audit_path:
            with open(self.audit_path, 'a', encoding='utf-8') as stream:
                stream.write(line)

    def read_stream(self, stream, source):
        # Raw descriptor reads avoid holding Python's buffered-stdin lock in a
        # daemon thread when the child exits before the parent closes stdin.
        pending = b''
        try:
            while True:
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    if pending:
                        self.events.put((source, pending))
                    break
                pending += chunk
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    self.events.put((source, line))
        except OSError:
            pass
        finally:
            self.events.put((source, None))

    def request_catalog(self, cursor=None):
        self.catalog_id = 'symphony-routing-' + uuid.uuid4().hex
        if self.catalog_deadline is None:
            self.catalog_deadline = time.monotonic() + self.catalog_timeout
        params = {'limit': 100, 'includeHidden': False}
        if cursor is not None:
            params['cursor'] = cursor
        write_message(self.child.stdin, {'id': self.catalog_id, 'method': 'model/list', 'params': params})

    def fail_turn(self, message, reason):
        write_message(sys.stdout.buffer, {'id': message['id'], 'error': {
            'code': -32602, 'message': 'Symphony model routing: ' + reason}})
        self.audit('routing_rejected', reason=reason)

    def forward_turn(self, message):
        try:
            params = message['params']
            if self.route is None:
                self.issue, labels = parse_envelope(params)
                self.route = select_route(labels, self.catalog)
                self.thread_id = params['threadId']
                if self.route['model'] == DEEPSEEK_MODEL:
                    if not os.environ.get('DEEPSEEK_API_KEY'):
                        raise RoutingError('deepseek_credentials_missing')
                    if self.start_params is None:
                        raise RoutingError('thread_start_required')
                    # Provider is a thread setting, not a turn setting. Create an
                    # empty provider-specific thread before sending any prompt.
                    # Keep the complete original policies and dynamic tool specs.
                    routed = copy.deepcopy(self.start_params)
                    routed.update(model=DEEPSEEK_MODEL, modelProvider='deepseek')
                    routed['config'] = {**(routed.get('config') or {}), **deepseek_config()}
                    self.switch_id = 'symphony-provider-' + uuid.uuid4().hex
                    self.switch_deadline = time.monotonic() + self.catalog_timeout
                    self.switch_turn = message
                    write_message(self.child.stdin, {'id': self.switch_id,
                                  'method': 'thread/start', 'params': routed})
                    return True
            elif params.get('threadId') != self.thread_id:
                raise RoutingError('one_thread_per_adapter_required')
            params['model'] = self.route['model']
            params['effort'] = self.route['effort']
            # Explicitly pin on every turn; continuation prompts need no envelope.
            self.turn_requests.add(message['id'])
            self.audit('turn_requested', requestId=message['id'])
            write_message(self.child.stdin, remap_thread(message, self.thread_id,
                          self.actual_thread_id or self.thread_id))
            return True
        except RoutingError as exc:
            self.fail_turn(message, str(exc))
            return False

    def handle_parent(self, message):
        if ('method' not in message and isinstance(message.get('id'), str)
                and message['id'].startswith('symphony-publish-')):
            if message['id'] == self.publish_request_id:
                try:
                    result = message['result']
                    text = result.get('output') or result['contentItems'][0]['text']
                    self.advance_publish(json.loads(text))
                except (KeyError, IndexError, TypeError, ValueError):
                    self.publish_result({'status': 'blocked', 'reason': 'invalid_github_tool_response'}, False)
            return True  # Late responses never reach the model or trigger retries.
        method = message.get('method')
        if method == 'thread/start':
            if self.start_params is not None:
                self.fail_turn(message, 'one_thread_per_adapter_required')
                return False
            message = copy.deepcopy(message)
            params = message['params']
            config = dict(params.get('config') or {})
            # Unattended workers use the tracker-owned dynamic github_api tool.
            # Apps connectors can request interactive approval and must not be
            # inherited from the account in either GPT or provider threads.
            config['features.apps'] = False
            excluded = config.get('shell_environment_policy.exclude', [])
            config['shell_environment_policy.exclude'] = list(dict.fromkeys(
                [*excluded, 'DEEPSEEK_API_KEY']))
            params['config'] = config
            if any(t.get('name') == 'github_api' for t in params.get('dynamicTools', [])):
                params['dynamicTools'] = [t for t in params['dynamicTools'] if t.get('name') != TOOL_NAME] + [copy.deepcopy(TOOL_SPEC)]
            self.start_params = copy.deepcopy(params)
        if method == 'turn/start':
            if self.switch_id:
                self.fail_turn(message, 'concurrent_turn_start')
                return False
            if self.catalog_error:
                self.fail_turn(message, self.catalog_error)
                return False
            if self.catalog_ready:
                return self.forward_turn(message)
            if self.catalog_deadline is None:
                self.fail_turn(message, 'initialize_handshake_required')
                return False
            if self.pending_turn is not None:
                self.fail_turn(message, 'concurrent_turn_start')
                return False
            self.pending_turn = message
            return True
        write_message(self.child.stdin, remap_thread(message, self.thread_id,
                      self.actual_thread_id or self.thread_id))
        if method == 'initialized' and self.catalog_deadline is None:
            self.request_catalog()
        return True

    def handle_child(self, message):
        params = message.get('params', {})
        name = params.get('name') or params.get('tool')
        if message.get('method') == 'item/tool/call' and name == 'github_api':
            args = params.get('arguments', {})
            if (isinstance(args, dict) and args.get('method', 'GET').upper() != 'GET'
                    and re.search(r'/(git/blobs|contents)(/|$)', str(args.get('path', '')))):
                write_message(self.child.stdin, {'id': message['id'], 'result': {
                    'success': False, 'contentItems': [{'type': 'inputText',
                    'text': 'Use github_publish_files with paths. Manual file-content publication is disabled.'}]}})
                return True
        if (message.get('method') == 'item/tool/call'
                and (message.get('params', {}).get('name') or message.get('params', {}).get('tool')) == TOOL_NAME):
            self.start_publish(message)
            return True
        if self.switch_id and message.get('method') == 'thread/started':
            return True
        if self.switch_id and message.get('id') == self.switch_id and 'method' not in message:
            pending, self.switch_turn = self.switch_turn, None
            self.switch_id = None
            actual = message.get('result', {}).get('thread', {}).get('id')
            if 'error' in message or not isinstance(actual, str) or not actual:
                self.fail_turn(pending, 'deepseek_thread_start_failed')
                return False
            self.actual_thread_id = actual
            self.audit('provider_selected', provider='deepseek')
            return self.forward_turn(pending)
        if self.catalog_id is not None and message.get('id') == self.catalog_id:
            try:
                if 'error' in message:
                    raise RoutingError('model_catalog_request_failed')
                cursor = add_catalog_page(self.catalog, message.get('result'))
                if cursor:
                    if cursor in self.cursors:
                        raise RoutingError('repeated_model_catalog_cursor')
                    self.cursors.add(cursor)
                    self.request_catalog(cursor)
                    return True
                self.catalog_ready = True
                self.catalog_id = None
                self.audit('catalog_loaded', gptModelCount=sum(m.startswith('gpt-') for m in self.catalog))
            except RoutingError as exc:
                self.catalog_id = None
                self.catalog_error = str(exc)
                self.audit('catalog_failed', reason=self.catalog_error)
            if self.pending_turn:
                pending, self.pending_turn = self.pending_turn, None
                return self.handle_parent(pending)
            return True
        if message.get('id') in self.turn_requests and 'method' not in message:
            self.turn_requests.remove(message['id'])
            self.audit('turn_rejected' if 'error' in message else 'turn_accepted', requestId=message['id'])
        if message.get('method') == 'turn/completed':
            turn = message.get('params', {}).get('turn', {})
            self.audit('turn_completed', turnId=turn.get('id'), status=turn.get('status'))
        write_message(sys.stdout.buffer, remap_thread(message, self.actual_thread_id,
                      self.thread_id) if self.actual_thread_id else message)
        return True

    def stop_child(self):
        if self.child is None:
            return
        if self.child.stdin:
            self.child.stdin.close()
        if os.name == 'posix':
            try:
                os.killpg(self.child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif self.child.poll() is None:
            self.child.terminate()
        try:
            self.child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait(timeout=3)
        finally:
            if os.name == 'posix':
                try:
                    os.killpg(self.child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def run(self):
        self.child = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=sys.stderr, start_new_session=os.name == 'posix')
        for stream, source in [(sys.stdin.buffer, 'parent'), (self.child.stdout, 'child')]:
            threading.Thread(target=self.read_stream, args=(stream, source), daemon=True).start()
        try:
            while True:
                if self.publish_deadline and time.monotonic() >= self.publish_deadline:
                    self.publish_result({'status': 'blocked', 'reason': 'github_publish_timeout',
                                         'next': 'Inspect remote branch before retry; request may have succeeded.'}, False)
                if self.switch_id and time.monotonic() >= self.switch_deadline:
                    self.fail_turn(self.switch_turn, 'deepseek_thread_start_timeout')
                    raise RoutingError('deepseek_thread_start_timeout')
                if self.catalog_id and time.monotonic() >= self.catalog_deadline:
                    if self.pending_turn:
                        self.fail_turn(self.pending_turn, 'model_catalog_timeout')
                    raise RoutingError('model_catalog_timeout')
                try:
                    source, line = self.events.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    if source == 'child':
                        raise RoutingError('app_server_exited')
                    return 0
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError()
                except (ValueError, UnicodeError) as exc:
                    raise RoutingError('invalid_protocol_json') from exc
                handler = self.handle_parent if source == 'parent' else self.handle_child
                if not handler(message):
                    return 1
        finally:
            self.stop_child()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog-timeout', type=float, default=30)
    parser.add_argument('--audit-log', type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.catalog_timeout <= 0:
        parser.error('--catalog-timeout must be positive')
    if args.audit_log:
        args.audit_log.parent.mkdir(parents=True, exist_ok=True)
    command = args.command or ['codex', 'app-server']
    if command[0] == '--':
        command = command[1:]
    bridge = Bridge(command, args.catalog_timeout, args.audit_log)
    def stop(_signum, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        if DEEPSEEK_KEY_FILE.is_file():
            key = DEEPSEEK_KEY_FILE.read_text(encoding='utf-8-sig').strip()
            if not re.fullmatch(r'sk-[A-Za-z0-9_-]+', key):
                raise RoutingError('invalid_deepseek_key_file')
            os.environ['DEEPSEEK_API_KEY'] = key
        return bridge.run()
    except KeyboardInterrupt:
        return 130
    except (OSError, RoutingError, KeyError, TypeError) as exc:
        # Never serialize an OS error, child output, prompt or credential.
        bridge.audit('adapter_failed', reason=str(exc) if isinstance(exc, RoutingError) else type(exc).__name__)
        return 1


if __name__ == '__main__':
    sys.exit(main())
