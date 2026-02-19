"""
AvailOps — Availability Operations System
Streamlit Dashboard - Interactive Visualization
"""

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pickle

# Page config
st.set_page_config(
    page_title="AvailOps — Availability Ops",
    page_icon="🏀",
    layout="wide"
)

# Load ML model
@st.cache_resource
def load_ml_model():
    try:
        with open('availops_risk_model.pkl', 'rb') as f:
            saved = pickle.load(f)
        return saved
    except:
        return None

# Database connection
@st.cache_resource
def get_database_connection():
    return sqlite3.connect('availops_demo.db', check_same_thread=False)

conn = get_database_connection()

# Title and header
st.title("🏀 AvailOps — Availability Operations System")
st.markdown("*Availability decision support for high-performance sport (synthetic demo data)*")
st.markdown("---")

# Sidebar - Date selection and filters
st.sidebar.header("Filters")

# Get date range from data
min_date = pd.read_sql_query("SELECT MIN(date) as date FROM wellness", conn)['date'][0]
max_date = pd.read_sql_query("SELECT MAX(date) as date FROM wellness", conn)['date'][0]

selected_date = st.sidebar.date_input(
    "Select Date",
    value=pd.to_datetime(max_date),
    min_value=pd.to_datetime(min_date),
    max_value=pd.to_datetime(max_date)
)

# Position filter
positions = ['All'] + list(pd.read_sql_query("SELECT DISTINCT position FROM players ORDER BY position", conn)['position'])
selected_position = st.sidebar.selectbox("Filter by Position", positions)

st.sidebar.markdown("---")
st.sidebar.markdown("### About This System")
st.sidebar.info(
    "This dashboard integrates wellness, training load, and force plate data "
    "to flag short-horizon availability risk and support daily decision-making."
)

# Main content - Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 Team Overview", "👤 Player Profiles", "⚠️ Risk Analysis", "📈 Trends"])

with tab1:
    st.header("Team Overview - " + str(selected_date))
    
    # Current team status query
    query = f"""
        SELECT 
            p.name,
            p.position,
            w.sleep_hours,
            w.soreness,
            w.stress,
            a.acwr,
            f.asymmetry_percent
        FROM players p
        LEFT JOIN wellness w ON p.player_id = w.player_id
        LEFT JOIN acwr a ON p.player_id = a.player_id AND w.date = a.date
        LEFT JOIN force_plate f ON p.player_id = f.player_id AND w.date = f.date
        WHERE w.date = '{selected_date}'
    """
    
    if selected_position != 'All':
        query += f" AND p.position = '{selected_position}'"
    
    team_data = pd.read_sql_query(query, conn)
    
    # Calculate risk score (simplified)
    def calculate_simple_risk(row):
        risk = 0
        if row['sleep_hours'] < 6:
            risk += 25
        if row['soreness'] >= 7:
            risk += 25
        if pd.notna(row['acwr']) and row['acwr'] > 1.5:
            risk += 25
        if pd.notna(row['asymmetry_percent']) and row['asymmetry_percent'] > 15:
            risk += 25
        return risk
    
    team_data['risk_score'] = team_data.apply(calculate_simple_risk, axis=1)
    team_data['risk_category'] = team_data['risk_score'].apply(
        lambda x: 'High' if x >= 50 else ('Medium' if x >= 25 else 'Low')
    )
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        high_risk = len(team_data[team_data['risk_category'] == 'High'])
        st.metric("High Risk Players", high_risk, delta=None)
    
    with col2:
        avg_sleep = team_data['sleep_hours'].mean()
        st.metric("Avg Sleep (hours)", f"{avg_sleep:.1f}", 
                 delta=f"{avg_sleep - 7.5:.1f} vs optimal")
    
    with col3:
        avg_soreness = team_data['soreness'].mean()
        st.metric("Avg Soreness", f"{avg_soreness:.1f}/10",
                 delta=f"{avg_soreness - 3:.1f} vs baseline")
    
    with col4:
        high_load = len(team_data[team_data['acwr'] > 1.3])
        st.metric("Elevated Load Players", high_load)
    
    st.markdown("---")
    
    # Team risk heatmap
    st.subheader("Team Risk Status")
    
    # Color code by risk
    def get_risk_color(risk):
        if risk == 'High':
            return 'background-color: #ff4444'
        elif risk == 'Medium':
            return 'background-color: #ffaa00'
        else:
            return 'background-color: #44ff44'
    
    # Display table with color coding
    display_cols = ['name', 'position', 'sleep_hours', 'soreness', 'acwr', 'risk_category']
    styled_df = team_data[display_cols].style.applymap(
        get_risk_color, 
        subset=['risk_category']
    ).format({
        'sleep_hours': '{:.1f}',
        'soreness': '{:.0f}',
        'acwr': '{:.2f}'
    })
    
    st.dataframe(styled_df, use_container_width=True)

with tab2:
    st.header("Individual Player Profiles")
    
    # Player selection
    players = pd.read_sql_query("SELECT name FROM players ORDER BY name", conn)['name'].tolist()
    selected_player = st.selectbox("Select Player", players)
    
    # Get player ID
    player_id = pd.read_sql_query(
        f"SELECT player_id FROM players WHERE name = '{selected_player}'", 
        conn
    )['player_id'][0]
    
    # Get player data (last 30 days)
    end_date = selected_date
    start_date = pd.to_datetime(end_date) - timedelta(days=30)
    
    player_query = f"""
        SELECT 
            w.date,
            w.sleep_hours,
            w.soreness,
            w.stress,
            t.game_minutes,
            t.practice_minutes,
            a.acwr,
            f.asymmetry_percent,
            f.cmj_height_cm
        FROM wellness w
        JOIN training_load t ON w.player_id = t.player_id AND w.date = t.date
        LEFT JOIN acwr a ON w.player_id = a.player_id AND w.date = a.date
        LEFT JOIN force_plate f ON w.player_id = f.player_id AND w.date = f.date
        WHERE w.player_id = {player_id}
        AND w.date >= '{start_date}'
        AND w.date <= '{end_date}'
        ORDER BY w.date
    """
    
    player_data = pd.read_sql_query(player_query, conn, parse_dates=['date'])
    
    if len(player_data) > 0:
        # Wellness trends
        st.subheader("Wellness Trends (30 Days)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig_sleep = px.line(player_data, x='date', y='sleep_hours', 
                               title='Sleep Hours',
                               markers=True)
            fig_sleep.add_hline(y=7.5, line_dash="dash", line_color="green", 
                               annotation_text="Optimal")
            fig_sleep.add_hline(y=6, line_dash="dash", line_color="red", 
                               annotation_text="Low")
            st.plotly_chart(fig_sleep, use_container_width=True)
        
        with col2:
            fig_soreness = px.line(player_data, x='date', y='soreness',
                                  title='Soreness (1-10)',
                                  markers=True)
            fig_soreness.add_hline(y=7, line_dash="dash", line_color="red",
                                  annotation_text="High")
            st.plotly_chart(fig_soreness, use_container_width=True)
        
        # Load management
        st.subheader("Load Management")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig_acwr = px.line(player_data, x='date', y='acwr',
                              title='Acute:Chronic Workload Ratio',
                              markers=True)
            fig_acwr.add_hline(y=1.5, line_dash="dash", line_color="red",
                              annotation_text="High Risk")
            fig_acwr.add_hline(y=0.8, line_dash="dash", line_color="orange",
                              annotation_text="Low Load")
            st.plotly_chart(fig_acwr, use_container_width=True)
        
        with col2:
            # Create combined minutes chart
            player_data['total_minutes'] = player_data['game_minutes'] + player_data['practice_minutes']
            fig_minutes = px.bar(player_data, x='date', y=['game_minutes', 'practice_minutes'],
                                title='Training & Game Minutes',
                                barmode='stack')
            st.plotly_chart(fig_minutes, use_container_width=True)
        
        # Force plate data (if available)
        fp_data = player_data[player_data['asymmetry_percent'].notna()]
        if len(fp_data) > 0:
            st.subheader("Force Plate Testing")
            
            col1, col2 = st.columns(2)
            
            with col1:
                fig_asym = px.line(fp_data, x='date', y='asymmetry_percent',
                                  title='Bilateral Asymmetry (%)',
                                  markers=True)
                fig_asym.add_hline(y=10, line_dash="dash", line_color="orange",
                                  annotation_text="Caution")
                fig_asym.add_hline(y=15, line_dash="dash", line_color="red",
                                  annotation_text="High Risk")
                st.plotly_chart(fig_asym, use_container_width=True)
            
            with col2:
                fig_cmj = px.line(fp_data, x='date', y='cmj_height_cm',
                                 title='CMJ Height (cm)',
                                 markers=True)
                st.plotly_chart(fig_cmj, use_container_width=True)
    
    else:
        st.warning("No data available for selected player in this date range")

with tab3:
    st.header("Availability Risk Analysis (Demo)")
    
    # Load availability risk output if available
    try:
        risk_df = pd.read_csv('current_availability_risk.csv')
        
        st.subheader("Current Availability Risk Output")
        
        # Create risk visualization
        fig_risk = px.bar(risk_df.sort_values('injury_risk_score', ascending=False),
                         x='name', y='injury_risk_score',
                         color='risk_category',
                         color_discrete_map={'Low': 'green', 'Medium': 'orange', 'High': 'red'},
                         title='Player Availability Risk Scores')
        st.plotly_chart(fig_risk, use_container_width=True)
        
        # Risk factors breakdown
        st.subheader("Risk Factors by Player")
        
        risk_factors = risk_df[['name', 'soreness', 'sleep_hours', 'acwr']].set_index('name')
        st.dataframe(risk_factors.style.background_gradient(cmap='RdYlGn_r', subset=['soreness']),
                    use_container_width=True)
        
    except:
        st.info("Run ML models to generate availability risk outputs")
    
    # Historical injuries
    st.subheader("Injury History")
    
    injuries = pd.read_sql_query("""
        SELECT 
            p.name,
            i.injury_type,
            i.body_part,
            i.injury_date,
            i.days_missed,
            i.return_date
        FROM injuries i
        JOIN players p ON i.player_id = p.player_id
        ORDER BY i.injury_date DESC
    """, conn, parse_dates=['injury_date', 'return_date'])
    
    if len(injuries) > 0:
        st.dataframe(injuries, use_container_width=True)
        
        # Injury breakdown
        col1, col2 = st.columns(2)
        
        with col1:
            injury_by_type = injuries.groupby('injury_type').size().reset_index(name='count')
            fig_type = px.pie(injury_by_type, values='count', names='injury_type',
                             title='Injuries by Type')
            st.plotly_chart(fig_type, use_container_width=True)
        
        with col2:
            injury_by_part = injuries.groupby('body_part').size().reset_index(name='count')
            fig_part = px.bar(injury_by_part, x='body_part', y='count',
                             title='Injuries by Body Part')
            st.plotly_chart(fig_part, use_container_width=True)
    else:
        st.info("No injuries recorded in database")

with tab4:
    st.header("Team Trends & Analytics")
    
    # Get all team data over time
    trend_query = """
        SELECT 
            w.date,
            AVG(w.sleep_hours) as avg_sleep,
            AVG(w.soreness) as avg_soreness,
            AVG(w.stress) as avg_stress,
            AVG(a.acwr) as avg_acwr,
            SUM(t.game_minutes) as total_game_minutes
        FROM wellness w
        JOIN training_load t ON w.player_id = t.player_id AND w.date = t.date
        LEFT JOIN acwr a ON w.player_id = a.player_id AND w.date = a.date
        GROUP BY w.date
        ORDER BY w.date
    """
    
    trend_data = pd.read_sql_query(trend_query, conn, parse_dates=['date'])
    
    # Wellness trends
    st.subheader("Team Wellness Trends")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig_sleep_trend = px.line(trend_data, x='date', y='avg_sleep',
                                 title='Average Team Sleep',
                                 markers=True)
        fig_sleep_trend.add_hline(y=7.5, line_dash="dash", line_color="green")
        st.plotly_chart(fig_sleep_trend, use_container_width=True)
    
    with col2:
        fig_soreness_trend = px.line(trend_data, x='date', y='avg_soreness',
                                    title='Average Team Soreness',
                                    markers=True)
        st.plotly_chart(fig_soreness_trend, use_container_width=True)
    
    # Load trends
    st.subheader("Team Load Trends")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig_acwr_trend = px.line(trend_data, x='date', y='avg_acwr',
                                title='Average Team ACWR',
                                markers=True)
        fig_acwr_trend.add_hline(y=1.3, line_dash="dash", line_color="orange")
        fig_acwr_trend.add_hline(y=1.5, line_dash="dash", line_color="red")
        st.plotly_chart(fig_acwr_trend, use_container_width=True)
    
    with col2:
        fig_minutes_trend = px.line(trend_data, x='date', y='total_game_minutes',
                                   title='Total Team Game Minutes',
                                   markers=True)
        st.plotly_chart(fig_minutes_trend, use_container_width=True)
    
    # Position comparison
    st.subheader("Position Comparison")
    
    position_query = """
        SELECT 
            p.position,
            AVG(w.sleep_hours) as avg_sleep,
            AVG(w.soreness) as avg_soreness,
            AVG(t.game_minutes) as avg_game_minutes,
            AVG(a.acwr) as avg_acwr
        FROM players p
        JOIN wellness w ON p.player_id = w.player_id
        JOIN training_load t ON p.player_id = t.player_id AND w.date = t.date
        LEFT JOIN acwr a ON p.player_id = a.player_id AND w.date = a.date
        GROUP BY p.position
    """
    
    position_data = pd.read_sql_query(position_query, conn)
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig_pos_minutes = px.bar(position_data, x='position', y='avg_game_minutes',
                                title='Average Game Minutes by Position')
        st.plotly_chart(fig_pos_minutes, use_container_width=True)
    
    with col2:
        fig_pos_soreness = px.bar(position_data, x='position', y='avg_soreness',
                                 title='Average Soreness by Position')
        st.plotly_chart(fig_pos_soreness, use_container_width=True)

# Footer
st.markdown("---")
st.markdown(
    "*AvailOps — Availability Operations System | Built by Chris Cothern | "
    "Data simulated for demonstration purposes*"
)
