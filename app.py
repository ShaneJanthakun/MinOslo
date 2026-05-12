"""
minoslo.no — Streamlit-avis
============================
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
    page_title="minoslo.no",
    page_icon="🗞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# Bruker st.html() for global injeksjon (ikke st.markdown).
# FIX 1 – Kontrast: --ink-mid og all brødtekst / ingress satt til #333333.
# FIX 3 – Klikk: fjernet overflow:hidden og z-index fra .map-thumb så
#          Streamlit-widgets under kartet ikke blokkeres av iframen.
# ─────────────────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,300;0,700;0,900;1,300;1,700&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root {
  --ink:        #111210;
  --ink-mid:    #333333;   /* FIX 1: var endret fra #3d3d38 → #333333 */
  --ink-soft:   #6b6b62;
  --cream:      #f7f5f0;
  --white:      #ffffff;
  --blue:       #1a4f8a;
  --blue-light: #e8eef7;
  --border:     #e2dfd8;
  --radius:     6px;
}

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }
.stApp { background: var(--cream); }
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: var(--ink); }

/* ── Sidebar ── */
[data-testid="stSidebar"] { background: var(--ink) !important; }
[data-testid="stSidebar"] * { color: #e8e6e0 !important; }
[data-testid="stSidebar"] .stButton > button {
  background: var(--blue) !important;
  color: white !important;
  border: none !important;
  border-radius: var(--radius) !important;
  font-weight: 500 !important;
  width: 100%;
  padding: 0.6rem !important;
}

/* ── Masthead ── */
.masthead {
  background: var(--ink);
  padding: 2rem 3rem 1.5rem;
  border-bottom: 3px solid var(--blue);
}
.masthead h1 {
  font-family: 'Fraunces', serif;
  font-size: clamp(2.8rem, 5vw, 4.5rem);
  font-weight: 900;
  color: #f7f5f0;
  line-height: 0.9;
  margin: 0;
}
.masthead-dateline {
  font-size: 0.65rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #6b6862;
  margin-bottom: 0.3rem;
}
.masthead-tagline {
  font-family: 'Fraunces', serif;
  font-style: italic;
  font-weight: 300;
  color: #6b6862;
  font-size: 0.95rem;
  margin-top: 0.4rem;
}

/* ── Section bar ── */
.section-bar {
  background: var(--white);
  border-bottom: 1px solid var(--border);
  padding: 0 3rem;
}
.section-bar-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  gap: 2rem;
}
.section-bar span {
  font-size: 0.7rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-soft);
  padding: 0.8rem 0;
}
.section-bar .active {
  color: var(--blue) !important;
  border-bottom: 2px solid var(--blue);
}

/* ── Page layout ── */
.page { max-width: 1200px; margin: 0 auto; padding: 2.5rem 3rem 4rem; }
.section-heading {
  font-family: 'Fraunces', serif;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-soft);
  border-top: 2px solid var(--ink);
  padding-top: 0.6rem;
  margin: 2.5rem 0 1.5rem;
}

/* ── Artikkelkort ── */
.hero-main {
  background: var(--white);
  padding: 2rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.hero-side {
  background: var(--white);
  padding: 1.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 0.75rem;
}
.hero-main h2, .hero-side h3 {
  font-family: 'Fraunces', serif;
  font-weight: 700;
  line-height: 1.15;
  margin: 0.5rem 0 0.75rem;
  color: var(--ink);
}
.hero-main h2 { font-size: clamp(1.6rem, 2.5vw, 2.2rem); }
.hero-side h3 { font-size: 1.05rem; }

/* FIX 1 – Ingress og brødtekst: eksplisitt mørk farge */
.ingress {
  font-size: 0.95rem;
  color: #333333;
  line-height: 1.65;
  font-weight: 400;
}

.card {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.4rem;
  margin-bottom: 1rem;
}
.card h3 {
  font-family: 'Fraunces', serif;
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.25;
  margin: 0.5rem 0 0.6rem;
}

/* ── Meta-badges ── */
.meta-row { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
.badge-bydel {
  font-size: 0.6rem; font-weight: 500; letter-spacing: 0.1em;
  text-transform: uppercase; background: var(--blue); color: white;
  padding: 0.2em 0.6em; border-radius: 3px;
}
.badge-dato { font-size: 0.7rem; color: var(--ink-soft); }
.badge-kat {
  font-size: 0.6rem; font-weight: 500;
  background: var(--blue-light); color: var(--blue);
  padding: 0.2em 0.6em; border-radius: 3px;
}

/* ── Tags ── */
.tags-row { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.75rem; }
.tag {
  font-size: 0.65rem;
  background: var(--cream);
  border: 1px solid var(--border);
  color: var(--ink-soft);
  padding: 0.2em 0.55em;
  border-radius: 20px;
}

/* ── Artikkelfullvisning ── */
.article-full {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 2.5rem;
  margin-top: 1.5rem;
}
.article-full h2 {
  font-family: 'Fraunces', serif;
  font-size: clamp(1.6rem, 2.5vw, 2.4rem);
  font-weight: 700;
  line-height: 1.15;
  margin-bottom: 1rem;
  color: var(--ink);
}
/* FIX 1 – ingress og brødtekst i fullvisning: #333333 */
.article-full .ingress-full {
  font-family: 'Fraunces', serif;
  font-style: italic;
  font-weight: 300;
  font-size: 1.15rem;
  color: #333333;
  border-left: 3px solid var(--blue);
  padding-left: 1.2rem;
  margin-bottom: 1.5rem;
  line-height: 1.7;
}
.article-full p {
  font-size: 1rem;
  line-height: 1.8;
  color: #333333;
  margin-bottom: 1rem;
  font-weight: 400;
}
.article-full .videre-boks {
  background: var(--blue-light);
  border-left: 3px solid var(--blue);
  padding: 1rem 1.2rem;
  margin: 1.5rem 0;
  border-radius: 0 var(--radius) var(--radius) 0;
  font-size: 0.9rem;
  color: var(--blue);
}
.kilde-link {
  font-size: 0.8rem;
  color: var(--ink-soft);
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}

/* ── Kartbilde-wrapper ──────────────────────────────────────────────────────
   FIX 3: Ingen overflow:hidden og ingen z-index her.
   overflow:hidden blokkerte klikk på Streamlit-widgets som lå under
   iframen i samme stacking context. border-radius settes kun på iframen.
   ────────────────────────────────────────────────────────────────────────── */
.map-thumb {
  line-height: 0;
  margin-bottom: 0.75rem;
}
</style>
"""

# ── Bydel → koordinater (lat, lon) ───────────────────────────────────────────
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

# Bounding-box halvbredde i grader
_DLON, _DLAT = 0.030, 0.015


def kart_html(bydel: str, høyde: int) -> str:
    """
    Returnerer komplett HTML-streng med en OpenStreetMap embed-iframe.
    Sentrert på bydelens koordinater. Ingen API-nøkkel nødvendig.

    FIX 2: iframen får border-radius og korrekt høyde satt direkte som
    inline style — høyden sendes også som 'height'-argument til
    components.html() slik at Streamlit setter riktig iframe-høyde.
    """
    lat, lon = BYDEL_COORDS.get(bydel, _OSLO_DEFAULT)
    bbox = f"{lon - _DLON},{lat - _DLAT},{lon + _DLON},{lat + _DLAT}"
    return f"""
<html><body style="margin:0;padding:0;overflow:hidden;">
<iframe
  src="https://www.openstreetmap.org/export/embed.html?bbox={bbox}&layer=mapnik"
  style="width:100%;height:{høyde}px;border:none;border-radius:6px 6px 0 0;display:block;"
  title="Kart over {bydel}">
</iframe>
</body></html>
""".strip()


# ── Testdata ──────────────────────────────────────────────────────────────────
DEMO_ARTIKLER = [
    {
        "overskrift": "Naboer protesterer mot 14 etasjer høyt leilighetsbygg på Grünerløkka",
        "ingress": (
            "Plan- og bygningsetaten har mottatt over 40 naboprotester etter at utbygger "
            "Stor-Oslo Eiendom søkte om å oppføre et 14 etasjer høyt leilighetsbygg i "
            "Thorvald Meyers gate. Naboene frykter at bygget vil skygge for bakgårder og "
            "endre bydelens karakter."
        ),
        "brodtekst": [
            "Søknaden gjelder rivning av et eksisterende 3-etasjes murbygg fra 1920-tallet "
            "og oppføring av et moderne leilighetsbygg med 68 leiligheter og næringslokaler "
            "i første etasje. Utbygger hevder prosjektet vil bidra til å løse boligmangelen i Oslo.",
            "Beboerforeningen på Grünerløkka har samlet underskrifter og sendt en samlet klage "
            "til Plan- og bygningsetaten. De mener byggehøyden bryter med den gjeldende "
            "reguleringsplanen for området, som tillater maksimalt 5 etasjer.",
            "— Dette handler ikke om å være mot utvikling, men om å bevare det som gjør "
            "Grünerløkka til et godt sted å bo, sier leder i beboerforeningen, Marit Svensson.",
            "Plan- og bygningsetaten har satt frist for ytterligere merknader til 1. juni. "
            "En eventuell klagebehandling kan ta opptil seks måneder.",
        ],
        "hva_skjer_videre": "Saken behandles av Plan- og bygningsetaten med vedtak ventet høsten 2025.",
        "tags": ["byggesak", "Grünerløkka", "naboprotester", "høyhus"],
        "kilde_url": "https://innsyn.pbe.oslo.kommune.no",
        "kilde_navn": "Plan- og bygningsetaten",
        "bydel": "Grünerløkka",
        "kategori": "byggesak",
        "publisert": "12. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Nytt bryggeri på Sagene får skjenkebevilling frem til midnatt",
        "ingress": (
            "Oslo kommune har innvilget skjenkebevilling til Sagene Bryggeri AS i "
            "Kristoffer Robins vei 5. Bevillingen gjelder øl og vin frem til midnatt "
            "på hverdager, og til 02.00 i helger."
        ),
        "brodtekst": [
            "Bryggeriet, som åpner dørene i juni, vil kombinere produksjon av håndverksøl "
            "med en taproom åpen for publikum. Eier Thomas Bakke sier de har brukt to år "
            "på å planlegge konseptet.",
            "Nærmiljøutvalget i Sagene bydel behandlet søknaden på sitt møte i april og "
            "hadde ingen innvendinger, forutsatt at støyreglementet overholdes.",
            "Kommunen stiller krav om at uteservering avsluttes senest klokken 23.00, "
            "og at det gjennomføres støymålinger etter åpning.",
            "Sagene Bryggeri blir det femte håndverksbryggeriet med taproom i Oslo som "
            "åpner i 2025, og en del av en voksende trend med lokalt produsert øl.",
        ],
        "hva_skjer_videre": "Bryggeriet planlegger offisiell åpning 14. juni med nabotreff.",
        "tags": ["skjenkebevilling", "Sagene", "bryggeri", "næringsliv"],
        "kilde_url": "https://oslo.kommune.no",
        "kilde_navn": "Oslo kommune",
        "bydel": "Sagene",
        "kategori": "skjenkebevilling",
        "publisert": "11. mai 2025",
        "bilde_url": "",
    },
    {
        "overskrift": "Kommunen vil gjøre Tøyenparken bilfri og utvide grøntarealet",
        "ingress": (
            "Bymiljøetaten legger frem forslag om å stenge Sørligata for gjennomkjøring "
            "og innlemme veibanen i Tøyenparken. Planen innebærer 4 200 kvadratmeter ny "
            "parkplass og en sammenhengende grønn korridor fra Botanisk hage til Vallhall."
        ),
        "brodtekst": [
            "Forslaget er en del av kommunens satsning på grønne lunger i indre Oslo øst, "
            "og er blant tiltakene som ble varslet i Klimabudsjettet for 2025. "
            "Planene innebærer at 34 parkeringsplasser langs Sørligata fjernes.",
            "Beboere i området er delte i synet på forslaget. Noen hilser den bilfrie sonen "
            "velkommen, mens andre — særlig eldre og barnefamilier med bil — er bekymret "
            "for parkeringssituasjonen.",
            "Bymiljøetaten understreker at det er planlagt to nye parkeringshus i nærheten "
            "innen 2027, og at sykkeltilbudet vil bli kraftig forbedret som del av samme prosjekt.",
            "Forslaget sendes på offentlig høring med frist 15. august 2025. "
            "Bystyret ventes å fatte endelig vedtak mot slutten av året.",
        ],
        "hva_skjer_videre": "Offentlig høring åpner 1. juni — merknader leveres på oslo.kommune.no.",
        "tags": ["regulering", "Tøyen", "bilfritt", "park", "grøntareal"],
        "kilde_url": "https://oslo.kommune.no",
        "kilde_navn": "Oslo kommune / Bymiljøetaten",
        "bydel": "Gamle Oslo",
        "kategori": "regulering",
        "publisert": "10. mai 2025",
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
    "🏗️ Byggesak": "byggesak",
    "🍺 Skjenkebevilling": "skjenkebevilling",
    "🗺️ Regulering": "regulering",
    "🗳️ Politisk vedtak": "politisk vedtak",
    "📋 Annet": "annet",
}


# ── Bildefunksjon ─────────────────────────────────────────────────────────────
def artikkel_bilde(art: dict, høyde: int = 180) -> None:
    """
    Viser artikkelbilde hvis bilde_url er satt, ellers et OSM-kart for bydelen.

    FIX 2: Kartet rendres med components.html(html_streng, height=høyde).
    Dette er den eneste måten å garantere at Streamlit setter riktig høyde
    på den underliggende iframen. st.html() / st.markdown() har ikke en
    height-parameter og kollapser til 0px for iframe-innhold.
    """
    bilde_url = art.get("bilde_url", "").strip()
    bydel = art.get("bydel", "Hele Oslo")

    if bilde_url:
        st.markdown(
            f'<div class="map-thumb">'
            f'<img src="{bilde_url}" '
            f'style="width:100%;height:{høyde}px;object-fit:cover;'
            f'border-radius:6px 6px 0 0;display:block;" alt="">'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        # FIX 2 + FIX 3: components.html med eksplisitt height, ingen
        # overflow:hidden-wrapper rundt seg som kan blokkere klikk.
        components.html(kart_html(bydel, høyde), height=høyde, scrolling=False)


# ── API-kall ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def hent_saker(bydel: str, antall: int = 6) -> list[dict]:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

    bydel_filter = (
        f"Fokuser KUN på saker fra bydel {bydel}."
        if bydel != "Alle bydeler"
        else "Finn saker fra ulike bydeler i Oslo."
    )

    researcher_system = f"""Du er nyhetsredaktør for minoslo.no.
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

    journalist_system = """Du er lokaljournalist for minoslo.no. Skriv klare, engasjerende artikler.
Returner KUN gyldig JSON:
{
  "overskrift": "Maks 10 ord",
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
        messages=[{
            "role": "user",
            "content": (
                f"Finn {antall} Oslo-saker fra siste uken (i dag: {dato}). "
                "Søk på einnsyn.no og oslo.kommune.no. KUN JSON."
            ),
        }],
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
            messages=[{"role": "user", "content": (
                f"Rå tittel: {sak['tittel_raa']}\nBydel: {sak['bydel']}\n"
                f"Kategori: {sak['kategori']}\nKilde: {sak['kilde_navn']} ({sak['kilde_url']})\n"
                f"Sammendrag: {sak['sammendrag_raa']}\n\nSkriv artikkel. KUN JSON."
            )}],
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


# ── Hjelpefunksjoner ──────────────────────────────────────────────────────────
def meta_row(art: dict) -> None:
    st.markdown(
        f'<div class="meta-row">'
        f'<span class="badge-bydel">{art["bydel"]}</span>'
        f'<span class="badge-dato">{art["publisert"]}</span>'
        f'<span class="badge-kat">{art["kategori"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def tags_row(art: dict) -> None:
    tags_html = "".join(f'<span class="tag">{t}</span>' for t in art.get("tags", []))
    st.markdown(f'<div class="tags-row">{tags_html}</div>', unsafe_allow_html=True)


# ── Hoved ────────────────────────────────────────────────────────────────────
def main() -> None:
    st.html(CUSTOM_CSS)

    if "artikler" not in st.session_state:
        st.session_state.artikler = []
    if "valgt_artikkel" not in st.session_state:
        st.session_state.valgt_artikkel = None

    # ── Sidebar ──
    with st.sidebar:
        st.markdown(
            '<p style="font-size:1.4rem;font-family:Fraunces,serif;font-weight:700;'
            'color:#f7f5f0;margin-bottom:0">minoslo</p>'
            '<p style="font-size:0.75rem;color:#6b6862;font-family:Fraunces,serif;'
            'font-style:italic">Din Oslo-avis</p>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown("**Velg bydel**")
        bydel = st.selectbox("bydel", BYDELER, label_visibility="collapsed")
        st.markdown("**Kategori**")
        kat_label = st.selectbox("kategori", list(KATEGORIER.keys()), label_visibility="collapsed")
        kat_filter = KATEGORIER[kat_label]
        st.markdown("---")
        if st.button("🔄  Hent nye saker", use_container_width=True):
            hent_saker.clear()
            st.session_state.valgt_artikkel = None
            st.session_state.artikler = []
            st.rerun()
        st.markdown("---")
        st.markdown(
            '<p style="font-size:0.65rem;color:#888;line-height:1.6">'
            "Artikler genereres av AI basert på offentlige kilder. "
            "Klikk kildelenken for å lese originaldokumentet.</p>",
            unsafe_allow_html=True,
        )

    # ── Masthead ──
    dato_str = datetime.now().strftime("%-d. %B %Y").lower()
    st.markdown(
        f'<div class="masthead"><div style="max-width:1200px;margin:0 auto">'
        f'<div class="masthead-dateline">Oslo · {dato_str}</div>'
        f'<h1>minoslo.no</h1>'
        f'<div class="masthead-tagline">Hva skjer i ditt nabolag — i dag</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-bar"><div class="section-bar-inner">'
        '<span class="active">Nyheter</span><span>Byggesaker</span>'
        '<span>Skjenkesaker</span><span>Regulering</span><span>Politikk</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="page">', unsafe_allow_html=True)

    # ── Hent saker ──────────────────────────────────────────────────────────
    # DEMO-MODUS: viser hardkodede testartikler uten API-kall.
    # Bytt til hent_saker() når du er klar for ekte data:
    #   with st.spinner("…"):
    #       st.session_state.artikler = hent_saker(bydel)
    if not st.session_state.artikler:
        st.session_state.artikler = DEMO_ARTIKLER

    artikler = st.session_state.artikler
    if kat_filter:
        artikler = [a for a in artikler if a.get("kategori") == kat_filter]

    if not artikler:
        st.markdown(
            '<div style="text-align:center;padding:4rem 2rem;color:#6b6b62">'
            '<h3 style="font-family:Fraunces,serif;font-style:italic">Ingen saker funnet</h3>'
            '<p>Prøv en annen bydel eller kategori.</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── Artikkelvisning (fullskjerm) ──
    if st.session_state.valgt_artikkel:
        art = st.session_state.valgt_artikkel
        if st.button("← Tilbake til forsiden"):
            st.session_state.valgt_artikkel = None
            st.rerun()
        st.markdown('<div class="article-full">', unsafe_allow_html=True)
        artikkel_bilde(art, høyde=300)
        meta_row(art)
        st.markdown(f'<h2>{art["overskrift"]}</h2>', unsafe_allow_html=True)
        st.markdown(f'<div class="ingress-full">{art["ingress"]}</div>', unsafe_allow_html=True)
        for avsnitt in art.get("brodtekst", []):
            st.markdown(f"<p>{avsnitt}</p>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="videre-boks"><strong>Hva skjer videre:</strong> '
            f'{art["hva_skjer_videre"]}</div>',
            unsafe_allow_html=True,
        )
        tags_row(art)
        st.markdown(
            f'<div class="kilde-link">Kilde: '
            f'<a href="{art["kilde_url"]}" target="_blank">{art["kilde_navn"]}</a></div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # ── Hero-seksjon ──
    st.markdown('<div class="section-heading">Dagens viktigste saker</div>', unsafe_allow_html=True)
    col_main, col_side = st.columns([3, 2], gap="small")

    with col_main:
        art = artikler[0]
        st.markdown('<div class="hero-main">', unsafe_allow_html=True)
        artikkel_bilde(art, høyde=200)
        meta_row(art)
        if st.button(art["overskrift"], key="hero_main", use_container_width=True):
            st.session_state.valgt_artikkel = art
            st.rerun()
        st.markdown(f'<p class="ingress">{art["ingress"]}</p>', unsafe_allow_html=True)
        tags_row(art)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_side:
        for i, art in enumerate(artikler[1:3]):
            st.markdown('<div class="hero-side">', unsafe_allow_html=True)
            artikkel_bilde(art, høyde=130)
            meta_row(art)
            if st.button(art["overskrift"], key=f"hero_side_{i}", use_container_width=True):
                st.session_state.valgt_artikkel = art
                st.rerun()
            st.markdown(f'<p class="ingress">{art["ingress"]}</p>', unsafe_allow_html=True)
            tags_row(art)
            st.markdown("</div>", unsafe_allow_html=True)

    # ── Kortgalleri ──
    if len(artikler) > 3:
        st.markdown('<div class="section-heading">Flere saker</div>', unsafe_allow_html=True)
        cols = st.columns(3, gap="small")
        for i, art in enumerate(artikler[3:]):
            with cols[i % 3]:
                st.markdown('<div class="card">', unsafe_allow_html=True)
                artikkel_bilde(art, høyde=130)
                meta_row(art)
                if st.button(art["overskrift"], key=f"card_{i}", use_container_width=True):
                    st.session_state.valgt_artikkel = art
                    st.rerun()
                st.markdown(f'<p class="ingress">{art["ingress"]}</p>', unsafe_allow_html=True)
                tags_row(art)
                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
