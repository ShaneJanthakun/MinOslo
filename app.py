"""
MinOslo — Produksjonsversjon
==============================
Deploy:  Render.com
Start:   streamlit run app.py --server.port $PORT --server.address 0.0.0.0

Datakilder:
  • Politiloggen  — api.politiet.no (JSON, siste 24t)
  • Oslo kommune  — aktuelt.oslo.kommune.no (RSS, siste 7d)
  • NRK Stor-Oslo — nrk.no/stor-oslo/feed/ (Atom, siste 7d)
  • eInnsyn       — einnsyn.no/rss (RSS, siste 7d)

Bilder:
  • OSM Nominatim + Static Maps — for saker med gateadresse
  • Wikimedia Commons — kategorisert bildesøk, åpen lisens, hotlinking OK
  • Faste Oslo-fallback-bilder  — brukes hvis ingen av delene gir treff

NB: Ruter trafikkstatus er utelatt — siden er en ren JavaScript-app
    uten skrapbar HTML fra en server. NRK Stor-Oslo dekker Ruter-avvik.
    Pixabay krever API-nøkkel og forbyr permanent hotlinking av bilde-URL-er.
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import re
import html as html_mod
import urllib.parse

# ── MÅ stå absolutt først ─────────────────────────────────────
st.set_page_config(
    page_title="MinOslo",
    page_icon="🗞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════════════
# TIDSSONE — norsk tid uten eksterne avhengigheter
# ════════════════════════════════════════════════════════════════
def _oslo_now() -> datetime:
    utc = datetime.now(timezone.utc)
    year = utc.year
    dst_start = datetime(year, 3, 25, 1, tzinfo=timezone.utc)
    dst_end   = datetime(year, 10, 25, 1, tzinfo=timezone.utc)
    offset    = 2 if dst_start <= utc < dst_end else 1
    return utc.astimezone(timezone(timedelta(hours=offset)))

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

MAX_ALDER_POLITI  = timedelta(hours=24)
MAX_ALDER_NYHETER = timedelta(days=7)

# Faste Oslo-fallback-bilder (Wikimedia Commons, CC0/åpen lisens)
OSLO_FALLBACK_BILDER = [
    "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a6/Oslo_Opera_House_2.jpg/1280px-Oslo_Opera_House_2.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Oslo_Barcode_Project.jpg/1280px-Oslo_Barcode_Project.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f0/Oslo_night_panorama.jpg/1280px-Oslo_night_panorama.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/58/Oslo_Radhus.JPG/1280px-Oslo_Radhus.JPG",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Aker_Brygge_Oslo_2013.jpg/1280px-Aker_Brygge_Oslo_2013.jpg",
]

# Kategori → Wikimedia Commons bilde-URL (curated, stabile URLer)
KAT_BILDER = {
    "politilogg":      "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/Oslo_Politidistrikt.jpg/640px-Oslo_Politidistrikt.jpg",
    "kommune":         "https://upload.wikimedia.org/wikipedia/commons/thumb/5/58/Oslo_Radhus.JPG/640px-Oslo_Radhus.JPG",
    "nrk":             "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a6/Oslo_Opera_House_2.jpg/640px-Oslo_Opera_House_2.jpg",
    "einnsyn":         "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Oslo_Barcode_Project.jpg/640px-Oslo_Barcode_Project.jpg",
    "byggesak":        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Oslo_Barcode_Project.jpg/640px-Oslo_Barcode_Project.jpg",
    "skjenkebevilling":"https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Aker_Brygge_Oslo_2013.jpg/640px-Aker_Brygge_Oslo_2013.jpg",
    "regulering":      "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f0/Oslo_night_panorama.jpg/640px-Oslo_night_panorama.jpg",
    "annet":           "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a6/Oslo_Opera_House_2.jpg/640px-Oslo_Opera_House_2.jpg",
}

# Kilde-konfig
KILDER = [
    {
        "id":      "politiloggen",
        "url":     "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=30",
        "navn":    "Politiloggen",
        "badge":   "P",
        "farge":   "#1a3a6a",
        "type":    "politilogg",
        "max_alder": MAX_ALDER_POLITI,
        "link":    "https://politiloggen.politiet.no",
    },
    {
        "id":      "oslo",
        "url":     "https://aktuelt.oslo.kommune.no/?format=rss",
        "url_alt": ["https://www.oslo.kommune.no/rss/", "https://aktuelt.oslo.kommune.no/feed/"],
        "navn":    "Oslo kommune",
        "badge":   "K",
        "farge":   "#0a5c2a",
        "type":    "rss",
        "kategori":"kommune",
        "max_alder": MAX_ALDER_NYHETER,
        "link":    "https://aktuelt.oslo.kommune.no",
    },
    {
        "id":      "nrk",
        "url":     "https://www.nrk.no/stor-oslo/feed/",
        "url_alt": ["https://www.nrk.no/toppsaker.rss"],
        "navn":    "NRK Stor-Oslo",
        "badge":   "N",
        "farge":   "#c00000",
        "type":    "rss",
        "kategori":"nrk",
        "max_alder": MAX_ALDER_NYHETER,
        "link":    "https://www.nrk.no/stor-oslo/",
    },
    {
        "id":      "einnsyn",
        "url":     "https://einnsyn.no/rss?q=Oslo+kommune&antall=20",
        "navn":    "eInnsyn",
        "badge":   "E",
        "farge":   "#5a3090",
        "type":    "rss",
        "kategori":"einnsyn",
        "max_alder": MAX_ALDER_NYHETER,
        "link":    "https://einnsyn.no",
    },
]

PLACEHOLDER_SAKER = [
    {
        "overskrift": "Oslo-guide: De beste turene i Marka denne helgen",
        "ingress": "Oslomarka tilbyr fantastiske turer året rundt — for store og små.",
        "publisert": _oslo_now().strftime("%-d. %b %Y"),
        "kilde_url": "https://www.ut.no/omrade/3230/",
        "kilde_navn": "ut.no", "badge": "T", "badge_farge": "#2a6a3a",
        "bydel": "Hele Oslo", "kategori": "annet", "bilde_url": OSLO_FALLBACK_BILDER[0],
        "brodtekst": [], "hva_skjer_videre": "", "tags": ["tur","marka"],
        "sortert_dato": _oslo_now() - timedelta(hours=1),
    },
    {
        "overskrift": "Hva skjer i Oslo denne uken? Konserter og markeder",
        "ingress": "Oslo har et rikt kulturtilbud. Sjekk Visit Oslo for oppdatert program.",
        "publisert": _oslo_now().strftime("%-d. %b %Y"),
        "kilde_url": "https://www.visitoslo.com/no/",
        "kilde_navn": "Visit Oslo", "badge": "V", "badge_farge": "#2a5a8a",
        "bydel": "Hele Oslo", "kategori": "annet", "bilde_url": OSLO_FALLBACK_BILDER[1],
        "brodtekst": [], "hva_skjer_videre": "", "tags": ["kultur","arrangement"],
        "sortert_dato": _oslo_now() - timedelta(hours=2),
    },
    {
        "overskrift": "Ruter i Oslo: Alt om kollektivtilbudet i dag",
        "ingress": "Med Ruter-appen reiser du smart med t-bane, buss, trikk og båt.",
        "publisert": _oslo_now().strftime("%-d. %b %Y"),
        "kilde_url": "https://ruter.no",
        "kilde_navn": "Ruter", "badge": "R", "badge_farge": "#8a1a1a",
        "bydel": "Hele Oslo", "kategori": "annet", "bilde_url": OSLO_FALLBACK_BILDER[4],
        "brodtekst": [], "hva_skjer_videre": "", "tags": ["kollektiv","ruter"],
        "sortert_dato": _oslo_now() - timedelta(hours=3),
    },
]

BYDELER = [
    "Alle bydeler","Alna","Bjerke","Frogner","Gamle Oslo","Grorud",
    "Grünerløkka","Nordre Aker","Nordstrand","Sagene","St. Hanshaugen",
    "Stovner","Søndre Nordstrand","Ullern","Vestre Aker","Østensjø",
]
KATEGORIER = [
    "Alle kategorier","politilogg","kommune","nrk","einnsyn",
    "byggesak","skjenkebevilling","regulering","politisk vedtak","annet",
]

# ════════════════════════════════════════════════════════════════
# TEMA
# ════════════════════════════════════════════════════════════════
LIGHT = {
    "bg":"#f0f0ee","bg_card":"#ffffff","bg_header":"#ffffff",
    "bg_sidebar":"#181818","bg_police":"#0b0b20",
    "border":"#e0ddd8","text_primary":"#111111","text_body":"#2a2a2a",
    "text_soft":"#666666","text_muted":"#999999","text_police":"#d8eeff",
    "accent":"#c8001e","accent2":"#1a4f8a",
    "tag_bg":"#eeece8","tag_text":"#555555",
    "meta_bg":"#f5f3f0","police_border":"#1a2860","police_item":"#121428",
    "card_shadow":"rgba(0,0,0,0.08)",
}
DARK = {
    "bg":"#0d0d0d","bg_card":"#1a1a1a","bg_header":"#111111",
    "bg_sidebar":"#0a0a0a","bg_police":"#08081a",
    "border":"#2e2e2e","text_primary":"#f0f0f0","text_body":"#cccccc",
    "text_soft":"#888888","text_muted":"#555555","text_police":"#c4e0f8",
    "accent":"#e8001f","accent2":"#4a8fd4",
    "tag_bg":"#252525","tag_text":"#aaaaaa",
    "meta_bg":"#222222","police_border":"#1e2d5e","police_item":"#101830",
    "card_shadow":"rgba(0,0,0,0.35)",
}

# ════════════════════════════════════════════════════════════════
# CSS — masonry-inspirert grid, 16:9 bilder, runde hjørner
# ════════════════════════════════════════════════════════════════
def build_css(t: dict) -> str:
    return f"""
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* ── Reset ── */
#MainMenu,footer,header{{visibility:hidden;}}
.block-container{{padding:0!important;max-width:100%!important;}}
html,body,.stApp{{background:{t["bg"]}!important;font-family:'Inter',sans-serif;}}

/* ── Sidebar ── */
[data-testid="stSidebar"]{{background:{t["bg_sidebar"]}!important;border-right:1px solid #222!important;}}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] span,[data-testid="stSidebar"] label{{color:#aaa!important;font-size:.75rem!important;}}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stTextArea textarea,
[data-testid="stSidebar"] .stSelectbox>div>div{{background:#252525!important;color:#eee!important;border-color:#3a3a3a!important;}}
[data-testid="stSidebar"] hr{{border-color:#2a2a2a!important;margin:.5rem 0!important;}}
[data-testid="stSidebar"] .stButton>button{{
    background:{t["accent"]}!important;color:#fff!important;border:none!important;
    border-radius:6px!important;font-weight:700!important;font-size:.72rem!important;
    letter-spacing:.07em;text-transform:uppercase;width:100%;padding:.52rem!important;
}}
[data-testid="stSidebar"] .stButton>button:hover{{opacity:.85!important;}}

/* ── Sticky Header med rød linje ── */
.mn-header{{
    background:{t["bg_header"]};border-bottom:4px solid {t["accent"]};
    position:sticky;top:0;z-index:200;
    box-shadow:0 2px 12px {t["card_shadow"]};
}}
.mn-inner{{max-width:1440px;margin:0 auto;padding:0 1.5rem;}}
.mn-top{{display:flex;align-items:baseline;justify-content:space-between;padding:.75rem 0 .2rem;}}
.mn-logo{{font-family:'Playfair Display',serif;font-size:clamp(1.6rem,4vw,2.3rem);font-weight:900;color:{t["accent"]};letter-spacing:-.03em;line-height:1;}}
.mn-logo span{{color:{t["text_primary"]};}}
.mn-dateline{{font-size:.6rem;color:{t["text_soft"]};letter-spacing:.12em;text-transform:uppercase;}}
.mn-nav{{display:flex;border-top:1px solid {t["border"]};overflow-x:auto;scrollbar-width:none;}}
.mn-nav::-webkit-scrollbar{{display:none;}}
.mn-nav-item{{font-size:.66rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:{t["text_soft"]};padding:.52rem .95rem;border-bottom:3px solid transparent;margin-bottom:-4px;white-space:nowrap;}}
.mn-nav-item.active{{color:{t["accent"]};border-bottom-color:{t["accent"]};}}

/* ── Side-wrapper ── */
.mn-page{{max-width:1440px;margin:0 auto;padding:1.5rem 1.5rem 5rem;}}
.mn-section-label{{font-size:.62rem;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:{t["text_soft"]};border-top:2px solid {t["text_primary"]};padding-top:.45rem;margin:1.8rem 0 1rem;}}
.mn-section-label-red{{border-top-color:{t["accent"]};color:{t["accent"]};}}

/* ── Kilde-badge ── */
.mn-badge-pill{{
    display:inline-flex;align-items:center;gap:.25rem;
    font-size:.57rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
    padding:.18em .5em;border-radius:4px;color:#fff;flex-shrink:0;
}}

/* ── HERO-KORT (full bredde) ── */
.mn-hero{{
    border-radius:15px;overflow:hidden;margin-bottom:1.5rem;
    box-shadow:0 4px 24px {t["card_shadow"]};
    background:{t["bg_card"]};border:1px solid {t["border"]};
}}
.mn-hero-img{{
    width:100%;aspect-ratio:16/9;object-fit:cover;display:block;
}}
.mn-hero-body{{padding:1.4rem 1.8rem 1.8rem;}}
.mn-hero-title{{
    font-family:'Playfair Display',serif;
    font-size:clamp(1.5rem,2.8vw,2.2rem);font-weight:900;
    line-height:1.15;color:{t["text_primary"]};
    margin:.5rem 0 .75rem;
}}
.mn-hero-ingress{{font-size:1rem;line-height:1.7;color:{t["text_body"]};margin-bottom:.75rem;}}

/* ── GRID — 3 kolonner på PC, 1 på mobil ── */
.mn-grid{{
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:1.25rem;
    margin-bottom:1.5rem;
}}
/* Andre-rad stor sak: 2/3 bredde */
.mn-grid-wide{{
    display:grid;
    grid-template-columns:2fr 1fr;
    gap:1.25rem;
    margin-bottom:1.25rem;
}}

/* ── STANDARD KORT ── */
.mn-card{{
    background:{t["bg_card"]};border:1px solid {t["border"]};
    border-radius:15px;overflow:hidden;
    box-shadow:0 2px 12px {t["card_shadow"]};
    display:flex;flex-direction:column;
    transition:box-shadow .2s;
}}
.mn-card:hover{{box-shadow:0 6px 24px {t["card_shadow"]};}}
.mn-card-img{{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;}}
.mn-card-body{{padding:1rem 1.1rem 1.15rem;flex:1;display:flex;flex-direction:column;}}
.mn-card-title{{
    font-family:'Playfair Display',serif;
    font-size:1.05rem;font-weight:700;line-height:1.25;
    color:{t["text_primary"]};margin:.4rem 0 .55rem;
}}
.mn-card-ingress{{font-size:.84rem;line-height:1.6;color:{t["text_body"]};flex:1;}}

/* ── Meta-rad ── */
.mn-meta{{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;margin-bottom:.25rem;}}
.mn-date{{font-size:.65rem;color:{t["text_muted"]};}}
.mn-kat{{font-size:.56rem;font-weight:600;background:{t["meta_bg"]};color:{t["text_soft"]};padding:.18em .5em;border-radius:3px;border:1px solid {t["border"]};}}

/* ── Kildelenke ── */
.mn-src{{display:inline-block;margin-top:.6rem;font-size:.72rem;font-weight:600;color:{t["accent2"]};text-decoration:none;border-bottom:1px solid currentColor;}}
.mn-src:hover{{opacity:.75;}}

/* ── Tags ── */
.mn-tags{{display:flex;flex-wrap:wrap;gap:.28rem;margin-top:.55rem;}}
.mn-tag{{font-size:.58rem;background:{t["tag_bg"]};color:{t["tag_text"]};border:1px solid {t["border"]};padding:.16em .46em;border-radius:20px;}}

/* ── Politilogg ── */
.mn-police-wrap{{background:{t["bg_police"]};border:1px solid {t["police_border"]};border-radius:15px;padding:1rem;}}
.mn-police-hdr{{font-size:.63rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:{t["accent"]};display:flex;align-items:center;gap:.4rem;margin-bottom:.75rem;}}
.mn-dot{{width:6px;height:6px;border-radius:50%;background:{t["accent"]};animation:blink 1.4s infinite;flex-shrink:0;}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.15}}}}
.mn-p-item{{background:{t["police_item"]};border:1px solid {t["police_border"]};border-radius:8px;padding:.65rem .8rem;margin-bottom:.45rem;}}
.mn-p-time{{font-size:.58rem;color:{t["accent"]};font-weight:700;margin-bottom:.15rem;}}
.mn-p-tekst{{font-size:.8rem;color:{t["text_police"]};line-height:1.5;}}
.mn-p-sted{{font-size:.62rem;color:#5a7fa8;margin-top:.12rem;}}
.mn-p-link{{font-size:.62rem;color:{t["accent2"]};margin-top:.3rem;text-decoration:none;border-bottom:1px solid currentColor;display:inline;}}

/* ── Artikkel-fullvisning ── */
.mn-article{{background:{t["bg_card"]};border:1px solid {t["border"]};border-radius:15px;padding:2rem;margin-top:.75rem;box-shadow:0 4px 20px {t["card_shadow"]};}}
.mn-article h1{{font-family:'Playfair Display',serif;font-size:clamp(1.5rem,4vw,2.6rem);font-weight:900;line-height:1.1;color:{t["text_primary"]};margin-bottom:.9rem;}}
.mn-lead{{font-size:1.05rem;line-height:1.75;color:{t["text_body"]};border-left:4px solid {t["accent"]};padding-left:1rem;margin-bottom:1.5rem;}}
.mn-body-p{{font-size:.98rem;line-height:1.88;color:{t["text_body"]};margin-bottom:.9rem;}}
.mn-kilde-boks{{margin-top:1.3rem;padding-top:.8rem;border-top:1px solid {t["border"]};}}
.mn-kilde-boks a{{display:inline-block;background:{t["accent2"]};color:#fff;padding:.42rem .85rem;border-radius:6px;font-size:.75rem;font-weight:700;text-decoration:none;}}

/* ── Streamlit-knapper som artikkellenker ──
   Ingen z-index / overflow:hidden på wrapper — hindrer klikk-blokkering ── */
.stButton>button{{
    background:transparent!important;color:{t["text_primary"]}!important;
    border:none!important;border-radius:0!important;
    font-family:'Playfair Display',serif!important;
    font-size:clamp(.95rem,2.5vw,1.08rem)!important;font-weight:700!important;
    text-align:left!important;padding:0!important;
    line-height:1.25!important;width:100%!important;
    white-space:normal!important;height:auto!important;cursor:pointer!important;
    min-height:44px!important;
}}
.stButton>button:hover{{color:{t["accent"]}!important;}}
.stButton>button:focus{{box-shadow:none!important;outline:none!important;}}
.mn-img-wrap{{line-height:0;}}

/* ── Mobil-first ── */
@media(max-width:900px){{
    .mn-grid,.mn-grid-wide{{grid-template-columns:1fr!important;}}
    .mn-page{{padding:.75rem .75rem 4rem;}}
    .mn-inner{{padding:0 .75rem;}}
    .mn-hero-body{{padding:1rem;}}
    .mn-card-body{{padding:.85rem;}}
    .mn-article{{padding:1.25rem;}}
}}
@media(min-width:901px) and (max-width:1200px){{
    .mn-grid{{grid-template-columns:repeat(2,1fr)!important;}}
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
    return re.sub(r"\s+", " ", tekst).strip()


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
    return dt.strftime("%-d. %b %Y, %H:%M") if dt else raa[:10] or "–"


# ════════════════════════════════════════════════════════════════
# BILDEHÅNDTERING
# Prioritet:
#   1. Gateadresse i teksten → OSM Static Map (Nominatim + tile)
#   2. Kategori-bilde fra Wikimedia Commons (curated, stabile URLer)
#   3. Oslo-fallback-bilde (rullerende)
# ════════════════════════════════════════════════════════════════

# Oslo-spesifikke gatenavn-mønstre
_GATE_RE = re.compile(
    r"\b([A-ZÆØÅ][a-zæøåA-ZÆØÅ]+(?:gate|gata|vei|veien|allé|alléen|plass|"
    r"plassen|torg|torget|brygge|bryggen|kaia|kaien|bakke|bakken|"
    r"løkka|hagen|parken|stien)\b(?:\s+\d+[A-Za-z]?)?)",
    re.UNICODE,
)

@st.cache_data(ttl=3600, show_spinner=False)
def _osm_kart_url(adresse: str) -> str | None:
    """
    Slår opp adressen i Oslo via OSM Nominatim og returnerer
    en statisk kartbilde-URL via openstreetmap.org embed.
    Returnerer None ved feil.
    """
    try:
        params = {
            "q": f"{adresse}, Oslo, Norway",
            "format": "json",
            "limit": 1,
        }
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers={"User-Agent": "MinOslo/1.0 (minoslo.no)"},
            timeout=3,
        )
        hits = r.json()
        if not hits:
            return None
        lat = float(hits[0]["lat"])
        lon = float(hits[0]["lon"])
        # OSM embed — viser kart sentrert på koordinatene
        d = 0.003   # ~300m bounding box
        bbox = f"{lon-d},{lat-d},{lon+d},{lat+d}"
        return f"https://www.openstreetmap.org/export/embed.html?bbox={bbox}&layer=mapnik&marker={lat},{lon}"
    except Exception:
        return None


def _finn_bilde(art: dict, idx: int = 0) -> dict:
    """
    Returnerer art beriket med bilde_url og bilde_type:
      'manuell' | 'osm_kart' | 'wikimedia' | 'fallback'
    """
    # Manuelt satt bilde
    if art.get("bilde_url", "").startswith("http"):
        return {**art, "bilde_type": "manuell"}

    # Sjekk for gateadresse i tittel + ingress
    tekst = f"{art.get('overskrift','')} {art.get('ingress','')}"
    treff = _GATE_RE.findall(tekst)
    if treff:
        # OSM kart-embed brukes som iframe — registrer for senere
        return {**art, "bilde_url": "", "bilde_type": "osm_kart",
                "osm_adresse": treff[0]}

    # Wikimedia kategori-bilde
    kat_bilde = KAT_BILDER.get(art.get("kategori", "annet"), OSLO_FALLBACK_BILDER[0])
    return {**art, "bilde_url": kat_bilde, "bilde_type": "wikimedia"}


def vis_bilde(art: dict, h_px: int, rund: bool = True) -> None:
    """Viser bilde eller OSM-kart. h_px er bildehøyde i piksler."""
    radius = "15px 15px 0 0" if rund else "0"
    btype  = art.get("bilde_type", "wikimedia")

    if btype == "osm_kart":
        # OSM embed-iframe via components.html
        adresse = art.get("osm_adresse", "Oslo")
        osm_url = _osm_kart_url(adresse)
        if osm_url:
            components.html(
                f'<!DOCTYPE html><html><body style="margin:0;overflow:hidden;">'
                f'<iframe src="{osm_url}" '
                f'style="width:100%;height:{h_px}px;border:none;display:block;'
                f'border-radius:{radius};" title="Kart: {adresse}"></iframe>'
                f'</body></html>',
                height=h_px, scrolling=False,
            )
            return
        # Fallback hvis OSM feiler
        art = {**art, "bilde_url": KAT_BILDER.get(art.get("kategori","annet"), OSLO_FALLBACK_BILDER[0])}

    url = art.get("bilde_url") or OSLO_FALLBACK_BILDER[0]
    st.markdown(
        f'<div class="mn-img-wrap">'
        f'<img src="{url}" '
        f'style="width:100%;height:{h_px}px;object-fit:cover;display:block;'
        f'border-radius:{radius};" alt="" '
        f'onerror="this.src=\'{OSLO_FALLBACK_BILDER[0]}\'">'
        f'</div>',
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════
# DATA-HENTING (alle med ttl=300, timeout=5)
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def hent_politilogg(kilde: dict) -> tuple[list[dict], str]:
    try:
        r = requests.get(kilde["url"], headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        raw   = r.json()
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
            dt     = _parse_dato(tidsp)
            if _for_gammel(dt, kilde["max_alder"]):
                continue
            ut.append({
                "tittel":       tittel or tekst[:60] or "Politimelding",
                "tekst":        tekst or tittel,
                "tid":          _vis_dato(dt, tidsp),
                "sted":         sted,
                "url":          url,
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
    alle_url  = [kilde["url"]] + kilde.get("url_alt", [])
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
            siste_feil = f"Timeout ({HTTP_TIMEOUT}s) — {url}"
        except Exception as e:
            siste_feil = f"{type(e).__name__}: {e}"

    if not xml_tekst:
        return [], siste_feil or "Alle URL-er feilet"

    try:
        soup  = BeautifulSoup(xml_tekst, "lxml-xml")
        items = soup.find_all("item") or soup.find_all("entry")
        ut    = []
        for item in items:
            def g(*tags: str) -> str:
                for tag in tags:
                    n = item.find(tag)
                    if n and n.get_text(strip=True):
                        return _rens(n.get_text())
                return ""

            tittel = g("title")
            desc   = g("description", "summary", "content")
            pub    = g("pubDate", "published", "updated", "dc:date")
            lenke  = g("link")
            if not lenke:
                lt = item.find("link")
                if lt:
                    lenke = lt.get("href", "") or _rens(lt.get_text())

            dt = _parse_dato(pub)
            if _for_gammel(dt, kilde["max_alder"]):
                continue
            if not tittel:
                continue

            art = {
                "overskrift":       tittel,
                "ingress":          (desc[:300] + "…") if len(desc) > 300 else desc,
                "brodtekst":        [desc] if desc else [],
                "publisert":        _vis_dato(dt, pub),
                "kilde_url":        lenke or kilde["link"],
                "kilde_navn":       kilde["navn"],
                "badge":            kilde["badge"],
                "badge_farge":      kilde["farge"],
                "bydel":            "Hele Oslo",
                "kategori":         kilde.get("kategori", "annet"),
                "bilde_url":        "",
                "hva_skjer_videre": "",
                "tags":             [kilde["navn"]],
                "sortert_dato":     dt or (_oslo_now() - timedelta(hours=6)),
            }
            ut.append(_finn_bilde(art, len(ut)))

        ut.sort(key=lambda x: x["sortert_dato"], reverse=True)
        return ut[:15], ""
    except Exception as e:
        return [], f"Parse-feil: {type(e).__name__}: {e}"


def hent_alle() -> tuple[list[dict], list[dict], dict]:
    politi, nyheter, debug = [], [], {}
    for kilde in KILDER:
        if kilde["type"] == "politilogg":
            data, feil = hent_politilogg(kilde)
            debug[kilde["navn"]] = {"ok": not feil, "feil": feil,
                                    "antall": len(data), "url": kilde["url"]}
            politi.extend(data)
        else:
            data, feil = hent_rss(kilde)
            debug[kilde["navn"]] = {"ok": not feil, "feil": feil,
                                    "antall": len(data), "url": kilde["url"]}
            for a in data:
                a.setdefault("badge",       kilde["badge"])
                a.setdefault("badge_farge", kilde["farge"])
            nyheter.extend(data)

    nyheter.sort(key=lambda x: x.get("sortert_dato", _oslo_now() - timedelta(days=7)), reverse=True)
    return politi, nyheter, debug


# ════════════════════════════════════════════════════════════════
# UI-BYGGEKLOSSER
# ════════════════════════════════════════════════════════════════
def badge_html(art: dict) -> str:
    farge = art.get("badge_farge", "#555")
    kode  = art.get("badge", "?")
    navn  = art.get("kilde_navn", "")
    return (f'<span class="mn-badge-pill" style="background:{farge}" title="{navn}">'
            f'{kode}&nbsp;{navn}</span>')


def meta_html(art: dict) -> str:
    d = art.get("publisert", "")
    k = art.get("kategori", "")
    vis_kat = k not in ("kommune", "nrk", "einnsyn", "politilogg", "annet")
    return (
        f'<div class="mn-meta">'
        + badge_html(art)
        + (f'<span class="mn-kat">{k}</span>' if vis_kat else "")
        + (f'<span class="mn-date">{d}</span>' if d else "")
        + "</div>"
    )


def kilde_html(art: dict, stor: bool = False) -> str:
    url  = art.get("kilde_url", "#")
    navn = art.get("kilde_navn", "Kilde")
    if stor:
        return (f'<div class="mn-kilde-boks">'
                f'<a href="{url}" target="_blank">📎 Les saken hos {navn}</a></div>')
    return f'<a href="{url}" target="_blank" class="mn-src">↗ Les hos {navn}</a>'


def tags_html(art: dict) -> str:
    s = "".join(f'<span class="mn-tag">{x}</span>' for x in art.get("tags", []))
    return f'<div class="mn-tags">{s}</div>' if s else ""


def politi_html(meldinger: list[dict]) -> str:
    if not meldinger:
        return (f'<div class="mn-police-wrap" style="text-align:center;padding:1.5rem;">'
                f'<p style="color:#5a7fa8;font-size:.82rem">Ingen nye meldinger siste 24 timer.</p>'
                f'<a href="https://politiloggen.politiet.no" target="_blank" '
                f'style="color:#4a8fd4;font-size:.75rem">↗ Se politiloggen direkte</a></div>')
    items = "".join(
        f'<div class="mn-p-item">'
        f'<div class="mn-p-time">🚔 {p["tid"]} · {p["sted"]}</div>'
        f'<div class="mn-p-tekst">{p["tekst"][:180]}{"…" if len(p["tekst"])>180 else ""}</div>'
        f'<a href="{p["url"]}" target="_blank" class="mn-p-link">↗ Kilde: Politiet</a>'
        f'</div>'
        for p in meldinger
    )
    return (f'<div class="mn-police-wrap">'
            f'<div class="mn-police-hdr"><div class="mn-dot"></div>'
            f'LIVE — OSLO POLITIDISTRIKT (siste 24t)</div>'
            f'{items}'
            f'<p style="font-size:.58rem;color:#3a5a80;margin-top:.5rem;text-align:center">'
            f'<a href="https://politiloggen.politiet.no" target="_blank" style="color:#4a8fd4">'
            f'↗ Alle meldinger</a></p></div>')


# ════════════════════════════════════════════════════════════════
# MAIN
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
            '<p style="font-family:\'Playfair Display\',serif;font-size:1.6rem;'
            'font-weight:900;color:#c8001e;margin:.15rem 0 0;letter-spacing:-.02em">'
            'MinOslo</p>'
            '<p style="font-size:.58rem;color:#555;margin:0 0 .25rem;'
            'letter-spacing:.1em;text-transform:uppercase">Ekte nyheter fra Oslo</p>',
            unsafe_allow_html=True)
        st.markdown("---")

        # Admin
        st.markdown(
            '<p style="font-size:.6rem;font-weight:700;letter-spacing:.18em;'
            'text-transform:uppercase;color:#c8001e;margin-bottom:.3rem">🔒 Admin</p>',
            unsafe_allow_html=True)
        if not st.session_state.admin_inn:
            pw = st.text_input("Passord", type="password",
                               placeholder="Skriv passord…",
                               label_visibility="collapsed")
            if st.button("Logg inn", key="btn_login", use_container_width=True):
                if pw == ADMIN_PW:
                    st.session_state.admin_inn = True
                    st.rerun()
                elif pw:
                    st.markdown(
                        '<p style="color:#e8001f;font-size:.7rem">✗ Feil passord</p>',
                        unsafe_allow_html=True)
        else:
            st.markdown(
                '<p style="color:#4caf50;font-size:.7rem;margin-bottom:.4rem">✓ Innlogget</p>',
                unsafe_allow_html=True)
            with st.expander("📌 Legg til topsak", expanded=True):
                with st.form("admin_form", clear_on_submit=True):
                    ny_t   = st.text_input("Tittel *")
                    ny_i   = st.text_area("Ingress *", height=60)
                    ny_b   = st.text_area("Brødtekst", height=80)
                    ny_bd  = st.selectbox("Bydel", BYDELER[1:])
                    ny_k   = st.selectbox("Kategori", KATEGORIER[1:])
                    ny_img = st.text_input("Bilde-URL (valgfritt)")
                    ny_src = st.text_input("Kilde-URL")
                    ny_sn  = st.text_input("Kilde-navn")
                    if st.form_submit_button("📌 Publiser"):
                        if ny_t.strip() and ny_i.strip():
                            art = {
                                "overskrift": ny_t.strip(), "ingress": ny_i.strip(),
                                "brodtekst": [l.strip() for l in ny_b.split("\n") if l.strip()],
                                "hva_skjer_videre": "", "tags": [ny_bd, ny_k],
                                "kilde_url": ny_src.strip() or "#",
                                "kilde_navn": ny_sn.strip() or "Redaksjonen",
                                "badge": "★", "badge_farge": "#8a1a1a",
                                "bydel": ny_bd, "kategori": ny_k,
                                "publisert": _oslo_now().strftime("%-d. %b %Y, %H:%M"),
                                "bilde_url": ny_img.strip(),
                                "sortert_dato": _oslo_now(),
                            }
                            st.session_state.manuell.insert(0, _finn_bilde(art))
                            st.success("✓ Publisert!")
                            st.rerun()
                        else:
                            st.warning("Tittel og ingress er påkrevd.")
            if st.button("Logg ut", key="btn_logout", use_container_width=True):
                st.session_state.admin_inn = False
                st.rerun()

        st.markdown("---")
        dm = "☀️ Light Mode" if st.session_state.dark else "🌙 Dark Mode"
        if st.button(dm, key="btn_dm", use_container_width=True):
            st.session_state.dark = not st.session_state.dark
            st.rerun()
        st.markdown("---")

        st.markdown(
            '<p style="font-size:.6rem;font-weight:700;letter-spacing:.15em;'
            'text-transform:uppercase;color:#888;margin-bottom:.2rem">Filtrer</p>',
            unsafe_allow_html=True)
        bydel_v = st.selectbox("Bydel",    BYDELER,    label_visibility="collapsed", key="f_bd")
        kat_v   = st.selectbox("Kategori", KATEGORIER, label_visibility="collapsed", key="f_k")
        st.markdown("---")

        if st.button("🔄 Oppdater nå", key="btn_refresh", use_container_width=True):
            st.cache_data.clear()
            st.session_state.valgt = None
            st.rerun()
        st.caption(f"Cache 5 min · {_oslo_now().strftime('%H:%M')} norsk tid")
        st.markdown(
            '<p style="font-size:.56rem;color:#444;line-height:1.6;margin-top:.4rem">'
            'Kilder: Politiloggen, Oslo kommune, NRK Stor-Oslo, eInnsyn</p>',
            unsafe_allow_html=True)

    # ── HEADER ─────────────────────────────────────────────────
    dato = _oslo_now().strftime("%-d. %B %Y")
    st.markdown(
        f'<div class="mn-header"><div class="mn-inner">'
        f'<div class="mn-top">'
        f'<div class="mn-logo">Min<span>Oslo</span></div>'
        f'<div class="mn-dateline">Oslo · {dato}</div>'
        f'</div>'
        f'<nav class="mn-nav">'
        f'<span class="mn-nav-item active">Nyheter</span>'
        f'<span class="mn-nav-item">Politilogg</span>'
        f'<span class="mn-nav-item">Kommune</span>'
        f'<span class="mn-nav-item">NRK</span>'
        f'<span class="mn-nav-item">eInnsyn</span>'
        f'</nav></div></div>',
        unsafe_allow_html=True)

    st.markdown('<div class="mn-page">', unsafe_allow_html=True)

    # ── ARTIKKELVISNING (ingen API-kall nødvendig) ─────────────
    if st.session_state.valgt:
        art = st.session_state.valgt
        if st.button("← Tilbake"):
            st.session_state.valgt = None
            st.rerun()
        vis_bilde(art, 400, rund=True)
        st.markdown('<div class="mn-article">', unsafe_allow_html=True)
        st.markdown(meta_html(art), unsafe_allow_html=True)
        st.markdown(f'<h1>{art["overskrift"]}</h1>', unsafe_allow_html=True)
        st.markdown(f'<div class="mn-lead">{art["ingress"]}</div>', unsafe_allow_html=True)
        for avsnitt in art.get("brodtekst", []):
            st.markdown(f'<p class="mn-body-p">{avsnitt}</p>', unsafe_allow_html=True)
        if art.get("hva_skjer_videre"):
            st.markdown(
                f'<div style="background:{t["meta_bg"]};border-left:4px solid {t["accent2"]};'
                f'padding:.8rem 1.1rem;margin:1.3rem 0;border-radius:0 6px 6px 0;'
                f'font-size:.88rem;color:{t["text_body"]}">'
                f'<strong>Hva skjer videre:</strong> {art["hva_skjer_videre"]}</div>',
                unsafe_allow_html=True)
        st.markdown(tags_html(art), unsafe_allow_html=True)
        st.markdown(kilde_html(art, stor=True), unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # ── API-KALL (etter at header er synlig) ───────────────────
    with st.spinner("Henter ferske nyheter fra Oslo…"):
        politi_data, nyheter_data, debug_info = hent_alle()

    # Bygg liste: manuell øverst, deretter API
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

    # ── TABS ───────────────────────────────────────────────────
    tab_nyheter, tab_politi = st.tabs(["📰 Nyheter", "🚔 Politilogg"])

    with tab_politi:
        st.markdown(
            '<div class="mn-section-label mn-section-label-red" style="margin-top:0">'
            'Politilogg Live — Oslo (siste 24 timer)</div>',
            unsafe_allow_html=True)
        st.markdown(politi_html(politi_data), unsafe_allow_html=True)
        if st.session_state.admin_inn:
            d = debug_info.get("Politiloggen", {})
            st.caption(f"⚙️ {d.get('url','?')} | {d.get('antall',0)} meldinger | {d.get('feil') or 'OK'}")

    with tab_nyheter:
        # Full bredde — ingen høyre kolonne
        st.markdown(
            '<div class="mn-section-label mn-section-label-red" style="margin-top:0">'
            'Siste nytt fra Oslo</div>',
            unsafe_allow_html=True)

        if not vis:
            st.info("Ingen saker matcher filteret ditt. Prøv 'Alle bydeler'.")
        else:
            # ── HERO: første sak (full bredde) ─────────────────
            hero = vis[0]
            st.markdown('<div class="mn-hero">', unsafe_allow_html=True)
            vis_bilde(hero, 420, rund=False)
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

            # ── WIDE PAIR: sak 2 og 3 (2/3 + 1/3) ─────────────
            if len(vis) >= 3:
                st.markdown('<div class="mn-grid-wide">', unsafe_allow_html=True)
                for i, art in enumerate(vis[1:3]):
                    is_wide = (i == 0)
                    st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                    vis_bilde(art, 220 if is_wide else 180, rund=False)
                    st.markdown('<div class="mn-card-body">', unsafe_allow_html=True)
                    st.markdown(meta_html(art), unsafe_allow_html=True)
                    if st.button(art["overskrift"], key=f"w_{id(art)}"):
                        st.session_state.valgt = art
                        st.rerun()
                    st.markdown(
                        f'<p class="mn-card-ingress">{art["ingress"][:180]}{"…" if len(art["ingress"])>180 else ""}</p>',
                        unsafe_allow_html=True)
                    st.markdown(kilde_html(art), unsafe_allow_html=True)
                    st.markdown("</div></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            # ── 3-KOLONNE GRID: resten ──────────────────────────
            resten = vis[3:]
            if resten:
                st.markdown(
                    '<div class="mn-section-label">Flere saker</div>',
                    unsafe_allow_html=True)
                st.markdown('<div class="mn-grid">', unsafe_allow_html=True)
                for art in resten:
                    st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                    vis_bilde(art, 180, rund=False)
                    st.markdown('<div class="mn-card-body">', unsafe_allow_html=True)
                    st.markdown(meta_html(art), unsafe_allow_html=True)
                    if st.button(art["overskrift"], key=f"g_{id(art)}"):
                        st.session_state.valgt = art
                        st.rerun()
                    st.markdown(
                        f'<p class="mn-card-ingress">{art["ingress"][:140]}{"…" if len(art["ingress"])>140 else ""}</p>',
                        unsafe_allow_html=True)
                    st.markdown(kilde_html(art), unsafe_allow_html=True)
                    st.markdown("</div></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

        # Politilogg-stripe under nyhetene
        st.markdown(
            '<div class="mn-section-label mn-section-label-red">Politilogg — siste meldinger</div>',
            unsafe_allow_html=True)
        st.markdown(politi_html(politi_data[:6]), unsafe_allow_html=True)

        # Debug for admin
        if st.session_state.admin_inn:
            with st.expander("⚙️ Debug (kun for admin)", expanded=False):
                for navn, d in debug_info.items():
                    ikon = "✅" if d["ok"] else "❌"
                    st.write(f"{ikon} **{navn}** — {d['antall']} saker hentet")
                    st.code(d["url"])
                    if d["feil"]:
                        st.error(d["feil"])
                st.caption(
                    f"Norsk tid: {_oslo_now().strftime('%d.%m.%Y %H:%M:%S')} | "
                    f"Politifilter: ≤24t | Nyhetsfilter: ≤7d | Cache: 300s"
                )

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
