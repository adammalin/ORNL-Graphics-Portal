"""Stage 1 browser-agent contexts and immutable drafts; no native mutations."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets

try:
    from backend.ai_context import build, inventory, canonical, fingerprint
    from backend.ai_validation import validate
    from backend.dev_store import WriteError
    from backend.job_service import WRITABLE_ACCESS, KEY
except ImportError:
    from ai_context import build, inventory, canonical, fingerprint
    from ai_validation import validate
    from dev_store import WriteError
    from job_service import WRITABLE_ACCESS, KEY

ROOT = Path(__file__).resolve().parents[1]


def settings(config):
    value = config.value.get('ai') or {}
    if not isinstance(value, dict):
        raise WriteError('Invalid AI pilot configuration.', 503)
    jobs = value.get('jobIds', [])
    if not isinstance(jobs, list) or len(jobs) > 20 or any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', x) for x in jobs) or len(jobs) != len(set(jobs)):
        raise WriteError('Allowlist at most twenty specific synthetic DEV job IDs for AI.', 503)
    return value.get('browserPilotEnabled') is True, frozenset(jobs)


def now():
    return datetime.now(timezone.utc).isoformat()


class AiService:
    def __init__(self, runtime):
        self.runtime = runtime

    def flags(self):
        enabled, jobs = settings(self.runtime.active_config())
        return {'aiContext': bool(enabled and jobs), 'aiDrafts': bool(enabled and jobs)}

    def _scope(self, sid, job, enabled=True, write=False, review=False):
        # Reuse the exact session, native-source and object policy as job routes.
        ctx = self.runtime.jobs._fresh(sid)
        project = self.runtime.jobs._project(ctx, job)
        on, jobs = settings(self.runtime.active_config())
        allowed = bool(on and job in jobs and project.get('synthetic') is True and not project.get('readOnly'))
        if enabled and not allowed:
            raise WriteError('AI is disabled for this job. Only explicitly selected synthetic DEV jobs are eligible.', 403)
        if write and ctx.reader.sheet.get('accessLevel') not in WRITABLE_ACCESS:
            raise WriteError('This source account is read-only; it cannot save AI drafts.', 403)
        if review and not self.runtime.jobs._permissions(ctx, project)['edit']:
            raise WriteError('Only a currently authorized job editor can review a brief.', 403)
        return ctx, project, allowed

    def _stable(self, sid, ctx, project, write=False, review=False):
        self.runtime.jobs._ensure_current(sid, ctx)
        current, latest, _ = self._scope(sid, project['id'], write=write, review=review)
        if current.principal != ctx.principal or latest['_rowId'] != project['_rowId'] or latest['revision'] != project['revision']:
            raise WriteError('context_changed: source or authorization changed; prepare fresh job context.', 409)
        return current

    def _materialize(self, sid, ctx, project, selected):
        result = build(ctx.reader, project, selected,
            lambda attachment: self.runtime.jobs.attachment(sid, project['id'], attachment))
        self._stable(sid, ctx, project)
        return result

    def _context(self, ctx, project, context_id):
        with self.runtime.db() as db:
            row = db.execute('SELECT payload_json FROM ai_intake_contexts WHERE context_id=? AND sheet_id=? AND row_id=? AND job_id=?',
                (context_id, ctx.reader.sheet_id, project['_rowId'], project['id'])).fetchone()
        if not row:
            raise WriteError('This AI context is not available for this job.', 404)
        return json.loads(row[0])

    def _check_fresh(self, sid, ctx, project, context):
        if context['sourceRevision'] != project['revision']:
            raise WriteError('This AI context is stale. Prepare a new one; original job data was preserved.', 409)
        actual = self._materialize(sid, ctx, project, context['selectedReferenceIds'])
        if actual['inputFingerprint'] != context['inputFingerprint']:
            raise WriteError('Reference contents or relevant inputs changed. Prepare a new context.', 409)

    def _is_stale(self, sid, ctx, project, context):
        try:
            self._check_fresh(sid, ctx, project, context)
            return False
        except WriteError as error:
            if error.status == 409:
                return True
            raise

    def _operation(self, db, ctx, action, key, payload):
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise WriteError('A valid operation identifier is required.')
        digest = fingerprint(payload)
        identity = (ctx.reader.sheet_id, ctx.principal.user_id, action, key)
        prior = db.execute('SELECT payload_hash,result_json FROM ai_operations WHERE sheet_id=? AND user_id=? AND action=? AND operation_key=?', identity).fetchone()
        if prior:
            if prior[0] != digest:
                raise WriteError('This operation key was already used for different content.', 409)
            return identity, digest, json.loads(prior[1])
        return identity, digest, None

    @staticmethod
    def _receipt(db, identity, digest, result):
        db.execute('INSERT INTO ai_operations VALUES (?,?,?,?,?,?,?)', (*identity, digest, canonical(result), now()))

    def prepare(self, sid, job, key, body):
        if not isinstance(body, dict) or set(body) != {'selectedReferenceIds'}:
            raise WriteError('Choose references for exactly this job.')
        with self.runtime.sheet_lock:
            ctx, project, _ = self._scope(sid, job)
            payload = {'job': job, 'selectedReferenceIds': body['selectedReferenceIds']}
            with self.runtime.db() as db:
                _, _, prior = self._operation(db, ctx, 'prepare', key, payload)
            if prior:
                return self.get_context(sid, job, prior['contextId'])
            context = self._materialize(sid, ctx, project, body['selectedReferenceIds'])
            context['contextId'] = 'ctx_' + secrets.token_urlsafe(24)
            with self.runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                identity, digest, prior = self._operation(db, ctx, 'prepare', key, payload)
                self._stable(sid, ctx, project)
                if not prior:
                    db.execute('INSERT INTO ai_intake_contexts VALUES (?,?,?,?,?,?,?,?,?)',
                        (context['contextId'], ctx.reader.sheet_id, project['_rowId'], job, '1.0',
                         project['revision'], context['inputFingerprint'], context['preparedAt'], canonical(context)))
                    self._receipt(db, identity, digest, {'contextId': context['contextId']})
            self.runtime.audit(ctx.principal, 'ai-context', job, 'saved')
            return self.get_context(sid, job, context['contextId'])

    def get_context(self, sid, job, context_id):
        with self.runtime.sheet_lock:
            ctx, project, _ = self._scope(sid, job)
            context = self._context(ctx, project, context_id)
            stale = self._is_stale(sid, ctx, project, context)
            self._stable(sid, ctx, project)
            return {'context': context, 'isStale': stale,
                    'instructions': (ROOT / 'docs/prompts/intake-analysis-v1.md').read_text(),
                    'outputSchema': json.loads((ROOT / 'docs/contracts/intake-analysis.schema.json').read_text())}

    def save_draft(self, sid, job, key, analysis):
        with self.runtime.sheet_lock:
            ctx, project, _ = self._scope(sid, job, write=True)
            if not isinstance(analysis, dict) or not isinstance(analysis.get('contextId'), str):
                raise WriteError('Import a contracted AI analysis object.')
            context = self._context(ctx, project, analysis['contextId'])
            validate(analysis, context)
            payload = {'job': job, 'analysis': analysis}
            with self.runtime.db() as db:
                _, _, prior = self._operation(db, ctx, 'draft', key, payload)
            if prior:
                return self.get_draft(sid, job, prior['draftId'])
            self._check_fresh(sid, ctx, project, context)
            draft_id = 'draft_' + secrets.token_urlsafe(24)
            with self.runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                identity, digest, prior = self._operation(db, ctx, 'draft', key, payload)
                self._stable(sid, ctx, project, write=True)
                if not prior:
                    version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM ai_analysis_drafts WHERE context_id=?', (context['contextId'],)).fetchone()[0]
                    db.execute('INSERT INTO ai_analysis_drafts VALUES (?,?,?,?,?,?,?)',
                        (draft_id, context['contextId'], version, 'needs_review', ctx.principal.user_id, now(), canonical(analysis)))
                    self._receipt(db, identity, digest, {'draftId': draft_id})
            self.runtime.audit(ctx.principal, 'ai-draft', job, 'saved')
            return self.get_draft(sid, job, draft_id)

    def _draft(self, ctx, project, draft_id):
        with self.runtime.db() as db:
            row = db.execute('SELECT d.draft_id,d.context_id,d.version,d.submitted_at,d.output_json FROM ai_analysis_drafts d JOIN ai_intake_contexts c ON c.context_id=d.context_id WHERE d.draft_id=? AND c.sheet_id=? AND c.row_id=? AND c.job_id=?',
                (draft_id, ctx.reader.sheet_id, project['_rowId'], project['id'])).fetchone()
            review = db.execute('SELECT decision,reviewed_at,selection_json FROM ai_draft_reviews WHERE draft_id=? ORDER BY reviewed_at DESC,rowid DESC LIMIT 1', (draft_id,)).fetchone() if row else None
        if not row:
            raise WriteError('This AI draft is not available for this job.', 404)
        return {'draftId': row[0], 'contextId': row[1], 'version': row[2], 'submittedAt': row[3],
                'analysis': json.loads(row[4]), 'status': review[0] if review else 'needs_review',
                'review': {'decision': review[0], 'at': review[1], **json.loads(review[2])} if review else None}

    def get_draft(self, sid, job, draft_id):
        with self.runtime.sheet_lock:
            ctx, project, _ = self._scope(sid, job)
            result = self._draft(ctx, project, draft_id)
            context = self._context(ctx, project, result['contextId'])
            result['isStale'] = self._is_stale(sid, ctx, project, context)
            self._stable(sid, ctx, project)
            return result

    def review(self, sid, job, draft_id, key, body):
        if not isinstance(body, dict) or set(body) - {'decision', 'note'} or body.get('decision') not in ('accepted', 'rejected') or not isinstance(body.get('note', ''), str) or len(body.get('note', '')) > 1000:
            raise WriteError('Review a brief as accepted or rejected, with an optional short note.')
        with self.runtime.sheet_lock:
            ctx, project, _ = self._scope(sid, job, write=True, review=True)
            draft = self._draft(ctx, project, draft_id)
            context = self._context(ctx, project, draft['contextId'])
            payload = {'job': job, 'draftId': draft_id, **body}
            with self.runtime.db() as db:
                _, _, prior = self._operation(db, ctx, 'review', key, payload)
            if prior:
                return self.get_draft(sid, job, draft_id)
            # Stale versions may be rejected, never accepted as the current brief.
            if body['decision'] == 'accepted':
                self._check_fresh(sid, ctx, project, context)
            with self.runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                identity, digest, prior = self._operation(db, ctx, 'review', key, payload)
                self._stable(sid, ctx, project, write=True, review=True)
                if not prior:
                    review_id = 'review_' + secrets.token_urlsafe(24)
                    db.execute('INSERT INTO ai_draft_reviews VALUES (?,?,?,?,?,?)',
                        (review_id, draft_id, ctx.principal.user_id, now(), body['decision'], canonical({'note': body.get('note', '')})))
                    self._receipt(db, identity, digest, {'reviewId': review_id, 'draftId': draft_id})
            self.runtime.audit(ctx.principal, 'ai-review', job, body['decision'])
            return self.get_draft(sid, job, draft_id)

    def status(self, sid, job, offset=0):
        if not isinstance(offset, int) or offset < 0 or offset > 10000:
            raise WriteError('Invalid history offset.')
        with self.runtime.sheet_lock:
            ctx, project, enabled = self._scope(sid, job, enabled=False)
            if not enabled:
                return {'enabled': False}
            writable = ctx.reader.sheet.get('accessLevel') in WRITABLE_ACCESS
            with self.runtime.db() as db:
                context = db.execute('SELECT context_id FROM ai_intake_contexts WHERE sheet_id=? AND row_id=? AND job_id=? ORDER BY prepared_at DESC,rowid DESC LIMIT 1',
                    (ctx.reader.sheet_id, project['_rowId'], job)).fetchone()
                rows = db.execute('SELECT d.draft_id,d.version,d.submitted_at FROM ai_analysis_drafts d JOIN ai_intake_contexts c ON c.context_id=d.context_id WHERE c.sheet_id=? AND c.row_id=? AND c.job_id=? ORDER BY d.submitted_at DESC,d.rowid DESC LIMIT 11 OFFSET ?',
                    (ctx.reader.sheet_id, project['_rowId'], job, offset)).fetchall()
                accepted = db.execute('''SELECT r.draft_id FROM ai_draft_reviews r
                    JOIN ai_analysis_drafts d ON d.draft_id=r.draft_id
                    JOIN ai_intake_contexts c ON c.context_id=d.context_id
                    WHERE c.sheet_id=? AND c.row_id=? AND c.job_id=? AND r.decision='accepted'
                    AND r.review_id=(SELECT r2.review_id FROM ai_draft_reviews r2 WHERE r2.draft_id=r.draft_id ORDER BY r2.reviewed_at DESC,r2.rowid DESC LIMIT 1)
                    ORDER BY r.reviewed_at DESC,r.rowid DESC LIMIT 1''',
                    (ctx.reader.sheet_id, project['_rowId'], job)).fetchone()
            latest = self._draft(ctx, project, rows[0][0]) if rows else None
            if latest:
                latest['isStale'] = self._is_stale(sid, ctx, project, self._context(ctx, project, latest['contextId']))
            accepted_draft = self._draft(ctx, project, accepted[0]) if accepted else None
            if accepted_draft:
                accepted_draft['isStale'] = self._is_stale(sid, ctx, project, self._context(ctx, project, accepted_draft['contextId']))
            self._stable(sid, ctx, project)
            return {'enabled': True, 'jobId': job, 'canSaveDraft': writable,
                'canReview': bool(writable and self.runtime.jobs._permissions(ctx, project)['edit']),
                'latestContextId': context[0] if context else None, 'latestDraft': latest,
                'acceptedBrief': accepted_draft, 'history': [{'draftId': r[0], 'version': r[1], 'at': r[2]} for r in rows[:10]],
                'hasMore': len(rows) > 10, 'offset': offset,
                'limits': {'draftBytes': 256 * 1024, 'selectedReferences': 10, 'contextCharacters': 80000},
                'businessFieldApply': False, 'nativePublication': False}

    def references(self, sid, job, offset=0):
        if not isinstance(offset, int) or offset < 0 or offset > 10000:
            raise WriteError('Invalid reference offset.')
        with self.runtime.sheet_lock:
            ctx, project, _ = self._scope(sid, job)
            refs = inventory(ctx.reader, project)
            self._stable(sid, ctx, project)
            return {'references': [{k: v for k, v in ref.items() if k not in ('file', 'attachmentId')} for ref in refs[offset:offset+50]],
                    'total': len(refs), 'offset': offset, 'hasMore': offset + 50 < len(refs)}
