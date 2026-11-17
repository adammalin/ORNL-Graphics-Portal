import importlib.util
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen, HTTPCookieProcessor, build_opener
import http.cookiejar

spec = importlib.util.spec_from_file_location('portal_server', Path(__file__).resolve().parents[1] / 'backend/server.py')
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)

def fake_sheet():
    names = ['DEV Test Record','Graphics Req #','Description','Additional Details','Project Stage','Requested Designer','Assigned Designer','Designer Response','Estimated Hours','Reference link 1']
    columns = [{'id': i + 1,'title': name} for i,name in enumerate(names)]
    def row(rid, dev, job):
        return {'id': rid, 'cells':[{'columnId':1,'value':dev},{'columnId':2,'value':job},{'columnId':3,'value':'Synthetic project'},{'columnId':4,'value':'Synthetic brief'},{'columnId':5,'value':'New'},{'columnId':10,'value':'javascript:alert(1)'}]}
    return {'id':123,'name':'DEV Graphics Assignments','version':9,'columns':columns,'rows':[row(11, True,'DEMO-1'),row(12,False,'COPIED'),row(13,True,'OUTSIDE-ALLOWLIST')]}

class GatewayTests(unittest.TestCase):
    def reader(self):
        self.calls=[]
        def transport(path):
            self.calls.append(path)
            return fake_sheet()
        return server_module.SmartsheetReader('123',['11','12'],'test-placeholder',transport)

    def test_allowlist_and_dev_marker_both_required(self):
        r=self.reader(); data=r.projects()
        self.assertEqual([p['id'] for p in data['projects']],['DEMO-1'])
        self.assertEqual(data['projects'][0]['references'],[])
        self.assertIn('rowIds=11%2C12',self.calls[0])
        self.assertEqual(r.audit,[{'method':'GET','resource':'allowlisted-dev-rows'}])
        r.projects(); self.assertEqual(len(self.calls),1)

    def test_wrong_source_and_empty_allowlist_fail_closed(self):
        with self.assertRaises(server_module.GatewayError):
            server_module.SmartsheetReader('123',[],'test-placeholder')
        with self.assertRaises(server_module.GatewayError):
            server_module.normalize_sheet({**fake_sheet(),'name':'Production'},'123',{'11'})
        with self.assertRaises(server_module.GatewayError):
            server_module.normalize_sheet(fake_sheet(),'456',{'11'})

    def test_attachment_ids_cannot_escape_verified_job_inventory(self):
        r=self.reader();r.projects()
        with self.assertRaises(server_module.GatewayError):r.attachment('DEMO-1','999')
        self.assertEqual(len(self.calls),1)

    def test_loopback_host_cookie_and_mutation_guards(self):
        reader=self.reader();server=server_module.PortalServer(('127.0.0.1',0),reader)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            with self.assertRaises(HTTPError) as denied:urlopen(base+'/api/projects')
            self.assertEqual(denied.exception.code,401)
            with client.open(base+'/') as response:self.assertEqual(response.status,200)
            with client.open(base+'/runtime-config.js') as response:self.assertIn(b'dev-readonly',response.read())
            with client.open(base+'/api/projects') as response:self.assertEqual(json.load(response)['mode'],'dev-readonly')
            with client.open(base+'/api/verification') as response:
                receipt=json.load(response)
                self.assertTrue(receipt['sheetVersionUnchanged'])
                self.assertFalse(receipt['nativeWritesEnabled'])
                self.assertTrue(all(r['method']=='GET' for r in receipt['upstreamRequests']))
            for method in ['POST','PUT','PATCH','DELETE']:
                with self.assertRaises(HTTPError) as rejected:client.open(Request(base+'/api/projects',data=b'{}',method=method))
                self.assertEqual(rejected.exception.code,405)
            with self.assertRaises(HTTPError) as rejected:client.open(Request(base+'/api/projects',headers={'Origin':'https://example.org'}))
            self.assertEqual(rejected.exception.code,401)
            with self.assertRaises(HTTPError) as rejected:client.open(Request(base+'/',headers={'Host':'example.org'}))
            self.assertEqual(rejected.exception.code,403)
            with self.assertRaises(HTTPError) as rejected:client.open(base+'/%2e%2e/README.md')
            self.assertEqual(rejected.exception.code,404)
            self.assertTrue(all(x['method']=='GET' for x in reader.audit))
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
