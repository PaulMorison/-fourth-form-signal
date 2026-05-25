from __future__ import annotations

"""Baseline-versus-uplift demand decomposition features."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series, first_non_null_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


UPLIFT_DECOMPOSITION_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_expected_baseline_units_promo_window",
    "feature_expected_baseline_units_first_7_days",
    "feature_expected_incremental_uplift_units_same_discount",
    "feature_expected_incremental_uplift_units_first_7_days",
    "feature_expected_total_units_from_baseline_plus_uplift",
    "feature_expected_total_units_first_7_days",
    "feature_uplift_share_of_total_expected_units",
    "feature_uplift_support_event_count",
    "feature_uplift_confidence_score",
    "feature_uplift_instability_score",
    "feature_uplift_vs_base_ratio",
    "feature_uplift_demand_support_flag",
)


def apply_ft_uplift_decomposition(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append governed baseline-plus-uplift demand decomposition features."""

    del reference_frame
    working = frame.copy()
    promo_window_days = first_non_null_series(working, ("live_promo_window_days", "promo_days"), positive_only=True)
    promo_window_days = promo_window_days.where(promo_window_days > 0.0, 0.0)
    first_7_window_days = promo_window_days.clip(lower=0.0, upper=7.0)
    baseline_daily_units = first_non_null_series(
        working,
        ("feature_non_promo_30d_avg_daily_units", "feature_non_promo_56d_avg_daily_units", "feature_non_promo_84d_avg_daily_units", "feature_pre_promo_baseline_daily_units", "baseline_daily_units"),
        positive_only=True,
    )
    baseline_expected_promo_window = (baseline_daily_units * promo_window_days).clip(lower=0.0)
    baseline_expected_first_7_days = (baseline_daily_units * first_7_window_days).clip(lower=0.0)

    support_event_count = ensure_numeric_series(working, "feature_same_discount_prior_event_count")
    uplift_ratio_avg = ensure_numeric_series(working, "feature_same_discount_prior_uplift_ratio_avg", default=float("nan"))
    uplift_ratio_median = ensure_numeric_series(working, "feature_same_discount_prior_uplift_ratio_median", default=float("nan"))
    uplift_ratio_std = ensure_numeric_series(working, "feature_same_discount_prior_uplift_ratio_std", default=float("nan"))
    discount_history_available_flag = ensure_numeric_series(
        working,
        "feature_same_discount_history_available_flag",
        default=0.0,
    ).clip(lower=0.0, upper=1.0)
    elasticity_estimate = ensure_numeric_series(working, "feature_discount_elasticity_estimate", default=float("nan"))
    elasticity_abs = ensure_numeric_series(working, "feature_discount_elasticity_abs", default=float("nan"))
    elasticity_confidence = ensure_numeric_series(
        working,
        "feature_discount_elasticity_confidence_score",
        default=0.0,
    ).clip(lower=0.0, upper=1.0)
    elasticity_direction_flag = ensure_numeric_series(
        working,
        "feature_discount_response_direction_consistent_flag",
        default=0.0,
    ).clip(lower=0.0, upper=1.0)
    probability_confidence = ensure_numeric_series(
        working,
        "feature_probability_demand_confidence_score",
        default=float("nan"),
    ).clip(lower=0.0, upper=1.0)

    same_discount_supported_ratio = uplift_ratio_median.where(
        support_event_count >= 2.0,
        uplift_ratio_avg,
    )
    same_discount_supported_ratio = same_discount_supported_ratio.clip(lower=0.0)
    elasticity_supported_ratio = elasticity_abs.where(
        elasticity_confidence >= 0.35,
        np.nan,
    )
    elasticity_supported_ratio = elasticity_supported_ratio.where(
        elasticity_direction_flag.eq(1.0),
        0.0,
    )
    restrained_uplift_ratio = same_discount_supported_ratio.where(
        elasticity_supported_ratio.isna(),
        np.minimum(same_discount_supported_ratio, elasticity_supported_ratio),
    )
    uplift_instability_score = safe_ratio(
        uplift_ratio_std,
        same_discount_supported_ratio.where(same_discount_supported_ratio > 0.0, np.nan),
    )
    uplift_confidence_score = _rowwise_nanmean(
        [
            (support_event_count / 4.0).clip(lower=0.0, upper=1.0),
            discount_history_available_flag,
            (1.0 / (1.0 + uplift_instability_score.fillna(5.0))).clip(lower=0.0, upper=1.0),
            elasticity_confidence,
            probability_confidence,
        ]
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    uplift_demand_support_flag = (
        discount_history_available_flag.eq(1.0)
        & support_event_count.ge(1.0)
        & uplift_confidence_score.ge(0.35)
        & restrained_uplift_ratio.fillna(0.0).gt(0.0)
    ).astype(float)
    expected_incremental_uplift_units = (
        baseline_expected_promo_window * restrained_uplift_ratio.fillna(0.0)
    ).where(uplift_demand_support_flag.eq(1.0), 0.0)
    expected_incremental_uplift_units_first_7_days = expected_incremental_uplift_units * safe_ratio(
        first_7_window_days,
        promo_window_days.where(promo_window_days > 0.0, np.nan),
    ).fillna(0.0)
    expected_total_units = (baseline_expected_promo_window + expected_incremental_uplift_units).clip(lower=0.0)
    expected_total_units_first_7_days = (baseline_expected_first_7_days + expected_incremental_uplift_units_first_7_days).clip(lower=0.0)

    derived_columns = pd.DataFrame(
        {
            "feature_expected_baseline_units_promo_window": baseline_expected_promo_window,
            "feature_expected_baseline_units_first_7_days": baseline_expected_first_7_days,
            "feature_expected_incremental_uplift_units_same_discount": expected_incremental_uplift_units,
            "feature_expected_incremental_uplift_units_first_7_days": expected_incremental_uplift_units_first_7_days,
            "feature_expected_total_units_from_baseline_plus_uplift": expected_total_units,
            "feature_expected_total_units_first_7_days": expected_total_units_first_7_days,
            "feature_uplift_share_of_total_expected_units": safe_ratio(
                expected_incremental_uplift_units,
                expected_total_units.where(expected_total_units > 0.0, np.nan),
            ).clip(lower=0.0, upper=1.0),
            "feature_uplift_support_event_count": support_event_count,
            "feature_uplift_confidence_score": uplift_confidence_score,
            "feature_uplift_instability_score": uplift_instability_score,
            "feature_uplift_vs_base_ratio": safe_ratio(
                expected_incremental_uplift_units,
                baseline_expected_promo_window.where(baseline_expected_promo_window > 0.0, np.nan),
            ).clip(lower=0.0),
            "feature_uplift_demand_support_flag": uplift_demand_support_flag,
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _rowwise_nanmean(series_list: list[pd.Series]) -> pd.Series:
    combined = pd.concat([pd.to_numeric(series, errors="coerce") for series in series_list], axis=1)
    return combined.mean(axis=1, skipna=True).astype("float64")