"""Owner-only customer projection and explicit, hash-bound reference visibility."""
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets

from backend.dev_store import WriteError
from backend.server import display

STAGES = {
    'New': ('submitted','Submitted',0), 'Assigned': ('assigning','Being assigned',1),
    'Accepted': ('accepted','Accepted',2), 'In Progress': ('in_progress','In progress',3),
    'In Review': ('in_review','In review',4), 'Completed': ('completed','Completed',5),
    'Archived': ('completed','Completed',5),
}
ORIGINAL_FIELDS = ('description','deliverables','audience','specifications','requestorGroup',
                   'notes','taskType','dueDate','reference1','reference2')


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return parsed.isoformat() if parsed.tzinfo else None
    except ValueError:
        return None


def now():
    return datetime.now(timezone.utc).isoformat()


class RequestTracking:
    def __init__(self, intake):
        self.intake, self.runtime = intake, intake.runtime

    def _record(self, actor, receipt):
        with self.runtime.db() as db:
            row = db.execute('SELECT r.job,r.title,r.created,s.row_id,s.fields_json FROM employee_intake_receipts r '
                'LEFT JOIN employee_request_snapshots s ON s.receipt=r.receipt '
                'WHERE r.receipt=? AND r.owner=? AND r.sheet=? AND r.job IS NOT NULL',
                (receipt,actor.key,self.intake.reader.sheet_id)).fetchone()
        if not row:
            raise WriteError('This request is not available to your account.',404)
        return row

    def _project(self, record):
        if not record[3]:
            return None  # Earlier receipts need verified binding; never guess by email/title.
        project = next((p for p in self.intake.reader._cache['projects']
                        if p['id']==record[0] and p['_rowId']==record[3]),None)
        if (not project or self.runtime.lifecycle.is_deleted(self.intake.reader.sheet_id,record[3]) or project.get('synthetic') is not True or project.get('readOnly')
                or record[3] in self.runtime.active_config().copied_row_ids):
            return None
        return project

    def _dto(self, receipt, record, details=False):
        project = self._project(record)
        base = {'receipt':receipt,'jobId':record[0],'title':record[1],
                'submittedAt':datetime.fromtimestamp(record[2],timezone.utc).isoformat()}
        if not project:
            return {**base,'available':False,'status':'unavailable','statusLabel':'Contact Creative Services',
                    'message':'Tracking is unavailable for this request. Contact Creative Services with your job number.'}
        status,label,step = STAGES.get(project['stage'], ('submitted','Submitted',0))
        raw = next(row for row in self.intake.reader.sheet['rows'] if str(row['id'])==record[3])
        columns = {c['id']:c['title'] for c in self.intake.reader.sheet['columns']}
        assigned = next((display(c) for c in raw['cells'] if columns.get(c['columnId'])=='Assigned Designer'), '')
        result = {**base,'available':True,'status':status,'statusLabel':label,'step':step,
                  'designer':assigned if project.get('response')=='accepted' else '',
                  'requestedDueDate':project.get('requestedDueDate',''),
                  'confirmedDueDate':project.get('finalDueDate',''),
                  'completedDate':project.get('completedDate',''),
                  'lastUpdatedAt':timestamp(raw.get('modifiedAt'))}
        if details:
            fields = json.loads(record[4])
            result['originalRequest'] = {key:fields[key] for key in ORIGINAL_FIELDS if key in fields}
            inventory = {f['id']:f for f in project.get('attachments',[])}
            with self.runtime.db() as db:
                resources = db.execute('SELECT attachment_id,category FROM employee_request_resources '
                    'WHERE receipt=? AND visible=1 ORDER BY updated_at,attachment_id',(receipt,)).fetchall()
                submitted = db.execute('SELECT name FROM employee_intake_files WHERE receipt=? ORDER BY rowid',(receipt,)).fetchall()
            result['files'] = [{'id':aid,'name':inventory[aid]['name'],'size':inventory[aid].get('size',''),
                               'category':category,
                               'url':f'/api/intake/my-requests/{receipt}/attachments/{aid}'}
                              for aid,category in resources if aid in inventory]
            linked = {f['name'] for f in result['files'] if f['category']=='submitted'}
            result['unlinkedSubmittedFiles'] = [name for (name,) in submitted if name not in linked]
        return result

    def list(self, sid, offset=0):
        if type(offset) is not int or offset<0 or offset>10000:
            raise WriteError('Choose a valid request page.')
        actor = self.intake.session(sid).actor
        with self.runtime.sheet_lock:
            with self.runtime.db() as db:
                receipts = db.execute('SELECT receipt FROM employee_intake_receipts WHERE owner=? AND sheet=? '
                    'AND job IS NOT NULL ORDER BY created DESC,receipt LIMIT 21 OFFSET ?',
                    (actor.key,self.intake.reader.sheet_id,offset)).fetchall()
            self.intake.reader.projects(force=True)
            result = {'requests':[self._dto(r,self._record(actor,r)) for (r,) in receipts[:20]],
                      'offset':offset,'hasMore':len(receipts)>20}
            if self.intake.session(sid).actor != actor:
                raise WriteError('Sign in again to see your requests.',401)
            return result

    def get(self, sid, receipt):
        actor = self.intake.session(sid).actor
        with self.runtime.sheet_lock:
            record = self._record(actor,receipt)  # Before source/file reads.
            self.intake.reader.projects(force=True)
            result = self._dto(receipt,record,details=True)
            self.intake.session(sid)
            return result

    def attachment(self, sid, receipt, attachment_id):
        actor = self.intake.session(sid).actor
        with self.runtime.sheet_lock:
            record = self._record(actor,receipt)
            with self.runtime.db() as db:
                grant = db.execute('SELECT content_sha256 FROM employee_request_resources '
                    'WHERE receipt=? AND attachment_id=? AND visible=1',(receipt,attachment_id)).fetchone()
            if not grant:
                raise WriteError('This file is not available to your account.',404)
            self.intake.reader.projects(force=True)
            if not self._project(record):
                raise WriteError('This request is not available.',404)
            content,mime,name = self.intake.reader.attachment(record[0],attachment_id)
            if hashlib.sha256(content).hexdigest()!=grant[0]:
                raise WriteError('This file changed. Ask Creative Services to share the current version.',409)
            self.intake.session(sid)
            with self.runtime.db() as db:
                current = db.execute('SELECT content_sha256 FROM employee_request_resources WHERE receipt=? '
                    'AND attachment_id=? AND visible=1',(receipt,attachment_id)).fetchone()
            if not self._project(record):raise WriteError('This request is no longer available.',404)
            if current!=grant:
                raise WriteError('File access changed. Refresh your request.',403)
            return content,mime,name

    def _staff(self, sid, job, edit=False):
        context = self.runtime.jobs._fresh(sid)
        project = self.runtime.jobs._project(context,job)
        if project.get('readOnly') or not project.get('synthetic'):
            raise WriteError('Copied projects cannot share files through requester tracking.',403)
        if edit and not self.runtime.jobs._permissions(context,project)['edit']:
            raise WriteError('Only a current job editor can change requester file access.',403)
        with self.runtime.db() as db:
            receipt = db.execute('SELECT r.receipt FROM employee_intake_receipts r '
                'JOIN employee_request_snapshots s ON s.receipt=r.receipt '
                'WHERE r.sheet=? AND r.job=? AND s.row_id=?',
                (context.reader.sheet_id,job,project['_rowId'])).fetchone()
        if not receipt:
            raise WriteError('Requester tracking is not available for this job.',404)
        return context,project,receipt[0]

    def staff_resources(self,sid,job):
        self.intake.active()
        with self.runtime.sheet_lock:
            context,project,receipt = self._staff(sid,job)
            with self.runtime.db() as db:
                rows = db.execute('SELECT attachment_id,category,visible FROM employee_request_resources WHERE receipt=?',(receipt,)).fetchall()
            self.runtime.jobs._ensure_current(sid,context)
            return {'resources':[{'id':aid,'category':category,'visible':bool(visible)} for aid,category,visible in rows]}

    def share(self,sid,job,body):
        self.intake.active()
        if (not isinstance(body,dict) or set(body)!={'attachmentId','visible','revision'}
                or type(body['visible']) is not bool or not isinstance(body['attachmentId'],str)
                or not isinstance(body['revision'],str)
                or not re.fullmatch(r'\d{1,20}',body['attachmentId'])):
            raise WriteError('Choose a file and its requester visibility.')
        aid,visible = body['attachmentId'],body['visible']
        with self.runtime.sheet_lock:
            context,project,receipt = self._staff(sid,job,edit=True)
            if body['revision']!=project['revision']:
                raise WriteError('The job changed. Refresh before sharing.',409)
            if not any(f['id']==aid for f in project.get('attachments',[])):
                raise WriteError('This file does not belong to this job.',404)
            with self.runtime.db() as db:
                prior = db.execute('SELECT category,content_sha256 FROM employee_request_resources WHERE receipt=? AND attachment_id=?',(receipt,aid)).fetchone()
            if prior and prior[0]=='submitted':
                raise WriteError('The requester already has access to their submitted file.',409)
            digest = prior[1] if prior else ''
            if visible:
                content,_,_ = context.reader.attachment(job,aid)
                digest = hashlib.sha256(content).hexdigest()
            fresh,latest,latest_receipt = self._staff(sid,job,edit=True)
            if fresh.principal!=context.principal or latest['revision']!=project['revision'] or latest_receipt!=receipt:
                raise WriteError('The job changed. Refresh before sharing.',409)
            with self.runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT INTO employee_request_resources VALUES (?,?,?,?,?,?,?) '
                    'ON CONFLICT(receipt,attachment_id) DO UPDATE SET content_sha256=excluded.content_sha256,'
                    'visible=excluded.visible,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
                    (receipt,aid,'shared',digest,int(visible),'smartsheet:'+context.principal.user_id,now()))
                db.execute('INSERT INTO employee_resource_events VALUES (?,?,?,?,?,?)',
                    (secrets.token_urlsafe(24),receipt,aid,'share' if visible else 'revoke',context.principal.user_id,now()))
            return self.staff_resources(sid,job)
