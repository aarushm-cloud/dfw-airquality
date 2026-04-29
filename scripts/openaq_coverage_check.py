"""
openaq_coverage_check.py

Feasibility check: would OpenAQ reference-grade stations fill the
spatial-coverage gaps left in our PurpleAir training set? Pulls the
list of PM2.5 stations within the project BBOX, filters to active
stations with >=180 days of history, recomputes the 4x4 grid coverage
with PurpleAir + OpenAQ combined, and writes a comparison map.

Density check uses location-level datetimeFirst/datetimeLast, not the
per-sensor hours endpoint — OpenAQ v3's meta.found returns ">N" sentinel
strings for hours queries, not exact integers, so it's not usable as a
density proxy.

Reuses the OpenAQ v3 client helpers in data/openaq.py.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import BBOX  # noqa: E402
from data.openaq import (  # noqa: E402
    _fetch_locations,
    _get_api_key,
    _get_pm25_sensor_id,
)

HISTORY_CSV    = PROJECT_ROOT / "data" / "history.csv"
OUTPUT_DIR     = PROJECT_ROOT / "scripts" / "output"
PLOT_PATH      = OUTPUT_DIR / "openaq_coverage.png"

LANDMARKS = {
    "DFW Airport":       (32.8998, -97.0403),
    "Downtown Dallas":   (32.7767, -96.7970),
    "Downtown Ft Worth": (32.7555, -97.3308),
    "Plano":             (33.0198, -96.6989),
    "Arlington":         (32.7357, -97.1081),
}

GRID_N             = 4
TRAINING_DAYS      = 180   # how far back our training window goes
ACTIVE_WITHIN_DAYS = 7     # datetimeLast must be this fresh
HINTON_LAT_LON     = (32.82, -96.86)
HINTON_NEAR_KM     = 5.0   # "near Hinton" = within this radius


# ---------------------------------------------------------------------------
# OpenAQ datetime helpers
# ---------------------------------------------------------------------------

def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def extract_location_datetimes(loc: dict) -> tuple[datetime | None, datetime | None]:
    """
    OpenAQ v3 puts authoritative datetimeFirst/datetimeLast at the location
    level. Per-sensor entries in the location response often have these as
    None. Read location-level only.
    """
    def _read(field: str) -> datetime | None:
        v = loc.get(field)
        if isinstance(v, dict):
            return parse_iso(v.get("utc"))
        if isinstance(v, str):
            return parse_iso(v)
        return None

    return _read("datetimeFirst"), _read("datetimeLast")


# ---------------------------------------------------------------------------
# Coverage math (mirrors scripts/sensor_coverage_check.py)
# ---------------------------------------------------------------------------

def cell_for_point(lat: float, lon: float) -> tuple[int, int] | None:
    """Return (row, col) in the GRID_N x GRID_N grid; row 0 = north."""
    if not (BBOX["south"] <= lat <= BBOX["north"]):
        return None
    if not (BBOX["west"]  <= lon <= BBOX["east"]):
        return None
    lat_step = (BBOX["north"] - BBOX["south"]) / GRID_N
    lon_step = (BBOX["east"]  - BBOX["west"])  / GRID_N
    # Distance from north edge → row index 0..GRID_N-1
    row = min(int((BBOX["north"] - lat) / lat_step), GRID_N - 1)
    col = min(int((lon - BBOX["west"])  / lon_step), GRID_N - 1)
    return row, col


def grid_cell_counts(sensors: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    counts = pd.DataFrame(0, index=range(GRID_N), columns=range(GRID_N))
    for _, r in sensors.iterrows():
        cell = cell_for_point(r["lat"], r["lon"])
        if cell is not None:
            counts.iloc[cell[0], cell[1]] += 1
    empty = [(r, c) for r in range(GRID_N) for c in range(GRID_N) if counts.iloc[r, c] == 0]
    return counts, empty


def cell_to_bbox(row: int, col: int) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) for a grid cell. Row 0 = north."""
    lat_step = (BBOX["north"] - BBOX["south"]) / GRID_N
    lon_step = (BBOX["east"]  - BBOX["west"])  / GRID_N
    north = BBOX["north"] - row * lat_step
    south = north - lat_step
    west  = BBOX["west"]  + col * lon_step
    east  = west + lon_step
    return south, west, north, east


def cell_center(row: int, col: int) -> tuple[float, float]:
    s, w, n, e = cell_to_bbox(row, col)
    return (s + n) / 2, (w + e) / 2


def haversine_km(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    from math import radians, sin, cos, asin, sqrt
    lat1, lon1 = map(radians, p1)
    lat2, lon2 = map(radians, p2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * 6371.0 * asin(sqrt(a))


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_combined_coverage(
    pa_sensors: pd.DataFrame,
    oaq_sensors: pd.DataFrame,
    empty_cells_pa_only: list[tuple[int, int]],
    closed_cells: set[tuple[int, int]],
    fillers_per_cell: dict[tuple[int, int], list[str]],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 9))

    bbox_rect = Rectangle(
        (BBOX["west"], BBOX["south"]),
        BBOX["east"] - BBOX["west"],
        BBOX["north"] - BBOX["south"],
        linewidth=1.5, edgecolor="#444", facecolor="#f7f7f7", zorder=1,
    )
    ax.add_patch(bbox_rect)

    # Shade PurpleAir-empty cells; tint closed ones differently so the
    # visual story is "red was the gap, green-tinted means filled".
    for (r, c) in empty_cells_pa_only:
        s, w, n, e = cell_to_bbox(r, c)
        if (r, c) in closed_cells:
            face, edge = "#d9f0d9", "#7aab7a"  # filled: light green
        else:
            face, edge = "#ffd8d8", "#e88"      # still empty: light red
        ax.add_patch(Rectangle((w, s), e - w, n - s,
                               facecolor=face, edgecolor=edge,
                               linewidth=0.7, zorder=2))

    for i in range(1, GRID_N):
        lat = BBOX["south"] + i * (BBOX["north"] - BBOX["south"]) / GRID_N
        lon = BBOX["west"]  + i * (BBOX["east"]  - BBOX["west"])  / GRID_N
        ax.axhline(lat, color="#bbb", linewidth=0.6, zorder=3)
        ax.axvline(lon, color="#bbb", linewidth=0.6, zorder=3)

    ax.scatter(
        pa_sensors["lon"], pa_sensors["lat"],
        s=60, color="#1f77b4", edgecolor="white", linewidth=1,
        zorder=5, label=f"PurpleAir surviving (n={len(pa_sensors)})",
    )

    if not oaq_sensors.empty:
        ax.scatter(
            oaq_sensors["lon"], oaq_sensors["lat"],
            s=160, marker="^", color="#2ca02c", edgecolor="#0e3a0e",
            linewidth=1, zorder=6,
            label=f"OpenAQ active (n={len(oaq_sensors)})",
        )
        for _, r in oaq_sensors.iterrows():
            ax.annotate(
                r["name"],
                (r["lon"], r["lat"]),
                xytext=(8, 5), textcoords="offset points",
                fontsize=7.5, fontweight="bold", color="#0e3a0e", zorder=7,
            )

    # Annotate each closed cell with which OpenAQ stations fill it
    for cell, names in fillers_per_cell.items():
        clat, clon = cell_center(*cell)
        ax.annotate(
            f"fills cell {cell}\n{', '.join(names)}",
            (clon, clat),
            ha="center", va="center",
            fontsize=8, fontweight="bold", color="#155c15",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#ffffff",
                      edgecolor="#7aab7a", linewidth=0.8, alpha=0.9),
            zorder=9,
        )

    for name, (lat, lon) in LANDMARKS.items():
        ax.scatter(lon, lat, s=110, marker="*", color="#ffae00",
                   edgecolor="#5a3e00", linewidth=0.8, zorder=8)
        ax.annotate(
            name, (lon, lat),
            xytext=(7, 7), textcoords="offset points",
            fontsize=9, fontweight="bold", color="#5a3e00", zorder=9,
        )

    ax.set_xlim(BBOX["west"]  - 0.04, BBOX["east"]  + 0.04)
    ax.set_ylim(BBOX["south"] - 0.04, BBOX["north"] + 0.04)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(
        "DFW Coverage — PurpleAir survivors + active OpenAQ stations\n"
        f"Red = PurpleAir gap, Green-tinted = gap closed by OpenAQ ({GRID_N}x{GRID_N})",
        fontsize=12,
    )
    ax.legend(loc="lower left", fontsize=9, framealpha=0.95)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(False)
    plt.tight_layout()
    plt.savefig(PLOT_PATH, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print(" OPENAQ COVERAGE FEASIBILITY CHECK")
    print("=" * 72)

    # --- PurpleAir baseline from history.csv ---
    if not HISTORY_CSV.exists():
        raise SystemExit(f"{HISTORY_CSV} not found — run collect_training_data.py first")
    history = pd.read_csv(HISTORY_CSV)
    pa = (history[["sensor_id", "lat", "lon"]]
          .drop_duplicates(subset=["sensor_id"])
          .reset_index(drop=True))
    pa_counts, pa_empty = grid_cell_counts(pa)
    print(f"\nPurpleAir baseline: {len(pa)} sensors, "
          f"{len(pa_empty)} of {GRID_N*GRID_N} grid cells empty")
    print(f"  Empty cells (row=north→south, col=west→east): {pa_empty}")

    # --- OpenAQ locations in BBOX ---
    api_key = _get_api_key()
    print("\nQuerying OpenAQ v3 for PM2.5 locations within BBOX...")
    locations = _fetch_locations(api_key)
    print(f"  Returned {len(locations)} locations")

    # --- Activity / history filter ---
    now = datetime.now(timezone.utc)
    cutoff_active = now - timedelta(days=ACTIVE_WITHIN_DAYS)
    cutoff_history = now - timedelta(days=TRAINING_DAYS)
    print(f"\nFiltering: datetimeLast within {ACTIVE_WITHIN_DAYS}d "
          f"AND datetimeFirst on or before {cutoff_history.date()} "
          f"({TRAINING_DAYS}d ago).")

    qualifying = []
    near_hinton_post_decommission = []
    for loc in locations:
        loc_id = loc.get("id")
        name   = loc.get("name") or f"openaq-{loc_id}"
        coords = loc.get("coordinates") or {}
        lat    = coords.get("latitude")
        lon    = coords.get("longitude")
        if lat is None or lon is None:
            continue

        pm25_sensor_id = _get_pm25_sensor_id(loc)
        if pm25_sensor_id is None:
            print(f"  SKIP  {name:<48s} ({loc_id})  no PM2.5 sensor")
            continue

        first, last = extract_location_datetimes(loc)
        first_str = first.isoformat() if first else "unknown"
        last_str  = last.isoformat()  if last  else "unknown"

        if last is None or last < cutoff_active:
            print(f"  SKIP  {name:<48s} ({loc_id})  inactive (last={last_str})")
            continue
        if first is None or first > cutoff_history:
            days_back = (now - first).days if first else 0
            print(f"  SKIP  {name:<48s} ({loc_id})  history too short "
                  f"(first={first_str}, only {days_back}d back)")
            continue

        # Hinton replacement check: stations whose datetimeFirst is on/after
        # 2025-02-24 and that sit within HINTON_NEAR_KM of Hinton's coords.
        possible_hinton = (
            first >= datetime(2025, 2, 24, tzinfo=timezone.utc)
            and haversine_km((lat, lon), HINTON_LAT_LON) <= HINTON_NEAR_KM
        )

        days_history = (now - first).days
        qualifying.append({
            "station_id":      f"oaq-{loc_id}",
            "openaq_loc_id":   loc_id,
            "pm25_sensor_id":  pm25_sensor_id,
            "name":            name,
            "lat":             lat,
            "lon":             lon,
            "datetimeFirst":   first_str,
            "datetimeLast":    last_str,
            "days_history":    days_history,
            "possible_hinton": possible_hinton,
        })
        flag = "  (possible Hinton replacement)" if possible_hinton else ""
        print(f"  KEEP  {name:<48s} ({loc_id})  "
              f"first={first_str[:10]}  last={last_str[:10]}  "
              f"hist={days_history}d{flag}")
        if possible_hinton:
            near_hinton_post_decommission.append(name)

    oaq = pd.DataFrame(qualifying)

    print("\n" + "-" * 72)
    print(f" QUALIFYING OPENAQ STATIONS ({len(oaq)})")
    print("-" * 72)
    if oaq.empty:
        print("None.")
    else:
        # Sorted by datetimeFirst ascending — earliest history first.
        # If any station only has ~180d of history, that's no margin and
        # we want it visible at the top of the list.
        oaq_view = (oaq
                    .sort_values("datetimeFirst")
                    .reset_index(drop=True)
                    [["station_id", "name", "lat", "lon",
                      "datetimeFirst", "datetimeLast", "days_history"]])
        print(oaq_view.to_string(index=False))

        margin = oaq["days_history"] - TRAINING_DAYS
        print(f"\nHistory margin vs. {TRAINING_DAYS}d training window:")
        print(f"  Min margin: {margin.min()}d   Median: {int(margin.median())}d   Max: {margin.max()}d")
        thin = oaq[margin < 30]
        if not thin.empty:
            print(f"  WARNING: {len(thin)} station(s) have <30d margin beyond the training window:")
            for _, r in thin.iterrows():
                print(f"    {r['name']} — only {r['days_history']}d of history")

    # --- Combined grid coverage ---
    print("\n" + "-" * 72)
    print(f" {GRID_N}x{GRID_N} GRID COVERAGE (PurpleAir + OpenAQ combined)")
    print("-" * 72)

    if oaq.empty:
        combined = pa.copy()
    else:
        combined = pd.concat([
            pa.assign(source="purpleair"),
            oaq[["station_id", "lat", "lon"]].rename(
                columns={"station_id": "sensor_id"}
            ).assign(source="openaq"),
        ], ignore_index=True)

    combined_counts, combined_empty = grid_cell_counts(combined)
    pa_empty_set = set(pa_empty)
    combined_empty_set = set(combined_empty)
    closed = pa_empty_set - combined_empty_set
    still_empty = pa_empty_set & combined_empty_set

    # Per-cell list of OpenAQ stations responsible for closing each gap
    fillers_per_cell: dict[tuple[int, int], list[str]] = {}
    if not oaq.empty:
        for _, r in oaq.iterrows():
            cell = cell_for_point(r["lat"], r["lon"])
            if cell is not None and cell in closed:
                fillers_per_cell.setdefault(cell, []).append(r["name"])

    print("PurpleAir-only counts:")
    print(pa_counts.to_string(index=False, header=False))
    print("\nCombined counts:")
    print(combined_counts.to_string(index=False, header=False))

    print(f"\nPurpleAir empty cells:    {len(pa_empty)}  {sorted(pa_empty)}")
    print(f"Combined empty cells:     {len(combined_empty)}  {sorted(combined_empty)}")
    print(f"Cells OpenAQ closes:      {len(closed)}  {sorted(closed)}")
    if fillers_per_cell:
        for cell, names in sorted(fillers_per_cell.items()):
            print(f"    cell {cell}: {', '.join(names)}")
    print(f"Cells still empty:        {len(still_empty)}  {sorted(still_empty)}")

    # --- Plot ---
    plot_combined_coverage(pa, oaq, pa_empty, closed, fillers_per_cell)
    print(f"\nMap saved to {PLOT_PATH.relative_to(PROJECT_ROOT)}")

    # --- Hinton check ---
    print("\n" + "-" * 72)
    print(" HINTON ST. C4 REPLACEMENT CHECK")
    print("-" * 72)
    if near_hinton_post_decommission:
        print(f"Possible Hinton replacement(s) (started ≥2025-02-24, within "
              f"{HINTON_NEAR_KM} km of {HINTON_LAT_LON}):")
        for n in near_hinton_post_decommission:
            print(f"  - {n}")
    else:
        print(f"No active station was registered ≥2025-02-24 within "
              f"{HINTON_NEAR_KM} km of Hinton's coords. Hinton appears to be "
              "retired with no direct OpenAQ replacement in our BBOX.")

    # --- Verdict ---
    print("\n" + "=" * 72)
    print(" VERDICT")
    print("=" * 72)
    n_closed = len(closed)
    n_pa_empty = len(pa_empty)

    if n_pa_empty == 0:
        verdict = ("PurpleAir already covers all cells — OpenAQ is not needed "
                   "for spatial reasons.")
    elif n_closed == 0:
        verdict = (f"OpenAQ closes 0 of {n_pa_empty} gaps. OpenAQ stations sit "
                   f"in regions PurpleAir already covers. Recommendation: "
                   f"tighten BBOX or accept gaps and tag low-confidence regions "
                   f"at inference time.")
    elif n_closed >= n_pa_empty * 0.5:
        verdict = (f"OpenAQ closes {n_closed} of {n_pa_empty} gaps — meaningful "
                   f"improvement. Remaining empty cells: {sorted(still_empty)}. "
                   f"Recommendation: integrate OpenAQ into the training "
                   f"collection as a separate work item, then re-evaluate.")
    else:
        verdict = (f"OpenAQ closes {n_closed} of {n_pa_empty} gaps — partial "
                   f"improvement. Remaining empty cells: {sorted(still_empty)}. "
                   f"Recommendation: integrate OpenAQ AND tag remaining holes "
                   f"as low-confidence regions at inference time.")

    print(f"\n{verdict}\n")


if __name__ == "__main__":
    main()
