from __future__ import annotations

"""Store-facing promotions prediction download surface."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import time
from pathlib import Path
import re

import numpy as np
import pandas as pd

from runtime.promotions.config import PromotionArtifactPaths
from models.promotions.allocation_demand_forecast_contract import (
    build_demand_forecast_contract_frame,
    build_demand_forecast_validation_summary_frame,
    log_demand_forecast_validation,
    sync_demand_forecast_aliases,
    validate_demand_forecast_contract_frame,
)
from models.promotions.order_policy_adjustments import build_order_policy_adjustments
from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (
    build_live_order_decision_diagnostics,
)
from surfaces.promotions.reporting.allocation_stock_contract import (
    HARD_ORDER_BLOCKER_CODES,
    apply_allocation_order_blockers,
    build_allocation_stock_contract_frame,
    compose_contract_audit_notes,
    log_allocation_contract_validation,
    reconcile_priority_and_operator_action,
    sync_allocation_contract_aliases,
    validate_allocation_stock_contract_frame,
)
from surfaces.promotions.reporting.demand_evidence_classifier import (
    DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE,
    DEMAND_EVIDENCE_CLASS_COLD_START,
    DEMAND_EVIDENCE_CLASS_LOW_NONZERO,
    DEMAND_EVIDENCE_CLASS_TRUE_ZERO,
    classify_demand_evidence_row,
)


DEFAULT_BASE_STOCK_MIN_UNITS = 2.0
BASE_STOCK_DAYS_COVER = 7.0
CURRENT_STOCK_COVER_DAYS_CAP = 365.0
LOW_CONFIDENCE_THRESHOLD = 0.45
FORECAST_COLLAPSE_MODAL_SHARE_THRESHOLD = 0.98
FORECAST_COLLAPSE_MIN_ROWS = 50
FORECAST_ZERO_FIRST7_SHARE_THRESHOLD = 0.35
FORECAST_FLAT_PROMOTION_MODAL_SHARE_THRESHOLD = 0.90
FORECAST_FLAT_PROMOTION_MIN_ROWS = 12
EXTREME_STOCK_COVER_DAYS_THRESHOLD = 120.0
LOW_NONZERO_DEMAND_MAX_UNITS = 1.0
ROW_SIGNAL_OVERRIDE_RATIO_THRESHOLD = 2.5
ROW_SIGNAL_OVERRIDE_ABSOLUTE_MIN_UNITS = 1.0
ZERO_FORECAST_RAW_NEAR_ZERO_MAX_UNITS = 0.05
ZERO_FORECAST_NEGLIGIBLE_BASELINE_DAILY_UNITS = 0.02
ZERO_FORECAST_LOW_BASELINE_DAILY_UNITS = 0.20
ZERO_FORECAST_REPEATED_NON_RESPONSE_MIN_COUNT = 2
ZERO_FORECAST_NO_RESPONSE_LIFT_MAX = 0.05

FORECAST_ZERO_DEMAND_TRUE = "TRUE_ZERO_DEMAND"
FORECAST_ZERO_DEMAND_LOW_NONZERO = "LOW_NONZERO_DEMAND"
FORECAST_ZERO_DEMAND_COLLAPSED = "COLLAPSED_FORECAST_REQUIRES_REVIEW"
FORECAST_ZERO_DEMAND_COHORT_FLAT = "COHORT_SOURCE_TOO_FLAT"
FORECAST_ZERO_DEMAND_ROUNDING = "ROUNDING_TO_ZERO_ARTIFACT"
FORECAST_ZERO_DEMAND_HEALTHY = "HEALTHY_NONZERO_DEMAND"
FORECAST_REPAIR_REASON_ACTIONABLE_OVERRIDE = "actionable_override_applied"
FORECAST_REPAIR_REASON_ROUNDING_LOSS = "rounding_loss_repaired"
FORECAST_REPAIR_REJECTED_ALL_DEGENERATE = "all_sources_degenerate_or_zero"
FORECAST_REPAIR_REJECTED_NOT_MATERIAL = "row_signal_not_materially_stronger"
FORECAST_REPAIR_REJECTED_HONEST_ZERO = "honest_zero_preserved"
FORECAST_REPAIR_REJECTED_LOW_NONZERO = "low_nonzero_preserved"
FORECAST_REPAIR_REJECTED_COHORT_FLAT = "cohort_source_too_flat_without_safe_override"
FIRST7_FALLBACK_REPAIR_REASON = "prorated_positive_total_when_first7_features_zero_or_missing"
FIRST7_FALLBACK_SUPPRESSED_BY_LAUNCH_CAP = "launch_cap_suppressed_prorated_first7"
FORECAST_BENIGN_ZERO_CLASSES = frozenset(
    {
        FORECAST_ZERO_DEMAND_TRUE,
        FORECAST_ZERO_DEMAND_LOW_NONZERO,
    }
)
FORECAST_UNRESOLVED_COLLAPSE_CLASSES = frozenset(
    {
        FORECAST_ZERO_DEMAND_COLLAPSED,
        FORECAST_ZERO_DEMAND_COHORT_FLAT,
        FORECAST_ZERO_DEMAND_ROUNDING,
    }
)
_FORECAST_BLOCKING_UNRESOLVED_FLAT_CLASSES = frozenset(
    {
        FORECAST_ZERO_DEMAND_COLLAPSED,
        FORECAST_ZERO_DEMAND_ROUNDING,
    }
)

ACTION_ORDER = ("ORDER", "REVIEW", "HOLD", "DO_NOT_ORDER")
PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_DO_NOT_ORDER_LOW_INCREMENTAL_VALUE = (
    "excluded_legitimate_do_not_order_low_incremental_value"
)
PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_HOLD_INVENTORY_SUFFICIENT = (
    "excluded_legitimate_hold_inventory_sufficient"
)

# Commercial governance constants for the operator-facing CSV.
# - Pre-promo store-ordering demand is bounded to the next 56 days. This
#   protects the commercial recommendation from any upstream anchor mismatch
#   that would otherwise inflate `expected_units_before_promo_start` (e.g., a
#   prediction_date drift that produces a 599-day pre-promo window for a
#   promotion starting in late April).
# - Launch stock for any actionable row must not fall below 2 units on hand
#   on day one of the promotion. Rows explicitly marked DO_NOT_ORDER are
#   exempt because the commercial decision is to walk away from the SKU.
STORE_PRE_PROMO_HORIZON_DAYS = 56
MIN_LAUNCH_STOCK_UNITS = 2

# Capital-at-risk model constants (transparent, bounded, documented).
# risk_factor = (1 - confidence_fraction) * evidence_factor * overstock_factor
# clipped to CAPITAL_AT_RISK_MIN_FACTOR..CAPITAL_AT_RISK_MAX_FACTOR.
# Higher risk_factor means a larger share of exposure is treated as at risk.
CAPITAL_AT_RISK_MIN_FACTOR = 0.05
CAPITAL_AT_RISK_MAX_FACTOR = 1.0
CAPITAL_AT_RISK_DEFAULT_CONFIDENCE = 0.5
CAPITAL_AT_RISK_FLOOR_DOLLARS = 1.0  # divisor floor for risk/reward ratio

# Risk-adjusted recommended_order_units multipliers.
# Goal: do not overbuy when confidence is weak or evidence is sparse.
ORDER_RISK_BASELINE_MULTIPLIER = 0.5
ORDER_RISK_CONFIDENCE_WEIGHT = 0.5
ORDER_EVIDENCE_PENALTY_SPARSE = 0.7
ORDER_EVIDENCE_PENALTY_NO_EVIDENCE = 0.5
ORDER_EVIDENCE_NO_EVIDENCE_CLASSES = (
    "evidence_supported_zero",
    "no_evidence_skip",
    "true_zero_demand",
)
ORDER_EVIDENCE_SPARSE_CLASSES = (
    "sparse_history",
    "insufficient_history",
    "cold_start",
)

# Store-facing OUTPUT contract: a simplified operator-facing decision sheet.
# The visible CSV exposes one governed decision hierarchy plus the minimum
# stock context needed to act. Internal order states, shadow-policy details,
# and rich diagnostics stay available only in audit or inspection siblings.
STORE_FACING_ROW_LEVEL_EVIDENCE_COLUMNS: tuple[str, ...] = ()

STORE_FACING_PROMOTION_LEVEL_DIAGNOSTIC_COLUMNS: tuple[str, ...] = ()

# ---- Operator OUTPUT contract, defined as ordered business-narrative blocks.
# The CSV reads left-to-right:
#   identification -> dates -> current stock -> demand forecast ->
#   selected quantile -> promo-start target -> order decision -> priority ->
#   explanation -> deprecated aliases (retained one release).
STORE_FACING_VISIBLE_IDENTITY_COLUMNS = (
    "store_number",
    "promotion_id",
    "promotion_name",
    "sku_number",
    "sku_description",
)

STORE_FACING_DATE_COLUMNS = (
    "model_run_date",
    "promotion_start_date",
    "promotion_end_date",
    "days_until_promo_start",
    "promo_window_days",
)

STORE_FACING_CURRENT_STOCK_COLUMNS = (
    "current_soh_at_model_run",
    "confirmed_inbound_units_before_promo_start",
)

# Governed demand-forecast contract — forecast block (sufficient-stock demand).
STORE_FACING_DEMAND_FORECAST_BLOCK = (
    "baseline_daily_units",
    "promo_uplift_factor",
    "pre_promo_demand_units",
    "promo_window_demand_units",
    "total_expected_demand_units",
    "stock_constraint_adjustment_units",
    "stock_constraint_flag",
    "demand_forecast_units_q50",
    "demand_forecast_units_q70",
    "demand_forecast_units_q85",
    "demand_forecast_units_q95",
)

# Governed demand-forecast contract — selected-quantile + provenance block.
STORE_FACING_SELECTED_DEMAND_BLOCK = (
    "selected_demand_quantile",
    "selected_demand_units",
    "demand_forecast_confidence",
    "demand_forecast_basis",
    "demand_forecast_reason_code",
    "demand_forecast_warning",
)

# Full demand-forecast column set (used for schema membership).
STORE_FACING_DEMAND_FORECAST_COLUMNS = (
    *STORE_FACING_DEMAND_FORECAST_BLOCK,
    *STORE_FACING_SELECTED_DEMAND_BLOCK,
)

STORE_FACING_PROMO_START_TARGET_COLUMNS = (
    "projected_soh_at_promo_start_before_order",
    "floor_units_required_at_promo_start",
    "target_soh_at_promo_start",
    "raw_stock_gap_units",
)

# `order_units` is the single operator-visible order quantity (the governed
# recommended_order_units value); recommended_order_units itself stays
# audit-only per the internal-order-state governance.
STORE_FACING_ORDER_DECISION_COLUMNS = (
    "recommended_order_units_before_pack_rounding",
    "order_units",
    "projected_soh_at_promo_start_after_order",
    "projected_soh_at_promo_end_after_order",
    "stock_position_status",
    "order_reason_code",
)

STORE_FACING_PRIORITY_COLUMNS = (
    "priority_rank",
    "priority_band",
)

STORE_FACING_EXPLANATION_COLUMNS = (
    "operator_decision",
    "operator_action",
    "reason_short",
    "risk_flag",
    "review_flag",
    "audit_notes",
)

# Deprecated aliases retained for one release for downstream compatibility.
STORE_FACING_DEPRECATED_ALIAS_COLUMNS = (
    "current_soh",
    "on_order_at_advice_time",
    "expected_units_before_promo_start",
    "projected_SOH_at_promo_start",
    "target_SOH_at_promo_start",
    "floor_units_required",
    "expected_promo_demand",
    "available_to_sell_before_floor",
    "projected_stock_gap_units",
    "discount_percent",
)

# Operator simplified-decision fields (used by governance checks).
STORE_FACING_SIMPLIFIED_OPERATOR_COLUMNS = (
    "operator_decision",
    "operator_action",
    "order_units",
    "reason_short",
    "risk_flag",
    "review_flag",
    "audit_notes",
)

# Retained-context union (schema membership for the canonical contract fields).
STORE_FACING_RETAINED_CONTEXT_COLUMNS = (
    *STORE_FACING_DATE_COLUMNS,
    *STORE_FACING_CURRENT_STOCK_COLUMNS,
    *STORE_FACING_DEMAND_FORECAST_COLUMNS,
    *STORE_FACING_PROMO_START_TARGET_COLUMNS,
    *STORE_FACING_ORDER_DECISION_COLUMNS,
    *STORE_FACING_DEPRECATED_ALIAS_COLUMNS,
)

STORE_FACING_SHADOW_POLICY_COLUMNS = (
    "shadow_policy_name",
    "shadow_policy_version",
    "shadow_policy_candidate_flag",
    "shadow_policy_segment",
    "shadow_policy_order_units",
    "shadow_policy_capital_at_risk",
    "shadow_policy_expected_reason",
    "shadow_policy_guardrail_status",
    "shadow_policy_blocker_reason",
    "shadow_policy_should_publish_flag",
    "shadow_policy_should_affect_final_order_flag",
)

STORE_FACING_INTERNAL_ORDER_STATE_COLUMNS = (
    "raw_model_order_units",
    "provisional_review_order_units",
    "final_store_order_units",
    "recommended_order_units",
    "raw_model_order_value",
    "provisional_review_order_value",
    "final_store_order_value",
    "recommended_order_value",
    "low_soh_policy_final_order_units",
    "low_soh_policy_shadow_order_units",
    "shadow_policy_order_units",
)

STORE_FACING_OUTPUT_COLUMNS = (
    *STORE_FACING_VISIBLE_IDENTITY_COLUMNS,
    *STORE_FACING_DATE_COLUMNS,
    *STORE_FACING_CURRENT_STOCK_COLUMNS,
    *STORE_FACING_DEMAND_FORECAST_BLOCK,
    *STORE_FACING_SELECTED_DEMAND_BLOCK,
    *STORE_FACING_PROMO_START_TARGET_COLUMNS,
    *STORE_FACING_ORDER_DECISION_COLUMNS,
    *STORE_FACING_PRIORITY_COLUMNS,
    *STORE_FACING_EXPLANATION_COLUMNS,
    *STORE_FACING_DEPRECATED_ALIAS_COLUMNS,
)

# Full intermediate schema retained for internal consumers (manager summary,
# audit builder, sort logic). Anything not in STORE_FACING_OUTPUT_COLUMNS is
# treated as diagnostic-only and is dropped before writing the per-promotion
# CSV. This keeps governance, sort logic, and downstream code stable while
# the operator-facing surface stays clean and commercial.
STORE_FACING_SCHEMA_COLUMNS = (
    # Action-critical block (sort + scan-and-act header)
    "priority_rank",
    "priority_band",
    "sku_number",
    "sku_description",
    "operator_decision",
    "operator_action",
    "order_units",
    "reason_short",
    "risk_flag",
    "review_flag",
    "audit_notes",
    "store_action_label",
    "store_action_label_v2",
    "store_action_reason",
    "store_action",
    "operator_status",
    "recommended_action",
    "execution_readiness_status",
    "demand_evidence_label",
    "availability_risk_label",
    "capital_drag_label",
    "primary_review_reason",
    "blocker_reason",
    "human_review_required_flag",
    "low_nonzero_value_relief_delta",
    "raw_model_order_units",
    "provisional_review_order_units",
    "final_store_order_units",
    "raw_model_order_value",
    "provisional_review_order_value",
    "final_store_order_value",
    "low_soh_policy_version",
    "low_soh_policy_candidate_flag",
    "low_soh_policy_production_eligible_flag",
    "low_soh_policy_final_order_units",
    "low_soh_policy_shadow_order_units",
    "low_soh_policy_capital_at_risk",
    "low_soh_policy_reason",
    "low_soh_policy_guardrail_status",
    "low_soh_policy_blocker_reason",
    "low_soh_policy_decision_source",
    "shadow_policy_name",
    "shadow_policy_version",
    "shadow_policy_candidate_flag",
    "shadow_policy_segment",
    "shadow_policy_order_units",
    "shadow_policy_capital_at_risk",
    "shadow_policy_expected_reason",
    "shadow_policy_guardrail_status",
    "shadow_policy_blocker_reason",
    "shadow_policy_should_publish_flag",
    "shadow_policy_should_affect_final_order_flag",
    "order_reconciliation_status",
    "order_reconciliation_reason",
    "decision_reason",
    "recommended_order_units",
    "model_confidence_percent",
    "capital_at_risk_adjusted_dollars",
    "retail_risk_reward_ratio",
    "discount_percent",
    "stockout_probability_percent",
    "projected_on_hand_at_promo_start",
    "minimum_launch_stock_units",
    "floor_units_required",
    "current_soh",
    "promo_allocated_units",
    "expected_promo_demand",
    "available_to_sell_before_floor",
    "target_stock_day_one_units",
    "projected_stock_gap_units",
    "days_to_promo_start",
    "prediction_date",
    "lead_up_demand_units",
    "expected_units_before_promo_start",
    "expected_units_first_7_days",
    "promotion_period_days",
    "expected_units_per_period",
    "expected_units_per_day",
    "projected_promotional_units",
    "expected_units_total_promo",
    "order_timing_summary",
    "forecast_trust_summary",
    "model_reason_summary",
    # Identity
    "store_number",
    "promotion_id",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    # Action support (diagnostic; not in OUTPUT contract)
    "minimum_safe_stock_day_one_units",
    "lead_days_to_promo_start",
    "days_until_action",
    "buy_now_flag",
    "watch_flag",
    "do_not_buy_flag",
    # Current stock position
    "current_soh_units",
    "on_order_units",
    "effective_available_units",
    "gap_to_day_one_target_units",
    # Reasoning / trust
    "demand_evidence_class",
    "confidence_band",
    "historical_promo_response_summary",
    "historical_units_same_discount_avg",
    "historical_units_same_or_better_discount_avg",
    "historical_promo_events_same_discount",
    "historical_promo_events_same_or_better_discount",
    "discount_response_summary",
    "forecast_trust_band",
    "promotion_backtest_within_10pct_flag",
    "promotion_backtest_mean_absolute_pct_error",
    "promotion_backtest_bias_class",
    "promotion_backtest_comparable_event_count",
    # Risk / capital
    "stockout_risk_reason",
    "days_of_cover_to_promo_start",
    "days_of_cover_first_7_days",
    "projected_launch_cover_units",
    "stockout_risk_band",
    "overstock_risk_band",
    "estimated_leftover_units",
    "estimated_leftover_cost_dollars",
    "target_end_stock_units",
    "target_end_days_cover",
    "cashflow_runoff_status",
    "trust_floor_status",
    "units_needed_for_trust_floor",
    "units_needed_for_high_demand_cover",
    "units_above_trust_target",
    "capital_tied_above_trust_target",
    "expected_gp_on_trust_floor_units",
    "expected_gp_on_speculative_units",
    "risk_adjusted_value_of_speculative_units",
    "speculative_capital_above_floor_units",
    "speculative_capital_above_floor_value",
    # User-facing aliases / enriched operator fields
    "SOH_at_advice_time",
    "on_order_at_advice_time",
    "projected_SOH_at_promo_start",
    "target_SOH_at_promo_start",
    "recommended_order_value",
    "weeks_of_cover_entering_promo",
    "end_of_promo_residual_risk",
    "SKU_MAE",
    "SKU_MSE",
    "SKU_bias",
    # Validation flags
    "data_quality_flag",
    # Governed allocation stock contract canonical fields (also surfaced in OUTPUT)
    "model_run_date",
    "days_until_promo_start",
    "promo_window_days",
    "current_soh_at_model_run",
    "confirmed_inbound_units_before_promo_start",
    "expected_pre_promo_demand_units",
    "expected_promo_window_demand_units",
    "total_expected_demand_model_run_to_promo_end_units",
    "projected_soh_at_promo_start_before_order",
    "floor_units_required_at_promo_start",
    "target_soh_at_promo_start",
    "raw_stock_gap_units",
    "recommended_order_units_before_pack_rounding",
    "projected_soh_at_promo_start_after_order",
    "projected_soh_at_promo_end_after_order",
    "stock_position_status",
    "order_reason_code",
    # Governed demand forecast contract fields (also surfaced in OUTPUT)
    *STORE_FACING_DEMAND_FORECAST_COLUMNS,
)

STORE_FACING_INTEGER_COLUMNS = (
    "priority_rank",
    "order_units",
    "raw_model_order_units",
    "provisional_review_order_units",
    "final_store_order_units",
    "low_soh_policy_candidate_flag",
    "low_soh_policy_production_eligible_flag",
    "low_soh_policy_final_order_units",
    "recommended_order_units",
    "target_stock_day_one_units",
    "minimum_safe_stock_day_one_units",
    "minimum_launch_stock_units",
    "projected_on_hand_at_promo_start",
    "projected_stock_gap_units",
    "days_to_promo_start",
    "floor_units_required",
    "current_soh",
    "promo_allocated_units",
    "expected_promo_demand",
    "available_to_sell_before_floor",
    "expected_units_before_promo_start",
    "expected_units_first_7_days",
    "expected_units_total_promo",
    "lead_up_demand_units",
    "projected_promotional_units",
    "model_confidence_percent",
    "lead_days_to_promo_start",
    "days_until_action",
    "buy_now_flag",
    "watch_flag",
    "do_not_buy_flag",
    "human_review_required_flag",
    "current_soh_units",
    "on_order_units",
    "effective_available_units",
    "gap_to_day_one_target_units",
    "estimated_leftover_units",
    "historical_promo_events_same_discount",
    "historical_promo_events_same_or_better_discount",
    "promotion_backtest_within_10pct_flag",
    "promotion_backtest_comparable_event_count",
)

STORE_FACING_CURRENCY_COLUMNS = (
    "raw_model_order_value",
    "provisional_review_order_value",
    "final_store_order_value",
    "recommended_order_value",
    "estimated_leftover_cost_dollars",
    "capital_at_risk_adjusted_dollars",
    "speculative_capital_above_floor_value",
    "capital_tied_above_trust_target",
    "expected_gp_on_trust_floor_units",
    "expected_gp_on_speculative_units",
    "risk_adjusted_value_of_speculative_units",
)

STORE_FACING_RISK_BANDS = ("LOW", "MEDIUM", "HIGH")
STORE_FACING_CONFIDENCE_BANDS = ("UNKNOWN", "LOW", "MEDIUM", "HIGH")
STORE_FACING_DATA_QUALITY_FLAGS = (
    "OK",
    "REVIEW_FORECAST",
    "INSUFFICIENT_HISTORY",
    "COLLAPSED_FORECAST",
    "REVIEW_DISCOUNT_MISSING",
    "REVIEW_DISCOUNT_CONFLICT",
)
_DISCOUNT_REVIEW_REASON_BY_FLAG = {
    "REVIEW_DISCOUNT_MISSING": "review_discount_missing",
    "REVIEW_DISCOUNT_CONFLICT": "review_discount_conflict",
}
_DISCOUNT_REVIEW_DECISION_REASON_BY_FLAG = {
    "REVIEW_DISCOUNT_MISSING": "Review required: governed discount mapping is missing while price fields imply a discount.",
    "REVIEW_DISCOUNT_CONFLICT": "Review required: governed discount conflicts with price-derived discount.",
}
DISCOUNT_REPAIR_TOLERANCE_PCT_POINTS = 1.0
DISCOUNT_REVIEW_REASON_HARD_MISSING_PRICES = "HARD_DATA_FAILURE_MISSING_PRICE_FIELDS"
DISCOUNT_REVIEW_REASON_HARD_INVALID_NORMAL = "HARD_DATA_FAILURE_INVALID_NORMAL_PRICE"
DISCOUNT_REVIEW_REASON_HARD_INVALID_PROMO = "HARD_DATA_FAILURE_INVALID_PROMO_PRICE"
DISCOUNT_REVIEW_REASON_REPAIRABLE_PRICE_TRUTH = "REPAIRABLE_PRICE_TRUTH"
DISCOUNT_REVIEW_REASON_ROUNDING_TOLERANCE = "ROUNDING_TOLERANCE_REPAIR"
DISCOUNT_REVIEW_REASON_MAPPING_CONFLICT = "MAPPING_SOURCE_CONFLICT"
DISCOUNT_REVIEW_REASON_NO_DISCOUNT_VALID = "NO_DISCOUNT_BUT_PROMO_VALID"
DISCOUNT_REVIEW_REASON_NO_ISSUE = "NO_DISCOUNT_REVIEW_ISSUE"
STORE_FACING_PRIORITY_BANDS = ("BUY_NOW", "REVIEW", "WATCH", "HOLD", "DO_NOT_BUY")
STORE_ACTION_LABELS = (
    "BUY",
    "PROTECT_AVAILABILITY",
    "HOLD_STOCK",
    "HOLD_STOCK_FLOOR_SAFE",
    "LOW_SOH_NO_AUTO_BUY",
    "LOW_SOH_PROTECT_AVAILABILITY",
    "LOW_SOH_BORDERLINE_REVIEW",
    "REDUCE_HOLDING",
    "NO_DEMAND",
    "NEVER_SOLD_IN_PROMO",
    "NO_PRIOR_PROMO_EVIDENCE",
    "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK",
    "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW",
    "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
    "BORDERLINE_OOS_REVIEW",
    "DATA_QUALITY_REVIEW",
)
EXECUTABLE_STORE_ACTION_LABELS = frozenset({"BUY", "PROTECT_AVAILABILITY"})
PROVISIONAL_REVIEW_STORE_ACTION_LABELS = frozenset(
    {"BORDERLINE_OOS_REVIEW", "DATA_QUALITY_REVIEW"}
)
NON_EXECUTABLE_STORE_ACTION_LABELS = frozenset(
    {
        "HOLD_STOCK",
        "HOLD_STOCK_FLOOR_SAFE",
        "LOW_SOH_NO_AUTO_BUY",
        "LOW_SOH_PROTECT_AVAILABILITY",
        "LOW_SOH_BORDERLINE_REVIEW",
        "REDUCE_HOLDING",
        "NO_DEMAND",
        "NEVER_SOLD_IN_PROMO",
        "NO_PRIOR_PROMO_EVIDENCE",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW",
        "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
        *PROVISIONAL_REVIEW_STORE_ACTION_LABELS,
    }
)
MIN_EXECUTABLE_RETAIL_RISK_REWARD_RATIO = 1.0
LOW_SOH_POLICY_VERSION = "low_soh_protection_v1_20260611"
LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS = 3
LOW_SOH_POLICY_MAX_PACK_SIZE_AUTO_ORDER = 3
LOW_SOH_POLICY_MAX_UNIT_COST_AUTO_ORDER = 60.0
LOW_SOH_POLICY_VALIDATED_SEGMENT_MISSED_SALES_RISK_RATE = 0.5239
LOW_SOH_POLICY_VALIDATED_SEGMENT_SOURCE = "validated_low_soh_actual_outcome_shadow_20260611"
SHADOW_POLICY_NAME_SEGMENTED_PL_PROVED_ORDER_1 = "SEGMENTED_PL_PROVED_ORDER_1"
SHADOW_POLICY_VERSION_SEGMENTED_PL_PROVED_ORDER_1 = "SEGMENTED_PL_PROVED_ORDER_1_V1_SHADOW"
SEGMENTED_PL_PROVED_SHADOW_MIN_PROMO_ALLOCATED_UNITS = 6
SHADOW_POLICY_SEGMENT_PL_PROVED_DEMAND_BUT_OVERBOUGHT = "PL_PROVED_DEMAND_BUT_OVERBOUGHT"
SHADOW_POLICY_GUARDRAIL_PASS = "PASS_SHADOW_ONLY"
SHADOW_POLICY_GUARDRAIL_BLOCKED = "BLOCKED"
LOW_SOH_POLICY_ELIGIBLE_LABELS = frozenset(
    {
        "HOLD_STOCK",
        "HOLD_STOCK_FLOOR_SAFE",
        "LOW_SOH_NO_AUTO_BUY",
        "LOW_SOH_PROTECT_AVAILABILITY",
        "LOW_SOH_BORDERLINE_REVIEW",
        "NO_DEMAND",
        "NEVER_SOLD_IN_PROMO",
        "NO_PRIOR_PROMO_EVIDENCE",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW",
        "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
        "BORDERLINE_OOS_REVIEW",
    }
)
ORDER_RECONCILIATION_STATUS_EXECUTABLE_BUY = "EXECUTABLE_BUY"
ORDER_RECONCILIATION_STATUS_EXECUTABLE_PROTECT = "EXECUTABLE_PROTECT_AVAILABILITY"
ORDER_RECONCILIATION_STATUS_CAPPED_TO_AVAILABILITY_NEED = "CAPPED_TO_AVAILABILITY_NEED"
ORDER_RECONCILIATION_STATUS_PROVISIONAL_REVIEW_ONLY = "PROVISIONAL_REVIEW_ONLY"
ORDER_RECONCILIATION_STATUS_SUPPRESSED_BY_LABEL_GOVERNANCE = "SUPPRESSED_BY_LABEL_GOVERNANCE"
SUPPRESSION_RISK_SAFE_STOCK_COVERS_DEMAND = "SAFE_SUPPRESSION_STOCK_COVERS_DEMAND"
SUPPRESSION_RISK_SAFE_NO_DEMAND = "SAFE_SUPPRESSION_NO_DEMAND"
SUPPRESSION_RISK_SAFE_CAPITAL_DRAG = "SAFE_SUPPRESSION_CAPITAL_DRAG"
SUPPRESSION_RISK_UNSAFE_FLOOR = "UNSAFE_SUPPRESSION_FLOOR_RISK"
SUPPRESSION_RISK_UNSAFE_ONLINE_AVAILABILITY = "UNSAFE_SUPPRESSION_ONLINE_AVAILABILITY_RISK"
SUPPRESSION_RISK_BORDERLINE_REVIEW = "BORDERLINE_SUPPRESSION_REVIEW"
SUPPRESSION_RISK_NOT_APPLICABLE = "NOT_APPLICABLE"
DYNAMIC_DEMAND_EVIDENCE_LABELS = frozenset({
    "CREDIBLE_PROMO_DEMAND",
    "LOW_NONZERO_DEMAND",
    "SPARSE_HISTORY",
})
WEAK_DEMAND_EVIDENCE_LABELS = frozenset({"NO_DEMAND", "NEVER_SOLD_IN_PROMO"})
HIGH_AVAILABILITY_RISK_LABELS = frozenset(
    {"ZERO_SOH_RISK", "BELOW_2_UNIT_FLOOR_RISK", "FLOOR_PROTECTION_NEEDED"}
)
STORE_FACING_BUY_NOW_LEAD_DAYS = 21
STORE_FACING_ORDER_TIMING_SUMMARIES = {
    "BUY_NOW": "Buy now for day-one cover",
    "REVIEW": "Manager review needed before action",
    "WATCH": "Watch until closer to promo",
    "HOLD": "Hold, stock already covers launch",
    "DO_NOT_BUY": "Do not buy, weak/no promo response evidence",
}

COMMERCIAL_SCHEMA_COLUMNS = (
    "store_number",
    "promotion_header_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "product_description",
    "current_soh_units",
    "qty_on_order_units",
    "promo_allocated_units",
    "predicted_units_until_promo_start",
    "predicted_units_first_7_days_of_promo",
    "predicted_units_total_promo",
    "promotion_period_days",
    "expected_units_per_period",
    "expected_units_per_day",
    "base_units_target",
    "target_end_stock_units",
    "target_end_days_cover",
    "cashflow_runoff_status",
    "trust_floor_status",
    "units_needed_for_trust_floor",
    "units_needed_for_high_demand_cover",
    "units_above_trust_target",
    "capital_tied_above_trust_target",
    "expected_gp_on_trust_floor_units",
    "expected_gp_on_speculative_units",
    "risk_adjusted_value_of_speculative_units",
    "speculative_capital_above_floor_units",
    "speculative_capital_above_floor_value",
    "promo_start_target_soh_units",
    "suggested_order_units",
    "expected_leftover_units_end_of_promo",
    "suggested_order_value",
    "stockout_risk_flag",
    "overstock_risk_flag",
    "capital_tied_up_risk_flag",
    "estimated_cash_risk_band",
    "demand_confidence_band",
    "execution_attention_flag",
    "forecast_quality_flag",
    "forecast_reliability_band",
    "demand_shape_flag",
    "promo_lift_expectation_flag",
    "demand_evidence_class",
    "cold_start_flag",
    "insufficient_history_flag",
    "publish_eligibility_reason",
    "review_reason",
    "promotion_effectiveness_signal",
    "decision_recommendation",
    "decision_reason",
    "client_reason",
    "operational_note",
    "final_decision_score",
    "final_confidence_score",
    "low_nonzero_value_relief_delta",
    "discount_percent",
    "normal_price",
    "promo_price",
    "feature_historical_promo_events_same_discount",
    "feature_historical_promo_events_same_or_better_discount",
    "feature_historical_units_same_discount_avg",
    "feature_historical_units_same_or_better_discount_avg",
    "feature_historical_discount_response_confidence",
    "feature_discount_band_response_avg",
    "feature_discount_band_event_count",
)

COMMERCIAL_UNIT_COLUMNS = (
    "current_soh_units",
    "qty_on_order_units",
    "promo_allocated_units",
    "predicted_units_until_promo_start",
    "predicted_units_first_7_days_of_promo",
    "predicted_units_total_promo",
    "base_units_target",
    "promo_start_target_soh_units",
    "suggested_order_units",
    "expected_leftover_units_end_of_promo",
)

COMMERCIAL_DECIMAL_COLUMNS = (
    "suggested_order_value",
    "final_decision_score",
    "final_confidence_score",
)

COMMERCIAL_STRING_LENGTH_LIMITS = {
    "store_number": 32,
    "promotion_header_key": 128,
    "promotion_name": 256,
    "promotion_start_date": 10,
    "promotion_end_date": 10,
    "sku_number": 64,
    "product_description": 256,
    "decision_recommendation": 32,
    "promotion_effectiveness_signal": 64,
    "estimated_cash_risk_band": 32,
    "demand_confidence_band": 32,
    "execution_attention_flag": 32,
    "forecast_quality_flag": 48,
    "forecast_reliability_band": 32,
    "demand_shape_flag": 48,
    "promo_lift_expectation_flag": 48,
    "demand_evidence_class": 64,
    "publish_eligibility_reason": 96,
    "review_reason": 128,
    "decision_reason": 512,
    "client_reason": 512,
    "operational_note": 512,
}


class PromotionStoreDownloadGroupingValidationError(ValueError):
    """Raised when store+promotion grouping would fragment promotion SKU sets."""


class PromotionStoreDownloadCommercialValidationError(ValueError):
    """Raised when commercial output violates client-safe contract rules."""


@dataclass(frozen=True)
class PromotionStorePredictionDownloadArtifacts:
    """Paths and summary metadata emitted by the Stage 11 download builder."""

    master_csv_path: str
    csv_path: str
    per_store_csv_paths: tuple[str, ...]
    per_store_promotion_csv_paths: tuple[str, ...]
    reconciliation_csv_path: str
    manifest_path: str
    manifest_csv_path: str
    row_count: int
    generated_file_count: int


@dataclass(frozen=True)
class _CommercialSanitizationResult:
    cleaned_frame: pd.DataFrame
    excluded_null_sku_rows: pd.DataFrame
    excluded_blank_product_description_rows: pd.DataFrame
    non_numeric_suggested_order_value_rows: pd.DataFrame
    duplicate_rows_diagnostics: pd.DataFrame
    unresolved_duplicate_rows: pd.DataFrame


def _prepare_feature_inspection_source_frame(
    frame: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Normalize the raw decision-surface frame for feature-inspection joins.

    Purpose:
        Preserve upstream ``feature_*`` and diagnostic columns for the
        per-promotion feature-inspection sibling without widening the governed
        commercial master CSV.

    Inputs:
        frame: optional raw decision-surface frame passed into Stage 11.

    Outputs:
        A copy of ``frame`` with stable join keys for store, promotion header,
        and SKU, or ``None`` when no source frame is available.

    Important assumptions:
        Promotion header identity must be derived with the same governed logic
        used elsewhere in the download builder.

    Failure behaviour:
        Returns ``None`` when ``frame`` is absent or empty.
    """

    if frame is None or frame.empty:
        return None
    source = frame.copy()
    source["store_number"] = _raw_series(source, ("store_number",)).astype(str)
    source["promotion_header_key"] = _build_promotion_header_key_series(
        promotion_id=_raw_series(source, ("promotion_id", "promotional_sku_id", "promotional_sku_id_key")),
        promotion_name=_text_series(source, ("promotion_name",)),
        promotion_start_date=_date_series(source, ("promotion_start_date_date", "promotion_start_date")),
        promotion_end_date=_date_series(source, ("promotional_end_date_date", "promotional_end_date")),
        promo_type=_text_series(source, ("promo_type",)),
    )
    source["sku_number"] = _raw_series(source, ("sku_number",)).astype(str)
    if "promotion_row_key" in source.columns:
        source["promotion_row_key"] = _raw_series(source, ("promotion_row_key",)).astype(str)
    return source


def _resolve_feature_inspection_row_key_frame(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Resolve one preferred raw promotion row key per surviving commercial row.

    Purpose:
        Preserve row-identity attribution for feature-inspection artifacts when
        the governed commercial frame has already collapsed duplicate
        store/promotion/SKU rows to a single surviving row.

    Inputs:
        frame: raw decision-surface rows for one store/promotion group.

    Outputs:
        One row per store/SKU pair with the preferred ``promotion_row_key``.

    Important assumptions:
        Preference order uses the same governing intuition as duplicate-row
        resolution: strongest confidence and decision score win first.

    Failure behaviour:
        Returns an empty frame when ``promotion_row_key`` is unavailable.
    """

    if frame.empty or "promotion_row_key" not in frame.columns:
        return pd.DataFrame(columns=["store_number", "sku_number", "promotion_row_key"])
    rank_columns = [
        column_name
        for column_name in (
            "final_confidence_score",
            "final_decision_score",
            "suggested_order_units",
            "predicted_units_total_promo",
            "predicted_units_sold",
        )
        if column_name in frame.columns
    ]
    resolved = frame.loc[:, ["store_number", "sku_number", "promotion_row_key", *rank_columns]].copy()
    resolved["store_number"] = resolved["store_number"].astype(str)
    resolved["sku_number"] = resolved["sku_number"].astype(str)
    resolved["promotion_row_key"] = resolved["promotion_row_key"].astype(str)
    for rank_column in rank_columns:
        resolved[rank_column] = pd.to_numeric(resolved[rank_column], errors="coerce").fillna(-1e12)
    if rank_columns:
        resolved = resolved.sort_values(
            by=["store_number", "sku_number", *rank_columns],
            ascending=[True, True, *([False] * len(rank_columns))],
            kind="mergesort",
        )
    return resolved.drop_duplicates(subset=["store_number", "sku_number"], keep="first")


def _merge_feature_inspection_on_store_sku(
    *,
    store_facing_group: pd.DataFrame,
    inspection_source_group: pd.DataFrame,
    upstream_feature_columns: list[str],
) -> pd.DataFrame:
    """Fallback merge for feature inspection when row identity is unavailable.

    Purpose:
        Join upstream inspection fields on the surviving store/SKU grain only
        when a stable raw ``promotion_row_key`` cannot be resolved.
    """

    merge_base = store_facing_group.copy()
    merge_base["_feature_join_store"] = merge_base["store_number"].astype(str)
    merge_base["_feature_join_sku"] = merge_base["sku_number"].astype(str)
    upstream_subset = inspection_source_group.loc[:, ["store_number", "sku_number", *upstream_feature_columns]].copy()
    upstream_subset["_feature_join_store"] = upstream_subset["store_number"].astype(str)
    upstream_subset["_feature_join_sku"] = upstream_subset["sku_number"].astype(str)
    upstream_subset = upstream_subset.drop(columns=["store_number", "sku_number"]).drop_duplicates(
        subset=["_feature_join_store", "_feature_join_sku"],
        keep="last",
    )
    return merge_base.merge(
        upstream_subset,
        on=["_feature_join_store", "_feature_join_sku"],
        how="left",
        sort=False,
    ).drop(columns=["_feature_join_store", "_feature_join_sku"])


class PromotionStorePredictionDownloadBuilder:
    """Write a store-friendly promotions prediction download to the NAS prediction root."""

    def write_report(
        self,
        *,
        run_id: str,
        as_of_date: str,
        decision_surface_frame: pd.DataFrame,
        artifact_paths: PromotionArtifactPaths,
        completed_backtest_summary_path: str | None = None,
        completed_backtest_rows_path: str | None = None,
    ) -> PromotionStorePredictionDownloadArtifacts:
        """Build, validate, and publish Stage 11 store-facing download artifacts."""
        completed_backtest_summary = _read_completed_backtest_summary(completed_backtest_summary_path)
        sku_backtest_summary = _build_sku_backtest_summary(_read_completed_backtest_rows(completed_backtest_rows_path))
        download_frame = self._build_download_frame(
            run_id=run_id,
            as_of_date=as_of_date,
            frame=decision_surface_frame,
        )
        forecast_per_row_diagnostics: pd.DataFrame | None = download_frame.attrs.pop(
            "forecast_per_row_diagnostics", None
        )
        # Remove DataFrame-valued attrs before sanitization to avoid pandas concat attrs-comparison error.
        download_frame.attrs.pop("forecast_resolution", None)
        sanitization = self._sanitize_commercial_frame(download_frame)
        download_frame = self._sort_download_frame(sanitization.cleaned_frame)
        forecast_health = self._forecast_health_summary(
            download_frame,
            forecast_per_row_diagnostics=forecast_per_row_diagnostics,
        )
        diagnostics_paths = self._write_commercial_diagnostics_artifacts(
            run_id=run_id,
            frame=download_frame,
            forecast_health=forecast_health,
            artifact_paths=artifact_paths,
            sanitization=sanitization,
            forecast_per_row_diagnostics=forecast_per_row_diagnostics,
        )
        if not sanitization.unresolved_duplicate_rows.empty:
            raise PromotionStoreDownloadCommercialValidationError(
                "duplicate store_number + promotion_header_key + sku_number rows detected with unresolved conflicts; "
                f"see {diagnostics_paths['duplicate_store_promotion_sku_rows_csv_path']}"
            )
        self._validate_commercial_contract(download_frame, forecast_health=forecast_health)
        bundle_root = artifact_paths.store_prediction_download_run_root(run_id)
        bundle_root.mkdir(parents=True, exist_ok=True)

        master_csv_path = artifact_paths.store_prediction_download_path(
            run_id,
            as_of_date=as_of_date,
        )
        master_csv_path.parent.mkdir(parents=True, exist_ok=True)
        download_frame.to_csv(master_csv_path, index=False)

        generated_file_rows: list[dict[str, object]] = []
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="master",
                file_path=str(master_csv_path),
                frame=download_frame,
            )
        )

        diagnostic_summary = self._promotion_group_diagnostic_summary(download_frame)
        self._validate_store_promotion_grouping(
            frame=download_frame,
            diagnostic_summary=diagnostic_summary,
            artifact_paths=artifact_paths,
            run_id=run_id,
        )

        per_store_paths = self._write_per_store_csvs(
            run_id=run_id,
            as_of_date=as_of_date,
            frame=download_frame,
            artifact_paths=artifact_paths,
            generated_file_rows=generated_file_rows,
            forecast_per_row_diagnostics=forecast_per_row_diagnostics,
            completed_backtest_summary=completed_backtest_summary,
            sku_backtest_summary=sku_backtest_summary,
        )
        per_store_promotion_paths = self._write_per_store_promotion_csvs(
            run_id=run_id,
            as_of_date=as_of_date,
            frame=download_frame,
            artifact_paths=artifact_paths,
            generated_file_rows=generated_file_rows,
            feature_inspection_source_frame=decision_surface_frame,
            forecast_per_row_diagnostics=forecast_per_row_diagnostics,
            completed_backtest_summary=completed_backtest_summary,
            sku_backtest_summary=sku_backtest_summary,
        )
        store_facing_projection_frame = self._store_facing_projection(
            download_frame,
            forecast_per_row_diagnostics=forecast_per_row_diagnostics,
            as_of_date=as_of_date,
            completed_backtest_summary=completed_backtest_summary,
            sku_backtest_summary=sku_backtest_summary,
        )
        allocation_validation_summary_path = (
            artifact_paths.store_prediction_diagnostics_root(run_id)
            / "allocation_contract_validation_summary.csv"
        )
        allocation_validation_summary_path.parent.mkdir(parents=True, exist_ok=True)
        validation_summary_payload = store_facing_projection_frame.attrs.get(
            "allocation_contract_validation_summary"
        )
        if validation_summary_payload:
            allocation_validation_summary_frame = pd.DataFrame([validation_summary_payload])
            allocation_validation_summary_frame.to_csv(allocation_validation_summary_path, index=False)
            generated_file_rows.append(
                _build_file_manifest_row(
                    run_id=run_id,
                    as_of_date=as_of_date,
                    file_type="allocation_contract_validation_summary",
                    file_path=str(allocation_validation_summary_path),
                    frame=allocation_validation_summary_frame,
                )
            )
            diagnostics_paths["allocation_contract_validation_summary_csv_path"] = str(
                allocation_validation_summary_path
            )
        demand_forecast_validation_summary_path = (
            artifact_paths.store_prediction_diagnostics_root(run_id)
            / "demand_forecast_contract_validation_summary.csv"
        )
        demand_forecast_validation_summary_path.parent.mkdir(parents=True, exist_ok=True)
        demand_forecast_summary_payload = store_facing_projection_frame.attrs.get(
            "demand_forecast_contract_validation_summary"
        )
        if demand_forecast_summary_payload:
            demand_forecast_validation_summary_frame = pd.DataFrame([demand_forecast_summary_payload])
            demand_forecast_validation_summary_frame.to_csv(
                demand_forecast_validation_summary_path, index=False
            )
            generated_file_rows.append(
                _build_file_manifest_row(
                    run_id=run_id,
                    as_of_date=as_of_date,
                    file_type="demand_forecast_contract_validation_summary",
                    file_path=str(demand_forecast_validation_summary_path),
                    frame=demand_forecast_validation_summary_frame,
                )
            )
            diagnostics_paths["demand_forecast_contract_validation_summary_csv_path"] = str(
                demand_forecast_validation_summary_path
            )
        store_facing_output_frame = _project_store_facing_output_columns(store_facing_projection_frame)
        label_distribution_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_action_label_distribution.csv"
        label_distribution_path.parent.mkdir(parents=True, exist_ok=True)
        label_distribution_frame = _build_store_action_label_distribution_frame(store_facing_projection_frame)
        label_distribution_frame.to_csv(label_distribution_path, index=False)
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_action_label_distribution",
                file_path=str(label_distribution_path),
                frame=label_distribution_frame,
            )
        )
        diagnostics_paths["store_action_label_distribution_csv_path"] = str(label_distribution_path)
        cleanup_issues_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_facing_contract_cleanup_issues.csv"
        cleanup_summary_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_facing_contract_cleanup_summary.csv"
        cleanup_issue_frame = _build_store_facing_contract_cleanup_issues_frame(
            operator_output_frame=store_facing_output_frame,
        )
        cleanup_summary_frame = _build_store_facing_contract_cleanup_summary_frame(
            issue_frame=cleanup_issue_frame,
            total_row_count=int(len(store_facing_output_frame.index)),
        )
        cleanup_issue_frame.to_csv(cleanup_issues_path, index=False)
        cleanup_summary_frame.to_csv(cleanup_summary_path, index=False)
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_facing_contract_cleanup_issues",
                file_path=str(cleanup_issues_path),
                frame=cleanup_issue_frame,
            )
        )
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_facing_contract_cleanup_summary",
                file_path=str(cleanup_summary_path),
                frame=cleanup_summary_frame,
            )
        )
        diagnostics_paths["store_facing_contract_cleanup_issues_csv_path"] = str(cleanup_issues_path)
        diagnostics_paths["store_facing_contract_cleanup_summary_csv_path"] = str(cleanup_summary_path)
        order_reconciliation_diagnostic_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_order_reconciliation_diagnostic.csv"
        order_reconciliation_summary_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_order_reconciliation_summary.csv"
        order_reconciliation_diagnostic = _build_store_order_reconciliation_diagnostic_frame(
            store_facing_frame=store_facing_projection_frame,
        )
        order_reconciliation_summary = _build_store_order_reconciliation_summary_frame(
            store_facing_frame=store_facing_projection_frame,
        )
        order_reconciliation_diagnostic.to_csv(order_reconciliation_diagnostic_path, index=False)
        order_reconciliation_summary.to_csv(order_reconciliation_summary_path, index=False)
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_order_reconciliation_diagnostic",
                file_path=str(order_reconciliation_diagnostic_path),
                frame=order_reconciliation_diagnostic,
            )
        )
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_order_reconciliation_summary",
                file_path=str(order_reconciliation_summary_path),
                frame=order_reconciliation_summary,
            )
        )
        diagnostics_paths["store_order_reconciliation_diagnostic_csv_path"] = str(order_reconciliation_diagnostic_path)
        diagnostics_paths["store_order_reconciliation_summary_csv_path"] = str(order_reconciliation_summary_path)
        suppressed_order_risk_audit_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_suppressed_order_risk_audit.csv"
        suppressed_order_risk_summary_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_suppressed_order_risk_summary.csv"
        suppressed_order_risk_audit = _build_store_suppressed_order_risk_audit_frame(
            store_facing_frame=store_facing_projection_frame,
        )
        suppressed_order_risk_summary = _build_store_suppressed_order_risk_summary_frame(
            store_facing_frame=store_facing_projection_frame,
            audit_frame=suppressed_order_risk_audit,
        )
        suppressed_order_risk_audit.to_csv(suppressed_order_risk_audit_path, index=False)
        suppressed_order_risk_summary.to_csv(suppressed_order_risk_summary_path, index=False)
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_suppressed_order_risk_audit",
                file_path=str(suppressed_order_risk_audit_path),
                frame=suppressed_order_risk_audit,
            )
        )
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_suppressed_order_risk_summary",
                file_path=str(suppressed_order_risk_summary_path),
                frame=suppressed_order_risk_summary,
            )
        )
        diagnostics_paths["store_suppressed_order_risk_audit_csv_path"] = str(suppressed_order_risk_audit_path)
        diagnostics_paths["store_suppressed_order_risk_summary_csv_path"] = str(suppressed_order_risk_summary_path)
        _validate_store_suppressed_order_risk_audit(suppressed_order_risk_audit)
        data_quality_breakdown_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_data_quality_review_breakdown.csv"
        data_quality_reason_distribution_path = artifact_paths.store_prediction_diagnostics_root(run_id) / "store_data_quality_review_reason_distribution.csv"
        data_quality_breakdown = _build_store_data_quality_review_breakdown_frame(
            commercial_frame=download_frame,
            store_facing_frame=store_facing_projection_frame,
        )
        data_quality_reason_distribution = _build_store_data_quality_review_reason_distribution_frame(
            breakdown_frame=data_quality_breakdown,
            total_row_count=int(len(store_facing_projection_frame.index)),
        )
        data_quality_breakdown.to_csv(data_quality_breakdown_path, index=False)
        data_quality_reason_distribution.to_csv(data_quality_reason_distribution_path, index=False)
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_data_quality_review_breakdown",
                file_path=str(data_quality_breakdown_path),
                frame=data_quality_breakdown,
            )
        )
        generated_file_rows.append(
            _build_file_manifest_row(
                run_id=run_id,
                as_of_date=as_of_date,
                file_type="store_data_quality_review_reason_distribution",
                file_path=str(data_quality_reason_distribution_path),
                frame=data_quality_reason_distribution,
            )
        )
        diagnostics_paths["store_data_quality_review_breakdown_csv_path"] = str(data_quality_breakdown_path)
        diagnostics_paths["store_data_quality_review_reason_distribution_csv_path"] = str(data_quality_reason_distribution_path)
        diagnostics_csv_path, diagnostics_json_path, reconciliation_csv_path = self._write_grouping_reconciliation_outputs(
            run_id=run_id,
            as_of_date=as_of_date,
            decision_surface_frame=decision_surface_frame,
            download_frame=download_frame,
            diagnostic_summary=diagnostic_summary,
            artifact_paths=artifact_paths,
            generated_file_rows=generated_file_rows,
        )

        totals = self._build_totals(download_frame)
        manifest_path, manifest_csv_path = self._write_manifest_outputs(
            run_id=run_id,
            as_of_date=as_of_date,
            master_csv_path=str(master_csv_path),
            download_frame=download_frame,
            totals=totals,
            forecast_health=forecast_health,
            diagnostics_paths=diagnostics_paths,
            diagnostics_csv_path=str(diagnostics_csv_path),
            diagnostics_json_path=str(diagnostics_json_path),
            reconciliation_csv_path=str(reconciliation_csv_path),
            artifact_paths=artifact_paths,
            generated_file_rows=generated_file_rows,
        )

        return PromotionStorePredictionDownloadArtifacts(
            master_csv_path=str(master_csv_path),
            csv_path=str(_primary_store_facing_csv_path(
                per_store_promotion_paths=per_store_promotion_paths,
                per_store_paths=per_store_paths,
                fallback_path=master_csv_path,
            )),
            per_store_csv_paths=tuple(per_store_paths),
            per_store_promotion_csv_paths=tuple(per_store_promotion_paths),
            reconciliation_csv_path=str(reconciliation_csv_path),
            manifest_path=str(manifest_path),
            manifest_csv_path=str(manifest_csv_path),
            row_count=int(len(download_frame.index)),
            generated_file_count=int(len(generated_file_rows)),
        )

    def _write_grouping_reconciliation_outputs(
        self,
        *,
        run_id: str,
        as_of_date: str,
        decision_surface_frame: pd.DataFrame,
        download_frame: pd.DataFrame,
        diagnostic_summary: pd.DataFrame,
        artifact_paths: PromotionArtifactPaths,
        generated_file_rows: list[dict[str, object]],
    ) -> tuple[object, object, object]:
        """Write grouping diagnostics and source-vs-output reconciliation artifacts."""
        diagnostics_csv_path = artifact_paths.store_prediction_grouping_diagnostics_csv_path(run_id)
        diagnostics_json_path = artifact_paths.store_prediction_grouping_diagnostics_json_path(run_id)
        reconciliation_csv_path = artifact_paths.store_prediction_reconciliation_csv_path(run_id)
        diagnostics_csv_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostics_json_path.parent.mkdir(parents=True, exist_ok=True)
        reconciliation_csv_path.parent.mkdir(parents=True, exist_ok=True)

        diagnostic_summary.to_csv(diagnostics_csv_path, index=False)
        diagnostics_json_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "as_of_date": as_of_date,
                    "grouping_key_name": "promotion_header_key",
                    "grouping_key_source_columns": ["promotion_id", "promotion_name", "promotion_start_date", "promotion_end_date", "promo_type"],
                    "null_sku_row_count": int(download_frame["sku_number"].isna().sum()),
                    "row_count": int(len(diagnostic_summary.index)),
                    "rows": diagnostic_summary.to_dict(orient="records"),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        reconciliation_frame = self._build_reconciliation_frame(
            source_frame=decision_surface_frame,
            output_frame=download_frame,
        )
        reconciliation_frame.to_csv(reconciliation_csv_path, index=False)
        generated_file_rows.append(
            {
                "run_id": run_id,
                "as_of_date": as_of_date,
                "store_number": "",
                "promotion_header_key": "",
                "promotion_name": "",
                "promotion_start_date": "",
                "promotion_end_date": "",
                "file_type": "reconciliation",
                "file_path": str(reconciliation_csv_path),
                "row_count": int(len(reconciliation_frame.index)),
                "unique_sku_count": 0,
                "action_counts": "{}",
                "review_row_count": 0,
                "review_required_row_count": 0,
                "order_row_count": 0,
                "hold_row_count": 0,
                "do_not_order_row_count": 0,
                "created_at": _created_at_utc(),
            }
        )
        return diagnostics_csv_path, diagnostics_json_path, reconciliation_csv_path

    def _write_manifest_outputs(
        self,
        *,
        run_id: str,
        as_of_date: str,
        master_csv_path: str,
        download_frame: pd.DataFrame,
        totals: dict[str, int],
        forecast_health: dict[str, object],
        diagnostics_paths: dict[str, str],
        diagnostics_csv_path: str,
        diagnostics_json_path: str,
        reconciliation_csv_path: str,
        artifact_paths: PromotionArtifactPaths,
        generated_file_rows: list[dict[str, object]],
    ) -> tuple[object, object]:
        """Write manifest csv/json outputs and append manifest file rows."""
        manifest_path = artifact_paths.store_prediction_manifest_path(run_id)
        manifest_csv_path = artifact_paths.store_prediction_manifest_csv_path(run_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_csv_path.parent.mkdir(parents=True, exist_ok=True)

        manifest_csv_row = {
            "run_id": run_id,
            "as_of_date": as_of_date,
            "store_number": "",
            "promotion_row_key": "",
            "file_type": "manifest_csv",
            "file_path": str(manifest_csv_path),
            "row_count": int(len(generated_file_rows) + 2),
            "review_required_row_count": int(totals["review_required_row_count"]),
            "order_row_count": int(totals["order_row_count"]),
            "hold_row_count": int(totals["hold_row_count"]),
            "do_not_order_row_count": int(totals["do_not_order_row_count"]),
            "created_at": _created_at_utc(),
        }
        manifest_json_row = {
            **manifest_csv_row,
            "file_type": "manifest_json",
            "file_path": str(manifest_path),
        }
        generated_file_rows.extend((manifest_csv_row, manifest_json_row))

        manifest_frame = pd.DataFrame(generated_file_rows)
        manifest_frame.to_csv(manifest_csv_path, index=False)

        manifest_payload = {
            "run_id": run_id,
            "as_of_date": as_of_date,
            "row_count": int(len(download_frame.index)),
            "master_csv_path": str(master_csv_path),
            "manifest_csv_path": str(manifest_csv_path),
            "columns": list(download_frame.columns),
            "file_count": int(len(generated_file_rows)),
            "totals": totals,
            "diagnostics": {
                "forecast_health": forecast_health,
                "grouping_diagnostics_csv_path": str(diagnostics_csv_path),
                "grouping_diagnostics_json_path": str(diagnostics_json_path),
                "reconciliation_csv_path": str(reconciliation_csv_path),
                **diagnostics_paths,
            },
            "logic": {
                "row_grain": "one row per store_number + promotion_header_key + sku_number",
                "base_units_target": "max(2 units, 7 days of expected demand)",
                "promo_start_target_soh_units": "base_units_target + predicted_units_first_7_days_of_promo",
                "suggested_order_units": "max(0, promo_start_target_soh_units - max(current_soh_units + qty_on_order_units - predicted_units_until_promo_start, 0))",
                "actions": [*ACTION_ORDER],
            },
            "files": generated_file_rows,
        }
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest_path, manifest_csv_path

    def _build_download_frame(
        self,
        *,
        run_id: str,
        as_of_date: str,
        frame: pd.DataFrame,
    ) -> pd.DataFrame:
        """Assemble the canonical commercial Stage 11 frame from decision-surface inputs."""
        inputs = self._extract_download_input_series(frame=frame, as_of_date=as_of_date)
        raw_predicted_units_for_policy = _numeric_series(
            frame,
            ("raw_predicted_units_sold", "predicted_units_sold"),
        ).clip(lower=0.0)
        calibrated_predicted_units_for_policy = _numeric_series(
            frame,
            ("calibrated_predicted_units_sold", "predicted_units_sold"),
        ).clip(lower=0.0)
        order_decision_diagnostics = build_live_order_decision_diagnostics(
            frame,
            raw_predicted_units=raw_predicted_units_for_policy,
            predicted_units=calibrated_predicted_units_for_policy,
        )
        policy_adjustments = build_order_policy_adjustments(
            frame,
            raw_predicted_units=raw_predicted_units_for_policy,
            calibrated_predicted_units=calibrated_predicted_units_for_policy,
            diagnostics_frame=order_decision_diagnostics,
        )
        policy_fired_mask = pd.to_numeric(
            policy_adjustments["policy_adjustment_fired_flag"],
            errors="coerce",
        ).fillna(0.0).ge(1.0)
        forecast_outputs = self._build_download_forecast_outputs(
            frame=frame,
            promo_window_days=inputs["promo_window_days"],
            days_until_promo_start=inputs["days_until_promo_start"],
            promotion_header_key=inputs["promotion_header_key"],
            current_soh_raw=inputs["current_soh_raw"],
            on_order_qty_raw=inputs["on_order_qty_raw"],
            # Phase 3: order-policy total cap applies to orders only, not demand forecast display.
            policy_adjusted_total_cap_units=None,
            policy_adjusted_launch_cap_units=pd.to_numeric(
                policy_adjustments["adjusted_launch_units"],
                errors="coerce",
            ).where(policy_fired_mask),
        )

        calc_frame = pd.DataFrame(
            {
                "promotion_name": inputs["promotion_name"],
                "promo_type": inputs["promo_type"],
                "promotion_header_key": inputs["promotion_header_key"],
                "decision_recommendation": inputs["decision_recommendation"],
                "leftover_risk_penalty": inputs["leftover_risk_penalty"],
                "predicted_total": forecast_outputs["predicted_units_total_promo"],
                "predicted_until_start": forecast_outputs["predicted_units_until_promo_start"],
                "predicted_first_7": forecast_outputs["predicted_units_first_7_days_of_promo"],
                "base_units_target": forecast_outputs["base_units_target"],
                "promo_start_target": forecast_outputs["promo_start_target_soh_units"],
                "current_soh_units": forecast_outputs["current_soh_units"],
                "qty_on_order_units": forecast_outputs["qty_on_order_units"],
                "inventory_missing": (inputs["current_soh_raw"].isna() | inputs["on_order_qty_raw"].isna()).astype(bool),
                "final_confidence_score": inputs["final_confidence_score"],
                "promo_window_days": inputs["promo_window_days"],
                "unit_cost": inputs["unit_cost"],
                "forecast_flat_promotion_flag": forecast_outputs["forecast_resolution"]["forecast_flat_promotion_flag"],
                "forecast_zero_demand_classification": forecast_outputs["forecast_resolution"][
                    "forecast_zero_demand_classification"
                ],
                "forecast_collapse_requires_review_flag": forecast_outputs["forecast_resolution"][
                    "forecast_collapse_requires_review_flag"
                ],
                "forecast_unresolved_collapse_reason": forecast_outputs["forecast_resolution"][
                    "forecast_unresolved_collapse_reason"
                ],
                "raw_history_units": forecast_outputs["forecast_resolution"]["raw_history_units"],
                "raw_predicted_units_sold": forecast_outputs["forecast_resolution"]["raw_predicted_units_sold"],
                "raw_demand_reference_units": forecast_outputs["forecast_resolution"]["raw_demand_reference_units"],
                "raw_baseline_expected_units": forecast_outputs["forecast_resolution"]["raw_baseline_expected_units"],
                "discount_evidence_strength_score": _numeric_series(frame, ("feature_discount_evidence_strength_score",)).clip(lower=0.0, upper=1.0),
                "elasticity_confidence_score": _numeric_series(frame, ("feature_discount_elasticity_confidence_score",)).clip(lower=0.0, upper=1.0),
                "same_discount_history_available_flag": _numeric_series(frame, ("feature_same_discount_history_available_flag",)).clip(lower=0.0, upper=1.0),
                "launch_stock_support_score": _numeric_series(frame, ("feature_launch_stock_support_score",)).clip(lower=0.0, upper=1.0),
                "discount_support_signals_present": pd.Series(
                    float(
                        any(
                            column_name in frame.columns
                            for column_name in (
                                "feature_discount_evidence_strength_score",
                                "feature_discount_elasticity_confidence_score",
                                "feature_same_discount_history_available_flag",
                                "feature_launch_stock_support_score",
                            )
                        )
                    ),
                    index=frame.index,
                    dtype="float64",
                ),
                "window_blend_conflict_score": _numeric_series(
                    frame,
                    ("feature_total_window_pressure_vs_launch_support_conflict_score", "feature_window_blend_conflict_score"),
                ).clip(lower=0.0, upper=1.0),
                "uplift_order_confidence": _numeric_series(
                    frame,
                    ("feature_uplift_confidence_score", "feature_order_recommendation_confidence_from_uplift"),
                ).clip(lower=0.0, upper=1.0),
            }
        )
        decision_outputs = _derive_row_level_commercial_decisions(
            calc_frame=calc_frame,
            output_index=frame.index,
        )
        policy_review_mask = pd.to_numeric(
            policy_adjustments["review_override_flag"],
            errors="coerce",
        ).fillna(0.0).ge(1.0)
        policy_review_reason = policy_adjustments["review_override_reason"].fillna("").astype(str).str.strip()
        discount_review_flag = _discount_mapping_review_flag(frame).fillna("").astype(str).str.strip().str.upper()
        decision_outputs = _apply_discount_review_hold_to_decision_outputs(
            decision_outputs=decision_outputs,
            discount_review_flag=discount_review_flag,
        )
        pre_policy_action_upper = decision_outputs["decision_recommendation"].astype(str).str.strip().str.upper()
        projected_on_hand_at_promo_start = (
            pd.to_numeric(calc_frame["current_soh_units"], errors="coerce").fillna(0.0)
            + pd.to_numeric(calc_frame["qty_on_order_units"], errors="coerce").fillna(0.0)
            - pd.to_numeric(calc_frame["predicted_until_start"], errors="coerce").fillna(0.0)
        ).clip(lower=0.0)
        predicted_total_units = pd.to_numeric(calc_frame["predicted_total"], errors="coerce").fillna(0.0).clip(lower=0.0)
        promo_start_target_units = pd.to_numeric(calc_frame["promo_start_target"], errors="coerce").fillna(0.0).clip(lower=0.0)
        demand_evidence_class_lower = (
            decision_outputs["demand_evidence_class"].fillna("").astype(str).str.strip().str.lower()
        )
        de_minimis_policy_demand_mask = predicted_total_units.le(1.0) & demand_evidence_class_lower.isin(
            {
                DEMAND_EVIDENCE_CLASS_LOW_NONZERO,
                DEMAND_EVIDENCE_CLASS_TRUE_ZERO,
            }
        )
        inventory_covers_expected_demand_mask = projected_on_hand_at_promo_start.ge(predicted_total_units)
        inventory_covers_launch_target_mask = projected_on_hand_at_promo_start.ge(promo_start_target_units)
        non_discount_policy_order_mask = (
            policy_review_mask
            & pre_policy_action_upper.eq("ORDER")
            & ~discount_review_flag.str.startswith("REVIEW_DISCOUNT")
        )
        stock_gap_policy_do_not_order_mask = (
            non_discount_policy_order_mask
            & policy_review_reason.eq("policy_stock_gap_high")
            & de_minimis_policy_demand_mask
            & inventory_covers_expected_demand_mask
        )
        sparse_policy_hold_mask = (
            non_discount_policy_order_mask
            & policy_review_reason.eq("policy_sparse_history_multi_driver")
            & de_minimis_policy_demand_mask
            & inventory_covers_launch_target_mask
        )
        sparse_policy_do_not_order_mask = (
            non_discount_policy_order_mask
            & policy_review_reason.eq("policy_sparse_history_multi_driver")
            & de_minimis_policy_demand_mask
            & inventory_covers_expected_demand_mask
            & ~inventory_covers_launch_target_mask
        )
        inventory_low_value_hold_mask = (
            non_discount_policy_order_mask
            & policy_review_reason.eq("policy_inventory_sufficient_low_value_history")
            & inventory_covers_launch_target_mask
        )
        inventory_low_value_do_not_order_mask = (
            non_discount_policy_order_mask
            & policy_review_reason.eq("policy_inventory_sufficient_low_value_history")
            & inventory_covers_expected_demand_mask
            & ~inventory_covers_launch_target_mask
        )
        decision_outputs["decision_recommendation"] = decision_outputs["decision_recommendation"].where(
            ~stock_gap_policy_do_not_order_mask,
            "DO_NOT_ORDER",
        )
        decision_outputs["decision_reason"] = decision_outputs["decision_reason"].where(
            ~stock_gap_policy_do_not_order_mask,
            "Do not order: governed stock-gap policy plus de minimis expected demand does not justify a fresh buy.",
        )
        decision_outputs["client_reason"] = decision_outputs["client_reason"].where(
            ~stock_gap_policy_do_not_order_mask,
            "Promotional demand is too weak to justify a fresh order; use existing stock only.",
        )
        decision_outputs["operational_note"] = decision_outputs["operational_note"].where(
            ~stock_gap_policy_do_not_order_mask,
            "Action now: do not place a fresh order for this SKU unless local sell-through materially exceeds this weak-demand posture.",
        )
        decision_outputs["publish_eligibility_reason"] = decision_outputs["publish_eligibility_reason"].where(
            ~stock_gap_policy_do_not_order_mask,
            PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_DO_NOT_ORDER_LOW_INCREMENTAL_VALUE,
        )
        decision_outputs["review_reason"] = decision_outputs["review_reason"].where(
            ~stock_gap_policy_do_not_order_mask,
            "",
        )
        decision_outputs["decision_recommendation"] = decision_outputs["decision_recommendation"].where(
            ~sparse_policy_hold_mask,
            "HOLD",
        )
        decision_outputs["decision_reason"] = decision_outputs["decision_reason"].where(
            ~sparse_policy_hold_mask,
            "Hold: sparse-history policy blocks auto-buy and projected stock already covers the launch target.",
        )
        decision_outputs["client_reason"] = decision_outputs["client_reason"].where(
            ~sparse_policy_hold_mask,
            "Evidence is too weak to justify buying more stock, and current inventory already covers likely launch needs.",
        )
        decision_outputs["operational_note"] = decision_outputs["operational_note"].where(
            ~sparse_policy_hold_mask,
            "Action now: hold current stock and monitor early promo sell-through before considering any reorder.",
        )
        decision_outputs["publish_eligibility_reason"] = decision_outputs["publish_eligibility_reason"].where(
            ~sparse_policy_hold_mask,
            PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_HOLD_INVENTORY_SUFFICIENT,
        )
        decision_outputs["review_reason"] = decision_outputs["review_reason"].where(
            ~sparse_policy_hold_mask,
            "",
        )
        decision_outputs["decision_recommendation"] = decision_outputs["decision_recommendation"].where(
            ~sparse_policy_do_not_order_mask,
            "DO_NOT_ORDER",
        )
        decision_outputs["decision_reason"] = decision_outputs["decision_reason"].where(
            ~sparse_policy_do_not_order_mask,
            "Do not order: sparse-history policy blocks auto-buy and current stock already covers likely promotional demand.",
        )
        decision_outputs["client_reason"] = decision_outputs["client_reason"].where(
            ~sparse_policy_do_not_order_mask,
            "Evidence is too weak to justify a fresh buy; use existing stock first.",
        )
        decision_outputs["operational_note"] = decision_outputs["operational_note"].where(
            ~sparse_policy_do_not_order_mask,
            "Action now: do not place a fresh order unless local sell-through materially outperforms this weak-demand posture.",
        )
        decision_outputs["publish_eligibility_reason"] = decision_outputs["publish_eligibility_reason"].where(
            ~sparse_policy_do_not_order_mask,
            PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_DO_NOT_ORDER_LOW_INCREMENTAL_VALUE,
        )
        decision_outputs["review_reason"] = decision_outputs["review_reason"].where(
            ~sparse_policy_do_not_order_mask,
            "",
        )
        decision_outputs["decision_recommendation"] = decision_outputs["decision_recommendation"].where(
            ~inventory_low_value_hold_mask,
            "HOLD",
        )
        decision_outputs["decision_reason"] = decision_outputs["decision_reason"].where(
            ~inventory_low_value_hold_mask,
            "Hold: existing stock already covers likely launch demand, and comparable promo history plus low incremental value do not justify a fresh buy.",
        )
        decision_outputs["client_reason"] = decision_outputs["client_reason"].where(
            ~inventory_low_value_hold_mask,
            "Current inventory already covers the likely launch need, so hold stock and avoid buying more until early sell-through proves stronger demand.",
        )
        decision_outputs["operational_note"] = decision_outputs["operational_note"].where(
            ~inventory_low_value_hold_mask,
            "Action now: hold current stock and monitor early promo sell-through before considering any reorder.",
        )
        decision_outputs["publish_eligibility_reason"] = decision_outputs["publish_eligibility_reason"].where(
            ~inventory_low_value_hold_mask,
            PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_HOLD_INVENTORY_SUFFICIENT,
        )
        decision_outputs["review_reason"] = decision_outputs["review_reason"].where(
            ~inventory_low_value_hold_mask,
            "",
        )
        decision_outputs["decision_recommendation"] = decision_outputs["decision_recommendation"].where(
            ~inventory_low_value_do_not_order_mask,
            "DO_NOT_ORDER",
        )
        decision_outputs["decision_reason"] = decision_outputs["decision_reason"].where(
            ~inventory_low_value_do_not_order_mask,
            "Do not order: existing stock already covers likely promotional demand, and comparable promo history plus low incremental value do not justify tying up fresh capital.",
        )
        decision_outputs["client_reason"] = decision_outputs["client_reason"].where(
            ~inventory_low_value_do_not_order_mask,
            "Use existing stock first; the expected return is too weak to justify buying more for this promotion.",
        )
        decision_outputs["operational_note"] = decision_outputs["operational_note"].where(
            ~inventory_low_value_do_not_order_mask,
            "Action now: do not place a fresh order unless local sell-through materially outperforms this weak-demand posture.",
        )
        decision_outputs["publish_eligibility_reason"] = decision_outputs["publish_eligibility_reason"].where(
            ~inventory_low_value_do_not_order_mask,
            PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_DO_NOT_ORDER_LOW_INCREMENTAL_VALUE,
        )
        decision_outputs["review_reason"] = decision_outputs["review_reason"].where(
            ~inventory_low_value_do_not_order_mask,
            "",
        )
        # Preserve governed non-buy outcomes after the policy cap has already
        # removed the buy edge. Policy review overlays should still apply to
        # existing REVIEW rows, but they must not reopen safe HOLD/DO_NOT_ORDER
        # outcomes as manual review work.
        policy_review_override_mask = (
            policy_review_mask
            & ~decision_outputs["decision_recommendation"].astype(str).str.strip().str.upper().isin({
                "HOLD",
                "DO_NOT_ORDER",
            })
        )
        decision_outputs["decision_recommendation"] = decision_outputs["decision_recommendation"].where(
            ~policy_review_override_mask,
            "REVIEW",
        )
        decision_outputs["decision_reason"] = decision_outputs["decision_reason"].where(
            ~policy_review_override_mask,
            "Policy review override: " + policy_adjustments["review_override_reason"].astype(str),
        )
        decision_outputs["client_reason"] = decision_outputs["client_reason"].where(
            ~policy_review_override_mask,
            "Governed policy forced review in a worst evidence bucket before auto-order release.",
        )
        decision_outputs["operational_note"] = decision_outputs["operational_note"].where(
            ~policy_review_override_mask,
            "Action now: hold auto-order and inspect the governed policy reason before releasing stock.",
        )
        decision_outputs["review_reason"] = decision_outputs["review_reason"].where(
            ~policy_review_override_mask,
            policy_adjustments["review_override_reason"].astype(str),
        )
        review_escalation_reason_code = pd.Series("not_review", index=frame.index, dtype="object")
        review_mask = decision_outputs["decision_recommendation"].astype(str).eq("REVIEW")
        review_escalation_reason_code = review_escalation_reason_code.where(
            ~(review_mask & policy_review_override_mask),
            policy_adjustments["review_override_reason"].astype(str),
        )
        review_escalation_reason_code = review_escalation_reason_code.where(
            ~(
                review_mask
                & ~policy_review_mask
                & pd.to_numeric(
                    order_decision_diagnostics["feature_order_risk_reason_launch_total_conflict_flag"],
                    errors="coerce",
                ).ge(1.0)
            ),
            "launch_total_conflict",
        )
        review_escalation_reason_code = review_escalation_reason_code.where(
            ~(review_mask & ~policy_review_mask & review_escalation_reason_code.eq("not_review") & pd.to_numeric(order_decision_diagnostics["feature_order_risk_reason_same_discount_weak_flag"], errors="coerce").ge(1.0)),
            "same_discount_weak",
        )
        review_escalation_reason_code = review_escalation_reason_code.where(
            ~(review_mask & ~policy_review_mask & review_escalation_reason_code.eq("not_review") & pd.to_numeric(order_decision_diagnostics["feature_order_risk_reason_elasticity_weak_flag"], errors="coerce").ge(1.0)),
            "elasticity_weak",
        )
        review_escalation_reason_code = review_escalation_reason_code.where(
            ~(review_mask & ~policy_review_mask & review_escalation_reason_code.eq("not_review") & pd.to_numeric(order_decision_diagnostics["feature_order_risk_reason_uplift_weak_flag"], errors="coerce").ge(1.0)),
            "uplift_weak",
        )
        review_escalation_reason_code = review_escalation_reason_code.where(
            ~(review_mask & ~policy_review_mask & review_escalation_reason_code.eq("not_review") & pd.to_numeric(order_decision_diagnostics["feature_order_risk_reason_sparse_history_flag"], errors="coerce").ge(1.0)),
            "sparse_history",
        )
        review_escalation_reason_code = review_escalation_reason_code.where(
            ~(review_mask & ~policy_review_mask & review_escalation_reason_code.eq("not_review") & pd.to_numeric(order_decision_diagnostics["feature_order_risk_reason_stock_vs_supported_gap_high_flag"], errors="coerce").ge(1.0)),
            "stock_vs_supported_gap_high",
        )
        review_escalation_reason_code = review_escalation_reason_code.where(
            ~(review_mask & ~policy_review_mask & review_escalation_reason_code.eq("not_review")),
            "review_not_from_order_diagnostics",
        )
        review_escalation_due_to_policy_flag = (review_mask & policy_review_override_mask).astype(float)
        review_escalation_due_to_evidence_conflict_flag = (
            review_mask
            & ~policy_review_mask
            & review_escalation_reason_code.isin(
                {
                    "launch_total_conflict",
                    "same_discount_weak",
                    "elasticity_weak",
                    "uplift_weak",
                    "sparse_history",
                    "stock_vs_supported_gap_high",
                }
            )
        ).astype(float)
        review_escalation_source = pd.Series("not_review", index=frame.index, dtype="object")
        review_escalation_source = review_escalation_source.where(~review_mask, "existing_logic")
        review_escalation_source = review_escalation_source.where(
            ~review_escalation_due_to_evidence_conflict_flag.astype(bool),
            "existing_evidence_conflict",
        )
        review_escalation_source = review_escalation_source.where(
            ~review_escalation_due_to_policy_flag.astype(bool),
            "policy",
        )

        suggested_order_units_series = decision_outputs["suggested_order_units"]
        expected_leftover_series = decision_outputs["expected_leftover_units_end_of_promo"]
        source_discount_percent = _numeric_series(
            frame,
            ("discount_percent", "feature_discount_depth_pct", "promo_discount_percent"),
        ).fillna(0.0)
        discount_truth_components = _resolve_discount_truth_components(frame)
        normal_price_series = discount_truth_components["price_normal"].fillna(0.0)
        promo_price_series = discount_truth_components["price_promo"].fillna(0.0)
        feature_period_days = _optional_numeric_series(frame, "feature_promo_period_days")
        promotion_period_days = pd.to_numeric(
            feature_period_days.where(feature_period_days.notna(), inputs["promo_window_days"]),
            errors="coerce",
        ).replace(0.0, pd.NA).fillna(inputs["promo_window_days"]).fillna(1.0)
        expected_units_per_period = pd.to_numeric(
            forecast_outputs["predicted_units_total_promo"], errors="coerce"
        ).fillna(0.0).clip(lower=0.0)
        expected_units_per_day = (
            expected_units_per_period.divide(promotion_period_days.where(promotion_period_days.gt(0.0), 1.0))
            .fillna(0.0)
            .round(4)
        )
        target_end_stock_units = _optional_numeric_series(frame, "feature_end_of_promo_target_units")
        target_end_stock_units = target_end_stock_units.where(
            target_end_stock_units.notna(),
            forecast_outputs["base_units_target"],
        ).fillna(0.0).clip(lower=0.0)
        target_end_days_cover = _numeric_series(
            frame,
            ("feature_end_of_promo_target_days_cover",),
        ).fillna(0.0).clip(lower=0.0)
        estimated_end_stock_units = (
            projected_on_hand_at_promo_start
            + pd.to_numeric(suggested_order_units_series, errors="coerce").fillna(0.0)
            - expected_units_per_period
        ).clip(lower=0.0)
        month_end_cash_flag = _numeric_series(
            frame,
            ("feature_month_end_cash_runoff_pressure_flag",),
        ).fillna(0.0).clip(lower=0.0, upper=1.0)
        cashflow_runoff_status = pd.Series("standard_cashflow", index=frame.index, dtype="object")
        cashflow_runoff_status = cashflow_runoff_status.where(
            month_end_cash_flag.lt(1.0),
            "month_end_runoff_max_7d_cover",
        )
        trust_floor_status = pd.Series("trust_floor_met", index=frame.index, dtype="object")
        trust_floor_status = trust_floor_status.where(
            estimated_end_stock_units.ge(target_end_stock_units),
            "below_target_end_stock",
        )
        speculative_capital_units = _optional_numeric_series(
            frame,
            "feature_expected_leftover_above_trust_floor_units",
        )
        fallback_speculative_units = (estimated_end_stock_units - target_end_stock_units).clip(lower=0.0)
        speculative_capital_units = speculative_capital_units.where(
            speculative_capital_units.notna(),
            fallback_speculative_units,
        ).clip(lower=0.0)
        units_needed_for_trust_floor = _optional_numeric_series(frame, "feature_units_needed_for_trust_floor")
        units_needed_for_high_demand_cover = _optional_numeric_series(frame, "feature_units_needed_for_high_demand_cover")
        units_above_trust_target = _optional_numeric_series(frame, "feature_units_above_trust_target")
        capital_tied_above_trust_target = _optional_numeric_series(frame, "feature_capital_tied_above_trust_target")
        expected_gp_on_trust_floor_units = _optional_numeric_series(frame, "feature_expected_gp_on_trust_floor_units")
        expected_gp_on_speculative_units = _optional_numeric_series(frame, "feature_expected_gp_on_speculative_units")
        risk_adjusted_value_of_speculative_units = _optional_numeric_series(
            frame,
            "feature_risk_adjusted_value_of_speculative_units",
        )
        download_frame = pd.DataFrame(
            {
                "store_number": inputs["store_number"],
                "promotion_header_key": inputs["promotion_header_key"],
                "promotion_name": inputs["promotion_name"],
                "promotion_start_date": inputs["promo_start_date"],
                "promotion_end_date": inputs["promo_end_date"],
                "sku_number": inputs["sku_number"],
                "product_description": inputs["description"],
                "current_soh_units": forecast_outputs["current_soh_units"],
                "qty_on_order_units": forecast_outputs["qty_on_order_units"],
                "promo_allocated_units": inputs["promo_allocated_units"],
                "predicted_units_until_promo_start": forecast_outputs["predicted_units_until_promo_start"],
                "predicted_units_first_7_days_of_promo": forecast_outputs["predicted_units_first_7_days_of_promo"],
                "predicted_units_total_promo": forecast_outputs["predicted_units_total_promo"],
                "promotion_period_days": promotion_period_days.round(0).astype("int64"),
                "expected_units_per_period": expected_units_per_period.round(0).astype("int64"),
                "expected_units_per_day": expected_units_per_day.astype(float),
                "base_units_target": forecast_outputs["base_units_target"],
                "target_end_stock_units": target_end_stock_units.round(4).astype(float),
                "target_end_days_cover": target_end_days_cover.round(4).astype(float),
                "cashflow_runoff_status": cashflow_runoff_status,
                "trust_floor_status": trust_floor_status,
                "units_needed_for_trust_floor": units_needed_for_trust_floor.round(4).astype(float),
                "units_needed_for_high_demand_cover": units_needed_for_high_demand_cover.round(4).astype(float),
                "units_above_trust_target": units_above_trust_target.round(4).astype(float),
                "capital_tied_above_trust_target": capital_tied_above_trust_target.round(2).astype(float),
                "expected_gp_on_trust_floor_units": expected_gp_on_trust_floor_units.round(2).astype(float),
                "expected_gp_on_speculative_units": expected_gp_on_speculative_units.round(2).astype(float),
                "risk_adjusted_value_of_speculative_units": risk_adjusted_value_of_speculative_units.round(2).astype(float),
                "speculative_capital_above_floor_units": speculative_capital_units.round(4).astype(float),
                "speculative_capital_above_floor_value": (speculative_capital_units * inputs["unit_cost"]).round(2).astype(float),
                "promo_start_target_soh_units": forecast_outputs["promo_start_target_soh_units"],
                "suggested_order_units": suggested_order_units_series,
                "expected_leftover_units_end_of_promo": expected_leftover_series,
                "suggested_order_value": (suggested_order_units_series.astype(float) * inputs["unit_cost"]).round(4),
                "stockout_risk_flag": decision_outputs["stockout_risk_flag"],
                "overstock_risk_flag": decision_outputs["overstock_risk_flag"],
                "capital_tied_up_risk_flag": decision_outputs["capital_tied_up_risk_flag"],
                "estimated_cash_risk_band": decision_outputs["estimated_cash_risk_band"],
                "demand_confidence_band": decision_outputs["demand_confidence_band"],
                "execution_attention_flag": decision_outputs["execution_attention_flag"],
                "forecast_quality_flag": decision_outputs["forecast_quality_flag"],
                "forecast_reliability_band": decision_outputs["forecast_reliability_band"],
                "demand_shape_flag": decision_outputs["demand_shape_flag"],
                "promo_lift_expectation_flag": decision_outputs["promo_lift_expectation_flag"],
                "demand_evidence_class": decision_outputs["demand_evidence_class"],
                "cold_start_flag": decision_outputs["cold_start_flag"],
                "insufficient_history_flag": decision_outputs["insufficient_history_flag"],
                "publish_eligibility_reason": decision_outputs["publish_eligibility_reason"],
                "review_reason": decision_outputs["review_reason"],
                "promotion_effectiveness_signal": decision_outputs["promotion_effectiveness_signal"],
                "decision_recommendation": decision_outputs["decision_recommendation"],
                "decision_reason": decision_outputs["decision_reason"],
                "client_reason": decision_outputs["client_reason"],
                "operational_note": decision_outputs["operational_note"],
                "final_decision_score": inputs["final_decision_score"].round(4),
                "final_confidence_score": inputs["final_confidence_score"].round(4),
                "low_nonzero_value_relief_delta": _optional_first_numeric_series(
                    frame,
                    (
                        "low_nonzero_value_relief_delta",
                        "low_nonzero_specialist_value_signal",
                        "specialist_shadow_expected_incremental_value_delta",
                        "expected_incremental_value_dollars_delta",
                    ),
                ).fillna(0.0).round(2).astype(float),
                "discount_percent": source_discount_percent,
                "normal_price": normal_price_series,
                "promo_price": promo_price_series,
                "feature_historical_promo_events_same_discount": _numeric_series(frame, ("feature_historical_promo_events_same_discount",)).fillna(0.0),
                "feature_historical_promo_events_same_or_better_discount": _numeric_series(frame, ("feature_historical_promo_events_same_or_better_discount",)).fillna(0.0),
                "feature_historical_units_same_discount_avg": _numeric_series(frame, ("feature_historical_units_same_discount_avg",)).fillna(0.0),
                "feature_historical_units_same_or_better_discount_avg": _numeric_series(frame, ("feature_historical_units_same_or_better_discount_avg",)).fillna(0.0),
                "feature_historical_discount_response_confidence": _numeric_series(frame, ("feature_historical_discount_response_confidence",)).fillna(0.0),
                "feature_discount_band_response_avg": _numeric_series(frame, ("feature_discount_band_response_avg",)).fillna(0.0),
                "feature_discount_band_event_count": _numeric_series(frame, ("feature_discount_band_event_count",)).fillna(0.0),
            }
        )
        download_frame = download_frame.loc[:, list(COMMERCIAL_SCHEMA_COLUMNS)]
        download_frame.attrs = dict(getattr(download_frame, "attrs", {}))
        download_frame.attrs["predicted_units_total_promo_fractional"] = (
            forecast_outputs["predicted_units_total_promo_fractional"].tolist()
        )
        per_row_forecast_diagnostics = pd.DataFrame(
            {
                "store_number": inputs["store_number"].astype(str),
                "promotion_header_key": inputs["promotion_header_key"].astype(str),
                "sku_number": inputs["sku_number"].astype(str),
                "promo_unit_cost": inputs["unit_cost"].astype(float),
                "forecast_source_used": forecast_outputs["forecast_resolution"]["forecast_source"],
                "forecast_source_raw_units": forecast_outputs["forecast_resolution"]["forecast_source_raw_units"],
                "forecast_source_priority_rank": forecast_outputs["forecast_resolution"]["forecast_source_priority_rank"],
                "forecast_repaired_flag": forecast_outputs["forecast_resolution"]["repaired_from_degenerate"],
                "forecast_repair_reason": forecast_outputs["forecast_resolution"]["forecast_repair_reason"],
                "forecast_zero_before_repair_flag": forecast_outputs["forecast_resolution"]["forecast_zero_before_repair_flag"],
                "forecast_zero_after_repair_flag": forecast_outputs["forecast_resolution"]["forecast_zero_after_repair_flag"],
                "forecast_flat_promotion_flag": forecast_outputs["forecast_resolution"]["forecast_flat_promotion_flag"],
                "raw_required_implied_units": forecast_outputs["forecast_resolution"]["raw_required_implied_units"],
                "raw_demand_reference_units": forecast_outputs["forecast_resolution"]["raw_demand_reference_units"],
                "raw_baseline_expected_units": forecast_outputs["forecast_resolution"]["raw_baseline_expected_units"],
                "raw_predicted_units_sold": forecast_outputs["forecast_resolution"]["raw_predicted_units_sold"],
                "raw_history_units": forecast_outputs["forecast_resolution"]["raw_history_units"],
                "forecast_zero_demand_classification": forecast_outputs["forecast_resolution"]["forecast_zero_demand_classification"],
                "first7_feature_raw_units": forecast_outputs["forecast_resolution"]["first7_feature_raw_units"],
                "first7_fallback_raw_units": forecast_outputs["forecast_resolution"]["first7_fallback_raw_units"],
                "first7_fallback_candidate_flag": forecast_outputs["forecast_resolution"]["first7_fallback_candidate_flag"],
                "first7_fallback_repaired_flag": forecast_outputs["forecast_resolution"]["first7_fallback_repaired_flag"],
                "first7_fallback_reason": forecast_outputs["forecast_resolution"]["first7_fallback_reason"],
                "forecast_repair_allowed_flag": forecast_outputs["forecast_resolution"]["forecast_repair_allowed_flag"],
                "forecast_repair_rejected_reason": forecast_outputs["forecast_resolution"]["forecast_repair_rejected_reason"],
                "forecast_rounding_loss_flag": forecast_outputs["forecast_resolution"]["forecast_rounding_loss_flag"],
                "forecast_row_override_applied_flag": forecast_outputs["forecast_resolution"]["forecast_row_override_applied_flag"],
                "forecast_row_override_source": forecast_outputs["forecast_resolution"]["forecast_row_override_source"],
                "forecast_collapse_requires_review_flag": forecast_outputs["forecast_resolution"]["forecast_collapse_requires_review_flag"],
                "forecast_unresolved_collapse_reason": forecast_outputs["forecast_resolution"][
                    "forecast_unresolved_collapse_reason"
                ],
                "zero_forecast_is_evidence_supported": forecast_outputs["forecast_resolution"][
                    "zero_forecast_is_evidence_supported"
                ],
                "zero_forecast_reason_code": forecast_outputs["forecast_resolution"]["zero_forecast_reason_code"],
                "zero_forecast_confidence": forecast_outputs["forecast_resolution"]["zero_forecast_confidence"],
                "historical_promo_response_count": forecast_outputs["forecast_resolution"][
                    "historical_promo_response_count"
                ],
                "historical_promo_units_at_similar_discount": forecast_outputs["forecast_resolution"][
                    "historical_promo_units_at_similar_discount"
                ],
                "historical_promo_lift_at_similar_discount": forecast_outputs["forecast_resolution"][
                    "historical_promo_lift_at_similar_discount"
                ],
                "never_sold_at_similar_discount_flag": forecast_outputs["forecast_resolution"][
                    "never_sold_at_similar_discount_flag"
                ],
                "baseline_velocity_class": forecast_outputs["forecast_resolution"]["baseline_velocity_class"],
                "demand_evidence_class": decision_outputs["demand_evidence_class"],
                "cold_start_flag": decision_outputs["cold_start_flag"],
                "insufficient_history_flag": decision_outputs["insufficient_history_flag"],
                "publish_eligibility_reason": decision_outputs["publish_eligibility_reason"],
                "review_reason": decision_outputs["review_reason"],
                "commercial_coherence_rule": decision_outputs["commercial_coherence_rule"],
                "commercial_contradiction_escalation_flag": decision_outputs["commercial_contradiction_escalation_flag"],
                "true_zero_demand_retained_flag": decision_outputs["true_zero_demand_retained_flag"],
                "likely_inventory_drag_flag": decision_outputs["likely_inventory_drag_flag"],
                "estimated_cash_risk_band": decision_outputs["estimated_cash_risk_band"],
                "demand_confidence_band": decision_outputs["demand_confidence_band"],
                "execution_attention_flag": decision_outputs["execution_attention_flag"],
                "decision_recommendation": decision_outputs["decision_recommendation"],
                "same_discount_history_bucket": order_decision_diagnostics["same_discount_history_bucket"],
                "elasticity_confidence_bucket": order_decision_diagnostics["elasticity_confidence_bucket"],
                "uplift_confidence_bucket": order_decision_diagnostics["uplift_confidence_bucket"],
                "base_demand_growth_bucket": order_decision_diagnostics["base_demand_growth_bucket"],
                "window_conflict_bucket": order_decision_diagnostics["window_conflict_bucket"],
                "adjusted_supported_total_units": policy_adjustments["adjusted_supported_total_units"],
                "adjusted_launch_units": policy_adjustments["adjusted_launch_units"],
                "adjusted_order_cap_units": policy_adjustments["adjusted_order_cap_units"],
                "policy_adjustment_fired_flag": policy_adjustments["policy_adjustment_fired_flag"],
                "policy_adjustment_reason": policy_adjustments["policy_adjustment_reason"],
                "policy_adjustment_strength": policy_adjustments["policy_adjustment_strength"],
                "policy_units_removed": policy_adjustments["policy_units_removed"],
                "policy_capital_at_risk_removed": policy_adjustments["policy_capital_at_risk_removed"],
                "policy_review_override_flag": policy_adjustments["review_override_flag"],
                "policy_review_override_reason": policy_adjustments["review_override_reason"],
                "evidence_same_discount_present_flag": order_decision_diagnostics["evidence_same_discount_present_flag"],
                "evidence_usable_elasticity_flag": order_decision_diagnostics["evidence_usable_elasticity_flag"],
                "evidence_strong_uplift_support_flag": order_decision_diagnostics["evidence_strong_uplift_support_flag"],
                "weak_fallback_logic_flag": order_decision_diagnostics["weak_fallback_logic_flag"],
                "order_sizing_driver": order_decision_diagnostics["order_sizing_driver"],
                "order_cap_reason": order_decision_diagnostics["order_cap_reason"],
                "evidence_conflict_review_candidate_flag": order_decision_diagnostics[
                    "evidence_conflict_review_candidate_flag"
                ],
                "order_risk_driver_combination": order_decision_diagnostics["order_risk_driver_combination"],
                "feature_order_risk_reason_same_discount_weak_flag": order_decision_diagnostics[
                    "feature_order_risk_reason_same_discount_weak_flag"
                ],
                "feature_order_risk_reason_elasticity_weak_flag": order_decision_diagnostics[
                    "feature_order_risk_reason_elasticity_weak_flag"
                ],
                "feature_order_risk_reason_uplift_weak_flag": order_decision_diagnostics[
                    "feature_order_risk_reason_uplift_weak_flag"
                ],
                "feature_order_risk_reason_base_trend_falling_flag": order_decision_diagnostics[
                    "feature_order_risk_reason_base_trend_falling_flag"
                ],
                "feature_order_risk_reason_launch_total_conflict_flag": order_decision_diagnostics[
                    "feature_order_risk_reason_launch_total_conflict_flag"
                ],
                "feature_order_risk_reason_stock_vs_supported_gap_high_flag": order_decision_diagnostics[
                    "feature_order_risk_reason_stock_vs_supported_gap_high_flag"
                ],
                "feature_order_risk_reason_sparse_history_flag": order_decision_diagnostics[
                    "feature_order_risk_reason_sparse_history_flag"
                ],
                "feature_order_risk_reason_multi_driver_count": order_decision_diagnostics[
                    "feature_order_risk_reason_multi_driver_count"
                ],
                "feature_order_risk_overallocation_score": order_decision_diagnostics[
                    "feature_order_risk_overallocation_score"
                ],
                "feature_order_support_strength_score": order_decision_diagnostics[
                    "feature_order_support_strength_score"
                ],
                "feature_order_review_priority_score": order_decision_diagnostics[
                    "feature_order_review_priority_score"
                ],
                "order_review_escalation_due_to_policy_flag": review_escalation_due_to_policy_flag,
                "order_review_escalation_due_to_evidence_conflict_flag": review_escalation_due_to_evidence_conflict_flag,
                "order_review_escalation_source": review_escalation_source,
                "order_review_escalation_reason_code": review_escalation_reason_code,
            },
            index=frame.index,
        )
        download_frame.attrs["source_row_count"] = int(len(frame.index))
        download_frame.attrs["forecast_source_counts"] = {
            source: int(count)
            for source, count in forecast_outputs["forecast_resolution"]["forecast_source"].value_counts(dropna=False).to_dict().items()
        }
        download_frame.attrs["forecast_repaired_count"] = int(
            forecast_outputs["forecast_resolution"]["repaired_from_degenerate"].sum()
        )
        download_frame.attrs["first7_fallback_repaired_count"] = int(
            forecast_outputs["forecast_resolution"]["first7_fallback_repaired_flag"].astype(bool).sum()
        )
        download_frame.attrs["forecast_resolution"] = forecast_outputs["forecast_resolution"]
        download_frame.attrs["forecast_per_row_diagnostics"] = per_row_forecast_diagnostics
        # Root-cause note: prior max-based cohort blend caused flat outputs whenever
        # baseline_expected_units was flat at a high value (dominated the max even when
        # required_implied_units had good per-row variation). Replaced with priority-ordered
        # per-promotion source selection: required_implied_units > demand_reference_units >
        # baseline_expected_units > predicted_units_sold > history signal.
        return download_frame

    def _extract_download_input_series(self, *, frame: pd.DataFrame, as_of_date: str) -> dict[str, pd.Series]:
        """Extract and normalize Stage 11 input series used by commercial frame assembly."""
        store_number = _raw_series(frame, ("store_number", "store_number_key"))
        promotion_id = _raw_series(frame, ("promotion_id", "promotional_sku_id", "promotional_sku_id_key"))
        promotion_name = _text_series(frame, ("promotion_name",))
        promo_type = _text_series(frame, ("promo_type",))
        sku_number = _raw_series(frame, ("sku_number", "sku_number_key"))
        description = _best_available_text_series(frame, ("product_description", "sku_description", "description"))
        promo_start_date = _date_series(frame, ("promotion_start_date_date", "promotion_start_date"))
        promo_end_date = _date_series(frame, ("promotional_end_date_date", "promotional_end_date"))

        current_soh_raw = _numeric_series(frame, ("current_soh",)).clip(lower=0.0)
        on_order_qty_raw = _numeric_series(frame, ("qty_on_order",)).clip(lower=0.0)
        promo_allocated_units = _round_non_negative_units(
            _numeric_series(frame, ("pl_allocation_qty", "pl_allocated")).clip(lower=0.0)
        )
        unit_cost = _numeric_series(frame, ("promo_effective_cost", "promo_cost_price", "last_received_cost")).clip(lower=0.0)

        final_decision_score = _numeric_series(frame, ("final_decision_score",)).clip(lower=0.0, upper=1.0)
        if "final_confidence_score" in frame.columns:
            final_confidence_score = _numeric_series(frame, ("final_confidence_score",)).clip(lower=0.0, upper=1.0)
        else:
            final_confidence_score = pd.Series(pd.NA, index=frame.index, dtype="float64")
        decision_recommendation = _text_series(frame, ("decision_recommendation",))
        leftover_risk_penalty = _numeric_series(frame, ("leftover_risk_penalty",)).clip(lower=0.0)

        as_of_parsed = pd.to_datetime(as_of_date, errors="coerce")
        promo_start_parsed = pd.to_datetime(promo_start_date, errors="coerce")
        promo_end_parsed = pd.to_datetime(promo_end_date, errors="coerce")
        days_until_promo_start = (promo_start_parsed - as_of_parsed).dt.days.clip(lower=0).fillna(0)
        promo_window_days = _numeric_series(frame, ("live_promo_window_days", "promo_days")).replace(0.0, pd.NA)
        derived_window_days = (promo_end_parsed - promo_start_parsed).dt.days.add(1).clip(lower=1)
        promo_window_days = promo_window_days.where(promo_window_days.notna(), derived_window_days).fillna(1.0)
        promotion_header_key = _build_promotion_header_key_series(
            promotion_id=promotion_id,
            promotion_name=promotion_name,
            promotion_start_date=promo_start_date,
            promotion_end_date=promo_end_date,
            promo_type=promo_type,
        )
        return {
            "store_number": store_number,
            "promotion_name": promotion_name,
            "promo_type": promo_type,
            "sku_number": sku_number,
            "description": description,
            "promo_start_date": promo_start_date,
            "promo_end_date": promo_end_date,
            "current_soh_raw": current_soh_raw,
            "on_order_qty_raw": on_order_qty_raw,
            "promo_allocated_units": promo_allocated_units,
            "unit_cost": unit_cost,
            "final_decision_score": final_decision_score,
            "final_confidence_score": final_confidence_score,
            "decision_recommendation": decision_recommendation,
            "leftover_risk_penalty": leftover_risk_penalty,
            "days_until_promo_start": days_until_promo_start,
            "promo_window_days": promo_window_days,
            "promotion_header_key": promotion_header_key,
        }

    def _build_download_forecast_outputs(
        self,
        *,
        frame: pd.DataFrame,
        promo_window_days: pd.Series,
        days_until_promo_start: pd.Series,
        promotion_header_key: pd.Series,
        current_soh_raw: pd.Series,
        on_order_qty_raw: pd.Series,
        policy_adjusted_total_cap_units: pd.Series | None = None,
        policy_adjusted_launch_cap_units: pd.Series | None = None,
    ) -> dict[str, pd.Series | pd.DataFrame]:
        """Resolve forecast sources and derive integer-safe forecast window series."""
        forecast_resolution = _resolve_commercial_forecast_inputs(
            frame=frame,
            promotion_header_key=promotion_header_key,
            promo_window_days=promo_window_days,
            predicted_units_sold=_numeric_series(frame, ("predicted_units_sold",)).clip(lower=0.0),
            required_implied_units=_numeric_series(frame, ("required_implied_units",)).clip(lower=0.0),
            demand_reference_units=_numeric_series(frame, ("demand_reference_units",)).clip(lower=0.0),
            baseline_expected_units=_numeric_series(
                frame,
                ("feature_expected_baseline_units_promo_window", "feature_baseline_units_expected_promo_window", "baseline_expected_units"),
            ).clip(lower=0.0),
            avg_daily_units=_numeric_series(frame, ("avg_daily_units",)).clip(lower=0.0),
            bar_units=_numeric_series(frame, ("bar_units",)).clip(lower=0.0),
        )
        predicted_units_total_promo_raw = forecast_resolution["resolved_total_units"].clip(lower=0.0)
        # Phase 3: do not ceiling customer demand forecast totals with order-policy caps.
        forecast_daily_units = forecast_resolution["resolved_daily_units"].clip(lower=0.0)
        baseline_daily_units = _numeric_series(
            frame,
            ("feature_non_promo_30d_avg_daily_units", "feature_non_promo_56d_avg_daily_units", "baseline_daily_units", "feature_pre_promo_baseline_daily_units"),
        ).clip(lower=0.0)
        launch_base_daily_units = baseline_daily_units.where(baseline_daily_units.gt(0.0), forecast_daily_units)
        if "feature_expected_baseline_units_first_7_days" in frame.columns or "feature_baseline_units_expected_first_7_days" in frame.columns:
            baseline_expected_first_7_days = _numeric_series(
                frame,
                ("feature_expected_baseline_units_first_7_days", "feature_baseline_units_expected_first_7_days"),
            ).clip(lower=0.0)
        else:
            baseline_expected_first_7_days = (launch_base_daily_units * promo_window_days.clip(upper=7.0)).clip(lower=0.0)
        if "feature_expected_incremental_uplift_units_first_7_days" in frame.columns or "feature_uplift_units_expected_first_7_days" in frame.columns:
            uplift_expected_first_7_days = _numeric_series(
                frame,
                ("feature_expected_incremental_uplift_units_first_7_days", "feature_uplift_units_expected_first_7_days"),
            ).clip(lower=0.0)
        else:
            uplift_supported_total_units = _numeric_series(
                frame,
                ("feature_expected_incremental_uplift_units_same_discount", "feature_uplift_units_expected_total", "feature_probability_uplift_supported_units"),
            ).clip(lower=0.0)
            uplift_expected_first_7_days = uplift_supported_total_units * promo_window_days.clip(upper=7.0).divide(
                promo_window_days.where(promo_window_days > 0.0),
            ).fillna(0.0)
        leadup_units_raw = (launch_base_daily_units * days_until_promo_start.clip(lower=0.0)).clip(lower=0.0)
        first7_feature_units_raw = (baseline_expected_first_7_days + uplift_expected_first_7_days).clip(lower=0.0)
        promo_window_days_for_share = promo_window_days.where(promo_window_days > 0.0, 1.0).fillna(1.0)
        launch_window_days = promo_window_days_for_share.clip(lower=0.0, upper=7.0)
        prorated_total_first7_units = predicted_units_total_promo_raw.multiply(
            launch_window_days.divide(promo_window_days_for_share).fillna(0.0)
        ).clip(lower=0.0)
        prorated_total_first7_units = prorated_total_first7_units.where(
            prorated_total_first7_units.le(predicted_units_total_promo_raw),
            predicted_units_total_promo_raw,
        )
        preliminary_true_zero_mask = forecast_resolution[
            "forecast_zero_demand_classification"
        ].astype(str).eq(FORECAST_ZERO_DEMAND_TRUE)
        first7_fallback_candidate_mask = (
            predicted_units_total_promo_raw.gt(0.0)
            & first7_feature_units_raw.fillna(0.0).le(0.0)
            & ~preliminary_true_zero_mask
        )
        launch_window_units_raw = first7_feature_units_raw.where(
            ~first7_fallback_candidate_mask,
            prorated_total_first7_units,
        ).clip(lower=0.0)
        if policy_adjusted_launch_cap_units is not None:
            launch_cap_units = pd.to_numeric(
                policy_adjusted_launch_cap_units,
                errors="coerce",
            ).fillna(launch_window_units_raw)
            launch_window_units_raw = launch_window_units_raw.where(
                launch_window_units_raw.le(launch_cap_units),
                launch_cap_units,
            ).clip(lower=0.0)
        first7_fallback_repaired_mask = first7_fallback_candidate_mask & launch_window_units_raw.gt(0.0)
        first7_fallback_reason = pd.Series("", index=frame.index, dtype="object")
        first7_fallback_reason = first7_fallback_reason.where(
            ~first7_fallback_candidate_mask,
            FIRST7_FALLBACK_REPAIR_REASON,
        )
        first7_fallback_reason = first7_fallback_reason.where(
            ~(
                first7_fallback_candidate_mask
                & ~first7_fallback_repaired_mask
            ),
            FIRST7_FALLBACK_SUPPRESSED_BY_LAUNCH_CAP,
        )
        forecast_resolution = forecast_resolution.copy()
        forecast_resolution["first7_feature_raw_units"] = first7_feature_units_raw
        forecast_resolution["first7_fallback_raw_units"] = prorated_total_first7_units
        forecast_resolution["first7_fallback_candidate_flag"] = first7_fallback_candidate_mask.astype(bool)
        forecast_resolution["first7_fallback_repaired_flag"] = first7_fallback_repaired_mask.astype(bool)
        forecast_resolution["first7_fallback_reason"] = first7_fallback_reason

        current_soh_units = _round_non_negative_units(current_soh_raw)
        qty_on_order_units = _round_non_negative_units(on_order_qty_raw)
        predicted_units_total_promo = _integerize_forecast_total_units(
            predicted_units_total_promo_raw
        )
        predicted_units_total_promo_fractional = predicted_units_total_promo_raw.round(4)
        predicted_units_until_promo_start = _round_non_negative_units(leadup_units_raw)
        launch_window_units_raw = launch_window_units_raw.where(
            launch_window_units_raw.le(predicted_units_total_promo_raw + 0.5),
            predicted_units_total_promo_raw,
        )
        predicted_units_first_7_days_of_promo = _integerize_forecast_total_units(launch_window_units_raw)
        predicted_units_first_7_days_of_promo = predicted_units_first_7_days_of_promo.clip(
            upper=predicted_units_total_promo,
        )
        zero_forecast_evidence = _classify_zero_forecast_evidence(
            frame=frame,
            forecast_resolution=forecast_resolution,
            predicted_units_total_promo=predicted_units_total_promo,
            predicted_units_first_7_days_of_promo=predicted_units_first_7_days_of_promo,
        )
        forecast_resolution = forecast_resolution.copy()
        for column in zero_forecast_evidence.columns:
            forecast_resolution[column] = zero_forecast_evidence[column]
        evidence_supported_zero_mask = zero_forecast_evidence[
            "zero_forecast_is_evidence_supported"
        ].astype(bool)
        if evidence_supported_zero_mask.any():
            forecast_resolution.loc[
                evidence_supported_zero_mask,
                "forecast_zero_demand_classification",
            ] = FORECAST_ZERO_DEMAND_TRUE
            forecast_resolution.loc[
                evidence_supported_zero_mask,
                "forecast_collapse_requires_review_flag",
            ] = False
            forecast_resolution.loc[
                evidence_supported_zero_mask,
                "forecast_unresolved_collapse_reason",
            ] = ""

        base_units_target = pd.Series(
            [
                int(max(DEFAULT_BASE_STOCK_MIN_UNITS, math.ceil(BASE_STOCK_DAYS_COVER * float(daily_units or 0.0))))
                for daily_units in launch_base_daily_units.tolist()
            ],
            index=frame.index,
            dtype="int64",
        )
        promo_start_target_soh_units = (base_units_target + predicted_units_first_7_days_of_promo).astype("int64")
        return {
            "forecast_resolution": forecast_resolution,
            "current_soh_units": current_soh_units,
            "qty_on_order_units": qty_on_order_units,
            "predicted_units_total_promo": predicted_units_total_promo,
            "predicted_units_total_promo_fractional": predicted_units_total_promo_fractional,
            "predicted_units_until_promo_start": predicted_units_until_promo_start,
            "predicted_units_first_7_days_of_promo": predicted_units_first_7_days_of_promo,
            "base_units_target": base_units_target,
            "promo_start_target_soh_units": promo_start_target_soh_units,
        }

    def _sanitize_commercial_frame(self, frame: pd.DataFrame) -> _CommercialSanitizationResult:
        working = frame.copy()
        working.attrs = dict(frame.attrs)
        working["sku_number"] = _normalize_identifier_series(working["sku_number"])
        working["product_description"] = _normalize_text_series(
            working["product_description"],
            collapse_internal_whitespace=True,
        )

        null_sku_mask = working["sku_number"].isna()
        excluded_null_sku_rows = _with_exclusion_reason(
            working.loc[null_sku_mask],
            reason="excluded_null_or_blank_sku_number",
        )
        working = working.loc[~null_sku_mask].copy()

        blank_description_mask = working["product_description"].isna()
        excluded_blank_product_description_rows = _with_exclusion_reason(
            working.loc[blank_description_mask],
            reason="excluded_blank_product_description",
        )
        working = working.loc[~blank_description_mask].copy()

        value_numeric = pd.to_numeric(working["suggested_order_value"], errors="coerce")
        non_numeric_value_mask = value_numeric.isna()
        non_numeric_suggested_order_value_rows = _with_exclusion_reason(
            working.loc[non_numeric_value_mask],
            reason="excluded_non_numeric_suggested_order_value",
        )
        working = working.loc[~non_numeric_value_mask].copy()
        working["suggested_order_value"] = pd.to_numeric(
            working["suggested_order_value"],
            errors="coerce",
        ).round(4)

        duplicate_diagnostics, unresolved_duplicates = self._resolve_duplicate_rows(working)
        if not duplicate_diagnostics.empty:
            keep_mask = duplicate_diagnostics["keep_row"].astype(bool)
            kept_indices = set(duplicate_diagnostics.loc[keep_mask, "source_row_index"].tolist())
            all_duplicate_indices = set(duplicate_diagnostics["source_row_index"].tolist())
            dropped_indices = all_duplicate_indices.difference(kept_indices)
            working = pd.concat(
                [
                    working.loc[~working.index.isin(all_duplicate_indices)],
                    working.loc[sorted(kept_indices)],
                ],
                axis=0,
            )
            if dropped_indices:
                working = working.loc[~working.index.isin(dropped_indices)]

        working = working.loc[:, list(COMMERCIAL_SCHEMA_COLUMNS)].reset_index(drop=True)
        for column in COMMERCIAL_UNIT_COLUMNS:
            working[column] = _round_non_negative_units(working[column])
        working["suggested_order_value"] = pd.to_numeric(
            working["suggested_order_value"],
            errors="coerce",
        ).round(4)
        working["final_decision_score"] = pd.to_numeric(
            working["final_decision_score"],
            errors="coerce",
        ).round(4)
        working["final_confidence_score"] = pd.to_numeric(
            working["final_confidence_score"],
            errors="coerce",
        ).round(4)
        _sync_fractional_promo_attrs(working)

        return _CommercialSanitizationResult(
            cleaned_frame=working,
            excluded_null_sku_rows=excluded_null_sku_rows,
            excluded_blank_product_description_rows=excluded_blank_product_description_rows,
            non_numeric_suggested_order_value_rows=non_numeric_suggested_order_value_rows,
            duplicate_rows_diagnostics=duplicate_diagnostics,
            unresolved_duplicate_rows=unresolved_duplicates,
        )

    def _resolve_duplicate_rows(
        self,
        frame: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        duplicate_mask = frame.duplicated(
            subset=["store_number", "promotion_header_key", "sku_number"],
            keep=False,
        )
        if not duplicate_mask.any():
            empty = pd.DataFrame(
                columns=[
                    "store_number",
                    "promotion_header_key",
                    "sku_number",
                    "resolution_status",
                    "resolution_reason",
                    "keep_row",
                    "source_row_index",
                ]
            )
            return empty, empty

        duplicates = frame.loc[duplicate_mask].copy()
        diagnostics_rows: list[dict[str, object]] = []
        unresolved_rows: list[pd.DataFrame] = []

        rank_columns = [
            "final_confidence_score",
            "final_decision_score",
            "suggested_order_units",
            "predicted_units_total_promo",
        ]
        grouped = duplicates.groupby(
            ["store_number", "promotion_header_key", "sku_number"],
            dropna=False,
            sort=False,
        )
        for (store_number, promotion_header_key, sku_number), group in grouped:
            comparable = group.drop(columns=[], errors="ignore")
            equivalent = len(comparable.drop_duplicates(keep="first")) == 1
            if equivalent:
                keep_index = int(group.index[0])
                for index in group.index.tolist():
                    diagnostics_rows.append(
                        {
                            "store_number": str(store_number),
                            "promotion_header_key": str(promotion_header_key),
                            "sku_number": str(sku_number),
                            "resolution_status": "resolved",
                            "resolution_reason": "bitwise_equivalent",
                            "keep_row": bool(index == keep_index),
                            "source_row_index": int(index),
                        }
                    )
                continue

            ranked = group.copy()
            for rank_column in rank_columns:
                ranked[rank_column] = pd.to_numeric(ranked[rank_column], errors="coerce").fillna(-1e12)
            ranked = ranked.sort_values(
                by=rank_columns,
                ascending=[False, False, False, False],
                kind="mergesort",
            )
            top_index = int(ranked.index[0])
            if len(ranked.index) == 1:
                top_unique = True
            else:
                top_values = tuple(float(ranked.iloc[0][column]) for column in rank_columns)
                second_values = tuple(float(ranked.iloc[1][column]) for column in rank_columns)
                top_unique = top_values > second_values

            if top_unique:
                for index in group.index.tolist():
                    diagnostics_rows.append(
                        {
                            "store_number": str(store_number),
                            "promotion_header_key": str(promotion_header_key),
                            "sku_number": str(sku_number),
                            "resolution_status": "resolved",
                            "resolution_reason": "deterministic_rank",
                            "keep_row": bool(index == top_index),
                            "source_row_index": int(index),
                        }
                    )
            else:
                unresolved_rows.append(group.assign(duplicate_resolution_status="unresolved_conflict"))
                for index in group.index.tolist():
                    diagnostics_rows.append(
                        {
                            "store_number": str(store_number),
                            "promotion_header_key": str(promotion_header_key),
                            "sku_number": str(sku_number),
                            "resolution_status": "unresolved",
                            "resolution_reason": "conflicting_rows_not_rankable",
                            "keep_row": False,
                            "source_row_index": int(index),
                        }
                    )

        diagnostics_frame = pd.DataFrame(diagnostics_rows)
        unresolved_frame = (
            pd.concat(unresolved_rows, ignore_index=False)
            if unresolved_rows
            else pd.DataFrame(columns=list(frame.columns) + ["duplicate_resolution_status"])
        )
        return diagnostics_frame, unresolved_frame

    def _write_commercial_diagnostics_artifacts(
        self,
        *,
        run_id: str,
        frame: pd.DataFrame,
        forecast_health: dict[str, object],
        artifact_paths: PromotionArtifactPaths,
        sanitization: _CommercialSanitizationResult,
        forecast_per_row_diagnostics: pd.DataFrame | None = None,
    ) -> dict[str, str]:
        diagnostics_root = artifact_paths.store_prediction_diagnostics_root(run_id)
        diagnostics_root.mkdir(parents=True, exist_ok=True)

        null_sku_path = diagnostics_root / "excluded_null_sku_rows.csv"
        blank_description_path = diagnostics_root / "excluded_blank_product_description_rows.csv"
        duplicate_rows_path = diagnostics_root / "duplicate_store_promotion_sku_rows.csv"
        non_numeric_value_path = diagnostics_root / "non_numeric_suggested_order_value_rows.csv"
        forecast_json_path = diagnostics_root / "forecast_collapse_diagnostics.json"
        forecast_distribution_path = diagnostics_root / "forecast_distribution_by_promotion.csv"
        forecast_source_raw_values_path = diagnostics_root / "forecast_source_raw_values_per_row.csv"
        forecast_repaired_rows_path = diagnostics_root / "forecast_repaired_rows.csv"
        true_zero_retained_rows_path = diagnostics_root / "true_zero_demand_retained_rows.csv"
        contradiction_escalations_path = diagnostics_root / "commercial_contradiction_repairs_or_escalations.csv"
        allocation_decision_summary_csv_path = artifact_paths.store_prediction_allocation_decision_summary_csv_path(run_id)
        allocation_decision_summary_json_path = artifact_paths.store_prediction_allocation_decision_summary_json_path(run_id)
        forecast_source_mix_by_promotion_path = diagnostics_root / "forecast_source_mix_by_promotion.csv"
        forecast_first7_to_total_sanity_path = diagnostics_root / "forecast_first7_to_total_sanity.csv"
        forecast_credibility_summary_path = diagnostics_root / "forecast_credibility_summary.json"
        forecast_collapse_rows_csv_path = diagnostics_root / "forecast_collapse_rows.csv"
        forecast_collapse_rows_parquet_path = diagnostics_root / "forecast_collapse_rows.parquet"
        forecast_collapse_by_promotion_path = diagnostics_root / "forecast_collapse_by_promotion.csv"
        forecast_collapse_by_source_path = diagnostics_root / "forecast_collapse_by_source.csv"
        forecast_zero_demand_classification_path = diagnostics_root / "forecast_zero_demand_classification.csv"
        forecast_repairs_applied_path = diagnostics_root / "forecast_repairs_applied.csv"
        forecast_repairs_rejected_path = diagnostics_root / "forecast_repairs_rejected.csv"
        forecast_rounding_loss_rows_path = diagnostics_root / "forecast_rounding_loss_rows.csv"
        forecast_honest_zero_rows_path = diagnostics_root / "forecast_honest_zero_rows.csv"
        forecast_low_nonzero_rows_path = diagnostics_root / "forecast_low_nonzero_rows.csv"
        forecast_unresolved_collapse_rows_path = diagnostics_root / "forecast_unresolved_collapse_rows.csv"
        forecast_stage11_outcome_summary_path = diagnostics_root / "forecast_stage11_outcome_summary.json"
        rows_by_demand_evidence_class_path = diagnostics_root / "rows_by_demand_evidence_class.csv"
        cold_start_new_line_rows_path = diagnostics_root / "cold_start_new_line_rows.csv"
        true_zero_demand_rows_path = diagnostics_root / "true_zero_demand_rows.csv"
        artificial_collapse_rows_path = diagnostics_root / "artificial_collapse_rows.csv"

        sanitization.excluded_null_sku_rows.to_csv(null_sku_path, index=False)
        sanitization.excluded_blank_product_description_rows.to_csv(blank_description_path, index=False)
        sanitization.duplicate_rows_diagnostics.to_csv(duplicate_rows_path, index=False)
        sanitization.non_numeric_suggested_order_value_rows.to_csv(non_numeric_value_path, index=False)

        distribution_rows: list[dict[str, object]] = []
        grouped = frame.groupby("promotion_header_key", sort=False, dropna=False)
        for promotion_header_key, group in grouped:
            total_values = pd.to_numeric(group["predicted_units_total_promo"], errors="coerce").fillna(0.0)
            first7_values = pd.to_numeric(group["predicted_units_first_7_days_of_promo"], errors="coerce").fillna(0.0)
            mode_value = float(total_values.mode().iloc[0]) if not total_values.mode().empty else 0.0
            distribution_rows.append(
                {
                    "promotion_header_key": str(promotion_header_key),
                    "row_count": int(len(group.index)),
                    "unique_total_forecast_count": int(total_values.nunique(dropna=True)),
                    "modal_total_forecast_value": round(mode_value, 4),
                    "modal_total_forecast_share": round(float(total_values.eq(mode_value).mean()), 6),
                    "zero_first_7_day_share": round(float(first7_values.eq(0).mean()), 6),
                    "total_forecast_std": round(float(total_values.std(ddof=0)), 6),
                    "total_forecast_min": round(float(total_values.min()), 4),
                    "total_forecast_max": round(float(total_values.max()), 4),
                }
            )
        pd.DataFrame(distribution_rows).to_csv(forecast_distribution_path, index=False)

        forecast_json_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "forecast_health": forecast_health,
                    "forecast_source_counts": dict(frame.attrs.get("forecast_source_counts", {})),
                    "repaired_from_degenerate_count": int(
                        frame.attrs.get("forecast_repaired_count", 0)
                    ),
                    "first7_fallback_repaired_count": int(
                        frame.attrs.get("first7_fallback_repaired_count", 0)
                    ),
                    "forecast_source_priority": list(_FORECAST_SOURCE_PRIORITY),
                    "thresholds": {
                        "modal_share_threshold": FORECAST_COLLAPSE_MODAL_SHARE_THRESHOLD,
                        "min_rows": FORECAST_COLLAPSE_MIN_ROWS,
                        "zero_first_7_share_threshold": FORECAST_ZERO_FIRST7_SHARE_THRESHOLD,
                        "flat_promotion_modal_share_threshold": FORECAST_FLAT_PROMOTION_MODAL_SHARE_THRESHOLD,
                        "flat_promotion_min_rows": FORECAST_FLAT_PROMOTION_MIN_ROWS,
                    },
                    "excluded_row_counts": {
                        "null_sku": int(len(sanitization.excluded_null_sku_rows.index)),
                        "blank_product_description": int(len(sanitization.excluded_blank_product_description_rows.index)),
                        "non_numeric_suggested_order_value": int(len(sanitization.non_numeric_suggested_order_value_rows.index)),
                    },
                    "duplicate_resolution": {
                        "diagnostic_row_count": int(len(sanitization.duplicate_rows_diagnostics.index)),
                        "unresolved_row_count": int(len(sanitization.unresolved_duplicate_rows.index)),
                    },
                    "forecast_distribution_by_promotion_csv_path": str(forecast_distribution_path),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        # Write per-row source attribution diagnostics.
        forecast_per_row_path = diagnostics_root / "forecast_source_per_row.csv"
        if forecast_per_row_diagnostics is not None and not forecast_per_row_diagnostics.empty:
            forecast_per_row_diagnostics.to_csv(forecast_per_row_path, index=False)
            allocation_summary_frame = pd.DataFrame(
                [
                    {
                        "metric_name": "auto_ordered_row_count",
                        "metric_value": float(forecast_per_row_diagnostics["decision_recommendation"].astype(str).eq("ORDER").sum()),
                    },
                    {
                        "metric_name": "review_row_count",
                        "metric_value": float(forecast_per_row_diagnostics["decision_recommendation"].astype(str).eq("REVIEW").sum()),
                    },
                    {
                        "metric_name": "weak_same_discount_support_row_count",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["feature_order_risk_reason_same_discount_weak_flag"], errors="coerce").sum()),
                    },
                    {
                        "metric_name": "weak_elasticity_support_row_count",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["feature_order_risk_reason_elasticity_weak_flag"], errors="coerce").sum()),
                    },
                    {
                        "metric_name": "weak_uplift_support_row_count",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["feature_order_risk_reason_uplift_weak_flag"], errors="coerce").sum()),
                    },
                    {
                        "metric_name": "launch_vs_total_conflict_row_count",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["feature_order_risk_reason_launch_total_conflict_flag"], errors="coerce").sum()),
                    },
                    {
                        "metric_name": "review_due_to_evidence_conflict_row_count",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["order_review_escalation_due_to_evidence_conflict_flag"], errors="coerce").sum()),
                    },
                    {
                        "metric_name": "policy_adjusted_row_count",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["policy_adjustment_fired_flag"], errors="coerce").sum()),
                    },
                    {
                        "metric_name": "policy_forced_review_row_count",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["order_review_escalation_due_to_policy_flag"], errors="coerce").sum()),
                    },
                    {
                        "metric_name": "total_units_removed_by_policy",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["policy_units_removed"], errors="coerce").sum()),
                    },
                    {
                        "metric_name": "total_capital_at_risk_removed_by_policy",
                        "metric_value": float(pd.to_numeric(forecast_per_row_diagnostics["policy_capital_at_risk_removed"], errors="coerce").sum()),
                    },
                ]
            )
            allocation_summary_frame.to_csv(allocation_decision_summary_csv_path, index=False)
            allocation_decision_summary_json_path.write_text(
                json.dumps(
                    {
                        "row_count": int(len(forecast_per_row_diagnostics.index)),
                        "summary_rows": allocation_summary_frame.to_dict(orient="records"),
                        "review_escalation_reason_counts": {
                            str(reason): int(count)
                            for reason, count in forecast_per_row_diagnostics[
                                "order_review_escalation_reason_code"
                            ].astype(str).value_counts(dropna=False).to_dict().items()
                        },
                        "review_escalation_source_counts": {
                            str(source_name): int(count)
                            for source_name, count in forecast_per_row_diagnostics[
                                "order_review_escalation_source"
                            ].astype(str).value_counts(dropna=False).to_dict().items()
                        },
                        "top_policy_reasons": {
                            str(reason): int(count)
                            for reason, count in forecast_per_row_diagnostics.loc[
                                forecast_per_row_diagnostics["policy_adjustment_reason"].astype(str).ne("no_policy_adjustment"),
                                "policy_adjustment_reason",
                            ].astype(str).value_counts(dropna=False).head(10).to_dict().items()
                        },
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        else:
            pd.DataFrame(
                columns=[
                    "store_number",
                    "promotion_header_key",
                    "sku_number",
                    "forecast_source_used",
                    "forecast_source_priority_rank",
                    "forecast_repaired_flag",
                    "forecast_repair_reason",
                    "forecast_zero_before_repair_flag",
                    "forecast_zero_after_repair_flag",
                    "forecast_flat_promotion_flag",
                    "forecast_zero_demand_classification",
                    "first7_feature_raw_units",
                    "first7_fallback_raw_units",
                    "first7_fallback_candidate_flag",
                    "first7_fallback_repaired_flag",
                    "first7_fallback_reason",
                    "forecast_repair_allowed_flag",
                    "forecast_repair_rejected_reason",
                    "forecast_rounding_loss_flag",
                    "forecast_row_override_applied_flag",
                    "forecast_row_override_source",
                    "forecast_collapse_requires_review_flag",
                    "forecast_unresolved_collapse_reason",
                    "commercial_coherence_rule",
                    "commercial_contradiction_escalation_flag",
                    "true_zero_demand_retained_flag",
                    "likely_inventory_drag_flag",
                ]
            ).to_csv(forecast_per_row_path, index=False)
            pd.DataFrame(columns=["metric_name", "metric_value"]).to_csv(allocation_decision_summary_csv_path, index=False)
            allocation_decision_summary_json_path.write_text(
                json.dumps({"row_count": 0, "summary_rows": [], "review_escalation_reason_counts": {}, "review_escalation_source_counts": {}, "top_policy_reasons": {}}, indent=2, sort_keys=True),
                encoding="utf-8",
            )

        if forecast_per_row_diagnostics is not None and not forecast_per_row_diagnostics.empty:
            raw_cols = [
                "store_number",
                "promotion_header_key",
                "sku_number",
                "forecast_source_used",
                "forecast_source_raw_units",
            ]
            for raw_source_column in (
                "raw_required_implied_units",
                "raw_demand_reference_units",
                "raw_baseline_expected_units",
                "raw_predicted_units_sold",
                "raw_history_units",
            ):
                if raw_source_column in forecast_per_row_diagnostics.columns:
                    raw_cols.append(raw_source_column)
            forecast_per_row_diagnostics.loc[:, raw_cols].to_csv(forecast_source_raw_values_path, index=False)
        else:
            pd.DataFrame(
                columns=[
                    "store_number",
                    "promotion_header_key",
                    "sku_number",
                    "forecast_source_used",
                    "forecast_source_raw_units",
                    "raw_required_implied_units",
                    "raw_demand_reference_units",
                    "raw_baseline_expected_units",
                    "raw_predicted_units_sold",
                    "raw_history_units",
                ]
            ).to_csv(forecast_source_raw_values_path, index=False)

        # Write aggregate stats by source.
        forecast_aggregate_path = diagnostics_root / "forecast_source_aggregate_by_source.csv"
        if forecast_per_row_diagnostics is not None and not forecast_per_row_diagnostics.empty:
            total_rows_for_source = pd.to_numeric(
                frame["predicted_units_total_promo"], errors="coerce"
            ).fillna(0.0)
            first7_for_source = pd.to_numeric(
                frame["predicted_units_first_7_days_of_promo"], errors="coerce"
            ).fillna(0.0)
            agg_rows: list[dict[str, object]] = []
            # Merge source info from per_row_diagnostics onto the cleaned frame if possible.
            # Since indices may differ post-sanitization, aggregate from the per-row diagnostics.
            for source_name, source_group in forecast_per_row_diagnostics.groupby(
                "forecast_source_used", sort=False, dropna=False
            ):
                group_count = int(len(source_group.index))
                zero_after_share = round(
                    float(source_group["forecast_zero_after_repair_flag"].astype(bool).mean()), 6
                ) if group_count > 0 else 0.0
                agg_rows.append(
                    {
                        "forecast_source": str(source_name),
                        "row_count": group_count,
                        "zero_after_repair_share": zero_after_share,
                        "repaired_row_count": int(
                            source_group["forecast_repaired_flag"].astype(bool).sum()
                        ),
                    }
                )
            # Add global per-source stats from the output values (best effort merge by position).
            pd.DataFrame(agg_rows).to_csv(forecast_aggregate_path, index=False)
        else:
            pd.DataFrame(
                columns=["forecast_source", "row_count", "zero_after_repair_share", "repaired_row_count"]
            ).to_csv(forecast_aggregate_path, index=False)

        # Write top-20 promotions by modal-share collapse (worst flatness in output).
        top20_flat_path = diagnostics_root / "forecast_top20_flat_promotions.csv"
        distribution_df = pd.DataFrame(distribution_rows)
        if not distribution_df.empty and "modal_total_forecast_share" in distribution_df.columns:
            top20_flat = distribution_df.sort_values(
                "modal_total_forecast_share", ascending=False
            ).head(20)
        else:
            top20_flat = pd.DataFrame(
                columns=["promotion_header_key", "row_count", "modal_total_forecast_share"]
            )
        top20_flat.to_csv(top20_flat_path, index=False)

        # Write top-20 promotions by zero-share in first 7 days.
        top20_zero_first7_path = diagnostics_root / "forecast_top20_zero_first7_promotions.csv"
        if not distribution_df.empty and "zero_first_7_day_share" in distribution_df.columns:
            top20_zero = distribution_df.sort_values(
                "zero_first_7_day_share", ascending=False
            ).head(20)
        else:
            top20_zero = pd.DataFrame(
                columns=["promotion_header_key", "row_count", "zero_first_7_day_share"]
            )
        top20_zero.to_csv(top20_zero_first7_path, index=False)

        if forecast_per_row_diagnostics is not None and not forecast_per_row_diagnostics.empty:
            repaired_rows = forecast_per_row_diagnostics.loc[
                forecast_per_row_diagnostics["forecast_repaired_flag"].astype(bool)
            ].copy()
            repaired_rows.to_csv(forecast_repaired_rows_path, index=False)
            repaired_rows.to_csv(forecast_repairs_applied_path, index=False)

            true_zero_rows = forecast_per_row_diagnostics.loc[
                forecast_per_row_diagnostics["true_zero_demand_retained_flag"].astype(int).eq(1)
            ].copy()
            true_zero_rows.to_csv(true_zero_retained_rows_path, index=False)

            contradiction_rows = forecast_per_row_diagnostics.loc[
                forecast_per_row_diagnostics["commercial_contradiction_escalation_flag"].astype(int).eq(1)
            ].copy()
            contradiction_rows.to_csv(contradiction_escalations_path, index=False)

            forecast_per_row_diagnostics.to_csv(forecast_zero_demand_classification_path, index=False)

            rejected_reason_series = (
                forecast_per_row_diagnostics["forecast_repair_rejected_reason"]
                if "forecast_repair_rejected_reason" in forecast_per_row_diagnostics.columns
                else pd.Series("", index=forecast_per_row_diagnostics.index, dtype="object")
            )
            rounding_loss_series = (
                forecast_per_row_diagnostics["forecast_rounding_loss_flag"].astype(bool)
                if "forecast_rounding_loss_flag" in forecast_per_row_diagnostics.columns
                else pd.Series(False, index=forecast_per_row_diagnostics.index, dtype="bool")
            )
            classification_series = (
                forecast_per_row_diagnostics["forecast_zero_demand_classification"].astype(str)
                if "forecast_zero_demand_classification" in forecast_per_row_diagnostics.columns
                else pd.Series("", index=forecast_per_row_diagnostics.index, dtype="object")
            )
            collapse_requires_review_series = (
                forecast_per_row_diagnostics["forecast_collapse_requires_review_flag"].astype(bool)
                if "forecast_collapse_requires_review_flag" in forecast_per_row_diagnostics.columns
                else pd.Series(False, index=forecast_per_row_diagnostics.index, dtype="bool")
            )

            rejected_repairs = forecast_per_row_diagnostics.loc[
                rejected_reason_series.astype(str).str.strip().ne("")
            ].copy()
            rejected_repairs.to_csv(forecast_repairs_rejected_path, index=False)

            rounding_loss_rows = forecast_per_row_diagnostics.loc[
                rounding_loss_series
            ].copy()
            rounding_loss_rows.to_csv(forecast_rounding_loss_rows_path, index=False)

            honest_zero_rows = forecast_per_row_diagnostics.loc[
                classification_series.eq(FORECAST_ZERO_DEMAND_TRUE)
            ].copy()
            honest_zero_rows.to_csv(forecast_honest_zero_rows_path, index=False)

            low_nonzero_rows = forecast_per_row_diagnostics.loc[
                classification_series.eq(FORECAST_ZERO_DEMAND_LOW_NONZERO)
            ].copy()
            low_nonzero_rows.to_csv(forecast_low_nonzero_rows_path, index=False)

            collapse_rows = forecast_per_row_diagnostics.loc[
                classification_series.isin(
                    {
                        FORECAST_ZERO_DEMAND_COLLAPSED,
                        FORECAST_ZERO_DEMAND_COHORT_FLAT,
                        FORECAST_ZERO_DEMAND_ROUNDING,
                    }
                )
                | collapse_requires_review_series
            ].copy()
            collapse_rows.to_csv(forecast_unresolved_collapse_rows_path, index=False)
            collapse_rows.to_csv(forecast_collapse_rows_csv_path, index=False)
            collapse_rows.to_parquet(forecast_collapse_rows_parquet_path, index=False)

            demand_class_counts = (
                forecast_per_row_diagnostics.groupby("demand_evidence_class", dropna=False)
                .size()
                .rename("row_count")
                .reset_index()
                .rename(columns={"demand_evidence_class": "demand_evidence_class"})
            ) if "demand_evidence_class" in forecast_per_row_diagnostics.columns else pd.DataFrame(
                columns=["demand_evidence_class", "row_count"]
            )
            demand_class_counts.to_csv(rows_by_demand_evidence_class_path, index=False)

            if "demand_evidence_class" in forecast_per_row_diagnostics.columns:
                forecast_per_row_diagnostics.loc[
                    forecast_per_row_diagnostics["demand_evidence_class"].astype(str).eq(DEMAND_EVIDENCE_CLASS_COLD_START)
                ].copy().to_csv(cold_start_new_line_rows_path, index=False)
                forecast_per_row_diagnostics.loc[
                    forecast_per_row_diagnostics["demand_evidence_class"].astype(str).eq(DEMAND_EVIDENCE_CLASS_TRUE_ZERO)
                ].copy().to_csv(true_zero_demand_rows_path, index=False)
                forecast_per_row_diagnostics.loc[
                    forecast_per_row_diagnostics["demand_evidence_class"].astype(str).eq(DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE)
                ].copy().to_csv(artificial_collapse_rows_path, index=False)
            else:
                pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                    cold_start_new_line_rows_path,
                    index=False,
                )
                pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                    true_zero_demand_rows_path,
                    index=False,
                )
                pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                    artificial_collapse_rows_path,
                    index=False,
                )

            collapse_by_promotion = (
                collapse_rows.groupby(["promotion_header_key", "forecast_zero_demand_classification"], dropna=False)
                .size()
                .rename("row_count")
                .reset_index()
            )
            collapse_by_promotion.to_csv(forecast_collapse_by_promotion_path, index=False)

            collapse_by_source = (
                collapse_rows.groupby(["forecast_source_used", "forecast_zero_demand_classification"], dropna=False)
                .size()
                .rename("row_count")
                .reset_index()
            )
            collapse_by_source.to_csv(forecast_collapse_by_source_path, index=False)

            source_mix_rows: list[dict[str, object]] = []
            grouped_source_mix = forecast_per_row_diagnostics.groupby(
                ["promotion_header_key", "forecast_source_used"],
                sort=False,
                dropna=False,
            )
            for (promotion_header_key, source_used), group in grouped_source_mix:
                source_mix_rows.append(
                    {
                        "promotion_header_key": str(promotion_header_key),
                        "forecast_source_used": str(source_used),
                        "row_count": int(len(group.index)),
                        "repaired_row_count": int(group["forecast_repaired_flag"].astype(bool).sum()),
                    }
                )
            pd.DataFrame(source_mix_rows).to_csv(forecast_source_mix_by_promotion_path, index=False)

            output_work = frame.copy()
            output_work["first7"] = pd.to_numeric(output_work["predicted_units_first_7_days_of_promo"], errors="coerce").fillna(0.0)
            output_work["total"] = pd.to_numeric(output_work["predicted_units_total_promo"], errors="coerce").fillna(0.0)
            output_work["first7_total_ratio"] = output_work["first7"].div(output_work["total"].replace(0.0, pd.NA)).fillna(0.0)
            sanity_rows: list[dict[str, object]] = []
            grouped_sanity = output_work.groupby("promotion_header_key", sort=False, dropna=False)
            for promotion_header_key, group in grouped_sanity:
                sanity_rows.append(
                    {
                        "promotion_header_key": str(promotion_header_key),
                        "row_count": int(len(group.index)),
                        "first7_to_total_ratio_mean": round(float(group["first7_total_ratio"].mean()), 6),
                        "first7_to_total_ratio_min": round(float(group["first7_total_ratio"].min()), 6),
                        "first7_to_total_ratio_max": round(float(group["first7_total_ratio"].max()), 6),
                    }
                )
            pd.DataFrame(sanity_rows).to_csv(forecast_first7_to_total_sanity_path, index=False)

            forecast_credibility_summary_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "row_count": int(len(frame.index)),
                        "repaired_row_count": int(repaired_rows.shape[0]),
                        "first7_fallback_repaired_row_count": int(
                            forecast_per_row_diagnostics["first7_fallback_repaired_flag"].astype(bool).sum()
                        ),
                        "unrepaired_row_count": int(len(frame.index) - repaired_rows.shape[0]),
                        "true_zero_demand_retained_row_count": int(true_zero_rows.shape[0]),
                        "contradiction_escalation_row_count": int(contradiction_rows.shape[0]),
                        "source_mix_by_promotion_csv_path": str(forecast_source_mix_by_promotion_path),
                        "first7_to_total_sanity_csv_path": str(forecast_first7_to_total_sanity_path),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            stage11_fail_reasons: list[str] = []
            if bool(forecast_health.get("collapsed_prediction_flag", False)):
                stage11_fail_reasons.append("modal_prediction_share")
            if (
                int(forecast_health.get("actionable_row_count", 0)) >= FORECAST_COLLAPSE_MIN_ROWS
                and float(forecast_health.get("actionable_zero_first_7_day_share", 0.0)) >= FORECAST_ZERO_FIRST7_SHARE_THRESHOLD
            ):
                stage11_fail_reasons.append("actionable_zero_first7_share")
            if int(forecast_health.get("unresolved_flat_promotion_count", 0)) > 0:
                stage11_fail_reasons.append("flat_promotions")
            collapse_reason_counts = {
                str(reason): int(count)
                for reason, count in collapse_rows[
                    "forecast_unresolved_collapse_reason"
                ].astype(str).replace("", "unspecified").value_counts(dropna=False).to_dict().items()
            }
            rejected_reason_counts = {
                str(reason): int(count)
                for reason, count in rejected_repairs[
                    "forecast_repair_rejected_reason"
                ].astype(str).replace("", "unspecified").value_counts(dropna=False).to_dict().items()
            }
            top_unresolved_promotions = (
                collapse_rows.groupby("promotion_header_key", dropna=False)
                .size()
                .sort_values(ascending=False)
                .head(20)
            )
            top_unresolved_promotions_rows = [
                {
                    "promotion_header_key": str(key),
                    "row_count": int(count),
                }
                for key, count in top_unresolved_promotions.items()
            ]
            unresolved_promotion_count = int(
                collapse_rows["promotion_header_key"].astype(str).nunique(dropna=True)
            )
            dominant_unresolved_source = ""
            if not collapse_by_source.empty:
                dominant_unresolved_source = str(
                    collapse_by_source.sort_values("row_count", ascending=False).iloc[0]["forecast_source_used"]
                )
            forecast_stage11_outcome_summary_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "stage11_will_fail": bool(stage11_fail_reasons),
                        "stage11_fail_reasons": stage11_fail_reasons,
                        "forecast_health": forecast_health,
                        "repair_rows_applied": int(repaired_rows.shape[0]),
                        "repair_rows_rejected": int(rejected_repairs.shape[0]),
                        "repair_rejected_reason_counts": rejected_reason_counts,
                        "collapse_rows": int(collapse_rows.shape[0]),
                        "unresolved_promotion_count": unresolved_promotion_count,
                        "dominant_unresolved_collapse_source": dominant_unresolved_source,
                        "unresolved_collapse_reason_counts": collapse_reason_counts,
                        "top_unresolved_promotions": top_unresolved_promotions_rows,
                        "honest_zero_rows": int(honest_zero_rows.shape[0]),
                        "low_nonzero_rows": int(low_nonzero_rows.shape[0]),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        else:
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_repaired_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_repairs_applied_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                true_zero_retained_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                contradiction_escalations_path,
                index=False,
            )
            pd.DataFrame(
                columns=["promotion_header_key", "forecast_source_used", "row_count", "repaired_row_count"]
            ).to_csv(forecast_source_mix_by_promotion_path, index=False)
            pd.DataFrame(
                columns=[
                    "promotion_header_key",
                    "row_count",
                    "first7_to_total_ratio_mean",
                    "first7_to_total_ratio_min",
                    "first7_to_total_ratio_max",
                ]
            ).to_csv(forecast_first7_to_total_sanity_path, index=False)
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_zero_demand_classification_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_repairs_rejected_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_rounding_loss_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_honest_zero_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_low_nonzero_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_unresolved_collapse_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["demand_evidence_class", "row_count"]).to_csv(
                rows_by_demand_evidence_class_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                cold_start_new_line_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                true_zero_demand_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                artificial_collapse_rows_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_csv(
                forecast_collapse_rows_csv_path,
                index=False,
            )
            pd.DataFrame(columns=["store_number", "promotion_header_key", "sku_number"]).to_parquet(
                forecast_collapse_rows_parquet_path,
                index=False,
            )
            pd.DataFrame(columns=["promotion_header_key", "forecast_zero_demand_classification", "row_count"]).to_csv(
                forecast_collapse_by_promotion_path,
                index=False,
            )
            pd.DataFrame(columns=["forecast_source_used", "forecast_zero_demand_classification", "row_count"]).to_csv(
                forecast_collapse_by_source_path,
                index=False,
            )
            forecast_credibility_summary_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "row_count": int(len(frame.index)),
                        "repaired_row_count": 0,
                        "first7_fallback_repaired_row_count": 0,
                        "unrepaired_row_count": int(len(frame.index)),
                        "true_zero_demand_retained_row_count": 0,
                        "contradiction_escalation_row_count": 0,
                        "source_mix_by_promotion_csv_path": str(forecast_source_mix_by_promotion_path),
                        "first7_to_total_sanity_csv_path": str(forecast_first7_to_total_sanity_path),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            forecast_stage11_outcome_summary_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "stage11_will_fail": False,
                        "stage11_fail_reasons": [],
                        "forecast_health": forecast_health,
                        "repair_rows_applied": 0,
                        "repair_rows_rejected": 0,
                        "repair_rejected_reason_counts": {},
                        "collapse_rows": 0,
                        "unresolved_promotion_count": 0,
                        "dominant_unresolved_collapse_source": "",
                        "unresolved_collapse_reason_counts": {},
                        "top_unresolved_promotions": [],
                        "honest_zero_rows": 0,
                        "low_nonzero_rows": 0,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

        return {
            "excluded_null_sku_rows_csv_path": str(null_sku_path),
            "excluded_blank_product_description_rows_csv_path": str(blank_description_path),
            "duplicate_store_promotion_sku_rows_csv_path": str(duplicate_rows_path),
            "non_numeric_suggested_order_value_rows_csv_path": str(non_numeric_value_path),
            "allocation_decision_summary_csv_path": str(allocation_decision_summary_csv_path),
            "allocation_decision_summary_json_path": str(allocation_decision_summary_json_path),
            "forecast_collapse_diagnostics_json_path": str(forecast_json_path),
            "forecast_distribution_by_promotion_csv_path": str(forecast_distribution_path),
            "forecast_source_per_row_csv_path": str(forecast_per_row_path),
            "forecast_source_raw_values_per_row_csv_path": str(forecast_source_raw_values_path),
            "forecast_source_aggregate_by_source_csv_path": str(forecast_aggregate_path),
            "forecast_top20_flat_promotions_csv_path": str(top20_flat_path),
            "forecast_top20_zero_first7_promotions_csv_path": str(top20_zero_first7_path),
            "forecast_repaired_rows_csv_path": str(forecast_repaired_rows_path),
            "true_zero_demand_retained_rows_csv_path": str(true_zero_retained_rows_path),
            "commercial_contradiction_repairs_or_escalations_csv_path": str(contradiction_escalations_path),
            "forecast_source_mix_by_promotion_csv_path": str(forecast_source_mix_by_promotion_path),
            "forecast_first7_to_total_sanity_csv_path": str(forecast_first7_to_total_sanity_path),
            "forecast_credibility_summary_json_path": str(forecast_credibility_summary_path),
            "forecast_collapse_rows_csv_path": str(forecast_collapse_rows_csv_path),
            "forecast_collapse_rows_parquet_path": str(forecast_collapse_rows_parquet_path),
            "forecast_collapse_by_promotion_csv_path": str(forecast_collapse_by_promotion_path),
            "forecast_collapse_by_source_csv_path": str(forecast_collapse_by_source_path),
            "forecast_zero_demand_classification_csv_path": str(forecast_zero_demand_classification_path),
            "forecast_repairs_applied_csv_path": str(forecast_repairs_applied_path),
            "forecast_repairs_rejected_csv_path": str(forecast_repairs_rejected_path),
            "forecast_rounding_loss_rows_csv_path": str(forecast_rounding_loss_rows_path),
            "forecast_honest_zero_rows_csv_path": str(forecast_honest_zero_rows_path),
            "forecast_low_nonzero_rows_csv_path": str(forecast_low_nonzero_rows_path),
            "forecast_unresolved_collapse_rows_csv_path": str(forecast_unresolved_collapse_rows_path),
            "forecast_stage11_outcome_summary_json_path": str(forecast_stage11_outcome_summary_path),
            "rows_by_demand_evidence_class_csv_path": str(rows_by_demand_evidence_class_path),
            "cold_start_new_line_rows_csv_path": str(cold_start_new_line_rows_path),
            "true_zero_demand_rows_csv_path": str(true_zero_demand_rows_path),
            "artificial_collapse_rows_csv_path": str(artificial_collapse_rows_path),
        }

    def _sort_download_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        sort_frame = frame.copy()
        sort_frame["_sort_store"] = _sortable_text(sort_frame["store_number"])
        sort_frame["_sort_promotion_start"] = _sortable_text(sort_frame["promotion_start_date"])
        sort_frame["_sort_promotion_key"] = _sortable_text(sort_frame["promotion_header_key"])
        sort_frame["_sort_sku"] = _sortable_text(sort_frame["sku_number"])
        sort_frame = sort_frame.sort_values(
            by=[
                "_sort_store",
                "_sort_promotion_start",
                "_sort_promotion_key",
                "suggested_order_units",
                "_sort_sku",
            ],
            ascending=[True, True, True, False, True],
            kind="mergesort",
        )
        return sort_frame.drop(
            columns=[
                "_sort_store",
                "_sort_promotion_start",
                "_sort_promotion_key",
                "_sort_sku",
            ]
        ).reset_index(drop=True)

    def _write_per_store_csvs(
        self,
        *,
        run_id: str,
        as_of_date: str,
        frame: pd.DataFrame,
        artifact_paths: PromotionArtifactPaths,
        generated_file_rows: list[dict[str, object]],
        forecast_per_row_diagnostics: pd.DataFrame | None = None,
        completed_backtest_summary: dict[str, object] | None = None,
        sku_backtest_summary: pd.DataFrame | None = None,
    ) -> list[str]:
        paths: list[str] = []
        for store_number, group in frame.groupby("store_number", dropna=False, sort=False):
            store_token = _sanitize_filename_component(str(store_number), fallback="unknown_store")
            store_facing_group = self._store_facing_projection(
                group,
                forecast_per_row_diagnostics=forecast_per_row_diagnostics,
                as_of_date=as_of_date,
                completed_backtest_summary=completed_backtest_summary,
                sku_backtest_summary=sku_backtest_summary,
            )
            store_output_frame = _project_store_facing_output_columns(store_facing_group)
            path = artifact_paths.store_prediction_store_csv_path(
                run_id=run_id,
                as_of_date=as_of_date,
                store_number=store_token,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            store_output_frame.to_csv(path, index=False)
            paths.append(str(path))
            generated_file_rows.append(
                _build_file_manifest_row(
                    run_id=run_id,
                    as_of_date=as_of_date,
                    file_type="store_predictions",
                    file_path=str(path),
                    frame=store_output_frame,
                    store_number=store_number,
                )
            )
        return paths

    def _write_per_store_promotion_csvs(
        self,
        *,
        run_id: str,
        as_of_date: str,
        frame: pd.DataFrame,
        artifact_paths: PromotionArtifactPaths,
        generated_file_rows: list[dict[str, object]],
        feature_inspection_source_frame: pd.DataFrame | None = None,
        forecast_per_row_diagnostics: pd.DataFrame | None = None,
        completed_backtest_summary: dict[str, object] | None = None,
        sku_backtest_summary: pd.DataFrame | None = None,
    ) -> list[str]:
        """Write per-promotion store artifacts and their inspection siblings.

        Purpose:
            Materialize the store-facing per-promotion CSV, manager summary, and
            feature-inspection sibling for each store/promotion group.

        Inputs:
            run_id: execution identifier.
            as_of_date: governed run date.
            frame: sorted governed commercial frame used for Stage 11 outputs.
            artifact_paths: artifact path resolver.
            generated_file_rows: mutable manifest accumulator.
            feature_inspection_source_frame: optional raw decision-surface frame
                retained only for inspection-side feature joins.
            forecast_per_row_diagnostics: optional row diagnostics.
            completed_backtest_summary: optional completed-promo summary payload.
            sku_backtest_summary: optional per-SKU backtest summary frame.

        Outputs:
            The ordered list of written per-promotion CSV paths.

        Important assumptions:
            The feature-inspection sibling may include more upstream columns than
            the governed master CSV, but store-facing commercial outputs must not
            widen.

        Side effects:
            Writes CSV artifacts and appends manifest rows.
        """

        paths: list[str] = []
        prepared_feature_source = _prepare_feature_inspection_source_frame(feature_inspection_source_frame)
        grouped = list(frame.groupby(["store_number", "promotion_header_key"], dropna=False, sort=False))
        base_paths: list[str] = []
        for (store_number, _), group in grouped:
            base_paths.append(
                str(
                    artifact_paths.store_prediction_store_promotion_csv_path(
                        run_id=run_id,
                        store_number=str(store_number),
                        promotion_start_date=_first_value(group["promotion_start_date"]),
                        promotion_name=_first_value(group["promotion_name"]),
                    )
                )
            )
        path_counts = Counter(base_paths)
        for ((store_number, promotion_header_key), group), base_path in zip(grouped, base_paths, strict=False):
            collision_key = str(promotion_header_key) if path_counts[base_path] > 1 else None
            path = artifact_paths.store_prediction_store_promotion_csv_path(
                run_id=run_id,
                store_number=str(store_number),
                promotion_start_date=_first_value(group["promotion_start_date"]),
                promotion_name=_first_value(group["promotion_name"]),
                collision_key=collision_key,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            store_facing_group = self._store_facing_projection(
                group,
                forecast_per_row_diagnostics=forecast_per_row_diagnostics,
                as_of_date=as_of_date,
                completed_backtest_summary=completed_backtest_summary,
                sku_backtest_summary=sku_backtest_summary,
            )
            store_output_frame = _project_store_facing_output_columns(store_facing_group)
            store_output_frame.to_csv(path, index=False)
            paths.append(str(path))
            generated_file_rows.append(
                _build_file_manifest_row(
                    run_id=run_id,
                    as_of_date=as_of_date,
                    file_type="store_promotion",
                    file_path=str(path),
                    frame=store_output_frame,
                    store_number=store_number,
                    promotion_header_key=promotion_header_key,
                )
            )
            audit_path = artifact_paths.store_prediction_store_promotion_artifact_path(
                run_id=run_id,
                store_number=str(store_number),
                promotion_start_date=_first_value(group["promotion_start_date"]),
                promotion_name=_first_value(group["promotion_name"]),
                artifact_name="operator_audit",
                extension="csv",
                collision_key=collision_key,
            )
            audit_frame = _project_store_facing_audit_columns(store_facing_group)
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_frame.to_csv(audit_path, index=False)
            generated_file_rows.append(
                _build_file_manifest_row(
                    run_id=run_id,
                    as_of_date=as_of_date,
                    file_type="store_promotion_operator_audit",
                    file_path=str(audit_path),
                    frame=audit_frame,
                    store_number=store_number,
                    promotion_header_key=promotion_header_key,
                )
            )
            summary_path = artifact_paths.store_prediction_store_promotion_artifact_path(
                run_id=run_id,
                store_number=str(store_number),
                promotion_start_date=_first_value(group["promotion_start_date"]),
                promotion_name=_first_value(group["promotion_name"]),
                artifact_name="manager_summary",
                extension="csv",
                collision_key=collision_key,
            )
            summary_frame = _build_store_promotion_manager_summary_frame(
                store_facing_frame=store_facing_group,
                store_number=str(store_number),
                promotion_name=_first_value(group["promotion_name"]),
                promotion_start_date=_first_value(group["promotion_start_date"]),
                promotion_end_date=_first_value(group["promotion_end_date"]),
            )
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_frame.to_csv(summary_path, index=False)
            generated_file_rows.append(
                _build_file_manifest_row(
                    run_id=run_id,
                    as_of_date=as_of_date,
                    file_type="store_promotion_manager_summary",
                    file_path=str(summary_path),
                    frame=summary_frame,
                    store_number=store_number,
                    promotion_header_key=promotion_header_key,
                )
            )

            # Feature-inspection sibling: full intermediate store-facing
            # frame (all sort/diagnostic/priority fields) joined with the
            # upstream model `feature_*` and raw decision-score columns
            # from the original decision surface for the same rows. Analysts use
            # this file to audit why an SKU received its action; store
            # operators ignore it.
            feature_inspection_path = artifact_paths.store_prediction_store_promotion_artifact_path(
                run_id=run_id,
                store_number=str(store_number),
                promotion_start_date=_first_value(group["promotion_start_date"]),
                promotion_name=_first_value(group["promotion_name"]),
                artifact_name="feature_inspection",
                extension="csv",
                collision_key=collision_key,
            )
            inspection_source_group = group
            if prepared_feature_source is not None:
                inspection_source_group = prepared_feature_source.loc[
                    prepared_feature_source["store_number"].astype(str).eq(str(store_number))
                    & prepared_feature_source["promotion_header_key"].astype(str).eq(str(promotion_header_key))
                ].copy()
            upstream_feature_columns = [
                column
                for column in inspection_source_group.columns
                if column.startswith("feature_")
                or column
                in (
                    "final_decision_score",
                    "final_confidence_score",
                    "row_cohort_disagreement_score",
                    "margin_risk_penalty",
                    "leftover_risk_penalty",
                    "stockout_risk_penalty",
                    "promotion_header_key",
                    "promotion_row_key",
                    "demand_evidence_class",
                    "demand_confidence_band",
                    "stockout_risk_flag",
                    "overstock_risk_flag",
                    "predicted_units_total_promo",
                    "predicted_units_first_7_days_of_promo",
                    "predicted_units_until_promo_start",
                    "expected_leftover_units_end_of_promo",
                )
            ]
            if prepared_feature_source is not None and upstream_feature_columns:
                resolved_row_keys = _resolve_feature_inspection_row_key_frame(inspection_source_group)
                if not resolved_row_keys.empty:
                    merge_base = store_facing_group.copy()
                    merge_base["_feature_join_store"] = merge_base["store_number"].astype(str)
                    merge_base["_feature_join_sku"] = merge_base["sku_number"].astype(str)
                    resolved_row_keys = resolved_row_keys.copy()
                    resolved_row_keys["_feature_join_store"] = resolved_row_keys["store_number"].astype(str)
                    resolved_row_keys["_feature_join_sku"] = resolved_row_keys["sku_number"].astype(str)
                    merge_base = merge_base.merge(
                        resolved_row_keys.loc[:, ["_feature_join_store", "_feature_join_sku", "promotion_row_key"]],
                        on=["_feature_join_store", "_feature_join_sku"],
                        how="left",
                        sort=False,
                    )
                    if merge_base["promotion_row_key"].notna().all():
                        merge_base["promotion_row_key"] = merge_base["promotion_row_key"].astype(str)
                        row_key_upstream_columns = [
                            column_name
                            for column_name in upstream_feature_columns
                            if column_name != "promotion_row_key"
                        ]
                        upstream_subset = inspection_source_group.loc[:, ["promotion_row_key", *row_key_upstream_columns]].copy()
                        upstream_subset["promotion_row_key"] = upstream_subset["promotion_row_key"].astype(str)
                        upstream_subset = upstream_subset.drop_duplicates(subset=["promotion_row_key"], keep="last")
                        feature_inspection_frame = merge_base.merge(
                            upstream_subset,
                            on=["promotion_row_key"],
                            how="left",
                            sort=False,
                        ).drop(columns=["_feature_join_store", "_feature_join_sku"])
                    else:
                        feature_inspection_frame = _merge_feature_inspection_on_store_sku(
                            store_facing_group=store_facing_group,
                            inspection_source_group=inspection_source_group,
                            upstream_feature_columns=upstream_feature_columns,
                        )
                else:
                    feature_inspection_frame = _merge_feature_inspection_on_store_sku(
                        store_facing_group=store_facing_group,
                        inspection_source_group=inspection_source_group,
                        upstream_feature_columns=upstream_feature_columns,
                    )
            else:
                upstream_subset = (
                    inspection_source_group.loc[:, upstream_feature_columns]
                    .reset_index(drop=True)
                    if upstream_feature_columns
                    else pd.DataFrame(index=range(len(store_facing_group.index)))
                )
                feature_inspection_frame = pd.concat(
                    [store_facing_group.reset_index(drop=True), upstream_subset],
                    axis=1,
                )
            # Drop duplicate columns that may appear in both frames
            feature_inspection_frame = feature_inspection_frame.loc[
                :, ~feature_inspection_frame.columns.duplicated()
            ]
            feature_inspection_path.parent.mkdir(parents=True, exist_ok=True)
            feature_inspection_frame.to_csv(feature_inspection_path, index=False)
            generated_file_rows.append(
                _build_file_manifest_row(
                    run_id=run_id,
                    as_of_date=as_of_date,
                    file_type="store_promotion_feature_inspection",
                    file_path=str(feature_inspection_path),
                    frame=feature_inspection_frame,
                    store_number=store_number,
                    promotion_header_key=promotion_header_key,
                )
            )
        return paths

    def _store_facing_projection(
        self,
        frame: pd.DataFrame,
        *,
        forecast_per_row_diagnostics: pd.DataFrame | None = None,
        as_of_date: str | None = None,
        completed_backtest_summary: dict[str, object] | None = None,
        sku_backtest_summary: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        return _build_store_facing_frame(
            commercial_frame=frame,
            forecast_per_row_diagnostics=forecast_per_row_diagnostics,
            as_of_date=as_of_date,
            completed_backtest_summary=completed_backtest_summary,
            sku_backtest_summary=sku_backtest_summary,
        )

    def _promotion_group_diagnostic_summary(self, frame: pd.DataFrame) -> pd.DataFrame:
        grouped = frame.groupby(["store_number", "promotion_header_key"], dropna=False, sort=False)
        rows: list[dict[str, object]] = []
        for (_, _), group in grouped:
            rows.append(
                {
                    "store_number": _first_value(group["store_number"]),
                    "promotion_header_key": _first_value(group["promotion_header_key"]),
                    "promotion_name": _first_value(group["promotion_name"]),
                    "promotion_start_date": _first_value(group["promotion_start_date"]),
                    "promotion_end_date": _first_value(group["promotion_end_date"]),
                    "row_count": int(len(group.index)),
                    "unique_sku_count": int(group["sku_number"].astype(str).nunique(dropna=True)),
                }
            )
        return pd.DataFrame(rows)

    def _validate_store_promotion_grouping(
        self,
        *,
        frame: pd.DataFrame,
        diagnostic_summary: pd.DataFrame,
        artifact_paths: PromotionArtifactPaths,
        run_id: str,
    ) -> None:
        grouped = frame.groupby(["store_number", "promotion_header_key"], dropna=False, sort=False)
        validation_failures: list[dict[str, object]] = []
        # Exclude rows with null sku_number before duplicate detection: two null-SKU rows in
        # the same group are not actionable duplicates — they are upstream data-quality gaps.
        # True duplicate SKUs (same non-null sku_number appearing twice) still trigger failure.
        null_sku_row_count = int(frame["sku_number"].isna().sum())
        frame_with_sku = frame[frame["sku_number"].notna()]
        duplicate_count = int(
            frame_with_sku.duplicated(subset=["store_number", "promotion_header_key", "sku_number"], keep=False).sum()
        )
        if duplicate_count > 0:
            validation_failures.append(
                {
                    "store_number": "*",
                    "promotion_header_key": "*",
                    "reason": "duplicate store_number + promotion_header_key + sku_number rows detected",
                    "duplicate_row_count": duplicate_count,
                }
            )

        for (store_number, promotion_header_key), group in grouped:
            if group["store_number"].nunique(dropna=False) != 1:
                validation_failures.append(
                    {
                        "store_number": str(store_number),
                        "promotion_header_key": str(promotion_header_key),
                        "reason": "group contains multiple store_number values",
                    }
                )
            if group["promotion_header_key"].nunique(dropna=False) != 1:
                validation_failures.append(
                    {
                        "store_number": str(store_number),
                        "promotion_header_key": str(promotion_header_key),
                        "reason": "group contains multiple promotion_header_key values",
                    }
                )
            unique_sku_count = int(group["sku_number"].astype(str).nunique(dropna=True))
            if unique_sku_count <= 2:
                logical_header_mask = (
                    frame["store_number"].astype(str).eq(str(store_number))
                    & frame["promotion_name"].eq(_first_value(group["promotion_name"]))
                    & frame["promotion_start_date"].eq(_first_value(group["promotion_start_date"]))
                    & frame["promotion_end_date"].eq(_first_value(group["promotion_end_date"]))
                )
                logical_header_rows = int(logical_header_mask.sum())
                if logical_header_rows > int(len(group.index)):
                    validation_failures.append(
                        {
                            "store_number": str(store_number),
                            "promotion_header_key": str(promotion_header_key),
                            "reason": "group appears fragmented: low sku count while same logical promotion header has additional rows",
                            "group_row_count": int(len(group.index)),
                            "logical_header_row_count": logical_header_rows,
                        }
                    )

        if validation_failures:
            failure_path = artifact_paths.store_prediction_grouping_validation_failures_path(run_id)
            failure_csv_path = artifact_paths.store_prediction_validation_root(run_id) / "store_prediction_download_grouping_validation_failures.csv"
            failure_parquet_path = artifact_paths.store_prediction_validation_root(run_id) / "store_prediction_download_grouping_validation_failures.parquet"
            failure_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(validation_failures).to_csv(failure_csv_path, index=False)
            pd.DataFrame(validation_failures).to_parquet(failure_parquet_path, index=False)
            failure_path.write_text(
                json.dumps(
                    {
                        "reason": "store promotion grouping validation failed",
                        "null_sku_row_count": null_sku_row_count,
                        "failures": validation_failures,
                        "failure_csv_path": str(failure_csv_path),
                        "failure_parquet_path": str(failure_parquet_path),
                        "diagnostic_summary": diagnostic_summary.to_dict(orient="records"),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            raise PromotionStoreDownloadGroupingValidationError(
                "Store promotion grouping validation failed; see "
                f"{failure_path} for details."
            )

    def _build_reconciliation_frame(
        self,
        *,
        source_frame: pd.DataFrame,
        output_frame: pd.DataFrame,
    ) -> pd.DataFrame:
        source_work = source_frame.copy()
        source_work["store_number"] = _raw_series(source_work, ("store_number",)).astype(str)
        source_work["promotion_header_key"] = _build_promotion_header_key_series(
            promotion_id=_raw_series(source_work, ("promotion_id", "promotional_sku_id", "promotional_sku_id_key")),
            promotion_name=_text_series(source_work, ("promotion_name",)),
            promotion_start_date=_date_series(source_work, ("promotion_start_date_date", "promotion_start_date")),
            promotion_end_date=_date_series(source_work, ("promotional_end_date_date", "promotional_end_date")),
            promo_type=_text_series(source_work, ("promo_type",)),
        )
        source_work["sku_number"] = _raw_series(source_work, ("sku_number",)).astype(str)

        rows: list[dict[str, object]] = []
        grouped_source = source_work.groupby(["store_number", "promotion_header_key"], sort=False, dropna=False)
        for (store_number, promotion_header_key), source_group in grouped_source:
            output_group = output_frame.loc[
                output_frame["store_number"].astype(str).eq(str(store_number))
                & output_frame["promotion_header_key"].astype(str).eq(str(promotion_header_key))
            ]
            source_row_count = int(len(source_group.index))
            output_row_count = int(len(output_group.index))
            source_sku_count = int(source_group["sku_number"].nunique(dropna=True))
            output_sku_count = int(output_group["sku_number"].astype(str).nunique(dropna=True))
            action_counts = output_group["decision_recommendation"].astype(str).value_counts(dropna=False).to_dict()
            duplicate_row_count = int(
                output_group[output_group["sku_number"].notna()].duplicated(subset=["store_number", "promotion_header_key", "sku_number"]).sum()
            )
            missing_row_count = max(source_row_count - output_row_count, 0)
            status = "PASS"
            reason = "counts_match"
            if duplicate_row_count > 0:
                status = "FAIL"
                reason = "duplicate_rows_in_output"
            elif source_row_count != output_row_count or source_sku_count != output_sku_count:
                status = "FAIL"
                reason = "source_output_count_mismatch"

            rows.append(
                {
                    "store_number": str(store_number),
                    "promotion_header_key": str(promotion_header_key),
                    "source_row_count": source_row_count,
                    "output_row_count": output_row_count,
                    "source_sku_count": source_sku_count,
                    "output_sku_count": output_sku_count,
                    "order_row_count": int(action_counts.get("ORDER", 0)),
                    "hold_row_count": int(action_counts.get("HOLD", 0)),
                    "review_row_count": int(action_counts.get("REVIEW", 0)),
                    "do_not_order_row_count": int(action_counts.get("DO_NOT_ORDER", 0)),
                    "monitor_row_count": int(action_counts.get("MONITOR", 0)),
                    "missing_row_count": missing_row_count,
                    "duplicate_row_count": duplicate_row_count,
                    "status": status,
                    "reason": reason,
                }
            )
        return pd.DataFrame(rows)

    def _build_totals(self, frame: pd.DataFrame) -> dict[str, int]:
        return {
            "total_rows": int(len(frame.index)),
            "review_required_row_count": int((frame["decision_recommendation"] == "REVIEW").sum()),
            "order_row_count": int((frame["decision_recommendation"] == "ORDER").sum()),
            "hold_row_count": int((frame["decision_recommendation"] == "HOLD").sum()),
            "do_not_order_row_count": int((frame["decision_recommendation"] == "DO_NOT_ORDER").sum()),
            "review_row_count": int((frame["decision_recommendation"] == "REVIEW").sum()),
            "monitor_row_count": 0,
        }

    def _forecast_health_summary(
        self,
        frame: pd.DataFrame,
        *,
        forecast_per_row_diagnostics: pd.DataFrame | None = None,
    ) -> dict[str, object]:
        values = pd.to_numeric(frame["predicted_units_total_promo"], errors="coerce").fillna(0.0)
        first7_values = pd.to_numeric(frame["predicted_units_first_7_days_of_promo"], errors="coerce").fillna(0.0)
        row_count = int(len(values.index))
        if row_count == 0:
            return {
                "row_count": 0,
                "unique_prediction_count": 0,
                "modal_prediction_value": 0.0,
                "modal_prediction_share": 0.0,
                "zero_first_7_day_share": 0.0,
                "prediction_std": 0.0,
                "collapsed_prediction_flag": False,
                "flat_promotion_count": 0,
                "flat_promotions": [],
                "actionable_row_count": 0,
                "actionable_modal_prediction_share": 0.0,
                "actionable_zero_first_7_day_share": 0.0,
                "unresolved_collapse_row_count": 0,
                "unresolved_collapse_share": 0.0,
                "unresolved_classification_counts": {},
                "unresolved_actionable_promotion_count": 0,
                "mixed_unresolved_promotion_count": 0,
                "unresolved_promotion_count": 0,
                "unresolved_flat_promotion_count": 0,
                "unresolved_flat_promotions": [],
                "cohort_flat_only_promotion_count": 0,
                "cohort_flat_only_promotions": [],
            }
        mode_value = float(values.mode().iloc[0]) if not values.mode().empty else 0.0
        modal_share = float(values.eq(mode_value).mean())
        zero_first_7_day_share = float(first7_values.eq(0).mean())
        classification_map: dict[tuple[str, str, str], str] = {}
        def _canonical_key_token(value: object) -> str:
            if pd.isna(value):
                return ""
            text = str(value).strip()
            if text.lower() in {"", "nan", "none", "<na>"}:
                return ""
            if re.fullmatch(r"\d+\.0+", text):
                return text.split(".", 1)[0]
            return text

        if forecast_per_row_diagnostics is not None and not forecast_per_row_diagnostics.empty:
            key_cols = ["store_number", "promotion_header_key", "sku_number", "forecast_zero_demand_classification"]
            available = [col for col in key_cols if col in forecast_per_row_diagnostics.columns]
            if len(available) == 4:
                keyed = forecast_per_row_diagnostics.loc[:, available].copy()
                for key_row in keyed.itertuples(index=False):
                    classification_map[
                        (
                            _canonical_key_token(key_row[0]),
                            _canonical_key_token(key_row[1]),
                            _canonical_key_token(key_row[2]),
                        )
                    ] = str(key_row[3])

        class_series = pd.Series(
            [FORECAST_ZERO_DEMAND_HEALTHY] * row_count,
            index=frame.index,
            dtype="object",
        )
        if classification_map:
            classifications = [
                classification_map.get(
                    (
                        _canonical_key_token(store),
                        _canonical_key_token(promo),
                        _canonical_key_token(sku),
                    ),
                    FORECAST_ZERO_DEMAND_HEALTHY,
                )
                for store, promo, sku in zip(
                    frame["store_number"].astype(str).tolist(),
                    frame["promotion_header_key"].astype(str).tolist(),
                    frame["sku_number"].astype(str).tolist(),
                    strict=False,
                )
            ]
            class_series = pd.Series(classifications, index=frame.index, dtype="object")

        false_first7_zero_mask = first7_values.eq(0) & values.gt(0)
        actionable_row_mask = (~class_series.isin(FORECAST_BENIGN_ZERO_CLASSES)) | false_first7_zero_mask

        actionable_row_count = int(actionable_row_mask.sum())
        if actionable_row_count > 0:
            actionable_values = values[actionable_row_mask]
            actionable_mode = (
                float(actionable_values.mode().iloc[0]) if not actionable_values.mode().empty else 0.0
            )
            actionable_modal_prediction_share = float(actionable_values.eq(actionable_mode).mean())
            actionable_zero_first_7_day_share = float(
                first7_values[actionable_row_mask].eq(0).mean()
            )
        else:
            actionable_modal_prediction_share = 0.0
            actionable_zero_first_7_day_share = 0.0

        flat_promotions: list[dict[str, object]] = []
        grouped = frame.groupby("promotion_header_key", sort=False, dropna=False)
        for promotion_header_key, group in grouped:
            group_values = pd.to_numeric(group["predicted_units_total_promo"], errors="coerce").fillna(0.0)
            group_first7_values = pd.to_numeric(
                group["predicted_units_first_7_days_of_promo"],
                errors="coerce",
            ).fillna(0.0)
            group_classifications = class_series.loc[group.index]
            group_false_first7_zero_mask = group_first7_values.eq(0) & group_values.gt(0)
            group_actionable_mask = (
                ~group_classifications.isin(FORECAST_BENIGN_ZERO_CLASSES)
            ) | group_false_first7_zero_mask
            group_actionable_values = group_values[group_actionable_mask]
            if len(group_actionable_values.index) < FORECAST_FLAT_PROMOTION_MIN_ROWS:
                continue
            group_mode = (
                float(group_actionable_values.mode().iloc[0])
                if not group_actionable_values.mode().empty
                else 0.0
            )
            group_modal_share = float(group_actionable_values.eq(group_mode).mean())

            if group_modal_share >= FORECAST_FLAT_PROMOTION_MODAL_SHARE_THRESHOLD:
                flat_promotions.append(
                    {
                        "promotion_header_key": str(promotion_header_key),
                        "row_count": int(len(group_actionable_values.index)),
                        "modal_prediction_value": round(group_mode, 4),
                        "modal_prediction_share": round(group_modal_share, 6),
                    }
                )
        unresolved_mask = class_series.isin(FORECAST_UNRESOLVED_COLLAPSE_CLASSES)
        unresolved_collapse_row_count = int(unresolved_mask.sum())
        unresolved_collapse_share = float(unresolved_collapse_row_count / row_count)
        unresolved_classification_counts = {
            str(name): int(count)
            for name, count in class_series[unresolved_mask].value_counts(dropna=False).to_dict().items()
        }
        unresolved_promotion_count = int(
            frame.loc[unresolved_mask, "promotion_header_key"].astype(str).nunique(dropna=True)
        )
        unresolved_flat_promotions: list[dict[str, object]] = []
        cohort_flat_only_promotions: list[dict[str, object]] = []
        unresolved_actionable_promotion_count = 0
        mixed_unresolved_promotion_count = 0
        for promotion_header_key, group in grouped:
            group_values = pd.to_numeric(group["predicted_units_total_promo"], errors="coerce").fillna(0.0)
            group_first7_values = pd.to_numeric(
                group["predicted_units_first_7_days_of_promo"],
                errors="coerce",
            ).fillna(0.0)
            group_classifications = class_series.loc[group.index]
            group_unresolved_mask = group_classifications.isin(FORECAST_UNRESOLVED_COLLAPSE_CLASSES)
            group_blocking_unresolved_mask = group_classifications.isin(
                _FORECAST_BLOCKING_UNRESOLVED_FLAT_CLASSES
            )
            group_false_first7_zero_mask = group_first7_values.eq(0) & group_values.gt(0)
            group_actionable_row_count = int(
                ((~group_classifications.isin(FORECAST_BENIGN_ZERO_CLASSES)) | group_false_first7_zero_mask).sum()
            )
            group_unresolved_row_count = int(group_unresolved_mask.sum())
            if group_unresolved_row_count > 0 and group_unresolved_row_count < group_actionable_row_count:
                mixed_unresolved_promotion_count += 1
                continue
            if group_unresolved_row_count == 0:
                continue
            group_blocking_unresolved_row_count = int(group_blocking_unresolved_mask.sum())
            if group_blocking_unresolved_row_count == 0:
                cohort_flat_only_promotions.append(
                    {
                        "promotion_header_key": str(promotion_header_key),
                        "row_count": group_unresolved_row_count,
                    }
                )
                continue
            group_unresolved_values = group_values[group_blocking_unresolved_mask]
            if group_blocking_unresolved_row_count < FORECAST_FLAT_PROMOTION_MIN_ROWS:
                continue
            group_mode = (
                float(group_unresolved_values.mode().iloc[0])
                if not group_unresolved_values.mode().empty
                else 0.0
            )
            group_modal_share = float(group_unresolved_values.eq(group_mode).mean())
            if group_modal_share >= FORECAST_FLAT_PROMOTION_MODAL_SHARE_THRESHOLD:
                unresolved_actionable_promotion_count += 1
                unresolved_flat_promotions.append(
                    {
                        "promotion_header_key": str(promotion_header_key),
                        "row_count": int(len(group_unresolved_values.index)),
                        "modal_prediction_value": round(group_mode, 4),
                        "modal_prediction_share": round(group_modal_share, 6),
                    }
                )

        collapsed = (
            actionable_row_count >= FORECAST_COLLAPSE_MIN_ROWS
            and actionable_modal_prediction_share >= FORECAST_COLLAPSE_MODAL_SHARE_THRESHOLD
        )
        return {
            "row_count": row_count,
            "unique_prediction_count": int(values.nunique(dropna=True)),
            "modal_prediction_value": round(mode_value, 4),
            "modal_prediction_share": round(modal_share, 6),
            "zero_first_7_day_share": round(zero_first_7_day_share, 6),
            "prediction_std": round(float(values.std(ddof=0)), 6),
            "collapsed_prediction_flag": bool(collapsed),
            "flat_promotion_count": int(len(flat_promotions)),
            "flat_promotions": flat_promotions,
            "actionable_row_count": actionable_row_count,
            "actionable_modal_prediction_share": round(actionable_modal_prediction_share, 6),
            "actionable_zero_first_7_day_share": round(actionable_zero_first_7_day_share, 6),
            "unresolved_collapse_row_count": unresolved_collapse_row_count,
            "unresolved_collapse_share": round(unresolved_collapse_share, 6),
            "unresolved_classification_counts": unresolved_classification_counts,
            "unresolved_actionable_promotion_count": int(unresolved_actionable_promotion_count),
            "mixed_unresolved_promotion_count": int(mixed_unresolved_promotion_count),
            "unresolved_promotion_count": unresolved_promotion_count,
            "unresolved_flat_promotion_count": int(len(unresolved_flat_promotions)),
            "unresolved_flat_promotions": unresolved_flat_promotions,
            "cohort_flat_only_promotion_count": int(len(cohort_flat_only_promotions)),
            "cohort_flat_only_promotions": cohort_flat_only_promotions,
        }

    def _validate_commercial_contract(self, frame: pd.DataFrame, *, forecast_health: dict[str, object]) -> None:
        failures: list[str] = []
        expected_columns = list(COMMERCIAL_SCHEMA_COLUMNS)
        missing = [column for column in expected_columns if column not in frame.columns]
        if missing:
            failures.append("Missing required commercial columns: " + ", ".join(missing))
        if list(frame.columns) != expected_columns:
            failures.append("Commercial export column order does not match the Stage 11 contract.")

        removed_columns = {
            "promotion_id",
            "promotional_sku_id_key",
            "sku_description",
            "supplier_number",
            "supplier_name",
            "brand_name",
            "target_base_stock_min_units",
            "minimum_base_stock_target_units",
            "recommended_order_units_to_min_base_stock",
            "live_promo_window_days",
            "promo_days",
            "order_priority",
            "reason_secondary",
            "model_signal_summary",
            "stock_position_summary",
            "demand_summary",
            "risk_summary",
            "inventory_inputs_missing_flag",
            "missing_current_soh_flag",
            "missing_qty_on_order_flag",
            "recommendation_input_null_counts",
        }
        unexpected_legacy = sorted(removed_columns.intersection(set(frame.columns)))
        if unexpected_legacy:
            failures.append("Legacy non-value columns still present: " + ", ".join(unexpected_legacy))

        blank_sku = frame["sku_number"].isna() | frame["sku_number"].astype(str).str.strip().isin({"", "nan", "none", "<na>"})
        if blank_sku.any():
            failures.append("sku_number cannot be null or blank.")
        if frame["product_description"].astype(str).str.strip().eq("").any():
            failures.append("product_description cannot be null or blank.")

        duplicate_count = int(
            frame.duplicated(subset=["store_number", "promotion_header_key", "sku_number"], keep=False).sum()
        )
        if duplicate_count > 0:
            failures.append("duplicate store_number + promotion_header_key + sku_number rows detected.")

        for column in COMMERCIAL_UNIT_COLUMNS:
            values = pd.to_numeric(frame[column], errors="coerce")
            if values.isna().any() or (values < 0).any() or not values.eq(values.round(0)).all():
                failures.append(f"{column} must be non-negative and integer-safe.")

        for column in COMMERCIAL_DECIMAL_COLUMNS:
            values = pd.to_numeric(frame[column], errors="coerce")
            if values.isna().any():
                failures.append(f"{column} must be numeric.")
            rounded = values.round(4)
            if not values.fillna(0.0).eq(rounded.fillna(0.0)).all():
                failures.append(f"{column} must round to 4 decimal places.")

        if (pd.to_numeric(frame["promo_start_target_soh_units"], errors="coerce") < pd.to_numeric(frame["base_units_target"], errors="coerce")).any():
            failures.append("promo_start_target_soh_units must be greater than or equal to base_units_target.")
        if (pd.to_numeric(frame["predicted_units_total_promo"], errors="coerce") < pd.to_numeric(frame["predicted_units_first_7_days_of_promo"], errors="coerce")).any():
            failures.append("predicted_units_total_promo must be greater than or equal to predicted_units_first_7_days_of_promo.")
        if (pd.to_numeric(frame["suggested_order_units"], errors="coerce") < 0).any():
            failures.append("suggested_order_units must be non-negative.")

        for column in ("decision_reason", "client_reason", "operational_note"):
            if frame[column].astype(str).str.strip().eq("").any():
                failures.append(f"{column} must be populated for every commercial row.")

        allowed_cash_bands = {"MINIMAL", "LOW", "MEDIUM", "HIGH"}
        if not frame["estimated_cash_risk_band"].astype(str).isin(allowed_cash_bands).all():
            failures.append("estimated_cash_risk_band contains unsupported values.")

        allowed_confidence_bands = {"UNKNOWN", "LOW", "MEDIUM", "HIGH"}
        if not frame["demand_confidence_band"].astype(str).isin(allowed_confidence_bands).all():
            failures.append("demand_confidence_band contains unsupported values.")

        allowed_attention_flags = {"URGENT", "REVIEW", "WATCH", "LOW_PRIORITY"}
        if not frame["execution_attention_flag"].astype(str).isin(allowed_attention_flags).all():
            failures.append("execution_attention_flag contains unsupported values.")

        allowed_forecast_quality_flags = {
            "NO_REAL_PROMO_DEMAND",
            "LOW_NONZERO_DEMAND",
            "UNCERTAIN_FLAT_PATTERN",
            "ACTIONABLE_FORECAST",
        }
        if not frame["forecast_quality_flag"].astype(str).isin(allowed_forecast_quality_flags).all():
            failures.append("forecast_quality_flag contains unsupported values.")

        allowed_forecast_reliability_bands = {"UNKNOWN", "LOW", "MEDIUM", "HIGH"}
        if not frame["forecast_reliability_band"].astype(str).isin(allowed_forecast_reliability_bands).all():
            failures.append("forecast_reliability_band contains unsupported values.")

        allowed_demand_shape_flags = {
            "HONEST_ZERO",
            "LOW_NONZERO",
            "COHORT_FLATNESS",
            "ROW_SIGNAL_VARIATION",
        }
        if not frame["demand_shape_flag"].astype(str).isin(allowed_demand_shape_flags).all():
            failures.append("demand_shape_flag contains unsupported values.")

        allowed_lift_flags = {"NONE_EXPECTED", "WEAK_LIFT", "UNCERTAIN_LIFT", "MATERIAL_LIFT"}
        if not frame["promo_lift_expectation_flag"].astype(str).isin(allowed_lift_flags).all():
            failures.append("promo_lift_expectation_flag contains unsupported values.")

        for column, max_length in COMMERCIAL_STRING_LENGTH_LIMITS.items():
            if frame[column].astype(str).str.len().gt(max_length).any():
                failures.append(f"{column} exceeds max SQL-safe length {max_length}.")

        expected_soh_at_promo_start = (
            pd.to_numeric(frame["current_soh_units"], errors="coerce").fillna(0.0)
            + pd.to_numeric(frame["qty_on_order_units"], errors="coerce").fillna(0.0)
            - pd.to_numeric(frame["predicted_units_until_promo_start"], errors="coerce").fillna(0.0)
        ).clip(lower=0.0)
        promo_gap = (
            pd.to_numeric(frame["promo_start_target_soh_units"], errors="coerce").fillna(0.0)
            - expected_soh_at_promo_start
        ).clip(lower=0.0)
        reconciled_leftover = (
            expected_soh_at_promo_start
            + pd.to_numeric(frame["suggested_order_units"], errors="coerce").fillna(0.0)
            - pd.to_numeric(frame["predicted_units_total_promo"], errors="coerce").fillna(0.0)
        ).clip(lower=0.0).round(0)
        actual_leftover = pd.to_numeric(
            frame["expected_leftover_units_end_of_promo"],
            errors="coerce",
        ).fillna(0.0).round(0)
        if not actual_leftover.eq(reconciled_leftover).all():
            failures.append("expected_leftover_units_end_of_promo does not reconcile with stock-plus-order minus total forecast.")
        promo_duration_days = (
            pd.to_datetime(frame["promotion_end_date"], errors="coerce")
            - pd.to_datetime(frame["promotion_start_date"], errors="coerce")
        ).dt.days.add(1).clip(lower=1).fillna(1)
        stock_cover_days = (
            (
                pd.to_numeric(frame["current_soh_units"], errors="coerce").fillna(0.0)
                + pd.to_numeric(frame["qty_on_order_units"], errors="coerce").fillna(0.0)
            )
            / (
                pd.to_numeric(frame["predicted_units_total_promo"], errors="coerce").fillna(0.0)
                .div(promo_duration_days)
                .replace(0.0, 0.01)
            )
        )

        explanation_text = (
            frame["decision_reason"].astype(str).str.lower()
            + " "
            + frame["client_reason"].astype(str).str.lower()
            + " "
            + frame["operational_note"].astype(str).str.lower()
        )
        contradiction_mask = (
            frame["decision_recommendation"].astype(str).eq("ORDER")
            & pd.to_numeric(frame["suggested_order_units"], errors="coerce").fillna(0.0).gt(0.0)
            & pd.to_numeric(frame["expected_leftover_units_end_of_promo"], errors="coerce").fillna(0.0).ge(
                pd.to_numeric(frame["base_units_target"], errors="coerce").fillna(0.0) + 4.0
            )
            & ~explanation_text.str.contains("leftover risk|review required|extreme stock cover|conflict", na=False)
        )
        if contradiction_mask.any():
            failures.append("Commercial contradiction detected: ORDER with extreme stock cover and high leftover without explanation.")

        extreme_cover_mask = (
            frame["decision_recommendation"].astype(str).eq("ORDER")
            & stock_cover_days.ge(EXTREME_STOCK_COVER_DAYS_THRESHOLD)
            & promo_gap.le(0.0)
            & ~explanation_text.str.contains("promo-start gap|start gap|review required", na=False)
        )
        if extreme_cover_mask.any():
            failures.append("Commercial contradiction detected: ORDER with extreme stock cover and no promo-start gap justification.")

        # Cohort-level collapse only blocks publication when there are unresolved per-promotion flat
        # issues. When unresolved_flat_promotion_count == 0, every flat promotion was resolved by the
        # anti-collapse repair or classified as true-zero and excluded from the actionable set, so the
        # cohort-modal-share spike is explained by integerization floor (fractional positives → 1 unit)
        # rather than a genuine degenerate forecast. The per-promotion unresolved check below is the
        # authoritative guard in that case.
        if bool(forecast_health.get("collapsed_prediction_flag", False)) and int(forecast_health.get("unresolved_flat_promotion_count", 0)) > 0:
            failures.append("Forecast collapse detected: modal prediction share exceeds threshold.")
        if (
            int(forecast_health.get("actionable_row_count", 0)) >= FORECAST_COLLAPSE_MIN_ROWS
            and float(forecast_health.get("actionable_zero_first_7_day_share", 0.0)) >= FORECAST_ZERO_FIRST7_SHARE_THRESHOLD
        ):
            failures.append("Forecast collapse detected: first-7-days forecast is zero for too many SKUs.")
        if int(forecast_health.get("unresolved_flat_promotion_count", 0)) > 0:
            failures.append("Forecast collapse detected: predicted_units_total_promo is implausibly flat within one or more promotions.")

        if failures:
            raise PromotionStoreDownloadCommercialValidationError("; ".join(failures))


# Priority-ordered source names for forecast resolution.
# Sources are tried in order; the first non-degenerate source for each promotion is used.
_FORECAST_SOURCE_PRIORITY: tuple[str, ...] = (
    "required_implied_units",   # rank 1 — stock-basis allocation; best per-promotion variation in live data
    "demand_reference_units",   # rank 2 — reference demand signal
    "baseline_expected_units",  # rank 3 — baseline model expectation (can be flat at high value; tried third)
    "predicted_units_sold",     # rank 4 — row-model output (frequently degenerate flat in live data)
    "history",                  # rank 5 — avg_daily_units × window or bar_units × window
)


def _source_is_acceptable_for_group(
    values: list[float],
    *,
    min_rows: int,
    modal_share_threshold: float,
) -> bool:
    """Return True if the source has at least one positive value and is not suspiciously flat.

    A source is flat if >= modal_share_threshold of values (including zeros) are the same
    AND the group has at least min_rows rows (too-small groups cannot be judged).
    """
    n = len(values)
    if n == 0:
        return False
    if not any(v > 0.0 for v in values):
        return False
    if n < min_rows:
        return True  # Too few rows to detect flatness — accept any positive signal
    counts = Counter(round(v, 6) for v in values)
    most_common_count = counts.most_common(1)[0][1]
    modal_share = most_common_count / n
    return modal_share < modal_share_threshold



def _prepare_forecast_source_values(
    *,
    predicted_units_sold: pd.Series,
    required_implied_units: pd.Series,
    demand_reference_units: pd.Series,
    baseline_expected_units: pd.Series,
    avg_daily_units: pd.Series,
    bar_units: pd.Series,
    promo_window_days: pd.Series,
) -> dict[str, list[float]]:
    """Build positional source value lists avoiding index-alignment issues.
    
    Computes the 5 forecast source options for each row position.
    """
    window_list_raw: list[float] = promo_window_days.fillna(1.0).tolist()
    history_list: list[float] = [
        max(
            float(avg or 0.0) * max(float(w or 1.0), 1.0),
            float(bar or 0.0) * max(float(w or 1.0), 1.0),
            0.0,
        )
        for avg, bar, w in zip(
            avg_daily_units.fillna(0.0).clip(lower=0.0).tolist(),
            bar_units.fillna(0.0).clip(lower=0.0).tolist(),
            window_list_raw,
            strict=False,
        )
    ]
    return {
        "required_implied_units": required_implied_units.fillna(0.0).clip(lower=0.0).tolist(),
        "demand_reference_units": demand_reference_units.fillna(0.0).clip(lower=0.0).tolist(),
        "baseline_expected_units": baseline_expected_units.fillna(0.0).clip(lower=0.0).tolist(),
        "predicted_units_sold": predicted_units_sold.fillna(0.0).clip(lower=0.0).tolist(),
        "history": history_list,
    }


def _classify_zero_forecast_evidence(
    *,
    frame: pd.DataFrame,
    forecast_resolution: pd.DataFrame,
    predicted_units_total_promo: pd.Series,
    predicted_units_first_7_days_of_promo: pd.Series,
) -> pd.DataFrame:
    """Classify whether a zero forecast is evidence-supported before fail-loud validation."""
    idx = frame.index
    current_discount = _numeric_series(
        frame,
        ("discount_percent", "feature_discount_depth_pct", "promo_discount_percent"),
    ).fillna(0.0)
    historical_discount_columns = (
        "historical_discount_percent",
        "historical_promo_discount_percent",
        "prior_promo_discount_percent",
        "prior_discount_percent",
        "historical_discount_depth_pct",
        "prior_discount_depth_pct",
    )
    historical_discount_known = any(column in frame.columns for column in historical_discount_columns)
    historical_discount = _numeric_series(frame, historical_discount_columns).fillna(0.0)
    historical_band_text = _best_available_text_series(
        frame,
        ("historical_discount_band", "historical_promo_discount_band", "prior_promo_discount_band"),
    ).fillna("")
    current_discount_bands = [
        _discount_band(value)
        for value in current_discount.tolist()
    ]
    historical_discount_bands = [
        _discount_band(value, text=band_text)
        for value, band_text in zip(
            historical_discount.tolist(),
            historical_band_text.tolist(),
            strict=False,
        )
    ]

    response_count = _numeric_series(
        frame,
        (
            "historical_promo_response_count",
            "historical_response_count_at_similar_discount",
            "prior_promo_response_count",
            "similar_discount_promo_response_count",
        ),
    ).fillna(0.0).clip(lower=0.0)
    historical_units = _numeric_series(
        frame,
        (
            "historical_promo_units_at_similar_discount",
            "historical_units_at_similar_discount",
            "prior_promo_units_at_similar_discount",
            "prior_units_at_similar_discount",
        ),
    ).fillna(0.0).clip(lower=0.0)
    historical_lift = _numeric_series(
        frame,
        (
            "historical_promo_lift_at_similar_discount",
            "historical_lift_at_similar_discount",
            "prior_promo_lift_at_similar_discount",
            "feature_prior_promo_response_same_sku_store",
            "feature_prior_promo_response_same_sku_network",
        ),
    ).fillna(0.0)
    explicit_similar_evidence_available = any(
        column in frame.columns
        for column in (
            "historical_promo_units_at_similar_discount",
            "historical_promo_lift_at_similar_discount",
            "historical_response_count_at_similar_discount",
            "similar_discount_promo_response_count",
        )
    )
    never_sold_flag = _flag_series(
        frame,
        (
            "never_sold_at_similar_discount_flag",
            "historical_never_sold_at_similar_discount_flag",
            "prior_never_sold_at_similar_discount_flag",
        ),
    )
    baseline_daily = _numeric_series(
        frame,
        (
            "baseline_daily_units",
            "feature_pre_promo_baseline_daily_units",
            "feature_sales_velocity_units_per_day",
            "avg_daily_units",
        ),
    ).fillna(0.0).clip(lower=0.0)
    if "has_baseline_demand" in frame.columns:
        has_baseline_demand = _flag_series(frame, ("has_baseline_demand",))
        baseline_daily = baseline_daily.where(has_baseline_demand.astype(bool), 0.0)
    baseline_classes = [
        _baseline_velocity_class(value)
        for value in baseline_daily.tolist()
    ]

    total_values = pd.to_numeric(predicted_units_total_promo, errors="coerce").fillna(0.0).tolist()
    first7_values = pd.to_numeric(predicted_units_first_7_days_of_promo, errors="coerce").fillna(0.0).tolist()
    raw_source_columns = [
        "raw_required_implied_units",
        "raw_demand_reference_units",
        "raw_baseline_expected_units",
        "raw_predicted_units_sold",
        "raw_history_units",
    ]
    raw_values = forecast_resolution.loc[:, raw_source_columns].fillna(0.0).clip(lower=0.0)
    max_raw_values = raw_values.max(axis=1).tolist()
    raw_model_values = pd.to_numeric(
        forecast_resolution.get("raw_predicted_units_sold", pd.Series(0.0, index=idx)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0).tolist()
    collapse_review_flags = forecast_resolution.get(
        "forecast_collapse_requires_review_flag",
        pd.Series(False, index=idx),
    ).astype(bool).tolist()

    supported_values: list[bool] = []
    reason_codes: list[str] = []
    confidence_values: list[float] = []
    similar_units_values: list[float] = []
    similar_lift_values: list[float] = []
    never_sold_values: list[int] = []

    for pos, index_value in enumerate(idx):
        total_units = float(total_values[pos] or 0.0)
        first7_units = float(first7_values[pos] or 0.0)
        current_band = current_discount_bands[pos]
        historical_band = historical_discount_bands[pos]
        if historical_discount_known:
            similar_discount = bool(historical_band and current_band == historical_band)
        else:
            similar_discount = explicit_similar_evidence_available
        count = float(response_count.loc[index_value] or 0.0)
        units = float(historical_units.loc[index_value] or 0.0) if similar_discount else 0.0
        lift = float(historical_lift.loc[index_value] or 0.0) if similar_discount else 0.0
        baseline_class = baseline_classes[pos]
        max_raw_signal = float(max_raw_values[pos] or 0.0)
        raw_model_signal = float(raw_model_values[pos] or 0.0)
        explicit_never_sold = bool(int(never_sold_flag.loc[index_value] or 0) == 1 and similar_discount)
        no_response_at_similar_discount = bool(
            similar_discount
            and count >= 1.0
            and units <= 0.0
            and lift <= ZERO_FORECAST_NO_RESPONSE_LIFT_MAX
        )
        repeated_non_response = bool(
            no_response_at_similar_discount
            and count >= ZERO_FORECAST_REPEATED_NON_RESPONSE_MIN_COUNT
        )
        never_sold = bool(explicit_never_sold or no_response_at_similar_discount)

        if total_units > 0.0 and first7_units <= 0.0:
            supported = False
            reason_code = "suspicious_first7_allocation_zero"
            confidence = 0.0
        elif total_units > 0.0:
            supported = False
            reason_code = "not_zero_forecast"
            confidence = 0.0
        elif repeated_non_response:
            supported = True
            reason_code = "similar_discount_repeated_non_response"
            confidence = 0.95
        elif never_sold:
            supported = True
            reason_code = "similar_discount_never_sold"
            confidence = 0.90
        elif baseline_class == "negligible" and max_raw_signal <= ZERO_FORECAST_RAW_NEAR_ZERO_MAX_UNITS:
            supported = True
            reason_code = "negligible_baseline_demand"
            confidence = 0.80
        elif (
            count <= 0.0
            and max_raw_signal <= ZERO_FORECAST_RAW_NEAR_ZERO_MAX_UNITS
            and raw_model_signal <= ZERO_FORECAST_RAW_NEAR_ZERO_MAX_UNITS
        ):
            supported = True
            reason_code = "raw_model_near_zero_with_sparse_history"
            confidence = 0.60
        elif bool(collapse_review_flags[pos]) and max_raw_signal > ZERO_FORECAST_RAW_NEAR_ZERO_MAX_UNITS:
            supported = False
            reason_code = "suspicious_positive_upstream_zero"
            confidence = 0.0
        else:
            supported = False
            reason_code = "unexplained_zero_concentration"
            confidence = 0.0

        supported_values.append(supported)
        reason_codes.append(reason_code)
        confidence_values.append(confidence)
        similar_units_values.append(units)
        similar_lift_values.append(lift)
        never_sold_values.append(int(never_sold))

    return pd.DataFrame(
        {
            "zero_forecast_is_evidence_supported": pd.Series(supported_values, index=idx, dtype="bool"),
            "zero_forecast_reason_code": pd.Series(reason_codes, index=idx, dtype="object"),
            "zero_forecast_confidence": pd.Series(confidence_values, index=idx, dtype="float64"),
            "historical_promo_response_count": response_count.astype("float64"),
            "historical_promo_units_at_similar_discount": pd.Series(
                similar_units_values,
                index=idx,
                dtype="float64",
            ),
            "historical_promo_lift_at_similar_discount": pd.Series(
                similar_lift_values,
                index=idx,
                dtype="float64",
            ),
            "never_sold_at_similar_discount_flag": pd.Series(never_sold_values, index=idx, dtype="int64"),
            "baseline_velocity_class": pd.Series(baseline_classes, index=idx, dtype="object"),
            "zero_forecast_discount_band": pd.Series(current_discount_bands, index=idx, dtype="object"),
            "historical_discount_band": pd.Series(historical_discount_bands, index=idx, dtype="object"),
        },
        index=idx,
    )


def _discount_band(value: object, *, text: object = "") -> str:
    text_value = str(text or "").strip().lower()
    for band in ("none", "shallow", "moderate", "deep", "extreme"):
        if band in text_value:
            return band
    try:
        percent = float(value)
    except (TypeError, ValueError):
        percent = 0.0
    if pd.isna(percent):
        percent = 0.0
    if percent > 1.0 and percent <= 100.0:
        percent = percent / 100.0
    percent = max(percent, 0.0)
    if percent <= 0.05:
        return "none"
    if percent <= 0.15:
        return "shallow"
    if percent <= 0.30:
        return "moderate"
    if percent <= 0.50:
        return "deep"
    return "extreme"


def _baseline_velocity_class(value: object) -> str:
    try:
        daily_units = float(value)
    except (TypeError, ValueError):
        daily_units = 0.0
    if pd.isna(daily_units):
        daily_units = 0.0
    daily_units = max(daily_units, 0.0)
    if daily_units <= ZERO_FORECAST_NEGLIGIBLE_BASELINE_DAILY_UNITS:
        return "negligible"
    if daily_units <= ZERO_FORECAST_LOW_BASELINE_DAILY_UNITS:
        return "low"
    if daily_units <= 1.0:
        return "medium"
    return "high"


def _flag_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return frame[column_name].map(_flag).astype("int64")
    return pd.Series(0, index=frame.index, dtype="int64")


def _flag(value: object) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and pd.isna(value):
            return 0
        return 1 if float(value) >= 1.0 else 0
    text = str(value or "").strip().lower()
    return 1 if text in {"1", "true", "yes", "y", "t"} else 0


def _perform_per_promotion_source_selection(
    *,
    promo_to_positions: dict[str, list[int]],
    source_values: dict[str, list[float]],
) -> dict[str, tuple[str, int, str]]:
    """Step 1: perform per-promotion source selection using raw-value quality check.
    
    For each promotion, iterate through source priority order and accept the first
    source that passes _source_is_acceptable_for_group criteria.
    """
    promotion_source_info: dict[str, tuple[str, int, str]] = {}
    for promo_key, positions in promo_to_positions.items():
        selected_source: str | None = None
        selected_rank: int = 0
        tried_degenerate: list[str] = []
        for rank, source_name in enumerate(_FORECAST_SOURCE_PRIORITY, start=1):
            group_values = [source_values[source_name][pos] for pos in positions]
            if _source_is_acceptable_for_group(
                group_values,
                min_rows=FORECAST_FLAT_PROMOTION_MIN_ROWS,
                modal_share_threshold=FORECAST_FLAT_PROMOTION_MODAL_SHARE_THRESHOLD,
            ):
                selected_source = source_name
                selected_rank = rank
                break
            tried_degenerate.append(source_name)
        if selected_source is None:
            promotion_source_info[promo_key] = (
                "zero_evidence",
                len(_FORECAST_SOURCE_PRIORITY) + 1,
                "all_sources_degenerate_or_zero",
            )
        elif selected_rank > 1:
            promotion_source_info[promo_key] = (
                selected_source,
                selected_rank,
                "degenerate:" + ",".join(tried_degenerate),
            )
        else:
            promotion_source_info[promo_key] = (selected_source, 1, "")
    return promotion_source_info


def _compute_resolved_forecast_values(
    *,
    promo_keys_list: list[str],
    source_values: dict[str, list[float]],
    promotion_source_info: dict[str, tuple[str, int, str]],
    window_list: list[float],
) -> dict[str, list[object]]:
    """Step 2: compute per-row resolved forecast values from selected sources.
    
    For each row, extract the selected source value, compute daily forecast,
    and initialize diagnostic tracking lists.
    """
    n = len(promo_keys_list)
    resolved_total: list[float] = [0.0] * n
    resolved_daily: list[float] = [0.0] * n
    source_used_list: list[str] = ["zero_evidence"] * n
    priority_rank_list: list[int] = [len(_FORECAST_SOURCE_PRIORITY) + 1] * n
    repaired_list: list[bool] = [False] * n
    repair_reason_list: list[str] = [""] * n
    zero_before_list: list[bool] = [False] * n
    zero_after_list: list[bool] = [True] * n
    flat_promo_list: list[bool] = [False] * n

    for pos, promo_key in enumerate(promo_keys_list):
        source_name, rank, repair_reason = promotion_source_info[promo_key]
        window = window_list[pos]
        preferred_value = source_values["required_implied_units"][pos]
        zero_before = preferred_value <= 0.0
        if source_name == "zero_evidence":
            total = 0.0
            flat_promo = True
        else:
            total = max(source_values[source_name][pos], 0.0)
            flat_promo = False
        daily = max(total / window, 0.0) if window > 0.0 else 0.0
        resolved_total[pos] = total
        resolved_daily[pos] = daily
        source_used_list[pos] = source_name
        priority_rank_list[pos] = rank
        repaired_list[pos] = source_name != "zero_evidence" and rank > 1
        repair_reason_list[pos] = repair_reason
        zero_before_list[pos] = zero_before
        zero_after_list[pos] = total <= 0.0
        flat_promo_list[pos] = flat_promo

    return {
        "resolved_total": resolved_total,
        "resolved_daily": resolved_daily,
        "source_used": source_used_list,
        "priority_rank": priority_rank_list,
        "repaired": repaired_list,
        "repair_reason": repair_reason_list,
        "zero_before": zero_before_list,
        "zero_after": zero_after_list,
        "flat_promo": flat_promo_list,
    }


def _apply_anti_collapse_repair(
    *,
    promo_to_positions: dict[str, list[int]],
    promotion_source_info: dict[str, tuple[str, int, str]],
    source_values: dict[str, list[float]],
    window_list: list[float],
    resolved_totals: list[float],
    resolved_dailies: list[float],
    source_used_list: list[str],
    priority_rank_list: list[int],
    repaired_list: list[bool],
    repair_reason_list: list[str],
    zero_after_list: list[bool],
    flat_promo_list: list[bool],
) -> None:
    """Step 3: anti-collapse repair - re-source flat promotions after rounding.
    
    For promotions that are flat even after rounding, tries lower-priority sources
    and updates the mutable result lists in-place if a non-flat source is found.
    """
    for promo_key, positions in promo_to_positions.items():
        if len(positions) < FORECAST_FLAT_PROMOTION_MIN_ROWS:
            continue
        current_source_name, current_rank, _ = promotion_source_info[promo_key]
        if current_source_name == "zero_evidence":
            continue
        rounded_vals: list[float] = [float(round(resolved_totals[pos])) for pos in positions]
        if _source_is_acceptable_for_group(
            rounded_vals,
            min_rows=FORECAST_FLAT_PROMOTION_MIN_ROWS,
            modal_share_threshold=FORECAST_FLAT_PROMOTION_MODAL_SHARE_THRESHOLD,
        ):
            continue
        repaired_in_collapse = False
        for rank, source_name in enumerate(_FORECAST_SOURCE_PRIORITY, start=1):
            if rank <= current_rank:
                continue
            group_raw = [source_values[source_name][pos] for pos in positions]
            group_rounded: list[float] = [float(round(max(v, 0.0))) for v in group_raw]
            if _source_is_acceptable_for_group(
                group_rounded,
                min_rows=FORECAST_FLAT_PROMOTION_MIN_ROWS,
                modal_share_threshold=FORECAST_FLAT_PROMOTION_MODAL_SHARE_THRESHOLD,
            ):
                for pos in positions:
                    window = window_list[pos]
                    total = max(source_values[source_name][pos], 0.0)
                    daily = max(total / window, 0.0) if window > 0.0 else 0.0
                    resolved_totals[pos] = total
                    resolved_dailies[pos] = daily
                    source_used_list[pos] = source_name
                    priority_rank_list[pos] = rank
                    repaired_list[pos] = True
                    repair_reason_list[pos] = f"anti_collapse_rounded_flat_repaired_to_{source_name}"
                    zero_after_list[pos] = total <= 0.0
                    flat_promo_list[pos] = False
                promotion_source_info[promo_key] = (source_name, rank, "anti_collapse_repair")
                repaired_in_collapse = True
                break
        if not repaired_in_collapse:
            for pos in positions:
                flat_promo_list[pos] = True


def _apply_row_level_signal_override_and_classification(
    *,
    source_values: dict[str, list[float]],
    resolved_totals: list[float],
    resolved_dailies: list[float],
    source_used_list: list[str],
    priority_rank_list: list[int],
    repaired_list: list[bool],
    repair_reason_list: list[str],
    zero_after_list: list[bool],
    flat_promo_list: list[bool],
    window_list: list[float],
) -> dict[str, list[object]]:
    """Apply strict remediation policy and classify every row for audit-ready diagnostics."""
    n = len(resolved_totals)
    zero_classification: list[str] = [FORECAST_ZERO_DEMAND_HEALTHY] * n
    repair_allowed_flags: list[bool] = [False] * n
    repair_rejected_reasons: list[str] = [""] * n
    rounding_loss_flags: list[bool] = [False] * n
    override_applied_flags: list[bool] = [False] * n
    override_source_names: list[str] = [""] * n
    collapse_review_flags: list[bool] = [False] * n
    unresolved_collapse_reasons: list[str] = [""] * n

    for pos in range(n):
        raw_candidates = {
            source_name: max(source_values[source_name][pos], 0.0)
            for source_name in _FORECAST_SOURCE_PRIORITY
        }
        selected_source = source_used_list[pos]
        selected_value = max(float(resolved_totals[pos] or 0.0), 0.0)
        max_row_signal = max(raw_candidates.values()) if raw_candidates else 0.0
        all_zero = max_row_signal <= 0.0
        low_nonzero = 0.0 < selected_value <= LOW_NONZERO_DEMAND_MAX_UNITS
        rounding_loss = bool(selected_value > 0.0 and int(round(selected_value)) <= 0)
        rounding_loss_flags[pos] = rounding_loss

        repair_allowed = bool(
            (selected_value <= 0.0)
            or rounding_loss
            or bool(flat_promo_list[pos])
        )
        repair_allowed_flags[pos] = repair_allowed

        if all_zero:
            zero_classification[pos] = FORECAST_ZERO_DEMAND_TRUE
            repair_rejected_reasons[pos] = FORECAST_REPAIR_REJECTED_HONEST_ZERO
            zero_after_list[pos] = True
            collapse_review_flags[pos] = False
            unresolved_collapse_reasons[pos] = ""
            continue

        if repair_allowed:
            candidates = [
                (name, value)
                for name, value in raw_candidates.items()
                if name != selected_source and value > 0.0
            ]
            candidates.sort(key=lambda item: item[1], reverse=True)
            if candidates:
                best_name, best_value = candidates[0]
                low_nonzero_repair = bool(
                    selected_value <= 0.0
                    and selected_source != "zero_evidence"
                    and not bool(flat_promo_list[pos])
                    and 0.0 < best_value <= LOW_NONZERO_DEMAND_MAX_UNITS
                )
                materially_stronger = (
                    best_value >= ROW_SIGNAL_OVERRIDE_ABSOLUTE_MIN_UNITS
                    and best_value >= max(selected_value * ROW_SIGNAL_OVERRIDE_RATIO_THRESHOLD, selected_value + 0.75)
                )
                if materially_stronger or low_nonzero_repair:
                    window = max(float(window_list[pos] or 1.0), 1.0)
                    resolved_totals[pos] = best_value
                    resolved_dailies[pos] = best_value / window
                    source_used_list[pos] = best_name
                    priority_rank_list[pos] = _FORECAST_SOURCE_PRIORITY.index(best_name) + 1
                    repaired_list[pos] = True
                    repair_reason_list[pos] = (
                        FORECAST_REPAIR_REASON_ROUNDING_LOSS
                        if rounding_loss
                        else FORECAST_REPAIR_REASON_ACTIONABLE_OVERRIDE
                    )
                    zero_after_list[pos] = False
                    flat_promo_list[pos] = False
                    override_applied_flags[pos] = True
                    override_source_names[pos] = best_name
                    selected_value = best_value
                    rounding_loss_flags[pos] = False
                else:
                    repair_rejected_reasons[pos] = FORECAST_REPAIR_REJECTED_NOT_MATERIAL
            else:
                repair_rejected_reasons[pos] = (
                    FORECAST_REPAIR_REJECTED_COHORT_FLAT
                    if bool(flat_promo_list[pos])
                    else FORECAST_REPAIR_REJECTED_ALL_DEGENERATE
                )

        selected_value = max(float(resolved_totals[pos] or 0.0), 0.0)
        low_nonzero = 0.0 < selected_value <= LOW_NONZERO_DEMAND_MAX_UNITS
        effective_rounding_loss = bool(selected_value > 0.0 and int(round(selected_value)) <= 0)
        rounding_loss_flags[pos] = effective_rounding_loss
        if selected_value <= 0.0:
            if bool(flat_promo_list[pos]):
                zero_classification[pos] = FORECAST_ZERO_DEMAND_COHORT_FLAT
                unresolved_collapse_reasons[pos] = (
                    repair_rejected_reasons[pos] or FORECAST_REPAIR_REJECTED_COHORT_FLAT
                )
            else:
                zero_classification[pos] = FORECAST_ZERO_DEMAND_COLLAPSED
                unresolved_collapse_reasons[pos] = (
                    repair_rejected_reasons[pos] or FORECAST_REPAIR_REJECTED_ALL_DEGENERATE
                )
            collapse_review_flags[pos] = True
            zero_after_list[pos] = True
        elif low_nonzero:
            zero_classification[pos] = FORECAST_ZERO_DEMAND_LOW_NONZERO
            if not repair_rejected_reasons[pos]:
                repair_rejected_reasons[pos] = FORECAST_REPAIR_REJECTED_LOW_NONZERO
            rounding_loss_flags[pos] = False
            collapse_review_flags[pos] = False
            unresolved_collapse_reasons[pos] = ""
        elif effective_rounding_loss:
            zero_classification[pos] = FORECAST_ZERO_DEMAND_ROUNDING
            collapse_review_flags[pos] = True
            unresolved_collapse_reasons[pos] = FORECAST_REPAIR_REJECTED_NOT_MATERIAL
        elif bool(flat_promo_list[pos]):
            zero_classification[pos] = FORECAST_ZERO_DEMAND_COHORT_FLAT
            collapse_review_flags[pos] = True
            unresolved_collapse_reasons[pos] = (
                repair_rejected_reasons[pos] or FORECAST_REPAIR_REJECTED_COHORT_FLAT
            )
        else:
            zero_classification[pos] = FORECAST_ZERO_DEMAND_HEALTHY
            collapse_review_flags[pos] = False
            unresolved_collapse_reasons[pos] = ""

    return {
        "forecast_zero_demand_classification": zero_classification,
        "forecast_repair_allowed_flag": repair_allowed_flags,
        "forecast_repair_rejected_reason": repair_rejected_reasons,
        "forecast_rounding_loss_flag": rounding_loss_flags,
        "forecast_row_override_applied_flag": override_applied_flags,
        "forecast_row_override_source": override_source_names,
        "forecast_collapse_requires_review_flag": collapse_review_flags,
        "forecast_unresolved_collapse_reason": unresolved_collapse_reasons,
    }


def _resolve_commercial_forecast_inputs(
    *,
    frame: pd.DataFrame,
    promotion_header_key: pd.Series,
    promo_window_days: pd.Series,
    predicted_units_sold: pd.Series,
    required_implied_units: pd.Series,
    demand_reference_units: pd.Series,
    baseline_expected_units: pd.Series,
    avg_daily_units: pd.Series,
    bar_units: pd.Series,
) -> pd.DataFrame:
    """Resolve authoritative forecast inputs using priority-ordered per-promotion source selection.

    Root cause fixed: the prior max-based cohort blend caused flat outputs whenever
    baseline_expected_units was flat at a high value for a promotion (dominates the max even
    when required_implied_units and demand_reference_units have good variation).

    Process (3 steps):
      1. Prepare forecast source values (5 options per row)
      2. Per-promotion source selection using quality check
      3. Compute per-row resolved values
      4. Anti-collapse repair for still-flat promotions after rounding

    Source priority (per promotion):
      1. required_implied_units  — stock-basis derived; best per-promotion variation
      2. demand_reference_units  — reference demand signal
      3. baseline_expected_units — baseline model expectation
      4. predicted_units_sold    — row-model output (frequently degenerate)
      5. history                 — max(avg_daily_units, bar_units) × window_days
    """
    promo_window_days = promo_window_days.replace(0.0, pd.NA).fillna(1.0)

    # Prepare source values
    source_values = _prepare_forecast_source_values(
        predicted_units_sold=predicted_units_sold,
        required_implied_units=required_implied_units,
        demand_reference_units=demand_reference_units,
        baseline_expected_units=baseline_expected_units,
        avg_daily_units=avg_daily_units,
        bar_units=bar_units,
        promo_window_days=promo_window_days,
    )

    # Build promotion grouping
    promo_keys_list: list[str] = promotion_header_key.astype(str).tolist()
    window_list_raw: list[float] = promo_window_days.fillna(1.0).tolist()
    window_list: list[float] = [max(float(w or 1.0), 1.0) for w in window_list_raw]
    promo_to_positions: dict[str, list[int]] = {}
    for pos, key in enumerate(promo_keys_list):
        promo_to_positions.setdefault(key, []).append(pos)

    # Step 1: Per-promotion source selection
    promotion_source_info = _perform_per_promotion_source_selection(
        promo_to_positions=promo_to_positions,
        source_values=source_values,
    )

    # Step 2: Compute per-row resolved values
    resolved_values = _compute_resolved_forecast_values(
        promo_keys_list=promo_keys_list,
        source_values=source_values,
        promotion_source_info=promotion_source_info,
        window_list=window_list,
    )

    # Step 3: Anti-collapse repair
    _apply_anti_collapse_repair(
        promo_to_positions=promo_to_positions,
        promotion_source_info=promotion_source_info,
        source_values=source_values,
        window_list=window_list,
        resolved_totals=resolved_values["resolved_total"],
        resolved_dailies=resolved_values["resolved_daily"],
        source_used_list=resolved_values["source_used"],
        priority_rank_list=resolved_values["priority_rank"],
        repaired_list=resolved_values["repaired"],
        repair_reason_list=resolved_values["repair_reason"],
        zero_after_list=resolved_values["zero_after"],
        flat_promo_list=resolved_values["flat_promo"],
    )

    policy_outputs = _apply_row_level_signal_override_and_classification(
        source_values=source_values,
        resolved_totals=resolved_values["resolved_total"],
        resolved_dailies=resolved_values["resolved_daily"],
        source_used_list=resolved_values["source_used"],
        priority_rank_list=resolved_values["priority_rank"],
        repaired_list=resolved_values["repaired"],
        repair_reason_list=resolved_values["repair_reason"],
        zero_after_list=resolved_values["zero_after"],
        flat_promo_list=resolved_values["flat_promo"],
        window_list=window_list,
    )

    # Return DataFrame with all diagnostics
    idx = frame.index
    return pd.DataFrame(
        {
            "resolved_total_units": pd.Series(resolved_values["resolved_total"], index=idx, dtype="float64"),
            "resolved_daily_units": pd.Series(resolved_values["resolved_daily"], index=idx, dtype="float64"),
            "forecast_source": pd.Series(resolved_values["source_used"], index=idx, dtype="object"),
            "forecast_source_raw_units": pd.Series(
                [source_values[source_name][pos] if source_name in source_values else 0.0 for pos, source_name in enumerate(resolved_values["source_used"])],
                index=idx,
                dtype="float64",
            ),
            "forecast_source_priority_rank": pd.Series(resolved_values["priority_rank"], index=idx, dtype="int64"),
            "repaired_from_degenerate": pd.Series(resolved_values["repaired"], index=idx, dtype="bool"),
            "forecast_repair_reason": pd.Series(resolved_values["repair_reason"], index=idx, dtype="object"),
            "forecast_zero_before_repair_flag": pd.Series(resolved_values["zero_before"], index=idx, dtype="bool"),
            "forecast_zero_after_repair_flag": pd.Series(resolved_values["zero_after"], index=idx, dtype="bool"),
            "forecast_flat_promotion_flag": pd.Series(resolved_values["flat_promo"], index=idx, dtype="bool"),
            "raw_required_implied_units": pd.Series(source_values["required_implied_units"], index=idx, dtype="float64"),
            "raw_demand_reference_units": pd.Series(source_values["demand_reference_units"], index=idx, dtype="float64"),
            "raw_baseline_expected_units": pd.Series(source_values["baseline_expected_units"], index=idx, dtype="float64"),
            "raw_predicted_units_sold": pd.Series(source_values["predicted_units_sold"], index=idx, dtype="float64"),
            "raw_history_units": pd.Series(source_values["history"], index=idx, dtype="float64"),
            "forecast_zero_demand_classification": pd.Series(
                policy_outputs["forecast_zero_demand_classification"],
                index=idx,
                dtype="object",
            ),
            "forecast_repair_allowed_flag": pd.Series(
                policy_outputs["forecast_repair_allowed_flag"],
                index=idx,
                dtype="bool",
            ),
            "forecast_repair_rejected_reason": pd.Series(
                policy_outputs["forecast_repair_rejected_reason"],
                index=idx,
                dtype="object",
            ),
            "forecast_rounding_loss_flag": pd.Series(
                policy_outputs["forecast_rounding_loss_flag"],
                index=idx,
                dtype="bool",
            ),
            "forecast_row_override_applied_flag": pd.Series(
                policy_outputs["forecast_row_override_applied_flag"],
                index=idx,
                dtype="bool",
            ),
            "forecast_row_override_source": pd.Series(
                policy_outputs["forecast_row_override_source"],
                index=idx,
                dtype="object",
            ),
            "forecast_collapse_requires_review_flag": pd.Series(
                policy_outputs["forecast_collapse_requires_review_flag"],
                index=idx,
                dtype="bool",
            ),
            "forecast_unresolved_collapse_reason": pd.Series(
                policy_outputs["forecast_unresolved_collapse_reason"],
                index=idx,
                dtype="object",
            ),
        }
    )


def _text_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    values = _best_available_text_series(frame, column_names)
    return values.fillna("").astype(str)


def _raw_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    result = pd.Series(pd.NA, index=frame.index, dtype="object")
    for column_name in column_names:
        if column_name not in frame.columns:
            continue
        candidate = frame[column_name]
        missing_mask = result.isna() | candidate.astype(str).str.strip().isin({"", "nan", "none", "<na>"})
        fill_mask = missing_mask & candidate.notna()
        result = result.where(~fill_mask, candidate)
    return result


def _best_available_text_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    result = pd.Series(pd.NA, index=frame.index, dtype="object")
    for column_name in column_names:
        if column_name not in frame.columns:
            continue
        candidate = _normalize_text_series(
            frame[column_name],
            collapse_internal_whitespace=True,
        )
        fill_mask = result.isna() & candidate.notna()
        result = result.where(~fill_mask, candidate)
    return result


def _normalize_text_series(
    series: pd.Series,
    *,
    collapse_internal_whitespace: bool,
) -> pd.Series:
    normalized = series.where(series.notna(), pd.NA).astype("object")
    normalized = normalized.map(
        lambda value: _normalize_text_value(
            value,
            collapse_internal_whitespace=collapse_internal_whitespace,
        )
    )
    return normalized


def _normalize_text_value(value: object, *, collapse_internal_whitespace: bool) -> object:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if collapse_internal_whitespace:
        text = re.sub(r"\s+", " ", text)
    if text.lower() in {"", "nan", "none", "<na>"}:
        return pd.NA
    return text


def _normalize_identifier_series(series: pd.Series) -> pd.Series:
    def _normalize_identifier(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        text = str(value).strip()
        if text.lower() in {"", "nan", "none", "<na>"}:
            return pd.NA
        if re.fullmatch(r"\d+\.0+", text):
            return text.split(".", 1)[0]
        return text

    return series.map(_normalize_identifier).astype("object")


def _with_exclusion_reason(frame: pd.DataFrame, *, reason: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*COMMERCIAL_SCHEMA_COLUMNS, "exclusion_reason"])
    diagnostic = frame.copy()
    diagnostic["exclusion_reason"] = reason
    return diagnostic.reset_index(drop=False).rename(columns={"index": "source_row_index"})


def _numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return pd.to_numeric(frame[column_name], errors="coerce")
    return pd.Series(0.0, index=frame.index, dtype="float64")


def _optional_numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name in frame.columns:
        return pd.to_numeric(frame[column_name], errors="coerce")
    return pd.Series(pd.NA, index=frame.index, dtype="Float64")


def _optional_first_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    resolved = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    for column_name in column_names:
        if column_name not in frame.columns:
            continue
        candidate = pd.to_numeric(frame[column_name], errors="coerce")
        resolved = resolved.where(resolved.notna(), candidate)
    return resolved


def _first_positive_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    resolved = pd.Series(np.nan, index=frame.index, dtype="float64")
    for column_name in column_names:
        if column_name not in frame.columns:
            continue
        candidate = pd.to_numeric(frame[column_name], errors="coerce")
        resolved = resolved.where(resolved.notna(), candidate.where(candidate > 0.0))
    return resolved


def _discount_decimal(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where(numeric.abs() <= 1.0, numeric / 100.0).clip(lower=0.0, upper=1.0)


def _resolve_discount_components(frame: pd.DataFrame) -> dict[str, pd.Series]:
    raw_discount = pd.Series(np.nan, index=frame.index, dtype="float64")
    for column_name in ("discount_percent", "feature_discount_depth_pct", "promo_discount_percent"):
        if column_name not in frame.columns:
            continue
        candidate = _discount_decimal(pd.to_numeric(frame[column_name], errors="coerce"))
        raw_discount = raw_discount.where(raw_discount.notna() & (raw_discount > 0.0), candidate.where(candidate > 0.0))

    normal_price = _first_positive_numeric_series(
        frame,
        (
            "normal_price",
            "regular_price",
            "regular_price_ex_gst_effective",
            "regular_price_ex_gst",
            "norm_retail_inc_gst",
        ),
    )
    promo_price = _first_positive_numeric_series(
        frame,
        (
            "promo_price",
            "promo_price_ex_gst",
            "promo_retail_inc_gst",
            "promotional_price",
        ),
    )
    derived_discount = ((normal_price - promo_price) / normal_price.where(normal_price > 0.0)).clip(
        lower=0.0,
        upper=1.0,
    )
    resolved_discount = raw_discount.where(raw_discount > 0.0, derived_discount)
    return {
        "raw_discount": raw_discount.fillna(0.0).clip(lower=0.0, upper=1.0),
        "normal_price": normal_price.fillna(0.0).clip(lower=0.0),
        "promo_price": promo_price.fillna(0.0).clip(lower=0.0),
        "derived_discount": derived_discount.fillna(0.0).clip(lower=0.0, upper=1.0),
        "resolved_discount": resolved_discount.fillna(0.0).clip(lower=0.0, upper=1.0),
    }


def _resolve_discount_truth_components(frame: pd.DataFrame) -> dict[str, pd.Series]:
    raw_discount = _resolve_discount_components(frame)["raw_discount"]
    normal_inc = _first_positive_numeric_series(
        frame,
        (
            "normal_price",
            "regular_price",
            "norm_retail_inc_gst",
        ),
    )
    promo_inc = _first_positive_numeric_series(
        frame,
        (
            "promo_retail_inc_gst",
            "promotional_price",
        ),
    )
    normal_ex = _first_positive_numeric_series(
        frame,
        (
            "regular_price_ex_gst_effective",
            "regular_price_ex_gst",
        ),
    )
    promo_ex = _first_positive_numeric_series(
        frame,
        (
            "promo_price",
            "promo_price_ex_gst",
        ),
    )
    legacy_normal = _first_positive_numeric_series(
        frame,
        (
            "normal_price",
            "regular_price",
        ),
    )
    legacy_promo = _first_positive_numeric_series(
        frame,
        (
            "promo_price",
            "promotional_price",
        ),
    )

    inc_pair_available = normal_inc.gt(0.0) & promo_inc.gt(0.0)
    ex_pair_available = normal_ex.gt(0.0) & promo_ex.gt(0.0)
    legacy_pair_available = (~inc_pair_available) & (~ex_pair_available) & legacy_normal.gt(0.0) & legacy_promo.gt(0.0)
    price_normal = normal_inc.where(
        inc_pair_available,
        normal_ex.where(ex_pair_available, legacy_normal.where(legacy_pair_available)),
    )
    price_promo = promo_inc.where(
        inc_pair_available,
        promo_ex.where(ex_pair_available, legacy_promo.where(legacy_pair_available)),
    )
    price_basis = pd.Series("missing", index=frame.index, dtype="object")
    price_basis = price_basis.where(~inc_pair_available, "inc_gst")
    price_basis = price_basis.where(~(~inc_pair_available & ex_pair_available), "ex_gst")
    price_basis = price_basis.where(~legacy_pair_available, "legacy")
    derived_discount = ((price_normal - price_promo) / price_normal.where(price_normal > 0.0)).clip(
        lower=0.0,
        upper=1.0,
    )
    repaired_discount = raw_discount.where(raw_discount.gt(0.0), derived_discount)
    return {
        "raw_discount": raw_discount.fillna(0.0).clip(lower=0.0, upper=1.0),
        "price_normal": price_normal.fillna(0.0).clip(lower=0.0),
        "price_promo": price_promo.fillna(0.0).clip(lower=0.0),
        "price_basis": price_basis,
        "derived_discount": derived_discount.fillna(0.0).clip(lower=0.0, upper=1.0),
        "repaired_discount": repaired_discount.fillna(0.0).clip(lower=0.0, upper=1.0),
    }


def _build_discount_review_diagnostic_frame(frame: pd.DataFrame) -> pd.DataFrame:
    components = _resolve_discount_truth_components(frame)
    mapped_discount_pct = (components["raw_discount"] * 100.0).round(4)
    derived_discount_pct = (components["derived_discount"] * 100.0).round(4)
    repaired_discount_pct = (components["repaired_discount"] * 100.0).round(4)
    discount_abs_diff = (components["raw_discount"] - components["derived_discount"]).abs() * 100.0
    tolerance = pd.Series(DISCOUNT_REPAIR_TOLERANCE_PCT_POINTS, index=frame.index, dtype="float64")

    raw_missing_or_zero = components["raw_discount"].le(0.0)
    valid_normal = components["price_normal"].gt(0.0)
    valid_promo = components["price_promo"].gt(0.0)
    valid_prices = valid_normal & valid_promo
    derived_discount_present = components["derived_discount"].ge(0.005)
    rounding_conflict = (
        components["raw_discount"].gt(0.0)
        & derived_discount_present
        & discount_abs_diff.gt(0.0)
        & discount_abs_diff.le(DISCOUNT_REPAIR_TOLERANCE_PCT_POINTS)
    )
    material_conflict = (
        components["raw_discount"].gt(0.0)
        & derived_discount_present
        & discount_abs_diff.gt(DISCOUNT_REPAIR_TOLERANCE_PCT_POINTS)
    )
    no_discount_valid = valid_prices & components["derived_discount"].lt(0.005)
    repairable_price_truth = raw_missing_or_zero & valid_prices & derived_discount_present

    reason_code = pd.Series(DISCOUNT_REVIEW_REASON_NO_ISSUE, index=frame.index, dtype="object")
    reason_code = reason_code.where(~(raw_missing_or_zero & ~valid_normal & ~valid_promo), DISCOUNT_REVIEW_REASON_HARD_MISSING_PRICES)
    reason_code = reason_code.where(~(raw_missing_or_zero & ~valid_normal & valid_promo), DISCOUNT_REVIEW_REASON_HARD_INVALID_NORMAL)
    reason_code = reason_code.where(~(raw_missing_or_zero & valid_normal & ~valid_promo), DISCOUNT_REVIEW_REASON_HARD_INVALID_PROMO)
    reason_code = reason_code.where(~repairable_price_truth, DISCOUNT_REVIEW_REASON_REPAIRABLE_PRICE_TRUTH)
    reason_code = reason_code.where(~rounding_conflict, DISCOUNT_REVIEW_REASON_ROUNDING_TOLERANCE)
    reason_code = reason_code.where(~material_conflict, DISCOUNT_REVIEW_REASON_MAPPING_CONFLICT)
    reason_code = reason_code.where(~(no_discount_valid & reason_code.eq(DISCOUNT_REVIEW_REASON_NO_ISSUE)), DISCOUNT_REVIEW_REASON_NO_DISCOUNT_VALID)

    can_repair = reason_code.isin(
        {
            DISCOUNT_REVIEW_REASON_REPAIRABLE_PRICE_TRUTH,
            DISCOUNT_REVIEW_REASON_ROUNDING_TOLERANCE,
            DISCOUNT_REVIEW_REASON_NO_DISCOUNT_VALID,
        }
    )
    repair_method = pd.Series("", index=frame.index, dtype="object")
    repair_method = repair_method.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_REPAIRABLE_PRICE_TRUTH), "derive_discount_from_price_truth")
    repair_method = repair_method.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_ROUNDING_TOLERANCE), "accept_price_truth_within_rounding_tolerance")
    repair_method = repair_method.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_NO_DISCOUNT_VALID), "accept_no_discount_from_valid_price_truth")

    reason_detail = pd.Series("", index=frame.index, dtype="object")
    reason_detail = reason_detail.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_HARD_MISSING_PRICES), "Mapped discount is missing and neither normal nor promo price is available for governed repair.")
    reason_detail = reason_detail.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_HARD_INVALID_NORMAL), "Mapped discount is missing and the normal price is absent or non-positive, so price truth cannot be derived.")
    reason_detail = reason_detail.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_HARD_INVALID_PROMO), "Mapped discount is missing and the promo price is absent or non-positive, so price truth cannot be derived.")
    reason_detail = reason_detail.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_REPAIRABLE_PRICE_TRUTH), "Mapped discount is missing or zero, but valid price truth yields a governed repairable discount.")
    reason_detail = reason_detail.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_ROUNDING_TOLERANCE), "Mapped discount and price-derived discount differ only within governed rounding tolerance.")
    reason_detail = reason_detail.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_MAPPING_CONFLICT), "Mapped discount materially conflicts with price-derived discount from the same price basis.")
    reason_detail = reason_detail.where(~reason_code.eq(DISCOUNT_REVIEW_REASON_NO_DISCOUNT_VALID), "Price truth shows no effective discount even though the promotion row is otherwise valid.")

    return pd.DataFrame(
        {
            "discount_data_quality_reason_code": reason_code,
            "discount_data_quality_reason_detail": reason_detail,
            "mapped_discount_pct": mapped_discount_pct.astype(float),
            "price_derived_discount_pct": derived_discount_pct.astype(float),
            "discount_abs_diff": discount_abs_diff.round(4).astype(float),
            "discount_tolerance_used": tolerance.astype(float),
            "can_repair_discount_flag": can_repair.astype(int),
            "repaired_discount_pct": repaired_discount_pct.astype(float),
            "repair_method": repair_method,
            "price_normal": components["price_normal"].round(4).astype(float),
            "price_promo": components["price_promo"].round(4).astype(float),
            "price_basis": components["price_basis"],
        },
        index=frame.index,
    )


def _resolve_discount_percent_series(frame: pd.DataFrame) -> pd.Series:
    """Surface the canonical promo discount as a readable 0..100 value.

    Resolution is row-wise: a positive governed discount wins, but if that
    field is missing/zero and normal/promo price differ, price-derived discount
    fills the operator CSV instead of collapsing the row to 0%.
    """

    components = _resolve_discount_components(frame)
    return (components["resolved_discount"] * 100.0).clip(lower=0.0, upper=100.0).round(1).astype(float)


def _discount_mapping_review_mask(frame: pd.DataFrame) -> pd.Series:
    return _discount_mapping_review_flag(frame).ne("")


def _discount_mapping_review_flag(frame: pd.DataFrame) -> pd.Series:
    components = _resolve_discount_components(frame)
    raw_missing_or_zero = components["raw_discount"] <= 0.0
    price_says_discount = components["derived_discount"] >= 0.005
    mapped_differs_from_price = (
        (components["raw_discount"] > 0.0)
        & (components["derived_discount"] >= 0.005)
        & ((components["raw_discount"] - components["derived_discount"]).abs() >= 0.05)
    )
    flags = pd.Series("", index=frame.index, dtype="object")
    flags = flags.where(~(raw_missing_or_zero & price_says_discount), "REVIEW_DISCOUNT_MISSING")
    flags = flags.where(~mapped_differs_from_price, "REVIEW_DISCOUNT_CONFLICT")
    return flags


def _date_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            values = pd.to_datetime(frame[column_name], errors="coerce")
            return values.dt.strftime("%Y-%m-%d").fillna("")
    return pd.Series("", index=frame.index, dtype="object")


def _build_file_manifest_row(
    *,
    run_id: str,
    as_of_date: str,
    file_type: str,
    file_path: str,
    frame: pd.DataFrame,
    store_number: object | None = None,
    promotion_header_key: object | None = None,
) -> dict[str, object]:
    action_column = "decision_recommendation" if "decision_recommendation" in frame.columns else "recommended_action"
    action_counts: dict[str, int] = {
        action: int((frame[action_column] == action).sum())
        for action in ACTION_ORDER
    } if action_column in frame.columns else {}
    return {
        "run_id": run_id,
        "as_of_date": as_of_date,
        "store_number": "" if store_number is None else str(store_number),
        "promotion_header_key": "" if promotion_header_key is None else str(promotion_header_key),
        "promotion_name": _first_value(frame["promotion_name"]) if "promotion_name" in frame.columns else "",
        "promotion_start_date": _first_value(frame["promotion_start_date"]) if "promotion_start_date" in frame.columns else "",
        "promotion_end_date": _first_value(frame["promotion_end_date"]) if "promotion_end_date" in frame.columns else "",
        "file_type": file_type,
        "file_path": file_path,
        "row_count": int(len(frame.index)),
        "unique_sku_count": int(frame["sku_number"].astype(str).nunique(dropna=True)) if "sku_number" in frame.columns else 0,
        "action_counts": json.dumps(action_counts, sort_keys=True),
        "review_row_count": int((frame[action_column] == "REVIEW").sum()) if action_column in frame.columns else 0,
        "review_required_row_count": int((frame[action_column] == "REVIEW").sum()) if action_column in frame.columns else 0,
        "order_row_count": action_counts.get("ORDER", 0),
        "hold_row_count": action_counts.get("HOLD", 0),
        "do_not_order_row_count": action_counts.get("DO_NOT_ORDER", 0),
        "created_at": _created_at_utc(),
    }


def _confidence_band(score: float) -> str:
    if score >= 0.8:
        return "HIGH"
    if score >= 0.55:
        return "MEDIUM"
    if score > 0.0:
        return "LOW"
    return "UNKNOWN"


def _cash_risk_band(value: float) -> str:
    if value >= 200.0:
        return "HIGH"
    if value >= 75.0:
        return "MEDIUM"
    if value > 0.0:
        return "LOW"
    return "MINIMAL"


def _execution_attention_flag(
    *,
    action_code: str,
    stockout_risk_flag: int,
    overstock_risk_flag: int,
    capital_tied_up_risk_flag: int,
    likely_inventory_drag_flag: int,
) -> str:
    if action_code == "REVIEW":
        return "REVIEW"
    if action_code == "ORDER" and stockout_risk_flag == 1:
        return "URGENT"
    if action_code == "DO_NOT_ORDER" or overstock_risk_flag == 1 or capital_tied_up_risk_flag == 1 or likely_inventory_drag_flag == 1:
        return "WATCH"
    return "LOW_PRIORITY"


def _created_at_utc() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def _primary_store_facing_csv_path(
    *,
    per_store_promotion_paths: list[str],
    per_store_paths: list[str],
    fallback_path: Path,
) -> str:
    if per_store_promotion_paths:
        return per_store_promotion_paths[0]
    if per_store_paths:
        return per_store_paths[0]
    return str(fallback_path)


@dataclass(frozen=True)
class _CommercialMessageBundle:
    promotion_effectiveness_signal: str
    action_code: str
    decision_reason: str
    client_reason: str
    operational_note: str
    coherence_rule: str
    contradiction_escalation_flag: int


def _build_commercial_message_bundle(
    *,
    inventory_missing: bool,
    low_confidence: bool,
    confidence_value: float,
    confidence_missing: bool,
    upstream_avoid: bool,
    elevated_leftover_risk: bool,
    stock_cover_days: float,
    start_gap_units: int,
    expected_leftover: int,
    expected_soh_at_promo_start: int,
    promo_start_target: int,
    base_units_target: int,
    predicted_total: int,
    forecast_flat_promotion_flag: bool,
    forecast_zero_demand_classification: str,
    forecast_collapse_requires_review_flag: bool,
    forecast_unresolved_collapse_reason: str,
    stockout_risk_flag: int,
    overstock_risk_flag: int,
) -> _CommercialMessageBundle:
    """Return deterministic premium commercial messaging for a store-facing recommendation row."""
    if predicted_total <= 0:
        effectiveness = "non_productive"
    elif forecast_flat_promotion_flag:
        effectiveness = "flat"
    elif overstock_risk_flag == 1:
        effectiveness = "weak"
    elif stockout_risk_flag == 1:
        effectiveness = "strong"
    else:
        effectiveness = "balanced"

    de_minimis_inventory_covered = (
        start_gap_units > 0
        and predicted_total > 0
        and predicted_total <= LOW_NONZERO_DEMAND_MAX_UNITS
        and expected_soh_at_promo_start >= predicted_total
    )

    if inventory_missing:
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="REVIEW",
            decision_reason=(
                "Review required: inventory inputs are incomplete, so order risk cannot be assessed confidently "
                f"for a promo-start target of {promo_start_target} units."
            ),
            client_reason=(
                "Review required: inventory inputs are incomplete, so the recommendation cannot be trusted without confirmation."
            ),
            operational_note=(
                "Action now: missing stock inputs require SOH and on-order verification before this row can leave REVIEW."
            ),
            coherence_rule="review_missing_inventory",
            contradiction_escalation_flag=0,
        )

    if forecast_collapse_requires_review_flag:
        unresolved_reason = forecast_unresolved_collapse_reason.strip() or "unresolved_forecast_pattern"
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="REVIEW",
            decision_reason=(
                "Review escalation: forecast quality is unresolved "
                f"({forecast_zero_demand_classification}; {unresolved_reason})."
            ),
            client_reason=(
                "Forecast reliability is not commercially dependable for auto-release; confirm local demand before ordering."
            ),
            operational_note=(
                "Action now: hold auto-buy, verify shelf movement and promo intent, then set quantity manually if justified."
            ),
            coherence_rule="review_unresolved_forecast_collapse",
            contradiction_escalation_flag=0,
        )

    if de_minimis_inventory_covered and (upstream_avoid or elevated_leftover_risk):
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="DO_NOT_ORDER",
            decision_reason=(
                "Do not order: projected promo-start stock "
                f"{expected_soh_at_promo_start} already covers the full expected promo demand of {predicted_total} units, "
                f"and a fresh buy would still leave {expected_leftover} leftover units."
            ),
            client_reason=(
                "Weak promotional demand is already covered by existing stock; do not tie up more cash in this SKU."
            ),
            operational_note=(
                "Action now: keep stock lean and only revisit this row if early promo sell-through materially exceeds the current weak-demand outlook."
            ),
            coherence_rule="do_not_order_low_incremental_value_inventory_covered",
            contradiction_escalation_flag=0,
        )

    if de_minimis_inventory_covered and (low_confidence or confidence_missing):
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="HOLD",
            decision_reason=(
                "Hold: projected promo-start stock "
                f"{expected_soh_at_promo_start} already covers the full expected promo demand of {predicted_total} units, "
                f"but confidence {confidence_value:.4f} is below release threshold for a fresh buy."
            ),
            client_reason=(
                "Demand is weak and existing stock already covers likely promo demand; monitor before buying more."
            ),
            operational_note=(
                "Action now: hold current inventory and only revisit quantity if early promo movement materially exceeds this low-demand expectation."
            ),
            coherence_rule="hold_inventory_covers_expected_low_confidence",
            contradiction_escalation_flag=0,
        )

    if low_confidence or confidence_missing:
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="REVIEW",
            decision_reason=(
                f"Review required: demand confidence {confidence_value:.4f} is below release threshold for an automatic buy decision."
            ),
            client_reason=(
                "Review required: confidence is below production threshold, so local store context should guide the final call."
            ),
            operational_note=(
                f"Action now: review start-gap {start_gap_units} units and projected leftover {expected_leftover} units before releasing order."
            ),
            coherence_rule="review_low_confidence",
            contradiction_escalation_flag=0,
        )

    if start_gap_units <= 0:
        if upstream_avoid or elevated_leftover_risk:
            return _CommercialMessageBundle(
                promotion_effectiveness_signal=effectiveness,
                action_code="DO_NOT_ORDER",
                decision_reason=(
                    f"Do not order: expected promo-start stock {expected_soh_at_promo_start} already covers target {promo_start_target}, "
                    f"with projected leftover risk of {expected_leftover} units."
                ),
                client_reason=(
                    "Limited promotional demand expected; ordering more stock risks tying up cash."
                ),
                operational_note=(
                    f"Action now: keep stock lean and redeploy working capital; current cover is {stock_cover_days:.1f} days."
                ),
                coherence_rule="do_not_order_excess_cover",
                contradiction_escalation_flag=0,
            )
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="HOLD",
            decision_reason=(
                f"Hold: expected promo-start stock {expected_soh_at_promo_start} already meets target {promo_start_target}."
            ),
            client_reason=(
                "Promotion appears balanced for this SKU; maintain current stock plan unless local demand shifts."
            ),
            operational_note=(
                f"Action now: monitor sell-through only; projected post-promo leftover is {expected_leftover} units."
            ),
            coherence_rule="hold_coverage_sufficient",
            contradiction_escalation_flag=0,
        )

    if upstream_avoid and elevated_leftover_risk:
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="REVIEW",
            decision_reason=(
                f"Review escalation: start-gap need ({start_gap_units} units) conflicts with high leftover risk ({expected_leftover} units)."
            ),
            client_reason=(
                "Contradictory commercial signals detected: protect availability without locking cash into likely dead stock."
            ),
            operational_note=(
                "Action now: use local demand knowledge and consider a controlled test quantity before full buy commitment."
            ),
            coherence_rule="review_gap_vs_leftover_conflict",
            contradiction_escalation_flag=1,
        )

    if stock_cover_days >= EXTREME_STOCK_COVER_DAYS_THRESHOLD and expected_leftover > base_units_target:
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="REVIEW",
            decision_reason=(
                f"Review escalation: stock cover is {stock_cover_days:.1f} days and incremental ordering still leaves {expected_leftover} leftover units."
            ),
            client_reason=(
                "Promotion effect appears weak for this SKU; keep stock lean unless store knowledge suggests otherwise."
            ),
            operational_note=(
                "Action now: validate stock integrity and transfer options before any additional order release."
            ),
            coherence_rule="review_extreme_stock_cover",
            contradiction_escalation_flag=1,
        )

    if overstock_risk_flag == 1:
        return _CommercialMessageBundle(
            promotion_effectiveness_signal=effectiveness,
            action_code="REVIEW",
            decision_reason=(
                f"Review escalation: a {start_gap_units} unit start-gap exists, but projected leftover remains high at {expected_leftover} units."
            ),
            client_reason=(
                "Likely capital trap risk: resolve quantity manually before release."
            ),
            operational_note=(
                "Action now: reduce buy quantity or hold this SKU for manual commercial review."
            ),
            coherence_rule="review_high_leftover_risk",
            contradiction_escalation_flag=1,
        )

    return _CommercialMessageBundle(
        promotion_effectiveness_signal=effectiveness,
        action_code="ORDER",
        decision_reason=(
            f"Strong promotion support expected; current stock is likely short by {start_gap_units} units at promo start."
        ),
        client_reason=(
            "Order now to protect promo availability while keeping projected post-promo leftover controlled."
        ),
        operational_note=(
            f"Action now: release suggested order to close start-gap; expected leftover after promo is {expected_leftover} units."
        ),
        coherence_rule="order_closes_start_gap",
        contradiction_escalation_flag=0,
    )


def _derive_row_level_commercial_decisions(
    *,
    calc_frame: pd.DataFrame,
    output_index: pd.Index,
) -> dict[str, pd.Series]:
    """Compute row-level commercial actions, risks, and explanation text.

    This isolates the recommendation decision tree from download-frame assembly
    so the core builder remains orchestration-focused and easier to reason about.
    """
    suggested_order_units: list[int] = []
    expected_leftover_units_end_of_promo: list[int] = []
    stockout_risk_flag_values: list[int] = []
    overstock_risk_flag_values: list[int] = []
    capital_tied_up_risk_flag_values: list[int] = []
    promotion_effectiveness_signal_values: list[str] = []
    decision_recommendation_values: list[str] = []
    decision_reason_values: list[str] = []
    client_reason_values: list[str] = []
    operational_note_values: list[str] = []
    commercial_coherence_rule_values: list[str] = []
    commercial_contradiction_escalation_values: list[int] = []
    true_zero_demand_retained_values: list[int] = []
    likely_inventory_drag_values: list[int] = []
    estimated_cash_risk_band_values: list[str] = []
    demand_confidence_band_values: list[str] = []
    execution_attention_flag_values: list[str] = []
    forecast_quality_flag_values: list[str] = []
    forecast_reliability_band_values: list[str] = []
    demand_shape_flag_values: list[str] = []
    promo_lift_expectation_flag_values: list[str] = []
    demand_evidence_class_values: list[str] = []
    cold_start_flag_values: list[int] = []
    insufficient_history_flag_values: list[int] = []
    publish_eligibility_reason_values: list[str] = []
    review_reason_values: list[str] = []

    for row in calc_frame.itertuples(index=False):
        expected_soh_at_promo_start = max(
            int(row.current_soh_units) + int(row.qty_on_order_units) - int(row.predicted_until_start),
            0,
        )
        start_gap_units = max(int(row.promo_start_target) - expected_soh_at_promo_start, 0)
        expected_leftover = max(
            expected_soh_at_promo_start + start_gap_units - int(row.predicted_total),
            0,
        )
        daily_rate = max(
            float(row.predicted_total or 0.0) / max(float(row.promo_window_days or 1.0), 1.0),
            0.01,
        )
        stock_cover_days = min(
            (int(row.current_soh_units) + int(row.qty_on_order_units)) / daily_rate,
            CURRENT_STOCK_COVER_DAYS_CAP,
        )
        confidence_missing = pd.isna(row.final_confidence_score)
        confidence_value = 0.0 if confidence_missing else float(row.final_confidence_score)
        low_confidence = (not confidence_missing) and confidence_value < LOW_CONFIDENCE_THRESHOLD
        upstream_avoid = str(row.decision_recommendation).strip().lower() == "avoid"
        elevated_leftover_risk = bool(
            float(row.leftover_risk_penalty or 0.0) >= 0.70
            or expected_leftover >= max(int(row.base_units_target), math.ceil(int(row.predicted_total) * 0.35), 4)
        )
        stockout_risk_flag = int(start_gap_units > 0 and int(row.predicted_first_7) > max(expected_soh_at_promo_start, 0))
        overstock_risk_flag = int(elevated_leftover_risk)
        capital_tied_up_risk_flag = int(overstock_risk_flag == 1 and (expected_leftover * float(row.unit_cost or 0.0)) >= 20.0)
        forecast_zero_demand_classification = str(
            getattr(row, "forecast_zero_demand_classification", FORECAST_ZERO_DEMAND_HEALTHY)
        )
        forecast_collapse_requires_review_flag = bool(
            getattr(row, "forecast_collapse_requires_review_flag", False)
        )
        forecast_unresolved_collapse_reason = str(
            getattr(row, "forecast_unresolved_collapse_reason", "") or ""
        )

        true_zero_demand_retained_flag = int(int(row.predicted_total) <= 0)
        likely_inventory_drag_flag = int(
            expected_leftover >= max(int(row.base_units_target), 2)
            and int(row.predicted_total) <= max(int(row.base_units_target), 2)
        )
        demand_classification = classify_demand_evidence_row(
            {
                "predicted_units_total_promo": row.predicted_total,
                "forecast_zero_demand_classification": forecast_zero_demand_classification,
                "forecast_collapse_requires_review_flag": forecast_collapse_requires_review_flag,
                "raw_history_units": getattr(row, "raw_history_units", 0.0),
                "raw_predicted_units_sold": getattr(row, "raw_predicted_units_sold", 0.0),
                "raw_demand_reference_units": getattr(row, "raw_demand_reference_units", 0.0),
                "raw_baseline_expected_units": getattr(row, "raw_baseline_expected_units", 0.0),
                "promotion_name": getattr(row, "promotion_name", ""),
                "promo_type": getattr(row, "promo_type", ""),
                "promotion_header_key": getattr(row, "promotion_header_key", ""),
            }
        )
        window_blend_conflict = float(getattr(row, "window_blend_conflict_score", 0.0) or 0.0)
        uplift_order_confidence = float(getattr(row, "uplift_order_confidence", 0.0) or 0.0)
        discount_evidence_strength_score = float(getattr(row, "discount_evidence_strength_score", 0.0) or 0.0)
        elasticity_confidence_score = float(getattr(row, "elasticity_confidence_score", 0.0) or 0.0)
        same_discount_history_available_flag = float(getattr(row, "same_discount_history_available_flag", 0.0) or 0.0)
        launch_stock_support_score = float(getattr(row, "launch_stock_support_score", 0.0) or 0.0)
        discount_support_signals_present = bool(getattr(row, "discount_support_signals_present", False))

        message_bundle = _build_commercial_message_bundle(
            inventory_missing=bool(row.inventory_missing),
            low_confidence=low_confidence,
            confidence_value=confidence_value,
            confidence_missing=confidence_missing,
            upstream_avoid=upstream_avoid,
            elevated_leftover_risk=elevated_leftover_risk,
            stock_cover_days=stock_cover_days,
            start_gap_units=start_gap_units,
            expected_leftover=expected_leftover,
            expected_soh_at_promo_start=expected_soh_at_promo_start,
            promo_start_target=int(row.promo_start_target),
            base_units_target=int(row.base_units_target),
            predicted_total=int(row.predicted_total),
            forecast_flat_promotion_flag=bool(row.forecast_flat_promotion_flag),
            forecast_zero_demand_classification=forecast_zero_demand_classification,
            forecast_collapse_requires_review_flag=forecast_collapse_requires_review_flag,
            forecast_unresolved_collapse_reason=forecast_unresolved_collapse_reason,
            stockout_risk_flag=stockout_risk_flag,
            overstock_risk_flag=overstock_risk_flag,
        )
        publish_eligibility_reason = demand_classification.publish_eligibility_reason
        review_reason = demand_classification.review_reason
        action_code = message_bundle.action_code
        decision_reason = message_bundle.decision_reason
        client_reason = message_bundle.client_reason
        operational_note = message_bundle.operational_note
        if demand_classification.demand_evidence_class == DEMAND_EVIDENCE_CLASS_TRUE_ZERO:
            action_code = "DO_NOT_ORDER"
            start_gap_units = 0
            expected_leftover = max(expected_soh_at_promo_start - int(row.predicted_total), 0)
            decision_reason = (
                "Do not order: demand is classified as true_zero_demand with no reliable promotional movement signal."
            )
            client_reason = (
                "No promotional uplift is evidenced for this row; preserve cash and keep stock lean."
            )
            operational_note = "Action now: keep this row out of auto-order flow and monitor local movement only."
        elif demand_classification.demand_evidence_class == DEMAND_EVIDENCE_CLASS_COLD_START:
            action_code = "REVIEW"
            decision_reason = (
                "Review required: cold_start_new_line classification indicates insufficient history to auto-release quantity."
            )
            client_reason = (
                "New-line demand evidence is limited; set quantity manually using local commercial context."
            )
            operational_note = "Action now: verify launch support and shelf commitment before any order release."
        elif demand_classification.demand_evidence_class == DEMAND_EVIDENCE_CLASS_ARTIFICIAL_COLLAPSE:
            action_code = "REVIEW"
            decision_reason = (
                "Review escalation: artificial_collapse detected in forecast evidence and requires manual decision."
            )
            client_reason = (
                "Forecast evidence is inconsistent for auto-release; resolve collapse cause before ordering."
            )
            operational_note = "Action now: isolate this row for remediation and do not auto-publish quantity."
        elif (
            start_gap_units > 0
            and window_blend_conflict >= 0.55
            and uplift_order_confidence < 0.55
        ):
            action_code = "REVIEW"
            decision_reason = (
                "Review escalation: total-window demand pressure materially exceeds launch-window support, so auto-ordering risks blending hold stock with promo uplift."
            )
            client_reason = (
                "Launch demand support is weaker than the total-promo signal; confirm replenishment timing before releasing quantity."
            )
            operational_note = (
                "Action now: separate lead-up cover, launch need, and full-promo holding requirement before ordering this SKU."
            )
        elif (
            start_gap_units > 0
            and action_code == "ORDER"
            and discount_support_signals_present
            and same_discount_history_available_flag <= 0.0
            and elasticity_confidence_score < 0.35
            and discount_evidence_strength_score < 0.45
            and launch_stock_support_score < 0.55
        ):
            action_code = "REVIEW"
            decision_reason = (
                "Review escalation: same-discount support is missing and elasticity evidence is weak, so the launch buy cannot be justified from broad promo demand alone."
            )
            client_reason = (
                "Historical discount evidence is too weak for auto-release; confirm store-specific demand before ordering."
            )
            operational_note = (
                "Action now: verify whether launch stock is supported by local same-SKU evidence before releasing this order."
            )

        if (
            action_code == "DO_NOT_ORDER"
            and message_bundle.coherence_rule == "do_not_order_low_incremental_value_inventory_covered"
        ):
            publish_eligibility_reason = PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_DO_NOT_ORDER_LOW_INCREMENTAL_VALUE
            review_reason = ""
        elif (
            action_code == "HOLD"
            and message_bundle.coherence_rule == "hold_inventory_covers_expected_low_confidence"
        ):
            publish_eligibility_reason = PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_HOLD_INVENTORY_SUFFICIENT
            review_reason = ""

        estimated_cash_risk_band = _cash_risk_band(expected_leftover * float(row.unit_cost or 0.0))
        demand_confidence_band = _confidence_band(confidence_value)
        execution_attention_flag = _execution_attention_flag(
            action_code=action_code,
            stockout_risk_flag=stockout_risk_flag,
            overstock_risk_flag=overstock_risk_flag,
            capital_tied_up_risk_flag=capital_tied_up_risk_flag,
            likely_inventory_drag_flag=likely_inventory_drag_flag,
        )

        if forecast_zero_demand_classification == FORECAST_ZERO_DEMAND_TRUE:
            forecast_quality_flag = "NO_REAL_PROMO_DEMAND"
            demand_shape_flag = "HONEST_ZERO"
            promo_lift_expectation_flag = "NONE_EXPECTED"
        elif forecast_zero_demand_classification == FORECAST_ZERO_DEMAND_LOW_NONZERO:
            forecast_quality_flag = "LOW_NONZERO_DEMAND"
            demand_shape_flag = "LOW_NONZERO"
            promo_lift_expectation_flag = "WEAK_LIFT"
        elif forecast_zero_demand_classification == FORECAST_ZERO_DEMAND_COHORT_FLAT:
            forecast_quality_flag = "UNCERTAIN_FLAT_PATTERN"
            demand_shape_flag = "COHORT_FLATNESS"
            promo_lift_expectation_flag = "UNCERTAIN_LIFT"
        elif forecast_zero_demand_classification in {
            FORECAST_ZERO_DEMAND_COLLAPSED,
            FORECAST_ZERO_DEMAND_ROUNDING,
        }:
            forecast_quality_flag = "UNCERTAIN_FLAT_PATTERN"
            demand_shape_flag = "ROW_SIGNAL_VARIATION"
            promo_lift_expectation_flag = "UNCERTAIN_LIFT"
        else:
            forecast_quality_flag = "ACTIONABLE_FORECAST"
            demand_shape_flag = "ROW_SIGNAL_VARIATION"
            promo_lift_expectation_flag = "MATERIAL_LIFT"

        if confidence_missing:
            forecast_reliability_band = "UNKNOWN"
        elif confidence_value >= 0.8:
            forecast_reliability_band = "HIGH"
        elif confidence_value >= 0.55:
            forecast_reliability_band = "MEDIUM"
        else:
            forecast_reliability_band = "LOW"

        suggested_order_units.append(start_gap_units)
        expected_leftover_units_end_of_promo.append(expected_leftover)
        stockout_risk_flag_values.append(stockout_risk_flag)
        overstock_risk_flag_values.append(overstock_risk_flag)
        capital_tied_up_risk_flag_values.append(capital_tied_up_risk_flag)
        promotion_effectiveness_signal_values.append(message_bundle.promotion_effectiveness_signal)
        decision_recommendation_values.append(action_code)
        decision_reason_values.append(decision_reason)
        client_reason_values.append(client_reason)
        operational_note_values.append(operational_note)
        commercial_coherence_rule_values.append(message_bundle.coherence_rule)
        commercial_contradiction_escalation_values.append(message_bundle.contradiction_escalation_flag)
        true_zero_demand_retained_values.append(true_zero_demand_retained_flag)
        likely_inventory_drag_values.append(likely_inventory_drag_flag)
        estimated_cash_risk_band_values.append(estimated_cash_risk_band)
        demand_confidence_band_values.append(demand_confidence_band)
        execution_attention_flag_values.append(execution_attention_flag)
        forecast_quality_flag_values.append(forecast_quality_flag)
        forecast_reliability_band_values.append(forecast_reliability_band)
        demand_shape_flag_values.append(demand_shape_flag)
        promo_lift_expectation_flag_values.append(promo_lift_expectation_flag)
        demand_evidence_class_values.append(demand_classification.demand_evidence_class)
        cold_start_flag_values.append(int(demand_classification.cold_start_flag))
        insufficient_history_flag_values.append(int(demand_classification.insufficient_history_flag))
        publish_eligibility_reason_values.append(publish_eligibility_reason)
        review_reason_values.append(review_reason)

    return {
        "suggested_order_units": pd.Series(suggested_order_units, index=output_index, dtype="int64"),
        "expected_leftover_units_end_of_promo": pd.Series(
            expected_leftover_units_end_of_promo,
            index=output_index,
            dtype="int64",
        ),
        "stockout_risk_flag": pd.Series(stockout_risk_flag_values, index=output_index, dtype="int64"),
        "overstock_risk_flag": pd.Series(overstock_risk_flag_values, index=output_index, dtype="int64"),
        "capital_tied_up_risk_flag": pd.Series(
            capital_tied_up_risk_flag_values,
            index=output_index,
            dtype="int64",
        ),
        "estimated_cash_risk_band": pd.Series(estimated_cash_risk_band_values, index=output_index, dtype="object"),
        "demand_confidence_band": pd.Series(demand_confidence_band_values, index=output_index, dtype="object"),
        "execution_attention_flag": pd.Series(execution_attention_flag_values, index=output_index, dtype="object"),
        "forecast_quality_flag": pd.Series(forecast_quality_flag_values, index=output_index, dtype="object"),
        "forecast_reliability_band": pd.Series(forecast_reliability_band_values, index=output_index, dtype="object"),
        "demand_shape_flag": pd.Series(demand_shape_flag_values, index=output_index, dtype="object"),
        "promo_lift_expectation_flag": pd.Series(promo_lift_expectation_flag_values, index=output_index, dtype="object"),
        "demand_evidence_class": pd.Series(demand_evidence_class_values, index=output_index, dtype="object"),
        "cold_start_flag": pd.Series(cold_start_flag_values, index=output_index, dtype="int64"),
        "insufficient_history_flag": pd.Series(insufficient_history_flag_values, index=output_index, dtype="int64"),
        "publish_eligibility_reason": pd.Series(publish_eligibility_reason_values, index=output_index, dtype="object"),
        "review_reason": pd.Series(review_reason_values, index=output_index, dtype="object"),
        "promotion_effectiveness_signal": pd.Series(
            promotion_effectiveness_signal_values,
            index=output_index,
            dtype="object",
        ),
        "decision_recommendation": pd.Series(decision_recommendation_values, index=output_index, dtype="object"),
        "decision_reason": pd.Series(decision_reason_values, index=output_index, dtype="object"),
        "client_reason": pd.Series(client_reason_values, index=output_index, dtype="object"),
        "operational_note": pd.Series(operational_note_values, index=output_index, dtype="object"),
        "commercial_coherence_rule": pd.Series(commercial_coherence_rule_values, index=output_index, dtype="object"),
        "commercial_contradiction_escalation_flag": pd.Series(
            commercial_contradiction_escalation_values,
            index=output_index,
            dtype="int64",
        ),
        "true_zero_demand_retained_flag": pd.Series(true_zero_demand_retained_values, index=output_index, dtype="int64"),
        "likely_inventory_drag_flag": pd.Series(likely_inventory_drag_values, index=output_index, dtype="int64"),
    }


def _apply_discount_review_hold_to_decision_outputs(
    *,
    decision_outputs: dict[str, pd.Series],
    discount_review_flag: pd.Series,
) -> dict[str, pd.Series]:
    """Fail closed when governed discount evidence requires review.

    Only rows already headed to ORDER are demoted. Safe non-buy outcomes remain
    untouched, and the helper uses explicit discount-review flags rather than
    quantity or forecast magnitude as an action proxy.
    """

    adjusted_outputs = dict(decision_outputs)
    action_upper = adjusted_outputs["decision_recommendation"].astype(str).str.strip().str.upper()
    review_flag = discount_review_flag.reindex(action_upper.index).fillna("").astype(str).str.strip().str.upper()
    discount_review_order_mask = action_upper.eq("ORDER") & review_flag.isin(_DISCOUNT_REVIEW_REASON_BY_FLAG)
    if not bool(discount_review_order_mask.any()):
        return adjusted_outputs

    review_reason = review_flag.map(_DISCOUNT_REVIEW_REASON_BY_FLAG).fillna("")
    decision_reason = review_flag.map(_DISCOUNT_REVIEW_DECISION_REASON_BY_FLAG).fillna(
        "Review required: governed discount evidence requires manual review before order release."
    )
    adjusted_outputs["decision_recommendation"] = adjusted_outputs["decision_recommendation"].where(
        ~discount_review_order_mask,
        "REVIEW",
    )
    adjusted_outputs["decision_reason"] = adjusted_outputs["decision_reason"].where(
        ~discount_review_order_mask,
        decision_reason,
    )
    adjusted_outputs["client_reason"] = adjusted_outputs["client_reason"].where(
        ~discount_review_order_mask,
        "Governed discount evidence requires manager review before any auto-order release.",
    )
    adjusted_outputs["operational_note"] = adjusted_outputs["operational_note"].where(
        ~discount_review_order_mask,
        "Action now: hold auto-order and resolve the governed discount evidence before releasing stock.",
    )
    adjusted_outputs["review_reason"] = adjusted_outputs["review_reason"].where(
        ~discount_review_order_mask,
        review_reason,
    )
    return adjusted_outputs


def _sanitize_filename_component(value: str, *, fallback: str, max_length: int = 64) -> str:
    candidate = value.strip().lower()
    candidate = re.sub(r"[^a-z0-9]+", "_", candidate)
    candidate = candidate.strip("_")
    if not candidate:
        candidate = fallback
    return candidate[:max_length]


def _sortable_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str)


def _sync_fractional_promo_attrs(frame: pd.DataFrame) -> None:
    values = frame.attrs.get("predicted_units_total_promo_fractional")
    if isinstance(values, list) and len(values) != len(frame.index):
        frame.attrs.pop("predicted_units_total_promo_fractional", None)


def _resolve_fractional_promo_units_series(frame: pd.DataFrame) -> pd.Series | None:
    column = frame.get("predicted_units_total_promo_fractional")
    if column is not None:
        return pd.to_numeric(column, errors="coerce")
    values = frame.attrs.get("predicted_units_total_promo_fractional")
    if isinstance(values, list) and len(values) == len(frame.index):
        return pd.Series(values, index=frame.index, dtype="float64")
    return None


def _round_non_negative_units(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0)
    return numeric.round(0).astype("int64")


def _integerize_forecast_total_units(series: pd.Series) -> pd.Series:
    """Display/order-support integer rounding for forecast totals.

    Canonical demand fields come from the governed demand contract and preserve
    fractional model output. This helper must not be used as contract input.
    """
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0)
    converted = [
        0 if float(value) <= 0.0 else max(int(round(float(value))), 1)
        for value in numeric.tolist()
    ]
    return pd.Series(converted, index=series.index, dtype="int64")


def _forecast_units_for_window(*, daily_units: float, window_days: float, positive_floor: bool) -> int:
    raw_value = max(daily_units, 0.0) * max(window_days, 0.0)
    if raw_value <= 0.0:
        return 0
    rounded = int(round(raw_value))
    if positive_floor and rounded <= 0:
        return 1
    return max(rounded, 0)


def _build_promotion_header_key_series(
    *,
    promotion_id: pd.Series,
    promotion_name: pd.Series,
    promotion_start_date: pd.Series,
    promotion_end_date: pd.Series,
    promo_type: pd.Series,
) -> pd.Series:
    promotion_id_clean = promotion_id.fillna("").astype(str).str.strip()
    promotion_id_clean = promotion_id_clean.where(
        ~promotion_id_clean.str.lower().isin({"", "nan", "none", "<na>"}),
        "",
    )
    header_key = (
        promotion_name.fillna("").astype(str).str.strip()
        + "|"
        + promotion_start_date.fillna("").astype(str).str.strip()
        + "|"
        + promotion_end_date.fillna("").astype(str).str.strip()
        + "|"
        + promo_type.fillna("").astype(str).str.strip()
    )
    header_key = header_key.apply(lambda value: _sanitize_filename_component(value, fallback="promotion", max_length=80))
    return promotion_id_clean.where(promotion_id_clean != "", header_key)


def _first_value(series: pd.Series) -> str:
    if series.empty:
        return ""
    return str(series.iloc[0])


def _store_int(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0)
    return numeric.round(0).astype("int64")


def _store_facing_truthy(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    return text in {"true", "t", "yes", "y", "1"}


def _join_diagnostics_to_commercial(
    commercial_frame: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Left-join per-row forecast diagnostics onto the commercial frame on natural keys."""
    keys = ["store_number", "promotion_header_key", "sku_number"]
    left = commercial_frame[keys].copy()
    for column in keys:
        left[column] = left[column].astype(str)
    right = diagnostics.copy()
    for column in keys:
        if column not in right.columns:
            right[column] = ""
        right[column] = right[column].astype(str)
    right = right.drop_duplicates(subset=keys, keep="first")
    left["__row_order__"] = range(len(left.index))
    merged = left.merge(right, on=keys, how="left")
    merged = merged.sort_values("__row_order__").reset_index(drop=True)
    merged.index = commercial_frame.index
    return merged


def _clean_reason_phrase(value: object) -> str:
    """Trim, collapse whitespace, and strip noise tokens / leading labels / trailing punctuation."""
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ").strip()
    if not text or text.lower() in {"none", "n/a", "nan", "null", "<na>"}:
        return ""
    text = re.sub(r"\s+", " ", text)
    # Strip recurring upstream label prefixes that duplicate the headline action verb.
    text = re.sub(
        r"(?i)^(operational note|note|reason|client reason|decision reason|recommendation reason|review required|manager review needed|order recommended|hold current position|do not order)\s*[:\-\u2013]\s*",
        "",
        text,
    )
    # Collapse stacked punctuation introduced by upstream concatenation ("foo.." / "foo. .").
    text = re.sub(r"\s*\.\s*\.+", ".", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = text.strip(" .;,-\t")
    if not text:
        return ""
    return text[0].upper() + text[1:]


def _compose_model_reason_summary(
    frame: pd.DataFrame,
    *,
    action: pd.Series | None = None,
    gap_units: pd.Series | None = None,
    lead_days: pd.Series | None = None,
    expected_total_promo: pd.Series | None = None,
    leftover_units: pd.Series | None = None,
    capital_at_risk: pd.Series | None = None,
    demand_evidence_class: pd.Series | None = None,
    confidence_band: pd.Series | None = None,
) -> pd.Series:
    """Plain-English single-sentence rationale for store operators.

    Each line follows a deterministic three-clause shape:
      1. Action verb prefix (Order recommended / Manager review needed / Hold / Do not order).
      2. Templated commercial driver derived from local Stage 11 data
         (start-gap, lead time, projected total demand, projected leftover,
         capital at risk, demand evidence, confidence). This is the trustworthy core.
      3. Optional upstream client/decision rationale, used only as a secondary hint
         when it adds new information not already conveyed by the templated clause.
    """
    n = len(frame.index)
    if action is None:
        action = frame["decision_recommendation"].astype(str).str.upper().str.strip()
    else:
        action = action.astype(str).str.upper().str.strip()

    def _fallback_int(series: pd.Series | None, source_col: str) -> pd.Series:
        if series is not None:
            return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)
        if source_col in frame.columns:
            return pd.to_numeric(frame[source_col], errors="coerce").fillna(0).astype(int)
        return pd.Series([0] * n, index=frame.index, dtype=int)

    def _fallback_float(series: pd.Series | None, source_col: str) -> pd.Series:
        if series is not None:
            return pd.to_numeric(series, errors="coerce").fillna(0.0)
        if source_col in frame.columns:
            return pd.to_numeric(frame[source_col], errors="coerce").fillna(0.0)
        return pd.Series([0.0] * n, index=frame.index, dtype=float)

    def _fallback_str(series: pd.Series | None, source_col: str) -> pd.Series:
        if series is not None:
            return series.astype(str)
        if source_col in frame.columns:
            return frame[source_col].astype(str)
        return pd.Series(["unknown"] * n, index=frame.index, dtype=object)

    gap_series = _fallback_int(gap_units, "gap_to_day_one_target_units")
    lead_series = _fallback_int(lead_days, "lead_days_to_promo_start")
    total_series = _fallback_int(expected_total_promo, "predicted_units_total_promo")
    leftover_series = _fallback_int(leftover_units, "expected_leftover_units_end_of_promo")
    capital_series = _fallback_float(capital_at_risk, "estimated_leftover_cost_dollars")
    evidence_series = _fallback_str(demand_evidence_class, "demand_evidence_class").str.lower()
    confidence_series = _fallback_str(confidence_band, "demand_confidence_band").str.upper()

    client_reason = frame["client_reason"] if "client_reason" in frame.columns else pd.Series([""] * n, index=frame.index)
    decision_reason = frame["decision_reason"] if "decision_reason" in frame.columns else pd.Series([""] * n, index=frame.index)

    prefixes = {
        "ORDER": "Order recommended",
        "REVIEW": "Manager review needed",
        "HOLD": "Hold current position",
        "DO_NOT_ORDER": "Do not order",
    }

    summaries: list[str] = []
    for (
        act,
        gap,
        lead,
        total_units,
        leftover,
        capital,
        evidence,
        confidence,
        upstream_client,
        upstream_decision,
    ) in zip(
        action.tolist(),
        gap_series.tolist(),
        lead_series.tolist(),
        total_series.tolist(),
        leftover_series.tolist(),
        capital_series.tolist(),
        evidence_series.tolist(),
        confidence_series.tolist(),
        client_reason.tolist(),
        decision_reason.tolist(),
        strict=False,
    ):
        prefix = prefixes.get(act, "Action recommended")
        driver = _compose_commercial_driver_clause(
            action=act,
            gap_units=int(gap),
            lead_days=int(lead),
            expected_total_promo=int(total_units),
            leftover_units=int(leftover),
            capital_at_risk=float(capital),
            demand_evidence_class=str(evidence),
            confidence_band=str(confidence),
        )
        upstream = _clean_reason_phrase(upstream_client) or _clean_reason_phrase(upstream_decision)
        if upstream:
            # Drop upstream tail if it merely restates the templated driver.
            normalized_driver = driver.lower()
            normalized_upstream = upstream.lower()
            tokens_in_common = sum(
                1 for tok in {"gap", "leftover", "review", "stockout", "overstock", "demand", "confidence"}
                if tok in normalized_driver and tok in normalized_upstream
            )
            if tokens_in_common >= 2 or normalized_upstream in normalized_driver:
                upstream = ""

        parts = [prefix, driver]
        if upstream:
            parts.append(upstream)
        sentence = ". ".join(p for p in parts if p) + "."
        sentence = re.sub(r"\s+", " ", sentence)
        sentence = re.sub(r"\.{2,}", ".", sentence)
        sentence = re.sub(r"\s+([,.;:])", r"\1", sentence).strip()
        if len(sentence) > 480:
            sentence = sentence[:477].rstrip(" .,;:") + "."
        summaries.append(sentence)
    return pd.Series(summaries, index=frame.index, dtype=object)


def _compose_commercial_driver_clause(
    *,
    action: str,
    gap_units: int,
    lead_days: int,
    expected_total_promo: int,
    leftover_units: int,
    capital_at_risk: float,
    demand_evidence_class: str,
    confidence_band: str,
) -> str:
    """Build the central commercial-driver sentence from local Stage 11 metrics.

    Deterministic, plain-English, never empty. Built from numeric facts so it does
    not depend on upstream prose quality.
    """
    evidence_phrase = {
        "healthy_nonzero_demand": "demand history supports the forecast",
        "low_nonzero_demand": "demand history is thin",
        "true_zero_demand": "no historical demand observed for this SKU",
        "insufficient_history": "history is too short to confirm the forecast",
    }.get(demand_evidence_class, "demand evidence is available")

    confidence_phrase = {
        "HIGH": "confidence is high",
        "MEDIUM": "confidence is moderate",
        "LOW": "confidence is low",
        "UNKNOWN": "confidence has not been scored",
    }.get(confidence_band, "confidence is moderate")

    if action == "ORDER":
        if gap_units > 0:
            core = (
                f"Day-one stock is {gap_units} unit(s) short of the target with "
                f"{lead_days} day(s) of lead time"
            )
        else:
            core = "Day-one stock is on target but additional cover is needed for the promo window"
        if expected_total_promo > 0:
            core += f"; total promo demand is forecast at {expected_total_promo} unit(s)"
        if leftover_units > 0 and capital_at_risk > 0:
            core += (
                f", with projected leftover of {leftover_units} unit(s) and "
                f"approximately ${capital_at_risk:.0f} of capital at risk"
            )
    elif action == "REVIEW":
        core_bits: list[str] = []
        if gap_units > 0:
            core_bits.append(f"day-one stock is {gap_units} unit(s) short of target")
        if leftover_units > 0:
            core_bits.append(f"projected leftover is {leftover_units} unit(s)")
        if capital_at_risk > 0:
            core_bits.append(f"approximately ${capital_at_risk:.0f} of capital at risk")
        core_bits.append(confidence_phrase)
        core = "Hold for manager review: " + ", ".join(core_bits)
        if lead_days > 0:
            core += f"; {lead_days} day(s) of lead time remain"
    elif action == "HOLD":
        core = (
            f"Stock position is adequate for the current forecast; no order needed today "
            f"({evidence_phrase}, {confidence_phrase})"
        )
        if lead_days > 0:
            core += f". Re-check in {min(lead_days, 7)} day(s)"
    elif action == "DO_NOT_ORDER":
        core = (
            f"Forecast does not justify additional stock for this promo "
            f"({evidence_phrase}; {confidence_phrase})"
        )
        if leftover_units > 0:
            core += f"; ordering would add an estimated {leftover_units} unit(s) of leftover"
    else:
        core = f"Forecast available; {evidence_phrase} and {confidence_phrase}"
    return core.strip()


def _compose_historical_response_summary(
    *,
    commercial_frame: pd.DataFrame,
    forecast_per_row_diagnostics: pd.DataFrame | None,
) -> pd.Series:
    del forecast_per_row_diagnostics
    historical = _resolve_historical_discount_frame(commercial_frame)
    insufficient_history = pd.to_numeric(
        commercial_frame.get(
            "insufficient_history_flag",
            pd.Series([0] * len(commercial_frame.index), index=commercial_frame.index),
        ),
        errors="coerce",
    ).fillna(0).astype(int)
    cold_start = pd.to_numeric(
        commercial_frame.get(
            "cold_start_flag",
            pd.Series([0] * len(commercial_frame.index), index=commercial_frame.index),
        ),
        errors="coerce",
    ).fillna(0).astype(int)
    evidence_class = commercial_frame.get(
        "demand_evidence_class",
        pd.Series([""] * len(commercial_frame.index), index=commercial_frame.index),
    ).astype(str).str.strip().str.lower()
    thin_history = (
        insufficient_history.eq(1)
        | cold_start.eq(1)
        | evidence_class.isin(("low_nonzero_demand", "insufficient_history", "cold_start", "sparse_history"))
    )
    summaries: list[str] = []
    for same_count, same_avg, better_count, better_avg, thin_history_flag in zip(
        historical["historical_promo_events_same_discount"].tolist(),
        historical["historical_units_same_discount_avg"].tolist(),
        historical["historical_promo_events_same_or_better_discount"].tolist(),
        historical["historical_units_same_or_better_discount_avg"].tolist(),
        thin_history.tolist(),
        strict=False,
    ):
        same_count_int = int(same_count or 0)
        better_count_int = int(better_count or 0)
        same_avg_float = float(same_avg or 0.0)
        better_avg_float = float(better_avg or 0.0)
        if same_count_int > 0:
            if same_avg_float <= 0.0:
                text = (
                    "Matching promo history exists but sold 0.0 units on average across "
                    f"{same_count_int} same-discount event(s)."
                )
            else:
                text = (
                    f"Matching promo history shows {same_count_int} same-discount event(s), "
                    f"avg {same_avg_float:.1f} units."
                )
        elif better_count_int > 0:
            if better_avg_float <= 0.0:
                text = (
                    "No exact same-discount history; matching promo history exists but sold 0.0 units on average across "
                    f"{better_count_int} same-or-better-discount event(s)."
                )
            else:
                text = (
                    "No exact same-discount history; matching promo history shows "
                    f"{better_count_int} same-or-better-discount event(s), avg {better_avg_float:.1f} units."
                )
        else:
            text = "No matching promo history available"
        if bool(thin_history_flag) and (same_count_int > 0 or better_count_int > 0):
            text += " Thin history; treat this as directional only."
        summaries.append(text)
    return pd.Series(summaries, index=commercial_frame.index, dtype=object)


def _resolve_unit_cost_series(
    *,
    commercial_frame: pd.DataFrame,
    forecast_per_row_diagnostics: pd.DataFrame | None,
) -> pd.Series:
    units = pd.to_numeric(commercial_frame["suggested_order_units"], errors="coerce").fillna(0.0)
    value = pd.to_numeric(commercial_frame["suggested_order_value"], errors="coerce").fillna(0.0)
    inferred = (value / units.where(units > 0)).fillna(0.0)
    if forecast_per_row_diagnostics is not None and not forecast_per_row_diagnostics.empty:
        diag = _join_diagnostics_to_commercial(commercial_frame, forecast_per_row_diagnostics)
        if "promo_unit_cost" in diag.columns:
            cost = pd.to_numeric(diag["promo_unit_cost"], errors="coerce").fillna(0.0).clip(lower=0.0)
            inferred = inferred.where(inferred > 0, cost)
    return inferred.clip(lower=0.0)


def _stockout_risk_band(
    *,
    stockout_flag: pd.Series,
    target_day_one: pd.Series,
    effective: pd.Series,
) -> pd.Series:
    target = pd.to_numeric(target_day_one, errors="coerce").fillna(0.0)
    eff = pd.to_numeric(effective, errors="coerce").fillna(0.0)
    gap = (target - eff).clip(lower=0.0)
    gap_ratio = (gap / target.where(target > 0, 1.0)).fillna(0.0)
    bands: list[str] = []
    for flag, ratio in zip(stockout_flag.tolist(), gap_ratio.tolist(), strict=False):
        if int(flag) != 1:
            bands.append("LOW")
        elif float(ratio) >= 0.5:
            bands.append("HIGH")
        else:
            bands.append("MEDIUM")
    return pd.Series(bands, index=stockout_flag.index, dtype=object)


def _overstock_risk_band(*, overstock_flag: pd.Series, cash_band: pd.Series) -> pd.Series:
    bands: list[str] = []
    for flag, cash in zip(overstock_flag.tolist(), cash_band.tolist(), strict=False):
        cash_text = str(cash).upper()
        if int(flag) != 1:
            bands.append("LOW")
        elif cash_text == "HIGH":
            bands.append("HIGH")
        elif cash_text == "MEDIUM":
            bands.append("MEDIUM")
        else:
            bands.append("LOW")
    return pd.Series(bands, index=overstock_flag.index, dtype=object)


def _resolve_zero_forecast_columns(
    *,
    commercial_frame: pd.DataFrame,
    forecast_per_row_diagnostics: pd.DataFrame | None,
) -> tuple[pd.Series, pd.Series]:
    if forecast_per_row_diagnostics is None or forecast_per_row_diagnostics.empty:
        empty_reason = pd.Series([""] * len(commercial_frame.index), index=commercial_frame.index, dtype=object)
        empty_supported = pd.Series([False] * len(commercial_frame.index), index=commercial_frame.index, dtype=bool)
        return empty_reason, empty_supported
    diag = _join_diagnostics_to_commercial(commercial_frame, forecast_per_row_diagnostics)
    reason = diag.get(
        "zero_forecast_reason_code",
        pd.Series([""] * len(diag.index), index=diag.index, dtype=object),
    ).fillna("").astype(str)
    supported_raw = diag.get(
        "zero_forecast_is_evidence_supported",
        pd.Series([False] * len(diag.index), index=diag.index, dtype=bool),
    )
    supported = pd.Series(
        [_store_facing_truthy(value) for value in supported_raw.tolist()],
        index=commercial_frame.index,
        dtype=bool,
    )
    return reason, supported


def _compute_priority_band_and_flags(
    *,
    action: pd.Series,
    gap_units: pd.Series,
    lead_days: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Return (priority_band, buy_now_flag, watch_flag, do_not_buy_flag, days_until_action).

    The band drives both the order_timing_summary text and priority_rank ordering.
    Logic:
      - DO_NOT_ORDER -> DO_NOT_BUY
      - REVIEW -> REVIEW (always immediate)
      - ORDER + gap > 0 + lead_days <= STORE_FACING_BUY_NOW_LEAD_DAYS -> BUY_NOW
      - ORDER + gap > 0 + lead_days > threshold -> WATCH (defer until closer to promo)
      - ORDER + gap == 0 -> HOLD
      - HOLD -> HOLD
      - anything else -> WATCH (safe default)
    """
    bands: list[str] = []
    buy_now_values: list[int] = []
    watch_values: list[int] = []
    do_not_buy_values: list[int] = []
    days_until_action_values: list[int] = []
    for act, gap, lead in zip(
        action.astype(str).str.upper().tolist(),
        gap_units.astype(int).tolist(),
        lead_days.astype(int).tolist(),
        strict=False,
    ):
        gap_int = max(int(gap), 0)
        lead_int = max(int(lead), 0)
        if act == "DO_NOT_ORDER":
            band = "DO_NOT_BUY"
            buy_now = 0
            watch = 0
            do_not_buy = 1
            days_until = 0
        elif act == "REVIEW":
            band = "REVIEW"
            buy_now = 0
            watch = 0
            do_not_buy = 0
            days_until = 0
        elif act == "ORDER" and gap_int > 0:
            if lead_int <= STORE_FACING_BUY_NOW_LEAD_DAYS:
                band = "BUY_NOW"
                buy_now = 1
                watch = 0
                do_not_buy = 0
                days_until = 0
            else:
                band = "WATCH"
                buy_now = 0
                watch = 1
                do_not_buy = 0
                days_until = max(lead_int - STORE_FACING_BUY_NOW_LEAD_DAYS, 0)
        elif act == "ORDER" and gap_int <= 0:
            band = "HOLD"
            buy_now = 0
            watch = 0
            do_not_buy = 0
            days_until = 0
        elif act == "HOLD":
            band = "HOLD"
            buy_now = 0
            watch = 0
            do_not_buy = 0
            days_until = 0
        else:
            band = "WATCH"
            buy_now = 0
            watch = 1
            do_not_buy = 0
            days_until = max(lead_int - STORE_FACING_BUY_NOW_LEAD_DAYS, 0)
        bands.append(band)
        buy_now_values.append(buy_now)
        watch_values.append(watch)
        do_not_buy_values.append(do_not_buy)
        days_until_action_values.append(days_until)
    index = action.index
    return (
        pd.Series(bands, index=index, dtype=object),
        pd.Series(buy_now_values, index=index, dtype="int64"),
        pd.Series(watch_values, index=index, dtype="int64"),
        pd.Series(do_not_buy_values, index=index, dtype="int64"),
        pd.Series(days_until_action_values, index=index, dtype="int64"),
    )


def _compute_priority_rank(
    *,
    priority_band: pd.Series,
    gap_units: pd.Series,
    capital_at_risk: pd.Series,
    lead_days: pd.Series,
) -> pd.Series:
    """1-indexed priority_rank within the file. Lower rank = act first."""
    band_order = {band: idx for idx, band in enumerate(STORE_FACING_PRIORITY_BANDS)}
    sort_frame = pd.DataFrame(
        {
            "__band__": priority_band.map(band_order).fillna(len(STORE_FACING_PRIORITY_BANDS)).astype(int),
            "__gap__": -pd.to_numeric(gap_units, errors="coerce").fillna(0).astype(int),
            "__capital__": -pd.to_numeric(capital_at_risk, errors="coerce").fillna(0.0),
            "__lead__": pd.to_numeric(lead_days, errors="coerce").fillna(0).astype(int),
        },
        index=priority_band.index,
    )
    ordering = sort_frame.sort_values(
        by=["__band__", "__gap__", "__capital__", "__lead__"],
        kind="stable",
    )
    ranks = pd.Series(range(1, len(ordering.index) + 1), index=ordering.index, dtype="int64")
    return ranks.reindex(priority_band.index)


def _compose_data_quality_flag(frame: pd.DataFrame) -> pd.Series:
    quality = frame.get(
        "forecast_quality_flag",
        pd.Series(["ACTIONABLE_FORECAST"] * len(frame.index), index=frame.index),
    ).astype(str)
    insufficient = pd.to_numeric(
        frame.get("insufficient_history_flag", pd.Series([0] * len(frame.index), index=frame.index)),
        errors="coerce",
    ).fillna(0).astype(int)
    cold_start = pd.to_numeric(
        frame.get("cold_start_flag", pd.Series([0] * len(frame.index), index=frame.index)),
        errors="coerce",
    ).fillna(0).astype(int)
    discount_review_flag = _discount_mapping_review_flag(frame).astype(str)

    flags: list[str] = []
    for q, ih, cs, review_discount_flag in zip(
        quality.tolist(),
        insufficient.tolist(),
        cold_start.tolist(),
        discount_review_flag.tolist(),
        strict=False,
    ):
        if str(review_discount_flag).strip() != "":
            flags.append(str(review_discount_flag))
        elif int(ih) == 1 or int(cs) == 1:
            flags.append("INSUFFICIENT_HISTORY")
        elif q == "ACTIONABLE_FORECAST":
            flags.append("OK")
        elif q == "UNCERTAIN_FLAT_PATTERN":
            flags.append("COLLAPSED_FORECAST")
        else:
            flags.append("REVIEW_FORECAST")
    return pd.Series(flags, index=frame.index, dtype=object)


def _build_store_promotion_manager_summary_frame(
    *,
    store_facing_frame: pd.DataFrame,
    store_number: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
) -> pd.DataFrame:
    """One-row companion summary CSV that lives alongside each per-promotion store CSV.

    Designed to answer five executive questions at a glance:
      1. How many SKUs need action now?
      2. How many are watch / review / do-not-buy?
      3. How much stock gap exists before launch?
      4. How much capital is at risk?
      5. Which SKUs are the most urgent today?
    """
    bands = store_facing_frame["priority_band"].astype(str)
    buy_now_count = int((bands == "BUY_NOW").sum())
    review_count = int((bands == "REVIEW").sum())
    watch_count = int((bands == "WATCH").sum())
    hold_count = int((bands == "HOLD").sum())
    do_not_buy_count = int((bands == "DO_NOT_BUY").sum())
    total_recommended_units = int(
        pd.to_numeric(store_facing_frame["recommended_order_units"], errors="coerce").fillna(0).sum()
    )
    total_capital_at_risk = float(
        pd.to_numeric(store_facing_frame["estimated_leftover_cost_dollars"], errors="coerce").fillna(0.0).sum()
    )
    total_risk_adjusted_capital_at_risk = float(
        pd.to_numeric(
            store_facing_frame.get(
                "capital_at_risk_adjusted_dollars",
                pd.Series(0.0, index=store_facing_frame.index),
            ),
            errors="coerce",
        )
        .fillna(0.0)
        .sum()
    )
    total_expected_units_total_promo = int(
        pd.to_numeric(store_facing_frame["expected_units_total_promo"], errors="coerce").fillna(0).sum()
    )
    total_projected_pre_promo_sales_units = int(
        pd.to_numeric(
            store_facing_frame["expected_units_before_promo_start"], errors="coerce"
        ).fillna(0).sum()
    )
    total_projected_first_7_days_units = int(
        pd.to_numeric(
            store_facing_frame["expected_units_first_7_days"], errors="coerce"
        ).fillna(0).sum()
    )
    promotion_period_days = int(
        pd.to_numeric(
            store_facing_frame.get(
                "promotion_period_days",
                pd.Series(0, index=store_facing_frame.index),
            ),
            errors="coerce",
        ).fillna(0).max()
    )
    total_expected_units_per_period = int(
        pd.to_numeric(
            store_facing_frame.get(
                "expected_units_per_period",
                pd.Series(0, index=store_facing_frame.index),
            ),
            errors="coerce",
        ).fillna(0).sum()
    )
    average_expected_units_per_day = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "expected_units_per_day",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).mean()
            ),
            4,
        )
    )
    total_target_end_stock_units = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "target_end_stock_units",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            4,
        )
    )
    total_units_needed_for_trust_floor = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "units_needed_for_trust_floor",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            4,
        )
    )
    total_units_needed_for_high_demand_cover = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "units_needed_for_high_demand_cover",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            4,
        )
    )
    total_units_above_trust_target = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "units_above_trust_target",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            4,
        )
    )
    total_capital_tied_above_trust_target = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "capital_tied_above_trust_target",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            2,
        )
    )
    total_expected_gp_on_trust_floor_units = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "expected_gp_on_trust_floor_units",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            2,
        )
    )
    total_expected_gp_on_speculative_units = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "expected_gp_on_speculative_units",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            2,
        )
    )
    total_risk_adjusted_value_of_speculative_units = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "risk_adjusted_value_of_speculative_units",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            2,
        )
    )
    total_speculative_capital_above_floor_units = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "speculative_capital_above_floor_units",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            4,
        )
    )
    total_speculative_capital_above_floor_value = float(
        round(
            float(
                pd.to_numeric(
                    store_facing_frame.get(
                        "speculative_capital_above_floor_value",
                        pd.Series(0.0, index=store_facing_frame.index),
                    ),
                    errors="coerce",
                ).fillna(0.0).sum()
            ),
            2,
        )
    )
    cashflow_runoff_status = _dominant_text_value(
        store_facing_frame.get(
            "cashflow_runoff_status",
            pd.Series("", index=store_facing_frame.index),
        )
    )
    trust_floor_status = _dominant_text_value(
        store_facing_frame.get(
            "trust_floor_status",
            pd.Series("", index=store_facing_frame.index),
        )
    )
    total_projected_promo_units = total_expected_units_total_promo

    # Promo-level discount descriptor: median of non-zero discount_percent
    # rounded to 1dp. Median tolerates outlier rows (e.g. half-price ad-hoc
    # SKUs in a multi-SKU promo) better than the mean.
    if "discount_percent" in store_facing_frame.columns:
        discount_series = pd.to_numeric(
            store_facing_frame["discount_percent"], errors="coerce"
        )
        non_zero_discount = discount_series[discount_series > 0]
        discount_percent_summary = (
            float(round(float(non_zero_discount.median()), 1))
            if not non_zero_discount.empty
            else 0.0
        )
    else:
        discount_percent_summary = 0.0

    # Average risk/reward weighted by recommended_order_units (so a
    # 100-unit BUY_NOW dominates a 1-unit WATCH). Falls back to a simple
    # mean when no units are recommended.
    if "retail_risk_reward_ratio" in store_facing_frame.columns:
        rr_series = pd.to_numeric(
            store_facing_frame["retail_risk_reward_ratio"], errors="coerce"
        ).fillna(0.0)
        rec_units_series = pd.to_numeric(
            store_facing_frame["recommended_order_units"], errors="coerce"
        ).fillna(0.0)
        weight_total = float(rec_units_series.sum())
        if weight_total > 0.0:
            average_risk_reward_ratio = float(
                round(float((rr_series * rec_units_series).sum() / weight_total), 2)
            )
        elif not rr_series.empty:
            average_risk_reward_ratio = float(round(float(rr_series.mean()), 2))
        else:
            average_risk_reward_ratio = 0.0
    else:
        average_risk_reward_ratio = 0.0
    gap_series = pd.to_numeric(
        store_facing_frame["gap_to_day_one_target_units"], errors="coerce"
    ).fillna(0)
    total_stock_gap_units = int(gap_series.clip(lower=0).sum())
    skus_with_stock_gap = int((gap_series > 0).sum())

    # Most-urgent SKUs: prefer BUY_NOW, then REVIEW, then WATCH, then top of priority sort.
    urgent_skus_series: pd.Series
    if buy_now_count > 0:
        urgent_skus_series = store_facing_frame.loc[bands == "BUY_NOW", "sku_number"]
    elif review_count > 0:
        urgent_skus_series = store_facing_frame.loc[bands == "REVIEW", "sku_number"]
    elif watch_count > 0:
        urgent_skus_series = store_facing_frame.loc[bands == "WATCH", "sku_number"]
    else:
        urgent_skus_series = store_facing_frame["sku_number"]
    most_urgent_skus = ", ".join(urgent_skus_series.astype(str).head(5).tolist())
    top_priority_skus = most_urgent_skus

    if not store_facing_frame.empty:
        next_action_lead_days = int(
            pd.to_numeric(store_facing_frame["lead_days_to_promo_start"], errors="coerce")
            .fillna(0)
            .min()
        )
    else:
        next_action_lead_days = 0
    days_to_promo_start = next_action_lead_days

    if not store_facing_frame.empty and "prediction_date" in store_facing_frame.columns:
        prediction_dates = (
            store_facing_frame["prediction_date"].astype(str).replace("nan", "")
        )
        non_empty = prediction_dates[prediction_dates != ""]
        prediction_date_value = (
            str(non_empty.iloc[0]) if not non_empty.empty else ""
        )
    else:
        prediction_date_value = ""

    if buy_now_count > 0:
        headline = (
            f"{buy_now_count} SKU(s) need action now; act within "
            f"{max(next_action_lead_days, 0)} day(s) of lead time."
        )
    elif review_count > 0:
        headline = f"{review_count} SKU(s) need manager review before any order is released."
    elif watch_count > 0:
        headline = f"{watch_count} SKU(s) on watch; no immediate order action required."
    else:
        headline = "No order action required for this promotion at this store."

    return pd.DataFrame(
        [
            {
                "store_number": store_number,
                "promotion_name": promotion_name,
                "prediction_date": prediction_date_value,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "days_to_promo_start": days_to_promo_start,
                "headline": headline,
                "total_skus": int(len(store_facing_frame.index)),
                "buy_now_count": buy_now_count,
                "review_count": review_count,
                "watch_count": watch_count,
                "hold_count": hold_count,
                "do_not_buy_count": do_not_buy_count,
                "skus_with_stock_gap_before_launch": skus_with_stock_gap,
                "total_stock_gap_units_before_launch": total_stock_gap_units,
                "total_recommended_order_units": total_recommended_units,
                "total_projected_pre_promo_sales_units": total_projected_pre_promo_sales_units,
                "total_projected_first_7_days_units": total_projected_first_7_days_units,
                "promotion_period_days": promotion_period_days,
                "total_expected_units_per_period": total_expected_units_per_period,
                "average_expected_units_per_day": average_expected_units_per_day,
                "total_target_end_stock_units": total_target_end_stock_units,
                "total_units_needed_for_trust_floor": total_units_needed_for_trust_floor,
                "total_units_needed_for_high_demand_cover": total_units_needed_for_high_demand_cover,
                "total_units_above_trust_target": total_units_above_trust_target,
                "total_capital_tied_above_trust_target": total_capital_tied_above_trust_target,
                "total_expected_gp_on_trust_floor_units": total_expected_gp_on_trust_floor_units,
                "total_expected_gp_on_speculative_units": total_expected_gp_on_speculative_units,
                "total_risk_adjusted_value_of_speculative_units": total_risk_adjusted_value_of_speculative_units,
                "cashflow_runoff_status": cashflow_runoff_status,
                "trust_floor_status": trust_floor_status,
                "total_speculative_capital_above_floor_units": total_speculative_capital_above_floor_units,
                "total_speculative_capital_above_floor_value": total_speculative_capital_above_floor_value,
                "total_projected_promo_units": total_projected_promo_units,
                "total_expected_units_total_promo": total_expected_units_total_promo,
                "total_estimated_leftover_cost_dollars": round(total_capital_at_risk, 2),
                # Canonical name (spec): risk-adjusted capital at risk.
                "total_capital_at_risk_adjusted_dollars": round(
                    total_risk_adjusted_capital_at_risk, 2
                ),
                # Legacy aliases retained for downstream consumers; both
                # carry the same risk-adjusted figure as the canonical key
                # above so no consumer reads stale leftover-only math.
                "total_capital_at_risk_dollars": round(
                    total_risk_adjusted_capital_at_risk, 2
                ),
                "total_risk_adjusted_capital_at_risk_dollars": round(
                    total_risk_adjusted_capital_at_risk, 2
                ),
                "discount_percent_summary": discount_percent_summary,
                "average_risk_reward_ratio": average_risk_reward_ratio,
                "lead_days_to_next_action": next_action_lead_days,
                "most_urgent_skus": most_urgent_skus,
                "top_priority_skus": top_priority_skus,
            }
        ]
    )


def _dominant_text_value(series: pd.Series) -> str:
    cleaned = series.astype(str).str.strip()
    cleaned = cleaned[(cleaned != "") & (cleaned.str.lower() != "nan")]
    if cleaned.empty:
        return ""
    return str(cleaned.value_counts().idxmax())


def _read_completed_backtest_summary(path: str | None) -> dict[str, object] | None:
    if not path:
        return None
    summary_path = Path(path)
    if not summary_path.exists():
        raise PromotionStoreDownloadCommercialValidationError(
            f"completed-promotion demand backtest summary not found: {summary_path}"
        )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionStoreDownloadCommercialValidationError(
            f"completed-promotion demand backtest summary must be a JSON object: {summary_path}"
        )
    return payload


def _read_completed_backtest_rows(path: str | None) -> pd.DataFrame | None:
    if not path:
        return None
    rows_path = Path(path)
    if not rows_path.exists():
        raise PromotionStoreDownloadCommercialValidationError(
            f"completed-promotion demand backtest rows not found: {rows_path}"
        )
    suffix = rows_path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(rows_path)
    if suffix == ".csv":
        return pd.read_csv(rows_path)
    raise PromotionStoreDownloadCommercialValidationError(
        f"completed-promotion demand backtest rows must be csv or parquet: {rows_path}"
    )


def _summary_float(summary: dict[str, object] | None, *keys: str, default: float = 0.0) -> float:
    if summary is None:
        return default
    for key in keys:
        value = summary.get(key)
        if value is None:
            continue
        try:
            result = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(result):
            return result
    return default


def _summary_int(summary: dict[str, object] | None, *keys: str, default: int = 0) -> int:
    return int(round(_summary_float(summary, *keys, default=float(default))))


def _classify_backtest_bias(*, comparable_count: int, over_rate: float, under_rate: float) -> str:
    if comparable_count <= 0:
        return "NO_COMPARABLE_EVENTS"
    if over_rate >= under_rate + 0.10:
        return "OVERFORECASTING"
    if under_rate >= over_rate + 0.10:
        return "UNDERFORECASTING"
    return "BALANCED"


def _build_sku_backtest_summary(rows: pd.DataFrame | None) -> pd.DataFrame | None:
    if rows is None or rows.empty or "sku_number" not in rows.columns:
        return None

    working = rows.copy()
    working["sku_number"] = working["sku_number"].astype(str).str.strip()
    working = working.loc[
        ~working["sku_number"].str.lower().isin({"", "nan", "none", "<na>"})
    ].copy()
    if working.empty:
        return None

    predicted = pd.to_numeric(working.get("predicted_units_total_promo"), errors="coerce").fillna(0.0)
    actual = pd.to_numeric(working.get("actual_units_sold_promo"), errors="coerce").fillna(0.0)
    working["signed_error_units"] = predicted - actual
    working["absolute_error_units"] = pd.to_numeric(
        working.get("absolute_error_units"), errors="coerce"
    ).fillna(working["signed_error_units"].abs())
    working["squared_error_units"] = working["signed_error_units"].pow(2)

    summary = (
        working.groupby("sku_number", dropna=False, sort=False)
        .agg(
            SKU_MAE=("absolute_error_units", "mean"),
            SKU_MSE=("squared_error_units", "mean"),
            comparable_row_count=("sku_number", "size"),
            over_rate=("signed_error_units", lambda values: float((values > 0).mean())),
            under_rate=("signed_error_units", lambda values: float((values < 0).mean())),
        )
        .reset_index()
    )
    summary["SKU_MAE"] = summary["SKU_MAE"].round(2)
    summary["SKU_MSE"] = summary["SKU_MSE"].round(2)
    summary["SKU_bias"] = [
        _classify_backtest_bias(
            comparable_count=int(row.comparable_row_count),
            over_rate=float(row.over_rate),
            under_rate=float(row.under_rate),
        )
        for row in summary.itertuples(index=False)
    ]
    return summary.loc[:, ["sku_number", "SKU_MAE", "SKU_MSE", "SKU_bias"]].copy()


def _build_backtest_trust_frame(
    *,
    frame: pd.DataFrame,
    summary: dict[str, object] | None,
) -> pd.DataFrame:
    index = frame.index
    comparable_count = _summary_int(summary, "comparable_rows", "completed_promotions_evaluated")
    mean_absolute_pct_error = _summary_float(
        summary,
        "mean_absolute_percentage_error",
        "mean_absolute_pct_error",
    )
    within_rate = _summary_float(summary, "within_10pct_rate")
    over_rate = _summary_float(summary, "overforecast_rate")
    under_rate = _summary_float(summary, "underforecast_rate")
    bias_class = _classify_backtest_bias(
        comparable_count=comparable_count,
        over_rate=over_rate,
        under_rate=under_rate,
    )

    comparable = pd.Series(comparable_count, index=index, dtype="int64")
    default_within_value: int | pd._libs.missing.NAType
    if comparable_count <= 0:
        default_within_value = pd.NA
    else:
        default_within_value = 1 if within_rate >= 0.50 else 0
    default_mape_value = round(mean_absolute_pct_error, 2) if comparable_count > 0 else float("nan")
    within_flag = pd.Series(default_within_value, index=index, dtype="Int64")
    mape = pd.Series(default_mape_value, index=index, dtype="float64")
    bias = pd.Series(bias_class, index=index, dtype="object")

    if "promotion_backtest_comparable_event_count" in frame.columns:
        comparable = pd.to_numeric(frame["promotion_backtest_comparable_event_count"], errors="coerce").fillna(comparable).clip(lower=0).astype("int64")
    if "promotion_backtest_within_10pct_flag" in frame.columns:
        row_within = pd.to_numeric(frame["promotion_backtest_within_10pct_flag"], errors="coerce").clip(0, 1)
        within_flag = row_within.fillna(within_flag).astype("Int64")
    if "promotion_backtest_mean_absolute_pct_error" in frame.columns:
        mape = pd.to_numeric(frame["promotion_backtest_mean_absolute_pct_error"], errors="coerce").fillna(mape).clip(lower=0.0)
    if "promotion_backtest_bias_class" in frame.columns:
        row_bias = frame["promotion_backtest_bias_class"].astype(str).str.strip().str.upper()
        bias = row_bias.where(row_bias.ne(""), bias)

    no_comparable_mask = comparable.le(0)
    within_flag = within_flag.where(~no_comparable_mask, pd.NA).astype("Int64")
    mape = mape.where(~no_comparable_mask, float("nan"))
    bias = bias.where(~no_comparable_mask, "NO_COMPARABLE_EVENTS")

    summary_texts: list[str] = []
    for within_value, mape_value, bias_value, count_value in zip(
        within_flag.tolist(),
        mape.tolist(),
        bias.tolist(),
        comparable.tolist(),
        strict=False,
    ):
        count_int = int(count_value or 0)
        if count_int <= 0:
            summary_texts.append(
                "Promotion-level backtest has no completed-promotion comparables yet; use row-level history, model confidence, and stock gap."
            )
            continue
        bias_text = str(bias_value).replace("_", " ").lower()
        within_text = "at least half within 10%" if int(within_value) == 1 else "less than half within 10%"
        summary_texts.append(
            "Promotion-level backtest has "
            f"{count_int} comparable event(s), {within_text}, mean error {float(mape_value):.1f}%, bias {bias_text}."
        )

    within_numeric = pd.to_numeric(within_flag, errors="coerce")
    trust_band = pd.Series("LOW", index=index, dtype="object")
    trust_band = trust_band.where(~comparable.eq(0), "LIMITED_BACKTEST")
    trust_band = trust_band.where(~(comparable.gt(0) & mape.le(35.0)), "MEDIUM")
    trust_band = trust_band.where(~(comparable.gt(0) & mape.le(20.0) & within_numeric.eq(1)), "HIGH")

    return pd.DataFrame(
        {
            "forecast_trust_band": trust_band.astype(str),
            "promotion_backtest_within_10pct_flag": within_flag.astype("Int64"),
            "promotion_backtest_mean_absolute_pct_error": mape.round(2).astype(float),
            "promotion_backtest_bias_class": bias.astype(str),
            "promotion_backtest_comparable_event_count": comparable.astype("int64"),
            "forecast_trust_summary": pd.Series(summary_texts, index=index, dtype="object"),
        },
        index=index,
    )


def _resolve_historical_discount_frame(frame: pd.DataFrame) -> pd.DataFrame:
    same_events = _numeric_series(frame, ("feature_historical_promo_events_same_discount",)).fillna(0.0).clip(lower=0.0)
    same_or_better_events = _numeric_series(frame, ("feature_historical_promo_events_same_or_better_discount",)).fillna(0.0).clip(lower=0.0)
    same_avg = _numeric_series(frame, ("feature_historical_units_same_discount_avg",)).fillna(0.0).clip(lower=0.0)
    same_or_better_avg = _numeric_series(frame, ("feature_historical_units_same_or_better_discount_avg",)).fillna(0.0).clip(lower=0.0)
    return pd.DataFrame(
        {
            "historical_units_same_discount_avg": same_avg.round(4),
            "historical_units_same_or_better_discount_avg": same_or_better_avg.round(4),
            "historical_promo_events_same_discount": same_events.round(0).astype("int64"),
            "historical_promo_events_same_or_better_discount": same_or_better_events.round(0).astype("int64"),
        },
        index=frame.index,
    )


def _compose_discount_response_summary(
    *,
    historical: pd.DataFrame,
    recommended_units: pd.Series,
) -> pd.Series:
    summaries: list[str] = []
    rec = pd.to_numeric(recommended_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    for same_count, same_avg, better_count, better_avg, rec_units in zip(
        historical["historical_promo_events_same_discount"].tolist(),
        historical["historical_units_same_discount_avg"].tolist(),
        historical["historical_promo_events_same_or_better_discount"].tolist(),
        historical["historical_units_same_or_better_discount_avg"].tolist(),
        rec.tolist(),
        strict=False,
    ):
        same_count_int = int(same_count or 0)
        better_count_int = int(better_count or 0)
        if same_count_int > 0:
            text = f"Same-discount history has {same_count_int} event(s), avg {float(same_avg):.1f} units."
            if better_count_int > same_count_int:
                text += f" Same-or-better discount avg {float(better_avg):.1f} units from {better_count_int} event(s)."
            if float(rec_units) > 0.0 and float(same_avg) > 0.0 and float(rec_units) > float(same_avg) * 1.5:
                text += " Recommended order is high versus same-discount history; review uplift before release."
            summaries.append(text)
        elif better_count_int > 0:
            summaries.append(
                f"No exact same-discount history; same-or-better discounts have {better_count_int} event(s), avg {float(better_avg):.1f} units."
            )
        else:
            summaries.append("No same-discount history for this store/SKU; use model confidence, stock gap, and backtest summary.")
    return pd.Series(summaries, index=historical.index, dtype="object")


def _build_stockout_operator_frame(
    *,
    projected_on_hand: pd.Series,
    target_day_one: pd.Series,
    expected_first7_units: pd.Series,
    bounded_expected_pre: pd.Series,
    lead_days: pd.Series,
    confidence_fraction: pd.Series,
    stockout_flag: pd.Series,
) -> pd.DataFrame:
    projected = pd.to_numeric(projected_on_hand, errors="coerce").fillna(0.0).clip(lower=0.0)
    target = pd.to_numeric(target_day_one, errors="coerce").fillna(0.0).clip(lower=0.0)
    first7 = pd.to_numeric(expected_first7_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    pre_units = pd.to_numeric(bounded_expected_pre, errors="coerce").fillna(0.0).clip(lower=0.0)
    lead = pd.to_numeric(lead_days, errors="coerce").fillna(0.0).clip(lower=0.0)
    confidence = pd.to_numeric(confidence_fraction, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    stockout = pd.to_numeric(stockout_flag, errors="coerce").fillna(0).astype(int)

    launch_gap = (target - projected).clip(lower=0.0)
    first7_gap = (first7 - projected).clip(lower=0.0)
    target_divisor = target.where(target > 0.0, 1.0)
    first7_divisor = first7.where(first7 > 0.0, 1.0)
    gap_pressure = (launch_gap / target_divisor).clip(lower=0.0, upper=1.0)
    first7_pressure = (first7_gap / first7_divisor).clip(lower=0.0, upper=1.0)
    probability = (
        5.0
        + 55.0 * gap_pressure
        + 25.0 * first7_pressure
        + 10.0 * stockout.clip(0, 1)
        + 5.0 * (1.0 - confidence)
    ).where((launch_gap > 0.0) | (first7_gap > 0.0) | (stockout > 0), 5.0 * (1.0 - confidence))
    probability = probability.clip(lower=0.0, upper=95.0).round(1)

    daily_pre = (pre_units / lead.where(lead > 0.0, 1.0)).replace(0.0, np.nan)
    daily_first7 = (first7 / 7.0).replace(0.0, np.nan)
    days_cover_to_start = (projected / daily_pre).replace([np.inf, -np.inf], np.nan).fillna(CURRENT_STOCK_COVER_DAYS_CAP).clip(0.0, CURRENT_STOCK_COVER_DAYS_CAP)
    days_cover_first7 = (projected / daily_first7).replace([np.inf, -np.inf], np.nan).fillna(CURRENT_STOCK_COVER_DAYS_CAP).clip(0.0, CURRENT_STOCK_COVER_DAYS_CAP)
    cover_units = (projected - target).round(4)

    reasons: list[str] = []
    for gap, first_gap, prob, cover_start, cover_first in zip(
        launch_gap.tolist(),
        first7_gap.tolist(),
        probability.tolist(),
        days_cover_to_start.tolist(),
        days_cover_first7.tolist(),
        strict=False,
    ):
        if float(gap) > 0.0:
            reasons.append(f"Projected launch stock is {float(gap):.0f} unit(s) below day-one target; approximate stockout likelihood {float(prob):.1f}%.")
        elif float(first_gap) > 0.0:
            reasons.append(f"Launch stock meets day-one target but covers only {float(cover_first):.1f} first-week day(s); approximate stockout likelihood {float(prob):.1f}%.")
        else:
            reasons.append(f"Projected launch stock covers day-one target and about {float(cover_start):.1f} pre-promo day(s); stockout likelihood is low.")

    return pd.DataFrame(
        {
            "stockout_probability_percent": probability.astype(float),
            "stockout_risk_reason": pd.Series(reasons, index=projected.index, dtype="object"),
            "days_of_cover_to_promo_start": days_cover_to_start.round(4).astype(float),
            "days_of_cover_first_7_days": days_cover_first7.round(4).astype(float),
            "projected_launch_cover_units": cover_units.astype(float),
        },
        index=projected.index,
    )


def _project_store_facing_output_columns(frame: pd.DataFrame) -> pd.DataFrame:
    _validate_store_facing_output_contract_definition()
    for column in STORE_FACING_OUTPUT_COLUMNS:
        if column not in frame.columns:
            raise PromotionStoreDownloadCommercialValidationError(
                f"store-facing operator output missing required column: {column}"
            )
    projected = frame.loc[:, list(STORE_FACING_OUTPUT_COLUMNS)].copy()
    _validate_store_facing_clean_operator_output(projected)
    return projected


def _project_store_facing_audit_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column in STORE_FACING_SCHEMA_COLUMNS:
        if column not in frame.columns:
            raise PromotionStoreDownloadCommercialValidationError(
                f"store-facing audit output missing required column: {column}"
            )
    return frame.loc[:, list(STORE_FACING_SCHEMA_COLUMNS)].copy()


def _validate_store_facing_output_contract_definition() -> None:
    output_columns = list(STORE_FACING_OUTPUT_COLUMNS)
    if len(output_columns) != len(set(output_columns)):
        raise PromotionStoreDownloadCommercialValidationError(
            "STORE_FACING_OUTPUT_COLUMNS must not contain duplicate columns"
        )


def _normalize_store_facing_contract_token(value: object) -> str:
    return re.sub(r"\s+", "_", str(value).strip().casefold())


def _store_facing_safe_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()


def _store_facing_text_implies_order(value: object) -> bool:
    token = _normalize_store_facing_contract_token(value)
    if not token:
        return False
    if any(blocked in token for blocked in ("do_not", "no_order", "no_auto_buy", "suppressed")):
        return False
    return any(keyword in token for keyword in ("buy", "order", "allocate", "recommended"))


def _store_facing_label_contains_low_soh_or_floor_risk(*values: object) -> bool:
    for value in values:
        token = _normalize_store_facing_contract_token(value)
        if not token:
            continue
        if token in {"floor_protected", "hold_stock_floor_safe"}:
            continue
        if "low_soh" in token:
            return True
        if token in {"floor_protection_needed", "zero_soh_risk"}:
            return True
        if "availability" in token:
            return True
        if token.startswith("below_") and "risk" in token:
            return True
    return False


def _is_clean_review_action(row: pd.Series) -> bool:
    recommended_action_token = _normalize_store_facing_contract_token(row.get("recommended_action", ""))
    store_action_token = _normalize_store_facing_contract_token(row.get("store_action", ""))
    operator_status_token = _normalize_store_facing_contract_token(row.get("operator_status", ""))
    action_token = _normalize_store_facing_contract_token(row.get("store_action_label", ""))
    reason_token = _normalize_store_facing_contract_token(row.get("order_reconciliation_reason", ""))
    primary_review_reason = _store_facing_safe_text(row.get("primary_review_reason", ""))
    review_reason = _store_facing_safe_text(row.get("review_reason", ""))
    human_review_required = pd.to_numeric(
        pd.Series([row.get("human_review_required_flag", 0.0)]),
        errors="coerce",
    ).fillna(0.0).iloc[0]
    if recommended_action_token in {"review", "review_required"}:
        return True
    if store_action_token == "review" or operator_status_token == "review":
        return True
    if primary_review_reason or review_reason:
        return True
    if float(human_review_required) >= 1.0:
        return True
    if recommended_action_token or store_action_token or operator_status_token:
        return False
    return "review" in action_token or "review" in reason_token


def _neutral_reason_short_for_decision(operator_decision: str, review_flag: int) -> str:
    decision = str(operator_decision).strip().upper()
    if review_flag >= 1:
        return "Manager review is required before action."
    neutral_reason_by_decision = {
        "BUY": "Expected demand exceeds protected stock coverage.",
        "PROTECT_AVAILABILITY": "Availability risk justifies a controlled stock top-up.",
        "HOLD_STOCK": "Current stock is expected to cover this promotion.",
        "HOLD_STOCK_FLOOR_SAFE": "Current stock covers expected demand while preserving the availability floor.",
        "LOW_SOH_NO_AUTO_BUY": "Projected stock is low, but demand evidence remains weak.",
        "LOW_SOH_PROTECT_AVAILABILITY": "Projected stock is low and availability risk should be monitored closely.",
        "LOW_SOH_BORDERLINE_REVIEW": "Projected stock is low and missed-sales risk needs a manual check.",
        "REDUCE_HOLDING": "Current holding is high relative to expected demand.",
        "NO_DEMAND": "Demand evidence does not justify extra stock.",
        "NEVER_SOLD_IN_PROMO": "Reliable promotion sell-through evidence is not available.",
        "NO_PRIOR_PROMO_EVIDENCE": "Prior promotion evidence is insufficient to support extra stock.",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK": "Prior promotion evidence is limited and stock risk is low.",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW": "Prior promotion evidence is limited and stock risk needs review.",
        "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND": "Baseline demand exists, but promotion evidence is still limited.",
        "BORDERLINE_OOS_REVIEW": "Borderline stock risk needs a manual check.",
        "DATA_QUALITY_REVIEW": "Input quality issues need manual review.",
    }
    return neutral_reason_by_decision.get(decision, "Current governed evidence does not support a stronger action.")


def _derive_clean_operator_decision(row: pd.Series) -> str:
    for column in ("store_action_label_v2", "store_action_label"):
        value = _store_facing_safe_text(row.get(column, ""))
        if value:
            return value
    store_action = _store_facing_safe_text(row.get("store_action", "")).upper().replace(" ", "_")
    return store_action or "HOLD_STOCK"


def _derive_clean_operator_action(row: pd.Series) -> str:
    recommended_action_token = _normalize_store_facing_contract_token(row.get("recommended_action", ""))
    store_action_token = _normalize_store_facing_contract_token(row.get("store_action", ""))
    operator_status_token = _normalize_store_facing_contract_token(row.get("operator_status", ""))
    order_units = pd.to_numeric(
        pd.Series([row.get("recommended_order_units", 0.0)]),
        errors="coerce",
    ).fillna(0.0).iloc[0]
    if _is_clean_review_action(row):
        return "REVIEW"
    if recommended_action_token == "order" or store_action_token == "buy" or operator_status_token == "ready":
        if float(order_units) > 0.0:
            return "BUY"
        return "DO_NOT_BUY"
    if recommended_action_token in {"hold", "hold_monitor"} or store_action_token == "hold" or operator_status_token == "monitor":
        return "MONITOR"
    if (
        recommended_action_token in {"do_not_order", "do_not_order_low_value"}
        or store_action_token == "do_not_buy"
        or operator_status_token in {"no_buy", "no_order"}
    ):
        return "DO_NOT_BUY"
    if float(order_units) > 0.0:
        return "BUY"
    expected_demand = pd.to_numeric(
        pd.Series([row.get("expected_promo_demand", 0.0)]),
        errors="coerce",
    ).fillna(0.0).iloc[0]
    if _store_facing_label_contains_low_soh_or_floor_risk(
        row.get("store_action_label", ""),
        row.get("availability_risk_label", ""),
    ) and float(expected_demand) > 0.0:
        return "MONITOR"
    return "DO_NOT_BUY"


def _derive_clean_reason_short(row: pd.Series, *, operator_decision: str, review_flag: int) -> str:
    primary_review_reason = _store_facing_safe_text(row.get("primary_review_reason", ""))
    review_reason_text = _store_facing_safe_text(row.get("review_reason", ""))
    decision_reason = _store_facing_safe_text(row.get("decision_reason", ""))
    model_reason_summary = _store_facing_safe_text(row.get("model_reason_summary", ""))
    order_reconciliation_reason = _store_facing_safe_text(row.get("order_reconciliation_reason", ""))

    reason = ""
    if review_flag >= 1:
        if primary_review_reason and (" " in primary_review_reason or "_" not in primary_review_reason):
            reason = primary_review_reason
        elif review_reason_text and (" " in review_reason_text or "_" not in review_reason_text):
            reason = review_reason_text
        elif decision_reason:
            reason = decision_reason
        elif model_reason_summary:
            reason = model_reason_summary
        else:
            reason = order_reconciliation_reason
    else:
        reason = order_reconciliation_reason or model_reason_summary or decision_reason
    if reason:
        reason = reason.split(". ", 1)[0].strip()
        if not reason.endswith("."):
            reason += "."
    order_units = pd.to_numeric(
        pd.Series([row.get("recommended_order_units", 0.0)]),
        errors="coerce",
    ).fillna(0.0).iloc[0]
    if float(order_units) <= 0.0 and _store_facing_text_implies_order(reason):
        return _neutral_reason_short_for_decision(operator_decision, review_flag)
    if reason:
        return reason
    return _neutral_reason_short_for_decision(operator_decision, review_flag)


def _derive_clean_risk_flag(row: pd.Series) -> str:
    availability = _store_facing_safe_text(row.get("availability_risk_label", ""))
    capital = _store_facing_safe_text(row.get("capital_drag_label", ""))
    demand = _store_facing_safe_text(row.get("demand_evidence_label", ""))
    residual = _store_facing_safe_text(row.get("end_of_promo_residual_risk", ""))
    if _store_facing_label_contains_low_soh_or_floor_risk(availability, row.get("store_action_label", "")):
        return availability or "LOW_SOH_OR_FLOOR_RISK"
    if capital and capital != "CAPITAL_DRAG_LOW":
        return capital
    if demand in {"NO_DEMAND", "NEVER_SOLD_IN_PROMO", "SPARSE_HISTORY", "LOW_NONZERO_DEMAND"}:
        return demand
    if residual and residual.upper() not in {"", "LOW"}:
        return residual
    return availability or capital or demand or residual


def _derive_clean_review_flag(row: pd.Series, *, operator_action: str) -> int:
    if _is_clean_review_action(row):
        return 1
    if operator_action == "REVIEW":
        return 1
    return 0


def _derive_clean_audit_notes(row: pd.Series) -> str:
    if "expected_promo_window_demand_units" in row.index:
        return compose_contract_audit_notes(
            order_reason_code=str(row.get("order_reason_code", "")),
            expected_promo_window_demand_units=float(
                pd.to_numeric(pd.Series([row.get("expected_promo_window_demand_units", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
            ),
            demand_evidence_label=str(row.get("demand_evidence_label", "")),
            stock_position_status=str(row.get("stock_position_status", "")),
            raw_stock_gap_units=float(
                pd.to_numeric(pd.Series([row.get("raw_stock_gap_units", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
            ),
            recommended_order_units=float(
                pd.to_numeric(pd.Series([row.get("recommended_order_units", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
            ),
            review_reason=str(row.get("primary_review_reason", "")),
            blocker_reason=str(row.get("blocker_reason", "")),
            confidence_pct=float(
                pd.to_numeric(pd.Series([row.get("model_confidence_percent", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
            ),
        )
    parts: list[str] = []
    review_reason = _store_facing_safe_text(row.get("primary_review_reason", ""))
    blocker_reason = _store_facing_safe_text(row.get("blocker_reason", ""))
    if review_reason:
        parts.append(f"review={review_reason}")
    if blocker_reason:
        parts.append(f"blocker={blocker_reason}")
    raw_units = pd.to_numeric(pd.Series([row.get("raw_model_order_units", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
    provisional_units = pd.to_numeric(pd.Series([row.get("provisional_review_order_units", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
    final_units = pd.to_numeric(pd.Series([row.get("final_store_order_units", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
    confidence_pct = pd.to_numeric(pd.Series([row.get("model_confidence_percent", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
    capital_risk = pd.to_numeric(pd.Series([row.get("capital_at_risk_adjusted_dollars", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
    risk_reward = pd.to_numeric(pd.Series([row.get("retail_risk_reward_ratio", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
    parts.extend(
        (
            f"demand={_store_facing_safe_text(row.get('demand_evidence_label', ''))}",
            f"availability={_store_facing_safe_text(row.get('availability_risk_label', ''))}",
            f"capital={_store_facing_safe_text(row.get('capital_drag_label', ''))}",
            f"raw_units={int(round(float(raw_units)))}",
            f"provisional_units={int(round(float(provisional_units)))}",
            f"final_units={int(round(float(final_units)))}",
            f"confidence_pct={int(round(float(confidence_pct)))}",
            f"capital_risk=${float(capital_risk):.2f}",
            f"risk_reward={float(risk_reward):.2f}",
            f"sku_mae={_store_facing_safe_text(row.get('SKU_MAE', ''))}",
            f"sku_mse={_store_facing_safe_text(row.get('SKU_MSE', ''))}",
            f"sku_bias={_store_facing_safe_text(row.get('SKU_bias', ''))}",
        )
    )
    return "; ".join(
        part
        for part in parts
        if not part.endswith("=")
        and part not in {"sku_mae=", "sku_mse=", "sku_bias="}
    )


def _build_store_facing_clean_operator_fields(store_frame: pd.DataFrame) -> pd.DataFrame:
    operator_decision = store_frame.apply(_derive_clean_operator_decision, axis=1)
    operator_action = store_frame.apply(_derive_clean_operator_action, axis=1)
    review_flag = pd.Series(
        [
            _derive_clean_review_flag(row, operator_action=action)
            for (_, row), action in zip(store_frame.iterrows(), operator_action.tolist(), strict=False)
        ],
        index=store_frame.index,
        dtype="int64",
    )
    order_units = pd.to_numeric(
        store_frame["recommended_order_units"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0).round(0).astype("int64")
    reason_short = pd.Series(
        [
            _derive_clean_reason_short(row, operator_decision=decision, review_flag=flag)
            for (_, row), decision, flag in zip(
                store_frame.iterrows(),
                operator_decision.tolist(),
                review_flag.tolist(),
                strict=False,
            )
        ],
        index=store_frame.index,
        dtype="object",
    )
    risk_flag = store_frame.apply(_derive_clean_risk_flag, axis=1)
    audit_notes = store_frame.apply(_derive_clean_audit_notes, axis=1)
    return pd.DataFrame(
        {
            "operator_decision": operator_decision.astype(str),
            "operator_action": operator_action.astype(str),
            "order_units": order_units,
            "reason_short": reason_short.astype(str),
            "risk_flag": risk_flag.astype(str),
            "review_flag": review_flag,
            "audit_notes": audit_notes.astype(str),
        },
        index=store_frame.index,
    )


def _validate_store_facing_clean_operator_output(frame: pd.DataFrame) -> None:
    failures: list[str] = []
    visible_shadow_columns = [column for column in STORE_FACING_SHADOW_POLICY_COLUMNS if column in frame.columns]
    if visible_shadow_columns:
        failures.append(
            "shadow policy fields must stay audit-only in the operator report: "
            + ", ".join(visible_shadow_columns)
        )
    visible_internal_columns = [column for column in STORE_FACING_INTERNAL_ORDER_STATE_COLUMNS if column in frame.columns]
    if visible_internal_columns:
        failures.append(
            "internal order-state fields must stay audit-only in the operator report: "
            + ", ".join(visible_internal_columns)
        )
    if not failures:
        order_units = pd.to_numeric(frame["order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
        operator_action = frame["operator_action"].astype(str).str.strip().str.upper()
        review_flag = pd.to_numeric(frame["review_flag"], errors="coerce").fillna(0.0)
        reason_short = frame["reason_short"].astype(str).str.strip()
        operator_decision = frame["operator_decision"].astype(str).str.strip().str.upper()
        expected_demand = pd.to_numeric(frame["expected_promo_demand"], errors="coerce").fillna(0.0).clip(lower=0.0)
        invalid_action_count = int((~operator_action.isin({"BUY", "REVIEW", "MONITOR", "DO_NOT_BUY"})).sum())
        if invalid_action_count > 0:
            failures.append(
                f"operator_action must be one of BUY, REVIEW, MONITOR, DO_NOT_BUY (rows={invalid_action_count})"
            )
        buy_zero_count = int((order_units.le(0.0) & operator_action.eq("BUY")).sum())
        if buy_zero_count > 0:
            failures.append(
                f"zero-order rows cannot present BUY in operator_action (rows={buy_zero_count})"
            )
        order_text_zero_count = int((order_units.le(0.0) & reason_short.map(_store_facing_text_implies_order)).sum())
        if order_text_zero_count > 0:
            failures.append(
                f"zero-order rows cannot present BUY or ORDER language in reason_short (rows={order_text_zero_count})"
            )
        low_soh_tension = (
            order_units.le(0.0)
            & expected_demand.gt(LOW_NONZERO_DEMAND_MAX_UNITS)
            & (
                operator_decision.str.contains("LOW_SOH", regex=False)
                | frame["risk_flag"].astype(str).map(
                    lambda value: _store_facing_label_contains_low_soh_or_floor_risk(value)
                )
            )
        )
        explicit_low_evidence_no_buy = (
            operator_decision.str.startswith("NO_PRIOR_PROMO_EVIDENCE")
            | operator_decision.eq("LOW_SOH_NO_AUTO_BUY")
            | operator_decision.eq("NO_DEMAND")
        )
        low_soh_allowed_actions = operator_action.isin({"REVIEW", "MONITOR"}) | (
            operator_action.eq("DO_NOT_BUY") & explicit_low_evidence_no_buy
        )
        low_soh_bad_action_count = int((low_soh_tension & ~low_soh_allowed_actions).sum())
        if low_soh_bad_action_count > 0:
            failures.append(
                "low-SOH or floor-risk rows with material demand tension must surface REVIEW or MONITOR, "
                "or an explicit low-evidence DO_NOT_BUY decision "
                f"(rows={low_soh_bad_action_count})"
            )
        invalid_review_flag_count = int((~review_flag.isin({0.0, 1.0})).sum())
        if invalid_review_flag_count > 0:
            failures.append(
                f"review_flag must be a governed 0/1 indicator (rows={invalid_review_flag_count})"
            )
        blank_reason_count = int(reason_short.eq("").sum())
        if blank_reason_count > 0:
            failures.append(
                f"reason_short must be populated on every visible operator row (rows={blank_reason_count})"
            )
    if failures:
        raise PromotionStoreDownloadCommercialValidationError("; ".join(failures))


def _build_store_facing_contract_cleanup_issues_frame(
    *,
    operator_output_frame: pd.DataFrame,
) -> pd.DataFrame:
    issue_rows: list[dict[str, object]] = []

    def add_issue(
        *,
        issue_type: str,
        row: pd.Series | None,
        proposed_field: str,
        cleanup_fix: str,
        severity: str,
        detail: str,
        fix_priority: int,
    ) -> None:
        issue_rows.append(
            {
                "issue_type": issue_type,
                "sku_number": "" if row is None else str(row["sku_number"]),
                "sku_description": "SCHEMA_LEVEL" if row is None else str(row["sku_description"]),
                "proposed_field": proposed_field,
                "cleanup_fix": cleanup_fix,
                "severity": severity,
                "detail": detail,
                "fix_priority": fix_priority,
            }
        )

    for _, row in operator_output_frame.iterrows():
        order_units = pd.to_numeric(pd.Series([row["order_units"]]), errors="coerce").fillna(0.0).iloc[0]
        if float(order_units) <= 0.0 and (
            str(row["operator_action"]).strip().upper() == "BUY" or _store_facing_text_implies_order(row["reason_short"])
        ):
            add_issue(
                issue_type="BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS",
                row=row,
                proposed_field="operator_action",
                cleanup_fix="Zero-order rows must not present BUY or ORDER language in visible action or reason fields.",
                severity="HIGH",
                detail=(
                    f"operator_decision={row['operator_decision']}; operator_action={row['operator_action']}; "
                    f"order_units={row['order_units']}; reason_short={row['reason_short']}"
                ),
                fix_priority=1,
            )

    for shadow_column in STORE_FACING_SHADOW_POLICY_COLUMNS:
        if shadow_column in operator_output_frame.columns:
            add_issue(
                issue_type="SHADOW_FIELDS_VISIBLE_IN_OPERATOR_REPORT",
                row=None,
                proposed_field="audit_only_shadow_fields",
                cleanup_fix="Move shadow-policy internals to audit-only artifacts.",
                severity="HIGH",
                detail=shadow_column,
                fix_priority=4,
            )

    for internal_column in STORE_FACING_INTERNAL_ORDER_STATE_COLUMNS:
        if internal_column in operator_output_frame.columns:
            add_issue(
                issue_type="MULTIPLE_ACTION_COLUMNS_CONFLICT",
                row=None,
                proposed_field="order_units",
                cleanup_fix="Keep one visible order_units field and move raw or provisional quantity states to audit-only outputs.",
                severity="HIGH",
                detail=internal_column,
                fix_priority=2,
            )

    if not issue_rows:
        return pd.DataFrame(
            columns=[
                "issue_type",
                "sku_number",
                "sku_description",
                "proposed_field",
                "cleanup_fix",
                "severity",
                "detail",
                "fix_priority",
            ]
        )
    return pd.DataFrame(issue_rows).sort_values(
        by=["fix_priority", "issue_type", "sku_number"],
        ascending=[True, True, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_store_facing_contract_cleanup_summary_frame(
    *,
    issue_frame: pd.DataFrame,
    total_row_count: int,
) -> pd.DataFrame:
    if issue_frame.empty:
        return pd.DataFrame(
            [
                {
                    "issue_type": "TOTAL_STORE_FACING_CLEANUP_ISSUES",
                    "issue_count": 0,
                    "severity": "SUMMARY",
                    "proposed_field": "",
                    "cleanup_fix": "",
                    "fix_priority": 0,
                    "sample_skus": "",
                    "total_row_count": int(total_row_count),
                }
            ]
        )
    grouped = (
        issue_frame.groupby(
            ["issue_type", "severity", "proposed_field", "cleanup_fix", "fix_priority"],
            dropna=False,
        )
        .agg(
            issue_count=("issue_type", "size"),
            sample_skus=(
                "sku_number",
                lambda values: ", ".join(
                    list(
                        dict.fromkeys(
                            [
                                value
                                for value in pd.Series(values).astype(str)
                                if value.strip() and value.strip().upper() != "SCHEMA_LEVEL"
                            ]
                        )
                    )[:5]
                ),
            ),
        )
        .reset_index()
        .sort_values(
            by=["fix_priority", "issue_count", "issue_type"],
            ascending=[True, False, True],
            kind="stable",
        )
    )
    grouped["total_row_count"] = int(total_row_count)
    total_row = pd.DataFrame(
        [
            {
                "issue_type": "TOTAL_STORE_FACING_CLEANUP_ISSUES",
                "issue_count": int(len(issue_frame.index)),
                "severity": "SUMMARY",
                "proposed_field": "",
                "cleanup_fix": "",
                "fix_priority": 0,
                "sample_skus": "",
                "total_row_count": int(total_row_count),
            }
        ]
    )
    return pd.concat([total_row, grouped], ignore_index=True)


def _compose_execution_readiness_status(action: pd.Series) -> pd.Series:
    action_upper = action.astype(str).str.strip().str.upper()
    readiness = pd.Series("BLOCKED", index=action.index, dtype="object")
    readiness = readiness.where(~action_upper.eq("ORDER"), "READY_TO_ORDER")
    readiness = readiness.where(~action_upper.isin({"REVIEW", "REVIEW_REQUIRED"}), "REVIEW_REQUIRED")
    readiness = readiness.where(~action_upper.isin({"HOLD", "HOLD_MONITOR"}), "MONITOR")
    readiness = readiness.where(
        ~action_upper.isin({"DO_NOT_ORDER", "DO_NOT_ORDER_LOW_VALUE"}),
        "NO_ORDER",
    )
    return readiness


def _compose_store_facing_action_label(
    *,
    action: pd.Series,
    publish_eligibility_reason: pd.Series | None = None,
) -> pd.Series:
    action_upper = action.astype(str).str.strip().str.upper()
    publish_reason = pd.Series("", index=action.index, dtype="object")
    if publish_eligibility_reason is not None:
        publish_reason = publish_eligibility_reason.reindex(action.index).fillna("").astype(str).str.strip()

    display_action = action_upper.copy()
    display_action = display_action.where(~action_upper.eq("REVIEW"), "REVIEW_REQUIRED")
    display_action = display_action.where(~action_upper.eq("HOLD"), "HOLD_MONITOR")
    low_value_non_buy = action_upper.eq("DO_NOT_ORDER") & publish_reason.eq(
        PUBLISH_ELIGIBILITY_REASON_EXCLUDED_LEGITIMATE_DO_NOT_ORDER_LOW_INCREMENTAL_VALUE
    )
    display_action = display_action.where(~low_value_non_buy, "DO_NOT_ORDER_LOW_VALUE")
    return display_action


def _compose_store_user_action_label(action: pd.Series) -> pd.Series:
    action_upper = action.astype(str).str.strip().str.upper()
    display_action = pd.Series("REVIEW", index=action.index, dtype="object")
    display_action = display_action.where(~action_upper.eq("ORDER"), "BUY")
    display_action = display_action.where(~action_upper.isin({"HOLD", "HOLD_MONITOR"}), "HOLD")
    display_action = display_action.where(
        ~action_upper.isin({"DO_NOT_ORDER", "DO_NOT_ORDER_LOW_VALUE"}),
        "DO NOT BUY",
    )
    display_action = display_action.where(~action_upper.isin({"REVIEW", "REVIEW_REQUIRED"}), "REVIEW")
    return display_action


def _compose_store_user_status_label(status: pd.Series) -> pd.Series:
    status_upper = status.astype(str).str.strip().str.upper()
    display_status = pd.Series("REVIEW", index=status.index, dtype="object")
    display_status = display_status.where(~status_upper.eq("READY_TO_ORDER"), "READY")
    display_status = display_status.where(~status_upper.eq("MONITOR"), "MONITOR")
    display_status = display_status.where(~status_upper.eq("NO_ORDER"), "NO BUY")
    display_status = display_status.where(~status_upper.eq("REVIEW_REQUIRED"), "REVIEW")
    return display_status


def _build_store_action_label_frame(
    *,
    store_frame: pd.DataFrame,
    display_action: pd.Series,
    data_quality_flag: pd.Series,
    discount_reason_code: pd.Series | None = None,
    publish_eligibility_reason: pd.Series,
    review_reason: pd.Series,
) -> pd.DataFrame:
    index = store_frame.index
    display_upper = display_action.astype(str).str.strip().str.upper()
    quality_upper = data_quality_flag.astype(str).str.strip().str.upper()
    discount_reason = (
        discount_reason_code.reindex(index).fillna("").astype(str).str.strip()
        if discount_reason_code is not None
        else pd.Series("", index=index, dtype="object")
    )
    publish_reason = publish_eligibility_reason.reindex(index).fillna("").astype(str).str.strip()
    review_reason_text = review_reason.reindex(index).fillna("").astype(str).str.strip()
    demand_class = store_frame["demand_evidence_class"].fillna("").astype(str).str.strip().str.lower()
    confidence = pd.to_numeric(store_frame["model_confidence_percent"], errors="coerce").fillna(0.0).divide(100.0)
    current_soh = pd.to_numeric(store_frame["current_soh"], errors="coerce").fillna(0.0)
    projected_soh = pd.to_numeric(store_frame["projected_on_hand_at_promo_start"], errors="coerce").fillna(current_soh)
    expected_demand = pd.to_numeric(store_frame["expected_promo_demand"], errors="coerce").fillna(0.0).clip(lower=0.0)
    available_to_sell_before_floor = pd.to_numeric(
        store_frame["available_to_sell_before_floor"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    recommended_units = pd.to_numeric(store_frame["recommended_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    leftover_units = pd.to_numeric(store_frame["estimated_leftover_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    capital_at_risk = pd.to_numeric(store_frame["capital_at_risk_adjusted_dollars"], errors="coerce").fillna(0.0).clip(lower=0.0)
    expected_gp = pd.to_numeric(store_frame["expected_gp_on_speculative_units"], errors="coerce").fillna(0.0)
    value_relief_delta = pd.to_numeric(store_frame["low_nonzero_value_relief_delta"], errors="coerce").fillna(0.0)
    same_discount_events = pd.to_numeric(store_frame["historical_promo_events_same_discount"], errors="coerce").fillna(0.0)
    better_discount_events = pd.to_numeric(store_frame["historical_promo_events_same_or_better_discount"], errors="coerce").fillna(0.0)
    same_discount_units = pd.to_numeric(store_frame["historical_units_same_discount_avg"], errors="coerce").fillna(0.0)
    better_discount_units = pd.to_numeric(store_frame["historical_units_same_or_better_discount_avg"], errors="coerce").fillna(0.0)
    selected_demand_units = pd.to_numeric(
        store_frame["selected_demand_units"]
        if "selected_demand_units" in store_frame.columns
        else store_frame.get("expected_promo_demand", pd.Series(0.0, index=index)),
        errors="coerce",
    ).fillna(0.0)
    positive_selected_demand = selected_demand_units.gt(0.0)

    no_promo_history = same_discount_events.add(better_discount_events).le(0.0)
    zero_sales_promo_history = same_discount_events.add(better_discount_events).gt(0.0) & same_discount_units.add(better_discount_units).le(0.0)
    floor_units = pd.Series(MIN_LAUNCH_STOCK_UNITS, index=index, dtype="float64")
    if "floor_units_required" in store_frame.columns:
        floor_units = pd.to_numeric(store_frame["floor_units_required"], errors="coerce").fillna(MIN_LAUNCH_STOCK_UNITS).clip(lower=0.0)
    floor_protected = expected_demand.le(available_to_sell_before_floor) | projected_soh.sub(expected_demand).ge(floor_units)
    low_projected_soh = projected_soh.le(1.0)
    baseline_demand_present = current_soh.gt(0.0) | expected_demand.gt(0.0) | same_discount_units.add(better_discount_units).gt(0.0)
    credible_demand = expected_demand.gt(0.0) & ~demand_class.isin(
        {
            "true_zero_demand",
            "no_evidence_skip",
            "evidence_supported_zero",
            "artificial_collapse",
        }
    )
    weak_or_no_demand = (
        expected_demand.le(1.0)
        | demand_class.isin({"true_zero_demand", "no_evidence_skip", "evidence_supported_zero"})
        | (no_promo_history & expected_demand.le(2.0))
        | zero_sales_promo_history
    )
    below_floor_now = current_soh.lt(MIN_LAUNCH_STOCK_UNITS)
    projected_below_floor = projected_soh.lt(MIN_LAUNCH_STOCK_UNITS)
    low_demand_covered = projected_soh.ge(MIN_LAUNCH_STOCK_UNITS) & expected_demand.le(
        available_to_sell_before_floor
    )
    demand_exceeds_floor_buffer = expected_demand.gt(available_to_sell_before_floor)
    floor_or_lost_sales_risk = credible_demand & (
        below_floor_now
        | projected_below_floor
        | (~weak_or_no_demand & demand_exceeds_floor_buffer)
    )
    current_floor_protection_risk = credible_demand & below_floor_now & (
        confidence.ge(0.75) | ~weak_or_no_demand
    )
    projected_floor_protection_risk = (
        credible_demand
        & projected_below_floor
        & ~low_demand_covered
        & ~weak_or_no_demand
    )
    protectable_floor_risk = current_floor_protection_risk | projected_floor_protection_risk | (
        credible_demand & ~weak_or_no_demand & demand_exceeds_floor_buffer
    )
    blocking_discount_quality = discount_reason.isin(
        {
            DISCOUNT_REVIEW_REASON_HARD_MISSING_PRICES,
            DISCOUNT_REVIEW_REASON_HARD_INVALID_NORMAL,
            DISCOUNT_REVIEW_REASON_HARD_INVALID_PROMO,
            DISCOUNT_REVIEW_REASON_MAPPING_CONFLICT,
        }
    )
    data_quality_review = quality_upper.eq("COLLAPSED_FORECAST") | blocking_discount_quality
    stock_gap_policy = review_reason_text.eq("policy_stock_gap_high") | publish_reason.eq("policy_stock_gap_high")
    sparse_history_policy = review_reason_text.eq("policy_sparse_history_multi_driver") | publish_reason.eq("policy_sparse_history_multi_driver")
    confidence_review = review_reason_text.eq("review_low_confidence") | publish_reason.eq("review_low_confidence")
    leftover_review = review_reason_text.eq("review_high_leftover_risk") | publish_reason.eq("review_high_leftover_risk")
    capital_drag_high = (
        projected_soh.gt(MIN_LAUNCH_STOCK_UNITS)
        & ~no_promo_history
        & ~zero_sales_promo_history
        & expected_demand.le(available_to_sell_before_floor.clip(lower=1.0))
        & (
            leftover_units.ge(2.0)
            | capital_at_risk.gt(expected_gp.clip(lower=0.0).add(1.0))
            | publish_reason.isin({"do_not_order", "do_not_order_low_incremental_value", "hold_inventory_sufficient"})
        )
    )
    label = pd.Series("HOLD_STOCK", index=index, dtype="object")
    label = label.where(
        ~(weak_or_no_demand & ~below_floor_now & no_promo_history & ~positive_selected_demand),
        "NEVER_SOLD_IN_PROMO",
    )
    label = label.where(
        ~(weak_or_no_demand & ~below_floor_now & ~no_promo_history & ~positive_selected_demand),
        "NO_DEMAND",
    )
    label = label.where(~(low_demand_covered & ~weak_or_no_demand), "HOLD_STOCK_FLOOR_SAFE")
    label = label.where(~capital_drag_high, "REDUCE_HOLDING")
    label = label.where(~(protectable_floor_risk & display_upper.eq("ORDER") & recommended_units.gt(0.0) & expected_demand.gt(2.0)), "BUY")
    label = label.where(
        ~(protectable_floor_risk & (below_floor_now | (projected_below_floor & ~low_demand_covered))),
        "PROTECT_AVAILABILITY",
    )
    borderline_review = display_upper.isin({"REVIEW", "REVIEW_REQUIRED"}) & (
        (floor_or_lost_sales_risk & ~below_floor_now & ~projected_below_floor)
        | (value_relief_delta.gt(0.0) & stock_gap_policy)
        | (credible_demand & confidence_review & current_soh.le(MIN_LAUNCH_STOCK_UNITS))
    )
    label = label.where(~borderline_review, "BORDERLINE_OOS_REVIEW")
    label = label.where(~data_quality_review, "DATA_QUALITY_REVIEW")

    label = label.where(~(label.eq("HOLD_STOCK") & floor_protected), "HOLD_STOCK_FLOOR_SAFE")
    label = label.where(~(label.eq("HOLD_STOCK") & low_projected_soh & weak_or_no_demand), "LOW_SOH_NO_AUTO_BUY")
    label = label.where(~(label.eq("HOLD_STOCK") & low_projected_soh), "LOW_SOH_BORDERLINE_REVIEW")
    label = label.where(~(label.eq("NO_DEMAND") & low_projected_soh), "LOW_SOH_NO_AUTO_BUY")
    label = label.where(~(label.eq("NEVER_SOLD_IN_PROMO") & low_projected_soh), "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW")
    label = label.where(~(label.eq("NEVER_SOLD_IN_PROMO") & baseline_demand_present), "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND")
    label = label.where(~label.eq("NEVER_SOLD_IN_PROMO"), "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK")

    # Publication-blocker fix: store_action_label must align with positive governed
    # demand. NO_DEMAND / NEVER_SOLD_IN_PROMO are zero-demand-only. Positive demand
    # with a stock/floor gap must not stay on suppressive hold labels without an
    # explicit hard blocker — route to PROTECT_AVAILABILITY so reconciliation can
    # emit a governed executable order or a documented protect decision.
    stock_gap_present = (
        demand_exceeds_floor_buffer
        | projected_below_floor
        | below_floor_now
        | selected_demand_units.gt(available_to_sell_before_floor)
    )
    positive_suppressive_with_gap = (
        positive_selected_demand
        & stock_gap_present
        & ~data_quality_review
        & label.isin(
            {
                "NO_DEMAND",
                "NEVER_SOLD_IN_PROMO",
                "HOLD_STOCK",
                "HOLD_STOCK_FLOOR_SAFE",
                "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK",
                "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
                "LOW_SOH_NO_AUTO_BUY",
            }
        )
    )
    label = label.where(~positive_suppressive_with_gap, "PROTECT_AVAILABILITY")
    positive_zero_demand_only = positive_selected_demand & label.isin({"NO_DEMAND", "NEVER_SOLD_IN_PROMO"})
    label = label.where(~positive_zero_demand_only, "LOW_SOH_NO_AUTO_BUY")

    label_v2 = label.copy()

    demand_label = pd.Series("CREDIBLE_PROMO_DEMAND", index=index, dtype="object")
    demand_label = demand_label.where(~demand_class.eq("low_nonzero_demand"), "LOW_NONZERO_DEMAND")
    demand_label = demand_label.where(~demand_class.isin({"cold_start", "insufficient_history", "sparse_history"}), "SPARSE_HISTORY")
    demand_label = demand_label.where(~(weak_or_no_demand & ~positive_selected_demand), "NO_DEMAND")
    demand_label = demand_label.where(
        ~((no_promo_history | zero_sales_promo_history) & ~positive_selected_demand),
        "NEVER_SOLD_IN_PROMO",
    )

    availability_label = pd.Series("FLOOR_PROTECTED", index=index, dtype="object")
    availability_label = availability_label.where(~(credible_demand & demand_exceeds_floor_buffer), "FLOOR_PROTECTION_NEEDED")
    availability_label = availability_label.where(~(current_soh.gt(0.0) & below_floor_now), "BELOW_2_UNIT_FLOOR_RISK")
    availability_label = availability_label.where(~current_soh.le(0.0), "ZERO_SOH_RISK")

    capital_label = pd.Series("CAPITAL_DRAG_LOW", index=index, dtype="object")
    capital_label = capital_label.where(~(projected_soh.gt(MIN_LAUNCH_STOCK_UNITS) & weak_or_no_demand), "CAPITAL_DRAG_WATCH")
    capital_label = capital_label.where(~capital_drag_high, "CAPITAL_DRAG_HIGH")

    blocker = pd.Series("", index=index, dtype="object")
    blocker = blocker.where(~(blocking_discount_quality & blocker.eq("")), discount_reason)
    blocker = blocker.where(~stock_gap_policy, "policy_stock_gap_high")
    blocker = blocker.where(~(sparse_history_policy & blocker.eq("")), "policy_sparse_history_multi_driver")
    blocker = blocker.where(~(leftover_review & blocker.eq("")), "review_high_leftover_risk")
    blocker = blocker.where(~(confidence_review & blocker.eq("")), "review_low_confidence")
    blocker = blocker.where(~(data_quality_review & blocker.eq("")), quality_upper)
    blocker = blocker.where(~(value_relief_delta.gt(0.0) & blocker.eq("")), "low_nonzero_value_relief_visible")

    reason = pd.Series("Hold stock. Current stock is expected to cover this promotion while preserving the 2-unit availability floor.", index=index, dtype="object")
    reason = reason.where(~label.eq("BUY"), "Buy controlled quantity. Expected demand exceeds available stock after protecting the 2-unit floor.")
    reason = reason.where(~label.eq("PROTECT_AVAILABILITY"), "Buy controlled quantity. SOH is below the 2-unit floor and credible demand could create lost sales or online unavailability.")
    reason = reason.where(~label.eq("HOLD_STOCK_FLOOR_SAFE"), "Do not buy. Projected stock covers expected promotion demand while preserving the 2-unit availability floor.")
    reason = reason.where(~label.eq("LOW_SOH_NO_AUTO_BUY"), "Do not auto-order. Projected SOH is low, but demand evidence is weak, so the system is not allocating extra capital automatically.")
    reason = reason.where(~label.eq("LOW_SOH_PROTECT_AVAILABILITY"), "Diagnostics only. Low projected SOH and credible demand may justify a tightly capped availability-protection order.")
    reason = reason.where(~label.eq("LOW_SOH_BORDERLINE_REVIEW"), "Review only. Projected SOH is low and missed-sales risk is plausible, but guardrails are not strong enough for automatic order.")
    reason = reason.where(~label.eq("REDUCE_HOLDING"), "Do not buy. Current holding is high relative to expected demand and creates capital drag.")
    reason = reason.where(~label.eq("NO_DEMAND"), "Do not buy. Demand evidence does not justify additional capital.")
    reason = reason.where(~label.eq("NEVER_SOLD_IN_PROMO"), "Do not buy by default. There is no reliable evidence this SKU sells in promotions.")
    reason = reason.where(~label.eq("NO_PRIOR_PROMO_EVIDENCE_LOW_RISK"), "Do not buy by default. There is no prior promotion evidence and projected stock risk is low.")
    reason = reason.where(~label.eq("NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW"), "Review only. There is no prior promotion evidence, but low projected SOH could still create missed-sales risk.")
    reason = reason.where(~label.eq("NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND"), "Review only. Prior promotion evidence is missing, but baseline demand means the SKU should not be treated as true no-demand.")
    reason = reason.where(~label.eq("BORDERLINE_OOS_REVIEW"), "Review only. SKU is near the buy boundary and may fall below the 2-unit availability floor or has value relief blocked by policy.")
    reason = reason.where(~label.eq("DATA_QUALITY_REVIEW"), "Review only. Required inputs are missing, inconsistent, or materially suspect.")
    reason = reason.where(
        ~label.eq("HOLD_STOCK"),
        "Do not buy. Current SOH is expected to cover this promotion and protects the online availability floor.",
    )

    return pd.DataFrame(
        {
            "store_action_label": label,
            "store_action_label_v2": label_v2,
            "store_action_reason": reason,
            "demand_evidence_label": demand_label,
            "availability_risk_label": availability_label,
            "capital_drag_label": capital_label,
            "blocker_reason": blocker,
            "human_review_required_flag": label.isin({"BORDERLINE_OOS_REVIEW", "DATA_QUALITY_REVIEW"}).astype(int),
        },
        index=index,
    )


def _build_segmented_pl_proved_shadow_policy(
    *,
    label_value: str,
    projected_soh_value: float,
    floor_value: float,
    expected_value: float,
    available_value: float,
    availability_label_value: str,
    demand_label_value: str,
    capital_label_value: str,
    blocker_value: str,
    promo_allocated_value: float,
    unit_cost_value: float,
    pack_size_value: float,
    avg_daily_value: float,
    estimated_leftover_value: float,
    data_quality_value: str,
) -> dict[str, object]:
    label_upper = str(label_value or "").strip().upper()
    availability_upper = str(availability_label_value or "").strip().upper()
    demand_upper = str(demand_label_value or "").strip().upper()
    capital_upper = str(capital_label_value or "").strip().upper()
    blocker_text = str(blocker_value or "").strip()
    data_quality_upper = str(data_quality_value or "").strip().upper()

    projected_soh_numeric = max(float(projected_soh_value or 0.0), 0.0)
    floor_numeric = max(float(floor_value or 0.0), 0.0)
    expected_numeric = max(float(expected_value or 0.0), 0.0)
    available_numeric = max(float(available_value or 0.0), 0.0)
    promo_allocated_numeric = max(float(promo_allocated_value or 0.0), 0.0)
    unit_cost_numeric = max(float(unit_cost_value or 0.0), 0.0)
    pack_size_numeric = max(float(pack_size_value or 0.0), 1.0)
    avg_daily_numeric = max(float(avg_daily_value or 0.0), 0.0)
    estimated_leftover_numeric = max(float(estimated_leftover_value or 0.0), 0.0)

    low_soh_risk_present = (
        availability_upper in HIGH_AVAILABILITY_RISK_LABELS
        or projected_soh_numeric <= max(floor_numeric, 2.0)
    )
    current_ff_executable_zero = label_upper in NON_EXECUTABLE_STORE_ACTION_LABELS
    availability_gap_present = (
        expected_numeric > available_numeric
        or projected_soh_numeric < max(floor_numeric, 2.0)
    )
    pl_allocation_signal_present = promo_allocated_numeric > 0.0
    pl_shadow_strength_sufficient = (
        promo_allocated_numeric >= SEGMENTED_PL_PROVED_SHADOW_MIN_PROMO_ALLOCATED_UNITS
    )
    pack_guardrail_pass = pack_size_numeric <= LOW_SOH_POLICY_MAX_PACK_SIZE_AUTO_ORDER
    cost_guardrail_pass = unit_cost_numeric <= LOW_SOH_POLICY_MAX_UNIT_COST_AUTO_ORDER
    capital_drag_guardrail_pass = capital_upper != "CAPITAL_DRAG_HIGH"
    target_excess_guardrail_pass = estimated_leftover_numeric <= max(expected_numeric, floor_numeric)
    forecast_guardrail_pass = data_quality_upper not in {"COLLAPSED_FORECAST", "REVIEW_FORECAST"}
    hard_data_guardrail_pass = not blocker_text.startswith("HARD_DATA_FAILURE")
    demand_present = demand_upper in DYNAMIC_DEMAND_EVIDENCE_LABELS
    demand_shadow_fallback_present = (
        pl_shadow_strength_sufficient
        and expected_numeric > 0.0
        and low_soh_risk_present
        and availability_gap_present
        and pack_guardrail_pass
        and cost_guardrail_pass
        and capital_drag_guardrail_pass
        and target_excess_guardrail_pass
        and forecast_guardrail_pass
        and hard_data_guardrail_pass
    )
    demand_proxy_satisfied = demand_present or demand_shadow_fallback_present
    baseline_demand_present = expected_numeric >= 1.0 or avg_daily_numeric > 0.0
    eligible_label = label_upper in LOW_SOH_POLICY_ELIGIBLE_LABELS

    candidate_flag = int(
        low_soh_risk_present
        and current_ff_executable_zero
        and availability_gap_present
        and pl_shadow_strength_sufficient
        and demand_proxy_satisfied
        and baseline_demand_present
        and eligible_label
    )

    blockers: list[str] = []
    if not low_soh_risk_present:
        blockers.append("NO_LOW_SOH_RISK")
    if not current_ff_executable_zero:
        blockers.append("FF_ALREADY_EXECUTABLE")
    if not availability_gap_present:
        blockers.append("NO_AVAILABILITY_GAP")
    if not pl_allocation_signal_present:
        blockers.append("NO_PL_ALLOCATION_SIGNAL")
    elif not pl_shadow_strength_sufficient:
        blockers.append("PL_ALLOCATION_BELOW_SHADOW_STRENGTH_THRESHOLD")
    if not demand_proxy_satisfied:
        blockers.append("NO_PROVEN_DEMAND_SIGNAL")
    if not baseline_demand_present:
        blockers.append("NO_EXPECTED_OR_BASELINE_DEMAND")
    if not eligible_label:
        blockers.append("LABEL_NOT_SHADOW_ELIGIBLE")
    if not pack_guardrail_pass:
        blockers.append("PACK_MOQ_UNECONOMIC")
    if not cost_guardrail_pass:
        blockers.append("HIGH_COST_LOW_CONFIDENCE")
    if not capital_drag_guardrail_pass:
        blockers.append("CAPITAL_DRAG_HIGH")
    if not forecast_guardrail_pass:
        blockers.append("FORECAST_REVIEW_REQUIRED")
    if not hard_data_guardrail_pass:
        blockers.append("HARD_DATA_FAILURE")
    if not target_excess_guardrail_pass:
        blockers.append("ENDING_STOCK_EXCESS_PROXY")

    shadow_pass = candidate_flag == 1 and len(blockers) == 0
    shadow_order_units = 1 if shadow_pass else 0
    shadow_capital_at_risk = round(shadow_order_units * unit_cost_numeric, 2)
    if demand_present:
        shadow_reason = (
            "Segmented PL-proved shadow policy would place a governed 1-unit shadow order because PL allocation meets the shadow strength threshold, demand is evidenced, and availability risk is present while Stage 11 remains non-executable."
        )
    else:
        shadow_reason = (
            "Segmented PL-proved shadow policy would place a governed 1-unit shadow order because promo_allocated_units meets the shadow strength threshold, expected promo demand is above zero, and guarded shadow-only demand fallback is satisfied while Stage 11 remains non-executable."
        )
    shadow_blocker_reason = "" if shadow_pass else ";".join(dict.fromkeys(blockers))

    return {
        "shadow_policy_name": SHADOW_POLICY_NAME_SEGMENTED_PL_PROVED_ORDER_1,
        "shadow_policy_version": SHADOW_POLICY_VERSION_SEGMENTED_PL_PROVED_ORDER_1,
        "shadow_policy_candidate_flag": candidate_flag,
        "shadow_policy_segment": SHADOW_POLICY_SEGMENT_PL_PROVED_DEMAND_BUT_OVERBOUGHT if candidate_flag == 1 else "",
        "shadow_policy_order_units": shadow_order_units,
        "shadow_policy_capital_at_risk": shadow_capital_at_risk,
        "shadow_policy_expected_reason": shadow_reason if candidate_flag == 1 else "",
        "shadow_policy_guardrail_status": SHADOW_POLICY_GUARDRAIL_PASS if shadow_pass else SHADOW_POLICY_GUARDRAIL_BLOCKED,
        "shadow_policy_blocker_reason": shadow_blocker_reason,
        "shadow_policy_should_publish_flag": 0,
        "shadow_policy_should_affect_final_order_flag": 0,
    }


def _build_store_order_reconciliation_frame(
    *,
    store_frame: pd.DataFrame,
) -> pd.DataFrame:
    index = store_frame.index
    label = store_frame["store_action_label"].fillna("").astype(str).str.strip().str.upper()
    if "raw_model_order_units" in store_frame.columns:
        raw_units_source = store_frame["raw_model_order_units"]
    else:
        raw_units_source = store_frame["recommended_order_units"]
    raw_units = pd.to_numeric(raw_units_source, errors="coerce").fillna(0.0).clip(lower=0.0)
    raw_value = pd.to_numeric(
        store_frame.get(
            "raw_model_order_value",
            pd.Series(0.0, index=index, dtype="float64"),
        ),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    if "projected_SOH_at_promo_start" in store_frame.columns:
        projected_soh_source = store_frame["projected_SOH_at_promo_start"]
    else:
        projected_soh_source = store_frame["projected_on_hand_at_promo_start"]
    projected_soh = pd.to_numeric(projected_soh_source, errors="coerce").fillna(0.0).clip(lower=0.0)
    floor_units = pd.to_numeric(store_frame["floor_units_required"], errors="coerce").fillna(
        MIN_LAUNCH_STOCK_UNITS
    )
    expected_demand = pd.to_numeric(store_frame["expected_promo_demand"], errors="coerce").fillna(0.0).clip(lower=0.0)
    available_to_sell_before_floor = pd.to_numeric(
        store_frame["available_to_sell_before_floor"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    projected_stock_gap_units = pd.to_numeric(
        store_frame["projected_stock_gap_units"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    risk_reward_ratio = pd.to_numeric(
        store_frame["retail_risk_reward_ratio"], errors="coerce"
    ).fillna(0.0)
    availability_risk_label = store_frame["availability_risk_label"].fillna("").astype(str).str.strip().str.upper()
    demand_evidence_label = store_frame["demand_evidence_label"].fillna("").astype(str).str.strip().str.upper()
    capital_drag_label = store_frame["capital_drag_label"].fillna("").astype(str).str.strip().str.upper()
    blocker_reason = store_frame["blocker_reason"].fillna("").astype(str).str.strip()
    unit_cost = raw_value.divide(raw_units.where(raw_units.gt(0.0))).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    pack_size = pd.to_numeric(
        store_frame.get("pack_size", pd.Series(1.0, index=index, dtype="float64")),
        errors="coerce",
    ).fillna(1.0).clip(lower=1.0)
    avg_daily_units = pd.to_numeric(
        store_frame.get(
            "expected_units_per_day",
            store_frame.get("avg_daily_units", pd.Series(0.0, index=index, dtype="float64")),
        ),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    expected_gp = pd.to_numeric(
        store_frame.get("expected_gp_on_speculative_units", pd.Series(0.0, index=index, dtype="float64")),
        errors="coerce",
    ).fillna(0.0)
    promo_allocated_units = pd.to_numeric(
        store_frame.get("promo_allocated_units", pd.Series(0.0, index=index, dtype="float64")),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    estimated_leftover_units = pd.to_numeric(
        store_frame.get("estimated_leftover_units", pd.Series(0.0, index=index, dtype="float64")),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    data_quality_flag = store_frame.get("data_quality_flag", pd.Series("", index=index, dtype="object")).fillna("").astype(str).str.strip().str.upper()

    provisional_units: list[int] = []
    final_units: list[int] = []
    provisional_values: list[float] = []
    final_values: list[float] = []
    low_soh_policy_versions: list[str] = []
    low_soh_candidate_flags: list[int] = []
    low_soh_production_eligible_flags: list[int] = []
    low_soh_final_order_units: list[int] = []
    low_soh_capital_at_risk_values: list[float] = []
    low_soh_policy_reasons: list[str] = []
    low_soh_guardrail_statuses: list[str] = []
    low_soh_blocker_reasons: list[str] = []
    low_soh_decision_sources: list[str] = []
    shadow_policy_names: list[str] = []
    shadow_policy_versions: list[str] = []
    shadow_policy_candidate_flags: list[int] = []
    shadow_policy_segments: list[str] = []
    shadow_policy_order_units_values: list[int] = []
    shadow_policy_capital_at_risk_values: list[float] = []
    shadow_policy_expected_reasons: list[str] = []
    shadow_policy_guardrail_statuses: list[str] = []
    shadow_policy_blocker_reasons: list[str] = []
    shadow_policy_should_publish_flags: list[int] = []
    shadow_policy_should_affect_final_order_flags: list[int] = []
    statuses: list[str] = []
    reasons: list[str] = []

    def _floor_protected(
        *,
        projected_soh_value: float,
        expected_demand_value: float,
        available_value: float,
        floor_value: float,
    ) -> bool:
        projected_soh_numeric = max(float(projected_soh_value or 0.0), 0.0)
        expected_demand_numeric = max(float(expected_demand_value or 0.0), 0.0)
        available_numeric = max(float(available_value or 0.0), 0.0)
        floor_numeric = max(float(floor_value or 0.0), 0.0)
        return (
            expected_demand_numeric <= available_numeric
            or (projected_soh_numeric - expected_demand_numeric) >= floor_numeric
        )

    def _weak_demand_no_auto_order_reason(
        *,
        projected_soh_int: int,
        floor_units_int: int,
    ) -> str:
        if projected_soh_int < floor_units_int:
            return (
                f"Do not auto-order. Projected SOH is below the {floor_units_int}-unit floor, but demand evidence is weak, "
                "so the system is not allocating extra capital automatically."
            )
        return (
            f"Do not auto-order. Projected SOH could fall below the {floor_units_int}-unit floor if demand materialises, "
            "but demand evidence is weak, so the system is not allocating extra capital automatically."
        )

    def _low_soh_policy_order_units(
        *,
        projected_soh_value: float,
        floor_value: float,
        expected_value: float,
        available_value: float,
        raw_units_value: float,
    ) -> int:
        floor_gap_units = max(float(floor_value or 0.0) - float(projected_soh_value or 0.0), 0.0)
        demand_gap_units = max(float(expected_value or 0.0) - float(available_value or 0.0), 0.0)
        controlled_need_units = max(
            floor_gap_units,
            min(demand_gap_units, float(LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS)),
        )
        capped_units = min(math.ceil(controlled_need_units), LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS)
        if float(expected_value or 0.0) <= 1.0 and float(projected_soh_value or 0.0) > 0.0:
            capped_units = min(capped_units, 1)
        if float(expected_value or 0.0) <= 2.0 and float(projected_soh_value or 0.0) > 0.0:
            capped_units = min(capped_units, 2)
        if float(raw_units_value or 0.0) > 0.0:
            capped_units = min(capped_units, int(max(round(float(raw_units_value or 0.0)), 0)))
        return int(max(capped_units, 0))

    for label_value, raw_units_value, projected_soh_value, floor_value, expected_value, available_value, gap_value, ratio_value, availability_value, demand_value, capital_value, blocker_value, unit_cost_value, pack_size_value, avg_daily_value, expected_gp_value, promo_allocated_value, estimated_leftover_value, data_quality_value in zip(
        label.tolist(),
        raw_units.tolist(),
        projected_soh.tolist(),
        floor_units.tolist(),
        expected_demand.tolist(),
        available_to_sell_before_floor.tolist(),
        projected_stock_gap_units.tolist(),
        risk_reward_ratio.tolist(),
        availability_risk_label.tolist(),
        demand_evidence_label.tolist(),
        capital_drag_label.tolist(),
        blocker_reason.tolist(),
        unit_cost.tolist(),
        pack_size.tolist(),
        avg_daily_units.tolist(),
        expected_gp.tolist(),
        promo_allocated_units.tolist(),
        estimated_leftover_units.tolist(),
        data_quality_flag.tolist(),
        strict=False,
    ):
        raw_units_int = int(max(round(float(raw_units_value or 0.0)), 0))
        projected_soh_int = int(max(round(float(projected_soh_value or 0.0)), 0))
        floor_units_int = int(max(round(float(floor_value or 0.0)), 0))
        expected_demand_int = int(max(round(float(expected_value or 0.0)), 0))
        gap_int = int(max(round(float(gap_value or 0.0)), 0))
        floor_protected = _floor_protected(
            projected_soh_value=float(projected_soh_value or 0.0),
            expected_demand_value=float(expected_value or 0.0),
            available_value=float(available_value or 0.0),
            floor_value=float(floor_value or 0.0),
        )
        availability_need_units = int(
            max(
                round(
                    max(
                        (float(floor_value or 0.0) + float(expected_value or 0.0))
                        - float(projected_soh_value or 0.0),
                        0.0,
                    )
                ),
                0,
            )
        )
        provisional_units_int = 0
        final_units_int = raw_units_int
        status_value = ORDER_RECONCILIATION_STATUS_EXECUTABLE_BUY
        reason_value = (
            f"Order now. Projected SOH at promotion start is {projected_soh_int}, expected demand is {expected_demand_int}, "
            f"and the SKU is {gap_int} unit(s) short of target after protecting the {floor_units_int}-unit floor."
        )
        availability_risk_present = availability_value in {
            "ZERO_SOH_RISK",
            "BELOW_2_UNIT_FLOOR_RISK",
            "FLOOR_PROTECTION_NEEDED",
        }
        shadow_policy = _build_segmented_pl_proved_shadow_policy(
            label_value=str(label_value or ""),
            projected_soh_value=float(projected_soh_value or 0.0),
            floor_value=float(floor_value or 0.0),
            expected_value=float(expected_value or 0.0),
            available_value=float(available_value or 0.0),
            availability_label_value=str(availability_value or ""),
            demand_label_value=str(demand_value or ""),
            capital_label_value=str(capital_value or ""),
            blocker_value=str(blocker_value or ""),
            promo_allocated_value=float(promo_allocated_value or 0.0),
            unit_cost_value=float(unit_cost_value or 0.0),
            pack_size_value=float(pack_size_value or 0.0),
            avg_daily_value=float(avg_daily_value or 0.0),
            estimated_leftover_value=float(estimated_leftover_value or 0.0),
            data_quality_value=str(data_quality_value or ""),
        )
        shadow_policy_units_int = int(shadow_policy["shadow_policy_order_units"])
        shadow_low_soh_candidate = int(shadow_policy["shadow_policy_candidate_flag"]) == 1
        shadow_low_soh_pass = shadow_policy_units_int > 0
        low_soh_production_eligible = False
        low_soh_guardrail_status = str(shadow_policy["shadow_policy_guardrail_status"])
        low_soh_blocker_reason = str(shadow_policy["shadow_policy_blocker_reason"])
        low_soh_policy_reason = (
            f"Governed shadow-only low-SOH policy {LOW_SOH_POLICY_VERSION}: {shadow_policy['shadow_policy_expected_reason']}"
            if shadow_low_soh_pass
            else f"Low-SOH shadow policy not eligible: {low_soh_blocker_reason or 'guardrails_not_met'}."
        )

        if label_value in PROVISIONAL_REVIEW_STORE_ACTION_LABELS:
            provisional_units_int = raw_units_int
            final_units_int = 0
            status_value = ORDER_RECONCILIATION_STATUS_PROVISIONAL_REVIEW_ONLY
            if label_value == "DATA_QUALITY_REVIEW":
                blocker_text = blocker_value or "Required price, forecast, or policy inputs are inconsistent"
                reason_value = (
                    "Do not auto-order. Data-quality conflict prevents a governed executable order. "
                    f"Review manually if commercially important. Blocker: {blocker_text}."
                )
            else:
                reason_value = (
                    f"Review only. The SKU is close to a buy decision, projected SOH at promotion start is {projected_soh_int}, "
                    f"and confidence is not high enough for automatic order while protecting the {floor_units_int}-unit floor."
                )
        elif label_value in NON_EXECUTABLE_STORE_ACTION_LABELS:
            final_units_int = 0
            status_value = ORDER_RECONCILIATION_STATUS_SUPPRESSED_BY_LABEL_GOVERNANCE
            if label_value in {"HOLD_STOCK", "HOLD_STOCK_FLOOR_SAFE"}:
                if floor_protected:
                    reason_value = (
                        f"Do not buy. Projected SOH at promotion start is {projected_soh_int}, expected demand is {expected_demand_int}, "
                        f"and the {floor_units_int}-unit floor is protected."
                    )
                else:
                    reason_value = _weak_demand_no_auto_order_reason(
                        projected_soh_int=projected_soh_int,
                        floor_units_int=floor_units_int,
                    )
            elif label_value == "REDUCE_HOLDING":
                reason_value = (
                    f"Do not buy. Projected SOH is {projected_soh_int} against expected demand of {expected_demand_int}, creating capital drag. "
                    "Use the promotion to sell through existing stock."
                )
            elif label_value in {"NO_DEMAND", "LOW_SOH_NO_AUTO_BUY"}:
                if floor_protected:
                    reason_value = (
                        f"Do not buy. Demand evidence is weak and projected SOH of {projected_soh_int} already protects the {floor_units_int}-unit availability floor."
                    )
                else:
                    reason_value = _weak_demand_no_auto_order_reason(
                        projected_soh_int=projected_soh_int,
                        floor_units_int=floor_units_int,
                    )
            elif label_value in {"LOW_SOH_PROTECT_AVAILABILITY", "LOW_SOH_BORDERLINE_REVIEW"}:
                provisional_units_int = raw_units_int
                reason_value = (
                    f"Review only. Projected SOH at promotion start is {projected_soh_int}, expected demand is {expected_demand_int}, "
                    f"and low-SOH protection remains shadow-only until actual-outcome guardrails pass."
                )
            elif label_value in {
                "NEVER_SOLD_IN_PROMO",
                "NO_PRIOR_PROMO_EVIDENCE",
                "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK",
                "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW",
                "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
            }:
                if floor_protected:
                    reason_value = (
                        f"Do not buy. Prior promotion evidence is limited and projected SOH of {projected_soh_int} already protects the {floor_units_int}-unit floor."
                    )
                else:
                    reason_value = _weak_demand_no_auto_order_reason(
                        projected_soh_int=projected_soh_int,
                        floor_units_int=floor_units_int,
                    )
        elif label_value == "PROTECT_AVAILABILITY":
            final_units_int = min(raw_units_int, availability_need_units)
            status_value = ORDER_RECONCILIATION_STATUS_EXECUTABLE_PROTECT
            if final_units_int < raw_units_int:
                status_value = ORDER_RECONCILIATION_STATUS_CAPPED_TO_AVAILABILITY_NEED
            reason_value = (
                f"Order controlled quantity. Projected SOH at promotion start is {projected_soh_int}, expected demand is {expected_demand_int}, "
                f"and the executable order is capped to {final_units_int} unit(s) to protect the {floor_units_int}-unit floor without overbuying."
            )
            if final_units_int <= 0:
                status_value = ORDER_RECONCILIATION_STATUS_SUPPRESSED_BY_LABEL_GOVERNANCE
                if floor_protected:
                    reason_value = (
                        f"Do not buy. Projected SOH at promotion start is {projected_soh_int}, expected demand is {expected_demand_int}, "
                        f"and the {floor_units_int}-unit floor is already protected."
                    )
                else:
                    reason_value = _weak_demand_no_auto_order_reason(
                        projected_soh_int=projected_soh_int,
                        floor_units_int=floor_units_int,
                    )
        else:
            final_units_int = raw_units_int
            status_value = ORDER_RECONCILIATION_STATUS_EXECUTABLE_BUY
            if not availability_risk_present and float(ratio_value or 0.0) < MIN_EXECUTABLE_RETAIL_RISK_REWARD_RATIO:
                final_units_int = 0
                status_value = ORDER_RECONCILIATION_STATUS_SUPPRESSED_BY_LABEL_GOVERNANCE
                if floor_protected:
                    reason_value = (
                        f"Do not buy. Risk/reward is poor, projected SOH is {projected_soh_int}, and the {floor_units_int}-unit floor is already protected without a fresh order."
                    )
                else:
                    reason_value = _weak_demand_no_auto_order_reason(
                        projected_soh_int=projected_soh_int,
                        floor_units_int=floor_units_int,
                    )

        if label_value == "REDUCE_HOLDING" and capital_value == "CAPITAL_DRAG_HIGH":
            reason_value = (
                f"Do not buy. Projected SOH is {projected_soh_int} against expected demand of {expected_demand_int}, creating capital drag. "
                "Use the promotion to sell through existing stock."
            )
        if label_value == "NO_DEMAND" and demand_value == "NO_DEMAND":
            if floor_protected:
                reason_value = (
                    f"Do not buy. Demand evidence does not justify fresh capital and projected SOH of {projected_soh_int} already protects the {floor_units_int}-unit floor."
                )
            else:
                reason_value = _weak_demand_no_auto_order_reason(
                    projected_soh_int=projected_soh_int,
                    floor_units_int=floor_units_int,
                )

        if shadow_low_soh_pass and label_value in {"LOW_SOH_PROTECT_AVAILABILITY", "LOW_SOH_BORDERLINE_REVIEW"}:
            provisional_units_int = max(provisional_units_int, raw_units_int)
            final_units_int = 0
            status_value = ORDER_RECONCILIATION_STATUS_PROVISIONAL_REVIEW_ONLY
            reason_value = low_soh_policy_reason

        provisional_units.append(provisional_units_int)
        final_units.append(final_units_int)
        provisional_values.append(round(provisional_units_int * float(unit_cost_value or 0.0), 2))
        final_values.append(round(final_units_int * float(unit_cost_value or 0.0), 2))
        low_soh_policy_versions.append(LOW_SOH_POLICY_VERSION)
        low_soh_candidate_flags.append(int(shadow_low_soh_candidate))
        low_soh_production_eligible_flags.append(int(low_soh_production_eligible))
        low_soh_final_order_units.append(0)
        low_soh_capital_at_risk_values.append(float(shadow_policy["shadow_policy_capital_at_risk"]))
        low_soh_policy_reasons.append(low_soh_policy_reason)
        low_soh_guardrail_statuses.append(low_soh_guardrail_status)
        low_soh_blocker_reasons.append(low_soh_blocker_reason)
        low_soh_decision_sources.append(LOW_SOH_POLICY_VALIDATED_SEGMENT_SOURCE if shadow_low_soh_candidate else "base_stage11_reconciliation")
        shadow_policy_names.append(str(shadow_policy["shadow_policy_name"]))
        shadow_policy_versions.append(str(shadow_policy["shadow_policy_version"]))
        shadow_policy_candidate_flags.append(int(shadow_policy["shadow_policy_candidate_flag"]))
        shadow_policy_segments.append(str(shadow_policy["shadow_policy_segment"]))
        shadow_policy_order_units_values.append(int(shadow_policy["shadow_policy_order_units"]))
        shadow_policy_capital_at_risk_values.append(float(shadow_policy["shadow_policy_capital_at_risk"]))
        shadow_policy_expected_reasons.append(str(shadow_policy["shadow_policy_expected_reason"]))
        shadow_policy_guardrail_statuses.append(str(shadow_policy["shadow_policy_guardrail_status"]))
        shadow_policy_blocker_reasons.append(str(shadow_policy["shadow_policy_blocker_reason"]))
        shadow_policy_should_publish_flags.append(int(shadow_policy["shadow_policy_should_publish_flag"]))
        shadow_policy_should_affect_final_order_flags.append(int(shadow_policy["shadow_policy_should_affect_final_order_flag"]))
        statuses.append(status_value)
        reasons.append(reason_value)

    return pd.DataFrame(
        {
            "provisional_review_order_units": pd.Series(provisional_units, index=index, dtype="int64"),
            "final_store_order_units": pd.Series(final_units, index=index, dtype="int64"),
            "provisional_review_order_value": pd.Series(provisional_values, index=index, dtype="float64"),
            "final_store_order_value": pd.Series(final_values, index=index, dtype="float64"),
            "low_soh_policy_version": pd.Series(low_soh_policy_versions, index=index, dtype="object"),
            "low_soh_policy_candidate_flag": pd.Series(low_soh_candidate_flags, index=index, dtype="int64"),
            "low_soh_policy_production_eligible_flag": pd.Series(low_soh_production_eligible_flags, index=index, dtype="int64"),
            "low_soh_policy_final_order_units": pd.Series(low_soh_final_order_units, index=index, dtype="int64"),
            "low_soh_policy_shadow_order_units": pd.Series(shadow_policy_order_units_values, index=index, dtype="int64"),
            "low_soh_policy_capital_at_risk": pd.Series(low_soh_capital_at_risk_values, index=index, dtype="float64"),
            "low_soh_policy_reason": pd.Series(low_soh_policy_reasons, index=index, dtype="object"),
            "low_soh_policy_guardrail_status": pd.Series(low_soh_guardrail_statuses, index=index, dtype="object"),
            "low_soh_policy_blocker_reason": pd.Series(low_soh_blocker_reasons, index=index, dtype="object"),
            "low_soh_policy_decision_source": pd.Series(low_soh_decision_sources, index=index, dtype="object"),
            "shadow_policy_name": pd.Series(shadow_policy_names, index=index, dtype="object"),
            "shadow_policy_version": pd.Series(shadow_policy_versions, index=index, dtype="object"),
            "shadow_policy_candidate_flag": pd.Series(shadow_policy_candidate_flags, index=index, dtype="int64"),
            "shadow_policy_segment": pd.Series(shadow_policy_segments, index=index, dtype="object"),
            "shadow_policy_order_units": pd.Series(shadow_policy_order_units_values, index=index, dtype="int64"),
            "shadow_policy_capital_at_risk": pd.Series(shadow_policy_capital_at_risk_values, index=index, dtype="float64"),
            "shadow_policy_expected_reason": pd.Series(shadow_policy_expected_reasons, index=index, dtype="object"),
            "shadow_policy_guardrail_status": pd.Series(shadow_policy_guardrail_statuses, index=index, dtype="object"),
            "shadow_policy_blocker_reason": pd.Series(shadow_policy_blocker_reasons, index=index, dtype="object"),
            "shadow_policy_should_publish_flag": pd.Series(shadow_policy_should_publish_flags, index=index, dtype="int64"),
            "shadow_policy_should_affect_final_order_flag": pd.Series(shadow_policy_should_affect_final_order_flags, index=index, dtype="int64"),
            "order_reconciliation_status": pd.Series(statuses, index=index, dtype="object"),
            "order_reconciliation_reason": pd.Series(reasons, index=index, dtype="object"),
        },
        index=index,
    )


def _build_store_order_reconciliation_diagnostic_frame(
    *,
    store_facing_frame: pd.DataFrame,
) -> pd.DataFrame:
    required_columns = [
        "store_number",
        "promotion_id",
        "promotion_name",
        "promotion_start_date",
        "promotion_end_date",
        "sku_number",
        "sku_description",
        "store_action_label",
        "raw_model_order_units",
        "provisional_review_order_units",
        "final_store_order_units",
        "low_soh_policy_version",
        "low_soh_policy_candidate_flag",
        "low_soh_policy_production_eligible_flag",
        "low_soh_policy_final_order_units",
        "low_soh_policy_shadow_order_units",
        "low_soh_policy_capital_at_risk",
        "low_soh_policy_reason",
        "low_soh_policy_guardrail_status",
        "low_soh_policy_blocker_reason",
        "low_soh_policy_decision_source",
        "shadow_policy_name",
        "shadow_policy_version",
        "shadow_policy_candidate_flag",
        "shadow_policy_segment",
        "shadow_policy_order_units",
        "shadow_policy_capital_at_risk",
        "shadow_policy_expected_reason",
        "shadow_policy_guardrail_status",
        "shadow_policy_blocker_reason",
        "shadow_policy_should_publish_flag",
        "shadow_policy_should_affect_final_order_flag",
        "raw_model_order_value",
        "final_store_order_value",
        "promo_allocated_units",
        "current_soh",
        "projected_SOH_at_promo_start",
        "floor_units_required",
        "expected_promo_demand",
        "available_to_sell_before_floor",
        "projected_stock_gap_units",
        "retail_risk_reward_ratio",
        "capital_drag_label",
        "availability_risk_label",
        "demand_evidence_label",
        "human_review_required_flag",
        "order_reconciliation_status",
        "order_reconciliation_reason",
    ]
    return store_facing_frame.loc[:, required_columns].copy()


def _build_store_order_reconciliation_summary_frame(
    *,
    store_facing_frame: pd.DataFrame,
) -> pd.DataFrame:
    raw_units = pd.to_numeric(store_facing_frame["raw_model_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    provisional_units = pd.to_numeric(store_facing_frame["provisional_review_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    final_units = pd.to_numeric(store_facing_frame["final_store_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    raw_value = pd.to_numeric(store_facing_frame["raw_model_order_value"], errors="coerce").fillna(0.0).clip(lower=0.0)
    final_value = pd.to_numeric(store_facing_frame["final_store_order_value"], errors="coerce").fillna(0.0).clip(lower=0.0)
    label = store_facing_frame["store_action_label"].fillna("").astype(str).str.strip().str.upper()
    suppressed_mask = label.isin(NON_EXECUTABLE_STORE_ACTION_LABELS.difference(PROVISIONAL_REVIEW_STORE_ACTION_LABELS)) & raw_units.gt(0.0) & final_units.le(0.0)
    contradiction_mask = label.isin(NON_EXECUTABLE_STORE_ACTION_LABELS) & final_units.gt(0.0)
    return pd.DataFrame(
        [
            {
                "total_rows": int(len(store_facing_frame.index)),
                "rows_where_raw_order_positive": int(raw_units.gt(0.0).sum()),
                "rows_where_final_order_positive": int(final_units.gt(0.0).sum()),
                "rows_suppressed_by_label_governance": int(suppressed_mask.sum()),
                "units_suppressed_by_label_governance": int(raw_units.loc[suppressed_mask].sum()),
                "value_suppressed_by_label_governance": round(float(raw_value.loc[suppressed_mask].sum() - final_value.loc[suppressed_mask].sum()), 2),
                "rows_sent_to_provisional_review": int(provisional_units.gt(0.0).sum()),
                "provisional_review_units": int(provisional_units.sum()),
                "final_buy_units": int(final_units.loc[label.eq("BUY")].sum()),
                "final_protect_availability_units": int(final_units.loc[label.eq("PROTECT_AVAILABILITY")].sum()),
                "final_order_value": round(float(final_value.sum()), 2),
                "count_of_contradictions_after_reconciliation": int(contradiction_mask.sum()),
            }
        ]
    )


def _build_store_suppressed_order_risk_audit_frame(
    *,
    store_facing_frame: pd.DataFrame,
) -> pd.DataFrame:
    raw_units = pd.to_numeric(store_facing_frame["raw_model_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    final_units = pd.to_numeric(store_facing_frame["final_store_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    provisional_units = pd.to_numeric(store_facing_frame["provisional_review_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    current_soh = pd.to_numeric(store_facing_frame["current_soh"], errors="coerce").fillna(0.0).clip(lower=0.0)
    on_order = pd.to_numeric(store_facing_frame["on_order_at_advice_time"], errors="coerce").fillna(0.0).clip(lower=0.0)
    expected_units_before = pd.to_numeric(store_facing_frame["expected_units_before_promo_start"], errors="coerce").fillna(0.0).clip(lower=0.0)
    projected_soh = pd.to_numeric(store_facing_frame["projected_SOH_at_promo_start"], errors="coerce").fillna(0.0).clip(lower=0.0)
    floor_units = pd.to_numeric(store_facing_frame["floor_units_required"], errors="coerce").fillna(MIN_LAUNCH_STOCK_UNITS)
    expected_demand = pd.to_numeric(store_facing_frame["expected_promo_demand"], errors="coerce").fillna(0.0).clip(lower=0.0)
    available_to_sell_before_floor = pd.to_numeric(store_facing_frame["available_to_sell_before_floor"], errors="coerce").fillna(0.0).clip(lower=0.0)
    expected_gap = (expected_demand - available_to_sell_before_floor).clip(lower=0.0)
    demand_label = store_facing_frame["demand_evidence_label"].fillna("").astype(str).str.strip().str.upper()
    availability_label = store_facing_frame["availability_risk_label"].fillna("").astype(str).str.strip().str.upper()
    capital_label = store_facing_frame["capital_drag_label"].fillna("").astype(str).str.strip().str.upper()
    risk_reward_ratio = pd.to_numeric(store_facing_frame["retail_risk_reward_ratio"], errors="coerce").fillna(0.0)
    expected_gp = pd.to_numeric(
        store_facing_frame.get(
            "expected_gp_on_speculative_units",
            pd.Series(0.0, index=store_facing_frame.index),
        ),
        errors="coerce",
    ).fillna(0.0)
    capital_at_risk = pd.to_numeric(store_facing_frame["capital_at_risk_adjusted_dollars"], errors="coerce").fillna(0.0).clip(lower=0.0)
    leftover_risk = store_facing_frame.get(
        "end_of_promo_residual_risk",
        pd.Series("", index=store_facing_frame.index, dtype="object"),
    ).fillna("").astype(str).str.strip().str.upper()
    suppression_reason = store_facing_frame["order_reconciliation_reason"].fillna("").astype(str).str.strip()
    label = store_facing_frame["store_action_label"].fillna("").astype(str).str.strip().str.upper()

    # De-minimis demand (<= 1 unit of honest model promo-window demand) is
    # treated as effectively weak for suppression-safety purposes. Patch C
    # corrects the *customer label* so a forecast of ~1 unit is no longer stamped
    # NO_DEMAND, but suppressing the order for a single-unit model forecast
    # remains a safe/justified hold (consistent with the legacy
    # expected_demand <= 1 weak-demand philosophy). We use the model promo-window
    # demand rather than the risk-buffered selected quantile so a protective
    # quantile bump (e.g. q85 -> 2 units) does not reclassify de-minimis demand
    # as credible. Without this, the relabel would convert previously-safe
    # NO_DEMAND suppressions into unsafe-floor risks and hard-abort the run.
    de_minimis_demand_basis = pd.to_numeric(
        store_facing_frame["promo_window_demand_units"]
        if "promo_window_demand_units" in store_facing_frame.columns
        else (
            store_facing_frame["selected_demand_units"]
            if "selected_demand_units" in store_facing_frame.columns
            else store_facing_frame.get("expected_promo_demand", pd.Series(0.0, index=store_facing_frame.index))
        ),
        errors="coerce",
    ).fillna(0.0)
    de_minimis_selected_demand = de_minimis_demand_basis.le(1.0)

    suppressed_mask = raw_units.gt(0.0) & final_units.le(0.0)
    projected_below_floor = projected_soh.lt(floor_units)
    credible_demand = demand_label.isin(DYNAMIC_DEMAND_EVIDENCE_LABELS) & ~de_minimis_selected_demand
    weak_demand = demand_label.isin(WEAK_DEMAND_EVIDENCE_LABELS) | de_minimis_selected_demand
    materially_above_demand = projected_soh.gt(expected_demand + floor_units)
    capital_drag_safe = capital_label.eq("CAPITAL_DRAG_HIGH") | materially_above_demand
    availability_risk_high = availability_label.isin(HIGH_AVAILABILITY_RISK_LABELS)
    provisional_review = provisional_units.gt(0.0) | label.eq("BORDERLINE_OOS_REVIEW")

    suppression_risk = pd.Series(SUPPRESSION_RISK_NOT_APPLICABLE, index=store_facing_frame.index, dtype="object")
    suppression_risk = suppression_risk.where(~(suppressed_mask & provisional_review), SUPPRESSION_RISK_BORDERLINE_REVIEW)
    suppression_risk = suppression_risk.where(
        ~(suppressed_mask & projected_below_floor & credible_demand & ~provisional_review),
        SUPPRESSION_RISK_UNSAFE_ONLINE_AVAILABILITY,
    )
    suppression_risk = suppression_risk.where(
        ~(suppressed_mask & expected_gap.gt(0.0) & credible_demand & ~provisional_review),
        SUPPRESSION_RISK_UNSAFE_FLOOR,
    )
    # PROTECT_AVAILABILITY may cap to zero when the physical floor is already met;
    # that is a governed protect decision, not an unsafe silent suppression.
    protect_floor_already_met = (
        suppressed_mask
        & label.eq("PROTECT_AVAILABILITY")
        & projected_soh.ge(floor_units)
    )
    suppression_risk = suppression_risk.where(
        ~protect_floor_already_met,
        SUPPRESSION_RISK_SAFE_STOCK_COVERS_DEMAND,
    )
    suppression_risk = suppression_risk.where(
        ~(suppressed_mask & label.eq("REDUCE_HOLDING") & capital_drag_safe & suppression_risk.eq(SUPPRESSION_RISK_NOT_APPLICABLE)),
        SUPPRESSION_RISK_SAFE_CAPITAL_DRAG,
    )
    suppression_risk = suppression_risk.where(
        ~(suppressed_mask & label.isin({"NO_DEMAND", "NEVER_SOLD_IN_PROMO"}) & suppression_risk.eq(SUPPRESSION_RISK_NOT_APPLICABLE)),
        SUPPRESSION_RISK_SAFE_NO_DEMAND,
    )
    suppression_risk = suppression_risk.where(
        ~(suppressed_mask & expected_gap.le(0.0) & suppression_risk.eq(SUPPRESSION_RISK_NOT_APPLICABLE)),
        SUPPRESSION_RISK_SAFE_STOCK_COVERS_DEMAND,
    )
    suppression_risk = suppression_risk.where(
        ~(suppressed_mask & capital_drag_safe & suppression_risk.eq(SUPPRESSION_RISK_NOT_APPLICABLE)),
        SUPPRESSION_RISK_SAFE_CAPITAL_DRAG,
    )
    suppression_risk = suppression_risk.where(
        ~(suppressed_mask & weak_demand & suppression_risk.eq(SUPPRESSION_RISK_NOT_APPLICABLE)),
        SUPPRESSION_RISK_SAFE_NO_DEMAND,
    )

    should_protect = (
        suppressed_mask
        & suppression_risk.eq(SUPPRESSION_RISK_UNSAFE_ONLINE_AVAILABILITY)
        & risk_reward_ratio.ge(MIN_EXECUTABLE_RETAIL_RISK_REWARD_RATIO)
    ).astype(int)
    should_buy = (
        suppressed_mask
        & suppression_risk.eq(SUPPRESSION_RISK_UNSAFE_FLOOR)
        & risk_reward_ratio.ge(MIN_EXECUTABLE_RETAIL_RISK_REWARD_RATIO)
        & expected_gp.gt(0.0)
    ).astype(int)
    should_borderline = (
        suppressed_mask
        & (
            suppression_risk.eq(SUPPRESSION_RISK_BORDERLINE_REVIEW)
            | (
                suppression_risk.isin(
                    {
                        SUPPRESSION_RISK_UNSAFE_FLOOR,
                        SUPPRESSION_RISK_UNSAFE_ONLINE_AVAILABILITY,
                    }
                )
                & ~should_protect.astype(bool)
                & ~should_buy.astype(bool)
            )
        )
    ).astype(int)

    audit = pd.DataFrame(
        {
            "store_number": store_facing_frame["store_number"].astype(str),
            "promotion_id": store_facing_frame["promotion_id"].astype(str),
            "promotion_name": store_facing_frame["promotion_name"].astype(str),
            "promotion_start_date": store_facing_frame["promotion_start_date"].astype(str),
            "promotion_end_date": store_facing_frame["promotion_end_date"].astype(str),
            "sku_number": store_facing_frame["sku_number"].astype(str),
            "sku_description": store_facing_frame["sku_description"].astype(str),
            "store_action_label": label,
            "raw_model_order_units": raw_units.astype(int),
            "final_store_order_units": final_units.astype(int),
            "provisional_review_order_units": provisional_units.astype(int),
            "current_soh": current_soh.astype(int),
            "on_order_at_advice_time": on_order.astype(int),
            "expected_units_before_promo_start": expected_units_before.astype(int),
            "projected_SOH_at_promo_start": projected_soh.astype(int),
            "floor_units_required": floor_units.astype(int),
            "expected_promo_demand": expected_demand.astype(int),
            "available_to_sell_before_floor": available_to_sell_before_floor.astype(int),
            "expected_demand_above_floor_gap": expected_gap.astype(int),
            "availability_risk_label": availability_label,
            "capital_drag_label": capital_label,
            "demand_evidence_label": demand_label,
            "retail_risk_reward_ratio": risk_reward_ratio.astype(float),
            "expected_gp": expected_gp.round(2).astype(float),
            "capital_at_risk": capital_at_risk.round(2).astype(float),
            "leftover_risk": leftover_risk,
            "suppression_reason": suppression_reason,
            "suppression_risk_label": suppression_risk,
            "should_have_been_protect_availability_flag": should_protect,
            "should_have_been_borderline_oos_review_flag": should_borderline,
            "should_have_been_buy_flag": should_buy,
        }
    )
    return audit.loc[suppressed_mask].reset_index(drop=True)


def _build_store_suppressed_order_risk_summary_frame(
    *,
    store_facing_frame: pd.DataFrame,
    audit_frame: pd.DataFrame,
) -> pd.DataFrame:
    raw_units = pd.to_numeric(store_facing_frame["raw_model_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    final_units = pd.to_numeric(store_facing_frame["final_store_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    suppressed_units = pd.to_numeric(audit_frame.get("raw_model_order_units", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).clip(lower=0.0)
    suppression_risk = audit_frame.get("suppression_risk_label", pd.Series(dtype="object")).astype(str)
    safe_mask = suppression_risk.isin(
        {
            SUPPRESSION_RISK_SAFE_STOCK_COVERS_DEMAND,
            SUPPRESSION_RISK_SAFE_NO_DEMAND,
            SUPPRESSION_RISK_SAFE_CAPITAL_DRAG,
        }
    )
    unsafe_mask = suppression_risk.isin(
        {
            SUPPRESSION_RISK_UNSAFE_FLOOR,
            SUPPRESSION_RISK_UNSAFE_ONLINE_AVAILABILITY,
        }
    )
    borderline_mask = suppression_risk.eq(SUPPRESSION_RISK_BORDERLINE_REVIEW)
    denominator = float(len(audit_frame.index) or 1)
    return pd.DataFrame(
        [
            {
                "total_rows": int(len(store_facing_frame.index)),
                "raw_positive_order_rows": int(raw_units.gt(0.0).sum()),
                "final_positive_order_rows": int(final_units.gt(0.0).sum()),
                "suppressed_raw_positive_rows": int(len(audit_frame.index)),
                "suppressed_raw_positive_units": int(suppressed_units.sum()),
                "safe_suppression_rows": int(safe_mask.sum()),
                "safe_suppression_units": int(suppressed_units.loc[safe_mask].sum()),
                "unsafe_suppression_rows": int(unsafe_mask.sum()),
                "unsafe_suppression_units": int(suppressed_units.loc[unsafe_mask].sum()),
                "borderline_suppression_rows": int(borderline_mask.sum()),
                "borderline_suppression_units": int(suppressed_units.loc[borderline_mask].sum()),
                "safe_suppression_pct": round(float(safe_mask.sum()) / denominator, 4),
                "unsafe_suppression_pct": round(float(unsafe_mask.sum()) / denominator, 4),
                "contradiction_count": int(
                    (
                        store_facing_frame["store_action_label"].fillna("").astype(str).str.strip().isin(
                            ["NO_DEMAND", "HOLD_STOCK", "REDUCE_HOLDING", "NEVER_SOLD_IN_PROMO", "DATA_QUALITY_REVIEW"]
                        )
                        & final_units.gt(0.0)
                    ).sum()
                ),
                "rows_where_expected_demand_exceeds_available_to_sell_before_floor": int(
                    pd.to_numeric(audit_frame.get("expected_demand_above_floor_gap", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).gt(0.0).sum()
                ),
                "rows_where_projected_soh_below_floor": int(
                    (
                        pd.to_numeric(audit_frame.get("projected_SOH_at_promo_start", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)
                        < pd.to_numeric(audit_frame.get("floor_units_required", pd.Series(dtype="float64")), errors="coerce").fillna(MIN_LAUNCH_STOCK_UNITS)
                    ).sum()
                ),
                "rows_where_projected_soh_below_floor_and_final_order_zero": int(
                    (
                        pd.to_numeric(audit_frame.get("projected_SOH_at_promo_start", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)
                        < pd.to_numeric(audit_frame.get("floor_units_required", pd.Series(dtype="float64")), errors="coerce").fillna(MIN_LAUNCH_STOCK_UNITS)
                    ).sum()
                ),
                "rows_where_availability_risk_high_and_final_order_zero": int(
                    audit_frame.get("availability_risk_label", pd.Series(dtype="object")).astype(str).isin(HIGH_AVAILABILITY_RISK_LABELS).sum()
                ),
            }
        ]
    )


def _validate_store_suppressed_order_risk_audit(audit_frame: pd.DataFrame) -> None:
    if audit_frame.empty:
        return
    suppression_risk = audit_frame["suppression_risk_label"].astype(str)
    unsafe_mask = suppression_risk.isin(
        {
            SUPPRESSION_RISK_UNSAFE_FLOOR,
            SUPPRESSION_RISK_UNSAFE_ONLINE_AVAILABILITY,
        }
    )
    if bool(unsafe_mask.any()):
        sample_rows = audit_frame.loc[
            unsafe_mask,
            [
                "store_number",
                "promotion_id",
                "sku_number",
                "store_action_label",
                "suppression_risk_label",
                "expected_demand_above_floor_gap",
                "projected_SOH_at_promo_start",
                "floor_units_required",
                "demand_evidence_label",
            ],
        ].head(10)
        raise PromotionStoreDownloadCommercialValidationError(
            "Unsafe suppressed executable orders remain after Stage 11 reconciliation; "
            f"rows={int(unsafe_mask.sum())}; samples={sample_rows.to_dict(orient='records')}"
        )


def _build_store_action_label_distribution_frame(store_facing_frame: pd.DataFrame) -> pd.DataFrame:
    counts = store_facing_frame.get(
        "store_action_label",
        pd.Series([], dtype="object"),
    ).astype(str).value_counts(dropna=False).to_dict()
    return pd.DataFrame(
        [
            {
                "store_action_label": label,
                "row_count": int(counts.get(label, 0)),
            }
            for label in STORE_ACTION_LABELS
        ]
    )


def _build_store_data_quality_review_breakdown_frame(
    *,
    commercial_frame: pd.DataFrame,
    store_facing_frame: pd.DataFrame,
) -> pd.DataFrame:
    diagnostics = _build_discount_review_diagnostic_frame(commercial_frame)
    keys = ["store_number", "promotion_name", "promotion_start_date", "promotion_end_date", "sku_number", "product_description"]
    commercial = commercial_frame.loc[:, [*keys, "promotion_header_key", "publish_eligibility_reason", "review_reason"]].copy()
    for column_name in keys:
        commercial[column_name] = commercial[column_name].astype(str)
    commercial["promotion_id"] = commercial["promotion_header_key"].astype(str)
    commercial = pd.concat([commercial.reset_index(drop=True), diagnostics.reset_index(drop=True)], axis=1)

    store = store_facing_frame.copy().reset_index(drop=True)
    join_keys = ["store_number", "promotion_name", "promotion_start_date", "promotion_end_date", "sku_number"]
    for column_name in join_keys:
        if column_name in store.columns:
            store[column_name] = store[column_name].astype(str)
    merged = commercial.merge(
        store.loc[:, [
            *join_keys,
            "store_action_label",
            "blocker_reason",
            "low_nonzero_value_relief_delta",
            "demand_evidence_label",
            "availability_risk_label",
            "capital_drag_label",
            "human_review_required_flag",
            "recommended_action",
            "store_action_reason",
        ]],
        on=join_keys,
        how="left",
        sort=False,
    )

    repaired_label_frame = _build_store_action_label_frame(
        store_frame=store,
        display_action=store["recommended_action"],
        data_quality_flag=pd.Series("OK", index=store.index, dtype="object"),
        discount_reason_code=pd.Series(DISCOUNT_REVIEW_REASON_NO_ISSUE, index=store.index, dtype="object"),
        publish_eligibility_reason=commercial_frame["publish_eligibility_reason"].reset_index(drop=True),
        review_reason=commercial_frame["review_reason"].reset_index(drop=True),
    )
    merged["would_have_label_if_repaired"] = repaired_label_frame["store_action_label"].reindex(merged.index).fillna("")
    merged["data_quality_reason_code"] = merged["discount_data_quality_reason_code"].astype(str)
    merged["data_quality_reason_detail"] = merged["discount_data_quality_reason_detail"].astype(str)
    review_rows = merged.loc[
        merged["store_action_label"].astype(str).eq("DATA_QUALITY_REVIEW")
        | merged["data_quality_reason_code"].astype(str).isin(
            {
                DISCOUNT_REVIEW_REASON_REPAIRABLE_PRICE_TRUTH,
                DISCOUNT_REVIEW_REASON_ROUNDING_TOLERANCE,
                DISCOUNT_REVIEW_REASON_MAPPING_CONFLICT,
                DISCOUNT_REVIEW_REASON_HARD_MISSING_PRICES,
                DISCOUNT_REVIEW_REASON_HARD_INVALID_NORMAL,
                DISCOUNT_REVIEW_REASON_HARD_INVALID_PROMO,
                DISCOUNT_REVIEW_REASON_NO_DISCOUNT_VALID,
            }
        )
    ].copy()
    review_rows.rename(
        columns={
            "product_description": "sku_description",
            "mapped_discount_pct": "mapped_discount_pct",
            "price_derived_discount_pct": "price_derived_discount_pct",
            "price_normal": "price_normal",
            "price_promo": "price_promo",
            "discount_abs_diff": "discount_abs_diff",
            "discount_tolerance_used": "discount_tolerance_used",
            "can_repair_discount_flag": "can_repair_discount_flag",
            "repaired_discount_pct": "repaired_discount_pct",
            "repair_method": "repair_method",
        },
        inplace=True,
    )
    ordered_columns = [
        "store_number",
        "promotion_id",
        "promotion_name",
        "promotion_start_date",
        "promotion_end_date",
        "sku_number",
        "sku_description",
        "store_action_label",
        "data_quality_reason_code",
        "data_quality_reason_detail",
        "price_normal",
        "price_promo",
        "mapped_discount_pct",
        "price_derived_discount_pct",
        "discount_abs_diff",
        "discount_tolerance_used",
        "can_repair_discount_flag",
        "repaired_discount_pct",
        "repair_method",
        "would_have_label_if_repaired",
    ]
    return review_rows.loc[:, ordered_columns].sort_values(
        by=["data_quality_reason_code", "store_number", "promotion_name", "sku_number"],
        kind="mergesort",
    ).reset_index(drop=True)


def _build_store_data_quality_review_reason_distribution_frame(
    *,
    breakdown_frame: pd.DataFrame,
    total_row_count: int,
) -> pd.DataFrame:
    if breakdown_frame.empty:
        return pd.DataFrame(
            columns=[
                "data_quality_reason_code",
                "row_count",
                "pct_of_total_rows",
                "pct_of_data_quality_review_rows",
                "example_sku_count",
            ]
        )
    grouped = (
        breakdown_frame.groupby("data_quality_reason_code", dropna=False)
        .agg(
            row_count=("data_quality_reason_code", "size"),
            example_sku_count=("sku_number", lambda values: int(pd.Series(values).astype(str).nunique(dropna=True))),
        )
        .reset_index()
        .sort_values(by=["row_count", "data_quality_reason_code"], ascending=[False, True], kind="mergesort")
    )
    dq_rows = max(int(len(breakdown_frame.index)), 1)
    grouped["pct_of_total_rows"] = grouped["row_count"].divide(max(total_row_count, 1)).mul(100.0).round(2)
    grouped["pct_of_data_quality_review_rows"] = grouped["row_count"].divide(dq_rows).mul(100.0).round(2)
    return grouped.loc[:, [
        "data_quality_reason_code",
        "row_count",
        "pct_of_total_rows",
        "pct_of_data_quality_review_rows",
        "example_sku_count",
    ]]


def _compose_primary_review_reason(
    *,
    action: pd.Series,
    data_quality_flag: pd.Series,
    model_reason_summary: pd.Series,
    review_reason: pd.Series | None = None,
) -> pd.Series:
    action_upper = action.astype(str).str.strip().str.upper()
    quality_upper = data_quality_flag.astype(str).str.strip().str.upper()
    reason = pd.Series("", index=action.index, dtype="object")
    review_rows = action_upper.isin({"REVIEW", "REVIEW_REQUIRED"})
    reason = reason.where(
        ~(review_rows & quality_upper.eq("REVIEW_DISCOUNT_MISSING")),
        "Governed discount mapping is missing; price-derived discount requires review",
    )
    reason = reason.where(
        ~(review_rows & quality_upper.eq("REVIEW_DISCOUNT_CONFLICT")),
        "Governed discount conflicts with price-derived discount",
    )
    reason = reason.where(~(review_rows & quality_upper.eq("INSUFFICIENT_HISTORY")), "Insufficient history for automatic ordering")
    reason = reason.where(~(review_rows & quality_upper.eq("COLLAPSED_FORECAST")), "Forecast collapsed to flat pattern")
    reason = reason.where(~(review_rows & quality_upper.eq("REVIEW_FORECAST")), "Forecast requires manager review")
    if review_reason is not None:
        explicit_reason = review_reason.reindex(action.index).fillna("").astype(str).str.strip()
        explicit_reason = explicit_reason.where(
            ~explicit_reason.isin(_DISCOUNT_REVIEW_REASON_BY_FLAG.values()),
            explicit_reason.map(
                {
                    "review_discount_missing": "Governed discount mapping is missing; price-derived discount requires review",
                    "review_discount_conflict": "Governed discount conflicts with price-derived discount",
                }
            ).fillna(explicit_reason),
        )
        discount_contract_reason = review_rows & quality_upper.isin({
            "REVIEW_DISCOUNT_MISSING",
            "REVIEW_DISCOUNT_CONFLICT",
        })
        reason = reason.where(~(review_rows & explicit_reason.ne("") & ~discount_contract_reason), explicit_reason)
    fallback = model_reason_summary.astype(str).str.strip()
    reason = reason.where(~(review_rows & reason.eq("")), fallback)
    reason = reason.where(~(review_rows & reason.eq("")), "Manager review required")
    return reason


def _normalize_action_data_quality_consistency(
    *,
    action: pd.Series,
    data_quality_flag: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    action_upper = action.astype(str).str.strip().str.upper()
    quality_upper = data_quality_flag.astype(str).str.strip().str.upper()

    review_quality_mask = quality_upper.str.startswith("REVIEW") | quality_upper.eq("COLLAPSED_FORECAST")
    action_upper = action_upper.where(~(action_upper.eq("ORDER") & review_quality_mask), "REVIEW")
    quality_upper = quality_upper.where(~(action_upper.eq("REVIEW") & quality_upper.eq("OK")), "REVIEW_FORECAST")

    return action_upper, quality_upper


def _normalize_action_review_hold_consistency(
    *,
    action: pd.Series,
    data_quality_flag: pd.Series,
    review_reason: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    action_upper = action.astype(str).str.strip().str.upper()
    quality_upper = data_quality_flag.astype(str).str.strip().str.upper()
    review_reason_present = review_reason.fillna("").astype(str).str.strip().ne("")

    review_hold_mask = action_upper.eq("ORDER") & review_reason_present
    action_upper = action_upper.where(~review_hold_mask, "REVIEW")
    quality_upper = quality_upper.where(~(review_hold_mask & quality_upper.eq("OK")), "REVIEW_FORECAST")

    return action_upper, quality_upper


def _validate_store_facing_operator_contract(frame: pd.DataFrame) -> None:
    failures: list[str] = []

    if any(
        column in frame.columns
        for column in (
            "backtest_within_10pct_flag",
            "backtest_mean_absolute_pct_error",
            "backtest_bias_class",
            "backtest_comparable_event_count",
        )
    ):
        failures.append("store-facing frame must not emit legacy row-level backtest_* columns")

    sku_backtest_columns = sorted(
        column for column in frame.columns if column.startswith("sku_backtest_")
    )
    if sku_backtest_columns:
        failures.append(
            "store-facing frame must not emit sku_backtest_* fields without a governed per-SKU Stage 11 source: "
            + ", ".join(sku_backtest_columns)
        )

    duplicate_mask = frame.duplicated(
        subset=["store_number", "promotion_name", "promotion_start_date", "promotion_end_date", "sku_number"],
        keep=False,
    )
    duplicate_count = int(duplicate_mask.sum())
    if duplicate_count > 0:
        failures.append(f"store-facing frame contains duplicate row grain rows: {duplicate_count}")

    action = frame["recommended_action"].astype(str).str.strip().str.upper()
    readiness = frame["execution_readiness_status"].astype(str).str.strip().str.upper()
    expected_readiness = _compose_execution_readiness_status(action)
    readiness_mismatch_count = int(readiness.ne(expected_readiness).sum())
    if readiness_mismatch_count > 0:
        failures.append(
            f"recommended_action and execution_readiness_status conflict on {readiness_mismatch_count} row(s)"
        )

    quality = frame["data_quality_flag"].astype(str).str.strip().str.upper()
    legacy_discount_mapping_count = int(quality.eq("REVIEW_DISCOUNT_MAPPING").sum())
    if legacy_discount_mapping_count > 0:
        failures.append(
            "store-facing frame must emit precise discount review flags, not REVIEW_DISCOUNT_MAPPING "
            f"(rows={legacy_discount_mapping_count})"
        )

    review_action_mask = action.isin({"REVIEW", "REVIEW_REQUIRED"})
    review_ok_count = int((review_action_mask & quality.eq("OK")).sum())
    if review_ok_count > 0:
        failures.append(f"REVIEW rows cannot carry OK data_quality_flag (rows={review_ok_count})")

    order_review_quality_count = int(
        (action.eq("ORDER") & (quality.str.startswith("REVIEW") | quality.eq("COLLAPSED_FORECAST"))).sum()
    )
    if order_review_quality_count > 0:
        failures.append(
            "ORDER rows cannot carry review/collapsed data_quality_flag "
            f"(rows={order_review_quality_count})"
        )

    if "store_action_label" in frame.columns and "recommended_order_units" in frame.columns:
        label = frame["store_action_label"].astype(str).str.strip().str.upper()
        recommended_units = pd.to_numeric(frame["recommended_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
        final_units = pd.to_numeric(
            frame.get("final_store_order_units", frame["recommended_order_units"]),
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0)
        recommended_final_mismatch_count = int(recommended_units.ne(final_units).sum())
        if recommended_final_mismatch_count > 0:
            failures.append(
                "recommended_order_units must equal final_store_order_units after reconciliation "
                f"(rows={recommended_final_mismatch_count})"
            )

        contradiction_count = int(
            (label.isin(NON_EXECUTABLE_STORE_ACTION_LABELS) & final_units.gt(0.0)).sum()
        )
        if contradiction_count > 0:
            failures.append(
                "non-executable store_action_label rows cannot carry positive final executable units "
                f"(rows={contradiction_count})"
            )

    narrative = frame["historical_promo_response_summary"].astype(str)
    same_count = pd.to_numeric(frame["historical_promo_events_same_discount"], errors="coerce").fillna(0)
    same_avg = pd.to_numeric(
        frame.get(
            "historical_units_same_discount_avg",
            pd.Series([0.0] * len(frame.index), index=frame.index),
        ),
        errors="coerce",
    ).fillna(0.0)
    better_count = pd.to_numeric(frame["historical_promo_events_same_or_better_discount"], errors="coerce").fillna(0)
    better_avg = pd.to_numeric(
        frame.get(
            "historical_units_same_or_better_discount_avg",
            pd.Series([0.0] * len(frame.index), index=frame.index),
        ),
        errors="coerce",
    ).fillna(0.0)
    no_history_mask = narrative.str.contains("No matching promo history available", case=False, na=False)
    no_history_contradiction_count = int((no_history_mask & (same_count.gt(0) | better_count.gt(0))).sum())
    if no_history_contradiction_count > 0:
        failures.append(
            "historical_promo_response_summary contradicts numeric history counts "
            f"(rows={no_history_contradiction_count})"
        )

    zero_sales_history_mask = (same_count.gt(0) & same_avg.le(0.0)) | (
        same_count.eq(0) & better_count.gt(0) & better_avg.le(0.0)
    )
    missing_zero_sales_count = int(
        (zero_sales_history_mask & ~narrative.str.contains(r"sold 0\.0 units on average", case=False, na=False)).sum()
    )
    if missing_zero_sales_count > 0:
        failures.append(
            "rows with positive history counts and zero historical average must state zero-sales history "
            f"(rows={missing_zero_sales_count})"
        )

    broader_history_mask = same_count.eq(0) & better_count.gt(0)
    missing_broader_history_count = int(
        (broader_history_mask & ~narrative.str.contains("same-or-better", case=False, na=False)).sum()
    )
    if missing_broader_history_count > 0:
        failures.append(
            "rows with same-or-better history must state broader-history narrative "
            f"(rows={missing_broader_history_count})"
        )

    comparable_backtest_count = pd.to_numeric(
        frame.get(
            "promotion_backtest_comparable_event_count",
            pd.Series([0] * len(frame.index), index=frame.index),
        ),
        errors="coerce",
    ).fillna(0)
    no_comparable_mask = comparable_backtest_count.le(0)
    no_comparable_mape_count = int(
        (
            no_comparable_mask
            & pd.to_numeric(
                frame.get(
                    "promotion_backtest_mean_absolute_pct_error",
                    pd.Series([float("nan")] * len(frame.index), index=frame.index),
                ),
                errors="coerce",
            ).notna()
        ).sum()
    )
    if no_comparable_mape_count > 0:
        failures.append(
            "rows with zero promotion_backtest_comparable_event_count must leave promotion_backtest_mean_absolute_pct_error blank "
            f"(rows={no_comparable_mape_count})"
        )

    no_comparable_within_count = int(
        (
            no_comparable_mask
            & pd.to_numeric(
                frame.get(
                    "promotion_backtest_within_10pct_flag",
                    pd.Series([float("nan")] * len(frame.index), index=frame.index),
                ),
                errors="coerce",
            ).notna()
        ).sum()
    )
    if no_comparable_within_count > 0:
        failures.append(
            "rows with zero promotion_backtest_comparable_event_count must leave promotion_backtest_within_10pct_flag blank "
            f"(rows={no_comparable_within_count})"
        )

    backtest_bias = frame.get(
        "promotion_backtest_bias_class",
        pd.Series(["NO_COMPARABLE_EVENTS"] * len(frame.index), index=frame.index),
    ).astype(str).str.strip().str.upper()
    invalid_no_comparable_bias_count = int(
        (no_comparable_mask & backtest_bias.ne("NO_COMPARABLE_EVENTS")).sum()
    )
    if invalid_no_comparable_bias_count > 0:
        failures.append(
            "rows with zero promotion_backtest_comparable_event_count must emit promotion_backtest_bias_class=NO_COMPARABLE_EVENTS "
            f"(rows={invalid_no_comparable_bias_count})"
        )

    review_reason = frame["primary_review_reason"].astype(str).str.strip()
    missing_review_reason_count = int((review_action_mask & review_reason.eq("")).sum())
    if missing_review_reason_count > 0:
        failures.append(
            f"REVIEW rows require non-empty primary_review_reason (rows={missing_review_reason_count})"
        )

    forecast_trust_summary = frame.get(
        "forecast_trust_summary",
        pd.Series([""] * len(frame.index), index=frame.index),
    ).astype(str).str.strip()
    missing_trust_summary_count = int(forecast_trust_summary.eq("").sum())
    if missing_trust_summary_count > 0:
        failures.append(
            "forecast_trust_summary must be non-empty and state promotion-level scope explicitly "
            f"(rows={missing_trust_summary_count})"
        )
    nonexplicit_trust_summary_count = int(
        (
            forecast_trust_summary.ne("")
            & ~forecast_trust_summary.str.contains(
                r"^Promotion-level backtest",
                case=False,
                na=False,
            )
        ).sum()
    )
    if nonexplicit_trust_summary_count > 0:
        failures.append(
            "forecast_trust_summary must state promotion-level scope explicitly "
            f"(rows={nonexplicit_trust_summary_count})"
        )

    if failures:
        raise PromotionStoreDownloadCommercialValidationError("; ".join(failures))


def _resolve_allocation_hard_blocker_codes(
    *,
    commercial_frame: pd.DataFrame,
    action: pd.Series,
    contract_frame: pd.DataFrame,
) -> pd.Series:
    """Map governed commercial signals to documented hard order blockers."""
    index = commercial_frame.index
    blockers = pd.Series("", index=index, dtype="object")
    action_upper = action.astype(str).str.strip().str.upper()
    evidence_class = commercial_frame["demand_evidence_class"].astype(str).str.strip().str.lower()
    data_quality = commercial_frame.get(
        "data_quality_flag",
        pd.Series("", index=index, dtype="object"),
    ).fillna("").astype(str).str.strip().str.upper()
    publish_reason = commercial_frame.get(
        "publish_eligibility_reason",
        pd.Series("", index=index, dtype="object"),
    ).fillna("").astype(str).str.strip().str.upper()
    review_reason = commercial_frame.get(
        "review_reason",
        pd.Series("", index=index, dtype="object"),
    ).fillna("").astype(str).str.strip().str.upper()
    cash_band = commercial_frame.get(
        "estimated_cash_risk_band",
        pd.Series("", index=index, dtype="object"),
    ).fillna("").astype(str).str.strip().str.upper()
    pack_size = pd.to_numeric(
        commercial_frame.get("pack_size", pd.Series(1.0, index=index, dtype="float64")),
        errors="coerce",
    ).fillna(1.0).clip(lower=1.0)
    raw_gap = pd.to_numeric(contract_frame["raw_stock_gap_units"], errors="coerce").fillna(0.0)

    invalid_data = data_quality.isin({"INVALID", "DATA_QUALITY_REVIEW", "MISSING_PRICE", "MISSING_FORECAST"})
    blockers = blockers.where(~invalid_data, "blocked_by_invalid_data")

    sparse_no_order = evidence_class.isin(ORDER_EVIDENCE_NO_EVIDENCE_CLASSES) & action_upper.eq("DO_NOT_ORDER")
    blockers = blockers.where(~sparse_no_order, "blocked_by_sparse_history")

    manual_review = action_upper.eq("REVIEW") & (
        publish_reason.str.contains("MANUAL", regex=False)
        | review_reason.str.contains("MANUAL", regex=False)
    )
    blockers = blockers.where(~manual_review, "blocked_by_manual_review")

    capital_block = cash_band.eq("HIGH") & action_upper.eq("DO_NOT_ORDER") & raw_gap.gt(0.0)
    blockers = blockers.where(~capital_block, "blocked_by_capital_rule")

    pack_block = raw_gap.gt(0.0) & pack_size.gt(float(LOW_SOH_POLICY_MAX_PACK_SIZE_AUTO_ORDER))
    blockers = blockers.where(~pack_block, "blocked_by_supplier_or_pack_constraint")
    return blockers.astype(str)


def _apply_allocation_contract_final_orders(
    *,
    store_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Keep final operator order units aligned with the governed stock contract."""
    out = store_frame.copy()
    # The order reconciliation frame has already applied operator-decision
    # gating (non-executable labels, review holds, low-SOH policy, hard
    # blockers) to the governed contract order that was published as
    # `raw_model_order_units`. The operator-visible recommended order must
    # equal that gated final so the report stays internally consistent.
    final_units = pd.to_numeric(out["final_store_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    final_units_int = final_units.round(0).astype("int64")
    final_value = pd.to_numeric(
        out.get("final_store_order_value", pd.Series(0.0, index=out.index)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    out["final_store_order_units"] = final_units_int
    out["recommended_order_units"] = final_units_int
    out["final_store_order_value"] = final_value.round(2).astype(float)
    out["recommended_order_value"] = out["final_store_order_value"]

    # Where a genuine stock gap was suppressed to zero by the operator-decision
    # gating without an explicit hard blocker, record a documented review
    # blocker so the gap/order reconciliation remains auditable.
    raw_gap = pd.to_numeric(out.get("raw_stock_gap_units", pd.Series(0.0, index=out.index)), errors="coerce").fillna(0.0)
    order_reason = out.get("order_reason_code", pd.Series("", index=out.index)).fillna("").astype(str).str.strip()
    has_hard_blocker = order_reason.isin(HARD_ORDER_BLOCKER_CODES)
    suppressed_by_gating = raw_gap.gt(0.0) & final_units_int.le(0) & ~has_hard_blocker
    out["order_reason_code"] = order_reason.where(~suppressed_by_gating, "blocked_by_manual_review")
    return out


def _build_store_facing_frame(
    *,
    commercial_frame: pd.DataFrame,
    forecast_per_row_diagnostics: pd.DataFrame | None,
    as_of_date: str | None,
    completed_backtest_summary: dict[str, object] | None = None,
    sku_backtest_summary: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Derive the operator-friendly Stage 11/12 store-facing CSV from the commercial frame."""
    frame = commercial_frame
    out = pd.DataFrame(index=frame.index)

    # ---- Identity -------------------------------------------------------
    out["store_number"] = frame["store_number"].astype(str)
    if "promotion_id" in frame.columns:
        out["promotion_id"] = frame["promotion_id"].astype(str)
    elif "promotion_header_key" in frame.columns:
        out["promotion_id"] = frame["promotion_header_key"].astype(str)
    else:
        out["promotion_id"] = frame["promotion_name"].astype(str)
    out["promotion_name"] = frame["promotion_name"].astype(str)
    out["promotion_start_date"] = frame["promotion_start_date"].astype(str)
    out["promotion_end_date"] = frame["promotion_end_date"].astype(str)
    out["sku_number"] = frame["sku_number"].astype(str)
    out["sku_description"] = frame["product_description"].astype(str)

    # ---- Action ---------------------------------------------------------
    action = frame["decision_recommendation"].astype(str).str.upper()
    out["target_stock_day_one_units"] = _store_int(frame["promo_start_target_soh_units"])
    out["minimum_safe_stock_day_one_units"] = _store_int(frame["base_units_target"])

    # ---- Demand timing --------------------------------------------------
    # Compute lead days (unclamped) so the 56-day store-ordering horizon clamp
    # can scale pre-promo demand commensurately. This protects the operator
    # CSV from any upstream prediction_date / as_of_date drift that would
    # otherwise inflate `expected_units_before_promo_start` and produce a
    # misleadingly large "gap before launch" for far-future promotions.
    if as_of_date:
        as_of_dt = pd.to_datetime(as_of_date, errors="coerce")
        promo_start_dt = pd.to_datetime(frame["promotion_start_date"], errors="coerce")
        lead_unclamped = (promo_start_dt - as_of_dt).dt.days
        lead_unclamped = pd.to_numeric(lead_unclamped, errors="coerce").fillna(0).clip(lower=0)
    else:
        lead_unclamped = pd.Series(0, index=frame.index, dtype="int64")
    lead = lead_unclamped.clip(upper=STORE_PRE_PROMO_HORIZON_DAYS)
    out["lead_days_to_promo_start"] = lead.round(0).astype("int64")
    out["days_to_promo_start"] = lead.round(0).astype("int64")
    out["prediction_date"] = (
        str(as_of_date) if as_of_date else ""
    )

    # Rebound pre-promo expected units so they can never represent more than
    # `STORE_PRE_PROMO_HORIZON_DAYS` of forward demand. We scale the model's
    # original projection by the ratio of the bounded window to the
    # unclamped window. When the unclamped window is already <= 56 the
    # scale is 1.0 (no change to model output).
    raw_expected_pre = pd.to_numeric(
        frame["predicted_units_until_promo_start"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    horizon_scale = pd.Series(1.0, index=frame.index, dtype="float64")
    long_horizon_mask = lead_unclamped > STORE_PRE_PROMO_HORIZON_DAYS
    if long_horizon_mask.any():
        horizon_scale = horizon_scale.where(
            ~long_horizon_mask,
            (
                pd.Series(STORE_PRE_PROMO_HORIZON_DAYS, index=frame.index, dtype="float64")
                / lead_unclamped.where(lead_unclamped > 0, 1).astype("float64")
            ).clip(upper=1.0),
        )
    bounded_expected_pre = (raw_expected_pre * horizon_scale).clip(lower=0.0)

    out["expected_units_before_promo_start"] = _store_int(bounded_expected_pre)
    out["expected_units_first_7_days"] = _store_int(frame["predicted_units_first_7_days_of_promo"])
    out["expected_units_total_promo"] = _store_int(frame["predicted_units_total_promo"])
    out["expected_promo_demand"] = out["expected_units_total_promo"]
    feature_period_days = _optional_numeric_series(frame, "feature_promo_period_days")
    promotion_period_days = feature_period_days.replace(0.0, pd.NA)
    source_period_days = _numeric_series(frame, ("live_promo_window_days", "promo_days")).replace(0.0, pd.NA)
    derived_period_days = (
        pd.to_datetime(frame["promotion_end_date"], errors="coerce")
        - pd.to_datetime(frame["promotion_start_date"], errors="coerce")
    ).dt.days.add(1).clip(lower=1)
    promotion_period_days = promotion_period_days.where(
        promotion_period_days.notna(),
        source_period_days,
    )
    promotion_period_days = promotion_period_days.where(
        promotion_period_days.notna(),
        derived_period_days,
    ).fillna(1.0)
    expected_units_per_period = pd.to_numeric(
        frame["predicted_units_total_promo"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    out["promotion_period_days"] = promotion_period_days.round(0).astype("int64")
    out["expected_units_per_period"] = _store_int(expected_units_per_period)
    out["expected_units_per_day"] = (
        expected_units_per_period.divide(promotion_period_days.where(promotion_period_days.gt(0.0), 1.0))
        .fillna(0.0)
        .round(4)
        .astype(float)
    )

    # ---- Governed demand-forecast contract (runs BEFORE the stock contract) ----
    # Forecasted units must represent expected demand under sufficient stock,
    # not raw historical sales which may be stock-constrained. The demand
    # contract separates pre-promo leakage from promo-window demand and never
    # silently fills missing demand with zero (routes to REVIEW instead).
    raw_soh_for_integrity = pd.to_numeric(frame["current_soh_units"], errors="coerce")
    demand_confidence_fraction = (
        _numeric_series(frame, ("final_confidence_score",))
        .fillna(CAPITAL_AT_RISK_DEFAULT_CONFIDENCE)
        .clip(lower=0.0, upper=1.0)
    )
    demand_evidence_lower = frame["demand_evidence_class"].astype(str).str.strip().str.lower()
    demand_sparse_mask = demand_evidence_lower.isin(ORDER_EVIDENCE_SPARSE_CLASSES) | demand_evidence_lower.isin(
        ORDER_EVIDENCE_NO_EVIDENCE_CLASSES
    )
    demand_cash_band = (
        frame.get("estimated_cash_risk_band", pd.Series("", index=frame.index))
        .fillna("")
        .astype(str)
        .str.upper()
    )
    demand_capital_drag_mask = demand_cash_band.eq("HIGH")
    # Pass the raw fractional model promo prediction so sub-unit demand is not
    # silently floored to 1 before the governed demand contract runs.
    fractional_promo_units = _resolve_fractional_promo_units_series(frame)
    model_promo_units_raw = pd.to_numeric(
        fractional_promo_units
        if fractional_promo_units is not None
        else frame["predicted_units_total_promo"],
        errors="coerce",
    )
    # Stockout is costly when on-hand plus confirmed inbound cannot cover the
    # expected promo-window demand. Combined with high trust this escalates the
    # selected demand quantile (protect availability); low trust stays at q50.
    demand_soh_plus_inbound = (
        raw_soh_for_integrity.clip(lower=0.0).fillna(0.0)
        + pd.to_numeric(frame["qty_on_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    )
    demand_high_stockout_cost = demand_soh_plus_inbound.lt(
        model_promo_units_raw.fillna(0.0)
    ) & model_promo_units_raw.fillna(0.0).gt(0.0)
    # Feature-layer demand signal (Patch B): used ONLY to detect a model/source
    # demand collapse, never to inflate or replace the model prediction. Prefer
    # the consensus expected-units signal, then first-7-days, then same-discount
    # history.
    demand_feature_signal = _optional_first_numeric_series(
        frame,
        (
            "feature_probability_expected_units_consensus",
            "feature_expected_total_units_first_7_days",
            "feature_historical_units_same_discount_avg",
            "historical_units_same_discount_avg",
        ),
    )
    demand_forecast_frame = build_demand_forecast_contract_frame(
        model_run_date=as_of_date or "",
        promotion_start_date=frame["promotion_start_date"],
        promotion_end_date=frame["promotion_end_date"],
        baseline_daily_units=out["expected_units_per_day"],
        promo_uplift_factor=1.0,
        pre_promo_demand_units_input=bounded_expected_pre,
        model_promo_window_units=model_promo_units_raw,
        confidence_fraction=demand_confidence_fraction,
        sparse_or_weak_evidence=demand_sparse_mask,
        negative_soh_detected=raw_soh_for_integrity.lt(0.0),
        high_capital_drag=demand_capital_drag_mask,
        high_stockout_cost=demand_high_stockout_cost,
        feature_demand_signal=demand_feature_signal,
    )
    demand_validation_started = time.perf_counter()
    demand_validation_summary, demand_validation_issues = validate_demand_forecast_contract_frame(
        demand_forecast_frame
    )
    log_demand_forecast_validation(demand_validation_summary, started_at=demand_validation_started)
    for column_name in demand_forecast_frame.columns:
        out[column_name] = demand_forecast_frame[column_name]
    out = sync_demand_forecast_aliases(out)
    out.attrs["demand_forecast_contract_validation_summary"] = demand_validation_summary.to_dict()
    out.attrs["demand_forecast_contract_validation_issue_count"] = int(len(demand_validation_issues.index))

    # The allocation stock contract consumes the governed demand fields: the
    # horizon-bounded pre-promo demand and the policy-selected promo-window
    # demand quantile. Selected demand defaults to q50 (the model prediction)
    # so governed production ordering is preserved for the common case.
    demand_pre_promo_units = pd.to_numeric(
        demand_forecast_frame["pre_promo_demand_units"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    demand_selected_units = pd.to_numeric(
        demand_forecast_frame["selected_demand_units"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)

    # ---- Current stock position (governed allocation contract) ----------
    soh = pd.to_numeric(frame["current_soh_units"], errors="coerce").fillna(0.0)
    on_order = pd.to_numeric(frame["qty_on_order_units"], errors="coerce").fillna(0.0)
    floor_units = pd.to_numeric(frame["base_units_target"], errors="coerce").fillna(MIN_LAUNCH_STOCK_UNITS).clip(lower=0.0)
    pack_size = pd.to_numeric(
        frame.get("pack_size", pd.Series(1.0, index=frame.index, dtype="float64")),
        errors="coerce",
    ).fillna(1.0).clip(lower=1.0)
    contract_frame = build_allocation_stock_contract_frame(
        model_run_date=as_of_date or "",
        promotion_start_date=frame["promotion_start_date"],
        promotion_end_date=frame["promotion_end_date"],
        current_soh_at_model_run=soh,
        confirmed_inbound_units_before_promo_start=on_order,
        expected_pre_promo_demand_units=demand_pre_promo_units,
        expected_promo_window_demand_units=demand_selected_units,
        floor_units_required_at_promo_start=floor_units,
        pack_size=pack_size,
    )
    hard_blockers = _resolve_allocation_hard_blocker_codes(
        commercial_frame=frame,
        action=action,
        contract_frame=contract_frame,
    )
    contract_frame = apply_allocation_order_blockers(
        contract_frame=contract_frame,
        hard_blocker_codes=hard_blockers,
    )
    for column_name in contract_frame.columns:
        out[column_name] = contract_frame[column_name]
    out = sync_allocation_contract_aliases(out)
    projected_on_hand = pd.to_numeric(
        out["projected_soh_at_promo_start_before_order"], errors="coerce"
    ).fillna(0.0)
    target_day_one = pd.to_numeric(out["target_soh_at_promo_start"], errors="coerce").fillna(0.0)
    out["current_soh_units"] = out["current_soh_at_model_run"]
    out["on_order_units"] = out["confirmed_inbound_units_before_promo_start"]
    out["minimum_launch_stock_units"] = out["floor_units_required_at_promo_start"]
    out["floor_units_required"] = out["floor_units_required_at_promo_start"]
    out["target_stock_day_one_units"] = out["target_soh_at_promo_start"]
    out["available_to_sell_before_floor"] = _store_int(
        (projected_on_hand - out["floor_units_required_at_promo_start"].astype("float64")).clip(lower=0.0)
    )
    effective = projected_on_hand.copy()
    out["effective_available_units"] = _store_int(effective)
    out["gap_to_day_one_target_units"] = out["raw_stock_gap_units"]
    out["projected_on_hand_at_promo_start"] = out["projected_soh_at_promo_start_before_order"]
    out["projected_stock_gap_units"] = out["raw_stock_gap_units"]
    out["prediction_date"] = out["model_run_date"]
    out["days_to_promo_start"] = out["days_until_promo_start"]
    unit_cost_series = _resolve_unit_cost_series(
        commercial_frame=frame,
        forecast_per_row_diagnostics=forecast_per_row_diagnostics,
    )

    # Contract order units are the governed model recommendation before
    # reconciliation audit trails are attached.
    contract_recommended = pd.to_numeric(out["recommended_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    out["raw_model_order_units"] = _store_int(contract_recommended)
    out["recommended_order_units"] = out["raw_model_order_units"]
    out["raw_model_order_value"] = (
        pd.to_numeric(out["raw_model_order_units"], errors="coerce").fillna(0.0) * unit_cost_series
    ).round(2).astype(float)

    confidence_fraction = _numeric_series(frame, ("final_confidence_score",))
    confidence_fraction = (
        confidence_fraction.fillna(CAPITAL_AT_RISK_DEFAULT_CONFIDENCE)
        .clip(lower=0.0, upper=1.0)
    )
    evidence_class_lower = (
        frame["demand_evidence_class"].astype(str).str.strip().str.lower()
    )

    # ---- New commercial fields (lead_up_demand, projected_promotional_units,
    #      discount, model_confidence_percent) — exposed to the operator
    #      in the OUTPUT contract.
    out["lead_up_demand_units"] = _store_int(bounded_expected_pre)
    out["projected_promotional_units"] = _store_int(
        pd.to_numeric(frame["predicted_units_total_promo"], errors="coerce")
        .fillna(0.0)
        .clip(lower=0.0)
    )
    out["discount_percent"] = _resolve_discount_percent_series(frame)
    out["model_confidence_percent"] = (
        (confidence_fraction * 100.0).round(0).clip(lower=0.0, upper=100.0).astype("int64")
    )
    stockout_signal = pd.to_numeric(frame["stockout_risk_flag"], errors="coerce").fillna(0).astype(int)
    stockout_operator_frame = _build_stockout_operator_frame(
        projected_on_hand=projected_on_hand,
        target_day_one=target_day_one,
        expected_first7_units=pd.to_numeric(frame["predicted_units_first_7_days_of_promo"], errors="coerce").fillna(0.0),
        bounded_expected_pre=bounded_expected_pre,
        lead_days=lead,
        confidence_fraction=confidence_fraction,
        stockout_flag=stockout_signal,
    )
    for column in stockout_operator_frame.columns:
        out[column] = stockout_operator_frame[column]

    # ---- Reasoning / trust ---------------------------------------------
    out["demand_evidence_class"] = frame["demand_evidence_class"].astype(str)
    out["confidence_band"] = frame["demand_confidence_band"].astype(str)
    out["historical_promo_response_summary"] = _compose_historical_response_summary(
        commercial_frame=frame,
        forecast_per_row_diagnostics=forecast_per_row_diagnostics,
    )
    historical_discount_frame = _resolve_historical_discount_frame(frame)
    for column in historical_discount_frame.columns:
        out[column] = historical_discount_frame[column]
    backtest_trust_frame = _build_backtest_trust_frame(
        frame=frame,
        summary=completed_backtest_summary,
    )
    for column in backtest_trust_frame.columns:
        out[column] = backtest_trust_frame[column]

    # ---- Risk / capital -------------------------------------------------
    cash_band = frame["estimated_cash_risk_band"].astype(str).str.upper()
    overstock = pd.to_numeric(frame["overstock_risk_flag"], errors="coerce").fillna(0).astype(int)
    stockout = stockout_signal
    leftover_units_raw = pd.to_numeric(
        frame["expected_leftover_units_end_of_promo"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    leftover_cost = (leftover_units_raw * unit_cost_series).round(2)
    out["stockout_risk_band"] = _stockout_risk_band(
        stockout_flag=stockout,
        target_day_one=target_day_one,
        effective=effective,
    )
    out["overstock_risk_band"] = _overstock_risk_band(
        overstock_flag=overstock,
        cash_band=cash_band,
    )
    out["estimated_leftover_units"] = _store_int(leftover_units_raw)
    out["estimated_leftover_cost_dollars"] = leftover_cost.astype(float)
    out["end_of_promo_residual_risk"] = out["overstock_risk_band"].astype(str)
    target_end_stock_units = _optional_numeric_series(frame, "feature_end_of_promo_target_units")
    target_end_stock_units = target_end_stock_units.where(
        target_end_stock_units.notna(),
        _numeric_series(frame, ("base_units_target",)),
    ).fillna(0.0).clip(lower=0.0)
    target_end_days_cover = _numeric_series(
        frame,
        ("feature_end_of_promo_target_days_cover",),
    ).clip(lower=0.0)
    estimated_end_stock_units = (
        projected_on_hand
        + pd.to_numeric(out["recommended_order_units"], errors="coerce").fillna(0.0)
        - expected_units_per_period
    ).clip(lower=0.0)
    month_end_cash_flag = _numeric_series(
        frame,
        ("feature_month_end_cash_runoff_pressure_flag",),
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    cashflow_runoff_status = pd.Series("standard_cashflow", index=frame.index, dtype="object")
    cashflow_runoff_status = cashflow_runoff_status.where(
        month_end_cash_flag.lt(1.0),
        "month_end_runoff_max_7d_cover",
    )
    trust_floor_status = pd.Series("trust_floor_met", index=frame.index, dtype="object")
    trust_floor_status = trust_floor_status.where(
        estimated_end_stock_units.ge(target_end_stock_units),
        "below_target_end_stock",
    )
    speculative_capital_units = _optional_numeric_series(
        frame,
        "feature_expected_leftover_above_trust_floor_units",
    )
    fallback_speculative_units = (estimated_end_stock_units - target_end_stock_units).clip(lower=0.0)
    speculative_capital_units = speculative_capital_units.where(
        speculative_capital_units.notna(),
        fallback_speculative_units,
    ).clip(lower=0.0)
    out["target_end_stock_units"] = target_end_stock_units.round(4).astype(float)
    out["target_end_days_cover"] = target_end_days_cover.round(4).astype(float)
    out["cashflow_runoff_status"] = cashflow_runoff_status
    out["trust_floor_status"] = trust_floor_status
    out["units_needed_for_trust_floor"] = _optional_first_numeric_series(
        frame,
        ("feature_units_needed_for_trust_floor", "units_needed_for_trust_floor"),
    ).round(4).astype(float)
    out["units_needed_for_high_demand_cover"] = _optional_first_numeric_series(
        frame,
        ("feature_units_needed_for_high_demand_cover", "units_needed_for_high_demand_cover"),
    ).round(4).astype(float)
    out["units_above_trust_target"] = _optional_first_numeric_series(
        frame,
        ("feature_units_above_trust_target", "units_above_trust_target"),
    ).round(4).astype(float)
    out["capital_tied_above_trust_target"] = _optional_first_numeric_series(
        frame,
        ("feature_capital_tied_above_trust_target", "capital_tied_above_trust_target"),
    ).round(2).astype(float)
    out["expected_gp_on_trust_floor_units"] = _optional_first_numeric_series(
        frame,
        ("feature_expected_gp_on_trust_floor_units", "expected_gp_on_trust_floor_units"),
    ).round(2).astype(float)
    out["expected_gp_on_speculative_units"] = _optional_first_numeric_series(
        frame,
        ("feature_expected_gp_on_speculative_units", "expected_gp_on_speculative_units"),
    ).round(2).astype(float)
    out["risk_adjusted_value_of_speculative_units"] = _optional_first_numeric_series(
        frame,
        (
            "feature_risk_adjusted_value_of_speculative_units",
            "risk_adjusted_value_of_speculative_units",
        ),
    ).round(2).astype(float)
    out["speculative_capital_above_floor_units"] = speculative_capital_units.round(4).astype(float)
    out["speculative_capital_above_floor_value"] = (
        speculative_capital_units * unit_cost_series
    ).round(2).astype(float)

    # ---- Capital at risk (risk-adjusted) + risk/reward ratio ------------
    # exposure = recommended_order_units * unit_cost (cash put down) OR
    # leftover_cost (cash that may be trapped) — whichever is larger.
    # risk_factor = (1 - confidence) * evidence_factor * overstock_factor
    # capital_at_risk = exposure * clip(risk_factor, MIN, MAX)
    recommended_units_float = pd.to_numeric(
        out["recommended_order_units"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    out["recommended_order_value"] = (recommended_units_float * unit_cost_series).round(2).astype(float)
    order_exposure_dollars = (recommended_units_float * unit_cost_series).clip(lower=0.0)
    exposure_dollars = pd.concat(
        [order_exposure_dollars, leftover_cost.astype(float).clip(lower=0.0)], axis=1
    ).max(axis=1)
    evidence_risk_factor = pd.Series(1.0, index=frame.index, dtype="float64")
    evidence_risk_factor = evidence_risk_factor.where(
        ~evidence_class_lower.isin(ORDER_EVIDENCE_SPARSE_CLASSES), 1.2
    )
    evidence_risk_factor = evidence_risk_factor.where(
        ~evidence_class_lower.isin(ORDER_EVIDENCE_NO_EVIDENCE_CLASSES), 1.5
    )
    overstock_band_upper = out["overstock_risk_band"].astype(str).str.upper()
    overstock_risk_factor = pd.Series(1.0, index=frame.index, dtype="float64")
    overstock_risk_factor = overstock_risk_factor.where(
        overstock_band_upper != "MEDIUM", 1.2
    )
    overstock_risk_factor = overstock_risk_factor.where(
        overstock_band_upper != "HIGH", 1.5
    )
    risk_factor = (
        (1.0 - confidence_fraction) * evidence_risk_factor * overstock_risk_factor
    ).clip(lower=CAPITAL_AT_RISK_MIN_FACTOR, upper=CAPITAL_AT_RISK_MAX_FACTOR)
    capital_at_risk_dollars = (exposure_dollars * risk_factor).round(2)
    out["capital_at_risk_adjusted_dollars"] = capital_at_risk_dollars.astype(float)

    # Reward proxy: projected promo unit value at unit_cost (sales-value
    # surrogate when GP is not in the operator path). Higher is better.
    projected_promo_units_float = pd.to_numeric(
        out["projected_promotional_units"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    expected_reward_dollars = (projected_promo_units_float * unit_cost_series).clip(lower=0.0)
    risk_reward_divisor = capital_at_risk_dollars.where(
        capital_at_risk_dollars >= CAPITAL_AT_RISK_FLOOR_DOLLARS,
        CAPITAL_AT_RISK_FLOOR_DOLLARS,
    )
    risk_reward_ratio = (expected_reward_dollars / risk_reward_divisor).round(2)
    out["retail_risk_reward_ratio"] = risk_reward_ratio.astype(float)

    # ---- Validation flags ----------------------------------------------
    out["review_flag"] = action.eq("REVIEW").astype(int)
    zero_reason, zero_supported = _resolve_zero_forecast_columns(
        commercial_frame=frame,
        forecast_per_row_diagnostics=forecast_per_row_diagnostics,
    )
    out["zero_forecast_reason_code"] = zero_reason
    out["zero_forecast_is_evidence_supported"] = zero_supported
    out["data_quality_flag"] = _compose_data_quality_flag(frame)
    action, normalized_quality = _normalize_action_data_quality_consistency(
        action=action,
        data_quality_flag=out["data_quality_flag"],
    )
    action, normalized_quality = _normalize_action_review_hold_consistency(
        action=action,
        data_quality_flag=normalized_quality,
        review_reason=frame.get(
            "review_reason",
            pd.Series([""] * len(frame.index), index=frame.index),
        ),
    )
    display_action = _compose_store_facing_action_label(
        action=action,
        publish_eligibility_reason=frame.get(
            "publish_eligibility_reason",
            pd.Series([""] * len(frame.index), index=frame.index),
        ),
    )
    out["recommended_action"] = display_action
    out["store_action"] = _compose_store_user_action_label(display_action)
    out["data_quality_flag"] = normalized_quality
    out["review_flag"] = display_action.isin({"REVIEW", "REVIEW_REQUIRED"}).astype(int)
    discount_review_diagnostics = _build_discount_review_diagnostic_frame(frame)
    out["low_nonzero_value_relief_delta"] = _optional_first_numeric_series(
        frame,
        (
            "low_nonzero_value_relief_delta",
            "low_nonzero_specialist_value_signal",
            "specialist_shadow_expected_incremental_value_delta",
            "expected_incremental_value_dollars_delta",
        ),
    ).fillna(0.0).round(2).astype(float)
    out["promo_allocated_units"] = _store_int(
        _numeric_series(frame, ("promo_allocated_units", "pl_allocation_qty", "pl_allocated")).clip(lower=0.0)
    )
    store_label_frame = _build_store_action_label_frame(
        store_frame=out,
        display_action=display_action,
        data_quality_flag=out["data_quality_flag"],
        discount_reason_code=discount_review_diagnostics["discount_data_quality_reason_code"],
        publish_eligibility_reason=frame.get(
            "publish_eligibility_reason",
            pd.Series([""] * len(frame.index), index=frame.index),
        ),
        review_reason=frame.get(
            "review_reason",
            pd.Series([""] * len(frame.index), index=frame.index),
        ),
    )
    for column_name in store_label_frame.columns:
        out[column_name] = store_label_frame[column_name]
    order_reconciliation_frame = _build_store_order_reconciliation_frame(
        store_frame=out,
    )
    for column_name in order_reconciliation_frame.columns:
        out[column_name] = order_reconciliation_frame[column_name]
    out = _apply_allocation_contract_final_orders(store_frame=out)
    out = sync_allocation_contract_aliases(out)
    out["recommended_order_value"] = out["final_store_order_value"]
    out["store_action_reason"] = out["order_reconciliation_reason"]
    out["discount_response_summary"] = _compose_discount_response_summary(
        historical=historical_discount_frame,
        recommended_units=out["recommended_order_units"],
    )

    # ---- Execution priority + timing -----------------------------------
    gap_units = pd.to_numeric(out["raw_stock_gap_units"], errors="coerce").fillna(0).astype(int)
    lead_days = pd.to_numeric(out["days_until_promo_start"], errors="coerce").fillna(0).astype(int)
    # Reason summary describes the risk-adjusted commercial exposure
    # (`capital_at_risk_adjusted_dollars`) rather than raw estimated
    # leftover cost, so the operator-visible sentence matches the dollar
    # figure on the same row of the per-promotion CSV.
    capital_at_risk = pd.to_numeric(
        out["capital_at_risk_adjusted_dollars"], errors="coerce"
    ).fillna(0.0)

    # Reason summary now derives its central commercial-driver clause from
    # local Stage 11 metrics rather than relying on upstream client_reason wording.
    out["model_reason_summary"] = _compose_model_reason_summary(
        frame,
        action=action,
        gap_units=gap_units,
        lead_days=lead_days,
        expected_total_promo=pd.to_numeric(out["expected_units_total_promo"], errors="coerce").fillna(0).astype(int),
        leftover_units=pd.to_numeric(out["estimated_leftover_units"], errors="coerce").fillna(0).astype(int),
        capital_at_risk=capital_at_risk,
        demand_evidence_class=out["demand_evidence_class"],
        confidence_band=out["confidence_band"],
    )
    out["execution_readiness_status"] = _compose_execution_readiness_status(display_action)
    out["operator_status"] = _compose_store_user_status_label(out["execution_readiness_status"])
    out["primary_review_reason"] = _compose_primary_review_reason(
        action=display_action,
        data_quality_flag=out["data_quality_flag"],
        model_reason_summary=out["model_reason_summary"],
        review_reason=frame.get(
            "review_reason",
            pd.Series([""] * len(frame.index), index=frame.index),
        ),
    )
    raw_decision_reason = frame.get("decision_reason")
    if raw_decision_reason is None:
        out["decision_reason"] = out["model_reason_summary"]
    else:
        raw_decision_reason = raw_decision_reason.astype(str).str.strip()
        out["decision_reason"] = raw_decision_reason.where(
            raw_decision_reason.ne(""),
            out["model_reason_summary"],
        )
    priority_band, buy_now, watch, do_not_buy, days_until_action = _compute_priority_band_and_flags(
        action=action,
        gap_units=gap_units,
        lead_days=lead_days,
    )
    out["priority_band"] = priority_band
    out["buy_now_flag"] = buy_now.astype(int)
    out["watch_flag"] = watch.astype(int)
    out["do_not_buy_flag"] = do_not_buy.astype(int)
    out["days_until_action"] = days_until_action.astype(int)
    out["order_timing_summary"] = priority_band.map(STORE_FACING_ORDER_TIMING_SUMMARIES).fillna(
        STORE_FACING_ORDER_TIMING_SUMMARIES["WATCH"]
    )
    out["priority_rank"] = _compute_priority_rank(
        priority_band=priority_band,
        gap_units=gap_units,
        capital_at_risk=capital_at_risk,
        lead_days=lead_days,
    )

    out["SOH_at_advice_time"] = out["current_soh_at_model_run"]
    out["on_order_at_advice_time"] = out["confirmed_inbound_units_before_promo_start"]
    out["projected_SOH_at_promo_start"] = out["projected_soh_at_promo_start_before_order"]
    out["target_SOH_at_promo_start"] = out["target_soh_at_promo_start"]
    out["weeks_of_cover_entering_promo"] = (
        pd.to_numeric(out["days_of_cover_to_promo_start"], errors="coerce").fillna(0.0) / 7.0
    ).round(2)

    sku_metric_map = None
    if sku_backtest_summary is not None and not sku_backtest_summary.empty:
        sku_metric_map = sku_backtest_summary.drop_duplicates(subset=["sku_number"]).set_index("sku_number")
    sku_lookup = out["sku_number"].astype(str)
    if sku_metric_map is None:
        out["SKU_MAE"] = pd.Series([pd.NA] * len(out.index), index=out.index, dtype="Float64")
        out["SKU_MSE"] = pd.Series([pd.NA] * len(out.index), index=out.index, dtype="Float64")
        out["SKU_bias"] = pd.Series(["NO_COMPARABLE_EVENTS"] * len(out.index), index=out.index, dtype="object")
    else:
        out["SKU_MAE"] = pd.to_numeric(sku_lookup.map(sku_metric_map["SKU_MAE"]), errors="coerce").round(2)
        out["SKU_MSE"] = pd.to_numeric(sku_lookup.map(sku_metric_map["SKU_MSE"]), errors="coerce").round(2)
        out["SKU_bias"] = sku_lookup.map(sku_metric_map["SKU_bias"]).fillna("NO_COMPARABLE_EVENTS").astype(str)

    clean_operator_fields = _build_store_facing_clean_operator_fields(out)
    for column_name in clean_operator_fields.columns:
        out[column_name] = clean_operator_fields[column_name]
    out["order_units"] = out["recommended_order_units"]
    priority_band, operator_action = reconcile_priority_and_operator_action(
        priority_band=out["priority_band"],
        operator_action=out["operator_action"],
        raw_stock_gap_units=out["raw_stock_gap_units"],
        recommended_order_units=out["recommended_order_units"],
        order_reason_code=out.get("order_reason_code", pd.Series("", index=out.index)),
    )
    out["priority_band"] = priority_band
    out["operator_action"] = operator_action
    out["audit_notes"] = out.apply(_derive_clean_audit_notes, axis=1)

    validation_started = time.perf_counter()
    validation_summary, validation_issues = validate_allocation_stock_contract_frame(out)
    log_allocation_contract_validation(validation_summary, started_at=validation_started)
    out.attrs["allocation_contract_validation_summary"] = validation_summary.to_dict()
    out.attrs["allocation_contract_validation_issue_count"] = int(len(validation_issues.index))

    _validate_store_facing_operator_contract(out)

    projected = out.loc[:, list(STORE_FACING_SCHEMA_COLUMNS)].copy()
    # Sort intentionally so first row in the file is the highest-priority action.
    projected = projected.sort_values(
        by=["priority_rank", "sku_number"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    return projected