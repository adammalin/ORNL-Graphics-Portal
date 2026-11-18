import {readPortalJson} from './http-client.js';
/* Stage 1: private browser-agent handoff. No model runner or source apply. */
import {escapeHtml as e} from './domain.js';
export async function mount({root,job,csrf}) {
  if(!root || root.dataset.mounted) return;
  root.dataset.mounted='true';
  const base='/api/v1/jobs/'+encodeURIComponent(job.id);
  let state,packet,draft,referencePage=0,historyPage=0,waiting=false,operation=null;
  const refs=[],history=[];
  const stamp=value=>new Date(value).toLocaleString();
  async function request(path,{method='GET',body,key,raw=false}={}) {
    const response=await fetch(base+path,{method,credentials:'same-origin',cache:'no-store',
      headers:method==='GET'?{}:{'Content-Type':'application/json','X-Portal-CSRF':csrf,'Idempotency-Key':key||crypto.randomUUID()},
      body:body===undefined?undefined:raw?body:JSON.stringify(body)});
    return readPortalJson(response);
  }
  function status(text,error=false){const target=root.querySelector('[data-testid=operation-status]');if(target){target.textContent=text;target.classList.toggle('notice-warning',error);}}
  function coverage(analysis){return `<h4>Reference coverage</h4><p>${analysis.coverage.reviewedSourceIds.length} sources declared reviewed; ${analysis.coverage.unreadSources.length} unread.</p>${analysis.coverage.unreadSources.length?`<ul>${analysis.coverage.unreadSources.map(s=>`<li>${e(s.sourceId)}: ${e(s.reason)}</li>`).join('')}</ul>`:''}`;}
  function analysisMarkup(value){return `<div class="ai-brief-text">${e(value.projectBrief)}</div>
    <h4>Proposed tasks</h4>${value.proposedTasks.length?`<ul>${value.proposedTasks.map(t=>`<li>${e(t.text)} <small>(proposed)</small></li>`).join('')}</ul>`:'<p>No tasks proposed.</p>'}
    <h4>Missing information</h4>${value.missingInformation.length?`<ul>${value.missingInformation.map(i=>`<li><strong>${e(i.topic)}</strong> (${e(i.materiality)}): ${e(i.whyItMatters)}</li>`).join('')}</ul>`:'<p>No unresolved gaps identified in the reviewed material.</p>'}
    <h4>Conflicts</h4>${value.conflicts.length?`<ul>${value.conflicts.map(i=>`<li><strong>${e(i.topic)}</strong>: ${e(i.explanation)}</li>`).join('')}</ul>`:'<p>No conflicts reported.</p>'}
    <h4>Draft questions for the customer</h4>${value.questionsForCustomer.length?`<ol>${value.questionsForCustomer.map(q=>`<li>${e(q.question)}</li>`).join('')}</ol>`:'<p>No follow-up questions recommended.</p>'}
    <h4>Proposed field values - not applied</h4>${value.fieldProposals.length?value.fieldProposals.map(p=>`<div class="ai-proposal"><strong>${e(p.field)}</strong><pre>${e(JSON.stringify(p.value,null,2))}</pre><p>${e(p.rationale)}</p><ul>${p.evidence.map(x=>`<li><strong>${e(x.sourceId)}</strong>: “${e(x.quote)}”</li>`).join('')}</ul></div>`).join(''):'<p>No field changes proposed.</p>'}${coverage(value)}`;}
  function renderAccepted(){const target=root.querySelector('[data-ai-accepted]');const accepted=state.acceptedBrief;target.innerHTML=accepted?`<div class="ai-accepted"><h3>${accepted.isStale?'Previously accepted brief - source changed':'Accepted brief in this portal'}</h3><p class="quiet-note">${e(accepted.draftId)} · ${e(stamp(accepted.review.at))}</p><div class="ai-brief-text">${e(accepted.analysis.projectBrief)}</div><p class="quiet-note">Stored separately from Smartsheet. ${accepted.isStale?'Prepare a fresh context before using this as the current brief.':'Original job fields are preserved.'}</p></div>`:'';}
  function renderDraft(){const target=root.querySelector('[data-ai-draft]');if(!draft){target.innerHTML='<p>No AI draft has been saved for this job yet.</p>';return;}
    target.innerHTML=`<h3>Saved draft · version ${draft.version}</h3><p data-testid="ai-draft-status"><strong>${e(draft.isStale?'Source changed':draft.status.replaceAll('_',' '))}</strong> · ${e(draft.draftId)}</p><p class="quiet-note">Context ${e(draft.contextId)} · ${e(stamp(draft.submittedAt))}. These are AI suggestions for review, not accepted work or messages already sent.</p>${analysisMarkup(draft.analysis)}
    ${draft.review?`<p class="quiet-note">Last review: ${e(draft.review.decision)} · ${e(stamp(draft.review.at))}${draft.review.note?' · '+e(draft.review.note):''}</p>`:''}
    ${state.canReview?`<div class="field"><label for="ai-review-note">Review note (optional)</label><textarea id="ai-review-note" maxlength="1000"></textarea></div><div class="ai-actions"><button class="button button-primary button-small" data-ai-action="accept" data-testid="ai-review-change" ${draft.isStale||draft.status==='accepted'?'disabled':''}>Accept brief in portal</button><button class="button button-small" data-ai-action="reject" ${draft.status==='rejected'?'disabled':''}>Reject draft</button></div><p class="quiet-note">Acceptance records your signed-in review of this draft. It does not change Smartsheet fields or prove independent human presence.</p>`:'<p class="quiet-note">A currently authorized job editor can accept or reject this draft.</p>'}`;
  }
  function renderPacket(){const target=root.querySelector('[data-ai-context]');target.innerHTML=packet?`<p><strong>${packet.isStale?'Source changed - prepare a fresh context.':'Context prepared.'}</strong> ${e(packet.context.contextId)}</p><p class="quiet-note">Job ${e(packet.context.jobId)} · ${e(stamp(packet.context.preparedAt))} · ${packet.context.sources.length} source entries. Unknown/relative dates remain unresolved.</p><div class="field"><label for="ai-context-json">Job context, instructions and output schema</label><textarea id="ai-context-json" data-testid="ai-context-json" readonly rows="12">${e(JSON.stringify(packet,null,2))}</textarea></div><div class="ai-actions"><button class="button button-small" data-ai-action="copy">Copy context and instructions</button><button class="button button-small" data-ai-action="download">Download context JSON</button></div><p class="quiet-note">Share this private context only with your approved agent. Ask Codex to analyze this job and import a contracted draft below. No model is called by preparing context.</p>`:'';}
  function renderHistory(){root.querySelector('[data-ai-history]').innerHTML=history.length?`<label for="ai-history">Saved draft history</label><select id="ai-history"><option value="">Choose a saved version</option>${history.map(h=>`<option value="${e(h.draftId)}">${e(stamp(h.at))} · v${h.version} · ${e(h.draftId.slice(0,14))}</option>`).join('')}</select>${state.hasMore?'<button class="button button-small" data-ai-action="older">Load older drafts</button>':''}`:'';}
  function renderRefs(more){root.querySelector('[data-ai-references]').innerHTML=`${refs.length?refs.map(r=>`<label class="ai-reference"><input type="checkbox" value="${e(r.sourceId)}"><span>${e(r.label)} <small>(${e(r.kind)}${r.mime?', '+e(r.mime):''})</small></span></label>`).join(''):'<p>No attached files or reference links on this job.</p>'}${more?'<button class="button button-small" data-ai-action="references">Load more references</button>':''}`;}
  async function loadRefs(){const data=await request('/reference-inventory?offset='+referencePage);refs.push(...data.references);referencePage+=data.references.length;renderRefs(data.hasMore);}
  async function refresh(){state=await request('/ai');draft=state.latestDraft;history.splice(0,history.length,...state.history);historyPage=10;renderDraft();renderAccepted();renderHistory();}
  root.innerHTML='<h2>AI project brief</h2><p role="status">Checking this job’s AI pilot access…</p>';
  try{
    state=await request('/ai');if(!root.isConnected)return;
    if(!state.enabled){root.innerHTML='<h2>AI project brief</h2><p>This job is outside the selected AI pilot. Its existing workflow is unchanged.</p>';return;}
    draft=state.latestDraft;history.push(...state.history);historyPage=10;
    root.inert=true;root.setAttribute('aria-busy','true');
    root.innerHTML=`<h2>AI project brief <span class="planned-label">Agent-assisted DEV pilot</span></h2><p>Prepare the job context, use your Codex agent to analyze it, and save a draft for review. This pilot does not run a model or edit Smartsheet fields automatically.</p><div class="notice" role="status" data-testid="operation-status">Loading saved context and reference inventory…</div><div data-ai-accepted></div>
    <details open><summary>1. Prepare job context</summary><p>All permitted request fields are included, including notes in Additional Details. Select reference files to read. Text and text-based PDFs are supported; images, external links and unreadable files are reported as incomplete coverage.</p><div data-ai-references></div><button class="button button-small" data-ai-action="prepare" data-testid="ai-prepare-context">Prepare job context</button><div data-ai-context></div></details>
    <details><summary>2. Import an AI draft</summary><p>Paste the analysis JSON produced by your authorized agent. Evidence quotes, coverage and proposals are validated before saving. Maximum 256 KiB.</p><form data-ai-import><div class="field"><label for="ai-import-json">AI analysis JSON</label><textarea id="ai-import-json" data-testid="ai-import-json" rows="12" required spellcheck="false"></textarea></div><button class="button button-primary button-small" type="submit" data-testid="ai-save-draft" ${state.canSaveDraft?'':'disabled'}>Validate and save draft</button></form></details>
    <details open><summary>3. Review the saved draft</summary><div data-ai-history></div><div data-ai-draft></div></details>`;
    renderDraft();renderAccepted();renderHistory();await loadRefs();
    if(state.latestContextId){packet=await request('/intake-contexts/'+encodeURIComponent(state.latestContextId));renderPacket();}
  }catch(error){root.inert=false;root.removeAttribute('aria-busy');root.innerHTML=`<h2>AI project brief</h2><p class="notice notice-warning" role="status">${e(error.message)}</p>`;return;}
  async function run(action,payload,task){if(waiting)return;waiting=true;
    const encoded=typeof payload==='string'?payload:JSON.stringify(payload);
    if(!operation||operation.action!==action||operation.payload!==encoded||operation.confirmed)operation={action,payload:encoded,key:crypto.randomUUID(),confirmed:false};
    const current=operation;
    root.querySelectorAll('button').forEach(b=>{b.dataset.wasDisabled=String(b.disabled);b.disabled=true;});
    try{await task(current.key);current.confirmed=true;}
    catch(error){status(`${error.message} Operation ${current.key}. Retry the same action to check its result.`,true);}
    finally{waiting=false;root.querySelectorAll('button').forEach(b=>{if(b.dataset.wasDisabled!==undefined){b.disabled=b.dataset.wasDisabled==='true';delete b.dataset.wasDisabled;}});}
  }
  root.addEventListener('click',async event=>{
    const button=event.target.closest('[data-ai-action]');if(!button)return;
    const action=button.dataset.aiAction;
    if(action==='copy'){try{await navigator.clipboard.writeText(JSON.stringify(packet,null,2));status('Private context copied.');}catch{status('Clipboard unavailable. Select the visible context text or use Download context JSON.',true);}return;}
    if(action==='download'){const url=URL.createObjectURL(new Blob([JSON.stringify(packet,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=job.id+'-ai-context.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);status('Context download requested.');return;}
    if(action==='prepare'){const selectedReferenceIds=[...root.querySelectorAll('[data-ai-references] input:checked')].map(el=>el.value);await run('prepare',selectedReferenceIds,async key=>{status('Reading selected job context and references…');packet=await request('/intake-contexts',{method:'POST',key,body:{selectedReferenceIds}});renderPacket();status('Context saved: '+packet.context.contextId+'. Ready for your authorized agent.');});return;}
    if(action==='references'){await run('references',referencePage,async()=>loadRefs());return;}
    if(action==='older'){await run('history',historyPage,async()=>{const page=await request('/ai?offset='+historyPage);history.push(...page.history);historyPage+=page.history.length;state.hasMore=page.hasMore;renderHistory();});return;}
    if(action==='accept'||action==='reject'){const body={decision:action==='accept'?'accepted':'rejected',note:root.querySelector('#ai-review-note')?.value||''};await run('review-'+draft.draftId,body,async key=>{status('Saving the draft review…');draft=await request('/ai-drafts/'+encodeURIComponent(draft.draftId)+'/reviews',{method:'POST',body,key});await refresh();status('Review saved. Smartsheet fields and native workflows were preserved.');});}
  });
  root.addEventListener('change',async event=>{if(event.target.id==='ai-history'&&event.target.value)await run('history-read',event.target.value,async()=>{draft=await request('/ai-drafts/'+encodeURIComponent(event.target.value));renderDraft();status('Saved version loaded.');});});
  root.querySelector('[data-ai-import]').addEventListener('submit',async event=>{event.preventDefault();const raw=root.querySelector('#ai-import-json').value;if(new TextEncoder().encode(raw).length>256*1024){status('AI JSON exceeds 256 KiB.',true);return;}await run('import',raw,async key=>{status('Validating evidence and saving the draft…');draft=await request('/ai-drafts',{method:'POST',raw:true,body:raw,key});const savedId=draft.draftId;await refresh();root.querySelector('#ai-import-json').value='';status('Draft saved: '+savedId+'. Review it below. No job fields changed.');});});
  root.inert=false;root.removeAttribute('aria-busy');status('Ready for an agent. Job '+job.id+'.');
}
