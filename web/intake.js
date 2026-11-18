import {searchSelect,mountSearchSelects,showChoiceError} from './search-select.js';
/* Authenticated employee form. This module never calls Smartsheet directly. */
const main = document.querySelector('#main');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let session, submission, saved, pendingFiles = [], busy = false;
const key = () => crypto.randomUUID();
async function api(path, options = {}) {
  const response = await fetch('/api/intake/' + path, {credentials:'same-origin',cache:'no-store', ...options,
    headers:{...(options.method ? {'X-Portal-CSRF':session.csrf} : {}), ...options.headers}});
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || 'The request could not be confirmed.');
    error.status = response.status; throw error;
  }
  return data;
}
function field(name, label, {type='text', required=false, full=false, rows=false, value='', readonly=false}={}) {
  return `<div class="field ${full?'full':''}"><label for="${name}">${label}${required?' *':''}</label>${rows
    ? `<textarea id="${name}" name="${name}" maxlength="4000" ${required?'required':''}>${esc(value)}</textarea>`
    : `<input id="${name}" name="${name}" type="${type}" maxlength="4000" value="${esc(value)}" ${required?'required':''} ${readonly?'readonly':''}>`}</div>`;
}
function render() {
  main.innerHTML = `<div class="page-heading"><div><div class="eyebrow">Creative Services</div><h1>Request creative work.</h1><p>Tell us about your project. We’ll use these details to help plan the work.</p></div></div>
  <p class="quiet-note">Signed in as ${esc(session.name)} · ${esc(session.email)}. Required fields are marked *.</p>
  <div class="form-layout"><form id="employee-request" class="request-form">
  <fieldset class="form-section" id="request-fields"><legend><span>01</span>The project</legend><div class="form-grid">
  ${field('title','Job title',{required:true,full:true})}
  ${searchSelect('taskType','Type of work',{options:session.taskTypes,multiple:session.taskTypeMultiple,required:true})}
  ${field('dueDate','Requested due date',{type:'date'})}
  ${field('description','Project description',{required:true,full:true,rows:true})}
  ${field('deliverables','Deliverables and quantities',{full:true})}
  ${field('audience','Intended audience')}${field('specifications','Dimensions / file formats')}
  </div></fieldset>
  <fieldset class="form-section" id="contact-fields"><legend><span>02</span>Your information</legend><div class="form-grid">
  ${field('requestor','Your name',{value:session.name,readonly:true})}${field('email','Your email',{type:'email',value:session.email,readonly:true})}
  ${searchSelect('requestorGroup','Group / department',{value:session.department,options:session.departmentOptions||[],full:true,allowCustom:true})}</div></fieldset>
  <fieldset class="form-section" id="reference-fields"><legend><span>03</span>References and additional details</legend><div class="form-grid">
  ${field('reference1','Reference link 1',{type:'url',full:true})}${field('reference2','Reference link 2',{type:'url',full:true})}
  <div class="field full"><label for="attachments">Reference files</label><div class="upload-zone"><input id="attachments" name="attachments" type="file" multiple accept="image/png,image/jpeg,image/webp,application/pdf,text/plain"><p>Up to 10 files, 30 MB each. PNG, JPEG, WebP, PDF or plain text.</p></div></div>
  ${field('notes','Notes / additional details',{rows:true,full:true})}</div></fieldset>
  <div id="form-status" role="status" aria-live="polite"></div><div class="form-actions"><p>Your contact details come from Microsoft. Your request and references are sent to Creative Services.</p><button class="button button-primary" type="submit" ${session.canSubmit?'':'disabled'}>Submit request</button></div></form>
  <aside class="form-aside"><div class="eyebrow">From idea to delivery</div><h2>Give us the full picture.</h2><p>Describe the purpose, audience and deliverables. Include any existing copy, examples or reference files.</p><ol class="steps"><li>Send your request.</li><li>Creative Services reviews the details.</li><li>A designer follows up to plan the work.</li></ol></aside></div>`;
  if (!session.canSubmit) document.querySelector('#form-status').textContent = 'Submissions are paused. Please try again after the pilot owner completes the DEV checks.';
  document.querySelector('#employee-request').addEventListener('submit', submit);
}
function success() {
  main.innerHTML = `<section class="success-panel"><div class="eyebrow">Request received</div><h1>Thanks, ${esc(session.name)}.</h1><p>Your request <strong>${esc(saved.jobId)}</strong> has been received.</p><p>${esc(saved.title)}</p><p>Creative Services will review your details and follow up with you.</p>${saved.attachments.length?`<h2>Reference files received</h2><ul>${saved.attachments.map(f=>`<li>${esc(f.name)}</li>`).join('')}</ul>`:''}<div class="page-actions"><a class="button button-primary" href="/my-requests#/requests/${encodeURIComponent(saved.receipt)}">View my request</a><a class="button" href="/request">Submit another request</a></div></section>`;
  main.focus();
}
async function submit(event) {
  event.preventDefault();
  if (busy) return;
  const form = event.currentTarget;
  const status = document.querySelector('#form-status');
  if(!new FormData(form).get('taskType')){showChoiceError(form,'taskType','Choose at least one type of work.');return;}
  const button = form.querySelector('button[type=submit]');
  if (!submission) {
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const fields = Object.fromEntries([...data].filter(([name])=>name!=='attachments' && name!=='taskType'));
    fields.taskType = session.taskTypeMultiple ? data.getAll('taskType') : data.get('taskType');
    pendingFiles = [...form.elements.attachments.files].map(file=>({file,key:key(),done:false}));
    const allowed = new Set(['image/png','image/jpeg','image/webp','application/pdf','text/plain']);
    if (pendingFiles.length>10 || pendingFiles.some(({file})=>!allowed.has(file.type)||!file.size||file.size>30*1024*1024)) {
      status.textContent='Choose up to 10 PNG, JPEG, WebP, PDF or plain text files, 30 MB each.'; return;
    }
    submission = {key:key(),fields};
  }
  busy=true; button.disabled=true;
  for (const id of ['request-fields','contact-fields','reference-fields']) document.getElementById(id).disabled=true;
  try {
    if (!saved) {
      status.textContent='Submitting your request…';
      saved = await api('requests',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':submission.key},body:JSON.stringify({fields:submission.fields})});
    } else saved = await api('requests/'+encodeURIComponent(saved.receipt));
    for (const item of pendingFiles.filter(f=>!f.done)) {
      status.textContent=`Request ${saved.jobId} received. Uploading ${item.file.name}…`;
      saved = await api('requests/'+encodeURIComponent(saved.receipt)+'/attachments',{method:'POST',
        headers:{'Idempotency-Key':item.key,'X-Filename':encodeURIComponent(item.file.name),'X-Project-Revision':saved.revision,'Content-Type':item.file.type},body:item.file});
      item.done=true;
    }
    success();
  } catch(error) {
    status.textContent = saved ? `Request ${saved.jobId} is saved. Some files could not be confirmed: ${error.message} Use Retry to continue without creating another request.`
      : `${error.message} Use Retry to check this same submission; do not create a second request if its outcome is unconfirmed.`;
    if (!saved && error.status===400) {
      submission=null;
      for (const id of ['request-fields','contact-fields','reference-fields']) document.getElementById(id).disabled=false;
      status.textContent=error.message;
    }
    if (error.status===401) {
      const link=document.createElement('a'); link.href='/auth/microsoft/login'; link.textContent=' Sign in again'; status.append(link);
    }
    button.disabled=false; button.textContent=submission?'Retry submission':'Submit request';
  } finally {busy=false;}
}
document.querySelector('#sign-out').addEventListener('click',async()=>{
  if (!session || busy) return;
  const response=await fetch('/auth/microsoft/logout',{method:'POST',headers:{'X-Portal-CSRF':session.csrf}});
  if (response.ok) location.assign('/');
});
let requesterTutorial;
async function help(){
  if(!requesterTutorial){const module=await import('./tutorial.js');requesterTutorial=module.createTutorial({kind:'requester',role:'requester',trackingAvailable:true,request:options=>api('onboarding',{...options,headers:options.method?{'Content-Type':'application/json'}:{},body:options.body===undefined?undefined:JSON.stringify(options.body)})});}
  return requesterTutorial;
}
document.querySelector('#requester-help').addEventListener('click',async()=>{try{await (await help()).open();}catch{main.insertAdjacentHTML('afterbegin','<p role="status">The tutorial is unavailable. Please try again.</p>');}});
mountSearchSelects();
try {
  session=await api('session');
  if(location.pathname==='/my-requests'){const module=await import('./requester.js');await module.mountRequester({main,api,session});}else render();
  try{await (await help()).initialize();}catch{/* Keep request functions available if the tutorial cannot save preferences. */}
}catch(error){main.textContent=error.message;const link=document.createElement('a');link.href='/auth/microsoft/login';link.textContent=' Sign in with Microsoft';main.append(link);}
