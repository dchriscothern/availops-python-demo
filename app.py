import os
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px


# =============================================================================
# AvailOps — War Room (Python Demo)
#
# Modes:
#   - PUBLIC DEMO (Streamlit Cloud OR local default): reads ./demo_data, anonymized
#   - LOCAL PRIVATE (local only): reads AVAILOPS_DATA_DIR, anonymized by default
#
# HARD SAFETY:
#   - If running in Streamlit Cloud/headless, the app is locked to demo_data + ANON=True.
#   - If AVAILOPS_DATA_DIR is set in Cloud to anything other than demo_data, the app refuses.
# =============================================================================


# -------------------------
# Runtime detection
# -------------------------
BASE_DIR = Path(__file__).resolve().parent

def _is_truthy(x: str) -> bool:
    return str(x).strip().lower() in ("1", "true", "yes", "y", "on")

def _running_in_cloud() -> bool:
    # Streamlit Cloud runs headless; local typically does not.
    # Keep this conservative: treat headless as "public hosting".
    headless = os.getenv("STREAMLIT_SERVER_HEADLESS", "")
    return _is_truthy(headless)

CLOUD_MODE = _running_in_cloud()

# -------------------------
# Data directory selection (with cloud hard lock)
# -------------------------
DEFAULT_DEMO_DIR = BASE_DIR / "demo_data"
ENV_DATA_DIR = os.getenv("AVAILOPS_DATA_DIR", "").strip()

if CLOUD_MODE:
    # HARD LOCK: Cloud must never read private/local paths.
    if ENV_DATA_DIR and Path(ENV_DATA_DIR).name.lower() != "demo_data":
        st.error(
            "Safety stop: This deployment is running in a hosted environment and is locked to demo_data.\n\n"
            "Remove AVAILOPS_DATA_DIR or set it to demo_data for cloud deployments."
        )
        st.stop()
    DATA_DIR = DEFAULT_DEMO_DIR
else:
    if ENV_DATA_DIR:
        p = Path(ENV_DATA_DIR)
        DATA_DIR = p if p.is_absolute() else (BASE_DIR / p)
    else:
        DATA_DIR = DEFAULT_DEMO_DIR

# -------------------------
# Anonymization controls
# -------------------------
# In Cloud: forced anonymized.
# Local: anonymized by default, allow clear IDs only if explicitly permitted.
ALLOW_CLEAR = (not CLOUD_MODE) and _is_truthy(os.getenv("AVAILOPS_ALLOW_CLEAR", "0"))
ENV_ANON = os.getenv("AVAILOPS_ANON", "1")
DEFAULT_ANON = True if CLOUD_MODE else _is_truthy(ENV_ANON)

# Stable anonymization salt (Cloud can use secrets; local can use env var)
SALT = os.getenv("AVAILOPS_SALT", "").strip()
if not SALT:
    try:
        SALT = st.secrets.get("AVAILOPS_SALT", "public-demo-salt")
    except Exception:
        SALT = "public-demo-salt"


# =============================================================================
# Helpers
# =============================================================================
def stable_code(value: str, prefix: str = "ATH") -> str:
    """Deterministic anonymized code; stable across sessions when SALT is stable."""
    h = hashlib.sha256((SALT + str(value)).encode("utf-8")).hexdigest()
    return f"{prefix}_{h[:8].upper()}"


def read_csv_robust(path: Path) -> pd.DataFrame:
    """
    Reads normal CSVs and fixes the common case where:
      - the header row is stored as a single comma-separated column name, OR
      - the first data row contains the header as comma-separated text.
    """
    if not path or not Path(path).exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()

    # Normal case
    if df.shape[1] > 1:
        return df

    # 1-column weird case
    col0_name = str(df.columns[0])
    s = df.iloc[:, 0].astype(str).fillna("").str.strip()

    # Case A: header is in the column name
    if col0_name.count(",") >= 1:
        headers = [h.strip() for h in col0_name.split(",")]
        split = s.str.split(",", expand=True)
        if split.shape[1] == len(headers):
            split.columns = headers
            return split

    # Case B: header is in first row value
    if len(s) > 0 and s.iloc[0].count(",") >= 1:
        headers = [h.strip() for h in s.iloc[0].split(",")]
        split = s.iloc[1:].str.split(",", expand=True)
        if split.shape[1] == len(headers):
            split.columns = headers
            return split.reset_index(drop=True)

    # Fallback: semicolon
    try:
        return pd.read_csv(path, sep=";")
    except Exception:
        return df


def load_first_existing(filenames) -> tuple[pd.DataFrame, Path | None]:
    for name in filenames:
        p = DATA_DIR / name
        if p.exists():
            return read_csv_robust(p), p
    return pd.DataFrame(), None


def coerce_dates(df: pd.DataFrame, candidates=("date", "game_date")) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    for c in candidates:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def safe_numeric(df: pd.DataFrame, cols) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def anonymize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Anonymize identifier-like columns; drop obvious name columns. No medical redaction here by default."""
    if df is None or df.empty:
        return df

    df = df.copy()

    # Identify a stable ID source
    id_candidates = ["athlete_id", "player_id", "player_code", "name", "player_name", "display_name"]
    id_col = next((c for c in id_candidates if c in df.columns), None)

    if "player_code" not in df.columns:
        if id_col:
            df["player_code"] = df[id_col].astype(str).map(lambda x: stable_code(x, prefix="ATH"))
        else:
            df["player_code"] = [f"ATH_{i:02d}" for i in range(1, len(df) + 1)]

    # Drop name-like columns
    drop_names = [c for c in df.columns if c.lower() in ("name", "player_name", "display_name", "athlete_name")]
    df.drop(columns=drop_names, inplace=True, errors="ignore")

    return df


def mode_label(anon: bool) -> str:
    if CLOUD_MODE:
        return "PUBLIC DEMO (Hosted)"
    return "LOCAL PRIVATE (Anonymized)" if anon else "LOCAL PRIVATE (Clear IDs)"


# =============================================================================
# Load data
# =============================================================================
# These filenames should exist in demo_data for the public demo.
watch, watch_path = load_first_existing(["watchlist_today.csv", "watchlist_today_example.csv"])
trends, trends_path = load_first_existing(["team_trends_7d.csv", "team_trends_7d_example.csv"])

# Public multi-season (preferred)
public_multi, public_multi_path = load_first_existing(["public_wnba_availability_anon_multi.csv",
                                                      "public_wnba_availability_anon_multi_example.csv"])

# Public single-team fallback (older)
public_single, public_single_path = load_first_existing(["public_wnba_2025_DAL_availability_anon.csv"])

# Optional game-level events (not required)
public_events, public_events_path = load_first_existing([
    "public_availability_events_anon.csv",
    "public_availability_events_2025_DAL_anon.csv"
])

# Coerce types
watch = coerce_dates(watch, ("date",))
watch = safe_numeric(watch, ["risk_score", "minutes", "rpe", "flags_count"])

trends = coerce_dates(trends, ("date",))
trends = safe_numeric(trends, ["team_minutes_7d", "team_load_7d", "sleep_avg_7d", "soreness_avg_7d", "flags_count_7d"])

public_multi = safe_numeric(public_multi, ["season", "games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"])
public_single = safe_numeric(public_single, ["games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"])

public_events = coerce_dates(public_events, ("game_date", "date"))
public_events = safe_numeric(public_events, ["minutes_played", "did_play", "dnp_flag"])

# Decide anonymization (local can optionally show clear IDs if explicitly allowed)
if ALLOW_CLEAR:
    # Team-facing UI: a single checkbox to anonymize IDs (default = DEFAULT_ANON)
    # Only visible locally if AVAILOPS_ALLOW_CLEAR=1
    pass

# =============================================================================
# UI
# =============================================================================
st.set_page_config(page_title="AvailOps — War Room", layout="wide")

# Sidebar: clean, team-facing
with st.sidebar:
    st.markdown("## AvailOps War Room")
    # Local-only toggle (if explicitly allowed)
    if ALLOW_CLEAR:
        anon_toggle = st.toggle("Anonymize IDs", value=DEFAULT_ANON, help="Local only. Cloud always anonymizes.")
        ANON = True if CLOUD_MODE else bool(anon_toggle)
    else:
        ANON = True if CLOUD_MODE else True  # default local = anonymized unless explicitly allowed

    st.markdown(f"**Mode:** `{mode_label(ANON)}`")

    # Data source label (do not show full private paths)
    data_src_label = "demo_data" if (DATA_DIR.resolve() == DEFAULT_DEMO_DIR.resolve()) else "private_data (local)"
    st.markdown(f"**Data source:** `{data_src_label}`")

    st.divider()
    st.markdown("### Data health")

    def _rows(df): return 0 if df is None or df.empty else int(len(df))

    st.metric("Watchlist rows", _rows(watch))
    st.metric("Team trend rows", _rows(trends))

    # Public players rows:
    public_df = public_multi if not public_multi.empty else public_single
    st.metric("Public rows", _rows(public_df))

    st.caption("Public demo uses anonymized/synthetic data only.")

    st.divider()
    st.markdown("### Filters")

    # Watchlist filter controls (safe even if empty)
    watch_search = st.text_input("Search (watchlist)", value="", placeholder="ATH_.. / player_code / note")
    show_flagged_only = st.checkbox("Flagged only (YELLOW/ORANGE/RED)", value=False)

    # Public filters (if multi-season available)
    season_filter = None
    team_filter = None
    if not public_multi.empty:
        seasons = sorted([int(x) for x in public_multi["season"].dropna().unique().tolist()]) if "season" in public_multi.columns else []
        teams = sorted([str(x) for x in public_multi["team_abb"].dropna().unique().tolist()]) if "team_abb" in public_multi.columns else []
        if seasons:
            season_filter = st.multiselect("Season", seasons, default=seasons[-1:])
        if teams:
            team_filter = st.multiselect("Team", teams, default=["DAL"] if "DAL" in teams else teams[:1])

    st.divider()
    st.markdown("### Privacy")
    st.markdown(
        "- **Cloud deployments are locked to demo_data + anonymization.**\n"
        "- **Private mode is local only** (reads from `AVAILOPS_DATA_DIR`).\n"
        "- Do **not** commit private exports to GitHub."
    )

# Apply anonymization to watchlist (and any other private tables you choose)
if ANON:
    watch = anonymize_df(watch)

# Title area
st.title("AvailOps — War Room")
st.caption("Decision-support view for availability operations (public demo + local private mode).")

# Metrics row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Watchlist rows", 0 if watch.empty else len(watch))
c2.metric("Trend rows", 0 if trends.empty else len(trends))
c3.metric("Public rows", 0 if public_df.empty else len(public_df))
c4.metric("Last refresh", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

tab1, tab2, tab3 = st.tabs(["Watchlist", "Team Trends", "Public Case Study"])


# =============================================================================
# Tab 1: Watchlist
# =============================================================================
with tab1:
    st.subheader("Watchlist (today)")

    if watch.empty:
        st.warning(
            "No watchlist rows found.\n\n"
            "Expected a CSV in the data source folder named:\n"
            "- watchlist_today.csv (preferred)\n"
            "- watchlist_today_example.csv (fallback)"
        )
    else:
        df = watch.copy()

        # Optional flagged-only logic (if status-like column exists)
        status_col = next((c for c in df.columns if c.lower() in ("status", "flag", "color")), None)
        if show_flagged_only and status_col:
            df = df[df[status_col].astype(str).str.upper().isin(["YELLOW", "ORANGE", "RED"])].copy()

        # Search across common columns
        if watch_search.strip():
            q = watch_search.strip().lower()
            cols = [c for c in df.columns if df[c].dtype == object or str(df[c].dtype).startswith("string")]
            if cols:
                mask = False
                for c in cols:
                    mask = mask | df[c].astype(str).str.lower().str.contains(q, na=False)
                df = df[mask].copy()

        left, right = st.columns([1, 1])

        with left:
            st.markdown("**Table**")
            st.dataframe(df, use_container_width=True)

        with right:
            risk_col = "risk_score" if "risk_score" in df.columns else None
            if risk_col and df[risk_col].notna().any():
                fig = px.histogram(df, x=risk_col, nbins=15, title="Risk score distribution")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No `risk_score` column found (or all missing).")

            if status_col:
                flagged = df[df[status_col].astype(str).str.upper().isin(["YELLOW", "ORANGE", "RED"])].copy()
                st.markdown("**Flagged subset**")
                st.dataframe(flagged, use_container_width=True)


# =============================================================================
# Tab 2: Team Trends
# =============================================================================
with tab2:
    st.subheader("Team trends (rolling 7d)")

    if trends.empty:
        st.warning(
            "No team trend rows found.\n\n"
            "Expected a CSV in the data source folder named:\n"
            "- team_trends_7d.csv (preferred)\n"
            "- team_trends_7d_example.csv (fallback)"
        )
    else:
        df = trends.copy()
        st.dataframe(df, use_container_width=True)

        date_col = "date" if "date" in df.columns else None
        metric_candidates = [c for c in df.columns if c != date_col]
        metric_candidates = [c for c in metric_candidates if pd.api.types.is_numeric_dtype(df[c])]

        if date_col and metric_candidates:
            pick = st.selectbox("Plot metric", metric_candidates, index=0)
            dfp = df.dropna(subset=[date_col]).sort_values(date_col)
            fig = px.line(dfp, x=date_col, y=pick, title=f"Trend: {pick}")
            st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# Tab 3: Public Case Study (multi-season preferred)
# =============================================================================
with tab3:
    st.subheader("Public case study (anonymized availability)")

    if public_df.empty:
        st.warning(
            "No public case study CSV found.\n\n"
            "Expected one of:\n"
            "- public_wnba_availability_anon_multi.csv (preferred)\n"
            "- public_wnba_2025_DAL_availability_anon.csv (fallback)"
        )
    else:
        st.caption("Source: public ESPN boxscore availability via wehoop. Player identities anonymized.")

        df = public_df.copy()

        # Normalize expected columns
        if "player_code" not in df.columns and "athlete_id" in df.columns:
            df["player_code"] = df["athlete_id"].astype(str).map(lambda x: stable_code(x, prefix="DAL25"))

        # Apply sidebar season/team filters (multi-season)
        if not public_multi.empty:
            if season_filter and "season" in df.columns:
                df = df[df["season"].isin(season_filter)].copy()
            if team_filter and "team_abb" in df.columns:
                df = df[df["team_abb"].astype(str).isin(team_filter)].copy()

        st.dataframe(df, use_container_width=True)

        # Scatter: DNP vs total minutes
        if set(["games_dnp", "minutes_total"]).issubset(df.columns):
            color = "season" if "season" in df.columns else None
            fig = px.scatter(
                df,
                x="games_dnp",
                y="minutes_total",
                color=color,
                title="Availability vs workload (anonymized)",
                hover_name="player_code" if "player_code" in df.columns else None,
            )
            st.plotly_chart(fig, use_container_width=True)

        # Top table
        if "minutes_total" in df.columns:
            topn = df.sort_values("minutes_total", ascending=False).head(15)
            st.markdown("**Top workload (minutes_total)**")
            st.dataframe(topn, use_container_width=True)

    if not public_events.empty:
        st.markdown("---")
        st.subheader("Optional: public availability events (game-level)")
        st.dataframe(public_events.head(250), use_container_width=True)