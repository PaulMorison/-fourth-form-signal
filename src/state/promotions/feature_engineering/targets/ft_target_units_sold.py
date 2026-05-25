from __future__ import annotations

"""Units-sold target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_target_units_sold(frame: pd.DataFrame) -> pd.DataFrame:
    """Add realized net units sold as the canonical units target."""

    working = frame.copy()
    working["target_actual_units_sold"] = ensure_numeric_series(working, "actual_units_sold").clip(lower=0.0)
    return working
