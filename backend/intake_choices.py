"""Department suggestions from explicit source fields, never guessed organizations."""
import re

GROUP_COLUMNS = ('Group / department', 'Requestor Group', 'Requestor group / department', 'Department')

def department_value(cells, display):
    for title in GROUP_COLUMNS:
        value = display(cells.get(title, {})).strip()
        if value:
            return value
    # This is the exact label written by this portal's intake serializer.
    match = re.search(r'(?:^|\n\n)Requestor group / department:\n([^\n]+)', display(cells.get('Additional Details', {})))
    return match[1].strip() if match else ''

def department_options(sheet):
    return sorted({v.strip() for c in sheet.get('columns', []) if c.get('title') in GROUP_COLUMNS
                   for v in c.get('options', []) if isinstance(v, str) and v.strip()}, key=str.casefold)
