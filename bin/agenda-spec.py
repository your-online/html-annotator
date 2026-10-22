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
"notitie" "door <NAAM> verplaatst van X naar Y". NAAM: --by, anders het veld
"movedBy" in de overlay, anders "reviewer". --page is standaard de overlay
zonder ".voorstellen.json" plus ".html". State via de bridge (POST /state),
anders rechtstreeks uit <annotatie-root>/<slug>/state.json. --dry-run schrijft niets.
"""
import argparse, datetime as D, json, os, re, sys, urllib.request
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


DN = ["ma", "di", "wo", "do", "vr", "za", "zo"]


def fmt(start, end):
    d = D.datetime.fromisoformat(start[:16])
    return f"{DN[d.weekday()]} {d.day:02d}-{d.month:02d} {start[11:16]}–{end[11:16]}"


def default_page(overlay):
    o = os.path.abspath(overlay)
    for suf in (".voorstellen.json", ".json"):
        if o.endswith(suf):
            return o[: -len(suf)] + ".html"
    return None


def read_state(page):
    """State van de pagina: eerst via de bridge, anders direct van schijf."""
    page = os.path.abspath(page)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    try:
        from html_annotator import config
        url = config.base_url() + "/state"
    except Exception:
        config, url = None, "http://127.0.0.1:8791/state"
    try:
        req = urllib.request.Request(url, data=json.dumps({"pageFile": page}).encode(),
                                     headers={"Content-Type": "application/json"})
        res = json.load(urllib.request.urlopen(req, timeout=3))
        if res.get("ok"):
            return res.get("state") or {}, res.get("statePath")
    except Exception:
        pass
    if config is None:
        raise SystemExit("bridge onbereikbaar en html_annotator niet importeerbaar")
    slug = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(os.path.basename(page))[0].lower()).strip("-")[:60] or "pagina"
    p = os.path.join(str(config.root()), slug, "state.json")
    try:
        return json.load(open(p, encoding="utf-8")), p
    except (OSError, ValueError):
        return {}, p


def apply_state(overlay, state, door=None):
    """Schrijft verplaatste voorstellen uit state terug in de overlay (in place).
    Geeft een lijst regels terug voor de uitvoer."""
    comp = ((state or {}).get("components") or {}).get("agenda") or {}
    door = (door or overlay.get("movedBy") or "reviewer").strip() or "reviewer"
    log = []
    for p in overlay.get("proposals", []):
        e = comp.get(f"voorstel-{p['nr']}")
        if not e or not e.get("start") or not e.get("end"):
            continue
        ns, ne = e["start"][:16], e["end"][:16]
        os_, oe = p["start"][:16], p["end"][:16]
        if (ns, ne) == (os_, oe):
            continue  # al in sync (of teruggezet naar voorstel)
        if p.get("status", "open") != "open":
            log.append(f"#{p['nr']} overgeslagen: status {p.get('status')}, de agenda is "
                       f"leidend (sleep naar {fmt(ns, ne)} genegeerd)")
            continue
        base = e.get("base") or {}
        if base and (base.get("start", "")[:16], base.get("end", "")[:16]) != (os_, oe):
            log.append(f"#{p['nr']} overgeslagen: overlay is na het slepen gewijzigd "
                       f"({fmt(os_, oe)}, sleep ging uit van {fmt(base['start'], base['end'])})")
            continue
        p["start"], p["end"] = ns, ne
        zin = f"door {door} verplaatst van {fmt(os_, oe)} naar {fmt(ns, ne)}"
        p["notitie"] = (p.get("notitie") + " · " + zin) if p.get("notitie") else zin
        log.append(f"#{p['nr']} {zin}")
    return log


def main_apply(a):
    page = a.page or default_page(a.apply_state)
    if not page:
        raise SystemExit("geef --page mee")
    overlay = json.load(open(a.apply_state, encoding="utf-8"))
    state, sp = read_state(page)
    log = apply_state(overlay, state, a.by)
    moved = [r for r in log if " overgeslagen: " not in r]
    if moved and not a.dry_run:
        with open(a.apply_state, "w", encoding="utf-8") as f:
            json.dump(overlay, f, ensure_ascii=False, indent=1)
    print(f"state: {sp}")
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
    ap.add_argument("--by", metavar="NAAM", help='wie sleepte (notitie "door NAAM verplaatst"); standaard overlay.movedBy, anders "reviewer"')
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
