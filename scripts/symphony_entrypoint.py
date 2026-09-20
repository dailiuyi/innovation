"""Initialize Burrito before installing verified modules; never start an unpatched tracker."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PATCHES = Path('/opt/symphony-patches')
EBIN = Path('/opt/symphony/.burrito/symphony_erts-16.4_0.0.3/lib/symphony_elixir-0.0.3/ebin')
REQUIRED = {'Elixir.SymphonyElixir.Orchestrator.beam', 'Elixir.SymphonyElixir.Codex.AppServer.beam'}
OPTIONAL = {'Elixir.SymphonyElixirWeb.Layouts.beam', 'Elixir.SymphonyElixirWeb.DashboardLive.beam'}


def verified_files(patches):
    manifest = json.loads((patches / 'manifest.json').read_text())
    modules = manifest['verifiedModules']
    if set(modules) != REQUIRED:
        raise RuntimeError('Controlled scheduler modules missing')
    preserved = manifest.get('preservedModules', {})
    if not set(preserved) <= OPTIONAL:
        raise RuntimeError('Unexpected preserved module')
    modules = {**modules, **preserved}
    for name, expected in modules.items():
        if hashlib.sha256((patches / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Module fingerprint mismatch: ' + name)
    return modules


def main():
    modules = verified_files(PATCHES)
    # --help performs release extraction without loading a workflow or starting a tracker.
    result = subprocess.run(['/usr/local/bin/symphony', '--help'], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=120)
    if result.returncode not in (0, 1) or b'Usage: symphony' not in result.stdout + result.stderr or not EBIN.is_dir():
        raise RuntimeError('Symphony release initialization failed')
    for name in modules:
        shutil.copyfile(PATCHES / name, EBIN / name)
    print('Verified controlled modules installed; starting Symphony.', flush=True)
    os.execv('/usr/local/bin/symphony', ['/usr/local/bin/symphony', *sys.argv[1:]])


if __name__ == '__main__':
    main()
