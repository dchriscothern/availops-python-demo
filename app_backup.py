import os
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="AvailOps War Room", layout="wide")

ROOT = os.path.dirname(os.path.abspath(__file__))

def load_csv(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception as e:
            st.error(f"Failed to read {path}: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

WATCH_PATH = os.path.join(ROOT, "demo_data", "watchlist_today_example.csv")
TRENDS_PATH = os.path.join(ROOT, "demo_data", "team_trends_7d_example.csv")
PUBLIC_PATH = os.path.join(ROOT, "demo_data", "public_wnba_2025_DAL_availability_anon.csv")

watch = load_csv(WATCH_PATH)
trends = load_csv(TRENDS_PATH)
pub = load_csv(PUBLIC_PATH)

st.title("AvailOps — War Room (Demo)")
st.caption("Public demo. Use anonymized/synthetic data only. Demo files live in /demo_data.")

c1, c2, c3 = st.columns(3)
c1.metric("Watchlist rows", 0 if watch.empty else len(watch))
c2.metric("Trend rows", 0 if trends.empty else len(trends))
c3.metric("Public players", 0 if pub.empty else len(pub))

tab1, tab2, tab3 = st.tabs(["Watchlist", "Team Trends", "Public Case Study"])

# -------------------------
# Tab 1: Watchlist
# -------------------------
with tab1:
    st.subheader("Watchlist (today)")

    if watch.empty:
        st.info("No rows found in demo_data/watchlist_today_example.csv. Add demo rows or copy a snapshot from AvailOps.")
    else:
        # Normalize expected columns if present
        for col in ["date", "athlete_id", "display_name", "status", "risk_score", "flags_triggered", "notes"]:
            if col not in watch.columns:
                watch[col] = None

        # Status filter (if status exists)
        if "status" in watch.columns:
            statuses = sorted([s for s in watch["status"].dropna().unique().tolist()])
            selected = st.multiselect("Filter status", statuses, default=statuses if statuses else None)
            df_show = watch[watch["status"].isin(selected)] if selected else watch
        else:
            df_show = watch

        st.dataframe(df_show, width="stretch")

        # Risk score plot (if numeric)
        if "risk_score" in df_show.columns:
            try:
                df_show["risk_score"] = pd.to_numeric(df_show["risk_score"], errors="coerce")
                fig = px.histogram(df_show.dropna(subset=["risk_score"]), x="risk_score", nbins=20,
                                   title="Risk Score Distribution")
                st.plotly_chart(fig, width="stretch")
            except Exception:
                st.warning("risk_score column exists but could not be plotted as numeric.")

# -------------------------
# Tab 2: Team Trends
# -------------------------
with tab2:
    st.subheader("Team Trends (last 7 days)")

    if trends.empty:
        st.info("Missing demo_data/team_trends_7d_example.csv (optional). Add it to enable trends plotting.")
    else:
        st.dataframe(trends, width="stretch")

        # Try plotting any numeric metric over time if a date column exists
        date_col = next((c for c in trends.columns if "date" in c.lower()), None)
        if date_col:
            df = trends.copy()
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            if numeric_cols:
                metric = st.selectbox("Plot metric", numeric_cols)
                fig = px.line(df.sort_values(date_col), x=date_col, y=metric, title=f"{metric} over time")
                st.plotly_chart(fig, width="stretch")

# -------------------------
# Tab 3: Public Case Study
# -------------------------
with tab3:
    st.subheader("Public Case Study — Availability vs Workload (anonymized)")

    if pub.empty:
        st.info("Missing demo_data/public_wnba_2025_DAL_availability_anon.csv. Copy it from AvailOps GOLD_EXPORT.")
    else:
        st.dataframe(pub, width="stretch")

        if {"minutes_total", "games_dnp"}.issubset(pub.columns):
            df = pub.copy()
            df["minutes_total"] = pd.to_numeric(df["minutes_total"], errors="coerce")
            df["games_dnp"] = pd.to_numeric(df["games_dnp"], errors="coerce")

            fig = px.scatter(
                df,
                x="games_dnp",
                y="minutes_total",
                hover_name="player_code" if "player_code" in df.columns else None,
                title="Availability vs Workload (Public, anonymized)"
            )
            st.plotly_chart(fig, width="stretch")