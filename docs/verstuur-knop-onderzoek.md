# Verstuur-knop op la-draft: ontwerp

De Verstuur-knop laat de reviewer een concept-bericht (WhatsApp of mail) op een
`la-draft`-kaart goedkeuren met een klik, zodat een agent precies díe tekst naar precies
díe ontvanger kan versturen. De bridge verstuurt zelf niets.

**Besluit (26-09-2026):** een klik op Verstuur plus de inline bevestiging ("Zeker?") telt
als akkoord van de reviewer op de exacte tekst. Zonder akkoord valt de gate terug op `ask`
(de gewone toestemmingsvraag), zodat "verstuur" typen in de chat blijft werken.

## Waarom een hook en geen bericht in de sessie

Alles wat via een injectieroute een sessie binnenkomt (achtergrondwachter, peer-bericht,
hook-context) behandelt Claude Code als data, niet als input van de gebruiker. Een
wake-up wordt expliciet gelabeld als "not user input". Toestemming komt dus uit één van
twee bronnen: een bericht dat de gebruiker zelf typt, of het permissiesysteem (hooks en
permissieregels die de gebruiker zelf instelt). De knop gebruikt het tweede.

## Stroom

1. De agent zet de kaart neer met `data-la-send`, `-channel`, `-to` (mail ook `-account`
   en `-subject` of `-reply`; optioneel `-cc`/`-bcc`) en plakt `references/send-snippet.html`
   vóór het annotator-snippet.
2. De reviewer klikt op **Verstuur** en bevestigt. De bridge (`POST /send-approve`) legt
   kanaal, ontvanger(s), onderwerp en tekst vast in `state.json` met een SHA-256 die de
   bridge zelf berekent.
3. De sessie die het concept maakte draait `bin/wacht-op-verstuur.py` als achtergrondtaak.
   Na de klik eindigt die met het akkoord en `vervolg`: de exacte tool-aanroep.
4. De agent roept de verzendtool één keer aan met precies die argumenten.
   `bin/verstuur-gate-hook.py` (PreToolUse) rekent de hash over de echte tool-argumenten:
   match met een niet-verbruikt akkoord → `allow`, anders `ask`.
5. `bin/verstuur-nastap-hook.py` (PostToolUse) verbruikt het akkoord na een geslaagde
   verzending (`/send-done`, of in-process als de bridge weg is); de kaart toont
   "Verstuurd HH:MM". Meldt de tool `"success": false`, dan blijft het akkoord staan; is de
   uitkomst onduidelijk, dan wordt het toch verbruikt (liever een tweede klik dan een
   dubbel bericht).

## Beveiliging

- **Een website kan geen akkoord vervalsen.** `/send-approve` eist `Origin` = de bridge
  zelf; browsers zetten die header altijd, dus alleen een `/p/`-pagina komt erdoor.
  `/state-save` weigert de component `send`; `/send-done` weigert browsers.
- **Elke bewerking na de klik trekt het akkoord in** (status `revoked`).
- **Buiten het dreigingsmodel:** een lokaal proces onder het account van de gebruiker kan
  de Origin-header vervalsen of `state.json` aanpassen, maar kan dan ook al alles wat de
  gebruiker kan.

## Ontvangers en kanalen

- **WhatsApp:** `data-la-send-to` is exact de `recipient` van `mcp__whatsapp__send_message`:
  nummer met landcode zonder + of spaties (`31600000000`), of een JID
  (`31600000000@s.whatsapp.net`, `120363000000000000@g.us`, `...@lid`). Een ander formaat
  geeft een uitgeschakelde knop. Nummer en JID van dezelfde persoon zijn verschillende
  waarden.
- **Mail (sinds 27-09-2026):** `send-mail` en `reply-mail-message` op elke server
  `ms365` of `ms365-<naam>`. Het akkoord dekt `channel, account, to, cc, bcc, subject,
  reply, text`; adreslijsten canoniek (kleine letters, ontdubbeld, gesorteerd), namen
  tellen niet. De `account`-parameter is verplicht en zit in de hash, de server niet. De
  body moet exact `tekst_naar_html(tekst)` zijn (lege regel = `<p>`, enter = `<br>`).
  Altijd `ask`: bijlagen, `from`/`sender`/`replyTo`, elk veld buiten de whitelist,
  platte-tekstbody, afwijkende HTML, ontbrekend account. Geen oordeel (gewone vraag):
  `reply-all-mail-message`, `send-draft-message`, `create-*-draft`.
- **Wachter voor mail:** `vervolg` kiest de MCP-server op het account via `mail_servers`
  in het configbestand (zie INSTALL.md). Onbekend account: geen aanroep, "vraag de
  reviewer in de chat".
- Andere kanalen: knop uit, `/send-approve` weigert.

## Optioneel: ondertekend groepsbericht

Voor één WhatsApp-groep kan een externe verifier berichten vooraf ondertekenen (bijv. een
vooraf ondertekend bericht). Alleen met de config-sleutel `signed_group_message`:

```json
{"signed_group_message": {"jid": "120363000000000000@g.us",
                          "verifier": "~/pad/naar/verifier-repo",
                          "module": "pakket.module",
                          "label": "voorbeeldbericht"}}
```

De gate laat dan `mcp__whatsapp__send_message` naar exact die `jid` door als
`<module>.toegestaan(tool_name, tool_input)` (geladen vanaf `verifier`) `True` geeft. Geen
of onvolledige sleutel, een andere ontvanger, of elke fout in de verifier: gewone gate.

## Registratie

`install-hooks` registreert deze twee hooks niet; zet ze zelf in `~/.claude/settings.json`
(niet `settings.local.json`: dat wordt niet geladen als de cwd buiten het project ligt),
met `<skill>` als pad naar de checkout:

```json
"PreToolUse": [
  { "matcher": "mcp__whatsapp__send_message|mcp__ms365.*__(send-mail|reply-mail-message)",
    "hooks": [{ "type": "command", "timeout": 10,
                "command": "/usr/bin/env python3 <skill>/bin/verstuur-gate-hook.py" }] }
],
"PostToolUse": [
  { "matcher": "mcp__whatsapp__send_message|mcp__ms365.*__(send-mail|reply-mail-message)",
    "hooks": [{ "type": "command", "timeout": 10,
                "command": "/usr/bin/env python3 <skill>/bin/verstuur-nastap-hook.py" }] }
]
```

Haal de verzendtools uit `permissions.allow`: crasht of timet de hook, dan valt Claude
Code terug op de permissieregels, en met een allow-regel betekent dat versturen zonder
vraag.

## Risico's en bekende grenzen

- **Auto mode.** In auto mode kan de classifier een `ask` zelf beantwoorden (gemeten
  28-09-2026: een tweede identieke verzending ging door). De gate is daar een vastlegging
  van wát is goedgekeurd, geen harde blokkade; de agent moet dubbel versturen zelf
  voorkomen. Een `deny`-gate met een aparte chat-hook werd door de classifier als
  permissie-omzeiling geblokt en is niet gebouwd.
- **Gelijktijdige aanroepen.** Twee aanroepen met dezelfde tekst kunnen allebei de gate
  passeren voordat de nastap draait. Een agent doet dat niet vanzelf.
- **Zonder lopende wachter gebeurt er na een klik niets.** Start bij elke kaart een
  wachter, en een nieuwe na elke tekstwijziging.
- **Sessie weg.** Het akkoord blijft staan; een nieuwe sessie kan het oppakken (de gate
  staat los van de sessie).
- **Sideviewer.** De inline bevestiging werkt ook in de Claude Desktop-sideviewer
  (gemeten 26-09-2026); `window.confirm()` deed dat niet.

## Tests

`tests/run.sh 18` (in de default-set): `tests/test_verstuur.py` (V1–V11),
`tests/test_verstuur_mail.py` (M0–M11) en `tests/case-18-verstuur-knop.mjs` (browser).
Eigen bridge op een vrije poort met tijdelijke root en config; er gaat niets naar buiten:
`bin/dummy-verstuur.py` speelt een toolaanroep na door beide hooks en schrijft naar een
logbestand. Niet gedekt: het gedrag van Claude Code zelf rond de hook, en de echte
WhatsApp- en mailservers.
