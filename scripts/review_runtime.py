"""Disposable Windows PostgreSQL/Redis/Java runtime, owned by its foreground parent."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def request(base, path, method='GET', body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        content = response.read()
        return response.status, json.loads(content) if content else {}


class Runtime:
    def __init__(self, source, resources, directory, jar, password=None):
        if os.name != 'nt':
            raise RuntimeError('HTTP preview runtime currently requires Windows')
        self.source, self.directory, self.jar = source, directory, jar
        self.pg = resources / '.local/postgresql17/pgsql/bin'
        self.java = next((resources / '.local/java21').glob('jdk*/bin/java.exe'))
        self.directory.mkdir(parents=True, exist_ok=False)
        self.processes, self.logs = [], []
        self.pg_started = False
        self.password = password or secrets.token_urlsafe(18)
        ports = set()
        while len(ports) < 4:
            ports.add(free_port())
        self.pg_port, redis, api, web = sorted(ports)
        self.base, self.web = f'http://127.0.0.1:{api}', f'http://127.0.0.1:{web}'
        self.web_port = web
        db_password = secrets.token_urlsafe(24)
        # All service-related variables are explicitly scoped to this new runtime.
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('AR_')}
        self.env.update(AR_DATABASE_URL=f'jdbc:postgresql://127.0.0.1:{self.pg_port}/review',
                        AR_DATABASE_USER='review', AR_DATABASE_PASSWORD=db_password,
                        AR_TOKEN_SECRET=secrets.token_urlsafe(64), AR_BOOTSTRAP_PASSWORD=self.password,
                        AR_REDIS_HOST='127.0.0.1', AR_REDIS_PORT=str(redis), AR_PORT=str(api),
                        AR_STORAGE_ENABLED='true', AR_STORAGE_ROOT=str(directory / 'artifacts'),
                        AR_STORAGE_MAX_BYTES=str(256 * 1024 * 1024),
                        AR_UPLOAD_DIR=str(directory / 'uploads'), AR_DEV_API_TARGET=self.base,
                        PGPASSWORD=db_password)
        self.redis_port = redis

    def command(self, args):
        with (self.directory / 'commands.log').open('ab') as log:
            subprocess.run([str(a) for a in args], env=self.env, cwd=self.directory,
                           stdout=log, stderr=log, check=True, timeout=90,
                           creationflags=subprocess.CREATE_NO_WINDOW)

    def start(self, name, args, cwd=None):
        log = (self.directory / (name + '.log')).open('ab')
        self.logs.append(log)
        process = subprocess.Popen([str(a) for a in args], env=self.env, cwd=cwd or self.directory,
                                   stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        self.processes.append(process)
        return process

    def __enter__(self):
        try:
            version = subprocess.check_output([str(self.pg / 'postgres.exe'), '--version'], text=True)
            if ' 17.' not in version:
                raise RuntimeError('PostgreSQL 17 required')
            self.pg_version = version.strip()
            pw = self.directory / 'init-password'
            pw.write_text(self.env['AR_DATABASE_PASSWORD'], encoding='ascii')
            try:
                self.command([self.pg / 'initdb.exe', '-D', self.directory / 'pgdata', '-U', 'review',
                              '--pwfile=' + str(pw), '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C'])
            finally:
                pw.unlink(missing_ok=True)
            # Set before launch so cleanup also handles a partially successful pg_ctl.
            self.pg_started = True
            self.command([self.pg / 'pg_ctl.exe', '-D', self.directory / 'pgdata', '-l',
                          self.directory / 'postgres.log', '-o', f'-h 127.0.0.1 -p {self.pg_port}', '-w', 'start'])
            self.command([self.pg / 'createdb.exe', '-h', '127.0.0.1', '-p', self.pg_port, '-U', 'review', 'review'])
            self.start('redis', ['redis-server', '--bind', '127.0.0.1', '--port', self.redis_port,
                                 '--save', '', '--appendonly', 'no'])
            backend = self.start('backend', [self.java, '-Duser.timezone=UTC', '-jar', self.jar,
                                              '--server.address=127.0.0.1'])
            until = time.monotonic() + 120
            while time.monotonic() < until:
                if backend.poll() is not None:
                    raise RuntimeError('Backend exited; inspect isolated backend.log')
                try:
                    if request(self.base, '/captchaImage')[0] == 200:
                        return self
                except (OSError, ValueError):
                    pass
                time.sleep(.3)
            raise RuntimeError('Backend startup timeout')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def frontend(self):
        frontend = self.start('frontend', ['node', self.source / 'frontend/node_modules/vite/bin/vite.js',
                                           '--host', '127.0.0.1', '--port', self.web_port, '--strictPort'],
                              self.source / 'frontend')
        until = time.monotonic() + 60
        while time.monotonic() < until:
            if frontend.poll() is not None:
                raise RuntimeError('Vite exited; inspect isolated frontend.log')
            try:
                with urllib.request.urlopen(self.web, timeout=5) as response:
                    html = response.read().decode()
                if '/src/main' in html and request(self.web, '/dev-api/captchaImage')[0] == 200:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.3)
        raise RuntimeError('Frontend/proxy startup timeout')

    def __exit__(self, *args):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        try:
            if self.pg_started and (self.directory / 'pgdata/postmaster.pid').exists():
                self.command([self.pg / 'pg_ctl.exe', '-D', self.directory / 'pgdata', '-m', 'fast', '-w', 'stop'])
        finally:
            for log in self.logs:
                log.close()


def account_smoke(runtime):
    """Real HTTP flow: 6-char bootstrap first, then create/reset/change and revoked sessions."""
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    def api(path, method='GET', body=None, token=None):
        status, result = request(runtime.base, path, method, body, token)
        return status, result

    def login(user, password):
        status, body = api('/login', 'POST', {'username': user, 'password': password})
        check('login ' + user, status == 200 and body.get('code') == 200 and bool(body.get('token')))
        return body['token']

    def valid(token):
        status, body = api('/getInfo', token=token)
        return status == 200 and body.get('code') == 200

    def reject(result, name):
        status, body = result
        check(name, (status != 200 or body.get('code') != 200) and '6–64' in body.get('msg', ''))

    admin = login('bootstrap', runtime.password)  # Fail fast: this caught PR #8's original defect.
    for size in (5, 65, 6, 64):
        result = api('/system/user', 'POST', {'userName': f'review_{size}', 'nickName': 'Review',
                                             'password': 'a' * size}, admin)
        if size in (5, 65):
            reject(result, f'create rejects {size}')
        else:
            check(f'create accepts {size}', result[0] == 200 and result[1].get('code') == 200)
            created = login(f'review_{size}', 'a' * size)
            if size == 6:
                admin = created  # First account retires bootstrap; never re-enable it.
    rows = api('/system/user/list', token=admin)[1]['rows']
    check('invalid creates leave no accounts', not any(r['userName'] in ('review_5', 'review_65') for r in rows))
    target_id = next(row['userId'] for row in rows if row['userName'] == 'review_64')
    password = 'a' * 64
    for operation in ('reset', 'own'):
        for size in (5, 65, 6, 64):
            old = [login('review_64', password), login('review_64', password)]
            new = ('b' if operation == 'reset' else 'c') * size
            if operation == 'reset':
                result = api('/system/user/resetPwd', 'PUT', {'userId': target_id, 'password': new}, admin)
            else:
                result = api('/system/user/profile/updatePwd', 'PUT',
                             {'oldPassword': password, 'newPassword': new}, old[0])
            if size in (5, 65):
                reject(result, f'{operation} rejects {size}')
                check(f'{operation} failure preserves sessions {size}', all(valid(t) for t in old))
                login('review_64', password)
            else:
                check(f'{operation} accepts {size}', result[0] == 200 and result[1].get('code') == 200)
                check(f'{operation} revokes both sessions {size}', all(not valid(t) for t in old))
                password = new
                login('review_64', password)
    return checks
