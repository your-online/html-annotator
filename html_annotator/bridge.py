#!/usr/bin/env python3
"""Local bridge for the HTML annotator (HTML-ANNOTATOR v3).

New embeds carry the ``<!-- HTML-ANNOTATOR v3 -->`` marker; the older
``LUC-ANNOTATOR`` v1/v2 blocks stay recognised everywhere (content hash, hooks),
so pages that already exist keep working.

Runs on 127.0.0.1:8791 (macOS, Linux, Windows) and writes annotations straight
to <root>/<page-slug>/ronde-NN/annotations.json, screenshot crops included in
ronde-NN/screenshots/. The root is ~/annotations unless configured otherwise
(see config.py).

Stdlib only. Pillow is used when it happens to be installed; otherwise headless
Chrome (or Edge) cuts the crop itself through an iframe clip. No browser found:
the annotation is stored without a crop.

Start:  python -m html_annotator serve
Check:  curl -s http://127.0.0.1:8791/ping
"""

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, config
from .record import schoon_locator, zet_ref_velden
from .refs import expand_comment

HOST = config.HOST
PORT = config.port()
ROOT = str(config.root())


def vind_chrome():
    """Pad naar een Chromium-browser voor headless crops, of None.

    Volgorde: env ANNOTATOR_CHROME / LUC_ANNOTATOR_CHROME > PATH > bekende
    installatiepaden per platform (macOS, Windows, Linux). Edge telt als
    fallback: dezelfde headless-vlaggen werken daar.
    """
    for var in ("HTML_ANNOTATOR_CHROME", "ANNOTATOR_CHROME", "LUC_ANNOTATOR_CHROME"):
        p = os.environ.get(var)
        if p:
            return p if os.path.isfile(p) else shutil.which(p)
    for naam in ("google-chrome", "google-chrome-stable", "chrome", "chromium",
                 "chromium-browser", "msedge", "microsoft-edge"):
        p = shutil.which(naam)
        if p:
            return p
    kandidaten = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
        "/snap/bin/chromium", "/usr/bin/microsoft-edge",
    ]
    for basis in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                  os.environ.get("LocalAppData")):
        if basis:
            kandidaten.append(os.path.join(basis, "Google", "Chrome", "Application", "chrome.exe"))
            kandidaten.append(os.path.join(basis, "Microsoft", "Edge", "Application", "msedge.exe"))
    for p in kandidaten:
        if os.path.isfile(p):
            return p
    return None


CHROME = vind_chrome()


def chrome_vlaggen():
    """Headless flags for a screenshot run. Running as root (typical on a server or in a
    container) Chrome refuses to start its sandbox; --no-sandbox is the documented way out."""
    vlaggen = ["--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--no-first-run", "--no-default-browser-check",
               "--allow-file-access-from-files", "--disable-dev-shm-usage"]
    if os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0:
        vlaggen.append("--no-sandbox")
    return vlaggen


def run_chrome(args, timeout=90):
    """subprocess.run with the Chrome stderr tail in the error, so a failed crop says why."""
    try:
        subprocess.run([CHROME] + chrome_vlaggen() + args, check=True, capture_output=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        staart = (e.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-3:]
        raise RuntimeError("chrome exit %d: %s" % (e.returncode, " | ".join(staart)[:400]))
CACHE = os.path.join(tempfile.gettempdir(), "html-annotator-shots")
MARGE = 12
LOCK = threading.Lock()

try:
    from PIL import Image  # type: ignore
    HEEFT_PILLOW = True
except Exception:  # pragma: no cover - afhankelijk van omgeving
    HEEFT_PILLOW = False


# ---------------------------------------------------------------- hulpjes

def slugify(tekst, standaard="pagina"):
    s = re.sub(r"[^a-z0-9]+", "-", (tekst or "").lower()).strip("-")
    return s[:60] or standaard


def pad_van_page(page, page_file):
    """Absoluut bestandspad van de pagina, of None."""
    if page_file:
        p = os.path.expanduser(page_file)  # "~/Desktop/x.html" komt van de /p/-route
        if os.path.isfile(p):
            return p
    if page and page.startswith("file://"):
        p = urllib.parse.unquote(urllib.parse.urlparse(page).path)
        if os.path.isfile(p):
            return p
    if page and "/p/" in page:
        try:
            rel = urllib.parse.unquote(urllib.parse.urlparse(page).path).split("/p/", 1)[1]
            p = os.path.join(os.path.expanduser("~"), rel)
            if os.path.isfile(p):
                return p
        except Exception:
            pass
    return None


# Both marker generations: new embeds write HTML-ANNOTATOR, existing pages
# carry LUC-ANNOTATOR v1/v2 and must keep hashing the same way.
ANNOTATOR_BLOK = re.compile(
    r"<!--\s*(?:HTML|LUC)-ANNOTATOR.*?<!--\s*/(?:HTML|LUC)-ANNOTATOR\s*-->",
    re.S | re.I)
MARKER_START = re.compile(r"<!--\s*(?:HTML|LUC)-ANNOTATOR", re.I)


def content_hash(bestand, dom_hash):
    """Hash van de pagina-inhoud zonder het annotator-blok."""
    if bestand:
        try:
            with open(bestand, "r", encoding="utf-8", errors="replace") as f:
                bron = f.read()
            bron = ANNOTATOR_BLOK.sub("", bron)
            # ook een niet-afgesloten v1-blok wegknippen
            m = MARKER_START.search(bron)
            i = m.start() if m else -1
            if i >= 0:
                bron = bron[:i]
            return "sha256:" + hashlib.sha256(bron.encode("utf-8")).hexdigest()[:32]
        except OSError:
            pass
    return "dom:" + (dom_hash or "onbekend")


def pagina_map(payload):
    bestand = pad_van_page(payload.get("page"), payload.get("pageFile"))
    if bestand:
        slug = slugify(os.path.splitext(os.path.basename(bestand))[0])
    else:
        slug = slugify(payload.get("slug") or payload.get("title"))
    return os.path.join(ROOT, slug), bestand


def rondes(map_pad):
    if not os.path.isdir(map_pad):
        return []
    uit = []
    for naam in os.listdir(map_pad):
        m = re.fullmatch(r"ronde-(\d+)", naam)
        if m and os.path.isdir(os.path.join(map_pad, naam)):
            uit.append(int(m.group(1)))
    return sorted(uit)


def lees_ronde(map_pad, nr):
    p = os.path.join(map_pad, "ronde-%02d" % nr, "annotations.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def bepaal_ronde(payload, maak=False):
    """Geeft (ronde-nr, ronde-map, json-pad, data-of-None, paginabestand).

    De lopende ronde is de hoogste bestaande ronde die niet gesloten is. Een
    gewijzigde pagina-inhoud opent dus GEEN nieuwe ronde meer; alleen een
    afgesloten ronde (POST /remove-all) doet dat. De contentHash wordt nog wel
    bijgehouden, als context bij welke paginaversie de feedback hoorde.
    """
    map_pad, bestand = pagina_map(payload)
    h = content_hash(bestand, payload.get("domHash"))
    bestaand = rondes(map_pad)
    nr, data = None, None
    if bestaand:
        laatste = bestaand[-1]
        d = lees_ronde(map_pad, laatste)
        if d is not None and not d.get("closed"):
            nr, data = laatste, d
        else:
            nr = laatste + 1
    else:
        nr = 1
    ronde_map = os.path.join(map_pad, "ronde-%02d" % nr)
    json_pad = os.path.join(ronde_map, "annotations.json")
    if data is None:
        data = {
            "page": payload.get("page"),
            "pageFile": bestand,
            "round": nr,
            "contentHash": h,
            "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "doc": payload.get("doc") or {},
            "annotations": [],
        }
    if maak:
        os.makedirs(os.path.join(ronde_map, "screenshots"), exist_ok=True)
    return nr, ronde_map, json_pad, data, bestand, h


def schrijf(json_pad, data):
    os.makedirs(os.path.dirname(json_pad), exist_ok=True)
    tmp = json_pad + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, json_pad)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------------ screenshots

def volledige_shot(bestand, page_url, dw, dh):
    """Volledige paginascreenshot (gecached op inhoud + afmeting)."""
    os.makedirs(CACHE, exist_ok=True)
    sleutel = hashlib.sha256(
        ("%s|%s|%s|%s" % (bestand or page_url, dw, dh,
                          os.path.getmtime(bestand) if bestand else "")
         ).encode()).hexdigest()[:24]
    uit = os.path.join(CACHE, sleutel + ".png")
    if os.path.isfile(uit):
        return uit
    url = page_url
    if bestand:
        url = "file://" + urllib.parse.quote(bestand)
    eis_chrome()
    run_chrome(["--screenshot=" + uit, "--window-size=%d,%d" % (dw, dh), url])
    return uit


def crop_via_chrome(bestand, page_url, dw, dh, box, uit):
    """Fallback zonder Pillow: iframe-clip renderen met headless Chrome."""
    eis_chrome()
    x0, y0, x1, y1 = box
    url = "file://" + urllib.parse.quote(bestand) if bestand else page_url
    html = (
        "<!doctype html><meta charset=utf-8>"
        "<style>html,body{margin:0;padding:0;overflow:hidden;background:#fff}"
        "iframe{position:absolute;border:0;left:%dpx;top:%dpx;width:%dpx;height:%dpx}"
        "</style><iframe src=\"%s\" scrolling=no></iframe>"
        % (-x0, -y0, dw, dh, url))
    os.makedirs(CACHE, exist_ok=True)
    wrapper = os.path.join(CACHE, "clip-%d.html" % int(time.time() * 1000))
    with open(wrapper, "w", encoding="utf-8") as f:
        f.write(html)
    try:
        run_chrome(["--screenshot=" + uit,
                    "--window-size=%d,%d" % (max(1, x1 - x0), max(1, y1 - y0)),
                    "file://" + urllib.parse.quote(wrapper)])
    finally:
        try:
            os.remove(wrapper)
        except OSError:
            pass
    return uit


def eis_chrome():
    """Geen Chrome/Edge: crop overslaan. h_save vangt dit en bewaart de annotatie
    zonder afbeelding (imageError), zodat opslaan nooit van een browser afhangt."""
    if not CHROME:
        print("no Chrome/Edge found: crop skipped, annotation still stored "
              "(set HTML_ANNOTATOR_CHROME to point at a browser)", flush=True)
        raise RuntimeError("no Chrome/Edge found (HTML_ANNOTATOR_CHROME)")


def maak_crop(bestand, page_url, doc, rect, uit_pad):
    dw = int(doc.get("w") or 800)
    dh = int(doc.get("h") or 2000)
    x0 = max(0, int(rect["x"]) - MARGE)
    y0 = max(0, int(rect["y"]) - MARGE)
    x1 = min(dw, int(rect["x"]) + int(rect["w"]) + MARGE)
    y1 = min(dh, int(rect["y"]) + int(rect["h"]) + MARGE)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("lege crop")
    os.makedirs(os.path.dirname(uit_pad), exist_ok=True)
    if HEEFT_PILLOW:
        vol = volledige_shot(bestand, page_url, dw, dh)
        with Image.open(vol) as img:
            img.crop((x0, y0, min(x1, img.width), min(y1, img.height))).save(uit_pad)
    else:
        crop_via_chrome(bestand, page_url, dw, dh, (x0, y0, x1, y1), uit_pad)
    return uit_pad


# -------------------------------------------------------------- endpoints

def h_session(payload):
    nr, ronde_map, json_pad, data, _, h = bepaal_ronde(payload)
    lijst = data.get("annotations", [])
    open_ann = []
    for a in lijst:
        if a.get("resolved"):
            continue
        open_ann.append({
            "nr": a.get("nr"), "id": a.get("id"), "type": a.get("type"),
            "rect": a.get("_rect") or a.get("rect") or None,
            "comment": a.get("comment") or "",
            "target": a.get("target") or "",
            "selectedText": a.get("selectedText") or "",
            "locator": a.get("locator") or None,
            "refs": a.get("refs") or [],
            "commentExpanded": a.get("commentExpanded") or expand_comment(
                a.get("comment") or "", a.get("refs") or []),
            "refsIncomplete": a.get("refsIncomplete") or [],
            "veld": a.get("veld") or "",
            "origineel": a.get("origineel") or "",
            "nieuw": a.get("nieuw") or "",
            "origineelHtml": a.get("origineelHtml") or "",
            "nieuwHtml": a.get("nieuwHtml") or "",
            "rijk": bool(a.get("rijk")),
            "diff": a.get("diff") or [],
            "hunks": a.get("hunks") or [],
            "createdAt": a.get("createdAt"),
            # anker is verdacht zodra de pagina sinds die annotatie gewijzigd is
            "stale": bool(a.get("contentHash")) and a.get("contentHash") != h,
        })
    return {"ok": True, "round": nr, "dir": ronde_map, "jsonPath": json_pad,
            "count": len(open_ann),
            "total": len(lijst),
            "resolved": len(lijst) - len(open_ann),
            "maxNr": max([a.get("nr", 0) for a in lijst] or [0]),
            "annotations": open_ann,
            "exists": os.path.isfile(json_pad),
            "contentHash": h}


def h_resolve(payload):
    """Markeert annotaties als verwerkt (of draait dat terug met resolved:false).

    Body: {"jsonPath": "...", "nrs": [1,2]} of {"ids": [...]}, eventueel met
    {"resolved": false}. Zonder jsonPath wordt de lopende ronde van de pagina
    gebruikt (page/pageFile/slug, net als de andere routes).
    """
    json_pad = payload.get("jsonPath")
    if json_pad:
        json_pad = os.path.expanduser(json_pad)
        if not os.path.isfile(json_pad):
            raise ValueError("annotations.json niet gevonden: %s" % json_pad)
        with open(json_pad, "r", encoding="utf-8") as f:
            data = json.load(f)
        nr = data.get("round")
    else:
        nr, _ronde_map, json_pad, data, _bestand, _h = bepaal_ronde(payload)
        if not os.path.isfile(json_pad):
            raise ValueError("nog geen annotaties voor deze pagina")

    nrs = set(int(x) for x in (payload.get("nrs") or []))
    ids = set(str(x) for x in (payload.get("ids") or []))
    hunks = set(int(x) for x in (payload.get("hunks") or []))
    if hunks and len(nrs) != 1:
        # Een hunknummer is alleen betekenisvol binnen één bewerking; zonder die
        # koppeling zou "hunk 2" van drie annotaties tegelijk afgevinkt worden.
        raise ValueError("geef bij hunks precies één nr mee")
    if not nrs and not ids:
        raise ValueError("geef nrs of ids mee")
    waarde = payload.get("resolved", True) is not False
    nu = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    geraakt = []
    hunks_geraakt = []
    hunks_ontbreken = []
    for a in data.get("annotations", []):
        if not (a.get("nr") in nrs or str(a.get("id")) in ids):
            continue
        if hunks:
            # Alleen de genoemde blokken afvinken. De bewerking zelf geldt pas als
            # verwerkt zodra er geen enkel blok meer openstaat.
            gevonden = set()
            for h in a.get("hunks") or []:
                if h.get("n") in hunks:
                    h["resolved"] = waarde
                    gevonden.add(h.get("n"))
            hunks_geraakt = sorted(gevonden)
            hunks_ontbreken = sorted(hunks - gevonden)
            alle = a.get("hunks") or []
            a["resolved"] = bool(alle) and all(h.get("resolved") for h in alle)
            if a["resolved"]:
                a["resolvedAt"] = nu
            else:
                a.pop("resolvedAt", None)
            geraakt.append(a.get("nr"))
            continue
        a["resolved"] = waarde
        if waarde:
            a["resolvedAt"] = nu
        else:
            a.pop("resolvedAt", None)
        # de hele bewerking afvinken vinkt ook alle losse blokken af
        for h in a.get("hunks") or []:
            h["resolved"] = waarde
        geraakt.append(a.get("nr"))
    ontbreekt = sorted(nrs - set(geraakt))
    data["updatedAt"] = nu
    schrijf(json_pad, data)
    open_n = len([a for a in data.get("annotations", []) if not a.get("resolved")])
    uit = {"ok": True, "round": nr, "jsonPath": json_pad, "resolved": sorted(geraakt),
           "notFound": ontbreekt, "open": open_n,
           "total": len(data.get("annotations", []))}
    if hunks:
        uit["hunksResolved"] = hunks_geraakt
        uit["hunksNotFound"] = hunks_ontbreken
        uit["hunksOpen"] = sum(
            1 for a in data.get("annotations", []) for h in (a.get("hunks") or [])
            if not h.get("resolved"))
    return uit


def h_save(payload):
    ann = dict(payload.get("annotation") or {})
    nr, ronde_map, json_pad, data, bestand, h = bepaal_ronde(payload, maak=True)
    data["lastContentHash"] = h
    data["doc"] = payload.get("doc") or data.get("doc") or {}
    lijst = data.setdefault("annotations", [])

    bestaande = next((a for a in lijst if a.get("id") == ann.get("id")), None)
    nummer = bestaande.get("nr") if bestaande else (
        max([a.get("nr", 0) for a in lijst] or [0]) + 1)

    rec = {
        "nr": nummer,
        "type": ann.get("type") or ("text" if ann.get("selectedText") else "region"),
        "target": (ann.get("target") or "").strip(),
        "comment": (ann.get("comment") or "").strip(),
        "id": ann.get("id"),
        "createdAt": ann.get("createdAt") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        # paginaversie waarop deze annotatie is gezet (context + stale-detectie)
        "contentHash": h,
    }
    zet_ref_velden(rec, ann.get("refs"))
    loc = schoon_locator(ann.get("locator"))
    if loc:
        rec["locator"] = loc
    if bestaande and bestaande.get("resolved"):
        rec["resolved"] = True
        rec["resolvedAt"] = bestaande.get("resolvedAt")

    if rec["type"] == "text":
        rec["selectedText"] = ann.get("selectedText") or ""
    elif rec["type"] == "edit":
        # De tekst van een conceptbericht is zelf herschreven. Bewaren als
        # voor/na plus de losse wijzigingen, zodat een agent ziet wat er moet
        # veranderen zonder de twee versies te hoeven vergelijken. Geen crop: het
        # bewijs is de tekst zelf.
        rec["veld"] = (ann.get("veld") or "").strip()
        rec["origineel"] = ann.get("origineel") or ""
        rec["nieuw"] = ann.get("nieuw") or ""
        # De kaart is rich text: naast de platte projectie (waarop gedift wordt) bewaren
        # we de mail-veilige HTML van beide versies. Die is de grondwaarheid zodra er
        # ook opmaak wijzigde, want opmaak staat per definitie niet in de platte tekst.
        rec["origineelHtml"] = ann.get("origineelHtml") or ""
        rec["nieuwHtml"] = ann.get("nieuwHtml") or ""
        rec["rijk"] = bool(ann.get("rijk"))
        rec["diff"] = ann.get("diff") or []
        # Per hunk bewaren we of hij al verwerkt is. Bestond deze bewerking al, dan
        # blijven eerder afgevinkte hunks afgevinkt zolang ze inhoudelijk hetzelfde
        # zijn — anders zou een nieuwe wijziging elders het hele blok heropenen.
        oude_hunks = {}
        if bestaande:
            for h in bestaande.get("hunks") or []:
                sleutel = (h.get("soort", "tekst"), h.get("verwijderd", ""),
                           h.get("toegevoegd", ""), h.get("blok", ""),
                           h.get("omschrijving", ""))
                oude_hunks[sleutel] = h.get("resolved", False)
        hunks = []
        for h in ann.get("hunks") or []:
            h = dict(h)
            sleutel = (h.get("soort", "tekst"), h.get("verwijderd", ""),
                       h.get("toegevoegd", ""), h.get("blok", ""),
                       h.get("omschrijving", ""))
            h["resolved"] = oude_hunks.get(sleutel, False)
            hunks.append(h)
        rec["hunks"] = hunks
    else:
        rect = ann.get("rect") or {}
        rel = "screenshots/annotatie-%02d.png" % nummer
        rec["_rect"] = rect
        # Bewerkt iemand een annotatie die bij een oudere paginaversie hoort, dan zou
        # opnieuw croppen de goede oude crop overschrijven met het verkeerde gebied.
        # In dat geval de bestaande crop en hash laten staan.
        hergebruik = (bestaande and bestaande.get("image")
                      and bestaande.get("_rect") == rect
                      and bestaande.get("contentHash")
                      and bestaande["contentHash"] != h)
        if hergebruik:
            rec["image"] = bestaande["image"]
            rec["contentHash"] = bestaande["contentHash"]
        else:
            try:
                maak_crop(bestand, payload.get("page"), data["doc"], rect,
                          os.path.join(ronde_map, rel))
                rec["image"] = rel
            except Exception as e:  # crop mislukt: annotatie toch bewaren
                rec["image"] = None
                rec["imageError"] = str(e)[:200]

    # meegestuurde afbeelding (geplakt/bijgevoegd) als los bestand wegschrijven
    img = ann.get("img")
    if isinstance(img, str) and img.startswith("data:image"):
        kop, _, body = img.partition(",")
        ext = "png" if "png" in kop else ("jpg" if "jpeg" in kop or "jpg" in kop else "png")
        rel = "screenshots/annotatie-%02d-bijlage.%s" % (nummer, ext)
        try:
            os.makedirs(os.path.join(ronde_map, "screenshots"), exist_ok=True)
            with open(os.path.join(ronde_map, rel), "wb") as f:
                f.write(base64.b64decode(body))
            rec["attachment"] = rel
        except Exception:
            pass
    elif bestaande and bestaande.get("attachment"):
        # bijlage stond al op schijf; de pagina stuurt hem na een refresh niet opnieuw mee
        rec["attachment"] = bestaande["attachment"]

    if bestaande:
        lijst[lijst.index(bestaande)] = rec
    else:
        lijst.append(rec)
    data["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    schrijf(json_pad, data)
    return {"ok": True, "round": nr, "jsonPath": json_pad, "nr": nummer,
            "image": rec.get("image"), "count": len(lijst)}


def h_delete(payload):
    nr, ronde_map, json_pad, data, _, _h = bepaal_ronde(payload)
    if not os.path.isfile(json_pad):
        return {"ok": True, "round": nr, "count": 0, "jsonPath": json_pad}
    lijst = data.get("annotations", [])
    weg = [a for a in lijst if a.get("id") == payload.get("id")]
    data["annotations"] = [a for a in lijst if a.get("id") != payload.get("id")]
    for a in weg:
        for sleutel in ("image", "attachment"):
            if a.get(sleutel):
                try:
                    os.remove(os.path.join(ronde_map, a[sleutel]))
                except OSError:
                    pass
    data["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    schrijf(json_pad, data)
    return {"ok": True, "round": nr, "jsonPath": json_pad,
            "count": len(data["annotations"])}


def h_remove_all(payload):
    """Wist de lopende ronde en sluit hem af; de volgende annotatie opent ronde+1."""
    nr, ronde_map, json_pad, data, _, _h = bepaal_ronde(payload)
    if not os.path.isfile(json_pad):
        return {"ok": True, "round": nr, "cleared": 0, "nextRound": nr}
    aantal = len(data.get("annotations", []))
    shots = os.path.join(ronde_map, "screenshots")
    if os.path.isdir(shots):
        shutil.rmtree(shots, ignore_errors=True)
    os.makedirs(shots, exist_ok=True)
    data["annotations"] = []
    data["closed"] = True
    data["clearedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    schrijf(json_pad, data)
    return {"ok": True, "round": nr, "cleared": aantal, "nextRound": nr + 1,
            "jsonPath": json_pad}


def _state_pad(payload):
    map_pad, bestand = pagina_map(payload)
    return os.path.join(map_pad, "state.json"), bestand


def h_state(payload):
    """Leest de opgeslagen componentstate van een pagina (bv. checkboxen).

    Body: {"page": "..."} (of pageFile/slug, zoals de andere routes).
    State leeft per pagina in <slug>/state.json, los van de annotatierondes:
    een checkbox-vinkje is een blijvende status, geen feedbackronde.
    """
    p, _ = _state_pad(payload)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {"components": {}}
    return {"ok": True, "statePath": p, "state": data}


def h_state_save(payload):
    """Bewaart één state-wijziging van een paginacomponent.

    Body: {"page": "...", "component": "checklist", "key": "#74",
           "value": {"checked": true, "label": "..."}}
    De value wordt over de bestaande entry gemergd; changedAt wordt gezet zodat
    een agent ziet wanneer er iets gewijzigd is (net als bij annotaties).
    """
    key = (payload.get("key") or "").strip()
    if not key:
        raise ValueError("geef key mee")
    component = (payload.get("component") or "default").strip()
    if component == "send":
        # Akkoorden lopen alleen via /send-approve (Origin-check + eigen hash);
        # /state-save heeft CORS * en mag ze dus nooit kunnen vervalsen.
        raise ValueError("component 'send' is alleen via /send-approve te schrijven")
    p, bestand = _state_pad(payload)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {"page": payload.get("page"), "pageFile": bestand, "components": {}}
    nu = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    comp = data.setdefault("components", {}).setdefault(component, {})
    entry = comp.setdefault(key, {})
    waarde = payload.get("value")
    if isinstance(waarde, dict):
        entry.update(waarde)
    else:
        entry["value"] = waarde
    entry["changedAt"] = nu
    data["updatedAt"] = nu
    schrijf(p, data)
    return {"ok": True, "statePath": p, "component": component, "key": key,
            "entry": entry}


def open_url(url):
    """Geeft een URL aan het OS: `open` (macOS), os.startfile (Windows),
    xdg-open (Linux); anders webbrowser als laatste redmiddel."""
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=True, capture_output=True, timeout=20)
    elif os.name == "nt":
        os.startfile(url)  # type: ignore[attr-defined]
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", url], check=True, capture_output=True, timeout=20)
    else:
        import webbrowser
        if not webbrowser.open(url):
            raise RuntimeError("geen manier gevonden om een URL te openen")


def h_sessie(payload):
    """Opent een nieuwe Claude Code-sessie met een voorgeladen prompt.

    Nodig omdat een ingebedde browser custom schemes als claude:// niet aan het
    OS doorgeeft: een klik doet daar stilzwijgend niets. De bridge draait buiten
    de browser en kan de URL aan het OS doorgeven (open/startfile/xdg-open).

    Bewust beperkt tot het claude-scheme, zodat dit geen algemene URL-opener
    wordt waarmee een willekeurige pagina van alles kan starten.
    """
    url = (payload.get("url") or "").strip()
    if not url:
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("geef url of prompt mee")
        url = "claude://code/new?q=" + urllib.parse.quote(prompt)
    if not url.startswith("claude://"):
        raise ValueError("alleen claude:// is toegestaan")
    open_url(url)
    return {"ok": True, "geopend": url[:80] + ("..." if len(url) > 80 else "")}


# === Verstuur-knop (prototype) ============================================
# De bridge verstuurt NOOIT zelf iets. Hij legt alleen vast welke exacte tekst de
# reviewer met een klik heeft goedgekeurd, met een hash die de bridge zelf berekent.
# De agent die het concept maakte wacht daarop (bin/wacht-op-verstuur.py), verifieert
# de hash en verstuurt precies die tekst. Elke bewerking na de klik trekt het akkoord in.

SEND_VELDEN = ("channel", "to", "subject", "text")

# Ontvanger zoals de verzendtool hem krijgt, per kanaal. WhatsApp
# (mcp__whatsapp__send_message, argument ``recipient``): een nummer met landcode
# zonder + of spaties, of een JID. Een kaart met "+31 6 ..." zou nooit matchen in de
# gate, dus die wordt bij de klik al geweigerd.
SEND_TO = {
    "whatsapp": re.compile(r"^(?:\d{8,15}|[0-9A-Za-z._-]+@(?:s\.whatsapp\.net|g\.us|lid))$"),
}


def send_canon(v):
    """Canonieke vorm van wat er de deur uit gaat: kanaal, ontvanger, onderwerp, tekst."""
    return json.dumps({k: (v.get(k) or "") for k in SEND_VELDEN}, sort_keys=True,
                      ensure_ascii=False, separators=(",", ":"))


def send_hash(v):
    return hashlib.sha256(send_canon(v).encode("utf-8")).hexdigest()


def _send_entry(payload):
    key = (payload.get("key") or "").strip()
    if not key:
        raise ValueError("geef key mee")
    p, bestand = _state_pad(payload)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {"page": payload.get("page"), "pageFile": bestand, "components": {}}
    comp = data.setdefault("components", {}).setdefault("send", {})
    return p, data, comp, key


def h_send_approve(payload):
    """Legt een klik op Verstuur vast. Alleen vanuit een pagina die de bridge zelf serveert."""
    tekst = payload.get("text") or ""
    if not tekst.strip():
        raise ValueError("lege tekst kan niet goedgekeurd worden")
    if not (payload.get("channel") and payload.get("to")):
        raise ValueError("kanaal en ontvanger zijn verplicht")
    if payload.get("channel") not in SEND_TO:
        # Eerst alleen WhatsApp (besluit 26-09-2026). Een klik op een mail- of
        # Teams-kaart zou een akkoord suggereren dat de gate niet kent.
        raise ValueError("kanaal %r heeft nog geen Verstuur-knop (alleen: %s)"
                         % (payload.get("channel"), ", ".join(sorted(SEND_TO))))
    vorm = SEND_TO.get(payload.get("channel"))
    if vorm and not vorm.match(payload.get("to")):
        raise ValueError("ontvanger %r past niet bij %s (verwacht: nummer met landcode zonder +, "
                         "of een JID)" % (payload.get("to"), payload.get("channel")))
    p, data, comp, key = _send_entry(payload)
    # Waar de akkoorden vandaan komen, zodat de nastap-hook /send-done kan aanroepen
    # zonder de pagina te kennen.
    data["page"] = payload.get("page") or data.get("page")
    if payload.get("pageFile") or not data.get("pageFile"):
        data["pageFile"] = pad_van_page(payload.get("page"), payload.get("pageFile"))
    nu = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    waarde = {k: payload.get(k) or "" for k in SEND_VELDEN}
    h = send_hash(waarde)
    oud = comp.get(key) or {}
    if oud.get("status") == "sent" and oud.get("hash") == h:
        raise ValueError("deze exacte tekst is al verstuurd")
    entry = dict(waarde)
    entry.update({"status": "approved", "hash": h, "approvedAt": nu, "changedAt": nu,
                  "html": payload.get("html") or "",
                  "session": payload.get("session") or "",
                  "approvalId": hashlib.sha256(("%s|%s|%s" % (key, h, time.time())).encode()).hexdigest()[:16]})
    comp[key] = entry
    data["updatedAt"] = nu
    schrijf(p, data)
    return {"ok": True, "statePath": p, "key": key, "hash": h, "approvalId": entry["approvalId"]}


def h_send_revoke(payload):
    """Tekst gewijzigd na de klik, of de reviewer trekt in: akkoord vervalt."""
    p, data, comp, key = _send_entry(payload)
    entry = comp.get(key)
    if not entry or entry.get("status") != "approved":
        return {"ok": True, "key": key, "status": (entry or {}).get("status")}
    nu = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    entry.update({"status": "revoked", "revokedAt": nu, "changedAt": nu,
                  "revokeReason": (payload.get("reason") or "")[:200]})
    data["updatedAt"] = nu
    schrijf(p, data)
    return {"ok": True, "key": key, "status": "revoked"}


def h_send_done(payload):
    """De agent meldt dat hij verstuurd heeft. Alleen met het juiste approvalId + hash."""
    p, data, comp, key = _send_entry(payload)
    entry = comp.get(key) or {}
    if entry.get("status") != "approved":
        raise ValueError("geen geldig akkoord (status: %s)" % entry.get("status"))
    if payload.get("approvalId") != entry.get("approvalId") or payload.get("hash") != entry.get("hash"):
        raise ValueError("approvalId/hash klopt niet met het vastgelegde akkoord")
    nu = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    entry.update({"status": "sent", "sentAt": nu, "changedAt": nu,
                  "sentVia": (payload.get("via") or "")[:200]})
    data["updatedAt"] = nu
    schrijf(p, data)
    return {"ok": True, "key": key, "status": "sent"}


# Welke herkomst een route eist. "page": alleen een browserpagina die de bridge zelf
# serveert (Origin = de bridge). "local": alleen een niet-browserproces (geen Origin):
# een browser zet op elke cross-origin POST een Origin-header, dus een website kan
# deze routes niet aanroepen.
HERKOMST = {"/send-approve": "page", "/send-revoke": "page", "/send-done": "local"}


ROUTES = {"/session": h_session, "/save": h_save, "/delete": h_delete,
          "/remove-all": h_remove_all, "/resolve": h_resolve,
          "/state": h_state, "/state-save": h_state_save,
          "/sessie": h_sessie,
          "/send-approve": h_send_approve, "/send-revoke": h_send_revoke,
          "/send-done": h_send_done}


class Handler(BaseHTTPRequestHandler):
    server_version = "HtmlAnnotatorBridge/%s" % __version__

    def log_message(self, fmt, *args):
        # Origin/Referer meeloggen: dat is de enige manier om vast te stellen vanaf welke
        # origin een ingebedde weergave (preview-pane, sideviewer) de bridge aanroept.
        # Without that value every claim about it is an assumption. See CRITERIA.md B17.
        try:
            herkomst = self.headers.get("Origin") or self.headers.get("Referer") or ""
        except Exception:
            herkomst = ""
        sys.stderr.write("[bridge] %s%s\n" % (fmt % args, (" origin=%s" % herkomst) if herkomst else ""))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _bestand(self, pad):
        """Serveert een lokaal bestand, zodat de pagina same-origin met de bridge draait."""
        if not os.path.isfile(pad):
            return self._json(404, {"ok": False, "error": "bestand niet gevonden: %s" % pad})
        soort = {
            ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
            ".json": "application/json; charset=utf-8",
        }.get(os.path.splitext(pad)[1].lower(), "application/octet-stream")
        with open(pad, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", soort)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        pad = self.path.split("?")[0]
        if pad == "/ping":
            # "version" is the wire protocol the snippet talks; "release" is
            # the package version (html_annotator.__version__).
            return self._json(200, {"ok": True, "bridge": "html-annotator",
                                    "version": 2, "release": __version__,
                                    "root": ROOT, "pillow": HEEFT_PILLOW})
        # /p/<pad-vanaf-home> serveert een lokale pagina same-origin met de bridge.
        # Voorbeeld: http://127.0.0.1:8791/p/Desktop/todos.html
        if pad.startswith("/p/"):
            # URL-pad is altijd met forward slashes; op Windows maakt Path daar
            # backslashes van. Nooit buiten de home-map serveren.
            rel = urllib.parse.unquote(pad[3:])
            home = Path.home().resolve()
            doel = Path(home, *[d for d in rel.split("/") if d]).resolve()
            if home not in doel.parents:
                return self._json(403, {"ok": False, "error": "pad buiten home"})
            return self._bestand(str(doel))
        self._json(404, {"ok": False, "error": "onbekend pad"})

    def do_POST(self):
        pad = self.path.split("?")[0]
        fn = ROUTES.get(pad)
        if not fn:
            return self._json(404, {"ok": False, "error": "onbekend pad"})
        eis = HERKOMST.get(pad)
        if eis:
            origin = self.headers.get("Origin")
            eigen = {"http://%s:%d" % (HOST, PORT), "http://localhost:%d" % PORT}
            if eis == "page" and origin not in eigen:
                return self._json(403, {"ok": False, "error": "alleen vanuit een /p/-pagina van deze bridge"})
            if eis == "local" and origin is not None:
                return self._json(403, {"ok": False, "error": "niet vanuit een browser"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            return self._json(400, {"ok": False, "error": "ongeldige body: %s" % e})
        try:
            with LOCK:
                self._json(200, fn(payload))
        except ValueError as e:
            # verkeerde of ontbrekende invoer is een clientfout, geen serverfout
            self._json(400, {"ok": False, "error": str(e)[:300]})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)[:300]})


class BridgeServer(ThreadingHTTPServer):
    """HTTPServer.server_bind calls socket.getfqdn(), a reverse-DNS lookup that can hang
    for half a minute on hosts without working reverse DNS (seen on macOS CI runners).
    The bridge only ever listens on a loopback IP, so the name is known up front."""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


def main():
    try:
        os.makedirs(ROOT, exist_ok=True)
        srv = BridgeServer((HOST, PORT), Handler)
    except Exception:
        import traceback
        print("html-annotator bridge failed to start on http://%s:%d" % (HOST, PORT), flush=True)
        traceback.print_exc()
        sys.stderr.flush()
        raise
    print("html-annotator %s listening on http://%s:%d (root: %s, pillow: %s)"
          % (__version__, HOST, PORT, ROOT, HEEFT_PILLOW), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.", flush=True)


if __name__ == "__main__":
    main()
