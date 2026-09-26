#!/usr/bin/env python3
"""Dummy-kanaal voor het prototype: 'verstuurt' naar een logbestand, nooit naar buiten.

Doet vlak voor verzending wat een echte verzendstap ook moet doen:
1. akkoord opnieuw ophalen (niet uit het geheugen van de wachter);
2. status moet nog 'approved' zijn en approvalId/hash moeten gelijk zijn aan wat de
   agent denkt te versturen (dus niet ingetrokken of vervangen sinds de klik);
3. hash opnieuw berekenen over de velden die daadwerkelijk verstuurd worden;
4. pas dan versturen, en /send-done melden.
"""
import argparse, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from html_annotator.bridge import send_hash  # noqa: E402


def post(base, pad, body):
    req = urllib.request.Request(base + pad, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--approval-id", required=True)
    ap.add_argument("--hash", required=True)
    ap.add_argument("--text-file", required=True, help="de tekst die de agent gaat versturen")
    ap.add_argument("--to", required=True)
    ap.add_argument("--channel", required=True)
    ap.add_argument("--subject", default="")
    ap.add_argument("--log", required=True)
    ap.add_argument("--bridge", default="http://127.0.0.1:%s" % os.environ.get("HTML_ANNOTATOR_PORT", "8791"))
    a = ap.parse_args()
    tekst = open(a.text_file, encoding="utf-8").read()
    e = ((post(a.bridge, "/state", {"page": a.page})["state"].get("components") or {}).get("send") or {}).get(a.key) or {}
    if e.get("status") != "approved":
        sys.exit("GEWEIGERD: geen geldig akkoord (status %s)" % e.get("status"))
    if e.get("approvalId") != a.approval_id or e.get("hash") != a.hash:
        sys.exit("GEWEIGERD: akkoord is vervangen sinds de wachter het zag")
    teversturen = {"channel": a.channel, "to": a.to, "subject": a.subject, "text": tekst}
    if send_hash(teversturen) != e["hash"]:
        sys.exit("GEWEIGERD: wat je wilt versturen wijkt af van de goedgekeurde tekst")
    with open(a.log, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(teversturen, at=time.strftime("%H:%M:%S")), ensure_ascii=False) + "\n")
    r = post(a.bridge, "/send-done", {"page": a.page, "key": a.key, "approvalId": a.approval_id,
                                      "hash": a.hash, "via": "dummy:" + a.log})
    print(json.dumps({"verstuurd": True, "bridge": r}, ensure_ascii=False))


if __name__ == "__main__":
    main()
