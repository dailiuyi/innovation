"""One entrypoint for unattended checks; emits a durable, bounded handoff decision."""
import argparse
import json
from pathlib import Path
import subprocess

import frontend_control
import harness


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--profile', choices=('quick', 'frontend'), default='quick')
    parser.add_argument('--retry-reason')
    args = parser.parse_args(argv)
    if args.retry_reason is not None and not args.retry_reason.strip():
        parser.error('--retry-reason must describe a repaired condition')
    root = args.root.resolve()
    base = frontend_control.safe_paths(root)
    decision = {'profile': args.profile, 'status': 'blocked', 'decision': 'environment_blocked',
                'nextAction': 'Inspect the evidence and record the blocker; do not repeat unchanged commands.',
                'scope': 'Container checks only. Issue-specific, host and independent acceptance remain separate.'}
    try:
        # A separate OS lock prevents concurrent agent_check calls from repeating checks.
        agent_base = root / '.local/agent-check'
        agent_base.mkdir(parents=True, exist_ok=True)
        with frontend_control.locked(agent_base):
            before = set((root / '.local/harness').glob('*/report.json'))
            command = ['check', '--profile', args.profile, '--root', str(root)]
            if args.retry_reason:
                command += ['--retry-reason', args.retry_reason]
            code = harness.main(command)
            reports = set((root / '.local/harness').glob('*/report.json')) - before
            if len(reports) != 1:
                raise frontend_control.Blocked('Cannot identify this check report unambiguously')
            report_path = reports.pop()
            report = frontend_control.read_json(report_path)
            decision.update(status=report['status'], report=str(report_path),
                            source=report.get('sourceAfter'), sourceUnchanged=report.get('sourceUnchanged'))
            if code == 0:
                decision.update(decision='container_checks_passed',
                                nextAction='If issue-specific checks are complete or explicitly host-pending, create/update the draft PR now. Do not repeat installation/build.')
            elif code == 1:
                decision.update(decision='code_check_failed', nextAction='Fix the reported failure, then run this entrypoint again.')
    except (frontend_control.Blocked, OSError, subprocess.SubprocessError) as exc:
        decision['reason'] = str(exc)
    frontend_control.save_json(base / 'handoff.json', decision)
    print(json.dumps(decision, ensure_ascii=False, indent=2), flush=True)
    return {'passed': 0, 'failed': 1, 'blocked': 2}[decision['status']]


if __name__ == '__main__':
    raise SystemExit(main())
