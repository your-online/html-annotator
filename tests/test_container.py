#!/usr/bin/env python3
"""B41, B42: de bridge in een container zonder root en zonder init-proces."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL)

from html_annotator import bridge, config, service  # noqa: E402

NO_SANDBOX = "--no-sandbox"
ENV_NAMEN = ("HTML_ANNOTATOR_CHROME_NO_SANDBOX", "XDG_CONFIG_HOME", "APPDATA")


def check(naam, conditie, extra=""):
    if not conditie:
        print("FAIL  %s%s" % (naam, ("\n      " + extra) if extra else ""))
        return 1
    print("PASS  %s" % naam)
    return 0


def draait_als_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


class Configmap:
    def __enter__(self):
        self.bewaard = {k: os.environ.get(k) for k in ENV_NAMEN}
        self.tmp = tempfile.mkdtemp(prefix="ann-container-")
        for k in ENV_NAMEN:
            os.environ.pop(k, None)
        os.environ["XDG_CONFIG_HOME"] = self.tmp
        os.environ["APPDATA"] = self.tmp
        return self

    def schrijf(self, data):
        pad = config.config_file()
        pad.parent.mkdir(parents=True, exist_ok=True)
        pad.write_text(json.dumps(data), encoding="utf-8")

    def __exit__(self, *exc):
        for k, v in self.bewaard.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)


def chrome_vlag_checks():
    if draait_als_root():
        print("SKIP  B41 chrome_no_sandbox (als root komt de vlag er toch al bij)")
        return 0
    n = 0
    with Configmap():
        n += check("B41 zonder instelling: geen --no-sandbox",
                   NO_SANDBOX not in bridge.chrome_vlaggen())
    with Configmap() as cfg:
        cfg.schrijf({"chrome_no_sandbox": True})
        n += check("B41 configsleutel chrome_no_sandbox: --no-sandbox",
                   NO_SANDBOX in bridge.chrome_vlaggen())
    with Configmap() as cfg:
        cfg.schrijf({"chrome_no_sandbox": "yes"})
        n += check("B41 configsleutel die niet true is: geen --no-sandbox",
                   NO_SANDBOX not in bridge.chrome_vlaggen())
    with Configmap():
        os.environ["HTML_ANNOTATOR_CHROME_NO_SANDBOX"] = "1"
        n += check("B41 env HTML_ANNOTATOR_CHROME_NO_SANDBOX=1: --no-sandbox",
                   NO_SANDBOX in bridge.chrome_vlaggen())
    with Configmap() as cfg:
        cfg.schrijf({"chrome_no_sandbox": True})
        os.environ["HTML_ANNOTATOR_CHROME_NO_SANDBOX"] = "0"
        n += check("B41 env 0 wint van de configsleutel",
                   NO_SANDBOX not in bridge.chrome_vlaggen())
    return n


def niet_opgeruimd_kind():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    deadline = time.time() + 10
    while time.time() < deadline and not service.is_zombie(proc.pid):
        time.sleep(0.05)
    return proc


def zombie_checks():
    if not os.path.isdir("/proc"):
        print("SKIP  B42 zombie (geen /proc op dit platform)")
        return 0
    n = check("B42 pid_alive: een draaiend proces leeft", service.pid_alive(os.getpid()))
    proc = niet_opgeruimd_kind()
    try:
        n += check("B42 is_zombie: een gestopt, niet opgeruimd kind is een zombie",
                   service.is_zombie(proc.pid))
        n += check("B42 pid_alive: een zombie leeft niet", not service.pid_alive(proc.pid))
    finally:
        proc.wait()
    return n


def main():
    n = chrome_vlag_checks() + zombie_checks()
    print("GROEN — 0 gefaald" if n == 0 else "ROOD — %d gefaald" % n)
    return n


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
