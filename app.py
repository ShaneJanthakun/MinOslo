"""
MinOslo — Ekte nettavis for Oslo
==================================
Deploy:  Render.com
Start:   streamlit run app.py --server.port $PORT --server.address 0.0.0.0

ARKITEKTUR — slik unngår vi svart skjerm:
  1. set_page_config() — første kall, ingen nettverkskall her
  2. Konstanter og funksjoner defineres (ingen bivirkninger)
  3. main() kalles — tegner CSS + header umiddelbart
  4. Sidebar-widgets tegnes (ingen blokkering)
  5. API-kall skjer ETTER at header er synlig, inne i st.spinner()
  6. Data vises

Datakilder:
  • Politiloggen: https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo
  • Oslo kommune:  https://aktuelt.oslo.kommune.no/?format=rss
  • eInnsyn:       https://einnsyn.no/rss?q=Oslo+kommune
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import html as html_mod
import re

# ── MÅ være absolutt første Streamlit-kall, ingen nettverkskall over ──────
st.set_page_config(
    page_title="MinOslo",
    page_icon="🗞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════════════
# KONSTANTER  (kun strenger/dicts — ingen bivirkninger)
# ════════════════════════════════════════════════════════════════
ADMIN_PW     = "løkka2024"
HTTP_TIMEOUT = 3    # STRENG: 3 sekunder maks per kall — aldri blokker UI
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    ),
    "Accept": "application/json, application/xml, text/xml, */*",
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
}

POLITIET_URL  = "https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=20"
POLITIET_LINK = "https://politiloggen.politiet.no/oslo"

OSLO_RSS_URLS = [
    "https://aktuelt.oslo.kommune.no/?format=rss",
    "https://www.oslo.kommune.no/rss/",
    "https://aktuelt.oslo.kommune.no/feed/",
]
OSLO_LINK    = "https://aktuelt.oslo.kommune.no"

EINNSYN_URL  = "https://einnsyn.no/rss?q=Oslo+kommune&antall=20"
EINNSYN_LINK = "https://einnsyn.no"

_KAT_KW = {
    "politilogg":      "police,oslo,night,city",
    "skjenkebevilling":"bar,pub,oslo,drinks",
    "byggesak":        "construction,building,oslo",
    "regulering":      "park,urban,oslo",
    "politisk vedtak": "oslo,city-hall,government",
    "kommune":         "oslo,norway,architecture",
    "einnsyn":         "oslo,document,office",
    "annet":           "oslo,norway,street",
}
_BYDEL_KW = {
    "Grünerløkka":"grunerlokka,oslo", "Frogner":"frogner,oslo",
    "Sagene":"sagene,oslo",           "Gamle Oslo":"oslo,fjord",
    "Grorud":"oslo,east",             "St. Hanshaugen":"oslo,park",
    "Nordstrand":"oslo,south,fjord",  "Alna":"oslo,suburb",
    "Bjerke":"oslo,east",             "Nordre Aker":"oslo,north,forest",
    "Stovner":"oslo,apartment",       "Søndre Nordstrand":"oslo,south",
    "Ullern":"oslo,west",             "Vestre Aker":"oslo,west,villa",
    "Østensjø":"oslo,lake",
}

BYDELER = [
    "Alle bydeler","Alna","Bjerke","Frogner","Gamle Oslo","Grorud",
    "Grünerløkka","Nordre Aker","Nordstrand","Sagene","St. Hanshaugen",
    "Stovner","Søndre Nordstrand","Ullern","Vestre Aker","Østensjø",
]
KATEGORIER = [
    "Alle kategorier","politilogg","kommune","einnsyn",
    "byggesak","skjenkebevilling","regulering","politisk vedtak","annet",
]

LIGHT = {
    "bg":"#f0f0ee","bg_card":"#ffffff","bg_header":"#ffffff",
    "bg_sidebar":"#181818","bg_police":"#0b0b20",
    "border":"#e0ddd8","text_primary":"#111111","text_body":"#2a2a2a",
    "text_soft":"#666666","text_muted":"#aaaaaa","text_police":"#d8eeff",
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
[data-testid="stSidebar"] .stTextInput input,[data-testid="stSidebar"] .stTextArea textarea,[data-testid="stSidebar"] .stSelectbox>div>div{{background:#252525!important;color:#eee!important;border-color:#3a3a3a!important;}}
[data-testid="stSidebar"] hr{{border-color:#2a2a2a!important;margin:.5rem 0!important;}}
[data-testid="stSidebar"] .stButton>button{{background:{t["accent"]}!important;color:#fff!important;border:none!important;border-radius:4px!important;font-weight:700!important;font-size:.72rem!important;letter-spacing:.07em;text-transform:uppercase;width:100%;padding:.5rem!important;}}
[data-testid="stSidebar"] .stButton>button:hover{{opacity:.85!important;}}

.mn-header{{background:{t["bg_header"]};border-bottom:4px solid {t["accent"]};position:sticky;top:0;z-index:200;}}
.mn-inner{{max-width:1380px;margin:0 auto;padding:0 1rem;}}
.mn-top{{display:flex;align-items:baseline;justify-content:space-between;padding:.7rem 0 .2rem;}}
.mn-logo{{font-family:'Playfair Display',serif;font-size:clamp(1.6rem,4vw,2.2rem);font-weight:900;color:{t["accent"]};letter-spacing:-.03em;line-height:1;}}
.mn-logo span{{color:{t["text_primary"]};}}
.mn-dateline{{font-size:.6rem;color:{t["text_soft"]};letter-spacing:.12em;text-transform:uppercase;}}
.mn-nav{{display:flex;border-top:1px solid {t["border"]};overflow-x:auto;}}
.mn-nav-item{{font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:{t["text_soft"]};padding:.5rem .9rem;border-bottom:3px solid transparent;margin-bottom:-4px;white-space:nowrap;}}
.mn-nav-item.active{{color:{t["accent"]};border-bottom-color:{t["accent"]};}}

.mn-page{{max-width:1380px;margin:0 auto;padding:1rem 1rem 5rem;}}
.mn-label{{font-size:.62rem;font-weight:700;letter-spacing:.2em;text-transform:uppercase;color:{t["text_soft"]};border-top:2px solid {t["text_primary"]};padding-top:.4rem;margin:1.4rem 0 .8rem;}}
.mn-label-red{{border-top-color:{t["accent"]};color:{t["accent"]};}}

.mn-card{{background:{t["bg_card"]};border:1px solid {t["border"]};border-radius:6px;overflow:hidden;margin-bottom:1rem;}}
.mn-card-body{{padding:.85rem 1rem 1rem;}}
.mn-card-ingress{{font-size:.85rem;line-height:1.6;color:{t["text_body"]};margin-top:.3rem;}}
.mn-hero-body{{background:{t["bg_card"]};border:1px solid {t["border"]};border-top:none;border-radius:0 0 6px 6px;padding:1.1rem 1.2rem 1.4rem;}}
.mn-hero-ingress{{font-size:.95rem;line-height:1.68;color:{t["text_body"]};margin:.3rem 0 .6rem;}}

.mn-meta{{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;margin-bottom:.25rem;}}
.mn-badge{{font-size:.56rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;background:{t["accent"]};color:#fff;padding:.2em .5em;border-radius:2px;}}
.mn-badge-kat{{font-size:.56rem;font-weight:600;background:{t["meta_bg"]};color:{t["text_soft"]};padding:.2em .5em;border-radius:2px;border:1px solid {t["border"]};}}
.mn-date{{font-size:.65rem;color:{t["text_muted"]};}}

.mn-source-link{{display:inline-block;margin-top:.6rem;font-size:.72rem;font-weight:600;color:{t["accent2"]};text-decoration:none;border-bottom:1px solid {t["accent2"]};padding-bottom:1px;}}
.mn-source-link:hover{{opacity:.75;}}

.mn-tags{{display:flex;flex-wrap:wrap;gap:.28rem;margin-top:.55rem;}}
.mn-tag{{font-size:.58rem;background:{t["tag_bg"]};color:{t["tag_text"]};border:1px solid {t["border"]};padding:.16em .46em;border-radius:20px;}}

.mn-police-box{{background:{t["bg_police"]};border:1px solid {t["police_border"]};border-radius:6px;padding:.9rem;}}
.mn-police-sticky{{position:sticky;top:76px;}}
.mn-police-hdr{{font-size:.63rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:{t["accent"]};display:flex;align-items:center;gap:.4rem;margin-bottom:.7rem;}}
.mn-dot{{width:6px;height:6px;border-radius:50%;background:{t["accent"]};animation:blink 1.4s infinite;flex-shrink:0;}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.15}}}}
.mn-police-item{{background:{t["police_item"]};border:1px solid {t["police_border"]};border-radius:4px;padding:.6rem .75rem;margin-bottom:.45rem;}}
.mn-p-time{{font-size:.58rem;color:{t["accent"]};font-weight:700;letter-spacing:.06em;margin-bottom:.15rem;}}
.mn-p-tekst{{font-size:.8rem;color:{t["text_police"]};line-height:1.5;}}
.mn-p-sted{{font-size:.62rem;color:#5a7fa8;margin-top:.15rem;}}
.mn-p-link{{font-size:.62rem;color:{t["accent2"]};margin-top:.3rem;text-decoration:none;border-bottom:1px solid {t["accent2"]};display:inline;}}

.mn-article{{background:{t["bg_card"]};border:1px solid {t["border"]};border-radius:6px;padding:1.5rem;margin-top:.5rem;}}
.mn-article h1{{font-family:'Playfair Display',serif;font-size:clamp(1.5rem,4vw,2.6rem);font-weight:900;line-height:1.1;color:{t["text_primary"]};margin-bottom:.85rem;}}
.mn-lead{{font-size:1.05rem;line-height:1.75;color:{t["text_body"]};border-left:4px solid {t["accent"]};padding-left:1rem;margin-bottom:1.5rem;}}
.mn-p{{font-size:.98rem;line-height:1.88;color:{t["text_body"]};margin-bottom:.9rem;}}
.mn-videre{{background:{t["meta_bg"]};border-left:4px solid {t["accent2"]};padding:.8rem 1.1rem;margin:1.3rem 0;border-radius:0 4px 4px 0;font-size:.88rem;color:{t["text_body"]};}}
.mn-kilde-boks{{margin-top:1.4rem;padding-top:.85rem;border-top:1px solid {t["border"]};}}
.mn-kilde-boks a{{display:inline-block;background:{t["accent2"]};color:#fff;padding:.45rem .9rem;border-radius:4px;font-size:.76rem;font-weight:700;letter-spacing:.06em;text-decoration:none;margin-right:.5rem;margin-top:.4rem;}}
.mn-kilde-boks a:hover{{opacity:.85;}}

/* Streamlit-knapper som titler — ingen z-index/overflow:hidden */
.stButton>button{{
    background:transparent!important;color:{t["text_primary"]}!important;
    border:none!important;border-radius:0!important;
    font-family:'Playfair Display',serif!important;
    font-size:clamp(1rem,2.5vw,1.1rem)!important;font-weight:700!important;
    text-align:left!important;padding:.1rem 0 0!important;
    line-height:1.25!important;width:100%!important;
    white-space:normal!important;height:auto!important;cursor:pointer!important;
    min-height:44px!important;
}}
.stButton>button:hover{{color:{t["accent"]}!important;}}
.stButton>button:focus{{box-shadow:none!important;outline:none!important;}}
.mn-img-wrap{{line-height:0;}}

@media(max-width:768px){{
    .mn-page{{padding:.6rem .6rem 4rem;}}
    .mn-inner{{padding:0 .75rem;}}
    .mn-article{{padding:1rem;}}
    .mn-hero-body{{padding:.9rem;}}
    .mn-card-body{{padding:.75rem;}}
}}
</style>
"""


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
_OSLO = (59.914, 10.752)


def vis_kart(bydel: str, h: int) -> None:
    lat, lon = _COORDS.get(bydel, _OSLO)
    bbox = f"{lon-.03},{lat-.015},{lon+.03},{lat+.015}"
    components.html(
        f'<!DOCTYPE html><html><body style="margin:0;overflow:hidden;">'
        f'<iframe src="https://www.openstreetmap.org/export/embed.html'
        f'?bbox={bbox}&layer=mapnik" '
        f'style="width:100%;height:{h}px;border:none;display:block;"'
        f' title="Kart"></iframe></body></html>',
        height=h, scrolling=False,
    )


def unsplash_url(art: dict, w: int = 800) -> str:
    bkw = _BYDEL_KW.get(art.get("bydel", ""), "oslo")
    kkw = _KAT_KW.get(art.get("kategori", "annet"), "oslo")
    return f"https://source.unsplash.com/featured/{w}x460/?{bkw},{kkw}"


def vis_media(art: dict, h: int, alltid_bilde: bool = False) -> None:
    url = art.get("bilde_url", "").strip() or (unsplash_url(art) if alltid_bilde else "")
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
# RENSING
# ════════════════════════════════════════════════════════════════
def _rens(tekst: str) -> str:
    tekst = html_mod.unescape(tekst or "")
    return re.sub(r"<[^>]+>", "", tekst).strip()


# ════════════════════════════════════════════════════════════════
# DATA-HENTING  — alle kall har timeout=3, ingen krasjer appen
# Disse kalles INNE i main(), ETTER at header er tegnet.
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=180, show_spinner=False)
def hent_politilogg() -> tuple[list[dict], str]:
    """
    Returnerer (meldinger, feilmelding).
    feilmelding er tom streng ved suksess.
    timeout=3 — hvis politiet ikke svarer på 3s, gir vi opp.
    """
    try:
        r = requests.get(
            POLITIET_URL,
            headers=HTTP_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()

        raw = r.json()
        # API kan returnere liste direkte, eller dict med "meldinger"/"data"
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = (raw.get("meldinger")
                     or raw.get("data")
                     or raw.get("results")
                     or [])
        else:
            return [], f"Ukjent responsformat: {type(raw)}"

        resultat = []
        for m in items[:12]:
            tittel = _rens(m.get("tittel") or m.get("title") or "")
            tekst  = _rens(m.get("tekst")  or m.get("text")  or m.get("description") or "")
            tidsp  = m.get("tidspunkt") or m.get("publishedOn") or m.get("created") or ""
            sted   = _rens(m.get("sted") or m.get("location") or m.get("district") or "Oslo")
            lenke  = m.get("url") or m.get("link") or POLITIET_LINK
            try:
                dt = datetime.fromisoformat(tidsp.replace("Z", "+00:00"))
                tid_vis = dt.strftime("%-d. %b %H:%M")
            except Exception:
                tid_vis = tidsp[:16] if tidsp else "–"
            resultat.append({
                "tittel": tittel or tekst[:60] or "Politimelding",
                "tekst":  tekst  or tittel,
                "tid":    tid_vis,
                "sted":   sted,
                "url":    lenke,
            })
        return resultat, ""

    except requests.exceptions.Timeout:
        return [], f"Timeout etter {HTTP_TIMEOUT}s — politiet.no svarer ikke"
    except requests.exceptions.ConnectionError as e:
        return [], f"Tilkoblingsfeil: {e}"
    except requests.exceptions.HTTPError as e:
        return [], f"HTTP-feil {e.response.status_code}: {e}"
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


@st.cache_data(ttl=600, show_spinner=False)
def hent_oslo_rss() -> tuple[list[dict], str]:
    """Prøver OSLO_RSS_URLS i rekkefølge. timeout=3 per URL."""
    siste_feil = ""
    siste_url  = ""

    for url in OSLO_RSS_URLS:
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            if r.ok and "<" in r.text:
                siste_url = url
                break
            siste_feil = f"HTTP {r.status_code} fra {url}"
            siste_url  = url
        except requests.exceptions.Timeout:
            siste_feil = f"Timeout ({HTTP_TIMEOUT}s) på {url}"
            siste_url  = url
            continue
        except Exception as e:
            siste_feil = f"{type(e).__name__} på {url}: {e}"
            siste_url  = url
            continue
    else:
        return [], siste_feil or "Alle RSS-URL-er feilet"

    try:
        root = ET.fromstring(r.text)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        resultat = []
        for item in items[:10]:
            def g(tag: str) -> str:
                n = item.find(tag)
                return _rens(n.text or "") if n is not None and n.text else ""
            tittel = g("title") or g("atom:title")
            lenke  = g("link")  or g("atom:link")
            desc   = g("description") or g("atom:summary") or g("atom:content")
            pub    = g("pubDate") or g("atom:published") or g("atom:updated")
            dato_vis = pub[:10]
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT",
                        "%Y-%m-%dT%H:%M:%S%z"):
                try:
                    dato_vis = datetime.strptime(pub.strip(), fmt).strftime("%-d. %b %Y")
                    break
                except Exception:
                    pass
            if tittel:
                resultat.append({
                    "overskrift": tittel,
                    "ingress":    (desc[:280] + "…") if len(desc) > 280 else desc,
                    "brodtekst":  [desc] if desc else [],
                    "publisert":  dato_vis,
                    "kilde_url":  lenke or OSLO_LINK,
                    "kilde_navn": "Oslo kommune",
                    "bydel":      "Hele Oslo",
                    "kategori":   "kommune",
                    "bilde_url":  "",
                    "hva_skjer_videre": "",
                    "tags":       ["Oslo kommune"],
                })
        return resultat, ""
    except ET.ParseError as e:
        return [], f"XML-parsefeil fra {siste_url}: {e}"
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


@st.cache_data(ttl=600, show_spinner=False)
def hent_einnsyn() -> tuple[list[dict], str]:
    """Henter offentlige saksdokumenter fra eInnsyn. timeout=3."""
    try:
        r = requests.get(EINNSYN_URL, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        root  = ET.fromstring(r.text)
        items = root.findall(".//item")
        resultat = []
        for item in items[:8]:
            def g(tag: str) -> str:
                n = item.find(tag)
                return _rens(n.text or "") if n is not None and n.text else ""
            tittel = g("title")
            lenke  = g("link")
            desc   = g("description")
            pub    = g("pubDate")
            dato_vis = pub[:10]
            try:
                dato_vis = datetime.strptime(pub[:25].strip(),
                                             "%a, %d %b %Y %H:%M:%S").strftime("%-d. %b %Y")
            except Exception:
                pass
            if tittel:
                resultat.append({
                    "overskrift": tittel,
                    "ingress":    (desc[:240] + "…") if len(desc) > 240 else desc,
                    "brodtekst":  [desc] if desc else [],
                    "publisert":  dato_vis,
                    "kilde_url":  lenke or EINNSYN_LINK,
                    "kilde_navn": "eInnsyn",
                    "bydel":      "Hele Oslo",
                    "kategori":   "einnsyn",
                    "bilde_url":  "",
                    "hva_skjer_videre": "",
                    "tags":       ["eInnsyn", "offentlig"],
                })
        return resultat, ""
    except requests.exceptions.Timeout:
        return [], f"Timeout etter {HTTP_TIMEOUT}s — einnsyn.no svarer ikke"
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


# ════════════════════════════════════════════════════════════════
# UI-HJELPERE
# ════════════════════════════════════════════════════════════════
def meta_html(art: dict) -> str:
    b = art.get("bydel",""); k = art.get("kategori",""); d = art.get("publisert","")
    return (f'<div class="mn-meta">'
            + (f'<span class="mn-badge">{b}</span>' if b else "")
            + (f'<span class="mn-badge-kat">{k}</span>' if k else "")
            + (f'<span class="mn-date">{d}</span>' if d else "")
            + '</div>')


def kilde_html(art: dict, stor: bool = False) -> str:
    url  = art.get("kilde_url","#")
    navn = art.get("kilde_navn","Kilde")
    if stor:
        return (f'<div class="mn-kilde-boks">'
                f'<a href="{url}" target="_blank">📎 Les saken hos {navn}</a></div>')
    return (f'<a href="{url}" target="_blank" class="mn-source-link">'
            f'↗ Kilde: {navn}</a>')


def tags_html(art: dict) -> str:
    s = "".join(f'<span class="mn-tag">{x}</span>' for x in art.get("tags",[]))
    return f'<div class="mn-tags">{s}</div>' if s else ""


def politi_boks(meldinger: list[dict], maks: int = 20) -> str:
    items = "".join(
        f'<div class="mn-police-item">'
        f'<div class="mn-p-time">🚔 {p["tid"]}</div>'
        f'<div class="mn-p-tekst">{p["tekst"][:160]}{"…" if len(p["tekst"])>160 else ""}</div>'
        f'<div class="mn-p-sted">📍 {p["sted"]}</div>'
        f'<a href="{p["url"]}" target="_blank" class="mn-p-link">↗ Kilde: Politiet</a>'
        f'</div>'
        for p in meldinger[:maks]
    )
    return (f'<div class="mn-police-box">'
            f'<div class="mn-police-hdr"><div class="mn-dot"></div>LIVE — OSLO POLITIDISTRIKT</div>'
            f'{items}'
            f'<p style="font-size:.58rem;color:#3a5a80;margin-top:.5rem;text-align:center">'
            f'<a href="{POLITIET_LINK}" target="_blank" style="color:#4a8fd4">'
            f'↗ Alle meldinger hos Politiloggen</a></p></div>')


# ════════════════════════════════════════════════════════════════
# MAIN  — rekkefølgen er kritisk for å unngå svart skjerm
# ════════════════════════════════════════════════════════════════
def main() -> None:

    # ── 1. Session state — ingen nettverkskall ───────────────
    for k, v in [("dark", False), ("manuell", []),
                 ("valgt", None), ("admin_inn", False)]:
        if k not in st.session_state:
            st.session_state[k] = v

    t = DARK if st.session_state.dark else LIGHT

    # ── 2. CSS injiseres umiddelbart — siden er nå hvit/mørk ─
    st.html(build_css(t))

    # ── 3. Sidebar — tegnes før API-kall ─────────────────────
    with st.sidebar:
        st.markdown(
            '<p style="font-family:\'Playfair Display\',serif;font-size:1.6rem;'
            'font-weight:900;color:#c8001e;margin:.1rem 0 0;letter-spacing:-.02em">'
            'MinOslo</p>'
            '<p style="font-size:.58rem;color:#555;margin:0 0 .3rem;'
            'letter-spacing:.1em;text-transform:uppercase">Ekte nyheter fra Oslo</p>',
            unsafe_allow_html=True)
        st.markdown("---")

        # Admin
        st.markdown('<p style="font-size:.6rem;font-weight:700;letter-spacing:.18em;'
                    'text-transform:uppercase;color:#c8001e;margin-bottom:.3rem">'
                    '🔒 Admin</p>', unsafe_allow_html=True)
        if not st.session_state.admin_inn:
            pw = st.text_input("Passord", type="password",
                               placeholder="Skriv passord…",
                               label_visibility="collapsed")
            if st.button("Logg inn", key="btn_login", use_container_width=True):
                if pw == ADMIN_PW:
                    st.session_state.admin_inn = True
                    st.rerun()
                elif pw:
                    st.markdown('<p style="color:#e8001f;font-size:.7rem">✗ Feil passord</p>',
                                unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#4caf50;font-size:.7rem">✓ Innlogget</p>',
                        unsafe_allow_html=True)
            with st.expander("➕ Legg til sak", expanded=False):
                with st.form("admin_form", clear_on_submit=True):
                    ny_t   = st.text_input("Tittel *")
                    ny_i   = st.text_area("Ingress *", height=60)
                    ny_b   = st.text_area("Brødtekst", height=80)
                    ny_bd  = st.selectbox("Bydel", BYDELER[1:])
                    ny_k   = st.selectbox("Kategori", KATEGORIER[1:])
                    ny_img = st.text_input("Bilde-URL (valgfritt)")
                    ny_src = st.text_input("Kilde-URL")
                    ny_sn  = st.text_input("Kilde-navn")
                    if st.form_submit_button("Publiser") and ny_t.strip() and ny_i.strip():
                        st.session_state.manuell.insert(0, {
                            "overskrift":ny_t.strip(),"ingress":ny_i.strip(),
                            "brodtekst":[l.strip() for l in ny_b.split("\n") if l.strip()],
                            "hva_skjer_videre":"","tags":[ny_bd,ny_k],
                            "kilde_url":ny_src.strip() or "#",
                            "kilde_navn":ny_sn.strip() or "Manuelt",
                            "bydel":ny_bd,"kategori":ny_k,
                            "publisert":datetime.now().strftime("%-d. %b %Y"),
                            "bilde_url":ny_img.strip(),
                        })
                        st.success("Publisert!")
                        st.rerun()
            if st.button("Logg ut", key="btn_logout", use_container_width=True):
                st.session_state.admin_inn = False
                st.rerun()

        st.markdown("---")
        dm_lbl = "☀️ Light Mode" if st.session_state.dark else "🌙 Dark Mode"
        if st.button(dm_lbl, key="btn_dm", use_container_width=True):
            st.session_state.dark = not st.session_state.dark
            st.rerun()

        st.markdown("---")
        st.markdown('<p style="font-size:.6rem;font-weight:700;letter-spacing:.15em;'
                    'text-transform:uppercase;color:#888;margin-bottom:.2rem">'
                    'Filtrer</p>', unsafe_allow_html=True)
        bydel_v = st.selectbox("Bydel", BYDELER,    label_visibility="collapsed", key="f_bd")
        kat_v   = st.selectbox("Kat",   KATEGORIER, label_visibility="collapsed", key="f_k")

        st.markdown("---")
        if st.button("🔄 Oppdater", key="btn_refresh", use_container_width=True):
            st.cache_data.clear()
            st.session_state.valgt = None
            st.rerun()

        st.markdown('<p style="font-size:.58rem;color:#444;line-height:1.6;margin-top:.5rem">'
                    'Live data fra Politiloggen og Oslo kommune.</p>',
                    unsafe_allow_html=True)

    # ── 4. Header tegnes — siden er nå synlig for brukeren ───
    dato = datetime.now().strftime("%-d. %B %Y")
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
        f'<span class="mn-nav-item">eInnsyn</span>'
        f'</nav>'
        f'</div></div>',
        unsafe_allow_html=True)

    st.markdown('<div class="mn-page">', unsafe_allow_html=True)

    # ── 5. Artikkelvisning (ingen API-kall nødvendig) ─────────
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
            st.markdown(f'<p class="mn-p">{avsnitt}</p>', unsafe_allow_html=True)
        if art.get("hva_skjer_videre"):
            st.markdown(f'<div class="mn-videre"><strong>Hva skjer videre:</strong> '
                        f'{art["hva_skjer_videre"]}</div>', unsafe_allow_html=True)
        st.markdown(tags_html(art), unsafe_allow_html=True)
        st.markdown(kilde_html(art, stor=True), unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # ── 6. API-kall skjer HER — etter at siden er synlig ─────
    #    st.spinner() holder UI responsivt mens data hentes
    with st.spinner("Henter ferske nyheter…"):
        politi_data, politi_feil   = hent_politilogg()
        oslo_data,   oslo_feil     = hent_oslo_rss()
        einnsyn_data, einnsyn_feil = hent_einnsyn()

    # ── 7. Bygg artikkel-liste ────────────────────────────────
    alle_art: list[dict] = []
    alle_art.extend(st.session_state.manuell)
    alle_art.extend(oslo_data)
    alle_art.extend(einnsyn_data)

    # Filtrer
    vis = list(alle_art)
    if bydel_v != "Alle bydeler":
        vis = [a for a in vis if a.get("bydel") == bydel_v]
    if kat_v != "Alle kategorier":
        vis = [a for a in vis if a.get("kategori") == kat_v]

    # ── 8. TABS (mobile-first: politilogg lett tilgjengelig) ──
    tab_nyheter, tab_politi = st.tabs(["📰 Nyheter", "🚔 Politilogg"])

    # ── Tab: Politilogg ───────────────────────────────────────
    with tab_politi:
        st.markdown('<div class="mn-label mn-label-red" style="margin-top:0">'
                    'Politilogg Live — Oslo</div>', unsafe_allow_html=True)
        if politi_feil:
            st.warning(f"Politiloggen er midlertidig utilgjengelig. ({politi_feil})")
            st.markdown(f'<a href="{POLITIET_LINK}" target="_blank" class="mn-source-link">'
                        f'↗ Se politiloggen direkte hos Politiet</a>',
                        unsafe_allow_html=True)
        elif politi_data:
            st.markdown(politi_boks(politi_data, maks=20), unsafe_allow_html=True)
        else:
            st.info("Ingen meldinger funnet for Oslo akkurat nå.")

    # ── Tab: Nyheter ──────────────────────────────────────────
    with tab_nyheter:
        col_news, col_police = st.columns([3, 1], gap="large")

        with col_news:
            if not vis:
                feil_mld = []
                if oslo_feil:    feil_mld.append(f"Oslo kommune: {oslo_feil}")
                if einnsyn_feil: feil_mld.append(f"eInnsyn: {einnsyn_feil}")
                st.markdown(
                    '<div style="text-align:center;padding:3rem 1rem;">'
                    '<div style="font-size:2rem;margin-bottom:.5rem">🔍</div>'
                    '<p style="font-size:1rem">Søker etter ferske nyheter fra Oslo…</p>'
                    '</div>', unsafe_allow_html=True)
                for m in feil_mld:
                    st.info(m)
            else:
                # Hero
                st.markdown('<div class="mn-label mn-label-red">Siste nytt</div>',
                            unsafe_allow_html=True)
                hero = vis[0]
                vis_media(hero, 300, alltid_bilde=True)
                st.markdown('<div class="mn-hero-body">', unsafe_allow_html=True)
                st.markdown(meta_html(hero), unsafe_allow_html=True)
                if st.button(hero["overskrift"], key="hero_btn"):
                    st.session_state.valgt = hero
                    st.rerun()
                st.markdown(f'<p class="mn-hero-ingress">{hero["ingress"]}</p>',
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
                        gruppe = resten[rad:rad+2]
                        cols   = st.columns(len(gruppe), gap="small")
                        for col, art in zip(cols, gruppe):
                            with col:
                                st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                                vis_media(art, 140)
                                st.markdown('<div class="mn-card-body">', unsafe_allow_html=True)
                                st.markdown(meta_html(art), unsafe_allow_html=True)
                                if st.button(art["overskrift"], key=f"card_{id(art)}"):
                                    st.session_state.valgt = art
                                    st.rerun()
                                ingress_kort = art["ingress"][:160]
                                if len(art["ingress"]) > 160:
                                    ingress_kort += "…"
                                st.markdown(f'<p class="mn-card-ingress">{ingress_kort}</p>',
                                            unsafe_allow_html=True)
                                st.markdown(kilde_html(art), unsafe_allow_html=True)
                                st.markdown("</div></div>", unsafe_allow_html=True)

        # Politilogg på desktop (høyre kolonne)
        with col_police:
            st.markdown('<div class="mn-label mn-label-red" style="margin-top:0">'
                        'Politilogg</div>', unsafe_allow_html=True)
            if politi_feil:
                st.markdown(
                    f'<div class="mn-police-box" style="text-align:center;padding:1.5rem;">'
                    f'<p style="color:#c8001e;font-size:.8rem">Utilgjengelig akkurat nå</p>'
                    f'<a href="{POLITIET_LINK}" target="_blank" style="color:#4a8fd4;font-size:.75rem">'
                    f'↗ Se politiloggen direkte</a></div>',
                    unsafe_allow_html=True)
            elif politi_data:
                st.markdown(
                    politi_boks(politi_data, maks=8).replace(
                        'class="mn-police-box"',
                        'class="mn-police-box mn-police-sticky"'),
                    unsafe_allow_html=True)

    # ── 9. Debug-panel (kun for admin) ───────────────────────
    if st.session_state.get("admin_inn"):
        with st.expander("🛠 Debug (kun synlig for admin)", expanded=False):
            st.caption(f"Kjøretid: {datetime.now().strftime('%H:%M:%S')} | "
                       f"timeout={HTTP_TIMEOUT}s")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**Politiloggen**")
                if politi_feil:
                    st.error(f"✗ {politi_feil}")
                    st.caption(f"URL: {POLITIET_URL}")
                else:
                    st.success(f"✓ {len(politi_data)} meldinger")
            with col2:
                st.markdown("**Oslo kommune RSS**")
                if oslo_feil:
                    st.error(f"✗ {oslo_feil}")
                    st.caption(f"URL-er prøvd: {OSLO_RSS_URLS}")
                else:
                    st.success(f"✓ {len(oslo_data)} saker")
            with col3:
                st.markdown("**eInnsyn**")
                if einnsyn_feil:
                    st.error(f"✗ {einnsyn_feil}")
                    st.caption(f"URL: {EINNSYN_URL}")
                else:
                    st.success(f"✓ {len(einnsyn_data)} saker")
            st.markdown("**HTTP Headers**")
            st.json(HTTP_HEADERS)

    st.markdown("</div>", unsafe_allow_html=True)   # mn-page


# ── Inngangspunkt — ingenting kjøres på modul-nivå over dette ──
if __name__ == "__main__":
    main()
