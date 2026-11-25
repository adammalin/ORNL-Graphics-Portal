import { readFile, readdir } from 'node:fs/promises';
import { join, extname } from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
const root=fileURLToPath(new URL('.',import.meta.url));
const walk=async p=>{const result=[];for(const d of await readdir(p,{withFileTypes:true})){if(['.git','.local','artifacts','__pycache__','node_modules'].includes(d.name))continue;const f=join(p,d.name);result.push(...d.isDirectory()?await walk(f):[f]);}return result;};
const files=await walk(root),text=[];
for(const f of files)if(['.js','.mjs','.html','.css','.svg','.md','.py','.yml','.json','.txt'].includes(extname(f)))text.push([f,await readFile(f,'utf8')]);
const tokens=await readFile(join(root,'web/ornl-design-tokens.css'),'utf8');
const palette=new Set([...tokens.matchAll(/#[0-9a-f]{6}\b/gi)].map(m=>m[0].toLowerCase()));
for(const [file,content] of text){
  assert(!/github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9_-]{25,}/.test(content),`Possible credential in ${file}`);
  if(file.includes('/web/')&&!file.includes('/assets/intake/pdfjs/'))for(const match of content.matchAll(/#[0-9a-f]{6}\b/gi))assert(palette.has(match[0].toLowerCase()),`Unapproved color ${match[0]} in ${file}`);
}
const publicConfig=await readFile(join(root,'web/runtime-config.js'),'utf8');
assert.match(publicConfig,/dataMode:\s*'demo'/);assert.match(publicConfig,/apiBase:\s*null/);
assert(!text.some(([file,s])=>file.includes('/web/')&&/api\.smartsheet\.com|Bearer\s|(?:Authorization|SMARTSHEET_API_TOKEN)\s*[:=]|[A-Z0-9._%+-]+@ornl\.gov/i.test(s)),'Private employee identities, credentials or direct Smartsheet API access in public web files');
const css=await readFile(join(root,'web/styles.css'),'utf8');
for(const match of css.matchAll(/border-radius\s*:\s*([^;}]+)/g))assert(['0','50%'].includes(match[1]),'Non-square UI container');
assert(!css.includes('Indivisible'),'Restricted font');
assert(await readFile(join(root,'web/assets/fonts/OFL-Mulish.txt'),'utf8'));
console.log(JSON.stringify({publicConfiguration:'demo-only',palette:'ORNL tokens',fonts:['Mulish','Aptos','Arial'],containerRadii:'zero; circular indicators only',secretScan:'passed',webFiles:text.filter(([f])=>f.includes('/web/')).length}));
