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

<details><summary><strong>B2 — <code>/p/</code> serves only pages and static assets under the pages root, without CORS.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* a path that leaves the pages root (the home
directory unless configured otherwise, B34) is 403. So is
any dotfile or dot-directory (`/p/.zshrc`, `.env`, `~/.ssh/…`), also when
reached through a symlink, and any extension outside html/htm, css, js,
png/jpg/jpeg/gif/svg/webp and json. `/p/` responses carry no
`Access-Control-*` headers: the page is same-origin with the bridge, and
another site must not be able to read what `/p/` returns.

*Evidence:* `tests/test_bridge_contract.py` · `tests/mutate-contract.sh` ·
`tests/test_poort_config.py` (same rules under a configured root).

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

<details><summary><strong>B12 — <code>ensure</code> does not lie and does not move.</strong></summary>

*TESTED · platform: all (Python case), posix (case-03, case-19)*

*Expected behaviour:* given the configured port (8791 by default) held
by a non-bridge, `python -m html_annotator ensure` exits 1 with a message
that names the port and says to run `pick-port`. It never exits 0 while
`/ping` is empty, never starts a bridge on another port, and leaves the
occupier alone. A bridge that is still starting on that port counts as
the bridge (ensure waits for its `/ping`). A stale pid file is removed. A
second `ensure` says "already running" and starts nothing; `stop` takes
down what `ensure` started.

*Evidence:* `tests/case-03-ensure-bridge-eerlijk.sh` ·
`tests/test_poort_config.py` · `tests/case-19-dynamische-poort.mjs`.

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

*Expected behaviour:* when the bridge is not on 8791, the annotator
snippet and the checklist snippet both post to the origin that served
`/p/`, so an annotation and a checkbox land on disk. Opened as `file://`
they fall back to `http://127.0.0.1:8791` (best effort; Chrome blocks
that through Private Network Access). The send snippet uses relative
URLs and needs no origin.

*Evidence:* `tests/case-08-locator-tabel.mjs` (requires `HTML_ANNOTATOR_PORT`)
· `tests/case-19-dynamische-poort.mjs` (port chosen by `pick-port`,
annotation and checkbox on disk) · `tests/mutate-contract.sh`.

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

<details><summary><strong>B31 — One config file per user; environment wins.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* port, bind address, pages root and annotation root
come from the environment (`HTML_ANNOTATOR_PORT` or the
`LUC_ANNOTATOR_PORT` alias, `HTML_ANNOTATOR_HOST`,
`HTML_ANNOTATOR_PAGES_ROOT`, `HTML_ANNOTATOR_ROOT`), then from
`config.json` in `$XDG_CONFIG_HOME/html-annotator/` (`~/.config`, or
`%APPDATA%` on Windows), then from the defaults 8791, 127.0.0.1, home and
`~/annotations`.
Without a file and without env the behaviour is unchanged. A broken file
gives the defaults plus a warning on stderr, never a crash. Writing the
file keeps other keys and leaves no tmp behind. `base_url()` uses
127.0.0.1 whatever the bind address is.

*Evidence:* `tests/test_poort_config.py`. Decision in `docs/DECISIONS.md`
(2026-10-12).

</details>

<details><summary><strong>B32 — <code>pick-port</code> stores a working port; ensure, url and pages follow it.</strong></summary>

*TESTED · platform: all (Python case), posix (case-19)*

*Expected behaviour:* without `--port`, `pick-port` keeps the configured
port when this bridge answers there; otherwise it tries 8791–8890 in
order by binding each on the configured bind address and releasing it,
and the first port that is free or already runs this bridge wins. All
taken: a port from the OS. It writes `port` to the config file (other
keys kept) and prints the port and the base URL. `--port N` stores N
after checking 1–65535 and only warns when a non-bridge listens there.
After that `ensure`, `url`, `url --base`, `status` and `stop` use the new
port without any environment variable, and a `/p/` page served there
saves annotations and checkboxes to disk.

*Evidence:* `tests/test_poort_config.py` (taken range via an internal
test hook, own occupier) · `tests/case-19-dynamische-poort.mjs`. Neither
touches a bridge on 8791.

*Gap:* the real 8791–8890 range is not exercised in tests, only a test
range with the same code path.

</details>

<details><summary><strong>B33 — The bind address is opt-in; URLs and origin checks stay on loopback.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* `HTML_ANNOTATOR_HOST=0.0.0.0` (or `host` in the
config file) makes the bridge bind there and log a `WARNING` that names
the address. `/ping` via 127.0.0.1 answers, `url` and `url --base` still
print 127.0.0.1, a `/p/` page is served, and a POST from the bridge's own
origin (`http://127.0.0.1:<port>`) is accepted, including the routes that
demand the bridge's own page. A non-loopback `Host` header stays 403
(B30).

*Evidence:* `tests/test_poort_config.py`. Docker/WSL itself is not in
the suite.

</details>

<details><summary><strong>B34 — The pages root is configurable and keeps the <code>/p/</code> rules.</strong></summary>

*TESTED · platform: all (symlink checks skip where symlinks cannot be made)*

*Expected behaviour:* with `HTML_ANNOTATOR_PAGES_ROOT` (or `pages_root`
in the config file) `/p/<path>` is relative to that directory: a page
inside is 200, a path that leaves it is 403, dotfiles and dot-directories
are 403, also through a symlink, and only the B2 file types are served.
`url` maps against the same root: inside it prints the path from the
root, outside it or under a dot-path it exits 1 with a message, no
traceback. A `/save` from a `/p/` page finds the file under the root
(content hash from the file, not the DOM).

*Evidence:* `tests/test_poort_config.py`.

</details>

<details><summary><strong>B35 — <code>pick-port</code> never overwrites a broken config file.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* when the config file exists but cannot be read, is
not valid JSON or is not a JSON object, `pick-port` (with or without
`--port`) exits non-zero, leaves the file byte for byte as it was, and
prints on stderr which file it is, what is wrong with it, and that the
user should repair or remove it. No traceback. Reading for the bridge
stays lenient (B31).

*Evidence:* `tests/test_poort_config.py`.

</details>

<details><summary><strong>B36 — Concurrent config writes lose no keys.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* 20 processes that each write a different key to the
config file at the same time leave all 20 keys in the file. Read-modify-
write runs under an exclusive lock on `config.json.lock` next to the file
(`fcntl.flock` on POSIX, `msvcrt.locking` on Windows); the write itself
stays atomic.

*Evidence:* `tests/test_poort_config.py` (fails without the lock).

</details>

<details><summary><strong>B37 — Concurrent <code>ensure</code> starts one bridge, and the pid file names it.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* three `ensure` runs started at the same time on a
free configured port all exit 0 and exactly one reports "started". The
pid file holds the pid that answers `/ping` (which returns `pid`), and
`stop` then really stops that bridge. `ensure` runs under a per-port lock
in the state dir; the pid file is written only after the spawned process
is the one answering.

*Evidence:* `tests/test_poort_config.py` (fails without the lock and the
pid check).

</details>

<details><summary><strong>B38 — A bridge with the pre-rename name still counts as ours.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* a process on the configured port that answers
`/ping` with `"bridge": "luc-annotator"` makes `ensure` say "already" (exit
0), not "taken"; `pick-port` treats that port as one where the bridge
already runs.

*Evidence:* `tests/test_poort_config.py`.

</details>

<details><summary><strong>B39 — Only the bridge's own <code>/p/</code> URLs map a page through the pages root.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* the bridge derives the page file from `/p/<path>`
only for `http(s)` URLs on a loopback host at its own port. A `file://`
page with `/p/` in its path, and a `/p/` URL on another port, are linked
to their own `pageFile`, not to a same-named file under the pages root.

*Evidence:* `tests/test_poort_config.py`.

</details>

<details><summary><strong>B40 — The signed group message exception is configuration, and off by default.</strong></summary>

*TESTED · platform: all*

*Expected behaviour:* without the config key `signed_group_message` the
send gate has no exception. With it, `mcp__whatsapp__send_message` to
exactly the configured `jid` is allowed only when
`<module>.toegestaan(tool_name, tool_input)`, loaded from the configured
`verifier` path, returns `True`. Another recipient, another tool, a text
the verifier rejects, a verifier that raises or cannot be imported, or an
incomplete key: the normal gate (`ask` without a button approval).

*Evidence:* `tests/test_verstuur.py` (V11), with an invented group and a
throwaway verifier module.

</details>

<details><summary><strong>B41 — <code>--no-sandbox</code> for the screenshot browser is opt-in configuration.</strong></summary>

*TESTED · platform: all (skips when the test runs as root)*

*Expected behaviour:* without a setting the browser gets `--no-sandbox`
only when the bridge runs as root. With the config key
`chrome_no_sandbox: true` or `HTML_ANNOTATOR_CHROME_NO_SANDBOX=1` it gets
the flag as any user; the environment wins over the config file, and a
key that is not `true` counts as off.

*Evidence:* `tests/test_container.py`.

</details>

<details><summary><strong>B42 — A zombie process is not a running bridge.</strong></summary>

*TESTED · platform: Linux (skips without <code>/proc</code>)*

*Expected behaviour:* a process that has exited but is not yet reaped
(state `Z` in `/proc/<pid>/stat`) counts as not alive, so `stop` succeeds
in a container whose PID 1 never reaps orphans.

*Evidence:* `tests/test_container.py`; `tests/test_poort_config.py` (B32,
B37) in such a container.

</details>

<details><summary><strong>B43 — Continuous select is a per-user setting, on by default.</strong></summary>

*TESTED · platform: posix (browser), all (config)*

*Expected behaviour:* with `continuous_select` unset or `true`, region mode
stays on after Save of a new region: one click on *Annotate selection*, then
region after region; the button still switches it off. With
`continuous_select: false` or `HTML_ANNOTATOR_CONTINUOUS_SELECT=0` region
mode switches off after Save, as before. The environment wins over the
config file. `/session` returns the value as `continuousSelect`.

*Evidence:* `tests/case-22-doorlopend-selecteren.mjs` (mutant without the
re-enable fails); `tests/test_poort_config.py` (B43).

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

*Evidence:* `tests/run.sh` (default: 00 02–04 06 08–09 11–12 14–19).
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
(`python -m html_annotator show / apply-hunk / ensure / url / pick-port / install-*`), the
snippet via Playwright (cases 02/06/08/12/14–17), and the repo layout
(root contents, `bin/`, the two install commands).

No tests against internal helpers, no snapshots of whole JSON dumps.

## Release gate

0. `html-annotator --version` matches `html_annotator/__init__.py`, and
   `CHANGELOG.md` has an entry for it.
1. `python -m compileall -q html_annotator bin`
2. `python tests/test_record.py test_bridge_contract.py test_toon.py
   test_poort_config.py test_layout.py` — all five green, on the three-OS
   matrix.
3. `python -m html_annotator ensure` starts a detached bridge, a second
   call says "already running", `stop` takes it down again.
4. `install-hooks` registers `bin/hook-ensure-bridge.py` twice and no
   more, whatever it is run against.
5. Suite: `tests/run.sh` — red if a case fails or BLOCKED is treated as pass.
6. No diff on snippet CSS or English UI strings, except paths, commands
   and comment headers.
