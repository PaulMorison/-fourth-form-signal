from __future__ import annotations

"""Promo-field-context ft module."""

import pandas as pd

from state.promotions.feature_engineering.context.ft_cannibalisation_pressure import apply_ft_cannibalisation_pressure
from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series, ensure_text_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_promo_field_context(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add promo-field density and cohort-size context features."""

    del reference_frame
    working = apply_ft_cannibalisation_pressure(frame)
    promo_week = pd.to_datetime(working["promotion_start_date_date"], errors="coerce").dt.isocalendar().week.astype(int)
    store_category_density = working.groupby(
        [working["store_number_key"], ensure_text_series(working, "category"), promo_week]
    )["promotion_row_key"].transform("count")
    supplier_density = working.groupby(
        [working["store_number_key"], ensure_numeric_series(working, "inferred_supplier_number"), promo_week]
    )["promotion_row_key"].transform("count")
    cohort_total = working.groupby([working["store_number_key"], promo_week])["promotion_row_key"].transform("count")
    working["feature_store_category_promo_density"] = safe_ratio(
        store_category_density.astype(float),
        cohort_total.astype(float),
    )
    working["feature_supplier_promo_density"] = safe_ratio(
        supplier_density.astype(float),
        cohort_total.astype(float),
    )
    working["feature_promotion_name_cohort_size"] = working.groupby(
        ensure_text_series(working, "promotion_name")
    )["promotion_row_key"].transform("count").astype(float)
    working["feature_promo_type_cohort_size"] = working.groupby(
        ensure_text_series(working, "promo_type")
    )["promotion_row_key"].transform("count").astype(float)
    working["feature_source_file_cohort_size"] = working.groupby(
        ensure_text_series(working, "source_file")
    )["promotion_row_key"].transform("count").astype(float)
    working["feature_field_density_by_store_category_week"] = (
        ensure_numeric_series(working, "feature_store_category_promo_density")
        * ensure_numeric_series(working, "feature_local_promotional_field_density_score")
    )
    return working
