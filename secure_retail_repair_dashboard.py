
import json
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px

import gspread
from google.oauth2.service_account import Credentials
import streamlit_authenticator as stauth
from streamlit_autorefresh import st_autorefresh

  
# ----------------------------
# Page config
# ----------------------------
st.set_page_config(page_title="Retail Repair Dashboard", layout="wide")

# Kompakt topplinje/overskrift
st.markdown("""
<style>
/* Skjul Streamlit-header/toolbar (fjerner tomt felt helt øverst) */
header[data-testid="stHeader"] { height: 0px; visibility: hidden; }
div[data-testid="stToolbar"]   { visibility: hidden; height: 0px; }

st.markdown("""
<style>
/* Tving frem sidebar-toggle ("hamburger") som flyter i hjørnet */
div[data-testid="collapsedControl"] {
  visibility: visible !important;
  display: block !important;
  position: fixed !important;
  top: 10px;
  left: 10px;
  z-index: 1001;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 8px;
  padding: 2px 6px;
}

/* Behold stram topp */
.block-container { padding-top: 0.4rem; }
</style>
""", unsafe_allow_html=True)

/* Mindre topppadding i hoved-containeren */
.block-container { padding-top: 0.4rem; }

/* Strammere tittel – mindre margin over/under */
h1 {
  margin-top: 0rem;
  margin-bottom: 0.5rem;
}

/* Dato til høyre, tettere på tittelen */
.date-right {
  text-align: right;
  font-size: 1.0rem;
  padding-top: 0.2rem;    /* justér ved behov */
  margin-bottom: 0; 
}

/* Liten «dra-opp» effekt på KPI-rad om du vil enda tettere på tittelen */
.kpi-row { margin-top: -0.2rem; }
</style>
""", unsafe_allow_html=True)

# --- KONSTANTER (må komme før de brukes) ---
TITLE = "Retail Repair Dashboard"
BRAND_COLS = ["Merke", "Product brand", "Brand"]
TECH_COLS  = ["Tekniker", "Service technician", "Technician"]

# Ekstra kolonner/innstillinger for "Innlevert"
DATE_COLS = ["Innlevert", "Received date", "Date"]  # mulige navn på dato-kolonnen
WORKSHEET_REPARERT   = st.secrets.get("worksheet", "Sheet1")   # som før
WORKSHEET_INNLEVERT  = st.secrets.get("worksheet_innlevert", "Sheet2")  # ny

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

# Hvilke worksheets som skal brukes (kan overstyres i secrets)
WORKSHEET_REPARERT  = st.secrets.get("worksheet", "Sheet1")
WORKSHEET_INNLEVERT = st.secrets.get("worksheet_innlevert", "Sheet2")

# Kolonnenavn som kan forekomme for dato i "Innlevert"
DATE_COLS = ["Innlevert", "Received date", "Date"]

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

def read_df():
    """Les data for 'Reparert' fra worksheet WORKSHEET_REPARERT (default Sheet1)."""
    gc = gspread_client()
    sh = gc.open_by_key(st.secrets.get("sheet_id"))
    ws = sh.worksheet(WORKSHEET_REPARERT)
    rows = ws.get_all_records()
    if not rows:
        return pd.DataFrame(columns=["Merke", "Tekniker"])
    return pd.DataFrame(rows)

def replace_data(df_new: pd.DataFrame):
    """Erstatt data i WORKSHEET_REPARERT (Reparert/Sheet1) med to kolonner: Merke, Tekniker."""
    gc = gspread_client()
    sh = gc.open_by_key(st.secrets.get("sheet_id"))
    ws_name = WORKSHEET_REPARERT
    try:
        ws = sh.worksheet(ws_name)
    except Exception:
        ws = sh.add_worksheet(ws_name, rows="1000", cols="10")

    # Map til riktig kolonner
    def pick(cands, df):
        for c in cands:
            if c in df.columns:
                return c
        return None

    bcol = pick(BRAND_COLS, df_new)
    tcol = pick(TECH_COLS,  df_new)

    if bcol is None or tcol is None:
        raise ValueError(f"Expected columns {BRAND_COLS} and {TECH_COLS}, got {list(df_new.columns)}")

    out = df_new[[bcol, tcol]].copy()
    out.columns = ["Merke", "Tekniker"]

    ws.clear()
    values = [out.columns.tolist()] + out.fillna("").astype(str).values.tolist()
    ws.update("A1", values)

def read_df_innlevert():
    """Les data for 'Innlevert' fra worksheet WORKSHEET_INNLEVERT (default Sheet2).
       Forventer kolonne 'Merke' og en datokolonne (f.eks. 'Innlevert')."""
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

    # Rens
    df[bcol] = df[bcol].astype(str).str.strip()
    df[dcol] = pd.to_datetime(df[dcol], errors="coerce").dt.date
    df = df[(df[bcol] != "") & df[dcol].notna()]

    out = df[[bcol, dcol]].copy()
    out.columns = ["Merke", "Innlevert"]
    return out


# ----------------------------
# Navigasjon (sidebar) + Header
# ----------------------------
st.sidebar.title("Dashbord")
view = st.sidebar.radio("Velg visning", ["Reparert", "Innlevert"], index=0)

# Header (tittel venstre, dato høyre)
h_left, h_right = st.columns([6, 1])
with h_left:
    st.markdown(f"# {TITLE}")   # Eksisterende tittel
with h_right:
    st.markdown(
        f"<div class='date-right'>{datetime.now().strftime('%Y-%m-%d')}</div>",
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
    total_inn = len(df_inn)
    unique_brands_inn = df_inn["Merke"].nunique()
    today = datetime.now().date()
    today_inn = int((df_inn["Innlevert"] == today).sum())

    # Samme KPI-rad som Reparert (tilpass verdier om du ønsker)
    st.markdown("<div class='kpi-row'>", unsafe_allow_html=True)
    sp_l, c1, c2, c3, sp_r = st.columns([1, 3, 3, 3, 1], gap="small")
    with c1:
        st.metric("Totalt innlevert", total_inn)
    with c2:
        st.metric("Merker", unique_brands_inn)
    with c3:
        st.metric("Innlevert i dag", today_inn)
    st.markdown("</div>", unsafe_allow_html=True)

    # Grafer
    left, right = st.columns(2)

    # Innlevert per merke (bar)
    per_brand_inn = (df_inn.groupby("Merke").size()
                     .reset_index(name="Innlevert")
                     .sort_values("Innlevert", ascending=False, ignore_index=True))
    with left:
        st.markdown('<div class="rr-card">', unsafe_allow_html=True)
        st.subheader("Innlevert per merke")
        if per_brand_inn.empty:
            st.info("Ingen innleveringer.")
        else:
            fig_b = px.bar(per_brand_inn, x="Merke", y="Innlevert", text="Innlevert")
            fig_b.update_traces(textposition="outside", cliponaxis=False)
            fig_b.update_layout(margin=dict(l=10, r=10, t=30, b=10), xaxis_tickangle=-35)
            st.plotly_chart(fig_b, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Innlevert per dag (linje)
    per_day = (pd.Series(df_inn["Innlevert"])
               .value_counts()
               .rename_axis("Dato")
               .reset_index(name="Innlevert")
               .sort_values("Dato"))
    with right:
        st.markdown('<div class="rr-card">', unsafe_allow_html=True)
        st.subheader("Innlevert per dag")
        if per_day.empty:
            st.info("Ingen innleveringer.")
        else:
            fig_d = px.line(per_day, x="Dato", y="Innlevert", markers=True)
            fig_d.update_layout(margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_d, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Tabell
    with st.expander("Vis tabell", expanded=False):
        st.markdown('<div class="rr-card">', unsafe_allow_html=True)
        st.dataframe(df_inn.reset_index(drop=True), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)


# Hvis "Innlevert" er valgt, rendrer vi og stopper videre kjøring (så Reparert-koden din under ikke kjøres)
if view == "Innlevert":
    render_innlevert()
    st.stop()

# Hvis "Reparert" er valgt, fortsetter filen som før
# (Koden din for 'Reparert' – df = read_df(), KPI, grafer, tabeller, admin-upload – følger videre nedenfor.)



# Skjul "Logged in as"
# st.caption(f"Logged in as **{name}**")


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
        st.dataframe(repairs_per_brand.reset_index(drop=True), use_container_width=True)
    with t_right:
        st.write("Repairs per Technician")
        st.dataframe(repairs_per_tech.reset_index(drop=True), use_container_width=True)

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
