"""Opt-in employee intake policy. Pure calendar/routing rules; sends no mail."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from backend.dev_store import WriteError

SERVICES = {
    'photography': ('Photography', 'Photography', ['An event', 'People / portraits', 'A location or subject', 'Help me decide']),
    'video': ('Video production', 'Video Production', ['Filming', 'Editing', 'Filming and editing', 'Help me decide']),
    'web': ('Web', 'Web', ['A new page or site', 'An existing page update', 'An interactive tool', 'Help me decide']),
    'reproduction': ('Reproduction / printing', 'Reproduction', ['Handouts / copies', 'A booklet or publication', 'Other printed materials', 'Help me decide']),
    'poster': ('Poster / large-format printing', 'Reproduction', ['36 × 48 inches', '24 × 36 inches', 'A custom size', 'Help me decide']),
    'unsure': ('Help me choose services', 'Graphics coordination', [])
}
EXTRA_FIELDS = {'additionalServices', 'serviceDetails', 'eventDate'}

def calendar_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError('Use YYYY-MM-DD.')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('Use YYYY-MM-DD.')
    return parsed

def today_eastern():
    return datetime.now(ZoneInfo('America/New_York')).date()

def minimum_date(today, closed):
    current, count = today, 0
    for _ in range(3700):
        current += timedelta(days=1)
        if current.weekday() < 5 and current.isoformat() not in closed:
            count += 1
            if count == 2:
                return current
    raise ValueError('No open business day.')

def policy(config, *, staff=False):
    raw = config.value.get('staffIntakeRules' if staff else 'guidedIntake', {})
    if not isinstance(raw, dict) or raw.get('enabled') is not True:
        return None
    calendar = raw.get('calendar', {})
    try:
        if not isinstance(calendar, dict) or (calendar.get('approved') is not True and not (staff and calendar.get('testOnly') is True)):
            raise ValueError()
        closed = calendar.get('closedDates')
        if not isinstance(closed, list) or len(closed) > 800:
            raise ValueError()
        for value in closed:
            calendar_date(value)
        through = calendar_date(calendar.get('validThrough'))
        today = today_eastern()
        earliest = minimum_date(today, closed)
        if through < earliest:
            raise ValueError()
        label = calendar.get('label')
        if not isinstance(label, str) or not label.strip() or len(label) > 160:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        return {'enabled': True, 'ready': False, 'message': 'The approved holiday/closure calendar needs review before guided requests can be submitted.'}
    return {'enabled': True, 'ready': True, 'today': today.isoformat(), 'timezone': 'America/New_York',
            'earliest': earliest.isoformat(), 'closedDates': sorted(set(closed)),
            'validThrough': through.isoformat(), 'calendarLabel': label.strip(),
            'notificationsEnabled': False, 'testOnly': calendar.get('approved') is not True,
            'layout': raw.get('layout', 'guided'),
            'services': [{'id': k, 'label': v[0], 'team': v[1], 'choices': v[2]} for k, v in SERVICES.items()]}

def normalize(fields, config, check_date=True, *, staff=False, override_lead_time=False):
    """Return a native-compatible payload and a safe original-input snapshot."""
    if set(fields) & {'overrideLeadTime', 'override', 'canOverride'}:
        raise WriteError('Date overrides are not accepted as request fields.', 400)
    if override_lead_time and not staff:
        raise WriteError('Only verified Graphics staff may override minimum lead time.', 403)
    p = policy(config, staff=staff)
    if not p:
        if override_lead_time:
            raise WriteError('Staff lead-time rules are not configured.', 503)
        if set(fields) & EXTRA_FIELDS:
            raise WriteError('Guided intake is not enabled.', 400)
        return dict(fields), dict(fields)
    if not p['ready']:
        raise WriteError(p['message'], 503)
    try:
        due = calendar_date(fields.get('dueDate'))
    except (ValueError, TypeError):
        raise WriteError('Choose a valid requested delivery date.', 400) from None
    if check_date and override_lead_time and due.isoformat() < p['today']:
        raise WriteError('Choose today or a future date.', 400)
    if check_date and not override_lead_time and due.isoformat() < p['earliest']:
        raise WriteError('Allow at least two business days. Earliest requested delivery: ' + p['earliest'] + '.', 400)
    if check_date and due.isoformat() > p['validThrough']:
        raise WriteError('Choose a date within the approved holiday/closure calendar, through ' + p['validThrough'] + '.', 400)
    if check_date and (due.weekday() >= 5 or due.isoformat() in p['closedDates']):
        raise WriteError('Requested delivery must be an open business day, excluding weekends and holidays/closures.', 400)
    event = fields.get('eventDate', '')
    if not isinstance(event, str):
        raise WriteError('Choose a valid event date.', 400)
    if event:
        try:
            calendar_date(event)
        except (ValueError, TypeError):
            raise WriteError('Choose a valid event date.', 400) from None
    ids = fields.get('additionalServices', [])
    if not isinstance(ids, list) or len(ids) > len(SERVICES) or any(not isinstance(i, str) or i not in SERVICES for i in ids) or len(ids) != len(set(ids)):
        raise WriteError('Choose valid additional services.', 400)
    details = fields.get('serviceDetails', {})
    if not isinstance(details, dict) or set(details) - set(ids):
        raise WriteError('Include details only for selected additional services.', 400)
    cleaned = {}
    for sid in ids:
        detail = details.get(sid, {})
        if not isinstance(detail, dict) or set(detail) - {'kind', 'quantity', 'notes'}:
            raise WriteError('Invalid additional service details.', 400)
        kind, notes = detail.get('kind', ''), detail.get('notes', '')
        if sid != 'unsure' and kind not in SERVICES[sid][2]:
            raise WriteError('Choose the type of support for ' + SERVICES[sid][0] + '.', 400)
        if not isinstance(notes, str) or len(notes) > 500:
            raise WriteError('Keep each service note under 500 characters.', 400)
        cleaned[sid] = {'kind': kind if sid != 'unsure' else '', 'notes': notes.strip()}
        if sid in ('reproduction', 'poster'):
            qty = detail.get('quantity', '')
            if isinstance(qty, bool) or not isinstance(qty, (str, int)) or not str(qty).isdigit() or not 1 <= int(qty) <= 100000:
                raise WriteError('Enter a whole printing quantity from 1 to 100,000.', 400)
            cleaned[sid]['quantity'] = str(int(qty))
    snapshot = {k: v for k, v in fields.items() if k not in EXTRA_FIELDS}
    snapshot.update(additionalServices=ids, serviceDetails=cleaned, eventDate=event)
    native = {k: v for k, v in fields.items() if k not in EXTRA_FIELDS}
    notes = native.get('notes', '')
    if not isinstance(notes, str):
        raise WriteError('Notes must be text.', 400)
    extra = []
    if event:
        extra.append('Event date (separate from delivery): ' + event)
    groups = {'Graphics coordination': ['Graphics project coordination']}
    for sid in ids:
        label, team, _ = SERVICES[sid]
        d = cleaned[sid]
        groups.setdefault(team, []).append(label)
        extra.append(label + ': ' + ' | '.join(v for v in [d['kind'], ('Quantity ' + d['quantity']) if 'quantity' in d else '', d['notes']] if v))
    extra.append('Service routing preview (no notifications sent by this feature):\n' + '\n'.join(team + ' — ' + ', '.join(labels) for team, labels in groups.items()))
    native['notes'] = notes + ('\n\n' if notes else '') + '\n'.join(extra)
    # The native Additional Details cell has an existing combined 4,000-character cap.
    return native, snapshot
