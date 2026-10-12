# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
at [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Per-user config file `~/.config/html-annotator/config.json`
  (`$XDG_CONFIG_HOME` respected, `%APPDATA%\html-annotator\config.json` on
  Windows) with the optional keys `port`, `host` and `pages_root`.
  Precedence: environment > config file > default.
- `pick-port [--port N]`: chooses a port (8791–8890, a port where the bridge
  already answers counts as good, the OS picks when all are taken) and stores
  it in the config file. Run it after installing.
- `url --base` prints only the bridge's base URL, for `curl` and scripts.
- `HTML_ANNOTATOR_HOST`: opt-in bind address (for example `0.0.0.0` in a
  container). URLs, `/ping` and the bridge's own origins stay on 127.0.0.1;
  a non-loopback bind logs a warning.
- `HTML_ANNOTATOR_PAGES_ROOT`: the directory `/p/` serves from (default:
  home). `url` maps against the same root; the dotfile, symlink and file
  type rules hold relative to it.
- Docker/WSL section in `INSTALL.md`; criteria B31–B39;
  `tests/test_poort_config.py` (CI on all three OSes) and
  `tests/case-19-dynamische-poort.mjs`.
- Config key `signed_group_message` (optional): a send-gate exception for one
  WhatsApp group whose messages an external verifier signs. Jid, verifier
  path, module and label come from the config file; without the key the
  gate behaves as before (B40).
- `/ping` also returns the bridge's `pid`.

### Changed

- `ensure` exits 1 when the configured port is taken by something that is
  not the bridge, and says to run `pick-port`. It never moves to another
  port on its own (B12).
- `references/checklist-snippet.html` talks to the origin that served the
  `/p/` page instead of a fixed `http://127.0.0.1:8791`, like the annotator
  snippet; `file://` still falls back to 8791.
- `bin/wacht-op-verstuur.py` takes the bridge from the `--page` URL, or
  from the config, instead of `HTML_ANNOTATOR_PORT`/8791.
- Agent docs (`SKILL.md`, the handbook, `README.md`, `INSTALL.md`): agents
  never build a `/p/` URL themselves; `url <file>` and `url --base` print it.
- `url <file>` on a hidden path (a part starting with `.`) or outside the
  pages root now exits 1 with an error, instead of printing a link the
  bridge would refuse anyway.
- An invalid port (for example `70000`) in `HTML_ANNOTATOR_PORT` or in the
  config file is ignored with a warning on stderr; the next source wins.
- `pick-port` never overwrites a config file it cannot read or parse: exit
  2 with the file and the problem; repair or remove it (B35).
- `write_config` runs read-modify-write under a lock file next to the
  config (`fcntl.flock` / `msvcrt.locking`): concurrent writers keep each
  other's keys (B36).
- `ensure` runs under a per-port lock in the state dir, so concurrent ensures
  start one bridge; the pid file is written only once the started process is
  the one answering `/ping`, so `stop` stops the real bridge (B37).
- `ensure` and `pick-port` also recognise a running bridge that still
  answers `/ping` with the pre-rename name `luc-annotator` (B38).
- The bridge maps a page to its file via `/p/` only for its own URLs
  (http(s), loopback host, its own port); `file://` pages and other sites
  use `pageFile` as before (B39).
- Send gate: mail tools on any `ms365` or `ms365-<name>` server are gated
  (the sender account in the hash decides, not the server name). Before,
  only a fixed list of server names was; others got no verdict at all.

### Migration notes

- **Send button for mail.** The watcher picks the MCP server per sender
  account from `mail_servers` in the config file. Without it every mail card
  ends in "vraag de reviewer in de chat". Add it once, for example
  `{"mail_servers": {"owner@example.com": "ms365"}}`.
- **Signed group message.** An installation that wants a pre-signed group
  message to pass without the button needs the `signed_group_message` key
  (see `INSTALL.md`), for example
  `{"signed_group_message": {"jid": "120363000000000000@g.us", "verifier":
  "~/path/to/verifier-repo", "module": "package.module", "label": "example
  signed message"}}`. Without it that message gets the normal gate (ask).

## [1.0.0rc1] — 2026-09-17

First release candidate as an installable package. Everything below is the
delta against the last state on `main`, which was a personal skill folder with
bash installers and Dutch-named entry points.

### Added

- `pyproject.toml` (hatchling): the distribution is `html-annotator`, the
  console script is `html-annotator`, and `python -m html_annotator` keeps
  working. Runtime dependencies: none (stdlib only); `pip install
  "html-annotator[crops]"` adds Pillow for faster screenshot crops.
- `html-annotator --version` and a `release` field in the bridge `/ping`
  answer. The version lives in exactly one place,
  `html_annotator/__init__.py`, and `pyproject.toml` reads it dynamically.
- The snippets are importable at runtime as
  `html_annotator/snippets/<name>.html` in an installed package, while
  `references/` stays the single source on disk.
- `install-skill` also works from a pip/pipx install: it copies `SKILL.md`,
  `references/` and the `bin/` wrappers into `~/.claude/skills/html-annotator`
  instead of requiring a checkout.
- `bin/show-annotations.py` and `bin/apply-hunk.py`.
- `LICENSE` (MIT, copyright "your-online") and this changelog.
- CI matrix on `ubuntu-latest`, `macos-latest` and `windows-latest`, plus a
  best-effort Playwright job; an end-to-end run on a Linux server.
- Criteria A10 (packaging: installable, `--version`, snippet importable) and
  A11 (one snippet source) in `CRITERIA.md`, covered by `tests/test_layout.py`.

### Changed

- **Scope cut (F0).** Core is snippet + bridge + CLI + handbook, plus the
  checklist and suggest layers. Todo-list spawning, the draft message card and
  `la-sub` moved to `extras/` (their code stays inside the one paste block).
- **One Python CLI (F1).** `install.sh`, `bin/ensure-bridge.sh` and
  `bin/hook-ensure-bridge.sh` are gone; everything runs through
  `python -m html_annotator`. No bash, no jq, so macOS, Linux and Windows take
  the same steps. Pid file and log moved to a per-user state directory.
- **Public names (F3).** `window.HtmlAnnotator` is the API, new embeds write
  the `<!-- HTML-ANNOTATOR v3 -->` … `<!-- /HTML-ANNOTATOR -->` markers, and
  the bridge identifies itself as `"bridge": "html-annotator"` in `/ping`.
- **Language.** The snippet UI, the bridge log lines, the CLI output and the
  work-rule box printed by `show` are English.
- Default annotation root is `~/annotations`; a machine that already uses the
  older folder on the desktop keeps it.

### Deprecated

- The previous page-global object name (still assigned as an alias of
  `window.HtmlAnnotator`), the `LUC_ANNOTATOR_*` environment variables, and
  `bin/toon-annotaties.py` / `bin/pas-hunk-toe.py`. All kept until 1.1; the
  exact names are in the migration table below.

### Removed

- The four bash scripts, the personal todo-list finder, and the installer step
  that placed personal memories.

## Migration from LUC-ANNOTATOR v2

Nothing breaks on upgrade; all of the old names still work.

| what | old | new | status of the old name |
|---|---|---|---|
| env: port | `LUC_ANNOTATOR_PORT` | `HTML_ANNOTATOR_PORT` | deprecated alias, still read |
| env: root | `LUC_ANNOTATOR_ROOT` | `HTML_ANNOTATOR_ROOT` | deprecated alias, still read |
| env: browser | `LUC_ANNOTATOR_CHROME` | `HTML_ANNOTATOR_CHROME` | deprecated alias, still read |
| page API | `window.LucAnnotator` | `window.HtmlAnnotator` | alias assigned by the snippet |
| markers | `<!-- LUC-ANNOTATOR v2 -->` … `<!-- /LUC-ANNOTATOR -->` | `<!-- HTML-ANNOTATOR v3 -->` … `<!-- /HTML-ANNOTATOR -->` | still recognised by the bridge (content hash), the hooks and the tests |
| bridge identity | `"bridge": "luc-annotator"` | `"bridge": "html-annotator"` | changed; check for the new value |
| install | `install.sh` | `python -m html_annotator install-skill` + `install-hooks` | removed |
| show annotations | `bin/toon-annotaties.py` | `html-annotator show` / `bin/show-annotations.py` | deprecated wrapper, still works |
| apply a hunk | `bin/pas-hunk-toe.py` | `html-annotator apply-hunk` / `bin/apply-hunk.py` | deprecated wrapper, still works |

Practical steps on an existing machine:

1. `git pull`, then `python -m html_annotator install-skill` and
   `python -m html_annotator install-hooks` — both idempotent; the hook entries
   from the bash era are replaced, not duplicated.
2. Existing pages keep their `LUC-ANNOTATOR` block and keep working. Re-embed
   only when you want the new markers; do not mix two blocks in one page.
3. Scripts that grep `/ping` for `luc-annotator` must look for
   `html-annotator` instead.

[1.0.0rc1]: https://github.com/your-online/html-annotator/releases/tag/v1.0.0rc1
