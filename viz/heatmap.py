# viz/heatmap.py — Folium map builder (Phase 1: sensor dots)

import folium
import pandas as pd
from config import MAP_CENTER, MAP_ZOOM, AQI_COLORS
from data.purpleair import classify_pm25


def build_sensor_map(df: pd.DataFrame) -> folium.Map:
    """
    Build a Folium map with a colored circle marker for each sensor.

    Each marker is color-coded by AQI category and shows the sensor
    name and PM2.5 reading in a popup.

    Args:
        df: DataFrame with columns [sensor_id, name, lat, lon, pm25]

    Returns:
        A folium.Map object ready to render in Streamlit.
    """
    m = folium.Map(
        location=MAP_CENTER,
        zoom_start=MAP_ZOOM,
        tiles="CartoDB positron",  # clean, light basemap
    )

    for _, row in df.iterrows():
        category = classify_pm25(row["pm25"])
        color = AQI_COLORS.get(category, "gray")

        popup_text = (
            f"<b>{row['name']}</b><br>"
            f"PM2.5: {row['pm25']:.1f} µg/m³<br>"
            f"Category: {category.replace('_', ' ').title()}"
        )

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=folium.Popup(popup_text, max_width=200),
            tooltip=f"{row['name']}: {row['pm25']:.1f} µg/m³",
        ).add_to(m)

    # Add a simple legend in the bottom-right corner
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; right: 30px; z-index: 1000;
        background: white; padding: 10px 14px; border-radius: 8px;
        border: 1px solid #ccc; font-size: 13px; line-height: 1.8;
    ">
        <b>PM2.5 AQI</b><br>
        <span style="color:green;">&#9679;</span> Good (&le;12)<br>
        <span style="color:#cccc00;">&#9679;</span> Moderate (12–35)<br>
        <span style="color:orange;">&#9679;</span> Sensitive (35–55)<br>
        <span style="color:red;">&#9679;</span> Unhealthy (55–150)<br>
        <span style="color:purple;">&#9679;</span> Very Unhealthy (150–250)<br>
        <span style="color:darkred;">&#9679;</span> Hazardous (&gt;250)
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m
