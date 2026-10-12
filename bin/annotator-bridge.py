#!/usr/bin/env python3
"""Thin wrapper: run the bridge in the foreground.

Prefer `python -m html_annotator serve`; this file exists so older hooks and
shortcuts keep working. It has no settings of its own: port, bind address and
page root come from html_annotator.config, like every other entry point.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from html_annotator import bridge

if __name__ == "__main__":
    sys.exit(bridge.main())
