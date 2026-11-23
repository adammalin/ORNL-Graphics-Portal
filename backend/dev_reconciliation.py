"""One-shot, host-armed DEV reconciliation. No public maintenance API or token export."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from backend.dev_store import WriteError
from scripts.compare_smartsheet_exports import normalized, is_dev


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def stamp():return datetime.now(timezone.utc).isoformat()
def save_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False));tmp.chmod(0o600);tmp.replace(path)
def cell_value(cell):
    obj=cell.get('objectValue') or {}
    if not isinstance(obj,dict):obj={}
    if obj.get('objectType')=='CONTACT':return obj.get('name') or obj.get('email') or cell.get('displayValue') or cell.get('value')
    return cell.get('value',cell.get('displayValue'))
def comparable(value,field):
    value=normalized(value)
    if field in ('Due Date','Final Due Date','Req Assigned / Closed') and re.match(r'^\d{4}-\d{2}-\d{2}',value):return value[:10]
    return value
def row_fields(sheet,row):
    titles={c['id']:c['title'] for c in sheet['columns']}
    return {titles[c['columnId']]:cell_value(c) for c in row['cells'] if c['columnId'] in titles}
def indexed(sheet):
    result=defaultdict(list)
    for row in sheet['rows']:
        job=normalized(row_fields(sheet,row).get('Graphics Req #'))
        if job:result[job].append(row)
    return result
def single(index,job):
    matches=index.get(job,[])
    if len(matches)!=1:raise WriteError('The reviewed job is missing or ambiguous: '+job,409)
    return matches[0]


class NativeClient:
    """Independent lowest-level boundary: the live sheet has GET access only."""
    def __init__(self,reader,source,target,guard):
        if source==target or not all(re.fullmatch(r'\d+',x) for x in (source,target)):
            raise WriteError('Distinct numeric live and DEV sheet IDs are required.',503)
        self.reader,self.source,self.target,self.guard=reader,source,target,guard
        self.requests=[];self.last=0

    def pace(self):
        delay=.3-(time.monotonic()-self.last)
        if delay>0:time.sleep(delay)
        self.last=time.monotonic()

    def get(self,path):
        pattern=r'/sheets/('+self.source+'|'+self.target+r')(?:/version|/discussions|/rows/\d+|/automationrules)?(?:\?[^#]*)?'
        if not re.fullmatch(pattern,path):raise WriteError('Read is outside the two approved sheets.',403)
        self.pace();self.requests.append({'method':'GET','path':path})
        return self.reader._get_json(path,'reviewed-dev-reconciliation-read')

    def write(self,method,path,payload):
        root='/sheets/'+self.target
        permitted=(path==root+'/rows' and method in ('POST','PUT')
            or bool(re.fullmatch(re.escape(root)+r'/rows/\d+/discussions',path)) and method=='POST'
            or bool(re.fullmatch(re.escape(root)+r'/discussions/\d+/comments',path)) and method=='POST')
        if not permitted:raise WriteError('Reconciliation can write only approved DEV rows and add-only comments.',403)
        self.guard();self.pace();self.requests.append({'method':method,'path':path})
        if self.reader._transport:return self.reader._transport(path,method,payload,None)
        req=Request('https://api.smartsheet.com/2.0'+path,method=method,data=json.dumps(payload).encode(),headers={
            'Authorization':'Bearer '+self.reader._token,'Content-Type':'application/json','Accept':'application/json',
            'smartsheet-integration-source':'APPLICATION,ORNL,Graphics-Portal-DEV-Reconciliation'})
        try:
            with self.reader._opener.open(req,timeout=40) as response:result=json.load(response)
        except HTTPError as error:
            raise WriteError('Native DEV import rejected (HTTP '+str(error.code)+'). Review the private receipt before retrying.',502) from None
        except (URLError,TimeoutError,ValueError):
            raise WriteError('Native DEV outcome is uncertain. Readback is required; the write was not repeated.',502) from None
        if result.get('resultCode')!=0 or 'result' not in result:
            raise WriteError('Native DEV import was not fully confirmed.',502)
        return result


class DevReconciliation:
    def __init__(self,runtime,path):
        self.runtime=runtime;self.path=Path(path).resolve();self.plan=json.loads(self.path.read_text())
        self.plan_digest=digest(self.plan);self.directory=self.path.parent
        self.db_path=self.directory/'receipts.sqlite3';self.lock=threading.Lock();self.running=False
        self.report=json.loads(Path(self.plan['reportPath']).read_text())
        if hashlib.sha256(Path(self.plan['reportPath']).read_bytes()).hexdigest()!=self.plan['reportSha256']:
            raise WriteError('The approved comparison report changed.',409)
        if str(self.plan['targetSheetId'])!=runtime.config.sheet_id:
            raise WriteError('The import target is not the pinned DEV sheet.',403)
        self.source=str(self.plan['sourceSheetId']);self.target=str(self.plan['targetSheetId'])
        self.expires=datetime.fromisoformat(self.plan['expiresAt'].replace('Z','+00:00')).timestamp()
        if not time.time()<self.expires<=min(runtime.config.expires,time.time()+4*3600+60):
            raise WriteError('A short, explicit reconciliation window is required.',503)
        self.report_hash=digest(self.report)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS operations (key TEXT PRIMARY KEY,payload_hash TEXT,state TEXT,result TEXT)')
        self.db_path.chmod(0o600)

    def db(self):return sqlite3.connect(self.db_path,timeout=15)
    def status(self,state,**data):save_json(self.directory/'status.json',{'at':stamp(),'state':state,**data})

    def guard(self):
        if time.time()>=self.expires or not self.path.exists() or digest(json.loads(self.path.read_text()))!=self.plan_digest:
            raise WriteError('The local reconciliation grant expired or was revoked.',403)
        context=self.runtime.jobs._ensure_current(self.sid,self.context)
        if context.principal.user_id!=str(self.plan['ownerId']) or not context.principal.is_admin:
            raise WriteError('This one-shot import belongs to its verified admin owner.',403)
        context.reader.store.require_writes()
        context.reader.store.validate_source()
        current=self.client.get('/sheets/'+self.source+'/version')
        if current.get('version')!=self.source_version:
            raise WriteError('The live source changed after preparation. Import paused before the next write.',409)

    def snapshot(self,sheet):
        value=self.client.get('/sheets/'+sheet+'?'+urlencode({'include':'attachments,objectValue','level':2}))
        if str(value.get('id'))!=sheet:raise WriteError('Unexpected sheet identity.',409)
        return value

    def discussions(self,sheet):
        result=self.client.get('/sheets/'+sheet+'/discussions?include=comments&includeAll=true')
        if 'data' not in result or result.get('totalPages',1)>1:raise WriteError('Complete discussion inventory is required.',409)
        return result['data']

    def prepare(self,sid):
        self.sid=sid;self.context=self.runtime.jobs._fresh(sid)
        if self.context.principal.user_id!=str(self.plan['ownerId']) or not self.context.principal.is_admin:
            raise WriteError('This one-shot import belongs to its verified admin owner.',403)
        self.client=NativeClient(self.context.reader,self.source,self.target,self.guard)
        source=self.snapshot(self.source);target=self.snapshot(self.target)
        if source.get('name')!=self.plan['sourceName'] or target.get('name')!='DEV Graphics Assignments':
            raise WriteError('Sheet names do not match the approved source and DEV copy.',409)
        if target.get('accessLevel') not in ('OWNER','ADMIN','EDITOR','EDITOR_SHARE'):
            raise WriteError('Current native DEV editing access is required.',403)
        self.source_version=source['version'];self.guard()
        # Retain raw read-only evidence even if an unfamiliar native value fails preparation.
        for name,value in [('source-before.json',source),('dev-before.json',target)]:
            if not (self.directory/name).exists():save_json(self.directory/name,value)
        src,dev=indexed(source),indexed(target)
        columns={c['title']:c for c in target['columns']}
        self.source_before,self.dev_before=source,target
        self.source_discussions=self.discussions(self.source);self.dev_discussions=self.discussions(self.target)
        # Backups include all native DEV rows and discussion text, not just portal-selected rows.
        for name,value in [('source-before.json',source),('dev-before.json',target),
                           ('source-discussions-before.json',self.source_discussions),('dev-discussions-before.json',self.dev_discussions)]:
            p=self.directory/name
            if not p.exists():save_json(p,value)
        updates=defaultdict(list);self.mapping={};creates=[]
        for item in self.report['conflicts']+self.report['fillCandidates']:
            a=single(src,item['job']);b=single(dev,item['job']);af=row_fields(source,a);bf=row_fields(target,b)
            self.unlocked(b)
            if is_dev({'fields':bf}):raise WriteError('A reviewed copy is now a DEV test record.',409)
            if comparable(af.get(item['field']),item['field'])!=comparable(item['live'],item['field']):
                raise WriteError('A reviewed live field changed: '+item['job']+' / '+item['field'],409)
            old=comparable(bf.get(item['field']),item['field']);allowed={comparable(item['dev'],item['field']),comparable(item['live'],item['field'])}
            if old not in allowed:raise WriteError('A reviewed DEV value changed: '+item['job']+' / '+item['field'],409)
            col=columns[item['field']];current=next((c for c in a['cells'] if c['columnId']==next(x['id'] for x in source['columns'] if x['title']==item['field'])),{})
            self.editable(col,next((c for c in b['cells'] if c['columnId']==col['id']),{}))
            updates[str(b['id'])].append({'columnId':col['id'],'value':current.get('value'),'strict':True})
            self.mapping[str(a['id'])]={'sourceJob':item['job'],'targetRow':str(b['id']),'targetJob':item['job']}
        for item in self.report['jobNumberCollisions']+self.report['missingRows']:
            job=item['job'];a=single(src,job)
            if normalized(row_fields(source,a).get('Description'))!=item.get('live',item)['title']:
                raise WriteError('A missing live project changed identity: '+job,409)
            marker='Original Graphics request: '+job+'\n'+self.plan['sourcePermalink']+'?rowId='+str(a['id'])
            values=[];source_columns={c['id']:c for c in source['columns']}
            for cell in a['cells']:
                source_col=source_columns.get(cell['columnId'],{});col=columns.get(source_col.get('title'))
                if not col or col.get('systemColumnType') or col.get('formula') or cell.get('formula') or col.get('title') in ('DEV Test Record','Project Stage','Latest Comment'):continue
                self.editable(col,{})
                if cell.get('value') is None and not cell.get('objectValue'):continue
                out=self.copy_cell(cell,col)
                if col['title']=='Additional Details':
                    out={'columnId':col['id'],'value':marker+'\n\n'+str(cell.get('value') or ''),'strict':True}
                values.append(out)
            if not any(c['columnId']==columns['Additional Details']['id'] for c in values):values.append({'columnId':columns['Additional Details']['id'],'value':marker,'strict':True})
            values.append({'columnId':columns['DEV Test Record']['id'],'value':False,'strict':True})
            if any(isinstance(c.get('value'),str) and len(c['value'])>4000 for c in values):raise WriteError('An imported native cell would exceed 4,000 characters.',409)
            creates.append({'sourceRow':str(a['id']),'sourceJob':job,'marker':marker,'cells':values})
        # Map all original copies for the reviewed comment history, never map a test collision.
        import_ids={v['sourceRow'] for v in creates}
        for source_row in source['rows']:
            f=row_fields(source,source_row);job=normalized(f.get('Graphics Req #'))
            if str(source_row['id']) in import_ids:continue
            matches=dev.get(job,[])
            if len(matches)==1 and not is_dev({'fields':row_fields(target,matches[0])}):
                self.mapping[str(source_row['id'])]={'sourceJob':job,'targetRow':str(matches[0]['id']),'targetJob':job}
        approved=Counter((c['job'],normalized(c['text']),normalized(c['author'])) for c in self.report['comments']['missingFromDev'])
        # Native readback outranks an export that omitted existing discussions.
        existing=defaultdict(list)
        for thread in self.dev_discussions:
            if thread.get('parentType')!='ROW':continue
            for comment in thread.get('comments',[]):
                author=comment.get('createdBy') or {}
                key=(str(thread['parentId']),normalized(comment.get('text')),normalized(author.get('name') or author.get('email')),comment.get('createdAt'))
                existing[key].append((str(thread['id']),str(comment['id'])))
        comments=[];present=[]
        for discussion in self.source_discussions:
            if discussion.get('parentType')!='ROW':continue
            row_id=str(discussion['parentId']);job=next((normalized(row_fields(source,r).get('Graphics Req #')) for r in source['rows'] if str(r['id'])==row_id),'')
            for comment in sorted(discussion.get('comments',[]),key=lambda c:c.get('createdAt','')):
                author=comment.get('createdBy') or {};name=author.get('name') or author.get('email') or ''
                key=(job,normalized(comment.get('text')),normalized(name))
                if not approved[key]:continue
                approved[key]-=1
                if row_id not in self.mapping and row_id not in import_ids:raise WriteError('A source comment has no safe DEV destination.',409)
                mapped=self.mapping.get(row_id)
                existing_key=(mapped['targetRow'] if mapped else '',normalized(comment.get('text')),normalized(name),comment.get('createdAt'))
                if existing[existing_key]:
                    target_thread,target_comment=existing[existing_key].pop(0)
                    present.append({'sourceComment':str(comment['id']),'sourceDiscussion':str(discussion['id']),
                                    'targetDiscussion':target_thread,'targetComment':target_comment})
                    continue
                marker='[Live Graphics comment '+self.source+':'+str(comment['id'])+']'
                body=marker+'\nOriginal author: '+name+'\nOriginal date: '+str(comment.get('createdAt',''))+'\nOriginal request: '+job+'\n\n'+str(comment.get('text') or '')
                comments.append({'sourceRow':row_id,'sourceJob':job,'sourceDiscussion':str(discussion['id']),
                                 'sourceComment':str(comment['id']),'marker':marker,'text':body})
        if any(approved.values()):raise WriteError('The current live comment inventory does not match all reviewed comments.',409)
        self.operations={'sourceVersion':self.source_version,'updates':[{'targetRow':k,'cells':v} for k,v in updates.items()],
                         'creates':creates,'comments':comments,'existingComments':present,'mapping':self.mapping}
        if {'fields':sum(len(x['cells']) for x in self.operations['updates']),'newJobs':len(creates),'comments':len(comments)}!=self.plan['expectedCounts']:
            raise WriteError('The prepared operation count differs from the approved import.',409)
        if len(present)!=self.plan.get('expectedExistingComments',0):
            raise WriteError('The native existing-comment count differs from the reviewed preflight.',409)
        self.prepared_digest=digest(self.operations);save_json(self.directory/'prepared.json',self.operations)
        self.status('prepared',digest=self.prepared_digest,counts=self.plan['expectedCounts'])
        return self.operations

    @staticmethod
    def unlocked(row):
        if row.get('locked') or row.get('lockedForUser'):
            raise WriteError('A native DEV destination is locked. Import paused.',409)

    @staticmethod
    def editable(column,cell):
        if column.get('systemColumnType') or column.get('formula') or column.get('locked') or cell.get('formula') or cell.get('linkInFromCell') or cell.get('hyperlink'):
            raise WriteError('A protected native field cannot be overwritten: '+column['title'],409)

    @staticmethod
    def copy_cell(cell,column):
        out={'columnId':column['id'],'strict':True}
        obj=cell.get('objectValue')
        if not isinstance(obj,dict):obj=None
        if obj and obj.get('objectType')=='CONTACT':
            out['objectValue']={k:v for k,v in obj.items() if k in ('objectType','email','name')}
        elif obj and obj.get('objectType') in ('MULTI_PICKLIST','MULTI_CONTACT'):
            out['objectValue']=copy.deepcopy(obj)
        else:out['value']=cell.get('value')
        return out

    def receipt(self,key,payload):
        fingerprint=digest(payload)
        with self.db() as db:
            saved=db.execute('SELECT payload_hash,state,result FROM operations WHERE key=?',(key,)).fetchone()
            if saved:
                if saved[0]!=fingerprint:raise WriteError('The durable import receipt belongs to different content.',409)
                return saved[1],json.loads(saved[2]) if saved[2] else None
            db.execute('INSERT INTO operations VALUES (?,?,?,NULL)',(key,fingerprint,'pending'))
        return 'new',None

    def finish(self,key,result):
        with self.db() as db:db.execute('UPDATE operations SET state=?,result=? WHERE key=?',('done',json.dumps(result),key))

    def apply(self):
        for op in self.operations['updates']:
            key='update:'+op['targetRow'];state,_=self.receipt(key,op)
            row=self.client.get('/sheets/'+self.target+'/rows/'+op['targetRow']+'?include=objectValue')
            self.unlocked(row)
            original=next(r for r in self.dev_before['rows'] if str(r['id'])==op['targetRow'])
            current={c['columnId']:c for c in row['cells']};prior={c['columnId']:c for c in original['cells']}
            for cell in op['cells']:
                self.editable(next(c for c in self.dev_before['columns'] if c['id']==cell['columnId']),current.get(cell['columnId'],{}))
                before=prior.get(cell['columnId'],{}).get('value');now=current.get(cell['columnId'],{}).get('value')
                if now not in (before,cell.get('value')):raise WriteError('A DEV value changed during import. Paused.',409)
            if state=='done' and any(current.get(c['columnId'],{}).get('value')!=c.get('value') for c in op['cells']):
                raise WriteError('A completed DEV update was changed afterward. It was not repeated.',409)
            if any(current.get(c['columnId'],{}).get('value')!=c.get('value') for c in op['cells']):
                self.client.write('PUT','/sheets/'+self.target+'/rows',[{'id':int(op['targetRow']),'cells':op['cells']}])
            self.finish(key,{'targetRow':op['targetRow']});self.status('applying',last=key)
        for op in self.operations['creates']:
            key='create:'+op['sourceRow'];state,saved=self.receipt(key,op)
            if saved:row_id=saved['targetRow']
            else:
                current=self.snapshot(self.target)
                found=[r for r in current['rows'] if str(row_fields(current,r).get('Additional Details') or '').startswith(op['marker'])]
                if len(found)>1:raise WriteError('Ambiguous imported-row marker. Paused.',409)
                if found:row_id=str(found[0]['id'])
                elif state=='pending':raise WriteError('Uncertain create has no readback yet. It was not repeated.',409)
                else:
                    response=self.client.write('POST','/sheets/'+self.target+'/rows',[{'toBottom':True,'cells':op['cells']}])
                    row_id=str(response['result'][0]['id'])
                self.finish(key,{'targetRow':row_id})
            row=self.client.get('/sheets/'+self.target+'/rows/'+row_id+'?include=objectValue')
            target_job=normalized(row_fields(self.dev_before,row).get('Graphics Req #'))
            if not target_job:raise WriteError('The imported row has no generated DEV job number yet.',409)
            self.mapping[op['sourceRow']]={'sourceJob':op['sourceJob'],'targetRow':row_id,'targetJob':target_job}
            self.status('applying',last=key)
        target_discussions=self.discussions(self.target);seen={}
        for discussion in target_discussions:
            for comment in discussion.get('comments',[]):
                marker=str(comment.get('text') or '').split('\n',1)[0]
                if marker.startswith('[Live Graphics comment '):
                    if marker in seen:raise WriteError('Duplicate native import markers need review.',409)
                    seen[marker]=(str(discussion['id']),str(comment['id']))
        threads={c['sourceDiscussion']:c['targetDiscussion'] for c in self.operations.get('existingComments',[])}
        for op in self.operations['comments']:
            key='comment:'+op['sourceComment'];state,saved=self.receipt(key,op)
            if saved:
                threads[op['sourceDiscussion']]=saved['targetDiscussion'];continue
            if op['marker'] in seen:
                thread,comment=seen[op['marker']]
            elif state=='pending':raise WriteError('Uncertain comment has no readback yet. It was not repeated.',409)
            else:
                dest=self.mapping[op['sourceRow']]['targetRow']
                row=self.client.get('/sheets/'+self.target+'/rows/'+dest+'?include=objectValue')
                self.unlocked(row)
                if is_dev({'fields':row_fields(self.dev_before,row)}):raise WriteError('A comment destination became a DEV test record.',409)
                if op['sourceDiscussion'] in threads:
                    thread=threads[op['sourceDiscussion']]
                    response=self.client.write('POST','/sheets/'+self.target+'/discussions/'+thread+'/comments',{'text':op['text']})
                    comment=str(response['result']['id'])
                else:
                    response=self.client.write('POST','/sheets/'+self.target+'/rows/'+dest+'/discussions',{'comment':{'text':op['text']}})
                    thread=str(response['result']['id']);comment=str(response['result']['comments'][0]['id'])
            threads[op['sourceDiscussion']]=thread;seen[op['marker']]=(thread,comment)
            self.finish(key,{'targetDiscussion':thread,'targetComment':comment});self.status('applying',last=key)
        after=self.snapshot(self.target);source_after=self.snapshot(self.source)
        if digest(source_after)!=digest(self.source_before):raise WriteError('The live sheet changed during the import; inspect the snapshots. No source write was issued.',409)
        protected=[];changes={u['targetRow']:{c['columnId'] for c in u['cells']} for u in self.operations['updates']}
        cols={c['id']:c for c in self.dev_before['columns']};after_rows={str(r['id']):r for r in after['rows']}
        for before in self.dev_before['rows']:
            rid=str(before['id']);new=after_rows.get(rid)
            if not new:raise WriteError('A preexisting DEV row is missing.',409)
            if before.get('attachments',[])!=new.get('attachments',[]):
                raise WriteError('Existing DEV attachment metadata changed; inspect the snapshots.',409)
            oldfields={c['columnId']:c for c in before['cells']};newfields={c['columnId']:c for c in new['cells']}
            for cid,cell in oldfields.items():
                col=cols[cid]
                if cid in changes.get(rid,set()) or col.get('formula') or col.get('systemColumnType') or col['title']=='Latest Comment':continue
                if cell!=newfields.get(cid):raise WriteError('An unrelated DEV input changed; inspect before/after evidence.',409)
            if is_dev({'fields':row_fields(self.dev_before,before)}):protected.append(rid)
        if after['columns']!=self.dev_before['columns']:raise WriteError('DEV schema changed during import.',409)
        source_discussions_after=self.discussions(self.source)
        if digest(source_discussions_after)!=digest(self.source_discussions):raise WriteError('Live discussions changed during import; inspect the read-only snapshots.',409)
        for op in self.operations['updates']:
            cells={c['columnId']:c for c in after_rows[op['targetRow']]['cells']}
            if any(cells.get(c['columnId'],{}).get('value')!=c.get('value') for c in op['cells']):
                raise WriteError('Native update readback does not match the approved values.',409)
        for op in self.operations['creates']:
            cells={c['columnId']:c for c in after_rows[self.mapping[op['sourceRow']]['targetRow']]['cells']}
            for requested in op['cells']:
                actual=cells.get(requested['columnId'],{})
                a,b=actual.get('objectValue'),requested.get('objectValue')
                if b:
                    if b['objectType']=='CONTACT':same=bool(a) and a.get('email','').lower()==b.get('email','').lower()
                    else:same=bool(a) and a.get('objectType')==b.get('objectType') and a.get('values')==b.get('values')
                else:same=actual.get('value')==requested.get('value')
                if not same:raise WriteError('An imported row did not retain a requested native value.',409)
        discussions_after=self.discussions(self.target);all_comments=defaultdict(list)
        existing_comments={str(c['id']):c for t in self.dev_discussions for c in t.get('comments',[])}
        after_comments={str(c['id']):c for t in discussions_after for c in t.get('comments',[])}
        if any(after_comments.get(cid)!=c for cid,c in existing_comments.items()):
            raise WriteError('A preexisting DEV comment changed; inspect the snapshots.',409)
        for thread in discussions_after:
            for c in thread.get('comments',[]):all_comments[str(c.get('text') or '').split('\n',1)[0]].append((thread,c))
        for op in self.operations['comments']:
            matches=all_comments[op['marker']]
            if len(matches)!=1 or matches[0][1]['text']!=op['text'] or str(matches[0][0]['parentId'])!=self.mapping[op['sourceRow']]['targetRow']:
                raise WriteError('Imported comment count, text or destination failed readback.',409)
        save_json(self.directory/'dev-after.json',after)
        save_json(self.directory/'source-after.json',source_after)
        save_json(self.directory/'dev-discussions-after.json',discussions_after)
        save_json(self.directory/'source-discussions-after.json',source_discussions_after)
        save_json(self.directory/'request-audit.json',self.client.requests)
        save_json(self.directory/'source-to-dev-mapping.json',self.mapping)
        self.status('complete',counts=self.plan['expectedCounts'],existingCommentsPreserved=len(self.operations.get('existingComments',[])),protectedTestRows=len(protected),sourceUnchanged=True,mapping=self.mapping)

    def on_login(self,sid):
        if not self.path.exists():return
        context=self.runtime.jobs._resolve(sid)
        if context.principal.user_id!=str(self.plan['ownerId']) or not context.principal.is_admin:return
        with self.lock:
            if self.running:return
            self.running=True
        def work():
            try:
                with self.runtime.sheet_lock:self.prepare(sid)
                # Host-only arming: browser/agent API callers cannot submit an arbitrary plan.
                while time.time()<self.expires:
                    arm=self.directory/'APPLY'
                    if arm.exists():
                        if arm.read_text().strip()!=self.prepared_digest:raise WriteError('The host approval digest does not match the prepared import.',409)
                        with self.runtime.sheet_lock:self.apply()
                        return
                    time.sleep(1)
                raise WriteError('The local reconciliation grant expired before apply.',403)
            except Exception as error:
                self.status('paused',error=str(error))
                save_json(self.directory/'diagnostic.json',{'traceback':traceback.format_exc()})
                if hasattr(self,'client'):save_json(self.directory/'request-audit.json',self.client.requests)
            finally:
                with self.lock:self.running=False
        threading.Thread(target=work,name='reviewed-dev-reconciliation',daemon=True).start()
