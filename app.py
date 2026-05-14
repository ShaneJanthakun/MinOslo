"""
MinOslo.no — Produksjonsversjon
=================================
Kjør:   streamlit run app.py --server.port $PORT --server.address 0.0.0.0
Krav:   pip install streamlit requests beautifulsoup4 lxml

Datakilder (ingen API-nøkler nødvendig):
  • Politiloggen  — api.politiet.no/politiloggen/v1
  • Oslo kommune  — aktuelt.oslo.kommune.no RSS
  • NRK Stor-Oslo — nrk.no/stor-oslo/feed/
  • eInnsyn       — einnsyn.no/rss
"""

import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import re, html as _html

st.set_page_config(
    page_title="MinOslo",
    page_icon="🗞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── NORSK TID ────────────────────────────────────────────────
def _nå() -> datetime:
    u = datetime.now(timezone.utc)
    off = 2 if datetime(u.year,3,25,1,tzinfo=timezone.utc) <= u < datetime(u.year,10,25,1,tzinfo=timezone.utc) else 1
    return u.astimezone(timezone(timedelta(hours=off)))

_TZ = _nå().tzinfo

# ─── KONSTANTER ───────────────────────────────────────────────
ADMIN_PW = "løkka2024"
TIMEOUT  = 5
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "nb-NO,nb;q=0.9",
}
OSM_UA = {"User-Agent": "MinOsloBot/1.0 (shane@example.com)"}

# Statiske Unsplash-bilder per kategori (ingen API-nøkkel)
IMGS = {
    "politilogg":       "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=800&h=450&fit=crop&q=75",
    "kommune":          "https://images.unsplash.com/photo-1446822775955-c34f483b410b?w=800&h=450&fit=crop&q=75",
    "nrk":              "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800&h=450&fit=crop&q=75",
    "einnsyn":          "https://images.unsplash.com/photo-1464938050520-ef2270bb8ce8?w=800&h=450&fit=crop&q=75",
    "byggesak":         "https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=800&h=450&fit=crop&q=75",
    "skjenkebevilling": "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?w=800&h=450&fit=crop&q=75",
    "regulering":       "https://images.unsplash.com/photo-1476231682828-37e571bc172f?w=800&h=450&fit=crop&q=75",
    "annet":            "https://images.unsplash.com/photo-1583907608452-7260268ec9a8?w=800&h=450&fit=crop&q=75",
}
FB = IMGS["annet"]  # garantert fallback

OSLO_RE = re.compile(
    r"\bOslo|Grünerløkka|Frogner|Sagene|Majorstuen|Alna|Bjerke|Grorud|"
    r"Nordstrand|Nordre Aker|Vestre Aker|Østensjø|Stovner|Gamle Oslo|"
    r"Hanshaugen|Sentrum|Bislett|Tøyen|Grønland|Holmlia\b", re.I
)
EKSKL = re.compile(
    r"\b(utenriks|verden|Europa|USA|Russland|Ukraina|Israel|Gaza|Kina|"
    r"Premier.?League|Champions League|Eliteserien|landslaget|VM |EM |"
    r"Nobel|Stortinget|regjeringen|statsminister|"
    r"Trondheim|Bergen|Stavanger|Tromsø|Bodø|Drammen)\b", re.I
)

GATE_RE = re.compile(
    r"\b([A-ZÆØÅ][a-zæøå]+(?:gate|gata|vei|veien|allé|alléen|plass|plassen|"
    r"torg|torget|brygge|bryggen|kaia|kaien|bakke|bakken|løkka|parken|stien)"
    r"(?:\s+\d+[A-Za-z]?)?)\b", re.U
)

BYDELER   = ["Alle bydeler","Alna","Bjerke","Frogner","Gamle Oslo","Grorud",
             "Grünerløkka","Nordre Aker","Nordstrand","Sagene","St. Hanshaugen",
             "Stovner","Søndre Nordstrand","Ullern","Vestre Aker","Østensjø"]
KATEGORIER= ["Alle kategorier","politilogg","kommune","nrk","einnsyn",
             "byggesak","skjenkebevilling","regulering","politisk vedtak","annet"]

KILDER = [
    {"id":"politi","url":"https://api.politiet.no/politiloggen/v1/meldinger?distrikt=Oslo&antall=30",
     "navn":"Politiloggen","badge":"P","farge":"#cd3d33","type":"politi",
     "max_alder":timedelta(hours=24),"link":"https://politiloggen.politiet.no","oslo_filter":True},
    {"id":"oslo","url":"https://aktuelt.oslo.kommune.no/?format=rss",
     "url_alt":["https://www.oslo.kommune.no/rss/","https://aktuelt.oslo.kommune.no/feed/"],
     "navn":"Oslo kommune","badge":"K","farge":"#1a6632","type":"rss","kategori":"kommune",
     "max_alder":timedelta(days=7),"link":"https://aktuelt.oslo.kommune.no","oslo_filter":False},
    {"id":"nrk","url":"https://www.nrk.no/stor-oslo/feed/",
     "url_alt":["https://www.nrk.no/toppsaker.rss"],
     "navn":"NRK","badge":"N","farge":"#cd3d33","type":"rss","kategori":"nrk",
     "max_alder":timedelta(days=7),"link":"https://www.nrk.no/stor-oslo/","oslo_filter":True},
    {"id":"einnsyn","url":"https://einnsyn.no/rss?q=Oslo+kommune&antall=20",
     "navn":"eInnsyn","badge":"E","farge":"#4a3580","type":"rss","kategori":"einnsyn",
     "max_alder":timedelta(days=7),"link":"https://einnsyn.no","oslo_filter":False},
]

PLACEHOLDER = [
    {"overskrift":"Oslo-guide: Ukens beste turer i Marka","ingress":"Oslomarka tilbyr fine turer for alle nivåer — her er ukens tips.","publisert":_nå().strftime("%-d. %b"),"kilde_url":"https://ut.no","kilde_navn":"ut.no","kilde_tekst":"Les hos ut.no","badge":"T","badge_farge":"#1a6632","kategori":"annet","bilde_url":FB,"brodtekst":[],"sortert_dato":_nå()-timedelta(hours=1)},
    {"overskrift":"Hva skjer i Oslo denne uken?","ingress":"Konserter, utstillinger og markeder — sjekk Visit Oslo for fullt program.","publisert":_nå().strftime("%-d. %b"),"kilde_url":"https://visitoslo.com","kilde_navn":"Visit Oslo","kilde_tekst":"Les hos Visit Oslo","badge":"V","badge_farge":"#1a4f8a","kategori":"annet","bilde_url":IMGS["kommune"],"brodtekst":[],"sortert_dato":_nå()-timedelta(hours=2)},
    {"overskrift":"Ruter: Slik reiser du smartest i Oslo","ingress":"T-bane, trikk og buss dekker hele Oslo. Last ned Ruter-appen for sanntidsinfo.","publisert":_nå().strftime("%-d. %b"),"kilde_url":"https://ruter.no","kilde_navn":"Ruter","kilde_tekst":"Les hos Ruter","badge":"R","badge_farge":"#8a1a1a","kategori":"annet","bilde_url":IMGS["regulering"],"brodtekst":[],"sortert_dato":_nå()-timedelta(hours=3)},
]

# ─── CSS ──────────────────────────────────────────────────────
# Injiseres via st.html() slik at den gjelder globalt i dokumentet.
# CSS-klasser (ikke inline-stiler) brukes på alle bilde-elementer —
# dette er løsningen på at bilder forsvinner på PC i Streamlit.
CSS = """
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,700;1,400&family=Lato:wght@300;400;700;900&display=swap" rel="stylesheet">
<style>
:root{
  --red:   #cd3d33;
  --dark:  #111;
  --body:  #222;
  --soft:  #555;
  --muted: #888;
  --bg:    #ffffff;
  --bg2:   #f8f8f6;
  --card:  #ffffff;
  --brd:   #e8e6e2;
  --shd:   0 1px 3px rgba(0,0,0,.07), 0 4px 14px rgba(0,0,0,.06);
  --shd-h: 0 4px 20px rgba(0,0,0,.14);
  --r:     10px;
  --r-img: 10px 10px 0 0;
}

/* ── Reset ── */
#MainMenu,footer,header{visibility:hidden!important}
.block-container{padding:0!important;max-width:100%!important}
html,body,.stApp{background:var(--bg)!important;font-family:'Lato',sans-serif;color:var(--body)}

/* ── Sidebar ── */
[data-testid="stSidebar"]{background:#111!important;border-right:1px solid #1c1c1c!important}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label{color:#888!important;font-size:.72rem!important;letter-spacing:.04em}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stTextArea textarea,
[data-testid="stSidebar"] .stSelectbox>div>div{background:#1c1c1c!important;color:#ddd!important;border-color:#2e2e2e!important}
[data-testid="stSidebar"] hr{border-color:#1e1e1e!important;margin:.5rem 0!important}
[data-testid="stSidebar"] .stButton>button{
  background:var(--red)!important;color:#fff!important;border:none!important;
  border-radius:6px!important;font-weight:700!important;font-size:.7rem!important;
  letter-spacing:.08em;text-transform:uppercase;width:100%;padding:.5rem!important}
[data-testid="stSidebar"] .stButton>button:hover{opacity:.82!important}

/* ── Header ── */
.mn-hdr{
  background:#fff;border-bottom:3px solid var(--red);
  position:sticky;top:0;z-index:400;
  box-shadow:0 1px 6px rgba(0,0,0,.06)}
.mn-hdr-in{
  max-width:1280px;margin:0 auto;padding:0 1.25rem;
  display:flex;align-items:center;justify-content:space-between;height:56px}
.mn-logo{
  font-family:'Libre Baskerville',Georgia,serif;
  font-size:clamp(1.45rem,3vw,1.9rem);font-weight:700;font-style:italic;
  color:var(--red);letter-spacing:-.03em;text-decoration:none;cursor:pointer}
.mn-logo:hover{opacity:.72}
.mn-logo b{color:var(--dark);font-style:normal}
.mn-dato{font-size:.58rem;color:var(--muted);letter-spacing:.1em;text-transform:uppercase}

/* ── Side ── */
.mn-page{max-width:1280px;margin:0 auto;padding:1.5rem 1.25rem 6rem}

/* ── Seksjonslinje ── */
.mn-sec{
  font-size:.58rem;font-weight:700;letter-spacing:.2em;text-transform:uppercase;
  color:var(--soft);border-top:1.5px solid var(--dark);padding-top:.4rem;margin:1.8rem 0 1rem}
.mn-sec-r{border-top-color:var(--red);color:var(--red)}

/* ── BILDE — CSS-klasse, ikke inline stiler ──────────────────────
   Årsaken til at bilder forsvinner på PC: Streamlit's wide layout
   wrapper ignorerer inline style="height:Xpx" i noen kontekster.
   CSS-klasseregelen her vinner alltid, uansett wrapper.
   ─────────────────────────────────────────────────────────────── */
.mn-img{
  width:100%;
  height:220px;          /* fast høyde — aldri 0 på noe skjerme */
  object-fit:cover;      /* fyller rammen uten strekking          */
  object-position:center;
  display:block;
  border-radius:var(--r-img)}
.mn-img-hero{height:340px}   /* hero-bilde er høyere */
.mn-img-wrap{line-height:0}  /* fjerner whitespace under img */

/* ── Badge ── */
.mn-badge{
  display:inline-block;font-size:.54rem;font-weight:700;letter-spacing:.07em;
  text-transform:uppercase;color:#fff;padding:.18em .5em .2em;border-radius:3px}
.mn-meta{display:flex;align-items:center;gap:.38rem;flex-wrap:wrap;margin-bottom:.28rem}
.mn-dato-liten{font-size:.6rem;color:var(--muted)}
.mn-src{
  font-size:.65rem;color:#1a4f8a;text-decoration:none;
  border-bottom:1px solid #1a4f8a;display:inline-block;
  margin-top:.5rem;transition:opacity .15s}
.mn-src:hover{opacity:.65}

/* ── HERO ── */
.mn-hero{
  background:var(--card);border:1px solid var(--brd);
  border-radius:var(--r);overflow:hidden;
  box-shadow:var(--shd);margin-bottom:1.6rem}
.mn-hero-body{padding:1.3rem 1.6rem 1.6rem}
.mn-hero-ingress{font-size:.97rem;line-height:1.72;color:var(--body);margin:.35rem 0 .6rem}

/* ── GRID: 3 kol desktop, 2 nettbrett, 1 mobil ── */
.mn-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1.1rem;margin-bottom:1.4rem}
.mn-grid-2{display:grid;grid-template-columns:2fr 1fr;gap:1.1rem;margin-bottom:1.1rem}

/* ── KORT ── */
.mn-card{
  background:var(--card);border:1px solid var(--brd);
  border-radius:var(--r);overflow:hidden;
  box-shadow:var(--shd);display:flex;flex-direction:column;
  transition:transform .18s,box-shadow .18s}
.mn-card:hover{transform:translateY(-3px);box-shadow:var(--shd-h)}
.mn-card-body{padding:.9rem 1rem 1rem;flex:1;display:flex;flex-direction:column}
.mn-card-ingress{font-size:.84rem;line-height:1.62;color:var(--body);flex:1;margin-top:.28rem}

/* ── Artikkelknapper som titler ──────────────────────────────────
   font-weight:900 + color:var(--dark) gir fete, svarte overskrifter.
   Ingen z-index/overflow:hidden — forhindrer klikk-blokkering.
   ─────────────────────────────────────────────────────────────── */
.stButton>button{
  background:transparent!important;
  color:var(--dark)!important;        /* svart overskrift */
  border:none!important;border-radius:0!important;
  font-family:'Libre Baskerville',Georgia,serif!important;
  font-size:clamp(.95rem,2vw,1.07rem)!important;
  font-weight:700!important;          /* fet */
  font-style:normal!important;
  line-height:1.22!important;
  text-align:left!important;padding:0!important;
  width:100%!important;white-space:normal!important;
  height:auto!important;cursor:pointer!important;
  min-height:44px!important}          /* iOS touch target */
.stButton>button:hover{color:var(--red)!important}
.stButton>button:focus{box-shadow:none!important;outline:none!important}

/* ── Politilogg ── */
.mn-pol{background:#05101f;border:1px solid #0d2040;border-radius:var(--r);padding:1rem}
.mn-pol-hdr{
  font-size:.58rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;
  color:var(--red);display:flex;align-items:center;gap:.38rem;margin-bottom:.7rem}
.mn-dot{width:6px;height:6px;border-radius:50%;background:var(--red);animation:p 1.4s infinite;flex-shrink:0}
@keyframes p{0%,100%{opacity:1}50%{opacity:.1}}
.mn-pi{background:#081828;border:1px solid #112240;border-radius:8px;padding:.6rem .78rem;margin-bottom:.4rem}
.mn-pi-t{font-size:.57rem;color:var(--red);font-weight:700;margin-bottom:.12rem}
.mn-pi-x{font-size:.8rem;color:#c8dfff;line-height:1.5}
.mn-pi-s{font-size:.6rem;color:#4a7aaa;margin-top:.1rem}
.mn-pi-a{font-size:.6rem;color:#4a8fd4;margin-top:.25rem;text-decoration:none;border-bottom:1px solid #4a8fd4;display:inline}

/* ── Artikkelvisning ── */
.mn-art{background:var(--card);border:1px solid var(--brd);border-radius:var(--r);padding:2rem;box-shadow:var(--shd);margin-top:.75rem}
.mn-art h1{font-family:'Libre Baskerville',serif;font-size:clamp(1.5rem,4vw,2.4rem);font-weight:700;line-height:1.1;color:var(--dark);margin-bottom:.9rem}
.mn-art-lead{font-size:1.03rem;line-height:1.76;color:var(--body);border-left:4px solid var(--red);padding-left:1rem;margin-bottom:1.5rem}
.mn-art-p{font-size:.97rem;line-height:1.88;color:var(--body);margin-bottom:.9rem}
.mn-art-kilde{margin-top:1.3rem;padding-top:.8rem;border-top:1px solid var(--brd)}
.mn-art-kilde a{display:inline-block;background:#1a4f8a;color:#fff;padding:.4rem .85rem;border-radius:6px;font-size:.72rem;font-weight:700;text-decoration:none}

/* ── Responsivt ── */
@media(max-width:768px){
  .mn-grid,.mn-grid-2{grid-template-columns:1fr!important}
  .mn-page{padding:.7rem .7rem 4rem}
  .mn-hdr-in{padding:0 .85rem}
  .mn-hero-body,.mn-card-body{padding:.85rem}
  .mn-art{padding:1.1rem}
  .mn-img-hero{height:220px}
  html{touch-action:manipulation}
}
@media(min-width:769px) and (max-width:1100px){
  .mn-grid{grid-template-columns:repeat(2,1fr)!important}
  .mn-grid-2{grid-template-columns:3fr 2fr!important}
}
</style>
"""

# ─── HJELPERE ─────────────────────────────────────────────────
def _rens(t:str)->str:
    if not t: return ""
    t=_html.unescape(t); t=re.sub(r"<[^>]+>"," ",t)
    return re.sub(r"\s{2,}"," ",t).strip()

def _dato(s:str)->datetime|None:
    if not s: return None
    for f in ("%a, %d %b %Y %H:%M:%S %z","%a, %d %b %Y %H:%M:%S GMT",
              "%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%SZ",
              "%Y-%m-%dT%H:%M:%S.%f%z","%Y-%m-%d"):
        try:
            dt=datetime.strptime(s.strip(),f)
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(_TZ)
        except: pass
    try: return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(_TZ)
    except: return None

def _gammel(dt,max_a)->bool: return bool(dt and dt<_nå()-max_a)
def _dstr(dt,raa="")->str: return dt.strftime("%-d. %b %Y, %H:%M") if dt else raa[:10] or "–"

def _oslo_ok(tittel:str,desc:str)->bool:
    t=f"{tittel} {desc}"
    if EKSKL.search(t): return False
    return bool(OSLO_RE.search(t))

# ─── BILDER ───────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _kart(adresse:str)->str|None:
    """Nominatim → statisk PNG-kart. Ikke interaktivt — bare et bilde."""
    try:
        r=requests.get("https://nominatim.openstreetmap.org/search",
                       params={"q":f"{adresse}, Oslo, Norway","format":"json","limit":1},
                       headers=OSM_UA,timeout=3)
        h=r.json()
        if not h: return None
        lat,lon=float(h[0]["lat"]),float(h[0]["lon"])
        return (f"https://staticmap.openstreetmap.de/staticmap.php"
                f"?center={lat},{lon}&zoom=16&size=800x450&markers={lat},{lon},red-pushpin")
    except: return None

def _bilde(art:dict)->dict:
    if art.get("bilde_url","").startswith("http"): return art
    t=f"{art.get('overskrift','')} {art.get('ingress','')}"
    for gate in GATE_RE.findall(t):
        url=_kart(gate)
        if url: return {**art,"bilde_url":url}
    return {**art,"bilde_url":IMGS.get(art.get("kategori","annet"),FB)}

def _img(art:dict,ekstra_cls:str="")->str:
    """
    Returnerer <img class="mn-img [ekstra_cls]">.
    CSS-klassen (ikke inline-stil) sikrer synlige bilder på PC.
    onerror garanterer at fallback alltid vises.
    """
    url=art.get("bilde_url") or FB
    kls=f"mn-img {ekstra_cls}".strip()
    return (f'<div class="mn-img-wrap">'
            f'<img src="{url}" class="{kls}" alt="" '
            f'onerror="this.src=\'{FB}\';this.onerror=null;">'
            f'</div>')

# ─── DATAHENTING ──────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _hent_politi(kilde:dict)->tuple[list,str]:
    try:
        r=requests.get(kilde["url"],headers=HDRS,timeout=TIMEOUT); r.raise_for_status()
        raw=r.json()
        items=raw if isinstance(raw,list) else (raw.get("meldinger") or raw.get("data") or [])
        ut=[]
        for m in items:
            tittel=_rens(m.get("tittel") or m.get("title") or "")
            tekst =_rens(m.get("tekst")  or m.get("text")  or m.get("description") or "")
            tidsp =m.get("tidspunkt") or m.get("publishedOn") or m.get("created") or ""
            sted  =_rens(m.get("sted") or m.get("location") or "Oslo")
            url   =m.get("url") or m.get("link") or kilde["link"]
            dt=_dato(tidsp)
            if _gammel(dt,kilde["max_alder"]): continue
            if not _oslo_ok(tittel,tekst): continue
            ut.append({"tittel":tittel or tekst[:60] or "Politimelding","tekst":tekst or tittel,
                       "tid":_dstr(dt,tidsp),"sted":sted,"url":url,
                       "sortert_dato":dt or (_nå()-timedelta(hours=12))})
        ut.sort(key=lambda x:x["sortert_dato"],reverse=True)
        return ut[:20],""
    except requests.exceptions.Timeout: return [],f"Timeout {TIMEOUT}s"
    except Exception as e: return [],f"{type(e).__name__}: {e}"

@st.cache_data(ttl=300, show_spinner=False)
def _hent_rss(kilde:dict)->tuple[list,str]:
    xml,feil="",""
    for url in [kilde["url"]]+kilde.get("url_alt",[]):
        try:
            r=requests.get(url,headers=HDRS,timeout=TIMEOUT)
            if r.ok and "<" in r.text: xml=r.text; break
            feil=f"HTTP {r.status_code}"
        except requests.exceptions.Timeout: feil=f"Timeout {TIMEOUT}s"
        except Exception as e: feil=f"{type(e).__name__}: {e}"
    if not xml: return [],feil or "Ingen URL svarte"
    try:
        soup=BeautifulSoup(xml,"lxml-xml")
        items=soup.find_all("item") or soup.find_all("entry")
        ut=[]
        for item in items:
            def g(*tags):
                for t in tags:
                    n=item.find(t)
                    if n and n.get_text(strip=True): return _rens(n.get_text())
                return ""
            tittel=g("title");
            if not tittel: continue
            desc=g("description","summary","content")
            pub =g("pubDate","published","updated","dc:date")
            lnk =g("link")
            if not lnk:
                lt=item.find("link")
                if lt: lnk=lt.get("href","") or _rens(lt.get_text())
            dt=_dato(pub)
            if _gammel(dt,kilde["max_alder"]): continue
            if kilde.get("oslo_filter") and not _oslo_ok(tittel,desc): continue
            sam=desc[:260].rstrip()+"…" if len(desc)>260 else desc
            art={"overskrift":tittel,"ingress":sam,"brodtekst":[],
                 "publisert":_dstr(dt,pub),"kilde_url":lnk or kilde["link"],
                 "kilde_navn":kilde["navn"],"kilde_tekst":f"Les hos {kilde['navn']}",
                 "badge":kilde["badge"],"badge_farge":kilde["farge"],
                 "kategori":kilde.get("kategori","annet"),"bilde_url":"",
                 "sortert_dato":dt or (_nå()-timedelta(hours=6))}
            ut.append(_bilde(art))
        ut.sort(key=lambda x:x["sortert_dato"],reverse=True)
        return ut[:14],""
    except Exception as e: return [],f"Parse: {type(e).__name__}: {e}"

def _hent_alt()->tuple[list,list,dict]:
    politi,nyheter,dbg=[],[],{}
    for k in KILDER:
        if k["type"]=="politi":
            d,f=_hent_politi(k)
            dbg[k["navn"]]={"ok":not f,"feil":f,"n":len(d),"url":k["url"]}
            politi.extend(d)
        else:
            d,f=_hent_rss(k)
            dbg[k["navn"]]={"ok":not f,"feil":f,"n":len(d),"url":k["url"]}
            for a in d:
                a.setdefault("badge",k["badge"]); a.setdefault("badge_farge",k["farge"])
            nyheter.extend(d)
    nyheter.sort(key=lambda x:x.get("sortert_dato",_nå()-timedelta(days=7)),reverse=True)
    return politi,nyheter,dbg

# ─── UI-HELPERS ───────────────────────────────────────────────
def _badge(a:dict)->str:
    return f'<span class="mn-badge" style="background:{a.get("badge_farge","#555")}">{a.get("badge","?")} {a.get("kilde_navn","")}</span>'

def _meta(a:dict)->str:
    d=a.get("publisert","")
    return f'<div class="mn-meta">{_badge(a)}'+( f'<span class="mn-dato-liten">{d}</span>' if d else "")+"</div>"

def _kilde(a:dict,stor=False)->str:
    url=a.get("kilde_url","#"); tx=a.get("kilde_tekst") or f"Les hos {a.get('kilde_navn','Kilde')}"
    if stor: return f'<div class="mn-art-kilde"><a href="{url}" target="_blank">📎 {tx}</a></div>'
    return f'<a href="{url}" target="_blank" class="mn-src">↗ {tx}</a>'

def _politi_html(ml:list)->str:
    if not ml:
        return ('<div class="mn-pol" style="text-align:center;padding:1.5rem">'
                '<p style="color:#5a7fa8;font-size:.82rem">Ingen meldinger siste 24t.</p>'
                '<a href="https://politiloggen.politiet.no" target="_blank" style="color:#4a8fd4;font-size:.75rem">↗ Se politiloggen direkte</a></div>')
    items="".join(
        f'<div class="mn-pi"><div class="mn-pi-t">🚔 {p["tid"]} · {p["sted"]}</div>'
        f'<div class="mn-pi-x">{p["tekst"][:200]}{"…" if len(p["tekst"])>200 else ""}</div>'
        f'<a href="{p["url"]}" target="_blank" class="mn-pi-a">↗ Les hos Politiloggen</a></div>'
        for p in ml)
    return (f'<div class="mn-pol"><div class="mn-pol-hdr"><div class="mn-dot"></div>'
            f'LIVE — OSLO POLITIDISTRIKT (siste 24t)</div>{items}'
            f'<p style="font-size:.56rem;color:#3a5a80;margin-top:.55rem;text-align:center">'
            f'<a href="https://politiloggen.politiet.no" target="_blank" style="color:#4a8fd4">↗ Alle meldinger</a></p></div>')

# ─── MAIN ─────────────────────────────────────────────────────
def main():
    for k,v in [("dark",False),("manuell",[]),("valgt",None),("admin",False)]:
        if k not in st.session_state: st.session_state[k]=v

    # CSS injiseres globalt via st.html() — nøkkelen til synlige bilder på PC
    st.html(CSS)

    # ── Sidebar ────────────────────────────────────────────────
    with st.sidebar:
        st.markdown('<p style="font-family:\'Libre Baskerville\',serif;font-size:1.45rem;'
                    'font-weight:700;font-style:italic;color:#cd3d33;margin:.12rem 0 0">'
                    'MinOslo</p>'
                    '<p style="font-size:.54rem;color:#555;margin:0 0 .2rem;'
                    'letter-spacing:.1em;text-transform:uppercase">Oslo i dag</p>',
                    unsafe_allow_html=True)
        st.markdown("---")

        st.markdown('<p style="font-size:.58rem;font-weight:700;letter-spacing:.15em;'
                    'text-transform:uppercase;color:#cd3d33;margin-bottom:.28rem">🔒 Admin</p>',
                    unsafe_allow_html=True)
        if not st.session_state.admin:
            pw=st.text_input("Passord",type="password",placeholder="Passord…",label_visibility="collapsed")
            if st.button("Logg inn",key="login",use_container_width=True):
                if pw==ADMIN_PW: st.session_state.admin=True; st.rerun()
                elif pw: st.markdown('<p style="color:#e8001f;font-size:.68rem">✗ Feil passord</p>',unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#4caf50;font-size:.68rem;margin-bottom:.4rem">✓ Innlogget</p>',unsafe_allow_html=True)
            with st.expander("📌 Ny topsak",expanded=True):
                with st.form("nysak",clear_on_submit=True):
                    t=st.text_input("Tittel *"); i=st.text_area("Ingress *",height=55)
                    bd=st.selectbox("Bydel",BYDELER[1:]); kat=st.selectbox("Kategori",KATEGORIER[1:])
                    img=st.text_input("Bilde-URL (valgfritt)"); src=st.text_input("Kilde-URL"); sn=st.text_input("Kilde-navn")
                    if st.form_submit_button("📌 Publiser"):
                        if t.strip() and i.strip():
                            a={"overskrift":t.strip(),"ingress":i.strip(),"brodtekst":[],"kilde_url":src.strip() or "#",
                               "kilde_navn":sn.strip() or "Redaksjonen","kilde_tekst":f"Les hos {sn.strip() or 'Redaksjonen'}",
                               "badge":"★","badge_farge":"#8a1a1a","kategori":kat,"bilde_url":img.strip(),
                               "publisert":_nå().strftime("%-d. %b %Y, %H:%M"),"sortert_dato":_nå()}
                            st.session_state.manuell.insert(0,_bilde(a)); st.success("✓"); st.rerun()
                        else: st.warning("Tittel og ingress er påkrevd.")
            if st.button("Logg ut",key="logout",use_container_width=True):
                st.session_state.admin=False; st.rerun()

        st.markdown("---")
        bydel=st.selectbox("Bydel",BYDELER,label_visibility="collapsed",key="fb")
        kat  =st.selectbox("Kategori",KATEGORIER,label_visibility="collapsed",key="fk")
        st.markdown("---")
        if st.button("🔄 Oppdater",key="oppdater",use_container_width=True):
            st.cache_data.clear(); st.session_state.valgt=None; st.rerun()
        st.caption(f"Cache 5 min · {_nå().strftime('%H:%M')}")

    # ── Header ─────────────────────────────────────────────────
    dato=_nå().strftime("%-d. %B %Y")
    st.markdown(
        f'<div class="mn-hdr"><div class="mn-hdr-in">'
        f'<a class="mn-logo" href="javascript:void(0)" onclick="window.location.reload()">'
        f'Min<b>Oslo</b></a>'
        f'<span class="mn-dato">{dato}</span>'
        f'</div></div>',
        unsafe_allow_html=True)

    st.markdown('<div class="mn-page">',unsafe_allow_html=True)

    # ── Artikkelvisning ────────────────────────────────────────
    if st.session_state.valgt:
        a=st.session_state.valgt
        if st.button("← Tilbake"): st.session_state.valgt=None; st.rerun()
        st.markdown(_img(a,"mn-img-hero"),unsafe_allow_html=True)
        st.markdown('<div class="mn-art">',unsafe_allow_html=True)
        st.markdown(_meta(a),unsafe_allow_html=True)
        st.markdown(f'<h1>{a["overskrift"]}</h1>',unsafe_allow_html=True)
        st.markdown(f'<div class="mn-art-lead">{a["ingress"]}</div>',unsafe_allow_html=True)
        for avsnitt in a.get("brodtekst",[]):
            st.markdown(f'<p class="mn-art-p">{avsnitt}</p>',unsafe_allow_html=True)
        st.markdown(_kilde(a,stor=True),unsafe_allow_html=True)
        st.markdown("</div></div>",unsafe_allow_html=True)
        return

    # ── Hent data (etter header er synlig) ─────────────────────
    with st.spinner("Henter siste nyheter fra Oslo…"):
        politi,nyheter,dbg=_hent_alt()

    alle=list(st.session_state.manuell)+nyheter
    if not alle: alle=list(PLACEHOLDER)

    # Filtrer
    vis=list(alle)
    if bydel!="Alle bydeler": vis=[a for a in vis if a.get("bydel")==bydel]
    if kat!="Alle kategorier": vis=[a for a in vis if a.get("kategori")==kat]
    if not vis: vis=list(alle)

    # ── Tabs ───────────────────────────────────────────────────
    t_ny,t_pol=st.tabs(["📰 Nyheter","🚔 Politilogg"])

    with t_pol:
        st.markdown('<div class="mn-sec mn-sec-r" style="margin-top:0">Politilogg — Oslo (siste 24 timer)</div>',unsafe_allow_html=True)
        st.markdown(_politi_html(politi),unsafe_allow_html=True)
        if st.session_state.admin:
            d=dbg.get("Politiloggen",{})
            st.caption(f"⚙️ {d.get('url','?')} | {d.get('n',0)} meldinger | {d.get('feil') or 'OK'}")

    with t_ny:
        st.markdown('<div class="mn-sec mn-sec-r" style="margin-top:0">Siste nytt fra Oslo</div>',unsafe_allow_html=True)

        if not vis:
            st.info("Ingen saker funnet. Prøv 'Alle bydeler'.")
        else:
            # Hero — første sak, full bredde
            h=vis[0]
            st.markdown('<div class="mn-hero">',unsafe_allow_html=True)
            st.markdown(_img(h,"mn-img-hero"),unsafe_allow_html=True)
            st.markdown('<div class="mn-hero-body">',unsafe_allow_html=True)
            st.markdown(_meta(h),unsafe_allow_html=True)
            if st.button(h["overskrift"],key="hero"):
                st.session_state.valgt=h; st.rerun()
            st.markdown(f'<p class="mn-hero-ingress">{h["ingress"]}</p>',unsafe_allow_html=True)
            st.markdown(_kilde(h),unsafe_allow_html=True)
            st.markdown("</div></div>",unsafe_allow_html=True)

            # 2-wide: sak 2 og 3
            if len(vis)>=3:
                st.markdown('<div class="mn-grid-2">',unsafe_allow_html=True)
                for a in vis[1:3]:
                    st.markdown('<div class="mn-card">',unsafe_allow_html=True)
                    st.markdown(_img(a),unsafe_allow_html=True)
                    st.markdown('<div class="mn-card-body">',unsafe_allow_html=True)
                    st.markdown(_meta(a),unsafe_allow_html=True)
                    if st.button(a["overskrift"],key=f"w{id(a)}"):
                        st.session_state.valgt=a; st.rerun()
                    k=a["ingress"][:165]+("…" if len(a["ingress"])>165 else "")
                    st.markdown(f'<p class="mn-card-ingress">{k}</p>',unsafe_allow_html=True)
                    st.markdown(_kilde(a),unsafe_allow_html=True)
                    st.markdown("</div></div>",unsafe_allow_html=True)
                st.markdown("</div>",unsafe_allow_html=True)

            # 3-kolonne grid: resten
            rest=vis[3:]
            if rest:
                st.markdown('<div class="mn-sec">Flere saker</div>',unsafe_allow_html=True)
                st.markdown('<div class="mn-grid">',unsafe_allow_html=True)
                for a in rest:
                    st.markdown('<div class="mn-card">',unsafe_allow_html=True)
                    st.markdown(_img(a),unsafe_allow_html=True)
                    st.markdown('<div class="mn-card-body">',unsafe_allow_html=True)
                    st.markdown(_meta(a),unsafe_allow_html=True)
                    if st.button(a["overskrift"],key=f"g{id(a)}"):
                        st.session_state.valgt=a; st.rerun()
                    k=a["ingress"][:128]+("…" if len(a["ingress"])>128 else "")
                    st.markdown(f'<p class="mn-card-ingress">{k}</p>',unsafe_allow_html=True)
                    st.markdown(_kilde(a),unsafe_allow_html=True)
                    st.markdown("</div></div>",unsafe_allow_html=True)
                st.markdown("</div>",unsafe_allow_html=True)

            # Mini politilogg-stripe
            st.markdown('<div class="mn-sec mn-sec-r">Politilogg — siste meldinger</div>',unsafe_allow_html=True)
            st.markdown(_politi_html(politi[:5]),unsafe_allow_html=True)

            # Debug (kun admin)
            if st.session_state.admin:
                with st.expander("⚙️ Debug",expanded=False):
                    for n,d in dbg.items():
                        st.write(f"{'✅' if d['ok'] else '❌'} **{n}** — {d['n']} saker")
                        st.code(d["url"])
                        if d["feil"]: st.error(d["feil"])
                    st.caption(f"Tid: {_nå().strftime('%H:%M:%S')} | Cache: 300s")

    st.markdown("</div>",unsafe_allow_html=True)

if __name__=="__main__":
    main()
