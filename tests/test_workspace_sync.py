"""Version polling, fewer upstream reads, and confirmed acceptance projection."""
import copy
import time
from test_pilot import PilotTestCase
from backend.server import normalize_sheet
from backend.intake_choices import department_value

class WorkspaceSyncTests(PilotTestCase):
    def test_unchanged_poll_reads_only_version_but_revalidates_source_periodically(self):
        client,data=self.login('coord');self.fake.calls.clear()
        response=self.get(client,'/api/projects?sinceVersion='+str(data['sourceVersion']))
        self.assertEqual(response.get_json()['unchanged'],True)
        self.assertEqual([c[1] for c in self.fake.calls],['/sheets/123/version'])
        self.readers[-1]._cache_time-=61;self.fake.calls.clear()
        response=self.get(client,'/api/projects?sinceVersion='+str(data['sourceVersion']))
        self.assertIn('projects',response.get_json());self.assertEqual(len(self.fake.calls),3)
        self.access['coord']='DENIED'
        self.assertEqual(self.get(client,'/api/projects?sinceVersion=1').status_code,502)

    def test_changed_version_refreshes_job_and_invalid_version_is_rejected(self):
        client,data=self.login('coord');cid=self.fake.bytitle['Description']['id']
        next(c for c in self.fake.rows[0]['cells'] if c['columnId']==cid)['value']='Updated by native editor'
        self.fake.version+=1
        response=self.get(client,'/api/projects?sinceVersion='+str(data['sourceVersion'])).get_json()
        self.assertEqual(response['projects'][0]['title'],'Updated by native editor')
        self.assertEqual(self.get(client,'/api/projects?sinceVersion=bad').status_code,400)
        self.value['invites']=[]
        self.assertNotEqual(self.get(client,'/api/projects?sinceVersion=2').status_code,200)

    def test_workspace_includes_same_capabilities_without_second_native_read(self):
        client,_=self.login('coord');self.fake.calls.clear()
        data=self.get(client,'/api/projects').get_json();self.assertEqual(len(self.fake.calls),2)
        self.assertEqual(data['capabilities'],self.get(client,'/api/v1/capabilities').get_json())

    def test_intake_uses_one_fresh_preflight_and_one_confirmed_readback(self):
        self.value['copiedRowIds']=['12'];client,_=self.login('coord');self.fake.calls.clear()
        body={'fields':{'title':'Fictional sync test','description':'A synthetic example','taskType':['Other'],
              'dueDate':'','requestorGroup':'Fictional Physics Group','notes':'','deliverables':'One flyer'}}
        response=self.write(client,'/api/projects',body);self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(len([c for c in self.fake.calls if c[0]=='GET']),7)
        job=next(p for p in response.get_json()['projects'] if p['id']==response.get_json()['jobId'])
        self.assertEqual(job['requestorGroup'],'Fictional Physics Group')
        self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),1)

    def test_recorded_acceptance_does_not_wait_for_formula_and_stage_alone_is_insufficient(self):
        self.fake.rows[0]['cells'] += [
          {'columnId':self.fake.bytitle['Requested Designer']['id'],'value':'designer@example.org'},
          {'columnId':self.fake.bytitle['Designer Response']['id'],'value':'Yes - I can take this job.'}]
        self.fake.rows[0]['cells']=[c for c in self.fake.rows[0]['cells'] if c['columnId']!=self.fake.bytitle['Assigned Designer']['id']]
        client,data=self.login('designer');self.assertEqual(data['projects'][0]['response'],'accepted')
        self.assertEqual(data['projects'][0]['requestedDesigner'],'designer@example.org')
        response=next(c for c in self.fake.rows[0]['cells'] if c['columnId']==self.fake.bytitle['Designer Response']['id'])
        response['value']='';self.fake.version+=1
        self.assertEqual(self.get(client,'/api/projects').get_json()['projects'][0]['response'],'')

    def test_department_parser_only_uses_explicit_fields_and_portal_marker(self):
        display=lambda c:c.get('value','')
        self.assertEqual(department_value({'Additional Details':{'value':'Physics probably?'}},display),'')
        self.assertEqual(department_value({'Additional Details':{'value':'Brief\n\nRequestor group / department:\nFictional Physics'}},display),'Fictional Physics')
