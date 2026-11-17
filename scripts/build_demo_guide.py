"""Build the private laptop demo guide. Uses only allowlisted config identifiers, never secrets."""
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
# Read only the known non-secret connection settings; never render the full config.
config = json.loads((ROOT/'.local/pilot-config.json').read_text())
origin, client_id = config['publicOrigin'], config['clientId']
complete_job, poster_job = config['ai']['jobIds'][:2]
expiry = datetime.fromisoformat(config['expiresAt']).astimezone(ZoneInfo('America/New_York'))
OUTPUT = ROOT/'output/pdf/Graphics-Portal-Demo-Startup-Guide.pdf'
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
fonts = Path.home()/'Library/Fonts'
pdfmetrics.registerFont(TTFont('Aptos', str(fonts/'Aptos.ttf')))
pdfmetrics.registerFont(TTFont('Aptos-Bold', str(fonts/'Aptos-Bold.ttf')))
pdfmetrics.registerFontFamily('Aptos', normal='Aptos', bold='Aptos-Bold', italic='Aptos', boldItalic='Aptos-Bold')
TOKENS = {'green':'#00662C','navy':'#00454D','gray':'#DBDCDB','white':'#FFFFFF','ink':'#373A36','blue':'#006BA6'}
C = {k:colors.HexColor(v) for k,v in TOKENS.items()}
styles = {
 'body':ParagraphStyle('Body', fontName='Aptos',fontSize=11,leading=15,textColor=C['ink'],spaceAfter=9),
 'small':ParagraphStyle('Small',fontName='Aptos',fontSize=9,leading=12,textColor=C['ink'],spaceAfter=6),
 'title':ParagraphStyle('Title',fontName='Aptos-Bold',fontSize=28,leading=31,textColor=C['green'],spaceAfter=12),
 'h2':ParagraphStyle('H2',fontName='Aptos-Bold',fontSize=15,leading=19,textColor=C['navy'],spaceBefore=11,spaceAfter=8),
 'step':ParagraphStyle('Step',fontName='Aptos-Bold',fontSize=12,leading=16,textColor=C['navy'],spaceBefore=9,spaceAfter=4),
 'white':ParagraphStyle('White',fontName='Aptos',fontSize=11,leading=15,textColor=C['white']),
 'cell':ParagraphStyle('Cell',fontName='Aptos',fontSize=10,leading=13,textColor=C['ink']),
}
story=[]
def p(text, style='body'): return Paragraph(text,styles[style])
def add(text,style='body'): story.append(p(text,style))
def title(kicker,text):
 add(kicker.upper(),'small');add(text,'title')
def step(n,head,text):
 story.append(KeepTogether([p(str(n)+'. '+head,'step'),p(text)]))
def box(text):
 t=Table([[p(text,'white')]],colWidths=[504]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),C['green']),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]));story.append(t);story.append(Spacer(1,10))
def link(label,url):return '<link href="'+escape(url,{'"':'&quot;'})+'" color="'+TOKENS['blue']+'"><u>'+escape(label)+'</u></link>'
def local(label,path): return link(label,Path(path).as_uri())
def table(rows,widths):
 t=Table([[p(a,'cell'),p(b,'cell')] for a,b in rows],colWidths=widths,hAlign='LEFT')
 t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),0.5,C['gray']),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));story.append(t);story.append(Spacer(1,8))

# Page 1
TITLE='Graphics Portal | Demo startup guide'
title('ORNL Creative Services / Laptop DEV pilot','Start your demo')
add('November 17, 2026  |  macOS  |  Version 1.0','small')
box('<b>First time on this Mac:</b> save the App secret once using page 2. After that, the launcher supplies the App ID and secret automatically.')
add('Your project folder','h2')
add(local('Open the project folder',ROOT)+'<br/>'+escape(str(ROOT)).replace('/ORNL-Graphics-Portal','/<br/>ORNL-Graphics-Portal'),'small')
step(1,'Keep the laptop connected','Keep it awake and online for the whole demo. Connect GlobalProtect VPN if required for the test environment.')
step(2,'Start or reuse the tunnel', 'If its Terminal is already hosting, leave it running. Otherwise double-click <b>start-pilot-tunnel.command</b> in the project folder. Complete Microsoft sign-in if requested. Keep the Terminal open.')
step(3,'Start or reuse the app','If the app is already running, reuse it. Otherwise double-click <b>start-pilot.command</b>. It reads the App ID from private config and the secret from Keychain. Wait for <b>Authenticated pilot ready</b>. Keep this second Terminal open.')
step(4,'Open the live DEV portal',link('Open the live DEV portal',origin)+'<br/>'+escape(origin)+'<br/>Complete the Microsoft tunnel gate and use your invited Smartsheet account. Review the consent screen if it appears.')
step(5,'Confirm the demo is ready','Open a synthetic DEV job. If you plan to submit or edit jobs, check the save gates on page 3. A running server alone does not mean saves are enabled.')
add('<b>Two Terminal windows stay open:</b> one for the tunnel and one for the app. Closing either can interrupt the demo. The printed tunnel Hosting port URL must match the app URL above.','small')
story.append(PageBreak())

# Page 2
title('One-time setup / Keep this page','Save the secret once')
add('The App secret can be looked up again. You do not need to create a new app or rotate the secret simply because you did not save it earlier.')
step(1,'Open the existing Smartsheet app',link('Open Smartsheet','https://app.smartsheet.com/')+' using the account that registered the app. Select <b>Account &gt; Developer Tools</b>. Find <b>ORNL Graphics Portal - DEV Pilot</b> and open its <b>View/Edit</b> action.')
step(2,'Copy the right value','Copy <b>App secret</b> from that app\'s details modal. This is different from your Smartsheet password and a personal API token. Close the secret details before screen-sharing.')
step(3,'Run the credential setup',local('Open save-pilot-credentials.command',ROOT/'save-pilot-credentials.command')+' in the project folder. At the hidden prompt, paste the secret and press Return. <b>No characters or dots appear while typing.</b> Wait for <b>App secret saved in macOS Keychain</b>.')
step(4,'Review any macOS prompt','macOS may request login Keychain access for the local Python interpreter. Review it on your Mac. A denied or locked Keychain stops setup without silently replacing an existing item.')
add('What is saved, and where','h2')
table([
 ('<b>App client ID</b>', 'Already in <b>.local/pilot-config.json</b>. If missing, setup asks once and saves only this identifier there.<br/>'+escape(client_id)),
 ('<b>App secret</b>', 'Stored in macOS Keychain under <b>ORNL Graphics Portal - Smartsheet OAuth DEV</b>; its account is the App client ID. Retrieved into server memory at launch.'),
], [120,384])
add('Run setup again only after an intentional secret rotation, a client-ID change, or a move to another Mac. Nothing embeds the secret in this PDF, a script, command arguments, environment variables or a plaintext settings file.','small')
add('Finding the modal later','h2')
add('There is no documented standalone URL for this app-details modal. Bookmark Smartsheet and follow the Account menu route above. '+link('Official Developer Tools instructions','https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/oauth')+'.','small')
story.append(PageBreak())

# Page 3
title('Before presenting / DEV only','Run a reliable demo')
add('Use the tunnel link for live data. '+link('GitHub Pages','https://adammalin.github.io/ORNL-Graphics-Portal/')+' contains fictional DEMO jobs and does not write to the development sheet.')
add('Before a demo that changes data','h2')
table([
 ('<b>Workflow review</b>', 'The native DEV sheet workflow review must be less than 24 hours old. Review all native workflows before renewing it; changing a timestamp alone is not a review.'),
 ('<b>Permissions</b>', 'The invited Smartsheet user needs their own DEV sheet permissions. Each designer must accept their own job offer. The launcher does not grant access.'),
 ('<b>Expiry</b>', 'Current app expiry: <b>'+escape(expiry.strftime('%B %d, %Y at %I:%M %p %Z'))+'</b>. Tunnel access may expire earlier. The scripts do not extend either expiry.'),
], [120,384])
add('A short demonstration path','h2')
step(1,'Show the board and a job','Open an existing synthetic DEV job from the board. Show its title, original request, stage, task type, references and other details.')
step(2,'Show the AI brief pilot','Open job <b>'+escape(poster_job)+'</b> to show the poster draft: a brief, proposed tasks, attachment evidence and one question about missing printed dimensions. Job <b>'+escape(complete_job)+'</b> is the complete-request example with no follow-up questions.')
step(3,'Explain what is running','Stage 1 uses the signed-in user\'s Codex agent to analyze prepared context and import a draft. It does not run a model automatically. Field suggestions are proposals, not applied Smartsheet updates. Only the two selected synthetic jobs have this AI pilot enabled.')
add('If you demonstrate a new request or stage update, use synthetic content and verify the result after saving. The existing DEV controls remain in force. AI drafts persist in private portal storage; they are not published into native Smartsheet dashboards.','small')
add('<b>Current qualification:</b> one real coordinator account has passed the live AI flow. The second designer\'s own-account test remains pending. Email, SCOUT, Dropbox and automatic AI field application are not connected.','small')
story.append(PageBreak())

# Page 4
title('Sign-in / Recovery','Why does Allow reappear?')
add('There are two different credentials: the <b>App secret</b> identifies the portal, while each person\'s <b>OAuth access token</b> represents their permission to use Smartsheet. Keychain saves the first; it does not preserve the second.')
table([
 ('<b>What happened?</b>', '<b>What to expect now</b>'),
 ('Navigate or reload', 'A valid portal session continues without a new authorization.'),
 ('App server restarts', 'All in-memory user sessions end. Users sign in again and can see Allow again.'),
 ('Idle or signed out', 'Sessions expire after 30 idle minutes, explicit sign-out, or at most six hours (possibly earlier). A fresh sign-in can require Allow again.'),
 ('Another browser', 'It has no existing portal session and must sign in.'),
], [140,364])
add('This is a current pilot behavior, not just a one-time installation prompt. Smartsheet supports refresh tokens. A future change could persist each user\'s session and tokens securely, with encryption and revocation handling, to reduce interruptions. That is separate from this launcher change. Provider policy can still require reauthorization.','small')
add('Quick recovery','h2')
table([
 ('<b>Keychain denied</b>', 'Unlock the login Keychain and retry. Re-run credential setup to replace an intentionally changed secret.'),
 ('<b>Port 4175 in use</b>', 'Reuse the existing server Terminal, or stop it with Ctrl+C before relaunching. The launcher does not kill it.'),
 ('<b>Tunnel unavailable</b>', 'Check its Terminal, network, Microsoft sign-in and access expiry.'),
 ('<b>Saves paused</b>', 'Check the 24-hour workflow review, writes switch, pilot expiry and your own native sheet permissions.'),
], [140,364])
add('When the demo ends','h2')
add('Press <b>Ctrl+C</b> in the app Terminal, then the tunnel Terminal. Keep the private config, SQLite state and Keychain item. Jobs, references, drafts and reviews persist; user login sessions do not.','small')
add('More help: '+local('local startup instructions',ROOT/'docs/demo-startup.md')+' | '+link('Smartsheet OAuth and consent','https://developers.smartsheet.com/api/smartsheet/guides/advanced-topics/oauth')+' | '+link('Token refresh reference','https://developers.smartsheet.com/api/smartsheet/openapi/tokens/tokens-getorrefresh'),'small')

def page(canvas,doc):
 canvas.saveState()
 canvas.setFillColor(C['green']);canvas.rect(0,774,612,18,fill=1,stroke=0)
 canvas.setStrokeColor(C['gray']);canvas.line(54,43,558,43)
 canvas.setFont('Aptos',8);canvas.setFillColor(C['ink'])
 canvas.drawString(54,29,'Graphics Portal / DEV demo guide / Draft operating instructions')
 canvas.drawRightString(558,29,str(doc.page))
 canvas.restoreState()

SimpleDocTemplate(str(OUTPUT),pagesize=(612,792),rightMargin=54,leftMargin=54,topMargin=42,bottomMargin=54,title=TITLE,author='ORNL Creative Services',subject='Laptop DEV demo startup, Keychain setup and Smartsheet consent').build(story,onFirstPage=page,onLaterPages=page)
print(OUTPUT)
