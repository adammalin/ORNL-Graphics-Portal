"""Durable first-show claims and per-principal tutorial-only preferences."""
from concurrent.futures import ThreadPoolExecutor
import copy
import unittest
import test_pilot as fixture
from backend.onboarding import Onboarding


@unittest.skipUnless(fixture.HAS_FLASK,'Install pilot requirements.')
class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.p=fixture.PilotTestCase();self.p.setUp()
        self.client,_=self.p.login('coord')
    def tearDown(self):self.p.tearDown()
    def post(self,body,client=None,**headers):
        client=client or self.client
        csrf=self.p.get(client,'/api/session').get_json()['csrf']
        return client.post('/api/onboarding',base_url=self.p.origin,json=body,headers={'Origin':self.p.origin,'X-Portal-CSRF':csrf,**headers})
    def test_first_claim_once_then_dismiss_and_replay_without_native_actions(self):
        before=copy.deepcopy(self.p.fake.rows);calls=len(self.p.fake.calls)
        first=self.post({'action':'claim'}).get_json();self.assertTrue(first['autoStart'])
        self.assertFalse(self.post({'action':'claim'}).get_json()['autoStart'])
        self.post({'action':'progress','track':'designer','lesson':3})
        self.post({'action':'dismiss','track':'designer','lesson':3})
        saved=self.p.get(self.client,'/api/onboarding').get_json()
        self.assertEqual((saved['status'],saved['lesson']),('dismissed',3))
        self.assertFalse(self.post({'action':'claim'}).get_json()['autoStart'])
        self.assertEqual(self.p.fake.rows,before);self.assertEqual(len(self.p.fake.calls),calls)
    def test_same_user_new_session_and_application_restart_do_not_repeat(self):
        self.post({'action':'complete','track':'coordinator','lesson':9})
        other,_=self.p.login('coord')
        self.assertFalse(self.post({'action':'claim'},other).get_json()['autoStart'])
        app=fixture.create_app(self.p.value,'synthetic-app-secret',oauth_transport=self.p.oauth,reader_factory=self.p.reader,reload_config=lambda:fixture.PilotConfig(self.p.value))
        data=Onboarding(app.extensions['pilot']).read('smartsheet:100','staff','coordinator')
        self.assertEqual(data['status'],'completed');self.assertTrue(data['completedAt'])
    def test_independent_identity_claims_and_role_choice_never_changes_authority(self):
        self.post({'action':'claim'})
        designer,_=self.p.login('designer')
        self.assertTrue(self.post({'action':'claim'},designer).get_json()['autoStart'])
        self.assertEqual(self.post({'action':'progress','track':'coordinator','lesson':1},designer).status_code,200)
        self.assertEqual(self.p.get(designer,'/api/session').get_json()['actor']['role'],'designer')
        self.assertEqual(self.p.get(designer,'/api/projects').get_json()['projects'],[])
    def test_parallel_first_claim_has_one_winner(self):
        service=Onboarding(self.p.runtime)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:service.write('smartsheet:parallel','staff','designer',{'action':'claim'}),range(6)))
        self.assertEqual(sum(r['autoStart'] for r in results),1)
    def test_auth_csrf_origin_body_and_track_validation(self):
        self.assertEqual(self.p.get(self.p.app.test_client(),'/api/onboarding').status_code,401)
        self.assertEqual(self.post({'action':'claim'},Origin='https://other.example').status_code,403)
        self.assertEqual(self.post({'action':'claim'},**{'X-Portal-CSRF':'wrong'}).status_code,403)
        for body in ({'action':'claim','role':'coordinator'},{'action':'progress','track':'requester'},{'action':'progress','lesson':True},{'action':'progress','lesson':999},{'action':'delete'}):
            self.assertEqual(self.post(body).status_code,400)
        self.assertEqual(self.post({'action':'claim','padding':'x'*5000}).status_code,413)
