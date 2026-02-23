import os
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px


# =============================================================================
# Paths / environment
# =============================================================================
APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"

def _is_headless() -> bool:
    # Streamlit Cloud typically runs headless
    return os.getenv("STREAMLIT_SERVER_HEADLESS", "").lower() == "true" or os.getenv("STREAMLIT_CLOUD", "").lower() == "true"

HEADLESS = _is_headless()

def _resolve_dir(p: str) -> Path:
    pp = Path(p).expanduser()
    if not pp.is_absolute():
        pp = (APP_DIR / pp).resolve()
    return pp

ENV_DATA_DIR = os.getenv("AVAILOPS_DATA_DIR", "").strip()
DATA_DIR = DEMO_DIR if (not ENV_DATA_DIR) else _resolve_dir(ENV_DATA_DIR)

# Hard cloud safety: Cloud/demo must ALWAYS use demo_data
if HEADLESS:
    DATA_DIR = DEMO_DIR

IS_DEMO = DATA_DIR.resolve() == DEMO_DIR.resolve()

def _within_repo(path: Path, repo_root: Path) -> bool:
    try:
        rp = repo_root.resolve()
        pp = path.resolve()
        return (pp == rp) or (rp in pp.parents)
    except Exception:
        return False

IN_REPO = _within_repo(DATA_DIR, APP_DIR)

# =============================================================================
# Privacy / anonymization controls
# =============================================================================
def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, None)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y")

ANON = True if HEADLESS else _env_bool("AVAILOPS_ANON", True)
ALLOW_CLEAR = _env_bool("AVAILOPS_ALLOW_CLEAR", False)

# Salt for stable pseudonyms
SALT = os.getenv("AVAILOPS_SALT", "").strip()
if not SALT:
    try:
        SALT = st.secrets.get("AVAILOPS_SALT", "public-demo-salt")
    except Exception:
        SALT = "public-demo-salt"

def stable_code(value: str, prefix="P") -> str:
    h = hashlib.sha256((SALT + str(value)).encode("utf-8")).hexdigest()
    return f"{prefix}-{h[:8]}"

# ---- HARD FAIL-SAFES (prevents accidental private leakage) ----
if HEADLESS:
    # Cloud must be demo + anonymized, always
    if not IS_DEMO:
        st.error("SAFETY STOP: Streamlit Cloud is locked to DEMO mode (demo_data) only.")
        st.stop()
    if not ANON:
        st.error("SAFETY STOP: Anonymization must be ON in Cloud.")
        st.stop()

if not ANON:
    # Clear-name mode is blocked unless explicitly allowed AND data is outside repo AND not demo
    if IS_DEMO or IN_REPO or (not ALLOW_CLEAR) or HEADLESS:
        st.error(
            "SAFETY STOP: Clear-name mode is blocked.\n\n"
            "To allow clear-name mode you MUST:\n"
            "  1) Run locally (not Cloud)\n"
            "  2) Point AVAILOPS_DATA_DIR to a folder OUTSIDE the repo\n"
            "  3) Set AVAILOPS_ALLOW_CLEAR=1\n"
        )
        st.stop()


# =============================================================================
# Robust CSV reader (handles the “everything in one cell/column” issue)
# =============================================================================
def read_csv_robust(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    # First try normal parse
    try:
        df = pd.read_csv(path)
        if df.shape[1] > 1:
            return df
    except Exception:
        pass

    # If it became 1 column, try: header-in-first-cell + split rows by comma
    try:
        df = pd.read_csv(path)
        if df.shape[1] == 1:
            header = str(df.columns[0]).strip().strip('"')
            if "," in header:
                cols = [c.strip().strip('"') for c in header.split(",")]
                s = df.iloc[:, 0].astype(str).str.strip().str.strip('"')
                split = s.str.split(",", expand=True)
                if split.shape[1] == len(cols):
                    split.columns = cols
                    return split
    except Exception:
        pass

    # Fallback: semicolon
    try:
        return pd.read_csv(path, sep=";")
    except Exception:
        return pd.DataFrame()


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0

@st.cache_data(show_spinner=False)
def load_csv_cached(path_str: str, mtime: float) -> pd.DataFrame:
    return read_csv_robust(Path(path_str))

def load_first(dir_path: Path, names: list[str]) -> tuple[pd.DataFrame, Path | None]:
    for n in names:
        p = dir_path / n
        if p.exists():
            return load_csv_cached(str(p), _mtime(p)), p
    return pd.DataFrame(), None


# =============================================================================
# Load datasets
# =============================================================================
# Private/daily ops exports (watchlist + trends) come from DATA_DIR
watch, watch_path = load_first(DATA_DIR, ["watchlist_today.csv", "watchlist_today_example.csv"])
trends, trends_path = load_first(DATA_DIR, ["team_trends_7d.csv", "team_trends_7d_example.csv"])

# Public case-study datasets should be public-safe; load from DATA_DIR first, then fallback to demo_data
public_multi, public_multi_path = load_first(DATA_DIR, ["public_wnba_availability_anon_multi.csv"])
if public_multi.empty:
    public_multi, public_multi_path = load_first(DEMO_DIR, ["public_wnba_availability_anon_multi.csv"])

public_single, public_single_path = load_first(DATA_DIR, ["public_wnba_2025_DAL_availability_anon.csv"])
if public_single.empty:
    public_single, public_single_path = load_first(DEMO_DIR, ["public_wnba_2025_DAL_availability_anon.csv"])


# =============================================================================
# Coerce types / anonymize
# =============================================================================
def coerce_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")
    return out

def coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out

watch = coerce_dates(watch, ["date"])
watch = coerce_numeric(watch, ["risk_score", "minutes", "rpe", "flags_count"])

trends = coerce_dates(trends, ["date"])
trends = coerce_numeric(trends, ["team_minutes_7d", "team_load_7d", "sleep_avg_7d", "soreness_avg_7d", "flags_count_7d"])

public_multi = coerce_numeric(public_multi, ["season", "games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"])
public_single = coerce_numeric(public_single, ["games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"])

def anonymize_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()

    # Prefer athlete_id for stable pseudonym; else display_name; else row index
    if "athlete_id" in out.columns:
        out["player_code"] = out["athlete_id"].astype(str).map(lambda x: stable_code(x, prefix="ATH"))
    elif "display_name" in out.columns:
        out["player_code"] = out["display_name"].astype(str).map(lambda x: stable_code(x, prefix="ATH"))
    else:
        out["player_code"] = [f"ATH-{i:03d}" for i in range(1, len(out) + 1)]

    # Drop name/id columns in anonymized mode
    out.drop(columns=[c for c in ["athlete_id", "display_name", "name", "player_name"] if c in out.columns], inplace=True, errors="ignore")

    # In Cloud, drop notes entirely (extra safe)
    if HEADLESS and "notes" in out.columns:
        out.drop(columns=["notes"], inplace=True, errors="ignore")

    # Move player_code to front
    cols = ["player_code"] + [c for c in out.columns if c != "player_code"]
    return out[cols]

if ANON:
    watch = anonymize_watchlist(watch)


# =============================================================================
# UI
# =============================================================================
st.set_page_config(page_title="AvailOps — War Room", layout="wide")
st.title("AvailOps — War Room")
st.caption("Decision-support view for availability ops (public demo + local private mode).")

mode_label = "CLOUD DEMO" if HEADLESS else ("LOCAL DEMO" if IS_DEMO else ("LOCAL PRIVATE (Anonymized)" if ANON else "LOCAL PRIVATE (Clear)"))

# Sidebar (professional + minimal)
with st.sidebar:
    st.markdown("## AvailOps War Room")
    st.markdown(f"**Mode:** `{mode_label}`")
    st.markdown(f"**Data source:** `{str(DATA_DIR)}`")
    st.markdown(f"**Anon:** `{ANON}`")

    st.divider()
    st.markdown("### Data health")
    st.metric("Watchlist rows", 0 if watch.empty else int(len(watch)))
    st.metric("Team trend rows", 0 if trends.empty else int(len(trends)))
    st.metric("Public rows", int(len(public_multi)) if not public_multi.empty else int(len(public_single)))

    missing = []
    if watch_path is None:
        missing.append("watchlist_today.csv")
    if trends_path is None:
        missing.append("team_trends_7d.csv")

    if missing and (not IS_DEMO):
        st.warning("Missing private exports:\n- " + "\n- ".join(missing))

    st.divider()
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

# Top metrics row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Watchlist rows", 0 if watch.empty else len(watch))
c2.metric("Trend rows", 0 if trends.empty else len(trends))
c3.metric("Public rows", (0 if (public_multi.empty and public_single.empty) else (len(public_multi) if not public_multi.empty else len(public_single))))
c4.metric("Last refresh", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

tab1, tab2, tab3 = st.tabs(["Watchlist", "Team Trends", "Public Case Study"])

# -----------------------------------------------------------------------------
# Tab 1: Watchlist
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Watchlist (today)")
    if watch.empty:
        st.warning(
            "No watchlist rows found.\n\n"
            "Private mode expects a CSV in your data folder named:\n"
            "- watchlist_today.csv (preferred)\n"
            "- watchlist_today_example.csv (fallback)"
        )
    else:
        status_col = next((c for c in watch.columns if c.lower() in ("status", "flag", "color")), None)
        risk_col = "risk_score" if "risk_score" in watch.columns else None

        left, right = st.columns([1.2, 0.8])

        with left:
            st.markdown("**All rows**")
            st.dataframe(watch, width="stretch")

        with right:
            if status_col:
                flagged = watch[watch[status_col].astype(str).str.upper().isin(["YELLOW", "ORANGE", "RED"])].copy()
                st.markdown("**Flagged subset (YELLOW/ORANGE/RED)**")
                st.dataframe(flagged, width="stretch")
            else:
                st.info("No `status` column found.")

            if risk_col and watch[risk_col].notna().any():
                fig = px.histogram(watch, x=risk_col, nbins=15, title="Risk score distribution")
                st.plotly_chart(fig, width="stretch")

# -----------------------------------------------------------------------------
# Tab 2: Team Trends
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Team trends (last 7 days)")
    if trends.empty:
        st.warning(
            "No team trend rows found.\n\n"
            "Private mode expects a CSV in your data folder named:\n"
            "- team_trends_7d.csv (preferred)\n"
            "- team_trends_7d_example.csv (fallback)"
        )
    else:
        st.dataframe(trends, width="stretch")

        date_col = "date" if "date" in trends.columns else None
        metric_candidates = [c for c in trends.columns if c != date_col and pd.api.types.is_numeric_dtype(trends[c])]

        if date_col and metric_candidates:
            pick = st.selectbox("Plot metric", metric_candidates, index=0)
            dfp = trends.dropna(subset=[date_col]).sort_values(date_col)
            fig = px.line(dfp, x=date_col, y=pick, title=f"Trend: {pick}")
            st.plotly_chart(fig, width="stretch")

# -----------------------------------------------------------------------------
# Tab 3: Public Case Study (multi-season capable)
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("Public case study (anonymized availability)")
    st.caption("Source: public ESPN boxscore availability via wehoop. Player identities anonymized.")

    pub = public_multi if not public_multi.empty else public_single

    if pub.empty:
        st.warning("No public case study file found. Expected in demo_data or your data folder.")
    else:
        # Detect columns for filters
        season_col = "season" if "season" in pub.columns else None
        team_col = None
        for cand in ("team_abb", "team", "team_abbrev", "team_abbreviation"):
            if cand in pub.columns:
                team_col = cand
                break

        # Sidebar filters (only when present)
        filt = pub.copy()
        f1, f2 = st.columns(2)

        if season_col:
            seasons = sorted([int(x) for x in pd.Series(filt[season_col]).dropna().unique().tolist()])
            with f1:
                season_pick = st.multiselect("Season", seasons, default=seasons[-1:] if seasons else [])
            if season_pick:
                filt = filt[filt[season_col].astype(float).astype(int).isin(season_pick)]

        if team_col:
            teams = sorted(pd.Series(filt[team_col]).dropna().astype(str).unique().tolist())
            with f2:
                team_pick = st.multiselect("Team", teams, default=teams[:1] if teams else [])
            if team_pick:
                filt = filt[filt[team_col].astype(str).isin(team_pick)]

        st.dataframe(filt, width="stretch")

        if set(["games_dnp", "minutes_total"]).issubset(filt.columns):
            hover = "player_code" if "player_code" in filt.columns else None
            fig = px.scatter(
                filt,
                x="games_dnp",
                y="minutes_total",
                title="Availability vs workload (anonymized)",
                hover_name=hover,
            )
            st.plotly_chart(fig, width="stretch")