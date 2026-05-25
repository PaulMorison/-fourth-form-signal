from __future__ import annotations

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.probability.ft_probability_shared_helpers import (
    negative_binomial_tail_probability,
    negative_binomial_zero_sale_probability,
    numeric_series,
    rowwise_nanmean,
)


PROBABILITY_NEGATIVE_BINOMIAL_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_probability_negative_binomial_expected_units",
    "feature_probability_negative_binomial_zero_sale_probability",
    "feature_probability_negative_binomial_tail_probability",
    "feature_probability_negative_binomial_dispersion_score",
    "feature_probability_negative_binomial_overallocation_risk_score",
)

_MIN_REQUIRED_EVENTS = 3.0
_MIN_OVERDISPERSION_RATIO = 1.15


def build_probability_negative_binomial_features(
    probability_input_frame: pd.DataFrame,
) -> pd.DataFrame:
    same_or_better_event_count = numeric_series(
        probability_input_frame,
        "probability_same_or_better_event_count",
    ).fillna(0.0)
    same_or_better_mean_units = numeric_series(
        probability_input_frame,
        "probability_same_or_better_units_mean",
    )
    same_or_better_variance = numeric_series(
        probability_input_frame,
        "probability_same_or_better_units_variance",
    )
    order_threshold_units = numeric_series(
        probability_input_frame,
        "probability_order_threshold_units",
    )

    raw_dispersion = (
        same_or_better_mean_units.pow(2)
        / (same_or_better_variance - same_or_better_mean_units)
    )
    supported_flag = (
        (same_or_better_event_count >= _MIN_REQUIRED_EVENTS)
        & same_or_better_mean_units.notna()
        & same_or_better_variance.notna()
        & (same_or_better_mean_units > 0.0)
        & (same_or_better_variance > same_or_better_mean_units * _MIN_OVERDISPERSION_RATIO)
        & raw_dispersion.notna()
        & np.isfinite(raw_dispersion)
        & (raw_dispersion > 0.0)
    )
    expected_units = same_or_better_mean_units.where(supported_flag)
    supported_dispersion = raw_dispersion.where(supported_flag).clip(upper=1_000_000.0)
    overdispersion_gap = (
        same_or_better_variance.div(same_or_better_mean_units.where(same_or_better_mean_units > 0.0, np.nan))
        - 1.0
    ).clip(lower=0.0)
    dispersion_score = (overdispersion_gap / (1.0 + overdispersion_gap)).where(supported_flag)

    zero_sale_probability = pd.Series(
        [
            negative_binomial_zero_sale_probability(mean_units, dispersion)
            for mean_units, dispersion in zip(expected_units, supported_dispersion)
        ],
        index=probability_input_frame.index,
        dtype="float64",
    )
    tail_probability = pd.Series(
        [
            negative_binomial_tail_probability(mean_units, dispersion, threshold_units)
            for mean_units, dispersion, threshold_units in zip(
                expected_units,
                supported_dispersion,
                order_threshold_units,
            )
        ],
        index=probability_input_frame.index,
        dtype="float64",
    )
    overallocation_risk_score = rowwise_nanmean(
        [
            zero_sale_probability,
            1.0 - tail_probability,
            dispersion_score,
        ],
        lower=0.0,
        upper=1.0,
    ).where(supported_flag)

    return pd.DataFrame(
        {
            "feature_probability_negative_binomial_expected_units": expected_units,
            "feature_probability_negative_binomial_zero_sale_probability": zero_sale_probability,
            "feature_probability_negative_binomial_tail_probability": tail_probability,
            "feature_probability_negative_binomial_dispersion_score": dispersion_score,
            "feature_probability_negative_binomial_overallocation_risk_score": overallocation_risk_score,
        },
        index=probability_input_frame.index,
    )