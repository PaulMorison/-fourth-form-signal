from __future__ import annotations

"""Intermittent-demand cadence features.

These features describe the SHAPE of pre-promo selling cadence so the model
can distinguish "sells 1 per day steadily" from "sells 1 every 4 days
intermittently". They are derived purely from the row's own pre-window
aggregates (`pre_*d_units`, `pre_*d_days_with_sales`, `pre_*d_avg_daily_units`,
`pre_*d_std_daily_units`) which are already strictly-prior to the promotion
start, so no future leakage is possible.

Emitted feature columns (model contract):
    feature_sales_interval_days_mean_56d
    feature_sales_interval_days_std_56d
    feature_sales_interval_days_cv_56d
    feature_days_since_last_sale
    feature_days_with_sales_28d
    feature_days_with_sales_56d
    feature_average_units_per_selling_day_28d
    feature_average_units_per_selling_day_56d
    feature_intermittent_demand_flag
    feature_sparse_repeat_purchase_flag
    feature_sales_day_density_28d
    feature_sales_day_density_56d
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


INTERMITTENT_DEMAND_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_sales_interval_days_mean_56d",
    "feature_sales_interval_days_std_56d",
    "feature_sales_interval_days_cv_56d",
    "feature_days_since_last_sale",
    "feature_days_with_sales_28d",
    "feature_days_with_sales_56d",
    "feature_average_units_per_selling_day_28d",
    "feature_average_units_per_selling_day_56d",
    "feature_intermittent_demand_flag",
    "feature_sparse_repeat_purchase_flag",
    "feature_sales_day_density_28d",
    "feature_sales_day_density_56d",
)

# Empirical cadence thresholds documented for governance:
# - intermittent_demand_flag: sells_interval > 4 days OR <= 25% of pre-56d days had a sale.
# - sparse_repeat_purchase_flag: <= 7 selling days in pre-56d AND average_units_per_selling_day <= 1.5.
_INTERMITTENT_INTERVAL_THRESHOLD_DAYS = 4.0
_INTERMITTENT_DENSITY_THRESHOLD = 0.25
_SPARSE_REPEAT_DAYS_THRESHOLD = 7.0
_SPARSE_REPEAT_UNITS_PER_DAY_THRESHOLD = 1.5


def apply_ft_intermittent_demand(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append intermittent-demand cadence features."""

    del reference_frame
    working = frame.copy()

    pre_56_units = ensure_numeric_series(working, "pre_56d_units")
    pre_28_units = ensure_numeric_series(working, "pre_28d_units")
    pre_56_dws = ensure_numeric_series(working, "pre_56d_days_with_sales")
    pre_28_dws = ensure_numeric_series(working, "pre_28d_days_with_sales")
    pre_56_std = ensure_numeric_series(working, "pre_56d_std_daily_units")
    pre_56_avg = ensure_numeric_series(working, "pre_56d_avg_daily_units")
    pre_7_dws = ensure_numeric_series(working, "pre_7d_days_with_sales")

    # Cadence mean: 56 / days_with_sales. When days_with_sales == 0 we treat
    # cadence as the full window (56) — meaning "no sales observed".
    interval_mean_56 = safe_ratio(
        pd.Series(56.0, index=working.index),
        pre_56_dws.where(pre_56_dws > 0, np.nan),
    )
    interval_mean_56 = interval_mean_56.where(pre_56_dws > 0, 56.0).fillna(56.0)

    # Interval-CV proxy: dispersion of daily units divided by mean of daily units;
    # treats high variance with low mean as more intermittent.
    interval_std_56 = pre_56_std.fillna(0.0)
    interval_cv_56 = safe_ratio(interval_std_56, pre_56_avg.where(pre_56_avg > 0, np.nan)).fillna(0.0)

    # Days-since-last-sale: if pre_7d had any selling day, conservatively call it
    # 7/days_with_sales rounded; else if pre_28d had any, use 28/dws; else use 56.
    days_since_last_sale = pd.Series(56.0, index=working.index, dtype="float64")
    has_28 = pre_28_dws > 0
    days_since_last_sale = days_since_last_sale.where(~has_28, np.minimum(28.0, np.ceil(28.0 / pre_28_dws.replace(0.0, np.nan)).fillna(28.0)))
    has_7 = pre_7_dws > 0
    days_since_last_sale = days_since_last_sale.where(~has_7, np.minimum(7.0, np.ceil(7.0 / pre_7_dws.replace(0.0, np.nan)).fillna(7.0)))

    avg_upd_28 = safe_ratio(pre_28_units, pre_28_dws.where(pre_28_dws > 0, np.nan)).fillna(0.0)
    avg_upd_56 = safe_ratio(pre_56_units, pre_56_dws.where(pre_56_dws > 0, np.nan)).fillna(0.0)

    density_28 = (pre_28_dws / 28.0).clip(lower=0.0, upper=1.0)
    density_56 = (pre_56_dws / 56.0).clip(lower=0.0, upper=1.0)

    intermittent_flag = (
        (interval_mean_56 > _INTERMITTENT_INTERVAL_THRESHOLD_DAYS)
        | (density_56 <= _INTERMITTENT_DENSITY_THRESHOLD)
    ).astype(float)
    sparse_repeat_flag = (
        (pre_56_dws <= _SPARSE_REPEAT_DAYS_THRESHOLD)
        & (avg_upd_56 <= _SPARSE_REPEAT_UNITS_PER_DAY_THRESHOLD)
    ).astype(float)

    working["feature_sales_interval_days_mean_56d"] = interval_mean_56.astype(float)
    working["feature_sales_interval_days_std_56d"] = interval_std_56.astype(float)
    working["feature_sales_interval_days_cv_56d"] = interval_cv_56.astype(float)
    working["feature_days_since_last_sale"] = days_since_last_sale.astype(float)
    working["feature_days_with_sales_28d"] = pre_28_dws.fillna(0.0).astype(float)
    working["feature_days_with_sales_56d"] = pre_56_dws.fillna(0.0).astype(float)
    working["feature_average_units_per_selling_day_28d"] = avg_upd_28.astype(float)
    working["feature_average_units_per_selling_day_56d"] = avg_upd_56.astype(float)
    working["feature_intermittent_demand_flag"] = intermittent_flag.astype(float)
    working["feature_sparse_repeat_purchase_flag"] = sparse_repeat_flag.astype(float)
    working["feature_sales_day_density_28d"] = density_28.astype(float)
    working["feature_sales_day_density_56d"] = density_56.astype(float)
    return working
