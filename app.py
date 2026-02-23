import os
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px


# ==========================================================
# Repo + environment detection
# ==========================================================
def find_repo_root(start: Path) -> Path:
    d = start.resolve()
    for _ in range(30):
        if (d / ".git").exists():
            return d
        if d.parent == d:
            break
        d = d.parent
    return start.resolve()


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = find_repo_root(APP_DIR)
DEMO_DIR = REPO_ROOT / "demo_data"


def is_cloud_runtime() -> bool:
    # Streamlit Cloud / headless environments. (This is the safe default trigger.)
    return os.getenv("STREAMLIT_SERVER_HEADLESS", "").lower() == "true" or \
           os.getenv("STREAMLIT_RUNTIME_ENV", "").lower() in {"cloud", "communitycloud"} or \
           os.getenv("STREAMLIT_CLOUD", "").lower() == "true"


IS_CLOUD = is_cloud_runtime()


def resolve_data_dir() -> Path:
    req = os.getenv("AVAILOPS_DATA_DIR", "").strip()
    if not req:
        return DEMO_DIR
    return Path(req).expanduser()


def path_is_within(child: Path, parent: Path) -> bool:
    try:
        child_r = child.resolve()
    except Exception:
        child_r = Path(str(child))
    try:
        parent_r = parent.resolve()
    except Exception:
        parent_r = Path(str(parent))
    return str(child_r).lower().startswith(str(parent_r).lower())


REQUESTED_DATA_DIR = resolve_data_dir()

# ==========================================================
# HARD FAIL-SAFE: deployed == demo-only + anonymized only
# ==========================================================
if IS_CLOUD:
    DATA_DIR = DEMO_DIR
    MODE_LABEL = "PUBLIC DEMO (deployed)"
    FORCE_ANON = True
else:
    # Local run
    if path_is_within(REQUESTED_DATA_DIR, REPO_ROOT):
        # Anything inside the repo is treated as demo-safe
        DATA_DIR = REQUESTED_DATA_DIR
        MODE_LABEL = "LOCAL DEMO"
        FORCE_ANON = True
    else:
        DATA_DIR = REQUESTED_DATA_DIR
        MODE_LABEL = "LOCAL PRIVATE"
        FORCE_ANON = False

# Anonymization toggle (env-driven) but enforced by fail-safe above
ANON_ENV = os.getenv("AVAILOPS_ANON", "1").strip()
ANON_REQUESTED = (ANON_ENV != "0")

ALLOW_CLEAR = os.getenv("AVAILOPS_ALLOW_CLEAR", "0").strip() == "1"

# Salt (stable mapping). In Cloud, you can store it in Streamlit secrets; default is safe.
SALT = os.getenv("AVAILOPS_SALT", "").strip()
if not SALT:
    try:
        SALT = st.secrets.get("AVAILOPS_SALT", "public-demo-salt")
    except Exception:
        SALT = "public-demo-salt"

# Enforce anonymization rules
if MODE_LABEL.startswith("PUBLIC DEMO"):
    ANON = True
elif FORCE_ANON:
    ANON = True
else:
    # Local private: allow clear ONLY if explicitly permitted
    if ANON_REQUESTED:
        ANON = True
    else:
        # They asked for clear names. Only allow if user opts-in explicitly and data_dir is outside repo.
        if ALLOW_CLEAR and (not path_is_within(DATA_DIR, REPO_ROOT)):
            ANON = False
        else:
            ANON = True  # fallback to safe behavior


# ==========================================================
# Streamlit display helpers (avoid use_container_width warnings)
# ==========================================================
def st_df(df: pd.DataFrame, **kwargs):
    # Newer Streamlit prefers width="stretch"
    try:
        return st.dataframe(df, width="stretch", **kwargs)
    except TypeError:
        return st.dataframe(df, use_container_width=True, **kwargs)


def st_plot(fig, **kwargs):
    try:
        return st.plotly_chart(fig, width="stretch", **kwargs)
    except TypeError:
        return st.plotly_chart(fig, use_container_width=True, **kwargs)


# ==========================================================
# CSV reading (robust against "everything in one column" files)
# ==========================================================
def read_csv_robust(path: Path) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame()

    # Normal CSV attempt
    try:
        df = pd.read_csv(path)
        if df.shape[1] > 1:
            return df
    except Exception:
        df = None

    # One-column "all values in one cell" fix (header embedded in column name)
    try:
        df = pd.read_csv(path)
        if df.shape[1] == 1:
            header = str(df.columns[0])
            if header.count(",") >= 1:
                cols = [c.strip() for c in header.split(",")]
                s = df.iloc[:, 0].astype(str).str.strip()
                split = s.str.split(",", expand=True)
                if split.shape[1] == len(cols):
                    split.columns = cols
                    # strip whitespace
                    for c in split.columns:
                        split[c] = split[c].astype(str).str.strip()
                    return split
    except Exception:
        pass

    # Semicolon fallback
    try:
        return pd.read_csv(path, sep=";")
    except Exception:
        return pd.DataFrame()


def load_first(filenames, search_dirs):
    for d in search_dirs:
        for name in filenames:
            p = Path(d) / name
            if p.exists():
                return p, read_csv_robust(p)
    return None, pd.DataFrame()


def coerce_date(df: pd.DataFrame, candidates=("date", "game_date")) -> pd.DataFrame:
    if df.empty:
        return df
    for c in candidates:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def coerce_numeric(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    if df.empty:
        return df
    if cols is None:
        # Try converting everything except obvious strings
        for c in df.columns:
            if c.lower() in {"player_code", "athlete_id", "status", "note", "notes", "team_abb"}:
                continue
            df[c] = pd.to_numeric(df[c], errors="ignore")
        return df
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# ==========================================================
# Anonymization
# ==========================================================
def stable_code(value: str, prefix="ATH") -> str:
    h = hashlib.sha256((SALT + str(value)).encode("utf-8")).hexdigest()
    return f"{prefix}_{h[:6].upper()}"


def anonymize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Anonymize player identifiers + remove name/diagnosis-like fields."""
    if df.empty:
        return df
    df = df.copy()

    # Create player_code
    id_candidates = ["athlete_id", "player_id", "player_code", "name", "player_name", "display_name"]
    id_col = next((c for c in id_candidates if c in df.columns), None)

    if "player_code" not in df.columns:
        if id_col:
            df["player_code"] = df[id_col].astype(str).map(lambda x: stable_code(x, prefix="ATH"))
        else:
            df["player_code"] = [f"ATH_{i:03d}" for i in range(1, len(df) + 1)]

    # Drop name-like columns
    drop_names = [c for c in df.columns if c.lower() in ("name", "player_name", "display_name", "athlete_name")]
    df.drop(columns=drop_names, inplace=True, errors="ignore")

    # Drop medical-ish columns if present
    redact = [
        c for c in df.columns
        if any(k in c.lower() for k in ("diagnos", "injur", "surgery", "acl", "fracture", "concussion", "medical"))
    ]
    df.drop(columns=redact, inplace=True, errors="ignore")
    return df


# ==========================================================
# Load data (private dir first; public/demo fallback in demo_data)
# ==========================================================
SEARCH_DIRS_PRIVATE_FIRST = [DATA_DIR, DEMO_DIR] if DATA_DIR != DEMO_DIR else [DEMO_DIR]

watch_path, watch = load_first(
    ["watchlist_today.csv", "watchlist_today_example.csv"],
    SEARCH_DIRS_PRIVATE_FIRST,
)

trends_path, trends = load_first(
    ["team_trends_7d.csv", "team_trends_7d_example.csv"],
    SEARCH_DIRS_PRIVATE_FIRST,
)

public_path, public_multi = load_first(
    ["public_wnba_availability_anon_multi.csv", "public_wnba_availability_anon_multi_example.csv",
     "public_wnba_2025_DAL_availability_anon.csv"],
    SEARCH_DIRS_PRIVATE_FIRST,
)

# Type coercion
watch = coerce_date(watch, ("date",))
watch = coerce_numeric(watch, ["risk_score", "minutes", "rpe", "flags_count"])

trends = coerce_date(trends, ("date",))
# Convert all numeric-looking columns except date
if not trends.empty:
    for c in trends.columns:
        if c != "date":
            trends[c] = pd.to_numeric(trends[c], errors="coerce")

if not public_multi.empty:
    # Common multi-season schema
    for c in ["season", "games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"]:
        if c in public_multi.columns:
            public_multi[c] = pd.to_numeric(public_multi[c], errors="coerce")
    if "team_abb" in public_multi.columns:
        public_multi["team_abb"] = public_multi["team_abb"].astype(str).str.upper().str.strip()
    if "player_code" in public_multi.columns:
        public_multi["player_code"] = public_multi["player_code"].astype(str).str.strip()

# Apply anonymization to watchlist when required
if ANON and not watch.empty:
    watch = anonymize_df(watch)


# ==========================================================
# UI
# ==========================================================
st.set_page_config(page_title="AvailOps — War Room", layout="wide")
st.title("AvailOps — War Room")
st.caption("Decision-support view for availability operations (public demo + local private mode).")

# Sidebar (clean + professional)
with st.sidebar:
    st.subheader("AvailOps War Room")

    # Mode badge
    if MODE_LABEL.startswith("PUBLIC DEMO"):
        st.success(f"Mode: {MODE_LABEL}")
        st.caption("Fail-safe active: demo_data only + anonymized only.")
    elif MODE_LABEL == "LOCAL DEMO":
        st.info(f"Mode: {MODE_LABEL}")
        st.caption("Repo-contained data → anonymized by default.")
    else:
        if ANON:
            st.success("Mode: LOCAL PRIVATE (Anonymized)")
        else:
            st.warning("Mode: LOCAL PRIVATE (Identifiable)")
        st.caption("Local-only. Not intended for public deployment.")

    # Data source label (don’t spam full paths unless debugging)
    src_label = "demo_data (repo)" if DATA_DIR == DEMO_DIR else "private_data (local)"
    st.write(f"**Data source:** `{src_label}`")

    # Data health
    st.markdown("---")
    st.markdown("### Data health")

    def health_line(label, p: Path | None, df: pd.DataFrame):
        if not p:
            return f"**{label}:** ❌ not found"
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            mtime = "unknown"
        return f"**{label}:** ✅ {len(df)} rows  •  _{p.name}_  •  {mtime}"

    st.markdown(health_line("Watchlist", watch_path, watch))
    st.markdown(health_line("Team trends", trends_path, trends))
    st.markdown(health_line("Public multi", public_path, public_multi))

    # Minimal operator controls
    st.markdown("---")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    with st.expander("Privacy & fail-safes", expanded=False):
        st.markdown(
            "- **Deployed mode**: forced to `demo_data/` and **ANON always ON**.\n"
            "- **Local private mode**: set `AVAILOPS_DATA_DIR` to a folder **outside the repo**.\n"
            "- **Identifiable mode** (not recommended): requires `AVAILOPS_ALLOW_CLEAR=1` and local private path.\n"
            "- The app is **read-only** (does not write files)."
        )


# Top metrics row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Watchlist rows", 0 if watch.empty else len(watch))
c2.metric("Trend rows", 0 if trends.empty else len(trends))
c3.metric("Public rows", 0 if public_multi.empty else len(public_multi))
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
            f"Expected in your data folder ({DATA_DIR}):\n"
            "- watchlist_today.csv (preferred)\n"
            "- watchlist_today_example.csv (fallback)"
        )
    else:
        # Optional filters
        status_col = next((c for c in watch.columns if c.lower() in ("status", "flag", "color")), None)
        risk_col = "risk_score" if "risk_score" in watch.columns else None

        if status_col:
            opts = sorted({str(x).upper() for x in watch[status_col].dropna().unique()})
            pick = st.multiselect("Filter status", opts, default=[x for x in opts if x in {"YELLOW", "ORANGE", "RED"}] or opts)
            fdf = watch[watch[status_col].astype(str).str.upper().isin(pick)].copy()
        else:
            fdf = watch.copy()

        st_df(fdf)

        if risk_col and pd.to_numeric(watch[risk_col], errors="coerce").notna().any():
            fig = px.histogram(watch, x=risk_col, nbins=15, title="Risk score distribution")
            st_plot(fig)


# -------------------------
# Tab 2: Team Trends
# -------------------------
with tab2:
    st.subheader("Team trends (rolling window)")

    if trends.empty:
        st.warning(
            "No trend rows found.\n\n"
            f"Expected in your data folder ({DATA_DIR}):\n"
            "- team_trends_7d.csv (preferred)\n"
            "- team_trends_7d_example.csv (fallback)"
        )
    else:
        st_df(trends)

        date_col = "date" if "date" in trends.columns else None
        numeric_cols = [c for c in trends.columns if c != date_col and pd.api.types.is_numeric_dtype(trends[c])]

        if date_col and numeric_cols:
            metric = st.selectbox("Plot metric", numeric_cols, index=0)
            dfp = trends.dropna(subset=[date_col]).sort_values(date_col)
            fig = px.line(dfp, x=date_col, y=metric, title=f"Trend: {metric}")
            st_plot(fig)


# -------------------------
# Tab 3: Public Case Study (multi-season)
# -------------------------
with tab3:
    st.subheader("Public case study (anonymized availability)")

    if public_multi.empty:
        st.warning(
            "No public case-study file found.\n\n"
            "Expected:\n"
            "- demo_data/public_wnba_availability_anon_multi.csv (preferred)\n"
            "- demo_data/public_wnba_2025_DAL_availability_anon.csv (fallback)"
        )
    else:
        st.caption("Source: public ESPN boxscores via wehoop. Player identities anonymized.")

        # Detect schema
        team_col = "team_abb" if "team_abb" in public_multi.columns else None
        season_col = "season" if "season" in public_multi.columns else None

        dfp = public_multi.copy()

        # Default: if PUBLIC DEMO, pin to DAL if present (job-targeted and cleaner)
        if MODE_LABEL.startswith("PUBLIC DEMO") and team_col and "DAL" in set(dfp[team_col].dropna().unique()):
            teams = ["DAL"]
            st.info("Public demo is pinned to DAL. Run locally to explore multiple teams.")
        else:
            if team_col:
                all_teams = sorted([t for t in dfp[team_col].dropna().unique()])
                teams = st.multiselect("Team", all_teams, default=all_teams[:1] if all_teams else [])
            else:
                teams = []

        if season_col:
            all_seasons = sorted([int(s) for s in dfp[season_col].dropna().unique()])
            seasons = st.multiselect("Season", all_seasons, default=all_seasons[-1:] if all_seasons else [])
        else:
            seasons = []

        if team_col and teams:
            dfp = dfp[dfp[team_col].isin(teams)]
        if season_col and seasons:
            dfp = dfp[dfp[season_col].isin(seasons)]

        st_df(dfp)

        # Charts if columns exist
        if set(["games_dnp", "minutes_total"]).issubset(dfp.columns):
            fig = px.scatter(
                dfp,
                x="games_dnp",
                y="minutes_total",
                color=season_col if season_col else None,
                hover_name="player_code" if "player_code" in dfp.columns else None,
                title="Availability vs workload (anonymized)",
            )
            st_plot(fig)

        # Concentration (top-5 share)
        if "minutes_total" in dfp.columns and dfp["minutes_total"].notna().any():
            tmp = dfp.copy()
            tmp["minutes_total"] = pd.to_numeric(tmp["minutes_total"], errors="coerce").fillna(0.0)
            tot = float(tmp["minutes_total"].sum())
            if tot > 0:
                top5 = float(tmp.sort_values("minutes_total", ascending=False).head(5)["minutes_total"].sum())
                st.metric("Top-5 minutes share", f"{(100.0 * top5 / tot):.1f}%")