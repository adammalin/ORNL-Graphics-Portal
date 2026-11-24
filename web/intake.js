import {collectClassicFields,classicRuleError,mountClassicRules} from './assets/intake/classic-rules.js';
import {classicClientForm} from './assets/intake/classic-client-form.js';
import {readPortalJson} from './http-client.js';
import {mountSearchSelects,showChoiceError} from './search-select.js';
import {mountGuidedIntake} from './guided-intake.js';
/* Authenticated employee form. This module never calls Smartsheet directly. */
const main = document.querySelector('#main');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let session, submission, saved, pendingFiles = [], busy = false;
const key = () => crypto.randomUUID();
async function api(path, options = {}) {
  const response = await fetch('/api/intake/' + path, {credentials:'same-origin',cache:'no-store', ...options,
    headers:{...(options.method ? {'X-Portal-CSRF':session.csrf} : {}), ...options.headers}});
  return readPortalJson(response);
}
function render() {
  main.innerHTML = classicClientForm(session);
  if (!session.canSubmit) document.querySelector('#form-status').textContent = 'Submissions are paused. Please try again after the pilot owner completes the DEV checks.';
  mountClassicRules(document.querySelector('#employee-request'),session);
  document.querySelector('#employee-request').addEventListener('submit', submit);
}
function success() {
  main.innerHTML = `<section class="success-panel"><div class="eyebrow">Request received</div><h1>Thanks, ${esc(session.name)}.</h1><p>Your request <strong>${esc(saved.jobId)}</strong> has been received.</p><p>${esc(saved.title)}</p><p>Creative Services will review your details and follow up with you.</p>${saved.attachments.length?`<h2>Reference files received</h2><ul>${saved.attachments.map(f=>`<li>${esc(f.name)}</li>`).join('')}</ul>`:''}<div class="page-actions"><a class="button button-primary" href="/my-requests#/requests/${encodeURIComponent(saved.receipt)}">View my request</a><a class="button" href="/request">Submit another request</a></div></section>`;
  main.focus();
}
async function submitGuided(fields, files, status) {
  if(busy)return;
  if(!submission){
    const allowed=new Set(['image/png','image/jpeg','image/webp','application/pdf','text/plain']);
    if(files.length>10||files.some(file=>!allowed.has(file.type)||!file.size||file.size>30*1024*1024)){
      const error=new Error('Choose up to 10 PNG, JPEG, WebP, PDF or plain text files, 30 MB each.');error.status=400;throw error;
    }
    submission={key:key(),fields};pendingFiles=files.map(file=>({file,key:key(),done:false}));
  }
  busy=true;
  try{
    if(!saved){status('Submitting your DEV request…');saved=await api('requests',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':submission.key},body:JSON.stringify({fields:submission.fields})});}
    else saved=await api('requests/'+encodeURIComponent(saved.receipt));
    for(const item of pendingFiles.filter(f=>!f.done)){
      status(`Request ${saved.jobId} received. Uploading ${item.file.name}…`);
      saved=await api('requests/'+encodeURIComponent(saved.receipt)+'/attachments',{method:'POST',headers:{'Idempotency-Key':item.key,'X-Filename':encodeURIComponent(item.file.name),'X-Project-Revision':saved.revision,'Content-Type':item.file.type},body:item.file});item.done=true;
    }
    success();
  }catch(error){if(!saved&&error.status===400)submission=null;if(saved){error.requestSaved=true;error.message=`Request ${saved.jobId} is saved. ${error.message} Continue the same submission to finish its references.`;}throw error;}
  finally{busy=false;}
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
    const fields = collectClassicFields(data,session);
    const ruleError=classicRuleError(fields,session.guidedIntake,{additionalRequested:data.has('additional')});
    if(ruleError){status.textContent=ruleError;return;}
    pendingFiles = [...form.elements.attachments.files].map(file=>({file,key:key(),done:false}));
    const allowed = new Set(['image/png','image/jpeg','image/webp','application/pdf','text/plain']);
    if (pendingFiles.length>10 || pendingFiles.some(({file})=>!allowed.has(file.type)||!file.size||file.size>30*1024*1024)) {
      status.textContent='Choose up to 10 PNG, JPEG, WebP, PDF or plain text files, 30 MB each.'; return;
    }
    submission = {key:key(),fields};
  }
  busy=true; button.disabled=true;
  for (const id of ['request-fields','contact-fields','reference-fields','service-fields']) document.getElementById(id)?.setAttribute('disabled','');
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
      for (const id of ['request-fields','contact-fields','reference-fields','service-fields']) document.getElementById(id)?.removeAttribute('disabled');
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
  if(location.pathname==='/my-requests'){const module=await import('./requester.js');await module.mountRequester({main,api,session});}
  else if(session.guidedIntake?.enabled&&session.guidedIntake.layout!=='classic')mountGuidedIntake({main,session,refreshSession:async()=>{session=await api('session');return session;},onSubmit:submitGuided});
  else render();
  try{await (await help()).initialize();}catch{/* Keep request functions available if the tutorial cannot save preferences. */}
}catch(error){main.textContent=error.message;const link=document.createElement('a');link.href='/auth/microsoft/login';link.textContent=' Sign in with Microsoft';main.append(link);}
