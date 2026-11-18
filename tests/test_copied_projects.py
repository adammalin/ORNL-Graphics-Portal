"""Selected copied projects are readable through ordinary policy but never writable."""
import copy
import secrets
import unittest
from unittest.mock import patch

import test_pilot as fixture
from backend.dev_store import WriteError
from backend.server import GatewayError


@unittest.skipUnless(fixture.HAS_FLASK, 'Install pilot requirements.')
class CopiedProjectTests(unittest.TestCase):
    def setUp(self):
        self.p = fixture.PilotTestCase()
        self.p.setUp()
        self.p.value['copiedRowIds'] = ['12']
        self.p.fake.columns.append({'id': 120, 'title': 'Status', 'type': 'TEXT_NUMBER'})
        self.p.fake.bytitle['Status'] = self.p.fake.columns[-1]
        self.copied = self.p.fake.rows[1]
        self.set_cell('Project Stage', '')
        self.set_cell('Status', 'Designer Accepted')
        self.set_cell('Description', 'Example copied scientific flyer')
        for name in ('Requested Designer', 'Assigned Designer'):
            self.set_cell(name, 'designer@example.org', objectValue={'objectType':'CONTACT','email':'designer@example.org','name':'Test Designer'}, displayValue='Test Designer')
        self.before = copy.deepcopy(self.copied)

    def tearDown(self):
        self.p.tearDown()

    def sid(self, who):
        email=self.p.profiles[who]['email']
        return next(key for key,session in self.p.runtime.sessions.items() if session.actor.email==email)

    def set_cell(self, name, value, **extra):
        cid = self.p.fake.bytitle[name]['id']
        self.copied['cells'] = [c for c in self.copied['cells'] if c['columnId'] != cid]
        self.copied['cells'].append({'columnId':cid,'value':value,**extra})

    def test_coordinator_can_read_selected_copied_job_but_cannot_mutate_it(self):
        client, data = self.p.login('coord')
        copied = next(p for p in data['projects'] if p['id'] == 'COPIED')
        self.assertTrue(copied['readOnly']); self.assertFalse(copied['synthetic'])
        self.assertEqual(copied['stage'], 'Accepted')
        self.assertEqual(copied['sourceStatus'], 'Designer Accepted')
        self.assertEqual(copied['permissions'], {'edit':False,'respond':False,'offer':False,'delete':False,'restore':False})
        for action in ('edit','stage','offer','accept','decline'):
            result = self.p.write(client, '/api/projects/COPIED', {'action':action,'revision':copied['revision'],'fields':{'title':'Do not save'},'stage':'Archived','designer':'designer@example.org'})
            self.assertEqual(result.status_code, 403, result.get_json())
        sid=next(k for k,s in self.p.runtime.sessions.items() if s.actor.role=='coordinator')
        self.assertEqual(self.p.runtime.jobs.get_job(sid,'COPIED')['id'],'COPIED')
        csrf = self.p.get(client, '/api/session').get_json()['csrf']
        result = client.post('/api/projects/COPIED/attachments',base_url=self.p.origin,data=b'no upload',headers={'Origin':self.p.origin,'X-Portal-CSRF':csrf,'Idempotency-Key':secrets.token_urlsafe(20),'X-Project-Revision':copied['revision'],'X-Filename':'test.txt','Content-Type':'text/plain'})
        self.assertEqual(result.status_code,403)
        self.assertEqual(self.copied,self.before)
        self.assertFalse([c for c in self.p.fake.calls if c[0]!='GET'])
        self.assertTrue(any('rowIds=12' in c[1] for c in self.p.fake.calls))

    def test_native_test_checkbox_cannot_promote_selected_copy_to_editable(self):
        self.set_cell('DEV Test Record',True)
        client,data = self.p.login('coord')
        project = next(p for p in data['projects'] if p['id']=='COPIED')
        self.assertTrue(project['readOnly']); self.assertFalse(project['permissions']['edit'])
        reader=self.p.readers[-1]
        self.assertNotIn('12',reader.row_ids)
        with self.assertRaises(WriteError): reader.store.row('COPIED')
        # Even an accidentally enlarged in-memory write set cannot bypass the guard.
        reader.row_ids = reader.row_ids | {'12'}
        with self.assertRaises(WriteError): reader._write('PUT','/sheets/123/rows',[{'id':12,'cells':[]}],'forbidden-copy-save')
        with self.assertRaises(WriteError): reader._write('POST','/sheets/123/rows/12/attachments',b'file','forbidden-copy-upload')
        self.assertFalse([c for c in self.p.fake.calls if c[0]!='GET'])

    def test_designer_visibility_and_offer_permissions_are_preserved(self):
        designer,data=self.p.login('designer')
        copied=next(p for p in data['projects'] if p['id']=='COPIED')
        self.assertFalse(copied['permissions']['edit']);self.assertFalse(copied['permissions']['respond'])
        other,data=self.p.login('other')
        self.assertNotIn('COPIED',[p['id'] for p in data['projects']])
        with self.assertRaises(WriteError) as error:self.p.runtime.jobs.get_job(self.sid('other'),'COPIED')
        self.assertEqual(error.exception.status,404)
        self.assertEqual(self.p.get(other,'/api/projects/COPIED/attachments/999').status_code,404)

    def test_uninvited_source_designer_is_displayed_but_not_offered_work(self):
        for name in ('Requested Designer','Assigned Designer'):
            self.set_cell(name,'historical@example.org',objectValue={'objectType':'CONTACT','email':'historical@example.org','name':'Historical Designer'},displayValue='Historical Designer')
        coordinator,data=self.p.login('coord')
        designer=next(d for d in data['designers'] if d['id']=='historical@example.org')
        self.assertEqual(designer['name'],'Historical Designer');self.assertFalse(designer['canReceiveOffer'])
        self.assertIn('historical@example.org',[d['id'] for d in data['teamWorkload']])
        other,data=self.p.login('other')
        self.assertNotIn('historical@example.org',[d['id'] for d in data['designers']])

    def test_copies_are_excluded_from_all_ai_even_if_misconfigured(self):
        self.p.value['ai']={'browserPilotEnabled':True,'jobIds':['COPIED']}
        client,_=self.p.login('coord')
        self.assertEqual(self.p.get(client,'/api/v1/jobs/COPIED/ai').get_json(),{'enabled':False})
        self.assertEqual(self.p.get(client,'/api/v1/jobs/COPIED/reference-inventory').status_code,403)
        csrf=self.p.get(client,'/api/session').get_json()['csrf']
        for suffix,body in [('intake-contexts',{'selectedReferenceIds':[]}),('ai-drafts',{})]:
            result=client.post('/api/v1/jobs/COPIED/'+suffix,base_url=self.p.origin,json=body,headers={'Origin':self.p.origin,'X-Portal-CSRF':csrf,'Idempotency-Key':secrets.token_urlsafe(20)})
            self.assertEqual(result.status_code,403)
        self.assertFalse([c for c in self.p.fake.calls if c[0]!='GET'])

    def test_selection_removal_and_native_revocation_take_effect(self):
        client,_=self.p.login('coord')
        self.p.value['copiedRowIds']=[]
        self.assertNotIn('COPIED',[p['id'] for p in self.p.get(client,'/api/projects').get_json()['projects']])
        with self.assertRaises(WriteError) as error:self.p.runtime.jobs.get_job(self.sid('coord'),'COPIED')
        self.assertEqual(error.exception.status,404)
        self.p.value['copiedRowIds']=['12']
        self.p.access['coord']='DENIED'
        self.assertNotEqual(self.p.get(client,'/api/projects').status_code,200)

    def test_copied_row_configuration_is_bounded_and_fail_closed(self):
        from backend.pilot import PilotConfig
        for value in ('12',['12','12'],['not-a-row'],[str(n) for n in range(21)]):
            with self.assertRaises(WriteError):PilotConfig({**self.p.value,'copiedRowIds':value})

    def test_copied_values_cannot_be_replaced_by_a_same_number_job(self):
        self.set_cell('Graphics Req #','TEST-1')
        client=self.p.app.test_client()
        # Callback must fail when selected/test IDs collide, never choose one.
        state=self.p.begin(client)
        response=self.p.get(client,'/auth/smartsheet/callback',query_string={'state':state,'code':'coord'})
        self.assertNotEqual(response.status_code,303)

    def test_source_change_between_test_and_copy_reads_rejects_mixed_snapshot(self):
        client,_=self.p.login('coord')
        reader=self.p.readers[-1];transport=reader._transport
        def changed(path,*args,**kwargs):
            result=transport(path,*args,**kwargs)
            if 'rowIds=12' in path:result['version']+=1
            return result
        reader._transport=changed
        with self.assertRaises(GatewayError):self.p.runtime.jobs.workspace(self.sid('coord'))

    def test_copied_attachment_read_obeys_same_account_visibility(self):
        coordinator,_=self.p.login('coord');reader=self.p.readers[-1]
        with patch.object(reader,'attachment',return_value=(b'synthetic reference','text/plain','reference.txt')) as attachment:
            result=self.p.get(coordinator,'/api/projects/COPIED/attachments/900')
            self.assertEqual(result.status_code,200);self.assertEqual(result.data,b'synthetic reference')
            attachment.assert_called_once_with('COPIED','900')
        other,_=self.p.login('other');reader=self.p.readers[-1]
        with patch.object(reader,'attachment') as attachment:
            self.assertEqual(self.p.get(other,'/api/projects/COPIED/attachments/900').status_code,404)
            attachment.assert_not_called()
