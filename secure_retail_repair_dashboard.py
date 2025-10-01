
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

TITLE = "Retail Repair Dashboard"  

# Kompakt layout + kort-stil (uthev hver kolonne/boks)
st.markdown("""
<style>
  /* Mindre luft på siden */
  .block-container { 
    padding-top: 1rem; 
    padding-bottom: 1rem; 
  }

  /* KPI-bokser (st.metric) som "cards" */
  div[data-testid="stMetric"] {
    background: rgba(255,255,255,0.03);     /* diskret bakgrunn på mørkt tema */
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 6px 16px rgba(0,0,0,0.25);
  }
  /* KPI-verdier (store tall) */
  div[data-testid="stMetricValue"] { 
    font-size: 2.2rem; 
    font-weight: 700;
  }
  /* KPI-labels */
  div[data-testid="stMetricLabel"] {
    font-size: 0.95rem;
    opacity: 0.9;
  }

  /* Generisk "card" du kan bruke rundt grafer/tabeller */
  .rr-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 6px 16px rgba(0,0,0,0.25);
    margin-bottom: 1rem;
  }

  /* Litt strammere overskrift-spacing inni cards */
  .rr-card h3, .rr-card h4 { margin-top: 0.2rem; }

  /* Plotly-bakgrunn: la kortets bakgrunn skinne gjennom */
  .stPlotlyChart, .plotly, .js-plotly-plot { background: transparent !important; }
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
# Google Sheets helpers
# ----------------------------
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
    gc = gspread_client()
    sh = gc.open_by_key(st.secrets.get("sheet_id"))
    ws = sh.worksheet(st.secrets.get("worksheet", "Sheet1"))
    rows = ws.get_all_records()
    if not rows:
        return pd.DataFrame(columns=["Merke", "Tekniker"])
    return pd.DataFrame(rows)

def replace_data(df_new: pd.DataFrame):
    gc = gspread_client()
    sh = gc.open_by_key(st.secrets.get("sheet_id"))
    ws_name = st.secrets.get("worksheet", "Sheet1")
    try:
        ws = sh.worksheet(ws_name)
    except Exception:
        ws = sh.add_worksheet(ws_name, rows="1000", cols="10")

    # Map to required columns
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

# -------------------------------
# Header (tittel venstre, dato høyre)
# -------------------------------
h_left, h_right = st.columns([4, 1])

with h_left:
    st.markdown(f"# {TITLE}")  # Stor tittel

with h_right:
    st.markdown(
        f"<div style='text-align:right; font-size:1.2rem; padding-top:0.8rem;'>"
        f"{datetime.now().strftime('%Y-%m-%d')}"
        f"</div>",
        unsafe_allow_html=True
    )


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
# KPI-tall (symmetrisk med Brands i midten)
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

# 5 like kolonner → innhold i 1, 3 og 5 gir perfekt sentrering av midtkolonnen
c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])

with c1:
    st.metric("Total Repairs", total_repairs)

with c3:
    st.metric("Brands", unique_brands)

with c5:
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
