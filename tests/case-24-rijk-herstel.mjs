/* B46: een rijke bewerking (opsomming, alinea's) overleeft een reload.

   Waarom dit bestaat: /save stuurt origineelHtml, nieuwHtml en rijk mee en /session
   geeft ze terug, maar de pagina gooide ze weg bij het overnemen van de bridge-lijst.
   Na een reload viel de kaart dan terug op de platte projectie en was de opmaak weg.

   Het bewijs: na de reload draagt de annotatie die de pagina van de bridge overnam die
   drie velden nog, en staat de opsomming weer in de kaart. */

import { chromium } from 'playwright-core';
import { readFileSync, writeFileSync, existsSync, rmSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const TESTDIR = join(homedir(), 'html-annotator-tests');
mkdirSync(TESTDIR, { recursive: true });
const ROOT = process.env.HTML_ANNOTATOR_ROOT || join(homedir(), 'annotations');
const SKILL = process.env.HTML_ANNOTATOR_SKILL_DIR || join(fileURLToPath(new URL('..', import.meta.url)));
const PORT = process.env.HTML_ANNOTATOR_PORT || '8791';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const slug = `zz-test-rijk-herstel-${Date.now()}`;
const bestand = join(TESTDIR, `${slug}.html`);
writeFileSync(bestand, `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<div class="la-draft">
  <div class="la-draft-hdr"><b>Aan:</b> Kim &nbsp;·&nbsp; <b>Onderwerp:</b> Planning</div>
  <div class="la-draft-txt"><p>Hoi Kim,</p><ul><li>eerste punt</li><li>tweede punt</li></ul><p>Groet,<br>Sam</p></div>
</div>
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-24: ${tekst}`); if (!ok) falen++; };

const editAnn = (page) => page.evaluate(() =>
  (window.HtmlAnnotator.anns() || []).filter((a) => a.type === 'edit')[0] || null);

let browser;
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const url = `http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`;
  const page = await browser.newPage();
  try { await page.goto(url, { waitUntil: 'load', timeout: 8000 }); }
  catch { console.log('  BLOKKED  case-24: bridge niet bereikbaar op poort ' + PORT); process.exit(2); }
  await page.waitForSelector('.la-draft-txt.la-bewerkbaar', { timeout: 5000 });
  await page.waitForFunction(() => window.HtmlAnnotator.bridge().ok, null, { timeout: 5000 });

  /* Rijke bewerking: een derde opsommingspunt erbij, de lijst blijft een lijst. */
  await page.click('.la-draft-txt');
  await page.evaluate(() => {
    const ul = document.querySelector('.la-draft-txt ul');
    const li = document.createElement('li'); li.textContent = 'derde punt'; ul.appendChild(li);
  });
  await page.evaluate(() => document.querySelector('.la-draft-txt').blur());
  await sleep(1500);

  const jsonPath = (await page.evaluate(() => window.HtmlAnnotator.bridge().jsonPath) || '')
    .replace(/^~/, homedir());
  let opSchijf = null;
  if (jsonPath && existsSync(jsonPath)) {
    opSchijf = (JSON.parse(readFileSync(jsonPath, 'utf8')).annotations || [])
      .filter((a) => a.type === 'edit')[0] || null;
  }
  zeg(!!(opSchijf && opSchijf.rijk && /derde punt/.test(opSchijf.nieuwHtml || '')),
    'voorwaarde: de bridge bewaarde de rijke bewerking (rijk + nieuwHtml)');
  await page.close();

  /* Reload: de pagina neemt de lijst van de bridge over via /session. */
  const page2 = await browser.newPage();
  await page2.goto(url, { waitUntil: 'load', timeout: 8000 });
  await page2.waitForFunction(() => window.HtmlAnnotator.bridge().ok
    && (window.HtmlAnnotator.anns() || []).some((a) => a.type === 'edit'), null, { timeout: 5000 })
    .catch(() => {});
  await sleep(500);
  const ann = await editAnn(page2);
  zeg(!!ann, 'na reload staat de bewerking in de lijst van de pagina');
  zeg(!!(ann && /<li>/.test(ann.origineelHtml || '')),
    `origineelHtml komt terug van de bridge (${JSON.stringify(ann && ann.origineelHtml || '').slice(0, 60)})`);
  zeg(!!(ann && /derde punt/.test(ann.nieuwHtml || '')),
    `nieuwHtml komt terug van de bridge (${JSON.stringify(ann && ann.nieuwHtml || '').slice(0, 60)})`);
  zeg(!!(ann && ann.rijk === true), `rijk komt terug van de bridge (${ann && ann.rijk})`);
  const lijst = await page2.evaluate(() =>
    document.querySelectorAll('.la-draft-txt ul li').length);
  zeg(lijst === 3, `de kaart toont de opsomming weer met drie punten (${lijst})`);
  await page2.close();
} finally {
  if (browser) await browser.close();
  rmSync(bestand, { force: true });
  rmSync(join(ROOT, slug), { recursive: true, force: true });
}
process.exit(falen ? 1 : 0);
