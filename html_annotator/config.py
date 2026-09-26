"""One place for host, port, annotation root, skill dir and state dir.

Environment overrides. ``HTML_ANNOTATOR_*`` is primary; the ``LUC_ANNOTATOR_*``
names are deprecated aliases that still work, so an existing install keeps
running:

    HTML_ANNOTATOR_PORT   port the bridge listens on (default 8791)
    HTML_ANNOTATOR_ROOT   where rounds are written (default ~/annotations)
    HTML_ANNOTATOR_CHROME browser used for screenshot crops

The default root is ``~/annotations``, except on a machine that already uses
the older ``annotaties`` folder on the Desktop and has no ``~/annotations``:
there the old location wins, so an upgrade does not orphan existing rounds.
"""

import os
import sys
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8791

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


def port():
    waarde = env("HTML_ANNOTATOR_PORT", "LUC_ANNOTATOR_PORT")
    try:
        return int(waarde) if waarde else DEFAULT_PORT
    except ValueError:
        return DEFAULT_PORT


def root():
    waarde = env("HTML_ANNOTATOR_ROOT", "LUC_ANNOTATOR_ROOT")
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


def legacy_pid_file():
    return state_dir() / "bridge.pid"


def log_file():
    return state_dir() / "bridge.log"


def base_url(poort=None):
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
