---
name: html-annotator
description: >
  Visual HTML annotation skill for fast iteration in agentic work.
  Embed the annotation snippet in every HTML deliverable (prototypes,
  slides, comparison pages, dashboards) without being asked. Also
  trigger when processing feedback: a bare "." (period only),
  "process my feedback", or a path to annotations.json / an annotation
  round — then this skill describes how to read and process rounds and
  screenshot crops. Every draft message (mail, WhatsApp) on a page is a
  la-draft card WITH the Verstuur (send) button — never the plain card,
  whichever skill asked for the page (a messaging or meeting-recap skill, …).
---

# HTML annotator: embed + process feedback

**Read `references/agent-handbook.md` before you act.** It covers the
bridge, rounds, processing (`.` / resolve / refs / locators / hunks),
the checklist component and the suggest layer. This file is only the
port: embed, start the bridge, `/p/` URL, plus the short process
trigger.

Criteria (and what must stay green): `CRITERIA.md`. What is core and
what is not: `docs/SCOPE.md`. Dated choices: `docs/DECISIONS.md`.
Install: `INSTALL.md`.

## Part 1: embed (every HTML deliverable)

Paste the full contents of `references/annotator-snippet.html` at the
bottom of every HTML file, just before `</body>` or at the end of the
file. The block runs from `<!-- HTML-ANNOTATOR v3 -->` to
`<!-- /HTML-ANNOTATOR -->`.

**Anchor on the LAST `</body>`, never the first.** A page can contain
`</body>` inside a JavaScript string long before the real one — bundled
libraries and any code that builds HTML in a variable do this routinely.
Insert on the first match and the snippet lands in the middle of a
script: that script breaks, its output renders as raw text on the page,
and everything it was supposed to draw silently disappears.

```python
i = html.rindex("</body>")        # rindex, not index
html = html[:i] + snippet + "\n" + html[i:]
```

`str.replace(..., 1)` and `sed` both hit the first match, so neither is
safe here. No `</body>` at all: append at the end of the file.

In one case this broke a 3.5 MB process-flow page (three `</body>`
occurrences — two of them inside DOMPurify and a `btoa()` call). The Mermaid diagrams vanished and a wall of minified JS appeared
under the tables. Verify after embedding: open the page and check that
what it normally renders is still there.

On an existing page:
- a block already present (`HTML-ANNOTATOR v3`, or the older
  `LUC-ANNOTATOR v2` that is still supported): do nothing;
- oldest block (`LUC-ANNOTATOR v1`, no end marker): replace everything
  from `<!-- LUC-ANNOTATOR` through the matching `</script>` with the
  new block;
- nothing there: append at the bottom.

Never leave two annotator blocks in one page.

Self-contained: no libraries, no CDN, no external fonts. Works on
`file://` and localhost.

**Always start the bridge afterwards.** One command, idempotent, so
call it blindly on every deliverable and every update of a page that
already has the snippet:

```bash
python -m html_annotator ensure     # or: html-annotator ensure
```

If it is already running, the command does nothing. If not, it starts
the bridge detached from your shell, writes pid and log to a per-user
state directory, and waits until it answers (max 5 seconds). Never skip
this: without the bridge, feedback lands in localStorage and nothing is
on disk.

If `ensure` exits 1 with "port N is taken by something that is not the
bridge", run `python -m html_annotator pick-port` once (it stores a free
port in the per-user config file) and `ensure` again. `ensure` never moves
to another port on its own.

**Safety net, two layers.** Both run `bin/hook-ensure-bridge.py` from
this skill, registered in `~/.claude/settings.json` by
`python -m html_annotator install-hooks`:

- **SessionStart** — one call per session, regardless of how that
  session later writes HTML. This is the layer that counts: the
  PostToolUse layer misses an agent that writes the file via Bash, and
  in auto-mode Bash is the prescribed route.
- **PostToolUse on `Edit|Write`** — if the written file is `.html`/`.htm`
  with an annotator marker (`HTML-ANNOTATOR`, or `LUC-ANNOTATOR` on an
  older page), the bridge comes up.

The matcher is not widened to `Bash`, because that would fire on every
Bash call in every project. What the chosen route does: the
SessionStart registration is user-level with an empty matcher, so it
runs at the start of every agent session on this machine, including
sessions that never touch annotations. That is one curl per session,
and nothing more if the bridge is already listening. The choice lives
in `docs/DECISIONS.md` (2026-08-18). Do not narrow it without a new decision.

**Self-heal in the page.** The snippet does not check the bridge once
on load; it retries every 3 seconds until it answers (plus on
`visibilitychange` and `focus`). If the bridge comes up later — via
the hook, or by hand — the status pill flips on its own and no reload
is needed.

Verification: `tests/run.sh`, criteria in `CRITERIA.md`. Two known
gaps: (1) the fresh-agent case is BLOCKED; (2) the hidden-panel
variant emulates `document.hidden`, not Chrome throttling.

**Always open the page through the bridge, never via `file://` or a
preview pane.** The bridge serves local files on
`GET /p/<path-from-pages-root>`. **Never build that URL yourself**; ask
the CLI:

```bash
python -m html_annotator url ~/Desktop/plan.html
# http://127.0.0.1:8791/p/Desktop/plan.html   (8791 is the default port)
```

The port differs per machine (`pick-port`), and the path after `/p/` is
relative to the pages root, which is the home directory unless
`HTML_ANNOTATOR_PAGES_ROOT` or the config file says otherwise. A file
outside the pages root, or under a dotfile or dot-directory, is refused:
`url` exits 1 with the reason, and the bridge answers 403.
`python -m html_annotator url --base` prints only the base URL (for
`curl`).

**Hand the URL to the reviewer as a clickable markdown link**
(`[title](<what url printed>)`), never inside backticks or a code
block: a code block forces copy-paste, a link opens with one click
(decision 2026-09-15). A preview pane
as `data:` can never reach loopback (Private Network Access). Via
`/p/` the page is same-origin with the bridge.

What the reviewer can do (behaviour unchanged; details in the handbook):
- drag a region, select text, link text (chips), Save;
- status pill `X saved` or `bridge off - localStorage only`;
- orphan list **"N likely processed"**;
- no download button, no Remove-all in the UI.

Test/debug API: `window.HtmlAnnotator.add({type:'region'|'text', rect,
comment, selectedText})`, `.anns()`, `.bridge()`, `.session()`,
`.resolve(annotation)`. Pages written before the rename reach the same
object through the deprecated global alias the snippet still assigns; see
the migration section in `CHANGELOG.md`.

### Checklist component (LA-CHECKLIST)

Any HTML deliverable with checkable items or rows (todo lists,
test-case tables, review queues) also gets the block from
`references/checklist-snippet.html` (`<!-- LA-CHECKLIST v1` to
`<!-- /LA-CHECKLIST -->`), pasted right before the HTML-ANNOTATOR
block. Put `data-la-check="<unique-key>"` on each checkable element
(optional `data-la-label` for an explicit label). The script injects a
Notion-style checkbox, loads saved state on page load via `POST /state`
and saves each change via `POST /state-save`; a checked element gets
the class `la-checked` (title struck through, dimmed).

Reading the checkmarks as an agent: per-page state lives in
`<annotation-root>/<slug>/state.json` (or `POST /state` on the
bridge) — persistent status, separate from the annotation rounds.
Format: `{"components": {"checklist": {"<key>": {"checked": true,
"label": "...", "changedAt": "..."}}}, "updatedAt": ...}`. Use
`changedAt` to see what changed since your last read, analogous to
reading `annotations.json`. Details: handbook part 5.

### Suggested changes (LA-SUGGEST layer)

When you change an existing HTML deliverable and the reviewer should accept
or undo each change individually, mark every changed element with
`data-la-suggest="<unique-key>"` plus `data-la-suggest-desc`,
`data-la-suggest-old` (original content) and optionally
`data-la-suggest-kind` (`edit`/`add`/`del`). Nothing else is needed: the
regular HTML-ANNOTATOR snippet detects these attributes and renders each
suggestion with the exact annotation mechanics — blue selection rects for
text, one region frame for visuals, and the badge stretched into a white
pill holding ✕ reject · ✓ accept · ✎ change; ✎ opens the normal annotator
popup (chips included) for "do it differently". Decisions land via
`POST /state-save` (component `suggest`) in the page's `state.json`.
Processing on `.`: accepted → keep and strip markers, rejected → restore the
original, change → apply the comment; then mark the key `processed`.
Full rules: handbook part 6.

### Draft message card (LA-DRAFT): always the Send-button version

Any draft mail or WhatsApp message on a page is a `.la-draft` card **with
the Verstuur button**. There is no "plain" variant for these channels:
a card without `data-la-send` is a bug, also on a first draft, also when
the calling skill (a messaging, recap or report skill, …) shows an
older example without it. This rule wins over such examples. Teams has no
button yet; only there the plain card plus "verstuur" in chat stays.

Every time, in this order:

1. Card attributes: `data-la-send="<mail|wa>-<name>-<date>"` (unique),
   `data-la-send-channel="mail"` or `"whatsapp"`, `data-la-send-to`
   (addresses only, comma-separated; WhatsApp: number/JID), and for mail
   `data-la-send-account` (sender account) plus either
   `data-la-send-reply="<verified messageId>"` or
   `data-la-send-subject="…"`. Optional `-cc`/`-bcc`. Names go in
   `la-draft-hdr`, not in the attributes.
2. Text in `la-draft-txt` as plain text: `<p>` per paragraph, `<br>` for
   line breaks, bullets as `•`/`◦` characters. No `<ul>/<li>/<a>/<b>`: the
   button sends `innerText`, formatting and links are dropped. Links for
   the reviewer go in `la-draft-na`.
3. Paste `references/send-snippet.html` **before** the annotator snippet.
4. Start the watcher in the same turn, in the background:
   `python3 bin/wacht-op-verstuur.py --page <p-url> --key <data-la-send>`.
   New watcher after every text change.
5. Before handing over the URL, grep the file for `data-la-send=`,
   `data-la-send-to=` (mail: also `data-la-send-account=`) and the
   send snippet. Missing one: fix first.

After the click, and what never goes through the button (attachments,
reply-all): the send instructions of the calling messaging skill.
Card styling and tracked changes: `extras/agent-handbook-extras.md` part 6.

## Agenda-preview (meeting voorstellen)

Every meeting **with invitees** the reviewer wants scheduled starts as a
calendar preview, before any invite exists: a Notion-Calendar-style week
view with the proposals highlighted between the reviewer's existing events.
The reviewer iterates through annotations; nothing is sent until they say "verstuur" on
time, title and invitees.

1. Fetch each calendar with `get-calendar-view`, `timezone="Europe/Amsterdam"`,
   `select="id,subject,start,end,isAllDay,showAs,attendees,organizer,bodyPreview,location,isCancelled"`:
   one call per account, with the MCP server that belongs to it (see
   `mail_servers` in the config file). Large results land in `tool-results/`; use
   that path. An inline result: write the JSON to the scratchpad first.
2. Write an overlay JSON: `heading`, optional `subheading`, `proposals`
   (`nr, title, start, end, invitees, toelichting, status open|verstuurd|vervallen, notitie`)
   and optional `tags` (`{"<exact title>": "nieuw"}`). Keep it next to
   the page, so the next round only edits this file.
3. Build and render:
   ```bash
   python3 bin/agenda-spec.py --cal werk:Werk:purple:<werk.json> \
     --cal prive:Privé:orange:<prive.json> --start <monday> --weeks 3 \
     --overlay <page>.voorstellen.json -o <scratch>/spec.json
   python3 bin/agenda-preview.py <scratch>/spec.json -o <page>.html
   ```
   The renderer embeds the annotator snippet itself; then `ensure` the
   bridge and hand over the `/p/` URL.

What the page does: "Busy." sync copies that mirror an event in another
calendar (±1 min) are dropped, the rest show as "Busy (sync copy)";
blocks of 3 h or more sit in a narrow lane on the left of the day with the
title vertical at the top, overlapping events move beside them; click any
block for a popover (time, duration, calendar, organizer, invitees with
responses, body; for proposals the status, toelichting and notitie).
After sending, set `status: "verstuurd"` and re-render: the proposal turns
green and picks up the real invitees and their responses.

**The reviewer drags, the agent syncs.** Open proposals (and only those, never
existing events) can be dragged on the page: up and down within the day and
to another day of the same week, plus a grip on the top and bottom edge to
move start or end (15-minute snap, minimum 15 minutes, mouse and touch).
A live time label follows the pointer; a red border warns when a proposal
overlaps an existing event, but nothing blocks. Every change autosaves via
the bridge into the page's `state.json` (component `agenda`, key
`voorstel-<nr>`: `{start, end, base, changedAt}`), along the same route as
the annotator snippet (own origin on a bridge `/p/` page, else the
`html-annotator-endpoint` meta, else the default port) and under the slug
of the `-o` file, also outside `/p/`. The pill next to the week range says
`saved` or `bridge off`. On load the page applies that state over the
overlay as long as `base` still equals the overlay time, and marks the
block `moved` (old time and a `back to proposal` button in the popover).
The page UI is English.

Before every next step (presenting the proposals again, or sending
invites), run the sync first and only then read the overlay:

```bash
python3 bin/agenda-spec.py --apply-state <page>.voorstellen.json   # --page <page>.html if named differently; --dry-run to look
```

It writes moved times into the overlay with `notitie` "moved by <name>
from X to Y". The name is `--by <name>`, else the overlay field `movedBy`,
else `reviewer`. It stops when the page file does not exist (pass the
`-o` file as `--page`), skips a proposal whose overlay you changed after
the drag (and says so), ignores drags on proposals that are not open on
the page (the real calendar leads once sent, also when the page derived
"sent" from a real event) or in the overlay, and is a no-op when nothing
moved. An applied drag gets `base` = the new time in `state.json`, so it
is never applied again, also not after you move that proposal yourself;
a new drag on the not yet re-rendered page is still applied at the next
sync, unless you moved that proposal after the sync. The sync reads the
state through the bridge, or from disk only when no bridge runs; the
first line says which (`state: <path> (bridge)` or `(disk)`), and a
bridge that answers with an error stops the sync.
Then re-render with the build commands above: the page shows the same
times, without the `moved` label. On `.`, processing the annotations and
this sync are one move: sync first, then apply the annotations to the
synced overlay, then re-render once.

## Processing (short port)

Triggers — do not ask for confirmation:

- a bare **`.`** (period only, surrounding whitespace is fine);
- "process my feedback" / a path to `annotations.json` or a round.

On `.`, find the open round yourself
(`python -m html_annotator show --open`, or the bridge). Without a page name that picks the most recently annotated
page with open annotations, within a 7-day window, and names the others in
one tail line. Older rounds stay on disk: `--list` shows every page with
open annotations, `--search <term>` finds one by name, `--since N` widens the
window. Never dump the full page list into context.
Understand first, then apply, then `POST /resolve`.
Read `references/agent-handbook.md` (part 4) for refs, locators, hunks,
crops. `python -m html_annotator show` reprints the work rule whenever
something is still open.
