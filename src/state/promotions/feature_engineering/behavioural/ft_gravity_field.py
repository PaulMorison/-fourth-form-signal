from __future__ import annotations

"""Gravity-field ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_gravity_field(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add category, supplier, and substitute gravity features."""

    del reference_frame
    working = frame.copy()
    working["feature_category_gravity"] = (
        ensure_numeric_series(working, "feature_category_overlap_discount_sum")
        * ensure_numeric_series(working, "feature_category_share_in_store")
    )
    working["feature_supplier_gravity"] = (
        ensure_numeric_series(working, "feature_supplier_overlap_discount_sum")
        * ensure_numeric_series(working, "feature_supplier_concentration")
    )
    working["feature_promo_crowding_gravity"] = ensure_numeric_series(
        working,
        "feature_local_promotional_field_density_score",
    )
    working["feature_stock_capital_gravity"] = (
        ensure_numeric_series(working, "feature_capital_at_risk")
        * ensure_numeric_series(working, "feature_overhang_risk")
    )
    working["feature_field_density_score"] = ensure_numeric_series(
        working,
        "feature_local_promotional_field_density_score",
    )
    working["feature_local_competition_pressure"] = ensure_numeric_series(
        working,
        "feature_substitute_overlap_discount_sum",
    )
    working["feature_category_gravity_score"] = working["feature_category_gravity"]
    working["feature_supplier_gravity_score"] = working["feature_supplier_gravity"]
    working["feature_substitute_gravity_score"] = working["feature_local_competition_pressure"]
    return working
