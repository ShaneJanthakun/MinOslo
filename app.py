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
import anthropic
import json
from datetime import datetime

st.set_page_config(
    page_title="minoslo.no",
    page_icon="🗞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,300;0,700;0,900;1,300;1,700&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root {
  --ink: #111210; --ink-mid: #3d3d38; --ink-soft: #6b6b62;
  --cream: #f7f5f0; --white: #ffffff;
  --blue: #1a4f8a; --blue-light: #e8eef7;
  --border: #e2dfd8; --radius: 6px;
}
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }
.stApp { background: var(--cream); }
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: var(--ink); }

[data-testid="stSidebar"] { background: var(--ink) !important; }
[data-testid="stSidebar"] * { color: #e8e6e0 !important; }
[data-testid="stSidebar"] .stButton > button {
  background: var(--blue) !important; color: white !important;
  border: none !important; border-radius: var(--radius) !important;
  font-weight: 500 !important; width: 100%; padding: 0.6rem !important;
}

.masthead { background: var(--ink); padding: 2rem 3rem 1.5rem; border-bottom: 3px solid var(--blue); }
.masthead h1 { font-family: 'Fraunces', serif; font-size: clamp(2.8rem,5vw,4.5rem); font-weight: 900; color: #f7f5f0; line-height: 0.9; margin: 0; }
.masthead-dateline { font-size: 0.65rem; letter-spacing: 0.2em; text-transform: uppercase; color: #6b6862; margin-bottom: 0.3rem; }
.masthead-tagline { font-family: 'Fraunces',serif; font-style: italic; font-weight: 300; color: #6b6862; font-size: 0.95rem; margin-top: 0.4rem; }

.section-bar { background: var(--white); border-bottom: 1px solid var(--border); padding: 0 3rem; }
.section-bar-inner { max-width: 1200px; margin: 0 auto; display: flex; gap: 2rem; }
.section-bar span { font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-soft); padding: 0.8rem 0; }
.section-bar .active { color: var(--blue) !important; border-bottom: 2px solid var(--blue); }

.page { max-width: 1200px; margin: 0 auto; padding: 2.5rem 3rem 4rem; }
.section-heading { font-family: 'Fraunces',serif; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-soft); border-top: 2px solid var(--ink); padding-top: 0.6rem; margin: 2.5rem 0 1.5rem; }

.hero-main { background: var(--white); padding: 2rem; border: 1px solid var(--border); border-radius: var(--radius); }
.hero-side { background: var(--white); padding: 1.5rem; border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 0.75rem; }
.hero-main h2, .hero-side h3 { font-family: 'Fraunces',serif; font-weight: 700; line-height: 1.15; margin: 0.5rem 0 0.75rem; color: var(--ink); }
.hero-main h2 { font-size: clamp(1.6rem,2.5vw,2.2rem); }
.hero-side h3 { font-size: 1.05rem; }
.ingress { font-size: 0.95rem; color: var(--ink-mid); line-height: 1.65; font-weight: 300; }

.card { background: var(--white); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.4rem; margin-bottom: 1rem; }
.card h3 { font-family: 'Fraunces',serif; font-size: 1.05rem; font-weight: 700; line-height: 1.25; margin: 0.5rem 0 0.6rem; }

.meta-row { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
.badge-bydel { font-size: 0.6rem; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; background: var(--blue); color: white; padding: 0.2em 0.6em; border-radius: 3px; }
.badge-dato { font-size: 0.7rem; color: var(--ink-soft); }
.badge-kat { font-size: 0.6rem; font-weight: 500; background: var(--blue-light); color: var(--blue); padding: 0.2em 0.6em; border-radius: 3px; }

.tags-row { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.75rem; }
.tag { font-size: 0.65rem; background: var(--cream); border: 1px solid var(--border); color: var(--ink-soft); padding: 0.2em 0.55em; border-radius: 20px; }

.article-full { background: var(--white); border: 1px solid var(--border); border-radius: var(--radius); padding: 2.5rem; margin-top: 1.5rem; }
.article-full h2 { font-family: 'Fraunces',serif; font-size: clamp(1.6rem,2.5vw,2.4rem); font-weight: 700; line-height: 1.15; margin-bottom: 1rem; }
.article-full .ingress-full { font-family: 'Fraunces',serif; font-style: italic; font-weight: 300; font-size: 1.15rem; color: var(--ink-mid); border-left: 3px solid var(--blue); padding-left: 1.2rem; margin-bottom: 1.5rem; line-height: 1.7; }
.article-full p { font-size: 1rem; line-height: 1.8; color: var(--ink-mid); margin-bottom: 1rem; font-weight: 300; }
.article-full .videre-boks { background: var(--blue-light); border-left: 3px solid var(--blue); padding: 1rem 1.2rem; margin: 1.5rem 0; border-radius: 0 var(--radius) var(--radius) 0; font-size: 0.9rem; color: var(--blue); }
.kilde-link { font-size: 0.8rem; color: var(--ink-soft); margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border); }
</style>
"""

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


@st.cache_data(ttl=3600, show_spinner=False)
def hent_saker(bydel: str, antall: int = 6) -> list[dict]:
    # Henter nøkkelen fra Streamlit Secrets — legg den i .streamlit/secrets.toml
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
    "sammendrag_raa": "2-3 setninger"
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
        messages=[{"role": "user", "content": f"Finn {antall} Oslo-saker fra siste uken (i dag: {dato}). Søk på einnsyn.no og oslo.kommune.no. KUN JSON."}],
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
            "kilde_url": sak["kilde_url"], "kilde_navn": sak["kilde_navn"],
            "bydel": sak["bydel"], "kategori": sak["kategori"],
            "publisert": datetime.now().strftime("%-d. %b %Y"),
        })
        artikler.append(art)
    return artikler


def meta_row(art):
    st.markdown(
        f'<div class="meta-row">'
        f'<span class="badge-bydel">{art["bydel"]}</span>'
        f'<span class="badge-dato">{art["publisert"]}</span>'
        f'<span class="badge-kat">{art["kategori"]}</span>'
        f'</div>', unsafe_allow_html=True)

def tags_row(art):
    tags_html = "".join(f'<span class="tag">{t}</span>' for t in art.get("tags", []))
    st.markdown(f'<div class="tags-row">{tags_html}</div>', unsafe_allow_html=True)


def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    if "artikler" not in st.session_state:
        st.session_state.artikler = []
    if "valgt_artikkel" not in st.session_state:
        st.session_state.valgt_artikkel = None

    # ── Sidebar ──
    with st.sidebar:
        st.markdown('<p style="font-size:1.4rem;font-family:Fraunces,serif;font-weight:700;color:#f7f5f0;margin-bottom:0">minoslo</p><p style="font-size:0.75rem;color:#6b6862;font-family:Fraunces,serif;font-style:italic">Din Oslo-avis</p>', unsafe_allow_html=True)
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
        st.markdown('<p style="font-size:0.65rem;color:#444;line-height:1.6">Artikler genereres av AI basert på offentlige kilder. Klikk kildelenken for å lese originaldokumentet.</p>', unsafe_allow_html=True)

    # ── Masthead ──
    dato_str = datetime.now().strftime("%-d. %B %Y").lower()
    st.markdown(f'<div class="masthead"><div style="max-width:1200px;margin:0 auto"><div class="masthead-dateline">Oslo · {dato_str}</div><h1>minoslo.no</h1><div class="masthead-tagline">Hva skjer i ditt nabolag — i dag</div></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-bar"><div class="section-bar-inner"><span class="active">Nyheter</span><span>Byggesaker</span><span>Skjenkesaker</span><span>Regulering</span><span>Politikk</span></div></div>', unsafe_allow_html=True)

    st.markdown('<div class="page">', unsafe_allow_html=True)

    # ── Hent saker ──
    if not st.session_state.artikler:
        with st.spinner("Leter etter aktuelle saker og skriver artikler…"):
            try:
                st.session_state.artikler = hent_saker(bydel)
            except Exception as e:
                st.error(f"Feil: {e}")
                st.stop()

    artikler = st.session_state.artikler
    if kat_filter:
        artikler = [a for a in artikler if a.get("kategori") == kat_filter]

    if not artikler:
        st.markdown('<div style="text-align:center;padding:4rem 2rem;color:#6b6b62"><h3 style="font-family:Fraunces,serif;font-style:italic">Ingen saker funnet</h3><p>Prøv en annen bydel eller kategori.</p></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ── Artikkelvisning ──
    if st.session_state.valgt_artikkel:
        art = st.session_state.valgt_artikkel
        if st.button("← Tilbake til forsiden"):
            st.session_state.valgt_artikkel = None
            st.rerun()
        st.markdown('<div class="article-full">', unsafe_allow_html=True)
        meta_row(art)
        st.markdown(f'<h2>{art["overskrift"]}</h2>', unsafe_allow_html=True)
        st.markdown(f'<div class="ingress-full">{art["ingress"]}</div>', unsafe_allow_html=True)
        for avsnitt in art.get("brodtekst", []):
            st.markdown(f"<p>{avsnitt}</p>", unsafe_allow_html=True)
        st.markdown(f'<div class="videre-boks"><strong>Hva skjer videre:</strong> {art["hva_skjer_videre"]}</div>', unsafe_allow_html=True)
        tags_row(art)
        st.markdown(f'<div class="kilde-link">Kilde: <a href="{art["kilde_url"]}" target="_blank">{art["kilde_navn"]}</a></div>', unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    # ── Hero ──
    st.markdown('<div class="section-heading">Dagens viktigste saker</div>', unsafe_allow_html=True)
    col_main, col_side = st.columns([3, 2], gap="small")

    with col_main:
        art = artikler[0]
        st.markdown('<div class="hero-main">', unsafe_allow_html=True)
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
            meta_row(art)
            if st.button(art["overskrift"], key=f"hero_side_{i}", use_container_width=True):
                st.session_state.valgt_artikkel = art
                st.rerun()
            st.markdown(f'<p class="ingress">{art["ingress"]}</p>', unsafe_allow_html=True)
            tags_row(art)
            st.markdown("</div>", unsafe_allow_html=True)

    # ── Cards ──
    if len(artikler) > 3:
        st.markdown('<div class="section-heading">Flere saker</div>', unsafe_allow_html=True)
        cols = st.columns(3, gap="small")
        for i, art in enumerate(artikler[3:]):
            with cols[i % 3]:
                st.markdown('<div class="card">', unsafe_allow_html=True)
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
