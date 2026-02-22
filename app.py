import os
import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px


# =========================
# Mode switches (Demo vs Private)
# =========================
DATA_DIR = Path(os.getenv("AVAILOPS_DATA_DIR", "demo_data"))
ANON = os.getenv("AVAILOPS_ANON", "1") == "1"

# Stable anonymization salt (Cloud can use secrets; local can use env var)
SALT = os.getenv("AVAILOPS_SALT", "")
if not SALT:
    try:
        SALT = st.secrets.get("AVAILOPS_SALT", "public-demo-salt")
    except Exception:
        SALT = "public-demo-salt"

# Fail-safe: if running in Streamlit Cloud / headless server, force anonymization ON
if os.getenv("STREAMLIT_SERVER_HEADLESS", "").lower() == "true":
    ANON = True


# =========================
# Helpers
# =========================
def stable_code(value: str, prefix="P") -> str:
    h = hashlib.sha256((SALT + str(value)).encode("utf-8")).hexdigest()
    return f"{prefix}-{h[:6]}"


def read_csv_robust(path: Path) -> pd.DataFrame:
    """Reads normal CSVs and fixes the common case where the entire row is in one column."""
    if not path.exists():
        return pd.DataFrame()

    # Try normal CSV first
    try:
        df = pd.read_csv(path)
        if df.shape[1] > 1:
            return df
    except Exception:
        df = None

    # If it parsed as 1 column, attempt to split by comma using header-in-first-cell heuristic
    try:
        df = pd.read_csv(path)
        if df.shape[1] == 1:
            col0 = str(df.columns[0])
            if col0.count(",") >= 2:
                new_cols = [c.strip() for c in col0.split(",")]
                s = df.iloc[:, 0].astype(str).str.strip()
                split = s.str.split(",", expand=True)
                # If split columns match header length, use it
                if split.shape[1] == len(new_cols):
                    split.columns = new_cols
                    split = split.apply(lambda x: x.astype(str).str.strip())
                    return split
    except Exception:
        pass

    # Try semicolon fallback
    try:
        df2 = pd.read_csv(path, sep=";")
        return df2
    except Exception:
        return pd.DataFrame()


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
    drop_names = [c for c in df.columns if c.lower() in ("name", "player_name", "display_name", "athlete_name")]
    df.drop(columns=drop_names, inplace=True, errors="ignore")

    # Drop diagnosis/surgery/medical-note columns if present
    redact = [
        c for c in df.columns
        if any(k in c.lower() for k in ("diagnos", "injur", "surgery", "acl", "fracture", "concussion", "medical_note"))
    ]
    df.drop(columns=redact, inplace=True, errors="ignore")

    return df


def load_csv(names):
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
# Load data
# =========================
watch = load_csv(["watchlist_today.csv", "watchlist_today_example.csv"])
trends = load_csv(["team_trends_7d.csv", "team_trends_7d_example.csv"])
public_summary = load_csv(["public_wnba_2025_DAL_availability_anon.csv"])
public_events = load_csv(["public_availability_events_2025_DAL_anon.csv"])  # optional

# Coerce types
watch = coerce_dates(watch, ("date",))
watch = safe_numeric(watch, ["risk_score", "minutes", "rpe", "flags_count"])

trends = coerce_dates(trends, ("date",))
trends = safe_numeric(trends, ["team_minutes_7d", "team_load_7d", "sleep_avg_7d", "soreness_avg_7d", "flags_count_7d"])

public_summary = safe_numeric(public_summary, ["games_with_box", "games_played", "games_dnp", "minutes_total", "minutes_avg"])
public_events = coerce_dates(public_events, ("game_date", "date"))
public_events = safe_numeric(public_events, ["minutes_played", "did_play", "dnp_flag"])

# Apply anonymization (watchlist only; trends is team-level; public_summary is already anonymized)
if ANON:
    watch = anonymize_df(watch)


# =========================
# UI
# =========================
st.set_page_config(page_title="AvailOps — War Room (Demo)", layout="wide")

st.title("AvailOps — War Room (Demo)")
st.caption("Public demo. Use anonymized/synthetic data only. Demo files live in /demo_data. Private mode reads from AVAILOPS_DATA_DIR.")

DEBUG = os.getenv("AVAILOPS_DEBUG", "0") == "1"

with st.sidebar:
    with st.expander("Runtime settings (click to expand)", expanded=DEBUG):
        st.write(f"**DATA_DIR:** `{DATA_DIR}`")
        st.write(f"**ANON:** `{ANON}`")
        st.caption("Demo reads /demo_data. Private reads from AVAILOPS_DATA_DIR.")
        st.write("**Tip (local private mode):**")
        st.code(
            '$env:AVAILOPS_DATA_DIR="C:\\AvailOps_PrivateData"\n'
            '$env:AVAILOPS_ANON="1"\n'
            '$env:AVAILOPS_SALT="private-internal-salt"\n'
            'streamlit run app.py',
            language="powershell",
        )
# Metrics row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Watchlist rows", 0 if watch.empty else len(watch))
c2.metric("Trend rows", 0 if trends.empty else len(trends))
c3.metric("Public players", 0 if public_summary.empty else len(public_summary))
c4.metric("Last refresh", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

tab1, tab2, tab3 = st.tabs(["Watchlist", "Team Trends", "Public Case Study"])

# -------------------------
# Tab 1: Watchlist
# -------------------------
with tab1:
    st.subheader("Watchlist (today)")
    if watch.empty:
        st.warning("No rows found. Place watchlist_today.csv in DATA_DIR or keep demo_data/watchlist_today.csv.")
    else:
        # Prefer displaying player_code if it exists
        display_cols = list(watch.columns)

        # If there is a status column, show flagged subset first
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

# -------------------------
# Tab 2: Team Trends
# -------------------------
with tab2:
    st.subheader("Team trends (last 7 days)")
    if trends.empty:
        st.warning("No rows found. Place team_trends_7d.csv in DATA_DIR or keep demo_data/team_trends_7d.csv.")
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

# -------------------------
# Tab 3: Public Case Study
# -------------------------
with tab3:
    st.subheader("Public case study (anonymized availability)")
    if public_summary.empty:
        st.warning("No public case study summary found in DATA_DIR.")
    else:
        st.caption("Source: public ESPN boxscore availability via wehoop. Player identities anonymized.")

        st.dataframe(public_summary, use_container_width=True)

        if set(["games_dnp", "minutes_total"]).issubset(public_summary.columns):
            fig = px.scatter(
                public_summary,
                x="games_dnp",
                y="minutes_total",
                title="Availability vs workload (anonymized)",
                hover_name="player_code" if "player_code" in public_summary.columns else None,
            )
            st.plotly_chart(fig, use_container_width=True)

    if not public_events.empty:
        st.markdown("---")
        st.subheader("Optional: public availability events (game-level)")
        st.dataframe(public_events.head(200), use_container_width=True)