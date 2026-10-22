# Decisions

Choices a later cleanup must not reopen without the owner.
Changing behaviour is a new decision, not an edit here.

## 2026-10-21 — A live snapshot is client input: sanitised, served over /snap/ only, own origin only

Trigger: review of the 2026-10-09 live crop. The snapshot HTML came from the
client and went to Chrome unsanitised; the CSP meta was inserted after the
first `<head…>` match (so markup in front of it ran outside the policy); a
`file://` page's snapshot was rendered as a `file://` document with
`--allow-file-access-from-files`; and `/save` with Origin `null` (any
sandboxed iframe, any `file://` page) was rendered too.

**Decision, defence in depth.**
1. The bridge sanitises every snapshot itself (`schoon_snapshot`): it
   rebuilds the document from parser tokens and drops `script`, `noscript`,
   `iframe`, `frame(set)`, `object`, `embed`, `applet`, `portal`, `base`,
   `<meta http-equiv>`, comments, `on*` attributes, `srcdoc` and
   `javascript:`/`vbscript:` URLs; text and attribute values are re-escaped;
   `<` inside `<style>` becomes the CSS escape `\3c `; password fields are
   masked (also done by the snippet).
2. One function (`bereid_snapshot`) owns sanitiser, nonce and CSP. The CSP
   goes out as an HTTP header on `/snap/<token>`, so it governs the whole
   document: `default-src 'none'`, `script-src` only the nonce of the
   restore script, `connect-src 'none'`, no frames/objects/forms; styles,
   images, fonts and media from the bridge's own origins, `https:` and
   `data:`. No meta CSP any more.
3. A snapshot is never rendered as a `file://` document and Chrome never
   gets `--allow-file-access-from-files` for it; only the file crop (the
   page file itself, unchanged behaviour) keeps that flag.
4. Only a `/save` whose Origin is the bridge's own origin (a `/p/` page,
   `http://127.0.0.1:<port>` or `http://localhost:<port>`) is live-rendered.
   Origin `null`, another loopback port, or no Origin (curl, CLI): the
   snapshot is ignored, the crop comes from the page file and
   `liveCropError` says why. The snippet does not even take a snapshot off
   `/p/`. Consequence: a page opened as `file://` gets the file crop again.

Same round: the crop runs outside the global LOCK (only reading and writing
the JSON are under it), a new crop goes to a temp file and replaces the old
one only when it succeeded, an existing crop is kept when a new one fails,
the render viewport is always the reviewer's (a selection outside it is
reached by scrolling; one larger than the viewport falls back to the file
crop), and Chrome is waited for, then stopped with its whole process tree
before the profile is removed; only a complete PNG counts.

**Rejected.**
- Keeping the `file://` route for `file://` pages with a tighter CSP: the
  document would still have a `file://` origin, and the flag would still be
  needed for its assets.
- Treating requests without Origin as trusted for live rendering: the
  snippet always sends Origin on a POST, so nothing legitimate needs it.
- A regex sanitiser: tag soup and parser differentials make it unreliable;
  rebuilding from tokens only writes out what was checked.

## 2026-10-09 — The crop comes from a live DOM snapshot, not from the page file

Trigger: a region selection over an expanded `<details>` gave a crop with
the toggle closed.

**Mechanism, checked.** The crop is made at save time: `h_save` →
`maak_crop` → `volledige_shot`, synchronously in the `/save` request. That
loaded the page file freshly in headless Chrome at `--window-size=<doc.w>,<doc.h>`
and cut the rect out. Everything not in the file was lost: `<details open>`,
scroll positions of containers and window, filled-in fields, state set by
scripts; a `position:fixed` header sat at the top of the document instead
of the top of the view.

**Decision.** At the selection (mouseup, before the popup opens) the snippet
takes a snapshot: `documentElement.cloneNode(true)`, with live state that is
not an attribute written onto the clone (`value`, `checked`, `selected`,
`textarea`, `data-la-snap-scroll` for scrolled elements, canvas → `<img>`,
CSSOM rules of empty `<style>` tags and adoptedStyleSheets), scripts and
`on*` attributes removed, annotator UI removed, `<base href=document.baseURI>`,
doctype in front. Plus `clientWidth/clientHeight`, `scrollX/Y` and
`devicePixelRatio`. The snapshot goes once with `/save` of a new region and
lives in memory only (never localStorage). The bridge renders it in an
iframe the size of the reviewer's viewport, with its own restore script
(CSP with a nonce: only that script runs, no network from script) that puts
the scroll positions back; animations and transitions are off. The record
says `cropSource: "live"`; without a snapshot the old route stays as
`cropSource: "file"`.

Why an iframe: Chrome's `--screenshot` captures the document from (0,0) and
does not paint what is scrolled away; a scrolled window gave a white crop
(measured). In an iframe the snapshot scrolls inside its own viewport, which
is in view. Why `/snap/` through the bridge: same origin as `/p/`, so fonts
(CORS) and CSS load; a `file://` page gets a temporary file, because an http
document may not load `file://` assets. DPR is followed (max 2).

Same change: the screenshot browser gets its own throwaway profile and
`--use-mock-keychain --password-store=basic`. Without that, Chrome on macOS
asked for the "Chrome Safe Storage" keychain item during crops. With an
explicit `--user-data-dir` Chrome does not always exit after `--screenshot`,
so the bridge ends it once the file is written and stable.

**Rejected.**
- `getDisplayMedia` / screen capture in the page: real pixels, but a
  permission prompt every session, does not work in a sandboxed or embedded
  viewer, and captures the annotator UI.
- A DOM-to-canvas library: breaks "no libraries/CDN" and only approximates
  CSS; Chrome renders the snapshot exactly.
- Sending the state as a recipe (which details open, which scroll) and
  replaying it on the file: covers only what is thought of in advance; JS
  state falls outside.
- CDP (`--remote-debugging-pipe`) for a real viewport screenshot: works, but
  is a protocol client in stdlib for what the iframe wrapper also solves.

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
The personal memories folder (kept outside the repo) was removed (the plan said move). Source: this
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

## 2026-10-12 — Poort, bind-adres en pagina-root per gebruiker instelbaar

Aanleiding: een gebruiker draait de bridge in Docker binnen WSL op Windows
(0.0.0.0 nodig, pagina's op een mount), en de skill moet bij een heel team
installeerbaar zijn zonder handwerk, ook als 8791 al bezet is.

- **Configbestand per gebruiker**, `~/.config/html-annotator/config.json`
  (`$XDG_CONFIG_HOME` gerespecteerd; Windows `%APPDATA%\html-annotator\`),
  optionele sleutels `port`, `host`, `pages_root`. Voorrang: env
  (`HTML_ANNOTATOR_*`, plus de bestaande `LUC_ANNOTATOR_*`-aliassen) >
  configbestand > standaard (8791, 127.0.0.1, home). `config.port()`,
  `host()` en `pages_root()` zijn de enige bron. Kapot bestand: negeren met
  een waarschuwing op stderr; een configfout mag de bridge niet tegenhouden.
- **`pick-port`** probeert 8791–8890 door echt te binden op het ingestelde
  bind-adres (en meteen los te laten) plus een connect-check; eerste vrije
  wint. Een poort waarop onze eigen bridge antwoordt (`/ping` →
  `"bridge": "html-annotator"`) telt als goed, en de al geconfigureerde
  poort blijft staan als onze bridge daar draait, zodat een herhaalde
  pick-port geen draaiende bridge wees maakt. Alles bezet: de OS kiest
  (bind op 0). Schrijft alleen `port`, atomisch, andere sleutels blijven.
  `--port N` valideert 1–65535 en waarschuwt alleen bij een vreemde
  bezetter. De reeks is in tests te verleggen met
  `HTML_ANNOTATOR_PORT_RANGE`; dat is een test-hook, geen gebruikersinstelling.
- **`ensure` wijkt nooit stil uit.** Bezet door iets anders dan de bridge:
  exit 1 met de poort en "run `python -m html_annotator pick-port`".
  Stil uitwijken zou de URL's in al uitgedeelde links en open tabbladen
  ongeldig maken zonder dat iemand het merkt. Een bridge die nog opstart
  telt als de bridge (ensure wacht op zijn `/ping`). De melding is Engels,
  zoals alle CLI-uitvoer sinds 2026-09-17.
- **Bind-adres opt-in** via `HTML_ANNOTATOR_HOST` / `host`. Alleen de socket
  verandert: `base_url()`, de URL's van `url`, de ping en de eigen origins in
  de bridge blijven 127.0.0.1/localhost op de actuele poort (0.0.0.0 in een
  URL werkt niet, en de bridge zou zijn eigen pagina's weigeren). Bij een
  niet-loopback-adres logt de bridge een `WARNING`. Host- en Origin-check
  blijven alleen loopback toelaten (2026-09-26).
- **Pagina-root** via `HTML_ANNOTATOR_PAGES_ROOT` / `pages_root`, standaard
  home. `/p/` en `python -m html_annotator url` gebruiken allebei
  `config.pages_root()`. De bestaande regels gelden ten opzichte van die
  root: niets erbuiten, geen dotfiles of dot-mappen (ook niet via symlink),
  alleen de types uit `P_SOORTEN`. De bridge leidt het bestand van een
  `/p/`-pagina af uit de URL en de root, omdat het snippet als `pageFile`
  `~/<pad>` stuurt, wat alleen klopt zolang de root home is.
- **Agents bouwen geen URL meer zelf**: altijd `url <bestand>` of
  `url --base` (nieuw). 8791 blijft de standaard en staat zo in de docs.
- **file://-fallback**: annotator- en checklist-snippet praten via `/p/` met
  `location.origin`; als bestand geopend vallen ze terug op
  `http://127.0.0.1:8791`. Best effort: Chrome blokkeert file:// naar
  loopback toch al (Private Network Access); de route blijft `/p/`.
- **Na de weerleggingsrondes (zelfde dag).** `pick-port` overschrijft een
  kapot configbestand niet meer (eerder las `write_config` het als `{}` en
  schreef dan alleen `port` terug: andere sleutels weg); lezen voor de bridge
  blijft wel tolerant. `write_config` draait onder een lock
  (`config.json.lock`), want gelijktijdige schrijvers verloren sleutels (12
  van 20 in een proef). `ensure` draait onder een lock per poort in de
  state-dir en schrijft het pid-bestand pas als het gestarte proces zelf op
  `/ping` antwoordt (`/ping` geeft nu `pid`): eerder wees het pid-bestand
  soms naar het verliezende, al gestopte proces en loog `stop`. Gekozen
  boven "de bridge schrijft zijn eigen pid-bestand", omdat dan ook een met
  de hand gestarte `serve` door `stop` geraakt zou worden. De lockfiles
  blijven staan: weghalen is racy. Herkenning van de eigen bridge accepteert
  ook de oude naam `luc-annotator`, anders gaf een nog draaiende oude bridge
  na een update "taken … pick-port". De `/p/`-afleiding van het paginabestand
  geldt alleen nog voor eigen http(s)-URL's (loopback, eigen poort).
- **Geen persoonlijke data in de repo.** Een gate-uitzondering voor één
  ondertekend groepsbericht loopt alleen via de
  optionele config-sleutel `signed_group_message` (zonder sleutel: geen
  uitzondering). De lijst met mailservers in de gate is generiek
  (`ms365` of `ms365-<naam>`): de afzender zit in de hash, de server niet, en
  een server buiten de oude lijst kreeg voorheen helemaal geen oordeel.
  Testdata, voorbeelden en docs gebruiken verzonnen namen en adressen.

## 2026-10-14 — Container zonder root en zonder init

Aanleiding: de bridge in een container die als gewone gebruiker draait met
alle capabilities weg (`--cap-drop=ALL`) en `sleep infinity` als PID 1.

- **`--no-sandbox` opt-in** via `HTML_ANNOTATOR_CHROME_NO_SANDBOX` /
  `chrome_no_sandbox`, zoals het bind-adres. Chrome vindt daar geen bruikbare
  sandbox en stopt; de screenshot ontbreekt dan. Niet automatisch bij
  "draait in een container": de browser rendert alleen eigen lokale pagina's,
  maar zonder sandbox is de container de enige grens, en dat kiest de
  eigenaar. Alleen de sleutel `true` telt, zodat een tikfout niet stil aan
  zet. Een wrapper-script rond chromium kan hetzelfde, maar is per machine
  handwerk buiten de skill.
- **Zombie telt als gestopt.** `pid_alive()` keek met `kill(pid, 0)`; dat
  slaagt ook voor een proces dat al gestopt is maar nog niet opgeruimd. De
  bridge start losgekoppeld, dus na `stop` ruimt PID 1 hem op, en dat doet
  `sleep infinity` nooit. Op Linux leest `pid_alive()` nu ook de status uit
  `/proc/<pid>/stat`. De zombie zelf kan de skill niet opruimen; daarvoor is
  `docker run --init`.
- **Annotatiemap ook in het configbestand** (`root`), naast
  `HTML_ANNOTATOR_ROOT`. In een container met de pagina's op een mount wil
  je de rondes daar ook, en met alleen een env-variabele stonden de
  instellingen op twee plekken. Zelfde voorrang als de andere sleutels.

## 2026-10-20 — Agenda slepen en een endpoint-meta voor elders gepubliceerde pagina's

- **Wie sleepte is een parameter.** De sync-notitie "door <naam> verplaatst
  van X naar Y" haalt de naam uit `--by`, anders uit het overlayveld
  `movedBy`, anders `reviewer`. Een vaste naam in de code past niet bij een
  generieke skill; een overlayveld laat een agent het per pagina één keer
  zetten, de vlag wint voor een losse run.
- **State per voorstel draagt een `base`.** De pagina schrijft naast de nieuwe
  tijd ook de overlaytijd waar de sleep van uitging. Laden en sync passen de
  state alleen toe zolang de overlay nog die tijd heeft; heeft de agent het
  voorstel intussen zelf verzet, dan wint de overlay en meldt de sync dat.
  Verstuurde of vervallen voorstellen volgen de echte agenda en worden nooit
  door een oude sleep verzet.
- **De agenda-pagina zoekt de bridge zoals het snippet:** via `/p/` de eigen
  origin, anders de standaardpoort. Een vaste `127.0.0.1:8791` zou op een
  machine met een andere poort stil "bridge uit" tonen.
- **`html-annotator-endpoint` in plaats van een productnaam.** De meta is een
  algemeen contract (zelfde routes en antwoorden als de bridge), niet gebonden
  aan één deelserver. Alleen `http(s)`, en op `/p/` genegeerd: de lokale
  bridge blijft leidend waar hij bereikbaar is, en een meta met
  `javascript:` of een relatief pad kan de schrijfroute niet kapen.

## 2026-10-21 — Review-ronde agenda en endpoint: één bron voor de schrijfroute

- **De endpointkeuze staat op één plek: blok `LA-BRIDGE-KEUZE` in het
  annotator-snippet** (route plus pagina-identiteit: `slug()`,
  `paginaBestand()`). Er waren drie kopieën (annotator, checklist, agenda) en
  die liepen al uiteen. De agenda-pagina plakt het blok bij het bouwen
  letterlijk in (`agenda-preview.py` leest het uit het snippet): geen kopie in
  de repo en het werkt ook zonder snippet op de pagina (`--no-snippet`). Het
  checklist-snippet is een los plakblok dat vóór het annotator-snippet staat;
  het vraagt de route bij elk verzoek op via `HtmlAnnotator.bridgeRoute()` en
  laadt zijn state pas na `DOMContentLoaded`. Alleen als de annotator niet op
  de pagina staat valt het terug op een korte kopie van dezelfde regel; dat is
  de enige overgebleven duplicatie, gekozen omdat de checklist los moet kunnen
  werken. Case-26 test beide paden. Verworpen: een apart gedeeld scriptbestand
  (pagina's zijn zelfstandige HTML zonder externe bestanden) en de checklist
  laten afhangen van de annotator (dan schrijft een losse checklist nergens).
- **"Een `/p/`-pagina van de bridge" betekent loopback-host én `/p/`-pad**
  (`127.0.0.1`, `localhost`, `[::1]`), zoals het handboek al zei. Alleen het pad
  controleren liet een elders gepubliceerde pagina met `/p/` in de URL naar
  zijn eigen origin schrijven in plaats van naar het endpoint.
- **De agenda stuurt de slug van het `-o`-bestand mee**, met dezelfde velden
  als het snippet (`page`, `pageFile`, `slug`, `title`). Buiten `/p/` (lokale
  dev-server, preview-pane) is er geen `pageFile`, en de titel-slug van het
  snippet wijkt af van wat de sync zoekt; de bestandsslug laat beide routes in
  dezelfde `state.json` uitkomen.
- **Sync markeert een verwerkte sleep met `base` = de nieuwe tijd**, via
  dezelfde bridge-route (`/state-save`, zonder bridge de handler zelf op
  schijf). Een entry met start = base is geen verplaatsing; zet de agent het
  voorstel later bewust terug, dan komt de oude sleep niet terug, niet op de
  pagina en niet in de volgende sync. Gekozen boven een aparte `synced`-vlag:
  de pagina kent `base` al, een vlag zou de pagina-logica moeten uitbreiden.
  Prijs: tussen sync en opnieuw renderen toont een herladen oude pagina de
  oude overlaytijd; het handboek zegt al direct na de sync te renderen.
- **De sync gebruikt de status zoals de pagina hem toont** (de `agenda-data`
  van het gebouwde bestand), naast de overlay-status. Build leidt "verstuurd"
  af uit een echt event met dezelfde titel en start; de overlay weet dat niet,
  dus alleen de overlay lezen gaf een spookdubbel. Daarom weigert de sync ook
  een paginapad dat niet bestaat: raden gaf de state van een andere pagina.
- **Geen eigen slug- en state-regels in `agenda-spec.py`**: zonder bridge
  roept de sync `bridge.h_state` / `bridge.h_state_save` rechtstreeks aan, en
  `agenda-preview.py` gebruikt `bridge.slugify`. `bin/agenda-sync.py` is weg:
  een alias die alleen doorstuurde was een tweede naam voor hetzelfde.
- **Opslaan per voorstel: één verzoek tegelijk, de laatste stand wint.** Een
  trage bridge kon een oudere tijd na een nieuwere wegschrijven. Laden van de
  state schrijft niet over een blok dat de reviewer al verzette en rendert
  niet midden in een sleep (dan verdween het gesleepte blok onder de pointer);
  het rendert na het neerzetten.
- **De agenda-pagina is Engels**, ook de notitie "moved by <naam> from X to
  Y", net als de pil en de knoppen van het snippet. De statuswaarden in de
  overlay (`open|verstuurd|vervallen`) blijven data en dus ongewijzigd.
