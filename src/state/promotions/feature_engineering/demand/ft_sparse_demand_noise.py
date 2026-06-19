from __future__ import annotations

"""Sparse-demand and noise-regime features for promotions.

The module separates stable low demand from random one-off tail behaviour using
pre-promotion cadence, repeat history, and already-governed basket structure.
It never reads realised during-promo outcomes.
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_sparse_demand_low_signal_flag",
    "feature_sparse_demand_stable_low_trust_flag",
    "feature_sparse_demand_random_tail_flag",
    "feature_sparse_demand_repeatability_score",
    "feature_sparse_demand_randomness_score",
    "feature_sparse_demand_one_off_likelihood_score",
    "feature_sparse_demand_daily_stability_score",
    "feature_sparse_demand_outlier_shape_score",
    "feature_sparse_demand_noise_regime_score",
    "feature_sparse_demand_evidence_available_flag",
)

SPARSE_DEMAND_NOISE_FEATURE_COLUMNS: tuple[str, ...] = (
    *SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS,
)


def apply_ft_sparse_demand_noise(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append sparse/noisy demand regime features from prior-safe inputs.

    Purpose:
        Distinguish stable low-demand trust-relevant rows from random one-off
        sparse rows so small-unit opportunity is not erased by average-based
        modelling.

    Inputs:
        frame: candidate rows with pre-promo cadence, history, and optional
            basket-structure features.
        reference_frame: accepted for registry compatibility and unused because
            this module consumes only row-local prior-safe signals.

    Outputs:
        A copy of ``frame`` with ``SPARSE_DEMAND_NOISE_FEATURE_COLUMNS``
        appended.

    Failure behavior:
        Missing cadence evidence is marked through the evidence flag and does
        not create BUY/ORDER action evidence.
    """

    del reference_frame
    working = frame.copy()
    pre_56_units = _optional_numeric_series(working, "pre_56d_units").clip(lower=0.0)
    pre_28_units = _optional_numeric_series(working, "pre_28d_units").clip(lower=0.0)
    pre_7_units = _optional_numeric_series(working, "pre_7d_units").clip(lower=0.0)
    pre_56_days = _optional_numeric_series(working, "pre_56d_days_with_sales").clip(lower=0.0, upper=56.0)
    pre_28_days = _optional_numeric_series(working, "pre_28d_days_with_sales").clip(lower=0.0, upper=28.0)
    pre_56_std = _optional_numeric_series(working, "pre_56d_std_daily_units").clip(lower=0.0)
    baseline_daily = _first_optional_numeric_series(
        working,
        (
            "feature_pre_promo_baseline_daily_units",
            "baseline_daily_units",
            "avg_daily_units",
        ),
    ).clip(lower=0.0)
    same_discount_events = _first_optional_numeric_series(
        working,
        (
            "feature_historical_promo_events_same_discount",
            "feature_historical_promo_events_same_or_better_discount",
        ),
    ).clip(lower=0.0)
    basket_dependency = _first_optional_numeric_series(
        working,
        (
            "feature_basket_conditional_dependency_score",
            "feature_basket_drag_along_dependency_score",
            "feature_sku_basket_dependency_score",
        ),
    ).clip(0.0, 1.0)
    anchor_score = _optional_numeric_series(working, "feature_basket_anchor_sku_score").clip(0.0, 1.0)

    evidence_available = pre_56_units.notna() | pre_56_days.notna() | baseline_daily.notna()
    pre_56_units = pre_56_units.fillna(0.0)
    pre_28_units = pre_28_units.fillna(0.0)
    pre_7_units = pre_7_units.fillna(0.0)
    pre_56_days = pre_56_days.fillna(0.0)
    pre_28_days = pre_28_days.fillna(0.0)
    pre_56_std = pre_56_std.fillna(0.0)
    baseline_daily = baseline_daily.fillna(0.0)
    same_discount_events = same_discount_events.fillna(0.0)
    basket_dependency = basket_dependency.fillna(0.0)
    anchor_score = anchor_score.fillna(0.0)

    density_56 = (pre_56_days / 56.0).clip(0.0, 1.0)
    density_28 = (pre_28_days / 28.0).clip(0.0, 1.0)
    avg_units_per_selling_day = safe_ratio(pre_56_units, pre_56_days.where(pre_56_days > 0.0)).clip(lower=0.0)
    baseline_cv = safe_ratio(pre_56_std, baseline_daily.where(baseline_daily > 0.0)).clip(lower=0.0, upper=3.0) / 3.0
    recent_shift = safe_ratio(
        (pre_7_units / 7.0) - (pre_28_units / 28.0),
        baseline_daily.where(baseline_daily > 0.0),
    ).abs().clip(0.0, 2.0) / 2.0

    repeatability_score = (
        0.35 * density_56
        + 0.25 * density_28
        + 0.20 * same_discount_events.clip(0.0, 3.0).divide(3.0)
        + 0.20 * basket_dependency
    ).clip(0.0, 1.0)
    daily_stability_score = (1.0 - (0.65 * baseline_cv + 0.35 * recent_shift)).clip(0.0, 1.0)
    one_off_likelihood_score = (
        0.45 * (1.0 - density_56)
        + 0.25 * (1.0 - repeatability_score)
        + 0.20 * baseline_cv
        + 0.10 * safe_ratio(
            pd.Series(1.0, index=working.index, dtype="float64"),
            pre_56_units.add(1.0),
        ).clip(0.0, 1.0)
    ).clip(0.0, 1.0)
    outlier_shape_score = (0.60 * baseline_cv + 0.40 * recent_shift).clip(0.0, 1.0)
    randomness_score = (
        0.45 * one_off_likelihood_score
        + 0.35 * outlier_shape_score
        + 0.20 * (1.0 - repeatability_score)
    ).clip(0.0, 1.0)
    low_signal_flag = (
        (pre_56_units.le(2.0) | pre_56_days.le(2.0))
        & same_discount_events.le(0.0)
        & baseline_daily.lt(0.25)
    ).astype(float)
    stable_low_trust_flag = (
        pre_56_units.between(1.0, 14.0, inclusive="both")
        & daily_stability_score.ge(0.55)
        & (repeatability_score.ge(0.35) | baseline_daily.ge(0.25) | anchor_score.ge(0.35))
    ).astype(float)
    random_tail_flag = (
        randomness_score.ge(0.6)
        & stable_low_trust_flag.lt(1.0)
        & low_signal_flag.ge(1.0)
    ).astype(float)
    noise_regime_score = (
        0.50 * randomness_score
        + 0.30 * low_signal_flag
        + 0.20 * (1.0 - daily_stability_score)
    ).clip(0.0, 1.0)

    derived = pd.DataFrame(
        {
            "feature_sparse_demand_low_signal_flag": low_signal_flag,
            "feature_sparse_demand_stable_low_trust_flag": stable_low_trust_flag,
            "feature_sparse_demand_random_tail_flag": random_tail_flag,
            "feature_sparse_demand_repeatability_score": repeatability_score,
            "feature_sparse_demand_randomness_score": randomness_score,
            "feature_sparse_demand_one_off_likelihood_score": one_off_likelihood_score,
            "feature_sparse_demand_daily_stability_score": daily_stability_score,
            "feature_sparse_demand_outlier_shape_score": outlier_shape_score,
            "feature_sparse_demand_noise_regime_score": noise_regime_score,
            "feature_sparse_demand_evidence_available_flag": evidence_available.astype(float),
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