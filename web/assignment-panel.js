import {escapeHtml as e} from './domain.js';

export function assignmentTime(value){
  if(!value)return 'Not recorded';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'Not recorded':new Intl.DateTimeFormat('en-US',{dateStyle:'medium',timeStyle:'short'}).format(date);
}
const names={create:'Request created','create-self-assigned':'Self-assigned and accepted',offer:'Offered',accept:'Accepted',decline:'Declined',reassign:'Reassigned',claim:'Claimed and accepted',stage:'Stage changed'};
export function assignmentPanel(project,designers=[]){
  const info=project.assignment||{},history=info.history||[];
  const person=id=>designers.find(d=>d.id===id)?.name||id||'Unassigned';
  return `<section class="panel"><h2>Assignment</h2><dl class="metadata"><div><dt>Routing status</dt><dd>${e(project.nativeStatus||'Not recorded')}</dd></div><div><dt>Designer response</dt><dd>${e(project.response==='accepted'?'Accepted':project.response==='declined'?'Declined':project.stage==='Assigned'?'Awaiting response':'No current offer')}</dd></div><div><dt>Offered</dt><dd>${e(assignmentTime(info.offeredAt))}</dd></div><div><dt>Accepted</dt><dd>${e(assignmentTime(info.acceptedAt))}</dd></div></dl>${project.assignmentActions?.claim?`<button class="button button-primary button-small" data-action="claim" data-id="${e(project.id)}">Assign to me and accept</button>`:''}${project.assignmentActions?.reassign?`<button class="button button-small" data-action="reassign-project" data-id="${e(project.id)}">Reassign job</button><p class="quiet-note">A new offer requires the new designer’s acceptance.</p>`:''}${history.length?`<details><summary>Assignment history (${history.length}${history.length===100?' most recent':''})</summary><ol class="assignment-history">${history.map(event=>`<li><strong>${e(names[event.action]||event.action)}${event.confirmed?'':' · Unconfirmed'}</strong><br>${e(event.actor?.name||'Unknown actor')} · ${e(assignmentTime(event.at))}<br>${e(person(event.after?.requestedDesigner))} · ${e(event.after?.stage||'')}${event.reason?`<p>${e(event.reason)}</p>`:''}</li>`).join('')}</ol></details>`:'<p class="quiet-note">Assignment history starts with changes made through this portal. Earlier dates are not inferred.</p>'}</section>`;
}
export function reassignmentForm(project,designers){
  const choices=designers.filter(d=>d.canReceiveOffer!==false&&d.id!==project.requestedDesigner);
  return `<form id="reassign-form" data-id="${e(project.id)}" class="form-grid"><p class="field full">This returns the job to Assigned, clears the previous acceptance, and offers it to the new designer. Project details and files are retained.</p><div class="field full"><label for="reassign-designer">New requested designer</label><select id="reassign-designer" name="designer" required><option value="">Choose a designer</option>${choices.map(d=>`<option value="${e(d.id)}">${e(d.name)}</option>`).join('')}</select></div><div class="field full"><label for="reassign-reason">Reason for reassignment</label><textarea id="reassign-reason" name="reason" required maxlength="4000"></textarea></div><label class="field full"><span><input type="checkbox" name="confirmReset" required> I understand the previous acceptance will be reset.</span></label><button type="submit" class="button button-primary">Save reassignment</button></form>`;
}
