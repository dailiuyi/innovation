"""Upgrade an isolated PostgreSQL 17 database from V012 with old draft files, then apply V013.
Never connects to the daily Demo database.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'backend/ruoyi-admin/src/main/resources/db/demo'
SHA = 'a' * 64
import sys
sys.path.insert(0, str(ROOT / '.local/python'))
import psycopg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir', type=Path, default=ROOT / '.local')
    parser.add_argument('--pg-bin', type=Path, default=ROOT / '.local/postgresql17/pgsql/bin')
    args = parser.parse_args()
    args.report_dir = args.report_dir.resolve()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    pg = args.pg_bin
    work = Path(tempfile.mkdtemp(prefix='export-path-mig-', dir=ROOT / '.local'))
    password = secrets.token_urlsafe(24)
    checks = []
    pg_started = False

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)
        if not condition:
            raise AssertionError(name)

    def run(name, *parts):
        log = work / (name.replace(' ', '-') + '.log')
        with log.open('w', encoding='utf-8') as out:
            proc = subprocess.run([str(pg / (name + '.exe')), *map(str, parts)],
                                  stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                  env=env, timeout=90)
        text = log.read_text(encoding='utf-8', errors='replace')
        if proc.returncode:
            raise RuntimeError(name + ' failed: ' + text)
        return text.strip()

    env = dict(os.environ, PGPASSWORD=password)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    try:
        version = run('postgres', '--version')
        check('real PostgreSQL 17 runtime', ' 17.' in version)
        pwfile = work / 'pw.txt'
        pwfile.write_text(password, encoding='ascii')
        data = work / 'pgdata'
        try:
            run('initdb', '-D', data, '-U', 'mig', '--pwfile=' + str(pwfile),
                '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C')
        finally:
            pwfile.unlink(missing_ok=True)
        run('pg_ctl', '-D', data, '-l', work / 'postgres.log', '-o', f'-h 127.0.0.1 -p {port}', '-w', 'start')
        pg_started = True
        run('createdb', '-h', '127.0.0.1', '-p', str(port), '-U', 'mig', 'mig')
        db = psycopg.connect(host='127.0.0.1', port=port, dbname='mig', user='mig', password=password, autocommit=True)
        def sql(statement, params=()):
            with db.cursor() as cur:
                cur.execute(statement, params)
                return cur.fetchall() if cur.description else []
        def apply(path):
            run('psql', '-h', '127.0.0.1', '-p', str(port), '-U', 'mig', '-d', 'mig',
                '-v', 'ON_ERROR_STOP=1', '-f', str(path))
        for path in sorted(MIGRATIONS.glob('V0*.sql')):
            if path.name.startswith('V013'):
                continue
            apply(path)
        check('applied migrations through V012', sql("select to_regclass('ar_draft_file')")[0][0] is not None)
        sql("insert into sys_user(user_name,nick_name,password,status,del_flag) values('mig','mig','x','0','0')")
        user_id = sql("select user_id from sys_user where user_name='mig'")[0][0]
        scene = uuid.uuid4()
        draft = uuid.uuid4()
        collection = uuid.uuid4()
        sql("insert into ar_scene(id,name) values(%s,'mig-scene')", (str(scene),))
        sql("insert into ar_draft(id,scene_id,request_key,description,creator_id,creator_name) values(%s,%s,%s,'d',%s,'mig')",
            (str(draft), str(scene), str(uuid.uuid4()), user_id))
        sql("""insert into ar_draft_collection(id,draft_id,request_key,status,generation,file_count,total_bytes,fingerprint,creator_id,creator_name)
               values(%s,%s,%s,'ACTIVE',1,0,0,%s,%s,'mig')""",
            (str(collection), str(draft), str(uuid.uuid4()), '0' * 64, user_id))

        def add_file(name, rel, fid=None):
            fid = fid or uuid.uuid4()
            sql("""insert into ar_draft_file(id,draft_id,collection_id,request_key,file_name,relative_path,kind,
                    expected_bytes,expected_sha256,storage_key,creator_id,creator_name,last_actor_id,last_actor_name)
                   values(%s,%s,%s,%s,%s,%s,'RESOURCE_FILE',1,%s,%s,%s,'mig',%s,'mig')""",
                (str(fid), str(draft), str(collection), str(uuid.uuid4()), name, rel, SHA, str(fid) + '.bin', user_id, user_id))
            return fid

        nested_a = add_file('a.bin', 'scene/models/a.bin')
        nested_b = add_file('a.bin', 'scene/textures/a.bin')
        keep = add_file('keep.bin', 'keep.bin')
        under = add_file('asset_1', 'safe/asset_1')
        under_child = add_file('data.bin', 'safe/assetA1/data.bin')
        pct = add_file('x.bin', 'dir%/x.bin')
        pct_other = add_file('y.bin', 'dirX/y.bin')
        con = add_file('CON.txt', 'CON.txt', uuid.UUID('aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'))
        colon = add_file('report:2026.txt', 'report:2026.txt', uuid.UUID('11111111-1111-4111-8111-111111111111'))
        qmark = add_file('report?2026.txt', 'report?2026.txt', uuid.UUID('22222222-2222-4222-8222-222222222222'))
        taken = add_file('report_2026-22222222.txt', 'report_2026-22222222.txt')
        before = {row[0]: (row[1], row[2], row[3]) for row in sql(
            "select id::text, file_name, relative_path, storage_key from ar_draft_file")}
        apply(MIGRATIONS / 'V013__safe_export_relative_paths.sql')
        after = {row[0]: (row[1], row[2], row[3]) for row in sql(
            "select id::text, file_name, relative_path, storage_key from ar_draft_file")}
        check('nested models path kept', after[str(nested_a)][1] == 'scene/models/a.bin')
        check('nested textures path kept', after[str(nested_b)][1] == 'scene/textures/a.bin')
        check('same file name in different directories kept', after[str(nested_a)][1] != after[str(nested_b)][1])
        check('valid top-level name kept', after[str(keep)][1] == 'keep.bin')
        check('underscore is not a prefix wildcard', after[str(under)][1] == 'safe/asset_1' and after[str(under_child)][1] == 'safe/assetA1/data.bin')
        check('percent is not a prefix wildcard', after[str(pct)][1] == 'dir%/x.bin' and after[str(pct_other)][1] == 'dirX/y.bin')
        check('reserved name rewritten', after[str(con)][1] == 'export-aaaaaaaa.txt')
        check('colon name sanitized', after[str(colon)][1] == 'report_2026.txt')
        check('question-mark name disambiguated', after[str(qmark)][1] != 'report_2026.txt' and after[str(qmark)][1] != 'report_2026-22222222.txt')
        check('sanitized names unique', after[str(colon)][1] != after[str(qmark)][1])
        check('existing disambiguated name kept', after[str(taken)][1] == 'report_2026-22222222.txt')
        check('generated name did not collide with existing',
              after[str(colon)][1] != 'report_2026-22222222.txt' and after[str(qmark)][1] != 'report_2026-22222222.txt')
        check('all live paths unique ignoring case',
              len({p[1].lower() for p in after.values()}) == len(after))
        check('file names unchanged', all(after[i][0] == before[i][0] for i in before))
        check('storage keys unchanged', all(after[i][2] == before[i][2] for i in before))
        check('unique index restored', sql("select indexname from pg_indexes where indexname='ar_draft_file_path_uidx'")[0][0] == 'ar_draft_file_path_uidx')
        report = {'passed': True, 'postgres': version, 'work': str(work), 'checks': checks}
        (args.report_dir / 'validation-export-path-migration.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    finally:
        (work / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
        if pg_started:
            subprocess.run([str(pg / 'pg_ctl.exe'), '-D', str(work / 'pgdata'), '-m', 'fast', '-w', 'stop'],
                           env=env, capture_output=True, timeout=30)
        print('Evidence directory:', work, flush=True)


if __name__ == '__main__':
    main()
