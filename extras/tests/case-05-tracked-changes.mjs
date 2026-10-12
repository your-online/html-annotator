/* AC-5: de reviewer herschrijft de tekst van een conceptbericht rechtstreeks in de kaart, en dat
   verschil komt als bewerking op schijf te staan — met voor, na en de losse wijzigingen,
   zodat een agent niet hoeft te raden wat er moet veranderen.

   Waarom dit een eigen case is en niet een variant van case-02: hier gaat het niet om of
   de bridge bereikbaar is, maar of de diff klopt en of hij een reload overleeft. Het
   bewijs komt uit een ander systeem dan de pagina: annotations.json op schijf.

   Draait in systeem-Chrome via de bridge (/p/), want dat is de route waarlangs de reviewer de
   pagina echt opent — gemeten in AC-4. */

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL = process.env.LUC_ANNOTATOR_SKILL_DIR
  || join(fileURLToPath(new URL('../..', import.meta.url)));
const PORT = process.env.LUC_ANNOTATOR_PORT || '8791';
const sh = (c, a) => { try { return execFileSync(c, a, { encoding: 'utf8' }).trim(); } catch { return ''; } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const ORIGINEEL = `Hi Alex,

Ik wil even bijpraten over de security-afscherming.

Groet,
Sam`;

const slug = `zz-test-tracked-${Date.now()}`;
const bestand = join(homedir(), 'Desktop', `${slug}.html`);
const pagina = `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<h2>Mail-concepten</h2>
<div class="la-draft">
  <div class="la-draft-hdr"><b>Aan:</b> Alex Jansen &nbsp;·&nbsp; <b>Onderwerp:</b> Security</div>
  <div class="la-draft-txt">${ORIGINEEL}</div>
  <div class="la-draft-na">Nog niet verstuurd.</div>
</div>
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`;
writeFileSync(bestand, pagina);

const url = `http://127.0.0.1:${PORT}/p/Desktop/${slug}.html`;
let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-05: ${tekst}`); if (!ok) falen++; };

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
await page.goto(url, { waitUntil: 'load' });
await page.waitForSelector('.la-draft-txt.la-bewerkbaar', { timeout: 5000 });

// 1. De reviewer klikt in de tekst en herschrijft een zin — geen knop, direct typen
await page.click('.la-draft-txt');   // klikken in de tekst zet de cursor
const NIEUW = ORIGINEEL.replace('Ik wil even bijpraten over de security-afscherming.',
  'Kunnen we deze week de security-afscherming doornemen?');
await page.evaluate((t) => {
  const box = document.querySelector('.la-draft-txt');
  box.textContent = t;
}, NIEUW);
await page.evaluate(() => document.querySelector('.la-draft-txt').blur());  // eruit klikken
await sleep(1500);

// 1b. eruit klikken toont GEEN diff: de kaart blijft de kale herschreven tekst, met
// alleen een knop "Show changes" in de bar. De automatische doorhaling sprong in het
// gezicht van wie gewoon aan het herschrijven was.
const naBlur = await page.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  const knop = document.querySelector('.la-draft-diff');
  return { ins: box.querySelectorAll('ins').length, del: box.querySelectorAll('del').length,
           knop: !!knop && knop.style.display !== 'none', label: knop ? knop.textContent : '' };
});
zeg(naBlur.ins === 0 && naBlur.del === 0,
  `na eruit klikken geen automatische diff (${naBlur.ins} ins, ${naBlur.del} del)`);
zeg(naBlur.knop && /Show changes/.test(naBlur.label),
  `knop "Show changes" staat klaar (${JSON.stringify(naBlur.label)})`);

// 2. via de knop moet de markup ins én del tonen, niet alleen de nieuwe tekst
await page.click('.la-draft-diff');
await sleep(300);
const markup = await page.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  return { ins: box.querySelectorAll('ins').length, del: box.querySelectorAll('del').length };
});
zeg(markup.ins > 0 && markup.del > 0,
  `wijziging zichtbaar als tracked change (${markup.ins} ins, ${markup.del} del)`);

// 2b. een bewerking hoort géén badge te krijgen en niet in de weeslijst te belanden.
// Dit ging mis en was in de browser meteen zichtbaar ("1 annotatie waarschijnlijk
// verwerkt") terwijl de opslag gewoon klopte: de assertie op ins/del zag dat niet.
const rommel = await page.evaluate(() => ({
  badges: document.querySelectorAll('.la-badge').length,
  wees: !!document.getElementById('la-wees'),
}));
zeg(rommel.badges === 0 && !rommel.wees,
  `geen badge en geen weeslijst voor een bewerking (badges: ${rommel.badges}, wees: ${rommel.wees})`);

// 3. het bewijs: staat het op schijf, met voor, na en de diff?
const jsonPath = await page.evaluate(() => window.LucAnnotator.bridge().jsonPath);
const pad = (jsonPath || '').replace(/^~/, homedir());
let opSchijf = null;
if (pad && existsSync(pad)) {
  const data = JSON.parse(readFileSync(pad, 'utf8'));
  opSchijf = (data.annotations || []).filter((a) => a.type === 'edit')[0] || null;
}
zeg(!!opSchijf, `bewerking teruggelezen uit ${pad || '(geen pad)'}`);

if (opSchijf) {
  zeg(opSchijf.origineel === ORIGINEEL, 'originele tekst bewaard');
  zeg(opSchijf.nieuw === NIEUW, 'herschreven tekst bewaard');
  const verwijderd = (opSchijf.diff || []).filter((o) => o.op === '-').map((o) => o.t).join('');
  const toegevoegd = (opSchijf.diff || []).filter((o) => o.op === '+').map((o) => o.t).join('');
  zeg(/bijpraten/.test(verwijderd) && /doornemen/.test(toegevoegd),
    'de diff wijst het gewijzigde deel aan, niet de hele tekst');
  // Een diff die alles als vervangen markeert is technisch waar en praktisch nutteloos.
  // Niet toetsen op een percentage — bij het herschrijven van een hele zin verandert
  // terecht veel — maar op tekst die aantoonbaar níet is aangeraakt: aanhef en afsluiting.
  const gelijk = (opSchijf.diff || []).filter((o) => o.op === '=').map((o) => o.t).join('');
  zeg(/Hi Alex,/.test(gelijk) && /Groet,/.test(gelijk) && /Sam/.test(gelijk),
    'aanhef en afsluiting staan als onveranderd in de diff, niet als vervangen');
}

// 3b. Terugklikken terwijl de doorhaling zichtbaar is. Dit is het geval waar het
// misging: de doorgehaalde tekst verdwijnt, de regel loopt anders, en de cursor van de
// browser landt naast de plek waar de reviewer klikte. Het klikpunt moet op dezelfde regel
// liggen als de wijziging en erna: alleen daar verschuift de tekst echt. Een punt op een
// latere regel is ongevoelig — dat bleek toen de mutatie "omrekening uit" gewoon groen
// bleef met "Groet," als doel.
const punt = await page.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  const w = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const i = n.nodeValue.indexOf('security-afscherming');
    if (i >= 0) {
      const r = document.createRange();
      r.setStart(n, i); r.setEnd(n, i + 1);
      const b = r.getBoundingClientRect();
      return { x: b.left + 1, y: b.top + b.height / 2 };
    }
  }
  return null;
});
if (!punt) {
  zeg(false, 'kon "Groet," niet lokaliseren om op te klikken');
} else {
  await page.mouse.click(punt.x, punt.y);
  await page.keyboard.type('XX');
  const naKlik = await page.evaluate(() => document.querySelector('.la-draft-txt').textContent);
  zeg(/XXsecurity-afscherming/.test(naKlik),
    `cursor landt waar geklikt is, ook met opmaak in beeld (${JSON.stringify((naKlik.match(/.{0,8}XX.{0,10}/) || ['niet gevonden'])[0])})`);
  // opruimen: de XX weer weg, anders meet stap 4 iets anders dan bedoeld
  await page.evaluate(() => {
    const box = document.querySelector('.la-draft-txt');
    box.textContent = box.textContent.replace('XX', '');
    box.blur();
  });
  await sleep(1500);
}

// 4. overleeft het een reload? Anders is het werk van de reviewer weg na verversen.
await page.reload({ waitUntil: 'load' });
await sleep(2500);
await page.click('.la-draft-diff');
await sleep(300);
const naReload = await page.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  return { ins: box.querySelectorAll('ins').length, del: box.querySelectorAll('del').length,
           nr: (window.LucAnnotator.drafts()[0] || {}).nr };
});
zeg(naReload.ins > 0 && naReload.del > 0, 'de bewerking staat er na een reload nog');

await browser.close();
rmSync(bestand, { force: true });
rmSync(join(homedir(), 'Desktop', 'annotaties', slug), { recursive: true, force: true });
process.exit(falen ? 1 : 0);
