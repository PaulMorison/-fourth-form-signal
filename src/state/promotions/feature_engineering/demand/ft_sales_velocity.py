from __future__ import annotations

"""Sales-velocity ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_sales_velocity(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add sales-velocity and baseline demand regime flags."""

    del reference_frame
    working = frame.copy()
    baseline_daily = ensure_numeric_series(working, "baseline_daily_units")
    working["feature_sales_velocity_units_per_day"] = baseline_daily
    working["feature_sales_velocity_ratio_short_to_long"] = safe_ratio(
        ensure_numeric_series(working, "pre_28d_avg_daily_units"),
        ensure_numeric_series(working, "pre_56d_avg_daily_units"),
    )
    working["feature_pre_promo_sales_per_selling_day"] = safe_ratio(
        ensure_numeric_series(working, "pre_56d_sales_ex_gst"),
        ensure_numeric_series(working, "pre_56d_days_with_sales"),
    )
    working["feature_slow_seller_flag"] = (baseline_daily < 1.0).astype(float)
    working["feature_medium_seller_flag"] = ((baseline_daily >= 1.0) & (baseline_daily < 5.0)).astype(float)
    working["feature_fast_seller_flag"] = (baseline_daily >= 5.0).astype(float)
    return working
