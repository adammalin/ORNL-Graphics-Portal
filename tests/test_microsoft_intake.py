"""Employee identity and create-only access, with fictional Microsoft/Smartsheet APIs."""
import copy
from datetime import datetime, timedelta, timezone
import secrets
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from test_pilot import PilotTestCase, HAS_FLASK
if HAS_FLASK:
    from backend.pilot import create_app, PilotConfig
    from backend import microsoft_intake as intake
    from backend.dev_store import WriteError

TENANT = '11111111-1111-4111-8111-111111111111'
CLIENT = '22222222-2222-4222-8222-222222222222'
MEMBER = '33333333-3333-4333-8333-333333333333'
OTHER = '44444444-4444-4444-8444-444444444444'


class FakeMicrosoft:
    def __init__(self):
        self.calls = []
        self.claims = {'tid': TENANT, 'oid': MEMBER, 'exp': time.time() + 1800}
        self.profile = {'id': MEMBER, 'displayName': 'Fictional Employee', 'mail': 'employee@example.org',
                        'department': 'Sample Science', 'userType': 'Member'}

    def begin(self):
        state = secrets.token_urlsafe(32)
        return {'state':state, 'auth_uri':'https://login.microsoftonline.com/'+TENANT+'/oauth2/v2.0/authorize?state='+state}, object()

    def complete(self, flow, client, response):
        self.calls.append(response.get('code'))
        if response.get('error'):
            raise WriteError('Sign-in was not approved.', 401)
        return copy.deepcopy(self.claims), copy.deepcopy(self.profile)


class MicrosoftIntakeTests(PilotTestCase):
    def setUp(self):
        super().setUp()
        self.ms = FakeMicrosoft()
        self.value['microsoftIntake'] = {'enabled': True, 'tenantId':TENANT, 'clientId':CLIENT,
                                        'integrationUserId':'100'}
        self.app = self.build()
        self.app.testing = True
        self.runtime = self.app.extensions['pilot']
        self.intake = self.app.extensions['employee_intake']

    def build(self):
        return create_app(self.value, 'synthetic-app-secret', oauth_transport=self.oauth,
                          reader_factory=self.reader, reload_config=lambda: PilotConfig(self.value),
                          microsoft_secret='synthetic-microsoft-secret', intake_token='coord', microsoft_oauth=self.ms)

    def ms_begin(self, client):
        response = self.get(client, '/auth/microsoft/login')
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        return parse_qs(urlsplit(response.location).query)['state'][0]

    def ms_login(self):
        client = self.app.test_client()
        state = self.ms_begin(client)
        response = self.get(client, intake.CALLBACK, query_string={'state':state,'code':'fictional-code'})
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        self.assertEqual(response.location, '/request')
        return client

    def ms_write(self, client, path, body=None, key=None, headers=None, content=None):
        csrf = self.get(client, '/api/intake/session').get_json()['csrf']
        kwargs = {'headers':{'Origin':self.origin, 'X-Portal-CSRF':csrf,
                  'Idempotency-Key':key or secrets.token_urlsafe(20), **(headers or {})}}
        kwargs.update({'data':content} if content is not None else {'json':body})
        return client.post(path, base_url=self.origin, **kwargs)

    def body(self):
        return {'fields':{'title':'Fictional outreach figure', 'description':'Explain a synthetic process.',
            'notes':'Preserve this extra request detail.', 'taskType':['Other'], 'dueDate':'2026-12-01',
            'deliverables':'One figure', 'audience':'Students', 'specifications':'Editable SVG',
            'requestorGroup':'Sample Science', 'reference1':'https://example.org/reference',
            'requestor':'Spoofed Person', 'email':'spoof@example.org'}}

    def create(self, client):
        response = self.ms_write(client, '/api/intake/requests', self.body())
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def writes(self):
        return [c for c in self.fake.calls if c[0] != 'GET']

    def test_anonymous_routes_disabled_config_and_secret_isolation(self):
        client = self.app.test_client()
        self.assertIn(b'Request creative work', self.get(client, '/').data)
        self.assertEqual(self.get(client, '/request').status_code, 303)
        for path in ['/api/intake/session','/api/intake/requests/TEST-1']:
            self.assertEqual(self.get(client,path).status_code, 401)
        for path in ['/intake.html','/.local/pilot-config.json']:
            self.assertEqual(self.get(client,path).status_code, 404)
        for path in ['/','/intake.js','/runtime-config.js']:
            with self.get(client,path) as response:
                content = response.data
            for private in [TENANT.encode(),CLIENT.encode(),b'synthetic-microsoft-secret',b'employee@example.org',b'TEST-1']:
                self.assertNotIn(private,content)
        self.value['microsoftIntake']['enabled']=False
        self.assertEqual(self.get(client,'/auth/microsoft/login').status_code,503)

    def test_microsoft_state_browser_binding_single_use_expiry_and_secure_cookie(self):
        first, other = self.app.test_client(), self.app.test_client()
        state = self.ms_begin(first)
        path=intake.CALLBACK+'?state='+state+'&code=sample'
        self.assertEqual(self.get(other,path).status_code,400)
        self.assertEqual(self.get(first,path).status_code,400)
        self.assertEqual(self.ms.calls,[])
        state=self.ms_begin(first)
        self.intake.pending[state]['expires']=time.time()-1
        self.assertEqual(self.get(first,intake.CALLBACK,query_string={'state':state,'code':'sample'}).status_code,400)
        state=self.ms_begin(first)
        response=self.get(first,intake.CALLBACK,query_string={'state':state,'code':'sample'})
        cookie='\n'.join(response.headers.getlist('Set-Cookie'))
        for flag in [intake.COOKIE,'Secure','HttpOnly','SameSite=Lax','Path=/']:self.assertIn(flag,cookie)
        self.assertNotIn('Domain=',cookie)
        self.assertEqual(self.get(first,intake.CALLBACK,query_string={'state':state,'code':'sample'}).status_code,400)
        self.assertEqual(len(self.ms.calls),1)

    def test_wrong_tenant_guest_mismatched_id_and_missing_contact_are_rejected(self):
        for source,key,value in [(self.ms.claims,'tid',CLIENT),(self.ms.claims,'oid',OTHER),
                                 (self.ms.profile,'userType','Guest'),(self.ms.profile,'mail',None),
                                 (self.ms.profile,'displayName','')]:
            old=source[key];source[key]=value
            client=self.app.test_client();state=self.ms_begin(client)
            self.assertEqual(self.get(client,intake.CALLBACK,query_string={'state':state,'code':'sample'}).status_code,403)
            source[key]=old
        self.assertEqual(self.intake.sessions,{})
        self.assertEqual(self.writes(),[])

    def test_optional_employee_app_role_is_required_when_configured(self):
        self.value['microsoftIntake']['requiredRole']='Employee.Intake'
        self.app=self.build();self.app.testing=True;self.intake=self.app.extensions['employee_intake']
        client=self.app.test_client();state=self.ms_begin(client)
        self.assertEqual(self.get(client,intake.CALLBACK,query_string={'state':state,'code':'sample'}).status_code,403)
        self.ms.claims['roles']=['Employee.Intake']
        self.ms_login()

    def test_requester_prefill_and_designer_sessions_remain_separate(self):
        client=self.ms_login()
        info=self.get(client,'/api/intake/session').get_json()
        self.assertEqual(info['email'],'employee@example.org')
        self.assertEqual(info['department'],'Sample Science')
        self.assertNotIn('designers',info)
        for path in ['/api/projects','/api/session','/api/v1/capabilities','/api/projects/TEST-1/attachments/900']:
            self.assertEqual(self.get(client,path).status_code,401)
        with self.get(client,'/request') as response:
            self.assertEqual(response.status_code,200)
        designer,_=self.login('designer')
        self.assertEqual(self.get(designer,'/api/intake/session').status_code,401)
        self.assertEqual(len(self.runtime.sessions),1)

    def test_create_retains_inputs_overrides_identity_and_returns_only_receipt(self):
        client=self.ms_login();before=copy.deepcopy(self.fake.rows)
        result=self.create(client)
        self.assertEqual(set(result),{'receipt','jobId','title','revision','attachments'})
        self.assertNotIn('projects',result)
        self.assertEqual(self.fake.rows[:len(before)],before)
        project=next(p for p in self.intake.reader.projects(force=True)['projects'] if p['id']==result['jobId'])
        self.assertEqual(project['requestor'],'Fictional Employee')
        self.assertEqual(project['stage'],'New')
        self.assertEqual(project['requestorGroup'],'Sample Science')
        for detail in ['Explain a synthetic process.','Preserve this extra request detail.','Students','Editable SVG']:
            self.assertIn(detail,project['description'])
        cells={c['columnId']:c for c in self.fake.rows[-1]['cells']}
        self.assertEqual(cells[self.fake.bytitle['Requestor Email']['id']]['value'],'employee@example.org')
        self.assertEqual(len(self.writes()),1)
        coord,_=self.login('coord')
        self.assertIn(result['jobId'],[p['id'] for p in self.get(coord,'/api/projects').get_json()['projects']])

    def test_employee_form_org_inputs_map_to_native_columns(self):
        self.fake.bytitle['Owner Directorate'].update(type='PICKLIST',options=['Fictional Research'])
        self.fake.bytitle['Owner Division/Office/Facility'].update(type='PICKLIST',options=['Fictional Division'])
        client=self.ms_login();info=self.get(client,'/api/intake/session').get_json()
        self.assertEqual(info['organizationOptions']['directorate'],['Fictional Research'])
        body=self.body();body['fields'].update(directorate='Fictional Research',division='Fictional Division')
        response=self.ms_write(client,'/api/intake/requests',body)
        self.assertEqual(response.status_code,200,response.get_json())
        cells={c['columnId']:c.get('value') for c in self.fake.rows[-1]['cells']}
        self.assertEqual(cells[self.fake.bytitle['Owner Directorate']['id']],'Fictional Research')
        self.assertEqual(cells[self.fake.bytitle['Owner Division/Office/Facility']['id']],'Fictional Division')
        self.assertEqual(cells[self.fake.bytitle['Owner Group']['id']],'Sample Science')
        with self.runtime.db() as db:
            self.assertEqual(db.execute('SELECT owner FROM employee_intake_receipts').fetchone()[0],TENANT+':'+MEMBER)
            self.assertNotIn('secret',str(db.execute('SELECT * FROM employee_intake_audit').fetchall()))

    def test_retries_are_owner_scoped_durable_and_do_not_duplicate(self):
        first=self.ms_login();key='same-client-request-key'
        response=self.ms_write(first,'/api/intake/requests',self.body(),key).get_json()
        again=self.ms_write(first,'/api/intake/requests',self.body(),key).get_json()
        self.assertEqual(response,again)
        self.assertEqual(len(self.writes()),1)
        self.ms.claims['oid']=OTHER;self.ms.profile['id']=OTHER
        second=self.ms_login()
        self.assertEqual(self.get(second,'/api/intake/requests/'+response['receipt']).status_code,404)
        self.assertEqual(self.get(second,'/api/intake/requests/TEST-1').status_code,404)
        other=self.ms_write(second,'/api/intake/requests',self.body(),key).get_json()
        self.assertNotEqual(other['jobId'],response['jobId'])
        self.assertEqual(len(self.writes()),2)
        self.app=self.build();self.app.testing=True;self.intake=self.app.extensions['employee_intake']
        second=self.ms_login()
        restored=self.ms_write(second,'/api/intake/requests',self.body(),key).get_json()
        self.assertEqual(restored['receipt'],other['receipt'])
        self.assertEqual(len(self.writes()),2)

    def test_origin_csrf_head_methods_and_unknown_parameters_fail_closed(self):
        client=self.ms_login()
        for headers in [{'Origin':'https://evil.example.org'},{'X-Portal-CSRF':'bad'}]:
            self.assertEqual(self.ms_write(client,'/api/intake/requests',self.body(),headers=headers).status_code,403)
        for extra in ['stage','hours','requestedDesigner','sheetId','finalDueDate']:
            body=self.body();body['fields'][extra]='bad'
            self.assertEqual(self.ms_write(client,'/api/intake/requests',body).status_code,400)
        for method in ['DELETE','PUT','PATCH']:
            result=client.open('/api/intake/requests/TEST-1',method=method,base_url=self.origin,
                headers={'Origin':self.origin,'X-Portal-CSRF':self.get(client,'/api/intake/session').get_json()['csrf']})
            self.assertEqual(result.status_code,405)
        self.assertEqual(client.head('/auth/microsoft/login',base_url=self.origin).status_code,405)
        self.assertEqual(self.writes(),[])

    def test_append_only_files_require_own_receipt_revision_and_count_limit(self):
        client=self.ms_login();receipt=self.create(client)
        def upload(key='synthetic-upload-key',revision=None,content=b'Fictional reference'):
            return self.ms_write(client,'/api/intake/requests/'+receipt['receipt']+'/attachments',key=key,
                headers={'X-Filename':'sample.txt','X-Project-Revision':revision or receipt['revision'],'Content-Type':'text/plain'},content=content)
        self.assertEqual(upload(revision='stale').status_code,409)
        result=upload().get_json()
        self.assertEqual(result['attachments'],[{'name':'sample.txt'}])
        self.assertEqual(upload().status_code,200)
        self.assertEqual(len(self.writes()),2)
        self.assertEqual(upload(content=b'Changed content').status_code,409)
        self.ms.claims['oid']=OTHER;self.ms.profile['id']=OTHER
        other=self.ms_login()
        self.assertEqual(self.ms_write(other,'/api/intake/requests/'+receipt['receipt']+'/attachments',
            content=b'bad',headers={'Content-Type':'text/plain','X-Filename':'sample.txt','X-Project-Revision':result['revision']}).status_code,404)
        row=self.fake.rows[-1]
        row['attachments']*=10
        self.assertEqual(upload(key='a-different-upload-key').status_code,403)
        row['attachments'].append({'id':123456,'name':'Internal designer reference.pdf'})
        confirmed=self.get(client,'/api/intake/requests/'+receipt['receipt']).get_json()
        self.assertEqual(confirmed['attachments'],[{'name':'sample.txt'}])
        self.assertEqual(len(self.writes()),2)
        with self.assertRaises(WriteError):self.intake.reader.store._write('PUT','/sheets/123/rows',[],'forbidden')
        with self.assertRaises(WriteError):self.intake.reader.store._write('DELETE','/sheets/123/rows',[],'forbidden')

    def test_uncertain_write_is_not_repeated_and_limit_is_enforced(self):
        client=self.ms_login();self.fake.timeout=True;key='uncertain-create-key'
        for expected in (502,409):
            self.assertEqual(self.ms_write(client,'/api/intake/requests',self.body(),key).status_code,expected)
        self.assertEqual(len(self.writes()),1)
        self.fake.timeout=False
        actor=next(iter(self.intake.sessions.values())).actor
        with self.runtime.db() as db:
            for n in range(20):
                db.execute('INSERT INTO employee_intake_receipts VALUES (?,?,?,?,?,NULL,NULL)',
                    ('receipt'+str(n),actor.key,'key'+str(n),'123',time.time()))
        self.assertEqual(self.ms_write(client,'/api/intake/requests',self.body()).status_code,429)
        self.assertEqual(len(self.writes()),1)

    def test_expired_review_native_automation_revocation_and_expired_session_block_writes(self):
        client=self.ms_login()
        self.value['workflowReview']['reviewedAt']=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        self.assertFalse(self.get(client,'/api/intake/session').get_json()['canSubmit'])
        self.assertEqual(self.ms_write(client,'/api/intake/requests',self.body()).status_code,403)
        self.value['workflowReview']['reviewedAt']=datetime.now(timezone.utc).isoformat()
        self.fake.rules[0]['enabled']=True
        self.assertEqual(self.ms_write(client,'/api/intake/requests',self.body()).status_code,409)
        self.fake.rules[0]['enabled']=False
        self.access['coord']='DENIED'
        self.assertEqual(self.get(client,'/api/intake/session').status_code,502)
        self.access['coord']='EDITOR'
        next(iter(self.intake.sessions.values())).expires=time.time()-1
        self.assertEqual(self.get(client,'/api/intake/session').status_code,401)
        self.assertEqual(self.writes(),[])

    def test_signout_configuration_change_and_expiry_do_not_fall_back_to_designer(self):
        client=self.ms_login()
        response=self.ms_write(client,'/auth/microsoft/logout',{})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.get(client,'/api/intake/session').status_code,401)
        self.assertEqual(self.get(client,'/api/projects').status_code,401)
        client=self.ms_login()
        self.value['microsoftIntake']['enabled']=False
        self.assertEqual(self.get(client,'/api/intake/session').status_code,503)

    def test_preflight_expiry_prevents_native_mutation(self):
        client=self.ms_login();original=self.intake.reader.store.validate_source
        def expired():
            result=original()
            next(iter(self.intake.sessions.values())).expires=time.time()-1
            return result
        self.intake.reader.store.validate_source=expired
        self.assertEqual(self.ms_write(client,'/api/intake/requests',self.body()).status_code,401)
        self.assertEqual(self.writes(),[])

    def test_integration_account_and_config_are_pinned(self):
        self.value['microsoftIntake']['integrationUserId']='999'
        with self.assertRaises(WriteError):self.build()
        self.value['microsoftIntake']['tenantId']='common'
        with self.assertRaises(WriteError):PilotConfig(self.value)

    def test_msal_adapter_uses_only_profile_scope_and_disables_offline_access(self):
        oauth=intake.MicrosoftOAuth(self.intake.config,'synthetic-secret',self.origin)
        with patch('msal.ConfidentialClientApplication') as factory:
            factory.return_value.initiate_auth_code_flow.return_value={'state':'sample','auth_uri':'https://login.microsoftonline.com/example'}
            flow,client=oauth.begin()
            self.assertEqual(factory.call_args.kwargs['exclude_scopes'],['offline_access'])
            self.assertEqual(factory.call_args.kwargs['authority'],'https://login.microsoftonline.com/'+TENANT)
            self.assertEqual(client.initiate_auth_code_flow.call_args.kwargs['scopes'],['User.Read'])
            self.assertEqual(client.initiate_auth_code_flow.call_args.kwargs['redirect_uri'],self.origin+intake.CALLBACK)
            client.acquire_token_by_auth_code_flow.return_value={'error':'denied','error_description':'SENSITIVE ERROR'}
            with self.assertRaises(WriteError) as error:oauth.complete(flow,client,{'state':'sample','code':'sample'})
            self.assertNotIn('SENSITIVE',str(error.exception))

    def test_launcher_requires_supported_tls_runtime_before_asking_for_secrets(self):
        import json
        from pathlib import Path
        from backend.pilot import main
        config_path=Path(self.tmp.name)/'microsoft-config.json'
        config_path.write_text(json.dumps(self.value))
        with patch('sys.argv',['pilot','--config',str(config_path),'--port','0']), \
             patch('backend.pilot.sys.version_info',(3,9)), \
             patch('backend.pilot.getpass.getpass') as prompt:
            with self.assertRaises(WriteError) as error:main()
        self.assertIn('Python 3.10+',str(error.exception))
        prompt.assert_not_called()
