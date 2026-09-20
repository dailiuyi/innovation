"""Record a same-machine ZIP write comparison for the bulk-write fix in `LocalZipExportStore`.

Host-run evidence tool: no harness profile executes it. It runs `ZipWriteBenchmarkTest` in the `ruoyi-ar`
module once per variant and writes `<report-dir>/zip-write-benchmark.json` beside the Maven log.

    python scripts/benchmark_zip_write.py --sample-mib 250 --runs 1

`legacy` keeps the pre-fix boundary stream that only overrode `close()`, so bulk writes degraded to single
bytes; `fixed` uses the current bulk-write boundary. Both variants share the current store buffering, so
the measurement isolates the boundary fix and understates the original build. Report the environment,
sample size and measured seconds in the validation record; the ratio is a local measurement, not a
promise of end-to-end speedup, and the gateway timeout limit is not measured here.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'ZIPBENCH '


def parse_benchmark(output):
    """Split the Java benchmark's printed lines into environment metadata and timed runs."""
    environment = None
    results = []
    for line in output.splitlines():
        index = line.find(PREFIX)
        if index < 0:
            continue
        entry = json.loads(line[index + len(PREFIX):])
        if 'environment' in entry:
            environment = entry['environment']
            continue
        entry['seconds'] = round(entry.pop('millis') / 1000, 3)
        results.append(entry)
    return environment, results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sample-mib', type=int, default=250, help='Incompressible sample size, default 250')
    parser.add_argument('--runs', type=int, default=1, help='Timed runs per variant')
    parser.add_argument('--module', default='ruoyi-ar', help='Affected reactor module')
    parser.add_argument('--report-dir', type=Path, default=ROOT / '.local/zip-write-benchmark')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--maven', help='Maven executable; discovered on PATH by default')
    parser.add_argument('--online', action='store_true', help='Allow dependency downloads instead of offline mode')
    args = parser.parse_args()
    root = args.root.resolve()
    args.report_dir = args.report_dir.resolve()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    maven = args.maven or shutil.which('mvn.cmd' if os.name == 'nt' else 'mvn')
    if not maven:
        print('Maven missing: provision the Java build environment before running this benchmark')
        raise SystemExit(2)
    env = dict(os.environ)
    java = next((root / '.local/java21').glob('jdk*/bin/java.exe'), None)
    if java:
        env['JAVA_HOME'] = str(java.parent.parent)
        env['PATH'] = str(java.parent) + os.pathsep + env.get('PATH', '')
    command = [maven, '-f', str(root / 'backend/pom.xml'), '-pl', args.module, '-am',
               '-Dmaven.repo.local=' + str(root / '.local/m2'), 'test', '-B', '-ntp',
               '-Dtest=ZipWriteBenchmarkTest', '-Dsurefire.failIfNoSpecifiedTests=false',
               '-Dzip.benchmark.miB=' + str(args.sample_mib), '-Dzip.benchmark.runs=' + str(args.runs)]
    if not args.online:
        command.append('-o')
    started = time.time()
    log = args.report_dir / 'maven.log'
    with log.open('wb') as output:
        result = subprocess.run([str(part) for part in command], cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
    environment, results = parse_benchmark(log.read_text(encoding='utf-8', errors='replace'))
    by_variant = {}
    for entry in results:
        by_variant.setdefault(entry['variant'], []).append(entry['seconds'])
    averages = {name: round(sum(values) / len(values), 3) for name, values in by_variant.items()}
    comparison = None
    if by_variant.get('legacy') and by_variant.get('fixed') and averages['fixed'] > 0:
        seconds = {'legacy': averages['legacy'], 'fixed': averages['fixed']}
        comparison = {'averageSeconds': seconds, 'ratio': round(seconds['legacy'] / seconds['fixed'], 2),
                      'fixedMiBPerSecond': round(args.sample_mib / averages['fixed'], 1),
                      'legacyMiBPerSecond': round(args.sample_mib / averages['legacy'], 1)}
    passed = bool(result.returncode == 0 and environment and by_variant.get('legacy') and by_variant.get('fixed'))
    report = {'passed': passed, 'command': [str(part) for part in command], 'exitCode': result.returncode,
              'seconds': round(time.time() - started, 2), 'mavenLog': str(log), 'environment': environment,
              'sample': {'requestedMiB': args.sample_mib, 'entryMiB': (environment or {}).get('entryMiB'),
                         'runs': args.runs, 'compressible': False, 'bytes': args.sample_mib * 1024 * 1024},
              'results': results, 'comparison': comparison,
              'limitations': ['Single-process micro-benchmark of the ZIP write chain only; no HTTP, gateway or client timing',
                              'Both variants reuse the current store buffering, so the measured legacy cost understates the pre-fix build',
                              'The ratio is a local measurement for the validation record, not a promised end-to-end speedup',
                              'The real ~60s gateway limit is not exercised here; a real 250 MiB build stays host acceptance']}
    (args.report_dir / 'zip-write-benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if comparison:
        print(f"legacy {comparison['averageSeconds']['legacy']}s vs fixed {comparison['averageSeconds']['fixed']}s "
              f"({comparison['legacyMiBPerSecond']} vs {comparison['fixedMiBPerSecond']} MiB/s, ratio {comparison['ratio']})")
    print(json.dumps({'passed': passed, 'environment': environment, 'comparison': comparison}, ensure_ascii=False))
    print('Report: ' + str(args.report_dir / 'zip-write-benchmark.json'))
    raise SystemExit(0 if passed else (2 if environment is None else 1))


if __name__ == '__main__':
    main()
