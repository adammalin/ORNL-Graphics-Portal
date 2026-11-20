"""Self-accepted intake is one native create, bound to the authenticated creator."""
import copy
from test_pilot import PilotTestCase


class IntakeSelfAssignmentTests(PilotTestCase):
    def intake(self, **extra):
        return {'fields':{'title':'Self-assignment test','description':'Fictional intake',
                         'taskType':'Other','requestor':'Forged','email':'other@example.org'},**extra}

    def writes(self):
        return [c for c in self.fake.calls if c[0]!='GET']

    def test_designer_and_admin_create_accepted_own_job_in_one_native_write(self):
        self.value['invites'][0]['role']='admin'
        for who in ('designer','coord'):
            with self.subTest(who=who):
                client,_=self.login(who);before=len(self.writes())
                result=self.write(client,'/api/projects',self.intake(assignToMe=True))
                self.assertEqual(result.status_code,200,result.get_json())
                saved=result.get_json();project=self.project(client,saved['jobId'])
                email=self.profiles[who]['email']
                self.assertEqual((project['stage'],project['response'],project['requestedDesigner']),
                                 ('Accepted','accepted',email))
                self.assertEqual(project['email'],email)
                self.assertTrue(project['permissions']['edit'])
                self.assertTrue(project['permissions']['delete'])
                self.assertEqual(next(d['jobs'] for d in saved['teamWorkload'] if d['id']==email),1)
                changes=self.writes()[before:];self.assertEqual(len(changes),1)
                self.assertEqual(changes[0][0],'POST')
                titles={c['id']:c['title'] for c in self.fake.columns}
                changed={titles[c['columnId']] for c in changes[0][2][0]['cells']}
                self.assertNotIn('Assigned Designer',changed)  # The native formula resolves it.
                self.assertIn('Designer Response',changed)
                outsider,_=self.login('other')
                self.assertNotIn(project['id'],[p['id'] for p in self.get(outsider,'/api/projects').get_json()['projects']])

    def test_default_and_unchecked_intake_remain_new_and_unassigned(self):
        client,_=self.login('designer')
        for extra in ({},{'assignToMe':False}):
            saved=self.write(client,'/api/projects',self.intake(**extra)).get_json()
            project=self.project(client,saved['jobId'])
            self.assertEqual(project['stage'],'New')
            self.assertNotEqual(project['response'],'accepted')
            self.assertFalse(project['requestedDesigner'])

    def test_self_assignment_cannot_name_someone_else_or_use_truthy_strings(self):
        client,_=self.login('designer')
        bodies=[self.intake(assignToMe=v) for v in ('true',1,None,{'email':'other@example.org'})]
        bodies.append(self.intake(assignToMe=True,designer='other@example.org'))
        body=self.intake(assignToMe=True);body['fields']['requestedDesigner']='other@example.org';bodies.append(body)
        for body in bodies:
            with self.subTest(body=body):
                self.assertEqual(self.write(client,'/api/projects',body).status_code,400)
        self.assertEqual(self.writes(),[])

    def test_retries_do_not_duplicate_or_change_assignment_intent(self):
        client,_=self.login('designer');key='self-assigned-create-retry'
        body=self.intake(assignToMe=True)
        saved=self.write(client,'/api/projects',body,key).get_json()
        again=self.write(client,'/api/projects',body,key).get_json()
        self.assertEqual(saved['jobId'],again['jobId'])
        changed=copy.deepcopy(body);changed['assignToMe']=False
        self.assertEqual(self.write(client,'/api/projects',changed,key).status_code,409)
        self.assertEqual(len(self.writes()),1)
        project=self.project(client,saved['jobId'])
        modified={'action':'edit','revision':project['revision'],'fields':{'title':'Changed'},'assignToMe':True}
        self.assertEqual(self.write(client,'/api/projects/'+project['id'],modified).status_code,400)
        self.assertEqual(len(self.writes()),1)

    def test_viewer_and_paused_pilot_cannot_create_self_accepted_jobs(self):
        viewer,_=self.login('viewer')
        self.assertEqual(self.write(viewer,'/api/projects',self.intake(assignToMe=True)).status_code,403)
        client,_=self.login('designer');self.value['writesEnabled']=False
        self.assertEqual(self.write(client,'/api/projects',self.intake(assignToMe=True)).status_code,403)
        self.assertEqual(self.writes(),[])
