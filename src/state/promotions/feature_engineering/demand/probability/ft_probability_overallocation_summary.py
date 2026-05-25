from __future__ import annotations

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.probability.ft_probability_shared_helpers import (
    bounded_sample_strength,
    numeric_series,
    poisson_probability_zero_sale,
    rowwise_nanmean,
    rowwise_non_null_count,
)


PROBABILITY_OVERALLOCATION_SUMMARY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_probability_expected_units_consensus",
    "feature_probability_zero_sale_consensus",
    "feature_probability_tail_risk_consensus",
    "feature_probability_overallocation_risk_score",
    "feature_probability_demand_confidence_score",
    "feature_probability_model_use_flag",
)


def build_probability_overallocation_summary(
    probability_input_frame: pd.DataFrame,
    *,
    poisson_frame: pd.DataFrame,
    negative_binomial_frame: pd.DataFrame,
    bayesian_poisson_frame: pd.DataFrame,
    zero_inflated_frame: pd.DataFrame,
    hypothesis_test_frame: pd.DataFrame,
    companion_frame: pd.DataFrame,
) -> pd.DataFrame:
    poisson_expected = numeric_series(poisson_frame, "feature_probability_poisson_expected_units")
    negative_binomial_expected = numeric_series(
        negative_binomial_frame,
        "feature_probability_negative_binomial_expected_units",
    )
    bayesian_expected = numeric_series(
        bayesian_poisson_frame,
        "feature_probability_bayesian_poisson_expected_units",
    )
    zero_inflated_expected = numeric_series(
        zero_inflated_frame,
        "feature_probability_zero_inflated_expected_units",
    )
    expected_unit_series = [
        poisson_expected,
        negative_binomial_expected,
        bayesian_expected,
        zero_inflated_expected,
    ]

    expected_units_consensus = rowwise_nanmean(expected_unit_series)
    bayesian_zero_sale_probability = pd.Series(
        [poisson_probability_zero_sale(value) for value in bayesian_expected],
        index=probability_input_frame.index,
        dtype="float64",
    )
    zero_sale_consensus = rowwise_nanmean(
        [
            numeric_series(poisson_frame, "feature_probability_poisson_zero_sale_probability"),
            numeric_series(
                negative_binomial_frame,
                "feature_probability_negative_binomial_zero_sale_probability",
            ),
            bayesian_zero_sale_probability,
            numeric_series(
                zero_inflated_frame,
                "feature_probability_zero_inflated_zero_sale_probability",
            ),
        ],
        lower=0.0,
        upper=1.0,
    )
    tail_risk_consensus = rowwise_nanmean(
        [
            numeric_series(poisson_frame, "feature_probability_poisson_tail_probability"),
            numeric_series(
                negative_binomial_frame,
                "feature_probability_negative_binomial_tail_probability",
            ),
            numeric_series(
                bayesian_poisson_frame,
                "feature_probability_bayesian_poisson_tail_probability",
            ),
        ],
        lower=0.0,
        upper=1.0,
    )
    method_overallocation_risk = rowwise_nanmean(
        [
            numeric_series(poisson_frame, "feature_probability_poisson_overallocation_risk_score"),
            numeric_series(
                negative_binomial_frame,
                "feature_probability_negative_binomial_overallocation_risk_score",
            ),
            numeric_series(
                zero_inflated_frame,
                "feature_probability_zero_inflated_overallocation_risk_score",
            ),
        ],
        lower=0.0,
        upper=1.0,
    )
    companion_risk = numeric_series(
        companion_frame,
        "feature_probability_companion_overallocation_risk_score",
    )
    overallocation_risk_score = rowwise_nanmean(
        [
            zero_sale_consensus,
            1.0 - tail_risk_consensus,
            method_overallocation_risk,
            companion_risk,
        ],
        lower=0.0,
        upper=1.0,
    )

    same_or_better_event_count = numeric_series(
        probability_input_frame,
        "probability_same_or_better_event_count",
    ).fillna(0.0)
    supported_model_count = rowwise_non_null_count(expected_unit_series)
    model_count_strength = (supported_model_count / 4.0).clip(lower=0.0, upper=1.0)
    history_strength = bounded_sample_strength(same_or_better_event_count, reference_count=5.0)
    stability_repeatability = rowwise_nanmean(
        [
            numeric_series(hypothesis_test_frame, "feature_units_lift_stability_score"),
            numeric_series(hypothesis_test_frame, "feature_same_discount_repeatability_score"),
            numeric_series(
                bayesian_poisson_frame,
                "feature_probability_bayesian_poisson_confidence_score",
            ),
        ],
        lower=0.0,
        upper=1.0,
    )
    agreement_score = _agreement_score(expected_unit_series)
    demand_confidence_score = rowwise_nanmean(
        [history_strength, model_count_strength, stability_repeatability, agreement_score],
        lower=0.0,
        upper=1.0,
    ).fillna(0.0)

    model_use_flag = (
        (same_or_better_event_count > 0.0)
        & (supported_model_count > 0.0)
        & (demand_confidence_score >= 0.15)
    ).astype(float)

    return pd.DataFrame(
        {
            "feature_probability_expected_units_consensus": expected_units_consensus,
            "feature_probability_zero_sale_consensus": zero_sale_consensus,
            "feature_probability_tail_risk_consensus": tail_risk_consensus,
            "feature_probability_overallocation_risk_score": overallocation_risk_score,
            "feature_probability_demand_confidence_score": demand_confidence_score,
            "feature_probability_model_use_flag": model_use_flag,
        },
        index=probability_input_frame.index,
    )


def _agreement_score(series_list: list[pd.Series]) -> pd.Series:
    combined = np.column_stack(
        [pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan) for series in series_list]
    )
    valid_count = np.sum(~np.isnan(combined), axis=1)
    safe_min = np.min(np.where(np.isnan(combined), np.inf, combined), axis=1)
    safe_max = np.max(np.where(np.isnan(combined), -np.inf, combined), axis=1)
    row_sum = np.nansum(combined, axis=1)
    row_mean = np.divide(
        row_sum,
        valid_count,
        out=np.full(len(row_sum), np.nan, dtype=float),
        where=valid_count > 0,
    )
    normalized_spread = np.divide(
        safe_max - safe_min,
        np.maximum(np.abs(row_mean), 1.0),
        out=np.full(len(row_sum), np.nan, dtype=float),
        where=valid_count > 0,
    )
    score = 1.0 / (1.0 + normalized_spread)
    score[valid_count < 2] = np.nan
    return pd.Series(score, index=series_list[0].index, dtype="float64").clip(lower=0.0, upper=1.0)