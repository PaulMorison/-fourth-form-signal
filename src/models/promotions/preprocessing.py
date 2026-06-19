from __future__ import annotations

"""Model-input preparation for promotions training and scoring."""

from dataclasses import dataclass

import pandas as pd

from models.promotions.model_input_quality import (
    PromotionModelInputQualityError,
    PromotionModelInputQualityReport,
    iter_downstream_decision_support_feature_columns,
    iter_units_head_core_feature_columns,
    prepare_governed_model_input,
)
from state.promotions.feature_engineering.demand.ft_basket_structure_dependency import (
    BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_sparse_demand_noise import (
    SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.probability import (
    PROBABILITY_MODEL_USE_FEATURE_COLUMNS,
)

GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_historical_promo_events_same_discount",
    "feature_historical_units_same_discount_avg",
    "feature_probability_model_use_flag",
    "feature_probability_expected_units_consensus",
    *BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS,
    *SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS,
    *PROBABILITY_MODEL_USE_FEATURE_COLUMNS,
)

UNITS_HEAD_CORE_FEATURE_COLUMNS: tuple[str, ...] = iter_units_head_core_feature_columns()
DOWNSTREAM_DECISION_SUPPORT_FEATURE_COLUMNS: tuple[str, ...] = (
    iter_downstream_decision_support_feature_columns()
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

_NON_NUMERIC_GOVERNED_TRAINING_INPUT_COLUMNS: tuple[str, ...] = (
    "catalogue_position",
)

GOVERNED_NUMERIC_TRAINING_INPUT_COLUMNS: tuple[str, ...] = tuple(
    column_name
    for column_name in _BASE_NUMERIC_COLUMNS
    if column_name not in _NON_NUMERIC_GOVERNED_TRAINING_INPUT_COLUMNS
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

    effective_feature_columns = feature_columns or UNITS_HEAD_CORE_FEATURE_COLUMNS
    effective_preserve_columns = tuple(
        dict.fromkeys(
            (
                *GOVERNED_CRITICAL_MODEL_USE_FEATURE_COLUMNS,
                *(preserve_columns or ()),
            )
        )
    )
    model_input, quality_report = prepare_governed_model_input(
        working,
        raw_numeric_feature_columns=_BASE_NUMERIC_COLUMNS,
        categorical_feature_columns=_BASE_CATEGORICAL_COLUMNS,
        engineered_feature_columns=effective_feature_columns,
        preserve_columns=effective_preserve_columns,
    )
    if feature_columns is None:
        _assert_units_head_core_feature_contract(
            source_frame=working,
            model_input=model_input,
            quality_report=quality_report,
        )
    return model_input, PromotionModelInputSchema(
        feature_columns=tuple(model_input.columns),
        numeric_columns=quality_report.numeric_feature_columns,
        categorical_columns=quality_report.categorical_feature_columns,
        quality_report=quality_report,
    )


def _assert_units_head_core_feature_contract(
    *,
    source_frame: pd.DataFrame,
    model_input: pd.DataFrame,
    quality_report: PromotionModelInputQualityReport | None,
) -> None:
    explicitly_removed_columns = set(
        getattr(quality_report, "removed_feature_columns", ())
        if quality_report is not None
        else ()
    )
    required_columns = [
        column_name
        for column_name in UNITS_HEAD_CORE_FEATURE_COLUMNS
        if column_name in source_frame.columns and column_name not in explicitly_removed_columns
    ]
    missing = [column_name for column_name in required_columns if column_name not in model_input.columns]
    if not missing:
        return
    raise PromotionModelInputQualityError(
        "Core units-head engineered features are missing from the model input frame: "
        + ", ".join(missing)
    )
