import {serviceFields} from './classic-rules.js';
import {organizationInputs} from '../../organization-fields.js';
import {searchSelect} from '../../search-select.js';
import {escapeHtml as esc} from '../../domain.js';

function field(name, label, {type='text', required=false, full=false, rows=false, value='', readonly=false}={}) {
  return `<div class="field ${full?'full':''}"><label for="${name}">${label}${required?' *':''}</label>${rows
    ? `<textarea id="${name}" name="${name}" maxlength="4000" ${required?'required':''}>${esc(value)}</textarea>`
    : `<input id="${name}" name="${name}" type="${type}" maxlength="4000" value="${esc(value)}" ${required?'required':''} ${readonly?'readonly':''}>`}</div>`;
}
export function classicClientForm(session) {
  return `<div class="page-heading"><div><div class="eyebrow">Creative Services</div><h1>Request creative work.</h1><p>Tell us about your project. We’ll use these details to help plan the work.</p></div></div>
  <p class="quiet-note">${session.demoMode?'Fictional client':'Signed in as'} ${esc(session.name)} · ${esc(session.email)}. Required fields are marked *.</p>
  <div class="form-layout"><form id="employee-request" class="request-form">
  <fieldset class="form-section" id="request-fields"><legend><span>01</span>The project</legend><div class="form-grid">
  ${field('title','Job title',{required:true,full:true})}
  ${searchSelect('taskType','Type of work',{options:session.taskTypes,multiple:session.taskTypeMultiple,required:true})}
  ${field('dueDate','Requested due date',{type:'date',required:!!session.guidedIntake})}${session.guidedIntake?`<p class="quiet-note field full">Allow at least two business days. Earliest requested delivery: <strong>${esc(session.guidedIntake.earliest||'Calendar review needed')}</strong>. Weekends and configured holidays / closures are excluded.<br>${esc(session.guidedIntake.calendarLabel||session.guidedIntake.message)}</p>`:''}
  ${field('description','Project description',{required:true,full:true,rows:true})}
  ${field('deliverables','Deliverables and quantities',{full:true})}
  ${field('audience','Intended audience')}${field('specifications','Dimensions / file formats')}
  </div></fieldset>
  ${serviceFields(session.guidedIntake)}
  <fieldset class="form-section" id="contact-fields"><legend><span>${session.guidedIntake?'03':'02'}</span>Your information</legend><div class="form-grid">
  ${field('requestor','Your name',{value:session.name,readonly:true})}${field('email','Your email',{type:'email',value:session.email,readonly:true})}
  ${organizationInputs(session.organizationOptions,session.departmentOptions||[],{requestorGroup:session.department||''})}<p class="quiet-note field full">If you’re unsure of your organization, leave it blank and Graphics will help coordinate.</p></div></fieldset>
  <fieldset class="form-section" id="reference-fields"><legend><span>${session.guidedIntake?'04':'03'}</span>References and additional details</legend><div class="form-grid">
  ${session.guidedIntake?field('eventDate','Event date (optional)',{type:'date'}):''}
  ${field('reference1','Reference link 1',{type:'url',full:true})}${field('reference2','Reference link 2',{type:'url',full:true})}
  <div class="field full"><label for="attachments">Reference files</label><div class="upload-zone"><input id="attachments" name="attachments" type="file" multiple accept="image/png,image/jpeg,image/webp,application/pdf,text/plain"><p>Up to 10 files, 30 MB each. PNG, JPEG, WebP, PDF or plain text.</p></div></div>
  ${field('notes','Notes / additional details',{rows:true,full:true})}</div></fieldset>
  <div id="form-status" role="status" aria-live="polite"></div><div class="form-actions"><p>${session.demoMode?'Demo contact details are fictional. Nothing is sent or saved.':'Your contact details come from Microsoft. Your request and references are sent to Creative Services.'}</p><button class="button button-primary" type="submit" ${session.canSubmit?'':'disabled'}>${session.demoMode?'Complete demo':'Submit request'}</button></div></form>
  <aside class="form-aside"><div class="eyebrow">From idea to delivery</div><h2>Give us the full picture.</h2><p>Describe the purpose, audience and deliverables. Include any existing copy, examples or reference files.</p><ol class="steps"><li>Send your request.</li><li>Creative Services reviews the details.</li><li>A designer follows up to plan the work.</li></ol></aside></div>`;
}
