import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkspaceSync} from '../web/workspace-sync.js';
import {searchSelect,uniqueChoices} from '../web/search-select.js';
test('an older background response cannot overwrite a completed save',async()=>{
  let resolve,reads=0,applied=[];
  const sync=createWorkspaceSync({read:()=>{reads++;return new Promise(r=>resolve=r);},canApply:()=>true,apply:d=>applied.push(d)});
  const first=sync.check();await sync.check();assert.equal(reads,1);
  sync.invalidate();resolve({projects:['older snapshot']});await first;assert.deepEqual(applied,[]);
});
test('sync preserves forms and skips unchanged versions; later changed data applies',async()=>{
  let allowed=false,reads=0,applied=[];
  const sync=createWorkspaceSync({read:async()=>{reads++;return reads===1?{unchanged:true}:{projects:['accepted job']};},canApply:()=>allowed,apply:d=>applied.push(d),now:()=>reads*6000});
  await sync.check();assert.equal(reads,0);allowed=true;await sync.check();assert.deepEqual(applied,[]);
  await sync.check({force:true});assert.equal(applied[0].projects[0],'accepted job');
});
test('searchable intake escapes source choices and retains native multiple form fields',()=>{
  const html=searchSelect('taskType','Type of work',{multiple:true,required:true,options:['Poster','<img onerror=alert(1)>']});
  assert.match(html,/<select id="taskType" name="taskType" multiple hidden>/);
  assert.ok(html.indexOf('data-choice-search')<html.indexOf('class="choice-options"'));
  assert.ok(!html.includes('<img onerror'));assert.deepEqual(uniqueChoices([' Physics ','Physics','','Chemistry']),['Chemistry','Physics']);
  assert.match(searchSelect('requestorGroup','Group / department',{allowCustom:true,value:'New team'}),/data-choice-custom/);
});
test('an arriving update pauses when the user starts editing during the read',async()=>{
  let resolve,allowed=true,applied=false,states=[];
  const sync=createWorkspaceSync({read:()=>new Promise(r=>resolve=r),canApply:()=>allowed,apply:()=>applied=true,status:s=>states.push(s)});
  const pending=sync.check();allowed=false;resolve({projects:['new snapshot']});await pending;
  assert.equal(applied,false);assert.equal(states.at(-1),'paused');
});
