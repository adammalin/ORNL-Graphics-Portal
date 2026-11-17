"""Private migrations preserve old state and fail atomically."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.ai_repository import migrate_private_state, SCHEMA_VERSION
from backend.dev_store import WriteError


class PrivateMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'state.sqlite3'

    def tearDown(self):
        self.tmp.cleanup()

    def test_additive_idempotent_migration_preserves_legacy_receipts_and_identities(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE bindings (invite TEXT PRIMARY KEY, user_id TEXT NOT NULL)')
            db.execute('INSERT INTO bindings VALUES (?,?)', ('tester@example.org', '123'))
            db.execute('CREATE TABLE operations (sheet TEXT, key TEXT, state TEXT, result TEXT)')
            db.execute('INSERT INTO operations VALUES (?,?,?,?)',
                       ('123', 'existing-receipt', 'done', '{"jobId":"SYNTHETIC"}'))
        self.assertEqual(migrate_private_state(self.path), SCHEMA_VERSION)
        self.assertEqual(migrate_private_state(self.path), SCHEMA_VERSION)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT * FROM bindings').fetchall(), [('tester@example.org', '123')])
            self.assertEqual(db.execute('SELECT * FROM operations').fetchall(),
                             [('123', 'existing-receipt', 'done', '{"jobId":"SYNTHETIC"}')])
            self.assertEqual(db.execute('SELECT version FROM portal_schema_migrations').fetchall(), [(1,), (2,), (3,)])
            for table in ['ai_intake_contexts', 'ai_analysis_drafts', 'ai_draft_reviews']:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_unknown_schema_version_stops_without_downgrading(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE portal_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT)')
            db.execute("INSERT INTO portal_schema_migrations VALUES (999, 'synthetic')")
        with self.assertRaises(WriteError) as error:
            migrate_private_state(self.path)
        self.assertEqual(error.exception.status, 503)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT version FROM portal_schema_migrations').fetchall(), [(999,)])
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='ai_intake_contexts'").fetchall(), [])

    def test_failed_migration_rolls_back_new_tables_and_version_receipt(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE ai_analysis_drafts (old_data TEXT)')
            db.execute("INSERT INTO ai_analysis_drafts VALUES ('preserve')")
        with self.assertRaises(sqlite3.OperationalError):
            migrate_private_state(self.path)
        with sqlite3.connect(self.path) as db:
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(names, {'ai_analysis_drafts'})
            self.assertEqual(db.execute('SELECT * FROM ai_analysis_drafts').fetchall(), [('preserve',)])
