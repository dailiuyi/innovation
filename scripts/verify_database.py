"""Start a private throwaway PostgreSQL cluster; never connect to existing databases.
Requires psycopg and local PostgreSQL binaries. Keeps its temporary directory for inspection.
"""
from pathlib import Path
import argparse
import json
import os
import secrets
import socket
import subprocess
import tempfile
import uuid
import psycopg

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pg-bin', default=r'C:\Program Files\PostgreSQL\18\bin')
    args = parser.parse_args()
    binaries = Path(args.pg_bin)
    work = Path(tempfile.mkdtemp(prefix='utopia-design-pg-'))
    password = secrets.token_urlsafe(32)
    pwfile = work / 'password.txt'
    pwfile.write_text(password, encoding='utf-8')
    data = work / 'data'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    def run(name, *parts):
        # PostgreSQL children can inherit Windows pipe handles; use a file, not PIPE.
        logfile = work / (name + '-command.log')
        with logfile.open('w', encoding='utf-8') as out:
            proc = subprocess.run([str(binaries / (name + '.exe')), *map(str, parts)],
                                  stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                  timeout=90)
        output = logfile.read_text(encoding='utf-8', errors='replace')
        if proc.returncode:
            raise RuntimeError(f'{name} failed: {output}')
        return output.strip()
    checks = []
    started = False
    report = {'temporaryCluster': str(work), 'checks': checks}
    try:
        report['serverVersion'] = run('postgres', '--version')
        run('initdb', '-D', data, '-U', 'design_review', '--pwfile', pwfile,
            '-A', 'scram-sha-256', '--encoding=UTF8', '--locale=C')
        # Listen only on loopback, random free port; no system service registration.
        run('pg_ctl', '-D', data, '-l', work / 'postgres.log', '-o',
            f'-h 127.0.0.1 -p {port}', '-w', 'start')
        started = True
        conn_args = dict(host='127.0.0.1', port=port, user='design_review',
                         password=password, dbname='postgres', autocommit=True, connect_timeout=5)
        with psycopg.connect(**conn_args) as db:
            for file in sorted((ROOT / 'database/migrations').glob('*.sql')):
                with db.transaction():
                    db.execute(file.read_text(encoding='utf-8'))
                checks.append({'name': 'apply ' + file.name, 'passed': True})
            def one(sql, params=()):
                return db.execute(sql, params).fetchone()[0]
            def check(name, condition):
                assert condition, name
                checks.append({'name': name, 'passed': True})
            def rejects(name, sql, params=()):
                try:
                    with db.transaction():
                        db.execute(sql, params)
                except psycopg.Error:
                    checks.append({'name': name, 'passed': True})
                    return
                raise AssertionError(name + ' should have been rejected')
            user = one("INSERT INTO admin_user(login,display_name,password_hash) VALUES ('review','Review','not-a-login-hash') RETURNING id")
            scene = one("INSERT INTO scene(name) VALUES ('Park story') RETURNING id")
            other_scene = one("INSERT INTO scene(name) VALUES ('Other story') RETURNING id")
            marker = one("INSERT INTO marker(scene_id,code,width_m,height_m,x,y,z,qx,qy,qz,qw) VALUES (%s,'review-marker',0.2,0.2,0,0,0,0,0,0,1) RETURNING id", (scene,))
            rejects('invalid quaternion', "INSERT INTO marker(scene_id,code,width_m,height_m,x,y,z,qx,qy,qz,qw) VALUES (%s,'invalid-marker',0.2,0.2,0,0,0,0,0,0,0)", (scene,))
            rejects('marker geometry immutable', "UPDATE marker SET width_m=0.3 WHERE id=%s", (marker,))
            def make_asset(ready=True):
                aid = uuid.uuid4()
                db.execute("""INSERT INTO asset(id,kind,upload_key,object_key,content_type,expected_bytes,expected_sha256,created_by)
                    VALUES (%s,'BUNDLE',%s,%s,'application/octet-stream',1,%s,%s)""", (aid,'staging/'+str(aid),'final/'+str(aid),'a'*64,user))
                if ready:
                    db.execute("UPDATE asset SET verified_bytes=1,verified_sha256=%s,state='READY' WHERE id=%s", ('a'*64,aid))
                return aid
            asset = make_asset()
            pending = make_asset(False)
            rejects('unverified asset cannot become ready', "UPDATE asset SET state='READY' WHERE id=%s", (pending,))
            rejects('verified asset key immutable', "UPDATE asset SET object_key='different' WHERE id=%s", (asset,))
            config = json.dumps({'ANDROID':{'format':'review','runtimeVersion':'review','minClientBuild':1,'entrypoint':'main.bundle'}})
            def version(number, variant='DAY', scene_id=scene, file_id=asset):
                vid = uuid.uuid4()
                db.execute("INSERT INTO scene_version(id,scene_id,variant,version_no,packages,created_by) VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
                           (vid,scene_id,variant,number,config,user))
                db.execute("INSERT INTO version_asset VALUES (%s,%s,'ANDROID','main.bundle')", (vid,file_id))
                return vid
            v1 = version(1)
            v2 = version(2)
            night = version(1,'NIGHT')
            other = version(1,scene_id=other_scene)
            bad = version(3,file_id=pending)
            rejects('duplicate version number', "INSERT INTO scene_version(id,scene_id,variant,version_no,created_by) VALUES (%s,%s,'DAY',1,%s)", (uuid.uuid4(),scene,user))
            rejects('unverified version cannot seal', 'SELECT seal_version(%s,0,%s)', (bad,user))
            def publish(vid, expected, var='DAY', actor=user):
                return one('SELECT publish_version(%s,%s,%s,%s,%s,%s)', (scene,var,vid,expected,actor,'review'))
            rejects('draft cannot publish', "SELECT publish_version(%s,'DAY',%s,0,%s,'bad')", (scene,v1,user))
            for vid in (v1,v2,night,other): db.execute('SELECT seal_version(%s,0,%s)', (vid,user))
            check('ready but never published is not public', not one('SELECT version_was_published(%s)', (v1,)))
            rejects('ready version content immutable', "UPDATE scene_version SET note='changed' WHERE id=%s", (v1,))
            rejects('ready associations immutable', 'DELETE FROM version_asset WHERE version_id=%s', (v1,))
            rejects('version from another scene rejected', "SELECT publish_version(%s,'DAY',%s,0,%s,'bad')", (scene,other,user))
            rejects('day version cannot publish as night', "SELECT publish_version(%s,'NIGHT',%s,0,%s,'bad')", (scene,v1,user))
            with psycopg.connect(**conn_args) as db2:
                db2.execute("SET lock_timeout='150ms'")
                with db.transaction():
                    check('publish first version', publish(v1,0)==1)
                    try:
                        db2.execute("SELECT publish_version(%s,'DAY',%s,0,%s,'concurrent')", (scene,v2,user))
                    except psycopg.errors.LockNotAvailable:
                        check('concurrent publisher cannot overwrite locked scene', True)
                    else:
                        raise AssertionError('second publisher should wait on scene lock')
            check('published version publicly eligible', one('SELECT version_was_published(%s)', (v1,)))
            rejects('stale publisher CAS rejected', "SELECT publish_version(%s,'DAY',%s,0,%s,'stale')", (scene,v2,user))
            check('publish second version', publish(v2,1)==2)
            check('publish night independently', publish(night,2,'NIGHT')==3)
            check('day pointer unchanged by night publish', one('SELECT current_day_version_id FROM scene WHERE id=%s',(scene,))==v2)
            check('rollback first day version', publish(v1,3)==4)
            check('night pointer unchanged by day rollback', one('SELECT current_night_version_id FROM scene WHERE id=%s',(scene,))==night)
            check('only successful publications audited', one("SELECT count(*) FROM audit_log WHERE action='PUBLISH_VERSION'")==4)
            rejects('audit immutable', "DELETE FROM audit_log WHERE action='PUBLISH_VERSION'")
            check('withdraw day', publish(None,4)==5)
            check('withdraw does not erase published history', one('SELECT version_was_published(%s)',(v1,)))
            db.execute("UPDATE scene_version SET state='REVOKED' WHERE id=%s",(v2,))
            rejects('revoked version cannot publish', "SELECT publish_version(%s,'DAY',%s,5,%s,'bad')", (scene,v2,user))
            db.execute("UPDATE asset SET state='REVOKED' WHERE id=%s",(asset,))
            check('revoked file blocks runtime download', not one('SELECT version_is_servable(%s)',(v1,)))
            db.execute('UPDATE admin_user SET enabled=false WHERE id=%s',(user,))
            rejects('disabled admin cannot publish', "SELECT publish_version(%s,'DAY',null,5,%s,'bad')", (scene,user))
            actual = {row[0] for row in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
            check('only seven approved tables', actual=={'admin_user','scene','scene_version','asset','version_asset','marker','audit_log'})
            report['tableCount'] = one("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
            report['passed'] = True
    except Exception as exc:
        report['passed'] = False
        report['error'] = str(exc).replace(password, '[redacted]')
        raise
    finally:
        if started:
            run('pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop')
        report['clusterStopped'] = started
        output = ROOT / 'docs/validation-database.json'
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='checks'}, ensure_ascii=False))
        print(f'Checks: {len(checks)}; report: {output}')

if __name__ == '__main__':
    main()
