/* B47 (browser): een open voorstel in de agenda-preview is te slepen; de nieuwe tijd
   landt via de bridge in <root>/<slug>/state.json (component agenda, key voorstel-<nr>,
   met base) en `agenda-spec.py --apply-state` zet hem terug in de overlay. Een
   verstuurd voorstel (ook afgeleid uit een echt event) is niet sleepbaar en een oude
   sleep wordt bij laden niet toegepast. Geen echte agenda: de events zijn een
   dummy-bestand. De standaardpoort wordt nergens geraakt: elk verzoek naar
   127.0.0.1:8791 wordt in de browser afgebroken. */
import { chromium } from 'playwright-core';
import { writeFileSync, readFileSync, rmSync, mkdirSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createServer } from 'node:http';

const SKILL = process.env.HTML_ANNOTATOR_SKILL_DIR || join(fileURLToPath(new URL('..', import.meta.url)));
const PORT = process.env.HTML_ANNOTATOR_PORT;
const ROOT = process.env.HTML_ANNOTATOR_ROOT;
if (!PORT || !ROOT) {
  console.log('  BLOKKED  case-25: HTML_ANNOTATOR_PORT en HTML_ANNOTATOR_ROOT verplicht (ephemeral bridge)');
  process.exit(2);
}
const PY = process.env.PYTHON || 'python3';
const TESTDIR = join(homedir(), 'html-annotator-tests');
mkdirSync(TESTDIR, { recursive: true });
const slug = `zz-agenda-slepen-${Date.now()}`;
const pagina = join(TESTDIR, `${slug}.html`);
const devPagina = join(TESTDIR, `${slug}-dev.html`);
const overlay = join(TESTDIR, `${slug}.voorstellen.json`);
const cal = join(TESTDIR, `${slug}.cal.json`);
const spec = join(TESTDIR, `${slug}.spec.json`);
const URL_P = `http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`;
const statePad = join(ROOT, slug, 'state.json');

const prop = (nr, start, end, status = 'open') => ({ nr, title: `Overleg ${nr}`, start, end,
  invitees: [`x${nr}@example.com`], toelichting: '', notitie: '', status });
const ov = { heading: 'test', hours: [8, 18], weeks: 3, proposals: [
  prop(1, '2026-10-07T09:00', '2026-10-07T09:45'), // wo: verplaatsen
  prop(2, '2026-10-08T11:00', '2026-10-08T11:30', 'verstuurd'),
  prop(3, '2026-10-08T13:00', '2026-10-08T13:30'), // overlay open, echt event → afgeleid verstuurd
  prop(4, '2026-10-06T09:00', '2026-10-06T09:45'), // di: grepen + snap
  prop(5, '2026-10-09T09:00', '2026-10-09T09:45'), // vr: overlap + terug naar voorstel
  prop(6, '2026-10-05T09:00', '2026-10-05T09:45'), // ma: pointercancel
  prop(7, '2026-10-10T09:00', '2026-10-10T09:45'), // za: trage bridge
  prop(8, '2026-10-11T09:00', '2026-10-11T09:45'), // zo: state komt binnen tijdens het slepen
] };
writeFileSync(overlay, JSON.stringify(ov));
const ev = (subject, a, b) => ({ subject, start: { dateTime: a, timeZone: 'Europe/Amsterdam' },
  end: { dateTime: b, timeZone: 'Europe/Amsterdam' } });
writeFileSync(cal, JSON.stringify({ value: [
  ev('Bestaand', '2026-10-07T14:00:00', '2026-10-07T15:00:00'),
  ev('Bestaand 2', '2026-10-09T10:00:00', '2026-10-09T11:00:00'),
  ev('Overleg 3', '2026-10-08T13:00:00', '2026-10-08T13:30:00'),
] }));

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-25: ${tekst}`); if (!ok) falen++; };
const py = (...args) => spawnSync(PY, args, { encoding: 'utf8', env: process.env });
const opruimen = () => [pagina, devPagina, overlay, cal, spec].forEach((f) => rmSync(f, { force: true }));
const bouw = (uit) => {
  const r1 = py(join(SKILL, 'bin', 'agenda-spec.py'), '--cal', `werk:Werk:purple:${cal}`, '--start', '2026-10-05',
    '--weeks', '3', '--overlay', overlay, '-o', spec);
  const r2 = py(join(SKILL, 'bin', 'agenda-preview.py'), spec, '-o', uit, '--no-snippet');
  if (r1.status !== 0 || r2.status !== 0) throw new Error('bouwen faalde: ' + r1.stderr + r2.stderr);
};
const leesState = () => (existsSync(statePad) ? JSON.parse(readFileSync(statePad, 'utf8')) : { components: {} });
const schrijfEntry = (key, entry) => {
  const s = leesState(); s.components = s.components || {}; s.components.agenda = s.components.agenda || {};
  s.components.agenda[key] = entry; mkdirSync(join(ROOT, slug), { recursive: true });
  writeFileSync(statePad, JSON.stringify(s));
};
const wachtOpPil = (page, re) => page.waitForFunction((src) => new RegExp(src).test(document.getElementById('agsave')?.textContent || ''),
  re.source, { timeout: 5000 }).catch(() => {});
const items = async (page) => Object.fromEntries((await page.evaluate(() => window.AgendaPreview.items())).map((i) => [i.nr, i]));
const tijd = (i) => i && `${i.start.slice(11)}–${i.end.slice(11)}`;

/* De weekkolom van een datum (zichtbare week) en de y van een tijd daarin (PX = 60 per uur, H0 = 8). */
async function kolom(page, j, m, d) {
  return page.evaluate(([j, m, d]) => {
    const el = document.querySelector('.week:not([hidden]) .day[data-day="' + new Date(j, m - 1, d).toDateString() + '"]');
    const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width };
  }, [j, m, d]);
}
const yVan = (k, hhmm) => { const [h, mi] = hhmm.split(':').map(Number); return k.y + (h * 60 + mi - 8 * 60); };
async function midden(page, sel) {
  const el = await page.$(sel); await el.scrollIntoViewIfNeeded(); const b = await el.boundingBox();
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}
async function sleep(page, van, naar) {
  await page.mouse.move(van.x, van.y); await page.mouse.down();
  await page.mouse.move(van.x, (van.y + naar.y) / 2, { steps: 3 }); await page.mouse.move(naar.x, naar.y, { steps: 3 });
  await page.mouse.up();
}
async function nieuwePagina(browser) {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1400 } });
  const fouten = [];
  page.on('pageerror', (e) => fouten.push(e.message));
  // de standaardpoort nooit raken: een draaiende bridge daar is niet van deze test
  await page.route('http://127.0.0.1:8791/**', (route) => route.abort());
  return { page, fouten };
}
async function naarWeek5Okt(page) {
  for (let i = 0; i < 3 && (await page.textContent('#wkr')) !== '5 Oct – 11 Oct'; i++) await page.click('#prev');
  return page.textContent('#wkr');
}

let browser;
try {
  bouw(pagina);
  // Oude sleeps op verstuurde voorstellen: mogen bij laden niets verzetten.
  schrijfEntry('voorstel-2', { start: '2026-10-08T15:00', end: '2026-10-08T15:30', base: { start: '2026-10-08T11:00', end: '2026-10-08T11:30' } });
  schrijfEntry('voorstel-3', { start: '2026-10-08T16:00', end: '2026-10-08T16:30', base: { start: '2026-10-08T13:00', end: '2026-10-08T13:30' } });

  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const { page, fouten } = await nieuwePagina(browser);
  try { await page.goto(URL_P, { waitUntil: 'load', timeout: 8000 }); }
  catch { console.log('  BLOKKED  case-25: bridge niet bereikbaar op poort ' + PORT); process.exit(2); }
  await wachtOpPil(page, /autosave on/);
  zeg((await page.textContent('#agsave')) === 'autosave on', 'pil zegt "autosave on" (bridge bereikt via de eigen origin)');
  zeg((await naarWeek5Okt(page)) === '5 Oct – 11 Oct', 'week van 5 oktober gekozen via de weeknavigatie');
  let it = await items(page);
  zeg(tijd(it[2]) === '11:00–11:30' && tijd(it[3]) === '13:00–13:30',
    `oude sleeps op verstuurde voorstellen niet toegepast bij laden (#2 ${tijd(it[2])}, #3 ${tijd(it[3])})`);
  zeg(await page.$('.k-prop.s-verstuurd.drag') === null && await page.$('.k-prop.s-verstuurd[data-id="p3"]') !== null,
    'verstuurd voorstel (ook afgeleid uit een echt event) is niet sleepbaar');

  // #1 een uur omlaag slepen (PX = 60 px per uur).
  const m1 = await midden(page, '.k-prop[data-id="p1"]');
  await sleep(page, m1, { x: m1.x, y: m1.y + 60 });
  it = await items(page);
  zeg(it[1] && it[1].start === '2026-10-07T10:00' && it[1].end === '2026-10-07T10:45' && it[1].moved,
    `#1 staat na het slepen op 10:00–10:45 (${tijd(it[1])})`);
  zeg(/moved/.test(await page.textContent('.k-prop[data-id="p1"] .mv')), 'het blok draagt het label "moved"');

  // Grepen: onder verzet alleen het eind, boven alleen het begin; beide snappen op 15 min.
  // (kolom pas meten na het scrollen dat midden() kan doen)
  const hb = await midden(page, '.k-prop[data-id="p4"] .hd.hb');
  let di = await kolom(page, 2026, 10, 6);
  await sleep(page, hb, { x: di.x + di.w / 2, y: yVan(di, '10:22') });
  it = await items(page);
  zeg(tijd(it[4]) === '09:00–10:15', `ondergreep naar 10:22 → eind gesnapt op 10:15, begin blijft (${tijd(it[4])})`);
  const ht = await midden(page, '.k-prop[data-id="p4"] .hd.ht');
  di = await kolom(page, 2026, 10, 6);
  await sleep(page, ht, { x: di.x + di.w / 2, y: yVan(di, '08:37') });
  it = await items(page);
  zeg(tijd(it[4]) === '08:30–10:15', `bovengreep naar 08:37 → begin gesnapt op 08:30, eind blijft (${tijd(it[4])})`);

  // Overlap met een bestaand event waarschuwt; "back to proposal" zet het terug.
  const m5 = await midden(page, '.k-prop[data-id="p5"]');
  await sleep(page, m5, { x: m5.x, y: m5.y + 60 });
  it = await items(page);
  zeg(tijd(it[5]) === '10:00–10:45' && it[5].clash && await page.$('.k-prop.clash[data-id="p5"]') !== null,
    `#5 op een bestaand event: overlap gemeld (${tijd(it[5])}, clash ${it[5] && it[5].clash})`);
  await page.click('.k-prop[data-id="p5"]');
  const knop = await page.$('#pop .reset');
  zeg(!!knop && (await knop.textContent()) === 'back to proposal', 'popover heeft de knop "back to proposal"');
  if (knop) await knop.click();
  it = await items(page);
  zeg(tijd(it[5]) === '09:00–09:45' && !it[5].moved && !it[5].clash, `na "back to proposal" staat #5 weer op 09:00 (${tijd(it[5])})`);

  // pointercancel (touch die de browser overneemt) beëindigt het slepen.
  await page.evaluate(() => addEventListener('pointerdown', (e) => { window.__pid = e.pointerId; }, true));
  const m6 = await midden(page, '.k-prop[data-id="p6"]');
  await page.mouse.move(m6.x, m6.y); await page.mouse.down();
  await page.mouse.move(m6.x, m6.y + 30, { steps: 3 }); await page.mouse.move(m6.x, m6.y + 60, { steps: 3 });
  await page.evaluate(() => dispatchEvent(new PointerEvent('pointercancel', { pointerId: window.__pid, bubbles: true })));
  const sleeptNog = await page.$('.k-prop.dragging') !== null;
  await page.mouse.move(m6.x, m6.y + 120, { steps: 3 }); await page.mouse.up();
  it = await items(page);
  zeg(!sleeptNog && tijd(it[6]) === '10:00–10:45', `pointercancel zet #6 neer waar hij was (${tijd(it[6])}, nog slepend: ${sleeptNog})`);

  let entry = null;
  for (let i = 0; i < 30 && !(entry && entry.start === '2026-10-07T10:00'); i++) {
    await page.waitForTimeout(100);
    entry = leesState().components?.agenda?.['voorstel-1'] || null;
  }
  zeg(!!entry && entry.start === '2026-10-07T10:00' && entry.end === '2026-10-07T10:45'
    && entry.base && entry.base.start === '2026-10-07T09:00', `state.json heeft voorstel-1 met base (${JSON.stringify(entry)})`);
  zeg((await page.textContent('#agsave')).startsWith('saved '), `pil na opslaan: "${await page.textContent('#agsave')}"`);

  // Herladen: de state wint van de overlay zolang base gelijk is.
  await page.reload({ waitUntil: 'load' });
  await wachtOpPil(page, /autosave on/);
  it = await items(page);
  zeg(tijd(it[1]) === '10:00–10:45' && tijd(it[4]) === '08:30–10:15', `na herladen: #1 ${tijd(it[1])}, #4 ${tijd(it[4])}`);

  // De agent verzet #4 in de overlay: bij herladen wint de overlay, de oude sleep niet.
  ov.proposals[3] = prop(4, '2026-10-06T11:00', '2026-10-06T11:45');
  writeFileSync(overlay, JSON.stringify(ov));
  bouw(pagina);
  await page.reload({ waitUntil: 'load' });
  await wachtOpPil(page, /autosave on/);
  it = await items(page);
  zeg(tijd(it[4]) === '11:00–11:45' && !it[4].moved && tijd(it[1]) === '10:00–10:45',
    `verouderde sleep (overlay sindsdien gewijzigd) genegeerd: #4 ${tijd(it[4])}, #1 ${tijd(it[1])}`);
  zeg(fouten.length === 0, `geen paginafouten (${fouten.join('; ')})`);
  await page.close();

  // Sync terug in de overlay, via de bridge op deze poort.
  const r3 = py(join(SKILL, 'bin', 'agenda-spec.py'), '--apply-state', overlay, '--by', 'tester');
  const ovNa = JSON.parse(readFileSync(overlay, 'utf8'));
  const o = (nr) => ovNa.proposals.find((p) => p.nr === nr);
  zeg(r3.status === 0 && o(1).start === '2026-10-07T10:00'
    && o(1).notitie === 'moved by tester from Wed 07-10 09:00–09:45 to Wed 07-10 10:00–10:45',
  `--apply-state zet #1 terug in de overlay ("${o(1).notitie}") ${r3.stderr}`);
  zeg(/^state: .*\(bridge\)$/m.test(r3.stdout), `de sync liep via de bridge, niet via schijf (${r3.stdout.split('\n')[0]})`);
  zeg(o(3).start === '2026-10-08T13:00' && o(4).start === '2026-10-06T11:00',
    `sync laat het afgeleid verstuurde #3 en het door de agent verzette #4 staan (#3 ${o(3).start}, #4 ${o(4).start})`);

  // Trage bridge: de eerste opslag van #7 blijft hangen terwijl #7 opnieuw verschuift.
  // De laatste stand moet winnen, niet het antwoord dat het laatst binnenkomt.
  {
    const { page: p2, fouten: f2 } = await nieuwePagina(browser);
    let eerste = true;
    await p2.route('**/state-save', async (route) => {
      const b = route.request().postData() || '';
      if (eerste && b.includes('"voorstel-7"')) { eerste = false; await new Promise((r) => setTimeout(r, 1500)); }
      return route.continue();
    });
    await p2.goto(URL_P, { waitUntil: 'load' });
    await wachtOpPil(p2, /autosave on/);
    await naarWeek5Okt(p2);
    const a = await midden(p2, '.k-prop[data-id="p7"]');
    await sleep(p2, a, { x: a.x, y: a.y + 60 });
    const b = await midden(p2, '.k-prop[data-id="p7"]');
    await sleep(p2, b, { x: b.x, y: b.y + 60 });
    let e7 = null;
    for (let i = 0; i < 40; i++) { await p2.waitForTimeout(100); e7 = leesState().components?.agenda?.['voorstel-7']; }
    zeg(!!e7 && e7.start === '2026-10-10T11:00', `trage bridge: state van #7 is de laatste sleep, 11:00 (${e7 && e7.start})`);
    zeg(f2.length === 0, `geen paginafouten (${f2.join('; ')})`);
    await p2.close();
  }

  // State komt binnen terwijl de reviewer sleept: niet over de hand heen schrijven,
  // en niet opnieuw renderen midden in een sleep (dan verdwijnt het gesleepte blok).
  {
    schrijfEntry('voorstel-8', { start: '2026-10-11T15:00', end: '2026-10-11T15:45', base: { start: '2026-10-11T09:00', end: '2026-10-11T09:45' } });
    const { page: p3, fouten: f3 } = await nieuwePagina(browser);
    // het antwoord vertragen (de bridge leest de state nú), niet het verzoek
    await p3.route('**/state', async (route) => {
      const res = await route.fetch(); await new Promise((r) => setTimeout(r, 1500)); return route.fulfill({ response: res });
    });
    await p3.goto(URL_P, { waitUntil: 'load' });
    await naarWeek5Okt(p3);
    const a = await midden(p3, '.k-prop[data-id="p8"]');
    await p3.mouse.move(a.x, a.y); await p3.mouse.down();
    await p3.mouse.move(a.x, a.y + 30, { steps: 3 });
    await wachtOpPil(p3, /autosave on/); // state is binnen, de sleep loopt nog
    await p3.mouse.move(a.x, a.y + 60, { steps: 3 }); await p3.mouse.up();
    const i3 = await items(p3);
    zeg(f3.length === 0, `geen paginafout als de state midden in een sleep binnenkomt (${f3.join('; ')})`);
    zeg(tijd(i3[8]) === '10:00–10:45', `de sleep van de reviewer wint van de geladen state (#8 ${tijd(i3[8])})`);
    zeg(tijd(i3[7]) === '11:00–11:45' && await p3.$('.week:not([hidden]) .k-prop[data-id="p7"] .mv') !== null,
      `geladen state van #7 staat na het neerzetten wél op de pagina (${tijd(i3[7])})`);
    await p3.close();
  }

  // Idem, maar de reviewer zet het blok al neer vóór de state binnen is.
  {
    schrijfEntry('voorstel-8', { start: '2026-10-11T15:00', end: '2026-10-11T15:45', base: { start: '2026-10-11T09:00', end: '2026-10-11T09:45' } });
    const { page: p3, fouten: f3 } = await nieuwePagina(browser);
    // het antwoord vertragen (de bridge leest de state nú), niet het verzoek
    await p3.route('**/state', async (route) => {
      const res = await route.fetch(); await new Promise((r) => setTimeout(r, 1500)); return route.fulfill({ response: res });
    });
    await p3.goto(URL_P, { waitUntil: 'load' });
    await naarWeek5Okt(p3);
    const a = await midden(p3, '.k-prop[data-id="p8"]');
    await sleep(p3, a, { x: a.x, y: a.y + 120 });
    await wachtOpPil(p3, /autosave on/);
    const i3 = await items(p3);
    zeg(f3.length === 0 && tijd(i3[8]) === '11:00–11:45',
      `state die na het neerzetten binnenkomt overschrijft de sleep niet (#8 ${tijd(i3[8])}) ${f3.join('; ')}`);
    await p3.close();
  }

  // Bridge onbereikbaar bij laden: de pil zegt het.
  {
    const { page: p4 } = await nieuwePagina(browser);
    await p4.route('**/state', (route) => route.abort());
    await p4.goto(URL_P, { waitUntil: 'load' });
    await wachtOpPil(p4, /bridge off/);
    zeg((await p4.textContent('#agsave')) === 'bridge off', `pil bij onbereikbare bridge: "${await p4.textContent('#agsave')}"`);
    await p4.close();
  }

  // Buiten /p/ (lokale dev-server of preview-pane) met de endpoint-meta naar de testbridge:
  // de agenda volgt de meta en stuurt de pagina-identiteit mee, dus de state landt onder de
  // slug van het paginabestand en de sync vindt hem.
  {
    bouw(devPagina);
    const html = readFileSync(devPagina, 'utf8').replace('<head>',
      `<head><meta name="html-annotator-endpoint" content="http://127.0.0.1:${PORT}/">`);
    // een echte dev-server op een vrije poort (geen /p/-pad, niet de bridge)
    const dev = createServer((req, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(html); });
    await new Promise((r) => dev.listen(0, '127.0.0.1', r));
    const { page: p5, fouten: f5 } = await nieuwePagina(browser);
    await p5.goto(`http://localhost:${dev.address().port}/dev/agenda.html`, { waitUntil: 'load' });
    await wachtOpPil(p5, /autosave on/);
    zeg((await p5.textContent('#agsave')) === 'autosave on', `dev-server: pil "${await p5.textContent('#agsave')}" (meta gevolgd)`);
    await naarWeek5Okt(p5);
    const a = await midden(p5, '.k-prop[data-id="p1"]');
    await sleep(p5, a, { x: a.x, y: a.y + 60 });
    const devState = join(ROOT, `${slug}-dev`, 'state.json');
    let e = null;
    for (let i = 0; i < 30 && !e; i++) {
      await p5.waitForTimeout(100);
      if (existsSync(devState)) e = JSON.parse(readFileSync(devState, 'utf8')).components?.agenda?.['voorstel-1'] || null;
    }
    zeg(!!e && e.start === '2026-10-07T11:00', `dev-server: state onder de slug van het paginabestand (${JSON.stringify(e)})`);
    const r = py(join(SKILL, 'bin', 'agenda-spec.py'), '--apply-state', overlay, '--page', devPagina, '--dry-run');
    zeg(r.status === 0 && /#1 moved by reviewer from Wed 07-10 10:00–10:45 to Wed 07-10 11:00–11:45/.test(r.stdout)
      && /\(bridge\)$/m.test(r.stdout),
      `dev-server: de sync vindt de sleep (${(r.stdout + r.stderr).trim()})`);
    zeg(f5.length === 0, `geen paginafouten (${f5.join('; ')})`);
    await p5.close();
    dev.close();
  }
} catch (e) {
  console.log(`  FAIL  case-25: ${e.message}`);
  falen++;
} finally {
  if (browser) await browser.close();
  opruimen();
}
console.log(falen ? `  case-25: ROOD (${falen})` : '  case-25: groen');
process.exit(falen ? 1 : 0);
