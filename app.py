"""
MinOslo — Produksjonsversjon
==============================
Deploy:  Render.com
Start:   streamlit run app.py --server.port $PORT --server.address 0.0.0.0

Kilder:
  • Politiloggen API  — api.politiet.no   (JSON, siste 24t)
  • Oslo kommune RSS  — aktuelt.oslo.kommune.no  (siste 7 dager)
  • NRK Stor-Oslo     — nrk.no/stor-oslo/feed/  (Atom, siste 7 dager)
  • eInnsyn           — einnsyn.no/rss   (siste 7 dager)

Ruter trafikkstatus er en ren JavaScript-app uten skrapbar HTML —
den er utelatt; bruk heller nrk.no/stor-oslo som dekker Ruter-avvik.
"""

import streamlit as st
import streamlit.components.v1 as components
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
# TIDSSONE — norsk tid (Europe/Oslo = UTC+1 / UTC+2)
# Bruker en enkel offset i stedet for pytz/zoneinfo for å unngå
# ekstra avhengighet. Norge er UTC+2 i sommertid, UTC+1 ellers.
# ════════════════════════════════════════════════════════════════
def _oslo_now() -> datetime:
    """Returnerer nåværende tidspunkt i norsk tid (UTC+1 / +2)."""
    utc_now = datetime.now(timezone.utc)
    # DST: siste søndag i mars → siste søndag i oktober
    year = utc_now.year
    # Enkel DST-sjekk: mars 25 – oktober 25 ≈ norsk sommertid
    dst_start = datetime(year, 3, 25, 1, 0, tzinfo=timezone.utc)
    dst_end   = datetime(year, 10, 25, 1, 0, tzinfo=timezone.utc)
    offset = 2 if dst_start <= utc_now < dst_end else 1
    return utc_now.astimezone(timezone(timedelta(hours=offset)))

OSLO_TZ   = _oslo_now().tzinfo
NOW_OSLO  = _oslo_now()

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
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
}

MAX_ALDER_POLITI  = timedelta(hours=24)
MAX_ALDER_NYHETER = timedelta(days=7)

# Kilde-config: (url, kilde_navn, badge_kode, badge_farge, max_alder)
KILDER = [
    {
        "url":     "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=30",
        "navn":    "Politiloggen",
        "badge":   "P",
        "farge":   "#1a3a6a",
        "type":    "politilogg",
        "max_alder": MAX_ALDER_POLITI,
        "link":    "https://politiloggen.politiet.no",
    },
    {
        "url":     "https://aktuelt.oslo.kommune.no/?format=rss",
        "url_alt": ["https://www.oslo.kommune.no/rss/", "https://aktuelt.oslo.kommune.no/feed/"],
        "navn":    "Oslo kommune",
        "badge":   "K",
        "farge":   "#0a5c2a",
        "type":    "rss",
        "max_alder": MAX_ALDER_NYHETER,
        "link":    "https://aktuelt.oslo.kommune.no",
    },
    {
        "url":     "https://www.nrk.no/stor-oslo/feed/",
        "url_alt": ["https://www.nrk.no/toppsaker.rss"],
        "navn":    "NRK Stor-Oslo",
        "badge":   "N",
        "farge":   "#c00000",
        "type":    "rss",
        "max_alder": MAX_ALDER_NYHETER,
        "link":    "https://www.nrk.no/stor-oslo/",
    },
    {
        "url":     "https://einnsyn.no/rss?q=Oslo+kommune&antall=20",
        "navn":    "eInnsyn",
        "badge":   "E",
        "farge":   "#5a3090",
        "type":    "rss",
        "max_alder": MAX_ALDER_NYHETER,
        "link":    "https://einnsyn.no",
    },
]

PLACEHOLDER_SAKER = [
    {
        "overskrift": "Oslo-guide: De beste turene i Marka denne helgen",
        "ingress": "Oslomarka tilbyr fantastiske turer året rundt. Her er våre tips til helgens utflukt for hele familien.",
        "publisert": NOW_OSLO.strftime("%-d. %b %Y"),
        "kilde_url": "https://www.ut.no/omrade/3230/", "kilde_navn": "ut.no",
        "badge": "T", "badge_farge": "#2a6a3a",
        "bydel": "Hele Oslo", "kategori": "annet",
        "bilde_url": "", "brodtekst": [], "hva_skjer_videre": "", "tags": ["tur", "marka"],
        "sortert_dato": NOW_OSLO - timedelta(hours=1),
    },
    {
        "overskrift": "Hva skjer i Oslo denne uken?",
        "ingress": "Konserter, markeder og utstillinger — Oslo har et rikt kulturtilbud. Sjekk Visit Oslo for oppdatert program.",
        "publisert": NOW_OSLO.strftime("%-d. %b %Y"),
        "kilde_url": "https://www.visitoslo.com/no/", "kilde_navn": "Visit Oslo",
        "badge": "V", "badge_farge": "#2a5a8a",
        "bydel": "Hele Oslo", "kategori": "annet",
        "bilde_url": "", "brodtekst": [], "hva_skjer_videre": "", "tags": ["kultur", "arrangement"],
        "sortert_dato": NOW_OSLO - timedelta(hours=2),
    },
    {
        "overskrift": "Smart reise i Oslo: Alt om Ruter-appen og kollektivtilbudet",
        "ingress": "Med Ruter-appen er Oslo enkel å navigere. T-bane, buss, trikk og båt til alle bydeler.",
        "publisert": NOW_OSLO.strftime("%-d. %b %Y"),
        "kilde_url": "https://ruter.no", "kilde_navn": "Ruter",
        "badge": "R", "badge_farge": "#8a1a1a",
        "bydel": "Hele Oslo", "kategori": "annet",
        "bilde_url": "", "brodtekst": [], "hva_skjer_videre": "", "tags": ["kollektiv", "ruter"],
        "sortert_dato": NOW_OSLO - timedelta(hours=3),
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

LIGHT = {
    "bg":"#f0f0ee","bg_card":"#ffffff","bg_header":"#ffffff",
    "bg_sidebar":"#181818","bg_police":"#0b0b20",
    "border":"#e0ddd8","text_primary":"#111111","text_body":"#2a2a2a",
    "text_soft":"#666666","text_muted":"#999999","text_police":"#d8eeff",
    "accent":"#c8001e","accent2":"#1a4f8a",
    "tag_bg":"#eeece8","tag_text":"#555555",
    "meta_bg":"#f5f3f0","police_border":"#1a2860","police_item":"#121428",
}
DARK = {
    "bg":"#0d0d0d","bg_card":"#1a1a1a","bg_header":"#111111",
    "bg_sidebar":"#0a0a0a","bg_police":"#08081a",
    "border":"#2e2e2e","text_primary":"#f0f0f0","text_body":"#cccccc",
    "text_soft":"#888888","text_muted":"#555555","text_police":"#c4e0f8",
    "accent":"#e8001f","accent2":"#4a8fd4",
    "tag_bg":"#252525","tag_text":"#aaaaaa",
    "meta_bg":"#222222","police_border":"#1e2d5e","police_item":"#101830",
}

_KAT_KW = {
    "politilogg":"police,oslo,night","skjenkebevilling":"bar,pub,oslo",
    "byggesak":"construction,oslo","regulering":"park,urban,oslo",
    "politisk vedtak":"oslo,city-hall","kommune":"oslo,architecture",
    "nrk":"oslo,news,broadcast","einnsyn":"oslo,office","annet":"oslo,street",
}
_BYDEL_KW = {
    "Grünerløkka":"grunerlokka,oslo","Frogner":"frogner,oslo",
    "Sagene":"sagene,oslo","Gamle Oslo":"oslo,fjord",
    "Grorud":"oslo,east","St. Hanshaugen":"oslo,park",
    "Nordstrand":"oslo,south","Alna":"oslo,suburb",
}


# ════════════════════════════════════════════════════════════════
# CSS
# ════════════════════════════════════════════════════════════════
def build_css(t: dict) -> str:
    return f"""
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
#MainMenu,footer,header{{visibility:hidden;}}
.block-container{{padding:0!important;max-width:100%!important;}}
html,body,.stApp{{background:{t["bg"]}!important;font-family:'Inter',sans-serif;}}

[data-testid="stSidebar"]{{background:{t["bg_sidebar"]}!important;border-right:1px solid #222!important;}}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] span,[data-testid="stSidebar"] label{{color:#aaa!important;font-size:.75rem!important;}}
[data-testid="stSidebar"] .stTextInput input,[data-testid="stSidebar"] .stTextArea textarea,[data-testid="stSidebar"] .stSelectbox>div>div{{background:#252525!important;color:#eee!important;border-color:#3a3a3a!important;font-size:.84rem!important;}}
[data-testid="stSidebar"] hr{{border-color:#2a2a2a!important;margin:.5rem 0!important;}}
[data-testid="stSidebar"] .stButton>button{{background:{t["accent"]}!important;color:#fff!important;border:none!important;border-radius:4px!important;font-weight:700!important;font-size:.72rem!important;letter-spacing:.07em;text-transform:uppercase;width:100%;padding:.5rem!important;}}
[data-testid="stSidebar"] .stButton>button:hover{{opacity:.85!important;}}

.mn-header{{background:{t["bg_header"]};border-bottom:4px solid {t["accent"]};position:sticky;top:0;z-index:200;box-shadow:0 2px 8px rgba(0,0,0,.07);}}
.mn-inner{{max-width:1380px;margin:0 auto;padding:0 1.25rem;}}
.mn-top{{display:flex;align-items:baseline;justify-content:space-between;padding:.7rem 0 .2rem;}}
.mn-logo{{font-family:'Playfair Display',serif;font-size:clamp(1.55rem,4vw,2.15rem);font-weight:900;color:{t["accent"]};letter-spacing:-.03em;line-height:1;}}
.mn-logo span{{color:{t["text_primary"]};}}
.mn-dateline{{font-size:.6rem;color:{t["text_soft"]};letter-spacing:.12em;text-transform:uppercase;}}
.mn-nav{{display:flex;border-top:1px solid {t["border"]};overflow-x:auto;scrollbar-width:none;}}
.mn-nav::-webkit-scrollbar{{display:none;}}
.mn-nav-item{{font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:{t["text_soft"]};padding:.48rem .9rem;border-bottom:3px solid transparent;margin-bottom:-4px;white-space:nowrap;}}
.mn-nav-item.active{{color:{t["accent"]};border-bottom-color:{t["accent"]};}}

.mn-page{{max-width:1380px;margin:0 auto;padding:1.25rem 1.25rem 5rem;}}

.mn-label{{font-size:.62rem;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:{t["text_soft"]};border-top:2px solid {t["text_primary"]};padding-top:.4rem;margin:1.6rem 0 .9rem;}}
.mn-label-red{{border-top-color:{t["accent"]};color:{t["accent"]};}}

/* ── Kilde-badge (nytt design) ── */
.kilde-badge{{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:3px;font-size:.6rem;font-weight:800;color:#fff;flex-shrink:0;margin-right:.3rem;vertical-align:middle;}}
.kilde-pill{{display:inline-flex;align-items:center;font-size:.58rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:.15em .45em;border-radius:3px;color:#fff;margin-right:.3rem;}}

.mn-hero-body{{background:{t["bg_card"]};border:1px solid {t["border"]};border-top:none;border-radius:0 0 6px 6px;padding:1.2rem 1.4rem 1.5rem;margin-bottom:1.5rem;}}
.mn-hero-ingress{{font-size:.97rem;line-height:1.7;color:{t["text_body"]};margin:.35rem 0 .6rem;}}

.mn-card{{background:{t["bg_card"]};border:1px solid {t["border"]};border-radius:6px;overflow:hidden;margin-bottom:1rem;display:flex;flex-direction:column;}}
.mn-card-body{{padding:.85rem 1rem 1rem;flex:1;}}
.mn-card-ingress{{font-size:.84rem;line-height:1.6;color:{t["text_body"]};margin-top:.3rem;}}

.mn-meta{{display:flex;align-items:center;gap:.35rem;flex-wrap:wrap;margin-bottom:.28rem;}}
.mn-date{{font-size:.65rem;color:{t["text_muted"]};}}
.mn-badge-kat{{font-size:.56rem;font-weight:600;background:{t["meta_bg"]};color:{t["text_soft"]};padding:.2em .52em;border-radius:2px;border:1px solid {t["border"]};}}

.mn-source{{display:inline-block;margin-top:.5rem;font-size:.72rem;font-weight:600;color:{t["accent2"]};text-decoration:none;border-bottom:1px solid currentColor;padding-bottom:1px;}}
.mn-source:hover{{opacity:.75;}}

.mn-tags{{display:flex;flex-wrap:wrap;gap:.28rem;margin-top:.5rem;}}
.mn-tag{{font-size:.58rem;background:{t["tag_bg"]};color:{t["tag_text"]};border:1px solid {t["border"]};padding:.16em .46em;border-radius:20px;}}

.mn-police-box{{background:{t["bg_police"]};border:1px solid {t["police_border"]};border-radius:6px;padding:.9rem;}}
.mn-police-sticky{{position:sticky;top:78px;}}
.mn-police-hdr{{font-size:.63rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:{t["accent"]};display:flex;align-items:center;gap:.4rem;margin-bottom:.7rem;}}
.mn-dot{{width:6px;height:6px;border-radius:50%;background:{t["accent"]};animation:blink 1.4s infinite;flex-shrink:0;}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.15}}}}
.mn-police-item{{background:{t["police_item"]};border:1px solid {t["police_border"]};border-radius:4px;padding:.6rem .75rem;margin-bottom:.45rem;}}
.mn-p-time{{font-size:.58rem;color:{t["accent"]};font-weight:700;letter-spacing:.06em;margin-bottom:.15rem;}}
.mn-p-tekst{{font-size:.8rem;color:{t["text_police"]};line-height:1.5;}}
.mn-p-sted{{font-size:.62rem;color:#5a7fa8;margin-top:.15rem;}}
.mn-p-link{{font-size:.62rem;color:{t["accent2"]};margin-top:.3rem;text-decoration:none;border-bottom:1px solid currentColor;display:inline;}}

.mn-article{{background:{t["bg_card"]};border:1px solid {t["border"]};border-radius:6px;padding:2rem;margin-top:.75rem;}}
.mn-article h1{{font-family:'Playfair Display',serif;font-size:clamp(1.5rem,4vw,2.6rem);font-weight:900;line-height:1.1;color:{t["text_primary"]};margin-bottom:.9rem;}}
.mn-lead{{font-size:1.05rem;line-height:1.75;color:{t["text_body"]};border-left:4px solid {t["accent"]};padding-left:1rem;margin-bottom:1.5rem;}}
.mn-body-p{{font-size:.98rem;line-height:1.88;color:{t["text_body"]};margin-bottom:.9rem;}}
.mn-kilde-boks{{margin-top:1.3rem;padding-top:.8rem;border-top:1px solid {t["border"]};}}
.mn-kilde-boks a{{display:inline-block;background:{t["accent2"]};color:#fff;padding:.42rem .85rem;border-radius:4px;font-size:.75rem;font-weight:700;text-decoration:none;}}
.mn-kilde-boks a:hover{{opacity:.85;}}

.stButton>button{{background:transparent!important;color:{t["text_primary"]}!important;border:none!important;border-radius:0!important;font-family:'Playfair Display',serif!important;font-size:clamp(.95rem,2.5vw,1.08rem)!important;font-weight:700!important;text-align:left!important;padding:.1rem 0 0!important;line-height:1.25!important;width:100%!important;white-space:normal!important;height:auto!important;cursor:pointer!important;min-height:44px!important;}}
.stButton>button:hover{{color:{t["accent"]}!important;}}
.stButton>button:focus{{box-shadow:none!important;outline:none!important;}}
.mn-img-wrap{{line-height:0;}}

@media(max-width:768px){{
    .mn-page{{padding:.75rem .75rem 4rem;}}
    .mn-inner{{padding:0 .75rem;}}
    .mn-article{{padding:1rem;}}
    .mn-hero-body,.mn-card-body{{padding:.85rem;}}
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


def _parse_dato(dato_str: str) -> datetime | None:
    """
    Parser datostreng til tz-aware datetime i norsk tid.
    Prøver alle vanlige RSS/Atom-formater.
    """
    if not dato_str:
        return None
    dato_str = dato_str.strip()
    formater = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formater:
        try:
            dt = datetime.strptime(dato_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(OSLO_TZ)
        except Exception:
            continue
    # ISO-fromisoformat som siste utvei
    try:
        dt = datetime.fromisoformat(dato_str.replace("Z", "+00:00"))
        return dt.astimezone(OSLO_TZ)
    except Exception:
        return None


def _for_gammel(dt: datetime | None, max_alder: timedelta) -> bool:
    if dt is None:
        return False  # usikker dato → inkluder saken
    grense = _oslo_now() - max_alder
    return dt < grense


def _kort_dato(dt: datetime | None, raa: str = "") -> str:
    if dt:
        return dt.strftime("%-d. %b %Y, %H:%M")
    return raa[:10] if raa else "–"


# ════════════════════════════════════════════════════════════════
# KART
# ════════════════════════════════════════════════════════════════
_COORDS = {
    "Alna":(59.910,10.850),"Bjerke":(59.935,10.800),
    "Frogner":(59.920,10.710),"Gamle Oslo":(59.905,10.770),
    "Grorud":(59.955,10.870),"Grünerløkka":(59.927,10.760),
    "Nordre Aker":(59.960,10.750),"Nordstrand":(59.875,10.800),
    "Sagene":(59.938,10.755),"St. Hanshaugen":(59.928,10.735),
    "Stovner":(59.970,10.920),"Søndre Nordstrand":(59.845,10.820),
    "Ullern":(59.910,10.650),"Vestre Aker":(59.950,10.670),
    "Østensjø":(59.890,10.830),
}
_OSLO_COORD = (59.914, 10.752)


def vis_kart(bydel: str, h: int) -> None:
    lat, lon = _COORDS.get(bydel, _OSLO_COORD)
    bbox = f"{lon-.03},{lat-.015},{lon+.03},{lat+.015}"
    components.html(
        f'<!DOCTYPE html><html><body style="margin:0;overflow:hidden;">'
        f'<iframe src="https://www.openstreetmap.org/export/embed.html'
        f'?bbox={bbox}&layer=mapnik" '
        f'style="width:100%;height:{h}px;border:none;display:block;" '
        f'title="Kart"></iframe></body></html>',
        height=h, scrolling=False,
    )


def _unsplash(art: dict, w: int = 800) -> str:
    bkw = _BYDEL_KW.get(art.get("bydel", ""), "oslo")
    kkw = _KAT_KW.get(art.get("kategori", "annet"), "oslo")
    return f"https://source.unsplash.com/featured/{w}x460/?{bkw},{kkw}"


def vis_media(art: dict, h: int, alltid_bilde: bool = False) -> None:
    url = art.get("bilde_url", "").strip() or (_unsplash(art) if alltid_bilde else "")
    if url:
        st.markdown(
            f'<div class="mn-img-wrap">'
            f'<img src="{url}" style="width:100%;height:{h}px;'
            f'object-fit:cover;display:block;border-radius:6px 6px 0 0;" alt="" '
            f'onerror="this.parentElement.style.display=\'none\'">'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        vis_kart(art.get("bydel", "Oslo"), h)


# ════════════════════════════════════════════════════════════════
# DATA-HENTING
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def hent_politilogg(kilde: dict) -> tuple[list[dict], str]:
    """
    Politiloggen-API (JSON).
    Filtrerer ut meldinger eldre enn 24 timer (norsk tid).
    """
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
                "tittel":       tittel or tekst[:60] or "Politimelding",
                "tekst":        tekst or tittel,
                "tid":          _kort_dato(dt, tidsp),
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
    """
    Henter RSS/Atom med BeautifulSoup (tolerant for ødelagt XML).
    Prøver url, deretter url_alt-listen.
    Filtrerer på max_alder.
    """
    alle_url = [kilde["url"]] + kilde.get("url_alt", [])
    siste_feil = ""
    xml_tekst  = ""

    for url in alle_url:
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            if r.ok and "<" in r.text:
                xml_tekst = r.text
                break
            siste_feil = f"HTTP {r.status_code} fra {url}"
        except requests.exceptions.Timeout:
            siste_feil = f"Timeout ({HTTP_TIMEOUT}s) — {url}"
        except Exception as e:
            siste_feil = f"{type(e).__name__}: {e}"

    if not xml_tekst:
        return [], siste_feil or "Alle URL-er feilet"

    try:
        soup = BeautifulSoup(xml_tekst, "lxml-xml")
        items = soup.find_all("item") or soup.find_all("entry")

        kat_map = {
            "Oslo kommune": "kommune",
            "NRK Stor-Oslo": "nrk",
            "eInnsyn":       "einnsyn",
        }
        kategori = kat_map.get(kilde["navn"], "annet")

        ut = []
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

            # link-tag kan være tom-element med href-attributt (Atom)
            lenke = g("link")
            if not lenke:
                link_tag = item.find("link")
                if link_tag:
                    lenke = link_tag.get("href", "") or _rens(link_tag.get_text())

            dt = _parse_dato(pub)
            if _for_gammel(dt, kilde["max_alder"]):
                continue

            if tittel:
                ut.append({
                    "overskrift":       tittel,
                    "ingress":          (desc[:300] + "…") if len(desc) > 300 else desc,
                    "brodtekst":        [desc] if desc else [],
                    "publisert":        _kort_dato(dt, pub),
                    "kilde_url":        lenke or kilde["link"],
                    "kilde_navn":       kilde["navn"],
                    "badge":            kilde["badge"],
                    "badge_farge":      kilde["farge"],
                    "bydel":            "Hele Oslo",
                    "kategori":         kategori,
                    "bilde_url":        "",
                    "hva_skjer_videre": "",
                    "tags":             [kilde["navn"]],
                    "sortert_dato":     dt or (_oslo_now() - timedelta(hours=6)),
                })

        ut.sort(key=lambda x: x["sortert_dato"], reverse=True)
        return ut[:15], ""

    except Exception as e:
        return [], f"Parse-feil: {type(e).__name__}: {e}"


def hent_alle_kilder() -> tuple[list[dict], list[dict], dict]:
    """
    Henter alle kilder parallelt (sekvensielt i praksis pga. GIL,
    men cache gjør det raskt fra andre kall).
    Returnerer (politilogg, nyheter, debug_info).
    """
    politilogg = []
    nyheter    = []
    debug      = {}

    for kilde in KILDER:
        if kilde["type"] == "politilogg":
            data, feil = hent_politilogg(kilde)
            debug[kilde["navn"]] = {"ok": not feil, "feil": feil, "antall": len(data), "url": kilde["url"]}
            politilogg.extend(data)
        else:
            data, feil = hent_rss(kilde)
            debug[kilde["navn"]] = {"ok": not feil, "feil": feil, "antall": len(data), "url": kilde["url"]}
            for art in data:
                art.setdefault("badge",      kilde["badge"])
                art.setdefault("badge_farge",kilde["farge"])
            nyheter.extend(data)

    # Sorter alle nyheter etter dato (nyeste øverst)
    nyheter.sort(key=lambda x: x.get("sortert_dato", _oslo_now() - timedelta(days=7)), reverse=True)
    return politilogg, nyheter, debug


# ════════════════════════════════════════════════════════════════
# UI-HJELPERE
# ════════════════════════════════════════════════════════════════
def badge_html(art: dict) -> str:
    farge = art.get("badge_farge", "#555")
    kode  = art.get("badge", "?")
    navn  = art.get("kilde_navn", "")
    return (f'<span class="kilde-pill" style="background:{farge}" '
            f'title="{navn}">{kode} {navn}</span>')


def meta_html(art: dict) -> str:
    d = art.get("publisert", "")
    k = art.get("kategori", "")
    return (
        f'<div class="mn-meta">'
        + badge_html(art)
        + (f'<span class="mn-badge-kat">{k}</span>' if k and k not in ("kommune","nrk","einnsyn","politilogg") else "")
        + (f'<span class="mn-date">{d}</span>' if d else "")
        + "</div>"
    )


def kilde_html(art: dict, stor: bool = False) -> str:
    url  = art.get("kilde_url", "#")
    navn = art.get("kilde_navn", "Kilde")
    if stor:
        return (f'<div class="mn-kilde-boks">'
                f'<a href="{url}" target="_blank">📎 Les saken hos {navn}</a></div>')
    return f'<a href="{url}" target="_blank" class="mn-source">↗ Les hos {navn}</a>'


def tags_html(art: dict) -> str:
    s = "".join(f'<span class="mn-tag">{x}</span>' for x in art.get("tags", []))
    return f'<div class="mn-tags">{s}</div>' if s else ""


def politi_html(meldinger: list[dict]) -> str:
    if not meldinger:
        return (
            f'<div class="mn-police-box" style="text-align:center;padding:1.5rem;">'
            f'<p style="color:#5a7fa8;font-size:.82rem">Ingen nye meldinger siste 24 timer.</p>'
            f'<a href="https://politiloggen.politiet.no" target="_blank" '
            f'style="color:#4a8fd4;font-size:.75rem">↗ Se politiloggen direkte</a></div>'
        )
    items = "".join(
        f'<div class="mn-police-item">'
        f'<div class="mn-p-time">🚔 {p["tid"]} · {p["sted"]}</div>'
        f'<div class="mn-p-tekst">{p["tekst"][:180]}{"…" if len(p["tekst"])>180 else ""}</div>'
        f'<a href="{p["url"]}" target="_blank" class="mn-p-link">↗ Kilde: Politiet</a>'
        f'</div>'
        for p in meldinger
    )
    return (
        f'<div class="mn-police-box">'
        f'<div class="mn-police-hdr"><div class="mn-dot"></div>'
        f'LIVE — OSLO (siste 24t)</div>'
        f'{items}'
        f'<p style="font-size:.58rem;color:#3a5a80;margin-top:.5rem;text-align:center">'
        f'<a href="https://politiloggen.politiet.no" target="_blank" style="color:#4a8fd4">'
        f'↗ Alle meldinger hos Politiloggen</a></p></div>'
    )


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
            '<p style="font-family:\'Playfair Display\',serif;font-size:1.55rem;'
            'font-weight:900;color:#c8001e;margin:.1rem 0 0;letter-spacing:-.02em">'
            'MinOslo</p>'
            '<p style="font-size:.58rem;color:#555;margin:0 0 .2rem;'
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
                    ny_b   = st.text_area("Brødtekst (én linje = avsnitt)", height=80)
                    ny_bd  = st.selectbox("Bydel", BYDELER[1:])
                    ny_k   = st.selectbox("Kategori", KATEGORIER[1:])
                    ny_img = st.text_input("Bilde-URL (valgfritt)")
                    ny_src = st.text_input("Kilde-URL")
                    ny_sn  = st.text_input("Kilde-navn")
                    if st.form_submit_button("📌 Publiser som topsak"):
                        if ny_t.strip() and ny_i.strip():
                            st.session_state.manuell.insert(0, {
                                "overskrift": ny_t.strip(),
                                "ingress":    ny_i.strip(),
                                "brodtekst":  [l.strip() for l in ny_b.split("\n") if l.strip()],
                                "hva_skjer_videre": "",
                                "tags":       [ny_bd, ny_k],
                                "kilde_url":  ny_src.strip() or "#",
                                "kilde_navn": ny_sn.strip() or "Redaksjonen",
                                "badge":      "★",
                                "badge_farge":"#8a1a1a",
                                "bydel":      ny_bd,
                                "kategori":   ny_k,
                                "publisert":  _oslo_now().strftime("%-d. %b %Y, %H:%M"),
                                "bilde_url":  ny_img.strip(),
                                "sortert_dato": _oslo_now(),
                            })
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
        st.caption(f"Cache: 5 min · Norsk tid: {_oslo_now().strftime('%H:%M')}")

        st.markdown(
            '<p style="font-size:.58rem;color:#444;line-height:1.6;margin-top:.5rem">'
            'Kilder: Politiloggen, Oslo kommune, NRK Stor-Oslo, eInnsyn.</p>',
            unsafe_allow_html=True)

    # ── HEADER ────────────────────────────────────────────────
    dato = _oslo_now().strftime("%-d. %B %Y")
    st.markdown(
        f'<div class="mn-header"><div class="mn-inner">'
        f'<div class="mn-top">'
        f'<div class="mn-logo">Min<span>Oslo</span></div>'
        f'<div class="mn-dateline">{dato}</div>'
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

    # ── ARTIKKELVISNING (ingen API-kall) ──────────────────────
    if st.session_state.valgt:
        art = st.session_state.valgt
        if st.button("← Tilbake"):
            st.session_state.valgt = None
            st.rerun()
        vis_media(art, 340, alltid_bilde=True)
        st.markdown('<div class="mn-article">', unsafe_allow_html=True)
        st.markdown(meta_html(art), unsafe_allow_html=True)
        st.markdown(f'<h1>{art["overskrift"]}</h1>', unsafe_allow_html=True)
        st.markdown(f'<div class="mn-lead">{art["ingress"]}</div>', unsafe_allow_html=True)
        for avsnitt in art.get("brodtekst", []):
            st.markdown(f'<p class="mn-body-p">{avsnitt}</p>', unsafe_allow_html=True)
        if art.get("hva_skjer_videre"):
            st.markdown(f'<div class="mn-videre-boks">{art["hva_skjer_videre"]}</div>',
                        unsafe_allow_html=True)
        st.markdown(tags_html(art), unsafe_allow_html=True)
        st.markdown(kilde_html(art, stor=True), unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # ── API-KALL (etter header) ────────────────────────────────
    with st.spinner("Henter ferske nyheter…"):
        politi_data, nyheter_data, debug_info = hent_alle_kilder()

    # Bygg artikkel-liste: manuell (topsaker) øverst, deretter API
    alle: list[dict] = list(st.session_state.manuell) + nyheter_data

    # Bruk placeholder hvis ALT feiler
    if not alle:
        alle = list(PLACEHOLDER_SAKER)

    # Filtrer
    vis = list(alle)
    if bydel_v != "Alle bydeler":
        vis = [a for a in vis if a.get("bydel") == bydel_v]
    if kat_v != "Alle kategorier":
        vis = [a for a in vis if a.get("kategori") == kat_v]
    if not vis:
        vis = list(alle)   # tilbakestill filter hvis ingen treff

    # ── TABS (mobil-first) ────────────────────────────────────
    tab_nyheter, tab_politi = st.tabs(["📰 Nyheter", "🚔 Politilogg"])

    with tab_politi:
        st.markdown(
            '<div class="mn-label mn-label-red" style="margin-top:0">'
            'Politilogg — Oslo (siste 24 timer)</div>',
            unsafe_allow_html=True)
        st.markdown(politi_html(politi_data), unsafe_allow_html=True)
        if st.session_state.admin_inn:
            d = debug_info.get("Politiloggen", {})
            st.caption(f"⚙️ URL: {d.get('url','?')} | Hentet: {d.get('antall',0)} | Feil: {d.get('feil') or 'ingen'}")

    with tab_nyheter:
        col_news, col_police = st.columns([3, 1], gap="large")

        with col_news:
            st.markdown(
                '<div class="mn-label mn-label-red">Siste nytt fra Oslo</div>',
                unsafe_allow_html=True)

            # Hero
            hero = vis[0]
            vis_media(hero, 300, alltid_bilde=True)
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
            st.markdown("</div>", unsafe_allow_html=True)

            # Kortgrid
            resten = vis[1:]
            if resten:
                st.markdown('<div class="mn-label">Flere saker</div>',
                            unsafe_allow_html=True)
                for rad in range(0, len(resten), 2):
                    gruppe = resten[rad:rad + 2]
                    cols   = st.columns(len(gruppe), gap="small")
                    for col, art in zip(cols, gruppe):
                        with col:
                            st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                            vis_media(art, 140)
                            st.markdown('<div class="mn-card-body">', unsafe_allow_html=True)
                            st.markdown(meta_html(art), unsafe_allow_html=True)
                            if st.button(art["overskrift"], key=f"k_{id(art)}"):
                                st.session_state.valgt = art
                                st.rerun()
                            kort = art["ingress"][:160]
                            if len(art["ingress"]) > 160:
                                kort += "…"
                            st.markdown(
                                f'<p class="mn-card-ingress">{kort}</p>',
                                unsafe_allow_html=True)
                            st.markdown(kilde_html(art), unsafe_allow_html=True)
                            st.markdown("</div></div>", unsafe_allow_html=True)

            # Debug (kun admin)
            if st.session_state.admin_inn:
                with st.expander("⚙️ Debug (kun for admin)", expanded=False):
                    for navn, d in debug_info.items():
                        ikon = "✅" if d["ok"] else "❌"
                        st.write(f"{ikon} **{navn}** — {d['antall']} saker")
                        st.code(d["url"])
                        if d["feil"]:
                            st.error(d["feil"])
                    st.caption(
                        f"Norsk tid: {_oslo_now().strftime('%d.%m.%Y %H:%M:%S')} | "
                        f"Politifilter: siste 24t | Nyhetsfilter: siste 7 dager | "
                        f"Cache TTL: 300s"
                    )

        with col_police:
            st.markdown(
                '<div class="mn-label mn-label-red" style="margin-top:0">Politilogg</div>',
                unsafe_allow_html=True)
            st.markdown(
                politi_html(politi_data[:8]).replace(
                    'class="mn-police-box"',
                    'class="mn-police-box mn-police-sticky"'),
                unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
