"""Per-identity tutorial preferences. No source reads, job writes or role changes."""
from datetime import datetime, timezone
from backend.dev_store import WriteError


def now():
    return datetime.now(timezone.utc).isoformat()


class Onboarding:
    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def tracks(kind):
        return ['requester'] if kind == 'requester' else ['designer', 'coordinator']

    def read(self, principal, kind, default):
        with self.runtime.db() as db:
            row = db.execute('SELECT status,track,lesson,completed_at FROM portal_tutorials WHERE principal=?', (principal,)).fetchone()
        return {'seen': bool(row), 'status': row[0] if row else 'new',
                'track': row[1] if row else default, 'lesson': row[2] if row else 0,
                'completedAt': row[3] if row else None, 'tracks': self.tracks(kind)}

    def write(self, principal, kind, default, body):
        if (not isinstance(body, dict) or set(body) - {'action','track','lesson'}
                or body.get('action') not in ('claim','progress','dismiss','complete')):
            raise WriteError('Choose a valid tutorial action.')
        track, lesson = body.get('track', default), body.get('lesson', 0)
        if track not in self.tracks(kind) or type(lesson) is not int or not 0 <= lesson <= 40:
            raise WriteError('Choose an available tutorial and lesson.')
        at = now()
        with self.runtime.db() as db:
            db.execute('BEGIN IMMEDIATE')
            inserted = db.execute('INSERT OR IGNORE INTO portal_tutorials VALUES (?,?,?,?,?,?,NULL)',
                                  (principal, at, 'shown', track, lesson, at)).rowcount == 1
            if body['action'] != 'claim':
                status = {'progress':'in_progress','dismiss':'dismissed','complete':'completed'}[body['action']]
                db.execute('UPDATE portal_tutorials SET status=?,track=?,lesson=?,updated_at=?,completed_at=CASE WHEN ?=\'completed\' THEN ? ELSE completed_at END WHERE principal=?',
                           (status,track,lesson,at,status,at,principal))
        return {**self.read(principal,kind,default), 'autoStart': inserted and body['action']=='claim'}
