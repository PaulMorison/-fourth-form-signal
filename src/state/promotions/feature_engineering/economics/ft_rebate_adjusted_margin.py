from __future__ import annotations

"""Rebate-adjusted margin ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_rebate_adjusted_margin(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add rebate-adjusted promo margin as a share of the promo selling price."""

    del reference_frame
    working = frame.copy()
    promo_price = ensure_numeric_series(working, "promo_price_ex_gst_effective")
    rebate_adjusted_cost = (
        ensure_numeric_series(working, "effective_cost_per_unit") - ensure_numeric_series(working, "scan_rebate_dollars")
    ).clip(lower=0.0)
    rebate_adjusted_margin = (promo_price - rebate_adjusted_cost).clip(lower=-promo_price.abs())
    working["feature_rebate_adjusted_margin_pct"] = safe_ratio(
        rebate_adjusted_margin,
        promo_price,
    )
    return working
