"""
MinOslo — Profesjonell nettavis
================================
Kjør:    streamlit run app.py
Krav:    pip install streamlit anthropic
Secrets: .streamlit/secrets.toml  →  ANTHROPIC_API_KEY = "sk-ant-..."
"""

import streamlit as st
import streamlit.components.v1 as components
import anthropic
import json
from datetime import datetime

st.set_page_config(
    page_title="MinOslo",
    page_icon="🗞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════
# TEMA  –  Light er standard
# ═══════════════════════════════════════════════════════════════
LIGHT = {
    "bg":           "#f2f2f0",
    "bg_card":      "#ffffff",
    "bg_sidebar":   "#1c1c1c",
    "bg_header":    "#ffffff",
    "bg_police":    "#12122a",
    "border":       "#e0ddd8",
    "text_primary": "#111111",
    "text_body":    "#2d2d2d",
    "text_soft":    "#666666",
    "text_muted":   "#999999",
    "text_police":  "#ddeeff",
    "accent":       "#c8001e",
    "accent2":      "#1a4f8a",
    "tag_bg":       "#f0eeeb",
    "tag_text":     "#555555",
    "meta_bg":      "#f5f3f0",
    "police_border":"#1e2d60",
    "police_item":  "#16213e",
    "toggle_bg":    "#333333",
    "toggle_text":  "#ffffff",
    "admin_bg":     "#1e1e1e",
    "admin_border": "#3a3a3a",
}
DARK = {
    "bg":           "#0d0d0d",
    "bg_card":      "#1a1a1a",
    "bg_sidebar":   "#0a0a0a",
    "bg_header":    "#111111",
    "bg_police":    "#090918",
    "border":       "#2e2e2e",
    "text_primary": "#f0f0f0",
    "text_body":    "#cccccc",
    "text_soft":    "#888888",
    "text_muted":   "#555555",
    "text_police":  "#c8e6fa",
    "accent":       "#e8001f",
    "accent2":      "#4a8fd4",
    "tag_bg":       "#252525",
    "tag_text":     "#aaaaaa",
    "meta_bg":      "#222222",
    "police_border":"#1e2d5e",
    "police_item":  "#101830",
    "toggle_bg":    "#e8e8e8",
    "toggle_text":  "#111111",
    "admin_bg":     "#111111",
    "admin_border": "#2a2a2a",
}

# ═══════════════════════════════════════════════════════════════
# UNSPLASH  –  dynamiske bilder basert på bydel + kategori
# ═══════════════════════════════════════════════════════════════
# source.unsplash.com/featured/?<keywords> henter et tilfeldig
# relevant bilde uten API-nøkkel. Kombinasjonen av bydel og
# kategori gir kontekstuelt riktige bilder for hver sak.

KAT_KEYWORDS = {
    "skjenkebevilling": "bar,pub,oslo",
    "byggesak":         "construction,architecture,building",
    "regulering":       "city,urban,park,oslo",
    "politisk vedtak":  "government,politics,city-hall",
    "politilogg":       "police,city,night",
    "annet":            "oslo,norway,city",
}
BYDEL_KEYWORDS = {
    "Grünerløkka":   "grunerlokka,oslo",
    "Frogner":        "frogner,oslo",
    "Sagene":         "sagene,oslo",
    "Gamle Oslo":     "oslo,waterfront",
    "Grorud":         "oslo,east",
    "St. Hanshaugen": "oslo,park",
    "Nordstrand":     "oslo,fjord",
    "Alna":           "oslo,suburb",
    "Bjerke":         "oslo,neighbourhood",
    "Nordre Aker":    "oslo,forest",
    "Stovner":        "oslo,apartment",
    "Søndre Nordstrand": "oslo,south",
    "Ullern":         "oslo,west",
    "Vestre Aker":    "oslo,villa",
    "Østensjø":       "oslo,lake",
}


def unsplash_url(art: dict, w: int = 900) -> str:
    """
    Bygger en source.unsplash.com URL med bydel- og kategori-stikkord.
    Returnerer alltid en gyldig URL — ingen API-nøkkel nødvendig.
    """
    bydel_kw = BYDEL_KEYWORDS.get(art.get("bydel", ""), "oslo")
    kat_kw   = KAT_KEYWORDS.get(art.get("kategori", "annet"), "oslo,city")
    keywords = f"{bydel_kw},{kat_kw}"
    return f"https://source.unsplash.com/featured/{w}x500/?{keywords}"


def bilde_url(art: dict, w: int = 900) -> str:
    """
    Fallback-kjede:
      1. Manuelt satt bilde_url i artikkelen
      2. Dynamisk Unsplash-URL basert på bydel + kategori
    Kartet brukes kun som siste nød-fallback i vis_media().
    """
    manuell = art.get("bilde_url", "").strip()
    return manuell if manuell else unsplash_url(art, w)


# ═══════════════════════════════════════════════════════════════
# CSS  –  bygges dynamisk fra temadict
# ═══════════════════════════════════════════════════════════════
def get_css(t: dict) -> str:
    return f"""
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
/* ── Reset ── */
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding: 0 !important; max-width: 100% !important; }}
html, body, .stApp {{ background-color: {t["bg"]} !important; font-family: 'Inter', sans-serif; }}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
  background: {t["bg_sidebar"]} !important;
  border-right: 1px solid #2a2a2a !important;
}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label {{
  color: #bbbbbb !important;
  font-size: 0.75rem !important;
}}
[data-testid="stSidebar"] .stSelectbox > div > div {{
  background: #2a2a2a !important;
  color: #eeeeee !important;
  border-color: #444 !important;
}}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stTextArea textarea {{
  background: #2a2a2a !important;
  color: #eeeeee !important;
  border-color: #444 !important;
  font-size: 0.85rem !important;
}}
[data-testid="stSidebar"] hr {{ border-color: #2e2e2e !important; }}

/* Sidebar-knapper: rød accent */
[data-testid="stSidebar"] .stButton > button {{
  background: {t["accent"]} !important;
  color: #ffffff !important;
  border: none !important;
  border-radius: 4px !important;
  font-weight: 700 !important;
  font-size: 0.75rem !important;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  width: 100%;
  padding: 0.6rem 1rem !important;
  margin-top: 0.2rem;
}}
[data-testid="stSidebar"] .stButton > button:hover {{ opacity: 0.85 !important; }}

/* ── Dark Mode toggle-knapp (synlig, kontrast mot mørk sidebar) ── */
.dm-toggle-btn {{
  display: block;
  width: 100%;
  background: {t["toggle_bg"]};
  color: {t["toggle_text"]};
  border: none;
  border-radius: 6px;
  padding: 0.55rem 0.9rem;
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  cursor: pointer;
  text-align: center;
  margin: 0.4rem 0;
}}

/* ── Admin-boks: alltid synlig i sidebar ── */
.admin-panel {{
  background: {t["admin_bg"]};
  border: 1px solid {t["admin_border"]};
  border-radius: 6px;
  padding: 0.9rem;
  margin-top: 0.5rem;
}}
.admin-panel-title {{
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: {t["accent"]};
  margin-bottom: 0.6rem;
}}

/* ── Header ── */
.mn-header {{
  background: {t["bg_header"]};
  border-bottom: 4px solid {t["accent"]};
  position: sticky; top: 0; z-index: 200;
}}
.mn-header-inner {{ max-width: 1400px; margin: 0 auto; padding: 0 1.5rem; }}
.mn-top {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 0.8rem 0 0.25rem;
}}
.mn-logo {{
  font-family: 'Playfair Display', serif;
  font-size: 2.2rem; font-weight: 900;
  color: {t["accent"]}; letter-spacing: -0.03em; line-height: 1;
}}
.mn-logo span {{ color: {t["text_primary"]}; }}
.mn-tagline {{ font-size: 0.62rem; color: {t["text_soft"]}; letter-spacing: 0.12em; text-transform: uppercase; }}
.mn-nav {{ display: flex; border-top: 1px solid {t["border"]}; }}
.mn-nav-item {{
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
  color: {t["text_soft"]}; padding: 0.55rem 1.1rem;
  border-bottom: 3px solid transparent; margin-bottom: -4px; white-space: nowrap;
}}
.mn-nav-item.active {{ color: {t["accent"]}; border-bottom-color: {t["accent"]}; }}

/* ── Page wrapper ── */
.mn-page {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem 1.5rem 5rem; }}

/* ── Section labels ── */
.mn-label {{
  font-size: 0.65rem; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase;
  color: {t["text_soft"]}; border-top: 2px solid {t["text_primary"]};
  padding-top: 0.45rem; margin: 1.8rem 0 1rem;
}}
.mn-label-red {{ border-top-color: {t["accent"]}; color: {t["accent"]}; }}

/* ── Hero ── */
.mn-hero {{
  border-radius: 6px; overflow: hidden;
  margin-bottom: 1.5rem; border: 1px solid {t["border"]};
}}
.mn-hero-img {{
  width: 100%; height: 400px; object-fit: cover;
  display: block; border-radius: 6px 6px 0 0;
}}
.mn-hero-body {{ padding: 1.4rem 1.8rem 1.8rem; background: {t["bg_card"]}; }}
.mn-hero-ingress {{
  font-size: 1rem; line-height: 1.68; color: {t["text_body"]};
  font-weight: 400; margin: 0.4rem 0 0.7rem; max-width: 75ch;
}}

/* ── Cards ── */
.mn-card {{
  background: {t["bg_card"]}; border: 1px solid {t["border"]};
  border-radius: 6px; overflow: hidden;
  margin-bottom: 1rem; display: flex; flex-direction: column;
}}
.mn-card-img {{ width: 100%; height: 155px; object-fit: cover; display: block; }}
.mn-card-body {{ padding: 0.9rem 1rem 1.1rem; flex: 1; }}
.mn-card-ingress {{
  font-size: 0.85rem; line-height: 1.6; color: {t["text_body"]}; font-weight: 400;
}}

/* ── Meta badges ── */
.mn-meta {{ display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.3rem; }}
.mn-badge {{
  font-size: 0.57rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
  background: {t["accent"]}; color: #fff; padding: 0.22em 0.55em; border-radius: 2px;
}}
.mn-badge-kat {{
  font-size: 0.57rem; font-weight: 600; background: {t["meta_bg"]};
  color: {t["text_soft"]}; padding: 0.22em 0.55em; border-radius: 2px;
  border: 1px solid {t["border"]};
}}
.mn-date {{ font-size: 0.67rem; color: {t["text_muted"]}; }}

/* ── Tags ── */
.mn-tags {{ display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.6rem; }}
.mn-tag {{
  font-size: 0.6rem; background: {t["tag_bg"]}; color: {t["tag_text"]};
  border: 1px solid {t["border"]}; padding: 0.18em 0.5em; border-radius: 20px;
}}

/* ── Politilogg ── */
.mn-police-box {{
  background: {t["bg_police"]}; border: 1px solid {t["police_border"]};
  border-radius: 6px; padding: 1rem; position: sticky; top: 80px;
}}
.mn-police-title {{
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.15em; text-transform: uppercase;
  color: {t["accent"]}; margin-bottom: 0.8rem;
  display: flex; align-items: center; gap: 0.4rem;
}}
.mn-police-dot {{
  width: 7px; height: 7px; background: {t["accent"]};
  border-radius: 50%; animation: blink 1.4s infinite;
}}
@keyframes blink {{ 0%,100% {{ opacity:1 }} 50% {{ opacity:0.15 }} }}
.mn-police-item {{
  background: {t["police_item"]}; border: 1px solid {t["police_border"]};
  border-radius: 4px; padding: 0.65rem 0.8rem; margin-bottom: 0.55rem;
}}
.mn-police-time {{ font-size: 0.62rem; color: {t["accent"]}; font-weight: 700; letter-spacing: 0.07em; margin-bottom: 0.2rem; }}
.mn-police-tekst {{ font-size: 0.82rem; color: {t["text_police"]}; line-height: 1.5; font-weight: 400; }}
.mn-police-sted {{ font-size: 0.64rem; color: #5a7fa8; margin-top: 0.2rem; }}

/* ── Artikkel fullvisning ── */
.mn-article-wrap {{
  background: {t["bg_card"]}; border: 1px solid {t["border"]};
  border-radius: 6px; padding: 2.5rem; margin-top: 1rem;
}}
.mn-article-wrap h1 {{
  font-family: 'Playfair Display', serif;
  font-size: clamp(1.8rem, 3vw, 2.8rem); font-weight: 900;
  line-height: 1.1; color: {t["text_primary"]}; margin-bottom: 1rem;
}}
.mn-ingress-full {{
  font-size: 1.1rem; line-height: 1.78; color: {t["text_body"]};
  font-weight: 400; border-left: 4px solid {t["accent"]};
  padding-left: 1.2rem; margin-bottom: 1.8rem;
}}
.mn-body-p {{ font-size: 1rem; line-height: 1.9; color: {t["text_body"]}; font-weight: 400; margin-bottom: 1rem; }}
.mn-videre {{
  background: {t["meta_bg"]}; border-left: 4px solid {t["accent2"]};
  padding: 0.85rem 1.2rem; margin: 1.5rem 0;
  border-radius: 0 4px 4px 0; font-size: 0.9rem; color: {t["text_body"]};
}}
.mn-kilde {{ font-size: 0.75rem; color: {t["text_soft"]}; margin-top: 1.5rem; padding-top: 0.9rem; border-top: 1px solid {t["border"]}; }}
.mn-kilde a {{ color: {t["accent"]}; text-decoration: none; }}

/* ── Streamlit-knapper (artikkelkort) ──
   Ingen z-index / overflow:hidden på wrapper — hindrer blokkering av klikk. ── */
.stButton > button {{
  background: transparent !important;
  color: {t["text_primary"]} !important;
  border: none !important; border-radius: 0 !important;
  font-family: 'Playfair Display', serif !important;
  font-size: 1.05rem !important; font-weight: 700 !important;
  text-align: left !important; padding: 0 !important;
  line-height: 1.25 !important; width: 100% !important;
  white-space: normal !important; height: auto !important;
  cursor: pointer !important;
}}
.stButton > button:hover {{ color: {t["accent"]} !important; }}
.stButton > button:focus {{ box-shadow: none !important; outline: none !important; }}

/* ── Kart-wrapper: aldri overflow:hidden eller z-index ── */
.mn-map-wrap {{ line-height: 0; }}
</style>
"""


# ═══════════════════════════════════════════════════════════════
# KART  –  components.html med eksplisitt height
# ═══════════════════════════════════════════════════════════════
BYDEL_COORDS: dict[str, tuple[float, float]] = {
    "Alna": (59.910, 10.850), "Bjerke": (59.935, 10.800),
    "Frogner": (59.920, 10.710), "Gamle Oslo": (59.905, 10.770),
    "Grorud": (59.955, 10.870), "Grünerløkka": (59.927, 10.760),
    "Nordre Aker": (59.960, 10.750), "Nordstrand": (59.875, 10.800),
    "Sagene": (59.938, 10.755), "St. Hanshaugen": (59.928, 10.735),
    "Stovner": (59.970, 10.920), "Søndre Nordstrand": (59.845, 10.820),
    "Ullern": (59.910, 10.650), "Vestre Aker": (59.950, 10.670),
    "Østensjø": (59.890, 10.830), "Hele Oslo": (59.914, 10.752),
}
_DEFAULT_COORD = (59.914, 10.752)


def vis_kart(bydel: str, h: int) -> None:
    """Rendrer OSM-kart via components.html — eneste API med ekte height-param."""
    lat, lon = BYDEL_COORDS.get(bydel, _DEFAULT_COORD)
    bbox = f"{lon-.03},{lat-.015},{lon+.03},{lat+.015}"
    html = (
        f'<!DOCTYPE html><html><body style="margin:0;overflow:hidden;">'
        f'<iframe src="https://www.openstreetmap.org/export/embed.html'
        f'?bbox={bbox}&layer=mapnik" '
        f'style="width:100%;height:{h}px;border:none;display:block;"'
        f' title="Kart over {bydel}"></iframe></body></html>'
    )
    components.html(html, height=h, scrolling=False)


def vis_media(art: dict, h: int, force_image: bool = False) -> None:
    """
    Viser bilde med denne prioriteringen:
      1. Manuelt satt bilde_url
      2. Dynamisk Unsplash-URL (bydel + kategori)
      3. OSM-kart som siste fallback (bare om force_image=False)
    force_image=True brukes for Hero — der vil vi alltid ha et bilde.
    """
    url = bilde_url(art, w=1100 if h > 300 else 800)
    if url:
        st.markdown(
            f'<div class="mn-map-wrap">'
            f'<img src="{url}" '
            f'style="width:100%;height:{h}px;object-fit:cover;display:block;'
            f'border-radius:6px 6px 0 0;" alt="" '
            f'onerror="this.style.display=\'none\'">'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif not force_image:
        vis_kart(art.get("bydel", "Hele Oslo"), h)


# ═══════════════════════════════════════════════════════════════
# DEMO-DATA  –  6 saker, mange fra Grünerløkka
# ═══════════════════════════════════════════════════════════════
DEMO_ARTIKLER = [
    {
        "overskrift": "Hele Grünerløkka-kvartalet rives — 120 nye leiligheter på vei",
        "ingress": "Plan- og bygningsetaten godkjente tirsdag rivingen av Thorvald Meyers gate 54–60. Den 100 år gamle bebyggelsen erstattes av et moderne leilighetsbygg med 120 enheter og næringslokaler i første etasje. Over 60 naboklager ble avvist.",
        "brodtekst": [
            "Vedtaket er blant de mest omstridte byggesakene på Grünerløkka på mange år. Leieboerforeningen mener kommunen ofrer levende bymiljø for utbyggerinteresser, mens utbygger Øst Eiendom AS hevder prosjektet vil tilføre 200 nye hjem til et marked med akutt boligmangel.",
            "Bygget er ikke listeført som verneverdig, men naboer argumenterer for at det inngår i et helhetlig kulturmiljø fra tidlig 1900-tall. Riksantikvaren ble konsultert, men konkluderte med at rivingen ikke strider mot nasjonale vernepolitiske mål.",
            "Beboerne som i dag leier i bygget har fått utflyttingsfrist til 1. oktober. Kommunen har bedt utbygger stille midlertidige boliger til rådighet, men juridisk er det ingen plikt til dette ved riving.",
            "Byggestart er planlagt januar 2026 med ferdigstillelse estimert til første kvartal 2028. Det nye bygget vil ha fire etasjer mer enn eksisterende bygg, noe som kaster skygge over tilstøtende bakgårder store deler av dagen.",
        ],
        "hva_skjer_videre": "Klagefrist til Statsforvalteren løper ut 2. juni — naboforeningen varsler klage.",
        "tags": ["riving", "Grünerløkka", "bolig", "naboprotester", "PBE"],
        "kilde_url": "https://innsyn.pbe.oslo.kommune.no",
        "kilde_navn": "Plan- og bygningsetaten",
        "bydel": "Grünerløkka",
        "kategori": "byggesak",
        "publisert": "12. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Tre barer på Løkka mister skjenkebevillingen",
        "ingress": "Oslo kommune trekker skjenkebevillingen fra Kafé Backstage, Bar Nordpolen og Pub 37 med umiddelbar virkning. Årsaken er gjentatte brudd på skjenketider og overskjenking dokumentert av natteravnene.",
        "brodtekst": [
            "Tilsynsmyndigheten gjennomførte tre uanmeldte kontroller mellom januar og april 2025. Ved alle anledningene ble det avdekket skjenking etter stengetid og gjester som åpenbart var overstadig beruset.",
            "Kafé Backstage reagerer med vantro og vil klage vedtaket inn for bystyrets klagenemnd. «Vi har hatt en ansvarlig skjenking i åtte år og dette er politisk motivert jakt på festlivet», sier daglig leder.",
            "Kommunens rusmiddeletat understreker at trekking av bevilling er siste utvei etter gjentatte advarsler skriftlig varslet etter første kontroll.",
            "Nabolaget er delt. Beboerforeningen i Olaf Ryes plass-kvartalet jubler, mens andre mener kommunen bør løse problemene med ekstra vakter fremfor stengning.",
        ],
        "hva_skjer_videre": "Klagenemnden behandler saken 18. juni — stedene holder stengt inntil videre.",
        "tags": ["skjenkebevilling", "Grünerløkka", "natteravnene", "bar"],
        "kilde_url": "https://oslo.kommune.no",
        "kilde_navn": "Oslo kommune",
        "bydel": "Grünerløkka",
        "kategori": "skjenkebevilling",
        "publisert": "11. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Sofienbergparken stenges hele sommeren for rehabilitering",
        "ingress": "Bymiljøetaten starter 1. juni full rehabilitering av Sofienbergparken. Gangveier, belysning og drenering fornyes. Parken gjenåpner 1. september, men deler er utilgjengelig i hele perioden.",
        "brodtekst": [
            "Prosjektet har en ramme på 28 millioner kroner og er finansiert gjennom kommunens grøntarealplan. Det er første gang siden 2003 at parken gjennomgår helhetlig rehabilitering.",
            "Støy fra anleggsarbeidet vil merkes på hverdager mellom 07.00 og 18.00. Treningsapparatene holdes tilgjengelige i en midlertidig sone gjennom hele sommeren.",
            "Hundelufteområdet i nordenden holdes åpent. Skateparken i sørenden stenger fra 15. juni til 20. august.",
            "Etter rehabiliteringen vil parken ha nytt LED-belysning, tre nye vannposter og en oppgradert lekeplass for barn fra 2 til 12 år.",
        ],
        "hva_skjer_videre": "Anleggsarbeidet starter 1. juni — parken gjenåpner offisielt 1. september.",
        "tags": ["park", "Grünerløkka", "Sofienbergparken", "rehabilitering"],
        "kilde_url": "https://oslo.kommune.no",
        "kilde_navn": "Oslo kommune / Bymiljøetaten",
        "bydel": "Grünerløkka",
        "kategori": "regulering",
        "publisert": "10. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Filipstad-planen vedtatt: 3 000 boliger og ny bystrand",
        "ingress": "Bystyret godkjente detaljreguleringsplanen for Filipstad med 52 mot 15 stemmer. Vedtaket åpner for 3 000 boliger, nytt bytorg og offentlig badestrand mellom Aker Brygge og Tjuvholmen.",
        "brodtekst": [
            "Filipstad er Oslos største byutviklingsprosjekt siden Bjørvika, estimert til over 12 milliarder kroner totalt. Byggestart er satt til 2027 med første innflytting i 2031.",
            "Beboere i Frogner bydel har protestert mot omfanget. De frykter økt trafikk, redusert sollys og press på eksisterende infrastruktur. 212 klager var innlevert til Plan- og bygningsetaten.",
            "Badestranden vil dekke 400 meter sjøfront og er dimensjonert for opp til 5 000 daglige besøkende i sommersesongen.",
            "Utbyggingen finansieres av privat kapital og kommunal infrastrukturinvestering på 2,8 milliarder kroner, der havnepromenaden dekkes av Oslo Havn KF.",
        ],
        "hva_skjer_videre": "Detaljprosjektering og arkitektkonkurranse lyses ut etter sommeren.",
        "tags": ["Filipstad", "bolig", "bystrand", "byutvikling", "Frogner"],
        "kilde_url": "https://pbe.oslo.kommune.no",
        "kilde_navn": "Plan- og bygningsetaten",
        "bydel": "Frogner",
        "kategori": "politisk vedtak",
        "publisert": "9. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Sagene skole fra 1898 rives — 420 elever flyttes til modulbygg",
        "ingress": "Utdanningsetaten bekrefter at Sagene skole rives etter at tilstandsrapport avdekket konstruksjonsfeil, fuktskader og asbest. 420 elever flyttes til midlertidige modulbygg fra høsten.",
        "brodtekst": [
            "Rehabiliteringskostnaden er estimert til 380 millioner — kun 20 millioner mindre enn nybygg. Kommunen velger riving og nybygg, ferdig til skolestart 2028.",
            "FAU-leder Tone Dahl er opprørt over informasjonsflyten: «Vi fikk vite om dette en uke før pressen. Det er ikke respekt for foreldre og elever.»",
            "Modulbyggene settes opp på skolens tomt. Utdanningsdirektøren garanterer at alle barn beholder sin nærskole og at modulene oppfyller alle krav til innemiljø og dagslys.",
            "Arkitektkonkurransen for det nye skolebygget lyses ut i september. Rivingstillatelse behandles av PBE i juni.",
        ],
        "hva_skjer_videre": "Modulbygg monteres august — rivingstillatelse i PBE juni.",
        "tags": ["skole", "Sagene", "riving", "utdanning"],
        "kilde_url": "https://oslo.kommune.no/skole-og-utdanning",
        "kilde_navn": "Oslo kommune / Utdanningsetaten",
        "bydel": "Sagene",
        "kategori": "politisk vedtak",
        "publisert": "8. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Nytt sykehjem på Nordstrand: 120 plasser og skjermet demensenhet",
        "ingress": "Sykehjemsetaten presenterer planer for 120 nye sykehjemsplasser på Ljanshøgda, inkludert skjermet avdeling for demens. Ventelisten i bydelen er i dag 80 personer med 14 måneders gjennomsnittlig ventetid.",
        "brodtekst": [
            "Det nye sykehjemmet bygges på kommunal tomt i Ljansbrukveien og er estimert til 680 millioner kroner. Bygget prosjekteres som passivhus med solceller og overvannsgjenbruk.",
            "Pårørendeforeningen er positive, men etterlyser bemanningsgarantier. «Nye rom er bra, men menneskene som steller gjør forskjellen», sier leder Kari Moen.",
            "Kommunen lover at bemanningsnormen følger Helsedirektoratets minstekrav og at 40 prosent av stillingene lyses ut som hele faste stillinger.",
            "Byggestart er planlagt til januar 2027. Sykehjemmet forventes ferdig til første kvartal 2029.",
        ],
        "hva_skjer_videre": "Byggesøknad sendes PBE august 2025 — byggestart januar 2027.",
        "tags": ["sykehjem", "Nordstrand", "eldreomsorg", "demens"],
        "kilde_url": "https://oslo.kommune.no/helse-og-omsorg",
        "kilde_navn": "Oslo kommune / Sykehjemsetaten",
        "bydel": "Nordstrand",
        "kategori": "politisk vedtak",
        "publisert": "7. mai 2025",
        "bilde_url": "",
    },
]

POLITILOGG = [
    {"tid": "07:42", "tekst": "Slagsmål utenfor nattklubb — to pågrepet.", "sted": "Grünerløkka · Thorvald Meyers gate"},
    {"tid": "06:15", "tekst": "Innbrudd i kiosk. Gjerningsperson ukjent.", "sted": "Sagene · Bentsebrugata"},
    {"tid": "04:50", "tekst": "Ordensforstyrrelser. Person bortvist.", "sted": "Grünerløkka · Olaf Ryes plass"},
    {"tid": "02:33", "tekst": "Trafikkulykke — MC og personbil. Én lettere skadet.", "sted": "Gamle Oslo · Schweigaards gate"},
    {"tid": "01:10", "tekst": "Sykkel stjålet fra låst stativ. Anmeldelse mottatt.", "sted": "St. Hanshaugen · Pilestredet"},
    {"tid": "00:05", "tekst": "Brannalarm — matlaging. Ingen fare.", "sted": "Frogner · Bygdøy allé"},
]

BYDELER = [
    "Alle bydeler", "Alna", "Bjerke", "Frogner", "Gamle Oslo", "Grorud",
    "Grünerløkka", "Nordre Aker", "Nordstrand", "Sagene", "St. Hanshaugen",
    "Stovner", "Søndre Nordstrand", "Ullern", "Vestre Aker", "Østensjø",
]
KAT_OPTIONS = {
    "Alle kategorier": None,
    "🏗️ Byggesak":        "byggesak",
    "🍺 Skjenkebevilling": "skjenkebevilling",
    "🗺️ Regulering":      "regulering",
    "🗳️ Politisk vedtak": "politisk vedtak",
    "📋 Annet":            "annet",
}
ADMIN_PW = "løkka2024"


# ═══════════════════════════════════════════════════════════════
# API  (brukes når du bytter fra DEMO til live-data)
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def hent_saker(bydel: str, antall: int = 6) -> list[dict]:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    bf = (f"Fokuser KUN på saker fra bydel {bydel}."
          if bydel != "Alle bydeler" else "Finn saker fra ulike bydeler i Oslo.")
    rs = f"""Du er nyhetsredaktør for MinOslo. Finn {antall} aktuelle Oslo-saker fra eInnsyn, oslo.kommune.no eller PBE.
{bf}
Returner KUN gyldig JSON:
{{"saker":[{{"tittel_raa":"...","kilde_url":"https://...","kilde_navn":"...","bydel":"...",
"kategori":"byggesak|skjenkebevilling|regulering|politisk vedtak|annet",
"sammendrag_raa":"2-3 setninger","bilde_url":""}}]}}"""
    js = """Du er lokaljournalist for MinOslo. Returner KUN gyldig JSON:
{"overskrift":"Maks 12 ord","ingress":"2-3 setninger",
"brodtekst":["avsnitt1","avsnitt2","avsnitt3","avsnitt4"],
"hva_skjer_videre":"1 setning","tags":["tag1","tag2","tag3"]}"""
    dato = datetime.now().strftime("%d. %B %Y")
    r1 = client.messages.create(
        model="claude-sonnet-4-5", max_tokens=2500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=rs,
        messages=[{"role": "user", "content":
            f"Finn {antall} Oslo-saker fra siste uken (i dag: {dato}). Søk einnsyn.no og oslo.kommune.no. KUN JSON."}],
    )
    raw = "".join(b.text for b in r1.content if hasattr(b, "text")).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    saker = json.loads(raw).get("saker", [])
    artikler = []
    for sak in saker:
        r2 = client.messages.create(
            model="claude-sonnet-4-5", max_tokens=1200, system=js,
            messages=[{"role": "user", "content":
                f"Rå tittel: {sak['tittel_raa']}\nBydel: {sak['bydel']}\n"
                f"Kategori: {sak['kategori']}\nKilde: {sak['kilde_navn']} ({sak['kilde_url']})\n"
                f"Sammendrag: {sak['sammendrag_raa']}\nKUN JSON."}],
        )
        txt = r2.content[0].text.strip()
        if txt.startswith("```"):
            txt = txt.split("\n", 1)[1].rsplit("```", 1)[0]
        art = json.loads(txt)
        art.update({"kilde_url": sak["kilde_url"], "kilde_navn": sak["kilde_navn"],
                    "bydel": sak["bydel"], "kategori": sak["kategori"],
                    "publisert": datetime.now().strftime("%-d. %b %Y"),
                    "bilde_url": sak.get("bilde_url", "")})
        artikler.append(art)
    return artikler


# ═══════════════════════════════════════════════════════════════
# UI-HJELPERE
# ═══════════════════════════════════════════════════════════════
def meta_html(art: dict) -> str:
    return (f'<div class="mn-meta">'
            f'<span class="mn-badge">{art["bydel"]}</span>'
            f'<span class="mn-badge-kat">{art["kategori"]}</span>'
            f'<span class="mn-date">{art.get("publisert","")}</span>'
            f'</div>')


def tags_html(art: dict) -> str:
    items = "".join(f'<span class="mn-tag">{x}</span>' for x in art.get("tags", []))
    return f'<div class="mn-tags">{items}</div>'


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main() -> None:
    # ── Session state ──
    defaults = {"dark_mode": False, "artikler": [], "valgt": None,
                "admin_logget_inn": False}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    t = DARK if st.session_state.dark_mode else LIGHT
    st.html(get_css(t))

    # ════════════════════════════════════════════
    # SIDEBAR
    # ════════════════════════════════════════════
    with st.sidebar:
        # Logo
        st.markdown(
            '<p style="font-family:\'Playfair Display\',serif;font-size:1.7rem;'
            'font-weight:900;color:#e8001f;margin:0.2rem 0 0;letter-spacing:-.02em">'
            'MinOslo</p>'
            '<p style="font-size:0.6rem;color:#666;margin:0 0 0.5rem;'
            'letter-spacing:.1em;text-transform:uppercase">Din Oslo-avis</p>',
            unsafe_allow_html=True)

        st.markdown("---")

        # ── DARK MODE  –  fremhevet som en tydelig knapp ──────────────
        modus_ikon  = "☀️" if st.session_state.dark_mode else "🌙"
        modus_tekst = "Bytt til Light Mode" if st.session_state.dark_mode else "Bytt til Dark Mode"
        # Bruk st.button (styleset i CSS til dm-toggle-btn via klassen)
        # Vi legger den i en form for å unngå rerun-loop
        if st.button(f"{modus_ikon}  {modus_tekst}", key="dm_toggle",
                     use_container_width=True):
            st.session_state.dark_mode = not st.session_state.dark_mode
            st.rerun()

        st.markdown("---")

        # ── Filtere ──
        st.markdown(
            '<p style="font-size:.62rem;font-weight:700;letter-spacing:.15em;'
            'text-transform:uppercase;color:#888;margin-bottom:.3rem">Filtrer</p>',
            unsafe_allow_html=True)
        bydel_valg = st.selectbox("Bydel", BYDELER,
                                  label_visibility="collapsed", key="sb_bydel")
        kat_valg   = st.selectbox("Kategori", list(KAT_OPTIONS.keys()),
                                  label_visibility="collapsed", key="sb_kat")

        st.markdown("---")
        if st.button("🔄  Hent nye saker fra AI", use_container_width=True):
            hent_saker.clear()
            st.session_state.valgt = None
            st.session_state.artikler = []
            st.rerun()

        st.markdown("---")

        # ── ADMIN-PANEL  –  alltid synlig, tydelig ramme ──────────────
        st.markdown(
            '<div style="background:#1a1a1a;border:1px solid #333;border-radius:6px;padding:.8rem .9rem;">'
            '<p style="font-size:.62rem;font-weight:700;letter-spacing:.18em;'
            'text-transform:uppercase;color:#e8001f;margin:0 0 .6rem">🔒 Admin-panel</p>',
            unsafe_allow_html=True)

        if not st.session_state.admin_logget_inn:
            pw = st.text_input("Passord", type="password",
                               placeholder="Skriv passord…",
                               label_visibility="collapsed")
            if st.button("Logg inn", use_container_width=True, key="admin_login"):
                if pw == ADMIN_PW:
                    st.session_state.admin_logget_inn = True
                    st.rerun()
                else:
                    st.markdown(
                        '<p style="color:#e8001f;font-size:.72rem;margin-top:.2rem">'
                        '✗ Feil passord</p>',
                        unsafe_allow_html=True)
        else:
            st.markdown(
                '<p style="color:#4caf50;font-size:.7rem;margin-bottom:.6rem">'
                '✓ Innlogget</p>',
                unsafe_allow_html=True)

            # Legg til ny sak
            st.markdown(
                '<p style="font-size:.65rem;font-weight:700;color:#aaa;'
                'margin-bottom:.3rem">Legg til ny sak</p>',
                unsafe_allow_html=True)
            with st.form("admin_form", clear_on_submit=True):
                ny_tittel    = st.text_input("Tittel *", placeholder="Overskrift…")
                ny_ingress   = st.text_area("Ingress *", height=70,
                                            placeholder="2–3 setninger…")
                ny_brodtekst = st.text_area("Brødtekst",  height=100,
                                            placeholder="Én setning/avsnitt per linje…")
                ny_bydel     = st.selectbox("Bydel", BYDELER[1:], key="admin_bydel")
                ny_kat_label = st.selectbox("Kategori",
                                            [k for k in KAT_OPTIONS if k != "Alle kategorier"],
                                            key="admin_kat")
                ny_bilde     = st.text_input("Bilde-URL (valgfritt)",
                                             placeholder="https://…")
                ny_kilde     = st.text_input("Kilde-URL (valgfritt)",
                                             placeholder="https://…")
                submitted = st.form_submit_button("➕  Publiser sak")
                if submitted:
                    if ny_tittel.strip() and ny_ingress.strip():
                        ny_art = {
                            "overskrift":    ny_tittel.strip(),
                            "ingress":       ny_ingress.strip(),
                            "brodtekst":     [l.strip() for l in ny_brodtekst.split("\n")
                                              if l.strip()],
                            "hva_skjer_videre": "",
                            "tags":          [ny_bydel,
                                              KAT_OPTIONS.get(ny_kat_label, "annet")],
                            "kilde_url":     ny_kilde.strip() or "#",
                            "kilde_navn":    "Manuelt lagt til",
                            "bydel":         ny_bydel,
                            "kategori":      KAT_OPTIONS.get(ny_kat_label, "annet"),
                            "publisert":     datetime.now().strftime("%-d. %b %Y"),
                            "bilde_url":     ny_bilde.strip(),
                        }
                        if not st.session_state.artikler:
                            st.session_state.artikler = list(DEMO_ARTIKLER)
                        st.session_state.artikler.insert(0, ny_art)
                        st.success("Sak publisert!")
                        st.rerun()
                    else:
                        st.error("Tittel og ingress er påkrevd.")

            if st.button("Logg ut", use_container_width=True, key="admin_logout"):
                st.session_state.admin_logget_inn = False
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)   # admin-boks

        st.markdown(
            '<p style="font-size:.6rem;color:#444;line-height:1.6;margin-top:.8rem">'
            'Artikler genereres av AI basert på offentlige kilder.</p>',
            unsafe_allow_html=True)

    # ════════════════════════════════════════════
    # HEADER
    # ════════════════════════════════════════════
    nav_items = ["Nyheter", "Byggesaker", "Skjenking", "Politilogg"]
    nav_html  = "".join(
        f'<span class="mn-nav-item{"  active" if i == 0 else ""}">{x}</span>'
        for i, x in enumerate(nav_items)
    )
    dato_str = datetime.now().strftime("%-d. %B %Y")
    st.markdown(
        f'<div class="mn-header"><div class="mn-header-inner">'
        f'<div class="mn-top">'
        f'<div class="mn-logo">Min<span>Oslo</span></div>'
        f'<div class="mn-tagline">Oslo · {dato_str}</div>'
        f'</div>'
        f'<nav class="mn-nav">{nav_html}</nav>'
        f'</div></div>',
        unsafe_allow_html=True)

    st.markdown('<div class="mn-page">', unsafe_allow_html=True)

    # ── Last saker ──
    if not st.session_state.artikler:
        st.session_state.artikler = list(DEMO_ARTIKLER)
        # Bytt til live-data ved å fjerne kommentaren under:
        # with st.spinner("Henter saker…"):
        #     st.session_state.artikler = hent_saker(bydel_valg)

    # ── Filtrer ──
    kat_filter = KAT_OPTIONS.get(kat_valg)
    alle = list(st.session_state.artikler)
    if bydel_valg != "Alle bydeler":
        alle = [a for a in alle if a.get("bydel") == bydel_valg]
    if kat_filter:
        alle = [a for a in alle if a.get("kategori") == kat_filter]

    # ════════════════════════════════════════════
    # ARTIKKELVISNING (full bredde)
    # ════════════════════════════════════════════
    if st.session_state.valgt:
        art = st.session_state.valgt
        if st.button("← Tilbake til forsiden"):
            st.session_state.valgt = None
            st.rerun()

        # Artikkel-hero: alltid bilde (Unsplash-fallback, aldri kart)
        vis_media(art, 420, force_image=True)

        st.markdown('<div class="mn-article-wrap">', unsafe_allow_html=True)
        st.markdown(meta_html(art), unsafe_allow_html=True)
        st.markdown(f'<h1>{art["overskrift"]}</h1>', unsafe_allow_html=True)
        st.markdown(f'<div class="mn-ingress-full">{art["ingress"]}</div>',
                    unsafe_allow_html=True)
        for avsnitt in art.get("brodtekst", []):
            st.markdown(f'<p class="mn-body-p">{avsnitt}</p>', unsafe_allow_html=True)
        if art.get("hva_skjer_videre"):
            st.markdown(
                f'<div class="mn-videre"><strong>Hva skjer videre:</strong> '
                f'{art["hva_skjer_videre"]}</div>',
                unsafe_allow_html=True)
        st.markdown(tags_html(art), unsafe_allow_html=True)
        st.markdown(
            f'<div class="mn-kilde">Kilde: '
            f'<a href="{art["kilde_url"]}" target="_blank">{art["kilde_navn"]}</a></div>',
            unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ════════════════════════════════════════════
    # FORSIDE: nyheter (3/4) + politilogg (1/4)
    # ════════════════════════════════════════════
    if not alle:
        st.markdown(
            f'<div style="text-align:center;padding:5rem 2rem;color:{t["text_soft"]}">'
            '<h3 style="font-family:\'Playfair Display\',serif;font-style:italic">'
            'Ingen saker funnet</h3><p>Prøv en annen bydel eller kategori.</p></div>',
            unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    col_news, col_police = st.columns([3, 1], gap="large")

    # ── Nyhetsspalte ──
    with col_news:
        st.markdown('<div class="mn-label mn-label-red">Hovedsak</div>',
                    unsafe_allow_html=True)
        hero = alle[0]

        # Hero-bilde: ALLTID Unsplash (force_image=True → aldri kart)
        vis_media(hero, 400, force_image=True)

        st.markdown('<div class="mn-hero-body">', unsafe_allow_html=True)
        st.markdown(meta_html(hero), unsafe_allow_html=True)
        if st.button(hero["overskrift"], key="hero_btn"):
            st.session_state.valgt = hero
            st.rerun()
        st.markdown(
            f'<p class="mn-hero-ingress">{hero["ingress"]}</p>',
            unsafe_allow_html=True)
        st.markdown(tags_html(hero), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)   # hero-body

        # Grid — resten av sakene
        resten = alle[1:]
        if resten:
            st.markdown('<div class="mn-label">Flere saker</div>',
                        unsafe_allow_html=True)
            for rad_start in range(0, len(resten), 3):
                rad  = resten[rad_start:rad_start + 3]
                cols = st.columns(len(rad), gap="small")
                for col, art in zip(cols, rad):
                    with col:
                        st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                        vis_media(art, 155)    # Unsplash eller kart-fallback
                        st.markdown('<div class="mn-card-body">', unsafe_allow_html=True)
                        st.markdown(meta_html(art), unsafe_allow_html=True)
                        idx = st.session_state.artikler.index(art)
                        if st.button(art["overskrift"], key=f"card_{idx}"):
                            st.session_state.valgt = art
                            st.rerun()
                        st.markdown(
                            f'<p class="mn-card-ingress">{art["ingress"]}</p>',
                            unsafe_allow_html=True)
                        st.markdown(tags_html(art), unsafe_allow_html=True)
                        st.markdown("</div></div>", unsafe_allow_html=True)

    # ── Politilogg-spalte ──
    with col_police:
        st.markdown('<div class="mn-label mn-label-red" style="margin-top:0">Politilogg</div>',
                    unsafe_allow_html=True)
        items_html = "".join(
            f'<div class="mn-police-item">'
            f'<div class="mn-police-time">🚔 {p["tid"]}</div>'
            f'<div class="mn-police-tekst">{p["tekst"]}</div>'
            f'<div class="mn-police-sted">📍 {p["sted"]}</div>'
            f'</div>'
            for p in POLITILOGG
        )
        st.markdown(
            f'<div class="mn-police-box">'
            f'<div class="mn-police-title">'
            f'<div class="mn-police-dot"></div>LIVE — SISTE 12 TIMER</div>'
            f'{items_html}'
            f'<p style="font-size:.6rem;color:#3a5a80;margin-top:.5rem;text-align:center">'
            f'Kilde: Oslo politidistrikt (demo)</p>'
            f'</div>',
            unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)   # mn-page


if __name__ == "__main__":
    main()
