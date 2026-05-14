"""
MinOslo.no — Flask-app
=======================
Start lokalt:  python app.py
Start Render:  gunicorn app:app
"""

import os, re, html as _html, json, logging
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from threading import Lock

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, jsonify

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("minoslo")

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────
# NORSK TID
# ─────────────────────────────────────────────────────────────
def _nå() -> datetime:
    u = datetime.now(timezone.utc)
    off = 2 if (
        datetime(u.year, 3, 25, 1, tzinfo=timezone.utc) <= u <
        datetime(u.year, 10, 25, 1, tzinfo=timezone.utc)
    ) else 1
    return u.astimezone(timezone(timedelta(hours=off)))

_TZ = _nå().tzinfo

# ─────────────────────────────────────────────────────────────
# HTTP-KONFIG
# ─────────────────────────────────────────────────────────────
HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "nb-NO,nb;q=0.9",
}
BOT_UA = {"User-Agent": "MinOsloBot/1.0 (shanebusiness99@gmail.com)"}
# Politiloggen og MET.no krever begge BOT_UA for å ikke bli blokkert.
# HDRS brukes til RSS-henting (nrk, oslo, einnsyn).
TIMEOUT = 6

# ─────────────────────────────────────────────────────────────
# BILDER
# Kun statisk OSM-kart ved gjenkjent adresse — ingen generelle
# illustrasjonsbilder eller Unsplash-placeholders.
# Saker uten adresse vises som rene tekst-kort (ingen tom bildeboks).
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# REGEX
# ─────────────────────────────────────────────────────────────
# Oslo-filter: utvidet med kjente steder, gater og nabolag
OSLO_RE = re.compile(
    r"\b(Oslo|Grünerløkka|Frogner|Sagene|Majorstuen|Alna|Bjerke|Grorud|"
    r"Nordstrand|Nordre Aker|Vestre Aker|Østensjø|Stovner|Gamle Oslo|"
    r"St\.?\s*Hanshaugen|Hanshaugen|Sentrum|Bislett|Tøyen|Grønland|"
    r"Holmlia|Manglerud|Lambertseter|Skullerud|Mortensrud|Romsås|"
    r"Furuset|Ellingsrud|Haugerud|Trasop|Ulvern|Røa|Vinderen|"
    r"Slemdal|Grefsen|Kjelsås|Nydalen|Sandaker|Torshov|Sinsen|"
    r"Storo|Lilleborg|Ullevål|Rikshospitalet|Gaustad|Sogn|"
    r"Majorstua|Homansbyen|Solli|Skøyen|Lysaker|Bygdøy|"
    r"Aker Brygge|Tjuvholmen|Vippetangen|Bjørvika|Sørenga|"
    r"Gamlebyen|Grønland|Tøyen|Kampen|Vålerenga|Etterstad|"
    r"Helsfyr|Bryn|Brynseng|Ensjø|Teisen|Løren|"
    r"Ulvensplitten|Alfaset|Lindeberg|Trosterud|Grorud|"
    r"Rommen|Ammerud|Haugenstua|Fossum|Stovner|"
    r"Hvam|Kalbakken|Vestli|Skovdal|Rødtvet|Veitvet|"
    r"Karl Johans|Aker|Sentrum|Rådhuset|Stortorvet)\b", re.I
)

# Utelukk-filter: kun harde nasjonale/internasjonale nøkkelord
EKSKL = re.compile(
    r"\b(utenriks|verden|internasjonal|Europa|USA|Russland|Ukraina|"
    r"Israel|Gaza|Kina|Storbritannia|Premier.?League|Champions League|"
    r"Eliteserien|landslaget|VM |EM |OL|Nobel|Stortinget|"
    r"regjeringen|statsminister|Finansdepartement|fjellbygd|Viken|"
    r"Trondheim|Bergen|Stavanger|Tromsø|Bodø|Drammen|Ringerike|"
    r"Hamar|Lillehammer|Fredrikstad|Sarpsborg|Moss|Halden)\b", re.I
)
GATE_RE = re.compile(
    r"\b([A-ZÆØÅ][a-zæøå]+(?:gate|gata|vei|veien|allé|alléen|plass|plassen|"
    r"torg|torget|brygge|bryggen|kaia|kaien|bakke|bakken|løkka|parken|stien)"
    r"(?:\s+\d+[A-Za-z]?)?)\b", re.U
)

# ─────────────────────────────────────────────────────────────
# HJELPERE
# ─────────────────────────────────────────────────────────────
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
        except: pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_TZ)
    except: return None

def _dstr(dt: datetime | None, raa: str = "") -> str:
    return dt.strftime("%-d. %b %Y, %H:%M") if dt else (raa[:10] or "–")

def _oslo_ok(tittel: str, desc: str) -> bool:
    t = f"{tittel} {desc}"
    if EKSKL.search(t): return False
    return bool(OSLO_RE.search(t))

# ─────────────────────────────────────────────────────────────
# BILDE-LOGIKK
# ─────────────────────────────────────────────────────────────
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
            headers=BOT_UA, timeout=3,
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
        log.warning(f"OSM-kart feil for '{adresse}': {e}")
        with _osm_lock: _osm_cache[adresse] = None
        return None

def _berik_bilde(art: dict) -> dict:
    """
    Sett bilde_url KUN hvis saken inneholder en gjenkjennelig adresse/gate.
    Ingen generelle illustrasjonsbilder — saker uten adresse er rene tekst-kort.
    """
    if art.get("bilde_url", "").startswith("http"):
        return art   # manuelt satt bilde — behold
    tekst = f"{art.get('overskrift','')} {art.get('ingress','')}"
    for gate in GATE_RE.findall(tekst):
        url = _osm_png(gate)
        if url:
            return {**art, "bilde_url": url, "bilde_type": "kart"}
    # Ingen adresse funnet → tom bilde_url (kortet viser kun tekst)
    return {**art, "bilde_url": "", "bilde_type": "ingen"}

# ─────────────────────────────────────────────────────────────
# VÆR  (MET.no Locationforecast 2.0 — gratis, ingen nøkkel)
# ─────────────────────────────────────────────────────────────
_vær_cache: dict = {}
_vær_ts: datetime | None = None
_vær_lock = Lock()

def _hent_vær() -> dict:
    global _vær_cache, _vær_ts
    # Streng cache-sjekk: returner cachet resultat hvis < 30 min gammelt
    with _vær_lock:
        if _vær_ts and (_nå() - _vær_ts).total_seconds() < 1800:
            return _vær_cache
    try:
        r = requests.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": "59.9139", "lon": "10.7522"},
            # MET.no blokkerer requests uten identifiserende User-Agent (gir tom respons/403)
            headers={"User-Agent": "MinOsloBot/1.0 (shanebusiness99@gmail.com)"},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        now    = data["properties"]["timeseries"][0]["data"]
        inst   = now["instant"]["details"]
        next1h = now.get("next_1_hours", {}).get("summary", {})
        symbol = next1h.get("symbol_code", "")
        SYMBOL_EMOJI = {
            "clearsky": "☀️", "fair": "🌤️", "partlycloudy": "⛅",
            "cloudy": "☁️", "fog": "🌫️", "lightrain": "🌦️",
            "rain": "🌧️", "heavyrain": "⛈️", "lightsnow": "🌨️",
            "snow": "❄️", "sleet": "🌨️", "thunder": "⛈️",
        }
        emoji  = next((v for k, v in SYMBOL_EMOJI.items() if k in symbol), "🌡️")
        temp   = round(inst.get("air_temperature", 0))
        result = {"temp": temp, "emoji": emoji}
        log.info(f"Vær hentet: {temp}° {symbol}")
        with _vær_lock:
            _vær_cache = result
            _vær_ts = _nå()
        return result
    except Exception as e:
        log.error(f"VÆR FEIL: {type(e).__name__}: {e}")
        # Returner cachet verdi hvis finnes, ellers fallback
        with _vær_lock:
            return _vær_cache if _vær_cache else {"temp": "–", "emoji": "🌡️"}

# ─────────────────────────────────────────────────────────────
# DATA-HENTING
# ─────────────────────────────────────────────────────────────
_data_cache: dict = {"politi": [], "nyheter": [], "ts": None}
_data_lock = Lock()

def _hent_politi() -> list[dict]:
    """
    Politiloggen API — henter siste 48 timer fra Oslo.
    Bruker BOT_UA (ikke HDRS) for å unngå HTTP 429 fra Politiet.
    Logger full feilmelding til konsollen ved feil.
    """
    url = "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=40"
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "MinOsloBot/1.0 (shanebusiness99@gmail.com)"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        raw = r.json()
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
                "tekst": tekst or tittel,
                "tid": _dstr(dt, tidsp),
                "sted": sted,
                "url": link,
                "dt": dt or (_nå() - timedelta(hours=24)),
            })
        ut.sort(key=lambda x: x["dt"], reverse=True)
        log.info(f"Politiloggen: {len(ut)} meldinger")
        return ut[:20]
    except Exception as e:
        log.error(f"POLITILOGG FEIL: {type(e).__name__}: {e} | URL: {url}")
        return []

def _hent_rss(kilde: dict) -> list[dict]:
    alle_url = [kilde["url"]] + kilde.get("url_alt", [])
    xml = ""
    for url in alle_url:
        try:
            r = requests.get(url, headers=HDRS, timeout=TIMEOUT)
            if r.ok and "<" in r.text:
                xml = r.text
                break
            log.warning(f"{kilde['navn']} HTTP {r.status_code} fra {url}")
        except Exception as e:
            log.warning(f"{kilde['navn']} feil på {url}: {e}")
    if not xml:
        log.error(f"{kilde['navn']}: alle URL-er feilet")
        return []
    try:
        soup = BeautifulSoup(xml, "lxml-xml")
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
            desc   = g("description", "summary", "content")
            pub    = g("pubDate", "published", "updated", "dc:date")
            lenke  = g("link")
            if not lenke:
                lt = item.find("link")
                if lt: lenke = lt.get("href", "") or _rens(lt.get_text())
            dt = _parse_dato(pub)
            if dt and dt < grense: continue
            if kilde.get("oslo_filter") and not _oslo_ok(tittel, desc): continue
            # Maks ett avsnitt, maks 280 tegn
            ingress = desc[:280].rstrip()
            if len(desc) > 280: ingress += "…"
            art = {
                "overskrift": tittel,
                "ingress": ingress,
                "publisert": _dstr(dt, pub),
                "kilde_url": lenke or kilde["link"],
                "kilde_navn": kilde["navn"],
                "kilde_tekst": f"Les hos {kilde['navn']}",
                "badge": kilde["badge"],
                "badge_farge": kilde["farge"],
                "kategori": kilde.get("kategori", "annet"),
                "bilde_url": "",
                "dt": dt or (_nå() - timedelta(hours=6)),
            }
            ut.append(_berik_bilde(art))
        ut.sort(key=lambda x: x["dt"], reverse=True)
        log.info(f"{kilde['navn']}: {len(ut)} saker")
        return ut[:14]
    except Exception as e:
        log.error(f"{kilde['navn']} parse-feil: {type(e).__name__}: {e}")
        return []

KILDER = [
    {
        "id": "oslo", "url": "https://aktuelt.oslo.kommune.no/?format=rss",
        "url_alt": ["https://www.oslo.kommune.no/rss/", "https://aktuelt.oslo.kommune.no/feed/"],
        "navn": "Oslo kommune", "badge": "K", "farge": "#1a6632",
        "kategori": "kommune", "max_alder": timedelta(days=7),
        "link": "https://aktuelt.oslo.kommune.no", "oslo_filter": False,
    },
    {
        "id": "nrk", "url": "https://www.nrk.no/stor-oslo/toppsaker.rss",
        "url_alt": ["https://www.nrk.no/stor-oslo/feed/", "https://www.nrk.no/toppsaker.rss"],
        "navn": "NRK", "badge": "N", "farge": "#c8001e",
        "kategori": "nrk", "max_alder": timedelta(days=7),
        "link": "https://www.nrk.no/stor-oslo/", "oslo_filter": True,
    },
    {
        "id": "einnsyn", "url": "https://einnsyn.no/rss?q=Oslo+kommune&antall=20",
        "navn": "eInnsyn", "badge": "E", "farge": "#4a3580",
        "kategori": "einnsyn", "max_alder": timedelta(days=7),
        "link": "https://einnsyn.no", "oslo_filter": False,
    },
]

PLACEHOLDER = [
    {"overskrift": "Oslos beste turtips denne helgen", "ingress": "Oslomarka tilbyr fantastiske turer for alle nivåer — her er ukens utvalgte ruter.", "publisert": _nå().strftime("%-d. %b"), "kilde_url": "https://ut.no", "kilde_navn": "ut.no", "kilde_tekst": "Les hos ut.no", "badge": "T", "badge_farge": "#1a6632", "kategori": "annet", "bilde_url": "", "dt": _nå() - timedelta(hours=1)},
    {"overskrift": "Hva skjer i Oslo denne uken?", "ingress": "Konserter, markeder og utstillinger — sjekk Visit Oslo for oppdatert program med de beste arrangementene.", "publisert": _nå().strftime("%-d. %b"), "kilde_url": "https://visitoslo.com", "kilde_navn": "Visit Oslo", "kilde_tekst": "Les hos Visit Oslo", "badge": "V", "badge_farge": "#1a4f8a", "kategori": "annet", "bilde_url": "", "dt": _nå() - timedelta(hours=2)},
    {"overskrift": "Ruter: Slik reiser du smartest i Oslo", "ingress": "T-bane, trikk og buss dekker hele Oslo. Last ned Ruter-appen for sanntidsinformasjon om avganger og forsinkelser.", "publisert": _nå().strftime("%-d. %b"), "kilde_url": "https://ruter.no", "kilde_navn": "Ruter", "kilde_tekst": "Les hos Ruter", "badge": "R", "badge_farge": "#8a1a1a", "kategori": "annet", "bilde_url": "", "dt": _nå() - timedelta(hours=3)},
]

def _hent_alt(force: bool = False) -> dict:
    global _data_cache
    with _data_lock:
        ts = _data_cache.get("ts")
        # Bruker total_seconds() — .seconds returnerer bare 0–59 og respekterer ikke cache riktig
        if not force and ts and (_nå() - ts).total_seconds() < 300:
            return _data_cache
    politi = _hent_politi()
    nyheter = []
    for k in KILDER:
        nyheter.extend(_hent_rss(k))
    nyheter.sort(key=lambda x: x["dt"], reverse=True)
    result = {"politi": politi, "nyheter": nyheter or list(PLACEHOLDER), "ts": _nå()}
    with _data_lock:
        _data_cache = result
    return result

# ─────────────────────────────────────────────────────────────
# HTML-MAL
# ─────────────────────────────────────────────────────────────
HTML = r"""<!doctype html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MinOslo — Oslo i dag</title>
<meta name="description" content="Ferske nyheter, politilogg og hva som skjer i Oslo akkurat nå.">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,400;1,700&family=Geist:wght@300;400;500;700&display=swap" rel="stylesheet">
<script>
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: {
          display: ['"Playfair Display"', 'Georgia', 'serif'],
          sans: ['Geist', 'system-ui', 'sans-serif'],
        },
        colors: {
          oslo: '#c8001e',
          'oslo-dark': '#a0001a',
        }
      }
    }
  }
</script>
<style>
  /* Stagger-animasjon for kort */
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .card-anim { animation: fadeUp .45s ease both; }
  .card-anim:nth-child(1) { animation-delay: .05s }
  .card-anim:nth-child(2) { animation-delay: .12s }
  .card-anim:nth-child(3) { animation-delay: .19s }
  .card-anim:nth-child(4) { animation-delay: .26s }
  .card-anim:nth-child(5) { animation-delay: .33s }
  .card-anim:nth-child(6) { animation-delay: .40s }
  .card-anim:nth-child(n+7) { animation-delay: .47s }

  /* Politilogg-puls */
  @keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:.15} }
  .live-dot { animation: pulse-dot 1.4s infinite; }

  /* Smooth scroll */
  html { scroll-behavior: smooth; }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 3px; }
</style>
</head>
<body class="bg-[#F9FAFB] font-sans antialiased text-[#111827]">

<!-- ══ HEADER ════════════════════════════════════════════════ -->
<header class="sticky top-0 z-50 bg-white border-b-2 border-oslo shadow-sm">
  <div class="max-w-screen-xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">

    <!-- Logo -->
    <a href="/" class="flex items-center gap-2 shrink-0 group" title="Til forsiden">
      <!-- Oslo-silhuett SVG (Barcode + Opera) -->
      <svg width="34" height="28" viewBox="0 0 34 28" fill="none" class="text-oslo transition-transform group-hover:scale-105">
        <!-- Operaen -->
        <polygon points="1,27 5,20 9,27" fill="currentColor" opacity=".85"/>
        <!-- Barcode-bygg -->
        <rect x="11" y="10" width="3" height="17" rx=".5" fill="currentColor"/>
        <rect x="15.5" y="6"  width="3" height="21" rx=".5" fill="currentColor"/>
        <rect x="20" y="13" width="3" height="14" rx=".5" fill="currentColor"/>
        <rect x="24.5" y="8"  width="3" height="19" rx=".5" fill="currentColor"/>
        <rect x="29" y="15" width="4" height="12" rx=".5" fill="currentColor"/>
        <!-- Grunnlinje -->
        <line x1="0" y1="27" x2="34" y2="27" stroke="currentColor" stroke-width="1.5"/>
      </svg>
      <span class="font-display font-black text-xl leading-none text-oslo italic">
        Min<span class="text-[#111827] not-italic">Oslo</span>
      </span>
    </a>

    <!-- Nav-lenker (desktop) -->
    <nav class="hidden md:flex items-center gap-5 text-xs font-semibold tracking-wide uppercase text-gray-500">
      <a href="#nyheter"    class="hover:text-oslo transition-colors">Nyheter</a>
      <a href="#politilogg" class="hover:text-oslo transition-colors">Politilogg</a>
      <a href="#oppdater"   onclick="oppdater(event)"
         class="cursor-pointer hover:text-oslo transition-colors">Oppdater</a>
    </nav>

    <!-- Vær-widget -->
    <div id="vær-widget" class="flex items-center gap-1.5 bg-gray-50 border border-gray-200
         rounded-full px-3 py-1 text-sm font-semibold text-gray-700 shrink-0 min-w-[72px]">
      <span id="vær-emoji" class="text-base leading-none">–</span>
      <span id="vær-temp" class="tabular-nums">–°</span>
    </div>
  </div>
</header>

<main class="max-w-screen-xl mx-auto px-4 sm:px-6 py-6">

  <!-- ══ NYHETER ═══════════════════════════════════════════ -->
  <section id="nyheter">
    <div class="flex items-center justify-between mb-5">
      <div class="flex items-center gap-3">
        <h2 class="font-display font-black text-xl text-[#111827]">Siste nytt</h2>
        <span class="text-[10px] font-bold tracking-widest uppercase text-gray-400">Oslo</span>
      </div>
      <span class="text-xs text-gray-400 font-mono">{{ oppdatert }}</span>
    </div>

    {% if nyheter %}
    <!-- Hero-sak -->
    {% set h = nyheter[0] %}
    <article class="card-anim bg-white rounded-2xl shadow-sm overflow-hidden mb-6
                    hover:shadow-md transition-shadow duration-200 cursor-pointer group"
             onclick="window.open('{{ h.kilde_url }}','_blank')">
      {% if h.bilde_url %}
      <div class="w-full aspect-video overflow-hidden bg-gray-100">
        <img src="{{ h.bilde_url }}" alt=""
             class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-[1.02]"
             onerror="this.parentElement.style.display='none'">
      </div>
      {% endif %}
      <div class="p-5 sm:p-6">
        <div class="flex items-center gap-2 mb-2.5">
          <span class="text-[10px] font-bold tracking-wider uppercase text-white px-2 py-0.5 rounded"
                style="background:{{ h.badge_farge }}">{{ h.badge }} {{ h.kilde_navn }}</span>
          <span class="text-[11px] text-gray-400 font-mono">{{ h.publisert }}</span>
        </div>
        <h3 class="font-display font-bold text-2xl sm:text-3xl leading-tight text-[#111827] mb-3
                   group-hover:text-oslo transition-colors">{{ h.overskrift }}</h3>
        <p class="text-[#374151] leading-relaxed text-base line-clamp-3">{{ h.ingress }}</p>
        <span class="inline-block mt-4 text-xs font-semibold text-[#1a4f8a] border-b border-[#1a4f8a]
                     pb-px hover:opacity-70 transition-opacity">↗ {{ h.kilde_tekst }}</span>
      </div>
    </article>

    <!-- Grid resten -->
    {% if nyheter|length > 1 %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      {% for art in nyheter[1:] %}
      <article class="card-anim bg-white rounded-2xl shadow-sm overflow-hidden
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
            <span class="text-[10px] text-gray-400 font-mono">{{ art.publisert }}</span>
          </div>
          <h3 class="font-display font-bold text-lg leading-snug text-[#111827] mb-2
                     group-hover:text-oslo transition-colors flex-1">{{ art.overskrift }}</h3>
          <p class="text-[#374151] text-sm leading-relaxed line-clamp-3 mb-3">{{ art.ingress }}</p>
          <span class="text-xs font-semibold text-[#1a4f8a] border-b border-[#1a4f8a]
                       pb-px w-fit hover:opacity-70 transition-opacity mt-auto">↗ {{ art.kilde_tekst }}</span>
        </div>
      </article>
      {% endfor %}
    </div>
    {% endif %}
    {% else %}
    <div class="bg-white rounded-2xl shadow-sm p-8 text-center">
      <p class="text-gray-400 text-sm">Ingen saker hentet akkurat nå. Prøv igjen om litt.</p>
    </div>
    {% endif %}
  </section>

  <!-- ══ POLITILOGG ════════════════════════════════════════ -->
  <section id="politilogg" class="mt-10">
    <div class="flex items-center gap-3 mb-5">
      <div class="live-dot w-2 h-2 rounded-full bg-oslo shrink-0"></div>
      <h2 class="font-display font-black text-xl text-[#111827]">Politilogg</h2>
      <span class="text-[10px] font-bold tracking-widest uppercase text-oslo">Live · siste 48t</span>
    </div>

    {% if politi %}
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {% for p in politi %}
      <a href="{{ p.url }}" target="_blank" rel="noopener"
         class="card-anim block bg-[#05101f] rounded-2xl p-4 hover:bg-[#0a1a30]
                transition-colors duration-200 group no-underline">
        <div class="flex items-start justify-between gap-3 mb-2">
          <span class="text-[10px] font-mono font-bold text-oslo tracking-wide">
            🚔 {{ p.tid }}
          </span>
          <span class="text-[10px] font-mono text-[#4a7aaa] shrink-0">📍 {{ p.sted }}</span>
        </div>
        <p class="text-[#c8dfff] text-sm leading-relaxed line-clamp-3
                  group-hover:text-white transition-colors">{{ p.tekst }}</p>
        <span class="inline-block mt-2.5 text-[10px] font-mono text-[#4a8fd4]
                     border-b border-[#4a8fd4] pb-px opacity-80 group-hover:opacity-100">
          ↗ Les hos Politiloggen
        </span>
      </a>
      {% endfor %}
    </div>
    {% else %}
    <div class="bg-[#05101f] rounded-2xl p-6 text-center">
      <p class="text-[#4a7aaa] text-sm mb-2">Ingen meldinger siste 48 timer.</p>
      <a href="https://politiloggen.politiet.no" target="_blank"
         class="text-[#4a8fd4] text-xs border-b border-[#4a8fd4]">↗ Se politiloggen direkte</a>
    </div>
    {% endif %}
  </section>

</main>

<!-- ══ FOOTER ════════════════════════════════════════════════ -->
<footer class="mt-16 border-t border-gray-100 bg-white">
  <div class="max-w-screen-xl mx-auto px-4 sm:px-6 py-6 flex flex-col sm:flex-row
              items-center justify-between gap-3 text-xs text-gray-400">
    <span class="font-display font-bold text-sm text-oslo italic">MinOslo</span>
    <span>Kilder: Politiloggen · Oslo kommune · NRK Stor-Oslo · eInnsyn</span>
    <span class="font-mono">Data oppdateres hvert 5. minutt</span>
  </div>
</footer>

<!-- ══ SCRIPTS ═══════════════════════════════════════════════ -->
<script>
// Hent vær
fetch('/api/vaer')
  .then(r => r.json())
  .then(d => {
    document.getElementById('vær-emoji').textContent = d.emoji;
    document.getElementById('vær-temp').textContent  = d.temp + '°';
  })
  .catch(() => {
    document.getElementById('vær-temp').textContent = '–°';
  });

// Oppdater-knapp
function oppdater(e) {
  e.preventDefault();
  fetch('/api/oppdater', { method: 'POST' })
    .then(() => window.location.reload())
    .catch(() => window.location.reload());
}

// Auto-refresh hvert 5. minutt
setTimeout(() => window.location.reload(), 5 * 60 * 1000);
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────
# FLASK-RUTER
# ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    data = _hent_alt()
    oppdatert = data["ts"].strftime("%H:%M") if data["ts"] else "–"
    return render_template_string(
        HTML,
        nyheter=data["nyheter"],
        politi=data["politi"],
        oppdatert=oppdatert,
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
    # Varm opp data ved oppstart
    _hent_alt()
    app.run(host="0.0.0.0", port=port, debug=False)
