from __future__ import annotations

"""Governed demand-uplift feature module.

Canon ownership:
- Separates promo-window baseline demand from incremental uplift demand.
- Reuses leakage-safe prior completed promotion history only.
- Refuses to fabricate uplift confidence when the governed baseline inputs are
  missing or contradictory.
- Preserves the promotion x sku x store row grain.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import (
    ensure_numeric_series,
    first_non_null_series,
)
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    coerce_promotions_frame_types,
    normalize_discount_decimal,
)


DEMAND_UPLIFT_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_baseline_units_expected_promo_window",
    "feature_baseline_units_expected_first_7_days",
    "feature_actual_units_minus_baseline",
    "feature_actual_units_minus_baseline_first_7_days",
    "feature_uplift_units_expected_total",
    "feature_uplift_units_expected_first_7_days",
    "feature_uplift_ratio_total",
    "feature_uplift_ratio_first_7_days",
    "feature_uplift_confidence_score",
    "feature_uplift_history_event_count",
    "feature_uplift_same_discount_event_count",
    "feature_uplift_same_or_better_discount_event_count",
    "feature_uplift_evidence_class",
    "feature_uplift_instability_score",
    "feature_uplift_overallocation_risk_score",
    "feature_leadup_units_pressure",
    "feature_launch_window_units_pressure",
    "feature_total_promo_units_pressure",
    "feature_window_blend_conflict_score",
    "feature_probability_uplift_supported_units",
    "feature_probability_uplift_upper_units",
    "feature_probability_uplift_tail_risk",
    "feature_probability_uplift_confidence",
    "feature_uplift_basket_support_score",
    "feature_uplift_multi_item_support_score",
    "feature_uplift_companion_strength_score",
    "feature_stockout_vs_overstock_conflict_score",
    "feature_overallocation_supported_by_uplift_flag",
    "feature_order_recommendation_confidence_from_uplift",
    "feature_order_recommendation_confidence_from_history",
    "feature_order_recommendation_confidence_from_probability",
)

DEMAND_UPLIFT_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_actual_units_minus_baseline",
    "feature_actual_units_minus_baseline_first_7_days",
)

DEMAND_UPLIFT_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    column_name
    for column_name in DEMAND_UPLIFT_FEATURE_COLUMNS
    if column_name not in DEMAND_UPLIFT_REVIEW_ONLY_FEATURE_COLUMNS
)

_FIRST_7_DAY_WINDOW_DAYS = 7.0
_BASELINE_CONSISTENCY_TOLERANCE_UNITS = 0.5
_LOW_CONFIDENCE_SLACK = 1.5


@dataclass(frozen=True)
class _UpliftHistorySummary:
    same_discount_event_count: float
    same_or_better_discount_event_count: float
    uplift_history_event_count: float
    uplift_mean_units: float
    uplift_std_units: float
    uplift_first7_mean_units: float
    uplift_first7_std_units: float


def apply_ft_demand_uplift(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append governed uplift, basket-support, and window-pressure features."""

    candidate = frame.copy()
    history_source = reference_frame if reference_frame is not None else candidate
    candidate_typed = coerce_promotions_frame_types(candidate)
    history_typed = coerce_promotions_frame_types(history_source)

    baseline_daily_units = _resolve_baseline_daily_units(candidate_typed)
    promo_window_days = _resolve_promo_window_days(candidate_typed)
    baseline_expected_units = _resolve_baseline_expected_units(
        candidate_typed,
        baseline_daily_units=baseline_daily_units,
        promo_window_days=promo_window_days,
    )
    first_7_window_days = promo_window_days.clip(lower=0.0, upper=_FIRST_7_DAY_WINDOW_DAYS)
    baseline_expected_first_7_days = (baseline_daily_units * first_7_window_days).clip(lower=0.0)

    probability_expected_units = ensure_numeric_series(
        candidate_typed,
        "feature_probability_expected_units_consensus",
        default=float("nan"),
    )
    probability_tail_risk = ensure_numeric_series(
        candidate_typed,
        "feature_probability_tail_risk_consensus",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0)
    probability_confidence = ensure_numeric_series(
        candidate_typed,
        "feature_probability_demand_confidence_score",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0)
    probability_model_use_flag = ensure_numeric_series(
        candidate_typed,
        "feature_probability_model_use_flag",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0)

    probability_supported_total_units = _probability_supported_total_units(
        probability_expected_units=probability_expected_units,
        baseline_expected_units=baseline_expected_units,
    )
    probability_supported_first_7_days_units = _scale_total_to_window(
        total_units=probability_supported_total_units,
        promo_window_days=promo_window_days,
        target_window_days=first_7_window_days,
    )
    probability_total_upper_units = _probability_total_upper_units(
        probability_expected_units=probability_expected_units,
        probability_tail_risk=probability_tail_risk,
        probability_confidence=probability_confidence,
    )
    probability_uplift_upper_units = (
        probability_total_upper_units - baseline_expected_units
    ).clip(lower=0.0)

    uplift_history = _build_uplift_history_summary(
        candidate_typed=candidate_typed,
        history_typed=history_typed,
    )
    uplift_mean_units = pd.Series(
        [summary.uplift_mean_units for summary in uplift_history],
        index=candidate.index,
        dtype="float64",
    )
    uplift_std_units = pd.Series(
        [summary.uplift_std_units for summary in uplift_history],
        index=candidate.index,
        dtype="float64",
    )
    uplift_first7_mean_units = pd.Series(
        [summary.uplift_first7_mean_units for summary in uplift_history],
        index=candidate.index,
        dtype="float64",
    )
    uplift_first7_std_units = pd.Series(
        [summary.uplift_first7_std_units for summary in uplift_history],
        index=candidate.index,
        dtype="float64",
    )
    uplift_history_event_count = pd.Series(
        [summary.uplift_history_event_count for summary in uplift_history],
        index=candidate.index,
        dtype="float64",
    )
    uplift_same_discount_event_count = pd.Series(
        [summary.same_discount_event_count for summary in uplift_history],
        index=candidate.index,
        dtype="float64",
    )
    uplift_same_or_better_discount_event_count = pd.Series(
        [summary.same_or_better_discount_event_count for summary in uplift_history],
        index=candidate.index,
        dtype="float64",
    )

    uplift_units_expected_total = probability_supported_total_units.where(
        probability_model_use_flag.eq(1.0),
        uplift_mean_units.clip(lower=0.0),
    ).clip(lower=0.0)
    uplift_units_expected_first_7_days = probability_supported_first_7_days_units.where(
        probability_model_use_flag.eq(1.0),
        uplift_first7_mean_units.clip(lower=0.0),
    ).clip(lower=0.0)

    uplift_instability_score = safe_ratio(
        uplift_std_units,
        uplift_mean_units.abs().where(uplift_mean_units.abs() > 0.0, np.nan),
    ).clip(lower=0.0, upper=5.0)
    uplift_confidence_score = _build_uplift_confidence_score(
        event_count=uplift_history_event_count,
        same_discount_event_count=uplift_same_discount_event_count,
        same_or_better_discount_event_count=uplift_same_or_better_discount_event_count,
        uplift_instability_score=uplift_instability_score,
        history_confidence=ensure_numeric_series(
            candidate_typed,
            "feature_historical_discount_response_confidence",
            default=float("nan"),
        ).clip(lower=0.0, upper=1.0),
        probability_confidence=probability_confidence,
    )

    basket_support_score = _build_uplift_basket_support_score(candidate_typed)
    multi_item_support_score = ensure_numeric_series(
        candidate_typed,
        "feature_probability_sku_in_multi_item_basket",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0)
    companion_strength_score = first_non_null_series(
        candidate_typed,
        (
            "feature_probability_companion_dependency_score",
            "feature_sku_basket_dependency_score",
            "feature_companion_concentration_index",
        ),
    ).clip(lower=0.0, upper=1.0)

    stock_basis_units = _resolve_stock_basis_units(candidate_typed)
    days_until_promo_start = _resolve_days_until_promo_start(candidate_typed)
    leadup_expected_units = (baseline_daily_units * days_until_promo_start).clip(lower=0.0)
    leadup_units_pressure = safe_ratio(
        leadup_expected_units,
        stock_basis_units.where(stock_basis_units > 0.0, np.nan),
    ).clip(lower=0.0, upper=20.0)
    launch_window_units_pressure = safe_ratio(
        baseline_expected_first_7_days + uplift_units_expected_first_7_days,
        stock_basis_units.where(stock_basis_units > 0.0, np.nan),
    ).clip(lower=0.0, upper=20.0)
    total_promo_units_pressure = safe_ratio(
        baseline_expected_units + uplift_units_expected_total,
        stock_basis_units.where(stock_basis_units > 0.0, np.nan),
    ).clip(lower=0.0, upper=20.0)

    uplift_evidence_class = _classify_uplift_evidence(
        uplift_confidence_score=uplift_confidence_score,
        uplift_history_event_count=uplift_history_event_count,
        uplift_instability_score=uplift_instability_score,
    )
    window_blend_conflict_score = (
        leadup_units_pressure.clip(upper=1.0)
        * (1.0 - uplift_confidence_score)
        * (1.0 - safe_ratio(uplift_units_expected_first_7_days, uplift_units_expected_total.where(uplift_units_expected_total > 0.0, np.nan)).clip(lower=0.0, upper=1.0).fillna(0.0))
    ).clip(lower=0.0, upper=1.0)

    allocation_vs_uplift_gap_units = (
        stock_basis_units - uplift_units_expected_total
    ).clip(lower=0.0)
    allocation_vs_probability_upper_gap_units = (
        stock_basis_units - probability_total_upper_units
    ).clip(lower=0.0)
    uplift_overallocation_risk_score = rowwise_nanmean(
        [
            safe_ratio(allocation_vs_uplift_gap_units, stock_basis_units.where(stock_basis_units > 0.0, np.nan)).clip(lower=0.0, upper=1.0),
            safe_ratio(allocation_vs_probability_upper_gap_units, stock_basis_units.where(stock_basis_units > 0.0, np.nan)).clip(lower=0.0, upper=1.0),
            (1.0 - uplift_confidence_score),
            uplift_instability_score.clip(upper=1.0),
        ]
    ).clip(lower=0.0, upper=1.0)

    actual_units_total = _resolve_actual_units_total(candidate_typed)
    actual_units_first_7_days = _resolve_actual_units_first_7_days(candidate_typed)
    actual_units_minus_baseline = (actual_units_total - baseline_expected_units).where(
        actual_units_total.notna(),
        np.nan,
    )
    actual_units_minus_baseline_first_7_days = (
        actual_units_first_7_days - baseline_expected_first_7_days
    ).where(actual_units_first_7_days.notna(), np.nan)

    probability_uplift_tail_risk = probability_tail_risk.where(
        probability_model_use_flag.eq(1.0),
        np.nan,
    )
    probability_uplift_confidence = probability_confidence.where(
        probability_model_use_flag.eq(1.0),
        np.nan,
    )

    expected_leftover_after_baseline = (
        stock_basis_units - baseline_expected_units
    ).clip(lower=0.0)
    expected_leftover_after_uplift = (
        stock_basis_units - (baseline_expected_units + uplift_units_expected_total)
    ).clip(lower=0.0)

    stockout_vs_overstock_conflict_score = rowwise_nanmean(
        [
            safe_ratio(expected_leftover_after_baseline, stock_basis_units.where(stock_basis_units > 0.0, np.nan)).clip(lower=0.0, upper=1.0),
            ensure_numeric_series(candidate_typed, "feature_probability_overallocation_risk_score", default=float("nan")).clip(lower=0.0, upper=1.0),
            ensure_numeric_series(candidate_typed, "feature_lost_sales_risk_score", default=float("nan")).clip(lower=0.0, upper=1.0),
        ]
    ).clip(lower=0.0, upper=1.0)

    overalloc_supported_by_uplift_flag = (
        uplift_units_expected_total >= allocation_vs_uplift_gap_units
    ).astype(float)
    order_confidence_from_uplift = uplift_confidence_score
    order_confidence_from_history = rowwise_nanmean(
        [
            ensure_numeric_series(candidate_typed, "feature_promo_history_evidence_strength", default=float("nan")).clip(lower=0.0, upper=1.0),
            ensure_numeric_series(candidate_typed, "feature_order_evidence_quality_score", default=float("nan")).clip(lower=0.0, upper=1.0),
            ensure_numeric_series(candidate_typed, "feature_historical_discount_response_confidence", default=float("nan")).clip(lower=0.0, upper=1.0),
        ]
    ).clip(lower=0.0, upper=1.0)
    order_confidence_from_probability = probability_uplift_confidence.fillna(0.0).clip(lower=0.0, upper=1.0)

    derived_columns = pd.DataFrame(
        {
            "feature_baseline_units_expected_promo_window": baseline_expected_units,
            "feature_baseline_units_expected_first_7_days": baseline_expected_first_7_days,
            "feature_actual_units_minus_baseline": actual_units_minus_baseline,
            "feature_actual_units_minus_baseline_first_7_days": actual_units_minus_baseline_first_7_days,
            "feature_uplift_units_expected_total": uplift_units_expected_total,
            "feature_uplift_units_expected_first_7_days": uplift_units_expected_first_7_days,
            "feature_uplift_ratio_total": safe_ratio(
                uplift_units_expected_total,
                baseline_expected_units.where(baseline_expected_units > 0.0, np.nan),
            ).clip(lower=0.0, upper=20.0),
            "feature_uplift_ratio_first_7_days": safe_ratio(
                uplift_units_expected_first_7_days,
                baseline_expected_first_7_days.where(baseline_expected_first_7_days > 0.0, np.nan),
            ).clip(lower=0.0, upper=20.0),
            "feature_uplift_confidence_score": uplift_confidence_score,
            "feature_uplift_history_event_count": uplift_history_event_count,
            "feature_uplift_same_discount_event_count": uplift_same_discount_event_count,
            "feature_uplift_same_or_better_discount_event_count": uplift_same_or_better_discount_event_count,
            "feature_uplift_evidence_class": uplift_evidence_class,
            "feature_uplift_instability_score": uplift_instability_score,
            "feature_uplift_overallocation_risk_score": uplift_overallocation_risk_score,
            "feature_leadup_units_pressure": leadup_units_pressure,
            "feature_launch_window_units_pressure": launch_window_units_pressure,
            "feature_total_promo_units_pressure": total_promo_units_pressure,
            "feature_window_blend_conflict_score": window_blend_conflict_score,
            "feature_probability_uplift_supported_units": probability_supported_total_units,
            "feature_probability_uplift_upper_units": probability_uplift_upper_units,
            "feature_probability_uplift_tail_risk": probability_uplift_tail_risk,
            "feature_probability_uplift_confidence": probability_uplift_confidence,
            "feature_uplift_basket_support_score": basket_support_score,
            "feature_uplift_multi_item_support_score": multi_item_support_score,
            "feature_uplift_companion_strength_score": companion_strength_score,
            "feature_stockout_vs_overstock_conflict_score": stockout_vs_overstock_conflict_score,
            "feature_overallocation_supported_by_uplift_flag": overalloc_supported_by_uplift_flag,
            "feature_order_recommendation_confidence_from_uplift": order_confidence_from_uplift,
            "feature_order_recommendation_confidence_from_history": order_confidence_from_history,
            "feature_order_recommendation_confidence_from_probability": order_confidence_from_probability,
        },
        index=candidate.index,
    )
    base_columns = candidate.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _resolve_baseline_daily_units(frame: pd.DataFrame) -> pd.Series:
    baseline_daily_units = first_non_null_series(
        frame,
        ("baseline_daily_units", "feature_pre_promo_baseline_daily_units"),
    )
    if "baseline_daily_units" not in frame.columns and "feature_pre_promo_baseline_daily_units" not in frame.columns:
        raise ValueError(
            "Demand uplift features require baseline daily demand columns: baseline_daily_units or feature_pre_promo_baseline_daily_units."
        )
    if (baseline_daily_units < 0.0).any():
        raise ValueError("Demand uplift features require non-negative baseline daily demand.")
    return baseline_daily_units


def _resolve_promo_window_days(frame: pd.DataFrame) -> pd.Series:
    promo_window_days = first_non_null_series(frame, ("live_promo_window_days", "promo_days"))
    if "live_promo_window_days" not in frame.columns and "promo_days" not in frame.columns:
        raise ValueError("Demand uplift features require live_promo_window_days or promo_days.")
    if (promo_window_days < 0.0).any():
        raise ValueError("Demand uplift features require non-negative promo window days.")
    return promo_window_days


def _resolve_baseline_expected_units(
    frame: pd.DataFrame,
    *,
    baseline_daily_units: pd.Series,
    promo_window_days: pd.Series,
) -> pd.Series:
    computed_baseline_expected_units = (baseline_daily_units * promo_window_days).clip(lower=0.0)
    if "baseline_expected_units" not in frame.columns:
        return computed_baseline_expected_units
    baseline_expected_units = ensure_numeric_series(frame, "baseline_expected_units", default=float("nan"))
    contradiction_mask = (
        baseline_expected_units.notna()
        & computed_baseline_expected_units.notna()
        & (baseline_expected_units - computed_baseline_expected_units).abs().gt(_BASELINE_CONSISTENCY_TOLERANCE_UNITS)
    )
    if bool(contradiction_mask.any()):
        raise ValueError(
            "Demand uplift features found contradictory baseline_expected_units versus baseline_daily_units * promo_window_days."
        )
    return baseline_expected_units.where(baseline_expected_units.notna(), computed_baseline_expected_units)


def _resolve_stock_basis_units(frame: pd.DataFrame) -> pd.Series:
    stock_basis_units = first_non_null_series(
        frame,
        ("stock_basis_units", "total_stock_available", "pl_allocated", "pl_allocation_qty", "store_adjusted_qty"),
    )
    if (stock_basis_units < 0.0).any():
        raise ValueError("Demand uplift features require non-negative stock basis units.")
    return stock_basis_units


def _resolve_days_until_promo_start(frame: pd.DataFrame) -> pd.Series:
    if "days_until_promo_start" in frame.columns:
        days_until_promo_start = ensure_numeric_series(frame, "days_until_promo_start", default=float("nan"))
    else:
        start_dates = pd.to_datetime(frame.get("promotion_start_date_date"), errors="coerce")
        as_of_dates = pd.to_datetime(frame.get("as_of_date"), errors="coerce")
        days_until_promo_start = (start_dates - as_of_dates).dt.days.astype("float64")
    return days_until_promo_start.clip(lower=0.0).fillna(0.0)


def _resolve_actual_units_total(frame: pd.DataFrame) -> pd.Series:
    return _optional_numeric_series(
        frame,
        (
            "actual_units_sold_promo",
            "target_actual_units_sold",
            "actual_units_sold",
        ),
    )


def _resolve_actual_units_first_7_days(frame: pd.DataFrame) -> pd.Series:
    return _optional_numeric_series(
        frame,
        (
            "actual_units_sold_first_7_days",
            "target_actual_units_sold_first_7_days",
        ),
    )


def _optional_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    return candidate_frame.bfill(axis=1).iloc[:, 0]


def _build_uplift_history_summary(
    *,
    candidate_typed: pd.DataFrame,
    history_typed: pd.DataFrame,
) -> list[_UpliftHistorySummary]:
    history = history_typed.copy()
    history = history.assign(
        _end=pd.to_datetime(history.get("promotional_end_date_date"), errors="coerce"),
        _start=pd.to_datetime(history.get("promotion_start_date_date"), errors="coerce"),
        _discount=normalize_discount_decimal(ensure_numeric_series(history, "discount_percent", default=float("nan"))),
    )
    history_baseline_daily_units = first_non_null_series(
        history,
        ("baseline_daily_units", "feature_pre_promo_baseline_daily_units"),
    )
    history_promo_window_days = first_non_null_series(history, ("live_promo_window_days", "promo_days"))
    history_baseline_expected_units = _optional_numeric_series(history, ("baseline_expected_units",)).where(
        lambda series: series.notna(),
        history_baseline_daily_units * history_promo_window_days,
    )
    history_first_7_baseline = (history_baseline_daily_units * history_promo_window_days.clip(upper=_FIRST_7_DAY_WINDOW_DAYS)).clip(lower=0.0)
    history_actual_units = _resolve_actual_units_total(history)
    history_actual_first_7_units = _resolve_actual_units_first_7_days(history)
    history["_uplift_units"] = (history_actual_units - history_baseline_expected_units).clip(lower=0.0)
    history["_uplift_first7_units"] = (history_actual_first_7_units - history_first_7_baseline).clip(lower=0.0)

    grouped_history: dict[tuple[object, object], pd.DataFrame] = {}
    if {"store_number_key", "sku_number_key"}.issubset(history.columns):
        for key, group in history.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False):
            grouped_history[tuple(key)] = group.loc[group["_end"].notna()].sort_values("_end", kind="mergesort")

    candidate_start_dates = pd.to_datetime(candidate_typed.get("promotion_start_date_date"), errors="coerce")
    candidate_store_keys = candidate_typed.get("store_number_key")
    candidate_sku_keys = candidate_typed.get("sku_number_key")
    candidate_discount = normalize_discount_decimal(ensure_numeric_series(candidate_typed, "discount_percent", default=float("nan")))

    summaries: list[_UpliftHistorySummary] = []
    for row_index in range(len(candidate_typed.index)):
        candidate_start = candidate_start_dates.iloc[row_index]
        prior_rows = grouped_history.get(
            (candidate_store_keys.iloc[row_index], candidate_sku_keys.iloc[row_index]),
            pd.DataFrame(),
        )
        if prior_rows.empty or pd.isna(candidate_start):
            summaries.append(
                _UpliftHistorySummary(0.0, 0.0, 0.0, 0.0, float("nan"), 0.0, float("nan"))
            )
            continue
        prior_rows = prior_rows.loc[prior_rows["_end"] < candidate_start].copy()
        if prior_rows.empty:
            summaries.append(
                _UpliftHistorySummary(0.0, 0.0, 0.0, 0.0, float("nan"), 0.0, float("nan"))
            )
            continue
        candidate_discount_value = candidate_discount.iloc[row_index]
        same_discount_mask = (prior_rows["_discount"] - candidate_discount_value).abs().le(0.005)
        same_or_better_mask = prior_rows["_discount"].ge(candidate_discount_value - 0.005)
        comparable_rows = prior_rows.loc[same_or_better_mask].copy()
        same_discount_rows = prior_rows.loc[same_discount_mask].copy()
        if comparable_rows.empty:
            comparable_rows = same_discount_rows
        uplift_units = pd.to_numeric(comparable_rows.get("_uplift_units"), errors="coerce").dropna()
        uplift_first7_units = pd.to_numeric(comparable_rows.get("_uplift_first7_units"), errors="coerce").dropna()
        summaries.append(
            _UpliftHistorySummary(
                same_discount_event_count=float(len(same_discount_rows.index)),
                same_or_better_discount_event_count=float(len(comparable_rows.index)),
                uplift_history_event_count=float(len(uplift_units.index)),
                uplift_mean_units=float(uplift_units.mean()) if not uplift_units.empty else 0.0,
                uplift_std_units=float(uplift_units.std(ddof=0)) if len(uplift_units.index) > 1 else float("nan"),
                uplift_first7_mean_units=float(uplift_first7_units.mean()) if not uplift_first7_units.empty else 0.0,
                uplift_first7_std_units=float(uplift_first7_units.std(ddof=0)) if len(uplift_first7_units.index) > 1 else float("nan"),
            )
        )
    return summaries


def _build_uplift_confidence_score(
    *,
    event_count: pd.Series,
    same_discount_event_count: pd.Series,
    same_or_better_discount_event_count: pd.Series,
    uplift_instability_score: pd.Series,
    history_confidence: pd.Series,
    probability_confidence: pd.Series,
) -> pd.Series:
    event_strength = (same_or_better_discount_event_count / 5.0).clip(lower=0.0, upper=1.0)
    same_discount_strength = (same_discount_event_count / 3.0).clip(lower=0.0, upper=1.0)
    stability_strength = (1.0 / (1.0 + uplift_instability_score.fillna(5.0))).clip(lower=0.0, upper=1.0)
    confidence = rowwise_nanmean(
        [event_strength, same_discount_strength, stability_strength, history_confidence, probability_confidence]
    ).fillna(0.0)
    return confidence.where(event_count.gt(0.0), 0.0).clip(lower=0.0, upper=1.0)


def _classify_uplift_evidence(
    *,
    uplift_confidence_score: pd.Series,
    uplift_history_event_count: pd.Series,
    uplift_instability_score: pd.Series,
) -> pd.Series:
    evidence_class = pd.Series(0.0, index=uplift_confidence_score.index, dtype="float64")
    evidence_class = evidence_class.where(
        ~(uplift_history_event_count >= 1.0),
        1.0,
    )
    evidence_class = evidence_class.where(
        ~((uplift_history_event_count >= 2.0) & uplift_confidence_score.ge(0.35)),
        2.0,
    )
    evidence_class = evidence_class.where(
        ~((uplift_history_event_count >= 4.0) & uplift_confidence_score.ge(0.6) & uplift_instability_score.fillna(5.0).le(0.75)),
        3.0,
    )
    return evidence_class


def _probability_supported_total_units(
    *,
    probability_expected_units: pd.Series,
    baseline_expected_units: pd.Series,
) -> pd.Series:
    return (probability_expected_units - baseline_expected_units).clip(lower=0.0)


def _probability_total_upper_units(
    *,
    probability_expected_units: pd.Series,
    probability_tail_risk: pd.Series,
    probability_confidence: pd.Series,
) -> pd.Series:
    return probability_expected_units * (
        1.0 + probability_tail_risk.fillna(0.0) + ((1.0 - probability_confidence.fillna(0.0)) * _LOW_CONFIDENCE_SLACK)
    )


def _scale_total_to_window(
    *,
    total_units: pd.Series,
    promo_window_days: pd.Series,
    target_window_days: pd.Series,
) -> pd.Series:
    return total_units * safe_ratio(target_window_days, promo_window_days.where(promo_window_days > 0.0, np.nan)).fillna(0.0)


def _build_uplift_basket_support_score(frame: pd.DataFrame) -> pd.Series:
    return rowwise_nanmean(
        [
            ensure_numeric_series(frame, "feature_basket_attach_rate", default=float("nan")).clip(lower=0.0, upper=1.0),
            ensure_numeric_series(frame, "feature_sku_basket_dependency_score", default=float("nan")).clip(lower=0.0, upper=1.0),
            ensure_numeric_series(frame, "feature_probability_companion_dependency_score", default=float("nan")).clip(lower=0.0, upper=1.0),
        ]
    ).clip(lower=0.0, upper=1.0)


def rowwise_nanmean(series_list: list[pd.Series]) -> pd.Series:
    numeric_frames = [pd.to_numeric(series, errors="coerce") for series in series_list]
    combined = pd.concat(numeric_frames, axis=1)
    return combined.mean(axis=1, skipna=True).astype("float64")