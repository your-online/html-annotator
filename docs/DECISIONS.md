# Decisions

Choices a later cleanup must not reopen without the owner.
Changing behaviour is a new decision, not an edit here.

## 2026-09-17 — Public names are `html-annotator`, old names stay as aliases (F3)

The skill ships under its own name instead of its author's. Public
surface: `window.HtmlAnnotator`, the markers `<!-- HTML-ANNOTATOR v3 -->`
… `<!-- /HTML-ANNOTATOR -->` written by new embeds, bridge identity
`"bridge": "html-annotator"` in `/ping`, and `HTML_ANNOTATOR_*`
environment variables. Reason: a distribution on PyPI and a public repo
cannot carry a personal identifier as its API, and `/ping` is what other
tooling matches on.

What did **not** change, on purpose: the localStorage prefix
`luc-annotaties` (renaming it drops unsent local drafts on pages that are
open right now), and the recognition of the old marker generation. The
bridge's content hash, the PostToolUse hook and the tests accept
`LUC-ANNOTATOR` v1/v2 blocks, so an existing page keeps working without
being re-embedded.

## 2026-09-17 — Alias policy: deprecated, not deleted, until 1.1

Every renamed thing keeps its old name working for one minor version:
the page-global alias assigned by the snippet, `LUC_ANNOTATOR_*` env
vars, `bin/toon-annotaties.py` and `bin/pas-hunk-toe.py`, and the old
markers. They are documented as deprecated in `INSTALL.md` and in the
migration section of `CHANGELOG.md`, not silently kept. The one thing
that changed without an alias is the `/ping` identity: a value cannot be
two strings at once, and a consumer that matched on it gets a clear
failure rather than a silent wrong branch.

Removal happens in 1.1, with the changelog entry written at that time.

## 2026-09-17 — Packaging: hatchling, one snippet source, skill files in the wheel (F2)

`pyproject.toml` uses hatchling and declares the distribution
`html-annotator` (checked free on PyPI on 2026-09-17), console script
`html-annotator = html_annotator.cli:main`, no runtime dependencies, and
`Pillow` behind the extra `[crops]`. The version has one home,
`html_annotator/__init__.py`; `[tool.hatch.version]` reads it, so a
release never has two numbers to keep in sync.

`references/` stays the single source of the paste blocks. The wheel
force-includes that directory as `html_annotator/snippets/` and
`SKILL.md` plus `bin/` as `html_annotator/_skill/`, so an installed
package can serve the snippet (`config.snippet_path()`) and
`install-skill` can assemble `~/.claude/skills/html-annotator` without a
checkout. The alternative — keeping a second copy of the snippet inside
the package directory — was rejected because two copies drift; criterion
A11 fails a copy that is not byte-identical.

In a checkout (and with `pip install -e .`) `config.is_checkout()` is
true and everything resolves against the working tree, so editing
`references/annotator-snippet.html` takes effect immediately.

## 2026-09-17 — One Python CLI, no bash, no jq (F1)

`install.sh`, `bin/ensure-bridge.sh` and `bin/hook-ensure-bridge.sh` are
gone. Everything runs through `python -m html_annotator` (package
`html_annotator/`, renamed from `annotator/`): `serve`, `ensure`, `stop`,
`status`, `show`, `resolve`, `apply-hunk`, `url`, `install-skill`,
`install-hooks`. Reason: a Windows user needed Git Bash plus jq for
install and hooks, which is a second toolchain for a stdlib-only skill.
`bin/*.py` stay as thin wrappers so older hooks and shortcuts keep
working. Pid file and log moved out of the checkout into a per-user
state directory, because a symlinked skill is read-only in spirit and a
copy would have carried them along.

## 2026-09-17 — Default annotation root `~/annotations`, old location wins if present

New installs write to `~/annotations`; a machine that already has the
older `annotaties` folder on the Desktop and no `~/annotations` keeps
using it. Env: `HTML_ANNOTATOR_ROOT` / `HTML_ANNOTATOR_PORT`, with the
`LUC_ANNOTATOR_*` names still accepted. Renaming the env vars without a
fallback would have broken running setups mid-session.

## 2026-09-17 — Scope: core versus extras (F0)

Core is snippet + bridge + CLI + handbook, plus the checklist and
suggest layers. Out: todo-list spawning (script deleted), the draft
message card and `la-sub` (docs and tests to `extras/`, code stays in
the snippet because the paste block is one file by the 2026-08-23
decision). `apply-hunk` stays core. Full reasoning: `docs/SCOPE.md`.

## 2026-08-18 — SessionStart hook always on

The bridge hook runs at user level on every agent session (empty
matcher). PostToolUse stays limited to `Edit|Write` on HTML with
`LUC-ANNOTATOR`. Do not narrow it: the bridge should be listening.

## 2026-08-18 — Pages via `/p/`, not `file://` or a preview pane

A `data:` origin cannot reach loopback (Private Network Access).
Deliver as `http://127.0.0.1:8791/p/<path-from-home>`.

## 2026-08-18 — Origin log stays on

Every bridge request logs `origin=` to stderr / `bridge.log`.

## 2026-08-23 — No Remove-all in the UI

`POST /remove-all` still exists. The button is gone. Rounds close only
through that endpoint, not through a page change.

## 2026-08-23 — English UI copy, status pill `X saved`

User-visible annotator strings are English. The pill shows the number
of open annotations, without a `round N -` prefix.

## 2026-08-23 — Paste block stays one file

`references/annotator-snippet.html` is the only thing that goes at the
bottom of HTML. No bundler, no split runtime JS until the output is
byte-identical.

## 2026-08-23 — Install without personal memories

`install.sh` does not install memories. Agent rules live in `SKILL.md`
and `references/`. Existing project `MEMORY.md` rules are not deleted.
`extras/luc-memories/` was removed (the plan said move). Source: this
cleanup, "it may change drastically". Content remains in git at
`472cf63`.

## 2026-08-23 — Locator follows the row, not the first repeated span

`zoekAnker` no longer treats "start span still exists" as processed.
The label comes from the start row; `zoekHostViaLabel` / `laHostPast`
keep repeated cell text on that row. Source: the client's owners, 2026-08-23.
No client page in the suite — case-08 is the reduced form.

## 2026-08-23 — Root is a port, CLIs in bin/

CLIs and hooks live in `bin/`. Python library in `annotator/`
(snake_case; renamed to `html_annotator/` on 2026-09-17). The ensure and
hook entry points are location-relative. Agent-facing docs name no person;
the page-global object and the `LUC-ANNOTATOR` marker stay (public API;
superseded on 2026-09-17, see the naming decision at the top).

## 2026-08-23 — Criteria at root, decisions in docs

`CRITERIA.md` is the contract (criterion, expected behaviour, evidence).
Dated lab notes live in `tests/red/`. Binding choices live in this file.

## 2026-08-23 — English on ports, Dutch handbook until a dedicated pass

Root ports a stranger opens first — `SKILL.md`, `README.md`,
`INSTALL.md`, `CRITERIA.md`, `install.sh` — are English (A8).
`references/agent-handbook.md` and the work-rule block printed by
`bin/toon-annotaties.py` stay Dutch until a dedicated translation.
The Dutch CLI filenames in `bin/` stay: they are the same class of
identifier as `LUC_ANNOTATOR_*`. (Superseded in part on 2026-09-17: the
CLI itself is `python -m html_annotator`, the `bin/` files are wrappers,
and the todo-list script was deleted with the scope pass.) `INSTALL.md`
stays a port, not a file in `bin/`.

## 2026-08-28 — Draft cards are rich text; the diff stays on the plain-text projection

`.la-draft-txt` renders as the recipient will see it: paragraphs, bulleted
and numbered lists, bold, italic and links. The allowed set is exactly
`p, ul, ol, li, b, i, a, br` — the intersection Outlook, Gmail and Teams
render without interpreting anything of their own. Reading the card back
into the block model *is* the sanitizer: anything else is flattened to
text, and paste is always plain text.

The tracked changes did **not** move to HTML. Two channels:

- **text** — diffed word-level on the plain-text projection of the card:
  the exact text a plain-text mail would carry, with no formatting
  sigils (`- `, `**`) in it. Hunks keep their shape
  (`voor/na/verwijderd/toegevoegd`), so anchoring, reload replay and
  `pas-hunk-toe.py` keep working unchanged.
- **formatting** — its own hunks, `soort: "opmaak"`, saying what happened
  to a block ("alinea werd opsomming", `vet aan op "issue"`).

Why not sigils in the projection: a reviewer types `- ` himself, so a
sigil cannot be told apart from content, and it would push every
formatting change through the word diff as noise. Why not diff the HTML:
the anchors would stop being findable in the page source.

Consequences accepted:

- A text hunk's anchor is clamped to its own block, because in the source
  a block boundary is a tag. An anchor that still runs through inline
  markup (`<b>`, `<a>`) is reported as MISLUKT by `pas-hunk-toe.py`
  rather than placed — never a silent wrong edit.
- `pas-hunk-toe.py` does not apply formatting hunks; it names them and
  points at `nieuwHtml`.
- A block whose text *and* formatting changed reports only the text hunk.
  `nieuwHtml` on the annotation is the complete new version and is the
  ground truth in that case.
- A card the agent wrote as plain text stays plain text (pre-wrap,
  `plaintext-only`) until the reviewer uses a formatting button. Then the
  whole card converts to blocks in one step — half-converting would
  collapse the remaining hard line breaks.

## 2026-08-29 — LA-SUGGEST als laag in het annotator-snippet, niet als los component

Suggested changes (agent wijzigt de pagina, reviewer accepteert/wijst af per
stuk) begonnen als eigen snippet met eigen highlight, pill en popup. Drie
iteraties lieten zien dat elke eigen implementatie (cel-gebonden knoppen,
gele mark, zelf positioneren in sticky tabellen) opnieuw de problemen opriep
die de annotator al lang had opgelost. Besluit: de laag leeft ín
annotator-snippet.html en hergebruikt letterlijk de annotatie-mechaniek —
la-rect-selecties (tekstregels voor tekst, één regiokader voor visuals), de
badge breed uitgetrokken tot pill met ✕ ✓ ✎, en voor ✎ de echte popup via
`HtmlAnnotator.openComposer` (chips incluis). Beslissingen zijn status
(state.json, component `suggest`), geen annotaties. `references/
suggest-snippet.html` is een deprecatie-pointer; niet meer inplakken.

## 2026-08-31 — Een LA-SUGGEST-change is te bewerken; pending wist de tekst niet

Bug: na ✎ + tekst + save kon de reviewer zijn eigen suggestie niet meer
bijschaven. Het oranje ✎-badge draait de keuze terug naar pending, en dat
deed `sugSave(elm, "pending", "")` — met een leeg `comment` en zonder
`refs`/`commentExpanded`, dus de getypte zin werd zowel in `sugState` als in
`state.json` overschreven. De volgende popup opende leeg.

Besluit: terugklikken naar pending is nog steeds terugklikken (de badge-flow
blijft), maar het bewaart de change-tekst, chips incluis. `sugPopup` vult het
commentveld met wat er in `sugState` staat — dat komt bij het laden uit
`POST /state`, dus de voorvulling overleeft een reload. Een al `processed`
entry telt daarbij als leeg. Bij `accepted`/`rejected` valt de tekst juist
weg: een verwerkende agent hoort geen dode change-comment op een accepted key
te vinden. En een voorgevuld commentveld zet de cursor achter de tekst in
plaats van ervoor — dat gold ook al voor het bewerken van een gewone
annotatie. Bewijs: `tests/case-14-suggest-change-bewerken.mjs`.

## 2026-08-31 — De LA-SUGGEST-laag hertekent bij zichtbaarheid, en één key is één pill

Twee bugs uit de KPI-pagina's van een klantproject, allebei in de LA-SUGGEST-laag.

**Verborgen rijen kregen geen pill.** De suggest-rijen zaten in ingeklapte
tabelgroepen (`collapsed-hide`) en dus zonder rect bij het tekenen; de laag
sloeg ze over. Uitklappen leverde geen hertekening op: de ResizeObserver kijkt
naar `document.body`, en die groeit niet als de tabel in zijn eigen
`overflow:auto`-scroller onder een `overflow:hidden`-body zit. Pas een andere
interactie (een annotatie plaatsen) liet de pills alsnog verschijnen. Besluit:
generiek meeliften op DOM- en zichtbaarheidswijzigingen — een MutationObserver
op `documentElement` (`childList` + de attributen `class`/`style`/`hidden`/
`open`) die de bestaande debounced `herteken()` aanroept, niet iets specifieks
voor deze inklapknoppen. Om te voorkomen dat de laag zichzelf aan de gang
houdt, gooit `render()` aan het eind zijn eigen mutatierecords weg
(`takeRecords`); filteren op klassenaam is te laat, want `el()` hangt de div
eerst in de body en zet de `la-`class er daarna pas op. Bewijs:
`tests/case-15-suggest-zichtbaar.mjs`, inclusief een rustmeting die een
render-lus zou betrappen.

**Eén key besliste stiekem over vijf rijen.** In de HTML van dat project deelden een
work-item-rij en zijn subtaakrijen dezelfde key (`wi-1042` op vijf rijen). De
laag tekende per element een pill, maar de beslissing gaat per key naar
`state.json` — vijf knoppen die samen één beslissing waren. Besluit: één key is
één suggestie, dus `renderSuggesties()` groepeert per key: alle rects van alle
elementen met die key worden gehighlight als één groep, met precies één pill.
Wat je ziet is dan wat er gebeurt. Wie per rij wil beslissen geeft elke rij een
eigen key (parent `wi-<id>`, subtaken `wi-<parentid>-<subid>`); zo staan de
live pagina's nu ook. Bewijs: `tests/case-16-suggest-gedeelde-key.mjs` en
`tests/case-17-suggest-losse-keys.mjs`.

Neveneffect in de suite: de mutant in `case-12` (snippet zonder scroll-listener
moet blijven plakken) sloeg om, omdat het plaatsen van de testannotatie zelf de
DOM muteert en de debounced hertekening dan ná de scroll viel. De mutant wacht
nu eerst 400ms uit; hij blijft daarmee aantoonbaar plakken en meet nog steeds
het ontbreken van de scroll-listener.

### Wat de falsificatieronde van 31-08-2026 aan die twee fixes veranderde

Twee onafhankelijke falsifiers vonden drie gaten die er toe deden, allemaal
verholpen voor de uitrol:

- **De debounce was uit te hongeren.** Nu elke mutatie `herteken()` voedt, kan
  een pagina die zichzelf per frame aanraakt (een rAF-animatie die een style
  zet) de timer eindeloos resetten: er wordt dan nooit getekend en de pill
  blijft weg — hetzelfde symptoom als de bug zelf. De debounce heeft daarom een
  plafond van 250ms: langer dan dat wachten we niet. Bewijs: assertie 5 in
  `case-15`, die rood wordt op een snippet zonder plafond.
- **De pill van een groep stond bij de verkeerde rij.** Hij hing aan het laatste
  rect van de hele groep, terwijl zijn tekst en popup van het eerste element
  komen: op een cluster van vijf rijen stond de knop naast de laatste subtaak.
  Het eerste element in documentvolgorde draagt nu de pill.
- **Een lege `data-la-suggest=""` voegde losse suggesties samen.** Een lege key
  groepeert niet meer.

Blijvende grens, bewust: de laag kijkt naar DOM-wijzigingen en naar de
attributen `class`, `style`, `hidden`, `open`. Een in- en uitklap die puur in
CSS gebeurt (`input:checked ~ tabel`) verandert geen attribuut en levert dus
geen hertekening op; dat staat als voorwaarde in het handboek. Een periodieke
sanity-render zou dat dekken, maar kost stroom op elke pagina en is voor de
KPI-pagina's (die `classList.toggle` gebruiken) niet nodig.

## 2026-09-26 — Bridge: origin-allowlist, /p/ zonder CORS en zonder dotfiles

Aanleiding: `GET /p/.zshrc` gaf 200 met `Access-Control-Allow-Origin: *`,
dus elke website kon via `fetch("http://127.0.0.1:8791/p/...")` bestanden
onder home lezen (`~/.ssh`, `.env`), afhankelijk van de browser. Ook de
POST-routes hadden CORS `*`.

- `/p/` stuurt geen CORS-headers meer; de pagina is same-origin.
- `/p/` serveert alleen html/htm, css, js, afbeeldingen en json, en weigert
  elk pad met een onderdeel dat met `.` begint, ook na het volgen van een symlink.
- Elk verzoek met een `Origin` buiten de allowlist is 403 vóór de handler.
  CORS alleen beschermt het antwoord; een `no-cors`-POST zou anders nog steeds
  schrijven of `/sessie` een `claude://`-prompt laten openen.
- Allowlist, afgeleid uit de origin-log (`bridge.log`, 2026-08-18 → 09-26):
  loopback op elke poort (de /p/-pagina's zelf, testbridges, dev-servers als
  `localhost:8931`), `file://` en `null` (pagina als bestand geopend: ~1.500
  verzoeken met `null`). Geen Origin (curl, hooks) blijft toegestaan.
- `Host` moet een loopback-naam zijn, tegen DNS-rebinding.

Restrisico, bewust: `null` blijft toegestaan omdat file://-pagina's in Chrome
dat sturen. Een website kan `null` ook sturen vanuit een sandboxed iframe en
dan de POST-routes aanroepen (niet `/p/` lezen). Chrome vraagt daarvoor
Local Network Access-toestemming; Safari/Firefox mogelijk niet. `null` dicht
kan zodra file://-gebruik weg is (levering via `/p/`, zie 2026-08-18).

## 2026-09-26 — Verstuur-knop: klik plus confirm is akkoord, eerst alleen WhatsApp

Besluit van de reviewer: een klik op Verstuur op een la-draft-kaart plus het
bevestigingsvenster telt als akkoord op de exacte tekst en ontvanger. De controle zit
niet in het model maar in een PreToolUse-hook die over de echte tool-argumenten hasht;
zonder match `ask`, zodat het chatpad blijft werken. Een PostToolUse-hook verbruikt het
akkoord na verzending. Alleen WhatsApp, omdat daar de platte-tekstprojectie van de kaart
één op één de body is; Teams en mail versturen HTML. De ontvanger op de kaart is de
letterlijke tool-waarde, niet een naam, want de hash zit erover. Onderzoek, tests en
livegang: `docs/verstuur-knop-onderzoek.md`.

## 2026-09-26 — Hooks in settings.json; bevestiging inline

`~/.claude/settings.local.json` laadt niet in een sessie met een andere cwd dan `~` (livetest: gate,
nastap én de SessionStart-bridge-hook draaiden niet vanuit `~/Desktop`). `install-hooks` schrijft
daarom naar `~/.claude/settings.json`. De bevestiging na Verstuur is geen `window.confirm()` meer
maar een inline "Zeker? [Nee, cancel] [Ja, verstuur]" onder de knop, zodat hij ook in de Claude
Desktop-sideviewer werkt (gemeten: die laadt de `/p/`-pagina niet in een frame).
