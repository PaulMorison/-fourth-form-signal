from __future__ import annotations

"""Stockout-risk proxy ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_stockout_risk_proxy(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add a stockout proxy from required demand exceeding stock."""

    del reference_frame
    working = frame.copy()
    required_units = ensure_numeric_series(working, "required_implied_units")
    total_stock_available = ensure_numeric_series(working, "total_stock_available").where(
        lambda values: values > 0.0,
        ensure_numeric_series(working, "stock_basis_units"),
    )
    working["feature_stockout_risk_proxy"] = safe_ratio(
        (required_units - total_stock_available).clip(lower=0.0),
        required_units,
    )
    return working
