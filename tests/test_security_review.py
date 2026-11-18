"""Bounded adversarial tests against fictional transports; no live security probes."""
import io
import json
import secrets
from unittest.mock import patch
from test_pilot import PilotTestCase
from test_dev_writes import FakeSmartsheet
from backend.server import SmartsheetReader,GatewayError

class SecurityReviewTests(PilotTestCase):
    def raw(self,client,path,body,mime='application/json',method='PATCH'):
        csrf=self.get(client,'/api/session').get_json()['csrf']
        return client.open(path,method=method,base_url=self.origin,data=body,content_type=mime,
            headers={'Origin':self.origin,'X-Portal-CSRF':csrf,'Idempotency-Key':secrets.token_urlsafe(20)})

    def test_regular_writes_reject_duplicate_keys_nonfinite_values_and_large_json_before_source_reads(self):
        c,data=self.login('coord');rev=json.dumps(data['projects'][0]['revision']);self.fake.calls.clear()
        bodies=[('{"action":"edit","revision":'+rev+',"fields":{"hours":1,"hours":9}}').encode(),
                ('{"action":"stage","action":"edit","revision":'+rev+',"fields":{"hours":1}}').encode(),
                ('{"action":"edit","revision":'+rev+',"fields":{"hours":NaN}}').encode(),
                ('{"action":"edit","revision":'+rev+',"fields":{"hours":1e999}}').encode(),
                b'{"fields":'+b'['*1500+b'0'+b']'*1500+b'}']
        for body in bodies:self.assertEqual(self.raw(c,'/api/projects/TEST-1',body).status_code,400)
        self.assertEqual(self.raw(c,'/api/projects/TEST-1',b' '*300000+b'{}').status_code,413)
        self.assertEqual(self.raw(c,'/api/projects/TEST-1',b'{}','text/plain').status_code,415)
        self.assertEqual(self.fake.calls,[])

    def test_preferences_and_sharing_use_the_same_strict_json_parser(self):
        c,_=self.login('coord')
        self.assertEqual(self.raw(c,'/api/onboarding',b'{"action":"claim","action":"complete"}',method='POST').status_code,400)
        self.assertEqual(self.raw(c,'/api/onboarding',b'{"action":"claim"}','text/plain',method='POST').status_code,415)
        with self.get(c,'/http-client.js') as response:self.assertEqual(response.status_code,200)
        self.assertEqual([x for x in self.fake.calls if x[0]!='GET'],[])

    def test_error_routes_keep_browser_protections_and_private_paths_are_not_served(self):
        c=self.app.test_client()
        for path in ['/api/projects','/.git/config','/.local/pilot-config.json','/assets/fonts/../../../backend/pilot.py','/assets/fonts/../../.local/pilot.sqlite3']:
            response=self.get(c,path);self.assertIn(response.status_code,(401,404))
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
            self.assertNotIn(b'synthetic-app-secret',response.data)
        for method in ('DELETE','PUT','OPTIONS','TRACE'):
            self.assertEqual(c.open('/api/projects/TEST-1',method=method,base_url=self.origin).status_code,405)

    def test_role_downgrade_during_read_cannot_reuse_old_coordinator_authority(self):
        c,_=self.login('coord');reader=self.readers[-1];original=reader.projects
        def downgraded(*a,**kw):
            result=original(*a,**kw)
            next(x for x in self.value['invites'] if x['email']=='coordinator@example.org')['role']='designer'
            return result
        reader.projects=downgraded
        result=self.get(c,'/api/projects').get_json()
        self.assertEqual(result['actor']['role'],'designer');self.assertEqual(result['projects'],[])

    def test_attachment_parameters_are_normalized_and_active_content_is_download_only(self):
        c,_=self.login('coord')
        self.runtime.jobs.attachment=lambda *a:(b'<h1>inert source text</h1>','Text/Plain; charset=UTF-8','sample.txt')
        r=self.get(c,'/api/projects/TEST-1/attachments/900')
        self.assertTrue(r.headers['Content-Type'].startswith('text/plain'));self.assertTrue(r.headers['Content-Disposition'].startswith('inline'))
        self.runtime.jobs.attachment=lambda *a:(b'<script>never rendered</script>','text/html','example.html')
        r=self.get(c,'/api/projects/TEST-1/attachments/900')
        self.assertEqual(r.headers['Content-Type'],'application/octet-stream');self.assertTrue(r.headers['Content-Disposition'].startswith('attachment'))

    def test_attachment_fetch_rejects_unsafe_hosts_ports_and_malformed_urls_without_credentials(self):
        fake=FakeSmartsheet();fake.rows[0]['attachments']=[{'id':900,'attachmentType':'FILE','name':'sample.txt','mimeType':'text/plain'}]
        metadata={'id':900,'name':'sample.txt','mimeType':'text/plain'}
        def transport(path):return metadata if path.endswith('/attachments/900') else fake(path)
        reader=SmartsheetReader('123',['11'],'fictional-token',transport)
        bad=['http://bucket.s3.amazonaws.com/a','https://evil.example/a','https://bucket.s3.amazonaws.com:8443/a',
             'https://bucket.s3.amazonaws.com:bad/a','https://[broken','https://user:password@bucket.s3.amazonaws.com/a',None]
        with patch.object(reader._opener,'open') as network:
            for url in bad:
                metadata['url']=url
                with self.assertRaises(GatewayError):reader.attachment('TEST-1','900')
            network.assert_not_called()
        metadata['url']='https://bucket.s3.amazonaws.com/a?signature=fictional'
        with patch.object(reader._opener,'open',return_value=io.BytesIO(b'Fictional file')) as network:
            self.assertEqual(reader.attachment('TEST-1','900')[0],b'Fictional file')
            self.assertNotIn('Authorization',dict(network.call_args.args[0].header_items()))

    def test_login_attempt_budget_is_bounded_without_contacting_identity_provider(self):
        c=self.app.test_client()
        for _ in range(30):self.assertEqual(self.get(c,'/auth/smartsheet/login').status_code,303)
        self.assertEqual(self.get(c,'/auth/smartsheet/login').status_code,429)
        self.assertEqual(len(self.runtime.pending),30);self.assertEqual(self.oauth_calls,[])

    def test_restart_probe_accepts_a_closed_connection_but_rejects_a_live_listener(self):
        import socket
        from backend.pilot import check_port_available
        listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1];listener.listen()
        try:
            with self.assertRaisesRegex(Exception,'already in use'):check_port_available(port)
            with socket.create_connection(('127.0.0.1',port),timeout=2) as client:
                connection,_=listener.accept();connection.close()
                self.assertEqual(client.recv(1),b'')
        finally:listener.close()
        check_port_available(port)
