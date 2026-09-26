#!/usr/bin/env python3
"""PreToolUse-gate voor verzendtools (prototype, NIET geregistreerd).

Laat een verzendtool alleen automatisch door als (kanaal, ontvanger, onderwerp, tekst)
exact overeenkomt met een akkoord dat via de Verstuur-knop is vastgelegd (status
"approved", hash klopt). Geen match: "ask" — dan valt Claude Code terug op de gewone
permissieprompt, dus het huidige "typ verstuur"-pad blijft werken.

Registratie (pas na Lucs besluit), in ~/.claude/settings.json:
  "PreToolUse": [{"matcher": "mcp__whatsapp__send_message",
                  "hooks": [{"type": "command", "command": "python3 <pad>/bin/verstuur-gate-hook.py"}]}]
"""
import glob, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from html_annotator import config  # noqa: E402
from html_annotator.bridge import send_hash  # noqa: E402

# tool -> (kanaal, functie die (to, subject, text) uit tool_input haalt)
TOOLS = {
    "mcp__whatsapp__send_message": ("whatsapp", lambda i: (i.get("recipient", ""), "", i.get("message", ""))),
    # Teams/mail: body is HTML; eerst afspreken dat de kaart nieuwHtml als akkoordtekst
    # vastlegt, of de gate de HTML naar de platte projectie terugrekent. Nog niet gedaan.
}


def uit(beslissing, reden):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
          "permissionDecision": beslissing, "permissionDecisionReason": reden}}, ensure_ascii=False))
    sys.exit(0)


def main():
    ev = json.load(sys.stdin)
    tool = ev.get("tool_name", "")
    if tool not in TOOLS:
        sys.exit(0)  # niet onze zaak
    kanaal, haal = TOOLS[tool]
    to, subject, text = haal(ev.get("tool_input") or {})
    h = send_hash({"channel": kanaal, "to": to, "subject": subject, "text": text})
    for pad in glob.glob(os.path.join(str(config.root()), "*", "state.json")):
        try:
            send = (json.load(open(pad, encoding="utf-8")).get("components") or {}).get("send") or {}
        except (OSError, ValueError):
            continue
        for key, e in send.items():
            if e.get("status") == "approved" and e.get("hash") == h and send_hash(e) == h:
                uit("allow", "Verstuur-klik gevonden: %s/%s (hash %s)" % (os.path.basename(os.path.dirname(pad)), key, h[:8]))
    uit("ask", "Geen Verstuur-akkoord op deze exacte tekst en ontvanger; vraag Luc.")


if __name__ == "__main__":
    main()
