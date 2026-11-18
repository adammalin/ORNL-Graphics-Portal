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
    return ' | '.join(label+': '+plain(names.get(report['filters'][key],report['filters'][key]) if key=='designer' else {'all':'All approved DEV records','copied':'Copied DEV projects','test':'Test jobs'}.get(report['filters'][key],report['filters'][key]) if key=='source' else report['filters'][key]) for key,label in labels.items() if report['filters'].get(key)) or 'All approved records'


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
            m=r['reporting'];values=[r['id'],r['title'],r['stage'],' | '.join(r['taskTypes']),r['designer'],r['department'],r['createdDate'],r['completedDate'],r['confirmedDueDate'],r['estimatedHours'],r['countedCompleted'],'Copied DEV source' if r['copied'] else 'DEV test',*[m.get(k,'') for k in ['directorate','division','impactLevel','impactCategory','impactJustification','impactStatement','intendedOutcome','observedOutcome','evidenceUrl','disposition']],r['url'],report['generatedAt'],report['sourceVersion'],report['filters']['start'],report['filters']['end'],filter_text(report),report['scope'],json.dumps(report['quality'],sort_keys=True),' | '.join(report['notes'])]
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
    height=2.35 if key=='monthly' else max(1.5,min(3.5,.34*len(report[key][:8])+.7))
    fig=Figure(figsize=(7,height),dpi=180,facecolor='#'+WHITE);FigureCanvasAgg(fig);ax=fig.subplots()
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
        ax.set_yticks(list(range(len(rows))),[textwrap.fill(compact(r['label'],55),28) for r in rows]);ax.invert_yaxis()
    from matplotlib.ticker import MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(integer=True)) if key!='monthly' else ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    for label in list(ax.get_xticklabels())+list(ax.get_yticklabels()):label.set_fontproperties(font)
    ax.tick_params(colors='#'+INK);fig.tight_layout(pad=1.1);out=io.BytesIO();fig.savefig(out,format='png',dpi=180);return out.getvalue()


def document_table(report,key):
    """Readable document labels and fixed widths in points, shared by PDF/Word."""
    header,rows=section_table(report,key)
    widths={'summary':[390,114],'quality':[390,114],'monthly':[252,126,126],
            'types':[400,104],'stages':[400,104],'directorates':[400,104],
            'designers':[216,72,72,72,72],'records':[64,248,82,110]}[key]
    if key=='designers':header=['Designer','Completed','Active','Offers','Est. hours']
    if key=='records':rows=[[compact(value,500) if j==1 else value for j,value in enumerate(row)] for row in rows]
    return header,rows,widths


def report_period(report):
    from datetime import date
    dates=[date.fromisoformat(report['filters'][key]) for key in ['start','end']]
    return ' – '.join(f'{d:%b} {d.day}, {d.year}' for d in dates)


def report_layout_name(layout):
    return {'executive':'Executive overview','operations':'Operations review','impact':'Impact briefing'}[layout]


def pdf_export(report,sections,layout):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.pagesizes import letter
    require_assets()
    pdfmetrics.registerFont(TTFont('ReportAptos',str(ASSET_DIR/'Aptos.ttf')))
    pdfmetrics.registerFont(TTFont('ReportAptosBold',str(ASSET_DIR/'Aptos-Bold.ttf')))
    styles=getSampleStyleSheet()
    for st in styles.byName.values():st.fontName='ReportAptos';st.textColor=colors.HexColor('#'+INK)
    styles['Title'].fontName='ReportAptosBold';styles['Title'].fontSize=22;styles['Title'].leading=26;styles['Title'].alignment=0;styles['Title'].spaceAfter=6
    for name,size in [('Heading1',16),('Heading2',11)]:
        st=styles[name];st.fontName='ReportAptosBold';st.fontSize=size;st.leading=size+4;st.textColor=colors.HexColor('#'+GREEN);st.spaceBefore=14;st.spaceAfter=7;st.keepWithNext=True
    styles['BodyText'].fontSize=10;styles['BodyText'].leading=13;styles['BodyText'].spaceAfter=6
    meta=ParagraphStyle('Metadata',parent=styles['BodyText'],fontSize=8.5,leading=11,textColor=colors.HexColor('#'+NAVY),spaceAfter=4)
    cell=ParagraphStyle('Cell',fontName='ReportAptos',fontSize=9.5,leading=12,textColor=colors.HexColor('#'+INK))
    number=ParagraphStyle('NumericCell',parent=cell,alignment=2)
    head=ParagraphStyle('TableHeader',parent=cell,fontName='ReportAptosBold',textColor=colors.HexColor('#'+NAVY))
    p=lambda value,style=styles['BodyText']:Paragraph(escape(plain(value)).replace('\n','<br/>'),style)
    content=[p(report['title'],styles['Title']),p(report_layout_name(layout)+' | '+report_period(report),meta),
             p(report['notes'][0],meta),p(filter_text(report),meta),
             p('Generated '+report['generatedAt']+' | Source version '+str(report['sourceVersion']),meta)]
    for key in sections:
        heading=p(SECTIONS[key],styles['Heading1'])
        if key in ('monthly','types','stages','directorates','designers'):
            png=chart_png(report,key)
            if png:
                image=Image(io.BytesIO(png));image.drawHeight=504*image.imageHeight/image.imageWidth;image.drawWidth=504
                content.append(KeepTogether([heading,image,Spacer(1,5)]))
            else:content.append(heading)
            if key!='monthly' and (len(report[key])>8 or any(len(r['label'])>55 for r in report[key][:8])):content.append(p('Chart shows up to 8 categories; complete labels and counts appear in the table.',meta))
        else:content.append(heading)
        if key=='impact':
            content.append(p(f'{len(report["highlights"])} high or strategic jobs. Up to 8 spotlights are included; use the job CSV for all records.'))
            for r in report['highlights'][:8]:
                content.append(p(r['id']+' '+compact(r['title'],500),styles['Heading2']))
                for label,field in [('Classification','impactLevel'),('Justification','impactJustification'),('Impact statement','impactStatement'),('Intended outcome','intendedOutcome'),('Observed outcome','observedOutcome'),('Evidence','evidenceUrl')]:content.append(p(label+': '+(r['reporting'].get(field) or 'Not recorded')))
            if not report['highlights']:content.append(p('No coordinator-classified high or strategic impact jobs are recorded for this period. This is not evidence of no impact.'))
            continue
        header,rows,widths=document_table(report,key)
        if key=='records':
            content.append(p('Long job titles are shortened; CSV retains complete values.'+(f' Showing 200 of {len(rows)} projects.' if len(rows)>200 else ''),meta));rows=rows[:200]
        if rows:
            table=Table([[p(v,head) for v in header]]+[[p(shown(v),number if j and key!='records' else cell) for j,v in enumerate(row)] for row in rows],repeatRows=1,hAlign='LEFT',colWidths=widths)
            commands=[('BACKGROUND',(0,0),(-1,0),colors.HexColor('#'+GRAY)),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#'+NAVY)),
                ('LINEBELOW',(0,1),(-1,-1),.35,colors.HexColor('#'+GRAY)),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]
            if key!='records':commands.append(('ALIGN',(1,1),(-1,-1),'RIGHT'))
            table.setStyle(TableStyle(commands))
            if key in ('summary','quality') and content[-1] is heading:content.pop();content.append(KeepTogether([heading,table]))
            else:content.append(table)
        else:content.append(p('No matching data.'))
        if key=='designers':content.append(p('Completed: verified completions in the period. Active, offers and estimates: current work across all dates within the other filters. Estimates are not actual effort.',meta))
        if key=='quality':
            for note in report['notes']:content.append(p(note,meta))
    out=io.BytesIO()
    def footer(canvas,doc):
        canvas.setFont('ReportAptos',8);canvas.setFillColor(colors.HexColor('#'+NAVY));canvas.drawString(54,28,'Creative Services | DEV sample | '+report['filters']['start']+' to '+report['filters']['end']);canvas.drawRightString(558,28,str(doc.page))
    SimpleDocTemplate(out,pagesize=letter,leftMargin=54,rightMargin=54,topMargin=40,bottomMargin=48,title=report['title']).build(content,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()


def docx_export(report,sections,layout):
    from docx import Document
    from docx.shared import Inches,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.style import WD_STYLE_TYPE
    require_assets();doc=Document();sec=doc.sections[0]
    sec.page_width=Inches(8.5);sec.page_height=Inches(11);sec.top_margin=sec.bottom_margin=Inches(.65);sec.left_margin=sec.right_margin=Inches(.75)
    sec.header_distance=sec.footer_distance=Inches(.25)
    for name,size in [('Normal',10),('Title',22),('Heading 1',16),('Heading 2',11)]:
        st=doc.styles[name];st.font.name='Aptos';st.font.size=Pt(size);st.font.color.rgb=RGBColor.from_string(GREEN if name.startswith('Heading') else INK)
        st.paragraph_format.space_after=Pt(6);st.paragraph_format.line_spacing=1.1
        if name.startswith('Heading'):st.font.bold=True;st.paragraph_format.space_before=Pt(14);st.paragraph_format.keep_with_next=True
    doc.styles['Title'].font.bold=True
    border=doc.styles['Title'].element.find(qn('w:pPr')).find(qn('w:pBdr'))
    if border is not None:border.getparent().remove(border)
    meta=doc.styles.add_style('Report metadata',WD_STYLE_TYPE.PARAGRAPH);meta.base_style=doc.styles['Normal'];meta.font.size=Pt(8.5);meta.font.color.rgb=RGBColor.from_string(NAVY);meta.paragraph_format.space_after=Pt(4)
    doc.add_paragraph(report['title'],'Title');doc.add_paragraph(report_layout_name(layout)+' | '+report_period(report),'Report metadata')
    for value in [report['notes'][0],filter_text(report),'Generated '+report['generatedAt']+' | Source version '+str(report['sourceVersion'])]:doc.add_paragraph(value,'Report metadata')
    hp=sec.header.paragraphs[0];hp.text='Creative Services | Management reporting';hp.style='Report metadata'
    fp=sec.footer.paragraphs[0];fp.style='Report metadata';fp.text='ORNL | DEV sample | Page '
    for instruction in ['PAGE','NUMPAGES']:
        if instruction=='NUMPAGES':fp.add_run(' of ')
        field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),instruction);fp._p.append(field)
    for key in sections:
        doc.add_heading(SECTIONS[key],1)
        if key in ('monthly','types','stages','directorates','designers'):
            png=chart_png(report,key)
            if png:
                para=doc.add_paragraph();para.paragraph_format.space_after=Pt(5);para.add_run().add_picture(io.BytesIO(png),width=Inches(7))
            if key!='monthly' and (len(report[key])>8 or any(len(r['label'])>55 for r in report[key][:8])):doc.add_paragraph('Chart shows up to 8 categories; complete labels and counts appear in the table.','Report metadata')
        if key=='impact':
            doc.add_paragraph(f'{len(report["highlights"])} high or strategic jobs. Up to 8 spotlights are included; use job CSV for all records.')
            for r in report['highlights'][:8]:
                doc.add_heading(plain(r['id']+' '+compact(r['title'],500)),2)
                for label,field in [('Classification','impactLevel'),('Justification','impactJustification'),('Impact statement','impactStatement'),('Intended outcome','intendedOutcome'),('Observed outcome','observedOutcome'),('Evidence','evidenceUrl')]:doc.add_paragraph(label+': '+plain(r['reporting'].get(field) or 'Not recorded'))
            if not report['highlights']:doc.add_paragraph('No high or strategic impact classifications are recorded for this period. This is not evidence of no impact.')
            continue
        header,rows,widths=document_table(report,key)
        if key=='records':
            doc.add_paragraph('Long job titles are shortened; CSV retains complete values.'+(f' Showing 200 of {len(rows)} projects.' if len(rows)>200 else ''),'Report metadata');rows=rows[:200]
        if not rows:doc.add_paragraph('No matching data.');continue
        table=doc.add_table(rows=1,cols=len(header));table.autofit=False;table.alignment=WD_TABLE_ALIGNMENT.LEFT
        pr=table._tbl.tblPr
        width=pr.find(qn('w:tblW'));width.set(qn('w:type'),'dxa');width.set(qn('w:w'),str(504*20))
        borders=OxmlElement('w:tblBorders')
        for side in ['top','left','bottom','right','insideH','insideV']:
            edge=OxmlElement('w:'+side);edge.set(qn('w:val'),'single' if side in ('bottom','insideH') else 'nil');edge.set(qn('w:sz'),'4');edge.set(qn('w:color'),GRAY);borders.append(edge)
        pr.append(borders)
        margins=OxmlElement('w:tblCellMar')
        for side in ['top','left','bottom','right']:
            item=OxmlElement('w:'+side);item.set(qn('w:type'),'dxa');item.set(qn('w:w'),'80' if side in ('top','bottom') else '120');margins.append(item)
        pr.append(margins)
        for column,width in zip(table.columns,widths):column.width=Pt(width)
        for i,values in enumerate([header]+rows):
            row=table.rows[0] if i==0 else table.add_row();rowpr=row._tr.get_or_add_trPr();rowpr.append(OxmlElement('w:cantSplit'))
            if i==0:rowpr.append(OxmlElement('w:tblHeader'))
            for j,(cell,value,width) in enumerate(zip(row.cells,values,widths)):
                cell.width=Pt(width);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.TOP;cell.text=plain(shown(value))
                if i==0:
                    shade=OxmlElement('w:shd');shade.set(qn('w:fill'),GRAY);cell._tc.get_or_add_tcPr().append(shade)
                for para in cell.paragraphs:
                    para.paragraph_format.space_before=Pt(0);para.paragraph_format.space_after=Pt(0);para.paragraph_format.line_spacing=1.05;para.paragraph_format.keep_with_next=(i<len(rows) if key in ('summary','quality') or (key!='records' and len(rows)<=12) else i==0)
                    if i and j and key!='records':para.alignment=WD_ALIGN_PARAGRAPH.RIGHT
                    for run in para.runs:run.font.name='Aptos';run.font.size=Pt(9.5);run.font.bold=i==0;run.font.color.rgb=RGBColor.from_string(NAVY if i==0 else INK)
        if key=='designers':doc.add_paragraph('Completed: verified completions in the period. Active, offers and estimates: current work across all dates within the other filters. Estimates are not actual effort.','Report metadata')
        if key=='quality':
            for note in report['notes']:doc.add_paragraph(note,'Report metadata')
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
    title_layout=next((item for item in prs.slide_layouts if item.name=='Title | Standard'),None)
    if title_layout is None:raise WriteError('Install the approved ORNL template with its Title | Standard layout.',503)
    cover=prs.slides.add_slide(title_layout)
    fields={0:'Creative Services\nManagement Report',14:report_period(report),1:'MANAGEMENT REPORTING',
            15:report_layout_name(layout),17:'DEV sample · Generated '+report['generatedAt'][:10]}
    if set(fields)-{shape.placeholder_format.idx for shape in cover.placeholders}:
        raise WriteError('The approved title layout is missing its native report placeholders.',503)
    for shape in cover.placeholders:
        idx=shape.placeholder_format.idx
        if shape.has_text_frame:
            shape.text=fields.get(idx,'');tf=shape.text_frame;tf.word_wrap=True
            tf.margin_top=tf.margin_bottom=tf.margin_left=tf.margin_right=0
            for para in tf.paragraphs:
                para.space_before=Pt(0);para.space_after=Pt(0);para.line_spacing=1.05
                para.font.name='Aptos';para.font.size=Pt({0:32,14:12,1:12,15:24,17:12}.get(idx,12));para.font.bold=idx in (0,1)
    cover.notes_slide.notes_text_frame.text=report['title']+'\n'+report['notes'][0]+'\nGenerated '+report['generatedAt']+' | Source version '+str(report['sourceVersion'])
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
