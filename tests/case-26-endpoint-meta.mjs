/* B48: <meta name="html-annotator-endpoint" content="<https-url>"> laat het snippet en
   het checklist-snippet naar een andere server schrijven dan de lokale bridge (een
   pagina die elders gepubliceerd is, sandbox, origin null). Zonder die meta, met een
   meta buiten <head>, op file:// (ook mét meta) en via /p/ van de bridge zelf
   (loopback-host, ook mét meta) blijft het gedrag exact zoals het was: 127.0.0.1:8791
   resp. de bridge zelf, pil "N saved". Een /p/-pad op een
   andere host is geen bridge: daar wint de meta, ook voor de agenda-pagina.

   De publicerende server wordt met page.route nagebootst: het gaat om de keuze van
   het endpoint en de pil, niet om de server. */
import { chromium } from 'playwright-core';
import { readFileSync, writeFileSync, rmSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

const SKILL = process.env.HTML_ANNOTATOR_SKILL_DIR || join(fileURLToPath(new URL('..', import.meta.url)));
const PORT = process.env.HTML_ANNOTATOR_PORT;
if (!PORT) {
  console.log('  BLOKKED  case-26: HTML_ANNOTATOR_PORT verplicht (ephemeral bridge voor de /p/-tak)');
  process.exit(2);
}
const TESTDIR = join(homedir(), 'html-annotator-tests');
mkdirSync(TESTDIR, { recursive: true });
const snippet = readFileSync(join(SKILL, 'references', 'annotator-snippet.html'), 'utf8');
const checklist = readFileSync(join(SKILL, 'references', 'checklist-snippet.html'), 'utf8');
const EP = 'https://publish.example.test/ann/TESTTOKEN';
const stamp = Date.now();
const metaPagina = join(TESTDIR, `zz-endpoint-meta-${stamp}.html`);
const kalePagina = join(TESTDIR, `zz-endpoint-kaal-${stamp}.html`);
const evilPagina = join(TESTDIR, `zz-endpoint-evil-${stamp}.html`);
const lijstPagina = join(TESTDIR, `zz-endpoint-lijst-${stamp}.html`);
const agendaPagina = join(TESTDIR, `zz-endpoint-agenda-${stamp}.html`);
const agendaSpec = join(TESTDIR, `zz-endpoint-agenda-${stamp}.spec.json`);
const bodyMetaPagina = join(TESTDIR, `zz-endpoint-bodymeta-${stamp}.html`);
const lijstKaal = join(TESTDIR, `zz-endpoint-lijstkaal-${stamp}.html`);
const body = (meta, extra = '') => `<!doctype html><html><head>${meta}<meta charset="utf-8"><title>endpoint ${stamp}</title></head>
<body><h1 id="h">Kop</h1><p id="p">Eerste alinea om te annoteren.</p>${extra}${snippet}</body></html>`;
const META = `<meta name="html-annotator-endpoint" content="${EP}/">`;
writeFileSync(metaPagina, body(META, '<p id="s" data-la-suggest="s1">Nieuwe zin.</p>'));
writeFileSync(kalePagina, body(''));
writeFileSync(evilPagina, body('<meta name="html-annotator-endpoint" content="javascript:alert(1)">'));
writeFileSync(lijstPagina, `<!doctype html><html><head>${META}<meta charset="utf-8"><title>lijst ${stamp}</title></head>
<body><ul><li data-la-check="punt-1"><span class="what">Punt een</span></li></ul>${checklist}</body></html>`);
// meta in de body (bv. geciteerde of geplakte inhoud): telt niet, voor beide snippets
writeFileSync(bodyMetaPagina, body('', `${META}<ul><li data-la-check="punt-1"><span class="what">Punt een</span></li></ul>${checklist}`));
writeFileSync(lijstKaal, `<!doctype html><html><head><meta charset="utf-8"><title>lijst ${stamp}</title></head>
<body>${META}<ul><li data-la-check="punt-1"><span class="what">Punt een</span></li></ul>${checklist}</body></html>`);

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-26: ${tekst}`); if (!ok) falen++; };
const opruimen = () => [metaPagina, kalePagina, evilPagina, lijstPagina, agendaPagina, agendaSpec,
  bodyMetaPagina, lijstKaal].forEach((f) => rmSync(f, { force: true }));

const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS' };

/* Bootst de publicerende server na; geeft de lijst gevraagde paden terug. */
async function nepServer(page, bodies) {
  const gezien = [];
  await page.route('https://publish.example.test/**', async (route) => {
    const req = route.request();
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS });
    const pad = new URL(req.url()).pathname;
    gezien.push(pad);
    if (bodies) bodies.push({ pad, body: req.postData() || '' });
    const antwoord = pad.endsWith('/session')
      ? { ok: true, round: 1, jsonPath: 'remote:x.html', count: 0, total: 0, maxNr: 0, annotations: [] }
      : pad.endsWith('/state')
        ? { ok: true, state: { components: {} } }
        : { ok: true, round: 1, jsonPath: 'remote:x.html', nr: 1, count: 1, open: 0 };
    return route.fulfill({ status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
      body: JSON.stringify(antwoord) });
  });
  return gezien;
}

/* Serveert een testbestand als https://pages.example.test/<naam> (een publicerende server). */
async function serveer(page, bestand, naam) {
  const html = readFileSync(bestand, 'utf8');
  await page.route('https://pages.example.test/**', (route) => route.request().method() === 'GET'
    ? route.fulfill({ status: 200, contentType: 'text/html', body: html })
    : route.fulfill({ status: 404, body: '' }));
  return `https://pages.example.test/${naam}`;
}

/* Vangt de lokale standaardpoort; geeft de lijst gevraagde paden terug. */
async function nepBridge(page) {
  const gezien = [];
  await page.route('http://127.0.0.1:8791/**', async (route) => {
    const req = route.request();
    if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS });
    gezien.push(new URL(req.url()).pathname);
    return route.fulfill({ status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ok: true, round: 1, jsonPath: '/tmp/x.json', count: 0, total: 0, maxNr: 0,
        annotations: [], state: { components: {} } }) });
  });
  return gezien;
}

let browser;
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true });

  // 1. elders gepubliceerd (https) mét meta → endpoint, pil "N saved remotely", lokale bridge nooit geraakt
  {
    const page = await browser.newPage();
    const gezien = await nepServer(page);
    let bridgeGeraakt = false;
    await page.route('http://127.0.0.1:8791/**', (route) => { bridgeGeraakt = true; return route.abort(); });
    await page.goto(await serveer(page, metaPagina, 'meta.html'), { waitUntil: 'load' });
    await page.waitForFunction(() => /saved remotely/.test(document.getElementById('la-status')?.textContent || ''),
      null, { timeout: 5000 }).catch(() => {});
    const api = await page.evaluate(() => window.HtmlAnnotator._test.bridgeOrigin);
    zeg(api === EP, `met meta schrijft het snippet naar het endpoint, zonder slash aan het eind (${api})`);
    const pil1 = await page.textContent('#la-status');
    zeg(pil1 === '0 saved remotely', `pil na sessie: "${pil1}"`);
    await page.evaluate(() => window.HtmlAnnotator.save({
      id: 'a-ep-1', type: 'region', rect: { x: 1, y: 2, w: 30, h: 20 }, comment: 'test', target: 'kop',
      createdAt: new Date().toISOString() }));
    const pil2 = await page.textContent('#la-status');
    zeg(pil2 === '1 saved remotely', `pil na opslaan: "${pil2}"`);
    zeg(gezien.includes('/ann/TESTTOKEN/session') && gezien.includes('/ann/TESTTOKEN/save'),
      `session + save gingen naar het endpoint (${gezien.join(', ')})`);
    // de andere routes ook: afvinken, verwijderen en suggestie-state
    page.on('dialog', (d) => d.dismiss());
    await page.evaluate(() => window.HtmlAnnotator.resolve(window.HtmlAnnotator.anns().find((a) => a.id === 'a-ep-1')));
    await page.evaluate(() => window.HtmlAnnotator.save({
      id: 'a-ep-2', type: 'region', rect: { x: 1, y: 2, w: 30, h: 20 }, comment: 'weg', target: 'kop',
      createdAt: new Date().toISOString() }));
    await page.evaluate(() => window.HtmlAnnotator.remove(window.HtmlAnnotator.anns().find((a) => a.id === 'a-ep-2')));
    await page.click('.la-sug-i-acc', { timeout: 3000 }).catch(() => {});
    for (let i = 0; i < 20 && !gezien.includes('/ann/TESTTOKEN/state-save'); i++) await page.waitForTimeout(100);
    zeg(['resolve', 'delete', 'state', 'state-save'].every((r) => gezien.includes('/ann/TESTTOKEN/' + r)),
      `resolve, delete, state en state-save gingen ook naar het endpoint (${gezien.join(', ')})`);
    zeg(!bridgeGeraakt, 'de lokale bridge is niet aangeroepen');
    await page.close();
  }

  // 2. file:// zónder meta → exact het oude gedrag: 127.0.0.1:8791 en "N saved"
  {
    const page = await browser.newPage();
    const gezien = [];
    await page.route('http://127.0.0.1:8791/**', async (route) => {
      const req = route.request();
      if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS });
      gezien.push(new URL(req.url()).pathname);
      return route.fulfill({ status: 200, headers: { ...CORS, 'Content-Type': 'application/json' },
        body: JSON.stringify({ ok: true, round: 1, jsonPath: '/tmp/x.json', count: 0, total: 0, maxNr: 0, annotations: [] }) });
    });
    await page.goto(pathToFileURL(kalePagina).href, { waitUntil: 'load' });
    await page.waitForFunction(() => / saved$/.test(document.getElementById('la-status')?.textContent || ''),
      null, { timeout: 5000 }).catch(() => {});
    const api = await page.evaluate(() => window.HtmlAnnotator._test.bridgeOrigin);
    zeg(api === 'http://127.0.0.1:8791', `zonder meta: bridge-origin ongewijzigd (${api})`);
    const pil = await page.textContent('#la-status');
    zeg(pil === '0 saved', `zonder meta: pil ongewijzigd ("${pil}")`);
    zeg(gezien.includes('/session'), 'zonder meta: /session ging naar 127.0.0.1:8791');
    await page.close();
  }

  // 3. meta met een niet-http(s)-waarde wordt genegeerd
  {
    const page = await browser.newPage();
    await page.route('http://127.0.0.1:8791/**', (route) => route.abort());
    await page.goto(pathToFileURL(evilPagina).href, { waitUntil: 'load' });
    const api = await page.evaluate(() => window.HtmlAnnotator._test.bridgeOrigin);
    zeg(api === 'http://127.0.0.1:8791', `meta met javascript: genegeerd (${api})`);
    await page.close();
  }

  // 4. via /p/ van de bridge, mét meta → de bridge zelf blijft leidend
  {
    const page = await browser.newPage();
    const rel = metaPagina.slice(homedir().length + 1).split(/[\\/]/).map(encodeURIComponent).join('/');
    await page.goto(`http://127.0.0.1:${PORT}/p/${rel}`, { waitUntil: 'load' });
    await page.waitForFunction(() => / saved$/.test(document.getElementById('la-status')?.textContent || ''),
      null, { timeout: 5000 }).catch(() => {});
    const api = await page.evaluate(() => window.HtmlAnnotator._test.bridgeOrigin);
    zeg(api === `http://127.0.0.1:${PORT}`, `/p/ met meta: de bridge blijft leidend (${api})`);
    const pil = await page.textContent('#la-status');
    zeg(/^\d+ saved$/.test(pil || ''), `/p/: pil "N saved" ("${pil}")`);
    await page.close();
  }

  // 5. checklist-snippet met meta (https): /state en /state-save gaan naar het endpoint
  {
    const page = await browser.newPage();
    const bodies = [];
    const gezien = await nepServer(page, bodies);
    let bridgeGeraakt = false;
    await page.route('http://127.0.0.1:8791/**', (route) => { bridgeGeraakt = true; return route.abort(); });
    await page.goto(await serveer(page, lijstPagina, 'lijst.html'), { waitUntil: 'load' });
    await page.waitForSelector('.la-check', { timeout: 3000 });
    await page.click('.la-check');
    for (let i = 0; i < 20 && !gezien.includes('/ann/TESTTOKEN/state-save'); i++) await page.waitForTimeout(100);
    zeg(gezien.includes('/ann/TESTTOKEN/state') && gezien.includes('/ann/TESTTOKEN/state-save'),
      `checklist: state + state-save naar het endpoint (${gezien.join(', ')})`);
    const save = bodies.find((b) => b.pad.endsWith('/state-save'));
    zeg(!!save && /"component":"checklist"/.test(save.body) && /"checked":true/.test(save.body),
      'checklist: het vinkje zit in de body');
    zeg(!bridgeGeraakt, 'checklist: de lokale bridge is niet aangeroepen');
    await page.close();
  }

  // 6. /p/-pad op een andere host dan loopback is niet de bridge: de meta wint, voor het
  //    annotator-snippet, het checklist-snippet en de agenda-pagina op dezelfde pagina.
  {
    const PY = process.env.PYTHON || 'python3';
    writeFileSync(agendaSpec, JSON.stringify({ start: '2026-10-05', weeks: 1, events: [], proposals: [
      { nr: 1, title: 'Overleg', start: '2026-10-07T09:00', end: '2026-10-07T09:45', status: 'open' }] }));
    const r = spawnSync(PY, [join(SKILL, 'bin', 'agenda-preview.py'), agendaSpec, '-o', agendaPagina], { encoding: 'utf8' });
    if (r.status !== 0) throw new Error('agenda bouwen faalde: ' + r.stderr);
    const html = readFileSync(agendaPagina, 'utf8').replace('<head>', `<head>${META}`)
      .replace('<!-- HTML-ANNOTATOR', `<ul><li data-la-check="punt-1"><span class="what">Punt een</span></li></ul>${checklist}<!-- HTML-ANNOTATOR`);
    const page = await browser.newPage();
    const gezien = await nepServer(page);
    const eigen = [];
    await page.route('https://pages.example.test/**', (route) => {
      if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'text/html', body: html });
      eigen.push(new URL(route.request().url()).pathname);
      return route.fulfill({ status: 404, body: '' });
    });
    await page.route('http://127.0.0.1:8791/**', (route) => { eigen.push('8791'); return route.abort(); });
    await page.goto('https://pages.example.test/p/agenda.html', { waitUntil: 'load' });
    const api = await page.evaluate(() => window.HtmlAnnotator._test.bridgeOrigin);
    zeg(api === EP, `/p/ op een niet-loopback-host: het snippet volgt de meta (${api})`);
    await page.waitForFunction(() => /autosave on/.test(document.getElementById('agsave')?.textContent || ''), null, { timeout: 5000 }).catch(() => {});
    zeg((await page.textContent('#agsave')) === 'autosave on', `agenda op die pagina volgt de meta ("${await page.textContent('#agsave')}")`);
    await page.click('.la-check');
    for (let i = 0; i < 20 && !gezien.includes('/ann/TESTTOKEN/state-save'); i++) await page.waitForTimeout(100);
    zeg(gezien.includes('/ann/TESTTOKEN/state-save'), `checklist op die pagina volgt de meta (${gezien.join(', ')})`);
    zeg(eigen.length === 0, `niets naar de eigen origin of de lokale bridge (${eigen.join(', ')})`);
    await page.close();
  }

  // 7. idem voor het checklist-snippet zonder annotator op de pagina (de terugval)
  {
    const page = await browser.newPage();
    const gezien = await nepServer(page);
    const eigen = [];
    const lijst = readFileSync(lijstPagina, 'utf8');
    await page.route('https://pages.example.test/**', (route) => {
      if (route.request().method() === 'GET') return route.fulfill({ status: 200, contentType: 'text/html', body: lijst });
      eigen.push(new URL(route.request().url()).pathname);
      return route.fulfill({ status: 404, body: '' });
    });
    await page.route('http://127.0.0.1:8791/**', (route) => { eigen.push('8791'); return route.abort(); });
    await page.goto('https://pages.example.test/p/lijst.html', { waitUntil: 'load' });
    await page.click('.la-check');
    for (let i = 0; i < 20 && !gezien.includes('/ann/TESTTOKEN/state-save'); i++) await page.waitForTimeout(100);
    zeg(gezien.includes('/ann/TESTTOKEN/state') && gezien.includes('/ann/TESTTOKEN/state-save') && eigen.length === 0,
      `losse checklist op /p/ van een niet-loopback-host volgt de meta (${gezien.join(', ')} | ${eigen.join(', ')})`);
    await page.close();
  }

  // 8. file:// mét meta in <head> → de meta telt niet: annotator en checklist-terugval
  //    blijven op 127.0.0.1:8791, niets naar het endpoint
  for (const [bestand, wat] of [[metaPagina, 'annotator'], [lijstPagina, 'losse checklist']]) {
    const page = await browser.newPage();
    const ep = await nepServer(page);
    const lokaal = await nepBridge(page);
    await page.goto(pathToFileURL(bestand).href, { waitUntil: 'load' });
    if (wat === 'annotator') {
      const api = await page.evaluate(() => window.HtmlAnnotator._test.bridgeOrigin);
      zeg(api === 'http://127.0.0.1:8791', `file:// met meta: ${wat} negeert de meta (${api})`);
      await page.waitForFunction(() => / saved$/.test(document.getElementById('la-status')?.textContent || ''),
        null, { timeout: 5000 }).catch(() => {});
    } else {
      await page.click('.la-check');
      for (let i = 0; i < 20 && !lokaal.includes('/state-save'); i++) await page.waitForTimeout(100);
    }
    zeg(ep.length === 0 && lokaal.length > 0,
      `file:// met meta: ${wat} schrijft niet naar het endpoint (endpoint: ${ep.join(', ')} | lokaal: ${lokaal.join(', ')})`);
    await page.close();
  }

  // 9. meta in de body (https) → telt niet, voor annotator, checklist via de annotator en de
  //    checklist-terugval
  for (const [bestand, wat] of [[bodyMetaPagina, 'annotator + checklist'], [lijstKaal, 'losse checklist']]) {
    const page = await browser.newPage();
    const ep = await nepServer(page);
    const lokaal = await nepBridge(page);
    await page.goto(await serveer(page, bestand, 'body.html'), { waitUntil: 'load' });
    if (wat !== 'losse checklist') {
      const api = await page.evaluate(() => window.HtmlAnnotator._test.bridgeOrigin);
      zeg(api === 'http://127.0.0.1:8791', `meta in de body: annotator negeert de meta (${api})`);
    }
    await page.click('.la-check');
    for (let i = 0; i < 20 && !lokaal.includes('/state-save'); i++) await page.waitForTimeout(100);
    zeg(ep.length === 0 && lokaal.includes('/state-save'),
      `meta in de body: ${wat} schrijft niet naar het endpoint (endpoint: ${ep.join(', ')} | lokaal: ${lokaal.join(', ')})`);
    await page.close();
  }
} catch (e) {
  console.log(`  FAIL  case-26: ${e.message}`);
  falen++;
} finally {
  if (browser) await browser.close();
  opruimen();
}
console.log(falen ? `  case-26: ROOD (${falen})` : '  case-26: groen');
process.exit(falen ? 1 : 0);
