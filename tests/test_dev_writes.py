import copy
import http.cookiejar
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
from backend.server import SmartsheetReader, PortalServer, GatewayError
from backend.dev_store import DevStore, WriteError, FIELDS, YES, NO

class FakeSmartsheet:
    def __init__(self):
        names = list(dict.fromkeys(list(FIELDS.values()) + ['DEV Test Record','Graphics Req #','Requested Designer','Designer Response','Assigned Designer','Project Stage','Completed Date']))
        self.columns = [{'id':i+1,'title':n,'type':'TEXT_NUMBER'} for i,n in enumerate(names)]
        self.bytitle = {c['title']:c for c in self.columns}
        self.bytitle['Assigned Designer'].update(type='CONTACT_LIST',formula='=IF([Designer Response]@row = "Yes - I can take this job.", [Requested Designer]@row, "")',contactOptions=[{'name':'Test Designer','email':'designer@example.org'}])
        self.bytitle['Task Type'].update(type='MULTI_PICKLIST',options=['Figure/Diagram/Chart','Other'])
        self.bytitle['Priority']['options']=['Low','Normal','High','Urgent']
        self.bytitle['Graphics Req #']['systemColumnType']='AUTO_NUMBER'
        self.rows=[self.make_row(11,'TEST-1',True),self.make_row(12,'COPIED',False),self.make_row(13,'OUTSIDE',True)]
        self.rules=[{'id':1,'enabled':False}]
        self.saved_filter={'id':777,'name':'DEV - Demo projects','query':{'operator':'AND','includeParent':False,'criteria':[{'operator':'IS_CHECKED','columnId':self.bytitle['DEV Test Record']['id']}]}}
        self.version=1
        self.calls=[]
        self.timeout=False

    def make_row(self,rid,job,dev):
        values={'Description':'Synthetic project','Additional Details':'Original input','DEV Test Record':dev,'Graphics Req #':job,'Project Stage':'New','Priority':'Normal','Task Type':'Other','Requestor':'Example Requester','Requestor Email':'requester@example.org','Completed Date':None}
        row={'id':rid,'modifiedAt':str(self.version) if hasattr(self,'version') else '0','cells':[{'columnId':self.bytitle[n]['id'],'value':v} for n,v in values.items()]}
        row['cells'].append({'columnId':self.bytitle['Assigned Designer']['id'],'formula':self.bytitle['Assigned Designer']['formula']})
        return row

    def __call__(self,path,method='GET',payload=None,headers=None):
        self.calls.append((method,path,copy.deepcopy(payload)))
        if method=='GET':
            if urlsplit(path).path.endswith('/version'):return {'version':self.version}
            if '/automationrules' in path:return {'data':copy.deepcopy(self.rules)}
            if '/filters/' in path:return copy.deepcopy(self.saved_filter)
            query=parse_qs(urlsplit(path).query);ids=set(query.get('rowIds',[''])[0].split(','))
            if 'filterId' in query:ids={str(r['id']) for r in self.rows}
            return {'id':123,'name':'DEV Graphics Assignments','accessLevel':'OWNER','version':self.version,'columns':copy.deepcopy(self.columns),'rows':copy.deepcopy([r for r in self.rows if str(r['id']) in ids])}
        if self.timeout:raise WriteError('Uncertain test timeout',502)
        if path.endswith('/attachments'):
            rid=int(path.split('/')[-2]);row=next(r for r in self.rows if r['id']==rid)
            row.setdefault('attachments',[]).append({'id':900+len(row.get('attachments',[])),'attachmentType':'FILE','name':'sample.txt','mimeType':'text/plain'})
            self.version+=1
            return {'resultCode':0,'result':row['attachments'][-1]}
        if method=='POST':
            rid=max(r['id'] for r in self.rows)+1;row=self.make_row(rid,'TEST-'+str(rid),True);self.rows.append(row)
        else:row=next(r for r in self.rows if r['id']==payload[0]['id'])
        cells={c['columnId']:c for c in row['cells']}
        cells.update({c['columnId']:{k:v for k,v in c.items() if k!='strict'} for c in payload[0]['cells']})
        requested=cells.get(self.bytitle['Requested Designer']['id'],{}).get('objectValue')
        response=cells.get(self.bytitle['Designer Response']['id'],{}).get('value')
        assigned={'columnId':self.bytitle['Assigned Designer']['id'],'formula':self.bytitle['Assigned Designer']['formula']}
        if response==YES and requested:assigned.update(objectValue=requested,value=requested['email'],displayValue=requested['name'])
        cells[assigned['columnId']]=assigned;row['cells']=list(cells.values());self.version+=1;row['modifiedAt']=str(self.version)
        return {'resultCode':0,'result':[copy.deepcopy(row)]}

class DevWritesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.fake=FakeSmartsheet();self.path=Path(self.tmp.name)/'state.db'
        self.reader=SmartsheetReader('123',['11','12'],'test-placeholder',self.fake)
        self.reader.store=DevStore(self.reader,self.path);self.reader.store.validate_source();self.n=0
    def tearDown(self):self.tmp.cleanup()
    def key(self):self.n+=1;return 'test-operation-key-'+str(self.n)
    def project(self):return self.reader.projects(force=True)['projects'][0]
    def action(self,action,**values):return self.reader.store.perform(self.key(),{'action':action,'revision':self.project()['revision'],**values},'TEST-1')
    def writes(self):return [c for c in self.fake.calls if c[0]!='GET']
    def intake(self):return {'fields':{'title':'New synthetic request','description':'All original details','taskType':'Other','requestor':'Example Requester','email':'requester@example.org','dueDate':'2026-12-01','notes':'Retain these notes','audience':'Scientists','specifications':'Editable vector','requestorGroup':'Sample team','reference1':'https://example.org/reference','reference2':'','deliverables':'Two figures'}}

    def test_edit_persists_without_overwriting_formula_or_other_rows(self):
        original=copy.deepcopy(self.fake.rows[1:])
        data=self.action('edit',fields={'title':'Updated title','hours':8,'requestedDueDate':'2026-12-01','finalDueDate':'2026-12-04'})
        p=data['projects'][0];self.assertEqual(p['title'],'Updated title');self.assertEqual(p['dueDate'],'2026-12-04');self.assertEqual(p['requestedDueDate'],'2026-12-01')
        self.assertEqual(self.fake.rows[1:],original)
        payload=self.writes()[0][2][0]['cells'];self.assertNotIn(self.fake.bytitle['Assigned Designer']['id'],[c['columnId'] for c in payload])
        self.assertTrue(self.reader.store.verification()['protectedExistingCellsUnchanged'])

    def test_offer_response_and_closure_use_native_formula(self):
        self.action('offer',designer='designer@example.org');self.assertEqual(self.project()['response'],'')
        self.action('decline');self.assertEqual(self.project()['response'],'declined')
        self.action('offer',designer='designer@example.org');self.action('accept');self.assertEqual(self.project()['response'],'accepted')
        for stage in ['In Progress','In Review','Completed','Archived']:self.action('stage',stage=stage)
        p=self.project();self.assertEqual(p['stage'],'Archived');self.assertTrue(p['completedDate'])
        self.assertTrue(all(c['columnId']!=self.fake.bytitle['Assigned Designer']['id'] for _,_,body in self.writes() for c in body[0]['cells']))

    def test_stale_edit_unknown_fields_formulas_and_automation_fail_closed(self):
        revision=self.project()['revision'];self.action('edit',fields={'title':'Changed elsewhere'})
        count=len(self.writes())
        with self.assertRaises(WriteError) as error:self.reader.store.perform(self.key(),{'action':'edit','revision':revision,'fields':{'hours':99}},'TEST-1')
        self.assertEqual(error.exception.status,409)
        for fields in [{'assignedDesigner':'fake'},{'stage':'Archived'},{'hours':float('nan')},{'title':'x'*4001},{'reference1':'javascript:bad'}]:
            with self.assertRaises(WriteError):self.action('edit',fields=fields)
        with self.assertRaises(WriteError):self.action('stage',stage='Completed')
        self.fake.rules[0]['enabled']=True
        with self.assertRaises(WriteError):self.action('edit',fields={'hours':9})
        self.assertEqual(len(self.writes()),count)

    def test_intake_is_idempotent_retains_all_details_and_survives_restart(self):
        key=self.key();first=self.reader.store.perform(key,self.intake());again=self.reader.store.perform(key,self.intake())
        self.assertEqual(first['jobId'],again['jobId']);self.assertEqual(len(self.writes()),1)
        p=next(p for p in first['projects'] if p['id']==first['jobId'])
        for detail in ['All original details','Retain these notes','Scientists','Editable vector']:self.assertIn(detail,p['description'])
        self.assertEqual(p['requestorGroup'],'Sample team')
        r=SmartsheetReader('123',['11','12'],'test-placeholder',self.fake);r.store=DevStore(r,self.path)
        self.assertIn(first['jobId'],[p['id'] for p in r.projects()['projects']])
        self.assertEqual(r.store.perform(key,self.intake())['jobId'],first['jobId']);self.assertEqual(len(self.writes()),1)
        changed=self.intake();changed['fields']['title']='Different'
        with self.assertRaises(WriteError):r.store.perform(key,changed)

    def test_uncertain_create_is_never_automatically_repeated(self):
        self.fake.timeout=True;key=self.key()
        for _ in range(2):
            with self.assertRaises(WriteError):self.reader.store.perform(key,self.intake())
        self.assertEqual(len(self.writes()),1)

    def test_validated_native_dev_filter_discovers_new_synthetic_rows_only(self):
        r=SmartsheetReader('123',[],'test-placeholder',self.fake,filter_id='777')
        self.assertEqual({p['id'] for p in r.projects()['projects']},{'TEST-1','OUTSIDE'})
        self.fake.rows.append(self.fake.make_row(99,'NATIVE-NEW',True))
        self.assertIn('NATIVE-NEW',{p['id'] for p in r.projects(force=True)['projects']})
        self.fake.saved_filter['query']['criteria'][0]['operator']='IS_NOT_CHECKED'
        with self.assertRaises(GatewayError):r.projects(force=True)

    def test_multi_task_categories_are_written_as_complex_values(self):
        self.action('edit',fields={'taskType':['Other','Figure/Diagram/Chart']})
        cell=self.writes()[-1][2][0]['cells'][0]
        self.assertEqual(cell['objectValue'],{'objectType':'MULTI_PICKLIST','values':['Other','Figure/Diagram/Chart']})
        self.assertNotIn('value',cell)

    def test_attachment_upload_is_add_only_and_checks_row_and_revision(self):
        key=self.key();p=self.project()
        data=self.reader.store.upload(key,'TEST-1',p['revision'],'sample.txt','text/plain',b'Synthetic reference')
        self.assertEqual(len(data['projects'][0]['attachments']),1)
        self.reader.store.upload(key,'TEST-1',p['revision'],'sample.txt','text/plain',b'Synthetic reference')
        self.assertEqual(len(self.writes()),1)
        for job,rev,name,mime in [('COPIED',p['revision'],'x.txt','text/plain'),('OUTSIDE',p['revision'],'x.txt','text/plain'),('TEST-1',p['revision'],'x.txt','text/plain'),('TEST-1',self.project()['revision'],'x.html','text/html')]:
            with self.assertRaises(WriteError):self.reader.store.upload(self.key(),job,rev,name,mime,b'Example')
        self.assertEqual(len(self.writes()),1)

    def test_http_write_requires_session_origin_csrf_and_supported_route(self):
        server=PortalServer(('127.0.0.1',0),self.reader);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}';client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            client.open(base+'/').close()
            payload=json.dumps({'action':'edit','revision':self.project()['revision'],'fields':{'hours':5}}).encode()
            headers={'Content-Type':'application/json','Origin':base,'X-Portal-CSRF':server.csrf,'Idempotency-Key':self.key()}
            for overrides in [{'X-Portal-CSRF':'wrong'},{'Origin':'https://example.org'}]:
                with self.assertRaises(HTTPError) as error:client.open(Request(base+'/api/projects/TEST-1',data=payload,method='PATCH',headers={**headers,**overrides}))
                self.assertEqual(error.exception.code,403)
            with client.open(Request(base+'/api/projects/TEST-1',data=payload,method='PATCH',headers=headers)) as response:self.assertEqual(json.load(response)['projects'][0]['hours'],5)
            for method in ['DELETE','PUT']:
                with self.assertRaises(HTTPError) as error:client.open(Request(base+'/api/projects/TEST-1',data=b'{}',method=method,headers=headers))
                self.assertEqual(error.exception.code,405)
            with client.open(base+'/api/verification') as response:
                data=json.load(response);self.assertTrue(data['schemaUnchanged']);self.assertFalse(data['deleteEnabled'])
        finally:server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__':unittest.main()
