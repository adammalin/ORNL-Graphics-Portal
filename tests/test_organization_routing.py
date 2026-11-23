"""Organization-to-cell mapping and one coordinator, using fictional data only."""
import copy
from itertools import product
from unittest.mock import patch

from test_pilot import PilotTestCase
from backend.organizations import resolve, validate_policy
from backend.dev_store import WriteError
from backend.pilot import PilotConfig


POLICY = {'version': 1,
    'managers': {'science': {'email': 'science@example.org', 'name': 'Science Coordinator'},
                 'operations': {'email': 'operations@example.org', 'name': 'Operations Coordinator'},
                 'central': {'email': 'coordinator@example.org', 'name': 'Central Coordinator'}},
    'divisionOverrides': [{'values': ['Shared Facility'], 'manager': 'operations'}],
    'directorates': [{'values': ['Fictional Science'], 'manager': 'science'},
                     {'values': ['Fictional Operations'], 'manager': 'operations'}],
    'default': 'central'}


class OrganizationRoutingTests(PilotTestCase):
    def setUp(self):
        super().setUp()
        self.value['invites'] += [{'email': p['email'], 'role': 'coordinator'}
                                  for p in list(POLICY['managers'].values())[:2]]
        self.value['organizationRouting'] = copy.deepcopy(POLICY)
        self.fake.bytitle['Owner Directorate'].update(type='PICKLIST', options=['Fictional Science','Fictional Operations','Unmapped Directorate'])
        self.fake.bytitle['Owner Division/Office/Facility'].update(type='PICKLIST', options=['Shared Facility','Research','Other'])
        manager = {'id': max(c['id'] for c in self.fake.columns)+1, 'title': 'Assigning Manager', 'type': 'CONTACT_LIST'}
        self.fake.columns.append(manager); self.fake.bytitle[manager['title']] = manager

    def body(self, **extra):
        return {'fields': {'title': 'Fictional organization request', 'description': 'Original client brief',
                'taskType': ['Other'], 'directorate': 'Fictional Science', 'division': 'Research',
                'requestorGroup': 'A new fictional group', 'notes': 'Retain the supplied details', **extra}}

    def native(self, row, title):
        return next((c.get('value') for c in row['cells'] if c['columnId']==self.fake.bytitle[title]['id']),None)

    def test_create_maps_org_cells_and_routes_atomically_without_email_or_designer_assignment(self):
        client,_ = self.login('coord');before=copy.deepcopy(self.fake.rows)
        response=self.write(client,'/api/projects',self.body());self.assertEqual(response.status_code,200,response.get_json())
        row=self.fake.rows[-1]
        for title,value in [('Owner Directorate','Fictional Science'),('Owner Division/Office/Facility','Research'),
                            ('Owner Group','A new fictional group'),('Assigning Manager','science@example.org')]:
            self.assertEqual(self.native(row,title),value)
        job=next(p for p in response.get_json()['projects'] if p['id']==response.get_json()['jobId'])
        self.assertEqual(job['directorate'],'Fictional Science');self.assertEqual(job['division'],'Research')
        self.assertEqual(job['requestorGroup'],'A new fictional group');self.assertEqual(job['coordinatingManager'],'science@example.org')
        self.assertIn('Retain the supplied details',job['description'])
        self.assertFalse(self.native(row,'Requested Designer'));self.assertFalse(self.native(row,'Designer Response'))
        self.assertEqual(self.fake.rows[:len(before)],before)
        writes=[x for x in self.fake.calls if x[0]!='GET'];self.assertEqual(len(writes),1)
        self.assertEqual(writes[0][:2],('POST','/sheets/123/rows'))
        self.assertEqual(len([c for c in writes[0][2][0]['cells'] if c['columnId']==self.fake.bytitle['Assigning Manager']['id']]),1)

    def test_division_override_default_and_all_combinations_choose_one_manager(self):
        for directorate,division in product(['','Fictional Science','Fictional Operations','Unmapped Directorate'],['','Research','Shared Facility','Other']):
            decision=resolve(validate_policy(POLICY),directorate,division)
            expected='operations@example.org' if division=='Shared Facility' or directorate=='Fictional Operations' else 'science@example.org' if directorate=='Fictional Science' else 'coordinator@example.org'
            self.assertEqual(decision['email'],expected)

    def test_coordinator_org_edit_reroutes_without_touching_accepted_designer(self):
        client,_=self.login('coord');body=self.body();body['assignToMe']=True
        data=self.write(client,'/api/projects',body).get_json();job=next(p for p in data['projects'] if p['id']==data['jobId'])
        self.assertEqual(job['stage'],'Accepted')
        row=self.fake.rows[-1];original=copy.deepcopy(row)
        result=self.write(client,'/api/projects/'+job['id'],{'action':'edit','revision':job['revision'],'fields':{'division':'Shared Facility'}})
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(self.native(row,'Assigning Manager'),'operations@example.org')
        self.assertEqual(self.native(row,'Owner Directorate'),'Fictional Science');self.assertEqual(self.native(row,'Owner Group'),'A new fictional group')
        untouched={self.fake.bytitle[k]['id'] for k in ('Requested Designer','Designer Response','Project Stage','Assigned Designer')}
        self.assertEqual([c for c in row['cells'] if c['columnId'] in untouched],[c for c in original['cells'] if c['columnId'] in untouched])

    def test_unrelated_edits_and_legacy_notes_do_not_reroute_or_erase_manual_manager(self):
        client,data=self.login('coord');job=data['projects'][0]
        row=self.fake.rows[0];row['cells'].append({'columnId':self.fake.bytitle['Assigning Manager']['id'],'value':'manual@example.org'})
        brief=next(c for c in row['cells'] if c['columnId']==self.fake.bytitle['Additional Details']['id']);brief['value']='Original\n\nRequestor group / department:\nLegacy Group'
        self.fake.version+=1;job=self.get(client,'/api/projects').get_json()['projects'][0]
        self.assertEqual(job['requestorGroup'],'Legacy Group')
        result=self.write(client,'/api/projects/'+job['id'],{'action':'edit','revision':job['revision'],'fields':{'hours':2}})
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(self.native(row,'Assigning Manager'),'manual@example.org')
        self.assertEqual(brief['value'],'Original\n\nRequestor group / department:\nLegacy Group')

    def test_noncoordinator_cannot_reroute_existing_job_and_client_cannot_choose_manager(self):
        client,_=self.login('designer');result=self.write(client,'/api/projects',self.body());job=next(p for p in result.get_json()['projects'] if p['id']==result.get_json()['jobId'])
        before=len([c for c in self.fake.calls if c[0]!='GET'])
        denied=self.write(client,'/api/projects/'+job['id'],{'action':'edit','revision':job['revision'],'fields':{'directorate':'Fictional Operations'}})
        self.assertEqual(denied.status_code,403)
        bad=self.write(client,'/api/projects',self.body(assigningManager='other@example.org'))
        self.assertEqual(bad.status_code,400);self.assertEqual(len([c for c in self.fake.calls if c[0]!='GET']),before)

    def test_unknown_choices_conflicting_policy_and_active_workflow_fail_before_write(self):
        client,_=self.login('coord')
        for field in ('directorate','division'):
            result=self.write(client,'/api/projects',self.body(**{field:'Invented unsupported choice'}));self.assertEqual(result.status_code,400)
        self.assertFalse([c for c in self.fake.calls if c[0]!='GET'])
        bad=copy.deepcopy(POLICY);bad['directorates'].append({'values':['Fictional Science'],'manager':'central'})
        with self.assertRaises(ValueError):validate_policy(bad)
        self.fake.rules[0]['enabled']=True
        self.assertEqual(self.write(client,'/api/projects',self.body()).status_code,409)

    def test_immediate_self_acceptance_is_not_replaced_by_coordinator_routing(self):
        client,_=self.login('designer');body=self.body(division='Shared Facility');body['assignToMe']=True
        result=self.write(client,'/api/projects',body);self.assertEqual(result.status_code,200,result.get_json())
        job=next(p for p in result.get_json()['projects'] if p['id']==result.get_json()['jobId'])
        self.assertEqual(job['response'],'accepted');self.assertEqual(job['stage'],'Accepted')
        self.assertEqual(job['requestedDesigner'],'designer@example.org');self.assertEqual(job['coordinatingManager'],'operations@example.org')

    def test_policy_change_during_save_and_ineligible_manager_fail_closed(self):
        client,_=self.login('coord');store=self.readers[-1].store;original=store.route_organization
        def change_during_save(*args,**kwargs):
            original(*args,**kwargs)
            self.value['organizationRouting']['default']='science'
        with patch.object(store,'route_organization',side_effect=change_during_save):
            result=self.write(client,'/api/projects',self.body())
        self.assertEqual(result.status_code,409);self.assertFalse([c for c in self.fake.calls if c[0]!='GET'])
        self.value['organizationRouting']['managers']['central']['email']='uninvited@example.org'
        with self.assertRaises(WriteError):PilotConfig(self.value)
