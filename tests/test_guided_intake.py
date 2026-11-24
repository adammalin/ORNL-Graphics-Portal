"""Matched requester/staff workflows against the existing synthetic transport."""
import copy
from datetime import date
import secrets
import unittest
from unittest.mock import patch
import test_microsoft_intake as fixture
from backend.guided_intake import minimum_date

class GuidedIntakeTests(unittest.TestCase):
    def setUp(self):
        self.clock=patch('backend.guided_intake.today_eastern',return_value=date(2026,11,24));self.clock.start()
        self.p=fixture.MicrosoftIntakeTests();self.p.setUp()
        self.p.value['guidedIntake']={'enabled':True,'calendar':{'approved':True,'label':'Fictional qualification calendar','validThrough':'2027-09-30','closedDates':['2026-11-26','2026-11-27']}}
        self.client=self.p.ms_login()
    def tearDown(self):self.p.tearDown();self.clock.stop()
    def body(self):
        fields={**self.p.body()['fields'],'dueDate':'2026-11-30','eventDate':'2026-12-05','additionalServices':['reproduction','poster'],'serviceDetails':{'reproduction':{'kind':'Handouts / copies','quantity':'40','notes':'Fictional handout'},'poster':{'kind':'36 × 48 inches','quantity':'2','notes':'Fictional poster'}}}
        return {'fields':fields}
    def create(self,body=None,key=None):return self.p.ms_write(self.client,'/api/intake/requests',body or self.body(),key=key)
    def track(self,token,client=None):return self.p.get(client or self.client,'/api/intake/my-requests/'+token)
    def test_dates_calendar_coverage_and_validation_precede_writes(self):
        info=self.p.get(self.client,'/api/intake/session').get_json();self.assertTrue(info['guidedIntake']['ready']);self.assertEqual(info['guidedIntake']['earliest'],'2026-11-30')
        before=len(self.p.writes())
        for due in ['', '2026-11-25','2026-11-26','2026-12-05','2026-02-30','2028-01-03']:
            body=self.body();body['fields']['dueDate']=due;self.assertEqual(self.create(body).status_code,400,due)
        self.assertEqual(len(self.p.writes()),before)
        self.p.value['guidedIntake']['calendar']['approved']=False
        self.assertFalse(self.p.get(self.client,'/api/intake/session').get_json()['canSubmit']);self.assertEqual(self.create().status_code,503)
    def test_service_fields_roundtrip_without_exposing_later_internal_notes(self):
        response=self.create();self.assertEqual(response.status_code,200,response.get_json());saved=response.get_json()
        tracked=self.track(saved['receipt']).get_json();original=tracked['originalRequest']
        self.assertEqual(original['additionalServices'],['reproduction','poster']);self.assertEqual(original['serviceDetails']['poster']['quantity'],'2');self.assertEqual(original['notes'],self.body()['fields']['notes']);self.assertEqual(original['eventDate'],'2026-12-05')
        coord,_=self.p.login('coord');project=self.p.project(coord,saved['jobId'])
        self.assertIn('Service routing preview',project['description']);self.assertEqual(project['description'].count('Reproduction —'),1)
        row=next(r for r in self.p.fake.rows if any(c.get('value')==saved['jobId'] for c in r['cells']))
        cid=self.p.fake.bytitle['Additional Details']['id'];next(c for c in row['cells'] if c['columnId']==cid)['value']='PRIVATE INTERNAL NOTE';self.p.fake.version+=1
        self.assertNotIn('PRIVATE INTERNAL NOTE',self.track(saved['receipt']).get_data(as_text=True))
    def test_request_offer_accept_progress_and_complete_are_visible_to_owner_only(self):
        response=self.create();self.assertEqual(response.status_code,200,response.get_json());saved=response.get_json();job=saved['jobId'];token=saved['receipt']
        coord,_=self.p.login('coord');designer,_=self.p.login('designer')
        for client,action,fields,status in [(coord,'offer',{'designer':'designer@example.org'},'assigning'),(designer,'accept',{},'accepted'),(designer,'stage',{'stage':'In Progress'},'in_progress'),(designer,'stage',{'stage':'In Review'},'in_review'),(designer,'stage',{'stage':'Completed'},'completed')]:
            changed=self.p.action(client,action,job=job,**fields);self.assertEqual(changed.status_code,200,changed.get_json());self.assertEqual(self.track(token).get_json()['status'],status)
        self.p.ms.claims['oid']=fixture.OTHER;self.p.ms.profile['id']=fixture.OTHER;other=self.p.ms_login()
        self.assertEqual(self.track(token,other).status_code,404);self.assertEqual(self.p.get(other,'/api/intake/my-requests').get_json()['requests'],[])
        self.assertEqual(self.track(token,coord).status_code,401)
    def test_retries_keep_idempotency_and_do_not_fail_when_original_date_has_passed(self):
        key=secrets.token_urlsafe(20);first=self.create(key=key);self.assertEqual(first.status_code,200,first.get_json());writes=len(self.p.writes())
        with patch('backend.guided_intake.today_eastern',return_value=date(2026,12,2)):
            again=self.create(key=key);self.assertEqual(again.status_code,200,again.get_json());self.assertEqual(again.get_json()['receipt'],first.get_json()['receipt'])
            changed=self.body();changed['fields']['title']='A different job';self.assertEqual(self.create(changed,key).status_code,409)
        self.assertEqual(len(self.p.writes()),writes)
    def test_service_validation_rejects_hidden_unknown_and_invalid_fields(self):
        for mutate in [lambda f:f.update(additionalServices=['invented']),lambda f:f.update(additionalServices=[]),lambda f:f['serviceDetails']['poster'].update(quantity='1.5'),lambda f:f['serviceDetails']['poster'].update(kind='not a choice'),lambda f:f.update(eventDate=False)]:
            b=self.body();mutate(b['fields']);self.assertEqual(self.create(b).status_code,400)
        b=self.body();b['fields']['additionalServices']=[];b['fields']['serviceDetails']={};self.assertEqual(self.create(b).status_code,200)
    def test_calendar_sequences(self):
        for start,closed,end in [(date(2026,11,27),[],date(2026,12,1)),(date(2028,2,28),[],date(2028,3,1)),(date(2026,12,31),['2027-01-01'],date(2027,1,5))]:self.assertEqual(minimum_date(start,closed),end)
