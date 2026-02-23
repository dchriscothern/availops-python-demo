import os
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px


# =========================
# Streamlit page config (must be before other st.* calls)
# =========================
st.set_page_config(page_title="AvailOps — War Room", layout="wide")


# =========================
# Paths + runtime mode
# =========================
APP_ROOT = Path(__file__).resolve().parent
DEFAULT_DEMO_DIR = APP_ROOT / "demo_data"

def _is_headless() -> bool:
    return os.getenv("STREAMLIT_SERVER_HEADLESS", "").lower() == "true"

RUN_MODE = "CLOUD" if _is_headless() else "LOCAL"

DATA_DIR = Path(os.getenv("AVAILOPS_DATA_DIR", str(DEFAULT_DEMO_DIR)))
ANON = os.getenv("AVAILOPS_ANON", "1") == "1"

# Explicit “allow clear” and “allow medical columns” gates (local only)
ALLOW_CLEAR = os.getenv("AVAILOPS_ALLOW_CLEAR", "0") == "1"
ALLOW_MEDICAL = os.getenv("AVAILOPS_ALLOW_MEDICAL", "0") == "1"

# Stable anonymization salt (Cloud can use secrets; local can use env var)
SALT = os.getenv("AVAILOPS_SALT", "")
if not SALT:
    try:
        SALT = st.secrets.get("AVAILOPS_SALT", "public-demo-salt")
    except Exception:
        SALT = "public-demo-salt"

# =========================
# HARD FAIL-SAFE
# =========================
# 1) Cloud/headless always anonymized
if RUN_MODE == "CLOUD":
    ANON = True
    ALLOW_CLEAR = False
    ALLOW_MEDICAL = False

# 2) Block identifiable mode unless explicitly allowed AND data is outside repo
def _path_is_inside_repo(p: Path) -> bool:
    try:
        return p.resolve().is_relative_to(APP_ROOT.resolve())
    except Exception:
        # Python <3.9 fallback (not needed for you, but safe)
        pr = str(p.resolve()).lower()
        rr = str(APP_ROOT.resolve()).lower()
        return pr.startswith(rr)

if not ANON:
    if not ALLOW_CLEAR:
        st.error(
            "Blocked: ANON=0 requested but AVAILOPS_ALLOW_CLEAR is not set.\n\n"
            "To run identifiable (LOCAL ONLY):\n"
            "  $env:AVAILOPS_ALLOW_CLEAR='1'\n"
            "  $env:AVAILOPS_ANON='0'\n"
        )
        st.stop()

    if _path_is_inside_repo(DATA_DIR):
        st.error(
            "Blocked: AVAILOPS_DATA_DIR points inside the Git repo.\n\n"
            "Private/identifiable data must live OUTSIDE the repo (e.g. C:\\AvailOps_PrivateData).\n"
            "Set:\n"
            "  $env:AVAILOPS_DATA_DIR='C:\\AvailOps_PrivateData'\n"
        )
        st.stop()


# =========================
# Helpers
# =========================
MEDICAL_KEYWORDS = (
    "diagnos", "injur", "surgery", "acl", "fracture", "concussion",
    "medical_note", "rx", "med", "imaging"
)

NAME_COLS = ("name", "player_name", "display_name", "athlete_name")

def stable_code(value: str, prefix="P") -> str:
    h = hashlib.sha256((SALT + str(value)).encode("utf-8")).hexdigest()
    return f"{prefix}-{h[:6]}"

def read_csv_robust(path: Path) -> pd.DataFrame:
    """
    Reads normal CSVs and fixes the common case where the entire row is in one column.
    This happens when a CSV was saved with quotes/encoding weirdness or pasted incorrectly.
    """
    if not path.exists():
        return pd.DataFrame()

    # Try normal CSV first
    try:
        df = pd.read_csv(path)
        if df.shape[1] > 1:
            return df
    except Exception:
        df = None

    # One-column case: try to split by comma (header-in-first-cell heuristic)
    try:
        df = pd.read_csv(path)
        if df.shape[1] == 1:
            col0 = str(df.columns[0])
            if col0.count(",") >= 2:
                new_cols = [c.strip() for c in col0.split(",")]
                s = df.iloc[:, 0].astype(str).str.strip()
                split = s.str.split(",", expand=True)
                if split.shape[1] == len(new_cols):
                    split.columns = new_cols
                    split = split.apply(lambda x: x.astype(str).str.strip())
                    return split
    except Exception:
        pass

    # Semicolon fallback
    try:
        return pd.read_csv(path, sep=";")
    except Exception:
        return pd.DataFrame()

def redact_medical_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    redact = [c for c in df.columns if any(k in c.lower() for k in MEDICAL_KEYWORDS)]
    df.drop(columns=redact, inplace=True, errors="ignore")
    return df

def anonymize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Adds player_code and redacts name/medical-ish fields when ANON is enabled."""
    if df is None or df.empty:
        return df

    df = df.copy()

    id_candidates = ["athlete_id", "player_id", "player_code", "name", "player_name", "display_name"]
    id_col = next((c for c in id_candidates if c in df.columns), None)

    if id_col:
        df["player_code"] = df[id_col].astype(str).map(lambda x: stable_code(x, prefix="P"))
    else:
        df["player_code"] = [f"P-{i:02d}" for i in range(1, len(df) + 1)]

    # Drop name-like columns
    drop_names = [c for c in df.columns if c.lower() in NAME_COLS]
    df.drop(columns=drop_names, inplace=True, errors="ignore")

    # Always redact medical-ish columns in anon mode
    df = redact_medical_columns(df)
    return df

def load_csv_first(names):
    """Return the first existing CSV from DATA_DIR, else empty df."""
    for n in names:
        p = DATA_DIR / n
        if p.exists():
            return read_csv_robust(p)
    return pd.DataFrame()

def coerce_dates(df: pd.DataFrame, col_candidates=("date", "game_date")) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    for c in col_candidates:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df

def safe_numeric(df: pd.DataFrame, cols):
    if df is None or df.empty:
        return df
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# =========================
# Cached loaders
# =========================
@st.cache_data(ttl=1800)  # 30 minutes
def load_watchlist():
    df = load_csv_first(["watchlist_today.csv", "watchlist_today_example.csv"])
    df = coerce_dates(df, ("date",))
    df = safe_numeric(df, ["risk_score", "minutes", "rpe", "flags_count"])
    return df

@st.cache_data(ttl=1800)
def load_trends():
    df = load_csv_first(["team_trends_7d.csv", "team_trends_7d_example.csv"])
    df = coerce_dates(df, ("date",))
    df = safe_numeric(df, ["team_minutes_7d", "team_load_7d", "sleep_avg_7d", "soreness_avg_7d", "flags_count_7d"])
    return df

@st.cache_data(ttl=1800)
def load_public_summary():
    # Prefer multi-team + multi-season file
    df = load_csv_first([
        "public_wnba_availability_anon_multi.csv",
        "public_wnba_2025_DAL_availability_anon.csv",
    ])
    df = safe_numeric(df, ["games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"])
    if not df.empty:
        if "season" not in df.columns:
            df["season"] = 2025
        if "team_abb" not in df.columns:
            df["team_abb"] = "DAL"
        df["team_abb"] = df["team_abb"].astype(str).str.upper()
        df["season"] = pd.to_numeric(df["season"], errors="coerce").astype("Int64")
    return df


# =========================
# Load data
# =========================
watch = load_watchlist()
trends = load_trends()
public_summary = load_public_summary()

# Apply privacy policy:
# - watchlist may contain ids/names => anonymize if ANON
# - even in clear mode, keep medical columns off unless explicitly allowed
if ANON:
    watch = anonymize_df(watch)
else:
    if not ALLOW_MEDICAL:
        watch = redact_medical_columns(watch)

# =========================
# UI
# =========================
st.title("AvailOps — War Room")
st.caption(
    "Demo-safe by default. Demo reads from /demo_data. "
    "Private mode reads from AVAILOPS_DATA_DIR (outside the repo)."
)

DEBUG = os.getenv("AVAILOPS_DEBUG", "0") == "1"

with st.sidebar:
    st.markdown("## Runtime")
    st.write(f"**Mode:** `{RUN_MODE}`")
    st.write(f"**DATA_DIR:** `{DATA_DIR}`")
    st.write(f"**ANON:** `{ANON}`")

    with st.expander("How to run modes (click to expand)", expanded=False):
        st.markdown("### Demo mode (public-safe)")
        st.code(
            "Remove-Item Env:\\AVAILOPS_DATA_DIR -ErrorAction SilentlyContinue\n"
            "$env:AVAILOPS_ANON='1'\n"
            "streamlit run app.py",
            language="powershell",
        )

        st.markdown("### Private mode (anonymized internal)")
        st.code(
            "$env:AVAILOPS_DATA_DIR='C:\\AvailOps_PrivateData'\n"
            "$env:AVAILOPS_ANON='1'\n"
            "$env:AVAILOPS_SALT='internal-salt'\n"
            "streamlit run app.py",
            language="powershell",
        )

        st.markdown("### Private mode (identifiable — LOCAL ONLY)")
        st.code(
            "$env:AVAILOPS_DATA_DIR='C:\\AvailOps_PrivateData'\n"
            "$env:AVAILOPS_ALLOW_CLEAR='1'\n"
            "$env:AVAILOPS_ANON='0'\n"
            "# Optional (still redacts medical unless you also set:)\n"
            "# $env:AVAILOPS_ALLOW_MEDICAL='1'\n"
            "streamlit run app.py",
            language="powershell",
        )

# Metrics row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Watchlist rows", 0 if watch.empty else len(watch))
c2.metric("Trend rows", 0 if trends.empty else len(trends))
c3.metric("Public rows", 0 if public_summary.empty else len(public_summary))
c4.metric("Last refresh", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

tab1, tab2, tab3 = st.tabs(["Watchlist", "Team Trends", "Public Case Study"])

# --- Tab 1: Watchlist
with tab1:
    st.subheader("Watchlist (today)")
    if watch.empty:
        st.warning("No rows found. Place watchlist_today.csv in DATA_DIR.")
    else:
        status_col = next((c for c in watch.columns if c.lower() in ("status", "flag", "color")), None)
        risk_col = "risk_score" if "risk_score" in watch.columns else None

        left, right = st.columns([1, 1])

        with left:
            st.markdown("**All rows**")
            st.dataframe(watch, use_container_width=True)

        with right:
            if status_col:
                flagged = watch[watch[status_col].astype(str).str.upper().isin(["YELLOW", "ORANGE", "RED"])].copy()
                st.markdown("**Flagged subset (YELLOW/ORANGE/RED)**")
                st.dataframe(flagged, use_container_width=True)
            else:
                st.info("No `status` column found. Showing risk distribution if available.")

            if risk_col and watch[risk_col].notna().any():
                fig = px.histogram(watch, x=risk_col, nbins=15, title="Risk score distribution")
                st.plotly_chart(fig, use_container_width=True)

# --- Tab 2: Team Trends
with tab2:
    st.subheader("Team trends (last 7 days)")
    if trends.empty:
        st.warning("No rows found. Place team_trends_7d.csv in DATA_DIR.")
    else:
        st.dataframe(trends, use_container_width=True)

        date_col = "date" if "date" in trends.columns else None
        metric_candidates = [c for c in trends.columns if c != date_col]
        metric_candidates = [c for c in metric_candidates if pd.api.types.is_numeric_dtype(trends[c])]

        if date_col and metric_candidates:
            pick = st.selectbox("Plot metric", metric_candidates, index=0)
            dfp = trends.dropna(subset=[date_col]).sort_values(date_col)
            fig = px.line(dfp, x=date_col, y=pick, title=f"Trend: {pick}")
            st.plotly_chart(fig, use_container_width=True)

# --- Tab 3: Public Case Study
with tab3:
    st.subheader("Public case study (anonymized availability)")
    if public_summary.empty:
        st.warning("No public case study summary found in DATA_DIR.")
    else:
        st.caption("Source: public ESPN boxscore availability via wehoop. Player identities anonymized.")
        df_pub = public_summary.copy()

        teams = sorted([t for t in df_pub["team_abb"].dropna().unique().tolist() if t])
        default_team = "DAL" if "DAL" in teams else (teams[0] if teams else None)

        cA, cB = st.columns([1, 2])
        with cA:
            team_sel = st.selectbox("Team", teams, index=teams.index(default_team) if default_team in teams else 0)

        sub = df_pub[df_pub["team_abb"] == team_sel].copy()
        seasons = sorted([int(s) for s in sub["season"].dropna().unique().tolist()])

        with cB:
            default_seasons = seasons[-1:] if len(seasons) >= 1 else seasons
            season_sel = st.multiselect("Seasons", seasons, default=default_seasons)

        if season_sel:
            sub = sub[sub["season"].isin(season_sel)]

        m1, m2, m3 = st.columns(3)
        m1.metric("Rows", int(len(sub)))
        m2.metric("Seasons selected", int(len(season_sel)))
        m3.metric("Total minutes (sum)", int(sub["minutes_total"].fillna(0).sum()) if "minutes_total" in sub.columns else 0)

        show_cols = [c for c in ["season", "team_abb", "player_code", "games_played", "games_dnp", "minutes_total", "minutes_avg"] if c in sub.columns]
        st.dataframe(sub.sort_values(["season", "minutes_total"], ascending=[True, False])[show_cols], use_container_width=True)

        if set(["games_dnp", "minutes_total"]).issubset(sub.columns):
            fig = px.scatter(
                sub,
                x="games_dnp",
                y="minutes_total",
                color="season" if "season" in sub.columns else None,
                title="Availability vs workload (anonymized)",
                hover_name="player_code" if "player_code" in sub.columns else None,
            )
            st.plotly_chart(fig, use_container_width=True)

        if "minutes_total" in sub.columns and "season" in sub.columns:
            fig2 = px.histogram(sub, x="minutes_total", color="season", nbins=20, title="Minutes distribution (by season)")
            st.plotly_chart(fig2, use_container_width=True)