from __future__ import annotations

"""Price-gap ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_price_gap(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add unit and relative promo-vs-normal price gap features."""

    del reference_frame
    working = frame.copy()
    regular_price = ensure_numeric_series(working, "regular_price_ex_gst_effective")
    promo_price = ensure_numeric_series(working, "promo_price_ex_gst_effective")
    price_gap = (regular_price - promo_price).clip(lower=0.0)
    working["feature_price_gap_ex_gst"] = price_gap
    working["feature_price_gap_pct_vs_normal"] = safe_ratio(price_gap, regular_price)
    working["feature_promo_price_ratio_vs_normal"] = safe_ratio(promo_price, regular_price)
    return working
