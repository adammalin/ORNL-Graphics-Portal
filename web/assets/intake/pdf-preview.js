import * as pdfjs from './pdfjs/pdf.min.mjs';
import {pdfSourcePath} from './pdf-source.js';
pdfjs.GlobalWorkerOptions.workerSrc=new URL('./pdfjs/pdf.worker.min.mjs',import.meta.url).href;
const $=id=>document.getElementById(id),status=$('status'),canvas=document.querySelector('canvas');
let pdf,current=1,rendering=false;
async function render(){
 if(!pdf||rendering)return;rendering=true;$('previous').disabled=true;$('next').disabled=true;$('zoom').disabled=true;
 try{
  status.textContent='Rendering page '+current+'…';const page=await pdf.getPage(current),scale=Number($('zoom').value),viewport=page.getViewport({scale}),ratio=Math.min(window.devicePixelRatio||1,2),pixelScale=Math.min(ratio,Math.sqrt(16000000/(viewport.width*viewport.height)));
  canvas.width=Math.floor(viewport.width*pixelScale);canvas.height=Math.floor(viewport.height*pixelScale);canvas.style.width=Math.floor(viewport.width)+'px';canvas.style.height=Math.floor(viewport.height)+'px';
  await page.render({canvasContext:canvas.getContext('2d'),viewport,transform:pixelScale===1?null:[pixelScale,0,0,pixelScale,0,0]}).promise;
  const text=await page.getTextContent();$('page-text').textContent=text.items.map(x=>x.str+(x.hasEOL?'\n':' ')).join('');
  $('page-label').textContent='Page '+current+' of '+pdf.numPages;canvas.setAttribute('aria-label','PDF preview, page '+current+' of '+pdf.numPages);status.textContent='Page '+current+' ready';
 }catch(error){status.textContent='This PDF page could not be previewed. Download the original to open it.';}
 finally{rendering=false;$('previous').disabled=!pdf||current<=1;$('next').disabled=!pdf||current>=pdf.numPages;$('zoom').disabled=false;}
}
$('previous').addEventListener('click',()=>{if(current>1){current--;render();}});$('next').addEventListener('click',()=>{if(pdf&&current<pdf.numPages){current++;render();}});$('zoom').addEventListener('change',render);
try{
 const params=new URLSearchParams(location.search),path=pdfSourcePath(params.get('file'));if(!path)throw new Error('Invalid source');
 const name=params.get('name')||'PDF preview';$('filename').textContent=name;document.title=name+' · PDF preview';$('download').href=path+'?download=1';$('download').hidden=false;
 const response=await fetch(path+'?preview=1',{credentials:'same-origin',redirect:'error'});if(!response.ok)throw new Error('File unavailable');
 if(response.headers.get('content-type')?.split(';')[0].toLowerCase()!=='application/pdf')throw new Error('Not PDF');
 const data=new Uint8Array(await response.arrayBuffer());if(data.length>20*1024*1024)throw new Error('Too large');
 pdf=await pdfjs.getDocument({data,isEvalSupported:false,enableXfa:false,useWasm:false,disableFontFace:true,useSystemFonts:true}).promise;await render();
}catch(error){status.textContent='Preview unavailable. Your session may have expired or the PDF may require a password. Return to the portal to sign in, or download the original.';}
