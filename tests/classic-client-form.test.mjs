import test from 'node:test';
import assert from 'node:assert/strict';
import {classicClientForm} from '../web/assets/intake/classic-client-form.js';
const session={name:'Test <Client>',email:'client@example.org',canSubmit:true,taskTypes:['Figure','Poster'],taskTypeMultiple:true,organizationOptions:{directorate:['Science'],division:['Research']},departmentOptions:['Group']};
test('classic client form has requester fields and no staff workspace controls',()=>{
  const html=classicClientForm(session);
  for(const name of ['title','description','taskType','dueDate','deliverables','audience','specifications','requestor','email','directorate','division','requestorGroup','reference1','reference2','notes','attachments'])assert.ok(html.includes(`name="${name}"`),name);
  for(const staff of ['Assign to me','Team workload','Preview as','Save DEV request','pilot-identity'])assert.ok(!html.includes(staff),staff);
  assert.match(html,/>Request creative work\.</);
  assert.match(html,/Test &lt;Client&gt;/);
  for(const name of ['requestor','email'])assert.match(html,new RegExp(`<input[^>]+name="${name}"[^>]+readonly`));
  assert.match(html,/>Submit request<\/button>/);
});
test('demo uses the same client fields and clearly local completion wording',()=>{
  const prod=classicClientForm(session),demo=classicClientForm({...session,demoMode:true});
  const names=s=>[...s.matchAll(/name="([^"]+)"/g)].map(m=>m[1]);
  assert.deepEqual(names(demo),names(prod));
  assert.match(demo,/>Complete demo<\/button>/);
  assert.match(demo,/Nothing is sent or saved/);
  assert.ok(!demo.includes('Your contact details come from Microsoft'));
});
