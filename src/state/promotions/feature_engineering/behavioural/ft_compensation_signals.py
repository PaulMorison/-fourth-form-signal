from __future__ import annotations

"""Compensation-signals ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_compensation_signals(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add compensation-needed and value-gap features."""

    del reference_frame
    working = frame.copy()
    working["feature_compensation_needed_score"] = (
        ensure_numeric_series(working, "feature_friction_to_conversion_burden")
        + ensure_numeric_series(working, "feature_composite_promo_instability")
        + ensure_numeric_series(working, "feature_inventory_carry_cost_burden")
    ) / 3.0
    working["feature_forced_sellthrough_discount_dependence"] = (
        ensure_numeric_series(working, "feature_discount_depth_pct")
        * ensure_numeric_series(working, "feature_overhang_risk")
    )
    working["feature_value_gap_score"] = (
        ensure_numeric_series(working, "feature_margin_sacrifice_per_expected_unit")
        + ensure_numeric_series(working, "feature_inventory_carry_cost_burden")
        - ensure_numeric_series(working, "feature_offer_strength_score")
    )
    return working
