import { STAGES, CLOSED, DESIGNERS, TASK_TYPES, assignedDesigner, isActive, myProjects, metrics, workload, moveProject, safeUrl, escapeHtml as e, filterProjects, validateRequest, daysUntil } from './domain.js';
import { demoProjects } from './demo-data.js';

const paths = {
  home:'M3 11 12 3l9 8M5 10v11h5v-7h4v7h5V10',
  board:'M3 4h5v16H3zM10 4h5v11h-5zM17 4h4v14h-4z',
  projects:'M3 5h7l2 2h9v13H3zM3 10h18',
  chart:'M4 20V4M4 20h17M8 16v-5M13 16V6M18 16v-8',
  archive:'M3 4h18v5H3zM5 9v12h14V9M10 13h4',
  plus:'M12 5v14M5 12h14',
  search:'M16.5 16.5 21 21M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0',
  arrow:'M4 12h16M14 6l6 6-6 6',
  clock:'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  calendar:'M4 5h16v16H4zM8 3v4M16 3v4M4 10h16',
  check:'m5 12 4 4L19 6',
  file:'M5 3h9l5 5v13H5zM14 3v6h5M8 13h8M8 17h6',
  link:'M9 15 15 9M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0',
  people:'M8 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8M1 21v-2a7 7 0 0 1 14 0v2M16 4a4 4 0 0 1 0 8M18 15a6 6 0 0 1 5 6',
  list:'M8 6h13M8 12h13M8 18h13M3 6h1M3 12h1M3 18h1',
  upload:'M12 16V3M7 8l5-5 5 5M4 15v6h16v-6',
  brief:'M5 3h14v18H5zM8 7h8M8 11h8M8 15h5',
  spark:'m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z',
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.file}"/></svg>`;
document.querySelectorAll('[data-icon]').forEach(el => el.innerHTML = icon(el.dataset.icon));
const main = document.querySelector('main');
const dialog = document.querySelector('#dialog');
const config = window.PORTAL_CONFIG || { dataMode:'demo' };
const authenticated = config.dataMode === 'pilot';
const connected = authenticated || ['dev-readonly','dev-write'].includes(config.dataMode);
const state = { aiModule:null, actor:null, csrf:null, canCreate:false, teamWorkload:null, taskTypes:TASK_TYPES, taskTypeMultiple:false, priorities:['Normal','High'], saving:false, requestKey:crypto.randomUUID(), mode:connected ? 'loading' : 'demo', projects:connected?[]:demoProjects(), designers:connected?[]:DESIGNERS, person:connected?'coordinator':'alex', view:'board', query:'', filterDesigner:'', filterStage:'', filterSource:'all', lastWorkspace:'my-work', error:'', files:new Map(), dragged:null };
const live = () => state.mode === 'dev-write';
const readonly = () => !['demo','dev-write'].includes(state.mode);
const person = id => state.designers.find(d => d.id === id);
const personName = id => person(id)?.name || (id ? 'Assigned designer' : 'Not yet assigned');
const formatDate = value => { if (!value) return 'Not set'; const d = new Date(`${value.slice(0,10)}T12:00:00`); return Number.isNaN(+d) ? 'Not set' : new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric'}).format(d); };
const hoursLabel = p => p.hours == null ? 'Not estimated' : `${Number(p.hours) || 0}h estimated`;
const stageTag = value => `<span class="stage stage-${String(value).toLowerCase().replaceAll(' ','-')}">${e(value)}</span>`;
const initials = name => name.split(/\s+/).map(n => n[0]).slice(0,2).join('').toUpperCase();
const avatar = id => `<span class="avatar ${e(id)}" aria-hidden="true">${e(person(id)?.initials || initials(personName(id)))}</span>`;
const route = () => { try { return decodeURIComponent(location.hash.slice(1) || '/').split('?')[0]; } catch { return '/not-found'; } };
const findProject = id => state.projects.find(p => p.id === id);
const isCoordinator = () => authenticated ? state.actor?.role === 'coordinator' : state.person === 'coordinator';
const canEdit = p => !p.readOnly && !readonly() && (authenticated ? p.permissions?.edit === true : isCoordinator() || assignedDesigner(p) === state.person);
const workloadRows = () => authenticated && state.teamWorkload ? state.teamWorkload : workload(state.projects,state.designers);
const uniqueAttachments = p => (p.attachments || []).filter(f => f && f.name);
function toast(message, error = false) { const el=document.querySelector('#toast'); el.textContent=message; el.classList.toggle('error',error); el.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.hidden=true,6500); }
function modal(title, body, footer='') {
  if (dialog.open) dialog.close();
  dialog.innerHTML=`<div class="dialog-header"><h2 id="dialog-title">${e(title)}</h2><button class="dialog-close" data-action="close-dialog" aria-label="Close dialog">×</button></div><div class="dialog-body">${body}</div>${footer ? `<div class="dialog-footer">${footer}</div>` : ''}`;
  dialog.showModal();
}
function heading(title, subtitle, eyebrow='Graphics workspace', actions='') { return `<div class="page-heading"><div><div class="eyebrow">${e(eyebrow)}</div><h1>${e(title)}</h1><p>${e(subtitle)}</p></div>${actions ? `<div class="page-actions">${actions}</div>` : ''}</div>`; }
function breadcrumbs(items) { return `<div class="breadcrumbs"><a href="#/">Overview</a>${items.map(([label,url])=>`<span>/</span>${url?`<a href="${url}">${e(label)}</a>`:e(label)}`).join('')}</div>`; }
function stats(projects) { const m=metrics(projects); return `<div class="stats">${[[m.active,'Active projects','Completed work excluded','projects'],[m.dueSoon,'Due in 7 days',m.overdue ? `${m.overdue} overdue` : 'No overdue projects','calendar'],[m.newRequests,'New requests','Awaiting team review','brief'],[`${m.hours}h`,'Estimated effort','Across active projects','clock']].map(([n,label,note,i])=>`<div class="stat"><div class="stat-top"><span class="stat-label">${label}</span>${icon(i)}</div><strong>${n}</strong><small>${note}</small></div>`).join('')}</div>`; }
const copiedLabel = p => p.readOnly ? '<span class="source-badge">Copied project · Read-only</span>' : '';
const copiedNotice = () => state.projects.some(p=>p.readOnly) ? '<div class="notice"><strong>Selected projects from the DEV copy.</strong> Copied projects are read-only. Test records remain available for editing. Workload totals reflect this selected sample.</div>' : '';
function card(p) {
  const designer=assignedDesigner(p), due=daysUntil(p.dueDate), files=uniqueAttachments(p).length;
  return `<article class="card" data-project="${e(p.id)}" ${p.readOnly?'data-readonly="true"':''} ${canEdit(p)?'draggable="true"':''} aria-label="${e(`${p.id}: ${p.title}`)}">
    <div class="card-top"><span class="job-id">${e(p.id)}</span>${p.priority === 'High'?'<span class="priority priority-high">High priority</span>':stageTag(p.stage)}</div>
    ${copiedLabel(p)}<h3><a href="#/projects/${encodeURIComponent(p.id)}">${e(p.title)}</a></h3><p class="card-type">${e(p.taskType || 'Type not specified')}</p>
    <div class="card-meta"><span class="${due !== null && due < 0 && isActive(p)?'overdue':''}">${icon('calendar')}${e(p.dueDate ? formatDate(p.dueDate).replace(/, \d{4}$/,'') : 'Date not set')}</span><span>${icon('clock')}${e(hoursLabel(p))}</span></div>
    ${files || p.references?.length ? `<a class="card-reference" href="#/projects/${encodeURIComponent(p.id)}/references">${icon('file')}${files ? `${files} reference file${files===1?'':'s'}` : ''}${files && p.references?.length?' · ':''}${p.references?.length ? `${p.references.length} link${p.references.length===1?'':'s'}` : ''}</a>` : ''}
    <div class="card-footer"><span class="person">${designer?avatar(designer):''}${e(designer?personName(designer):p.requestedDesigner?(p.readOnly?`Requested: ${personName(p.requestedDesigner)}`:`Offered to ${personName(p.requestedDesigner).split(' ')[0]}`):'Unassigned')}</span><a class="card-link" href="#/projects/${encodeURIComponent(p.id)}">View job →</a></div>
  </article>`;
}
function offersForCurrent() { return state.projects.filter(p => !p.readOnly && isActive(p) && p.requestedDesigner === state.person && !['accepted','declined'].includes(p.response)); }
function offerPanel() {
  const offers=offersForCurrent();
  if(!offers.length) return `<section class="panel offer-panel"><div class="eyebrow">Project offers</div><h3>No offers waiting</h3><p>New project offers will appear here for the selected ${connected?'test':'demo'} designer.</p><a class="card-link" href="#/projects">Explore the team board →</a></section>`;
  const p=offers[0];return `<section class="panel offer-panel"><div class="eyebrow">${icon('brief')} Your next project?</div><h3>${e(p.title)}</h3><p>${e(p.taskType)}<br>Requested by ${e(p.requestor)}<br>Due ${e(formatDate(p.dueDate))}</p><div class="offer-actions"><a class="button button-primary button-small" href="#/projects/${encodeURIComponent(p.id)}">Review offer →</a></div><p class="quiet-note">Assignment is confirmed only after you accept.</p></section>`;
}
function teamMini() { return `<section class="panel team-mini"><h3>Team at a glance</h3>${workloadRows().filter(d=>!connected||d.jobs||d.offers).slice(0,6).map(d=>`<div class="mini-person">${avatar(d.id)}<span><strong>${e(d.name)}</strong><br>${d.jobs} active project${d.jobs===1?'':'s'}</span><span>${d.hours}h</span></div>`).join('')}<p class="quiet-note">Estimated work, not confirmed availability.</p><a class="card-link" href="#/workload">Explore team workload →</a></section>`; }
function renderHome() {
  const own=person(state.person); const jobs=own?myProjects(state.projects,state.person):state.projects.filter(isActive);
  return `<section class="hero"><div><div class="eyebrow">Graphics Portal · Workspace preview</div><h1>Your projects.<br>One shared workspace.</h1><p>Submit a clear request, follow the work, and keep project information close at hand.</p><div class="hero-actions"><a class="button button-energy" href="#/new">${icon('plus')}New project request</a><a class="button button-quiet" href="#/my-work">Explore my work ${icon('arrow')}</a></div></div><aside class="hero-aside">${icon('people')}<strong>For everyone<br>requesting Graphics work.</strong><p>Employee intake is part of the proposal—not limited to the Graphics team.</p><a href="#/new">Try the employee request form →</a></aside></section>
    ${stats(state.projects)}
    <div class="home-columns"><section><div class="section-heading"><div><h2>${own?'My active projects':'Active projects'}</h2><p>${own?`${e(own.name)} · ${authenticated?'Signed-in designer':connected?'Local test':'Demo designer'} view`:'Team workspace preview'}</p></div><a href="#/${own?'my-work':'projects'}">View board →</a></div><div class="project-grid">${jobs.slice(0,4).map(card).join('')||'<div class="empty-state"><p>No active assignments for this view.</p></div>'}</div></section><aside class="home-side">${offerPanel()}${teamMini()}</aside></div>
    <section class="steps-strip" aria-label="How the portal works"><article><b>01 / REQUEST</b><h3>Start with the project</h3><p>Share the goal, deliverables, dates and reference material.</p></article><article><b>02 / COORDINATE</b><h3>Find the right designer</h3><p>Graphics reviews the request and records the designer’s acceptance.</p></article><article><b>03 / DELIVER</b><h3>Keep the work together</h3><p>Follow progress from a job page, then retain the completed record.</p></article></section>`;
}
function collectionBase(type) {
  if(type==='archive') return state.projects.filter(p=>CLOSED.has(p.stage));
  if(type==='my-work') return myProjects(state.projects,state.person);
  return state.projects.filter(isActive);
}
function list(projects) { return `<div class="list-wrap"><table><thead><tr><th>Job / project title</th><th>Stage</th><th>Designer</th><th>Due date</th><th>Estimate</th><th>Details</th></tr></thead><tbody>${projects.map(p=>`<tr><td><span class="job-id">${e(p.id)}</span><br>${copiedLabel(p)}<br><a href="#/projects/${encodeURIComponent(p.id)}">${e(p.title)}</a></td><td>${stageTag(p.stage)}</td><td>${e(personName(assignedDesigner(p)))}</td><td>${e(formatDate(p.dueDate))}</td><td>${p.hours == null ? 'Not estimated' : `${Number(p.hours)||0}h`}</td><td><a href="#/projects/${encodeURIComponent(p.id)}">View job →</a></td></tr>`).join('')}</tbody></table></div>`; }
function collectionResults(type) {
  const projects=filterProjects(collectionBase(type),{query:state.query,designer:state.filterDesigner,stage:state.filterStage,source:state.filterSource}).sort((a,b)=>Number(!!b.readOnly)-Number(!!a.readOnly));
  if(!projects.length) return `<div class="empty-state"><h2>${type==='my-work'?'No matching active assignments':'No matching projects'}</h2><p>${type==='my-work'?'Accepted projects appear here for the selected designer. Pending offers remain on the team board.':'Try a different search or filter.'}</p><a class="button button-small" href="#/projects">Open team projects →</a></div>`;
  if(state.view==='list'||type==='archive') return list(projects);
  const stages=type==='my-work'?['Accepted','In Progress','In Review']:['New','Assigned','Accepted','In Progress','In Review'];
  return `<div class="board" aria-label="Project kanban board">${stages.filter(s=>!state.filterStage||state.filterStage===s).map(s=>{ const rows=projects.filter(p=>p.stage===s);return `<section class="lane" data-stage="${e(s)}" aria-label="${e(s)} lane"><div class="lane-heading"><h2>${e(s)}</h2><span>${rows.length}</span></div>${rows.map(card).join('')||'<div class="empty-lane">No projects in this stage</div>'}</section>`; }).join('')}</div>`;
}
function renderCollection(type) {
  state.lastWorkspace=type;
  const title=type==='my-work'?'My work':type==='archive'?'Completed & archived':'All projects';
  const intro=type==='my-work'?(authenticated?'Your accepted projects. Each job opens its own page.':'Accepted projects assigned to the selected designer. Each job opens its own page.'):type==='archive'?'Completed projects stay available with their details and references.':authenticated&&!isCoordinator()?'Requests and assignments available to your signed-in account.':'A shared view of active requests and work across the Graphics team.';
  const offers=type==='my-work'?offersForCurrent():[];
  return `${breadcrumbs([[title]])}${heading(title,intro,'Project workspace',`<a class="button button-primary" href="#/new">${icon('plus')}New request</a>`)}
    ${copiedNotice()}${offers.length?`<div class="notice notice-warning"><strong>${offers.length} project offer${offers.length===1?'':'s'} waiting.</strong> <a class="inline-link" href="#/projects/${encodeURIComponent(offers[0].id)}">Review ${e(offers[0].title)} →</a></div>`:''}
    <div class="toolbar"><label class="search">${icon('search')}<input id="project-search" type="search" placeholder="Search by project title, job number or requester" aria-label="Search projects" value="${e(state.query)}"></label><div class="filter-controls">${state.projects.some(p=>p.readOnly)?`<select id="source-filter" aria-label="Filter by project source">${[['all','All projects'],['copied','Copied projects · Read-only'],['test','Test projects']].map(([value,label])=>`<option value="${value}" ${state.filterSource===value?'selected':''}>${label}</option>`).join('')}</select>`:''}${type!=='my-work'?`<select id="designer-filter" aria-label="Filter by designer"><option value="">All designers</option>${state.designers.map(d=>`<option value="${e(d.id)}" ${state.filterDesigner===d.id?'selected':''}>${e(d.name)}</option>`).join('')}</select>`:''}<select id="stage-filter" aria-label="Filter by stage"><option value="">All stages</option>${(type==='archive'?['Completed','Archived']:type==='my-work'?['Accepted','In Progress','In Review']:STAGES.filter(s=>!CLOSED.has(s))).map(s=>`<option ${state.filterStage===s?'selected':''}>${e(s)}</option>`).join('')}</select>${type!=='archive'?`<div class="view-toggle" aria-label="Project display"><button data-action="board-view" class="${state.view==='board'?'active':''}" aria-pressed="${state.view==='board'}">${icon('board')}Board</button><button data-action="list-view" class="${state.view==='list'?'active':''}" aria-pressed="${state.view==='list'}">${icon('list')}List</button></div>`:''}</div></div>
    <div id="collection-results">${collectionResults(type)}</div><p class="quiet-note">${readonly()?'Read-only DEV connection. Changes to Smartsheet are disabled.':live()?'Editable test cards can change stage. Copied project cards remain read-only.':'Drag your assigned cards to change stage, or use the stage control on the job page. All changes are demo-only.'}</p>`;
}
function fileRows(p) {
  const files=uniqueAttachments(p);
  return `${files.length?`<div class="files">${files.map(f=>`<article class="file"><span class="file-icon">${icon('file')}</span><div class="file-info"><strong>${e(f.name)}</strong><small>${e(f.size||'Reference file')}${f.sessionOnly?' · This tab only':''}</small></div><div class="file-actions"><button data-action="preview-file" data-id="${e(p.id)}" data-file="${e(f.id)}">Preview</button><a href="${e(fileUrl(f,true)||'#')}" download>Download ↓</a></div></article>`).join('')}</div>`:'<p class="quiet-note">No files attached to this project.</p>'}
    ${(p.references||[]).length?`<div class="reference-links">${p.references.map((r,i)=>safeUrl(r.url)?`<a href="${e(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${icon('link')}${e(r.label||`Reference link ${i+1}`)} ↗</a>`:'').join('')}</div>`:''}`;
}
function fileUrl(f,download=false) {
  if(f.remote) return f.url+(download?'?download=1':'');
  if(f.sessionOnly) return state.files.get(f.id)?.url || null;
  return ['./assets/references/reference-layout.svg','./assets/references/reference-notes.txt'].includes(f.url)?f.url:null;
}
function renderDetail(id, focusReferences=false) {
  const p=findProject(id);if(!p)return notFound();
  const assigned=assignedDesigner(p), ownOffer=authenticated?p.permissions?.respond===true:!readonly()&&p.requestedDesigner===state.person&&!['accepted','declined'].includes(p.response)&&isActive(p);
  const refcount=uniqueAttachments(p).length+(p.references||[]).length;
  return `${breadcrumbs([['Projects',`#/${state.lastWorkspace}`],[p.id]])}
    <div class="page-heading detail-heading"><div><div class="detail-overline"><span class="job-id">${e(p.id)}</span>${stageTag(p.stage)}${p.priority==='High'?'<span class="priority priority-high">High priority</span>':''}</div><h1>${e(p.title)}</h1><p>${e(p.taskType||'Task type not specified')}</p></div><div class="page-actions"><a class="button button-small" href="#/${state.lastWorkspace}">← Back to projects</a>${canEdit(p)?`<button class="button button-primary button-small" data-action="edit-project" data-id="${e(p.id)}">Edit job</button>`:''}</div></div>
    ${p.readOnly?'<div class="notice"><strong>Copied project · Read-only.</strong> Original information is shown from the DEV sheet. Editing, assignment, uploads and AI processing are disabled for this record.</div>':''}
    ${readonly()?'<div class="notice"><strong>Read-only DEV preview.</strong> This page reads the selected job directly. It does not change the native sheet or dashboard selection.</div>':''}
    ${!p.readOnly&&ownOffer?`<div class="notice notice-warning"><strong>This job has been offered to you.</strong> Review the request and references, then accept or decline.<div class="offer-actions"><button class="button button-primary button-small" data-action="accept" data-id="${e(p.id)}">${icon('check')}Accept this job</button><button class="button button-small" data-action="decline" data-id="${e(p.id)}">Decline / return to Graphics</button></div></div>`:''}
    <div class="detail-grid"><div class="detail-main"><dl class="facts"><div><dt>Task type</dt><dd>${e(p.taskType||'Not specified')}</dd></div><div><dt>Estimated hours</dt><dd>${p.hours == null ? 'Not estimated' : `${Number(p.hours)||0} hours`}</dd></div><div><dt>Due date</dt><dd>${e(formatDate(p.dueDate))}</dd></div><div><dt>Assigned designer</dt><dd>${e(personName(assigned))}</dd></div></dl>
      <section class="detail-section"><h2>${icon('brief')}${live()?'Project details & notes':'Project description'}</h2><p>${e(p.description||'No project description supplied.')}</p></section>
      <section class="detail-section"><h2>Deliverables & requirements</h2><p>${e(p.deliverables||'Not yet specified.')}</p>${p.audience?`<p><br><strong>Audience:</strong> ${e(p.audience)}</p>`:''}${p.specifications?`<p><br><strong>Production specifications:</strong> ${e(p.specifications)}</p>`:''}</section>
      <section class="detail-section" id="references"><h2>${icon('file')}Reference files & links <span class="job-id">${refcount}</span></h2>${fileRows(p)}${live()&&canEdit(p)?`<form id="reference-form" data-id="${e(p.id)}" class="reference-upload"><label for="job-files">Add reference files</label><input id="job-files" name="files" type="file" multiple accept="image/png,image/jpeg,image/webp,application/pdf,text/plain" required><button class="button button-small" type="submit">Upload files to this job</button><p class="quiet-note">Adds new attachments to this DEV job. Existing files are retained.</p></form>`:''}</section>
      ${!live()?`<section class="detail-section"><h2>Notes / additional details</h2><p>${e(p.notes||'No additional notes.')}</p></section>`:''}
      ${p.readOnly?'':state.aiModule?'<section id="ai-panel" class="ai-panel" aria-label="AI project brief"></section>':`<section class="future-panel"><h2>${icon('spark')}AI project brief <span class="planned-label">Planned</span></h2><p>Future assistance could summarize the request, suggest tasks and identify unresolved details. AI is not enabled in this prototype.</p></section>`}
    </div><aside class="detail-side">
      <section class="panel"><h2>Request information</h2><dl class="metadata"><div><dt>Requestor</dt><dd>${e(p.requestor||'Not specified')}</dd></div><div><dt>Email</dt><dd>${e(p.email||'Not specified')}</dd></div><div><dt>Group / department</dt><dd>${e(p.requestorGroup||(live()?'See project details':'Not specified'))}</dd></div><div><dt>Received</dt><dd>${e(formatDate(p.createdDate))}</dd></div><div><dt>Completed</dt><dd>${e(formatDate(p.completedDate))}</dd></div></dl></section>
      <section class="panel detail-controls"><h2>Project stage</h2>${canEdit(p)?`<label for="job-stage">Update stage</label><select id="job-stage">${STAGES.map(s=>`<option ${p.stage===s?'selected':''}>${s}</option>`).join('')}</select><button class="button button-primary button-small" data-action="save-stage" data-id="${e(p.id)}">Update stage</button>`:`${stageTag(p.stage)}${p.sourceStatus?`<p>Source status: ${e(p.sourceStatus)}</p>`:''}<p class="quiet-note">${p.readOnly?'Copied projects are read-only.':readonly()?'Stage changes are disabled in the read-only connection.':assigned?'Switch to the assigned demo designer or coordinator to update this project.':'Assignment is recorded only after the offered designer accepts.'}</p>`}</section>
      ${!p.readOnly&&!readonly()&&isCoordinator()&&!assigned&&(!authenticated||p.permissions?.offer)?`<section class="panel detail-controls"><h2>Offer to a designer</h2><label for="offer-designer">Requested designer</label><select id="offer-designer">${state.designers.filter(d=>d.canReceiveOffer!==false).map(d=>`<option value="${e(d.id)}" ${d.id===p.requestedDesigner?'selected':''}>${e(d.name)}</option>`).join('')}</select><button class="button button-primary button-small" data-action="offer" data-id="${e(p.id)}">${live()?'Save designer offer':'Record demo offer'}</button><p class="quiet-note">No email is sent. ${authenticated?'The invited designer records acceptance in their own signed-in session.':live()?'Use the offered designer’s local test view to record acceptance.':'The designer must accept in the demo.'}</p></section>`:''}
      <section class="panel"><h2>Project connections</h2><dl class="metadata"><div><dt>SCOUT job</dt><dd>Not connected</dd></div><div><dt>Project folder</dt><dd>Not connected</dd></div></dl><p class="quiet-note">SCOUT and Dropbox integration are future work.</p></section>
    </aside></div>`;
}
function field(name,label,{type='text',required=false,full=false,value='',help='',options=null,rows=false,multiple=false}={}) {
  const input=rows?`<textarea id="${name}" name="${name}" ${required?'required':''}>${e(value)}</textarea>`:options?`<select id="${name}" name="${name}" ${required?'required':''} ${multiple?'multiple size="5"':''}>${multiple?'':'<option value="">Choose an option</option>'}${options.map(v=>`<option ${(Array.isArray(value)?value.includes(v):v===value)?'selected':''}>${e(v)}</option>`).join('')}</select>`:`<input id="${name}" name="${name}" type="${type}" value="${e(value)}" ${required?'required':''} ${type==='number'?'min="0" max="10000" step="0.5"':''} ${type==='url'?'placeholder="https://"':''} ${name==='email'?'autocomplete="email"':name==='requestor'?'autocomplete="name"':''}>`;
  return `<div class="field ${full?'full':''}"><label for="${name}">${label}${required?' *':' <span>(optional)</span>'}</label>${input}${help?`<small id="${name}-help">${help}</small>`:''}<span class="field-error" id="${name}-error"></span></div>`;
}
function renderNew() {
  if(readonly()||(authenticated&&!state.canCreate))return `${breadcrumbs([['New request']])}${heading('Project intake',authenticated?'Your Smartsheet permissions and pilot settings control submission access.':'The proposed employee form will use ORNL-approved sign-in, separate from Graphics team access.')}<div class="notice"><strong>${authenticated?'Submission is currently unavailable.':'Live submission is not enabled.'}</strong> ${authenticated?'Your sheet access may be read-only, or the pilot owner may have paused writes.':'This DEV connection is read-only. Use the public demo to try the form with synthetic information.'}</div><a class="button" href="#/projects">Back to projects →</a>`;
  return `${breadcrumbs([['New project request']])}${heading('Tell us about your project.','Start with what you know. Graphics can clarify any remaining details before work begins.','Employee intake')}
    ${live()?'<div class="notice"><strong>DEV intake.</strong> This form saves a synthetic test request and its files to the DEV Smartsheet. Use test information only.</div>':'<div class="notice"><strong>Demo request only.</strong> Use fictional details. This form creates a sample job in this tab; it does not submit to Graphics or Smartsheet. Live intake will require ORNL-approved sign-in.</div>'}
    <div class="form-layout"><form id="request-form" class="request-form" novalidate>
      <fieldset class="form-section"><legend><span>01</span>The project</legend><div class="form-grid">
        ${field('title','Project title',{required:true,full:true,help:'A short, descriptive name for the work.'})}
        ${field('taskType','Type of work',{required:true,options:state.taskTypes,multiple:state.taskTypeMultiple,help:state.taskTypeMultiple?'Choose one or more categories. Use Ctrl (Windows) or Command (Mac) to select multiple.':''})}${field('dueDate','Requested due date',{type:'date'})}
        ${field('description','Project details',{required:true,full:true,rows:true,help:'What do you need, what should it communicate, and how will it be used?'})}
        ${field('deliverables','Deliverables and quantities',{full:true,help:'For example: one editable figure and a presentation-ready PNG.'})}
        ${field('audience','Intended audience')}${field('specifications','Dimensions / file formats')}
      </div></fieldset>
      <fieldset class="form-section"><legend><span>02</span>Your information</legend><div class="form-grid">${field('requestor','Your name',{required:true})}${field('email','Your email',{type:'email',required:true})}${field('requestorGroup','Group / department',{full:true})}</div></fieldset>
      <fieldset class="form-section"><legend><span>03</span>References and additional details</legend><div class="form-grid">${field('reference1','Reference link 1',{type:'url',full:true})}${field('reference2','Reference link 2',{type:'url',full:true})}<div class="field full"><label for="attachments">Reference files <span>(optional)</span></label><div class="upload-zone">${icon('upload')}<input id="attachments" name="attachments" type="file" multiple accept="image/png,image/jpeg,image/webp,application/pdf,text/plain"><p>Up to 10 test files, 30 MB each.<br>${live()?'Files are stored on the new DEV request in Smartsheet.':'Demo files stay in this tab until you reload.'}</p></div><span class="field-error" id="attachments-error"></span></div>${field('notes','Notes / additional details',{full:true,rows:true,help:'Include anything else the designer should know.'})}</div></fieldset>
      <div class="form-actions"><p>Fields marked * are required. No email, SCOUT job or Dropbox folder is created.</p><button class="button button-primary" type="submit">${live()?'Save DEV request':'Create demo request'} ${icon('arrow')}</button></div>
    </form><aside class="form-aside"><div class="eyebrow">Employee request experience</div><h2>A request form for the whole lab.</h2><p>The proposed live portal will allow ORNL employees outside Graphics to submit work without joining the Graphics workspace or accessing the project sheet.</p><hr><h2>What happens next?</h2><ol class="steps"><li>Graphics reviews your request and any references.</li><li>A designer is offered the project and records acceptance.</li><li>The team confirms details and follows the work through completion.</li></ol><hr><h2>A helpful starting point</h2><ul><li>Purpose and intended audience</li><li>Deliverables, quantities and dates</li><li>Reference examples and source material</li></ul><p>Not sure which category fits? Choose “Other / Not sure.”</p></aside></div>`;
}
function renderSuccess(id) { const p=findProject(id);if(!p)return notFound();return `<section class="success-panel">${icon('check')}<div class="eyebrow">${live()?'DEV request saved':'Demo request created'}</div><h1>${live()?'Your test request is saved.':'Your sample request is ready.'}</h1><p><strong>${e(p.title)}</strong><br>${e(p.id)}</p><p>It is now in the New lane, with the details and references you supplied.</p><div class="notice">${live()?'Saved in the DEV Smartsheet. This job remains available after refreshing or restarting the local server.':'This was a browser-only demonstration. No request was sent to Graphics or saved in Smartsheet. Refreshing the page resets the demo.'}</div><div class="page-actions"><a class="button button-primary" href="#/projects/${encodeURIComponent(p.id)}">View this job →</a><a class="button" href="#/projects">Open team board</a></div></section>`; }
function renderWorkload() {
  const rows=workloadRows(), active=state.projects.filter(isActive);
  return `${breadcrumbs([['Team workload']])}${heading('A shared view of the work.','Active projects and estimates help the team start an availability conversation.','Team workload')}${copiedNotice()}
    <div class="notice"><strong>${connected?'DEV estimates':'Synthetic planning example'}.</strong> Completed and archived projects are excluded. Missing estimates are excluded from hours. These totals are not a calendar-based availability assessment.</div>
    <div class="workload-grid">${rows.map(d=>`<article class="workload-card"><div class="workload-person">${avatar(d.id)}<h2>${e(d.name)}</h2></div><div class="hours">${d.hours}<small> estimated hours</small></div>${d.capacity>0?`<div class="workload-bar" role="img" aria-label="${e(`${d.hours} estimated hours out of ${d.capacity} sample planning hours`)}"><span style="width:${Math.min(100,d.hours/d.capacity*100)}%"></span></div><p class="quiet-note">${d.capacity}h sample planning reference</p>`:'<p class="quiet-note">Planning capacity: not configured</p>'}<div class="workload-numbers"><span><strong>${d.jobs}</strong>Active projects</span><span><strong>${d.offers}</strong>Pending offers</span></div><p class="quiet-note">Calendar availability: not connected</p><button class="button button-small" data-action="show-designer" data-person="${e(d.id)}">View projects →</button></article>`).join('')}</div>
    <section class="panel status-breakdown"><div class="section-heading"><h2>Active work by stage</h2><span class="job-id">${active.length} active projects</span></div>${STAGES.filter(s=>!CLOSED.has(s)).map(s=>{const count=active.filter(p=>p.stage===s).length;return `<div class="status-row"><span>${e(s)}</span><div class="status-track" aria-hidden="true"><span style="width:${active.length?count/active.length*100:0}%"></span></div><b>${count}</b></div>`;}).join('')}</section>`;
}
function notFound() { return `<div class="empty-state"><h1>Project not found</h1><p>This job is not part of the current workspace. ${live()?'Refresh the DEV workspace if the request was just created.':'Demo requests disappear when the page reloads.'}</p><a class="button button-primary" href="#/projects">Back to projects →</a></div>`; }
function updateChrome(path) {
  let nav=path==='/'?'home':path.split('/')[1]; if(path.startsWith('/projects/'))nav='projects';
  document.querySelectorAll('[data-nav]').forEach(a=>{const active=a.dataset.nav===nav;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  document.querySelector('#my-count').textContent=myProjects(state.projects,state.person).length || '';
  const banner=document.querySelector('#mode-banner');banner.classList.toggle('live',readonly());
  banner.textContent=authenticated&&state.actor?`Private DEV pilot · ${state.actor.name} · ${live()?'Saves to Smartsheet':'Read-only access'}`:state.mode==='demo'?'Interactive demo · Synthetic projects · Changes stay in this tab':state.mode==='loading'?'Connecting to the local DEV gateway…':state.mode==='error'?'DEV connection unavailable':live()?'Local DEV editor · Saves to Smartsheet · Test roles only':'Local DEV preview · Read-only Smartsheet data · No ORNL sign-in connected';
  document.querySelector('#connection-label').textContent=state.mode==='demo'?'Demo workspace':state.mode==='error'?'Connection unavailable':authenticated?'Authenticated DEV pilot':'Local DEV connection';
  document.querySelector('#footer-mode').textContent=authenticated?`Invited DEV pilot · ${live()?'Saves enabled':'Read-only'}`:live()?'DEV saves enabled · Local testing only':readonly()?'Read-only DEV preview · Native flows unchanged':'Synthetic examples · No live submissions';
  document.querySelector('#refresh-workspace').hidden=!connected;
  main.setAttribute('aria-busy',String(state.saving));
  if(authenticated){document.querySelector('#preview-controls').hidden=true;document.querySelector('#pilot-identity').hidden=!state.actor;document.querySelector('#pilot-user-name').textContent=state.actor?`${state.actor.name} · ${state.actor.role}`:'';}
}
function render({focus=false}={}) {
  const path=route();updateChrome(path);
  if(state.mode==='loading'){main.innerHTML='<div class="loading-state">Loading the DEV workspace…</div>';return;}
  if(state.mode==='error'){main.innerHTML=`${heading('The DEV connection is unavailable.','Reconnect and refresh to confirm the latest job values.')}<div class="notice notice-warning">${e(state.error)}</div><button class="button" data-action="reload">Try again</button>${authenticated?'<a class="button button-primary" href="/auth/smartsheet/login">Sign in to Smartsheet</a>':''}`;return;}
  if(path==='/') main.innerHTML=renderHome();
  else if(['/my-work','/projects','/archive'].includes(path))main.innerHTML=renderCollection(path.slice(1));
  else if(path==='/new')main.innerHTML=renderNew();
  else if(path==='/workload')main.innerHTML=renderWorkload();
  else if(path.startsWith('/submitted/'))main.innerHTML=renderSuccess(path.split('/')[2]);
  else if(path.startsWith('/projects/'))main.innerHTML=renderDetail(path.split('/')[2],path.endsWith('/references'));
  else main.innerHTML=notFound();
  document.title=`${main.querySelector('h1')?.innerText.replace(/\s+/g,' ').trim() || 'Workspace'} · ORNL Graphics Portal`;
  if(authenticated&&path==='/new'&&state.actor){for(const [id,value] of [['requestor',state.actor.name],['email',state.actor.id]]){const input=document.getElementById(id);if(input){input.value=value;input.readOnly=true;}}}
  if(state.aiModule&&path.startsWith('/projects/')){const job=findProject(path.split('/')[2]);if(job&&!job.readOnly)state.aiModule.mount({root:document.querySelector('#ai-panel'),job,csrf:state.csrf});}
  if(focus) main.focus({preventScroll:true});
  if(path.endsWith('/references'))document.querySelector('#references')?.scrollIntoView({block:'start'});
}
function updateCollection() { const type=route().slice(1);const target=document.querySelector('#collection-results');if(target)target.innerHTML=collectionResults(type); }
function applyWorkspace(data) {
  if(!['dev-readonly','dev-write'].includes(data.mode)||!Array.isArray(data.projects))throw new Error('Unexpected DEV response.');
  if(authenticated){if(!data.actor?.id)throw new Error('The pilot session could not be verified.');state.actor=data.actor;state.person=data.actor.id;state.csrf=data.csrf;state.canCreate=!!data.canCreate;state.teamWorkload=data.teamWorkload||null;}
  state.projects=data.projects;state.designers=data.designers||[];state.taskTypes=data.taskTypes||TASK_TYPES;state.taskTypeMultiple=!!data.taskTypeMultiple;state.priorities=data.priorities||['Normal','High'];state.mode=data.mode;
}
async function api(path, {method='GET',body,key,headers={}}={}) {
  if(config.apiBase!=='/api')throw new Error('The local gateway configuration is invalid.');
  const response=await fetch((path.startsWith('/auth/')?'':'/api')+path,{method,credentials:'same-origin',cache:'no-store',headers:method==='GET'?{}:{'Content-Type':'application/json','X-Portal-CSRF':state.csrf||config.csrf,'Idempotency-Key':key||crypto.randomUUID(),...headers},body:body===undefined?undefined:body instanceof File?body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw new Error(data.error||'The DEV operation could not be confirmed. Refresh and inspect the job.');
  return data;
}
async function busy(task) {
  if(state.saving)throw new Error('A save is already in progress.');
  state.saving=true;main.setAttribute('aria-busy','true');
  document.querySelectorAll('button[type="submit"]').forEach(b=>b.disabled=true);
  try{return await task();}finally{state.saving=false;main.setAttribute('aria-busy','false');document.querySelectorAll('button[type="submit"]').forEach(b=>b.disabled=false);}
}
async function mutate(id, updater, change) {
  if(readonly())throw new Error('This DEV connection is read-only.');
  const index=state.projects.findIndex(p=>p.id===id);if(index<0)throw new Error('Project not found.');
  if(live())await busy(async()=>applyWorkspace(await api('/projects/'+encodeURIComponent(id),{method:'PATCH',body:{...change,revision:state.projects[index].revision}})));
  else state.projects[index]=updater(state.projects[index]);
  render();
}
async function accept(id,accepted) {
  const p=findProject(id);if(!p||p.requestedDesigner!==state.person||readonly())throw new Error(authenticated?'Only the offered designer can respond.':'Switch to the offered designer’s test view to respond.');
  await mutate(id,job=>({...job,response:accepted?'accepted':'declined',stage:accepted?'Accepted':'New'}),{action:accepted?'accept':'decline'});
  toast(accepted?(live()?'Acceptance saved to Smartsheet. The native assignment formula controls My Work.':'Demo job accepted. It is now in My Work.'):(live()?'Decline saved to Smartsheet. The request is back with Graphics.':'Demo offer declined. The request is back with Graphics.'));
}
function editProject(id) {
  const p=findProject(id);if(!p||!canEdit(p))throw new Error('This project is not editable in the current preview.');
  modal(live()?'Edit DEV job':'Edit demo job',`<form id="edit-form" data-id="${e(id)}" class="form-grid">${field('edit-title','Job title',{required:true,full:true,value:p.title})}${live()?`${field('edit-requested-date','Requested due date',{type:'date',value:p.requestedDueDate||''})}${field('edit-final-date','Final due date',{type:'date',value:p.finalDueDate||''})}${field('edit-type','Task type',{options:state.taskTypes,value:state.taskTypeMultiple?p.taskTypes:p.taskType,multiple:state.taskTypeMultiple})}`:field('edit-date','Due date',{type:'date',value:p.dueDate||''})}${field('edit-hours','Estimated hours',{type:'number',value:p.hours??''})}${field('edit-priority','Priority',{options:state.priorities,value:p.priority||'Normal'})}${live()?`${field('edit-description','Project details / notes',{required:true,full:true,rows:true,value:p.description||'',help:'Saved to the existing Additional Details field. Includes notes and other request information.'})}${field('edit-deliverables','Deliverables and quantities',{full:true,value:p.deliverables||''})}${[1,2].map(n=>field('edit-reference'+n,'Reference link '+n,{type:'url',full:true,value:(p.references||[]).find(r=>r.label==='Reference link '+n)?.url||''})).join('')}`:field('edit-notes','Notes / additional details',{full:true,rows:true,value:p.notes||''})}<button class="button button-primary" type="submit">${live()?'Save to DEV Smartsheet':'Save demo changes'}</button></form>`);
}
function checkFiles(files) {
  if(files.length>10||files.some(f=>!f.size||f.size>30*1024*1024||!['image/png','image/jpeg','image/webp','application/pdf','text/plain'].includes(f.type)))throw new Error('Choose up to 10 PNG, JPEG, WebP, PDF or text files, up to 30 MB each.');
}
async function uploadFiles(id, files) {
  for(const file of files){
    const data=await api('/projects/'+encodeURIComponent(id)+'/attachments',{method:'POST',body:file,headers:{'Content-Type':file.type,'X-Filename':encodeURIComponent(file.name),'X-Project-Revision':findProject(id).revision}});
    applyWorkspace(data);
  }
}

async function previewFile(id,fileId) {
  const p=findProject(id),f=p?.attachments?.find(x=>x.id===fileId),url=f&&fileUrl(f);if(!f||!url)throw new Error('This demo file is no longer available.');
  const footer=`<a class="button button-primary button-small" href="${e(fileUrl(f,true))}" download>Download file ↓</a>`;
  if(['image/png','image/jpeg','image/webp'].includes(f.type)||(!f.remote&&f.url==='./assets/references/reference-layout.svg'))modal(f.name,`<img src="${e(url)}" alt="${e(`Reference preview: ${f.name}`)}">`,footer);
  else if(f.type==='text/plain') { const response=await fetch(url,{credentials:'same-origin'});if(!response.ok)throw new Error('The file could not be opened.');const text=await response.text();modal(f.name,`<pre>${e(text.slice(0,50000))}</pre>`,footer); }
  else modal(f.name,'<p>This file type is available to download. Inline preview is not enabled for this format.</p>',footer);
}
function about() {
  if(authenticated){modal('About the DEV pilot',`<p>This invited pilot uses your Smartsheet login and your existing access to the DEV sheet. Your pilot role further limits the jobs and actions available to you.</p><p>Selected copied projects are read-only. Enabled saves update synthetic DEV jobs and add reference files. There are no delete operations. Native dashboard and workflow definitions are preserved.</p><p>${state.aiModule?'Agent-assisted AI context, draft import and review are enabled only for selected synthetic jobs; no model or source apply runs automatically.':'AI is not enabled in this session.'} General employee intake, email notifications, calendar access, SCOUT and Dropbox remain pending. This is a temporary development pilot, not a production service.</p>`);return;}
  modal('About this prototype',`<p><strong>A separate proposal for a custom Graphics Portal.</strong> The public website uses fictional projects and people. It does not connect visitors to the native Smartsheet workspace.</p><ul><li>Try an employee request, switch demo designers, accept an offer and move work through its stages.</li><li>Each job has its own URL and reference section; there is no shared job selector.</li><li>Demo changes are held in this tab and reset on reload.</li><li>A separate local gateway can read approved DEV rows and, when explicitly started in DEV editing mode, save requests, edits and new attachments. It never deletes files or records.</li></ul><p>Public ORNL employee sign-in, AI, email, SCOUT and Dropbox are not connected. A separate invited OAuth pilot is available through its protected server.</p><p>This is a design draft, not an approved production service.</p>`,`<button class="button button-small" data-action="reset-demo" ${state.mode!=='demo'?'disabled':''}>Reset demo workspace</button><button class="button button-primary button-small" data-action="close-dialog">Continue exploring</button>`);
}
document.addEventListener('click',async event=>{
  if(event.target.closest('a[href="#main"]')){event.preventDefault();main.focus();return;}
  const button=event.target.closest('[data-action]');if(!button)return;
  if(state.saving&&!['close-dialog','preview-file'].includes(button.dataset.action)){toast('Wait for the current save to finish.',true);return;}
  try {
    const {action,id}=button.dataset;
    if(action==='close-dialog'){dialog.close();return;}
    if(action==='about'){about();return;}
    if(action==='reload'){location.reload();return;}
    if(action==='sign-out'){await api('/auth/logout',{method:'POST',body:{}});location.href='/';return;}
    if(action==='refresh-workspace'){if(state.saving)throw new Error('Wait for the current save to finish.');applyWorkspace(await api('/projects?refresh=1'));render();toast('Latest DEV values loaded.');return;}
    if(action==='reset-demo'){if(state.mode!=='demo'||authenticated)return;for(const f of state.files.values())URL.revokeObjectURL(f.url);state.files.clear();state.projects=demoProjects();dialog.close();if(route()!=='/')location.hash='#/';else render();toast('Synthetic workspace reset.');return;}
    if(action==='board-view'||action==='list-view'){state.view=action==='board-view'?'board':'list';render();return;}
    if(action==='show-designer'){state.query='';state.filterStage='';state.filterDesigner=button.dataset.person;state.lastWorkspace='projects';location.hash='#/projects';return;}
    if(action==='accept'||action==='decline'){await accept(id,action==='accept');return;}
    if(action==='edit-project'){editProject(id);return;}
    if(action==='preview-file'){await previewFile(id,button.dataset.file);return;}
    if(action==='offer'){const designer=document.querySelector('#offer-designer').value;if(!isCoordinator()||!person(designer))throw new Error('Choose a valid demo designer.');await mutate(id,p=>({...p,requestedDesigner:designer,response:'',stage:'Assigned'}),{action:'offer',designer});toast(live()?'Designer offer saved to Smartsheet. No email was sent.':'Demo offer recorded. Switch to that designer to accept. No email was sent.');return;}
    if(action==='save-stage'){const p=findProject(id);if(!p||!canEdit(p))throw new Error('This project cannot be changed in the current preview.');const stage=document.querySelector('#job-stage').value;await mutate(id,p=>moveProject(p,stage),{action:'stage',stage});toast(`${live()?'Smartsheet':'Demo'} stage updated to ${stage}.`);}
  }catch(error){toast(error.message||'The action could not be completed.',true);}
});
document.addEventListener('change',event=>{
  if(event.target.id==='preview-user'){if(authenticated)return;state.person=event.target.value;state.query='';state.filterDesigner='';state.filterStage='';render();return;}
  if(event.target.id==='designer-filter'){state.filterDesigner=event.target.value;updateCollection();}
  if(event.target.id==='source-filter'){state.filterSource=event.target.value;updateCollection();}
  if(event.target.id==='stage-filter'){state.filterStage=event.target.value;updateCollection();}
});
document.addEventListener('input',event=>{if(event.target.id==='project-search'){state.query=event.target.value;updateCollection();}});
document.addEventListener('submit',async event=>{
  if(!['edit-form','request-form','reference-form'].includes(event.target.id))return;
  event.preventDefault();
  try {
    if(readonly())throw new Error('DEV editing is not enabled.');
    const form=event.target;
    if(form.id==='reference-form'){
      const id=form.dataset.id,p=findProject(id);if(!p||!canEdit(p))throw new Error('This project is not editable.');
      const files=[...form.elements.files.files];checkFiles(files);
      await busy(()=>uploadFiles(id,files));render();toast('Reference files saved on this Smartsheet job.');return;
    }
    if(form.id==='edit-form'){
      const p=findProject(form.dataset.id);if(!p||!canEdit(p))throw new Error('This project is not editable.');
      const data=new FormData(form),title=String(data.get('edit-title')).trim(),hours=String(data.get('edit-hours')).trim()===''?null:Number(data.get('edit-hours'));
      if(!title||(hours!==null&&(!Number.isFinite(hours)||hours<0||hours>10000)))throw new Error('Enter a title and a valid non-negative estimate.');
      const values={title,hours,priority:String(data.get('edit-priority'))};
      if(live())Object.assign(values,{requestedDueDate:String(data.get('edit-requested-date')),finalDueDate:String(data.get('edit-final-date')),taskType:state.taskTypeMultiple?data.getAll('edit-type'):String(data.get('edit-type')),description:String(data.get('edit-description')),deliverables:String(data.get('edit-deliverables')),reference1:String(data.get('edit-reference1')),reference2:String(data.get('edit-reference2'))});
      else Object.assign(values,{dueDate:String(data.get('edit-date')),notes:String(data.get('edit-notes'))});
      const fields=Object.fromEntries(Object.entries(values).filter(([k,v])=>k==='taskType'&&state.taskTypeMultiple?JSON.stringify(v)!==JSON.stringify(p.taskTypes):v!==(k.startsWith('reference')?(p.references||[]).find(r=>r.label==='Reference link '+k.slice(-1))?.url||'':p[k]??'')));
      if(!Object.keys(fields).length){dialog.close();toast('No changes to save.');return;}
      await mutate(p.id,p=>({...p,...values}),{action:'edit',fields});dialog.close();toast(live()?'Changes saved to DEV Smartsheet.':'Demo changes saved in this tab.');return;
    }
    const data=new FormData(form),values=Object.fromEntries([...data.entries()].filter(([k])=>k!=='attachments').map(([k,v])=>[k,String(v).trim()]));
    if(state.taskTypeMultiple)values.taskType=data.getAll('taskType');
    const errors=validateRequest(values),files=[...document.querySelector('#attachments').files];
    try{checkFiles(files);}catch(error){errors.attachments=error.message;}
    form.querySelectorAll('.field-error').forEach(el=>el.textContent='');form.querySelectorAll('[aria-invalid]').forEach(el=>{el.removeAttribute('aria-invalid');el.removeAttribute('aria-describedby');});
    if(Object.keys(errors).length){for(const [key,message] of Object.entries(errors)){const error=form.querySelector(`#${key}-error`),input=form.elements.namedItem(key);if(error)error.textContent=message;if(input){input.setAttribute('aria-invalid','true');input.setAttribute('aria-describedby',`${key}-error`);}}form.elements.namedItem(Object.keys(errors)[0])?.focus();return;}
    if(live()){
      let createdId;
      await busy(async()=>{
        const result=await api('/projects',{method:'POST',key:state.requestKey,body:{fields:values}});applyWorkspace(result);createdId=result.jobId;
        // A saved request survives an attachment failure. Never repeat intake to retry a file.
        try{await uploadFiles(createdId,files);}catch(error){location.hash='#/projects/'+encodeURIComponent(createdId)+'/references';throw new Error(`Job ${createdId} was saved. Some files may need uploading from its reference section. ${error.message}`);}
      });
      state.requestKey=crypto.randomUUID();location.hash='#/submitted/'+encodeURIComponent(createdId);return;
    }
    const id=`DEMO-${Math.max(1048,...state.projects.map(p=>Number(p.id.replace('DEMO-',''))||0))+1}`;
    const attachments=files.map((f,i)=>{const key=`${id}-file-${i}`;state.files.set(key,{file:f,url:URL.createObjectURL(f)});return {id:key,name:f.name,type:f.type,size:`${Math.max(1,Math.round(f.size/1024))} KB`,sessionOnly:true};});
    state.projects.unshift({...values,id,synthetic:true,stage:'New',priority:'Normal',response:'',requestedDesigner:'',hours:null,createdDate:new Date().toISOString().slice(0,10),completedDate:'',attachments,references:[values.reference1,values.reference2].filter(Boolean).map((url,i)=>({label:`Reference link ${i+1}`,url:safeUrl(url)}))});
    location.hash=`#/submitted/${id}`;
  }catch(error){toast(error.message||'The save could not be confirmed. Refresh and inspect the job.',true);}
});

document.addEventListener('dragstart',event=>{const card=event.target.closest('.card[draggable=true]');if(!card)return;state.dragged=card.dataset.project;event.dataTransfer.setData('text/plain',state.dragged);event.dataTransfer.effectAllowed='move';});
document.addEventListener('dragover',event=>{const lane=event.target.closest('.lane');if(lane&&state.dragged){event.preventDefault();lane.classList.add('drag-over');event.dataTransfer.dropEffect='move';}});
document.addEventListener('dragleave',event=>{const lane=event.target.closest('.lane');if(lane&&!lane.contains(event.relatedTarget))lane.classList.remove('drag-over');});
document.addEventListener('dragend',()=>{state.dragged=null;document.querySelectorAll('.drag-over').forEach(el=>el.classList.remove('drag-over'));});
document.addEventListener('drop',async event=>{const lane=event.target.closest('.lane');if(!lane||!state.dragged)return;event.preventDefault();const p=findProject(state.dragged);state.dragged=null;try{if(!p||!canEdit(p))throw new Error('This project is read-only.');await mutate(p.id,p=>moveProject(p,lane.dataset.stage),{action:'stage',stage:lane.dataset.stage});toast(`${live()?'Smartsheet':'Demo'} project moved to ${lane.dataset.stage}.`);}catch(error){document.querySelectorAll('.drag-over').forEach(el=>el.classList.remove('drag-over'));toast(error.message,true);}});
window.addEventListener('hashchange',()=>{state.query='';if(!route().startsWith('/projects')){state.filterDesigner='';state.filterStage='';}window.scrollTo({top:0,behavior:'instant'});render({focus:true});});
async function initialize(){
  if(connected){
    try{
      applyWorkspace(await api('/projects?refresh=1'));
      if(authenticated){try{const capabilities=await api('/v1/capabilities');if(capabilities.features.aiContext)state.aiModule=await import('./ai-panel.js');}catch{/* Older running pilots keep their existing UI until restart. */}}
      if(!authenticated)state.person='coordinator';
      document.querySelector('#preview-user').innerHTML='<option value="coordinator">Graphics coordinator · Local test</option>'+state.designers.map(d=>`<option value="${e(d.id)}">${e(d.name)} · Local test</option>`).join('')+'<option value="requester">Employee / requester · Local test</option>';
      document.querySelector('#preview-help').textContent=live()?'Local test controls. This is not employee authentication. Saves affect the DEV sheet.':'Local display filter only. Not an authenticated user session.';
    }catch(error){state.mode='error';state.projects=[];state.designers=[];state.error=error.message;}
  }
  render();
}
render();initialize();
