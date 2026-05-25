from __future__ import annotations

"""Backward-looking demand-curve shape features for promotions.

Business meaning:
- separates SKUs with improving or accelerating pre-promo demand from SKUs
    with flattening, noisy, or deteriorating demand
- keeps all percentage-like ratios in decimal form

Leakage guard:
- uses only pre-promotion demand aggregates already known before the promotion
  decision date
- does not read realised promo sales, stockouts, post-promo outcomes, or future
  rows

Output columns are declared in GROWTH_CURVE_SHAPE_FEATURE_COLUMNS.
"""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


GROWTH_CURVE_SHAPE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_growth_curve_recent_slope_units_per_day",
    "feature_growth_curve_long_slope_units_per_day",
    "feature_growth_curve_second_derivative_proxy",
    "feature_growth_curve_acceleration_score",
    "feature_growth_curve_deceleration_score",
    "feature_growth_curve_convexity_score",
    "feature_growth_curve_recent_to_long_slope_ratio",
    "feature_growth_curve_flattening_score",
    "feature_growth_curve_decay_persistence_score",
    "feature_growth_curve_monotonic_improvement_flag",
    "feature_growth_curve_monotonic_decline_flag",
    "feature_growth_curve_noise_penalty_score",
    "feature_growth_curve_confidence_score",
    "feature_growth_curve_late_window_momentum_vs_baseline",
)

FEATURE_COLUMNS: tuple[str, ...] = GROWTH_CURVE_SHAPE_FEATURE_COLUMNS

REQUIRED_COLUMNS: tuple[str, ...] = (
    "pre_56d_units",
    "pre_28d_units",
    "pre_7d_units",
    "pre_56d_days_with_sales",
    "pre_28d_days_with_sales",
    "pre_7d_days_with_sales",
    "pre_56d_std_daily_units",
    "baseline_daily_units",
)

_EPSILON = 1.0e-9


def apply_ft_growth_curve_shape(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append demand growth/decay shape features from pre-decision windows."""

    del reference_frame
    _validate_required_columns(frame)

    working = frame.copy()
    pre_56d_units = ensure_numeric_series(working, "pre_56d_units").clip(lower=0.0)
    pre_28d_units = ensure_numeric_series(working, "pre_28d_units").clip(lower=0.0)
    pre_7d_units = ensure_numeric_series(working, "pre_7d_units").clip(lower=0.0)
    baseline_daily_units = ensure_numeric_series(working, "baseline_daily_units").clip(lower=0.0)
    baseline_anchor = baseline_daily_units.where(baseline_daily_units > 0.0, pre_56d_units / 56.0)
    baseline_anchor = baseline_anchor.where(baseline_anchor > 0.0, 1.0)

    early_window_daily_units = (pre_56d_units - pre_28d_units).clip(lower=0.0) / 28.0
    middle_window_daily_units = (pre_28d_units - pre_7d_units).clip(lower=0.0) / 21.0
    late_window_daily_units = pre_7d_units / 7.0

    early_to_middle_slope = middle_window_daily_units - early_window_daily_units
    middle_to_late_slope = late_window_daily_units - middle_window_daily_units
    long_slope = late_window_daily_units - early_window_daily_units
    second_derivative = middle_to_late_slope - early_to_middle_slope
    normalized_second_derivative = safe_ratio(second_derivative, baseline_anchor)
    acceleration_score = normalized_second_derivative.clip(lower=0.0, upper=1.0)
    deceleration_score = (-normalized_second_derivative).clip(lower=0.0, upper=1.0)
    convexity_score = safe_ratio(
        (middle_to_late_slope - early_to_middle_slope).clip(lower=0.0),
        baseline_anchor,
    ).clip(lower=0.0, upper=1.0)
    recent_to_long_slope_ratio = safe_ratio(
        middle_to_late_slope,
        long_slope.abs().where(long_slope.abs() > _EPSILON),
    ).clip(lower=-5.0, upper=5.0)

    positive_growth_path = late_window_daily_units.gt(early_window_daily_units)
    flattening_score = (
        positive_growth_path.astype(float)
        * deceleration_score
        * safe_ratio(late_window_daily_units, baseline_anchor).clip(lower=0.0, upper=1.0)
    ).clip(lower=0.0, upper=1.0)
    decay_persistence_score = (
        early_to_middle_slope.lt(0.0).astype(float) * 0.5
        + middle_to_late_slope.lt(0.0).astype(float) * 0.5
    ) * safe_ratio((early_window_daily_units - late_window_daily_units).clip(lower=0.0), baseline_anchor).clip(lower=0.0, upper=1.0)

    monotonic_improvement_flag = (
        (early_window_daily_units <= middle_window_daily_units)
        & (middle_window_daily_units <= late_window_daily_units)
        & late_window_daily_units.gt(early_window_daily_units)
    ).astype(float)
    monotonic_decline_flag = (
        (early_window_daily_units >= middle_window_daily_units)
        & (middle_window_daily_units >= late_window_daily_units)
        & early_window_daily_units.gt(late_window_daily_units)
    ).astype(float)

    pre_56d_days_with_sales = ensure_numeric_series(working, "pre_56d_days_with_sales").clip(lower=0.0, upper=56.0)
    pre_28d_days_with_sales = ensure_numeric_series(working, "pre_28d_days_with_sales").clip(lower=0.0, upper=28.0)
    pre_7d_days_with_sales = ensure_numeric_series(working, "pre_7d_days_with_sales").clip(lower=0.0, upper=7.0)
    support_ratio = pd.concat(
        [pre_56d_days_with_sales / 56.0, pre_28d_days_with_sales / 28.0, pre_7d_days_with_sales / 7.0],
        axis=1,
    ).mean(axis=1).clip(lower=0.0, upper=1.0)
    volatility_cv = safe_ratio(
        ensure_numeric_series(working, "pre_56d_std_daily_units").clip(lower=0.0),
        baseline_anchor,
    )
    choppiness = safe_ratio((middle_to_late_slope - early_to_middle_slope).abs(), baseline_anchor).clip(lower=0.0, upper=1.0)
    noise_penalty = (0.65 * (volatility_cv / 2.0).clip(lower=0.0, upper=1.0) + 0.35 * choppiness).clip(lower=0.0, upper=1.0)
    confidence_score = (support_ratio * (1.0 - noise_penalty)).clip(lower=0.0, upper=1.0)
    late_window_momentum = safe_ratio(late_window_daily_units - baseline_anchor, baseline_anchor).clip(lower=-1.0, upper=5.0)

    derived_columns = pd.DataFrame(
        {
            "feature_growth_curve_recent_slope_units_per_day": middle_to_late_slope,
            "feature_growth_curve_long_slope_units_per_day": long_slope,
            "feature_growth_curve_second_derivative_proxy": second_derivative,
            "feature_growth_curve_acceleration_score": acceleration_score,
            "feature_growth_curve_deceleration_score": deceleration_score,
            "feature_growth_curve_convexity_score": convexity_score,
            "feature_growth_curve_recent_to_long_slope_ratio": recent_to_long_slope_ratio,
            "feature_growth_curve_flattening_score": flattening_score,
            "feature_growth_curve_decay_persistence_score": decay_persistence_score,
            "feature_growth_curve_monotonic_improvement_flag": monotonic_improvement_flag,
            "feature_growth_curve_monotonic_decline_flag": monotonic_decline_flag,
            "feature_growth_curve_noise_penalty_score": noise_penalty,
            "feature_growth_curve_confidence_score": confidence_score,
            "feature_growth_curve_late_window_momentum_vs_baseline": late_window_momentum,
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _validate_required_columns(frame: pd.DataFrame) -> None:
    missing_columns = [column_name for column_name in REQUIRED_COLUMNS if column_name not in frame.columns]
    if missing_columns:
        raise ValueError(
            "ft_growth_curve_shape missing required columns: "
            + ", ".join(missing_columns)
        )