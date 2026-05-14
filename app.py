"""
MinOslo.no — Flask + Gunicorn
==============================
Start:   gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60
Lokalt:  python app.py

Datakilder:
  • Oslo kommune  — aktuelt.oslo.kommune.no (HTML-skraping, fleire strategier)
  • NRK Stor-Oslo — nrk.no/stor-oslo/toppsaker.rss
  • eInnsyn       — einnsyn.no/rss
  • Politiloggen  — api.politiet.no (JSON, 48t)
  • Ruter status  — ruter.no/trafikkstatus (HTML-skraping)
  • Vær           — MET.no Locationforecast 2.0
"""

import os, re, html as _html, logging
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
# NORSK TID
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
# HEADERS
# ═══════════════════════════════════════════════════════════════
_UA_BOT = "MinOsloBot/1.0 (shanebusiness99@gmail.com)"

# MET + Politiet: identifiserende UA som forhindrer 403/429
HDRS_BOT = {"User-Agent": _UA_BOT}

# RSS og HTML-skraping: full browser UA
HDRS_WEB = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

TIMEOUT = 8

# ═══════════════════════════════════════════════════════════════
# OSLO-FILTER
# ═══════════════════════════════════════════════════════════════
OSLO_RE = re.compile(
    r"\b(Oslo|Grünerløkka|Frogner|Sagene|Majorstuen|Majorstua|Alna|Bjerke|"
    r"Grorud|Nordstrand|Nordre Aker|Vestre Aker|Østensjø|Stovner|Gamle Oslo|"
    r"St\.?\s*Hanshaugen|Hanshaugen|Sentrum|Bislett|Tøyen|Grønland|Holmlia|"
    r"Manglerud|Lambertseter|Skullerud|Mortensrud|Romsås|Furuset|Ellingsrud|"
    r"Haugerud|Røa|Vinderen|Slemdal|Grefsen|Kjelsås|Nydalen|Sandaker|"
    r"Torshov|Sinsen|Storo|Ullevål|Rikshospitalet|Gaustad|Homansbyen|"
    r"Solli|Skøyen|Lysaker|Bygdøy|Aker Brygge|Tjuvholmen|Vippetangen|"
    r"Bjørvika|Sørenga|Gamlebyen|Kampen|Vålerenga|Etterstad|Helsfyr|"
    r"Bryn|Brynseng|Ensjø|Teisen|Løren|Alfaset|Lindeberg|Trosterud|"
    r"Rommen|Ammerud|Haugenstua|Fossum|Kalbakken|Vestli|Rødtvet|"
    r"Veitvet|Karl Johans|Rådhuset|Stortorvet|Ullern)\b", re.I
)
EKSKL = re.compile(
    r"\b(utenriks|verden|internasjonal|Europa|USA|Russland|Ukraina|"
    r"Israel|Gaza|Kina|Storbritannia|Premier.?League|Champions League|"
    r"Eliteserien|landslaget|Nobel|Stortinget|regjeringen|statsminister|"
    r"Finansdepartement|fjellbygd|Viken|Trondheim|Bergen|Stavanger|"
    r"Tromsø|Bodø|Drammen|Ringerike|Hamar|Lillehammer|Fredrikstad|"
    r"Sarpsborg|Moss|Halden)\b", re.I
)
GATE_RE = re.compile(
    r"\b([A-ZÆØÅ][a-zæøå]+"
    r"(?:gate|gata|vei|veien|allé|alléen|plass|plassen|torg|torget|"
    r"brygge|bryggen|kaia|kaien|bakke|bakken|løkka|parken|stien)"
    r"(?:\s+\d+[A-Za-z]?)?)\b", re.U
)

def _oslo_ok(tittel: str, desc: str) -> bool:
    t = f"{tittel} {desc}"
    return not EKSKL.search(t) and bool(OSLO_RE.search(t))

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
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d",
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

def _cache_ok(ts: datetime | None, sek: int) -> bool:
    """total_seconds() — .seconds gir bare 0-59 og er en klassisk bug."""
    return bool(ts and (_nå() - ts).total_seconds() < sek)

# ═══════════════════════════════════════════════════════════════
# KARTBILDER — statisk PNG fra OSM, ingen iframe
# ═══════════════════════════════════════════════════════════════
_osm_cache: dict[str, str | None] = {}
_osm_lock = Lock()

def _osm_png(adr: str) -> str | None:
    with _osm_lock:
        if adr in _osm_cache:
            return _osm_cache[adr]
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{adr}, Oslo, Norway", "format": "json", "limit": 1},
            headers={"User-Agent": _UA_BOT}, timeout=3,
        )
        hits = r.json()
        if not hits:
            with _osm_lock: _osm_cache[adr] = None
            return None
        lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
        url = (
            f"https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={lat},{lon}&zoom=16&size=900x506"
            f"&markers={lat},{lon},red-pushpin"
        )
        with _osm_lock: _osm_cache[adr] = url
        return url
    except Exception as e:
        log.warning(f"OSM '{adr}': {e}")
        with _osm_lock: _osm_cache[adr] = None
        return None

def _berik(art: dict) -> dict:
    """Legg til statisk kartbilde kun hvis adresse finnes i teksten."""
    if art.get("bilde_url", "").startswith("http"):
        return art
    t = f"{art.get('overskrift','')} {art.get('ingress','')}"
    for gate in GATE_RE.findall(t):
        url = _osm_png(gate)
        if url:
            return {**art, "bilde_url": url}
    return {**art, "bilde_url": ""}

# ═══════════════════════════════════════════════════════════════
# VÆR (MET.no — fungerer med BOT-UA)
# ═══════════════════════════════════════════════════════════════
_vær_data: dict = {}
_vær_ts:   datetime | None = None
_vær_lock = Lock()

_EMOJI_MAP = {
    "clearsky": "☀️", "fair": "🌤️", "partlycloudy": "⛅",
    "cloudy": "☁️", "fog": "🌫️", "lightrain": "🌦️",
    "rain": "🌧️", "heavyrain": "⛈️", "lightsnow": "🌨️",
    "snow": "❄️", "sleet": "🌨️", "thunder": "⛈️",
}

def _hent_vær() -> dict:
    global _vær_data, _vær_ts
    with _vær_lock:
        if _cache_ok(_vær_ts, 1800): return _vær_data
    try:
        r = requests.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": "59.9139", "lon": "10.7522"},
            headers={"User-Agent": _UA_BOT},
            timeout=6,
        )
        r.raise_for_status()
        d   = r.json()["properties"]["timeseries"][0]["data"]
        sym = d.get("next_1_hours", {}).get("summary", {}).get("symbol_code", "")
        tmp = round(d["instant"]["details"].get("air_temperature", 0))
        res = {"temp": tmp, "emoji": next((v for k, v in _EMOJI_MAP.items() if k in sym), "🌡️")}
        log.info(f"Vær: {tmp}° {sym}")
        with _vær_lock: _vær_data, _vær_ts = res, _nå()
        return res
    except Exception as e:
        log.error(f"VÆR FEIL: {type(e).__name__}: {e}")
        with _vær_lock:
            return _vær_data if _vær_data else {"temp": "–", "emoji": "🌡️"}

# ═══════════════════════════════════════════════════════════════
# RUTER TRAFIKKSTATUS — HTML-skraping av ruter.no/trafikkstatus
#
# Strategi 1: skrap ruter.no/trafikkstatus/ direkte
# Strategi 2: Entur GraphQL som backup
# Returnerer alltid et brukbart resultat
# ═══════════════════════════════════════════════════════════════
_ruter_data: dict = {}
_ruter_ts:   datetime | None = None
_ruter_lock = Lock()

def _ruter_scrape() -> dict | None:
    """Skrap ruter.no/trafikkstatus/ med BeautifulSoup."""
    url = "https://ruter.no/trafikkstatus/"
    try:
        r = requests.get(url, headers=HDRS_WEB, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        log.info(f"Ruter HTML lengde: {len(r.text)} tegn")

        avvik = []

        # Strategi A: artikkel/listeelementer med avvik-innhold
        kandidater = (
            soup.find_all("article")
            or soup.find_all(class_=re.compile(r"disruption|deviation|avvik|status|message|alert|incident", re.I))
            or soup.find_all(["li", "div"], class_=re.compile(r"item|card|row|entry", re.I))
        )

        seen = set()
        for el in kandidater[:20]:
            # Finn overskrift
            h = (
                el.find(["h1","h2","h3","h4","h5"])
                or el.find(class_=re.compile(r"title|heading|name", re.I))
            )
            if not h:
                continue
            tittel = _rens(h.get_text())
            if not tittel or len(tittel) < 5 or tittel in seen:
                continue
            seen.add(tittel)

            # Finn beskrivelse
            p = el.find("p") or el.find(class_=re.compile(r"desc|body|text|content", re.I))
            desc = _rens(p.get_text()) if p else ""

            # Bestem alvorlighetsgrad fra klasser/tekst
            klasser = " ".join(el.get("class", []))
            tekst_all = f"{tittel} {desc} {klasser}".lower()
            alvorlig = any(w in tekst_all for w in [
                "innstilt", "stanset", "stoppet", "avlyst", "cancelled",
                "severe", "critical", "error", "feil", "stopp"
            ])

            # Finn linjer (t-bane, buss, trikk)
            linjer = []
            for span in el.find_all(["span", "strong", "b"], limit=5):
                tx = _rens(span.get_text())
                if re.match(r"^[A-Z]?\d{1,3}[A-Z]?$", tx) or any(
                    w in tx.lower() for w in ["t-bane", "buss", "trikk", "linje", "tog"]
                ):
                    linjer.append(tx)
            linje_str = ", ".join(linjer[:3]) or ""

            avvik.append({
                "summary": tittel,
                "desc":    (desc[:200] + "…") if len(desc) > 200 else desc,
                "linjer":  linje_str,
                "alvorlig": alvorlig,
            })

        if avvik:
            log.info(f"Ruter skraping: {len(avvik)} avvik funnet")
            avvik.sort(key=lambda x: x["alvorlig"], reverse=True)
            return {
                "ok": False,
                "avvik": avvik[:6],
                "oppdatert": _nå().strftime("%H:%M"),
                "antall": len(avvik),
                "kilde": "ruter.no",
            }

        # Sjekk om siden sier "alt OK" eksplisitt
        full_text = soup.get_text().lower()
        if any(p in full_text for p in ["alt i rute", "ingen avvik", "normal drift", "no disruptions"]):
            log.info("Ruter: ingen avvik (tekst-match)")
            return {
                "ok": True, "avvik": [],
                "oppdatert": _nå().strftime("%H:%M"),
                "antall": 0, "kilde": "ruter.no",
            }

        # Siden inneholder HTML men vi klarte ikke å parse strukturen
        log.warning(f"Ruter skraping: ingen elementer parstet (HTML-struktur ukjent). Første 500 tegn: {r.text[:500]}")
        return None

    except Exception as e:
        log.error(f"Ruter skraping feil: {type(e).__name__}: {e}")
        return None


def _ruter_entur() -> dict | None:
    """Backup: Entur GraphQL for Ruter-avvik."""
    try:
        query = """
        {
          situations(codespaces: ["RUT"]) {
            id
            summary { value language }
            description { value language }
            severity
            validityPeriod { startTime endTime }
            affects { lines { publicCode name } }
          }
        }
        """
        r = requests.post(
            "https://api.entur.io/realtime/v1/graphql",
            json={"query": query},
            headers={
                "User-Agent": _UA_BOT,
                "Content-Type": "application/json",
                "ET-Client-Name": "minoslo-newsapp",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        situations = r.json().get("data", {}).get("situations", []) or []
        nå = _nå()

        avvik = []
        for s in situations:
            vp = s.get("validityPeriod", {})
            if vp.get("endTime"):
                slutt = _parse_dato(vp["endTime"])
                if slutt and slutt < nå:
                    continue

            def nb(lst):
                if not lst: return ""
                item = next((x for x in lst if x.get("language") in ("no","nb")), None)
                return _rens((item or lst[0]).get("value", ""))

            summary = nb(s.get("summary", []))
            if not summary:
                continue
            desc = nb(s.get("description", []))
            sev  = s.get("severity", "").lower()
            lines = s.get("affects", {}).get("lines", []) or []
            linjer = ", ".join(
                f"{l.get('publicCode','')} {l.get('name','')}".strip()
                for l in lines[:3]
            ) or ""

            avvik.append({
                "summary":  summary,
                "desc":     (desc[:200] + "…") if len(desc) > 200 else desc,
                "linjer":   linjer,
                "alvorlig": sev in ("severe", "verysevere"),
            })

        avvik.sort(key=lambda x: x["alvorlig"], reverse=True)
        log.info(f"Entur Ruter: {len(avvik)} avvik")
        return {
            "ok": len(avvik) == 0,
            "avvik": avvik[:6],
            "oppdatert": nå.strftime("%H:%M"),
            "antall": len(avvik),
            "kilde": "entur",
        }
    except Exception as e:
        log.error(f"Entur backup feil: {type(e).__name__}: {e}")
        return None


def _hent_ruter_status() -> dict:
    global _ruter_data, _ruter_ts
    with _ruter_lock:
        if _cache_ok(_ruter_ts, 300): return _ruter_data

    # Prøv Ruter direkte, deretter Entur som backup
    res = _ruter_scrape() or _ruter_entur()
    if res is None:
        res = {"ok": None, "avvik": [], "oppdatert": "–", "antall": 0, "kilde": "–"}

    with _ruter_lock:
        _ruter_data, _ruter_ts = res, _nå()
    return res

# ═══════════════════════════════════════════════════════════════
# OSLO KOMMUNE — HTML-skraping med tre strategier
#
# aktuelt.oslo.kommune.no er en Enonic CMS-side med server-side
# rendering — fungerer med requests + BeautifulSoup.
# ═══════════════════════════════════════════════════════════════
_kommune_data: list = []
_kommune_ts:   datetime | None = None
_kommune_lock = Lock()

def _hent_oslo_kommune() -> list[dict]:
    global _kommune_data, _kommune_ts
    with _kommune_lock:
        if _cache_ok(_kommune_ts, 300): return _kommune_data

    url = "https://aktuelt.oslo.kommune.no/"
    result = []

    try:
        r = requests.get(url, headers=HDRS_WEB, timeout=TIMEOUT)
        r.raise_for_status()
        html_len = len(r.text)
        log.info(f"Oslo kommune HTML: {html_len} tegn, status {r.status_code}")

        if html_len < 500:
            log.warning("Oslo kommune: respons for kort — mulig JavaScript-side")
        else:
            soup = BeautifulSoup(r.text, "html.parser")

            # ── Strategi 1: article-elementer (mest vanlig i CMS) ──
            articles = soup.find_all("article", limit=20)
            log.info(f"Oslo kommune strategi 1 (article): {len(articles)} elementer")

            if not articles:
                # ── Strategi 2: elementer med artikkel-klasser ──
                articles = (
                    soup.find_all(class_=re.compile(
                        r"article|news[-_]?item|story|post|card|nyhet", re.I
                    ), limit=20)
                )
                log.info(f"Oslo kommune strategi 2 (klasse): {len(articles)} elementer")

            if not articles:
                # ── Strategi 3: alle <a>-lenker som peker på /nyheter/ eller /aktuelt/ ──
                articles = [
                    a for a in soup.find_all("a", href=True)
                    if any(p in a["href"] for p in ["/nyheter", "/aktuelt", "/pressemeldinger", "/article"])
                ][:20]
                log.info(f"Oslo kommune strategi 3 (a[href]): {len(articles)} elementer")

            seen = set()
            for el in articles:
                # Tittel
                h = (
                    el.find(["h1","h2","h3","h4"])
                    or el.find(class_=re.compile(r"title|heading|tittel|overskrift", re.I))
                )
                if el.name == "a" and not h:
                    tittel = _rens(el.get_text())
                elif h:
                    tittel = _rens(h.get_text())
                else:
                    continue

                if not tittel or len(tittel) < 8 or tittel in seen:
                    continue
                seen.add(tittel)

                # Lenke
                a = el.find("a") if el.name != "a" else el
                href = a["href"] if a and a.get("href") else ""
                lenke = (
                    href if href.startswith("http")
                    else f"https://aktuelt.oslo.kommune.no{href}"
                    if href.startswith("/")
                    else url
                )

                # Ingress
                p = el.find("p") or el.find(class_=re.compile(
                    r"ingress|intro|lead|preamble|desc|summary|manchet|teaser", re.I
                ))
                ingress = _rens(p.get_text()) if p else ""
                if len(ingress) > 240:
                    ingress = ingress[:240] + "…"

                art = {
                    "overskrift":  tittel,
                    "ingress":     ingress,
                    "publisert":   _nå().strftime("%-d. %b %Y"),
                    "kilde_url":   lenke,
                    "kilde_navn":  "Oslo kommune",
                    "kilde_tekst": "Les hos Oslo kommune",
                    "badge":       "K",
                    "badge_farge": "#1a6632",
                    "kategori":    "kommune",
                    "bilde_url":   "",
                    "dt":          _nå() - timedelta(minutes=30),
                }
                result.append(_berik(art))
                if len(result) >= 10:
                    break

            log.info(f"Oslo kommune: {len(result)} artikler fra HTML")

    except Exception as e:
        log.error(f"OSLO KOMMUNE FEIL: {type(e).__name__}: {e}")

    # ── Fallback: RSS dersom HTML-skraping gir 0 ──
    if not result:
        log.info("Oslo kommune: prøver RSS-fallback")
        result = _oslo_rss_fallback()

    with _kommune_lock:
        _kommune_data, _kommune_ts = result, _nå()
    return result


def _oslo_rss_fallback() -> list[dict]:
    """Siste utvei: RSS-feed for Oslo kommune."""
    for url in [
        "https://aktuelt.oslo.kommune.no/?format=rss",
        "https://www.oslo.kommune.no/rss/",
    ]:
        try:
            r = requests.get(url, headers=HDRS_WEB, timeout=TIMEOUT)
            if not r.ok or "<" not in r.text:
                log.warning(f"Oslo RSS {url}: HTTP {r.status_code}")
                continue
            soup  = BeautifulSoup(r.text, "lxml-xml")
            items = soup.find_all("item")
            log.info(f"Oslo RSS {url}: {len(items)} items")
            if not items:
                continue
            grense = _nå() - timedelta(days=7)
            ut = []
            for item in items[:10]:
                def gtxt(tag):
                    n = item.find(tag)
                    return _rens(n.get_text()) if n else ""
                tittel = gtxt("title")
                if not tittel: continue
                desc   = gtxt("description")
                pub    = gtxt("pubDate")
                lenke  = gtxt("link")
                dt     = _parse_dato(pub)
                if dt and dt < grense: continue
                ingress = (desc[:240] + "…") if len(desc) > 240 else desc
                art = {
                    "overskrift": tittel, "ingress": ingress,
                    "publisert": _dstr(dt, pub), "kilde_url": lenke or url,
                    "kilde_navn": "Oslo kommune", "kilde_tekst": "Les hos Oslo kommune",
                    "badge": "K", "badge_farge": "#1a6632",
                    "kategori": "kommune", "bilde_url": "",
                    "dt": dt or (_nå() - timedelta(hours=3)),
                }
                ut.append(_berik(art))
            if ut:
                log.info(f"Oslo RSS: {len(ut)} saker")
                return ut[:10]
        except Exception as e:
            log.warning(f"Oslo RSS feil {url}: {e}")
    log.error("Oslo kommune: alle strategier feilet")
    return []

# ═══════════════════════════════════════════════════════════════
# POLITILOGGEN
# ═══════════════════════════════════════════════════════════════
def _hent_politi() -> list[dict]:
    url = "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=40"
    try:
        r = requests.get(url, headers={"User-Agent": _UA_BOT}, timeout=TIMEOUT)
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
# RSS (NRK + eInnsyn)
# ═══════════════════════════════════════════════════════════════
KILDER_RSS = [
    {
        "id": "nrk",
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
            r = requests.get(url, headers=HDRS_WEB, timeout=TIMEOUT)
            if r.ok and "<" in r.text:
                xml = r.text
                log.info(f"{kilde['navn']}: hentet fra {url}")
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
            ut.append(_berik(art))
        ut.sort(key=lambda x: x["dt"], reverse=True)
        log.info(f"{kilde['navn']}: {len(ut)} saker")
        return ut[:14]
    except Exception as e:
        log.error(f"{kilde['navn']} parse-feil: {type(e).__name__}: {e}")
        return []

# ═══════════════════════════════════════════════════════════════
# HOVED-CACHE
# ═══════════════════════════════════════════════════════════════
_cache: dict = {"politi": [], "nyheter": [], "ts": None}
_cache_lock = Lock()

PLACEHOLDER = [
    {"overskrift": "Oslos beste turtips denne helgen",
     "ingress": "Oslomarka tilbyr fantastiske turer for alle nivåer — her er tips for helgen.",
     "publisert": "i dag", "kilde_url": "https://ut.no",
     "kilde_navn": "ut.no", "kilde_tekst": "Les hos ut.no",
     "badge": "T", "badge_farge": "#1a6632", "bilde_url": "",
     "dt": _nå() - timedelta(hours=1)},
    {"overskrift": "Hva skjer i Oslo denne uken?",
     "ingress": "Konserter, markeder og utstillinger — sjekk Visit Oslo for oppdatert program.",
     "publisert": "i dag", "kilde_url": "https://visitoslo.com",
     "kilde_navn": "Visit Oslo", "kilde_tekst": "Les hos Visit Oslo",
     "badge": "V", "badge_farge": "#1a4f8a", "bilde_url": "",
     "dt": _nå() - timedelta(hours=2)},
    {"overskrift": "Ruter: Slik reiser du smartest i Oslo",
     "ingress": "T-bane, trikk og buss dekker hele Oslo — last ned Ruter-appen.",
     "publisert": "i dag", "kilde_url": "https://ruter.no",
     "kilde_navn": "Ruter", "kilde_tekst": "Les hos Ruter",
     "badge": "R", "badge_farge": "#8a1a1a", "bilde_url": "",
     "dt": _nå() - timedelta(hours=3)},
]

def _hent_alt(force: bool = False) -> dict:
    global _cache
    with _cache_lock:
        if not force and _cache_ok(_cache.get("ts"), 300):
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
    with _cache_lock: _cache = result
    return result

# ═══════════════════════════════════════════════════════════════
# HTML-MAL — editorial stil, alle tekster garantert mørke
# ═══════════════════════════════════════════════════════════════
HTML = r"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MinOslo — Oslo i dag</title>
<meta name="description" content="Nyheter, trafikkstatus og politilogg for Oslo.">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,700;1,400&family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet">
<script>
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: {
          display: ['"Libre Baskerville"', 'Georgia', 'serif'],
          body: ['"Source Sans 3"', 'system-ui', 'sans-serif'],
        },
        colors: { oslo: '#c8001e' }
      }
    }
  }
</script>
<style>
  body { font-family: "Source Sans 3", system-ui, sans-serif; }

  @keyframes fadeUp {
    from { opacity:0; transform:translateY(12px) }
    to   { opacity:1; transform:translateY(0) }
  }
  .fi  { animation: fadeUp .35s ease both }
  .fi:nth-child(1)  { animation-delay:.03s }
  .fi:nth-child(2)  { animation-delay:.08s }
  .fi:nth-child(3)  { animation-delay:.13s }
  .fi:nth-child(4)  { animation-delay:.18s }
  .fi:nth-child(n+5){ animation-delay:.23s }

  @keyframes pr { 0%,100%{opacity:1} 50%{opacity:.1} }
  .pr { animation: pr 1.5s ease infinite }

  @keyframes bly { 0%,100%{opacity:1} 50%{opacity:.4} }
  .bly { animation: bly 2s ease infinite }

  html { scroll-behavior:smooth }
  ::-webkit-scrollbar { width:5px }
  ::-webkit-scrollbar-thumb { background:#cbd5e1; border-radius:3px }
</style>
</head>
<body class="bg-slate-50 text-slate-900">

<!-- HEADER -->
<header class="sticky top-0 z-50 bg-white border-b-[3px] border-oslo"
        style="box-shadow:0 1px 6px rgba(0,0,0,.08)">
  <div class="max-w-screen-xl mx-auto px-4 sm:px-6 h-[52px]
              flex items-center justify-between gap-3">

    <a href="/" onclick="location.reload();return false;"
       class="flex items-center gap-2 group shrink-0">
      <svg width="28" height="22" viewBox="0 0 28 22" fill="none"
           class="text-oslo group-hover:scale-110 transition-transform duration-200">
        <polygon points="0,21 3,15 6,21" fill="currentColor" opacity=".9"/>
        <rect x="8"   y="7"  width="2.5" height="14" rx=".4" fill="currentColor"/>
        <rect x="12"  y="3"  width="2.5" height="18" rx=".4" fill="currentColor"/>
        <rect x="16"  y="10" width="2.5" height="11" rx=".4" fill="currentColor"/>
        <rect x="20"  y="5"  width="2.5" height="16" rx=".4" fill="currentColor"/>
        <rect x="24"  y="12" width="3.5" height="9"  rx=".4" fill="currentColor"/>
        <line x1="0" y1="21" x2="28" y2="21" stroke="currentColor" stroke-width="1.5"/>
      </svg>
      <span class="font-display font-bold italic text-[1.25rem] leading-none text-oslo">
        Min<span class="not-italic text-slate-900">Oslo</span>
      </span>
    </a>

    <nav class="hidden md:flex items-center gap-5
                text-[11px] font-bold tracking-widest uppercase text-slate-400">
      <a href="#nyheter"    class="hover:text-oslo transition-colors">Nyheter</a>
      <a href="#ruter"      class="hover:text-oslo transition-colors">Trafikk</a>
      <a href="#politilogg" class="hover:text-oslo transition-colors">Politilogg</a>
      <button onclick="oppdater()"
              class="hover:text-oslo transition-colors bg-transparent border-0 p-0
                     font-bold text-[11px] tracking-widest uppercase text-slate-400 cursor-pointer">
        Oppdater
      </button>
    </nav>

    <div class="flex items-center gap-2 shrink-0">
      <!-- Vær -->
      <div class="flex items-center gap-1.5 bg-slate-100 border border-slate-200
                  rounded-full px-3 py-1 text-sm font-bold text-slate-800 min-w-[66px]">
        <span id="w-emoji">–</span>
        <span id="w-temp" class="tabular-nums">–°</span>
      </div>
      <!-- Ruter-indikator -->
      <div id="ruter-pill"
           class="hidden md:flex items-center gap-1.5 bg-slate-100 border border-slate-200
                  rounded-full px-3 py-1 text-[11px] font-bold text-slate-700 min-w-[80px]">
        <span id="r-dot" class="w-2 h-2 rounded-full bg-slate-400 shrink-0"></span>
        <span id="r-txt">–</span>
      </div>
    </div>
  </div>
</header>

<main class="max-w-screen-xl mx-auto px-4 sm:px-6 py-6">

  <!-- RUTER TRAFIKKSTATUS -->
  <section id="ruter" class="mb-8">
    <div class="flex items-center gap-2.5 mb-3">
      <span class="pr w-2 h-2 rounded-full bg-oslo inline-block shrink-0"></span>
      <h2 class="font-display font-bold text-lg text-slate-900">Trafikkstatus</h2>
      <span class="text-[10px] font-bold tracking-widest uppercase text-oslo">Ruter Oslo</span>
      <span class="ml-auto text-[10px] text-slate-400 font-mono">{{ ruter.oppdatert }}</span>
    </div>

    {% if ruter.ok is none %}
      <div class="bg-white border border-slate-200 rounded-xl p-4
                  flex items-center gap-3 text-slate-700 text-sm">
        <span class="text-xl">🚌</span>
        <span>Trafikkstatus ikke tilgjengelig akkurat nå.</span>
        <a href="https://ruter.no/trafikkstatus/" target="_blank"
           class="ml-auto text-oslo border-b border-oslo text-xs font-bold whitespace-nowrap">
          Sjekk Ruter ↗
        </a>
      </div>

    {% elif ruter.ok %}
      <div class="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-3
                  flex items-center gap-3">
        <span class="text-2xl">✅</span>
        <div>
          <p class="font-bold text-emerald-900 text-sm">Alt i rute</p>
          <p class="text-emerald-800 text-xs mt-0.5">
            Ingen registrerte driftsavvik på Ruter-nettet.
          </p>
        </div>
        <a href="https://ruter.no/trafikkstatus/" target="_blank"
           class="ml-auto text-emerald-700 border-b border-emerald-500
                  text-xs font-bold shrink-0">
          Ruter.no ↗
        </a>
      </div>

    {% else %}
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {% for a in ruter.avvik %}
        <div class="fi bg-white rounded-xl border overflow-hidden
                    {% if a.alvorlig %}border-red-300{% else %}border-amber-300{% endif %}">
          <div class="px-4 py-2 text-[10px] font-bold tracking-wide uppercase
                      {% if a.alvorlig %}bg-red-50 text-red-800{% else %}bg-amber-50 text-amber-800{% endif %}">
            {% if a.alvorlig %}⚠️ Alvorlig{% else %}ℹ️ Melding{% endif %}
            {% if a.linjer %}
              <span class="ml-1 font-normal normal-case">{{ a.linjer }}</span>
            {% endif %}
          </div>
          <div class="p-4">
            <p class="font-bold text-sm text-slate-900 leading-snug mb-1">{{ a.summary }}</p>
            {% if a.desc %}
            <p class="text-xs text-slate-700 leading-relaxed">{{ a.desc }}</p>
            {% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
      <p class="mt-2 text-right">
        <a href="https://ruter.no/trafikkstatus/" target="_blank"
           class="text-[11px] font-bold text-oslo border-b border-oslo">
          Se alle avvik hos Ruter ↗
        </a>
      </p>
    {% endif %}
  </section>

  <!-- NYHETER -->
  <section id="nyheter">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2.5">
        <h2 class="font-display font-bold text-xl text-slate-900">Siste nytt</h2>
        <span class="text-[10px] font-bold tracking-widest uppercase text-slate-400">Oslo</span>
      </div>
      <span class="text-xs font-mono text-slate-400">{{ oppdatert }}</span>
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
             class="w-full h-full object-cover rounded-t-xl
                    transition-transform duration-500 group-hover:scale-[1.02]"
             onerror="this.parentElement.style.display='none'">
      </div>
      {% endif %}
      <div class="p-5 sm:p-7">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-[10px] font-bold tracking-wider uppercase
                       text-white px-2 py-0.5 rounded"
                style="background:{{ h.badge_farge }}">
            {{ h.badge }} {{ h.kilde_navn }}
          </span>
          <span class="text-[11px] font-mono text-slate-400">{{ h.publisert }}</span>
        </div>
        <h3 class="font-display font-bold text-2xl sm:text-3xl leading-tight
                   text-slate-900 mb-3 group-hover:text-oslo transition-colors duration-150">
          {{ h.overskrift }}
        </h3>
        <p class="text-slate-700 leading-relaxed text-base line-clamp-3">{{ h.ingress }}</p>
        <span class="inline-block mt-4 text-xs font-bold text-blue-700
                     border-b border-blue-400 pb-px hover:opacity-70 transition-opacity">
          ↗ {{ h.kilde_tekst }}
        </span>
      </div>
    </article>

    <!-- GRID -->
    {% if nyheter|length > 1 %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {% for art in nyheter[1:] %}
      <article class="fi bg-white rounded-2xl shadow-sm overflow-hidden flex flex-col
                      hover:shadow-md transition-shadow duration-200 cursor-pointer group"
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
            <span class="text-[9px] font-bold tracking-wider uppercase
                         text-white px-1.5 py-0.5 rounded"
                  style="background:{{ art.badge_farge }}">
              {{ art.badge }} {{ art.kilde_navn }}
            </span>
            <span class="text-[10px] font-mono text-slate-400">{{ art.publisert }}</span>
          </div>
          <h3 class="font-display font-bold text-[1.05rem] leading-snug
                     text-slate-900 mb-2 flex-1
                     group-hover:text-oslo transition-colors duration-150">
            {{ art.overskrift }}
          </h3>
          <p class="text-slate-700 text-sm leading-relaxed line-clamp-3 mb-3">
            {{ art.ingress }}
          </p>
          <span class="text-xs font-bold text-blue-700 border-b border-blue-400
                       pb-px w-fit mt-auto hover:opacity-70 transition-opacity">
            ↗ {{ art.kilde_tekst }}
          </span>
        </div>
      </article>
      {% endfor %}
    </div>
    {% endif %}

    {% else %}
    <div class="bg-white rounded-2xl shadow-sm p-10 text-center">
      <p class="text-sm text-slate-400">Ingen saker hentet akkurat nå. Prøv igjen om litt.</p>
    </div>
    {% endif %}
  </section>

  <!-- POLITILOGG -->
  <section id="politilogg" class="mt-12">
    <div class="flex items-center gap-3 mb-4">
      <span class="pr w-2 h-2 rounded-full bg-oslo inline-block shrink-0"></span>
      <h2 class="font-display font-bold text-xl text-slate-900">Politilogg</h2>
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
          <span class="text-[10px] font-mono shrink-0" style="color:#5a8fbb">
            📍 {{ p.sted }}
          </span>
        </div>
        <p class="text-sm leading-relaxed line-clamp-3 mb-2.5"
           style="color:#c8dfff">{{ p.tekst }}</p>
        <span class="text-[10px] font-mono border-b pb-px opacity-75
                     group-hover:opacity-100 transition-opacity"
              style="color:#4a8fd4;border-color:#4a8fd4">
          ↗ Les hos Politiloggen
        </span>
      </a>
      {% endfor %}
    </div>
    {% else %}
    <div class="rounded-2xl p-8 text-center" style="background:#05101f">
      <p class="text-sm mb-3" style="color:#5a8fbb">
        Ingen meldinger siste 48 timer.
      </p>
      <a href="https://politiloggen.politiet.no" target="_blank"
         class="text-xs border-b"
         style="color:#4a8fd4;border-color:#4a8fd4">
        ↗ Se politiloggen direkte
      </a>
    </div>
    {% endif %}
  </section>

</main>

<footer class="mt-16 border-t border-slate-200 bg-white">
  <div class="max-w-screen-xl mx-auto px-4 sm:px-6 py-5
              flex flex-col sm:flex-row items-center justify-between
              gap-3 text-xs text-slate-400">
    <span class="font-display font-bold italic text-oslo text-sm">MinOslo</span>
    <span>Politiloggen · Oslo kommune · NRK Stor-Oslo · eInnsyn · Ruter</span>
    <span class="font-mono">Oppdateres hvert 5. min</span>
  </div>
</footer>

<script>
fetch('/api/vaer')
  .then(r => r.json())
  .then(d => {
    document.getElementById('w-emoji').textContent = d.emoji || '🌡️';
    document.getElementById('w-temp').textContent  = d.temp + '°';
  }).catch(() => {});

fetch('/api/ruter')
  .then(r => r.json())
  .then(d => {
    const pill = document.getElementById('ruter-pill');
    const dot  = document.getElementById('r-dot');
    const txt  = document.getElementById('r-txt');
    pill.classList.remove('hidden');
    if (d.ok === true) {
      dot.className = 'w-2 h-2 rounded-full bg-emerald-500 shrink-0';
      txt.textContent = 'I rute';
      pill.style.borderColor = '#6ee7b7';
    } else if (d.ok === false) {
      dot.className = 'w-2 h-2 rounded-full bg-oslo shrink-0 bly';
      txt.textContent = d.antall + ' avvik';
      pill.style.borderColor = '#fca5a5';
    } else {
      txt.textContent = 'Ukjent';
    }
  }).catch(() => {});

function oppdater() {
  fetch('/api/oppdater', { method: 'POST' })
    .finally(() => location.reload());
}

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
    return render_template_string(
        HTML,
        nyheter   = data["nyheter"],
        politi    = data["politi"],
        ruter     = ruter,
        oppdatert = data["ts"].strftime("%H:%M") if data["ts"] else "–",
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
    _hent_ruter_status()
    return jsonify({"ok": True})

@app.route("/robots.txt")
def robots():
    return "User-agent: *\nDisallow:\n", 200, {"Content-Type": "text/plain"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    _hent_alt()
    _hent_ruter_status()
    app.run(host="0.0.0.0", port=port, debug=False)
