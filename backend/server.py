"""Local portal gateway: synthetic demo, read-only DEV or scoped DEV editing.

Not a production identity service. Always binds to loopback. Credentials are entered
with getpass and remain in process memory. DEV edits require an explicit startup flag.
"""
import argparse
import getpass
import hmac
import http.cookies
import json
import mimetypes
import math
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, unquote, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler

try:
    from backend.dev_store import DevStore, WriteError, revision
except ImportError:
    from dev_store import DevStore, WriteError, revision

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
MAX_FILE_BYTES = 30 * 1024 * 1024

try:
    from backend.intake_choices import department_value
except ImportError:
    from intake_choices import department_value

class GatewayError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def require_id(value):
    value = str(value)
    if not value.isdigit() or len(value) > 20:
        raise GatewayError('A valid numeric Smartsheet identifier is required.')
    return value

def display(cell):
    value = cell.get('displayValue', cell.get('value', ''))
    return str(value).strip() if value is not None and not isinstance(value, (dict, list)) else ''

def contact(cell):
    obj = cell.get('objectValue') or {}
    email = obj.get('email') if isinstance(obj, dict) else None
    key = email or cell.get('value') or ''
    return str(key).strip().lower(), display(cell)

def url_value(cell):
    raw = (cell.get('hyperlink') or {}).get('url') or display(cell)
    try:
        parsed = urlsplit(raw)
        return raw if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None

def media_type(value):
    return str(value or '').partition(';')[0].strip().lower()

def date_value(cell):
    value = str(cell.get('value') or '')
    return value[:10] if len(value) >= 10 and value[4:5] == '-' and value[7:8] == '-' else ''

def normalize_sheet(sheet, sheet_id, row_ids, copied_row_ids=frozenset()):
    if str(sheet.get('id')) != str(sheet_id) or sheet.get('name') != 'DEV Graphics Assignments':
        raise GatewayError('The configured source is not the approved DEV Graphics Assignments sheet.')
    columns = {c['id']: c.get('title', '') for c in sheet.get('columns', [])}
    if 'DEV Test Record' not in columns.values():
        raise GatewayError('The source does not have the DEV test marker.')
    projects, people = [], {}
    for row in sheet.get('rows', []):
        copied = str(row.get('id')) in copied_row_ids
        if str(row.get('id')) not in row_ids and not copied:
            continue
        cells = {columns.get(c['columnId'], ''): c for c in row.get('cells', [])}
        if not copied and cells.get('DEV Test Record', {}).get('value') is not True:
            continue
        v = lambda title: display(cells.get(title, {}))
        job_id, title = v('Graphics Req #'), v('Description')
        if not job_id or not title:
            continue
        assigned_id, assigned_name = contact(cells.get('Assigned Designer', {}))
        offered_id, offered_name = contact(cells.get('Requested Designer', {}))
        for key, name in [(assigned_id, assigned_name), (offered_id, offered_name)]:
            if key:
                people[key] = {'id': key, 'name': name or key, 'initials': ''.join(p[:1] for p in (name or key).split()[:2]).upper(), 'capacity': None}
        response_text = v('Designer Response').lower()
        response = 'accepted' if assigned_id or (offered_id and response_text == 'yes - i can take this job.') else 'declined' if response_text.startswith('no') else ''
        designer_id = assigned_id or offered_id
        stage = v('Project Stage')
        source_status = v('Status') if copied else ''
        if stage not in ['New', 'Assigned', 'Accepted', 'In Progress', 'In Review', 'Completed', 'Archived']:
            # View-only projection of legacy statuses; never change source cells.
            legacy = {'designer requested': 'Assigned', 'designer accepted': 'Accepted',
                      'completed': 'Completed', 'closed': 'Completed',
                      'canceled': 'Archived', 'cancelled': 'Archived'}
            stage = ('Completed' if copied and date_value(cells.get('Completed Date', {}))
                     else legacy.get(source_status.casefold(), 'New'))
        try:
            hours = float(v('Estimated Hours')) if v('Estimated Hours') else None
            if hours is not None and (not math.isfinite(hours) or hours < 0):
                hours = None
        except ValueError:
            hours = None
        references = []
        for name in ['Reference link 1', 'Reference link 2']:
            url = url_value(cells.get(name, {}))
            if url:
                references.append({'label': name, 'url': url})
        attachments = []
        for f in row.get('attachments', []):
            if f.get('attachmentType') != 'FILE':
                continue
            attachment_id = require_id(f['id'])
            attachments.append({'id': attachment_id, 'name': str(f.get('name', 'Reference file')), 'type': f.get('mimeType', 'application/octet-stream'), 'size': f"{f.get('sizeInKb', 0)} KB", 'remote': True, 'url': f"/api/projects/{quote(job_id, safe='')}/attachments/{attachment_id}"})
        if any(p['id'] == job_id for p in projects):
            raise GatewayError('Ambiguous DEV job identifier. No job details will be returned.')
        task_types = (cells.get('Task Type', {}).get('objectValue') or {}).get('values', [])
        projects.append({'id': job_id, '_rowId': str(row['id']), 'revision': revision(row), 'synthetic': not copied, 'readOnly': copied, 'sourceStatus': source_status, 'title': title, 'description': v('Additional Details'), 'notes': '', 'taskType': ' · '.join(task_types) or v('Task Type'), 'taskTypes': task_types or ([v('Task Type')] if v('Task Type') else []), 'stage': stage, 'requestedDesigner': designer_id, 'response': response, 'hours': hours, 'requestedDueDate': date_value(cells.get('Due Date', {})), 'finalDueDate': date_value(cells.get('Final Due Date', {})), 'dueDate': date_value(cells.get('Final Due Date', {})) or date_value(cells.get('Due Date', {})), 'createdDate': date_value(cells.get('Req Received', {})), 'completedDate': date_value(cells.get('Completed Date', {})), 'priority': v('Priority') or 'Normal', 'requestor': v('Requestor'), 'email': v('Requestor Email'), 'requestorGroup': department_value(cells, display), 'deliverables': v('Deliverables and Quantities'), 'references': references, 'attachments': attachments})
    return projects, list(people.values())

class SmartsheetReader:
    def __init__(self, sheet_id, row_ids, token, transport=None, filter_id=None):
        self.sheet_id = require_id(sheet_id)
        self.row_ids = frozenset(require_id(r) for r in row_ids)
        self.filter_id = require_id(filter_id) if filter_id else None
        self.copied_row_ids = frozenset()
        if not self.row_ids and not self.filter_id:
            raise GatewayError('Explicit synthetic DEV row IDs are required for this pilot.')
        if not token:
            raise GatewayError('A token is required for a live DEV connection.')
        self._token = token
        self._transport = transport
        self._opener = build_opener(NoRedirect())
        self.audit = []
        self._cache = None
        self._cache_time = 0
        self._lock = threading.RLock()
        self.sheet = None
        self.store = None
        self.version = None
        self.initial_version = None

    def _get_json(self, path, kind):
        # Only this fixed-sheet GET and attachment GETs verified below are possible.
        self.audit.append({'method': 'GET', 'resource': kind})
        if self._transport:
            return self._transport(path)
        request = Request('https://api.smartsheet.com/2.0' + path, method='GET', headers={'Authorization': 'Bearer ' + self._token, 'Accept': 'application/json'})
        try:
            with self._opener.open(request, timeout=25) as response:
                raw = response.read(10 * 1024 * 1024 + 1)
                if len(raw) > 10 * 1024 * 1024:
                    raise GatewayError('DEV response exceeded the pilot size limit.')
                return json.loads(raw)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            raise GatewayError('Smartsheet could not be read. Check the token and DEV access.') from None

    def projects(self, force=False):
        with self._lock:
            if not force and self._cache is not None and time.monotonic() - self._cache_time < 15:
                return self._cache
            params = {'include': 'attachments,objectValue', 'level': 2}
            if self.filter_id:
                saved_filter = self._get_json(f'/sheets/{self.sheet_id}/filters/{self.filter_id}', 'dev-filter-check')
                q = saved_filter.get('query') or {}
                criteria = q.get('criteria') or []
                if str(saved_filter.get('id')) != self.filter_id or saved_filter.get('name') != 'DEV - Demo projects' or q.get('operator') != 'AND' or q.get('includeParent') is not False or len(criteria) != 1 or criteria[0].get('operator') != 'IS_CHECKED':
                    raise GatewayError('The native DEV-only filter changed. No jobs will be returned.')
                params.update(filterId=self.filter_id, exclude='filteredOutRows')
            else:
                params['rowIds'] = ','.join(sorted(self.row_ids))
            query = urlencode(params)
            sheet = self._get_json(f'/sheets/{self.sheet_id}?{query}', 'allowlisted-dev-rows')
            if self.filter_id:
                marker = next((c['id'] for c in sheet.get('columns', []) if c.get('title') == 'DEV Test Record'), None)
                if not marker or criteria[0].get('columnId') != marker:
                    raise GatewayError('The native filter is not restricted to DEV Test Record.')
                self.row_ids = frozenset(str(row['id']) for row in sheet.get('rows', []) if any(c.get('columnId') == marker and c.get('value') is True for c in row.get('cells', [])))
            projects, designers = normalize_sheet(sheet, self.sheet_id, self.row_ids)
            # The independent read selection never joins the native write allowlist.
            if self.copied_row_ids:
                self.row_ids = self.row_ids - self.copied_row_ids
                selected = self._get_json(f'/sheets/{self.sheet_id}?' + urlencode({
                    'rowIds': ','.join(sorted(self.copied_row_ids)),
                    'include': 'attachments,objectValue', 'level': 2}), 'selected-copied-dev-rows')
                if (selected.get('version') != sheet.get('version')
                        or selected.get('columns') != sheet.get('columns')
                        or selected.get('accessLevel') != sheet.get('accessLevel')):
                    raise GatewayError('The DEV source changed while loading copied projects. Refresh before continuing.')
                copied, copied_designers = normalize_sheet(selected, self.sheet_id, frozenset(), self.copied_row_ids)
                projects = [p for p in projects if p['_rowId'] not in self.copied_row_ids] + copied
                if len({p['id'] for p in projects}) != len(projects):
                    raise GatewayError('Ambiguous DEV job identifier. No job details will be returned.')
                designers = list({p['id']: p for p in designers + copied_designers}.values())
                sheet = {**sheet, 'rows': [r for r in sheet['rows'] if str(r['id']) not in self.copied_row_ids]
                         + [r for r in selected.get('rows', []) if str(r.get('id')) in self.copied_row_ids]}
            self.sheet = sheet
            self.version = sheet.get('version')
            if self.initial_version is None:
                self.initial_version = self.version
            self._cache = {'mode': 'dev-readonly', 'projects': projects, 'designers': designers, 'sourceVersion': self.version}
            if self.store:
                self._cache.update(self.store.metadata())
                self._cache['mode'] = 'dev-write'
            self._cache_time = time.monotonic()
            return self._cache

    def _write(self, method, path, payload, kind, headers=None):
        if not self.store:
            raise WriteError('DEV writes are not enabled.', 405)
        rows_path = f'/sheets/{self.sheet_id}/rows'
        is_rows = path == rows_path and method in ('POST', 'PUT') and isinstance(payload, list) and len(payload) == 1
        match = re.fullmatch(re.escape(rows_path) + r'/(\d+)/attachments', path)
        is_upload = method == 'POST' and match and match[1] in self.row_ids and match[1] not in self.copied_row_ids and isinstance(payload, bytes)
        if not (is_rows or is_upload):
            raise WriteError('This operation is outside the DEV write boundary.', 403)
        if is_rows and method == 'PUT' and (str(payload[0].get('id')) not in self.row_ids or str(payload[0].get('id')) in self.copied_row_ids):
            raise WriteError('This row is outside the DEV write boundary.', 403)
        self.audit.append({'method': method, 'resource': kind})
        if self._transport:
            return self._transport(path, method, payload, headers)
        request_headers = {'Authorization': 'Bearer ' + self._token, 'Accept': 'application/json', 'Content-Type': 'application/json', 'smartsheet-integration-source': 'APPLICATION,ORNL,Graphics-Portal-DEV'}
        request_headers.update(headers or {})
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        request = Request('https://api.smartsheet.com/2.0' + path, method=method, data=data, headers=request_headers)
        try:
            with self._opener.open(request, timeout=40) as response:
                result = json.load(response)
        except HTTPError as error:
            try:
                detail = json.loads(error.read(4096))
            except (ValueError, UnicodeDecodeError):
                detail = {}
            reason = str(detail.get('message', 'Refresh and inspect the job before trying again.'))[:500]
            raise WriteError(f'Smartsheet rejected this save (HTTP {error.code}, code {detail.get("errorCode", "unknown")}): {reason}', 502) from None
        except (URLError, TimeoutError, json.JSONDecodeError):
            raise WriteError('The save outcome could not be confirmed. Refresh and inspect Smartsheet before trying again; the request was not repeated.', 502) from None
        if result.get('resultCode') != 0 or 'result' not in result:
            raise WriteError('Smartsheet did not confirm a complete save. Refresh and inspect the job.', 502)
        return result

    def attachment(self, job_id, attachment_id):
        attachment_id = require_id(attachment_id)
        project = next((p for p in self.projects()['projects'] if p['id'] == job_id), None)
        if not project or not any(f['id'] == attachment_id for f in project['attachments']):
            raise GatewayError('This attachment does not belong to an allowlisted DEV job.')
        metadata = self._get_json(f'/sheets/{self.sheet_id}/attachments/{attachment_id}', 'verified-dev-attachment')
        if str(metadata.get('id')) != attachment_id:
            raise GatewayError('Unexpected attachment response.')
        try:
            url = metadata.get('url', '')
            if not isinstance(url, str):
                raise ValueError()
            parsed = urlsplit(url)
            host = parsed.hostname or ''
            if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                    or not (host.endswith('.amazonaws.com') or host.endswith('.smartsheet.com'))):
                raise ValueError()
        except (ValueError, TypeError):
            raise GatewayError('The attachment host is not supported by this pilot.') from None
        request = Request(metadata['url'], method='GET')  # Never forward Smartsheet credentials.
        try:
            with self._opener.open(request, timeout=25) as response:
                content = response.read(MAX_FILE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError):
            raise GatewayError('The reference file could not be retrieved.') from None
        if len(content) > MAX_FILE_BYTES:
            raise GatewayError('The reference file exceeds the pilot size limit.')
        self.audit.append({'method': 'GET', 'resource': 'temporary-file-download'})
        return content, metadata.get('mimeType', 'application/octet-stream'), str(metadata.get('name', 'reference-file'))

class PortalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, reader=None):
        if address[0] != '127.0.0.1':
            raise GatewayError('This pilot may only bind to 127.0.0.1.')
        self.reader = reader
        self.session = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        super().__init__(address, PortalHandler)

class PortalHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # No API responses, headers, tokens, form values or signed URLs in logs.
        pass

    def response(self, code, body=b'', content_type='text/plain; charset=utf-8', extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def json_response(self, code, data):
        self.response(code, json.dumps(data), 'application/json; charset=utf-8')

    def allowed_host(self):
        port = self.server.server_port
        return self.headers.get('Host', '') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def api_authorized(self):
        origin = self.headers.get('Origin')
        port = self.server.server_port
        if origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
            return False
        cookie = http.cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except http.cookies.CookieError:
            return False
        given = cookie.get('portal_dev_session')
        return bool(given and hmac.compare_digest(given.value, self.server.session))

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.allowed_host():
            self.response(403, 'Unrecognized local host.')
            return
        path = urlsplit(self.path).path
        if path.startswith('/api/'):
            if not self.server.reader:
                self.json_response(404, {'error': 'No DEV connection is configured.'})
                return
            if not self.api_authorized():
                self.json_response(401, {'error': 'Open the local portal first.'})
                return
            try:
                if path == '/api/projects':
                    self.json_response(200, self.server.reader.projects(force='refresh' in parse_qs(urlsplit(self.path).query)))
                    return
                if path == '/api/verification':
                    reader = self.server.reader
                    data = reader.projects(force=True)
                    extra = reader.store.verification() if reader.store else {}
                    self.json_response(200, {'mode': data['mode'], 'syntheticJobs': len(data['projects']), 'sheetVersionUnchanged': reader.initial_version == reader.version, 'nativeWritesEnabled': bool(reader.store), 'upstreamRequests': reader.audit, **extra})
                    return
                parts = path.strip('/').split('/')
                if len(parts) == 5 and parts[:2] == ['api', 'projects'] and parts[3] == 'attachments':
                    content, mime, name = self.server.reader.attachment(unquote(parts[2]), parts[4])
                    mime = media_type(mime)
                    allowed_preview = {'image/png', 'image/jpeg', 'image/webp', 'text/plain'}
                    download = 'download' in parse_qs(urlsplit(self.path).query) or mime not in allowed_preview
                    disposition = f"{'attachment' if download else 'inline'}; filename*=UTF-8''{quote(name, safe='')}"
                    self.response(200, content, 'application/octet-stream' if download else mime, {'Content-Disposition': disposition})
                    return
                self.json_response(404, {'error': 'Unknown read-only endpoint.'})
            except (GatewayError, WriteError) as error:
                self.json_response(getattr(error, 'status', 502), {'error': str(error)})
            return
        if path == '/runtime-config.js' and self.server.reader:
            mode = 'dev-write' if self.server.reader.store else 'dev-readonly'
            config = {'dataMode': mode, 'apiBase': '/api', 'csrf': self.server.csrf}
            self.response(200, 'window.PORTAL_CONFIG=Object.freeze(' + json.dumps(config) + ');', 'text/javascript; charset=utf-8')
            return
        relative = unquote(path).lstrip('/') or 'index.html'
        candidate = (WEB / relative).resolve()
        if not candidate.is_relative_to(WEB.resolve()) or not candidate.is_file():
            self.response(404, 'Not found.')
            return
        extra = {}
        if candidate == WEB / 'index.html' and self.server.reader:
            extra['Set-Cookie'] = f'portal_dev_session={self.server.session}; HttpOnly; SameSite=Strict; Path=/'
        mime = mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
        if candidate.suffix == '.js':
            mime = 'text/javascript'
        self.response(200, candidate.read_bytes(), mime, extra)

    def reject_write(self):
        self.response(405, 'This method is disabled. No deletion or arbitrary API operation is available.', extra={'Allow': 'GET, HEAD, POST, PATCH' if self.server.reader and self.server.reader.store else 'GET, HEAD'})

    def save(self):
        if not self.server.reader or not self.server.reader.store:
            self.reject_write()
            return
        if not self.allowed_host() or not self.api_authorized() or self.headers.get('Origin') != f'http://{self.headers.get("Host")}' or not hmac.compare_digest(self.headers.get('X-Portal-CSRF', ''), self.server.csrf):
            self.json_response(403, {'error': 'Open the local portal and retry from that tab.'})
            return
        path = urlsplit(self.path).path
        parts = path.strip('/').split('/')
        create = self.command == 'POST' and parts == ['api', 'projects']
        update = self.command == 'PATCH' and len(parts) == 3 and parts[:2] == ['api', 'projects']
        upload = self.command == 'POST' and len(parts) == 4 and parts[:2] == ['api', 'projects'] and parts[3] == 'attachments'
        if not (create or update or upload):
            self.json_response(404, {'error': 'Unknown DEV save endpoint.'})
            return
        try:
            if self.headers.get('Transfer-Encoding'):
                raise WriteError('Chunked uploads are not supported.', 400)
            try:
                length = int(self.headers.get('Content-Length', '-1'))
            except ValueError:
                raise WriteError('Invalid content length.') from None
            if length < 1 or length > (MAX_FILE_BYTES if upload else 100000):
                raise WriteError('Request exceeds the permitted size.', 413)
            self.connection.settimeout(45)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise WriteError('The upload was incomplete.')
            key = self.headers.get('Idempotency-Key', '')
            store = self.server.reader.store
            if upload:
                data = store.upload(key, unquote(parts[2]), self.headers.get('X-Project-Revision', ''), unquote(self.headers.get('X-Filename', '')), self.headers.get('Content-Type', ''), raw)
            else:
                if self.headers.get('Content-Type') != 'application/json':
                    raise WriteError('Use JSON for project saves.', 415)
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise WriteError('Invalid project JSON.') from None
                data = store.perform(key, body, unquote(parts[2]) if update else None)
            self.json_response(200, data)
        except (GatewayError, WriteError) as error:
            self.json_response(getattr(error, 'status', 502), {'error': str(error)})

    do_POST = do_PATCH = save
    do_PUT = do_DELETE = do_OPTIONS = reject_write

def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--dev', action='store_true', help='Read only explicitly allowlisted synthetic DEV rows; prompt for token.')
    parser.add_argument('--dev-write', action='store_true', help='Enable scoped DEV intake, editing and new attachments. Loopback only; no production identity.')
    parser.add_argument('--config', help='Private JSON configuration with sheetId and rowIds. Never include the API token.')
    parser.add_argument('--state', default=str(ROOT / '.local/dev-state.sqlite3'), help='Private local row registry and idempotency ledger; not an API-token store.')
    parser.add_argument('--sheet-id', default=os.environ.get('SMARTSHEET_SHEET_ID'))
    parser.add_argument('--row-ids', default=os.environ.get('SMARTSHEET_DEV_ROW_IDS', ''))
    parser.add_argument('--dev-filter-id', help='Existing DEV - Demo projects filter. Its exact DEV checkbox criterion is checked before using it.')
    parser.add_argument('--check', action='store_true', help='Verify two GET reads have the same sheet version; print counts only and exit.')
    args = parser.parse_args()
    if args.config:
        private_config = json.loads(Path(args.config).read_text())
        args.sheet_id = private_config['sheetId']
        args.row_ids = ','.join(map(str, private_config.get('rowIds', [])))
        args.dev_filter_id = private_config.get('filterId', args.dev_filter_id)
    reader = None
    if args.dev or args.dev_write:
        if not args.sheet_id or not (args.row_ids or args.dev_filter_id):
            parser.error('--dev requires --sheet-id and either explicit --row-ids or the validated DEV filter.')
        reader = SmartsheetReader(args.sheet_id, args.row_ids.split(',') if args.row_ids else [], getpass.getpass('DEV API token (memory only, never saved): '), filter_id=args.dev_filter_id)
        data = reader.projects()
        if args.dev_write:
            reader.store = DevStore(reader, args.state)
            reader.store.validate_source()
            data = reader.projects(force=True)
        print(json.dumps({'mode': data['mode'], 'syntheticJobs': len(data['projects']), 'nativeWritesEnabled': bool(reader.store)}), flush=True)
    if args.check:
        if not reader:
            parser.error('--check requires --dev.')
        version = reader.version
        reader.projects(force=True)
        print(json.dumps({'twoReadsSameVersion': version == reader.version, 'requests': reader.audit}), flush=True)
        return
    server = PortalServer(('127.0.0.1', args.port), reader)
    print(f'Local: http://127.0.0.1:{server.server_port}', flush=True)
    print(('DEV saves enabled for approved synthetic rows.' if reader.store else 'Read-only DEV gateway.') if reader else 'Synthetic demo. No Smartsheet connection.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    try:
        cli()
    except GatewayError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
