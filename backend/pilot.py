"""Invited-user Smartsheet OAuth pilot. No shared-token fallback or delete API.

Use the local editor separately. This service binds only to loopback; its configured
HTTPS origin is supplied by an authenticated development tunnel. Tokens and sessions
live only in memory. The public Pages build never enables this mode.
"""
import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, quote
from urllib.request import Request, build_opener

from flask import Flask, Response, jsonify, redirect, request, send_from_directory

try:
    from backend.server import SmartsheetReader, GatewayError, NoRedirect, WEB, MAX_FILE_BYTES
    from backend.dev_store import DevStore, WriteError
except ImportError:
    from server import SmartsheetReader, GatewayError, NoRedirect, WEB, MAX_FILE_BYTES
    from dev_store import DevStore, WriteError

SESSION_COOKIE = '__Host-graphics_pilot'
LOGIN_COOKIE = '__Host-graphics_login'
CALLBACK = '/auth/smartsheet/callback'
WRITABLE_ACCESS = {'OWNER', 'ADMIN', 'EDITOR', 'EDITOR_SHARE'}
EMAIL = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')
KEY = re.compile(r'[A-Za-z0-9_-]{16,100}')


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
        if not self.sheet_id.isdigit() or not self.filter_id.isdigit():
            raise WriteError('The approved DEV sheet and filter must be configured.', 503)
        self.expires = utc_time(value.get('expiresAt', ''))
        if not time.time() < self.expires <= time.time() + 7 * 86400 + 60:
            raise WriteError('The pilot must expire within seven days.', 503)
        self.invites = {}
        for item in value.get('invites', []):
            email = str(item.get('email', '')).strip().lower()
            role = item.get('role', 'designer')
            if not EMAIL.fullmatch(email) or role not in ('designer', 'coordinator') or email in self.invites:
                raise WriteError('Each invite needs a unique email and designer/coordinator role.', 503)
            self.invites[email] = role
        if not self.invites or len(self.invites) > 20:
            raise WriteError('Configure between one and twenty named pilot invites.', 503)
        self.path = Path(value.get('statePath', Path(__file__).resolve().parents[1] / '.local/pilot-state.sqlite3'))
        self.writes = value.get('writesEnabled') is True

    def available(self):
        if time.time() >= self.expires:
            raise WriteError('This pilot has expired. Contact the pilot owner.', 403)

    def workflow_review_valid(self):
        review = self.value.get('workflowReview') or {}
        if review.get('allNativeWorkflowsChecked') is not True:
            return False
        try:
            reviewed = utc_time(review.get('reviewedAt', ''))
        except WriteError:
            return False
        return 0 <= time.time() - reviewed < 24 * 3600


@dataclass
class Actor:
    user_id: str
    email: str
    name: str
    identities: frozenset
    invite_email: str
    role: str


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

    def creator(self, job, actor):
        with self.db() as db:
            return bool(db.execute('SELECT 1 FROM creators WHERE sheet=? AND job=? AND user_id=?', (self.config.sheet_id, job, actor.user_id)).fetchone())

    def can_read(self, actor, p):
        return actor.role == 'coordinator' or p.get('requestedDesigner') in actor.identities or self.creator(p['id'], actor)

    def permissions(self, session, p):
        a = session.actor
        writable = self.active_config().writes and self.active_config().workflow_review_valid() and session.reader.sheet.get('accessLevel') in WRITABLE_ACCESS
        own_accepted = p.get('requestedDesigner') in a.identities and p.get('response') == 'accepted'
        creator_new = p.get('stage') == 'New' and self.creator(p['id'], a)
        return {'edit': bool(writable and (a.role == 'coordinator' or own_accepted or creator_new)),
                'respond': bool(writable and p.get('requestedDesigner') in a.identities and p.get('stage') == 'Assigned' and p.get('response') not in ('accepted', 'declined')),
                'offer': bool(writable and a.role == 'coordinator' and p.get('response') != 'accepted' and p.get('stage') not in ('Completed', 'Archived'))}

    def project_data(self, session, raw=None):
        config, a = self.active_config(), session.actor
        raw = raw or session.reader.projects(force=True)
        projects = []
        for project in raw['projects']:
            if self.can_read(a, project):
                project = {k:v for k,v in project.items() if k != '_rowId'}
                project['permissions'] = self.permissions(session, project)
                # Canonicalize only the response DTO, never the native contact cell.
                if project.get('requestedDesigner') in a.identities:
                    project['requestedDesigner'] = a.email
                projects.append(project)
        directory = list(raw.get('designers', []))
        # Never expose uninvited directory entries in the pilot payload.
        directory = [d for d in directory if d['id'] in config.invites or d['id'] in a.identities]
        directory = list({(a.email if d['id'] in a.identities else d['id']):
                         ({**d,'id':a.email,'name':a.name} if d['id'] in a.identities else d)
                         for d in directory}.values())
        if not any(d['id'] == a.email for d in directory):
            directory.append({'id':a.email,'name':a.name,'initials':''.join(x[:1] for x in a.name.split()[:2]),'capacity':None})
        counts = []
        for d in directory:
            identities = a.identities if d['id'] == a.email else {d['id']}
            own = [p for p in raw['projects'] if p.get('requestedDesigner') in identities and p.get('stage') not in ('Completed','Archived')]
            accepted = [p for p in own if p.get('response') == 'accepted']
            counts.append({**d,'jobs':len(accepted),'hours':sum(p.get('hours') or 0 for p in accepted),'offers':len([p for p in own if p.get('response') not in ('accepted','declined')])})
        return {'mode':'dev-write' if config.writes and config.workflow_review_valid() and session.reader.sheet.get('accessLevel') in WRITABLE_ACCESS else 'dev-readonly',
                'projects':projects,'designers':directory,'taskTypes':raw.get('taskTypes',[]),'taskTypeMultiple':raw.get('taskTypeMultiple',False),'priorities':raw.get('priorities',[]),
                'teamWorkload':counts,'actor':{'id':a.email,'name':a.name,'role':a.role},'csrf':session.csrf,
                'canCreate':bool(config.writes and config.workflow_review_valid() and session.reader.sheet.get('accessLevel') in WRITABLE_ACCESS),
                'accessLevel':session.reader.sheet.get('accessLevel','VIEWER')}

    def audit(self, actor, action, job, outcome):
        with self.db() as db:
            db.execute('INSERT INTO audit VALUES (?,?,?,?,?,?)', (datetime.now(timezone.utc).isoformat(),actor.user_id,actor.role,action,job,outcome))


class PilotStore(DevStore):
    def __init__(self, reader, path, runtime, actor):
        self.runtime, self.actor = runtime, actor
        super().__init__(reader, path)

    def metadata(self):
        data = super().metadata()
        directory = {p['id']:p for p in data['designers']}
        for email in self.runtime.active_config().invites:
            directory.setdefault(email,{'id':email,'name':email,'initials':email[:2].upper(),'capacity':None})
        data['designers'] = [d for email,d in directory.items() if email in self.runtime.active_config().invites or email in self.actor.identities]
        return data

    def require_writes(self):
        config = self.runtime.active_config()
        if not config.writes:
            raise WriteError('Writes are disabled for this pilot.', 403)
        if not config.workflow_review_valid():
            raise WriteError('The native workflow review is missing or expired. Pilot writes are paused.', 403)

    def validate_source(self):
        self.require_writes()
        return super().validate_source()

    def namespaced_key(self, key):
        if not isinstance(key,str) or not KEY.fullmatch(key):
            raise WriteError('A valid save identifier is required.')
        return hashlib.sha256((self.actor.user_id+':'+key).encode()).hexdigest()

    def perform_for(self, session, key, body, job_id=None):
        self.require_writes()
        with self.reader._lock:
            self.reader.projects(force=True)
            if self.reader.sheet.get('accessLevel') not in WRITABLE_ACCESS:
                raise WriteError('Your Smartsheet account cannot edit this sheet.', 403)
            key = self.namespaced_key(key)
            if job_id:
                p = next((p for p in self.reader._cache['projects'] if p['id']==job_id),None)
                if not p or not self.runtime.can_read(self.actor,p):
                    raise WriteError('This project is not available to your account.',404)
                perms = self.runtime.permissions(session,p)
                with self.db() as db:
                    replay = db.execute('SELECT 1 FROM operations WHERE sheet=? AND key=?',(self.reader.sheet_id,key)).fetchone()
                if not replay:
                    action = body.get('action') if isinstance(body,dict) else None
                    allowed = perms['respond'] if action in ('accept','decline') else perms['offer'] if action=='offer' else perms['edit'] if action in ('edit','stage') else False
                    if not allowed:
                        raise WriteError('Your account cannot perform this action on this job.',403)
                    if action=='offer' and body.get('designer') not in self.runtime.active_config().invites:
                        raise WriteError('Offer jobs only to invited pilot users.',403)
            else:
                if not isinstance(body,dict) or not isinstance(body.get('fields'),dict):
                    raise WriteError('Invalid intake fields.')
                body = {**body,'fields':{**body['fields'],'email':self.actor.email,'requestor':self.actor.name}}
            try:
                result = super().perform(key,body,job_id)
                saved_job = result['jobId']
                if job_id is None:
                    with self.db() as db:
                        db.execute('INSERT OR IGNORE INTO creators VALUES (?,?,?)',(self.reader.sheet_id,saved_job,self.actor.user_id))
                self.runtime.audit(self.actor,body.get('action','create'),saved_job,'success')
                return {**self.runtime.project_data(session,result),'jobId':saved_job}
            except (WriteError,GatewayError):
                self.runtime.audit(self.actor,body.get('action','create'),job_id or '', 'unconfirmed')
                raise

    def upload_for(self, session, key, job_id, expected, name, mime, content):
        self.require_writes()
        with self.reader._lock:
            self.reader.projects(force=True)
            p = next((p for p in self.reader._cache['projects'] if p['id']==job_id),None)
            if not p or not self.runtime.can_read(self.actor,p):
                raise WriteError('This project is not available to your account.',404)
            if not self.runtime.permissions(session,p)['edit']:
                raise WriteError('Your account cannot add references to this project.',403)
            result = super().upload(self.namespaced_key(key),job_id,expected,name,mime,content)
            self.runtime.audit(self.actor,'upload',job_id,'success')
            return self.runtime.project_data(session,result)


def create_app(config, secret, oauth_transport=None, reader_factory=SmartsheetReader, reload_config=None):
    if not secret:
        raise WriteError('Enter the OAuth app secret at the hidden local prompt.',503)
    config = config if isinstance(config,PilotConfig) else PilotConfig(config)
    runtime = PilotRuntime(config,OAuthClient(config.client_id,secret,config.origin,oauth_transport),reader_factory,reload_config)
    app = Flask(__name__,static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=MAX_FILE_BYTES,TRUSTED_HOSTS=[config.host,'127.0.0.1','localhost'])
    app.extensions['pilot'] = runtime

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
            s = runtime.session(request.cookies.get(SESSION_COOKIE))
            if not equal(request.headers.get('X-Portal-CSRF',''),s.csrf):
                raise WriteError('Refresh the page before saving.',403)

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer',
          'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",'Permissions-Policy':'camera=(), microphone=(), geolocation=()'})
        return response

    @app.errorhandler(WriteError)
    def write_error(error):
        if request.path.startswith('/api/'):
            return jsonify(error=str(error)),error.status
        return login_page(str(error)),error.status

    @app.errorhandler(GatewayError)
    def upstream_error(error):
        return jsonify(error='Smartsheet access could not be verified. Reconnect or contact the pilot owner.'),502

    @app.errorhandler(413)
    def oversized(error):
        return jsonify(error='This file or request exceeds the permitted size.'),413

    def signed_in():
        return runtime.session(request.cookies.get(SESSION_COOKIE))

    def login_page(message=''):
        from markupsafe import escape
        return Response('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in - Graphics DEV pilot</title><link rel="stylesheet" href="/ornl-design-tokens.css"><link rel="stylesheet" href="/styles.css"></head><body><main class="pilot-login"><div class="eyebrow">Graphics Portal / invited DEV pilot</div><h1>Sign in to your workspace.</h1><p>Use the Smartsheet account invited to this pilot. Your existing sheet access and pilot role control what you can see and change.</p>'+('<div class="notice notice-warning">'+str(escape(message))+'</div>' if message else '')+'<a class="button button-primary" href="/auth/smartsheet/login">Continue with Smartsheet</a><p class="quiet-note">Smartsheet will request sheet read/write permission. This portal restricts that access to approved synthetic DEV jobs and provides no deletion operations. It is separate from the native dashboards.</p></main></body></html>',mimetype='text/html')

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
        old = request.cookies.get(SESSION_COOKIE)
        if old:
            runtime.logout(old)
        response = redirect('/#/projects' if session.actor.role == 'coordinator' else '/#/my-work',303)
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

    @app.get('/api/projects')
    def projects():
        s = signed_in()
        return jsonify(runtime.project_data(s))

    @app.post('/api/projects')
    def create_project():
        s = signed_in()
        return jsonify(s.reader.store.perform_for(s,request.headers.get('Idempotency-Key',''),request.get_json(silent=True)))

    @app.patch('/api/projects/<job>')
    def update_project(job):
        s = signed_in()
        return jsonify(s.reader.store.perform_for(s,request.headers.get('Idempotency-Key',''),request.get_json(silent=True),job))

    @app.post('/api/projects/<job>/attachments')
    def upload(job):
        s = signed_in()
        name = request.headers.get('X-Filename','')
        from urllib.parse import unquote
        return jsonify(s.reader.store.upload_for(s,request.headers.get('Idempotency-Key',''),job,request.headers.get('X-Project-Revision',''),unquote(name),request.mimetype,request.get_data(cache=False)))

    @app.get('/api/projects/<job>/attachments/<attachment>')
    def attachment(job,attachment):
        s = signed_in()
        with runtime.sheet_lock:
            data = s.reader.projects(force=True)
            p = next((p for p in data['projects'] if p['id']==job),None)
            if not p or not runtime.can_read(s.actor,p):
                raise WriteError('This project is not available to your account.',404)
            content,mime,name = s.reader.attachment(job,attachment)
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
            return login_page('' if error.status==401 else str(error))
        response = send_from_directory(WEB,'index.html')
        return response

    @app.get('/<path:asset>')
    def static_asset(asset):
        allowed = {'app.js','domain.js','demo-data.js','runtime-config.js','styles.css','ornl-design-tokens.css'}
        if asset not in allowed and not asset.startswith(('assets/fonts/','assets/favicon.')):
            raise WriteError('Not found.',404)
        return send_from_directory(WEB,asset)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='.local/pilot-config.json')
    parser.add_argument('--port',type=int,default=4175)
    args = parser.parse_args()
    path = Path(args.config).resolve()
    initial = json.loads(path.read_text())
    client_id = initial.get('clientId') or input('Smartsheet OAuth app client ID: ').strip()
    def load():
        value = json.loads(path.read_text())
        value['clientId'] = value.get('clientId') or client_id
        return PilotConfig(value)
    config = load()
    print('Copy the App secret from Smartsheet, paste it at the next prompt, then press Return.',flush=True)
    print('No characters or dots will appear while you paste/type. Ctrl+C cancels.',flush=True)
    secret = ''
    while not secret.strip():
        secret = getpass.getpass('Smartsheet OAuth app secret (hidden; memory only): ')
        if not secret.strip():
            print('No secret received. Paste the App secret, then press Return. Nothing has started yet.',flush=True)
    app = create_app(config,secret,reload_config=load)
    from waitress import serve
    print('Authenticated pilot ready behind '+config.origin,flush=True)
    print('Loopback backend: http://127.0.0.1:'+str(args.port),flush=True)
    print('No API-token fallback. OAuth tokens expire with the in-memory session.',flush=True)
    # Only this process owns the per-sheet lock. Start one pilot process, not replicas.
    serve(app,host='127.0.0.1',port=args.port,threads=6,connection_limit=40,channel_timeout=60,max_request_body_size=MAX_FILE_BYTES,clear_untrusted_proxy_headers=True)


if __name__=='__main__':
    try:main()
    except (WriteError,GatewayError,FileNotFoundError,ValueError) as error:
        print(str(error),file=sys.stderr);sys.exit(1)
