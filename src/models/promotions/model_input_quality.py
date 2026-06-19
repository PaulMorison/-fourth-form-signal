from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import re
from typing import Sequence

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.ft_basket_context_feature_bundle import (
    BASKET_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_basket_equilibrium import (
    BASKET_EQUILIBRIUM_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_distribution_shape_distance import (
    DISTRIBUTION_SHAPE_DISTANCE_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_fragility_adjusted_opportunity import (
    FRAGILITY_ADJUSTED_OPPORTUNITY_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_kalman_state import (
    KALMAN_STATE_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_demand_uplift import (
    DEMAND_UPLIFT_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (
    ORDER_DECISION_DIAGNOSTICS_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_pca_residual_structure import (
    PCA_RESIDUAL_STRUCTURE_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_promotion_situational_awareness import (
    PROMOTION_SITUATIONAL_AWARENESS_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.probability import (
    PROBABILITY_MODEL_USE_FEATURE_COLUMNS,
    PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.stock.ft_target_stock_logic import (
    TARGET_STOCK_REVIEW_ONLY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules


ENGINEERED_FEATURE_PREFIX = "feature_"
TARGET_COLUMN_PREFIX = "target_"
NEAR_CONSTANT_DOMINANCE_THRESHOLD = 0.995
HIGH_NULL_RATE_THRESHOLD = 0.5
CORRELATION_REVIEW_THRESHOLD = 0.98

UNITS_HEAD_CORE_FEATURE_FAMILIES: tuple[str, ...] = (
    "basket_structure_dependency",
    "sparse_demand_noise",
    "probability",
    "same_discount_promo_history",
)

DOWNSTREAM_DECISION_SUPPORT_FEATURE_FAMILIES: tuple[str, ...] = (
    "basket_equilibrium",
    "target_stock_shape",
    "allocation_discipline",
    "micro_market_equilibrium",
    "fragility_opportunity_shape",
    "baseline_discount_uplift",
    "basket_context",
    "other_engineered_feature",
)

STRICT_NUMERIC_KEY_COLUMNS: tuple[str, ...] = (
    "store_number",
    "store_number_key",
    "sku_number_key",
    "inferred_supplier_number",
)

REQUIRED_GOVERNED_NUMERIC_KEY_COLUMNS: tuple[str, ...] = (
    "store_number_key",
    "sku_number_key",
)

AUDIT_ONLY_COLUMNS: tuple[str, ...] = (
    "source_file",
    "ingested_at",
)

RAW_PROMO_OUTCOME_COLUMNS: tuple[str, ...] = (
    "actual_units_sold",
    "actual_units_sold_promo",
    "actual_gross_profit_dollars",
    "actual_sales_ex_gst",
    "actual_sales_ex_gst_promo",
    "actual_sales_inc_gst",
    "actual_sales_inc_gst_promo",
    "actual_avg_daily_units",
    "actual_std_daily_units",
    "actual_peak_daily_units",
    "actual_avg_sales_ex_gst_per_selling_day",
    "actual_avg_sales_inc_gst_per_selling_day",
    "actual_avg_units_per_selling_day_promo",
    "actual_avg_sales_per_selling_day_promo",
    "actual_units_per_transaction",
    "actual_sales_ex_gst_per_transaction",
    "actual_transaction_count_promo",
    "actual_days_with_sales_promo",
    "actual_promo_transaction_intensity",
    "realised_transaction_count",
    "realised_promo_transaction_count",
    "promo_actual_units_sold",
    "promo_sales_day_count",
)

POST_EVENT_PREFIXES: tuple[str, ...] = (
    "post_",
    "actual_units_post_",
    "actual_sales_ex_gst_post_",
)

DOWNSTREAM_OUTPUT_PREFIXES: tuple[str, ...] = (
    "predicted_",
    "recommended_",
    "decision_",
    "final_",
    "forecast_",
)

BOUNDED_ZERO_ONE_COLUMNS: tuple[str, ...] = (
    "feature_prior_promo_price_memory_score",
    "feature_prior_promo_discount_memory_score",
    "feature_prior_promo_cannibalisation_risk_score",
    "feature_historical_discount_response_confidence",
    "feature_probability_zero_demand_same_or_better_discount",
    "feature_probability_low_demand_vs_baseline_same_or_better_discount",
    "feature_probability_demand_exceeds_allocation_same_or_better_discount",
    "feature_probability_units_below_allocation_same_or_better_discount",
    "feature_probability_stockout_vs_stock_basis_same_or_better_discount",
    "feature_promo_history_evidence_strength",
    "feature_sparse_history_penalty",
    "feature_order_evidence_quality_score",
    "feature_overallocation_risk_score",
    "feature_historical_zero_sale_after_buy_rate",
    "feature_same_discount_success_rate_56d",
    "feature_historical_trapped_capital_rate",
    "feature_historical_sell_through_on_accepted_qty",
    "feature_historical_allocation_efficiency_rate",
    "feature_historical_overallocation_above_floor_rate",
    "feature_historical_under_floor_missed_demand_rate",
    "feature_historical_memory_category_fallback_flag",
    "feature_historical_memory_department_fallback_flag",
    "feature_probability_poisson_zero_sale_probability",
    "feature_probability_poisson_one_or_more_sale_probability",
    "feature_probability_poisson_tail_probability",
    "feature_probability_poisson_overallocation_risk_score",
    "feature_probability_negative_binomial_zero_sale_probability",
    "feature_probability_negative_binomial_tail_probability",
    "feature_probability_negative_binomial_dispersion_score",
    "feature_probability_negative_binomial_overallocation_risk_score",
    "feature_probability_bayesian_poisson_tail_probability",
    "feature_probability_bayesian_poisson_confidence_score",
    "feature_probability_zero_inflation_rate",
    "feature_probability_zero_inflated_zero_sale_probability",
    "feature_probability_zero_inflated_nonzero_probability",
    "feature_probability_zero_inflated_overallocation_risk_score",
    "feature_units_lift_p_value",
    "feature_units_lift_stability_score",
    "feature_basket_attach_rate_p_value",
    "feature_same_discount_repeatability_score",
    "feature_same_discount_response_p_value",
    "feature_probability_sold_in_multi_item_basket_rate",
    "feature_probability_sold_as_solo_item_rate",
    "feature_probability_companion_dependency_score",
    "feature_probability_companion_overallocation_risk_score",
    "feature_probability_zero_sale_consensus",
    "feature_probability_tail_risk_consensus",
    "feature_probability_overallocation_risk_score",
    "feature_probability_demand_confidence_score",
    "feature_probability_model_use_flag",
    "feature_probability_expected_sell_through_pct",
    "feature_probability_allocation_discipline_score",
    "feature_same_discount_history_available_flag",
    "feature_non_promo_days_with_sales_ratio_30d",
    "feature_non_promo_days_with_sales_ratio_56d",
    "feature_non_promo_base_demand_growing_flag",
    "feature_non_promo_history_available_flag",
    "feature_non_promo_low_history_flag",
    "feature_non_promo_stable_history_flag",
    "feature_discount_elasticity_confidence_score",
    "feature_discount_response_r_squared",
    "feature_discount_response_direction_consistent_flag",
    "feature_uplift_confidence_score",
    "feature_uplift_share_of_total_expected_units",
    "feature_uplift_demand_support_flag",
    "feature_uplift_supported_sell_through_pct",
    "feature_uplift_allocation_discipline_score",
    "feature_supported_sell_through_score",
    "feature_discount_evidence_strength_score",
    "feature_allocation_risk_over_uplift_score",
    "feature_launch_stock_support_score",
    "feature_total_window_pressure_vs_launch_support_conflict_score",
    "feature_stock_below_trust_floor_flag",
    "feature_trust_floor_missed_demand_risk_score",
    "feature_expected_bill_cycle_capital_drag_ratio",
    "feature_speculative_above_trust_floor_risk_flag",
    "feature_inventory_sufficiency_flag",
    "feature_weak_promo_low_value_flag",
    "feature_high_underlying_demand_flag",
    "feature_no_promo_history_flag",
    "feature_month_end_cash_runoff_pressure_flag",
    "feature_order_risk_reason_same_discount_weak_flag",
    "feature_order_risk_reason_elasticity_weak_flag",
    "feature_order_risk_reason_uplift_weak_flag",
    "feature_order_risk_reason_base_trend_falling_flag",
    "feature_order_risk_reason_launch_total_conflict_flag",
    "feature_order_risk_reason_stock_vs_supported_gap_high_flag",
    "feature_order_risk_reason_sparse_history_flag",
    "feature_order_risk_overallocation_score",
    "feature_order_support_strength_score",
    "feature_order_review_priority_score",
    "feature_basket_attach_rate",
    "feature_sku_solo_purchase_rate",
    "feature_sku_basket_dependency_score",
    "feature_top_companion_sku_1_share",
    "feature_top_companion_sku_2_share",
    "feature_companion_concentration_index",
    "feature_basket_diversity_when_sku_present",
    "feature_weekend_share_with_sku",
    "feature_pay_cycle_sensitivity_score",
    "feature_stock_constrained_history_flag",
    "feature_lost_sales_risk_score",
    "feature_probability_sku_in_multi_item_basket",
    "feature_probability_sku_solo_purchase",
    "feature_probability_units_given_multi_item_basket",
    "feature_probability_zero_units_given_low_traffic",
    "feature_companion_absence_risk_score",
    "feature_anchor_centrality_score",
    "feature_anchor_presence_support_score",
    "feature_top_anchor_dependency_score",
    "feature_anchor_absence_risk_score",
    "feature_drag_along_probability",
    "feature_companion_cluster_support_score",
    "feature_companion_concentration_score",
    "feature_multi_sku_promo_basket_rate",
    "feature_three_plus_promo_sku_basket_rate",
    "feature_solo_purchase_rate",
    "feature_sparse_random_purchase_score",
    "feature_basket_noise_score",
    "feature_transaction_object_uncertainty_score",
    "feature_conditional_sale_rate_with_anchor",
    "feature_conditional_sale_rate_without_anchor",
    "feature_substitution_pressure_score",
    "feature_promo_basket_depth_alignment_score",
    "feature_anchor_mix_stability_score",
    "feature_basket_equilibrium_score",
    "feature_basket_equilibrium_fragility_score",
    "feature_basket_history_missing_evidence_flag",
    "feature_pca_structure_residual_score",
    "feature_pca_structure_fit_score",
    "feature_pca_structure_outlier_flag",
    "feature_pca_allocation_residual_score",
    "feature_pca_allocation_outlier_flag",
)

_INTEGERISH_PATTERN = re.compile(r"^[+-]?\d+(?:\.0+)?$")


class PromotionModelInputQualityError(ValueError):
    """Raised when the governed model-input quality contract is violated."""


@dataclass(frozen=True)
class PromotionModelInputQualityReport:
    source_row_count: int
    feature_columns: tuple[str, ...]
    numeric_feature_columns: tuple[str, ...]
    categorical_feature_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    metadata_columns: tuple[str, ...]
    leakage_risk_columns: tuple[str, ...]
    normalized_text_columns: tuple[str, ...]
    removed_feature_columns: tuple[str, ...]
    mixed_type_key_columns: tuple[str, ...]
    column_audit: pd.DataFrame
    leakage_review: pd.DataFrame
    correlation_review: pd.DataFrame
    summary_frame: pd.DataFrame
    summary_payload: dict[str, object]

    def removed_feature_columns_for_reason(self, reason: str) -> tuple[str, ...]:
        rows = self.column_audit.loc[
            self.column_audit["removal_reason"].astype(str).eq(reason), "column_name"
        ].astype(str)
        return tuple(rows.tolist())


def iter_registered_model_feature_columns() -> tuple[str, ...]:
    columns: list[str] = []
    seen: set[str] = set()
    for definition in iter_registered_feature_modules():
        for column_name in definition.output_columns:
            if column_name in seen:
                continue
            seen.add(column_name)
            columns.append(column_name)
    return tuple(columns)


def _registered_feature_module_by_column() -> dict[str, str]:
    module_by_feature: dict[str, str] = {}
    for definition in iter_registered_feature_modules():
        for column_name in definition.output_columns:
            module_by_feature.setdefault(str(column_name), definition.name)
    return module_by_feature


def _feature_family_for_column(column_name: str, module_name: str) -> str:
    lowered_feature = column_name.lower()
    lowered_module = module_name.lower()
    if "basket_equilibrium" in lowered_module or any(
        token in lowered_feature
        for token in (
            "anchor_centrality",
            "anchor_presence_support",
            "top_anchor_dependency",
            "multi_sku_promo_basket_rate",
            "three_plus_promo_sku_basket_rate",
            "basket_equilibrium",
            "conditional_sale_rate_with_anchor",
            "conditional_lift_with_anchor",
            "transaction_object_uncertainty",
        )
    ):
        return "basket_equilibrium"
    if "basket_structure_dependency" in lowered_module:
        return "basket_structure_dependency"
    if "micro_market_equilibrium" in lowered_module or any(
        token in lowered_feature
        for token in (
            "micro_market_",
            "local_equilibrium_gap",
            "small_unit_option_value",
            "convexity_to_capital",
            "trust_floor_convexity",
            "high_demand_underprotection",
            "end_shape_fragility",
        )
    ):
        return "micro_market_equilibrium"
    if "sparse_demand_noise" in lowered_module or "sparse_demand" in lowered_feature:
        return "sparse_demand_noise"
    if "kalman" in lowered_module or "kalman" in lowered_feature:
        return "kalman_state"
    if "distribution_shape" in lowered_module or "wasserstein" in lowered_feature:
        return "distribution_shape_distance"
    if "dag" in lowered_feature or "dependency_support" in lowered_feature:
        return "dag_dependency_support"
    if "fragility_adjusted_opportunity" in lowered_module:
        return "fragility_opportunity"
    if "pca" in lowered_feature or "pca" in lowered_module:
        return "pca"
    if "situational_awareness" in lowered_module or "situational" in lowered_feature:
        return "situational_awareness"
    if "probability" in lowered_feature or "probability" in lowered_module:
        return "probability"
    if "target_stock" in lowered_module or "end_of_promo_target" in lowered_feature:
        return "target_stock_shape"
    if "allocation" in lowered_module or any(
        token in lowered_feature
        for token in ("allocation", "trust_floor", "capital_tied", "overallocation")
    ):
        return "allocation_discipline"
    if any(
        token in lowered_feature
        for token in ("same_discount", "same_or_better", "prior_promo", "promo_history", "historical_")
    ):
        return "same_discount_promo_history"
    if any(
        token in lowered_feature or token in lowered_module
        for token in ("fragility", "opportunity", "survival", "shape", "growth_curve")
    ):
        return "fragility_opportunity_shape"
    if "basket" in lowered_feature or "basket" in lowered_module:
        return "basket_context"
    if any(token in lowered_module for token in ("discount", "uplift", "baseline")):
        return "baseline_discount_uplift"
    return "other_engineered_feature"


def classify_engineered_feature_role(column_name: str) -> str:
    review_only_feature_columns = _review_only_engineered_feature_columns()
    if column_name in review_only_feature_columns:
        return "review_only"
    module_by_feature = _registered_feature_module_by_column()
    family_name = _feature_family_for_column(column_name, module_by_feature.get(column_name, ""))
    if family_name in UNITS_HEAD_CORE_FEATURE_FAMILIES:
        return "units_head_core"
    if family_name in DOWNSTREAM_DECISION_SUPPORT_FEATURE_FAMILIES:
        return "downstream_decision_support"
    return "downstream_decision_support"


def iter_units_head_core_feature_columns() -> tuple[str, ...]:
    return tuple(
        column_name
        for column_name in iter_registered_model_feature_columns()
        if classify_engineered_feature_role(column_name) == "units_head_core"
    )


def iter_downstream_decision_support_feature_columns() -> tuple[str, ...]:
    return tuple(
        column_name
        for column_name in iter_registered_model_feature_columns()
        if classify_engineered_feature_role(column_name) == "downstream_decision_support"
    )


def iter_default_model_use_feature_columns() -> tuple[str, ...]:
    review_only_feature_columns = _review_only_engineered_feature_columns()
    return tuple(
        column_name
        for column_name in iter_registered_model_feature_columns()
        if column_name not in review_only_feature_columns
    )


def iter_review_only_engineered_feature_columns() -> tuple[str, ...]:
    """Return registered engineered feature columns governed as review-only."""

    return tuple(
        dict.fromkeys(
            (
                *PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS,
                *BASKET_REVIEW_ONLY_FEATURE_COLUMNS,
                *BASKET_EQUILIBRIUM_REVIEW_ONLY_FEATURE_COLUMNS,
                *DEMAND_UPLIFT_REVIEW_ONLY_FEATURE_COLUMNS,
                *PCA_RESIDUAL_STRUCTURE_REVIEW_ONLY_FEATURE_COLUMNS,
                *PROMOTION_SITUATIONAL_AWARENESS_REVIEW_ONLY_FEATURE_COLUMNS,
                *ORDER_DECISION_DIAGNOSTICS_REVIEW_ONLY_FEATURE_COLUMNS,
                *TARGET_STOCK_REVIEW_ONLY_FEATURE_COLUMNS,
                *KALMAN_STATE_REVIEW_ONLY_FEATURE_COLUMNS,
                *DISTRIBUTION_SHAPE_DISTANCE_REVIEW_ONLY_FEATURE_COLUMNS,
                *FRAGILITY_ADJUSTED_OPPORTUNITY_REVIEW_ONLY_FEATURE_COLUMNS,
            )
        )
    )


def filter_model_use_engineered_feature_columns(
    engineered_feature_columns: Sequence[str],
) -> tuple[str, ...]:
    review_only_feature_columns = _review_only_engineered_feature_columns()
    filtered: list[str] = []
    seen: set[str] = set()
    for column_name in engineered_feature_columns:
        if column_name in review_only_feature_columns or column_name in seen:
            continue
        seen.add(column_name)
        filtered.append(column_name)
    return tuple(filtered)


def _review_only_engineered_feature_columns() -> set[str]:
    return set(iter_review_only_engineered_feature_columns())


def classify_leakage_risk(column_name: str) -> tuple[str, str] | None:
    if column_name.startswith(TARGET_COLUMN_PREFIX):
        return "target_column", "Target columns are supervised outcomes, not model inputs."
    if column_name in RAW_PROMO_OUTCOME_COLUMNS:
        return "raw_promo_outcome", "Realised during-promotion outcome column."
    if any(
        column_name.startswith(prefix) or prefix in column_name
        for prefix in POST_EVENT_PREFIXES
    ):
        return "post_event_outcome", "Post-event outcome column."
    if column_name in AUDIT_ONLY_COLUMNS:
        return "audit_only", "Audit-only field retained for traceability rather than training."
    if any(column_name.startswith(prefix) for prefix in DOWNSTREAM_OUTPUT_PREFIXES):
        return "downstream_decision_output", "Downstream predicted or decision output column."
    return None


def is_hard_leakage_risk(column_name: str) -> bool:
    classification = classify_leakage_risk(column_name)
    return classification is not None and classification[0] != "audit_only"


def prepare_governed_model_input(
    frame: pd.DataFrame,
    *,
    raw_numeric_feature_columns: Sequence[str],
    categorical_feature_columns: Sequence[str],
    engineered_feature_columns: Sequence[str] | None = None,
    preserve_columns: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, PromotionModelInputQualityReport]:
    duplicate_name_counts = pd.Series(list(frame.columns), dtype="object").value_counts()
    duplicate_name_columns = duplicate_name_counts.loc[duplicate_name_counts > 1].index.astype(str).tolist()
    if duplicate_name_columns:
        raise PromotionModelInputQualityError(
            f"Duplicate model-input source columns are not allowed: {duplicate_name_columns}"
        )

    working = frame.copy()
    normalized_text_columns = _normalize_text_columns(working)
    mixed_type_table = _build_mixed_type_table(working)
    required_key_issues = _build_required_numeric_key_issue_table(working)
    if not required_key_issues.empty:
        issue_text = _format_required_numeric_key_issue_text(required_key_issues)
        raise PromotionModelInputQualityError(
            "Invalid governed numeric key fields detected: " + issue_text
        )
    mixed_type_key_columns = tuple(
        mixed_type_table.loc[
            mixed_type_table["strict_numeric_key_flag"].astype(bool)
            & mixed_type_table["mixed_type_flag"].astype(bool),
            "column_name",
        ].astype(str)
    )
    if mixed_type_key_columns:
        raise PromotionModelInputQualityError(
            "Mixed-type governed numeric key fields detected: "
            + ", ".join(mixed_type_key_columns)
        )

    target_columns = tuple(
        column_name
        for column_name in working.columns
        if str(column_name).startswith(TARGET_COLUMN_PREFIX)
    )
    leakage_review = _build_leakage_review(working.columns)
    leakage_risk_columns = tuple(leakage_review["column_name"].astype(str).tolist())

    selected_engineered_feature_columns = _selected_engineered_feature_columns(
        working.columns,
        engineered_feature_columns=engineered_feature_columns,
    )
    raw_numeric_candidates = tuple(
        column_name for column_name in raw_numeric_feature_columns if column_name in working.columns
    )
    categorical_candidates = tuple(
        column_name for column_name in categorical_feature_columns if column_name in working.columns
    )

    candidate_feature_columns: list[str] = []
    seen_candidates: set[str] = set()
    for column_name in (*raw_numeric_candidates, *selected_engineered_feature_columns, *categorical_candidates):
        if column_name in seen_candidates:
            continue
        seen_candidates.add(column_name)
        if column_name in target_columns or is_hard_leakage_risk(column_name):
            continue
        candidate_feature_columns.append(column_name)
    preserved_feature_columns = {
        column_name
        for column_name in (preserve_columns or ())
        if column_name in candidate_feature_columns
    }

    removal_reason_by_column: dict[str, str] = {}
    removal_detail_by_column: dict[str, str] = {}
    duplicate_to_kept = _duplicate_content_map(working)
    for column_name in candidate_feature_columns:
        if column_name in preserved_feature_columns:
            continue
        kept_column = duplicate_to_kept.get(column_name)
        if kept_column is None:
            continue
        removal_reason_by_column[column_name] = "duplicate_content_feature"
        removal_detail_by_column[column_name] = f"kept={kept_column}"

    registry_feature_set = set(iter_registered_model_feature_columns())
    for column_name in working.columns:
        if not str(column_name).startswith(ENGINEERED_FEATURE_PREFIX):
            continue
        if column_name in selected_engineered_feature_columns:
            continue
        removal_reason_by_column[str(column_name)] = "unregistered_engineered_feature"
        detail = "feature_not_registered"
        if column_name in registry_feature_set:
            detail = "feature_not_selected"
        removal_detail_by_column[str(column_name)] = detail

    numeric_feature_columns: list[str] = []
    categorical_feature_columns_selected: list[str] = []
    for column_name in candidate_feature_columns:
        if column_name in removal_reason_by_column:
            continue
        if column_name in categorical_candidates:
            categorical_feature_columns_selected.append(column_name)
            continue
        coerced = pd.to_numeric(working[column_name], errors="coerce")
        if coerced.notna().any():
            working[column_name] = coerced
            numeric_feature_columns.append(column_name)
            continue
        if column_name in preserved_feature_columns:
            working[column_name] = coerced
            numeric_feature_columns.append(column_name)
            continue
        if column_name in selected_engineered_feature_columns and working[column_name].notna().any():
            raise PromotionModelInputQualityError(
                f"Engineered feature lost numeric signal before model input: {column_name}"
            )
        removal_reason_by_column[column_name] = "no_numeric_signal_after_coercion"
        removal_detail_by_column[column_name] = "numeric_allowlist_column_not_numeric_after_cleaning"

    constant_feature_columns = _constant_feature_columns(
        working,
        feature_columns=(*numeric_feature_columns, *categorical_feature_columns_selected),
    )
    for column_name, reason in constant_feature_columns.items():
        if column_name in preserved_feature_columns:
            continue
        removal_reason_by_column[column_name] = reason
        removal_detail_by_column[column_name] = "dead_constant_feature_removed"

    final_numeric_feature_columns = tuple(
        column_name
        for column_name in numeric_feature_columns
        if column_name not in removal_reason_by_column
    )
    final_categorical_feature_columns = tuple(
        column_name
        for column_name in categorical_feature_columns_selected
        if column_name not in removal_reason_by_column
    )
    final_feature_columns = (*final_numeric_feature_columns, *final_categorical_feature_columns)

    cleaned_model_input = working.loc[:, final_feature_columns].copy()
    correlation_review = _build_correlation_review(
        cleaned_model_input,
        numeric_feature_columns=final_numeric_feature_columns,
    )

    metadata_columns = tuple(
        column_name
        for column_name in working.columns
        if column_name not in set(final_feature_columns)
        and column_name not in set(target_columns)
        and column_name not in set(leakage_risk_columns)
    )

    column_audit = _build_column_audit(
        original_frame=frame,
        cleaned_frame=working,
        target_columns=target_columns,
        leakage_review=leakage_review,
        mixed_type_table=mixed_type_table,
        duplicate_name_counts=duplicate_name_counts,
        duplicate_to_kept=duplicate_to_kept,
        selected_candidate_feature_columns=tuple(candidate_feature_columns),
        final_feature_columns=final_feature_columns,
        removal_reason_by_column=removal_reason_by_column,
        removal_detail_by_column=removal_detail_by_column,
    )
    summary_payload = _build_summary_payload(
        source_frame=frame,
        cleaned_model_input=cleaned_model_input,
        target_columns=target_columns,
        metadata_columns=metadata_columns,
        leakage_risk_columns=leakage_risk_columns,
        normalized_text_columns=normalized_text_columns,
        column_audit=column_audit,
        correlation_review=correlation_review,
        mixed_type_key_columns=mixed_type_key_columns,
    )
    summary_frame = pd.DataFrame(
        [{"metric": key, "value": _summary_value_to_text(value)} for key, value in summary_payload.items()]
    )

    report = PromotionModelInputQualityReport(
        source_row_count=int(len(frame.index)),
        feature_columns=tuple(final_feature_columns),
        numeric_feature_columns=final_numeric_feature_columns,
        categorical_feature_columns=final_categorical_feature_columns,
        target_columns=target_columns,
        metadata_columns=metadata_columns,
        leakage_risk_columns=leakage_risk_columns,
        normalized_text_columns=normalized_text_columns,
        removed_feature_columns=tuple(
            column_audit.loc[
                column_audit["selected_for_model_flag"].astype(bool)
                & column_audit["removed_from_model_flag"].astype(bool),
                "column_name",
            ].astype(str)
        ),
        mixed_type_key_columns=mixed_type_key_columns,
        column_audit=column_audit,
        leakage_review=leakage_review,
        correlation_review=correlation_review,
        summary_frame=summary_frame,
        summary_payload=summary_payload,
    )
    return cleaned_model_input, report


def build_model_input_quality_summary_text(
    *,
    stage_label: str,
    report: PromotionModelInputQualityReport,
) -> str:
    removed_columns = report.column_audit.loc[
        report.column_audit["removed_from_model_flag"].astype(bool),
        ["column_name", "removal_reason", "removal_detail"],
    ]
    high_null_columns = report.column_audit.loc[
        report.column_audit["high_null_flag"].astype(bool), "column_name"
    ].astype(str)
    lines = [
        "PROMOTIONS MODEL INPUT QUALITY AUDIT",
        f"stage: {stage_label}",
        f"source rows: {report.source_row_count}",
        f"selected feature count: {len(report.feature_columns)}",
        f"numeric feature count: {len(report.numeric_feature_columns)}",
        f"categorical feature count: {len(report.categorical_feature_columns)}",
        f"target column count: {len(report.target_columns)}",
        f"metadata column count: {len(report.metadata_columns)}",
        f"leakage-risk column count: {len(report.leakage_risk_columns)}",
        f"normalized text columns: {len(report.normalized_text_columns)}",
        f"removed feature columns: {len(report.removed_feature_columns)}",
    ]
    if removed_columns.empty:
        lines.append("removed feature detail: none")
    else:
        lines.append("removed feature detail:")
        for row in removed_columns.itertuples(index=False):
            detail = f" ({row.removal_detail})" if str(row.removal_detail) else ""
            lines.append(f"- {row.column_name}: {row.removal_reason}{detail}")
    if high_null_columns.empty:
        lines.append("high-null columns: none")
    else:
        lines.append("high-null columns:")
        for column_name in high_null_columns.tolist()[:20]:
            lines.append(f"- {column_name}")
    if report.correlation_review.empty:
        lines.append("high-correlation review: none above threshold")
    else:
        lines.append("high-correlation review:")
        for row in report.correlation_review.head(10).itertuples(index=False):
            lines.append(
                f"- {row.left_column_name} vs {row.right_column_name}: corr={float(row.correlation):.4f}"
            )
    return "\n".join(lines) + "\n"


def _normalize_text_columns(frame: pd.DataFrame) -> tuple[str, ...]:
    normalized_columns: list[str] = []
    for column_name in frame.columns:
        series = frame[column_name]
        if not (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype)
        ):
            continue
        normalized_columns.append(str(column_name))
        normalized = series.map(_normalize_text_value)
        frame[column_name] = normalized.astype(object)
    return tuple(normalized_columns)


def _normalize_text_value(value: object) -> object:
    if value is None or pd.isna(value):
        return pd.NA
    normalized = " ".join(str(value).split())
    return pd.NA if normalized == "" else normalized


def _build_mixed_type_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for column_name in frame.columns:
        series = frame[column_name]
        if not (
            str(column_name) in STRICT_NUMERIC_KEY_COLUMNS
            or pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype)
        ):
            continue
        non_null = series.dropna()
        if non_null.empty:
            continue
        stringified = non_null.astype(str)
        numeric_like_mask = stringified.str.fullmatch(_INTEGERISH_PATTERN)
        numeric_like_count = int(numeric_like_mask.sum())
        nonnumeric_like = stringified.loc[~numeric_like_mask]
        nonnumeric_like_count = int(len(nonnumeric_like.index))
        mixed_type_flag = numeric_like_count > 0 and nonnumeric_like_count > 0
        if not mixed_type_flag and str(column_name) not in STRICT_NUMERIC_KEY_COLUMNS:
            continue
        rows.append(
            {
                "column_name": str(column_name),
                "numeric_like_count": numeric_like_count,
                "nonnumeric_like_count": nonnumeric_like_count,
                "mixed_type_flag": mixed_type_flag,
                "strict_numeric_key_flag": str(column_name) in STRICT_NUMERIC_KEY_COLUMNS,
                "sample_nonnumeric_values": "|".join(nonnumeric_like.unique().tolist()[:5]),
            }
        )
    return pd.DataFrame(
        rows,
        columns=(
            "column_name",
            "numeric_like_count",
            "nonnumeric_like_count",
            "mixed_type_flag",
            "strict_numeric_key_flag",
            "sample_nonnumeric_values",
        ),
    )


def _build_required_numeric_key_issue_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for column_name in REQUIRED_GOVERNED_NUMERIC_KEY_COLUMNS:
        if column_name not in frame.columns:
            continue
        series = frame[column_name]
        numeric = pd.to_numeric(series, errors="coerce").astype("float64")
        finite_mask = pd.Series(np.isfinite(numeric.to_numpy()), index=series.index)
        null_mask = series.isna()
        non_numeric_mask = series.notna() & numeric.isna()
        non_integer_mask = series.notna() & numeric.notna() & (
            ~finite_mask | ~numeric.mod(1).eq(0)
        )
        issue_mask = null_mask | non_numeric_mask | non_integer_mask
        if not bool(issue_mask.any()):
            continue
        sample_values = [
            str(value)
            for value in series.loc[issue_mask].drop_duplicates().head(5).tolist()
        ]
        rows.append(
            {
                "column_name": column_name,
                "invalid_row_count": int(issue_mask.sum()),
                "null_count": int(null_mask.sum()),
                "non_numeric_count": int(non_numeric_mask.sum()),
                "non_integer_count": int(non_integer_mask.sum()),
                "sample_invalid_values": "|".join(sample_values),
            }
        )
    return pd.DataFrame(
        rows,
        columns=(
            "column_name",
            "invalid_row_count",
            "null_count",
            "non_numeric_count",
            "non_integer_count",
            "sample_invalid_values",
        ),
    )


def _format_required_numeric_key_issue_text(issue_table: pd.DataFrame) -> str:
    parts: list[str] = []
    for row in issue_table.itertuples(index=False):
        parts.append(
            f"{row.column_name} "
            f"(invalid_rows={int(row.invalid_row_count)}, "
            f"nulls={int(row.null_count)}, "
            f"non_numeric={int(row.non_numeric_count)}, "
            f"non_integer={int(row.non_integer_count)})"
        )
    return ", ".join(parts)


def _build_leakage_review(columns: Sequence[object]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for column_name in columns:
        classification = classify_leakage_risk(str(column_name))
        if classification is None:
            continue
        rows.append(
            {
                "column_name": str(column_name),
                "classification": classification[0],
                "reason": classification[1],
            }
        )
    return pd.DataFrame(rows, columns=("column_name", "classification", "reason"))


def _selected_engineered_feature_columns(
    columns: Sequence[object],
    *,
    engineered_feature_columns: Sequence[str] | None,
) -> tuple[str, ...]:
    selected = (
        filter_model_use_engineered_feature_columns(engineered_feature_columns)
        if engineered_feature_columns is not None
        else iter_default_model_use_feature_columns()
    )
    available = {str(column_name) for column_name in columns}
    ordered: list[str] = []
    seen: set[str] = set()
    for column_name in selected:
        if column_name not in available or column_name in seen:
            continue
        seen.add(column_name)
        ordered.append(column_name)
    return tuple(ordered)


def _duplicate_content_map(frame: pd.DataFrame) -> dict[str, str]:
    canonical_by_signature: dict[str, str] = {}
    duplicate_to_kept: dict[str, str] = {}
    for column_name in frame.columns:
        series = frame[column_name]
        signature = _series_content_signature(series)
        canonical = canonical_by_signature.get(signature)
        if canonical is None:
            canonical_by_signature[signature] = str(column_name)
            continue
        duplicate_to_kept[str(column_name)] = canonical
    return duplicate_to_kept


def _series_content_signature(series: pd.Series) -> str:
    hashed = pd.util.hash_pandas_object(series, index=False)
    digest = sha1()
    digest.update(str(series.dtype).encode("utf-8"))
    digest.update(hashed.to_numpy(dtype="uint64", copy=False).tobytes())
    return digest.hexdigest()


def _constant_feature_columns(
    frame: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for column_name in feature_columns:
        non_null = frame[column_name].dropna()
        unique_count = int(non_null.nunique(dropna=True))
        if unique_count == 0:
            reasons[column_name] = "all_null_feature"
            continue
        if unique_count == 1:
            reasons[column_name] = "constant_feature"
    return reasons


def _build_correlation_review(
    frame: pd.DataFrame,
    *,
    numeric_feature_columns: Sequence[str],
) -> pd.DataFrame:
    if len(numeric_feature_columns) < 2 or len(frame.index) < 3:
        return pd.DataFrame(
            columns=("left_column_name", "right_column_name", "correlation", "correlation_abs", "row_count_used")
        )
    review_frame = frame.loc[:, list(numeric_feature_columns)].copy()
    usable_columns = [
        column_name
        for column_name in review_frame.columns
        if review_frame[column_name].dropna().nunique(dropna=True) > 1
    ]
    if len(usable_columns) < 2:
        return pd.DataFrame(
            columns=("left_column_name", "right_column_name", "correlation", "correlation_abs", "row_count_used")
        )
    corr = review_frame.loc[:, usable_columns].corr(method="pearson", min_periods=3)
    rows: list[dict[str, object]] = []
    for left_index, left_column in enumerate(usable_columns):
        for right_column in usable_columns[left_index + 1 :]:
            correlation = corr.loc[left_column, right_column]
            if pd.isna(correlation) or abs(float(correlation)) < CORRELATION_REVIEW_THRESHOLD:
                continue
            pair_rows = int(
                review_frame.loc[:, [left_column, right_column]].dropna().shape[0]
            )
            rows.append(
                {
                    "left_column_name": left_column,
                    "right_column_name": right_column,
                    "correlation": float(correlation),
                    "correlation_abs": abs(float(correlation)),
                    "row_count_used": pair_rows,
                }
            )
    result = pd.DataFrame(
        rows,
        columns=("left_column_name", "right_column_name", "correlation", "correlation_abs", "row_count_used"),
    )
    if result.empty:
        return result
    return result.sort_values(["correlation_abs", "left_column_name", "right_column_name"], ascending=[False, True, True]).reset_index(drop=True)


def _build_column_audit(
    *,
    original_frame: pd.DataFrame,
    cleaned_frame: pd.DataFrame,
    target_columns: Sequence[str],
    leakage_review: pd.DataFrame,
    mixed_type_table: pd.DataFrame,
    duplicate_name_counts: pd.Series,
    duplicate_to_kept: dict[str, str],
    selected_candidate_feature_columns: Sequence[str],
    final_feature_columns: Sequence[str],
    removal_reason_by_column: dict[str, str],
    removal_detail_by_column: dict[str, str],
) -> pd.DataFrame:
    leakage_by_column = {
        str(row.column_name): (str(row.classification), str(row.reason))
        for row in leakage_review.itertuples(index=False)
    }
    model_input_ordinal_by_column = {
        str(column_name): index + 1
        for index, column_name in enumerate(final_feature_columns)
    }
    mixed_type_by_column = {
        str(row.column_name): row
        for row in mixed_type_table.itertuples(index=False)
    }
    duplicate_group_sizes: dict[str, int] = {}
    for duplicate_column, kept_column in duplicate_to_kept.items():
        duplicate_group_sizes[kept_column] = duplicate_group_sizes.get(kept_column, 1) + 1
        duplicate_group_sizes[duplicate_column] = duplicate_group_sizes.get(kept_column, 1)

    rows: list[dict[str, object]] = []
    candidate_feature_set = set(selected_candidate_feature_columns)
    final_feature_set = set(final_feature_columns)
    target_set = set(target_columns)
    for column_name in original_frame.columns:
        column_name = str(column_name)
        source_series = original_frame[column_name]
        cleaned_series = cleaned_frame[column_name]
        null_count = int(cleaned_series.isna().sum())
        null_rate = float(null_count / max(len(cleaned_series.index), 1))
        non_null = cleaned_series.dropna()
        unique_count = int(non_null.nunique(dropna=True))
        dominant_value = ""
        dominant_share = 0.0
        if not non_null.empty:
            counts = non_null.astype(str).value_counts(dropna=True)
            dominant_value = str(counts.index[0])[:256]
            dominant_share = float(counts.iloc[0] / max(int(non_null.shape[0]), 1))
        removal_reason = removal_reason_by_column.get(column_name, "")
        removal_detail = removal_detail_by_column.get(column_name, "")
        leakage = leakage_by_column.get(column_name)
        mixed_type = mixed_type_by_column.get(column_name)
        range_issue = _range_issue_for_column(column_name, cleaned_series)
        if column_name in final_feature_set or column_name in candidate_feature_set or column_name.startswith(ENGINEERED_FEATURE_PREFIX):
            column_role = "feature"
        elif column_name in target_set:
            column_role = "target"
        elif leakage is not None:
            column_role = "leakage_risk"
        else:
            column_role = "metadata"
        rows.append(
            {
                "column_name": column_name,
                "column_role": column_role,
                "source_dtype": str(source_series.dtype),
                "cleaned_dtype": str(cleaned_series.dtype),
                "selected_for_model_flag": column_name in candidate_feature_set,
                "included_in_clean_model_flag": column_name in final_feature_set,
                "model_input_ordinal": int(model_input_ordinal_by_column.get(column_name, 0)),
                "removed_from_model_flag": bool(removal_reason),
                "removal_reason": removal_reason,
                "removal_detail": removal_detail,
                "duplicate_name_count": int(duplicate_name_counts.get(column_name, 1)),
                "duplicate_name_flag": int(duplicate_name_counts.get(column_name, 1)) > 1,
                "duplicate_content_flag": column_name in duplicate_to_kept or column_name in duplicate_group_sizes,
                "duplicate_content_kept_column_name": duplicate_to_kept.get(column_name, ""),
                "duplicate_content_group_size": int(duplicate_group_sizes.get(column_name, 1)),
                "constant_flag": unique_count <= 1,
                "near_constant_flag": unique_count > 1 and dominant_share >= NEAR_CONSTANT_DOMINANCE_THRESHOLD,
                "dominant_value": dominant_value,
                "dominant_share": round(dominant_share, 6),
                "null_count": null_count,
                "null_rate": round(null_rate, 6),
                "high_null_flag": null_rate >= HIGH_NULL_RATE_THRESHOLD,
                "mixed_type_flag": bool(mixed_type.mixed_type_flag) if mixed_type is not None else False,
                "mixed_type_numeric_like_count": int(mixed_type.numeric_like_count) if mixed_type is not None else 0,
                "mixed_type_nonnumeric_like_count": int(mixed_type.nonnumeric_like_count) if mixed_type is not None else 0,
                "mixed_type_sample_nonnumeric_values": str(mixed_type.sample_nonnumeric_values) if mixed_type is not None else "",
                "strict_numeric_key_flag": bool(mixed_type.strict_numeric_key_flag) if mixed_type is not None else column_name in STRICT_NUMERIC_KEY_COLUMNS,
                "leakage_risk_flag": leakage is not None,
                "leakage_classification": leakage[0] if leakage is not None else "",
                "leakage_reason": leakage[1] if leakage is not None else "",
                "impossible_or_unstable_range_flag": range_issue is not None,
                "impossible_or_unstable_range_detail": range_issue or "",
            }
        )
    return pd.DataFrame(rows)


def _range_issue_for_column(column_name: str, series: pd.Series) -> str | None:
    numeric = pd.to_numeric(series, errors="coerce")
    non_null = numeric.dropna()
    if non_null.empty:
        return None
    if column_name.endswith("_flag"):
        invalid = non_null.loc[~non_null.isin([0.0, 1.0])]
        if not invalid.empty:
            return "binary_flag_outside_zero_one"
    if column_name in {"discount_percent", "feature_discount_depth_pct"}:
        invalid = non_null.loc[(non_null < 0.0) | (non_null > 100.0)]
        if not invalid.empty:
            return "percentage_outside_zero_to_hundred"
    if column_name in BOUNDED_ZERO_ONE_COLUMNS:
        invalid = non_null.loc[(non_null < 0.0) | (non_null > 1.0)]
        if not invalid.empty:
            return "bounded_zero_one_outside_range"
    if np.isinf(non_null.to_numpy(dtype=float)).any():
        return "infinite_numeric_values"
    return None


def _build_summary_payload(
    *,
    source_frame: pd.DataFrame,
    cleaned_model_input: pd.DataFrame,
    target_columns: Sequence[str],
    metadata_columns: Sequence[str],
    leakage_risk_columns: Sequence[str],
    normalized_text_columns: Sequence[str],
    column_audit: pd.DataFrame,
    correlation_review: pd.DataFrame,
    mixed_type_key_columns: Sequence[str],
) -> dict[str, object]:
    removed_rows = column_audit.loc[
        column_audit["removed_from_model_flag"].astype(bool),
        ["column_name", "removal_reason", "removal_detail"],
    ]
    review_only_probability_columns = set(PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS)
    review_only_basket_columns = set(BASKET_REVIEW_ONLY_FEATURE_COLUMNS)
    review_only_engineered_columns = _review_only_engineered_feature_columns()
    removal_reasons: dict[str, list[str]] = {}
    for row in removed_rows.itertuples(index=False):
        removal_reasons.setdefault(str(row.removal_reason), []).append(str(row.column_name))
    payload: dict[str, object] = {
        "source_row_count": int(len(source_frame.index)),
        "source_column_count": int(len(source_frame.columns)),
        "clean_model_row_count": int(len(cleaned_model_input.index)),
        "feature_count": int(cleaned_model_input.shape[1]),
        "target_count": int(len(target_columns)),
        "metadata_count": int(len(metadata_columns)),
        "leakage_risk_count": int(len(leakage_risk_columns)),
        "normalized_text_column_count": int(len(normalized_text_columns)),
        "duplicate_name_column_count": int(column_audit["duplicate_name_flag"].astype(bool).sum()),
        "duplicate_content_column_count": int(column_audit["duplicate_content_flag"].astype(bool).sum()),
        "removed_feature_column_count": int(removed_rows.shape[0]),
        "constant_feature_column_count": int(column_audit["constant_flag"].astype(bool).sum()),
        "near_constant_column_count": int(column_audit["near_constant_flag"].astype(bool).sum()),
        "high_null_column_count": int(column_audit["high_null_flag"].astype(bool).sum()),
        "mixed_type_column_count": int(column_audit["mixed_type_flag"].astype(bool).sum()),
        "mixed_type_key_columns": list(mixed_type_key_columns),
        "impossible_or_unstable_range_column_count": int(
            column_audit["impossible_or_unstable_range_flag"].astype(bool).sum()
        ),
        "correlation_review_pair_count": int(len(correlation_review.index)),
        "removed_feature_columns_by_reason": removal_reasons,
        "review_only_probability_columns_removed": [
            str(column_name)
            for column_name in removed_rows["column_name"].astype(str).tolist()
            if str(column_name) in review_only_probability_columns
        ],
        "review_only_basket_columns_removed": [
            str(column_name)
            for column_name in removed_rows["column_name"].astype(str).tolist()
            if str(column_name) in review_only_basket_columns
        ],
        "review_only_engineered_columns_removed": [
            str(column_name)
            for column_name in removed_rows["column_name"].astype(str).tolist()
            if str(column_name) in review_only_engineered_columns
        ],
        "feature_columns": [str(column_name) for column_name in cleaned_model_input.columns],
        "target_columns": [str(column_name) for column_name in target_columns],
        "metadata_columns": [str(column_name) for column_name in metadata_columns],
        "leakage_risk_columns": [str(column_name) for column_name in leakage_risk_columns],
    }
    return payload


def _summary_value_to_text(value: object) -> str:
    if isinstance(value, (list, tuple, dict)):
        return str(value)
    return str(value)