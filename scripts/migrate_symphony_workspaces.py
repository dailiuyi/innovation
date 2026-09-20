"""Copy stopped Symphony workspaces into an empty native volume; never delete the source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time


def migrate(source, destination):
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('Migration roots cannot be symbolic links')
    source, destination = source.resolve(strict=True), destination.resolve(strict=True)
    if not source.is_dir() or not destination.is_dir():
        raise ValueError('Migration roots must be directories')
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Migration roots must be separate')
    if any(destination.iterdir()):
        raise ValueError('Destination must be empty; retain incomplete copies for inspection')
    started = time.monotonic()
    entries = []
    total = 0
    def fail_walk(error):
        raise error

    for folder, dirs, files in os.walk(source, followlinks=False, onerror=fail_walk):
        dirs.sort()
        files.sort()
        for name in list(dirs) + files:
            old = Path(folder) / name
            relative = old.relative_to(source)
            new = destination / relative
            info = old.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if old.is_symlink():
                target = os.readlink(old)
                os.symlink(target, new)
                if name in dirs:
                    dirs.remove(name)
                entries.append({'path': relative.as_posix(), 'link': target})
            elif old.is_dir():
                new.mkdir()
                entries.append({'path': relative.as_posix(), 'directory': True})
            elif old.is_file():
                digest = hashlib.sha256()
                with old.open('rb') as src, new.open('xb') as dst:
                    while block := src.read(1024 * 1024):
                        digest.update(block)
                        dst.write(block)
                after = old.stat()
                if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Source changed during migration: ' + str(relative))
                shutil.copystat(old, new, follow_symlinks=False)
                with new.open('rb') as dst:
                    if hashlib.file_digest(dst, 'sha256').hexdigest() != digest.hexdigest():
                        raise ValueError('Destination bytes differ: ' + str(relative))
                entries.append({'path': relative.as_posix(), 'bytes': info.st_size,
                                'sha256': digest.hexdigest(), 'mode': mode})
                total += info.st_size
            else:
                raise ValueError('Unsupported special file: ' + str(relative))
            if len(entries) % 2000 == 0:
                print(json.dumps({'copiedEntries': len(entries), 'bytes': total}), flush=True)
    for entry in entries:
        path = destination / entry['path']
        if 'link' in entry and os.readlink(path) != entry['link']:
            raise ValueError('Link verification failed')
    report = {'verified': True, 'entries': len(entries), 'bytes': total,
              'seconds': round(time.monotonic() - started, 3),
              'source': str(source), 'destination': str(destination),
              'workspaces': sorted(p.name for p in source.iterdir() if p.is_dir()),
              'inventorySha256': hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()}
    (destination / '.migration-inventory.json').write_text(json.dumps(entries), encoding='utf-8')
    (destination / '.migration-verified.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    migrate(args.source, args.destination)
