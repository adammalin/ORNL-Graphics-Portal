"""Local prototype gateway: static demo or explicitly allowlisted, read-only DEV rows.

Not a production identity service. Always binds to loopback. No Smartsheet mutation
method exists. Credentials are entered with getpass and remain in process memory.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, unquote, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
MAX_FILE_BYTES = 30 * 1024 * 1024

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

def date_value(cell):
    value = str(cell.get('value') or '')
    return value[:10] if len(value) >= 10 and value[4:5] == '-' and value[7:8] == '-' else ''

def normalize_sheet(sheet, sheet_id, row_ids):
    if str(sheet.get('id')) != str(sheet_id) or sheet.get('name') != 'DEV Graphics Assignments':
        raise GatewayError('The configured source is not the approved DEV Graphics Assignments sheet.')
    columns = {c['id']: c.get('title', '') for c in sheet.get('columns', [])}
    if 'DEV Test Record' not in columns.values():
        raise GatewayError('The source does not have the DEV test marker.')
    projects, people = [], {}
    for row in sheet.get('rows', []):
        if str(row.get('id')) not in row_ids:
            continue
        cells = {columns.get(c['columnId'], ''): c for c in row.get('cells', [])}
        if cells.get('DEV Test Record', {}).get('value') is not True:
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
        response = 'accepted' if assigned_id else 'declined' if response_text.startswith('no') else ''
        designer_id = assigned_id or offered_id
        stage = v('Project Stage')
        if stage not in ['New', 'Assigned', 'Accepted', 'In Progress', 'In Review', 'Completed', 'Archived']:
            stage = 'New'
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
        projects.append({'id': job_id, 'synthetic': True, 'title': title, 'description': v('Additional Details'), 'notes': '', 'taskType': v('Task Type'), 'stage': stage, 'requestedDesigner': designer_id, 'response': response, 'hours': hours, 'dueDate': date_value(cells.get('Final Due Date', {})) or date_value(cells.get('Due Date', {})), 'createdDate': date_value(cells.get('Req Received', {})), 'completedDate': date_value(cells.get('Completed Date', {})), 'priority': v('Priority') or 'Normal', 'requestor': v('Requestor'), 'email': v('Requestor Email'), 'requestorGroup': '', 'deliverables': v('Deliverables and Quantities'), 'references': references, 'attachments': attachments})
    return projects, list(people.values())

class SmartsheetReader:
    def __init__(self, sheet_id, row_ids, token, transport=None):
        self.sheet_id = require_id(sheet_id)
        self.row_ids = frozenset(require_id(r) for r in row_ids)
        if not self.row_ids:
            raise GatewayError('Explicit synthetic DEV row IDs are required for this pilot.')
        if not token:
            raise GatewayError('A token is required for a live DEV connection.')
        self._token = token
        self._transport = transport
        self._opener = build_opener(NoRedirect())
        self.audit = []
        self._cache = None
        self._cache_time = 0
        self._lock = threading.Lock()
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
            query = urlencode({'rowIds': ','.join(sorted(self.row_ids)), 'include': 'attachments,objectValue'})
            sheet = self._get_json(f'/sheets/{self.sheet_id}?{query}', 'allowlisted-dev-rows')
            projects, designers = normalize_sheet(sheet, self.sheet_id, self.row_ids)
            self.version = sheet.get('version')
            if self.initial_version is None:
                self.initial_version = self.version
            self._cache = {'mode': 'dev-readonly', 'projects': projects, 'designers': designers}
            self._cache_time = time.monotonic()
            return self._cache

    def attachment(self, job_id, attachment_id):
        attachment_id = require_id(attachment_id)
        project = next((p for p in self.projects()['projects'] if p['id'] == job_id), None)
        if not project or not any(f['id'] == attachment_id for f in project['attachments']):
            raise GatewayError('This attachment does not belong to an allowlisted DEV job.')
        metadata = self._get_json(f'/sheets/{self.sheet_id}/attachments/{attachment_id}', 'verified-dev-attachment')
        if str(metadata.get('id')) != attachment_id:
            raise GatewayError('Unexpected attachment response.')
        parsed = urlsplit(metadata.get('url', ''))
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or parsed.username or parsed.password or not (host.endswith('.amazonaws.com') or host.endswith('.smartsheet.com')):
            raise GatewayError('The attachment host is not supported by this pilot.')
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
                    self.json_response(200, self.server.reader.projects())
                    return
                if path == '/api/verification':
                    reader = self.server.reader
                    data = reader.projects(force=True)
                    self.json_response(200, {'mode': 'dev-readonly', 'syntheticJobs': len(data['projects']), 'sheetVersionUnchanged': reader.initial_version == reader.version, 'nativeWritesEnabled': False, 'upstreamRequests': reader.audit})
                    return
                parts = path.strip('/').split('/')
                if len(parts) == 5 and parts[:2] == ['api', 'projects'] and parts[3] == 'attachments':
                    content, mime, name = self.server.reader.attachment(unquote(parts[2]), parts[4])
                    allowed_preview = {'image/png', 'image/jpeg', 'image/webp', 'text/plain'}
                    download = 'download' in parse_qs(urlsplit(self.path).query) or mime not in allowed_preview
                    disposition = f"{'attachment' if download else 'inline'}; filename*=UTF-8''{quote(name, safe='')}"
                    self.response(200, content, 'application/octet-stream' if download else mime, {'Content-Disposition': disposition})
                    return
                self.json_response(404, {'error': 'Unknown read-only endpoint.'})
            except GatewayError as error:
                self.json_response(502, {'error': str(error)})
            return
        if path == '/runtime-config.js' and self.server.reader:
            self.response(200, "window.PORTAL_CONFIG=Object.freeze({dataMode:'dev-readonly',apiBase:'/api'});", 'text/javascript; charset=utf-8')
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
        self.response(405, 'This gateway is read-only. No changes were made.', extra={'Allow': 'GET, HEAD'})

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = reject_write

def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--dev', action='store_true', help='Read only explicitly allowlisted synthetic DEV rows; prompt for token.')
    parser.add_argument('--sheet-id', default=os.environ.get('SMARTSHEET_SHEET_ID'))
    parser.add_argument('--row-ids', default=os.environ.get('SMARTSHEET_DEV_ROW_IDS', ''))
    parser.add_argument('--check', action='store_true', help='Verify two GET reads have the same sheet version; print counts only and exit.')
    args = parser.parse_args()
    reader = None
    if args.dev:
        if not args.sheet_id or not args.row_ids:
            parser.error('--dev requires --sheet-id and an explicit --row-ids allowlist.')
        reader = SmartsheetReader(args.sheet_id, args.row_ids.split(','), getpass.getpass('DEV API token (memory only, never saved): '))
        data = reader.projects()
        print(json.dumps({'mode': 'dev-readonly', 'syntheticJobs': len(data['projects']), 'nativeWritesEnabled': False}), flush=True)
    if args.check:
        if not reader:
            parser.error('--check requires --dev.')
        version = reader.version
        reader.projects(force=True)
        print(json.dumps({'twoReadsSameVersion': version == reader.version, 'requests': reader.audit}), flush=True)
        return
    server = PortalServer(('127.0.0.1', args.port), reader)
    print(f'Local: http://127.0.0.1:{server.server_port}', flush=True)
    print('Read-only DEV gateway.' if reader else 'Synthetic demo. No Smartsheet connection.', flush=True)
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
