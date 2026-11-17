"""Transport-independent pilot job operations.

The service resolves private session handles itself. It does not accept actors,
bearer tokens, arbitrary source IDs or model-selected permissions. Future MCP
and agent authorization adapters are intentionally not enabled in Stage 0.
"""
from dataclasses import dataclass, field
from contextlib import contextmanager
import copy
import hashlib
import re

try:
    from backend.dev_store import DevStore, WriteError
    from backend.principals import Principal
    from backend.server import GatewayError, MAX_FILE_BYTES
except ImportError:
    from dev_store import DevStore, WriteError
    from principals import Principal
    from server import GatewayError, MAX_FILE_BYTES


WRITABLE_ACCESS = frozenset({'OWNER', 'ADMIN', 'EDITOR', 'EDITOR_SHARE'})
KEY = re.compile(r'[A-Za-z0-9_-]{16,100}')
FEATURE_NAMES = (
    'aiContext', 'aiDrafts', 'agentApi', 'mcp', 'businessFieldApply',
    'nativePublication', 'modelRunner', 'unattendedAi', 'nativeAiIntegration',
)


@dataclass(frozen=True)
class _Context:
    principal: Principal
    session: object = field(repr=False)

    @property
    def reader(self):
        return self.session.reader


class PilotStore(DevStore):
    """Native writer configuration only; user/action policy lives in JobService."""
    def __init__(self, reader, path, runtime, actor):
        self.runtime = runtime
        self.identities = frozenset(actor.identities)
        self._write_guard = None
        super().__init__(reader, path)

    def metadata(self):
        data = super().metadata()
        invites = self.runtime.active_config().invites
        directory = {p['id']: p for p in data['designers']}
        for email in invites:
            directory.setdefault(email, {
                'id': email, 'name': email, 'initials': email[:2].upper(),
                'capacity': None,
            })
        data['designers'] = [d for email, d in directory.items()
                             if email in invites or email in self.identities]
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

    @contextmanager
    def authorized_writes(self, guard):
        # JobService holds the shared sheet lock for the whole operation.
        if self._write_guard is not None:
            raise WriteError('A save is already in progress.', 409)
        self._write_guard = guard
        try:
            yield
        finally:
            self._write_guard = None

    def _write(self, *args, **kwargs):
        if self._write_guard is None:
            raise WriteError('Use the authenticated job service to save.', 403)
        self._write_guard()
        return super()._write(*args, **kwargs)


class JobService:
    def __init__(self, runtime):
        self.runtime = runtime

    def _resolve(self, session_id):
        if not isinstance(session_id, str) or not session_id:
            raise WriteError('Sign in to Smartsheet to open the pilot.', 401)
        session = self.runtime.session(session_id)
        return _Context(Principal.from_session(session), session)

    def _fresh(self, session_id):
        context = self._resolve(session_id)
        context.reader.projects(force=True)
        # Reads can outlast an expiry or invite update. Revalidate before use.
        return self._resolve(session_id)

    def _ensure_current(self, session_id, context):
        current = self._resolve(session_id)
        if current.principal != context.principal or current.reader is not context.reader:
            raise WriteError('Your authorization changed. Refresh before continuing.', 403)
        return current

    def _creator(self, job, principal):
        with self.runtime.db() as db:
            return bool(db.execute(
                'SELECT 1 FROM creators WHERE sheet=? AND job=? AND user_id=?',
                (self.runtime.config.sheet_id, job, principal.user_id)).fetchone())

    def _can_read(self, principal, project):
        return (principal.role == 'coordinator'
                or project.get('requestedDesigner') in principal.identities
                or self._creator(project['id'], principal))

    def _writable(self, context):
        config = self.runtime.active_config()
        return bool(config.writes and config.workflow_review_valid()
                    and context.reader.sheet.get('accessLevel') in WRITABLE_ACCESS)

    def _permissions(self, context, project):
        principal = context.principal
        writable = self._writable(context)
        own = project.get('requestedDesigner') in principal.identities
        accepted = own and project.get('response') == 'accepted'
        creator_new = project.get('stage') == 'New' and self._creator(project['id'], principal)
        return {
            'edit': bool(writable and (principal.role == 'coordinator' or accepted or creator_new)),
            'respond': bool(writable and own and project.get('stage') == 'Assigned'
                            and project.get('response') not in ('accepted', 'declined')),
            'offer': bool(writable and principal.role == 'coordinator'
                          and project.get('response') != 'accepted'
                          and project.get('stage') not in ('Completed', 'Archived')),
        }

    def _project(self, context, job_id):
        project = next((p for p in context.reader._cache['projects'] if p['id'] == job_id), None)
        if not project or not self._can_read(context.principal, project):
            raise WriteError('This project is not available to your account.', 404)
        return project

    def _project_dto(self, context, project):
        output = copy.deepcopy({key: value for key, value in project.items() if key != '_rowId'})
        output['permissions'] = self._permissions(context, project)
        if output.get('requestedDesigner') in context.principal.identities:
            output['requestedDesigner'] = context.principal.email
        return output

    def _before_write(self, session_id, context, job_id=None, action=None):
        current = self._ensure_current(session_id, context)
        current.reader.store.require_writes()
        if current.reader.sheet.get('accessLevel') not in WRITABLE_ACCESS:
            raise WriteError('Your Smartsheet account cannot edit this sheet.', 403)
        if job_id:
            permissions = self._permissions(current, self._project(current, job_id))
            allowed = (permissions['respond'] if action in ('accept', 'decline')
                       else permissions['offer'] if action == 'offer'
                       else permissions['edit'] if action in ('edit', 'stage', 'upload')
                       else False)
            if not allowed:
                raise WriteError('Your account cannot perform this action on this job.', 403)

    def _workspace(self, context, raw):
        principal = context.principal
        config = self.runtime.active_config()
        projects = [self._project_dto(context, p) for p in raw['projects']
                    if self._can_read(principal, p)]
        directory = [d for d in raw.get('designers', [])
                     if d['id'] in config.invites or d['id'] in principal.identities]
        directory = list({
            (principal.email if d['id'] in principal.identities else d['id']):
            ({**d, 'id': principal.email, 'name': principal.name}
             if d['id'] in principal.identities else d)
            for d in directory
        }.values())
        if not any(d['id'] == principal.email for d in directory):
            directory.append({
                'id': principal.email, 'name': principal.name,
                'initials': ''.join(x[:1] for x in principal.name.split()[:2]),
                'capacity': None,
            })
        counts = []
        for designer in directory:
            identities = principal.identities if designer['id'] == principal.email else {designer['id']}
            own = [p for p in raw['projects'] if p.get('requestedDesigner') in identities
                   and p.get('stage') not in ('Completed', 'Archived')]
            accepted = [p for p in own if p.get('response') == 'accepted']
            counts.append({
                **designer, 'jobs': len(accepted),
                'hours': sum(p.get('hours') or 0 for p in accepted),
                'offers': len([p for p in own if p.get('response') not in ('accepted', 'declined')]),
            })
        writable = self._writable(context)
        return {
            'mode': 'dev-write' if writable else 'dev-readonly',
            'projects': projects, 'designers': directory,
            'taskTypes': raw.get('taskTypes', []),
            'taskTypeMultiple': raw.get('taskTypeMultiple', False),
            'priorities': raw.get('priorities', []), 'teamWorkload': counts,
            'actor': principal.public_identity(), 'canCreate': writable,
            'accessLevel': context.reader.sheet.get('accessLevel', 'VIEWER'),
        }

    def workspace(self, session_id):
        with self.runtime.sheet_lock:
            context = self._fresh(session_id)
            result = self._workspace(context, context.reader._cache)
            self._ensure_current(session_id, context)
            return result

    def get_job(self, session_id, job_id):
        with self.runtime.sheet_lock:
            context = self._fresh(session_id)
            result = self._project_dto(context, self._project(context, job_id))
            self._ensure_current(session_id, context)
            return result

    def capabilities(self, session_id):
        with self.runtime.sheet_lock:
            context = self._fresh(session_id)
            result = {
                'schemaVersion': '1.0',
                'actor': context.principal.public_identity(),
                'canCreate': self._writable(context),
                'accessLevel': context.reader.sheet.get('accessLevel', 'VIEWER'),
                'jobActionsAreScoped': True,
                'features': {name: False for name in FEATURE_NAMES},
                'limits': {'attachmentBytes': MAX_FILE_BYTES},
                'constraints': {'deletion': False, 'sharedTokenFallback': False},
            }
            self._ensure_current(session_id, context)
            return result

    @staticmethod
    def _key(principal, key):
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise WriteError('A valid save identifier is required.')
        # Preserve existing browser receipts across the Stage 0 refactor.
        return hashlib.sha256((principal.user_id + ':' + key).encode()).hexdigest()

    def perform(self, session_id, key, body, job_id=None):
        with self.runtime.sheet_lock:
            context = self._fresh(session_id)
            reader, principal = context.reader, context.principal
            reader.store.require_writes()
            if reader.sheet.get('accessLevel') not in WRITABLE_ACCESS:
                raise WriteError('Your Smartsheet account cannot edit this sheet.', 403)
            key = self._key(principal, key)
            if job_id:
                project = self._project(context, job_id)
                permissions = self._permissions(context, project)
                with reader.store.db() as db:
                    replay = db.execute(
                        'SELECT 1 FROM operations WHERE sheet=? AND key=?',
                        (reader.sheet_id, key)).fetchone()
                if not replay:
                    action = body.get('action') if isinstance(body, dict) else None
                    allowed = (permissions['respond'] if action in ('accept', 'decline')
                               else permissions['offer'] if action == 'offer'
                               else permissions['edit'] if action in ('edit', 'stage')
                               else False)
                    if not allowed:
                        raise WriteError('Your account cannot perform this action on this job.', 403)
                    if action == 'offer' and body.get('designer') not in self.runtime.active_config().invites:
                        raise WriteError('Offer jobs only to invited pilot users.', 403)
            else:
                if not isinstance(body, dict) or not isinstance(body.get('fields'), dict):
                    raise WriteError('Invalid intake fields.')
                body = {**body, 'fields': {**body['fields'],
                        'email': principal.email, 'requestor': principal.name}}
            try:
                # Do not use an authorization snapshot after queued work expires.
                action = body.get('action') if isinstance(body, dict) else None
                with reader.store.authorized_writes(
                        lambda: self._before_write(session_id, context, job_id, action)):
                    result = reader.store.perform(key, body, job_id)
                saved_job = result['jobId']
                if job_id is None:
                    with self.runtime.db() as db:
                        db.execute('INSERT OR IGNORE INTO creators VALUES (?,?,?)',
                                   (reader.sheet_id, saved_job, principal.user_id))
                self.runtime.audit(principal, body.get('action', 'create'), saved_job, 'success')
                context = self._resolve(session_id)
                return {**self._workspace(context, result), 'jobId': saved_job}
            except (WriteError, GatewayError):
                self.runtime.audit(principal, body.get('action', 'create'), job_id or '', 'unconfirmed')
                raise

    def upload(self, session_id, key, job_id, expected, name, mime, content):
        with self.runtime.sheet_lock:
            context = self._fresh(session_id)
            context.reader.store.require_writes()
            project = self._project(context, job_id)
            if not self._permissions(context, project)['edit']:
                raise WriteError('Your account cannot add references to this project.', 403)
            key = self._key(context.principal, key)
            with context.reader.store.authorized_writes(
                    lambda: self._before_write(session_id, context, job_id, 'upload')):
                result = context.reader.store.upload(key, job_id, expected, name, mime, content)
            self.runtime.audit(context.principal, 'upload', job_id, 'success')
            return self._workspace(self._resolve(session_id), result)

    def attachment(self, session_id, job_id, attachment_id):
        with self.runtime.sheet_lock:
            context = self._fresh(session_id)
            self._project(context, job_id)
            result = context.reader.attachment(job_id, attachment_id)
            # Do not return file contents after source/session authority has ended.
            self._ensure_current(session_id, context)
            return result
