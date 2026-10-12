"""Verstuur-knop: gedeelde logica voor de gate-hook (PreToolUse) en de nastap (PostToolUse).

Een akkoord is een entry in ``<root>/<slug>/state.json`` onder ``components.send.<key>``,
vastgelegd door ``/send-approve`` na een klik op Verstuur. Deze module zoekt bij een
verzendtool-aanroep het akkoord dat exact bij de verzonden velden hoort.
Hij verstuurt niets en schrijft niets; dat doen de hooks via de bridge.

Kanalen: WhatsApp (platte tekst, één op één de kaarttekst) en mail (sinds 27-09-2026).
Mail gaat als HTML de deur uit, maar het akkoord ligt op de platte tekst van de kaart.
De HTML in de tool-aanroep moet daarom exact ``tekst_naar_html(tekst)`` zijn; alles wat
daar niet uit terug te rekenen is (andere tags, attributen, handtekening) matcht nooit.
"""

import glob
import json
import os
import re

from . import config
from .bridge import adressen, send_hash

# Accounts en de MCP-server die ermee verstuurt (voor het vervolg van de wachter) staan
# per gebruiker in het configbestand, sleutel ``mail_servers``:
#   {"mail_servers": {"jij@example.com": "ms365-example"}}
# De afzender zit in de hash via de ``account``-parameter; welke server de call doet
# maakt voor de gate niet uit.
def mail_servers():
    data = config.read_config().get("mail_servers")
    if not isinstance(data, dict):
        return {}
    return {str(k).lower(): str(v) for k, v in data.items() if k and v}

# Elke ms365-server (``ms365`` of ``ms365-<naam>``): de afzender zit via ``account`` in de
# hash, de server niet. Een server buiten deze vorm krijgt van de gate geen oordeel
# (gewone permissieprompt).
MAIL_TOOL = re.compile(r"^mcp__ms365(?:-[A-Za-z0-9-]+)?__(send-mail|reply-mail-message)$")


class Ongeldig(ValueError):
    """Bekende verzendtool, maar in een vorm die de gate nooit doorlaat."""


# --- tekst <-> HTML ---------------------------------------------------------------

def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tekst_naar_html(tekst):
    """Vaste weergave: lege regel = nieuwe <p>, enkele regelafbreking = <br>."""
    return "".join("<p>%s</p>" % _esc(p).replace("\n", "<br>") for p in tekst.split("\n\n"))


_P = re.compile(r"<p>(.*?)</p>", re.S)


def html_naar_tekst(html):
    """Strikte inverse van tekst_naar_html; alles wat er niet exact uit kan komen: Ongeldig."""
    if not isinstance(html, str) or not html:
        raise Ongeldig("lege of ontbrekende HTML-body")
    delen = _P.findall(html)
    if "".join("<p>%s</p>" % d for d in delen) != html:
        raise Ongeldig("HTML-body is geen reeks <p>-blokken")
    tekst = "\n\n".join(d.replace("<br>", "\n").replace("&lt;", "<").replace("&gt;", ">")
                        .replace("&amp;", "&") for d in delen)
    if tekst_naar_html(tekst) != html:
        raise Ongeldig("HTML-body is niet de vaste weergave van een platte tekst")
    return tekst


# --- tool_input -> velden ----------------------------------------------------------

def _alleen(d, toegestaan, waar):
    if not isinstance(d, dict):
        raise Ongeldig("%s ontbreekt of is geen object" % waar)
    extra = set(d) - set(toegestaan)
    if extra:
        raise Ongeldig("%s bevat niet-toegestane velden: %s" % (waar, ", ".join(sorted(extra))))


def _ontvangers(lijst, waar):
    if lijst is None:
        return ""
    if not isinstance(lijst, list):
        raise Ongeldig("%s is geen lijst" % waar)
    uit = []
    for r in lijst:
        _alleen(r, ("emailAddress",), waar)
        _alleen(r.get("emailAddress"), ("address", "name"), waar)
        a = r["emailAddress"].get("address")
        if not a:
            raise Ongeldig("%s zonder adres" % waar)
        uit.append(a)
    return adressen(uit)


TOP = ("account", "body", "excludeResponse", "includeHeaders")


def _mail(tool, i):
    _alleen(i, TOP + (("messageId",) if tool == "reply-mail-message" else ()), "tool_input")
    account = (i.get("account") or "").strip().lower()
    if not account:
        raise Ongeldig("account ontbreekt: de afzender moet expliciet zijn")
    body = i.get("body")
    ontv = ("toRecipients", "ccRecipients", "bccRecipients")
    if tool == "send-mail":
        _alleen(body, ("Message", "SaveToSentItems"), "body")
        m = body.get("Message")
        _alleen(m, ("subject", "body") + ontv, "Message")
        _alleen(m.get("body"), ("contentType", "content"), "Message.body")
        if m["body"].get("contentType") != "html":
            raise Ongeldig("Message.body.contentType moet html zijn")
        html, subject, reply = m["body"].get("content"), m.get("subject") or "", ""
    else:
        _alleen(body, ("Comment", "Message"), "body")
        m = body.get("Message") or {}
        _alleen(m, ontv, "Message")
        html, subject, reply = body.get("Comment"), "", i.get("messageId") or ""
        if not reply:
            raise Ongeldig("messageId ontbreekt")
    to = _ontvangers(m.get("toRecipients"), "toRecipients")
    if not to:
        # Ook bij een antwoord: anders kiest Graph de ontvanger zelf (T31).
        raise Ongeldig("toRecipients moet expliciet gevuld zijn")
    return {"channel": "mail", "account": account, "to": to,
            "cc": _ontvangers(m.get("ccRecipients"), "ccRecipients"),
            "bcc": _ontvangers(m.get("bccRecipients"), "bccRecipients"),
            "subject": subject, "reply": reply, "text": html_naar_tekst(html)}


def velden(tool_name, tool_input):
    """Velden voor een bekende verzendtool, None voor een andere tool.
    Gooit Ongeldig als het een bekende tool is in een vorm die nooit mag matchen."""
    i = tool_input or {}
    if tool_name == "mcp__whatsapp__send_message":
        return {"channel": "whatsapp", "to": i.get("recipient") or "", "subject": "",
                "text": i.get("message") or ""}
    m = MAIL_TOOL.match(tool_name or "")
    if m:
        return _mail(m.group(1), i)
    return None


def hash_voor(tool_name, tool_input):
    """Hash over de verzonden velden; None als het geen verzendtool is. Bij een bekende
    tool in een ongeldige vorm een waarde die met geen enkel akkoord kan matchen."""
    try:
        v = velden(tool_name, tool_input)
    except Exception as ex:  # Ongeldig, maar ook een onverwachte vorm: nooit een match
        return "ongeldig: %s" % ex
    return None if v is None else send_hash(v)


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


# --- vervolg voor de wachter -------------------------------------------------------

def _lijst(csv):
    return [{"emailAddress": {"address": a}} for a in filter(None, (csv or "").split(","))]


def vervolg(e):
    """De exacte tool-aanroep bij een akkoord, of een string als er geen knop-route is."""
    kanaal = e.get("channel")
    if kanaal == "whatsapp":
        return {"tool": "mcp__whatsapp__send_message",
                "arguments": {"recipient": e.get("to"), "message": e.get("text")}}
    if kanaal == "mail":
        server = mail_servers().get((e.get("account") or "").lower())
        if not server:
            return "afzender %r heeft geen bekende MCP-server: vraag de reviewer in de chat" % e.get("account")
        m = {"toRecipients": _lijst(e.get("to"))}
        for k, veld in (("cc", "ccRecipients"), ("bcc", "bccRecipients")):
            if e.get(k):
                m[veld] = _lijst(e.get(k))
        html = tekst_naar_html(e.get("text") or "")
        if e.get("reply"):
            return {"tool": "mcp__%s__reply-mail-message" % server,
                    "arguments": {"account": e.get("account"), "messageId": e.get("reply"),
                                  "body": {"Comment": html, "Message": m}}}
        m.update({"subject": e.get("subject") or "", "body": {"contentType": "html", "content": html}})
        return {"tool": "mcp__%s__send-mail" % server,
                "arguments": {"account": e.get("account"), "body": {"Message": m, "SaveToSentItems": True}}}
    return "kanaal %r heeft geen Verstuur-gate: vraag de reviewer in de chat" % kanaal
