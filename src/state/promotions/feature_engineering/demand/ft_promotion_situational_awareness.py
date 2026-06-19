from __future__ import annotations

"""Review-only promotion situational awareness feature module.

Canon ownership:
- Interprets existing trust-floor, capital, replenishment, PCA, and evidence
  signals into auditable state labels.
- Emits review-only context only; it does not widen BUY/ORDER policy or create
  model-use features.
- Treats missing evidence as unavailable context rather than as low risk.
"""

import numpy as np
import pandas as pd


PROMOTION_SITUATIONAL_AWARENESS_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_trust_floor_pressure_state",
    "feature_speculative_capital_pressure_state",
    "feature_replenishment_confidence_state",
    "feature_promotion_context_quality_state",
    "feature_capital_deployment_posture",
    "feature_context_reason_summary",
)

PROMOTION_SITUATIONAL_AWARENESS_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    *PROMOTION_SITUATIONAL_AWARENESS_FEATURE_COLUMNS,
)

_UNAVAILABLE = "unavailable"

_TRUST_FLOOR_PRESSURE_PROTECT = "protect_trust_floor"
_TRUST_FLOOR_PRESSURE_WATCH = "watch_trust_floor_pressure"
_TRUST_FLOOR_PRESSURE_CLEAR = "trust_floor_clear"

_SPECULATIVE_CAPITAL_HIGH = "speculative_capital_high"
_SPECULATIVE_CAPITAL_WATCH = "speculative_capital_watch"
_SPECULATIVE_CAPITAL_NOT_EVIDENCED = "speculative_capital_not_evidenced"

_REPLENISHMENT_CONSTRAINED = "replenishment_constrained"
_REPLENISHMENT_PARTIAL = "replenishment_partial"
_REPLENISHMENT_SUPPORTED = "replenishment_supported"

_CONTEXT_EVIDENCE_SUPPORTED = "context_evidence_supported"
_CONTEXT_REVIEW_REQUIRED = "context_review_required"
_CONTEXT_WEAK_OR_CONFLICTED = "context_weak_or_conflicted"

_POSTURE_REVIEW_UNAVAILABLE = "review_unavailable_context"
_POSTURE_PROTECT_TRUST_FLOOR = "protect_trust_floor_before_capital_suppression"
_POSTURE_REVIEW_SPECULATIVE_CAPITAL = "review_speculative_capital_suppression"
_POSTURE_MONITOR_CAPITAL = "monitor_capital_pressure"
_POSTURE_NO_NEW_SIGNAL = "no_new_policy_signal"


def apply_ft_promotion_situational_awareness(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append review-only situational awareness states.

    Purpose:
        Convert governed numeric feature evidence into readable state labels for
        inspection, replay, and attribution without changing model inputs or
        downstream order policy.

    Inputs:
        frame: promotion candidates carrying allocation-discipline, PCA, and
            prior-evidence features.
        reference_frame: accepted for registry compatibility and deliberately
            unused because this layer is row-local over already-governed inputs.

    Outputs:
        A copy of ``frame`` with review-only state and reason columns appended.

    Important assumptions:
        All historical evidence consumed here has already been engineered using
        prior-safe modules. This module must never infer realised future
        promotion outcomes.

    Failure behaviour:
        Missing prerequisite evidence produces ``unavailable`` states. The
        module does not coerce unknown stock, capital, or evidence into weak or
        safe labels.
    """

    del reference_frame
    working = frame.copy()

    trust_floor_state = _build_trust_floor_pressure_state(working)
    speculative_capital_state = _build_speculative_capital_pressure_state(working)
    replenishment_state = _build_replenishment_confidence_state(working)
    context_quality_state = _build_context_quality_state(working)
    deployment_posture = _build_capital_deployment_posture(
        trust_floor_state=trust_floor_state,
        speculative_capital_state=speculative_capital_state,
        replenishment_state=replenishment_state,
        context_quality_state=context_quality_state,
    )
    reason_summary = _build_reason_summary(
        trust_floor_state=trust_floor_state,
        speculative_capital_state=speculative_capital_state,
        replenishment_state=replenishment_state,
        context_quality_state=context_quality_state,
        deployment_posture=deployment_posture,
    )

    derived_columns = pd.DataFrame(
        {
            "feature_trust_floor_pressure_state": trust_floor_state,
            "feature_speculative_capital_pressure_state": speculative_capital_state,
            "feature_replenishment_confidence_state": replenishment_state,
            "feature_promotion_context_quality_state": context_quality_state,
            "feature_capital_deployment_posture": deployment_posture,
            "feature_context_reason_summary": reason_summary,
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _build_trust_floor_pressure_state(frame: pd.DataFrame) -> pd.Series:
    stock_below_floor = _optional_numeric_series(frame, "feature_stock_below_trust_floor_flag").clip(0.0, 1.0)
    trust_floor_gap_units = _optional_numeric_series(frame, "feature_projected_stock_gap_to_trust_floor_units").clip(lower=0.0)
    missed_demand_risk = _optional_numeric_series(frame, "feature_trust_floor_missed_demand_risk_score").clip(0.0, 1.0)
    cover_ratio = _optional_numeric_series(frame, "feature_pre_promo_cover_ratio").clip(lower=0.0)

    evidence_available = stock_below_floor.notna() & trust_floor_gap_units.notna() & missed_demand_risk.notna()
    protect_floor = evidence_available & (
        stock_below_floor.ge(1.0) | trust_floor_gap_units.gt(0.0) | missed_demand_risk.ge(0.35)
    )
    watch_floor = evidence_available & ~protect_floor & cover_ratio.notna() & cover_ratio.lt(1.0)

    return _state_series(
        frame.index,
        default=_TRUST_FLOOR_PRESSURE_CLEAR,
        unavailable=~evidence_available,
        ordered_conditions=(
            (protect_floor, _TRUST_FLOOR_PRESSURE_PROTECT),
            (watch_floor, _TRUST_FLOOR_PRESSURE_WATCH),
        ),
    )


def _build_speculative_capital_pressure_state(frame: pd.DataFrame) -> pd.Series:
    speculative_flag = _optional_numeric_series(frame, "feature_speculative_above_trust_floor_risk_flag").clip(0.0, 1.0)
    capital_drag_ratio = _optional_numeric_series(frame, "feature_expected_bill_cycle_capital_drag_ratio").clip(0.0, 1.0)
    leftover_above_floor_units = _optional_numeric_series(
        frame,
        "feature_expected_leftover_above_trust_floor_units",
    ).clip(lower=0.0)
    pca_allocation_outlier = _optional_numeric_series(frame, "feature_pca_allocation_outlier_flag").clip(0.0, 1.0)

    evidence_available = speculative_flag.notna() & capital_drag_ratio.notna() & leftover_above_floor_units.notna()
    high_pressure = evidence_available & speculative_flag.ge(1.0) & capital_drag_ratio.ge(0.15)
    watch_pressure = evidence_available & ~high_pressure & (
        speculative_flag.ge(1.0)
        | capital_drag_ratio.ge(0.15)
        | leftover_above_floor_units.ge(1.0)
        | pca_allocation_outlier.eq(1.0)
    )

    return _state_series(
        frame.index,
        default=_SPECULATIVE_CAPITAL_NOT_EVIDENCED,
        unavailable=~evidence_available,
        ordered_conditions=(
            (high_pressure, _SPECULATIVE_CAPITAL_HIGH),
            (watch_pressure, _SPECULATIVE_CAPITAL_WATCH),
        ),
    )


def _build_replenishment_confidence_state(frame: pd.DataFrame) -> pd.Series:
    inventory_sufficiency = _optional_numeric_series(frame, "feature_inventory_sufficiency_flag").clip(0.0, 1.0)
    cover_ratio = _optional_numeric_series(frame, "feature_pre_promo_cover_ratio").clip(lower=0.0)
    stock_below_floor = _optional_numeric_series(frame, "feature_stock_below_trust_floor_flag").clip(0.0, 1.0)

    evidence_available = inventory_sufficiency.notna() & cover_ratio.notna() & stock_below_floor.notna()
    constrained = evidence_available & (
        inventory_sufficiency.le(0.0) | cover_ratio.lt(1.0) | stock_below_floor.ge(1.0)
    )
    supported = evidence_available & ~constrained & inventory_sufficiency.ge(1.0) & cover_ratio.ge(1.5)

    return _state_series(
        frame.index,
        default=_REPLENISHMENT_PARTIAL,
        unavailable=~evidence_available,
        ordered_conditions=(
            (constrained, _REPLENISHMENT_CONSTRAINED),
            (supported, _REPLENISHMENT_SUPPORTED),
        ),
    )


def _build_context_quality_state(frame: pd.DataFrame) -> pd.Series:
    model_use_flag = _optional_numeric_series(frame, "feature_probability_model_use_flag").clip(0.0, 1.0)
    same_discount_available = _optional_numeric_series(
        frame,
        "feature_same_discount_history_available_flag",
    ).clip(0.0, 1.0)
    same_discount_event_count = _optional_numeric_series(frame, "feature_same_discount_prior_event_count").clip(lower=0.0)
    discount_evidence_strength = _optional_numeric_series(frame, "feature_discount_evidence_strength_score").clip(0.0, 1.0)
    order_review_priority = _optional_numeric_series(frame, "feature_order_review_priority_score").clip(0.0, 1.0)
    pca_structure_outlier = _optional_numeric_series(frame, "feature_pca_structure_outlier_flag").clip(0.0, 1.0)

    core_evidence_available = model_use_flag.notna() & same_discount_available.notna() & discount_evidence_strength.notna()
    evidence_supported = core_evidence_available & model_use_flag.ge(1.0) & (
        same_discount_available.ge(1.0)
        | same_discount_event_count.ge(2.0)
        | discount_evidence_strength.ge(0.45)
    )
    conflicted = core_evidence_available & (
        model_use_flag.le(0.0)
        | discount_evidence_strength.lt(0.35)
        | order_review_priority.ge(0.55)
        | pca_structure_outlier.eq(1.0)
    )
    review_required = core_evidence_available & ~evidence_supported & ~conflicted

    return _state_series(
        frame.index,
        default=_CONTEXT_WEAK_OR_CONFLICTED,
        unavailable=~core_evidence_available,
        ordered_conditions=(
            (evidence_supported, _CONTEXT_EVIDENCE_SUPPORTED),
            (review_required, _CONTEXT_REVIEW_REQUIRED),
        ),
    )


def _build_capital_deployment_posture(
    *,
    trust_floor_state: pd.Series,
    speculative_capital_state: pd.Series,
    replenishment_state: pd.Series,
    context_quality_state: pd.Series,
) -> pd.Series:
    unavailable = (
        trust_floor_state.eq(_UNAVAILABLE)
        | speculative_capital_state.eq(_UNAVAILABLE)
        | replenishment_state.eq(_UNAVAILABLE)
        | context_quality_state.eq(_UNAVAILABLE)
    )
    protect_floor = trust_floor_state.eq(_TRUST_FLOOR_PRESSURE_PROTECT)
    review_speculative = (
        ~protect_floor
        & speculative_capital_state.eq(_SPECULATIVE_CAPITAL_HIGH)
        & context_quality_state.ne(_CONTEXT_EVIDENCE_SUPPORTED)
    )
    monitor_capital = ~protect_floor & speculative_capital_state.eq(_SPECULATIVE_CAPITAL_WATCH)

    return _state_series(
        trust_floor_state.index,
        default=_POSTURE_NO_NEW_SIGNAL,
        unavailable=unavailable,
        ordered_conditions=(
            (protect_floor, _POSTURE_PROTECT_TRUST_FLOOR),
            (review_speculative, _POSTURE_REVIEW_SPECULATIVE_CAPITAL),
            (monitor_capital, _POSTURE_MONITOR_CAPITAL),
        ),
        unavailable_value=_POSTURE_REVIEW_UNAVAILABLE,
    )


def _build_reason_summary(
    *,
    trust_floor_state: pd.Series,
    speculative_capital_state: pd.Series,
    replenishment_state: pd.Series,
    context_quality_state: pd.Series,
    deployment_posture: pd.Series,
) -> pd.Series:
    return pd.Series(
        [
            ";".join(
                [
                    f"trust_floor={trust_floor}",
                    f"capital={capital}",
                    f"replenishment={replenishment}",
                    f"context={context}",
                    f"posture={posture}",
                ]
            )
            for trust_floor, capital, replenishment, context, posture in zip(
                trust_floor_state.astype(str),
                speculative_capital_state.astype(str),
                replenishment_state.astype(str),
                context_quality_state.astype(str),
                deployment_posture.astype(str),
            )
        ],
        index=trust_floor_state.index,
        dtype="object",
    )


def _optional_numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def _state_series(
    index: pd.Index,
    *,
    default: str,
    unavailable: pd.Series,
    ordered_conditions: tuple[tuple[pd.Series, str], ...],
    unavailable_value: str = _UNAVAILABLE,
) -> pd.Series:
    state = pd.Series(default, index=index, dtype="object")
    state.loc[unavailable.reindex(index, fill_value=True).astype(bool)] = unavailable_value
    for condition, value in ordered_conditions:
        condition_aligned = condition.reindex(index, fill_value=False).astype(bool)
        state.loc[condition_aligned] = value
    return state