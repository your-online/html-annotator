#!/bin/bash
# AC-2: een verse agent die een HTML-pagina voor de reviewer oplevert en het bestand via Bash
# wegschrijft, laat de bridge draaien.
#
# Verse context is hier een echt losstaand `claude -p`-proces, niet een subagent van de
# lopende sessie: een subagent erft de context en de CLAUDE.md-lezing van zijn ouder en
# is dus precies niet vers op de manier die dit criterium bedoelt.
#
# Bewust GEEN --bare: de PostToolUse-hook en CLAUDE.md zijn onderdeel van wat getest
# wordt. Bewust de Bash-route: de hook hangt aan Edit|Write en dit is de route die hem
# mist.

set -uo pipefail
source "$(dirname "$0")/lib.sh"

WERK=$(mktemp -d "${TMPDIR:-/tmp}/annotator-case01.XXXXXX")
DOEL="$WERK/notitie.html"
LOG="$WERK/claude.log"
trap 'rm -rf "$WERK"' EXIT

echo "case-01: verse agent laat de bridge draaien"

# --- voorwaarde: de bridge draait aantoonbaar NIET ---------------------------
if ! bridge_down; then
  fail "kon de bridge niet omlaag krijgen; test zegt niets"
  exit 2
fi
PID_VOOR=$(bridge_pid)
if [ -n "$PID_VOOR" ]; then
  fail "poort $PORT nog bezet door pid $PID_VOOR"
  exit 2
fi

# --- de verse agent ---------------------------------------------------------
PROMPT="Maak een korte HTML-pagina voor de reviewer met drie bullets over waarom een lokale
bridge handig is. Schrijf het bestand met een bash heredoc naar $DOEL — gebruik
daarvoor niet de Write- of Edit-tool, maar echt Bash. Als je klaar bent, zeg alleen
waar het bestand staat."

( cd "$WERK" && claude -p "$PROMPT" \
    --allowedTools "Bash Read Glob Grep Skill" \
    >"$LOG" 2>&1 )
AGENT_EXIT=$?

# --- assertions: elke faalroute is hard, nooit een stille pass ---------------
RC=0

if [ "$AGENT_EXIT" -ne 0 ]; then
  fail "claude -p eindigde met exit $AGENT_EXIT — er is niets getest. Laatste output:"
  tail -n 8 "$LOG" | sed 's/^/        /'
  exit 2
fi

if [ ! -f "$DOEL" ]; then
  fail "agent heeft $DOEL niet aangemaakt — er is niets getest"
  tail -n 8 "$LOG" | sed 's/^/        /'
  exit 2
fi

if grep -qE "HTML-ANNOTATOR|LUC-ANNOTATOR" "$DOEL"; then
  pass "opgeleverde HTML bevat het annotator-snippet"
else
  fail "opgeleverde HTML bevat geen annotator-marker (HTML-ANNOTATOR/LUC-ANNOTATOR)"
  RC=1
fi

if [ -n "$(ping_bridge)" ]; then
  pass "bridge antwoordt na de run"
else
  fail "bridge antwoordt niet na de run"
  RC=1
fi

PID_NA=$(bridge_pid)
if [ -n "$PID_NA" ] && [ "$PID_NA" != "$PID_VOOR" ]; then
  pass "bridge is een nieuw proces (pid $PID_NA)"
else
  fail "geen nieuw bridge-proces (voor='$PID_VOOR' na='$PID_NA')"
  RC=1
fi

exit $RC
