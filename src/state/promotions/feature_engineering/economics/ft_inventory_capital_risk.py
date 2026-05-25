from __future__ import annotations

"""Inventory-capital-risk ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_inventory_capital_risk(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add capital-at-risk and carrying-cost burden features."""

    del reference_frame
    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    effective_cost = ensure_numeric_series(working, "effective_cost_per_unit")
    capital_at_risk = stock_basis * effective_cost
    expected_profit = (
        ensure_numeric_series(working, "feature_unit_profit_after_fees")
        .clip(lower=0.0)
        * ensure_numeric_series(working, "demand_reference_units")
    )
    working["feature_capital_at_risk"] = capital_at_risk
    working["feature_inventory_carry_cost_burden"] = safe_ratio(
        ensure_numeric_series(working, "inventory_carrying_cost"),
        capital_at_risk,
    )
    working["feature_profit_risk_asymmetry"] = safe_ratio(capital_at_risk, expected_profit)
    working["feature_promo_capital_efficiency"] = safe_ratio(
        ensure_numeric_series(working, "demand_reference_units"),
        capital_at_risk,
    )
    working["feature_gmroi_regime_score"] = ensure_numeric_series(working, "gmroi_8w")
    return working
