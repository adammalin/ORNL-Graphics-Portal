"""In-memory report downloads; no public file URLs or native-sheet writes."""
import csv
from html import escape
import io
import json
import os
from pathlib import Path
import re
import textwrap
import threading
import zipfile

from backend.dev_store import WriteError
from backend.reporting import SECTIONS

ROOT=Path(__file__).resolve().parents[1]
ASSET_DIR=ROOT/'.local/report-assets'
# Literal colors come from web/ornl-design-tokens.css (the existing approved palette).
GREEN='00662C';NAVY='00454D';INK='373A36';GRAY='DBDCDB';WHITE='FFFFFF';BLUE='006BA6'
_RENDER_LOCK=threading.Lock()
KPI_LABELS={'periodJobs':'Distinct jobs with period activity','received':'Jobs received in period','completed':'Verified completions in period',
 'averageCompletedPerMonth':'Average completions per month','currentActive':'Current active jobs across all dates',
 'currentEstimatedHours':'Current estimated hours on accepted work','averageTurnaroundDays':'Average turnaround in calendar days',
 'onTimePercent':'On time against confirmed deadline percent','highImpact':'High or strategic impact jobs',
 'directoratesServed':'Classified directorates served'}
QUALITY_LABELS={'selectedSourceRecords':'Records in approved selection','matchingScopeRecords':'Records matching non-date filters',
 'periodRecords':'Records with period activity','missingReceivedDate':'Records missing a valid received date',
 'closedWithoutCompletionDate':'Closed records missing a completion date','unverifiedArchived':'Archived records without verified completion',
 'reversedCompletionDates':'Completed records with reversed received/completion dates',
 'unclassifiedDirectorate':'Period jobs without a directorate','impactAssessed':'Period jobs with an impact classification',
 'completionDurationSample':'Completions usable for turnaround','onTimeSample':'Completions with a confirmed due date',
 'partialMonths':'Period contains partial months'}


def plain(value):return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value if value is not None else ''))
def compact(value,limit=90):
    value=plain(value)
    return value if len(value)<=limit else value[:limit-1]+'…'


def shown(value):return 'Not available' if value is None else 'Yes' if value is True else 'No' if value is False else plain(value)
def csv_value(value):
    if isinstance(value,str) and (value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n'))):return "'"+value
    return '' if value is None else value


def filter_text(report):
    labels={'source':'Source','designer':'Designer','taskType':'Work type','directorate':'Directorate','impactLevel':'Impact level','stage':'Current stage'}
    names={d['id']:d['name'] for d in report['options']['designers']}
    return ' | '.join(label+': '+plain(names.get(report['filters'][key],report['filters'][key]) if key=='designer' else {'all':'All approved DEV records','copied':'Copied projects (read-only)','test':'Test jobs'}.get(report['filters'][key],report['filters'][key]) if key=='source' else report['filters'][key]) for key,label in labels.items() if report['filters'].get(key)) or 'All approved records'


def section_table(report,key):
    if key=='summary':return ['Measure','Value'],[[v,shown(report['kpis'][k])] for k,v in KPI_LABELS.items()]
    if key=='monthly':return ['Month','Received','Completed'],[[r['label'],r['received'],r['completed']] for r in report['monthly']]
    if key in ('types','stages','directorates'):return ['Category','Jobs'],[[r['label'],r['value']] for r in report[key]]
    if key=='designers':return ['Designer','Completed in period','Current active','Pending offers','Estimated hours'],[[r['label'],r['value'],r['active'],r['offers'],r['estimatedHours']] for r in report[key]]
    if key=='quality':return ['Coverage measure','Value'],[[label,shown(report['quality'].get(k))] for k,label in QUALITY_LABELS.items()]
    if key=='records':return ['Job','Title','Current stage','Directorate'],[[r['id'],r['title'],r['stage'],r['reporting'].get('directorate') or 'Unclassified'] for r in report['records']]
    return ['Project','Impact level','Impact statement'],[[r['id']+' '+r['title'],r['reporting']['impactLevel'],r['reporting'].get('impactStatement') or 'No statement recorded'] for r in report['highlights']]


def csv_export(report,sections,jobs=False):
    out=io.StringIO(newline='');writer=csv.writer(out)
    if jobs:
        columns=['Job','Title','Current stage','Work types','Designer','Department','Received date','Completion date',
            'Confirmed due date','Estimated hours','Counted completed in period','Source','Directorate','Division','Impact level',
            'Impact category','Impact justification','Impact statement','Intended outcome','Observed outcome','Evidence URL','Reporting disposition','Job URL','Report generated','Source version','Period start','Period end','Applied filters','Report scope','Data coverage JSON','Definitions']
        writer.writerow(columns)
        for r in report['records']:
            m=r['reporting'];values=[r['id'],r['title'],r['stage'],' | '.join(r['taskTypes']),r['designer'],r['department'],r['createdDate'],r['completedDate'],r['confirmedDueDate'],r['estimatedHours'],r['countedCompleted'],'Copied read-only' if r['copied'] else 'DEV test',*[m.get(k,'') for k in ['directorate','division','impactLevel','impactCategory','impactJustification','impactStatement','intendedOutcome','observedOutcome','evidenceUrl','disposition']],r['url'],report['generatedAt'],report['sourceVersion'],report['filters']['start'],report['filters']['end'],filter_text(report),report['scope'],json.dumps(report['quality'],sort_keys=True),' | '.join(report['notes'])]
            writer.writerow([csv_value(v) for v in values])
    else:
        writer.writerow(['Section','Record','Metric','Value'])
        writer.writerow(['Report','Scope','Dataset',report['scope']]);writer.writerow(['Report','Generated','Timestamp',report['generatedAt']]);writer.writerow(['Report','Source','Version',report['sourceVersion']])
        writer.writerow(['Report','Filters','Applied filters',json.dumps(report['filters'],sort_keys=True)])
        for key in sections:
            header,rows=section_table(report,key)
            for n,row in enumerate(rows,1):
                for label,value in zip(header,row):writer.writerow([SECTIONS[key],n,csv_value(label),csv_value(value)])
        for i,note in enumerate(report['notes'],1):writer.writerow(['Definitions',i,'Note',note])
    return ('\ufeff'+out.getvalue()).encode('utf-8')


def require_assets(presentation=False):
    for name in ['Aptos.ttf','Aptos-Bold.ttf']+(['ornl-template.potx'] if presentation else []):
        if not (ASSET_DIR/name).is_file():raise WriteError('The approved report fonts or presentation template are not installed. Contact the portal administrator.',503)


def chart_png(report,key):
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.local/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.font_manager import FontProperties
    font=FontProperties(fname=str(ASSET_DIR/'Aptos.ttf'),size=10)
    fig=Figure(figsize=(7,3.2),dpi=180,facecolor='#'+WHITE);FigureCanvasAgg(fig);ax=fig.subplots()
    ax.spines[['top','right']].set_visible(False)
    if key=='monthly':
        rows=report[key];xs=list(range(len(rows)))
        ax.bar([x-.2 for x in xs],[r['received'] for r in rows],width=.38,color='#'+GREEN,label='Received')
        ax.bar([x+.2 for x in xs],[r['completed'] for r in rows],width=.38,color='#'+NAVY,label='Completed')
        ax.set_xticks(xs,[r['label'] for r in rows],rotation=45,ha='right');ax.legend(prop=font,frameon=False)
    else:
        rows=report[key][:8]
        if not rows:return None
        ax.barh(list(range(len(rows))),[r['value'] for r in rows],color='#'+GREEN)
        ax.set_yticks(list(range(len(rows))),[textwrap.fill(plain(r['label']),32) for r in rows]);ax.invert_yaxis()
    from matplotlib.ticker import MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(integer=True)) if key!='monthly' else ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    for label in list(ax.get_xticklabels())+list(ax.get_yticklabels()):label.set_fontproperties(font)
    ax.tick_params(colors='#'+INK);fig.tight_layout(pad=1.1);out=io.BytesIO();fig.savefig(out,format='png',dpi=180);return out.getvalue()


def pdf_export(report,sections,layout):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.pagesizes import letter
    require_assets();pdfmetrics.registerFont(TTFont('ReportAptos',str(ASSET_DIR/'Aptos.ttf')));pdfmetrics.registerFont(TTFont('ReportAptosBold',str(ASSET_DIR/'Aptos-Bold.ttf')))
    styles=getSampleStyleSheet()
    for st in styles.byName.values():st.fontName='ReportAptos';st.textColor=colors.HexColor('#'+INK)
    styles['Title'].fontName='ReportAptosBold';styles['Title'].fontSize=25;styles['Title'].leading=29;styles['Title'].alignment=0
    styles['Heading1'].fontName='ReportAptosBold';styles['Heading1'].fontSize=18;styles['Heading1'].leading=22;styles['Heading1'].textColor=colors.HexColor('#'+GREEN)
    styles['BodyText'].fontSize=10.5;styles['BodyText'].leading=14
    cell=ParagraphStyle('Cell',fontName='ReportAptos',fontSize=9,leading=12,textColor=colors.HexColor('#'+INK))
    p=lambda text,style=styles['BodyText']:Paragraph(escape(plain(text)).replace('\n','<br/>'),style)
    content=[p(report['title'],styles['Title']),p(layout.replace('-',' ').title()+' report'),p(report['filters']['start']+' through '+report['filters']['end']),Spacer(1,12),p(report['notes'][0]),p(filter_text(report)),p('Generated '+report['generatedAt']+' | Source version '+str(report['sourceVersion']))]
    for index,key in enumerate(sections):
        if index==0 and key=='summary':content.append(Spacer(1,22))
        else:content.append(PageBreak())
        content.append(p(SECTIONS[key],styles['Heading1']))
        if key=='records':content.append(p('Long job titles are shortened in this register; the job CSV retains complete values.'))
        if key in ('monthly','types','stages','directorates','designers'):
            png=chart_png(report,key)
            if png:content.extend([Image(io.BytesIO(png),width=490,height=224),Spacer(1,12)])
            if key!='monthly' and len(report[key])>8:content.append(p('Chart shows the first 8 categories. The table includes all categories.'))
        if key=='impact':
            highlights=report['highlights'];content.append(p(f'{len(highlights)} high or strategic jobs in this period. Showing up to 8 spotlights; use the job CSV for all records.'))
            for r in highlights[:8]:
                m=r['reporting'];content.extend([Spacer(1,12),p(r['id']+' '+r['title'],styles['Heading2'])])
                for label,field in [('Classification','impactLevel'),('Justification','impactJustification'),('Impact statement','impactStatement'),('Intended outcome','intendedOutcome'),('Observed outcome','observedOutcome'),('Evidence','evidenceUrl')]:
                    content.append(p(label+': '+(m.get(field) or 'Not recorded')))
            if not highlights:content.append(p('No coordinator-classified high or strategic impact jobs are recorded for this period. This is not evidence of no impact.'))
        else:
            header,rows=section_table(report,key)
            if key=='records' and len(rows)>200:content.append(p(f'Showing 200 of {len(rows)} matching projects. Download job CSV for all records.'));rows=rows[:200]
            if not rows:content.append(p('No matching data.'))
            else:
                table=Table([[p(v,cell) for v in header]]+[[p(shown(v),cell) for v in ([compact(v,500) for v in row] if key=='records' else row)] for row in rows],repeatRows=1,hAlign='LEFT',colWidths=([345,145] if len(header)==2 else [490/len(header)]*len(header)))
                table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#'+GRAY)),('GRID',(0,0),(-1,-1),.4,colors.HexColor('#'+GRAY)),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));content.append(table)
        if key=='quality':
            for note in report['notes']:content.extend([Spacer(1,8),p(note)])
    out=io.BytesIO()
    def footer(canvas,doc):
        canvas.setFont('ReportAptos',8);canvas.setFillColor(colors.HexColor('#'+NAVY));canvas.drawString(54,28,'Creative Services | DEV sample | '+report['filters']['start']+' to '+report['filters']['end']);canvas.drawRightString(558,28,str(doc.page))
    SimpleDocTemplate(out,pagesize=letter,leftMargin=54,rightMargin=54,topMargin=45,bottomMargin=48,title=report['title']).build(content,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()


def docx_export(report,sections,layout):
    from docx import Document
    from docx.shared import Inches,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    require_assets();doc=Document();sec=doc.sections[0];sec.page_width=Inches(8.5);sec.page_height=Inches(11);sec.top_margin=sec.bottom_margin=Inches(.7);sec.left_margin=sec.right_margin=Inches(.75)
    for name in ['Normal','Title','Heading 1','Heading 2']:
        doc.styles[name].font.name='Aptos';doc.styles[name].font.color.rgb=RGBColor.from_string(INK if name in ('Normal','Title') else GREEN)
    doc.styles['Normal'].font.size=Pt(11);doc.styles['Normal'].paragraph_format.space_after=Pt(8)
    doc.add_paragraph(report['title'],'Title');doc.add_paragraph(layout.title()+' report')
    doc.add_paragraph(report['filters']['start']+' through '+report['filters']['end']);doc.add_paragraph(report['notes'][0]);doc.add_paragraph(filter_text(report));doc.add_paragraph('Generated '+report['generatedAt']+' | Source version '+str(report['sourceVersion']))
    sec.header.paragraphs[0].text='Creative Services'
    sec.footer.paragraphs[0].text='ORNL | DEV sample | '+report['filters']['start']+' to '+report['filters']['end']
    for index,key in enumerate(sections):
        if index or key!='summary':doc.add_page_break()
        doc.add_heading(SECTIONS[key],1)
        if key in ('monthly','types','stages','directorates','designers'):
            png=chart_png(report,key)
            if png:doc.add_picture(io.BytesIO(png),width=Inches(6.8))
            if key!='monthly' and len(report[key])>8:doc.add_paragraph('Chart shows the first 8 categories. The table includes all categories.')
        if key=='impact':
            doc.add_paragraph(f'{len(report["highlights"])} high or strategic jobs. Showing up to 8 spotlights; the job CSV includes all records.')
            for r in report['highlights'][:8]:
                doc.add_heading(plain(r['id']+' '+r['title']),2)
                for label,k in [('Classification','impactLevel'),('Justification','impactJustification'),('Impact statement','impactStatement'),('Intended outcome','intendedOutcome'),('Observed outcome','observedOutcome'),('Evidence','evidenceUrl')]:doc.add_paragraph(label+': '+plain(r['reporting'].get(k) or 'Not recorded'))
            if not report['highlights']:doc.add_paragraph('No high or strategic impact classifications are recorded for this period. This is not evidence of no impact.')
        else:
            header,rows=section_table(report,key)
            if key=='records' and len(rows)>200:doc.add_paragraph(f'Showing 200 of {len(rows)} matching projects. Use job CSV for all records.');rows=rows[:200]
            table=doc.add_table(rows=1,cols=len(header));table.style='Table Grid'
            if len(header)==2:
                table.autofit=False;table.columns[0].width=Inches(4.9);table.columns[1].width=Inches(2.1)
            for cell,text in zip(table.rows[0].cells,header):
                cell.text=plain(text);shade=OxmlElement('w:shd');shade.set(qn('w:fill'),GRAY);cell._tc.get_or_add_tcPr().append(shade)
            repeat=OxmlElement('w:tblHeader');table.rows[0]._tr.get_or_add_trPr().append(repeat)
            for row in rows:
                for cell,value in zip(table.add_row().cells,row):cell.text=plain(shown(value))
            if not rows:doc.add_paragraph('No matching data.')
            if key=='quality':
                for note in report['notes']:doc.add_paragraph(note)
    out=io.BytesIO();doc.save(out);return out.getvalue()


def presentation_template():
    from pptx import Presentation
    source=zipfile.ZipFile(ASSET_DIR/'ornl-template.potx');out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dst:
        for item in source.infolist():
            data=source.read(item.filename)
            if item.filename=='[Content_Types].xml':data=data.replace(b'application/vnd.openxmlformats-officedocument.presentationml.template.main+xml',b'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml')
            dst.writestr(item,data)
    prs=Presentation(out)
    for item in list(prs.slides._sldIdLst):prs.part.drop_rel(item.rId);prs.slides._sldIdLst.remove(item)
    return prs


def pptx_export(report,sections,layout):
    from pptx.util import Inches,Pt
    from pptx.dml.color import RGBColor
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE,XL_LEGEND_POSITION
    require_assets(True);prs=presentation_template()
    def text(slide,value,x,y,w,h,size=18,color=INK,bold=False):
        shape=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h));tf=shape.text_frame;tf.word_wrap=True
        for i,line in enumerate(plain(value).split('\n')):
            p=tf.paragraphs[0] if i==0 else tf.add_paragraph();p.text=line;p.font.name='Aptos';p.font.size=Pt(size);p.font.bold=bold;p.font.color.rgb=RGBColor.from_string(color)
        return shape
    def page(title,subtitle=''):
        slide=prs.slides.add_slide(prs.slide_layouts[5]);slide.shapes.title.text=title
        for p in slide.shapes.title.text_frame.paragraphs:p.font.name='Aptos';p.font.size=Pt(32);p.font.color.rgb=RGBColor.from_string(INK)
        for shape in list(slide.placeholders):
            if shape.placeholder_format.idx!=0:shape._element.getparent().remove(shape._element)
        text(slide,subtitle,.5,1.4,12.2,.45,16,color=NAVY)
        text(slide,'DEV sample | '+report['filters']['start']+' to '+report['filters']['end'],.5,6.65,12.2,.35,14,color=NAVY)
        slide.notes_slide.notes_text_frame.text='Source snapshot generated '+report['generatedAt']+'; source version '+str(report['sourceVersion'])+'\nFilters: '+json.dumps(report['filters'],sort_keys=True)+'\n'+'\n'.join(report['notes'])
        return slide
    cover=prs.slides.add_slide(prs.slide_layouts[4]);cover.shapes.title.text=report['title']
    for shape in cover.placeholders:
        if shape.placeholder_format.idx==0:
            for p in shape.text_frame.paragraphs:p.font.name='Aptos';p.font.size=Pt(32);p.font.color.rgb=RGBColor.from_string(WHITE)
        elif shape.has_text_frame:
            shape.text=''
    text(cover,layout.title()+' report',1.0,3.8,11.2,.5,24,color=WHITE)
    text(cover,report['filters']['start']+' through '+report['filters']['end'],1.0,4.45,11.2,.5,20,color=WHITE)
    text(cover,'DEV sample | '+report['generatedAt'][:10],1.0,5.1,11.2,.45,16,color=WHITE)
    scope=page('Report scope and filters','Generated '+report['generatedAt']+' | Source version '+str(report['sourceVersion']))
    text(scope,filter_text(report)+'\n\n'+report['notes'][0],.7,2.1,11.8,4.2,22)
    for key in sections:
        if key in ('monthly','types','stages','directorates','designers'):
            rows=report[key];chunks=[rows[i:i+8] for i in range(0,len(rows),8)] or [[]]
            for number,chunk in enumerate(chunks):
                slide=page(SECTIONS[key]+(f' {number+1} of {len(chunks)}' if len(chunks)>1 else ''),'Completed counts use verified dates; current workload uses all dates.' if key=='designers' else 'Distinct period jobs; multi-category work can appear in several types.' if key=='types' else '')
                if not chunk:text(slide,'No matching data.',.7,2.2,11.8,1);continue
                data=CategoryChartData();data.categories=[csv_value(textwrap.fill(compact(r['label'],80),32)) for r in chunk]
                if key=='monthly':data.add_series('Received',[r['received'] for r in chunk]);data.add_series('Completed',[r['completed'] for r in chunk])
                else:data.add_series('Completed in period' if key=='designers' else 'Jobs',[r['value'] for r in chunk])
                chart=slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED if key=='monthly' else XL_CHART_TYPE.BAR_CLUSTERED,Inches(.6),Inches(2.0),Inches(12.1),Inches(4.35),data).chart
                chart.has_legend=key=='monthly'
                if chart.has_legend:chart.legend.position=XL_LEGEND_POSITION.BOTTOM;chart.legend.font.name='Aptos';chart.legend.font.size=Pt(14)
                for axis in [chart.category_axis,chart.value_axis]:axis.tick_labels.font.name='Aptos';axis.tick_labels.font.size=Pt(14)
                chart.value_axis.minimum_scale=0
                for i,series in enumerate(chart.series):series.format.fill.solid();series.format.fill.fore_color.rgb=RGBColor.from_string(GREEN if i==0 else NAVY);series.format.line.fill.background()
            if key=='designers':
                header,workload=section_table(report,key)
                for offset in range(0,len(workload),6):
                    chunk=workload[offset:offset+6];slide=page('Designer workload','Current accepted work and offers use all dates within the other filters. Estimates are not actual effort.')
                    table=slide.shapes.add_table(len(chunk)+1,5,Inches(.6),Inches(2.0),Inches(12.1),Inches(min(4.4,.55*(len(chunk)+1)))).table
                    for i,row in enumerate([header]+chunk):
                        for j,value in enumerate(row):
                            cell=table.cell(i,j);cell.text=compact(shown(value),60);cell.fill.solid();cell.fill.fore_color.rgb=RGBColor.from_string(GRAY if i==0 else WHITE)
                            for p in cell.text_frame.paragraphs:p.font.name='Aptos';p.font.size=Pt(16);p.font.color.rgb=RGBColor.from_string(INK)
                    for column,width in zip(table.columns,[4.1,2,2,2,2]):column.width=Inches(width)
        elif key=='impact':
            rows=report['highlights'][:8]
            if not rows:text(page('Impact highlights'),'No coordinator-classified high or strategic impact jobs are recorded for this period.\nThis is not evidence of no impact.',.7,2.2,11.8,2,24)
            for r in rows:
                m=r['reporting'];parts=[('Impact statement',m.get('impactStatement') or 'Not recorded'),('Intended outcome',m.get('intendedOutcome') or 'Not recorded'),('Observed outcome',m.get('observedOutcome') or 'Not recorded'),('Justification',m.get('impactJustification') or 'Not recorded'),('Evidence',m.get('evidenceUrl') or 'Not recorded')]
                lines=[]
                for label,value in [('Project',r['title'])]+parts:
                    lines.extend(textwrap.wrap(label+': '+plain(value),88) or ['Not recorded'])
                for offset in range(0,len(lines),10):
                    slide=page('Impact highlights',r['id']+' | '+m['impactLevel']+(f' | continued {offset//10+1}' if offset else ''))
                    text(slide,'\n'.join(lines[offset:offset+10]),.7,2.1,11.8,4.2,20)
                    slide.notes_slide.notes_text_frame.text+='\nProject: '+r['title']+'\n'+r['url']
        else:
            header,rows=section_table(report,key)
            limit=48 if key=='records' else len(rows)
            step=4 if key=='records' else 8
            for offset in range(0,max(1,min(len(rows),limit)),step):
                chunk=rows[offset:offset+step];slide=page(SECTIONS[key],('First '+str(limit)+' of '+str(len(rows))+' projects. ' if len(rows)>limit else '')+'Long labels shortened; full values in job CSV.' if key=='records' else '')
                if not chunk:text(slide,'No matching data.',.7,2.2,11.8,1);continue
                table=slide.shapes.add_table(len(chunk)+1,len(header),Inches(.6),Inches(2.0),Inches(12.1),Inches(min(4.4,.48*(len(chunk)+1)))).table
                for i,row in enumerate([header]+chunk):
                    for j,value in enumerate(row):
                        cell=table.cell(i,j);cell.text=compact(shown(value),90 if j==1 else 48) if key=='records' else plain(shown(value));cell.fill.solid();cell.fill.fore_color.rgb=RGBColor.from_string(GRAY if i==0 else WHITE)
                        for p in cell.text_frame.paragraphs:p.font.name='Aptos';p.font.size=Pt(16);p.font.color.rgb=RGBColor.from_string(INK)
                if key in ('summary','quality'):table.columns[0].width=Inches(9);table.columns[1].width=Inches(3.1)
                if key=='records':
                    for column,width in zip(table.columns,[1.4,6.1,2.3,2.3]):column.width=Inches(width)
            if key=='quality':
                for offset in range(0,len(report['notes']),2):text(page('Reporting definitions'),'\n\n'.join(report['notes'][offset:offset+2]),.7,2.1,11.8,4.1,22)
    out=io.BytesIO();prs.save(out);return out.getvalue()


def render_export(report,fmt,sections,layout):
    if not _RENDER_LOCK.acquire(blocking=False):raise WriteError('Another report is being exported. Try again shortly.',429)
    try:
        if fmt in ('csv','csv-jobs'):content=csv_export(report,sections,fmt=='csv-jobs');mime='text/csv; charset=utf-8';ext='csv'
        elif fmt=='pdf':content=pdf_export(report,sections,layout);mime='application/pdf';ext='pdf'
        elif fmt=='docx':content=docx_export(report,sections,layout);mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document';ext='docx'
        else:content=pptx_export(report,sections,layout);mime='application/vnd.openxmlformats-officedocument.presentationml.presentation';ext='pptx'
        return content,mime,'creative-services-'+layout+'-'+report['filters']['start']+'-'+report['filters']['end']+('-jobs' if fmt=='csv-jobs' else '')+'.'+ext
    finally:_RENDER_LOCK.release()
