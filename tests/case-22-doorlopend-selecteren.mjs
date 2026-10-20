/* B43: doorlopend selecteren. Staat continuous_select aan (standaard), dan blijft de
   regio-modus na Save aan: één klik op de knop, daarna regio na regio. Staat hij uit
   (bridge levert continuousSelect:false via /session), dan gaat de modus na Save uit,
   zoals vóór deze toggle. */

import { chromium } from 'playwright-core';
import { readFileSync, writeFileSync, rmSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const TESTDIR = join(homedir(), 'html-annotator-tests');
mkdirSync(TESTDIR, { recursive: true });
const ROOT = process.env.HTML_ANNOTATOR_ROOT || join(homedir(), 'annotations');
const SKILL = process.env.HTML_ANNOTATOR_SKILL_DIR || join(fileURLToPath(new URL('..', import.meta.url)));
const PORT = process.env.HTML_ANNOTATOR_PORT || '8791';

const slug = `zz-test-doorlopend-${Date.now()}`;
const bestand = join(TESTDIR, `${slug}.html`);
writeFileSync(bestand, `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<body style="margin:0;font:16px sans-serif">
<div id="a" style="position:absolute;left:20px;top:20px;width:300px;height:60px;background:#eef">A</div>
<div id="b" style="position:absolute;left:20px;top:120px;width:300px;height:60px;background:#efe">B</div>
<div id="c" style="position:absolute;left:20px;top:220px;width:300px;height:60px;background:#fee">C</div>
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-22: ${tekst}`); if (!ok) falen++; };

async function regio(page, y, tekst) {
  await page.mouse.move(30, y); await page.mouse.down();
  await page.mouse.move(200, y + 40, { steps: 4 }); await page.mouse.up();
  await page.waitForSelector('#la-popup .la-save', { timeout: 3000 });
  await page.keyboard.type(tekst);
  await page.click('#la-popup .la-save');
  await page.waitForSelector('#la-popup', { state: 'detached', timeout: 3000 });
  await page.waitForTimeout(150);
}
const modusAan = (page) => page.evaluate(() => !!document.getElementById('la-overlay'));

let browser;
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const url = `http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`;

  /* aan (standaard): één klik, drie regio's */
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
  try { await page.goto(url, { waitUntil: 'load', timeout: 8000 }); }
  catch { console.log('  BLOKKED  case-22: bridge niet bereikbaar op poort ' + PORT); process.exit(2); }
  await page.waitForFunction(() => /saved/.test(document.getElementById('la-status').textContent), null, { timeout: 5000 });
  await page.click('#la-toggle');
  await regio(page, 30, 'een');
  zeg(await modusAan(page), 'aan: regio-modus blijft aan na de eerste Save');
  await regio(page, 130, 'twee');
  await regio(page, 230, 'drie');
  zeg(await modusAan(page), 'aan: regio-modus nog aan na drie Saves zonder knopklik');
  await page.waitForFunction(() => /^3 saved/.test(document.getElementById('la-status').textContent), null, { timeout: 5000 }).catch(() => {});
  const status = await page.textContent('#la-status');
  zeg(/^3 saved/.test(status), `aan: drie annotaties bewaard (${status})`);
  await page.click('#la-toggle');
  zeg(!(await modusAan(page)), 'aan: de knop zet de modus weer uit');
  await page.close();

  /* uit: bridge zegt continuousSelect:false → modus uit na Save */
  const page2 = await browser.newPage({ viewport: { width: 800, height: 600 } });
  await page2.route('**/session', async (route) => {
    const r = await route.fetch(); const j = await r.json();
    j.continuousSelect = false;
    await route.fulfill({ response: r, json: j });
  });
  await page2.goto(url, { waitUntil: 'load', timeout: 8000 });
  await page2.waitForFunction(() => /saved/.test(document.getElementById('la-status').textContent), null, { timeout: 5000 });
  await page2.click('#la-toggle');
  await regio(page2, 30, 'vier');
  zeg(!(await modusAan(page2)), 'uit: regio-modus gaat uit na Save (oude gedrag)');
} finally {
  if (browser) await browser.close();
  rmSync(bestand, { force: true });
  rmSync(join(ROOT, slug), { recursive: true, force: true });
}
process.exit(falen ? 1 : 0);
