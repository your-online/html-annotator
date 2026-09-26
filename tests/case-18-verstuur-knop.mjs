/* case-18: de Verstuur-knop op een WhatsApp-kaart, in een echte browser.

   Wat hier moet kloppen en wat alleen een browser laat zien:
   1. de reviewer bewerkt de tekst inline en klikt Verstuur: de confirm toont de
      bewerkte tekst en het akkoord in state.json is die bewerkte tekst;
   2. typen na de klik trekt het akkoord in (UI én state.json), en de gate zegt dan ask;
   3. een pagina van een andere origin kan geen akkoord vastleggen;
   4. na verzending (dummy-kanaal: gate-hook -> logbestand -> nastap-hook) toont de
      kaart "Verstuurd HH:MM", ook na een reload.

   Eigen bridge op een vrije poort met een tijdelijke root; de live bridge op 8791
   wordt niet aangeraakt. Er wordt niets echt verstuurd. */

import { chromium } from 'playwright-core';
import { spawn, execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync, existsSync, mkdirSync, mkdtempSync } from 'node:fs';
import { createServer } from 'node:http';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL = fileURLToPath(new URL('..', import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const vrijePoort = () => new Promise((res) => {
  const s = createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
});

const PORT = await vrijePoort();
const ROOT = mkdtempSync(join(tmpdir(), 'ann-c18-'));
const env = { ...process.env, HTML_ANNOTATOR_PORT: String(PORT), HTML_ANNOTATOR_ROOT: ROOT,
  PYTHONPATH: SKILL };
delete env.LUC_ANNOTATOR_PORT; delete env.LUC_ANNOTATOR_ROOT;
const bridge = spawn('python3', ['-m', 'html_annotator', 'serve'], { cwd: SKILL, env, stdio: 'ignore' });
let omhoog = false;
for (let i = 0; i < 50 && !omhoog; i++) {
  try { omhoog = (await fetch(`http://127.0.0.1:${PORT}/ping`)).ok; } catch { await sleep(200); }
}
if (!omhoog) { console.log(`  BLOKKED case-18: bridge op ${PORT} kwam niet omhoog`); bridge.kill('SIGINT'); process.exit(2); }

const TESTDIR = join(homedir(), 'html-annotator-tests');
mkdirSync(TESTDIR, { recursive: true });
const slug = `zz-test-verstuur-${Date.now()}`;
const bestand = join(TESTDIR, `${slug}.html`);
const statePad = join(ROOT, slug, 'state.json');
const NR = '31600000001';
const ORIGINEEL = 'Hi Nard, lukt morgen om 10:00?';
writeFileSync(bestand, `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<h2>Concept</h2>
<div class="la-draft" data-la-send="wa-nard" data-la-send-channel="whatsapp" data-la-send-to="${NR}">
  <div class="la-draft-hdr"><b>WhatsApp:</b> Nard</div>
  <div class="la-draft-txt">${ORIGINEEL}</div>
</div>
<div class="la-draft" data-la-send="wa-fout" data-la-send-channel="whatsapp" data-la-send-to="+31 6 00000001">
  <div class="la-draft-hdr"><b>WhatsApp:</b> fout nummer</div>
  <div class="la-draft-txt">Andere kaart</div>
</div>
${readFileSync(join(SKILL, 'references', 'send-snippet.html'), 'utf8')}
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-18: ${tekst}`); if (!ok) falen++; };
const entry = () => { try { return JSON.parse(readFileSync(statePad, 'utf8')).components.send['wa-nard'] || {}; } catch { return {}; } };
const py = (script, args, input) => {
  try { return execFileSync('python3', [join(SKILL, 'bin', script), ...args], { env, input, encoding: 'utf8' }); }
  catch (e) { return e.stdout || ''; }
};
const gate = (to, text) => {
  const o = py('verstuur-gate-hook.py', [], JSON.stringify({ tool_name: 'mcp__whatsapp__send_message',
    tool_input: { recipient: to, message: text } }));
  return o.trim() ? JSON.parse(o).hookSpecificOutput.permissionDecision : '';
};
const kaart = '.la-draft[data-la-send="wa-nard"]';
const knopTekst = (sel = kaart) => page.$eval(`${sel} .la-send-btn`, (b) => b.textContent.trim());

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
const dialogen = [];
page.on('dialog', async (d) => { dialogen.push(d.message()); await d.accept(); });
const url = `http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`;
try {
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForSelector(`${kaart} .la-send-btn`, { timeout: 5000 });
  await page.waitForSelector(`${kaart} .la-draft-txt.la-bewerkbaar`, { timeout: 5000 });

  // 0. de balk toont de exacte recipient-waarde; een kaart met "+31 6 ..." krijgt geen knop
  zeg((await page.$eval(`${kaart} .la-send-doel`, (e) => e.textContent)) === `whatsapp → ${NR}`,
    'balk toont kanaal en exacte recipient-waarde');
  zeg(await page.$eval('.la-draft[data-la-send="wa-fout"] .la-send-btn', (b) => b.disabled),
    'kaart met ongeldige WhatsApp-recipient heeft een uitgeschakelde knop');

  // 1. inline bewerken, dan klikken: akkoord = bewerkte tekst
  await page.click(`${kaart} .la-draft-txt`);
  await page.keyboard.press('End');
  await page.keyboard.type(' Of 11:00?');
  await page.evaluate((s) => document.querySelector(s + ' .la-draft-txt').blur(), kaart);
  await sleep(400);
  await page.click(`${kaart} .la-send-btn`);
  await sleep(800);
  const BEWERKT = ORIGINEEL + ' Of 11:00?';
  zeg(dialogen.length === 1 && dialogen[0].includes(BEWERKT) && dialogen[0].includes(NR),
    `confirm toont bewerkte tekst en recipient (${JSON.stringify(dialogen[0] || '').slice(0, 90)})`);
  let e = entry();
  zeg(e.status === 'approved' && e.text === BEWERKT && e.to === NR,
    `akkoord in state.json is de bewerkte tekst (${e.status}, ${JSON.stringify(e.text)})`);
  zeg(gate(NR, BEWERKT) === 'allow', 'gate op de bewerkte tekst: allow');
  zeg(gate(NR, ORIGINEEL) === 'ask', 'gate op de oorspronkelijke tekst: ask');

  // 2. wijzigen na de klik trekt in
  await page.click(`${kaart} .la-draft-txt`);
  await page.keyboard.press('End');
  await page.keyboard.type('!');
  await sleep(600);
  e = entry();
  zeg(e.status === 'revoked', `typen na de klik: state.json revoked (${e.status})`);
  zeg(/ingetrokken/.test(await page.$eval(`${kaart} .la-send-status`, (s) => s.textContent)),
    'UI meldt "akkoord ingetrokken"');
  zeg(gate(NR, BEWERKT) === 'ask', 'gate op de eerder goedgekeurde tekst: ask');
  await page.evaluate((s) => document.querySelector(s + ' .la-draft-txt').blur(), kaart);
  await sleep(400);

  // 3. andere origin kan geen akkoord vastleggen
  const vreemdPoort = await vrijePoort();
  const vreemd = createServer((q, r) => { r.setHeader('Content-Type', 'text/html'); r.end('<p>vreemd</p>'); });
  await new Promise((r) => vreemd.listen(vreemdPoort, '127.0.0.1', r));
  const p2 = await browser.newPage();
  await p2.goto(`http://127.0.0.1:${vreemdPoort}/`);
  const poging = await p2.evaluate(async ({ PORT, url, NR }) => {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/send-approve`, { method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: JSON.stringify({ page: url, key: 'wa-nard', channel: 'whatsapp', to: NR, text: 'vervalst' }) });
      return r.status;
    } catch (x) { return 'fetch-fout'; }
  }, { PORT, url, NR });
  await p2.close(); vreemd.close();
  e = entry();
  zeg(e.status === 'revoked' && e.text !== 'vervalst',
    `akkoord vanaf andere origin geweigerd (http ${poging}, status blijft ${e.status})`);
  zeg(gate(NR, 'vervalst') === 'ask', 'gate op de vervalste tekst: ask');

  // 4. opnieuw klikken, dummy-verzending, kaart toont "Verstuurd HH:MM"
  await page.click(`${kaart} .la-send-btn`);
  await sleep(800);
  e = entry();
  const DEFINITIEF = BEWERKT + '!';
  zeg(e.status === 'approved' && e.text === DEFINITIEF, `nieuwe klik: nieuw akkoord (${JSON.stringify(e.text)})`);
  const tf = join(ROOT, 'tekst.txt'); writeFileSync(tf, e.text);
  const log = join(ROOT, 'outbox.jsonl');
  const uit = JSON.parse(py('dummy-verstuur.py', ['--to', NR, '--text-file', tf, '--log', log]) || '{}');
  zeg(uit.gate === 'allow' && uit.verstuurd === true, `dummy-kanaal: gate allow, verstuurd (${uit.gate})`);
  zeg(entry().status === 'sent', 'nastap zet status sent');
  let knop = '';
  for (let i = 0; i < 20 && !/^Verstuurd \d\d:\d\d$/.test(knop); i++) { await sleep(300); knop = await knopTekst(); }
  zeg(/^Verstuurd \d\d:\d\d$/.test(knop), `kaart toont zonder reload "${knop}"`);
  await page.reload({ waitUntil: 'load' });
  await page.waitForSelector(`${kaart} .la-send-btn`, { timeout: 5000 });
  await sleep(800);
  knop = await knopTekst();
  zeg(/^Verstuurd \d\d:\d\d$/.test(knop) && await page.$eval(`${kaart} .la-send-btn`, (b) => b.disabled),
    `na reload nog steeds "${knop}", knop uit`);
  const tweede = JSON.parse(py('dummy-verstuur.py', ['--to', NR, '--text-file', tf, '--log', log]) || '{}');
  zeg(tweede.gate === 'ask' && readFileSync(log, 'utf8').trim().split('\n').length === 1,
    'dubbel versturen: gate ask, outbox houdt één bericht');
} catch (x) {
  zeg(false, `onverwachte fout: ${x.message}`);
} finally {
  await browser.close();
  bridge.kill('SIGINT');  // alleen ons eigen kind
  rmSync(bestand, { force: true });
  rmSync(ROOT, { recursive: true, force: true });
}
console.log(falen ? `  case-18: ${falen} gefaald` : '  case-18: groen');
process.exit(falen ? 1 : 0);
