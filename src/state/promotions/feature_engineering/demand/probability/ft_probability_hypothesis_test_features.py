from __future__ import annotations

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.probability.ft_probability_shared_helpers import (
    bounded_sample_strength,
    clip_zero_one,
    confidence_interval_width,
    normal_two_sided_p_value,
    numeric_series,
    standard_error_from_variance,
)


PROBABILITY_HYPOTHESIS_TEST_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_units_lift_effect_size",
    "feature_units_lift_p_value",
    "feature_units_lift_sample_size",
    "feature_units_lift_confidence_interval_width",
    "feature_units_lift_stability_score",
    "feature_basket_attach_rate_lift",
    "feature_basket_attach_rate_p_value",
    "feature_same_discount_repeatability_score",
    "feature_same_discount_response_variance",
    "feature_same_discount_response_p_value",
)


def build_probability_hypothesis_test_features(
    probability_input_frame: pd.DataFrame,
) -> pd.DataFrame:
    units_lift_mean = numeric_series(
        probability_input_frame,
        "probability_units_lift_mean",
    )
    units_lift_variance = numeric_series(
        probability_input_frame,
        "probability_units_lift_variance",
    )
    units_lift_sample_size = numeric_series(
        probability_input_frame,
        "probability_units_lift_sample_size",
    ).fillna(0.0)
    basket_attach_rate_lift = numeric_series(
        probability_input_frame,
        "probability_basket_attach_rate_lift_mean",
    )
    basket_attach_rate_lift_variance = numeric_series(
        probability_input_frame,
        "probability_basket_attach_rate_lift_variance",
    )
    basket_attach_rate_lift_sample_size = numeric_series(
        probability_input_frame,
        "probability_basket_attach_rate_lift_sample_size",
    ).fillna(0.0)
    same_discount_response_mean = numeric_series(
        probability_input_frame,
        "probability_same_discount_response_mean",
    )
    same_discount_response_variance = numeric_series(
        probability_input_frame,
        "probability_same_discount_response_variance",
    )
    same_discount_response_sample_size = numeric_series(
        probability_input_frame,
        "probability_same_discount_response_sample_size",
    ).fillna(0.0)

    units_lift_effect_size = units_lift_mean.div(
        np.sqrt(units_lift_variance.where(units_lift_variance > 0.0, np.nan))
    )
    units_lift_ci_width = pd.Series(
        [
            confidence_interval_width(variance_value, sample_size)
            for variance_value, sample_size in zip(
                units_lift_variance,
                units_lift_sample_size,
            )
        ],
        index=probability_input_frame.index,
        dtype="float64",
    )
    units_lift_p_value = pd.Series(
        [
            normal_two_sided_p_value(
                mean_value,
                standard_error_from_variance(variance_value, sample_size),
            )
            for mean_value, variance_value, sample_size in zip(
                units_lift_mean,
                units_lift_variance,
                units_lift_sample_size,
            )
        ],
        index=probability_input_frame.index,
        dtype="float64",
    )
    units_lift_stability_score = clip_zero_one(
        bounded_sample_strength(units_lift_sample_size, reference_count=6.0)
        * (1.0 / (1.0 + units_lift_ci_width.div(units_lift_mean.abs() + 1.0)))
    ).where(units_lift_sample_size > 0.0, 0.0)

    basket_attach_rate_p_value = pd.Series(
        [
            normal_two_sided_p_value(
                mean_value,
                standard_error_from_variance(variance_value, sample_size),
            )
            for mean_value, variance_value, sample_size in zip(
                basket_attach_rate_lift,
                basket_attach_rate_lift_variance,
                basket_attach_rate_lift_sample_size,
            )
        ],
        index=probability_input_frame.index,
        dtype="float64",
    )

    same_discount_repeatability_score = clip_zero_one(
        bounded_sample_strength(same_discount_response_sample_size, reference_count=4.0)
        * (
            1.0
            / (
                1.0
                + np.sqrt(same_discount_response_variance.clip(lower=0.0)).div(
                    same_discount_response_mean.abs() + 1.0
                )
            )
        )
    ).where(same_discount_response_sample_size > 0.0, 0.0)
    same_discount_response_p_value = pd.Series(
        [
            normal_two_sided_p_value(
                mean_value,
                standard_error_from_variance(variance_value, sample_size),
            )
            for mean_value, variance_value, sample_size in zip(
                same_discount_response_mean,
                same_discount_response_variance,
                same_discount_response_sample_size,
            )
        ],
        index=probability_input_frame.index,
        dtype="float64",
    )

    return pd.DataFrame(
        {
            "feature_units_lift_effect_size": units_lift_effect_size,
            "feature_units_lift_p_value": units_lift_p_value,
            "feature_units_lift_sample_size": units_lift_sample_size,
            "feature_units_lift_confidence_interval_width": units_lift_ci_width,
            "feature_units_lift_stability_score": units_lift_stability_score,
            "feature_basket_attach_rate_lift": basket_attach_rate_lift,
            "feature_basket_attach_rate_p_value": basket_attach_rate_p_value,
            "feature_same_discount_repeatability_score": same_discount_repeatability_score,
            "feature_same_discount_response_variance": same_discount_response_variance,
            "feature_same_discount_response_p_value": same_discount_response_p_value,
        },
        index=probability_input_frame.index,
    )