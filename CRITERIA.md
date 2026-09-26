# Criteria

An annotation the reviewer places lands on disk and does not disappear
after a restart, a reload, or an edit elsewhere on the page. Pages open
via `/p/`. The repo is a skill someone else can install, without
personal workflow files.

Proof is `<annotation-root>/<slug>/ronde-NN/annotations.json`, not the
chat. `tests/run.sh` covers a **subset**. A BLOCKED case never counts as
green. Dated choices: `docs/DECISIONS.md`. Where the scope line runs:
`docs/SCOPE.md`.

Every criterion below carries two labels:

- **TESTED** — an automated case fails when the behaviour breaks.
  **UNTESTED** — believed to hold, but nothing catches a regression.
- **platform: all / posix / windows** — where the evidence was
  collected. `all` means the Python tests run on the three-OS CI matrix;
  `posix` means the evidence is a Playwright or shell case that only
  runs on macOS and Linux.

## Out of scope

- Model behaviour (agent pastes the snippet / calls resolve) is not
  enforceable by the suite.
- A sideviewer is allowed, but only via `/p/`, never as `file://`/`data:`.
- Chrome throttling of a real background tab is untested.
- The draft card (`la-draft`) and `la-sub` left the contract in the F0
  pass: their CSS and JS still ship inside the snippet, their criteria
  sit in `extras/CRITERIA-extras.md` (B13, B15, B24, B25) and their
  cases in `extras/tests/`. See `docs/SCOPE.md`.
- Public names as of 1.0.0rc1: `window.HtmlAnnotator`, the markers
  `<!-- HTML-ANNOTATOR v3 -->` … `<!-- /HTML-ANNOTATOR -->`, bridge
  identity `html-annotator`, env `HTML_ANNOTATOR_*`. The previous
  generation stays readable and is kept as a deprecated alias until 1.1:
  the old page-global, `<!-- LUC-ANNOTATOR -->` blocks (content hash and
  hooks still recognise them), `LUC_ANNOTATOR_*`, and the localStorage
  prefix `luc-annotaties`, which does not change at all. Migration table:
  `CHANGELOG.md`.

## Functional requirements

<details><summary><strong>B1 — <code>/ping</code> returns 200, OPTIONS 204, no CORS <code>*</code>.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `GET /ping` answers; a preflight from an allowed
origin is 204. CORS echoes the allowed origin, never `*` (see B30).

*Evidence:* `tests/test_bridge_contract.py`.

*Gap:* no mutation on identity.

</details>

<details><summary><strong>B2 — <code>/p/</code> serves only pages and static assets under home, without CORS.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* a path that leaves the home directory is 403. So is
any dotfile or dot-directory (`/p/.zshrc`, `.env`, `~/.ssh/…`), also when
reached through a symlink, and any extension outside html/htm, css, js,
png/jpg/jpeg/gif/svg/webp and json. `/p/` responses carry no
`Access-Control-*` headers: the page is same-origin with the bridge, and
another site must not be able to read what `/p/` returns.

*Evidence:* `tests/test_bridge_contract.py` · `tests/mutate-contract.sh`.

</details>

<details><summary><strong>B3 — POST <code>/session</code> <code>/save</code> <code>/delete</code> <code>/remove-all</code> <code>/resolve</code> <code>/sessie</code> exist; <code>/resolve</code> sets <code>resolved</code> on disk.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* each route answers; resolve writes `resolved` on
the record.

*Evidence:* `tests/test_bridge_contract.py` · mutate (resolve-noop).

*Gap:* no mutation per remaining route.

</details>

<details><summary><strong>B4 — A round is never overwritten; a new round only after <code>/remove-all</code>.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* a second save stays in the current round; a new
`ronde-NN` appears only after remove-all.

*Evidence:* `tests/test_bridge_contract.py` · `tests/mutate-contract.sh`.

</details>

<details><summary><strong>B5 — <code>contentHash</code> ignores the annotator block.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* editing only the snippet does not change the page hash.

*Evidence:* `tests/test_bridge_contract.py` · `tests/mutate-contract.sh`.

</details>

<details><summary><strong>B6 — A crop failure still stores the annotation.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* when `maak_crop` raises, the JSON record is still written.

*Evidence:* `h_save` with a raising crop (no live Chrome) · mutate.

</details>

<details><summary><strong>B7 — JSON write is atomic (tmp + replace); a dump error leaves the original.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* a failed dump does not truncate `annotations.json`.

*Evidence:* `tests/test_bridge_contract.py` (direct `schrijf`). Tmp cleanup is B21.

</details>

<details><summary><strong>B8 — <code>show --open</code> prints the work rule, expands refs, shows locator.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* open items include the work rule, resolved refs, and the locator.

*Evidence:* `tests/test_toon.py` · mutate (work rule).

*Gap:* refs and locator are not mutated.

</details>

<details><summary><strong>B9 — Missing refs: do not guess, do warn.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `refsIncomplete` asks to save again; the CLI does not invent a target.

*Evidence:* `tests/test_toon.py` · `tests/test_record.py`.

*Gap:* no mutation.

</details>

<details><summary><strong>B10 — Pill self-heals and a later save lands on disk.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* given a page that is already open while the bridge
is down, when the bridge comes up the pill flips to `X saved` within 10s
without a reload, and a save after that lands in `annotations.json`.
The hidden-panel variant emulates `document.hidden`; it does not
measure Chrome timer throttling (B19).

*Evidence:* `tests/case-02-selfheal.mjs`.

*Gap:* no contract mutation.

</details>

<details><summary><strong>B11 — SessionStart brings the bridge up.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* given the hooks written by
`python -m html_annotator install-hooks`, a route exists that starts the bridge without depending on how the agent writes
the file, and the `Edit|Write` route still works. SessionStart covers
Bash writes; the matcher is not widened to every Bash call.

*Evidence:* `tests/case-04-bridge-omhoog-los-van-schrijfroute.sh`.

*Gap:* no contract mutation.

</details>

<details><summary><strong>B12 — <code>ensure</code> does not lie.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* given port 8791 held by a non-bridge,
`python -m html_annotator ensure` ends with a live answering bridge or a
non-zero exit — never exit 0 while `/ping` is empty. A stale pid file is
removed. A second `ensure` says "already running" and starts nothing;
`stop` takes down what `ensure` started.

*Evidence:* `tests/case-03-ensure-bridge-eerlijk.sh`.

*Gap:* no contract mutation.

</details>

<details><summary><strong>B14 — Hunks are independently applicable.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* each contiguous edit is its own hunk with
surrounding text as the anchor. Hunks apply and resolve independently.
The edit is done only when no hunk is open.

*Evidence:* `tests/case-06-hunks.mjs` · `html_annotator/hunks.py`.

*Gap:* no contract mutation.

</details>

<details><summary><strong>B16 — Locator survives a row insert; orphan only when the text is gone; repeated cell text stays on the labeled row.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* inserting a row above does not move the mark;
deleting the text orphans it; two identical cells keep the mark on the
row the locator named.

*Evidence:* `tests/case-08-locator-tabel.mjs` · `tests/mutate-contract.sh`.

*Gap:* no real client page in the repo.

</details>

<details><summary><strong>B17 — Sideviewer origin.</strong></summary>

*UNTESTED · platform: posix (manual, 2026-08-18)*

*Expected behaviour:* opening a file in the sideviewer is a `data:`
snapshot and cannot reach the bridge. The same page via `/p/` works,
including self-heal.

*Evidence:* `tests/sideview-test.sh` (manual). Measured 2026-08-18.

</details>

<details><summary><strong>B18 — A fresh agent pastes the snippet.</strong></summary>

*UNTESTED · platform: posix (BLOCKED)*

*Expected behaviour:* a fresh agent asked to ship HTML via Bash starts
the bridge (new pid) and includes the `LUC-ANNOTATOR` marker. All runs
must pass.

*Evidence:* `tests/case-01`. Currently BLOCKED on a spend limit; not in
default `tests/run.sh`.

</details>

<details><summary><strong>[gap]</strong> <s>B19 — Chrome throttling of a real background tab.</s> — untested, leave it.</summary>

*Evidence:* not collected.

</details>

<details><summary><strong>[gap]</strong> <s>B20 — The model pastes the snippet / calls resolve.</s> — not enforceable.</summary>

*Evidence:* not collected.

</details>

<details><summary><strong>B21 — A dump error removes the <code>.tmp</code>.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* after a failed dump the leftover tmp file is gone.

*Evidence:* `tests/test_bridge_contract.py` · mutate (`os.remove`).

</details>

<details><summary><strong>B22 — A page under <code>/p/</code> on a non-default port talks to that port.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* when the bridge is not on 8791, the snippet still
posts to the port that served `/p/`.

*Evidence:* `tests/case-08-locator-tabel.mjs` (requires `HTML_ANNOTATOR_PORT`)
· `tests/mutate-contract.sh`.

</details>

<details><summary><strong>B26 — Checklist state persists per page, outside the rounds.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `POST /state-save` with `{component, key, value}`
merges the value over the existing entry, stamps `changedAt` on the entry
and `updatedAt` on the whole, and writes `<slug>/state.json` next to the
`ronde-NN` dirs — never inside one. `POST /state` reads it back; an unknown
page yields empty `components`, a save with no `key` is a 400. Checked
state is a lasting status, not a feedback round: `remove-all` does not
touch it. Snippet: `references/checklist-snippet.html` (LA-CHECKLIST).

*Evidence:* `tests/test_bridge_contract.py`.

</details>

<details><summary><strong>B27 — A LA-SUGGEST "change" is editable, and pending keeps the typed text.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* opening the ✎ popup for a suggestion that already
carries a `change` decision prefills the comment field with the stored
comment (chips included) and puts the caret behind it; saving replaces the
decision instead of stacking one. Clicking the orange badge still returns
the suggestion to pending, but keeps `comment`/`refs`/`commentExpanded` in
`state.json`, so the text is still there after a reload — the prefill comes
from `POST /state`, not from an in-memory variable. `accepted` and
`rejected` drop the text, so a processing agent never finds a dead change
comment on an accepted key.

*Evidence:* `tests/case-14-suggest-change-bewerken.mjs`; decision in
`docs/DECISIONS.md` (2026-08-31).

</details>

<details><summary><strong>B28 — A suggestion that becomes visible later gets its pill on its own.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* an element with `data-la-suggest` that is hidden at
load (a collapsed table group, an inline `display:none`) or inserted into
the DOM later shows its rects and pill as soon as it becomes visible — no
other interaction needed, also when the page itself does not resize because
the table sits in its own `overflow:auto` scroller. Redrawing settles: the
layer's own nodes never trigger another redraw.

*Evidence:* `tests/case-15-suggest-zichtbaar.mjs`; decision in
`docs/DECISIONS.md` (2026-08-31).

</details>

<details><summary><strong>B29 — One suggest key is one suggestion with one pill.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* elements sharing a `data-la-suggest` key are drawn as
one visual group — every rect highlighted — with exactly one pill, because
the decision is stored per key. Elements with different keys keep their own
pill and decide independently: accepting one leaves the other pending, and
`state.json` only carries the key that was clicked.

*Evidence:* `tests/case-16-suggest-gedeelde-key.mjs` ·
`tests/case-17-suggest-losse-keys.mjs`; decision in `docs/DECISIONS.md`
(2026-08-31).

</details>

<details><summary><strong>B30 — Only loopback, <code>file://</code> and <code>null</code> origins reach the bridge.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* a request with an `Origin` other than
`http(s)://127.0.0.1|localhost|[::1]` (any port), `file://` or `null` is
403 before any handler runs, so a cross-site `no-cors` POST has no side
effect either. A request without `Origin` (curl, hooks, CLI) is allowed.
A `Host` header that is not a loopback name is 403 (DNS rebinding).
Allowed origins get their own origin back in `Access-Control-Allow-Origin`.

*Evidence:* `tests/test_bridge_contract.py` · `tests/mutate-contract.sh`.
Decision in `docs/DECISIONS.md` (2026-09-26).

*Gap:* `null` stays allowed for pages opened as a file; a site can also
send `null` from a sandboxed iframe.

</details>

<details><summary><strong>B23 — Region and text boxes scroll with the HTML they mark, including inside an <code>overflow:auto</code> scroller.</strong></summary>

*TESTED · platform: posix*

*Expected behaviour:* after the marked row moves in a nested scroller, the
box and badge sit on that row — not at the same viewport coordinates.
Window-scroll still follows too.

*Evidence:* `tests/case-12-scroll-mee.mjs` (listener mutant included).

</details>

## Architecture

<details><summary><strong>A1 — Root holds only ports.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* root files are README, SKILL, INSTALL, CRITERIA,
`.gitignore`. Directories: `html_annotator/` `bin/` `references/`
`tests/` `docs/` `extras/`. Snippet lives in `references/`. Gitignored
runtime does not count, and `install-skill` does not copy it.

*Evidence:* `tests/test_layout.py`.

</details>

<details><summary><strong>A2 — No <code>memories/</code>. Agent rules live in <code>references/</code>.</strong></summary>

*TESTED · platform: all*

*Evidence:* `tests/test_layout.py`.

</details>

<details><summary><strong>A3 — <code>extras/</code> is documented and never installed.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `extras/README.md` says what is in there and that
it is not part of the install; `docs/SCOPE.md` says why; `install-skill`
leaves `extras/` out of the copy.

*Evidence:* `tests/test_layout.py`.

</details>

<details><summary><strong>A4 — CLIs and hooks live in <code>bin/</code> as thin wrappers; <code>install-hooks</code> points there; a <code>bin/&lt;name&gt;.py</code> string in agent-facing docs names a file that exists.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `install-hooks` registers exactly two entries
(SessionStart + PostToolUse on `Edit|Write`), both calling
`bin/hook-ensure-bridge.py` with an absolute Python path, both
idempotent, `--print` writing nothing.

*Evidence:* `tests/test_layout.py` · `tests/mutate-layout.sh` (invented name).

</details>

<details><summary><strong>A5 — Python modules: <code>snake_case</code>. Scripts in <code>bin/</code>: kebab-case.</strong></summary>

*TESTED · platform: all*

*Evidence:* `tests/test_layout.py`.

</details>

<details><summary><strong>A6 — Agent-facing text names no person.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* the allowlist covers identifiers that carry
behaviour: the deprecated page-global alias, `LUC-ANNOTATOR` markers,
`luc-annotaties` and `LUC_ANNOTATOR_*`. Exempt: `docs/DECISIONS.md` and
`extras/`.

*Evidence:* `tests/test_layout.py` · `tests/mutate-layout.sh`.

</details>

<details><summary><strong>A7 — The functional criteria stay green.</strong></summary>

*TESTED · platform: posix (full suite), all (Python cases)*

*Evidence:* `tests/run.sh` (default: 00 02–04 06 08–09 11–12 14–17).
`00 09 11` run without a browser and are the three-OS CI set. The suite
header prints `git rev-parse --short HEAD` and a dirty-tree count.

</details>

<details><summary><strong>A8 — Root ports are English.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `SKILL.md`, `README.md`, `INSTALL.md` and
`CRITERIA.md` have no Dutch function-word leftovers. Since 1.0.0rc1 the
snippet UI, the bridge log lines, the CLI output and the work-rule box
printed by `show` are English too (`docs/DECISIONS.md`, 2026-09-17).
`references/agent-handbook.md` is still Dutch and is the one remaining
surface waiting for a dedicated translation pass.

*Evidence:* `tests/test_layout.py` · `tests/mutate-layout.sh`.

</details>

<details><summary><strong>A9 — No bash in the core.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* install, hooks, bridge and CLIs are one Python
entry point (`python -m html_annotator`). No `.sh` outside `tests/`
(Playwright runner) and `extras/`. A Windows user needs neither Git Bash
nor jq.

*Evidence:* `tests/test_layout.py` (A9) · CI matrix on
`windows-latest`.

</details>

<details><summary><strong>A10 — The package installs, reports its version, and carries the snippet.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `pyproject.toml` builds the distribution
`html-annotator` with the console script `html-annotator` and no runtime
dependencies (`[crops]` adds Pillow). The version sits in exactly one
place, `html_annotator/__init__.py`; `pyproject.toml` reads it
dynamically, `html-annotator --version` and `python -m html_annotator
--version` print it, and `/ping` returns it as `release`. `pip install
-e .` into a fresh venv gives a working console script, and
`install-skill` also works from an installed package instead of only
from a checkout. `LICENSE` and `CHANGELOG.md` exist and the changelog
names this version.

*Evidence:* `tests/test_layout.py` (A10 checks, including the venv
install; it prints SKIP instead of PASS when no venv or no network is
available) · `tests/test_bridge_contract.py` (B1 `release`).

*Gap:* a published wheel from PyPI is not exercised; the venv case
installs from the working tree.

</details>

<details><summary><strong>A11 — One source for the snippets.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `references/` is the only copy of
`annotator-snippet.html`, `checklist-snippet.html` and
`suggest-snippet.html` in the repo. The build maps that directory into
the wheel as `html_annotator/snippets/`, so the snippet is importable at
runtime (`html_annotator.config.snippet_path()`), and a second copy in
the tree is only allowed when it is byte-identical — a drifting copy
fails.

*Evidence:* `tests/test_layout.py` (A11 checks).

</details>

## Seams

Tests only touch these edges: the bridge HTTP API, the CLI
(`python -m html_annotator show / apply-hunk / ensure / install-*`), the
snippet via Playwright (cases 02/06/08/12/14–17), and the repo layout
(root contents, `bin/`, the two install commands).

No tests against internal helpers, no snapshots of whole JSON dumps.

## Release gate

0. `html-annotator --version` matches `html_annotator/__init__.py`, and
   `CHANGELOG.md` has an entry for it.
1. `python -m compileall -q html_annotator bin`
2. `python tests/test_record.py test_bridge_contract.py test_toon.py
   test_layout.py` — all four green, on the three-OS matrix.
3. `python -m html_annotator ensure` starts a detached bridge, a second
   call says "already running", `stop` takes it down again.
4. `install-hooks` registers `bin/hook-ensure-bridge.py` twice and no
   more, whatever it is run against.
5. Suite: `tests/run.sh` — red if a case fails or BLOCKED is treated as pass.
6. No diff on snippet CSS or English UI strings, except paths, commands
   and comment headers.
