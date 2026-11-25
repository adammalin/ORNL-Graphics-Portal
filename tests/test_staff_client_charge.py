"""Native client/charge persistence and verified submitter authorization."""
import copy
from test_pilot import PilotTestCase

class StaffClientChargeTests(PilotTestCase):
    def body(self,**extra):
        return {'fields':{'title':'Fictional client intake','description':'Client supplied details',
                'taskType':'Other','dueDate':'2026-12-01','requestor':'Fictional Client',
                'email':'client@example.org','chargeNumber':'DEMO26QA1'},'onBehalfOf':True,**extra}

    def test_client_and_native_charge_survive_new_session_with_original_staff_actor(self):
        staff,_=self.login('designer');key='staff-client-charge-create'
        result=self.write(staff,'/api/projects',self.body(),key)
        self.assertEqual(result.status_code,200,result.get_json());job=result.json['jobId']
        again=self.write(staff,'/api/projects',self.body(),key)
        self.assertEqual(again.json['jobId'],job)
        writes=[c for c in self.fake.calls if c[0]!='GET'];self.assertEqual(len(writes),1)
        titles={c['id']:c['title'] for c in self.fake.columns}
        native={titles[c['columnId']]:c.get('value') for c in writes[0][2][0]['cells']}
        self.assertEqual(native['Charge #'],'DEMO26QA1');self.assertEqual(native['Requestor'],'Fictional Client')
        self.assertEqual(native['Requestor Email'],'client@example.org')
        fresh,_=self.login('designer');p=self.project(fresh,job)
        self.assertEqual((p['requestor'],p['email'],p['chargeNumber']),('Fictional Client','client@example.org','DEMO26QA1'))
        self.assertEqual(p['chargeValidation'],'Pending validation')
        self.assertEqual(p['submission']['actor']['email'],'designer@example.org')
        self.assertTrue(p['permissions']['delete']);self.assertEqual(p['stage'],'New');self.assertFalse(p['requestedDesigner'])
        stranger,_=self.login('other');self.assertNotIn(job,[x['id'] for x in self.get(stranger,'/api/projects').json['projects']])
        body=self.body();body['fields']['email']='changed@example.org'
        self.assertEqual(self.write(staff,'/api/projects',body,key).status_code,409)

    def test_default_submission_remains_bound_to_verified_staff_identity(self):
        staff,_=self.login('designer');body=self.body(onBehalfOf=False)
        r=self.write(staff,'/api/projects',body);self.assertEqual(r.status_code,200,r.json)
        p=self.project(staff,r.json['jobId']);self.assertEqual(p['email'],'designer@example.org')

    def test_edit_existing_client_and_charge_does_not_change_creator_or_unrelated_cells(self):
        staff,_=self.login('designer');body=self.body(onBehalfOf=False);body['fields'].pop('chargeNumber')
        job=self.write(staff,'/api/projects',body).json['jobId'];p=self.project(staff,job);before=copy.deepcopy(self.fake.rows)
        r=self.write(staff,'/api/projects/'+job,{'action':'edit','revision':p['revision'],'fields':{'requestor':'Fictional Client','email':'client@example.org','chargeNumber':'DEMO26QA1'}})
        self.assertEqual(r.status_code,200,r.json);p=self.project(staff,job)
        self.assertEqual(p['submission']['actor']['email'],'designer@example.org');self.assertEqual(p['chargeNumber'],'DEMO26QA1')
        self.assertEqual(self.fake.rows[:3],before[:3]);self.assertTrue(p['permissions']['delete']);self.assertEqual(p['stage'],'New')

    def test_missing_client_invalid_email_charge_actor_and_non_boolean_are_rejected(self):
        staff,_=self.login('designer')
        bodies=[]
        for key,value in [('requestor',''),('email','invalid'),('chargeNumber','bad\ncode'),('chargeNumber','x'*81)]:
            b=self.body();b['fields'][key]=value;bodies.append(b)
        bodies.extend([self.body(onBehalfOf='true'),{**self.body(),'submittedBy':'forged@example.org'}])
        for body in bodies:
            with self.subTest(body=body):self.assertEqual(self.write(staff,'/api/projects',body).status_code,400)
        self.assertFalse([c for c in self.fake.calls if c[0]!='GET'])

    def test_readonly_and_paused_writes_block_client_submission(self):
        viewer,_=self.login('viewer');self.assertEqual(self.write(viewer,'/api/projects',self.body()).status_code,403)
        staff,_=self.login('designer');self.value['writesEnabled']=False
        self.assertEqual(self.write(staff,'/api/projects',self.body()).status_code,403)
