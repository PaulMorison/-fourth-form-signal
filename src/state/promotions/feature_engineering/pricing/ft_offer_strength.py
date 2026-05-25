from __future__ import annotations

"""Offer-strength ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_offer_strength(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add numeric offer-strength and ticket-size regime features."""

    del reference_frame
    working = frame.copy()
    discount_depth = ensure_numeric_series(working, "feature_discount_depth_pct").where(
        lambda values: values > 0.0,
        safe_ratio(
            ensure_numeric_series(working, "discount_amount"),
            ensure_numeric_series(working, "regular_price_ex_gst_effective"),
        ),
    )
    explicit_customer_discount = safe_ratio(
        ensure_numeric_series(working, "customer_discount"),
        ensure_numeric_series(working, "regular_price_ex_gst_effective"),
    )
    catalogue_bonus = safe_ratio(
        pd.Series(1.0, index=working.index, dtype="float64"),
        ensure_numeric_series(working, "catalogue_position").where(lambda values: values > 0.0),
    )
    promo_price = ensure_numeric_series(working, "promo_price_ex_gst_effective")
    working["feature_offer_strength_score"] = (
        discount_depth * 0.6
        + explicit_customer_discount * 0.2
        + catalogue_bonus * 0.2
    )
    working["feature_low_ticket_flag"] = (promo_price <= 12.0).astype(float)
    working["feature_mid_ticket_flag"] = ((promo_price > 12.0) & (promo_price <= 20.0)).astype(float)
    working["feature_high_ticket_flag"] = (promo_price > 20.0).astype(float)
    return working
