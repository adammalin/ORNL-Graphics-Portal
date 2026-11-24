/* Browser-only demonstrator. Deliberately has no fetch/API/upload adapter. */
import {mountGuidedIntake} from './guided-intake.js';
import {mountSearchSelects} from './search-select.js';
import {TASK_TYPES,escapeHtml as e} from './domain.js';
const main=document.querySelector('#main');
const session={name:'Demo Requester',email:'demo@example.org',demoMode:true,canSubmit:true,
  guidedIntake:window.PORTAL_CONFIG.demoCalendar,taskTypes:TASK_TYPES,taskTypeMultiple:true,
  organizationOptions:{directorate:['Fictional Science','Fictional Operations'],division:['Research','Operations']},departmentOptions:['Fictional Research Group']};
mountSearchSelects();
mountGuidedIntake({main,session,refreshSession:async()=>session,onSubmit:async(fields,files)=>{
  main.innerHTML=`<section class="success-panel"><div class="eyebrow">Demo complete · Nothing submitted</div><h1>Your sample request is ready.</h1><p><strong>${e(fields.title)}</strong></p><div class="notice">This is a non-active demonstration. No request, file or notification was sent. Nothing was saved to Smartsheet. The information below exists only in this tab and disappears on refresh.</div><h2>What you entered</h2><dl class="metadata">${[['Purpose',fields.description],['Graphics work',[fields.taskType].flat().join(', ')],['Requested delivery',fields.dueDate],['Event date',fields.eventDate],['Deliverables',fields.deliverables],['Audience',fields.audience],['Requirements',fields.specifications],['Directorate',fields.directorate],['Division',fields.division],['Group',fields.requestorGroup],['Reference link 1',fields.reference1],['Reference link 2',fields.reference2],['Notes',fields.notes]].filter(([,v])=>v).map(([k,v])=>`<div><dt>${e(k)}</dt><dd>${e(v)}</dd></div>`).join('')}</dl><h2>Supporting services</h2>${fields.additionalServices.length?fields.additionalServices.map(id=>{const d=fields.serviceDetails[id]||{},s=session.guidedIntake.services.find(s=>s.id===id);return `<p><strong>${e(s.label)}</strong>: ${e([d.kind,d.quantity?'Quantity '+d.quantity:'',d.notes].filter(Boolean).join(' · '))}</p>`;}).join(''):'<p>No additional services selected.</p>'}<h2>Reference file names only</h2><p>No files were uploaded.</p><ul>${files.map(f=>`<li>${e(f.name)}</li>`).join('')||'<li>None selected</li>'}</ul><div class="page-actions"><a class="button button-primary" href="/intake-demos/guided">Try guided again</a><a class="button" href="/intake-demos/classic#/new">Compare classic form</a><a class="button" href="/">Return to DEV workspace</a></div></section>`;
  main.focus();
}});
