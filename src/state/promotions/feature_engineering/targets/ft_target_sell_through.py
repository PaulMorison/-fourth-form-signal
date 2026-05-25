from __future__ import annotations

"""Sell-through target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_target_sell_through(frame: pd.DataFrame) -> pd.DataFrame:
    """Add realized sell-through percentage as a governed target."""

    working = frame.copy()
    actual_units = ensure_numeric_series(working, "target_actual_units_sold")
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    working["target_sell_through_pct"] = safe_ratio(actual_units, stock_basis).clip(lower=0.0, upper=1.0)
    return working
