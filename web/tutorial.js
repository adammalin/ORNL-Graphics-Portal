import {TUTORIALS,lessonsFor,newPractice,practiceAction} from './tutorial-content.js';
const e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stages=['Submitted','Being assigned','Accepted','In progress','In review','Completed'];
const locations={workspace:'Sidebar → My work',offers:'My work → Waiting offers → View job',details:'Project card → View job',references:'View job → Reference files & links',editing:'View job → Edit job',stages:'View job → Project stage',ai:'View job → AI project brief (eligible jobs)',sharing:'View job → Reference files → Requester access',find:'Sidebar → All projects or Completed & archived',intake:'All projects → New lane',routing:'View job → Offer to a designer',responses:'All projects → Assigned and Accepted lanes',workload:'Sidebar → Team workload',request:'Header → New request',tracking:'Header → My Requests → View my request'};
export function createTutorial({request=null,kind='staff',role='designer',aiAvailable=false,trackingAvailable=false}={}){
  const tracks=kind==='requester'?['requester']:kind==='demo'?['designer','coordinator','requester']:['designer','coordinator'];
  let prefs={track:tracks.includes(role)?role:tracks[0],lesson:0,seen:false},track=prefs.track,index=0,intro=true,practice=newPractice(),returnFocus,saveQueue=Promise.resolve(),saveError='';
  const dialog=document.createElement('dialog');dialog.id='tutorial-dialog';dialog.className='tutorial-dialog';dialog.setAttribute('aria-labelledby','tutorial-title');document.body.append(dialog);
  const lessons=()=>lessonsFor(track,{aiAvailable,trackingAvailable});
  function persist(action){
    if(!request)return Promise.resolve();
    const body={action,track,lesson:index};
    saveQueue=saveQueue.catch(()=>{}).then(()=>request({method:'POST',body})).then(result=>{prefs=result;saveError='';}).catch(()=>{saveError='Your progress could not be saved. You can still use this guide; use Help to open it again.';const status=dialog.querySelector('[data-tutorial-save]');if(status)status.textContent=saveError;});
    return saveQueue;
  }
  function preview(){
    const type=lessons()[index].practice;
    const button=(action,label,extra='')=>`<button type="button" class="button button-small" data-tutorial-action="${action}" ${extra}>${label}</button>`;
    const card=`<div class="tutorial-example"><span class="job-id">PRACTICE-101</span><h3>${e(practice.title)}</h3><dl><div><dt>Stage</dt><dd>${e(practice.stage)}</dd></div><div><dt>Designer</dt><dd>${e(practice.designer)}${practice.response==='accepted'?' · Accepted':' · Offer pending'}</dd></div><div><dt>Task type</dt><dd>Fact sheet / Flyer / Handout</dd></div></dl></div>`;
    let controls='';
    if(type==='workspace')controls=`<div class="tutorial-actions">${button('view','My work','data-value="my"')}${button('view','All projects','data-value="all"')}</div><p>${practice.view==='my'?(practice.response==='accepted'?'PRACTICE-101 appears in My work.':'No accepted practice assignment yet. An offer is waiting for your response.'):'PRACTICE-101 is an offer awaiting acceptance.'}</p>${button('accept','Accept practice offer')}`;
    else if(type==='offers')controls=`<div class="tutorial-actions">${button('accept','Accept practice offer')}${button('decline','Decline practice offer')}</div>`;
    else if(type==='details')controls=`${button('details',practice.detail?'Close practice details':'View practice job')} ${practice.detail?`<div class="tutorial-sample-copy"><strong>Project description</strong><p>${e(practice.description)}</p><strong>Notes / additional details</strong><p>${e(practice.notes)}</p><p>Requested delivery is supplied in the notes. There is no need to ask the customer for it again.</p></div>`:''}`;
    else if(type==='references')controls=`<ul>${practice.files.map(name=>`<li>${e(name)}</li>`).join('')}</ul><div class="tutorial-actions">${button('preview','Preview example reference')}${button('add-file','Add an example file')}</div>${practice.preview?'<div class="tutorial-sample-copy"><strong>Approved copy.txt</strong><p>Fictional Science Open House. December 11, 2026, 10 a.m., Fictional Hall. Deliver one PDF and one editable source file.</p></div>':''}`;
    else if(type==='editing')controls=`<div class="field"><label for="tutorial-practice-title">Practice job title</label><input id="tutorial-practice-title" maxlength="120" value="${e(practice.title)}"></div><div class="field"><label for="tutorial-practice-date">Practice requested delivery</label><input id="tutorial-practice-date" type="date" value="${e(practice.date||'2026-12-04')}"></div>${button('edit','Save practice details')}`;
    else if(type==='stages')controls=`<p>First accept this practice offer, then try changing its stage.</p>${button('accept','Accept practice offer')}<div class="field"><label for="tutorial-practice-stage">Practice stage</label><select id="tutorial-practice-stage">${['Accepted','In Progress','In Review','Completed','Archived'].map(s=>`<option ${s===practice.stage?'selected':''}>${s}</option>`).join('')}</select></div>${button('stage','Update practice stage')}`;
    else if(type==='routing'||type==='workload')controls=`${type==='workload'?'<div class="tutorial-sample-copy"><p><strong>Alex Rivera:</strong> 3 active projects · 18 estimated hours</p><p><strong>Morgan Lee:</strong> 2 active projects · 9 estimated hours</p><p>Fictional estimates only. Calendar availability is not connected.</p></div>':''}<div class="field"><label for="tutorial-practice-designer">Practice requested designer</label><select id="tutorial-practice-designer">${['Alex Rivera','Morgan Lee'].map(n=>`<option ${n===practice.designer?'selected':''}>${n}</option>`).join('')}</select></div>${button('offer','Save practice offer')}`;
    else if(type==='responses')controls=`<p>This is a simulation of the receiving designer’s decision, not an action you can perform for them on a live job.</p><div class="tutorial-actions">${button('accept','See a designer accept')}${button('decline','See a designer decline')}</div>`;
    else if(type==='intake')controls=`<div class="field"><label for="tutorial-practice-title">Practice request title</label><input id="tutorial-practice-title" maxlength="120" value="${e(practice.title)}"></div><p>Project description: ${e(practice.description)}</p><p>Additional details: ${e(practice.notes)}</p>${button('create','Submit practice request')}`;
    else if(type==='ai')controls=`${button('brief','View an example AI draft')}${practice.brief?`<div class="tutorial-sample-copy"><strong>Example brief</strong><p>Create a one-page flyer for scientists attending the fictional open house. Deliver one PDF and an editable source file by December 4.</p><p><strong>Proposed tasks:</strong> set up the page, lay out approved copy, check event details, export deliverables.</p><p><strong>Follow-up questions:</strong> none. The notes and reference supply the required details.</p><p><strong>Evidence:</strong> “Requested delivery: December 4, 2026.”</p>${button('review','Accept practice brief')}</div>`:''}`;
    else if(type==='sharing')controls=`<p><strong>Final flyer.pdf</strong> · ${practice.shared?'Shared with the practice requester':'Internal only'}</p>${button('share',practice.shared?'Stop practice sharing':'Share example file with practice requester')}<p>Only this walkthrough’s example visibility changes.</p>`;
    else if(type==='find')controls=`<div class="tutorial-actions">${button('view','Active projects','data-value="active"')}${button('view','Completed & archived','data-value="closed"')}${button('view','Copied projects','data-value="copied"')}</div><p>${practice.view==='closed'?'PRACTICE-099 · Completed poster · Archived · Reference files retained.':practice.view==='copied'?'PRACTICE-COPY · Copied project · Read-only. No edit or drag controls.':'PRACTICE-101 · Active practice request.'}</p>`;
    else if(type==='tracking'){const current={'Assigned':1,'Accepted':2,'In Progress':3,'In Review':4,'Completed':5}[practice.stage]||0;controls=`<ol class="request-progress">${stages.map((s,i)=>`<li class="${i<=current?'reached':''}" ${i===current?'aria-current="step"':''}>${e(s)}</li>`).join('')}</ol><p>The requester can read this view, not change it.</p><div class="tutorial-actions">${button('track','Preview work in progress','data-value="In Progress"')}${button('track','Preview completed work','data-value="Completed"')}</div>`;}
    else controls='<p>Practice complete. Return to the app whenever you are ready.</p>';
    return `<div class="tutorial-practice"><div class="tutorial-practice-label">Practice mode · Fictional information</div>${type==='finish'?'':card}${controls}<p class="tutorial-feedback" role="status" aria-live="polite">${e(practice.message)}</p></div>`;
  }
  function render(focus=false){
    const list=lessons(),lesson=list[index];
    const where=track==='requester'?({request:'Header → New request',references:'New request → References and additional details',tracking:'Header → My Requests → View my request'}[lesson.id]||''):(locations[lesson.id]||locations[lesson.practice]||'');
    dialog.innerHTML=`<div class="dialog-header"><div><div class="eyebrow">Graphics Portal walkthrough</div><h2 id="tutorial-title" tabindex="-1">${intro?'Welcome. Choose your walkthrough.':e(lesson.title)}</h2></div><button class="dialog-close" type="button" data-tutorial-action="exit" aria-label="Exit tutorial">×</button></div>
    ${intro?`<div class="dialog-body tutorial-intro"><p>Learn the app by practicing with fictional jobs. Practice actions stay in this walkthrough and do not change live records, share files or send messages.</p><div class="field"><label for="tutorial-role">Which workflow would you like to learn?</label><select id="tutorial-role">${tracks.map(t=>`<option value="${t}" ${track===t?'selected':''}>${e(TUTORIALS[t].label)}</option>`).join('')}</select><small>This selects a lesson, not your account’s permissions.</small></div><p>${e(TUTORIALS[track].description)}</p><p>${list.length} chapters. Use Back, Next or the chapter menu. You can exit whenever you need and reopen from Help.</p><div class="tutorial-actions"><button type="button" class="button button-primary" data-tutorial-action="start">Start walkthrough</button>${prefs.lesson>0&&track===prefs.track?'<button type="button" class="button" data-tutorial-action="resume">Resume saved chapter</button>':''}<button type="button" class="text-button" data-tutorial-action="exit">Skip for now</button></div><div class="tutorial-chapter-preview">${list.map(l=>`<span>${e(l.title)}</span>`).join('')}</div></div>`:
    `<div class="tutorial-layout"><nav class="tutorial-chapters" aria-label="Tutorial chapters">${list.map((l,i)=>`<button type="button" data-tutorial-action="chapter" data-index="${i}" ${i===index?'aria-current="step"':''}>${i+1}. ${e(l.title)}</button>`).join('')}<button type="button" data-tutorial-action="choose">Change walkthrough</button></nav><section class="tutorial-lesson" aria-label="Current tutorial chapter"><div class="tutorial-progress"><span>${e(TUTORIALS[track].label)} · Chapter ${index+1} of ${list.length}</span><progress value="${index+1}" max="${list.length}" aria-label="Walkthrough progress"></progress></div><p class="tutorial-lead">${e(lesson.intro)}</p>${where?`<p class="tutorial-location"><strong>Where to find it:</strong> ${e(where)}</p>`:''}<ul class="tutorial-points">${lesson.points.map(t=>`<li>${e(t)}</li>`).join('')}</ul>${preview()}</section></div><div class="dialog-footer tutorial-footer"><button type="button" class="button" data-tutorial-action="back" ${index===0?'disabled':''}>Back</button><span>Practice never changes live jobs.</span><button type="button" class="button button-primary" data-tutorial-action="${index===list.length-1?'finish':'next'}">${index===list.length-1?'Finish walkthrough':'Next chapter'}</button></div>`}<p class="tutorial-save-note" data-tutorial-save role="status">${e(saveError)}</p>`;
    if(focus)dialog.querySelector('#tutorial-title').focus();
  }
  function resetPractice(){practice=newPractice();if(['editing','ai','sharing','references'].includes(lessons()[index].practice)){practice.stage='In Progress';practice.response='accepted';}}
  function open(){
    if(dialog.open)return;
    returnFocus=document.querySelector('#portal-help,#requester-help')||document.activeElement;intro=true;track=tracks.includes(prefs.track)?prefs.track:tracks[0];index=Math.min(prefs.lesson||0,lessons().length-1);practice=newPractice();render();dialog.showModal();dialog.querySelector('#tutorial-role').focus();
  }
  async function exit(complete=false){
    await persist(complete?'complete':'dismiss');dialog.close();if(returnFocus?.isConnected)returnFocus.focus();
  }
  dialog.addEventListener('cancel',event=>{event.preventDefault();exit();});
  dialog.addEventListener('change',event=>{if(event.target.id==='tutorial-role'){track=event.target.value;index=0;render();dialog.querySelector('#tutorial-role').focus();}});
  dialog.addEventListener('click',event=>{
    const button=event.target.closest('[data-tutorial-action]');if(!button)return;
    const action=button.dataset.tutorialAction;
    if(action==='exit'||action==='finish'){exit(action==='finish');return;}
    if(action==='choose'){intro=true;render(true);return;}
    if(['start','resume','next','back','chapter'].includes(action)){
      if(action==='start')index=0;
      if(action==='resume')index=Math.min(prefs.lesson||0,lessons().length-1);
      if(action==='next')index=Math.min(index+1,lessons().length-1);
      if(action==='back')index=Math.max(0,index-1);
      if(action==='chapter')index=Number(button.dataset.index);
      intro=false;resetPractice();render(true);persist('progress');return;
    }
    let value=button.dataset.value;
    if(action==='offer')value=dialog.querySelector('#tutorial-practice-designer').value;
    if(action==='stage')value=dialog.querySelector('#tutorial-practice-stage').value;
    if(action==='edit')value={title:dialog.querySelector('#tutorial-practice-title').value,date:dialog.querySelector('#tutorial-practice-date').value};
    if(action==='create')value=dialog.querySelector('#tutorial-practice-title').value;
    practice=practiceAction(practice,action,value);render();dialog.querySelector('[data-tutorial-action="'+action+'"]')?.focus({preventScroll:true});dialog.querySelector('.tutorial-feedback')?.scrollIntoView({block:'nearest'});
  });
  return {
    async initialize(){if(!request)return;const result=await request({method:'POST',body:{action:'claim'}});prefs=result;if(result.autoStart)open();},
    async open(){if(request){try{prefs=await request({});}catch{saveError='Saved progress is unavailable. This practice session can still run.';}}open();}
  };
}
