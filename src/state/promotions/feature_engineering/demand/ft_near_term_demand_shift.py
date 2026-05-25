from __future__ import annotations

"""Near-term-demand-shift ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_near_term_demand_shift(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add short-vs-long baseline shift and uplift burden features."""

    del reference_frame
    working = frame.copy()
    short_baseline = ensure_numeric_series(working, "pre_7d_avg_daily_units")
    medium_baseline = ensure_numeric_series(working, "pre_28d_avg_daily_units")
    long_baseline = ensure_numeric_series(working, "pre_56d_avg_daily_units")
    prior_baseline = ensure_numeric_series(working, "pre_prior_21d_avg_daily_units")
    working["feature_short_vs_long_baseline_acceleration"] = safe_ratio(short_baseline, long_baseline)
    working["feature_recent_acceleration_ratio"] = safe_ratio(short_baseline, prior_baseline)
    working["feature_required_vs_baseline_demand_gap"] = safe_ratio(
        ensure_numeric_series(working, "required_implied_daily") - medium_baseline.where(medium_baseline > 0.0, long_baseline),
        medium_baseline.where(medium_baseline > 0.0, long_baseline),
    )
    return working
