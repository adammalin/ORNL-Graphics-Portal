"""Every guided field: actual serializer/native-cell contract and owned readback.

Uses the injected Smartsheet transport; not evidence of a real DEV save.
"""
import copy
from datetime import date
import json
import secrets
import unittest
from unittest.mock import patch
import test_microsoft_intake as fixture
from backend.guided_intake import SERVICES, normalize

class GuidedFieldRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.clock=patch('backend.guided_intake.today_eastern',return_value=date(2026,11,24));self.clock.start()
        self.p=fixture.MicrosoftIntakeTests();self.p.setUp()
        self.p.fake.bytitle['Owner Directorate'].update(type='PICKLIST',options=['DIRECTORATE_MARKER'])
        self.p.fake.bytitle['Owner Division/Office/Facility'].update(type='PICKLIST',options=['DIVISION_MARKER'])
        self.p.value['guidedIntake']={'enabled':True,'calendar':{'approved':True,'label':'Fictional field qualification','validThrough':'2027-12-31','closedDates':['2026-11-26','2026-11-27']}}
        self.client=self.p.ms_login()
    def tearDown(self):self.p.tearDown();self.clock.stop()
    def full(self):
        return {'title':'FAKE DEMO — All fields: μm & “quoted” <text>',
                'description':'PURPOSE_MARKER: Scientific story\nSecond line — α / β.',
                'taskType':['Figure/Diagram/Chart','Other'], 'audience':'AUDIENCE_MARKER: fictional researchers & staff',
                'deliverables':'DELIVERABLES_MARKER: 2 editable figures\n1 poster + 40 handouts',
                'specifications':'SPECS_MARKER: 36 × 48 in; SVG/PDF; 300 ppi',
                'directorate':'DIRECTORATE_MARKER','division':'DIVISION_MARKER','requestorGroup':'GROUP_MARKER — a custom department',
                'dueDate':'2026-11-30','eventDate':'2026-12-05',
                'reference1':'https://example.org/one?topic=alpha&view=full#figure',
                'reference2':'https://example.org/two/reference.pdf',
                'notes':'NOTES_MARKER: retain this original note\nNo scientific claims implied.',
                'requestor':'Spoofed name','email':'spoof@example.org',
                'additionalServices':list(SERVICES),
                'serviceDetails':{sid:({'kind':s[2][0],'notes':sid.upper()+'_NOTE — retain α'}|({'quantity':'17'} if sid in ('poster','reproduction') else {})) if sid!='unsure' else {} for sid,s in SERVICES.items()}}
    def submit(self,fields,key=None):return self.p.ms_write(self.client,'/api/intake/requests',{'fields':fields},key=key)
    def tracked(self,receipt):return self.p.get(self.client,'/api/intake/my-requests/'+receipt).get_json()
    def test_every_field_is_preserved_in_native_cells_and_customer_snapshot(self):
        fields=self.full();before=copy.deepcopy(self.p.fake.rows);response=self.submit(fields)
        self.assertEqual(response.status_code,200,response.get_json());saved=response.get_json()
        row=self.p.fake.rows[-1];cells={self.p.fake.columns[c['columnId']-1]['title']:c for c in row['cells']}
        scalar={'Description':'[DEV PORTAL] '+fields['title'],'Due Date':fields['dueDate'],'Deliverables and Quantities':fields['deliverables'],'Owner Directorate':fields['directorate'],'Owner Division/Office/Facility':fields['division'],'Owner Group':fields['requestorGroup'],'Reference link 1':fields['reference1'],'Reference link 2':fields['reference2'],'Requestor':'Fictional Employee','Requestor Email':'employee@example.org','DEV Test Record':True,'Project Stage':'New'}
        for column,expected in scalar.items():
            with self.subTest(native=column):self.assertEqual(cells[column]['value'],expected)
        self.assertEqual(cells['Task Type']['objectValue']['values'],fields['taskType'])
        native=cells['Additional Details']['value']
        for key in ['description','audience','specifications','notes']:
            with self.subTest(nativeDetails=key):self.assertIn(fields[key],native)
        self.assertIn(fields['eventDate'],native)
        for sid in fields['additionalServices']:
            self.assertIn(SERVICES[sid][0],native)
            if sid!='unsure':self.assertIn(fields['serviceDetails'][sid]['notes'],native)
        self.assertEqual(native.count('Reproduction —'),1)
        original=self.tracked(saved['receipt'])['originalRequest']
        for key in ['description','taskType','audience','deliverables','specifications','directorate','division','requestorGroup','dueDate','eventDate','reference1','reference2','notes','additionalServices']:
            with self.subTest(snapshot=key):self.assertEqual(original.get(key),fields[key])
        for sid in fields['additionalServices']:
            if sid!='unsure':self.assertEqual(original['serviceDetails'][sid]['notes'],fields['serviceDetails'][sid]['notes'])
        self.assertEqual(self.p.fake.rows[:len(before)],before)
        write=self.p.writes()[0][2][0]['cells'];protected={c['id'] for c in self.p.fake.columns if c.get('formula') or c.get('systemColumnType')}
        self.assertFalse(protected & {c['columnId'] for c in write})
    def test_each_service_choice_and_quantity_boundary(self):
        for sid,s in SERVICES.items():
            for choice in s[2] or ['']:
                fields=self.full();fields['additionalServices']=[sid];fields['serviceDetails']={sid:{'kind':choice,'notes':'CHOICE_MARKER',**({'quantity':'1'} if sid in ('poster','reproduction') else {})}}
                with self.subTest(service=sid,choice=choice):
                    native,original=normalize(fields,self.p.runtime.active_config());self.assertIn(s[0],native['notes']);self.assertEqual(original['serviceDetails'][sid]['kind'],choice)
        for qty in ['0','-1','1.5',True,'100001','not a number']:
            f=self.full();f['serviceDetails']['poster']['quantity']=qty
            with self.subTest(quantity=qty):self.assertEqual(self.submit(f).status_code,400)
        for qty in ['1','100000']:
            f=self.full();f['serviceDetails']['poster']['quantity']=qty;self.assertEqual(self.submit(f).status_code,200)
    def test_required_only_request_has_no_stale_hidden_service_values(self):
        f={'title':'FAKE DEMO — Required only','description':'REQUIRED_MARKER','taskType':['Other'],'dueDate':'2026-11-30','additionalServices':[],'serviceDetails':{}}
        response=self.submit(f);self.assertEqual(response.status_code,200,response.get_json());original=self.tracked(response.get_json()['receipt'])['originalRequest']
        self.assertEqual(original['additionalServices'],[]);self.assertEqual(original['serviceDetails'],{})
        bad={**f,'serviceDetails':{'video':{'kind':'Filming','notes':'HIDDEN_VALUE'}}};self.assertEqual(self.submit(bad).status_code,400)
    def test_oversized_combined_details_and_unsafe_links_never_write(self):
        before=len(self.p.writes())
        for change in [{'description':'X'*4000},{'notes':'X'*4001},{'reference1':'javascript:alert(1)'},{'reference2':'https://user:password@example.org/private'}]:
            f=self.full();f.update(change)
            with self.subTest(change=list(change)):self.assertEqual(self.submit(f).status_code,400)
        self.assertEqual(len(self.p.writes()),before)
    def test_safe_snapshot_survives_subsequent_staff_notes_and_data_refresh(self):
        response=self.submit(self.full());self.assertEqual(response.status_code,200,response.get_json());saved=response.get_json();first=self.tracked(saved['receipt'])
        row=self.p.fake.rows[-1];cid=self.p.fake.bytitle['Additional Details']['id'];next(c for c in row['cells'] if c['columnId']==cid)['value']='PRIVATE_STAFF_NOTE'
        self.p.fake.version+=1
        self.assertEqual(self.tracked(saved['receipt'])['originalRequest'],first['originalRequest'])
        self.assertNotIn('PRIVATE_STAFF_NOTE',json.dumps(self.tracked(saved['receipt'])))
    def test_current_accepted_contact_outranks_a_stale_assigned_formula(self):
        result=self.submit(self.full());self.assertEqual(result.status_code,200,result.get_json());saved=result.get_json();row=self.p.fake.rows[-1]
        updates={'Requested Designer':{'value':'other@example.org','displayValue':'Current Designer','objectValue':{'objectType':'CONTACT','email':'other@example.org','name':'Current Designer'}},'Designer Response':{'value':'Yes - I can take this job.'},'Project Stage':{'value':'Accepted'},'Assigned Designer':{'value':'designer@example.org','displayValue':'Old Designer','objectValue':{'objectType':'CONTACT','email':'designer@example.org','name':'Old Designer'},'formula':self.p.fake.bytitle['Assigned Designer']['formula']}}
        for name,cell in updates.items():
            cid=self.p.fake.bytitle[name]['id'];row['cells']=[c for c in row['cells'] if c['columnId']!=cid]+[{'columnId':cid,**cell}]
        self.p.fake.version+=1
        self.assertEqual(self.tracked(saved['receipt'])['designer'],'Current Designer')
