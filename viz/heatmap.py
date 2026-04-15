# viz/heatmap.py — Folium map builder (Phase 1: sensor dots, Phase 2: IDW heatmap, Phase 3: adjusted PM2.5)

from functools import lru_cache

import numpy as np
import folium
import pandas as pd
import pgeocode
from uszipcode import SearchEngine
from config import MAP_CENTER, MAP_ZOOM, AQI_COLORS
from data.purpleair import classify_pm25

# pgeocode Nominatim instance for forward zip-code lookup (zip → lat/lon).
# Used by zip_to_coords() for any future sidebar search feature.
_nomi = pgeocode.Nominatim("us")

# uszipcode search engine — loads a local SQLite DB of US zip codes.
# simple_zipcode=True uses the lightweight "simple" DB (9 MB, faster).
_search = SearchEngine(simple_zipcode=True)


@lru_cache(maxsize=2048)
def _coords_to_zip(lat: float, lon: float) -> str | None:
    """
    Reverse-geocode a lat/lon to the nearest US zip code using uszipcode.
    Coordinates are rounded to 2 decimal places before lookup (≈1.1 km
    precision), which is well within zip code resolution and improves the
    cache hit rate significantly across the 60×60 grid.

    Returns the zip code string (e.g. "75201") or None if no result within
    a 5-mile radius.
    """
    lat_r = round(lat, 2)
    lon_r = round(lon, 2)
    result = _search.by_coordinates(lat_r, lon_r, radius=5, returns=1)
    if result:
        return result[0].zipcode
    return None


# PM2.5 color scale: green → yellow → orange → red → purple → dark red
# Each tuple is (pm25_threshold, hex_color). Folium interpolates between them.
PM25_COLORSCALE = [
    (0,     "#00e400"),  # green      — Good
    (12,    "#ffff00"),  # yellow     — Moderate
    (35.4,  "#ff7e00"),  # orange     — Sensitive
    (55.4,  "#ff0000"),  # red        — Unhealthy
    (150.4, "#8f3f97"),  # purple     — Very Unhealthy
    (250.4, "#7e0023"),  # dark red   — Hazardous
]


def _pm25_to_hex(pm25: float) -> str:
    """
    Map a PM2.5 value to a hex color by linearly interpolating
    between the stops in PM25_COLORSCALE.
    """
    # Clamp to the scale's range
    pm25 = max(PM25_COLORSCALE[0][0], min(pm25, PM25_COLORSCALE[-1][0]))

    # Find which two stops the value falls between
    for i in range(len(PM25_COLORSCALE) - 1):
        lo_val, lo_hex = PM25_COLORSCALE[i]
        hi_val, hi_hex = PM25_COLORSCALE[i + 1]

        if lo_val <= pm25 <= hi_val:
            # How far between the two stops (0.0 → 1.0)
            t = (pm25 - lo_val) / (hi_val - lo_val)

            # Parse hex colors into R, G, B integers
            lo_rgb = [int(lo_hex[j:j+2], 16) for j in (1, 3, 5)]
            hi_rgb = [int(hi_hex[j:j+2], 16) for j in (1, 3, 5)]

            # Linearly interpolate each channel
            r = int(lo_rgb[0] + t * (hi_rgb[0] - lo_rgb[0]))
            g = int(lo_rgb[1] + t * (hi_rgb[1] - lo_rgb[1]))
            b = int(lo_rgb[2] + t * (hi_rgb[2] - lo_rgb[2]))

            return f"#{r:02x}{g:02x}{b:02x}"

    return PM25_COLORSCALE[-1][1]  # fallback: hazardous color


def zip_to_coords(zip_code: str) -> tuple[float, float] | None:
    """
    Forward-geocode a US zip code to (latitude, longitude) using pgeocode's
    public query_postal_code() method.

    Returns (lat, lon) on success, or None if the zip is not found.
    Intended for any future "search by zip code" sidebar feature.
    """
    result = _nomi.query_postal_code(zip_code)
    if pd.isna(result.latitude):
        return None
    return (result.latitude, result.longitude)


def _add_idw_overlay(
    m: folium.Map,
    lats: np.ndarray,
    lons: np.ndarray,
    values: np.ndarray,
) -> None:
    """
    Draw each cell of a pre-computed PM2.5 grid as a coloured rectangle on the map.
    The caller is responsible for running IDW and apply_grid before calling this.

    We use Rectangle markers rather than a raster image so this works
    in any browser without extra plugins.
    """

    # Cell half-width in degrees (how big each rectangle is)
    cell_lat = (lats[1, 0] - lats[0, 0]) / 2
    cell_lon = (lons[0, 1] - lons[0, 0]) / 2

    # Create one FeatureGroup so all heatmap tiles are toggled together
    heatmap_group = folium.FeatureGroup(name="PM2.5 Heatmap", show=True)

    rows, cols = lats.shape
    for i in range(rows):
        for j in range(cols):
            pm25_val = values[i, j]
            color    = _pm25_to_hex(pm25_val)
            lat      = lats[i, j]
            lon      = lons[i, j]

            category = classify_pm25(pm25_val)
            zip_code = _coords_to_zip(lat, lon)
            location_label = f"Zip: {zip_code}" if zip_code else f"{lat:.3f}, {lon:.3f}"
            popup_text = (
                f"<b>{location_label}</b><br>"
                f"PM2.5: {pm25_val:.1f} µg/m³<br>"
                f"Category: {category.replace('_', ' ').title()}"
            )

            folium.Rectangle(
                bounds=[
                    [lat - cell_lat, lon - cell_lon],  # south-west corner
                    [lat + cell_lat, lon + cell_lon],  # north-east corner
                ],
                color=None,         # no border stroke
                fill=True,
                fill_color=color,
                fill_opacity=0.35,  # semi-transparent so basemap shows through
                popup=folium.Popup(popup_text, max_width=180),
                tooltip=f"{pm25_val:.1f} µg/m³",
            ).add_to(heatmap_group)

    heatmap_group.add_to(m)


def build_sensor_map(
    df: pd.DataFrame,
    lats: np.ndarray,
    lons: np.ndarray,
    grid_values: np.ndarray,
) -> folium.Map:
    """
    Build a Folium map with:
      - IDW heatmap overlay (Phase 2), using the pre-computed adjusted grid
      - Colored circle marker for each sensor (Phase 1)
      - AQI legend

    The caller (app.py) is responsible for running run_idw() and adjust_grid()
    before calling this function and passing in the resulting arrays.
    """
    m = folium.Map(
        location=MAP_CENTER,
        zoom_start=MAP_ZOOM,
        tiles="CartoDB positron",
    )

    # --- Phase 2: heatmap overlay (drawn first so dots render on top) ---
    _add_idw_overlay(m, lats, lons, grid_values)

    # --- Phase 1: sensor dot markers ---
    sensor_group = folium.FeatureGroup(name="Sensor Readings", show=True)

    for _, row in df.iterrows():
        category = classify_pm25(row["pm25"])
        color    = AQI_COLORS.get(category, "gray")

        # Show both adjusted (traffic+wind) and raw sensor reading in the popup
        raw = row.get("pm25_raw", row["pm25"])

        if row["pm25"] == 0.0:
            zero_note = "<br><i style='color:#888;font-size:11px;'>⚠ Sensor reported 0 — may be offline or malfunctioning.</i>"
        else:
            zero_note = ""

        popup_text = (
            f"<b>{row['name']}</b><br>"
            f"PM2.5: {row['pm25']:.1f} µg/m³<br>"
            f"Category: {category.replace('_', ' ').title()}"
            f"{zero_note}"
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
        ).add_to(sensor_group)

    sensor_group.add_to(m)

    # Layer control (lets user toggle heatmap and dots on/off)
    folium.LayerControl(position="topright").add_to(m)

    # --- Legend ---
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; right: 30px; z-index: 1000;
        background: white; padding: 10px 14px; border-radius: 8px;
        border: 1px solid #ccc; font-size: 13px; line-height: 1.8;
    ">
        <b>PM2.5 AQI</b><br>
        <span style="color:#00e400;">&#9679;</span> Good (&le;12)<br>
        <span style="color:#cccc00;">&#9679;</span> Moderate (12–35)<br>
        <span style="color:#ff7e00;">&#9679;</span> Sensitive (35–55)<br>
        <span style="color:red;">&#9679;</span> Unhealthy (55–150)<br>
        <span style="color:#8f3f97;">&#9679;</span> Very Unhealthy (150–250)<br>
        <span style="color:#7e0023;">&#9679;</span> Hazardous (&gt;250)
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m
