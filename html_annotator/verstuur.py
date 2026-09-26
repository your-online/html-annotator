"""Verstuur-knop: gedeelde logica voor de gate-hook (PreToolUse) en de nastap (PostToolUse).

Een akkoord is een entry in ``<root>/<slug>/state.json`` onder ``components.send.<key>``,
vastgelegd door ``/send-approve`` na een klik op Verstuur. Deze module zoekt bij een
verzendtool-aanroep het akkoord dat exact bij (kanaal, ontvanger, onderwerp, tekst) hoort.
Hij verstuurt niets en schrijft niets; dat doen de hooks via de bridge.
"""

import glob
import json
import os

from . import config
from .bridge import send_hash

# tool -> (kanaal, functie die (to, subject, text) uit tool_input haalt).
# Alleen WhatsApp: platte tekst, dus de platte-tekstprojectie van de kaart is één op
# één de body. Teams en mail versturen HTML en vragen eerst een besluit over wat er
# gehasht wordt (docs/verstuur-knop-onderzoek.md, Risico's).
TOOLS = {
    "mcp__whatsapp__send_message": (
        "whatsapp", lambda i: (i.get("recipient") or "", "", i.get("message") or "")),
}


def velden(tool_name, tool_input):
    """(kanaal, to, subject, text) voor een bekende verzendtool, anders None."""
    if tool_name not in TOOLS:
        return None
    kanaal, haal = TOOLS[tool_name]
    to, subject, text = haal(tool_input or {})
    return kanaal, to, subject, text


def zoek_akkoord(h, status="approved"):
    """Eerste akkoord met deze hash en status: (statePad, stateData, key, entry) of None.

    Een entry telt alleen als de hash ook klopt met de velden die erin staan; een
    handmatig aangepaste entry met een oude hash valt daarmee af.
    """
    for pad in sorted(glob.glob(os.path.join(str(config.root()), "*", "state.json"))):
        try:
            with open(pad, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        send = (data.get("components") or {}).get("send") or {}
        for key, e in send.items():
            if e.get("status") == status and e.get("hash") == h and send_hash(e) == h:
                return pad, data, key, e
    return None


def hash_voor(tool_name, tool_input):
    v = velden(tool_name, tool_input)
    if v is None:
        return None
    kanaal, to, subject, text = v
    return send_hash({"channel": kanaal, "to": to, "subject": subject, "text": text})
