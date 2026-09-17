"""Authoring source for the Utopia V0.1 API."""
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]

def obj(properties, required=None):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties,
            'required': list(properties) if required is None else required}

def string(**kw): return dict(type='string', **kw)
def integer(**kw): return dict(type='integer', **kw)
def enum(*values): return string(enum=list(values))
def array(items, **kw): return dict(type='array', items=items, **kw)
def ref(name): return {'$ref': '#/components/schemas/' + name}

uuid = string(format='uuid')
platform = enum('ANDROID', 'IOS', 'MINIPROGRAM')
variant = enum('DAY', 'NIGHT')
sha = string(pattern='^[0-9a-f]{64}$')
position = array({'type': 'number'}, minItems=3, maxItems=3)
rotation = array({'type': 'number'}, minItems=4, maxItems=4)
playback = obj({'mode': enum('LOCAL_INDEPENDENT'), 'durationMs': integer(minimum=0),
                'recoveryPolicy': enum('RESUME_LOCAL_TIME', 'RESTART')})
package = obj({'format': string(minLength=1), 'runtimeVersion': string(minLength=1),
               'minClientBuild': integer(minimum=1), 'maxClientBuild': integer(minimum=1),
               'entrypoint': string(minLength=1)}, ['format', 'runtimeVersion', 'minClientBuild', 'entrypoint'])
packages = obj({p: package for p in platform['enum']}, [])
packages.pop('required')
packages['minProperties'] = 1
file_descriptor = obj({'assetId': uuid, 'logicalPath': string(minLength=1), 'sha256': sha,
                       'bytes': integer(format='int64', minimum=1),
                       'url': string(format='uri', pattern='^https://'), 'expiresAt': string(format='date-time')})
manifest = obj({'schemaVersion': integer(enum=[1]), 'sceneId': uuid, 'versionId': uuid,
                'versionNo': integer(minimum=1), 'variant': variant, 'platform': platform,
                'format': string(minLength=1), 'runtimeVersion': string(minLength=1),
                'clientBuildRange': obj({'min': integer(minimum=1), 'max': integer(minimum=1)}, ['min']),
                'coordinateSystem': enum('scene-local-v1'),
                'markers': array(obj({'markerId': uuid, 'widthMeters': {'type': 'number', 'minimum': 0.000001},
                     'heightMeters': {'type': 'number', 'minimum': 0.000001},
                     'sceneFromMarker': obj({'position': position, 'rotation': rotation})}), minItems=1),
                'files': array(file_descriptor, minItems=1, maxItems=1000),
                'entrypoint': string(minLength=1), 'playback': playback})
manifest.update({'$schema': 'https://json-schema.org/draft/2020-12/schema',
                 '$id': 'https://schemas.example.invalid/utopia/runtime-manifest-v1.json'})
schemas = {
    'Error': obj({'code': string(), 'message': string(), 'traceId': string()}),
    'Csrf': obj({'headerName': enum('X-CSRF-TOKEN'), 'token': string()}),
    'Login': obj({'username': string(minLength=1), 'password': string(minLength=1)}),
    'Me': obj({'id': uuid, 'displayName': string()}),
    'Resource': obj({'id': uuid}),
    'SceneCreate': obj({'name': string(minLength=1, maxLength=200), 'address': string(),
                       'longitude': {'type': 'number', 'minimum': -180, 'maximum': 180},
                       'latitude': {'type': 'number', 'minimum': -90, 'maximum': 90},
                       'geoCrs': enum('WGS84', 'GCJ02', 'BD09')}, ['name']),
    'SceneView': obj({'id': uuid, 'name': string(), 'lockVersion': integer(minimum=0), 'enabled': {'type': 'boolean'},
                     'currentDayVersionId': string(format='uuid', nullable=True),
                     'currentNightVersionId': string(format='uuid', nullable=True)}),
    'SceneList': obj({'items': array(ref('SceneView'))}),
    'MarkerCreate': obj({'sceneId': uuid, 'widthMeters': {'type': 'number', 'minimum': 0.000001},
                         'heightMeters': {'type': 'number', 'minimum': 0.000001}, 'position': position, 'rotation': rotation}),
    'MarkerView': obj({'id': uuid, 'code': string(), 'sceneId': uuid}),
    'EnabledUpdate': obj({'enabled': {'type': 'boolean'}, 'expectedVersion': integer(minimum=0), 'reason': string(minLength=1)}),
    'MarkerEnabled': obj({'enabled': {'type': 'boolean'}, 'reason': string(minLength=1)}),
    'VersionCreate': obj({'id': uuid, 'variant': variant}),
    'VersionView': obj({'id': uuid, 'sceneId': uuid, 'variant': variant, 'versionNo': integer(minimum=1),
                        'state': enum('DRAFT', 'READY', 'REVOKED'), 'lockVersion': integer(minimum=0)}),
    'DraftUpdate': obj({'expectedVersion': integer(minimum=0), 'packages': packages, 'playback': playback,
                       'note': string(), 'files': array(obj({'assetId': uuid, 'platform': platform,
                                                            'logicalPath': string(minLength=1)}), minItems=1, maxItems=1000)}),
    'ExpectedVersion': obj({'expectedVersion': integer(minimum=0)}),
    'Reason': obj({'reason': string(minLength=1, maxLength=1000)}),
    'Publish': obj({'variant': variant, 'versionId': string(format='uuid', nullable=True),
                    'expectedVersion': integer(minimum=0), 'reason': string(minLength=1, maxLength=1000)}),
    'UploadRequest': obj({'id': uuid, 'kind': enum('CAPTURE','GS','MODEL','TEXTURE','AUDIO','TIMELINE','BUNDLE','MANIFEST','OTHER'),
                         'contentType': string(minLength=1), 'bytes': integer(format='int64', minimum=1), 'sha256': sha}),
    'UploadIntent': obj({'assetId': uuid, 'uploadUrl': string(format='uri'), 'method': enum('PUT'),
                        'headers': {'type': 'object', 'additionalProperties': string()}, 'expiresAt': string(format='date-time')}),
    'UploadComplete': obj({'objectVersion': string(minLength=1)}),
    'AssetView': obj({'id': uuid, 'state': enum('PENDING','READY','REJECTED','REVOKED')}),
    'RuntimeManifest': {k: v for k, v in manifest.items() if not k.startswith('$')},
}
paths = {}
schemas['VersionList'] = obj({'items': array(ref('VersionView'))})
view_packages = dict(packages)
view_packages.pop('minProperties')
schemas['VersionDetail'] = obj(dict(schemas['VersionView']['properties'], packages=view_packages,
    playback=playback, note=string(), files=array(obj({'assetId': uuid, 'platform': platform,
                                                    'logicalPath': string(minLength=1)}))))

def add(path, method, operation, summary, request=None, response=None, status='200', public=False, description='', query=None):
    import re
    params = [{'name': n, 'in': 'path', 'required': True, 'schema': integer(format='int64') if n=='operId' else string() if n in ('code','dictType') else uuid}
              for n in re.findall(r'\{([^}]+)\}', path)]
    params.extend(query or [])
    responses = {status: {'description': 'Success'}}
    if response: responses[status]['content'] = {'application/json': {'schema': ref(response)}}
    for code in ('400','401','403','404','409','413','429','503'):
        responses[code] = {'description': 'Request failed; 409 covers state/version conflict or incompatible client',
                           'content': {'application/json': {'schema': ref('Error')}}}
    op = {'operationId': operation, 'summary': summary, 'description': description or summary,
          'security': [] if public else [{'bearerAuth': []}], 'parameters': params, 'responses': responses,
          'x-implementation': 'candidate'}
    if request:
        mime = 'application/json'
        op['requestBody'] = {'required': True, 'content': {mime: {'schema': ref(request)}}}
    paths.setdefault(path, {})[method] = op

def query(name, schema, required=True): return {'name': name, 'in': 'query', 'required': required, 'schema': schema}

add('/api/v1/scenes','post','createScene','创建场景（包含地点信息）','SceneCreate','SceneView','201')
add('/api/v1/scenes','get','listScenes','列出场景',response='SceneList',
    query=[query('limit',integer(minimum=1,maximum=100,default=20),False),query('offset',integer(minimum=0,default=0),False)])
add('/api/v1/scenes/{sceneId}','get','getScene','查看场景和当前昼夜版本',response='SceneView')
add('/api/v1/scenes/{sceneId}/enabled','put','setSceneEnabled','启用或禁用场景','EnabledUpdate','SceneView')
add('/api/v1/markers','post','createMarker','创建固定坐标的现场标记','MarkerCreate','MarkerView','201')
add('/api/v1/markers/{markerId}/enabled','put','setMarkerEnabled','启用或禁用现场标记','MarkerEnabled','Resource')
add('/api/v1/scenes/{sceneId}/versions','post','createVersion','创建昼夜草稿','VersionCreate','VersionView','201',
    description='客户端生成稳定UUID作为id；同id同scene/variant返回原版本，不同参数409。服务端锁scene行分配versionNo。')
add('/api/v1/scenes/{sceneId}/versions','get','listVersions','查看历史版本以选择回滚目标',response='VersionList',
    query=[query('variant',variant,False),query('limit',integer(minimum=1,maximum=100,default=20),False),
           query('offset',integer(minimum=0,default=0),False)])
add('/api/v1/versions/{versionId}','get','getVersion','查询版本状态、配置和文件',response='VersionDetail')
add('/api/v1/versions/{versionId}','put','updateDraft','原子替换草稿配置和文件','DraftUpdate','VersionView')
add('/api/v1/versions/{versionId}/ready','post','sealVersion','校验并冻结版本','ExpectedVersion','VersionView')
add('/api/v1/versions/{versionId}/revoke','post','revokeVersion','撤销问题版本','Reason','VersionView')
add('/api/v1/scenes/{sceneId}/publish','put','publishVersion','发布、回滚或下线一个昼夜版本','Publish','SceneView',
    description='versionId=null为下线；expectedVersion是scene.lockVersion。切换指针与审计同事务；冲突409后重新读取，不盲目覆盖。')
add('/api/v1/assets/uploads','post','createUpload','登记文件并申请对象存储直传','UploadRequest','UploadIntent','201',
    description='id稳定；重复登记比较文件元数据，相同复用PENDING资产并重新签发凭证，不同409。只有staging写权限。')
add('/api/v1/assets/{assetId}/complete','post','completeUpload','同步校验上传文件并登记为可用','UploadComplete','AssetView',
    description='有界校验在DB事务外执行；固定对象版本、验证摘要并复制到不可覆盖final key。超时503后GET查询，PENDING可安全重试；不创建后台任务。')
add('/api/v1/assets/{assetId}','get','getAsset','查询文件是否已验证',response='AssetView')
add('/api/v1/assets/{assetId}/revoke','post','revokeAsset','撤销问题文件并记录审计','Reason','AssetView')
runtime_queries = [query('platform',platform),query('clientBuild',integer(minimum=1))]
add('/api/v1/versions/{versionId}/preview','get','previewVersion','登录后预览待发布的READY版本',response='RuntimeManifest',
    query=runtime_queries,description='READY且所有文件可用；未发布版本只允许管理员预览。')
add('/api/v1/client/markers/{code}/manifest','get','resolveManifest','游客扫码取得运行清单',response='RuntimeManifest',public=True,
    query=runtime_queries+[query('variant',variant),query('versionId',uuid,False)],
    description='不指定versionId取当前指针；指定历史版本须同scene/variant且有发布审计记录。检查scene/marker启用、文件未撤销、平台兼容；no-store。')
# Demo contracts coexist with explicitly labelled future candidate operations.
schemas.pop('Csrf')
schemas.pop('Me')
schemas['SceneCreate']['properties'].update({
    'address': string(maxLength=1000, nullable=True),
    'longitude': {'type':'number','minimum':-180,'maximum':180,'nullable':True},
    'latitude': {'type':'number','minimum':-90,'maximum':90,'nullable':True},
    'geoCrs': dict(enum('WGS84','GCJ02','BD09'),nullable=True),
})
schemas['SceneUpdate'] = obj(dict(schemas['SceneCreate']['properties'], expectedVersion=integer(minimum=0)), ['name','expectedVersion'])
schemas['SceneView'] = obj(dict(schemas['SceneCreate']['properties'], id=uuid,
    enabled={'type':'boolean'},lockVersion=integer(minimum=0),createdAt=string(format='date-time'),updatedAt=string(format='date-time')),
    ['id','name','enabled','lockVersion','createdAt','updatedAt'])
schemas['SceneList'] = obj({'items':array(ref('SceneView')),'total':integer(minimum=0)})
schemas['FrameworkResponse'] = {'type':'object','additionalProperties':True,'properties':{'code':integer(),'msg':string()}}
schemas['Login'] = obj({'username':string(),'password':string(minLength=12,maxLength=64)},['username','password'])
schemas['AccountCreate'] = obj({'userName':string(pattern='^[A-Za-z0-9_]{3,30}$'),'nickName':string(minLength=1,maxLength=30),'password':string(minLength=12,maxLength=64)})
schemas['AccountStatus'] = obj({'userId':integer(format='int64'),'status':enum('0','1')})
schemas['AccountPassword'] = obj({'userId':integer(format='int64'),'password':string(minLength=12,maxLength=64)})
schemas['OwnPassword'] = obj({'oldPassword':string(),'newPassword':string(minLength=12,maxLength=64)})
schemas['ProfileUpdate'] = obj({'nickName':string(maxLength=30),'email':string(maxLength=50),'phonenumber':string(maxLength=11),'sex':enum('0','1','2')},[])
schemas['ProfileUpdate'].pop('required')
schemas['AuditList'] = obj({'items':array({'type':'object','additionalProperties':True}),'total':integer(minimum=0)})
add('/api/v1/scenes/{sceneId}','put','updateScene','修改场景基本信息','SceneUpdate','SceneView')
add('/api/v1/audits','get','listAudits','只读场景业务审计',response='AuditList',query=[query('limit',integer(minimum=1,maximum=100,default=20),False),query('offset',integer(minimum=0,default=0),False)])
paths['/api/v1/scenes']['get']['parameters'].append(query('name',string(maxLength=200),False))
for path,method,operation,summary,request in [
    ('/login','post','login','登录；成功返回 token','Login'),
    ('/logout','post','logout','退出登录',None),
    ('/getInfo','get','getInfo','当前用户及权限',None),
    ('/getRouters','get','getRouters','当前用户菜单',None),
    ('/captchaImage','get','captchaConfig','验证码开关与挑战；本地 Demo 关闭验证码',None),
    ('/system/user/profile','get','profile','本人资料',None),
    ('/system/user/profile','put','updateProfile','修改本人资料','ProfileUpdate'),
    ('/system/user/list','get','listUsers','账号分页列表',None),
    ('/system/user','post','createUser','创建固定角色管理员','AccountCreate'),
    ('/system/user/changeStatus','put','changeUserStatus','修改账号状态','AccountStatus'),
    ('/system/user/resetPwd','put','resetPassword','重置密码并撤销旧凭证','AccountPassword'),
    ('/system/user/profile/updatePwd','put','changeOwnPassword','修改本人密码并撤销旧凭证','OwnPassword'),
    ('/monitor/logininfor/list','get','loginLogs','登录日志分页',None),
    ('/monitor/operlog/list','get','operationLogs','操作日志分页',None),
    ('/monitor/operlog/{operId}','get','operationLogDetail','操作日志详情',None),
    ('/system/dict/data/type/{dictType}','get','dictionaryValues','界面状态字典',None),
]:
    add(path,method,operation,summary,request,'FrameworkResponse',public=operation in ('login','captchaConfig'))
    paths[path][method]['x-implementation']='implemented'
    paths[path][method]['description'] += '。沿用若依 code/msg 响应；业务错误可能使用 HTTP 200。'
    for response in paths[path][method]['responses'].values():
        response['content']={'application/json':{'schema':ref('FrameworkResponse')}}
    if method=='get' and path.endswith('/list'):
        paths[path][method]['parameters'] += [query('pageNum',integer(minimum=1,default=1),False),query('pageSize',integer(minimum=1,default=20),False)]
for path in ('/api/v1/scenes','/api/v1/scenes/{sceneId}','/api/v1/scenes/{sceneId}/enabled','/api/v1/audits'):
    for operation in paths[path].values(): operation['x-implementation']='implemented'
for methods in paths.values():
    for operation in methods.values():
        operation['tags'] = ['Demo 已实现' if operation['x-implementation']=='implemented' else '候选：尚未实现']
        if operation['x-implementation']=='candidate':
            operation['description'] = '尚未实现，文件格式待确认；当前服务不开放此接口。'+operation['description']
spec = {'openapi': '3.0.3', 'info': {'title': 'AR Demo and candidate API', 'version': '0.2.0',
         'description': 'Demo: RuoYi + PostgreSQL, fixed-role administrators and scenes. Docker Compose and local ArtifactStorage infrastructure are available without artifact HTTP endpoints. Historical cloud/day-night resource and publication contracts below await a real deliverable and client loading agreement; they are not implemented.'},
        'servers': [{'url': 'https://api.example.invalid', 'description': 'placeholder'}], 'paths': paths,
        'components': {'securitySchemes': {'bearerAuth': {'type': 'http', 'scheme': 'bearer', 'bearerFormat':'JWT'}}, 'schemas': schemas}}
example = {'schemaVersion': 1, 'sceneId': '10000000-0000-4000-8000-000000000001',
           'versionId': '10000000-0000-4000-8000-000000000002', 'versionNo': 1, 'variant': 'DAY', 'platform': 'ANDROID',
           'format': 'unity-addressables', 'runtimeVersion': 'TO_BE_CONFIRMED', 'clientBuildRange': {'min': 1},
           'coordinateSystem': 'scene-local-v1', 'markers': [{'markerId': '10000000-0000-4000-8000-000000000003',
             'widthMeters': 0.2, 'heightMeters': 0.2, 'sceneFromMarker': {'position': [0,0,0], 'rotation': [0,0,0,1]}}],
           'files': [{'assetId': '10000000-0000-4000-8000-000000000004', 'logicalPath': 'catalog.json', 'sha256': 'a'*64,
                      'bytes': 1024, 'url': 'https://cdn.example.invalid/catalog.json?signature=EXAMPLE', 'expiresAt': '2026-09-14T12:10:00Z'}],
           'entrypoint': 'catalog.json', 'playback': {'mode': 'LOCAL_INDEPENDENT', 'durationMs': 60000, 'recoveryPolicy': 'RESUME_LOCAL_TIME'}}

if __name__ == '__main__':
    (ROOT/'contracts/openapi.yaml').write_text(yaml.safe_dump(spec,allow_unicode=True,sort_keys=False),encoding='utf-8')
    for path, value in [('schemas/runtime-manifest.schema.json',manifest),('examples/runtime-manifest.json',example)]:
        (ROOT/'contracts'/path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Generated',sum(len(v) for v in paths.values()),'operations')
