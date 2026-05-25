from __future__ import annotations

"""Unit-profitability ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_unit_profitability(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add unit-level profitability after fees and expected-flow pressure."""

    del reference_frame
    working = frame.copy()
    promo_price = ensure_numeric_series(working, "promo_price_ex_gst_effective")
    effective_cost = ensure_numeric_series(working, "effective_cost_per_unit")
    fees = ensure_numeric_series(working, "franchise_fees")
    demand_reference = ensure_numeric_series(working, "demand_reference_units")
    unit_profit_after_fees = promo_price - effective_cost - fees
    working["feature_unit_profit_after_fees"] = unit_profit_after_fees
    working["feature_unit_profitability_ratio"] = safe_ratio(unit_profit_after_fees, promo_price)
    working["feature_margin_sacrifice_per_expected_unit"] = safe_ratio(
        ensure_numeric_series(working, "feature_margin_dollars_at_risk"),
        demand_reference,
    )
    return working
