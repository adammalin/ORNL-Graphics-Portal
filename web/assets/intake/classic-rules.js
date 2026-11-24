import {escapeHtml as e} from '../../domain.js';
import {dueError,routeGroups} from '../../business-days.js';
export function serviceFields(p){
  if(!p)return '';
  return `<fieldset class="form-section" id="service-fields"><legend><span>02</span>Additional services</legend><label class="guided-toggle"><input type="checkbox" name="additional" id="classic-additional"><span><strong>This project needs additional Creative Services support.</strong><small>Include photography, video, web or printing in the same request.</small></span></label><div id="classic-services" hidden><div class="guided-choice-grid">${p.services.map(s=>`<label class="guided-choice"><input type="checkbox" name="additionalServices" value="${e(s.id)}"><span>${e(s.label)}</span></label>`).join('')}</div>${p.services.filter(s=>s.id!=='unsure').map(s=>`<section class="guided-detail" data-service="${e(s.id)}" hidden><h3>${e(s.label)}</h3><div class="form-grid"><div class="field"><label for="service-${s.id}-kind">Type of ${e(s.label.toLowerCase())} support *</label><select id="service-${s.id}-kind" name="service.${s.id}.kind" disabled required><option value="">Choose an option</option>${s.choices.map(c=>`<option>${e(c)}</option>`).join('')}</select></div>${['reproduction','poster'].includes(s.id)?`<div class="field"><label for="service-${s.id}-quantity">How many copies? *</label><input id="service-${s.id}-quantity" name="service.${s.id}.quantity" type="number" min="1" max="100000" step="1" required disabled></div>`:''}<div class="field full"><label for="service-${s.id}-notes">Details for ${e(s.label.toLowerCase())} (optional)</label><input id="service-${s.id}-notes" name="service.${s.id}.notes" maxlength="500" disabled></div></div></section>`).join('')}</div><div class="quiet-note" id="classic-routing" aria-live="polite">Graphics coordination · No service notifications are sent.</div></fieldset>`;
}
export function collectClassicFields(data,session){
  const fields=Object.fromEntries([...data].filter(([name])=>!['attachments','taskType','additional','additionalServices','overrideLeadTime','assignToMe'].includes(name)&&!name.startsWith('service.')));
  fields.taskType=session.taskTypeMultiple?data.getAll('taskType'):data.get('taskType');
  if(session.guidedIntake){
    fields.additionalServices=data.has('additional')?data.getAll('additionalServices'):[];
    fields.serviceDetails=Object.fromEntries(fields.additionalServices.map(id=>[id,id==='unsure'?{}:Object.fromEntries(['kind','quantity','notes'].filter(k=>data.has(`service.${id}.${k}`)).map(k=>[k,data.get(`service.${id}.${k}`)]))]));
  }
  return fields;
}
export function classicRuleError(fields,p,{overrideMinimum=false,additionalRequested=false}={}){
  if(!p)return '';
  const error=dueError(fields.dueDate,p,{overrideMinimum});if(error)return error;
  if(additionalRequested&&!fields.additionalServices?.length)return 'Choose a supporting service or turn additional support off.';
  for(const id of fields.additionalServices||[]){const s=p.services.find(s=>s.id===id),d=fields.serviceDetails?.[id]||{};
    if(!s)return 'Choose valid supporting services.';
    if(id!=='unsure'&&!s.choices.includes(d.kind))return `Choose the type of support for ${s.label}.`;
    if(['reproduction','poster'].includes(id)&&(!/^\d+$/.test(d.quantity||'')||Number(d.quantity)<1||Number(d.quantity)>100000))return 'Enter a whole printing quantity from 1 to 100,000.';
    if((d.notes||'').length>500)return 'Keep each service note under 500 characters.';
  }
  return '';
}
export function mountClassicRules(form,session){
  const p=session.guidedIntake;if(!p)return;
  const due=form.elements.dueDate;
  function update(){
    const override=form.elements.overrideLeadTime?.checked===true&&p.canOverride===true;
    due.required=true;due.min=override?p.today:p.earliest;due.max=p.validThrough||'';
    due.setCustomValidity(due.value?dueError(due.value,p,{overrideMinimum:override}):'');
    const parent=form.querySelector('#classic-additional');
    if(!parent)return;
    form.querySelector('#classic-services').hidden=!parent.checked;
    for(const input of form.querySelectorAll('[name=additionalServices]'))input.disabled=!parent.checked;
    const ids=parent.checked?[...form.querySelectorAll('[name=additionalServices]:checked')].map(i=>i.value):[];
    for(const section of form.querySelectorAll('[data-service]')){section.hidden=!ids.includes(section.dataset.service);for(const input of section.querySelectorAll('input,select'))input.disabled=section.hidden;}
    form.querySelector('#classic-routing').textContent=routeGroups(ids,p.services).map(g=>`${g.team}: ${g.services.join(', ')}`).join(' · ')+' · Routing preview only; no notifications sent.';
  }
  form.addEventListener('change',update);form.addEventListener('input',event=>{if(event.target===due)update();});
  update();
}
