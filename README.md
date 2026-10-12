# html-annotator

Visual HTML annotation for agentic work. Paste one self-contained block at the
bottom of any HTML page and the page becomes annotatable: drag a region, select
text, link one passage to another, type a comment, Save. The feedback lands on
disk as JSON plus screenshot crops, next to the page it belongs to — not in a
chat log that the next session has to reconstruct.

The other half is a local bridge: a stdlib-only Python HTTP server on
127.0.0.1 that receives what the page saves, keeps rounds, cuts the crops and
serves the page itself so the browser and the bridge share an origin. An agent
starts it with one idempotent command, hands the reviewer a link, and processes
the round later with `show` → edit → `resolve`. No libraries, no CDN, no
bundler; macOS, Linux and Windows run the same commands.

## Quick start (5 minutes)

**1. Install** (any OS, needs Python 3.9+):

```bash
pipx install git+https://github.com/your-online/html-annotator
html-annotator install-skill
html-annotator install-hooks
html-annotator pick-port      # stores a free port (8791 when it is free)
```

Per OS, if you prefer a checkout over pipx:

<table>
<tr><th>macOS / Linux</th><th>Windows (PowerShell)</th><th>Windows (Git Bash)</th></tr>
<tr><td>

```bash
git clone https://github.com/your-online/html-annotator \
  ~/repos/html-annotator
cd ~/repos/html-annotator
python3 -m html_annotator install-skill
python3 -m html_annotator install-hooks
python3 -m html_annotator pick-port
```

</td><td>

```powershell
git clone https://github.com/your-online/html-annotator `
  $HOME\repos\html-annotator
cd $HOME\repos\html-annotator
py -3 -m html_annotator install-skill --copy
py -3 -m html_annotator install-hooks
py -3 -m html_annotator pick-port
```

</td><td>

```bash
git clone https://github.com/your-online/html-annotator \
  ~/repos/html-annotator
cd ~/repos/html-annotator
python -m html_annotator install-skill --copy
python -m html_annotator install-hooks
python -m html_annotator pick-port
```

</td></tr>
</table>

**2. Start the bridge and check it.**

```bash
html-annotator ensure       # idempotent: does nothing if it is already up
html-annotator status       # {"ok": true, "bridge": "html-annotator", ...}
```

**3. Make a page annotatable.** Paste the whole of
`references/annotator-snippet.html` just before the **last** `</body>` (see
`SKILL.md` for why the last one).

**4. Open it through the bridge**, never as `file://` and never in a preview
pane:

```bash
html-annotator url ~/Desktop/plan.html
# http://127.0.0.1:8791/p/Desktop/plan.html   (8791 is the default port)
```

**5. Annotate and process.** Drag, comment, Save. Then, in the agent session,
`html-annotator show --open` prints the open round, and
`html-annotator resolve <slug> --nrs 1,3` checks items off.

## The `/p/` rule

Pages open on `http://127.0.0.1:<port>/p/<path-from-pages-root>`. Do not build
that URL by hand: `html-annotator url <file>` knows the port (8791 by default,
see `pick-port`) and the pages root (the home directory by default). Anything
outside the pages root, and any dotfile or dot-directory, is refused with 403.

This is not a preference. A page opened as `file://` or rendered in a preview
pane as a `data:` document sits on an origin that cannot reach loopback
(Private Network Access), so every Save fails silently into localStorage.
Through `/p/` the page is same-origin with the bridge and everything works,
including the self-heal that flips the status pill when the bridge comes up
later. Hand the link that `url` prints over as a clickable markdown link, not
inside backticks.

## The agent workflow

```
embed snippet ──► ensure ──► hand over /p/ link ──► reviewer annotates
                                                          │
   resolve ◄──── apply the feedback ◄──── show --open ◄────┘
```

- **`.`** — a bare period from the reviewer means "process my feedback". No
  confirmation question; find the open round yourself.
- **show** — `html-annotator show --open` picks the most recently annotated
  page with open items (7-day window; `--list`, `--search`, `--since` widen
  it) and reprints the work rule: understand first, ask when a comment is
  ambiguous, then edit.
- **process** — region annotations carry a crop to read, text annotations carry
  `selectedText` plus a locator, `edit` annotations carry hunks that
  `html-annotator apply-hunk` places one by one.
- **resolve** — `html-annotator resolve <slug> --nrs 1,3` (or `POST /resolve`).
  Processing without resolving is not done: the annotation loses its anchor and
  comes back every round.

Full rules: [SKILL.md](SKILL.md) (the thin port) and
[references/agent-handbook.md](references/agent-handbook.md) (the source of
truth).

## Commands

| command | role |
|---|---|
| `serve` | bridge in the foreground |
| `ensure` | start it detached if it is not answering (idempotent) |
| `stop` · `status` | stop it · print `/ping` |
| `show [page] [--open\|--list\|--search X\|--since N]` | open annotations |
| `resolve <slug\|json> --nrs 1,2` | mark annotations as processed |
| `apply-hunk <json> --nr 1 --hunks 2` | apply one block of a draft edit |
| `url <file>` · `url --base` | the `/p/` link for a local file · the base URL only |
| `pick-port [--port N]` | choose a free port (8791–8890, else from the OS) and store it in the config file |
| `install-skill` · `install-hooks` | install, both idempotent |
| `--version` | print the version |

`html-annotator <command>` and `python -m html_annotator <command>` are the
same thing.

## File map

| path | role |
|---|---|
| `SKILL.md` | agent port (embed, `/p/`, `.`) |
| `references/` | handbook, snippets, record schema — the single source of the paste blocks |
| `html_annotator/` | Python package: CLI, bridge, config, show, hunks |
| `bin/` | thin wrappers for the hooks and older shortcuts |
| `pyproject.toml` | packaging; the version lives in `html_annotator/__init__.py` |
| `CRITERIA.md` · `tests/` | acceptance criteria and the suite that proves them |
| `docs/` | `SCOPE.md` (core vs extra), `DECISIONS.md` (dated choices) |
| `CHANGELOG.md` | releases and the migration from LUC-ANNOTATOR v2 |
| `extras/` | not part of the skill install (see `extras/README.md`) |

## How it works

```
HTML page  ──►  references/annotator-snippet.html
              fetch the origin that served /p/
                        ▼
                html-annotator serve
                        ▼
      ~/annotations/<page>/ronde-NN/annotations.json
```

## Limits

- Python tests run on macOS, Linux and Windows in CI; the Playwright suite is
  only exercised on macOS and Linux.
- Default annotation root: `~/annotations`. A machine that already uses the
  older annotation folder on the desktop keeps it, so an upgrade orphans
  nothing.
- Two blind spots in the suite: see CRITERIA.md (B18, B19).

## Links

[Install](INSTALL.md) · [Agent handbook](references/agent-handbook.md) ·
[Criteria](CRITERIA.md) · [Scope](docs/SCOPE.md) ·
[Decisions](docs/DECISIONS.md) · [Changelog](CHANGELOG.md) ·
[License](LICENSE) (MIT)
