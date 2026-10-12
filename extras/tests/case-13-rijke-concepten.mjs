/* AC-13: het conceptbericht is rich text — opsommingen, vet en links staan er zoals de
   ontvanger ze straks in de mail ziet — zonder dat de tracked changes eronder verdwijnen.

   Waarom een eigen case naast 05 en 06: die twee bewaken de tekstdiff op een platte
   kaart. Hier gaat het om de twee dingen die met opmaak nieuw zijn en stuk kunnen:
   (1) blijft een tekstwijziging in een opgemaakte kaart een gewoon hunk met een
       platte-tekstanker, plaatsbaar met pas-hunk-toe.py en terug na een reload;
   (2) komt een opmaakwijziging (regel wordt bullet, woord wordt vet) als eigen blok
       terug in plaats van als woordruis in de tekstdiff.
   De opgeleverde HTML moet bovendien mail-veilig zijn: alleen tags die een mailclient
   zonder eigen interpretatie rendert.

   Draait in systeem-Chrome via de bridge (/p/), net als case-05. */

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL = process.env.LUC_ANNOTATOR_SKILL_DIR
  || join(fileURLToPath(new URL('../..', import.meta.url)));
const PORT = process.env.LUC_ANNOTATOR_PORT || '8791';
const sh = (c, a) => { try { return execFileSync(c, a, { encoding: 'utf8' }).trim(); } catch (e) { return (e.stdout || '') + (e.stderr || ''); } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const slug = `zz-test-rijk-${Date.now()}`;
const bestand = join(homedir(), 'Desktop', `${slug}.html`);
/* Een kaart zoals een agent hem voortaan schrijft: alinea's, een opsomming, vet en een
   link. Geen pre-wrap-tekst meer. */
const pagina = `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<h2>Mail-concepten</h2>
<div class="la-draft">
  <div class="la-draft-hdr"><b>Aan:</b> Alex Jansen &nbsp;·&nbsp; <b>Onderwerp:</b> Security</div>
  <div class="la-draft-txt"><p>Hi Alex,</p><p>Korte recap van ons gesprek net:</p><ul><li>Alex: schiet het <b>issue</b> in bij <a href="https://example.org/pbi/1234">PBI 1234</a></li><li>Sam: stuurt de opzet door</li></ul><p>Groet,<br>Sam</p></div>
  <div class="la-draft-na">Nog niet verstuurd.</div>
</div>
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`;
writeFileSync(bestand, pagina);

const url = `http://127.0.0.1:${PORT}/p/Desktop/${slug}.html`;
let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-13: ${tekst}`); if (!ok) falen++; };

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
await page.goto(url, { waitUntil: 'load' });
await page.waitForSelector('.la-draft-txt.la-bewerkbaar', { timeout: 5000 });

// 1. de kaart rendert als mail, niet als tekst met streepjes
const vorm = await page.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  return {
    li: box.querySelectorAll('li').length,
    vet: box.querySelectorAll('b').length,
    link: box.querySelectorAll('a[href]').length,
    rijk: box.classList.contains('la-rijk'),
    prewrap: getComputedStyle(box).whiteSpace,
  };
});
zeg(vorm.li === 2 && vorm.vet === 1 && vorm.link === 1 && vorm.rijk && vorm.prewrap !== 'pre-wrap',
  `opsomming, vet en link gerenderd (li ${vorm.li}, b ${vorm.vet}, a ${vorm.link}, wit ${vorm.prewrap})`);

// 2. de projectie waarop gedift wordt is kale tekst — geen "- ", geen "**"
const proj = await page.evaluate(() => window.LucAnnotator.drafts()[0].origineel);
zeg(!/^\s*[-*]\s/m.test(proj) && !proj.includes('**') && proj.includes('Alex: schiet het issue in bij PBI 1234'),
  `projectie is kale tekst zonder opmaakmarkeringen (${JSON.stringify(proj.split('\n')[4] || '')})`);

// 3. een tekstwijziging in een opgemaakte kaart -> gewoon tekst-hunk met platte anker
await page.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  box.focus();
  const li = box.querySelectorAll('li')[1];
  li.textContent = 'Sam: stuurt de opzet vrijdag door';
  box.dispatchEvent(new Event('input', { bubbles: true }));
});
await page.evaluate(() => document.querySelector('.la-draft-txt').blur());
await sleep(1500);

const map_ = join(homedir(), 'Desktop', 'annotaties', slug, 'ronde-01');
const jsonPad = join(map_, 'annotations.json');
zeg(existsSync(jsonPad), `bewerking teruggelezen uit ${jsonPad}`);
let data = JSON.parse(readFileSync(jsonPad, 'utf8'));
let ann = (data.annotations || []).find((a) => a.type === 'edit');
const tekstHunks = (ann?.hunks || []).filter((h) => h.soort !== 'opmaak');
zeg(tekstHunks.length === 1 && tekstHunks[0].toegevoegd.includes('vrijdag'),
  `tekstwijziging is één tekst-hunk (${tekstHunks.length}, +"${(tekstHunks[0]?.toegevoegd || '').trim()}")`);
zeg(!!tekstHunks[0] && !/[<>]/.test(tekstHunks[0].voor + tekstHunks[0].na + tekstHunks[0].verwijderd),
  'het anker van een tekst-hunk is platte tekst, geen HTML');

// 4. de opgeslagen nieuwe versie is mail-veilige HTML
const tags = [...(ann?.nieuwHtml || '').matchAll(/<\/?([a-z0-9]+)/gi)].map((m) => m[1].toLowerCase());
const toegestaan = new Set(['p', 'ul', 'ol', 'li', 'b', 'i', 'a', 'br']);
const verboden = [...new Set(tags)].filter((t) => !toegestaan.has(t));
zeg(verboden.length === 0 && /<li>/.test(ann?.nieuwHtml || ''),
  `nieuwHtml gebruikt alleen mail-veilige tags (${[...new Set(tags)].join(',')})`);

// 5. tracked change zichtbaar in de opgemaakte weergave, met de lijst intact
const markup = await page.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  return { ins: box.querySelectorAll('ins').length, del: box.querySelectorAll('del').length,
    li: box.querySelectorAll('li').length, insInLi: box.querySelectorAll('li ins').length };
});
zeg(markup.ins > 0 && markup.li === 2 && markup.insInLi > 0,
  `wijziging staat als tracked change ín de opsomming (${markup.ins} ins, ${markup.li} li)`);

// 6. pas-hunk-toe.py plaatst het tekst-hunk gewoon op de HTML-bron
const uit = sh('python3', [join(SKILL, 'bin', 'pas-hunk-toe.py'), jsonPad, '--nr', String(ann.nr),
  '--hunks', String(tekstHunks[0].n)]);
const bron = readFileSync(bestand, 'utf8');
zeg(bron.includes('stuurt de opzet vrijdag door'),
  `tekst-hunk doorgevoerd in de HTML-bron door pas-hunk-toe.py`);
if (!bron.includes('stuurt de opzet vrijdag door')) console.log(uit);

// --- tweede kaart: opmaak als eigen kanaal --------------------------------
const slug2 = `zz-test-opmaak-${Date.now()}`;
const bestand2 = join(homedir(), 'Desktop', `${slug2}.html`);
const PLAT = `Hi Alex,

Twee dingen:

Alex: schiet het issue in
Sam: stuurt de opzet door

Groet,
Sam`;
writeFileSync(bestand2, `<!doctype html><meta charset="utf-8"><title>${slug2}</title>
<div class="la-draft">
  <div class="la-draft-hdr"><b>Aan:</b> Alex &nbsp;·&nbsp; <b>Onderwerp:</b> Twee dingen</div>
  <div class="la-draft-txt">${PLAT}</div>
</div>
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

const page2 = await browser.newPage();
await page2.goto(`http://127.0.0.1:${PORT}/p/Desktop/${slug2}.html`, { waitUntil: 'load' });
await page2.waitForSelector('.la-draft-txt.la-bewerkbaar', { timeout: 5000 });

// een platte kaart begint plat: pre-wrap en plaintext-only, precies als voorheen
const start2 = await page2.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  return { rijk: box.classList.contains('la-rijk'), ce: box.getAttribute('contenteditable') };
});
zeg(!start2.rijk && start2.ce === 'plaintext-only',
  `een platte kaart blijft plat tot de reviewer opmaak aanzet (${start2.ce})`);

// De reviewer selecteert de twee owner-regels en maakt er een echte opsomming van
await page2.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  box.focus();
  const t = box.firstChild;
  const start = box.textContent.indexOf('Alex: schiet');
  const eind = box.textContent.indexOf('door') + 4;
  const r = document.createRange();
  r.setStart(t, start); r.setEnd(t, eind);
  const s = getSelection(); s.removeAllRanges(); s.addRange(r);
});
await page2.click('.la-draft-bar button[title="Bulleted list"]');
await sleep(300);
await page2.evaluate(() => document.querySelector('.la-draft-txt').blur());
await sleep(1500);

const na = await page2.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  return { li: box.querySelectorAll('li').length, rijk: box.classList.contains('la-rijk'),
    d: window.LucAnnotator.drafts()[0] };
});
zeg(na.li === 2 && na.rijk, `twee regels werden een echte opsomming (${na.li} li)`);
zeg(na.d.nieuw === na.d.origineel,
  'de platte tekst is niet veranderd — opmaak lekt niet in de tekstdiff');

const map2 = join(homedir(), 'Desktop', 'annotaties', slug2, 'ronde-01');
const json2 = join(map2, 'annotations.json');
const data2 = JSON.parse(readFileSync(json2, 'utf8'));
const ann2 = (data2.annotations || []).find((a) => a.type === 'edit');
const opmaak = (ann2?.hunks || []).filter((h) => h.soort === 'opmaak');
const tekst2 = (ann2?.hunks || []).filter((h) => h.soort !== 'opmaak');
zeg(opmaak.length === 2 && tekst2.length === 0,
  `opmaakwijziging komt als eigen blok terug, zonder tekst-hunks (${opmaak.length} opmaak, ${tekst2.length} tekst)`);
zeg(opmaak.length > 0 && opmaak.every((h) => /opsomming/.test(h.omschrijving || '') && (h.blok || '').length > 0),
  `elk opmaakblok zegt wat er gebeurde en op welke regel ("${opmaak[0]?.omschrijving}")`);

// pas-hunk-toe.py mag hier niets stilletjes doen
const bron2voor = readFileSync(bestand2, 'utf8');
const uit2 = sh('python3', [join(SKILL, 'bin', 'pas-hunk-toe.py'), json2, '--nr', String(ann2.nr),
  '--hunks', String(opmaak[0].n)]);
zeg(readFileSync(bestand2, 'utf8') === bron2voor && /opmaak/i.test(uit2),
  'pas-hunk-toe.py laat een opmaakblok staan en zegt waarom');

// en de bewerking overleeft een reload, op zijn anker
await page2.reload({ waitUntil: 'load' });
await page2.waitForSelector('.la-draft-txt.la-bewerkbaar', { timeout: 5000 });
await sleep(1200);
const herstel = await page2.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  return { li: box.querySelectorAll('li').length,
    meld: box.parentNode.querySelector('.la-draft-meld').textContent };
});
zeg(herstel.li === 2 && /saved as annotation/.test(herstel.meld),
  `de opmaakbewerking staat er na een reload nog (${herstel.li} li, "${herstel.meld}")`);

// vet op één woord: opmaak, geen tekstwijziging
await page2.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  box.focus();
  const li = box.querySelectorAll('li')[0];
  const t = li.firstChild;
  const i = li.textContent.indexOf('issue');
  const r = document.createRange();
  r.setStart(t, i); r.setEnd(t, i + 5);
  const s = getSelection(); s.removeAllRanges(); s.addRange(r);
});
await page2.click('.la-draft-bar button[title="Bold (⌘B)"]');
await sleep(300);
await page2.evaluate(() => document.querySelector('.la-draft-txt').blur());
await sleep(1500);
const vetD = await page2.evaluate(() => window.LucAnnotator.drafts()[0]);
const data3 = JSON.parse(readFileSync(json2, 'utf8'));
const ann3 = (data3.annotations || []).find((a) => a.type === 'edit');
const vetHunk = (ann3?.hunks || []).filter((h) => h.soort === 'opmaak' && /vet/.test(h.omschrijving || ''));
zeg(vetD.nieuw === vetD.origineel && vetHunk.length === 1 && /issue/.test(vetHunk[0].omschrijving),
  `vet op één woord is een opmaakblok, geen tekstwijziging ("${vetHunk[0]?.omschrijving}")`);
zeg(/<b>issue<\/b>/.test(vetD.nieuwHtml || ''), 'het vet staat in de mail-HTML');

await browser.close();
for (const f of [bestand, bestand2]) { try { rmSync(f); } catch {} }
for (const d of [join(homedir(), 'Desktop', 'annotaties', slug), join(homedir(), 'Desktop', 'annotaties', slug2)]) {
  try { rmSync(d, { recursive: true, force: true }); } catch {}
}
process.exit(falen ? 1 : 0);
