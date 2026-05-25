from __future__ import annotations

"""Margin-pressure ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_margin_pressure(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add margin compression, dollars at risk, and expected GM change features."""

    del reference_frame
    working = frame.copy()
    regular_price = ensure_numeric_series(working, "regular_price_ex_gst_effective")
    promo_price = ensure_numeric_series(working, "promo_price_ex_gst_effective")
    cost_basis = ensure_numeric_series(working, "effective_cost_per_unit")
    baseline_units = ensure_numeric_series(working, "baseline_expected_units")
    demand_reference_units = ensure_numeric_series(working, "demand_reference_units")
    normal_margin = (regular_price - cost_basis).clip(lower=0.0)
    promo_margin = (promo_price - cost_basis).clip(lower=-promo_price.abs())
    margin_compression = (
        ensure_numeric_series(working, "gm_normal_pct")
        - ensure_numeric_series(working, "gm_promo_pct")
    )

    working["feature_effective_margin_compression_pct"] = margin_compression
    working["feature_margin_dollars_at_risk"] = (normal_margin - promo_margin).clip(lower=0.0) * baseline_units
    working["feature_expected_gm_change_dollars"] = (
        promo_margin * demand_reference_units - normal_margin * baseline_units
    )
    working["feature_margin_delta_per_unit"] = promo_margin - normal_margin
    working["feature_discount_to_margin_tradeoff"] = safe_ratio(
        ensure_numeric_series(working, "feature_discount_depth_pct"),
        margin_compression.abs(),
    )
    return working
