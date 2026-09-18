"""Reference transport tools, not the production API or an AR runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen


CHUNK = 64 * 1024


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download(url, destination, size, sha256, timeout=30, headers=None):
    """One attempt; rerun after a network failure to resume. One writer per destination."""
    extra = {} if headers is None else dict(headers)
    if type(size) is not int or size < 0 or not re.fullmatch("[0-9a-f]{64}", sha256):
        raise ValueError("Expected nonnegative size and lowercase SHA256")
    if not url.startswith(("http://", "https://")):
        raise ValueError("Only HTTP(S) is supported")
    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.stat().st_size == size and digest(destination) == sha256:
            return destination
        raise ValueError("Destination already exists with different content")
    partial = destination.with_name(destination.name + "." + sha256 + ".part")
    metadata = partial.with_suffix(".json")
    lock = destination.with_name(destination.name + ".download.lock")
    with lock.open("x"):
        pass
    try:
        offset = partial.stat().st_size if partial.exists() else 0
        etag = None
        if metadata.exists():
            try:
                etag = json.loads(metadata.read_text("utf-8")).get("etag")
            except (ValueError, AttributeError):
                etag = None
        if not isinstance(etag, str) or not re.fullmatch(r'"[\x21\x23-\x7e]*"', etag):
            etag = None
        if offset > size:
            partial.unlink()
            offset = 0
        if offset == size and partial.exists():
            if digest(partial) != sha256:
                partial.unlink()
                raise ValueError("Checksum mismatch; rerun to restart")
        else:
            headers = {"Accept-Encoding": "identity"}
            if extra:
                headers.update(extra)
            if offset and etag:
                headers.update({"Range": f"bytes={offset}-", "If-Range": etag})
            else:
                offset = 0
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("Encoded responses cannot be resumed")
                actual_etag = response.headers.get("ETag")
                strong = bool(actual_etag and re.fullmatch(r'"[\x21\x23-\x7e]*"', actual_etag))
                if response.status == 206:
                    if not offset or actual_etag != etag:
                        raise ValueError("Unexpected partial response or changed ETag")
                    if response.headers.get("Content-Range") != f"bytes {offset}-{size - 1}/{size}":
                        raise ValueError("Unexpected Content-Range")
                elif response.status == 200:
                    offset = 0  # Range ignored or If-Range mismatch: truncate, never append.
                else:
                    raise ValueError("Unexpected HTTP status")
                if response.headers.get("Content-Length") != str(size - offset):
                    raise ValueError("Unexpected Content-Length")
                # Truncate before updating validator so a crash cannot pair old bytes with new ETag.
                with partial.open("ab" if offset else "wb") as output:
                    metadata.write_text(json.dumps({"etag": actual_etag if strong else None}), "utf-8")
                    while block := response.read(CHUNK):
                        if output.tell() + len(block) > size:
                            raise ValueError("Response exceeds expected size")
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
            if partial.stat().st_size != size:
                raise IOError("Download incomplete; rerun to resume")
            if digest(partial) != sha256:
                partial.unlink()
                raise ValueError("Checksum mismatch; rerun to restart")
        # Same-volume hard link makes complete bytes visible without overwriting another file.
        os.link(partial, destination)
        partial.unlink()
        metadata.unlink(missing_ok=True)
        return destination
    finally:
        lock.unlink(missing_ok=True)


RESERVED_SEGMENT = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.I)


def validate_relative_path(path):
    if not isinstance(path, str) or not path or "\0" in path or "\\" in path:
        raise ValueError("unsafe relative path")
    if path.startswith("/") or path.endswith("/") or "//" in path:
        raise ValueError("unsafe relative path")
    if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
        raise ValueError("unsafe relative path")
    parts = path.split("/")
    if not parts or len(parts) > 32 or len(path) > 1024:
        raise ValueError("unsafe relative path")
    for part in parts:
        if part in (".", "..") or not part or len(part) > 255:
            raise ValueError("unsafe relative path")
        if part.startswith(" ") or part.endswith(" ") or part.endswith("."):
            raise ValueError("unsafe relative path")
        if any(ord(c) < 32 or c == 127 or c in '<>:"|?*' for c in part):
            raise ValueError("unsafe relative path")
        if RESERVED_SEGMENT.fullmatch(part):
            raise ValueError("unsafe relative path")
    return path


def restore_tree(manifest, destination, base_url="", headers=None, timeout=30):
    """Download every manifest file into destination, keeping the top-level folder."""
    destination = Path(destination).absolute()
    if destination.exists():
        raise ValueError("destination already exists")
    files = manifest["files"]
    paths = [validate_relative_path(item["relativePath"]) for item in files]
    if len(set(paths)) != len(paths) or len({p.lower() for p in paths}) != len(paths):
        raise ValueError("relative path conflict")
    ordered = sorted(path.lower() for path in paths)
    for index, prefix in enumerate(ordered):
        for other in ordered[index + 1:]:
            if other.startswith(prefix + "/"):
                raise ValueError("file and directory path conflict")
            if not other.startswith(prefix):
                break
    destination.mkdir(parents=True)
    for item in files:
        relative = validate_relative_path(item["relativePath"])
        url = item["downloadPath"]
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        target = destination.joinpath(*relative.split("/"))
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError("path escaped destination")
        download(url, target, int(item["bytes"]), item["sha256"], timeout=timeout, headers=headers)
        if digest(target) != item["sha256"] or target.stat().st_size != item["bytes"]:
            raise ValueError("restored file mismatch")
    return destination


def reference_server(package, port=0):
    """Loopback-only test server for one immutable file. No production authentication."""
    package = Path(package).resolve()
    size, etag = package.stat().st_size, '"' + digest(package) + '"'

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.transfer(False)

        def do_GET(self):
            self.transfer(True)

        def transfer(self, body):
            if self.path != "/artifact":
                self.send_error(404)
                return
            start, end, status = 0, size - 1, 200
            request_range = self.headers.get("Range") if body else None
            if request_range and self.headers.get("If-Range", etag) == etag:
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", request_range)
                if match:
                    start = int(match[1])
                    end = min(int(match[2]) if match[2] else size - 1, size - 1)
                    if start >= size or end < start:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    status = 206
                # Other range forms are ignored; full 200 is permitted by HTTP.
            self.send_response(status)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-transform")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if body:
                try:
                    with package.open("rb") as source:
                        source.seek(start)
                        remaining = end - start + 1
                        while remaining:
                            block = source.read(min(CHUNK, remaining))
                            if not block:
                                break
                            self.wfile.write(block)
                            remaining -= len(block)
                except (BrokenPipeError, ConnectionResetError):
                    pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("download")
    p.add_argument("url")
    p.add_argument("destination", type=Path)
    p.add_argument("--bytes", required=True, type=int)
    p.add_argument("--sha256", required=True)
    p = commands.add_parser("serve")
    p.add_argument("package", type=Path)
    p.add_argument("--port", type=int, default=18083)
    p = commands.add_parser("restore-manifest")
    p.add_argument("manifest", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--base-url", default="")
    args = parser.parse_args()
    if args.command == "download":
        token = os.environ.get("AR_TOKEN")
        download(args.url, args.destination, args.bytes, args.sha256,
                 headers={"Authorization": "Bearer " + token} if token else None)
        print("Verified and downloaded")
    elif args.command == "restore-manifest":
        token = os.environ.get("AR_TOKEN")
        restore_tree(json.loads(args.manifest.read_text("utf-8")), args.destination, args.base_url,
                     headers={"Authorization": "Bearer " + token} if token else None)
        print("Verified and restored")
    else:
        with reference_server(args.package, args.port) as server:
            print(f"Reference only: http://127.0.0.1:{server.server_port}/artifact", flush=True)
            server.serve_forever()


if __name__ == "__main__":
    main()
