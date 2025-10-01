
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
BRAND_COLS = ["Merke", "Product brand", "Brand"]
TECH_COLS  = ["Tekniker", "Service technician", "Technician"]

# Auto-refresh every 30 minutes
st_autorefresh(interval=30 * 60 * 1000, key="auto_refresh_30min")

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
    credentials=credentials_dict,
    cookie_name=auth_cfg.get("cookie_name", "repair_dash_cookie"),
    key=auth_cfg.get("signature_key", "CHANGE_ME"),
    cookie_expiry_days=auth_cfg.get("cookie_expiry_days", 7),
)

name, auth_status, username = authenticator.login("Login", "main")

if not auth_status:
    if auth_status is False:
        st.error("Invalid username/password")
    st.stop()

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

# ----------------------------
# Header (title left, date right)
# ----------------------------
h_left, h_right = st.columns([4, 1])
with h_left:
    st.markdown(f"## {TITLE}")
with h_right:
    st.markdown(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")

st.caption(f"Logged in as **{name}**")

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

# ----------------------------
# KPIs
# ----------------------------
total_repairs = len(df)
unique_brands = df[brand_col].nunique()
repairs_per_tech = df[tech_col].value_counts().reset_index()
repairs_per_tech.columns = ["Technician", "Repairs"]
top_tech = repairs_per_tech.iloc[0] if not repairs_per_tech.empty else None

k1, k2, k3 = st.columns(3)
k1.metric("Total Repairs", f"{total_repairs}")
k2.metric("Brands", f"{unique_brands}")
if top_tech is not None:
    k3.metric("Top Technician", f"{top_tech['Technician']}", f"{int(top_tech['Repairs'])} repairs")
else:
    k3.metric("Top Technician", "-", None)

# ----------------------------
# Charts row
# ----------------------------
chart_left, chart_right = st.columns(2)

repairs_per_brand = (
    df[brand_col].value_counts()
      .reset_index()
      .rename(columns={"index": "Brand", brand_col: "Repairs"})
      .sort_values("Repairs", ascending=False)
)

with chart_left:
    st.subheader("Repairs by Brand")
    fig_b = px.bar(
        repairs_per_brand,
        x="Brand",
        y="Repairs",
        text="Repairs",
    )
    fig_b.update_traces(textposition="outside")
    fig_b.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_b, use_container_width=True)

with chart_right:
    st.subheader("Repairs by Technician")
    if not repairs_per_tech.empty:
        fig_t = px.pie(
            repairs_per_tech,
            names="Technician",
            values="Repairs",
            hole=0.6,
        )
        fig_t.update_traces(textinfo="percent+label")
        fig_t.update_layout(showlegend=True, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_t, use_container_width=True)
    else:
        st.info("No technician data.")

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
