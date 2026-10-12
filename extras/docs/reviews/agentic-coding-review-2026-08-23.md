# Review: html-annotator layout-refactor

Diff basis: 472cf63 (laatste commit vóór dit doel; de hele opruimronde is
uncommitted working tree). Eén revisie na [Review My Work](3beadc1b-4f4e-4768-bdd1-2ac9e455aa3d)
en [Falsifier van de review](066b2349-a825-4fe8-a31a-4c293ac0ac28). Finding 1
uit v1 (A7 rood) is geschrapt: `tests/red/ronde-17-a7-default.txt` is een echte
groene single-invocation.

## Wat overeind blijft

Criteria stonden er vóór de `git mv` (transcript 318–328). De mutatie-harnesses
werken op een kopie. Tests zijn onder druk aangescherpt, niet versmald
(case-02, case-03, case-04, punt-trigger). Gaten hebben een naam (Gat-kolom,
B18–B20, BLOKKED ≠ pass).

Tien contract-mutanten en zeven layout-mutanten bijten. De PASS-telling in de
captures is hoger omdat ongemutileerde baselines meekomen.

## Wat zwak is

1. **B16 staat als lock, dit diff maakt het.** `acceptance.md` zet B16 onder
   *Bestaand gedrag*. Op 472cf63 bestaan `zoekHostViaLabel` / `laHostPast` /
   `laRegioTeWijd` niet. A7 leest als regressiegarantie over code die samen met
   zijn tests is geschreven. C3. Remedie: B16 naar gewijzigd gedrag, met de
   gerapporteerde bug erbij. Geen klantpagina in de suite — die staat niet in
   deze repo; case-08 is al de gereduceerde vorm (cross-row + herhaalde
   `Backlog`).

2. **B7 groeide een assert die productie dwong.** De lock (tmp + replace,
   origineel blijft) gold al. `B7 dump-fout laat geen tmp` in
   `test_bridge_contract.py` forceerde `os.remove(tmp)`. C3. Remedie: die eis
   apart zetten, mutant op `os.remove`.

3. **Bridge-origin is ongezegd en tandeloos op 8791.** Het snippet leidt
   `BRIDGE` af onder `/p/`. case-08 assert `origin === "http://127.0.0.1:" +
   PORT` met default 8791, dus de oude constante slaagt ook. Alleen
   `mutate-contract.sh` (case-10, niet in A7) gebruikt een random poort. C3/C6.
   Remedie: B-rij + `LUC_ANNOTATOR_PORT` verplicht in case-08.

4. **Geen rood record op de pre-move boom; A3 en A5 zonder mutant.**
   `mutate-layout.sh` dekt A1/A2/A4/A6. C6. Remedie: `git archive 472cf63` +
   huidige layout-test bewaren; mutanten voor extras/ en naamgeving.

5. **Niets gecommit, binding is partieel.** Headers hashen snippet/hook/ensure,
   niet de bridge of de tests. Dit transcript slaat geen tool-results op. C7.
   Remedie: twee commits + SHA op de capture — niet in deze ronde (geen commit
   zonder opdracht).

6. **Captures worden overschreven.** `ronde-17-a7-default.txt` is een eerdere
   rode run kwijt. C7. Remedie: niet herschrijven; `ronde-16-a7-default.txt`
   (proza, geen output) weg.

7. **Bestaande installs breken; `--copy` op een stale `$DOEL` liegt.**
   `install.sh` laat een bestaande non-clone staan en registreert daarna
   `$DOEL/bin/hook-ensure-bridge.sh` alsof die er is. A4-test gebruikt een verse
   HOME. C9. Remedie: `--copy` ververst; geen hook-claim zonder bestand;
   upgrade-paragraaf in INSTALL.md.

8. **De riskantste regressie (`.`-trigger, snippet-standaard) heeft geen
   artefact-check.** A2 slaagt op `/p/` + `kaal` — ook op 472cf63. C3. Remedie:
   SKILL-description en handbook op de punt-trigger; mutant die die zin weghaalt.

9. **Drie criteria-vocabularies.** `acceptance.md`, `tests/criteria.md`,
   `VERIFICATION.md` AC-1…AC-7. `run.sh` citeert criteria.md nog als actueel.
   Gate 5 verbiedt UI-string-wijzigingen die het pad-move al deed. C1. Remedie:
   citations rechtzetten, gate 5 pad-wijzigingen toestaan. `criteria.md` blijft
   historisch (niet wissen: narratie, geen tweede bron van waarheid).

10. **Drie baselines onder `set -e`.** Rode baseline breekt het script vóór het
    FAIL-bericht. C6. Remedie: `set +e` om de drie unmutated calls.

## Open twijfel

Klantfixture in de suite: geen. De pagina hoort niet bij deze skill-repo.
case-08 encodeert de gerapporteerde bug al. Commit-splitsing: wacht op de eigenaar.
