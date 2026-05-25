from __future__ import annotations

"""Uplift target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_target_uplift(frame: pd.DataFrame) -> pd.DataFrame:
    """Add realized uplift versus the explicit pre-promo baseline."""

    working = frame.copy()
    working["target_realised_uplift_vs_baseline"] = safe_ratio(
        ensure_numeric_series(working, "target_actual_units_sold") - ensure_numeric_series(working, "baseline_expected_units"),
        ensure_numeric_series(working, "baseline_expected_units"),
    )
    return working
