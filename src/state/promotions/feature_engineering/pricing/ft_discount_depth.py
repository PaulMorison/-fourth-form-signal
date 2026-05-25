from __future__ import annotations

"""Discount-depth ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_discount_depth(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add discount depth as the promo markdown versus the regular ex-GST price."""

    del reference_frame
    working = frame.copy()
    regular_price = ensure_numeric_series(working, "regular_price_ex_gst_effective")
    promo_price = ensure_numeric_series(working, "promo_price_ex_gst_effective")
    working["feature_discount_depth_pct"] = safe_ratio(
        (regular_price - promo_price).clip(lower=0.0),
        regular_price,
    )
    return working
