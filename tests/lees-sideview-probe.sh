#!/bin/bash
# Leest wat de sideview-probe naar de bridge stuurde en drukt het leesbaar af.
# Hoort bij maak-sideview-probe.sh. Bedoeld voor de agent, om direct te kunnen debuggen.
#
#   ~/.claude/skills/html-annotator/tests/lees-sideview-probe.sh [aantal] [vanaf-regel]
#
# vanaf-regel snijdt oudere runs weg: geef het regelnummer dat bridge.log had toen de
# meting begon. Zonder dat argument lees je ook metingen van eerder, en die lijken op
# een verse uitslag.
#
# Geen regels gevonden betekent iets: de pagina kon de bridge niet bereiken vanaf die
# origin. Dan is de diagnose alleen op het scherm te zien.

set -uo pipefail
SKILL_DIR="$HOME/.claude/skills/html-annotator"
LOG="$SKILL_DIR/bridge.log"
AANTAL="${1:-4}"
VANAF="${2:-1}"

[ -f "$LOG" ] || { echo "geen bridge.log"; exit 1; }

REGELS=$(tail -n "+$VANAF" "$LOG" | grep -o 'diag=[A-Za-z0-9+/=._-]*' | tail -n "$AANTAL")

if [ -z "$REGELS" ]; then
  echo "GEEN probe-regels in bridge.log."
  echo
  echo "Dat is zelf een uitslag: de pagina heeft de bridge niet kunnen bereiken vanaf de"
  echo "origin waar hij draaide. Vraag de reviewer om de diagnose van het scherm te kopiëren."
  echo
  echo "Wat er wel binnenkwam, laatste origins:"
  grep -o 'origin=[^ ]*' "$LOG" | sort | uniq -c | tail -10
  exit 2
fi

echo "$REGELS" | while read -r r; do
  echo "$r" | sed 's/^diag=//' | python3 -c '
import sys, base64, json
ruw = sys.stdin.read().strip()
fase, _, data = ruw.partition(".")
try:
    rap = json.loads(base64.b64decode(data + "=" * (-len(data) % 4)).decode("utf-8"))
except Exception as e:
    print("  (kon niet decoderen: %s)" % e); raise SystemExit
print("=== fase: %s · %s ===" % (fase, rap.get("t", "?")))
for k in ("href", "protocol", "origin", "baseURI", "secure", "zichtbaar", "electron", "pil"):
    if k in rap:
        print("  %-11s %s" % (k, rap[k]))
lb = rap.get("loopback") or {}
print("  %-11s %s" % ("loopback", "BEREIKBAAR" if lb.get("bereikbaar") else "GEBLOKKEERD: " + str(lb.get("reden"))))
if "zelfherstel" in rap:
    print("  %-11s %s (na %ss)" % ("zelfherstel", rap["zelfherstel"], rap.get("secondenGewacht", "?")))
if rap.get("fouten"):
    print("  consolefouten:")
    for f in rap["fouten"]:
        print("    - %s" % f)
if rap.get("ua"):
    print("  ua          %s" % rap["ua"])
print()
'
done

echo "Origins die de bridge in totaal zag:"
grep -o 'origin=[^ ]*' "$LOG" | sort | uniq -c | tail -10
