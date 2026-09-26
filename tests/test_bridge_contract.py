#!/usr/bin/env python3
"""B1–B7: bridge-HTTP en ronde-gedrag, zonder de live poort 8791."""

import hashlib
import json
import os
import socket
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL)


def check(naam, conditie):
    if not conditie:
        print("FAIL  %s" % naam)
        return 1
    print("PASS  %s" % naam)
    return 0


def vrije_poort():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    return poort


def laad_bridge_mod():
    from html_annotator import bridge
    return bridge


def http(method, url, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            raw = r.read()
            return r.status, dict(r.headers), raw
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def start_bridge(root, poort):
    env = os.environ.copy()
    env["HTML_ANNOTATOR_PORT"] = str(poort)
    env["HTML_ANNOTATOR_ROOT"] = root
    env["PYTHONPATH"] = SKILL + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    log = open(os.path.join(root, "bridge-test.log"), "w+", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "html_annotator", "serve"],
        cwd=SKILL,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    basis = "http://127.0.0.1:%d" % poort
    # ruim: een koude CI-runner (macOS) heeft soms >5s nodig voor de eerste start
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            code, _, _ = http("GET", basis + "/ping")
            if code == 200:
                return proc, basis
        except OSError:
            time.sleep(0.05)
    # Diagnose: waar hangt het kind? SIGINT geeft een KeyboardInterrupt-traceback in de log.
    rc = proc.poll()
    try:
        if rc is None:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=5)
    except Exception:
        proc.kill()
    log.seek(0)
    raise RuntimeError("bridge kwam niet omhoog op poort %s (rc=%s, exe=%s); log:\n%s"
                       % (poort, rc, sys.executable, log.read()))


def p_route_checks(basis):
    """B2: /p/ serveert alleen pagina's en statische assets onder home, zonder CORS,
    en nooit dotfiles of dot-mappen (ook niet via een symlink)."""
    n = 0
    home = os.path.realpath(os.path.expanduser("~"))
    werk = tempfile.mkdtemp(prefix="html-annotator-ptest-", dir=home)
    rel = os.path.basename(werk)
    try:
        for naam, inhoud in (("pagina.html", "<p>ok</p>"), ("stijl.css", "p{}"),
                             ("notities.txt", "geheim"), ("sleutel", "geheim"),
                             (".env", "TOKEN=x")):
            with open(os.path.join(werk, naam), "w", encoding="utf-8") as f:
                f.write(inhoud)
        os.makedirs(os.path.join(werk, ".verborgen"))
        with open(os.path.join(werk, ".verborgen", "x.html"), "w", encoding="utf-8") as f:
            f.write("<p>verborgen</p>")
        os.symlink(os.path.join(werk, ".verborgen", "x.html"), os.path.join(werk, "link.html"))

        code, hdr, raw = http("GET", basis + "/p/%s/pagina.html" % rel)
        n += check("B2 /p/ html 200", code == 200 and raw == b"<p>ok</p>")
        n += check("B2 /p/ zonder CORS",
                   not any(k.lower().startswith("access-control-") for k in hdr))
        code, hdr, _ = http("GET", basis + "/p/%s/pagina.html" % rel,
                            headers={"Origin": "http://127.0.0.1:1"})
        n += check("B2 /p/ ook voor loopback-origin zonder CORS",
                   code == 200 and "Access-Control-Allow-Origin" not in hdr)
        code, _, _ = http("GET", basis + "/p/%s/stijl.css" % rel)
        n += check("B2 /p/ css 200", code == 200)
        for naam in ("notities.txt", "sleutel"):
            code, _, raw = http("GET", basis + "/p/%s/%s" % (rel, naam))
            n += check("B2 /p/ %s (type) is 403" % naam, code == 403 and b"geheim" not in raw)
        for pad in (".env", ".verborgen/x.html", "link.html", "%2Eenv"):
            code, _, raw = http("GET", basis + "/p/%s/%s" % (rel, pad))
            n += check("B2 /p/ %s (dot) is 403" % pad,
                       code == 403 and b"TOKEN" not in raw and b"verborgen</p>" not in raw)
        code, _, _ = http("GET", basis + "/p/.zshrc")
        n += check("B2 /p/.zshrc is 403", code == 403)
    finally:
        shutil.rmtree(werk, ignore_errors=True)
    return n


def allowlist_checks(basis, poort, root):
    """B30: alleen loopback-, file://- en null-origins; al het andere 403 vóór de handler."""
    n = 0
    for origin in ("http://127.0.0.1:%d" % poort, "http://localhost:8931",
                   "http://[::1]:5173", "null", "file://"):
        code, hdr, _ = http("POST", basis + "/state", {"slug": "zz-origin"},
                            headers={"Origin": origin})
        n += check("B30 %s mag POSTen" % origin,
                   code == 200 and hdr.get("Access-Control-Allow-Origin") == origin)
        code, hdr, _ = http("OPTIONS", basis + "/save", headers={"Origin": origin})
        n += check("B30 %s preflight 204" % origin,
                   code == 204 and hdr.get("Access-Control-Allow-Origin") == origin)
    code, hdr, _ = http("POST", basis + "/state", {"slug": "zz-origin"})
    n += check("B30 zonder Origin (curl/hook) mag",
               code == 200 and "Access-Control-Allow-Origin" not in hdr)

    for origin in ("https://evil.example", "http://127.0.0.1.evil.example",
                   "http://localhost.evil.example:8791", "chrome-extension://abc",
                   "data:", "https://127.0.0.1@evil.example"):
        code, hdr, _ = http("OPTIONS", basis + "/save", headers={"Origin": origin})
        n += check("B30 %s preflight 403" % origin,
                   code == 403 and "Access-Control-Allow-Origin" not in hdr)
    # De bijwerking telt, niet het antwoord: een no-cors-POST mag niets doen.
    for pad, body in (("/state-save", {"slug": "zz-evil", "key": "k", "value": 1}),
                      ("/save", {"slug": "zz-evil", "annotation": {"id": "e", "comment": "x"}}),
                      ("/sessie", {"prompt": "doe iets"})):
        code, hdr, _ = http("POST", basis + pad, body,
                            headers={"Origin": "https://evil.example"})
        n += check("B30 %s van vreemde origin 403" % pad,
                   code == 403 and "Access-Control-Allow-Origin" not in hdr)
    n += check("B30 vreemde origin schreef niets",
               not os.path.exists(os.path.join(root, "zz-evil")))
    # DNS-rebinding: een eigen naam die naar 127.0.0.1 wijst is same-origin met de bridge.
    code, _, _ = http("GET", basis + "/ping", headers={"Host": "evil.example:%d" % poort})
    n += check("B30 vreemde Host 403", code == 403)
    code, _, _ = http("GET", basis + "/ping", headers={"Host": "localhost:%d" % poort})
    n += check("B30 Host localhost mag", code == 200)
    return n


def main():
    n = 0
    root = tempfile.mkdtemp(prefix="ann-root-")
    pagina = os.path.join(tempfile.mkdtemp(prefix="ann-page-"), "demo.html")
    blok = "<!-- HTML-ANNOTATOR v3 -->\n<script>var x=1;</script>\n<!-- /HTML-ANNOTATOR -->"
    oud_blok = "<!-- LUC-ANNOTATOR v2 -->\n<script>var x=1;</script>\n<!-- /LUC-ANNOTATOR -->"
    with open(pagina, "w", encoding="utf-8") as f:
        f.write("<!doctype html><title>demo</title><p>inhoud</p>\n" + blok + "\n")

    mod = laad_bridge_mod()
    h1 = mod.content_hash(pagina, "abc")
    kaal = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    kaal.write("<!doctype html><title>demo</title><p>inhoud</p>\n\n")
    kaal.close()
    h2 = mod.content_hash(kaal.name, "abc")
    n += check("B5 hash negeert annotator-blok", h1 == h2 and h1.startswith("sha256:"))
    with open(pagina, "a", encoding="utf-8") as f:
        f.write("<p>gewijzigd</p>\n")
    h3 = mod.content_hash(pagina, "abc")
    n += check("B5 hash ziet echte wijziging", h1 != h3)
    # Een pagina met het oude LUC-ANNOTATOR-blok moet dezelfde hash houden.
    oud = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
    oud.write("<!doctype html><title>demo</title><p>inhoud</p>\n" + oud_blok + "\n")
    oud.close()
    n += check("B5 hash negeert ook een LUC-ANNOTATOR v2-blok",
               mod.content_hash(oud.name, "abc") == h1)

    poort = vrije_poort()
    proc, basis = start_bridge(root, poort)
    try:
        code, hdr, raw = http("GET", basis + "/ping")
        ping = json.loads(raw.decode("utf-8"))
        n += check("B1 ping 200", code == 200 and ping.get("ok") is True)
        n += check("B1 ping identiteit", ping.get("bridge") == "html-annotator")
        from html_annotator import __version__
        n += check("B1 ping release", ping.get("release") == __version__)
        n += check("B1 geen CORS *", hdr.get("Access-Control-Allow-Origin") != "*")

        code, _, _ = http("OPTIONS", basis + "/save")
        n += check("B1 OPTIONS 204", code == 204)

        n += allowlist_checks(basis, poort, root)

        code, _, raw = http("GET", basis + "/p/../etc/passwd")
        body = json.loads(raw.decode("utf-8"))
        n += check("B2 /p/ buiten home is 403", code == 403 and body.get("ok") is False)

        n += p_route_checks(basis)

        for pad in ("/session", "/save", "/delete", "/remove-all", "/resolve",
                    "/state", "/state-save", "/sessie"):
            code, _, raw = http("POST", basis + pad, {})
            n += check("B3 %s antwoordt" % pad, code in (200, 400))
        code, _, raw = http("POST", basis + "/sessie", {"url": "file:///etc/passwd"})
        n += check("B3 /sessie weigert file://", code == 400)

        slug = {"page": "http://127.0.0.1:%d/p/Desktop/demo.html" % poort,
                "pageFile": pagina, "slug": "demo", "title": "demo"}
        code, _, raw = http("POST", basis + "/save", {
            **slug,
            "annotation": {
                "id": "t-1", "type": "text", "selectedText": "inhoud",
                "comment": "zet \u27e6r1\u27e7 gelijk",
                "refs": [{"id": "r1", "selectedText": "andere"}],
                "locator": {"path": "p:nth-of-type(1)", "nth": 0},
            },
        })
        save1 = json.loads(raw.decode("utf-8"))
        n += check("B3 save ok", code == 200 and save1.get("ok") and save1.get("round") == 1)
        json_pad = save1["jsonPath"]
        n += check("B7 json bestaat", os.path.isfile(json_pad))
        n += check("B7 geen tmp-rest", not os.path.exists(json_pad + ".tmp"))

        atomair = os.path.join(tempfile.mkdtemp(prefix="ann-atom-"), "annotations.json")
        oud = {"annotations": [{"id": "keep-me"}]}
        mod.schrijf(atomair, oud)
        try:
            mod.schrijf(atomair, {"bad": object()})
            n += check("B7 dump-fout laat origineel staan", False)
        except TypeError:
            na = json.loads(open(atomair, encoding="utf-8").read())
            n += check("B7 dump-fout laat origineel staan", na == oud)
            n += check("B7 dump-fout laat geen tmp", not os.path.exists(atomair + ".tmp"))
        data = json.loads(open(json_pad, encoding="utf-8").read())
        rec = data["annotations"][0]
        n += check("B3 text-save houdt locator", rec.get("type") == "text" and rec.get("locator", {}).get("path"))
        n += check("B9 refs bewaard", rec.get("refs") and rec["refs"][0]["id"] == "r1")

        mod.ROOT = tempfile.mkdtemp(prefix="ann-crop-")
        def _crop_faalt(*_a, **_k):
            raise RuntimeError("crop kapot")
        mod.maak_crop = _crop_faalt
        crop_uit = mod.h_save({
            "page": "http://127.0.0.1/p/Desktop/crop-demo.html",
            "pageFile": pagina,
            "slug": "crop-demo",
            "title": "crop",
            "doc": {"w": 800, "h": 600},
            "annotation": {
                "id": "regio-1", "type": "region",
                "rect": {"x": 10, "y": 10, "w": 40, "h": 40},
                "comment": "regio blijft",
            },
        })
        regio = next(a for a in json.loads(open(crop_uit["jsonPath"], encoding="utf-8").read())["annotations"]
                     if a.get("id") == "regio-1")
        n += check("B6 crop-fout bewaart toch", crop_uit.get("ok") is True and regio.get("comment") == "regio blijft")
        n += check("B6 imageError gezet", bool(regio.get("imageError")) and regio.get("image") is None)

        code, _, raw = http("POST", basis + "/save", {
            **slug,
            "annotation": {"id": "t-2", "type": "text", "selectedText": "nog", "comment": "tweede"},
        })
        save2 = json.loads(raw.decode("utf-8"))
        n += check("B4 zelfde ronde", save2.get("round") == 1)
        http("POST", basis + "/delete", {"id": "t-1", **slug})
        over = json.loads(open(json_pad, encoding="utf-8").read())["annotations"]
        n += check("B3 delete houdt de rest", [a.get("id") for a in over] == ["t-2"])

        http("POST", basis + "/remove-all", slug)
        code, _, raw = http("POST", basis + "/save", {
            **slug,
            "annotation": {"id": "t-3", "type": "text", "selectedText": "nieuw", "comment": "ronde 2"},
        })
        save3 = json.loads(raw.decode("utf-8"))
        n += check("B4 nieuwe ronde na remove-all", save3.get("round") == 2)
        n += check("B4 ronde 1 blijft staan", os.path.isfile(json_pad))

        code, _, raw = http("POST", basis + "/resolve", {
            "jsonPath": save3["jsonPath"], "nrs": [1],
        })
        res = json.loads(raw.decode("utf-8"))
        n += check("B3 resolve", code == 200 and 1 in (res.get("resolved") or []))
        op_schijf = json.loads(open(save3["jsonPath"], encoding="utf-8").read())
        rec3 = op_schijf["annotations"][0]
        n += check("B3 resolve op schijf", rec3.get("resolved") is True and rec3.get("resolvedAt"))
        http("POST", basis + "/resolve", {
            "jsonPath": save3["jsonPath"], "nrs": [1], "resolved": False,
        })
        terug = json.loads(open(save3["jsonPath"], encoding="utf-8").read())["annotations"][0]
        n += check("B3 resolve terug te draaien", terug.get("resolved") is not True)

        # B26: component-state (LA-CHECKLIST) los van de rondes.
        code, _, raw = http("POST", basis + "/state", slug)
        leeg = json.loads(raw.decode("utf-8"))
        n += check("B26 state leeg leesbaar", code == 200 and leeg.get("ok")
                   and leeg.get("state", {}).get("components") == {})
        code, _, raw = http("POST", basis + "/state-save", {
            **slug, "component": "checklist", "key": "#74",
            "value": {"checked": True, "label": "demo-item"},
        })
        st1 = json.loads(raw.decode("utf-8"))
        n += check("B26 state-save ok", code == 200 and st1.get("ok")
                   and st1["entry"].get("checked") is True and st1["entry"].get("changedAt"))
        code, _, raw = http("POST", basis + "/state-save", {"component": "checklist", **slug})
        n += check("B26 state-save zonder key is 400", code == 400)
        http("POST", basis + "/state-save", {
            **slug, "component": "checklist", "key": "#74",
            "value": {"checked": False},
        })
        code, _, raw = http("POST", basis + "/state", slug)
        st2 = json.loads(raw.decode("utf-8"))
        entry = st2["state"]["components"]["checklist"]["#74"]
        n += check("B26 value gemergd, label blijft",
                   entry.get("checked") is False and entry.get("label") == "demo-item")
        n += check("B26 state.json op schijf, buiten ronde-NN",
                   os.path.isfile(st2["statePath"])
                   and os.path.basename(st2["statePath"]) == "state.json"
                   and "ronde-" not in st2["statePath"]
                   and os.path.dirname(st2["statePath"]) == os.path.dirname(os.path.dirname(json_pad)))
        n += check("B26 updatedAt gezet", bool(st2["state"].get("updatedAt")))
        http("POST", basis + "/remove-all", slug)
        _, _, raw = http("POST", basis + "/state", slug)
        st3 = json.loads(raw.decode("utf-8"))
        n += check("B26 remove-all raakt state niet",
                   "#74" in st3["state"]["components"].get("checklist", {}))
    finally:
        proc.kill()
        proc.wait(timeout=3)

    return n


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
