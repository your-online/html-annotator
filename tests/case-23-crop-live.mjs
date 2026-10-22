/* case-23 (B44, B45): de crop van een regio-annotatie toont wat de reviewer op dat moment zag.

   Voor 09-10-2026 renderde de bridge bij /save het paginabestand opnieuw, vers geladen,
   in headless Chrome. Alles wat de reviewer interactief had veranderd ging daarbij
   verloren. Deze case zet vier soorten live staat neer en kijkt per soort of de crop
   hem laat zien:

   1. een <details> die dicht is bij het laden en die de reviewer openklikt;
   2. een overflow:auto-container die gescrold is;
   3. een element dat een paginascript na een klik verandert (en dat het script bij
      het laden juist terugzet: draaien de paginascripts in de snapshot, dan faalt dit);
   4. een position:fixed-kop bij een gescrold venster (een volledige-paginarender zet
      die bovenaan het document, niet bovenaan wat de reviewer zag).

   Plus: de crop is vergeleken met een referentiescreenshot van de live pagina (zelfde
   box, annotator-UI verborgen); de snapshot belandt nooit in localStorage; een comment
   bewerken maakt geen nieuwe crop; annotatie verwijderen = crop-bestand weg; en een
   file://-pagina (snapshot direct naar /save) krijgt ook een live crop.

   B45: de screenshotbrowser draait met een eigen wegwerpprofiel en een mock-keychain
   (geen keychain-prompts), en --no-sandbox blijft opt-in zoals in B41. Dat deel draait
   tegen een nep-Chrome die zijn argv vastlegt, dus zonder echte browser.

   tests/run.sh start de bridge op een vrije poort met een tijdelijke root en configmap
   (HTML_ANNOTATOR_PORT, HTML_ANNOTATOR_ROOT): de live bridge en de echte
   annotatierondes worden niet aangeraakt. */

import { chromium } from 'playwright-core';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync, existsSync, mkdirSync, mkdtempSync, chmodSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SKILL = fileURLToPath(new URL('..', import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const PORT = process.env.HTML_ANNOTATOR_PORT;
const ROOT = process.env.HTML_ANNOTATOR_ROOT;
if (!PORT || !ROOT || PORT === '8791') {
  console.log('  BLOKKED case-23: zet HTML_ANNOTATOR_PORT (niet 8791) en HTML_ANNOTATOR_ROOT (tests/run.sh doet dat)');
  process.exit(2);
}
const env = { ...process.env, PYTHONPATH: SKILL };
let omhoog = false;
for (let i = 0; i < 50 && !omhoog; i++) {
  try { omhoog = (await fetch(`http://127.0.0.1:${PORT}/ping`)).ok; } catch { await sleep(200); }
}
if (!omhoog) { console.log(`  BLOKKED case-23: geen bridge op ${PORT}`); process.exit(2); }

const TESTDIR = join(homedir(), 'html-annotator-tests');
mkdirSync(TESTDIR, { recursive: true });
const slug = `zz-test-crop-live-${Date.now()}`;
const bestand = join(TESTDIR, `${slug}.html`);

/* Kleuren zijn zo gekozen dat elke staat een eigen, eenduidige kleur heeft:
   rood = uitgeklapte details, groen = wat er bij dichte details op die plek staat,
   magenta = streep 5 van de scroller (zichtbaar na scrollTop 500), geel = streep 0,
   blauw = door het script gezette staat, grijs = wat het script bij laden zet,
   cyaan = de fixed kop. */
writeFileSync(bestand, `<!doctype html><meta charset="utf-8"><title>${slug}</title>
<style>
  body { margin: 0; font: 14px/1.3 sans-serif; background: #fff }
  #kop { position: fixed; top: 0; left: 0; right: 0; height: 40px; background: #00ffff; z-index: 5 }
  .ruimte { height: 800px }
  details { margin: 0 20px }
  summary { height: 24px }
  #inhoud { height: 100px; background: #ff0000 }
  #groen { height: 60px; margin: 0 20px; background: #00ff00 }
  #rol { height: 200px; overflow: auto; margin: 20px; width: 400px }
  #rol div { height: 100px }
  #js { height: 100px; margin: 20px; width: 400px; background: #ff8800 }
</style>
<div id="kop"></div>
<div class="ruimte"></div>
<details id="det"><summary>Statistiekdetails</summary><div id="inhoud"></div></details>
<div id="groen"></div>
<div id="rol">
  <div style="background:#ffff00"></div><div style="background:#ffffff"></div>
  <div style="background:#000000"></div><div style="background:#ffffff"></div>
  <div style="background:#000000"></div><div style="background:#ff00ff"></div>
  <div style="background:#ff00ff"></div><div style="background:#ffffff"></div>
</div>
<div id="js"></div>
<button id="knop" onclick="document.getElementById('js').style.background='#0000ff'">zet blauw</button>
<div class="ruimte"></div>
<script>
  document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('js').style.background = '#888888';
  });
</script>
${readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8')}`);

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-23: ${tekst}`); if (!ok) falen++; };
const jsonPad = () => join(ROOT, slug, 'ronde-01', 'annotations.json');
const lees = () => { try { return JSON.parse(readFileSync(jsonPad(), 'utf8')); } catch { return { annotations: [] }; } };

function opruimen() {
  rmSync(bestand, { force: true });
}

let browser;
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 900, height: 600 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.HtmlAnnotator && window.HtmlAnnotator.bridge().ok, null, { timeout: 8000 });

  // Live staat neerzetten, zoals een reviewer het zou doen.
  await page.evaluate(() => window.scrollTo(0, 760));
  await page.click('#det summary');
  await page.evaluate(() => { document.getElementById('rol').scrollTop = 500; });
  await page.click('#knop');
  await page.evaluate(() => window.scrollTo(0, 760));
  await sleep(200);

  /* Doorlopend selecteren (B43) kan de regio-modus na Save aan laten: zet hem expliciet. */
  async function modus(p, aan) {
    const nu = await p.evaluate(() => !!document.getElementById('la-overlay'));
    if (nu !== aan) await p.click('#la-toggle');
  }

  const vak = async (sel) => page.evaluate((s) => {
    const b = document.querySelector(s).getBoundingClientRect();
    return { x: Math.round(b.left), y: Math.round(b.top), w: Math.round(b.width), h: Math.round(b.height) };
  }, sel);

  /* Referentie: screenshot van de live pagina, annotator-UI verborgen, op precies de box
     die de bridge knipt (rect + marge 12, binnen het document). */
  const MARGE = 12;
  async function referentie(r) {
    const tag = await page.addStyleTag({ content: '#la-bar,#la-popup,.la-rect,.la-badge,.la-ghost,#la-wees{visibility:hidden!important}' });
    const x0 = Math.max(0, r.x - MARGE), y0 = Math.max(0, r.y - MARGE);
    const clip = { x: x0, y: y0, width: r.x + r.w + MARGE - x0, height: r.y + r.h + MARGE - y0 };
    const buf = await page.screenshot({ clip });
    await tag.evaluate((n) => n.remove());
    return buf;
  }

  async function sleep_regio(r, comment) {
    await modus(page, true);
    await page.mouse.move(r.x, r.y);
    await page.mouse.down();
    await page.mouse.move(r.x + r.w / 2, r.y + r.h / 2, { steps: 4 });
    await page.mouse.move(r.x + r.w, r.y + r.h, { steps: 4 });
    await page.mouse.up();
    await page.waitForSelector('#la-popup .la-comment-ed', { timeout: 3000 });
    await page.type('#la-popup .la-comment-ed', comment);
    const n = lees().annotations.length;
    await page.click('#la-popup .la-save');
    for (let i = 0; i < 100; i++) {
      const a = lees().annotations;
      if (a.length > n && a[a.length - 1].comment === comment && 'image' in a[a.length - 1]) return a[a.length - 1];
      await sleep(200);
    }
    return null;
  }

  // Box binnen het element, een stukje van de randen af.
  const binnen = (b, pad = 10) => ({ x: b.x + pad, y: b.y + pad, w: b.w - 2 * pad, h: b.h - 2 * pad });
  const det = binnen(await vak('#inhoud'));
  const rol = binnen(await vak('#rol'));
  const js = binnen(await vak('#js'));
  const kop = { x: 300, y: 4, w: 200, h: 60 };   // fixed kop (0-40) plus de zone eronder

  const refs = { det: await referentie(det), rol: await referentie(rol), js: await referentie(js), kop: await referentie(kop) };

  const a1 = await sleep_regio(det, 'details open');
  const a2 = await sleep_regio(rol, 'scroller');
  const a3 = await sleep_regio(js, 'js-staat');
  const a4 = await sleep_regio(kop, 'fixed kop');

  // Pixels lezen in de browser: geen PNG-library nodig.
  const pix = await ctx.newPage();
  async function analyse(buf, kleuren) {
    return pix.evaluate(async ({ b64, kleuren }) => {
      const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
      const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
      const g = c.getContext('2d'); g.drawImage(img, 0, 0);
      const d = g.getImageData(0, 0, c.width, c.height).data;
      const tel = {}; kleuren.forEach((k) => { tel[k] = 0; });
      const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
      const doelen = kleuren.map(rgb);
      for (let i = 0; i < d.length; i += 4) {
        doelen.forEach((t, j) => {
          if (Math.abs(d[i] - t[0]) < 40 && Math.abs(d[i + 1] - t[1]) < 40 && Math.abs(d[i + 2] - t[2]) < 40) tel[kleuren[j]]++;
        });
      }
      const n = d.length / 4;
      const frac = {}; kleuren.forEach((k) => { frac[k] = tel[k] / n; });
      return { w: c.width, h: c.height, frac, data: Array.from(d) };
    }, { b64: buf.toString('base64'), kleuren });
  }
  function verschil(x, y) {
    if (x.w !== y.w || x.h !== y.h) return 999;
    let som = 0;
    for (let i = 0; i < x.data.length; i += 4) {
      som += Math.abs(x.data[i] - y.data[i]) + Math.abs(x.data[i + 1] - y.data[i + 1]) + Math.abs(x.data[i + 2] - y.data[i + 2]);
    }
    return som / (x.data.length / 4) / 3;
  }
  const crop = (a) => (a && a.image ? readFileSync(join(ROOT, slug, 'ronde-01', a.image)) : null);

  async function controleer(naam, a, ref, goed, fout) {
    const c = crop(a);
    if (!c) { zeg(false, `${naam}: geen crop (${a ? a.imageError : 'annotatie niet opgeslagen'})`); return; }
    const kl = await analyse(c, [goed, fout]);
    const rf = await analyse(ref, [goed, fout]);
    zeg(kl.frac[goed] > 0.5 && kl.frac[fout] < 0.05,
      `${naam}: crop toont de live staat (${goed} ${(kl.frac[goed] * 100).toFixed(0)}%, ${fout} ${(kl.frac[fout] * 100).toFixed(0)}%)`);
    const v = verschil(kl, rf);
    zeg(v < 6, `${naam}: crop ≈ referentiescreenshot van de live pagina (${kl.w}x${kl.h} vs ${rf.w}x${rf.h}, gem. verschil ${v === 999 ? 'maat wijkt af' : v.toFixed(2)})`);
    zeg(a.cropSource === 'live', `${naam}: cropSource = live (${a.cropSource})`);
  }

  await controleer('details', a1, refs.det, '#ff0000', '#00ff00');
  await controleer('scroller', a2, refs.rol, '#ff00ff', '#ffff00');
  await controleer('js-staat', a3, refs.js, '#0000ff', '#888888');
  if (a4 && a4.image) {
    const kl = await analyse(crop(a4), ['#00ffff']);
    const rf = await analyse(refs.kop, ['#00ffff']);
    zeg(Math.abs(kl.frac['#00ffff'] - rf.frac['#00ffff']) < 0.05 && kl.frac['#00ffff'] > 0.2,
      `fixed kop: zelfde aandeel cyaan als live (${(kl.frac['#00ffff'] * 100).toFixed(0)}% vs ${(rf.frac['#00ffff'] * 100).toFixed(0)}%)`);
  } else {
    zeg(false, 'fixed kop: geen crop');
  }

  // De snapshot hoort nooit in localStorage (te groot, en paginainhoud).
  const ls = await page.evaluate(() => localStorage.getItem('luc-annotaties:' + location.pathname) || '');
  zeg(ls.length < 20000 && ls.indexOf('<html') < 0 && ls.indexOf('snapshot') < 0,
    `localStorage bevat geen snapshot (${ls.length} tekens)`);

  await modus(page, false);

  // Comment bewerken: de crop van het selectiemoment blijft staan.
  if (a2 && a2.image) {
    const voor = crop(a2);
    await page.evaluate(() => document.getElementById('rol').scrollTop = 0);   // staat verandert
    const badge = await page.$$eval('.la-badge', (bs) => bs.findIndex((b) => b.textContent === '2'));
    await page.locator('.la-badge').nth(badge).click();
    await page.waitForSelector('#la-popup .la-comment-ed');
    await page.click('#la-popup .la-comment-ed');
    await page.keyboard.press('End');
    await page.keyboard.type(' (bewerkt)');
    await page.click('#la-popup .la-save');
    let na = null;
    for (let i = 0; i < 50; i++) {
      na = lees().annotations.find((a) => a.nr === a2.nr);
      if (na && /bewerkt/.test(na.comment)) break;
      await sleep(200);
    }
    zeg(!!na && /bewerkt/.test(na.comment) && na.image === a2.image && Buffer.compare(voor, crop(na)) === 0
      && na.cropSource === 'live', 'comment bewerken laat de crop van het selectiemoment staan');
  }

  // Verwijderen: annotatie weg = crop weg.
  if (a1 && a1.image) {
    const pad = join(ROOT, slug, 'ronde-01', a1.image);
    const badge = await page.$$eval('.la-badge', (bs) => bs.findIndex((b) => b.textContent === '1'));
    await page.locator('.la-badge').nth(badge).click();
    await page.waitForSelector('#la-popup .la-del');
    await page.click('#la-popup .la-del');
    let weg = false;
    for (let i = 0; i < 30 && !weg; i++) { weg = !existsSync(pad) && !lees().annotations.some((a) => a.nr === a1.nr); if (!weg) await sleep(200); }
    zeg(weg, 'annotatie verwijderen haalt ook het crop-bestand weg');
    zeg(existsSync(join(ROOT, slug, 'ronde-01', a3.image)), 'de crops van de andere annotaties blijven staan');
  }

  // Retina: devicePixelRatio 2 geeft een crop op dubbele resolutie, gelijk aan de live weergave.
  {
    const ctx2 = await browser.newContext({ viewport: { width: 900, height: 600 }, deviceScaleFactor: 2 });
    const p2 = await ctx2.newPage();
    await p2.goto(`http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`, { waitUntil: 'load' });
    await p2.waitForFunction(() => window.HtmlAnnotator && window.HtmlAnnotator.bridge().ok, null, { timeout: 8000 });
    await p2.evaluate(() => window.scrollTo(0, 760));
    await p2.click('#det summary');
    await p2.evaluate(() => window.scrollTo(0, 760));
    const b = await p2.evaluate(() => { const r = document.getElementById('inhoud').getBoundingClientRect(); return { x: Math.round(r.left) + 10, y: Math.round(r.top) + 10, w: Math.round(r.width) - 20, h: Math.round(r.height) - 20 }; });
    const tag = await p2.addStyleTag({ content: '#la-bar,#la-popup,.la-rect,.la-badge,.la-ghost,#la-wees{visibility:hidden!important}' });
    const ref = await p2.screenshot({ clip: { x: b.x - MARGE, y: b.y - MARGE, width: b.w + 2 * MARGE, height: b.h + 2 * MARGE } });
    await tag.evaluate((n) => n.remove());
    const n0 = lees().annotations.length;
    await modus(p2, true);
    await p2.mouse.move(b.x, b.y); await p2.mouse.down();
    await p2.mouse.move(b.x + b.w, b.y + b.h, { steps: 5 }); await p2.mouse.up();
    await p2.waitForSelector('#la-popup .la-comment-ed');
    await p2.type('#la-popup .la-comment-ed', 'retina');
    await p2.click('#la-popup .la-save');
    let a = null;
    for (let i = 0; i < 100 && !a; i++) { const l = lees().annotations; a = l.length > n0 && l.find((x) => x.comment === 'retina' && 'image' in x); if (!a) await sleep(200); }
    if (a && a.image) {
      const kl = await analyse(crop(a), ['#ff0000']);
      const rf = await analyse(ref, ['#ff0000']);
      zeg(kl.w === rf.w && kl.h === rf.h && kl.w === 2 * (b.w + 2 * MARGE) && verschil(kl, rf) < 6,
        `DPR 2: crop op dubbele resolutie, gelijk aan live (${kl.w}x${kl.h} vs ${rf.w}x${rf.h}, verschil ${verschil(kl, rf).toFixed(2)})`);
    } else {
      zeg(false, 'DPR 2: geen crop');
    }
    await ctx2.close();
  }

  // file://-pagina: geen /p/, de snapshot gaat rechtstreeks mee naar /save.
  const snapHtml = readFileSync(bestand, 'utf8').split('<!-- HTML-ANNOTATOR')[0]
    .replace('<details id="det">', '<details id="det" open>')
    .replace(/<script>[\s\S]*?<\/script>/g, '');
  // Zonder snapshot (oude snippet): de oude route, gemarkeerd als file.
  const rf0 = await fetch(`http://127.0.0.1:${PORT}/save`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      page: 'file://' + bestand, pageFile: bestand, slug: slug + '-oud', title: 'oud',
      doc: { w: 900, h: 2400 },
      annotation: { id: 'oud-1', type: 'region', rect: { x: det.x, y: det.y + 760, w: det.w, h: det.h }, comment: 'oud' },
    }),
  }).then((x) => x.json());
  {
    const fa = (rf0.ok && JSON.parse(readFileSync(rf0.jsonPath, 'utf8')).annotations.find((x) => x.id === 'oud-1')) || {};
    zeg(rf0.ok && fa.cropSource === 'file' && !!fa.image, `zonder snapshot: oude route, cropSource = file (${fa.cropSource})`);
  }

  // Een /snap/-token bestaat alleen tijdens het renderen.
  {
    const r404 = await fetch(`http://127.0.0.1:${PORT}/snap/onbekend`);
    zeg(r404.status === 404, `/snap/<onbekend token> geeft 404 (${r404.status})`);
  }

  const r = await fetch(`http://127.0.0.1:${PORT}/save`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      page: 'file://' + bestand, pageFile: bestand, slug: slug + '-file', title: 'file',
      doc: { w: 900, h: 2400 },
      snapshot: { html: snapHtml, vw: 900, vh: 600, sx: 0, sy: 760, dpr: 1 },
      annotation: { id: 'file-1', type: 'region', rect: { x: det.x, y: det.y + 760, w: det.w, h: det.h }, comment: 'file' },
    }),
  }).then((x) => x.json());
  if (r.ok && r.image) {
    const fa = JSON.parse(readFileSync(r.jsonPath, 'utf8')).annotations.find((x) => x.id === 'file-1') || {};
    const kl = await analyse(readFileSync(join(r.jsonPath, '..', r.image)), ['#ff0000', '#00ff00']);
    zeg(kl.frac['#ff0000'] > 0.5 && fa.cropSource === 'live',
      `file://-pagina: crop uit de snapshot (rood ${(kl.frac['#ff0000'] * 100).toFixed(0)}%, cropSource ${fa.cropSource})`);
  } else {
    zeg(false, `file://-pagina: geen crop (${JSON.stringify(r).slice(0, 200)})`);
  }

  // Zonder Pillow: het venster is de crop zelf (iframe verschoven); zelfde uitkomst.
  {
    const uit = join(ROOT, 'zonder-pillow.png');
    const snapPad = join(ROOT, 'snap.json');
    writeFileSync(snapPad, JSON.stringify({ html: snapHtml, vw: 900, vh: 600, sx: 0, sy: 760, dpr: 1 }));
    const py = spawnSync('python3', ['-c', `
import json, sys
from html_annotator import bridge as b
b.HEEFT_PILLOW = False
snap = json.load(open(sys.argv[1]))
b.maak_crop_live(snap, sys.argv[2], json.loads(sys.argv[3]), sys.argv[4])
`, snapPad, 'file://' + bestand, JSON.stringify({ x: det.x, y: det.y + 760, w: det.w, h: det.h }), uit],
    { cwd: SKILL, env, encoding: 'utf8' });
    if (py.status === 0 && existsSync(uit)) {
      const kl = await analyse(readFileSync(uit), ['#ff0000']);
      zeg(kl.frac['#ff0000'] > 0.5 && kl.w === det.w + 2 * MARGE,
        `zonder Pillow: crop uit de snapshot (${kl.w}x${kl.h}, rood ${(kl.frac['#ff0000'] * 100).toFixed(0)}%)`);
    } else {
      zeg(false, `zonder Pillow: mislukt (${(py.stderr || '').trim().split('\n').pop()})`);
    }
  }

  // B45: eigen wegwerpprofiel + mock-keychain; --no-sandbox alleen opt-in (B41).
  {
    const nep = mkdtempSync(join(tmpdir(), 'ann-c23-chrome-'));
    const nepChrome = join(nep, 'chrome');
    writeFileSync(nepChrome, `#!/usr/bin/env python3
import json, os, sys
shot = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--screenshot=")][0]
prof = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--user-data-dir=")]
with open(os.environ["C23_ARGV"], "w") as f:
    json.dump({"argv": sys.argv[1:], "profielBestond": bool(prof) and os.path.isdir(prof[0])}, f)
open(shot, "wb").write(b"png")
`);
    chmodSync(nepChrome, 0o755);
    const run = (extra) => {
      const argvPad = join(nep, 'argv.json');
      const py = spawnSync('python3', ['-c', `
import os, sys
from html_annotator import bridge as b
b.CHROME = sys.argv[1]
b.run_chrome(["--screenshot=" + os.path.join(sys.argv[2], "shot.png"), "about:blank"], timeout=20)
`, nepChrome, nep], { cwd: SKILL, env: { ...env, ...extra, C23_ARGV: argvPad }, encoding: 'utf8' });
      if (py.status !== 0) return { fout: (py.stderr || '').trim().split('\n').pop() };
      return JSON.parse(readFileSync(argvPad, 'utf8'));
    };
    const a = run({ HTML_ANNOTATOR_CHROME_NO_SANDBOX: '' });
    if (a.fout) {
      zeg(false, `B45: nep-Chrome draaide niet (${a.fout})`);
    } else {
      const prof = (a.argv.find((x) => x.startsWith('--user-data-dir=')) || '').split('=')[1];
      zeg(a.argv.includes('--use-mock-keychain') && a.argv.includes('--password-store=basic'),
        'B45: screenshotbrowser start met --use-mock-keychain en --password-store=basic');
      zeg(!!prof && /html-annotator-chrome-/.test(prof) && a.profielBestond && !existsSync(prof),
        `B45: eigen wegwerpprofiel (--user-data-dir), na afloop weg (${prof})`);
      const root = typeof process.getuid === 'function' && process.getuid() === 0;
      zeg(root || !a.argv.includes('--no-sandbox'), 'B41 intact: geen --no-sandbox zonder opt-in');
    }
    const b = run({ HTML_ANNOTATOR_CHROME_NO_SANDBOX: '1' });
    zeg(!b.fout && b.argv.includes('--no-sandbox') && b.argv.includes('--use-mock-keychain'),
      'B41 intact: HTML_ANNOTATOR_CHROME_NO_SANDBOX=1 voegt --no-sandbox toe, naast de mock-keychain');
    rmSync(nep, { recursive: true, force: true });
  }
} catch (e) {
  zeg(false, 'onverwachte fout: ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e));
} finally {
  if (browser) await browser.close();
  opruimen();
}
process.exit(falen ? 1 : 0);
