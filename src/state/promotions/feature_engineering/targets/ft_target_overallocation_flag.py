from __future__ import annotations

"""Overallocation-flag target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_target_overallocation_flag(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the governed overallocation flag target."""

    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    demand_reference = ensure_numeric_series(working, "demand_reference_units")
    leftover_pct = ensure_numeric_series(working, "target_leftover_stock_pct")
    working["target_overallocation_flag"] = (
        (stock_basis > demand_reference * 1.25) & (leftover_pct >= 0.2)
    ).astype(int)
    return working
