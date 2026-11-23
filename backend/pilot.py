"""Invited-user Smartsheet OAuth pilot. No shared-token fallback or delete API.

Use the local editor separately. This service binds only to loopback; its configured
HTTPS origin is supplied by an authenticated development tunnel. Tokens and sessions
live only in memory. The public Pages build never enables this mode.
"""
import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import getpass
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import socket
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, quote
from urllib.request import Request, build_opener

from flask import Flask, Response, jsonify, redirect, request, send_from_directory

try:
    from backend.server import SmartsheetReader, GatewayError, NoRedirect, WEB, MAX_FILE_BYTES, media_type
    from backend.dev_store import WriteError, SaveRefreshError
    from backend.principals import Actor
    from backend.job_service import JobService, PilotStore
    from backend.ai_repository import migrate_private_state
    from backend import microsoft_intake as employee_intake
    from backend.ai_service import AiService, settings as ai_settings
    from backend.ai_validation import strict_json
    from backend.pilot_credentials import CredentialError, client_id_from_config, load_secret
    from backend.onboarding import Onboarding
except ImportError:
    from server import SmartsheetReader, GatewayError, NoRedirect, WEB, MAX_FILE_BYTES, media_type
    from dev_store import WriteError, SaveRefreshError
    from principals import Actor
    from job_service import JobService, PilotStore
    from ai_repository import migrate_private_state
    import microsoft_intake as employee_intake
    from ai_service import AiService, settings as ai_settings
    from ai_validation import strict_json
    from pilot_credentials import CredentialError, client_id_from_config, load_secret
    from onboarding import Onboarding

SESSION_COOKIE = '__Host-graphics_pilot'
LOGIN_COOKIE = '__Host-graphics_login'
CALLBACK = '/auth/smartsheet/callback'
EMAIL = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')


def equal(a, b):
    return isinstance(a, str) and isinstance(b, str) and hmac.compare_digest(a.encode(), b.encode())


def utc_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('timezone required')
        return parsed.timestamp()
    except (AttributeError, ValueError, TypeError):
        raise WriteError('Pilot expiry/review dates must be timezone-aware ISO timestamps.', 503) from None


def check_port_available(port):
    try:
        with socket.socket() as probe:
            # Match the server's reuse behavior after a graceful stop. TIME_WAIT
            # connections must not be mistaken for a still-running listener.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))
    except OSError:
        raise WriteError('Port '+str(port)+' is already in use. Reuse the existing pilot Terminal, or stop it with Ctrl+C before starting another server.', 503) from None


class PilotConfig:
    def __init__(self, value):
        self.value = dict(value)
        parsed = urlsplit(value.get('publicOrigin', ''))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.port not in (None, 443):
            raise WriteError('Set publicOrigin to the exact HTTPS pilot origin, without a path or port.', 503)
        self.host = parsed.hostname.lower()
        self.origin = 'https://' + self.host
        self.client_id = value.get('clientId', '')
        if not isinstance(self.client_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,200}', self.client_id):
            raise WriteError('Register the Smartsheet OAuth app and set its clientId.', 503)
        self.sheet_id = str(value.get('sheetId', ''))
        self.filter_id = str(value.get('filterId', ''))
        copied = value.get('copiedRowIds', [])
        if (not isinstance(copied, list) or len(copied) > 20
                or any(not isinstance(r, str) or not re.fullmatch(r'\d{1,20}', r) for r in copied)
                or len(set(copied)) != len(copied)):
            raise WriteError('Select at most twenty unique copied DEV row IDs for read-only display.', 503)
        self.copied_row_ids = frozenset(copied)
        if not self.sheet_id.isdigit() or not self.filter_id.isdigit():
            raise WriteError('The approved DEV sheet and filter must be configured.', 503)
        self.expires = utc_time(value.get('expiresAt', ''))
        if not time.time() < self.expires <= time.time() + 7 * 86400 + 60:
            raise WriteError('The pilot must expire within seven days.', 503)
        self.invites = {}
        for item in value.get('invites', []):
            email = str(item.get('email', '')).strip().lower()
            role = item.get('role', 'designer')
            if not EMAIL.fullmatch(email) or role not in ('designer', 'coordinator', 'admin') or email in self.invites:
                raise WriteError('Each invite needs a unique email and designer/coordinator/admin role.', 503)
            self.invites[email] = role
        if not self.invites or len(self.invites) > 20:
            raise WriteError('Configure between one and twenty named pilot invites.', 503)
        try:
            from backend.organizations import validate_policy
        except ImportError:
            from organizations import validate_policy
        try:
            self.organization_routing = validate_policy(value.get('organizationRouting'),
                {email for email, role in self.invites.items() if role in ('admin', 'coordinator')})
        except (ValueError, TypeError, KeyError) as error:
            raise WriteError('Invalid private organization routing: ' + str(error), 503) from None
        self.path = Path(value.get('statePath', Path(__file__).resolve().parents[1] / '.local/pilot-state.sqlite3'))
        self.writes = value.get('writesEnabled') is True
        employee_intake.settings(self)  # Validate optional identity configuration.
        ai_settings(self)

    def available(self):
        if time.time() >= self.expires:
            raise WriteError('This pilot has expired. Contact the pilot owner.', 403)

    def workflow_review_valid(self):
        review = self.value.get('workflowReview') or {}
        if review.get('allNativeWorkflowsChecked') is not True:
            return False
        try:
            reviewed = utc_time(review.get('reviewedAt', ''))
            if 'validUntil' in review:
                until = utc_time(review['validUntil'])
                # A completed native review can cover the explicitly approved
                # pilot window. Never carry it into another renewal automatically.
                return (reviewed <= time.time() < until <= self.expires
                        and 0 < until - reviewed <= 7 * 86400 + 60)
        except WriteError:
            return False
        return 0 <= time.time() - reviewed < 24 * 3600


@dataclass
class PilotSession:
    actor: Actor
    reader: object
    csrf: str
    created: float
    expires: float
    last_seen: float
    access_checked: float = 0
    lock: object = field(default_factory=threading.RLock)


class OAuthClient:
    def __init__(self, client_id, secret, origin, transport=None):
        self.client_id, self._secret, self.origin = client_id, secret, origin
        self.transport = transport
        self.opener = build_opener(NoRedirect())

    def authorize_url(self, state):
        return 'https://app.smartsheet.com/b/authorize?' + urlencode({'client_id': self.client_id, 'response_type': 'code', 'scope': 'READ_SHEETS WRITE_SHEETS', 'state': state})

    def exchange(self, code):
        if not isinstance(code, str) or not code or len(code) > 2000:
            raise WriteError('Smartsheet did not provide a valid authorization code.', 400)
        if self.transport:
            return self.transport('token', code)
        body = urlencode({'grant_type': 'authorization_code', 'code': code, 'client_id': self.client_id, 'client_secret': self._secret}).encode()
        try:
            req = Request('https://api.smartsheet.com/2.0/token', data=body, headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}, method='POST')
            with self.opener.open(req, timeout=30) as response:
                data = json.loads(response.read(100000))
        except (HTTPError, URLError, TimeoutError, ValueError):
            raise WriteError('Smartsheet authorization could not be completed. Start sign-in again.', 401) from None
        if not data.get('access_token') or data.get('token_type', '').lower() != 'bearer':
            raise WriteError('Smartsheet did not return an access token.', 401)
        return data

    def profile(self, token):
        if self.transport:
            return self.transport('profile', token)
        req = Request('https://api.smartsheet.com/2.0/users/me', headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
        try:
            with self.opener.open(req, timeout=25) as response:
                return json.loads(response.read(100000))
        except (HTTPError, URLError, TimeoutError, ValueError):
            raise WriteError('The Smartsheet account could not be verified. Sign in again.', 401) from None


class PilotRuntime:
    def __init__(self, config, oauth, reader_factory=SmartsheetReader, reload_config=None):
        self.config, self.oauth = config, oauth
        self.reader_factory, self.reload_config = reader_factory, reload_config
        self.sheet_lock = threading.RLock()
        self.lock = threading.RLock()
        self.pending, self.sessions, self.login_attempts = {}, {}, []
        migrate_private_state(config.path)
        self.jobs = JobService(self)
        self.ai = AiService(self)
        config.path.parent.mkdir(parents=True, exist_ok=True)
        config.path.touch(mode=0o600, exist_ok=True)
        config.path.chmod(0o600)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS bindings (invite TEXT PRIMARY KEY, user_id TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS creators (sheet TEXT, job TEXT, user_id TEXT, PRIMARY KEY(sheet,job))')
            db.execute('CREATE TABLE IF NOT EXISTS audit (at TEXT, user_id TEXT, role TEXT, action TEXT, job TEXT, outcome TEXT)')

    def db(self):
        return sqlite3.connect(str(self.config.path), timeout=15)

    def active_config(self):
        config = self.reload_config() if self.reload_config else self.config
        # Changing an origin/client/source underneath live sessions requires restart.
        if (config.origin, config.client_id, config.sheet_id, config.filter_id) != (self.config.origin, self.config.client_id, self.config.sheet_id, self.config.filter_id):
            raise WriteError('The pilot connection configuration changed. Restart the service.', 503)
        config.available()
        return config

    def cleanup(self):
        now = time.time()
        for state, data in list(self.pending.items()):
            if data['expires'] <= now:
                self.pending.pop(state, None)
        for sid, session in list(self.sessions.items()):
            if session.expires <= now or session.last_seen + 1800 <= now:
                self.sessions.pop(sid, None)
                session.reader._token = ''
        self.login_attempts = [t for t in self.login_attempts if now - t < 60]

    def begin_login(self):
        self.active_config()
        with self.lock:
            self.cleanup()
            if len(self.pending) >= 100 or len(self.login_attempts) >= 30:
                raise WriteError('Too many sign-in attempts. Please try again shortly.', 429)
            state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.pending[state] = {'browser': browser, 'expires': time.time() + 600}
            self.login_attempts.append(time.time())
        return state, browser

    def resolve_actor(self, profile):
        config = self.active_config()
        uid = str(profile.get('id', ''))
        email = str(profile.get('email', '')).strip().lower()
        if not uid.isdigit() or not EMAIL.fullmatch(email):
            raise WriteError('Smartsheet returned an incomplete account profile.', 403)
        identities = {email}
        for item in profile.get('alternateEmails', []):
            address = str(item.get('email', '')).lower()
            if item.get('confirmed') is True and EMAIL.fullmatch(address):
                identities.add(address)
        invited = identities.intersection(config.invites)
        if len(invited) != 1:
            raise WriteError('This Smartsheet account is not uniquely matched to a pilot invite. Contact the pilot owner.', 403)
        invite = invited.pop()
        with self.db() as db:
            prior = db.execute('SELECT user_id FROM bindings WHERE invite=?', (invite,)).fetchone()
            if prior and prior[0] != uid:
                raise WriteError('This invite is already linked to a different Smartsheet account. Contact the pilot owner.', 403)
            db.execute('INSERT OR IGNORE INTO bindings VALUES (?,?)', (invite, uid))
        name = ' '.join(str(profile.get(k, '')).strip() for k in ('firstName', 'lastName')).strip() or email
        return Actor(uid, email, name[:200], frozenset(identities), invite, config.invites[invite])

    def complete_login(self, state, browser, code):
        self.active_config()
        with self.lock:
            self.cleanup()
            pending = self.pending.pop(state, None)
        if not pending or not equal(browser, pending['browser']):
            raise WriteError('The sign-in request expired or belongs to another browser. Start again.', 400)
        tokens = self.oauth.exchange(code)
        token = tokens.get('access_token')
        if not isinstance(token, str) or not token:
            raise WriteError('Smartsheet did not return an access token.', 401)
        actor = self.resolve_actor(self.oauth.profile(token))
        reader = self.reader_factory(self.config.sheet_id, [], token, filter_id=self.config.filter_id)
        reader.copied_row_ids = self.active_config().copied_row_ids
        reader._lock = self.sheet_lock  # One writer per sheet across all pilot sessions.
        reader.projects(force=True)  # Uses this user's token; never a shared-token fallback.
        reader.store = PilotStore(reader, self.config.path, self, actor)
        now = time.time()
        try:
            lifetime = min(21600, max(0, float(tokens.get('expires_in', 21600)) - 60))
        except (ValueError, TypeError):
            raise WriteError('Smartsheet returned an invalid token lifetime.', 401) from None
        if lifetime < 60:
            raise WriteError('The Smartsheet authorization has already expired. Sign in again.', 401)
        session = PilotSession(actor, reader, secrets.token_urlsafe(32), now, min(now + lifetime, self.config.expires), now, now)
        with self.lock:
            self.cleanup()
            if len(self.sessions) >= 100:
                raise WriteError('The pilot has reached its session limit.', 503)
            sid = secrets.token_urlsafe(32)
            self.sessions[sid] = session
        self.audit(actor, 'sign-in', '', 'success')
        return sid, session

    def session(self, sid):
        config = self.active_config()
        with self.lock:
            self.cleanup()
            session = self.sessions.get(sid or '')
            if not session:
                raise WriteError('Sign in to Smartsheet to open the pilot.', 401)
            role = config.invites.get(session.actor.invite_email)
            if role is None:
                self.sessions.pop(sid, None)
                session.reader._token = ''
                raise WriteError('This pilot invite has been removed.', 403)
            session.actor.role = role
            session.last_seen = time.time()
            return session

    def logout(self, sid):
        with self.lock:
            session = self.sessions.pop(sid or '', None)
            if session:
                session.reader._token = ''
                self.audit(session.actor, 'sign-out', '', 'success')

    def audit(self, actor, action, job, outcome):
        with self.db() as db:
            db.execute('INSERT INTO audit VALUES (?,?,?,?,?,?)', (datetime.now(timezone.utc).isoformat(),actor.user_id,actor.role,action,job,outcome))


def create_app(config, secret, oauth_transport=None, reader_factory=SmartsheetReader, reload_config=None,
               microsoft_secret=None, intake_token=None, microsoft_oauth=None, reconciliation_plan=None):
    if not secret:
        raise WriteError('Enter the OAuth app secret at the hidden local prompt.',503)
    config = config if isinstance(config,PilotConfig) else PilotConfig(config)
    runtime = PilotRuntime(config,OAuthClient(config.client_id,secret,config.origin,oauth_transport),reader_factory,reload_config)
    from backend.job_lifecycle import JobLifecycle
    runtime.lifecycle = JobLifecycle(runtime)
    app = Flask(__name__,static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=MAX_FILE_BYTES,TRUSTED_HOSTS=[config.host,'127.0.0.1','localhost'])
    app.extensions['pilot'] = runtime
    app.extensions['job_service'] = runtime.jobs
    app.extensions['ai_service'] = runtime.ai
    if reconciliation_plan:
        from backend.dev_reconciliation import DevReconciliation
        runtime.reconciliation = DevReconciliation(runtime,reconciliation_plan)
    intake = (employee_intake.IntakeService(runtime, microsoft_secret, intake_token, microsoft_oauth)
              if employee_intake.settings(config) else None)
    app.extensions['employee_intake'] = intake
    runtime.intake = intake
    tutorial = Onboarding(runtime)
    from backend.reporting import Reporting
    reporting = Reporting(runtime)
    app.extensions['reporting'] = reporting

    def requester_service():
        if intake is None:
            raise WriteError('Employee intake is awaiting Microsoft and integration setup.', 503)
        return intake

    @app.before_request
    def guards():
        # The origin is pinned; forwarded headers are never trusted for auth or redirects.
        if request.host.split(':')[0].lower() not in (config.host,'127.0.0.1','localhost'):
            raise WriteError('Unrecognized pilot host.',403)
        runtime.active_config()
        if request.method not in ('GET','HEAD','POST','PATCH'):
            raise WriteError('This method is disabled. Deletion is unavailable.',405)
        if request.method == 'HEAD' and request.path.startswith('/auth/'):
            raise WriteError('Use the sign-in link in your browser.',405)
        if request.method in ('POST','PATCH'):
            if request.headers.get('Origin') != config.origin:
                raise WriteError('Use the configured HTTPS pilot origin.',403)
            s = (requester_service().session(request.cookies.get(employee_intake.COOKIE))
                 if request.path.startswith('/api/intake/') or request.path == '/auth/microsoft/logout'
                 else runtime.session(request.cookies.get(SESSION_COOKIE)))
            if not equal(request.headers.get('X-Portal-CSRF',''),s.csrf):
                raise WriteError('Refresh the page before saving.',403)

    def request_json(limit=128*1024):
        if request.mimetype != 'application/json':
            raise WriteError('Use an application/json request.', 415)
        if request.content_length is not None and request.content_length > limit:
            raise WriteError('Request JSON exceeds the permitted size.', 413)
        return strict_json(request.stream.read(limit+1), limit, label='Request JSON')

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
          'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",'Permissions-Policy':'camera=(), microphone=(), geolocation=()'})
        return response

    @app.errorhandler(WriteError)
    def write_error(error):
        if request.path.startswith('/api/'):
            if isinstance(error, SaveRefreshError):
                return jsonify(error=str(error), saveConfirmed=True, jobId=error.job_id), error.status
            return jsonify(error=str(error)),error.status
        return login_page(str(error)),error.status

    @app.errorhandler(GatewayError)
    def upstream_error(error):
        try:
            from backend.server import RefreshUnavailable
        except ImportError:
            from server import RefreshUnavailable
        if isinstance(error, RefreshUnavailable):
            return jsonify(error='DEV data is temporarily unavailable or changing. Refresh again shortly; your sign-in has not been reset.'),503
        return jsonify(error='Smartsheet access could not be verified. Reconnect or contact the pilot owner.'),502

    @app.errorhandler(413)
    def oversized(error):
        return jsonify(error='This file or request exceeds the permitted size.'),413

    def signed_in():
        return runtime.session(request.cookies.get(SESSION_COOKIE))

    def login_page(message=''):
        from markupsafe import escape
        employee = ('<h1>How can we help?</h1><p>Request creative work using your organization Microsoft account. Your contact details are filled in for you.</p><a class="button button-primary" href="/auth/microsoft/login">Request creative work</a><hr><h2>Graphics workspace</h2>' if intake else '<h1>Sign in to your workspace.</h1>')
        return Response('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in - Graphics DEV pilot</title><link rel="stylesheet" href="/ornl-design-tokens.css"><link rel="stylesheet" href="/styles.css"></head><body><main class="pilot-login"><div class="eyebrow">Graphics Portal / DEV pilot</div>'+employee+'<p>Designers and coordinators: use the Smartsheet account invited to this pilot.</p>'+('<div class="notice notice-warning">'+str(escape(message))+'</div>' if message else '')+'<a class="button button-primary" href="/auth/smartsheet/login">Continue with Smartsheet</a></main></body></html>',mimetype='text/html')

    @app.get('/auth/microsoft/login')
    def microsoft_login():
        uri, browser = requester_service().begin()
        response = redirect(uri, 303)
        response.set_cookie(employee_intake.LOGIN_COOKIE, browser, max_age=600,
                            secure=True, httponly=True, samesite='Lax', path='/')
        return response

    @app.get(employee_intake.CALLBACK)
    def microsoft_callback():
        service = requester_service()
        sid, session = service.complete(request.args.to_dict(), request.cookies.get(employee_intake.LOGIN_COOKIE, ''))
        service.logout(request.cookies.get(employee_intake.COOKIE))
        response = redirect('/request', 303)
        response.set_cookie(employee_intake.COOKIE, sid, max_age=int(session.expires-time.time()),
                            secure=True, httponly=True, samesite='Lax', path='/')
        response.delete_cookie(employee_intake.LOGIN_COOKIE, secure=True, httponly=True, samesite='Lax', path='/')
        return response

    @app.post('/auth/microsoft/logout')
    def microsoft_logout():
        requester_service().logout(request.cookies.get(employee_intake.COOKIE))
        response = jsonify(ok=True)
        response.delete_cookie(employee_intake.COOKIE, secure=True, httponly=True, samesite='Lax', path='/')
        return response

    @app.get('/request')
    @app.get('/my-requests')
    def requester_page():
        service = requester_service()
        try:
            service.session(request.cookies.get(employee_intake.COOKIE))
        except WriteError as error:
            if error.status == 401:
                return redirect('/auth/microsoft/login', 303)
            raise
        return send_from_directory(WEB, 'intake.html')

    @app.get('/api/intake/session')
    def requester_info():
        return jsonify(requester_service().info(request.cookies.get(employee_intake.COOKIE)))

    @app.post('/api/intake/requests')
    def employee_create():
        return jsonify(requester_service().create(request.cookies.get(employee_intake.COOKIE),
            request.headers.get('Idempotency-Key', ''), request_json()))

    @app.get('/api/intake/requests/<receipt>')
    def employee_receipt(receipt):
        return jsonify(requester_service().receipt(request.cookies.get(employee_intake.COOKIE), receipt))

    @app.get('/api/intake/my-requests')
    def my_requests():
        return jsonify(requester_service().tracking.list(request.cookies.get(employee_intake.COOKIE), offset()))

    @app.get('/api/intake/my-requests/<receipt>')
    def my_request(receipt):
        return jsonify(requester_service().tracking.get(request.cookies.get(employee_intake.COOKIE), receipt))

    @app.get('/api/intake/my-requests/<receipt>/attachments/<attachment>')
    def requester_attachment(receipt,attachment):
        content,mime,name = requester_service().tracking.attachment(request.cookies.get(employee_intake.COOKIE),receipt,attachment)
        response = Response(content,content_type='application/octet-stream')
        response.headers['Content-Disposition'] = "attachment; filename*=UTF-8''"+quote(name,safe='')
        return response

    def tutorial_identity(employee=False):
        if employee:
            actor = requester_service().session(request.cookies.get(employee_intake.COOKIE)).actor
            return 'microsoft:'+actor.key, 'requester', 'requester'
        actor = signed_in().actor
        return 'smartsheet:'+actor.user_id, 'staff', 'coordinator' if actor.role in ('coordinator','admin') else 'designer'

    def tutorial_response(employee=False):
        principal,kind,default = tutorial_identity(employee)
        if request.method=='GET':
            return jsonify(tutorial.read(principal,kind,default))
        if request.content_length is None or request.content_length>4096:
            raise WriteError('The tutorial update is too large.',413)
        return jsonify(tutorial.write(principal,kind,default,request_json(4096)))

    @app.route('/api/onboarding',methods=['GET','POST'])
    def staff_tutorial():
        return tutorial_response()

    @app.route('/api/intake/onboarding',methods=['GET','POST'])
    def employee_tutorial():
        return tutorial_response(True)

    @app.get('/api/v1/jobs/<job>/requester-resources')
    def requester_resources(job):
        return jsonify(requester_service().tracking.staff_resources(request.cookies.get(SESSION_COOKIE),job))

    @app.post('/api/v1/jobs/<job>/requester-resources')
    def share_requester_resource(job):
        if request.content_length is None or request.content_length>4096:
            raise WriteError('The visibility update is too large.',413)
        return jsonify(requester_service().tracking.share(request.cookies.get(SESSION_COOKIE),job,request_json(4096)))

    @app.post('/api/intake/requests/<receipt>/attachments')
    def employee_upload(receipt):
        from urllib.parse import unquote
        return jsonify(requester_service().upload(request.cookies.get(employee_intake.COOKIE),
            request.headers.get('Idempotency-Key', ''), receipt, request.headers.get('X-Project-Revision', ''),
            unquote(request.headers.get('X-Filename', '')), request.mimetype, request.get_data(cache=False)))

    @app.get('/auth/smartsheet/login')
    def login():
        state,browser = runtime.begin_login()
        response = redirect(runtime.oauth.authorize_url(state),303)
        response.set_cookie(LOGIN_COOKIE,browser,max_age=600,secure=True,httponly=True,samesite='Lax',path='/')
        return response

    @app.get(CALLBACK)
    def callback():
        # Never log the callback query, code, state, tokens or provider error text.
        if request.args.get('error'):
            raise WriteError('Smartsheet sign-in was not approved. You can start again.',401)
        state = request.args.get('state','')
        sid,session = runtime.complete_login(state,request.cookies.get(LOGIN_COOKIE,''),request.args.get('code',''))
        if getattr(runtime,'reconciliation',None):runtime.reconciliation.on_login(sid)
        old = request.cookies.get(SESSION_COOKIE)
        if old:
            runtime.logout(old)
        response = redirect('/#/projects' if session.actor.role in ('coordinator','admin') else '/#/my-work',303)
        response.set_cookie(SESSION_COOKIE,sid,max_age=int(session.expires-time.time()),secure=True,httponly=True,samesite='Lax',path='/')
        response.delete_cookie(LOGIN_COOKIE,secure=True,httponly=True,samesite='Lax',path='/')
        return response

    @app.post('/auth/logout')
    def logout():
        runtime.logout(request.cookies.get(SESSION_COOKIE))
        response = jsonify(ok=True)
        response.delete_cookie(SESSION_COOKIE,secure=True,httponly=True,samesite='Lax',path='/')
        return response

    @app.get('/api/session')
    def session_info():
        s = signed_in()
        return jsonify(actor={'id':s.actor.email,'name':s.actor.name,'role':s.actor.role},csrf=s.csrf)

    def browser_workspace(data):
        # CSRF belongs only to the browser adapter, never the shared job service.
        return jsonify({**data, 'csrf': signed_in().csrf})

    @app.post('/api/reports')
    def create_report():
        return jsonify(reporting.snapshot(request.cookies.get(SESSION_COOKIE),request_json(8192)))

    @app.patch('/api/reports/jobs/<job>')
    def reporting_profile(job):
        return jsonify(reporting.profile(request.cookies.get(SESSION_COOKIE),job,request_json(16384)))

    @app.post('/api/reports/<snapshot_id>/export')
    def export_report(snapshot_id):
        content,mime,name=reporting.export(request.cookies.get(SESSION_COOKIE),snapshot_id,request_json(4096))
        response=Response(content,content_type=mime)
        response.headers['Content-Disposition']="attachment; filename*=UTF-8''"+quote(name,safe='')
        return response

    @app.get('/api/v1/capabilities')
    def capabilities():
        return jsonify(runtime.jobs.capabilities(request.cookies.get(SESSION_COOKIE)))

    def ai_body(limit=256*1024):
        if request.mimetype != 'application/json':
            raise WriteError('Use an application/json request.', 415)
        return strict_json(request.stream.read(limit+1), limit)

    def offset():
        try:
            return int(request.args.get('offset','0'))
        except ValueError:
            raise WriteError('Invalid page offset.') from None

    @app.get('/api/v1/jobs/<job>/ai')
    def ai_status(job):
        return jsonify(runtime.ai.status(request.cookies.get(SESSION_COOKIE),job,offset()))

    @app.get('/api/v1/jobs/<job>/reference-inventory')
    def ai_references(job):
        return jsonify(runtime.ai.references(request.cookies.get(SESSION_COOKIE),job,offset()))

    @app.post('/api/v1/jobs/<job>/intake-contexts')
    def ai_prepare(job):
        return jsonify(runtime.ai.prepare(request.cookies.get(SESSION_COOKIE),job,
            request.headers.get('Idempotency-Key',''),ai_body(16384)))

    @app.get('/api/v1/jobs/<job>/intake-contexts/<context>')
    def ai_context(job,context):
        return jsonify(runtime.ai.get_context(request.cookies.get(SESSION_COOKIE),job,context))

    @app.post('/api/v1/jobs/<job>/ai-drafts')
    def ai_draft_import(job):
        return jsonify(runtime.ai.save_draft(request.cookies.get(SESSION_COOKIE),job,
            request.headers.get('Idempotency-Key',''),ai_body()))

    @app.get('/api/v1/jobs/<job>/ai-drafts/<draft>')
    def ai_draft_get(job,draft):
        return jsonify(runtime.ai.get_draft(request.cookies.get(SESSION_COOKIE),job,draft))

    @app.post('/api/v1/jobs/<job>/ai-drafts/<draft>/reviews')
    def ai_review(job,draft):
        return jsonify(runtime.ai.review(request.cookies.get(SESSION_COOKIE),job,draft,
            request.headers.get('Idempotency-Key',''),ai_body(16384)))

    @app.get('/api/v1/deleted-jobs')
    def deleted_jobs():
        return jsonify(runtime.lifecycle.list(request.cookies.get(SESSION_COOKIE)))

    @app.post('/api/v1/jobs/<job>/lifecycle')
    def change_job_lifecycle(job):
        return jsonify(runtime.lifecycle.change(request.cookies.get(SESSION_COOKIE),request.headers.get('Idempotency-Key',''),job,request_json(4096)))

    @app.get('/api/projects')
    def projects():
        sid = request.cookies.get(SESSION_COOKIE)
        return browser_workspace(runtime.jobs.updates(sid, request.args['sinceVersion'])
                                 if 'sinceVersion' in request.args else runtime.jobs.workspace(sid))

    @app.post('/api/projects')
    def create_project():
        return browser_workspace(runtime.jobs.perform(request.cookies.get(SESSION_COOKIE),request.headers.get('Idempotency-Key',''),request_json()))

    @app.patch('/api/projects/<job>')
    def update_project(job):
        return browser_workspace(runtime.jobs.perform(request.cookies.get(SESSION_COOKIE),request.headers.get('Idempotency-Key',''),request_json(),job))

    @app.post('/api/projects/<job>/attachments')
    def upload(job):
        name = request.headers.get('X-Filename','')
        from urllib.parse import unquote
        return browser_workspace(runtime.jobs.upload(request.cookies.get(SESSION_COOKIE),request.headers.get('Idempotency-Key',''),job,request.headers.get('X-Project-Revision',''),unquote(name),request.mimetype,request.get_data(cache=False)))

    @app.get('/api/projects/<job>/attachments/<attachment>')
    def attachment(job,attachment):
        content,mime,name = runtime.jobs.attachment(request.cookies.get(SESSION_COOKIE),job,attachment)
        mime = media_type(mime)
        download = 'download' in request.args or mime not in {'image/png','image/jpeg','image/webp','text/plain'}
        response = Response(content,content_type='application/octet-stream' if download else mime)
        response.headers['Content-Disposition'] = ('attachment' if download else 'inline')+"; filename*=UTF-8''"+quote(name,safe='')
        return response

    @app.get('/runtime-config.js')
    def runtime_config():
        # Anonymous configuration contains neither credentials nor the invite list.
        return Response('window.PORTAL_CONFIG=Object.freeze('+json.dumps({'dataMode':'pilot','apiBase':'/api'})+');',mimetype='text/javascript')

    @app.get('/')
    def home():
        try:
            signed_in()
        except WriteError as error:
            if intake:
                try:
                    intake.session(request.cookies.get(employee_intake.COOKIE))
                    return redirect('/request', 303)
                except WriteError:
                    pass
            return login_page('' if error.status==401 else str(error))
        response = send_from_directory(WEB,'index.html')
        return response

    @app.get('/<path:asset>')
    def static_asset(asset):
        allowed = {'organization-fields.js','assignment-panel.js','app.js','domain.js','demo-data.js','runtime-config.js','styles.css','ornl-design-tokens.css','intake.js','ai-panel.js', 'search-select.js', 'workspace-sync.js','http-client.js','reports.js','lifecycle.js','tutorial.js','tutorial-content.js','requester.js'}
        if asset not in allowed and not asset.startswith(('assets/fonts/','assets/favicon.')):
            raise WriteError('Not found.',404)
        return send_from_directory(WEB,asset)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='.local/pilot-config.json')
    parser.add_argument('--port',type=int,default=4175)
    parser.add_argument('--reconciliation-plan',help='Private, expiring, owner-bound one-shot DEV maintenance plan; never exposed through an API.')
    parser.add_argument('--secret-source', choices=('keychain', 'prompt'),
                        default='keychain' if sys.platform == 'darwin' else 'prompt')
    args = parser.parse_args()
    check_port_available(args.port)
    path = Path(args.config).resolve()
    client_id = client_id_from_config(path)
    def load():
        value = json.loads(path.read_text())
        value['clientId'] = value.get('clientId') or client_id
        return PilotConfig(value)
    config = load()
    if employee_intake.settings(config):
        import ssl
        if sys.version_info < (3, 10) or not ssl.OPENSSL_VERSION.startswith('OpenSSL '):
            raise WriteError('Microsoft intake requires Python 3.10+ with OpenSSL. Prepare the supported pilot environment before entering secrets; Python 3.12 is recommended.', 503)
    secret = load_secret(client_id, args.secret_source)
    microsoft_secret = intake_token = None
    if employee_intake.settings(config):
        for label in ('Microsoft intake app secret', 'Approved intake integration Smartsheet token'):
            value = ''
            while not value.strip():
                value = getpass.getpass(label + ' (hidden; memory only): ')
            if microsoft_secret is None:
                microsoft_secret = value.strip()
            else:
                intake_token = value.strip()
    app = create_app(config,secret,reload_config=load,
                     microsoft_secret=microsoft_secret,intake_token=intake_token,reconciliation_plan=args.reconciliation_plan)
    from waitress import serve
    print('Authenticated pilot ready behind '+config.origin,flush=True)
    print('Loopback backend: http://127.0.0.1:'+str(args.port),flush=True)
    print('Keep this Terminal and the tunnel Terminal open. Ctrl+C stops this server.',flush=True)
    print('Pilot expires: '+datetime.fromtimestamp(config.expires).astimezone().isoformat(),flush=True)
    if not config.writes or not config.workflow_review_valid():
        print('DEV saves are paused until the configured write gate and native workflow review are valid.',flush=True)
    print('Designer sessions have no API-token fallback. OAuth tokens expire with the in-memory session.',flush=True)
    # Only this process owns the per-sheet lock. Start one pilot process, not replicas.
    serve(app,host='127.0.0.1',port=args.port,threads=6,connection_limit=40,channel_timeout=60,max_request_body_size=MAX_FILE_BYTES,clear_untrusted_proxy_headers=True)


if __name__=='__main__':
    try:main()
    except (WriteError,GatewayError,FileNotFoundError,ValueError,CredentialError) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
