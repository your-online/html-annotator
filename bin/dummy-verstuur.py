#!/usr/bin/env python3
"""Dummy-kanaal: speelt een mcp__whatsapp__send_message-aanroep na zoals Claude Code hem
doet, maar 'verstuurt' naar een logbestand. Er gaat nooit iets naar buiten.

1. PreToolUse: bin/verstuur-gate-hook.py met het tool-event. Alleen bij "allow" gaat
   het door; "ask" betekent in het echt: Claude Code vraagt de reviewer om toestemming.
   De dummy stopt dan (exit 10), want er is hier niemand om te antwoorden.
2. "Versturen": één JSON-regel in --log.
3. PostToolUse: bin/verstuur-nastap-hook.py met een geslaagd tool-resultaat
   ({"success": true}, zoals de WhatsApp-MCP antwoordt), of --faal voor success false.

Uitvoer: JSON met de beslissing van de gate en de melding van de nastap.
"""
import argparse, json, os, subprocess, sys, time

BIN = os.path.dirname(os.path.abspath(__file__))
TOOL = "mcp__whatsapp__send_message"


def hook(naam, ev):
    r = subprocess.run([sys.executable, os.path.join(BIN, naam)], input=json.dumps(ev),
                       capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        sys.exit("hook %s faalde (%d): %s" % (naam, r.returncode, r.stderr.strip()))
    return json.loads(r.stdout) if r.stdout.strip() else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="recipient zoals de tool hem krijgt")
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--faal", action="store_true", help="tool meldt success false")
    a = ap.parse_args()
    tekst = open(a.text_file, encoding="utf-8").read()
    ev = {"hook_event_name": "PreToolUse", "tool_name": TOOL,
          "tool_input": {"recipient": a.to, "message": tekst}}
    pre = hook("verstuur-gate-hook.py", ev).get("hookSpecificOutput", {})
    uit = {"gate": pre.get("permissionDecision"), "gateReden": pre.get("permissionDecisionReason")}
    if pre.get("permissionDecision") != "allow":
        print(json.dumps(uit, ensure_ascii=False))
        return 10
    with open(a.log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"to": a.to, "text": tekst, "at": time.strftime("%H:%M:%S")},
                           ensure_ascii=False) + "\n")
    ev.update({"hook_event_name": "PostToolUse",
               "tool_response": {"success": not a.faal, "message": "dummy"}})
    post = hook("verstuur-nastap-hook.py", ev).get("hookSpecificOutput", {})
    uit.update({"verstuurd": True, "nastap": post.get("additionalContext")})
    print(json.dumps(uit, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
