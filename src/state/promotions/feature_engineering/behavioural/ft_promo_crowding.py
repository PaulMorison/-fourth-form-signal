from __future__ import annotations

"""Promo-crowding ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_promo_crowding(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add crowding gravity based on overlapping nearby offers."""

    del reference_frame
    working = frame.copy()
    working["feature_promo_crowding_gravity_score"] = safe_ratio(
        ensure_numeric_series(working, "feature_category_overlap_discount_sum"),
        ensure_numeric_series(working, "feature_store_overlap_count"),
    )
    working["feature_local_promotional_field_density_score"] = ensure_numeric_series(
        working,
        "feature_local_promotional_field_density_score",
    )
    return working
