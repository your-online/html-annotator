# Scope: what is core, what is an extra

The skill has to be installable by someone who is not its author, on
macOS, Linux or Windows, without inheriting a personal workflow. This
file says where the line is and why. Dated choices: `DECISIONS.md`.

## Core

Everything a stranger needs to annotate an HTML page and process the
feedback:

1. **The snippet** — `references/annotator-snippet.html`, one paste
   block: region and text annotations, refs/chips, the orphan list, the
   LA-SUGGEST layer, the status pill. Plus
   `references/checklist-snippet.html` (LA-CHECKLIST).
2. **The bridge** — `html_annotator/bridge.py`: rounds on disk, `/p/`
   file serving under the home directory, `GET /ping`, `POST /session`,
   `/save`, `/delete`, `/resolve`, `/remove-all`, `/state`,
   `/state-save`. `/sessie` (open a `claude://` link through the OS)
   stays as well: it is Claude Code generic, not personal, and the
   snippet's session links call it.
3. **The CLI** — `python -m html_annotator`: `serve`, `ensure`, `stop`,
   `status`, `show`, `resolve`, `apply-hunk`, `url`, `install-skill`,
   `install-hooks`. One entry point, no bash, no jq.
4. **The agent handbook** — `references/agent-handbook.md`, with
   `SKILL.md` as the thin port.

The checklist and suggest layers are core: they are generic review
mechanics, not one person's workflow.

## Extras (in `extras/`, not installed)

| what | why it is not core |
|---|---|
| `agent-handbook-extras.md` part 5 — spawning tasks from an HTML todo list | depends on the author's todo list, its numbering convention and a task-spawning skill that is not in this repo |
| part 6 — the draft message card (`la-draft`), tracked changes | a workflow for reviewing unsent messages; useful, but not what "annotate an HTML page" means, and it drags in a second skill (a messaging skill) |
| part 7 — nested sub-points (`la-sub`) | visual convention of one todo list |
| `tests/case-05`, `case-07`, `case-13` | they only cover those extras |
| `docs/refactor-plan-fase-0-2.md`, `docs/reviews/` | dated history of an earlier pass |

Deleted rather than moved: a personal todo-list finder script, and the todo-list tail
of the work rule printed by `show`.

**The snippet was not cut.** `la-draft` and `la-sub` keep their CSS and
JS inside `references/annotator-snippet.html`: it is one paste block by
decision (2026-08-23), and splitting it is a UI change, not a scope
change. What moved is their agent-facing documentation and their tests.
The consequence is deliberate: a page can still use those classes, but
the core contract does not promise them.

`apply-hunk` (`html_annotator/hunks.py`) stays core even though hunks
today only come from draft edits: it is a generic "apply one block of a
rewrite" tool, it is covered by `tests/case-06`, and the bridge keeps
storing `type: "edit"` records.

## Personal references

Agent-facing text names no person and points at no machine-specific
path (criterion A6, `tests/test_layout.py`). The annotation root is
configurable and defaults to `~/annotations`. Since 1.0.0rc1 the public
names are `window.HtmlAnnotator`, the `HTML-ANNOTATOR` markers, bridge
identity `html-annotator` and `HTML_ANNOTATOR_*`. The previous
generation is not deleted but kept as deprecated aliases until 1.1
(page-global alias, `LUC-ANNOTATOR` blocks, `LUC_ANNOTATOR_*`,
localStorage prefix `luc-annotaties`), because dropping them without a
migration orphans pages that already exist. See `CHANGELOG.md`.
