# Agent handbook (html-annotator)

Read this file when `SKILL.md` asks you to — before delivering HTML and before processing annotations. Part 1 (embedding) lives in `SKILL.md`; what used to be here about spawning tasks, draft cards and `la-sub` has moved to `extras/agent-handbook-extras.md` (see `docs/SCOPE.md`).

> **Draft messages (`la-draft`): always the Send-button version.** A draft mail or
> WhatsApp message on a page always gets the Verstuur button (`data-la-send*`
> attributes, `references/send-snippet.html` before the annotator snippet, watcher
> `bin/wacht-op-verstuur.py` in the background, plain-text `<p>` blocks). Never the
> plain card, whatever the calling skill's example shows. Exact steps: `SKILL.md`,
> section "Draft message card (LA-DRAFT)".

## Part 2: the bridge

A browser page cannot write to disk on its own. The bridge
(`html_annotator/bridge.py`, stdlib only) solves that: it listens on
**127.0.0.1:8791** by default (not 8080, because that belongs to Docker),
manages the round directories, writes the JSON and cuts out the screenshot
crops.

**Port, bind address and pages root can differ per machine.** Never assume
8791 and never build a URL yourself:

- `python -m html_annotator url <file>` prints the `/p/` link for a page;
- `python -m html_annotator url --base` prints only the base URL
  (`http://127.0.0.1:<port>`), for `curl` and scripts.

Where the values come from, highest first: environment
(`HTML_ANNOTATOR_PORT`, `HTML_ANNOTATOR_HOST`, `HTML_ANNOTATOR_PAGES_ROOT`) >
the per-user config file (`~/.config/html-annotator/config.json`,
`$XDG_CONFIG_HOME` respected, on Windows `%APPDATA%\html-annotator\config.json`;
keys `port`, `host`, `pages_root`) > the defaults 8791, 127.0.0.1 and the home
directory. URLs always use 127.0.0.1, also when the bridge binds to 0.0.0.0
(Docker).

`python -m html_annotator pick-port` chooses a port once: it tries 8791–8890,
takes the first free one (a port where this bridge already answers counts as
good), falls back to a port from the OS when all are taken, and writes it to
the config file. Run it after installing, and whenever `ensure` says the port
is taken by something else. If pick-port itself fails, find a free port
yourself and store it with `python -m html_annotator pick-port --port N`.
`ensure` never switches ports on its own.

All commands below run as `python -m html_annotator <command>`;
after a pip/pipx install, `html-annotator <command>` is exactly the same.
`python -m html_annotator --version` tells you which version you have in front of you.

Starting goes through `python -m html_annotator ensure` (see part 1), not
by hand. That command first checks whether it is already listening, otherwise starts it
detached from your shell, and writes pid and log to a per-user state
directory (`~/.local/state/html-annotator`, on Windows `%LOCALAPPDATA%`).
Running it in the foreground is possible too, for debugging:

```bash
python -m html_annotator serve
```

Is it running? `python -m html_annotator status` (or
`curl -s "$(python -m html_annotator url --base)/ping"`) gives
`{"ok": true, "bridge": "html-annotator", "version": 2, "release": "...", ...}`
(`version` is the protocol the snippet speaks, `release` the package version).
In the page itself
you can see it from the green status pill ("X saved"). If that pill is
orange and says "bridge off - localStorage only", nothing has been written to disk;
the page then falls back to localStorage and says so on every Save.

The bridge crops with headless Chrome (`--headless=new --screenshot
--window-size=<doc.w>,<doc.h>`) plus Pillow if it is installed; without
Pillow, Chrome renders the region itself through an iframe clip. Both routes are
tested. Full-page screenshots are cached in
`$TMPDIR/html-annotator-shots`.

Endpoints: `GET /ping`, `GET /p/<path-from-pages-root>` (forward slashes in the URL, on Windows too; nothing outside the pages root, no dotfiles or dot-directories, also not through a symlink), `POST /session`, `/save`, `/delete`,
`/remove-all`, `/resolve`, `/state`, `/state-save`, `/sessie`.

`/session` returns, besides the counts, the open annotations as well (nr, id,
type, rect, comment, selectedText, `stale`), so the page knows what to
draw.

`POST /sessie` opens a new Claude Code session with a preloaded prompt:
pass `{"prompt": "..."}` or a ready-made `{"url": "claude://code/new?q=..."}`.
Only the claude scheme is accepted, so this does not become a general
URL opener. It exists because an embedded browser does not pass custom schemes
through; a session-start skill can build on it.

## Part 3: rounds and directory structure

```
<annotation-root>/<page-slug>/
  ronde-01/
    annotations.json
    screenshots/annotatie-01.png
  ronde-02/
    ...
```

The annotation root is `~/annotations` (or `HTML_ANNOTATOR_ROOT`; the old
`LUC_ANNOTATOR_*` names still work as a deprecated alias. On a machine that already
uses the old annotation folder on the desktop, that one stays). The slug comes from the
filename of the page (file://) or otherwise from the page title, and is a valid
directory name on every operating system. Old rounds are never overwritten.

A new round starts **only** when the current round is closed through
`POST /remove-all`: that round is emptied and set to `"closed": true`, and
the next annotation opens round+1. There is no button for it in the page itself
any more. The current round is always the highest existing round that is not closed.

Changed page content no longer opens a new round. If you edit the HTML
in response to feedback, the round stays as it is, with the annotations that
have not been processed yet. The `contentHash` (hash of the HTML file without the
annotator block; for non-disk pages a DOM hash) is still
written, per round and per annotation, purely as context for which
page version that feedback belonged to, plus `lastContentHash` at round level.

## Part 4: processing feedback

**Triggers.** Read and process open annotations as soon as the reviewer sends one of these
messages (do not ask for extra confirmation that he means it):

- a bare **`.`** (period only, surrounding whitespace is fine) — that is
  the short "process my annotations";
- "process my feedback", "check my saved feedback", or a path to
  `annotations.json` / an annotation round.

On a bare `.` find the open round yourself (via
`python -m html_annotator show --open` or the bridge), instead of waiting for an
explicit path. Check on the same trigger whether the page's `state.json`
holds unprocessed LA-SUGGEST decisions (component `suggest`, part 6) — the
reviewer uses one `.` for both channels.

The reviewer sometimes also pastes a message along the lines of "Look, here are the annotations:
`<path>/ronde-NN/annotations.json`. There are X of them." Read that file.

Per annotation:

```json
{ "nr": 1, "type": "region", "target": "kop van de kaart",
  "comment": "...", "image": "screenshots/annotatie-01.png", "_rect": {...} }
{ "nr": 2, "type": "text", "target": "...", "comment": "Maak hetzelfde als ⟦r1⟧",
  "selectedText": "de exact geselecteerde tekst",
  "locator": { "path": "#a", "start": { "path": "#a", "node": 0, "offset": 0 },
               "end": { "path": "#a", "node": 0, "offset": 27 }, "nth": 0,
               "label": "This is the first paragraph. Make me match the second one." },
  "refs": [{ "id": "r1", "selectedText": "andere tekst op de pagina" }] }
```

- `locator` (on `type: "text"`): the place on the page, not just the text. `path`
  is the common element, `start`/`end` the exact range, `nth` which
  occurrence if the same text appears more than once, `label` the context (row/card). Use
  this to know *which* "check" or which row the reviewer meant. No locator plus text
  that occurs more than once: ask, do not pick the first hit.
- `refs` (optional): other text fragments the reviewer linked in the comment.
  In `comment` they appear as `⟦r1⟧`, `⟦r2⟧`, …; `refs` gives the full
  `selectedText` per id. Use this for "same as …" feedback.
- When processing: read **`commentExpanded`** (refs filled in as `"text"`) or
  `python -m html_annotator show` — that expands markers and warns when `refs` is missing.
  If it says `refsIncomplete`, ask the reviewer to save again; do not guess which text r1/r2 was.
- Common intentions: **"Make ⟦r1⟧ the same as ⟦r2⟧"** → change the text
  of r1 (or the annotated `selectedText`) to match r2; **"change to"** =
  replace with the ref text. `selectedText` is the primary anchor; refs are
  comparison text elsewhere on the page.

- `type: "region"` → open `image` (the path is relative to the round directory) with the
  Read tool and read the crop alongside the comment. You no longer have to crop yourself, that
  already happened at save time. `_rect` is internal, ignore it.
- `type: "text"` → use `selectedText`; there is no screenshot.
- `type: "edit"` → the reviewer rewrote the text of a draft message himself. `hunks`
  gives the changes as separate blocks, each with the surrounding text as an anchor
  (`voor`/`na`), the `alinea` number to refer to, and `verwijderd`/`toegevoegd`.
  `diff` is the same information as a flat sequence, `origineel` and `nieuw` the two full
  versions. Blocks can be applied and ticked off one by one:

  ```bash
  python -m html_annotator apply-hunk <json> --nr 1 --hunks 2 --resolve
  ```

  The anchor is the text, not the position — so a block stays placeable even if the page
  has changed elsewhere in the meantime. If you cannot find a block, do not invent a spot: report
  it and ask. Take `nieuw` over as the text of that draft; there is nothing to
  interpret here, he has already written it down the way he wants it. Only ask further if
  his rewrite touches something that also appears elsewhere in the page.
  `python -m html_annotator show` prints this as a readable diff.
- `attachment` is there when the reviewer pasted or attached an image himself; view
  that one with the Read tool as well.

**Understand first, process second.** This is not a formality: the reviewer often dictates
his annotations, which makes sentences run dead now and then and leaves context that is
obvious to him off the page. Go through them one by one and put what
you are unsure about to him, instead of filling it in yourself. Ask when something is too vague
to act on, say so when you disagree or see a consequence
he does not mention, and say it when a point contradicts something he said
earlier. If there are choices in it, ask the question clickably with `AskUserQuestion`.
In doubt about whether to ask: ask. Guessing wrong costs him more time than a
question.

`python -m html_annotator show` prints this working rule itself as soon as there are open annotations,
so it also reaches a session that has not read this skill.

With many annotations you may bring in subagents (one per annotation or per small group)
or work through them step by step. Process point by point.

For the context of an older round, go to the matching `ronde-NN` directory; the
`contentHash` and `capturedAt` tell you which version of the page that
feedback belonged to.

### MANDATORY: mark processed annotations as resolved

This is the step that gets forgotten most often, and that is exactly where it goes wrong: a
processed annotation whose flag you do not set loses its anchor (after all, you changed the
text), ends up in the "likely processed" list and comes back
every round. So processing without ticking off is **not done**.

Once you have processed an annotation in the page, report it to the bridge right away.
It stays in the JSON as history (with `"resolved": true` and
`"resolvedAt"`), but disappears from the page, so that after a refresh the reviewer only
sees what is still open. Do this per processed batch, not only at the end:

```bash
curl -s -X POST "$(python -m html_annotator url --base)/resolve" \
  -H 'Content-Type: application/json' \
  -d '{"jsonPath":"~/annotations/todos/ronde-09/annotations.json","nrs":[1,3,4]}'
```

Response: `{"ok":true,"round":9,"resolved":[1,3,4],"notFound":[],"open":2,"total":5}`.
Check `notFound` and `open`: that is your own check that you had the right numbers
and how many are still open.

- `nrs` are the annotation numbers from that round; `ids` is allowed too.
- `jsonPath` is the path the reviewer sent you (`~` is fine). If you leave it out,
  the bridge takes the current round of the page (`pageFile`/`page`/`slug`, just like the
  other routes).
- Undoing is possible with `"resolved": false`.
- Say in your answer which numbers you ticked off and what is still
  open.

Positioning after a page change: the snippet looks up text annotations
again through their `locator` (path, start row label, then `selectedText` + nth).
Only when that text is nowhere on the page any more does the annotation appear in
the "likely processed" card at the bottom left. Region annotations from an older
page version are not drawn at possibly wrong coordinates and land
in that same card. If you process such an annotation, it disappears from there
as soon as you set it resolved; the reviewer can also tick it off there himself with the ✓.

## Part 5: the checklist component (LA-CHECKLIST)

For every HTML with tickable items or rows (todo lists, test case tables,
review rows). The component is a separate block, `<!-- LA-CHECKLIST v1` through
`<!-- /LA-CHECKLIST -->`, canonical in `references/checklist-snippet.html`.
Self-contained, no dependencies, just like the annotator snippet. Like the
annotator snippet it talks to the bridge that served the page (`location.origin`
on a `/p/` URL), whatever its port. Opened as `file://` it falls back to
`http://127.0.0.1:8791`, best effort only: Chrome blocks `file://` pages from
reaching loopback anyway (Private Network Access), so open pages via `url`.

**Embedding:**

1. Paste the full block from `references/checklist-snippet.html` right before
   the HTML-ANNOTATOR block (on older pages the LUC-ANNOTATOR block).
2. Put `data-la-check="<unique-key>"` on every tickable element. The key is the
   lasting anchor in the state — pick something stable (e.g. the item number,
   `"#74"`), not a sequence number that shifts.
3. Optionally `data-la-label="..."` for an explicit label; otherwise the script takes
   the text of `.what` or of the element itself (max 140 characters).

The script injects a Notion-style checkbox — into `.la-check-slot` if there
is one, otherwise into the first `summary`, otherwise at the front of the element — loads the
stored state at page load through `POST /state`, and writes every change
through `POST /state-save` with `{component:"checklist", key, value:{checked,
label}}`. A ticked element gets the class `la-checked` (title
struck through and dimmed; the CSS targets `.what`, inside a `summary` too).

**State, separate from the rounds.** The ticks are lasting status, not a
feedback round: they live per page in `<annotation-root>/<slug>/state.json`,
next to the `ronde-NN` directories. Format:

```json
{ "components": { "checklist": {
    "#74": { "checked": true, "label": "…", "changedAt": "2026-08-28T…" } } },
  "updatedAt": "2026-08-28T…" }
```

**Reading it as an agent:** read `state.json` directly, or ask the bridge with
`POST /state` and `{"page": "..."}` (or `pageFile`/`slug`, like the other
routes). Use `changedAt` per key and `updatedAt` on the whole to see
what has changed since last time — analogous to how you read
`annotations.json`. There is nothing to resolve: a tick *is* the status.

`/state-save` merges the given `value` over the existing entry and sets
`changedAt`; components other than `checklist` can use the same two routes
with their own `component` name.

## Part 6: suggested changes (LA-SUGGEST layer)

For changes that you as an agent make in an existing HTML and that the
reviewer wants to be able to accept or revert one by one — like suggested
changes in code. Since v5 this is **no longer a separate snippet**: the layer sits in
the ordinary annotator snippet and activates itself as soon as there are elements with
`data-la-suggest` on the page. So a page with the HTML-ANNOTATOR block
(or the older LUC-ANNOTATOR block) already has everything;
`references/suggest-snippet.html` is obsolete.

**Marking (while making the change):** put on every changed element

- `data-la-suggest="<unique-key>"` — stable key (e.g. `"wi-29119"`), mandatory;
- `data-la-suggest-desc="..."` — one sentence saying *what* you changed; this
  becomes the quote block in the popup;
- `data-la-suggest-old="..."` — the original text, so that a rejection is
  exactly revertible. Mandatory with `kind="edit"`;
- `data-la-suggest-kind` — `"edit"` (default), `"add"` (new; rejecting =
  removing), `"del"` (proposal to delete; rejecting = leaving it in place);
- `data-la-suggest-mode` — usually leave it out: text automatically gets
  text-line selections and visuals (`figure`/`svg`/`img`/`canvas`/`video`/
  `table`, or something containing those) one region frame. Only set it explicitly
  (`"text"` or `"region"`) when that autodetection picks wrong.

**One key = one suggestion = one pill.** The decision is stored per key,
so only put the same `data-la-suggest` on several elements when it really is
one decision. If you do, the layer draws all rects of those elements
as one visual group with exactly one pill next to it — what you see is then what
happens. If the reviewer should be able to decide per row (a work item row with its
subtask rows, for instance), give every row its own key: parent `wi-<id>`,
subtasks `wi-<parentid>-<subid>`, each with its own `data-la-suggest-desc`.
(Until 31-08-2026 the layer drew a pill per element on a shared key: five
buttons that were secretly one decision together.)

**Hidden at load time is fine.** Suggestions in a collapsed table group, behind
a filter or in DOM inserted later get their pill as soon as they become
visible: the layer redraws on DOM and visibility changes. So you do not have to
do anything extra to support collapsible sections. What the layer watches for:
DOM being added or removed, and the attributes `class`, `style`,
`hidden` and `open`. If your page collapses or expands purely in CSS (an
`input:checked ~ table` trick, or a stylesheet that swaps), then no attribute
changes and the pill stays away — so have such a toggle set a class or
a style as well.

**What the reviewer sees:** exactly the annotation mechanics. Every suggestion gets
the familiar selection rects (blue) over the changed text, with at the
end the badge stretched out into a pill with the three actions in it:
**✕ reject · ✓ accept · ✎ otherwise**. On ✎ the ordinary
annotator popup opens, with the proposal as a quote and the full comment field
(including text chips through the chain icon); Save = "otherwise, namely like this".
After a decision the pill shrinks to one coloured badge (green ✓ / red ✕ /
orange ✎); clicking it turns the choice back to pending. With a
change decision the typed text is kept along the way: if the reviewer picks
✎ again, his own sentence (chips included) is back in the popup and he
can polish it instead of retyping. That works after a reload too — the
prefill comes from the loaded state, not from a variable. Accepting or
rejecting drops the text on purpose, so that you do not find a dead change comment on
an accepted key.

**State.** Decisions are lasting status, not a feedback round: they sit in
`<annotation-root>/<slug>/state.json` under component `suggest`
(`POST /state-save`), with per key `decision` (`"accepted"`, `"rejected"`,
`"change"`, `"pending"`), `comment`, and with chips also `refs` (id +
selectedText + locator) and `commentExpanded` (chips written out inline).

**Processing as an agent.** Same triggers as annotations (bare `.`, "process").
Read the state (`state.json` or `POST /state`) and handle it per key:

- `accepted` → the change stays. Remove the `data-la-suggest*` attributes.
- `rejected` → revert exactly: with `kind="edit"` you put
  `data-la-suggest-old` back, with `"add"` you delete the element, with
  `"del"` you leave it in place. Then remove the attributes.
- `change` → carry out `commentExpanded`; use `refs[].locator` when the
  intended text occurs more than once on the page. Unclear: ask, do not guess.
- `pending` or no entry → leave it. A pending entry can still carry a
  `comment` (text from a change that was clicked back): that is a draft
  by the reviewer, not an instruction — do not carry it out.

Report every handled key with `POST /state-save` and
`{"component":"suggest","key":"...","value":{"processed":true}}` — the layer
skips entries with `processed` when reloading. Say in your answer what
you left accepted, reverted and changed.

An LA-SUGGEST decision is status (like a tick), *not* an annotation: it
does not end up in `annotations.json` and does not need `/resolve`. Ordinary
annotations on the same page keep working as usual.
