"""Start/stop only this project's isolated demo processes. Secrets stay in .local."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
LOCAL = ROOT / '.local'
LOCAL.mkdir(exist_ok=True)
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
PG = Path(os.environ.get('AR_PG_BIN', LOCAL / 'postgresql17/pgsql/bin'))
JAVA = Path(os.environ.get('AR_JAVA_HOME', next((LOCAL / 'java21').glob('jdk*'), Path('missing'))))
config_file = LOCAL / 'demo-secrets.json'
if not config_file.exists():
    config_file.write_text(json.dumps({
        'AR_DATABASE_PASSWORD': secrets.token_urlsafe(30),
        'AR_TOKEN_SECRET': secrets.token_urlsafe(64),
        'AR_BOOTSTRAP_PASSWORD': secrets.token_urlsafe(20),
        'AR_DATABASE_USER': 'ar_demo',
        'AR_DATABASE_URL': 'jdbc:postgresql://127.0.0.1:15432/ar_demo',
        'AR_REDIS_PORT': '16379', 'AR_PORT': '18080',
    }), encoding='utf-8')
config = json.loads(config_file.read_text(encoding='utf-8'))
env = dict(os.environ, **config, JAVA_HOME=str(JAVA), TZ='UTC')
env['PATH'] = str(JAVA / 'bin') + os.pathsep + env['PATH']
env['PGPASSWORD'] = config['AR_DATABASE_PASSWORD']
env.setdefault('AR_STORAGE_ENABLED', 'true')
env.setdefault('AR_STORAGE_ROOT', str(LOCAL / 'artifacts'))
env.setdefault('AR_STORAGE_MAX_BYTES', str(256 * 1024 * 1024))
def run(args):
    # A daemon may inherit output handles on Windows; a regular file avoids waiting
    # forever for a PIPE's EOF after pg_ctl has already exited.
    import tempfile
    with tempfile.TemporaryFile() as output:
        result=subprocess.run([str(a) for a in args], env=env, cwd=ROOT, creationflags=FLAGS,stdout=output,stderr=subprocess.STDOUT)
        output.seek(0)
        print(output.read().decode('utf-8',errors='replace'))
    result.check_returncode()
def start(name, args, cwd=ROOT):
    pid_file = LOCAL / (name + '.pid')
    if pid_file.exists():
        raise SystemExit(f'{name} has a recorded PID; stop it before restarting')
    with (LOCAL / (name + '.log')).open('ab') as log:
        proc = subprocess.Popen([str(a) for a in args], env=env, cwd=cwd, stdout=log, stderr=log, creationflags=FLAGS)
    pid_file.write_text(str(proc.pid))
    print(name, 'started; log in .local')
def stop(name, pattern):
    pid_file=LOCAL/(name+'.pid')
    if pid_file.exists():
        pid=int(pid_file.read_text().strip())
        command=f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; if ($p -and $p.CommandLine -notlike '{pattern}') {{ throw 'PID identity mismatch' }}; if ($p) {{ Stop-Process -Id {pid} }}"
        run(['powershell','-NoProfile','-Command',command])
        pid_file.unlink()

action = sys.argv[1]
if action == 'infra':
    version = subprocess.check_output([str(PG / 'postgres.exe'), '--version'], text=True)
    if ' 17.' not in version:
        raise SystemExit('PostgreSQL 17 required: ' + version)
    data = LOCAL / 'pgdata17'
    if not data.exists():
        pwfile = LOCAL / 'pg-password.tmp'
        pwfile.write_text(config['AR_DATABASE_PASSWORD'], encoding='ascii')
        try:
            run([PG/'initdb.exe', '-D', data, '-U', 'ar_demo', '--pwfile='+str(pwfile), '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C'])
        finally:
            pwfile.unlink(missing_ok=True)
    run([PG/'pg_ctl.exe', '-D', data, '-l', LOCAL/'postgres.log', '-o', '-h 127.0.0.1 -p 15432', '-w', 'start'])
    exists = subprocess.check_output([str(PG/'psql.exe'),'-h','127.0.0.1','-p','15432','-U','ar_demo','-d','postgres','-tAc',"select 1 from pg_database where datname='ar_demo'"],env=env,text=True)
    if not exists.strip(): run([PG/'createdb.exe','-h','127.0.0.1','-p','15432','-U','ar_demo','ar_demo'])
    start('redis', ['redis-server', '--bind','127.0.0.1','--port','16379','--save','','--appendonly','no'])
elif action == 'backend':
    start('backend', [JAVA/'bin/java.exe','-Duser.timezone=UTC','-jar',ROOT/'backend/ruoyi-admin/target/ruoyi-admin.jar'])
elif action == 'redis':
    start('redis', ['redis-server', '--bind','127.0.0.1','--port','16379','--save','','--appendonly','no'])
elif action == 'frontend':
    host=env.get('AR_FRONTEND_HOST','127.0.0.1')
    start('frontend',['node',ROOT/'frontend/node_modules/vite/bin/vite.js','--host',host,'--port','43174','--strictPort'],ROOT/'frontend')
    print(f'Frontend: http://{host}:43174')
elif action == 'build':
    if (LOCAL/'backend.pid').exists():
        raise SystemExit('Stop the backend before packaging: python scripts/local_demo.py stop-backend')
    run(['mvn.cmd','-f',ROOT/'backend/pom.xml','-Dmaven.repo.local='+str(LOCAL/'m2'),'package','-B','-ntp'])
elif action == 'stop-backend':
    stop('backend','*innovation*ruoyi-admin.jar*')
elif action == 'stop-frontend':
    stop('frontend','*innovation*node_modules*vite*')
elif action == 'stop':
    stop('frontend','*innovation*node_modules*vite*')
    stop('backend','*innovation*ruoyi-admin.jar*')
    stop('redis','*redis-server*--port 16379*')
    run([PG/'pg_ctl.exe','-D',LOCAL/'pgdata17','-m','fast','-w','stop'])
else:
    raise SystemExit('Use infra, build, backend, frontend, stop-backend, or stop')
