"""Adversarial user/agent authorization against fictional sources only."""
import copy
import io
import json
import secrets
import time
from unittest.mock import Mock,patch
from test_pilot import PilotTestCase
from backend.dev_store import WriteError
from backend.principals import Principal


class AgentAuthorizationTests(PilotTestCase):
    def setUp(self):
        super().setUp();self.value['invites'][0]['role']='admin';self.value['copiedRowIds']=['12']
        self.admin,_=self.login('coord')
    def post(self,client,path,body,key=None,**headers):
        csrf=self.get(client,'/api/session').get_json()['csrf']
        return client.post(path,base_url=self.origin,json=body,headers={'Origin':self.origin,'X-Portal-CSRF':csrf,'Idempotency-Key':key or secrets.token_urlsafe(20),**headers})
    def sid(self,who='coord'):
        return next(sid for sid,session in self.runtime.sessions.items() if session.actor.user_id==self.profiles[who]['id'])
    def create(self,client):
        response=self.write(client,'/api/projects',{'fields':{'title':'Fictional owned job','description':'Fictional intake','taskType':'Other','requestor':'spoofed owner','email':'spoof@example.org','dueDate':'2026-12-01'}})
        self.assertEqual(response.status_code,200,response.get_json());return response.get_json()['jobId']
    def change(self,client,job,action='delete',key=None,body=None):
        if body is None:
            project=self.runtime.jobs._project(self.runtime.jobs._fresh(client.get_cookie('__Host-graphics_pilot',domain='pilot.example.org').value),job,include_deleted=True)
            state=self.runtime.lifecycle.state('123',project['_rowId'])
            body={'action':action,'revision':project['revision'],'version':state['version'],'confirmation':job,'reason':'Fictional audit test'}
        return self.post(client,'/api/v1/jobs/'+job+'/lifecycle',body,key)

    def test_admin_can_edit_selected_copy_but_never_unselected_or_computed_cells(self):
        p=self.project(self.admin,'COPIED');self.assertTrue(p['permissions']['edit']);self.assertTrue(p['permissions']['delete'])
        before=copy.deepcopy(self.fake.rows);response=self.write(self.admin,'/api/projects/COPIED',{'action':'edit','revision':p['revision'],'fields':{'hours':7}})
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.fake.rows[0],before[0]);self.assertEqual(self.fake.rows[2],before[2])
        marker=self.fake.bytitle['DEV Test Record']['id'];self.assertFalse(next(c['value'] for c in self.fake.rows[1]['cells'] if c['columnId']==marker))
        assigned=self.fake.bytitle['Assigned Designer']['id'];self.assertEqual(next(c['formula'] for c in self.fake.rows[1]['cells'] if c['columnId']==assigned),self.fake.bytitle['Assigned Designer']['formula'])
        sid=self.sid();reader=self.runtime.sessions[sid].reader
        with self.assertRaises(WriteError):reader._write('PUT','/sheets/123/rows',[{'id':12,'cells':[]}],'untrusted-agent')
        self.assertEqual(reader.store._admin_rows,frozenset())
        hidden=self.fake.make_row(99,'NOT-SELECTED',False);self.fake.rows.append(hidden);self.fake.version+=1
        self.assertEqual(self.write(self.admin,'/api/projects/NOT-SELECTED',{'action':'edit','revision':'forged','fields':{'hours':9}}).status_code,404)
        p=self.project(self.admin,'COPIED')
        self.assertEqual(self.write(self.admin,'/api/projects/COPIED',{'action':'edit','revision':p['revision'],'fields':{'assignedDesigner':'fake'}}).status_code,400)

    def test_creator_can_delete_and_restore_without_native_writes(self):
        owner,_=self.login('designer');job=self.create(owner);before=copy.deepcopy(self.fake.rows);self.fake.calls.clear()
        response=self.change(owner,job);self.assertEqual(response.status_code,200,response.get_json())
        self.assertNotIn(job,{p['id'] for p in self.get(owner,'/api/projects').get_json()['projects']})
        deleted=self.get(owner,'/api/v1/deleted-jobs').get_json()['jobs'];self.assertEqual([p['id'] for p in deleted],[job]);self.assertTrue(deleted[0]['canRestore'])
        self.assertEqual(self.change(owner,job,'restore').status_code,200)
        self.assertIn(job,{p['id'] for p in self.get(owner,'/api/projects').get_json()['projects']})
        self.assertEqual(self.fake.rows,before);self.assertTrue(all(c[0]=='GET' for c in self.fake.calls))
        with self.runtime.db() as db:
            self.assertEqual(db.execute('SELECT action,actor,client_id,execution_origin FROM job_lifecycle_events ORDER BY rowid').fetchall(),[('delete','101','portal-browser','browser'),('restore','101','portal-browser','browser')])

    def test_assignee_edit_permission_never_transfers_creator_delete_authority(self):
        owner,_=self.login('designer');other,_=self.login('other');job=self.create(owner)
        self.assertEqual(self.action(self.admin,'offer',job,designer='other@example.org').status_code,200)
        self.assertEqual(self.action(other,'accept',job).status_code,200)
        p=self.project(other,job);self.assertTrue(p['permissions']['edit']);self.assertFalse(p['permissions']['delete'])
        self.assertEqual(self.change(other,job).status_code,403)
        self.assertEqual(self.write(other,'/api/projects/'+job,{'action':'edit','revision':p['revision'],'fields':{'requestor':'Other account','email':'other@example.org'}}).status_code,200)
        self.assertEqual(self.change(other,job).status_code,403)
        self.assertEqual(self.change(owner,job).status_code,200)
        self.assertEqual(self.get(other,'/api/v1/deleted-jobs').get_json()['jobs'],[])

    def test_admin_delete_any_copy_and_coordinator_cannot_delete_someone_elses_job(self):
        self.value['invites'][2]['role']='coordinator';coord,_=self.login('other')
        self.assertFalse(self.project(coord,'TEST-1')['permissions']['delete'])
        self.assertEqual(self.change(coord,'TEST-1').status_code,403)
        self.assertEqual(self.change(coord,'COPIED').status_code,403)
        before=copy.deepcopy(self.fake.rows);self.fake.calls.clear()
        self.assertEqual(self.change(self.admin,'COPIED').status_code,200)
        self.assertIn('COPIED',{p['id'] for p in self.get(self.admin,'/api/v1/deleted-jobs').get_json()['jobs']})
        self.assertEqual(self.change(self.admin,'COPIED','restore').status_code,200)
        self.assertEqual(self.fake.rows,before);self.assertTrue(all(c[0]=='GET' for c in self.fake.calls))

    def test_deleted_job_blocks_files_native_edits_ai_and_cached_reports(self):
        self.value['ai']={'browserPilotEnabled':True,'jobIds':['TEST-1']}
        before=self.post(self.admin,'/api/v1/jobs/TEST-1/intake-contexts',{'selectedReferenceIds':[]}).get_json()['context']
        snapshot=self.post(self.admin,'/api/reports',{'filters':{}}).get_json()['snapshotId']
        p=self.project(self.admin);self.assertEqual(self.change(self.admin,'TEST-1').status_code,200)
        self.assertEqual(self.write(self.admin,'/api/projects/TEST-1',{'action':'edit','revision':p['revision'],'fields':{'hours':9}}).status_code,410)
        self.assertEqual(self.get(self.admin,'/api/projects/TEST-1/attachments/900').status_code,410)
        self.assertEqual(self.get(self.admin,'/api/v1/jobs/TEST-1/intake-contexts/'+before['contextId']).status_code,410)
        self.assertEqual(self.post(self.admin,'/api/reports/'+snapshot+'/export',{'format':'csv','layout':'executive','sections':['summary']}).status_code,409)
        self.assertNotIn('TEST-1',{p['id'] for p in self.post(self.admin,'/api/reports',{'filters':{}}).get_json()['report']['classificationProjects']})
        self.assertEqual(self.change(self.admin,'TEST-1','restore').status_code,200)
        self.assertEqual(self.post(self.admin,'/api/reports/'+snapshot+'/export',{'format':'csv','layout':'executive','sections':['summary']}).status_code,409)

    def test_native_viewer_global_pause_and_removed_selection_still_restrict_admin(self):
        self.value['invites'][3]['role']='admin';viewer,_=self.login('viewer')
        self.assertFalse(self.project(viewer,'TEST-1')['permissions']['edit']);self.assertFalse(self.project(viewer,'TEST-1')['permissions']['delete'])
        self.assertEqual(self.change(viewer,'TEST-1').status_code,403)
        self.value['writesEnabled']=False;self.assertEqual(self.change(self.admin,'TEST-1').status_code,403)
        self.value['writesEnabled']=True;self.assertEqual(self.change(self.admin,'COPIED').status_code,200)
        p=next(p for p in self.get(self.admin,'/api/v1/deleted-jobs').get_json()['jobs'] if p['id']=='COPIED')
        self.value['copiedRowIds']=[]
        self.assertEqual(self.change(self.admin,'COPIED',body={'action':'restore','revision':p['sourceRevision'],'version':p['lifecycleVersion'],'confirmation':'COPIED','reason':''}).status_code,404)

    def test_source_or_state_changes_and_replays_never_repeat_or_redelete(self):
        p=self.project(self.admin);body={'action':'delete','revision':p['revision'],'version':0,'confirmation':'TEST-1','reason':''};key=secrets.token_urlsafe(20)
        self.assertEqual(self.change(self.admin,'TEST-1',key=key,body=body).status_code,200)
        self.assertTrue(self.change(self.admin,'TEST-1',key=key,body=body).get_json()['replayed'])
        self.assertEqual(self.change(self.admin,'TEST-1',key=key,body={**body,'reason':'changed'}).status_code,409)
        self.assertEqual(self.change(self.admin,'TEST-1','restore').status_code,200)
        self.assertEqual(self.change(self.admin,'TEST-1',key=key,body=body).status_code,409)
        self.assertEqual(self.change(self.admin,'TEST-1',body=body).status_code,409)
        with self.runtime.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM job_lifecycle_events').fetchone()[0],2)
        p=self.project(self.admin);self.fake.version+=1;self.fake.rows[0]['modifiedAt']='changed'
        self.assertEqual(self.change(self.admin,'TEST-1',body={**body,'version':2,'revision':p['revision']}).status_code,409)

    def test_role_revocation_and_copy_selection_change_during_preflight_prevent_write(self):
        p=self.project(self.admin,'COPIED');reader=self.runtime.sessions[self.sid()].reader;original=reader._get_json
        def altered(path,*a,**kw):
            result=original(path,*a,**kw)
            if '/automationrules' in path:self.value['invites'][0]['role']='coordinator'
            return result
        reader._get_json=altered;self.fake.calls.clear()
        self.assertEqual(self.write(self.admin,'/api/projects/COPIED',{'action':'edit','revision':p['revision'],'fields':{'hours':8}}).status_code,403)
        self.assertTrue(all(c[0]=='GET' for c in self.fake.calls))
        self.value['invites'][0]['role']='admin'
        def selection(path,*a,**kw):
            result=original(path,*a,**kw)
            if '/automationrules' in path:self.value['copiedRowIds']=[]
            return result
        reader._get_json=selection
        self.assertIn(self.write(self.admin,'/api/projects/COPIED',{'action':'edit','revision':p['revision'],'fields':{'hours':8}}).status_code,(404,409))
        self.assertTrue(all(c[0]=='GET' for c in self.fake.calls))

    def test_owner_binding_cannot_be_reused_for_replacement_row_with_same_job_number(self):
        owner,_=self.login('designer');job=self.create(owner);row=next(r for r in self.fake.rows if any(c.get('value')==job for c in r['cells']))
        old=row['id'];self.fake.rows.remove(row);replacement=self.fake.make_row(999,job,True);self.fake.rows.append(replacement);self.fake.version+=1
        self.assertNotIn(job,{p['id'] for p in self.get(owner,'/api/projects').get_json()['projects']})
        self.assertEqual(self.change(owner,job,body={'action':'delete','revision':'forged','version':0,'confirmation':job,'reason':''}).status_code,404)
        with self.runtime.db() as db:self.assertEqual(db.execute('SELECT row_id,user_id FROM job_ownership').fetchall(),[(str(old),'101')])

    def test_old_create_receipt_cannot_claim_a_replacement_row(self):
        owner,_=self.login('designer');key=secrets.token_urlsafe(20)
        body={'fields':{'title':'Fictional request','description':'Original source','taskType':'Other','dueDate':'2026-12-01'}}
        result=self.write(owner,'/api/projects',body,key);self.assertEqual(result.status_code,200)
        job=result.get_json()['jobId'];row=next(r for r in self.fake.rows if any(c.get('value')==job for c in r['cells']))
        self.fake.rows.remove(row);self.fake.rows.append(self.fake.make_row(999,job,True));self.fake.version+=1;self.fake.calls.clear()
        self.assertEqual(self.write(owner,'/api/projects',body,key).status_code,409)
        self.assertFalse([c for c in self.fake.calls if c[0]!='GET'])
        with self.runtime.db() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM job_ownership WHERE row_id='999'").fetchone()[0],0)

    def test_refresh_poll_observes_lifecycle_and_role_changes_without_native_version_change(self):
        other,_=self.login('designer');job=self.create(other);data=self.get(self.admin,'/api/projects').get_json();version=data['sourceVersion']
        self.assertEqual(self.change(other,job).status_code,200)
        response=self.get(self.admin,'/api/projects?sinceVersion='+str(version)).get_json()
        self.assertNotIn(job,{p['id'] for p in response['projects']});self.assertEqual(response['sourceVersion'],version)
        self.value['invites'][0]['role']='designer'
        response=self.get(self.admin,'/api/projects?sinceVersion='+str(version)).get_json()
        self.assertEqual(response['actor']['role'],'designer');self.assertEqual(response['projects'],[])

    def test_unissued_agent_credentials_forged_roles_and_permanent_deletion_are_denied(self):
        anonymous=self.app.test_client();headers={'Origin':self.origin,'Authorization':'Bearer fictional-unissued-grant','X-Portal-CSRF':'forged'}
        self.assertEqual(anonymous.post('/api/v1/jobs/TEST-1/lifecycle',base_url=self.origin,json={},headers=headers).status_code,401)
        for path in ['/mcp','/api/agent-grants','/api/v1/jobs','/api/tokens']:
            self.assertIn(self.get(anonymous,path).status_code,(401,404))
        designer,_=self.login('designer');project=self.project(self.admin)
        body={'action':'delete','revision':project['revision'],'version':0,'confirmation':'TEST-1','reason':'','role':'admin','user_id':'100'}
        self.assertEqual(self.change(designer,'TEST-1',body=body).status_code,400)
        self.assertEqual(self.get(designer,'/api/session').get_json()['actor']['role'],'designer')
        reader=self.runtime.sessions[self.sid()].reader
        with self.assertRaises(WriteError):reader._write('DELETE','/sheets/123/rows?ids=11',None,'untrusted-agent-delete')
        for method in ['DELETE','PUT','TRACE']:
            self.assertEqual(self.admin.open('/api/projects/TEST-1',method=method,base_url=self.origin).status_code,405)
        for action in ['purge','hard-delete','move','share','schema']:
            self.assertEqual(self.change(self.admin,'TEST-1',body={k:v for k,v in {**body,'action':action}.items() if k not in ('role','user_id')}).status_code,400)
        for role in ['admin','coordinator','designer']:
            self.value['invites'][0]['role']=role
            with self.assertRaises(WriteError):self.runtime.jobs.workspace(Principal('100','a@example.org','A',frozenset(),role,time.time()+100))
        self.assertFalse([c for c in self.fake.calls if c[0]!='GET'])

    def test_deleted_reference_bytes_are_not_returned_after_inflight_recovery_state_change(self):
        reader=self.runtime.sessions[self.sid()].reader;p=self.project(self.admin)
        def download(*args):
            self.runtime.lifecycle.change(self.sid(),secrets.token_urlsafe(20),'TEST-1',{'action':'delete','revision':p['revision'],'version':0,'confirmation':'TEST-1','reason':''})
            return b'Fictional private data','text/plain','reference.txt'
        reader.attachment=download
        self.assertEqual(self.get(self.admin,'/api/projects/TEST-1/attachments/900').status_code,410)
