import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from migrate_symphony_workspaces import migrate


class MigrationTests(unittest.TestCase):
    def test_copy_preserves_source_and_verifies_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, dst = root / 'old', root / 'new'
            (src / 'GH-1/.local').mkdir(parents=True)
            dst.mkdir()
            payload = src / 'GH-1/.local/data.bin'
            payload.write_bytes(bytes(range(256)) * 9)
            result = migrate(src, dst)
            self.assertTrue(result['verified'])
            self.assertEqual(payload.read_bytes(), (dst / 'GH-1/.local/data.bin').read_bytes())
            self.assertTrue((dst / '.migration-verified.json').is_file())
            with self.assertRaises(ValueError):
                migrate(src, dst)

    def test_overlap_and_file_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / 'child'
            child.mkdir()
            with self.assertRaises(ValueError):
                migrate(root, child)
            file = root / 'file'
            file.write_text('x')
            with self.assertRaises(ValueError):
                migrate(file, child)

    def test_unreadable_directory_cannot_be_marked_verified(self):
        def denied_walk(root, *, followlinks, onerror):
            onerror(PermissionError('Unreadable source directory'))
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'old', Path(tmp) / 'new'
            src.mkdir()
            dst.mkdir()
            with patch('migrate_symphony_workspaces.os.walk', side_effect=denied_walk):
                with self.assertRaises(PermissionError):
                    migrate(src, dst)
            self.assertFalse((dst / '.migration-verified.json').exists())

    @unittest.skipUnless(os.name == 'posix', 'Migration runs inside Linux')
    def test_executable_mode_and_symbolic_links_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'old', Path(tmp) / 'new'
            (src / 'GH-1/bin').mkdir(parents=True)
            dst.mkdir()
            executable = src / 'GH-1/bin/tool'
            executable.write_bytes(b'#!/bin/sh\nexit 0\n')
            executable.chmod(0o755)
            (src / 'GH-1/command').symlink_to('bin/tool')
            (src / 'GH-1/linked-dir').symlink_to('bin', target_is_directory=True)
            migrate(src, dst)
            self.assertEqual((dst / 'GH-1/bin/tool').stat().st_mode & 0o777, 0o755)
            self.assertEqual(os.readlink(dst / 'GH-1/command'), 'bin/tool')
            self.assertTrue((dst / 'GH-1/linked-dir').is_symlink())
            self.assertEqual((dst / 'GH-1/command').read_bytes(), executable.read_bytes())


if __name__ == '__main__':
    unittest.main()
