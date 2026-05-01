"""
Rates & FX Basis Dashboard — pages/2_Rates_FX.py
Reads historicalDataRatesFX.xlsx from GitHub via utils/data_loader.py
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.data_loader import load_file, append_and_push

st.set_page_config(page_title="Rates & FX Basis", page_icon="📊", layout="wide")

# ── GitHub path for this file ─────────────────────────────────────────────────
try:
    GH_PATH = st.secrets.get("GITHUB_PATH_RATESFX") or "historicalDataRatesFX.xlsx"
except Exception:
    GH_PATH = "historicalDataRatesFX.xlsx"

# ── Display name mapping ──────────────────────────────────────────────────────
DISPLAY = {
    # TIPS / Inflation-linked
    "GTII30":    "US TIPS 30Y",
    "GTII10":    "US TIPS 10Y",
    "GTII5":     "US TIPS 5Y",
    "GTCADII10Y":"CAD IL 10Y",
    "GTCAD5Y":   "CAD 5Y",
    "GTCAD30Y":  "CAD 30Y",
    "GTDEMII10Y":"EUR IL 10Y",
    "GTDEMII7Y": "EUR IL 7Y",
    "GTGBPII10Y":"GBP IL 10Y",
    "GTGBPII5Y": "GBP IL 5Y",
    "GTGBPII30Y":"GBP IL 30Y",
    "GTJPYII10Y":"JPY IL 10Y",
    "GTJPYII5Y": "JPY IL 5Y",
    # Money market rates
    "SOFRRATE":  "SOFR",
    "IRRBIOER":  "IORB",
    "FEDL01":    "EFFR",
    "UREPGATO":  "GCF/RRP",
    "TGCRRATE":  "TGCR",
    "FDTRFTRL":  "Fed Target (Low)",
    "USBGRATE":  "BGCR",
    "UREPTATO":  "Tri-Party Avg",
    "farwcbls":  "Reserve Bal (Wed)",
    "nypvoa":    "NY Fed SRF",
    # Money market spreads
    "SOFR-IORB (Bank Repos)":            "SOFR−IORB (Bank Repos)",
    "EFFR-IORB (Reserve Demand)":        "EFFR−IORB (Reserve Demand)",
    "TGCR-RRP (Private Repo Demand)":    "TGCR−RRP (Private Repo)",
    "GCF-TPR (Dealer BS Capacity)":      "GCF−TPR (Dealer Cap.)",
    "SOFR-EFFR (FHLB Repo Demand)":      "SOFR−EFFR (FHLB)",
    # FX basis
    "EUXOQQC":   "EUR/USD Basis Spot",
    "EUXOQQ1":   "EUR/USD Basis 1Y",
    "BPXOQQC":   "GBP/USD Basis Spot",
    "BPXOQQ1":   "GBP/USD Basis 1Y",
    "JYBSS3M":   "JPY Basis 3M",
    "JYBSS12M":  "JPY Basis 12M",
    "CDXOQQC":   "CAD/USD Basis Spot",
    "CDXOQQ1":   "CAD/USD Basis 1Y",
    "ADBSQQC":   "AUD/USD Basis Spot",
    "ADBSQQ1":   "AUD/USD Basis 1Y",
}

def disp(col): return DISPLAY.get(col, col)

PALETTE = ["#378ADD","#1D9E75","#D85A30","#9F77DD","#E8A838",
           "#E05C8A","#4ade80","#f87171","#60a5fa","#facc15","#fb923c","#c084fc"]

# ── Chart builder ─────────────────────────────────────────────────────────────
def line_chart(df, cols, title, period_days, normalize=False, zero_line=False):
    available = [c for c in cols if c in df.columns]
    if not available:
        st.caption(f"No data: {cols}")
        return
    cutoff = df["Date"].max() - pd.Timedelta(days=period_days)
    dff = df[df["Date"] >= cutoff][["Date"] + available].copy()

    fig = go.Figure()
    for i, col in enumerate(available):
        y = dff[col].copy()
        if normalize:
            base = y.dropna().iloc[0] if not y.dropna().empty else 1
            y = (y / (base if base != 0 else 1) - 1) * 100
        fig.add_trace(go.Scatter(
            x=dff["Date"], y=y, name=disp(col), mode="lines",
            line=dict(width=1.5, color=PALETTE[i % len(PALETTE)]),
        ))
    if zero_line:
        fig.add_hline(y=0, line_dash="dash", line_color="rgba(150,150,150,0.4)", line_width=1)

    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        margin=dict(l=50, r=20, t=40, b=80),
        legend=dict(orientation="h", yanchor="top", y=-0.15,
                    xanchor="left", x=0, font=dict(size=10)),
        yaxis=dict(title="% change" if normalize else "", showgrid=True),
        xaxis=dict(type="date", showgrid=False,
                   rangebreaks=[dict(bounds=["sat","mon"], dvalue=86400000)]),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch")

# ── Load data ─────────────────────────────────────────────────────────────────
st.title("📊 Rates & FX Basis")

sheets, sha = load_file(GH_PATH)
if not sheets:
    st.stop()

df = list(sheets.values())[0]
st.success("✅ Loaded from GitHub")

# ── Append new data UI ────────────────────────────────────────────────────────
with st.expander("📤 Append new market data"):
    new_file = st.file_uploader("Upload file with new rows", type=["xlsx","xls","csv"], key="rfx_upload")
    if new_file and st.button("Append & push to GitHub"):
        with st.spinner("Merging and pushing…"):
            ok = append_and_push(GH_PATH, sha, sheets, new_file)
        if ok:
            st.success("Pushed! Refreshing…")
            st.rerun()
        else:
            st.error("Push failed — check token permissions.")

# ── Sidebar controls ──────────────────────────────────────────────────────────
st.sidebar.header("Settings")
period   = st.sidebar.selectbox("Period", ["1Y","2Y","5Y","10Y","All"], index=2)
normalize = st.sidebar.checkbox("Normalize to % return", value=False)
days = {"1Y":365,"2Y":730,"5Y":1825,"10Y":3650,"All":99999}[period]

_last = df["Date"].max().strftime("%b %d, %Y") if not df.empty else "n/a"
st.caption(f"Data through **{_last}**")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_tips, tab_mm, tab_fx = st.tabs([
    "🏛️ Inflation-Linked Bonds",
    "💵 Money Market Stress",
    "💱 FX Basis Swaps",
])

# ════════════════════════════════════════════
# TAB 1 — INFLATION-LINKED BONDS
# ════════════════════════════════════════════
with tab_tips:
    st.subheader("US TIPS")
    line_chart(df, ["GTII5","GTII10","GTII30"], "US TIPS Yields", days, normalize)

    st.subheader("International Inflation-Linked")
    line_chart(df, ["GTCADII10Y","GTDEMII10Y","GTGBPII10Y","GTJPYII10Y"],
               "10Y IL Bonds — Global", days, normalize)

    st.subheader("GBP IL Bonds")
    line_chart(df, ["GTGBPII5Y","GTGBPII10Y","GTGBPII30Y"],
               "GBP Inflation-Linked", days, normalize)

    st.subheader("CAD Bonds")
    line_chart(df, ["GTCAD5Y","GTCADII10Y","GTCAD30Y"],
               "CAD Govt Bonds", days, normalize)

# ════════════════════════════════════════════
# TAB 2 — MONEY MARKET STRESS
# ════════════════════════════════════════════
with tab_mm:
    st.subheader("Policy & Overnight Rates")
    line_chart(df, ["SOFRRATE","FEDL01","IRRBIOER","FDTRFTRL","UREPTATO"],
               "Key Money Market Rates", days, normalize)

    st.subheader("Money Market Stress Spreads")
    spreads = [
        "SOFR-IORB (Bank Repos)",
        "EFFR-IORB (Reserve Demand)",
        "TGCR-RRP (Private Repo Demand)",
        "GCF-TPR (Dealer BS Capacity)",
        "SOFR-EFFR (FHLB Repo Demand)",
    ]
    line_chart(df, spreads, "Bloomberg Money Market Stress Indicators", days,
               normalize=False, zero_line=True)

    # Show latest spread values as metrics
    latest = df[df[spreads].notna().any(axis=1)].dropna(subset=spreads, how='all').iloc[-1]
    prev   = df[df[spreads].notna().any(axis=1)].dropna(subset=spreads, how='all').iloc[-2]
    cols_m = st.columns(len(spreads))
    for i, s in enumerate(spreads):
        val  = latest[s] if pd.notna(latest[s]) else float("nan")
        chg  = (latest[s] - prev[s]) if pd.notna(latest[s]) and pd.notna(prev[s]) else float("nan")
        cols_m[i].metric(
            disp(s),
            f"{val:.2f} bp" if not pd.isna(val) else "n/a",
            f"{chg:+.2f}" if not pd.isna(chg) else None,
        )

    st.subheader("Reserve Balance & SRF")
    line_chart(df, ["farwcbls","nypvoa","UREPGATO"],
               "Reserve Balance & Repo Facility", days)

# ════════════════════════════════════════════
# TAB 3 — FX BASIS SWAPS
# ════════════════════════════════════════════
with tab_fx:
    st.subheader("EUR/USD Basis")
    line_chart(df, ["EUXOQQC","EUXOQQ1"], "EUR/USD Cross-Currency Basis",
               days, normalize=False, zero_line=True)

    st.subheader("GBP/USD Basis")
    line_chart(df, ["BPXOQQC","BPXOQQ1"], "GBP/USD Cross-Currency Basis",
               days, normalize=False, zero_line=True)

    st.subheader("JPY Basis")
    line_chart(df, ["JYBSS3M","JYBSS12M"], "JPY Cross-Currency Basis",
               days, normalize=False, zero_line=True)

    st.subheader("CAD/USD Basis")
    line_chart(df, ["CDXOQQC","CDXOQQ1"], "CAD/USD Cross-Currency Basis",
               days, normalize=False, zero_line=True)

    st.subheader("AUD/USD Basis")
    line_chart(df, ["ADBSQQC","ADBSQQ1"], "AUD/USD Cross-Currency Basis",
               days, normalize=False, zero_line=True)

    st.subheader("All FX Basis — 1Y Tenors")
    line_chart(df, ["EUXOQQ1","BPXOQQ1","CDXOQQ1","ADBSQQ1","JYBSS12M"],
               "1Y Cross-Currency Basis Comparison", days, normalize=False, zero_line=True)
