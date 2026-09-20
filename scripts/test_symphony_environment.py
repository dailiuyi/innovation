"""Image acceptance: run in the validation image with --network none, no auth.

Mount this directory at /tests and a disposable cache root at /data/cache.
Use the project's Symphony seccomp profile for the Codex sandbox test.
"""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from prepare_symphony_workspace import BASE, prepare


@unittest.skipUnless(BASE.is_dir(), 'Requires the built Symphony validation image')
class ImageEnvironmentTests(unittest.TestCase):
    def test_java_and_maven(self):
        java = subprocess.run(['java', '-version'], capture_output=True, text=True, check=True)
        self.assertIn('version "21.', java.stderr + java.stdout)
        maven = subprocess.check_output(['mvn', '--version'], text=True)
        self.assertIn('Apache Maven 3.9.', maven)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='symphony-env-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in ('pip', 'npm'):
            (Path('/data/cache') / name).mkdir(parents=True, exist_ok=True)
        self.old_no_index = os.environ.get('PIP_NO_INDEX')
        os.environ['PIP_NO_INDEX'] = '1'
        self.addCleanup(self.restore_environment)

    def restore_environment(self):
        if self.old_no_index is None:
            os.environ.pop('PIP_NO_INDEX', None)
        else:
            os.environ['PIP_NO_INDEX'] = self.old_no_index

    def workspace(self, name):
        workspace = self.root / name
        (workspace / 'scripts').mkdir(parents=True)
        # Exercise Windows build input versus Linux checkout line endings too.
        (workspace / 'scripts/requirements-review.txt').write_bytes(
            (BASE / 'requirements.txt').read_text().replace('\n', '\r\n').encode())
        return workspace

    def prepare(self, workspace):
        with redirect_stdout(io.StringIO()):
            return prepare(workspace)

    def run_python(self, workspace, code):
        return subprocess.check_output([str(workspace / '.local/venv/bin/python'), '-c', code], text=True).strip()

    def test_offline_initialization_and_readonly_shared_packages(self):
        first, second = self.workspace('a'), self.workspace('b')
        timings = []
        for workspace in (first, second):
            result = self.prepare(workspace)
            self.assertEqual(result['mode'], 'image')
            timings.append(result['seconds'])
            location = self.run_python(workspace, 'import yaml; print(yaml.__file__)')
            self.assertTrue(location.startswith(str(BASE)))
            self.assertFalse(os.access(Path(location), os.W_OK))
        self.assertNotEqual(self.run_python(first, 'import sys; print(sys.prefix)'),
                            self.run_python(second, 'import sys; print(sys.prefix)'))
        self.assertEqual(self.prepare(first)['mode'], 'image')
        print(json.dumps({'offlineInitSeconds': timings}))

    def test_changed_requirements_install_only_in_task(self):
        first, second = self.workspace('a'), self.workspace('b')
        wheels = self.root / 'wheels'
        wheels.mkdir()
        name = 'symphony_cache_fixture'
        info = name + '-1.0.dist-info'
        files = {name + '.py': 'VALUE = 42\n',
                 info + '/METADATA': 'Metadata-Version: 2.1\nName: symphony-cache-fixture\nVersion: 1.0\n',
                 info + '/WHEEL': 'Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
        record = info + '/RECORD'
        files[record] = ''.join(path + ',,\n' for path in [*files, record])
        wheel = wheels / (name + '-1.0-py3-none-any.whl')
        with zipfile.ZipFile(wheel, 'w') as archive:
            for path, content in files.items():
                archive.writestr(path, content)
        requirements = first / 'scripts/requirements-review.txt'
        requirements.write_text(requirements.read_text() + '\n' + str(wheel) + '\n')
        self.assertEqual(self.prepare(first)['mode'], 'task-overlay')
        self.assertEqual(self.prepare(second)['mode'], 'image')
        self.assertEqual(self.run_python(first, 'import symphony_cache_fixture; print(symphony_cache_fixture.VALUE)'), '42')
        self.assertEqual(self.run_python(second, 'import importlib.util; print(importlib.util.find_spec("symphony_cache_fixture"))'), 'None')
        self.assertFalse(any(BASE.rglob(name + '.py')))

    def test_shared_cache_locations(self):
        workspace = self.workspace('cache')
        self.prepare(workspace)
        pip_cache = subprocess.check_output([str(workspace / '.local/venv/bin/python'), '-m', 'pip', 'cache', 'dir'], text=True).strip()
        npm_cache = subprocess.check_output(['npm', 'config', 'get', 'cache'], text=True).strip()
        self.assertEqual(pip_cache, '/data/cache/pip')
        self.assertEqual(npm_cache, '/data/cache/npm')
        for directory in (pip_cache, npm_cache):
            marker = Path(directory) / 'image-test-marker'
            marker.write_text('shared')
            self.assertEqual(marker.read_text(), 'shared')
            marker.unlink()

    def test_sandbox_cache_access_and_other_workspace_denied(self):
        # Outside /tmp: Codex intentionally grants temporary-directory writes.
        workspace = Path('/data/test-workspaces/a')
        sibling = Path('/data/test-workspaces/b')
        workspace.mkdir(parents=True, exist_ok=True)
        sibling.mkdir(parents=True, exist_ok=True)
        code = '''
import errno
from pathlib import Path
for p in ['local-marker', '/data/cache/pip/sandbox-marker', '/data/cache/npm/sandbox-marker']:
    Path(p).write_text('ok')
try:
    Path('/data/test-workspaces/b/forbidden-marker').write_text('bad')
except OSError as error:
    assert error.errno in (errno.EACCES, errno.EPERM, errno.EROFS), error
    print('sandbox-boundaries-ok')
else:
    raise AssertionError('sibling workspace unexpectedly writable')
'''
        result = subprocess.run(['codex', 'sandbox', '-P', 'cache-test',
                                 '-c', 'permissions.cache-test={extends=":workspace",filesystem={"/data/cache/pip"="write","/data/cache/npm"="write"}}',
                                 '-C', str(workspace), '--', 'python3', '-c', code],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('sandbox-boundaries-ok', result.stdout)


if __name__ == '__main__':
    unittest.main()
