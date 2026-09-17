"""HTTP verification against the isolated local demo. Never prints credentials."""
import json
import base64
import subprocess
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / '.local/demo-secrets.json').read_text())
BASE = 'http://127.0.0.1:18080'
results = []
def call(path, method='GET', body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    req=urllib.request.Request(BASE+path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content=resp.read()
            return resp.status,json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        try: return e.code,json.loads(e.read())
        except ValueError: return e.code,{}
def check(name, condition):
    results.append({'name':name,'passed':bool(condition)})
    if not condition: raise AssertionError(name)
    print('PASS', name)
def login(name,password):
    status,data=call('/login','POST',{'username':name,'password':password})
    if 'token' not in data: raise AssertionError('Login failed: '+str(data.get('msg')))
    return data['token']

if __name__ == '__main__':
    for attempt in range(30):
        try:
            call('/captchaImage'); break
        except OSError: time.sleep(1)
    account_file=ROOT/'.local/test-accounts.json'
    if account_file.exists():
        accounts=json.loads(account_file.read_text())
    else:
        accounts={name:secrets.token_urlsafe(18) for name in ('demo_a','demo_b')}
        bootstrap=login('bootstrap',CONFIG['AR_BOOTSTRAP_PASSWORD'])
        status,data=call('/system/user','POST',{'userName':'demo_a','nickName':'演示管理员 A','password':accounts['demo_a'],'roleIds':[1]},bootstrap)
        check('create fixed-role administrator',data.get('code')==200)
        check('bootstrap retired after first administrator',call('/getInfo',token=bootstrap)[0]==401)
        token=login('demo_a',accounts['demo_a'])
        status,data=call('/system/user','POST',{'userName':'demo_b','nickName':'演示管理员 B','password':accounts['demo_b']},token)
        check('create second administrator',data.get('code')==200)
        account_file.write_text(json.dumps(accounts))
    a=login('demo_a',accounts['demo_a']); b=login('demo_b',accounts['demo_b'])
    check('wrong password rejected',call('/login','POST',{'username':'demo_a','password':'wrong-password'})[1].get('code')!=200)
    check('anonymous denied',call('/getInfo')[0]==401)
    check('equal roles and permissions', all(call('/getInfo',token=a)[1][k]==call('/getInfo',token=b)[1][k] for k in ('roles','permissions')))
    check('routers load',len(call('/getRouters',token=a)[1].get('data',[]))>0)
    data=call('/system/user/list?pageNum=1&pageSize=1',token=a)[1]
    check('user pagination',len(data.get('rows',[]))==1 and data.get('total',0)>=3)
    for path in ('/monitor/logininfor/list','/monitor/operlog/list'):
        check(path+' PostgreSQL query',call(path,token=a)[1].get('code')==200)
        check(path+' date filter',call(path+'?params%5BbeginTime%5D=2020-01-01&params%5BendTime%5D=2030-01-01',token=a)[1].get('code')==200)
    for path,method in (('/register','POST'),('/system/role/list','GET'),('/common/upload','POST'),('/system/user/102','DELETE'),('/tool/gen/list','GET')):
        status,data=call(path,method,token=a)
        check(path+' denied',status in (401,403) or data.get('code') in (401,403))
    users=call('/system/user/list',token=a)[1]['rows']; ids={u['userName']:u['userId'] for u in users}
    call('/system/user/changeStatus','PUT',{'userId':ids['demo_b'],'status':'1'},a)
    check('disabled token rejected',call('/getInfo',token=b)[0]==401)
    check('last administrator protected',call('/system/user/changeStatus','PUT',{'userId':ids['demo_a'],'status':'1'},a)[1].get('code')!=200)
    call('/system/user/changeStatus','PUT',{'userId':ids['demo_b'],'status':'0'},a)
    b=login('demo_b',accounts['demo_b'])
    replacement=secrets.token_urlsafe(18)
    check('password reset succeeds',call('/system/user/resetPwd','PUT',{'userId':ids['demo_b'],'password':replacement},a)[1].get('code')==200)
    accounts['demo_b']=replacement; account_file.write_text(json.dumps(accounts))
    check('old token after password reset rejected',call('/getInfo',token=b)[0]==401)
    b=login('demo_b',replacement)
    call('/logout','POST',token=b)
    check('logout token rejected',call('/getInfo',token=b)[0]==401)
    expiring=login('demo_b',replacement)
    payload=expiring.split('.')[1]
    session_id=json.loads(base64.urlsafe_b64decode(payload+'='*((-len(payload))%4)))['login_user_key']
    subprocess.run(['C:/Program Files/Redis/redis-cli.exe','-p','16379','PEXPIRE','login_tokens:'+session_id,'1'],stdout=subprocess.DEVNULL,check=True)
    time.sleep(.05)
    check('expired Redis credential rejected',call('/getInfo',token=expiring)[0]==401)
    b=login('demo_b',replacement)
    own=secrets.token_urlsafe(18)
    check('own password change succeeds',call('/system/user/profile/updatePwd','PUT',{'oldPassword':replacement,'newPassword':own},b)[1].get('code')==200)
    accounts['demo_b']=own;account_file.write_text(json.dumps(accounts))
    check('own password revokes current token',call('/getInfo',token=b)[0]==401)
    check('profile and users do not expose password hashes','password' not in call('/getInfo',token=a)[1]['user'] and all('password' not in u for u in users))
    report={'stage':'framework','database':'PostgreSQL 17.6','checks':results}
    (ROOT/'docs/validation-framework.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
