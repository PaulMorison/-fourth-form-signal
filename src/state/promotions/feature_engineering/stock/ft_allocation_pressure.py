from __future__ import annotations

"""Allocation-pressure ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_allocation_pressure(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add allocation pressure ratios versus baseline and implied demand."""

    del reference_frame
    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    working["feature_allocation_vs_baseline_demand_ratio"] = safe_ratio(
        stock_basis,
        ensure_numeric_series(working, "baseline_expected_units"),
    )
    working["feature_allocation_vs_required_implied_demand_ratio"] = safe_ratio(
        stock_basis,
        ensure_numeric_series(working, "required_implied_units"),
    )
    working["feature_allocation_to_baseline_gap"] = (
        stock_basis - ensure_numeric_series(working, "baseline_expected_units")
    )
    working["feature_required_vs_allocation_gap"] = (
        ensure_numeric_series(working, "required_implied_units") - stock_basis
    )
    return working
