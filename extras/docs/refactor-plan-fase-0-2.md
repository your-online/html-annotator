# Uitvoerplan: html-annotator schoner, 0 gedrag

> Superseded 2026-08-23 door de `bin/` + `annotator/`-layout. Alleen geschiedenis.

Randvoorwaarde: geen functionele wijziging, geen layout-wijziging, geen
wijziging van UI-copy. Bestaande `tests/run.sh` moet groen blijven.
HEAD bij start: `ded3ee5` (al op origin/main).

## Wat we wel / niet doen

Doen (fase 0–2, plus een dunne 3):
- document-seams zoals de sandbox-repo
- memories-bundle inperken
- één pad/ROOT-config in Python
- tests lezen de clone, niet alleen `~/.claude/skills/...`
- `__pycache__/` in `.gitignore`

Niet doen:
- snippet splitsen of een bundler (fase 4 = alleen comment-koppen in het
  bestaande bestand)
- `ensure-bridge.sh` / `hook-ensure-bridge.sh` / `annotator-bridge.py`
  verplaatsen (hooks en alerts blijven op root-paden)
- `~/Desktop/annotaties` als default wijzigen
- vijf persoonlijke memories wissen — die gaan naar een map met persoonlijke memories buiten de repo
  en worden niet meer geïnstalleerd

## Fase 0 — freeze

1. Schrijf `VERIFICATION.md`: geclusterde MUST-lijst uit de AC-inventaris
   (gebied + TYPE + TESTED/UNTESTED). Geen nieuwe eisen verzinnen.
2. Schrijf `decisions.md`: SessionStart altijd aan (18-08-2026); geen
   Remove-all in UI; Engelse UI; `/p/` verplicht; rondes sluiten alleen via
   `/remove-all`; paste-blok blijft één bestand.
3. In `tests/criteria.md` bovenaan één alinea: suite toetst een subset;
   volledige freeze staat in `VERIFICATION.md`.

## Fase 1 — skill-packaging

4. `references/agent-handbook.md` = huidige SKILL.md deel 2–7 (bridge,
   rondes, verwerken, todos, draft, la-sub), ongewijzigd van inhoud.
5. `SKILL.md` dun: frontmatter + deel 1 + korte verwerk-paragraaf.
   **VERPLICHT** bovenaan: lees `references/agent-handbook.md` vóór uitvoering.
   Triggers in de description blijven.
6. `memories/` houdt alleen:
   `html-annotator-standaard.md`, `punt-verwerk-annotaties.md`,
   `annotator-bridge-autostart.md`, `MEMORY-index-regels.md` (alleen die
   drie bullets).
7. Verplaats de vijf overige memories naar een map met persoonlijke memories buiten de repo + korte
   README daar: niet deel van de skill-install.
8. `install.sh` kopieert alleen de drie annotator-memories. Bestaande
   bestanden in een project-memory niet overschrijven (al zo).
9. README herschrijven: wat het is, `/p/`, tabel van bestanden, pointers
   naar INSTALL / VERIFICATION / decisions / handbook. Geen derde kopie
   van de hele skill.

## Fase 2 — paden, zonder hook-breuk

10. Nieuw `annotator_config.py`: `HOST`, `PORT`, `ROOT` (env
    `LUC_ANNOTATOR_ROOT` default `~/Desktop/annotaties`), `SKILL_DIR`.
    Bridge en `toon-annotaties.py` importeren dit. Defaults identiek aan nu.
11. Tests die `~/.claude/skills/html-annotator` hardcoden: snippet/bridge
    uit de repo-root van de test (`path.join(..., '..')`).
12. `.gitignore`: `__pycache__/`, `*.pyc`.
13. Geen `src/`/`bin/`-verhuizing in deze ronde.

## Fase 3 — dun, geen nieuw gedrag

14. `schoon_locator` + refs-validatie blijven in Python; documenteer het
    record in `references/annotation-record.md` (velden die `h_save` nu
    al schrijft). Geen extra verplichte velden, geen JS-payload-wijziging.

## Fase 4 — alleen leesbaarheid

15. In `annotator-snippet.html` duidelijke sectiekoppen (al deels aanwezig).
    Geen extractie, geen buildstap.

## Verificatie na afloop

- `tests/run.sh` (of de cases die zonder spend-limit/Chrome-blokkeren
  lopen). Minimaal: Python compile + `toon-annotaties.py --help`-achtige
  smoke + grep dat hook-paden nog `hook-ensure-bridge.sh` in de skill-root
  zijn.
- Diff-check: geen wijziging in snippet-CSS of Engelse UI-strings, behalve
  comment-koppen.
- `install.sh --dry` bestaat niet: handmatig nalopen dat alleen 3 memories
  in de loop zitten.

## Stopcondities

Stop en vraag de eigenaar als een stap het paste-blok, poort 8791, `/p/`-gedrag,
poller, of UI-copy zou moeten veranderen om “schoon” te worden.
