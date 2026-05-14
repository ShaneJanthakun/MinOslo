"""
MinOslo.no — Flask + Gunicorn
==============================
Start:   gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60
Lokalt:  python app.py

Datakilder:
  • Politiloggen  — api.politiet.no (JSON, 48t)
  • Oslo kommune  — aktuelt.oslo.kommune.no (HTML-skraping)
  • NRK Stor-Oslo — nrk.no/stor-oslo/toppsaker.rss
  • eInnsyn       — einnsyn.no/rss
  • Ruter status  — Entur GraphQL API (åpent, ingen nøkkel)
  • Vær           — MET.no Locationforecast 2.0
"""

import os, re, html as _html, logging, json
from datetime import datetime, timezone, timedelta
from threading import Lock

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("minoslo")
app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════
# NORSK TID (ingen ekstern avhengighet)
# ═══════════════════════════════════════════════════════════════
def _nå() -> datetime:
    u = datetime.now(timezone.utc)
    off = 2 if (
        datetime(u.year, 3, 25, 1, tzinfo=timezone.utc) <= u <
        datetime(u.year, 10, 25, 1, tzinfo=timezone.utc)
    ) else 1
    return u.astimezone(timezone(timedelta(hours=off)))

_TZ = _nå().tzinfo

# ═══════════════════════════════════════════════════════════════
# HEADERS — tre sett for tre formål
# ═══════════════════════════════════════════════════════════════
_UA_BOT     = "MinOsloBot/1.0 (shanebusiness99@gmail.com)"
_UA_BROWSER = "Mozilla/5.0 (compatible; MinOsloBot/1.0)"

# MET.no og Politiet krever identifiserende UA — ellers 403/429
HDRS_BOT = {
    "User-Agent": _UA_BOT,
    "Accept": "application/json, */*",
}

# RSS-feeds: browser UA + XML accept
HDRS_RSS = {
    "User-Agent": _UA_BROWSER,
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "nb-NO,nb;q=0.9",
}

# HTML-skraping: browser UA
HDRS_HTML = {
    "User-Agent": _UA_BROWSER,
    "Accept": "text/html,*/*",
    "Accept-Language": "nb-NO,nb;q=0.9",
}

# OSM Nominatim: identifiserende UA (påkrevd av ToS)
HDRS_OSM = {"User-Agent": _UA_BOT}

TIMEOUT = 7

# ═══════════════════════════════════════════════════════════════
# OSLO-FILTER
# ═══════════════════════════════════════════════════════════════
OSLO_RE = re.compile(
    r"\b("
    r"Oslo|Grünerløkka|Frogner|Sagene|Majorstuen|Majorstua|"
    r"Alna|Bjerke|Grorud|Nordstrand|Nordre Aker|Vestre Aker|"
    r"Østensjø|Stovner|Gamle Oslo|St\.?\s*Hanshaugen|Hanshaugen|"
    r"Sentrum|Bislett|Tøyen|Grønland|Holmlia|Manglerud|"
    r"Lambertseter|Skullerud|Mortensrud|Romsås|Furuset|"
    r"Ellingsrud|Haugerud|Røa|Vinderen|Slemdal|Grefsen|"
    r"Kjelsås|Nydalen|Sandaker|Torshov|Sinsen|Storo|"
    r"Ullevål|Rikshospitalet|Gaustad|Homansbyen|Solli|"
    r"Skøyen|Lysaker|Bygdøy|Aker Brygge|Tjuvholmen|"
    r"Vippetangen|Bjørvika|Sørenga|Gamlebyen|Kampen|"
    r"Vålerenga|Etterstad|Helsfyr|Bryn|Brynseng|Ensjø|"
    r"Teisen|Løren|Alfaset|Lindeberg|Trosterud|Rommen|"
    r"Ammerud|Haugenstua|Fossum|Kalbakken|Vestli|"
    r"Rødtvet|Veitvet|Karl Johans|Rådhuset|Stortorvet|Ullern"
    r")\b", re.I
)

EKSKL = re.compile(
    r"\b("
    r"utenriks|verden|internasjonal|Europa|USA|Russland|Ukraina|"
    r"Israel|Gaza|Kina|Storbritannia|Premier.?League|Champions League|"
    r"Eliteserien|landslaget|Nobel|Stortinget|regjeringen|"
    r"statsminister|Finansdepartement|fjellbygd|Viken|"
    r"Trondheim|Bergen|Stavanger|Tromsø|Bodø|Drammen|"
    r"Ringerike|Hamar|Lillehammer|Fredrikstad|Sarpsborg|Moss|Halden"
    r")\b", re.I
)

GATE_RE = re.compile(
    r"\b([A-ZÆØÅ][a-zæøå]+"
    r"(?:gate|gata|vei|veien|allé|alléen|plass|plassen|"
    r"torg|torget|brygge|bryggen|kaia|kaien|bakke|bakken|"
    r"løkka|parken|stien)"
    r"(?:\s+\d+[A-Za-z]?)?)\b",
    re.U,
)

def _oslo_ok(tittel: str, desc: str) -> bool:
    t = f"{tittel} {desc}"
    if EKSKL.search(t):
        return False
    return bool(OSLO_RE.search(t))

# ═══════════════════════════════════════════════════════════════
# HJELPERE
# ═══════════════════════════════════════════════════════════════
def _rens(t: str) -> str:
    if not t: return ""
    t = _html.unescape(t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()

def _parse_dato(s: str) -> datetime | None:
    if not s: return None
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(_TZ)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_TZ)
    except Exception:
        return None

def _dstr(dt: datetime | None, raa: str = "") -> str:
    return dt.strftime("%-d. %b %Y, %H:%M") if dt else (raa[:10] or "–")

def _cache_gyldig(ts: datetime | None, sekunder: int) -> bool:
    """Bruk total_seconds() — .seconds returnerer bare 0–59."""
    return bool(ts and (_nå() - ts).total_seconds() < sekunder)

# ═══════════════════════════════════════════════════════════════
# KARTBILDER — statisk PNG, ingen iframe, ingen zoom
# ═══════════════════════════════════════════════════════════════
_osm_cache: dict[str, str | None] = {}
_osm_lock = Lock()

def _osm_png(adresse: str) -> str | None:
    with _osm_lock:
        if adresse in _osm_cache:
            return _osm_cache[adresse]
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{adresse}, Oslo, Norway", "format": "json", "limit": 1},
            headers=HDRS_OSM, timeout=3,
        )
        hits = r.json()
        if not hits:
            with _osm_lock: _osm_cache[adresse] = None
            return None
        lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
        url = (
            f"https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={lat},{lon}&zoom=16&size=900x506"
            f"&markers={lat},{lon},red-pushpin"
        )
        with _osm_lock: _osm_cache[adresse] = url
        return url
    except Exception as e:
        log.warning(f"OSM '{adresse}': {e}")
        with _osm_lock: _osm_cache[adresse] = None
        return None

def _berik_bilde(art: dict) -> dict:
    """Kart KUN ved gjenkjent adresse — ingen generelle bilder."""
    if art.get("bilde_url", "").startswith("http"):
        return art
    tekst = f"{art.get('overskrift','')} {art.get('ingress','')}"
    for gate in GATE_RE.findall(tekst):
        url = _osm_png(gate)
        if url:
            return {**art, "bilde_url": url}
    return {**art, "bilde_url": ""}

# ═══════════════════════════════════════════════════════════════
# VÆR  (MET.no Locationforecast 2.0)
# ═══════════════════════════════════════════════════════════════
_vær_data: dict = {}
_vær_ts:   datetime | None = None
_vær_lock = Lock()

_EMOJI = {
    "clearsky": "☀️", "fair": "🌤️", "partlycloudy": "⛅",
    "cloudy": "☁️", "fog": "🌫️", "lightrain": "🌦️",
    "rain": "🌧️", "heavyrain": "⛈️", "lightsnow": "🌨️",
    "snow": "❄️", "sleet": "🌨️", "thunder": "⛈️",
}

def _hent_vær() -> dict:
    global _vær_data, _vær_ts
    with _vær_lock:
        if _cache_gyldig(_vær_ts, 1800):
            return _vær_data
    try:
        r = requests.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": "59.9139", "lon": "10.7522"},
            headers={"User-Agent": _UA_BOT},   # MET krever identifiserende UA
            timeout=6,
        )
        r.raise_for_status()
        d  = r.json()["properties"]["timeseries"][0]["data"]
        sym = d.get("next_1_hours", {}).get("summary", {}).get("symbol_code", "")
        tmp = round(d["instant"]["details"].get("air_temperature", 0))
        res = {"temp": tmp, "emoji": next((v for k, v in _EMOJI.items() if k in sym), "🌡️")}
        log.info(f"Vær: {tmp}° {sym}")
        with _vær_lock:
            _vær_data, _vær_ts = res, _nå()
        return res
    except Exception as e:
        log.error(f"VÆR FEIL: {type(e).__name__}: {e}")
        with _vær_lock:
            return _vær_data if _vær_data else {"temp": "–", "emoji": "🌡️"}

# ═══════════════════════════════════════════════════════════════
# RUTER TRAFIKKSTATUS  (Entur åpent GraphQL)
#
# Entur drifter all kollektivdata i Norge. API-et er åpent,
# ingen API-nøkkel nødvendig for leseoperasjoner.
# Vi henter aktive «situasjoner» (avvik) for Oslo-regionen.
# ═══════════════════════════════════════════════════════════════
_ruter_data: dict = {}
_ruter_ts:   datetime | None = None
_ruter_lock = Lock()

_ENTUR_GQL = "https://api.entur.io/realtime/v1/graphql"

_ENTUR_QUERY = """
{
  situations(codespaces: ["RUT"]) {
    id
    summary { value language }
    description { value language }
    severity
    reportType
    validityPeriod { startTime endTime }
    affects {
      lines { id name publicCode transportMode }
    }
  }
}
"""

def _hent_ruter_status() -> dict:
    """
    Henter aktive driftsavvik for Ruter-linjer fra Entur sitt åpne GraphQL-API.
    Returnerer dict med:
      ok: bool     — True hvis ingen alvorlige avvik
      avvik: list  — liste med avvik-dicts
      oppdatert: str
    """
    global _ruter_data, _ruter_ts
    with _ruter_lock:
        if _cache_gyldig(_ruter_ts, 300):  # 5-minutters cache
            return _ruter_data
    try:
        r = requests.post(
            _ENTUR_GQL,
            json={"query": _ENTUR_QUERY},
            headers={
                "User-Agent": _UA_BOT,
                "Content-Type": "application/json",
                "ET-Client-Name": "minoslo-newsapp",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        situations = r.json().get("data", {}).get("situations", []) or []

        avvik = []
        nå = _nå()
        for s in situations:
            # Filtrer ut utløpte situasjoner
            vp = s.get("validityPeriod", {})
            slutt = vp.get("endTime")
            if slutt:
                slutt_dt = _parse_dato(slutt)
                if slutt_dt and slutt_dt < nå:
                    continue

            # Hent norsk tekst
            def nb(lst):
                if not lst: return ""
                nb_item = next((x for x in lst if x.get("language") == "no"), None)
                return _rens((nb_item or lst[0]).get("value", ""))

            summary = nb(s.get("summary", []))
            desc    = nb(s.get("description", []))
            if not summary:
                continue

            severity = s.get("severity", "").lower()
            lines = s.get("affects", {}).get("lines", []) or []
            linje_navn = ", ".join(
                f"{l.get('publicCode', '')} {l.get('name', '')}".strip()
                for l in lines[:3]
            ) or "Generelt avvik"

            avvik.append({
                "summary":   summary,
                "desc":      desc[:160] + ("…" if len(desc) > 160 else ""),
                "severity":  severity,
                "linjer":    linje_navn,
                "alvorlig":  severity in ("severe", "verysevere", "undefined"),
            })

        avvik.sort(key=lambda x: x["alvorlig"], reverse=True)
        res = {
            "ok":         len(avvik) == 0,
            "avvik":      avvik[:6],
            "oppdatert":  nå.strftime("%H:%M"),
            "antall":     len(avvik),
        }
        log.info(f"Ruter status: {len(avvik)} avvik")
        with _ruter_lock:
            _ruter_data, _ruter_ts = res, nå
        return res
    except Exception as e:
        log.error(f"RUTER FEIL: {type(e).__name__}: {e}")
        with _ruter_lock:
            return _ruter_data if _ruter_data else {
                "ok": None, "avvik": [], "oppdatert": "–", "antall": 0
            }

# ═══════════════════════════════════════════════════════════════
# OSLO KOMMUNE — HTML-skraping
# RSS-feeden er ustabil; skraper nettsiden direkte i stedet.
# ═══════════════════════════════════════════════════════════════
def _hent_oslo_kommune() -> list[dict]:
    url = "https://aktuelt.oslo.kommune.no/"
    try:
        r = requests.get(url, headers=HDRS_HTML, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        artikler = []
        grense = _nå() - timedelta(days=7)

        # Prøv ulike kortstrukturer som Oslo kommune bruker
        selectors = [
            "article",
            ".article-card", ".news-card", ".card",
            '[class*="article"]', '[class*="news"]',
            "li.item", ".list-item",
        ]
        items = []
        for sel in selectors:
            items = soup.select(sel)
            if len(items) >= 2:
                break

        # Fallback: alle <a>-tagger med tittel-klasse
        if not items:
            items = soup.select("a[href]")

        seen = set()
        for item in items[:30]:
            # Finn tittel
            tittel_el = (
                item.find(["h1","h2","h3","h4"])
                or item.find(class_=re.compile(r"title|heading|overskrift", re.I))
                or (item if item.name == "a" else None)
            )
            if not tittel_el:
                continue
            tittel = _rens(tittel_el.get_text())
            if not tittel or len(tittel) < 10:
                continue
            if tittel in seen:
                continue
            seen.add(tittel)

            # Finn lenke
            a_tag = item.find("a") if item.name != "a" else item
            lenke = ""
            if a_tag and a_tag.get("href"):
                href = a_tag["href"]
                lenke = href if href.startswith("http") else f"https://aktuelt.oslo.kommune.no{href}"

            # Finn ingress/intro
            ingress_el = item.find(
                class_=re.compile(r"ingress|intro|lead|desc|summary|preamble|manchet", re.I)
            ) or item.find("p")
            ingress = _rens(ingress_el.get_text()) if ingress_el else ""
            ingress = ingress[:240] + ("…" if len(ingress) > 240 else "")

            art = {
                "overskrift":  tittel,
                "ingress":     ingress,
                "publisert":   _nå().strftime("%-d. %b %Y"),
                "kilde_url":   lenke or url,
                "kilde_navn":  "Oslo kommune",
                "kilde_tekst": "Les hos Oslo kommune",
                "badge":       "K",
                "badge_farge": "#1a6632",
                "kategori":    "kommune",
                "bilde_url":   "",
                "dt":          _nå() - timedelta(minutes=30),
            }
            artikler.append(_berik_bilde(art))

            if len(artikler) >= 10:
                break

        log.info(f"Oslo kommune: {len(artikler)} artikler (HTML-skraping)")
        return artikler
    except Exception as e:
        log.error(f"OSLO KOMMUNE FEIL: {type(e).__name__}: {e}")
        # Fallback: prøv RSS
        return _hent_oslo_rss()

def _hent_oslo_rss() -> list[dict]:
    """RSS-fallback for Oslo kommune."""
    for url in [
        "https://aktuelt.oslo.kommune.no/?format=rss",
        "https://www.oslo.kommune.no/rss/",
    ]:
        try:
            r = requests.get(url, headers=HDRS_RSS, timeout=TIMEOUT)
            if not r.ok or "<" not in r.text:
                continue
            soup  = BeautifulSoup(r.text, "lxml-xml")
            items = soup.find_all("item")
            if not items:
                continue
            grense = _nå() - timedelta(days=7)
            ut = []
            for item in items[:10]:
                tittel = _rens((item.find("title") or {}).get_text() if item.find("title") else "")
                if not tittel: continue
                desc  = _rens(item.find("description").get_text() if item.find("description") else "")
                lenke = _rens(item.find("link").get_text() if item.find("link") else "")
                pub   = _rens(item.find("pubDate").get_text() if item.find("pubDate") else "")
                dt    = _parse_dato(pub)
                if dt and dt < grense: continue
                ingress = desc[:240] + ("…" if len(desc) > 240 else "")
                art = {
                    "overskrift": tittel, "ingress": ingress,
                    "publisert": _dstr(dt, pub), "kilde_url": lenke or url,
                    "kilde_navn": "Oslo kommune", "kilde_tekst": "Les hos Oslo kommune",
                    "badge": "K", "badge_farge": "#1a6632",
                    "kategori": "kommune", "bilde_url": "",
                    "dt": dt or (_nå() - timedelta(hours=3)),
                }
                ut.append(_berik_bilde(art))
            if ut:
                log.info(f"Oslo kommune RSS: {len(ut)} saker")
                return ut[:10]
        except Exception as e:
            log.warning(f"Oslo RSS feil {url}: {e}")
    return []

# ═══════════════════════════════════════════════════════════════
# POLITILOGGEN
# ═══════════════════════════════════════════════════════════════
def _hent_politi() -> list[dict]:
    url = "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=40"
    try:
        r = requests.get(
            url,
            headers={"User-Agent": _UA_BOT},   # BOT UA — ellers 429
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        raw   = r.json()
        items = raw if isinstance(raw, list) else (
            raw.get("meldinger") or raw.get("data") or raw.get("results") or []
        )
        grense = _nå() - timedelta(hours=48)
        ut = []
        for m in items:
            tittel = _rens(m.get("tittel") or m.get("title") or "")
            tekst  = _rens(m.get("tekst")  or m.get("text")  or m.get("description") or "")
            tidsp  = m.get("tidspunkt") or m.get("publishedOn") or m.get("created") or ""
            sted   = _rens(m.get("sted") or m.get("location") or "Oslo")
            link   = m.get("url") or m.get("link") or "https://politiloggen.politiet.no"
            dt = _parse_dato(tidsp)
            if dt and dt < grense: continue
            if not _oslo_ok(tittel, tekst): continue
            ut.append({
                "tittel": tittel or tekst[:60] or "Politimelding",
                "tekst":  tekst or tittel,
                "tid":    _dstr(dt, tidsp),
                "sted":   sted,
                "url":    link,
                "dt":     dt or (_nå() - timedelta(hours=24)),
            })
        ut.sort(key=lambda x: x["dt"], reverse=True)
        log.info(f"Politiloggen: {len(ut)} meldinger")
        return ut[:20]
    except Exception as e:
        log.error(f"POLITILOGG FEIL: {type(e).__name__}: {e}")
        return []

# ═══════════════════════════════════════════════════════════════
# RSS-HENTING (NRK + eInnsyn)
# ═══════════════════════════════════════════════════════════════
KILDER_RSS = [
    {
        "id": "nrk",
        # FIX: toppsaker.rss er den fungerende URL-en for NRK Stor-Oslo
        "url": "https://www.nrk.no/stor-oslo/toppsaker.rss",
        "url_alt": [],
        "navn": "NRK", "badge": "N", "farge": "#c8001e",
        "kategori": "nrk", "max_alder": timedelta(days=7),
        "link": "https://www.nrk.no/stor-oslo/", "oslo_filter": True,
    },
    {
        "id": "einnsyn",
        "url": "https://einnsyn.no/rss?q=Oslo+kommune&antall=20",
        "url_alt": [],
        "navn": "eInnsyn", "badge": "E", "farge": "#4a3580",
        "kategori": "einnsyn", "max_alder": timedelta(days=7),
        "link": "https://einnsyn.no", "oslo_filter": False,
    },
]

def _hent_rss(kilde: dict) -> list[dict]:
    alle_url = [kilde["url"]] + kilde.get("url_alt", [])
    xml = ""
    for url in alle_url:
        try:
            r = requests.get(url, headers=HDRS_RSS, timeout=TIMEOUT)
            if r.ok and "<" in r.text:
                xml = r.text
                log.info(f"{kilde['navn']} hentet fra {url}")
                break
            log.warning(f"{kilde['navn']} HTTP {r.status_code} fra {url}")
        except Exception as e:
            log.warning(f"{kilde['navn']} feil {url}: {e}")
    if not xml:
        log.error(f"{kilde['navn']}: ingen URL svarte")
        return []
    try:
        soup  = BeautifulSoup(xml, "lxml-xml")
        items = soup.find_all("item") or soup.find_all("entry")
        grense = _nå() - kilde["max_alder"]
        ut = []
        for item in items:
            def g(*tags):
                for t in tags:
                    n = item.find(t)
                    if n and n.get_text(strip=True):
                        return _rens(n.get_text())
                return ""
            tittel = g("title")
            if not tittel: continue
            desc  = g("description", "summary", "content")
            pub   = g("pubDate", "published", "updated", "dc:date")
            lenke = g("link")
            if not lenke:
                lt = item.find("link")
                if lt: lenke = lt.get("href", "") or _rens(lt.get_text())
            dt = _parse_dato(pub)
            if dt and dt < grense: continue
            if kilde.get("oslo_filter") and not _oslo_ok(tittel, desc): continue
            ingress = desc[:280].rstrip()
            if len(desc) > 280: ingress += "…"
            art = {
                "overskrift":  tittel,
                "ingress":     ingress,
                "publisert":   _dstr(dt, pub),
                "kilde_url":   lenke or kilde["link"],
                "kilde_navn":  kilde["navn"],
                "kilde_tekst": f"Les hos {kilde['navn']}",
                "badge":       kilde["badge"],
                "badge_farge": kilde["farge"],
                "kategori":    kilde.get("kategori", "annet"),
                "bilde_url":   "",
                "dt":          dt or (_nå() - timedelta(hours=6)),
            }
            ut.append(_berik_bilde(art))
        ut.sort(key=lambda x: x["dt"], reverse=True)
        log.info(f"{kilde['navn']}: {len(ut)} saker")
        return ut[:14]
    except Exception as e:
        log.error(f"{kilde['navn']} parse {type(e).__name__}: {e}")
        return []

# ═══════════════════════════════════════════════════════════════
# HOVED-CACHE (5 min, total_seconds())
# ═══════════════════════════════════════════════════════════════
_cache: dict = {"politi": [], "nyheter": [], "ts": None}
_cache_lock = Lock()

PLACEHOLDER = [
    {"overskrift": "Oslos beste turtips denne helgen",
     "ingress": "Oslomarka tilbyr fantastiske turer for alle nivåer.",
     "publisert": "i dag", "kilde_url": "https://ut.no",
     "kilde_navn": "ut.no", "kilde_tekst": "Les hos ut.no",
     "badge": "T", "badge_farge": "#1a6632", "bilde_url": "",
     "dt": _nå() - timedelta(hours=1)},
    {"overskrift": "Hva skjer i Oslo denne uken?",
     "ingress": "Konserter, markeder og utstillinger — sjekk Visit Oslo.",
     "publisert": "i dag", "kilde_url": "https://visitoslo.com",
     "kilde_navn": "Visit Oslo", "kilde_tekst": "Les hos Visit Oslo",
     "badge": "V", "badge_farge": "#1a4f8a", "bilde_url": "",
     "dt": _nå() - timedelta(hours=2)},
    {"overskrift": "Ruter: Slik reiser du smartest i Oslo",
     "ingress": "T-bane, trikk og buss for alle bydeler — last ned Ruter-appen.",
     "publisert": "i dag", "kilde_url": "https://ruter.no",
     "kilde_navn": "Ruter", "kilde_tekst": "Les hos Ruter",
     "badge": "R", "badge_farge": "#8a1a1a", "bilde_url": "",
     "dt": _nå() - timedelta(hours=3)},
]

def _hent_alt(force: bool = False) -> dict:
    global _cache
    with _cache_lock:
        if not force and _cache_gyldig(_cache.get("ts"), 300):
            return _cache
    nyheter = []
    nyheter.extend(_hent_oslo_kommune())
    for k in KILDER_RSS:
        nyheter.extend(_hent_rss(k))
    nyheter.sort(key=lambda x: x["dt"], reverse=True)
    result = {
        "politi":  _hent_politi(),
        "nyheter": nyheter if nyheter else list(PLACEHOLDER),
        "ts":      _nå(),
    }
    with _cache_lock:
        _cache = result
    return result

# ═══════════════════════════════════════════════════════════════
# HTML-MAL
# Estetikk: editorial avis — Libre Baskerville serif display,
# Source Sans Pro for brødtekst, Oslo-rødt som skarp aksent.
# ALL tekst er slate-900 / gray-800 for maksimal lesbarhet.
# ═══════════════════════════════════════════════════════════════
HTML = r"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MinOslo — Oslo i dag</title>
<meta name="description" content="Ferske nyheter, politilogg, trafikkstatus og vær for Oslo.">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,700;1,400&family=Source+Sans+3:wght@300;400;600;700&display=swap" rel="stylesheet">
<script>
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: {
          display: ['"Libre Baskerville"', 'Georgia', 'serif'],
          body:    ['"Source Sans 3"', 'system-ui', 'sans-serif'],
        },
        colors: { oslo: '#c8001e', 'oslo-d': '#a0001a' }
      }
    }
  }
</script>
<style>
  body { font-family: 'Source Sans 3', system-ui, sans-serif; }

  /* Stagger fade-up for kort */
  @keyframes fadeUp {
    from { opacity:0; transform:translateY(14px) }
    to   { opacity:1; transform:translateY(0) }
  }
  .fi { animation: fadeUp .38s ease both }
  .fi:nth-child(1)   { animation-delay:.04s }
  .fi:nth-child(2)   { animation-delay:.09s }
  .fi:nth-child(3)   { animation-delay:.14s }
  .fi:nth-child(4)   { animation-delay:.19s }
  .fi:nth-child(5)   { animation-delay:.24s }
  .fi:nth-child(n+6) { animation-delay:.30s }

  /* Live-puls */
  @keyframes pr { 0%,100%{opacity:1} 50%{opacity:.08} }
  .pr { animation: pr 1.5s ease infinite }

  /* Ruter status blink */
  @keyframes blink-y { 0%,100%{opacity:1} 50%{opacity:.45} }
  .blink-y { animation: blink-y 2s ease infinite }

  html { scroll-behavior: smooth }

  /* Scrollbar */
  ::-webkit-scrollbar { width:5px }
  ::-webkit-scrollbar-thumb { background:#d1d5db; border-radius:3px }

  /* Garantert mørk tekst — override alt */
  .dark-txt   { color: #1e293b !important }   /* slate-800 */
  .body-txt   { color: #334155 !important }   /* slate-700 */
  .muted-txt  { color: #64748b !important }   /* slate-500 */
</style>
</head>
<body class="bg-slate-50" style="color:#1e293b">

<!-- ══ HEADER ════════════════════════════════════════════════ -->
<header class="sticky top-0 z-50 bg-white border-b-[3px] border-oslo"
        style="box-shadow:0 1px 6px rgba(0,0,0,.08)">
  <div class="max-w-screen-xl mx-auto px-4 sm:px-6 h-[52px]
              flex items-center justify-between gap-3">

    <!-- Logo -->
    <a href="/" onclick="location.reload();return false;"
       class="flex items-center gap-2 group shrink-0" title="MinOslo">
      <svg width="30" height="24" viewBox="0 0 30 24" fill="none" aria-hidden="true"
           class="text-oslo group-hover:scale-110 transition-transform duration-200">
        <polygon points="0,23 3.5,16 7,23" fill="currentColor" opacity=".9"/>
        <rect x="9"   y="8"  width="2.8" height="15" rx=".4" fill="currentColor"/>
        <rect x="13"  y="4"  width="2.8" height="19" rx=".4" fill="currentColor"/>
        <rect x="17"  y="11" width="2.8" height="12" rx=".4" fill="currentColor"/>
        <rect x="21"  y="6"  width="2.8" height="17" rx=".4" fill="currentColor"/>
        <rect x="25.5" y="13" width="3.5" height="10" rx=".4" fill="currentColor"/>
        <line x1="0" y1="23" x2="30" y2="23" stroke="currentColor" stroke-width="1.5"/>
      </svg>
      <span class="font-display font-bold text-[1.3rem] leading-none italic text-oslo">
        Min<span class="not-italic dark-txt">Oslo</span>
      </span>
    </a>

    <!-- Desktop nav -->
    <nav class="hidden md:flex items-center gap-5 text-[11px] font-bold
                tracking-widest uppercase muted-txt">
      <a href="#nyheter"    class="hover:text-oslo transition-colors">Nyheter</a>
      <a href="#ruter"      class="hover:text-oslo transition-colors">Trafikk</a>
      <a href="#politilogg" class="hover:text-oslo transition-colors">Politilogg</a>
      <button onclick="oppdater()"
              class="hover:text-oslo transition-colors cursor-pointer bg-transparent border-0 p-0 font-bold text-[11px] tracking-widest uppercase muted-txt">
        Oppdater
      </button>
    </nav>

    <!-- Høyre: Vær + Ruter-puls -->
    <div class="flex items-center gap-2 shrink-0">
      <!-- Vær-widget -->
      <div id="vær-widget"
           class="flex items-center gap-1.5 bg-slate-50 border border-slate-200
                  rounded-full px-3 py-1 text-sm font-bold dark-txt min-w-[66px]">
        <span id="w-emoji" class="leading-none">–</span>
        <span id="w-temp"  class="tabular-nums">–°</span>
      </div>
      <!-- Ruter status-indikator (pulserende prikk) -->
      <div id="ruter-dot-wrap"
           class="hidden md:flex items-center gap-1.5 bg-slate-50 border
                  rounded-full px-3 py-1 text-[11px] font-bold min-w-[72px]
                  border-slate-200 dark-txt"
           title="Trafikkstatus">
        <span id="ruter-dot" class="w-2 h-2 rounded-full bg-slate-300 shrink-0"></span>
        <span id="ruter-dot-txt">–</span>
      </div>
    </div>
  </div>
</header>

<main class="max-w-screen-xl mx-auto px-4 sm:px-6 py-6">

  <!-- ══ RUTER TRAFIKKSTATUS ═══════════════════════════════ -->
  <section id="ruter" class="mb-7">
    <div class="flex items-center gap-2 mb-3">
      <span class="pr w-2 h-2 rounded-full bg-oslo inline-block shrink-0"></span>
      <h2 class="font-display font-bold text-lg dark-txt">Trafikkstatus</h2>
      <span class="text-[10px] font-bold tracking-widest uppercase text-oslo">
        Ruter Oslo
      </span>
      <span class="ml-auto text-[10px] muted-txt font-mono" id="ruter-tid">{{ ruter.oppdatert }}</span>
    </div>

    {% if ruter.ok is none %}
    <div class="bg-white border border-slate-200 rounded-xl p-4 text-sm body-txt">
      Trafikkstatus ikke tilgjengelig akkurat nå.
      <a href="https://ruter.no/reise/trafikkinfo/" target="_blank"
         class="text-oslo border-b border-oslo ml-1">Sjekk Ruter direkte ↗</a>
    </div>

    {% elif ruter.ok %}
    <div class="flex items-center gap-3 bg-emerald-50 border border-emerald-200
                rounded-xl px-4 py-3">
      <span class="text-2xl">✅</span>
      <div>
        <p class="font-bold text-emerald-800 text-sm">Alt i rute</p>
        <p class="text-emerald-700 text-xs">Ingen registrerte driftsavvik på Ruter-nettet.</p>
      </div>
      <a href="https://ruter.no/reise/trafikkinfo/" target="_blank"
         class="ml-auto text-[11px] font-bold text-emerald-700 border-b border-emerald-400 shrink-0">
        Ruter ↗
      </a>
    </div>

    {% else %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {% for a in ruter.avvik %}
      <div class="fi bg-white rounded-xl border overflow-hidden
                  {% if a.alvorlig %}border-red-300{% else %}border-amber-200{% endif %}">
        <div class="px-4 py-2 text-[10px] font-bold tracking-wider uppercase
                    {% if a.alvorlig %}bg-red-50 text-red-700{% else %}bg-amber-50 text-amber-700{% endif %}">
          {% if a.alvorlig %}⚠️ Alvorlig avvik{% else %}ℹ️ Driftsmelding{% endif %}
          <span class="ml-2 font-normal normal-case">{{ a.linjer }}</span>
        </div>
        <div class="p-4">
          <p class="font-bold text-sm dark-txt leading-snug mb-1">{{ a.summary }}</p>
          {% if a.desc %}
          <p class="text-xs body-txt leading-relaxed">{{ a.desc }}</p>
          {% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
    <div class="mt-2 text-right">
      <a href="https://ruter.no/reise/trafikkinfo/" target="_blank"
         class="text-[11px] font-bold text-oslo border-b border-oslo">
        Se alle avvik hos Ruter ↗
      </a>
    </div>
    {% endif %}
  </section>

  <!-- ══ NYHETER ═══════════════════════════════════════════ -->
  <section id="nyheter">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2.5">
        <h2 class="font-display font-bold text-xl dark-txt">Siste nytt</h2>
        <span class="text-[10px] font-bold tracking-widest uppercase muted-txt">Oslo</span>
      </div>
      <span class="text-xs font-mono muted-txt">{{ oppdatert }}</span>
    </div>

    {% if nyheter %}

    <!-- HERO -->
    {% set h = nyheter[0] %}
    <article class="fi bg-white rounded-2xl shadow-sm overflow-hidden mb-6
                    hover:shadow-md transition-shadow duration-200 cursor-pointer group"
             onclick="window.open('{{ h.kilde_url }}','_blank')">
      {% if h.bilde_url %}
      <div class="w-full aspect-video overflow-hidden bg-slate-100">
        <img src="{{ h.bilde_url }}" alt=""
             class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-[1.02]"
             onerror="this.parentElement.style.display='none'">
      </div>
      {% endif %}
      <div class="p-5 sm:p-7">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-[10px] font-bold tracking-wider uppercase text-white px-2 py-0.5 rounded"
                style="background:{{ h.badge_farge }}">{{ h.badge }} {{ h.kilde_navn }}</span>
          <span class="text-[11px] font-mono muted-txt">{{ h.publisert }}</span>
        </div>
        <h3 class="font-display font-bold text-2xl sm:text-3xl leading-tight dark-txt mb-3
                   group-hover:text-oslo transition-colors duration-150">
          {{ h.overskrift }}
        </h3>
        <p class="body-txt leading-relaxed text-base line-clamp-3">{{ h.ingress }}</p>
        <span class="inline-block mt-4 text-xs font-bold border-b pb-px
                     text-blue-700 border-blue-400 hover:opacity-70 transition-opacity">
          ↗ {{ h.kilde_tekst }}
        </span>
      </div>
    </article>

    <!-- 3-KOLONNE GRID -->
    {% if nyheter|length > 1 %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {% for art in nyheter[1:] %}
      <article class="fi bg-white rounded-2xl shadow-sm overflow-hidden
                      hover:shadow-md transition-shadow duration-200 cursor-pointer group flex flex-col"
               onclick="window.open('{{ art.kilde_url }}','_blank')">
        {% if art.bilde_url %}
        <div class="w-full aspect-video overflow-hidden bg-slate-100">
          <img src="{{ art.bilde_url }}" alt=""
               class="w-full h-full object-cover rounded-t-xl
                      transition-transform duration-500 group-hover:scale-[1.03]"
               onerror="this.parentElement.style.display='none'">
        </div>
        {% endif %}
        <div class="p-4 flex flex-col flex-1">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-[9px] font-bold tracking-wider uppercase text-white px-1.5 py-0.5 rounded"
                  style="background:{{ art.badge_farge }}">{{ art.badge }} {{ art.kilde_navn }}</span>
            <span class="text-[10px] font-mono muted-txt">{{ art.publisert }}</span>
          </div>
          <h3 class="font-display font-bold text-[1.05rem] leading-snug dark-txt mb-2
                     group-hover:text-oslo transition-colors duration-150 flex-1">
            {{ art.overskrift }}
          </h3>
          <p class="body-txt text-sm leading-relaxed line-clamp-3 mb-3">{{ art.ingress }}</p>
          <span class="text-xs font-bold border-b pb-px w-fit mt-auto
                       text-blue-700 border-blue-400 hover:opacity-70 transition-opacity">
            ↗ {{ art.kilde_tekst }}
          </span>
        </div>
      </article>
      {% endfor %}
    </div>
    {% endif %}

    {% else %}
    <div class="bg-white rounded-2xl shadow-sm p-10 text-center">
      <p class="text-sm muted-txt">Ingen saker hentet akkurat nå. Prøv igjen om litt.</p>
    </div>
    {% endif %}
  </section>

  <!-- ══ POLITILOGG ════════════════════════════════════════ -->
  <section id="politilogg" class="mt-12">
    <div class="flex items-center gap-3 mb-4">
      <span class="pr w-2 h-2 rounded-full bg-oslo inline-block shrink-0"></span>
      <h2 class="font-display font-bold text-xl dark-txt">Politilogg</h2>
      <span class="text-[10px] font-bold tracking-widest uppercase text-oslo">
        Live · siste 48t
      </span>
    </div>

    {% if politi %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {% for p in politi %}
      <a href="{{ p.url }}" target="_blank" rel="noopener"
         class="fi block rounded-2xl p-4 no-underline group
                transition-opacity duration-200 hover:opacity-90"
         style="background:#05101f">
        <div class="flex items-start justify-between gap-3 mb-2">
          <span class="text-[10px] font-mono font-bold text-oslo tracking-wide">
            🚔 {{ p.tid }}
          </span>
          <span class="text-[10px] font-mono shrink-0" style="color:#4a7aaa">
            📍 {{ p.sted }}
          </span>
        </div>
        <p class="text-sm leading-relaxed line-clamp-3 mb-2.5
                  group-hover:opacity-100 transition-opacity"
           style="color:#c8dfff">{{ p.tekst }}</p>
        <span class="text-[10px] font-mono border-b pb-px opacity-70 group-hover:opacity-100"
              style="color:#4a8fd4;border-color:#4a8fd4">↗ Les hos Politiloggen</span>
      </a>
      {% endfor %}
    </div>
    {% else %}
    <div class="rounded-2xl p-8 text-center" style="background:#05101f">
      <p class="text-sm mb-2" style="color:#4a7aaa">Ingen meldinger siste 48 timer.</p>
      <a href="https://politiloggen.politiet.no" target="_blank"
         class="text-xs border-b" style="color:#4a8fd4;border-color:#4a8fd4">
        ↗ Se politiloggen direkte
      </a>
    </div>
    {% endif %}
  </section>

</main>

<!-- ══ FOOTER ════════════════════════════════════════════════ -->
<footer class="mt-16 border-t border-slate-200 bg-white">
  <div class="max-w-screen-xl mx-auto px-4 sm:px-6 py-5
              flex flex-col sm:flex-row items-center justify-between
              gap-3 text-xs muted-txt">
    <span class="font-display font-bold text-sm italic text-oslo">MinOslo</span>
    <span>Politiloggen · Oslo kommune · NRK · eInnsyn · Ruter via Entur</span>
    <span class="font-mono">Oppdateres hvert 5. min</span>
  </div>
</footer>

<!-- ══ SCRIPTS ═══════════════════════════════════════════════ -->
<script>
// ── Vær-widget ──────────────────────────────────────────────
fetch('/api/vaer')
  .then(r => r.json())
  .then(d => {
    document.getElementById('w-emoji').textContent = d.emoji || '🌡️';
    document.getElementById('w-temp').textContent  = d.temp + '°';
  })
  .catch(() => {
    document.getElementById('w-temp').textContent = '–°';
  });

// ── Ruter-status mini-indikator i header ───────────────────
fetch('/api/ruter')
  .then(r => r.json())
  .then(d => {
    const wrap = document.getElementById('ruter-dot-wrap');
    const dot  = document.getElementById('ruter-dot');
    const txt  = document.getElementById('ruter-dot-txt');
    wrap.classList.remove('hidden');
    if (d.ok === true) {
      dot.className = 'w-2 h-2 rounded-full bg-emerald-500 shrink-0';
      txt.textContent = 'I rute';
      wrap.className = wrap.className.replace('border-slate-200', 'border-emerald-200');
    } else if (d.ok === false) {
      dot.className = 'w-2 h-2 rounded-full bg-oslo shrink-0 blink-y';
      txt.textContent = d.antall + ' avvik';
      wrap.className = wrap.className.replace('border-slate-200', 'border-red-200');
    } else {
      txt.textContent = '–';
    }
  })
  .catch(() => {});

// ── Oppdater ────────────────────────────────────────────────
function oppdater() {
  fetch('/api/oppdater', { method: 'POST' })
    .finally(() => location.reload());
}

// Auto-refresh hvert 5. minutt
setTimeout(() => location.reload(), 5 * 60 * 1000);
</script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════
# FLASK-RUTER
# ═══════════════════════════════════════════════════════════════
@app.route("/")
def index():
    data  = _hent_alt()
    ruter = _hent_ruter_status()
    ts    = data["ts"]
    return render_template_string(
        HTML,
        nyheter   = data["nyheter"],
        politi    = data["politi"],
        ruter     = ruter,
        oppdatert = ts.strftime("%H:%M") if ts else "–",
    )

@app.route("/api/vaer")
def api_vaer():
    return jsonify(_hent_vær())

@app.route("/api/ruter")
def api_ruter():
    return jsonify(_hent_ruter_status())

@app.route("/api/oppdater", methods=["POST"])
def api_oppdater():
    _hent_alt(force=True)
    _hent_ruter_status()   # oppdater Ruter-cache også
    return jsonify({"ok": True})

@app.route("/robots.txt")
def robots():
    return "User-agent: *\nDisallow:\n", 200, {"Content-Type": "text/plain"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    _hent_alt()            # varm opp nyhets-cache ved oppstart
    _hent_ruter_status()   # varm opp Ruter-cache
    app.run(host="0.0.0.0", port=port, debug=False)
