# data/corrections.py — Shared PM2.5 correction formulas.
#
# The single source of truth for the EPA / Barkjohn 2021 PurpleAir correction.
# Imported by both the live ingestion path (data/ingestion/purpleair.py) and
# the historical training pipeline (ml/training/collect_training_data.py) so
# the two pipelines are guaranteed to apply byte-identical math.
#
# The function is intentionally side-effect-free (no logging, no global state).
# Callers that need progress logging (the training script) should wrap this
# with their own reporting layer.

import pandas as pd


def apply_epa_correction(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the EPA's PM2.5 correction formula for PurpleAir sensors:

        PM2.5_corrected = 0.52 * PM2.5_raw - 0.085 * RH + 5.71

    PurpleAir's laser particle counter systematically overestimates PM2.5,
    especially when humidity is high (water droplets scatter the laser and
    get counted as particles). The Barkjohn et al. 2021 regression formula,
    derived from years of co-location with federal reference-grade monitors,
    is the standard correction in U.S. regulatory and public-health contexts
    (EPA AirNow Fire and Smoke Map technical documentation).

    Input MUST be the CF=1 channel (`pm2.5_cf_1`). Barkjohn 2021 was derived
    from CF=1 co-location data; feeding it ATM-channel input overcorrects at
    moderate concentrations and diverges significantly at PM2.5 > 50 µg/m³.

    Behaviour:
      - `pm25_raw` is the input to the formula. If absent, it is initialised
        to a copy of `pm25` (live ingest path: pm25 carries the raw reading
        when the function is called). If present, it is preserved (training
        path: pm25_raw was set by A/B validation upstream as
        ``(pm25_a + pm25_b) / 2``).
      - Rows with humidity available are corrected via the formula.
      - Rows with missing humidity (NaN cell, or `humidity` column entirely
        absent) keep `pm25 = pm25_raw` so downstream consumers see one
        consistent column.
      - `epa_corrected` is 1 where the formula was applied, 0 otherwise.
      - The final `pm25` column is clipped to ``>= 0``. The formula can
        produce small negatives at very low concentrations; this also
        defensively guards any non-RH rows that happen to carry a negative
        raw reading.

    Args:
        df: DataFrame with at minimum a `pm25` column. `humidity` and
            `pm25_raw` are honoured if present.

    Returns:
        Copy of the input with `pm25` (corrected), `pm25_raw` (preserved),
        and `epa_corrected` (0/1) columns guaranteed.
    """
    out = df.copy()

    # Preserve the audit trail. Only initialise pm25_raw if the upstream
    # caller hasn't already supplied it — A/B validation in the training
    # pipeline writes pm25_raw before this function runs and we must not
    # clobber that value.
    if "pm25_raw" not in out.columns:
        out["pm25_raw"] = out["pm25"]

    # Without a humidity column we can't apply the formula at all; pm25
    # falls back to pm25_raw uniformly.
    if "humidity" not in out.columns:
        out["pm25"] = out["pm25_raw"]
        out["epa_corrected"] = 0
        out["pm25"] = out["pm25"].clip(lower=0)
        return out

    has_rh = out["humidity"].notna()

    # Apply the formula where humidity is available; fall back to pm25_raw
    # everywhere else. Setting both branches explicitly means the function
    # is robust to whatever pm25 happened to be on entry.
    corrected_values = 0.52 * out["pm25_raw"] - 0.085 * out["humidity"] + 5.71
    out.loc[has_rh,  "pm25"] = corrected_values[has_rh]
    out.loc[~has_rh, "pm25"] = out.loc[~has_rh, "pm25_raw"]
    out["epa_corrected"]     = has_rh.astype(int)

    # Single clip across all rows: corrected values can go small-negative
    # at very low PM2.5; non-RH rows shouldn't be negative in practice but
    # this is a defensive belt that costs nothing.
    out["pm25"] = out["pm25"].clip(lower=0)

    return out
