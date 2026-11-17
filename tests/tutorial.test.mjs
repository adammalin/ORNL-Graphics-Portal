import test from 'node:test';
import assert from 'node:assert/strict';
import {TUTORIALS,lessonsFor,newPractice,practiceAction} from '../web/tutorial-content.js';
test('role lessons cover the shipped workflows and omit unavailable integrations',()=>{
  for(const track of ['designer','coordinator','requester'])assert.equal(new Set(TUTORIALS[track].lessons.map(l=>l.id)).size,TUTORIALS[track].lessons.length);
  for(const key of ['offers','details','references','editing','stages','ai','find'])assert(TUTORIALS.designer.lessons.some(l=>l.id===key));
  for(const key of ['routing','responses','workload','planning','ai'])assert(TUTORIALS.coordinator.lessons.some(l=>l.id===key));
  assert(lessonsFor('designer',{aiAvailable:false,trackingAvailable:false}).every(l=>!['ai','customer-files'].includes(l.id)));
});
test('acceptance, refusal, archive and sharing stay inside independent fictional practice state',()=>{
  const original=newPractice();let p=practiceAction(original,'stage','Completed');assert.equal(p.stage,'Assigned');assert.match(p.message,/Accept/);
  p=practiceAction(p,'accept');p=practiceAction(p,'stage','Archived');assert.equal(p.stage,'Archived');assert.equal(original.stage,'Assigned');
  p=practiceAction(p,'share');assert.equal(p.shared,true);p=practiceAction(p,'share');assert.equal(p.shared,false);
  p=practiceAction(p,'decline');assert.equal(p.stage,'New');assert.equal(p.response,'declined');
  p=practiceAction(p,'add-file');assert.equal(p.files.length,2);assert.equal(original.files.length,1);
});
