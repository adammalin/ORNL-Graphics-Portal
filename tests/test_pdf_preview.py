"""Native PDF delivery plus unchanged access/download boundaries."""
from test_pilot import PilotTestCase
from backend.server import attachment_delivery

class PdfPreviewTests(PilotTestCase):
    def test_explicit_pdf_preview_is_inline_and_preserves_browser_headers(self):
        client,_=self.login('coord');pdf=b'%PDF-1.4\nsynthetic header control'
        self.runtime.jobs.attachment=lambda *args:(pdf,'Application/PDF; charset=binary','FAKE DEMO reference.pdf')
        response=self.get(client,'/api/projects/TEST-1/attachments/900?preview=1')
        self.assertEqual(response.status_code,200);self.assertEqual(response.data,pdf)
        self.assertEqual(response.headers['Content-Type'],'application/pdf')
        self.assertTrue(response.headers['Content-Disposition'].startswith('inline;'))
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])

    def test_download_wins_and_pdf_defaults_remain_downloads(self):
        client,_=self.login('coord');self.runtime.jobs.attachment=lambda *args:(b'%PDF-1.4\ncontrol','application/pdf','sample.pdf')
        for query in ['', '?download=1','?preview=1&download=1','?preview=0','?preview=1&preview=0']:
            response=self.get(client,'/api/projects/TEST-1/attachments/900'+query)
            self.assertEqual(response.headers['Content-Type'],'application/octet-stream',query)
            self.assertTrue(response.headers['Content-Disposition'].startswith('attachment;'),query)

    def test_unknown_active_or_mislabeled_content_is_not_previewed(self):
        for body,mime in [(b'<script>fake PDF</script>','application/pdf'),(b'%PDF-1.4','text/html'),(b'%PDF-1.4','application/octet-stream')]:
            with self.subTest(mime=mime):self.assertEqual(attachment_delivery(body,mime,pdf_preview=True),('application/octet-stream',True))

    def test_preview_query_does_not_bypass_session_or_selected_job_access(self):
        self.assertEqual(self.get(self.app.test_client(),'/api/projects/TEST-1/attachments/900?preview=1').status_code,401)
        other,_=self.login('other');self.assertEqual(self.get(other,'/api/projects/TEST-1/attachments/900?preview=1').status_code,404)
        self.assertFalse(any(call[0]!='GET' for call in self.fake.calls))
