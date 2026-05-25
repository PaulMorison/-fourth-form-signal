from __future__ import annotations

"""Baseline-demand ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_baseline_demand(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add the pre-promo rolling demand reference used across model families."""

    del reference_frame
    working = frame.copy()
    working["feature_pre_promo_rolling_demand_units"] = ensure_numeric_series(
        working,
        "baseline_expected_units",
    )
    working["feature_pre_promo_baseline_daily_units"] = ensure_numeric_series(
        working,
        "baseline_daily_units",
    )
    working["feature_baseline_volatility_cv"] = ensure_numeric_series(
        working,
        "pre_56d_std_daily_units",
    ).divide(
        ensure_numeric_series(working, "baseline_daily_units").replace(0.0, pd.NA)
    ).fillna(0.0)
    return working
