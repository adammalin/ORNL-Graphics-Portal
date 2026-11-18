/* Searchable choices; native selects retain the form's existing wire format. */
import {escapeHtml as e} from './domain.js';
export const uniqueChoices = values => [...new Set(values.filter(v=>typeof v==='string').map(v=>v.trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
export function searchSelect(name,label,{options=[],value='',multiple=false,required=false,allowCustom=false,full=false}={}){
  const selected=Array.isArray(value)?value:value?[value]:[], choices=uniqueChoices([...options,...selected]);
  return `<div class="field search-choice ${full?'full':''}" data-choice="${name}" data-multiple="${multiple}" data-custom="${allowCustom}"><label id="${name}-label" for="${name}-toggle">${e(label)}${required?' *':' <span>(optional)</span>'}</label><select id="${name}" name="${name}" ${multiple?'multiple':''} hidden>${multiple?'':'<option value=""></option>'}${choices.map(v=>`<option value="${e(v)}" ${selected.includes(v)?'selected':''}>${e(v)}</option>`).join('')}</select><button type="button" id="${name}-toggle" class="choice-toggle" aria-labelledby="${name}-label ${name}-selection" aria-expanded="false" aria-controls="${name}-panel" ><span id="${name}-selection" data-choice-selection>${e(selected.join(' · ')||'Choose an option')}</span><span aria-hidden="true">⌄</span></button><div id="${name}-panel" class="choice-panel" hidden><label class="choice-search-label" for="${name}-search">Search ${e(label.toLowerCase())}</label><input id="${name}-search" type="search" autocomplete="off" maxlength="4000" placeholder="Type to filter…" data-choice-search><div class="choice-options" role="group" aria-labelledby="${name}-label">${choices.map((v,i)=>`<label class="choice-option"><input type="${multiple?'checkbox':'radio'}" data-choice-option value="${e(v)}" ${selected.includes(v)?'checked':''}><span>${e(v)}</span></label>`).join('')}</div><p class="choice-empty" data-choice-empty hidden>No matching options.</p>${allowCustom?'<button type="button" class="choice-custom" data-choice-custom hidden></button>':''}${!required?'<button type="button" class="text-button" data-choice-clear>Clear selection</button>':''}<p class="choice-hint">${multiple?'Select all that apply. ':''}${allowCustom?'Can’t find your department? Type its name, then choose Use.':'Type above to filter the list.'}</p></div><small data-choice-caption>${e(selected.join(' · '))}</small><span class="field-error" id="${name}-error" role="status"></span></div>`;
}
const widget=target=>target.closest('.search-choice');
function close(box,focus=false){box.querySelector('.choice-panel').hidden=true;const button=box.querySelector('.choice-toggle');button.setAttribute('aria-expanded','false');if(focus)button.focus();}
function open(box){document.querySelectorAll('.search-choice').forEach(other=>{if(other!==box)close(other);});box.querySelector('.choice-panel').hidden=false;box.querySelector('.choice-toggle').setAttribute('aria-expanded','true');box.querySelector('[data-choice-search]').focus();}
function update(box){
  const select=box.querySelector('select'),chosen=[...select.selectedOptions].map(o=>o.value).filter(Boolean);
  box.querySelector('[data-choice-selection]').textContent=chosen.join(' · ')||'Choose an option';
  box.querySelector('[data-choice-caption]').textContent=chosen.join(' · ');
  box.querySelectorAll('[data-choice-option]').forEach(input=>input.checked=chosen.includes(input.value));
  box.querySelector('.field-error').textContent='';box.querySelector('.choice-toggle').removeAttribute('aria-invalid');select.dispatchEvent(new Event('change',{bubbles:true}));
}
function choose(box,value,checked=true){
  const select=box.querySelector('select');if(![...select.options].some(o=>o.value===value))select.add(new Option(value,value));
  for(const option of select.options)if(!select.multiple||option.value===value)option.selected=option.value===value&&checked;
  update(box);if(!select.multiple)close(box,true);
}
let installed=false;
export function mountSearchSelects(){
  if(installed)return;installed=true;
  document.addEventListener('click',event=>{
    const box=widget(event.target);if(!box){document.querySelectorAll('.search-choice').forEach(b=>close(b));return;}
    if(event.target.closest('.choice-toggle'))box.querySelector('.choice-panel').hidden?open(box):close(box);
    if(event.target.closest('[data-choice-custom]'))choose(box,box.querySelector('[data-choice-search]').value.trim());
    if(event.target.closest('[data-choice-clear]')){box.querySelector('select').selectedIndex=-1;update(box);close(box,true);}
  });
  document.addEventListener('focusin',event=>{document.querySelectorAll('.search-choice').forEach(box=>{if(!box.contains(event.target))close(box);});});
  document.addEventListener('change',event=>{if(event.target.matches('[data-choice-option]'))choose(widget(event.target),event.target.value,event.target.checked);});
  document.addEventListener('input',event=>{
    if(!event.target.matches('[data-choice-search]'))return;const box=widget(event.target),q=event.target.value.trim().toLocaleLowerCase();let matches=0;
    box.querySelectorAll('.choice-option').forEach(row=>{row.hidden=!row.textContent.toLocaleLowerCase().includes(q);if(!row.hidden)matches++;});
    box.querySelector('[data-choice-empty]').hidden=matches>0;
    const custom=box.querySelector('[data-choice-custom]');if(custom){custom.hidden=!q||[...box.querySelector('select').options].some(o=>o.value.toLocaleLowerCase()===q);custom.textContent='Use “'+event.target.value.trim()+'”';}
  });
  document.addEventListener('keydown',event=>{
    const box=widget(event.target);if(!box)return;
    if(event.key==='Escape'&&!box.querySelector('.choice-panel').hidden){event.preventDefault();event.stopPropagation();close(box,true);}
    if(event.key==='ArrowDown'&&event.target.matches('.choice-toggle')){event.preventDefault();open(box);}
    else if(event.key==='ArrowDown'&&event.target.matches('[data-choice-search]')){event.preventDefault();box.querySelector('.choice-option:not([hidden]) input')?.focus();}
    if(event.key==='Enter'&&event.target.matches('[data-choice-search]')){event.preventDefault();const custom=box.querySelector('[data-choice-custom]');if(custom&&!custom.hidden)custom.click();else box.querySelector('.choice-option:not([hidden]) input')?.click();}
  });
}
export function showChoiceError(form,name,message){const box=form.querySelector(`[data-choice="${name}"]`);if(!box)return false;box.querySelector('.field-error').textContent=message;const toggle=box.querySelector('.choice-toggle');toggle.setAttribute('aria-invalid','true');toggle.setAttribute('aria-describedby',name+'-error');toggle.focus();return true;}
