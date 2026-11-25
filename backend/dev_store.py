"""Bounded DEV writes. No arbitrary API requests, schema edits, moves or deletions."""
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, quote
from zoneinfo import ZoneInfo
try:
    from backend.organizations import ORGANIZATION_FIELDS, choices as organization_choices, resolve as resolve_organization
    from backend import assignment_history
except ImportError:
    from organizations import ORGANIZATION_FIELDS, choices as organization_choices, resolve as resolve_organization
    import assignment_history

STAGES = ['New', 'Assigned', 'Accepted', 'In Progress', 'In Review', 'Completed', 'Archived']
YES = 'Yes - I can take this job.'
NO = "No - I'm not available."

def allowed_stages(project):
    stage=project['stage']
    if stage=='Archived':
        return ['Archived']
    if stage=='Completed':
        return ['Completed','Archived']
    if project.get('response')=='accepted':
        return ['Accepted','In Progress','In Review','Completed','Archived']
    return [stage,'Archived'] if stage in ('New','Assigned') else ['Archived']

def routing_status(stage, response):
    return 'Designer Accepted' if response=='accepted' else 'Designer Requested' if stage=='Assigned' else 'New'
FIELDS = {
    'title': 'Description', 'description': 'Additional Details', 'taskType': 'Task Type',
    'requestedDueDate': 'Due Date', 'finalDueDate': 'Final Due Date',
    'hours': 'Estimated Hours', 'priority': 'Priority', 'deliverables': 'Deliverables and Quantities',
    'requestor': 'Requestor', 'email': 'Requestor Email', 'chargeNumber': 'Charge #',
    'reference1': 'Reference link 1', 'reference2': 'Reference link 2',
    **ORGANIZATION_FIELDS,
}

class WriteError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

class SaveRefreshError(WriteError):
    """The native write was acknowledged and its durable receipt is saved."""
    def __init__(self, job_id=None, created_row_id=None):
        super().__init__('Saved to DEV Smartsheet, but the refreshed job data is not available yet. Refresh DEV data before editing again; do not submit another request.', 503)
        self.job_id = job_id
        self.created_row_id = created_row_id

def text(value, label, required=False):
    if not isinstance(value, str):
        raise WriteError(label + ' must be text.')
    value = value.strip()
    if (required and not value) or len(value) > 4000:
        raise WriteError(label + ' is required and must fit within 4,000 characters.' if required else label + ' must fit within 4,000 characters.')
    return value

def valid_date(value):
    if value == '':
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise WriteError('Enter a valid date.')
    try:
        date.fromisoformat(value)
    except ValueError:
        raise WriteError('Enter a valid date.') from None
    return value

def revision(row):
    # Ignore row position; only the actual row state matters for stale-edit checks.
    fields = {k: row.get(k) for k in ('id', 'modifiedAt', 'cells', 'attachments', 'locked', 'lockedForUser')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

class DevStore:
    def __init__(self, reader, state_path):
        self.reader = reader
        self.path = Path(state_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        with self.db() as db:
            assignment_history.initialize(db)
            db.execute('CREATE TABLE IF NOT EXISTS rows (sheet TEXT, row_id TEXT, PRIMARY KEY(sheet,row_id))')
            db.execute('CREATE TABLE IF NOT EXISTS operations (sheet TEXT, key TEXT, fingerprint TEXT, state TEXT, result TEXT, PRIMARY KEY(sheet,key))')
            extra = [r[0] for r in db.execute('SELECT row_id FROM rows WHERE sheet=?', (reader.sheet_id,))]
        reader.row_ids = frozenset(set(reader.row_ids) | set(extra))
        self.initial_schema = None
        self.initial_rules = None
        self.baseline = {}
        self.touched = {}

    def db(self):
        return sqlite3.connect(str(self.path), timeout=10)

    def _write(self, *args, **kwargs):
        return self.reader._write(*args, **kwargs)

    def validate_source(self, *, source_current=False):
        r = self.reader
        if not source_current or r.sheet is None:
            r.projects(force=True)
        sheet = r.sheet
        if sheet.get('accessLevel') not in ('OWNER', 'ADMIN', 'EDITOR', 'EDITOR_SHARE'):
            raise WriteError('This API account does not have DEV editing access.', 403)
        columns = {c['title']: c for c in sheet['columns']}
        required = set(FIELDS.values()) | {'DEV Test Record', 'Graphics Req #', 'Requested Designer', 'Designer Response', 'Assigned Designer', 'Project Stage', 'Completed Date', 'Status', 'Update Status', 'Req Assigned / Closed'}
        if not required.issubset(columns):
            raise WriteError('The DEV field mapping changed. Saving is stopped.', 409)
        if columns['Assigned Designer'].get('formula') != '=IF([Designer Response]@row = "Yes - I can take this job.", [Requested Designer]@row, "")':
            raise WriteError('The native assignment formula changed. Saving is stopped.', 409)
        rules = r._get_json(f'/sheets/{r.sheet_id}/automationrules?includeAll=true', 'dev-automation-check')
        if 'data' not in rules or any(rule.get('enabled') is not False for rule in rules['data']):
            raise WriteError('A DEV automation is active or its status is unknown. Saving is stopped; no workflow was changed.', 409)
        schema = json.dumps(sheet['columns'], sort_keys=True)
        rule_state = json.dumps(rules['data'], sort_keys=True)
        if self.initial_schema is None:
            self.initial_schema, self.initial_rules = schema, rule_state
            self.baseline = {str(row['id']): json.loads(json.dumps(row)) for row in sheet['rows']}
        elif schema != self.initial_schema or rule_state != self.initial_rules:
            raise WriteError('DEV columns or workflow configuration changed. Restart after reviewing the mapping.', 409)
        return columns

    def assignment_actor(self):
        return {'id':'local-dev','name':'Local DEV operator'}

    def assignment_details(self, project):
        with self.db() as db:
            return assignment_history.details(db,self.reader.sheet_id,project)

    def assignment_values(self, columns, values, project=None, row=None, *, action='create'):
        response=values.get('Designer Response',None)
        response=('accepted' if response==YES else 'declined' if response==NO else '') if 'Designer Response' in values else (project or {}).get('response','')
        stage=values.get('Project Stage',(project or {}).get('stage','New'))
        status=routing_status(stage,response)
        if status not in columns['Status'].get('options',[]) or not {'Pending','Responded'}.issubset(columns['Update Status'].get('options',[])):
            raise WriteError('The native routing-status choices changed. Assignment saving is paused.',409)
        if action=='stage' and (project or {}).get('nativeStatus') not in ('',None,'New','Designer Requested','Designer Accepted'):
            # A production-stage change must not erase a legacy editing/cancel/close status.
            status=project['nativeStatus']
        else:
            values.update({'Status':status,'Update Status':'Responded' if response else 'Pending' if stage=='Assigned' else None})
        if response=='accepted' and action in ('create','accept','claim'):
            assigned=next((c.get('value') for c in (row or {}).get('cells',[]) if c['columnId']==columns['Req Assigned / Closed']['id']),None)
            if not assigned:
                values['Req Assigned / Closed']=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        return {'requestedDesigner':values.get('Requested Designer',(project or {}).get('requestedDesigner','')),
                'response':response,'stage':stage,'nativeStatus':status}

    def record_assignment(self, key, project, action, after, reason=''):
        with self.db() as db:
            assignment_history.prepare(db,self.reader.sheet_id,key,project,action,after,self.assignment_actor(),datetime.now(timezone.utc).isoformat(),reason)

    def metadata(self):
        columns = {c['title']: c for c in self.reader.sheet['columns']}
        contacts = columns.get('Assigned Designer', {}).get('contactOptions', []) + columns.get('Requested Designer', {}).get('contactOptions', [])
        designers = {p['id']: p for p in self.reader._cache['designers']}
        for contact in contacts:
            email = contact.get('email', '').lower()
            if email:
                name = contact.get('name') or email
                designers[email] = {'id': email, 'name': name, 'initials': ''.join(x[:1] for x in name.split()[:2]), 'capacity': None}
        try:
            from backend.intake_choices import department_options
        except ImportError:
            from intake_choices import department_options
        return {'organizationOptions': organization_choices(self.reader.sheet), 'departmentOptions': department_options(self.reader.sheet), 'designers': list(designers.values()), 'taskTypes': columns.get('Task Type', {}).get('options', []), 'taskTypeMultiple': columns.get('Task Type', {}).get('type') == 'MULTI_PICKLIST', 'priorities': columns.get('Priority', {}).get('options', [])}

    def permits_admin_row(self,row_id):
        return False

    def organization_policy(self):
        return None

    def route_organization(self, columns, values, row=None):
        policy = self.organization_policy()
        if policy is None:
            return
        manager = columns.get('Assigning Manager', {})
        if manager.get('type') != 'CONTACT_LIST':
            raise WriteError('The native coordinating-manager field changed. Routing is paused.', 409)
        titles = {c['id']: c['title'] for c in columns.values()}
        previous = {titles.get(c['columnId']): c.get('value', '') for c in (row or {}).get('cells', [])}
        decision = resolve_organization(policy,
            values.get('Owner Directorate', previous.get('Owner Directorate', '')),
            values.get('Owner Division/Office/Facility', previous.get('Owner Division/Office/Facility', '')))
        values['Assigning Manager'] = decision['email']

    def row(self, job_id, expected=None):
        columns = {c['id']: c['title'] for c in self.reader.sheet['columns']}
        matches = []
        for row in self.reader.sheet['rows']:
            cells = {columns.get(c['columnId']): c for c in row.get('cells', [])}
            if ((str(row['id']) in self.reader.row_ids and str(row['id']) not in self.reader.copied_row_ids and cells.get('DEV Test Record', {}).get('value') is True) or self.permits_admin_row(str(row['id']))) and cells.get('Graphics Req #', {}).get('value') == job_id:
                matches.append(row)
        if len(matches) != 1:
            raise WriteError('This job is outside the approved synthetic DEV rows.', 404)
        row = matches[0]
        if row.get('locked') or row.get('lockedForUser'):
            raise WriteError('This DEV row is locked.', 409)
        if expected is not None and (not isinstance(expected, str) or revision(row) != expected):
            raise WriteError('This job changed since it was opened. Refresh it and review the latest values before saving.', 409)
        return row

    def cells(self, columns, values, row=None):
        existing = {c['columnId']: c for c in (row or {}).get('cells', [])}
        result = []
        for title, value in values.items():
            col = columns[title]
            cell = existing.get(col['id'], {})
            if col.get('formula') or col.get('systemColumnType') or col.get('locked') or cell.get('formula') or cell.get('linkInFromCell'):
                raise WriteError('A protected or computed field cannot be overwritten: ' + title, 409)
            out = {'columnId': col['id'], 'value': value, 'strict': True}
            if col['type'] == 'MULTI_PICKLIST':
                out = {'columnId': col['id'], 'objectValue': {'objectType': 'MULTI_PICKLIST', 'values': value if isinstance(value, list) else [value]}, 'strict': True}
            if title == 'Requested Designer' and value:
                person = next((p for p in self.metadata()['designers'] if p['id'] == value), None)
                if not person:
                    raise WriteError('Choose a designer from the DEV directory.')
                out = {'columnId': col['id'], 'objectValue': {'objectType': 'CONTACT', 'email': value, 'name': person['name']}, 'strict': True}
            if title == 'Assigning Manager' and self.organization_policy():
                person = next((p for p in self.organization_policy()['managers'].values() if p['email'] == value), None)
                if not person:
                    raise WriteError('The coordinating manager is not in the reviewed routing policy.', 409)
                out = {'columnId': col['id'], 'value': value, 'displayValue': person['name'], 'strict': True}
            if cell.get('hyperlink'):
                raise WriteError('This cell has a native hyperlink; edit it in Smartsheet to preserve its link.', 409)
            result.append(out)
        return result

    def clean_fields(self, fields, columns):
        if not isinstance(fields, dict) or not fields or set(fields) - set(FIELDS):
            raise WriteError('Unknown or empty editable field list.')
        values = {}
        for key, value in fields.items():
            title = FIELDS[key]
            if key == 'taskType' and columns[title]['type'] == 'MULTI_PICKLIST':
                value = [value] if isinstance(value, str) else value
                if not isinstance(value, list) or not value or any(not isinstance(v, str) or v not in columns[title].get('options', []) for v in value):
                    raise WriteError('Choose one or more existing DEV task types.')
                value = list(dict.fromkeys(value))
            elif key in ('requestedDueDate', 'finalDueDate'):
                value = valid_date(value)
            elif key == 'hours':
                if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 10000):
                    raise WriteError('Estimated hours must be between 0 and 10,000, or blank.')
            else:
                value = text(value, title, key in ('title', 'description', 'requestor', 'email', 'taskType'))
                if key == 'chargeNumber' and value and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._/-]{0,79}', value):
                    raise WriteError('Enter a charge number of up to 80 letters, numbers, spaces, dots, slashes, underscores or hyphens. Validation is still pending.')
                if key == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
                    raise WriteError('Enter a valid requestor email.')
                if key.startswith('reference') and value:
                    try:
                        url = urlsplit(value)
                        good = url.scheme in ('https', 'http') and url.hostname and not url.username and not url.password
                    except ValueError:
                        good = False
                    if not good:
                        raise WriteError('Reference links must be complete http or https URLs.')
                if key in ('taskType', 'priority') and value not in columns[title].get('options', []):
                    raise WriteError('Choose an existing DEV ' + title.lower() + '.')
                if key in ('directorate', 'division') and value and value not in columns[title].get('options', []):
                    raise WriteError('Choose an existing ' + title.lower() + ', or leave it blank for coordination.')
            values[title] = value
        return values

    def begin(self, key, fingerprint):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}', key):
            raise WriteError('A valid request identifier is required.')
        with self.db() as db:
            prior = db.execute('SELECT fingerprint,state,result FROM operations WHERE sheet=? AND key=?', (self.reader.sheet_id, key)).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise WriteError('This request identifier belongs to different content. Refresh before retrying.', 409)
                if prior[1] != 'done':
                    raise WriteError('The previous save has an uncertain outcome. Refresh and inspect Smartsheet before trying another save; it was not repeated.', 409)
                return json.loads(prior[2])
            db.execute('INSERT INTO operations VALUES (?,?,?,?,?)', (self.reader.sheet_id, key, fingerprint, 'pending', None))
        return None

    def finish(self, key, result, row_id=None):
        with self.db() as db:
            if row_id:
                db.execute('INSERT OR IGNORE INTO rows VALUES (?,?)', (self.reader.sheet_id, str(row_id)))
            db.execute('UPDATE operations SET state=?,result=? WHERE sheet=? AND key=?', ('done', json.dumps(result), self.reader.sheet_id, key))
            assignment_history.confirm(db,self.reader.sheet_id,key,result,row_id)

    def perform(self, key, body, job_id=None, *, source_current=False, self_assign_to=None):
        if not isinstance(body, dict):
            raise WriteError('Invalid save request.')
        if self_assign_to is not None and job_id is not None and body.get('action')!='claim':
            raise WriteError('Self-assignment is only available when creating a job.')
        # Preserve legacy receipts for ordinary intake. Include the server-verified
        # assignee in new receipts so a changed checkbox cannot replay other intent.
        intent = [job_id,body] + ([{'selfAssignTo':self_assign_to}] if self_assign_to else [])
        fingerprint = hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()
        with self.reader._lock:
            # Resolve duplicate submissions before checking a now-stale revision.
            with self.db() as db:
                prior = db.execute('SELECT 1 FROM operations WHERE sheet=? AND key=?', (self.reader.sheet_id, key)).fetchone()
            if prior:
                done = self.begin(key, fingerprint)
                result=self.result(done.get('jobId'), done.get('createdRowId'), allow_pending=done.get('readbackPending',False))
                if done.get('createdRowId'):
                    self.finish(key, {'jobId': result['jobId'], 'createdRowId': done['createdRowId']})
                return {**result,'createdRowId':done.get('createdRowId')}
            columns = self.validate_source(source_current=True) if source_current else self.validate_source()
            if job_id is None:
                if set(body) != {'fields'}:
                    raise WriteError('Invalid intake request.')
                fields = dict(body['fields']) if isinstance(body['fields'], dict) else {}
                allowed = set(FIELDS) | {'notes', 'audience', 'specifications', 'requestorGroup', 'dueDate'}
                if set(fields) - allowed:
                    raise WriteError('Unknown intake field.')
                # Preserve every supplied request detail in one native-readable cell;
                # no new columns or formula changes are needed.
                details = text(fields.pop('description', ''), 'Project details', True)
                for detail_key, label in [('notes', 'Notes / additional details'), ('audience', 'Intended audience'), ('specifications', 'Dimensions / file formats')]:
                    extra = text(fields.pop(detail_key, ''), label)
                    if extra:
                        details += '\n\n' + label + ':\n' + extra
                fields['description'] = text(details, 'Combined project details and notes', True)
                fields['requestedDueDate'] = fields.pop('dueDate', '')
                if set(fields) & {'hours', 'finalDueDate'}:
                    raise WriteError('Intake cannot set confirmed estimates or final dates.')
                for required in ('title', 'requestor', 'email'):
                    text(fields.get(required, ''), required, True)
                if not fields.get('taskType'):
                    raise WriteError('Choose at least one task type.')
                fields['title'] = '[DEV PORTAL] ' + fields['title'].removeprefix('[DEV PORTAL] ')
                fields['priority'] = 'Normal'
                values = self.clean_fields(fields, columns)
                self.route_organization(columns, values)
                values.update({'DEV Test Record': True, 'Project Stage': 'New'})
                if self_assign_to:
                    values.update({'Requested Designer':self_assign_to,
                                   'Designer Response':YES,'Project Stage':'Accepted'})
                after=self.assignment_values(columns,values)
                payload = [{'toBottom': True, 'cells': self.cells(columns, values)}]
                self.begin(key, fingerprint)
                self.record_assignment(key,None,'create-self-assigned' if self_assign_to else 'create',after)
                response = self._write('POST', f'/sheets/{self.reader.sheet_id}/rows', payload, 'new-dev-request')
                row = response['result'][0]
                row_id = str(row['id'])
                # Native acknowledgement is durable even if the readback fails.
                native_job = next((c.get('value') for c in row.get('cells', [])
                    if c['columnId'] == columns['Graphics Req #']['id']), None)
                self.finish(key, {'jobId': native_job, 'createdRowId': row_id, 'readbackPending':True}, row_id)
                self.reader.row_ids = frozenset(set(self.reader.row_ids) | {row_id})
                result = self.result(native_job, row_id, allow_pending=True)
                job_id = result['jobId']
                self.finish(key, {'jobId': job_id,'createdRowId':row_id}, row_id)
                # This was just read back by permanent row ID; do not load it twice.
                return {**result, 'createdRowId':row_id}
            else:
                if set(body) - {'action', 'revision', 'fields', 'stage', 'designer', 'reason', 'confirmReset'}:
                    raise WriteError('Unknown save parameter.')
                row = self.row(job_id, body.get('revision', ''))
                project = next(p for p in self.reader._cache['projects'] if p['id'] == job_id)
                action = body.get('action')
                if action == 'edit' and set(body) == {'action', 'revision', 'fields'}:
                    values = self.clean_fields(body['fields'], columns)
                    if set(body['fields']) & {'directorate', 'division'}:
                        self.route_organization(columns, values, row)
                elif action == 'offer' and set(body) == {'action', 'revision', 'designer'}:
                    if project['response'] == 'accepted' or project['stage'] in ('Completed', 'Archived'):
                        raise WriteError('Offer a new, unassigned active request.', 409)
                    values = {'Requested Designer': text(body['designer'], 'Designer', True), 'Designer Response': None, 'Project Stage': 'Assigned'}
                    if project['stage']=='Assigned' and not project['response'] and project['requestedDesigner']==values['Requested Designer']:
                        raise WriteError('This designer already has the current offer. Its offer date was kept.',409)
                elif action == 'reassign' and set(body)=={'action','revision','designer','reason','confirmReset'}:
                    if project['response']!='accepted' or project['stage'] in ('Completed','Archived') or body['confirmReset'] is not True:
                        raise WriteError('Reassignment requires an active accepted job and explicit acceptance reset.',409)
                    designer=text(body['designer'],'Designer',True)
                    if designer==project['requestedDesigner']:
                        raise WriteError('Choose a different designer for reassignment.',409)
                    text(body['reason'],'Reassignment reason',True)
                    values={'Requested Designer':designer,'Designer Response':None,'Project Stage':'Assigned'}
                elif action=='claim' and set(body)=={'action','revision'}:
                    if not self_assign_to or project['stage']!='New' or project['response']=='accepted' or (project['requestedDesigner'] and project['response']!='declined'):
                        raise WriteError('Only an available, unassigned request can be claimed.',409)
                    values={'Requested Designer':self_assign_to,'Designer Response':YES,'Project Stage':'Accepted'}
                elif action in ('accept', 'decline') and set(body) == {'action', 'revision'}:
                    if not project['requestedDesigner'] or project['response'] == 'accepted' or project['stage'] != 'Assigned':
                        raise WriteError('This job does not have a pending designer offer.', 409)
                    values = {'Designer Response': YES if action == 'accept' else NO, 'Project Stage': 'Accepted' if action == 'accept' else 'New'}
                elif action == 'stage' and set(body) == {'action', 'revision', 'stage'}:
                    stage = body['stage']
                    if stage not in allowed_stages(project):
                        raise WriteError('This stage would conflict with the assignment. Use the offer or reassignment action instead.',409)
                    if stage == 'Assigned' and not project['requestedDesigner']:
                        raise WriteError('Offer the request to a designer first.')
                    if stage in ('Accepted', 'In Progress', 'In Review', 'Completed') and project['response'] != 'accepted':
                        raise WriteError('Record designer acceptance before starting work.')
                    values = {'Project Stage': stage}
                    if stage=='Completed' and not project['completedDate']:
                        values['Completed Date'] = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
                else:
                    raise WriteError('Unknown or malformed project action.')
                after=self.assignment_values(columns,values,project,row,action=action) if action!='edit' else None
                payload = [{'id': row['id'], 'cells': self.cells(columns, values, row)}]
                self.begin(key, fingerprint)
                if after:
                    self.record_assignment(key,project,action,after,body.get('reason',''))
                self._write('PUT', f'/sheets/{self.reader.sheet_id}/rows', payload, 'dev-job-' + action)
                self.touched.setdefault(str(row['id']), set()).update(values)
                self.finish(key, {'jobId': job_id})
            return self.result(job_id)

    def result(self, job_id, created_row_id=None, *, allow_pending=False):
        # Import locally: the server module also imports this writer.
        try:
            from backend.server import GatewayError
        except ImportError:
            from server import GatewayError
        try:
            data = self.reader.projects(force=True)
        except GatewayError:
            raise SaveRefreshError(job_id, created_row_id) from None
        if created_row_id:
            projected = next((p for p in data['projects'] if p['_rowId'] == created_row_id), None)
            if not projected:
                if allow_pending:
                    raise SaveRefreshError(job_id, created_row_id)
                raise WriteError('The original created row is no longer available. Ask an admin to reconcile this request.',409)
            if job_id and projected['id'] != job_id:
                raise WriteError('The original created row cannot be verified. Ask an admin to reconcile this request.',409)
            job_id = projected['id']
        return {**data, 'jobId': job_id}

    def verification(self):
        self.validate_source()
        columns = {c['id']: c for c in self.reader.sheet['columns']}
        current = {str(row['id']): row for row in self.reader.sheet['rows']}
        preserved = True
        for row_id, before in self.baseline.items():
            if row_id not in current:
                preserved = False
                continue
            after = {c['columnId']: c for c in current[row_id]['cells']}
            for cell in before['cells']:
                col = columns[cell['columnId']]
                other = after.get(cell['columnId'], {})
                if col.get('systemColumnType'):
                    continue
                if cell.get('formula') or col.get('formula'):
                    preserved &= cell.get('formula') == other.get('formula')
                elif col['title'] not in self.touched.get(row_id, set()):
                    preserved &= cell == other
        return {'schemaUnchanged': True, 'workflowConfigUnchanged': True, 'protectedExistingCellsUnchanged': bool(preserved), 'deleteEnabled': False}

    def upload(self, key, job_id, expected, name, mime, content):
        if not isinstance(name, str) or not name or len(name) > 200 or any(c in name for c in '\r\n\x00/\\"'):
            raise WriteError('Choose a file with a simple filename of up to 200 characters.')
        allowed = {'image/png', 'image/jpeg', 'image/webp', 'application/pdf', 'text/plain'}
        if mime not in allowed or not content or len(content) > 30 * 1024 * 1024:
            raise WriteError('Use PNG, JPEG, WebP, PDF or plain text, up to 30 MB per file.')
        fingerprint = hashlib.sha256(json.dumps([job_id, name, mime]).encode() + content).hexdigest()
        with self.reader._lock:
            with self.db() as db:
                prior = db.execute('SELECT 1 FROM operations WHERE sheet=? AND key=?', (self.reader.sheet_id, key)).fetchone()
            if prior:
                receipt = self.begin(key, fingerprint)
                return {**self.result(receipt['jobId']), 'attachmentId': receipt.get('attachmentId')}
            self.validate_source()
            row = self.row(job_id, expected)
            self.begin(key, fingerprint)
            disposition = f'attachment; filename="{name}"' if name.isascii() else "attachment; filename*=UTF-8''" + quote(name, safe='')
            response = self._write('POST', f'/sheets/{self.reader.sheet_id}/rows/{row["id"]}/attachments', content, 'dev-reference-upload', {'Content-Type': mime, 'Content-Disposition': disposition})
            native = response.get('result', {})
            attachment_id = str(native.get('id', '')) if isinstance(native, dict) else ''
            attachment_id = attachment_id if attachment_id.isdigit() else None
            self.finish(key, {'jobId': job_id, 'attachmentId': attachment_id})
            return {**self.result(job_id), 'attachmentId': attachment_id}
