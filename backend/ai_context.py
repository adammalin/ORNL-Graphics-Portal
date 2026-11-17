"""Deterministic, allowlisted job snapshots for externally generated AI drafts."""
import hashlib
import json
from datetime import datetime, timezone

try:
    from backend.dev_store import WriteError
    from backend.ai_extract import VERSION, extract
    from backend.server import GatewayError
except ImportError:
    from dev_store import WriteError
    from ai_extract import VERSION, extract
    from server import GatewayError

POLICY = 'browser-ai-1.0'
PROMPT = 'intake-analysis-1.0'
FIELDS = {
    'title': ('Description', 'text'), 'description': ('Additional Details', 'text'),
    'taskType': ('Task Type', 'multi_picklist'), 'requestedDueDate': ('Due Date', 'date'),
    'finalDueDate': ('Final Due Date', 'date'),
    'deliverables': ('Deliverables and Quantities', 'text'),
}
PROPOSABLE = frozenset({'requestedDueDate', 'taskType', 'deliverables'})
MAX_CONTEXT = 150000
MODEL_BUDGET = 80000


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError):
        raise WriteError('Context contains an unsupported value.', 409) from None


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def is_blank(value):
    return value is None or value == '' or value == []


def inventory(reader, project):
    row = next((r for r in reader.sheet['rows'] if str(r['id']) == project['_rowId']), None)
    if not row:
        raise WriteError('This source row is not available.', 404)
    refs = []
    for item in row.get('attachments', []):
        if not str(item.get('id', '')).isdigit():
            raise WriteError('A reference has an invalid identifier.', 409)
        metadata = {k: item.get(k) for k in ('id', 'name', 'mimeType', 'sizeInKb', 'createdAt', 'attachmentType', 'attachmentSubType')}
        refs.append({'sourceId': 'a_' + str(item['id']), 'kind': 'attachment',
            'label': str(item.get('name', 'Reference file'))[:500],
            'mime': str(item.get('mimeType', 'application/octet-stream')),
            'file': item.get('attachmentType') == 'FILE',
            'version': fingerprint(metadata), 'attachmentId': str(item['id'])})
    for n, ref in enumerate(project.get('references', [])):
        refs.append({'sourceId': 'link_' + str(n + 1), 'kind': 'link',
            'label': ref['label'], 'version': fingerprint(ref), 'file': False})
    return sorted(refs, key=lambda r: r['sourceId'])


def build(reader, project, selected, read_attachment):
    refs = inventory(reader, project)
    if len(refs) + len(FIELDS) > 60:
        raise WriteError('context_too_large: this pilot supports at most 60 field/reference entries. The complete inventory remains available separately.', 413)
    ref_map = {r['sourceId']: r for r in refs}
    if not isinstance(selected, list) or len(selected) > 10 or any(not isinstance(x, str) for x in selected) or len(set(selected)) != len(selected) or set(selected) - set(ref_map):
        raise WriteError('Select up to ten references from this job only.')
    columns = {c['title']: c for c in reader.sheet['columns']}
    fields, definitions, sources = {}, {}, []
    for key, (column, kind) in FIELDS.items():
        value = project.get('taskTypes', []) if key == 'taskType' else project.get(key, '')
        if value is None:
            value = ''
        fields[key] = value
        blank = is_blank(value)
        native = columns.get(column, {})
        definitions[key] = {'sourceColumn': column, 'type': kind,
            'isBlank': blank, 'aiProposable': key in PROPOSABLE and blank and not native.get('formula')}
        if key == 'taskType':
            definitions[key]['options'] = list(native.get('options', []))
            definitions[key]['multiple'] = native.get('type') == 'MULTI_PICKLIST'
        if not blank:
            sources.append({'sourceId': 'field_' + key, 'kind': 'field', 'label': column,
                'version': fingerprint(value), 'status': 'delivered',
                'text': '\n'.join(value) if isinstance(value, list) else str(value)})
    for ref in refs:
        source = {k: v for k, v in ref.items() if k not in ('file', 'attachmentId')}
        source.update(status='not_selected', text='')
        if ref['sourceId'] in selected:
            if ref['file']:
                try:
                    content, mime, name = read_attachment(ref['attachmentId'])
                    source.update(extract(content, mime, name))
                except (GatewayError, WriteError):
                    # Authentication/source changes are checked again by the service.
                    source.update(status='inaccessible', text='')
            else:
                source.update(status='unsupported')  # Never fetch external URLs.
        sources.append(source)
    sources.sort(key=lambda s: s['sourceId'])
    readable = sum(len(s['text']) for s in sources)
    if readable > min(MAX_CONTEXT, MODEL_BUDGET):
        raise WriteError('context_too_large: selected text exceeds the 80,000-character browser-agent budget. Select fewer references; no source was silently omitted.', 413)
    body = {'fields': fields, 'fieldDefinitions': definitions, 'sources': sources,
            'extractorVersion': VERSION, 'policyVersion': POLICY, 'promptVersion': PROMPT}
    return {**body, 'schemaVersion': '1.0', 'fingerprintVersion': 'canonical-json-sha256-1',
        'jobId': project['id'], 'sourceRevision': project['revision'],
        'inputFingerprint': fingerprint(body),
        'preparedAt': datetime.now(timezone.utc).isoformat(), 'sourceTimeZone': 'America/New_York',
        'requestTimeAnchor': None, 'relativeDatePolicy': 'Do not resolve relative dates; ask for an explicit date.',
        'selectedReferenceIds': sorted(selected),
        'allowedFieldProposals': [key for key, value in definitions.items() if value['aiProposable']],
        'coverage': {'deliveredSourceIds': [s['sourceId'] for s in sources if s['status'] == 'delivered'],
                     'unreadSources': [{'sourceId': s['sourceId'], 'reason': s['status']} for s in sources if s['status'] != 'delivered']}}
