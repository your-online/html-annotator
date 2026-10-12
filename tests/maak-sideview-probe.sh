#!/bin/bash
# Bouwt ~/Desktop/sideview-probe.html: een pagina met het gewone annotator-snippet plus
# een diagnoseblok, om te meten wat de ECHTE Claude Desktop-sideviewer doet. Dat is het
# surface the suite cannot cover (see CRITERIA.md B17).
#
#   ~/.claude/skills/html-annotator/tests/maak-sideview-probe.sh
#
# De diagnose gaat langs twee kanalen naar buiten, want precies het geval dat we willen
# uitsluiten — de bridge is onbereikbaar vanaf deze origin — is ook het geval waarin de
# pagina niets kan versturen:
#
#   1. via de bridge: fetch naar /ping?diag=<base64>. De bridge logt elke request-regel,
#      dus de diagnose belandt in bridge.log zonder dat er een endpoint bij hoeft.
#   2. op het scherm: een blok met dezelfde gegevens plus een kopieerknop, zodat de reviewer ze
#      kan plakken als kanaal 1 het niet haalt.
#
# Uitlezen doe je met lees-sideview-probe.sh.

set -uo pipefail
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOEL="$HOME/Desktop/sideview-probe.html"
PORT="${LUC_ANNOTATOR_PORT:-8791}"

[ -f "$SKILL_DIR/references/annotator-snippet.html" ] || { echo "FOUT: snippet niet gevonden" >&2; exit 1; }

{
cat <<HTML
<!doctype html>
<meta charset="utf-8">
<title>sideview-probe</title>
<style>
  body { font: 15px/1.5 -apple-system, system-ui, sans-serif; margin: 32px; max-width: 720px; }
  h1 { font-size: 20px; }
  #uitslag { border: 2px solid #999; border-radius: 8px; padding: 14px 16px; margin: 18px 0;
             background: #fafafa; color: #111; }
  #uitslag.goed { border-color: #1a7f37; background: #eaf7ee; }
  #uitslag.fout { border-color: #b3261e; background: #fdeceb; }
  #uitslag h2 { font-size: 15px; margin: 0 0 8px; }
  pre { white-space: pre-wrap; word-break: break-all; font-size: 12px; background: #fff;
        border: 1px solid #ddd; border-radius: 6px; padding: 10px; }
  button.kopieer { font: inherit; padding: 6px 12px; border-radius: 6px; border: 1px solid #888;
                   background: #fff; cursor: pointer; }
</style>

<h1>Sideview-probe</h1>
<p id="doel">Deze zin is er om op te annoteren. Selecteer hem en maak een annotatie zodra
de statuspil rechtsonder groen is.</p>

<div id="uitslag"><h2>Meten…</h2><p>Even wachten, de probe kijkt ~15 seconden mee.</p></div>
<pre id="ruw">—</pre>
<p><button class="kopieer" id="kopieer">Kopieer diagnose</button>
   <span id="kopiemeld"></span></p>

<script>
/* Vroeg beginnen: fouten die vóór de rest van het script optreden willen we ook hebben. */
(function () {
  "use strict";
  var BRIDGE = "http://127.0.0.1:$PORT";
  var fouten = [];
  var origFout = console.error;
  console.error = function () {
    try { fouten.push(Array.prototype.join.call(arguments, " ").slice(0, 400)); } catch (e) {}
    return origFout.apply(console, arguments);
  };
  window.addEventListener("error", function (e) {
    fouten.push("onerror: " + (e && e.message ? e.message : String(e)));
  });

  function feiten() {
    return {
      t: new Date().toISOString(),
      href: String(location.href).slice(0, 300),
      protocol: location.protocol,
      origin: String(location.origin),
      baseURI: String(document.baseURI || "").slice(0, 300),
      secure: !!window.isSecureContext,
      zichtbaar: document.visibilityState,
      ua: navigator.userAgent.slice(0, 220),
      /* Electron zet dit meestal; een gewone browser niet. Verraadt of we in de app zitten. */
      electron: /Electron/i.test(navigator.userAgent),
      pil: (document.getElementById("la-status") || {}).textContent || "(geen pil)",
      fouten: fouten.slice(-6)
    };
  }

  /* Losse fetch, buiten het snippet om: zo weten we of loopback vanaf deze origin
     überhaupt bereikbaar is, ongeacht wat het snippet doet. */
  function probeer() {
    return fetch(BRIDGE + "/ping", { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) { return { bereikbaar: true, antwoord: j }; })
      .catch(function (e) { return { bereikbaar: false, reden: String(e && e.message || e).slice(0, 300) }; });
  }

  function b64(s) {
    try { return btoa(unescape(encodeURIComponent(s))); } catch (e) { return "encode-fout"; }
  }

  /* Kanaal 1: de diagnose als queryparameter. De bridge logt de hele request-regel,
     dus dit landt in bridge.log. Lukt het niet, dan is dát het antwoord. */
  function stuur(rapport, fase) {
    var q = b64(JSON.stringify(rapport));
    return fetch(BRIDGE + "/ping?diag=" + fase + "." + q, { cache: "no-store" })
      .then(function () { return true; }).catch(function () { return false; });
  }

  var rapporten = [];
  function toon(kop, goed) {
    var d = document.getElementById("uitslag");
    d.className = goed === true ? "goed" : goed === false ? "fout" : "";
    d.innerHTML = "<h2>" + kop + "</h2>";
    document.getElementById("ruw").textContent = JSON.stringify(rapporten, null, 1);
  }

  document.getElementById("kopieer").addEventListener("click", function () {
    var t = JSON.stringify(rapporten, null, 1);
    var m = document.getElementById("kopiemeld");
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(
        function () { m.textContent = " gekopieerd — plak het in de chat"; },
        function () { m.textContent = " kopiëren geweigerd; selecteer de tekst hierboven"; });
    } else { m.textContent = " selecteer de tekst hierboven en kopieer met cmd+C"; }
  });

  /* Fase 1: direct bij het laden. Verwacht: bridge omlaag, dus onbereikbaar. */
  probeer().then(function (r1) {
    var f = feiten(); f.fase = "start"; f.loopback = r1;
    rapporten.push(f);
    toon(r1.bereikbaar ? "Start: bridge bereikbaar" : "Start: bridge niet bereikbaar (verwacht)", null);
    stuur(f, "start");

    /* Fase 2: 15 seconden meekijken. Zodra de bridge omhoog komt hoort de pil vanzelf
       om te slaan, zonder reload. Dat is de na-zwengel-vraag, op het echte oppervlak. */
    var stappen = 0;
    var timer = setInterval(function () {
      stappen++;
      var pil = (document.getElementById("la-status") || {}).textContent || "";
      var om = /round \\d+/.test(pil);
      if (om || stappen >= 15) {
        clearInterval(timer);
        probeer().then(function (r2) {
          var g = feiten(); g.fase = "eind"; g.loopback = r2; g.secondenGewacht = stappen;
          g.zelfherstel = om;
          rapporten.push(g);
          toon(om ? "GELUKT — de pil sloeg vanzelf om, zonder reload"
                  : "NIET GELUKT — de pil bleef staan: " + (pil || "(leeg)"), om);
          stuur(g, "eind").then(function (verstuurd) {
            if (!verstuurd) {
              var d = document.getElementById("uitslag");
              d.innerHTML += "<p><b>De bridge kon niet bereikt worden vanaf deze weergave.</b> " +
                "Kopieer de diagnose hieronder en plak hem in de chat.</p>";
            }
          });
        });
      }
    }, 1000);
  });
})();
</script>
HTML
cat "$SKILL_DIR/references/annotator-snippet.html"
} > "$DOEL"

echo "probe geschreven: $DOEL"
echo "open dit bestand in de Claude Desktop-sideviewer."
