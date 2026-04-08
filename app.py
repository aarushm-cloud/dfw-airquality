# app.py — Streamlit entry point (Phase 1)

import streamlit as st
from streamlit_folium import st_folium
from data.purpleair import fetch_sensors
from viz.heatmap import build_sensor_map

# --- Page config ---
st.set_page_config(
    page_title="DFW Air Quality",
    page_icon="💨",
    layout="wide",
)

st.title("💨 DFW Real-Time Air Quality")
st.caption("Live PM2.5 readings from PurpleAir sensors across the Dallas metro area.")

# --- Sidebar ---
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
    st.markdown("---")
    st.markdown(
        "**Data source:** [PurpleAir](https://www2.purpleair.com/)  \n"
        "PM2.5 readings are 10-minute averages.  \n"
        "Outdoor sensors only."
    )

# --- Fetch sensor data (cached for 5 minutes) ---
@st.cache_data(ttl=300, show_spinner="Fetching sensor data...")
def load_data():
    return fetch_sensors()

try:
    df = load_data()
except ValueError as e:
    st.error(str(e))
    st.info("Add your PurpleAir API key to the `.env` file and restart the app.")
    st.stop()
except Exception as e:
    st.error(f"Failed to fetch sensor data: {e}")
    st.stop()

# --- Stats row ---
col1, col2, col3 = st.columns(3)
col1.metric("Active Sensors", len(df))
if not df.empty:
    col2.metric("Avg PM2.5 (µg/m³)", f"{df['pm25'].mean():.1f}")
    col3.metric("Max PM2.5 (µg/m³)", f"{df['pm25'].max():.1f}")

# --- Map ---
if df.empty:
    st.warning("No sensor data found for the Dallas bounding box. Check your API key and try again.")
else:
    folium_map = build_sensor_map(df)
    st_folium(folium_map, width="100%", height=600, returned_objects=[])
