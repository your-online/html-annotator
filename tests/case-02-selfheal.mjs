/* AC-1: een pagina die al open staat terwijl de bridge omlaag is, herstelt zichzelf
   zodra de bridge omhoog komt — zonder reload — en slaat daarna echt naar schijf op.
   Dat is de "na-zwengel" die de reviewer nu handmatig geeft.

   Draait in de systeem-Chrome (channel: chrome) en niet in een gedownloade Chromium:
   dat staat dichter bij de Electron-runtime van Claude Desktop. Het blijft een
   benadering — zie criteria.md, "Wat de suite niet toetst".

   Twee origins, omdat het gedrag ervan afhangt:
     file  — pagina van schijf, zoals de reviewer hem los opent. Moet werken.
     data  — data:-snapshot, de vorm die de preview-pane volgens SKILL.md gebruikt.
             Kan principieel niet werken: Chrome weigert loopback vanuit een opaque
             origin met "the resource is in more-private address space `loopback`"
             (Private Network Access). Deze case is dus een verwachte mislukking, maar
             wel een die zijn reden moet aantonen: hij gaat rood als de blokkade een
             andere oorzaak heeft, en óók als hij ineens wél lukt — dan is de aanname
             onder AC-4 achterhaald en moet die herijkt worden.

   Bewijs komt uit een ander systeem dan de pagina: de annotatie wordt op schijf
   teruggelezen via het jsonPath dat de bridge zelf teruggaf. */

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync, existsSync } from 'node:fs';
import { tmpdir, homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL = process.env.HTML_ANNOTATOR_SKILL_DIR || process.env.LUC_ANNOTATOR_SKILL_DIR
  || join(fileURLToPath(new URL('..', import.meta.url)));
const PORT = process.env.HTML_ANNOTATOR_PORT || process.env.LUC_ANNOTATOR_PORT || '8791';
const PILL_TIMEOUT_MS = 10_000;
const ORIGINS = (process.env.CASE02_ORIGINS || 'file,data').split(',');
const VERBORGEN = process.env.CASE02_VERBORGEN === '1';

const sh = (cmd, args) => execFileSync(cmd, args, { encoding: 'utf8' }).trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function bridgePid() {
  try {
    return sh('lsof', ['-tnP', `-iTCP:${PORT}`, '-sTCP:LISTEN']).split('\n')[0] || '';
  } catch { return ''; }
}
async function bridgeDown() {
  const pid = bridgePid();
  if (pid) { try { sh('kill', [pid]); } catch {} }
  for (let i = 0; i < 30; i++) {
    if (!bridgePid()) return true;
    await sleep(200);
  }
  return false;
}
function bridgeUp() {
  try { execFileSync('python3', ['-m', 'html_annotator', 'ensure'], { cwd: SKILL, stdio: 'ignore' }); } catch {}
  return !!bridgePid();
}

/* Mutaties over de fix zelf. Zonder dit weet je niet wélk deel van het zelfherstel het
   werk doet: de timer, of de focus/visibility-listeners. Dat verschil is niet
   academisch — een sideview-paneel waar de reviewer niet in klikt krijgt nooit een focus-event,
   dus als de listeners het doen werkt de fix juist daar niet.

   CASE02_MUTATIE=geen-interval | geen-listeners | geen-poller
   Elke mutatie draagt zijn eigen verwachting, want die is niet uniform: zonder de
   listeners hóórt het herstel te blijven werken (dan is de timer de dragende helft),
   zonder de timer niet. */
const INTERVAL_UIT = [['}, 3000);', '}, 3000000);']];
const LISTENERS_UIT = [
  ['addEventListener("visibilitychange", function () {', 'addEventListener("nooit-vis", function () {'],
  ['addEventListener("focus", function () {', 'addEventListener("nooit-focus", function () {'],
];
const MUTATIES = {
  // De timer eruit: herstel moet uitblijven. Slaagt het alsnog, dan deden de
  // focus-listeners het werk — en die vuren nooit in een sideview-paneel waar de reviewer
  // niet in klikt, dus dan lost de fix zijn eigen use-case niet op.
  'geen-interval': { paren: INTERVAL_UIT, herstelVerwacht: false },
  // De listeners eruit: herstel moet blijven werken, op de timer alleen.
  //
  // PAS OP bij het lezen van dit groene resultaat: het betekent NIET dat de listeners
  // overbodig zijn. Chrome throttelt setInterval in een verborgen tab naar ongeveer
  // eens per minuut, en de timer in het snippet slaat een verborgen pagina bewust
  // over. Juist dan is visibilitychange wat de pagina meteen bijwerkt zodra de reviewer
  // terugkijkt. Deze case draait alleen met een zichtbare pagina en is dus blind voor
  // het geval waarin de listeners hun bestaan verdienen. Verwijder ze niet op grond
  // van deze groene run; bouw eerst een variant die de pagina echt verbergt.
  'geen-listeners': { paren: LISTENERS_UIT, herstelVerwacht: true },
  // Alles eruit: dit is de staat van vóór de fix, en moet rood zijn. Anders test de
  // assertie niet wat hij beweert te testen.
  'geen-poller': { paren: [...INTERVAL_UIT, ...LISTENERS_UIT], herstelVerwacht: false },
};

/* Wat de verborgen-variant NIET doet: de twee mechanismen van elkaar scheiden. Zodra de
   pagina weer zichtbaar is mag de timer ook weer vuren, dus herstel binnen het
   assertievenster kan van beide komen — gemeten in ronde 8: met de listeners eruit
   herstelde de pagina alsnog. De variant bewijst dus dát een verborgen paneel bijkomt
   nadat de reviewer erop terugkijkt, niet welke regel dat deed. Wil je die scheiding echt, dan
   moet de timer-periode omhoog tijdens deze variant; dat is bewust niet gebouwd omdat
   de gebruikersvraag "komt het paneel bij" is, niet "welke listener deed het".
   De mutatie 'geen-poller' dekt af dat het blok als geheel dragend is, ook hier. */

const MUTATIE = process.env.CASE02_MUTATIE || '';
let snippet = readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8');
if (MUTATIE) {
  const m = MUTATIES[MUTATIE];
  if (!m) { console.log(`  FAIL  onbekende mutatie "${MUTATIE}"`); process.exit(2); }
  for (const [van, naar] of m.paren) {
    if (!snippet.includes(van)) {
      // Een mutatie die niet aanslaat test niets, en zou als "check betrapt niets" lezen.
      console.log(`  FAIL  mutatie "${MUTATIE}" kon niet worden toegepast: "${van}" niet gevonden`);
      process.exit(2);
    }
    snippet = snippet.split(van).join(naar);
  }
  console.log(`  (mutatie actief: ${MUTATIE} — herstel ${MUTATIES[MUTATIE].herstelVerwacht ? 'moet blijven werken' : 'hoort uit te blijven'})`);
}

const slug = `zz-test-selfheal-${Date.now()}`;
const pagina = `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<h1>${slug}</h1><p id="doel">Dit is de testtekst waarop geannoteerd wordt.</p>
${snippet}`;

const werk = mkdtempSync(join(tmpdir(), 'annotator-case02-'));
const bestand = join(werk, `${slug}.html`);
writeFileSync(bestand, pagina);

const urlVoor = {
  file: () => 'file://' + bestand,
  data: () => 'data:text/html;charset=utf-8,' + encodeURIComponent(pagina),
};
// Origins waar de bridge principieel onbereikbaar is, met het patroon dat dat moet
// bewijzen. Zie de kop van dit bestand.
const GEBLOKKEERD = { data: /more-private address space|Private Network|CORS policy/i };

let falen = 0;
const browser = await chromium.launch({ channel: 'chrome', headless: true });

for (const origin of ORIGINS) {
  const label = `case-02[${origin}${VERBORGEN ? ',verborgen' : ''}${MUTATIE ? ',' + MUTATIE : ''}]`;
  if (!urlVoor[origin]) { console.log(`  FAIL  ${label}: onbekende origin`); falen++; continue; }

  if (!(await bridgeDown())) {
    console.log(`  FAIL  ${label}: bridge niet omlaag te krijgen; test zegt niets`);
    falen++; continue;
  }

  const page = await browser.newPage();
  if (VERBORGEN) {
    await page.addInitScript(() => {
      window.__verborgen = true;
      Object.defineProperty(document, 'hidden',
        { configurable: true, get: () => window.__verborgen === true });
      Object.defineProperty(document, 'visibilityState',
        { configurable: true, get: () => (window.__verborgen ? 'hidden' : 'visible') });
    });
  }
  const consoleFouten = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleFouten.push(m.text()); });

  await page.goto(urlVoor[origin](), { waitUntil: 'load' });
  await page.waitForSelector('#la-status', { timeout: 5000 });

  // 1. with the bridge down the pill should say "bridge off"
  let zagOff = true;
  await page.waitForFunction(
    () => /bridge off/.test(document.getElementById('la-status')?.textContent || ''),
    null, { timeout: 5000 },
  ).catch(() => { zagOff = false; });
  const pilVoor = await page.textContent('#la-status');
  if (!GEBLOKKEERD[origin] && (!zagOff || !/bridge off/.test(pilVoor || ''))) {
    console.log(`  FAIL  ${label}: pil toonde geen bridge-off vóór herstel ("${pilVoor}")`);
    falen++; await page.close(); continue;
  }

  /* 1b. Verborgen-paneel-variant (CASE02_VERBORGEN=1). Dit staat dichter bij de
     werkelijkheid van de reviewer dan een pagina op de voorgrond: het sideview-paneel staat er terwijl
     hij in de chat typt. De timer slaat een verborgen pagina bewust over, dus dan is
     `visibilitychange` het enige dat de pagina bijwerkt zodra hij terugkijkt. Zonder
     deze variant heeft die listener geen enkele assertie onder zich.

     Let op wat dit wél en niet is: de verborgen staat wordt geëmuleerd door
     document.hidden te overschrijven (zie de init-script hierboven), omdat noch headless
     noch headed Chrome via bringToFront een echte hidden-page oplevert. Het toetst dus
     onze eigen branch-logica — slaat de timer een verborgen pagina over, en werkt de
     listener bij terugkomst — en niet Chrome's throttling van timers in echte
     achtergrondtabs. Dat laatste blijft ongetoetst. */

  // 2. bridge komt omhoog terwijl de pagina open blijft staan
  const opgestart = bridgeUp();
  if (!opgestart) {
    console.log(`  FAIL  ${label}: ensure kreeg de bridge niet omhoog`);
    falen++; await page.close(); continue;
  }

  /* 2b. Verborgen: de pagina hóórt nu níet te herstellen. Doet hij dat wel, dan werkt
     de timer door op een onzichtbare pagina en meet de rest van deze variant niets. */
  if (VERBORGEN) {
    if (!(await page.evaluate(() => document.hidden))) {
      console.log(`  FAIL  ${label}: verbergen sloeg niet aan (document.hidden bleef false) — variant zegt niets`);
      await browser.close();
      process.exit(2);
    }
    await sleep(6000);
    const tussenpil = await page.textContent('#la-status');
    if (/\d+ saved/.test(tussenpil || '')) {
      console.log(`  FAIL  ${label}: herstelde al terwijl de pagina verborgen was ("${tussenpil}") — deze variant toetst de listener dan niet`);
      falen++;
      await page.close();
      continue;
    }
    // en nu kijkt de reviewer weer naar het paneel
    await page.evaluate(() => {
      window.__verborgen = false;
      document.dispatchEvent(new Event('visibilitychange'));
    });
  }

  // 3. de pil moet vanzelf omslaan — geen reload, geen klik
  let hersteld = true;
  await page.waitForFunction(
    () => /\d+ saved/.test(document.getElementById('la-status')?.textContent || ''),
    null, { timeout: VERBORGEN ? 3000 : PILL_TIMEOUT_MS },
  ).catch(() => { hersteld = false; });
  const pilNa = await page.textContent('#la-status');

  // 4. en dan het echte bewijs: landt een annotatie op schijf?
  const merk = `case02-${origin}-${Date.now()}`;
  const opslag = await page.evaluate(async (comment) => {
    try {
      await window.LucAnnotator.add({ type: 'text', selectedText: 'testtekst', comment });
      return { ok: true, jsonPath: window.LucAnnotator.bridge().jsonPath };
    } catch (e) { return { ok: false, error: String(e && e.message || e) }; }
  }, merk);

  let opSchijf = false;
  if (opslag.ok && opslag.jsonPath) {
    const pad = opslag.jsonPath.replace(/^~/, homedir());
    opSchijf = existsSync(pad) && readFileSync(pad, 'utf8').includes(merk);
    opslag.pad = pad;
  }

  const patroon = GEBLOKKEERD[origin];
  if (patroon) {
    // Verwachte mislukking: hij moet mislukken, én om de gedocumenteerde reden.
    if (hersteld || opSchijf) {
      console.log(`  FAIL  ${label}: bereikte de bridge tóch — de aanname onder AC-4 is achterhaald, herijk criteria.md`);
      falen++;
    } else if (consoleFouten.some((t) => patroon.test(t))) {
      console.log(`  PASS  ${label}: geblokkeerd om de verwachte reden (Private Network Access), zoals gedocumenteerd`);
    } else {
      console.log(`  FAIL  ${label}: geblokkeerd, maar niet om de verwachte reden — de oorzaak is veranderd`);
      falen++;
    }
  } else if (MUTATIE) {
    const verwacht = MUTATIES[MUTATIE].herstelVerwacht;
    if (hersteld === verwacht) {
      console.log(`  PASS  ${label}: mutatie "${MUTATIE}" gedroeg zich zoals voorspeld (herstel: ${hersteld})`);
    } else if (verwacht) {
      console.log(`  FAIL  ${label}: herstel viel weg door "${MUTATIE}" — dat deel is dus wél dragend, in tegenstelling tot wat de code beweert`);
      falen++;
    } else {
      console.log(`  FAIL  ${label}: herstelde ondanks "${MUTATIE}" — een ander mechanisme doet het werk dan bedoeld`);
      falen++;
    }
  } else {
    if (hersteld) {
      console.log(`  PASS  ${label}: pil herstelde zonder reload ("${pilVoor}" -> "${pilNa}")`);
    } else {
      console.log(`  FAIL  ${label}: pil bleef "${pilNa}" na ${PILL_TIMEOUT_MS / 1000}s met draaiende bridge`);
      falen++;
    }
    if (opSchijf) {
      console.log(`  PASS  ${label}: annotatie teruggelezen uit ${opslag.pad}`);
    } else {
      console.log(`  FAIL  ${label}: annotatie niet op schijf (${opslag.error || opslag.pad || 'geen jsonPath'})`);
      falen++;
    }
  }

  if (consoleFouten.length) {
    console.log(`        console: ${consoleFouten.slice(0, 3).join(' | ').slice(0, 300)}`);
  }
  await page.close();
}

await browser.close();
process.exit(falen ? 1 : 0);
