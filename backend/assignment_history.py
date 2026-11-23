"""Private assignment receipts and timestamps. No native API or notification sender."""
import hashlib
import json
import uuid

DDL = (
    '''CREATE TABLE IF NOT EXISTS portal_assignment_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sheet_id TEXT NOT NULL, operation_key TEXT NOT NULL,
        row_id TEXT, job_id TEXT, state TEXT NOT NULL CHECK(state IN ('pending','confirmed')),
        action TEXT NOT NULL, generation TEXT NOT NULL, at TEXT NOT NULL,
        actor_json TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
        reason TEXT NOT NULL, UNIQUE(sheet_id,operation_key))''',
    'CREATE INDEX IF NOT EXISTS portal_assignment_row ON portal_assignment_events(sheet_id,row_id,event_id)',
)


def initialize(db):
    for sql in DDL:
        db.execute(sql)


def snapshot(project):
    p=project or {}
    return {k:p.get(k,'') for k in ('requestedDesigner','response','stage','nativeStatus')}


def details(db, sheet_id, project):
    rows=db.execute('SELECT action,generation,at,actor_json,before_json,after_json,reason,state '
        'FROM portal_assignment_events WHERE sheet_id=? AND row_id=? ORDER BY event_id DESC LIMIT 100',
        (sheet_id,project['_rowId'])).fetchall()
    confirmed=[r for r in rows if r[7]=='confirmed']
    latest=json.loads(confirmed[0][5]) if confirmed else {}
    matches=bool(latest and all(project.get(k,'')==latest.get(k,'') for k in ('requestedDesigner','response')))
    current={k:latest.get(k) if matches else None for k in ('offeredAt','acceptedAt','respondedAt','completedAt')}
    current['generation']=confirmed[0][1] if matches else 'untracked-'+hashlib.sha256(json.dumps([project['_rowId'],snapshot(project)],sort_keys=True).encode()).hexdigest()[:24]
    current['tracked']=matches
    current['history']=[{'action':r[0],'generation':r[1],'at':r[2],'actor':json.loads(r[3]),
        'before':json.loads(r[4]),'after':json.loads(r[5]),'reason':r[6],'confirmed':r[7]=='confirmed'} for r in rows]
    return current


def prepare(db, sheet_id, key, project, action, after, actor, at, reason=''):
    before=snapshot(project)
    previous=details(db,sheet_id,project) if project else {}
    fresh=action in ('offer','reassign','claim','create-self-assigned')
    generation=str(uuid.uuid4()) if fresh else previous.get('generation') or str(uuid.uuid4())
    state={**after,**{k:previous.get(k) for k in ('offeredAt','acceptedAt','respondedAt','completedAt')}}
    if fresh:
        state.update(offeredAt=at,acceptedAt=None,respondedAt=None,completedAt=None)
    if action in ('accept','claim','create-self-assigned'):
        state.update(acceptedAt=at,respondedAt=at)
    elif action=='decline':
        state.update(respondedAt=at,acceptedAt=None)
    if after.get('stage')=='Completed' and not state.get('completedAt'):
        state['completedAt']=at
    db.execute('INSERT INTO portal_assignment_events (sheet_id,operation_key,row_id,job_id,state,action,generation,at,actor_json,before_json,after_json,reason) '
        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (sheet_id,key,(project or {}).get('_rowId'),(project or {}).get('id'),'pending',action,generation,at,
         json.dumps(actor),json.dumps(before),json.dumps(state),reason))


def confirm(db, sheet_id, key, result, row_id=None):
    db.execute("UPDATE portal_assignment_events SET state='confirmed',row_id=COALESCE(row_id,?),job_id=COALESCE(?,job_id) WHERE sheet_id=? AND operation_key=?",
        (row_id,result.get('jobId'),sheet_id,key))
