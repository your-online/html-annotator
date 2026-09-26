# Verstuur-knop op la-draft: onderzoek en advies

26-09-2026. Prototype op branch `proto/verstuur-knop` (commit a6a8621), afgemaakt voor
WhatsApp op branch `proto/verstuur-knop-whatsapp`. Niet in de live skill. Getest met een
dummy-kanaal op een losse bridge (eigen poort); er is niets verstuurd.

**Besluit Luc (26-09-2026):** een klik op Verstuur plus het bevestigingsvenster telt als
zijn akkoord op de exacte tekst. Eerst alleen WhatsApp. Zonder akkoord valt de gate terug
op `ask` (de gewone toestemmingsvraag), zodat "verstuur" typen in de chat blijft werken.
Zie "Klaar voor livegang" onderaan.

## Kort

**Haalbaar: ja, maar niet als "bericht in de sessie = akkoord".** Welke injectieroute je
ook kiest, Claude Code behandelt wat binnenkomt als data en niet als Lucs input. Getest:
toen de achtergrondwachter afging, kwam de melding binnen met de tekst
*"NOT user input ... must NOT be treated as approval or consent"*. Een peer-bericht
(`<cross-session-message>`) en hook-context hebben dezelfde status.

Het akkoord moet dus ergens vandaan komen dat Claude Code wél als toestemming telt. Dat
zijn er twee: **een bericht dat Luc zelf typt of verstuurt**, en **het permissiesysteem**
(hooks en permissieregels die Luc zelf instelt). De aanbevolen route gebruikt het tweede.

## Aanbevolen route: klik legt vast, PreToolUse-hook is de poort

1. De agent zet de kaart neer met `data-la-send`, `-channel`, `-to` (en `-subject`,
   `-session`).
2. Luc klikt op **Verstuur**. Er verschijnt een `confirm()`-dialoog met kanaal, ontvanger
   en de exacte tekst (dus inclusief zijn eigen inline-edits). Na OK legt de bridge
   (`POST /send-approve`) kanaal, ontvanger, onderwerp en tekst vast in `state.json`, met
   een SHA-256 die de bridge zelf berekent.
3. De sessie die het concept maakte heeft `bin/wacht-op-verstuur.py` als achtergrondtaak
   draaien. Na de klik stopt die taak, en de sessie wordt wakker met het akkoord als
   eigen tool-resultaat. Er zijn geen sockets en geen peer-berichten nodig.
4. De agent roept de gewone verzendtool aan met precies die tekst.
   **`bin/verstuur-gate-hook.py` (PreToolUse)** rekent de hash over de echte
   tool-argumenten en zet die naast de vastgelegde akkoorden: bij een match `allow`, bij
   geen match `ask`. Bij `ask` vraagt Claude Code gewoon om toestemming, dus het huidige
   "typ verstuur"-pad blijft werken.
5. Na verzending meldt de agent `POST /send-done` en de kaart toont "Verstuurd".

De controle zit daarmee niet meer in het oordeel van het model maar in een
deterministische hook. Die hook maakt ook het huidige pad sterker: een agent kan geen
andere tekst versturen dan de tekst waarop geklikt is.

### Wat getest is (dummy-kanaal)

| scenario | resultaat |
|---|---|
| inline-edit, daarna klik | akkoord bevat de bewerkte tekst |
| tekst wijzigen na de klik | UI: "akkoord ingetrokken"; verzenden van de oude tekst geweigerd (status revoked) |
| agent wil afwijkende tekst versturen | geweigerd (hash wijkt af) |
| andere ontvanger, zelfde tekst | geweigerd (de ontvanger zit in de hash) |
| exacte tekst | verstuurd naar de dummy-outbox, status sent, kaart toont "Verstuurd" |
| nogmaals versturen (replay) | geweigerd (status sent) |
| `/send-approve` met de Origin van een website, of zonder Origin | 403 |
| `/state-save` met `component: "send"` (vervalsen via de CORS-*-route) | geweigerd |
| `/send-done` vanuit een browser | 403 |
| gate-hook: exact / tekst+"!" / andere ontvanger | allow / ask / ask |

### Beveiliging

- **Een website kan geen akkoord vervalsen.** `/send-approve` eist `Origin` = de bridge
  zelf. Browsers zetten die header altijd, dus alleen een `/p/`-pagina komt erdoor.
  `/state-save` weigert de component `send`.
- **Clickjacking.** In een iframe (`window.top !== window`) blijft de knop uit. Een
  cross-origin iframe mag in Chrome bovendien geen `confirm()` tonen.
- **Wat de prototype niet dekt.** Een lokaal proces onder Lucs eigen account kan de
  Origin-header vervalsen of `state.json` rechtstreeks aanpassen. Zo'n proces kan echter
  ook al alles wat Luc kan, dus dit valt buiten het dreigingsmodel.
- **Apart gevonden, los van deze feature:** de live bridge serveert via `/p/` *elk*
  bestand onder home met `Access-Control-Allow-Origin: *` (geverifieerd met curl). Een
  website kan daardoor, afhankelijk van de browser (Chrome's Local Network Access vraagt
  eerst toestemming, Safari en Firefox mogelijk niet), bestanden als `~/.ssh/*` of
  `.env`-bestanden lezen. Aanbevolen: CORS op `/p/` weghalen (pagina's zijn same-origin
  en hebben het niet nodig) en `/p/` beperken tot `.html` en statische assets.

## De andere routes

| route | werkt? | telt als Lucs akkoord? | oordeel |
|---|---|---|---|
| (a) cross-session socket `/tmp/cc-socks/<pid>.sock` | technisch misschien. Het protocol is intern, vereist de sleutel uit `~/.claude/sessions/<pid>.*.key` en kan per versie veranderen | **nee**: komt binnen als `<cross-session-message>`, en een sessie in een andere permissiemodus houdt het vast tot de gebruiker het goedkeurt | afraden |
| (b) UserPromptSubmit-hook die klikken injecteert | ja, maar alleen als Luc toch al iets typt | nee: hook-context is data. Luc moet dan nog steeds een beurt beginnen | voegt weinig toe; wel handig als herinnering |
| (c) achtergrondwachter / Monitor op state.json | **ja, getest** | nee op zichzelf (expliciet zo gelabeld). Met de gate-hook als poort wel | onderdeel van de aanbeveling (trigger) |
| (d) `claude://` deeplink | `claude://code/new?q=` vult een prompt voor in een **nieuwe** sessie; `claude://code/continue?session=<id>` opent een **bestaande** sessie maar accepteert geen `q` (gecontroleerd in de URL-handler van Claude.app) | **ja**, als Luc zelf op Enter drukt | sterkste vorm van akkoord, maar in een nieuwe sessie zonder context. Terugvaloptie |
| desktop `send_message` (MCP) | komt binnen als user-turn "From <sessie>" | nee: afkomstig van een andere sessie, en alleen door een Claude-sessie aan te roepen, niet door de bridge | n.v.t. |

## Risico's

- **Tekst en verzonden body.** Het akkoord ligt op de platte-tekstprojectie van de
  kaart. WhatsApp verstuurt platte tekst, dus dat klopt één op één. Teams en mail
  versturen HTML: de gate moet dan hashen over `nieuwHtml`, of de HTML terugrekenen naar
  de projectie. Dat is nog niet gebouwd, de gate kent nu alleen WhatsApp.
- **Ontvanger-notatie.** `data-la-send-to` moet exact de waarde zijn die de tool krijgt
  (WhatsApp: nummer zonder +, of JID). De confirm-dialoog laat die waarde zien, niet de
  kop van de kaart.
- **Replay via de gate.** Opgelost: `bin/verstuur-nastap-hook.py` (PostToolUse) verbruikt
  het akkoord na een geslaagde verzending. Restrisico: twee *gelijktijdige* aanroepen met
  dezelfde tekst passeren allebei de gate voordat de nastap draait. Een agent doet dat
  niet vanzelf; wie het wil dichtzetten laat de gate het akkoord al bij `allow` claimen.
- **Sessie weg.** Is de sessie die het concept maakte gesloten, dan wacht er niemand.
  Het akkoord blijft staan; een nieuwe sessie kan het oppakken (de gate staat los van de
  sessie).
- **Het model kan terughoudend blijven.** Ook met de hook kan een agent aarzelen, omdat
  de harness de wake-up expliciet als non-consent labelt. De regel in CLAUDE.md moet
  daarom noemen dat de gate-hook het akkoord afdwingt.

## Wat Luc moet beslissen

1. **Telt een klik (met confirm-dialoog) als "expliciet akkoord op de exacte tekst"?**
   Zo ja, dan moet de regel in CLAUDE.md worden aangepast, bijvoorbeeld: *"Een klik op
   Verstuur op een la-draft-kaart, doorgelaten door de verstuur-gate-hook, is mijn akkoord
   op precies die tekst en ontvanger."*
2. **Gate bij geen match: `ask` of `deny`?** `ask` houdt het huidige chatpad open (advies).
   `deny` betekent dat alleen de knop nog kan versturen.
3. **Eerst alleen WhatsApp, of meteen ook Teams en mail?** Voor Teams en mail is het
   HTML-besluit hierboven nodig.
4. **Wil je liever de deeplink-terugvaloptie (d)?** Klik, dan een nieuwe sessie met een
   voorgevulde prompt, en jij drukt op Enter. Dat is juridisch het zuiverst, maar
   omslachtiger.
5. Los hiervan: **de CORS-fix op `/p/`** (zie Beveiliging).

## Bestanden (branch `proto/verstuur-knop`, bijgewerkt op `proto/verstuur-knop-whatsapp`)

- `html_annotator/bridge.py`: `/send-approve`, `/send-revoke`, `/send-done`, de
  Origin-eisen (`HERKOMST`) en het blok op `component: "send"` in `/state-save`
- `references/send-snippet.html`: het LA-SEND-blok (knop, confirm, intrekken bij edit,
  status na reload)
- `bin/wacht-op-verstuur.py`: achtergrondwachter voor de sessie die het concept maakte
- `bin/dummy-verstuur.py`: dummy-kanaal; speelt een WhatsApp-toolaanroep na door beide hooks heen en schrijft naar een logbestand
- `bin/verstuur-gate-hook.py`: PreToolUse-gate (niet geregistreerd)
- `bin/verstuur-nastap-hook.py`: PostToolUse-nastap, verbruikt het akkoord (niet geregistreerd)
- `html_annotator/verstuur.py`: gedeelde tool-mapping en akkoord-zoeker voor beide hooks
- `tests/test_verstuur.py` en `tests/case-18-verstuur-knop.mjs`: case 18 in `tests/run.sh`

## Afgemaakt voor WhatsApp (26-09-2026)

Branch `proto/verstuur-knop-whatsapp`, bovenop a6a8621.

| onderdeel | wat |
|---|---|
| PostToolUse-nastap | `bin/verstuur-nastap-hook.py`. Na `mcp__whatsapp__send_message` zoekt hij het akkoord met dezelfde hash en roept `/send-done` aan (bridge weg: dezelfde handler in-process). Status wordt `sent`, de kaart toont "Verstuurd HH:MM". Meldt de tool `"success": false`, dan blijft het akkoord staan. Is de uitkomst onduidelijk, dan wordt het toch verbruikt: liever een tweede klik dan een dubbel bericht. |
| PreToolUse-gate | `bin/verstuur-gate-hook.py`. `allow` alleen bij een akkoord met status `approved` en exact dezelfde hash over kanaal, ontvanger en tekst. Anders `ask`. Een andere tool: geen oordeel. Kan hij de akkoorden niet lezen: `ask`, nooit `allow`. |
| Ontvangerformaat | `data-la-send-to` op de kaart is exact de `recipient` die de tool krijgt: nummer met landcode zonder + of spaties (`31612345678`), of een JID (`...@s.whatsapp.net`, `...@g.us`, `...@lid`). De naam blijft in `la-draft-hdr`. De balk onder de kaart toont `whatsapp → 31612345678`, de confirm ook. Snippet en bridge weigeren een ander formaat al bij de klik (een kaart met `+31 6 ...` zou in de gate nooit matchen). Nummer en JID van dezelfde persoon zijn verschillende waarden: de agent moet versturen naar wat op de kaart staat. |
| Alleen WhatsApp | Een kaart met een ander kanaal krijgt een uitgeschakelde knop; `/send-approve` weigert andere kanalen. |
| Paginasleutel (bug in a6a8621) | De snippet stuurde het pad zonder `/p/`, waardoor de bridge élke pagina op slug `pagina` zette: akkoorden van verschillende pagina's in één `state.json`. Nu stuurt hij `location.href`, zoals de checklist. Wachter en dummy nemen een `/p/`-URL of een bestandspad. |
| Wachter | `bin/wacht-op-verstuur.py` geeft na de klik naast het akkoord een `vervolg`: de exacte tool-aanroep (`recipient`, `message`). Exit 3 als de kaart al verstuurd is. |

### Tests

`tests/run.sh 18` (in de default-set). Eigen bridge op een vrije poort, tijdelijke root;
de live bridge op 8791 wordt niet aangeraakt. Er gaat niets naar buiten: het dummy-kanaal
roept de gate aan, schrijft bij `allow` één regel in een logbestand en roept dan de nastap aan.

| scenario | case | resultaat |
|---|---|---|
| inline-edit, klik, confirm | 18 browser | confirm toont bewerkte tekst + recipient; akkoord = bewerkte tekst; gate `allow` op bewerkt, `ask` op origineel |
| typen na de klik | 18 browser | `revoked` in state.json, UI "akkoord ingetrokken", gate `ask` |
| andere tekst / andere ontvanger / zelfde nummer als JID | V3 | `ask` |
| dubbel versturen | V6, 18 browser | tweede keer `ask`, outbox houdt één bericht; opnieuw goedkeuren van verstuurde tekst geweigerd |
| vervalst akkoord: Origin van een website, geen Origin, `/state-save` met `send`, fetch vanaf een andere origin in de browser | V1, 18 browser | 403 / geweigerd, geen entry |
| na verzending | V5, 18 browser | status `sent`, kaart "Verstuurd HH:MM", ook na reload, knop uit |
| tool meldt `success: false` | V8 | akkoord blijft `approved` |
| bridge draait niet tijdens de nastap | V9 | in-process verbruikt, daarna `ask` |
| wachter | V4 | wacht, stopt na klik, geeft exact de tool-argumenten |
| ongeldige recipient op de kaart, ander kanaal | V2, 18 browser | knop uit / 400 |

Mutatiecheck: nastap uitgeschakeld → 7 asserts rood (V5, V6, V8, V9); gate altijd `allow`
→ 7 asserts rood (V1, V3, V6, V7, V9).

Niet gedekt: het gedrag van Claude Code zelf rond de hook (zie stap 5 hieronder), en de
echte WhatsApp-MCP.

## Wakker worden: stap voor skill `bericht-sturen` (voorstel)

Niet in de live skill gezet. Voorgestelde tekst, als aanvulling op "Voorleggen: altijd als
HTML-concept" (na punt 4) voor WhatsApp:

> **WhatsApp: Verstuur-knop.** Zet op de kaart:
> `data-la-send="wa-<naam>-<datum>"` (uniek per bericht), `data-la-send-channel="whatsapp"`,
> `data-la-send-to="<recipient>"`: exact de waarde die je aan `mcp__whatsapp__send_message`
> geeft (nummer met landcode zonder +, of de JID uit de store; bij een groep de `@g.us`-JID).
> Plak `references/send-snippet.html` vóór het annotator-snippet.
>
> Start daarna in dezelfde beurt de wachter als achtergrondtaak (`run_in_background: true`):
>
> ```bash
> python3 ~/.claude/skills/html-annotator/bin/wacht-op-verstuur.py \
>   --page http://127.0.0.1:8791/p/Desktop/bericht-nard-2026-09-26.html --key wa-nard-2026-09-26
> ```
>
> Klikt Luc op Verstuur en bevestigt hij, dan eindigt de wachter en word je wakker met het
> akkoord. Doe dan precies dit:
> 1. Is `ok` false: niets versturen, meld in één regel wat er is (timeout, al verstuurd).
> 2. Roep `mcp__whatsapp__send_message` één keer aan met exact `vervolg.arguments`:
>    `recipient` en `message` letterlijk overnemen, geen spatie of regelafbreking aanpassen.
> 3. Vraagt Claude Code alsnog om toestemming, dan klopt de tekst of ontvanger niet met
>    het akkoord (of Luc heeft het ingetrokken): stop en meld het; niet opnieuw proberen.
> 4. Rapporteer: naar wie, vanaf welk account, en dat de kaart op "Verstuurd" staat.
>    `/send-done` hoef je niet aan te roepen; de nastap-hook doet dat.
>
> Past Luc de tekst aan na het wakker worden, of komt er nieuwe feedback: werk de kaart
> bij, start een nieuwe wachter, en verstuur niets op het oude akkoord.
> Typt Luc in de chat "verstuur", dan blijft het gewone pad gelden (de gate vraagt dan
> om toestemming, en die geeft Luc).

## Klaar voor livegang

Niets hiervan is gedaan: CLAUDE.md, settings en de live skill zijn niet aangeraakt.

### Activeren, in deze volgorde

1. **Mergen.** In `~/.claude/skills/html-annotator`: branch `proto/verstuur-knop-whatsapp`
   mergen naar de werkbranch. Let op: de live checkout heeft ongecommitte wijzigingen van
   een andere sessie (`bin/annotator-bridge.py`, `bin/toon-annotaties.py`,
   `references/annotator-snippet.html`, `docs/page-save-voor-312.diff`). Die eerst laten
   committen of stashen door de eigenaar. Ook `docs/verstuur-knop-onderzoek.md` staat daar
   nog als ongetrackt bestand; de branch bevat de bijgewerkte versie, dus het losse bestand
   eerst weghalen, anders weigert git de merge. De branch raakt `annotator-snippet.html` niet;
   `html_annotator/bridge.py` wel (nieuwe routes, blok op `component: "send"`).
2. **Bridge herstarten** zodat hij de nieuwe routes kent (door Luc of via
   `python3 -m html_annotator ensure` na een eigen stop; niet met `pkill`).
   Controle: `curl -s -X POST http://127.0.0.1:8791/send-done -H 'Content-Type: application/json' -d '{}'`
   geeft een fout over een ontbrekende key, niet "onbekend pad".
3. **Hooks registreren** in `~/.claude/settings.local.json`, onder `hooks`, naast de
   bestaande entries:

   ```json
   "PreToolUse": [
     { "matcher": "mcp__whatsapp__send_message",
       "hooks": [{ "type": "command", "timeout": 10,
                   "command": "/usr/bin/env python3 /Users/lucmahieu/.claude/skills/html-annotator/bin/verstuur-gate-hook.py" }] }
   ],
   "PostToolUse": [
     { "matcher": "mcp__whatsapp__send_message",
       "hooks": [{ "type": "command", "timeout": 10,
                   "command": "/usr/bin/env python3 /Users/lucmahieu/.claude/skills/html-annotator/bin/verstuur-nastap-hook.py" }] }
   ]
   ```

4. **`mcp__whatsapp__send_message` uit de `permissions.allow`-lijst halen** in
   `~/.claude/settings.local.json` (staat er nu in, regel ~48). Nu gaat een WhatsApp-bericht
   daardoor zonder vraag de deur uit; alleen de CLAUDE.md-regel houdt het tegen. Met de gate
   erbij geldt: bij een match zegt de hook `allow`, zonder match `ask`. Maar crasht of
   timet de hook, dan valt Claude Code terug op de permissieregels, en met de allow-regel
   betekent dat: versturen zonder vraag. Zonder die regel wordt het de gewone vraag.
5. **Nagaan hoe `ask` zich gedraagt in auto-modus** (`defaultMode: "auto"` in
   `settings.json`). De hook-documentatie zegt dat `ask` de gebruiker laat bevestigen; of
   de auto-modus-classifier zo'n vraag zelf beantwoordt is niet getest. Veilig te toetsen
   zonder iets te versturen: in een nieuwe sessie de agent een `send_message` laten
   aanroepen zonder akkoord, en bij de vraag **nee** kiezen. Komt er geen vraag en gaat
   het bericht door, dan de hook op `deny` zetten voor het geval zonder match (één regel in
   `verstuur-gate-hook.py`) en het chatpad via een tweede route regelen.
6. **Snippet op concept-pagina's.** Nieuwe pagina's: `references/send-snippet.html` vóór
   het annotator-snippet plakken en de kaart-attributen zetten (zie het voorstel voor
   `bericht-sturen` hierboven). Bestaande pagina's hoeven niets: zonder `data-la-send`
   verandert er niets.
7. **Skill `bericht-sturen` bijwerken** met de voorgestelde stap hierboven, en het
   `la-draft`-deel in `extras/agent-handbook-extras.md` (staat al op de branch).
8. **CLAUDE.md aanpassen** (voorstel hieronder), na Lucs akkoord op de tekst.
9. **Eerste echte keer**: een appje aan Luc zelf, zodat een fout niemand anders raakt.

### Voorstel voor CLAUDE.md, sectie Berichten

Huidige tekst:

> **Niets gaat de deur uit zonder Lucs expliciete akkoord op de exacte tekst.** "Stuur even
> een berichtje" is de opdracht om het bericht te máken, niet om het te versturen. Alleen
> een expliciet "verstuur" of "doe maar" op de voorgelegde tekst telt; verandert de tekst
> daarna nog, leg de nieuwe versie opnieuw voor. Opstellen via skill `bericht-sturen`, de
> recap na een meeting via `recap-meeting`.

Voorgestelde tekst:

> **Niets gaat de deur uit zonder Lucs expliciete akkoord op de exacte tekst.** "Stuur even
> een berichtje" is de opdracht om het bericht te máken, niet om het te versturen. Akkoord
> is één van twee dingen: (1) een expliciet "verstuur" of "doe maar" in de chat op de
> voorgelegde tekst, of (2) voor WhatsApp: een klik op **Verstuur** op de la-draft-kaart
> plus OK in het bevestigingsvenster. Route 2 geldt alleen voor exact die tekst en die
> ontvanger, en alleen als de verstuur-gate-hook de aanroep doorlaat; vraagt Claude Code
> toch om toestemming, dan is er geen akkoord en verstuur je niet op eigen houtje.
> Verandert de tekst na het akkoord, leg de nieuwe versie opnieuw voor. Opstellen via skill
> `bericht-sturen`, de recap na een meeting via `recap-meeting`.

## Livetest 26-09

Verse sessie (cwd `~/Desktop`, auto mode), kaart `wa-luc-test2-2026-09-26` naar 31658730061.

| Check | Uitkomst |
|---|---|
| Wachter eindigt na klik + OK met `ok=true` | ja (17:05:34) |
| `send_message` met `vervolg.arguments` verstuurd | ja, `success: true` |
| Toestemmingsvraag bij de verzending | nee (maar zie hieronder: gate draaide niet) |
| Kaart automatisch "Verstuurd" | **nee**: state bleef `approved` |
| Negatieve test (2e verzending → `ask`) | overgeslagen: zonder nastap staat het akkoord nog open, dus zonder gate zou een 2e bericht gewoon doorgaan |

**Oorzaak.** `~/.claude/settings.local.json` wordt niet geladen als de cwd `~/Desktop` is. Ook de
SessionStart-hook `hook-ensure-bridge.py` uit dat bestand liep niet; alleen de hooks uit
`~/.claude/settings.json` (AMY/WIP) draaiden. Gate en nastap waren dus allebei inactief. De logica zelf
klopt: `hash_voor` + `zoek_akkoord` vinden het akkoord voor exact deze argumenten (dry-run).
Fix: de hookblokken naar `~/.claude/settings.json` verplaatsen, daarna test 2 herhalen incl. stap 6.

**Aanpassing zelfde dag.** `window.confirm()` vervangen door een inline "Zeker? [Nee, cancel] [Ja, verstuur]"
onder de knop (Luc: moet ook in de sideviewer werken). De iframe-blokkade (`ingelijst`, clickjacking) staat
nog aan; die moet eruit of versmald worden voordat de knop in een ingebedde viewer werkt.

**Vervolg 17:10–17:25.** Hookblokken (gate, nastap, bridge) verplaatst naar `~/.claude/settings.json`;
`classified-guard.py` bleef in `settings.local.json`. De wijziging werd midden in de sessie opgepikt: bij de
volgende verzending (kaart `wa-luc-test3-2026-09-26`) meldde de nastap "akkoord verbruikt (bridge)" en sprong de
kaart vanzelf op Verstuurd. Sideviewer gemeten: Lucs klik op test 3 in de Claude Desktop-sideviewer kwam door
(geen iframe-blokkade), dus alleen de inline-bevestiging was nodig; `frame-ancestors` niet nodig.
Val: zonder lopende wachter gebeurt er na een klik niets. Start dus bij elke Verstuur-kaart een wachter.
Negatieve test (gate `ask` op een tweede verzending) nog niet gedaan.
