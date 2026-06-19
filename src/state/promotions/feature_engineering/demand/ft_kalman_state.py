from __future__ import annotations

"""Review-only Kalman-style demand state diagnostics for promotions."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


KALMAN_STATE_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_kalman_demand_state_level",
    "feature_kalman_demand_state_trend",
    "feature_kalman_demand_state_uncertainty",
    "feature_kalman_demand_state_shift_score",
    "feature_kalman_demand_state_review_only_flag",
)

KALMAN_STATE_FEATURE_COLUMNS: tuple[str, ...] = (
    *KALMAN_STATE_REVIEW_ONLY_FEATURE_COLUMNS,
)


def apply_ft_kalman_state(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append review-only Kalman-style demand state features.

    Purpose:
        Filter prior pre-promo demand windows into a stable state, trend, and
        uncertainty diagnostic without using realised promotion outcomes.

    Inputs:
        frame: candidate rows carrying prior-window average demand columns.
        reference_frame: accepted for registry compatibility and unused.

    Outputs:
        A copy of ``frame`` with ``KALMAN_STATE_FEATURE_COLUMNS`` appended.

    Failure behavior:
        Missing observations produce high uncertainty rather than a safe state.
    """

    del reference_frame
    working = frame.copy()
    prior_daily = _optional_numeric_series(working, "pre_prior_21d_avg_daily_units").clip(lower=0.0)
    mid_daily = _optional_numeric_series(working, "pre_28d_avg_daily_units").clip(lower=0.0)
    recent_daily = _optional_numeric_series(working, "pre_7d_avg_daily_units").clip(lower=0.0)
    long_std = _optional_numeric_series(working, "pre_56d_std_daily_units").clip(lower=0.0)
    fallback_daily = _first_optional_numeric_series(
        working,
        ("feature_pre_promo_baseline_daily_units", "baseline_daily_units", "avg_daily_units"),
    ).clip(lower=0.0)

    observations = pd.concat([prior_daily, mid_daily, recent_daily], axis=1)
    fallback_observations = observations.T.fillna(fallback_daily).T.fillna(0.0)
    measurement_noise = safe_ratio(long_std.fillna(0.0), fallback_daily.fillna(0.0).add(1.0)).clip(0.05, 2.0)
    state = fallback_observations.iloc[:, 0]
    variance = pd.Series(1.0, index=working.index, dtype="float64")
    for column_index in range(1, fallback_observations.shape[1]):
        variance = variance + 0.05
        kalman_gain = safe_ratio(variance, variance + measurement_noise)
        innovation = fallback_observations.iloc[:, column_index] - state
        state = state + kalman_gain * innovation
        variance = (1.0 - kalman_gain).clip(0.0, 1.0) * variance

    trend = recent_daily.fillna(state) - prior_daily.fillna(state)
    shift_score = safe_ratio(trend.abs(), state.abs().add(1.0)).clip(0.0, 1.0)
    missing_observation_share = observations.isna().sum(axis=1).astype(float) / float(observations.shape[1])
    uncertainty = (variance.clip(0.0, 1.0) + missing_observation_share).clip(0.0, 1.0)
    derived = pd.DataFrame(
        {
            "feature_kalman_demand_state_level": state.clip(lower=0.0),
            "feature_kalman_demand_state_trend": trend,
            "feature_kalman_demand_state_uncertainty": uncertainty,
            "feature_kalman_demand_state_shift_score": shift_score,
            "feature_kalman_demand_state_review_only_flag": pd.Series(1.0, index=working.index),
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived.columns), errors="ignore")
    return pd.concat([base_columns, derived], axis=1)


def _optional_numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    """Return a numeric series preserving missing evidence as NaN."""

    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def _first_optional_numeric_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
) -> pd.Series:
    """Return the first non-null numeric evidence from candidate columns."""

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return frame[present_columns].apply(pd.to_numeric, errors="coerce").bfill(axis=1).iloc[:, 0]