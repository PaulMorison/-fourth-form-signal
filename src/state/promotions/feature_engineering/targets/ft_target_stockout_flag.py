from __future__ import annotations

"""Stockout-flag target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_target_stockout_flag(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the governed stockout flag target."""

    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    actual_units = ensure_numeric_series(working, "target_actual_units_sold")
    sell_through = ensure_numeric_series(working, "target_sell_through_pct")
    post_14d_units = ensure_numeric_series(working, "post_14d_units")
    working["target_stockout_flag"] = (
        (actual_units >= stock_basis * 0.98)
        | ((post_14d_units > 0.0) & (sell_through >= 0.9))
    ).astype(int)
    return working