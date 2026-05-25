from __future__ import annotations

"""Rebate-economics ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_rebate_economics(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add rebate-adjusted cost and dependency features."""

    del reference_frame
    working = frame.copy()
    promo_price = ensure_numeric_series(working, "promo_price_ex_gst_effective")
    effective_cost = ensure_numeric_series(working, "effective_cost_per_unit")
    rebate = ensure_numeric_series(working, "scan_rebate_dollars")
    rebate_adjusted_cost = (effective_cost - rebate).clip(lower=0.0)
    working["feature_rebate_adjusted_margin_pct"] = safe_ratio(
        promo_price - rebate_adjusted_cost,
        promo_price,
    )
    working["feature_rebate_dependency_score"] = safe_ratio(
        rebate,
        (promo_price - effective_cost).abs() + rebate,
    )
    working["feature_effective_cost_ratio"] = safe_ratio(effective_cost, promo_price)
    return working
