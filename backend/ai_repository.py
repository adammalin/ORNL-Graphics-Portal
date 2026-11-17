"""Versioned private-state foundation. AI storage has no public write API yet."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

try:
    from backend.dev_store import WriteError
except ImportError:
    from dev_store import WriteError


SCHEMA_VERSION = 3
MIGRATIONS = (
    (1, (
        """CREATE TABLE ai_intake_contexts (
            context_id TEXT PRIMARY KEY,
            sheet_id TEXT NOT NULL,
            row_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL,
            prepared_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )""",
        """CREATE TABLE ai_analysis_drafts (
            draft_id TEXT PRIMARY KEY,
            context_id TEXT NOT NULL REFERENCES ai_intake_contexts(context_id),
            version INTEGER NOT NULL CHECK(version > 0),
            status TEXT NOT NULL,
            submitted_by TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            output_json TEXT NOT NULL,
            UNIQUE(context_id, version)
        )""",
        """CREATE TABLE ai_draft_reviews (
            review_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES ai_analysis_drafts(draft_id),
            reviewer_id TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            decision TEXT NOT NULL,
            selection_json TEXT NOT NULL
        )""",
        'CREATE INDEX ai_context_job ON ai_intake_contexts(sheet_id, row_id)',
    )),
    (2, (
        '''CREATE TABLE ai_operations (
            sheet_id TEXT NOT NULL, user_id TEXT NOT NULL,
            action TEXT NOT NULL, operation_key TEXT NOT NULL,
            payload_hash TEXT NOT NULL, result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(sheet_id, user_id, action, operation_key)
        )''',
        'CREATE INDEX ai_drafts_context ON ai_analysis_drafts(context_id, version)',
        'CREATE INDEX ai_reviews_draft ON ai_draft_reviews(draft_id, reviewed_at)',
    )),
    (3, (
        '''CREATE TABLE portal_tutorials (
            principal TEXT PRIMARY KEY, first_shown_at TEXT NOT NULL,
            status TEXT NOT NULL, track TEXT NOT NULL, lesson INTEGER NOT NULL,
            updated_at TEXT NOT NULL, completed_at TEXT
        )''',
        '''CREATE TABLE employee_request_snapshots (
            receipt TEXT PRIMARY KEY, row_id TEXT NOT NULL, fields_json TEXT NOT NULL
        )''',
        '''CREATE TABLE employee_request_resources (
            receipt TEXT NOT NULL, attachment_id TEXT NOT NULL,
            category TEXT NOT NULL, content_sha256 TEXT NOT NULL,
            visible INTEGER NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(receipt, attachment_id)
        )''',
        '''CREATE TABLE employee_resource_events (
            event_id TEXT PRIMARY KEY, receipt TEXT NOT NULL, attachment_id TEXT NOT NULL,
            action TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL
        )''',
    )),
)


def migrate_private_state(path):
    """Add empty tables transactionally, preserving all legacy state and receipts.

    No Smartsheet connection is used. Unknown/newer migration versions fail
    closed; migrations never drop, rename or rewrite existing tables.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    with sqlite3.connect(str(path), timeout=15) as db:
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS portal_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
        applied = {row[0] for row in db.execute('SELECT version FROM portal_schema_migrations')}
        known = {version for version, _ in MIGRATIONS}
        if applied - known:
            raise WriteError('Private state uses an unsupported schema version. Use a compatible application release.', 503)
        for version, statements in MIGRATIONS:
            if version in applied:
                continue
            for statement in statements:
                db.execute(statement)
            db.execute('INSERT INTO portal_schema_migrations VALUES (?, ?)',
                       (version, datetime.now(timezone.utc).isoformat()))
    return SCHEMA_VERSION
