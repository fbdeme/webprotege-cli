// Exploration harness: load the WebProtégé SPA and dump the live DOM surface
// (visible text, inputs, buttons, links, dialogs) so selectors are grounded in
// fact rather than guessed. Not part of the shipped CLI.
//
//   node test/explore.js [url] [--shot name]
import { chromium } from 'playwright';
import fs from 'node:fs';

const url = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : 'http://localhost:5000/';
const shotIdx = process.argv.indexOf('--shot');
const shot = shotIdx > -1 ? process.argv[shotIdx + 1] : 'explore';

const outDir = '/tmp/claude-1000/-home-user-workspace-2026/0fd572bd-2d17-4247-836a-093d88995066/scratchpad/wp-shots';
fs.mkdirSync(outDir, { recursive: true });

function dump(label, arr) {
  console.log(`\n=== ${label} (${arr.length}) ===`);
  for (const x of arr) console.log('  ' + x);
}

const b = await chromium.launch({ headless: true });
const ctx = await b.newContext();
const p = await ctx.newPage();
await p.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
await p.waitForTimeout(2500); // let GWT render

await p.screenshot({ path: `${outDir}/${shot}.png`, fullPage: true });
console.log('screenshot ->', `${outDir}/${shot}.png`);

const snap = await p.evaluate(() => {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const txt = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  const pick = (sel) => [...document.querySelectorAll(sel)].filter(vis);
  return {
    buttons: pick('button, [role=button], .gwt-Button, .btn').map(txt).filter(Boolean),
    links: pick('a').map((a) => `${txt(a)} :: ${a.getAttribute('href') || ''}`).filter((s) => s.replace(' :: ', '').trim()),
    inputs: pick('input, textarea, select').map((i) => `${i.tagName.toLowerCase()}[type=${i.type || ''}] name=${i.name || ''} ph=${i.placeholder || ''} aria=${i.getAttribute('aria-label') || ''}`),
    headings: pick('h1,h2,h3,.wp-dialog__title,[class*=Title],[class*=title]').map(txt).filter(Boolean).slice(0, 30),
    bodyText: document.body.innerText.replace(/\s+/g, ' ').slice(0, 600),
  };
});

dump('headings', snap.headings);
dump('buttons', snap.buttons);
dump('links', snap.links);
dump('inputs', snap.inputs);
console.log('\n=== bodyText ===\n' + snap.bodyText);

await b.close();
