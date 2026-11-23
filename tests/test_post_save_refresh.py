"""Consistent native snapshots and acknowledged writes, using fictional data."""
import secrets
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from backend.server import SmartsheetReader,GatewayError,RefreshUnavailable
from test_dev_writes import FakeSmartsheet
from test_pilot import PilotTestCase


class WorkspaceReadRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fake=FakeSmartsheet()
        self.reader=SmartsheetReader('123',[],'fictional',self.fake,filter_id='777')
        self.reader.copied_row_ids=frozenset({'12'})
        self.reader.projects(force=True)

    def test_version_race_restarts_entire_read_without_mixing_snapshots(self):
        original=self.reader._transport;changed=False
        def racing(path):
            nonlocal changed
            if 'rowIds=' in path and not changed:
                changed=True;self.fake.version+=1
                cell=next(c for c in self.fake.rows[0]['cells'] if c['columnId']==self.fake.bytitle['Description']['id'])
                cell['value']='New consistent title'
            return original(path)
        self.reader._transport=racing
        result=self.reader.projects(force=True)
        self.assertEqual(result['sourceVersion'],self.fake.version)
        self.assertEqual(next(p for p in result['projects'] if p['id']=='TEST-1')['title'],'New consistent title')
        self.assertEqual(sum(x.get('reason')=='snapshot-version-changed' for x in self.reader.audit),1)
        self.assertTrue(all(c[0]=='GET' for c in self.fake.calls))

    def test_continuous_changes_stop_after_three_pairs_and_preserve_complete_cache(self):
        before=(self.reader._cache,self.reader.sheet,self.reader.row_ids,self.reader.version)
        self.fake.rows.append(self.fake.make_row(99,'NEW-TEST',True))
        original=self.reader._transport;self.fake.calls.clear()
        def racing(path):
            if 'rowIds=' in path:self.fake.version+=1
            return original(path)
        self.reader._transport=racing
        with self.assertRaises(RefreshUnavailable):self.reader.projects(force=True)
        self.assertEqual(sum('rowIds=' in c[1] for c in self.fake.calls),3)
        self.assertIs(self.reader._cache,before[0]);self.assertIs(self.reader.sheet,before[1])
        self.assertEqual((self.reader.row_ids,self.reader.version),before[2:])

    def test_schema_access_and_filter_changes_are_not_retried(self):
        original=self.reader._transport
        for change in ('schema','access','filter'):
            self.fake.calls.clear()
            def altered(path):
                result=original(path)
                if change=='filter' and '/filters/' in path:result['name']='Changed filter'
                if 'rowIds=' in path:
                    if change=='schema':result['columns'][0]['title']='Changed schema'
                    if change=='access':result['accessLevel']='VIEWER'
                return result
            self.reader._transport=altered
            with self.assertRaises(GatewayError) as error:self.reader.projects(force=True)
            self.assertNotIsInstance(error.exception,RefreshUnavailable)
            self.assertLessEqual(len(self.fake.calls),3)
        self.reader._transport=original

    def test_only_temporary_http_errors_are_retryable(self):
        self.reader._transport=None
        for code,expected in ((503,RefreshUnavailable),(429,RefreshUnavailable),(401,GatewayError),(403,GatewayError)):
            with patch.object(self.reader._opener,'open',side_effect=HTTPError('https://api.smartsheet.com',code,'test',{},None)):
                with self.assertRaises(expected) as error:self.reader._get_json('/sheets/123','fictional-read')
                if code in (401,403):self.assertNotIsInstance(error.exception,RefreshUnavailable)


class ConfirmedSaveRecoveryTests(PilotTestCase):
    def fail_readback(self,reader,drop_generated_number=False):
        original=reader._transport;remaining=0
        def transport(path,method='GET',payload=None,headers=None):
            nonlocal remaining
            if method=='GET' and remaining:
                remaining-=1
                raise RefreshUnavailable('Fictional temporary read failure')
            result=original(path,method,payload,headers)
            if method in ('POST','PUT'):
                remaining=3
                if drop_generated_number and method=='POST':
                    result['result'][0]['cells']=[c for c in result['result'][0]['cells']
                        if c['columnId']!=self.fake.bytitle['Graphics Req #']['id']]
            return result
        reader._transport=transport

    def intake(self):
        return {'fields':{'title':'Fictional refresh recovery','description':'No real client data',
            'taskType':['Other']},'assignToMe':True}

    def test_confirmed_edit_receipt_replays_readback_without_a_second_native_write(self):
        client,data=self.login('coord');reader=self.readers[-1];self.fail_readback(reader)
        job=data['projects'][0];key=secrets.token_urlsafe(20)
        body={'action':'edit','revision':job['revision'],'fields':{'hours':7}}
        failed=self.write(client,'/api/projects/'+job['id'],body,key=key)
        self.assertEqual(failed.status_code,503);self.assertTrue(failed.get_json()['saveConfirmed'])
        replay=self.write(client,'/api/projects/'+job['id'],body,key=key)
        self.assertEqual(replay.status_code,200,replay.get_json())
        self.assertEqual(next(p for p in replay.get_json()['projects'] if p['id']==job['id'])['hours'],7)
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),1)

    def test_post_save_version_race_recovers_inside_the_original_request(self):
        self.value['copiedRowIds']=['12'];client,data=self.login('coord');reader=self.readers[-1]
        original=reader._transport;race=False
        def transport(path,method='GET',payload=None,headers=None):
            nonlocal race
            if method=='GET' and 'rowIds=' in path and race:
                self.fake.version+=1;race=False
            result=original(path,method,payload,headers)
            if method=='PUT':race=True
            return result
        reader._transport=transport;job=next(p for p in data['projects'] if p['id']=='TEST-1')
        result=self.write(client,'/api/projects/TEST-1',{'action':'edit','revision':job['revision'],'fields':{'hours':8}})
        self.assertEqual(result.status_code,200,result.get_json())
        self.assertEqual(next(p for p in result.get_json()['projects'] if p['id']=='TEST-1')['hours'],8)
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),1)
        self.assertTrue(any(x.get('reason')=='snapshot-version-changed' for x in reader.audit))

    def test_create_receipt_and_creator_rights_survive_failed_readback(self):
        client,_=self.login('designer');reader=self.readers[-1];self.fail_readback(reader)
        key=secrets.token_urlsafe(20);body=self.intake()
        failed=self.write(client,'/api/projects',body,key=key)
        self.assertEqual(failed.status_code,503);self.assertTrue(failed.get_json()['saveConfirmed'])
        job_id=failed.get_json()['jobId'];self.assertTrue(job_id)
        # Rights are retained before the original browser receipt is resumed.
        job=self.project(client,job_id);self.assertTrue(job['permissions']['edit'])
        replay=self.write(client,'/api/projects',body,key=key)
        self.assertEqual(replay.status_code,200,replay.get_json());self.assertEqual(replay.get_json()['jobId'],job_id)
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),1)
        self.assertEqual(self.project(client,job_id)['stage'],'Accepted')

    def test_create_with_deferred_job_number_recovers_by_permanent_row_id(self):
        client,_=self.login('designer');self.fail_readback(self.readers[-1],True)
        key=secrets.token_urlsafe(20);body=self.intake()
        failed=self.write(client,'/api/projects',body,key=key)
        self.assertEqual(failed.status_code,503);self.assertIsNone(failed.get_json()['jobId'])
        pending=self.get(client,'/api/projects').get_json()['projects']
        created=next(p for p in pending if 'Fictional refresh recovery' in p['title'])
        self.assertTrue(created['permissions']['edit'])
        replay=self.write(client,'/api/projects',body,key=key)
        self.assertEqual(replay.status_code,200,replay.get_json())
        self.assertTrue(self.project(client,replay.get_json()['jobId'])['permissions']['edit'])
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),1)

    def test_uncertain_native_write_has_no_confirmed_receipt_and_is_never_repeated(self):
        client,_=self.login('designer');self.fake.timeout=True
        key=secrets.token_urlsafe(20);body=self.intake()
        failed=self.write(client,'/api/projects',body,key=key)
        self.assertFalse(failed.get_json().get('saveConfirmed',False))
        self.write(client,'/api/projects',body,key=key)
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),1)

    def test_attachment_receipt_recovery_does_not_upload_a_second_file(self):
        client,data=self.login('coord');reader=self.readers[-1];self.fail_readback(reader)
        job=data['projects'][0];key=secrets.token_urlsafe(20)
        csrf=self.get(client,'/api/session').get_json()['csrf']
        options={'base_url':self.origin,'data':b'Fictional reference', 'headers':{
            'Origin':self.origin,'X-Portal-CSRF':csrf,'Idempotency-Key':key,
            'X-Project-Revision':job['revision'],'X-Filename':'fictional.txt','Content-Type':'text/plain'}}
        failed=client.post('/api/projects/'+job['id']+'/attachments',**options)
        self.assertEqual(failed.status_code,503);self.assertTrue(failed.get_json()['saveConfirmed'])
        replay=client.post('/api/projects/'+job['id']+'/attachments',**options)
        self.assertEqual(replay.status_code,200,replay.get_json())
        self.assertEqual(len(self.project(client,job['id'])['attachments']),1)
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),1)

    def test_policy_denial_on_receipt_replay_never_repeats_native_write(self):
        client,data=self.login('coord');reader=self.readers[-1];self.fail_readback(reader)
        key=secrets.token_urlsafe(20);job=data['projects'][0]
        body={'action':'edit','revision':job['revision'],'fields':{'hours':4}}
        self.assertEqual(self.write(client,'/api/projects/'+job['id'],body,key=key).status_code,503)
        self.access['coord']='DENIED'
        self.assertNotEqual(self.write(client,'/api/projects/'+job['id'],body,key=key).status_code,200)
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),1)
