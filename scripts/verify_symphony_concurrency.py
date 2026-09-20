"""One baseline and two concurrent warm-dependency builds in a disposable native volume.

Run without network, credentials or the scheduler, with the seed volume read-only.
Never use the live task workspace as --output. Keeps all evidence for inspection.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time

from frontend_control import hash_files, package_tree
from harness import Step, run_step
from symphony_task import fingerprint


def counters():
    root = Path('/sys/fs/cgroup')
    def pairs(name):
        return {k: int(v) for k, v in (line.split() for line in (root / name).read_text().splitlines())}
    return {'memoryBytes': int((root / 'memory.current').read_text()),
            'anonymousBytes': pairs('memory.stat')['anon'], 'events': pairs('memory.events'),
            'cpu': pairs('cpu.stat')}


def copy_ignored(seed, folder, names):
    relative = Path(folder).relative_to(seed)
    excluded = {'__pycache__'}
    if relative == Path('frontend'):
        excluded.add('dist')
    if relative == Path('.local'):
        excluded.update({'harness', 'frontend-control', 'agent-check', 'java-check'})
    if len(relative.parts) == 2 and relative.parts[0] == 'backend':
        excluded.add('target')
    return set(names) & excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    seed, output = args.seed.resolve(strict=True), args.output.resolve(strict=True)
    if seed == output or seed in output.parents or output in seed.parents or any(output.iterdir()):
        parser.error('Use a separate, empty output volume; nothing is overwritten')
    if any(os.environ.get(k) for k in ('GITHUB_TOKEN', 'DEEPSEEK_API_KEY')):
        parser.error('Run this benchmark without credentials')
    before_source = fingerprint(seed)
    seed_dependencies = package_tree(seed)
    results = []
    for name in ('baseline', 'parallel-a', 'parallel-b'):
        target = output / name
        shutil.copytree(seed, target, symlinks=True,
                        ignore=lambda folder, names: copy_ignored(seed, folder, names))
        if package_tree(target) != seed_dependencies:
            raise RuntimeError('Copied installed dependencies differ from seed')
        if fingerprint(target) != before_source:
            raise RuntimeError('Copied source differs from seed')
    env = dict(os.environ)
    env.pop('SYMPHONY_ENVIRONMENT_LOCK', None)
    def execute(name):
        workspace = output / name
        evidence = output / (name + '-evidence')
        evidence.mkdir()
        started = time.monotonic()
        java = run_step(Step('java', [str(workspace / '.local/venv/bin/python'),
                                     str(Path(__file__).with_name('check_java.py')), '--root', str(workspace),
                                     '--module', 'ruoyi-ar', '--offline'], workspace, 600), evidence, env)
        build = run_step(Step('frontend', ['npm', '--prefix', str(workspace / 'frontend'),
                                          'run', 'build:prod'], workspace, 300), evidence, env)
        java_reports = list((workspace / '.local/java-check').glob('*/report.json'))
        java_report = json.loads(java_reports[0].read_text()) if len(java_reports) == 1 else {}
        result = {'name': name, 'seconds': round(time.monotonic()-started, 3),
                  'java': java, 'javaTests': java_report,
                  'frontend': build, 'sourceUnchanged': fingerprint(workspace) == before_source,
                  'output': hash_files(workspace / 'frontend/dist')}
        print(json.dumps({'completed': name, 'seconds': result['seconds'],
                          'java': java['status'], 'frontend': build['status']}), flush=True)
        return result
    baseline = execute('baseline')
    if baseline['java']['status'] != 'passed' or baseline['frontend']['status'] != 'passed':
        (output / 'baseline-failed.json').write_text(json.dumps(baseline, indent=2))
        raise RuntimeError('Baseline failed; inspect evidence before attempting concurrent work')
    before = counters()
    samples = []
    stopped = threading.Event()
    def monitor():
        while not stopped.is_set():
            samples.append(counters())
            stopped.wait(0.1)
    thread = threading.Thread(target=monitor)
    thread.start()
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(execute, ('parallel-a', 'parallel-b')))
    finally:
        stopped.set()
        thread.join()
    wall = time.monotonic() - started
    after = counters()
    all_results = [baseline, *results]
    passed = all(r['sourceUnchanged'] and r['java']['status'] == 'passed'
                 and r['frontend']['status'] == 'passed' and r['javaTests'].get('tests', 0) > 0
                 and r['output'] == baseline['output'] for r in all_results)
    passed = passed and fingerprint(seed) == before_source and after['events']['oom_kill'] == before['events']['oom_kill']
    report = {'status': 'passed' if passed else 'failed', 'sourceSha256': before_source,
              'dependencies': 'Independent copies of the existing Linux task dependencies; offline warm-cache benchmark',
              'baseline': baseline, 'parallel': results, 'parallelWallSeconds': round(wall, 3),
              'parallelThroughputVsSerial': round(2 * baseline['seconds'] / wall, 3),
              'peakMemoryBytesIncludingCache': max(s['memoryBytes'] for s in samples),
              'peakAnonymousBytes': max(s['anonymousBytes'] for s in samples),
              'beforeCounters': before, 'afterCounters': after,
              'scope': 'Two concurrent Java module tests and production frontend builds. No model inference, cold downloads or HTTP/browser acceptance.'}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('baseline','parallel','beforeCounters','afterCounters')}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
