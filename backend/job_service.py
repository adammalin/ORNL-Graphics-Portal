"""Transport-independent pilot job operations.

The service resolves private session handles itself. It does not accept actors,
bearer tokens, arbitrary source IDs or model-selected permissions. Future MCP
and agent authorization adapters are intentionally not enabled in Stage 0.
"""
from dataclasses import dataclass, field
from contextlib import contextmanager
import copy
import hashlib
import json
import re
import time
from datetime import datetime, timezone

try:
    from backend.dev_store import DevStore, WriteError, SaveRefreshError, allowed_stages
    from backend.principals import Principal
    from backend.server import GatewayError, MAX_FILE_BYTES
except ImportError:
    from dev_store import DevStore, WriteError, SaveRefreshError, allowed_stages
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
        self._self_contact = {'id':actor.email,'name':actor.name,
                              'initials':''.join(p[:1] for p in actor.name.split()[:2]),'capacity':None}
        self._assignment_actor={'id':actor.user_id,'name':actor.name,'email':actor.email}
        self._write_guard = None
        self._routing_version = None
        self._admin_rows = frozenset()
        super().__init__(reader, path)

    def metadata(self):
        data = super().metadata()
        invites = self.runtime.active_config().invites
        directory = {p['id']: p for p in data['designers']}
        directory[self._self_contact['id']] = self._self_contact
        for email in invites:
            directory.setdefault(email, {
                'id': email, 'name': email, 'initials': email[:2].upper(),
                'capacity': None,
            })
        data['designers'] = [d for email, d in directory.items()
                             if email in invites or email in self.identities or any(
                                 p.get('readOnly') and p.get('requestedDesigner') == email
                                 for p in self.reader._cache['projects'])]
        return data

    def require_writes(self):
        config = self.runtime.active_config()
        if not config.writes:
            raise WriteError('Writes are disabled for this pilot.', 403)
        if not config.workflow_review_valid():
            raise WriteError('The native workflow review is missing or expired. Pilot writes are paused.', 403)

    def organization_policy(self):
        return self.runtime.active_config().organization_routing

    def assignment_actor(self):
        return self._assignment_actor

    def validate_source(self, *, source_current=False):
        self.require_writes()
        return super().validate_source(source_current=source_current)

    @contextmanager
    def authorized_writes(self, guard, admin_rows=()):
        # JobService holds the shared sheet lock for the whole operation.
        if self._write_guard is not None:
            raise WriteError('A save is already in progress.', 409)
        self._write_guard = guard
        self._routing_version = json.dumps(self.organization_policy(), sort_keys=True)
        self._admin_rows = frozenset(admin_rows)
        try:
            yield
        finally:
            self._write_guard = None
            self._routing_version = None
            self._admin_rows = frozenset()

    def permits_admin_row(self,row_id):
        return self._write_guard is not None and row_id in self._admin_rows and row_id in self.runtime.active_config().copied_row_ids

    def _write(self, *args, **kwargs):
        if self._write_guard is None:
            raise WriteError('Use the authenticated job service to save.', 403)
        if self._routing_version != json.dumps(self.organization_policy(), sort_keys=True):
            raise WriteError('Organization routing changed during this request. Refresh and review before saving.', 409)
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
        context.reader.copied_row_ids = self.runtime.active_config().copied_row_ids
        context.reader.projects(force=True)
        # Reads can outlast an expiry or invite update. Revalidate before use.
        return self._resolve(session_id)

    def _ensure_current(self, session_id, context):
        current = self._resolve(session_id)
        if current.reader.copied_row_ids != self.runtime.active_config().copied_row_ids:
            raise WriteError('The approved project selection changed. Refresh before continuing.',409)
        if current.principal != context.principal or current.reader is not context.reader:
            raise WriteError('Your authorization changed. Refresh before continuing.', 403)
        return current

    def _creator(self, job, principal, row_id):
        with self.runtime.db() as db:
            # Acknowledged creates may initially lack the generated job number.
            # Bind it once, only from an allowed native row and its original owner.
            owned=db.execute('SELECT job_id FROM job_ownership WHERE sheet_id=? AND row_id=? AND user_id=?',
                (self.runtime.config.sheet_id,row_id,principal.user_id)).fetchone()
            if owned and owned[0]=='':
                db.execute('UPDATE job_ownership SET job_id=? WHERE sheet_id=? AND row_id=? AND job_id=? AND user_id=?',
                    (job,self.runtime.config.sheet_id,row_id,'',principal.user_id))
            return bool(owned and owned[0] in ('',job))

    def _can_read(self, principal, project):
        return (principal.can_coordinate
                or project.get('requestedDesigner') in principal.identities
                or self._creator(project['id'], principal, project['_rowId']))

    def _writable(self, context):
        config = self.runtime.active_config()
        return bool(config.writes and config.workflow_review_valid()
                    and context.reader.sheet.get('accessLevel') in WRITABLE_ACCESS)

    def _permissions(self, context, project):
        lifecycle=self.runtime.lifecycle.state(context.reader.sheet_id,project['_rowId'])
        manage=self.runtime.lifecycle.can_manage(context,project)
        recovery={'delete':manage and lifecycle['state']=='active','restore':manage and lifecycle['state']=='deleted'}
        if lifecycle['state']=='deleted' or ((project.get('readOnly') or project.get('synthetic') is not True) and not context.principal.is_admin):
            return {'edit': False, 'respond': False, 'offer': False, **recovery}
        principal = context.principal
        writable = self._writable(context)
        own = project.get('requestedDesigner') in principal.identities
        accepted = own and project.get('response') == 'accepted'
        creator_new = project.get('stage') == 'New' and self._creator(project['id'], principal, project['_rowId'])
        return {
            **recovery,
            'edit': bool(writable and (principal.can_coordinate or accepted or creator_new)),
            'respond': bool(writable and own and project.get('stage') == 'Assigned'
                            and project.get('response') not in ('accepted', 'declined')),
            'offer': bool(writable and principal.can_coordinate
                          and project.get('response') != 'accepted'
                          and project.get('stage') not in ('Completed', 'Archived')),
        }

    def _action_allowed(self, context, project, action, permissions=None):
        permissions=self._permissions(context,project) if permissions is None else permissions
        active=project['stage'] not in ('Completed','Archived')
        if action=='reassign':
            return bool(permissions['edit'] and context.principal.can_coordinate and active and project['response']=='accepted')
        if action=='claim':
            return bool(permissions['edit'] and project['stage']=='New' and project['response']!='accepted'
                        and (not project['requestedDesigner'] or project['response']=='declined'))
        return (permissions['respond'] if action in ('accept','decline') else permissions['offer'] if action=='offer'
                else permissions['edit'] if action in ('edit','stage','upload') else False)

    def _project(self, context, job_id, include_deleted=False):
        project = next((p for p in context.reader._cache['projects'] if p['id'] == job_id), None)
        if not project or not self._can_read(context.principal, project):
            raise WriteError('This project is not available to your account.', 404)
        if not include_deleted and self.runtime.lifecycle.is_deleted(context.reader.sheet_id,project['_rowId']):
            raise WriteError('This job is in the recoverable Deleted area.',410)
        return project

    def _project_dto(self, context, project):
        output = copy.deepcopy({key: value for key, value in project.items() if key != '_rowId'})
        output['permissions'] = self._permissions(context, project)
        output['allowedStages']=allowed_stages(project)
        output['assignmentActions']={action:self._action_allowed(context,project,action,output['permissions']) for action in ('claim','reassign')}
        output['assignment']=context.reader.store.assignment_details(project)
        output['lifecycleVersion'] = self.runtime.lifecycle.state(context.reader.sheet_id,project['_rowId'])['version']
        output['requesterTrackable'] = False
        if getattr(self.runtime,'intake',None) and (self.runtime.active_config().value.get('microsoftIntake') or {}).get('enabled'):
            with self.runtime.db() as db:
                output['requesterTrackable'] = bool(db.execute('SELECT 1 FROM employee_intake_receipts r '
                    'JOIN employee_request_snapshots s ON s.receipt=r.receipt WHERE r.sheet=? AND r.job=? AND s.row_id=?',
                    (context.reader.sheet_id,project['id'],project['_rowId'])).fetchone()) and not project.get('readOnly')
        if output.get('requestedDesigner') in context.principal.identities:
            output['requestedDesigner'] = context.principal.email
        return output

    def _before_write(self, session_id, context, job_id=None, action=None):
        current = self._ensure_current(session_id, context)
        current.reader.store.require_writes()
        if current.reader.sheet.get('accessLevel') not in WRITABLE_ACCESS:
            raise WriteError('Your Smartsheet account cannot edit this sheet.', 403)
        if job_id:
            allowed = self._action_allowed(current,self._project(current,job_id),action)
            if not allowed:
                raise WriteError('Your account cannot perform this action on this job.', 403)

    def _workspace(self, context, raw):
        principal = context.principal
        config = self.runtime.active_config()
        raw={**raw,'projects':[p for p in raw['projects'] if not self.runtime.lifecycle.is_deleted(context.reader.sheet_id,p['_rowId'])]}
        context.reader._portal_policy = self._policy_version(context)
        projects = [self._project_dto(context, p) for p in raw['projects']
                    if self._can_read(principal, p)]
        visible_copied_designers = {p.get('requestedDesigner') for p in projects if p.get('readOnly')}
        directory = [d for d in raw.get('designers', [])
                     if d['id'] in config.invites or d['id'] in principal.identities
                     or d['id'] in visible_copied_designers]
        directory = list({
            (principal.email if d['id'] in principal.identities else d['id']):
            ({**d, 'id': principal.email, 'name': principal.name}
             if d['id'] in principal.identities else d)
            for d in directory
        }.values())
        directory = [{**d, 'canReceiveOffer': d['id'] in config.invites} for d in directory]
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
                'offers': len([p for p in own if not p.get('readOnly') and p.get('response') not in ('accepted', 'declined')]),
            })
        writable = self._writable(context)
        return {
            'mode': 'dev-write' if writable else 'dev-readonly',
            'projects': projects, 'designers': directory,
            'sourceVersion': context.reader.version,
            'departmentOptions': raw.get('departmentOptions', []),
            'organizationOptions': raw.get('organizationOptions', {}),
            'capabilities': self._capabilities(context),
            'taskTypes': raw.get('taskTypes', []),
            'taskTypeMultiple': raw.get('taskTypeMultiple', False),
            'priorities': raw.get('priorities', []), 'teamWorkload': counts,
            'actor': principal.public_identity(), 'canCreate': writable,
            'accessLevel': context.reader.sheet.get('accessLevel', 'VIEWER'),
        }

    def _policy_version(self,context):
        config=self.runtime.active_config()
        return (context.principal,tuple(sorted(config.invites.items())),config.writes,config.workflow_review_valid(),json.dumps(config.organization_routing, sort_keys=True),self.runtime.lifecycle.epoch())

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

    def _capabilities(self, context):
        return {
            'schemaVersion': '1.0',
            'requesterTrackingAvailable': bool(getattr(self.runtime,'intake',None)
                and (self.runtime.active_config().value.get('microsoftIntake') or {}).get('enabled')),
            'actor': context.principal.public_identity(),
            'canCreate': self._writable(context),
            'accessLevel': context.reader.sheet.get('accessLevel', 'VIEWER'),
            'jobActionsAreScoped': True,
            'features': {**{name: False for name in FEATURE_NAMES},
                         **self.runtime.ai.flags()},
            'limits': {'attachmentBytes': MAX_FILE_BYTES},
            'constraints': {'deletion': False, 'recoverableDeletion': True, 'sharedTokenFallback': False},
            }

    def capabilities(self, session_id):
        with self.runtime.sheet_lock:
            context = self._fresh(session_id)
            result = self._capabilities(context)
            self._ensure_current(session_id, context)
            return result

    def updates(self, session_id, version):
        """A version check is a hint only; source writes always do a full fresh read."""
        if not isinstance(version, str) or not re.fullmatch(r'\d{1,20}', version):
            raise WriteError('Choose a valid workspace version.')
        with self.runtime.sheet_lock:
            context = self._resolve(session_id)
            reader = context.reader
            config = self.runtime.active_config()
            current = reader._get_json(f'/sheets/{reader.sheet_id}/version', 'dev-version-check').get('version')
            if type(current) is not int or current < 0:
                raise GatewayError('Smartsheet returned an invalid workspace version.')
            unchanged = (str(current) == version and current == reader.version
                         and reader.copied_row_ids == config.copied_row_ids
                         and time.monotonic() - reader._cache_time < 60
                         and getattr(reader,'_portal_policy',None)==self._policy_version(context))
            if unchanged:
                result = {'unchanged': True, 'sourceVersion': current}
            else:
                context = self._fresh(session_id)
                result = self._workspace(context, context.reader._cache)
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
            self_assign_to = None
            if job_id:
                project = self._project(context, job_id)
                if project.get('readOnly') and not principal.is_admin:
                    raise WriteError('Copied DEV projects are read-only. Use a test record to make changes.', 403)
                permissions = self._permissions(context, project)
                with reader.store.db() as db:
                    replay = db.execute(
                        'SELECT 1 FROM operations WHERE sheet=? AND key=?',
                        (reader.sheet_id, key)).fetchone()
                if not replay:
                    action = body.get('action') if isinstance(body, dict) else None
                    allowed = self._action_allowed(context,project,action)
                    if not allowed:
                        raise WriteError('Your account cannot perform this action on this job.', 403)
                    if (action == 'edit' and isinstance(body.get('fields'), dict)
                            and set(body['fields']) & {'directorate', 'division'} and not principal.can_coordinate):
                        raise WriteError('Only coordinators and admins can change routing organization fields.', 403)
                    if action in ('offer','reassign') and body.get('designer') not in self.runtime.active_config().invites:
                        raise WriteError('Offer jobs only to invited pilot users.', 403)
                if isinstance(body,dict) and body.get('action')=='claim':
                    self_assign_to=principal.email
            else:
                if (not isinstance(body, dict) or set(body)-{'fields','assignToMe'}
                        or not isinstance(body.get('fields'), dict)
                        or type(body.get('assignToMe',False)) is not bool):
                    raise WriteError('Invalid intake fields.')
                # Acceptance can only be recorded for the authenticated creator,
                # never for a caller-supplied designer or an existing job.
                self_assign_to = principal.email if body.get('assignToMe',False) else None
                body = {'fields': {**body['fields'],
                        'email': principal.email, 'requestor': principal.name}}
            try:
                # Do not use an authorization snapshot after queued work expires.
                action = body.get('action') if isinstance(body, dict) else None
                with reader.store.authorized_writes(
                        lambda: self._before_write(session_id, context, job_id, action),
                        admin_rows={project['_rowId']} if job_id and principal.is_admin else ()):
                    result = reader.store.perform(key, body, job_id, source_current=True,
                                                  self_assign_to=self_assign_to)
                saved_job = result['jobId']
                if job_id is None:
                    saved=next((p for p in result['projects'] if p['id']==saved_job),None)
                    if not saved or not result.get('createdRowId') or result['createdRowId']!=saved['_rowId']:
                        raise WriteError('The original creation row cannot be verified. Ask an admin to reconcile this request.',409)
                    with self.runtime.db() as db:
                        db.execute('INSERT OR IGNORE INTO creators VALUES (?,?,?)',
                                   (reader.sheet_id, saved_job, principal.user_id))
                        db.execute('INSERT OR IGNORE INTO job_ownership VALUES (?,?,?,?,?)',
                            (reader.sheet_id,saved['_rowId'],saved_job,principal.user_id,datetime.now(timezone.utc).isoformat()))
                self.runtime.audit(principal, 'create-self-assigned' if self_assign_to and job_id is None else body.get('action', 'create'), saved_job, 'success')
                context = self._resolve(session_id)
                return {**self._workspace(context, result), 'jobId': saved_job}
            except SaveRefreshError as error:
                if job_id is None and error.created_row_id:
                    # Preserve creator rights from the acknowledged native row,
                    # even when later workspace reads are temporarily unavailable.
                    with self.runtime.db() as db:
                        if error.job_id:
                            db.execute('INSERT OR IGNORE INTO creators VALUES (?,?,?)',
                                (reader.sheet_id, error.job_id, principal.user_id))
                        db.execute('INSERT OR IGNORE INTO job_ownership VALUES (?,?,?,?,?)',
                            (reader.sheet_id,error.created_row_id,error.job_id or '',principal.user_id,datetime.now(timezone.utc).isoformat()))
                self.runtime.audit(principal, body.get('action', 'create'), error.job_id or job_id or '', 'saved-refresh-pending')
                raise
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
                    lambda: self._before_write(session_id, context, job_id, 'upload'),
                    admin_rows={project['_rowId']} if context.principal.is_admin else ()):
                result = context.reader.store.upload(key, job_id, expected, name, mime, content)
            self.runtime.audit(context.principal, 'upload', job_id, 'success')
            return self._workspace(self._resolve(session_id), result)

    def attachment(self, session_id, job_id, attachment_id):
        with self.runtime.sheet_lock:
            context = self._fresh(session_id)
            self._project(context, job_id)
            result = context.reader.attachment(job_id, attachment_id)
            # Recheck private deletion as well as source/session authority after download.
            self._project(context,job_id)
            self._ensure_current(session_id, context)
            return result
