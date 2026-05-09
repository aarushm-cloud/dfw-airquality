# engine/snapshot.py — Pipeline snapshot dataclass.
#
# Lifted out of api/routes/grid.py so engine modules (router, etc.) can
# accept it without importing from the api/ package. The dependency
# direction is api → engine, never the reverse.

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PipelineSnapshot:
    """One run of the ingest → IDW → adjust pipeline.

    `lats_2d` / `lons_2d` come from `np.meshgrid` over `config.BBOX`, so
    each row of `lats_2d` is constant lat and each column of `lons_2d` is
    constant lon. Collapse to 1D with `lats_2d[:, 0]` / `lons_2d[0, :]`
    for nearest-neighbor lookups.
    """

    timestamp: str
    sensor_df: pd.DataFrame
    lats_2d: np.ndarray
    lons_2d: np.ndarray
    grid: np.ndarray            # adjusted PM2.5 grid, shape matches lats_2d/lons_2d
    confidence: np.ndarray      # 0–1 per cell
    wind_speed: float
    wind_deg: float
