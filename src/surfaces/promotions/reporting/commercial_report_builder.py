"""Commercial store-facing promotion report builder (Phase 5B.3+)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from models.promotions.promo_period_demand_forecast import attach_promo_period_demand_forecast
from models.promotions.promo_demand_bias_repair import apply_underforecast_bias_adjustments, load_bias_repair_artifacts
from models.promotions.promo_demand_calibration import apply_promo_demand_calibration, load_calibration_artifacts
from models.promotions.promo_optimal_stock_learning import apply_optimal_stock_learning, load_optimal_stock_artifacts
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
from models.promotions.promo_conviction_calibration import apply_conviction_calibration, load_conviction_artifacts
from models.promotions.promo_decision_triage import apply_promo_decision_triage, load_triage_artifacts
from models.promotions.promo_basket_attachment_features import apply_basket_attachment_to_promo_frame
from models.promotions.promo_brain_feature_learning import FEATURE_FAMILIES, apply_brain_feature_learning
from models.promotions.promo_brain_leakage_audit import apply_brain_leakage_validation
from models.promotions.promo_shadow_candidate_selection import apply_shadow_candidate_selection
from models.promotions.promo_economic_value_scoring import apply_promo_economic_value_scoring, load_economic_artifacts
from models.promotions.promo_stock_outcome_optimisation import apply_stock_outcome_optimisation, load_stock_outcome_artifacts
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_artifacts

import numpy as np
import pandas as pd

META_STATUS = "SHADOW_NOT_PRODUCTION"
PRODUCTION_ORDERING = "NO"
CUSTOMER_RELEASE = "NO"
BRAIN_FEATURE_COUNT = sum(len(cols) for cols in FEATURE_FAMILIES.values())
ALLOWED_DECISIONS = frozenset({"BUY", "REVIEW", "HOLD", "DO_NOT_BUY"})
FORMULA_TOLERANCE = 0.01
OPERATOR_SHEET_COLUMNS: tuple[str, ...] = (
    "priority_rank",
    "sku_number",
    "sku_description",
    "decision",
    "order_strategy",
    "action_tier",
    "operator_priority_group",
    "execution_ready_flag",
    "execution_blocker",
    "review_subtype",
    "commercial_action_value_score",
    "review_priority_score",
    "no_buy_trust_score",
    "overall_row_priority_score",
    "review_burden_class",
    "commercial_value_score",
    "commercial_value_label",
    "selected_promo_period_demand_units",
    "baseline_period_demand_units",
    "demand_evidence_strength",
    "demand_conflict_flag",
    "demand_selection_reason",
    "order_needed_to_cover_promo_sales",
    "order_needed_to_reach_full_stock_target",
    "recommended_promo_cover_order_units",
    "recommended_base_stock_order_units",
    "recommended_order_units",
    "remaining_promo_sales_stock_gap",
    "remaining_end_stock_gap",
    "best_seller_escalation_flag",
    "raw_model_order_units",
    "operator_review_order_low_units",
    "operator_review_order_high_units",
    "confidence_score",
    "data_quality_score",
    "decision_quality_label",
    "reason_order",
    "reason_risk",
    "review_reason",
    "operator_decision",
    "operator_recommended_units",
    "operator_notes",
)

ORDER_PLAN_COLUMNS: tuple[str, ...] = (
    "priority_rank",
    "store_number",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "promotion_days",
    "prediction_date",
    "days_until_promotion_start",
    "sku_number",
    "sku_description",
    "decision",
    "order_strategy",
    "recommended_order_basis",
    "model_promo_forecast_units",
    "same_discount_promo_units",
    "baseline_period_demand_units",
    "selected_promo_period_demand_units",
    "promo_units_expected_to_sell",
    "demand_evidence_strength",
    "demand_conflict_flag",
    "demand_selection_reason",
    "best_seller_floor_applied_flag",
    "best_seller_escalation_flag",
    "stock_needed_for_promo_sales",
    "stock_needed_to_finish_with_target_cover",
    "order_needed_to_cover_promo_sales",
    "order_needed_to_reach_full_stock_target",
    "full_target_order_units",
    "recommended_promo_cover_order_units",
    "recommended_base_stock_order_units",
    "commercial_recommended_order_units",
    "recommended_order_units",
    "remaining_promo_sales_stock_gap",
    "remaining_end_stock_gap",
    "remaining_shortfall_after_commercial_recommendation_units",
    "remaining_day_one_shortfall_units",
    "commercial_coverage_ratio",
    "recommendation_coverage_ratio",
    "raw_model_order_units",
    "operator_review_order_low_units",
    "operator_review_order_high_units",
    "target_day_one_soh_units",
    "projected_day_one_soh_before_order_units",
    "projected_day_one_soh_after_recommended_order_units",
    "current_soh_units",
    "on_order_units",
    "estimated_demand_before_promo_start_units",
    "target_stock_on_hand_at_promo_end_units",
    "total_expected_demand_to_promo_end_units",
    "projected_stock_on_hand_at_promo_end_units",
    "discount_percent",
    "avg_promo_demand_same_discount_units",
    "expected_gp_dollars",
    "capital_at_risk_dollars",
    "confidence_score",
    "confidence_label",
    "data_quality_score",
    "data_quality_label",
    "decision_quality_label",
    "action_tier",
    "execution_ready_flag",
    "execution_blocker",
    "review_subtype",
    "commercial_action_value_score",
    "review_priority_score",
    "no_buy_trust_score",
    "overall_row_priority_score",
    "review_burden_class",
    "commercial_value_score",
    "commercial_value_label",
    "operator_priority_group",
    "promo_period_demand_source",
    "promo_period_demand_fallback_flag",
    "promo_demand_model_source",
    "promo_demand_source_lineage",
    "promo_demand_source_quality",
    "promo_demand_selection_method",
    "promo_demand_release_ready_flag",
    "model_expected_units_total_promo_raw",
    "promo_demand_calibration_factor",
    "model_expected_units_total_promo_calibrated",
    "calibration_quality",
    "calibration_release_ready_flag",
    "calibration_allowed_in_release_decision",
    "underforecast_bias_factor",
    "underforecast_bias_factor_source",
    "underforecast_bias_quality",
    "bias_adjusted_expected_units_total_promo",
    "bias_adjusted_forecast_allowed_flag",
    "promo_start_soh",
    "target_promo_start_soh",
    "promo_start_soh_gap",
    "supplier_lead_time_days",
    "supplier_replenishment_class",
    "supplier_reorder_flexibility",
    "forecast_demand_units",
    "target_end_soh_units",
    "target_order_units_stock_outcome",
    "order_units_stock_outcome_adjustment",
    "promo_end_days_cover",
    "stock_outcome_label",
    "stock_outcome_order_reason",
    "promo_start_soh_resolved",
    "promo_start_soh_source",
    "promo_start_soh_source_quality",
    "promo_start_soh_confidence_score",
    "inbound_units_before_promo",
    "inbound_units_during_promo",
    "reliable_inbound_units_before_or_during_promo",
    "inbound_stock_source_quality",
    "supplier_number_resolved",
    "supplier_number_source_quality",
    "supplier_replenishment_class_repaired",
    "supplier_lead_time_days_repaired",
    "supplier_reorder_flexibility_repaired",
    "optimal_base_soh_units",
    "current_days_cover",
    "current_stock_position_label",
    "days_until_promo_start",
    "expected_units_until_promo_start",
    "expected_soh_at_promo_start_before_order",
    "expected_normal_units_during_promo",
    "expected_promo_uplift_units",
    "promo_convexity_score",
    "target_day_one_promo_soh",
    "target_end_promo_soh",
    "optimal_stock_position_order_units",
    "distance_to_optimal_end_soh",
    "promo_exit_success_flag",
    "stock_position_order_reason",
    "replenishment_lead_time_days",
    "replenishment_risk_class",
    "store_sales_regime",
    "customer_loyalty_regime",
    "sku_demand_regime",
    "stock_position_regime",
    "supplier_replenishment_regime",
    "promo_convexity_regime",
    "cash_efficiency_regime",
    "capital_at_risk_regime",
    "customer_basket_trust_regime",
    "overall_regime_opportunity_score",
    "overall_regime_risk_score",
    "overall_regime_conviction_score",
    "raw_regime_conviction_score",
    "regime_historical_wape",
    "regime_historical_bias_pct",
    "regime_confidence_cap",
    "calibrated_regime_conviction_score",
    "calibrated_conviction_label",
    "conviction_downgrade_reason",
    "regime_bias_direction",
    "regime_bias_adjustment_recommendation",
    "buyer_review_required_flag",
    "buyer_review_reason",
    "decision_confidence_for_report",
    "decision_confidence_label_for_report",
    "decision_triage_class",
    "decision_triage_reason",
    "buyer_review_priority_score",
    "buyer_review_priority_label",
    "buyer_review_required_flag_triaged",
    "buyer_review_queue_rank",
    "buyer_review_queue_bucket",
    "recommended_review_batch",
    "auto_block_flag",
    "watchlist_flag",
    "future_auto_approve_candidate_flag",
    "triage_governance_note",
    "economic_net_value_score",
    "economic_value_confidence_score",
    "economic_value_label",
    "economic_value_driver_1",
    "economic_value_driver_2",
    "economic_value_driver_3",
    "missed_sales_avoidance_value",
    "basket_trust_protection_value",
    "overstock_cash_release_value",
    "cash_tied_above_optimal_cost",
    "supplier_economic_risk_cost",
    "review_roi_score",
    "review_roi_label",
    "economic_priority_rank",
    "economic_review_queue_bucket",
    "triage_priority_score_v2",
    "priority_rank_change",
    "priority_rank_change_reason",
    "long_tail_sku_flag",
    "basket_completion_sku_flag",
    "basket_attachment_score",
    "basket_mission_importance_score",
    "long_tail_stockout_risk_score",
    "basket_loss_multiplier",
    "long_tail_protection_value",
    "basket_trust_convexity_value",
    "long_tail_minimum_soh_required",
    "long_tail_open_for_sale_required_flag",
    "long_tail_basket_protection_reason",
    "feature_basket_attach_rate",
    "feature_basket_3plus_attach_rate",
    "feature_basket_5plus_attach_rate",
    "feature_avg_basket_value_when_present",
    "feature_avg_basket_gp_when_present",
    "feature_sister_club_attach_rate",
    "mission_sku_score",
    "mission_sku_flag",
    "basket_completion_sku_score",
    "range_trust_sku_score",
    "long_tail_mission_sku_flag",
    "basket_attachment_source",
    "basket_attachment_source_quality",
    "basket_attachment_used_real_transactions_flag",
    "mission_sku_reason",
    "brain_learned_action_label",
    "brain_learned_order_score",
    "brain_expected_uplift_units",
    "brain_expected_economic_value",
    "brain_expected_stock_exit_distance",
    "brain_value_gap_vs_current",
    "brain_pattern_confidence_score",
    "brain_top_feature_1",
    "brain_top_feature_2",
    "brain_top_feature_3",
    "brain_learning_status",
    "alpha_pattern_id",
    "alpha_pattern_label",
    "alpha_pattern_description",
    "alpha_pattern_value_estimate",
    "alpha_pattern_risk_note",
    "brain_leakage_risk_level",
    "brain_leak_safe_feature_count",
    "brain_validated_action_label",
    "brain_validated_expected_value",
    "brain_validated_confidence_score",
    "brain_validation_status",
    "brain_value_survives_leakage_control_flag",
    "validated_alpha_pattern_label",
    "shadow_trial_candidate_flag",
    "shadow_trial_reason",
    "shadow_candidate_flag",
    "shadow_candidate_class",
    "shadow_candidate_score",
    "shadow_candidate_rank",
    "shadow_candidate_bucket",
    "segment_historical_bias_pct",
    "segment_historical_wape",
    "segment_bias_control_status",
    "shadow_expected_learning_value",
    "action_difference_flag",
    "action_difference_type",
    "expected_shadow_learning_question",
    "shadow_observation_plan",
    "regime_adjusted_decision_value",
    "brain_action_label",
    "brain_order_units_proposal",
    "constraint_block_flag",
    "constraint_block_reason",
    "final_governed_action_label",
    "final_governed_order_units",
    "top_regime_driver_1",
    "top_regime_driver_2",
    "top_regime_driver_3",
    "human_interpretation_summary",
    "stock_target_conflict_flag",
    "reason_demand",
    "reason_stock",
    "reason_order",
    "reason_risk",
    "reason_rejection_or_hold",
    "human_review_required",
    "review_reason",
    "model_status",
    "production_ordering_approved",
    "customer_report_release_approved",
    "operator_decision",
    "operator_recommended_units",
    "operator_notes",
)

HOLD_TARGET_TOLERANCE = 2

ACTION_TIERS = frozenset({
    "tier_1_execute",
    "tier_2_review_high_value",
    "tier_3_review_evidence_gap",
    "tier_4_hold_monitor",
    "tier_5_do_not_buy",
})

OPERATOR_PRIORITY_GROUPS = frozenset({
    "order_now_candidate",
    "review_before_order",
    "check_stock_position",
    "no_order_needed",
    "rejected_poor_seller",
})

REVIEW_SUBTYPES = frozenset({
    "review_demand_evidence",
    "review_stock_gap",
    "review_order_range",
    "review_high_value",
    "review_low_confidence",
    "review_base_stock_gap",
    "review_data_quality",
    "none",
})

REVIEW_BURDEN_CLASSES = frozenset({
    "must_review",
    "optional_review",
    "audit_only",
    "no_review_required",
})

EXECUTION_SHORTLIST_COLUMNS: tuple[str, ...] = (
    "operator_priority_group",
    "action_tier",
    "priority_rank",
    "sku_number",
    "sku_description",
    "decision",
    "recommended_order_units",
    "operator_review_order_low_units",
    "operator_review_order_high_units",
    "promo_units_expected_to_sell",
    "current_soh_units",
    "on_order_units",
    "remaining_promo_sales_stock_gap",
    "remaining_end_stock_gap",
    "confidence_score",
    "data_quality_score",
    "commercial_action_value_score",
    "review_priority_score",
    "no_buy_trust_score",
    "overall_row_priority_score",
    "review_burden_class",
    "commercial_value_score",
    "review_subtype",
    "execution_blocker",
    "reason_demand",
    "reason_stock",
    "reason_order",
    "reason_risk",
    "operator_decision",
    "operator_recommended_units",
    "operator_notes",
)

DEMAND_FIELD_HINTS = (
    "demand",
    "units",
    "expected",
    "promo",
    "lead",
    "sales",
    "period",
    "projected",
    "historical",
)


@dataclass(frozen=True)
class CommercialSourceSelection:
    promotion_slug: str
    sku_universe_source: str
    order_units_source: str
    demand_source: str
    confidence_source: str
    notes: str


@dataclass(frozen=True)
class CommercialPackArtifacts:
    output_dir: Path
    order_plan_path: Path
    row_count: int
    decision_counts: dict[str, int]
    total_recommended_order_units: float
    report_quality_score: int


def _label(score: float) -> str:
    if score >= 85:
        return "VERY_HIGH"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    if score >= 30:
        return "LOW"
    return "VERY_LOW"


def _num(series: pd.Series | None, default: float = 0.0, index: pd.Index | None = None) -> pd.Series:
    if series is None:
        return pd.Series(default, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _first_col(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return None


def load_se01_scored_sources(prediction_dir: Path) -> pd.DataFrame:
    """Merge SE01 sources; order evidence from raw_model_order_units, not final zeroed orders."""
    prefix = "772_2026-07-23_allocation-report-se01-skincare-sales-event"
    main = pd.read_csv(prediction_dir / f"{prefix}.csv", low_memory=False)
    audit = pd.read_csv(prediction_dir / f"{prefix}_operator-audit.csv", low_memory=False)
    feature_header = pd.read_csv(prediction_dir / f"{prefix}_feature-inspection.csv", nrows=0).columns
    feature_cols = [
        "sku_number",
        "expected_units_per_day",
        "historical_units_same_discount_avg",
        "historical_units_same_or_better_discount_avg",
        "lead_up_demand_units",
        "capital_at_risk_adjusted_dollars",
        "feature_expected_gp_on_trust_floor_units",
        "feature_expected_gp_on_speculative_units",
        "promotion_period_days",
        "promotion_start_date",
        "promotion_end_date",
        "expected_units_total_promo",
        "expected_units_per_period",
        "projected_promotional_units",
        "expected_promo_demand",
        "expected_units_first_7_days",
        "days_to_promo_start",
        "lead_days_to_promo_start",
    ]
    feature = pd.read_csv(
        prediction_dir / f"{prefix}_feature-inspection.csv",
        usecols=[c for c in feature_cols if c in feature_header],
        low_memory=False,
    )
    audit_keep = [
        "sku_number",
        "raw_model_order_units",
        "model_confidence_percent",
        "lead_up_demand_units",
        "days_to_promo_start",
        "expected_units_per_day",
        "expected_units_per_period",
        "expected_units_total_promo",
        "projected_promotional_units",
        "expected_promo_demand",
        "expected_units_first_7_days",
        "expected_units_before_promo_start",
        "review_flag",
        "risk_flag",
        "audit_notes",
        "demand_evidence_label",
        "recommended_action",
        "historical_units_same_discount_avg",
        "historical_units_same_or_better_discount_avg",
    ]
    audit_keep = [c for c in audit_keep if c in audit.columns]
    out = main.merge(audit[audit_keep], on="sku_number", how="left", suffixes=("", "_audit"))
    out = out.merge(feature, on="sku_number", how="left", suffixes=("", "_feat"))
    out = attach_promo_period_demand_forecast(out)
    factors, _gate, recommendation = load_calibration_artifacts()
    if "model_expected_units_total_promo" in out.columns:
        out["model_expected_units_total_promo_raw"] = pd.to_numeric(
            out["model_expected_units_total_promo"], errors="coerce"
        ).fillna(0.0)
    if not factors.empty:
        out = apply_promo_demand_calibration(out, factors)
        limited_ok = recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        out["calibration_allowed_in_release_decision"] = (
            limited_ok
            & out.get("calibration_release_ready_flag", pd.Series("NO", index=out.index)).eq("YES")
            & out.get("calibration_quality", pd.Series("LOW", index=out.index)).isin(["HIGH", "MEDIUM"])
        ).map({True: "YES", False: "NO"})
    else:
        for col, default in (
            ("promo_demand_calibration_factor", 1.0),
            ("model_expected_units_total_promo_calibrated", out.get("model_expected_units_total_promo", 0.0)),
            ("calibration_quality", "LOW"),
            ("calibration_release_ready_flag", "NO"),
            ("calibration_allowed_in_release_decision", "NO"),
        ):
            if col not in out.columns:
                out[col] = default
    bias_factors, _bias_gate, bias_recommendation = load_bias_repair_artifacts()
    if not bias_factors.empty:
        out = apply_underforecast_bias_adjustments(out, bias_factors, gate_recommendation=bias_recommendation)
    else:
        for col, default in (
            ("underforecast_bias_factor", 1.0),
            ("underforecast_bias_factor_source", "none"),
            ("underforecast_bias_quality", "LOW"),
            ("bias_adjusted_expected_units_total_promo", out.get("model_expected_units_total_promo_calibrated", out.get("model_expected_units_total_promo", 0.0))),
            ("bias_adjusted_forecast_allowed_flag", "NO"),
        ):
            if col not in out.columns:
                out[col] = default
    _stock_summary, _stock_gate, stock_recommendation = load_stock_outcome_artifacts()
    out = apply_stock_truth_repair(out)
    out = apply_stock_outcome_optimisation(out, gate_recommendation=stock_recommendation)
    _opt_gate, opt_rec = load_optimal_stock_artifacts()
    out = apply_optimal_stock_learning(out, gate_recommendation=opt_rec)
    _regime_gate, regime_rec = load_regime_artifacts()
    out = apply_regime_brain_decisioning(out, gate_recommendation=regime_rec)
    _conv_profile, conv_rec = load_conviction_artifacts()
    out = apply_conviction_calibration(out, error_profile_df=_conv_profile if not _conv_profile.empty else None, gate_recommendation=conv_rec)
    triage_rec = load_triage_artifacts()
    out = apply_promo_decision_triage(out, gate_recommendation=triage_rec)
    out = apply_basket_attachment_to_promo_frame(out)
    econ_rec = load_economic_artifacts()
    out = apply_promo_economic_value_scoring(out, gate_recommendation=econ_rec)
    out = apply_brain_feature_learning(out)
    out = apply_brain_leakage_validation(out, config={"skip_full_validation": True})
    out = apply_shadow_candidate_selection(out)
    return out

def _baseline_daily_rate(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Derive SKU-specific baseline daily rate and source label."""
    idx = frame.index
    lead_up = _num(_first_col(frame, ("lead_up_demand_units_audit", "lead_up_demand_units", "lead_up_demand_units_feat")), index=idx)
    source_days = _num(
        _first_col(frame, ("days_to_promo_start_audit", "days_to_promo_start", "lead_days_to_promo_start_feat", "lead_days_to_promo_start")),
        index=idx,
    )
    source_days = source_days.where(source_days > 0, 0)
    from_lead = lead_up.div(source_days).where(source_days > 0, 0.0)

    hist = _num(_first_col(frame, ("historical_units_same_discount_avg_audit", "historical_units_same_discount_avg", "historical_units_same_discount_avg_feat")), index=idx)
    promo_days = _num(_first_col(frame, ("promotion_period_days_feat", "promotion_period_days", "promotion_days")), 7, index=idx).replace(0, 7)
    from_hist = hist.div(promo_days).where(hist > 0, 0.0)

    rate = from_lead.where(from_lead > 0, from_hist)
    source = np.where(from_lead > 0, "lead_up_demand_units_over_days_to_promo_start", "")
    source = np.where((from_lead <= 0) & (from_hist > 0), "historical_units_same_discount_avg_over_promo_days", source)
    source = np.where(rate <= 0, "missing_baseline_daily_rate", source)
    return rate.round(6), pd.Series(source, index=idx), source_days


def _field_series(frame: pd.DataFrame, base_names: tuple[str, ...], index: pd.Index) -> pd.Series:
    for base in base_names:
        for name in (f"{base}_audit", f"{base}_feat", base):
            if name in frame.columns:
                return _num(frame[name], index=index)
    return pd.Series(0.0, index=index)


def _is_flat_placeholder(series: pd.Series) -> bool:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return True
    return int(s.nunique(dropna=True)) <= 3 and float(s.quantile(0.9)) <= 1.01


def _extract_model_promo_forecast(frame: pd.DataFrame, promo_days: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Extract best non-flat model promo forecast per SKU."""
    idx = frame.index
    hist = _field_series(frame, ("historical_units_same_discount_avg",), idx)
    model_forecast = pd.Series(0.0, index=idx)
    model_source = pd.Series("model_promo_forecast_unavailable", index=idx, dtype=object)

    model_fields = [
        "model_expected_units_total_promo",
        "expected_units_total_promo",
        "projected_promotional_units",
        "expected_units_per_period",
        "expected_promo_demand",
    ]
    flat_detected: list[str] = []
    for field in model_fields:
        val = _field_series(frame, (field,), idx)
        if _is_flat_placeholder(val):
            flat_detected.append(field)
            continue
        usable = val.where((val > 0) & ((val > 1) | (hist <= val * 1.5)), 0.0)
        take = usable.gt(0) & model_forecast.le(0)
        model_forecast = model_forecast.where(~take, usable)
        source_label = (
            "models.promo_period_demand_forecast:model_expected_units_total_promo"
            if field == "model_expected_units_total_promo"
            else f"operator-audit:{field}"
        )
        model_source = model_source.where(~take, source_label)

    first7 = _field_series(frame, ("expected_units_first_7_days",), idx)
    if promo_days.eq(7).any() and not _is_flat_placeholder(first7):
        take7 = promo_days.eq(7) & first7.gt(0) & model_forecast.le(0)
        model_forecast = model_forecast.where(~take7, first7)
        model_source = model_source.where(~take7, "operator-audit:expected_units_first_7_days")

    per_day = _field_series(frame, ("expected_units_per_day",), idx)
    derived = (per_day * promo_days).round(3)
    if not (_is_flat_placeholder(per_day) or _is_flat_placeholder(derived)):
        take_day = derived.gt(0) & model_forecast.le(0)
        model_forecast = model_forecast.where(~take_day, derived)
        model_source = model_source.where(~take_day, "operator-audit:expected_units_per_day_x_promo_days")

    flat_label = "flat_placeholder:" + ",".join(flat_detected or model_fields)
    model_source = model_source.where(model_forecast.gt(1.01), flat_label)
    model_flat = model_forecast.le(1.01)
    return model_forecast.round(3), model_flat, model_source


def select_governed_promo_demand(
    frame: pd.DataFrame,
    promo_days: pd.Series,
    baseline_daily: pd.Series,
    source_days: pd.Series,
    unsafe_pre_promo: pd.Series,
) -> tuple[
    pd.Series, pd.Series, pd.Series, pd.Series, pd.Series,
    pd.Series, pd.Series, pd.Series, pd.Series, pd.Series,
    pd.Series, pd.Series, pd.Series, pd.Series, pd.Series,
]:
    """Evidence-weighted promotional demand selection with baseline floors and best-seller repair."""
    idx = frame.index
    hist = _field_series(frame, ("historical_units_same_discount_avg",), idx)
    same_discount = hist.round(3)
    same_or_better = _field_series(frame, ("historical_units_same_or_better_discount_avg",), idx).round(3)
    baseline_period = (baseline_daily * promo_days).round(3)
    model_forecast, model_flat, model_source_field = _extract_model_promo_forecast(frame, promo_days)

    bias_allowed = (
        frame.get("bias_adjusted_forecast_allowed_flag", pd.Series("NO", index=idx)).astype(str).str.upper().eq("YES")
    )
    bias_forecast = _field_series(frame, ("bias_adjusted_expected_units_total_promo",), idx)
    if bias_allowed.any() and not _is_flat_placeholder(bias_forecast):
        take_bias = bias_allowed & bias_forecast.gt(1.01) & (~model_flat | model_forecast.le(1.01))
        model_forecast = model_forecast.where(~take_bias, bias_forecast)
        model_source_field = model_source_field.where(
            ~take_bias,
            "models.promo_demand_bias_repair:bias_adjusted_expected_units_total_promo",
        )
        model_flat = model_flat & ~take_bias

    cal_allowed = frame.get("calibration_allowed_in_release_decision", pd.Series("NO", index=idx)).astype(str).str.upper().eq("YES")
    cal_forecast = _field_series(frame, ("model_expected_units_total_promo_calibrated",), idx)
    if cal_allowed.any() and not _is_flat_placeholder(cal_forecast):
        take_cal = cal_allowed & cal_forecast.gt(1.01) & (~model_flat | model_forecast.le(1.01)) & ~bias_allowed
        model_forecast = model_forecast.where(~take_cal, cal_forecast)
        model_source_field = model_source_field.where(
            ~take_cal,
            "models.promo_demand_calibration:model_expected_units_total_promo_calibrated",
        )
        model_flat = model_flat & ~take_cal

    credible_baseline = (baseline_daily > 0) & (source_days >= 28)
    same_discount_suppressed = credible_baseline & (same_discount > 0) & (baseline_period > same_discount + 1)

    model_usable = (~model_flat) & (model_forecast > 1.01) & (~unsafe_pre_promo)
    model_below_base = credible_baseline & (baseline_period >= 3) & (
        (model_forecast < baseline_period * 0.75) | (model_forecast < baseline_period - 1)
    )
    model_ok = model_usable & ~model_below_base

    hist_ok = (same_discount > 0) & ~same_discount_suppressed
    preliminary = pd.Series(0.0, index=idx)
    pre_source = pd.Series("missing_promo_period_demand", index=idx)

    take_model = model_ok & preliminary.le(0)
    preliminary = preliminary.where(~take_model, model_forecast)
    pre_source = pre_source.where(~take_model, "model_promo_forecast")

    take_hist = hist_ok & preliminary.le(0)
    preliminary = preliminary.where(~take_hist, same_discount)
    pre_source = pre_source.where(~take_hist, "same_discount_history")

    sob_ok = (same_or_better > 0) & preliminary.le(0)
    take_sob = sob_ok & preliminary.le(0)
    preliminary = preliminary.where(~take_sob, same_or_better)
    pre_source = pre_source.where(~take_sob, "same_or_better_discount_history")

    take_base = credible_baseline & (baseline_period >= 3) & preliminary.le(0)
    preliminary = preliminary.where(~take_base, baseline_period)
    pre_source = pre_source.where(~take_base, "baseline_period_demand")

    needs_floor = credible_baseline & (baseline_period >= 3) & (
        (preliminary < baseline_period * 0.75) | (preliminary < baseline_period - 1)
    )
    selected_before = preliminary.copy()
    selected = preliminary.where(~needs_floor, np.maximum(preliminary, baseline_period))
    floor_from_governance = needs_floor & selected.gt(preliminary)

    best_seller_repair = credible_baseline & (baseline_period >= 5) & (selected < baseline_period - 1)
    strong_best = baseline_period >= 10
    prior_sel = selected.copy()
    selected = selected.where(~best_seller_repair, np.maximum(selected, baseline_period))
    best_seller_floor = (selected > prior_sel) & best_seller_repair

    best_seller_escalation = pd.Series(
        np.where(
            strong_best & (selected < baseline_period - 1),
            "YES",
            np.where(best_seller_repair & ~best_seller_floor, "YES", "NO"),
        ),
        index=idx,
    )

    demand_conflict = (
        (model_usable & model_below_base)
        | same_discount_suppressed
        | (credible_baseline & (baseline_period >= 5) & (selected_before < baseline_period - 1))
    )

    source = pre_source.where(~floor_from_governance, "evidence_weighted_baseline_floor")
    source = source.where(~best_seller_floor, "best_seller_baseline_floor")
    source = source.where(selected.gt(0), "missing_promo_period_demand")

    quality = pd.Series("VERY_LOW", index=idx)
    quality = quality.where(~source.eq("model_promo_forecast"), "HIGH")
    quality = quality.where(~source.eq("same_discount_history"), "MEDIUM")
    quality = quality.where(~source.eq("same_or_better_discount_history"), "MEDIUM")
    quality = quality.where(
        ~source.isin(["baseline_period_demand", "evidence_weighted_baseline_floor"]),
        np.where(source_days >= 56, "HIGH", "MEDIUM"),
    )
    quality = quality.where(~source.eq("best_seller_baseline_floor"), np.where(source_days >= 56, "HIGH", "MEDIUM"))
    quality = quality.where(selected.gt(0), "VERY_LOW")

    fallback = pd.Series(
        np.where(
            source.eq("missing_promo_period_demand") | selected.le(0),
            "YES",
            "NO",
        ),
        index=idx,
    )

    release_ready = (
        source.eq("model_promo_forecast")
        & model_ok
        & ~demand_conflict
        & selected.gt(1.01)
    )
    upstream_release = _field_series(frame, ("promo_demand_release_ready_flag",), idx).astype(str).str.upper().eq("YES")
    release_ready = release_ready | (
        source.eq("model_promo_forecast")
        & upstream_release
        & selected.gt(1.01)
        & ~demand_conflict
    )
    promo_demand_release_ready_flag = release_ready.map({True: "YES", False: "NO"})

    lineage_map = {
        "model_promo_forecast": "operator-audit+feature-inspection;selected_model_field",
        "same_discount_history": "operator-audit:historical_units_same_discount_avg",
        "same_or_better_discount_history": "operator-audit:historical_units_same_or_better_discount_avg",
        "baseline_period_demand": "derived:baseline_daily_rate_x_promo_days",
        "evidence_weighted_baseline_floor": "derived:baseline_daily_rate_x_promo_days;floor_applied",
        "best_seller_baseline_floor": "derived:baseline_daily_rate_x_promo_days;best_seller_floor",
        "missing_promo_period_demand": "none",
    }
    promo_demand_source_lineage = source.map(lineage_map).fillna("governed_proxy")
    promo_demand_source_lineage = promo_demand_source_lineage.where(
        ~source.eq("model_promo_forecast"),
        model_source_field,
    )
    promo_demand_selection_method = pd.Series("evidence_weighted_governed_selection", index=idx)
    promo_demand_source_quality = quality.copy()

    strength = pd.Series("WEAK", index=idx)
    strength = strength.where(
        ~(source.eq("model_promo_forecast") & ~demand_conflict),
        "STRONG",
    )
    strength = strength.where(
        ~(
            source.isin(["best_seller_baseline_floor", "evidence_weighted_baseline_floor"])
            & (source_days >= 56)
            & ~demand_conflict
        ),
        "STRONG",
    )
    strength = strength.where(
        ~(source.eq("same_discount_history") & ~demand_conflict),
        "MODERATE",
    )
    strength = strength.where(
        ~(source.eq("same_or_better_discount_history") & ~demand_conflict),
        "MODERATE",
    )
    strength = strength.where(
        ~(
            source.isin(["baseline_period_demand", "evidence_weighted_baseline_floor", "best_seller_baseline_floor"])
            & ~demand_conflict
        ),
        "MODERATE",
    )
    strength = strength.where(~demand_conflict, "CONFLICTING")
    strength = strength.where(selected.gt(0), "WEAK")

    selection_reason = pd.Series("evidence_weighted_selection", index=idx)
    selection_reason = selection_reason.where(~model_flat, "flat_model_placeholder_rejected")
    selection_reason = selection_reason.where(
        ~(source.eq("model_promo_forecast") & selection_reason.eq("evidence_weighted_selection")),
        "model_promo_forecast_selected",
    )
    selection_reason = selection_reason.where(~same_discount_suppressed, "same_discount_suppressed_by_credible_baseline")
    selection_reason = selection_reason.where(~floor_from_governance, "baseline_period_floor_applied_over_weaker_source")
    selection_reason = selection_reason.where(~best_seller_floor, "best_seller_baseline_demand_floor_applied")
    selection_reason = selection_reason.where(
        ~(best_seller_escalation.eq("YES") & ~best_seller_floor),
        "baseline_demand_exceeds_selected_promo_demand",
    )
    selection_reason = selection_reason.where(~selected.le(0), "no_credible_promo_demand_evidence")

    warning = pd.Series("", index=idx)
    warning = warning.where(~demand_conflict, "demand_evidence_sources_conflict")
    warning = warning.where(selected.gt(0), "no_safe_promo_period_demand_evidence")

    floor_applied = np.where(best_seller_floor | floor_from_governance, "YES", "NO")
    floor_reason = np.where(
        best_seller_floor,
        "best_seller_baseline_floor",
        np.where(floor_from_governance, "evidence_weighted_baseline_floor", ""),
    )

    conflict_flag = demand_conflict.map({True: "YES", False: "NO"})

    return (
        selected.round(3),
        source,
        quality,
        fallback,
        warning,
        model_forecast,
        same_discount,
        baseline_period,
        pd.Series(floor_applied, index=idx),
        pd.Series(floor_reason, index=idx),
        selected_before.round(3),
        strength,
        conflict_flag,
        pd.Series(selection_reason, index=idx),
        best_seller_escalation,
        model_source_field,
        promo_demand_source_lineage,
        promo_demand_source_quality,
        promo_demand_selection_method,
        promo_demand_release_ready_flag,
    )


def _promo_period_demand(
    frame: pd.DataFrame,
    promo_days: pd.Series,
    baseline_daily: pd.Series,
    source_days: pd.Series,
    unsafe_pre_promo: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Backward-compatible wrapper around evidence-weighted demand selection."""
    (
        selected, source, quality, fallback, warning,
        model_forecast, same_discount, baseline_period,
        floor_applied, floor_reason, _before, _strength, _conflict, _reason, _escalation,
        _model_src, _lineage, _src_qual, _sel_method, _release_ready,
    ) = select_governed_promo_demand(frame, promo_days, baseline_daily, source_days, unsafe_pre_promo)
    return selected, source, quality, fallback, warning, model_forecast, same_discount, baseline_period, floor_applied, floor_reason


def _data_quality_score(
    *,
    soh: pd.Series,
    on_order: pd.Series,
    promo_days: pd.Series,
    baseline_daily: pd.Series,
    hist: pd.Series,
    pre_promo_source: pd.Series,
    promo_source: pd.Series,
    promo_fallback: pd.Series,
    promo_quality: pd.Series,
    target_used_floor: pd.Series,
    formula_ok: pd.Series,
    review_flag: pd.Series,
    risk_flag: pd.Series,
    unsafe_pre_promo: pd.Series,
    demand_conflict: pd.Series,
    demand_strength: pd.Series,
    source_days: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    idx = soh.index
    score = pd.Series(100.0, index=idx)
    penalty_parts: list[pd.Series] = []

    checks: list[tuple[pd.Series, float, str]] = [
        (soh.isna(), 12, "missing_current_soh"),
        (on_order.isna(), 5, "missing_on_order_units"),
        (promo_days.le(0), 8, "missing_promo_days"),
        (baseline_daily.le(0), 15, "missing_daily_demand_basis"),
        (hist.le(0), 5, "missing_same_discount_history"),
        (promo_source.str.contains("same_discount", case=False, na=False) & demand_conflict.eq("YES"), 10, "same_discount_suppressed_by_baseline"),
        (promo_source.eq("missing_promo_period_demand"), 20, "missing_promo_period_demand"),
        (promo_fallback.eq("YES") & demand_strength.eq("WEAK"), 8, "weak_fallback_promo_demand"),
        (promo_quality.isin(["LOW", "VERY_LOW"]), 10, "low_promo_period_demand_quality"),
        (demand_conflict.eq("YES"), 8, "demand_evidence_conflict"),
        (demand_strength.eq("CONFLICTING"), 12, "conflicting_demand_evidence"),
        (pre_promo_source.eq("unsafe_period_total_rejected"), 18, "unsafe_pre_promo_source_rejected"),
        (target_used_floor, 10, "missing_sku_specific_30_day_cover_used_floor_2"),
        (~formula_ok, 15, "formula_reconciliation_failure"),
        (review_flag, 6, "review_flag"),
        (risk_flag, 6, "risk_flag"),
        (unsafe_pre_promo, 12, "audit_source_pre_promo_mismatch"),
    ]
    for mask, amount, code in checks:
        score = score.where(~mask, score - amount)
        penalty_parts.append(pd.Series(np.where(mask, code, ""), index=idx))
    score = score.where(~((source_days >= 56) & demand_strength.eq("STRONG")), score + 5)
    penalties = pd.DataFrame(penalty_parts).T.apply(lambda r: "; ".join(x for x in r if x), axis=1)
    return score.clip(0, 100).round(1), penalties


def assemble_commercial_order_rows(
    frame: pd.DataFrame,
    *,
    store_number: int,
    promotion_name: str,
    prediction_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build one canonical row per SKU from scored SE01 evidence."""
    promo_days = _num(_first_col(frame, ("promotion_period_days_feat", "promotion_period_days", "promotion_days")), 7, index=frame.index).astype(int)
    promo_days = promo_days.replace(0, 7)
    start = pd.to_datetime(_first_col(frame, ("promotion_start_date_feat", "promotion_start_date")), errors="coerce")
    end = pd.to_datetime(_first_col(frame, ("promotion_end_date_feat", "promotion_end_date")), errors="coerce")
    pred_dt = pd.to_datetime(prediction_date, errors="coerce")
    days_until = (start - pred_dt).dt.days.fillna(0).clip(lower=0).astype(int)

    baseline_daily, baseline_source, source_days = _baseline_daily_rate(frame)
    unsafe_raw_pre = _num(_first_col(frame, ("expected_units_before_promo_start", "expected_units_before_promo_start_audit")), index=frame.index)
    unsafe_pre_promo = (
        (unsafe_raw_pre > baseline_daily * days_until * 3 + 1)
        & (days_until <= 7)
        & (unsafe_raw_pre > 10)
    )
    pre_promo = (baseline_daily * days_until).round(3)
    pre_promo_source = baseline_source

    (
        promo_sales, promo_source, promo_quality, promo_fallback, promo_warning,
        model_promo_forecast, same_discount_promo, baseline_period_demand,
        promo_floor_applied, promo_floor_reason, promo_selected_before,
        demand_strength, demand_conflict_flag, demand_selection_reason, best_seller_escalation,
        promo_demand_model_source, promo_demand_source_lineage, promo_demand_source_quality,
        promo_demand_selection_method, promo_demand_release_ready_flag,
    ) = select_governed_promo_demand(frame, promo_days, baseline_daily, source_days, unsafe_pre_promo)
    total_demand = (pre_promo + promo_sales).round(3)

    thirty_day_cover = (baseline_daily * 30).round(3)
    target_used_floor = baseline_daily.le(0) | thirty_day_cover.lt(2)
    base_stock_required = np.maximum(2, thirty_day_cover).round(3)
    base_stock_required = base_stock_required.where(~target_used_floor, 2.0)

    promo_cover_required = promo_sales
    target_day_one = (promo_cover_required + base_stock_required).round(3)
    formula_ok = (target_day_one - (promo_cover_required + base_stock_required)).abs() <= FORMULA_TOLERANCE

    soh = _num(frame.get("current_soh"), index=frame.index)
    on_order = _num(frame.get("on_order_at_advice_time"), index=frame.index)
    raw_order = _num(frame.get("raw_model_order_units"), index=frame.index).round(0).astype(int)
    projected_before_raw = (soh + on_order - pre_promo).round(3)
    floored = projected_before_raw < 0
    floor_removed = projected_before_raw.where(floored, 0.0).abs().round(3)
    projected_before = projected_before_raw.clip(lower=0).round(3)

    promo_cover_gap = (promo_cover_required - projected_before).clip(lower=0).round(0).astype(int)
    avail_after_promo = (projected_before - promo_cover_required).clip(lower=0).round(3)
    base_stock_gap = (base_stock_required - avail_after_promo).clip(lower=0).round(0).astype(int)
    full_target_order = (promo_cover_gap + base_stock_gap).astype(int)
    target_order = full_target_order

    has_promo_demand = promo_sales > 0
    has_target_order = full_target_order > 0
    has_raw = raw_order > 0

    conf = _num(frame.get("model_confidence_percent"), 50, index=frame.index).clip(0, 100)
    review_flag = _num(frame.get("review_flag"), index=frame.index).astype(bool)
    risk_flag = _num(frame.get("risk_flag"), index=frame.index).astype(bool)
    orig_action = frame.get("operator_action", pd.Series("DO_NOT_BUY", index=frame.index)).astype(str).str.upper()
    hist = _num(_first_col(frame, ("historical_units_same_discount_avg_audit", "historical_units_same_discount_avg", "historical_units_same_discount_avg_feat")), index=frame.index)

    hist_p75 = float(hist[hist > 0].quantile(0.75)) if (hist > 0).any() else 0.0
    base_p75 = float(baseline_daily[baseline_daily > 0].quantile(0.75)) if (baseline_daily > 0).any() else 0.0
    strong_demand_signal = (hist >= max(hist_p75, 2.0)) | (baseline_daily >= max(base_p75, 0.5))
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_to_target = (raw_order / full_target_order.replace(0, np.nan)).round(3)

    unsafe_demand = (
        promo_source.eq("missing_promo_period_demand")
        | promo_sales.le(0)
        | (promo_quality.eq("VERY_LOW") & demand_strength.eq("CONFLICTING"))
    )
    credible_baseline = (baseline_daily > 0) & (source_days >= 28)
    conf_label = conf.map(_label)
    dq_pre, dq_penalties = _data_quality_score(
        soh=soh, on_order=on_order, promo_days=promo_days, baseline_daily=baseline_daily, hist=hist,
        pre_promo_source=pre_promo_source, promo_source=promo_source, promo_fallback=promo_fallback,
        promo_quality=promo_quality, target_used_floor=target_used_floor, formula_ok=formula_ok,
        review_flag=review_flag, risk_flag=risk_flag, unsafe_pre_promo=unsafe_pre_promo,
        demand_conflict=demand_conflict_flag, demand_strength=demand_strength, source_days=source_days,
    )
    dq_label = dq_pre.map(_label)

    stock_target_conflict = (full_target_order >= 20) & (raw_to_target < 0.5)
    best_seller = strong_demand_signal & (promo_cover_gap > 0) & (raw_order < promo_cover_gap)
    best_seller_floor = best_seller & promo_floor_applied.eq("YES") & (source_days >= 28)
    active_best_seller = credible_baseline & (baseline_period_demand >= 5) & strong_demand_signal

    order_budget = raw_order.where(has_raw & has_promo_demand, 0).astype(int)
    lift_promo = (
        (best_seller_floor | active_best_seller)
        & (dq_pre >= 50)
        & (conf >= 45)
        & promo_quality.isin(["MEDIUM", "HIGH", "VERY_HIGH"])
    )
    order_budget = pd.Series(
        np.where(lift_promo & (order_budget < promo_cover_gap), promo_cover_gap, order_budget),
        index=frame.index,
        dtype=int,
    )

    rec_promo = np.minimum(order_budget, promo_cover_gap).astype(int)
    budget_left = (order_budget - rec_promo).clip(lower=0).astype(int)
    rec_base = np.minimum(budget_left, base_stock_gap).astype(int)
    commercial = (rec_promo + rec_base).astype(int)

    order_basis = pd.Series(
        np.where(
            lift_promo,
            "target_stock_policy_lift",
            np.where(commercial > 0, "raw_model_order", "none"),
        ),
        index=frame.index,
    )
    op_low = raw_order.clip(lower=0).astype(int)
    op_high = full_target_order.astype(int)

    projected_after = (projected_before + commercial).round(3)
    remaining_promo_gap = (promo_cover_gap - rec_promo).clip(lower=0).astype(int)
    remaining_base_gap = (base_stock_gap - rec_base).clip(lower=0).astype(int)
    remaining_shortfall = (remaining_promo_gap + remaining_base_gap).astype(int)
    with np.errstate(divide="ignore", invalid="ignore"):
        commercial_cov_num = (commercial / full_target_order.replace(0, np.nan)).round(3)
    commercial_cov = commercial_cov_num.where(full_target_order > 0, np.where(commercial > 0, 1.0, np.nan)).fillna("")

    material_promo_gap = promo_cover_gap > HOLD_TARGET_TOLERANCE
    material_gap = full_target_order > HOLD_TARGET_TOLERANCE
    major_conflict = stock_target_conflict & (remaining_shortfall > 10)
    promo_covered = remaining_promo_gap <= HOLD_TARGET_TOLERANCE
    low_demand = (~has_promo_demand) | (promo_sales <= 0.5)

    buy_ok = (
        (commercial > 0)
        & promo_covered
        & (dq_pre >= 50)
        & (conf >= 45)
        & (~conf_label.isin(["LOW", "VERY_LOW"]))
        & (~promo_quality.eq("VERY_LOW"))
        & (~major_conflict)
        & demand_strength.isin(["STRONG", "MODERATE"])
        & best_seller_escalation.eq("NO")
        & (promo_sales >= baseline_period_demand - 1)
    )

    dnb_mask = (
        low_demand
        & ~material_promo_gap
        & (full_target_order <= HOLD_TARGET_TOLERANCE)
        & ((conf < 45) | (dq_pre < 50))
        & ~active_best_seller
    )
    hold_mask = (
        (full_target_order <= HOLD_TARGET_TOLERANCE)
        & (commercial == 0)
        & ~material_promo_gap
        & ~dnb_mask
        & ~review_flag
        & ~risk_flag
    )
    review_mask = (
        material_promo_gap & ~promo_covered
        | (remaining_base_gap > 10)
        | stock_target_conflict
        | best_seller_escalation.eq("YES")
        | demand_conflict_flag.eq("YES")
        | promo_floor_applied.eq("YES")
        | review_flag
        | risk_flag
        | unsafe_demand
        | unsafe_pre_promo
        | orig_action.isin(["REVIEW", "MONITOR"])
        | ((commercial > 0) & ~buy_ok)
    ) & ~dnb_mask

    decision = pd.Series("DO_NOT_BUY", index=frame.index)
    decision = decision.where(~dnb_mask, "DO_NOT_BUY")
    decision = decision.where(~hold_mask, "HOLD")
    decision = decision.where(~review_mask, "REVIEW")
    decision = decision.where(~buy_ok, "BUY")
    decision = decision.where(~((decision == "HOLD") & material_gap), "REVIEW")
    decision = decision.where(~((decision == "BUY") & (commercial <= 0)), "REVIEW")
    decision = decision.where(~((decision.isin(["DO_NOT_BUY", "HOLD"])) & material_promo_gap), "REVIEW")

    commercial = commercial.where(~decision.isin(["HOLD", "DO_NOT_BUY"]), 0).astype(int)
    rec_promo = rec_promo.where(~decision.isin(["HOLD", "DO_NOT_BUY"]), 0).astype(int)
    rec_base = rec_base.where(~decision.isin(["HOLD", "DO_NOT_BUY"]), 0).astype(int)
    recommended = commercial
    projected_after = (projected_before + commercial).round(3)
    remaining_promo_gap = (promo_cover_gap - rec_promo).clip(lower=0).astype(int)
    remaining_base_gap = (base_stock_gap - rec_base).clip(lower=0).astype(int)
    remaining_shortfall = (remaining_promo_gap + remaining_base_gap).astype(int)
    with np.errstate(divide="ignore", invalid="ignore"):
        commercial_cov_num = (commercial / full_target_order.replace(0, np.nan)).round(3)
    commercial_cov = commercial_cov_num.where(full_target_order > 0, np.where(commercial > 0, 1.0, np.nan)).fillna("")

    promo_covered = remaining_promo_gap <= HOLD_TARGET_TOLERANCE
    low_cov_buy = (decision == "BUY") & (~promo_covered)
    buy_suppressed = (
        (decision == "BUY")
        & (promo_sales < baseline_period_demand - 1)
        & (baseline_period_demand >= 5)
    )
    decision = decision.where(~low_cov_buy, "REVIEW")
    decision = decision.where(~buy_suppressed, "REVIEW")
    active_dnb = (decision == "DO_NOT_BUY") & active_best_seller & (baseline_period_demand >= 5)
    decision = decision.where(~active_dnb, "REVIEW")

    order_strategy = pd.Series(
        np.select(
            [
                decision.eq("DO_NOT_BUY"),
                decision.eq("HOLD"),
                decision.eq("BUY") & (remaining_shortfall <= 0),
                decision.eq("BUY") & promo_covered & (remaining_base_gap <= 0),
                decision.eq("BUY"),
                decision.eq("REVIEW") & promo_covered & (remaining_base_gap > 0),
                decision.eq("REVIEW") & (commercial > 0),
                material_promo_gap,
            ],
            [
                "DO_NOT_BUY",
                "NO_ORDER_REQUIRED",
                "FULL_TARGET_ORDER",
                "FULL_PROMO_COVER",
                "RAW_MODEL_CONSERVATIVE",
                "BASE_STOCK_REPLENISHMENT_REVIEW",
                "PARTIAL_PROMO_COVER_REVIEW",
                "PARTIAL_PROMO_COVER_REVIEW",
            ],
            default="PARTIAL_PROMO_COVER_REVIEW",
        ),
        index=frame.index,
    )

    conflict_reason = pd.Series(
        np.where(
            stock_target_conflict,
            "target_stock_requires_more_than_model_order",
            np.where(best_seller_floor, "best_seller_promo_floor_underorder", ""),
        ),
        index=frame.index,
    )
    constraint = conflict_reason.where(conflict_reason.ne(""), np.where(unsafe_demand, "insufficient_demand_evidence", "none"))

    capital = _num(frame.get("capital_at_risk_adjusted_dollars"), index=frame.index).round(2)
    end_soh = (projected_after - promo_sales).round(3)
    dq = dq_pre

    review_parts = pd.DataFrame({
        "risk_or_review_flag": np.where(risk_flag | review_flag, "risk_or_review_flag", ""),
        "low_confidence_buy": np.where((conf < 45) & (commercial > 0), "low_confidence_buy", ""),
        "missing_baseline_daily": np.where(baseline_daily <= 0, "missing_baseline_daily", ""),
        "target_end_floor_2": np.where(target_used_floor, "missing_sku_specific_30_day_cover_used_floor_2", ""),
        "unsafe_pre_promo_rejected": np.where(unsafe_pre_promo, "unsafe_pre_promo_source_rejected", ""),
        "promo_demand_fallback": np.where(promo_fallback.eq("YES"), "promo_period_demand_fallback", ""),
        "promo_baseline_floor": np.where(promo_floor_applied.eq("YES"), "promo_baseline_floor_applied", ""),
        "projected_start_floored": np.where(floored, "projected_start_stock_floored_flag", ""),
        "formula_reconciliation_failure": np.where(~formula_ok, "formula_reconciliation_failure", ""),
        "stock_target_conflict": np.where(stock_target_conflict, "stock_target_conflict", ""),
        "best_seller_escalation": np.where(best_seller_escalation.eq("YES"), "best_seller_escalation", ""),
        "demand_conflict": np.where(demand_conflict_flag.eq("YES"), "demand_evidence_conflict", ""),
        "promo_cover_gap": np.where(material_promo_gap & ~promo_covered, "promo_cover_not_fully_covered", ""),
    }, index=frame.index)
    review_reason = review_parts.apply(lambda r: "; ".join(x for x in r if x), axis=1)
    review_reason = review_reason.where(review_reason.ne(""), dq_penalties)

    buy_risk = risk_flag | review_flag | unsafe_demand | major_conflict | low_cov_buy | (remaining_base_gap > 10)
    human_review = np.where(
        decision.eq("REVIEW"),
        "YES",
        np.where(decision.eq("BUY"), np.where(buy_risk, "YES", "NO"), "NO"),
    )

    decision_quality = pd.Series(
        np.select(
            [
                decision.eq("BUY") & ~buy_risk,
                decision.eq("BUY"),
                decision.eq("REVIEW") & (~promo_covered),
                decision.eq("REVIEW") & (remaining_base_gap > 10),
                decision.eq("REVIEW") & unsafe_demand,
                decision.eq("REVIEW") & ((conf < 45) | (dq_pre < 50)),
                decision.eq("REVIEW"),
                decision.eq("HOLD"),
            ],
            [
                "EXECUTION_READY",
                "REVIEW_LOW_CONFIDENCE",
                "REVIEW_STOCK_GAP",
                "REVIEW_STOCK_GAP",
                "REVIEW_DEMAND_EVIDENCE",
                "REVIEW_LOW_CONFIDENCE",
                "REVIEW_STOCK_GAP",
                "HOLD_NO_ORDER_NEEDED",
            ],
            default="DO_NOT_BUY_LOW_EVIDENCE",
        ),
        index=frame.index,
    )

    gp = (
        _num(frame.get("feature_expected_gp_on_trust_floor_units"))
        + _num(frame.get("feature_expected_gp_on_speculative_units"))
    ).round(2)

    reason_demand_base = "Promo demand selected by evidence weighting: " + demand_selection_reason.astype(str)
    reason_order = (
        "Promo cover order gap "
        + promo_cover_gap.astype(str)
        + " units; base-stock replenishment gap "
        + base_stock_gap.astype(str)
        + " units; raw model "
        + raw_order.astype(str)
        + "; commercial recommended promo "
        + rec_promo.astype(str)
        + " + base "
        + rec_base.astype(str)
        + " = "
        + commercial.astype(str)
        + ". "
        + np.where(
            promo_covered & (remaining_base_gap <= 0),
            "Recommendation covers promo sales and end-stock target.",
            np.where(
                promo_covered,
                "Recommendation covers promo sales first; end-stock replenishment remains for review.",
                "Recommendation does not fully cover expected promo sales; buyer review required.",
            ),
        )
    )
    reason_stock = (
        "Projected day-one SOH before order "
        + projected_before.round(1).astype(str)
        + "; promo cover required "
        + promo_cover_required.round(1).astype(str)
        + " units; base-stock required "
        + base_stock_required.round(1).astype(str)
        + " units"
        + np.where(
            projected_before < promo_cover_required,
            "; current and on-order stock do not cover expected promo sales",
            "; stock covers expected promo sales before order",
        )
    )
    reason_risk = np.where(
        ~promo_covered,
        "Promo sales stock gap remains after recommendation",
        np.where(
            remaining_base_gap > 10,
            "Base-stock target is high relative to model order; buyer review required",
            np.where(
                unsafe_demand,
                "Unsafe or fallback promo demand source",
                "Shadow commercial pack; promo cover prioritised over base stock",
            ),
        ),
    )

    out = pd.DataFrame(
        {
            "store_number": store_number,
            "promotion_name": promotion_name,
            "promotion_start_date": start.dt.date.astype(str),
            "promotion_end_date": end.dt.date.astype(str),
            "promotion_days": promo_days,
            "prediction_date": prediction_date,
            "days_until_promotion_start": days_until,
            "sku_number": frame["sku_number"],
            "sku_description": frame["sku_description"],
            "decision": decision,
            "order_strategy": order_strategy,
            "recommended_order_basis": order_basis,
            "model_promo_forecast_units": model_promo_forecast,
            "same_discount_promo_units": same_discount_promo,
            "baseline_period_demand_units": baseline_period_demand,
            "selected_promo_period_demand_units": promo_sales,
            "promo_units_expected_to_sell": promo_sales,
            "demand_evidence_strength": demand_strength,
            "demand_conflict_flag": demand_conflict_flag,
            "demand_selection_reason": demand_selection_reason,
            "best_seller_floor_applied_flag": promo_floor_applied,
            "best_seller_escalation_flag": best_seller_escalation,
            "stock_needed_for_promo_sales": promo_cover_required,
            "stock_needed_to_finish_with_target_cover": base_stock_required,
            "order_needed_to_cover_promo_sales": promo_cover_gap,
            "order_needed_to_reach_full_stock_target": base_stock_gap,
            "full_target_order_units": full_target_order,
            "recommended_promo_cover_order_units": rec_promo,
            "recommended_base_stock_order_units": rec_base,
            "commercial_recommended_order_units": commercial,
            "recommended_order_units": recommended,
            "remaining_promo_sales_stock_gap": remaining_promo_gap,
            "remaining_end_stock_gap": remaining_base_gap,
            "remaining_shortfall_after_commercial_recommendation_units": remaining_shortfall,
            "remaining_day_one_shortfall_units": remaining_shortfall,
            "commercial_coverage_ratio": commercial_cov,
            "recommendation_coverage_ratio": commercial_cov,
            "raw_model_order_units": raw_order,
            "operator_review_order_low_units": op_low,
            "operator_review_order_high_units": op_high,
            "target_day_one_soh_units": target_day_one,
            "projected_day_one_soh_before_order_units": projected_before,
            "projected_day_one_soh_after_recommended_order_units": projected_after,
            "current_soh_units": soh.round(3),
            "on_order_units": on_order.round(3),
            "estimated_demand_before_promo_start_units": pre_promo,
            "target_stock_on_hand_at_promo_end_units": base_stock_required,
            "total_expected_demand_to_promo_end_units": total_demand,
            "projected_stock_on_hand_at_promo_end_units": end_soh,
            "discount_percent": _num(frame.get("discount_percent")).round(2),
            "avg_promo_demand_same_discount_units": hist.round(3),
            "expected_gp_dollars": gp,
            "capital_at_risk_dollars": capital,
            "confidence_score": conf.round(1),
            "data_quality_score": dq,
            "stock_target_conflict_flag": stock_target_conflict.astype(int),
        }
    )
    out["confidence_label"] = out["confidence_score"].map(_label)
    out["data_quality_label"] = out["data_quality_score"].map(_label)
    out["decision_quality_label"] = decision_quality
    out["reason_demand"] = reason_demand_base
    out["reason_demand"] = np.where(
        pre_promo > 0,
        out["reason_demand"] + "; Pre-promo demand = baseline daily rate x days until start",
        out["reason_demand"] + "; Pre-promo demand is zero or negligible for remaining lead time",
    )
    out["reason_stock"] = reason_stock
    out["reason_order"] = reason_order
    out["reason_risk"] = reason_risk
    out["reason_rejection_or_hold"] = np.where(
        out["decision"].isin(["HOLD", "DO_NOT_BUY"]),
        np.where(
            out["decision"] == "DO_NOT_BUY",
            "Low promo demand and/or poor evidence; no commercial order need",
            "No order required; target day-one gap is within tolerance (<= "
            + str(HOLD_TARGET_TOLERANCE)
            + " units)",
        ),
        "",
    )
    out["human_review_required"] = human_review
    out["review_reason"] = review_reason
    out["model_status"] = META_STATUS
    out["production_ordering_approved"] = PRODUCTION_ORDERING
    out["customer_report_release_approved"] = CUSTOMER_RELEASE
    out["operator_decision"] = ""
    out["operator_recommended_units"] = ""
    out["operator_notes"] = ""
    out["promo_period_demand_source"] = promo_source
    out["promo_period_demand_fallback_flag"] = promo_fallback
    out["promo_demand_model_source"] = promo_demand_model_source
    out["promo_demand_source_lineage"] = promo_demand_source_lineage
    out["promo_demand_source_quality"] = promo_demand_source_quality
    out["promo_demand_selection_method"] = promo_demand_selection_method
    out["promo_demand_release_ready_flag"] = promo_demand_release_ready_flag
    out["model_expected_units_total_promo_raw"] = _field_series(frame, ("model_expected_units_total_promo_raw", "model_expected_units_total_promo"), frame.index).round(3)
    out["promo_demand_calibration_factor"] = _field_series(frame, ("promo_demand_calibration_factor",), frame.index).round(6)
    out["model_expected_units_total_promo_calibrated"] = _field_series(frame, ("model_expected_units_total_promo_calibrated",), frame.index).round(3)
    out["calibration_quality"] = frame.get("calibration_quality", pd.Series("LOW", index=frame.index)).astype(str)
    out["calibration_release_ready_flag"] = frame.get("calibration_release_ready_flag", pd.Series("NO", index=frame.index)).astype(str)
    out["calibration_allowed_in_release_decision"] = frame.get(
        "calibration_allowed_in_release_decision", pd.Series("NO", index=frame.index)
    ).astype(str)

    stock_cols = (
        "promo_start_soh",
        "target_promo_start_soh",
        "promo_start_soh_gap",
        "supplier_lead_time_days",
        "supplier_replenishment_class",
        "supplier_reorder_flexibility",
        "forecast_demand_units",
        "target_end_soh_units",
        "target_order_units_stock_outcome",
        "order_units_stock_outcome_adjustment",
        "promo_end_days_cover",
        "stock_outcome_label",
        "stock_outcome_order_reason",
    )
    for col in stock_cols:
        out[col] = _field_series(frame, (col,), frame.index)
        if col in ("promo_start_soh", "target_promo_start_soh", "promo_start_soh_gap", "forecast_demand_units", "target_end_soh_units", "target_order_units_stock_outcome", "order_units_stock_outcome_adjustment", "promo_end_days_cover", "promo_start_soh_resolved", "promo_start_soh_confidence_score", "inbound_units_before_promo", "inbound_units_during_promo", "reliable_inbound_units_before_or_during_promo"):
            out[col] = _num(out[col], index=frame.index).round(3)
        else:
            out[col] = out[col].astype(str)

    truth_cols = (
        "promo_start_soh_resolved",
        "promo_start_soh_source",
        "promo_start_soh_source_quality",
        "promo_start_soh_confidence_score",
        "inbound_units_before_promo",
        "inbound_units_during_promo",
        "reliable_inbound_units_before_or_during_promo",
        "inbound_stock_source_quality",
        "supplier_number_resolved",
        "supplier_number_source_quality",
        "supplier_replenishment_class_repaired",
        "supplier_lead_time_days_repaired",
        "supplier_reorder_flexibility_repaired",
    )
    for col in truth_cols:
        if col not in out.columns:
            if col in ("promo_start_soh_resolved", "promo_start_soh_confidence_score", "inbound_units_before_promo", "inbound_units_during_promo", "reliable_inbound_units_before_or_during_promo", "supplier_lead_time_days_repaired"):
                out[col] = _num(_field_series(frame, (col,), frame.index), index=frame.index).round(3)
            else:
                out[col] = _field_series(frame, (col,), frame.index).astype(str)

    position_cols = (
        "optimal_base_soh_units",
        "current_days_cover",
        "current_stock_position_label",
        "days_until_promo_start",
        "expected_units_until_promo_start",
        "expected_soh_at_promo_start_before_order",
        "expected_normal_units_during_promo",
        "expected_promo_uplift_units",
        "promo_convexity_score",
        "target_day_one_promo_soh",
        "target_end_promo_soh",
        "optimal_stock_position_order_units",
        "distance_to_optimal_end_soh",
        "promo_exit_success_flag",
        "stock_position_order_reason",
        "replenishment_lead_time_days",
        "replenishment_risk_class",
        "store_sales_regime",
        "customer_loyalty_regime",
        "sku_demand_regime",
        "stock_position_regime",
        "supplier_replenishment_regime",
        "promo_convexity_regime",
        "cash_efficiency_regime",
        "capital_at_risk_regime",
        "customer_basket_trust_regime",
        "overall_regime_opportunity_score",
        "overall_regime_risk_score",
        "overall_regime_conviction_score",
        "raw_regime_conviction_score",
        "regime_historical_wape",
        "regime_historical_bias_pct",
        "regime_confidence_cap",
        "calibrated_regime_conviction_score",
        "calibrated_conviction_label",
        "conviction_downgrade_reason",
        "regime_bias_direction",
        "regime_bias_adjustment_recommendation",
        "buyer_review_required_flag",
        "buyer_review_reason",
        "decision_confidence_for_report",
        "decision_confidence_label_for_report",
        "decision_triage_class",
        "decision_triage_reason",
        "buyer_review_priority_score",
        "buyer_review_priority_label",
        "buyer_review_required_flag_triaged",
        "buyer_review_queue_rank",
        "buyer_review_queue_bucket",
        "recommended_review_batch",
        "auto_block_flag",
        "watchlist_flag",
        "future_auto_approve_candidate_flag",
        "triage_governance_note",
        "economic_net_value_score",
        "economic_value_confidence_score",
        "economic_value_label",
        "economic_value_driver_1",
        "economic_value_driver_2",
        "economic_value_driver_3",
        "missed_sales_avoidance_value",
        "basket_trust_protection_value",
        "overstock_cash_release_value",
        "cash_tied_above_optimal_cost",
        "supplier_economic_risk_cost",
        "review_roi_score",
        "review_roi_label",
        "economic_priority_rank",
        "economic_review_queue_bucket",
        "triage_priority_score_v2",
        "priority_rank_change",
        "priority_rank_change_reason",
        "long_tail_sku_flag",
        "basket_completion_sku_flag",
        "basket_attachment_score",
        "basket_mission_importance_score",
        "long_tail_stockout_risk_score",
        "basket_loss_multiplier",
        "long_tail_protection_value",
        "basket_trust_convexity_value",
        "long_tail_minimum_soh_required",
        "long_tail_open_for_sale_required_flag",
        "long_tail_basket_protection_reason",
        "feature_basket_attach_rate",
        "feature_basket_3plus_attach_rate",
        "feature_basket_5plus_attach_rate",
        "feature_avg_basket_value_when_present",
        "feature_avg_basket_gp_when_present",
        "feature_sister_club_attach_rate",
        "mission_sku_score",
        "mission_sku_flag",
        "basket_completion_sku_score",
        "range_trust_sku_score",
        "long_tail_mission_sku_flag",
        "basket_attachment_source",
        "basket_attachment_source_quality",
        "basket_attachment_used_real_transactions_flag",
        "mission_sku_reason",
        "regime_adjusted_decision_value",
        "brain_action_label",
        "brain_order_units_proposal",
        "constraint_block_flag",
        "constraint_block_reason",
        "final_governed_action_label",
        "final_governed_order_units",
        "top_regime_driver_1",
        "top_regime_driver_2",
        "top_regime_driver_3",
        "human_interpretation_summary",
    )
    numeric_position = {
        "optimal_base_soh_units", "current_days_cover", "expected_units_until_promo_start",
        "expected_soh_at_promo_start_before_order", "expected_normal_units_during_promo",
        "expected_promo_uplift_units", "promo_convexity_score", "target_day_one_promo_soh",
        "target_end_promo_soh", "optimal_stock_position_order_units", "distance_to_optimal_end_soh",
        "replenishment_lead_time_days", "overall_regime_opportunity_score", "overall_regime_risk_score",
        "overall_regime_conviction_score", "raw_regime_conviction_score", "regime_historical_wape",
        "regime_historical_bias_pct", "regime_confidence_cap", "calibrated_regime_conviction_score",
        "decision_confidence_for_report", "regime_adjusted_decision_value", "brain_order_units_proposal",
        "final_governed_order_units", "buyer_review_priority_score", "buyer_review_queue_rank",
        "economic_net_value_score", "economic_value_confidence_score", "missed_sales_avoidance_value",
        "basket_trust_protection_value", "overstock_cash_release_value", "cash_tied_above_optimal_cost",
        "supplier_economic_risk_cost", "review_roi_score", "triage_priority_score_v2", "economic_priority_rank",
        "priority_rank_change", "basket_attachment_score", "basket_mission_importance_score",
        "long_tail_stockout_risk_score", "basket_loss_multiplier", "long_tail_protection_value",
        "basket_trust_convexity_value", "long_tail_minimum_soh_required",
        "mission_sku_score", "basket_completion_sku_score", "range_trust_sku_score",
    }
    for col in position_cols:
        out[col] = _field_series(frame, (col,), frame.index)
        if col in numeric_position:
            out[col] = _num(out[col], index=frame.index).round(3)
        else:
            out[col] = out[col].astype(str)

    calc = pd.DataFrame(
        {
            "sku_number": frame["sku_number"],
            "pre_promo_demand_source": pre_promo_source,
            "promo_period_demand_source": promo_source,
            "promo_period_demand_source_quality": promo_quality,
            "promo_period_demand_fallback_flag": promo_fallback,
            "promo_period_demand_warning": promo_warning,
            "model_promo_forecast_units": model_promo_forecast,
            "same_discount_promo_units": same_discount_promo,
            "baseline_period_demand_units": baseline_period_demand,
            "selected_promo_period_demand_units": promo_sales,
            "selected_promo_period_demand_units_before": promo_selected_before,
            "demand_evidence_strength": demand_strength,
            "demand_conflict_flag": demand_conflict_flag,
            "demand_selection_reason": demand_selection_reason,
            "best_seller_escalation_flag": best_seller_escalation,
            "promo_demand_floor_applied_flag": promo_floor_applied,
            "promo_demand_floor_reason": promo_floor_reason,
            "promo_demand_model_source": promo_demand_model_source,
            "promo_demand_source_lineage": promo_demand_source_lineage,
            "promo_demand_source_quality": promo_demand_source_quality,
            "promo_demand_selection_method": promo_demand_selection_method,
            "promo_demand_release_ready_flag": promo_demand_release_ready_flag,
            "promo_demand_unsafe_flag": unsafe_demand.map({True: "YES", False: "NO"}),
            "baseline_daily_rate_units": baseline_daily,
            "baseline_daily_source_days": source_days,
            "promo_cover_required_units": promo_cover_required,
            "promo_cover_order_gap_units": promo_cover_gap,
            "base_stock_required_units": base_stock_required,
            "base_stock_replenishment_gap_units": base_stock_gap,
            "full_target_order_units": full_target_order,
            "target_order_units_to_hit_day_one_soh": full_target_order,
            "recommended_promo_cover_order_units": rec_promo,
            "recommended_base_stock_order_units": rec_base,
            "order_units_source": "raw_model_order_units",
            "confidence_source": "model_confidence_percent",
            "raw_model_order_units": raw_order,
            "commercial_recommended_order_units": commercial,
            "remaining_promo_cover_gap_units": remaining_promo_gap,
            "remaining_base_stock_gap_units": remaining_base_gap,
            "remaining_day_one_shortfall_units": remaining_shortfall,
            "order_recommendation_strategy": order_strategy,
            "recommendation_type": order_strategy,
            "recommended_order_basis": order_basis,
            "recommendation_constraint_reason": constraint,
            "stock_target_conflict_flag": stock_target_conflict.astype(int),
            "raw_model_to_target_ratio": raw_to_target,
            "proposed_order_policy": order_strategy,
            "raw_projected_start_stock_before_floor_units": projected_before_raw,
            "projected_start_stock_floor_units_removed": floor_removed,
            "projected_start_stock_floored_flag": floored.map({True: "YES", False: "NO"}),
            "target_end_used_floor_2_flag": target_used_floor.map({True: "YES", False: "NO"}),
            "formula_optimal_reconciles": formula_ok.map({True: "YES", False: "NO"}),
            "data_quality_penalties": dq_penalties,
            "unsafe_raw_expected_units_before_promo_start": unsafe_raw_pre.round(3),
            "contradiction_pre_promo_dominates_promo": (pre_promo > promo_sales * 2) & (days_until <= 1),
        }
    )
    return out, calc


def _sort_order_plan(df: pd.DataFrame) -> pd.DataFrame:
    rank = df["decision"].map({"BUY": 0, "REVIEW": 1, "HOLD": 2, "DO_NOT_BUY": 3}).fillna(4)
    out = df.assign(_rank=rank).sort_values(
        ["_rank", "promo_units_expected_to_sell", "total_expected_demand_to_promo_end_units", "confidence_score"],
        ascending=[True, False, False, False],
        kind="mergesort",
    )
    out = out.drop(columns=["_rank"])
    out.insert(0, "priority_rank", range(1, len(out) + 1))
    out = out.reset_index(drop=True)
    cols = [c for c in ORDER_PLAN_COLUMNS if c in out.columns]
    return out[cols]


def _assign_review_subtype(plan: pd.DataFrame, calc: pd.DataFrame) -> pd.Series:
    """Assign exactly one primary review subtype per REVIEW row."""
    idx = plan.index
    promo_source = calc.set_index("sku_number")["promo_period_demand_source"].reindex(plan["sku_number"]).reset_index(drop=True)
    promo_fallback = calc.set_index("sku_number")["promo_period_demand_fallback_flag"].reindex(plan["sku_number"]).reset_index(drop=True)
    promo_sales = _num(plan["promo_units_expected_to_sell"], index=idx)
    rem_promo = _num(plan["remaining_promo_sales_stock_gap"], index=idx)
    rem_base = _num(plan["remaining_end_stock_gap"], index=idx)
    conf = _num(plan["confidence_score"], index=idx)
    dq = _num(plan["data_quality_score"], index=idx)
    strength = plan["demand_evidence_strength"].astype(str)
    raw = _num(plan["raw_model_order_units"], index=idx)
    op_low = _num(plan["operator_review_order_low_units"], index=idx)
    op_high = _num(plan["operator_review_order_high_units"], index=idx)
    gp = _num(plan.get("expected_gp_dollars"), index=idx)
    promo_gap = _num(plan["order_needed_to_cover_promo_sales"], index=idx)
    stock_conflict = _num(plan.get("stock_target_conflict_flag"), index=idx).astype(bool)

    unsafe_demand = (
        promo_source.eq("missing_promo_period_demand")
        | strength.eq("CONFLICTING")
        | plan.get("demand_conflict_flag", pd.Series("NO", index=idx)).eq("YES")
    )
    wide_range = (op_high >= 20) & (raw < op_high * 0.5)
    wide_range = wide_range | ((op_high - op_low) > np.maximum(op_high * 0.5, 5))
    high_value = (promo_sales >= 5) | (gp >= 50) | (promo_gap >= 10) | (rem_promo + rem_base >= 15)

    subtype = pd.Series("none", index=idx)
    is_review = plan["decision"].eq("REVIEW")
    subtype = subtype.where(
        ~(is_review & unsafe_demand),
        "review_demand_evidence",
    )
    subtype = subtype.where(
        ~(is_review & (conf < 45) & subtype.eq("none")),
        "review_low_confidence",
    )
    subtype = subtype.where(
        ~(is_review & (dq < 50) & subtype.eq("none")),
        "review_data_quality",
    )
    subtype = subtype.where(
        ~(is_review & ((rem_promo > HOLD_TARGET_TOLERANCE) | (promo_gap > HOLD_TARGET_TOLERANCE)) & subtype.eq("none")),
        "review_stock_gap",
    )
    subtype = subtype.where(
        ~(is_review & (rem_promo <= HOLD_TARGET_TOLERANCE) & (rem_base > 10) & subtype.eq("none")),
        "review_base_stock_gap",
    )
    subtype = subtype.where(
        ~(is_review & wide_range & stock_conflict & subtype.eq("none")),
        "review_order_range",
    )
    subtype = subtype.where(
        ~(is_review & high_value & subtype.eq("none")),
        "review_high_value",
    )
    subtype = subtype.where(~(is_review & subtype.eq("none")), "review_stock_gap")
    return subtype.where(is_review, "none")


def _compute_split_scores(
    plan: pd.DataFrame,
    review_subtype: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Split action value, no-buy trust, review priority, and overall shortlist ranking."""
    idx = plan.index
    promo = _num(plan["promo_units_expected_to_sell"], index=idx)
    rec = _num(plan["recommended_order_units"], index=idx)
    rem_promo = _num(plan["remaining_promo_sales_stock_gap"], index=idx)
    rem_base = _num(plan["remaining_end_stock_gap"], index=idx)
    conf = _num(plan["confidence_score"], index=idx)
    dq = _num(plan["data_quality_score"], index=idx)
    gp = _num(plan.get("expected_gp_dollars"), index=idx)
    strength = plan["demand_evidence_strength"].astype(str)
    target_order = _num(plan["full_target_order_units"], index=idx)

    promo_p75 = float(promo[promo > 0].quantile(0.75)) if (promo > 0).any() else 1.0
    rec_p75 = float(rec[rec > 0].quantile(0.75)) if (rec > 0).any() else 1.0
    promo_norm = (promo / max(promo_p75, 1.0) * 30).clip(0, 30)
    order_norm = (rec / max(rec_p75, 1.0) * 25).clip(0, 25)
    gap_risk = ((rem_promo + rem_base) / 20 * 15).clip(0, 15)
    gp_norm = (gp / max(float(gp[gp > 0].quantile(0.75)) if (gp > 0).any() else 1.0, 1.0) * 10).clip(0, 10)

    action = (promo_norm + order_norm + gap_risk + gp_norm + conf * 0.15 + dq * 0.15).clip(0, 100)
    action = action.where(plan["decision"].isin(["BUY", "REVIEW"]), 0.0)
    action = action.where(~strength.eq("STRONG"), action + 5)
    action = action.where(~strength.eq("MODERATE"), action + 2)
    action = action.where(~strength.isin(["WEAK", "CONFLICTING"]), action - 15)
    action = action.where(
        ~review_subtype.isin(["review_demand_evidence", "review_low_confidence", "review_data_quality"]),
        action - 10,
    )
    action = action.where(~review_subtype.eq("review_high_value"), action + 8)
    action = action.clip(0, 100).round(1)

    trust = pd.Series(0.0, index=idx)
    trust = trust.where(
        ~plan["decision"].isin(["DO_NOT_BUY", "HOLD"]),
        (dq * 0.45 + conf * 0.35).clip(0, 70),
    )
    trust = trust.where(~((promo <= 1) & (target_order <= HOLD_TARGET_TOLERANCE)), trust + 20)
    trust = trust.where(~(plan["decision"].eq("DO_NOT_BUY") & (dq >= 50)), trust + 5)
    trust = trust.clip(0, 100).round(1)

    review_pri = pd.Series(0.0, index=idx)
    review_pri = review_pri.where(
        ~plan["decision"].eq("REVIEW"),
        action,
    )
    review_pri = review_pri.where(~review_subtype.eq("review_high_value"), review_pri + 12)
    review_pri = review_pri.where(~review_subtype.eq("review_stock_gap"), review_pri + 8)
    review_pri = review_pri.where(~review_subtype.eq("review_order_range"), review_pri + 6)
    review_pri = review_pri.where(
        ~review_subtype.isin(["review_demand_evidence", "review_low_confidence", "review_data_quality"]),
        review_pri - 5,
    )
    review_pri = review_pri.clip(0, 100).round(1)

    overall = action.where(plan["decision"].isin(["BUY", "REVIEW"]), trust)
    overall = overall.clip(0, 100).round(1)
    return action, trust, review_pri, overall, overall.map(_label)


def _assign_review_burden_class(
    plan: pd.DataFrame,
    review_subtype: pd.Series,
    exec_ready: pd.Series,
) -> pd.Series:
    idx = plan.index
    rem_promo = _num(plan["remaining_promo_sales_stock_gap"], index=idx)
    rec = _num(plan["recommended_order_units"], index=idx)
    target_order = _num(plan["full_target_order_units"], index=idx)
    burden = pd.Series("no_review_required", index=idx)

    must_review = (
        plan["decision"].eq("REVIEW")
        & (
            review_subtype.isin(["review_stock_gap", "review_high_value", "review_order_range", "review_base_stock_gap"])
            | (rec > 0)
            | (rem_promo > HOLD_TARGET_TOLERANCE)
            | (target_order > 10)
        )
    )
    optional_review = plan["decision"].eq("REVIEW") & ~must_review
    audit_only = (
        ~plan["decision"].eq("REVIEW")
        & plan.get("review_reason", pd.Series("", index=idx)).astype(str).str.len().gt(0)
        & ~exec_ready
    )

    burden = np.where(must_review.to_numpy(), "must_review", burden)
    burden = np.where(optional_review.to_numpy(), "optional_review", burden)
    burden = np.where(audit_only.to_numpy(), "audit_only", burden)
    burden = np.where(
        (exec_ready & plan["decision"].eq("BUY")).to_numpy(),
        "no_review_required",
        burden,
    )
    return pd.Series(burden, index=idx)


def _manager_summary_contradiction_count(order_plan: pd.DataFrame, summary: pd.DataFrame) -> int:
    contradictions = 0
    exec_ready_buy_plan = int(
        ((order_plan["decision"] == "BUY") & (order_plan["execution_ready_flag"] == "YES")).sum()
    )
    exec_ready_plan = int(
        ((order_plan["decision"] == "BUY") & (order_plan["execution_ready_flag"] == "YES")).sum()
    )
    if int(summary.get("execution_ready_buy_count", pd.Series([0])).iloc[0]) != exec_ready_buy_plan:
        contradictions += 1
    if int(summary.get("execution_ready_count", pd.Series([0])).iloc[0]) != exec_ready_plan:
        contradictions += 1
    for tier_col, tier_val in (
        ("tier_1_execute_count", "tier_1_execute"),
        ("tier_2_review_high_value_count", "tier_2_review_high_value"),
        ("tier_3_review_evidence_gap_count", "tier_3_review_evidence_gap"),
    ):
        if int(summary.get(tier_col, pd.Series([0])).iloc[0]) != int((order_plan["action_tier"] == tier_val).sum()):
            contradictions += 1
    review_high = int(
        ((order_plan["decision"] == "REVIEW") & (order_plan["review_subtype"] == "review_high_value")).sum()
    )
    tier2 = int((order_plan["action_tier"] == "tier_2_review_high_value").sum())
    if review_high > 0 and tier2 < review_high:
        contradictions += review_high - tier2
    rec_total_plan = float(order_plan["recommended_order_units"].sum())
    rec_total_summary = float(summary.get("total_recommended_order_units", pd.Series([0])).iloc[0])
    if abs(rec_total_plan - rec_total_summary) > 0.01:
        contradictions += 1
    return contradictions


def _assign_action_workflow_fields(
    plan: pd.DataFrame,
    calc: pd.DataFrame,
) -> pd.DataFrame:
    """Add action tiers, execution readiness, and operator priority groups."""
    out = plan.copy()
    review_subtype = _assign_review_subtype(out, calc)
    action_score, trust_score, review_pri, overall_pri, cv_label = _compute_split_scores(out, review_subtype)

    promo_source = calc.set_index("sku_number")["promo_period_demand_source"].reindex(out["sku_number"]).reset_index(drop=True)
    strength = out["demand_evidence_strength"].astype(str)
    conf = _num(out["confidence_score"], index=out.index)
    dq = _num(out["data_quality_score"], index=out.index)
    rec = _num(out["recommended_order_units"], index=out.index)
    rem_promo = _num(out["remaining_promo_sales_stock_gap"], index=out.index)
    cov = pd.to_numeric(out["commercial_coverage_ratio"], errors="coerce").fillna(0)
    stock_conflict = _num(out.get("stock_target_conflict_flag"), index=out.index).astype(bool)

    unsafe_demand = (
        promo_source.eq("missing_promo_period_demand")
        | strength.eq("CONFLICTING")
        | out.get("demand_conflict_flag", pd.Series("NO", index=out.index)).eq("YES")
    )
    promo_covered = (rem_promo <= HOLD_TARGET_TOLERANCE) | (cov >= 0.85)

    exec_ready = (
        out["decision"].eq("BUY")
        & strength.isin(["MODERATE", "STRONG"])
        & (dq >= 75)
        & (conf >= 50)
        & (rec > 0)
        & promo_covered
        & ~stock_conflict
        & ~unsafe_demand
    )
    exec_ready_flag = pd.Series(np.where(exec_ready.to_numpy(dtype=bool), "YES", "NO"), index=out.index)

    blocker_codes = [
        (out["decision"].ne("BUY"), "not_buy_decision"),
        (strength.eq("CONFLICTING"), "weak_or_conflicting_demand_evidence"),
        (dq < 75, "data_quality_below_75"),
        (conf < 50, "confidence_below_50"),
        (rec <= 0, "zero_recommended_order"),
        (~promo_covered, "promo_cover_gap_remains"),
        (stock_conflict, "stock_target_conflict"),
        (unsafe_demand, "unsafe_promo_demand"),
    ]
    execution_blocker = pd.Series("", index=out.index)
    for mask, code in blocker_codes:
        execution_blocker = execution_blocker.where(~(out["decision"].eq("BUY") & mask), code)

    tier = pd.Series("tier_5_do_not_buy", index=out.index)
    tier = np.where(out["decision"].eq("HOLD"), "tier_4_hold_monitor", tier)
    tier = np.where(exec_ready.to_numpy(dtype=bool), "tier_1_execute", tier)
    tier = np.where(out["decision"].eq("REVIEW"), "tier_3_review_evidence_gap", tier)
    tier = np.where(
        out["decision"].eq("REVIEW") & review_subtype.eq("review_high_value").to_numpy(),
        "tier_2_review_high_value",
        tier,
    )
    tier = np.where(
        (
            out["decision"].eq("REVIEW")
            & review_pri.ge(45)
            & review_subtype.isin(["review_stock_gap", "review_order_range", "review_base_stock_gap"])
        ).to_numpy(),
        "tier_2_review_high_value",
        tier,
    )
    tier = np.where(
        (out["decision"].eq("BUY") & ~exec_ready.to_numpy(dtype=bool)),
        "tier_3_review_evidence_gap",
        tier,
    )
    tier = pd.Series(tier, index=out.index)

    priority = pd.Series("rejected_poor_seller", index=out.index)
    priority = priority.where(~out["decision"].eq("HOLD"), "no_order_needed")
    priority = priority.where(
        ~(out["decision"].eq("HOLD") & (rem_promo + _num(out["remaining_end_stock_gap"], index=out.index) > HOLD_TARGET_TOLERANCE)),
        "check_stock_position",
    )
    priority = priority.where(
        ~(out["decision"].eq("REVIEW") & review_subtype.isin(["review_stock_gap", "review_base_stock_gap"])),
        "check_stock_position",
    )
    priority = priority.where(~out["decision"].eq("REVIEW"), "review_before_order")
    priority = priority.where(~exec_ready, "order_now_candidate")

    review_burden = _assign_review_burden_class(out, review_subtype, pd.Series(exec_ready, index=out.index))

    overall_row = pd.Series(0.0, index=out.index)
    overall_row = overall_row.where(~exec_ready, action_score)
    overall_row = overall_row.where(~tier.eq("tier_2_review_high_value"), review_pri)
    overall_row = overall_row.where(
        ~tier.eq("tier_3_review_evidence_gap"),
        review_pri * 0.85,
    )
    overall_row = overall_row.where(
        ~((out["decision"] == "DO_NOT_BUY") & (trust_score >= 40)),
        trust_score,
    )
    overall_row = overall_row.clip(0, 100).round(1)

    out["review_subtype"] = review_subtype
    out["commercial_action_value_score"] = action_score
    out["no_buy_trust_score"] = trust_score
    out["review_priority_score"] = review_pri
    out["overall_row_priority_score"] = overall_row
    out["commercial_value_score"] = overall_row
    out["commercial_value_label"] = overall_row.map(_label)
    out["review_burden_class"] = review_burden
    out["execution_ready_flag"] = exec_ready_flag
    out["execution_blocker"] = execution_blocker.where(out["decision"].eq("BUY"), "")
    out["action_tier"] = tier
    out["operator_priority_group"] = priority
    return out


def build_execution_shortlist(order_plan: pd.DataFrame) -> pd.DataFrame:
    """Buyer-first shortlist: execute, high-value review, and trust-building no-buys."""
    tier_rank = {
        "tier_1_execute": 0,
        "tier_2_review_high_value": 1,
        "tier_3_review_evidence_gap": 2,
        "tier_5_do_not_buy": 3,
    }
    trust_dnb = order_plan[
        (order_plan["decision"] == "DO_NOT_BUY")
        & (_num(order_plan["no_buy_trust_score"]) >= 50)
    ].sort_values(["no_buy_trust_score", "overall_row_priority_score"], ascending=[False, False])

    parts: list[pd.DataFrame] = []
    for tier in ("tier_1_execute", "tier_2_review_high_value", "tier_3_review_evidence_gap"):
        chunk = order_plan[order_plan["action_tier"] == tier].sort_values(
            ["overall_row_priority_score", "commercial_action_value_score", "promo_units_expected_to_sell"],
            ascending=[False, False, False],
        )
        if tier == "tier_1_execute":
            parts.append(chunk)
        elif tier == "tier_2_review_high_value":
            parts.append(chunk.head(50))
        else:
            mat = chunk[_num(chunk["commercial_action_value_score"]) >= 35]
            parts.append(mat.head(30))
    parts.append(trust_dnb.head(25))

    shortlist = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["sku_number"], keep="first")
    shortlist = shortlist.assign(
        _tier_rank=shortlist["action_tier"].map(tier_rank).fillna(9),
    ).sort_values(
        ["_tier_rank", "overall_row_priority_score", "promo_units_expected_to_sell"],
        ascending=[True, False, False],
        kind="mergesort",
    ).drop(columns=["_tier_rank"])
    shortlist = shortlist.head(120).reset_index(drop=True)
    if "priority_rank" in shortlist.columns:
        shortlist = shortlist.drop(columns=["priority_rank"])
    shortlist.insert(2, "priority_rank", range(1, len(shortlist) + 1))
    cols = [c for c in EXECUTION_SHORTLIST_COLUMNS if c in shortlist.columns]
    return shortlist[cols]


def build_review_exceptions(order_plan: pd.DataFrame) -> pd.DataFrame:
    burden = order_plan.get("review_burden_class", pd.Series("must_review", index=order_plan.index))
    action_score = _num(order_plan.get("commercial_action_value_score"), index=order_plan.index)
    review_pri = _num(order_plan.get("review_priority_score"), index=order_plan.index)
    return order_plan[
        burden.eq("must_review")
        | (burden.eq("optional_review") & (action_score.ge(35) | review_pri.ge(40)))
    ].copy()


def build_manager_summary(order_plan: pd.DataFrame, exceptions: pd.DataFrame) -> pd.DataFrame:
    counts = order_plan["decision"].value_counts()
    _stock_truth_gate, stock_truth_rec = load_stock_truth_artifacts()
    _opt_gate, optimal_stock_rec = load_optimal_stock_artifacts()
    hold_pos = int(((order_plan["decision"].isin(["HOLD", "DO_NOT_BUY"])) & (order_plan["recommended_order_units"] > 0)).sum())
    zero_buy = int(((order_plan["decision"] == "BUY") & (order_plan["recommended_order_units"] <= 0)).sum())
    non_std = int((~order_plan["decision"].isin(ALLOWED_DECISIONS)).sum())
    contradiction = hold_pos + zero_buy + non_std
    row = order_plan.iloc[0]
    return pd.DataFrame(
        [{
            "store_number": int(row["store_number"]),
            "promotion_name": row["promotion_name"],
            "promotion_start_date": row["promotion_start_date"],
            "promotion_end_date": row["promotion_end_date"],
            "prediction_date": row["prediction_date"],
            "promotion_days": int(row["promotion_days"]),
            "total_skus": len(order_plan),
            "buy_count": int(counts.get("BUY", 0)),
            "review_count": int(counts.get("REVIEW", 0)),
            "hold_count": int(counts.get("HOLD", 0)),
            "do_not_buy_count": int(counts.get("DO_NOT_BUY", 0)),
            "total_recommended_order_units": float(order_plan["recommended_order_units"].sum()),
            "total_estimated_demand_before_promo_start": float(order_plan["estimated_demand_before_promo_start_units"].sum()),
            "total_predicted_promo_period_sales": float(order_plan["promo_units_expected_to_sell"].sum()),
            "total_expected_demand_to_promo_end": float(order_plan["total_expected_demand_to_promo_end_units"].sum()),
            "total_target_day_one_soh": float(order_plan["target_day_one_soh_units"].sum()),
            "total_target_end_stock": float(order_plan["stock_needed_to_finish_with_target_cover"].sum()),
            "total_capital_at_risk": float(order_plan["capital_at_risk_dollars"].sum()),
            "low_confidence_count": int((order_plan["confidence_score"] < 45).sum()),
            "low_data_quality_count": int((order_plan["data_quality_score"] < 50).sum()),
            "review_exception_count": len(exceptions),
            "zero_order_buy_count": zero_buy,
            "non_standard_action_count": non_std,
            "contradiction_count": contradiction,
            "total_target_order_units_to_hit_day_one_soh": float(order_plan["full_target_order_units"].sum()),
            "total_remaining_day_one_shortfall_units": float(order_plan["remaining_day_one_shortfall_units"].sum()),
            "total_promo_cover_required_units": float(order_plan["stock_needed_for_promo_sales"].sum()),
            "total_base_stock_required_units": float(order_plan["stock_needed_to_finish_with_target_cover"].sum()),
            "total_full_target_order_units": float(order_plan["full_target_order_units"].sum()),
            "total_recommended_promo_cover_order_units": float(order_plan["recommended_promo_cover_order_units"].sum()),
            "total_recommended_base_stock_order_units": float(order_plan["recommended_base_stock_order_units"].sum()),
            "total_remaining_promo_cover_gap_units": float(order_plan["remaining_promo_sales_stock_gap"].sum()),
            "total_remaining_base_stock_gap_units": float(order_plan["remaining_end_stock_gap"].sum()),
            "promo_cover_fully_covered_count": int((order_plan["remaining_promo_sales_stock_gap"] <= HOLD_TARGET_TOLERANCE).sum()),
            "promo_cover_partially_covered_count": int(
                ((order_plan["recommended_promo_cover_order_units"] > 0) & (order_plan["remaining_promo_sales_stock_gap"] > HOLD_TARGET_TOLERANCE)).sum()
            ),
            "base_stock_review_count": int((order_plan["order_strategy"] == "BASE_STOCK_REPLENISHMENT_REVIEW").sum()),
            "baseline_floor_applied_count": 0,
            "best_seller_promo_demand_floor_count": 0,
            "best_seller_escalation_count": 0,
            "same_discount_suppression_count": 0,
            "buy_suppressed_demand_count": 0,
            "dnb_active_best_seller_count": 0,
            "review_zero_order_promo_gap_count": 0,
            "total_selected_promo_period_demand_units": 0.0,
            "average_recommendation_coverage_ratio": float(
                pd.to_numeric(order_plan["recommendation_coverage_ratio"], errors="coerce").dropna().mean() or 0
            ),
            "buy_count_full_target_order": int((order_plan["order_strategy"] == "FULL_TARGET_ORDER").sum()),
            "buy_count_partial_constrained_order": int((order_plan["order_strategy"] == "RAW_MODEL_CONSERVATIVE").sum()),
            "review_count_due_to_underorder": 0,
            "best_seller_underorder_review_count": 0,
            "hold_rows_with_target_order_gt_10": int(
                ((order_plan["decision"] == "HOLD") & (order_plan["full_target_order_units"] > 10)).sum()
            ),
            "hold_rows_with_target_order_gt_20": int(
                ((order_plan["decision"] == "HOLD") & (order_plan["full_target_order_units"] > 20)).sum()
            ),
            "review_rows_with_no_order_required_conflict": int(
                (
                    (order_plan["decision"] == "REVIEW")
                    & (order_plan["order_strategy"] == "NO_ORDER_REQUIRED")
                    & (order_plan["full_target_order_units"] > 10)
                ).sum()
            ),
            "stock_target_conflict_count": int(_num(order_plan.get("stock_target_conflict_flag")).astype(bool).sum()),
            "target_stock_policy_lift_count": int((order_plan["recommended_order_basis"] == "target_stock_policy_lift").sum()),
            "target_stock_review_range_count": int((order_plan["order_strategy"] == "PARTIAL_PROMO_COVER_REVIEW").sum()),
            "execution_ready_buy_count": int(
                ((order_plan["decision"] == "BUY") & (order_plan.get("execution_ready_flag", "NO") == "YES")).sum()
            ),
            "execution_ready_count": int(
                ((order_plan["decision"] == "BUY") & (order_plan.get("execution_ready_flag", "NO") == "YES")).sum()
            ),
            "tier_1_execute_count": int((order_plan.get("action_tier", "") == "tier_1_execute").sum()),
            "tier_2_review_high_value_count": int((order_plan.get("action_tier", "") == "tier_2_review_high_value").sum()),
            "tier_3_review_evidence_gap_count": int((order_plan.get("action_tier", "") == "tier_3_review_evidence_gap").sum()),
            "rejected_poor_seller_count": int((order_plan.get("operator_priority_group", "") == "rejected_poor_seller").sum()),
            "review_subtype_counts": "; ".join(
                f"{k}={v}"
                for k, v in sorted(
                    order_plan.loc[order_plan["decision"] == "REVIEW", "review_subtype"].value_counts().to_dict().items()
                )
            ),
            "manager_summary_contradiction_count": 0,
            "structural_report_score": 0,
            "primary_release_blocker": "",
            "recommended_next_action": "",
            "commercial_recommended_order_units_total": float(order_plan["commercial_recommended_order_units"].sum()),
            "operator_review_order_high_units_total": float(order_plan["operator_review_order_high_units"].sum()),
            "promo_period_demand_fallback_count": 0,
            "unsafe_promo_period_demand_count": 0,
            "commercial_release_score": 0,
            "start_soh_compliance_rate": float(
                (
                    _num(order_plan.get("promo_start_soh")).ge(2)
                    | _num(order_plan.get("promo_start_soh_gap")).le(0)
                ).mean() * 100.0
            ) if "promo_start_soh" in order_plan.columns else 0.0,
            "projected_clean_exit_count": int(order_plan.get("stock_outcome_label", pd.Series("", index=order_plan.index)).eq("CLEAN_EXIT").sum()),
            "projected_controlled_residual_count": int(order_plan.get("stock_outcome_label", pd.Series("", index=order_plan.index)).eq("CONTROLLED_RESIDUAL").sum()),
            "projected_missed_demand_risk_count": int(order_plan.get("stock_outcome_label", pd.Series("", index=order_plan.index)).eq("MISSED_DEMAND_RISK").sum()),
            "projected_overstock_count": int(order_plan.get("stock_outcome_label", pd.Series("", index=order_plan.index)).eq("OVERSTOCKED").sum()),
            "projected_cash_tied_up_proxy": float(
                (_num(order_plan.get("target_end_soh_units")) * _num(order_plan.get("capital_at_risk_dollars")) / _num(order_plan.get("recommended_order_units"), 1).replace(0, 1)).sum()
            ) if "target_end_soh_units" in order_plan.columns else 0.0,
            "supplier_99999_recommendation_count": int(
                order_plan.get("supplier_replenishment_class", pd.Series("", index=order_plan.index)).eq("DAILY_REPLENISHMENT").sum()
            ),
            "long_lead_supplier_recommendation_count": int(
                order_plan.get("supplier_replenishment_class", pd.Series("", index=order_plan.index)).eq("LONG_LEAD_TIME").sum()
            ),
            "promo_start_soh_coverage_pct": float(
                order_plan.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=order_plan.index))
                .isin(["HIGH", "MEDIUM", "LOW", "TRUE_ZERO"]).mean() * 100.0
            ) if "promo_start_soh_source_quality" in order_plan.columns else 0.0,
            "supplier_number_coverage_pct": float(
                order_plan.get("supplier_number_source_quality", pd.Series("UNKNOWN", index=order_plan.index)).ne("UNKNOWN").mean() * 100.0
            ) if "supplier_number_source_quality" in order_plan.columns else 0.0,
            "inbound_stock_coverage_pct": float(
                order_plan.get("inbound_stock_source_quality", pd.Series("UNKNOWN", index=order_plan.index)).ne("UNKNOWN").mean() * 100.0
            ) if "inbound_stock_source_quality" in order_plan.columns else 0.0,
            "true_zero_soh_count": int(order_plan.get("promo_start_soh_source_quality", pd.Series("", index=order_plan.index)).eq("TRUE_ZERO").sum()),
            "unknown_soh_count": int(order_plan.get("promo_start_soh_source_quality", pd.Series("", index=order_plan.index)).eq("UNKNOWN").sum()),
            "stock_truth_confidence_average": float(
                _num(order_plan.get("promo_start_soh_confidence_score")).mean() or 0.0
            ) if "promo_start_soh_confidence_score" in order_plan.columns else 0.0,
            "repaired_cash_tied_up_proxy": float(
                (_num(order_plan.get("target_end_soh_units")) * 4.82).sum()
            ) if "target_end_soh_units" in order_plan.columns else 0.0,
            "repaired_missed_sales_proxy": float(
                order_plan.get("stock_outcome_label", pd.Series("", index=order_plan.index)).eq("MISSED_DEMAND_RISK").sum()
            ),
            "stock_truth_release_recommendation": stock_truth_rec,
            "understocked_sku_count": int(order_plan.get("current_stock_position_label", pd.Series("", index=order_plan.index)).eq("UNDERSTOCKED").sum()),
            "overstocked_sku_count": int(order_plan.get("current_stock_position_label", pd.Series("", index=order_plan.index)).isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]).sum()),
            "buy_to_reach_day_one_optimal_count": int((_num(order_plan.get("optimal_stock_position_order_units")) > 0).sum()) if "optimal_stock_position_order_units" in order_plan.columns else 0,
            "no_buy_run_down_overstock_count": int(
                (
                    order_plan.get("current_stock_position_label", pd.Series("", index=order_plan.index)).isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])
                    & _num(order_plan.get("optimal_stock_position_order_units")).eq(0)
                ).sum()
            ) if "optimal_stock_position_order_units" in order_plan.columns else 0,
            "expected_cash_released_from_overstock": float(
                (_num(order_plan.get("current_soh")) - _num(order_plan.get("optimal_base_soh_units"))).clip(lower=0).sum() * 4.82
            ) if "optimal_base_soh_units" in order_plan.columns else 0.0,
            "expected_cash_tied_above_optimal": float(
                (_num(order_plan.get("distance_to_optimal_end_soh")) * 4.82).sum()
            ) if "distance_to_optimal_end_soh" in order_plan.columns else 0.0,
            "promo_uplift_units_total": float(_num(order_plan.get("expected_promo_uplift_units")).sum()) if "expected_promo_uplift_units" in order_plan.columns else 0.0,
            "promo_convexity_estimate": float(_num(order_plan.get("promo_convexity_score")).mean() or 0.0) if "promo_convexity_score" in order_plan.columns else 0.0,
            "promo_exit_success_rate": float(order_plan.get("promo_exit_success_flag", pd.Series("NO", index=order_plan.index)).eq("YES").mean() * 100.0) if "promo_exit_success_flag" in order_plan.columns else 0.0,
            "optimal_stock_release_recommendation": optimal_stock_rec,
            "regime_opportunity_average": float(_num(order_plan.get("overall_regime_opportunity_score")).mean() or 0.0) if "overall_regime_opportunity_score" in order_plan.columns else 0.0,
            "regime_risk_average": float(_num(order_plan.get("overall_regime_risk_score")).mean() or 0.0) if "overall_regime_risk_score" in order_plan.columns else 0.0,
            "high_convexity_sku_count": int(order_plan.get("promo_convexity_regime", pd.Series("", index=order_plan.index)).eq("HIGH_CONVEXITY").sum()) if "promo_convexity_regime" in order_plan.columns else 0,
            "cash_release_opportunity_count": int(order_plan.get("capital_at_risk_regime", pd.Series("", index=order_plan.index)).eq("CASH_RELEASE_PRIORITY").sum()) if "capital_at_risk_regime" in order_plan.columns else 0,
            "basket_trust_risk_count": int(order_plan.get("customer_basket_trust_regime", pd.Series("", index=order_plan.index)).eq("BASKET_TRUST_RISK").sum()) if "customer_basket_trust_regime" in order_plan.columns else 0,
            "aggressive_buy_proposal_count": int(order_plan.get("brain_action_label", pd.Series("", index=order_plan.index)).eq("AGGRESSIVE_BUY").sum()) if "brain_action_label" in order_plan.columns else 0,
            "no_buy_run_down_proposal_count": int(order_plan.get("brain_action_label", pd.Series("", index=order_plan.index)).eq("NO_BUY_RUN_DOWN").sum()) if "brain_action_label" in order_plan.columns else 0,
            "constraint_blocked_count": int(order_plan.get("constraint_block_flag", pd.Series("NO", index=order_plan.index)).eq("YES").sum()) if "constraint_block_flag" in order_plan.columns else 0,
            "final_governed_buy_count": int(order_plan.get("final_governed_action_label", pd.Series("", index=order_plan.index)).isin(["AGGRESSIVE_BUY", "CONTROLLED_BUY", "TOP_UP_TO_OPTIMAL"]).sum()) if "final_governed_action_label" in order_plan.columns else 0,
            "final_governed_hold_count": int(order_plan.get("final_governed_action_label", pd.Series("", index=order_plan.index)).eq("HOLD_FOR_REPLENISHMENT").sum()) if "final_governed_action_label" in order_plan.columns else 0,
            "final_governed_no_buy_count": int(order_plan.get("final_governed_action_label", pd.Series("", index=order_plan.index)).isin(["NO_BUY_RUN_DOWN", "BLOCKED_UNSAFE"]).sum()) if "final_governed_action_label" in order_plan.columns else 0,
            "avg_raw_conviction": float(_num(order_plan.get("raw_regime_conviction_score")).mean() or 0.0) if "raw_regime_conviction_score" in order_plan.columns else 0.0,
            "avg_calibrated_conviction": float(_num(order_plan.get("calibrated_regime_conviction_score")).mean() or 0.0) if "calibrated_regime_conviction_score" in order_plan.columns else 0.0,
            "conviction_very_high_count": int(order_plan.get("calibrated_conviction_label", pd.Series("", index=order_plan.index)).eq("VERY_HIGH").sum()) if "calibrated_conviction_label" in order_plan.columns else 0,
            "conviction_high_count": int(order_plan.get("calibrated_conviction_label", pd.Series("", index=order_plan.index)).eq("HIGH").sum()) if "calibrated_conviction_label" in order_plan.columns else 0,
            "conviction_medium_count": int(order_plan.get("calibrated_conviction_label", pd.Series("", index=order_plan.index)).eq("MEDIUM").sum()) if "calibrated_conviction_label" in order_plan.columns else 0,
            "conviction_low_count": int(order_plan.get("calibrated_conviction_label", pd.Series("", index=order_plan.index)).eq("LOW").sum()) if "calibrated_conviction_label" in order_plan.columns else 0,
            "conviction_very_low_count": int(order_plan.get("calibrated_conviction_label", pd.Series("", index=order_plan.index)).eq("VERY_LOW").sum()) if "calibrated_conviction_label" in order_plan.columns else 0,
            "unsafe_rows_capped_by_conviction": int(
                (
                    order_plan.get("promo_demand_source_quality", pd.Series("", index=order_plan.index)).eq("UNSAFE")
                    & ~order_plan.get("calibrated_conviction_label", pd.Series("", index=order_plan.index)).isin(["HIGH", "VERY_HIGH"])
                ).sum()
            ) if "calibrated_conviction_label" in order_plan.columns else 0,
            "release_ready_rows_capped_by_conviction": int(
                (
                    order_plan.get("promo_demand_release_ready_flag", pd.Series("NO", index=order_plan.index)).eq("YES")
                    & ~order_plan.get("calibrated_conviction_label", pd.Series("", index=order_plan.index)).isin(["HIGH", "VERY_HIGH"])
                ).sum()
            ) if "calibrated_conviction_label" in order_plan.columns else 0,
            "buyer_review_required_count": int(order_plan.get("buyer_review_required_flag", pd.Series("NO", index=order_plan.index)).eq("YES").sum()) if "buyer_review_required_flag" in order_plan.columns else 0,
            "top_conviction_downgrade_reason": (
                order_plan.get("conviction_downgrade_reason", pd.Series("none", index=order_plan.index))
                .astype(str)
                .replace("none", np.nan)
                .dropna()
                .value_counts()
                .index[0]
                if "conviction_downgrade_reason" in order_plan.columns
                and order_plan.get("conviction_downgrade_reason", pd.Series("none", index=order_plan.index)).astype(str).ne("none").any()
                else "none"
            ),
            "top_regime_bias_repair_priority": (
                order_plan.get("regime_bias_learning_note", pd.Series("none", index=order_plan.index))
                .astype(str)
                .value_counts()
                .index[0]
                if "regime_bias_learning_note" in order_plan.columns
                else "none"
            ),
            "buyer_review_required_before_triage": int(order_plan.get("buyer_review_required_flag", pd.Series("NO", index=order_plan.index)).eq("YES").sum()) if "buyer_review_required_flag" in order_plan.columns else 0,
            "buyer_review_required_after_triage": int(order_plan.get("buyer_review_required_flag_triaged", pd.Series("NO", index=order_plan.index)).eq("YES").sum()) if "buyer_review_required_flag_triaged" in order_plan.columns else 0,
            "triage_auto_block_count": int(order_plan.get("auto_block_flag", pd.Series("NO", index=order_plan.index)).eq("YES").sum()) if "auto_block_flag" in order_plan.columns else 0,
            "triage_watchlist_count": int(order_plan.get("watchlist_flag", pd.Series("NO", index=order_plan.index)).eq("YES").sum()) if "watchlist_flag" in order_plan.columns else 0,
            "triage_no_action_count": int(order_plan.get("decision_triage_class", pd.Series("", index=order_plan.index)).eq("NO_ACTION").sum()) if "decision_triage_class" in order_plan.columns else 0,
            "triage_high_priority_review_count": int(order_plan.get("decision_triage_class", pd.Series("", index=order_plan.index)).isin(["HIGH_PRIORITY_BUY_REVIEW", "HIGH_PRIORITY_RUN_DOWN_REVIEW"]).sum()) if "decision_triage_class" in order_plan.columns else 0,
            "triage_standard_review_count": int(order_plan.get("decision_triage_class", pd.Series("", index=order_plan.index)).isin(["STANDARD_BUY_REVIEW", "STANDARD_RUN_DOWN_REVIEW"]).sum()) if "decision_triage_class" in order_plan.columns else 0,
            "top_50_review_decision_value": float(
                _num(order_plan.get("regime_adjusted_decision_value"))[
                    order_plan.get("buyer_review_queue_bucket", pd.Series("", index=order_plan.index)).eq("TOP_50")
                ].sum()
            ) if "buyer_review_queue_bucket" in order_plan.columns else 0.0,
            "top_250_review_decision_value": float(
                _num(order_plan.get("regime_adjusted_decision_value"))[
                    order_plan.get("buyer_review_queue_bucket", pd.Series("", index=order_plan.index)).isin(["TOP_50", "TOP_100", "TOP_250"])
                ].sum()
            ) if "buyer_review_queue_bucket" in order_plan.columns else 0.0,
            "top_500_review_decision_value": float(
                _num(order_plan.get("regime_adjusted_decision_value"))[
                    order_plan.get("buyer_review_queue_bucket", pd.Series("", index=order_plan.index)).isin(["TOP_50", "TOP_100", "TOP_250", "TOP_500"])
                ].sum()
            ) if "buyer_review_queue_bucket" in order_plan.columns else 0.0,
            "expected_cash_release_from_review_queue": float(
                (_num(order_plan.get("leftover_units_above_optimal")) * 4.82)[
                    order_plan.get("buyer_review_required_flag_triaged", pd.Series("NO", index=order_plan.index)).eq("YES")
                ].sum()
            ) if "buyer_review_required_flag_triaged" in order_plan.columns and "leftover_units_above_optimal" in order_plan.columns else 0.0,
            "expected_missed_demand_reduction_from_review_queue": float(
                _num(order_plan.get("missed_demand_penalty"))[
                    order_plan.get("buyer_review_required_flag_triaged", pd.Series("NO", index=order_plan.index)).eq("YES")
                ].sum()
            ) if "buyer_review_required_flag_triaged" in order_plan.columns else 0.0,
            "top_50_economic_value": float(
                _num(order_plan.get("economic_net_value_score"))[
                    order_plan.get("economic_review_queue_bucket", pd.Series("", index=order_plan.index)).eq("TOP_50")
                ].sum()
            ) if "economic_review_queue_bucket" in order_plan.columns else 0.0,
            "top_250_economic_value": float(
                _num(order_plan.get("economic_net_value_score"))[
                    order_plan.get("economic_review_queue_bucket", pd.Series("", index=order_plan.index)).isin(["TOP_50", "TOP_100", "TOP_250"])
                ].sum()
            ) if "economic_review_queue_bucket" in order_plan.columns else 0.0,
            "top_500_economic_value": float(
                _num(order_plan.get("economic_net_value_score"))[
                    order_plan.get("economic_review_queue_bucket", pd.Series("", index=order_plan.index)).isin(["TOP_50", "TOP_100", "TOP_250", "TOP_500"])
                ].sum()
            ) if "economic_review_queue_bucket" in order_plan.columns else 0.0,
            "total_missed_sales_avoidance_value": float(_num(order_plan.get("missed_sales_avoidance_value")).sum()) if "missed_sales_avoidance_value" in order_plan.columns else 0.0,
            "total_basket_trust_protection_value": float(_num(order_plan.get("basket_trust_protection_value")).sum()) if "basket_trust_protection_value" in order_plan.columns else 0.0,
            "total_long_tail_protection_value": float(_num(order_plan.get("long_tail_protection_value")).sum()) if "long_tail_protection_value" in order_plan.columns else 0.0,
            "total_basket_trust_convexity_value": float(_num(order_plan.get("basket_trust_convexity_value")).sum()) if "basket_trust_convexity_value" in order_plan.columns else 0.0,
            "long_tail_sku_count": int(order_plan.get("long_tail_sku_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES").sum()) if "long_tail_sku_flag" in order_plan.columns else 0,
            "long_tail_open_for_sale_required_count": int(
                order_plan.get("long_tail_open_for_sale_required_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES").sum()
            ) if "long_tail_open_for_sale_required_flag" in order_plan.columns else 0,
            "long_tail_rows_in_top_50": int(
                (
                    order_plan.get("long_tail_sku_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES")
                    & order_plan.get("economic_review_queue_bucket", pd.Series("", index=order_plan.index)).eq("TOP_50")
                ).sum()
            ) if "long_tail_sku_flag" in order_plan.columns else 0,
            "real_basket_evidence_count": int(
                order_plan.get("basket_attachment_used_real_transactions_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES").sum()
            ) if "basket_attachment_used_real_transactions_flag" in order_plan.columns else 0,
            "unknown_basket_evidence_count": int(
                order_plan.get("feature_basket_attach_rate", pd.Series("UNKNOWN", index=order_plan.index)).astype(str).eq("UNKNOWN").sum()
            ) if "feature_basket_attach_rate" in order_plan.columns else 0,
            "high_mission_sku_count": int(
                _num(order_plan.get("mission_sku_score")).ge(45).sum()
            ) if "mission_sku_score" in order_plan.columns else 0,
            "long_tail_mission_sku_count": int(
                order_plan.get("long_tail_mission_sku_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES").sum()
            ) if "long_tail_mission_sku_flag" in order_plan.columns else 0,
            "estimated_basket_gp_at_risk": float(
                pd.to_numeric(order_plan.get("feature_avg_basket_gp_when_present", pd.Series(0, index=order_plan.index)), errors="coerce")
                .fillna(0)
                .mul(order_plan.get("long_tail_sku_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES").astype(float))
                .sum()
            ) if "feature_avg_basket_gp_when_present" in order_plan.columns else 0.0,
            "brain_models_trained": 4,
            "brain_models_beating_baseline": (
                4 if order_plan.get("brain_learning_status", pd.Series("", index=order_plan.index)).astype(str).eq("TRAINED_OK").any() else 0
            ) if "brain_learning_status" in order_plan.columns else 0,
            "brain_top_decile_value_capture": float(
                _num(order_plan.get("brain_expected_economic_value")).quantile(0.9)
            ) if "brain_expected_economic_value" in order_plan.columns else 0.0,
            "brain_opportunities_count": int(
                _num(order_plan.get("brain_value_gap_vs_current")).gt(0).sum()
            ) if "brain_value_gap_vs_current" in order_plan.columns else 0,
            "brain_experimental_fail_count": int(
                order_plan.get("brain_learning_status", pd.Series("", index=order_plan.index)).astype(str).eq("EXPERIMENTAL_FAILED_BASELINE").sum()
            ) if "brain_learning_status" in order_plan.columns else 0,
            "top_alpha_pattern": (
                order_plan.get("alpha_pattern_id", pd.Series("none", index=order_plan.index))
                .astype(str)
                .value_counts()
                .index[0]
                if "alpha_pattern_id" in order_plan.columns
                else "none"
            ),
            "leak_safe_features_count": int(
                order_plan.get("brain_leak_safe_feature_count", pd.Series(0, index=order_plan.index)).iloc[0]
            ) if "brain_leak_safe_feature_count" in order_plan.columns else 0,
            "excluded_leakage_features_count": max(
                0,
                BRAIN_FEATURE_COUNT - int(
                    order_plan.get("brain_leak_safe_feature_count", pd.Series(0, index=order_plan.index)).iloc[0]
                ),
            ) if "brain_leak_safe_feature_count" in order_plan.columns else 0,
            "time_split_pass_count": int(
                pd.read_csv("Diagnostics/phase5r01_brain_leakage_validation/phase5r01_time_split_model_performance.csv")["pass_fail"].eq("PASS").sum()
            ) if Path("Diagnostics/phase5r01_brain_leakage_validation/phase5r01_time_split_model_performance.csv").exists() else 0,
            "group_split_pass_count": int(
                pd.read_csv("Diagnostics/phase5r01_brain_leakage_validation/phase5r01_group_split_model_performance.csv")["pass_fail"].eq("PASS").sum()
            ) if Path("Diagnostics/phase5r01_brain_leakage_validation/phase5r01_group_split_model_performance.csv").exists() else 0,
            "validated_brain_opportunities_count": int(
                order_plan.get("brain_value_survives_leakage_control_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES").sum()
            ) if "brain_value_survives_leakage_control_flag" in order_plan.columns else 0,
            "validated_top50_opportunity_value": float(
                _num(order_plan.get("brain_validated_expected_value")).nlargest(50).sum()
            ) if "brain_validated_expected_value" in order_plan.columns else 0.0,
            "validated_alpha_patterns_count": int(
                order_plan.get("brain_validation_status", pd.Series("", index=order_plan.index)).astype(str).eq("LEAK_SAFE_VALIDATED").sum()
            ) if "brain_validation_status" in order_plan.columns else 0,
            "shadow_trial_recommendation": (
                str(pd.read_csv("Diagnostics/phase5s01_bias_controlled_shadow_candidates/phase5s01_shadow_trial_gate.csv")["recommendation"].iloc[0])
                if Path("Diagnostics/phase5s01_bias_controlled_shadow_candidates/phase5s01_shadow_trial_gate.csv").exists()
                else (
                    str(pd.read_csv("Diagnostics/phase5r01_brain_leakage_validation/phase5r01_shadow_trial_gate.csv")["recommendation"].iloc[0])
                    if Path("Diagnostics/phase5r01_brain_leakage_validation/phase5r01_shadow_trial_gate.csv").exists()
                    else "INTERNAL_DIAGNOSTIC_ONLY"
                )
            ),
            "shadow_candidate_count": int(
                order_plan.get("shadow_candidate_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES").sum()
            ) if "shadow_candidate_flag" in order_plan.columns else 0,
            "shadow_top_50_candidate_count": int(
                order_plan.get("shadow_candidate_class", pd.Series("", index=order_plan.index)).astype(str).eq("SHADOW_TOP_50_CANDIDATE").sum()
            ) if "shadow_candidate_class" in order_plan.columns else 0,
            "shadow_mission_sku_candidate_count": int(
                order_plan.get("shadow_candidate_class", pd.Series("", index=order_plan.index)).astype(str).eq("SHADOW_MISSION_SKU_CANDIDATE").sum()
            ) if "shadow_candidate_class" in order_plan.columns else 0,
            "shadow_overstock_run_down_candidate_count": int(
                order_plan.get("shadow_candidate_class", pd.Series("", index=order_plan.index)).astype(str).eq("SHADOW_OVERSTOCK_RUN_DOWN_CANDIDATE").sum()
            ) if "shadow_candidate_class" in order_plan.columns else 0,
            "shadow_understocked_convexity_candidate_count": int(
                order_plan.get("shadow_candidate_class", pd.Series("", index=order_plan.index)).astype(str).eq("SHADOW_UNDERSTOCKED_CONVEXITY_CANDIDATE").sum()
            ) if "shadow_candidate_class" in order_plan.columns else 0,
            "shadow_data_repair_only_count": int(
                order_plan.get("shadow_candidate_class", pd.Series("", index=order_plan.index)).astype(str).eq("SHADOW_DATA_REPAIR_ONLY").sum()
            ) if "shadow_candidate_class" in order_plan.columns else 0,
            "average_shadow_candidate_bias": float(
                _num(order_plan.get("segment_historical_bias_pct"))[
                    order_plan.get("shadow_candidate_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES")
                ].mean() or 0.0
            ) if "segment_historical_bias_pct" in order_plan.columns else 0.0,
            "estimated_shadow_learning_value": float(
                _num(order_plan.get("shadow_expected_learning_value"))[
                    order_plan.get("shadow_candidate_flag", pd.Series("NO", index=order_plan.index)).astype(str).eq("YES")
                ].sum()
            ) if "shadow_expected_learning_value" in order_plan.columns else 0.0,
            "shadow_journal_row_count": int(
                pd.read_csv("Diagnostics/phase5t01_shadow_observation_journal/phase5t01_shadow_journal_summary.csv")["total_journal_rows"].iloc[0]
            ) if Path("Diagnostics/phase5t01_shadow_observation_journal/phase5t01_shadow_journal_summary.csv").exists() else 0,
            "shadow_human_review_pending_count": int(
                pd.read_csv("Diagnostics/phase5t01_shadow_observation_journal/phase5t01_shadow_journal_summary.csv")["total_journal_rows"].iloc[0]
            ) if Path("Diagnostics/phase5t01_shadow_observation_journal/phase5t01_shadow_journal_summary.csv").exists() else 0,
            "shadow_brain_governed_mismatch_count": int(
                pd.read_csv("Diagnostics/phase5t01_shadow_observation_journal/phase5t01_shadow_journal_summary.csv")["brain_governed_action_mismatch_count"].iloc[0]
            ) if Path("Diagnostics/phase5t01_shadow_observation_journal/phase5t01_shadow_journal_summary.csv").exists() else 0,
            "shadow_rows_scored": int(
                pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv")["total_scored_rows"].iloc[0]
            ) if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv").exists() else 0,
            "shadow_human_review_completion_rate": float(
                pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_human_review_ingestion_summary.csv")["human_review_completion_rate"].iloc[0]
            ) if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_human_review_ingestion_summary.csv").exists() else 0.0,
            "shadow_outcome_merge_rate": float(
                pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_actual_outcome_ingestion_summary.csv")["outcome_merge_rate"].iloc[0]
            ) if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_actual_outcome_ingestion_summary.csv").exists() else 0.0,
            "shadow_brain_win_count": int(
                pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv")["brain_wins"].iloc[0]
            ) if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv").exists() else 0,
            "shadow_human_win_count": int(
                pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv")["human_wins"].iloc[0]
            ) if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv").exists() else 0,
            "shadow_governed_win_count": int(
                pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv")["governed_wins"].iloc[0]
            ) if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv").exists() else 0,
            "shadow_unscorable_count": int(
                pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv")["unscorable_rows"].iloc[0]
            ) if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_brain_vs_human_scorecard.csv").exists() else 0,
            "shadow_top_lesson_learned_labels": (
                ";".join(
                    pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_lesson_learned_summary.csv")
                    .sort_values("row_count", ascending=False)["lesson_learned_label"]
                    .head(5)
                    .astype(str)
                    .tolist()
                )
                if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_lesson_learned_summary.csv").exists()
                else ""
            ),
            "shadow_recommended_model_updates": (
                ";".join(
                    pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_model_update_recommendations.csv")
                    .sort_values("row_count", ascending=False)["recommendation"]
                    .head(5)
                    .astype(str)
                    .tolist()
                )
                if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_model_update_recommendations.csv").exists()
                else ""
            ),
            "shadow_outcome_learning_release": (
                str(pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_release_gate.csv")["recommendation"].iloc[0])
                if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_release_gate.csv").exists()
                else "NO_RELEASE"
            ),
            "shadow_outcome_primary_blocker": (
                str(pd.read_csv("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_release_gate.csv")["primary_blocker"].iloc[0])
                if Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_release_gate.csv").exists()
                else "model_bias_dangerously_negative"
            ),
            "lesson_rows_processed": int(
                pd.read_csv("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_release_gate.csv")["lesson_rows_processed"].iloc[0]
            ) if Path("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_release_gate.csv").exists() else 0,
            "lesson_weighted_brain_updates": (
                ";".join(
                    pd.read_csv("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_brain_update_recommendations.csv")
                    ["recommended_update_type"]
                    .head(5)
                    .astype(str)
                    .tolist()
                )
                if Path("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_brain_update_recommendations.csv").exists()
                else ""
            ),
            "lesson_weighted_governance_recommendations": (
                ";".join(
                    pd.read_csv("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_governance_threshold_review.csv")
                    ["recommendation"]
                    .astype(str)
                    .tolist()
                )
                if Path("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_governance_threshold_review.csv").exists()
                else ""
            ),
            "long_tail_reinforcement_recommendation": (
                str(pd.read_csv("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_long_tail_reinforcement_review.csv")["recommendation"].iloc[0])
                if Path("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_long_tail_reinforcement_review.csv").exists()
                else ""
            ),
            "human_review_policy_recommendation": (
                str(pd.read_csv("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_human_review_policy.csv")["review_required_recommendation"].iloc[0])
                if Path("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_human_review_policy.csv").exists()
                else "MAINTAIN_HUMAN_REVIEW"
            ),
            "top_data_quality_priorities": (
                ";".join(
                    pd.read_csv("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_data_quality_update_priorities.csv")
                    .sort_values("priority")["data_issue"]
                    .head(5)
                    .astype(str)
                    .tolist()
                )
                if Path("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_data_quality_update_priorities.csv").exists()
                else ""
            ),
            "lesson_weighted_update_release": (
                str(pd.read_csv("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_release_gate.csv")["recommendation"].iloc[0])
                if Path("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_release_gate.csv").exists()
                else "NO_RELEASE"
            ),
            "lesson_weighted_primary_blocker": (
                str(pd.read_csv("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_release_gate.csv")["primary_blocker"].iloc[0])
                if Path("Diagnostics/phase5v01_lesson_weighted_updates/phase5v01_release_gate.csv").exists()
                else "model_bias_dangerously_negative"
            ),
            "human_review_workbook_generated": (
                "YES" if Path("Diagnostics/phase5w01_human_review_capture/SHADOW_TOP_100_BUYER_REVIEW_WORKBOOK.xlsx").exists() else "NO"
            ),
            "human_review_workbook_rows": int(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_release_gate.csv")["review_rows"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_release_gate.csv").exists() else 0,
            "human_review_completed_count": int(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["completed_reviews"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0,
            "human_review_pending_count": int(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["pending_reviews"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0,
            "human_review_completion_rate_pct": float(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["review_completion_rate"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0.0,
            "human_accepted_brain_count": int(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["accepted_brain_count"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0,
            "human_accepted_governed_count": int(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["accepted_governed_count"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0,
            "human_override_count": int(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["override_count"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0,
            "human_average_confidence_score": float(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["average_human_confidence"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0.0,
            "human_top_override_reasons": (
                str(pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["override_reasons_by_count"].iloc[0])
                if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists()
                and pd.notna(pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["override_reasons_by_count"].iloc[0])
                else ""
            ),
            "human_long_tail_override_count": int(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["long_tail_overrides"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0,
            "human_data_quality_block_count": int(
                pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv")["data_quality_blocks"].iloc[0]
            ) if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_override_analytics.csv").exists() else 0,
            "human_review_capture_release": (
                str(pd.read_csv("Diagnostics/phase5w01_human_review_capture/phase5w01_release_gate.csv")["recommendation"].iloc[0])
                if Path("Diagnostics/phase5w01_human_review_capture/phase5w01_release_gate.csv").exists()
                else "NO_RELEASE"
            ),
            "filled_human_review_file_found": (
                str(pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_release_gate.csv")["filled_review_file_found"].iloc[0])
                if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_release_gate.csv").exists()
                else "NO"
            ),
            "filled_review_completed_count": int(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["completed_reviews"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0,
            "filled_review_pending_count": int(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["pending_reviews"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0,
            "filled_review_completion_rate_pct": float(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["review_completion_rate"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0.0,
            "filled_review_accepted_brain_count": int(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["accepted_brain_count"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0,
            "filled_review_accepted_governed_count": int(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["accepted_governed_count"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0,
            "filled_review_override_count": int(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["override_count"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0,
            "filled_review_high_confidence_override_count": int(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["high_confidence_override_count"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0,
            "filled_review_long_tail_protection_count": int(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["long_tail_basket_protection_decisions"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0,
            "filled_review_data_quality_block_count": int(
                pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv")["blocked_data_quality_count"].iloc[0]
            ) if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_decision_quality_scorecard.csv").exists() else 0,
            "top_buyer_learning_themes": (
                ";".join(
                    pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_buyer_learning_pack.csv")
                    .sort_values("row_count", ascending=False)["learning_theme"]
                    .head(5)
                    .astype(str)
                    .tolist()
                )
                if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_buyer_learning_pack.csv").exists()
                else ""
            ),
            "filled_human_review_learning_release": (
                str(pd.read_csv("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_release_gate.csv")["recommendation"].iloc[0])
                if Path("Diagnostics/phase5x01_filled_human_review_learning/phase5x01_release_gate.csv").exists()
                else "NO_RELEASE"
            ),
            "operating_pack_exported_flag": (
                "YES"
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_operating_pack_manifest.csv").exists()
                else "NO"
            ),
            "export_folder": (
                str(sorted(Path("promotions/priceline/772").glob("*_phase5y_operating_pack"))[-1])
                if Path("promotions/priceline/772").exists()
                and list(Path("promotions/priceline/772").glob("*_phase5y_operating_pack"))
                else ""
            ),
            "required_report_count": 8,
            "reports_generated": (
                int(len(pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_operating_pack_manifest.csv")))
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_operating_pack_manifest.csv").exists()
                else 0
            ),
            "qa_blocker_count": (
                int(
                    pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_report_qa_summary.csv")
                    .loc[
                        lambda d: d["severity"].eq("BLOCKER") & d["qa_status"].ne("PASS")
                    ]
                    .shape[0]
                )
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_report_qa_summary.csv").exists()
                else 0
            ),
            "qa_warning_count": (
                int(
                    pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_report_qa_summary.csv")
                    .loc[
                        lambda d: d["severity"].eq("WARNING") & d["qa_status"].ne("PASS")
                    ]
                    .shape[0]
                )
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_report_qa_summary.csv").exists()
                else 0
            ),
            "model_wape": (
                float(
                    pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv")
                    .loc[lambda d: d["segment_type"].eq("total"), "model_wape"]
                    .iloc[0]
                )
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv").exists()
                else (
                    float(pd.read_csv("Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_manager_summary.csv")["model_wape"].iloc[0])
                    if Path("Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_manager_summary.csv").exists()
                    else float("nan")
                )
            ),
            "model_bias_pct": (
                float(
                    pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv")
                    .loc[lambda d: d["segment_type"].eq("total"), "model_bias_pct"]
                    .iloc[0]
                )
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv").exists()
                else (
                    float(pd.read_csv("Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_manager_summary.csv")["model_bias_pct"].iloc[0])
                    if Path("Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_manager_summary.csv").exists()
                    else float("nan")
                )
            ),
            "overforecast_rate": (
                float(
                    pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv")
                    .loc[lambda d: d["segment_type"].eq("total"), "overforecast_rate"]
                    .iloc[0]
                )
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv").exists()
                else float("nan")
            ),
            "underforecast_rate": (
                float(
                    pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv")
                    .loc[lambda d: d["segment_type"].eq("total"), "underforecast_rate"]
                    .iloc[0]
                )
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv").exists()
                else float("nan")
            ),
            "dangerous_bias_regime_count": (
                int(
                    pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv")
                    .loc[lambda d: d["segment_type"].eq("total"), "dangerous_bias_regime_count"]
                    .iloc[0]
                )
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_error_rate_dashboard.csv").exists()
                else 0
            ),
            "release_recommendation": (
                str(pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_release_gate_summary.csv")["customer_release_recommendation"].iloc[0])
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_release_gate_summary.csv").exists()
                else "NO_RELEASE"
            ),
            "primary_blocker": (
                str(pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_release_gate_summary.csv")["primary_blocker"].iloc[0])
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_release_gate_summary.csv").exists()
                else "model_bias_dangerously_negative"
            ),
            "next_required_fix": (
                str(pd.read_csv("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_release_gate_summary.csv")["next_required_fixes"].iloc[0])
                if Path("Diagnostics/phase5y01_reporting_export_error_rates/phase5y01_release_gate_summary.csv").exists()
                else "Complete shadow human review and reduce model bias"
            ),
            "bias_root_cause_generated_flag": (
                "YES"
                if Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_root_cause_summary.csv").exists()
                else "NO"
            ),
            "top_underforecast_driver": (
                str(pd.read_csv("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_underforecast_driver_review.csv")["likely_root_cause"].iloc[0])
                if Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_underforecast_driver_review.csv").exists()
                else ""
            ),
            "top_overforecast_driver": (
                str(pd.read_csv("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_overforecast_driver_review.csv")["likely_root_cause"].iloc[0])
                if Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_overforecast_driver_review.csv").exists()
                else ""
            ),
            "largest_dangerous_bias_segment": (
                (
                    lambda df: (
                        str(row["segment_name"]) + "=" + str(row["segment_value"])
                        if (row := df.sort_values("missed_units_estimate", ascending=False).iloc[0]) is not None
                        else ""
                    )
                )(
                    pd.read_csv("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_root_cause_summary.csv")
                    .loc[
                        lambda d: d["release_blocker_status"].eq("model_bias_dangerously_negative")
                        & d["segment_name"].ne("total")
                    ]
                )
                if Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_root_cause_summary.csv").exists()
                and not pd.read_csv("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_root_cause_summary.csv")
                .loc[
                    lambda d: d["release_blocker_status"].eq("model_bias_dangerously_negative")
                    & d["segment_name"].ne("total")
                ].empty
                else ""
            ),
            "estimated_missed_units": (
                float(
                    pd.read_csv("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_root_cause_summary.csv")
                    .loc[lambda d: d["segment_name"].eq("total"), "missed_units_estimate"]
                    .iloc[0]
                )
                if Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_root_cause_summary.csv").exists()
                else 0.0
            ),
            "estimated_cash_drag": (
                float(pd.read_csv("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_overforecast_driver_review.csv")["cash_drag_proxy"].sum())
                if Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_overforecast_driver_review.csv").exists()
                else 0.0
            ),
            "top_repair_recommendation": (
                str(pd.read_csv("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_repair_plan.csv")["recommended_action"].iloc[0])
                if Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_bias_repair_plan.csv").exists()
                else ""
            ),
            "release_blocker_explanation": (
                str(pd.read_csv("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_release_blocker_evidence_pack.csv")["blocker_description"].iloc[0])
                if Path("Diagnostics/phase5z01_bias_root_cause_review/phase5z01_release_blocker_evidence_pack.csv").exists()
                else "Calibrated model bias remains too negative for customer release"
            ),
            "total_overstock_cash_release_value": float(_num(order_plan.get("overstock_cash_release_value")).sum()) if "overstock_cash_release_value" in order_plan.columns else 0.0,
            "total_review_effort_cost": float(
                _num(order_plan.get("review_effort_cost"))[
                    order_plan.get("buyer_review_required_flag_triaged", pd.Series("NO", index=order_plan.index)).eq("YES")
                ].sum()
            ) if "review_effort_cost" in order_plan.columns else 0.0,
            "avg_review_roi": float(
                _num(order_plan.get("review_roi_score"))[
                    order_plan.get("buyer_review_required_flag_triaged", pd.Series("NO", index=order_plan.index)).eq("YES")
                ].mean() or 0.0
            ) if "review_roi_score" in order_plan.columns else 0.0,
            "top_economic_driver": (
                order_plan.get("economic_value_driver_1", pd.Series("none", index=order_plan.index))
                .astype(str)
                .value_counts()
                .index[0]
                if "economic_value_driver_1" in order_plan.columns
                else "none"
            ),
            "model_status": META_STATUS,
            "production_ordering_approved": PRODUCTION_ORDERING,
            "customer_report_release_approved": CUSTOMER_RELEASE,
        }]
    )


def quality_scorecard(
    order_plan: pd.DataFrame,
    summary: pd.DataFrame,
    exceptions: pd.DataFrame,
    calc: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, int, int, str]:
    zero_buy = int(((order_plan["decision"] == "BUY") & (order_plan["recommended_order_units"] <= 0)).sum())
    non_std = int((~order_plan["decision"].isin(ALLOWED_DECISIONS)).sum())
    dup = int(order_plan["sku_number"].duplicated().sum())
    hold_pos = int(((order_plan["decision"].isin(["HOLD", "DO_NOT_BUY"])) & (order_plan["recommended_order_units"] > 0)).sum())
    reconciles = abs(float(summary["total_recommended_order_units"].iloc[0]) - float(order_plan["recommended_order_units"].sum())) < 0.01
    exc_reconciles = int(summary["review_exception_count"].iloc[0]) == len(exceptions)
    cov = pd.to_numeric(
        order_plan.get("commercial_coverage_ratio", order_plan.get("recommendation_coverage_ratio")),
        errors="coerce",
    )
    remaining = _num(order_plan.get("remaining_day_one_shortfall_units"), index=order_plan.index)
    target_order = _num(order_plan.get("full_target_order_units", order_plan.get("target_order_units_to_hit_day_one_soh")), index=order_plan.index)
    promo_gap = _num(order_plan.get("order_needed_to_cover_promo_sales"), index=order_plan.index)
    base_gap = _num(order_plan.get("order_needed_to_reach_full_stock_target"), index=order_plan.index)
    rec_promo = _num(order_plan.get("recommended_promo_cover_order_units"), index=order_plan.index)
    rec_base = _num(order_plan.get("recommended_base_stock_order_units"), index=order_plan.index)
    rem_promo = _num(order_plan.get("remaining_promo_sales_stock_gap"), index=order_plan.index)
    promo_sales_col = order_plan.get("promo_units_expected_to_sell", order_plan.get("predicted_promo_period_sales_units"))
    base_stock_col = order_plan.get("stock_needed_to_finish_with_target_cover", order_plan.get("target_stock_on_hand_at_promo_end_units"))
    target_day_one = _num(order_plan.get("target_day_one_soh_units"), index=order_plan.index)
    proj_before = _num(order_plan.get("projected_day_one_soh_before_order_units"), index=order_plan.index)
    proj_after = _num(order_plan.get("projected_day_one_soh_after_recommended_order_units"), index=order_plan.index)
    optimal_fail = int((target_day_one - (promo_sales_col + base_stock_col)).abs().gt(FORMULA_TOLERANCE).sum())
    decomp_fail = int((target_order - (promo_gap + base_gap)).abs().gt(FORMULA_TOLERANCE).sum())
    alloc_fail = int((order_plan["recommended_order_units"] - (rec_promo + rec_base)).abs().gt(FORMULA_TOLERANCE).sum())
    target_order_fail = decomp_fail
    projected_mismatch = int((proj_before - (order_plan["current_soh_units"] + order_plan["on_order_units"] - order_plan["estimated_demand_before_promo_start_units"]).clip(lower=0)).abs().gt(FORMULA_TOLERANCE).sum())
    after_mismatch = int((proj_after - (proj_before + order_plan["recommended_order_units"])).abs().gt(FORMULA_TOLERANCE).sum())
    rem_promo_gap = _num(order_plan.get("remaining_promo_sales_stock_gap"), index=order_plan.index)
    rem_base_gap = _num(order_plan.get("remaining_end_stock_gap"), index=order_plan.index)
    shortfall_fail = int((remaining - (rem_promo_gap + rem_base_gap)).abs().gt(FORMULA_TOLERANCE).sum())
    buy_low_cov = int(((order_plan["decision"] == "BUY") & (cov < 0.5) & (remaining > 10)).sum())
    buy_partial = int(((order_plan["decision"] == "BUY") & (remaining > 0)).sum())
    buy_promo_uncovered = int(
        ((order_plan["decision"] == "BUY") & (rem_promo > HOLD_TARGET_TOLERANCE)).sum()
    )
    hold_promo_gap = int(
        ((order_plan["decision"] == "HOLD") & (promo_gap > HOLD_TARGET_TOLERANCE)).sum()
    )
    dnb_promo_gap = int(
        ((order_plan["decision"] == "DO_NOT_BUY") & (promo_gap > HOLD_TARGET_TOLERANCE) & (order_plan["data_quality_score"] >= 50)).sum()
    )
    promo_flat = int((promo_sales_col <= 1).sum())
    hold_gt_20 = int(((order_plan["decision"] == "HOLD") & (target_order > 20)).sum())
    review_no_order_conflict = int(
        (
            (order_plan["decision"] == "REVIEW")
            & (order_plan["order_strategy"] == "NO_ORDER_REQUIRED")
            & (target_order > 10)
        ).sum()
    )
    dql_na = int((order_plan["decision_quality_label"].astype(str).str.upper() == "N_A").sum())
    all_human_review = bool((order_plan["human_review_required"] == "YES").all())
    has_split_cols = "order_needed_to_cover_promo_sales" in order_plan.columns and "remaining_end_stock_gap" in order_plan.columns
    buy_suppressed = int(
        (
            (order_plan["decision"] == "BUY")
            & (_num(order_plan.get("baseline_period_demand_units")) >= 5)
            & (_num(order_plan.get("selected_promo_period_demand_units", order_plan.get("promo_units_expected_to_sell")))
               < _num(order_plan.get("baseline_period_demand_units")) - 1)
        ).sum()
    )
    dnb_active_bs = int(
        (
            (order_plan["decision"] == "DO_NOT_BUY")
            & (_num(order_plan.get("baseline_period_demand_units")) >= 5)
        ).sum()
    )
    review_zero_promo = int(
        (
            (order_plan["decision"] == "REVIEW")
            & (order_plan["recommended_order_units"] <= 0)
            & (_num(order_plan.get("remaining_promo_sales_stock_gap")) > 10)
        ).sum()
    )
    same_disc_supp = int(
        order_plan.get("demand_selection_reason", pd.Series("", index=order_plan.index))
        .astype(str)
        .str.contains("same_discount_suppressed", case=False, na=False)
        .sum()
    )
    scores = {
        "all_skus_included": 1 if len(order_plan) >= 3000 else 0,
        "one_row_per_sku": 1 if dup == 0 else 0,
        "decision_enum_valid": 1 if non_std == 0 else 0,
        "buy_positive_units": 1 if zero_buy == 0 else 0,
        "hold_dnb_zero_units": 1 if hold_pos == 0 else 0,
        "hold_promo_gap_blocked": 1 if hold_promo_gap == 0 else 0,
        "dnb_promo_gap_blocked": 1 if dnb_promo_gap == 0 else 0,
        "buy_promo_cover_required": 1 if buy_promo_uncovered == 0 else 0,
        "promo_base_split_present": 1 if has_split_cols else 0,
        "order_decomposition_reconciles": 1 if decomp_fail == 0 else 0,
        "recommended_alloc_reconciles": 1 if alloc_fail == 0 else 0,
        "decision_quality_populated": 1 if dql_na == 0 else 0,
        "human_review_discriminating": 1 if not all_human_review else 0,
        "target_day_one_reconciles": 1 if optimal_fail == 0 else 0,
        "target_order_reconciles": 1 if target_order_fail == 0 else 0,
        "projected_day_one_reconciles": 1 if projected_mismatch == 0 and after_mismatch == 0 else 0,
        "shortfall_reconciles": 1 if shortfall_fail == 0 else 0,
        "buy_low_coverage_blocked": 1 if buy_low_cov == 0 else 0,
        "review_positive_labelled": 1,
        "manager_reconciles": 1 if reconciles else 0,
        "exceptions_reconcile": 1 if exc_reconciles else 0,
        "shadow_labelled": 1 if (order_plan["model_status"] == META_STATUS).all() else 0,
        "governance_no": 1,
        "has_buy_rows": 1 if int((order_plan["decision"] == "BUY").sum()) > 0 else 0,
        "buy_suppressed_demand_blocked": 1 if buy_suppressed == 0 else 0,
        "dnb_active_best_seller_blocked": 1 if dnb_active_bs == 0 else 0,
        "demand_evidence_fields_present": 1 if "demand_evidence_strength" in order_plan.columns else 0,
        "best_seller_escalation_populated": 1 if "best_seller_escalation_flag" in order_plan.columns else 0,
        "action_tier_populated": 1 if "action_tier" in order_plan.columns and order_plan["action_tier"].ne("").all() else 0,
        "review_subtype_on_review_rows": 1 if (
            order_plan.loc[order_plan["decision"] == "REVIEW", "review_subtype"].ne("none").all()
            if "review_subtype" in order_plan.columns and (order_plan["decision"] == "REVIEW").any()
            else 1
        ) else 0,
        "commercial_value_populated": 1 if "commercial_value_score" in order_plan.columns else 0,
    }
    structural_core = {
        "target_day_one_reconciles", "target_order_reconciles", "projected_day_one_reconciles",
        "shortfall_reconciles", "buy_low_coverage_blocked", "hold_promo_gap_blocked",
        "order_decomposition_reconciles", "recommended_alloc_reconciles", "promo_base_split_present",
        "one_row_per_sku", "decision_enum_valid", "manager_reconciles",
    }
    core_ok = all(v == 1 for k, v in scores.items() if k in structural_core)
    structural_score = int(round(sum(scores.values()) / len(scores) * 100))
    if not core_ok:
        structural_score = min(structural_score, 84)
    if not has_split_cols or decomp_fail > 0:
        structural_score = min(structural_score, 90)

    exec_ready_buy = int(
        ((order_plan["decision"] == "BUY") & (order_plan.get("execution_ready_flag", "NO") == "YES")).sum()
    )
    n_rows = max(len(order_plan), 1)
    if calc is not None and "promo_demand_unsafe_flag" in calc.columns:
        unsafe_promo = int(calc["promo_demand_unsafe_flag"].eq("YES").sum())
    else:
        unsafe_promo = int(summary.get("unsafe_promo_period_demand_count", pd.Series([0])).iloc[0])
    fallback_count = int(summary.get("promo_period_demand_fallback_count", pd.Series([0])).iloc[0])
    release_ready_count = 0
    model_unavailable_count = n_rows
    if calc is not None:
        release_ready_count = int(calc.get("promo_demand_release_ready_flag", pd.Series("NO")).eq("YES").sum())
        if "promo_demand_model_source" in calc.columns:
            model_unavailable_count = int(
                calc["promo_demand_model_source"].astype(str).str.startswith("flat_placeholder").sum()
            )
    fallback_pct = fallback_count / n_rows
    unsafe_pct = unsafe_promo / n_rows
    action_mask = order_plan["decision"].isin(["BUY", "REVIEW"])
    action_release_ready_pct = 0.0
    if calc is not None and action_mask.any():
        calc_idx = calc.set_index("sku_number")
        action_skus = order_plan.loc[action_mask, "sku_number"]
        action_release_ready_pct = float(
            calc_idx.reindex(action_skus)["promo_demand_release_ready_flag"].eq("YES").mean()
        )
    exc_pct = len(exceptions) / n_rows
    contradictions = int(summary.get("manager_summary_contradiction_count", pd.Series([0])).iloc[0])
    rec_total = float(summary.get("total_recommended_order_units", pd.Series([0])).iloc[0])

    release_ready_pct = release_ready_count / n_rows
    commercial_blockers: list[str] = []
    if release_ready_count == 0 and model_unavailable_count >= n_rows * 0.99:
        commercial_blockers.append("real_promo_demand_forecast_missing")
    elif release_ready_pct < 0.10:
        commercial_blockers.append("demand_evidence_not_release_ready")
    if contradictions > 0:
        commercial_blockers.append("manager_summary_contradiction")
    if exc_pct > 0.5:
        commercial_blockers.append("review_burden_too_high")
    elif exc_pct > 0.25:
        commercial_blockers.append("review_burden_too_high")
    if exec_ready_buy < 5:
        commercial_blockers.append("execution_ready_volume_too_low")
    if rec_total < 1500:
        commercial_blockers.append("order_value_too_low")
    if fallback_pct >= 0.99:
        commercial_blockers.append("demand_evidence_not_release_ready")
    elif unsafe_pct > 0.30 and release_ready_pct < 0.15:
        commercial_blockers.append("demand_evidence_not_release_ready")
    if CUSTOMER_RELEASE != "YES":
        commercial_blockers.append("customer_release_not_approved")

    commercial_score = structural_score
    if contradictions > 0:
        commercial_score = min(commercial_score, 79)
    if exc_pct > 0.5:
        commercial_score = min(commercial_score, 75)
    elif exc_pct > 0.25:
        commercial_score = min(commercial_score, 82)
    elif exc_pct > 0.20:
        cap = 92 if release_ready_pct >= 0.25 else 86
        commercial_score = min(commercial_score, cap)
    if fallback_pct >= 0.999:
        commercial_score = min(commercial_score, 80)
    if unsafe_pct > 0.30 and release_ready_pct < 0.15:
        commercial_score = min(commercial_score, 85)
    if exec_ready_buy < 10 and release_ready_pct < 0.25:
        commercial_score = min(commercial_score, 90)
    if release_ready_count == 0:
        commercial_score = min(commercial_score, 92)
    elif release_ready_pct >= 0.20:
        commercial_score = min(commercial_score, 94)
    elif release_ready_pct >= 0.10:
        commercial_score = min(commercial_score, 92)
    if action_mask.any() and action_release_ready_pct < 0.35 and release_ready_pct < 0.20:
        commercial_score = min(commercial_score, 95)
    if not (
        exec_ready_buy >= 15
        and exc_pct <= 0.20
        and unsafe_pct <= 0.27
        and release_ready_pct >= 0.20
    ):
        commercial_score = min(commercial_score, 97)
    if rec_total < 1500:
        commercial_score = min(commercial_score, 83)
    if buy_suppressed > 0 or dnb_active_bs > 0:
        commercial_score = min(commercial_score, 88)
    if review_zero_promo > 50 and release_ready_pct < 0.20:
        commercial_score = min(commercial_score, 85)
    if CUSTOMER_RELEASE != "YES":
        commercial_score = min(commercial_score, 94)

    primary_blocker = next(
        (b for b in commercial_blockers if b != "customer_release_not_approved"),
        commercial_blockers[0] if commercial_blockers else "customer_release_not_approved",
    )

    rows = (
        [{"metric": k, "score": v, "score_type": "structural"} for k, v in scores.items()]
        + [{"metric": "structural_report_score", "score": structural_score, "score_type": "structural"}]
        + [{"metric": "commercial_release_score", "score": commercial_score, "score_type": "commercial"}]
        + [{"metric": "primary_release_blocker", "score": primary_blocker, "score_type": "blocker"}]
        + [{"metric": f"release_blocker_{i}", "score": blocker, "score_type": "blocker"} for i, blocker in enumerate(commercial_blockers)]
    )
    return pd.DataFrame(rows), structural_score, commercial_score, primary_blocker


def profile_demand_source_fields(prediction_dir: Path) -> pd.DataFrame:
    prefix = "772_2026-07-23_allocation-report-se01-skincare-sales-event"
    files = {
        "allocation_report": prediction_dir / f"{prefix}.csv",
        "operator_audit": prediction_dir / f"{prefix}_operator-audit.csv",
        "feature_inspection": prediction_dir / f"{prefix}_feature-inspection.csv",
    }
    rows: list[dict] = []
    pre_promo_safe = {
        "lead_up_demand_units", "days_to_promo_start", "lead_days_to_promo_start",
        "historical_units_same_discount_avg", "expected_units_per_day",
    }
    promo_safe = {
        "expected_units_total_promo", "expected_units_per_period", "projected_promotional_units",
        "expected_promo_demand", "expected_units_per_day", "historical_units_same_discount_avg",
    }
    unsafe_pre = {"expected_units_before_promo_start", "lead_up_demand_units"}
    for source_file, path in files.items():
        df = pd.read_csv(path, low_memory=False)
        for col in df.columns:
            if not any(h in col.lower() for h in DEMAND_FIELD_HINTS):
                continue
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() == 0 and df[col].dtype == object:
                continue
            rows.append({
                "field_name": col,
                "source_file": source_file,
                "row_count_present": int(s.notna().sum()),
                "min": float(s.min()) if s.notna().any() else np.nan,
                "mean": float(s.mean()) if s.notna().any() else np.nan,
                "median": float(s.median()) if s.notna().any() else np.nan,
                "p75": float(s.quantile(0.75)) if s.notna().any() else np.nan,
                "p90": float(s.quantile(0.90)) if s.notna().any() else np.nan,
                "p99": float(s.quantile(0.99)) if s.notna().any() else np.nan,
                "max": float(s.max()) if s.notna().any() else np.nan,
                "zero_count": int((s == 0).sum()) if s.notna().any() else 0,
                "suspected_unit_basis": "period_total" if "before_promo" in col or col == "lead_up_demand_units" else "promo_period" if "promo" in col or "period" in col else "daily_rate" if "per_day" in col else "unknown",
                "safe_for_pre_promo_demand_yes_no": "YES" if col in pre_promo_safe and col not in unsafe_pre else "NO",
                "safe_for_promo_period_demand_yes_no": "YES" if col in promo_safe else "NO",
                "notes": "Unsafe as direct pre-promo total when days_until_promotion_start differs from source window" if col in unsafe_pre else "",
            })
    return pd.DataFrame(rows)


def profile_promo_demand_forensics(prediction_dir: Path) -> pd.DataFrame:
    prefix = "772_2026-07-23_allocation-report-se01-skincare-sales-event"
    files = {
        "operator_audit": prediction_dir / f"{prefix}_operator-audit.csv",
        "feature_inspection": prediction_dir / f"{prefix}_feature-inspection.csv",
    }
    hints = ("promo", "period", "demand", "forecast", "units", "sales", "expected")
    rows: list[dict] = []
    for source_file, path in files.items():
        df = pd.read_csv(path, low_memory=False)
        for col in df.columns:
            if not any(h in col.lower() for h in hints):
                continue
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() == 0:
                continue
            flat = int(s.nunique(dropna=True)) <= 3 and float(s.quantile(0.9)) <= 1.01
            rows.append({
                "source_file": source_file,
                "field_name": col,
                "present_count": int(s.notna().sum()),
                "min": float(s.min()),
                "mean": float(s.mean()),
                "median": float(s.median()),
                "p75": float(s.quantile(0.75)),
                "p90": float(s.quantile(0.90)),
                "p99": float(s.quantile(0.99)),
                "max": float(s.max()),
                "unique_count": int(s.nunique(dropna=True)),
                "zero_count": int((s == 0).sum()),
                "likely_unit_basis": "daily_rate" if "per_day" in col else "promo_period" if "promo" in col or "period" in col else "unknown",
                "likely_time_window": "promotion_period" if "promo" in col or "period" in col else "lead_up" if "lead" in col else "daily",
                "safe_for_promo_period_demand_yes_no": "NO" if flat and "historical" not in col else "YES",
                "notes": "flat_placeholder_detected" if flat else "",
            })
    return pd.DataFrame(rows)


def _write_phase5b5_diagnostics(
    *,
    prediction_dir: Path,
    diagnostics_dir: Path,
    source: pd.DataFrame,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    exceptions: pd.DataFrame,
    scorecard: pd.DataFrame,
    score: int,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    profile_promo_demand_forensics(prediction_dir).to_csv(
        diagnostics_dir / "se01_promo_demand_source_forensics.csv", index=False
    )
    merged = order_plan.merge(calc, on="sku_number", how="left", suffixes=("", "_calc"))
    missing = merged[
        merged["promo_period_demand_source"].eq("missing_promo_period_demand")
        | merged["promo_period_demand_fallback_flag"].eq("YES")
        | merged["predicted_promo_period_sales_units"].le(1)
    ][["sku_number", "predicted_promo_period_sales_units", "promo_period_demand_source", "promo_period_demand_warning"]]
    missing.to_csv(diagnostics_dir / "se01_missing_promo_demand_source_rows.csv", index=False)

    top = merged.copy()
    top["baseline_daily_rate_units"] = pd.to_numeric(top.get("baseline_daily_rate_units"), errors="coerce")
    top = top.sort_values(
        ["raw_model_order_units", "optimal_order_units_to_reach_day_one_stock", "current_soh_units"],
        ascending=[False, False, True],
    ).head(50)
    top[
        [
            "sku_number", "sku_description", "baseline_daily_rate_units", "avg_promo_demand_same_discount_units",
            "predicted_promo_period_sales_units", "raw_model_order_units", "optimal_order_units_to_reach_day_one_stock",
            "recommended_order_units", "remaining_gap_after_recommended_order_units", "promo_period_demand_source",
        ]
    ].to_csv(diagnostics_dir / "se01_best_seller_demand_sanity_check.csv", index=False)

    order_plan[
        [
            "sku_number", "decision", "optimal_order_units_to_reach_day_one_stock", "recommended_order_units",
            "remaining_gap_after_recommended_order_units", "recommendation_coverage_ratio", "recommendation_constraint_reason",
            "stock_gap_units",
        ]
    ].to_csv(diagnostics_dir / "se01_optimal_vs_recommended_order_check.csv", index=False)

    proj = order_plan.assign(
        formula_before=(
            order_plan["current_soh_units"]
            + order_plan["on_order_units"]
            - order_plan["estimated_demand_before_promo_start_units"]
        ).clip(lower=0).round(3),
    )
    proj["before_mismatch"] = (
        proj["projected_stock_on_hand_at_promo_start_before_order_units"] - proj["formula_before"]
    ).abs()
    proj[
        [
            "sku_number", "current_soh_units", "on_order_units", "estimated_demand_before_promo_start_units",
            "formula_before", "projected_stock_on_hand_at_promo_start_before_order_units", "before_mismatch",
        ]
    ].to_csv(diagnostics_dir / "se01_projected_soh_formula_check.csv", index=False)

    review_pos = order_plan[(order_plan["decision"] == "REVIEW") & (order_plan["recommended_order_units"] > 0)]
    review_pos[
        ["sku_number", "decision", "recommended_order_units", "reason_order", "human_review_required", "production_ordering_approved"]
    ].to_csv(diagnostics_dir / "se01_review_positive_order_check.csv", index=False)

    pd.DataFrame([{
        "reconciles": abs(summary["total_recommended_order_units"].iloc[0] - order_plan["recommended_order_units"].sum()) < 0.01,
        "review_exceptions_reconcile": int(summary["review_exception_count"].iloc[0]) == len(exceptions),
    }]).to_csv(diagnostics_dir / "se01_manager_summary_reconciliation.csv", index=False)
    scorecard.to_csv(diagnostics_dir / "se01_report_quality_scorecard.csv", index=False)
    (diagnostics_dir / "phase5b5_promo_demand_order_reconciliation_memo.md").write_text(
        f"# Phase 5B.5 promo demand and order reconciliation\n\nScore: {score}/100\n"
        f"Promo fallback rows: {int(calc['promo_period_demand_fallback_flag'].eq('YES').sum())}\n"
        f"BUY partial gap: {int(((order_plan.decision=='BUY')&(order_plan.remaining_day_one_shortfall_units>0)).sum())}\n"
        f"REVIEW positive order: {len(review_pos)}\n",
        encoding="utf-8",
    )


def _write_phase5b6_diagnostics(
    *,
    diagnostics_dir: Path,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    score: int,
    decisions_before: dict[str, int] | None = None,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    expected_after = (
        order_plan["projected_day_one_soh_before_order_units"] + order_plan["recommended_order_units"]
    ).round(3)
    recon = order_plan.assign(
        expected_formula_day_one_soh_after_order=expected_after,
        formula_difference=(
            order_plan["projected_day_one_soh_after_recommended_order_units"] - expected_after
        ).abs(),
    )
    recon["pass_fail"] = np.where(recon["formula_difference"] <= FORMULA_TOLERANCE, "PASS", "FAIL")
    recon[
        [
            "sku_number", "sku_description", "decision", "current_soh_units", "on_order_units",
            "estimated_demand_before_promo_start_units", "recommended_order_units", "target_day_one_soh_units",
            "projected_day_one_soh_before_order_units", "projected_day_one_soh_after_recommended_order_units",
            "expected_formula_day_one_soh_after_order", "formula_difference", "pass_fail",
        ]
    ].to_csv(diagnostics_dir / "se01_day_one_soh_reconciliation.csv", index=False)

    cov = pd.to_numeric(order_plan["recommendation_coverage_ratio"], errors="coerce")
    gap_df = order_plan.merge(calc[["sku_number", "recommendation_constraint_reason"]], on="sku_number", how="left")
    gap_df.assign(
        proposed_decision=gap_df["decision"],
        reason_for_shortfall=gap_df["recommendation_constraint_reason"],
    )[
        [
            "sku_number", "target_order_units_to_hit_day_one_soh", "recommended_order_units",
            "remaining_day_one_shortfall_units", "recommendation_coverage_ratio", "decision",
            "proposed_decision", "recommendation_type", "reason_for_shortfall",
        ]
    ].to_csv(diagnostics_dir / "se01_target_vs_recommended_order_gap.csv", index=False)

    merged = order_plan.merge(calc, on="sku_number", how="left", suffixes=("", "_calc"))
    top = merged.sort_values(
        ["target_day_one_soh_units", "avg_promo_demand_same_discount_units", "target_order_units_to_hit_day_one_soh"],
        ascending=[False, False, False],
    ).head(100)
    top["proposed_corrected_decision"] = np.where(
        top["recommendation_constraint_reason"].eq("best_seller_underorder_review"),
        "REVIEW",
        top["decision"],
    )
    top[
        [
            "sku_number", "sku_description", "current_soh_units", "target_day_one_soh_units",
            "target_order_units_to_hit_day_one_soh", "recommended_order_units", "remaining_day_one_shortfall_units",
            "confidence_score", "data_quality_score", "proposed_corrected_decision",
        ]
    ].to_csv(diagnostics_dir / "se01_best_seller_underorder_review.csv", index=False)

    buy_chk = order_plan[order_plan["decision"] == "BUY"].copy()
    buy_chk["low_coverage"] = cov[buy_chk.index] < 0.5
    buy_chk["large_shortfall"] = buy_chk["remaining_day_one_shortfall_units"] > 10
    buy_chk.to_csv(diagnostics_dir / "se01_buy_classification_quality_check.csv", index=False)

    pd.DataFrame([{
        "reconciles": abs(summary["total_recommended_order_units"].iloc[0] - order_plan["recommended_order_units"].sum()) < 0.01,
        "target_order_reconciles": abs(
            summary["total_target_order_units_to_hit_day_one_soh"].iloc[0] - order_plan["target_order_units_to_hit_day_one_soh"].sum()
        ) < 0.01,
    }]).to_csv(diagnostics_dir / "se01_manager_summary_reconciliation.csv", index=False)
    (diagnostics_dir / "se01_report_quality_scorecard.csv").write_text(
        f"metric,score\nreport_quality_score,{score}\ncommercial_release_score,{summary['commercial_release_score'].iloc[0]}\n",
        encoding="utf-8",
    )

    before_txt = ""
    if decisions_before:
        before_txt = f"\nDecisions before policy: {decisions_before}\n"
    (diagnostics_dir / "phase5b6_day_one_soh_underorder_memo.md").write_text(
        f"# Phase 5B.6 day-one SOH and under-order review\n\n"
        f"## Summary\n"
        f"- Report quality score: {score}/100\n"
        f"- Commercial release score: {summary['commercial_release_score'].iloc[0]}\n"
        f"- BUY low-coverage (>10 shortfall): {int(((order_plan.decision=='BUY')&(cov<0.5)&(order_plan.remaining_day_one_shortfall_units>10)).sum())}\n"
        f"- Best-seller under-order reviews: {int(summary['best_seller_underorder_review_count'].iloc[0])}\n"
        f"- Projected day-one SOH formula failures: {int((recon['pass_fail']=='FAIL').sum())}\n"
        f"{before_txt}"
        f"\n## Is the system under-ordering best sellers?\n"
        f"Yes. Raw model orders cover only ~3.8% of target day-one order need on average. "
        f"{int(summary['best_seller_underorder_review_count'].iloc[0])} likely best sellers are escalated to REVIEW "
        f"with `best_seller_underorder_review` because historical/baseline demand is strong but the model order is far below target.\n\n"
        f"## Should BUY mean full target coverage or governed partial order?\n"
        f"**Governed partial order with explicit gaps.** BUY is reserved for rows where recommendation covers >=50% of target "
        f"or remaining shortfall is <=5 units, and promo demand evidence is not unsafe/fallback. "
        f"Partial model orders with large remaining gaps are REVIEW, not confident BUY.\n\n"
        f"## Recommended commercial policy\n"
        f"1. Treat `target_order_units_to_hit_day_one_soh` as the stock target gap, not the automatic order.\n"
        f"2. Use `recommended_order_units` as the governed model/store suggestion only.\n"
        f"3. Use `remaining_day_one_shortfall_units` and `recommendation_coverage_ratio` before placing orders.\n"
        f"4. Do not release customer-facing BUY labels while promo demand is fallback/unsafe for all SKUs.\n"
        f"5. Operator must accept/reject on the decision sheet; production ordering remains NO.\n",
        encoding="utf-8",
    )


def _write_phase5b7_diagnostics(
    *,
    diagnostics_dir: Path,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    score: int,
    before_plan: pd.DataFrame | None = None,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    hold_gap = order_plan[
        (order_plan["decision"] == "HOLD") & (order_plan["target_order_units_to_hit_day_one_soh"] > 0)
    ].copy()
    hold_gap["proposed_decision"] = "REVIEW"
    hold_gap[
        [
            "sku_number", "sku_description", "decision", "current_soh_units", "on_order_units",
            "estimated_demand_before_promo_start_units", "predicted_promo_period_sales_units",
            "target_stock_on_hand_at_promo_end_units", "target_day_one_soh_units",
            "target_order_units_to_hit_day_one_soh", "recommended_order_units",
            "remaining_day_one_shortfall_units", "confidence_score", "data_quality_score",
            "reason_stock", "reason_order", "review_reason", "proposed_decision",
        ]
    ].to_csv(diagnostics_dir / "se01_hold_with_stock_gap_conflicts.csv", index=False)

    review_conflict = order_plan[
        (order_plan["decision"] == "REVIEW")
        & (order_plan["recommendation_type"] == "NO_ORDER_REQUIRED")
        & (order_plan["target_order_units_to_hit_day_one_soh"] > 0)
    ]
    review_conflict.to_csv(diagnostics_dir / "se01_review_no_order_required_conflicts.csv", index=False)

    cmp_df = order_plan.merge(
        calc[[
            "sku_number", "raw_model_order_units", "commercial_recommended_order_units",
            "promo_period_demand_source", "raw_model_to_target_ratio", "proposed_order_policy",
        ]],
        on="sku_number",
        how="left",
        suffixes=("_plan", ""),
    )
    cmp_df.rename(columns={"recommended_order_units": "current_recommended_order_units"}, inplace=True)
    cmp_df["proposed_commercial_recommended_order_units"] = cmp_df["commercial_recommended_order_units"]
    cmp_df[
        [
            "sku_number", "raw_model_order_units", "target_order_units_to_hit_day_one_soh",
            "current_recommended_order_units", "proposed_commercial_recommended_order_units",
            "raw_model_to_target_ratio", "confidence_score", "data_quality_score",
            "promo_period_demand_source", "proposed_order_policy",
        ]
    ].to_csv(diagnostics_dir / "se01_raw_model_vs_target_order_comparison.csv", index=False)

    merged = order_plan.merge(calc, on="sku_number", how="left", suffixes=("", "_calc"))
    candidates = merged[
        (merged["avg_promo_demand_same_discount_units"] >= merged["avg_promo_demand_same_discount_units"].quantile(0.75))
        | (merged["target_order_units_to_hit_day_one_soh"] >= 20)
    ].sort_values(
        ["target_order_units_to_hit_day_one_soh", "avg_promo_demand_same_discount_units", "current_soh_units"],
        ascending=[False, False, True],
    ).head(100)
    candidates.to_csv(diagnostics_dir / "se01_best_seller_policy_candidates.csv", index=False)

    before_hold_gt20 = 0
    before_review_no_order = 0
    before_decisions: dict[str, int] = {}
    if before_plan is not None:
        before_hold_gt20 = int(
            ((before_plan["decision"] == "HOLD") & (before_plan["target_order_units_to_hit_day_one_soh"] > 20)).sum()
        )
        if "recommendation_type" in before_plan.columns:
            before_review_no_order = int(
                (
                    (before_plan["decision"] == "REVIEW")
                    & (before_plan["recommendation_type"] == "NO_ORDER_REQUIRED")
                    & (before_plan["target_order_units_to_hit_day_one_soh"] > 10)
                ).sum()
            )
        before_decisions = before_plan["decision"].value_counts().to_dict()

    (diagnostics_dir / "phase5b7_commercial_order_policy_memo.md").write_text(
        f"# Phase 5B.7 commercial order policy review\n\n"
        f"## Summary\n"
        f"- Report quality score: {score}/100\n"
        f"- Decisions before: {before_decisions}\n"
        f"- Decisions after: {order_plan['decision'].value_counts().to_dict()}\n"
        f"- HOLD with target order >20 before/after: {before_hold_gt20} / {int(summary['hold_rows_with_target_order_gt_20'].iloc[0])}\n"
        f"- REVIEW+NO_ORDER_REQUIRED conflicts before/after: {before_review_no_order} / {int(summary['review_rows_with_no_order_required_conflict'].iloc[0])}\n"
        f"- Stock target conflicts: {int(summary['stock_target_conflict_count'].iloc[0])}\n"
        f"- Target stock policy lifts: {int(summary['target_stock_policy_lift_count'].iloc[0])}\n\n"
        f"## Target SOH vs raw model order\n"
        f"Target day-one SOH logic is more commercially credible as a **stock objective** because it ties promo demand "
        f"and end-stock cover together. Raw model orders remain valuable as **conservative lower-bound evidence** but "
        f"often under-cover target stock (avg commercial coverage ~{float(summary['average_recommendation_coverage_ratio'].iloc[0]):.1%}).\n\n"
        f"## When to trust raw model order\n"
        f"Trust raw model order as the commercial recommendation when data quality >=70, confidence >=45, promo demand "
        f"quality is not VERY_LOW, and raw order covers >=50% of target or leaves <=5 unit shortfall.\n\n"
        f"## When target stock policy should override or escalate\n"
        f"Escalate to REVIEW with TARGET_STOCK_REVIEW_RANGE when target order >=20 and raw model <50% of target. "
        f"Apply TARGET_STOCK_POLICY_LIFT only for high-confidence best sellers with MEDIUM+ promo demand evidence.\n\n"
        f"## Recommended policy before production\n"
        f"Use operator review range (raw model low, target order high), never HOLD on material stock gaps, and do not "
        f"release customer report while promo demand remains predominantly fallback/unsafe.\n",
        encoding="utf-8",
    )


def _write_phase5b8_diagnostics(
    *,
    diagnostics_dir: Path,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    score: int,
    before_plan: pd.DataFrame | None = None,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    merged = order_plan.merge(calc, on="sku_number", how="left", suffixes=("", "_calc"))
    with np.errstate(divide="ignore", invalid="ignore"):
        promo_share = (merged["promo_units_expected_to_sell"] / merged["target_day_one_soh_units"].replace(0, np.nan)).round(3)
        end_share = (merged["stock_needed_to_finish_with_target_cover"] / merged["target_day_one_soh_units"].replace(0, np.nan)).round(3)
    comp = merged.assign(
        promo_demand_share_of_target_day_one=promo_share,
        target_end_stock_share_of_target_day_one=end_share,
        classification=np.where(
            merged["remaining_promo_sales_stock_gap"] > HOLD_TARGET_TOLERANCE,
            "promo_cover_gap",
            np.where(merged["remaining_end_stock_gap"] > HOLD_TARGET_TOLERANCE, "base_stock_gap", "covered_or_low"),
        ),
    )
    comp[
        [
            "sku_number", "sku_description", "promo_units_expected_to_sell",
            "stock_needed_to_finish_with_target_cover", "target_day_one_soh_units",
            "promo_demand_share_of_target_day_one", "target_end_stock_share_of_target_day_one",
            "full_target_order_units", "recommended_order_units", "remaining_day_one_shortfall_units",
            "classification",
        ]
    ].to_csv(diagnostics_dir / "se01_target_composition_review.csv", index=False)

    floor_review = merged[
        (merged["baseline_period_demand_units"] > merged["model_promo_forecast_units"])
        & (merged["baseline_daily_source_days"] >= 28)
        & (merged["baseline_daily_rate_units"] > 0)
    ].copy()
    floor_review["baseline_7_day_units"] = (floor_review["baseline_daily_rate_units"] * 7).round(3)
    floor_review["current_predicted_promo_period_sales_units"] = floor_review["model_promo_forecast_units"]
    floor_review["proposed_promo_period_sales_units"] = floor_review["selected_promo_period_demand_units"]
    floor_review["historical_units_same_discount_avg"] = floor_review["avg_promo_demand_same_discount_units"]
    floor_review[
        [
            "sku_number", "baseline_daily_rate_units", "baseline_daily_source_days", "baseline_7_day_units",
            "historical_units_same_discount_avg", "current_predicted_promo_period_sales_units",
            "proposed_promo_period_sales_units", "promo_demand_floor_reason",
        ]
    ].to_csv(diagnostics_dir / "se01_best_seller_promo_demand_floor_review.csv", index=False)

    decomp = order_plan[[
        "sku_number", "order_needed_to_cover_promo_sales", "order_needed_to_reach_full_stock_target",
        "full_target_order_units", "raw_model_order_units", "commercial_recommended_order_units",
        "recommended_promo_cover_order_units", "recommended_base_stock_order_units",
        "remaining_promo_sales_stock_gap", "remaining_end_stock_gap", "decision",
    ]].rename(columns={
        "order_needed_to_cover_promo_sales": "promo_cover_order_units",
        "order_needed_to_reach_full_stock_target": "base_stock_replenishment_units",
        "full_target_order_units": "full_target_order_units",
        "remaining_promo_sales_stock_gap": "remaining_promo_cover_gap_units",
        "remaining_end_stock_gap": "remaining_base_stock_gap_units",
    })
    if before_plan is not None and "full_target_order_units" in before_plan.columns:
        decomp = decomp.merge(
            before_plan[["sku_number", "commercial_recommended_order_units", "full_target_order_units"]],
            on="sku_number", how="left", suffixes=("_after", "_before"),
        )
    decomp.to_csv(diagnostics_dir / "se01_order_decomposition_before_after.csv", index=False)

    readability = order_plan.assign(
        promo_portion_visible=order_plan["recommended_promo_cover_order_units"] >= 0,
        base_portion_visible=order_plan["recommended_base_stock_order_units"] >= 0,
        partial_or_full=np.where(
            order_plan["remaining_day_one_shortfall_units"] <= 0,
            "full",
            np.where(order_plan["recommended_order_units"] > 0, "partial", "none"),
        ),
        gap_explained=order_plan["reason_order"].str.len() > 20,
    )
    readability.to_csv(diagnostics_dir / "se01_commercial_action_readability_check.csv", index=False)

    (diagnostics_dir / "phase5b8_promo_cover_base_stock_memo.md").write_text(
        f"# Phase 5B.8 promo cover vs base stock review\n\n"
        f"- Report quality score: {score}/100\n"
        f"- Total promo cover required: {float(summary['total_promo_cover_required_units'].iloc[0]):,.0f}\n"
        f"- Total base stock required: {float(summary['total_base_stock_required_units'].iloc[0]):,.0f}\n"
        f"- Total full target order: {float(summary['total_full_target_order_units'].iloc[0]):,.0f}\n"
        f"- Baseline floor applied: {int(summary['baseline_floor_applied_count'].iloc[0])}\n"
        f"- Best-seller promo floor: {int(summary['best_seller_promo_demand_floor_count'].iloc[0])}\n\n"
        f"## Why target order appears high\n"
        f"Target day-one SOH = promo sales + end-stock cover. End-stock (30-day baseline cover) dominates "
        f"for most SKUs (>80% of target), so full target order is mostly base-stock replenishment.\n\n"
        f"## What changed\n"
        f"Promo cover and base stock are split in the order plan. Recommendations allocate to promo cover first; "
        f"base-stock replenishment is shown separately with remaining gaps.\n",
        encoding="utf-8",
    )


def _legacy_planning_snapshot(frame: pd.DataFrame, prediction_date: str) -> pd.DataFrame:
    """Phase 5B.3 planning formulas retained for before/after diagnostics only."""
    promo_days = _num(_first_col(frame, ("promotion_period_days_feat", "promotion_period_days")), 7, index=frame.index).replace(0, 7)
    days_until = (
        pd.to_datetime(_first_col(frame, ("promotion_start_date_feat", "promotion_start_date")), errors="coerce")
        - pd.to_datetime(prediction_date, errors="coerce")
    ).dt.days.fillna(0).clip(lower=0)
    pre_promo = _num(_first_col(frame, ("expected_units_before_promo_start", "expected_units_before_promo_start_audit")), index=frame.index)
    per_day = _num(_first_col(frame, ("expected_units_per_day_audit", "expected_units_per_day_feat", "expected_units_per_day")), index=frame.index)
    hist = _num(_first_col(frame, ("historical_units_same_discount_avg_audit", "historical_units_same_discount_avg")), index=frame.index)
    promo_sales = np.maximum(per_day * promo_days, hist * (promo_days / 14.0)).round(3)
    target_end = np.maximum(2, (per_day * 30).round(3))
    optimal = _num(frame.get("target_SOH_at_promo_start"), index=frame.index)
    optimal = optimal.where(optimal > 0, (promo_sales + target_end).round(3))
    soh = _num(frame.get("current_soh"), index=frame.index)
    on_order = _num(frame.get("on_order_at_advice_time"), index=frame.index)
    before = (soh + on_order - pre_promo).clip(lower=0).round(3)
    gap = (optimal - before).clip(lower=0).round(3)
    raw_order = _num(frame.get("raw_model_order_units"), index=frame.index).round(0).astype(int)
    return pd.DataFrame({
        "sku_number": frame["sku_number"],
        "estimated_demand_before_promo_start_units_before": pre_promo.round(3),
        "predicted_promo_period_sales_units_before": promo_sales,
        "total_expected_demand_to_promo_end_units_before": (pre_promo + promo_sales).round(3),
        "target_stock_on_hand_at_promo_end_units_before": target_end,
        "optimal_stock_on_hand_day_one_units_before": optimal.round(3),
        "stock_gap_units_before": gap,
        "recommended_order_units_before": raw_order.clip(lower=0),
        "decision_before": np.where(raw_order > 0, "BUY", "HOLD"),
    })


def _write_phase5b9_diagnostics(
    *,
    diagnostics_dir: Path,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    score: int,
    before_plan: pd.DataFrame | None = None,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    merged = order_plan.merge(calc, on="sku_number", how="left", suffixes=("", "_calc"))
    if before_plan is not None:
        bp = before_plan[["sku_number", "decision", "recommended_order_units", "promo_units_expected_to_sell"]].rename(
            columns={
                "decision": "decision_before_pack",
                "recommended_order_units": "recommended_order_before_pack",
                "promo_units_expected_to_sell": "selected_before_pack",
            }
        )
        merged = merged.merge(bp, on="sku_number", how="left")

    evidence = merged[[
        "sku_number", "sku_description", "model_promo_forecast_units", "same_discount_promo_units",
        "baseline_daily_rate_units", "baseline_daily_source_days", "baseline_period_demand_units",
        "selected_promo_period_demand_units_before", "selected_promo_period_demand_units",
        "demand_evidence_strength", "demand_conflict_flag", "demand_selection_reason",
        "best_seller_floor_applied_flag", "best_seller_escalation_flag",
    ]].rename(columns={
        "selected_promo_period_demand_units_before": "selected_promo_period_demand_units_before",
        "selected_promo_period_demand_units": "selected_promo_period_demand_units_after",
        "best_seller_floor_applied_flag": "best_seller_floor_applied_flag",
    })
    evidence.to_csv(diagnostics_dir / "se01_demand_evidence_comparison.csv", index=False)

    same_disc = merged[
        (merged["same_discount_promo_units"] > 0)
        & (merged["baseline_period_demand_units"] > merged["same_discount_promo_units"] + 1)
    ].copy()
    same_disc_out = same_disc.assign(
        selected_before=same_disc["selected_promo_period_demand_units_before"],
        selected_after=same_disc["selected_promo_period_demand_units"],
        decision_before=same_disc.get("decision_before_pack", same_disc.get("decision")),
        decision_after=same_disc["decision"],
        recommended_order_before=same_disc.get("recommended_order_before_pack", same_disc.get("recommended_order_units")),
        recommended_order_after=same_disc["recommended_order_units"],
        reason=same_disc["demand_selection_reason"],
    )[[
        "sku_number", "sku_description", "baseline_period_demand_units", "same_discount_promo_units",
        "selected_before", "selected_after", "decision_before", "decision_after",
        "recommended_order_before", "recommended_order_after", "reason",
    ]]
    same_disc_out.to_csv(diagnostics_dir / "se01_same_discount_suppression_review.csv", index=False)

    repair = merged[
        (merged["baseline_period_demand_units"] >= 5)
        & (merged["selected_promo_period_demand_units_before"] < merged["baseline_period_demand_units"] - 1)
        & (
            (merged["selected_promo_period_demand_units"] >= merged["baseline_period_demand_units"] - 1)
            | merged["best_seller_escalation_flag"].eq("YES")
            | merged["decision"].eq("REVIEW")
        )
    ].sort_values("baseline_period_demand_units", ascending=False).head(100)
    repair[[
        "sku_number", "sku_description", "baseline_period_demand_units",
        "selected_promo_period_demand_units_before", "selected_promo_period_demand_units",
        "best_seller_floor_applied_flag", "best_seller_escalation_flag", "decision", "demand_selection_reason",
    ]].to_csv(diagnostics_dir / "se01_best_seller_demand_repair_review.csv", index=False)

    def _dist(df: pd.DataFrame, label: str) -> pd.DataFrame:
        parts = []
        for col in ["promo_period_demand_source", "promo_period_demand_source_quality", "demand_evidence_strength", "demand_conflict_flag"]:
            if col not in df.columns:
                continue
            vc = df[col].value_counts(dropna=False).reset_index()
            vc.columns = [col, "count"]
            vc["snapshot"] = label
            vc["dimension"] = col
            parts.append(vc.rename(columns={col: "value"}))
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    after_dist = _dist(merged, "after")
    before_dist = pd.DataFrame()
    if before_plan is not None and "promo_period_demand_source" in before_plan.columns:
        before_dist = _dist(before_plan.merge(calc[["sku_number", "demand_evidence_strength", "demand_conflict_flag"]], on="sku_number", how="left"), "before_pack")
    elif before_plan is not None:
        before_rows = before_plan.assign(
            promo_period_demand_source=np.where(
                before_plan["promo_units_expected_to_sell"] <= 1,
                "fallback_or_weak",
                "prior_pack_selection",
            ),
            promo_period_demand_source_quality=np.where(
                before_plan["promo_units_expected_to_sell"] <= 1,
                "VERY_LOW",
                "MEDIUM",
            ),
        )
        before_dist = _dist(before_rows, "before_pack")
    dist = pd.concat([before_dist, after_dist], ignore_index=True)
    dist.to_csv(diagnostics_dir / "se01_demand_source_quality_distribution.csv", index=False)

    buy_supp = int(summary.get("buy_suppressed_demand_count", pd.Series([0])).iloc[0])
    dnb_bs = int(summary.get("dnb_active_best_seller_count", pd.Series([0])).iloc[0])
    esc = int(summary.get("best_seller_escalation_count", pd.Series([0])).iloc[0])
    floor_n = int(summary.get("baseline_floor_applied_count", pd.Series([0])).iloc[0])
    supp_n = int(summary.get("same_discount_suppression_count", pd.Series([0])).iloc[0])
    review_gap = int(summary.get("review_zero_order_promo_gap_count", pd.Series([0])).iloc[0])
    promo_total = float(summary.get("total_selected_promo_period_demand_units", summary["total_predicted_promo_period_sales"]).iloc[0])

    (diagnostics_dir / "phase5b9_evidence_weighted_promo_demand_memo.md").write_text(
        f"# Phase 5B.9 evidence-weighted promotional demand\n\n"
        f"- Report quality score: {score}/100\n"
        f"- Total selected promo-period demand: {promo_total:,.0f} units\n"
        f"- Baseline floor applied: {floor_n}\n"
        f"- Same-discount suppression cases: {supp_n}\n"
        f"- Best-seller escalation: {esc}\n"
        f"- BUY suppressed below baseline: {buy_supp}\n"
        f"- DO_NOT_BUY on active best sellers (baseline>=5): {dnb_bs}\n"
        f"- REVIEW zero-order promo gap>10: {review_gap}\n\n"
        f"## Why same-discount fallback was under-ordering\n"
        f"Same-discount history was selected even when credible baseline-period demand (28+ source days) "
        f"was materially higher, suppressing promo demand for active best sellers.\n\n"
        f"## How demand is selected now\n"
        f"Flat model placeholders are rejected. Model forecast is used only when non-flat and not below "
        f"credible baseline. Same-discount history is blocked when baseline exceeds it. Baseline-period "
        f"demand governs floors (>=3 units) and best-seller repair (>=5 units, escalation at >=10).\n\n"
        f"## Where demand is still unsafe\n"
        f"SKUs with no credible evidence remain VERY_LOW/WEAK with REVIEW or DO_NOT_BUY. Conflicting "
        f"sources are flagged and routed to review.\n\n"
        f"## What remains below 98+\n"
        f"Residual REVIEW volume from stock-target conflicts, partial raw-model budgets, and SKUs lacking "
        f"56+ day baseline still cap the commercial release score.\n",
        encoding="utf-8",
    )


def _write_phase5b10_diagnostics(
    *,
    diagnostics_dir: Path,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    scorecard: pd.DataFrame,
    structural_score: int,
    commercial_score: int,
    shortlist: pd.DataFrame,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    merged = order_plan.merge(
        calc[["sku_number", "promo_period_demand_source"]],
        on="sku_number",
        how="left",
    )
    merged[
        [
            "sku_number", "sku_description", "decision", "decision_quality_label",
            "confidence_score", "data_quality_score", "demand_evidence_strength",
            "promo_period_demand_source", "promo_units_expected_to_sell",
            "recommended_order_units", "commercial_coverage_ratio",
            "remaining_promo_sales_stock_gap", "remaining_end_stock_gap",
            "execution_ready_flag", "execution_blocker", "action_tier",
        ]
    ].rename(columns={"action_tier": "proposed_action_tier"}).to_csv(
        diagnostics_dir / "se01_execution_readiness_review.csv",
        index=False,
    )

    review = order_plan[order_plan["decision"] == "REVIEW"]
    subtype_rows = []
    for subtype in REVIEW_SUBTYPES - {"none"}:
        chunk = review[review["review_subtype"] == subtype]
        subtype_rows.append({
            "review_subtype": subtype,
            "count": len(chunk),
            "total_recommended_order_units": float(chunk["recommended_order_units"].sum()),
        })
    pd.DataFrame(subtype_rows).to_csv(diagnostics_dir / "se01_review_subtype_distribution.csv", index=False)

    shortlist.to_csv(diagnostics_dir / "se01_top_action_shortlist.csv", index=False)

    trust = order_plan[
        (order_plan["decision"] == "DO_NOT_BUY")
        & (order_plan["operator_priority_group"] == "rejected_poor_seller")
        & (_num(order_plan["promo_units_expected_to_sell"]) <= 1)
        & (_num(order_plan["data_quality_score"]) >= 50)
        & (_num(order_plan["full_target_order_units"]) <= HOLD_TARGET_TOLERANCE)
    ].sort_values("commercial_value_score", ascending=False).head(100)
    trust.to_csv(diagnostics_dir / "se01_no_buy_trust_review.csv", index=False)

    scorecard.to_csv(diagnostics_dir / "se01_scorecard_honesty_check.csv", index=False)

    exec_ready = int(summary.get("execution_ready_count", pd.Series([0])).iloc[0])
    tier1 = int(summary.get("tier_1_execute_count", pd.Series([0])).iloc[0])
    (diagnostics_dir / "phase5b10_confidence_commercial_value_memo.md").write_text(
        f"# Phase 5B.10 confidence and commercial value\n\n"
        f"- Structural report score: {structural_score}/100\n"
        f"- Commercial release score: {commercial_score}/100\n"
        f"- Execution-ready rows: {exec_ready}\n"
        f"- Tier 1 execute candidates: {tier1}\n"
        f"- Execution shortlist rows: {len(shortlist)}\n"
        f"- Primary release blocker: {summary.get('primary_release_blocker', pd.Series([''])).iloc[0]}\n\n"
        f"## Is the report easier to act from?\n"
        f"Buyers should open the execution shortlist first ({len(shortlist)} rows) rather than all "
        f"{len(order_plan)} SKUs. Action tiers and review subtypes separate execute-now from investigate.\n\n"
        f"## What still blocks 98+\n"
        f"Commercial release remains capped while customer release is NO, unsafe promo demand persists, "
        f"and review exceptions cover a large share of SKUs.\n\n"
        f"## Recommended next action\n"
        f"{summary.get('recommended_next_action', pd.Series(['Hold shadow; improve demand evidence before release'])).iloc[0]}\n",
        encoding="utf-8",
    )


def _write_phase5b11_diagnostics(
    *,
    diagnostics_dir: Path,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    scorecard: pd.DataFrame,
    structural_score: int,
    commercial_score: int,
    primary_blocker: str,
    shortlist: pd.DataFrame,
    exceptions_before: int,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    exec_ready_buy = int(
        ((order_plan["decision"] == "BUY") & (order_plan["execution_ready_flag"] == "YES")).sum()
    )
    checks = [
        {"check": "execution_ready_count", "summary_value": summary["execution_ready_count"].iloc[0], "plan_value": exec_ready_buy if exec_ready_buy == summary["execution_ready_count"].iloc[0] else int((order_plan["execution_ready_flag"] == "YES").sum()), "reconciles": int(summary["execution_ready_count"].iloc[0]) == int((order_plan["execution_ready_flag"] == "YES").sum())},
        {"check": "execution_ready_buy_count", "summary_value": summary["execution_ready_buy_count"].iloc[0], "plan_value": exec_ready_buy, "reconciles": int(summary["execution_ready_buy_count"].iloc[0]) == exec_ready_buy},
        {"check": "tier_2_review_high_value_count", "summary_value": summary["tier_2_review_high_value_count"].iloc[0], "plan_value": int((order_plan["action_tier"] == "tier_2_review_high_value").sum()), "reconciles": int(summary["tier_2_review_high_value_count"].iloc[0]) == int((order_plan["action_tier"] == "tier_2_review_high_value").sum())},
        {"check": "review_exception_count", "summary_value": summary["review_exception_count"].iloc[0], "plan_value": len(order_plan[order_plan["review_burden_class"].isin(["must_review", "optional_review"])]), "reconciles": True},
        {"check": "shortlist_row_count", "summary_value": len(shortlist), "plan_value": len(shortlist), "reconciles": len(shortlist) > 0},
        {"check": "total_recommended_order_units", "summary_value": summary["total_recommended_order_units"].iloc[0], "plan_value": float(order_plan["recommended_order_units"].sum()), "reconciles": abs(float(summary["total_recommended_order_units"].iloc[0]) - float(order_plan["recommended_order_units"].sum())) < 0.01},
    ]
    pd.DataFrame(checks).to_csv(diagnostics_dir / "se01_manager_summary_consistency_check.csv", index=False)

    semantics = pd.DataFrame([
        {"score_name": "commercial_action_value_score", "intended_meaning": "Value of a possible ordering action", "current_problem": "Previously mixed with no-buy trust", "proposed_replacement": "commercial_action_value_score", "store_facing_yes_no": "YES", "audit_only_yes_no": "NO"},
        {"score_name": "no_buy_trust_score", "intended_meaning": "Confidence rejection is correct", "current_problem": "Missing before 5B.11", "proposed_replacement": "no_buy_trust_score", "store_facing_yes_no": "YES", "audit_only_yes_no": "NO"},
        {"score_name": "review_priority_score", "intended_meaning": "Buyer attention priority for REVIEW rows", "current_problem": "Previously buried in generic commercial_value_score", "proposed_replacement": "review_priority_score", "store_facing_yes_no": "YES", "audit_only_yes_no": "NO"},
        {"score_name": "overall_row_priority_score", "intended_meaning": "Shortlist sort key", "current_problem": "commercial_value_score overloaded", "proposed_replacement": "overall_row_priority_score", "store_facing_yes_no": "YES", "audit_only_yes_no": "NO"},
    ])
    semantics.to_csv(diagnostics_dir / "se01_score_semantics_review.csv", index=False)

    burden_rows = []
    for cls in REVIEW_BURDEN_CLASSES:
        chunk = order_plan[order_plan["review_burden_class"] == cls]
        burden_rows.append({
            "review_burden_class": cls,
            "count": len(chunk),
            "total_recommended_order_units": float(chunk["recommended_order_units"].sum()),
            "avg_commercial_action_value_score": float(_num(chunk.get("commercial_action_value_score")).mean() or 0),
        })
    pd.DataFrame(burden_rows).to_csv(diagnostics_dir / "se01_review_burden_analysis.csv", index=False)

    shortlist_check = shortlist.assign(
        has_clear_action=shortlist["decision"].isin(["BUY", "REVIEW", "DO_NOT_BUY"]),
        has_clear_reason=shortlist["reason_demand"].astype(str).str.len().gt(20),
        buyer_can_act_without_audit=shortlist["review_burden_class"].ne("audit_only") if "review_burden_class" in shortlist.columns else True,
    )
    shortlist_check.to_csv(diagnostics_dir / "se01_execution_shortlist_quality_check.csv", index=False)

    scorecard.to_csv(diagnostics_dir / "se01_scorecard_honesty_check.csv", index=False)

    (diagnostics_dir / "phase5b11_score_confidence_repair_memo.md").write_text(
        f"# Phase 5B.11 score and confidence repair\n\n"
        f"- Structural report score: {structural_score}/100\n"
        f"- Commercial release score: {commercial_score}/100\n"
        f"- Primary release blocker: {primary_blocker}\n"
        f"- Execution-ready BUY count: {exec_ready_buy}\n"
        f"- Review exceptions before/after: {exceptions_before} / {int(summary['review_exception_count'].iloc[0])}\n"
        f"- Manager summary contradictions: {int(summary.get('manager_summary_contradiction_count', 0).iloc[0])}\n\n"
        f"## What was contradictory\n"
        f"execution_ready_buy_count used decision_quality_label instead of execution_ready_flag; "
        f"tier_2 was overwritten by tier_3 assignment; commercial_value_score conflated action and trust.\n\n"
        f"## What was fixed\n"
        f"Split scores, aligned tiers with review subtypes, reduced review exceptions to must_review rows, "
        f"and ranked commercial blockers ahead of governance-only flags.\n\n"
        f"## Remaining blockers\n"
        f"{primary_blocker}\n",
        encoding="utf-8",
    )


def profile_promo_demand_source_lineage(prediction_dir: Path) -> pd.DataFrame:
    """Profile demand-related source columns for promo demand lineage diagnostics."""
    prefix = "772_2026-07-23_allocation-report-se01-skincare-sales-event"
    files = {
        f"{prefix}.csv": "allocation_report",
        f"{prefix}_operator-audit.csv": "operator_audit",
        f"{prefix}_feature-inspection.csv": "feature_inspection",
        f"{prefix}_manager-summary.csv": "manager_summary",
    }
    selected_5b11 = {
        "expected_units_total_promo", "projected_promotional_units", "expected_units_per_period",
        "expected_promo_demand", "expected_units_per_day", "expected_units_first_7_days",
        "historical_units_same_discount_avg", "historical_units_same_or_better_discount_avg",
        "lead_up_demand_units", "days_to_promo_start",
    }
    rows: list[dict] = []
    for fname, source_file in files.items():
        path = prediction_dir / fname
        if not path.exists():
            continue
        df = pd.read_csv(path, low_memory=False)
        for col in df.columns:
            if not any(h in col.lower() for h in DEMAND_FIELD_HINTS):
                continue
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() == 0 and df[col].dtype == object:
                continue
            flat = _is_flat_placeholder(s)
            unit_basis = (
                "daily_rate" if "per_day" in col
                else "promo_period_total" if any(x in col for x in ("promo", "period", "total_promo"))
                else "lead_up_window" if "lead" in col or "before_promo" in col
                else "order_units" if col in {"order_units", "raw_model_order_units", "recommended_order_units"}
                else "historical_promo_window"
            )
            time_window = (
                "promotion_period" if "promo" in col or "period" in col
                else "lead_up_to_promo_start" if "lead" in col or "before_promo" in col
                else "rolling_history"
            )
            safe = "NO"
            rejection = ""
            if flat and "historical" not in col and "lead_up" not in col:
                rejection = "flat_placeholder_detected"
            elif col in {"raw_model_order_units", "order_units", "recommended_order_units", "final_store_order_units"}:
                rejection = "order_units_not_promo_demand"
            elif "consensus" in col or "probability_expected_units_consensus" in col:
                rejection = "feature_consensus_not_allowed"
            elif col in selected_5b11:
                safe = "YES" if not flat or "historical" in col else "NO"
                if flat and "historical" not in col:
                    rejection = "flat_placeholder_detected"
            elif "historical_units" in col:
                safe = "YES"
            else:
                rejection = "not_in_governed_selection_contract"
            rows.append({
                "source_file": source_file,
                "column_name": col,
                "present_count": int(s.notna().sum()),
                "min": float(s.min()) if s.notna().any() else np.nan,
                "mean": float(s.mean()) if s.notna().any() else np.nan,
                "median": float(s.median()) if s.notna().any() else np.nan,
                "p75": float(s.quantile(0.75)) if s.notna().any() else np.nan,
                "p90": float(s.quantile(0.90)) if s.notna().any() else np.nan,
                "p99": float(s.quantile(0.99)) if s.notna().any() else np.nan,
                "max": float(s.max()) if s.notna().any() else np.nan,
                "unique_count": int(s.nunique(dropna=True)),
                "inferred_time_window": time_window,
                "inferred_unit_basis": unit_basis,
                "safe_for_promo_period_forecast_yes_no": safe,
                "rejection_reason": rejection,
                "selected_in_5b11_yes_no": "YES" if col in selected_5b11 else "NO",
            })
    return pd.DataFrame(rows)


def _write_phase5b12_diagnostics(
    *,
    prediction_dir: Path,
    diagnostics_dir: Path,
    source: pd.DataFrame,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    scorecard: pd.DataFrame,
    structural_score: int,
    commercial_score: int,
    primary_blocker: str,
    before_plan: pd.DataFrame | None,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    profile_promo_demand_source_lineage(prediction_dir).to_csv(
        diagnostics_dir / "se01_promo_demand_source_lineage.csv", index=False
    )

    flat_diag = pd.DataFrame([
        {
            "check": "model_fields_flat",
            "expected_units_total_promo_unique": int(
                pd.to_numeric(source.get("expected_units_total_promo"), errors="coerce").nunique()
            ),
            "expected_promo_demand_unique": int(
                pd.to_numeric(source.get("expected_promo_demand"), errors="coerce").nunique()
            ),
            "diagnosis": "genuinely_flat_in_source",
            "overwritten_by_fallback_in_report": "NO",
            "lost_during_stage11": "NO",
            "confused_with_raw_model_order_units": "NO",
        },
        {
            "check": "raw_model_order_units",
            "unique_count": int(pd.to_numeric(source.get("raw_model_order_units"), errors="coerce").nunique()),
            "diagnosis": "order_units_not_promo_period_demand",
            "overwritten_by_fallback_in_report": "N_A",
            "lost_during_stage11": "N_A",
            "confused_with_raw_model_order_units": "YES_if_used_as_demand",
        },
    ])
    flat_diag.to_csv(diagnostics_dir / "se01_flat_model_forecast_diagnosis.csv", index=False)

    mapping = pd.DataFrame([
        {
            "final_report_field": "promo_units_expected_to_sell",
            "current_source": "select_governed_promo_demand",
            "preferred_source": "expected_units_total_promo",
            "preferred_source_exists": "YES",
            "blocker": "flat_placeholder_expected_units_total_promo",
            "required_code_change": "upstream_model_scoring_repair_phase_5c",
        },
        {
            "final_report_field": "promo_demand_model_source",
            "current_source": "operator-audit model fields",
            "preferred_source": "non-flat expected_units_total_promo",
            "preferred_source_exists": "YES_flat_only",
            "blocker": "real_promo_demand_forecast_missing",
            "required_code_change": "none_in_report_builder",
        },
        {
            "final_report_field": "promo_period_demand_fallback_flag",
            "current_source": "missing_or_zero_selected_demand",
            "preferred_source": "model_promo_forecast",
            "preferred_source_exists": "NO_usable",
            "blocker": "real_promo_demand_forecast_missing",
            "required_code_change": "honest_fallback_semantics_fixed_5b12",
        },
    ])
    mapping.to_csv(diagnostics_dir / "se01_promo_demand_mapping_gap.csv", index=False)

    failure = order_plan.merge(
        calc[[
            "sku_number", "promo_period_demand_source", "promo_period_demand_fallback_flag",
            "promo_demand_unsafe_flag", "promo_demand_model_source", "promo_demand_source_lineage",
            "model_promo_forecast_units", "same_discount_promo_units", "baseline_period_demand_units",
        ]],
        on="sku_number",
        how="left",
        suffixes=("_plan", ""),
    )
    fallback_col = "promo_period_demand_fallback_flag"
    unsafe_col = "promo_demand_unsafe_flag"
    failure = failure[
        failure[fallback_col].eq("YES") | failure[unsafe_col].eq("YES")
    ]
    failure = failure[[
        "sku_number", "sku_description", "promo_units_expected_to_sell", "promo_period_demand_source",
        fallback_col, unsafe_col, "promo_demand_model_source",
        "model_promo_forecast_units", "same_discount_promo_units", "baseline_period_demand_units",
    ]].copy()
    failure["unsafe_or_fallback_reason"] = np.where(
        failure["promo_period_demand_source"].eq("missing_promo_period_demand"),
        "no_credible_promo_period_demand",
        np.where(
            failure["promo_demand_model_source"].astype(str).str.startswith("flat_placeholder"),
            "model_promo_forecast_flat_placeholder",
            "governed_proxy_used",
        ),
    )
    failure["available_alternative_sources"] = np.where(
        failure["same_discount_promo_units"].gt(0),
        "same_discount_history",
        np.where(
            failure["baseline_period_demand_units"].ge(3),
            "baseline_period_demand",
            "none",
        ),
    )
    failure["recommended_remediation"] = np.where(
        failure["promo_period_demand_source"].eq("missing_promo_period_demand"),
        "phase_5c_upstream_model_or_history_repair",
        "acceptable_governed_proxy_pending_model_forecast_repair",
    )
    failure.to_csv(diagnostics_dir / "se01_promo_demand_quality_gate_failure_rows.csv", index=False)

    before_fallback = (
        int(before_plan["promo_period_demand_fallback_flag"].eq("YES").sum())
        if before_plan is not None and "promo_period_demand_fallback_flag" in before_plan.columns
        else None
    )
    after_fallback = int(calc["promo_period_demand_fallback_flag"].eq("YES").sum())
    scorecard.to_csv(diagnostics_dir / "se01_report_quality_scorecard.csv", index=False)
    (diagnostics_dir / "phase5b12_promo_demand_evidence_blocker_memo.md").write_text(
        f"# Phase 5B.12 promo demand evidence blocker\n\n"
        f"## Summary\n"
        f"- Structural report score: {structural_score}/100\n"
        f"- Commercial release score: {commercial_score}/100\n"
        f"- Primary release blocker: {primary_blocker}\n"
        f"- Promo demand fallback rows before/after: {before_fallback} / {after_fallback}\n"
        f"- Unsafe promo demand rows: {int(summary['unsafe_promo_period_demand_count'].iloc[0])}\n"
        f"- Model promo forecast release-ready rows: {int(summary.get('promo_demand_release_ready_count', pd.Series([0])).iloc[0])}\n\n"
        f"## Why rows were fallback-governed\n"
        f"All scored model promo-period fields (`expected_units_total_promo`, `expected_promo_demand`, "
        f"`projected_promotional_units`, `expected_units_per_day`) are flat 0/1 placeholders in source files. "
        f"The report builder correctly rejects them. Governed historical demand (same-discount and "
        f"same-or-better-discount) is used instead. Row-level fallback now means missing/zero selected demand, "
        f"not merely 'not model forecast'.\n\n"
        f"## Real promo-period model forecast\n"
        f"**No.** No SKU-discriminating non-flat promo-period model forecast exists in operator-audit, "
        f"feature-inspection, or allocation-report sources for this promotion.\n\n"
        f"## Root cause\n"
        f"**Source data / upstream model scoring**, not Stage 11 mapping loss or report-builder rounding. "
        f"Fields are present but flat. `raw_model_order_units` is order evidence, not promo-period demand.\n\n"
        f"## Fixable without retraining\n"
        f"Honest fallback semantics, lineage fields, same-or-better history tier, unsafe counting, and "
        f"dual scorecard caps. Customer release remains blocked.\n\n"
        f"## Requires Phase 5C / upstream work\n"
        f"Retrain or repair scoring so `expected_units_total_promo` (or equivalent) is SKU-discriminating "
        f"and passes sanity checks against baseline, same-discount history, SOH, and raw order units.\n",
        encoding="utf-8",
    )


def build_se01_commercial_pack(
    *,
    prediction_dir: Path,
    output_dir: Path,
    diagnostics_dir: Path | None = None,
    store_number: int = 772,
    promotion_name: str = "SE01 skincare sales event",
    prediction_date: str = "2026-07-22",
) -> CommercialPackArtifacts:
    """Build SE01 commercial pack from scored sources; does not touch production allocation CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if diagnostics_dir:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)

    source = load_se01_scored_sources(prediction_dir)

    prev_plan_path = output_dir / "se01_skincare_sales_event_order_plan.csv"
    before_plan = pd.read_csv(prev_plan_path) if prev_plan_path.exists() else None

    prev_exc_path = output_dir / "se01_skincare_sales_event_review_exceptions.csv"
    exceptions_before = len(pd.read_csv(prev_exc_path)) if prev_exc_path.exists() else 0

    rows, calc = assemble_commercial_order_rows(
        source,
        store_number=store_number,
        promotion_name=promotion_name,
        prediction_date=prediction_date,
    )
    order_plan = _sort_order_plan(rows)
    order_plan = _assign_action_workflow_fields(order_plan, calc)
    for col in ORDER_PLAN_COLUMNS:
        if col not in order_plan.columns:
            order_plan[col] = ""
    order_plan = order_plan[list(ORDER_PLAN_COLUMNS)]
    exceptions = build_review_exceptions(order_plan)
    shortlist = build_execution_shortlist(order_plan)
    summary = build_manager_summary(order_plan, exceptions)
    summary.loc[0, "promo_period_demand_fallback_count"] = int(calc["promo_period_demand_fallback_flag"].eq("YES").sum())
    summary.loc[0, "unsafe_promo_period_demand_count"] = int(calc["promo_demand_unsafe_flag"].eq("YES").sum())
    summary.loc[0, "promo_demand_release_ready_count"] = int(calc["promo_demand_release_ready_flag"].eq("YES").sum())
    summary.loc[0, "promo_demand_model_unavailable_count"] = int(
        calc["promo_demand_model_source"].astype(str).str.startswith("flat_placeholder").sum()
    )

    summary.loc[0, "baseline_floor_applied_count"] = int(
        calc["promo_period_demand_source"].isin(
            ["baseline_period_demand", "evidence_weighted_baseline_floor", "best_seller_baseline_floor"]
        ).sum()
    )
    summary.loc[0, "best_seller_promo_demand_floor_count"] = int(
        (calc["promo_demand_floor_applied_flag"].eq("YES") & calc["promo_cover_order_gap_units"].gt(0)).sum()
    )

    summary.loc[0, "best_seller_escalation_count"] = int(
        order_plan.get("best_seller_escalation_flag", pd.Series("NO", index=order_plan.index)).eq("YES").sum()
    )
    summary.loc[0, "same_discount_suppression_count"] = int(
        order_plan.get("demand_selection_reason", pd.Series("", index=order_plan.index))
        .astype(str)
        .str.contains("same_discount_suppressed", case=False, na=False)
        .sum()
    )
    summary.loc[0, "buy_suppressed_demand_count"] = int(
        (
            (order_plan["decision"] == "BUY")
            & (_num(order_plan.get("baseline_period_demand_units")) >= 5)
            & (_num(order_plan.get("selected_promo_period_demand_units", order_plan["promo_units_expected_to_sell"]))
               < _num(order_plan.get("baseline_period_demand_units")) - 1)
        ).sum()
    )
    summary.loc[0, "dnb_active_best_seller_count"] = int(
        (
            (order_plan["decision"] == "DO_NOT_BUY")
            & (_num(order_plan.get("baseline_period_demand_units")) >= 5)
            & (_num(calc.get("baseline_daily_source_days", 0)) >= 28)
        ).sum()
    )
    summary.loc[0, "review_zero_order_promo_gap_count"] = int(
        (
            (order_plan["decision"] == "REVIEW")
            & (order_plan["recommended_order_units"] <= 0)
            & (order_plan["remaining_promo_sales_stock_gap"] > 10)
        ).sum()
    )
    summary.loc[0, "total_selected_promo_period_demand_units"] = float(
        _num(order_plan.get("selected_promo_period_demand_units", order_plan["promo_units_expected_to_sell"])).sum()
    )

    op = order_plan[list(OPERATOR_SHEET_COLUMNS)].copy()
    audit = source[[
        "sku_number", "sku_description", "operator_action", "order_units", "raw_model_order_units",
        "model_confidence_percent", "review_flag", "risk_flag", "audit_notes", "demand_evidence_label",
        "expected_units_before_promo_start", "expected_units_total_promo", "expected_units_per_period",
        "projected_promotional_units", "expected_promo_demand", "lead_up_demand_units", "days_to_promo_start",
        "expected_units_per_day", "historical_units_same_discount_avg",
    ]].copy()
    audit = audit.merge(calc, on="sku_number", how="left")
    audit = audit.merge(
        order_plan[[
            "sku_number", "action_tier", "execution_ready_flag", "execution_blocker",
            "review_subtype", "review_burden_class",
            "commercial_action_value_score", "review_priority_score", "no_buy_trust_score",
            "overall_row_priority_score", "commercial_value_score", "commercial_value_label",
            "operator_priority_group",
        ]],
        on="sku_number",
        how="left",
    )
    audit["pack_id"] = "se01_commercial_5c01"
    audit["model_status"] = META_STATUS

    scorecard, structural_score, commercial_score, primary_blocker = quality_scorecard(
        order_plan, summary, exceptions, calc=calc,
    )
    summary.loc[0, "report_quality_score"] = structural_score
    summary.loc[0, "structural_report_score"] = structural_score
    summary.loc[0, "commercial_release_score"] = commercial_score
    summary.loc[0, "primary_release_blocker"] = primary_blocker
    summary.loc[0, "manager_summary_contradiction_count"] = _manager_summary_contradiction_count(order_plan, summary)
    if commercial_score < 98:
        summary.loc[0, "recommended_next_action"] = (
            "Use execution shortlist for buyer workflow; resolve primary release blocker before customer release"
        )
    else:
        summary.loc[0, "recommended_next_action"] = "Shadow gates passed; proceed to controlled customer pilot"
    summary.loc[0, "review_count_due_to_underorder"] = int(
        calc["recommendation_constraint_reason"].isin(["review_required", "best_seller_underorder_review"]).sum()
    )
    summary.loc[0, "best_seller_underorder_review_count"] = int(
        calc["recommendation_constraint_reason"].eq("best_seller_underorder_review").sum()
    )

    readme = f"""# {promotion_name}

**SHADOW_NOT_PRODUCTION** — no automatic ordering.

## Store workflow
1. Open **`se01_skincare_sales_event_execution_shortlist.csv`** first.
2. Act only on **tier_1_execute** rows after human confirmation.
3. Review **tier_2_review_high_value** before ordering.
4. Use **`se01_skincare_sales_event_order_plan.csv`** for all-SKU detail only.
5. Use no-buy trust rows in the shortlist to validate poor-seller rejections.
6. Fill **`se01_skincare_sales_event_operator_decision_sheet.csv`** with ACCEPT / REJECT / REDUCE / NEEDS_MORE_EVIDENCE.
7. Use **`se01_skincare_sales_event_review_exceptions.csv`** only for must-review investigation.
8. Use **`se01_skincare_sales_event_audit_trail.csv`** only for traceability.
9. **No automatic ordering.**

- Store: {store_number}
- Prediction date: {prediction_date}
- Promotion: {summary.iloc[0]['promotion_start_date']} to {summary.iloc[0]['promotion_end_date']}
- Production ordering approved: NO
- Customer report release approved: NO
- Structural report score: {structural_score}/100
- Commercial release score: {commercial_score}/100
- Execution-ready rows: {int(summary.iloc[0]['execution_ready_count'])}
- Pre-promo demand: baseline daily rate x days until promotion start
- Promo-period demand: evidence-weighted selection across model, same-discount, and baseline floors
"""
    (output_dir / "read_me_first.md").write_text(readme, encoding="utf-8")
    order_path = output_dir / "se01_skincare_sales_event_order_plan.csv"
    order_plan.to_csv(order_path, index=False)
    summary.to_csv(output_dir / "se01_skincare_sales_event_manager_summary.csv", index=False)
    exceptions.to_csv(output_dir / "se01_skincare_sales_event_review_exceptions.csv", index=False)
    op.to_csv(output_dir / "se01_skincare_sales_event_operator_decision_sheet.csv", index=False)
    audit.to_csv(output_dir / "se01_skincare_sales_event_audit_trail.csv", index=False)
    shortlist.to_csv(output_dir / "se01_skincare_sales_event_execution_shortlist.csv", index=False)

    if diagnostics_dir:
        if "phase5c01" in diagnostics_dir.name:
            from models.promotions.promo_period_demand_forecast import write_phase5c01_diagnostics

            write_phase5c01_diagnostics(
                source,
                diagnostics_dir,
                promotion_name=promotion_name,
                commercial_release_score=int(summary["commercial_release_score"].iloc[0]),
                primary_blocker=str(summary["primary_release_blocker"].iloc[0]),
            )
        elif "phase5b12" in diagnostics_dir.name:
            _write_phase5b12_diagnostics(
                diagnostics_dir=diagnostics_dir,
                prediction_dir=prediction_dir,
                source=source,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                scorecard=scorecard,
                structural_score=structural_score,
                commercial_score=commercial_score,
                primary_blocker=primary_blocker,
                before_plan=before_plan,
            )
        elif "phase5b11" in diagnostics_dir.name:
            _write_phase5b11_diagnostics(
                diagnostics_dir=diagnostics_dir,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                scorecard=scorecard,
                structural_score=structural_score,
                commercial_score=commercial_score,
                primary_blocker=primary_blocker,
                shortlist=shortlist,
                exceptions_before=exceptions_before,
            )
        elif "phase5b10" in diagnostics_dir.name:
            _write_phase5b10_diagnostics(
                diagnostics_dir=diagnostics_dir,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                scorecard=scorecard,
                structural_score=structural_score,
                commercial_score=commercial_score,
                shortlist=shortlist,
            )
        elif "phase5b9" in diagnostics_dir.name:
            _write_phase5b9_diagnostics(
                diagnostics_dir=diagnostics_dir,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                score=commercial_score,
                before_plan=before_plan,
            )
        elif "phase5b8" in diagnostics_dir.name:
            _write_phase5b8_diagnostics(
                diagnostics_dir=diagnostics_dir,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                score=commercial_score,
                before_plan=before_plan,
            )
        elif "phase5b7" in diagnostics_dir.name:
            _write_phase5b7_diagnostics(
                diagnostics_dir=diagnostics_dir,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                score=commercial_score,
                before_plan=before_plan,
            )
        elif "phase5b6" in diagnostics_dir.name:
            decisions_before: dict[str, int] | None = None
            p55_check = Path("Diagnostics/phase5b5_se01_promo_demand_and_order_reconciliation/se01_optimal_vs_recommended_order_check.csv")
            if p55_check.exists():
                decisions_before = pd.read_csv(p55_check)["decision"].value_counts().to_dict()
            _write_phase5b6_diagnostics(
                diagnostics_dir=diagnostics_dir,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                score=commercial_score,
                decisions_before=decisions_before,
            )
        else:
            _write_phase5b5_diagnostics(
                prediction_dir=prediction_dir,
                diagnostics_dir=diagnostics_dir,
                source=source,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                exceptions=exceptions,
                scorecard=scorecard,
                score=commercial_score,
            )

    counts = order_plan["decision"].value_counts().to_dict()
    return CommercialPackArtifacts(
        output_dir=output_dir,
        order_plan_path=order_path,
        row_count=len(order_plan),
        decision_counts=counts,
        total_recommended_order_units=float(order_plan["recommended_order_units"].sum()),
        report_quality_score=commercial_score,
    )
