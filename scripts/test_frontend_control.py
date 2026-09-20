"""Exercise cache invalidation, interrupted work, concurrent callers and evidence."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import frontend_control as control


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.front = self.root / 'frontend'
        self.front.mkdir()
        for name, text in [('package.json', '{}'), ('package-lock.json', '{}'),
                           ('app.vue', 'initial'), ('.env.production', 'VITE_TITLE=sample')]:
            (self.front / name).write_text(text)
        self.calls = []
        self.build_status = 'passed'
        self.context = {'node': 'test-node', 'npm': 'test-npm', 'environment': 'test-env'}

    def runner(self, command, root, directory, env, timeout, name):
        self.calls.append(name)
        log = directory / (name + '.log')
        log.write_text('synthetic ' + name)
        if name == 'install':
            vite = self.front / 'node_modules/vite/bin/vite.js'
            vite.parent.mkdir(parents=True, exist_ok=True)
            vite.write_text('synthetic vite')
            return {'status': 'passed', 'log': str(log), 'exitCode': 0}
        out = self.front / 'dist'
        out.mkdir(exist_ok=True)
        (out / 'index.html').write_text((self.front / 'app.vue').read_text())
        return {'status': self.build_status, 'log': str(log),
                'exitCode': 0 if self.build_status == 'passed' else None}

    def run_control(self, **kwargs):
        return control.operate(self.root, env={}, context=self.context, run=self.runner, **kwargs)

    def test_second_call_reuses_install_and_build_with_evidence(self):
        first = self.run_control()
        second = self.run_control()
        self.assertEqual(self.calls, ['install', 'build'])
        self.assertEqual(second['mode'], 'reused')
        self.assertEqual(second['dependencies'], 'reused')
        self.assertEqual(second['log'], first['log'])

    def test_docs_change_keeps_build_but_frontend_change_invalidates(self):
        self.run_control()
        (self.root / 'README.md').write_text('new docs')
        self.assertEqual(self.run_control()['mode'], 'reused')
        (self.front / 'app.vue').write_text('changed')
        self.assertEqual(self.run_control()['mode'], 'executed')
        self.assertEqual(self.calls, ['install', 'build', 'build'])

    def test_lockfile_or_runtime_change_reinstalls(self):
        self.run_control()
        (self.front / 'package-lock.json').write_text('{"lockfileVersion":3}')
        self.run_control()
        self.context['node'] = 'new-node'
        self.run_control()
        self.assertEqual(self.calls, ['install', 'build'] * 3)

    def test_ignored_env_and_added_deleted_files_invalidate(self):
        self.run_control()
        (self.front / '.env.production').write_text('VITE_TITLE=changed')
        self.run_control()
        (self.front / 'extra.js').write_text('new')
        self.run_control()
        (self.front / 'extra.js').unlink()
        self.run_control()
        self.assertEqual(self.calls.count('install'), 1)
        self.assertEqual(self.calls.count('build'), 4)

    def test_dist_tampering_and_missing_outputs_rebuild(self):
        self.run_control()
        (self.front / 'dist/index.html').write_text('tampered')
        self.assertEqual(self.run_control()['mode'], 'executed')
        (self.front / 'dist/index.html').unlink()
        self.assertEqual(self.run_control()['mode'], 'executed')

    def test_dependency_damage_is_detected_not_reused(self):
        self.run_control()
        (self.front / 'node_modules/vite/bin/vite.js').write_text('corrupted')
        self.run_control()
        self.assertEqual(self.calls.count('install'), 2)

    def test_vite_cache_does_not_invalidate_packages(self):
        self.run_control()
        cache = self.front / 'node_modules/.vite'
        cache.mkdir()
        (cache / 'temporary').write_text('dev-only')
        self.assertEqual(self.run_control()['mode'], 'reused')

    def test_timeout_holds_same_inputs_until_explicit_repair(self):
        self.build_status = 'blocked'
        self.run_control()
        held = self.run_control()
        self.assertEqual(held['mode'], 'held')
        self.assertEqual(held['status'], 'blocked')
        self.assertEqual(self.calls, ['install', 'build'])
        self.build_status = 'passed'
        self.assertEqual(self.run_control(retry_reason='repaired environment')['status'], 'passed')
        self.assertEqual(self.calls, ['install', 'build', 'build'])

    def test_interrupted_build_not_automatically_retried(self):
        self.run_control()
        path = control.safe_paths(self.root) / 'build.json'
        state = control.read_json(path)
        state['status'] = 'running'
        control.save_json(path, state)
        self.assertEqual(self.run_control()['mode'], 'held')
        self.assertEqual(self.calls, ['install', 'build'])

    def test_changed_source_allows_new_attempt_after_failure(self):
        self.build_status = 'failed'
        self.run_control()
        self.assertEqual(self.run_control()['status'], 'failed')
        (self.front / 'app.vue').write_text('fixed')
        self.build_status = 'passed'
        self.assertEqual(self.run_control()['status'], 'passed')

    def test_source_change_during_build_cannot_pass(self):
        original = self.runner
        def changed(*args):
            result = original(*args)
            if args[-1] == 'build':
                (self.front / 'app.vue').write_text('changed during build')
            return result
        result = control.operate(self.root, env={}, context=self.context, run=changed)
        self.assertEqual(result['status'], 'blocked')

    def test_interrupted_install_holds_without_second_install(self):
        self.run_control(action='deps')
        path = control.safe_paths(self.root) / 'install.json'
        state = control.read_json(path)
        state['status'] = 'running'
        control.save_json(path, state)
        with self.assertRaises(control.Blocked):
            self.run_control(action='deps')
        self.assertEqual(self.calls, ['install'])

    def test_concurrent_operation_is_blocked_and_lock_releases(self):
        base = control.safe_paths(self.root)
        with control.locked(base):
            with self.assertRaises(control.Blocked):
                self.run_control()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.run_control()['status'], 'passed')

    def test_corrupt_receipt_fails_closed(self):
        self.run_control()
        (control.safe_paths(self.root) / 'build.json').write_text('invalid json')
        self.assertEqual(self.run_control()['mode'], 'executed')

    def test_missing_log_prevents_build_reuse(self):
        result = self.run_control()
        Path(result['log']).unlink()
        self.assertEqual(self.run_control()['mode'], 'executed')

    def test_warm_build_scans_dependencies_once_before_and_once_after(self):
        self.run_control()
        (self.front / 'app.vue').write_text('new build')
        with patch.object(control, 'package_tree', wraps=control.package_tree) as scan:
            self.assertEqual(self.run_control()['status'], 'passed')
            self.assertEqual(scan.call_count, 2)

    def test_dependency_change_during_build_is_still_blocked(self):
        self.run_control()
        (self.front / 'app.vue').write_text('new build')
        original = self.runner
        def changed(*args):
            result = original(*args)
            if args[-1] == 'build':
                (self.front / 'node_modules/vite/bin/vite.js').write_text('mutated')
            return result
        result = control.operate(self.root, env={}, context=self.context, run=changed)
        self.assertEqual(result['status'], 'blocked')

    def test_agent_entrypoint_defers_dependency_work_and_forwards_retry(self):
        import agent_check
        import harness
        def check(command):
            self.assertIn('--retry-reason', command)
            self.assertEqual(command[-1], 'environment repaired')
            evidence = self.root / '.local/harness/synthetic'
            evidence.mkdir(parents=True)
            (evidence / 'report.json').write_text(json.dumps({
                'status': 'passed', 'sourceAfter': {}, 'sourceUnchanged': True}))
            return 0
        with patch.object(harness, 'main', side_effect=check), patch.object(control, 'operate') as operation:
            self.assertEqual(agent_check.main(['--root', str(self.root), '--profile', 'frontend',
                                              '--retry-reason', 'environment repaired']), 0)
            operation.assert_not_called()

    def test_cold_frontend_prerequisites_defer_install_to_controller(self):
        import harness
        checks = harness.prerequisites('frontend', self.root)
        self.assertNotIn('frontend dependencies', [item['name'] for item in checks])


if __name__ == '__main__':
    unittest.main()
