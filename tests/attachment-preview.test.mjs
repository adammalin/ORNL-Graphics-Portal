import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pdfPreviewUrl,pdfPreviewLink} from '../web/assets/intake/attachment-preview.js';
const route='/api/projects/FAKE-DEMO-1/attachments/900';
test('PDF preview has an explicit native route and safe new-tab attributes',()=>{const html=pdfPreviewLink('Application/PDF; charset=binary',route,'Reference.pdf');assert.equal(pdfPreviewUrl('application/pdf',route),'/assets/intake/pdf-preview.html?file='+encodeURIComponent(route));assert.match(html,/target="_blank"/);assert.match(html,/rel="noopener noreferrer"/);assert.match(html,/in a new tab/);assert.doesNotMatch(html,/download/);});
test('non-PDF attachments retain their existing preview path',()=>{for(const type of ['text/html','image/png','text/plain','application/octet-stream'])assert.equal(pdfPreviewLink(type,route,'sample.pdf'),'');});
test('external, script and ambiguous download URLs cannot become preview links',()=>{for(const url of ['javascript:alert(1)','https://upstream.example/signed','//other.example/a','/api/projects/G_1/attachments/1?download=1','data:application/pdf;base64,AAAA','/auth/smartsheet/logout'])assert.equal(pdfPreviewUrl('application/pdf',url),null);});
test('source names are escaped in accessible preview labels',()=>{const html=pdfPreviewLink('application/pdf',route,'<img onerror="bad">.pdf');assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));assert.ok(html.includes('&quot;'));});
test('same-tab session file blobs remain browser-viewable',()=>{assert.equal(pdfPreviewUrl('application/pdf','blob:https://portal.example/123'),'blob:https://portal.example/123');});

import {pdfSourcePath} from '../web/assets/intake/pdf-source.js';
test('viewer accepts only exact authenticated attachment paths',()=>{assert.equal(pdfSourcePath(route),route);for(const path of [null,'https://evil.example/file.pdf','//evil.example','/auth/smartsheet/logout',route+'?download=1','/api/projects/../attachments/1','/api/projects/G%2F1/attachments/1'])assert.equal(pdfSourcePath(path),null);});
