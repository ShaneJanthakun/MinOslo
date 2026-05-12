"""
MinOslo — Profesjonell nettavis
================================
Kjør: streamlit run app.py

Krav:
    pip install streamlit anthropic

Legg API-nøkkelen i .streamlit/secrets.toml:
    ANTHROPIC_API_KEY = "sk-ant-..."
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

# ─────────────────────────────────────────────────────────────────────────────
# TEMA-DEFINISJONER
# Alle farger defineres her — CSS-strengen bygges dynamisk i get_css().
# ─────────────────────────────────────────────────────────────────────────────
DARK = {
    "bg":           "#0f0f0f",
    "bg_card":      "#1a1a1a",
    "bg_sidebar":   "#111111",
    "bg_hero":      "#141414",
    "border":       "#2e2e2e",
    "text_primary": "#f0f0f0",
    "text_body":    "#cccccc",
    "text_soft":    "#888888",
    "text_muted":   "#555555",
    "accent":       "#e63329",   # VG-rød
    "accent_light": "#ff6b64",
    "tag_bg":       "#252525",
    "tag_text":     "#aaaaaa",
    "button_bg":    "transparent",
    "button_text":  "#f0f0f0",
    "button_hover": "#1a1a1a",
    "badge_bg":     "#e63329",
    "badge_text":   "#ffffff",
    "meta_bg":      "#252525",
}

LIGHT = {
    "bg":           "#f4f4f4",
    "bg_card":      "#ffffff",
    "bg_sidebar":   "#1a1a1a",
    "bg_hero":      "#ffffff",
    "border":       "#dddddd",
    "text_primary": "#111111",
    "text_body":    "#333333",
    "text_soft":    "#666666",
    "text_muted":   "#999999",
    "accent":       "#e63329",
    "accent_light": "#c0251c",
    "tag_bg":       "#f0f0f0",
    "tag_text":     "#555555",
    "button_bg":    "transparent",
    "button_text":  "#111111",
    "button_hover": "#f0f0f0",
    "badge_bg":     "#e63329",
    "badge_text":   "#ffffff",
    "meta_bg":      "#f0f0f0",
}


def get_css(t: dict) -> str:
    """Bygg komplett CSS-streng fra temavariabler."""
    return f"""
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
/* ── Reset & globals ── */
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding: 0 !important; max-width: 100% !important; }}

html, body, .stApp {{
  background-color: {t["bg"]} !important;
  font-family: 'Inter', sans-serif;
  color: {t["text_primary"]};
}}

/* ── Sidebar ── */
[data-testid="stSidebar"] {{
  background: {t["bg_sidebar"]} !important;
  border-right: 1px solid {t["border"]};
}}
[data-testid="stSidebar"] * {{
  color: #e0e0e0 !important;
}}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stMarkdown p {{
  color: #aaaaaa !important;
  font-size: 0.75rem !important;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}}
[data-testid="stSidebar"] .stButton > button {{
  background: {t["accent"]} !important;
  color: #ffffff !important;
  border: none !important;
  border-radius: 4px !important;
  font-weight: 600 !important;
  font-size: 0.8rem !important;
  width: 100%;
  padding: 0.6rem 1rem !important;
  margin-top: 0.5rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
  background: {t["accent_light"]} !important;
}}
[data-testid="stSidebar"] hr {{
  border-color: #333333 !important;
}}

/* ── Header / Masthead ── */
.mn-header {{
  background: {t["bg_card"]};
  border-bottom: 3px solid {t["accent"]};
  padding: 0;
}}
.mn-header-inner {{
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 2rem;
}}
.mn-top-bar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 0 0.5rem;
}}
.mn-logo {{
  font-family: 'Playfair Display', serif;
  font-size: 2.4rem;
  font-weight: 900;
  color: {t["accent"]};
  letter-spacing: -0.02em;
  line-height: 1;
  text-decoration: none;
}}
.mn-logo span {{ color: {t["text_primary"]}; }}
.mn-dateline {{
  font-size: 0.7rem;
  color: {t["text_soft"]};
  text-transform: uppercase;
  letter-spacing: 0.15em;
}}
.mn-nav {{
  display: flex;
  gap: 0;
  border-top: 1px solid {t["border"]};
  margin-top: 0.25rem;
}}
.mn-nav-item {{
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: {t["text_soft"]};
  padding: 0.7rem 1.2rem;
  border-bottom: 3px solid transparent;
  margin-bottom: -3px;
  cursor: default;
}}
.mn-nav-item.active {{
  color: {t["accent"]};
  border-bottom-color: {t["accent"]};
}}

/* ── Page wrapper ── */
.mn-page {{
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem 2rem 5rem;
}}

/* ── Seksjonstitler ── */
.mn-section-label {{
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: {t["text_soft"]};
  border-top: 2px solid {t["text_primary"]};
  padding-top: 0.5rem;
  margin: 2.5rem 0 1.2rem;
}}

/* ── Hero-kort (heltesak) ── */
.mn-hero {{
  background: {t["bg_hero"]};
  border: 1px solid {t["border"]};
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 1.5rem;
}}
.mn-hero-body {{
  padding: 1.5rem 2rem 1.8rem;
}}
.mn-hero-title {{
  font-family: 'Playfair Display', serif;
  font-size: clamp(1.8rem, 3vw, 2.8rem);
  font-weight: 900;
  line-height: 1.1;
  color: {t["text_primary"]};
  margin: 0.6rem 0 0.9rem;
}}
.mn-hero-ingress {{
  font-size: 1.05rem;
  line-height: 1.7;
  color: {t["text_body"]};
  font-weight: 400;
  margin-bottom: 1rem;
}}

/* ── Artikkelkort (grid) ── */
.mn-card {{
  background: {t["bg_card"]};
  border: 1px solid {t["border"]};
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 1rem;
  display: flex;
  flex-direction: column;
}}
.mn-card-body {{
  padding: 1rem 1.2rem 1.2rem;
  flex: 1;
}}
.mn-card-title {{
  font-family: 'Playfair Display', serif;
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.25;
  color: {t["text_primary"]};
  margin: 0.5rem 0 0.6rem;
}}
.mn-card-ingress {{
  font-size: 0.88rem;
  line-height: 1.6;
  color: {t["text_body"]};
  font-weight: 400;
}}

/* ── Meta-badges ── */
.mn-meta {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.4rem;
}}
.mn-badge {{
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  background: {t["accent"]};
  color: #ffffff;
  padding: 0.25em 0.6em;
  border-radius: 3px;
}}
.mn-badge-kat {{
  font-size: 0.58rem;
  font-weight: 600;
  background: {t["meta_bg"]};
  color: {t["text_soft"]};
  padding: 0.25em 0.6em;
  border-radius: 3px;
  border: 1px solid {t["border"]};
}}
.mn-date {{
  font-size: 0.7rem;
  color: {t["text_soft"]};
}}

/* ── Tags ── */
.mn-tags {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-top: 0.75rem;
}}
.mn-tag {{
  font-size: 0.62rem;
  background: {t["tag_bg"]};
  color: {t["tag_text"]};
  border: 1px solid {t["border"]};
  padding: 0.2em 0.55em;
  border-radius: 20px;
}}

/* ── Artikkel fullvisning ── */
.mn-article {{
  background: {t["bg_card"]};
  border: 1px solid {t["border"]};
  border-radius: 6px;
  padding: 2.5rem;
  margin-top: 1rem;
}}
.mn-article h1 {{
  font-family: 'Playfair Display', serif;
  font-size: clamp(1.8rem, 3vw, 2.6rem);
  font-weight: 900;
  line-height: 1.12;
  color: {t["text_primary"]};
  margin-bottom: 1rem;
}}
.mn-article .mn-ingress-full {{
  font-size: 1.15rem;
  line-height: 1.75;
  color: {t["text_body"]};
  font-weight: 400;
  border-left: 4px solid {t["accent"]};
  padding-left: 1.2rem;
  margin-bottom: 1.8rem;
}}
.mn-article p {{
  font-size: 1rem;
  line-height: 1.85;
  color: {t["text_body"]};
  font-weight: 400;
  margin-bottom: 1.1rem;
}}
.mn-article .mn-videre {{
  background: {t["meta_bg"]};
  border-left: 4px solid {t["accent"]};
  padding: 1rem 1.3rem;
  margin: 1.8rem 0;
  border-radius: 0 4px 4px 0;
  font-size: 0.92rem;
  color: {t["text_body"]};
}}
.mn-article .mn-kilde {{
  font-size: 0.78rem;
  color: {t["text_soft"]};
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid {t["border"]};
}}
.mn-article .mn-kilde a {{ color: {t["accent"]}; text-decoration: none; }}

/* ── Streamlit-knapper — gjøres transparente og tilpasses temaet ──
   VIKTIG: ingen z-index, ingen overflow:hidden på wrapper.
   Dette hindrer at knapper blokkeres av kart-iframes. ── */
.stButton > button {{
  background: {t["button_bg"]} !important;
  color: {t["button_text"]} !important;
  border: none !important;
  border-radius: 0 !important;
  font-family: 'Playfair Display', serif !important;
  font-size: 1rem !important;
  font-weight: 700 !important;
  text-align: left !important;
  padding: 0 !important;
  line-height: 1.25 !important;
  width: 100% !important;
  white-space: normal !important;
  height: auto !important;
  cursor: pointer !important;
}}
.stButton > button:hover {{
  color: {t["accent"]} !important;
  text-decoration: none !important;
}}
.stButton > button:focus {{
  box-shadow: none !important;
  outline: none !important;
}}

/* ── Kart-wrapper: INGEN overflow:hidden, INGEN z-index ──
   Disse to egenskapene var rotårsaken til at knapper ble blokkert. ── */
.mn-map-wrap {{
  line-height: 0;
  border-radius: 6px 6px 0 0;
}}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# KART
# ─────────────────────────────────────────────────────────────────────────────
BYDEL_COORDS: dict[str, tuple[float, float]] = {
    "Alna":              (59.9100, 10.8500),
    "Bjerke":            (59.9350, 10.8000),
    "Frogner":           (59.9200, 10.7100),
    "Gamle Oslo":        (59.9050, 10.7700),
    "Grorud":            (59.9550, 10.8700),
    "Grünerløkka":       (59.9270, 10.7600),
    "Nordre Aker":       (59.9600, 10.7500),
    "Nordstrand":        (59.8750, 10.8000),
    "Sagene":            (59.9380, 10.7550),
    "St. Hanshaugen":    (59.9280, 10.7350),
    "Stovner":           (59.9700, 10.9200),
    "Søndre Nordstrand": (59.8450, 10.8200),
    "Ullern":            (59.9100, 10.6500),
    "Vestre Aker":       (59.9500, 10.6700),
    "Østensjø":          (59.8900, 10.8300),
    "Hele Oslo":         (59.9139, 10.7522),
}
_OSLO_DEFAULT = (59.9139, 10.7522)
_DLON, _DLAT = 0.030, 0.015


def vis_kart(bydel: str, høyde: int) -> None:
    """
    Rendrer OpenStreetMap via components.html() med eksplisitt høyde.
    Dette er den ENESTE Streamlit-API-en som garanterer riktig iframe-høyde.
    st.html() / st.markdown() har ikke height-parameter og kollapser til 0px.
    """
    lat, lon = BYDEL_COORDS.get(bydel, _OSLO_DEFAULT)
    bbox = f"{lon-_DLON},{lat-_DLAT},{lon+_DLON},{lat+_DLAT}"
    html = f"""<!DOCTYPE html><html><body style="margin:0;padding:0;overflow:hidden;">
<iframe
  src="https://www.openstreetmap.org/export/embed.html?bbox={bbox}&layer=mapnik"
  style="width:100%;height:{høyde}px;border:none;display:block;"
  title="Kart over {bydel}">
</iframe></body></html>"""
    components.html(html, height=høyde, scrolling=False)


def vis_bilde(art: dict, høyde: int) -> None:
    """Bilde hvis tilgjengelig, ellers OSM-kart som fallback."""
    url = art.get("bilde_url", "").strip()
    if url:
        st.markdown(
            f'<div class="mn-map-wrap">'
            f'<img src="{url}" style="width:100%;height:{høyde}px;'
            f'object-fit:cover;display:block;" alt=""></div>',
            unsafe_allow_html=True,
        )
    else:
        vis_kart(art.get("bydel", "Hele Oslo"), høyde)


# ─────────────────────────────────────────────────────────────────────────────
# DEMO-DATA  (6 varierte testsaker)
# ─────────────────────────────────────────────────────────────────────────────
DEMO_ARTIKLER = [
    {
        "overskrift": "Gigantprosjekt på Filipstad: 3 000 boliger og ny bystrand planlegges",
        "ingress": (
            "Oslo kommune og Statsbygg presenterer i dag detaljreguleringsplanen for Filipstad. "
            "Planen innebærer 3 000 nye boliger, et nytt bytorg ved sjøkanten og en offentlig "
            "badestrand mellom Aker Brygge og Tjuvholmen. Beboere i Frogner er bekymret for "
            "økt trafikk og skygge på eksisterende boligbebyggelse."
        ),
        "brodtekst": [
            "Filipstad-prosjektet er det største byutviklingsprosjektet i Oslo siden Bjørvika, "
            "og er estimert til å koste over 12 milliarder kroner. Byggestart er planlagt til 2027 "
            "med første innflytting i 2031.",
            "Reguleringsplanen åpner for bygg opp til 14 etasjer langs sjøfronten, noe som har "
            "skapt kraftige reaksjoner fra beboere i Frogner bydel. Over 200 naboklager er allerede "
            "innlevert til Plan- og bygningsetaten.",
            "Ordfører Anne Lindboe forsvarer prosjektet og peker på at Oslo trenger minst "
            "50 000 nye boliger de neste ti årene for å møte befolkningsveksten.",
            "Den nye badestranden er beregnet til å trekke opp mot 5 000 besøkende daglig i "
            "sommersesongen og vil erstatte containerterminalen som i dag dominerer området.",
        ],
        "hva_skjer_videre": "Offentlig høring avsluttes 30. juni — vedtak i bystyret ventes i november.",
        "tags": ["Filipstad", "byutvikling", "bolig", "bystrand", "Frogner"],
        "kilde_url": "https://pbe.oslo.kommune.no",
        "kilde_navn": "Plan- og bygningsetaten",
        "bydel": "Frogner",
        "kategori": "regulering",
        "publisert": "12. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Ny T-banelinje til Grorud vedtatt — åpner i 2031",
        "ingress": (
            "Bystyret stemte tirsdag kveld for utbygging av en ny T-banelinje fra Storo til Grorud. "
            "Prosjektet har en kostnadsramme på 8,4 milliarder kroner og er ventet å halvere "
            "reisetiden fra Grorud sentrum til Oslo S."
        ),
        "brodtekst": [
            "Den nye linjen vil få fem stasjoner: Storo, Bjerke, Alna senter, Furuset og Grorud. "
            "Alle stasjonene bygges universelt utformet med heis og taktile ledelinjer.",
            "Ruter anslår at den nye linjen vil ta 18 000 daglige reisende fra buss og bil, "
            "noe som tilsvarer 1 200 tonn redusert CO₂ per år.",
            "Grorud bydelsutvalg har i årevis jobbet for bedre kollektivtilbud og hyllet vedtaket "
            "som «historisk for østkanten».",
            "Anleggsarbeidet starter høsten 2026. I byggeperioden vil det bli innført "
            "erstatningsbusser på strekningen.",
        ],
        "hva_skjer_videre": "Detaljprosjektering starter i høst — anleggsstart planlagt oktober 2026.",
        "tags": ["T-bane", "Grorud", "kollektivtransport", "bystyret"],
        "kilde_url": "https://oslo.kommune.no",
        "kilde_navn": "Oslo kommune",
        "bydel": "Grorud",
        "kategori": "politisk vedtak",
        "publisert": "11. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Populær kafé på Grünerløkka nektes skjenkebevilling etter naboklag",
        "ingress": (
            "Kafé Lykkelig i Thorvald Meyers gate fikk avslag på søknad om utvidet "
            "skjenkebevilling til 03.00. Kommunen viser til 47 naboklager om støy og "
            "ordensproblemer i helgene."
        ),
        "brodtekst": [
            "Kaféen, som har vært et populært samlingssted på Løkka siden 2019, søkte om å "
            "utvide skjenketiden fra 01.00 til 03.00 fredag og lørdag. Søknaden ble avslått "
            "i formannskapet med 8 mot 3 stemmer.",
            "Eier Maria Halvorsen er skuffet og mener kommunen ikke tar nok hensyn til "
            "næringslivets behov. Hun vurderer å klage vedtaket inn for Statsforvalteren.",
            "Beboerne i nabolaget er derimot lettet. «Vi er glade for at kommunen lytter til oss "
            "som faktisk bor her,» sier naboforeningens leder Bjørn Eriksen.",
            "Kaféen beholder sin nåværende bevilling frem til 01.00 og kan søke på nytt etter "
            "seks måneder dersom støynivået dokumenteres som akseptabelt.",
        ],
        "hva_skjer_videre": "Klagefrist utløper 26. mai — endelig avgjørelse hos Statsforvalteren.",
        "tags": ["skjenkebevilling", "kafé", "Grünerløkka", "naboklage"],
        "kilde_url": "https://oslo.kommune.no",
        "kilde_navn": "Oslo kommune",
        "bydel": "Grünerløkka",
        "kategori": "skjenkebevilling",
        "publisert": "10. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Historisk skole i Sagene rives — elever sendes til modulbygg",
        "ingress": (
            "Sagene skole fra 1898 skal rives etter at kommunen konkluderte med at bygget "
            "har omfattende fukt- og betongrehabileringsbehov. 420 elever flyttes til "
            "midlertidige modulbygg i tre år mens ny skole reises på tomten."
        ),
        "brodtekst": [
            "Tilstandsrapporten som ble lagt frem for Utdanningsetaten viser sprekker i bærende "
            "konstruksjoner, omfattende fuktskader og asbest i vegger og gulv. Rehabiliteringskost "
            "er estimert til 380 millioner — bare 20 millioner mindre enn et nybygg.",
            "Foreldrene er rasende. FAU-leder Tone Dahl kaller prosessen «en katastrofe» og krever "
            "at kommunen garanterer at modulbyggene er forsvarlige og at elevene ikke mister "
            "uteareal i byggeperioden.",
            "Utdanningsdirektøren beklager situasjonen og lover at modulbyggene vil tilfredsstille "
            "alle krav til innemiljø, og at skolegården sikres et areal tilsvarende normkravet.",
            "Det er bevilget 420 millioner til ny skole som skal stå ferdig til skolestart 2028. "
            "Arkitektkonkurransen lyses ut etter sommeren.",
        ],
        "hva_skjer_videre": "Rivingstillatelse behandles av PBE i juni — modulbygg settes opp fra august.",
        "tags": ["skole", "Sagene", "riving", "utdanning", "kulturminne"],
        "kilde_url": "https://www.oslo.kommune.no/skole-og-utdanning",
        "kilde_navn": "Oslo kommune / Utdanningsetaten",
        "bydel": "Sagene",
        "kategori": "politisk vedtak",
        "publisert": "9. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Tøyenparken utvides: 4 200 m² ny park etter at Sørligata stenges",
        "ingress": (
            "Bymiljøetaten starter arbeidet med å gjøre Sørligata bilfri og innlemme "
            "veibanen i Tøyenparken. Prosjektet gir 4 200 nye kvadratmeter parkplass "
            "og en sammenhengende grønn korridor fra Botanisk hage til Vallhall."
        ),
        "brodtekst": [
            "Sørligata mellom Tøyengata og Kolstadgata vil stenges for gjennomkjøring fra "
            "1. september. Totalt fjernes 34 parkeringsplasser, noe bilister i nabolaget "
            "protesterer mot.",
            "Bymiljøetaten understreker at to nye parkeringshus i nærheten er under planlegging "
            "og vil stå ferdige innen 2027. I mellomtiden vil gateparkering i sidegatene utvides.",
            "Prosjektet er finansiert over Klimabudsjettet 2025 og er en del av en større "
            "satsning på grønne lunger i indre Oslo øst.",
            "Lokale barnehager og skoler har bidratt i designprosessen og ønsker seg "
            "klatrestativer, vannlek og urtehage som del av den nye parken.",
        ],
        "hva_skjer_videre": "Anleggsarbeid starter 1. september — parken åpner offisielt vår 2026.",
        "tags": ["park", "Tøyen", "bilfritt", "Gamle Oslo", "grøntareal"],
        "kilde_url": "https://oslo.kommune.no",
        "kilde_navn": "Oslo kommune / Bymiljøetaten",
        "bydel": "Gamle Oslo",
        "kategori": "regulering",
        "publisert": "8. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Nytt sykehjem på Nordstrand: 120 plasser og demensenhet",
        "ingress": (
            "Sykehjemsetaten legger frem planer for et nytt sykehjem på Ljanshøgda med "
            "120 plasser, inkludert en skjermet avdeling for personer med demens. "
            "Ventelisten i bydelen er i dag på over 80 personer."
        ),
        "brodtekst": [
            "Det nye sykehjemmet skal bygges på en kommunal tomt i Ljansbrukveien og er "
            "beregnet å koste 680 millioner kroner. Bygget planlegges som et «grønt» bygg "
            "med solceller og gjenbruk av regnvann.",
            "Nordstrand har i dag to sykehjem med til sammen 198 plasser, noe som er langt "
            "under behovet for en aldrende bydel. Køen for sykehjemsplass er den lengste "
            "i Oslo, med gjennomsnittlig ventetid på 14 måneder.",
            "Pårørendeforeningen er positive, men etterlyser mer personell. «Det nytter lite "
            "med nye rom hvis det ikke er nok folk til å stelle pasientene,» sier leder "
            "Kari Moen.",
            "Kommunen lover at bemanningsnormen vil følge Helsedirektoratets anbefalinger og "
            "at 40 prosent av stillingene lyses ut som hele faste stillinger.",
        ],
        "hva_skjer_videre": "Byggesøknad sendes PBE i august — byggestart planlagt januar 2027.",
        "tags": ["sykehjem", "Nordstrand", "eldreomsorg", "demens", "helse"],
        "kilde_url": "https://oslo.kommune.no/helse-og-omsorg",
        "kilde_navn": "Oslo kommune / Sykehjemsetaten",
        "bydel": "Nordstrand",
        "kategori": "politisk vedtak",
        "publisert": "7. mai 2025",
        "bilde_url": "",
    },
]

BYDELER = [
    "Alle bydeler", "Alna", "Bjerke", "Frogner", "Gamle Oslo", "Grorud",
    "Grünerløkka", "Nordre Aker", "Nordstrand", "Sagene",
    "St. Hanshaugen", "Stovner", "Søndre Nordstrand",
    "Ullern", "Vestre Aker", "Østensjø",
]

KATEGORIER = {
    "Alle kategorier": None,
    "🏗️ Byggesak":        "byggesak",
    "🍺 Skjenkebevilling": "skjenkebevilling",
    "🗺️ Regulering":      "regulering",
    "🗳️ Politisk vedtak": "politisk vedtak",
    "📋 Annet":            "annet",
}

NAV_ITEMS = ["Nyheter", "Byggesaker", "Skjenkesaker", "Regulering", "Politikk"]


# ─────────────────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def hent_saker(bydel: str, antall: int = 6) -> list[dict]:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

    bydel_filter = (
        f"Fokuser KUN på saker fra bydel {bydel}."
        if bydel != "Alle bydeler"
        else "Finn saker fra ulike bydeler i Oslo."
    )

    researcher_system = f"""Du er nyhetsredaktør for MinOslo.
Finn {antall} aktuelle Oslo-saker fra eInnsyn, oslo.kommune.no eller PBE.
{bydel_filter}
Returner KUN gyldig JSON:
{{
  "saker": [{{
    "tittel_raa": "...", "kilde_url": "https://...", "kilde_navn": "...",
    "bydel": "...", "kategori": "byggesak | skjenkebevilling | regulering | politisk vedtak | annet",
    "sammendrag_raa": "2-3 setninger", "bilde_url": ""
  }}]
}}"""

    journalist_system = """Du er lokaljournalist for MinOslo. Skriv klare, engasjerende artikler.
Returner KUN gyldig JSON:
{
  "overskrift": "Maks 12 ord",
  "ingress": "2-3 setninger",
  "brodtekst": ["avsnitt1","avsnitt2","avsnitt3","avsnitt4"],
  "hva_skjer_videre": "1 setning",
  "tags": ["tag1","tag2","tag3"]
}"""

    dato = datetime.now().strftime("%d. %B %Y")
    r1 = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2500,
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
            model="claude-sonnet-4-5",
            max_tokens=1200,
            system=journalist_system,
            messages=[{"role": "user", "content":
                f"Rå tittel: {sak['tittel_raa']}\nBydel: {sak['bydel']}\n"
                f"Kategori: {sak['kategori']}\nKilde: {sak['kilde_navn']} ({sak['kilde_url']})\n"
                f"Sammendrag: {sak['sammendrag_raa']}\n\nSkriv artikkel. KUN JSON."}],
        )
        txt = r2.content[0].text.strip()
        if txt.startswith("```"):
            txt = txt.split("\n", 1)[1].rsplit("```", 1)[0]
        art = json.loads(txt)
        art.update({
            "kilde_url":  sak["kilde_url"],
            "kilde_navn": sak["kilde_navn"],
            "bydel":      sak["bydel"],
            "kategori":   sak["kategori"],
            "publisert":  datetime.now().strftime("%-d. %b %Y"),
            "bilde_url":  sak.get("bilde_url", ""),
        })
        artikler.append(art)
    return artikler


# ─────────────────────────────────────────────────────────────────────────────
# UI-KOMPONENTER
# ─────────────────────────────────────────────────────────────────────────────
def meta(art: dict) -> None:
    st.markdown(
        f'<div class="mn-meta">'
        f'<span class="mn-badge">{art["bydel"]}</span>'
        f'<span class="mn-badge-kat">{art["kategori"]}</span>'
        f'<span class="mn-date">{art["publisert"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def tags(art: dict) -> None:
    t = "".join(f'<span class="mn-tag">{x}</span>' for x in art.get("tags", []))
    st.markdown(f'<div class="mn-tags">{t}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    # ── Temavalg (initialiseres til Dark) ──
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = True
    if "artikler" not in st.session_state:
        st.session_state.artikler = []
    if "valgt" not in st.session_state:
        st.session_state.valgt = None

    tema = DARK if st.session_state.dark_mode else LIGHT

    # Injiser CSS via st.html() — ikke st.markdown()
    st.html(get_css(tema))

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(
            '<p style="font-family:\'Playfair Display\',serif;font-size:1.6rem;'
            'font-weight:900;color:#e63329;margin:0.5rem 0 0.25rem">MinOslo</p>'
            '<p style="font-size:0.7rem;color:#666;margin-bottom:1rem">Din Oslo-avis</p>',
            unsafe_allow_html=True,
        )
        st.markdown("---")

        # Dark/Light-toggle
        modus_label = "🌙 Dark mode" if st.session_state.dark_mode else "☀️ Light mode"
        st.markdown(f"**{modus_label}**")
        if st.toggle("Bytt modus", value=st.session_state.dark_mode, label_visibility="collapsed"):
            if not st.session_state.dark_mode:
                st.session_state.dark_mode = True
                st.rerun()
        else:
            if st.session_state.dark_mode:
                st.session_state.dark_mode = False
                st.rerun()

        st.markdown("---")
        st.markdown("**Velg bydel**")
        bydel = st.selectbox("bydel", BYDELER, label_visibility="collapsed")
        st.markdown("**Kategori**")
        kat_label = st.selectbox("kategori", list(KATEGORIER.keys()), label_visibility="collapsed")
        kat_filter = KATEGORIER[kat_label]
        st.markdown("---")

        if st.button("🔄  Hent nye saker", use_container_width=True):
            hent_saker.clear()
            st.session_state.valgt = None
            st.session_state.artikler = []
            st.rerun()

        st.markdown("---")
        st.markdown(
            '<p style="font-size:0.65rem;color:#666;line-height:1.6">'
            "Artikler genereres av AI basert på offentlige kilder. "
            "Klikk kildelenken for å lese originaldokumentet.</p>",
            unsafe_allow_html=True,
        )

    # ── Header ──
    nav_html = "".join(
        f'<span class="mn-nav-item{"  active" if i == 0 else ""}">{item}</span>'
        for i, item in enumerate(NAV_ITEMS)
    )
    dato_str = datetime.now().strftime("%-d. %B %Y")
    st.markdown(
        f'<div class="mn-header"><div class="mn-header-inner">'
        f'<div class="mn-top-bar">'
        f'<div class="mn-logo">Min<span>Oslo</span></div>'
        f'<div class="mn-dateline">Oslo · {dato_str}</div>'
        f'</div>'
        f'<nav class="mn-nav">{nav_html}</nav>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="mn-page">', unsafe_allow_html=True)

    # ── Last inn saker ──
    # DEMO-MODUS aktiv. Bytt til hent_saker() for ekte data:
    #   with st.spinner("Henter saker…"):
    #       st.session_state.artikler = hent_saker(bydel)
    if not st.session_state.artikler:
        st.session_state.artikler = DEMO_ARTIKLER

    artikler = st.session_state.artikler
    if kat_filter:
        artikler = [a for a in artikler if a.get("kategori") == kat_filter]

    if not artikler:
        st.markdown(
            f'<div style="text-align:center;padding:5rem 2rem;color:{tema["text_soft"]}">'
            '<h3 style="font-family:\'Playfair Display\',serif;font-style:italic">'
            "Ingen saker funnet</h3>"
            "<p>Prøv en annen bydel eller kategori.</p></div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── Artikkelvisning (fullskjerm) ──
    if st.session_state.valgt:
        art = st.session_state.valgt
        if st.button("← Tilbake"):
            st.session_state.valgt = None
            st.rerun()

        vis_bilde(art, høyde=360)
        st.markdown('<div class="mn-article">', unsafe_allow_html=True)
        meta(art)
        st.markdown(f'<h1>{art["overskrift"]}</h1>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="mn-ingress-full">{art["ingress"]}</div>',
            unsafe_allow_html=True,
        )
        for avsnitt in art.get("brodtekst", []):
            st.markdown(f"<p>{avsnitt}</p>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="mn-videre"><strong>Hva skjer videre:</strong> '
            f'{art["hva_skjer_videre"]}</div>',
            unsafe_allow_html=True,
        )
        tags(art)
        st.markdown(
            f'<div class="mn-kilde">Kilde: '
            f'<a href="{art["kilde_url"]}" target="_blank">{art["kilde_navn"]}</a></div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── Hero (heltesak — full bredde) ──
    st.markdown('<div class="mn-section-label">Toppsakene</div>', unsafe_allow_html=True)

    hero = artikler[0]
    st.markdown('<div class="mn-hero">', unsafe_allow_html=True)
    vis_bilde(hero, høyde=340)
    st.markdown('<div class="mn-hero-body">', unsafe_allow_html=True)
    meta(hero)
    if st.button(hero["overskrift"], key="hero_btn"):
        st.session_state.valgt = hero
        st.rerun()
    st.markdown(
        f'<p class="mn-hero-ingress">{hero["ingress"]}</p>',
        unsafe_allow_html=True,
    )
    tags(hero)
    st.markdown("</div></div>", unsafe_allow_html=True)   # hero-body + hero

    # ── Grid (resten av sakene) ──
    resten = artikler[1:]
    if resten:
        st.markdown('<div class="mn-section-label">Flere saker</div>', unsafe_allow_html=True)
        # 3-kolonners grid
        for rad_start in range(0, len(resten), 3):
            rad = resten[rad_start:rad_start + 3]
            cols = st.columns(len(rad), gap="small")
            for col, art in zip(cols, rad):
                idx = artikler.index(art)
                with col:
                    st.markdown('<div class="mn-card">', unsafe_allow_html=True)
                    vis_bilde(art, høyde=150)
                    st.markdown('<div class="mn-card-body">', unsafe_allow_html=True)
                    meta(art)
                    if st.button(art["overskrift"], key=f"card_{idx}"):
                        st.session_state.valgt = art
                        st.rerun()
                    st.markdown(
                        f'<p class="mn-card-ingress">{art["ingress"]}</p>',
                        unsafe_allow_html=True,
                    )
                    tags(art)
                    st.markdown("</div></div>", unsafe_allow_html=True)  # card-body + card

    st.markdown("</div>", unsafe_allow_html=True)   # mn-page


if __name__ == "__main__":
    main()
