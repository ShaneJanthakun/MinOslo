"""
MinOslo — Produksjonsversjon
==============================
Deploy:  Render.com
Start:   streamlit run app.py --server.port $PORT --server.address 0.0.0.0

Kilder:
  • Politiloggen  api.politiet.no   — JSON, siste 24t
  • Oslo kommune  aktuelt.oslo.kommune.no — RSS, siste 7d
  • NRK Stor-Oslo nrk.no/stor-oslo/feed/ — Atom, siste 7d, kun Oslo-saker
  • eInnsyn       einnsyn.no/rss         — RSS, siste 7d

Bilder (ingen interaktive kart, ingen iframe):
  • OSM staticmap.openstreetmap.de — statisk PNG for adressesaker
  • Unsplash statiske URL-er       — per kategori, ingen API-nøkkel
  • Fast Oslo-fallback             — garantert bilde
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import re
import html as html_mod

# ── MÅ stå absolutt først ─────────────────────────────────────
st.set_page_config(
    page_title="MinOslo",
    page_icon="🗞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════════════
# NORSK TID  (ingen pytz/zoneinfo nødvendig)
# ════════════════════════════════════════════════════════════════
def _oslo_now() -> datetime:
    utc = datetime.now(timezone.utc)
    dst_start = datetime(utc.year, 3, 25, 1, tzinfo=timezone.utc)
    dst_end   = datetime(utc.year, 10, 25, 1, tzinfo=timezone.utc)
    return utc.astimezone(timezone(timedelta(hours=2 if dst_start <= utc < dst_end else 1)))

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
# Egne headers for Nominatim (OSM krever identifikasjon)
OSM_HEADERS = {"User-Agent": "MinOsloBot/1.0 (shane@example.com)"}

MAX_ALDER_POLITI  = timedelta(hours=24)
MAX_ALDER_NYHETER = timedelta(days=7)

# Garantert fallback — Oslo operahus
OSLO_FALLBACK = (
    "https://images.unsplash.com/photo-1583907608452-7260268ec9a8"
    "?auto=format&fit=crop&q=80&w=800&h=450"
)

# Kategori → Unsplash (statisk, hotlinking OK for display, ingen nøkkel)
KAT_BILDER = {
    "politilogg":       "https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&q=80&w=800&h=450",
    "kommune":          "https://images.unsplash.com/photo-1446822775955-c34f483b410b?auto=format&fit=crop&q=80&w=800&h=450",
    "nrk":              "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&q=80&w=800&h=450",
    "einnsyn":          "https://images.unsplash.com/photo-1464938050520-ef2270bb8ce8?auto=format&fit=crop&q=80&w=800&h=450",
    "byggesak":         "https://images.unsplash.com/photo-1504307651254-35680f356dfd?auto=format&fit=crop&q=80&w=800&h=450",
    "skjenkebevilling": "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?auto=format&fit=crop&q=80&w=800&h=450",
    "regulering":       "https://images.unsplash.com/photo-1476231682828-37e571bc172f?auto=format&fit=crop&q=80&w=800&h=450",
    "annet":            "https://images.unsplash.com/photo-1583907608452-7260268ec9a8?auto=format&fit=crop&q=80&w=800&h=450",
}

# NRK: ord som avslører nasjonale/utenriks-saker vi skal filtrere bort
NRK_UTENFOR_OSLO = re.compile(
    r"\b(utenriks|verden|internasjonal|Europa|USA|Russland|Ukraina|Israel|"
    r"Gaza|Kina|Storbritannia|premier.league|Champions League|Eliteserien|"
    r"Tippeligaen|landslaget|VM|EM|OL|Paralympics|Nobel|Stortinget|"
    r"regjering|regjeringen|statsminister|Finansdepartement|"
    r"Trondheim|Bergen|Stavanger|Tromsø|Kristiansand|Bodø)\b",
    re.IGNORECASE,
)

KILDER = [
    {
        "id": "politiloggen",
        "url": "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=30",
        "navn": "Politiloggen", "badge": "P", "farge": "#1a3a6a",
        "type": "politilogg", "max_alder": MAX_ALDER_POLITI,
        "link": "https://politiloggen.politiet.no",
    },
    {
        "id": "oslo",
        "url": "https://aktuelt.oslo.kommune.no/?format=rss",
        "url_alt": ["https://www.oslo.kommune.no/rss/", "https://aktuelt.oslo.kommune.no/feed/"],
        "navn": "Oslo kommune", "badge": "K", "farge": "#0a5c2a",
        "type": "rss", "kategori": "kommune", "max_alder": MAX_ALDER_NYHETER,
        "link": "https://aktuelt.oslo.kommune.no", "oslo_filter": False,
    },
    {
        "id": "nrk",
        "url": "https://www.nrk.no/stor-oslo/feed/",
        "url_alt": ["https://www.nrk.no/toppsaker.rss"],
        "navn": "NRK", "badge": "N", "farge": "#c00000",
        "type": "rss", "kategori": "nrk", "max_alder": MAX_ALDER_NYHETER,
        "link": "https://www.nrk.no/stor-oslo/", "oslo_filter": True,
    },
    {
        "id": "einnsyn",
        "url": "https://einnsyn.no/rss?q=Oslo+kommune&antall=20",
        "navn": "eInnsyn", "badge": "E", "farge": "#5a3090",
        "type": "rss", "kategori": "einnsyn", "max_alder": MAX_ALDER_NYHETER,
        "link": "https://einnsyn.no", "oslo_filter": False,
    },
]

PLACEHOLDER_SAKER = [
    {
        "overskrift": "Oslo-guide: De beste turene i Marka denne helgen",
        "ingress": "Oslomarka tilbyr fantastiske turer året rundt — for store og små.",
        "publisert": _oslo_now().strftime("%-d. %b %Y"),
        "kilde_url": "https://www.ut.no/omrade/3230/", "kilde_navn": "ut.no",
        "badge": "T", "badge_farge": "#2a6a3a", "bydel": "Hele Oslo",
        "kategori": "annet", "bilde_url": OSLO_FALLBACK,
        "brodtekst": [], "tags": ["tur", "marka"],
        "sortert_dato": _oslo_now() - timedelta(hours=1),
    },
    {
        "overskrift": "Hva skjer i Oslo denne uken?",
        "ingress": "Oslo har et rikt kulturtilbud. Sjekk Visit Oslo for oppdatert program.",
        "publisert": _oslo_now().strftime("%-d. %b %Y"),
        "kilde_url": "https://www.visitoslo.com/no/", "kilde_navn": "Visit Oslo",
        "badge": "V", "badge_farge": "#2a5a8a", "bydel": "Hele Oslo",
        "kategori": "annet",
        "bilde_url": "https://images.unsplash.com/photo-1486325212027-8081e485255e?auto=format&fit=crop&q=80&w=800&h=450",
        "brodtekst": [], "tags": ["kultur", "arrangement"],
        "sortert_dato": _oslo_now() - timedelta(hours=2),
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
# TEMA
# ════════════════════════════════════════════════════════════════
LIGHT = {
    "bg": "#f2f1ef", "bg_card": "#ffffff", "bg_header": "#ffffff",
    "bg_sidebar": "#141414", "bg_police": "#080818",
    "border": "#e8e5e0",
    # Tekst — eksplisitt mørk, overstyres med !important i CSS
    "text_primary": "#111111", "text_body": "#333333",
    "text_soft": "#666666", "text_muted": "#999999", "text_police": "#d8eeff",
    "accent": "#c8001e", "accent2": "#1a4f8a",
    "tag_bg": "#eceae6", "tag_text": "#444444",
    "meta_bg": "#f5f3f0", "police_border": "#1a2860", "police_item": "#0d1530",
    "card_shadow": "rgba(0,0,0,0.07)",
}
DARK = {
    "bg": "#0c0c0c", "bg_card": "#181818", "bg_header": "#101010",
    "bg_sidebar": "#080808", "bg_police": "#060616",
    "border": "#2a2a2a",
    "text_primary": "#f0f0f0", "text_body": "#cccccc",
    "text_soft": "#888888", "text_muted": "#555555", "text_police": "#c4e0f8",
    "accent": "#e8001f", "accent2": "#4a8fd4",
    "tag_bg": "#222222", "tag_text": "#aaaaaa",
    "meta_bg": "#1e1e1e", "police_border": "#1e2d5e", "police_item": "#0e1628",
    "card_shadow": "rgba(0,0,0,0.40)",
}


# ════════════════════════════════════════════════════════════════
# CSS  — editorial/avis-stil, Playfair + Source Serif
# Alle farger bruker !important for å overvinne Streamlit-stiler
# ════════════════════════════════════════════════════════════════
def build_css(t: dict) -> str:
    is_light = t is LIGHT
    # Kortknapp-tekstfarge: alltid mørk i light mode, alltid lys i dark mode
    btn_color = "#111111" if is_light else "#f0f0f0"
    btn_hover = "#c8001e"
    return f"""
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700;1,900&family=Source+Serif+4:wght@300;400;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ── Reset ── */
#MainMenu,footer,header{{visibility:hidden!important;}}
.block-container{{padding:0!important;max-width:100%!important;}}
html,body,.stApp{{
    background:{t["bg"]}!important;
    font-family:'Source Serif 4',Georgia,serif;
    -webkit-font-smoothing:antialiased;
}}

/* ── Sidebar ── */
[data-testid="stSidebar"]{{background:{t["bg_sidebar"]}!important;border-right:1px solid #1e1e1e!important;}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label{{color:#888!important;font-size:.72rem!important;font-family:'DM Mono',monospace;letter-spacing:.04em;}}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stTextArea textarea,
[data-testid="stSidebar"] .stSelectbox>div>div{{
    background:#1a1a1a!important;color:#ddd!important;
    border-color:#2e2e2e!important;font-size:.82rem!important;
    font-family:'Source Serif 4',serif!important;
}}
[data-testid="stSidebar"] hr{{border-color:#1e1e1e!important;margin:.5rem 0!important;}}
[data-testid="stSidebar"] .stButton>button{{
    background:{t["accent"]}!important;color:#fff!important;border:none!important;
    border-radius:4px!important;font-weight:700!important;font-size:.68rem!important;
    font-family:'DM Mono',monospace!important;letter-spacing:.1em;text-transform:uppercase;
    width:100%;padding:.5rem!important;
}}
[data-testid="stSidebar"] .stButton>button:hover{{opacity:.82!important;}}

/* ── HEADER — sticky, rød bunnlinje ── */
.mn-header{{
    background:{t["bg_header"]};
    border-bottom:3px solid {t["accent"]};
    position:sticky;top:0;z-index:300;
    box-shadow:0 1px 8px {t["card_shadow"]};
}}
.mn-inner{{max-width:1360px;margin:0 auto;padding:0 1.5rem;}}
.mn-top{{
    display:flex;align-items:center;
    justify-content:space-between;
    padding:.8rem 0 .65rem;
}}
/* Logo — klikkbar, laster side på nytt */
.mn-logo{{
    font-family:'Playfair Display',serif;
    font-size:clamp(1.55rem,3.5vw,2.1rem);
    font-weight:900;color:{t["accent"]};letter-spacing:-.04em;
    line-height:1;text-decoration:none;cursor:pointer;
    transition:opacity .15s;
}}
.mn-logo:hover{{opacity:.78;}}
.mn-logo span{{color:{t["text_primary"]};}}
.mn-dateline{{
    font-family:'DM Mono',monospace;font-size:.58rem;
    color:{t["text_soft"]};letter-spacing:.14em;text-transform:uppercase;
}}
/* Ingen nav-linje under header */

/* ── Side-wrapper ── */
.mn-page{{max-width:1360px;margin:0 auto;padding:1.5rem 1.5rem 6rem;}}

/* ── Seksjons-label ── */
.mn-label{{
    font-family:'DM Mono',monospace;
    font-size:.6rem;font-weight:500;letter-spacing:.2em;text-transform:uppercase;
    color:{t["text_soft"]};border-top:1.5px solid {t["text_primary"]};
    padding-top:.45rem;margin:2rem 0 1rem;
}}
.mn-label-red{{border-top-color:{t["accent"]};color:{t["accent"]};}}

/* ── Kilde-badge ── */
.mn-pill{{
    display:inline-flex;align-items:center;gap:.22rem;
    font-family:'DM Mono',monospace;
    font-size:.55rem;font-weight:500;letter-spacing:.08em;text-transform:uppercase;
    padding:.15em .48em;border-radius:3px;color:#fff;flex-shrink:0;line-height:1.4;
}}

/* ── Meta-rad ── */
.mn-meta{{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;margin-bottom:.3rem;}}
.mn-date{{
    font-family:'DM Mono',monospace;font-size:.6rem;
    color:{t["text_muted"]}!important;letter-spacing:.04em;
}}

/* ── Kildelenke ── */
.mn-src{{
    display:inline-block;margin-top:.55rem;
    font-family:'DM Mono',monospace;font-size:.68rem;font-weight:500;
    color:{t["accent2"]}!important;text-decoration:none;
    border-bottom:1px solid {t["accent2"]};padding-bottom:1px;
}}
.mn-src:hover{{opacity:.72;}}

/* ── Tags ── */
.mn-tags{{display:flex;flex-wrap:wrap;gap:.25rem;margin-top:.5rem;}}
.mn-tag{{
    font-family:'DM Mono',monospace;font-size:.55rem;
    background:{t["tag_bg"]};color:{t["tag_text"]}!important;
    border:1px solid {t["border"]};padding:.14em .44em;border-radius:20px;
}}

/* ── HERO (full bredde, 200px bilde) ── */
.mn-hero{{
    background:{t["bg_card"]};border:1px solid {t["border"]};
    border-radius:12px;overflow:hidden;margin-bottom:1.75rem;
    box-shadow:0 3px 18px {t["card_shadow"]};
}}
.mn-hero-body{{padding:1.4rem 1.75rem 1.75rem;}}
.mn-hero-ingress{{
    font-size:1rem;line-height:1.72;
    color:{t["text_body"]}!important;   /* !important — hvit i light mode fix */
    margin:.4rem 0 .65rem;
}}

/* ── GRID — 3 kol på PC, 2 på nettbrett, 1 på mobil ── */
.mn-grid{{
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:1.2rem;margin-bottom:1.5rem;
}}
.mn-grid-wide{{
    display:grid;
    grid-template-columns:2fr 1fr;
    gap:1.2rem;margin-bottom:1.2rem;
}}

/* ── STANDARD KORT ── */
.mn-card{{
    background:{t["bg_card"]};border:1px solid {t["border"]};
    border-radius:12px;overflow:hidden;
    box-shadow:0 2px 10px {t["card_shadow"]};
    display:flex;flex-direction:column;
    transition:transform .18s,box-shadow .18s;
}}
.mn-card:hover{{
    transform:translateY(-2px);
    box-shadow:0 6px 22px {t["card_shadow"]};
}}
/* Bilderamme: fast 200px, object-fit:cover — fjerner tomme bokser */
.mn-card-img{{
    width:100%;height:200px!important;
    object-fit:cover!important;display:block;
}}
.mn-card-body{{padding:.95rem 1.05rem 1.1rem;flex:1;display:flex;flex-direction:column;}}

/* ── Artikkelknapper som titler ──────────────────────────────────
   KRITISK for light mode:
   color er satt til mørk med !important så den ikke arver hvit fra Streamlit.
   Ingen z-index / overflow:hidden på wrapper.
   ─────────────────────────────────────────────────────────────── */
.stButton>button{{
    background:transparent!important;
    color:{btn_color}!important;          /* mørk i light, lys i dark */
    border:none!important;border-radius:0!important;
    font-family:'Playfair Display',serif!important;
    font-size:clamp(.92rem,2vw,1.06rem)!important;
    font-weight:700!important;line-height:1.25!important;
    text-align:left!important;padding:0!important;
    width:100%!important;white-space:normal!important;
    height:auto!important;cursor:pointer!important;
    min-height:44px!important;   /* iOS touch target */
}}
.stButton>button:hover{{color:{btn_hover}!important;}}
.stButton>button:focus{{box-shadow:none!important;outline:none!important;}}

/* ── Ingress i kort ─────────────────────────────────────────────
   !important sikrer mørk tekst i light mode.
   ─────────────────────────────────────────────────────────────── */
.mn-card-ingress{{
    font-size:.84rem;line-height:1.62;
    color:{t["text_body"]}!important;
    flex:1;margin-top:.3rem;
}}

/* Bilde-wrapper: ingen overflow:hidden, ingen z-index */
.mn-img-wrap{{line-height:0;}}

/* ── Politilogg ── */
.mn-police-wrap{{
    background:{t["bg_police"]};border:1px solid {t["police_border"]};
    border-radius:12px;padding:1rem;margin-top:.5rem;
}}
.mn-police-hdr{{
    font-family:'DM Mono',monospace;
    font-size:.6rem;font-weight:500;letter-spacing:.15em;text-transform:uppercase;
    color:{t["accent"]};display:flex;align-items:center;gap:.4rem;margin-bottom:.75rem;
}}
.mn-dot{{
    width:6px;height:6px;border-radius:50%;
    background:{t["accent"]};animation:blink 1.4s infinite;flex-shrink:0;
}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.12}}}}
.mn-p-item{{
    background:{t["police_item"]};border:1px solid {t["police_border"]};
    border-radius:7px;padding:.6rem .8rem;margin-bottom:.42rem;
}}
.mn-p-time{{font-family:'DM Mono',monospace;font-size:.58rem;color:{t["accent"]};font-weight:500;margin-bottom:.14rem;}}
.mn-p-tekst{{font-size:.8rem;color:{t["text_police"]}!important;line-height:1.5;}}
.mn-p-sted{{font-family:'DM Mono',monospace;font-size:.6rem;color:#5a7fa8!important;margin-top:.12rem;}}
.mn-p-link{{font-family:'DM Mono',monospace;font-size:.6rem;color:{t["accent2"]}!important;margin-top:.28rem;text-decoration:none;border-bottom:1px solid {t["accent2"]};display:inline;}}

/* ── Artikkel fullvisning ── */
.mn-article{{
    background:{t["bg_card"]};border:1px solid {t["border"]};
    border-radius:12px;padding:2rem;margin-top:.75rem;
    box-shadow:0 3px 18px {t["card_shadow"]};
}}
.mn-article h1{{
    font-family:'Playfair Display',serif;
    font-size:clamp(1.5rem,4vw,2.5rem);font-weight:900;
    line-height:1.1;color:{t["text_primary"]}!important;margin-bottom:.9rem;
}}
.mn-lead{{
    font-size:1.05rem;line-height:1.75;color:{t["text_body"]}!important;
    border-left:4px solid {t["accent"]};padding-left:1rem;margin-bottom:1.5rem;
}}
.mn-body-p{{font-size:.97rem;line-height:1.88;color:{t["text_body"]}!important;margin-bottom:.9rem;}}
.mn-kilde-boks{{margin-top:1.3rem;padding-top:.8rem;border-top:1px solid {t["border"]};}}
.mn-kilde-boks a{{
    display:inline-block;background:{t["accent2"]};color:#fff!important;
    padding:.4rem .85rem;border-radius:5px;
    font-family:'DM Mono',monospace;font-size:.72rem;font-weight:500;
    text-decoration:none;letter-spacing:.04em;
}}
.mn-kilde-boks a:hover{{opacity:.85;}}

/* ── MOBIL — 100% bredde, ikke zoomet inn ── */
@media(max-width:768px){{
    .mn-grid,.mn-grid-wide{{grid-template-columns:1fr!important;}}
    .mn-page{{padding:.75rem .75rem 4rem;}}
    .mn-inner{{padding:0 .8rem;}}
    .mn-hero-body,.mn-card-body{{padding:.9rem;}}
    .mn-article{{padding:1.1rem;}}
    /* Forhindre at Streamlit zoomer inn på mobil */
    html{{touch-action:manipulation;}}
}}
@media(min-width:769px) and (max-width:1100px){{
    .mn-grid{{grid-template-columns:repeat(2,1fr)!important;}}
    .mn-grid-wide{{grid-template-columns:3fr 2fr!important;}}
}}
</style>
"""


# ════════════════════════════════════════════════════════════════
# HJELPERE
# ════════════════════════════════════════════════════════════════
def _rens(tekst: str) -> str:
    if not tekst:
        return ""
    tekst = html_mod.unescape(tekst)
    tekst = re.sub(r"<[^>]+>", " ", tekst)
    tekst = re.sub(r"\s{2,}", " ", tekst)
    return tekst.strip()


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


def _vis_dato(dt: datetime | None, raa: str = "") -> str:
    return dt.strftime("%-d. %b %Y, %H:%M") if dt else (raa[:10] or "–")


def _er_oslo_sak(tittel: str, desc: str) -> bool:
    """Filtrer NRK-saker: behold kun Oslo-relevante, fjern utenriks/nasjonal/sport."""
    tekst = f"{tittel} {desc}"
    if NRK_UTENFOR_OSLO.search(tekst):
        return False
    return True


# ════════════════════════════════════════════════════════════════
# BILDE-LOGIKK
# 1. Manuelt bilde  → vis direkte
# 2. Gateadresse    → statisk OSM PNG (ingen iframe, ingen zoom-knapper)
# 3. Kategoribilde  → Unsplash statisk URL
# 4. Fallback       → Oslo-bilde (garanti — ingen tomme bokser)
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
    Nominatim-oppslag → returnerer URL til statisk PNG-kart.
    Bruker OSM_HEADERS med identifiserende User-Agent (påkrevd av Nominatim ToS).
    Ingen iframe, ingen interaktivitet — bare et bilde.
    """
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{adresse}, Oslo, Norway", "format": "json", "limit": 1},
            headers=OSM_HEADERS,
            timeout=3,
        )
        hits = r.json()
        if not hits:
            return None
        lat = float(hits[0]["lat"])
        lon = float(hits[0]["lon"])
        # staticmap.openstreetmap.de → ekte PNG-bilde, ikke interaktivt
        return (
            f"https://staticmap.openstreetmap.de/staticmap.php"
            f"?center={lat},{lon}&zoom=16&size=800x450"
            f"&markers={lat},{lon},red-pushpin"
        )
    except Exception:
        return None


def _berik_bilde(art: dict) -> dict:
    """Finn beste bilde og legg det på art['bilde_url']."""
    if art.get("bilde_url", "").startswith("http"):
        return art   # manuelt satt — bruk det

    tekst = f"{art.get('overskrift','')} {art.get('ingress','')}"
    treff = _GATE_RE.findall(tekst)
    if treff:
        kart_url = _osm_png_url(treff[0])
        if kart_url:
            return {**art, "bilde_url": kart_url}

    # Kategori → Unsplash
    bilde = KAT_BILDER.get(art.get("kategori", "annet"), OSLO_FALLBACK)
    return {**art, "bilde_url": bilde}


def vis_bilde_html(art: dict, h: int = 200) -> str:
    """
    Returnerer HTML-streng for et bilde med fast høyde.
    Alle bilder: height:{h}px; object-fit:cover — ingen tomme bokser.
    onerror peker på garantert fallback.
    """
    url = art.get("bilde_url") or OSLO_FALLBACK
    return (
        f'<div class="mn-img-wrap">'
        f'<img src="{url}" '
        f'style="width:100%;height:{h}px!important;object-fit:cover!important;'
        f'display:block;border-radius:12px 12px 0 0;" alt="" '
        f'onerror="this.src=\'{OSLO_FALLBACK}\'">'
        f'</div>'
    )


# ════════════════════════════════════════════════════════════════
# DATA-HENTING  (ttl=300, timeout=5, stille feil)
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
            ut.append({
                "tittel": tittel or tekst[:60] or "Politimelding",
                "tekst": tekst or tittel,
                "tid": _vis_dato(dt, tidsp),
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

            # NRK: filtrer bort ikke-Oslo-saker
            if oslo_filter and not _er_oslo_sak(tittel, desc):
                continue

            # Sammendrag: ett kort avsnitt, maks 280 tegn
            sammendrag = desc[:280].rstrip()
            if len(desc) > 280:
                sammendrag += "…"

            # Kilde-tekst: "Les hos NRK" / "Les hos Oslo kommune" etc.
            kilde_tekst = f"Les hos {kilde['navn']}"

            art = {
                "overskrift": tittel,
                "ingress": sammendrag,
                "brodtekst": [],   # ingen doble avsnitt
                "publisert": _vis_dato(dt, pub),
                "kilde_url": lenke or kilde["link"],
                "kilde_navn": kilde["navn"],
                "kilde_tekst": kilde_tekst,
                "badge": kilde["badge"],
                "badge_farge": kilde["farge"],
                "bydel": "Hele Oslo",
                "kategori": kilde.get("kategori", "annet"),
                "bilde_url": "",
                "tags": [kilde["navn"]],
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
    return f'<span class="mn-pill" style="background:{farge}">{kode} {navn}</span>'


def meta_html(art: dict) -> str:
    d = art.get("publisert", "")
    return (
        '<div class="mn-meta">'
        + badge_html(art)
        + (f'<span class="mn-date">{d}</span>' if d else "")
        + "</div>"
    )


def kilde_html(art: dict, stor: bool = False) -> str:
    url     = art.get("kilde_url", "#")
    tekst   = art.get("kilde_tekst") or f"Les hos {art.get('kilde_navn','Kilde')}"
    if stor:
        return f'<div class="mn-kilde-boks"><a href="{url}" target="_blank">📎 {tekst}</a></div>'
    return f'<a href="{url}" target="_blank" class="mn-src">↗ {tekst}</a>'


def tags_html(art: dict) -> str:
    s = "".join(f'<span class="mn-tag">{x}</span>' for x in art.get("tags", []))
    return f'<div class="mn-tags">{s}</div>' if s else ""


def politi_html(meldinger: list[dict]) -> str:
    if not meldinger:
        return (
            '<div class="mn-police-wrap" style="text-align:center;padding:1.5rem;">'
            '<p style="color:#5a7fa8;font-size:.82rem">Ingen meldinger siste 24 timer.</p>'
            f'<a href="https://politiloggen.politiet.no" target="_blank" '
            f'style="color:#4a8fd4;font-size:.75rem">↗ Se politiloggen direkte</a></div>'
        )
    items = "".join(
        f'<div class="mn-p-item">'
        f'<div class="mn-p-time">🚔 {p["tid"]} · {p["sted"]}</div>'
        f'<div class="mn-p-tekst">{p["tekst"][:180]}{"…" if len(p["tekst"])>180 else ""}</div>'
        f'<a href="{p["url"]}" target="_blank" class="mn-p-link">↗ Les hos Politiloggen</a>'
        f'</div>'
        for p in meldinger
    )
    return (
        f'<div class="mn-police-wrap">'
        f'<div class="mn-police-hdr"><div class="mn-dot"></div>'
        f'LIVE — OSLO POLITIDISTRIKT (siste 24t)</div>'
        f'{items}'
        f'<p style="font-family:\'DM Mono\',monospace;font-size:.56rem;'
        f'color:#3a5a80;margin-top:.5rem;text-align:center">'
        f'<a href="https://politiloggen.politiet.no" target="_blank" style="color:#4a8fd4">'
        f'↗ Alle meldinger</a></p></div>'
    )


# ════════════════════════════════════════════════════════════════
# MAIN
# Rekkefølge er kritisk:
#   1. session_state   — ingen nettverkskall
#   2. CSS             — siden får farge
#   3. Sidebar         — ingen nettverkskall
#   4. Header          — synlig for bruker
#   5. API-kall        — inne i st.spinner etter header
#   6. Render innhold
# ════════════════════════════════════════════════════════════════
def main() -> None:

    for k, v in [("dark", False), ("manuell", []),
                 ("valgt", None), ("admin_inn", False)]:
        if k not in st.session_state:
            st.session_state[k] = v

    t = DARK if st.session_state.dark else LIGHT
    st.html(build_css(t))

    # ── SIDEBAR ────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<p style="font-family:\'Playfair Display\',serif;font-size:1.55rem;'
            'font-weight:900;color:#c8001e;margin:.15rem 0 0;letter-spacing:-.03em">'
            'MinOslo</p>'
            '<p style="font-family:\'DM Mono\',monospace;font-size:.55rem;'
            'color:#555;margin:0 0 .25rem;letter-spacing:.1em;text-transform:uppercase">'
            'Oslo i dag</p>',
            unsafe_allow_html=True)
        st.markdown("---")

        # Admin
        st.markdown(
            '<p style="font-family:\'DM Mono\',monospace;font-size:.58rem;'
            'font-weight:500;letter-spacing:.15em;text-transform:uppercase;'
            'color:#c8001e;margin-bottom:.3rem">🔒 Admin</p>',
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
                                "overskrift": ny_t.strip(), "ingress": ny_i.strip(),
                                "brodtekst": [], "tags": [ny_bd, ny_k],
                                "kilde_url":  ny_src.strip() or "#",
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
        dm = "☀️ Light" if st.session_state.dark else "🌙 Dark"
        if st.button(dm, key="btn_dm", use_container_width=True):
            st.session_state.dark = not st.session_state.dark
            st.rerun()
        st.markdown("---")

        st.markdown(
            '<p style="font-family:\'DM Mono\',monospace;font-size:.58rem;'
            'font-weight:500;letter-spacing:.12em;text-transform:uppercase;'
            'color:#666;margin-bottom:.2rem">Filtrer</p>',
            unsafe_allow_html=True)
        bydel_v = st.selectbox("Bydel",    BYDELER,    label_visibility="collapsed", key="f_bd")
        kat_v   = st.selectbox("Kategori", KATEGORIER, label_visibility="collapsed", key="f_k")
        st.markdown("---")

        if st.button("🔄 Oppdater nå", key="btn_refresh", use_container_width=True):
            st.cache_data.clear()
            st.session_state.valgt = None
            st.rerun()
        st.caption(f"Cache 5 min · {_oslo_now().strftime('%H:%M')} norsk tid")

    # ── HEADER — tegnes umiddelbart (ingen API-kall over) ─────
    dato = _oslo_now().strftime("%-d. %B %Y")
    # Logo-knapp: JavaScript location.reload() laster siden på nytt
    st.markdown(
        f'<div class="mn-header"><div class="mn-inner">'
        f'<div class="mn-top">'
        f'<a class="mn-logo" href="javascript:void(0)" '
        f'onclick="window.location.reload()">Min<span>Oslo</span></a>'
        f'<span class="mn-dateline">Oslo · {dato}</span>'
        f'</div>'
        f'</div></div>',   # ingen nav-linje
        unsafe_allow_html=True)

    st.markdown('<div class="mn-page">', unsafe_allow_html=True)

    # ── ARTIKKELVISNING (ingen API-kall) ───────────────────────
    if st.session_state.valgt:
        art = st.session_state.valgt
        if st.button("← Tilbake"):
            st.session_state.valgt = None
            st.rerun()
        st.markdown(vis_bilde_html(art, 280), unsafe_allow_html=True)
        st.markdown('<div class="mn-article">', unsafe_allow_html=True)
        st.markdown(meta_html(art), unsafe_allow_html=True)
        st.markdown(f'<h1>{art["overskrift"]}</h1>', unsafe_allow_html=True)
        st.markdown(f'<div class="mn-lead">{art["ingress"]}</div>', unsafe_allow_html=True)
        for avsnitt in art.get("brodtekst", []):
            st.markdown(f'<p class="mn-body-p">{avsnitt}</p>', unsafe_allow_html=True)
        st.markdown(tags_html(art), unsafe_allow_html=True)
        st.markdown(kilde_html(art, stor=True), unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # ── API-KALL (etter at header er synlig) ───────────────────
    with st.spinner("Henter siste nyheter fra Oslo…"):
        politi_data, nyheter_data, debug_info = hent_alle()

    # Toppsaker fra admin øverst, deretter API-data
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
        vis = list(alle)   # tilbakestill filter ved ingen treff

    # ── TABS (mobil-first: politilogg i egen fane) ─────────────
    tab_nyheter, tab_politi = st.tabs(["📰 Nyheter", "🚔 Politilogg"])

    with tab_politi:
        st.markdown(
            '<div class="mn-label mn-label-red" style="margin-top:0">'
            'Politilogg — Oslo politidistrikt (siste 24 timer)</div>',
            unsafe_allow_html=True)
        st.markdown(politi_html(politi_data), unsafe_allow_html=True)
        if st.session_state.admin_inn:
            d = debug_info.get("Politiloggen", {})
            st.caption(f"⚙️ {d.get('url','?')} | {d.get('antall',0)} meldinger | {d.get('feil') or 'OK'}")

    with tab_nyheter:
        st.markdown(
            '<div class="mn-label mn-label-red" style="margin-top:0">'
            'Siste nytt fra Oslo</div>',
            unsafe_allow_html=True)

        if not vis:
            st.info("Ingen saker matcher filteret. Prøv 'Alle bydeler'.")
        else:
            # ── HERO: første sak, full bredde ──────────────────
            hero = vis[0]
            st.markdown('<div class="mn-hero">', unsafe_allow_html=True)
            st.markdown(vis_bilde_html(hero, 280), unsafe_allow_html=True)
            st.markdown('<div class="mn-hero-body">', unsafe_allow_html=True)
            st.markdown(meta_html(hero), unsafe_allow_html=True)
            if st.button(hero["overskrift"], key="hero_btn"):
                st.session_state.valgt = hero
                st.rerun()
            st.markdown(
                f'<p class="mn-hero-ingress">{hero["ingress"]}</p>',
                unsafe_allow_html=True)
            st.markdown(kilde_html(hero), unsafe_allow_html=True)
            st.markdown(tags_html(hero), unsafe_allow_html=True)
            st.markdown("</div></div>", unsafe_allow_html=True)

            # ── WIDE PAIR: sak 2 og 3 ──────────────────────────
            if len(vis) >= 3:
                st.markdown('<div class="mn-grid-wide">', unsafe_allow_html=True)
                for art in vis[1:3]:
                    st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                    st.markdown(vis_bilde_html(art, 200), unsafe_allow_html=True)
                    st.markdown('<div class="mn-card-body">', unsafe_allow_html=True)
                    st.markdown(meta_html(art), unsafe_allow_html=True)
                    if st.button(art["overskrift"], key=f"w_{id(art)}"):
                        st.session_state.valgt = art
                        st.rerun()
                    st.markdown(
                        f'<p class="mn-card-ingress">{art["ingress"][:160]}{"…" if len(art["ingress"])>160 else ""}</p>',
                        unsafe_allow_html=True)
                    st.markdown(kilde_html(art), unsafe_allow_html=True)
                    st.markdown("</div></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            # ── 3-KOLONNERS GRID: resten ───────────────────────
            resten = vis[3:]
            if resten:
                st.markdown('<div class="mn-label">Flere saker</div>', unsafe_allow_html=True)
                st.markdown('<div class="mn-grid">', unsafe_allow_html=True)
                for art in resten:
                    st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                    st.markdown(vis_bilde_html(art, 200), unsafe_allow_html=True)
                    st.markdown('<div class="mn-card-body">', unsafe_allow_html=True)
                    st.markdown(meta_html(art), unsafe_allow_html=True)
                    if st.button(art["overskrift"], key=f"g_{id(art)}"):
                        st.session_state.valgt = art
                        st.rerun()
                    st.markdown(
                        f'<p class="mn-card-ingress">{art["ingress"][:130]}{"…" if len(art["ingress"])>130 else ""}</p>',
                        unsafe_allow_html=True)
                    st.markdown(kilde_html(art), unsafe_allow_html=True)
                    st.markdown("</div></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            # ── Mini politilogg-stripe under nyheter ───────────
            st.markdown(
                '<div class="mn-label mn-label-red">Politilogg — siste meldinger</div>',
                unsafe_allow_html=True)
            st.markdown(politi_html(politi_data[:5]), unsafe_allow_html=True)

            # ── Debug (kun admin) ───────────────────────────────
            if st.session_state.admin_inn:
                with st.expander("⚙️ Debug (kun for admin)", expanded=False):
                    for navn, d in debug_info.items():
                        ikon = "✅" if d["ok"] else "❌"
                        st.write(f"{ikon} **{navn}** — {d['antall']} saker")
                        st.code(d["url"])
                        if d["feil"]:
                            st.error(d["feil"])
                    st.caption(
                        f"Tid: {_oslo_now().strftime('%H:%M:%S')} | "
                        f"Politifilter: ≤24t | Nyhetsfilter: ≤7d | Cache: 300s"
                    )

    st.markdown("</div>", unsafe_allow_html=True)   # mn-page


if __name__ == "__main__":
    main()
