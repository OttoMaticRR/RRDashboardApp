
import json
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px

import gspread
from google.oauth2.service_account import Credentials
import streamlit_authenticator as stauth
from streamlit_autorefresh import st_autorefresh
import locale
NOR_MONTHS = [
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember"
]

def format_no_date(d):
    """Returner '3. oktober 2025' for en date/datetime (norsk, uten locale)."""
    if d is None:
        return "-"
    # pandas NaT-sjekk
    try:
        import pandas as pd
        if pd.isna(d):
            return "-"
    except Exception:
        pass
    from datetime import datetime, date
    if isinstance(d, datetime):
        d = d.date()
    day = d.day
    month = NOR_MONTHS[d.month - 1]
    year = d.year
    return f"{day}. {month} {year}"

  
# ----------------------------
# Page config
# ----------------------------
st.set_page_config(
    page_title="Retail Repair Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"   # <- VIKTIG
)

# --- Globalt design-tema (farger/typografi) ---
ACCENT = "#e73f3f"  # samme som menyen
st.markdown(f"""
<style>
:root {{
  --accent: {ACCENT};
  --text: #0f1115;
  --muted: #6b7280;
  --card-bg: rgba(255,255,255,0.04);
  --card-bd: rgba(255,255,255,0.10);
}}

/* Global font/antialias */
html, body, [data-testid="stAppViewContainer"] * {{
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--text);
}}

/* Overskrifter */
h1, h2, h3 {{
  letter-spacing: .2px;
  line-height: 1.15;
}}

/* Understrek (accent) på seksjons-overskrifter */
.block-header {{
  display:flex; align-items:center; gap:.6rem; margin: .25rem 0 1rem 0;
}}
.block-header .dot {{
  width:10px; height:10px; border-radius:50%; background: var(--accent);
  box-shadow: 0 0 0 4px rgba(231,63,63,.12);
}}
.block-header h2, .block-header h3 {{ margin:0; }}
</style>
""", unsafe_allow_html=True)


# All CSS i ÉN blokk (IKKE fler st.markdown med <style> under)
css = '''
<style>
/* ————— SLANK HEADER (la den være synlig slik at burgeren kan vises) ————— */
header[data-testid="stHeader"]{
  background: transparent;
  height: 2rem;          /* tynn */
  min-height: 2rem;
}

/* Ikke skjul toolbaren – la Streamlit håndtere den. */
main .block-container{
  padding-top: .2rem;
  margin-top: -.6rem;    /* justér ved behov (mer negativt = mindre luft) */
}

/* Dato høyre */
.date-right{ text-align:right; font-size:1rem; margin:0; padding-top:.2rem; }

/* KPI-kort */
div[data-testid="stMetric"]{
  min-height:150px; height:150px;
  display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center;
  background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08);
  border-radius:12px; padding:16px 18px; box-shadow:0 6px 16px rgba(0,0,0,.25);
}
div[data-testid="stMetricValue"]{ font-size:2.2rem; font-weight:700; text-align:center; width:100%; }
div[data-testid="stMetricLabel"]{ font-size:.95rem; opacity:.9; text-align:center; width:100%; }

/* Cards for grafer/tabeller */
.rr-card{
  background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08);
  border-radius:12px; padding:16px; box-shadow:0 6px 16px rgba(0,0,0,.25); margin-bottom:1rem;
}
.stPlotlyChart, .plotly, .js-plotly-plot{ background:transparent !important; }

/* Slankere, moderne kort (flyttet INNI <style>) */
.rr-card, [data-testid="stContainer"] > div:has(> .rr-card-inner) { 
  background: var(--card-bg);
  border: 1px solid var(--card-bd);
  border-radius: 14px;
  box-shadow: 0 8px 18px rgba(0,0,0,.18);
  padding: 14px 16px;
}
.rr-card-inner { margin: 0; }
</style>
'''
st.markdown(css, unsafe_allow_html=True)



# --- KONSTANTER (må komme før de brukes) ---
TITLE = "Retail Repair Dashboard"
BRAND_COLS = ["Merke", "Product brand", "Brand"]
TECH_COLS  = ["Tekniker", "Service technician", "Technician"]

# Felles kandidater (robust på kolonnenavn)
BRAND_COLS = ["Merke", "Product brand", "Brand"]
STATUS_COLS = ["Statustekst", "Status", "Repair status", "State"]
DATE_COLS   = ["Statusdato", "Dato", "Innlevert", "Received date", "Date"]

# Hvilke arkfaner (kan overstyres i secrets)
WORKSHEET_REPARERT   = st.secrets.get("worksheet", "Sheet1")
WORKSHEET_INNLEVERT  = st.secrets.get("worksheet_innlevert", "Sheet2")
WORKSHEET_INHOUSE    = st.secrets.get("worksheet_inhouse", "Sheet3")  # NY
WORKSHEET_ARBEIDET   = st.secrets.get("worksheet_arbeidet", "Sheet5")

# Kompakt layout + kort-stil (uthev hver kolonne/boks)
st.markdown("""
<style>
  /* KPI-bokser (st.metric) som "cards" + lik høyde og midtjustert innhold */
  div[data-testid="stMetric"]{
    background: rgba(255,255,255,0.03);     
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 6px 16px rgba(0,0,0,0.25);
    min-height: 150px;            /* fast høyde */
    height: 150px;                /* tving samme høyde */
    display: flex;
    flex-direction: column;
    justify-content: center;      /* vertikalt sentrert */
    align-items: center;          /* horisontalt sentrert */
    text-align: center;
  }

  /* KPI-verdier (store tall) */
  div[data-testid="stMetricValue"] { 
    font-size: 2.2rem; 
    font-weight: 700;
    text-align: center;
    width: 100%;
  }

  /* KPI-labels */
  div[data-testid="stMetricLabel"] {
    font-size: 0.95rem;
    opacity: 0.9;
    text-align: center;
    width: 100%;
  }
</style>
""", unsafe_allow_html=True)


# Auto-refresh every 5 minutes
st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh_5min")

# ----------------------------
# Authentication
# ----------------------------
auth_cfg = st.secrets.get("auth", {})
credentials_dict = {"usernames": {}}
for user in auth_cfg.get("credentials", []):
    credentials_dict["usernames"][user["username"]] = {
        "name": user.get("name", user["username"]),
        "password": user["password"],
        "role": user.get("role", "viewer"),
    }

authenticator = stauth.Authenticate(
    credentials_dict,
    auth_cfg.get("cookie_name", "repair_dash_cookie"),
    auth_cfg.get("signature_key", "CHANGE_ME"),
    auth_cfg.get("cookie_expiry_days", 7),
)

# Vis skjema (ny API: login() returnerer ingenting, men setter session_state)
authenticator.login(location="main", fields={"Form name": "Login"})

# Les status fra session_state
auth_status = st.session_state.get("authentication_status", None)
name       = st.session_state.get("name", None)
username   = st.session_state.get("username", None)

if auth_status is None:
    # Skjemaet er vist, men bruker har ikke (eller feil) sendt inn ennå
    st.stop()
elif auth_status is False:
    st.error("Invalid username/password")
    st.stop()
# Hvis True, fortsetter appen videre

# ----------------------------
# Google Sheets helpers (+ støtte for Innlevert)
# ----------------------------

# Kolonnenavn som kan forekomme for dato i "Innlevert"
DATE_COLS = ["Innlevert", "Received date", "Date"]

@st.cache_resource(show_spinner=False)
def gspread_client():
    svc_raw = st.secrets.get("gcp_service_account")
    if isinstance(svc_raw, str):
        svc_info = json.loads(svc_raw)
    elif isinstance(svc_raw, dict):
        svc_info = svc_raw
    else:
        st.error("Missing gcp_service_account in secrets.")
        st.stop()

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(svc_info, scopes=scopes)
    return gspread.authorize(creds)


@st.cache_data(ttl=300, show_spinner=False)  # 5 min cache – juster fritt
def read_df():
    """Les data for 'Reparert' fra worksheet WORKSHEET_REPARERT (default Sheet1)."""
    gc = gspread_client()
    sh = gc.open_by_key(st.secrets.get("sheet_id"))
    ws = sh.worksheet(WORKSHEET_REPARERT)
    rows = ws.get_all_records()
    if not rows:
        return pd.DataFrame(columns=["Merke", "Tekniker"])
    return pd.DataFrame(rows)


@st.cache_data(ttl=300, show_spinner=False)
def read_df_innlevert():
    """Les 'Innlevert' fra WORKSHEET_INNLEVERT (default Sheet2)."""
    gc = gspread_client()
    sh = gc.open_by_key(st.secrets.get("sheet_id"))
    ws = sh.worksheet(WORKSHEET_INNLEVERT)
    rows = ws.get_all_records()
    if not rows:
        return pd.DataFrame(columns=["Merke", "Innlevert"])

    df = pd.DataFrame(rows)

    # Finn aktuelle kolonner
    def pick(cands, df_):
        for c in cands:
            if c in df_.columns:
                return c
        return None

    bcol = pick(BRAND_COLS, df) or "Merke"
    dcol = pick(DATE_COLS,  df) or "Innlevert"

    # Rens og robust dato-parsing
    df[bcol] = df[bcol].astype(str).str.strip()
    dates = pd.to_datetime(df[dcol], errors="coerce", dayfirst=True, infer_datetime_format=True)
    needs_excel = dates.isna()
    if needs_excel.any():
        as_num = pd.to_numeric(df.loc[needs_excel, dcol], errors="coerce")
        conv = pd.to_datetime(as_num, errors="coerce", unit="D", origin="1899-12-30")
        dates.loc[needs_excel] = conv
    df[dcol] = dates.dt.date

    df = df[(df[bcol] != "") & df[dcol].notna()]
    out = df[[bcol, dcol]].copy()
    out.columns = ["Merke", "Innlevert"]
    return out


@st.cache_data(ttl=300, show_spinner=False)
def read_df_inhouse():
    """Les 'Inhouse' fra WORKSHEET_INHOUSE.
       Forventer A=Merke, B=Statustekst, C=Statusdato (tekst eller Excel-seriedato)."""
    gc = gspread_client()
    sh = gc.open_by_key(st.secrets.get("sheet_id"))
    ws = sh.worksheet(WORKSHEET_INHOUSE)
    rows = ws.get_all_records()
    if not rows:
        return pd.DataFrame(columns=["Merke", "Status", "Dato"])

    df = pd.DataFrame(rows)

    # Case-insensitive plukking av kolonner
    colmap = {c.lower().strip(): c for c in df.columns}

    def pick_casefold(cands):
        for cand in cands:
            real = colmap.get(cand.lower())
            if real:
                return real
        return None

    brand_col  = pick_casefold(["Merke", "Product brand", "Brand"])
    status_col = pick_casefold(["Statustekst", "Status", "Repair status", "State"])
    date_col   = pick_casefold(["Statusdato", "Dato", "Innlevert", "Received date", "Date"])

    # Snill feilmelding hvis noe mangler
    missing = []
    if brand_col is None:  missing.append("Merke")
    if status_col is None: missing.append("Statustekst")
    if date_col is None:   missing.append("Statusdato")
    if missing:
        raise KeyError(", ".join(missing))

    # Rens / normaliser
    df[brand_col]  = df[brand_col].astype(str).str.strip()
    df[status_col] = df[status_col].astype(str).str.strip()

    # Robust dato-parsing
    dates = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True, infer_datetime_format=True)
    needs_excel = dates.isna()
    if needs_excel.any():
        as_num = pd.to_numeric(df.loc[needs_excel, date_col], errors="coerce")
        conv = pd.to_datetime(as_num, errors="coerce", unit="D", origin="1899-12-30")
        dates.loc[needs_excel] = conv
    df[date_col] = dates.dt.date

    df = df[(df[brand_col] != "") & (df[status_col] != "") & df[date_col].notna()].copy()

    # Standardiser ut-kolonner
    out = df[[brand_col, status_col, date_col]].copy()
    out.columns = ["Merke", "Status", "Dato"]
    return out
    
@st.cache_data(ttl=300, show_spinner=False)
def read_df_arbeidet():
    """
    Leser dagens arbeid fra WORKSHEET_ARBEIDET (Sheet5).
    Forventer minst tre kolonner (variasjoner håndteres case-insensitivt):
      - Merker  (f.eks 'Merker', 'Merke', 'Brand')
      - Status  (f.eks 'Statusteks', 'Statustekst', 'Status')
      - Tekniker (f.eks 'Tekniker', 'Technician', 'Service technician')
    Returnerer alltid kolonnene: Merke, Status, Tekniker
    """
    gc = gspread_client()
    sh = gc.open_by_key(st.secrets.get("sheet_id"))
    ws = sh.worksheet(WORKSHEET_ARBEIDET)

    values = ws.get_all_values()
    if not values or len(values) < 2:
        return pd.DataFrame(columns=["Merke", "Status", "Tekniker"])

    header = [h.strip() for h in values[0]]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=header)

    # Case-insensitive mapping
    colmap = {c.lower().strip(): c for c in df.columns}

    def pick_casefold(cands):
        for cand in cands:
            real = colmap.get(cand.lower())
            if real:
                return real
        return None

    brand_col = pick_casefold(["Merker", "Merke", "Brand"])
    status_col = pick_casefold(["Statusteks", "Statustekst", "Status"])
    tech_col = pick_casefold(["Tekniker", "Technician", "Service technician"])

    if brand_col is None or status_col is None or tech_col is None:
        # Returner tomt i riktig format (unngå krasj i UI)
        return pd.DataFrame(columns=["Merke", "Status", "Tekniker"])

    # Rens litt
    df[brand_col] = df[brand_col].astype(str).str.strip()
    df[status_col] = df[status_col].astype(str).str.strip()
    df[tech_col] = df[tech_col].astype(str).str.strip()

    out = df[[brand_col, status_col, tech_col]].copy()
    out.columns = ["Merke", "Status", "Tekniker"]
    # Filtrer bort helt blanke rader
    out = out[(out["Merke"] != "") | (out["Status"] != "") | (out["Tekniker"] != "")]
    return out.reset_index(drop=True)


# ----------------------------
# Navigasjon (sidebar) + Header
# ----------------------------
# --- Custom sidebar-meny (tekst = svart, åpner i samme fane) ---
qp = st.query_params
view = qp.get("view") or "Reparert"
if isinstance(view, list):
    view = view[0]

st.sidebar.markdown(f"""
<style>
.sidebar-menu {{
  font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  margin-top: 6px;
}}
.sidebar-menu .menu-item {{
  display: flex; align-items: center; gap: 10px;
  color: #111 !important; text-decoration: none;
  padding: 10px 14px; border-radius: 10px;
  transition: all .18s ease-in-out;
}}
.sidebar-menu .menu-item:hover {{
  background: rgba(0,0,0,0.07);
  color: #000 !important;
}}
.sidebar-menu .menu-item.active {{
  background: #e73f3f;
  color: #000 !important;
  box-shadow: 0 6px 16px rgba(231,63,63,.35);
}}
.sidebar-menu .emoji {{
  width: 20px; display: inline-flex; justify-content: center;
}}
</style>

<div class="sidebar-menu">
  <a href="?view=Reparert"  target="_self" class="menu-item{' active' if view=='Reparert'  else ''}">
    <span class="emoji">🧰</span> Reparert
  </a>
  <a href="?view=Innlevert" target="_self" class="menu-item{' active' if view=='Innlevert' else ''}">
    <span class="emoji">📦</span> Innlevert
  </a>
  <a href="?view=Inhouse"   target="_self" class="menu-item{' active' if view=='Inhouse'   else ''}">
    <span class="emoji">🏠</span> Inhouse
  </a>
    <a href="?view=Arbeidet" target="_self" class="menu-item{' active' if view=='Arbeidet' else ''}">
    <span class="emoji">🛠️</span> Arbeidet på
  </a>
</div>
""", unsafe_allow_html=True)


# Header (tittel venstre, dato høyre)
h_left, h_right = st.columns([6, 1])
with h_left:
    st.markdown(f"# {TITLE}")   # Eksisterende tittel
with h_right:
    st.markdown(
        f"<div class='date-right'>{format_no_date(datetime.now())}</div>",
        unsafe_allow_html=True
    )


# ----------------------------
# Innlevert – visning og logikk (kjører bare når valgt)
# ----------------------------
def render_innlevert():
    try:
        df_inn = read_df_innlevert()
    except Exception as e:
        st.error(f"Kunne ikke lese 'Innlevert': {e}")
        st.stop()

    # KPI-er
    total_inn = len(df_inn)                       # antall rader (uten header – get_all_records dropper header)
    unique_brands_inn = df_inn["Merke"].nunique() # unike merker
    today = datetime.now().date()
    today_inn = int((df_inn["Innlevert"] == today).sum())  # innlevert i dag

    # KPI-rad
    sp_l, c1, c2, c3, sp_r = st.columns([1, 3, 3, 3, 1], gap="small")
    with c1:
        st.metric("Totalt innlevert", total_inn)
    with c2:
        st.metric("Merker", unique_brands_inn)
    with c3:
        st.metric("Innlevert i dag", today_inn)

    # ----- Grafer -----
    left, right = st.columns(2)

    # Innlevert per merke (bar)
    per_brand_inn = (
        df_inn.groupby("Merke").size()
        .reset_index(name="Innlevert")
        .sort_values("Innlevert", ascending=False, ignore_index=True)
    )
    with left:
        with st.container(border=True):  # ekte "card" uten ekstra tom rad
            st.subheader("Innlevert per merke")
            if per_brand_inn.empty:
                st.info("Ingen innleveringer.")
            else:
                fig_b = px.bar(per_brand_inn, x="Merke", y="Innlevert", text="Innlevert")
                fig_b.update_traces(textposition="outside", cliponaxis=False)
                fig_b.update_layout(margin=dict(l=10, r=10, t=30, b=10), xaxis_tickangle=-35)
                st.plotly_chart(fig_b, use_container_width=True)

    # Innlevert per dag (linje)
    per_day = (
        pd.Series(df_inn["Innlevert"])
        .value_counts()
        .rename_axis("Dato")
        .reset_index(name="Innlevert")
        .sort_values("Dato")
    )
    with right:
        with st.container(border=True):
            st.subheader("Innlevert per dag")
            if per_day.empty:
                st.info("Ingen innleveringer.")
            else:
                fig_d = px.line(per_day, x="Dato", y="Innlevert", markers=True)
                fig_d.update_layout(margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig_d, use_container_width=True)

    # Tabell
    with st.expander("Vis tabell", expanded=False):
        with st.container(border=True):
            df_show = df_inn.copy()
            df_show.index = range(1, len(df_show) + 1)  # 1-basert indeks
            st.dataframe(df_show, use_container_width=True)


# Hvis "Reparert" er valgt, fortsetter filen som før
# (Koden din for 'Reparert' – df = read_df(), KPI, grafer, tabeller, admin-upload – følger videre nedenfor.)



# Skjul "Logged in as"
# st.caption(f"Logged in as **{name}**")

def render_inhouse():
    try:
        df_inh = read_df_inhouse()
    except Exception as e:
        st.error(f"Kunne ikke lese 'Inhouse': {e}")
        st.stop()

    # KPI-er
    total_inhouse = len(df_inh)
    eldste = df_inh["Dato"].min() if not df_inh.empty else None
    eldste_txt = format_no_date(eldste) if eldste else "-"

    top_brand = "-"
    top_brand_count = 0
    if not df_inh.empty:
        vc = df_inh["Merke"].value_counts()
        if not vc.empty:
            top_brand = vc.idxmax()
            top_brand_count = int(vc.max())

    # KPI-rad
    sp_l, c1, c2, c3, sp_r = st.columns([1, 3, 3, 3, 1], gap="small")
    with c1:
        st.metric("Total", total_inhouse)
    with c2:
        st.metric("Eldste Inhouse", eldste_txt)
    with c3:
        st.metric("Topp-merke", top_brand, f"{top_brand_count} stk" if top_brand_count else None)

    # Grafer
    left, right = st.columns(2)

    # Bar: antall per status
    per_status = (
        df_inh.groupby("Status").size()
             .reset_index(name="Antall")
             .sort_values("Antall", ascending=False, ignore_index=True)
    )
    with left:
        with st.container(border=True):
            st.subheader("Antall per status")
            if per_status.empty:
                st.info("Ingen inhouse-rader.")
            else:
                fig_s = px.bar(per_status, x="Status", y="Antall", text="Antall")
                fig_s.update_traces(textposition="outside", cliponaxis=False)
                fig_s.update_layout(margin=dict(l=10, r=10, t=30, b=10), xaxis_tickangle=-35)
                st.plotly_chart(fig_s, use_container_width=True)

    # Bar: antall per dato (søyle i stedet for linje)
    per_day = (
        df_inh.groupby("Dato").size()
             .reset_index(name="Antall")
             .sort_values("Dato")
    )
    with right:
        with st.container(border=True):
            st.subheader("Antall per dato")
            if per_day.empty:
                st.info("Ingen inhouse-rader.")
            else:
                fig_d = px.bar(per_day, x="Dato", y="Antall", text="Antall")
                fig_d.update_traces(textposition="outside", cliponaxis=False)
                fig_d.update_layout(margin=dict(l=10, r=10, t=30, b=10), xaxis_tickangle=-35)
                st.plotly_chart(fig_d, use_container_width=True)

    # Tabell
    with st.expander("Vis tabell", expanded=False):
        with st.container(border=True):
            df_show = df_inh.copy()
            df_show.index = range(1, len(df_show) + 1)
            st.dataframe(df_show, use_container_width=True)

def render_arbeidet():
    try:
        df_a = read_df_arbeidet()
    except Exception as e:
        st.error(f"Kunne ikke lese 'Arbeidet på': {e}")
        st.stop()

    # KPI-er
    total = len(df_a)
    if total:
        status_counts = df_a["Status"].value_counts()
        top_status = status_counts.idxmax()
        top_status_count = int(status_counts.max())

        tech_counts = df_a["Tekniker"].value_counts()
        top_tech = tech_counts.idxmax()
        top_tech_count = int(tech_counts.max())
    else:
        top_status, top_status_count = "-", 0
        top_tech, top_tech_count = "-", 0

    sp_l, c1, c2, c3, sp_r = st.columns([1, 3, 3, 3, 1], gap="small")
    with c1:
        st.metric("Totalt (i dag)", total)
    with c2:
        st.metric("Status (flest)", top_status, f"{top_status_count} stk" if top_status_count else None)
    with c3:
        st.metric("Top Technician", top_tech, f"{top_tech_count} stk" if top_tech_count else None)

    left, right = st.columns(2)

    # Venstre: TABELL – antall pr. merke
    with left:
        with st.container(border=True):
            st.subheader("Merker i dag (antall)")
            if df_a.empty:
                st.info("Ingen registreringer i dag.")
            else:
                per_brand = (
                    df_a.groupby("Merke").size()
                        .reset_index(name="Antall")
                        .sort_values("Antall", ascending=False, ignore_index=True)
                )
                # Vis som pen tabell med 1-basert indeks
                per_brand_show = per_brand.copy()
                per_brand_show.index = range(1, len(per_brand_show) + 1)
                st.dataframe(per_brand_show, use_container_width=True)

    # Høyre: SØYLE – antall pr. status
    with right:
        with st.container(border=True):
            st.subheader("Status i dag (antall)")
            if df_a.empty:
                st.info("Ingen registreringer i dag.")
            else:
                per_status = (
                    df_a.groupby("Status").size()
                        .reset_index(name="Antall")
                        .sort_values("Antall", ascending=False, ignore_index=True)
                )
                fig = px.bar(per_status, x="Status", y="Antall", text="Antall")
                fig.update_traces(textposition="outside", cliponaxis=False)
                fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), xaxis_tickangle=-35)
                st.plotly_chart(fig, use_container_width=True)

    # Valgfri: full tabell under en expander
    with st.expander("Vis råtabell (i dag)", expanded=False):
        if df_a.empty:
            st.info("Ingen data.")
        else:
            df_show = df_a.copy()
            df_show.index = range(1, len(df_show) + 1)
            st.dataframe(df_show, use_container_width=True)


# ----------------------------
# Ruting mellom visninger (må komme ETTER at funksjonene er definert)
# ----------------------------
if view == "Innlevert":
    render_innlevert()
    st.stop()
elif view == "Inhouse":
    render_inhouse()
    st.stop()
elif view == "Arbeidet":
    render_arbeidet()
    st.stop()


# ----------------------------
# Load and clean data
# ----------------------------
try:
    df = read_df()
except Exception as e:
    st.error(f"Could not read data source: {e}")
    st.stop()

def pick(cands, df):
    for c in cands:
        if c in df.columns:
            return c
    return None

brand_col = pick(BRAND_COLS, df)
tech_col  = pick(TECH_COLS, df)

if brand_col is None or tech_col is None:
    st.error(f"Missing columns. Found {list(df.columns)}; expected {BRAND_COLS} and {TECH_COLS}.")
    st.stop()

df[brand_col] = df[brand_col].astype(str).str.strip()
df[tech_col]  = df[tech_col].astype(str).str.strip()
df = df[(df[brand_col] != "") & (df[tech_col] != "")]

# -------------------------------
# KPI-tall (sentrert, like store kort, liten avstand)
# -------------------------------
total_repairs = len(df)
unique_brands = df[brand_col].nunique()

repairs_per_tech = (
    df.groupby(tech_col).size()
      .reset_index(name="Repairs")
      .rename(columns={tech_col: "Technician"})
      .sort_values("Repairs", ascending=False, ignore_index=True)
)
top_tech_name = repairs_per_tech.iloc[0]["Technician"] if not repairs_per_tech.empty else "-"
top_tech_reps = int(repairs_per_tech.iloc[0]["Repairs"]) if not repairs_per_tech.empty else 0

# Ytre «spacere» for å sentrere hele KPI-raden,
# og tre like brede kolonner i midten
sp_l, c1, c2, c3, sp_r = st.columns([1, 3, 3, 3, 1], gap="small")

with c1:
    st.metric("Total Repairs", total_repairs)

with c2:
    st.metric("Brands", unique_brands)

with c3:
    st.metric("Top Technician", top_tech_name, f"{top_tech_reps} repairs")


# -------------------------------
# Charts
# -------------------------------
left, right = st.columns(2)

# Brand counts
repairs_per_brand = (df.groupby(brand_col).size()
                     .reset_index(name="Repairs")
                     .rename(columns={brand_col: "Brand"})
                     .sort_values("Repairs", ascending=False, ignore_index=True))

with left:
    st.subheader("Repairs by Brand")
    if repairs_per_brand.empty:
        st.info("No brand data.")
    else:
        repairs_per_brand["Brand"] = repairs_per_brand["Brand"].astype(str)
        repairs_per_brand["Repairs"] = repairs_per_brand["Repairs"].astype(int)
        fig_b = px.bar(repairs_per_brand, x="Brand", y="Repairs", text="Repairs")
        fig_b.update_traces(textposition="outside", cliponaxis=False)
        fig_b.update_layout(margin=dict(l=10, r=10, t=30, b=10), xaxis_tickangle=-35)
        st.plotly_chart(fig_b, use_container_width=True)

with right:
    st.subheader("Repairs by Technician")
    if repairs_per_tech.empty:
        st.info("No technician data.")
    else:
        repairs_per_tech["Technician"] = repairs_per_tech["Technician"].astype(str)
        repairs_per_tech["Repairs"] = repairs_per_tech["Repairs"].astype(int)
        fig_t = px.pie(repairs_per_tech, names="Technician", values="Repairs", hole=0.6)
        fig_t.update_traces(textinfo="percent+label")
        fig_t.update_layout(showlegend=True, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_t, use_container_width=True)


# ----------------------------
# Tables (expander)
# ----------------------------
with st.expander("Show tables", expanded=False):
    t_left, t_right = st.columns(2)
    with t_left:
        st.write("Repairs per Brand")
        tbl_brand = repairs_per_brand.copy()
        tbl_brand.index = range(1, len(tbl_brand) + 1)
        st.dataframe(tbl_brand, use_container_width=True)

    with t_right:
        st.write("Repairs per Technician")
        tbl_tech = repairs_per_tech.copy()
        tbl_tech.index = range(1, len(tbl_tech) + 1)
        st.dataframe(tbl_tech, use_container_width=True)



# ----------------------------
# Admin: replace data
# ----------------------------
role = credentials_dict["usernames"][username].get("role", "viewer")
with st.expander("Admin: Replace data (upload new Excel)", expanded=False):
    if role != "admin":
        st.info("Viewer access only.")
    else:
        uploaded = st.file_uploader("Upload Excel (.xlsx) with columns Merke/Tekniker", type=["xlsx"])
        if uploaded is not None:
            try:
                new_df = pd.read_excel(uploaded)
                replace_data(new_df)
                st.success("Data replaced successfully. Click to reload.")
                if st.button("Reload now"):
                    st.experimental_rerun()
            except Exception as e:
                st.error(f"Upload failed: {e}")

# ----------------------------
# Logout
# ----------------------------
authenticator.logout("Logout", "sidebar")
st.sidebar.caption("Secure dashboard")
