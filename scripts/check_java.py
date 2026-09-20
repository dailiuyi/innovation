"""Run selected Java module tests, rejecting zero-test or skipped-test delivery."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def test_counts(files):
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    for file in files:
        suite = ET.parse(file).getroot()
        for key in counts:
            counts[key] += int(suite.get(key, 0))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', required=True, help='Affected reactor module, e.g. ruoyi-framework')
    parser.add_argument('--tests', help='Optional Surefire test class selector')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'ruoyi-[a-z]+', args.module) or not (ROOT / 'backend' / args.module / 'pom.xml').is_file():
        parser.error('Unknown module')
    evidence = ROOT / '.local/java-check' / uuid.uuid4().hex[:12]
    evidence.mkdir(parents=True)
    env = dict(os.environ)
    java = next((ROOT / '.local/java21').glob('jdk*/bin/java.exe'), None)
    if java:
        env['JAVA_HOME'] = str(java.parent.parent)
        env['PATH'] = str(java.parent) + os.pathsep + env.get('PATH', '')
    mvn = shutil.which('mvn.cmd' if os.name == 'nt' else 'mvn')
    if not mvn:
        raise SystemExit('Maven missing: provision the Java-capable execution image')
    command = [mvn, '-f', str(ROOT / 'backend/pom.xml'), '-pl', args.module, '-am',
               '-Dmaven.repo.local=' + str(ROOT / '.local/m2'), 'clean', 'test', '-B', '-ntp']
    if args.offline:
        command.append('-o')
    if args.tests:
        command += ['-Dtest=' + args.tests, '-Dsurefire.failIfNoSpecifiedTests=false']
    before = time.time()
    with (evidence / 'maven.log').open('wb') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=log)
    files = [p for p in (ROOT / 'backend').glob('*/target/surefire-reports/TEST-*.xml')
             if p.stat().st_mtime >= before]
    counts = test_counts(files)
    passed = result.returncode == 0 and counts['tests'] > 0 and not any(counts[k] for k in ('failures', 'errors', 'skipped'))
    report = {'status': 'passed' if passed else 'failed', 'module': args.module, 'command': command,
              'exitCode': result.returncode, **counts, 'seconds': round(time.time() - before, 2),
              'scope': 'Java tests only; HTTP/database/session revocation not established'}
    (evidence / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    print('Evidence: ' + str(evidence))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
