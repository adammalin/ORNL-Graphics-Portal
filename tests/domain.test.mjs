import test from 'node:test';
import assert from 'node:assert/strict';
import { myProjects, metrics, workload, moveProject, assignedDesigner, safeUrl, escapeHtml, validateRequest, filterProjects } from '../web/domain.js';

const projects = [
  { id:'one',title:'Figure',stage:'In Progress',requestedDesigner:'a',response:'accepted',hours:6,dueDate:'2026-11-20' },
  { id:'two',title:'Pending',stage:'Assigned',requestedDesigner:'a',response:'',hours:20,dueDate:'2026-11-18' },
  { id:'three',title:'Closed',stage:'Completed',requestedDesigner:'a',response:'accepted',hours:100,dueDate:'2026-11-15' },
  { id:'four',title:'Archived',stage:'Archived',requestedDesigner:'a',response:'accepted',hours:200,dueDate:'2026-11-10' },
  { id:'five',title:'Other work',stage:'Accepted',requestedDesigner:'b',response:'accepted',hours:4,dueDate:'2026-12-10' },
];
test('pending offers never become assignments or appear in My Work',()=>{
  assert.equal(assignedDesigner(projects[1]),'');
  assert.deepEqual(myProjects(projects,'a').map(p=>p.id),['one']);
  assert.deepEqual(myProjects(projects,'b').map(p=>p.id),['five']);
});
test('closed jobs do not inflate active workload, estimates or due-soon counts',()=>{
  const m=metrics(projects,new Date('2026-11-17T12:00:00'));
  assert.equal(m.active,3);assert.equal(m.hours,30);assert.equal(m.dueSoon,2);assert.equal(m.overdue,0);assert.equal(m.closed,2);
  const [a,b]=workload(projects,[{id:'a'},{id:'b'}]);
  assert.equal(a.hours,6);assert.equal(a.offers,1);assert.equal(b.hours,4);
});
test('moving a lane cannot manufacture acceptance; demo closure retains original completion date',()=>{
  assert.throws(()=>moveProject(projects[1],'Accepted'),/acceptance/);
  assert.throws(()=>moveProject({...projects[1],requestedDesigner:''},'Assigned'),/Offer/);
  const done=moveProject(projects[0],'Completed',new Date('2026-11-17T12:00:00Z'));
  const archived=moveProject(done,'Archived',new Date('2026-11-20T12:00:00Z'));
  assert.equal(archived.completedDate,'2026-11-17');assert.equal(archived.response,'accepted');assert.equal(projects[0].stage,'In Progress');
});
test('untrusted text and reference URLs cannot inject executable markup or credential URLs',()=>{
  assert.equal(safeUrl('javascript:alert(1)'),null);assert.equal(safeUrl('data:text/html,hello'),null);
  assert.equal(safeUrl('https://user:secret@example.org'),null);assert.equal(safeUrl('https://example.org/reference'),'https://example.org/reference');
  assert.equal(escapeHtml('<img onerror="x">'), '&lt;img onerror=&quot;x&quot;&gt;');
});
test('request validation only requires factual intake inputs and rejects malformed links',()=>{
  const values={title:'Example',description:'Example details',requestor:'Sample person',email:'sample@example.org',taskType:'Other / Not sure'};
  assert.deepEqual(validateRequest(values),{});
  assert.ok(validateRequest({...values,email:'invalid'}).email);
  assert.ok(validateRequest({...values,reference1:'javascript:alert(1)'}).reference1);
  assert.deepEqual(filterProjects(projects,{query:'FIGURE'}).map(p=>p.id),['one']);
});

test('copied project source filter preserves classification and blocks stage mutation',()=>{
  const copied={...projects[0],id:'copied',readOnly:true,synthetic:false};
  assert.deepEqual(filterProjects([...projects,copied],{source:'copied'}).map(p=>p.id),['copied']);
  assert.equal(filterProjects([...projects,copied],{source:'test'}).length,projects.length);
  assert.deepEqual(filterProjects([...projects,copied],{source:'copied',designer:'a',query:'FIGURE'}).map(p=>p.id),['copied']);
  assert.throws(()=>moveProject(copied,'Completed'),/read-only/);
});
