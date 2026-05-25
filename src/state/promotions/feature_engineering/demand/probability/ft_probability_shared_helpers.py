from __future__ import annotations

import math

import numpy as np
import pandas as pd


def numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def clip_zero_one(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").clip(lower=0.0, upper=1.0)


def rowwise_nanmean(
    series_list: list[pd.Series],
    *,
    lower: float | None = None,
    upper: float | None = None,
) -> pd.Series:
    if not series_list:
        return pd.Series(dtype="float64")
    combined = np.column_stack(
        [pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan) for series in series_list]
    )
    valid_count = np.sum(~np.isnan(combined), axis=1)
    with np.errstate(all="ignore"):
        row_sum = np.nansum(combined, axis=1)
    row_mean = np.divide(
        row_sum,
        valid_count,
        out=np.full(len(row_sum), np.nan, dtype=float),
        where=valid_count > 0,
    )
    result = pd.Series(row_mean, index=series_list[0].index, dtype="float64")
    if lower is not None or upper is not None:
        result = result.clip(lower=lower, upper=upper)
    return result


def rowwise_weighted_mean(
    value_series_list: list[pd.Series],
    weight_series_list: list[pd.Series],
) -> pd.Series:
    if not value_series_list:
        return pd.Series(dtype="float64")
    values = np.column_stack(
        [pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan) for series in value_series_list]
    )
    weights = np.column_stack(
        [pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan) for series in weight_series_list]
    )
    invalid_mask = np.isnan(values) | np.isnan(weights) | (weights <= 0.0)
    safe_weights = np.where(invalid_mask, 0.0, weights)
    safe_values = np.where(invalid_mask, 0.0, values)
    denominator = safe_weights.sum(axis=1)
    numerator = (safe_values * safe_weights).sum(axis=1)
    result = np.divide(
        numerator,
        denominator,
        out=np.full(len(numerator), np.nan, dtype=float),
        where=denominator > 0.0,
    )
    return pd.Series(result, index=value_series_list[0].index, dtype="float64")


def rowwise_non_null_count(series_list: list[pd.Series]) -> pd.Series:
    if not series_list:
        return pd.Series(dtype="float64")
    combined = np.column_stack(
        [pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan) for series in series_list]
    )
    counts = np.sum(~np.isnan(combined), axis=1).astype(float)
    return pd.Series(counts, index=series_list[0].index, dtype="float64")


def bounded_sample_strength(sample_size: pd.Series, *, reference_count: float = 6.0) -> pd.Series:
    return pd.to_numeric(sample_size, errors="coerce").fillna(0.0).clip(lower=0.0).div(reference_count).clip(0.0, 1.0)


def standard_error_from_variance(variance_value: float, sample_size: float) -> float:
    if not np.isfinite(variance_value) or float(variance_value) < 0.0:
        return float("nan")
    if not np.isfinite(sample_size) or float(sample_size) <= 0.0:
        return float("nan")
    return float(math.sqrt(float(variance_value) / float(sample_size)))


def normal_two_sided_p_value(effect_mean: float, standard_error: float) -> float:
    if not np.isfinite(effect_mean) or not np.isfinite(standard_error) or float(standard_error) <= 0.0:
        return float("nan")
    z_score = abs(float(effect_mean)) / float(standard_error)
    return float(math.erfc(z_score / math.sqrt(2.0)))


def confidence_interval_width(
    variance_value: float,
    sample_size: float,
    *,
    z_score: float = 1.96,
) -> float:
    standard_error = standard_error_from_variance(variance_value, sample_size)
    if not np.isfinite(standard_error):
        return float("nan")
    return float(2.0 * float(z_score) * standard_error)


def poisson_probability_zero_sale(expected_units: float) -> float:
    if not np.isfinite(expected_units) or float(expected_units) < 0.0:
        return float("nan")
    return float(math.exp(-float(expected_units)))


def poisson_probability_one_or_more_sale(expected_units: float) -> float:
    probability_zero = poisson_probability_zero_sale(expected_units)
    if not np.isfinite(probability_zero):
        return float("nan")
    return float(1.0 - probability_zero)


def poisson_probability_tail_probability(expected_units: float, threshold_units: float) -> float:
    if not np.isfinite(expected_units) or float(expected_units) < 0.0:
        return float("nan")
    if not np.isfinite(threshold_units):
        return float("nan")
    integer_threshold = int(math.ceil(float(threshold_units)))
    if integer_threshold <= 0:
        return 1.0
    probability_mass = math.exp(-float(expected_units))
    cumulative_probability = probability_mass
    for unit_count in range(1, integer_threshold):
        probability_mass *= float(expected_units) / float(unit_count)
        cumulative_probability += probability_mass
    return float(min(max(1.0 - cumulative_probability, 0.0), 1.0))


def negative_binomial_zero_sale_probability(mean_units: float, dispersion: float) -> float:
    if not _is_valid_negative_binomial_input(mean_units, dispersion):
        return float("nan")
    success_probability = float(dispersion) / (float(dispersion) + float(mean_units))
    return float(success_probability ** float(dispersion))


def negative_binomial_tail_probability(
    mean_units: float,
    dispersion: float,
    threshold_units: float,
) -> float:
    if not _is_valid_negative_binomial_input(mean_units, dispersion):
        return float("nan")
    if not np.isfinite(threshold_units):
        return float("nan")
    integer_threshold = int(math.ceil(float(threshold_units)))
    if integer_threshold <= 0:
        return 1.0
    return float(
        min(
            max(
                1.0
                - _negative_binomial_cdf_le(
                    integer_threshold - 1,
                    mean_units=float(mean_units),
                    dispersion=float(dispersion),
                ),
                0.0,
            ),
            1.0,
        )
    )


def _negative_binomial_cdf_le(
    unit_cap: int,
    *,
    mean_units: float,
    dispersion: float,
) -> float:
    if unit_cap < 0:
        return 0.0
    success_probability = float(dispersion) / (float(dispersion) + float(mean_units))
    failure_probability = 1.0 - success_probability
    probability_mass = success_probability ** float(dispersion)
    cumulative_probability = probability_mass
    for unit_count in range(1, int(unit_cap) + 1):
        probability_mass *= (
            ((float(dispersion) + float(unit_count) - 1.0) / float(unit_count))
            * failure_probability
        )
        cumulative_probability += probability_mass
    return float(min(max(cumulative_probability, 0.0), 1.0))


def _is_valid_negative_binomial_input(mean_units: float, dispersion: float) -> bool:
    return bool(
        np.isfinite(mean_units)
        and np.isfinite(dispersion)
        and float(mean_units) >= 0.0
        and float(dispersion) > 0.0
    )