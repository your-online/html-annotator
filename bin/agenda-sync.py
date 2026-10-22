#!/usr/bin/env python3
"""Sync na slepen: schrijf op de pagina verplaatste voorstellen terug in de overlay.

    python3 agenda-sync.py <pagina>.voorstellen.json [--page <pagina>.html] [--by NAAM] [--dry-run]

Kort alias van `agenda-spec.py --apply-state`. Draai dit vóór elke volgende
stap (voorstellen opnieuw voorleggen of invites versturen) en lees pas daarna
de overlay. Alleen voorstellen met status open worden verplaatst; verstuurde
of vervallen voorstellen volgen de echte agenda.
"""

import os
import subprocess
import sys

if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
    print(__doc__.strip())
    sys.exit(0 if len(sys.argv) >= 2 else 2)
spec = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agenda-spec.py")
sys.exit(subprocess.call([sys.executable, spec, "--apply-state", *sys.argv[1:]]))
