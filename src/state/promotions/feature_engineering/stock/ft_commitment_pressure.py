from __future__ import annotations

"""Commitment-pressure ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_commitment_pressure(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add stock commitment, on-order support, and congestion features."""

    del reference_frame
    working = frame.copy()
    committed_units = ensure_numeric_series(working, "total_units_commited")
    available_units = ensure_numeric_series(working, "total_stock_available")
    current_and_order = ensure_numeric_series(working, "current_soh") + ensure_numeric_series(working, "qty_on_order")
    working["feature_commitment_pressure_ratio"] = safe_ratio(committed_units, available_units)
    working["feature_on_order_support_ratio"] = safe_ratio(
        ensure_numeric_series(working, "qty_on_order"),
        ensure_numeric_series(working, "demand_reference_units"),
    )
    working["feature_inventory_congestion"] = safe_ratio(committed_units, current_and_order)
    return working
