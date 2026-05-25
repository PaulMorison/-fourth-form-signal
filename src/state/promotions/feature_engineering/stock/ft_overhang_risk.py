from __future__ import annotations

"""Overhang-risk ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_overhang_risk(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add overhang, underallocation, and capital-risk exposure features."""

    del reference_frame
    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    demand_reference = ensure_numeric_series(working, "demand_reference_units")
    overhang_units = (stock_basis - demand_reference).clip(lower=0.0)
    underallocation_units = (demand_reference - stock_basis).clip(lower=0.0)
    working["feature_overhang_risk"] = safe_ratio(overhang_units, stock_basis)
    working["feature_underallocation_risk"] = safe_ratio(underallocation_units, demand_reference)
    working["feature_overhang_capital_risk"] = (
        overhang_units * ensure_numeric_series(working, "effective_cost_per_unit")
    )
    return working
