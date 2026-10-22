#!/usr/bin/env python3
"""Bouw een agenda-preview-spec uit Graph get-calendar-view-output.

    python3 agenda-spec.py \
      --cal werk:Werk:purple:werk.json \
      --cal prive:Privé:orange:prive.json \
      --start 2026-10-05 --weeks 3 \
      --overlay voorstellen.json -o spec.json
    python3 agenda-preview.py spec.json -o pagina.html

--cal  id:label:kleur:pad   pad = ruwe JSON van get-calendar-view ({"value":[...]}
                            of een lijst). Haal op met timezone="Europe/Amsterdam"
                            en select="id,subject,start,end,isAllDay,showAs,
                            attendees,organizer,bodyPreview,location,isCancelled"
                            (UTC-tijden worden zo nodig omgerekend).
--overlay pad               JSON met topniveau-velden die de spec aanvullen:
                            heading, subheading, title, proposals, tags, hours, ...

Sync na slepen (vóór elke volgende stap draaien):

    python3 agenda-spec.py --apply-state pagina.voorstellen.json [--page pagina.html] [--by NAAM]

Leest de state van de pagina (component "agenda", key "voorstel-<nr>" met
{start, end, base}) en schrijft verplaatste tijden terug in de overlay, met in
"notitie" "moved by <NAAM> from X to Y". NAAM: --by, anders het veld
"movedBy" in de overlay, anders "reviewer". --page is standaard de overlay
zonder ".voorstellen.json" plus ".html"; bestaat die pagina niet, dan stopt de
sync (geef --page mee). Alleen voorstellen die op de pagina open zijn (de status
zoals agenda-preview hem afleidt, dus ook niet als er al een echt event is) en in
de overlay open staan, worden verplaatst. Na het terugschrijven krijgt de entry
in de state base = de nieuwe tijd (en applied = {from, to}): die sleep is verwerkt
en komt niet terug als de agent het voorstel later zelf verzet. Een volgende sleep
op de nog niet herbouwde pagina (base = de tijd van vóór de sync) wordt wel
toegepast, zolang de overlay sinds die sync niet veranderd is. State via de
bridge (POST /state en /state-save); draait er geen bridge (verbinding geweigerd),
dan rechtstreeks in <annotatie-root>/<slug>/state.json. Antwoordt de bridge met
een fout (ok:false, HTTP-fout, time-out), dan stopt de sync. De uitvoer noemt de
gebruikte route: "state: <pad> (bridge)" of "(disk)". --dry-run schrijft niets.
"""
import argparse, datetime as D, json, os, re, sys, urllib.error, urllib.request
from zoneinfo import ZoneInfo

AMS = ZoneInfo("Europe/Amsterdam")


def t(x):
    s = x["dateTime"][:19]
    d = D.datetime.fromisoformat(s)
    if (x.get("timeZone") or "").upper() in ("UTC", "ETC/UTC"):
        d = d.replace(tzinfo=D.timezone.utc).astimezone(AMS).replace(tzinfo=None)
    return d.strftime("%Y-%m-%dT%H:%M")


def clean_body(b):
    b = (b or "").replace("\r\n", "\n")
    b = re.split(r"\n?[_.]{20,}", b)[0]  # Teams-blok en scheidingslijnen eraf
    return b.strip()


def person(a):
    ea = a.get("emailAddress") or {}
    return {"name": ea.get("name", ""), "address": ea.get("address", ""),
            "type": a.get("type", ""), "response": (a.get("status") or {}).get("response", "")}


def convert(cal, raw):
    v = raw["value"] if isinstance(raw, dict) else raw
    out = []
    for e in v:
        if e.get("isCancelled"):
            continue
        org = (e.get("organizer") or {}).get("emailAddress") or {}
        loc = (e.get("location") or {}).get("displayName", "")
        out.append({
            "cal": cal, "title": e.get("subject", ""), "start": t(e["start"]), "end": t(e["end"]),
            "allDay": bool(e.get("isAllDay")), "showAs": e.get("showAs", ""),
            "attendees": [person(a) for a in e.get("attendees") or []],
            "organizer": {"name": org.get("name", ""), "address": org.get("address", "")} if org else None,
            "body": clean_body(e.get("bodyPreview")), "location": loc,
        })
    return out


DN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt(start, end):
    d = D.datetime.fromisoformat(start[:16])
    return f"{DN[d.weekday()]} {d.day:02d}-{d.month:02d} {start[11:16]}–{end[11:16]}"


def default_page(overlay):
    o = os.path.abspath(overlay)
    for suf in (".voorstellen.json", ".json"):
        if o.endswith(suf):
            return o[: -len(suf)] + ".html"
    return None


def _bridge():
    """De bridge-module zelf: zelfde slug- en state-regels, geen kopie."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from html_annotator import bridge, config
    return bridge, config


def page_info(page):
    """De agenda-data van de gebouwde pagina: slug en de afgeleide status per voorstel.
    Nooit raden: zonder paginabestand leest de bridge de state van een andere pagina."""
    try:
        h = open(page, encoding="utf-8").read()
    except OSError:
        raise SystemExit(f"pagina {page} bestaat niet; geef --page <pagina>.html mee (het -o-bestand van agenda-preview)")
    try:
        data = json.loads(h.split('id="agenda-data">', 1)[1].split("</script>", 1)[0].replace("<\\/", "</"))
    except (IndexError, ValueError):
        raise SystemExit(f"{page} is geen agenda-preview-pagina (geen agenda-data); geef --page mee")
    return data.get("slug"), {p["nr"]: p.get("status", "open") for p in data.get("proposals", [])}


def _call(route, payload):
    """POST naar de bridge. Alleen als er geen bridge draait (verbinding geweigerd)
    dezelfde handler rechtstreeks op schijf; een bridge die wel antwoordt maar faalt
    (ok:false, HTTP-fout, time-out) is een fout, nooit stil op schijf verder.
    Geeft (antwoord, "bridge" | "disk") terug."""
    bridge, config = _bridge()
    url = config.base_url() + route
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            res = json.load(e)
        except ValueError:
            res = {"ok": False, "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError):
            return {"/state": bridge.h_state, "/state-save": bridge.h_state_save}[route](payload), "disk"
        raise SystemExit(f"bridge {url} faalde ({e.reason}); sync gestopt")
    except (OSError, ValueError) as e:
        raise SystemExit(f"bridge {url} faalde ({e}); sync gestopt")
    if not isinstance(res, dict) or not res.get("ok"):
        fout = res.get("error") if isinstance(res, dict) else None
        raise SystemExit(f"bridge {url} gaf ok:false ({fout or res}); sync gestopt")
    return res, "bridge"


def read_state(page, slug=None):
    """State van de pagina: via de bridge, of van schijf als er geen bridge draait."""
    res, via = _call("/state", {"pageFile": os.path.abspath(page), "slug": slug})
    return res.get("state") or {}, res.get("statePath"), via


def mark_applied(page, slug, toegepast):
    """Verwerkte sleeps: base = de nieuwe tijd, zodat ze nooit nog eens toegepast worden;
    applied onthoudt van welke tijd naar welke, voor een sleep op de oude pagina."""
    for nr, (ns, ne), (os_, oe) in toegepast:
        _call("/state-save", {"pageFile": os.path.abspath(page), "slug": slug, "component": "agenda",
                              "key": f"voorstel-{nr}", "value": {
                                  "base": {"start": ns, "end": ne},
                                  "applied": {"from": {"start": os_, "end": oe}, "to": {"start": ns, "end": ne}}}})


def apply_state(overlay, state, door=None, status=None):
    """Schrijft verplaatste voorstellen uit state terug in de overlay (in place).
    status: {nr: status} zoals de pagina hem toont (afgeleid door agenda-preview).
    Geeft (regels voor de uitvoer, [(nr, (nieuw), (oud))] van de toegepaste) terug."""
    comp = ((state or {}).get("components") or {}).get("agenda") or {}
    door = (door or overlay.get("movedBy") or "reviewer").strip() or "reviewer"
    log, toegepast = [], []
    for p in overlay.get("proposals", []):
        e = comp.get(f"voorstel-{p['nr']}")
        if not e or not e.get("start") or not e.get("end"):
            continue
        ns, ne = e["start"][:16], e["end"][:16]
        os_, oe = p["start"][:16], p["end"][:16]
        base = e.get("base") or {}
        if (ns, ne) == (os_, oe) or (base and (base.get("start", "")[:16], base.get("end", "")[:16]) == (ns, ne)):
            continue  # al in sync, teruggezet naar voorstel, of al verwerkt
        st = p.get("status", "open")
        if st == "open" and status:
            st = status.get(p["nr"], st)
        if st != "open":
            log.append(f"#{p['nr']} overgeslagen: status {st}, de agenda is "
                       f"leidend (sleep naar {fmt(ns, ne)} genegeerd)")
            continue
        # Een sleep op de pagina van vóór de vorige sync heeft base = de tijd van vóór die
        # sync; die geldt nog zolang de overlay staat waar die sync hem neerzette.
        ap = e.get("applied") or {}
        kort = lambda x: ((x or {}).get("start", "")[:16], (x or {}).get("end", "")[:16])
        oude_pagina = bool(ap) and kort(ap.get("from")) == kort(base) and kort(ap.get("to")) == (os_, oe)
        if base and kort(base) != (os_, oe) and not oude_pagina:
            log.append(f"#{p['nr']} overgeslagen: overlay is na het slepen gewijzigd "
                       f"({fmt(os_, oe)}, sleep ging uit van {fmt(base['start'], base['end'])})")
            continue
        p["start"], p["end"] = ns, ne
        zin = f"moved by {door} from {fmt(os_, oe)} to {fmt(ns, ne)}"
        p["notitie"] = (p.get("notitie") + " · " + zin) if p.get("notitie") else zin
        log.append(f"#{p['nr']} {zin}")
        toegepast.append((p["nr"], (ns, ne), (os_, oe)))
    return log, toegepast


def main_apply(a):
    page = a.page or default_page(a.apply_state)
    if not page:
        raise SystemExit("geef --page mee")
    slug, status = page_info(page)
    overlay = json.load(open(a.apply_state, encoding="utf-8"))
    state, sp, via = read_state(page, slug)
    log, toegepast = apply_state(overlay, state, a.by, status)
    moved = [r for r in log if " overgeslagen: " not in r]
    if moved and not a.dry_run:
        with open(a.apply_state, "w", encoding="utf-8") as f:
            json.dump(overlay, f, ensure_ascii=False, indent=1)
        mark_applied(page, slug, toegepast)
    print(f"state: {sp} ({via})")
    print("\n".join(log) if log else "geen verplaatsingen; overlay ongewijzigd")
    if moved and a.dry_run:
        print("(dry-run: niets geschreven)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cal", action="append")
    ap.add_argument("--start")
    ap.add_argument("--weeks", type=int, default=2)
    ap.add_argument("--overlay")
    ap.add_argument("-o", "--out")
    ap.add_argument("--apply-state", metavar="OVERLAY")
    ap.add_argument("--page")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--by", metavar="NAAM", help='wie sleepte (notitie "moved by NAAM"); standaard overlay.movedBy, anders "reviewer"')
    a = ap.parse_args()
    if a.apply_state:
        return main_apply(a)
    if not a.cal or not a.out:
        ap.error("--cal en -o zijn verplicht (of gebruik --apply-state)")
    spec = {"start": a.start, "weeks": a.weeks, "calendars": [], "events": [], "proposals": []}
    for c in a.cal:
        cid, label, color, path = c.split(":", 3)
        spec["calendars"].append({"id": cid, "label": label, "color": color})
        spec["events"] += convert(cid, json.load(open(path)))
    if a.overlay:
        spec.update(json.load(open(a.overlay)))
    json.dump(spec, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{a.out}: {len(spec['events'])} events, {len(spec['proposals'])} voorstellen")


if __name__ == "__main__":
    main()
