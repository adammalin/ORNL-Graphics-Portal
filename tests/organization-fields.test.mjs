import test from 'node:test';
import assert from 'node:assert/strict';
import {organizationInputs} from '../web/organization-fields.js';

test('intake and edits submit distinct native organization values, with custom groups only',()=>{
  const html=organizationInputs({directorate:['Science'],division:['Research']},['Group A'],{directorate:'Science',division:'Research',requestorGroup:'Group A'});
  for(const field of ['directorate','division','requestorGroup'])assert.ok(html.includes(`name="${field}"`));
  assert.match(html,/data-choice="directorate"[^>]*data-custom="false"/);
  assert.match(html,/data-choice="division"[^>]*data-custom="false"/);
  assert.match(html,/data-choice="requestorGroup"[^>]*data-custom="true"/);
  assert.ok(organizationInputs({},[],{},'edit-',false).includes('name="edit-requestorGroup"'));
  assert.ok(!organizationInputs({},[],{},'edit-',false).includes('name="edit-directorate"'));
});

test('organization names are escaped and existing values stay selected',()=>{
  const html=organizationInputs({directorate:['<img src=x onerror=alert(1)>']},[],{division:'Legacy division'});
  assert.ok(!html.includes('<img src=x'));
  assert.ok(html.includes('&lt;img'));
  assert.match(html,/<option value="Legacy division" selected>/);
});
