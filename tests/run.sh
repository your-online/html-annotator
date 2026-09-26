#!/bin/bash
# Runner voor de annotator-bridge-suite.
#
#   tests/run.sh                # A7: 00 02–04 06 08–09 11–12 14–18
#                               (geen case-01 spend, geen mutate)
#   tests/run.sh 00 09 11       # de drie cases zonder browser (ook de CI-set)
#   tests/run.sh 02 03          # alleen deze cases
#   tests/run.sh 01 10          # verse-agent + mutatie, expliciet
#   CASE01_RUNS=1 tests/run.sh 01
#
# Uitgangspunten die deze runner bewust hardmaakt:
# - Een case die niet kón draaien (exit 2) is geen pass. Hij wordt als BLOKKED geteld
#   en de suite eindigt rood, want een test die niets deed bewijst niets.
# - Case-01 test agent-gedrag en is dus flaky. De drempel staat vooraf vast in
#   CRITERIA.md B18: every run must pass. k/n is always printed.
# - Wat de suite NIET dekt wordt afgedrukt, zodat groen niet als volledige dekking leest.

set -uo pipefail
cd "$(dirname "$0")"
source ./lib.sh

CASE01_RUNS="${CASE01_RUNS:-3}"
GEVRAAGD=("$@")
# Default = wat A7 van iedereen eist. case-01 (spend) en case-10 (mutatie,
# bewust traag + eigen boom) alleen als je ze noemt.
DEFAULT="00 02 03 04 06 08 09 11 12 14 15 16 17 18"
wil() {
  if [ ${#GEVRAAGD[@]} -eq 0 ]; then
    for g in $DEFAULT; do [ "$g" = "$1" ] && return 0; done
    return 1
  fi
  for g in "${GEVRAAGD[@]}"; do [ "$g" = "$1" ] && return 0; done
  return 1
}

BRIDGE_BIJ_START=$(bridge_pid)
FALEN=0
BLOKKED=0
echo "=== annotator-bridge suite · $(date '+%Y-%m-%d %H:%M:%S') ==="
if git -C .. rev-parse --short HEAD >/dev/null 2>&1; then
  echo "commit: $(git -C .. rev-parse --short HEAD)  dirty: $(git -C .. status --porcelain | wc -l | tr -d ' ')"
else
  echo "commit: unknown  dirty: n/a"
fi
echo "snippet: $(shasum -a 256 ../references/annotator-snippet.html | cut -c1-12)  hook: $(shasum -a 256 ../bin/hook-ensure-bridge.py | cut -c1-12)  cli: $(shasum -a 256 ../html_annotator/cli.py | cut -c1-12)"
echo

if wil 00 || wil record; then
  echo "case-00: annotation-record (geen browser)"
  python3 -m compileall -q ../html_annotator ../bin || FALEN=$((FALEN + 1))
  python3 ./test_record.py
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 09 || wil contract; then
  echo "case-09: bridge-contract B1–B7"
  python3 ./test_bridge_contract.py
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  echo "case-09b: show B8–B9"
  python3 ./test_toon.py
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 10 || wil mutate; then
  echo "case-10: mutatie over B2/B5/B8"
  ./mutate-contract.sh
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 11 || wil layout; then
  echo "case-11: repo-layout A1–A6"
  python3 ./test_layout.py
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  chmod +x ./mutate-layout.sh
  ./mutate-layout.sh
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 02; then
  if [ ! -d node_modules/playwright-core ]; then
    echo "BLOKKED case-02: playwright-core ontbreekt. Installeer met:"
    echo "  (cd \"$(cd "$(dirname "$0")" && pwd)\" && npm i --no-save playwright-core)"
    BLOKKED=$((BLOKKED + 1))
  else
    node ./case-02-selfheal.mjs
    [ $? -ne 0 ] && FALEN=$((FALEN + 1))
    # Verborgen paneel: de echte situatie, want het sideview-paneel staat er
    # terwijl er in de chat getypt wordt. Alleen de file-origin; data: is daar al afgedekt.
    CASE02_ORIGINS=file CASE02_VERBORGEN=1 node ./case-02-selfheal.mjs
    rc=$?
    [ $rc -eq 2 ] && BLOKKED=$((BLOKKED + 1))
    [ $rc -eq 1 ] && FALEN=$((FALEN + 1))
  fi
  echo
fi

if wil 03; then
  ./case-03-ensure-bridge-eerlijk.sh
  rc=$?
  [ $rc -eq 2 ] && BLOKKED=$((BLOKKED + 1))
  [ $rc -eq 1 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 04; then
  ./case-04-bridge-omhoog-los-van-schrijfroute.sh
  rc=$?
  [ $rc -eq 2 ] && BLOKKED=$((BLOKKED + 1))
  [ $rc -eq 1 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 01; then
  geslaagd=0
  geblokkeerd=0
  for i in $(seq 1 "$CASE01_RUNS"); do
    echo "case-01 run $i/$CASE01_RUNS"
    ./case-01-verse-agent.sh
    rc=$?
    [ $rc -eq 0 ] && geslaagd=$((geslaagd + 1))
    [ $rc -eq 2 ] && geblokkeerd=$((geblokkeerd + 1))
  done
  echo "case-01: $geslaagd/$CASE01_RUNS geslaagd, $geblokkeerd geblokkeerd (drempel: $CASE01_RUNS/$CASE01_RUNS)"
  [ "$geblokkeerd" -gt 0 ] && BLOKKED=$((BLOKKED + 1))
  [ "$geslaagd" -lt "$CASE01_RUNS" ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 06; then
  echo "case-06: losse blokken binnen één bewerking"
  bridge_up >/dev/null 2>&1 || echo "  (bridge_up faalde; case rapporteert zelf)"
  node ./case-06-hunks.mjs
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 14; then
  echo "case-14: change-suggestie bewerken in plaats van overschrijven"
  bridge_up >/dev/null 2>&1 || echo "  (bridge_up faalde; case rapporteert zelf)"
  node ./case-14-suggest-change-bewerken.mjs
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 15; then
  echo "case-15: suggestie die pas later zichtbaar wordt"
  bridge_up >/dev/null 2>&1 || echo "  (bridge_up faalde; case rapporteert zelf)"
  node ./case-15-suggest-zichtbaar.mjs
  rc=$?
  [ $rc -eq 2 ] && BLOKKED=$((BLOKKED + 1))
  [ $rc -eq 1 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 16; then
  echo "case-16: gedeelde suggest-key is één suggestie met één pill"
  bridge_up >/dev/null 2>&1 || echo "  (bridge_up faalde; case rapporteert zelf)"
  node ./case-16-suggest-gedeelde-key.mjs
  rc=$?
  [ $rc -eq 2 ] && BLOKKED=$((BLOKKED + 1))
  [ $rc -eq 1 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 17; then
  echo "case-17: losse suggest-keys beslissen onafhankelijk"
  bridge_up >/dev/null 2>&1 || echo "  (bridge_up faalde; case rapporteert zelf)"
  node ./case-17-suggest-losse-keys.mjs
  rc=$?
  [ $rc -eq 2 ] && BLOKKED=$((BLOKKED + 1))
  [ $rc -eq 1 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 12; then
  echo "case-12: boxes scrollen mee met de HTML"
  bridge_up >/dev/null 2>&1 || echo "  (bridge_up faalde; case rapporteert zelf)"
  node ./case-12-scroll-mee.mjs
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  echo
fi

if wil 18 || wil verstuur; then
  # Eigen bridge op een vrije poort, tijdelijke root; raakt de live bridge niet.
  echo "case-18: Verstuur-knop (WhatsApp) — gate, nastap, wachter, dummy-kanaal"
  python3 ./test_verstuur.py
  [ $? -ne 0 ] && FALEN=$((FALEN + 1))
  if [ ! -d node_modules/playwright-core ]; then
    echo "BLOKKED case-18 (browser): playwright-core ontbreekt"
    BLOKKED=$((BLOKKED + 1))
  else
    node ./case-18-verstuur-knop.mjs
    rc=$?
    [ $rc -eq 2 ] && BLOKKED=$((BLOKKED + 1))
    [ $rc -eq 1 ] && FALEN=$((FALEN + 1))
  fi
  echo
fi

if wil 08; then
  echo "case-08: locator blijft op de tabelrij na insert"
  c08_poort=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
  c08_root=$(mktemp -d)
  HTML_ANNOTATOR_PORT="$c08_poort" HTML_ANNOTATOR_ROOT="$c08_root" \
    python3 -m html_annotator serve >/tmp/ann-c08-bridge.log 2>&1 &
  c08_pid=$!
  c08_ok=0
  for _ in $(seq 1 25); do
    if curl -s -o /dev/null --max-time 0.2 "http://127.0.0.1:$c08_poort/ping"; then
      c08_ok=1
      break
    fi
    sleep 0.2
  done
  if [ "$c08_ok" -eq 0 ]; then
    echo "BLOKKED case-08: ephemeral bridge op $c08_poort kwam niet omhoog"
    BLOKKED=$((BLOKKED + 1))
  else
    LUC_ANNOTATOR_PORT="$c08_poort" HTML_ANNOTATOR_PORT="$c08_poort" node ./case-08-locator-tabel.mjs
    rc=$?
    [ $rc -eq 2 ] && BLOKKED=$((BLOKKED + 1))
    [ $rc -eq 1 ] && FALEN=$((FALEN + 1))
  fi
  kill "$c08_pid" 2>/dev/null || true
  wait "$c08_pid" 2>/dev/null || true
  rm -rf "$c08_root"
  echo
fi

echo "NIET IN DE SUITE: case-05, case-07 en case-13 dekken de la-draft-kaart en"
echo "la-sub. Die zijn uit de scope (docs/SCOPE.md) en staan in extras/tests/."
echo
echo "NIET GEAUTOMATISEERD — de echte Claude Desktop sideviewer. Case-02 draait in"
echo "systeem-Chrome; Electron heeft eigen CSP en flags. Handmatig gemeten 18-08-2026"
echo "(CRITERIA.md B17): opening as a FILE does not work there and does not self-heal; via"
echo "http://127.0.0.1:8791/p/<pad> werkt alles, inclusief zelfherstel."
echo "Opnieuw meten: tests/sideview-test.sh"
echo

if [ "$FALEN" -eq 0 ] && [ "$BLOKKED" -eq 0 ]; then
  echo "GROEN — alle gedraaide cases geslaagd"
else
  echo "ROOD — $FALEN gefaald, $BLOKKED geblokkeerd"
fi

# De bridge terugzetten zoals we hem aantroffen: de tests zetten hem herhaaldelijk om.
[ -n "$BRIDGE_BIJ_START" ] && bridge_up >/dev/null 2>&1

[ "$FALEN" -eq 0 ] && [ "$BLOKKED" -eq 0 ]
