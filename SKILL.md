---
name: html-annotator
description: >
  Visual HTML annotation skill for fast iteration in agentic work.
  Embed the annotation snippet in every HTML deliverable (prototypes,
  slides, comparison pages, dashboards) without being asked. Also
  trigger when processing feedback: a bare "." (period only),
  "process my feedback", or a path to annotations.json / an annotation
  round — then this skill describes how to read and process rounds and
  screenshot crops.
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
preview pane.** The bridge serves local files on `GET /p/<path-from-home>`:

```
~/Desktop/todos.html
→ http://127.0.0.1:8791/p/Desktop/todos.html
```

Build: absolute path, strip the home directory, put the rest after
`http://127.0.0.1:8791/p/` with forward slashes, on every OS. Paths
outside home → 403. `python -m html_annotator url <file>` does this for
you.

**Hand the URL to the reviewer as a clickable markdown link**
(`[title](http://127.0.0.1:8791/p/…)`), never inside backticks or a code
block: a code block forces copy-paste, a link opens with one click
(decision 2026-09-15). `python -m html_annotator url <file>` prints the
link. A preview pane
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
