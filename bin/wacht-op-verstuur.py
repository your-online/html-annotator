#!/usr/bin/env python3
"""Wacht tot de reviewer op Verstuur klikt op een la-draft-kaart.

Draai dit als achtergrondtaak (run_in_background) in de sessie die het concept maakte:
    python3 bin/wacht-op-verstuur.py --page http://127.0.0.1:8791/p/Desktop/x.html --key wa-nard
(--page mag ook het bestandspad zijn: ~/Desktop/x.html.)

Zodra de klik binnen is (status "approved", hash klopt) print het script het akkoord
als JSON en stopt: de achtergrondtaak eindigt en de sessie wordt wakker met dit als
eigen tool-resultaat. Er komt geen peer-bericht aan te pas.

Wat de agent daarna doet staat in "vervolg" in de uitvoer: precies één verzendtool-
aanroep met exact deze ontvanger en tekst. De PreToolUse-gate laat die alleen door als
de hash klopt; de PostToolUse-nastap verbruikt het akkoord. Het script verstuurt zelf niets.

Exitcodes: 0 akkoord, 1 timeout, 2 hash klopt niet, 3 al verstuurd.
"""
import argparse, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from html_annotator.bridge import send_hash  # noqa: E402  (zelfde canonieke hash)

TOOL = {"whatsapp": ("mcp__whatsapp__send_message", "recipient", "message")}


def pagina(page):
    if "/p/" in page or page.startswith("file://"):
        return {"page": page}
    return {"pageFile": os.path.abspath(os.path.expanduser(page))}


def state(base, page):
    req = urllib.request.Request(base + "/state", data=json.dumps(pagina(page)).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)["state"]


def vervolg(e):
    t = TOOL.get(e.get("channel"))
    if not t:
        return "kanaal %r heeft geen Verstuur-gate: vraag de reviewer in de chat" % e.get("channel")
    return {"tool": t[0], "arguments": {t[1]: e.get("to"), t[2]: e.get("text")},
            "regel": "exact deze argumenten, één keer; niets aan de tekst veranderen. "
                     "Vraagt Claude Code alsnog om toestemming, dan klopt er iets niet: stop en meld het."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True, help="/p/-URL of bestandspad van de pagina")
    ap.add_argument("--key", required=True, help="waarde van data-la-send op de kaart")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--bridge", default="http://127.0.0.1:%s" % os.environ.get("HTML_ANNOTATOR_PORT", "8791"))
    a = ap.parse_args()
    eind = time.time() + a.timeout
    while time.time() < eind:
        try:
            e = ((state(a.bridge, a.page).get("components") or {}).get("send") or {}).get(a.key)
        except Exception as ex:
            e = None
            print("bridge niet bereikbaar: %s" % ex, file=sys.stderr)
        if e and e.get("status") == "sent":
            print(json.dumps({"ok": False, "fout": "al verstuurd om %s; niets doen" % e.get("sentAt")}))
            return 3
        if e and e.get("status") == "approved":
            if send_hash(e) != e.get("hash"):
                print(json.dumps({"ok": False, "fout": "hash klopt niet met de vastgelegde velden"}))
                return 2
            print(json.dumps({"ok": True, "akkoord": {k: e.get(k) for k in
                  ("channel", "to", "subject", "text", "hash", "approvalId", "approvedAt")},
                  "vervolg": vervolg(e)}, ensure_ascii=False, indent=1))
            return 0
        time.sleep(1)
    print(json.dumps({"ok": False, "fout": "timeout, geen klik"}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
