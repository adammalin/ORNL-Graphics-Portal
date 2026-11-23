"""Native organization fields and deterministic, host-configured coordination."""
import re

ORGANIZATION_FIELDS = {
    'directorate': 'Owner Directorate',
    'division': 'Owner Division/Office/Facility',
    'requestorGroup': 'Owner Group',
}


def choices(sheet):
    columns = {c['title']: c for c in sheet.get('columns', [])}
    return {key: list(columns.get(title, {}).get('options', []))
            for key, title in ORGANIZATION_FIELDS.items() if key != 'requestorGroup'}


def validate_policy(policy, eligible=None):
    if policy is None:
        return None
    if not isinstance(policy, dict) or set(policy) != {'version', 'managers', 'divisionOverrides', 'directorates', 'default'} or type(policy['version']) is not int or policy['version'] != 1:
        raise ValueError('Organization routing requires the supported, explicit policy schema.')
    managers = policy['managers']
    if not isinstance(managers, dict) or not 1 <= len(managers) <= 20 or policy['default'] not in managers:
        raise ValueError('Configure named routing managers and one default.')
    for key, person in managers.items():
        if not isinstance(key, str) or not isinstance(person, dict) or set(person) != {'email', 'name'}:
            raise ValueError('Each routing manager needs an email and display name.')
        if not isinstance(person['email'], str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', person['email']) or not isinstance(person['name'], str) or not 0 < len(person['name']) <= 200:
            raise ValueError('Invalid coordinating manager contact.')
        if eligible is not None and person['email'] not in eligible:
            raise ValueError('Routing managers must be invited coordinators or admins.')
    for dimension in ('divisionOverrides', 'directorates'):
        entries = policy[dimension]
        if not isinstance(entries, list) or len(entries) > 50:
            raise ValueError('Invalid organization routing table.')
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'values', 'manager'} or entry['manager'] not in managers:
                raise ValueError('Every routing row needs a known manager.')
            if not isinstance(entry['values'], list) or not entry['values']:
                raise ValueError('Routing conditions must name their organization values.')
            for value in entry['values']:
                if not isinstance(value, str) or not value.strip() or len(value) > 4000 or value in seen:
                    raise ValueError('Organization routing contains duplicate or invalid conditions.')
                seen.add(value)
    return policy


def resolve(policy, directorate='', division=''):
    """Division overrides, then directorate, then exactly one fallback manager."""
    if policy is None:
        return None
    for dimension, value in (('divisionOverrides', division), ('directorates', directorate)):
        for entry in policy[dimension]:
            if value and value in entry['values']:
                return {**policy['managers'][entry['manager']], 'reason': 'division' if dimension == 'divisionOverrides' else 'directorate'}
    return {**policy['managers'][policy['default']], 'reason': 'coordination required' if not directorate else 'default'}
