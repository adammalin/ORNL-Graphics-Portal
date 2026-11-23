"""Canonical assignment transitions, native status parity and private history."""
import copy
import secrets
import tempfile
from pathlib import Path
from unittest.mock import patch
from test_pilot import PilotTestCase
from backend.dev_store import YES,NO
from backend.pilot import PilotConfig

class AssignmentConsistencyTests(PilotTestCase):
    def setUp(self):
        super().setUp()
        self.value['invites'][0]['role']='admin'

    def new(self,client,self_accept=False,key=None):
        result=self.write(client,'/api/projects',{'fields':{'title':'Fictional assignment QA','description':'No real work','taskType':['Other']},'assignToMe':self_accept},key=key)
        self.assertEqual(result.status_code,200,result.get_json())
        return next(p for p in result.get_json()['projects'] if p['id']==result.get_json()['jobId'])

    def change(self,client,job,action,**extra):
        current=self.project(client,job)
        return self.write(client,'/api/projects/'+job,{'action':action,'revision':current['revision'],**extra})

    def native(self,job,title):
        cid=self.fake.bytitle[title]['id'];jid=self.fake.bytitle['Graphics Req #']['id']
        row=next(r for r in self.fake.rows if any(c['columnId']==jid and c.get('value')==job for c in r['cells']))
        return next((c.get('value') for c in row['cells'] if c['columnId']==cid),None)

    def test_create_offer_decline_reoffer_accept_is_atomic_and_timestamped(self):
        admin,_=self.login('coord');designer,_=self.login('designer')
        job=self.new(admin);jid=job['id'];self.assertEqual(self.native(jid,'Status'),'New')
        self.assertEqual(self.change(admin,jid,'offer',designer='designer@example.org').status_code,200)
        offered=self.project(designer,jid);generation=offered['assignment']['generation'];offered_at=offered['assignment']['offeredAt']
        self.assertEqual((offered['stage'],offered['nativeStatus'],offered['responseStatus']),('Assigned','Designer Requested','Pending'))
        self.assertTrue(offered_at);self.assertIsNone(offered['assignment']['acceptedAt'])
        self.assertEqual(self.change(designer,jid,'decline').status_code,200)
        self.assertEqual((self.native(jid,'Status'),self.native(jid,'Update Status'),self.native(jid,'Designer Response')),('New','Responded',NO))
        self.assertEqual(self.change(admin,jid,'offer',designer='designer@example.org').status_code,200)
        pending=self.project(designer,jid);self.assertNotEqual(pending['assignment']['generation'],generation)
        self.assertEqual(self.change(designer,jid,'accept').status_code,200)
        accepted=self.project(designer,jid)
        self.assertEqual((accepted['stage'],accepted['nativeStatus'],accepted['responseStatus']),('Accepted','Designer Accepted','Responded'))
        self.assertTrue(accepted['assignment']['acceptedAt']);self.assertTrue(self.native(jid,'Req Assigned / Closed'))
        writes=[c for c in self.fake.calls if c[0]!='GET'];self.assertEqual(len(writes),5)
        last={c['columnId']:c for c in writes[-1][2][0]['cells']}
        for title in ('Status','Update Status','Designer Response','Project Stage'):self.assertIn(self.fake.bytitle[title]['id'],last)
        self.assertNotIn(self.fake.bytitle['Assigned Designer']['id'],last)
        self.assertEqual(len(accepted['assignment']['history']),5)

    def test_self_accept_and_claim_use_verified_actor_and_preserve_dates_on_unrelated_edit(self):
        admin,_=self.login('coord');job=self.new(admin,True);jid=job['id']
        self.assertEqual(self.native(jid,'Status'),'Designer Accepted')
        self.assertEqual(job['assignment']['offeredAt'],job['assignment']['acceptedAt'])
        before=copy.deepcopy(job['assignment']);assigned=self.native(jid,'Req Assigned / Closed')
        self.assertEqual(self.change(admin,jid,'edit',fields={'hours':3}).status_code,200)
        self.assertEqual(self.project(admin,jid)['assignment'],before)
        unassigned=self.new(admin)
        self.assertEqual(self.change(admin,unassigned['id'],'claim').status_code,200)
        claimed=self.project(admin,unassigned['id'])
        self.assertEqual((claimed['requestedDesigner'],claimed['response'],claimed['stage']),('coordinator@example.org','accepted','Accepted'))
        self.assertFalse(claimed['assignmentActions']['claim']);self.assertTrue(assigned)
        self.assertNotEqual(self.change(admin,unassigned['id'],'claim').status_code,200)

    def test_reassignment_requires_coordinator_confirmation_and_new_designer_acceptance(self):
        admin,_=self.login('coord');designer,_=self.login('designer');other,_=self.login('other')
        job=self.new(designer,True);jid=job['id'];first_date=self.native(jid,'Req Assigned / Closed')
        for client,extra in ((designer,{'designer':'other@example.org','reason':'Fictional handoff','confirmReset':True}),
                             (admin,{'designer':'other@example.org','reason':'Fictional handoff','confirmReset':False}),
                             (admin,{'designer':'outsider@example.org','reason':'Fictional handoff','confirmReset':True})):
            self.assertNotEqual(self.change(client,jid,'reassign',**extra).status_code,200)
        old=self.project(designer,jid)
        result=self.change(admin,jid,'reassign',designer='other@example.org',reason='Fictional handoff',confirmReset=True)
        self.assertEqual(result.status_code,200,result.get_json())
        self.assertEqual((self.native(jid,'Designer Response'),self.native(jid,'Status'),self.native(jid,'Project Stage')),(None,'Designer Requested','Assigned'))
        self.assertEqual(self.native(jid,'Req Assigned / Closed'),first_date)
        self.assertEqual(self.change(designer,jid,'accept').status_code,403)
        self.assertEqual(self.change(other,jid,'accept').status_code,200)
        accepted=self.project(other,jid);self.assertEqual(accepted['requestedDesigner'],'other@example.org')
        self.assertNotEqual(accepted['assignment']['generation'],old['assignment']['generation'])
        self.assertEqual(accepted['assignment']['history'][1]['reason'],'Fictional handoff')

    def test_stale_offer_duplicate_offer_and_stage_shortcuts_cannot_reset_acceptance(self):
        admin,_=self.login('coord');designer,_=self.login('designer');jid=self.new(admin)['id']
        self.change(admin,jid,'offer',designer='designer@example.org');old=self.project(designer,jid)
        self.assertEqual(self.change(admin,jid,'offer',designer='designer@example.org').status_code,409)
        self.change(admin,jid,'offer',designer='other@example.org');self.change(admin,jid,'offer',designer='designer@example.org')
        stale=self.write(designer,'/api/projects/'+jid,{'action':'accept','revision':old['revision']})
        self.assertEqual(stale.status_code,409)
        self.change(designer,jid,'accept')
        for stage in ('New','Assigned'):
            self.assertEqual(self.change(admin,jid,'stage',stage=stage).status_code,409)
        self.assertEqual(self.native(jid,'Designer Response'),YES)

    def test_receipt_replay_history_is_once_and_uncertain_transition_is_not_confirmed(self):
        admin,_=self.login('coord');job=self.new(admin);key=secrets.token_urlsafe(20)
        body={'action':'offer','revision':job['revision'],'designer':'designer@example.org'}
        first=self.write(admin,'/api/projects/'+job['id'],body,key=key)
        again=self.write(admin,'/api/projects/'+job['id'],body,key=key)
        self.assertEqual((first.status_code,again.status_code),(200,200))
        history=self.project(admin,job['id'])['assignment']['history'];self.assertEqual(len(history),2)
        self.fake.timeout=True
        failed=self.change(admin,job['id'],'offer',designer='other@example.org')
        self.assertNotEqual(failed.status_code,200)
        history=self.project(admin,job['id'])['assignment']['history']
        self.assertEqual(len(history),3);self.assertFalse(history[0]['confirmed'])
        self.assertEqual(history[1]['action'],'offer')

    def test_completion_and_archive_preserve_routing_and_do_not_invent_completion(self):
        admin,_=self.login('coord');job=self.new(admin,True);jid=job['id']
        for stage in ('In Progress','In Review','Completed','Archived'):
            self.assertEqual(self.change(admin,jid,'stage',stage=stage).status_code,200)
            self.assertEqual(self.native(jid,'Status'),'Designer Accepted')
        completed=self.native(jid,'Completed Date');self.assertTrue(completed)
        self.assertEqual(self.change(admin,jid,'reassign',designer='other@example.org',reason='Closed',confirmReset=True).status_code,403)
        incomplete=self.new(admin,True)['id'];self.change(admin,incomplete,'stage',stage='Archived')
        self.assertFalse(self.native(incomplete,'Completed Date'))

    def test_old_native_assignment_has_no_inferred_acceptance_timestamp(self):
        admin,_=self.login('coord');designer,_=self.login('designer')
        self.offer(admin);self.change(designer,'TEST-1','accept')
        # Remove only fictional tracking history to represent a pre-existing native assignment.
        with self.runtime.db() as db:db.execute('DELETE FROM portal_assignment_events')
        job=self.project(admin,'TEST-1');self.assertIsNone(job['assignment']['acceptedAt'])
        self.assertEqual(self.change(admin,'TEST-1','stage',stage='In Progress').status_code,200)
        self.assertIsNone(self.project(admin,'TEST-1')['assignment']['acceptedAt'])

    def test_stale_assignment_formula_cannot_hide_a_new_offer_or_override_decline(self):
        from backend.server import normalize_sheet
        admin,_=self.login('coord');jid=self.new(admin,True)['id']
        reader=self.readers[-1];reader.projects(force=True)
        sheet=copy.deepcopy(reader.sheet)
        row=next(r for r in sheet['rows'] if any(c['columnId']==self.fake.bytitle['Graphics Req #']['id'] and c.get('value')==jid for c in r['cells']))
        def set_cell(title,value):
            cid=self.fake.bytitle[title]['id'];row['cells']=[c for c in row['cells'] if c['columnId']!=cid]+[{'columnId':cid,'value':value}]
        set_cell('Requested Designer','other@example.org');set_cell('Designer Response',None);set_cell('Project Stage','Assigned')
        def project():return next(p for p in normalize_sheet(sheet,'123',reader.row_ids)[0] if p['id']==jid)
        pending=project();self.assertEqual((pending['requestedDesigner'],pending['response']),('other@example.org',''))
        set_cell('Designer Response',NO);set_cell('Project Stage','New')
        self.assertEqual(project()['response'],'declined')
        set_cell('Designer Response',YES);set_cell('Project Stage','Accepted')
        self.assertEqual((project()['requestedDesigner'],project()['response']),('other@example.org','accepted'))

    def test_production_stage_preserves_legacy_status_without_backdating_acceptance(self):
        admin,_=self.login('coord');jid=self.new(admin,True)['id']
        row=self.fake.rows[-1];status=self.fake.bytitle['Status']['id'];assigned_date=self.fake.bytitle['Req Assigned / Closed']['id']
        for cell in row['cells']:
            if cell['columnId']==status:cell['value']='Editing - In Process'
            if cell['columnId']==assigned_date:cell['value']=None
        self.fake.version+=1
        self.assertEqual(self.change(admin,jid,'stage',stage='In Progress').status_code,200)
        self.assertEqual(self.native(jid,'Status'),'Editing - In Process')
        self.assertIsNone(self.native(jid,'Req Assigned / Closed'))
