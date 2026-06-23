from __future__ import annotations

"""Allocation-aware forecast calibration for promotions unit predictions."""

import numpy as np
import pandas as pd


ALLOCATION_AWARE_CAP_SCORE_THRESHOLD = 0.15
ALLOCATION_AWARE_LOW_CONFIDENCE_SLACK = 1.5


def compute_allocation_aware_cap_units(
    frame: pd.DataFrame,
    predicted_units: pd.Series | np.ndarray,
) -> pd.Series:
    """Compute allocation-aware order/risk ceiling units (order path only).

    Phase 3: this cap must not overwrite customer demand forecasts. Demand stays
    on the raw model path; this series is for order policy and diagnostics.
    """

    raw_prediction = pd.Series(predicted_units, index=frame.index, dtype="float64").clip(lower=0.0)
    baseline_units = _first_present_numeric_column(
        frame,
        ("feature_expected_baseline_units_promo_window", "feature_baseline_units_expected_promo_window"),
    )
    expected_units = _numeric_column(frame, "feature_probability_expected_units_consensus")
    uplift_supported_units = _first_present_numeric_column(
        frame,
        ("feature_expected_incremental_uplift_units_same_discount", "feature_probability_uplift_supported_units"),
    )
    uplift_upper_units = _first_present_numeric_column(
        frame,
        ("feature_expected_incremental_uplift_units_same_discount", "feature_probability_uplift_upper_units"),
    )
    tail_risk = _numeric_column(frame, "feature_probability_tail_risk_consensus").fillna(0.0).clip(0.0, 1.0)
    demand_confidence = _numeric_column(frame, "feature_probability_demand_confidence_score").fillna(0.0).clip(0.0, 1.0)
    uplift_confidence = _first_present_numeric_column(
        frame,
        ("feature_uplift_confidence_score", "feature_probability_uplift_confidence"),
    ).fillna(0.0).clip(0.0, 1.0)
    discipline_score = _first_present_numeric_column(
        frame,
        ("feature_allocation_risk_over_uplift_score", "feature_probability_allocation_discipline_score"),
    ).fillna(0.0).clip(
        0.0,
        1.0,
    )
    uplift_discipline_score = _first_present_numeric_column(
        frame,
        ("feature_allocation_risk_over_uplift_score", "feature_uplift_allocation_discipline_score"),
    ).fillna(0.0).clip(
        0.0,
        1.0,
    )
    elasticity_confidence = _numeric_column(frame, "feature_discount_elasticity_confidence_score").fillna(0.0).clip(0.0, 1.0)
    evidence_strength = _numeric_column(frame, "feature_discount_evidence_strength_score").fillna(0.0).clip(0.0, 1.0)
    base_demand_growing_flag = _numeric_column(frame, "feature_non_promo_base_demand_growing_flag").fillna(0.0).clip(0.0, 1.0)
    uplift_support_flag = _numeric_column(frame, "feature_uplift_demand_support_flag").fillna(0.0).eq(1.0)
    model_use_flag = _numeric_column(frame, "feature_probability_model_use_flag").fillna(0.0).eq(1.0)
    supported_expected_units = _first_present_numeric_column(
        frame,
        ("feature_expected_total_units_from_baseline_plus_uplift",),
    )
    supported_expected_units = supported_expected_units.where(
        supported_expected_units.notna(),
        (baseline_units + uplift_supported_units),
    ).where(
        uplift_supported_units.notna(),
        supported_expected_units.where(supported_expected_units.notna(), expected_units),
    )
    probability_upper_bound = expected_units * (
        1.0 + tail_risk + ((1.0 - demand_confidence) * ALLOCATION_AWARE_LOW_CONFIDENCE_SLACK)
    )
    uplift_upper_bound = (baseline_units + uplift_upper_units).where(
        uplift_upper_units.notna(),
        probability_upper_bound,
    )
    effective_upper_bound = uplift_upper_bound.where(uplift_upper_bound.notna(), probability_upper_bound)
    effective_expected_units = supported_expected_units.where(supported_expected_units.notna(), expected_units)
    effective_discipline_score = uplift_discipline_score.where(
        uplift_discipline_score.gt(0.0),
        discipline_score,
    )
    effective_confidence = _rowwise_nanmean(
        uplift_confidence.where(uplift_confidence.gt(0.0), np.nan),
        demand_confidence.where(demand_confidence.gt(0.0), np.nan),
        elasticity_confidence.where(elasticity_confidence.gt(0.0), np.nan),
        evidence_strength.where(evidence_strength.gt(0.0), np.nan),
    ).fillna(0.0)
    effective_upper_bound = effective_upper_bound * (1.0 + (0.10 * base_demand_growing_flag))
    cap_mask = (
        (model_use_flag | uplift_support_flag)
        & effective_expected_units.gt(0.0)
        & effective_upper_bound.notna()
        & effective_discipline_score.ge(ALLOCATION_AWARE_CAP_SCORE_THRESHOLD)
        & effective_confidence.gt(0.0)
    )
    capped_prediction = raw_prediction.where(
        ~cap_mask,
        np.minimum(raw_prediction, effective_upper_bound),
    )
    return capped_prediction.clip(lower=0.0)


def apply_allocation_aware_units_cap(
    frame: pd.DataFrame,
    predicted_units: pd.Series | np.ndarray,
) -> pd.Series:
    """Return allocation-aware order/risk ceiling units.

    Backwards-compatible alias for ``compute_allocation_aware_cap_units``. Phase 3
    callers must not treat this output as customer demand; use raw model output
    for ``calibrated_predicted_units_*`` / ``predicted_units_sold``.
    """
    return compute_allocation_aware_cap_units(frame, predicted_units)


def _numeric_column(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def _first_present_numeric_column(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    return candidate_frame.bfill(axis=1).iloc[:, 0]


def _rowwise_nanmean(*series_list: pd.Series) -> pd.Series:
    combined = pd.concat([pd.to_numeric(series, errors="coerce") for series in series_list], axis=1)
    return combined.mean(axis=1, skipna=True).astype("float64")
