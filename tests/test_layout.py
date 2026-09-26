#!/usr/bin/env python3
"""A1–A11: de repo ziet eruit als een installeerbare skill, niet als een
persoonlijke scriptbak — de core draait zonder bash, en het pakket is te
installeren (A10) met één bron voor het snippet (A11).

De venv-case (pip install -e .) slaat zichzelf over zonder netwerk of zonder
venv-module; hij rapporteert dat dan als SKIP, niet als PASS.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from html_annotator import __version__ as VERSIE  # noqa: E402

# A1: ports. Snippet and handbook live in references/. Decisions in docs/.
ROOT_OK = {
    "README.md", "SKILL.md", "INSTALL.md", "CRITERIA.md", "CHANGELOG.md",
    "LICENSE", "pyproject.toml", ".gitignore",
}
ROOT_DIRS_OK = {"html_annotator", "bin", "references", "tests", "docs",
                "extras", ".git"}

# Agent-facing: what a stranger or installer reads. No tests/, no docs/
# history, no extras/.
AGENT_FILES = ("SKILL.md", "README.md", "INSTALL.md", "CRITERIA.md")
# Identifiers die gedrag dragen: contentHash en de hook herkennen naast
# HTML-ANNOTATOR ook nog het oude LUC-ANNOTATOR-blok, de oude page-global is de
# deprecated alias voor bestaande pagina's, env LUC_ANNOTATOR_* zijn deprecated
# aliassen en luc-annotaties is de localStorage-prefix. De lookaheads houden de
# oude naam zelf uit dit bestand.
ALLOW = re.compile(
    r"Luc(?=Annotator)|\(\?:HTML\|LUC\)-ANNOTATOR|/?LUC-ANNOTATOR|"
    r"luc(?=-annotaties)|LUC(?=_ANNOTATOR_)",
    re.I,
)
NAAM = re.compile(r"luc|luke", re.I)

RUNTIME = {"bridge.log", "bridge.pid", "bridge-hook.log", "__pycache__"}
DOT_OK = {".gitignore", ".git", ".github", ".claude"}
OUD_NAMEN = (
    "annotator_config.py", "annotator_record.py", "annotator_refs.py",
    "annotator-bridge.py", "ensure-bridge.sh", "hook-ensure-bridge.sh",
    "toon-annotaties.py", "pas-hunk-toe.py", "vind-todolijst.sh",
    "install.sh",
)
OUD_PAD = re.compile(
    r"(?:skills/html-annotator/|\$DOEL/|\./)"
    r"(?!bin/|html_annotator/)"
    r"(?:%s)" % "|".join(re.escape(n) for n in OUD_NAMEN)
)
BIN_REF = re.compile(r"\bbin/([A-Za-z0-9._-]+\.(?:py|sh))\b")
# A8: ports only. Handbook and WERKREGEL stay Dutch (docs/DECISIONS.md).
PORT_EN = ("SKILL.md", "README.md", "INSTALL.md", "CRITERIA.md")
NL = re.compile(
    r"\b(worden|wordt|bestand|draai|hieronder|wanneer|voordat|nadat|tenzij|volgende)\b",
    re.I,
)
# A11: het snippet heeft één bron op schijf. references/ is die bron; een
# tweede kopie in het pakket mag alleen bestaan als hij byte-identiek is
# (dan komt hij uit een build), anders kunnen ze uit elkaar lopen.
SNIPPETS = ("annotator-snippet.html", "checklist-snippet.html",
            "suggest-snippet.html")
# A9: geen bash in de core. tests/ mag bash houden voor de Playwright-suite.
BASH_VRIJ = ("html_annotator", "bin", "references", "docs", ".github")


def heeft_oud_pad(tekst):
    return bool(OUD_PAD.search(tekst))


def ontbrekende_bin_refs():
    miss = []
    for pad in agent_paden():
        tekst = open(pad, encoding="utf-8").read()
        for m in BIN_REF.finditer(tekst):
            naam = m.group(1)
            if not os.path.isfile(os.path.join(ROOT, "bin", naam)):
                miss.append("%s → bin/%s" % (os.path.relpath(pad, ROOT), naam))
    return miss


def nederlandse_poorten():
    hit = []
    for rel in PORT_EN:
        pad = os.path.join(ROOT, rel)
        if not os.path.isfile(pad):
            continue
        if NL.search(open(pad, encoding="utf-8").read()):
            hit.append(rel)
    return hit


def gitignore_rootnamen():
    namen = set()
    pad = os.path.join(ROOT, ".gitignore")
    if not os.path.isfile(pad):
        return namen
    for regel in open(pad, encoding="utf-8"):
        regel = regel.strip()
        if not regel or regel.startswith("#"):
            continue
        if "/" in regel.rstrip("/"):
            continue
        namen.add(regel.rstrip("/").replace("\\", ""))
    return namen - {"*.pyc"}


def agent_paden():
    paden = [os.path.join(ROOT, rel) for rel in AGENT_FILES]
    ref = os.path.join(ROOT, "references")
    if os.path.isdir(ref):
        for naam in sorted(os.listdir(ref)):
            if naam.endswith((".md", ".html")):
                paden.append(os.path.join(ref, naam))
    for sub in ("bin", "html_annotator"):
        d = os.path.join(ROOT, sub)
        if os.path.isdir(d):
            for naam in sorted(os.listdir(d)):
                if naam.endswith((".py", ".sh")):
                    paden.append(os.path.join(d, naam))
    return [p for p in paden if os.path.isfile(p)]


def shell_scripts_in_core():
    hit = []
    for sub in BASH_VRIJ:
        for dirpad, dirs, files in os.walk(os.path.join(ROOT, sub)):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules")]
            for f in files:
                if f.endswith((".sh", ".bash")):
                    hit.append(os.path.relpath(os.path.join(dirpad, f), ROOT))
    for f in os.listdir(ROOT):
        if f.endswith((".sh", ".bash")):
            hit.append(f)
    return sorted(hit)




def snippet_duplicaten():
    """Snippets die in references/ én in het pakket staan en verschillen."""
    uit = []
    pakket = os.path.join(ROOT, "html_annotator", "snippets")
    for naam in SNIPPETS:
        bron = os.path.join(ROOT, "references", naam)
        kopie = os.path.join(pakket, naam)
        if not os.path.isfile(kopie):
            continue
        if not os.path.isfile(bron):
            continue
        if open(bron, "rb").read() != open(kopie, "rb").read():
            uit.append(naam)
    return uit


def venv_install_check():
    """pip install -e . in een verse venv; (status, toelichting)."""
    tmp = tempfile.mkdtemp(prefix="ann-venv-")
    doel = os.path.join(tmp, "venv")
    maak = subprocess.run([sys.executable, "-m", "venv", doel],
                          capture_output=True, text=True)
    if maak.returncode != 0:
        return "skip", "venv aanmaken lukt niet (%s)" % (
            (maak.stderr or maak.stdout or "").strip().splitlines()[-1:] or "?")
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    py = os.path.join(doel, bin_dir, "python.exe" if os.name == "nt" else "python")
    uit = subprocess.run([py, "-m", "pip", "install", "-q", "-e", ROOT],
                         capture_output=True, text=True)
    if uit.returncode != 0:
        staart = (uit.stderr or uit.stdout or "").strip().splitlines()[-4:]
        if any(w in (uit.stderr or "").lower()
               for w in ("network", "temporary failure", "connection", "resolve",
                         "proxy", "retries exceeded")):
            return "skip", "geen netwerk voor de build-backend: %s" % " | ".join(staart)
        return "fail", "pip install -e . rc=%s: %s" % (uit.returncode, " | ".join(staart))
    exe = os.path.join(doel, bin_dir, "html-annotator.exe" if os.name == "nt" else "html-annotator")
    if not os.path.isfile(exe):
        return "fail", "console script html-annotator is niet ge\u00efnstalleerd"
    v = subprocess.run([exe, "--version"], capture_output=True, text=True)
    if v.returncode != 0 or VERSIE not in (v.stdout or ""):
        return "fail", "html-annotator --version gaf %r (rc=%s)" % (v.stdout, v.returncode)
    m = subprocess.run([py, "-m", "html_annotator", "--version"],
                       capture_output=True, text=True)
    if VERSIE not in (m.stdout or ""):
        return "fail", "python -m html_annotator --version gaf %r" % m.stdout
    return "ok", "html-annotator %s uit een verse venv" % VERSIE


def check(naam, conditie):
    if not conditie:
        print("FAIL  %s" % naam)
        return 1
    print("PASS  %s" % naam)
    return 0


def cli(home, *args):
    """Draait de CLI met een eigen HOME, zoals een verse install."""
    env = os.environ.copy()
    env["HOME"] = home
    env["USERPROFILE"] = home
    env["XDG_STATE_HOME"] = os.path.join(home, ".local", "state")
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "html_annotator", *args],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )


def main():
    n = 0
    namen = set(os.listdir(ROOT))
    runtime = set(RUNTIME)
    los = []
    for naam in sorted(namen):
        if naam.startswith("."):
            if naam not in DOT_OK:
                los.append(naam)
            continue
        if naam in runtime:
            continue
        pad = os.path.join(ROOT, naam)
        if os.path.isdir(pad):
            if naam not in ROOT_DIRS_OK:
                los.append(naam + "/")
            continue
        if naam not in ROOT_OK:
            los.append(naam)
    n += check("A1 root alleen poorten", los == [])
    if los:
        print("      nog in root: %s" % ", ".join(los))
    n += check("A1 snippet in references/",
               os.path.isfile(os.path.join(ROOT, "references", "annotator-snippet.html")))
    n += check("A1 .gitignore bestaat", os.path.isfile(os.path.join(ROOT, ".gitignore")))
    n += check("A1 gitignore-runtime is subset", gitignore_rootnamen() <= RUNTIME)
    n += check("A1 runtime staat in gitignore", RUNTIME <= gitignore_rootnamen())

    handbook = os.path.join(ROOT, "references", "agent-handbook.md")
    hb = open(handbook, encoding="utf-8").read() if os.path.isfile(handbook) else ""
    n += check("A2 geen memories/", "memories" not in namen)
    skill_md = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    n += check("A2 agent rules in references/",
               os.path.isfile(handbook) and "/p/" in hb and "bare" in hb)
    n += check("A2 SKILL period trigger", 'a bare "."' in skill_md)
    n += check("A3 extras/ heeft een README",
               os.path.isfile(os.path.join(ROOT, "extras", "README.md")))
    n += check("A3 scope-document", os.path.isfile(os.path.join(ROOT, "docs", "SCOPE.md")))
    n += check("A4 bin/ bestaat", os.path.isdir(os.path.join(ROOT, "bin")))
    n += check("A4 html_annotator-pakket",
               os.path.isfile(os.path.join(ROOT, "html_annotator", "__init__.py"))
               and os.path.isfile(os.path.join(ROOT, "html_annotator", "__main__.py")))

    for verplicht in (
        "bin/ensure-bridge.py",
        "bin/hook-ensure-bridge.py",
        "bin/annotator-bridge.py",
        "bin/toon-annotaties.py",
        "bin/pas-hunk-toe.py",
    ):
        n += check("A4 %s" % verplicht, os.path.isfile(os.path.join(ROOT, verplicht)))

    oud = []
    for pad in agent_paden():
        if heeft_oud_pad(open(pad, encoding="utf-8").read()):
            oud.append(os.path.relpath(pad, ROOT))
    n += check("A4 geen pre-bin paden", oud == [])
    if oud:
        print("      oude paden in: %s" % ", ".join(oud))
    bin_miss = ontbrekende_bin_refs()
    n += check("A4 bin-refs bestaan", bin_miss == [])
    if bin_miss:
        print("      ontbreekt: %s" % ", ".join(bin_miss))

    n += check("A5 geen hyphen-module in html_annotator/", not any(
        f.endswith(".py") and "-" in f
        for f in os.listdir(os.path.join(ROOT, "html_annotator"))
    ))
    n += check("A5 bin kebab-case", all(
        "_" not in f
        for f in os.listdir(os.path.join(ROOT, "bin"))
        if f.endswith((".py", ".sh"))
    ))

    luc = []
    for pad in agent_paden():
        tekst = ALLOW.sub("", open(pad, encoding="utf-8").read())
        if NAAM.search(tekst):
            luc.append(os.path.relpath(pad, ROOT))
    n += check("A6 geen persoonsnaam in agent-facing docs", luc == [])
    if luc:
        print("      nog een persoonsnaam in: %s" % ", ".join(luc))
    nl = nederlandse_poorten()
    n += check("A8 poorten Engels", nl == [])
    if nl:
        print("      Nederlands in: %s" % ", ".join(nl))

    sh = shell_scripts_in_core()
    n += check("A9 geen bash in de core", sh == [])
    if sh:
        print("      shell-scripts: %s" % ", ".join(sh))

    home = tempfile.mkdtemp(prefix="ann-inst-")
    uit = cli(home, "install-skill", "--copy")
    dest = os.path.join(home, ".claude", "skills", "html-annotator")
    n += check("A3 install zonder memories/",
               uit.returncode == 0 and not os.path.isdir(os.path.join(dest, "memories")))
    if uit.returncode != 0:
        print("      install-skill rc=%s\n%s\n%s" % (uit.returncode, uit.stdout, uit.stderr))
    n += check("A3 install zonder extras/", not os.path.isdir(os.path.join(dest, "extras")))
    runtime_mee = [naam for naam in RUNTIME if os.path.exists(os.path.join(dest, naam))]
    n += check("A1 install zonder runtime", runtime_mee == [])
    if runtime_mee:
        print("      meegekopieerd: %s" % ", ".join(runtime_mee))
    n += check("A4 install-skill is idempotent", cli(home, "install-skill", "--copy").returncode == 0)

    droog = cli(home, "install-hooks", "--print")
    n += check("A4 install-hooks --print schrijft niets",
               droog.returncode == 0
               and "hook-ensure-bridge.py" in droog.stdout
               and not os.path.isfile(os.path.join(home, ".claude", "settings.json")))
    uit2 = cli(home, "install-hooks")
    settings = os.path.join(home, ".claude", "settings.json")
    hook_ok = False
    events = set()
    if os.path.isfile(settings):
        d = json.load(open(settings, encoding="utf-8"))
        for event, groepen in (d.get("hooks") or {}).items():
            for g in groepen:
                for h in g.get("hooks") or []:
                    c = h.get("command") or ""
                    if "hook-ensure-bridge.py" in c:
                        events.add(event)
                        pad = c.split('" "')[-1].strip('"')
                        if os.path.isfile(pad):
                            hook_ok = True
    n += check("A4 install-hook bestaat", uit2.returncode == 0 and hook_ok)
    n += check("A4 beide hook-events",
               events == {"PostToolUse", "SessionStart"})
    # Nog een keer: geen dubbele registratie.
    cli(home, "install-hooks")
    d = json.load(open(settings, encoding="utf-8"))
    aantal = sum(
        1
        for groepen in (d.get("hooks") or {}).values()
        for g in groepen
        for h in (g.get("hooks") or [])
        if "hook-ensure-bridge.py" in (h.get("command") or "")
    )
    n += check("A4 install-hooks idempotent", aantal == 2)

    # ---- A10: het pakket is installeerbaar -----------------------------
    n += check("A10 pyproject bestaat", os.path.isfile(os.path.join(ROOT, "pyproject.toml")))
    pyproject = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
    n += check("A10 console script",
               'html-annotator = "html_annotator.cli:main"' in pyproject)
    n += check("A10 versie op \u00e9\u00e9n plek",
               '"1.0' not in pyproject and "html_annotator/__init__.py" in pyproject)
    n += check("A10 LICENSE bestaat", os.path.isfile(os.path.join(ROOT, "LICENSE")))
    n += check("A10 CHANGELOG noemt deze versie",
               VERSIE in open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read())
    v = cli(home, "--version")
    n += check("A10 --version werkt",
               v.returncode == 0 and VERSIE in v.stdout)

    # ---- A11: \u00e9\u00e9n bron voor het snippet ------------------------------
    dubbel = snippet_duplicaten()
    n += check("A11 geen afwijkende snippet-kopie", dubbel == [])
    if dubbel:
        print("      lopen uiteen: %s" % ", ".join(dubbel))
    import html_annotator.config as cfg
    n += check("A11 snippet vindbaar via het pakket",
               os.path.isfile(str(cfg.snippet_path())))

    status, toelichting = venv_install_check()
    if status == "skip":
        print("SKIP  A10 pip install -e . (%s)" % toelichting)
    else:
        n += check("A10 pip install -e . + console script", status == "ok")
        if status != "ok":
            print("      %s" % toelichting)
    return n


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
