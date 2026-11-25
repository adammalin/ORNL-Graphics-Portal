import {escapeHtml as e} from '../../domain.js';

export function pdfPreviewUrl(type,url) {
  if(String(type||'').split(';')[0].trim().toLowerCase()!=='application/pdf'||typeof url!=='string')return null;
  // Native attachment route preserves session/role checks. Never expose an upstream signed URL.
  if(/^\/api\/projects\/[^/?#]+\/attachments\/[A-Za-z0-9_-]+$/.test(url))return '/assets/intake/pdf-preview.html?file='+encodeURIComponent(url);
  if(/^blob:https?:\/\//.test(url))return url;
  return null;
}
export function pdfPreviewLink(type,url,name) {
  let target=pdfPreviewUrl(type,url);if(!target)return '';
  if(target.startsWith('/assets/'))target+='&name='+encodeURIComponent(name);
  return `<a href="${e(target)}" target="_blank" rel="noopener noreferrer" aria-label="${e('Preview '+name+' in a new tab')}">Preview ↗</a>`;
}
