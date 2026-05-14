"""
MinOslo — Produksjonsversjon
==============================
Deploy:  Render.com
Start:   streamlit run app.py --server.port $PORT --server.address 0.0.0.0

Design-filosofi: Editorial/avis-stil inspirert av NYT og Aftenposten.
  Gjennomtenkt typografi (Fraunces + Lato), Oslo-rød aksentt, rent grid.

Datakilder:
  • Politiloggen  api.politiet.no   — JSON, siste 24t
  • Oslo kommune  aktuelt.oslo.kommune.no — RSS, siste 7d
  • NRK Stor-Oslo nrk.no/stor-oslo/feed/ — Atom, siste 7d, kun Oslo-saker
  • eInnsyn       einnsyn.no/rss    — RSS, siste 7d

Bilder:
  • OSM staticmap.openstreetmap.de — statisk PNG for adressesaker
  • Unsplash per kategori           — statiske URL-er, ingen API-nøkkel
  • Garantert Oslo-fallback         — aldri tomme bokser
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import re
import html as html_mod

st.set_page_config(
    page_title="MinOslo",
    page_icon="🗞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════════════
# NORSK TID
# ════════════════════════════════════════════════════════════════
def _oslo_now() -> datetime:
    utc = datetime.now(timezone.utc)
    dst_s = datetime(utc.year, 3, 25, 1, tzinfo=timezone.utc)
    dst_e = datetime(utc.year, 10, 25, 1, tzinfo=timezone.utc)
    return utc.astimezone(timezone(timedelta(hours=2 if dst_s <= utc < dst_e else 1)))

_OSLO_TZ = _oslo_now().tzinfo

# ════════════════════════════════════════════════════════════════
# KONSTANTER
# ════════════════════════════════════════════════════════════════
ADMIN_PW     = "løkka2024"
HTTP_TIMEOUT = 5
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
}
OSM_HEADERS = {"User-Agent": "MinOsloBot/1.0 (shane@example.com)"}

MAX_ALDER_POLITI  = timedelta(hours=24)
MAX_ALDER_NYHETER = timedelta(days=7)

OSLO_FALLBACK = (
    "https://images.unsplash.com/photo-1583907608452-7260268ec9a8"
    "?auto=format&fit=crop&q=80&w=900&h=500"
)

KAT_BILDER = {
    "politilogg":       "https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&q=80&w=900&h=500",
    "kommune":          "https://images.unsplash.com/photo-1446822775955-c34f483b410b?auto=format&fit=crop&q=80&w=900&h=500",
    "nrk":              "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&q=80&w=900&h=500",
    "einnsyn":          "https://images.unsplash.com/photo-1464938050520-ef2270bb8ce8?auto=format&fit=crop&q=80&w=900&h=500",
    "byggesak":         "https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&q=80&w=900&h=500",
    "skjenkebevilling": "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?auto=format&fit=crop&q=80&w=900&h=500",
    "regulering":       "https://images.unsplash.com/photo-1476231682828-37e571bc172f?auto=format&fit=crop&q=80&w=900&h=500",
    "annet":            "https://images.unsplash.com/photo-1583907608452-7260268ec9a8?auto=format&fit=crop&q=80&w=900&h=500",
}

# Oslo-bydeler for positiv filter på politilogg-saker
OSLO_BYDELER_RE = re.compile(
    r"\bOslo|Grünerløkka|Frogner|Sagene|Majorstuen|Alna|Bjerke|Grorud|"
    r"Nordstrand|Nordre Aker|Vestre Aker|Østensjø|Stovner|Gamle Oslo|"
    r"St\.?\s*Hanshaugen|Sentrum|Bislett|Tøyen|Grønland|Manglerud|"
    r"Lambertseter|Skullerud|Holmlia|Søndre Nordstrand\b",
    re.IGNORECASE,
)

NRK_EKSKLUDER = re.compile(
    r"\b(utenriks|verden|internasjonal|Europa|USA|Russland|Ukraina|Israel|"
    r"Gaza|Kina|Storbritannia|Premier.?League|Champions League|Eliteserien|"
    r"landslaget|VM |EM |Nobel|Stortinget|regjeringen|statsminister|"
    r"Trondheim|Bergen|Stavanger|Tromsø|Kristiansand|Bodø|Drammen)\b",
    re.IGNORECASE,
)

KILDER = [
    {
        "id": "politiloggen",
        "url": "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=30",
        "navn": "Politiloggen", "badge": "P", "farge": "#cd3d33",
        "type": "politilogg", "max_alder": MAX_ALDER_POLITI,
        "link": "https://politiloggen.politiet.no",
    },
    {
        "id": "oslo",
        "url": "https://aktuelt.oslo.kommune.no/?format=rss",
        "url_alt": ["https://www.oslo.kommune.no/rss/", "https://aktuelt.oslo.kommune.no/feed/"],
        "navn": "Oslo kommune", "badge": "K", "farge": "#1a6632",
        "type": "rss", "kategori": "kommune", "max_alder": MAX_ALDER_NYHETER,
        "link": "https://aktuelt.oslo.kommune.no", "oslo_filter": False,
    },
    {
        "id": "nrk",
        "url": "https://www.nrk.no/stor-oslo/feed/",
        "url_alt": ["https://www.nrk.no/toppsaker.rss"],
        "navn": "NRK", "badge": "N", "farge": "#cd3d33",
        "type": "rss", "kategori": "nrk", "max_alder": MAX_ALDER_NYHETER,
        "link": "https://www.nrk.no/stor-oslo/", "oslo_filter": True,
    },
    {
        "id": "einnsyn",
        "url": "https://einnsyn.no/rss?q=Oslo+kommune&antall=20",
        "navn": "eInnsyn", "badge": "E", "farge": "#4a3580",
        "type": "rss", "kategori": "einnsyn", "max_alder": MAX_ALDER_NYHETER,
        "link": "https://einnsyn.no", "oslo_filter": False,
    },
]

PLACEHOLDER_SAKER = [
    {
        "overskrift": "Oslos beste turtips denne helgen",
        "ingress": "Oslomarka tilbyr fantastiske turer året rundt — for store og små.",
        "publisert": _oslo_now().strftime("%-d. %b %Y"),
        "kilde_url": "https://www.ut.no/omrade/3230/",
        "kilde_navn": "ut.no", "kilde_tekst": "Les hos ut.no",
        "badge": "T", "badge_farge": "#1a6632",
        "bydel": "Hele Oslo", "kategori": "annet",
        "bilde_url": OSLO_FALLBACK, "brodtekst": [], "tags": [],
        "sortert_dato": _oslo_now() - timedelta(hours=1),
    },
    {
        "overskrift": "Hva skjer i Oslo denne uken?",
        "ingress": "Oslo har et rikt kulturtilbud. Sjekk Visit Oslo for oppdatert program med konserter og utstillinger.",
        "publisert": _oslo_now().strftime("%-d. %b %Y"),
        "kilde_url": "https://www.visitoslo.com/no/",
        "kilde_navn": "Visit Oslo", "kilde_tekst": "Les hos Visit Oslo",
        "badge": "V", "badge_farge": "#1a4f8a",
        "bydel": "Hele Oslo", "kategori": "annet",
        "bilde_url": "https://images.unsplash.com/photo-1486325212027-8081e485255e?auto=format&fit=crop&q=80&w=900&h=500",
        "brodtekst": [], "tags": [],
        "sortert_dato": _oslo_now() - timedelta(hours=2),
    },
    {
        "overskrift": "Ruter: Slik reiser du smart i Oslo",
        "ingress": "Med Ruter-appen reiser du grønt med t-bane, buss, trikk og båt til alle bydeler i Oslo.",
        "publisert": _oslo_now().strftime("%-d. %b %Y"),
        "kilde_url": "https://ruter.no",
        "kilde_navn": "Ruter", "kilde_tekst": "Les hos Ruter",
        "badge": "R", "badge_farge": "#8a1a1a",
        "bydel": "Hele Oslo", "kategori": "annet",
        "bilde_url": KAT_BILDER["regulering"],
        "brodtekst": [], "tags": [],
        "sortert_dato": _oslo_now() - timedelta(hours=3),
    },
]

BYDELER = [
    "Alle bydeler", "Alna", "Bjerke", "Frogner", "Gamle Oslo", "Grorud",
    "Grünerløkka", "Nordre Aker", "Nordstrand", "Sagene", "St. Hanshaugen",
    "Stovner", "Søndre Nordstrand", "Ullern", "Vestre Aker", "Østensjø",
]
KATEGORIER = [
    "Alle kategorier", "politilogg", "kommune", "nrk", "einnsyn",
    "byggesak", "skjenkebevilling", "regulering", "politisk vedtak", "annet",
]

# ════════════════════════════════════════════════════════════════
# DESIGN-SYSTEM
# Farge-variabler definert én gang, brukt overalt via CSS-klasser.
# Rotproblemet med "bilder usynlige på PC" skyldes at Streamlit
# sitt shadow-DOM stripper inline-stiler med !important.
# Løsning: alle bilde-stiler defineres i <style>-blokken via
# CSS-klasser (ikke inline), og injiseres via st.html() som setter
# dem globalt i dokumentet — ikke inne i en isolert komponent.
# ════════════════════════════════════════════════════════════════

CSS = """
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,700;0,9..144,900;1,9..144,400;1,9..144,700&family=Lato:wght@300;400;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>

/* ═══════════════════════════════════════════════
   CSS-VARIABLER — endre her, virker overalt
   ═══════════════════════════════════════════════ */
:root {
  --bg:          #f8f9fa;
  --bg-card:     #ffffff;
  --bg-header:   #ffffff;
  --bg-sidebar:  #111111;
  --bg-police:   #060d1f;

  --text-1:      #111111;   /* overskrifter */
  --text-2:      #222222;   /* brødtekst — ALLTID mørk */
  --text-3:      #555555;   /* metadata */
  --text-4:      #888888;   /* dato, kilde */
  --text-police: #c8dfff;

  --accent:      #cd3d33;   /* Oslo-rød */
  --accent-dark: #a52e26;
  --accent-blue: #1a4f8a;

  --border:      #e8e6e2;
  --border-card: #ededeb;
  --shadow-sm:   0 1px 4px rgba(0,0,0,.06), 0 2px 12px rgba(0,0,0,.05);
  --shadow-md:   0 4px 16px rgba(0,0,0,.10), 0 1px 4px rgba(0,0,0,.06);
  --shadow-lg:   0 8px 32px rgba(0,0,0,.14), 0 2px 8px rgba(0,0,0,.08);
  --radius:      12px;
  --radius-sm:   8px;
  --radius-img:  12px 12px 0 0;

  --font-display: 'Fraunces', Georgia, serif;
  --font-body:    'Lato', sans-serif;
  --font-mono:    'JetBrains Mono', monospace;
}

/* ═══════════════════════════════════════════════
   RESET & BASE
   ═══════════════════════════════════════════════ */
#MainMenu, footer, header { visibility: hidden !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

html, body, .stApp {
  background: var(--bg) !important;
  font-family: var(--font-body);
  color: var(--text-2);
  -webkit-font-smoothing: antialiased;
}

/* ═══════════════════════════════════════════════
   SIDEBAR
   ═══════════════════════════════════════════════ */
[data-testid="stSidebar"] {
  background: var(--bg-sidebar) !important;
  border-right: 1px solid #1e1e1e !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label {
  color: #999 !important;
  font-size: .73rem !important;
  font-family: var(--font-mono);
  letter-spacing: .05em;
}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stTextArea textarea,
[data-testid="stSidebar"] .stSelectbox > div > div {
  background: #1c1c1c !important;
  color: #ddd !important;
  border-color: #2e2e2e !important;
  font-size: .83rem !important;
}
[data-testid="stSidebar"] hr {
  border-color: #1e1e1e !important;
  margin: .55rem 0 !important;
}
[data-testid="stSidebar"] .stButton > button {
  background: var(--accent) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 6px !important;
  font-family: var(--font-mono) !important;
  font-weight: 500 !important;
  font-size: .68rem !important;
  letter-spacing: .1em;
  text-transform: uppercase;
  width: 100%;
  padding: .52rem !important;
  transition: opacity .15s;
}
[data-testid="stSidebar"] .stButton > button:hover { opacity: .80 !important; }

/* ═══════════════════════════════════════════════
   HEADER — sticky, rød underlinje
   ═══════════════════════════════════════════════ */
.mo-header {
  background: var(--bg-header);
  border-bottom: 3px solid var(--accent);
  position: sticky;
  top: 0;
  z-index: 400;
  box-shadow: 0 1px 6px rgba(0,0,0,.07);
}
.mo-header-inner {
  max-width: 1320px;
  margin: 0 auto;
  padding: 0 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 58px;
}
/* Logo — klikkbar, laster siden på nytt */
.mo-logo {
  font-family: var(--font-display);
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 900;
  font-style: italic;
  color: var(--accent);
  letter-spacing: -.04em;
  text-decoration: none;
  line-height: 1;
  cursor: pointer;
  transition: opacity .15s;
}
.mo-logo:hover { opacity: .75; }
.mo-logo-suffix { color: var(--text-1); font-style: normal; }
.mo-dateline {
  font-family: var(--font-mono);
  font-size: .6rem;
  color: var(--text-4);
  letter-spacing: .12em;
  text-transform: uppercase;
}

/* ═══════════════════════════════════════════════
   SIDE-WRAPPER
   ═══════════════════════════════════════════════ */
.mo-page {
  max-width: 1320px;
  margin: 0 auto;
  padding: 1.75rem 1.5rem 6rem;
}

/* ═══════════════════════════════════════════════
   SEKSJONSTITLER
   ═══════════════════════════════════════════════ */
.mo-section {
  font-family: var(--font-mono);
  font-size: .6rem;
  font-weight: 500;
  letter-spacing: .2em;
  text-transform: uppercase;
  color: var(--text-3);
  border-top: 1.5px solid var(--text-1);
  padding-top: .45rem;
  margin: 2rem 0 1.1rem;
}
.mo-section-red { border-top-color: var(--accent); color: var(--accent); }

/* ═══════════════════════════════════════════════
   KILDE-BADGE
   ═══════════════════════════════════════════════ */
.mo-badge {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: .55rem;
  font-weight: 500;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: #fff;
  padding: .18em .5em .2em;
  border-radius: 4px;
  line-height: 1.4;
  flex-shrink: 0;
}
.mo-meta {
  display: flex;
  align-items: center;
  gap: .4rem;
  flex-wrap: wrap;
  margin-bottom: .3rem;
}
.mo-date {
  font-family: var(--font-mono);
  font-size: .6rem;
  color: var(--text-4);
  letter-spacing: .03em;
}
.mo-src {
  font-family: var(--font-mono);
  font-size: .65rem;
  color: var(--accent-blue);
  text-decoration: none;
  border-bottom: 1px solid var(--accent-blue);
  padding-bottom: 1px;
  display: inline-block;
  margin-top: .55rem;
  transition: opacity .15s;
}
.mo-src:hover { opacity: .7; }

/* ═══════════════════════════════════════════════
   BILDE-KLASSE — dette er løsningen på "bilder
   usynlige på PC". Stilen er i <style>-blokken
   (ikke inline), og st.html() injiserer den
   globalt. CSS-klassen fungerer på alle skjermer.
   ═══════════════════════════════════════════════ */
.mo-img {
  width: 100%;
  height: 220px;
  object-fit: cover;
  display: block;
  border-radius: var(--radius-img);
  /* Ingen !important nødvendig — klassen vinner
     over Streamlit's base-stiler */
}
.mo-img-wrap { line-height: 0; }   /* fjerner whitespace under img */

/* ═══════════════════════════════════════════════
   HERO-KORT (full bredde)
   ═══════════════════════════════════════════════ */
.mo-hero {
  background: var(--bg-card);
  border: 1px solid var(--border-card);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-md);
  margin-bottom: 1.75rem;
}
.mo-hero .mo-img { height: 320px; border-radius: var(--radius-img); }
.mo-hero-body { padding: 1.4rem 1.75rem 1.75rem; }
.mo-hero-ingress {
  font-family: var(--font-body);
  font-size: 1rem;
  line-height: 1.72;
  color: var(--text-2) !important;
  margin: .4rem 0 .65rem;
}

/* ═══════════════════════════════════════════════
   GRID — 3 kol desktop, 2 nettbrett, 1 mobil
   ═══════════════════════════════════════════════ */
.mo-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
  margin-bottom: 1.5rem;
}
.mo-grid-wide {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 1.25rem;
  margin-bottom: 1.25rem;
}

/* ═══════════════════════════════════════════════
   STANDARD KORT
   ═══════════════════════════════════════════════ */
.mo-card {
  background: var(--bg-card);
  border: 1px solid var(--border-card);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  transition: transform .2s ease, box-shadow .2s ease;
}
/* Hover: boks løfter seg lett */
.mo-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
}
.mo-card-body {
  padding: .95rem 1.1rem 1.15rem;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.mo-card-ingress {
  font-size: .85rem;
  line-height: 1.62;
  color: var(--text-2) !important;   /* alltid mørk grå, uansett tema */
  flex: 1;
  margin-top: .3rem;
}

/* ═══════════════════════════════════════════════
   STREAMLIT-KNAPPER SOM ARTIKKELLENKER
   Kritisk for lesbarhet: color satt eksplisitt.
   Ingen z-index/overflow:hidden — hindrer
   klikk-blokkering.
   ═══════════════════════════════════════════════ */
.stButton > button {
  background: transparent !important;
  color: var(--text-1) !important;
  border: none !important;
  border-radius: 0 !important;
  font-family: var(--font-display) !important;
  font-size: clamp(.95rem, 2vw, 1.08rem) !important;
  font-weight: 700 !important;
  font-style: normal !important;
  line-height: 1.22 !important;
  text-align: left !important;
  padding: 0 !important;
  width: 100% !important;
  white-space: normal !important;
  height: auto !important;
  cursor: pointer !important;
  min-height: 44px !important;   /* iOS touch target */
}
.stButton > button:hover { color: var(--accent) !important; }
.stButton > button:focus { box-shadow: none !important; outline: none !important; }

/* ═══════════════════════════════════════════════
   POLITILOGG
   ═══════════════════════════════════════════════ */
.mo-police {
  background: var(--bg-police);
  border: 1px solid #0e1f4a;
  border-radius: var(--radius);
  padding: 1rem;
}
.mo-police-hdr {
  font-family: var(--font-mono);
  font-size: .6rem;
  font-weight: 500;
  letter-spacing: .15em;
  text-transform: uppercase;
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: .4rem;
  margin-bottom: .75rem;
}
.mo-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse 1.4s infinite;
  flex-shrink: 0;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.12} }
.mo-p-item {
  background: #0b1530;
  border: 1px solid #1a2d60;
  border-radius: var(--radius-sm);
  padding: .62rem .8rem;
  margin-bottom: .42rem;
}
.mo-p-time {
  font-family: var(--font-mono);
  font-size: .58rem;
  color: var(--accent);
  font-weight: 500;
  margin-bottom: .14rem;
}
.mo-p-tekst { font-size: .8rem; color: var(--text-police); line-height: 1.5; }
.mo-p-sted  { font-family: var(--font-mono); font-size: .6rem; color: #5a7fa8; margin-top: .12rem; }
.mo-p-link  {
  font-family: var(--font-mono); font-size: .6rem; color: #4a8fd4;
  margin-top: .28rem; text-decoration: none;
  border-bottom: 1px solid #4a8fd4; display: inline;
}

/* ═══════════════════════════════════════════════
   ARTIKKEL FULLVISNING
   ═══════════════════════════════════════════════ */
.mo-article {
  background: var(--bg-card);
  border: 1px solid var(--border-card);
  border-radius: var(--radius);
  padding: 2.25rem;
  box-shadow: var(--shadow-md);
  margin-top: .75rem;
}
.mo-article h1 {
  font-family: var(--font-display);
  font-size: clamp(1.5rem, 4vw, 2.5rem);
  font-weight: 900;
  line-height: 1.1;
  color: var(--text-1) !important;
  margin-bottom: 1rem;
}
.mo-lead {
  font-size: 1.05rem;
  line-height: 1.76;
  color: var(--text-2) !important;
  border-left: 4px solid var(--accent);
  padding-left: 1.1rem;
  margin-bottom: 1.6rem;
}
.mo-body-p { font-size: .97rem; line-height: 1.88; color: var(--text-2) !important; margin-bottom: .9rem; }
.mo-kilde-boks { margin-top: 1.4rem; padding-top: .85rem; border-top: 1px solid var(--border); }
.mo-kilde-boks a {
  display: inline-block;
  background: var(--accent-blue);
  color: #fff !important;
  padding: .42rem .9rem;
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: .72rem;
  font-weight: 500;
  text-decoration: none;
  letter-spacing: .04em;
}
.mo-kilde-boks a:hover { background: #143d6e; }

/* ═══════════════════════════════════════════════
   RESPONSIVT GRID
   ═══════════════════════════════════════════════ */
@media (max-width: 768px) {
  .mo-grid, .mo-grid-wide { grid-template-columns: 1fr !important; }
  .mo-page { padding: .75rem .75rem 4rem; }
  .mo-header-inner { padding: 0 .9rem; }
  .mo-hero-body, .mo-card-body { padding: .9rem; }
  .mo-article { padding: 1.1rem; }
  .mo-hero .mo-img { height: 200px; }
  html { touch-action: manipulation; }
}
@media (min-width: 769px) and (max-width: 1100px) {
  .mo-grid { grid-template-columns: repeat(2, 1fr) !important; }
  .mo-grid-wide { grid-template-columns: 3fr 2fr !important; }
}
</style>
"""


# ════════════════════════════════════════════════════════════════
# HJELPERE
# ════════════════════════════════════════════════════════════════
def _rens(t: str) -> str:
    if not t:
        return ""
    t = html_mod.unescape(t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _parse_dato(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(_OSLO_TZ)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_OSLO_TZ)
    except Exception:
        return None


def _for_gammel(dt: datetime | None, max_alder: timedelta) -> bool:
    return bool(dt and dt < _oslo_now() - max_alder)


def _dato_str(dt: datetime | None, raa: str = "") -> str:
    return dt.strftime("%-d. %b %Y, %H:%M") if dt else (raa[:10] or "–")


def _er_oslo_sak(tittel: str, desc: str) -> bool:
    """
    Oslo-filter for NRK og Politiet:
    Behold saker som nevner Oslo eller en kjent bydel.
    Filtrer bort saker som inneholder klare nasjonale/utenriks-nøkkelord.
    """
    tekst = f"{tittel} {desc}"
    if NRK_EKSKLUDER.search(tekst):
        return False
    if OSLO_BYDELER_RE.search(tekst):
        return True
    return False


# ════════════════════════════════════════════════════════════════
# BILDE-LOGIKK
# Rotproblem med "bilder usynlige på PC":
#   Streamlit's st.markdown() pakker HTML i en shadow-DOM-komponent
#   som ignorerer inline-stiler på img-tagger i noen situasjoner.
#   Løsning: CSS-klassen .mo-img er definert i <style>-blokken
#   over (ikke inline), og st.html() injiserer den globalt.
#   Alle bilder bruker class="mo-img" — aldri inline height/width.
# ════════════════════════════════════════════════════════════════
_GATE_RE = re.compile(
    r"\b([A-ZÆØÅ][a-zæøåA-ZÆØÅ]+(?:gate|gata|vei|veien|allé|alléen|plass|"
    r"plassen|torg|torget|brygge|bryggen|kaia|kaien|bakke|bakken|"
    r"løkka|hagen|parken|stien)\b(?:\s+\d+[A-Za-z]?)?)",
    re.UNICODE,
)


@st.cache_data(ttl=3600, show_spinner=False)
def _osm_png_url(adresse: str) -> str | None:
    """
    Nominatim → statisk PNG (ikke interaktivt kart).
    User-Agent kreves av Nominatim ToS.
    """
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{adresse}, Oslo, Norway", "format": "json", "limit": 1},
            headers=OSM_HEADERS, timeout=3,
        )
        hits = r.json()
        if not hits:
            return None
        lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
        return (
            f"https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={lat},{lon}&zoom=16&size=900x500"
            f"&markers={lat},{lon},red-pushpin"
        )
    except Exception:
        return None


def _berik_bilde(art: dict) -> dict:
    """Sett art['bilde_url'] — garantert en gyldig URL (aldri tom)."""
    if art.get("bilde_url", "").startswith("http"):
        return art
    tekst = f"{art.get('overskrift','')} {art.get('ingress','')}"
    treff = _GATE_RE.findall(tekst)
    if treff:
        kart = _osm_png_url(treff[0])
        if kart:
            return {**art, "bilde_url": kart}
    bilde = KAT_BILDER.get(art.get("kategori", "annet"), OSLO_FALLBACK)
    return {**art, "bilde_url": bilde}


def img_html(art: dict, ekstra_klasse: str = "") -> str:
    """
    Returnerer <img> med CSS-klassen mo-img (ikke inline stiler).
    onerror sikrer at fallback-bildet alltid vises.
    ekstra_klasse kan legge til f.eks. 'mo-hero-img'.
    """
    url = art.get("bilde_url") or OSLO_FALLBACK
    klass = f"mo-img {ekstra_klasse}".strip()
    return (
        f'<div class="mo-img-wrap">'
        f'<img src="{url}" class="{klass}" alt="" '
        f'onerror="this.src=\'{OSLO_FALLBACK}\';this.onerror=null;">'
        f'</div>'
    )


# ════════════════════════════════════════════════════════════════
# DATA-HENTING
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def hent_politilogg(kilde: dict) -> tuple[list[dict], str]:
    try:
        r = requests.get(kilde["url"], headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        raw = r.json()
        items = raw if isinstance(raw, list) else (
            raw.get("meldinger") or raw.get("data") or raw.get("results") or []
        )
        ut = []
        for m in items:
            tittel = _rens(m.get("tittel") or m.get("title") or "")
            tekst  = _rens(m.get("tekst")  or m.get("text")  or m.get("description") or "")
            tidsp  = m.get("tidspunkt") or m.get("publishedOn") or m.get("created") or ""
            sted   = _rens(m.get("sted") or m.get("location") or m.get("district") or "Oslo")
            url    = m.get("url") or m.get("link") or kilde["link"]
            dt = _parse_dato(tidsp)
            if _for_gammel(dt, kilde["max_alder"]):
                continue
            # Streng Oslo-filter: kun meldinger som nevner Oslo/bydel
            if not _er_oslo_sak(tittel, tekst):
                continue
            ut.append({
                "tittel": tittel or tekst[:60] or "Politimelding",
                "tekst": tekst or tittel,
                "tid": _dato_str(dt, tidsp),
                "sted": sted, "url": url,
                "sortert_dato": dt or (_oslo_now() - timedelta(hours=12)),
            })
        ut.sort(key=lambda x: x["sortert_dato"], reverse=True)
        return ut[:20], ""
    except requests.exceptions.Timeout:
        return [], f"Timeout ({HTTP_TIMEOUT}s)"
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


@st.cache_data(ttl=300, show_spinner=False)
def hent_rss(kilde: dict) -> tuple[list[dict], str]:
    alle_url = [kilde["url"]] + kilde.get("url_alt", [])
    siste_feil = ""
    xml_tekst  = ""
    for url in alle_url:
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            if r.ok and "<" in r.text:
                xml_tekst = r.text
                break
            siste_feil = f"HTTP {r.status_code}"
        except requests.exceptions.Timeout:
            siste_feil = f"Timeout ({HTTP_TIMEOUT}s)"
        except Exception as e:
            siste_feil = f"{type(e).__name__}: {e}"
    if not xml_tekst:
        return [], siste_feil or "Alle URL-er feilet"

    try:
        soup  = BeautifulSoup(xml_tekst, "lxml-xml")
        items = soup.find_all("item") or soup.find_all("entry")
        oslo_filter = kilde.get("oslo_filter", False)
        ut = []
        for item in items:
            def g(*tags: str) -> str:
                for tag in tags:
                    n = item.find(tag)
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
            if _for_gammel(dt, kilde["max_alder"]):
                continue
            if oslo_filter and not _er_oslo_sak(tittel, desc):
                continue

            sammendrag = desc[:280].rstrip()
            if len(desc) > 280:
                sammendrag += "…"

            art = {
                "overskrift": tittel,
                "ingress": sammendrag,
                "brodtekst": [],
                "publisert": _dato_str(dt, pub),
                "kilde_url": lenke or kilde["link"],
                "kilde_navn": kilde["navn"],
                "kilde_tekst": f"Les hos {kilde['navn']}",
                "badge": kilde["badge"],
                "badge_farge": kilde["farge"],
                "bydel": "Hele Oslo",
                "kategori": kilde.get("kategori", "annet"),
                "bilde_url": "",
                "tags": [],
                "sortert_dato": dt or (_oslo_now() - timedelta(hours=6)),
            }
            ut.append(_berik_bilde(art))

        ut.sort(key=lambda x: x["sortert_dato"], reverse=True)
        return ut[:15], ""
    except Exception as e:
        return [], f"Parse-feil: {type(e).__name__}: {e}"


def hent_alle() -> tuple[list[dict], list[dict], dict]:
    politi, nyheter, debug = [], [], {}
    for kilde in KILDER:
        if kilde["type"] == "politilogg":
            data, feil = hent_politilogg(kilde)
        else:
            data, feil = hent_rss(kilde)
        debug[kilde["navn"]] = {
            "ok": not feil, "feil": feil, "antall": len(data), "url": kilde["url"]
        }
        if kilde["type"] == "politilogg":
            politi.extend(data)
        else:
            for a in data:
                a.setdefault("badge",       kilde["badge"])
                a.setdefault("badge_farge", kilde["farge"])
            nyheter.extend(data)
    nyheter.sort(
        key=lambda x: x.get("sortert_dato", _oslo_now() - timedelta(days=7)),
        reverse=True,
    )
    return politi, nyheter, debug


# ════════════════════════════════════════════════════════════════
# UI-BYGGEKLOSSER
# ════════════════════════════════════════════════════════════════
def badge_html(art: dict) -> str:
    farge = art.get("badge_farge", "#555")
    kode  = art.get("badge", "?")
    navn  = art.get("kilde_navn", "")
    return f'<span class="mo-badge" style="background:{farge}">{kode}&nbsp;{navn}</span>'


def meta_html(art: dict) -> str:
    d = art.get("publisert", "")
    return (
        '<div class="mo-meta">'
        + badge_html(art)
        + (f'<span class="mo-date">{d}</span>' if d else "")
        + "</div>"
    )


def kilde_html(art: dict, stor: bool = False) -> str:
    url   = art.get("kilde_url", "#")
    tekst = art.get("kilde_tekst") or f"Les hos {art.get('kilde_navn','Kilde')}"
    if stor:
        return f'<div class="mo-kilde-boks"><a href="{url}" target="_blank">📎 {tekst}</a></div>'
    return f'<a href="{url}" target="_blank" class="mo-src">↗ {tekst}</a>'


def politi_html(meldinger: list[dict]) -> str:
    if not meldinger:
        return (
            '<div class="mo-police" style="text-align:center;padding:1.5rem;">'
            '<p style="color:#5a7fa8;font-size:.82rem;">Ingen meldinger siste 24 timer.</p>'
            f'<a href="https://politiloggen.politiet.no" target="_blank" '
            f'style="color:#4a8fd4;font-size:.75rem;">↗ Se politiloggen direkte</a></div>'
        )
    items = "".join(
        f'<div class="mo-p-item">'
        f'<div class="mo-p-time">🚔 {p["tid"]} · {p["sted"]}</div>'
        f'<div class="mo-p-tekst">{p["tekst"][:200]}{"…" if len(p["tekst"])>200 else ""}</div>'
        f'<a href="{p["url"]}" target="_blank" class="mo-p-link">↗ Les hos Politiloggen</a>'
        f'</div>'
        for p in meldinger
    )
    return (
        f'<div class="mo-police">'
        f'<div class="mo-police-hdr"><div class="mo-dot"></div>'
        f'LIVE — OSLO POLITIDISTRIKT (siste 24t)</div>'
        f'{items}'
        f'<p style="font-family:var(--font-mono);font-size:.56rem;'
        f'color:#3a5a80;margin-top:.6rem;text-align:center;">'
        f'<a href="https://politiloggen.politiet.no" target="_blank" '
        f'style="color:#4a8fd4;">↗ Alle meldinger</a></p></div>'
    )


# ════════════════════════════════════════════════════════════════
# MAIN
# Rekkefølge er kritisk for å unngå svart skjerm:
#   1. session_state — ingen nettverkskall
#   2. st.html(CSS) — siden får utseende umiddelbart
#   3. Sidebar — ingen nettverkskall
#   4. Header — synlig for bruker
#   5. API-kall — inne i st.spinner, etter header
#   6. Innhold rendres
# ════════════════════════════════════════════════════════════════
def main() -> None:

    for k, v in [("dark", False), ("manuell", []),
                 ("valgt", None), ("admin_inn", False)]:
        if k not in st.session_state:
            st.session_state[k] = v

    # Injiser CSS globalt — dette er avgjørende for at .mo-img virker på PC
    st.html(CSS)

    # ── SIDEBAR ────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<p style="font-family:\'Fraunces\',serif;font-size:1.5rem;'
            'font-weight:900;font-style:italic;color:#cd3d33;'
            'margin:.15rem 0 0;letter-spacing:-.03em">MinOslo</p>'
            '<p style="font-family:\'JetBrains Mono\',monospace;font-size:.54rem;'
            'color:#555;margin:0 0 .25rem;letter-spacing:.1em;text-transform:uppercase">'
            'Oslo i dag</p>',
            unsafe_allow_html=True)
        st.markdown("---")

        # Admin
        st.markdown(
            '<p style="font-family:\'JetBrains Mono\',monospace;font-size:.58rem;'
            'letter-spacing:.15em;text-transform:uppercase;color:#cd3d33;'
            'margin-bottom:.3rem">🔒 Admin</p>',
            unsafe_allow_html=True)

        if not st.session_state.admin_inn:
            pw = st.text_input("Passord", type="password",
                               placeholder="Passord…", label_visibility="collapsed")
            if st.button("Logg inn", key="btn_login", use_container_width=True):
                if pw == ADMIN_PW:
                    st.session_state.admin_inn = True
                    st.rerun()
                elif pw:
                    st.markdown(
                        '<p style="color:#e8001f;font-size:.68rem">✗ Feil passord</p>',
                        unsafe_allow_html=True)
        else:
            st.markdown(
                '<p style="color:#4caf50;font-size:.68rem;margin-bottom:.4rem">✓ Innlogget</p>',
                unsafe_allow_html=True)
            with st.expander("📌 Ny topsak", expanded=True):
                with st.form("admin_form", clear_on_submit=True):
                    ny_t   = st.text_input("Tittel *")
                    ny_i   = st.text_area("Ingress *", height=60)
                    ny_bd  = st.selectbox("Bydel", BYDELER[1:])
                    ny_k   = st.selectbox("Kategori", KATEGORIER[1:])
                    ny_img = st.text_input("Bilde-URL (valgfritt)")
                    ny_src = st.text_input("Kilde-URL")
                    ny_sn  = st.text_input("Kilde-navn")
                    if st.form_submit_button("📌 Publiser"):
                        if ny_t.strip() and ny_i.strip():
                            art = {
                                "overskrift": ny_t.strip(),
                                "ingress": ny_i.strip(),
                                "brodtekst": [], "tags": [],
                                "kilde_url": ny_src.strip() or "#",
                                "kilde_navn": ny_sn.strip() or "Redaksjonen",
                                "kilde_tekst": f"Les hos {ny_sn.strip() or 'Redaksjonen'}",
                                "badge": "★", "badge_farge": "#8a1a1a",
                                "bydel": ny_bd, "kategori": ny_k,
                                "publisert": _oslo_now().strftime("%-d. %b %Y, %H:%M"),
                                "bilde_url": ny_img.strip(),
                                "sortert_dato": _oslo_now(),
                            }
                            st.session_state.manuell.insert(0, _berik_bilde(art))
                            st.success("✓ Publisert!")
                            st.rerun()
                        else:
                            st.warning("Tittel og ingress er påkrevd.")
            if st.button("Logg ut", key="btn_logout", use_container_width=True):
                st.session_state.admin_inn = False
                st.rerun()

        st.markdown("---")
        bydel_v = st.selectbox("Bydel",    BYDELER,    label_visibility="collapsed", key="f_bd")
        kat_v   = st.selectbox("Kategori", KATEGORIER, label_visibility="collapsed", key="f_k")
        st.markdown("---")

        if st.button("🔄 Oppdater", key="btn_refresh", use_container_width=True):
            st.cache_data.clear()
            st.session_state.valgt = None
            st.rerun()
        st.caption(f"Cache 5 min · {_oslo_now().strftime('%H:%M')}")

    # ── HEADER — tegnes umiddelbart ──────────────────────────────
    dato = _oslo_now().strftime("%-d. %B %Y")
    st.markdown(
        f'<div class="mo-header">'
        f'<div class="mo-header-inner">'
        f'<a class="mo-logo" href="javascript:void(0)" '
        f'onclick="window.location.reload();">'
        f'Min<span class="mo-logo-suffix">Oslo</span></a>'
        f'<span class="mo-dateline">Oslo · {dato}</span>'
        f'</div></div>',
        unsafe_allow_html=True)

    st.markdown('<div class="mo-page">', unsafe_allow_html=True)

    # ── ARTIKKELVISNING ─────────────────────────────────────────
    if st.session_state.valgt:
        art = st.session_state.valgt
        if st.button("← Tilbake"):
            st.session_state.valgt = None
            st.rerun()
        st.markdown(img_html(art), unsafe_allow_html=True)
        st.markdown('<div class="mo-article">', unsafe_allow_html=True)
        st.markdown(meta_html(art), unsafe_allow_html=True)
        st.markdown(f'<h1>{art["overskrift"]}</h1>', unsafe_allow_html=True)
        st.markdown(f'<div class="mo-lead">{art["ingress"]}</div>', unsafe_allow_html=True)
        for avsnitt in art.get("brodtekst", []):
            st.markdown(f'<p class="mo-body-p">{avsnitt}</p>', unsafe_allow_html=True)
        st.markdown(kilde_html(art, stor=True), unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # ── API-KALL (etter at header er synlig) ────────────────────
    with st.spinner("Henter ferske nyheter fra Oslo…"):
        politi_data, nyheter_data, debug_info = hent_alle()

    # Toppsaker øverst, deretter API-data
    alle: list[dict] = list(st.session_state.manuell) + nyheter_data
    if not alle:
        alle = list(PLACEHOLDER_SAKER)

    # Filtrer
    vis = list(alle)
    if bydel_v != "Alle bydeler":
        vis = [a for a in vis if a.get("bydel") == bydel_v]
    if kat_v != "Alle kategorier":
        vis = [a for a in vis if a.get("kategori") == kat_v]
    if not vis:
        vis = list(alle)

    # ── TABS ────────────────────────────────────────────────────
    tab_nyheter, tab_politi = st.tabs(["📰 Nyheter", "🚔 Politilogg"])

    with tab_politi:
        st.markdown(
            '<div class="mo-section mo-section-red" style="margin-top:0">'
            'Politilogg — Oslo politidistrikt (siste 24 timer)</div>',
            unsafe_allow_html=True)
        st.markdown(politi_html(politi_data), unsafe_allow_html=True)
        if st.session_state.admin_inn:
            d = debug_info.get("Politiloggen", {})
            st.caption(f"⚙️ {d.get('url','?')} | {d.get('antall',0)} meldinger | {d.get('feil') or 'OK'}")

    with tab_nyheter:
        st.markdown(
            '<div class="mo-section mo-section-red" style="margin-top:0">'
            'Siste nytt fra Oslo</div>',
            unsafe_allow_html=True)

        if not vis:
            st.info("Ingen saker funnet. Prøv 'Alle bydeler'.")
        else:
            # ── HERO: første sak, full bredde ───────────────────
            hero = vis[0]
            st.markdown('<div class="mo-hero">', unsafe_allow_html=True)
            st.markdown(img_html(hero), unsafe_allow_html=True)
            st.markdown('<div class="mo-hero-body">', unsafe_allow_html=True)
            st.markdown(meta_html(hero), unsafe_allow_html=True)
            if st.button(hero["overskrift"], key="hero_btn"):
                st.session_state.valgt = hero
                st.rerun()
            st.markdown(
                f'<p class="mo-hero-ingress">{hero["ingress"]}</p>',
                unsafe_allow_html=True)
            st.markdown(kilde_html(hero), unsafe_allow_html=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

            # ── WIDE PAIR: sak 2 og 3 ───────────────────────────
            if len(vis) >= 3:
                st.markdown('<div class="mo-grid-wide">', unsafe_allow_html=True)
                for art in vis[1:3]:
                    st.markdown('<div class="mo-card">', unsafe_allow_html=True)
                    st.markdown(img_html(art), unsafe_allow_html=True)
                    st.markdown('<div class="mo-card-body">', unsafe_allow_html=True)
                    st.markdown(meta_html(art), unsafe_allow_html=True)
                    if st.button(art["overskrift"], key=f"w_{id(art)}"):
                        st.session_state.valgt = art
                        st.rerun()
                    k = art["ingress"][:170]
                    if len(art["ingress"]) > 170:
                        k += "…"
                    st.markdown(f'<p class="mo-card-ingress">{k}</p>', unsafe_allow_html=True)
                    st.markdown(kilde_html(art), unsafe_allow_html=True)
                    st.markdown("</div></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            # ── 3-KOLONNERS GRID: resten ─────────────────────────
            resten = vis[3:]
            if resten:
                st.markdown(
                    '<div class="mo-section">Flere saker</div>',
                    unsafe_allow_html=True)
                st.markdown('<div class="mo-grid">', unsafe_allow_html=True)
                for art in resten:
                    st.markdown('<div class="mo-card">', unsafe_allow_html=True)
                    st.markdown(img_html(art), unsafe_allow_html=True)
                    st.markdown('<div class="mo-card-body">', unsafe_allow_html=True)
                    st.markdown(meta_html(art), unsafe_allow_html=True)
                    if st.button(art["overskrift"], key=f"g_{id(art)}"):
                        st.session_state.valgt = art
                        st.rerun()
                    k = art["ingress"][:130]
                    if len(art["ingress"]) > 130:
                        k += "…"
                    st.markdown(f'<p class="mo-card-ingress">{k}</p>', unsafe_allow_html=True)
                    st.markdown(kilde_html(art), unsafe_allow_html=True)
                    st.markdown("</div></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            # ── Mini politilogg-stripe ───────────────────────────
            st.markdown(
                '<div class="mo-section mo-section-red">'
                'Politilogg — siste meldinger</div>',
                unsafe_allow_html=True)
            st.markdown(politi_html(politi_data[:5]), unsafe_allow_html=True)

            # ── Debug (kun admin) ────────────────────────────────
            if st.session_state.admin_inn:
                with st.expander("⚙️ Debug (kun admin)", expanded=False):
                    for navn, d in debug_info.items():
                        ikon = "✅" if d["ok"] else "❌"
                        st.write(f"{ikon} **{navn}** — {d['antall']} saker")
                        st.code(d["url"])
                        if d["feil"]:
                            st.error(d["feil"])
                    st.caption(
                        f"Tid: {_oslo_now().strftime('%H:%M:%S')} | "
                        f"Politifilter: ≤24t + Oslo-sjekk | "
                        f"Nyhetsfilter: ≤7d | Cache: 300s"
                    )

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
