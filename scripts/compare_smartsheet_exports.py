"""Offline comparison only: no network connection and no sheet write operations."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re

JOB = 'Graphics Req #'
DERIVED = {'Due Date Urgency','Days Until Due','Days Since Received','Date Modified',
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
            candidates.append({'sheet':sheet['name'],'headers':nonempty,'rows':rows})
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
                            'This value comparison covers the main job sheet. Separate comment tabs and attachment metadata/files are not reconciled.',
                            'DEV-only rows, columns, links and calculated fields are retained. No live-to-DEV import has run.'],
            'schema':{'liveColumns':live['headers'],'devColumns':dev['headers'],
                      'missingDevColumns':sorted(set(live['headers'])-set(dev['headers'])),
                      'devOnlyColumns':sorted(set(dev['headers'])-set(live['headers']))},
            'missingRows':[],'devOnlyRows':[],'jobNumberCollisions':[],'ambiguousKeys':[],
            'conflicts':[],'fillCandidates':[],'calculatedDifferences':[],'unkeyedRows':unkeyed,
            'matchedJobs':[],'unchangedJobs':[]}
    common=(set(live['headers'])&set(dev['headers']))-{JOB,'DEV Test Record'}
    for job in sorted(set(left)|set(right)):
        a,b=left.get(job,[]),right.get(job,[])
        if len(a)>1 or len(b)>1:
            result['ambiguousKeys'].append({'job':job,'liveRows':[brief(r) for r in a],'devRows':[brief(r) for r in b]});continue
        if not a:
            result['devOnlyRows'].append({**brief(b[0]),'synthetic':is_dev(b[0])});continue
        if not b:
            result['missingRows'].append(brief(a[0]));continue
        if is_dev(b[0]):
            result['jobNumberCollisions'].append({'job':job,'live':brief(a[0]),'dev':brief(b[0])});continue
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
    result['summary']={'liveRows':len(live['rows']),'devRows':len(dev['rows']),
                       **{k:len(result[k]) for k in ('missingRows','devOnlyRows','jobNumberCollisions','ambiguousKeys','matchedJobs','unchangedJobs','conflicts','fillCandidates','calculatedDifferences')},
                       'jobsWithConflicts':len({r['job'] for r in result['conflicts']})}
    return result


def html_report(report):
    def cell(v):
        text=normalized(v)
        return escape(text) if text else '<em>Blank</em>'
    def table(headers,rows):
        return '<table><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+(''.join('<tr>'+''.join('<td>'+cell(v)+'</td>' for v in row)+'</tr>' for row in rows) or '<tr><td colspan="'+str(len(headers))+'">None found.</td></tr>')+'</tbody></table>'
    sections=[('<h2>Summary</h2>'+table(['Measure','Count'],report['summary'].items()))]
    for key,title in [('conflicts','Conflicting or DEV-only values — keep DEV until reviewed'),('fillCandidates','Possible missing DEV values — review before filling'),('calculatedDifferences','Calculated or system-value differences — do not overwrite')]:
        sections.append('<h2>'+title+'</h2>'+table(['Job','Project','Field','Live value','DEV value'],([r['job'],r['title'],r['field'],r['live'],r['dev']] for r in report[key])))
    sections.append('<h2>Job-number collisions — different projects must not be merged</h2>'+table(['Job','Live project','DEV test project'],([r['job'],r['live']['title'],r['dev']['title']] for r in report['jobNumberCollisions'])))
    for key,title in [('missingRows','Live jobs missing from DEV'),('devOnlyRows','DEV-only jobs — retain')]:
        sections.append('<h2>'+title+'</h2>'+table(['Job','Project','Export row'],([r['job'],r['title'],r['exportRow']] for r in report[key])))
    sections.append('<h2>Ambiguous duplicate job numbers</h2>'+table(['Job','Live rows','DEV rows'],([r['job'],r['liveRows'],r['devRows']] for r in report['ambiguousKeys'])))
    sections.append('<h2>Columns</h2>'+table(['Live-only columns missing in DEV','DEV-only columns to retain'],[[report['schema']['missingDevColumns'],report['schema']['devOnlyColumns']]]))
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>Graphics sheet reconciliation</title><style>body{font:15px/1.5 Arial,sans-serif;color:#18363a;margin:32px;max-width:1500px}h1{color:#004751}h2{font-size:20px;border-top:2px solid #00703c;padding-top:18px;margin-top:32px}table{border-collapse:collapse;width:100%;margin:14px 0 26px;table-layout:fixed}th{text-align:left;background:#e8f0ed}td,th{padding:10px;border-bottom:1px solid #ccd6d3;vertical-align:top;overflow-wrap:anywhere;white-space:pre-wrap}em{color:#666}li{margin:7px 0}</style><h1>Graphics sheet reconciliation</h1><p>'+escape(report['generatedAt'])+'</p><p><strong>Comparison only. Neither sheet was changed.</strong></p><p>'+escape(report['matchingMethod'])+'</p><ul>'+''.join('<li>'+escape(v)+'</li>' for v in report['limitations'])+'</ul>'+''.join(sections)+'</html>'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',required=True,type=Path);parser.add_argument('--dev',required=True,type=Path);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();report=compare(json.loads(args.live.read_text()),json.loads(args.dev.read_text()))
    args.out.mkdir(parents=True,exist_ok=True)
    for name,text in [('reconciliation.json',json.dumps(report,ensure_ascii=False,indent=2)),('reconciliation.html',html_report(report))]:
        path=args.out/name;path.write_text(text);path.chmod(0o600)
    print(json.dumps(report['summary']))


if __name__=='__main__':main()
