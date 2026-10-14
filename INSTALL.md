# INSTALL

Install this skill so it behaves the same on any machine: files, hooks, and
the deliver rule. Do not skip steps 2 and 3; those turn "the skill is there"
into "the skill works".

Everything runs through one CLI. No bash, no jq, so the steps are the same on
macOS, Linux and Windows.

## Fast path

As a package (recommended — nothing to clone, the CLI lands on your PATH):

```bash
pipx install git+https://github.com/your-online/html-annotator
html-annotator install-skill
html-annotator install-hooks
html-annotator pick-port
```

`pip install html-annotator` works too, and `pip install "html-annotator[crops]"`
adds Pillow for faster screenshot crops. From a checkout, `pip install -e .`
gives the same CLI against your working tree.

From a checkout without installing anything:

```bash
git clone https://github.com/your-online/html-annotator ~/repos/html-annotator
cd ~/repos/html-annotator
python -m html_annotator install-skill      # --copy on Windows
python -m html_annotator install-hooks
python -m html_annotator pick-port
```

`html-annotator <command>` and `python -m html_annotator <command>` are the
same entry point; the rest of this file uses the second form because it also
works straight from a checkout.

All three commands are idempotent. Still do step 3 and step 4 by hand.

Agent rules live in `SKILL.md` and `references/`. No memories are copied.

## Step 1 — skill on disk

The skill must be reachable as `~/.claude/skills/html-annotator/`.

```bash
python -m html_annotator install-skill          # symlink to this checkout
python -m html_annotator install-skill --copy   # copy instead
```

A symlink is preferred: an update is one `git pull`. On Windows a symlink
needs Developer Mode or admin rights, so `--copy` is the default there. If
something else already sits on that path, the command says so and leaves it
alone.

From a pip/pipx install there is no checkout to link to, so the command copies
the skill files that ship inside the package — `SKILL.md`, `references/` and
the `bin/` wrappers — into that directory. Updating means `pipx upgrade
html-annotator` followed by `html-annotator install-skill` again.

## Step 2 — register the two hooks

These keep the bridge up. Without them, someone has to run
`python -m html_annotator ensure` by hand, and "why did nothing save" is
almost always "the bridge was down".

```bash
python -m html_annotator install-hooks           # writes the two hooks
python -m html_annotator install-hooks --print   # show, change nothing
```

That writes into `~/.claude/settings.json` (a timestamped backup lands
next to it) two entries that both call `bin/hook-ensure-bridge.py` with the
same Python that ran the command:

- **SessionStart**, empty matcher — one call per session, whatever route that
  session later uses to write HTML. This is the layer that counts: the
  PostToolUse layer misses an agent that writes the file through Bash, and in
  auto-mode Bash is the prescribed route.
- **PostToolUse on `Edit|Write`** — starts the bridge when the written file is
  `.html`/`.htm` and carries an annotator marker (`HTML-ANNOTATOR`, or the
  older `LUC-ANNOTATOR` on pages embedded before the rename).

Other hooks under those events stay; only an earlier annotator hook is
replaced. The empty-matcher SessionStart hook fires on every agent session on
the machine, including sessions that never touch annotations. That is on
purpose: one ping per session. If the owner wants it narrower, that is their
call — do not narrow it unasked.

## Step 2b — choose the port

```bash
python -m html_annotator pick-port             # search and store
python -m html_annotator pick-port --port 8800 # store this one
```

Nothing to configure by hand. `pick-port` tries 8791–8890 by actually binding
each port on the configured bind address and releasing it again; the first
free port wins. A port where this bridge already answers counts as good, so on
a machine that already runs the bridge it keeps that port. When the whole
range is taken, the OS hands out a port. The choice is written as `port` into
the per-user config file (other keys stay), and the command prints the port and
the base URL. Run it after installing and whenever `ensure` reports that the
port is taken by something that is not the bridge: `ensure` never moves to
another port on its own.

**For an agent doing the install:** if `pick-port` fails, find a free port
yourself (any port nothing listens on) and store it with
`python -m html_annotator pick-port --port N`. Never edit URLs or snippets to
match a port: `python -m html_annotator url <file>` and `url --base` always
print the right one.

With `--port N` the port is validated (1–65535) and stored without a search;
it only warns when something other than the bridge listens there.

## Step 3 — deliver rule in the global instructions

The strongest trigger is not in the skill but in the global instructions. Put
a rule like this in `~/.claude/CLAUDE.md`, adapted to how the owner wants it:

```markdown
## Deliverables

Mails, plans, analyses and other write-ups ship as HTML via the
`html-annotator` skill, not as chat text, so they can take inline and
selection comments.
```

Ask before writing that — it touches every project.

## Step 4 — verify

```bash
python -m html_annotator --version
python -m html_annotator ensure
python -m html_annotator status
```

Expected: `{"ok": true, "bridge": "html-annotator", "version": 2, "release":
"1.0.0rc1", ...}`. `version` is the wire protocol the snippet speaks;
`release` is the package version.

Run the suite (Node + Playwright; install once):

```bash
cd tests && npm i --no-save playwright-core && cd ..
tests/run.sh
```

Two limits, also in `CRITERIA.md`: the fresh-agent case has never been
verified in practice (it reports BLOCKED, not pass), and the hidden-panel
variant emulates `document.hidden`, so it tests branch logic, not Chrome
throttling.

The test that counts: make an HTML file with the snippet, open it via
`python -m html_annotator url <that file>`, drag a rectangle, type a comment,
Save. There should now be an `annotations.json` plus a crop under
`~/annotations/<slug>/ronde-01/`.

## Configuration

Precedence, highest first: environment variable > per-user config file >
default.

| variable | config key | meaning | default |
|---|---|---|---|
| `HTML_ANNOTATOR_PORT` | `port` | port of the bridge | `8791` |
| `HTML_ANNOTATOR_HOST` | `host` | address the bridge binds to | `127.0.0.1` |
| `HTML_ANNOTATOR_PAGES_ROOT` | `pages_root` | directory `/p/` serves pages from | home directory |
| `HTML_ANNOTATOR_ROOT` | – | where rounds are written | `~/annotations` |
| – | `mail_servers` | sender account → MCP server for the Send button, e.g. `{"you@example.com": "ms365"}` | none (mail cards then fall back to asking in chat) |
| – | `signed_group_message` | optional send-gate exception for one WhatsApp group whose messages an external verifier signs: `{"jid": "120363000000000000@g.us", "verifier": "~/path/to/verifier-repo", "module": "package.module", "label": "example signed message"}` (see `docs/verstuur-knop-onderzoek.md`) | none (no exception: the normal gate) |
| `HTML_ANNOTATOR_CHROME` | – | browser used for crops | auto-detected |

The config file is `~/.config/html-annotator/config.json`
(`$XDG_CONFIG_HOME/html-annotator/config.json` if that is set,
`%APPDATA%\html-annotator\config.json` on Windows), for example
`{"port": 8792}`. `pick-port` writes it; all keys are optional. A broken or
unreadable file is ignored with a warning on stderr, so the bridge still
starts on the defaults. `pick-port` never overwrites such a file: it exits
with an error naming the file and the problem; repair or remove it yourself.
Writes are serialised with a lock file next to it (`config.json.lock`), so
concurrent writers do not lose each other's keys.

`HTML_ANNOTATOR_HOST` only changes where the socket listens. The URLs the CLI
prints, the `/ping` check and the origins the bridge accepts stay on
127.0.0.1/localhost at the bridge's own port. Any address other than loopback
makes the bridge log a `WARNING`, because the port is then reachable from the
network unless a firewall or a port mapping stops it. Only set it for a
container (see Docker below).

`HTML_ANNOTATOR_PAGES_ROOT` moves what `/p/` serves: the path after `/p/` is
relative to that directory, and the existing rules hold relative to it —
nothing outside it, no dotfile or dot-directory (also not through a symlink),
only html/htm, css, js, images and json. `python -m html_annotator url <file>`
maps against the same root, so a link it prints always opens.

The `LUC_ANNOTATOR_PORT`, `LUC_ANNOTATOR_ROOT` and `LUC_ANNOTATOR_CHROME`
names are **deprecated aliases**. They are still read, so a running setup does
not break mid-session, and they go away in 1.1.

On a machine that already uses the older annotation folder on the desktop and
has no `~/annotations`, that old directory stays the default, so an upgrade
orphans nothing. Pid file and log live in a per-user state directory
(`~/.local/state/html-annotator`, `%LOCALAPPDATA%\html-annotator` on Windows),
never inside the checkout.

## Deprecated names kept until 1.1

| deprecated | use instead |
|---|---|
| `bin/toon-annotaties.py` | `bin/show-annotations.py` · `html-annotator show` |
| `bin/pas-hunk-toe.py` | `bin/apply-hunk.py` · `html-annotator apply-hunk` |
| the old page-global annotator object | `window.HtmlAnnotator` (the snippet still assigns the old name as an alias) |
| `LUC_ANNOTATOR_*` | `HTML_ANNOTATOR_*` |
| `<!-- LUC-ANNOTATOR v2 -->` blocks | `<!-- HTML-ANNOTATOR v3 -->`; old blocks stay recognised |

The full table, including what to change in your own scripts, is the
migration section of `CHANGELOG.md`.

## Upgrading from an older install

Re-run `install-skill` and `install-hooks`. The hook entries from the bash era
are replaced, not duplicated. The four shell scripts (`ensure-bridge`,
`hook-ensure-bridge`, `install`, the todo-list finder) are gone; the `bin/*.py`
files that remain are thin wrappers around the CLI.

Pages that already carry a `LUC-ANNOTATOR` block keep working: the bridge, the
hooks and the content hash still recognise both marker generations. Re-embed a
page only when you want the new markers, and never leave two blocks in one
page.

The old installer placed memories. Those are no longer in this skill. If they
still sit under `~/.claude/projects/*/memory/`, they are
`annotator-bridge-autostart.md` and `html-annotator-standaard.md`. Do not
delete them automatically — they are project rules.

## Requirements

- **python3** (3.9+, stdlib is enough) — the bridge runs on it.
- **Chrome or Edge** — for screenshot crops. Found via
  `HTML_ANNOTATOR_CHROME`, then PATH, then the usual install paths. Without
  either, region annotations store without a crop.
- **Pillow** (optional) — faster crops; `pip install "html-annotator[crops]"`.
- **Node** (optional) — only for the Playwright suite.
- A free port. **8791** by default (8080 is often Docker); `pick-port`
  chooses another one when 8791 is taken.

## Windows

The bridge, the CLI and the hooks are plain Python and run natively: Chrome or
Edge is found in the usual places, `claude://` links open through the shell,
`/p/<path-from-pages-root>` takes forward slashes in the URL and maps them to
backslashes on disk, and page slugs stay filesystem-safe. CI runs the Python
tests and a real `/save` on `windows-latest`.

In PowerShell use `py -3 -m html_annotator …` (or `html-annotator …` after a
pip/pipx install) and pass `--copy` to `install-skill`, because a symlink
needs Developer Mode. In Git Bash the macOS/Linux commands work as written,
with `--copy` for the same reason.

What is not covered there: the Playwright suite (`tests/run.sh`) is only
exercised on macOS and Linux, and if the Microsoft Store `python3` alias gets
in the way, disable it.

## Docker / WSL

The bridge can run in a container, for example Docker inside WSL on Windows,
with the browser on the host. Three things differ from a local install:

- **Bind to all interfaces inside the container:** `HTML_ANNOTATOR_HOST=0.0.0.0`.
  The bridge logs a warning for that; publish the port on the host's loopback
  only (`-p 127.0.0.1:8791:8791`) so the network cannot reach it. Use
  `0.0.0.0`, not a specific non-loopback address such as the container's own
  IP: `ping`, `status` and `ensure` always look for the bridge on 127.0.0.1, so
  with a bind on one specific address they do not find it.
- **Same port inside and outside.** The port inside the container must equal
  the published host port in the `-p` mapping, because pages and the bridge
  compare origins on that port. Set it explicitly with
  `HTML_ANNOTATOR_PORT=<port>` or `pick-port --port <port>`; do not let
  `pick-port` search inside a container, it only sees the container's ports.
- **Pages root on a mount:** mount the directory with your pages and point
  `HTML_ANNOTATOR_PAGES_ROOT` at it; `/p/<path>` is then relative to that mount.
- **Screenshot browser without root:** a container that runs as a normal user
  with all capabilities dropped gives Chrome no usable sandbox ("No usable
  sandbox!"), and region annotations land without a screenshot. Set
  `HTML_ANNOTATOR_CHROME_NO_SANDBOX=1` or `"chrome_no_sandbox": true` in the
  config file; as root the bridge adds `--no-sandbox` by itself. Without an
  init process as PID 1 (`docker run` without `--init`) a stopped bridge
  stays behind as a zombie; the bridge treats that as stopped, `--init`
  cleans it up.

```bash
docker run -p 127.0.0.1:8791:8791 \
  -e HTML_ANNOTATOR_HOST=0.0.0.0 -e HTML_ANNOTATOR_PORT=8791 \
  -e HTML_ANNOTATOR_PAGES_ROOT=/pages -v "$HOME/pages:/pages" \
  -e HTML_ANNOTATOR_ROOT=/annotations -v "$HOME/annotations:/annotations" \
  <image> python -m html_annotator serve
```

Open pages via `http://127.0.0.1:8791/p/<path-under-/pages>` or
`http://localhost:8791/...` on the host. Not via the container's IP or the WSL
IP (for example `http://172.x.x.x:8791`): the bridge answers those with 403 on
purpose, because its Host and Origin checks accept loopback names only.
A page opened as `file://` falls back to `http://127.0.0.1:8791` as best
effort, but Chrome blocks `file://` pages from reaching loopback anyway
(Private Network Access); serve pages through `/p/`.

## What this repo deliberately does not ship

- The annotation root (`~/annotations`) — user data, created on first save.
- Skills that the handbook mentions but that are not in this repo:
  a session-start skill (`POST /sessie`), and a messaging skill that drives the
  Send button (see `docs/verstuur-knop-onderzoek.md`). The annotator works
  without them; say so instead of failing silently.
- The owner's personal glue — see `extras/README.md` and `docs/SCOPE.md`.
