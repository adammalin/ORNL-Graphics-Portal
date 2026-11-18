import {escapeHtml as e} from './domain.js';
export function mountDeleted({root,api,run,onChanged}){
 if(root.dataset.mounted)return;root.dataset.mounted='true';let jobs=[];
 async function load(){
  try{const data=await api('/v1/deleted-jobs');if(!root.isConnected)return;jobs=data.jobs;
   root.innerHTML=`<div class="page-heading"><div><div class="eyebrow">Recoverable jobs</div><h1>Deleted jobs</h1><p>Admins can restore any job here. Other staff see only jobs they created.</p></div><button type="button" class="button button-small" data-deleted-refresh>Refresh deleted jobs</button></div><div class="notice">These jobs are hidden in this portal. Their Smartsheet rows, attachments and native workflows remain intact.</div><div class="list-wrap"><table><thead><tr><th>Job</th><th>Project</th><th>Deleted</th><th>Action</th></tr></thead><tbody>${jobs.map(p=>`<tr><td>${e(p.id)}</td><td>${e(p.title)}</td><td>${e(new Date(p.deletedAt).toLocaleString())}</td><td>${p.canRestore?`<button class="button button-small" type="button" data-restore-job="${e(p.id)}">Restore job</button>`:'Restoration unavailable'}</td></tr>`).join('')||'<tr><td colspan="4">No deleted jobs are available to your account.</td></tr>'}</tbody></table></div><div data-restore-panel></div><p data-lifecycle-status role="status"></p>`;
  }catch(error){root.innerHTML=`<h1>Deleted jobs</h1><p class="notice notice-warning">${e(error.message)}</p><button type="button" class="button" data-deleted-refresh>Refresh deleted jobs</button>`;}
 }
 root.addEventListener('click',event=>{
  if(event.target.closest('[data-deleted-refresh]')){load();return;}
  const button=event.target.closest('[data-restore-job]');if(!button)return;
  const p=jobs.find(j=>j.id===button.dataset.restoreJob);if(!p)return;
  root.querySelector('[data-restore-panel]').innerHTML=`<section class="panel"><h2>Restore ${e(p.id)}</h2><p>${e(p.title)}</p><form id="restore-job-form" data-job="${e(p.id)}"><div class="field"><label for="restore-confirmation">Type ${e(p.id)} to confirm</label><input id="restore-confirmation" name="confirmation" required autocomplete="off"></div><button class="button button-primary" type="submit">Confirm restore</button></form></section>`;
  root.querySelector('#restore-confirmation').focus();
 });
 root.addEventListener('submit',async event=>{
  if(event.target.id!=='restore-job-form')return;event.preventDefault();
  const p=jobs.find(j=>j.id===event.target.dataset.job),message=root.querySelector('[data-lifecycle-status]');
  try{const confirmation=new FormData(event.target).get('confirmation');await run(()=>api('/v1/jobs/'+encodeURIComponent(p.id)+'/lifecycle',{method:'POST',body:{action:'restore',revision:p.sourceRevision,version:p.lifecycleVersion,confirmation,reason:''}}));await onChanged();await load();root.querySelector('[data-lifecycle-status]').textContent='Job restored. It is available in the project views again.';}
  catch(error){message.textContent=error.message;}
 });
 load();
}
