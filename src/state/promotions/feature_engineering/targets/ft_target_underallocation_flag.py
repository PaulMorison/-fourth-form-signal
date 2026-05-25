from __future__ import annotations

"""Underallocation-flag target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_target_underallocation_flag(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the governed underallocation flag target."""

    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    demand_reference = ensure_numeric_series(working, "demand_reference_units")
    working["target_underallocation_flag"] = (
        (stock_basis < demand_reference * 0.85)
        | (ensure_numeric_series(working, "target_stockout_flag") == 1)
    ).astype(int)
    return working
