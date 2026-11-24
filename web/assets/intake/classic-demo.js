/* Client-facing Classic demo: local preview only, never an API/upload adapter. */
import {collectClassicFields,classicRuleError,mountClassicRules} from './classic-rules.js';
import {classicClientForm} from './classic-client-form.js';
import {mountSearchSelects,showChoiceError} from '../../search-select.js';
import {TASK_TYPES,escapeHtml as e} from '../../domain.js';
const session={name:'Demo Requester',email:'demo@example.org',demoMode:true,canSubmit:true,
  taskTypes:TASK_TYPES,taskTypeMultiple:true,guidedIntake:window.PORTAL_CONFIG.demoCalendar,
  organizationOptions:{directorate:['Fictional Science','Fictional Operations'],division:['Research','Operations']},
  departmentOptions:['Fictional Research Group']};
document.body.className='requester-site';
document.body.innerHTML=`<a class="skip-link" href="#main">Skip to content</a><header class="site-header"><a class="site-mark" href="/intake-demos/classic"><span><strong>ORNL Creative Services</strong><small>Client intake form comparison</small></span></a><nav class="header-actions" aria-label="Intake demo versions"><a href="/intake-demos/classic" aria-current="page">Classic client form demo</a><a href="/intake-demos/guided">Guided client form demo</a><a href="/">Return to DEV workspace</a></nav></header><div class="mode-banner"><strong>NON-ACTIVE CLIENT DEMO</strong> · Nothing is sent or saved to Smartsheet. No uploads or notifications. Use fictional information. Refresh resets the demo.</div><main id="main" class="intake-shell" tabindex="-1"></main>`;
const main=document.querySelector('#main');
main.innerHTML=classicClientForm(session);
document.title='Classic client intake demo · ORNL';
mountSearchSelects();
mountClassicRules(main.querySelector('form'),session);
main.querySelector('form').addEventListener('submit',event=>{
  event.preventDefault();
  const form=event.currentTarget;
  const data=new FormData(form);
  if(!data.get('taskType')){showChoiceError(form,'taskType','Choose at least one type of work.');return;}
  const fields=collectClassicFields(data,session);
  const ruleError=classicRuleError(fields,session.guidedIntake,{additionalRequested:data.has('additional')});
  if(ruleError){document.querySelector('#form-status').textContent=ruleError;return;}
  if(!form.reportValidity())return;
  const files=[...form.elements.attachments.files];
  if(files.length>10||files.some(f=>!['image/png','image/jpeg','image/webp','application/pdf','text/plain'].includes(f.type)||!f.size||f.size>30*1024*1024)){
    document.querySelector('#form-status').textContent='Choose up to 10 PNG, JPEG, WebP, PDF or plain text files, 30 MB each.';return;
  }
  const names={title:'Job title',description:'Project description',dueDate:'Requested due date',eventDate:'Event date',deliverables:'Deliverables and quantities',audience:'Intended audience',specifications:'Dimensions / file formats',requestor:'Your name',email:'Your email',directorate:'Directorate',division:'Division / office / facility',requestorGroup:'Group / department',reference1:'Reference link 1',reference2:'Reference link 2',notes:'Notes / additional details'};
  main.innerHTML=`<section class="success-panel"><div class="eyebrow">Classic client demo complete · Nothing submitted</div><h1>Your sample request is ready.</h1><div class="notice">This was a browser-only demonstration of the original client request form. Nothing was saved to Smartsheet or sent to Creative Services. No files were uploaded. Refreshing resets the demo.</div><h2>What you entered</h2><dl class="metadata"><div><dt>Type of work</dt><dd>${e(data.getAll('taskType').join(', '))}</dd></div>${Object.entries(names).filter(([name])=>data.get(name)).map(([name,label])=>`<div><dt>${e(label)}</dt><dd>${e(data.get(name))}</dd></div>`).join('')}</dl><h2>Supporting services</h2>${fields.additionalServices.map(id=>{const d=fields.serviceDetails[id]||{},s=session.guidedIntake.services.find(s=>s.id===id);return `<p><strong>${e(s.label)}</strong>: ${e([d.kind,d.quantity?'Quantity '+d.quantity:'',d.notes].filter(Boolean).join(' · '))}</p>`;}).join('')||'<p>Graphics only.</p>'}<h2>Reference file names only</h2><ul>${files.map(f=>`<li>${e(f.name)}</li>`).join('')||'<li>None selected</li>'}</ul><div class="page-actions"><a class="button button-primary" href="/intake-demos/classic">Try classic again</a><a class="button" href="/intake-demos/guided">Compare guided client form</a><a class="button" href="/">Return to DEV workspace</a></div></section>`;
  main.focus();
});
