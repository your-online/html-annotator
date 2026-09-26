#!/usr/bin/env python3
"""PreToolUse-gate voor verzendtools (Verstuur-knop, eerst alleen WhatsApp).

Laat een verzendtool alleen automatisch door als (kanaal, ontvanger, onderwerp, tekst)
exact overeenkomt met een niet-verbruikt akkoord dat via de Verstuur-knop is vastgelegd
(status "approved", hash klopt). Geen match: "ask" — dan valt Claude Code terug op de
gewone permissieprompt, dus het "typ verstuur"-pad in de chat blijft werken.

Het akkoord wordt hier niet verbruikt; dat doet de nastap (verstuur-nastap-hook.py,
PostToolUse) na een geslaagde verzending. Zonder nastap laat deze gate dezelfde tekst
een tweede keer door.

Registratie: zie docs/verstuur-knop-onderzoek.md, "Klaar voor livegang".
"""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from html_annotator import verstuur  # noqa: E402


def uit(beslissing, reden):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
          "permissionDecision": beslissing, "permissionDecisionReason": reden}}, ensure_ascii=False))
    sys.exit(0)


def main():
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        uit("ask", "Verstuur-gate: hook-invoer onleesbaar; vraag de reviewer.")
    h = verstuur.hash_voor(ev.get("tool_name", ""), ev.get("tool_input"))
    if h is None:
        sys.exit(0)  # niet onze tool: geen oordeel
    try:
        gevonden = verstuur.zoek_akkoord(h)
    except Exception as ex:  # nooit per ongeluk allow: bij twijfel de gewone vraag
        uit("ask", "Verstuur-gate: akkoorden niet leesbaar (%s); vraag de reviewer." % ex)
    if gevonden:
        pad, _data, key, e = gevonden
        uit("allow", "Verstuur-klik gevonden: %s/%s (hash %s, akkoord %s)"
            % (os.path.basename(os.path.dirname(pad)), key, h[:8], e.get("approvalId")))
    uit("ask", "Geen niet-verbruikt Verstuur-akkoord op deze exacte tekst en ontvanger; "
               "vraag de reviewer om akkoord.")


if __name__ == "__main__":
    main()
