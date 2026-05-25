from __future__ import annotations

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.probability.ft_probability_shared_helpers import (
    bounded_sample_strength,
    negative_binomial_tail_probability,
    numeric_series,
)


PROBABILITY_BAYESIAN_POISSON_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_probability_bayesian_poisson_prior_rate",
    "feature_probability_bayesian_poisson_posterior_rate",
    "feature_probability_bayesian_poisson_expected_units",
    "feature_probability_bayesian_poisson_tail_probability",
    "feature_probability_bayesian_poisson_confidence_score",
)

_MINIMUM_ALPHA = 1e-6


def build_probability_bayesian_poisson_features(
    probability_input_frame: pd.DataFrame,
) -> pd.DataFrame:
    prior_rate = numeric_series(
        probability_input_frame,
        "probability_bayesian_prior_rate",
    )
    prior_event_count = numeric_series(
        probability_input_frame,
        "probability_bayesian_prior_event_count",
    ).fillna(0.0)
    recent_units_sum = numeric_series(
        probability_input_frame,
        "probability_bayesian_recent_units_sum",
    ).fillna(0.0)
    recent_event_count = numeric_series(
        probability_input_frame,
        "probability_bayesian_recent_event_count",
    ).fillna(0.0)
    order_threshold_units = numeric_series(
        probability_input_frame,
        "probability_order_threshold_units",
    )

    supported_prior_rate = prior_rate.where(prior_rate.notna() & (prior_rate >= 0.0))
    prior_weight = prior_event_count.where(prior_event_count > 0.0, np.nan)
    prior_alpha = (supported_prior_rate * prior_weight).where(supported_prior_rate.notna())
    prior_alpha = prior_alpha.mask(prior_alpha.eq(0.0), _MINIMUM_ALPHA)
    posterior_alpha = prior_alpha + recent_units_sum
    posterior_beta = prior_weight + recent_event_count
    posterior_rate = posterior_alpha / posterior_beta.where(posterior_beta > 0.0, np.nan)
    expected_units = posterior_rate
    tail_probability = pd.Series(
        [
            negative_binomial_tail_probability(mean_units, alpha_value, threshold_units)
            for mean_units, alpha_value, threshold_units in zip(
                expected_units,
                posterior_alpha,
                order_threshold_units,
            )
        ],
        index=probability_input_frame.index,
        dtype="float64",
    )

    total_evidence = prior_event_count + recent_event_count
    shift_penalty = 1.0 / (
        1.0 + (posterior_rate - supported_prior_rate).abs() / (supported_prior_rate.abs() + 1.0)
    )
    confidence_score = (
        bounded_sample_strength(total_evidence, reference_count=6.0) * shift_penalty
    ).clip(lower=0.0, upper=1.0)
    confidence_score = confidence_score.where(expected_units.notna())

    return pd.DataFrame(
        {
            "feature_probability_bayesian_poisson_prior_rate": supported_prior_rate,
            "feature_probability_bayesian_poisson_posterior_rate": posterior_rate,
            "feature_probability_bayesian_poisson_expected_units": expected_units,
            "feature_probability_bayesian_poisson_tail_probability": tail_probability,
            "feature_probability_bayesian_poisson_confidence_score": confidence_score,
        },
        index=probability_input_frame.index,
    )