/* Fictional training content only. Lessons never supply authority or live job IDs. */
const lesson=(id,title,intro,points,practice)=>({id,title,intro,points,practice});
const details=lesson('details','Read the full job','The card is a starting point. Open View job to see the complete request.',[
  'Check the job number and title so you know you opened the intended project.',
  'Read Project details & notes, deliverables, task type, dates and reference files together.',
  'Requested due date is the customer’s request. Final due date records the team’s confirmed delivery date.',
  'A missing structured field may already be answered in the notes or references.'
],'details');
const references=lesson('references','Use reference files and links','Keep examples and source material with the job.',[
  'Use the reference count on a card or the Reference files & links section on the details page.',
  'Preview supported files or download a reference to inspect it. A filename alone is not the file’s contents.',
  'On an editable job, Add reference files adds a new attachment. Existing files are retained.',
  'Copied projects show references read-only. A requester sees only their submitted files and files explicitly shared with them.'
],'references');
const ai=lesson('ai','Review an AI brief','An AI draft is a proposal for you to review, not a replacement for the original request.',[
  'On an eligible job, prepare its AI context and select the references your agent should read.',
  'Ask your authorized agent to extract supplied facts first, then draft the brief, tasks and only necessary follow-up questions.',
  'Import the analysis and review evidence, missing information, conflicts and reference coverage.',
  'Accepting a brief records a portal review. It does not apply suggested job fields or send questions to the customer. Changed sources require a fresh context.'
],'ai');
const find=lesson('find','Find work again','Use the views and filters to find the record you need.',[
  'Search by job number, title, requester or task type. Use designer and stage filters to narrow the board.',
  'Switch between Board and List. View job opens the details for that individual record.',
  'The project source filter separates copied read-only projects from editable test records.',
  'Completed & archived retains closed work and its references; completed work is excluded from active workload totals.'
],'find');
const finish=lesson('finish','You are ready','The walkthrough is complete. Your practice has not changed any live project.',[
  'Use Help → Tutorials whenever you want to replay the full walkthrough or revisit one chapter.',
  'Each account’s permissions still determine its available controls.',
  'When an operation cannot be confirmed, refresh and inspect the saved job before repeating it.',
  'You can leave this guide at any point. It will open again only when you choose to run it.'
],'finish');
export const TUTORIALS={
  designer:{label:'Designer',description:'Learn offers, My work, references, project updates and completion.',lessons:[
    lesson('workspace','Find your workspace','Your signed-in account determines which requests and assignments you can see.',[
      'My work contains accepted active projects assigned to you.',
      'Pending offers need your response before they become accepted assignments.',
      'All projects shows records available to your account. It does not grant access to everyone’s work.',
      'A Copied project · Read-only label means you can inspect that sample but cannot edit or move it.'
    ],'workspace'),
    lesson('offers','Accept or decline an offer','Review the request before deciding whether you can take it.',[
      'Open an offer to read its scope, due dates and references.',
      'Accept this job records your own acceptance. The project then appears in My work.',
      'Decline / return to Graphics returns the request for coordination.',
      'A coordinator can offer work, but cannot record acceptance on your behalf.'
    ],'offers'),details,references,
    lesson('editing','Update project information','Use Edit job when your account has permission to make changes.',[
      'Keep the title, project details, deliverables, dates, estimate and priority useful to the team.',
      'Preserve original request facts and distinguish requested dates from confirmed dates.',
      'Save only intentional changes, then check the confirmed result.',
      'If another person changed the job, refresh and review the latest values before saving again.'
    ],'editing'),
    lesson('stages','Move work through its stages','Stage changes communicate the current state of an accepted assignment.',[
      'Use the stage control on the details page, or drag an editable assigned card between lanes.',
      'In Progress means work has started; In Review means it is being reviewed.',
      'Mark Completed when the work is complete. Archive retains the record and its files.',
      'A stage change does not automatically send an email, create a SCOUT job or create a Dropbox folder.'
    ],'stages'),ai,
    lesson('customer-files','Share a file with the requester','When requester tracking is enabled, file visibility is an explicit choice.',[
      'Requester access appears only for eligible Microsoft-submitted jobs that you can edit.',
      'Share with requester makes that selected file version available in their own My Requests page.',
      'Internal references remain private until shared. Stop sharing withdraws that file’s tracking access without deleting it.',
      'A changed file must be shared again. This control does not change native Smartsheet sharing or send an email.'
    ],'sharing'),find,finish]},
  coordinator:{label:'Coordinator',description:'Learn intake review, routing, acceptance, workload and oversight.',lessons:[
    lesson('intake','Review incoming requests','New requests arrive in the New lane for review.',[
      'Open the request and read the customer’s purpose, intended audience, deliverables and requested date.',
      'Read additional notes and reference files before deciding that information is missing.',
      'Separate essential follow-up questions from helpful but optional details.',
      'A successful submission has a job number and a saved record. Inspect an uncertain result before submitting a duplicate.'
    ],'intake'),details,references,
    lesson('routing','Offer the right designer','Offer work to an invited designer after reviewing the request.',[
      'Use Offer to a designer on an eligible unaccepted project.',
      'Save designer offer records the request; it does not mean the designer has accepted.',
      'Historical names can appear on copied projects without becoming eligible offer recipients.',
      'Category routing and calendar-based availability are separate automation work, not decisions this screen makes automatically.'
    ],'routing'),
    lesson('responses','Follow the designer response','Acceptance belongs to the designer receiving the offer.',[
      'An offered request stays distinct from an accepted assignment.',
      'If the designer accepts, the assignment becomes visible in their My work view.',
      'If the designer declines, review the request and offer it to someone else.',
      'You cannot impersonate the designer’s acceptance. The example below simulates their response only inside training.'
    ],'responses'),
    lesson('workload','Use the workload view','Use estimates as a starting point for an availability conversation.',[
      'Team workload shows accepted active projects and their estimated hours.',
      'Completed and archived projects do not inflate active workload. Missing estimates are not invented.',
      'Pending offers remain separate from accepted work.',
      'Selected copied projects form a sample, not a complete staffing picture. Calendar availability is not connected.'
    ],'workload'),
    lesson('planning','Keep plans current','Check dates, estimates and priority as scope becomes clear.',[
      'Use Edit job to record permitted project changes.',
      'Confirm the delivery commitment separately from the customer’s requested date.',
      'Use stage filters and individual job pages to follow accepted work through review and completion.',
      'Refresh to see native Smartsheet changes; resolve stale-edit messages before retrying.'
    ],'editing'),ai,
    lesson('customer-files','Control customer-visible files','Customer tracking exposes an intentionally limited view of each owned request.',[
      'The requester sees their own submission, progress, confirmed assignment and dates.',
      'Internal notes, AI drafts, charge fields and other customers’ jobs stay out of that view.',
      'Use Requester access on an eligible file to explicitly share its current version or stop sharing it.',
      'Only requests with verified submission ownership are eligible. Copied jobs do not become customer-accessible automatically.'
    ],'sharing'),find,finish]},
  requester:{label:'Requester',description:'Learn how to submit a clear request and follow your own work.',lessons:[
    lesson('request','Send a clear request','Sign in with your organization Microsoft account to request creative work.',[
      'Your name and email come from your verified sign-in. No Smartsheet account is needed for this requester area.',
      'Give the project a short title and explain its purpose, audience, deliverables and requested date.',
      'Use Notes / additional details for anything else the designer should know.',
      'After submission, keep the generated job number. If confirmation is uncertain, retry the same submission instead of starting another.'
    ],'intake'),
    lesson('references','Include useful references','Attach the examples, approved copy or source material the team needs.',[
      'The form accepts supported images, PDFs and plain text, up to ten files and thirty megabytes each.',
      'A saved request can remain saved even if a file upload fails. Use Retry to continue that upload.',
      'My Requests lists files you submitted and files Creative Services explicitly shares with you.',
      'An internal file is not automatically visible just because it is attached to a job.'
    ],'references'),
    lesson('tracking','Follow your request','My Requests shows only jobs linked to your verified submission identity.',[
      'Open a request to see its current progress and original submitted information.',
      'Being assigned means an offer is pending. The designer’s name appears after acceptance.',
      'Requested delivery and confirmed delivery are separate dates.',
      'This tracking view is read-only. The progress bar shows the current stage, not an invented history of milestone dates.'
    ],'tracking'),finish]}
};
export function lessonsFor(track,{aiAvailable=true,trackingAvailable=true}={}){
  return TUTORIALS[track].lessons.filter(l=>(l.id!=='ai'||aiAvailable)&&(l.id!=='customer-files'||trackingAvailable));
}
export function newPractice(){return {title:'Science outreach flyer',description:'Invite scientists to a fictional open house. Use simple geometric artwork.',notes:'Requested delivery: December 4, 2026. Deliver one PDF and one editable source file.',stage:'Assigned',designer:'Alex Rivera',response:'',files:['Approved copy.txt'],preview:false,detail:false,created:false,brief:false,reviewed:false,shared:false,query:'',view:'active',message:''};}
export function practiceAction(job,action,value){
  const p={...job,files:[...job.files],message:''};
  if(action==='accept'){p.response='accepted';p.stage='Accepted';p.message='Practice offer accepted. It now belongs in My work.';}
  else if(action==='decline'){p.response='declined';p.stage='New';p.message='Practice offer declined and returned for coordination.';}
  else if(action==='details'){p.detail=!p.detail;}
  else if(action==='preview'){p.preview=!p.preview;}
  else if(action==='add-file'){if(!p.files.includes('Layout reference.png'))p.files.push('Layout reference.png');p.message='Example reference added in practice only.';}
  else if(action==='offer'){p.designer=value;p.response='';p.stage='Assigned';p.message='Practice offer saved. Acceptance still belongs to the designer.';}
  else if(action==='stage'){if(p.response!=='accepted')p.message='Accept the practice offer before starting this assignment.';else{p.stage=value;p.message=value==='Archived'?'Practice job archived; its record and references are retained.':'Practice stage updated.';}}
  else if(action==='edit'){p.title=value.title||p.title;p.date=value.date||p.date;p.message='Practice details saved. The real job and dates were not changed.';}
  else if(action==='create'){p.created=true;p.title=value||p.title;p.stage='New';p.message='Practice request PRACTICE-101 created. Nothing was submitted.';}
  else if(action==='brief'){p.brief=true;p.message='Example draft displayed. No model was called.';}
  else if(action==='review'){p.reviewed=true;p.message='Practice brief accepted in this walkthrough. No job fields applied and no questions sent.';}
  else if(action==='share'){p.shared=!p.shared;p.message=p.shared?'Example file is visible to the practice requester.':'Example file withdrawn from the practice requester; nothing was deleted.';}
  else if(action==='view'){p.view=value;}
  else if(action==='track'){p.stage=value;}
  return p;
}
