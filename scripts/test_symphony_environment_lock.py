import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import symphony_environment as environment


class EnvironmentLockTests(unittest.TestCase):
    def test_benchmark_excludes_app_output_but_keeps_dependency_dist(self):
        from verify_symphony_concurrency import copy_ignored
        root = Path('/fixture')
        self.assertEqual(copy_ignored(root, root / 'frontend', ['dist', 'src']), {'dist'})
        self.assertEqual(copy_ignored(root, root / 'frontend/node_modules/vite', ['dist', 'bin']), set())
        self.assertEqual(copy_ignored(root, root / 'backend/ruoyi-ar', ['target', 'src']), {'target'})

    def test_changed_or_missing_controller_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool = root / 'tool.py'
            tool.write_bytes(b'print(1)\r\n')
            lock = {'schemaVersion': 1, 'files': [{'source': 'tool.py', 'runtime': str(tool),
                                                 'sha256': environment.sha(tool)}], 'imageFiles': {}}
            tool.write_bytes(b'print(1)\n')
            self.assertEqual(environment.verify_files(lock, root), [])
            tool.write_bytes(b'print(2)\n')
            self.assertTrue(environment.verify_files(lock, root))
            tool.unlink()
            self.assertTrue(environment.verify_files(lock, root))

    def test_image_tag_drift_does_not_refresh_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = root / 'lock.json'
            lock.write_text(json.dumps({'schemaVersion': 1, 'files': [], 'image': 'fixture', 'imageId': 'old'}))
            original = lock.read_bytes()
            with patch.object(environment, 'command', return_value='new'):
                self.assertEqual(environment.verify_host(root, lock)['status'], 'blocked')
            self.assertEqual(lock.read_bytes(), original)

    def test_quick_skips_java_and_node_but_frontend_java_checks_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / 'lock.json'
            lock.write_text(json.dumps({'schemaVersion': 1, 'files': [], 'imageFiles': {},
                                        'tools': {k: k for k in environment.TOOLS}}))
            seen = []
            def command(args):
                seen.append(str(args[0]))
                if Path(args[0]).name == 'python':
                    return ''
                return next(k for k,v in environment.TOOLS.items() if v == args)
            with patch.object(environment, 'command', side_effect=command):
                self.assertEqual(environment.task_preflight(None, 'quick', [], lock)['status'], 'passed')
                self.assertNotIn('mvn', seen)
                self.assertNotIn('npm', seen)
                seen.clear()
                self.assertEqual(environment.task_preflight(None, 'frontend', ['ruoyi-ar'], lock)['status'], 'passed')
                self.assertIn('mvn', seen)
                self.assertIn('npm', seen)

    def test_missing_maven_blocks_java_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / 'lock.json'
            lock.write_text(json.dumps({'schemaVersion': 1, 'files': [], 'imageFiles': {},
                                        'tools': {k: k for k in environment.TOOLS}}))
            def command(args):
                if args[0] == 'mvn':
                    raise FileNotFoundError('Maven missing')
                if Path(args[0]).name == 'python':
                    return ''
                return next(k for k,v in environment.TOOLS.items() if v == args)
            with patch.object(environment, 'command', side_effect=command):
                result = environment.task_preflight(None, 'quick', ['ruoyi-ar'], lock)
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual([c['name'] for c in result['checks'] if c['status'] == 'blocked'], ['maven version/PATH'])

    def test_nested_native_mount_overrides_windows_parent(self):
        content = '1 0 0:1 / / rw - overlay overlay rw\n2 1 0:2 / /data rw - 9p host rw\n3 2 0:3 / /data/workspaces rw - ext4 disk rw\n'
        with patch.object(Path, 'read_text', return_value=content):
            self.assertTrue(environment.native_workspace(Path('/data/workspaces/GH-1')))
            self.assertFalse(environment.native_workspace(Path('/data/other')))


if __name__ == '__main__':
    unittest.main()
