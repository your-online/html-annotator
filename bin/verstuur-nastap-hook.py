#!/usr/bin/env python3
"""PostToolUse-nastap voor verzendtools (Verstuur-knop, eerst alleen WhatsApp).

Na een geslaagde verzending wordt het bijbehorende akkoord verbruikt: status "sent"
via /send-done. Daarmee laat de gate (verstuur-gate-hook.py) dezelfde tekst niet nog
eens door, en toont de kaart "Verstuurd <tijd>".

- Geen akkoord met deze hash (verstuurd via het chatpad): niets te doen.
- Tool meldt expliciet mislukking ("success": false): akkoord blijft staan, zodat een
  nieuwe poging kan; de agent krijgt dat te horen.
- Uitkomst onduidelijk: toch verbruiken. Liever een tweede klik dan een dubbel bericht.

Eerst via de bridge (POST /send-done, zonder Origin: alleen een lokaal proces mag dat);
draait de bridge niet, dan dezelfde handler in-process op state.json.
"""
import json, os, sys, urllib.error, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from html_annotator import config, verstuur  # noqa: E402


def gelukt(resp):
    """True/False als de tool het zegt, None als het niet te zien is."""
    kandidaten = [resp]
    if isinstance(resp, dict):
        kandidaten += [resp.get("structuredContent"), resp.get("result")]
        kandidaten += [c.get("text") for c in resp.get("content") or [] if isinstance(c, dict)]
    if isinstance(resp, list):
        kandidaten += [c.get("text") for c in resp if isinstance(c, dict)]
    for k in kandidaten:
        if isinstance(k, str):
            try:
                k = json.loads(k)
            except ValueError:
                continue
        if isinstance(k, dict) and isinstance(k.get("success"), bool):
            return k["success"]
        if isinstance(k, dict) and k.get("isError") is True:
            return False
    return None


def meld(tekst):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
          "additionalContext": tekst}}, ensure_ascii=False))
    sys.exit(0)


def send_done(payload):
    basis = "http://%s:%d" % (config.HOST, config.port())
    req = urllib.request.Request(basis + "/send-done", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.load(r), "bridge"
    except urllib.error.HTTPError as e:
        return json.load(e), "bridge"
    except OSError:
        from html_annotator import bridge
        try:
            return bridge.h_send_done(payload), "in-process"
        except ValueError as ex:
            return {"ok": False, "error": str(ex)}, "in-process"


def main():
    ev = json.load(sys.stdin)
    tool = ev.get("tool_name", "")
    h = verstuur.hash_voor(tool, ev.get("tool_input"))
    if h is None:
        sys.exit(0)
    gevonden = verstuur.zoek_akkoord(h)
    if not gevonden:
        sys.exit(0)  # geen knop-akkoord: verstuurd via het chatpad
    pad, data, key, e = gevonden
    if gelukt(ev.get("tool_response")) is False:
        meld("Verzending mislukt volgens %s; Verstuur-akkoord %s blijft staan." % (tool, key))
    payload = {"page": data.get("page"), "pageFile": data.get("pageFile"),
               "slug": os.path.basename(os.path.dirname(pad)),
               "key": key, "approvalId": e.get("approvalId"), "hash": h, "via": tool}
    r, route = send_done(payload)
    if r.get("ok"):
        meld("Verstuur-akkoord %s verbruikt (%s): kaart toont nu Verstuurd." % (key, route))
    meld("LET OP: akkoord %s niet verbruikt (%s: %s). Meld /send-done handmatig, anders "
         "laat de gate dezelfde tekst nog eens door." % (key, route, r.get("error")))


if __name__ == "__main__":
    main()
