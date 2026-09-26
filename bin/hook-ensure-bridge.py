#!/usr/bin/env python3
"""Claude Code hook: bring the bridge up.

Registered twice in ~/.claude/settings.json (see
`python -m html_annotator install-hooks`):

* SessionStart — once per session, whatever route that session later uses to
  write HTML. This is the layer that counts: the PostToolUse layer misses an
  agent that writes the file through Bash.
* PostToolUse on Edit|Write — starts the bridge when the written file is
  .html/.htm and carries an annotator marker (HTML-ANNOTATOR, or the older
  LUC-ANNOTATOR on pages that were embedded before the rename).

Cheap and quiet, and it always exits 0: a hook must never fail a tool call.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from html_annotator import service


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    event = payload.get("hook_event_name") or ""
    if event != "SessionStart":
        pad = (payload.get("tool_input") or {}).get("file_path") or ""
        if not pad:
            return 0
        p = Path(pad)
        if p.suffix.lower() not in (".html", ".htm") or not p.is_file():
            return 0
        try:
            bron = p.read_text(encoding="utf-8", errors="replace")
            if "HTML-ANNOTATOR" not in bron and "LUC-ANNOTATOR" not in bron:
                return 0
        except OSError:
            return 0
    try:
        status, bericht = service.ensure()
        print("[annotator-hook] %s: %s" % (status, bericht), file=sys.stderr)
    except Exception as e:  # nooit een tool-call laten falen
        print("[annotator-hook] error: %s" % e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
