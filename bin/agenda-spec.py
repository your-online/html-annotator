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
"""
import argparse, datetime as D, json, re
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cal", action="append", required=True)
    ap.add_argument("--start")
    ap.add_argument("--weeks", type=int, default=2)
    ap.add_argument("--overlay")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
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
