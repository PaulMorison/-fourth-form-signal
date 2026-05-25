from __future__ import annotations

"""Governed post-calibration order policy adjustments for worst evidence buckets.

Canon ownership:
- consumes existing row-level order diagnostics plus governed baseline/uplift inputs
- applies small explicit conservative rules after model calibration
- returns auditable caps and review overrides for trainer, scoring, and Stage 11
- does not retrain the model, invent a second framework, or use realised outcomes
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (
    build_live_order_decision_diagnostics,
)


ORDER_POLICY_ADJUSTMENT_COLUMNS: tuple[str, ...] = (
    "adjusted_supported_total_units",
    "adjusted_launch_units",
    "adjusted_order_cap_units",
    "review_override_flag",
    "review_override_reason",
    "policy_adjustment_reason",
    "policy_adjustment_strength",
    "policy_adjustment_fired_flag",
    "policy_units_removed",
    "policy_capital_at_risk_removed",
)

ORDER_POLICY_MAJOR_BUCKET_COLUMNS: tuple[str, ...] = (
    "weak_same_discount_history",
    "weak_elasticity",
    "weak_uplift",
    "falling_base",
    "launch_total_conflict",
    "sparse_history_multi_driver",
)

_NO_POLICY_REASON = "no_policy_adjustment"
_NO_REVIEW_OVERRIDE_REASON = "no_review_override"
_RULE_SPARSE_MULTI_DRIVER_BASELINE_ONLY = "sparse_history_multi_driver_baseline_only"
_RULE_FALLING_BASE_LAUNCH_CONFLICT = "falling_base_launch_conflict_review"
_RULE_WEAK_SAME_DISCOUNT_AND_UPLIFT = "weak_same_discount_and_uplift_cap"
_RULE_WEAK_ELASTICITY = "weak_elasticity_uplift_restraint"
_RULE_STOCK_GAP_HIGH = "stock_gap_high_review_cap"

ORDER_POLICY_RULE_NAMES: tuple[str, ...] = (
    _RULE_SPARSE_MULTI_DRIVER_BASELINE_ONLY,
    _RULE_FALLING_BASE_LAUNCH_CONFLICT,
    _RULE_WEAK_SAME_DISCOUNT_AND_UPLIFT,
    _RULE_WEAK_ELASTICITY,
    _RULE_STOCK_GAP_HIGH,
)

_REVIEW_REASON_SPARSE_MULTI_DRIVER = "policy_sparse_history_multi_driver"
_REVIEW_REASON_FALLING_BASE_LAUNCH_CONFLICT = "policy_falling_base_launch_total_conflict"
_REVIEW_REASON_STOCK_GAP_HIGH = "policy_stock_gap_high"

_LAUNCH_WINDOW_DAYS = 7.0
_SPARSE_MULTI_DRIVER_THRESHOLD = 3.0
_MAJOR_BUCKET_MULTI_DRIVER_THRESHOLD = 2.0
_MIN_POLICY_SIGNAL_COLUMNS_PRESENT = 4
_POLICY_SIGNAL_COLUMNS: tuple[str, ...] = (
    "feature_same_discount_prior_event_count",
    "feature_same_discount_history_available_flag",
    "feature_discount_evidence_strength_score",
    "feature_discount_elasticity_confidence_score",
    "feature_discount_response_event_count",
    "feature_uplift_confidence_score",
    "feature_uplift_demand_support_flag",
    "feature_non_promo_recent_acceleration_score",
    "feature_non_promo_base_trend_30d_vs_56d",
    "feature_non_promo_base_trend_30d_vs_84d",
    "feature_non_promo_history_available_flag",
    "feature_non_promo_low_history_flag",
    "feature_sparse_history_penalty",
    "feature_total_window_pressure_vs_launch_support_conflict_score",
    "feature_allocation_vs_supported_total_gap_units",
    "feature_allocation_risk_over_uplift_score",
)

_POLICY_STRENGTH_BY_REASON: dict[str, float] = {
    _NO_POLICY_REASON: 0.0,
    _RULE_WEAK_ELASTICITY: 0.35,
    _RULE_STOCK_GAP_HIGH: 0.55,
    _RULE_WEAK_SAME_DISCOUNT_AND_UPLIFT: 0.60,
    _RULE_FALLING_BASE_LAUNCH_CONFLICT: 0.75,
    _RULE_SPARSE_MULTI_DRIVER_BASELINE_ONLY: 0.90,
}

ORDER_POLICY_RULE_STRENGTH_BY_NAME: dict[str, float] = {
    rule_name: _POLICY_STRENGTH_BY_REASON[rule_name]
    for rule_name in ORDER_POLICY_RULE_NAMES
}


def build_order_policy_adjustments(
    frame: pd.DataFrame,
    *,
    raw_predicted_units: pd.Series,
    calibrated_predicted_units: pd.Series,
    diagnostics_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build explicit conservative caps and review overrides from governed diagnostics."""

    working = frame.copy()
    diagnostics = diagnostics_frame if diagnostics_frame is not None else build_live_order_decision_diagnostics(
        working,
        raw_predicted_units=raw_predicted_units,
        predicted_units=calibrated_predicted_units,
    )
    raw_units = pd.to_numeric(raw_predicted_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    calibrated_units = pd.to_numeric(calibrated_predicted_units, errors="coerce").fillna(0.0).clip(lower=0.0)

    promo_window_days = _first_present_numeric_series(working, ("live_promo_window_days", "promo_days"))
    promo_window_days = promo_window_days.replace(0.0, np.nan).fillna(_LAUNCH_WINDOW_DAYS).clip(lower=1.0)
    launch_window_days = promo_window_days.clip(upper=_LAUNCH_WINDOW_DAYS)

    baseline_total_units = _first_present_numeric_series(
        working,
        (
            "feature_expected_baseline_units_promo_window",
            "feature_baseline_units_expected_promo_window",
            "baseline_expected_units",
        ),
    ).fillna(0.0).clip(lower=0.0)
    uplift_total_units = _first_present_numeric_series(
        working,
        (
            "feature_expected_incremental_uplift_units_same_discount",
            "feature_uplift_units_expected_total",
            "feature_probability_uplift_supported_units",
        ),
    ).fillna(0.0).clip(lower=0.0)

    baseline_launch_units = _first_present_numeric_series(
        working,
        (
            "feature_expected_baseline_units_first_7_days",
            "feature_baseline_units_expected_first_7_days",
        ),
    )
    baseline_launch_units = baseline_launch_units.where(
        baseline_launch_units.gt(0.0),
        baseline_total_units.multiply(launch_window_days).divide(promo_window_days.where(promo_window_days > 0.0)).fillna(0.0),
    ).clip(lower=0.0)

    uplift_launch_units = _first_present_numeric_series(
        working,
        (
            "feature_expected_incremental_uplift_units_first_7_days",
            "feature_uplift_units_expected_first_7_days",
        ),
    )
    uplift_launch_units = uplift_launch_units.where(
        uplift_launch_units.gt(0.0),
        uplift_total_units.multiply(launch_window_days).divide(promo_window_days.where(promo_window_days > 0.0)).fillna(0.0),
    ).clip(lower=0.0)

    adjusted_supported_total_units = calibrated_units.copy()
    adjusted_launch_units = (
        baseline_launch_units.add(uplift_launch_units).clip(lower=0.0)
    ).where(
        baseline_launch_units.add(uplift_launch_units).gt(0.0),
        calibrated_units.multiply(launch_window_days).divide(promo_window_days.where(promo_window_days > 0.0)).fillna(0.0),
    ).clip(lower=0.0)

    policy_adjustment_reason = pd.Series(_NO_POLICY_REASON, index=working.index, dtype="object")
    policy_adjustment_strength = pd.Series(0.0, index=working.index, dtype="float64")
    review_override_flag = pd.Series(0.0, index=working.index, dtype="float64")
    review_override_reason = pd.Series(_NO_REVIEW_OVERRIDE_REASON, index=working.index, dtype="object")

    policy_signal_presence_count = sum(1 for column_name in _POLICY_SIGNAL_COLUMNS if column_name in working.columns)
    if policy_signal_presence_count < _MIN_POLICY_SIGNAL_COLUMNS_PRESENT:
        return _build_policy_output_frame(
            index=working.index,
            adjusted_supported_total_units=adjusted_supported_total_units,
            adjusted_launch_units=np.minimum(adjusted_launch_units, adjusted_supported_total_units),
            adjusted_order_cap_units=calibrated_units,
            review_override_flag=review_override_flag,
            review_override_reason=review_override_reason,
            policy_adjustment_reason=policy_adjustment_reason,
            policy_adjustment_strength=policy_adjustment_strength,
            policy_units_removed=pd.Series(0.0, index=working.index, dtype="float64"),
            policy_capital_at_risk_removed=pd.Series(0.0, index=working.index, dtype="float64"),
        )

    has_same_discount_signals = _has_columns(
        working,
        (
            "feature_same_discount_prior_event_count",
            "feature_same_discount_history_available_flag",
            "feature_discount_evidence_strength_score",
        ),
    )
    has_elasticity_signals = _has_columns(
        working,
        (
            "feature_discount_elasticity_confidence_score",
            "feature_discount_response_event_count",
        ),
    )
    has_uplift_signals = _has_columns(
        working,
        (
            "feature_uplift_confidence_score",
            "feature_uplift_demand_support_flag",
        ),
    )
    has_base_trend_signals = _has_columns(
        working,
        (
            "feature_non_promo_recent_acceleration_score",
            "feature_non_promo_base_trend_30d_vs_56d",
            "feature_non_promo_base_trend_30d_vs_84d",
            "feature_non_promo_base_demand_growing_flag",
        ),
    )
    has_conflict_signals = _has_columns(
        working,
        ("feature_total_window_pressure_vs_launch_support_conflict_score",),
    )
    has_stock_gap_signals = _has_columns(
        working,
        (
            "feature_allocation_vs_supported_total_gap_units",
            "feature_allocation_risk_over_uplift_score",
        ),
    )
    has_sparse_history_signals = _has_columns(
        working,
        (
            "feature_non_promo_low_history_flag",
            "feature_sparse_history_penalty",
        ),
    )

    major_bucket_frame = build_order_policy_major_bucket_frame(diagnostics)
    same_discount_uplift_mask = (
        major_bucket_frame["weak_same_discount_history"].eq(1.0)
        & major_bucket_frame["weak_uplift"].eq(1.0)
    ) if has_same_discount_signals and has_uplift_signals else _false_mask(working.index)
    elasticity_weak_mask = (
        major_bucket_frame["weak_elasticity"].eq(1.0)
    ) if has_elasticity_signals else _false_mask(working.index)
    falling_base_launch_conflict_mask = (
        major_bucket_frame["falling_base"].eq(1.0)
        & major_bucket_frame["launch_total_conflict"].eq(1.0)
    ) if has_base_trend_signals and has_conflict_signals else _false_mask(working.index)
    stock_gap_high_mask = (
        pd.to_numeric(
            diagnostics["feature_order_risk_reason_stock_vs_supported_gap_high_flag"],
            errors="coerce",
        ).fillna(0.0).ge(1.0)
    ) if has_stock_gap_signals else _false_mask(working.index)
    sparse_multi_driver_mask = (
        pd.to_numeric(diagnostics["feature_order_risk_reason_sparse_history_flag"], errors="coerce").fillna(0.0).ge(1.0)
        & pd.to_numeric(diagnostics["feature_order_risk_reason_multi_driver_count"], errors="coerce").fillna(0.0).ge(_SPARSE_MULTI_DRIVER_THRESHOLD)
        & pd.to_numeric(diagnostics["evidence_same_discount_present_flag"], errors="coerce").fillna(0.0).le(0.0)
        & pd.to_numeric(diagnostics["evidence_usable_elasticity_flag"], errors="coerce").fillna(0.0).le(0.0)
        & pd.to_numeric(diagnostics["evidence_strong_uplift_support_flag"], errors="coerce").fillna(0.0).le(0.0)
    ) if (
        has_sparse_history_signals
        and has_same_discount_signals
        and has_elasticity_signals
        and has_uplift_signals
    ) else _false_mask(working.index)

    adjusted_supported_total_units = _apply_policy_cap(
        current_units=adjusted_supported_total_units,
        baseline_units=baseline_total_units,
        uplift_units=uplift_total_units,
        calibrated_units=calibrated_units,
        mask=sparse_multi_driver_mask,
        uplift_retain_share=0.0,
        fallback_total_share=0.35,
    )
    adjusted_launch_units = _apply_policy_cap(
        current_units=adjusted_launch_units,
        baseline_units=baseline_launch_units,
        uplift_units=uplift_launch_units,
        calibrated_units=adjusted_launch_units,
        mask=sparse_multi_driver_mask,
        uplift_retain_share=0.0,
        fallback_total_share=0.35,
    )
    policy_adjustment_reason = policy_adjustment_reason.where(~sparse_multi_driver_mask, _RULE_SPARSE_MULTI_DRIVER_BASELINE_ONLY)

    adjusted_supported_total_units = _apply_policy_cap(
        current_units=adjusted_supported_total_units,
        baseline_units=baseline_total_units,
        uplift_units=uplift_total_units,
        calibrated_units=calibrated_units,
        mask=falling_base_launch_conflict_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON),
        uplift_retain_share=0.10,
        fallback_total_share=0.50,
    )
    adjusted_launch_units = _apply_policy_cap(
        current_units=adjusted_launch_units,
        baseline_units=baseline_launch_units,
        uplift_units=uplift_launch_units,
        calibrated_units=adjusted_launch_units,
        mask=falling_base_launch_conflict_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON),
        uplift_retain_share=0.0,
        fallback_total_share=0.45,
    )
    policy_adjustment_reason = policy_adjustment_reason.where(
        ~(falling_base_launch_conflict_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON)),
        _RULE_FALLING_BASE_LAUNCH_CONFLICT,
    )

    adjusted_supported_total_units = _apply_policy_cap(
        current_units=adjusted_supported_total_units,
        baseline_units=baseline_total_units,
        uplift_units=uplift_total_units,
        calibrated_units=calibrated_units,
        mask=same_discount_uplift_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON),
        uplift_retain_share=0.25,
        fallback_total_share=0.55,
    )
    adjusted_launch_units = _apply_policy_cap(
        current_units=adjusted_launch_units,
        baseline_units=baseline_launch_units,
        uplift_units=uplift_launch_units,
        calibrated_units=adjusted_launch_units,
        mask=same_discount_uplift_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON),
        uplift_retain_share=0.20,
        fallback_total_share=0.50,
    )
    policy_adjustment_reason = policy_adjustment_reason.where(
        ~(same_discount_uplift_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON)),
        _RULE_WEAK_SAME_DISCOUNT_AND_UPLIFT,
    )

    adjusted_supported_total_units = _apply_policy_cap(
        current_units=adjusted_supported_total_units,
        baseline_units=baseline_total_units,
        uplift_units=uplift_total_units,
        calibrated_units=calibrated_units,
        mask=elasticity_weak_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON),
        uplift_retain_share=0.60,
        fallback_total_share=0.80,
    )
    adjusted_launch_units = _apply_policy_cap(
        current_units=adjusted_launch_units,
        baseline_units=baseline_launch_units,
        uplift_units=uplift_launch_units,
        calibrated_units=adjusted_launch_units,
        mask=elasticity_weak_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON),
        uplift_retain_share=0.55,
        fallback_total_share=0.75,
    )
    policy_adjustment_reason = policy_adjustment_reason.where(
        ~(elasticity_weak_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON)),
        _RULE_WEAK_ELASTICITY,
    )

    adjusted_supported_total_units = _apply_policy_cap(
        current_units=adjusted_supported_total_units,
        baseline_units=baseline_total_units,
        uplift_units=uplift_total_units,
        calibrated_units=calibrated_units,
        mask=stock_gap_high_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON),
        uplift_retain_share=0.35,
        fallback_total_share=0.65,
    )
    adjusted_launch_units = _apply_policy_cap(
        current_units=adjusted_launch_units,
        baseline_units=baseline_launch_units,
        uplift_units=uplift_launch_units,
        calibrated_units=adjusted_launch_units,
        mask=stock_gap_high_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON),
        uplift_retain_share=0.25,
        fallback_total_share=0.60,
    )
    policy_adjustment_reason = policy_adjustment_reason.where(
        ~(stock_gap_high_mask & policy_adjustment_reason.eq(_NO_POLICY_REASON)),
        _RULE_STOCK_GAP_HIGH,
    )

    review_override_flag = review_override_flag.where(~sparse_multi_driver_mask, 1.0)
    review_override_reason = review_override_reason.where(~sparse_multi_driver_mask, _REVIEW_REASON_SPARSE_MULTI_DRIVER)
    review_override_flag = review_override_flag.where(~falling_base_launch_conflict_mask, 1.0)
    review_override_reason = review_override_reason.where(
        ~(falling_base_launch_conflict_mask & review_override_reason.eq(_NO_REVIEW_OVERRIDE_REASON)),
        _REVIEW_REASON_FALLING_BASE_LAUNCH_CONFLICT,
    )
    review_override_flag = review_override_flag.where(~stock_gap_high_mask, 1.0)
    review_override_reason = review_override_reason.where(
        ~(stock_gap_high_mask & review_override_reason.eq(_NO_REVIEW_OVERRIDE_REASON)),
        _REVIEW_REASON_STOCK_GAP_HIGH,
    )

    for reason_name, strength_value in _POLICY_STRENGTH_BY_REASON.items():
        policy_adjustment_strength = policy_adjustment_strength.where(
            ~policy_adjustment_reason.eq(reason_name),
            strength_value,
        )

    adjusted_supported_total_units = adjusted_supported_total_units.clip(lower=0.0)
    adjusted_launch_units = adjusted_launch_units.clip(lower=0.0)
    adjusted_launch_units = np.minimum(adjusted_launch_units, adjusted_supported_total_units)
    adjusted_order_cap_units = np.minimum(calibrated_units, adjusted_supported_total_units)
    adjusted_order_cap_units = np.maximum(adjusted_order_cap_units, 0.0)
    adjusted_launch_units = np.minimum(adjusted_launch_units, adjusted_order_cap_units)

    unit_cost = _first_present_numeric_series(
        working,
        (
            "effective_cost_per_unit",
            "promo_effective_cost",
            "promo_cost_price",
            "last_received_cost",
        ),
    ).fillna(0.0).clip(lower=0.0)
    policy_units_removed = (calibrated_units - adjusted_order_cap_units).clip(lower=0.0)
    policy_capital_at_risk_removed = (policy_units_removed * unit_cost).clip(lower=0.0)
    return _build_policy_output_frame(
        index=working.index,
        adjusted_supported_total_units=adjusted_supported_total_units,
        adjusted_launch_units=adjusted_launch_units,
        adjusted_order_cap_units=adjusted_order_cap_units,
        review_override_flag=review_override_flag,
        review_override_reason=review_override_reason,
        policy_adjustment_reason=policy_adjustment_reason,
        policy_adjustment_strength=policy_adjustment_strength,
        policy_units_removed=policy_units_removed,
        policy_capital_at_risk_removed=policy_capital_at_risk_removed,
    )


def build_order_policy_major_bucket_frame(diagnostics_frame: pd.DataFrame) -> pd.DataFrame:
    """Build stable major-bucket flags for policy metrics and diagnostics."""

    diagnostics = diagnostics_frame.copy()
    return pd.DataFrame(
        {
            "weak_same_discount_history": pd.to_numeric(
                diagnostics["feature_order_risk_reason_same_discount_weak_flag"],
                errors="coerce",
            ).fillna(0.0).ge(1.0).astype(float),
            "weak_elasticity": pd.to_numeric(
                diagnostics["feature_order_risk_reason_elasticity_weak_flag"],
                errors="coerce",
            ).fillna(0.0).ge(1.0).astype(float),
            "weak_uplift": pd.to_numeric(
                diagnostics["feature_order_risk_reason_uplift_weak_flag"],
                errors="coerce",
            ).fillna(0.0).ge(1.0).astype(float),
            "falling_base": pd.to_numeric(
                diagnostics["feature_order_risk_reason_base_trend_falling_flag"],
                errors="coerce",
            ).fillna(0.0).ge(1.0).astype(float),
            "launch_total_conflict": pd.to_numeric(
                diagnostics["feature_order_risk_reason_launch_total_conflict_flag"],
                errors="coerce",
            ).fillna(0.0).ge(1.0).astype(float),
            "sparse_history_multi_driver": (
                pd.to_numeric(diagnostics["feature_order_risk_reason_sparse_history_flag"], errors="coerce").fillna(0.0).ge(1.0)
                & pd.to_numeric(diagnostics["feature_order_risk_reason_multi_driver_count"], errors="coerce").fillna(0.0).ge(_MAJOR_BUCKET_MULTI_DRIVER_THRESHOLD)
            ).astype(float),
        },
        index=diagnostics.index,
    )


def build_order_policy_rule_trigger_frame(
    frame: pd.DataFrame,
    *,
    diagnostics_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Build exact governed rule-trigger flags used by the policy overlay."""

    diagnostics = diagnostics_frame.copy()
    zero_frame = pd.DataFrame(
        {rule_name: pd.Series(0.0, index=frame.index, dtype="float64") for rule_name in ORDER_POLICY_RULE_NAMES},
        index=frame.index,
    )
    policy_signal_presence_count = sum(1 for column_name in _POLICY_SIGNAL_COLUMNS if column_name in frame.columns)
    if policy_signal_presence_count < _MIN_POLICY_SIGNAL_COLUMNS_PRESENT:
        return zero_frame

    has_same_discount_signals = _has_columns(
        frame,
        (
            "feature_same_discount_prior_event_count",
            "feature_same_discount_history_available_flag",
            "feature_discount_evidence_strength_score",
        ),
    )
    has_elasticity_signals = _has_columns(
        frame,
        (
            "feature_discount_elasticity_confidence_score",
            "feature_discount_response_event_count",
        ),
    )
    has_uplift_signals = _has_columns(
        frame,
        (
            "feature_uplift_confidence_score",
            "feature_uplift_demand_support_flag",
        ),
    )
    has_base_trend_signals = _has_columns(
        frame,
        (
            "feature_non_promo_recent_acceleration_score",
            "feature_non_promo_base_trend_30d_vs_56d",
            "feature_non_promo_base_trend_30d_vs_84d",
            "feature_non_promo_base_demand_growing_flag",
        ),
    )
    has_conflict_signals = _has_columns(
        frame,
        ("feature_total_window_pressure_vs_launch_support_conflict_score",),
    )
    has_stock_gap_signals = _has_columns(
        frame,
        (
            "feature_allocation_vs_supported_total_gap_units",
            "feature_allocation_risk_over_uplift_score",
        ),
    )
    has_sparse_history_signals = _has_columns(
        frame,
        (
            "feature_non_promo_low_history_flag",
            "feature_sparse_history_penalty",
        ),
    )

    major_bucket_frame = build_order_policy_major_bucket_frame(diagnostics)
    same_discount_uplift_mask = (
        major_bucket_frame["weak_same_discount_history"].eq(1.0)
        & major_bucket_frame["weak_uplift"].eq(1.0)
    ) if has_same_discount_signals and has_uplift_signals else _false_mask(frame.index)
    elasticity_weak_mask = (
        major_bucket_frame["weak_elasticity"].eq(1.0)
    ) if has_elasticity_signals else _false_mask(frame.index)
    falling_base_launch_conflict_mask = (
        major_bucket_frame["falling_base"].eq(1.0)
        & major_bucket_frame["launch_total_conflict"].eq(1.0)
    ) if has_base_trend_signals and has_conflict_signals else _false_mask(frame.index)
    stock_gap_high_mask = (
        pd.to_numeric(
            diagnostics["feature_order_risk_reason_stock_vs_supported_gap_high_flag"],
            errors="coerce",
        ).fillna(0.0).ge(1.0)
    ) if has_stock_gap_signals else _false_mask(frame.index)
    sparse_multi_driver_mask = (
        pd.to_numeric(diagnostics["feature_order_risk_reason_sparse_history_flag"], errors="coerce").fillna(0.0).ge(1.0)
        & pd.to_numeric(diagnostics["feature_order_risk_reason_multi_driver_count"], errors="coerce").fillna(0.0).ge(_SPARSE_MULTI_DRIVER_THRESHOLD)
        & pd.to_numeric(diagnostics["evidence_same_discount_present_flag"], errors="coerce").fillna(0.0).le(0.0)
        & pd.to_numeric(diagnostics["evidence_usable_elasticity_flag"], errors="coerce").fillna(0.0).le(0.0)
        & pd.to_numeric(diagnostics["evidence_strong_uplift_support_flag"], errors="coerce").fillna(0.0).le(0.0)
    ) if (
        has_sparse_history_signals
        and has_same_discount_signals
        and has_elasticity_signals
        and has_uplift_signals
    ) else _false_mask(frame.index)

    return pd.DataFrame(
        {
            _RULE_SPARSE_MULTI_DRIVER_BASELINE_ONLY: sparse_multi_driver_mask.astype(float),
            _RULE_FALLING_BASE_LAUNCH_CONFLICT: falling_base_launch_conflict_mask.astype(float),
            _RULE_WEAK_SAME_DISCOUNT_AND_UPLIFT: same_discount_uplift_mask.astype(float),
            _RULE_WEAK_ELASTICITY: elasticity_weak_mask.astype(float),
            _RULE_STOCK_GAP_HIGH: stock_gap_high_mask.astype(float),
        },
        index=frame.index,
    )


def _apply_policy_cap(
    *,
    current_units: pd.Series,
    baseline_units: pd.Series,
    uplift_units: pd.Series,
    calibrated_units: pd.Series,
    mask: pd.Series,
    uplift_retain_share: float,
    fallback_total_share: float,
) -> pd.Series:
    current_numeric = pd.to_numeric(current_units, errors="coerce").fillna(0.0)
    target_units = _policy_target_units(
        baseline_units=baseline_units,
        uplift_units=uplift_units,
        calibrated_units=calibrated_units,
        uplift_retain_share=uplift_retain_share,
        fallback_total_share=fallback_total_share,
    )
    capped_units = np.minimum(
        current_numeric,
        pd.to_numeric(target_units, errors="coerce").fillna(0.0),
    )
    return current_numeric.where(~mask, capped_units)


def _policy_target_units(
    *,
    baseline_units: pd.Series,
    uplift_units: pd.Series,
    calibrated_units: pd.Series,
    uplift_retain_share: float,
    fallback_total_share: float,
) -> pd.Series:
    supported_target = pd.to_numeric(baseline_units, errors="coerce").fillna(0.0) + (
        pd.to_numeric(uplift_units, errors="coerce").fillna(0.0) * uplift_retain_share
    )
    fallback_target = pd.to_numeric(calibrated_units, errors="coerce").fillna(0.0) * fallback_total_share
    return supported_target.where(supported_target.gt(0.0), fallback_target).clip(lower=0.0)


def _build_policy_output_frame(
    *,
    index: pd.Index,
    adjusted_supported_total_units: pd.Series,
    adjusted_launch_units: pd.Series,
    adjusted_order_cap_units: pd.Series,
    review_override_flag: pd.Series,
    review_override_reason: pd.Series,
    policy_adjustment_reason: pd.Series,
    policy_adjustment_strength: pd.Series,
    policy_units_removed: pd.Series,
    policy_capital_at_risk_removed: pd.Series,
) -> pd.DataFrame:
    policy_adjustment_fired_flag = (
        policy_adjustment_reason.ne(_NO_POLICY_REASON)
        | review_override_flag.ge(1.0)
    ).astype(float)
    return pd.DataFrame(
        {
            "adjusted_supported_total_units": pd.to_numeric(adjusted_supported_total_units, errors="coerce").fillna(0.0),
            "adjusted_launch_units": pd.to_numeric(adjusted_launch_units, errors="coerce").fillna(0.0),
            "adjusted_order_cap_units": pd.to_numeric(adjusted_order_cap_units, errors="coerce").fillna(0.0),
            "review_override_flag": review_override_flag,
            "review_override_reason": review_override_reason,
            "policy_adjustment_reason": policy_adjustment_reason,
            "policy_adjustment_strength": policy_adjustment_strength,
            "policy_adjustment_fired_flag": policy_adjustment_fired_flag,
            "policy_units_removed": pd.to_numeric(policy_units_removed, errors="coerce").fillna(0.0),
            "policy_capital_at_risk_removed": pd.to_numeric(policy_capital_at_risk_removed, errors="coerce").fillna(0.0),
        },
        index=index,
    )


def _first_present_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    return candidate_frame.bfill(axis=1).iloc[:, 0]


def _has_any_columns(frame: pd.DataFrame, column_names: tuple[str, ...]) -> bool:
    return any(column_name in frame.columns for column_name in column_names)


def _has_columns(frame: pd.DataFrame, column_names: tuple[str, ...]) -> bool:
    return all(column_name in frame.columns for column_name in column_names)


def _false_mask(index: pd.Index) -> pd.Series:
    return pd.Series(False, index=index, dtype=bool)