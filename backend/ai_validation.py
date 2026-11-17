"""Strict external draft validation: shape, evidence, coverage and proposals."""
from datetime import date
import json
import math
from pathlib import Path
import re

try:
    from backend.dev_store import WriteError
except ImportError:
    from dev_store import WriteError

MAX_DRAFT_BYTES = 256 * 1024
SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'docs/contracts/intake-analysis.schema.json'


def strict_json(raw, limit=MAX_DRAFT_BYTES):
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise WriteError('AI JSON exceeds the permitted size.', 413)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('non-finite number')
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('non-finite number')
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (ValueError, UnicodeError, RecursionError):
        raise WriteError('Use valid JSON without duplicate keys or non-finite values.') from None


def explicit_date(value, quotes):
    wanted = date.fromisoformat(value)
    patterns = [re.escape(value)]
    for month in {wanted.strftime('%B'), wanted.strftime('%b')}:
        patterns.extend([rf'{month}\.?\s+0?{wanted.day}(?:st|nd|rd|th)?[,]?\s+{wanted.year}',
                         rf'0?{wanted.day}\s+{month}\.?[,]?\s+{wanted.year}'])
    return any(re.search(r'(?<!\w)(?:' + '|'.join(patterns) + r')(?!\w)', quote, re.I) for quote in quotes)


def validate(data, context):
    from jsonschema import Draft202012Validator, FormatChecker
    schema = json.loads(SCHEMA_PATH.read_text())
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data))
    if errors:
        path = '.'.join(str(x) for x in errors[0].absolute_path) or 'root'
        # Do not echo untrusted payloads or parser internals in diagnostics/logs.
        raise WriteError('The AI draft does not match the output contract at ' + path[:160] + '.')
    if data['contextId'] != context['contextId'] or data['inputFingerprint'] != context['inputFingerprint']:
        raise WriteError('This draft belongs to a different context or fingerprint.', 409)
    sources = {s['sourceId']: s for s in context['sources']}
    def nonblank(value):
        if isinstance(value, str) and not value.strip():
            raise WriteError('AI text values cannot be blank.')
        if isinstance(value, dict):
            for item in value.values(): nonblank(item)
        if isinstance(value, list):
            for item in value: nonblank(item)
    nonblank(data)
    def unique(items):
        ids = [item['id'] for item in items]
        if len(ids) != len(set(ids)):
            raise WriteError('Task, issue and question identifiers must be unique.')
    for group in ('proposedTasks', 'missingInformation', 'conflicts', 'questionsForCustomer'):
        unique(data[group])
    reviewed = data['coverage']['reviewedSourceIds']
    unread_list = data['coverage']['unreadSources']
    unread = {x['sourceId']: x['reason'] for x in unread_list}
    if len(unread) != len(unread_list) or set(reviewed) & set(unread) or set(reviewed) | set(unread) != set(sources):
        raise WriteError('Coverage must account for every source exactly once.')
    for sid in reviewed:
        if sources[sid]['status'] != 'delivered':
            raise WriteError('An undelivered or truncated source cannot be claimed as fully reviewed.')
    for sid, reason in unread.items():
        expected = sources[sid]['status']
        if reason != ('not_reviewed' if expected == 'delivered' else expected):
            raise WriteError('Unread coverage does not match the prepared source inventory.')
    def source_ids(ids):
        if not ids or set(ids) - set(reviewed):
            raise WriteError('Cited sources must be delivered and declared reviewed.')
    def evidence(items):
        quotes = []
        for item in items:
            sid, quote = item['sourceId'], item['quote']
            source_ids([sid])
            if quote not in sources[sid]['text']:
                raise WriteError('An evidence quote does not occur exactly in its cited source.')
            quotes.append(quote)
        return quotes
    for task in data['proposedTasks']:
        source_ids(task['sourceIds'])
    issue_ids = set()
    for issue in data['missingInformation']:
        source_ids(issue['reviewedSourceIds'])
        if issue['materiality'] == 'blocking':
            issue_ids.add(issue['id'])
            if unread:
                raise WriteError('Review all references before declaring information definitively missing.')
    for conflict in data['conflicts']:
        evidence(conflict['evidence'])
        issue_ids.add(conflict['id'])
    for question in data['questionsForCustomer']:
        if unread or set(question['issueIds']) - issue_ids:
            raise WriteError('Questions must address material unresolved issues after complete source review.')
    proposed = set()
    for item in data['fieldProposals']:
        field = item['field']
        if field in proposed or field not in context['allowedFieldProposals'] or not context['fieldDefinitions'][field]['isBlank']:
            raise WriteError('Propose a field only once, and only for an allowed blank destination.')
        proposed.add(field)
        quotes = evidence(item['evidence'])
        if field == 'taskType':
            definition = context['fieldDefinitions'][field]
            if set(item['value']) - set(definition['options']) or (not definition['multiple'] and len(item['value']) != 1):
                raise WriteError('Use the exact permitted native task type choices.')
        if field == 'requestedDueDate' and not explicit_date(item['value'], quotes):
            raise WriteError('A requested date proposal needs an explicit absolute date in its evidence; relative or ambiguous dates require clarification.')
    return data
