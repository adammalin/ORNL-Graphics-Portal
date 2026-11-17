"""Microsoft employee intake: isolated identity and create/add-only DEV access.

No requester ever receives the integration credential or a sheet workspace.
MSAL owns code flow state/nonce/PKCE validation; tokens are discarded after /me.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import re
import secrets
import time
from urllib.request import Request, build_opener

try:
    from backend.dev_store import WriteError, revision
    from backend.job_service import PilotStore, KEY, WRITABLE_ACCESS
    from backend.principals import Actor
    from backend.server import NoRedirect
except ImportError:
    from dev_store import WriteError, revision
    from job_service import PilotStore, KEY, WRITABLE_ACCESS
    from principals import Actor
    from server import NoRedirect

COOKIE = '__Host-graphics_requester'
LOGIN_COOKIE = '__Host-graphics_microsoft_login'
CALLBACK = '/auth/microsoft/callback'
GUID = re.compile(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')
EMAIL = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')
ALLOWED_FIELDS = frozenset({'title', 'description', 'taskType', 'dueDate', 'deliverables',
    'audience', 'specifications', 'requestorGroup', 'reference1', 'reference2', 'notes',
    'requestor', 'email'})


def settings(config):
    value = config.value.get('microsoftIntake') or {}
    if value.get('enabled') is not True:
        return None
    if not all(isinstance(value.get(k), str) and GUID.fullmatch(value[k])
               for k in ('tenantId', 'clientId')):
        raise WriteError('Configure the single-tenant Microsoft intake application IDs.', 503)
    if not str(value.get('integrationUserId', '')).isdigit():
        raise WriteError('Pin the approved intake integration Smartsheet user ID.', 503)
    role = value.get('requiredRole', '')
    if not isinstance(role, str) or len(role) > 100:
        raise WriteError('Invalid Microsoft intake eligibility role.', 503)
    return {k: value.get(k, '') for k in ('tenantId', 'clientId', 'integrationUserId', 'requiredRole')}


class MicrosoftOAuth:
    """One MSAL client/cache per pending browser flow, never a persisted token cache."""
    def __init__(self, config, secret, origin):
        if not secret:
            raise WriteError('Enter the Microsoft intake app secret locally.', 503)
        self.config, self._secret, self.origin = config, secret, origin

    def begin(self):
        import msal
        try:
            client = msal.ConfidentialClientApplication(
                self.config['clientId'], client_credential=self._secret,
                authority='https://login.microsoftonline.com/' + self.config['tenantId'],
                token_cache=msal.TokenCache(), exclude_scopes=['offline_access'],
                enable_pii_log=False, timeout=25)
            flow = client.initiate_auth_code_flow(
                scopes=['User.Read'], redirect_uri=self.origin + CALLBACK,
                response_mode='query', max_age=3600)
        except Exception:
            raise WriteError('Microsoft sign-in is unavailable. Contact the pilot owner.', 503) from None
        if not flow.get('auth_uri') or not flow.get('state'):
            raise WriteError('Microsoft sign-in is unavailable. Contact the pilot owner.', 503)
        return flow, client

    def complete(self, flow, client, response):
        try:
            result = client.acquire_token_by_auth_code_flow(flow, response)
            claims, token = result.get('id_token_claims'), result.get('access_token')
            if not isinstance(claims, dict) or not isinstance(token, str) or not token:
                raise ValueError()
            url = 'https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,department,userType'
            req = Request(url, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
            with build_opener(NoRedirect()).open(req, timeout=25) as reply:
                profile = json.loads(reply.read(100000))
            return claims, profile
        except Exception:
            raise WriteError('Microsoft sign-in could not be verified. Start sign-in again.', 401) from None
        finally:
            # The pending flow/client and its in-memory token cache are not retained.
            if 'result' in locals():
                result.clear()


@dataclass(frozen=True)
class Requester:
    tenant: str
    oid: str
    name: str
    email: str
    department: str

    @property
    def key(self):
        return self.tenant + ':' + self.oid


@dataclass
class RequesterSession:
    actor: Requester
    csrf: str
    expires: float
    last_seen: float


class IntakeStore(PilotStore):
    def _write(self, method, path, *args, **kwargs):
        # Defense in depth even if a future caller accidentally invokes edit/stage.
        root = '/sheets/' + self.reader.sheet_id
        if method != 'POST' or not (path == root + '/rows'
                or re.fullmatch(re.escape(root) + r'/rows/\d+/attachments', path)):
            raise WriteError('Employee intake can only create requests and add reference files.', 403)
        return super()._write(method, path, *args, **kwargs)


class IntakeService:
    def __init__(self, runtime, microsoft_secret, integration_token, oauth=None):
        self.runtime = runtime
        self.config = settings(runtime.config)
        if not self.config or not integration_token:
            raise WriteError('Microsoft intake needs its own approved integration connection.', 503)
        self.oauth = oauth or MicrosoftOAuth(self.config, microsoft_secret, runtime.config.origin)
        profile = runtime.oauth.profile(integration_token)
        if str(profile.get('id')) != self.config['integrationUserId']:
            raise WriteError('The intake integration account does not match its approved identity.', 403)
        self.reader = runtime.reader_factory(runtime.config.sheet_id, [], integration_token,
                                              filter_id=runtime.config.filter_id)
        self.reader._lock = runtime.sheet_lock
        self.reader.projects(force=True)
        actor = Actor(str(profile['id']), '', 'Employee intake integration', frozenset(), '', 'integration')
        self.reader.store = IntakeStore(self.reader, runtime.config.path, runtime, actor)
        self.pending, self.sessions, self.attempts = {}, {}, []
        with runtime.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS employee_intake_receipts '
                       '(receipt TEXT PRIMARY KEY, owner TEXT NOT NULL, key TEXT NOT NULL, sheet TEXT NOT NULL, '
                       'created REAL NOT NULL, job TEXT, title TEXT, UNIQUE(owner,key,sheet))')
            db.execute('CREATE TABLE IF NOT EXISTS employee_intake_files '
                       '(receipt TEXT NOT NULL, key TEXT NOT NULL, name TEXT NOT NULL, '
                       'PRIMARY KEY(receipt,key))')
            db.execute('CREATE TABLE IF NOT EXISTS employee_intake_audit '
                       '(at REAL NOT NULL, owner TEXT NOT NULL, action TEXT NOT NULL, '
                       'receipt TEXT NOT NULL, outcome TEXT NOT NULL)')

    def active(self):
        cfg = self.runtime.active_config()
        if settings(cfg) != self.config:
            raise WriteError('Microsoft intake configuration changed. Restart the service.', 503)
        return cfg

    def cleanup(self):
        now = time.time()
        for key, value in list(self.pending.items()):
            if value['expires'] <= now:
                self.pending.pop(key, None)
        for key, value in list(self.sessions.items()):
            if value.expires <= now or value.last_seen + 1800 <= now:
                self.sessions.pop(key, None)
        self.attempts = [at for at in self.attempts if now - at < 60]

    def begin(self):
        self.active()
        with self.runtime.lock:
            self.cleanup()
            if len(self.pending) >= 100 or len(self.attempts) >= 30:
                raise WriteError('Too many sign-in attempts. Try again shortly.', 429)
            self.attempts.append(time.time())
            flow, client = self.oauth.begin()
            browser = secrets.token_urlsafe(32)
            self.pending[flow['state']] = {'flow': flow, 'client': client,
                'browser': browser, 'expires': time.time() + 600}
            return flow['auth_uri'], browser

    def complete(self, response, browser):
        cfg = self.active()
        state = response.get('state', '')
        with self.runtime.lock:
            self.cleanup()
            pending = self.pending.pop(state, None)
        if not pending or not isinstance(browser, str) or not hmac.compare_digest(browser, pending['browser']):
            raise WriteError('This sign-in expired or belongs to another browser. Start again.', 400)
        claims, profile = self.oauth.complete(pending['flow'], pending['client'], response)
        tenant, oid = str(claims.get('tid', '')).lower(), str(claims.get('oid', '')).lower()
        if (tenant != self.config['tenantId'].lower() or not GUID.fullmatch(oid)
                or str(profile.get('id', '')).lower() != oid or profile.get('userType') != 'Member'):
            raise WriteError('Intake is limited to approved organization member accounts. Guest accounts cannot submit.', 403)
        role = self.config['requiredRole']
        roles = claims.get('roles', [])
        if role and (not isinstance(roles, list) or role not in roles):
            raise WriteError('Your Microsoft account is not assigned the intake role.', 403)
        email, name = str(profile.get('mail') or '').strip().lower(), str(profile.get('displayName') or '').strip()
        if not EMAIL.fullmatch(email) or len(email) > 254 or not name or len(name) > 200:
            raise WriteError('Microsoft did not provide your contact name and email. Ask IT to complete your directory profile.', 403)
        try:
            token_expiry = float(claims['exp'])
            if not math.isfinite(token_expiry):
                raise ValueError()
            expires = min(token_expiry, time.time() + 3600, cfg.expires)
            if expires < time.time() + 60:
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise WriteError('Microsoft sign-in has expired. Start again.', 401) from None
        actor = Requester(tenant, oid, name, email, str(profile.get('department') or '')[:200])
        sid = secrets.token_urlsafe(32)
        with self.runtime.lock:
            self.cleanup()
            if len(self.sessions) >= 100:
                raise WriteError('The intake session limit has been reached. Try again later.', 503)
            self.sessions[sid] = RequesterSession(actor, secrets.token_urlsafe(32), expires, time.time())
        return sid, self.sessions[sid]

    def session(self, sid):
        self.active()
        with self.runtime.lock:
            self.cleanup()
            session = self.sessions.get(sid or '')
            if not session:
                raise WriteError('Sign in with your organization Microsoft account to submit a request.', 401)
            session.last_seen = time.time()
            return session

    def logout(self, sid):
        with self.runtime.lock:
            self.sessions.pop(sid or '', None)

    def info(self, sid):
        session = self.session(sid)
        with self.runtime.sheet_lock:
            self.reader.projects(force=True)
            data = self.reader.store.metadata()
            self.session(sid)
        actor = session.actor
        cfg = self.active()
        return {'name': actor.name, 'email': actor.email, 'department': actor.department,
                'csrf': session.csrf, 'taskTypes': data['taskTypes'],
                'taskTypeMultiple': data['taskTypeMultiple'],
                'canSubmit': bool(cfg.writes and cfg.workflow_review_valid()
                                  and self.reader.sheet.get('accessLevel') in WRITABLE_ACCESS)}

    def guard(self, sid, actor):
        if self.session(sid).actor != actor:
            raise WriteError('Your sign-in changed. Sign in again.', 403)
        self.reader.store.require_writes()

    def audit(self, actor, action, receipt, outcome):
        with self.runtime.db() as db:
            db.execute('INSERT INTO employee_intake_audit VALUES (?,?,?,?,?)',
                       (time.time(), actor.key, action, receipt, outcome))

    def owned(self, actor, receipt):
        with self.runtime.db() as db:
            row = db.execute('SELECT job FROM employee_intake_receipts WHERE receipt=? AND owner=? AND sheet=?',
                             (receipt, actor.key, self.reader.sheet_id)).fetchone()
        if not row or not row[0]:
            raise WriteError('This submission receipt is not available.', 404)
        return row[0]

    def receipt(self, sid, receipt):
        actor = self.session(sid).actor
        with self.runtime.sheet_lock:
            job = self.owned(actor, receipt)
            self.reader.projects(force=True)
            row = self.reader.store.row(job)
            project = next((p for p in self.reader._cache['projects'] if p['id'] == job), None)
            if not project:
                raise WriteError('The request is not available. Contact Creative Services with your receipt.', 404)
            # A receipt never reveals later internal references added by designers.
            with self.runtime.db() as db:
                title = db.execute('SELECT title FROM employee_intake_receipts WHERE receipt=?', (receipt,)).fetchone()[0]
                files = db.execute('SELECT name FROM employee_intake_files WHERE receipt=? ORDER BY rowid', (receipt,)).fetchall()
            self.session(sid)
            return {'receipt': receipt, 'jobId': job, 'title': title,
                    'revision': revision(row), 'attachments': [
                        {'name': name} for (name,) in files]}

    @staticmethod
    def operation_key(actor, key, action):
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise WriteError('A valid save identifier is required.')
        return hashlib.sha256(('microsoft-intake:' + actor.key + ':' + action + ':' + key).encode()).hexdigest()

    def create(self, sid, key, body):
        actor = self.session(sid).actor
        hashed = self.operation_key(actor, key, 'create')
        if not isinstance(body, dict) or set(body) != {'fields'} or not isinstance(body['fields'], dict):
            raise WriteError('Invalid intake fields.')
        fields = body['fields']
        if set(fields) - ALLOWED_FIELDS:
            raise WriteError('Unknown intake field.')
        body = {'fields': {**fields, 'requestor': actor.name, 'email': actor.email}}
        with self.runtime.sheet_lock:
            self.guard(sid, actor)
            with self.runtime.db() as db:
                row = db.execute('SELECT receipt FROM employee_intake_receipts WHERE owner=? AND key=? AND sheet=?',
                                 (actor.key, hashed, self.reader.sheet_id)).fetchone()
                if row:
                    receipt = row[0]
                else:
                    count = db.execute('SELECT COUNT(*) FROM employee_intake_receipts WHERE owner=? AND created>? AND sheet=?',
                                       (actor.key, time.time() - 86400, self.reader.sheet_id)).fetchone()[0]
                    if count >= 20:
                        raise WriteError('You have reached the daily pilot request limit. Contact Creative Services.', 429)
                    receipt = secrets.token_urlsafe(24)
                    db.execute('INSERT INTO employee_intake_receipts VALUES (?,?,?,?,?,NULL,NULL)',
                               (receipt, actor.key, hashed, self.reader.sheet_id, time.time()))
            try:
                with self.reader.store.authorized_writes(lambda: self.guard(sid, actor)):
                    result = self.reader.store.perform(hashed, body)
                with self.runtime.db() as db:
                    project = next(p for p in result['projects'] if p['id'] == result['jobId'])
                    db.execute('UPDATE employee_intake_receipts SET job=?,title=COALESCE(title,?) WHERE receipt=? AND owner=?',
                               (result['jobId'], project['title'], receipt, actor.key))
                self.audit(actor, 'create', receipt, 'success')
                return self.receipt(sid, receipt)
            except Exception:
                self.audit(actor, 'create', receipt, 'unconfirmed')
                raise

    def upload(self, sid, key, receipt, expected, name, mime, content):
        actor = self.session(sid).actor
        key = self.operation_key(actor, key, 'upload')
        with self.runtime.sheet_lock:
            self.guard(sid, actor)
            job = self.owned(actor, receipt)
            self.reader.projects(force=True)
            row = self.reader.store.row(job)
            project = next((p for p in self.reader._cache['projects'] if p['id'] == job), {})
            # Uploads are available for one day, while the request is still New.
            with self.runtime.db() as db:
                created = db.execute('SELECT created FROM employee_intake_receipts WHERE receipt=?', (receipt,)).fetchone()[0]
                replay = db.execute('SELECT 1 FROM operations WHERE sheet=? AND key=?', (self.reader.sheet_id, key)).fetchone()
            if not replay and (project.get('stage') != 'New' or time.time() - created > 86400 or len(row.get('attachments', [])) >= 10):
                raise WriteError('Reference uploads are closed for this submission. Contact Creative Services.', 403)
            with self.reader.store.authorized_writes(lambda: self.guard(sid, actor)):
                self.reader.store.upload(key, job, expected, name, mime, content)
            with self.runtime.db() as db:
                db.execute('INSERT OR IGNORE INTO employee_intake_files VALUES (?,?,?)', (receipt, key, name))
            self.audit(actor, 'upload', receipt, 'success')
            return self.receipt(sid, receipt)
