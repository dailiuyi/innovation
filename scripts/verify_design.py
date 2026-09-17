"""Validate generated contracts, examples, local Markdown links, and SQL/API enums."""
from pathlib import Path
import copy
import importlib.util
import json
import re
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

ROOT=Path(__file__).resolve().parents[1]
def main():
    checks=[]
    def check(name, condition=True):
        assert condition, name
        checks.append({'name':name,'passed':True})
    spec=yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text(encoding='utf-8'))
    validate(spec)
    check('OpenAPI 3.0 structural validation')
    schema=json.loads((ROOT/'contracts/schemas/runtime-manifest.schema.json').read_text(encoding='utf-8'))
    example=json.loads((ROOT/'contracts/examples/runtime-manifest.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema,format_checker=FormatChecker())
    validator.validate(example)
    check('runtime manifest Draft 2020-12 schema and example')
    paths=[f['logicalPath'] for f in example['files']]
    check('entrypoint resolves to unique file', len(paths)==len(set(paths)) and example['entrypoint'] in paths)
    for marker in example['markers']:
        check('example quaternion normalized', abs(sum(v*v for v in marker['sceneFromMarker']['rotation'])-1)<1e-5)
    for name, mutate in [
       ('unsupported platform',lambda x:x.update(platform='DESKTOP')),
       ('negative marker size',lambda x:x['markers'][0].update(widthMeters=-1)),
       ('invalid SHA256',lambda x:x['files'][0].update(sha256='invalid')),
       ('HTTP download forbidden',lambda x:x['files'][0].update(url='http://example.invalid/f')),
       ('missing version ID',lambda x:x.pop('versionId')),
       ('unexpected manifest field',lambda x:x.update(secret='bad'))]:
        changed=copy.deepcopy(example);mutate(changed)
        check('reject '+name,bool(list(validator.iter_errors(changed))))
    module_spec=importlib.util.spec_from_file_location('contract_source',ROOT/'scripts/generate_contracts.py')
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    check('OpenAPI matches authoring source',spec==module.spec)
    check('manifest schema matches authoring source',schema==module.manifest)
    check('manifest example matches authoring source',example==module.example)
    operations=[]
    for path,methods in spec['paths'].items():
        for method,operation in methods.items():
            operations.append(operation['operationId'])
            check('no worker/project API '+operation['operationId'], not path.startswith('/internal/') and '/projects/' not in path)
            check('implementation boundary '+operation['operationId'], operation['x-implementation'] in ('implemented','candidate'))
            check('no legacy CSRF '+operation['operationId'], 'X-CSRF-TOKEN' not in {p['name'] for p in operation['parameters']})
            if not path.startswith('/api/v1/client/') and operation['operationId'] not in ('login','captchaConfig'):
                check('admin Bearer '+operation['operationId'], operation['security']==[{'bearerAuth':[]}])
    check('operation IDs unique',len(operations)==len(set(operations)))
    sql=(ROOT/'database/migrations/V001__platform.sql').read_text(encoding='utf-8')
    api_states=spec['components']['schemas']['VersionView']['properties']['state']['enum']
    block=sql.split('CREATE TABLE scene_version (',1)[1].split('ALTER TABLE scene',1)[0]
    db_states=re.search(r"CHECK\(state IN \(([^)]*)\)\)",block).group(1)
    check('database and API version states agree',set(re.findall(r"'([^']+)'",db_states))==set(api_states))
    check('only seven schema tables',set(re.findall(r'CREATE TABLE (\w+)',sql))=={'admin_user','scene','scene_version','asset','version_asset','marker','audit_log'})
    docfiles=[ROOT/'README.md',ROOT/'database/README.md',*sorted((ROOT/'docs').glob('*.md'))]
    for file in docfiles:
        content=file.read_text(encoding='utf-8')
        for dest in re.findall(r'\]\(([^)]+)\)',content):
            if re.match(r'^(https?://|mailto:|#)',dest):continue
            target=(file.parent/dest.split('#')[0]).resolve()
            check('local link '+file.name+' -> '+dest,target.is_file() or target==ROOT/'docs/validation-contracts.json')
    report={'passed':True,'operations':len(operations),'checks':checks,
            'limitations':['No HTTP server or client runtime executed','No cloud storage or GPU invoked','Mermaid source checked only as Markdown, not rendered']}
    output=ROOT/'docs/validation-contracts.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'PASS: {len(checks)} checks, {len(operations)} operations; {output}')

if __name__=='__main__':main()
