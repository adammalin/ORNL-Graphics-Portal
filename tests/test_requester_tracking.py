"""Only the verified owner can see customer-safe current status and explicit file grants."""
import copy
import hashlib
import json
import secrets
import unittest
from unittest.mock import patch
import test_microsoft_intake as fixture


class RequesterTrackingTests(unittest.TestCase):
    def setUp(self):
        self.p=fixture.MicrosoftIntakeTests();self.p.setUp();self.client=self.p.ms_login();self.receipt=self.p.create(self.client)
        self.job=self.receipt['jobId'];self.token=self.receipt['receipt']
        self.row=next(r for r in self.p.fake.rows if any(c.get('value')==self.job for c in r['cells']))
    def tearDown(self):self.p.tearDown()
    def get(self,client=None,suffix=''):
        return self.p.get(client or self.client,'/api/intake/my-requests/'+self.token+suffix)
    def cell(self,name,value,**extra):
        cid=self.p.fake.bytitle[name]['id'];self.row['cells']=[c for c in self.row['cells'] if c['columnId']!=cid]+[{'columnId':cid,'value':value,**extra}]
        self.p.fake.version+=1;self.row['modifiedAt']='2026-11-17T20:00:00Z'
    def other(self):
        self.p.ms.claims['oid']=fixture.OTHER;self.p.ms.profile['id']=fixture.OTHER
        return self.p.ms_login()  # Deliberately same email: identity, not email, controls ownership.
    def coordinator(self):return self.p.login('coord')[0]
    def staff_share(self,staff,aid='901',visible=True,revision=None):
        project=self.p.project(staff,self.job)
        csrf=self.p.get(staff,'/api/session').get_json()['csrf']
        return staff.post('/api/v1/jobs/'+self.job+'/requester-resources',base_url=self.p.origin,json={'attachmentId':aid,'visible':visible,'revision':revision or project['revision']},headers={'Origin':self.p.origin,'X-Portal-CSRF':csrf})
    def add_file(self,aid='901',name='Internal reference.txt'):
        self.row.setdefault('attachments',[]).append({'id':int(aid),'name':name,'attachmentType':'FILE','mimeType':'text/plain','sizeInKb':1})
        self.p.fake.version+=1
    def test_owner_list_readonly_projection_and_original_snapshot(self):
        self.cell('Additional Details','INTERNAL DESIGNER NOTE - NEVER EXPOSE')
        listing=self.p.get(self.client,'/api/intake/my-requests').get_json()
        self.assertEqual([r['jobId'] for r in listing['requests']],[self.job])
        result=self.get().get_json();raw=json.dumps(result)
        self.assertEqual(result['status'],'submitted');self.assertEqual(result['originalRequest']['description'],'Explain a synthetic process.')
        self.assertEqual(result['originalRequest']['notes'],'Preserve this extra request detail.')
        for secret in ('INTERNAL DESIGNER NOTE','COPIED','"TEST-1"','synthetic-app-secret','_rowId','revision','aiDraft'):
            self.assertNotIn(secret,raw)
        for method in ('PATCH','PUT','DELETE','POST'):
            response=self.client.open('/api/intake/my-requests/'+self.token,method=method,base_url=self.p.origin,headers={'Origin':self.p.origin,'X-Portal-CSRF':self.p.get(self.client,'/api/intake/session').get_json()['csrf']},json={})
            self.assertEqual(response.status_code,405)
    def test_other_same_email_identity_and_staff_cookie_cannot_access_requests(self):
        other=self.other();calls=len(self.p.fake.calls)
        self.assertEqual(self.get(other).status_code,404);self.assertEqual(len(self.p.fake.calls),calls)
        self.assertEqual(self.p.get(other,'/api/intake/my-requests').get_json()['requests'],[])
        self.assertEqual(self.get(self.coordinator()).status_code,401)
    def test_status_dates_assignment_and_archive_mapping_without_invented_history(self):
        self.cell('Project Stage','Assigned');self.cell('Requested Designer','designer@example.org',objectValue={'objectType':'CONTACT','email':'designer@example.org','name':'Test Designer'})
        result=self.get().get_json();self.assertEqual(result['status'],'assigning');self.assertEqual(result['designer'],'')
        self.cell('Assigned Designer','designer@example.org',displayValue='Test Designer',objectValue={'objectType':'CONTACT','email':'designer@example.org','name':'Test Designer'})
        self.cell('Final Due Date','2026-12-04')
        for stage,status in [('Accepted','accepted'),('In Progress','in_progress'),('In Review','in_review'),('Completed','completed'),('Archived','completed')]:
            self.cell('Project Stage',stage);result=self.get().get_json();self.assertEqual(result['status'],status)
            self.assertEqual(result['designer'],'Test Designer');self.assertEqual(result['requestedDueDate'],'2026-12-01');self.assertEqual(result['confirmedDueDate'],'2026-12-04')
            self.assertNotIn('history',result)
    def test_tracking_survives_application_restart_and_paused_writes(self):
        self.p.app=self.p.build();self.p.runtime=self.p.app.extensions['pilot'];self.p.intake=self.p.app.extensions['employee_intake']
        self.client=self.p.ms_login();self.p.value['writesEnabled']=False
        self.assertEqual(self.get().status_code,200)
        self.assertEqual(len(self.p.get(self.client,'/api/intake/my-requests').get_json()['requests']),1)
    def test_unbound_legacy_receipts_or_selected_copy_do_not_expose_live_fields(self):
        self.p.value['copiedRowIds']=[str(self.row['id'])]
        self.assertFalse(self.get().get_json()['available'])
        self.p.value['copiedRowIds']=[]
        with self.p.runtime.db() as db:db.execute('DELETE FROM employee_request_snapshots WHERE receipt=?',(self.token,))
        result=self.get().get_json();self.assertFalse(result['available']);self.assertNotIn('originalRequest',result)
    def test_submitted_upload_gets_exact_hash_bound_download_without_internal_files(self):
        body=b'Customer supplied reference'
        result=self.p.ms_write(self.client,'/api/intake/requests/'+self.token+'/attachments',headers={'Content-Type':'text/plain','X-Filename':'customer.txt','X-Project-Revision':self.receipt['revision']},content=body)
        self.assertEqual(result.status_code,200,result.get_json())
        self.add_file()
        result=self.get().get_json();self.assertEqual([f['name'] for f in result['files']],['sample.txt'])
        with patch.object(self.p.intake.reader,'attachment',return_value=(body,'text/plain','customer.txt')):
            response=self.get(suffix='/attachments/900');self.assertEqual(response.status_code,200);self.assertEqual(response.data,body)
        with patch.object(self.p.intake.reader,'attachment',return_value=(b'CHANGED','text/plain','customer.txt')):
            self.assertEqual(self.get(suffix='/attachments/900').status_code,409)
        self.assertEqual(self.get(suffix='/attachments/901').status_code,404)
    def test_staff_explicit_share_revoke_and_stale_snapshot_guards(self):
        self.add_file();staff=self.coordinator();reader=self.p.readers[-1]
        self.assertTrue(self.p.project(staff,self.job)['requesterTrackable'])
        self.assertEqual(self.get().get_json()['files'],[])
        self.assertEqual(self.staff_share(staff,revision='stale').status_code,409)
        before=copy.deepcopy(self.p.fake.rows);writes=len(self.p.writes())
        with patch.object(reader,'attachment',return_value=(b'Approved file','text/plain','Internal reference.txt')):
            response=self.staff_share(staff);self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(self.p.fake.rows,before);self.assertEqual(len(self.p.writes()),writes)
        self.assertEqual(len(self.get().get_json()['files']),1)
        other=self.other();self.assertEqual(self.get(other,suffix='/attachments/901').status_code,404)
        self.assertEqual(self.staff_share(staff,visible=False).status_code,200)
        self.assertEqual(self.get().get_json()['files'],[]);self.assertEqual(self.get(suffix='/attachments/901').status_code,404)
    def test_requester_cannot_use_staff_sharing_or_tutorial_paths_and_tutorial_is_once(self):
        result=self.staff_share(self.coordinator(),aid='999');self.assertEqual(result.status_code,404)
        self.assertEqual(self.p.get(self.client,'/api/onboarding').status_code,401)
        first=self.p.ms_write(self.client,'/api/intake/onboarding',{'action':'claim'}).get_json();self.assertTrue(first['autoStart']);self.assertEqual(first['tracks'],['requester'])
        self.assertFalse(self.p.ms_write(self.client,'/api/intake/onboarding',{'action':'claim'}).get_json()['autoStart'])
        self.assertEqual(self.p.ms_write(self.client,'/api/intake/onboarding',{'action':'progress','track':'coordinator'}).status_code,400)
    def test_revoked_integration_and_disabled_feature_fail_closed(self):
        self.p.access['coord']='DENIED';self.assertEqual(self.get().status_code,502)
        self.p.value['microsoftIntake']['enabled']=False;self.assertEqual(self.get().status_code,503)

    def test_recoverable_staff_deletion_blocks_requester_tracking_files_and_uploads(self):
        self.p.value['invites'][0]['role']='admin';admin,_=self.p.login('coord')
        csrf=self.p.get(admin,'/api/session').get_json()['csrf']
        project=next(p for p in self.p.get(admin,'/api/projects').get_json()['projects'] if p['id']==self.job)
        body={'action':'delete','revision':project['revision'],'version':0,'confirmation':self.job,'reason':'Fictional deletion audit'}
        response=admin.post('/api/v1/jobs/'+self.job+'/lifecycle',base_url=self.p.origin,json=body,
            headers={'Origin':self.p.origin,'X-Portal-CSRF':csrf,'Idempotency-Key':'fictional-delete-request-key'})
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertFalse(self.get().get_json()['available'])
        response=self.p.ms_write(self.client,'/api/intake/requests/'+self.token+'/attachments',content=b'fake reference',
            headers={'Content-Type':'text/plain','X-Filename':'example.txt','X-Project-Revision':project['revision']})
        self.assertEqual(response.status_code,410)
