"""OAuth HTTP and cross-user authorization boundaries, using a synthetic API."""
import copy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

HAS_FLASK = importlib.util.find_spec('flask') is not None
if HAS_FLASK:
    from backend.pilot import create_app, PilotConfig, SESSION_COOKIE, LOGIN_COOKIE
    from backend.server import SmartsheetReader, GatewayError
    from backend.dev_store import WriteError, YES
    from test_dev_writes import FakeSmartsheet


@unittest.skipUnless(HAS_FLASK, 'Install requirements-pilot.txt to run OAuth pilot tests.')
class PilotTestCase(unittest.TestCase):
    origin = 'https://pilot.example.org'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = FakeSmartsheet()
        self.value = {
            'publicOrigin': self.origin, 'clientId': 'synthetic-client-id',
            'sheetId': '123', 'filterId': '777',
            'statePath': str(Path(self.tmp.name) / 'pilot.sqlite3'),
            'expiresAt': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            'writesEnabled': True,
            'workflowReview': {'allNativeWorkflowsChecked': True, 'reviewedAt': datetime.now(timezone.utc).isoformat()},
            'invites': [{'email': email, 'role': role} for email, role in [
                ('coordinator@example.org', 'coordinator'),
                ('designer@example.org', 'designer'), ('other@example.org', 'designer'),
                ('viewer@example.org', 'designer')]],
        }
        self.profiles = {
            key: {'id': str(i + 100), 'email': email, 'firstName': key.title(), 'lastName': 'Tester'}
            for i, (key, email) in enumerate([
                ('coord', 'coordinator@example.org'), ('designer', 'designer@example.org'),
                ('other', 'other@example.org'), ('viewer', 'viewer@example.org'),
                ('outsider', 'outsider@example.org')])
        }
        self.readers, self.oauth_calls, self.access = [], [], {}
        self.app = create_app(self.value, 'synthetic-app-secret', oauth_transport=self.oauth,
                              reader_factory=self.reader, reload_config=lambda: PilotConfig(self.value))
        self.app.testing = True
        self.runtime = self.app.extensions['pilot']

    def tearDown(self):
        self.tmp.cleanup()

    def oauth(self, kind, value):
        self.oauth_calls.append((kind, value))
        if kind == 'token':
            return {'access_token': value, 'token_type': 'bearer', 'expires_in': 3600}
        return copy.deepcopy(self.profiles[value])

    def reader(self, sheet, rows, token, filter_id=None):
        def transport(path, method='GET', payload=None, headers=None):
            if self.access.get(token) == 'DENIED':
                raise GatewayError('Access revoked')
            result = self.fake(path, method, payload, headers)
            if isinstance(result, dict) and 'columns' in result:
                result['accessLevel'] = self.access.get(token, 'VIEWER' if token == 'viewer' else 'EDITOR')
            return result
        reader = SmartsheetReader(sheet, rows, token, transport, filter_id=filter_id)
        self.readers.append(reader)
        return reader

    def get(self, client, path, **kwargs):
        return client.get(path, base_url=self.origin, **kwargs)

    def begin(self, client):
        response = self.get(client, '/auth/smartsheet/login')
        self.assertEqual(response.status_code, 303)
        url = urlsplit(response.location)
        self.assertEqual(url.hostname, 'app.smartsheet.com')
        query = parse_qs(url.query)
        self.assertEqual(query['scope'], ['READ_SHEETS WRITE_SHEETS'])
        return query['state'][0]

    def login(self, who):
        client = self.app.test_client()
        state = self.begin(client)
        response = self.get(client, '/auth/smartsheet/callback', query_string={'state': state, 'code': who})
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        data = self.get(client, '/api/projects').get_json()
        return client, data

    def write(self, client, path, body, key=None, **overrides):
        csrf = self.get(client, '/api/session').get_json()['csrf']
        headers = {'Origin': self.origin, 'X-Portal-CSRF': csrf, 'Idempotency-Key': key or secrets.token_urlsafe(20)}
        headers.update(overrides)
        return client.open(path, method='POST' if path == '/api/projects' else 'PATCH',
                           base_url=self.origin, json=body, headers=headers)

    def project(self, client, job='TEST-1'):
        return next(p for p in self.get(client, '/api/projects').get_json()['projects'] if p['id'] == job)

    def action(self, client, action, job='TEST-1', **fields):
        return self.write(client, '/api/projects/' + job,
                          {'action': action, 'revision': self.project(client, job)['revision'], **fields})

    def offer(self, coord, target='designer@example.org'):
        response = self.action(coord, 'offer', designer=target)
        self.assertEqual(response.status_code, 200, response.get_json())



class PilotTests(PilotTestCase):
    def test_anonymous_routes_and_static_allowlist_never_expose_private_data(self):
        client = self.app.test_client()
        home = self.get(client, '/')
        self.assertIn(b'Continue with Smartsheet', home.data)
        for private in [b'synthetic-app-secret', b'designer@example.org', b'TEST-1', b'Preview as']:
            self.assertNotIn(private, home.data)
        self.assertEqual(self.get(client, '/api/projects').status_code, 401)
        self.assertEqual(self.get(client, '/api/projects/TEST-1/attachments/900').status_code, 401)
        for path in ['/.local/pilot.sqlite3', '/backend/pilot.py', '/assets/../README.md', '/api/verification', '/data/projects.json']:
            self.assertEqual(self.get(client, path).status_code, 404)
        config = self.get(client, '/runtime-config.js')
        self.assertIn(b'"dataMode": "pilot"', config.data)
        self.assertNotIn(b'clientId', config.data)
        self.assertIn('no-store', home.headers['Cache-Control'])
        self.assertIn("frame-ancestors 'none'", home.headers['Content-Security-Policy'])
        # The real frontend's module imports must load in the protected server too.
        for path in ['/app.js', '/domain.js', '/demo-data.js', '/styles.css', '/assets/fonts/mulish-latin.woff2']:
            with self.get(client, path) as response:
                self.assertEqual(response.status_code, 200)

    def test_oauth_state_is_browser_bound_single_use_and_has_secure_cookies(self):
        first, other = self.app.test_client(), self.app.test_client()
        state = self.begin(first)
        callback = '/auth/smartsheet/callback?state=' + state + '&code=designer'
        self.assertEqual(self.get(other, callback).status_code, 400)
        self.assertEqual(self.get(first, callback).status_code, 400)
        self.assertEqual(self.oauth_calls, [])
        state = self.begin(first)
        response = self.get(first, '/auth/smartsheet/callback', query_string={'state': state, 'code': 'designer'})
        cookies = '\n'.join(response.headers.getlist('Set-Cookie'))
        for flag in [SESSION_COOKIE, 'Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/']:
            self.assertIn(flag, cookies)
        self.assertNotIn('Domain=', cookies)
        self.assertEqual(self.get(first, '/auth/smartsheet/callback', query_string={'state': state, 'code': 'designer'}).status_code, 400)
        self.assertEqual(len([call for call in self.oauth_calls if call[0] == 'token']), 1)

    def test_expired_denied_and_uninvited_logins_fail_closed(self):
        client = self.app.test_client()
        state = self.begin(client)
        self.runtime.pending[state]['expires'] = time.time() - 1
        self.assertEqual(self.get(client, '/auth/smartsheet/callback', query_string={'state': state, 'code': 'designer'}).status_code, 400)
        self.assertEqual(self.get(client, '/auth/smartsheet/callback?error=access_denied').status_code, 401)
        state = self.begin(client)
        self.assertEqual(self.get(client, '/auth/smartsheet/callback', query_string={'state': state, 'code': 'outsider'}).status_code, 403)
        self.assertEqual(self.runtime.sessions, {})
        self.assertEqual(self.readers, [])

    def test_verified_aliases_and_immutable_id_binding(self):
        self.profiles['designer']['email'] = 'primary@example.org'
        self.profiles['designer']['alternateEmails'] = [{'email': 'designer@example.org', 'confirmed': False}]
        with self.assertRaises(WriteError): self.runtime.resolve_actor(self.profiles['designer'])
        self.profiles['designer']['alternateEmails'][0]['confirmed'] = True
        coord, _ = self.login('coord')
        self.offer(coord)
        designer, _ = self.login('designer')
        self.assertEqual(self.project(designer)['requestedDesigner'], 'primary@example.org')
        self.assertEqual(self.action(designer, 'accept').status_code, 200)
        data = self.get(designer, '/api/projects').get_json()
        self.assertEqual(next(d['jobs'] for d in data['teamWorkload'] if d['id'] == 'primary@example.org'), 1)
        self.profiles['designer']['id'] = '999'
        with self.assertRaises(WriteError): self.runtime.resolve_actor(self.profiles['designer'])

    def test_independent_tokens_designer_isolation_and_no_impersonation(self):
        coord, _ = self.login('coord')
        self.offer(coord)
        designer, data = self.login('designer')
        other, other_data = self.login('other')
        self.assertEqual({p['id'] for p in data['projects']}, {'TEST-1'})
        self.assertEqual(other_data['projects'], [])
        self.assertTrue(all('_rowId' not in p for p in data['projects']))
        self.assertFalse(self.project(coord)['permissions']['respond'])
        self.assertEqual(self.action(coord, 'accept').status_code, 403)
        body = {'action': 'accept', 'revision': self.project(designer)['revision']}
        self.assertEqual(self.write(other, '/api/projects/TEST-1', body).status_code, 404)
        self.assertEqual(self.get(other, '/api/projects/TEST-1/attachments/900').status_code, 404)
        self.assertEqual(self.action(designer, 'accept').status_code, 200)
        self.assertEqual(self.action(designer, 'stage', stage='In Progress').status_code, 200)
        self.assertEqual({reader._token for reader in self.readers}, {'coord', 'designer', 'other'})
        self.assertIs(self.readers[0]._lock, self.readers[1]._lock)
        spoof = {'action': 'edit', 'revision': self.project(designer)['revision'], 'fields': {'hours': 4}, 'role': 'coordinator'}
        self.assertEqual(self.write(designer, '/api/projects/TEST-1', spoof).status_code, 400)

    def test_viewer_revoked_source_and_removed_invites_are_enforced(self):
        viewer, data = self.login('viewer')
        self.assertFalse(data['canCreate'])
        self.assertEqual(self.write(viewer, '/api/projects', {'fields': {}}).status_code, 403)
        designer, _ = self.login('designer')
        self.access['designer'] = 'DENIED'
        self.assertEqual(self.get(designer, '/api/projects').status_code, 502)
        self.value['invites'] = [i for i in self.value['invites'] if i['email'] != 'viewer@example.org']
        self.assertEqual(self.get(viewer, '/api/projects').status_code, 403)
        self.assertEqual(self.readers[0]._token, '')

    def test_origin_csrf_methods_host_and_logout(self):
        coord, _ = self.login('coord')
        for overrides in [{'Origin': 'https://evil.example'}, {'X-Portal-CSRF': 'incorrect'}]:
            self.assertEqual(self.write(coord, '/api/projects', {'fields': {}}, **overrides).status_code, 403)
        for method in ['DELETE', 'PUT', 'TRACE', 'OPTIONS']:
            self.assertEqual(coord.open('/api/projects/TEST-1', method=method, base_url=self.origin).status_code, 405)
        before = len(self.runtime.pending)
        self.assertEqual(coord.head('/auth/smartsheet/login', base_url=self.origin).status_code, 405)
        self.assertEqual(coord.head('/auth/smartsheet/callback?code=designer', base_url=self.origin).status_code, 405)
        self.assertEqual(before, len(self.runtime.pending))
        self.assertIn(coord.get('/', base_url='https://evil.example').status_code, [400, 403])
        csrf = self.get(coord, '/api/session').get_json()['csrf']
        result = coord.post('/auth/logout', base_url=self.origin, json={}, headers={'Origin': self.origin, 'X-Portal-CSRF': csrf})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.readers[0]._token, '')
        self.assertEqual(self.get(coord, '/api/projects').status_code, 401)

    def test_idle_and_absolute_session_expiry(self):
        client, _ = self.login('designer')
        session = next(iter(self.runtime.sessions.values()))
        session.last_seen = time.time() - 1801
        self.assertEqual(self.get(client, '/api/projects').status_code, 401)
        self.assertEqual(session.reader._token, '')
        client, _ = self.login('designer')
        next(iter(self.runtime.sessions.values())).expires = time.time() - 1
        self.assertEqual(self.get(client, '/api/projects').status_code, 401)

    def test_create_retries_are_user_scoped_and_requestor_is_verified(self):
        first, _ = self.login('designer')
        other, _ = self.login('other')
        body = {'fields': {'title': 'Synthetic intake', 'description': 'Fictional project', 'taskType': 'Other',
                           'requestor': 'Impersonated person', 'email': 'spoof@example.org', 'dueDate': ''}}
        key = 'same-client-request-key'
        saved = self.write(first, '/api/projects', body, key).get_json()
        again = self.write(first, '/api/projects', body, key).get_json()
        separate = self.write(other, '/api/projects', body, key).get_json()
        self.assertEqual(saved['jobId'], again['jobId'])
        self.assertNotEqual(saved['jobId'], separate['jobId'])
        p = self.project(first, saved['jobId'])
        self.assertEqual(p['requestor'], 'Designer Tester')
        self.assertTrue(p['permissions']['edit'])
        self.assertNotIn(saved['jobId'], [p['id'] for p in separate['projects']])
        self.assertEqual(len([call for call in self.fake.calls if call[0] != 'GET']), 2)
        with self.runtime.db() as db:
            self.assertNotIn('synthetic-app-secret', str(db.execute('SELECT * FROM audit').fetchall()))

    def test_add_only_attachments_require_job_permission_and_revision(self):
        coord, _ = self.login('coord')
        self.offer(coord)
        designer, _ = self.login('designer')
        csrf = self.get(designer, '/api/session').get_json()['csrf']
        def upload():
            return designer.post('/api/projects/TEST-1/attachments', base_url=self.origin, data=b'Synthetic reference',
                headers={'Origin': self.origin, 'X-Portal-CSRF': csrf, 'Idempotency-Key': 'synthetic-upload-key',
                         'X-Filename': 'sample.txt', 'X-Project-Revision': self.project(designer)['revision'],
                         'Content-Type': 'text/plain'})
        self.assertEqual(upload().status_code, 403)
        self.assertEqual(self.action(designer, 'accept').status_code, 200)
        self.assertEqual(upload().status_code, 200)
        self.assertEqual(upload().status_code, 200)
        self.assertEqual(len([call for call in self.fake.calls if call[1].endswith('/attachments') and call[0] == 'POST']), 1)

    def test_expired_workflow_review_pauses_writes_and_config_requires_timezone(self):
        coord, _ = self.login('coord')
        self.value['workflowReview']['reviewedAt'] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        self.assertFalse(self.get(coord, '/api/projects').get_json()['canCreate'])
        self.assertEqual(self.write(coord, '/api/projects', {'fields': {}}).status_code, 403)
        invalid = {**self.value, 'expiresAt': '2026-12-01T12:00:00'}
        with self.assertRaises(WriteError): PilotConfig(invalid)
        self.assertEqual(PilotConfig({**self.value, 'publicOrigin': self.origin + ':443'}).origin, self.origin)

    def test_launcher_retries_empty_secret_without_echoing_it(self):
        from backend.pilot import main
        config_path = Path(self.tmp.name) / 'config.json'
        config_path.write_text(json.dumps(self.value))
        output = io.StringIO()
        with patch('sys.argv', ['pilot', '--config', str(config_path), '--secret-source', 'prompt', '--port', '0']), \
             patch('backend.pilot_credentials.sys.stdin.isatty', return_value=True), \
             patch('backend.pilot_credentials.getpass.getpass', side_effect=['', 'synthetic-app-secret']), \
             patch('waitress.serve') as serve, redirect_stdout(output):
            main()
        self.assertIn('No secret received.', output.getvalue())
        self.assertIn('Authenticated pilot ready', output.getvalue())
        self.assertNotIn('synthetic-app-secret', output.getvalue())
        self.assertEqual(serve.call_args.kwargs['host'], '127.0.0.1')

    def test_macos_launcher_uses_saved_keychain_secret_without_prompt(self):
        from backend.pilot import main
        config_path = Path(self.tmp.name) / 'config.json'
        config_path.write_text(json.dumps(self.value))
        output = io.StringIO()
        with patch('sys.argv', ['pilot', '--config', str(config_path), '--port', '0']), \
             patch('backend.pilot.sys.platform', 'darwin'), \
             patch('backend.pilot_credentials.read_keychain', return_value='synthetic-keychain-secret') as read, \
             patch('backend.pilot_credentials.getpass.getpass') as prompt, \
             patch('waitress.serve') as serve, redirect_stdout(output):
            main()
        read.assert_called_once_with(self.value['clientId'])
        prompt.assert_not_called()
        self.assertIn('Authenticated pilot ready', output.getvalue())
        self.assertNotIn('synthetic-keychain-secret', output.getvalue())
        self.assertEqual(serve.call_args.kwargs['host'], '127.0.0.1')

    def test_busy_port_stops_before_reading_credentials(self):
        from backend.pilot import main
        with patch('sys.argv', ['pilot']), \
             patch('backend.pilot.socket.socket', side_effect=OSError('busy')), \
             patch('backend.pilot.load_secret') as load:
            with self.assertRaisesRegex(WriteError, 'already in use'):
                main()
        load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
