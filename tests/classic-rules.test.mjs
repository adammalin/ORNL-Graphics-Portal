import test from 'node:test';import assert from 'node:assert/strict';
import {classicRuleError,collectClassicFields,serviceFields} from '../web/assets/intake/classic-rules.js';
import {classicClientForm} from '../web/assets/intake/classic-client-form.js';
const p={ready:true,today:'2026-11-24',earliest:'2026-11-30',validThrough:'2027-09-30',closedDates:['2026-11-26','2026-11-27'],services:[{id:'poster',label:'Poster',team:'Reproduction',choices:['36 × 48 inches']},{id:'video',label:'Video production',team:'Video Production',choices:['Editing']}]};
test('classic enforces same business-day and closure rule; staff option only bypasses minimum',()=>{
  assert.ok(classicRuleError({dueDate:'2026-11-24'},p));assert.equal(classicRuleError({dueDate:'2026-11-30'},p),'');
  assert.equal(classicRuleError({dueDate:'2026-11-24'},p,{overrideMinimum:true}),'');
  for(const dueDate of ['2026-11-23','2026-11-26','2026-11-28','2028-01-03'])assert.ok(classicRuleError({dueDate},p,{overrideMinimum:true}));
});
test('classic collects only selected service details and excludes override/control fields',()=>{
  const d=new FormData();for(const [k,v] of Object.entries({title:'Demo',dueDate:'2026-11-30',additional:'on',overrideLeadTime:'on','service.poster.kind':'36 × 48 inches','service.poster.quantity':'2','service.poster.notes':'Poster','service.video.notes':'Hidden'}))d.append(k,v);d.append('taskType','Other');d.append('additionalServices','poster');
  const f=collectClassicFields(d,{taskTypeMultiple:true,guidedIntake:p});assert.deepEqual(f.additionalServices,['poster']);assert.deepEqual(Object.keys(f.serviceDetails),['poster']);assert.ok(!('overrideLeadTime' in f));assert.equal(classicRuleError(f,p),'');
  d.delete('additional');const hidden=collectClassicFields(d,{taskTypeMultiple:true,guidedIntake:p});assert.deepEqual(hidden.serviceDetails,{});assert.deepEqual(hidden.additionalServices,[]);
});
test('classic and guided share service choices; client markup never exposes override',()=>{
  const html=classicClientForm({name:'Demo',email:'demo@example.org',canSubmit:true,guidedIntake:p,taskTypes:['Other'],organizationOptions:{},departmentOptions:[]});
  assert.match(html,/Allow at least two business days/);assert.match(html,/name="dueDate"[^>]+required/);
  for(const service of p.services){assert.ok(serviceFields(p).includes(service.label));for(const choice of service.choices)assert.ok(html.includes(choice));}
  assert.ok(!html.includes('overrideLeadTime'));
  assert.ok(classicRuleError({dueDate:'2026-11-30',additionalServices:[]},p,{additionalRequested:true}));
  assert.ok(classicRuleError({dueDate:'2026-11-30',additionalServices:['poster'],serviceDetails:{poster:{kind:'36 × 48 inches',quantity:'1.5'}}},p));
});
