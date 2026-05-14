"""
MinOslo.no — Flask + Gunicorn
==============================
Start lokalt:  python app.py
Start Render:  gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 60

Alle fire rettelser er bakt inn fra grunnen av:
  1. NRK  → https://www.nrk.no/stor-oslo/toppsaker.rss
  2. MET  → User-Agent: MinOsloBot/1.0 (shanebusiness99@gmail.com)
  3. Politi → samme User-Agent, ikke browser-headers
  4. Cache → total_seconds(), ikke .seconds
"""

import os, re, html as _html, logging
from datetime import datetime, timezone, timedelta
from threading import Lock

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, jsonify

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
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
# HTTP-HEADERS
# Tre ulike header-sett for tre ulike formål:
#   BOT_UA  — identifiserer oss overfor MET og Politiet (kreves!)
#   RSS_HDR — for RSS-feeds (NRK, Oslo kommune, eInnsyn)
#   OSM_HDR — for Nominatim kart-oppslag
# ═══════════════════════════════════════════════════════════════
_MY_UA = "MinOsloBot/1.0 (shanebusiness99@gmail.com)"

BOT_UA = {"User-Agent": _MY_UA}

RSS_HDR = {
    "User-Agent": "Mozilla/5.0 (compatible; MinOsloBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "nb-NO,nb;q=0.9",
}

OSM_HDR = {"User-Agent": _MY_UA}

TIMEOUT = 7

# ═══════════════════════════════════════════════════════════════
# OSLO-FILTER
# ═══════════════════════════════════════════════════════════════
OSLO_RE = re.compile(
    r"\b("
    r"Oslo|Grünerløkka|Frogner|Sagene|Majorstuen|Majorstua|Alna|Bjerke|Grorud|"
    r"Nordstrand|Nordre Aker|Vestre Aker|Østensjø|Stovner|Gamle Oslo|"
    r"St\.?\s*Hanshaugen|Hanshaugen|Sentrum|Bislett|Tøyen|Grønland|"
    r"Holmlia|Manglerud|Lambertseter|Skullerud|Mortensrud|Romsås|"
    r"Furuset|Ellingsrud|Haugerud|Ulvern|Røa|Vinderen|"
    r"Slemdal|Grefsen|Kjelsås|Nydalen|Sandaker|Torshov|Sinsen|"
    r"Storo|Lilleborg|Ullevål|Rikshospitalet|Gaustad|"
    r"Homansbyen|Solli|Skøyen|Lysaker|Bygdøy|"
    r"Aker Brygge|Tjuvholmen|Vippetangen|Bjørvika|Sørenga|"
    r"Gamlebyen|Kampen|Vålerenga|Etterstad|"
    r"Helsfyr|Bryn|Brynseng|Ensjø|Teisen|Løren|"
    r"Alfaset|Lindeberg|Trosterud|"
    r"Rommen|Ammerud|Haugenstua|Fossum|"
    r"Kalbakken|Vestli|Rødtvet|Veitvet|"
    r"Karl Johans|Rådhuset|Stortorvet|Ullern"
    r")\b", re.I
)

EKSKL = re.compile(
    r"\b("
    r"utenriks|verden|internasjonal|Europa|USA|Russland|Ukraina|"
    r"Israel|Gaza|Kina|Storbritannia|Premier.?League|Champions League|"
    r"Eliteserien|landslaget|Nobel|Stortinget|"
    r"regjeringen|statsminister|Finansdepartement|fjellbygd|Viken|"
    r"Trondheim|Bergen|Stavanger|Tromsø|Bodø|Drammen|Ringerike|"
    r"Hamar|Lillehammer|Fredrikstad|Sarpsborg|Moss|Halden"
    r")\b", re.I
)

GATE_RE = re.compile(
    r"\b([A-ZÆØÅ][a-zæøå]+"
    r"(?:gate|gata|vei|veien|allé|alléen|plass|plassen|"
    r"torg|torget|brygge|bryggen|kaia|kaien|bakke|bakken|løkka|parken|stien)"
    r"(?:\s+\d+[A-Za-z]?)?)\b", re.U
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

# ═══════════════════════════════════════════════════════════════
# KARTBILDER (statisk PNG via OSM staticmap)
# Kun for saker med gjenkjent gateadresse — ingen generelle bilder.
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
            headers=OSM_HDR,
            timeout=3,
        )
        hits = r.json()
        if not hits:
            with _osm_lock:
                _osm_cache[adresse] = None
            return None
        lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
        url = (
            f"https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={lat},{lon}&zoom=16&size=900x506"
            f"&markers={lat},{lon},red-pushpin"
        )
        with _osm_lock:
            _osm_cache[adresse] = url
        return url
    except Exception as e:
        log.warning(f"OSM kart '{adresse}': {e}")
        with _osm_lock:
            _osm_cache[adresse] = None
        return None

def _berik_bilde(art: dict) -> dict:
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
# FIX: BOT_UA med shanebusiness99@gmail.com — uten dette gir MET 403
# FIX: total_seconds() i cache-sjekken
# ═══════════════════════════════════════════════════════════════
_vær_res: dict = {}
_vær_ts: datetime | None = None
_vær_lock = Lock()

SYMBOL_EMOJI = {
    "clearsky":     "☀️",
    "fair":         "🌤️",
    "partlycloudy": "⛅",
    "cloudy":       "☁️",
    "fog":          "🌫️",
    "lightrain":    "🌦️",
    "rain":         "🌧️",
    "heavyrain":    "⛈️",
    "lightsnow":    "🌨️",
    "snow":         "❄️",
    "sleet":        "🌨️",
    "thunder":      "⛈️",
}

def _hent_vær() -> dict:
    global _vær_res, _vær_ts
    with _vær_lock:
        # total_seconds() — ikke .seconds (som bare gir 0–59 sekunder)
        if _vær_ts and (_nå() - _vær_ts).total_seconds() < 1800:
            return _vær_res
    try:
        r = requests.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": "59.9139", "lon": "10.7522"},
            headers={"User-Agent": "MinOsloBot/1.0 (shanebusiness99@gmail.com)"},
            timeout=6,
        )
        r.raise_for_status()
        data   = r.json()
        ts0    = data["properties"]["timeseries"][0]["data"]
        inst   = ts0["instant"]["details"]
        next1h = ts0.get("next_1_hours", {}).get("summary", {})
        symbol = next1h.get("symbol_code", "")
        emoji  = next((v for k, v in SYMBOL_EMOJI.items() if k in symbol), "🌡️")
        temp   = round(inst.get("air_temperature", 0))
        res    = {"temp": temp, "emoji": emoji}
        log.info(f"Vær: {temp}° {symbol}")
        with _vær_lock:
            _vær_res = res
            _vær_ts  = _nå()
        return res
    except Exception as e:
        log.error(f"VÆR FEIL {type(e).__name__}: {e}")
        with _vær_lock:
            return _vær_res if _vær_res else {"temp": "–", "emoji": "🌡️"}

# ═══════════════════════════════════════════════════════════════
# POLITILOGGEN
# FIX: BOT_UA — browser-headers gir 429 fra Politiet
# FIX: total_seconds() i cache-sjekken
# ═══════════════════════════════════════════════════════════════
def _hent_politi() -> list[dict]:
    url = "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=40"
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "MinOsloBot/1.0 (shanebusiness99@gmail.com)"},
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
            if dt and dt < grense:
                continue
            if not _oslo_ok(tittel, tekst):
                continue
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
        log.error(f"POLITILOGG FEIL {type(e).__name__}: {e}")
        return []

# ═══════════════════════════════════════════════════════════════
# RSS-HENTING
# FIX NRK: primær URL er nå toppsaker.rss (ikke /feed/ som ga 404)
# ═══════════════════════════════════════════════════════════════
KILDER = [
    {
        "id": "oslo",
        "url": "https://aktuelt.oslo.kommune.no/?format=rss",
        "url_alt": [
            "https://www.oslo.kommune.no/rss/",
            "https://aktuelt.oslo.kommune.no/feed/",
        ],
        "navn": "Oslo kommune", "badge": "K", "farge": "#1a6632",
        "kategori": "kommune", "max_alder": timedelta(days=7),
        "link": "https://aktuelt.oslo.kommune.no", "oslo_filter": False,
    },
    {
        # FIX: /stor-oslo/feed/ ga 404 — toppsaker.rss er den fungerende URL-en
        "id": "nrk",
        "url": "https://www.nrk.no/stor-oslo/toppsaker.rss",
        "url_alt": [],   # ingen backup — den riktige URL-en er over
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
            r = requests.get(url, headers=RSS_HDR, timeout=TIMEOUT)
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
            if not tittel:
                continue
            desc  = g("description", "summary", "content")
            pub   = g("pubDate", "published", "updated", "dc:date")
            lenke = g("link")
            if not lenke:
                lt = item.find("link")
                if lt:
                    lenke = lt.get("href", "") or _rens(lt.get_text())
            dt = _parse_dato(pub)
            if dt and dt < grense:
                continue
            if kilde.get("oslo_filter") and not _oslo_ok(tittel, desc):
                continue
            ingress = desc[:280].rstrip()
            if len(desc) > 280:
                ingress += "…"
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
# HOVED-CACHE
# FIX: total_seconds() — .seconds returnerer bare 0–59 sekunder
#      og ignorerer timer, som betyr cachen aldri virket riktig
# ═══════════════════════════════════════════════════════════════
_data: dict = {"politi": [], "nyheter": [], "ts": None}
_data_lock = Lock()

PLACEHOLDER = [
    {"overskrift": "Oslos beste turtips denne helgen",
     "ingress": "Oslomarka tilbyr fantastiske turer for alle nivåer — her er ukens utvalgte ruter.",
     "publisert": _nå().strftime("%-d. %b"), "kilde_url": "https://ut.no",
     "kilde_navn": "ut.no", "kilde_tekst": "Les hos ut.no",
     "badge": "T", "badge_farge": "#1a6632", "bilde_url": "",
     "dt": _nå() - timedelta(hours=1)},
    {"overskrift": "Hva skjer i Oslo denne uken?",
     "ingress": "Konserter, markeder og utstillinger — sjekk Visit Oslo for oppdatert program.",
     "publisert": _nå().strftime("%-d. %b"), "kilde_url": "https://visitoslo.com",
     "kilde_navn": "Visit Oslo", "kilde_tekst": "Les hos Visit Oslo",
     "badge": "V", "badge_farge": "#1a4f8a", "bilde_url": "",
     "dt": _nå() - timedelta(hours=2)},
    {"overskrift": "Ruter: Slik reiser du smartest i Oslo",
     "ingress": "T-bane, trikk og buss dekker hele Oslo. Last ned Ruter-appen for sanntidsinformasjon.",
     "publisert": _nå().strftime("%-d. %b"), "kilde_url": "https://ruter.no",
     "kilde_navn": "Ruter", "kilde_tekst": "Les hos Ruter",
     "badge": "R", "badge_farge": "#8a1a1a", "bilde_url": "",
     "dt": _nå() - timedelta(hours=3)},
]

def _hent_alt(force: bool = False) -> dict:
    global _data
    with _data_lock:
        ts = _data.get("ts")
        # total_seconds() — kritisk riktig
        if not force and ts and (_nå() - ts).total_seconds() < 300:
            return _data
    politi  = _hent_politi()
    nyheter = []
    for k in KILDER:
        nyheter.extend(_hent_rss(k))
    nyheter.sort(key=lambda x: x["dt"], reverse=True)
    result = {
        "politi":  politi,
        "nyheter": nyheter if nyheter else list(PLACEHOLDER),
        "ts":      _nå(),
    }
    with _data_lock:
        _data = result
    return result

# ═══════════════════════════════════════════════════════════════
# HTML-MAL (Tailwind via CDN + Playfair + Geist)
# ═══════════════════════════════════════════════════════════════
HTML = r"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MinOslo — Oslo i dag</title>
<meta name="description" content="Ferske nyheter, politilogg og hva som skjer i Oslo akkurat nå.">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,400&family=Lato:wght@300;400;700;900&display=swap" rel="stylesheet">
<script>
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: {
          display: ['"Playfair Display"', 'Georgia', 'serif'],
          sans: ['Lato', 'system-ui', 'sans-serif'],
        },
        colors: {
          oslo: '#c8001e',
          'oslo-d': '#a0001a',
        }
      }
    }
  }
</script>
<style>
  /* Fade-up stagger for nyhets-kort */
  @keyframes fadeUp {
    from { opacity:0; transform:translateY(16px) }
    to   { opacity:1; transform:translateY(0) }
  }
  .card-in { animation: fadeUp .4s ease both }
  .card-in:nth-child(1)  { animation-delay:.04s }
  .card-in:nth-child(2)  { animation-delay:.10s }
  .card-in:nth-child(3)  { animation-delay:.16s }
  .card-in:nth-child(4)  { animation-delay:.22s }
  .card-in:nth-child(5)  { animation-delay:.28s }
  .card-in:nth-child(n+6){ animation-delay:.34s }

  /* Live-puls for politilogg */
  @keyframes pulse-r { 0%,100%{opacity:1} 50%{opacity:.1} }
  .pulse-r { animation: pulse-r 1.4s ease infinite }

  html { scroll-behavior:smooth }
  ::-webkit-scrollbar { width:6px }
  ::-webkit-scrollbar-thumb { background:#d1d5db; border-radius:3px }

  /* Alle brødtekster i nyhetskorter: mørk grå #333 */
  .card-body-text { color: #333333 !important; }
</style>
</head>
<body class="bg-[#F9FAFB] font-sans antialiased" style="color:#111827">

<!-- ══ HEADER ════════════════════════════════════════════════ -->
<header class="sticky top-0 z-50 bg-white border-b-[3px] border-oslo shadow-sm">
  <div class="max-w-screen-xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">

    <!-- Logo — klikk = reload -->
    <a href="/" onclick="location.reload();return false;"
       class="flex items-center gap-2.5 shrink-0 group" title="MinOslo – til forsiden">
      <svg width="32" height="26" viewBox="0 0 32 26" fill="none" aria-hidden="true"
           class="text-oslo transition-transform duration-200 group-hover:scale-110">
        <!-- Opera-taket -->
        <polygon points="0,25 4,18 8,25" fill="currentColor" opacity=".9"/>
        <!-- Barcode-bygg -->
        <rect x="10"  y="9"  width="3" height="16" rx=".4" fill="currentColor"/>
        <rect x="14.5" y="5" width="3" height="20" rx=".4" fill="currentColor"/>
        <rect x="19"  y="12" width="3" height="13" rx=".4" fill="currentColor"/>
        <rect x="23.5" y="7" width="3" height="18" rx=".4" fill="currentColor"/>
        <rect x="28"  y="14" width="3.5" height="11" rx=".4" fill="currentColor"/>
        <line x1="0" y1="25" x2="32" y2="25" stroke="currentColor" stroke-width="1.5"/>
      </svg>
      <span class="font-display font-black text-[1.35rem] leading-none italic text-oslo">
        Min<span class="not-italic" style="color:#111827">Oslo</span>
      </span>
    </a>

    <!-- Desktop-nav -->
    <nav class="hidden md:flex items-center gap-6 text-xs font-bold tracking-widest uppercase"
         style="color:#6b7280">
      <a href="#nyheter"    class="hover:text-oslo transition-colors duration-150">Nyheter</a>
      <a href="#politilogg" class="hover:text-oslo transition-colors duration-150">Politilogg</a>
      <button onclick="oppdater()"
              class="hover:text-oslo transition-colors duration-150 cursor-pointer bg-transparent border-0 p-0">
        Oppdater
      </button>
    </nav>

    <!-- Vær-widget -->
    <div class="flex items-center gap-1.5 bg-gray-50 border border-gray-200
                rounded-full px-3 py-1 text-sm font-bold shrink-0 min-w-[70px]"
         style="color:#374151">
      <span id="w-emoji" class="text-base leading-none">–</span>
      <span id="w-temp"  class="tabular-nums">–°</span>
    </div>
  </div>
</header>

<main class="max-w-screen-xl mx-auto px-4 sm:px-6 py-7">

  <!-- ══ NYHETER ═══════════════════════════════════════════ -->
  <section id="nyheter">
    <div class="flex items-center justify-between mb-5">
      <div class="flex items-center gap-3">
        <h2 class="font-display font-black text-xl" style="color:#111827">Siste nytt</h2>
        <span class="text-[10px] font-bold tracking-widest uppercase" style="color:#9ca3af">Oslo</span>
      </div>
      <span class="text-xs font-mono" style="color:#9ca3af">{{ oppdatert }}</span>
    </div>

    {% if nyheter %}

    <!-- HERO-SAK: første sak, full bredde -->
    {% set h = nyheter[0] %}
    <article class="card-in bg-white rounded-2xl shadow-sm overflow-hidden mb-6
                    hover:shadow-md transition-shadow duration-200 cursor-pointer group"
             onclick="window.open('{{ h.kilde_url }}','_blank')">
      {% if h.bilde_url %}
      <div class="w-full aspect-video overflow-hidden bg-gray-100">
        <img src="{{ h.bilde_url }}" alt=""
             class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-[1.02]"
             onerror="this.parentElement.style.display='none'">
      </div>
      {% endif %}
      <div class="p-5 sm:p-7">
        <div class="flex items-center gap-2 mb-3">
          <span class="text-[10px] font-bold tracking-wider uppercase text-white px-2 py-0.5 rounded"
                style="background:{{ h.badge_farge }}">{{ h.badge }} {{ h.kilde_navn }}</span>
          <span class="text-[11px] font-mono" style="color:#9ca3af">{{ h.publisert }}</span>
        </div>
        <h3 class="font-display font-black text-2xl sm:text-[1.75rem] leading-tight mb-3
                   group-hover:text-oslo transition-colors duration-150"
            style="color:#111827">{{ h.overskrift }}</h3>
        <p class="card-body-text leading-relaxed text-base line-clamp-3">{{ h.ingress }}</p>
        <span class="inline-block mt-4 text-xs font-bold border-b pb-px
                     hover:opacity-70 transition-opacity"
              style="color:#1a4f8a;border-color:#1a4f8a">↗ {{ h.kilde_tekst }}</span>
      </div>
    </article>

    <!-- GRID: resten av sakene -->
    {% if nyheter|length > 1 %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {% for art in nyheter[1:] %}
      <article class="card-in bg-white rounded-2xl shadow-sm overflow-hidden
                      hover:shadow-md transition-shadow duration-200 cursor-pointer group flex flex-col"
               onclick="window.open('{{ art.kilde_url }}','_blank')">
        {% if art.bilde_url %}
        <div class="w-full aspect-video overflow-hidden bg-gray-100">
          <img src="{{ art.bilde_url }}" alt=""
               class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
               onerror="this.parentElement.style.display='none'">
        </div>
        {% endif %}
        <div class="p-4 flex flex-col flex-1">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-[9px] font-bold tracking-wider uppercase text-white px-1.5 py-0.5 rounded"
                  style="background:{{ art.badge_farge }}">{{ art.badge }} {{ art.kilde_navn }}</span>
            <span class="text-[10px] font-mono" style="color:#9ca3af">{{ art.publisert }}</span>
          </div>
          <h3 class="font-display font-black text-[1.05rem] leading-snug mb-2
                     group-hover:text-oslo transition-colors duration-150 flex-1"
              style="color:#111827">{{ art.overskrift }}</h3>
          <p class="card-body-text text-sm leading-relaxed line-clamp-3 mb-3">{{ art.ingress }}</p>
          <span class="text-xs font-bold border-b pb-px w-fit mt-auto
                       hover:opacity-70 transition-opacity"
                style="color:#1a4f8a;border-color:#1a4f8a">↗ {{ art.kilde_tekst }}</span>
        </div>
      </article>
      {% endfor %}
    </div>
    {% endif %}

    {% else %}
    <div class="bg-white rounded-2xl shadow-sm p-10 text-center">
      <p class="text-sm" style="color:#9ca3af">Ingen saker hentet akkurat nå. Prøv igjen om litt.</p>
    </div>
    {% endif %}
  </section>

  <!-- ══ POLITILOGG ════════════════════════════════════════ -->
  <section id="politilogg" class="mt-12">
    <div class="flex items-center gap-3 mb-5">
      <span class="pulse-r w-2 h-2 rounded-full bg-oslo shrink-0 inline-block"></span>
      <h2 class="font-display font-black text-xl" style="color:#111827">Politilogg</h2>
      <span class="text-[10px] font-bold tracking-widest uppercase text-oslo">Live · siste 48t</span>
    </div>

    {% if politi %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {% for p in politi %}
      <a href="{{ p.url }}" target="_blank" rel="noopener"
         class="card-in block rounded-2xl p-4 no-underline group
                transition-colors duration-200 hover:opacity-90"
         style="background:#05101f;color:inherit">
        <div class="flex items-start justify-between gap-3 mb-2">
          <span class="text-[10px] font-mono font-bold text-oslo tracking-wide">🚔 {{ p.tid }}</span>
          <span class="text-[10px] font-mono shrink-0" style="color:#4a7aaa">📍 {{ p.sted }}</span>
        </div>
        <p class="text-sm leading-relaxed line-clamp-3 group-hover:opacity-100 transition-opacity"
           style="color:#c8dfff">{{ p.tekst }}</p>
        <span class="inline-block mt-2.5 text-[10px] font-mono border-b pb-px opacity-75 group-hover:opacity-100"
              style="color:#4a8fd4;border-color:#4a8fd4">↗ Les hos Politiloggen</span>
      </a>
      {% endfor %}
    </div>
    {% else %}
    <div class="rounded-2xl p-8 text-center" style="background:#05101f">
      <p class="text-sm mb-2" style="color:#4a7aaa">Ingen meldinger siste 48 timer.</p>
      <a href="https://politiloggen.politiet.no" target="_blank"
         class="text-xs border-b" style="color:#4a8fd4;border-color:#4a8fd4">
         ↗ Se politiloggen direkte</a>
    </div>
    {% endif %}
  </section>

</main>

<!-- ══ FOOTER ════════════════════════════════════════════════ -->
<footer class="mt-16 border-t bg-white" style="border-color:#f3f4f6">
  <div class="max-w-screen-xl mx-auto px-4 sm:px-6 py-6
              flex flex-col sm:flex-row items-center justify-between gap-3
              text-xs" style="color:#9ca3af">
    <span class="font-display font-bold text-sm italic text-oslo">MinOslo</span>
    <span>Politiloggen · Oslo kommune · NRK Stor-Oslo · eInnsyn</span>
    <span class="font-mono">Oppdateres hvert 5. min</span>
  </div>
</footer>

<!-- ══ SCRIPTS ═══════════════════════════════════════════════ -->
<script>
// Vær-widget: hentes fra /api/vaer etter at siden har lastet
fetch('/api/vaer')
  .then(r => r.json())
  .then(d => {
    document.getElementById('w-emoji').textContent = d.emoji || '🌡️';
    document.getElementById('w-temp').textContent  = d.temp + '°';
  })
  .catch(() => {
    document.getElementById('w-temp').textContent = '–°';
  });

// Tøm cache og last siden på nytt
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
    data = _hent_alt()
    ts   = data["ts"]
    oppdatert = ts.strftime("%H:%M") if ts else "–"
    return render_template_string(
        HTML,
        nyheter   = data["nyheter"],
        politi    = data["politi"],
        oppdatert = oppdatert,
    )

@app.route("/api/vaer")
def api_vaer():
    return jsonify(_hent_vær())

@app.route("/api/oppdater", methods=["POST"])
def api_oppdater():
    _hent_alt(force=True)
    return jsonify({"ok": True})

@app.route("/robots.txt")
def robots():
    return "User-agent: *\nDisallow:\n", 200, {"Content-Type": "text/plain"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    _hent_alt()   # varm opp cache ved oppstart
    app.run(host="0.0.0.0", port=port, debug=False)
