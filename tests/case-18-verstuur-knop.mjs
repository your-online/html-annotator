/* case-18: de Verstuur-knop op een WhatsApp- en een mailkaart, in een echte browser.

   Wat hier moet kloppen en wat alleen een browser laat zien:
   1. de reviewer bewerkt de tekst inline, klikt Verstuur en "Ja, verstuur": het
      "Zeker?"-regeltje toont de ontvanger en het akkoord in state.json is de bewerkte tekst;
   2. typen na de klik trekt het akkoord in (UI én state.json), en de gate zegt dan ask;
   3. een pagina van een andere origin kan geen akkoord vastleggen;
   4. na verzending (dummy-kanaal: gate-hook -> logbestand -> nastap-hook) toont de
      kaart "Verstuurd HH:MM", ook na een reload;
   5. mail: balk en "Zeker?" tonen afzender, Aan, Cc en onderwerp; de wachter-aanroep
      komt door de gate; het akkoord overleeft een reload ondanks hoofdletters in het
      adres op de kaart; een kaart zonder afzender krijgt geen knop; opmaak geeft een waarschuwing.

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
// eigen configbestand met de account→server-koppeling voor het mail-vervolg
const CFG = join(ROOT, 'cfg');
mkdirSync(join(CFG, 'html-annotator'), { recursive: true });
writeFileSync(join(CFG, 'html-annotator', 'config.json'),
  JSON.stringify({ mail_servers: { 'owner@example.com': 'ms365-thuis' } }));
const env = { ...process.env, HTML_ANNOTATOR_PORT: String(PORT), HTML_ANNOTATOR_ROOT: ROOT,
  PYTHONPATH: SKILL, XDG_CONFIG_HOME: CFG, APPDATA: CFG };
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
const ORIGINEEL = 'Hi Sam, lukt morgen om 10:00?';
writeFileSync(bestand, `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<h2>Concept</h2>
<div class="la-draft" data-la-send="wa-sam" data-la-send-channel="whatsapp" data-la-send-to="${NR}">
  <div class="la-draft-hdr"><b>WhatsApp:</b> Sam</div>
  <div class="la-draft-txt">${ORIGINEEL}</div>
</div>
<div class="la-draft" data-la-send="wa-fout" data-la-send-channel="whatsapp" data-la-send-to="+31 6 00000001">
  <div class="la-draft-hdr"><b>WhatsApp:</b> fout nummer</div>
  <div class="la-draft-txt">Andere kaart</div>
</div>
<div class="la-draft" data-la-send="m-alex" data-la-send-channel="mail" data-la-send-account="owner@example.com"
  data-la-send-to="Alex@Example.com" data-la-send-cc="sam@example.com" data-la-send-subject="Planning vrijdag">
  <div class="la-draft-hdr"><b>Mail</b> Aan: Alex · Cc: Sam · Onderwerp: Planning vrijdag</div>
  <div class="la-draft-txt">Hi Alex, de planning staat vrijdag klaar. Groet, Sam</div>
</div>
<div class="la-draft" data-la-send="m-vet" data-la-send-channel="mail" data-la-send-account="owner@example.com"
  data-la-send-to="alex@example.com" data-la-send-subject="Vet">
  <div class="la-draft-hdr"><b>Mail</b> met opmaak</div>
  <div class="la-draft-txt">Dit is <b>belangrijk</b>.</div>
</div>
<div class="la-draft" data-la-send="m-geen" data-la-send-channel="mail" data-la-send-to="alex@example.com">
  <div class="la-draft-hdr"><b>Mail</b> zonder afzender</div>
  <div class="la-draft-txt">Zonder account</div>
</div>
${readFileSync(join(SKILL, 'references', 'send-snippet.html'), 'utf8')}
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-18: ${tekst}`); if (!ok) falen++; };
const entry = (k = 'wa-sam') => { try { return JSON.parse(readFileSync(statePad, 'utf8')).components.send[k] || {}; } catch { return {}; } };
const py = (script, args, input) => {
  try { return execFileSync('python3', [join(SKILL, 'bin', script), ...args], { env, input, encoding: 'utf8' }); }
  catch (e) { return e.stdout || ''; }
};
const gate = (to, text) => {
  const o = py('verstuur-gate-hook.py', [], JSON.stringify({ tool_name: 'mcp__whatsapp__send_message',
    tool_input: { recipient: to, message: text } }));
  return o.trim() ? JSON.parse(o).hookSpecificOutput.permissionDecision : '';
};
const kaart = '.la-draft[data-la-send="wa-sam"]';
const knopTekst = (sel = kaart) => page.$eval(`${sel} .la-send-btn`, (b) => b.textContent.trim());

// Verstuur + "Ja, verstuur" in het inline "Zeker?"-regeltje; geeft de tekst van dat regeltje.
const verstuur = async (sel = kaart) => {
  await page.click(`${sel} .la-send-btn`);
  await sleep(200);
  const zekerTekst = await page.$eval(`${sel} .la-send-zeker span`, (e) => e.textContent);
  await page.click(`${sel} .la-send-ja`);
  await sleep(800);
  return zekerTekst;
};

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
  const zekerTekst = await verstuur();
  const BEWERKT = ORIGINEEL + ' Of 11:00?';
  zeg(dialogen.length === 0 && zekerTekst.startsWith('Zeker?') && zekerTekst.includes(NR),
    `"Zeker?" toont de recipient, geen browserdialoog (${JSON.stringify(zekerTekst)})`);
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
        body: JSON.stringify({ page: url, key: 'wa-sam', channel: 'whatsapp', to: NR, text: 'vervalst' }) });
      return r.status;
    } catch (x) { return 'fetch-fout'; }
  }, { PORT, url, NR });
  await p2.close(); vreemd.close();
  e = entry();
  zeg(e.status === 'revoked' && e.text !== 'vervalst',
    `akkoord vanaf andere origin geweigerd (http ${poging}, status blijft ${e.status})`);
  zeg(gate(NR, 'vervalst') === 'ask', 'gate op de vervalste tekst: ask');

  // 4. opnieuw klikken, dummy-verzending, kaart toont "Verstuurd HH:MM"
  await verstuur();
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

  // 5. mail
  const mk = '.la-draft[data-la-send="m-alex"]';
  await page.waitForSelector(`${mk} .la-draft-txt.la-bewerkbaar`, { timeout: 5000 });
  const doel = await page.$eval(`${mk} .la-send-doel`, (e) => e.textContent);
  zeg(doel === 'mail · van owner@example.com → Alex@Example.com · cc sam@example.com · "Planning vrijdag"',
    `mail-balk toont afzender, Aan, Cc, onderwerp (${doel})`);
  zeg(await page.$eval('.la-draft[data-la-send="m-geen"] .la-send-btn', (b) => b.disabled)
    && /afzenderaccount/.test(await page.$eval('.la-draft[data-la-send="m-geen"] .la-send-status', (s) => s.textContent)),
    'mailkaart zonder afzenderaccount: knop uit met uitleg');
  const zm = await verstuur(mk);
  zeg(zm.includes('van owner@example.com') && zm.includes('cc sam@example.com'), `"Zeker?" bij mail toont afzender en Cc (${zm})`);
  let m = entry('m-alex');
  zeg(m.status === 'approved' && m.to === 'alex@example.com' && m.account === 'owner@example.com'
    && m.cc === 'sam@example.com' && m.subject === 'Planning vrijdag',
    `mail-akkoord met canonieke adressen (${m.status}, ${m.to}, ${m.cc})`);
  const aanroep = JSON.parse(execFileSync('python3', ['-c',
    'import json,sys; from html_annotator import verstuur; print(json.dumps(verstuur.vervolg(json.load(sys.stdin))))'],
    { env, cwd: SKILL, input: JSON.stringify(m), encoding: 'utf8' }));
  const mg = py('verstuur-gate-hook.py', [], JSON.stringify({ tool_name: aanroep.tool, tool_input: aanroep.arguments }));
  zeg(aanroep.tool === 'mcp__ms365-thuis__send-mail' && JSON.parse(mg).hookSpecificOutput.permissionDecision === 'allow',
    `vervolg-aanroep van de wachter komt door de gate (${aanroep.tool})`);
  await page.reload({ waitUntil: 'load' });
  await page.waitForSelector(`${mk} .la-send-btn`, { timeout: 5000 });
  await sleep(800);
  zeg(entry('m-alex').status === 'approved' && await knopTekst(mk) === 'Trek akkoord in',
    `mail-akkoord overleeft reload ondanks hoofdletters op de kaart (${entry('m-alex').status})`);
  await verstuur('.la-draft[data-la-send="m-vet"]');
  zeg(entry('m-vet').status === 'approved'
    && /opmaak/.test(await page.$eval('.la-draft[data-la-send="m-vet"] .la-send-status', (s) => s.textContent)),
    'mailkaart met vet: vastgelegd met waarschuwing dat opmaak niet meegaat');
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
