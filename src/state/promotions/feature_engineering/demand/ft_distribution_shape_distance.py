from __future__ import annotations

"""Review-only distribution-shape distance diagnostics for promotions."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


DISTRIBUTION_SHAPE_DISTANCE_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_wasserstein_recent_vs_baseline_distance",
    "feature_distribution_shape_shift_score",
    "feature_distribution_tail_pressure_score",
    "feature_distribution_sparse_support_distance",
    "feature_distribution_shape_review_only_flag",
)

DISTRIBUTION_SHAPE_DISTANCE_FEATURE_COLUMNS: tuple[str, ...] = (
    *DISTRIBUTION_SHAPE_DISTANCE_REVIEW_ONLY_FEATURE_COLUMNS,
)


def apply_ft_distribution_shape_distance(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append review-only robust distribution-distance diagnostics.

    Purpose:
        Approximate Wasserstein-style distance between recent and baseline
        prior-window demand distributions using only pre-promo aggregate shape.

    Inputs:
        frame: candidate rows with prior demand means, standard deviations, and
            selling-day density fields.
        reference_frame: accepted for registry compatibility and unused.

    Outputs:
        A copy of ``frame`` with distribution-shape diagnostics appended.

    Failure behavior:
        Missing shape evidence becomes a high sparse-support distance; no
        missing value is interpreted as publishable demand.
    """

    del reference_frame
    working = frame.copy()
    long_mean = _first_optional_numeric_series(
        working,
        ("pre_56d_avg_daily_units", "feature_pre_promo_baseline_daily_units", "baseline_daily_units", "avg_daily_units"),
    ).clip(lower=0.0)
    recent_mean = _first_optional_numeric_series(
        working,
        ("pre_7d_avg_daily_units", "pre_28d_avg_daily_units"),
    ).clip(lower=0.0)
    long_std = _optional_numeric_series(working, "pre_56d_std_daily_units").clip(lower=0.0)
    recent_std = _optional_numeric_series(working, "pre_28d_std_daily_units").clip(lower=0.0)
    days_with_sales = _first_optional_numeric_series(
        working,
        ("pre_56d_days_with_sales", "feature_days_with_sales_56d"),
    ).clip(lower=0.0, upper=56.0)
    long_mean_filled = long_mean.fillna(0.0)
    recent_mean_filled = recent_mean.fillna(long_mean_filled)
    long_std_filled = long_std.fillna(0.0)
    recent_std_filled = recent_std.fillna(long_std_filled)
    density = days_with_sales.fillna(0.0).divide(56.0).clip(0.0, 1.0)

    wasserstein_distance = (
        (recent_mean_filled - long_mean_filled).abs()
        + (recent_std_filled - long_std_filled).abs()
    ).clip(lower=0.0)
    shift_score = safe_ratio(wasserstein_distance, long_mean_filled.add(long_std_filled).add(1.0)).clip(0.0, 1.0)
    tail_pressure_score = safe_ratio(
        (recent_mean_filled + recent_std_filled) - (long_mean_filled + long_std_filled),
        long_mean_filled.add(long_std_filled).add(1.0),
    ).clip(lower=0.0, upper=1.0)
    sparse_support_distance = (1.0 - density).clip(0.0, 1.0)
    derived = pd.DataFrame(
        {
            "feature_wasserstein_recent_vs_baseline_distance": wasserstein_distance,
            "feature_distribution_shape_shift_score": shift_score,
            "feature_distribution_tail_pressure_score": tail_pressure_score,
            "feature_distribution_sparse_support_distance": sparse_support_distance,
            "feature_distribution_shape_review_only_flag": pd.Series(1.0, index=working.index),
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