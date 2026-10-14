"""Start, check and stop the bridge process — POSIX and Windows, no shell.

``ensure`` is the command every deliverable calls: it pings first and only
starts a detached process when nothing answers. Detaching matters because the
bridge has to outlive the agent session that started it.
"""

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import config


def ping(poort=None, timeout=2.0):
    """Answer of GET /ping as a dict, or None when nothing is listening."""
    url = config.base_url(poort) + "/ping"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


#: names a bridge of ours answers /ping with; "luc-annotator" is the name from before
#: the rename, so an older bridge that still runs counts as ours (not as a stranger)
BRIDGE_NAMES = ("html-annotator", "luc-annotator")


def is_bridge(info):
    """True when a /ping answer comes from this bridge (current or pre-rename name),
    not from another service."""
    return isinstance(info, dict) and info.get("bridge") in BRIDGE_NAMES


def poort_vrij(poort, host=None):
    """True when nothing listens on the port: binding works and nothing answers a
    connect on loopback.

    POSIX: with SO_REUSEADDR, like the bridge itself (HTTPServer), so a TIME_WAIT
    left by a just-stopped process does not count as taken; an active listener
    still makes the bind fail. Windows: without it, because there SO_REUSEADDR
    would let us bind on top of a listener. The connect check covers a listener on
    another address (0.0.0.0 vs 127.0.0.1)."""
    host = host or config.host()
    familie = socket.AF_INET6 if ":" in host else socket.AF_INET
    s = socket.socket(familie, socket.SOCK_STREAM)
    try:
        if os.name != "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, poort))
    except OSError:
        return False
    finally:
        s.close()
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.settimeout(0.3)
    try:
        return c.connect_ex((config.HOST, poort)) != 0
    except OSError:
        return True
    finally:
        c.close()


def os_poort(host=None):
    """A port the OS hands out (bind on 0), released again right away."""
    host = host or config.host()
    familie = socket.AF_INET6 if ":" in host else socket.AF_INET
    s = socket.socket(familie, socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        return s.getsockname()[1]
    finally:
        s.close()


def kies_poort(host=None):
    """(port, reason) for pick-port. A running bridge of ours on the configured port
    keeps it; otherwise the first port in the range that is ours or free wins; all
    taken: a port from the OS. reason in bridge/free/os."""
    host = host or config.host()
    huidig = config.port()
    if is_bridge(ping(huidig, timeout=0.5)):
        return huidig, "bridge"
    start, eind = config.port_range()
    for poort in range(start, eind + 1):
        if is_bridge(ping(poort, timeout=0.5)):
            return poort, "bridge"
        if poort_vrij(poort, host):
            return poort, "free"
    return os_poort(host), "os"


def pick_port(poort=None):
    """Choose (or take) a port and write it to the config file.
    Returns (exit code, message for stdout, warning for stderr or "")."""
    waarschuwing = []
    if poort is not None:
        if not config.geldige_poort(poort):
            return 2, "", "not a port: %s (use 1-65535)" % poort
        poort = int(poort)
        info = ping(poort, timeout=0.5)
        if not is_bridge(info) and not poort_vrij(poort):
            waarschuwing.append("port %d is in use by something that is not the bridge; "
                                "ensure will refuse it until it is free" % poort)
        reden = "set"
    else:
        poort, reden = kies_poort()
    try:
        pad = config.write_config({"port": poort})
    except config.ConfigError as e:
        return 2, "", ("%s. Not overwriting it: repair the file or remove it, then run "
                       "pick-port again." % e)
    if config.env("HTML_ANNOTATOR_PORT", "LUC_ANNOTATOR_PORT"):
        waarschuwing.append("HTML_ANNOTATOR_PORT is set in the environment and wins over "
                            "the config file for this shell")
    uitleg = {"bridge": "the bridge already answers there", "free": "free",
              "os": "%d-%d all taken, chosen by the OS" % config.port_range(),
              "set": "set by hand"}[reden]
    bericht = "port: %d (%s)\nbase-url: %s\nconfig: %s" % (
        poort, uitleg, config.base_url(poort), pad)
    return 0, bericht, "\n".join(waarschuwing)


def wait_for(poort=None, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        info = ping(poort, timeout=1.0)
        if info:
            return info
        time.sleep(0.2)
    return None


def read_pid(poort=None):
    for pad in (config.pid_file(poort), config.legacy_pid_file()):
        try:
            return int(pad.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
    return None


def _drop_pid(poort=None):
    for pad in (config.pid_file(poort), config.legacy_pid_file()):
        try:
            pad.unlink()
        except OSError:
            pass


def pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        uit = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid],
                             capture_output=True, text=True)
        return str(pid) in (uit.stdout or "")
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return not is_zombie(pid)


def is_zombie(pid):
    try:
        with open("/proc/%d/stat" % pid, encoding="ascii", errors="replace") as f:
            status = f.read().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return False
    return status == "Z"


def _spawn(poort=None):
    """Start the bridge detached from this process and this terminal."""
    state = config.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    log = config.log_file().open("ab")
    env = os.environ.copy()
    # `-m html_annotator` must resolve wherever the child is started from.
    pad = str(config.SKILL_DIR)
    env["PYTHONPATH"] = pad + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if poort:
        env["HTML_ANNOTATOR_PORT"] = str(poort)
    cmd = [config.python_exe(), "-m", "html_annotator", "serve"]
    kwargs = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL,
              "cwd": pad, "env": env, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                                   | getattr(subprocess, "DETACHED_PROCESS", 0x00000008))
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    return proc.pid


def ensure(poort=None, seconds=5.0):
    """Idempotent: returns (status, message). status in already/started/failed.

    Runs under a per-port lock in the state dir, so concurrent ensures never spawn two
    bridges: the first one starts it, the others wait and then find it running. The
    pid file is written only once the spawned process is the one answering /ping."""
    poort = poort or config.port()
    try:
        with config.file_lock(config.ensure_lock_file(poort), timeout=seconds + 25):
            return _ensure(poort, seconds)
    except TimeoutError as e:
        return "failed", str(e)


def _ensure(poort, seconds):
    info = ping(poort)
    if not is_bridge(info) and not poort_vrij(poort):
        # Bezet. Kan onze eigen bridge zijn die nog opstart (ensure van een oudere
        # versie zonder lock); anders weigeren: nooit stil uitwijken naar een andere poort.
        info = info or wait_for(poort, seconds)
        if not is_bridge(info):
            return "failed", ("port %d is taken by something that is not the bridge; "
                              "run `python -m html_annotator pick-port`" % poort)
    if is_bridge(info):
        return "already", "bridge already running on %s" % config.base_url(poort)
    pid = read_pid(poort)
    if pid and not pid_alive(pid):
        _drop_pid(poort)
    pid = _spawn(poort)
    info = wait_for(poort, seconds)
    if is_bridge(info):
        # /ping names the pid that actually listens. Only that one goes into the pid
        # file, so `stop` never points at a process that lost the bind and exited.
        luisteraar = info.get("pid") if isinstance(info.get("pid"), int) else None
        if luisteraar == pid or (luisteraar is None and pid_alive(pid)):
            config.pid_file(poort).write_text(str(pid), encoding="utf-8")
            return "started", "bridge started on %s (pid %d, log %s)" % (
                config.base_url(poort), pid, config.log_file())
        return "already", ("bridge already running on %s (pid %s; the one this ensure "
                           "started did not get the port)" % (config.base_url(poort), luisteraar))
    staart = ""
    try:
        staart = "\n".join(config.log_file().read_text(
            encoding="utf-8", errors="replace").splitlines()[-15:])
    except OSError:
        pass
    return "failed", "bridge did not answer within %ss. Last log lines:\n%s" % (seconds, staart)


def stop(poort=None):
    """Stop the bridge started by ensure. Returns (ok, message)."""
    poort = poort or config.port()
    pid = read_pid(poort)
    if not pid:
        if ping(poort):
            return False, ("something answers on %s but no pid file (%s) — "
                           "stop it yourself" % (config.base_url(poort), config.pid_file(poort)))
        return True, "no bridge to stop"
    if not pid_alive(pid):
        _drop_pid(poort)
        return True, "no running bridge (stale pid %d removed)" % pid
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(25):
        if not pid_alive(pid):
            break
        time.sleep(0.2)
    _drop_pid(poort)
    if pid_alive(pid):
        return False, "pid %d is still alive" % pid
    return True, "bridge stopped (pid %d)" % pid


def serve():
    from . import bridge
    bridge.main()
    return 0


def url_for(pad):
    """http://127.0.0.1:<port>/p/<path-from-pages-root> for a local file.

    Same rules as the /p/ route: inside config.pages_root(), no dotfile or
    dot-directory on the way (also not after following a symlink)."""
    doel = Path(os.path.expanduser(str(pad))).resolve()
    basis = config.pages_root()
    try:
        rel = doel.relative_to(basis)
    except ValueError:
        raise ValueError("path outside the pages root (%s), the bridge refuses it: %s"
                         % (basis, doel))
    if any(d.startswith(".") for d in rel.parts):
        raise ValueError("hidden path (a part starts with '.'), the bridge refuses it: %s"
                         % doel)
    return config.base_url() + "/p/" + "/".join(rel.parts)


def resolve(target, nrs=(), ids=(), poort=None, resolved=True):
    """POST /resolve for a slug or an annotations.json path."""
    payload = {"resolved": bool(resolved)}
    if nrs:
        payload["nrs"] = [int(n) for n in nrs]
    if ids:
        payload["ids"] = [str(i) for i in ids]
    tekst = str(target)
    if tekst.endswith(".json") or os.path.sep in tekst or "/" in tekst:
        payload["jsonPath"] = os.path.expanduser(tekst)
    else:
        payload["slug"] = tekst
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(config.base_url(poort) + "/resolve", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8") or "{}")
