#!/bin/bash
# AC-3: `ensure` mag nooit met exitcode 0 eindigen terwijl er geen bridge
# antwoordt. Aanleiding: bridge.log bevat "OSError: [Errno 48] Address already in use"
# tracebacks terwijl bridge-hook.log op dezelfde momenten succes meldt.
#
# Opzet: de poort ($PORT, standaard 8791) bezetten met een luisteraar die géén bridge
# is, en kijken wat het script dan doet. Het moet falen, met een verwijzing naar
# pick-port, en mag nooit stil naar een andere poort uitwijken (CRITERIA.md B12).
#
# LET OP: bridge_down stopt wat er op $PORT luistert. Draai deze case tegen een
# testpoort (HTML_ANNOTATOR_PORT=<vrij>) als er een live bridge op 8791 staat.

set -uo pipefail
source "$(dirname "$0")/lib.sh"

echo "case-03: ensure liegt niet over een bezette poort"

if ! bridge_down; then
  fail "kon de bridge niet omlaag krijgen; test zegt niets"
  exit 2
fi

# Kale TCP-luisteraar: sluit connecties meteen (geen HTTP). Zonder accept()
# duurt elke ping de volle timeout; ensure doet dat tot 26x
# en de oude sleep(60)-bezetter was dan dood voor de assert.
python3 - "$PORT" <<'PY' &
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[1])))
s.listen(5)
while True:
    c, _ = s.accept()
    c.close()
PY
BEZETTER=$!
trap 'kill $BEZETTER 2>/dev/null; wait $BEZETTER 2>/dev/null' EXIT

for _ in $(seq 1 25); do
  [ "$(bridge_pid)" = "$BEZETTER" ] && break
  sleep 0.2
done
if [ "$(bridge_pid)" != "$BEZETTER" ]; then
  fail "kon de poort niet bezetten met pid $BEZETTER (lsof: $(bridge_pid))"
  exit 2
fi

MELDING=$(cd "$SKILL_DIR" && python3 -m html_annotator ensure 2>&1 >/dev/null)
EXIT_CODE=$?
ANTWOORD=$(ping_bridge)

if ! kill -0 "$BEZETTER" 2>/dev/null; then
  fail "bezetter is dood voordat we assertten; scenario deed zich niet voor (lsof: $(bridge_pid))"
  exit 2
fi

RC=0
if echo "$ANTWOORD" | grep -q html-annotator; then
  fail "ensure startte een echte bridge terwijl de poort bezet hoorde (exit $EXIT_CODE, lsof: $(bridge_pid))"
  RC=1
elif [ "$EXIT_CODE" -eq 0 ]; then
  fail "ensure exit 0 op een niet-bridge-bezetter (ping: ${ANTWOORD:-leeg})"
  RC=1
else
  pass "exit $EXIT_CODE, bezetter leeft, ping is geen html-annotator (lsof: $(bridge_pid))"
fi
if echo "$MELDING" | grep -q "pick-port"; then
  pass "melding verwijst naar pick-port"
else
  fail "melding noemt pick-port niet: ${MELDING:-leeg}"
  RC=1
fi

exit $RC
