import test from 'node:test';
import assert from 'node:assert/strict';
import {readPortalJson,mediaType} from '../web/http-client.js';
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
