#!/usr/bin/env python3
"""Verstuur-knop (mail): wat het akkoord dekt, de gate op send-mail en reply-mail-message,
tekst<->HTML, wachter en nastap. Zelfde opzet als test_verstuur.py: eigen bridge op een
vrije poort, tijdelijke root, dummy-kanaal. Er gaat geen mail de deur uit.
"""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(TESTS)
sys.path.insert(0, TESTS)
sys.path.insert(0, SKILL)
from test_bridge_contract import check, http, start_bridge, vrije_poort  # noqa: E402
from test_verstuur import hook, regels, stop  # noqa: E402

BIN = os.path.join(SKILL, "bin")
VAN = "owner@example.com"
AAN = "alex@example.com"
CC = "sam@example.com"
ONDERWERP = "Planning vrijdag"
TEKST = "Hi Alex,\n\nDe planning staat vrijdag klaar.\nKlopt 10:00 nog?\n\nGroet,\nSam"
SEND = "mcp__ms365-thuis__send-mail"
REPLY = "mcp__ms365-thuis__reply-mail-message"


def html(t):
    from html_annotator.verstuur import tekst_naar_html
    return tekst_naar_html(t)


def lijst(*a):
    return [{"emailAddress": {"address": x}} for x in a]


def nieuw(text=TEKST, account=VAN, to=(AAN,), cc=(CC,), subject=ONDERWERP, **extra):
    m = {"subject": subject, "body": {"contentType": "html", "content": html(text)},
         "toRecipients": lijst(*to)}
    if cc:
        m["ccRecipients"] = lijst(*cc)
    m.update(extra)
    i = {"body": {"Message": m, "SaveToSentItems": True}}
    if account is not None:
        i["account"] = account
    return i


def antwoord(text=TEKST, mid="AAMkAD-msg-1", to=(AAN,), cc=()):
    m = {"toRecipients": lijst(*to)} if to else {}
    if cc:
        m["ccRecipients"] = lijst(*cc)
    return {"account": VAN, "messageId": mid, "body": {"Comment": html(text), "Message": m}}


def gate(tool, invoer):
    return hook("verstuur-gate-hook.py", {"tool_name": tool, "tool_input": invoer}).get("permissionDecision")


def dummy(tool, invoer, log):
    tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(invoer, tf)
    tf.close()
    r = subprocess.run([sys.executable, os.path.join(BIN, "dummy-verstuur.py"), "--tool", tool,
                        "--input-file", tf.name, "--log", log], capture_output=True, text=True, timeout=30)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else {"stderr": r.stderr})


def main():
    n = 0
    # Eigen configbestand met de account→server-koppeling; ook de wachter (subproces) leest het.
    cfg = tempfile.mkdtemp(prefix="ann-cfg-")
    os.environ["XDG_CONFIG_HOME"] = os.environ["APPDATA"] = cfg
    from html_annotator import config
    config.write_config({"mail_servers": {VAN: "ms365-thuis"}})
    from html_annotator import verstuur
    from html_annotator.bridge import send_hash

    # --- zonder bridge: tekst <-> HTML en de WhatsApp-hash ---------------------------
    for t in (TEKST, "a", "a\n\n\nb", "<b>x</b> & y", "\n\nx\n", "regel<br>letterlijk"):
        n += check("M0 tekst->html->tekst is exact (%r)" % t[:14],
                   verstuur.html_naar_tekst(verstuur.tekst_naar_html(t)) == t)
    for slecht in ("<p>a</p><div>b</div>", "<p class='x'>a</p>", "<p>a<b>vet</b></p>",
                   "<p>a</p>\n<p>b</p>", "a", "<p>a<br/>b</p>", "<p>a &nbsp;</p>"):
        try:
            verstuur.html_naar_tekst(slecht)
            ok = False
        except verstuur.Ongeldig:
            ok = True
        n += check("M0 geen vaste weergave -> Ongeldig (%s)" % slecht[:22], ok)
    wa = {"channel": "whatsapp", "to": "31600000001", "subject": "", "text": "hoi"}
    oud = hashlib.sha256(json.dumps(wa, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()
    n += check("M0 WhatsApp-hash ongewijzigd door de mailvelden (B1)", send_hash(wa) == oud)

    root = tempfile.mkdtemp(prefix="ann-root-")
    poort = vrije_poort()
    os.environ["HTML_ANNOTATOR_ROOT"] = root
    os.environ["HTML_ANNOTATOR_PORT"] = str(poort)
    os.environ.pop("LUC_ANNOTATOR_ROOT", None)
    os.environ.pop("LUC_ANNOTATOR_PORT", None)
    map_ = os.path.join(os.path.expanduser("~"), "html-annotator-tests")
    os.makedirs(map_, exist_ok=True)
    slug = "zz-test-verstuur-mail-%d-%d" % (int(time.time()), os.getpid())
    bestand = os.path.join(map_, slug + ".html")
    with open(bestand, "w", encoding="utf-8") as f:
        f.write("<!doctype html><title>%s</title><p>testpagina</p>\n" % slug)
    log = os.path.join(root, "dummy-outbox.jsonl")
    proc, basis = start_bridge(root, poort)
    url = "%s/p/html-annotator-tests/%s.html" % (basis, slug)
    statepad = os.path.join(root, slug, "state.json")

    def approve(key, **v):
        p = {"page": url, "key": key, "channel": "mail", "account": VAN, "to": AAN, "cc": CC,
             "subject": ONDERWERP, "text": TEKST}
        p.update(v)
        code, _, raw = http("POST", basis + "/send-approve", p, {"Origin": basis})
        return code, json.loads(raw.decode("utf-8") or "{}")

    def entry(key):
        try:
            return json.load(open(statepad, encoding="utf-8"))["components"]["send"][key]
        except (OSError, ValueError, KeyError):
            return {}

    try:
        # --- validatie bij de klik ---------------------------------------------------
        n += check("M1 mail zonder account: 400", approve("m-x", account="")[0] == 400)
        n += check("M1 account geen e-mailadres: 400", approve("m-x", account="alex")[0] == 400)
        n += check("M1 Aan met naam i.p.v. adres: 400", approve("m-x", to="Alex Voorbeeld")[0] == 400)
        n += check("M1 Cc met ongeldig adres: 400", approve("m-x", cc="sam")[0] == 400)
        code, _, _ = http("POST", basis + "/send-approve", {"page": url, "key": "wa-x",
                          "channel": "whatsapp", "to": "31600000001", "text": "x", "cc": CC},
                          {"Origin": basis})
        n += check("M1 cc op een WhatsApp-kaart: 400", code == 400)
        n += check("M1 niets vastgelegd", entry("m-x") == {})

        # --- klik -> gate op send-mail ----------------------------------------------
        code, _ = approve("m-1", to="Alex@Example.com ", cc=CC)
        e = entry("m-1")
        n += check("M2 klik legt akkoord vast, adressen canoniek",
                   code == 200 and e.get("status") == "approved" and e.get("to") == AAN
                   and e.get("account") == VAN and e.get("cc") == CC)
        n += check("M3 gate exact: allow", gate(SEND, nieuw()) == "allow")
        n += check("M3 gate hoofdletters in adressen/account: allow",
                   gate(SEND, nieuw(account=VAN.upper(), to=("ALEX@example.com",))) == "allow")
        t = nieuw()
        t["body"]["Message"]["toRecipients"][0]["emailAddress"]["name"] = "Alex Voorbeeld"
        n += check("M3 gate met weergavenaam bij het adres: allow", gate(SEND, t) == "allow")
        n += check("M4 andere tekst: ask", gate(SEND, nieuw(text=TEKST + "!")) == "ask")
        n += check("M4 ander onderwerp: ask", gate(SEND, nieuw(subject="Planning")) == "ask")
        n += check("M4 extra Cc: ask", gate(SEND, nieuw(cc=(CC, "kim@example.com"))) == "ask")
        n += check("M4 Cc weg: ask", gate(SEND, nieuw(cc=())) == "ask")
        n += check("M4 zelfde adres in Bcc erbij: ask",
                   gate(SEND, nieuw(bccRecipients=lijst("x@example.com"))) == "ask")
        n += check("M4 Aan en Cc omgewisseld: ask", gate(SEND, nieuw(to=(CC,), cc=(AAN,))) == "ask")
        n += check("M4 andere afzender: ask", gate(SEND, nieuw(account="werk@example.com")) == "ask")
        n += check("M4 zonder account: ask", gate(SEND, nieuw(account=None)) == "ask")
        n += check("M5 bijlage: ask", gate(SEND, nieuw(attachments=[{"name": "a.pdf"}])) == "ask")
        n += check("M5 from-veld: ask", gate(SEND, nieuw(**{"from": lijst(VAN)[0]})) == "ask")
        n += check("M5 replyTo: ask", gate(SEND, nieuw(replyTo=lijst("x@example.com"))) == "ask")
        t = nieuw()
        t["body"]["Message"]["body"] = {"contentType": "text", "content": TEKST}
        n += check("M5 platte-tekstbody: ask", gate(SEND, t) == "ask")
        t = nieuw()
        t["body"]["Message"]["body"]["content"] += "<p>-- handtekening</p>"
        n += check("M5 HTML met extra blok: ask", gate(SEND, t) == "ask")
        t = nieuw()
        t["body"]["Message"]["body"]["content"] = t["body"]["Message"]["body"]["content"].replace("<p>", "<p style='x'>", 1)
        n += check("M5 HTML met attribuut: ask", gate(SEND, t) == "ask")
        n += check("M5 zelfde velden via ms365-example-server (account telt, server niet): allow",
                   gate("mcp__ms365-example__send-mail", nieuw()) == "allow")
        n += check("M5 willekeurige ms365-<naam>-server zonder akkoord: ask (geen vrije doorgang)",
                   gate("mcp__ms365-nieuw-2__send-mail", nieuw(text="niet goedgekeurd")) == "ask")
        n += check("M5 server buiten ms365[-naam] (underscore): geen oordeel",
                   hook("verstuur-gate-hook.py", {"tool_name": "mcp__ms365_x__send-mail",
                        "tool_input": nieuw()}) == {})
        n += check("M5 send-draft-message: geen oordeel (gewone vraag)",
                   hook("verstuur-gate-hook.py", {"tool_name": "mcp__ms365-thuis__send-draft-message",
                        "tool_input": {"messageId": "x"}}) == {})

        # --- wachter geeft de exacte aanroep, die door de gate komt -----------------
        w = subprocess.Popen([sys.executable, os.path.join(BIN, "wacht-op-verstuur.py"),
                              "--page", bestand, "--key", "m-w", "--timeout", "20",
                              "--bridge", basis], stdout=subprocess.PIPE, text=True)
        time.sleep(1.5)
        approve("m-w", text="wachtertekst\n\nGroet,\nLuc", cc="")
        out, _ = w.communicate(timeout=10)
        wj = json.loads(out)
        v = wj.get("vervolg") or {}
        n += check("M6 wachter: send-mail op ms365-thuis voor het voorbeeldaccount",
                   w.returncode == 0 and v.get("tool") == SEND)
        n += check("M6 wachter: akkoord toont afzender", (wj.get("akkoord") or {}).get("account") == VAN)
        n += check("M6 vervolg.arguments gaat door de gate", gate(v.get("tool"), v.get("arguments")) == "allow")
        n += check("M6 vervolg zonder lege ccRecipients",
                   "ccRecipients" not in v.get("arguments", {}).get("body", {}).get("Message", {}))

        # --- versturen + nastap + replay ---------------------------------------------
        rc, uit = dummy(SEND, nieuw(), log)
        n += check("M7 dummy exact: allow, verstuurd", rc == 0 and uit.get("gate") == "allow")
        n += check("M7 nastap: status sent", entry("m-1").get("status") == "sent")
        rc, uit = dummy(SEND, nieuw(), log)
        n += check("M7 tweede keer: ask, outbox houdt één mail", rc == 10 and len(regels(log)) == 1)

        # --- antwoord ----------------------------------------------------------------
        code, _ = approve("m-r", reply="AAMkAD-msg-1", subject="", cc="")
        n += check("M8 antwoord-akkoord vastgelegd", code == 200 and entry("m-r").get("reply") == "AAMkAD-msg-1")
        n += check("M8 reply exact: allow", gate(REPLY, antwoord()) == "allow")
        n += check("M8 reply op ander bericht: ask", gate(REPLY, antwoord(mid="AAMkAD-msg-2")) == "ask")
        n += check("M8 reply zonder expliciete Aan (T31): ask", gate(REPLY, antwoord(to=())) == "ask")
        n += check("M8 reply met extra Cc: ask", gate(REPLY, antwoord(cc=(CC,))) == "ask")
        n += check("M8 reply-akkoord geldt niet voor een nieuwe mail: ask",
                   gate(SEND, nieuw(subject="", cc=())) == "ask")
        t = antwoord()
        t["body"]["Message"]["body"] = {"contentType": "html", "content": html(TEKST)}
        n += check("M8 reply met Message.body: ask", gate(REPLY, t) == "ask")
        n += check("M8 reply-all: geen oordeel (gewone vraag)",
                   hook("verstuur-gate-hook.py", {"tool_name": "mcp__ms365-thuis__reply-all-mail-message",
                        "tool_input": antwoord()}) == {})
        wj2 = verstuur.vervolg(entry("m-r"))
        n += check("M8 vervolg voor antwoord = reply-mail-message en gaat door de gate",
                   wj2["tool"] == REPLY and gate(REPLY, wj2["arguments"]) == "allow")

        # --- onbekende afzender ------------------------------------------------------
        approve("m-u", account="iemand@example.org", text="onbekend")
        n += check("M9 vervolg bij onbekend account: geen aanroep, vraag de reviewer",
                   isinstance(verstuur.vervolg(entry("m-u")), str))

        # --- intrekken ----------------------------------------------------------------
        approve("m-2", text="tweede mail")
        http("POST", basis + "/send-revoke", {"page": url, "key": "m-2", "reason": "test"}, {"Origin": basis})
        n += check("M10 na intrekken: ask", gate(SEND, nieuw(text="tweede mail")) == "ask")

        # --- rommel in tool_input: nooit een crash, altijd ask ----------------------
        for naam, invoer in (("body null", {"account": VAN, "body": None}),
                             ("Message string", {"account": VAN, "body": {"Message": "x"}}),
                             ("ontvanger zonder emailAddress", {"account": VAN, "body": {"Message": {
                                 "subject": ONDERWERP, "body": {"contentType": "html", "content": html(TEKST)},
                                 "toRecipients": [{}]}}}),
                             ("onbekend topveld", {**nieuw(), "extra": 1})):
            n += check("M11 %s: ask" % naam, gate(SEND, copy.deepcopy(invoer)) == "ask")
    finally:
        stop(proc)
        os.remove(bestand)
        shutil.rmtree(root, ignore_errors=True)
    print("%s — %d gefaald" % ("GROEN" if n == 0 else "ROOD", n))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
