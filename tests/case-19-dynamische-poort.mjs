/* case-19: de bridge op een andere poort dan 8791, end-to-end in een echte browser.

   Scenario (CRITERIA.md B12, B22, B32): de geconfigureerde poort is bezet door iets dat
   geen bridge is.
   1. ensure weigert (exit 1) en verwijst naar pick-port, in plaats van stil uit te wijken;
   2. pick-port kiest de volgende vrije poort en schrijft die in het configbestand;
   3. ensure, url en de /p/-pagina volgen die poort zonder HTML_ANNOTATOR_PORT;
   4. een annotatie en een checkbox (checklist-snippet) landen op schijf.

   Alles tijdelijk: configmap, statemap, annotatie-root. De poortreeks is een testreeks
   (HTML_ANNOTATOR_PORT_RANGE) met een eigen bezetter, zodat de live bridge op 8791
   nooit gestopt of bezet wordt. */

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync, mkdirSync, mkdtempSync, existsSync } from 'node:fs';
import { createServer } from 'node:net';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL = fileURLToPath(new URL('..', import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const luister = (poort) => new Promise((res) => {
  const s = createServer((c) => c.destroy());
  s.once('error', () => res(null));
  s.listen(poort, '127.0.0.1', () => res(s));
});
const sluit = (s) => new Promise((r) => (s ? s.close(() => r()) : r()));

// Twee aaneengesloten vrije poorten; de eerste bezetten we zelf. Bewust buiten de
// ephemeral-reeks (macOS/Windows 49152+, Linux 32768+): daar kan de bronpoort van een
// eigen ping-verbinding precies op p+1 landen en die poort tijdelijk bezet houden.
let p = 0;
let bezetter = null;
for (let i = 0; i < 50 && !bezetter; i++) {
  const kandidaat = 20000 + Math.floor(Math.random() * 10000);
  const eerste = await luister(kandidaat);
  if (!eerste) continue;
  await sluit(eerste);
  const tweede = await luister(kandidaat + 1);
  if (!tweede) continue;
  await sluit(tweede);
  bezetter = await luister(kandidaat);
  if (bezetter) p = kandidaat;
}
if (!bezetter) { console.log('  BLOKKED case-19: geen vrij poortblok gevonden'); process.exit(2); }

const TMP = mkdtempSync(join(tmpdir(), 'ann-c19-'));
const CFG = join(TMP, 'cfg'), STATE = join(TMP, 'state'), ROOT = join(TMP, 'annotations');
for (const d of [CFG, STATE, ROOT]) mkdirSync(d, { recursive: true });
const env = { ...process.env, XDG_CONFIG_HOME: CFG, APPDATA: CFG, XDG_STATE_HOME: STATE,
  LOCALAPPDATA: STATE, HTML_ANNOTATOR_ROOT: ROOT, PYTHONPATH: SKILL,
  HTML_ANNOTATOR_PORT_RANGE: `${p}-${p + 1}` };
for (const k of ['HTML_ANNOTATOR_PORT', 'LUC_ANNOTATOR_PORT', 'LUC_ANNOTATOR_ROOT',
  'HTML_ANNOTATOR_HOST', 'HTML_ANNOTATOR_PAGES_ROOT']) delete env[k];
const CONFIG = join(CFG, 'html-annotator', 'config.json');
mkdirSync(join(CFG, 'html-annotator'), { recursive: true });
writeFileSync(CONFIG, JSON.stringify({ port: p }));

const cli = (...args) => {
  try {
    return { rc: 0, uit: execFileSync('python3', ['-m', 'html_annotator', ...args],
      { cwd: SKILL, env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }) };
  } catch (e) { return { rc: e.status, uit: (e.stdout || '') + (e.stderr || '') }; }
};

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-19: ${tekst}`); if (!ok) falen++; };

const TESTDIR = join(homedir(), 'html-annotator-tests');
mkdirSync(TESTDIR, { recursive: true });
const slug = `zz-test-poort-${Date.now()}`;
const bestand = join(TESTDIR, `${slug}.html`);
writeFileSync(bestand, `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<h1>Poorttest</h1>
<p id="tekst">Deze zin krijgt een annotatie.</p>
<ul><li data-la-check="item-1"><span class="what">Eerste punt</span></li></ul>
${readFileSync(join(SKILL, 'references', 'checklist-snippet.html'), 'utf8')}
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

let browser = null;
try {
  // 1. Geconfigureerde poort bezet door een vreemde: ensure weigert.
  let r = cli('ensure', '--timeout', '1');
  zeg(r.rc === 1 && r.uit.includes('pick-port') && r.uit.includes(String(p)),
    `ensure op vreemd bezette poort ${p}: exit ${r.rc}, melding noemt pick-port`);

  // 2. pick-port kiest de volgende.
  r = cli('pick-port');
  const cfg = JSON.parse(readFileSync(CONFIG, 'utf8'));
  zeg(r.rc === 0 && cfg.port === p + 1, `pick-port schreef ${cfg.port} (verwacht ${p + 1}): ${r.uit.trim()}`);

  // 3. ensure, url --base en url volgen.
  r = cli('ensure');
  zeg(r.rc === 0 && r.uit.includes(`:${p + 1}`), `ensure start op ${p + 1}: ${r.uit.trim()}`);
  const base = cli('url', '--base').uit.trim();
  zeg(base === `http://127.0.0.1:${p + 1}`, `url --base = ${base}`);
  const url = cli('url', bestand).uit.trim();
  zeg(url === `http://127.0.0.1:${p + 1}/p/html-annotator-tests/${slug}.html`, `url = ${url}`);

  // 4. Browser: annotatie en checkbox landen op schijf.
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => window.HtmlAnnotator && window.HtmlAnnotator.bridge
    && window.HtmlAnnotator.bridge().ok, null, { timeout: 10000 });
  const origin = await page.evaluate(() => window.HtmlAnnotator._test.bridgeOrigin);
  zeg(origin === `http://127.0.0.1:${p + 1}`, `snippet praat met ${origin}`);

  const comment = `poorttest ${Date.now()}`;
  await page.evaluate((c) => window.HtmlAnnotator.add({ type: 'text',
    selectedText: 'Deze zin krijgt een annotatie.', comment: c }), comment);
  const json = join(ROOT, slug, 'ronde-01', 'annotations.json');
  let opgeslagen = false;
  for (let i = 0; i < 25 && !opgeslagen; i++) {
    opgeslagen = existsSync(json) && readFileSync(json, 'utf8').includes(comment);
    if (!opgeslagen) await sleep(200);
  }
  zeg(opgeslagen, `annotatie in ${json}`);

  await page.click('[data-la-check="item-1"] input.la-check');
  const statePad = join(ROOT, slug, 'state.json');
  let gevinkt = false;
  for (let i = 0; i < 25 && !gevinkt; i++) {
    try {
      gevinkt = JSON.parse(readFileSync(statePad, 'utf8')).components.checklist['item-1'].checked === true;
    } catch { /* nog niet geschreven */ }
    if (!gevinkt) await sleep(200);
  }
  zeg(gevinkt, `checkbox in ${statePad}`);
} catch (e) {
  zeg(false, `onverwachte fout: ${e.message}`);
} finally {
  if (browser) await browser.close();
  const s = cli('stop');
  zeg(s.rc === 0, `stop: ${s.uit.trim()}`);
  await sluit(bezetter);
  rmSync(bestand, { force: true });
  rmSync(TMP, { recursive: true, force: true });
}
process.exit(falen ? 1 : 0);
