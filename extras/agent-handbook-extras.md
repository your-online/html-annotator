# Handbook extras (not part of the skill)

These three parts were removed from `references/agent-handbook.md` in the
F0 scope pass: they describe the author's personal workflow (spawning tasks
from an HTML todo list) or components whose agent-facing rules are not part
of the core contract (the draft message card `la-draft`, the nested
sub-points `la-sub`). The CSS and JS for `la-draft` and `la-sub` still ship
inside `references/annotator-snippet.html` — the snippet stays one paste
block — so a page that uses them keeps working. Only the documentation and
their Playwright cases moved here. See `docs/SCOPE.md`.

The todo-list script `bin/vind-todolijst.sh` was deleted, not moved: it was
pure personal glue. The part below still refers to it.

## Deel 5: taken spawnen vanaf de todolijst

Vraagt de reviewer om een taak te spawnen (`spawn_task`), dan hangt die altijd aan een punt op
zijn HTML-todolijst, en het nummer van dat punt hoort in de sessietitel. De volledige
conventie staat in de skill **`task-spawnen`** — lees die voordat je spawnt; hier staat
alleen wat je moet weten om er te komen.

**Zoek de lijst, onthoud hem niet.** Het bestand verhuist en wordt hernoemd, dus nooit
een pad uit je hoofd of uit een eerder gesprek:

```bash
~/.claude/skills/html-annotator/bin/vind-todolijst.sh        # pad
~/.claude/skills/html-annotator/bin/vind-todolijst.sh -v     # met hoogste nummer erbij
```

Het script kiest de meest recent gewijzigde HTML op het bureaublad die genummerde punten
heeft (`<span class="num">`) én zich als todolijst laat herkennen. Vindt hij niets, dan
verzin je er geen: vraag het de reviewer.

Daarna, in het kort — de details en de reden erachter staan in `task-spawnen`:

1. Zoek het punt waar de taak bij hoort en pak zijn nummer. Bestaat het nog niet, maak
   het dan eerst aan op de lijst, met een nummer dat één hoger is dan het hoogste in het
   **hele** bestand (de prioriteitsbanden delen één doorlopende reeks).
2. Noem de sessie `XX.YY-kebab-case-naam`, met twee cijfers per segment.
3. Zet in de meegegeven prompt dat de gespawnde sessie zichzelf aan het eind hernoemt
   naar `[DONE]-<titel>`.

## Deel 6: de concept-berichtkaart

Een conceptbericht (mail, Teams, WhatsApp) dat nog niet verstuurd is, hoort niet
als platte tekst in de chat maar als kaart in de HTML. Dan kan de reviewer de tekst zien
zoals de ontvanger hem krijgt, en er met de annotator per zin op reageren.

De CSS zit in `references/annotator-snippet.html`, dus elke pagina met het snippet kan het
component gebruiken zonder eigen opmaak. Klassen hebben de `la-`-prefix, net als
de rest van de annotator, en zijn vlak (`la-draft-hdr` in plaats van
`.la-draft .hdr`) zodat een pagina-eigen `.hdr`, `.txt` of `.na` er niet mee
botst. `--ink` en `--muted` worden gebruikt als de pagina ze definieert, met een
fallback als dat niet zo is.

```html
<h2>Mail-concepten <span class="count">1</span></h2>
<p class="lead">Nog niet verstuurd. Annoteer gerust in de tekst zelf, dan pas ik aan.</p>

<div class="la-draft">
  <div class="la-draft-hdr"><b>Aan:</b> Alex Jansen &nbsp;·&nbsp; <b>Cc:</b> Sam de Vries &nbsp;·&nbsp; <b>Onderwerp:</b> Even bijpraten over security</div>
  <div class="la-draft-txt">
    <p>Hi Alex,</p>
    <p>Eerste alinea van het bericht.</p>
    <ul>
      <li>Alex: schiet het issue in bij <a href="https://…/pbi/1234">PBI 1234</a></li>
      <li>Ik: stuur de opzet door</li>
    </ul>
    <p>Groet,<br>de reviewer</p>
  </div>
  <div class="la-draft-na">Openstaand: welk issue heb je ingeschoten? Zodra je dat zegt maak ik de eerste zin concreet.</div>
</div>
```

**Rich text.** De kaart toont het bericht zoals de ontvanger het krijgt: alinea's,
opsommingen, vet, cursief en links. Het toegestane setje is klein en mail-veilig —
`p`, `ul`, `ol`, `li`, `b`, `i`, `a`, `br` — precies de doorsnede die Outlook, Gmail en
Teams zonder eigen interpretatie renderen. Wat je er verder in zet wordt bij het inlezen
platgeslagen tot tekst; plakken gaat altijd als platte tekst. Er is geen bibliotheek en
geen CDN in het spel: het snippet blijft één bestand.

De reviewer heeft onder elke kaart een balkje met **B**, *I*, link, • en 1. (en ⌘B / ⌘I /
⌘K). Een kaart die je als platte tekst schreef blijft platte tekst — pre-wrap,
`plaintext-only` — tot hij zelf een opmaakknop gebruikt; dan gaat de héle kaart in één
keer over op blokken. Half omschakelen zou de overgebleven harde regelovergangen op één
hoop gooien.

**Tracked changes.** Elke `la-draft-txt` is direct bewerkbaar: de reviewer klikt in de tekst,
de cursor staat waar hij klikte, en hij typt. Er is bewust geen knop om "de bewerkmodus
aan te zetten" — dat was een drempel voor iets wat hij gewoon wil kunnen doen. Klikt hij
eruit, dan gaat de bewerking als annotatie van `type: "edit"` naar de bridge; de kaart
blijft de kale, herschreven tekst tonen. Het verschil met de oorspronkelijke tekst
(doorhaling en onderstreping, in de opgemaakte kaart, dus een gewijzigde bullet blijft een
bullet) verschijnt alleen op verzoek via de knop "Show changes" in de bar, en verdwijnt
weer met "Hide changes" of door in de tekst te klikken. Bewust niet automatisch bij het
eruit klikken: dat sprong in het gezicht van wie gewoon aan het herschrijven was. Dat is vaak sneller dan een
comment: in plaats van uitleggen wat er anders moet, schrijft hij het gewoon anders op.
"↺ Herstel origineel" zet de kaart terug en verwijdert de bewerking.

Er wordt **niet op de HTML gedift maar op de platte-tekstprojectie** ervan: precies de
tekst die in een plain-text mail zou staan, zonder opmaakmarkeringen erin. Opmaak is een
eigen kanaal. Dat levert twee soorten blokken op:

- `soort: "tekst"` — de vertrouwde hunk met `voor` / `na` / `verwijderd` / `toegevoegd`.
  Het anker blijft binnen zijn eigen blok, want tussen twee blokken staat in de bron een
  tag. `pas-hunk-toe.py` plaatst deze blokken gewoon.
- `soort: "opmaak"` — "alinea werd opsomming", `vet aan op "issue"`. Die staan per
  definitie niet in de tekst, dus `pas-hunk-toe.py` raakt ze niet aan en zegt dat ook:
  die neem je over uit `nieuwHtml`.

Wijzigden tekst én opmaak in hetzelfde blok, dan zie je alleen het tekstblok.
`nieuwHtml` op de annotatie is dan de grondwaarheid: dat is de volledige nieuwe versie,
mail-veilig, klaar om als body te gebruiken.

Meerdere wijzigingen in dezelfde kaart worden losse blokken, genummerd in de tekst (¹ ² ³)
zodat de reviewer en jij hetzelfde blok bedoelen. Je kunt ze los doorvoeren en los afvinken; wat
nog openstaat blijft na een reload zichtbaar, herplaatst op zijn anker in de tekst zoals
die dan is.

Klikt hij terug in een tekst waar de opmaak zichtbaar is, dan wordt de klikpositie
omgerekend naar de kale tekst voordat de cursor gezet wordt. Zonder dat sprong de cursor,
want de doorgehaalde tekst verdwijnt bij het terugschakelen en de regel loopt dan anders.

Een bewerking krijgt bewust géén badge en komt niet in de weeslijst: hij is al zichtbaar
in de kaart zelf. Na een reload wordt hij teruggezet, gekoppeld op de kop van de kaart.
Is de concepttekst zelf ongewijzigd, dan komt de bewerkte versie compleet terug, opmaak
incluis. Is de tekst wél veranderd sinds de bewerking, dan worden alleen de openstaande
blokken op hun anker herplaatst en meldt het snippet wat het niet meer terugvond.

Regels bij het gebruik:

- Schrijf de berichttekst in blokken: `<p>` per alinea, `<ul>`/`<ol>` met `<li>` voor
  opsommingen, `<br>` voor een harde regelovergang binnen een alinea. Alleen die tags,
  plus `<b>`, `<i>` en `<a href>`. Geen `style`, geen `<div>`, geen tabellen.
- Streepjes-als-bullet (`- Alex: …` als gewone tekstregel) zijn geen opsomming meer.
  Wil je een opsomming, schrijf er dan één.
- Kortere kaarten mogen nog steeds platte tekst zijn: laat je de blokken weg, dan
  gedraagt de kaart zich als voorheen (echte regelafbrekingen, `white-space: pre-wrap`,
  geen `<br>` of `<p>`). Bedoel je opmaak, gebruik dan blokken — niet allebei door elkaar.
- `la-draft-na` is jouw notitie, niet die van de ontvanger: wat nog open staat,
  welke vraag beantwoord moet worden, of wat er gebeurt zodra het verstuurd is.
- De concepten staan bovenaan de pagina, met een lead-regel die duidelijk maakt
  dat er nog niets verstuurd is.
- Een concept in de pagina zetten is geen goedkeuring. De verzendregel uit
  CLAUDE.md en de skill `bericht-sturen` blijft onverkort gelden.

### Verstuur-knop (LA-SEND, alleen WhatsApp)

Een kaart kan een knop **Verstuur** krijgen. Klikt de reviewer erop en bevestigt hij,
dan legt de bridge kanaal, ontvanger en de exacte tekst vast met een hash
(`components.send.<key>` in `state.json`). De bridge verstuurt niets. Plak
`references/send-snippet.html` vóór het annotator-snippet en zet op de kaart:

```html
<div class="la-draft" data-la-send="wa-nard-2026-09-26"
     data-la-send-channel="whatsapp" data-la-send-to="31612345678">
  <div class="la-draft-hdr"><b>WhatsApp:</b> Nard</div>
  <div class="la-draft-txt">Hi Nard, lukt morgen om 10:00?</div>
</div>
```

- `data-la-send-to` is **exact** de `recipient` die `mcp__whatsapp__send_message` krijgt:
  nummer met landcode zonder + of spaties, of een JID (`@s.whatsapp.net`, `@g.us`,
  `@lid`). De naam hoort in `la-draft-hdr`. Een ander formaat geeft een uitgeschakelde
  knop. De balk onder de kaart toont `whatsapp → <recipient>`.
- Elke bewerking na de klik trekt het akkoord in; de reviewer klikt dan opnieuw.
- Wachten: `bin/wacht-op-verstuur.py --page <url> --key <key>` als achtergrondtaak. Na de
  klik eindigt die met het akkoord en de exacte tool-argumenten (`vervolg`).
- Versturen: één aanroep met precies die argumenten. De PreToolUse-hook
  `bin/verstuur-gate-hook.py` laat alleen een exacte match door (anders de gewone
  toestemmingsvraag); de PostToolUse-hook `bin/verstuur-nastap-hook.py` zet daarna de
  status op `sent` en de kaart op "Verstuurd HH:MM". Een tweede aanroep met dezelfde tekst
  krijgt weer de toestemmingsvraag.
- Andere kanalen hebben (nog) geen knop. Achtergrond en livegang:
  `docs/verstuur-knop-onderzoek.md`.

## Deel 7: geneste subpunten (`la-sub`)

Heeft een punt subtaken, dan wil de reviewer die visueel onder hun ouder zien hangen: hoe
dieper genest, hoe verder ingesprongen. Een platte lijst waarin de hiërarchie
alleen uit de tekst blijkt kost hem leeswerk dat de opmaak gratis kan doen.

De CSS zit in `references/annotator-snippet.html`, dus elke pagina met het snippet heeft het
al. Zet de klasse op het blok zelf, naast wat de pagina er verder aan geeft:

```html
<div class="card">34 · Ouderpunt</div>
<div class="card la-sub">34a · Subtaak</div>
<div class="card la-sub2">34a1 · Sub-subtaak</div>
<div class="card la-sub3">34a1a · Nog een niveau dieper</div>
```

`la-sub` = niveau 1, `la-sub2` t/m `la-sub4` = dieper. Vier niveaus omdat daaronder
de inspringing meer leesbaarheid kost dan hij oplevert; heb je toch een vijfde nodig,
dan is dat één regel bij in het snippet (`--la-diepte: 5`).

Waarom klassen en geen `data-diepte`: `attr()` is in CSS niet in `calc()` te gebruiken,
dus een attribuut vraagt evengoed één selector per niveau. Dan zijn klassen korter,
en ze sluiten aan op wat er al op de todolijst stond.

Punten om op te letten:

- De klassen hangen bewust aan niets anders dan zichzelf — geen `.card` of andere
  pagina-klasse — zodat ze op elk blok-element werken: een kaart, een `<li>`, een
  losse `<div>` in een analyse of vergelijkingspagina.
- Het snippet zet zelf `position: relative` op het element, want het haakje is een
  `::before` die daaraan hangt. Positioneer zo'n element dus niet zelf absoluut.
- De lijnkleur volgt `--line` als de pagina die definieert, met een lichte grijze
  fallback. Zo is het haakje ook zichtbaar op een pagina zonder kleurtokens.
- De inspringstap is 30px en te overschrijven met `--la-stap` op een ouder-element,
  bijvoorbeeld `20px` op een smalle pagina. Het haakje rekent mee.
- Nesting is puur visueel: de blokken blijven zussen in de HTML. Dat is bewust —
  echte nesting zou de annotator, de banden en de tellingen op de todolijst raken.

