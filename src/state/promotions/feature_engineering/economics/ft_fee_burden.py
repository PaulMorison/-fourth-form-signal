from __future__ import annotations

"""Fee-burden ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_fee_burden(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add fee-burden features relative to price and margin."""

    del reference_frame
    working = frame.copy()
    fees = ensure_numeric_series(working, "franchise_fees")
    promo_price = ensure_numeric_series(working, "promo_price_ex_gst_effective")
    promo_margin_before_fees = (
        promo_price - ensure_numeric_series(working, "effective_cost_per_unit")
    ).clip(lower=0.0)
    working["feature_fee_burden_ratio"] = safe_ratio(fees, promo_price)
    working["feature_fee_share_of_unit_margin"] = safe_ratio(fees, promo_margin_before_fees)
    return working
