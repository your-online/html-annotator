"""One place for host, port, annotation root, skill dir and state dir.

Precedence: environment > per-user config file > default. ``HTML_ANNOTATOR_*``
is primary; the ``LUC_ANNOTATOR_*`` names are deprecated aliases that still
work, so an existing install keeps running:

    HTML_ANNOTATOR_PORT        port the bridge listens on (default 8791)
    HTML_ANNOTATOR_HOST        address the bridge binds to (default 127.0.0.1)
    HTML_ANNOTATOR_PAGES_ROOT  directory /p/ serves pages from (default: home)
    HTML_ANNOTATOR_ROOT        where rounds are written (default ~/annotations)
    HTML_ANNOTATOR_CHROME      browser used for screenshot crops
    HTML_ANNOTATOR_CHROME_NO_SANDBOX  1: start that browser with --no-sandbox
    HTML_ANNOTATOR_CONTINUOUS_SELECT  0: region mode switches off after each Save

The config file (``config_file()``) holds the optional keys ``port``, ``host``,
``pages_root``, ``root``, ``chrome_no_sandbox`` and ``continuous_select``; ``python -m html_annotator pick-port``
writes ``port``.
``base_url()`` always uses 127.0.0.1, also when the bridge binds to 0.0.0.0:
the host is where the bridge listens, not the address a browser uses.

The default root is ``~/annotations``, except on a machine that already uses
the older ``annotaties`` folder on the Desktop and has no ``~/annotations``:
there the old location wins, so an upgrade does not orphan existing rounds.
"""

import contextlib
import json
import os
import sys
import time
from pathlib import Path

#: address in every URL the bridge hands out (base_url, /p/ links, own origins)
HOST = "127.0.0.1"
#: default bind address; see host()
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8791
#: the range ``pick-port`` tries before it asks the OS for a port
PORT_RANGE = (8791, 8890)

#: directory of the package itself (site-packages/html_annotator in an install)
PACKAGE_DIR = Path(__file__).resolve().parent
#: directory of the checkout / installed skill
SKILL_DIR = PACKAGE_DIR.parent


def is_checkout():
    """True when we run from a git checkout or an installed skill directory.

    False for a pip/pipx install, where ``SKILL_DIR`` is site-packages and the
    skill files travel inside the package instead (see pyproject.toml).
    """
    return (SKILL_DIR / "SKILL.md").is_file()


def snippets_dir():
    """Directory holding the pasteable snippets, checkout or installed."""
    if is_checkout():
        return SKILL_DIR / "references"
    return PACKAGE_DIR / "snippets"


def snippet_path(naam="annotator-snippet.html"):
    """Absolute path of a snippet that ships with this package."""
    return snippets_dir() / naam


def skill_source_dir():
    """Directory ``install-skill`` copies from: the checkout, or package data."""
    if is_checkout():
        return SKILL_DIR
    return PACKAGE_DIR / "_skill"


def env(*names, default=None):
    """First non-empty value of these environment variables."""
    for naam in names:
        waarde = os.environ.get(naam)
        if waarde:
            return waarde
    return default


def default_root():
    home = Path.home()
    nieuw = home / "annotations"
    oud = home / "Desktop" / "annotaties"
    if oud.is_dir() and not nieuw.is_dir():
        return oud
    return nieuw


def config_file():
    """Per-user config file. Windows: ``%APPDATA%\\html-annotator\\config.json``.
    Elsewhere: ``$XDG_CONFIG_HOME/html-annotator/config.json`` (``~/.config``)."""
    if os.name == "nt":
        basis = env("APPDATA", default=str(Path.home() / "AppData" / "Roaming"))
    else:
        basis = env("XDG_CONFIG_HOME", default=str(Path.home() / ".config"))
    return Path(basis) / "html-annotator" / "config.json"


_gewaarschuwd = set()


def _waarschuw(tekst):
    """Eén keer per proces op stderr; config wordt bij elke port()/host() gelezen."""
    if tekst not in _gewaarschuwd:
        _gewaarschuwd.add(tekst)
        print("html-annotator: warning: %s" % tekst, file=sys.stderr)


class ConfigError(ValueError):
    """The config file exists but cannot be read or parsed."""


def _lees_strikt(pad):
    """Contents of ``pad`` as a dict; missing: {}. Unreadable, invalid JSON or not an
    object: ConfigError with the reason."""
    try:
        tekst = pad.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise ConfigError("cannot read %s (%s)" % (pad, e))
    try:
        data = json.loads(tekst) if tekst.strip() else {}
    except ValueError as e:
        raise ConfigError("%s is not valid JSON (%s)" % (pad, e))
    if not isinstance(data, dict):
        raise ConfigError("%s is not a JSON object" % pad)
    return data


def read_config():
    """Contents of the config file as a dict. Missing: {}. Broken or unreadable:
    {} plus a warning on stderr — a bad file must never stop the bridge."""
    try:
        return _lees_strikt(config_file())
    except ConfigError as e:
        _waarschuw("%s; ignoring it" % e)
        return {}


@contextlib.contextmanager
def file_lock(pad, timeout=30.0):
    """Exclusive lock on ``pad`` (created if needed) across processes.

    POSIX: fcntl.flock. Windows: msvcrt.locking on the first byte. Polls until
    ``timeout`` seconds, then raises TimeoutError. The lock file itself stays."""
    pad = Path(pad)
    pad.parent.mkdir(parents=True, exist_ok=True)
    f = open(str(pad), "a+b")
    deadline = time.time() + timeout
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError("could not lock %s within %ss" % (pad, timeout))
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    finally:
        f.close()


def config_lock_file():
    pad = config_file()
    return pad.with_name(pad.name + ".lock")


def write_config(updates):
    """Merge ``updates`` into the config file and keep the other keys.

    Read-modify-write runs under a lock (``config.json.lock`` next to the file), so
    concurrent writers of different keys do not lose each other's keys; the write
    itself is atomic (tmp + replace). A file that exists but is broken is never
    overwritten: ConfigError, so the owner can repair or remove it. Returns the path."""
    pad = config_file()
    pad.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(config_lock_file()):
        data = _lees_strikt(pad)
        data.update(updates)
        tmp = pad.with_name(pad.name + ".%d.tmp" % os.getpid())
        try:
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(str(tmp), str(pad))
        finally:
            if tmp.exists():
                tmp.unlink()
    return pad


def geldige_poort(waarde):
    """int in 1–65535, or None."""
    try:
        poort = int(waarde)
    except (TypeError, ValueError):
        return None
    return poort if 1 <= poort <= 65535 else None


def port():
    """Env (HTML_ANNOTATOR_PORT, LUC_ANNOTATOR_PORT) > config file > 8791."""
    waarde = env("HTML_ANNOTATOR_PORT", "LUC_ANNOTATOR_PORT")
    if waarde:
        poort = geldige_poort(waarde)
        if poort:
            return poort
        _waarschuw("HTML_ANNOTATOR_PORT=%r is not a port; ignoring it" % waarde)
    waarde = read_config().get("port")
    if waarde is not None:
        poort = geldige_poort(waarde)
        if poort:
            return poort
        _waarschuw("port %r in %s is not a port; ignoring it" % (waarde, config_file()))
    return DEFAULT_PORT


def host():
    """Bind address of the bridge: env HTML_ANNOTATOR_HOST > config file > 127.0.0.1.
    Only where the bridge listens; URLs keep using ``HOST``."""
    waarde = env("HTML_ANNOTATOR_HOST")
    if waarde:
        return waarde
    waarde = read_config().get("host")
    if isinstance(waarde, str) and waarde.strip():
        return waarde.strip()
    return DEFAULT_HOST


def chrome_no_sandbox():
    waarde = env("HTML_ANNOTATOR_CHROME_NO_SANDBOX")
    if waarde:
        return waarde.strip().lower() in ("1", "true", "yes")
    return read_config().get("chrome_no_sandbox") is True


def continuous_select_from_env():
    """True when HTML_ANNOTATOR_CONTINUOUS_SELECT is set: the config file then has no say."""
    return bool(env("HTML_ANNOTATOR_CONTINUOUS_SELECT"))


def continuous_select():
    """Region mode stays on after Save, so the next region is one drag away.
    Env HTML_ANNOTATOR_CONTINUOUS_SELECT > config file ``continuous_select`` > on."""
    waarde = env("HTML_ANNOTATOR_CONTINUOUS_SELECT")
    if waarde:
        return waarde.strip().lower() not in ("0", "false", "no", "off")
    return read_config().get("continuous_select") is not False


def is_loopback(adres):
    naam = (adres or "").strip().strip("[]").lower()
    return naam in ("localhost", "::1") or naam.startswith("127.")


def pages_root():
    """Directory ``/p/`` serves from and ``url`` maps against: env
    HTML_ANNOTATOR_PAGES_ROOT > config file ``pages_root`` > home. The one source
    of truth for both."""
    waarde = env("HTML_ANNOTATOR_PAGES_ROOT")
    if not waarde:
        uit_bestand = read_config().get("pages_root")
        waarde = uit_bestand if isinstance(uit_bestand, str) and uit_bestand.strip() else None
    if not waarde:
        return Path.home().resolve()
    return Path(os.path.expanduser(waarde)).resolve()


def port_range():
    """Range for pick-port. ``HTML_ANNOTATOR_PORT_RANGE="start-end"`` is a test hook,
    not a user setting: the suite uses it to test the "taken" branch without ever
    touching a live bridge on 8791."""
    waarde = env("HTML_ANNOTATOR_PORT_RANGE")
    if waarde:
        try:
            start, eind = (geldige_poort(x) for x in waarde.split("-", 1))
            if start and eind and start <= eind:
                return start, eind
        except ValueError:
            pass
        _waarschuw("HTML_ANNOTATOR_PORT_RANGE=%r is not start-end; using %d-%d"
                   % ((waarde,) + PORT_RANGE))
    return PORT_RANGE


def root():
    waarde = env("HTML_ANNOTATOR_ROOT", "LUC_ANNOTATOR_ROOT")
    if not waarde:
        uit_bestand = read_config().get("root")
        waarde = uit_bestand if isinstance(uit_bestand, str) and uit_bestand.strip() else None
    return Path(os.path.expanduser(waarde)) if waarde else default_root()


def state_dir():
    """Per-user directory for pid file and log — never inside the checkout.

    Windows: ``%LOCALAPPDATA%``. Elsewhere: ``$XDG_STATE_HOME`` or
    ``~/.local/state``.
    """
    if os.name == "nt":
        basis = env("LOCALAPPDATA", default=str(Path.home() / "AppData" / "Local"))
    else:
        basis = env("XDG_STATE_HOME", default=str(Path.home() / ".local" / "state"))
    return Path(basis) / "html-annotator"


def pid_file(poort=None):
    """One pid file per port, so a test bridge on another port never gets stopped by
    accident. The pre-1.0 single ``bridge.pid`` is still read as a fallback."""
    return state_dir() / ("bridge-%d.pid" % (poort or port()))


def ensure_lock_file(poort=None):
    """Lock that makes ``ensure`` on one port run one at a time (see service.ensure)."""
    return state_dir() / ("ensure-%d.lock" % (poort or port()))


def legacy_pid_file():
    return state_dir() / "bridge.pid"


def log_file():
    return state_dir() / "bridge.log"


def base_url(poort=None):
    """Always 127.0.0.1, whatever host() binds to (0.0.0.0 is not an address)."""
    return "http://%s:%d" % (HOST, poort or port())


def skills_dir():
    return Path.home() / ".claude" / "skills"


def settings_file():
    return Path.home() / ".claude" / "settings.json"


def python_exe():
    return sys.executable or "python3"


# Backwards compatible module-level values. Modules that need a live value
# (tests spawn processes with different env) call the functions instead.
PORT = port()
ROOT = str(root())
