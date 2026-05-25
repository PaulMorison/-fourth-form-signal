from __future__ import annotations

"""Model-input preparation for promotions training and scoring."""

from dataclasses import dataclass

import pandas as pd

from models.promotions.model_input_quality import (
    PromotionModelInputQualityReport,
    prepare_governed_model_input,
)


_BASE_NUMERIC_COLUMNS = (
    "store_number_key",
    "sku_number_key",
    "promotional_sku_id_key",
    "inferred_supplier_number",
    "catalogue_position",
    "regular_price",
    "promo_price",
    "norm_retail_inc_gst",
    "promo_retail_inc_gst",
    "promo_gst_component",
    "promo_price_ex_gst",
    "discount_amount",
    "discount_percent",
    "customer_discount",
    "scan_rebate_dollars",
    "scan_rebate_pct_last_cost",
    "last_received_cost",
    "promo_cost_price",
    "promo_effective_cost",
    "gm_normal_pct",
    "gm_promo_pct",
    "promo_gm_unit",
    "promo_gm_pct",
    "gross_profit_normal",
    "gross_profit_promo",
    "gross_profit_promo_dollars",
    "franchise_fees",
    "pack_size",
    "bar_units",
    "current_soh",
    "qty_on_order",
    "pl_allocation_qty",
    "pl_allocated",
    "store_adjusted_qty",
    "total_units_commited",
    "total_stock_available",
    "avg_8_wk_unit_sales",
    "avg_daily_units",
    "avg_1_wk_units",
    "promo_days",
    "tot_days_cover",
    "stock_turnover",
    "pl_extended_cost",
    "inventory_carrying_cost",
    "coverage_ratio_8w",
    "utilisation_ratio_8w",
    "gmroi_8w",
    "sales_promo_period_avg",
    "has_baseline_demand",
    "required_implied_daily",
    "pl_allocations_implied_multiple",
    "required_implied_multiple",
    "implied_uplift_in_sales",
    "live_promo_window_days",
    "pre_56d_units",
    "pre_28d_units",
    "pre_7d_units",
    "pre_56d_sales_ex_gst",
    "pre_56d_days_with_sales",
    "pre_56d_avg_daily_units",
    "pre_28d_avg_daily_units",
    "pre_7d_avg_daily_units",
    "pre_prior_21d_avg_daily_units",
    "pre_56d_std_daily_units",
    "pre_28d_std_daily_units",
    "baseline_daily_units",
    "baseline_expected_units",
    "baseline_expected_sales_ex_gst",
    "stock_basis_units",
    "required_implied_units",
    "demand_reference_units",
    "effective_cost_per_unit",
    "promo_price_ex_gst_effective",
    "regular_price_ex_gst_effective",
    "model_promo_start_month",
    "model_promo_start_week",
    "model_promo_start_dayofweek",
)

_BASE_CATEGORICAL_COLUMNS = (
    "promotion_name",
    "promo_type",
    "customer_offer",
    "sku_description",
    "department",
    "category",
)


@dataclass(frozen=True)
class PromotionModelInputSchema:
    feature_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    quality_report: PromotionModelInputQualityReport | None = None


def prepare_model_input_frame(
    frame: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...] | None = None,
    preserve_columns: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, PromotionModelInputSchema]:
    """Select and augment the leakage-safe feature columns used by the models."""

    working = frame.copy()
    promo_start = pd.to_datetime(working.get("promotion_start_date_date"), errors="coerce")
    working["model_promo_start_month"] = promo_start.dt.month.fillna(0).astype(int)
    working["model_promo_start_week"] = promo_start.dt.isocalendar().week.fillna(0).astype(int)
    working["model_promo_start_dayofweek"] = promo_start.dt.dayofweek.fillna(0).astype(int)

    model_input, quality_report = prepare_governed_model_input(
        working,
        raw_numeric_feature_columns=_BASE_NUMERIC_COLUMNS,
        categorical_feature_columns=_BASE_CATEGORICAL_COLUMNS,
        engineered_feature_columns=feature_columns,
        preserve_columns=preserve_columns,
    )
    return model_input, PromotionModelInputSchema(
        feature_columns=tuple(model_input.columns),
        numeric_columns=quality_report.numeric_feature_columns,
        categorical_columns=quality_report.categorical_feature_columns,
        quality_report=quality_report,
    )
