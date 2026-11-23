"""Department suggestions from explicit source fields, never guessed organizations."""
import re

GROUP_COLUMNS = ('Owner Group', 'Group / department', 'Requestor Group', 'Requestor group / department', 'Department')

def department_value(cells, display):
    for title in GROUP_COLUMNS:
        value = display(cells.get(title, {})).strip()
        if value:
            return value
    # This is the exact label written by this portal's intake serializer.
    match = re.search(r'(?:^|\n\n)Requestor group / department:\n([^\n]+)', display(cells.get('Additional Details', {})))
    return match[1].strip() if match else ''

def department_options(sheet):
    titles = {c['id']: c.get('title') for c in sheet.get('columns', [])}
    values = {v.strip() for c in sheet.get('columns', []) if c.get('title') in GROUP_COLUMNS
              for v in c.get('options', []) if isinstance(v, str) and v.strip()}
    for row in sheet.get('rows', []):
        cells = {titles.get(c['columnId']): c for c in row.get('cells', [])}
        value = department_value(cells, lambda c: str(c.get('displayValue', c.get('value', '')) or ''))
        if value: values.add(value)
    return sorted(values, key=str.casefold)
