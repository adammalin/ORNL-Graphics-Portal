"""Transport-free callers must satisfy the same policy as the browser adapter."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import secrets
import time
from unittest.mock import Mock

from test_pilot import PilotTestCase, HAS_FLASK
if HAS_FLASK:
    from backend.dev_store import WriteError
    from backend.principals import Principal


class JobServiceTests(PilotTestCase):
    def sid(self, who):
        email = self.profiles[who]['email']
        return next(key for key, session in self.runtime.sessions.items()
                    if session.actor.email == email)

    def test_service_and_http_read_results_match_without_transport_credentials(self):
        client, http = self.login('coord')
        service = self.runtime.jobs
        direct = service.workspace(self.sid('coord'))
        self.assertNotIn('csrf', direct)
        self.assertEqual({k: v for k, v in http.items() if k != 'csrf'}, direct)
        self.assertNotIn('_rowId', service.get_job(self.sid('coord'), 'TEST-1'))
        capabilities = self.get(client, '/api/v1/capabilities').get_json()
        self.assertEqual(capabilities, service.capabilities(self.sid('coord')))
        self.assertEqual(capabilities['schemaVersion'], '1.0')
        self.assertTrue(capabilities['jobActionsAreScoped'])
        self.assertTrue(capabilities['canCreate'])
        self.assertFalse(any(capabilities['features'].values()))
        self.assertFalse(capabilities['constraints']['deletion']);self.assertFalse(capabilities['constraints']['sharedTokenFallback']);self.assertTrue(capabilities['constraints']['recoverableDeletion'])
        for secret in ['csrf', 'access_token', 'client_secret', 'sessionId']:
            self.assertNotIn(secret, capabilities)

    def test_identity_snapshot_is_immutable_and_is_not_an_authentication_handle(self):
        self.login('coord')
        session = self.runtime.sessions[self.sid('coord')]
        principal = Principal.from_session(session)
        with self.assertRaises(FrozenInstanceError):
            principal.role = 'designer'
        for forged in [None, {}, principal, 'coordinator', 'unissued-session']:
            with self.assertRaises(WriteError) as error:
                self.runtime.jobs.workspace(forged)
            self.assertEqual(error.exception.status, 401)

    def test_direct_writes_are_visible_in_browser_and_retries_do_not_duplicate(self):
        client, _ = self.login('coord')
        sid, service = self.sid('coord'), self.runtime.jobs
        body = {'action': 'edit', 'revision': service.get_job(sid, 'TEST-1')['revision'],
                'fields': {'hours': 5}}
        key = secrets.token_urlsafe(20)
        first = service.perform(sid, key, body, 'TEST-1')
        again = service.perform(sid, key, body, 'TEST-1')
        self.assertNotIn('csrf', first)
        self.assertEqual(first['jobId'], again['jobId'])
        self.assertEqual(self.project(client)['hours'], 5)
        self.assertEqual(len([call for call in self.fake.calls if call[0] != 'GET']), 1)
        self.assertEqual(self.action(client, 'edit', fields={'hours': 6}).status_code, 200)
        self.assertEqual(service.get_job(sid, 'TEST-1')['hours'], 6)

    def test_job_result_is_detached_from_native_reader_cache(self):
        self.login('coord')
        sid = self.sid('coord')
        reader = self.runtime.sessions[sid].reader
        result = self.runtime.jobs.get_job(sid, 'TEST-1')
        result['attachments'].append({'id': 'fabricated'})
        cached = next(p for p in reader._cache['projects'] if p['id'] == 'TEST-1')
        self.assertEqual(cached['attachments'], [])

    def test_direct_caller_cannot_read_update_or_download_another_designers_job(self):
        self.login('other')
        sid, service = self.sid('other'), self.runtime.jobs
        for call in [
            lambda: service.get_job(sid, 'TEST-1'),
            lambda: service.perform(sid, secrets.token_urlsafe(20),
                                   {'action': 'edit', 'revision': 'forged', 'fields': {'hours': 8}}, 'TEST-1'),
            lambda: service.attachment(sid, 'TEST-1', '900'),
            lambda: service.upload(sid, secrets.token_urlsafe(20), 'TEST-1',
                                   'forged', 'test.txt', 'text/plain', b'Test'),
        ]:
            with self.assertRaises(WriteError) as error:
                call()
            self.assertEqual(error.exception.status, 404)
        self.assertFalse([call for call in self.fake.calls if call[0] != 'GET'])

    def test_role_changes_and_logout_apply_to_direct_service_calls(self):
        self.login('coord')
        sid = self.sid('coord')
        self.assertTrue(self.runtime.jobs.workspace(sid)['projects'])
        self.value['invites'][0]['role'] = 'designer'
        self.assertEqual(self.runtime.jobs.workspace(sid)['projects'], [])
        self.assertEqual(self.runtime.jobs.capabilities(sid)['actor']['role'], 'designer')
        self.runtime.logout(sid)
        with self.assertRaises(WriteError) as error:
            self.runtime.jobs.workspace(sid)
        self.assertEqual(error.exception.status, 401)

    def test_permission_expiry_during_native_preflight_prevents_the_write(self):
        for change in ['logout', 'demote', 'expire_review']:
            with self.subTest(change=change):
                # Each iteration uses a fresh issued session and fresh key.
                self.value['invites'][0]['role'] = 'coordinator'
                self.value['workflowReview']['reviewedAt'] = datetime.now(timezone.utc).isoformat()
                client, _ = self.login('coord')
                sid = self.sid('coord')
                session = self.runtime.sessions[sid]
                project = self.project(client)
                original = session.reader._get_json
                def preflight(path, resource, **kwargs):
                    result = original(path, resource, **kwargs)
                    if '/automationrules' in path:
                        if change == 'logout':
                            self.runtime.logout(sid)
                        elif change == 'demote':
                            self.value['invites'][0]['role'] = 'designer'
                        else:
                            self.value['workflowReview']['reviewedAt'] = (
                                datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
                    return result
                session.reader._get_json = preflight
                with self.assertRaises(WriteError):
                    self.runtime.jobs.perform(
                        sid, secrets.token_urlsafe(20),
                        {'action': 'edit', 'revision': project['revision'], 'fields': {'hours': 8}},
                        'TEST-1')
                self.assertFalse([call for call in self.fake.calls if call[0] != 'GET'])
                # Remove the previous iteration's session without trusting a cached handle.
                self.runtime.logout(sid)

    def test_native_store_cannot_write_outside_the_authenticated_service(self):
        self.login('coord')
        session = self.runtime.sessions[self.sid('coord')]
        revision = self.runtime.jobs.get_job(self.sid('coord'), 'TEST-1')['revision']
        with self.assertRaises(WriteError) as error:
            session.reader.store.perform(
                secrets.token_urlsafe(20),
                {'action': 'edit', 'revision': revision, 'fields': {'hours': 8}}, 'TEST-1')
        self.assertEqual(error.exception.status, 403)
        self.assertFalse([call for call in self.fake.calls if call[0] != 'GET'])

    def test_attachment_contents_are_not_returned_after_session_expiry(self):
        self.login('coord')
        sid = self.sid('coord')
        session = self.runtime.sessions[sid]
        def download(job, attachment):
            session.expires = time.time() - 1
            return b'Synthetic private bytes', 'text/plain', 'test.txt'
        session.reader.attachment = Mock(side_effect=download)
        with self.assertRaises(WriteError) as error:
            self.runtime.jobs.attachment(sid, 'TEST-1', '900')
        self.assertEqual(error.exception.status, 401)
        self.assertEqual(session.reader._token, '')

    def test_attachment_contents_are_not_returned_after_role_demotion(self):
        self.login('coord')
        sid = self.sid('coord')
        def download(job, attachment):
            self.value['invites'][0]['role'] = 'designer'
            return b'Synthetic private bytes', 'text/plain', 'test.txt'
        self.runtime.sessions[sid].reader.attachment = Mock(side_effect=download)
        with self.assertRaises(WriteError) as error:
            self.runtime.jobs.attachment(sid, 'TEST-1', '900')
        self.assertEqual(error.exception.status, 403)

    def test_capability_route_does_not_enable_bearer_or_mcp_auth(self):
        client = self.app.test_client()
        response = self.get(client, '/api/v1/capabilities',
                            headers={'Authorization': 'Bearer synthetic-unissued-value'})
        self.assertEqual(response.status_code, 401)
        for route in ['/mcp', '/api/v1/jobs', '/api/v1/jobs/TEST-1/ai-drafts']:
            self.assertEqual(self.get(client, route).status_code, 404)
        viewer, _ = self.login('viewer')
        caps = self.get(viewer, '/api/v1/capabilities').get_json()
        self.assertFalse(caps['canCreate'])
        self.assertFalse(any(caps['features'].values()))
