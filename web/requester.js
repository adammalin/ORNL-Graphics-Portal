/* Read-only requester UI. All identity and ownership checks remain server-side. */
const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=value=>{if(!value)return 'To be confirmed';const d=new Date(value.length===10?value+'T12:00:00':value);return Number.isNaN(+d)?'Not available':new Intl.DateTimeFormat('en-US',{dateStyle:'medium'}).format(d);};
const stages=['Submitted','Being assigned','Accepted','In progress','In review','Completed'];
export function mountRequester({main,api,session}){
  let offset=0,filter='all',busy=false,pending=false;
  const requestLink=r=>'#/requests/'+encodeURIComponent(r.receipt);
  const card=r=>`<article class="request-summary"><div class="card-top"><span class="job-id">${e(r.jobId)}</span><span class="stage">${e(r.statusLabel)}</span></div><h2><a href="${requestLink(r)}">${e(r.title)}</a></h2><dl class="metadata"><div><dt>Submitted</dt><dd>${date(r.submittedAt)}</dd></div><div><dt>Confirmed delivery</dt><dd>${r.available?date(r.confirmedDueDate):'Not available'}</dd></div><div><dt>Designer</dt><dd>${e(r.designer||'Being confirmed')}</dd></div></dl><a class="button button-small" href="${requestLink(r)}">View my request →</a></article>`;
  async function render(){
    if(busy){pending=true;return;}busy=true;const loadedHash=location.hash;main.setAttribute('aria-busy','true');
    const activeFocus=document.activeElement?.id;
    try{
      const match=location.hash.match(/^#\/requests\/([^/]+)$/);
      if(match){
        const r=await api('my-requests/'+encodeURIComponent(decodeURIComponent(match[1])));if(location.hash!==loadedHash){pending=true;return;}
        main.innerHTML=`<div class="breadcrumbs"><a href="#/">My Requests</a><span>/</span>${e(r.jobId)}</div><div class="page-heading"><div><div class="eyebrow">Your project</div><h1>${e(r.title)}</h1><p>${e(r.jobId)} · ${e(r.statusLabel)}</p></div><button id="requester-refresh" class="button button-small" type="button">Refresh status</button></div>${r.available?details(r):`<div class="notice">${e(r.message)}</div>`}`;
      }else{
        const data=await api('my-requests?offset='+offset);if(location.hash!==loadedHash){pending=true;return;}
        const rows=data.requests.filter(r=>filter==='all'||(filter==='completed'?r.status==='completed':r.status!=='completed'));
        main.innerHTML=`<div class="page-heading"><div><div class="eyebrow">Creative Services</div><h1>My Requests</h1><p>Follow the creative work you have requested.</p></div><div class="page-actions"><button id="requester-refresh" class="button button-small" type="button">Refresh status</button><a class="button button-primary" href="/request">New request</a></div></div><p class="quiet-note">Signed in as ${e(session.name)}. This page shows only requests linked to your verified sign-in.</p><div class="toolbar"><label for="requester-filter">Show requests on this page</label><select id="requester-filter">${[['all','All'],['active','Open'],['completed','Completed']].map(([v,l])=>`<option value="${v}" ${filter===v?'selected':''}>${l}</option>`).join('')}</select></div><div class="request-summary-grid">${rows.map(card).join('')||'<div class="empty-state"><h2>No requests here yet</h2><p>New requests you submit through this portal will appear here. Try another filter or submit a new request.</p></div>'}</div><div class="page-actions requester-pagination"><button type="button" id="requester-previous" class="button button-small" ${offset?'':'disabled'}>Previous page</button><span>Page ${offset/20+1}</span><button type="button" id="requester-next" class="button button-small" ${data.hasMore?'':'disabled'}>Next page</button></div>`;
      }
      document.title=(match?'Your request':'My Requests')+' · ORNL Creative Services';
      main.querySelector('#requester-refresh').addEventListener('click',render);
      main.querySelector('#requester-filter')?.addEventListener('change',event=>{filter=event.target.value;render();});
      main.querySelector('#requester-previous')?.addEventListener('click',()=>{offset=Math.max(0,offset-20);render();});
      main.querySelector('#requester-next')?.addEventListener('click',()=>{offset+=20;render();});
      if(activeFocus)main.querySelector('#'+activeFocus)?.focus();
    }catch(error){
      main.innerHTML=`<div class="page-heading"><h1>Your requests could not be loaded.</h1></div><div class="notice" role="status">${e(error.message)}</div><div class="page-actions"><button id="requester-retry" class="button" type="button">Try again</button><a class="button" href="/my-requests">My Requests</a>${error.status===401?'<a class="button button-primary" href="/auth/microsoft/login">Sign in with Microsoft</a>':''}</div>`;
      main.querySelector('#requester-retry').addEventListener('click',render);
    }finally{busy=false;main.removeAttribute('aria-busy');if(pending){pending=false;render();}}
  }
  function details(r){
    const original=r.originalRequest||{};
    const originalLabels={description:'Original project description',deliverables:'Deliverables and quantities',audience:'Intended audience',specifications:'Dimensions / file formats',requestorGroup:'Group / department',notes:'Notes / additional details',taskType:'Task type',dueDate:'Requested delivery as submitted'};
    const originalText=Object.entries(originalLabels).filter(([key])=>original[key]).map(([key,label])=>`<section class="detail-section"><h2>${label}</h2><p>${e(Array.isArray(original[key])?original[key].join(' · '):original[key])}</p></section>`).join('');
    const referenceLinks=['reference1','reference2'].map(key=>original[key]).filter(value=>{try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password;}catch{return false;}});
    const referenceSection=referenceLinks.length?`<section class="detail-section"><h2>Reference links you submitted</h2><ul>${referenceLinks.map(url=>`<li><a class="inline-link" href="${e(url)}" target="_blank" rel="noopener noreferrer">${e(url)}</a></li>`).join('')}</ul></section>`:'';
    const files=(category,label)=>{const rows=(r.files||[]).filter(f=>f.category===category);return `<section class="detail-section"><h2>${label}</h2>${rows.length?`<ul class="requester-files">${rows.map(f=>`<li><span>${e(f.name)} <small>${e(f.size)}</small></span><a href="${e(f.url)}" download>Download</a></li>`).join('')}</ul>`:'<p>None available yet.</p>'}</section>`;};
    return `<section class="panel"><h2>Current progress</h2><ol class="request-progress">${stages.map((label,i)=>`<li class="${i<=r.step?'reached':''}" ${i===r.step?'aria-current="step"':''}>${label}</li>`).join('')}</ol><p class="quiet-note">${r.lastUpdatedAt?'Job last updated '+date(r.lastUpdatedAt)+'.':'The latest stage is loaded when you open or refresh this page.'} This tracker shows the current stage.</p></section><dl class="facts"><div><dt>Designer</dt><dd>${e(r.designer||'Being confirmed')}</dd></div><div><dt>Requested delivery</dt><dd>${date(r.requestedDueDate)}</dd></div><div><dt>Confirmed delivery</dt><dd>${date(r.confirmedDueDate)}</dd></div><div><dt>Submitted</dt><dd>${date(r.submittedAt)}</dd></div></dl><div class="notice">Your request is read-only here. Contact Creative Services if the scope or delivery needs change.</div>${originalText}${referenceSection}${files('submitted','Your submitted references')}${r.unlinkedSubmittedFiles?.length?`<p>Earlier submitted filenames: ${r.unlinkedSubmittedFiles.map(e).join(', ')}. Download links are not available for these earlier uploads.</p>`:''}${files('shared','Files shared by Creative Services')}<a class="button" href="/my-requests">Back to My Requests</a>`;
  }
  window.addEventListener('hashchange',render);
  return render();
}
