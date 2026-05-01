import streamlit as st
import pandas as pd
import base64, io, requests


# ── GitHub helpers ─────────────────────────────────────────────────────────────
def _gh_creds():
    try:
        token = st.secrets.get("GITHUB_TOKEN") or ""
        repo  = st.secrets.get("GITHUB_REPO")  or ""
    except Exception:
        token, repo = "", ""
    return token, repo

def _gh_get(path: str):
    """Fetch raw bytes of a file from GitHub. Returns (bytes, sha) or (None, None)."""
    token, repo = _gh_creds()
    if not token or not repo or not path:
        return None, None
    url     = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"token {token}",
               "Accept": "application/vnd.github.v3+json"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        st.error(f"❌ Network error: {e}")
        return None, None

    if r.status_code == 401:
        st.error("❌ GitHub auth failed — check GITHUB_TOKEN in Secrets.")
        return None, None
    if r.status_code == 404:
        st.error(f"❌ File not found on GitHub: `{path}`")
        return None, None
    if r.status_code != 200:
        st.error(f"❌ GitHub error {r.status_code}: {r.text[:200]}")
        return None, None

    info = r.json()
    sha  = info.get("sha", "")

    # Files >1MB come via download_url, not inline base64
    if not info.get("content") or info.get("encoding") != "base64":
        dl = info.get("download_url")
        if not dl:
            st.error(f"❌ No content in GitHub response for `{path}`")
            return None, None
        try:
            raw = requests.get(dl, timeout=30).content
        except Exception as e:
            st.error(f"❌ Download failed: {e}")
            return None, None
    else:
        raw = base64.b64decode(info["content"].replace("\n", ""))

    return raw, sha


def _gh_put(path: str, content_bytes: bytes, sha: str, message: str) -> bool:
    """Push updated file back to GitHub."""
    token, repo = _gh_creds()
    if not token or not repo or not path:
        st.error("❌ GitHub credentials not configured.")
        return False
    url     = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"token {token}",
               "Accept": "application/vnd.github.v3+json"}
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode(),
        "sha":     sha,
    }
    r = requests.put(url, headers=headers, json=payload, timeout=30)
    return r.status_code in (200, 201)


# ── Excel parsing ──────────────────────────────────────────────────────────────
def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise: parse Date, sort, ffill."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    if "Date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    num = df.select_dtypes(include="number").columns
    df[num] = df[num].ffill().bfill()
    return df

def _shorten(col: str) -> str:
    suffixes = [' Comdty',' Index',' index',' Govt',' govt',' Curncy',' curncy']
    for s in suffixes:
        col = col.replace(s, '')
    return col.strip()

def parse_excel_bytes(raw: bytes, filename: str) -> dict:
    """Parse raw xlsx bytes → dict of {sheet_name: DataFrame}."""
    name = filename.lower()
    sheets = {}
    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw))
        df = _clean(df)
        df.columns = [_shorten(c) if c != "Date" else c for c in df.columns]
        sheets["data"] = df
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
                df = _clean(df)
                df.columns = [_shorten(c) if c != "Date" else c for c in df.columns]
                sheets[sheet] = df
            except Exception:
                pass
    return sheets


# ── Public load function (cached per file path) ────────────────────────────────
@st.cache_data(ttl=300)
def load_file(gh_path: str) -> tuple[dict, str]:
    """Load an Excel/CSV file from GitHub. Returns (sheets_dict, sha)."""
    raw, sha = _gh_get(gh_path)
    if raw is None:
        return {}, ""
    sheets = parse_excel_bytes(raw, gh_path)
    return sheets, sha


def append_and_push(gh_path: str, sha: str,
                    existing_sheets: dict, new_file) -> bool:
    """Merge new_file rows into existing_sheets and push back to GitHub."""
    new_raw  = new_file.read()
    new_sheets = parse_excel_bytes(new_raw, new_file.name)

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        all_keys = set(existing_sheets) | set(new_sheets)
        for key in all_keys:
            old = existing_sheets.get(key, pd.DataFrame())
            new = new_sheets.get(key, pd.DataFrame())
            if old.empty:
                merged = new
            elif new.empty:
                merged = old
            else:
                last      = old["Date"].max()
                additions = new[new["Date"] > last].copy()
                # align columns
                for c in old.columns:
                    if c not in additions.columns:
                        additions[c] = float("nan")
                additions = additions[old.columns]
                merged = pd.concat([old, additions], ignore_index=True) \
                           .sort_values("Date").reset_index(drop=True)
            if not merged.empty:
                merged.to_excel(writer, sheet_name=key, index=False)

    ok = _gh_put(gh_path, out.getvalue(), sha,
                 f"Data update: {new_file.name}")
    if ok:
        st.cache_data.clear()
    return ok
