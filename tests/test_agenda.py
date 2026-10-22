#!/usr/bin/env python3
"""B47: agenda-preview: slepen → state → sync terug in de overlay.

Raakt alleen de CLI-randen: bin/agenda-spec.py (bouwen + --apply-state) en
bin/agenda-preview.py (renderen). Geen bridge nodig: de sync valt terug op
<HTML_ANNOTATOR_ROOT>/<slug>/state.json; de poort wijst naar niets.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(SKILL, "bin", "agenda-spec.py")
PREVIEW = os.path.join(SKILL, "bin", "agenda-preview.py")


def check(naam, conditie):
    if not conditie:
        print("FAIL  %s" % naam)
        return 1
    print("PASS  %s" % naam)
    return 0


def vrije_poort():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def draai(env, *args):
    return subprocess.run([sys.executable, *args], env=env, capture_output=True, text=True)


def prop(nr, start, end, notitie=""):
    return {"nr": nr, "title": "Pair %d" % nr, "start": start, "end": end,
            "invitees": ["x%d@example.com" % nr], "toelichting": "", "notitie": notitie,
            "status": "open"}


def main():
    n = 0
    tmp = tempfile.mkdtemp(prefix="agenda-test-")
    root = os.path.join(tmp, "root")
    cfg = os.path.join(tmp, "cfg")  # eigen configmap: nooit het echte configbestand lezen
    env = dict(os.environ, HTML_ANNOTATOR_ROOT=root, HTML_ANNOTATOR_PORT=str(vrije_poort()),
               XDG_CONFIG_HOME=cfg, APPDATA=cfg)
    page = os.path.join(tmp, "Planning Test.html")
    overlay = os.path.join(tmp, "Planning Test.voorstellen.json")
    ov = {"heading": "test", "proposals": [
        prop(1, "2026-10-07T09:45", "2026-10-07T10:30"),
        prop(2, "2026-10-07T15:00", "2026-10-07T15:45", notitie="optioneel"),
        prop(3, "2026-10-08T10:00", "2026-10-08T10:45"),
        prop(4, "2026-10-08T13:00", "2026-10-08T13:45"),
        dict(prop(5, "2026-10-08T15:00", "2026-10-08T15:45"), status="verstuurd"),
    ]}
    json.dump(ov, open(overlay, "w"), ensure_ascii=False, indent=1)
    cal = os.path.join(tmp, "cal.json")
    json.dump({"value": [{"subject": "Refinement", "start": {"dateTime": "2026-10-08T13:00:00", "timeZone": "Europe/Amsterdam"},
                          "end": {"dateTime": "2026-10-08T15:00:00", "timeZone": "Europe/Amsterdam"}}]}, open(cal, "w"))
    # State zoals de pagina hem schrijft: slug = bestandsnaam zonder extensie.
    os.makedirs(os.path.join(root, "planning-test"))
    state = {"components": {"agenda": {
        # 1: verplaatst naar een andere dag
        "voorstel-1": {"start": "2026-10-09T14:00", "end": "2026-10-09T14:45",
                       "base": {"start": "2026-10-07T09:45", "end": "2026-10-07T10:30"}},
        # 2: bovenrand omhoog, bestaande notitie blijft staan
        "voorstel-2": {"start": "2026-10-07T14:30", "end": "2026-10-07T15:45",
                       "base": {"start": "2026-10-07T15:00", "end": "2026-10-07T15:45"}},
        # 3: teruggezet naar voorstel → niets doen
        "voorstel-3": {"start": "2026-10-08T10:00", "end": "2026-10-08T10:45",
                       "base": {"start": "2026-10-08T10:00", "end": "2026-10-08T10:45"}},
        # 4: overlay is na het slepen door de agent gewijzigd → oude state niet toepassen
        "voorstel-4": {"start": "2026-10-08T16:00", "end": "2026-10-08T16:45",
                       "base": {"start": "2026-10-08T11:00", "end": "2026-10-08T11:45"}},
        # 5: al verstuurd → de agenda is leidend, sleep negeren
        "voorstel-5": {"start": "2026-10-08T16:00", "end": "2026-10-08T16:45",
                       "base": {"start": "2026-10-08T15:00", "end": "2026-10-08T15:45"}},
    }}}
    json.dump(state, open(os.path.join(root, "planning-test", "state.json"), "w"))
    open(page, "w").write("<html></html>")

    voor = open(overlay).read()
    r = draai(env, SPEC, "--apply-state", overlay, "--dry-run")
    n += check("B47 dry-run schrijft niets", r.returncode == 0 and open(overlay).read() == voor
               and "#1 door reviewer verplaatst" in r.stdout)

    SYNC = os.path.join(SKILL, "bin", "agenda-sync.py")
    r = draai(env, SYNC, overlay)  # alias; --page afgeleid uit de overlaynaam
    na = {p["nr"]: p for p in json.load(open(overlay))["proposals"]}
    n += check("B47 sync draait (page afgeleid)", r.returncode == 0)
    n += check("B47 verplaatst naar andere dag",
               (na[1]["start"], na[1]["end"]) == ("2026-10-09T14:00", "2026-10-09T14:45"))
    n += check("B47 notitie zegt van X naar Y",
               na[1]["notitie"] == "door reviewer verplaatst van wo 07-10 09:45–10:30 naar vr 09-10 14:00–14:45")
    n += check("B47 resize bovenrand + bestaande notitie behouden",
               na[2]["start"] == "2026-10-07T14:30" and na[2]["notitie"].startswith("optioneel · door reviewer verplaatst"))
    n += check("B47 teruggezet voorstel ongemoeid", na[3]["start"] == "2026-10-08T10:00" and na[3]["notitie"] == "")
    n += check("B47 verouderde state niet toegepast",
               na[4]["start"] == "2026-10-08T13:00" and "#4 overgeslagen" in r.stdout)

    n += check("B47 verstuurd voorstel niet verplaatst",
               na[5]["start"] == "2026-10-08T15:00" and "#5 overgeslagen: status verstuurd" in r.stdout)

    # Wie sleepte is instelbaar: --by wint van overlay.movedBy, dat wint van "reviewer".
    ov2 = os.path.join(tmp, "Planning Test.by.voorstellen.json")
    json.dump(dict(ov, movedBy="planner"), open(ov2, "w"), ensure_ascii=False)
    r = draai(env, SPEC, "--apply-state", ov2, "--page", page, "--dry-run")
    n += check("B47 movedBy uit de overlay", "#1 door planner verplaatst" in r.stdout)
    r = draai(env, SYNC, ov2, "--page", page, "--by", "teamlead", "--dry-run")
    n += check("B47 --by wint van movedBy", "#1 door teamlead verplaatst" in r.stdout)

    na_txt = open(overlay).read()
    r = draai(env, SPEC, "--apply-state", overlay)
    n += check("B47 tweede sync is no-op", open(overlay).read() == na_txt and "#1" not in r.stdout)

    # Opnieuw renderen geeft de nieuwe stand, met de drag-code en de state-sleutels.
    spec = os.path.join(tmp, "spec.json")
    out = os.path.join(tmp, "out.html")
    r1 = draai(env, SPEC, "--cal", "werk:Werk:purple:" + cal, "--start", "2026-10-05",
               "--overlay", overlay, "-o", spec)
    r2 = draai(env, PREVIEW, spec, "-o", out, "--no-snippet")
    n += check("B47 render draait", r1.returncode == 0 and r2.returncode == 0)
    h = open(out, encoding="utf-8").read()
    data = json.loads(h.split('id="agenda-data">', 1)[1].split("</script>", 1)[0].replace("<\\/", "</"))
    p1 = [p for p in data["proposals"] if p["nr"] == 1][0]
    n += check("B47 render toont gesyncte tijd", p1["start"] == "2026-10-09T14:00")
    for naam, stuk in [("pointer events", "pointerdown"), ("pointercancel (touch)", "pointercancel"),
                       ("snap 15", "SNAP=15"), ("grepen boven/onder", 'data-h="top"'),
                       ("grepen onder", 'data-h="bottom"'), ("state-save", "'/state-save'"),
                       ("state laden", "'/state'"), ("component agenda", "component:'agenda'"),
                       ("key voorstel-<nr>", "'voorstel-'+x.nr"), ("base meegeschreven", "base:{start:"),
                       ("pil", 'id="agsave"'), ("bridge uit", "bridge uit"),
                       ("terug naar voorstel", "terug naar voorstel"), ("overlap-waarschuwing", "clash")]:
        n += check("B47 html bevat %s" % naam, stuk in h)
    return n


if __name__ == "__main__":
    fouten = main()
    print("%d fout(en)" % fouten if fouten else "alles groen")
    sys.exit(1 if fouten else 0)
