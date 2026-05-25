from __future__ import annotations

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.probability.ft_probability_shared_helpers import (
    numeric_series,
    poisson_probability_zero_sale,
    rowwise_nanmean,
)


PROBABILITY_ZERO_INFLATED_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_probability_zero_inflation_rate",
    "feature_probability_zero_inflated_expected_units",
    "feature_probability_zero_inflated_zero_sale_probability",
    "feature_probability_zero_inflated_nonzero_probability",
    "feature_probability_zero_inflated_overallocation_risk_score",
)

_MIN_REQUIRED_EVENTS = 3.0
_MIN_ZERO_HEAVY_RATE = 0.35
_MIN_EXCESS_ZERO_GAP = 0.10


def build_probability_zero_inflated_features(
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
    same_or_better_zero_rate = numeric_series(
        probability_input_frame,
        "probability_same_or_better_zero_rate",
    )
    order_threshold_units = numeric_series(
        probability_input_frame,
        "probability_order_threshold_units",
    )

    ordinary_poisson_zero_probability = pd.Series(
        [poisson_probability_zero_sale(mean_units) for mean_units in same_or_better_mean_units],
        index=probability_input_frame.index,
        dtype="float64",
    )
    zero_heavy_flag = (
        (same_or_better_event_count >= _MIN_REQUIRED_EVENTS)
        & same_or_better_mean_units.notna()
        & same_or_better_zero_rate.notna()
        & (same_or_better_zero_rate >= _MIN_ZERO_HEAVY_RATE)
        & (same_or_better_zero_rate >= ordinary_poisson_zero_probability + _MIN_EXCESS_ZERO_GAP)
    )
    denominator = (1.0 - ordinary_poisson_zero_probability).replace(0.0, np.nan)
    zero_inflation_rate = (
        (same_or_better_zero_rate - ordinary_poisson_zero_probability) / denominator
    ).clip(lower=0.0, upper=1.0).where(zero_heavy_flag)
    expected_units = same_or_better_mean_units.where(zero_heavy_flag)
    latent_lambda = (
        expected_units / (1.0 - zero_inflation_rate).replace(0.0, np.nan)
    ).where(zero_heavy_flag)
    zero_sale_probability = (
        zero_inflation_rate
        + (1.0 - zero_inflation_rate) * ordinary_poisson_zero_probability.where(latent_lambda.notna(), np.nan)
    ).where(zero_heavy_flag)
    nonzero_probability = (1.0 - zero_sale_probability).where(zero_heavy_flag)
    threshold_shortfall = (
        1.0 - expected_units.div(order_threshold_units.where(order_threshold_units > 0.0, np.nan))
    ).clip(lower=0.0, upper=1.0)
    overallocation_risk_score = rowwise_nanmean(
        [zero_sale_probability, threshold_shortfall],
        lower=0.0,
        upper=1.0,
    ).where(zero_heavy_flag)

    return pd.DataFrame(
        {
            "feature_probability_zero_inflation_rate": zero_inflation_rate,
            "feature_probability_zero_inflated_expected_units": expected_units,
            "feature_probability_zero_inflated_zero_sale_probability": zero_sale_probability,
            "feature_probability_zero_inflated_nonzero_probability": nonzero_probability,
            "feature_probability_zero_inflated_overallocation_risk_score": overallocation_risk_score,
        },
        index=probability_input_frame.index,
    )