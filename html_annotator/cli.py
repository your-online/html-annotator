"""`python -m html_annotator <command>` — the only entry point.

    serve            run the bridge in the foreground
    ensure           start it detached if it is not answering (idempotent)
    stop             stop the bridge started by ensure
    status           print what /ping says
    show             show open annotations
    resolve          mark annotations as processed
    apply-hunk       apply single blocks of a draft edit
    url PATH         print the http://127.0.0.1:<port>/p/... URL for a file
    url --base       print only the base URL (http://127.0.0.1:<port>)
    pick-port        choose a free port (8791-8890) and store it in the config file
    install-skill    put this checkout at ~/.claude/skills/html-annotator
    install-hooks    register the SessionStart + PostToolUse hooks
    --version        print the version and exit

Installed as a console script this is `html-annotator <command>`;
`python -m html_annotator <command>` keeps working and means the same thing.
"""

import argparse
import json
import sys

from . import __version__, config, install, service


def _p(argv=None):
    ap = argparse.ArgumentParser(prog="html-annotator",
                                 description="HTML annotator bridge and CLI")
    ap.add_argument("--version", "-V", action="version",
                    version="html-annotator %s" % __version__)
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("serve", help="run the bridge in the foreground")

    e = sub.add_parser("ensure", help="start the bridge detached if needed")
    e.add_argument("--port", type=int, default=None)
    e.add_argument("--timeout", type=float, default=5.0)

    s = sub.add_parser("stop", help="stop the bridge started by ensure")
    s.add_argument("--port", type=int, default=None)

    st = sub.add_parser("status", help="print what /ping says")
    st.add_argument("--port", type=int, default=None)

    sub.add_parser("show", help="show open annotations", add_help=False)

    r = sub.add_parser("resolve", help="mark annotations as processed")
    r.add_argument("target", help="page slug or path to annotations.json")
    r.add_argument("--nrs", default="", help="comma separated annotation numbers")
    r.add_argument("--ids", default="", help="comma separated annotation ids")
    r.add_argument("--undo", action="store_true", help="set resolved back to false")
    r.add_argument("--port", type=int, default=None)

    sub.add_parser("apply-hunk", help="apply blocks of a draft edit", add_help=False)

    u = sub.add_parser("url", help="print the /p/ URL for a local file")
    u.add_argument("path", nargs="?")
    u.add_argument("--base", action="store_true",
                   help="print only the base URL of the bridge")

    pp = sub.add_parser("pick-port", help="choose a port and store it in the config file")
    pp.add_argument("--port", default=None,
                    help="store this port instead of searching (1-65535)")

    isk = sub.add_parser("install-skill", help="install into ~/.claude/skills")
    isk.add_argument("--copy", action="store_true",
                     help="copy instead of symlink (default on Windows)")

    ih = sub.add_parser("install-hooks", help="register the two hooks")
    ih.add_argument("--print", dest="toon", action="store_true",
                    help="show what would be written, change nothing")
    ih.add_argument("--target", default=None,
                    help="skill directory the hook command points at")
    return ap, ap.parse_args(argv)


def _nummers(tekst):
    return [x.strip() for x in (tekst or "").split(",") if x.strip()]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--version", "-V"):
        print("html-annotator %s" % __version__)
        return 0
    # show/apply-hunk have their own flags; argparse must not eat them.
    if argv and argv[0] == "show":
        from . import show
        return show.main(argv[1:])
    if argv and argv[0] == "apply-hunk":
        from . import hunks
        return hunks.main(argv[1:])

    ap, a = _p(argv)
    cmd = a.cmd

    if cmd == "serve":
        return service.serve()

    if cmd == "ensure":
        status, bericht = service.ensure(a.port, a.timeout)
        print(bericht, file=sys.stderr if status == "failed" else sys.stdout)
        return 1 if status == "failed" else 0

    if cmd == "stop":
        ok, bericht = service.stop(a.port)
        print(bericht)
        return 0 if ok else 1

    if cmd == "status":
        info = service.ping(a.port)
        if not info:
            print("no bridge on %s" % config.base_url(a.port))
            return 1
        print(json.dumps(info, indent=2))
        return 0

    if cmd == "resolve":
        uit = service.resolve(a.target, _nummers(a.nrs), _nummers(a.ids),
                              a.port, resolved=not a.undo)
        print(json.dumps(uit, indent=2, ensure_ascii=False))
        return 0 if uit.get("ok") else 1

    if cmd == "url":
        if a.base:
            print(config.base_url())
            return 0
        if not a.path:
            print("url: give a PATH, or --base", file=sys.stderr)
            return 2
        try:
            print(service.url_for(a.path))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        return 0

    if cmd == "pick-port":
        code, bericht, waarschuwing = service.pick_port(a.port)
        if bericht:
            print(bericht)
        if waarschuwing:
            soort = "warning: " if code == 0 else "error: "
            print(soort + waarschuwing.replace("\n", "\n" + soort), file=sys.stderr)
        return code

    if cmd == "install-skill":
        code, bericht = install.install_skill(kopie=a.copy or None)
        print(bericht)
        return code

    if cmd == "install-hooks":
        code, bericht = install.install_hooks(a.target, toon_alleen=a.toon)
        print(bericht)
        return code

    ap.print_help()
    return 2
