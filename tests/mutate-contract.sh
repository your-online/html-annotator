#!/usr/bin/env bash
# C6: de contract-tests moeten rood worden als het gedrag stuk is.
# Elke mutatie is een bekende breuk; slaagt de suite nog, dan bijt de test niet.
# Werkt op een kopie van de boom — de shipped source blijft onaangeraakt.
set -euo pipefail
ORIG="$(cd "$(dirname "$0")/.." && pwd)"
werk=$(mktemp -d)
trap 'rm -rf "$werk"' EXIT
rsync -a --exclude .git --exclude tests/node_modules --exclude __pycache__ \
  --exclude '*.pyc' --exclude bridge.log --exclude bridge.pid --exclude bridge-hook.log \
  "$ORIG"/ "$werk/repo/"
if [ -d "$ORIG/tests/node_modules" ]; then
  ln -s "$ORIG/tests/node_modules" "$werk/repo/tests/node_modules"
fi
SKILL="$werk/repo"
cd "$SKILL/tests"
BRIDGE="$SKILL/html_annotator/bridge.py"
TOON="$SKILL/html_annotator/show.py"
SNIP="$SKILL/references/annotator-snippet.html"

falen=0
zeg() {
  if [ "$1" = 0 ]; then echo "  PASS  mutate: $2"
  else echo "  FAIL  mutate: $2"; falen=1
  fi
}

vrije_poort() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()'
}

wacht_bridge() {
  local poort=$1 i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if curl -s -o /dev/null --max-time 0.2 "http://127.0.0.1:$poort/ping"; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

# 0 = mutant overleefde, 1 = test rood (kill), 2 = BLOKKED (geen kill).
case08() {
  local log=$1 ok_msg=$2 rood_msg=$3
  set +e
  LUC_ANNOTATOR_SKILL_DIR="$SKILL" LUC_ANNOTATOR_PORT="$poort" \
    node ./case-08-locator-tabel.mjs >"$log" 2>&1
  local rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then zeg 1 "$ok_msg"
  elif [ "$rc" -eq 1 ]; then zeg 0 "$rood_msg"
  else zeg 1 "B16 BLOKKED (exit $rc) — geen kill"
  fi
}

set +e
python3 ./test_bridge_contract.py >/tmp/ann-mut-ok.txt 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then zeg 0 "ongemutileerd B1–B7 groen"
else zeg 1 "ongemutileerd B1–B7 niet groen"
fi

# 403 voor /p/ buiten home → 200. B2 moet dit vangen.
python3 - <<'PY' "$BRIDGE"
import sys
p = sys.argv[1]
t = open(p).read()
oud = 'return self._json(403, {"ok": False, "error": "pad buiten home"}, cors=False)'
nieuw = 'return self._json(200, {"ok": True, "error": "MUTATIE"}, cors=False)'
if oud not in t:
    raise SystemExit("anker voor /p/-403 ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_bridge_contract.py >/tmp/ann-mut-p403.txt 2>&1; then
  zeg 1 "B2 blijft groen na 403→200"
else
  zeg 0 "B2 wordt rood als /p/ buiten home wordt doorgelaten"
fi
rsync -a "$ORIG/html_annotator/bridge.py" "$BRIDGE"

# Dotfile-weigering uit → /p/.env serveert weer. B2 moet dit vangen.
python3 - <<'PY' "$BRIDGE"
import sys
p = sys.argv[1]
t = open(p).read()
oud = 'if any(d.startswith(".") for d in delen + list(doel.relative_to(home).parts)):'
nieuw = 'if False:  # MUTATIE: dotfiles door'
if oud not in t:
    raise SystemExit("anker voor dotfile-weigering ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_bridge_contract.py >/tmp/ann-mut-dot.txt 2>&1; then
  zeg 1 "B2 blijft groen als /p/ dotfiles serveert"
else
  zeg 0 "B2 wordt rood als /p/ dotfiles serveert"
fi
rsync -a "$ORIG/html_annotator/bridge.py" "$BRIDGE"

# Origin-allowlist uit → elke site mag POSTen. B30 moet dit vangen.
python3 - <<'PY' "$BRIDGE"
import sys
p = sys.argv[1]
t = open(p).read()
oud = '    if origin in ("null", "file://"):\n        return True\n'
nieuw = '    return True  # MUTATIE: elke origin\n'
if oud not in t:
    raise SystemExit("anker voor origin-allowlist ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_bridge_contract.py >/tmp/ann-mut-origin.txt 2>&1; then
  zeg 1 "B30 blijft groen als elke origin mag"
else
  zeg 0 "B30 wordt rood als de origin-allowlist weg is"
fi
rsync -a "$ORIG/html_annotator/bridge.py" "$BRIDGE"

# Hash zonder het annotator-blok te strippen. B5 moet dit vangen.
python3 - <<'PY' "$BRIDGE"
import sys
p = sys.argv[1]
t = open(p).read()
oud = "bron = ANNOTATOR_BLOK.sub(\"\", bron)"
nieuw = "bron = bron  # MUTATIE: blok blijft in de hash"
if oud not in t:
    raise SystemExit("anker voor content_hash ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_bridge_contract.py >/tmp/ann-mut-hash.txt 2>&1; then
  zeg 1 "B5 blijft groen als het annotator-blok in de hash zit"
else
  zeg 0 "B5 wordt rood als contentHash het blok meetelt"
fi
rsync -a "$ORIG/html_annotator/bridge.py" "$BRIDGE"

# Ronde-teller hergebruikt de huidige ronde na remove-all. B4 moet dit vangen.
python3 - <<'PY' "$BRIDGE"
import sys
p = sys.argv[1]
t = open(p).read()
oud = "            nr = laatste + 1"
nieuw = "            nr = laatste  # MUTATIE: hergebruik ronde"
if oud not in t:
    raise SystemExit("anker voor ronde+1 ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_bridge_contract.py >/tmp/ann-mut-b4.txt 2>&1; then
  zeg 1 "B4 blijft groen als de ronde wordt hergebruikt"
else
  zeg 0 "B4 wordt rood als remove-all geen nieuwe ronde opent"
fi
rsync -a "$ORIG/html_annotator/bridge.py" "$BRIDGE"

python3 - <<'PY' "$BRIDGE"
import sys
p = sys.argv[1]
t = open(p).read()
oud = """        a["resolved"] = waarde
        if waarde:
            a["resolvedAt"] = nu"""
nieuw = """        dict(a)["resolved"] = waarde
        if waarde:
            dict(a)["resolvedAt"] = nu"""
if oud not in t:
    raise SystemExit("anker voor resolve-op-schijf ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_bridge_contract.py >/tmp/ann-mut-resolve.txt 2>&1; then
  zeg 1 "B3 blijft groen als /resolve niets op schijf zet"
else
  zeg 0 "B3 wordt rood als resolve de JSON niet wijzigt"
fi
rsync -a "$ORIG/html_annotator/bridge.py" "$BRIDGE"

python3 - <<'PY' "$BRIDGE"
import sys
p = sys.argv[1]
t = open(p).read()
oud = """        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
"""
nieuw = """        raise
"""
if oud not in t:
    raise SystemExit("anker voor tmp-opruim ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_bridge_contract.py >/tmp/ann-mut-tmp.txt 2>&1; then
  zeg 1 "B21 blijft groen zonder os.remove(tmp)"
else
  zeg 0 "B21 wordt rood als dump-fout het tmp laat liggen"
fi
rsync -a "$ORIG/html_annotator/bridge.py" "$BRIDGE"

set +e
python3 ./test_toon.py >/tmp/ann-mut-toon-ok.txt 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then zeg 0 "ongemutileerd B8–B9 groen"
else zeg 1 "ongemutileerd B8–B9 niet groen"
fi

python3 - <<'PY' "$TOON"
import sys
p = sys.argv[1]
t = open(p).read()
oud = "        print(WERKREGEL)"
nieuw = "        print('')  # MUTATIE"
if oud not in t:
    raise SystemExit("anker voor WERKREGEL ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_toon.py >/tmp/ann-mut-toon.txt 2>&1; then
  zeg 1 "B8 blijft groen zonder WERKREGEL"
else
  zeg 0 "B8 wordt rood als de werkregel weg is"
fi
rsync -a "$ORIG/html_annotator/show.py" "$TOON"

# B6: crop-except weg → annotatie verdwijnt of de call knalt.
python3 - <<'PY' "$BRIDGE"
import sys
p = sys.argv[1]
t = open(p).read()
oud = """            except Exception as e:  # crop mislukt: annotatie toch bewaren
                rec["image"] = None
                rec["imageError"] = str(e)[:200]"""
nieuw = """            except Exception as e:
                raise  # MUTATIE: crop-fout slikt de annotatie"""
if oud not in t:
    raise SystemExit("anker voor crop-except ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
if python3 ./test_bridge_contract.py >/tmp/ann-mut-b6.txt 2>&1; then
  zeg 1 "B6 blijft groen als een crop-fout opbolt"
else
  zeg 0 "B6 wordt rood als crop-falen de annotatie laat vallen"
fi
rsync -a "$ORIG/html_annotator/bridge.py" "$BRIDGE"

if [ ! -d node_modules/playwright-core ]; then
  zeg 1 "B16 overgeslagen: playwright-core ontbreekt (geen stilzwijgende pass)"
else
  poort=$(vrije_poort)
  root=$(mktemp -d)
  LUC_ANNOTATOR_PORT="$poort" LUC_ANNOTATOR_ROOT="$root" python3 -m html_annotator serve >/tmp/ann-mut-b16-bridge.log 2>&1 &
  bpid=$!
  if ! wacht_bridge "$poort"; then
    zeg 1 "B16-bridge kwam niet omhoog"
    kill "$bpid" 2>/dev/null || true
  else
    set +e
    LUC_ANNOTATOR_SKILL_DIR="$SKILL" LUC_ANNOTATOR_PORT="$poort" \
      node ./case-08-locator-tabel.mjs >/tmp/ann-mut-b16-ok.txt 2>&1
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then zeg 0 "ongemutileerd case-08 groen"
    else zeg 1 "ongemutileerd case-08 niet groen (exit $rc)"
    fi

    # Mutant A: label van gemeenschappelijke voorouder i.p.v. start-rij.
    python3 - <<'PY' "$SNIP"
import sys
p = sys.argv[1]
t = open(p).read()
oud = "      label: laContextLabel(aEl),"
nieuw = "      label: laContextLabel(gemeen),"
if oud not in t:
    raise SystemExit("anker voor label-start-rij ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
    case08 /tmp/ann-mut-b16-a.txt \
      "B16 blijft groen als het label van tbody komt" \
      "B16 wordt rood als het label van de gemeenschappelijke voorouder komt"
    rsync -a "$ORIG/references/annotator-snippet.html" "$SNIP"

    # Mutant B: start-range bestaat → wees, geen fallback.
    python3 - <<'PY' "$SNIP"
import sys
p = sys.argv[1]
t = open(p).read()
oud = """      if (range && laTekstNogDaar(range, tekst) && laLabelPast(range, loc.label)) {
        var rects = laRectsVanRange(range);
        if (rects) return rects;
      }"""
nieuw = """      if (range && laTekstNogDaar(range, tekst) && laLabelPast(range, loc.label)) {
        var rects = laRectsVanRange(range);
        if (rects) return rects;
      } else if (range) {
        return null;
      }"""
if oud not in t:
    raise SystemExit("anker voor zoekAnker-fallback ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
    case08 /tmp/ann-mut-b16-b.txt \
      "B16 blijft groen met de oude wees-te-vroeg-logica" \
      "B16 wordt rood als een bestaande start-span wees maakt"
    rsync -a "$ORIG/references/annotator-snippet.html" "$SNIP"

    python3 - <<'PY' "$SNIP"
import sys
p = sys.argv[1]
t = open(p).read()
oud = """  function zoekHostViaLabel(label) {
    var needle = laNorm(label);
    if (needle.length < 8) return null;"""
nieuw = """  function zoekHostViaLabel(label) {
    return null;
    var needle = laNorm(label);
    if (needle.length < 8) return null;"""
if oud not in t:
    raise SystemExit("anker voor zoekHostViaLabel ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
    case08 /tmp/ann-mut-b16-c.txt \
      "B16 blijft groen zonder zoekHostViaLabel" \
      "B16 wordt rood als het label de herhaalde tekst niet redt"
    rsync -a "$ORIG/references/annotator-snippet.html" "$SNIP"

    python3 - <<'PY' "$SNIP"
import sys
p = sys.argv[1]
t = open(p).read()
oud = '  var BRIDGE = (location.protocol.indexOf("http") === 0 && location.pathname.indexOf("/p/") === 0)'
nieuw = '  var BRIDGE = "http://127.0.0.1:8791"; var _MUT = (location.protocol.indexOf("http") === 0 && location.pathname.indexOf("/p/") === 0)'
if oud not in t:
    raise SystemExit("anker voor BRIDGE-origin ontbreekt")
open(p, "w").write(t.replace(oud, nieuw, 1))
PY
    case08 /tmp/ann-mut-bridge.txt \
      "B16 blijft groen als BRIDGE hard 8791 is" \
      "bridge-origin wordt rood als het snippet de /p/-poort negeert"
    rsync -a "$ORIG/references/annotator-snippet.html" "$SNIP"
    kill "$bpid" 2>/dev/null || true
    wait "$bpid" 2>/dev/null || true
  fi
fi

exit $falen
