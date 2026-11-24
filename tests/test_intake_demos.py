"""Comparison pages are gated, non-active and isolated from native writes."""
import json
from pathlib import Path
from test_pilot import PilotTestCase

class IntakeDemoTests(PilotTestCase):
    def test_anonymous_pages_and_configuration_require_existing_staff_auth(self):
        client=self.app.test_client()
        for path in ['/intake-demos','/intake-demos/classic','/intake-demos/guided','/intake-demos/classic/config.js','/intake-demos/guided/config.js']:
            r=self.get(client,path)
            self.assertEqual(r.status_code,401,path)
            self.assertNotIn(b'window.PORTAL_CONFIG=',r.data)
            self.assertIn(b'Continue with Smartsheet',r.data)
    def test_both_versions_are_non_active_even_for_read_only_staff(self):
        client,_=self.login('viewer')
        before=len([c for c in self.fake.calls if c[0]!='GET'])
        for version in ['classic','guided']:
            r=self.get(client,'/intake-demos/'+version)
            self.assertEqual(r.status_code,200)
            self.assertIn("connect-src 'none'",r.headers['Content-Security-Policy'])
            self.assertIn("form-action 'none'",r.headers['Content-Security-Policy'])
            self.assertIn('/intake-demos/'+version+'/config.js',r.text)
            self.assertIn('/intake-demos/guided',r.text)
            self.assertIn('/intake-demos/classic',r.text)
            config=self.get(client,'/intake-demos/'+version+'/config.js')
            value=json.loads(config.text.split('Object.freeze(',1)[1][:-2])
            self.assertEqual(value['dataMode'],'demo');self.assertTrue(value['intakeComparison'])
            self.assertFalse(value['demoCalendar']['notificationsEnabled'])
            self.assertIn('official ORNL calendar pending',value['demoCalendar']['calendarLabel'])
            self.assertNotIn('csrf',value);self.assertNotIn('actor',value)
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),before)
    def test_demo_post_disabled_and_actual_intake_unchanged(self):
        client,_=self.login('coord')
        csrf=self.get(client,'/api/session').json['csrf']
        for path in ['/intake-demos/classic','/intake-demos/guided','/intake-demos/guided/submit']:
            response=client.post(path,base_url=self.origin,json={'fields':{'title':'Must never create'}},headers={'Origin':self.origin,'X-Portal-CSRF':csrf})
            self.assertEqual(response.status_code,405)
        self.assertFalse([c for c in self.fake.calls if c[0]!='GET'])
        self.assertIn('pilot',self.get(client,'/runtime-config.js').text)
        self.assertEqual(self.get(client,'/auth/microsoft/login').status_code,503)
        self.assertIn('/intake-demos/guided',self.get(client,'/').text)
        self.assertEqual(self.get(client,'/intake-demos/not-a-version').status_code,404)
    def test_guided_demo_has_no_network_or_upload_adapter(self):
        script=(Path(__file__).parents[1]/'web/intake-demo.js').read_text()
        self.assertNotIn('fetch(',script);self.assertNotIn('XMLHttpRequest',script)
        self.assertNotIn('/api/',script)
        self.assertIn('Nothing submitted',script)

    def test_client_demo_modules_are_served_without_enabling_microsoft(self):
        client,_=self.login('coord')
        self.assertIn('/assets/intake/workspace-entry.js',self.get(client,'/intake-demos/classic').text)
        for name in ['workspace-entry.js','classic-demo.js','classic-client-form.js']:
            response=self.get(client,'/assets/intake/'+name)
            self.assertEqual(response.status_code,200)
        script=self.get(client,'/assets/intake/classic-demo.js').text
        self.assertNotIn('fetch(',script)
        self.assertNotIn('/api/',script)
        self.assertIn('classicClientForm(session)',script)
        self.assertIn('classicClientForm(session)',self.get(client,'/intake.js').text)
        self.assertEqual(self.get(client,'/auth/microsoft/login').status_code,503)
