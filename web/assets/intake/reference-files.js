/* Selected draft files only; clearing never changes saved attachments or originals. */
export function referenceFileError(files){
  const allowed=new Set(['image/png','image/jpeg','image/webp','application/pdf','text/plain']);
  return files.length>10||files.some(f=>!allowed.has(f.type)||!f.size||f.size>30*1024*1024)
    ?'Choose up to 10 PNG, JPEG, WebP, PDF or plain text files, 30 MB each.':'';
}
export function mountReferenceFiles(form){
  const input=form.elements.attachments,clear=form.querySelector('[data-clear-reference-files]'),status=form.querySelector('[data-reference-file-status]');
  if(!input||!clear)return;
  function update(){const files=[...input.files];clear.hidden=!files.length;if(status)status.textContent=referenceFileError(files)||(files.length?files.map(f=>f.name).join(' · '):'No files selected.');}
  input.addEventListener('change',update);
  clear.addEventListener('click',()=>{input.value='';update();input.focus();});
  update();
}
