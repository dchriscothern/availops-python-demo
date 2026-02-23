import os
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px

# =============================================================================
# AvailOps — War Room (Public Demo + Local Private Mode)
#
# HARD FAIL-SAFES:
#  1) If running on Streamlit Cloud/headless => FORCE DEMO mode (private disabled)
#  2) Private mode requires explicit opt-in: AVAILOPS_PRIVATE_OK=1
#  3) Private data directory MUST be OUTSIDE the repo root (prevents accidental commit)
# =============================================================================


# -----------------------------
# Utilities
# -----------------------------
def find_repo_root(start: Path | None = None) -> Path:
    d = (start or Path.cwd()).resolve()
    for _ in range(30):
        if (d / ".git").exists() or (d / "app.py").exists():
            return d
        if d.parent == d:
            break
        d = d.parent
    return Path.cwd().resolve()


def is_cloud_runtime() -> bool:
    # Streamlit Cloud is typically headless.
    return os.getenv("STREAMLIT_SERVER_HEADLESS", "").lower() == "true"


def path_is_inside(child: Path, parent: Path) -> bool:
    try:
        child = child.resolve()
        parent = parent.resolve()
        return parent in child.parents or child == parent
    except Exception:
        return False


def stable_code(value: str, salt: str, prefix="P") -> str:
    h = hashlib.sha256((salt + str(value)).encode("utf-8")).hexdigest()
    return f"{prefix}{h[:8]}"


@st.cache_data(show_spinner=False)
def read_csv_robust(path: Path) -> pd.DataFrame:
    """
    Reads normal CSVs and fixes the common case where the entire row is in one column
    (e.g., headers + values all packed into the first cell).
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

    # If it parsed as 1 column, attempt to split by comma using header-in-first-cell
    try:
        df = pd.read_csv(path)
        if df.shape[1] == 1:
            header = str(df.columns[0])
            if header.count(",") >= 2:
                cols = [c.strip() for c in header.split(",")]
                s = df.iloc[:, 0].astype(str).str.strip()
                split = s.str.split(",", expand=True)
                if split.shape[1] == len(cols):
                    split.columns = cols
                    split = split.apply(lambda x: x.astype(str).str.strip())
                    return split
    except Exception:
        pass

    # Semicolon fallback
    try:
        return pd.read_csv(path, sep=";")
    except Exception:
        return pd.DataFrame()


def safe_to_datetime(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def safe_to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def show_df(df: pd.DataFrame, **kwargs):
    # Streamlit is deprecating use_container_width; support both.
    try:
        st.dataframe(df, width="stretch", **kwargs)
    except TypeError:
        st.dataframe(df, use_container_width=True, **kwargs)


def anonymize_watchlist(df: pd.DataFrame, salt: str) -> pd.DataFrame:
    """
    Anonymizes watchlist by replacing athlete identifiers with stable player codes,
    and dropping name/medical-ish columns.
    """
    if df.empty:
        return df

    df = df.copy()

    # Pick an identifier column
    id_candidates = ["athlete_id", "player_id", "name", "player_name", "display_name"]
    id_col = next((c for c in id_candidates if c in df.columns), None)

    if id_col:
        df["player_code"] = df[id_col].astype(str).map(lambda x: stable_code(x, salt=salt, prefix="ATH_"))
        # Drop the raw identifier to avoid leaking it in screenshots
        df.drop(columns=[id_col], inplace=True, errors="ignore")
    else:
        df["player_code"] = [f"ATH_{i:02d}" for i in range(1, len(df) + 1)]

    # Drop name-like columns (if present)
    drop_names = [c for c in df.columns if c.lower() in ("name", "player_name", "display_name", "athlete_name")]
    df.drop(columns=drop_names, inplace=True, errors="ignore")

    # Drop medical-ish fields by keyword
    redact = [
        c for c in df.columns
        if any(k in c.lower() for k in ("diagnos", "injur", "surgery", "acl", "fracture", "concussion", "medical", "note"))
    ]
    df.drop(columns=redact, inplace=True, errors="ignore")

    # Move player_code to front
    cols = ["player_code"] + [c for c in df.columns if c != "player_code"]
    df = df[cols]
    return df


# -----------------------------
# Mode + privacy gating
# -----------------------------
ROOT = find_repo_root()
CLOUD = is_cloud_runtime()

# Explicit private opt-in (required)
PRIVATE_OK = os.getenv("AVAILOPS_PRIVATE_OK", "0") == "1"
REQUEST_PRIVATE = (os.getenv("AVAILOPS_MODE", "").lower() == "private") or bool(os.getenv("AVAILOPS_DATA_DIR", ""))

# Default: DEMO mode
MODE = "DEMO"
DATA_DIR = (ROOT / "demo_data").resolve()
DATA_SOURCE_LABEL = "demo_data (bundled)"

# Private mode rules
if CLOUD:
    # Hard fail-safe: Cloud can NEVER run private mode
    MODE = "DEMO"
else:
    if REQUEST_PRIVATE and PRIVATE_OK:
        candidate = Path(os.getenv("AVAILOPS_DATA_DIR", "")).expanduser()
        if candidate:
            candidate = candidate.resolve()

        if not candidate or not candidate.exists():
            MODE = "DEMO"
        else:
            # Hard fail-safe: private dir must NOT live inside the repo
            if path_is_inside(candidate, ROOT):
                MODE = "DEMO"
                PRIVATE_OK = False  # force off
            else:
                MODE = "PRIVATE"
                DATA_DIR = candidate
                DATA_SOURCE_LABEL = f"{candidate.name} (local)"

# Anonymization behavior
# - DEMO: forced anonymized
# - PRIVATE: default anonymized unless explicitly allowed
ALLOW_CLEAR = os.getenv("AVAILOPS_ALLOW_CLEAR", "0") == "1"
ANON = True if MODE == "DEMO" else (os.getenv("AVAILOPS_ANON", "1") == "1")
if MODE == "PRIVATE" and ALLOW_CLEAR and not CLOUD:
    # allow clear names only in local private mode
    ANON = False

# Salt
SALT = os.getenv("AVAILOPS_SALT", "")
if not SALT:
    try:
        SALT = st.secrets.get("AVAILOPS_SALT", "public-demo-salt")
    except Exception:
        SALT = "public-demo-salt"

RUNTIME = "CLOUD" if CLOUD else "LOCAL"


# -----------------------------
# Load data
# -----------------------------
def load_first(names: list[str], directory: Path) -> tuple[pd.DataFrame, Path | None]:
    for n in names:
        p = directory / n
        if p.exists():
            return read_csv_robust(p), p
    return pd.DataFrame(), None


# Watchlist + trends come from selected data dir (demo or private)
watch, watch_path = load_first(["watchlist_today.csv", "watchlist_today_example.csv"], DATA_DIR)
trends, trends_path = load_first(["team_trends_7d.csv", "team_trends_7d_example.csv"], DATA_DIR)

# Public case-study CSV:
# Prefer multi-season file if present in *current* DATA_DIR, else fallback to demo_data,
# else fallback to legacy single-season DAL file.
public_multi, public_multi_path = load_first(
    ["public_wnba_availability_anon_multi.csv", "public_wnba_availability_anon_multi_example.csv"],
    DATA_DIR
)
if public_multi.empty:
    public_multi, public_multi_path = load_first(
        ["public_wnba_availability_anon_multi.csv", "public_wnba_availability_anon_multi_example.csv"],
        (ROOT / "demo_data").resolve()
    )

public_single, public_single_path = load_first(
    ["public_wnba_2025_DAL_availability_anon.csv"],
    DATA_DIR
)
if public_single.empty:
    public_single, public_single_path = load_first(
        ["public_wnba_2025_DAL_availability_anon.csv"],
        (ROOT / "demo_data").resolve()
    )

# Coerce types (best effort)
watch = safe_to_datetime(watch, "date")
watch = safe_to_numeric(watch, ["risk_score", "minutes", "rpe", "flags_count"])

trends = safe_to_datetime(trends, "date")
# Make all non-date columns numeric if possible
if not trends.empty:
    for c in trends.columns:
        if c != "date":
            trends[c] = pd.to_numeric(trends[c], errors="coerce")

# Public multi schema
if not public_multi.empty:
    for c in ["season", "games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"]:
        if c in public_multi.columns:
            public_multi[c] = pd.to_numeric(public_multi[c], errors="coerce")

# Public single schema
if not public_single.empty:
    for c in ["games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"]:
        if c in public_single.columns:
            public_single[c] = pd.to_numeric(public_single[c], errors="coerce")

# Apply anonymization to watchlist if enabled
if ANON and not watch.empty:
    watch = anonymize_watchlist(watch, salt=SALT)


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="AvailOps — War Room", layout="wide")

st.title("AvailOps — War Room")
st.caption("Decision-support view for availability operations (public demo + local private mode).")

# Sidebar (clean + professional)
with st.sidebar:
    st.markdown("## AvailOps War Room")
    mode_badge = "DEMO (Public-safe)" if MODE == "DEMO" else ("PRIVATE (Clear)" if not ANON else "PRIVATE (Anonymized)")
    st.markdown(f"**Mode:** `{RUNTIME}  |  {mode_badge}`")
    st.markdown(f"**Data source:** `{DATA_SOURCE_LABEL}`")

    if CLOUD:
        st.info("Streamlit Cloud runs **DEMO only**. Private mode is disabled by design.")

    # Data health
    st.markdown("---")
    st.markdown("### Data health")
    st.write(f"Watchlist rows: **{0 if watch.empty else len(watch)}**")
    st.write(f"Trend rows: **{0 if trends.empty else len(trends)}**")

    # Optional: show file mtimes (safe)
    with st.expander("Show file details", expanded=False):
        def fmt(p: Path | None):
            if not p:
                return "—"
            try:
                return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return "—"

        st.write(f"watchlist file: `{watch_path.name if watch_path else '—'}`")
        st.write(f"watchlist mtime: `{fmt(watch_path)}`")
        st.write(f"trends file: `{trends_path.name if trends_path else '—'}`")
        st.write(f"trends mtime: `{fmt(trends_path)}`")
        st.write(f"public multi: `{public_multi_path.name if public_multi_path else '—'}`")
        st.write(f"public single: `{public_single_path.name if public_single_path else '—'}`")

    st.markdown("---")
    with st.expander("How to run modes", expanded=False):
        st.markdown("**Demo mode (public-safe):**")
        st.code(
            "cd C:\\GitHub\\availops-python-demo\\availops-python-demo\n"
            "streamlit run app.py",
            language="powershell",
        )
        st.markdown("**Private mode (LOCAL only, anonymized):**")
        st.code(
            "$env:AVAILOPS_PRIVATE_OK='1'\n"
            "$env:AVAILOPS_MODE='private'\n"
            "$env:AVAILOPS_DATA_DIR='C:\\AvailOps_PrivateData'\n"
            "$env:AVAILOPS_ANON='1'\n"
            "$env:AVAILOPS_SALT='internal-salt'\n"
            "streamlit run app.py",
            language="powershell",
        )
        st.markdown("**Private mode (LOCAL only, clear names — discouraged):**")
        st.code(
            "$env:AVAILOPS_ALLOW_CLEAR='1'\n"
            "$env:AVAILOPS_ANON='0'\n"
            "streamlit run app.py",
            language="powershell",
        )

# Top metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Watchlist rows", 0 if watch.empty else len(watch))
c2.metric("Trend rows", 0 if trends.empty else len(trends))
pub_rows = 0
if not public_multi.empty:
    pub_rows = len(public_multi)
elif not public_single.empty:
    pub_rows = len(public_single)
c3.metric("Public rows", pub_rows)
c4.metric("Last refresh", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

tab1, tab2, tab3 = st.tabs(["Watchlist", "Team Trends", "Public Case Study"])


# -------------------------
# Tab 1: Watchlist
# -------------------------
with tab1:
    st.subheader("Watchlist (today)")

    if watch.empty:
        st.warning(
            "No watchlist rows found.\n\n"
            "Expected in your data folder:\n"
            "- watchlist_today.csv (preferred)\n"
            "- watchlist_today_example.csv (fallback)"
        )
    else:
        # Flagged subset if status/color exists
        status_col = next((c for c in watch.columns if c.lower() in ("status", "flag", "color")), None)
        risk_col = "risk_score" if "risk_score" in watch.columns else None

        left, right = st.columns([1.3, 1])

        with left:
            st.markdown("**All rows**")
            show_df(watch)

        with right:
            if status_col:
                flagged = watch[watch[status_col].astype(str).str.upper().isin(["YELLOW", "ORANGE", "RED"])].copy()
                st.markdown("**Flagged subset (YELLOW/ORANGE/RED)**")
                show_df(flagged)
            else:
                st.info("No `status/color` column found. Showing risk distribution if available.")

            if risk_col and watch[risk_col].notna().any():
                fig = px.histogram(watch, x=risk_col, nbins=15, title="Risk score distribution")
                st.plotly_chart(fig, use_container_width=True)


# -------------------------
# Tab 2: Team Trends
# -------------------------
with tab2:
    st.subheader("Team trends")

    if trends.empty:
        st.warning(
            "No trend rows found.\n\n"
            "Expected in your data folder:\n"
            "- team_trends_7d.csv (preferred)\n"
            "- team_trends_7d_example.csv (fallback)"
        )
    else:
        show_df(trends)

        date_col = "date" if "date" in trends.columns else None
        metric_candidates = [c for c in trends.columns if c != date_col]
        metric_candidates = [c for c in metric_candidates if pd.api.types.is_numeric_dtype(trends[c])]

        if date_col and metric_candidates:
            pick = st.selectbox("Plot metric", metric_candidates, index=0)
            dfp = trends.dropna(subset=[date_col]).sort_values(date_col)
            fig = px.line(dfp, x=date_col, y=pick, title=f"Trend: {pick}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Trend plotting requires a `date` column and at least one numeric metric column.")


# -------------------------
# Tab 3: Public Case Study
# -------------------------
with tab3:
    st.subheader("Public case study (anonymized availability)")
    st.caption("Source: public ESPN boxscore availability via wehoop. Player identities anonymized.")

    # Prefer multi-season dataset if available
    if not public_multi.empty and {"season", "team_abb"}.issubset(public_multi.columns):
        df_pub = public_multi.copy()

        # Filters
        seasons = sorted([int(s) for s in df_pub["season"].dropna().unique().tolist()])
        teams = sorted([str(t) for t in df_pub["team_abb"].dropna().unique().tolist()])

        colf1, colf2 = st.columns([1, 1])
        with colf1:
            season_sel = st.multiselect("Season", seasons, default=seasons[-1:] if seasons else [])
        with colf2:
            team_sel = st.multiselect("Team", teams, default=["DAL"] if "DAL" in teams else teams[:1])

        if season_sel:
            df_pub = df_pub[df_pub["season"].isin(season_sel)]
        if team_sel:
            df_pub = df_pub[df_pub["team_abb"].isin(team_sel)]

        show_df(df_pub)

        # Charts (if expected columns exist)
        if {"games_dnp", "minutes_total"}.issubset(df_pub.columns):
            fig = px.scatter(
                df_pub,
                x="games_dnp",
                y="minutes_total",
                color="team_abb" if "team_abb" in df_pub.columns else None,
                hover_name="player_code" if "player_code" in df_pub.columns else None,
                title="Availability vs workload (anonymized)",
            )
            st.plotly_chart(fig, use_container_width=True)

        # Download filtered
        st.download_button(
            "Download filtered CSV",
            df_pub.to_csv(index=False).encode("utf-8"),
            file_name="public_case_filtered.csv",
            mime="text/csv",
        )

    elif not public_single.empty:
        df_pub = public_single.copy()
        show_df(df_pub)

        if {"games_dnp", "minutes_total"}.issubset(df_pub.columns):
            fig = px.scatter(
                df_pub,
                x="games_dnp",
                y="minutes_total",
                hover_name="player_code" if "player_code" in df_pub.columns else None,
                title="Availability vs workload (anonymized)",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.download_button(
            "Download CSV",
            df_pub.to_csv(index=False).encode("utf-8"),
            file_name="public_case.csv",
            mime="text/csv",
        )
    else:
        st.warning(
            "No public case-study CSV found.\n\n"
            "Expected:\n"
            "- public_wnba_availability_anon_multi.csv (multi-season)\n"
            "or\n"
            "- public_wnba_2025_DAL_availability_anon.csv"
        )