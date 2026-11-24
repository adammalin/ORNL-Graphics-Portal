"""Minimum lead time is shared; bypass authority comes only from staff sessions."""
import copy
from datetime import date
import secrets
import unittest
from unittest.mock import patch
import test_microsoft_intake as fixture

class StaffIntakeRuleTests(unittest.TestCase):
    def setUp(self):
        self.clock=patch('backend.guided_intake.today_eastern',return_value=date(2026,11,24));self.clock.start()
        self.p=fixture.MicrosoftIntakeTests();self.p.setUp()
        self.rules={'enabled':True,'layout':'classic','calendar':{'approved':True,'label':'Fictional qualification calendar','validThrough':'2027-09-30','closedDates':['2026-11-26','2026-11-27']}}
        self.p.value['staffIntakeRules']=copy.deepcopy(self.rules);self.p.value['guidedIntake']=copy.deepcopy(self.rules)
        self.staff,_=self.p.login('designer');self.client=self.p.ms_login()
    def tearDown(self):self.p.tearDown();self.clock.stop()
    def body(self,date='2026-11-30',override=False):return {**self.p.body(),'overrideLeadTime':override,'fields':{**self.p.body()['fields'],'dueDate':date}}
    def save(self,body=None,key=None,client=None):return self.p.write(client or self.staff,'/api/projects',body or self.body(),key=key)
    def test_staff_capability_is_verified_and_not_in_client_session(self):
        data=self.p.get(self.staff,'/api/projects').json;self.assertTrue(data['staffIntake']['canOverride']);self.assertEqual(data['staffIntake']['earliest'],'2026-11-30')
        info=self.p.get(self.client,'/api/intake/session').json;self.assertNotIn('staffIntake',info);self.assertNotIn('canOverride',info['guidedIntake']);self.assertEqual(info['guidedIntake']['layout'],'classic')
        viewer,_=self.p.login('viewer');self.assertFalse(self.p.get(viewer,'/api/projects').json['staffIntake']['canOverride']);self.assertEqual(self.save(self.body('2026-11-24',True),client=viewer).status_code,403)
    def test_staff_minimum_is_enforced_and_override_is_recorded_with_verified_actor(self):
        before=len(self.p.writes());self.assertEqual(self.save(self.body('2026-11-24')).status_code,400);self.assertEqual(len(self.p.writes()),before)
        saved=self.save(self.body('2026-11-24',True));self.assertEqual(saved.status_code,200,saved.json)
        project=next(p for p in saved.json['projects'] if p['id']==saved.json['jobId'])
        self.assertEqual(project['requestedDueDate'],'2026-11-24');self.assertEqual(project['email'],'designer@example.org');self.assertEqual(project['stage'],'New')
        self.assertIn('Lead-time minimum overridden by verified Graphics staff: Designer Tester (designer@example.org)',project['description'])
    def test_override_does_not_bypass_past_closed_invalid_dates_or_missing_calendar(self):
        before=len(self.p.writes())
        for due in ['2026-11-23','2026-11-26','2026-11-28','2026-02-30','2028-01-03','']:
            response=self.save(self.body(due,True));self.assertEqual(response.status_code,400,(due,response.json))
        self.p.value['staffIntakeRules']['calendar']['approved']=False
        self.assertEqual(self.save(self.body('2026-11-24',True)).status_code,503)
        self.assertEqual(len(self.p.writes()),before)
    def test_client_cannot_forge_staff_override_even_with_a_staff_cookie(self):
        from backend.pilot import SESSION_COOKIE
        cookie=self.staff.get_cookie(SESSION_COOKIE,domain='pilot.example.org')
        self.assertIsNotNone(cookie)
        self.client.set_cookie(SESSION_COOKIE,cookie.value,domain='pilot.example.org',secure=True)
        before=len(self.p.writes())
        for key in ['override','overrideLeadTime','canOverride']:
            body=self.p.body();body['fields'][key]=True
            self.assertEqual(self.p.ms_write(self.client,'/api/intake/requests',body).status_code,400)
            self.assertEqual(self.p.ms_write(self.client,'/api/intake/requests',{**self.p.body(),key:True}).status_code,400)
        body=self.p.body();body['fields']['dueDate']='2026-11-24'
        self.assertEqual(self.p.ms_write(self.client,'/api/intake/requests',body).status_code,400)
        self.assertEqual(len(self.p.writes()),before)
    def test_override_retry_does_not_duplicate_and_cannot_change_intent(self):
        key=secrets.token_urlsafe(20);body=self.body('2026-11-24',True);first=self.save(body,key);self.assertEqual(first.status_code,200,first.json);writes=len(self.p.writes())
        with patch('backend.guided_intake.today_eastern',return_value=date(2026,12,2)):
            again=self.save(body,key);self.assertEqual(again.status_code,200,again.json);self.assertEqual(again.json['jobId'],first.json['jobId'])
            changed=copy.deepcopy(body);changed['overrideLeadTime']=False;self.assertEqual(self.save(changed,key).status_code,409)
        self.assertEqual(len(self.p.writes()),writes)
    def test_sample_calendar_is_limited_to_dev_staff_not_real_employee_intake(self):
        for key in ['staffIntakeRules','guidedIntake']:
            self.p.value[key]['calendar'].update(approved=False,testOnly=True)
        self.assertTrue(self.p.get(self.staff,'/api/projects').json['staffIntake']['testOnly'])
        self.assertEqual(self.save().status_code,200)
        self.assertFalse(self.p.get(self.client,'/api/intake/session').json['canSubmit'])
        self.assertEqual(self.p.ms_write(self.client,'/api/intake/requests',self.p.body()).status_code,503)
    def test_classic_client_has_same_server_rules_and_service_storage(self):
        fields={**self.p.body()['fields'],'dueDate':'2026-11-30','additionalServices':['video','poster'],'serviceDetails':{'video':{'kind':'Editing','notes':'Fictional video'},'poster':{'kind':'36 × 48 inches','quantity':'2','notes':'Fictional poster'}},'eventDate':'2026-12-05'}
        response=self.p.ms_write(self.client,'/api/intake/requests',{'fields':fields});self.assertEqual(response.status_code,200,response.json)
        tracked=self.p.get(self.client,'/api/intake/my-requests/'+response.json['receipt']).json
        self.assertEqual(tracked['originalRequest']['serviceDetails'],fields['serviceDetails']);self.assertEqual(tracked['originalRequest']['eventDate'],'2026-12-05')
    def test_staff_additional_services_save_with_override_and_verified_identity(self):
        body=self.body('2026-11-24',True)
        body['fields'].update(additionalServices=['video','reproduction','poster'],serviceDetails={'video':{'kind':'Editing','notes':'Synthetic video request'},'reproduction':{'kind':'Handouts / copies','quantity':'40','notes':'Synthetic copies'},'poster':{'kind':'36 × 48 inches','quantity':'2','notes':'Synthetic posters'}},eventDate='2026-12-05')
        response=self.save(body);self.assertEqual(response.status_code,200,response.json)
        project=next(p for p in response.json['projects'] if p['id']==response.json['jobId'])
        for value in ['Video production: Editing','Quantity 40','Quantity 2','2026-12-05','Lead-time minimum overridden by verified Graphics staff: Designer Tester']:
            self.assertIn(value,project['description'])
        self.assertEqual(project['description'].count('Reproduction —'),1)
        self.assertEqual(project['email'],'designer@example.org')
