from __future__ import annotations

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.probability.ft_probability_shared_helpers import (
    numeric_series,
    poisson_probability_one_or_more_sale,
    poisson_probability_tail_probability,
    poisson_probability_zero_sale,
    rowwise_nanmean,
)


PROBABILITY_POISSON_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_probability_poisson_expected_units",
    "feature_probability_poisson_zero_sale_probability",
    "feature_probability_poisson_one_or_more_sale_probability",
    "feature_probability_poisson_tail_probability",
    "feature_probability_poisson_overallocation_risk_score",
)

_MIN_REQUIRED_EVENTS = 2.0
_LOW_VOLUME_EXPECTED_UNITS_CEILING = 8.0
_STABLE_VARIANCE_RATIO = 1.35


def build_probability_poisson_features(probability_input_frame: pd.DataFrame) -> pd.DataFrame:
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

    stable_low_volume_flag = (
        (same_or_better_event_count >= _MIN_REQUIRED_EVENTS)
        & same_or_better_mean_units.notna()
        & (same_or_better_mean_units >= 0.0)
        & (same_or_better_mean_units <= _LOW_VOLUME_EXPECTED_UNITS_CEILING)
        & (
            same_or_better_variance.isna()
            | (
                same_or_better_variance
                <= same_or_better_mean_units.clip(lower=1e-6) * _STABLE_VARIANCE_RATIO
            )
        )
    )
    expected_units = same_or_better_mean_units.where(stable_low_volume_flag)

    zero_sale_probability = pd.Series(
        [poisson_probability_zero_sale(value) for value in expected_units],
        index=probability_input_frame.index,
        dtype="float64",
    )
    one_or_more_sale_probability = pd.Series(
        [poisson_probability_one_or_more_sale(value) for value in expected_units],
        index=probability_input_frame.index,
        dtype="float64",
    )
    tail_probability = pd.Series(
        [
            poisson_probability_tail_probability(expected_value, threshold_value)
            for expected_value, threshold_value in zip(expected_units, order_threshold_units)
        ],
        index=probability_input_frame.index,
        dtype="float64",
    )
    overallocation_risk_score = rowwise_nanmean(
        [
            zero_sale_probability,
            1.0 - tail_probability,
        ],
        lower=0.0,
        upper=1.0,
    ).where(stable_low_volume_flag)

    return pd.DataFrame(
        {
            "feature_probability_poisson_expected_units": expected_units,
            "feature_probability_poisson_zero_sale_probability": zero_sale_probability,
            "feature_probability_poisson_one_or_more_sale_probability": one_or_more_sale_probability,
            "feature_probability_poisson_tail_probability": tail_probability,
            "feature_probability_poisson_overallocation_risk_score": overallocation_risk_score,
        },
        index=probability_input_frame.index,
    )