/* AC-6: meerdere wijzigingen in één conceptbericht zijn los van elkaar te behandelen.

   Waarom dit bestaat: vóór hunks was één bewerking één brok. Maakte de reviewer drie wijzigingen
   in dezelfde mail, dan moest een agent ze alledrie overnemen of geen. Dat is precies wat
   een unified diff wél kan en wij niet.

   Wat hier getoetst wordt is de eigenschap die dat mogelijk maakt: elke aaneengesloten
   wijziging krijgt een eigen blok met de tekst eromheen als anker, blokken zijn apart toe
   te passen en apart af te vinken, en een blok is nog plaatsbaar nadat de pagina elders
   veranderd is — want daar zou een positie- of regelnummer op stuklopen.

   Het bewijs komt niet uit de pagina maar van schijf: annotations.json en het
   daadwerkelijk gewijzigde HTML-bestand. */

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, existsSync, rmSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const TESTDIR = join(homedir(), 'html-annotator-tests');
mkdirSync(TESTDIR, { recursive: true });
const ROOT = process.env.HTML_ANNOTATOR_ROOT || process.env.LUC_ANNOTATOR_ROOT || join(homedir(), 'annotations');

const SKILL = process.env.HTML_ANNOTATOR_SKILL_DIR || process.env.LUC_ANNOTATOR_SKILL_DIR
  || join(fileURLToPath(new URL('..', import.meta.url)));
const PORT = process.env.HTML_ANNOTATOR_PORT || process.env.LUC_ANNOTATOR_PORT || '8791';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* Let op het woord "klaar.": dat staat er twee keer, en alleen de tweede wordt
   gewijzigd. Dat is met opzet. Zonder context om zich op te ankeren kan een blok niet
   weten wélke van de twee bedoeld is — en dát is de eigenschap die hier bewezen moet
   worden. Met een uniek woord bewijst de test niets: de kale tekst volstaat dan al. */
const ORIGINEEL = `Hoi Kim,

De coverage-cijfers staan klaar. Ik loop ze donderdag met je door.

Het losse overzicht staat klaar.

Groet,
Sam`;

/* Drie wijzigingen, ver uit elkaar en elk aaneengesloten, zodat ze echt drie blokken
   worden. Een eerdere versie gebruikte "Laat even weten of dat schikt." ->
   "Laat je weten of dat uitkomt?" en kreeg terecht víer blokken: "even"->"je" en
   "schikt."->"uitkomt?" met ongewijzigde tekst ertussen zijn twee wijzigingen, geen één.
   De diff had gelijk en de test niet. */
const laatste = ORIGINEEL.lastIndexOf('klaar.');
const NIEUW = (ORIGINEEL.slice(0, laatste) + 'gereed.' + ORIGINEEL.slice(laatste + 'klaar.'.length))
  .replace('Hoi Kim,', 'Hallo Kim,')
  .replace('donderdag', 'vrijdag');

const slug = `zz-test-hunks-${Date.now()}`;
const bestand = join(TESTDIR, `${slug}.html`);
writeFileSync(bestand, `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<div class="la-draft">
  <div class="la-draft-hdr"><b>Aan:</b> Kim &nbsp;·&nbsp; <b>Onderwerp:</b> Coverage</div>
  <div class="la-draft-txt">${ORIGINEEL}</div>
</div>
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-06: ${tekst}`); if (!ok) falen++; };

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage();
await page.goto(`http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`, { waitUntil: 'load' });
await page.waitForSelector('.la-draft-txt.la-bewerkbaar', { timeout: 5000 });

await page.click('.la-draft-txt');
await page.evaluate((t) => { document.querySelector('.la-draft-txt').textContent = t; }, NIEUW);
await page.evaluate(() => document.querySelector('.la-draft-txt').blur());
await sleep(1500);
await page.click('.la-draft-diff');
await sleep(300);

const jsonPath = (await page.evaluate(() => window.LucAnnotator.bridge().jsonPath) || '')
  .replace(/^~/, homedir());
let ann = null;
if (existsSync(jsonPath)) {
  ann = (JSON.parse(readFileSync(jsonPath, 'utf8')).annotations || [])
    .filter((a) => a.type === 'edit')[0] || null;
}
zeg(!!ann, `bewerking teruggelezen uit ${jsonPath || '(geen pad)'}`);

const hunks = (ann && ann.hunks) || [];
zeg(hunks.length === 3, `drie losse wijzigingen worden drie blokken (${hunks.length})`);

// Elk blok moet op zichzelf plaatsbaar zijn: zonder anker is het onbruikbaar.
zeg(hunks.every((h) => (h.voor || h.na)),
  'elk blok draagt context als anker, geen kale positie');
zeg(hunks.every((h) => typeof h.alinea === 'number' && h.alinea >= 1),
  `elk blok weet in welke alinea het staat (${hunks.map((h) => h.alinea).join(',')})`);

// De nummering op het scherm moet dezelfde blokken aanwijzen als de opslag, anders
// bedoelen de reviewer en de agent iets anders met "blok 2".
const opScherm = await page.evaluate(() =>
  Array.prototype.map.call(document.querySelectorAll('.la-draft-txt .la-hunk-nr'),
    (e) => Number(e.textContent)));
zeg(opScherm.join(',') === hunks.map((h) => h.n).join(','),
  `schermnummers komen overeen met de opslag (${opScherm.join(',')} vs ${hunks.map((h) => h.n).join(',')})`);

await browser.close();

/* Nu het punt van de hele exercitie: alleen blok 2 toepassen, de rest laten staan. */
const uit = execFileSync('python3', [join(SKILL, 'bin/pas-hunk-toe.py'), jsonPath,
  '--nr', String(ann.nr), '--hunks', '2', '--resolve'], { encoding: 'utf8' });
const naToepassen = readFileSync(bestand, 'utf8');
const kaart = naToepassen.slice(naToepassen.indexOf('la-draft-txt'), naToepassen.indexOf('</div>\n</div>'));
zeg(/vrijdag/.test(kaart), 'blok 2 is doorgevoerd in de pagina');
zeg(/Hoi Kim,/.test(kaart) && !/Hallo Kim,/.test(kaart),
  'blok 1 is ongemoeid gelaten — blokken zijn dus echt onafhankelijk');
zeg(/staat klaar\./.test(kaart), 'blok 3 is ongemoeid gelaten');

const naAfvinken = JSON.parse(readFileSync(jsonPath, 'utf8'));
const annNa = (naAfvinken.annotations || []).filter((a) => a.type === 'edit')[0];
const open = (annNa.hunks || []).filter((h) => !h.resolved).map((h) => h.n);
zeg(open.join(',') === '1,3', `alleen blok 2 staat afgevinkt, 1 en 3 blijven open (${open.join(',')})`);
zeg(annNa.resolved !== true,
  'de bewerking zelf geldt nog niet als verwerkt zolang er blokken openstaan');

/* Twee dingen tegelijk waar een positie op stukloopt: er komt tekst bóven het blok bij,
   én het te wijzigen woord komt twee keer voor. Alleen het anker kan dit nog aanwijzen. */
writeFileSync(bestand, readFileSync(bestand, 'utf8')
  .replace('Hoi Kim,', 'Hoi Kim,\n\nEven vooraf: dit is een extra alinea.'));
let uit3 = '';
try {
  uit3 = execFileSync('python3', [join(SKILL, 'bin/pas-hunk-toe.py'), jsonPath,
    '--nr', String(ann.nr), '--hunks', '3'], { encoding: 'utf8' });
} catch (e) { uit3 = String(e.stdout || e.message); }
const eind = readFileSync(bestand, 'utf8');
zeg(/staat gereed\./.test(eind),
  'blok 3 landt op de juiste van twee gelijke zinnen, ook met tekst erboven erbij');
zeg(/staan klaar\./.test(eind),
  'de andere "klaar." is niet aangeraakt — het anker koos, niet de volgorde');

/* Terug naar de pagina: nadat een agent één blok heeft doorgevoerd moet de reviewer zijn nog
   openstaande blokken blíjven zien. Anders raakt hij zijn eigen wijziging uit beeld
   zodra er iets van verwerkt is — precies wanneer overzicht het meest telt. */
writeFileSync(bestand, `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<div class="la-draft">
  <div class="la-draft-hdr"><b>Aan:</b> Kim &nbsp;·&nbsp; <b>Onderwerp:</b> Coverage</div>
  <div class="la-draft-txt">${ORIGINEEL.replace('donderdag', 'vrijdag')}</div>
</div>
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

const browser2 = await chromium.launch({ channel: 'chrome', headless: true });
const page2 = await browser2.newPage();
await page2.goto(`http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`, { waitUntil: 'load' });
await sleep(2500);
await page2.click('.la-draft-diff');
await sleep(300);
const herstel = await page2.evaluate(() => {
  const box = document.querySelector('.la-draft-txt');
  return {
    nrs: Array.prototype.map.call(box.querySelectorAll('.la-hunk-nr'), (e) => e.textContent).join(','),
    del: Array.prototype.map.call(box.querySelectorAll('del'), (e) => e.textContent).join('|'),
    melding: (document.querySelector('.la-draft-meld') || {}).textContent || '',
  };
});
await browser2.close();
// Beide nog openstaande blokken moeten terug zijn: blok 1 ("Hoi"->"Hallo") en blok 3
// ("klaar."->"gereed."). Alleen het gewijzigde woord is doorgehaald, niet de hele regel —
// "Kim," veranderde immers niet.
zeg(/Hoi/.test(herstel.del) && /klaar\./.test(herstel.del),
  `beide open blokken staan er nog, ook nu blok 2 is doorgevoerd (doorgehaald: ${JSON.stringify(herstel.del)})`);
zeg(!/donderdag/.test(herstel.del),
  'het al doorgevoerde blok wordt niet opnieuw getoond');
zeg(!/gewijzigd sinds annotatie/.test(herstel.melding),
  `geen "tekst is gewijzigd"-melding meer, de blokken zijn gewoon herplaatst (${JSON.stringify(herstel.melding)})`);

if (process.env.CASE06_TOON) { console.log(uit.trim(), '\n', uit3.trim()); }

rmSync(bestand, { force: true });
rmSync(join(ROOT, slug), { recursive: true, force: true });
process.exit(falen ? 1 : 0);
