"""Real PostgreSQL 17, HTTP and browser ingestion acceptance in a new private local directory.
Never connects to the running Demo database. Keeps failed evidence under .local.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local/python'))
import psycopg
from playwright.sync_api import sync_playwright

CHECKS = []
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

def check(name, condition):
    CHECKS.append({'name': name, 'passed': bool(condition)})
    print(('PASS ' if condition else 'FAIL ') + name, flush=True)
    if not condition:
        raise AssertionError(name)

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def main():
    run = ROOT / '.local' / ('ingestion-check-' + time.strftime('%Y%m%d-%H%M%S'))
    run.mkdir()
    pg = ROOT / '.local/postgresql17/pgsql/bin'
    java = next((ROOT / '.local/java21').glob('jdk*/bin/java.exe'))
    pg_port, redis_port, api_port, web_port = [free_port() for _ in range(4)]
    password = secrets.token_urlsafe(24)
    env = dict(os.environ, AR_DATABASE_URL=f'jdbc:postgresql://127.0.0.1:{pg_port}/ingestion',
               AR_DATABASE_USER='ingestion', AR_DATABASE_PASSWORD=password,
               AR_TOKEN_SECRET=secrets.token_urlsafe(64), AR_BOOTSTRAP_PASSWORD=password,
               AR_REDIS_HOST='127.0.0.1', AR_REDIS_PORT=str(redis_port), AR_PORT=str(api_port),
               AR_STORAGE_ENABLED='true', AR_STORAGE_ROOT=str(run / 'artifacts'),
               AR_STORAGE_MAX_BYTES=str(4 * 1024 * 1024), AR_UPLOAD_DIR=str(run / 'framework-uploads'),
               AR_DEV_API_TARGET=f'http://127.0.0.1:{api_port}', PGPASSWORD=password)
    base = f'http://127.0.0.1:{api_port}'
    token = None
    processes = []
    logs = []
    pg_started = False
    db = None
    def cmd(args):
        with tempfile.TemporaryFile() as output:
            r = subprocess.run([str(a) for a in args], env=env, cwd=run, creationflags=FLAGS, stdout=output, stderr=subprocess.STDOUT)
            output.seek(0)
            content = output.read()
        if r.returncode:
            (run / 'command-error.log').write_bytes(content)
            raise RuntimeError('Test command failed; inspect local command-error.log')
        return content.decode(errors='replace')
    def start(name, args, cwd=run):
        log = (run / (name + '.log')).open('ab'); logs.append(log)
        p = subprocess.Popen([str(a) for a in args], cwd=cwd, env=env, creationflags=FLAGS, stdout=log, stderr=log)
        processes.append(p)
        return p
    def api(path, method='GET', body=None, auth=True, raw=False):
        headers = {'Content-Type': 'application/octet-stream' if raw else 'application/json'}
        if auth and token:
            headers['Authorization'] = 'Bearer ' + token
        data = body if raw else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                content = r.read(); return r.status, json.loads(content) if content else {}
        except urllib.error.HTTPError as e:
            content = e.read(); return e.code, json.loads(content) if content else {}
    def start_backend():
        p = start('backend', [java, '-Duser.timezone=UTC', '-jar', ROOT / 'backend/ruoyi-admin/target/ruoyi-admin.jar', '--server.address=127.0.0.1'])
        until = time.monotonic() + 120
        while time.monotonic() < until:
            if p.poll() is not None:
                raise RuntimeError('Backend exited; inspect ' + str(run / 'backend.log'))
            try:
                if api('/captchaImage', auth=False)[0] == 200:
                    return p
            except OSError:
                pass
            time.sleep(.5)
        raise RuntimeError('Backend startup timed out')
    def sql(statement, args=()):
        with db.cursor() as c:
            c.execute(statement, args)
            return c.fetchall() if c.description else []
    try:
        version = cmd([pg / 'postgres.exe', '--version']).strip()
        check('real PostgreSQL 17 runtime', ' 17.' in version)
        pw = run / 'init-password'; pw.write_text(password)
        try:
            cmd([pg / 'initdb.exe', '-D', run / 'pgdata', '-U', 'ingestion', '--pwfile=' + str(pw), '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C'])
        finally:
            pw.unlink(missing_ok=True)
        cmd([pg / 'pg_ctl.exe', '-D', run / 'pgdata', '-l', run / 'postgres.log', '-o', f'-h 127.0.0.1 -p {pg_port}', '-w', 'start'])
        pg_started = True
        cmd([pg / 'createdb.exe', '-h', '127.0.0.1', '-p', str(pg_port), '-U', 'ingestion', 'ingestion'])
        db = psycopg.connect(host='127.0.0.1', port=pg_port, dbname='ingestion', user='ingestion', password=password, autocommit=True)
        start('redis', ['redis-server', '--bind', '127.0.0.1', '--port', str(redis_port), '--save', '', '--appendonly', 'no'])
        backend = start_backend()
        token = api('/login', 'POST', {'username':'bootstrap','password':password}, auth=False)[1].get('token')
        check('administrator login', bool(token))
        check('anonymous config rejected', api('/api/v1/drafts/config', auth=False)[0] == 401)
        scene = api('/api/v1/scenes', 'POST', {'name':'ingestion-acceptance'})[1]
        scene_id = scene['id']
        create = {'requestKey':str(uuid.uuid4()),'description':'first draft'}
        path = f'/api/v1/scenes/{scene_id}/drafts'
        code, draft = api(path, 'POST', create)
        check('create scene draft', code == 200 and draft['sceneId'] == scene_id)
        draft_id = draft['id']; dp = '/api/v1/drafts/' + draft_id
        check('draft create retry is idempotent', api(path,'POST',create)[1]['id'] == draft_id and api(path)[1]['total'] == 1)
        check('missing scene draft rejected', api('/api/v1/scenes/'+str(uuid.uuid4())+'/drafts','POST',create)[0] == 404)
        gone = api('/api/v1/scenes','POST',{'name':'deleted-scene'})[1]
        api('/api/v1/scenes/'+gone['id']+'?expectedVersion=0','DELETE')
        check('deleted scene draft rejected', api('/api/v1/scenes/'+gone['id']+'/drafts','POST',create)[0] == 404)
        check('edit draft description', api(dp,'PUT',{'description':'updated','expectedVersion':0})[1]['description']=='updated')
        check('stale edit rejected', api(dp,'PUT',{'description':'stale','expectedVersion':0})[0] == 409)
        def register(name, data, **overrides):
            body = dict(requestKey=str(uuid.uuid4()),fileName=name,kind='RESOURCE_FILE',bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            body.update(overrides)
            return api(dp+'/files','POST',body), body
        def upload(record, data):
            return api(dp+'/files/'+record['id']+'/content','PUT',data,raw=True)
        def current(record):
            return sql('select status from ar_draft_file where id=%s',(record['id'],))[0][0]
        a = b'first synthetic resource\n'; b = b'second resource\x00\x01'
        (code, first), meta = register('first.bin',a)
        check('register pending file', code == 200 and first['status']=='PENDING')
        check('registration retry returns same row', api(dp+'/files','POST',meta)[1]['id'] == first['id'])
        check('idempotency key metadata conflict', api(dp+'/files','POST',{**meta,'bytes':len(a)+1})[0]==409)
        check('first upload available', upload(first,a)[1]['status']=='AVAILABLE')
        check('duplicate content submission stays available', upload(first,a)[1]['status']=='AVAILABLE')
        (code, second), _ = register('second.bin',b)
        check('second different file available', upload(second,b)[1]['status']=='AVAILABLE')
        check('two files associated with one draft', api(dp+'/files')[1]['total']==2)
        for record,data in ((first,a),(second,b)):
            actual=(run/'artifacts/committed'/record['storageKey']).read_bytes()
            check('formal storage bytes and SHA256 '+record['fileName'],len(actual)==len(data) and hashlib.sha256(actual).digest()==hashlib.sha256(data).digest())
        check('oversized declaration rejected', register('oversize.bin',b'',bytes=4*1024*1024+1)[0][0]==413)
        (_, mismatch), _=register('mismatch.bin',a,sha256='0'*64)
        check('digest mismatch rejected and not available', upload(mismatch,a)[0]==422 and current(mismatch)=='FAILED')
        (_, oversized), _=register('actual-too-large.bin',a)
        check('actual size exceeds declaration rejected', upload(oversized,a+b)[0]==422 and current(oversized)=='FAILED')
        check('failure reason identifies digest mismatch', 'SHA256' in sql('select failure_reason from ar_draft_file where id=%s',(mismatch['id'],))[0][0])
        check('failed files absent from formal storage', not (run/'artifacts/committed'/mismatch['storageKey']).exists() and not (run/'artifacts/committed'/oversized['storageKey']).exists())
        check('AAR requires client library category', register('sample.aar',a)[0][0]==400)
        (_, aar), _=register('sample.aar',a,kind='CLIENT_LIBRARY')
        check('AAR registered only as client library', upload(aar,a)[1]['kind']=='CLIENT_LIBRARY')
        (_, removed), removed_meta=register('remove-me.bin',a)
        upload(removed,a)
        remove_path=dp+'/files/'+removed['id']
        check('anonymous file removal rejected',api(remove_path,'DELETE',auth=False)[0]==401)
        check('wrong draft cannot remove file',api('/api/v1/drafts/'+str(uuid.uuid4())+'/files/'+removed['id'],'DELETE')[0]==404)
        check('remove uploaded file',api(remove_path,'DELETE')[0]==204)
        check('repeat removal is idempotent',api(remove_path,'DELETE')[0]==204)
        check('removed file hidden from list',removed['id'] not in [x['id'] for x in api(dp+'/files')[1]['items']])
        check('physical deletion removes formal bytes',not (run/'artifacts/committed'/removed['storageKey']).exists())
        check('physical deletion removes file row',sql('select count(*) from ar_draft_file where id=%s',(removed['id'],))[0][0]==0)
        check('removed file cannot upload',upload(removed,a)[0]==404)
        check('old registration key cannot resurrect file',api(dp+'/files','POST',removed_meta)[0]==410)
        (_, replacement), _=register('remove-me.bin',a)
        check('new registration can readd removed file',replacement['id']!=removed['id'] and upload(replacement,a)[1]['status']=='AVAILABLE')
        check('removal audit is attributable and singular',sql("select count(*) from ar_audit where action='FILE_DELETE' and detail->>'fileId'=%s and actor_name='bootstrap'",(removed['id'],))[0][0]==1)
        check('failed file can be removed',api(dp+'/files/'+oversized['id'],'DELETE')[0]==204)
        empty={'requestKey':str(uuid.uuid4()),'description':'empty-to-delete'}
        empty_id=api(path,'POST',empty)[1]['id']
        check('anonymous draft removal rejected',api('/api/v1/drafts/'+empty_id,'DELETE',auth=False)[0]==401)
        check('remove empty draft',api('/api/v1/drafts/'+empty_id,'DELETE')[0]==204)
        check('repeat draft removal is idempotent',api('/api/v1/drafts/'+empty_id,'DELETE')[0]==204)
        check('removed draft hidden from list',empty_id not in [x['id'] for x in api(path)[1]['items']])
        packed={'requestKey':str(uuid.uuid4()),'description':'packed-to-delete'}
        packed_id=api(path,'POST',packed)[1]['id']
        packed_path='/api/v1/drafts/'+packed_id
        packed_body=dict(requestKey=str(uuid.uuid4()),fileName='packed.bin',kind='RESOURCE_FILE',bytes=len(a),sha256=hashlib.sha256(a).hexdigest())
        packed_file=api(packed_path+'/files','POST',packed_body)[1]
        check('packed draft file available',api(packed_path+'/files/'+packed_file['id']+'/content','PUT',a,raw=True)[1]['status']=='AVAILABLE')
        packed_key=packed_file['storageKey']
        check('remove draft with files',api(packed_path,'DELETE')[0]==204)
        check('removed draft row gone',sql('select count(*) from ar_draft where id=%s',(packed_id,))[0][0]==0)
        check('removed draft files physically gone',sql('select count(*) from ar_draft_file where draft_id=%s',(packed_id,))[0][0]==0 and not (run/'artifacts/committed'/packed_key).exists())
        check('removed draft cannot be edited',api(packed_path,'PUT',{'description':'gone','expectedVersion':0})[0]==404)
        check('draft deletion audit is attributable',sql("select count(*) from ar_audit where action='DRAFT_DELETE' and detail->>'draftId'=%s and actor_name='bootstrap'",(packed_id,))[0][0]==1)
        check('same request key can create a new draft after deletion',api(path,'POST',packed)[1]['id']!=packed_id)
        (_, pending_removal), _=register('pending-removal.bin',a)
        check('pending file can be removed',api(dp+'/files/'+pending_removal['id'],'DELETE')[0]==204)
        # Inject a non-regular storage target so delete fails without deleting the DB row.
        (_, delete_failure), _=register('delete-failure.bin',a)
        blocked=run/'artifacts/committed'/delete_failure['storageKey']
        blocked.mkdir()
        check('storage deletion failure reports 503',api(dp+'/files/'+delete_failure['id'],'DELETE')[0]==503)
        failing=next(x for x in api(dp+'/files')[1]['items'] if x['id']==delete_failure['id'])
        check('failed deletion stays visible and retryable',failing['status']=='DELETE_FAILED' and bool(failing['failureReason']))
        check('deletion in progress rejects upload',upload(delete_failure,a)[0]==404)
        blocked.rmdir()
        check('failed deletion retry completes',api(dp+'/files/'+delete_failure['id'],'DELETE')[0]==204 and not sql('select id from ar_draft_file where id=%s',(delete_failure['id'],)))
        # Durable intent snapshots at both crash boundaries (before unlink / after unlink).
        recovery_ids=[]
        for stage in ('before-unlink','after-unlink'):
            (_, item), _=register(stage+'.bin',a)
            upload(item,a)
            sql("insert into ar_file_deletion(file_id,draft_id,request_key,actor_id,actor_name) select id,draft_id,request_key,creator_id,creator_name from ar_draft_file where id=%s",(item['id'],))
            if stage=='after-unlink':(run/'artifacts/committed'/item['storageKey']).unlink()
            recovery_ids.append(item)
        # Existing logical removals must not be physically purged without explicit selection.
        (_, legacy), _=register('legacy-removal.bin',a)
        upload(legacy,a)
        sql('update ar_draft_file set removed_at=now(),removed_by=creator_id where id=%s',(legacy['id'],))
        (_, interrupted), _=register('interrupted.bin',a*5000)
        def begin_partial(record, data):
            sock=socket.create_connection(('127.0.0.1',api_port),timeout=10)
            head=f"PUT {dp}/files/{record['id']}/content HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {token}\r\nContent-Type: application/octet-stream\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n"
            sock.sendall(head.encode()+data[:32])
            until=time.monotonic()+10
            while current(record)!='UPLOADING' and time.monotonic()<until: time.sleep(.05)
            check('partial request durably marked uploading',current(record)=='UPLOADING')
            return sock
        sock=begin_partial(interrupted,a*5000)
        check('active upload cannot be removed',api(dp+'/files/'+interrupted['id'],'DELETE')[0]==409)
        check('active upload blocks draft deletion',api(dp,'DELETE')[0]==409)
        check('concurrent upload rejected without false success',upload(interrupted,a*5000)[0]==409)
        sock.shutdown(socket.SHUT_RDWR);sock.close()
        until=time.monotonic()+10
        while current(interrupted)=='UPLOADING' and time.monotonic()<until: time.sleep(.05)
        check('disconnected upload marked failed',current(interrupted)=='FAILED')
        check('interrupted upload retry succeeds with same file id',upload(interrupted,a*5000)[1]['id']==interrupted['id'] and current(interrupted)=='AVAILABLE')
        (_, crash), _=register('crash.bin',a*6000)
        crash_socket=begin_partial(crash,a*6000)
        (_, staged), _=register('staged.bin',b)
        (run/'artifacts/staging'/(staged['id']+'.ready')).write_bytes(b)
        (_, ack), _=register('ack-lost.bin',a)
        (run/'artifacts/committed'/ack['storageKey']).write_bytes(a)
        (_, pending), _=register('pending.bin',b)
        backend.kill();backend.wait(timeout=15);crash_socket.close()
        check('hard-stopped service retains unfinished record',current(crash)=='UPLOADING')
        backend=start_backend()
        check('restart does not restore removed files',removed['id'] not in [x['id'] for x in api(dp+'/files')[1]['items']] and sql('select count(*) from ar_draft_file where id=%s',(removed['id'],))[0][0]==0 and not (run/'artifacts/committed'/removed['storageKey']).exists())
        check('restart completes interrupted physical deletions',all(not sql('select id from ar_draft_file where id=%s',(x['id'],)) and not (run/'artifacts/committed'/x['storageKey']).exists() and sql('select completed_at is not null from ar_file_deletion where file_id=%s',(x['id'],))[0][0] for x in recovery_ids))
        check('legacy removals not purged automatically',(run/'artifacts/committed'/legacy['storageKey']).exists() and bool(sql('select id from ar_draft_file where id=%s',(legacy['id'],))))
        check('completed files remain available after restart',current(first)=='AVAILABLE' and current(second)=='AVAILABLE')
        check('restart identifies incomplete upload',current(crash)=='FAILED' and current(pending)=='FAILED')
        check('restart reconciles ready and committed files',current(staged)=='AVAILABLE' and current(ack)=='AVAILABLE')
        check('explicit legacy deletion clears bytes and row',api(dp+'/files/'+legacy['id'],'DELETE')[0]==204 and not (run/'artifacts/committed'/legacy['storageKey']).exists() and not sql('select id from ar_draft_file where id=%s',(legacy['id'],)))
        check('retry after service restart succeeds',upload(crash,a*6000)[1]['status']=='AVAILABLE')
        check('no duplicate registration after retries',sql('select count(*) from ar_draft_file where draft_id=%s and request_key=%s',(draft_id,meta['requestKey']))[0][0]==1)
        actor=api('/getInfo')[1]['user']['userId']
        check('audit identifies actor draft and file',sql("select count(*) from ar_audit where actor_id=%s and detail->>'draftId'=%s and detail->>'fileId'=%s and action='FILE_AVAILABLE'",(actor,draft_id,first['id']))[0][0]==1)
        check('reconciliation audit marks system action',sql("select count(*) from ar_audit where detail->>'draftId'=%s and detail->>'performedBy'='SYSTEM_RECONCILIATION'",(draft_id,))[0][0]>=4)
        check('anonymous upload rejected',api(dp+'/files/'+first['id']+'/content','PUT',a,auth=False,raw=True)[0]==401)
        # A real authenticated account with no administrator role.
        api('/system/user','POST',{'userName':'nonadmin','nickName':'nonadmin','password':password})
        uid=sql("select user_id from sys_user where user_name='nonadmin'")[0][0]
        sql('delete from sys_user_role where user_id=%s',(uid,))
        admin_token=token
        token=api('/login','POST',{'username':'nonadmin','password':password},auth=False)[1].get('token')
        check('nonadministrator authenticated',bool(token))
        check('nonadministrator removal forbidden',api(dp+'/files/'+first['id'],'DELETE')[0]==403)
        check('nonadministrator draft removal forbidden',api(dp,'DELETE')[0]==403)
        check('nonadministrator draft access forbidden',api(dp)[0]==403 and api(path,'POST',create)[0]==403)
        # Account creation intentionally retires bootstrap in the application. Restore only this
        # synthetic isolated account for the subsequent browser checks, then obtain a fresh token.
        sql("update sys_user set status='0',del_flag='0' where user_name='bootstrap'")
        token=api('/login','POST',{'username':'bootstrap','password':password},auth=False)[1].get('token')
        check('fresh administrator session for browser',bool(token))
        start('vite',['node',ROOT/'frontend/node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',str(web_port),'--strictPort'],ROOT/'frontend')
        web=f'http://127.0.0.1:{web_port}'
        until=time.monotonic()+30
        while time.monotonic()<until:
            try:
                urllib.request.urlopen(web,timeout=1).close();break
            except OSError: time.sleep(.3)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':1500,'height':1050})
            context.add_cookies([{'name':'Admin-Token','value':token,'url':web}])
            page=context.new_page()
            page.on('pageerror',lambda e: print('BROWSER ERROR',str(e),flush=True))
            page.goto(web+'/admin/scenes')
            row=page.get_by_role('row').filter(has_text='ingestion-acceptance')
            row.get_by_role('button',name='编辑',exact=True).click()
            page.get_by_role('button',name='版本草稿与文件',exact=True).click()
            page.get_by_placeholder('填写版本说明（可留空）').fill('browser draft')
            page.get_by_role('button',name='创建草稿',exact=True).click()
            page.get_by_role('heading',name='草稿文件',exact=False).wait_for()
            payloads=[{'name':'browser-one.bin','mimeType':'application/octet-stream','buffer':a},{'name':'browser-two.bin','mimeType':'application/octet-stream','buffer':b*(200000)}]
            page.locator('input[type=file]').set_input_files(payloads)
            page.get_by_role('row').filter(has_text='browser-two.bin').get_by_text('已校验入库',exact=True).wait_for(timeout=30000)
            check('browser creates draft and uploads two files',page.get_by_role('row').filter(has_text='browser-one.bin').get_by_text('已校验入库',exact=True).count()==1)
            browser_draft=page.url.split('draftId=')[1].split('&')[0]
            check('browser multi-chunk hash matches original',sql("select expected_sha256,verified_bytes from ar_draft_file where draft_id=%s and file_name='browser-two.bin'",(browser_draft,))[0]==(hashlib.sha256(b*200000).hexdigest(),len(b)*200000))
            page.reload()
            page.get_by_role('row').filter(has_text='browser-two.bin').get_by_text('已校验入库',exact=True).wait_for()
            check('browser refresh preserves selected draft and files',page.get_by_role('row').filter(has_text='browser-one.bin').count()==1)
            page.locator('input[type=file]').set_input_files(payloads[0])
            page.get_by_role('status').filter(has_text='已校验入库').wait_for(timeout=30000)
            check('browser repeated file selection does not duplicate row',page.get_by_role('row').filter(has_text='browser-one.bin').count()==1)
            row=page.get_by_role('row').filter(has_text='browser-one.bin')
            original_id=sql("select id::text from ar_draft_file where draft_id=%s and file_name='browser-one.bin' and removed_at is null",(browser_draft,))[0][0]
            row.get_by_role('button',name='删除',exact=True).click()
            page.get_by_role('button',name='取消',exact=True).click()
            check('browser cancellation keeps file',sql('select removed_at is null from ar_draft_file where id=%s',(original_id,))[0][0])
            row.get_by_role('button',name='删除',exact=True).click()
            page.get_by_role('button',name='永久删除',exact=True).click()
            row.wait_for(state='hidden')
            page.reload()
            page.get_by_role('row').filter(has_text='browser-two.bin').wait_for()
            check('browser removal remains hidden after refresh',page.get_by_role('row').filter(has_text='browser-one.bin').count()==0)
            page.locator('input[type=file]').set_input_files(payloads[0])
            page.get_by_role('row').filter(has_text='browser-one.bin').get_by_text('已校验入库',exact=True).wait_for(timeout=30000)
            check('browser can explicitly readd removed file',sql("select count(*) from ar_draft_file where draft_id=%s and file_name='browser-one.bin' and removed_at is null",(browser_draft,))[0][0]==1 and not (run/'artifacts/committed'/(original_id+'.bin')).exists())
            draft_row=page.get_by_role('row').filter(has_text=browser_draft)
            draft_row.get_by_role('button',name='删除',exact=True).click()
            page.get_by_role('button',name='取消',exact=True).click()
            check('browser cancellation keeps draft',sql('select count(*) from ar_draft where id=%s',(browser_draft,))[0][0]==1)
            draft_row.get_by_role('button',name='删除',exact=True).click()
            page.get_by_role('button',name='永久删除',exact=True).click()
            draft_row.wait_for(state='hidden')
            check('browser draft removal hides row and files',sql('select count(*) from ar_draft where id=%s',(browser_draft,))[0][0]==0 and sql('select count(*) from ar_draft_file where draft_id=%s',(browser_draft,))[0][0]==0)
            page.screenshot(path=str(run/'browser.png'),full_page=True)
            page.goto(web+'/admin/scenes?draftScene='+scene_id+'&draftId='+draft_id)
            page.get_by_role('row').filter(has_text='mismatch.bin').get_by_text('失败',exact=True).wait_for()
            check('browser shows failure reason and retry action',page.get_by_role('row').filter(has_text='mismatch.bin').get_by_text('SHA256',exact=False).count()>0 and page.get_by_role('row').filter(has_text='mismatch.bin').get_by_role('button',name='重新选择原文件').count()==1)
            browser.close()
        report={'passed':True,'postgres':version,'runtime':'isolated native PostgreSQL 17 / Redis / Spring Boot / Vite / Edge',
                'checks':CHECKS,'limitations':['No Addressables/client-loading validation','No power-loss or disk-full injection','Nginx container route not exercised by this native test']}
        (ROOT/'docs/validation-ingestion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:
        (run/'checks.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2),encoding='utf-8')
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=15)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        if db:db.close()
        if pg_started:cmd([pg/'pg_ctl.exe','-D',run/'pgdata','-m','fast','-w','stop'])
        for log in logs:log.close()
        print('Evidence directory:',run,flush=True)

if __name__=='__main__':
    main()
