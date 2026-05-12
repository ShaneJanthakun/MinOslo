"""
MinOslo — Profesjonell nettavis
================================
Kjør: streamlit run app.py
Krav: pip install streamlit anthropic
Secrets (.streamlit/secrets.toml): ANTHROPIC_API_KEY = "sk-ant-..."
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

# ═════════════════════════════════════════════════════════════════════════════
# TEMA
# ═════════════════════════════════════════════════════════════════════════════
LIGHT = {
    "bg":            "#f2f2f0",
    "bg_card":       "#ffffff",
    "bg_sidebar":    "#1a1a1a",
    "bg_header":     "#ffffff",
    "bg_police":     "#1a1a2e",
    "border":        "#e0ddd8",
    "text_primary":  "#111111",
    "text_body":     "#2d2d2d",
    "text_soft":     "#666666",
    "text_muted":    "#999999",
    "text_police":   "#e8f4fd",
    "accent":        "#c8001e",
    "accent2":       "#1a4f8a",
    "tag_bg":        "#f0eeeb",
    "tag_text":      "#555555",
    "meta_bg":       "#f5f3f0",
    "police_border": "#2a3a6e",
    "police_item":   "#16213e",
    "input_bg":      "#ffffff",
    "input_text":    "#111111",
    "hero_overlay":  "rgba(0,0,0,0.45)",
}

DARK = {
    "bg":            "#0d0d0d",
    "bg_card":       "#1a1a1a",
    "bg_sidebar":    "#0a0a0a",
    "bg_header":     "#111111",
    "bg_police":     "#0a0a1e",
    "border":        "#2e2e2e",
    "text_primary":  "#f0f0f0",
    "text_body":     "#cccccc",
    "text_soft":     "#888888",
    "text_muted":    "#555555",
    "text_police":   "#c8e6fa",
    "accent":        "#e8001f",
    "accent2":       "#4a8fd4",
    "tag_bg":        "#252525",
    "tag_text":      "#aaaaaa",
    "meta_bg":       "#222222",
    "police_border": "#1e2d5e",
    "police_item":   "#101830",
    "input_bg":      "#222222",
    "input_text":    "#f0f0f0",
    "hero_overlay":  "rgba(0,0,0,0.55)",
}

KAT_ILLUSTRASJONER = {
    "skjenkebevilling": "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?w=800&q=80",
    "byggesak":         "https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=800&q=80",
    "regulering":       "https://images.unsplash.com/photo-1476231682828-37e571bc172f?w=800&q=80",
    "politisk vedtak":  "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=800&q=80",
    "politilogg":       "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=800&q=80",
    "annet":            "https://images.unsplash.com/photo-1486325212027-8081e485255e?w=800&q=80",
}


def get_css(t: dict) -> str:
    return f"""
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
/* ── Reset ── */
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding: 0 !important; max-width: 100% !important; }}
html, body, .stApp {{ background-color: {t["bg"]} !important; font-family: 'Inter', sans-serif; }}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{ background: {t["bg_sidebar"]} !important; border-right: 1px solid #222 !important; }}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown span {{ color: #aaaaaa !important; font-size: 0.72rem !important; letter-spacing: 0.06em; }}
[data-testid="stSidebar"] .stSelectbox > div > div {{ background: #222 !important; color: #eee !important; border-color: #444 !important; }}
[data-testid="stSidebar"] .stTextInput input {{ background: {t["input_bg"]} !important; color: {t["input_text"]} !important; border-color: #444 !important; }}
[data-testid="stSidebar"] .stTextArea textarea {{ background: #222 !important; color: #eee !important; border-color: #444 !important; }}
[data-testid="stSidebar"] hr {{ border-color: #2a2a2a !important; margin: 0.8rem 0 !important; }}
[data-testid="stSidebar"] .stButton > button {{
    background: {t["accent"]} !important; color: #fff !important;
    border: none !important; border-radius: 3px !important;
    font-weight: 700 !important; font-size: 0.75rem !important;
    letter-spacing: 0.08em; text-transform: uppercase;
    width: 100%; padding: 0.55rem 1rem !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{ opacity: 0.88 !important; }}

/* ── Header ── */
.mn-header {{
    background: {t["bg_header"]};
    border-bottom: 4px solid {t["accent"]};
    padding: 0;
    position: sticky; top: 0; z-index: 100;
}}
.mn-header-inner {{ max-width: 1400px; margin: 0 auto; padding: 0 1.5rem; }}
.mn-top {{ display: flex; align-items: baseline; justify-content: space-between; padding: 0.9rem 0 0.3rem; }}
.mn-logo {{
    font-family: 'Playfair Display', serif;
    font-size: 2.2rem; font-weight: 900;
    color: {t["accent"]}; letter-spacing: -0.03em; line-height: 1;
}}
.mn-logo span {{ color: {t["text_primary"]}; }}
.mn-tagline {{ font-size: 0.65rem; color: {t["text_soft"]}; letter-spacing: 0.12em; text-transform: uppercase; }}
.mn-nav {{ display: flex; border-top: 1px solid {t["border"]}; }}
.mn-nav-item {{
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
    color: {t["text_soft"]}; padding: 0.6rem 1.1rem; border-bottom: 3px solid transparent;
    margin-bottom: -4px; white-space: nowrap;
}}
.mn-nav-item.active {{ color: {t["accent"]}; border-bottom-color: {t["accent"]}; }}

/* ── Page ── */
.mn-page {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem 1.5rem 5rem; }}

/* ── Section label ── */
.mn-label {{
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase;
    color: {t["text_soft"]}; border-top: 2px solid {t["text_primary"]};
    padding-top: 0.45rem; margin: 1.8rem 0 1rem;
}}
.mn-label-red {{ border-top-color: {t["accent"]}; color: {t["accent"]}; }}

/* ── Hero ── */
.mn-hero {{
    position: relative; border-radius: 6px; overflow: hidden;
    margin-bottom: 1.5rem; cursor: pointer;
    border: 1px solid {t["border"]};
}}
.mn-hero-img {{
    width: 100%; height: 380px; object-fit: cover; display: block;
}}
.mn-hero-overlay {{
    position: absolute; bottom: 0; left: 0; right: 0;
    background: linear-gradient(transparent 0%, {t["hero_overlay"]} 100%);
    padding: 3rem 2rem 1.8rem;
}}
.mn-hero-title {{
    font-family: 'Playfair Display', serif;
    font-size: clamp(1.6rem, 2.8vw, 2.5rem);
    font-weight: 900; line-height: 1.1; color: #ffffff;
    margin: 0.4rem 0 0.7rem; text-shadow: 0 2px 8px rgba(0,0,0,0.6);
}}
.mn-hero-ingress {{
    font-size: 1rem; line-height: 1.6; color: rgba(255,255,255,0.90);
    font-weight: 400; max-width: 72ch;
}}

/* ── Cards ── */
.mn-card {{
    background: {t["bg_card"]}; border: 1px solid {t["border"]};
    border-radius: 6px; overflow: hidden; margin-bottom: 1rem;
    display: flex; flex-direction: column;
}}
.mn-card-img {{ width: 100%; height: 155px; object-fit: cover; display: block; }}
.mn-card-body {{ padding: 1rem 1.1rem 1.2rem; flex: 1; }}
.mn-card-title {{
    font-family: 'Playfair Display', serif;
    font-size: 1.05rem; font-weight: 700; line-height: 1.25;
    color: {t["text_primary"]}; margin: 0.4rem 0 0.5rem;
}}
.mn-card-ingress {{ font-size: 0.86rem; line-height: 1.6; color: {t["text_body"]}; font-weight: 400; }}

/* ── Meta ── */
.mn-meta {{ display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.3rem; }}
.mn-badge {{
    font-size: 0.58rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    background: {t["accent"]}; color: #fff; padding: 0.22em 0.55em; border-radius: 2px;
}}
.mn-badge-kat {{
    font-size: 0.58rem; font-weight: 600; background: {t["meta_bg"]};
    color: {t["text_soft"]}; padding: 0.22em 0.55em; border-radius: 2px;
    border: 1px solid {t["border"]};
}}
.mn-date {{ font-size: 0.68rem; color: {t["text_muted"]}; }}

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
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.15em;
    text-transform: uppercase; color: {t["accent"]}; margin-bottom: 0.8rem;
    display: flex; align-items: center; gap: 0.4rem;
}}
.mn-police-dot {{
    width: 7px; height: 7px; background: {t["accent"]}; border-radius: 50%;
    animation: blink 1.4s infinite;
}}
@keyframes blink {{ 0%,100% {{ opacity:1 }} 50% {{ opacity:0.2 }} }}
.mn-police-item {{
    background: {t["police_item"]}; border: 1px solid {t["police_border"]};
    border-radius: 4px; padding: 0.7rem 0.85rem; margin-bottom: 0.6rem;
}}
.mn-police-time {{ font-size: 0.62rem; color: {t["accent"]}; font-weight: 700; letter-spacing: 0.08em; margin-bottom: 0.25rem; }}
.mn-police-tekst {{ font-size: 0.82rem; color: {t["text_police"]}; line-height: 1.5; font-weight: 400; }}
.mn-police-sted {{ font-size: 0.65rem; color: #6a8ab0; margin-top: 0.25rem; }}

/* ── Filter-bar ── */
.mn-filter-bar {{
    background: {t["bg_card"]}; border: 1px solid {t["border"]};
    border-radius: 6px; padding: 0.75rem 1rem;
    display: flex; align-items: center; gap: 1rem;
    margin-bottom: 1.2rem; flex-wrap: wrap;
}}
.mn-filter-label {{ font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: {t["text_soft"]}; }}

/* ── Artikkel fullvisning ── */
.mn-article-wrap {{ background: {t["bg_card"]}; border: 1px solid {t["border"]}; border-radius: 6px; padding: 2.5rem; margin-top: 1rem; }}
.mn-article-wrap h1 {{
    font-family: 'Playfair Display', serif;
    font-size: clamp(1.8rem, 3vw, 2.8rem); font-weight: 900;
    line-height: 1.1; color: {t["text_primary"]}; margin-bottom: 1rem;
}}
.mn-ingress-full {{
    font-size: 1.12rem; line-height: 1.75; color: {t["text_body"]};
    font-weight: 400; border-left: 4px solid {t["accent"]};
    padding-left: 1.2rem; margin-bottom: 1.8rem;
}}
.mn-body-p {{ font-size: 1rem; line-height: 1.9; color: {t["text_body"]}; font-weight: 400; margin-bottom: 1rem; }}
.mn-videre {{
    background: {t["meta_bg"]}; border-left: 4px solid {t["accent2"]};
    padding: 0.9rem 1.2rem; margin: 1.5rem 0; border-radius: 0 4px 4px 0;
    font-size: 0.92rem; color: {t["text_body"]};
}}
.mn-kilde {{ font-size: 0.75rem; color: {t["text_soft"]}; margin-top: 1.5rem; padding-top: 0.9rem; border-top: 1px solid {t["border"]}; }}
.mn-kilde a {{ color: {t["accent"]}; text-decoration: none; }}

/* ── Admin-skjema ── */
.admin-box {{
    background: #1a1a1a; border: 1px solid #333;
    border-radius: 6px; padding: 1rem; margin-top: 0.5rem;
}}
.admin-box .stTextInput input, .admin-box .stTextArea textarea {{
    background: #2a2a2a !important; color: #f0f0f0 !important;
    border-color: #444 !important; font-size: 0.85rem !important;
}}

/* ── Streamlit-knapper (artikkelkort og hero) ──
   Ingen z-index, ingen overflow:hidden på wrappers — dette var
   rotårsaken til at knapper ble blokkert av kart-iframen. ── */
.stButton > button {{
    background: transparent !important; color: {t["text_primary"]} !important;
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

/* ── Kart-wrapper: ALDRI overflow:hidden eller z-index her ── */
.mn-map-wrap {{ line-height: 0; border-radius: 6px 6px 0 0; }}
</style>
"""


# ═════════════════════════════════════════════════════════════════════════════
# KART  (components.html med eksplisitt height — eneste som garanterer visning)
# ═════════════════════════════════════════════════════════════════════════════
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
_D = (59.914, 10.752)


def vis_kart(bydel: str, h: int) -> None:
    lat, lon = BYDEL_COORDS.get(bydel, _D)
    bbox = f"{lon-.03},{lat-.015},{lon+.03},{lat+.015}"
    html = (f'<!DOCTYPE html><html><body style="margin:0;overflow:hidden;">'
            f'<iframe src="https://www.openstreetmap.org/export/embed.html'
            f'?bbox={bbox}&layer=mapnik" '
            f'style="width:100%;height:{h}px;border:none;display:block;" '
            f'title="Kart over {bydel}"></iframe></body></html>')
    components.html(html, height=h, scrolling=False)


def vis_media(art: dict, h: int) -> None:
    """Bilde → kategori-illustrasjon → OSM-kart (fallback-kjede)."""
    url = art.get("bilde_url", "").strip()
    if not url:
        url = KAT_ILLUSTRASJONER.get(art.get("kategori", ""), "")
    if url:
        st.markdown(
            f'<div class="mn-map-wrap">'
            f'<img src="{url}" style="width:100%;height:{h}px;'
            f'object-fit:cover;display:block;" alt=""></div>',
            unsafe_allow_html=True,
        )
    else:
        vis_kart(art.get("bydel", "Hele Oslo"), h)


# ═════════════════════════════════════════════════════════════════════════════
# DEMO-DATA
# ═════════════════════════════════════════════════════════════════════════════
DEMO_ARTIKLER = [
    {
        "overskrift": "Hele Grünerløkka-blokka rives for å gi plass til 120 nye leiligheter",
        "ingress": "Plan- og bygningsetaten godkjente tirsdag rivingen av Thorvald Meyers gate 54–60. Den 100 år gamle kvartalsbebyggelsen erstattes av et moderne leilighetsbygg med 120 enheter og næringslokaler i første etasje. Over 60 naboklager ble avvist.",
        "brodtekst": [
            "Vedtaket er blant de mest omstridte byggesakene på Grünerløkka på mange år. Leieboerforeningen mener kommunen ofrer levende bymiljø for utbyggerinteresser, mens utbygger Øst Eiendom AS hevder prosjektet vil tilføre 200 nye hjem til et marked med akutt boligmangel.",
            "Bygget er ikke listeført som verneverdig, men naboer argumenterer for at det inngår i et helhetlig kulturmiljø fra tidlig 1900-tall som bør bevares. Riksantikvaren ble konsultert, men konkluderte med at rivingen ikke strider mot nasjonale vernepolitiske mål.",
            "Beboerne som i dag leier i bygget, har fått utflyttingsfrist til 1. oktober. Kommunen har bedt utbygger stille midlertidige boliger til rådighet, men juridisk er det ingen plikt til dette ved riving.",
            "Byggestart er planlagt januar 2026. Ferdigstillelse estimeres til første kvartal 2028. Det nye bygget vil ha fire etasjer mer enn det eksisterende, noe som vil kaste skygge over bakgårdene til tilstøtende eiendommer store deler av dagen.",
        ],
        "hva_skjer_videre": "Klagefrist til Statsforvalteren løper ut 2. juni — naboforeningen varsler klage.",
        "tags": ["riving", "Grünerløkka", "bolig", "naboprotester", "PBE"],
        "kilde_url": "https://innsyn.pbe.oslo.kommune.no",
        "kilde_navn": "Plan- og bygningsetaten",
        "bydel": "Grünerløkka",
        "kategori": "byggesak",
        "publisert": "12. mai 2025",
        "bilde_url": "https://images.unsplash.com/photo-1486325212027-8081e485255e?w=1200&q=85",
    },
    {
        "overskrift": "Tre barer på Løkka mister skjenkebevillingen etter natteravnrapporter",
        "ingress": "Oslo kommune trekker skjenkebevillingen fra Kafé Backstage, Bar Nordpolen og Pub 37 på Grünerløkka med umiddelbar virkning. Årsaken er gjentatte brudd på skjenketider og tilfeller av overskjenking dokumentert av natteravnene.",
        "brodtekst": [
            "Tilsynsmyndigheten gjennomførte tre uanmeldte kontroller mellom januar og april 2025. Ved alle tre anledningene ble det avdekket skjenking etter stengetid og gjester som åpenbart var påvirket over det lovlige nivået.",
            "Kafé Backstage reagerer med vantro og vil klage vedtaket inn for bystyrets klagenemnd. «Vi har hatt en ansvarlig skjenking i åtte år og dette er politisk motivert jakt på festlivet på Løkka», sier daglig leder Petter Vik.",
            "Kommunens rusmiddeletat understreker at trekking av bevilling er siste utvei etter gjentatte advarsler, og at de tre stedene fikk skriftlige varsler etter første kontroll.",
            "Nabolaget er delt. Beboerforeningen i Olaf Ryes plass-kvartalet jubler, mens andre fastboende mener kommunen overdramatiserer problemer som heller bør løses med ekstra vakter og tidligere stengetid.",
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
        "ingress": "Bymiljøetaten starter 1. juni full rehabilitering av Sofienbergparken på Grünerløkka. Gangveier, belysning og drenering fornyes. Parken gjenåpner 1. september, men deler av arealet vil være utilgjengelig i hele perioden.",
        "brodtekst": [
            "Prosjektet har en ramme på 28 millioner kroner og er finansiert gjennom kommunens grøntarealplan. Det er første gang siden 2003 at parken gjennomgår en helhetlig rehabilitering.",
            "Støy fra anleggsarbeidet vil merkes i nabolaget, særlig på hverdager mellom 07.00 og 18.00. Bymiljøetaten lover å ta hensyn til brukere av parken og bevare treningsapparatene tilgjengelig i en midlertidig sone.",
            "Hundelufteområdet i nordenden vil holdes åpent gjennom hele sommeren. Skateparken i sørenden stenger fra 15. juni til 20. august.",
            "Etter rehabiliteringen vil parken ha nytt LED-belysning, tre nye vannposter, og en oppgradert lekeplass tilpasset barn fra 2 til 12 år.",
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
        "ingress": "Bystyret godkjente tirsdag detaljreguleringsplanen for Filipstad med 52 mot 15 stemmer. Vedtaket åpner for 3 000 nye boliger, et nytt bytorg og en offentlig badestrand mellom Aker Brygge og Tjuvholmen.",
        "brodtekst": [
            "Filipstad er Oslos største byutviklingsprosjekt siden Bjørvika og er estimert til å koste over 12 milliarder kroner totalt. Byggestart er satt til 2027 med første innflytting i 2031.",
            "Beboere i Frogner bydel har protestert mot prosjektets omfang. De frykter økt trafikk, redusert sollys og press på eksisterende infrastruktur. 212 klager var innlevert til Plan- og bygningsetaten.",
            "Badestranden vil dekke 400 meter sjøfront og er dimensjonert for opp til 5 000 daglige besøkende i sommersesongen.",
            "Utbyggingen finansieres av en kombinasjon av privat kapital og kommunal infrastrukturinvestering på 2,8 milliarder, der havnepromenaden og den nye badestranden dekkes av Oslo Havn KF.",
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
        "overskrift": "Sagene skole fra 1898 rives — 420 elever til modulbygg",
        "ingress": "Utdanningsetaten bekrefter at Sagene skole skal rives etter at tilstandsrapport avdekket alvorlige konstruksjonsfeil, fuktskader og asbest. 420 elever flyttes til midlertidige modulbygg fra høsten.",
        "brodtekst": [
            "Rehabiliteringskostnaden er estimert til 380 millioner kroner — kun 20 millioner mindre enn et nybygg. Kommunen har valgt riving og nybygg, som vil stå ferdig til skolestart 2028.",
            "FAU-leder Tone Dahl er opprørt over informasjonsflyten. «Vi fikk vite om dette en uke før pressen. Det er ikke respekt for foreldre og elever», sier hun.",
            "Modulbyggene settes opp på skolens egen tomt. Utdanningsdirektøren garanterer at alle barn beholder sin nærskole og at modulbyggene oppfyller alle krav til innemiljø og dagslys.",
            "Arkitektkonkurransen for det nye skolebygget lyses ut i september. Rivingstillatelse behandles av Plan- og bygningsetaten i juni.",
        ],
        "hva_skjer_videre": "Modulbygg monteres august — rivingstillatelse behandles i PBE juni.",
        "tags": ["skole", "Sagene", "riving", "utdanning"],
        "kilde_url": "https://oslo.kommune.no/skole-og-utdanning",
        "kilde_navn": "Oslo kommune / Utdanningsetaten",
        "bydel": "Sagene",
        "kategori": "politisk vedtak",
        "publisert": "8. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Nytt sykehjem på Nordstrand: 120 plasser og demensenhet",
        "ingress": "Sykehjemsetaten presenterer planer for 120 nye sykehjemsplasser på Ljanshøgda, inkludert en skjermet avdeling for demens. Ventelisten i bydelen er i dag på 80 personer med 14 måneders gjennomsnittlig ventetid.",
        "brodtekst": [
            "Det nye sykehjemmet bygges på en kommunal tomt i Ljansbrukveien og kostnadsestimeres til 680 millioner kroner. Bygget prosjekteres som et passivhusbygg med solceller og gjenbruk av overvann.",
            "Pårørendeforeningen er positive, men etterlyser bemanningsgarantier. «Nye rom er bra, men det er menneskene som steller som gjør forskjellen», sier leder Kari Moen.",
            "Kommunen lover at bemanningsnormen vil følge Helsedirektoratets minstekrav, og at minst 40 prosent av stillingene lyses ut som hele faste stillinger.",
            "Byggestart er planlagt til januar 2027. Sykehjemmet forventes å stå ferdig til første kvartal 2029.",
        ],
        "hva_skjer_videre": "Byggesøknad sendes PBE i august 2025 — byggestart januar 2027.",
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
    {"tid": "07:42", "tekst": "Slagsmål utenfor nattklubb. To personer pågrepet.", "sted": "Grünerløkka — Thorvald Meyers gate"},
    {"tid": "06:15", "tekst": "Innbrudd i kiosk. Gjerningsperson ukjent, etterforskningssak opprettes.", "sted": "Sagene — Bentsebrugata"},
    {"tid": "04:50", "tekst": "Ordensforstyrrelser. Persons opptreden medførte utrykning, bortvist fra stedet.", "sted": "Grünerløkka — Olaf Ryes plass"},
    {"tid": "02:33", "tekst": "Trafikkulykke — MC og personbil. Én lettere skadet, ambulanse tilkalt.", "sted": "Gamle Oslo — Schweigaards gate"},
    {"tid": "01:10", "tekst": "Sykkel stjålet fra låst stativ. Anmeldelse mottatt.", "sted": "St. Hanshaugen — Pilestredet"},
    {"tid": "00:05", "tekst": "Brannalarm utløst, viste seg å være matlaging. Ingen fare.", "sted": "Frogner — Bygdøy allé"},
]

BYDELER = ["Alle bydeler", "Alna", "Bjerke", "Frogner", "Gamle Oslo", "Grorud",
           "Grünerløkka", "Nordre Aker", "Nordstrand", "Sagene", "St. Hanshaugen",
           "Stovner", "Søndre Nordstrand", "Ullern", "Vestre Aker", "Østensjø"]

KATEGORIER_MAP = {
    "Alle kategorier": None,
    "🏗️ Byggesak":        "byggesak",
    "🍺 Skjenkebevilling": "skjenkebevilling",
    "🗺️ Regulering":      "regulering",
    "🗳️ Politisk vedtak": "politisk vedtak",
    "📋 Annet":            "annet",
}

ADMIN_PASSORD = "løkka2024"


# ═════════════════════════════════════════════════════════════════════════════
# API
# ═════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def hent_saker(bydel: str, antall: int = 6) -> list[dict]:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    bydel_filter = (f"Fokuser KUN på saker fra bydel {bydel}."
                    if bydel != "Alle bydeler"
                    else "Finn saker fra ulike bydeler i Oslo.")
    researcher_system = f"""Du er nyhetsredaktør for MinOslo.
Finn {antall} aktuelle Oslo-saker fra eInnsyn, oslo.kommune.no eller PBE.
{bydel_filter}
Returner KUN gyldig JSON:
{{"saker":[{{"tittel_raa":"...","kilde_url":"https://...","kilde_navn":"...",
"bydel":"...","kategori":"byggesak|skjenkebevilling|regulering|politisk vedtak|annet",
"sammendrag_raa":"2-3 setninger","bilde_url":""}}]}}"""
    journalist_system = """Du er lokaljournalist for MinOslo.
Returner KUN gyldig JSON:
{"overskrift":"Maks 12 ord","ingress":"2-3 setninger",
"brodtekst":["avsnitt1","avsnitt2","avsnitt3","avsnitt4"],
"hva_skjer_videre":"1 setning","tags":["tag1","tag2","tag3"]}"""
    dato = datetime.now().strftime("%d. %B %Y")
    r1 = client.messages.create(
        model="claude-sonnet-4-5", max_tokens=2500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=researcher_system,
        messages=[{"role": "user", "content":
                   f"Finn {antall} Oslo-saker fra siste uken (i dag: {dato}). "
                   "Søk på einnsyn.no og oslo.kommune.no. KUN JSON."}],
    )
    raw = "".join(b.text for b in r1.content if hasattr(b, "text")).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    saker = json.loads(raw).get("saker", [])
    artikler = []
    for sak in saker:
        r2 = client.messages.create(
            model="claude-sonnet-4-5", max_tokens=1200, system=journalist_system,
            messages=[{"role": "user", "content":
                       f"Rå tittel: {sak['tittel_raa']}\nBydel: {sak['bydel']}\n"
                       f"Kategori: {sak['kategori']}\nKilde: {sak['kilde_navn']} ({sak['kilde_url']})\n"
                       f"Sammendrag: {sak['sammendrag_raa']}\nSkriv artikkel. KUN JSON."}],
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


# ═════════════════════════════════════════════════════════════════════════════
# UI-HJELPERE
# ═════════════════════════════════════════════════════════════════════════════
def meta_html(art: dict) -> str:
    return (f'<div class="mn-meta">'
            f'<span class="mn-badge">{art["bydel"]}</span>'
            f'<span class="mn-badge-kat">{art["kategori"]}</span>'
            f'<span class="mn-date">{art.get("publisert","")}</span>'
            f'</div>')


def tags_html(art: dict) -> str:
    t = "".join(f'<span class="mn-tag">{x}</span>' for x in art.get("tags", []))
    return f'<div class="mn-tags">{t}</div>'


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
def main() -> None:
    # ── Session state ──
    for k, v in [("dark_mode", False), ("artikler", []),
                 ("valgt", None), ("admin_logget_inn", False)]:
        if k not in st.session_state:
            st.session_state[k] = v

    t = DARK if st.session_state.dark_mode else LIGHT
    st.html(get_css(t))

    # ══════════════════════════════════════════════════════════════════════
    # SIDEBAR
    # ══════════════════════════════════════════════════════════════════════
    with st.sidebar:
        st.markdown(
            '<p style="font-family:\'Playfair Display\',serif;font-size:1.6rem;'
            'font-weight:900;color:#e8001f;margin:0.3rem 0 0">MinOslo</p>'
            '<p style="font-size:0.65rem;color:#666;margin-bottom:0.8rem;letter-spacing:.08em">DIN OSLO-AVIS</p>',
            unsafe_allow_html=True)
        st.markdown("---")

        # Dark/Light toggle
        ny_modus = st.toggle(
            "🌙 Dark mode",
            value=st.session_state.dark_mode,
            help="Bytt mellom lyst og mørkt tema")
        if ny_modus != st.session_state.dark_mode:
            st.session_state.dark_mode = ny_modus
            st.rerun()

        st.markdown("---")
        st.markdown("**FILTRER SAKER**")
        bydel_valg = st.selectbox("Velg bydel", BYDELER, label_visibility="visible",
                                  key="sidebar_bydel")
        kat_valg = st.selectbox("Velg kategori", list(KATEGORIER_MAP.keys()),
                                label_visibility="visible", key="sidebar_kat")
        st.markdown("---")

        if st.button("🔄  Hent nye saker fra AI", use_container_width=True):
            hent_saker.clear()
            st.session_state.valgt = None
            st.session_state.artikler = []
            st.rerun()

        st.markdown("---")

        # ── Admin-panel ──
        st.markdown(
            '<p style="font-size:0.65rem;font-weight:700;letter-spacing:.15em;'
            'text-transform:uppercase;color:#888;margin-bottom:.5rem">🔒 Admin</p>',
            unsafe_allow_html=True)

        if not st.session_state.admin_logget_inn:
            pw = st.text_input("Passord", type="password", label_visibility="collapsed",
                               placeholder="Skriv inn passord…")
            if pw == ADMIN_PASSORD:
                st.session_state.admin_logget_inn = True
                st.rerun()
            elif pw:
                st.markdown('<p style="color:#e8001f;font-size:.72rem">Feil passord</p>',
                            unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#4caf50;font-size:.7rem">✓ Innlogget som admin</p>',
                        unsafe_allow_html=True)
            if st.button("Logg ut", use_container_width=True):
                st.session_state.admin_logget_inn = False
                st.rerun()

            st.markdown("**Legg til ny sak**")
            with st.form("admin_form", clear_on_submit=True):
                ny_tittel   = st.text_input("Tittel *")
                ny_ingress  = st.text_area("Ingress *", height=80)
                ny_brodtekst = st.text_area("Brødtekst (ett avsnitt per linje)", height=120)
                ny_bydel    = st.selectbox("Bydel", BYDELER[1:])
                ny_kat      = st.selectbox("Kategori", [k for k in KATEGORIER_MAP if k != "Alle kategorier"])
                ny_bilde    = st.text_input("Bilde-URL (valgfritt)")
                ny_kilde    = st.text_input("Kilde-URL (valgfritt)")
                submitted   = st.form_submit_button("➕ Publiser sak")
                if submitted and ny_tittel and ny_ingress:
                    ny_art = {
                        "overskrift": ny_tittel,
                        "ingress": ny_ingress,
                        "brodtekst": [a.strip() for a in ny_brodtekst.split("\n") if a.strip()],
                        "hva_skjer_videre": "",
                        "tags": [ny_bydel, KATEGORIER_MAP.get(ny_kat, ny_kat)],
                        "kilde_url": ny_kilde or "#",
                        "kilde_navn": "Manuelt lagt til",
                        "bydel": ny_bydel,
                        "kategori": KATEGORIER_MAP.get(ny_kat, "annet"),
                        "publisert": datetime.now().strftime("%-d. %b %Y"),
                        "bilde_url": ny_bilde,
                    }
                    if not st.session_state.artikler:
                        st.session_state.artikler = list(DEMO_ARTIKLER)
                    st.session_state.artikler.insert(0, ny_art)
                    st.success("Sak publisert!")
                    st.rerun()

        st.markdown("---")
        st.markdown(
            '<p style="font-size:.62rem;color:#555;line-height:1.6">'
            'Artikler genereres av AI basert på offentlige kilder. '
            'Klikk kildelenken for å lese originaldokumentet.</p>',
            unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════════════════════════════
    nav_html = "".join(
        f'<span class="mn-nav-item{"  active" if i == 0 else ""}">{x}</span>'
        for i, x in enumerate(["Nyheter", "Byggesaker", "Skjenking", "Politilogg"])
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
        # Bytt til livedata:
        # with st.spinner("Henter saker…"):
        #     st.session_state.artikler = hent_saker(bydel_valg)

    # ── Filtrer ──
    kat_filter = KATEGORIER_MAP.get(kat_valg)
    alle = st.session_state.artikler
    if bydel_valg != "Alle bydeler":
        alle = [a for a in alle if a.get("bydel") == bydel_valg]
    if kat_filter:
        alle = [a for a in alle if a.get("kategori") == kat_filter]

    # ══════════════════════════════════════════════════════════════════════
    # ARTIKKELVISNING (full bredde)
    # ══════════════════════════════════════════════════════════════════════
    if st.session_state.valgt:
        art = st.session_state.valgt
        if st.button("← Tilbake til forsiden"):
            st.session_state.valgt = None
            st.rerun()
        vis_media(art, 400)
        st.markdown('<div class="mn-article-wrap">', unsafe_allow_html=True)
        st.markdown(meta_html(art), unsafe_allow_html=True)
        st.markdown(f'<h1>{art["overskrift"]}</h1>', unsafe_allow_html=True)
        st.markdown(f'<div class="mn-ingress-full">{art["ingress"]}</div>', unsafe_allow_html=True)
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

    # ══════════════════════════════════════════════════════════════════════
    # FORSIDE: to-kolonne layout (nyheter | politilogg)
    # ══════════════════════════════════════════════════════════════════════
    if not alle:
        st.markdown(
            f'<div style="text-align:center;padding:5rem 2rem;color:{t["text_soft"]}">'
            '<h3 style="font-family:\'Playfair Display\',serif;font-style:italic">'
            'Ingen saker funnet</h3><p>Prøv en annen bydel eller kategori.</p></div>',
            unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    col_nyheter, col_police = st.columns([3, 1], gap="large")

    # ── Venstre: nyheter ──
    with col_nyheter:
        # Hero
        st.markdown('<div class="mn-label mn-label-red">Hovedsak</div>', unsafe_allow_html=True)
        hero = alle[0]
        vis_media(hero, 380)
        st.markdown(meta_html(hero), unsafe_allow_html=True)
        if st.button(hero["overskrift"], key="hero_btn"):
            st.session_state.valgt = hero
            st.rerun()
        st.markdown(
            f'<p class="mn-hero-ingress" style="color:{t["text_body"]};'
            f'font-size:1rem;line-height:1.65;margin:.4rem 0 .7rem">'
            f'{hero["ingress"]}</p>',
            unsafe_allow_html=True)
        st.markdown(tags_html(hero), unsafe_allow_html=True)

        # Grid — resten av sakene
        resten = alle[1:]
        if resten:
            st.markdown('<div class="mn-label">Flere saker</div>', unsafe_allow_html=True)
            for rad_start in range(0, len(resten), 3):
                rad = resten[rad_start:rad_start + 3]
                cols = st.columns(len(rad), gap="small")
                for col, art in zip(cols, rad):
                    with col:
                        st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                        vis_media(art, 150)
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

    # ── Høyre: Politilogg ──
    with col_police:
        st.markdown(
            '<div class="mn-label mn-label-red" style="margin-top:0">Politilogg</div>',
            unsafe_allow_html=True)
        police_items = "".join(
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
            f'{police_items}'
            f'<p style="font-size:.62rem;color:#3a5a80;margin-top:.5rem;text-align:center">'
            f'Kilde: Oslo politidistrikt (demo)</p>'
            f'</div>',
            unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
