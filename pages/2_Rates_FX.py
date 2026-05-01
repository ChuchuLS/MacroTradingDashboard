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
    # ── Curve snapshot ───────────────────────────────────────────────────────
    st.subheader("Real Rates Curve Snapshot")

    # Define tenors and currencies
    IL_CURVES = {
        "🇺🇸 US TIPS":  {"5Y":"GTII5",  "10Y":"GTII10", "30Y":"GTII30"},
        "🇨🇦 Canada":   {"5Y":"GTCAD5Y","10Y":"GTCADII10Y","30Y":"GTCAD30Y"},
        "🇩🇪 Germany":  {"7Y":"GTDEMII7Y","10Y":"GTDEMII10Y"},
        "🇬🇧 UK":       {"5Y":"GTGBPII5Y","10Y":"GTGBPII10Y","30Y":"GTGBPII30Y"},
        "🇯🇵 Japan":    {"10Y":"GTJPYII10Y"},
    }

    def get_curve_point(col, date):
        """Get yield for a column on or near a given date."""
        if col not in df.columns:
            return None
        sub = df[df["Date"] <= date][col].dropna()
        return float(sub.iloc[-1]) if not sub.empty else None

    latest_date = df["Date"].max()
    week_ago    = latest_date - pd.Timedelta(weeks=1)
    month_ago   = latest_date - pd.Timedelta(days=30)

    # Build one curve chart per currency
    curve_cols = st.columns(2)
    col_idx = 0
    for ccy, tenors in IL_CURVES.items():
        if len(tenors) < 2:
            continue
        tenor_labels = list(tenors.keys())
        cols_list    = list(tenors.values())

        now_vals   = [get_curve_point(c, latest_date) for c in cols_list]
        week_vals  = [get_curve_point(c, week_ago)    for c in cols_list]
        month_vals = [get_curve_point(c, month_ago)   for c in cols_list]

        fig = go.Figure()
        if any(v is not None for v in now_vals):
            fig.add_trace(go.Scatter(
                x=tenor_labels, y=now_vals, mode="lines+markers",
                name=f"Now ({latest_date.strftime('%b %d')})",
                line=dict(color="#378ADD", width=2), marker=dict(size=7),
            ))
        if any(v is not None for v in week_vals):
            fig.add_trace(go.Scatter(
                x=tenor_labels, y=week_vals, mode="lines+markers",
                name="1 Week Ago",
                line=dict(color="#9ca3af", width=1.5, dash="dash"), marker=dict(size=5),
            ))
        if any(v is not None for v in month_vals):
            fig.add_trace(go.Scatter(
                x=tenor_labels, y=month_vals, mode="lines+markers",
                name="1 Month Ago",
                line=dict(color="#6b7280", width=1, dash="dot"), marker=dict(size=5),
            ))
        fig.update_layout(
            title=dict(text=ccy, font=dict(size=13)),
            margin=dict(l=40, r=20, t=40, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="left", x=0, font=dict(size=10)),
            yaxis=dict(title="Yield (%)", tickformat=".2f"),
            xaxis=dict(title="Tenor"),
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        with curve_cols[col_idx % 2]:
            st.plotly_chart(fig, width="stretch")
        col_idx += 1

    st.divider()

    # ── Time series ──────────────────────────────────────────────────────────
    st.subheader("Real Rates — Time Series")

    st.markdown("**🇺🇸 US TIPS**")
    line_chart(df, ["GTII5","GTII10","GTII30"], "US TIPS Yields", days, normalize)

    st.markdown("**🇨🇦 Canada**")
    line_chart(df, ["GTCAD5Y","GTCADII10Y","GTCAD30Y"], "Canada IL Bonds", days, normalize)

    st.markdown("**🇩🇪 Germany**")
    line_chart(df, ["GTDEMII7Y","GTDEMII10Y"], "Germany IL Bonds", days, normalize)

    st.markdown("**🇬🇧 UK**")
    line_chart(df, ["GTGBPII5Y","GTGBPII10Y","GTGBPII30Y"], "UK IL Bonds", days, normalize)

    st.markdown("**🇯🇵 Japan**")
    line_chart(df, ["GTJPYII10Y"], "Japan IL Bonds", days, normalize)

    st.markdown("**🌍 10Y Comparison**")
    line_chart(df, ["GTII10","GTCADII10Y","GTDEMII10Y","GTGBPII10Y","GTJPYII10Y"],
               "10Y Real Rates — Global Comparison", days, normalize)

# ════════════════════════════════════════════
# TAB 2 — MONEY MARKET STRESS
# ════════════════════════════════════════════
with tab_mm:
    SPREADS = [
        "SOFR-IORB (Bank Repos)",
        "EFFR-IORB (Reserve Demand)",
        "TGCR-RRP (Private Repo Demand)",
        "GCF-TPR (Dealer BS Capacity)",
        "SOFR-EFFR (FHLB Repo Demand)",
    ]

    # ── Metric cards ─────────────────────────────────────────────────────────
    avail_spreads = [s for s in SPREADS if s in df.columns]
    if avail_spreads:
        valid = df[avail_spreads].notna().any(axis=1)
        latest_row = df[valid].iloc[-1]
        prev_row   = df[valid].iloc[-2]
        cols_m = st.columns(len(avail_spreads))
        for i, s in enumerate(avail_spreads):
            val = latest_row[s] if pd.notna(latest_row[s]) else None
            chg = (latest_row[s] - prev_row[s]) if (
                pd.notna(latest_row[s]) and pd.notna(prev_row[s])) else None
            cols_m[i].metric(
                disp(s),
                f"{val:.2f} bp" if val is not None else "n/a",
                f"{chg:+.2f}" if chg is not None else None,
            )

    st.divider()

    # ── Spreads time series ───────────────────────────────────────────────────
    st.subheader("Money Market Stress Spreads")
    line_chart(df, SPREADS,
               "Bloomberg Money Market Stress (SOFR/EFFR/TGCR/GCF spreads)",
               days, normalize=False, zero_line=True)

    st.divider()

    # ── Reserve Balance & NY Fed SRF ─────────────────────────────────────────
    st.subheader("Reserve Balance & NY Fed SRF")
    line_chart(df, ["farwcbls","nypvoa"],
               "Reserve Balance (Wed Close) & NY Fed Standing Repo Facility",
               days, normalize=False, zero_line=False)

# ════════════════════════════════════════════
# TAB 3 — FX BASIS SWAPS
# ════════════════════════════════════════════
with tab_fx:
    # All FX basis in one chart
    ALL_FX = ["EUXOQQC","EUXOQQ1",
              "BPXOQQC","BPXOQQ1",
              "JYBSS3M","JYBSS12M",
              "CDXOQQC","CDXOQQ1",
              "ADBSQQC","ADBSQQ1"]

    st.subheader("Cross-Currency Basis Swaps — All Pairs")
    line_chart(df, ALL_FX,
               "EUR / GBP / JPY / CAD / AUD vs USD Basis Swaps",
               days, normalize=False, zero_line=True)
