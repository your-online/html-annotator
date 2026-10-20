#!/usr/bin/env python3
"""B12 (stuk zonder bash), B31–B34: configbestand, pick-port, bind-adres en pagina-root.

Draait zonder browser en zonder de live poort 8791: elke bridge hier krijgt een eigen
poort, een tijdelijke config-, state- en annotatiemap. De "bezet"-takken van pick-port
worden getest met een eigen bezetter op een testreeks (HTML_ANNOTATOR_PORT_RANGE),
nooit door 8791 te bezetten of te stoppen. Platform: alle drie (CI-matrix).
"""

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import redirect_stderr

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL)

from html_annotator import config, service  # noqa: E402

ENV_NAMEN = ("HTML_ANNOTATOR_PORT", "LUC_ANNOTATOR_PORT", "HTML_ANNOTATOR_HOST",
             "HTML_ANNOTATOR_PAGES_ROOT", "HTML_ANNOTATOR_PORT_RANGE",
             "HTML_ANNOTATOR_ROOT", "LUC_ANNOTATOR_ROOT")


def check(naam, conditie, extra=""):
    if not conditie:
        print("FAIL  %s%s" % (naam, ("\n      " + extra) if extra else ""))
        return 1
    print("PASS  %s" % naam)
    return 0


def vrij(poort):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", poort))
        return True
    except OSError:
        return False
    finally:
        s.close()


def vrije_poort():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    return poort


def vrij_blok(n=2):
    """Begin van n aaneengesloten vrije poorten (geen garantie, wel goed genoeg).

    Buiten de ephemeral-reeks (macOS/Windows 49152+, Linux 32768+): daar kan de
    bronpoort van een eigen ping precies op p+1 landen en die poort even bezet houden."""
    import random
    for _ in range(50):
        p = random.randint(20000, 29990)
        if all(vrij(p + i) for i in range(n)):
            return p
    raise RuntimeError("geen blok van %d vrije poorten gevonden" % n)


class Bezetter:
    """Kale TCP-luisteraar die géén bridge is: accepteert en sluit meteen."""

    def __init__(self, poort):
        self.s = socket.socket()
        self.s.bind(("127.0.0.1", poort))
        self.s.listen(5)
        self.s.settimeout(0.2)
        self.stop = False
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def _loop(self):
        while not self.stop:
            try:
                c, _ = self.s.accept()
                c.close()
            except OSError:
                continue

    def sluit(self):
        self.stop = True
        self.t.join(2)
        self.s.close()


class Omgeving:
    """Tijdelijke config-, state-, annotatie- en paginamappen voor kindprocessen."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="ann-poort-")
        self.cfg = os.path.join(self.tmp, "cfg")
        self.state = os.path.join(self.tmp, "state")
        self.root = os.path.join(self.tmp, "annotations")
        for d in (self.cfg, self.state, self.root):
            os.makedirs(d)
        self.env = {k: v for k, v in os.environ.items() if k not in ENV_NAMEN}
        self.env.update({"XDG_CONFIG_HOME": self.cfg, "APPDATA": self.cfg,
                         "XDG_STATE_HOME": self.state, "LOCALAPPDATA": self.state,
                         "HTML_ANNOTATOR_ROOT": self.root, "PYTHONUTF8": "1",
                         "PYTHONPATH": SKILL + (os.pathsep + os.environ["PYTHONPATH"]
                                                if os.environ.get("PYTHONPATH") else "")})

    @property
    def config_pad(self):
        return os.path.join(self.cfg, "html-annotator", "config.json")

    def config(self):
        with open(self.config_pad, encoding="utf-8") as f:
            return json.load(f)

    def schrijf_config(self, data):
        os.makedirs(os.path.dirname(self.config_pad), exist_ok=True)
        with open(self.config_pad, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def cli(self, *args, extra=None, timeout=60):
        env = dict(self.env, **(extra or {}))
        r = subprocess.run([sys.executable, "-m", "html_annotator"] + list(args),
                           cwd=SKILL, env=env, capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, r.stdout, r.stderr

    def serve(self, poort, extra=None):
        env = dict(self.env, HTML_ANNOTATOR_PORT=str(poort), **(extra or {}))
        log = open(os.path.join(self.tmp, "serve-%d.log" % poort), "w+", encoding="utf-8")
        proc = subprocess.Popen([sys.executable, "-m", "html_annotator", "serve"],
                                cwd=SKILL, env=env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.time() + 30
        while time.time() < deadline:
            if ping(poort):
                return proc, log
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        log.seek(0)
        proc.kill()
        raise RuntimeError("bridge kwam niet op %d:\n%s" % (poort, log.read()))

    def opruimen(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def ping(poort):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/ping" % poort, timeout=1) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def http(method, url, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# --- B31: configbestand en voorrang ------------------------------------------

def config_checks():
    n = 0
    bewaard = {k: os.environ.get(k) for k in ENV_NAMEN + ("XDG_CONFIG_HOME", "APPDATA")}
    tmp = tempfile.mkdtemp(prefix="ann-cfg-")
    try:
        for k in ENV_NAMEN:
            os.environ.pop(k, None)
        os.environ["XDG_CONFIG_HOME"] = tmp
        os.environ["APPDATA"] = tmp
        pad = config.config_file()
        n += check("B31 configbestand onder XDG_CONFIG_HOME/APPDATA",
                   str(pad) == os.path.join(tmp, "html-annotator", "config.json"), str(pad))
        n += check("B31 zonder bestand en env: 8791, 127.0.0.1, home",
                   config.port() == 8791 and config.host() == "127.0.0.1"
                   and config.pages_root() == config.Path.home().resolve())

        paginas = tempfile.mkdtemp(prefix="ann-pag-")
        config.write_config({"port": 9101, "host": "0.0.0.0", "pages_root": paginas,
                             "root": "~/ann-uit-bestand", "eigen": "blijft"})
        n += check("B31 bestand zet port/host/pages_root",
                   config.port() == 9101 and config.host() == "0.0.0.0"
                   and config.pages_root() == config.Path(paginas).resolve())
        n += check("B31 bestand zet root",
                   config.root() == config.Path.home() / "ann-uit-bestand", str(config.root()))
        n += check("B31 base_url blijft 127.0.0.1 bij host 0.0.0.0",
                   config.base_url() == "http://127.0.0.1:9101", config.base_url())

        config.write_config({"port": 9102})
        data = json.load(open(str(pad), encoding="utf-8"))
        n += check("B31 write_config behoudt andere sleutels",
                   data.get("eigen") == "blijft" and data.get("host") == "0.0.0.0"
                   and data.get("port") == 9102, json.dumps(data))
        # De lockfile blijft bewust staan (weghalen is racy); een tmp-bestand niet.
        n += check("B31 write_config laat geen tmp achter",
                   set(os.listdir(os.path.dirname(str(pad)))) <= {"config.json", "config.json.lock"},
                   str(os.listdir(os.path.dirname(str(pad)))))

        os.environ["LUC_ANNOTATOR_PORT"] = "9103"
        n += check("B31 LUC_ANNOTATOR_PORT (alias) wint van het bestand", config.port() == 9103)
        os.environ["HTML_ANNOTATOR_PORT"] = "9104"
        os.environ["HTML_ANNOTATOR_HOST"] = "127.0.0.2"
        os.environ["HTML_ANNOTATOR_PAGES_ROOT"] = tmp
        os.environ["HTML_ANNOTATOR_ROOT"] = tmp
        n += check("B31 env wint van het bestand",
                   config.port() == 9104 and config.host() == "127.0.0.2"
                   and config.pages_root() == config.Path(tmp).resolve()
                   and config.root() == config.Path(tmp))
        for k in ("LUC_ANNOTATOR_PORT", "HTML_ANNOTATOR_PORT", "HTML_ANNOTATOR_HOST",
                  "HTML_ANNOTATOR_PAGES_ROOT", "HTML_ANNOTATOR_ROOT"):
            os.environ.pop(k)

        with open(str(pad), "w", encoding="utf-8") as f:
            f.write("{kapot")
        config._gewaarschuwd.clear()
        fout = io.StringIO()
        with redirect_stderr(fout):
            waarden = (config.port(), config.host(), config.pages_root())
        n += check("B31 kapot bestand: standaardwaarden, geen crash",
                   waarden == (8791, "127.0.0.1", config.Path.home().resolve()), str(waarden))
        n += check("B31 kapot bestand: waarschuwing op stderr",
                   "warning" in fout.getvalue() and "config.json" in fout.getvalue(),
                   fout.getvalue())
        shutil.rmtree(paginas, ignore_errors=True)
    finally:
        for k, v in bewaard.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    return n


# --- B32: pick-port -----------------------------------------------------------

def pick_port_checks():
    n = 0
    om = Omgeving()
    bezetters = []
    procs = []
    try:
        # Eerste poort van de reeks bezet door een vreemde: de tweede wint. De
        # geconfigureerde poort wijst naar een dode poort; zonder config zou het
        # de standaard 8791 zijn, en daar kan een live bridge draaien die blijft staan.
        p = vrij_blok(2)
        bezetters.append(Bezetter(p))
        om.schrijf_config({"pages_root": "~/ergens", "port": vrije_poort()})
        rc, uit, err = om.cli("pick-port", extra={"HTML_ANNOTATOR_PORT_RANGE": "%d-%d" % (p, p + 1)})
        n += check("B32 pick-port slaat een vreemd bezette poort over",
                   rc == 0 and om.config().get("port") == p + 1, uit + err)
        n += check("B32 pick-port print poort en base-url",
                   ("port: %d" % (p + 1)) in uit and ("http://127.0.0.1:%d" % (p + 1)) in uit, uit)
        n += check("B32 pick-port behoudt andere sleutels",
                   om.config().get("pages_root") == "~/ergens", json.dumps(om.config()))
        rc, uit, _ = om.cli("url", "--base")
        n += check("B32 url --base volgt het configbestand",
                   rc == 0 and uit.strip() == "http://127.0.0.1:%d" % (p + 1), uit)

        # Hele reeks bezet: de OS kiest.
        rc, uit, err = om.cli("pick-port", extra={"HTML_ANNOTATOR_PORT_RANGE": "%d-%d" % (p, p)})
        gekozen = om.config().get("port")
        n += check("B32 reeks vol: OS-poort", rc == 0 and isinstance(gekozen, int)
                   and gekozen != p and 1 <= gekozen <= 65535 and "OS" in uit, uit + err)

        # Onze eigen bridge op de eerste poort telt als goed.
        q = vrij_blok(2)
        proc, _ = om.serve(q)
        procs.append(proc)
        om.schrijf_config({"port": vrije_poort()})
        rc, uit, err = om.cli("pick-port", extra={"HTML_ANNOTATOR_PORT_RANGE": "%d-%d" % (q, q + 1)})
        n += check("B32 poort met onze bridge wordt gekozen",
                   rc == 0 and om.config().get("port") == q and "bridge" in uit, uit + err)
        # Geconfigureerde poort met onze bridge blijft staan, ook buiten de reeks.
        rc, uit, err = om.cli("pick-port", extra={"HTML_ANNOTATOR_PORT_RANGE": "%d-%d" % (p, p)})
        n += check("B32 draaiende bridge op de geconfigureerde poort blijft",
                   rc == 0 and om.config().get("port") == q, uit + err)

        # --port: valideren, en waarschuwen bij een vreemde bezetter.
        rc, uit, err = om.cli("pick-port", "--port", "70000")
        n += check("B32 --port 70000 geweigerd", rc != 0 and om.config().get("port") == q, err)
        rc, uit, err = om.cli("pick-port", "--port", str(p))
        n += check("B32 --port N op vreemde bezetter: geschreven met waarschuwing",
                   rc == 0 and om.config().get("port") == p and "warning" in err, err)

        # B12/E4: ensure op een vreemd bezette geconfigureerde poort.
        rc, uit, err = om.cli("ensure", "--timeout", "1")
        n += check("B12 ensure op vreemde bezetter: exit 1 met pick-port in de melding",
                   rc == 1 and "pick-port" in err and str(p) in err, "rc=%s %s %s" % (rc, uit, err))
        n += check("B12 ensure startte daar geen bridge", ping(p) is None)
        n += check("B12 ensure liet de bezetter leven", bezetters[0].t.is_alive())


        # ensure, url, status en stop volgen de geconfigureerde poort zonder env.
        f = vrije_poort()
        om.schrijf_config({"port": f})
        rc, uit, err = om.cli("ensure")
        info = ping(f) or {}
        n += check("B32 ensure start op de poort uit het configbestand",
                   rc == 0 and info.get("bridge") == "html-annotator", uit + err)
        rc2, uit2, _ = om.cli("ensure")
        n += check("B32 tweede ensure: already running", rc2 == 0 and "already" in uit2, uit2)
        pagina = os.path.join(os.path.expanduser("~"), "zz-poort-test.html")
        rc, uit, err = om.cli("url", pagina)
        n += check("B32 url volgt de poort",
                   rc == 0 and uit.strip() == "http://127.0.0.1:%d/p/zz-poort-test.html" % f,
                   uit + err)
        rc, uit, err = om.cli("stop")
        n += check("B32 stop neemt hem weer omlaag", rc == 0 and ping(f) is None, uit + err)
        # De bridge sloot net verbindingen: TIME_WAIT op zijn poort. Dat is geen
        # bezetting; stop gevolgd door ensure moet gewoon weer starten.
        rc, uit, err = om.cli("ensure")
        n += check("B12 ensure direct na stop (TIME_WAIT) start gewoon",
                   rc == 0 and (ping(f) or {}).get("bridge") == "html-annotator",
                   "rc=%s %s %s" % (rc, uit, err))
        om.cli("stop")
    finally:
        for b in bezetters:
            b.sluit()
        for proc in procs:
            stop(proc)
        om.cli("stop")
        om.opruimen()
    return n


# --- B33: bind-adres ----------------------------------------------------------

def host_checks():
    n = 0
    om = Omgeving()
    paginas = os.path.join(om.tmp, "paginas")
    os.makedirs(paginas)
    with open(os.path.join(paginas, "p.html"), "w", encoding="utf-8") as f:
        f.write("<p>host</p>")
    poort = vrije_poort()
    extra = {"HTML_ANNOTATOR_HOST": "0.0.0.0", "HTML_ANNOTATOR_PAGES_ROOT": paginas}
    proc = None
    try:
        proc, log = om.serve(poort, extra)
        n += check("B33 bridge start op 0.0.0.0, /ping via 127.0.0.1",
                   (ping(poort) or {}).get("bridge") == "html-annotator")
        time.sleep(0.2)
        log.seek(0)
        tekst = log.read()
        n += check("B33 waarschuwing in de log bij niet-loopback",
                   "WARNING" in tekst and "0.0.0.0" in tekst, tekst)
        rc, uit, _ = om.cli("url", "--base", extra=dict(extra, HTML_ANNOTATOR_PORT=str(poort)))
        n += check("B33 url --base blijft 127.0.0.1",
                   uit.strip() == "http://127.0.0.1:%d" % poort, uit)
        basis = "http://127.0.0.1:%d" % poort
        code, raw = http("GET", basis + "/p/p.html")
        n += check("B33 eigen /p/-pagina 200", code == 200 and b"host" in raw)
        eigen = {"Origin": basis}
        code, _ = http("POST", basis + "/state-save",
                       {"page": basis + "/p/p.html", "component": "checklist", "key": "k",
                        "value": {"checked": True}}, headers=eigen)
        n += check("B33 POST vanaf de eigen origin niet geweigerd", code == 200)
        code, raw = http("POST", basis + "/send-revoke", {"page": basis + "/p/p.html", "key": "x"},
                         headers=eigen)
        n += check("B33 page-route vanaf de eigen origin niet geweigerd",
                   b"alleen vanuit" not in raw, "%s %s" % (code, raw))
        code, _ = http("GET", basis + "/ping", headers={"Host": "evil.example:%d" % poort})
        n += check("B33 vreemde Host blijft 403", code == 403)
    finally:
        if proc:
            stop(proc)
        om.opruimen()
    return n


# --- B34: pagina-root ---------------------------------------------------------

def pages_root_checks():
    n = 0
    om = Omgeving()
    paginas = os.path.join(om.tmp, "paginas")
    buiten = os.path.join(om.tmp, "buiten")
    for d in (paginas, buiten, os.path.join(paginas, "sub"), os.path.join(paginas, ".verborgen")):
        os.makedirs(d)
    bestanden = {
        os.path.join(paginas, "binnen.html"): "<p>binnen</p>",
        os.path.join(paginas, "sub", "dieper.html"): "<p>dieper</p>",
        os.path.join(paginas, ".env"): "TOKEN=x",
        os.path.join(paginas, ".verborgen", "x.html"): "<p>verborgen</p>",
        os.path.join(paginas, "notities.txt"): "geheim",
        os.path.join(buiten, "buiten.html"): "<p>buiten</p>",
    }
    for pad, inhoud in bestanden.items():
        with open(pad, "w", encoding="utf-8") as f:
            f.write(inhoud)
    symlinks = True
    try:
        os.symlink(os.path.join(buiten, "buiten.html"), os.path.join(paginas, "naar-buiten.html"))
        os.symlink(os.path.join(paginas, ".verborgen", "x.html"),
                   os.path.join(paginas, "naar-dot.html"))
    except (OSError, NotImplementedError):
        symlinks = False  # Windows zonder Developer Mode
    poort = vrije_poort()
    extra = {"HTML_ANNOTATOR_PAGES_ROOT": paginas}
    proc = None
    try:
        proc, _ = om.serve(poort, extra)
        basis = "http://127.0.0.1:%d" % poort
        code, raw = http("GET", basis + "/p/binnen.html")
        n += check("B34 pagina binnen de root 200", code == 200 and b"binnen" in raw)
        code, raw = http("GET", basis + "/p/sub/dieper.html")
        n += check("B34 submap binnen de root 200", code == 200 and b"dieper" in raw)
        code, raw = http("GET", basis + "/p/../buiten/buiten.html")
        code2, raw2 = http("GET", basis + "/p/%2E%2E/buiten/buiten.html")
        n += check("B34 pagina buiten de root 403",
                   code == 403 and code2 == 403 and b"buiten</p>" not in raw + raw2,
                   "%s %s" % (code, code2))
        for pad in (".env", ".verborgen/x.html"):
            code, raw = http("GET", basis + "/p/" + pad)
            n += check("B34 %s (dot) geweigerd" % pad, code == 403 and b"TOKEN" not in raw
                       and b"verborgen</p>" not in raw)
        code, _ = http("GET", basis + "/p/notities.txt")
        n += check("B34 type buiten P_SOORTEN 403", code == 403)
        if symlinks:
            code, raw = http("GET", basis + "/p/naar-buiten.html")
            n += check("B34 symlink naar buiten de root geweigerd",
                       code == 403 and b"buiten</p>" not in raw)
            code, raw = http("GET", basis + "/p/naar-dot.html")
            n += check("B34 symlink naar een dot-map geweigerd",
                       code == 403 and b"verborgen</p>" not in raw)
        else:
            print("SKIP  B34 symlinks (geen rechten om ze te maken)")
        # Het snippet stuurt pageFile "~/<pad-na-/p/>"; de bridge moet de root gebruiken.
        code, raw = http("POST", basis + "/save", {
            "page": basis + "/p/binnen.html", "pageFile": "~/binnen.html",
            "annotation": {"id": "r1", "type": "text", "selectedText": "binnen", "comment": "c"}})
        antwoord = json.loads(raw or b"{}")
        rondes = [os.path.join(r, f) for r, _, fs in os.walk(om.root) for f in fs
                  if f == "annotations.json"]
        hash_ok = False
        if rondes:
            data = json.load(open(rondes[0], encoding="utf-8"))
            hash_ok = str(data.get("contentHash", "")).startswith("sha256:")
        n += check("B34 /save van een /p/-pagina vindt het bestand onder de root",
                   code == 200 and antwoord.get("ok") and hash_ok,
                   "%s %s %s" % (code, raw[:200], rondes))
        # B39: een file://-pagina met /p/ in het pad hoort bij zijn eigen bestand, niet
        # bij het gelijknamige bestand onder de pagina-root. Idem voor een /p/-URL van
        # een andere poort.
        pmap = os.path.join(om.tmp, "p")
        os.makedirs(pmap)
        for naam, map_ in (("zz-file-p.html", pmap), ("zz-file-p.html", paginas),
                           ("zz-andere-poort.html", pmap), ("zz-andere-poort.html", paginas)):
            with open(os.path.join(map_, naam), "w", encoding="utf-8") as fh:
                fh.write("<p>%s</p>" % map_)
        for naam, page in (("zz-file-p.html", "file://" + os.path.join(pmap, "zz-file-p.html")),
                           ("zz-andere-poort.html", "http://127.0.0.1:%d/p/zz-andere-poort.html"
                            % (poort + 1 if poort < 65535 else poort - 1))):
            eigen = os.path.join(pmap, naam)
            code, raw = http("POST", basis + "/save", {
                "page": page, "pageFile": eigen,
                "annotation": {"id": "f-" + naam, "type": "text", "selectedText": "p",
                               "comment": "c"}})
            antwoord = json.loads(raw or b"{}")
            try:
                gekoppeld = json.load(open(antwoord["jsonPath"], encoding="utf-8")).get("pageFile")
            except (KeyError, OSError, ValueError):
                gekoppeld = None
            n += check("B39 %s: gekoppeld aan het eigen bestand, niet aan de pagina-root"
                       % page.split(":")[0] + (" (file://)" if page.startswith("file") else " (andere poort)"),
                       code == 200 and gekoppeld is not None
                       and os.path.realpath(gekoppeld) == os.path.realpath(eigen),
                       "%s %s" % (code, gekoppeld))
        rc, uit, err = om.cli("url", os.path.join(paginas, "sub", "dieper.html"),
                              extra=dict(extra, HTML_ANNOTATOR_PORT=str(poort)))
        n += check("B34 url binnen de root: pad vanaf de root",
                   rc == 0 and uit.strip() == basis + "/p/sub/dieper.html", uit + err)
        rc, uit, err = om.cli("url", os.path.join(buiten, "buiten.html"), extra=extra)
        n += check("B34 url buiten de root: nette fout",
                   rc == 1 and "pages root" in err and "Traceback" not in err, uit + err)
        rc, uit, err = om.cli("url", os.path.join(paginas, ".env"), extra=extra)
        n += check("B34 url naar een dotfile: nette fout",
                   rc == 1 and "hidden" in err and "Traceback" not in err, uit + err)
    finally:
        if proc:
            stop(proc)
        om.opruimen()
    return n


# --- B35–B38: kapot configbestand, gelijktijdig schrijven en ensure, oude naam ------

class OudeBridge:
    """Antwoordt op /ping als een bridge van vóór de hernoeming ("luc-annotator")."""

    def __init__(self, poort):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"ok": True, "bridge": "luc-annotator", "version": 2}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", poort), H)
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def sluit(self):
        self.srv.shutdown()
        self.srv.server_close()


def lees_pid(om, poort):
    try:
        with open(os.path.join(om.state, "html-annotator", "bridge-%d.pid" % poort),
                  encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def robuustheid_checks():
    n = 0
    om = Omgeving()
    oud = None
    try:
        # B35: pick-port op een kapot configbestand overschrijft het niet.
        kapot = '{"mail_servers": {"owner@example.com": "ms365"}, kapot'
        os.makedirs(os.path.dirname(om.config_pad), exist_ok=True)
        with open(om.config_pad, "w", encoding="utf-8") as f:
            f.write(kapot)
        rc, uit, err = om.cli("pick-port", extra={"HTML_ANNOTATOR_PORT_RANGE": "%d-%d" % ((vrij_blok(1),) * 2)})
        with open(om.config_pad, encoding="utf-8") as f:
            na = f.read()
        n += check("B35 pick-port op kapot configbestand: exit != 0, bestand onaangeroerd",
                   rc != 0 and na == kapot, "rc=%s %s" % (rc, err))
        n += check("B35 melding noemt het bestand, de fout en repareren/verwijderen",
                   om.config_pad in err and "not valid JSON" in err and "remove" in err
                   and "Traceback" not in err, err)
        rc, uit, err = om.cli("pick-port", "--port", str(vrije_poort()))
        with open(om.config_pad, encoding="utf-8") as f:
            na = f.read()
        n += check("B35 ook pick-port --port overschrijft het kapotte bestand niet",
                   rc != 0 and na == kapot, err)
        os.remove(om.config_pad)

        # B36: 20 gelijktijdige schrijvers, elk een eigen sleutel: alles blijft.
        code = ("import sys; from html_annotator import config; "
                "config.write_config({'k%s' % sys.argv[1]: int(sys.argv[1])})")
        procs = [subprocess.Popen([sys.executable, "-c", code, str(i)], cwd=SKILL, env=om.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(20)]
        fouten = [p.communicate(timeout=60)[1] for p in procs]
        data = om.config()
        n += check("B36 20 gelijktijdige write_config: alle 20 sleutels aanwezig",
                   all(data.get("k%d" % i) == i for i in range(20)),
                   "%d/20 %s" % (sum(1 for i in range(20) if data.get("k%d" % i) == i),
                                 [f for f in fouten if f][:1]))

        # B37: drie ensures tegelijk op een vrije poort: één bridge, pid-bestand klopt.
        f = vrij_blok(1)
        om.schrijf_config({"port": f})
        procs = [subprocess.Popen([sys.executable, "-m", "html_annotator", "ensure"], cwd=SKILL,
                                  env=om.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for _ in range(3)]
        uitkomsten = [p.communicate(timeout=90) + (p.returncode,) for p in procs]
        info = ping(f) or {}
        gestart = sum(1 for o in uitkomsten if "started" in o[0])
        n += check("B37 drie gelijktijdige ensures: alle drie exit 0, precies één startte",
                   all(o[2] == 0 for o in uitkomsten) and gestart == 1, str(uitkomsten))
        pid = lees_pid(om, f)
        n += check("B37 pid-bestand = pid die luistert (/ping)",
                   pid is not None and pid == info.get("pid"), "%s vs %s" % (pid, info.get("pid")))
        rc, uit, err = om.cli("stop")
        time.sleep(0.3)
        n += check("B37 stop stopt de luisterende bridge echt",
                   rc == 0 and ping(f) is None and not service.pid_alive(info.get("pid")), uit + err)

        # B38: een draaiende bridge van vóór de hernoeming telt als de onze.
        g = vrij_blok(1)
        oud = OudeBridge(g)
        om.schrijf_config({"port": g})
        rc, uit, err = om.cli("ensure", "--timeout", "2")
        n += check("B38 ensure op een oude bridge (luc-annotator): already, geen fout",
                   rc == 0 and "already" in uit, "rc=%s %s %s" % (rc, uit, err))
        om.schrijf_config({"port": vrije_poort()})
        rc, uit, err = om.cli("pick-port", extra={"HTML_ANNOTATOR_PORT_RANGE": "%d-%d" % (g, g)})
        n += check("B38 pick-port kiest de poort van de oude bridge als 'bridge'",
                   rc == 0 and om.config().get("port") == g and "bridge" in uit, uit + err)
    finally:
        if oud:
            oud.sluit()
        om.cli("stop")
        om.opruimen()
    return n


def doorlopend_checks():
    """B43: continuous_select staat standaard aan; config-sleutel en env zetten hem."""
    n = 0
    bewaard = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "APPDATA",
                                               "HTML_ANNOTATOR_CONTINUOUS_SELECT")}
    tmp = tempfile.mkdtemp(prefix="ann-door-")
    try:
        os.environ.pop("HTML_ANNOTATOR_CONTINUOUS_SELECT", None)
        os.environ["XDG_CONFIG_HOME"] = tmp
        os.environ["APPDATA"] = tmp
        n += check("B43 continuous_select standaard aan", config.continuous_select() is True)
        config.write_config({"continuous_select": False})
        n += check("B43 config-sleutel false zet hem uit", config.continuous_select() is False)
        os.environ["HTML_ANNOTATOR_CONTINUOUS_SELECT"] = "1"
        n += check("B43 env wint van het configbestand", config.continuous_select() is True)
        os.environ["HTML_ANNOTATOR_CONTINUOUS_SELECT"] = "0"
        config.write_config({"continuous_select": True})
        n += check("B43 env 0 zet hem uit", config.continuous_select() is False)
    finally:
        for k, v in bewaard.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    return n


def main():
    n = 0
    n += config_checks()
    n += doorlopend_checks()
    n += pick_port_checks()
    n += host_checks()
    n += pages_root_checks()
    n += robuustheid_checks()
    print("GROEN — 0 gefaald" if n == 0 else "ROOD — %d gefaald" % n)
    return n


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
