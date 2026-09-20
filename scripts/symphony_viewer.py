"""Read-only, loopback-only viewer for Symphony's persisted Codex events."""
import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / '.local/symphony/data/codex/sessions'
PAGE = Path(__file__).with_name('symphony_viewer.html')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def session_files():
    return {m.group(): p for p in SESSIONS.glob('**/rollout-*.jsonl')
            if (m := UUID.search(p.name)) and p.resolve().is_relative_to(SESSIONS.resolve())}


def read_events(path, offset):
    events = []
    with path.open('rb') as stream:
        if offset > path.stat().st_size:
            offset = 0
        stream.seek(offset)
        for _ in range(200):
            start = stream.tell()
            line = stream.readline()
            if not line.endswith(b'\n'):
                stream.seek(start)
                break
            try:
                item = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            payload = item.get('payload', {})
            # Never expose encrypted reasoning or duplicate internal event copies.
            if item.get('type') == 'response_item' and payload.get('type') != 'reasoning':
                events.append({'time': item.get('timestamp'), 'type': payload.get('type'),
                               'data': {k: v for k, v in payload.items()
                                        if k != 'internal_chat_message_metadata_passthrough'}})
            elif item.get('type') == 'event_msg' and payload.get('type') in (
                    'token_count', 'task_started', 'task_complete', 'turn_aborted', 'error'):
                events.append({'time': item.get('timestamp'), 'type': payload.get('type'), 'data': payload})
        return {'events': events, 'offset': stream.tell(), 'size': path.stat().st_size}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
            self.send_error(403)
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == '/':
                body, kind = PAGE.read_bytes(), 'text/html; charset=utf-8'
            elif parsed.path == '/api/sessions':
                body, kind = self.json_body([{'id': key, 'updated': p.stat().st_mtime}
                                            for key, p in sorted(session_files().items(), key=lambda x: x[1].stat().st_mtime, reverse=True)])
            elif parsed.path == '/api/state':
                try:
                    with urlopen('http://127.0.0.1:43190/api/v1/state', timeout=2) as response:
                        state = json.load(response)
                    body, kind = self.json_body({'available': True, 'state': state})
                except Exception:
                    body, kind = self.json_body({'available': False})
            elif parsed.path == '/api/events':
                query = parse_qs(parsed.query)
                sid = query.get('id', [''])[0]
                offset = int(query.get('offset', ['0'])[0])
                if not UUID.fullmatch(sid) or offset < 0:
                    raise ValueError('Invalid session or offset')
                path = session_files().get(sid)
                if path is None:
                    self.send_error(404)
                    return
                body, kind = self.json_body(read_events(path, offset))
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        except ValueError:
            self.send_error(400)
        except OSError:
            self.send_error(503)

    @staticmethod
    def json_body(value):
        return json.dumps(value, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=43191)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Session viewer: http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
