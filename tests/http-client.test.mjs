import test from 'node:test';
import assert from 'node:assert/strict';
import {readPortalJson,mediaType,recoverConfirmedSave} from '../web/http-client.js';
test('gateway HTML fails clearly rather than being parsed or accepted as portal data',async()=>{
  await assert.rejects(()=>readPortalJson(new Response('<h1>Sign in</h1>',{headers:{'Content-Type':'text/html'}})),error=>error.status===502&&error.message.includes('not confirmed'));
});
test('invalid JSON and denied requests retain safe diagnostics and status',async()=>{
  await assert.rejects(()=>readPortalJson(new Response('bad',{headers:{'Content-Type':'application/json'}})),error=>error.status===502);
  await assert.rejects(()=>readPortalJson(new Response('{"error":"Sign in again"}',{status:401,headers:{'Content-Type':'application/json'}})),error=>error.status===401&&error.message==='Sign in again');
  assert.deepEqual(await readPortalJson(new Response('{"jobId":"FAKE-1"}',{headers:{'Content-Type':'application/json'}})),{jobId:'FAKE-1'});
});
test('MIME parameters and case do not disable safe native file previews',()=>{
  assert.equal(mediaType(' Text/Plain; charset=UTF-8 '),'text/plain');
  assert.equal(mediaType('IMAGE/PNG'),'image/png');
  assert.equal(mediaType(null),'');
});

test('only a confirmed durable save can resume its exact receipt once',async()=>{
  let calls=0;const options={key:'same-receipt',body:{hours:7}},seen=[];
  const send=async()=>{seen.push(options);if(++calls===1)return readPortalJson(new Response(JSON.stringify({error:'Saved; refresh pending',saveConfirmed:true,jobId:'TEST-1'}),{status:503,headers:{'Content-Type':'application/json'}}));return {jobId:'TEST-1'};};
  assert.deepEqual(await recoverConfirmedSave(send),{jobId:'TEST-1'});
  assert.equal(calls,2);assert.equal(seen[0],seen[1]);
  for(const status of [401,403,502,503]){
    calls=0;await assert.rejects(()=>recoverConfirmedSave(async()=>{calls++;throw Object.assign(new Error('Not confirmed'),{status});}));assert.equal(calls,1);
  }
});

test('exhausted recovery preserves saved status and current authorization denial',async()=>{
  let calls=0;const saved=Object.assign(new Error('Already saved'),{saveConfirmed:true,status:503});
  await assert.rejects(()=>recoverConfirmedSave(async()=>{calls++;throw saved;}),error=>error===saved);
  assert.equal(calls,2);calls=0;
  await assert.rejects(()=>recoverConfirmedSave(async()=>{if(++calls===1)throw saved;throw Object.assign(new Error('Access revoked'),{status:403});}),error=>error.status===403&&error.saveConfirmed&&error.message.includes('saved'));
  assert.equal(calls,2);
});
