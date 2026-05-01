"""
Yield Curve Dashboard — Streamlit
==================================
GitHub integration:
  - Reads historicalDataBBG.xlsx directly from your GitHub repo on startup
  - Upload button appends new rows and pushes back to GitHub via API
  - Set secrets in .streamlit/secrets.toml:
      GITHUB_TOKEN = "ghp_..."
      GITHUB_REPO  = "youruser/yourrepo"
      GITHUB_PATH  = "historicalDataBBG.xlsx"   # path inside repo
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from pathlib import Path
import base64, io, requests

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="US Yield Curve Dashboard",
    page_icon="📈",
    layout="wide",
)

# ── Regime classification (12-week / ~3-month lookback) ──────────────────────
REGIME_COLORS = {
    "Bull Steepener":  "#4ade80",
    "Bear Steepener":  "#f87171",
    "Steepener Twist": "#facc15",
    "Bull Flattener":  "#60a5fa",
    "Bear Flattener":  "#fb923c",
    "Flattener Twist": "#c084fc",
    "Unchanged":       "#9ca3af",
}

def classify_regime(curve, curve_lb, y_short, y_short_lb, y_long, y_long_lb, eps=0.001):
    steep = curve > curve_lb + eps
    flat  = curve < curve_lb - eps
    s_up  = y_short > y_short_lb + eps
    l_up  = y_long  > y_long_lb  + eps
    s_dn  = y_short < y_short_lb - eps
    l_dn  = y_long  < y_long_lb  - eps

    if steep and s_dn and l_dn: return "Bull Steepener"
    if steep and s_up and l_up: return "Bear Steepener"
    if steep and s_dn and l_up: return "Steepener Twist"
    if flat  and s_dn and l_dn: return "Bull Flattener"
    if flat  and s_up and l_up: return "Bear Flattener"
    if flat  and s_up and l_dn: return "Flattener Twist"
    return "Unchanged"

def add_regimes(df, spread_col, short_col, long_col, lookback=60):
    """Add a regime column for a given spread."""
    curve    = df[long_col]  - df[short_col]
    curve_lb = curve.shift(lookback)
    s_lb     = df[short_col].shift(lookback)
    l_lb     = df[long_col].shift(lookback)

    regimes = []
    for i in range(len(df)):
        if pd.isna(curve_lb.iloc[i]):
            regimes.append("Unchanged")
        else:
            regimes.append(classify_regime(
                curve.iloc[i], curve_lb.iloc[i],
                df[short_col].iloc[i], s_lb.iloc[i],
                df[long_col].iloc[i],  l_lb.iloc[i],
            ))
    return regimes

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data
def clean_sheet(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise a single sheet: strip column names, parse Date, ffill blanks, sort."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    # Find the date column (first column or one named Date)
    if "Date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    num_cols = df.select_dtypes(include="number").columns
    df[num_cols] = df[num_cols].ffill().bfill()
    return df

def shorten(col: str) -> str:
    """Strip Bloomberg suffix from column name."""
    return col.replace(" Comdty", "").replace(" Index", "").strip()

# ── Column group definitions ──────────────────────────────────────────────────
YIELD_COLS_BBG = ["USGG10YR","USGG3M","USGG2YR","USGG5YR","USGG30YR","USGG12M","USGG20YR"]
YIELD_RENAME   = {"USGG2YR":"2Y","USGG10YR":"10Y","USGG30YR":"30Y",
                  "USGG3M":"3M","USGG5YR":"5Y","USGG12M":"12M","USGG20YR":"20Y"}

METAL_COLS     = ["GC1 COMB","SI1","HG1","PL1","PA1",
                  "LMCADS03","LMAHDS03","LMZSDS03","LMPBDS03","LMNIDS03","LMSNDS03"]
ENERGY_COLS    = ["CO1","CL1","NG1"]
SOFTS_COLS     = ["C 1 COMB","S 1","W 1","SM1","BO1","O 1",
                  "SB1","KC1","CT1","CC1","JO1","LC1","LH1","FC1","KO1","JN1","RS1"]
SOFTS_NAMES    = {
    "C 1 COMB":"Corn","S 1":"Soybeans","W 1":"Wheat","SM1":"Soybean Meal",
    "BO1":"Soybean Oil","O 1":"Oats","SB1":"Sugar","KC1":"Coffee",
    "CT1":"Cotton","CC1":"Cocoa","JO1":"OJ","LC1":"Live Cattle",
    "LH1":"Lean Hogs","FC1":"Feeder Cattle","KO1":"Palm Oil",
    "JN1":"Rubber","RS1":"Canola",
}

# ── Display names: Bloomberg code → "Exchange Product" ────────────────────────
DISPLAY_NAMES = {
    # Precious metals (COMEX)
    "GC1 COMB": "COMEX Gold",
    "SI1":       "COMEX Silver",
    "PL1":       "NYMEX Platinum",
    "PA1":       "NYMEX Palladium",
    # Industrial / Copper
    "HG1":       "COMEX Copper",
    # LME Base Metals
    "LMCADS03":  "LME Copper (3M)",
    "LMAHDS03":  "LME Aluminium (3M)",
    "LMZSDS03":  "LME Zinc (3M)",
    "LMPBDS03":  "LME Lead (3M)",
    "LMNIDS03":  "LME Nickel (3M)",
    "LMSNDS03":  "LME Tin (3M)",
    # Energy (NYMEX/ICE)
    "CL1":       "NYMEX WTI Crude",
    "CL1 COMB":  "NYMEX WTI Crude",
    "CO1":       "ICE Brent Crude",
    "NG1":       "NYMEX Nat Gas",
    # Grains (CBOT)
    "C 1 COMB":  "CBOT Corn",
    "S 1":       "CBOT Soybeans",
    "W 1":       "CBOT Wheat",
    "SM1":       "CBOT Soybean Meal",
    "BO1":       "CBOT Soybean Oil",
    "O 1":       "CBOT Oats",
    # Softs
    "SB1":       "ICE Sugar #11",
    "KC1":       "ICE Coffee",
    "CT1":       "ICE Cotton",
    "CC1":       "ICE Cocoa",
    "JO1":       "ICE OJ",
    # Livestock (CME)
    "LC1":       "CME Live Cattle",
    "LH1":       "CME Lean Hogs",
    "FC1":       "CME Feeder Cattle",
    # Other
    "KO1":       "BMD Palm Oil",
    "JN1":       "OSE Rubber",
    "RS1":       "ICE Canola",
}

def disp(col: str) -> str:
    """Return display name for a Bloomberg column code."""
    return DISPLAY_NAMES.get(col, col)

def split_into_sheets(df: pd.DataFrame) -> dict:
    """Split a wide single-sheet DataFrame into logical sub-DataFrames by column group."""
    sheets = {}
    def extract(cols):
        avail = [c for c in cols if c in df.columns]
        if avail:
            return df[["Date"] + avail].copy().dropna(subset=avail, how="all")
        return pd.DataFrame()

    y = extract(YIELD_COLS_BBG)
    if not y.empty:
        y = y.rename(columns=YIELD_RENAME)
        sheets["yields"] = y

    m = extract(METAL_COLS);  sheets["metal"]  = m  if not m.empty  else pd.DataFrame()
    e = extract(ENERGY_COLS); sheets["energy"] = e  if not e.empty  else pd.DataFrame()
    s = extract(SOFTS_COLS);  sheets["softs"]  = s  if not s.empty  else pd.DataFrame()
    return {k: v for k, v in sheets.items() if not v.empty}

def _parse_bytes(raw: bytes, filename: str) -> dict:
    """Parse raw xlsx/csv bytes into sheets dict. Not cached (called with bytes)."""
    import io
    name = filename.lower()
    sheets = {}
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw))
        df = clean_sheet(df)
        df.columns = [shorten(c) if c != "Date" else c for c in df.columns]
        sheets = split_into_sheets(df) or {"yields": df}
    else:
        try:
            xl = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
        except Exception:
            xl = pd.ExcelFile(io.BytesIO(raw), engine="xlrd")
        for sheet in xl.sheet_names:
            try:
                df = xl.parse(sheet)
                if df.empty:
                    continue
                df = clean_sheet(df)
                df.columns = [shorten(c) if c != "Date" else c for c in df.columns]
                sheets[sheet] = df
            except Exception as e:
                pass
        if len(sheets) == 1:
            only = list(sheets.values())[0]
            split = split_into_sheets(only)
            if len(split) > 1:
                sheets = split
    if "yields" in sheets:
        sheets["yields"] = sheets["yields"].rename(
            columns={k:v for k,v in YIELD_RENAME.items() if k in sheets["yields"].columns})
    return sheets

@st.cache_data
def load_sheets(file) -> dict:
    """Return dict of {sheet_name: DataFrame}. Reads file bytes once."""
    import io
    raw  = file.read()
    name = file.name.lower()
    return _parse_bytes(raw, name)

@st.cache_data
def load_data(file) -> pd.DataFrame:
    """Return yields sheet only (already renamed to short names by load_sheets)."""
    sheets = load_sheets(file)
    return sheets.get("yields", list(sheets.values())[0] if sheets else pd.DataFrame())

# ── Spread chart builder ──────────────────────────────────────────────────────
def spread_chart(df, front, back, title, lookback=60):
    """front = shorter tenor, back = longer tenor. Spread = back - front (always positive in normal curve)."""
    if front not in df.columns or back not in df.columns:
        st.warning(f"Missing columns: {front} or {back}")
        return

    spread = (df[back] - df[front]) * 100  # bps — long minus short
    regimes = add_regimes(df, f"{front}{back}", front, back, lookback)
    colors  = [REGIME_COLORS.get(r, "#9ca3af") for r in regimes]

    dates = df["Date"].tolist()
    sv    = spread.tolist()

    # Infer bar width in ms from median date gap
    if len(dates) > 1:
        gaps = [(dates[i+1] - dates[i]).days for i in range(min(20, len(dates)-1))]
        bar_width_ms = int(sorted(gaps)[len(gaps)//2] * 0.7 * 86_400_000)
    else:
        bar_width_ms = int(0.7 * 86_400_000)

    fig = go.Figure()

    # Single bar trace with per-bar colors
    fig.add_trace(go.Bar(
        x=dates, y=sv,
        width=bar_width_ms,
        marker=dict(color=colors, line_width=0),
        showlegend=False,
        hovertemplate="<b>%{x|%b %d %Y}</b><br>Spread: %{y:.0f} bp<br>Regime: %{customdata}<extra></extra>",
        customdata=regimes,
    ))

    # Invisible legend-only traces
    seen = set()
    for regime, color in REGIME_COLORS.items():
        if regime in regimes and regime not in seen:
            seen.add(regime)
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(symbol="square", size=10, color=color),
                name=regime, showlegend=True,
            ))

    fig.add_hline(y=0, line_dash="dash", line_color="rgba(150,150,150,0.5)", line_width=1)

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        barmode="overlay",
        margin=dict(l=50, r=20, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=11)),
        yaxis=dict(title="bp", ticksuffix=" bp"),
        xaxis=dict(type="date", showgrid=False,
                   rangebreaks=[dict(bounds=["sat","mon"], dvalue=86400000)]),
        hovermode="x",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width='stretch')

# ── Full yield curve snapshot ─────────────────────────────────────────────────
def yield_curve_snapshot(df, tenors_available):
    order = ["3M", "12M", "2Y", "5Y", "10Y", "20Y", "30Y"]
    cols  = [c for c in order if c in tenors_available]
    if len(cols) < 2:
        return

    latest = df[["Date"] + cols].dropna().iloc[-1]
    prev   = df[["Date"] + cols].dropna().iloc[-2] if len(df) > 1 else latest
    wk_ago = df[["Date"] + cols].dropna().iloc[-6] if len(df) > 5 else latest

    x_labels = cols
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_labels, y=[latest[c] for c in cols],
                             mode="lines+markers", name=str(latest["Date"].date()),
                             line=dict(color="#378ADD", width=2), marker=dict(size=7)))
    fig.add_trace(go.Scatter(x=x_labels, y=[wk_ago[c] for c in cols],
                             mode="lines+markers", name=str(wk_ago["Date"].date()) + " (1wk ago)",
                             line=dict(color="#9ca3af", width=1, dash="dash"), marker=dict(size=5)))
    fig.update_layout(
        margin=dict(l=50, r=20, t=30, b=40),
        yaxis=dict(title="Yield (%)", tickformat=".2f"),
        xaxis=dict(title="Tenor"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width='stretch', config={'displayModeBar': True})


# ── Main app ──────────────────────────────────────────────────────────────────
st.title("📈 US Treasury Yield Curve Dashboard")

# ── GitHub config — read secrets lazily inside functions, never at module level
def _gh_creds():
    """Read GitHub secrets at call time (never cached at module load)."""
    try:
        token = st.secrets.get("GITHUB_TOKEN") or ""
        repo  = st.secrets.get("GITHUB_REPO")  or ""
        path  = st.secrets.get("GITHUB_PATH")  or "historicalDataBBG.xlsx"
    except Exception:
        token, repo, path = "", "", "historicalDataBBG.xlsx"
    return token, repo, path

def _upload_password():
    try:
        return st.secrets.get("UPLOAD_PASSWORD") or ""
    except Exception:
        return ""

def _gh_api():
    _, repo, path = _gh_creds()
    return f"https://api.github.com/repos/{repo}/contents/{path}"

def _gh_headers():
    token, _, _ = _gh_creds()
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

def load_from_github() -> tuple[dict, str]:
    """Download xlsx from GitHub, return (sheets_dict, sha)."""
    token, repo, path = _gh_creds()
    if not token or not repo or not path:
        return {}, ""

    url     = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

    try:
        r = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        st.error(f"❌ Network error: {e}")
        return {}, ""

    if r.status_code == 401:
        st.error("❌ GitHub auth failed — GITHUB_TOKEN is wrong or expired.")
        return {}, ""
    if r.status_code == 404:
        st.error(f"❌ File not found. Tried: `{url}`")
        return {}, ""
    if r.status_code != 200:
        st.error(f"❌ GitHub error {r.status_code}: {r.text[:200]}")
        return {}, ""

    info = r.json()
    sha  = info.get("sha", "")

    # Files >1MB are not base64-encoded inline — use download_url instead
    if not info.get("content") or info.get("encoding") != "base64":
        dl = info.get("download_url")
        if not dl:
            st.error(f"❌ No content in GitHub response. Keys: {list(info.keys())}")
            return {}, ""
        try:
            raw = requests.get(dl, timeout=30).content
        except Exception as e:
            st.error(f"❌ Download failed: {e}")
            return {}, ""
    else:
        raw = base64.b64decode(info["content"].replace("\n", ""))

    try:
        sheets = _parse_bytes(raw, path)
        return sheets, sha
    except Exception as e:
        st.error(f"❌ Parse error: {e}")
        return {}, ""

def push_to_github(new_xlsx_bytes: bytes, sha: str, commit_msg: str) -> bool:
    """Push updated xlsx back to GitHub, overwriting the file."""
    token, repo, path = _gh_creds()
    if not token or not repo or not path:
        st.error("GitHub credentials not configured in secrets.")
        return False
    url     = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    payload = {
        "message": commit_msg,
        "content": base64.b64encode(new_xlsx_bytes).decode(),
        "sha":     sha,
    }
    r = requests.put(url, headers=headers, json=payload, timeout=30)
    return r.status_code in (200, 201)

def append_new_data(existing_sheets: dict, new_file) -> tuple[dict, bytes]:
    """Merge uploaded new data into existing sheets, return updated sheets + xlsx bytes."""
    new_sheets = load_sheets(new_file)
    merged = {}
    all_keys = set(existing_sheets) | set(new_sheets)
    for key in all_keys:
        old = existing_sheets.get(key, pd.DataFrame())
        new = new_sheets.get(key, pd.DataFrame())
        if old.empty:
            merged[key] = new
        elif new.empty:
            merged[key] = old
        else:
            last = old["Date"].max()
            additions = new[new["Date"] > last]
            if not additions.empty:
                # Align columns
                for c in old.columns:
                    if c not in additions.columns:
                        additions = additions.copy()
                        additions[c] = float("nan")
                additions = additions[old.columns]
                merged[key] = pd.concat([old, additions], ignore_index=True).sort_values("Date").reset_index(drop=True)
            else:
                merged[key] = old

    # Serialise back to xlsx (one sheet per group, reverse-renamed to original BBG names)
    SHORT_TO_BBG = {v: k for k, v in YIELD_RENAME.items()}
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for key, df in merged.items():
            df_out = df.copy()
            if key == "yields":
                df_out = df_out.rename(columns={v: k+" Index" for k, v in YIELD_RENAME.items() if v in df_out.columns})
            df_out.to_excel(writer, sheet_name=key, index=False)
    return merged, out.getvalue()

# ── Load data: GitHub first, fallback to manual upload ───────────────────────
gh_sheets, gh_sha = load_from_github()
has_github = bool(gh_sheets)
_token, _repo, _path = _gh_creds()

if has_github:
    st.success("✅ Loaded from GitHub")
else:
    if not _token:
        st.info("💡 **GitHub not configured.** Add `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_PATH` to Streamlit Cloud → Settings → Secrets.")
    st.subheader("Manual upload")

if not has_github:
    uploaded_file = st.file_uploader("Upload historicalDataBBG.xlsx", type=["xlsx","xls","csv"])
else:
    uploaded_file = None

# ── Data update panel (password protected) ────────────────────────────────────
if has_github:
    with st.expander("📤 Update market data"):
        pwd_input = st.text_input("Enter upload password", type="password", key="upload_pwd")
        correct_pwd = _upload_password()

        if pwd_input and pwd_input != correct_pwd:
            st.error("❌ Wrong password")
        elif pwd_input == correct_pwd and correct_pwd != "":
            st.success("✅ Authenticated")
            st.markdown("Upload **one file** containing all your latest data. "
                        "The app will automatically update both `historicalDataBBG.xlsx` "
                        "and `historicalDataRatesFX.xlsx` based on column names.")

            new_data_file = st.file_uploader(
                "Upload update file (xlsx with all columns)",
                type=["xlsx","xls","csv"], key="new_data"
            )

            if new_data_file:
                # Preview what will be updated
                try:
                    preview_raw  = new_data_file.read()
                    new_data_file.seek(0)
                    preview_df   = _parse_bytes(preview_raw, new_data_file.name)
                    for sh, df_p in preview_df.items():
                        last = df_p["Date"].max().strftime("%b %d, %Y") if "Date" in df_p.columns else "?"
                        st.caption(f"  • **{sh}**: {len(df_p)} rows, latest: {last}")
                except Exception:
                    pass

                if st.button("✅ Append & push to GitHub", type="primary"):
                    # Load RatesFX file path from secrets
                    try:
                        ratesfx_path = st.secrets.get("GITHUB_PATH_RATESFX") or "historicalDataRatesFX.xlsx"
                    except Exception:
                        ratesfx_path = "historicalDataRatesFX.xlsx"

                    with st.spinner("Merging and pushing to GitHub…"):
                        # Parse the uploaded file once
                        update_raw   = new_data_file.read()
                        new_parsed   = _parse_bytes(update_raw, new_data_file.name)

                        # ── Update historicalDataBBG.xlsx ──────────────────
                        bbg_cols = set(c for sh in gh_sheets.values()
                                       for c in sh.columns if c != "Date")
                        new_bbg  = {k: v for k, v in new_parsed.items()
                                    if any(c in bbg_cols for c in v.columns if c != "Date")}
                        ok_bbg = False
                        if new_bbg:
                            merged_bbg, bytes_bbg = append_new_data(gh_sheets, new_data_file)
                            ok_bbg = push_to_github(bytes_bbg, gh_sha, "Data update: BBG")

                        # ── Update historicalDataRatesFX.xlsx ──────────────
                        from utils.data_loader import load_file, append_and_push
                        rfx_sheets, rfx_sha = load_file(ratesfx_path)
                        ok_rfx = False
                        if rfx_sheets and new_parsed:
                            rfx_cols = set(c for sh in rfx_sheets.values()
                                           for c in sh.columns if c != "Date")
                            new_rfx  = {k: v for k, v in new_parsed.items()
                                        if any(c in rfx_cols for c in v.columns if c != "Date")}
                            if new_rfx:
                                import io as _io
                                new_data_file.seek(0)
                                ok_rfx = append_and_push(ratesfx_path, rfx_sha,
                                                         rfx_sheets, new_data_file)

                    results = []
                    if ok_bbg: results.append("historicalDataBBG.xlsx ✅")
                    if ok_rfx: results.append("historicalDataRatesFX.xlsx ✅")
                    if results:
                        st.success(f"Pushed: {', '.join(results)}")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.warning("Nothing was pushed — check column names match existing data.")
        else:
            st.caption("🔒 Password required to upload data.")

# Resolve which sheets to use
if has_github:
    all_sheets = gh_sheets
elif uploaded_file is not None:
    all_sheets = load_sheets(uploaded_file)
else:
    st.stop()

# Derive per-group DataFrames from sheets (already split & renamed by load_sheets)
df_hist        = all_sheets.get("yields", pd.DataFrame())
metal_df_hist  = all_sheets.get("metal",  pd.DataFrame())
energy_df_hist = all_sheets.get("energy", pd.DataFrame())
softs_df_hist  = all_sheets.get("softs",  pd.DataFrame())

df        = df_hist
metal_df  = metal_df_hist
energy_df = energy_df_hist
softs_df  = softs_df_hist

tenors = [c for c in ["3M","12M","2Y","5Y","10Y","20Y","30Y"] if c in df.columns]

# Status banner
_y_last = df["Date"].max().strftime("%b %d, %Y") if not df.empty else "n/a"
st.caption(f"Data through **{_y_last}** · Upload new data using the append button above to update")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_yield, tab_comm, tab_corr = st.tabs(["📈 Yield Curve", "📦 Commodities & Energy", "🔗 Correlation"])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — YIELD CURVE
# ════════════════════════════════════════════════════════════════════════════════
with tab_yield:
    st.sidebar.header("Yield Settings")
    period = st.sidebar.selectbox("Period", ["1Y", "2Y", "5Y", "10Y", "All"], index=2)
    lookback_weeks = st.sidebar.slider("Regime lookback (weeks)", 1, 52, 12)
    lookback = lookback_weeks * 5

    period_map = {"1Y": 252, "2Y": 504, "5Y": 1260, "10Y": 2520, "All": len(df)}
    n = period_map[period]
    df_view = df.iloc[-n:].reset_index(drop=True)

    latest = df_view[["Date"] + tenors].dropna().iloc[-1]
    prev   = df_view[["Date"] + tenors].dropna().iloc[-2]

    st.subheader(f"Latest: {latest['Date'].strftime('%b %d, %Y')}")
    cols_metrics = st.columns(len(tenors) + 2)
    for i, t in enumerate(tenors):
        chg = latest[t] - prev[t]
        cols_metrics[i].metric(label=t, value=f"{latest[t]:.2f}%",
                               delta=f"{chg:+.2f}%", delta_color="inverse")

    if "2Y" in tenors and "10Y" in tenors:
        s2s10 = (latest["10Y"] - latest["2Y"]) * 100
        p2s10 = (prev["10Y"]   - prev["2Y"])   * 100
        cols_metrics[-2].metric("2s10s", f"{s2s10:+.0f} bp", f"{s2s10-p2s10:+.1f} bp")

    if "10Y" in tenors and "30Y" in tenors:
        s10s30 = (latest["30Y"] - latest["10Y"]) * 100
        p10s30 = (prev["30Y"]   - prev["10Y"])   * 100
        cols_metrics[-1].metric("10s30s", f"{s10s30:+.0f} bp", f"{s10s30-p10s30:+.1f} bp")

    st.divider()
    st.subheader("Yield curve snapshot")
    yield_curve_snapshot(df_view, tenors)

    st.divider()
    # (front=shorter tenor, back=longer tenor) — spread always computed as back - front
    spreads_to_plot = []
    if "2Y"  in tenors and "10Y" in tenors: spreads_to_plot.append(("2Y",  "10Y", "2s10s spread (bp)"))
    if "10Y" in tenors and "30Y" in tenors: spreads_to_plot.append(("10Y", "30Y", "10s30s spread (bp)"))
    if "3M"  in tenors and "10Y" in tenors: spreads_to_plot.append(("3M",  "10Y", "3m10y spread (bp)"))
    if "2Y"  in tenors and "5Y"  in tenors: spreads_to_plot.append(("2Y",  "5Y",  "2s5s spread (bp)"))
    if "5Y"  in tenors and "30Y" in tenors: spreads_to_plot.append(("5Y",  "30Y", "5s30s spread (bp)"))

    for front, back, title in spreads_to_plot:
        st.subheader(title)
        spread_chart(df_view, front, back, title, lookback=lookback)

    with st.expander("View raw data"):
        st.dataframe(df_view[["Date"] + tenors].set_index("Date").sort_index(ascending=False),
                     width='stretch')

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMMODITIES & ENERGY
# ════════════════════════════════════════════════════════════════════════════════
with tab_comm:
    st.sidebar.divider()
    st.sidebar.header("Commodities Settings")
    comm_period = st.sidebar.selectbox("Trend period", ["1Y","2Y","5Y","10Y","All"], index=2, key="comm_period")
    normalize   = st.sidebar.checkbox("Normalize to % return", value=False)
    comm_days   = {"1Y":365,"2Y":730,"5Y":1825,"10Y":3650,"All":99999}[comm_period]

    METAL_GROUPS = {
        "Precious Metals":   ["GC1 COMB", "SI1", "PL1", "PA1"],
        "Base Metals (LME & COMEX)": ["HG1","LMCADS03","LMAHDS03","LMZSDS03","LMPBDS03","LMNIDS03","LMSNDS03"],
    }

    def trend_chart(df, cols, title, period_days, normalize=False):
        available = [c for c in cols if c in df.columns]
        if not available:
            st.caption(f"No data found for: {cols}")
            return
        cutoff = df["Date"].max() - pd.Timedelta(days=period_days)
        dff = df[df["Date"] >= cutoff][["Date"] + available].copy()
        # Reindex to business days + ffill to remove all weekend/holiday gaps
        dff = dff.set_index("Date")
        bdays = pd.bdate_range(dff.index.min(), dff.index.max())
        dff = dff.reindex(bdays).ffill().bfill().reset_index()
        dff = dff.rename(columns={"index": "Date"})
        palette = ["#378ADD","#1D9E75","#D85A30","#9F77DD","#E8A838",
                   "#E05C8A","#4ade80","#f87171","#60a5fa","#facc15","#fb923c","#c084fc"]

        if normalize:
            # Single axis — all % returns comparable
            fig = go.Figure()
            for i, col in enumerate(available):
                y = dff[col].copy()
                base = y.dropna().iloc[0] if not y.dropna().empty else 1
                base = base if base != 0 else 1
                y = (y / base - 1) * 100
                fig.add_trace(go.Scatter(
                    x=dff["Date"], y=y, name=disp(col), mode="lines",
                    line=dict(width=1.5, color=palette[i % len(palette)]),
                ))
            fig.update_layout(yaxis=dict(title="% change from start", showgrid=True))
        else:
            # Auto dual-axis: group cols by price magnitude, put outliers on right axis
            medians = {c: dff[c].median() for c in available if dff[c].notna().any()}
            if not medians:
                return
            med_vals = sorted(medians.values())
            overall_median = med_vals[len(med_vals)//2]
            # cols whose median is <10% or >1000% of the group median go on y2
            y2_cols = [c for c, m in medians.items()
                       if m < overall_median * 0.1 or m > overall_median * 10]
            y1_cols = [c for c in available if c not in y2_cols]

            fig = go.Figure()
            for i, col in enumerate(available):
                on_y2 = col in y2_cols and y1_cols  # only use y2 if there's a y1
                fig.add_trace(go.Scatter(
                    x=dff["Date"], y=dff[col], name=disp(col), mode="lines",
                    line=dict(width=1.5, color=palette[i % len(palette)]),
                    yaxis="y2" if on_y2 else "y",
                ))

            if y2_cols and y1_cols:
                fig.update_layout(
                    yaxis2=dict(
                        title="", overlaying="y", side="right",
                        showgrid=False, tickfont=dict(size=10),
                    )
                )
            fig.update_layout(yaxis=dict(title="Price", showgrid=True))

        fig.update_layout(
            title=dict(text=title, font=dict(size=13)),
            margin=dict(l=50, r=80, t=36, b=36),
            legend=dict(orientation="h", yanchor="top", y=-0.15,
                        xanchor="left", x=0, font=dict(size=10)),
            xaxis=dict(type="date", showgrid=False,
                       rangebreaks=[dict(bounds=["sat","mon"], dvalue=86400000)]),
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width='stretch')

    if metal_df.empty and energy_df.empty:
        st.info("No 'metal' or 'energy' sheets found in the uploaded file.")
    else:
        if not metal_df.empty:
            st.subheader("Metals")
            for group_name, cols in METAL_GROUPS.items():
                avail = [c for c in cols if c in metal_df.columns]
                if avail:
                    trend_chart(metal_df, avail, group_name, comm_days, normalize)

        if not energy_df.empty:
            st.subheader("Energy")
            ecols = [c for c in energy_df.columns if c != "Date"]
            trend_chart(energy_df, ecols, "Energy prices", comm_days, normalize)

        if not softs_df.empty:
            st.subheader("Soft Commodities & Livestock")
            SOFTS_GROUPS = {
                "Grains":    ["C 1 COMB","S 1","W 1","SM1","BO1","O 1"],
                "Softs":     ["SB1","KC1","CT1","CC1","JO1"],
                "Livestock": ["LC1","LH1","FC1"],
                "Other":     ["KO1","JN1","RS1"],
            }
            for grp, cols in SOFTS_GROUPS.items():
                avail = [c for c in cols if c in softs_df.columns]
                if avail:
                    trend_chart(softs_df, avail, grp, comm_days, normalize)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — CROSS-ASSET CORRELATION
# ════════════════════════════════════════════════════════════════════════════════
with tab_corr:
    st.sidebar.divider()
    st.sidebar.header("Correlation Settings")
    corr_window = st.sidebar.selectbox("Window", ["1M (21d)","3M (63d)","6M (126d)"], index=1, key="corr_win")
    corr_period = st.sidebar.selectbox("History", ["1Y","2Y","5Y","All"], index=1, key="corr_period")
    win_map   = {"1M (21d)":21,"3M (63d)":63,"6M (126d)":126}
    window    = win_map[corr_window]
    corr_days = {"1Y":365,"2Y":730,"5Y":1825,"All":99999}[corr_period]

    def build_unified(sheets, days):
        frames = []
        for sheet, sdf in sheets.items():
            if sdf.empty or "Date" not in sdf.columns:
                continue
            cutoff = sdf["Date"].max() - pd.Timedelta(days=days)
            dff = sdf[sdf["Date"] >= cutoff].set_index("Date")
            dff.columns = [f"{sheet}:{c}" for c in dff.columns]
            frames.append(dff)
        if not frames:
            return pd.DataFrame()
        unified = frames[0]
        for f in frames[1:]:
            unified = unified.join(f, how="outer")
        unified = unified.sort_index()
        # Reindex to all weekdays so mismatched calendars don't create gaps
        all_dates = pd.bdate_range(unified.index.min(), unified.index.max())
        unified = unified.reindex(all_dates)
        # Forward-fill: use last known price when market is closed
        unified = unified.ffill().bfill()
        return unified

    unified    = build_unified(all_sheets, corr_days)
    all_assets = list(unified.columns) if not unified.empty else []
    short_name = lambda c: c.split(":")[-1]

    if unified.empty:
        st.info("No data available for correlation.")
    else:
        # ── Rolling correlation line chart ────────────────────────────────────
        st.subheader("Rolling correlation")
        col_a, col_b = st.columns(2)
        default_a = next((c for c in all_assets if "10Y" in c), all_assets[0])
        default_b = next((c for c in all_assets if "GC1" in c or "CL1" in c), all_assets[min(1,len(all_assets)-1)])
        asset_a = col_a.selectbox("Asset A", all_assets,
                                  format_func=short_name,
                                  index=all_assets.index(default_a), key="ca")
        asset_b = col_b.selectbox("Asset B", all_assets,
                                  format_func=short_name,
                                  index=all_assets.index(default_b), key="cb")

        if asset_a != asset_b:
            rets         = unified[[asset_a, asset_b]].pct_change().dropna()
            rolling_corr = rets[asset_a].rolling(window).corr(rets[asset_b]).dropna()

            # FIX 1: Line chart instead of bar chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=rolling_corr.index, y=rolling_corr.values,
                mode="lines", line=dict(width=1.8, color="#378ADD"),
                fill="tozeroy",
                fillcolor="rgba(55,138,221,0.12)",
                hovertemplate="<b>%{x|%b %d %Y}</b><br>Corr: %{y:.3f}<extra></extra>",
            ))
            fig.add_hline(y=0,    line_dash="dash", line_color="rgba(150,150,150,0.5)", line_width=1)
            fig.add_hline(y=0.7,  line_dash="dot",  line_color="rgba(29,158,117,0.5)",  line_width=1)
            fig.add_hline(y=-0.7, line_dash="dot",  line_color="rgba(216,90,48,0.5)",   line_width=1)
            fig.update_layout(
                title=dict(text=f"Rolling {corr_window}: {short_name(asset_a)} vs {short_name(asset_b)}", font=dict(size=13)),
                margin=dict(l=50, r=20, t=40, b=36),
                yaxis=dict(title="Correlation", range=[-1.05, 1.05], tickformat=".2f", zeroline=False),
                xaxis=dict(type="date", showgrid=False,
                           rangebreaks=[dict(bounds=["sat","mon"], dvalue=86400000)]),
                hovermode="x unified",
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, width='stretch')

        st.divider()

        # ── Correlation heatmap with asset picker ─────────────────────────────
        st.subheader(f"Correlation matrix — {corr_window}")
        all_short  = [short_name(c) for c in all_assets]
        default_sel = all_short  # all selected by default
        selected_short = st.multiselect(
            "Select assets to include",
            options=all_short,
            default=default_sel,
            key="heatmap_assets",
        )

        if len(selected_short) >= 2:
            sel_full   = [c for c in all_assets if short_name(c) in selected_short]
            rets_all   = unified[sel_full].pct_change().dropna().iloc[-window:]
            corr_m     = rets_all.corr()
            labels     = [short_name(c) for c in corr_m.columns]
            z          = corr_m.values.round(2).tolist()

            heat = go.Figure(go.Heatmap(
                z=z, x=labels, y=labels,
                colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
                text=[[f"{v:.2f}" for v in row] for row in z],
                texttemplate="%{text}", textfont=dict(size=9),
                showscale=True, colorbar=dict(thickness=12, len=0.8),
            ))
            heat.update_layout(
                height=max(500, len(labels)*36 + 120),
                margin=dict(l=80, r=20, t=20, b=80),
                xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
                yaxis=dict(tickfont=dict(size=10), autorange="reversed"),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(heat, width='stretch')
        else:
            st.info("Select at least 2 assets to show the matrix.")
