"""Coordinator reporting over the existing approved, visible DEV selection."""
from collections import Counter
from datetime import date, datetime, timedelta
import copy
import hashlib
import json
import secrets
import time
from zoneinfo import ZoneInfo
from urllib.parse import quote

from backend.dev_store import WriteError
from backend.server import url_value

LEVELS = ['', 'Routine', 'High', 'Strategic']
OUTCOMES = ['', 'Completed', 'Cancelled']
PROFILE_FIELDS = {'directorate':160,'division':160,'impactLevel':20,'impactCategory':120,
                  'impactJustification':1000,'impactStatement':1200,'intendedOutcome':1200,
                  'observedOutcome':1200,'evidenceUrl':1000,'disposition':20}
SECTIONS = {'summary':'Executive summary','monthly':'Monthly activity','types':'Types of work',
            'stages':'Current project stages','designers':'Designer activity',
            'directorates':'Directorates served','impact':'Impact highlights',
            'quality':'Data coverage and definitions','records':'Project register'}
PRESETS = {'executive':['summary','monthly','types','directorates','impact','quality'],
           'operations':['summary','monthly','stages','types','designers','directorates','quality','records'],
           'impact':['summary','directorates','types','impact','quality']}


def iso_date(value):
    try:return date.fromisoformat(value) if isinstance(value,str) and len(value)==10 else None
    except ValueError:return None


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def clean_filters(body):
    if not isinstance(body,dict) or set(body)-{'start','end','source','designer','taskType','directorate','impactLevel','stage'}:
        raise WriteError('Choose valid report filters.')
    today=datetime.now(ZoneInfo('America/New_York')).date()
    result={'start':body.get('start',today.replace(month=1,day=1).isoformat()),'end':body.get('end',today.isoformat()),
            **{k:body.get(k,'') for k in ['designer','taskType','directorate','impactLevel','stage']},'source':body.get('source','all')}
    start,end=iso_date(result['start']),iso_date(result['end'])
    if not start or not end or not (1900<=start.year<=end.year<=2100) or start>end or (end-start).days>5*366:
        raise WriteError('Choose a report period of up to five years between 1900 and 2100, with start before end.')
    if any(not isinstance(v,str) or len(v)>200 for v in result.values()):raise WriteError('A report filter is invalid.')
    if result['source'] not in ('all','test','copied') or result['impactLevel'] not in LEVELS:
        raise WriteError('Choose an available source or impact level.')
    return result


def completed(p):
    meta=p.get('reporting',{})
    if meta.get('disposition')=='Cancelled' or p.get('sourceStatus','').casefold() in ('cancelled','canceled'):return False
    if p['stage']=='Archived':
        return bool(iso_date(p.get('completedDate')) and
                    (meta.get('disposition')=='Completed' or p.get('sourceStatus','').casefold() in ('completed','closed')))
    return p['stage']=='Completed' and bool(iso_date(p.get('completedDate')))


def aggregate(projects,filters,designers,source_version,origin):
    start,end=iso_date(filters['start']),iso_date(filters['end'])
    names={d['id']:d['name'] for d in designers}
    def types(p):return list(dict.fromkeys(p.get('taskTypes') or [p.get('taskType') or 'Unspecified']))
    scoped=[]
    for p in projects:
        meta=p.get('reporting',{})
        if filters['source']=='copied' and not p.get('readOnly'):continue
        if filters['source']=='test' and p.get('readOnly'):continue
        if filters['designer'] and p.get('requestedDesigner')!=filters['designer']:continue
        if filters['taskType'] and filters['taskType'] not in types(p):continue
        if filters['stage'] and p['stage']!=filters['stage']:continue
        if filters['directorate'] and (meta.get('directorate') or 'Unclassified')!=filters['directorate']:continue
        if filters['impactLevel'] and meta.get('impactLevel')!=filters['impactLevel']:continue
        scoped.append(p)
    def in_period(value):return bool(iso_date(value) and start<=iso_date(value)<=end)
    received=[p for p in scoped if in_period(p.get('createdDate'))]
    finished=[p for p in scoped if completed(p) and in_period(p.get('completedDate'))]
    active=[p for p in scoped if p['stage'] not in ('Completed','Archived')]
    # Current open work is a separate all-date metric; charts use period activity.
    ids={p['id'] for p in received+finished}
    cohort=[p for p in scoped if p['id'] in ids]
    months=[];cursor=start.replace(day=1)
    while cursor<=end:
        key=cursor.strftime('%Y-%m');months.append({'label':key,'received':sum((p.get('createdDate') or '').startswith(key) for p in received),
            'completed':sum((p.get('completedDate') or '').startswith(key) for p in finished)})
        cursor=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1)
    durations=[(iso_date(p['completedDate'])-iso_date(p['createdDate'])).days for p in finished
               if iso_date(p.get('createdDate')) and iso_date(p['completedDate'])>=iso_date(p['createdDate'])]
    on_time=[p for p in finished if iso_date(p.get('finalDueDate'))]
    high=[p for p in cohort if p.get('reporting',{}).get('impactLevel') in ('High','Strategic') and p['reporting'].get('impactJustification')]
    def counts(values):return [{'label':label,'value':value} for label,value in sorted(Counter(values).items(),key=lambda x:(-x[1],x[0]))]
    type_counts=counts(t for p in cohort for t in types(p))
    directorates=counts(p.get('reporting',{}).get('directorate') or 'Unclassified' for p in cohort)
    designer_rows=[]
    for d in designers:
        own=[p for p in scoped if p.get('requestedDesigner')==d['id']]
        designer_rows.append({'label':d['name'],'value':sum(p['id'] in {f['id'] for f in finished} for p in own),
            'active':sum(p in active and p.get('response')=='accepted' for p in own),
            'offers':sum(p in active and not p.get('readOnly') and p.get('response') not in ('accepted','declined') for p in own),
            'estimatedHours':round(sum(p.get('hours') or 0 for p in own if p in active and p.get('response')=='accepted'),2)})
    records=[]
    for p in sorted(cohort,key=lambda p:(p.get('createdDate') or '',p['id']),reverse=True):
        meta=p.get('reporting',{})
        records.append({'id':p['id'],'title':p['title'],'stage':p['stage'],'taskTypes':types(p),
            'designer':names.get(p.get('requestedDesigner'),'Not assigned') if p.get('response')=='accepted' else 'Not assigned',
            'department':p.get('requestorGroup',''),'createdDate':p.get('createdDate',''),'completedDate':p.get('completedDate',''),
            'confirmedDueDate':p.get('finalDueDate',''),'estimatedHours':p.get('hours'),
            'countedCompleted':p in finished,'copied':bool(p.get('readOnly')),
            'reporting':meta,'metadataVersion':p.get('metadataVersion',0),'sourceRevision':p['revision'],
            'canAnnotate':p.get('canAnnotate',False),'url':origin+'/#/projects/'+quote(p['id'],safe='')})
    assessed=sum(bool(p.get('reporting',{}).get('impactLevel')) for p in cohort)
    quality={
        'selectedSourceRecords':len(projects),'matchingScopeRecords':len(scoped),'periodRecords':len(cohort),
        'missingReceivedDate':sum(not iso_date(p.get('createdDate')) for p in scoped),
        'closedWithoutCompletionDate':sum(p['stage'] in ('Completed','Archived') and not iso_date(p.get('completedDate')) for p in scoped),
        'unverifiedArchived':sum(p['stage']=='Archived' and not completed(p) and p.get('reporting',{}).get('disposition')!='Cancelled' for p in scoped),
        'unclassifiedDirectorate':sum(not p.get('reporting',{}).get('directorate') for p in cohort),
        'reversedCompletionDates':sum(completed(p) and bool(iso_date(p.get('createdDate'))) and p['completedDate']<p['createdDate'] for p in scoped),
        'impactAssessed':assessed,'completionDurationSample':len(durations),'onTimeSample':len(on_time),
        'partialMonths':start.day!=1 or (end+timedelta(days=1)).day!=1,
    }
    kpis={'periodJobs':len(cohort),'received':len(received),'completed':len(finished),
          'averageCompletedPerMonth':round(len(finished)/len(months),2),
          'currentActive':len(active),'currentEstimatedHours':round(sum(p.get('hours') or 0 for p in active if p.get('response')=='accepted'),2),
          'averageTurnaroundDays':round(sum(durations)/len(durations),1) if durations else None,
          'onTimePercent':round(100*sum(p['completedDate']<=p['finalDueDate'] for p in on_time)/len(on_time),1) if on_time else None,
          'highImpact':len(high),'directoratesServed':sum(r['label']!='Unclassified' for r in directorates)}
    notes=[
        'DEV sample only: approved test records and selected copied projects; not an organization-wide total.',
        'Period jobs were received or verified completed in the selected period. Current backlog and its estimates use all dates within the other filters.',
        'Monthly averages include zero-completion months. Partial first/last months are included and identified.',
        'A multi-category job appears in each applicable work type; category counts can exceed distinct jobs.',
        'Archived jobs require an explicit completed outcome or a completed legacy status. Cancelled work is excluded from completions.',
        'Turnaround uses dated completions with a valid received date. On-time delivery uses confirmed final due dates only. Missing values remain unknown.',
        'High/strategic impact requires coordinator classification and justification. Planned outcomes are distinct from observed results. Estimates are not actual effort.',
    ]
    return {'title':'Creative Services Management Report','generatedAt':datetime.now(ZoneInfo('America/New_York')).isoformat(),
            'sourceVersion':source_version,'scope':'DEV sample','filters':filters,'kpis':kpis,'monthly':months,
            'types':type_counts,'directorates':directorates,'stages':counts(p['stage'] for p in cohort),
            'designers':sorted(designer_rows,key=lambda r:(-r['value'],-r['active'],r['label'])),'quality':quality,'notes':notes,'records':records,
            'highlights':[r for r in records if r['reporting'].get('impactLevel') in ('High','Strategic') and r['reporting'].get('impactJustification')],
            'classificationProjects':[{'id':p['id'],'title':p['title'],'canAnnotate':p.get('canAnnotate',False),'sourceRevision':p['revision'],'metadataVersion':p.get('metadataVersion',0),'reporting':p.get('reporting',{})} for p in projects],
            'options':{'designers':designers,'types':sorted({t for p in projects for t in types(p)}),
                'directorates':sorted({p.get('reporting',{}).get('directorate') or 'Unclassified' for p in projects}),
                'levels':LEVELS,'sections':SECTIONS,'presets':PRESETS}}


class Reporting:
    def __init__(self,runtime):self.runtime=runtime

    def _coordinator(self,sid,fresh=True):
        context=self.runtime.jobs._resolve(sid)
        if not context.principal.can_coordinate:raise WriteError('Reports are available to coordinators and admins only.',403)
        if fresh:context=self.runtime.jobs._fresh(sid)
        if not context.principal.can_coordinate:raise WriteError('Your reporting access changed.',403)
        return context

    def _projects(self,context):
        result=[]
        with self.runtime.db() as db:
            rows={row: (version,json.loads(payload)) for row,version,payload in db.execute(
                'SELECT row_id,version,payload_json FROM reporting_profiles WHERE sheet_id=?',(context.reader.sheet_id,))}
        for source in context.reader._cache['projects']:
            if not self.runtime.jobs._can_read(context.principal,source) or self.runtime.lifecycle.is_deleted(context.reader.sheet_id,source['_rowId']):continue
            p=copy.deepcopy(source);version,meta=rows.get(p['_rowId'],(0,{}));p['reporting']=meta;p['metadataVersion']=version;p['lifecycleVersion']=self.runtime.lifecycle.state(context.reader.sheet_id,p['_rowId'])['version']
            p['canAnnotate']=bool(self.runtime.jobs._permissions(context,p)['edit'])
            result.append(p)
        return result

    def _fingerprint(self,context,projects):
        return digest({'sheetVersion':context.reader.version,'copies':sorted(self.runtime.active_config().copied_row_ids),
                       'rows':[(p['_rowId'],p['revision'],p['metadataVersion'],p['lifecycleVersion']) for p in projects]})

    def snapshot(self,sid,body):
        if not isinstance(body,dict) or set(body)!={'filters'}:raise WriteError('Choose report filters.')
        filters=clean_filters(body['filters'])
        with self.runtime.sheet_lock:
            context=self._coordinator(sid);projects=self._projects(context)
            if len(projects)>5000:raise WriteError('The selected reporting source exceeds the pilot limit.',413)
            raw=self.runtime.jobs._workspace(context,context.reader._cache)
            report=aggregate(projects,filters,raw['designers'],context.reader.version,self.runtime.config.origin)
            if len(json.dumps(report).encode())>8*1024*1024:raise WriteError('This report is too large. Narrow the filters.',413)
            fingerprint=self._fingerprint(context,projects);self.runtime.jobs._ensure_current(sid,context)
            snapshot=secrets.token_urlsafe(24);expires=min(time.time()+1800,context.principal.expires_at)
            with self.runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM reporting_snapshots WHERE expires_at<?',(time.time(),))  # Expired private generated snapshots only, never source jobs/files.
                count=db.execute('SELECT COUNT(*) FROM reporting_snapshots WHERE owner=?',(context.principal.user_id,)).fetchone()[0]
                if count>=30:raise WriteError('Too many report snapshots. Reuse a report or wait for expiry.',429)
                db.execute('INSERT INTO reporting_snapshots VALUES (?,?,?,?,?,?,?)',(snapshot,context.principal.user_id,context.reader.sheet_id,
                    expires,fingerprint,json.dumps(report),time.time()))
            return {'snapshotId':snapshot,'expiresAt':expires,'report':report}

    def profile(self,sid,job,body):
        if not isinstance(body,dict) or set(body)!={'sourceRevision','metadataVersion','fields'} or type(body['metadataVersion']) is not int:
            raise WriteError('Refresh this job before updating reporting details.')
        values=body['fields']
        if not isinstance(values,dict) or set(values)!=set(PROFILE_FIELDS):raise WriteError('Use the available reporting fields.')
        if any(not isinstance(values[k],str) or len(values[k])>limit or any(ord(c)<32 and c not in '\n\r\t' for c in values[k]) for k,limit in PROFILE_FIELDS.items()):raise WriteError('A reporting field is too long or invalid.')
        values={k:v.strip() for k,v in values.items()}
        if values['impactLevel'] not in LEVELS or values['disposition'] not in OUTCOMES:raise WriteError('Choose a valid impact level and outcome.')
        if values['impactLevel'] in ('High','Strategic') and not values['impactJustification']:raise WriteError('Explain why this job qualifies as high or strategic impact.')
        if values['evidenceUrl'] and not url_value({'value':values['evidenceUrl']}):raise WriteError('Enter a complete http(s) evidence URL without credentials.')
        with self.runtime.sheet_lock:
            context=self._coordinator(sid);project=self.runtime.jobs._project(context,job)
            if not self.runtime.jobs._permissions(context,project)['edit']:raise WriteError('Your role or the native edit checks do not permit reporting changes to this job.',403)
            if body['sourceRevision']!=project['revision']:raise WriteError('The job changed. Refresh the report.',409)
            with self.runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                prior=db.execute('SELECT version FROM reporting_profiles WHERE sheet_id=? AND row_id=?',(context.reader.sheet_id,project['_rowId'])).fetchone()
                version=prior[0] if prior else 0
                if version!=body['metadataVersion']:raise WriteError('Another coordinator changed these reporting details. Refresh.',409)
                self.runtime.jobs._ensure_current(sid,context)
                db.execute('INSERT INTO reporting_profiles VALUES (?,?,?,?,?,?,?) ON CONFLICT(sheet_id,row_id) DO UPDATE SET '
                    'version=excluded.version,payload_json=excluded.payload_json,updated_by=excluded.updated_by,updated_at=excluded.updated_at',
                    (context.reader.sheet_id,project['_rowId'],job,version+1,json.dumps(values),context.principal.user_id,time.time()))
            self.runtime.audit(context.principal,'reporting-profile',job,'success')
            return {'saved':True,'metadataVersion':version+1}

    def export(self,sid,snapshot_id,body):
        from backend.report_exports import render_export
        if not isinstance(body,dict) or set(body)!={'format','sections','layout'}:raise WriteError('Choose an export format and report sections.')
        sections=body['sections'];fmt=body['format'];layout=body['layout']
        if (not isinstance(fmt,str) or not isinstance(layout,str) or fmt not in ('csv','csv-jobs','pdf','docx','pptx') or layout not in PRESETS or not isinstance(sections,list)
                or not sections or len(sections)>len(SECTIONS)
                or any(not isinstance(s,str) or s not in SECTIONS for s in sections) or len(set(sections))!=len(sections)):
            raise WriteError('Choose available sections without duplicates.')
        if 'quality' not in sections:sections=sections+['quality']
        with self.runtime.sheet_lock:
            context=self._coordinator(sid)
            with self.runtime.db() as db:
                saved=db.execute('SELECT expires_at,fingerprint,payload_json FROM reporting_snapshots WHERE snapshot_id=? AND owner=? AND sheet_id=?',
                    (snapshot_id,context.principal.user_id,context.reader.sheet_id)).fetchone()
            if not saved:raise WriteError('This report is not available to your account.',404)
            if saved[0]<time.time():raise WriteError('This report snapshot expired. Generate a new report.',410)
            projects=self._projects(context)
            if saved[1]!=self._fingerprint(context,projects):raise WriteError('Source data or reporting details changed. Refresh the report before exporting.',409)
            report=json.loads(saved[2]);principal=context.principal
        # Expensive document generation does not hold the native sheet's mutation lock.
        result=render_export(report,fmt,sections,layout)
        with self.runtime.sheet_lock:
            current=self._coordinator(sid)
            if saved[0]<time.time():raise WriteError('This report snapshot expired. Generate a new report.',410)
            if current.principal!=principal or saved[1]!=self._fingerprint(current,self._projects(current)):
                raise WriteError('Source or authorization changed while exporting. Refresh and try again.',409)
            self.runtime.jobs._ensure_current(sid,current)
        return result
