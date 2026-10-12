#!/bin/bash
# De echte sideviewer meten — het ene oppervlak dat de geautomatiseerde suite niet kan
# cover (CRITERIA.md B17). One command; the script does the rest.
#
#   ~/.claude/skills/html-annotator/tests/sideview-test.sh [wachttijd]
#
# Wat het doet, in volgorde:
#   1. probe-pagina opnieuw bouwen op ~/Desktop/sideview-probe.html
#   2. de bridge omlaag halen, zodat de pagina met "bridge uit" begint — dat is de enige
#      manier om zelfherstel te kunnen zien
#   3. wachten tot de reviewer die pagina in de sideviewer heeft geopend (default 45s)
#   4. de bridge omhoog brengen en meekijken of de pagina vanzelf bijkomt
#   5. afdrukken wat de probe over zichzelf gemeld heeft
#
# Blijft de uitslag leeg, dan kon de pagina de bridge niet bereiken vanaf die origin. Dat
# is geen storing maar een meetresultaat, en dan staat de diagnose op het scherm.

set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
. "$DIR/lib.sh"

WACHT="${1:-45}"

echo "=== sideview-test · $(date '+%H:%M:%S') ==="
echo

"$DIR/maak-sideview-probe.sh" >/dev/null || { echo "FOUT: probe bouwen mislukt" >&2; exit 1; }
echo "1. probe gebouwd: ~/Desktop/sideview-probe.html"

if ! bridge_down; then
  echo "FOUT: de bridge gaat niet omlaag, dus zelfherstel is niet te meten." >&2
  exit 1
fi
# Vanaf hier tellen, zodat metingen van eerdere runs niet als verse uitslag lezen.
VANAF=$(( $(wc -l < "$SKILL_DIR/bridge.log" 2>/dev/null || echo 0) + 1 ))

echo "2. bridge omlaag (pagina moet straks met 'bridge uit' beginnen)"
echo
echo "   ---> OPEN NU ~/Desktop/sideview-probe.html IN DE SIDEVIEWER <---"
echo "        Je hebt $WACHT seconden. Laat de pagina daarna gewoon openstaan."
echo

for ((i = WACHT; i > 0; i--)); do
  printf "\r   nog %2ds " "$i"
  sleep 1
done
printf "\r%*s\r" 20 ""

echo "3. bridge omhoog"
bridge_up >/dev/null 2>&1
if ! wait_for_bridge 8; then
  echo "FOUT: de bridge kwam niet omhoog; test zegt niets." >&2
  exit 1
fi

echo "4. 25 seconden meekijken of de pagina vanzelf bijkomt..."
sleep 25

echo
echo "5. wat de probe meldde:"
echo
"$DIR/lees-sideview-probe.sh" 4 "$VANAF"
UITSLAG=$?

echo
if [ $UITSLAG -eq 2 ]; then
  cat <<'EOF'
CONCLUSIE ONVOLLEDIG. De pagina heeft de bridge niet bereikt. Twee mogelijkheden, en
alleen de reviewer kan ze uit elkaar houden:

  a. de sideviewer draait op een origin die loopback niet mag benaderen — dan staat er
     op de pagina een rood blok met de reden;
  b. de pagina is niet (op tijd) geopend — dan staat er niets bijzonders op het scherm.

Vraag de reviewer om op "Kopieer diagnose" te klikken en dat in de chat te plakken.
EOF
else
  echo "Klaar. Kijk bij 'zelfherstel' hierboven: True betekent dat de pil vanzelf omsloeg,"
  echo "zonder reload, in de echte sideviewer. Dat is de na-zwengel, gemeten in plaats van"
  echo "beredeneerd."
fi
