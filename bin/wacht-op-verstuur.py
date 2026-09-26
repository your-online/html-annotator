#!/usr/bin/env python3
"""Wacht tot de reviewer op Verstuur klikt op een la-draft-kaart (prototype).

Draai dit als achtergrondtaak in de sessie die het concept maakte:
    python bin/wacht-op-verstuur.py --page Desktop/x.html --key mail-alex [--timeout 3600]
Zodra de klik binnen is (status "approved", hash klopt) print het script het akkoord
als JSON en stopt: de achtergrondtaak eindigt en de sessie wordt wakker met dit als
eigen tool-resultaat. Er komt geen peer-bericht aan te pas.

Het script verstuurt zelf niets.
"""
import argparse, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from html_annotator.bridge import send_hash  # noqa: E402  (zelfde canonieke hash)


def state(base, page):
    req = urllib.request.Request(base + "/state", data=json.dumps({"page": page}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)["state"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--bridge", default="http://127.0.0.1:%s" % os.environ.get("HTML_ANNOTATOR_PORT", "8791"))
    a = ap.parse_args()
    eind = time.time() + a.timeout
    gezien = None
    while time.time() < eind:
        try:
            e = ((state(a.bridge, a.page).get("components") or {}).get("send") or {}).get(a.key)
        except Exception as ex:
            e = None
            print("bridge niet bereikbaar: %s" % ex, file=sys.stderr)
        if e and e.get("status") == "approved" and e.get("approvalId") != gezien:
            if send_hash(e) != e.get("hash"):
                print(json.dumps({"ok": False, "fout": "hash klopt niet met de vastgelegde velden"}))
                return 2
            print(json.dumps({"ok": True, "akkoord": {k: e.get(k) for k in
                  ("channel", "to", "subject", "text", "hash", "approvalId", "approvedAt")}},
                  ensure_ascii=False, indent=1))
            return 0
        time.sleep(1)
    print(json.dumps({"ok": False, "fout": "timeout, geen klik"}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
