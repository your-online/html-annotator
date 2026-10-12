#!/usr/bin/env python3
"""PreToolUse-gate voor verzendtools (Verstuur-knop: WhatsApp en mail).

Laat een verzendtool alleen automatisch door als alle verzonden velden (kanaal,
ontvanger(s), onderwerp, tekst en bij mail ook afzender, Cc, Bcc en antwoord-op)
exact overeenkomen met een niet-verbruikt akkoord dat via de Verstuur-knop is vastgelegd
(status "approved", hash klopt). Geen match: "ask" — dan valt Claude Code terug op de
gewone permissieprompt, dus het "typ verstuur"-pad in de chat blijft werken.

Het akkoord wordt hier niet verbruikt; dat doet de nastap (verstuur-nastap-hook.py,
PostToolUse) na een geslaagde verzending. Zonder nastap laat deze gate dezelfde tekst
een tweede keer door.

Registratie: zie docs/verstuur-knop-onderzoek.md, "Registratie".
"""
import importlib, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from html_annotator import config, verstuur  # noqa: E402


def uit(beslissing, reden):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
          "permissionDecision": beslissing, "permissionDecisionReason": reden}}, ensure_ascii=False))
    sys.exit(0)


def ondertekend_groepsbericht(ev):
    """Optionele uitzondering op de knop-eis: één WhatsApp-groep waarvoor een externe
    verifier ondertekende berichten uitgeeft. Alleen met de config-sleutel
    ``signed_group_message`` (zie INSTALL.md):

        {"signed_group_message": {"jid": "120363000000000000@g.us",
                                  "verifier": "/pad/naar/verifier-repo",
                                  "module": "pakket.module",
                                  "label": "voorbeeldbericht"}}

    Alleen mcp__whatsapp__send_message naar exact die ``jid``; daarna beslist
    ``<module>.toegestaan(tool_name, tool_input) is True`` (geladen vanaf ``verifier``).
    Geen of onvolledige sleutel, of elke fout: geen uitzondering (gewone gate).
    Geeft het label terug bij een uitzondering, anders None."""
    if ev.get("tool_name") != "mcp__whatsapp__send_message":
        return None
    try:
        cfg = config.read_config().get("signed_group_message")
    except Exception:
        return None
    if not isinstance(cfg, dict):
        return None
    jid, pad, module = cfg.get("jid"), cfg.get("verifier"), cfg.get("module")
    if not (isinstance(jid, str) and jid and isinstance(pad, str) and pad
            and isinstance(module, str) and module):
        return None
    if (ev.get("tool_input") or {}).get("recipient") != jid:
        return None
    pad = os.path.expanduser(pad)
    try:
        sys.path.insert(0, pad)
        mod = importlib.import_module(module)
        if mod.toegestaan(ev.get("tool_name"), ev.get("tool_input")) is True:
            return str(cfg.get("label") or "ondertekend groepsbericht")
        return None
    except Exception:
        return None
    finally:
        if sys.path and sys.path[0] == pad:
            sys.path.pop(0)


def main():
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        uit("ask", "Verstuur-gate: hook-invoer onleesbaar; vraag de reviewer.")
    label = ondertekend_groepsbericht(ev)
    if label:
        uit("allow", "Verstuur-gate: %s, door de geconfigureerde verifier ondertekend en "
                     "nog niet verbruikt (signed_group_message in het configbestand)." % label)
    h = verstuur.hash_voor(ev.get("tool_name", ""), ev.get("tool_input"))
    if h is None:
        sys.exit(0)  # niet onze tool: geen oordeel
    if h.startswith("ongeldig"):
        uit("ask", "Verstuur-gate: deze aanroep kan nooit bij een knop-akkoord horen (%s); "
                   "vraag de reviewer om akkoord." % h[len("ongeldig: "):])
    try:
        gevonden = verstuur.zoek_akkoord(h)
    except Exception as ex:  # nooit per ongeluk allow: bij twijfel de gewone vraag
        uit("ask", "Verstuur-gate: akkoorden niet leesbaar (%s); vraag de reviewer." % ex)
    if gevonden:
        pad, _data, key, e = gevonden
        uit("allow", "Verstuur-klik gevonden: %s/%s (hash %s, akkoord %s)"
            % (os.path.basename(os.path.dirname(pad)), key, h[:8], e.get("approvalId")))
    uit("ask", "Geen niet-verbruikt Verstuur-akkoord op deze exacte tekst, ontvanger(s) en afzender; "
               "vraag de reviewer om akkoord.")


if __name__ == "__main__":
    main()
