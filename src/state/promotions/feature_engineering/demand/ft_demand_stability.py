from __future__ import annotations

"""Demand-stability ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import bounded_score, ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_demand_stability(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add baseline volatility and demand stability features."""

    del reference_frame
    working = frame.copy()
    working["feature_baseline_volatility_cv"] = safe_ratio(
        ensure_numeric_series(working, "pre_56d_std_daily_units"),
        ensure_numeric_series(working, "baseline_daily_units"),
    )
    working["feature_demand_stability"] = bounded_score(
        working["feature_baseline_volatility_cv"].abs()
    )
    return working
