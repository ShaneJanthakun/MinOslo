"""
MinOslo.no — Flask + Gunicorn
==============================
Start:    gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60
Lokalt:   python app.py

Datakilder:
  • Oslo kommune  — aktuelt.oslo.kommune.no (RSS-fallback)
  • NRK Stor-Oslo — nrk.no/stor-oslo/toppsaker.rss
  • eInnsyn       — einnsyn.no/rss
  • Politiloggen  — api.politiet.no (JSON, 48t)
  • Ruter status  — ruter.no/trafikkstatus (HTML-skraping) + Entur v3 GraphQL
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

HDRS_BOT = {"User-Agent": _UA_BOT}

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
    return bool(ts and (_nå() - ts).total_seconds() < sek)

# ═══════════════════════════════════════════════════════════════
# KARTBILDER
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
    if art.get("bilde_url", "").startswith("http"):
        return art
    t = f"{art.get('overskrift','')} {art.get('ingress','')}"
    for gate in GATE_RE.findall(t):
        url = _osm_png(gate)
        if url:
            return {**art, "bilde_url": url}
    return {**art, "bilde_url": ""}

# ═══════════════════════════════════════════════════════════════
# VÆR
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
# RUTER TRAFIKKSTATUS
# ═══════════════════════════════════════════════════════════════
_ruter_data: dict = {}
_ruter_ts:   datetime | None = None
_ruter_lock = Lock()

def _ruter_scrape() -> dict | None:
    url = "https://ruter.no/trafikkstatus/"
    try:
        r = requests.get(url, headers=HDRS_WEB, timeout=TIMEOUT)
        r.raise_for_status()
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, "html.parser")

        avvik = []
        kandidater = (
            soup.find_all("article")
            or soup.find_all(class_=re.compile(r"disruption|deviation|avvik|status|message|alert", re.I))
            or soup.find_all(["li", "div"], class_=re.compile(r"item|card|row", re.I))
        )

        seen = set()
        for el in kandidater[:20]:
            h = (el.find(["h1","h2","h3","h4","h5"]) or el.find(class_=re.compile(r"title|heading", re.I)))
            if not h: continue
            tittel = _rens(h.get_text())
            
            # Rens ut informasjonskapsler / app-reklame
            if not tittel or len(tittel) < 5 or tittel in seen or any(w in tittel.lower() for w in ["informasjonskapsler", "cookie", "last ned appen"]):
                continue
            seen.add(tittel)

            p = el.find("p") or el.find(class_=re.compile(r"desc|body|text", re.I))
            desc = _rens(p.get_text()) if p else ""
            if any(w in desc.lower() for w in ["informasjonskapsler", "cookie", "godta", "personvern"]):
                continue

            klasser = " ".join(el.get("class", []))
            tekst_all = f"{tittel} {desc} {klasser}".lower()
            alvorlig = any(w in tekst_all for w in ["innstilt", "stanset", "stoppet", "avlyst", "severe", "critical", "feil", "stopp"])

            linjer = []
            for span in el.find_all(["span", "strong", "b"], limit=5):
                tx = _rens(span.get_text())
                if re.match(r"^[A-Z]?\d{1,3}[A-Z]?$", tx) or any(w in tx.lower() for w in ["t-bane", "buss", "trikk", "linje"]):
                    linjer.append(tx)
            linje_str = ", ".join(linjer[:3]) or ""

            avvik.append({
                "summary": tittel,
                "desc": (desc[:200] + "…") if len(desc) > 200 else desc,
                "linjer": linje_str,
                "alvorlig": alvorlig,
            })

        if avvik:
            avvik.sort(key=lambda x: x["alvorlig"], reverse=True)
            return {"ok": False, "avvik": avvik[:8], "oppdatert": _nå().strftime("%H:%M"), "antall": len(avvik), "kilde": "ruter.no"}

        full_text = soup.get_text().lower()
        if any(p in full_text for p in ["alt i rute", "ingen avvik", "normal drift"]):
            return {"ok": True, "avvik": [], "oppdatert": _nå().strftime("%H:%M"), "antall": 0, "kilde": "ruter.no"}
        return None
    except Exception as e:
        log.error(f"Ruter skraping feil: {e}")
        return None

def _ruter_entur() -> dict | None:
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
            "https://api.entur.io/journey-planner/v3/graphql",
            json={"query": query},
            headers={
                "User-Agent": _UA_BOT,
                "Content-Type": "application/json",
                "ET-Client-Name": "minoslo-minoslo.no",
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
                if slutt and slutt < nå: continue

            def nb(lst):
                if not lst: return ""
                item = next((x for x in lst if x.get("language") in ("no","nb")), None)
                return _rens((item or lst[0]).get("value", ""))

            summary = nb(s.get("summary", []))
            if not summary or any(w in summary.lower() for w in ["cookie", "informasjonskapsler"]): continue
            
            desc = nb(s.get("description", []))
            sev = s.get("severity", "").lower()
            lines = s.get("affects", {}).get("lines", []) or []
            linjer = ", ".join(f"{l.get('publicCode','')} {l.get('name','')}".strip() for l in lines[:3]) or ""

            avvik.append({
                "summary": summary,
                "desc": (desc[:200] + "…") if len(desc) > 200 else desc,
                "linjer": linjer,
                "alvorlig": sev in ("severe", "verysevere"),
            })

        avvik.sort(key=lambda x: x["alvorlig"], reverse=True)
        return {"ok": len(avvik) == 0, "avvik": avvik[:8], "oppdatert": nå.strftime("%H:%M"), "antall": len(avvik), "kilde": "entur"}
    except Exception as e:
        log.error(f"Entur backup feil: {e}")
        return None

def _hent_ruter_status() -> dict:
    global _ruter_data, _ruter_ts
    with _ruter_lock:
        if _cache_ok(_ruter_ts, 300): return _ruter_data
    res = _ruter_scrape() or _ruter_entur()
    if res is None:
        res = {"ok": True, "avvik": [], "oppdatert": _nå().strftime("%H:%M"), "antall": 0, "kilde": "–"}
    with _ruter_lock:
        _ruter_data, _ruter_ts = res, _nå()
    return res

# ═══════════════════════════════════════════════════════════════
# OSLO KOMMUNE (Enkel RSS-Fallback logikk)
# ═══════════════════════════════════════════════════════════════
def _hent_oslo_kommune() -> list[dict]:
    ut = []
    try:
        r = requests.get("https://aktuelt.oslo.kommune.no/?format=rss", headers=HDRS_WEB, timeout=TIMEOUT)
        r.encoding = 'utf-8'
        if r.ok and "<" in r.text:
            soup = BeautifulSoup(r.text, "lxml-xml")
            items = soup.find_all("item")
            for item in items[:5]:
                tittel = _rens(item.find("title").get_text() if item.find("title") else "")
                if not tittel: continue
                desc = _rens(item.find("description").get_text() if item.find("description") else "")
                lenke = _rens(item.find("link").get_text() if item.find("link") else "https://aktuelt.oslo.kommune.no/")
                
                ut.append({
                    "overskrift": tittel, "ingress": (desc[:240] + "…") if len(desc) > 240 else desc,
                    "publisert": "Nylig", "kilde_url": lenke, "kilde_navn": "Oslo kommune",
                    "kilde_tekst": "Les hos Oslo kommune", "badge": "K", "badge_farge": "#1a6632",
                    "kategori": "kommune", "bilde_url": "", "dt": _nå() - timedelta(minutes=45)
                })
    except Exception as e:
        log.warning(f"Kommune RSS feil: {e}")
    return ut

# ═══════════════════════════════════════════════════════════════
# POLITILOGGEN
# ═══════════════════════════════════════════════════════════════
def _hent_politi() -> list[dict]:
    url = "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=40"
    try:
        r = requests.get(url, headers={"User-Agent": _UA_BOT}, timeout=TIMEOUT)
        r.raise_for_status()
        items = r.json()
        if not isinstance(items, list):
            items = items.get("meldinger") or []
        grense = _nå() - timedelta(hours=48)
        ut = []
        for m in items:
            tittel = _rens(m.get("tittel") or m.get("title") or "")
            tekst  = _rens(m.get("tekst")  or m.get("text")  or m.get("description") or "")
            tidsp  = m.get("tidspunkt") or ""
            sted   = _rens(m.get("sted") or "Oslo")
            link   = m.get("url") or "https://politiloggen.politiet.no"
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
        return ut[:20]
    except Exception as e:
        log.error(f"Politiloggen feil: {e}")
        return []

# ═══════════════════════════════════════════════════════════════
# RSS (NRK + eInnsyn)
# ═══════════════════════════════════════════════════════════════
KILDER_RSS = [
    {
        "id": "nrk",
        "url": "https://www.nrk.no/stor-oslo/toppsaker.rss",
        "navn": "NRK", "badge": "N", "farge": "#c8001e",
        "kategori": "nrk", "max_alder": timedelta(days=7),
        "link": "https://www.nrk.no/stor-oslo/", "oslo_filter": True,
    },
    {
        "id": "einnsyn",
        "url": "https://einnsyn.no/rss?q=Oslo+kommune&antall=20",
        "navn": "eInnsyn", "badge": "E", "farge": "#4a3580",
        "kategori": "einnsyn", "max_alder": timedelta(days=7),
        "link": "https://einnsyn.no", "oslo_filter": False,
    },
]

def _hent_rss(kilde: dict) -> list[dict]:
    ut = []
    try:
        r = requests.get(kilde["url"], headers=HDRS_WEB, timeout=TIMEOUT)
        r.encoding = 'utf-8'
        if r.ok and "<" in r.text:
            soup = BeautifulSoup(r.text, "lxml-xml")
            items = soup.find_all("item") or soup.find_all("entry")
            grense = _nå() - kilde["max_alder"]
            for item in items:
                def g(*tags):
                    for t in tags:
                        n = item.find(t)
                        if n and n.get_text(strip=True): return _rens(n.get_text())
                    return ""
                tittel = g("title")
                if not tittel: continue
                desc  = g("description", "summary", "content")
                pub   = g("pubDate", "published")
                lenke = g("link")
                dt = _parse_dato(pub)
                if dt and dt < grense: continue
                if kilde.get("oslo_filter") and not _oslo_ok(tittel, desc): continue
                
                ingress = desc[:280].rstrip()
                if len(desc) > 280: ingress += "…"
                
                ut.append(_berik({
                    "overskrift": tittel, "ingress": ingress, "publisert": _dstr(dt, pub),
                    "kilde_url": lenke or kilde["link"], "kilde_navn": kilde["navn"],
                    "kilde_tekst": f"Les hos {kilde['navn']}", "badge": kilde["badge"],
                    "badge_farge": kilde["farge"], "kategori": kilde["kategori"],
                    "bilde_url": "", "dt": dt or (_nå() - timedelta(hours=6))
                }))
    except Exception as e:
        log.error(f"RSS feil for {kilde['navn']}: {e}")
    return ut

# ═══════════════════════════════════════════════════════════════
# HOVED-CACHE (Akkumulerer trygt uten å slette)
# ═══════════════════════════════════════════════════════════════
_cache: dict = {"politi": [], "nyheter": [], "ts": None}
_cache_lock = Lock()

def _hent_alt(force: bool = False) -> dict:
    global _cache
    with _cache_lock:
        if not force and _cache_ok(_cache.get("ts"), 300):
            return _cache

    # Hent politiloggen separat i en sikret try-except
    try:
        politi_saker = _hent_politi()
    except Exception:
        politi_saker = _cache.get("politi", [])

    # Hent nyheter lagvis så de ALDRI sletter hverandre ved delvis feil
    akkumulerte_nyheter = []
    
    try:
        akkumulerte_nyheter.extend(_hent_oslo_kommune())
    except Exception as e:
        log.warning(f"Feil i kommune-loop: {e}")

    for kilde in KILDER_RSS:
        try:
            saker = _hent_rss(kilde)
            if saker:
                akkumulerte_nyheter.extend(saker)
        except Exception as e:
            log.warning(f"Feil ved henting av {kilde['navn']}: {e}")

    # Sorter samlet nyhetsfeed kronologisk
    if akkumulerte_nyheter:
        akkumulerte_nyheter.sort(key=lambda x: x["dt"], reverse=True)
    else:
        akkumulerte_nyheter = _cache.get("nyheter", [])

    result = {
        "politi": politi_saker,
        "nyheter": akkumulerte_nyheter,
        "ts": _nå(),
    }
    with _cache_lock: _cache = result
    return result

# ═══════════════════════════════════════════════════════════════
# DELTE DESIGNKOMPONENTER (Garantert lesbar og mørk tekst)
# ═══════════════════════════════════════════════════════════════
BASE_MAL = """<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MinOslo — Oslo i dag</title>
<script src="https://cdn.tailwindcss.com"></script>
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
</head>
<body class="bg-slate-50 text-slate-900 font-body">

<header class="sticky top-0 z-50 bg-white border-b-[3px] border-oslo shadow-sm">
  <div class="max-w-screen-xl mx-auto px-4 h-[52px] flex items-center justify-between">
    <a href="/" class="flex items-center gap-2">
      <span class="font-display font-bold italic text-[1.25rem] text-oslo">Min<span class="not-italic text-slate-900">Oslo</span></span>
    </a>
    <nav class="flex items-center gap-6 text-[12px] font-bold tracking-widest uppercase text-slate-500">
      <a href="/" class="hover:text-oslo transition-colors">Nyheter</a>
      <a href="/trafikk" class="hover:text-oslo transition-colors flex items-center gap-1">
        Trafikk
        {% if ruter_status.antall > 0 %}
          <span class="bg-oslo text-white text-[10px] px-1.5 py-0.5 rounded-full font-sans font-bold">{{ ruter_status.antall }}</span>
        {% endif %}
      </a>
    </nav>
    <div class="text-sm font-bold text-slate-800 flex items-center gap-1.5 bg-slate-100 px-3 py-1 rounded-full">
      <span>{{ vaer.emoji }}</span> <span>{{ vaer.temp }}°</span>
    </div>
  </div>
</header>

<main class="max-w-screen-xl mx-auto px-4 py-6">
  {% block content %}{% endblock %}
</main>

<footer class="border-t border-slate-200 mt-12 py-6 bg-white text-center text-xs text-slate-500 font-medium">
  &copy; {{ aar }} MinOslo.no &bull; Lokale sanntidsnyheter for hovedstaden.
</footer>

</body>
</html>"""

# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route("/")
def index():
    data = _hent_alt()
    vaer = _hent_vær()
    ruter = _hent_ruter_status()
    
    index_html = """
    {% extends "base" %}
    {% block content %}
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      
      <div class="lg:col-span-2 space-y-6">
        <h2 class="font-display font-bold text-2xl border-b-2 border-slate-200 pb-2 text-slate-900">Siste nytt</h2>
        <div class="space-y-6">
          {% for s in data.nyheter %}
            <article class="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-5">
              {% if s.bilde_url %}
                <div class="md:w-1/3 shrink-0">
                  <img src="{{ s.bilde_url }}" class="w-full h-40 object-cover rounded-lg border border-slate-100" alt="Kart">
                </div>
              {% endif %}
              <div class="flex-1 space-y-2">
                <div class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <span class="px-1.5 py-0.5 rounded text-white" style="background-color: {{ s.badge_farge }}">{{ s.badge }}</span>
                  <span>{{ s.kilde_navn }}</span>
                  <span>&bull;</span>
                  <span>{{ s.publisert }}</span>
                </div>
                <h3 class="font-display font-bold text-xl text-slate-900 hover:text-oslo transition-colors">
                  <a href="{{ s.kilde_url }}" target="_blank">{{ s.overskrift }}</a>
                </h3>
                <p class="text-slate-600 text-sm leading-relaxed">{{ s.ingress }}</p>
              </div>
            </article>
          {% endfor %}
        </div>
      </div>

      <div class="space-y-6">
        <h2 class="font-display font-bold text-2xl border-b-2 border-slate-200 pb-2 text-slate-900">Politiloggen</h2>
        <div class="space-y-4">
          {% for p in data.politi %}
            <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-2">
              <div class="flex items-center justify-between text-xs font-bold text-slate-400 uppercase tracking-wider">
                <span class="text-sky-700 bg-sky-50 px-2 py-0.5 rounded border border-sky-100">🚔 {{ p.sted }}</span>
                <span>{{ p.tid }}</span>
              </div>
              <h4 class="font-bold text-slate-900 text-base leading-snug">
                <a href="{{ p.url }}" target="_blank" class="hover:underline">{{ p.tittel }}</a>
              </h4>
              <p class="text-slate-600 text-xs leading-relaxed">{{ p.tekst }}</p>
            </div>
          {% endfor %}
        </div>
      </div>

    </div>
    {% endblock %}
    """
    return render_template_string(BASE_MAL + index_html, data=data, vaer=vaer, ruter_status=ruter, aar=_nå().year)


@app.route("/trafikk")
def trafikk():
    vaer = _hent_vær()
    ruter = _hent_ruter_status()
    
    trafikk_html = """
    {% extends "base" %}
    {% block content %}
    <div class="max-w-3xl mx-auto space-y-6">
      <div class="flex items-center justify-between border-b-2 border-slate-200 pb-2">
        <h2 class="font-display font-bold text-2xl text-slate-900">Trafikkstatus for Oslo</h2>
        <span class="text-xs font-medium text-slate-400">Oppdatert: {{ ruter_status.oppdatert }} (Kilde: {{ ruter_status.kilde }})</span>
      </div>

      {% if ruter_status.avvik %}
        <div class="space-y-4">
          {% for a in ruter_status.avvik %}
            <div class="p-5 rounded-xl border {{ 'bg-red-50 border-red-200' if a.alvorlig else 'bg-amber-50 border-amber-200' }} space-y-3 shadow-sm">
              <div class="flex flex-wrap items-center gap-2">
                <span class="px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider {{ 'bg-red-600 text-white' if a.alvorlig else 'bg-amber-600 text-white' }}">
                  {{ 'Kritisk avvik' if a.alvorlig else 'Forsinkelse / Avvik' }}
                </span>
                {% if a.linjer %}
                  <span class="bg-white text-slate-800 border {{ 'border-red-200' if a.alvorlig else 'border-amber-200' }} text-xs px-2 py-0.5 rounded font-bold">
                    {{ a.linjer }}
                  </span>
                {% endif %}
              </div>
              <h3 class="font-bold text-slate-900 text-lg leading-snug">{{ a.summary }}</h3>
              {% if a.desc %}
                <p class="text-slate-700 text-sm leading-relaxed">{{ a.desc }}</p>
              {% endif %}
            </div>
          {% endfor %}
        </div>
      {% else %}
        <div class="bg-emerald-50 border border-emerald-200 p-8 rounded-xl text-center space-y-2 shadow-sm">
          <div class="text-3xl">💚</div>
          <h3 class="font-bold text-emerald-900 text-xl">Alt i rute</h3>
          <p class="text-emerald-700 text-sm">Det er ingen registrerte avvik eller store forsinkelser i kollektivtrafikken akkurat nå.</p>
        </div>
      {% endif %}
    </div>
    {% endblock %}
    """
    return render_template_string(BASE_MAL + trafikk_html, vaer=vaer, ruter_status=ruter, aar=_nå().year)


# For testing/lokal kjøring
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
