#!/usr/bin/env python3
"""B44/B45 zonder echte browser: eigenschappen van de live crop, getoetst op onze eigen code.

Beveiliging wordt getoetst als eigenschap, nooit met een werkende aanvalspayload: de
sanitiser haalt uit een snapshot-string scripts, on*-attributen, javascript:-URL's,
iframe/object/embed en <meta http-equiv> weg (inerte voorbeeldmarkup); het antwoord op
/snap/<token> draagt een CSP-header; een snapshot wordt nooit als file://-document of
met --allow-file-access-from-files gerenderd (argv en URL's van een nep-Chrome); een
snapshot van een andere origin dan de bridge zelf wordt niet live gerenderd (record).

De nep-Chrome legt vast wat hij krijgt (argv, de wrapper, wat /snap/ antwoordt) en schrijft
een geldige witte PNG op --window-size. Zo is ook te toetsen hoe /save zich gedraagt als de
crop faalt of traag is. run_chrome zelf draait tegen een nep-Chrome die niet uit zichzelf
stopt.

Elke bridge draait op een vrije poort met tijdelijke root, configmap en pagina-root; 8791
en de echte annotatierondes worden niet aangeraakt. Gestopt wordt via de eigen pid.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL)


def vrije_poort():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    return poort


# De module in dit proces importeren zonder iets van de echte gebruiker te lezen of te
# schrijven: root, configmap en pagina-root tijdelijk, eigen poort.
TMP = tempfile.mkdtemp(prefix="ann-livecrop-mod-")
os.environ.update(HTML_ANNOTATOR_PORT=str(vrije_poort()),
                  HTML_ANNOTATOR_ROOT=os.path.join(TMP, "root"),
                  HTML_ANNOTATOR_PAGES_ROOT=TMP, XDG_CONFIG_HOME=os.path.join(TMP, "cfg"),
                  APPDATA=os.path.join(TMP, "cfg"))
os.environ.pop("HTML_ANNOTATOR_HOST", None)
from html_annotator import bridge as mod  # noqa: E402

NEP_CHROME = r'''#!/usr/bin/env python3
import json, os, re, struct, sys, time, urllib.error, urllib.parse, urllib.request, zlib
d = os.environ["NEP_CHROME_DIR"]
try:
    modus = open(os.path.join(d, "modus")).read().strip()
except OSError:
    modus = "ok"
def png(w, h):
    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
    ruw = zlib.compress((b"\x00" + b"\xff\xff\xff" * w) * h, 1)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", ruw) + chunk(b"IEND", b""))
args = sys.argv[1:]
def arg(p):
    return next((a.split("=", 1)[1] for a in args if a.startswith(p)), None)
log = {"argv": args, "fetches": [], "wrapper": ""}
url = args[-1]
if url.startswith("file:"):
    try:
        bron = open(urllib.request.url2pathname(urllib.parse.urlparse(url).path), encoding="utf-8").read()
    except OSError:
        bron = ""
    log["wrapper"] = bron
    # Zoals Chrome: de iframes van de wrapper ophalen. Er wordt niets uitgevoerd.
    for src in re.findall(r'src="([^"]+)"', bron):
        src = src.replace("&amp;", "&")
        log["fetches"].append({"url": src})
        if not src.startswith("http"):
            continue
        try:
            with urllib.request.urlopen(src, timeout=5) as r:
                log["fetches"][-1].update(status=r.status, csp=r.headers.get("Content-Security-Policy"),
                                          body=r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            log["fetches"][-1].update(status=e.code)
with open(os.path.join(d, "log.jsonl"), "a") as f:
    f.write(json.dumps(log) + "\n")
if modus == "fail":
    sys.stderr.write("nep-fout\n")
    sys.exit(1)
if modus == "traag":
    time.sleep(3)
w, h = (int(x) for x in arg("--window-size=").split(","))
s = float(arg("--force-device-scale-factor=") or 1)
open(arg("--screenshot="), "wb").write(png(int(round(w * s)), int(round(h * s))))
'''

# Chrome die de screenshot schrijft maar niet stopt, met een kindproces in dezelfde boom.
HANGENDE_CHROME = r'''#!/usr/bin/env python3
import os, struct, subprocess, sys, time, zlib
d = os.environ["NEP_CHROME_DIR"]
args = sys.argv[1:]
def arg(p):
    return next((a.split("=", 1)[1] for a in args if a.startswith(p)), None)
def chunk(t, data):
    return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff" * 12) * 4, 1)) + chunk(b"IEND", b""))
profiel = arg("--user-data-dir=")
open(os.path.join(profiel, "in-gebruik"), "w").write("x")
kind = subprocess.Popen(["sleep", "300"])
open(os.path.join(d, "pids"), "w").write("%d %d %s" % (os.getpid(), kind.pid, profiel))
data = png if os.environ.get("NEP_PNG") != "half" else png[:30]
open(arg("--screenshot="), "wb").write(data)
if os.environ.get("NEP_EXIT"):
    kind.kill()
    sys.exit(0)
time.sleep(300)
'''


def check(naam, conditie, extra=""):
    if not conditie:
        print("FAIL  %s%s" % (naam, ("  (" + extra + ")") if extra else ""))
        return 1
    print("PASS  %s" % naam)
    return 0


def http(method, url, body=None, headers=None, timeout=30):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def schrijf_chrome(map_pad, bron):
    """Nep-Chrome als uitvoerbaar script; op Windows via een .cmd-launcher (geen shebang)."""
    pad = os.path.join(map_pad, "chrome")
    with open(pad, "w") as f:
        f.write(bron)
    os.chmod(pad, 0o755)
    if os.name == "nt":
        cmd = pad + ".cmd"
        with open(cmd, "w") as f:
            f.write('@"%s" "%s" %%*\r\n' % (sys.executable, pad))
        return cmd
    return pad


class Bridge:
    """Eigen bridge met nep-Chrome, tijdelijke root, configmap en pagina-root."""

    def __init__(self, zonder_pillow=False):
        self.tmp = tempfile.mkdtemp(prefix="ann-livecrop-")
        self.root = os.path.join(self.tmp, "root")
        self.pages = os.path.join(self.tmp, "pages")
        self.nep = os.path.join(self.tmp, "nep")
        for d in (self.root, self.pages, self.nep):
            os.makedirs(d)
        self.chrome = schrijf_chrome(self.nep, NEP_CHROME)
        self.poort = vrije_poort()
        self.basis = "http://127.0.0.1:%d" % self.poort
        env = os.environ.copy()
        env.update(HTML_ANNOTATOR_PORT=str(self.poort), HTML_ANNOTATOR_ROOT=self.root,
                   HTML_ANNOTATOR_PAGES_ROOT=self.pages, HTML_ANNOTATOR_CHROME=self.chrome,
                   NEP_CHROME_DIR=self.nep)
        env["XDG_CONFIG_HOME"] = env["APPDATA"] = os.path.join(self.tmp, "cfg")
        env.pop("HTML_ANNOTATOR_HOST", None)
        pad = [SKILL]
        if zonder_pillow:
            # Een PIL-pakket dat niet te importeren is: de bridge draait dan zonder Pillow.
            nopil = os.path.join(self.tmp, "nopil", "PIL")
            os.makedirs(nopil)
            with open(os.path.join(nopil, "__init__.py"), "w") as f:
                f.write("raise ImportError('geen Pillow in deze test')\n")
            pad.insert(0, os.path.dirname(nopil))
        env["PYTHONPATH"] = os.pathsep.join(pad)
        self.log = open(os.path.join(self.tmp, "bridge.log"), "w+")
        self.proc = subprocess.Popen([sys.executable, "-m", "html_annotator", "serve"], cwd=SKILL,
                                     env=env, stdout=self.log, stderr=subprocess.STDOUT)
        eind = time.time() + 30
        while time.time() < eind:
            try:
                if http("GET", self.basis + "/ping", timeout=1)[0] == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            self.stop()
            raise RuntimeError("bridge kwam niet omhoog")
        self.pagina = os.path.join(self.pages, "pagina.html")
        with open(self.pagina, "w", encoding="utf-8") as f:
            f.write("<!doctype html><title>pagina</title><body style='margin:0'><p>hallo</p></body>")
        self.page_url = self.basis + "/p/pagina.html"

    def modus(self, m):
        with open(os.path.join(self.nep, "modus"), "w") as f:
            f.write(m)

    def logregels(self):
        try:
            with open(os.path.join(self.nep, "log.jsonl")) as f:
                return [json.loads(r) for r in f if r.strip()]
        except OSError:
            return []

    def save(self, ann_id, comment, snapshot=None, page=None, origin="eigen", rect=None):
        """origin "eigen" = de /p/-pagina van deze bridge (zoals de snippet), None = geen header."""
        body = {"page": page or self.page_url, "slug": "pagina", "title": "pagina",
                "doc": {"w": 900, "h": 1200},
                "annotation": {"id": ann_id, "type": "region", "comment": comment,
                               "rect": rect or {"x": 20, "y": 20, "w": 200, "h": 100}}}
        if snapshot is not None:
            body["snapshot"] = snapshot
        headers = {}
        if origin is not None:
            headers["Origin"] = self.basis if origin == "eigen" else origin
        code, raw = http("POST", self.basis + "/save", body, headers=headers, timeout=60)
        j = json.loads(raw.decode("utf-8"))
        rec = None
        if j.get("ok"):
            with open(j["jsonPath"], encoding="utf-8") as f:
                rec = next((a for a in json.load(f)["annotations"] if a.get("id") == ann_id), None)
        return code, j, rec

    def crop_bytes(self, j, rec):
        if not rec or not rec.get("image"):
            return None
        p = os.path.join(os.path.dirname(j["jsonPath"]), rec["image"])
        if not os.path.isfile(p):
            return None
        with open(p, "rb") as f:
            return f.read()

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


def snap(html, **extra):
    s = {"html": html, "vw": 900, "vh": 600, "sx": 0, "sy": 0, "dpr": 1}
    s.update(extra)
    return s


# Inerte voorbeeldmarkup: elk onderdeel dat de sanitiser moet weghalen, zonder iets dat
# werkt als aanval (geen netwerk, geen bestanden, geen bestaande handlers).
INERT = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    "<meta http-equiv=\"refresh\" content=\"30\"><base href=\"/elders/\">"
    "<script>x=1</script><style>p::before{content:\"<\"}</style></head>"
    "<body onload=\"x()\" style=\"margin:0\">"
    "<img src=\"a.png\" onerror=\"x()\"><IMG SRC=\"b.png\" OnClick=\"x()\">"
    "<a href=\"javascript:x()\">a</a><a href=\" JaVa\tScRiPt:x()\">b</a>"
    "<iframe src=\"a.html\"></iframe><iframe srcdoc=\"x\"></iframe>"
    "<object data=\"a.bin\"><p>terugval</p></object><embed src=\"a.bin\">"
    "<noscript><p>n</p></noscript><!-- opmerking -->"
    "<form><input type=\"password\" value=\"abc\"><input type=\"text\" value=\"zichtbaar\"></form>"
    "<svg viewBox=\"0 0 10 10\"><rect width=\"10\" height=\"10\"></rect></svg>"
    "<p id=\"blijft\" style=\"color:red\">inhoud &amp; meer</p>"
    "<script>x=2</script></body></html>")


def sanitiser_checks():
    """1a/14d: eigenschappen van de sanitiser, als unit-test op de functie."""
    n = 0
    schoon = getattr(mod, "schoon_snapshot", None)
    uit = schoon(INERT) if schoon else ""
    laag = uit.lower()
    weg = ["<script", "onload", "onerror", "onclick", "javascript", "<iframe", "srcdoc",
           "<object", "<embed", "http-equiv", "<base", "<noscript", "opmerking", "x()"]
    n += check("1a sanitiser: script, on*, javascript:, iframe/object/embed, meta http-equiv, base weg",
               bool(uit) and not [w for w in weg if w in laag], repr([w for w in weg if w in laag]))
    n += check("1a sanitiser laat de inhoud staan (doctype, charset, stijl, tekst, svg, afbeelding)",
               uit.lower().startswith("<!doctype html>") and '<meta charset="utf-8">' in uit
               and 'id="blijft"' in uit and "color:red" in uit and "inhoud &amp; meer" in uit
               and 'src="a.png"' in uit and "<svg" in uit and 'value="zichtbaar"' in uit, uit[:400])
    stijl = re.search(r"<style>(.*?)</style>", uit, re.S)
    n += check("1a sanitiser: geen '<' meer binnen <style> (geen uitbraak uit de stylesheet)",
               bool(stijl) and "<" not in stijl.group(1), repr(stijl.group(1) if stijl else None))
    n += check("14d sanitiser maskeert wachtwoordvelden (zelfde lengte, geen echte tekens)",
               'value="xxx"' in uit and "abc" not in uit, uit[:400])
    return n


def bereid_checks():
    """1b/4/11: één functie bezit sanitiser, nonce en CSP; het herstel-script hoort in <body>."""
    n = 0
    bereid = getattr(mod, "bereid_snapshot", None)
    if not bereid:
        return check("11 bereid_snapshot(html, x, y, ...) -> (body, csp) bestaat", False)
    body, csp = bereid(INERT, 0, 0, base=None, port=mod.PORT)
    body = body.decode("utf-8") if isinstance(body, bytes) else body
    nonce = re.search(r"script-src 'nonce-([^']+)'", csp)
    n += check("1b CSP: default-src 'none', connect-src 'none', script-src alleen de nonce",
               "default-src 'none'" in csp and "connect-src 'none'" in csp and nonce
               and re.search(r"script-src 'nonce-[^' ]+'(;|$)", csp) is not None, csp)
    scripts = re.findall(r"<script\b[^>]*>", body, re.I)
    n += check("11 precies één script in de snapshot: het eigen, met de nonce uit de CSP",
               len(scripts) == 1 and nonce and ('nonce="%s"' % nonce.group(1)) in scripts[0],
               repr(scripts))
    b2, csp2 = bereid(INERT, 0, 0, base=None, port=mod.PORT)
    n += check("11 elke snapshot een eigen nonce", csp2 != csp)
    # 4: U+0130 wordt bij lower() twee tekens; </body> moet heel blijven.
    body, _ = bereid("<!doctype html><html><head></head><body><p>İİİİ</p></BODY></html>", 0, 0,
                     base=None, port=mod.PORT)
    body = body.decode("utf-8") if isinstance(body, bytes) else body
    eind = re.search(r"</body\s*>", body, re.I)
    i_script = body.find("<script")
    n += check("4 herstel-script staat binnen <body>, </body> blijft heel (U+0130)",
               eind is not None and 0 <= i_script < eind.start() and "İİİİ</p>" in body, body[-300:])
    body, _ = bereid("<html><head><title>t</title></head><body>x</body></html>", 0, 0,
                     base="http://127.0.0.1:%d/p/map/pagina.html" % mod.PORT, port=mod.PORT)
    body = body.decode("utf-8") if isinstance(body, bytes) else body
    n += check("1 eigen <base> naar de /p/-map van de pagina, in <head>",
               re.search(r"<head>\s*<base href=\"http://127\.0\.0\.1:%d/p/map/pagina\.html\">" % mod.PORT,
                         body) is not None, body[:200])
    return n


def snapshot_checks(b):
    """1b/1c/14c: wat /snap/<token> serveert, hoe het gerenderd wordt en hoe lang het bestaat."""
    n = 0
    b.modus("ok")
    voor = len(b.logregels())
    # Een file://-pagina: de snapshot moet tóch via http (/snap/) en zonder bestandstoegang.
    code, j, rec = b.save("inert-1", "inert", snap(INERT), page=Path(b.pagina).as_uri())
    regels = b.logregels()[voor:]
    snaps = [f for r in regels for f in r["fetches"] if "/snap/" in f["url"]]
    n += check("1c snapshot via http /snap/, nooit als file://-document",
               code == 200 and snaps and all(f["url"].startswith(b.basis + "/snap/") for f in snaps)
               and not any(f["url"].startswith("file:") for r in regels for f in r["fetches"]),
               json.dumps([f["url"] for r in regels for f in r["fetches"]])[:300])
    n += check("1c live crop zonder --allow-file-access-from-files",
               regels and all("--allow-file-access-from-files" not in r["argv"] for r in regels),
               json.dumps([r["argv"] for r in regels])[:300])
    n += check("B45 elke Chrome-run met --use-mock-keychain en --password-store=basic",
               regels and all("--use-mock-keychain" in r["argv"] and "--password-store=basic" in r["argv"]
                              for r in regels), json.dumps([r["argv"] for r in regels])[:300])
    f = snaps[0] if snaps else {}
    csp = f.get("csp") or ""
    body = f.get("body") or ""
    n += check("1b CSP-header op /snap/: default-src 'none', connect-src 'none', alleen nonce-script",
               "default-src 'none'" in csp and "connect-src 'none'" in csp
               and re.search(r"script-src 'nonce-[^' ]+'(;|$)", csp) is not None, csp)
    n += check("1a /snap/ serveert de gesaniteerde snapshot",
               body and "x()" not in body and "<iframe" not in body.lower() and 'id="blijft"' in body,
               body[:200])
    # 14c: het token bestond tijdens het renderen en is daarna weg.
    n += check("14c /snap/<token> antwoordde 200 tijdens het renderen",
               bool(snaps) and snaps[0].get("status") == 200)
    if snaps:
        code404, _ = http("GET", snaps[0]["url"])
        n += check("14c hetzelfde /snap/<token> geeft 404 na het renderen", code404 == 404,
                   str(code404))
    n += check("1 record: cropSource live", rec and rec.get("cropSource") == "live", repr(rec))
    return n


def viewport_checks(b):
    """5: de render-viewport is die van de reviewer, ook als de selectie eronder doorloopt."""
    n = 0
    b.modus("ok")
    voor = len(b.logregels())
    code, j, rec = b.save("vh-1", "vh", snap("<p>x</p>"), rect={"x": 100, "y": 550, "w": 200, "h": 100})
    regels = b.logregels()[voor:]
    wrapper = regels[-1]["wrapper"] if regels else ""
    hoogte = re.search(r"iframe\{[^}]*height:(\d+)px", wrapper)
    venster = next((a for a in (regels[-1]["argv"] if regels else []) if a.startswith("--window-size=")), "")
    # Met Pillow is het venster de viewport; zonder Pillow is het venster de crop (224x124).
    pillow = json.loads(http("GET", b.basis + "/ping")[1]).get("pillow")
    n += check("5 selectie onder de viewport: iframe blijft 600 hoog (viewport van de reviewer)",
               rec and rec.get("cropSource") == "live" and hoogte and int(hoogte.group(1)) == 600
               and venster == ("--window-size=900,600" if pillow else "--window-size=224,124"),
               "%s %s" % (hoogte and hoogte.group(0), venster))
    code, j, rec = b.save("vh-2", "te hoog", snap("<p>x</p>"), rect={"x": 100, "y": 50, "w": 200, "h": 700})
    n += check("5 selectie hoger dan de viewport: geen live crop, terugval op het bestand",
               rec and rec.get("cropSource") == "file" and rec.get("liveCropError"), repr(rec))
    return n


def origin_checks(b):
    """1d: alleen een /save van de eigen origin (/p/-pagina) wordt live gerenderd."""
    n = 0
    b.modus("ok")
    for naam, origin in (("null", "null"), ("andere-poort", "http://localhost:%d" % vrije_poort()),
                         ("geen", None)):
        voor = len(b.logregels())
        code, j, rec = b.save("o-" + naam, naam, snap("<p>x</p>"), origin=origin)
        snaps = [f for r in b.logregels()[voor:] for f in r["fetches"] if "/snap/" in f["url"]]
        n += check("1d Origin %s: snapshot niet gerenderd, crop uit het bestand" % naam,
                   code == 200 and not snaps and rec and rec.get("cropSource") == "file"
                   and "origin" in (rec.get("liveCropError") or ""), repr(rec))
    voor = len(b.logregels())
    code, j, rec = b.save("o-eigen", "eigen", snap("<p>x</p>"))
    snaps = [f for r in b.logregels()[voor:] for f in r["fetches"] if "/snap/" in f["url"]]
    n += check("1d eigen origin (/p/-pagina): snapshot wel gerenderd",
               code == 200 and snaps and rec and rec.get("cropSource") == "live", repr(rec))
    return n


def lock_checks(b):
    """9: de Chrome-crop houdt de globale LOCK niet vast; /session wacht er niet op."""
    n = 0
    b.modus("traag")
    klaar = {}

    def bewaar():
        klaar["save"] = b.save("traag-1", "traag", snap("<p>x</p>"))

    t = threading.Thread(target=bewaar)
    t.start()
    time.sleep(0.8)
    t0 = time.time()
    code, _ = http("POST", b.basis + "/session", {"page": b.page_url, "slug": "pagina"})
    duur = time.time() - t0
    t.join(30)
    b.modus("ok")
    n += check("9 /session tijdens een trage crop antwoordt direct (<1,5 s)",
               code == 200 and duur < 1.5, "%.2fs" % duur)
    rec = klaar.get("save", (0, {}, None))[2]
    n += check("9 de trage /save komt daarna gewoon binnen", rec and rec.get("cropSource") == "live",
               repr(rec))
    return n


def lees_rec(json_pad, ann_id):
    with open(json_pad, encoding="utf-8") as f:
        return next((a for a in json.load(f)["annotations"] if a.get("id") == ann_id), None) or {}


def sessie_ids(b):
    _, raw = http("POST", b.basis + "/session", {"page": b.page_url, "slug": "pagina"},
                  headers={"Origin": b.basis})
    return {a["id"]: a for a in json.loads(raw)["annotations"]}


def race_checks(b):
    """15/16: /delete en een bewerking terwijl de eerste /save nog op zijn crop wacht."""
    n = 0
    # 15: delete tijdens een trage live crop; de save mag de annotatie niet terugzetten.
    b.modus("traag")
    klaar = {}
    t = threading.Thread(target=lambda: klaar.setdefault("s", b.save("del-1", "x", snap("<p>x</p>"))))
    t.start()
    time.sleep(0.8)
    code, _ = http("POST", b.basis + "/delete", {"page": b.page_url, "slug": "pagina", "id": "del-1"},
                   headers={"Origin": b.basis})
    t.join(30)
    b.modus("ok")
    ids = sessie_ids(b)
    _, j, _rec = klaar.get("s", (0, {"jsonPath": os.path.join(b.root, "x")}, None))
    shots = os.path.join(os.path.dirname(j["jsonPath"]), "screenshots")
    with open(j["jsonPath"], encoding="utf-8") as f:
        bekend = {os.path.basename(a.get("image") or "") for a in json.load(f)["annotations"]}
    wees = [x for x in (os.listdir(shots) if os.path.isdir(shots) else [])
            if re.fullmatch(r"annotatie-\d+\.png", x) and x not in bekend]
    n += check("15 /delete tijdens een trage crop: annotatie blijft weg",
               code == 200 and "del-1" not in ids and j.get("ok"), repr(sorted(ids)))
    n += check("15 geen crop-bestand van de verwijderde annotatie", not wees, repr(wees))
    # 16: bewerking (zonder snapshot, zoals de snippet) terwijl de eerste save cropt.
    b.modus("traag")
    klaar = {}
    voor = len(b.logregels())
    t = threading.Thread(target=lambda: klaar.setdefault("s", b.save("ed-1", "oud", snap("<p>x</p>"))))
    t.start()
    time.sleep(0.5)
    b.modus("ok")
    _, j, _rec = b.save("ed-1", "nieuw", None)
    t.join(30)
    rec = lees_rec(j["jsonPath"], "ed-1")
    n += check("16 bewerking tijdens de crop: de laatste bewerking wint, live crop blijft",
               rec.get("comment") == "nieuw" and rec.get("cropSource") == "live" and rec.get("image"),
               repr(rec))
    n += check("16 de bewerking start geen tweede Chrome", len(b.logregels()) - voor == 1,
               str(len(b.logregels()) - voor))
    # 16b: twee saves met snapshot; de tweede is sneller klaar maar later binnen: die wint.
    b.modus("traag")
    klaar = {}
    t = threading.Thread(target=lambda: klaar.setdefault("s", b.save("ed-2", "oud", snap("<p>x</p>"))))
    t.start()
    time.sleep(0.5)
    b.modus("ok")
    _, j, _rec = b.save("ed-2", "nieuw", snap("<p>y</p>"))
    t.join(30)
    rec = lees_rec(j["jsonPath"], "ed-2")
    n += check("16 twee saves van hetzelfde id: de laatst binnengekomen wint",
               rec.get("comment") == "nieuw", repr(rec))
    return n


def behoud_checks():
    """2/3/14b: een mislukte nieuwe crop gooit nooit een goede bestaande crop weg (zonder Pillow:
    Chrome schrijft daar direct op het doelpad)."""
    n = 0
    b = Bridge(zonder_pillow=True)
    try:
        b.modus("ok")
        _, j, rec = b.save("live-1", "eerst", snap("<p>live</p>"))
        b1 = b.crop_bytes(j, rec)
        n += check("3 opzet: live crop zonder Pillow", rec and rec.get("cropSource") == "live" and b1,
                   repr(rec))
        b.modus("fail")
        _, j, rec = b.save("live-1", "comment bewerkt", snap("<p>andere staat</p>"))
        n += check("3 live crop mislukt op een bestaande annotatie: de goede crop blijft",
                   rec and rec.get("cropSource") == "live" and b1 and b.crop_bytes(j, rec) == b1
                   and rec.get("comment") == "comment bewerkt", repr(rec))

        b.modus("ok")
        _, j, rec = b.save("file-1", "eerst", None)
        b2 = b.crop_bytes(j, rec)
        n += check("3 opzet: file crop", rec and rec.get("cropSource") == "file" and b2, repr(rec))
        b.modus("fail")
        _, j, rec = b.save("file-1", "zonder snapshot", None)
        n += check("3 file crop mislukt zonder snapshot: bestaande crop blijft, geen imageError",
                   rec and rec.get("cropSource") == "file" and b2 and b.crop_bytes(j, rec) == b2
                   and "imageError" not in rec and rec.get("comment") == "zonder snapshot", repr(rec))
        _, j, rec = b.save("file-1", "opnieuw", {"html": 123})
        n += check("3/14b nieuwe crop mislukt (live en file): bestaande crop blijft, bestand intact",
                   rec and rec.get("image") and b2 and b.crop_bytes(j, rec) == b2
                   and rec.get("liveCropError"), repr(rec))

        b.modus("ok")
        _, j, rec = b.save("kapot-1", "kapot", {"html": 123})
        n += check("14b kapotte snapshot: cropSource file + liveCropError",
                   rec and rec.get("cropSource") == "file" and rec.get("image")
                   and rec.get("liveCropError"), repr(rec))
        _, j, rec = b.save("groot-1", "groot", snap("x" * (mod.SNAP_MAX + 1)))
        n += check("14b te grote snapshot: cropSource file + liveCropError 'te groot'",
                   rec and rec.get("cropSource") == "file" and rec.get("image")
                   and "te groot" in (rec.get("liveCropError") or ""), repr(rec)[:300])
        b.modus("ok")
        _, j, rec = b.save("groot-2", "eerst", snap("<p>x</p>"))
        b3 = b.crop_bytes(j, rec)
        _, j, rec = b.save("groot-2", "groot", snap("x" * (mod.SNAP_MAX + 1)))
        n += check("14b te grote snapshot op een bestaande annotatie: bestaande crop blijft",
                   b3 and rec and rec.get("cropSource") == "live" and b.crop_bytes(j, rec) == b3
                   and "te groot" in (rec.get("liveCropError") or ""), repr(rec)[:300])
        resten = [x for x in os.listdir(os.path.join(os.path.dirname(j["jsonPath"]), "screenshots"))
                  if not re.fullmatch(r"annotatie-\d+\.png", x)]
        n += check("3 geen halve of tijdelijke crops achtergebleven", not resten, repr(resten))
    finally:
        b.stop()
    return n


def snap_max_checks():
    """9: de snippet hanteert dezelfde grens als de bridge (SNAP_MAX)."""
    with open(os.path.join(SKILL, "references", "annotator-snippet.html"), encoding="utf-8") as f:
        bron = f.read()
    m = re.search(r"LA_SNAP_MAX\s*=\s*([0-9 *]+);", bron)
    waarde = eval(m.group(1)) if m else None  # alleen cijfers, spaties en *
    return check("9 LA_SNAP_MAX in de snippet == SNAP_MAX in de bridge",
                 waarde == mod.SNAP_MAX, "%r vs %r" % (waarde, mod.SNAP_MAX))


def url_checks():
    """10: één helper voor file-URL's, die ook met spaties en # in het pad klopt."""
    n = 0
    helper = getattr(mod, "bestand_url", None)
    pad = os.path.join(TMP, "map met spatie", "a#b.html")
    n += check("10 bestand_url(pad) == Path(pad).as_uri()",
               helper is not None and helper(pad) == Path(pad).resolve().as_uri(),
               helper(pad) if helper else "geen helper")
    with open(os.path.join(SKILL, "html_annotator", "bridge.py"), encoding="utf-8") as f:
        bron = f.read()
    n += check("10 nergens meer \"file://\" + quote(...) in de bridge",
               re.search(r"[\"']file://[\"']\s*\+", bron) is None)
    return n


def injectie_checks():
    """13: maak_crop_live krijgt Chrome, Pillow en poort als parameter."""
    n = 0
    nep = tempfile.mkdtemp(prefix="ann-inject-")
    os.environ["NEP_CHROME_DIR"] = nep
    srv = mod.BridgeServer(("127.0.0.1", 0), mod.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        chrome = schrijf_chrome(nep, NEP_CHROME)
        uit = os.path.join(nep, "uit.png")
        fout = None
        try:
            mod.maak_crop_live(snap("<p>x</p>"), "http://127.0.0.1:%d/p/a.html" % srv.server_address[1],
                               {"x": 10, "y": 10, "w": 50, "h": 40}, uit, chrome=chrome, pillow=False,
                               port=srv.server_address[1])
        except Exception as e:  # noqa: BLE001
            fout = e
        with open(os.path.join(nep, "log.jsonl")) as f:
            regels = [json.loads(r) for r in f if r.strip()]
        snaps = [x for r in regels for x in r["fetches"] if "/snap/" in x["url"]]
        n += check("13 maak_crop_live(chrome=, pillow=, port=) zonder globals te patchen",
                   fout is None and mod.png_compleet(uit) and snaps and snaps[0].get("status") == 200
                   and ":%d/snap/" % srv.server_address[1] in snaps[0]["url"], repr(fout))
    except Exception as e:  # noqa: BLE001
        n += check("13 maak_crop_live met geïnjecteerde Chrome", False, repr(e))
    finally:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(nep, ignore_errors=True)
    return n


def lees_pids(tmp):
    """pid van de nep-Chrome, pid van zijn kind, profielmap; (0, 0, "") als hij niet startte."""
    try:
        with open(os.path.join(tmp, "pids")) as f:
            ouder, kind, profiel = f.read().split(" ", 2)
        return int(ouder), int(kind), profiel
    except (OSError, ValueError):
        return 0, 0, ""


def leeft(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # zombie telt als dood: ps zegt dan Z
    st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(st.stdout.strip()) and not st.stdout.strip().startswith("Z")


def run_chrome_checks():
    """8/14e: Chrome die niet stopt wordt met zijn hele boom gestopt, het profiel is daarna
    weg; een halve PNG wordt nooit geaccepteerd."""
    n = 0
    if os.name == "nt":
        return check("14e run_chrome-boom (alleen posix)", True)
    tmp = tempfile.mkdtemp(prefix="ann-runchrome-")
    try:
        chrome = schrijf_chrome(tmp, HANGENDE_CHROME)
        os.environ["NEP_CHROME_DIR"] = tmp
        shot = os.path.join(tmp, "shot.png")
        t0 = time.time()
        fout = None
        try:
            mod.run_chrome(["--screenshot=" + shot, "--window-size=4,4", "about:blank"],
                           timeout=20, chrome=chrome)
        except Exception as e:  # noqa: BLE001
            fout = e
        duur = time.time() - t0
        ouder, kind, profiel = lees_pids(tmp)
        time.sleep(0.5)
        compleet = getattr(mod, "png_compleet", lambda p: False)
        n += check("14e Chrome die niet stopt: run_chrome komt terug met een geldige PNG",
                   fout is None and duur < 15 and compleet(shot), "%r %.1fs" % (fout, duur))
        n += check("14e de hele procesboom is gestopt (ook het kindproces)",
                   ouder and not leeft(ouder) and kind and not leeft(kind), "%s %s" % (ouder, kind))
        n += check("14e het wegwerpprofiel is weg", profiel and not os.path.exists(profiel), profiel)

        os.environ["NEP_PNG"] = "half"
        if os.path.exists(os.path.join(tmp, "pids")):
            os.remove(os.path.join(tmp, "pids"))
        fout = None
        try:
            mod.run_chrome(["--screenshot=" + shot, "--window-size=4,4", "about:blank"],
                           timeout=3, chrome=chrome)
        except Exception as e:  # noqa: BLE001
            fout = e
        ouder, kind, profiel = lees_pids(tmp)
        time.sleep(0.5)
        n += check("8 halve PNG wordt niet geaccepteerd (timeout-fout)", isinstance(fout, RuntimeError),
                   repr(fout))
        n += check("8 na de timeout: boom gestopt, profiel weg",
                   ouder and not leeft(ouder) and kind and not leeft(kind) and profiel
                   and not os.path.exists(profiel))

        # Chrome stopt netjes (exit 0) maar de PNG is afgebroken: niet accepteren.
        os.environ["NEP_EXIT"] = "1"
        fout = None
        try:
            mod.run_chrome(["--screenshot=" + shot, "--window-size=4,4", "about:blank"],
                           timeout=10, chrome=chrome)
        except Exception as e:  # noqa: BLE001
            fout = e
        n += check("8 exit 0 met een afgebroken PNG: fout, geen crop", isinstance(fout, RuntimeError),
                   repr(fout))
    finally:
        os.environ.pop("NEP_PNG", None)
        os.environ.pop("NEP_EXIT", None)
        # opruimen voor het geval de test rood is en de boom nog leeft
        for pid in lees_pids(tmp)[:2]:
            if pid:
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass
        shutil.rmtree(tmp, ignore_errors=True)
    return n


def main():
    n = 0
    try:
        n += sanitiser_checks()
        n += bereid_checks()
        n += url_checks()
        n += snap_max_checks()
        n += injectie_checks()
        n += run_chrome_checks()
        b = Bridge()
        try:
            n += snapshot_checks(b)
            n += viewport_checks(b)
            n += origin_checks(b)
            n += lock_checks(b)
            n += race_checks(b)
        finally:
            b.stop()
        n += behoud_checks()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("%s  test_live_crop: %d fout" % ("FAIL" if n else "PASS", n))
    return n


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
