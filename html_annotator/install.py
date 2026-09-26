"""Install the skill and its two hooks — pure Python, no jq, no bash.

Two independent commands:

* ``install-skill`` puts this checkout at ``~/.claude/skills/html-annotator``
  (symlink, or a copy with ``--copy``; copy is the default on Windows, where a
  symlink needs Developer Mode or admin rights).
* ``install-hooks`` registers the SessionStart and PostToolUse hooks in
  ``~/.claude/settings.json``. Idempotent: an existing annotator hook is
  replaced, other hooks are left alone.
"""

import json
import os
import shutil
import time
from pathlib import Path

from . import config

HOOK_SCRIPT = "bin/hook-ensure-bridge.py"
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", "extras"}
EXCLUDE_FILES = {"bridge.log", "bridge.pid", "bridge-hook.log"}


def _hook_command(doel):
    """The command Claude Code runs. No shell, no `~`: absolute paths only."""
    return '"%s" "%s"' % (config.python_exe(), Path(doel, HOOK_SCRIPT))


def hook_entries(doel):
    cmd = _hook_command(doel)
    hook = {"type": "command", "command": cmd, "timeout": 15,
            "statusMessage": "annotator-bridge check"}
    return {
        "PostToolUse": {"matcher": "Edit|Write", "hooks": [dict(hook)]},
        "SessionStart": {"matcher": "", "hooks": [dict(hook)]},
    }


def _zonder_annotator(groepen):
    uit = []
    for groep in groepen or []:
        commandos = [h.get("command") or "" for h in (groep.get("hooks") or [])]
        if any("ensure-bridge" in c or "html_annotator" in c for c in commandos):
            continue
        uit.append(groep)
    return uit


def plan_hooks(settings, doel):
    """The settings dict with our two hooks registered."""
    data = dict(settings or {})
    hooks = dict(data.get("hooks") or {})
    for event, entry in hook_entries(doel).items():
        hooks[event] = _zonder_annotator(hooks.get(event)) + [entry]
    data["hooks"] = hooks
    return data


def install_hooks(doel=None, toon_alleen=False):
    doel = Path(doel or (config.skills_dir() / "html-annotator"))
    pad = config.settings_file()
    try:
        bestaand = json.loads(pad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        bestaand = {}
    nieuw = plan_hooks(bestaand, doel)
    if toon_alleen:
        return 0, json.dumps(nieuw.get("hooks"), indent=2)
    pad.parent.mkdir(parents=True, exist_ok=True)
    if pad.exists():
        backup = pad.with_suffix(".json.bak-%s" % time.strftime("%Y%m%d%H%M%S"))
        shutil.copyfile(pad, backup)
    pad.write_text(json.dumps(nieuw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0, "hooks registered in %s (backup next to it)" % pad


def _kopieer(bron, doel):
    def negeer(directory, namen):
        uit = {n for n in namen if n in EXCLUDE_DIRS or n in EXCLUDE_FILES}
        uit |= {n for n in namen if n.endswith(".pyc")}
        return uit
    shutil.copytree(bron, doel, ignore=negeer, dirs_exist_ok=True)


def _kopieer_uit_pakket(doel):
    """Assemble the skill from package data (pip/pipx install, no checkout).

    Copies exactly the files an agent needs: SKILL.md, references/ and the bin
    wrappers. The Python code itself stays in site-packages; the wrappers and
    hooks call the installed interpreter.
    """
    bron = config.skill_source_dir()
    doel.mkdir(parents=True, exist_ok=True)
    skill_md = bron / "SKILL.md"
    if skill_md.is_file():
        shutil.copyfile(skill_md, doel / "SKILL.md")
    refs = config.snippets_dir()
    if refs.is_dir():
        _kopieer(refs, doel / "references")
    if (bron / "bin").is_dir():
        _kopieer(bron / "bin", doel / "bin")
    return 0, "skill installed from the package at %s" % doel


def install_skill(kopie=None, bron=None):
    doel = config.skills_dir() / "html-annotator"
    doel.parent.mkdir(parents=True, exist_ok=True)
    if bron is None and not config.is_checkout():
        return _kopieer_uit_pakket(doel)
    bron = Path(bron or config.SKILL_DIR).resolve()
    if kopie is None:
        kopie = os.name == "nt"
    if doel.is_symlink() and Path(os.readlink(doel)) == bron:
        return 0, "skill already linked at %s" % doel
    if kopie:
        _kopieer(bron, doel)
        return 0, "skill copied to %s" % doel
    if doel.exists():
        return 1, ("%s already exists and is not this checkout — left alone. "
                   "Remove it, or run install-skill --copy." % doel)
    try:
        doel.symlink_to(bron, target_is_directory=True)
    except OSError as e:
        return 1, "symlink failed (%s) — use install-skill --copy" % e
    return 0, "skill linked: %s -> %s" % (doel, bron)
