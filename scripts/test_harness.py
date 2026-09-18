"""Regression checks for evidence integrity and safe failure behavior."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import harness


class HarnessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def step(self, code, evidence=None, timeout=10):
        return harness.Step('sample', [sys.executable, '-c', code], self.root, timeout, evidence)

    def test_nonzero_exit_stops_later_steps_and_keeps_log(self):
        marker = self.root / 'should-not-exist'
        steps = [self.step("print('synthetic failure'); raise SystemExit(7)"),
                 harness.Step('later', [sys.executable, '-c', f'from pathlib import Path; Path({str(marker)!r}).touch()'], self.root)]
        results = harness.execute_steps(steps, self.root, os.environ.copy())
        self.assertEqual([r['status'] for r in results], ['failed', 'skipped'])
        self.assertEqual(results[0]['exitCode'], 7)
        self.assertIn('synthetic failure', (self.root / 'sample.log').read_text())
        self.assertFalse(marker.exists())

    def test_success_without_expected_evidence_is_failure(self):
        result = harness.run_step(self.step('pass', self.root / 'missing.json'), self.root, os.environ.copy())
        self.assertEqual(result['status'], 'failed')

    def test_failed_or_empty_evidence_cannot_pass_on_zero_exit(self):
        evidence = self.root / 'evidence.json'
        for report in ({'passed': False, 'checks': [{'passed': True}]},
                       {'passed': True, 'checks': [{'passed': False}]}, {'passed': True, 'checks': []},
                       [], 123, {'passed': True, 'checks': ['not a check']}):
            with self.subTest(report=report):
                evidence.write_text(json.dumps(report))
                result = harness.run_step(self.step('pass', evidence), self.root, os.environ.copy())
                self.assertEqual(result['status'], 'failed')

    def test_valid_evidence_passes(self):
        evidence = self.root / 'evidence.json'
        evidence.write_text(json.dumps({'passed': True, 'checks': [{'passed': True}]}))
        result = harness.run_step(self.step('pass', evidence), self.root, os.environ.copy())
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['checks'], 1)

    def test_missing_executable_is_blocked(self):
        step = harness.Step('missing', [self.root / 'no-such-executable'], self.root)
        self.assertEqual(harness.run_step(step, self.root, os.environ.copy())['status'], 'blocked')

    def test_timeout_is_blocked_and_process_stops(self):
        marker = self.root / 'should-not-exist'
        code = f'import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).touch()'
        result = harness.run_step(self.step(code, timeout=0.1), self.root, os.environ.copy())
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(marker.exists())

    def test_skipped_and_empty_results_never_mean_success(self):
        self.assertEqual(harness.overall_status([]), 'blocked')
        self.assertEqual(harness.overall_status([{'status': 'passed'}, {'status': 'skipped'}]), 'blocked')

    def test_fingerprint_captures_dirty_untracked_and_deleted_content(self):
        def git(*args):
            subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)
        git('init', '-q')
        tracked = self.root / 'source.txt'
        tracked.write_text('original')
        (self.root / '.gitignore').write_text('.local/\n')
        git('add', '.')
        git('-c', 'user.name=Harness Test', '-c', 'user.email=harness@example.invalid',
            '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=' + str(self.root / 'no-hooks'), 'commit', '-qm', 'fixture')
        original = harness.source_identity(self.root)
        tracked.write_text('modified')
        dirty = harness.source_identity(self.root)
        self.assertEqual(original['head'], dirty['head'])
        self.assertNotEqual(original['sourceSha256'], dirty['sourceSha256'])
        (self.root / 'new.txt').write_text('untracked')
        untracked = harness.source_identity(self.root)
        self.assertNotEqual(dirty['sourceSha256'], untracked['sourceSha256'])
        (self.root / '.local').mkdir()
        (self.root / '.local/report.json').write_text('ignored')
        self.assertEqual(untracked, harness.source_identity(self.root))
        tracked.unlink()
        self.assertNotEqual(untracked['sourceSha256'], harness.source_identity(self.root)['sourceSha256'])

    def test_contract_drift_is_detected_without_rewriting_contract(self):
        # A real verifier against a disposable fixture, not a mocked check result.
        (self.root / 'scripts').mkdir()
        for name in ('verify_design.py', 'generate_contracts.py'):
            shutil.copy2(harness.ROOT / 'scripts' / name, self.root / 'scripts' / name)
        shutil.copytree(harness.ROOT / 'contracts', self.root / 'contracts')
        contract = self.root / 'contracts/openapi.yaml'
        import yaml
        spec = yaml.safe_load(contract.read_text(encoding='utf-8'))
        spec['info']['title'] = 'deliberate drift fixture'
        contract.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding='utf-8')
        before = contract.read_bytes()
        result = subprocess.run([sys.executable, str(self.root / 'scripts/verify_design.py'), '--report-dir', str(self.root / 'reports')],
                                capture_output=True, text=True, encoding='utf-8', env=harness.environment(), timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('OpenAPI matches authoring source', result.stderr)
        self.assertEqual(contract.read_bytes(), before)
        self.assertFalse((self.root / 'reports/validation-contracts.json').exists())


if __name__ == '__main__':
    unittest.main()
