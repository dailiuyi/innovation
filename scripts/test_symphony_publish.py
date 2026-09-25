import base64
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import symphony_codex_adapter as adapter
from symphony_publish import PublishError, blob_sha, publish, snapshot

HEAD = 'a' * 40
TREE = 'b' * 40
COMMIT = 'c' * 40
NEW_TREE = 'd' * 40


class Remote:
    def __init__(self, exists=True):
        self.head = HEAD if exists else None
        self.requests = []
        self.corrupt = False
        self.conflict = False

    def call(self, req):
        self.requests.append(req)
        method, path = req['method'], req['path']
        self.test_scope(path)
        body = req.get('body', {})
        if method == 'GET' and '/git/ref/' in path:
            if self.conflict and len(self.requests) > 2:
                self.head = 'e' * 40
            return {'status': 200, 'body': {'object': {'sha': self.head}}} if self.head else {'status': 404}
        if '/git/commits/' in path:
            value = {'tree': {'sha': TREE}}
        elif path.endswith('/git/blobs'):
            value = {'sha': '0' * 40 if self.corrupt else blob_sha(base64.b64decode(body['content']))}
        elif path.endswith('/git/trees'):
            value = {'sha': NEW_TREE}
        elif path.endswith('/git/commits'):
            value = {'sha': COMMIT, 'tree': {'sha': body['tree']}, 'parents': [{'sha': HEAD}]}
        elif '/git/refs' in path:
            if method == 'PATCH':
                assert body['force'] is False
            self.head = body['sha']
            value = {'object': {'sha': self.head}}
        else:
            raise AssertionError(req)
        return {'status': 200, 'body': value}

    @staticmethod
    def test_scope(path):
        assert path.startswith('/repos/dailiuyi/innovation-ar-resource-platform/')


def run(root, args, remote):
    job = publish(root, args)
    try:
        req = next(job)
        while True:
            req = job.send(remote.call(req))
    except StopIteration as result:
        return result.value


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'GH-9'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / '.gitignore').write_text('ignored/\n', encoding='utf-8')
        self.data = ('中文\r\n"quotes"\\\x00'.encode() * 6000)
        (self.root / 'file.bin').write_bytes(self.data)
        self.args = {'branch': 'codex/issue-9', 'expected_head': HEAD,
                     'paths': ['file.bin'], 'message': 'Publish exact bytes'}

    def test_large_binary_and_new_existing_branches(self):
        for exists in (True, False):
            remote = Remote(exists)
            result = run(self.root, self.args, remote)
            self.assertEqual(result['commit'], COMMIT)
            uploaded = next(r['body'] for r in remote.requests if r['path'].endswith('/git/blobs'))
            self.assertEqual(base64.b64decode(uploaded['content']), self.data)
            tree = next(r['body'] for r in remote.requests if r['path'].endswith('/git/trees'))
            self.assertEqual(tree['base_tree'], TREE)
            self.assertEqual(tree['tree'][0]['sha'], blob_sha(self.data))

    def test_corrupt_blob_and_concurrent_remote_stop_before_ref_write(self):
        for kind in ('corrupt', 'conflict'):
            remote = Remote()
            setattr(remote, kind, True)
            with self.assertRaises(PublishError):
                run(self.root, self.args, remote)
            self.assertFalse(any('/git/refs' in r['path'] for r in remote.requests))

    def test_stale_head_no_network_write(self):
        remote = Remote()
        remote.head = 'e' * 40
        with self.assertRaisesRegex(PublishError, 'head_changed'):
            run(self.root, self.args, remote)
        self.assertEqual(len(remote.requests), 1)

    def test_changed_local_file_stops_before_ref(self):
        remote = Remote()
        original = remote.call
        def mutate(req):
            result = original(req)
            if req['path'].endswith('/git/commits'):
                (self.root / 'file.bin').write_bytes(b'changed')
            return result
        remote.call = mutate
        with self.assertRaisesRegex(PublishError, 'workspace_changed'):
            run(self.root, self.args, remote)
        self.assertFalse(any('/git/refs' in r['path'] for r in remote.requests))

    def test_invalid_sensitive_ignored_and_large_paths(self):
        (self.root / 'ignored').mkdir()
        (self.root / 'ignored' / 'x').write_text('secret')
        (self.root / 'large').write_bytes(b'x' * (1024 * 1024 + 1))
        for name in ('../x', '/tmp/x', 'C:/x', 'a\\b', '.git/config', '.local/x', '.env', 'ignored/x', 'large'):
            with self.subTest(name=name), self.assertRaises(PublishError):
                snapshot(self.root, [name])

    def test_symlink_rejected(self):
        try:
            (self.root / 'link').symlink_to(self.root / 'file.bin')
        except OSError:
            self.skipTest('OS does not permit symlink creation')
        with self.assertRaisesRegex(PublishError, 'symlink'):
            snapshot(self.root, ['link'])

    def test_executable_mode_preserved(self):
        subprocess.run(['git', '-C', str(self.root), 'add', 'file.bin'], check=True)
        subprocess.run(['git', '-C', str(self.root), 'update-index', '--chmod=+x', 'file.bin'], check=True)
        self.assertEqual(snapshot(self.root, ['file.bin'])[0]['mode'], '100755')

    def test_invalid_branch_and_duplicates(self):
        for branch in ('main', 'codex/../main', 'codex/a.lock', 'codex/a//b'):
            with self.assertRaises(PublishError):
                run(self.root, dict(self.args, branch=branch), Remote())
        with self.assertRaisesRegex(PublishError, 'duplicate'):
            snapshot(self.root, ['file.bin', 'file.bin'])

    def test_bridge_transport_compact_reply_duplicate_hold_and_thread_mapping(self):
        bridge = adapter.Bridge([])
        bridge.issue = 'GH-9'
        bridge.thread_id = 'parent-thread'
        bridge.actual_thread_id = 'provider-thread'
        bridge.start_params = {'cwd': str(self.root)}
        bridge.child = SimpleNamespace(stdin=io.BytesIO())
        out = SimpleNamespace(buffer=io.BytesIO())
        remote = Remote()
        call = {'id': 73, 'method': 'item/tool/call', 'params': {
            'name': 'github_publish_files', 'threadId': 'provider-thread', 'arguments': self.args}}
        with patch.object(adapter, 'WORKSPACE_ROOT', self.root.parent), patch.object(adapter.sys, 'stdout', out):
            bridge.handle_child(call)
            while bridge.publish_job is not None:
                req = json.loads(out.buffer.getvalue().splitlines()[-1])
                self.assertEqual(req['params']['threadId'], 'parent-thread')
                result = remote.call(req['params']['arguments'])
                bridge.handle_parent({'id': req['id'], 'result': {
                    'contentItems': [{'type': 'inputText', 'text': json.dumps(result)}]}})
            done = json.loads(bridge.child.stdin.getvalue().splitlines()[-1])
            self.assertTrue(done['result']['success'])
            self.assertLess(len(json.dumps(done)), 1000)
            self.assertNotIn(base64.b64encode(self.data).decode(), json.dumps(done))
            bridge.handle_child(call)
            held = json.loads(bridge.child.stdin.getvalue().splitlines()[-1])
            self.assertIn('duplicate_publication_request_held', json.dumps(held))

    def test_bridge_rejects_untrusted_workspace_and_drops_late_replies(self):
        bridge = adapter.Bridge([])
        bridge.issue = 'GH-9'
        bridge.start_params = {'cwd': str(self.root)}
        bridge.child = SimpleNamespace(stdin=io.BytesIO())
        bridge.handle_child({'id': 1, 'method': 'item/tool/call', 'params': {
            'name': 'github_publish_files', 'arguments': self.args}})
        self.assertIn(b'untrusted_workspace_root', bridge.child.stdin.getvalue())
        size = bridge.child.stdin.tell()
        bridge.handle_parent({'id': 'symphony-publish-expired', 'result': {}})
        self.assertEqual(size, bridge.child.stdin.tell())

    def test_manual_blob_fallback_rejected(self):
        bridge = adapter.Bridge([])
        bridge.child = SimpleNamespace(stdin=io.BytesIO())
        for path in ('/repos/dailiuyi/innovation-ar-resource-platform/git/blobs', '/repos/dailiuyi/innovation-ar-resource-platform/contents/x'):
            bridge.handle_child({'id': 11, 'method': 'item/tool/call', 'params': {
                'name': 'github_api', 'arguments': {'method': 'POST', 'path': path, 'body': {'content': 'large'}}}})
        replies = bridge.child.stdin.getvalue().splitlines()
        self.assertEqual(len(replies), 2)
        self.assertTrue(all(not json.loads(r)['result']['success'] for r in replies))

    def test_api_failure_is_not_retried(self):
        remote = Remote()
        calls = []
        def denied(req):
            calls.append(req)
            return {'status': 403, 'body': {}}
        remote.call = denied
        with self.assertRaisesRegex(PublishError, '403'):
            run(self.root, self.args, remote)
        self.assertEqual(len(calls), 1)




class GitScanTimeoutTests(unittest.TestCase):
    def test_slow_workspace_scans_have_a_bounded_separate_budget(self):
        from symphony_publish import git
        with patch('symphony_publish.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=b'')) as invoke:
            for operation in ('diff', 'ls-files'):
                git(Path('.'), operation, '--name-only')
                self.assertEqual(invoke.call_args.kwargs['timeout'], 120)
            git(Path('.'), 'rev-parse', 'HEAD')
            self.assertEqual(invoke.call_args.kwargs['timeout'], 15)


if __name__ == '__main__':
    unittest.main()
