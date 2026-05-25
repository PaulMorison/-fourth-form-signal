from __future__ import annotations

"""Typed schema contracts for promotions cohort assignment and history.

Canon ownership:
- Declares the required base, target, and feature columns consumed by the
  promotions cohort and archetype layer.
- Keeps the cohort layer tied to the governed train-ready promotions dataset
  instead of redefining column meaning locally.
- Does not own cohort-key logic, history aggregation, similarity scoring, or
  reporting outputs.
"""

import pandas as pd

from state.promotions.promotion_frame_schema import coerce_promotions_frame_types


COHORT_BASE_COLUMNS = (
    "promotion_row_key",
    "promotion_name",
    "promo_type",
    "customer_offer",
    "department",
    "category",
    "source_file",
    "store_number_key",
    "sku_number_key",
    "promotion_start_date_date",
    "promotional_end_date_date",
    "inferred_supplier_number",
)

COHORT_TARGET_COLUMNS = (
    "target_actual_units_sold",
    "target_actual_sales_ex_gst",
    "target_actual_gross_profit_dollars",
    "target_sell_through_pct",
    "target_leftover_stock_pct",
    "target_stockout_flag",
    "target_overallocation_flag",
    "target_underallocation_flag",
    "target_realised_uplift_vs_baseline",
    "target_post_promo_followthrough_units",
    "target_post_promo_followthrough_sales_ex_gst",
)

COHORT_FEATURE_COLUMNS = (
    "feature_discount_depth_pct",
    "feature_price_gap_pct_vs_normal",
    "feature_offer_text_percent_flag",
    "feature_offer_text_amount_flag",
    "feature_offer_text_multi_buy_flag",
    "feature_offer_text_bonus_flag",
    "feature_effective_margin_compression_pct",
    "feature_rebate_dependency_score",
    "feature_total_stock_pressure_ratio",
    "feature_allocation_vs_baseline_demand_ratio",
    "feature_overhang_risk",
    "feature_pre_promo_baseline_daily_units",
    "feature_recent_acceleration_ratio",
    "feature_history_regime_score",
    "feature_baseline_instability_ratio",
    "feature_composite_promo_instability",
    "feature_short_long_demand_phase_alignment",
    "feature_promo_window_alignment_score",
    "feature_category_sync_score",
    "feature_store_sync_score",
    "feature_category_gravity",
    "feature_supplier_gravity",
    "feature_promo_crowding_gravity",
    "feature_field_density_score",
    "feature_local_promotional_field_density_score",
    "feature_store_category_promo_density",
    "feature_supplier_promo_density",
    "feature_store_level_promo_load",
)

COHORT_ASSIGNMENT_REQUIRED_COLUMNS = COHORT_BASE_COLUMNS + COHORT_FEATURE_COLUMNS

COHORT_REQUIRED_COLUMNS = COHORT_BASE_COLUMNS + COHORT_TARGET_COLUMNS + COHORT_FEATURE_COLUMNS

SIMILARITY_ANCHOR_FEATURE_COLUMNS = (
    "feature_discount_depth_pct",
    "feature_price_gap_pct_vs_normal",
    "feature_effective_margin_compression_pct",
    "feature_rebate_dependency_score",
    "feature_total_stock_pressure_ratio",
    "feature_allocation_vs_baseline_demand_ratio",
    "feature_overhang_risk",
    "feature_pre_promo_baseline_daily_units",
    "feature_recent_acceleration_ratio",
    "feature_composite_promo_instability",
    "feature_category_sync_score",
    "feature_category_gravity",
    "feature_field_density_score",
    "feature_store_category_promo_density",
)


def coerce_cohort_frame_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a promotions frame with stable numeric and datetime types."""

    return coerce_promotions_frame_types(frame)


def missing_required_cohort_columns(
    frame: pd.DataFrame,
    *,
    required_columns: tuple[str, ...] = COHORT_REQUIRED_COLUMNS,
) -> tuple[str, ...]:
    """Return the missing required cohort columns in stable order."""

    return tuple(column_name for column_name in required_columns if column_name not in frame.columns)