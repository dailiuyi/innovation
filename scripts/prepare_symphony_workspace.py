"""Create a task-local venv which can read the image's immutable validators."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

BASE = Path('/opt/symphony-validation')


def prepare(workspace, base=BASE):
    started = time.monotonic()
    requirements = workspace / 'scripts/requirements-review.txt'
    expected = (base / 'requirements.txt').read_text(encoding='utf-8')
    requested = requirements.read_text(encoding='utf-8')
    environment = workspace / '.local/venv'
    if not environment.resolve().is_relative_to(workspace.resolve()):
        raise ValueError('Task environment must stay inside its workspace')
    python = environment / 'bin/python'
    if not python.is_file():
        # Avoid ensurepip copying hundreds of files over a Windows bind mount.
        # pip itself is available through the same immutable image site-packages.
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(environment)], check=True)
    site = Path(subprocess.check_output([
        str(python), '-c', "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip())
    if not site.resolve().is_relative_to(environment.resolve()):
        raise ValueError('Task site-packages must stay inside its environment')
    shared_site = base / 'venv/lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
    if not shared_site.is_dir():
        raise ValueError('Image validation environment is missing or uses a different Python version')
    (site / 'symphony-validation.pth').write_text(str(shared_site) + '\n', encoding='utf-8')
    pip_launcher = environment / 'bin/pip'
    if not pip_launcher.exists():
        pip_launcher.write_text('#!/bin/sh\nexec "$(dirname "$0")/python" -m pip "$@"\n', encoding='utf-8')
        pip_launcher.chmod(0o755)
    # Newline-normalized text compares Windows build input with Linux checkouts.
    matches_image = requested == expected
    if not matches_image:
        # pip installs overrides in this task's venv, never the read-only base.
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
    subprocess.run([str(python), '-c', 'import yaml, jsonschema, openapi_spec_validator, psycopg'], check=True)
    result = {'status': 'passed', 'mode': 'image' if matches_image else 'task-overlay',
              'requirementsSha256': hashlib.sha256(requested.encode()).hexdigest(),
              'seconds': round(time.monotonic() - started, 3)}
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    prepare(Path.cwd())
