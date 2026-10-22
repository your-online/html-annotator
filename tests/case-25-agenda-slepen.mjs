/* B47 (browser): een open voorstel in de agenda-preview is te slepen; de nieuwe tijd
   landt via de bridge in <root>/<slug>/state.json (component agenda, key voorstel-<nr>,
   met base) en agenda-sync.py zet hem terug in de overlay. Een verstuurd voorstel is
   niet sleepbaar. Geen echte agenda: de events zijn een dummy-bestand. */
import { chromium } from 'playwright-core';
import { writeFileSync, readFileSync, rmSync, mkdirSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

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
const overlay = join(TESTDIR, `${slug}.voorstellen.json`);
const cal = join(TESTDIR, `${slug}.cal.json`);
const spec = join(TESTDIR, `${slug}.spec.json`);

const prop = (nr, start, end, status = 'open') => ({ nr, title: `Overleg ${nr}`, start, end,
  invitees: [`x${nr}@example.com`], toelichting: '', notitie: '', status });
writeFileSync(overlay, JSON.stringify({ heading: 'test', hours: [8, 18], proposals: [
  prop(1, '2026-10-07T09:00', '2026-10-07T09:45'),
  prop(2, '2026-10-08T11:00', '2026-10-08T11:30', 'verstuurd'),
] }));
writeFileSync(cal, JSON.stringify({ value: [{ subject: 'Bestaand', start: { dateTime: '2026-10-07T14:00:00', timeZone: 'Europe/Amsterdam' },
  end: { dateTime: '2026-10-07T15:00:00', timeZone: 'Europe/Amsterdam' } }] }));

let falen = 0;
const zeg = (ok, tekst) => { console.log(`  ${ok ? 'PASS' : 'FAIL'}  case-25: ${tekst}`); if (!ok) falen++; };
const py = (...args) => spawnSync(PY, args, { encoding: 'utf8', env: process.env });
const opruimen = () => [pagina, overlay, cal, spec].forEach((f) => rmSync(f, { force: true }));

let browser;
try {
  const r1 = py(join(SKILL, 'bin', 'agenda-spec.py'), '--cal', `werk:Werk:purple:${cal}`, '--start', '2026-10-05',
    '--weeks', '1', '--overlay', overlay, '-o', spec);
  const r2 = py(join(SKILL, 'bin', 'agenda-preview.py'), spec, '-o', pagina, '--no-snippet');
  if (r1.status !== 0 || r2.status !== 0) throw new Error('bouwen faalde: ' + r1.stderr + r2.stderr);

  browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  try { await page.goto(`http://127.0.0.1:${PORT}/p/html-annotator-tests/${slug}.html`, { waitUntil: 'load', timeout: 8000 }); }
  catch { console.log('  BLOKKED  case-25: bridge niet bereikbaar op poort ' + PORT); process.exit(2); }
  await page.waitForFunction(() => /autosave aan/.test(document.getElementById('agsave')?.textContent || ''), null, { timeout: 5000 }).catch(() => {});
  zeg((await page.textContent('#agsave')) === 'autosave aan', 'pil zegt "autosave aan" (bridge bereikt via de eigen origin)');
  zeg(await page.$('.k-prop.s-verstuurd.drag') === null, 'verstuurd voorstel is niet sleepbaar');

  // De week van 5 oktober tonen en #1 een uur omlaag slepen (PX = 60 px per uur).
  await page.evaluate(() => { const w = [...document.querySelectorAll('.week')]; w.forEach((s, i) => { s.hidden = i !== 0; }); });
  const el = await page.$('.k-prop.drag');
  await el.scrollIntoViewIfNeeded();
  const b = await el.boundingBox();
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.mouse.move(x, y); await page.mouse.down();
  await page.mouse.move(x, y + 30, { steps: 3 }); await page.mouse.move(x, y + 60, { steps: 3 });
  await page.mouse.up();
  const items = await page.evaluate(() => window.AgendaPreview.items());
  const p1 = items.find((i) => i.nr === 1);
  zeg(p1 && p1.start === '2026-10-07T10:00' && p1.end === '2026-10-07T10:45' && p1.moved,
    `#1 staat na het slepen op 10:00–10:45 (${p1 && p1.start}–${p1 && p1.end})`);

  const statePad = join(ROOT, slug, 'state.json');
  let entry = null;
  for (let i = 0; i < 30 && !entry; i++) {
    await page.waitForTimeout(100);
    if (existsSync(statePad)) entry = JSON.parse(readFileSync(statePad, 'utf8')).components?.agenda?.['voorstel-1'] || null;
  }
  zeg(!!entry && entry.start === '2026-10-07T10:00' && entry.end === '2026-10-07T10:45'
    && entry.base && entry.base.start === '2026-10-07T09:00', `state.json heeft voorstel-1 met base (${JSON.stringify(entry)})`);

  // Herladen: de state wint van de overlay zolang base gelijk is.
  await page.reload({ waitUntil: 'load' });
  await page.waitForFunction(() => /autosave aan/.test(document.getElementById('agsave')?.textContent || ''), null, { timeout: 5000 }).catch(() => {});
  const na = (await page.evaluate(() => window.AgendaPreview.items())).find((i) => i.nr === 1);
  zeg(na && na.start === '2026-10-07T10:00', `na herladen staat #1 nog op 10:00 (${na && na.start})`);

  // Sync terug in de overlay, via de bridge op deze poort.
  const r3 = py(join(SKILL, 'bin', 'agenda-sync.py'), overlay, '--by', 'tester');
  const ov = JSON.parse(readFileSync(overlay, 'utf8'));
  const o1 = ov.proposals.find((p) => p.nr === 1);
  zeg(r3.status === 0 && o1.start === '2026-10-07T10:00' && /^door tester verplaatst van /.test(o1.notitie),
    `agenda-sync zet #1 terug in de overlay ("${o1.notitie}")`);
} catch (e) {
  console.log(`  FAIL  case-25: ${e.message}`);
  falen++;
} finally {
  if (browser) await browser.close();
  opruimen();
}
console.log(falen ? `  case-25: ROOD (${falen})` : '  case-25: groen');
process.exit(falen ? 1 : 0);
