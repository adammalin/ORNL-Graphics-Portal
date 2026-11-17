"""Bounded reference extraction. No network, OCR, embedded code or active rendering."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

LIMIT = 50000
VERSION = 'bounded-text-pdf-1.0.1'


def extract(content, mime, name):
    digest = hashlib.sha256(content).hexdigest()
    result = {'contentHash': digest, 'extractorVersion': VERSION, 'status': 'unsupported', 'text': ''}
    # Smartsheet returns media-type parameters on real attachments, e.g.
    # text/plain;charset=UTF-8. Parameters do not change the media type.
    mime = str(mime).partition(';')[0].strip().lower()
    # Octet-stream is accepted only with .txt plus strict UTF-8/control checks,
    # or an actual PDF signature and .pdf. File content is always inert text.
    plain = mime == 'text/plain' or (mime == 'application/octet-stream' and name.lower().endswith('.txt'))
    pdf = mime == 'application/pdf' or (mime == 'application/octet-stream' and name.lower().endswith('.pdf') and content.startswith(b'%PDF-'))
    if plain:
        try:
            text = content.decode('utf-8-sig')
            if any(ord(c) < 32 and c not in '\n\r\t' for c in text):
                return result
        except UnicodeError:
            return result
        result.update(text=text[:LIMIT], status='truncated' if len(text) > LIMIT else 'delivered')
        if not text.strip():
            result.update(status='unsupported', text='')
    elif pdf:
        try:
            reply = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--pdf'],
                input=content, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=9, check=False)
            if reply.returncode == 0 and len(reply.stdout) <= 400000:
                data = json.loads(reply.stdout)
                if data.get('status') in ('delivered', 'truncated', 'unsupported') and isinstance(data.get('text'), str) and len(data['text']) <= LIMIT:
                    result.update(data)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return result


def pdf_worker(content):
    # Parser runs outside the server process; CPU and address-space limits where
    # supported supplement the parent timeout and bounded input/output limits.
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    except (ValueError, OSError):
        pass
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted:
        return {'status': 'unsupported', 'text': ''}
    parts, length = [], 0
    truncated = len(reader.pages) > 40
    for n, page in enumerate(reader.pages[:40]):
        text = '[Page ' + str(n + 1) + ']\n' + page.extract_text(extraction_mode='plain')
        parts.append(text[:max(0, LIMIT - length)])
        length += len(text) + 2
        if length > LIMIT:
            truncated = True
            break
    text = '\n\n'.join(parts)[:LIMIT]
    # A page label is not extracted document content (e.g. scanned PDF).
    actual = '\n'.join(__import__('re').sub(r'\[Page \d+\]', '', p) for p in parts).strip()
    if not actual:
        return {'status': 'unsupported', 'text': ''}
    return {'status': 'truncated' if truncated else 'delivered', 'text': text}


if __name__ == '__main__':
    try:
        content = sys.stdin.buffer.read(30 * 1024 * 1024 + 1)
        if len(content) > 30 * 1024 * 1024:
            raise ValueError()
        print(json.dumps(pdf_worker(content)))
    except Exception:
        print(json.dumps({'status': 'unsupported', 'text': ''}))
