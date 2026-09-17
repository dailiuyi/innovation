"""Verify an empty dedicated database, then restart the same application/database."""
import json
import os
import subprocess
import time
import uuid
import urllib.request
import urllib.error
import psycopg
from verify_framework import ROOT,CONFIG

local=ROOT/'.local'
name='ar_init_'+uuid.uuid4().hex[:10]
conn=psycopg.connect(host='127.0.0.1',port=15432,dbname='postgres',user='ar_demo',password=CONFIG['AR_DATABASE_PASSWORD'],autocommit=True)
conn.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
conn.close()
env=dict(os.environ,**CONFIG)
env['AR_PORT']='18081'
env['AR_REDIS_DATABASE']='1'
env['AR_DATABASE_URL']='jdbc:postgresql://127.0.0.1:15432/'+name
java=next((local/'java21').glob('jdk*'))/'bin/java.exe'
counts=[]
for attempt in range(2):
    with (local/'initialization.log').open('ab') as log:
        process=subprocess.Popen([str(java),'-Duser.timezone=UTC','-jar',str(ROOT/'backend/ruoyi-admin/target/ruoyi-admin.jar')],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(60):
            if process.poll() is not None: raise AssertionError('Initialization process exited; inspect .local/initialization.log')
            try:
                with urllib.request.urlopen('http://127.0.0.1:18081/captchaImage',timeout=1) as r:
                    if r.status==200: break
            except OSError: time.sleep(.5)
        else: raise AssertionError('Initialization timeout')
        # HTTP readiness can precede ApplicationRunner by milliseconds.
        time.sleep(.4)
        db=psycopg.connect(host='127.0.0.1',port=15432,dbname=name,user='ar_demo',password=CONFIG['AR_DATABASE_PASSWORD'])
        row=[db.execute('select count(*) from '+table).fetchone()[0] for table in ('flyway_schema_history','sys_user','sys_menu','sys_role','ar_scene')]
        counts.append(row);db.close()
    finally:
        process.terminate();process.wait(timeout=20)
assert counts[0]==counts[1] and counts[0][1]==1 and counts[0][-1]==0,counts
(ROOT/'docs/validation-initialization.json').write_text(json.dumps({'passed':True,'database':name,'postgresql':'17.6','firstStart':counts[0],'secondStart':counts[1],'columns':['migrations','users','menus','roles','scenes'],'note':'Dedicated database retained in local test cluster.'},indent=2),encoding='utf-8')
print('PASS empty database initialization and repeat startup')
