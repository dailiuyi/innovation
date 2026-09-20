"""Lifecycle regressions against real Git trees and a simulated tracker."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from symphony_task import Task, delivery, inspect_uncertain_delivery, lock, save, validate_plan
from symphony_publish import blob_sha


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'GH-9'
        self.root.mkdir()
        self.control = self.base / 'control'
        self.plan = {'title': '调整场景布局', 'profile': 'quick', 'allowedPaths': ['sample.txt'],
                     'javaModules': [], 'hostSuites': ['scene-ui'], 'acceptance': '四个按钮完整显示'}
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        (self.root / 'sample.txt').write_text('original', encoding='utf-8')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        save(self.control / 'GH-9/plan.json', self.plan)
        self.task = Task(self.control, 'GH-9', self.root)
        self.assertTrue(self.task.begin())
        self.edit('changed')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE).decode().strip()

    def edit(self, content):
        (self.root / 'sample.txt').write_text(content, encoding='utf-8')

    def test_one_repair_then_stop_across_reload(self):
        self.assertTrue(self.task.start_check())
        self.assertEqual(self.task.finish_check({'status': 'failed'}), 'repair')
        self.edit('fixed once')
        self.task = Task(self.control, 'GH-9', self.root)
        self.assertTrue(self.task.start_check())
        self.assertEqual(self.task.finish_check({'status': 'failed'}), 'blocked')
        resumed = Task(self.control, 'GH-9', self.root)
        self.assertFalse(resumed.begin())
        self.assertEqual(len(resumed.state['checks']), 2)

    def test_unchanged_failure_not_executed_twice(self):
        self.task.start_check()
        self.task.finish_check({'status': 'failed'})
        self.assertFalse(self.task.start_check())
        self.assertEqual(self.task.state['reason'], 'unchanged_failed_submission')
        self.assertEqual(len(self.task.state['checks']), 1)

    def test_environment_or_interrupted_process_stops_without_repair(self):
        self.task.start_check()
        crashed = Task(self.control, 'GH-9', self.root)
        self.assertFalse(crashed.begin())
        self.assertEqual(crashed.state['status'], 'blocked')
        self.task.finish_check({'status': 'blocked', 'reason': 'missing_browser'})
        self.assertEqual(self.task.state['status'], 'blocked')

    def test_source_changed_during_checks_never_passes(self):
        self.task.start_check()
        self.edit('concurrent change')
        self.task.finish_check({'status': 'passed'})
        self.assertEqual(self.task.state['status'], 'blocked')

    def test_out_of_scope_and_unplanned_backend_fail_before_checks(self):
        (self.root / 'other.txt').write_text('unrelated')
        self.assertFalse(self.task.start_check())
        self.assertEqual(self.task.state['reason'], 'empty_or_out_of_scope_changes')

    def test_lock_prevents_second_owner(self):
        with lock(self.task.home):
            with self.assertRaises(OSError):
                with lock(self.task.home):
                    self.fail('second owner entered')

    def tracker(self, operation, fail_labels=False, existing=False):
        requests, head = [], None
        tree, commit = 'b' * 40, 'c' * 40
        try:
            request = next(operation)
            while True:
                requests.append(request)
                method, path = request['method'], request['path']
                body = request.get('body', {})
                result = {'status': 200, 'body': {}}
                if '/git/ref/heads/' in path:
                    result = {'status': 200, 'body': {'object': {'sha': head}}} if head else {'status': 404, 'body': {}}
                elif '/git/commits/' in path:
                    result['body'] = {'tree': {'sha': 'a' * 40}}
                elif path.endswith('/git/blobs'):
                    import base64
                    result['body'] = {'sha': blob_sha(base64.b64decode(body['content']))}
                elif path.endswith('/git/trees'):
                    result['body'] = {'sha': tree}
                elif path.endswith('/git/commits'):
                    result['body'] = {'sha': commit, 'tree': {'sha': tree}, 'parents': [{'sha': self.task.state['baseCommit']}]}
                elif path.endswith('/git/refs'):
                    head = body['sha']
                elif '/pulls?' in path:
                    result['body'] = [{'number': 10, 'draft': True}] if existing else []
                elif '/pulls' in path:
                    result['body'] = {'number': 10, 'html_url': 'https://example.invalid/pr/10'}
                elif '/labels' in path and fail_labels:
                    result['status'] = 403
                request = operation.send(result)
        except StopIteration:
            return requests

    def test_large_chinese_file_and_failed_labels_still_terminal(self):
        self.edit('中文文件内容\n' * 20000)
        self.task.start_check()
        self.task.finish_check({'status': 'passed'})
        requests = self.tracker(delivery(self.task), fail_labels=True)
        self.assertEqual(self.task.state['delivery']['status'], 'draft_created')
        self.assertFalse(self.task.state['labelsUpdated'])
        self.assertFalse(Task(self.control, 'GH-9', self.root).begin())
        self.assertEqual(len([r for r in requests if r['method'] == 'POST' and r['path'].endswith('/pulls')]), 1)
        self.assertTrue(Path(self.task.state['evidence'], 'changes.patch').is_file())

    def test_existing_draft_updated_and_failure_visibly_unaccepted(self):
        self.task.start_check()
        self.task.finish_check({'status': 'blocked', 'reason': 'timeout'})
        requests = self.tracker(delivery(self.task), existing=True)
        updates = [r for r in requests if '/pulls/10' in r['path']]
        self.assertEqual(len(updates), 1)
        self.assertIn('未通过／待验收', updates[0]['body']['body'])
        self.assertFalse(any(r['method'] == 'POST' and r['path'].endswith('/pulls') for r in requests))

    def test_remote_head_change_cannot_be_overwritten(self):
        self.task.update(status='blocked', reason='environment')
        operation = delivery(self.task)
        request = next(operation)
        self.assertIn('/git/ref/', request['path'])
        request = operation.send({'status': 200, 'body': {'object': {'sha': 'f' * 40}}})
        self.assertIn('/labels', request['path'])
        self.assertEqual(self.task.state['delivery']['status'], 'blocked')
        self.assertNotIn('publishedCommit', self.task.state)

    def test_plan_cannot_request_shell_commands_or_runtime_scope(self):
        for extra in [{'command': 'curl ...'}, {'allowedPaths': ['../secret']}, {'profile': 'ingestion'}]:
            with self.assertRaises(ValueError):
                validate_plan({**self.plan, **extra})

    def test_uncertain_delivery_only_reads_back_and_stays_stopped(self):
        operation = inspect_uncertain_delivery(self.task, 'timeout')
        first = next(operation)
        self.assertEqual(first['method'], 'GET')
        second = operation.send({'status': 200, 'body': {'object': {'sha': 'e' * 40}}})
        self.assertEqual(second['method'], 'GET')
        with self.assertRaises(StopIteration):
            operation.send({'status': 200, 'body': [{'number': 10, 'draft': True, 'html_url': 'synthetic'}]})
        self.assertEqual(self.task.state['status'], 'blocked')
        self.assertEqual(self.task.state['delivery']['observations']['branch']['sha'], 'e' * 40)

    def test_boot_rejects_modified_module_before_release_start(self):
        import hashlib
        from symphony_entrypoint import REQUIRED, verified_files
        modules = {}
        for name in REQUIRED:
            (self.base / name).write_bytes(b'verified fixture')
            modules[name] = hashlib.sha256(b'verified fixture').hexdigest()
        save(self.base / 'manifest.json', {'verifiedModules': modules})
        self.assertEqual(set(verified_files(self.base)), REQUIRED)
        (self.base / next(iter(REQUIRED))).write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'fingerprint'):
            verified_files(self.base)

    def test_boot_rejects_arbitrary_preserved_module_paths(self):
        from symphony_entrypoint import REQUIRED, verified_files
        save(self.base / 'manifest.json', {'verifiedModules': dict.fromkeys(REQUIRED, 'synthetic'),
                                          'preservedModules': {'../unexpected': 'synthetic'}})
        with self.assertRaisesRegex(RuntimeError, 'Unexpected'):
            verified_files(self.base)


if __name__ == '__main__':
    unittest.main()
