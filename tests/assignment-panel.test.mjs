import test from 'node:test';
import assert from 'node:assert/strict';
import {assignmentPanel,reassignmentForm,assignmentTime} from '../web/assignment-panel.js';
test('assignment panel shows real timestamps, recorded routing state and guarded actions',()=>{
 const p={id:'TEST-1',stage:'Accepted',response:'accepted',nativeStatus:'Designer Accepted',assignmentActions:{reassign:true,claim:false},assignment:{acceptedAt:'2026-11-23T18:00:00Z',history:[{action:'accept',confirmed:true,at:'2026-11-23T18:00:00Z',actor:{name:'Fictional Designer'},after:{stage:'Accepted'},reason:'<script>not markup</script>'}]}};
 const html=assignmentPanel(p);
 assert.match(html,/Designer Accepted/);assert.match(html,/Reassign job/);assert.ok(!html.includes('Assign to me and accept'));assert.match(html,/Assignment history \(1\)/);assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);
 assert.equal(assignmentTime(null),'Not recorded');assert.equal(assignmentTime('invalid'),'Not recorded');
});
test('reassignment form requires a new eligible target, reason and explicit acceptance reset',()=>{
 const html=reassignmentForm({id:'TEST-1',requestedDesigner:'a'},[{id:'a',name:'Current'},{id:'b',name:'New Designer'},{id:'x',name:'Not eligible',canReceiveOffer:false}]);
 assert.ok(!html.includes('value="a"'));assert.ok(!html.includes('value="x"'));assert.ok(html.includes('value="b"'));assert.match(html,/name="reason" required/);assert.match(html,/name="confirmReset" required/);
 const panel=assignmentPanel({id:'TEST-1',stage:'New',assignmentActions:{claim:true}});
 assert.match(panel,/Assign to me and accept/);assert.match(panel,/Earlier dates are not inferred/);
});
