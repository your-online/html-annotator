#!/usr/bin/env python3
"""Verstuur-knop (WhatsApp): bridge-endpoints, PreToolUse-gate, PostToolUse-nastap,
wachter en dummy-kanaal. Zonder browser en zonder de live poort 8791: eigen bridge op
een vrije poort met een tijdelijke annotatie-root. Er wordt niets echt verstuurd; het
dummy-kanaal schrijft naar een logbestand.

De klik zelf (confirm, inline-edit, intrekken bij typen) staat in case-18 (browser).
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

TESTS = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(TESTS)
sys.path.insert(0, TESTS)
sys.path.insert(0, SKILL)
from test_bridge_contract import check, http, start_bridge, vrije_poort  # noqa: E402

BIN = os.path.join(SKILL, "bin")
NR = "31600000001"
TEKST = "Hi Nard, kun je morgen om 10:00?\nGroet"


def stop(proc):
    """Alleen onze eigen bridge (eigen pid), nooit iets op de live poort."""
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def hook(naam, ev):
    r = subprocess.run([sys.executable, os.path.join(BIN, naam)], input=json.dumps(ev),
                       capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout).get("hookSpecificOutput", {}) if r.stdout.strip() else {}


def gate(to, text):
    return hook("verstuur-gate-hook.py", {"tool_name": "mcp__whatsapp__send_message",
                                          "tool_input": {"recipient": to, "message": text}}
                ).get("permissionDecision")


def dummy(to, text, log, faal=False):
    tf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tf.write(text)
    tf.close()
    args = [sys.executable, os.path.join(BIN, "dummy-verstuur.py"), "--to", to,
            "--text-file", tf.name, "--log", log] + (["--faal"] if faal else [])
    r = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else {"stderr": r.stderr})


def regels(log):
    return open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []


def main():
    n = 0
    root = tempfile.mkdtemp(prefix="ann-root-")
    poort = vrije_poort()
    os.environ["HTML_ANNOTATOR_ROOT"] = root   # hooks en dummy erven dit
    os.environ["HTML_ANNOTATOR_PORT"] = str(poort)
    os.environ.pop("LUC_ANNOTATOR_ROOT", None)
    os.environ.pop("LUC_ANNOTATOR_PORT", None)
    map_ = os.path.join(os.path.expanduser("~"), "html-annotator-tests")
    os.makedirs(map_, exist_ok=True)
    slug = "zz-test-verstuur-%d-%d" % (int(time.time()), os.getpid())
    bestand = os.path.join(map_, slug + ".html")
    with open(bestand, "w", encoding="utf-8") as f:
        f.write("<!doctype html><title>%s</title><p>testpagina</p>\n" % slug)
    log = os.path.join(root, "dummy-outbox.jsonl")

    proc, basis = start_bridge(root, poort)
    url = "%s/p/html-annotator-tests/%s.html" % (basis, slug)
    eigen = {"Origin": basis}
    statepad = os.path.join(root, slug, "state.json")

    def approve(key, text=TEKST, to=NR, channel="whatsapp", headers=eigen):
        code, _, raw = http("POST", basis + "/send-approve",
                            {"page": url, "key": key, "channel": channel, "to": to, "text": text},
                            headers)
        return code, json.loads(raw.decode("utf-8") or "{}")

    def entry(key):
        try:
            return json.load(open(statepad, encoding="utf-8"))["components"]["send"][key]
        except (OSError, ValueError, KeyError):
            return {}

    try:
        # --- vervalsen van buitenaf ------------------------------------------------
        code, _ = approve("wa-1", headers={"Origin": "https://evil.example"})
        n += check("V1 /send-approve met Origin van een website: 403", code == 403)
        code, _ = approve("wa-1", headers={})
        n += check("V1 /send-approve zonder Origin (lokaal proces/curl): 403", code == 403)
        code, _, _ = http("POST", basis + "/state-save", {"page": url, "component": "send",
                          "key": "wa-1", "value": {"status": "approved"}}, eigen)
        n += check("V1 /state-save met component send: geweigerd", code != 200)
        code, _, _ = http("POST", basis + "/send-done", {"page": url, "key": "wa-1"},
                          {"Origin": basis})
        n += check("V1 /send-done vanuit een browser: 403", code == 403)
        n += check("V1 geen van die routes heeft een akkoord achtergelaten", entry("wa-1") == {})
        n += check("V1 gate zonder akkoord: ask", gate(NR, TEKST) == "ask")

        # --- ontvangerformaat en kanaal ---------------------------------------------
        code, j = approve("wa-x", to="+31 6 00000001")
        n += check("V2 ontvanger met + en spaties geweigerd bij de klik", code == 400)
        code, _ = approve("wa-x", channel="mail", to="a@b.nl")
        n += check("V2 kanaal mail heeft nog geen knop: geweigerd", code == 400)
        code, _ = approve("wa-jid", to=NR + "@s.whatsapp.net", text="jid-variant")
        n += check("V2 JID als ontvanger toegestaan", code == 200)

        # --- klik -> gate -----------------------------------------------------------
        code, j = approve("wa-1")
        n += check("V3 klik legt akkoord vast", code == 200 and entry("wa-1").get("status") == "approved")
        n += check("V3 state.json kent de pagina (voor de nastap)",
                   json.load(open(statepad, encoding="utf-8")).get("pageFile") == bestand)
        n += check("V3 gate exact: allow", gate(NR, TEKST) == "allow")
        n += check("V3 gate tekst + '!': ask", gate(NR, TEKST + "!") == "ask")
        n += check("V3 gate andere ontvanger, zelfde tekst: ask", gate("31600000002", TEKST) == "ask")
        n += check("V3 gate zelfde nummer als JID (andere recipient-waarde): ask",
                   gate(NR + "@s.whatsapp.net", TEKST) == "ask")

        # --- wachter ----------------------------------------------------------------
        w = subprocess.Popen([sys.executable, os.path.join(BIN, "wacht-op-verstuur.py"),
                              "--page", bestand, "--key", "wa-w", "--timeout", "20",
                              "--bridge", basis], stdout=subprocess.PIPE, text=True)
        time.sleep(1.5)
        n += check("V4 wachter wacht zolang er geen klik is", w.poll() is None)
        approve("wa-w", text="wachtertekst")
        out, _ = w.communicate(timeout=10)
        wj = json.loads(out)
        n += check("V4 wachter stopt na de klik met exit 0", w.returncode == 0 and wj.get("ok"))
        n += check("V4 wachter geeft exact de tool-argumenten",
                   (wj.get("vervolg") or {}).get("arguments") == {"recipient": NR, "message": "wachtertekst"})

        # --- versturen via het dummy-kanaal + nastap -------------------------------
        rc, uit = dummy(NR, TEKST, log)
        n += check("V5 dummy-verzending exact: gate allow, verstuurd", rc == 0 and uit.get("gate") == "allow")
        e = entry("wa-1")
        n += check("V5 nastap verbruikt het akkoord (status sent, sentAt)",
                   e.get("status") == "sent" and bool(e.get("sentAt")))
        n += check("V5 via de bridge (/send-done)", "(bridge)" in (uit.get("nastap") or ""))
        n += check("V5 outbox heeft precies één bericht", len(regels(log)) == 1)

        rc, uit = dummy(NR, TEKST, log)
        n += check("V6 dubbel versturen: gate ask, niets verstuurd",
                   rc == 10 and uit.get("gate") == "ask" and len(regels(log)) == 1)
        code, _ = approve("wa-1")
        n += check("V6 dezelfde tekst opnieuw goedkeuren na verzending: geweigerd", code == 400)

        # --- intrekken --------------------------------------------------------------
        approve("wa-2", text="tweede bericht")
        code, _, _ = http("POST", basis + "/send-revoke", {"page": url, "key": "wa-2",
                          "reason": "test"}, eigen)
        n += check("V7 na intrekken: gate ask",
                   code == 200 and entry("wa-2").get("status") == "revoked" and gate(NR, "tweede bericht") == "ask")

        # --- tool meldt mislukking --------------------------------------------------
        approve("wa-3", text="derde bericht")
        rc, uit = dummy(NR, "derde bericht", log, faal=True)
        n += check("V8 success false: akkoord blijft approved",
                   rc == 0 and entry("wa-3").get("status") == "approved")
        n += check("V8 nastap zegt dat het mislukt is", "mislukt" in (uit.get("nastap") or ""))

        # --- nastap als de bridge niet draait ----------------------------------------
        stop(proc)
        rc, uit = dummy(NR, "derde bericht", log)
        n += check("V9 bridge weg: nastap verbruikt in-process",
                   rc == 0 and entry("wa-3").get("status") == "sent" and "(in-process)" in (uit.get("nastap") or ""))
        n += check("V9 daarna: gate ask", gate(NR, "derde bericht") == "ask")

        # --- andere tools: geen oordeel ---------------------------------------------
        r = subprocess.run([sys.executable, os.path.join(BIN, "verstuur-gate-hook.py")],
                           input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
                           capture_output=True, text=True)
        n += check("V10 gate zwijgt bij een andere tool", r.returncode == 0 and r.stdout.strip() == "")
    finally:
        stop(proc)
        os.remove(bestand)
        shutil.rmtree(root, ignore_errors=True)
    print("%s — %d gefaald" % ("GROEN" if n == 0 else "ROOD", n))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
