"""Recoverable portal deletion; never removes a native row, file or audit event."""
from datetime import datetime,timezone
import hashlib
import json
import secrets

from backend.dev_store import WriteError


def now():return datetime.now(timezone.utc).isoformat()


class JobLifecycle:
    def __init__(self,runtime):self.runtime=runtime

    def state(self,sheet,row):
        with self.runtime.db() as db:
            saved=db.execute('SELECT state,version,updated_at FROM job_lifecycle WHERE sheet_id=? AND row_id=?',(sheet,row)).fetchone()
        return {'state':saved[0],'version':saved[1],'updatedAt':saved[2]} if saved else {'state':'active','version':0,'updatedAt':None}

    def is_deleted(self,sheet,row):return self.state(sheet,row)['state']=='deleted'

    def epoch(self):
        with self.runtime.db() as db:return db.execute('SELECT COALESCE(MAX(rowid),0) FROM job_lifecycle_events').fetchone()[0]

    def can_manage(self,context,project):
        config=self.runtime.active_config()
        # No native write occurs, so native-automation review age does not gate this
        # private reversible action. Global pause and native edit access still apply.
        return bool(config.writes and context.reader.sheet.get('accessLevel') in ('OWNER','ADMIN','EDITOR','EDITOR_SHARE')
            and (context.principal.is_admin or (not project.get('readOnly') and
                self.runtime.jobs._creator(project['id'],context.principal,project['_rowId']))))

    def list(self,sid):
        with self.runtime.sheet_lock:
            context=self.runtime.jobs._fresh(sid);result=[]
            for project in context.reader._cache['projects']:
                state=self.state(context.reader.sheet_id,project['_rowId'])
                if state['state']!='deleted':continue
                owner=self.runtime.jobs._creator(project['id'],context.principal,project['_rowId'])
                if not context.principal.is_admin and not owner:continue
                result.append({'id':project['id'],'title':project['title'],'stage':project['stage'],
                    'sourceRevision':project['revision'],'lifecycleVersion':state['version'],'deletedAt':state['updatedAt'],
                    'canRestore':self.can_manage(context,project)})
            self.runtime.jobs._ensure_current(sid,context)
            return {'jobs':sorted(result,key=lambda p:(p['deletedAt'],p['id']),reverse=True),'recoverableOnly':True}

    def change(self,sid,key,job,body):
        if not isinstance(body,dict) or set(body)!={'action','revision','version','confirmation','reason'}:
            raise WriteError('Use the available delete or restore action.')
        action=body['action']
        if action not in ('delete','restore') or type(body['version']) is not int or body['version']<0:
            raise WriteError('Choose a valid action and refresh the job.')
        if body['confirmation']!=job:raise WriteError('Type the exact job number to confirm.')
        if not isinstance(body['reason'],str) or len(body['reason'])>500 or any(ord(c)<32 for c in body['reason']):
            raise WriteError('The optional reason must fit within 500 characters on one line.')
        payload_hash=hashlib.sha256(json.dumps([job,body],sort_keys=True).encode()).hexdigest()
        with self.runtime.sheet_lock:
            context=self.runtime.jobs._fresh(sid)
            project=self.runtime.jobs._project(context,job,include_deleted=True)
            if not self.can_manage(context,project):
                self.runtime.audit(context.principal,'portal-'+action,job,'denied')
                raise WriteError('Only an admin or the verified creator can delete or restore this job.',403)
            operation=self.runtime.jobs._key(context.principal,key)
            with self.runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                saved=db.execute('SELECT state,version FROM job_lifecycle WHERE sheet_id=? AND row_id=?',(context.reader.sheet_id,project['_rowId'])).fetchone()
                state,version=saved if saved else ('active',0)
                prior=db.execute('SELECT payload_hash,result_json FROM job_lifecycle_operations WHERE sheet_id=? AND user_id=? AND operation_key=?',
                    (context.reader.sheet_id,context.principal.user_id,operation)).fetchone()
                self.runtime.jobs._ensure_current(sid,context)
                if prior:
                    if prior[0]!=payload_hash:raise WriteError('This operation key belongs to different content.',409)
                    result=json.loads(prior[1])
                    if result['state']!=state or result['version']!=version:raise WriteError('The job changed after that action. Refresh before continuing.',409)
                    return {**result,'replayed':True}
                if body['revision']!=project['revision'] or body['version']!=version:
                    raise WriteError('The job or its deleted state changed. Refresh and review the latest values.',409)
                target='deleted' if action=='delete' else 'active'
                if state==target:raise WriteError('This job is already in that state. Refresh before continuing.',409)
                at=now();result={'jobId':job,'state':target,'version':version+1}
                db.execute('INSERT INTO job_lifecycle VALUES (?,?,?,?,?,?,?) ON CONFLICT(sheet_id,row_id) DO UPDATE SET '
                    'job_id=excluded.job_id,state=excluded.state,version=excluded.version,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
                    (context.reader.sheet_id,project['_rowId'],job,target,version+1,context.principal.user_id,at))
                db.execute('INSERT INTO job_lifecycle_events VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (secrets.token_urlsafe(24),context.reader.sheet_id,project['_rowId'],job,action,context.principal.user_id,at,
                     project['revision'],body['reason'],context.principal.client_id,context.principal.execution_origin))
                db.execute('INSERT INTO job_lifecycle_operations VALUES (?,?,?,?,?,?)',
                    (context.reader.sheet_id,context.principal.user_id,operation,payload_hash,json.dumps(result),at))
            self.runtime.audit(context.principal,'portal-'+action,job,'success')
            return result
