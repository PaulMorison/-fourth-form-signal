from __future__ import annotations

"""Governed order-decision diagnostics derived from existing demand evidence.

Canon ownership:
- explains why a row remains risky to over-order after baseline/uplift/
  elasticity hardening
- derives only from already-governed engineered features
- provides review-only diagnostics for backtesting, scoring, and reporting
- does not create a second decision framework or leak realised outcomes into
  model-use features
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_order_risk_reason_same_discount_weak_flag",
    "feature_order_risk_reason_elasticity_weak_flag",
    "feature_order_risk_reason_uplift_weak_flag",
    "feature_order_risk_reason_base_trend_falling_flag",
    "feature_order_risk_reason_launch_total_conflict_flag",
    "feature_order_risk_reason_stock_vs_supported_gap_high_flag",
    "feature_order_risk_reason_sparse_history_flag",
    "feature_order_risk_reason_multi_driver_count",
    "feature_order_risk_overallocation_score",
    "feature_order_support_strength_score",
    "feature_order_review_priority_score",
)

ORDER_DECISION_DIAGNOSTICS_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    *ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS,
)

SAME_DISCOUNT_HISTORY_BUCKET_ORDER: tuple[str, ...] = (
    "no_history",
    "low_history",
    "adequate_history",
    "strong_history",
)
CONFIDENCE_BUCKET_ORDER: tuple[str, ...] = (
    "low_confidence",
    "medium_confidence",
    "high_confidence",
)
BASE_DEMAND_GROWTH_BUCKET_ORDER: tuple[str, ...] = (
    "falling_base",
    "flat_base",
    "growing_base",
)
WINDOW_CONFLICT_BUCKET_ORDER: tuple[str, ...] = (
    "no_conflict",
    "moderate_conflict",
    "high_conflict",
)

_LOW_HISTORY_MAX_EVENTS = 1.0
_ADEQUATE_HISTORY_MAX_EVENTS = 3.0
_LOW_CONFIDENCE_MAX = 0.35
_HIGH_CONFIDENCE_MIN = 0.70
_BASE_FALLING_MAX = -0.05
_BASE_GROWING_MIN = 0.05
_MODERATE_CONFLICT_MIN = 0.25
_HIGH_CONFLICT_MIN = 0.55
_HIGH_STOCK_GAP_SHARE_MIN = 0.25
_HIGH_ALLOCATION_RISK_MIN = 0.55
_LOW_SUPPORT_STRENGTH_MAX = 0.45
_HIGH_REVIEW_PRIORITY_MIN = 0.55
_UPLIFT_MATERIALITY_RATIO_MIN = 0.25
_UPLIFT_MATERIALITY_UNITS_MIN = 2.0


def apply_ft_order_decision_diagnostics(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append review-only order-risk diagnostics from governed evidence seams."""

    del reference_frame
    working = frame.copy()
    event_count = ensure_numeric_series(working, "feature_same_discount_prior_event_count")
    same_discount_available = ensure_numeric_series(working, "feature_same_discount_history_available_flag").clip(
        lower=0.0,
        upper=1.0,
    )
    discount_evidence_strength = ensure_numeric_series(working, "feature_discount_evidence_strength_score").clip(
        lower=0.0,
        upper=1.0,
    )
    elasticity_confidence = ensure_numeric_series(working, "feature_discount_elasticity_confidence_score").clip(
        lower=0.0,
        upper=1.0,
    )
    elasticity_event_count = ensure_numeric_series(working, "feature_discount_response_event_count")
    uplift_confidence = ensure_numeric_series(working, "feature_uplift_confidence_score").clip(
        lower=0.0,
        upper=1.0,
    )
    uplift_support_flag = ensure_numeric_series(working, "feature_uplift_demand_support_flag").clip(
        lower=0.0,
        upper=1.0,
    )
    trend_30d_vs_56d = ensure_numeric_series(working, "feature_non_promo_base_trend_30d_vs_56d", default=float("nan"))
    trend_30d_vs_84d = ensure_numeric_series(working, "feature_non_promo_base_trend_30d_vs_84d", default=float("nan"))
    recent_acceleration = ensure_numeric_series(working, "feature_non_promo_recent_acceleration_score", default=float("nan"))
    history_available = ensure_numeric_series(working, "feature_non_promo_history_available_flag").clip(
        lower=0.0,
        upper=1.0,
    )
    low_history_flag = ensure_numeric_series(working, "feature_non_promo_low_history_flag").clip(
        lower=0.0,
        upper=1.0,
    )
    sparse_history_penalty = ensure_numeric_series(working, "feature_sparse_history_penalty").clip(
        lower=0.0,
        upper=1.0,
    )
    conflict_score = ensure_numeric_series(
        working,
        "feature_total_window_pressure_vs_launch_support_conflict_score",
    ).clip(lower=0.0, upper=1.0)
    allocation_gap_units = ensure_numeric_series(working, "feature_allocation_vs_supported_total_gap_units", default=float("nan"))
    allocation_risk_score = ensure_numeric_series(working, "feature_allocation_risk_over_uplift_score").clip(
        lower=0.0,
        upper=1.0,
    )
    stock_basis_units = ensure_numeric_series(working, "stock_basis_units", default=float("nan"))
    supported_total_units = ensure_numeric_series(
        working,
        "feature_expected_total_units_from_baseline_plus_uplift",
        default=float("nan"),
    )

    same_discount_weak_flag = (
        same_discount_available.le(0.0)
        | event_count.le(_LOW_HISTORY_MAX_EVENTS)
        | discount_evidence_strength.lt(_LOW_SUPPORT_STRENGTH_MAX)
    ).astype(float)
    elasticity_weak_flag = (
        elasticity_confidence.lt(_LOW_CONFIDENCE_MAX)
        | elasticity_event_count.lt(2.0)
    ).astype(float)
    uplift_weak_flag = (
        uplift_support_flag.le(0.0)
        | uplift_confidence.lt(_LOW_SUPPORT_STRENGTH_MAX)
    ).astype(float)
    base_trend_falling_flag = (
        history_available.eq(1.0)
        & (
            recent_acceleration.lt(_BASE_FALLING_MAX)
            | trend_30d_vs_56d.lt(_BASE_FALLING_MAX)
            | trend_30d_vs_84d.lt(_BASE_FALLING_MAX)
        )
    ).astype(float)
    launch_total_conflict_flag = conflict_score.ge(_HIGH_CONFLICT_MIN).astype(float)
    supported_denominator = pd.concat(
        [
            stock_basis_units.where(stock_basis_units > 0.0),
            supported_total_units.where(supported_total_units > 0.0),
        ],
        axis=1,
    ).max(axis=1, skipna=True)
    stock_vs_supported_gap_share = _nan_ratio(
        allocation_gap_units.clip(lower=0.0),
        supported_denominator,
    ).clip(lower=0.0, upper=1.0)
    stock_vs_supported_gap_high_flag = (
        stock_vs_supported_gap_share.ge(_HIGH_STOCK_GAP_SHARE_MIN)
        | allocation_risk_score.ge(_HIGH_ALLOCATION_RISK_MIN)
    ).astype(float)
    sparse_history_flag = (
        low_history_flag.eq(1.0)
        | sparse_history_penalty.ge(0.5)
        | event_count.le(0.0)
    ).astype(float)
    multi_driver_count = pd.concat(
        [
            same_discount_weak_flag,
            elasticity_weak_flag,
            uplift_weak_flag,
            base_trend_falling_flag,
            launch_total_conflict_flag,
            stock_vs_supported_gap_high_flag,
            sparse_history_flag,
        ],
        axis=1,
    ).sum(axis=1).astype("float64")

    support_strength_score = _rowwise_nanmean(
        [
            same_discount_available,
            (event_count / 4.0).clip(lower=0.0, upper=1.0),
            discount_evidence_strength,
            elasticity_confidence,
            uplift_confidence,
            history_available,
        ]
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    overallocation_score = _rowwise_nanmean(
        [
            allocation_risk_score,
            conflict_score,
            stock_vs_supported_gap_share,
            (1.0 - support_strength_score),
            (multi_driver_count / 7.0).clip(lower=0.0, upper=1.0),
        ]
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    review_priority_score = _rowwise_nanmean(
        [
            overallocation_score,
            conflict_score,
            (1.0 - support_strength_score),
            stock_vs_supported_gap_high_flag,
            same_discount_weak_flag,
            uplift_weak_flag,
        ]
    ).fillna(0.0).clip(lower=0.0, upper=1.0)

    derived_columns = pd.DataFrame(
        {
            "feature_order_risk_reason_same_discount_weak_flag": same_discount_weak_flag,
            "feature_order_risk_reason_elasticity_weak_flag": elasticity_weak_flag,
            "feature_order_risk_reason_uplift_weak_flag": uplift_weak_flag,
            "feature_order_risk_reason_base_trend_falling_flag": base_trend_falling_flag,
            "feature_order_risk_reason_launch_total_conflict_flag": launch_total_conflict_flag,
            "feature_order_risk_reason_stock_vs_supported_gap_high_flag": stock_vs_supported_gap_high_flag,
            "feature_order_risk_reason_sparse_history_flag": sparse_history_flag,
            "feature_order_risk_reason_multi_driver_count": multi_driver_count,
            "feature_order_risk_overallocation_score": overallocation_score,
            "feature_order_support_strength_score": support_strength_score,
            "feature_order_review_priority_score": review_priority_score,
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def build_order_decision_bucket_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return governed readable bucket labels for allocation error decomposition."""

    working = _ensure_diagnostic_columns(frame)
    same_discount_event_count = ensure_numeric_series(working, "feature_same_discount_prior_event_count")
    same_discount_history_available = ensure_numeric_series(
        working,
        "feature_same_discount_history_available_flag",
    )
    elasticity_confidence = ensure_numeric_series(working, "feature_discount_elasticity_confidence_score")
    uplift_confidence = ensure_numeric_series(working, "feature_uplift_confidence_score")
    recent_acceleration = ensure_numeric_series(working, "feature_non_promo_recent_acceleration_score", default=float("nan"))
    trend_30d_vs_56d = ensure_numeric_series(working, "feature_non_promo_base_trend_30d_vs_56d", default=float("nan"))
    trend_30d_vs_84d = ensure_numeric_series(working, "feature_non_promo_base_trend_30d_vs_84d", default=float("nan"))
    base_growth_flag = ensure_numeric_series(working, "feature_non_promo_base_demand_growing_flag")
    conflict_score = ensure_numeric_series(
        working,
        "feature_total_window_pressure_vs_launch_support_conflict_score",
    ).clip(lower=0.0, upper=1.0)

    return pd.DataFrame(
        {
            "same_discount_history_bucket": classify_same_discount_history_bucket(
                same_discount_event_count=same_discount_event_count,
                same_discount_history_available=same_discount_history_available,
            ),
            "elasticity_confidence_bucket": classify_confidence_bucket(elasticity_confidence),
            "uplift_confidence_bucket": classify_confidence_bucket(uplift_confidence),
            "base_demand_growth_bucket": classify_base_demand_growth_bucket(
                recent_acceleration=recent_acceleration,
                trend_30d_vs_56d=trend_30d_vs_56d,
                trend_30d_vs_84d=trend_30d_vs_84d,
                base_growth_flag=base_growth_flag,
            ),
            "window_conflict_bucket": classify_window_conflict_bucket(conflict_score),
        },
        index=working.index,
    )


def build_live_order_decision_diagnostics(
    frame: pd.DataFrame,
    *,
    raw_predicted_units: pd.Series,
    predicted_units: pd.Series,
) -> pd.DataFrame:
    """Build compact per-row diagnostics for live scoring and reporting artifacts."""

    working = _ensure_diagnostic_columns(frame)
    bucket_frame = build_order_decision_bucket_frame(working)
    baseline_expected_units = ensure_numeric_series(
        working,
        "feature_expected_baseline_units_promo_window",
        default=float("nan"),
    )
    uplift_supported_units = ensure_numeric_series(
        working,
        "feature_expected_incremental_uplift_units_same_discount",
        default=float("nan"),
    )
    supported_total_units = ensure_numeric_series(
        working,
        "feature_expected_total_units_from_baseline_plus_uplift",
        default=float("nan"),
    )
    elasticity_confidence = ensure_numeric_series(working, "feature_discount_elasticity_confidence_score")
    elasticity_direction = ensure_numeric_series(working, "feature_discount_response_direction_consistent_flag")
    elasticity_abs = ensure_numeric_series(working, "feature_discount_elasticity_abs", default=float("nan"))
    uplift_support_flag = ensure_numeric_series(working, "feature_uplift_demand_support_flag")
    same_discount_available = ensure_numeric_series(working, "feature_same_discount_history_available_flag")
    probability_model_use_flag = ensure_numeric_series(working, "feature_probability_model_use_flag")
    review_priority = ensure_numeric_series(working, "feature_order_review_priority_score")
    support_strength = ensure_numeric_series(working, "feature_order_support_strength_score")

    sizing_driver = classify_order_sizing_driver(
        baseline_expected_units=baseline_expected_units,
        uplift_supported_units=uplift_supported_units,
        uplift_support_flag=uplift_support_flag,
    )
    cap_reason = classify_order_cap_reason(
        frame=working,
        raw_predicted_units=raw_predicted_units,
        predicted_units=predicted_units,
        sizing_driver=sizing_driver,
        baseline_expected_units=baseline_expected_units,
        supported_total_units=supported_total_units,
        elasticity_confidence=elasticity_confidence,
        elasticity_direction=elasticity_direction,
        elasticity_abs=elasticity_abs,
    )
    same_discount_present_flag = same_discount_available.ge(1.0).astype(float)
    usable_elasticity_flag = (
        elasticity_confidence.ge(_LOW_CONFIDENCE_MAX) & elasticity_direction.eq(1.0)
    ).astype(float)
    strong_uplift_support_flag = (
        uplift_support_flag.eq(1.0)
        & ensure_numeric_series(working, "feature_uplift_confidence_score").ge(0.60)
    ).astype(float)
    evidence_conflict_review_flag = (
        ensure_numeric_series(working, "feature_order_risk_reason_launch_total_conflict_flag").eq(1.0)
        & review_priority.ge(_HIGH_REVIEW_PRIORITY_MIN)
    ).astype(float)
    weak_fallback_logic_flag = (
        sizing_driver.eq("fallback") | support_strength.lt(_LOW_SUPPORT_STRENGTH_MAX)
    ).astype(float)

    identifier_frame = pd.DataFrame(index=working.index)
    for column_name in (
        "promotion_row_key",
        "store_number",
        "store_number_key",
        "promotion_header_key",
        "sku_number",
        "sku_number_key",
    ):
        if column_name in working.columns:
            identifier_frame[column_name] = working[column_name]

    return pd.concat(
        [
            identifier_frame,
            bucket_frame,
            pd.DataFrame(
                {
                    "evidence_same_discount_present_flag": same_discount_present_flag,
                    "evidence_usable_elasticity_flag": usable_elasticity_flag,
                    "evidence_strong_uplift_support_flag": strong_uplift_support_flag,
                    "evidence_probability_model_use_flag": probability_model_use_flag.clip(lower=0.0, upper=1.0),
                    "weak_fallback_logic_flag": weak_fallback_logic_flag,
                    "order_sizing_driver": sizing_driver,
                    "order_cap_reason": cap_reason,
                    "evidence_conflict_review_candidate_flag": evidence_conflict_review_flag,
                    "order_risk_driver_combination": build_order_risk_driver_combination(working),
                    "feature_order_risk_reason_same_discount_weak_flag": ensure_numeric_series(
                        working,
                        "feature_order_risk_reason_same_discount_weak_flag",
                    ),
                    "feature_order_risk_reason_elasticity_weak_flag": ensure_numeric_series(
                        working,
                        "feature_order_risk_reason_elasticity_weak_flag",
                    ),
                    "feature_order_risk_reason_uplift_weak_flag": ensure_numeric_series(
                        working,
                        "feature_order_risk_reason_uplift_weak_flag",
                    ),
                    "feature_order_risk_reason_base_trend_falling_flag": ensure_numeric_series(
                        working,
                        "feature_order_risk_reason_base_trend_falling_flag",
                    ),
                    "feature_order_risk_reason_launch_total_conflict_flag": ensure_numeric_series(
                        working,
                        "feature_order_risk_reason_launch_total_conflict_flag",
                    ),
                    "feature_order_risk_reason_stock_vs_supported_gap_high_flag": ensure_numeric_series(
                        working,
                        "feature_order_risk_reason_stock_vs_supported_gap_high_flag",
                    ),
                    "feature_order_risk_reason_sparse_history_flag": ensure_numeric_series(
                        working,
                        "feature_order_risk_reason_sparse_history_flag",
                    ),
                    "feature_order_risk_reason_multi_driver_count": ensure_numeric_series(
                        working,
                        "feature_order_risk_reason_multi_driver_count",
                    ),
                    "feature_order_risk_overallocation_score": ensure_numeric_series(
                        working,
                        "feature_order_risk_overallocation_score",
                    ),
                    "feature_order_support_strength_score": support_strength,
                    "feature_order_review_priority_score": review_priority,
                    "raw_predicted_units_sold": pd.to_numeric(raw_predicted_units, errors="coerce"),
                    "predicted_units_sold": pd.to_numeric(predicted_units, errors="coerce"),
                },
                index=working.index,
            ),
        ],
        axis=1,
    )


def classify_same_discount_history_bucket(
    *,
    same_discount_event_count: pd.Series,
    same_discount_history_available: pd.Series,
) -> pd.Series:
    bucket = pd.Series("strong_history", index=same_discount_event_count.index, dtype="object")
    bucket = bucket.where(same_discount_event_count.gt(_ADEQUATE_HISTORY_MAX_EVENTS), "adequate_history")
    bucket = bucket.where(same_discount_event_count.gt(_LOW_HISTORY_MAX_EVENTS), "low_history")
    bucket = bucket.where(
        same_discount_history_available.gt(0.0) & same_discount_event_count.gt(0.0),
        "no_history",
    )
    return bucket


def classify_confidence_bucket(confidence: pd.Series) -> pd.Series:
    bucket = pd.Series("high_confidence", index=confidence.index, dtype="object")
    bucket = bucket.where(confidence.ge(_HIGH_CONFIDENCE_MIN), "medium_confidence")
    bucket = bucket.where(confidence.ge(_LOW_CONFIDENCE_MAX), "low_confidence")
    return bucket


def classify_base_demand_growth_bucket(
    *,
    recent_acceleration: pd.Series,
    trend_30d_vs_56d: pd.Series,
    trend_30d_vs_84d: pd.Series,
    base_growth_flag: pd.Series,
) -> pd.Series:
    bucket = pd.Series("flat_base", index=base_growth_flag.index, dtype="object")
    growing_mask = (
        base_growth_flag.eq(1.0)
        | recent_acceleration.ge(_BASE_GROWING_MIN)
        | trend_30d_vs_56d.ge(_BASE_GROWING_MIN)
        | trend_30d_vs_84d.ge(_BASE_GROWING_MIN)
    )
    falling_mask = (
        recent_acceleration.le(_BASE_FALLING_MAX)
        | trend_30d_vs_56d.le(_BASE_FALLING_MAX)
        | trend_30d_vs_84d.le(_BASE_FALLING_MAX)
    )
    bucket = bucket.where(~growing_mask, "growing_base")
    bucket = bucket.where(~falling_mask, "falling_base")
    return bucket


def classify_window_conflict_bucket(conflict_score: pd.Series) -> pd.Series:
    bucket = pd.Series("high_conflict", index=conflict_score.index, dtype="object")
    bucket = bucket.where(conflict_score.ge(_HIGH_CONFLICT_MIN), "moderate_conflict")
    bucket = bucket.where(conflict_score.ge(_MODERATE_CONFLICT_MIN), "no_conflict")
    return bucket


def classify_order_sizing_driver(
    *,
    baseline_expected_units: pd.Series,
    uplift_supported_units: pd.Series,
    uplift_support_flag: pd.Series,
) -> pd.Series:
    uplift_material_mask = uplift_support_flag.eq(1.0) & uplift_supported_units.ge(
        np.maximum(_UPLIFT_MATERIALITY_UNITS_MIN, baseline_expected_units.fillna(0.0) * _UPLIFT_MATERIALITY_RATIO_MIN)
    )
    driver = pd.Series("fallback", index=baseline_expected_units.index, dtype="object")
    driver = driver.where(~baseline_expected_units.gt(0.0), "baseline")
    driver = driver.where(~uplift_material_mask, "uplift")
    return driver


def classify_order_cap_reason(
    *,
    frame: pd.DataFrame,
    raw_predicted_units: pd.Series,
    predicted_units: pd.Series,
    sizing_driver: pd.Series,
    baseline_expected_units: pd.Series,
    supported_total_units: pd.Series,
    elasticity_confidence: pd.Series,
    elasticity_direction: pd.Series,
    elasticity_abs: pd.Series,
) -> pd.Series:
    working = _ensure_diagnostic_columns(frame)
    cap_applied = pd.to_numeric(predicted_units, errors="coerce").lt(pd.to_numeric(raw_predicted_units, errors="coerce") - 1e-9)
    launch_conflict_flag = ensure_numeric_series(working, "feature_order_risk_reason_launch_total_conflict_flag")
    review_priority = ensure_numeric_series(working, "feature_order_review_priority_score")
    allocation_risk_score = ensure_numeric_series(working, "feature_allocation_risk_over_uplift_score")
    same_discount_uplift_ratio = ensure_numeric_series(
        working,
        "feature_same_discount_prior_uplift_ratio_avg",
        default=float("nan"),
    )

    reason = sizing_driver.copy()
    reason = reason.where(
        ~(launch_conflict_flag.eq(1.0) & review_priority.ge(_HIGH_REVIEW_PRIORITY_MIN)),
        "launch_vs_total_conflict_review_rule",
    )
    elasticity_restraint_mask = (
        cap_applied
        & elasticity_confidence.ge(_LOW_CONFIDENCE_MAX)
        & elasticity_direction.eq(1.0)
        & elasticity_abs.notna()
        & same_discount_uplift_ratio.notna()
        & elasticity_abs.lt(same_discount_uplift_ratio)
    )
    reason = reason.where(~elasticity_restraint_mask, "elasticity_restraint")
    reason = reason.where(
        ~(cap_applied & allocation_risk_score.ge(0.15) & ~elasticity_restraint_mask),
        "allocation_discipline_restraint",
    )
    reason = reason.where(
        ~(
            cap_applied
            & sizing_driver.eq("baseline")
            & baseline_expected_units.gt(0.0)
        ),
        "baseline",
    )
    reason = reason.where(
        ~(
            cap_applied
            & sizing_driver.eq("uplift")
            & supported_total_units.gt(baseline_expected_units)
        ),
        "uplift_supported_total",
    )
    return reason


def build_order_risk_driver_combination(frame: pd.DataFrame) -> pd.Series:
    working = _ensure_diagnostic_columns(frame)
    driver_columns = (
        ("feature_order_risk_reason_same_discount_weak_flag", "same_discount_weak"),
        ("feature_order_risk_reason_elasticity_weak_flag", "elasticity_weak"),
        ("feature_order_risk_reason_uplift_weak_flag", "uplift_weak"),
        ("feature_order_risk_reason_base_trend_falling_flag", "base_trend_falling"),
        ("feature_order_risk_reason_launch_total_conflict_flag", "launch_total_conflict"),
        ("feature_order_risk_reason_stock_vs_supported_gap_high_flag", "stock_vs_supported_gap_high"),
        ("feature_order_risk_reason_sparse_history_flag", "sparse_history"),
    )
    labels = []
    for row_index in working.index:
        active = [
            label
            for column_name, label in driver_columns
            if float(pd.to_numeric(working.at[row_index, column_name], errors="coerce") or 0.0) >= 1.0
        ]
        labels.append("+".join(active) if active else "no_risk_driver")
    return pd.Series(labels, index=working.index, dtype="object")


def _ensure_diagnostic_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if set(ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS).issubset(frame.columns):
        return frame
    return apply_ft_order_decision_diagnostics(frame)


def _nan_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator_clean = pd.to_numeric(denominator, errors="coerce").where(
        pd.to_numeric(denominator, errors="coerce").ne(0.0)
    )
    return pd.to_numeric(numerator, errors="coerce").divide(denominator_clean).replace([np.inf, -np.inf], np.nan)


def _rowwise_nanmean(series_list: list[pd.Series]) -> pd.Series:
    combined = pd.concat([pd.to_numeric(series, errors="coerce") for series in series_list], axis=1)
    return combined.mean(axis=1, skipna=True).astype("float64")