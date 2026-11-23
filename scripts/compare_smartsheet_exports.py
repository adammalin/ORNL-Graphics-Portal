"""Offline comparison only: no network connection and no sheet write operations."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re

JOB = 'Graphics Req #'
DERIVED = {'Due Date Urgency','Days Until Due','Days Since Received','Date Modified','Req Received',
           'Last Updated By','Assigned Designer','Latest Comment'}


def normalized(value):
    if value is None:return ''
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,(dict,list)):return json.dumps(value,sort_keys=True,ensure_ascii=False)
    return str(value).replace('\r\n','\n').strip()


def records(export):
    candidates=[]
    for sheet in export['sheets']:
        for index,row in enumerate(sheet['rows'][:25]):
            headers=[normalized(v) for v in row]
            if JOB not in headers:continue
            nonempty=[h for h in headers if h]
            if len(set(nonempty))!=len(nonempty):raise ValueError('Duplicate column labels require review.')
            rows=[]
            for number,values in enumerate(sheet['rows'][index+1:],index+2):
                data={h:values[i] if i<len(values) else None for i,h in enumerate(headers) if h}
                if any(normalized(v) for v in data.values()):rows.append({'exportRow':number,'fields':data})
            candidates.append({'sheet':sheet['name'],'headers':nonempty,'rows':rows,'headerRow':index+1})
            break
    if len(candidates)!=1:raise ValueError('Expected exactly one sheet with a Graphics Req # header.')
    return candidates[0]


def is_dev(row):
    f=row['fields']
    return (normalized(f.get('DEV Test Record')).lower() in ('true','1')
            or bool(re.match(r'^\[DEV(?:\s|\])',normalized(f.get('Description')),re.I)))


def brief(row):
    return {'job':normalized(row['fields'].get(JOB)).upper(),'title':normalized(row['fields'].get('Description')),
            'exportRow':row['exportRow']}


def comments(export,main):
    byrow={r['exportRow']-main['headerRow']:r for r in main['rows']}
    result=[];unmapped=[]
    for sheet in export['sheets']:
        if sheet['name'].lower()!='comments':continue
        for number,values in enumerate(sheet['rows'],1):
            if not any(normalized(v) for v in values):continue
            match=re.fullmatch(r'Row (\d+)',normalized(values[0]))
            row=byrow.get(int(match[1])) if match else None
            if not row or len(values)<4:
                unmapped.append(number);continue
            result.append({**brief(row),'text':normalized(values[1]),'author':normalized(values[2]),'date':normalized(values[3])})
    return result,unmapped


def compare(live_export,dev_export):
    live,dev=records(live_export),records(dev_export)
    indexes=[];unkeyed={}
    for label,data in [('live',live),('dev',dev)]:
        idx=defaultdict(list);unkeyed[label]=[]
        for row in data['rows']:
            job=normalized(row['fields'].get(JOB)).upper()
            if job:idx[job].append(row)
            else:unkeyed[label].append(row['exportRow'])
        indexes.append(idx)
    left,right=indexes
    result={'generatedAt':datetime.now(timezone.utc).isoformat(),'readOnly':True,
            'sources':{'live':live_export.get('source',{}),'dev':dev_export.get('source',{})},
            'matchingMethod':'Unique job number in native exports; no source-to-copy permanent row mapping or complete clone-time baseline is available.',
            'limitations':['No value is approved for overwrite by this report.',
                            'A blank DEV value may have been deliberately cleared; proposed fills require review.',
                            'Native Excel exports omit attachment files and do not preserve native formulas, column types, cell history or permissions. Attachment parity is not proven.',
                            'Comments are compared by exported row reference, text, author and date. Native comment IDs, reply relationships and attachment metadata/files are not reconciled.',
                            'Req Received is the native CREATED_DATE system field; cloning resets it. Its differences are reported with calculated/system values, not as editable overwrite conflicts.',
                            'DEV-only rows, columns, links and calculated fields are retained. No live-to-DEV import has run.'],
            'schema':{'liveColumns':live['headers'],'devColumns':dev['headers'],
                      'missingDevColumns':sorted(set(live['headers'])-set(dev['headers'])),
                      'devOnlyColumns':sorted(set(dev['headers'])-set(live['headers']))},
            'missingRows':[],'devOnlyRows':[],'jobNumberCollisions':[],'ambiguousKeys':[],
            'conflicts':[],'fillCandidates':[],'calculatedDifferences':[],'unkeyedRows':unkeyed,
            'matchedJobs':[],'unchangedJobs':[]}
    if live_export.get('source',{}).get('savedVersionOnly'):
        result['limitations'].append(live_export['source']['note'])
    common=(set(live['headers'])&set(dev['headers']))-{JOB,'DEV Test Record'}
    for job in sorted(set(left)|set(right)):
        a,b=left.get(job,[]),right.get(job,[])
        if len(a)>1 or len(b)>1:
            result['ambiguousKeys'].append({'job':job,'liveRows':[brief(r) for r in a],'devRows':[brief(r) for r in b]});continue
        if not a:
            result['devOnlyRows'].append({**brief(b[0]),'synthetic':is_dev(b[0])});continue
        if not b:
            result['missingRows'].append(brief(a[0]));continue
        placeholder=not any(normalized(b[0]['fields'].get(k)) for k in ('Description','Requestor','Requestor Email'))
        if is_dev(b[0]) or placeholder:
            result['jobNumberCollisions'].append({'job':job,'live':brief(a[0]),'dev':brief(b[0]),
                'reason':'DEV placeholder has no project identity' if placeholder else 'DEV synthetic project uses this live job number'});continue
        result['matchedJobs'].append(job);changed=False
        for field in sorted(common):
            av,bv=a[0]['fields'].get(field),b[0]['fields'].get(field)
            if normalized(av)==normalized(bv):continue
            item={'job':job,'title':brief(b[0])['title'],'field':field,'live':av,'dev':bv,
                  'liveExportRow':a[0]['exportRow'],'devExportRow':b[0]['exportRow']}
            if field in DERIVED:result['calculatedDifferences'].append(item);continue
            changed=True
            if not normalized(bv) and normalized(av):result['fillCandidates'].append(item)
            else:result['conflicts'].append({**item,'reason':'Live is blank; retain DEV value' if not normalized(av) else 'Values differ; retain DEV pending review'})
        if not changed:result['unchangedJobs'].append(job)
    source_comments,source_unmapped=comments(live_export,live)
    dev_comments,dev_unmapped=comments(dev_export,dev)
    def comment_key(c):return tuple(c[k] for k in ('job','text','author','date'))
    remaining=Counter(comment_key(c) for c in dev_comments);missing_comments=[]
    blocked={c['job'] for c in result['jobNumberCollisions']+result['ambiguousKeys']+result['missingRows']}
    for comment in source_comments:
        key=comment_key(comment)
        if remaining[key]:remaining[key]-=1
        else:missing_comments.append({**comment,'targetBlocked':comment['job'] in blocked})
    result['comments']={'missingFromDev':missing_comments,'liveUnmappedExportRows':source_unmapped,
                        'devUnmappedExportRows':dev_unmapped,'devOnlyCount':sum(remaining.values())}
    result['summary']={'liveRows':len(live['rows']),'devRows':len(dev['rows']),
                       **{k:len(result[k]) for k in ('missingRows','devOnlyRows','jobNumberCollisions','ambiguousKeys','matchedJobs','unchangedJobs','conflicts','fillCandidates','calculatedDifferences')},
                       'jobsWithConflicts':len({r['job'] for r in result['conflicts']}),
                       'liveComments':len(source_comments),'devComments':len(dev_comments),
                       'commentsMissingFromDev':len(missing_comments),
                       'jobsWithMissingComments':len({c['job'] for c in missing_comments})}
    assert len(live['rows']) == len(result['matchedJobs'])+len(result['missingRows'])+len(result['jobNumberCollisions'])+sum(len(x['liveRows']) for x in result['ambiguousKeys'])+len(unkeyed['live'])
    assert len(dev['rows']) == len(result['matchedJobs'])+len(result['devOnlyRows'])+len(result['jobNumberCollisions'])+sum(len(x['devRows']) for x in result['ambiguousKeys'])+len(unkeyed['dev'])
    return result


def html_report(report):
    def cell(v):
        text=normalized(v)
        if len(text)>220:
            return '<details class="cell-detail"><summary>'+escape(text[:120])+'…</summary><div>'+escape(text)+'</div></details>'
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}T00:00:00',text):text=text[:10]
        return escape(text) if text else '<em>Blank</em>'
    def table(headers,rows):
        return '<table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+(''.join('<tr>'+''.join('<td>'+cell(v)+'</td>' for v in row)+'</tr>' for row in rows) or '<tr><td colspan="'+str(len(headers))+'">None found.</td></tr>')+'</tbody></table>'
    labels={'liveRows':'Live jobs','devRows':'DEV jobs including tests','matchedJobs':'Existing copied jobs matched',
            'unchangedJobs':'Copied jobs without editable-field differences','jobsWithConflicts':'Copied jobs with conflicts',
            'conflicts':'Conflicting business-field values','fillCandidates':'Possible fills requiring review',
            'jobNumberCollisions':'Live projects blocked by DEV job-number collisions','devOnlyRows':'DEV-only jobs to retain',
            'commentsMissingFromDev':'Live comments missing from DEV','jobsWithMissingComments':'Jobs with missing comments'}
    summary=[(label,report['summary'][key]) for key,label in labels.items()]
    sections=['<h2>Summary</h2>'+table(['Measure','Count'],summary)]
    sections.append('<h2>Conflicting business values — keep DEV until reviewed</h2>'+table(['Job','Project','Field','Live value','DEV value'],([r['job'],r['title'],r['field'],r['live'],r['dev']] for r in report['conflicts'])))
    sections.append('<h2>Job-number collisions — different projects must not be merged</h2>'+table(['Job','Live project','DEV project','Reason'],([r['job'],r['live']['title'],r['dev']['title'],r['reason']] for r in report['jobNumberCollisions'])))
    sections.append('<h2>Possible missing DEV values — review before filling</h2>'+table(['Job','Project','Field','Live value','DEV value'],([r['job'],r['title'],r['field'],r['live'],r['dev']] for r in report['fillCandidates'])))
    sections.append('<details><summary>Live comments missing from DEV ('+str(len(report['comments']['missingFromDev']))+')</summary>'+table(['Job','Comment','Author','Date','Action'],([r['job'],r['text'],r['author'],r['date'],'Resolve job identity first' if r['targetBlocked'] else 'Review add-only history import'] for r in report['comments']['missingFromDev']))+'</details>')
    sections.append('<details><summary>Calculated and system-value differences — do not overwrite ('+str(len(report['calculatedDifferences']))+')</summary>'+table(['Job','Project','Field','Live value','DEV value'],([r['job'],r['title'],r['field'],r['live'],r['dev']] for r in report['calculatedDifferences']))+'</details>')
    for key,title in [('missingRows','Live job numbers absent from DEV'),('devOnlyRows','DEV-only jobs — retain')]:
        sections.append('<h2>'+title+'</h2>'+table(['Job','Project','Export row'],([r['job'],r['title'],r['exportRow']] for r in report[key])))
    sections.append('<h2>Ambiguous duplicate job numbers</h2>'+table(['Job','Live rows','DEV rows'],([r['job'],r['liveRows'],r['devRows']] for r in report['ambiguousKeys'])))
    sections.append('<h2>Columns</h2>'+table(['Live-only columns missing in DEV','DEV-only columns to retain'],[[report['schema']['missingDevColumns'],report['schema']['devOnlyColumns']]]))
    sections.append('<h2>Snapshot sources</h2>'+table(['Source','Export file','Captured at','SHA-256'],([label,source.get('filename'),source.get('capturedAt'),source.get('sha256')] for label,source in report['sources'].items())))
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Graphics sheet reconciliation</title><style>body{font:15px/1.5 Arial,sans-serif;color:#18363a;margin:32px;max-width:1500px}h1{color:#004751}h2{font-size:20px;border-top:2px solid #00703c;padding-top:18px;margin-top:32px}table{border-collapse:collapse;width:100%;margin:14px 0 26px;table-layout:fixed}th{text-align:left;background:#e8f0ed}td,th{padding:10px;border-bottom:1px solid #ccd6d3;vertical-align:top;overflow-wrap:anywhere;white-space:pre-wrap}em{color:#666}li{margin:7px 0}details{border-top:1px solid #ccd6d3;margin:22px 0;padding-top:12px}summary{font-weight:bold;cursor:pointer}.cell-detail{border:0;margin:0;padding:0}.cell-detail summary{font-weight:normal}.cell-detail div{padding-top:8px}</style><h1>Graphics sheet reconciliation</h1><p>'+escape(report['generatedAt'])+'</p><p><strong>Comparison only. Neither sheet was changed.</strong> Live snapshot excludes unsaved changes reported by Smartsheet.</p>'+''.join(sections)+'<details><summary>Matching method and limits</summary><p>'+escape(report['matchingMethod'])+'</p><ul>'+''.join('<li>'+escape(v)+'</li>' for v in report['limitations'])+'</ul></details></html>'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',required=True,type=Path);parser.add_argument('--dev',required=True,type=Path);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();report=compare(json.loads(args.live.read_text()),json.loads(args.dev.read_text()))
    args.out.mkdir(parents=True,exist_ok=True)
    for name,text in [('reconciliation.json',json.dumps(report,ensure_ascii=False,indent=2)),('reconciliation.html',html_report(report))]:
        path=args.out/name;path.write_text(text);path.chmod(0o600)
    print(json.dumps(report['summary']))


if __name__=='__main__':main()
