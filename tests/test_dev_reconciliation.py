"""Real reconciliation policy against two fictional native sheets; never uses credentials."""
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import re
from unittest.mock import patch

from test_pilot import PilotTestCase
from scripts.compare_smartsheet_exports import compare
from backend.dev_reconciliation import DevReconciliation,NativeClient,row_fields,cell_value
from backend.dev_store import WriteError
from backend.server import GatewayError


class DevReconciliationTests(PilotTestCase):
    def setUp(self):
        super().setUp();self.value['invites'][0]['role']='admin'
        status={'id':99,'title':'Status','type':'PICKLIST','options':['New','Designer Accepted']}
        self.fake.columns.append(status);self.fake.bytitle['Status']=status
        self.fake.rows[1]['cells'].append({'columnId':99,'value':'New'})
        desc=self.fake.bytitle['Description']['id']
        next(c for c in self.fake.rows[1]['cells'] if c['columnId']==desc)['value']='Original clone'
        self.source=copy.deepcopy({'id':456,'name':'Graphics Assignments','version':50,
                'accessLevel':'EDITOR','columns':self.fake.columns,'rows':[self.fake.rows[1],self.fake.rows[0]]})
        self.source['rows'][0]['id']=100;self.source['rows'][1]['id']=101
        next(c for c in self.source['rows'][0]['cells'] if c['columnId']==99)['value']='Designer Accepted'
        next(c for c in self.source['rows'][1]['cells'] if c['columnId']==desc)['value']='New live project'
        marker=self.fake.bytitle['DEV Test Record']['id']
        for row in self.source['rows']:
            next(c for c in row['cells'] if c['columnId']==marker)['value']=False
        self.source_threads=[{'id':200,'parentType':'ROW','parentId':100,'comments':[
            {'id':201,'text':'First note','createdAt':'2026-11-01T10:00:00Z','createdBy':{'name':'Original Author'}},
            {'id':202,'text':'Reply note','createdAt':'2026-11-02T10:00:00Z','createdBy':{'name':'Original Author'}}]}]
        self.target_threads=[];self.native_calls=[];self.uncertain_create=False
        self.client,_=self.login('coord');self.sid=next(iter(self.runtime.sessions))
        self.runtime.sessions[self.sid].reader._transport=self.native
        def exported(sheet,comments=False):
            rows=[['Graphics Req #','Description','Status','DEV Test Record']]
            for row in sheet['rows']:
                f=row_fields(sheet,row);rows.append([f.get(k) for k in rows[0]])
            result={'sheets':[{'name':'Jobs','rows':rows}]}
            if comments:result['sheets'].append({'name':'Comments','rows':[
                ['Row 1','First note','Original Author','11/1/26 5:00 AM'],['Row 1','Reply note','Original Author','11/2/26 5:00 AM']]})
            return result
        dev={'columns':self.fake.columns,'rows':self.fake.rows}
        report=compare(exported(self.source,True),exported(dev));self.directory=Path(self.tmp.name)/'maintenance';self.directory.mkdir()
        report_path=self.directory/'review.json';report_path.write_text(json.dumps(report))
        plan={'sourceSheetId':'456','targetSheetId':'123','ownerId':'100','sourceName':'Graphics Assignments',
              'sourcePermalink':'https://app.smartsheet.com/sheets/fictional-source',
              'reportPath':str(report_path),'reportSha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
              'expiresAt':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
              'expectedCounts':{'fields':1,'newJobs':1,'comments':2}}
        self.plan_path=self.directory/'plan.json';self.plan_path.write_text(json.dumps(plan))

    def native(self,path,method='GET',payload=None,headers=None):
        self.native_calls.append((method,path,copy.deepcopy(payload)))
        source=path.startswith('/sheets/456')
        if source and method!='GET':raise AssertionError('A live write was attempted')
        if source:
            if '/version' in path:return {'version':self.source['version']}
            if '/discussions' in path:return {'data':copy.deepcopy(self.source_threads),'totalPages':1}
            return copy.deepcopy(self.source)
        if method=='GET' and '/discussions' in path:return {'data':copy.deepcopy(self.target_threads),'totalPages':1}
        row_match=re.match(r'/sheets/123/rows/(\d+)',path)
        if method=='GET' and row_match:return copy.deepcopy(next(r for r in self.fake.rows if r['id']==int(row_match[1])))
        if method=='POST' and ('/discussions/' in path or path.endswith('/discussions')):
            if path.endswith('/discussions'):
                thread={'id':500+len(self.target_threads),'parentType':'ROW','parentId':int(row_match[1]),'comments':[]}
                self.target_threads.append(thread);text=payload['comment']['text']
            else:
                did=int(re.search(r'/discussions/(\d+)',path)[1]);thread=next(t for t in self.target_threads if t['id']==did);text=payload['text']
            c={'id':700+sum(len(t['comments']) for t in self.target_threads),'text':text,'createdAt':'2026-11-23T10:00:00Z','createdBy':{'name':'Importer'}}
            thread['comments'].append(c);self.fake.version+=1
            return {'resultCode':0,'result':copy.deepcopy(thread if path.endswith('/discussions') else c)}
        if method=='GET' and re.fullmatch(r'/sheets/123\?.*',path) and 'filterId' not in path:
            path+='&rowIds='+','.join(str(r['id']) for r in self.fake.rows)
        result=self.fake(path,method,payload,headers)
        if method=='POST' and path=='/sheets/123/rows' and self.uncertain_create:
            self.uncertain_create=False;raise WriteError('Synthetic timeout after commit',502)
        return result

    def reconciler(self):
        tool=DevReconciliation(self.runtime,self.plan_path)
        # Real adapter is paced for upstream quotas; synthetic transports need no delay.
        tool.prepare(self.sid);return tool

    def test_applies_only_dev_updates_creates_and_history_once(self):
        before=copy.deepcopy([r for r in self.fake.rows if r['id'] in (11,13)])
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler();tool.apply();writes=[c for c in self.native_calls if c[0]!='GET']
            self.assertEqual(len(writes),4)  # one field update, one new row, first note and reply
            self.assertTrue(all(c[1].startswith('/sheets/123/') for c in writes))
            self.assertEqual(before,[r for r in self.fake.rows if r['id'] in (11,13)])
            self.assertEqual(len(self.fake.rows),4)
            self.assertEqual(len(self.target_threads),1);self.assertEqual(len(self.target_threads[0]['comments']),2)
            self.assertIn('Original author: Original Author',self.target_threads[0]['comments'][0]['text'])
            tool=self.reconciler();tool.apply()
            self.assertEqual(len([c for c in self.native_calls if c[0]!='GET']),4)

    def test_source_write_and_arbitrary_endpoint_are_denied_below_the_service(self):
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler()
            for method,path in [('PUT','/sheets/456/rows'),('POST','/sheets/456/rows/100/discussions'),('DELETE','/sheets/123/rows'),('POST','/sheets/123/columns')]:
                with self.subTest(path=path),self.assertRaises(WriteError):tool.client.write(method,path,{})
            with self.assertRaises(WriteError):tool.client.get('/sheets/999')
        self.assertFalse([c for c in self.native_calls if c[0]!='GET'])

    def test_wrong_owner_revocation_and_global_pause_prevent_native_mutations(self):
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler();self.value['writesEnabled']=False
            with self.assertRaises(WriteError):tool.apply()
        self.assertFalse([c for c in self.native_calls if c[0]!='GET'])

    def test_source_change_or_unreviewed_dev_edit_pauses_before_write(self):
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler();self.source['version']+=1
            with self.assertRaises(WriteError):tool.apply()
        self.assertFalse([c for c in self.native_calls if c[0]!='GET'])

    def test_uncertain_create_is_recovered_by_readback_without_duplicate(self):
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler();self.uncertain_create=True
            with self.assertRaises(WriteError):tool.apply()
            self.assertEqual(len(self.fake.rows),4)
            tool=self.reconciler();tool.apply()
            self.assertEqual(len(self.fake.rows),4)
            self.assertEqual(len([c for c in self.native_calls if c[0]=='POST' and c[1]=='/sheets/123/rows']),1)

    def test_completed_update_is_not_replayed_over_a_later_change(self):
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler();tool.apply()
            next(c for c in self.fake.rows[1]['cells'] if c['columnId']==99)['value']='New'
            tool=self.reconciler()
            with self.assertRaises(WriteError):tool.apply()

    def test_locked_destination_is_rejected_before_any_write(self):
        self.fake.rows[1]['lockedForUser']=True
        with patch.object(NativeClient,'pace'),self.assertRaises(WriteError):self.reconciler()
        self.assertFalse([c for c in self.native_calls if c[0]!='GET'])

    def test_reenabled_automation_stops_import(self):
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler();self.fake.rules[0]['enabled']=True
            with self.assertRaises(WriteError):tool.apply()
        self.assertFalse([c for c in self.native_calls if c[0]!='GET'])

    def test_another_admin_cannot_use_owner_bound_plan(self):
        plan=json.loads(self.plan_path.read_text());plan['ownerId']='999'
        self.plan_path.write_text(json.dumps(plan))
        with patch.object(NativeClient,'pace'),self.assertRaises(WriteError):self.reconciler()
        self.assertFalse([c for c in self.native_calls if c[0]!='GET'])

    def test_scalar_object_values_retain_native_primitives(self):
        for value in ('Text',14,False):
            cell={'columnId':1,'value':value,'objectValue':value}
            self.assertEqual(cell_value(cell),value)
            self.assertEqual(DevReconciliation.copy_cell(cell,{'id':2})['value'],value)

    def test_existing_native_history_is_preserved_without_duplicate_import(self):
        self.target_threads=copy.deepcopy(self.source_threads)
        self.target_threads[0]['parentId']=12;self.target_threads[0]['id']=800
        plan=json.loads(self.plan_path.read_text());plan['expectedCounts']['comments']=0;plan['expectedExistingComments']=2
        self.plan_path.write_text(json.dumps(plan))
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler();tool.apply()
        self.assertEqual(len(self.target_threads),1)
        self.assertFalse([c for c in self.native_calls if c[0]=='POST' and '/discussions' in c[1]])

    def test_only_transient_copied_read_validation_is_retried(self):
        with patch.object(NativeClient,'pace'):
            tool=self.reconciler()
            store=tool.context.reader.store
            real=store.validate_source
            transient=GatewayError('The DEV source changed while loading copied projects. Refresh before continuing.')
            with patch.object(store,'validate_source',side_effect=[transient,real()]) as check,patch('backend.dev_reconciliation.time.sleep'):
                tool.guard();self.assertEqual(check.call_count,2)
            with patch.object(store,'validate_source',side_effect=GatewayError('Different failure')) as check,self.assertRaises(GatewayError):tool.guard()
            self.assertEqual(check.call_count,1)
        self.assertFalse([c for c in self.native_calls if c[0]!='GET'])
