from __future__ import annotations

"""Leftover-stock target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_target_leftover_stock(frame: pd.DataFrame) -> pd.DataFrame:
    """Add leftover stock percentage after realized promo sales."""

    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    working["target_leftover_stock_pct"] = safe_ratio(
        (stock_basis - ensure_numeric_series(working, "target_actual_units_sold")).clip(lower=0.0),
        stock_basis,
    ).clip(lower=0.0, upper=1.0)
    return working
