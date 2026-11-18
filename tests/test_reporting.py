"""Reporting arithmetic, private ownership, source protection and real download packages."""
import copy
import csv
from datetime import date
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from backend.reporting import aggregate, clean_filters, completed, PROFILE_FIELDS
from backend.dev_store import WriteError
from test_pilot import PilotTestCase


def sample_project(key,**extra):
    return {'id':key,'_rowId':key,'revision':'r1','title':'Fictional '+key,'stage':'New',
            'createdDate':'2026-01-05','completedDate':'','finalDueDate':'','taskTypes':['Figure','Poster'],
            'requestedDesigner':'designer@example.org','response':'accepted','hours':4,'reporting':{},**extra}


def sample_report():
    jobs=[sample_project('A',stage='Completed',completedDate='2026-02-03',finalDueDate='2026-02-04',reporting={
        'directorate':'Fictional Research','impactLevel':'High','impactJustification':'Coordinator confirmed demonstration',
        'impactStatement':'Fictional example, not an ORNL result.','intendedOutcome':'Explain the method.',
        'observedOutcome':'No measured outcome yet.','evidenceUrl':'https://example.org/evidence'}),
        sample_project('B',createdDate='2025-12-01',stage='Completed',completedDate='2026-01-12'),
        sample_project('C',createdDate='',stage='Archived'),sample_project('D')]
    return aggregate(jobs,clean_filters({'start':'2026-01-01','end':'2026-03-31'}),
        [{'id':'designer@example.org','name':'Fictional Designer'}],7,'https://pilot.example.org')


class ReportingArithmeticTests(unittest.TestCase):
    def test_dates_cohort_months_multicategory_and_unknowns(self):
        r=sample_report();k=r['kpis']
        self.assertEqual((k['periodJobs'],k['received'],k['completed']),(3,2,2))
        self.assertEqual(k['averageCompletedPerMonth'],.67)
        self.assertEqual(r['monthly'][-1],{'label':'2026-03','received':0,'completed':0})
        self.assertEqual(sum(t['value'] for t in r['types']),6)
        self.assertEqual(k['onTimePercent'],100);self.assertEqual(r['quality']['onTimeSample'],1)
        self.assertEqual(k['highImpact'],1);self.assertEqual(k['directoratesServed'],1)
        self.assertEqual(k['currentEstimatedHours'],4);self.assertFalse(r['quality']['partialMonths'])
        self.assertEqual(r['quality']['missingReceivedDate'],1)
        self.assertEqual(r['quality']['unverifiedArchived'],1)
        self.assertEqual(r['quality']['reversedCompletionDates'],0)
        self.assertNotIn('email',r['records'][0]);self.assertNotIn('description',r['records'][0])

    def test_cancelled_and_unverified_archive_not_completion(self):
        base=sample_project('A',stage='Archived',completedDate='2026-02-03')
        self.assertFalse(completed(base))
        for meta,status,answer in [({'disposition':'Completed'},'',True),({},'Closed',True),
                                   ({'disposition':'Cancelled'},'Closed',False),({},'Canceled',False)]:
            self.assertEqual(completed({**base,'reporting':meta,'sourceStatus':status}),answer)
        self.assertFalse(completed({**base,'reporting':{'disposition':'Completed'},'completedDate':'bad'}))

    def test_empty_and_filtered_coverage_is_explicit(self):
        r=aggregate([],clean_filters({'start':'2026-01-15','end':'2026-02-03'}),[],1,'https://example.org')
        self.assertEqual(r['kpis']['averageCompletedPerMonth'],0)
        self.assertIsNone(r['kpis']['onTimePercent']);self.assertIsNone(r['kpis']['averageTurnaroundDays'])
        self.assertTrue(r['quality']['partialMonths'])
        for body in [[],{'end':'bad'},{'start':'2026-05-01','end':'2026-01-01'},{'source':[]},{'unknown':True},
                     {'start':'2000-01-01','end':'2026-01-01'},{'start':'9999-01-01','end':'9999-12-31'},{'impactLevel':'Invented'}]:
            with self.assertRaises(WriteError):clean_filters(body)


class ReportingAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.p=PilotTestCase();self.p.setUp();self.p.value['copiedRowIds']=['12']
        self.client,_=self.p.login('coord');self.service=self.p.app.extensions['reporting']
    def tearDown(self):self.p.tearDown()
    def request(self,path,body,client=None,method='POST',**headers):
        client=client or self.client
        csrf=self.p.get(client,'/api/session').get_json()['csrf']
        return client.open(path,method=method,base_url=self.p.origin,json=body,
            headers={'Origin':self.p.origin,'X-Portal-CSRF':csrf,**headers})
    def snapshot(self,client=None):
        result=self.request('/api/reports',{'filters':{}},client)
        self.assertEqual(result.status_code,200,result.get_json());return result.get_json()
    def fields(self):return {k:'' for k in PROFILE_FIELDS}
    def profile(self,**changes):
        project=next(p for p in self.snapshot()['report']['classificationProjects'] if p['id']=='TEST-1')
        fields={**self.fields(),**changes}
        return {'sourceRevision':project['sourceRevision'],'metadataVersion':project['metadataVersion'],'fields':fields}
    def download(self,snap,**changes):
        return self.request('/api/reports/'+snap['snapshotId']+'/export',{'format':'csv','layout':'executive','sections':['summary'],**changes})

    def test_coordinator_only_csrf_and_static_boundaries(self):
        anonymous=self.p.app.test_client()
        self.assertEqual(anonymous.post('/api/reports',base_url=self.p.origin,json={'filters':{}},headers={'Origin':self.p.origin}).status_code,401)
        for who in ['designer','other','viewer']:
            client,_=self.p.login(who)
            self.assertEqual(self.request('/api/reports',{'filters':{}},client).status_code,403)
        self.assertEqual(self.request('/api/reports',{'filters':{}},Origin='https://evil.example').status_code,403)
        self.assertEqual(self.request('/api/reports',{'filters':{}},**{'X-Portal-CSRF':'bad'}).status_code,403)
        with self.p.get(self.client,'/reports.js') as response:self.assertEqual(response.status_code,200)
        self.assertEqual(self.p.get(self.client,'/.local/report-assets/ornl-template.potx').status_code,404)

    def test_profile_is_versioned_private_and_never_writes_native_source(self):
        body=self.profile(directorate='Fictional Research',impactLevel='High',impactJustification='Demonstrated only in this test')
        before=copy.deepcopy(self.p.fake.rows);self.p.fake.calls.clear()
        result=self.request('/api/reports/jobs/TEST-1',body,method='PATCH')
        self.assertEqual(result.status_code,200,result.get_json());self.assertEqual(result.get_json()['metadataVersion'],1)
        self.assertEqual(self.p.fake.rows,before);self.assertTrue(all(c[0]=='GET' for c in self.p.fake.calls))
        self.assertEqual(self.request('/api/reports/jobs/TEST-1',body,method='PATCH').status_code,409)
        copied=next(p for p in self.snapshot()['report']['classificationProjects'] if p['id']=='COPIED')
        body.update(sourceRevision=copied['sourceRevision'],metadataVersion=0)
        self.assertFalse(copied['canAnnotate'])
        self.assertEqual(self.request('/api/reports/jobs/COPIED',body,method='PATCH').status_code,403)
        with self.p.runtime.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reporting_profiles').fetchone()[0],1)

    def test_profile_validation_source_revision_and_readonly_checks(self):
        for values in [{'impactLevel':'High'},{'evidenceUrl':'javascript:bad'}, {'evidenceUrl':'https://u:pw@example.org'},
                       {'directorate':'x'*161},{'impactStatement':'bad\x00text'}]:
            self.assertEqual(self.request('/api/reports/jobs/TEST-1',self.profile(**values),method='PATCH').status_code,400)
        body=self.profile();body['sourceRevision']='old'
        self.assertEqual(self.request('/api/reports/jobs/TEST-1',body,method='PATCH').status_code,409)
        self.p.value['writesEnabled']=False
        self.assertEqual(self.request('/api/reports/jobs/TEST-1',self.profile(),method='PATCH').status_code,403)

    def test_snapshot_owner_expiry_revocation_and_source_changes(self):
        snap=self.snapshot();result=self.download(snap)
        self.assertEqual(result.status_code,200,result.get_json(silent=True))
        self.assertIn('attachment;',result.headers['Content-Disposition']);self.assertIn('no-store',result.headers['Cache-Control'])
        self.assertIn(b'Data coverage',result.data) # Mandatory even if omitted by a client.
        self.p.value['invites'][1]['role']='coordinator';other,_=self.p.login('designer')
        self.assertEqual(self.request('/api/reports/'+snap['snapshotId']+'/export',{'format':'csv','layout':'executive','sections':['summary']},other).status_code,404)
        self.p.fake.version+=1
        self.assertEqual(self.download(snap).status_code,409)
        snap=self.snapshot()
        with self.p.runtime.db() as db:db.execute('UPDATE reporting_snapshots SET expires_at=?',(time.time()-1,))
        self.assertEqual(self.download(snap).status_code,410)
        snap=self.snapshot();self.p.access['coord']='DENIED'
        self.assertEqual(self.download(snap).status_code,502)

    def test_profile_change_invalidates_snapshot_and_post_render_changes_fail_closed(self):
        snap=self.snapshot();body=self.profile(directorate='Fictional Directorate')
        self.assertEqual(self.request('/api/reports/jobs/TEST-1',body,method='PATCH').status_code,200)
        self.assertEqual(self.download(snap).status_code,409)
        snap=self.snapshot()
        def changed(*args):self.p.fake.version+=1;return b'not released','text/csv','report.csv'
        with patch('backend.report_exports.render_export',side_effect=changed):self.assertEqual(self.download(snap).status_code,409)
        snap=self.snapshot()
        def revoked(*args):
            self.p.value['invites'][1]['role']='coordinator';self.p.value['invites']=self.p.value['invites'][1:]
            return b'not released','text/csv','report.csv'
        with patch('backend.report_exports.render_export',side_effect=revoked):self.assertEqual(self.download(snap).status_code,403)

    def test_bad_export_requests_and_snapshot_limits(self):
        snap=self.snapshot()
        for change in [{'format':[]},{'layout':{}},{'sections':[{}]},{'sections':['summary','summary']},{'sections':[]}]:
            self.assertEqual(self.download(snap,**change).status_code,400)
        for _ in range(29):self.snapshot()
        self.assertEqual(self.request('/api/reports',{'filters':{}}).status_code,429)


class ReportingDownloadTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('MPLCONFIGDIR',str(Path.cwd()/'.local/matplotlib'))
        from matplotlib import get_data_path
        from pptx import Presentation
        self.tmp=tempfile.TemporaryDirectory();self.assets=Path(self.tmp.name)
        for source,target in [('DejaVuSans.ttf','Aptos.ttf'),('DejaVuSans-Bold.ttf','Aptos-Bold.ttf')]:
            self.assets.joinpath(target).write_bytes(Path(get_data_path(),'fonts/ttf',source).read_bytes())
        prs=Presentation();prs.save(self.assets/'ornl-template.potx') # Fictional CI template; private official artwork is not committed.
        self.patch=patch('backend.report_exports.ASSET_DIR',self.assets);self.patch.start()
    def tearDown(self):self.patch.stop();self.tmp.cleanup()

    def test_all_downloads_reopen_and_preserve_filters_data_and_editable_charts(self):
        from backend.report_exports import render_export
        from backend.reporting import SECTIONS
        from docx import Document
        from pptx import Presentation
        from pypdf import PdfReader
        report=sample_report();report['filters']['directorate']='Fictional Research'
        for fmt in ['csv','csv-jobs','pdf','docx','pptx']:
            with self.subTest(format=fmt):
                data,mime,name=render_export(report,fmt,list(SECTIONS),'operations')
                self.assertTrue(data);self.assertIn('2026-01-01',name)
                if fmt.startswith('csv'):
                    rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))));self.assertGreater(len(rows),1)
                    self.assertIn('Fictional Research',data.decode())
                elif fmt=='pdf':
                    pdf=PdfReader(io.BytesIO(data));text='\n'.join(page.extract_text() for page in pdf.pages)
                    self.assertIn('Fictional Research',text);self.assertIn('Source version 7',text);self.assertGreater(len(pdf.pages),5)
                elif fmt=='docx':
                    doc=Document(io.BytesIO(data));text='\n'.join(p.text for p in doc.paragraphs)
                    self.assertIn('Fictional Research',text);self.assertGreater(len(doc.tables),5)
                else:
                    prs=Presentation(io.BytesIO(data));self.assertGreater(len(prs.slides),8)
                    self.assertGreater(sum(shape.has_chart for slide in prs.slides for shape in slide.shapes),3)
                    self.assertTrue(any(shape.has_table for slide in prs.slides for shape in slide.shapes))
                    self.assertIn('Fictional Research','\n'.join(shape.text for slide in prs.slides for shape in slide.shapes if shape.has_text_frame))

    def test_empty_documents_and_long_values_remain_valid_packages(self):
        from backend.report_exports import render_export
        from backend.reporting import SECTIONS
        from pptx import Presentation
        from pypdf import PdfReader
        empty=aggregate([],clean_filters({'start':'2026-01-01','end':'2026-01-31'}),[],1,'https://example.org')
        for fmt in ['pdf','docx','pptx']:
            data,_,_=render_export(empty,fmt,list(SECTIONS),'executive');self.assertTrue(data)
        r=sample_report();r['records'][0]['title']='Long fictional project title '*150
        r['types'][0]['label']='=HYPERLINK("https://example.org")'
        r['highlights'][0]['reporting']['impactStatement']='A long fictional impact statement with no measured claim. '*20
        pdf,_,_=render_export(r,'pdf',['records','impact','quality'],'impact');self.assertGreater(len(PdfReader(io.BytesIO(pdf)).pages),2)
        pptx,_,_=render_export(r,'pptx',['types','impact','records','quality'],'impact')
        self.assertGreater(len(Presentation(io.BytesIO(pptx)).slides),5)
        reordered,_,_=render_export(r,'pdf',['monthly','summary','quality'],'operations')
        pages=PdfReader(io.BytesIO(reordered)).pages
        self.assertIn('Monthly activity',pages[1].extract_text());self.assertIn('Executive summary',pages[2].extract_text())
        with zipfile.ZipFile(io.BytesIO(pptx)) as package:
            for name in package.namelist():
                if name.endswith('.xlsx'):
                    with zipfile.ZipFile(io.BytesIO(package.read(name))) as workbook:
                        for item in workbook.namelist():
                            if item.startswith('xl/worksheets/') and item.endswith('.xml'):self.assertNotIn(b'<f>',workbook.read(item))

    def test_csv_formula_escape_and_missing_private_assets_fail_closed(self):
        from backend.report_exports import csv_export,render_export
        r=sample_report();r['records'][0]['title']=' =HYPERLINK("https://example.org")'
        rows=list(csv.reader(io.StringIO(csv_export(r,['records'],True).decode('utf-8-sig'))))
        self.assertTrue(rows[1][1].startswith("'"))
        with patch('backend.report_exports.ASSET_DIR',self.assets/'missing'):
            with self.assertRaises(WriteError) as error:render_export(r,'pptx',['summary'],'executive')
            self.assertEqual(error.exception.status,503)
