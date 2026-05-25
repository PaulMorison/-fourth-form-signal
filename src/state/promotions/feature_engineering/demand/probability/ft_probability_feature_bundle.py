from __future__ import annotations

"""Governed promotions probability feature bundle.

The bundle scans leakage-safe comparable history once, materialises a compact
probability/statistical-evidence summary, and lets narrowly-scoped modules emit
only the outputs they can defend.
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.probability.ft_probability_bayesian_poisson_features import (
    PROBABILITY_BAYESIAN_POISSON_FEATURE_COLUMNS,
    build_probability_bayesian_poisson_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_companion_features import (
    PROBABILITY_COMPANION_FEATURE_COLUMNS,
    build_probability_companion_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_hypothesis_test_features import (
    PROBABILITY_HYPOTHESIS_TEST_FEATURE_COLUMNS,
    build_probability_hypothesis_test_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_negative_binomial_features import (
    PROBABILITY_NEGATIVE_BINOMIAL_FEATURE_COLUMNS,
    build_probability_negative_binomial_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_overallocation_summary import (
    PROBABILITY_OVERALLOCATION_SUMMARY_FEATURE_COLUMNS,
    build_probability_overallocation_summary,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_poisson_features import (
    PROBABILITY_POISSON_FEATURE_COLUMNS,
    build_probability_poisson_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_zero_inflated_features import (
    PROBABILITY_ZERO_INFLATED_FEATURE_COLUMNS,
    build_probability_zero_inflated_features,
)
from state.promotions.feature_engineering.shared.ft_base_math import (
    ensure_numeric_series,
    first_non_null_series,
)
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    coerce_promotions_frame_types,
    normalize_discount_decimal,
)


PROBABILITY_FEATURE_BUNDLE_COLUMNS: tuple[str, ...] = (
    *PROBABILITY_POISSON_FEATURE_COLUMNS,
    *PROBABILITY_NEGATIVE_BINOMIAL_FEATURE_COLUMNS,
    *PROBABILITY_BAYESIAN_POISSON_FEATURE_COLUMNS,
    *PROBABILITY_ZERO_INFLATED_FEATURE_COLUMNS,
    *PROBABILITY_HYPOTHESIS_TEST_FEATURE_COLUMNS,
    *PROBABILITY_COMPANION_FEATURE_COLUMNS,
    *PROBABILITY_OVERALLOCATION_SUMMARY_FEATURE_COLUMNS,
)

PROBABILITY_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_probability_expected_units_consensus",
    "feature_probability_zero_sale_consensus",
    "feature_probability_tail_risk_consensus",
    "feature_probability_overallocation_risk_score",
    "feature_probability_demand_confidence_score",
    "feature_probability_model_use_flag",
    "feature_units_lift_stability_score",
    "feature_same_discount_repeatability_score",
)

PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    column_name
    for column_name in PROBABILITY_FEATURE_BUNDLE_COLUMNS
    if column_name not in set(PROBABILITY_MODEL_USE_FEATURE_COLUMNS)
)

if len(PROBABILITY_FEATURE_BUNDLE_COLUMNS) != len(set(PROBABILITY_FEATURE_BUNDLE_COLUMNS)):
    raise ValueError("Probability feature bundle columns must be unique.")

_DISCOUNT_TOLERANCE_DECIMAL = 0.005


def apply_ft_probability_feature_bundle(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append the governed promotions probability/statistical-evidence layer."""

    candidate = frame.copy()
    history_source = reference_frame if reference_frame is not None else candidate
    probability_input_frame = _build_probability_input_frame(
        candidate_typed=coerce_promotions_frame_types(candidate),
        history_typed=coerce_promotions_frame_types(history_source),
    )
    poisson_frame = build_probability_poisson_features(probability_input_frame)
    negative_binomial_frame = build_probability_negative_binomial_features(
        probability_input_frame
    )
    bayesian_poisson_frame = build_probability_bayesian_poisson_features(
        probability_input_frame
    )
    zero_inflated_frame = build_probability_zero_inflated_features(probability_input_frame)
    hypothesis_test_frame = build_probability_hypothesis_test_features(
        probability_input_frame
    )
    companion_frame = build_probability_companion_features(probability_input_frame)
    overallocation_summary_frame = build_probability_overallocation_summary(
        probability_input_frame,
        poisson_frame=poisson_frame,
        negative_binomial_frame=negative_binomial_frame,
        bayesian_poisson_frame=bayesian_poisson_frame,
        zero_inflated_frame=zero_inflated_frame,
        hypothesis_test_frame=hypothesis_test_frame,
        companion_frame=companion_frame,
    )

    for feature_frame in (
        poisson_frame,
        negative_binomial_frame,
        bayesian_poisson_frame,
        zero_inflated_frame,
        hypothesis_test_frame,
        companion_frame,
        overallocation_summary_frame,
    ):
        for column_name in feature_frame.columns:
            candidate[column_name] = feature_frame[column_name]
    return candidate


def _build_probability_input_frame(
    *,
    candidate_typed: pd.DataFrame,
    history_typed: pd.DataFrame,
) -> pd.DataFrame:
    history = history_typed.copy()
    history_baseline_expected_units = ensure_numeric_series(
        history,
        "baseline_expected_units",
        default=float("nan"),
    )
    history_baseline_daily_units = first_non_null_series(
        history,
        ("baseline_daily_units", "feature_pre_promo_baseline_daily_units"),
    ).where(lambda series: series > 0.0)
    history_promo_window_days = first_non_null_series(
        history,
        ("live_promo_window_days", "promo_days"),
    ).where(lambda series: series > 0.0)
    history_baseline_prior_mean_units = history_baseline_expected_units.where(
        history_baseline_expected_units.notna(),
        history_baseline_daily_units * history_promo_window_days,
    )
    history = history.assign(
        _start=pd.to_datetime(history.get("promotion_start_date_date"), errors="coerce"),
        _end=pd.to_datetime(history.get("promotional_end_date_date"), errors="coerce"),
        _units=ensure_numeric_series(history, "actual_units_sold_promo", default=float("nan")).clip(lower=0.0),
        _baseline_units=history_baseline_prior_mean_units,
        _discount=normalize_discount_decimal(
            ensure_numeric_series(history, "discount_percent", default=float("nan"))
        ),
        _transaction_count=first_non_null_series(
            history,
            ("realised_transaction_count", "realised_promo_transaction_count", "actual_transaction_count_promo"),
        ).where(lambda series: series >= 0.0),
        _solo_transaction_count=ensure_numeric_series(
            history,
            "realised_sku_solo_transaction_count",
            default=float("nan"),
        ).clip(lower=0.0),
        _multi_item_transaction_count=ensure_numeric_series(
            history,
            "realised_sku_multi_item_transaction_count",
            default=float("nan"),
        ).clip(lower=0.0),
        _basket_item_count_sum=ensure_numeric_series(
            history,
            "realised_basket_item_count_sum_when_sku_present",
            default=float("nan"),
        ).clip(lower=0.0),
        _top_companion_sku_1_share=ensure_numeric_series(
            history,
            "realised_top_companion_sku_1_share",
            default=float("nan"),
        ),
        _top_companion_sku_2_share=ensure_numeric_series(
            history,
            "realised_top_companion_sku_2_share",
            default=float("nan"),
        ),
        _companion_concentration=ensure_numeric_series(
            history,
            "realised_companion_concentration_index",
            default=float("nan"),
        ),
    )
    history["_multi_item_rate"] = history["_multi_item_transaction_count"].div(
        history["_transaction_count"].where(history["_transaction_count"] > 0.0, np.nan)
    )
    history["_solo_rate"] = history["_solo_transaction_count"].div(
        history["_transaction_count"].where(history["_transaction_count"] > 0.0, np.nan)
    )
    history["_basket_depth_mean"] = history["_basket_item_count_sum"].div(
        history["_transaction_count"].where(history["_transaction_count"] > 0.0, np.nan)
    )
    concentration_fallback = (
        history["_top_companion_sku_1_share"].clip(lower=0.0, upper=1.0)
        .fillna(0.0)
        .add(history["_top_companion_sku_2_share"].clip(lower=0.0, upper=1.0).fillna(0.0))
        / 2.0
    )
    history["_companion_concentration_signal"] = history["_companion_concentration"].where(
        history["_companion_concentration"].notna(),
        concentration_fallback,
    ).clip(lower=0.0, upper=1.0)
    history["_companion_dependency_score"] = (
        history["_multi_item_rate"].clip(lower=0.0, upper=1.0)
        * history["_companion_concentration_signal"]
        * ((history["_basket_depth_mean"] - 1.0) / 4.0).clip(lower=0.0, upper=1.0)
    ).clip(lower=0.0, upper=1.0)
    history["_companion_overallocation_risk_proxy"] = (
        history["_companion_dependency_score"]
        * (1.0 - history["_solo_rate"].clip(lower=0.0, upper=1.0))
    ).clip(lower=0.0, upper=1.0)
    history["_basket_attach_rate_lift"] = history["_multi_item_rate"] - history["_solo_rate"]
    history["_units_lift"] = history["_units"] - history["_baseline_units"]

    grouped_history: dict[tuple[object, object], pd.DataFrame] = {}
    for key, group in history.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False):
        grouped_history[tuple(key)] = group.loc[group["_end"].notna()].sort_values(
            "_end",
            kind="mergesort",
        )

    candidate_start_dates = pd.to_datetime(
        candidate_typed.get("promotion_start_date_date"),
        errors="coerce",
    )
    candidate_discount = normalize_discount_decimal(
        ensure_numeric_series(candidate_typed, "discount_percent", default=float("nan"))
    )
    candidate_store_keys = candidate_typed.get("store_number_key")
    candidate_sku_keys = candidate_typed.get("sku_number_key")
    baseline_expected_units = ensure_numeric_series(
        candidate_typed,
        "baseline_expected_units",
        default=float("nan"),
    )
    baseline_daily_units = first_non_null_series(
        candidate_typed,
        ("baseline_daily_units", "feature_pre_promo_baseline_daily_units"),
    ).where(lambda series: series > 0.0)
    promo_window_days = first_non_null_series(
        candidate_typed,
        ("live_promo_window_days", "promo_days"),
    ).where(lambda series: series > 0.0)
    baseline_prior_mean_units = baseline_expected_units.where(
        baseline_expected_units.notna(),
        baseline_daily_units * promo_window_days,
    )
    order_threshold_units = first_non_null_series(
        candidate_typed,
        ("pl_allocated", "pl_allocation_qty", "store_adjusted_qty", "required_implied_units"),
    ).where(lambda series: series >= 0.0)
    stock_basis_units = first_non_null_series(
        candidate_typed,
        ("stock_basis_units", "total_stock_available"),
    ).where(lambda series: series >= 0.0)

    rows: list[dict[str, object]] = []
    for row_index in range(len(candidate_typed.index)):
        baseline_prior_mean_value = baseline_prior_mean_units.iloc[row_index]
        row_summary = {
            "probability_same_discount_event_count": 0.0,
            "probability_same_or_better_event_count": 0.0,
            "probability_same_discount_units_sum": float("nan"),
            "probability_same_or_better_units_sum": float("nan"),
            "probability_same_discount_units_mean": float("nan"),
            "probability_same_or_better_units_mean": float("nan"),
            "probability_same_discount_units_variance": float("nan"),
            "probability_same_or_better_units_variance": float("nan"),
            "probability_same_or_better_zero_count": float("nan"),
            "probability_same_or_better_zero_rate": float("nan"),
            "probability_days_since_last_same_or_better_promo": float("nan"),
            "probability_order_threshold_units": float(order_threshold_units.iloc[row_index])
            if not pd.isna(order_threshold_units.iloc[row_index])
            else float("nan"),
            "probability_stock_basis_units": float(stock_basis_units.iloc[row_index])
            if not pd.isna(stock_basis_units.iloc[row_index])
            else float("nan"),
            "probability_baseline_prior_mean_units": float(baseline_prior_mean_value)
            if not pd.isna(baseline_prior_mean_value)
            else float("nan"),
            "probability_promo_window_days": float(promo_window_days.iloc[row_index])
            if not pd.isna(promo_window_days.iloc[row_index])
            else float("nan"),
            "probability_bayesian_prior_rate": float(baseline_prior_mean_value)
            if not pd.isna(baseline_prior_mean_value)
            else float("nan"),
            "probability_bayesian_prior_event_count": 1.0 if not pd.isna(baseline_prior_mean_value) else 0.0,
            "probability_bayesian_recent_units_sum": 0.0,
            "probability_bayesian_recent_event_count": 0.0,
            "probability_bayesian_recent_mean_units": float("nan"),
            "probability_bayesian_recent_variance": float("nan"),
            "probability_units_lift_mean": float("nan"),
            "probability_units_lift_variance": float("nan"),
            "probability_units_lift_sample_size": 0.0,
            "probability_basket_attach_rate_lift_mean": float("nan"),
            "probability_basket_attach_rate_lift_variance": float("nan"),
            "probability_basket_attach_rate_lift_sample_size": 0.0,
            "probability_same_discount_response_mean": float("nan"),
            "probability_same_discount_response_variance": float("nan"),
            "probability_same_discount_response_sample_size": 0.0,
            "probability_sold_in_multi_item_basket_rate": float("nan"),
            "probability_sold_as_solo_item_rate": float("nan"),
            "probability_companion_dependency_score_prior_mean": float("nan"),
            "probability_basket_depth_when_sold_mean": float("nan"),
            "probability_companion_overallocation_risk_proxy": float("nan"),
        }
        candidate_start_date = candidate_start_dates.iloc[row_index]
        if pd.isna(candidate_start_date):
            rows.append(row_summary)
            continue
        candidate_key = (
            candidate_store_keys.iloc[row_index] if candidate_store_keys is not None else None,
            candidate_sku_keys.iloc[row_index] if candidate_sku_keys is not None else None,
        )
        prior_rows = grouped_history.get(candidate_key)
        if prior_rows is None or prior_rows.empty:
            rows.append(row_summary)
            continue
        completed_prior_rows = prior_rows.loc[prior_rows["_end"] < candidate_start_date].copy()
        if completed_prior_rows.empty:
            rows.append(row_summary)
            continue

        candidate_discount_value = candidate_discount.iloc[row_index]
        if pd.isna(candidate_discount_value):
            rows.append(row_summary)
            continue
        same_or_better_mask = (
            completed_prior_rows["_discount"].fillna(-np.inf) + _DISCOUNT_TOLERANCE_DECIMAL
            >= float(candidate_discount_value)
        )
        better_mask = (
            completed_prior_rows["_discount"].fillna(-np.inf)
            > float(candidate_discount_value) + _DISCOUNT_TOLERANCE_DECIMAL
        )
        same_discount_mask = same_or_better_mask & ~better_mask
        same_discount_rows = completed_prior_rows.loc[same_discount_mask].copy()
        same_or_better_rows = completed_prior_rows.loc[same_or_better_mask].copy()
        same_discount_units = same_discount_rows["_units"].dropna().clip(lower=0.0)
        same_or_better_units = same_or_better_rows["_units"].dropna().clip(lower=0.0)

        row_summary.update(
            {
                "probability_same_discount_event_count": float(len(same_discount_units.index)),
                "probability_same_or_better_event_count": float(len(same_or_better_units.index)),
                "probability_same_discount_units_sum": float(same_discount_units.sum())
                if not same_discount_units.empty
                else float("nan"),
                "probability_same_or_better_units_sum": float(same_or_better_units.sum())
                if not same_or_better_units.empty
                else float("nan"),
                "probability_same_discount_units_mean": float(same_discount_units.mean())
                if not same_discount_units.empty
                else float("nan"),
                "probability_same_or_better_units_mean": float(same_or_better_units.mean())
                if not same_or_better_units.empty
                else float("nan"),
                "probability_same_discount_units_variance": _series_variance(same_discount_units),
                "probability_same_or_better_units_variance": _series_variance(same_or_better_units),
                "probability_same_or_better_zero_count": float((same_or_better_units <= 0.0).sum())
                if not same_or_better_units.empty
                else float("nan"),
                "probability_same_or_better_zero_rate": float((same_or_better_units <= 0.0).mean())
                if not same_or_better_units.empty
                else float("nan"),
            }
        )
        if not same_or_better_rows.empty:
            latest_same_or_better_end = same_or_better_rows["_end"].max()
            if pd.notna(latest_same_or_better_end):
                row_summary["probability_days_since_last_same_or_better_promo"] = float(
                    (candidate_start_date - latest_same_or_better_end).days
                )

        older_rows, recent_rows = _split_bayesian_history_rows(same_or_better_rows)
        older_units = older_rows["_units"].dropna().clip(lower=0.0)
        recent_units = recent_rows["_units"].dropna().clip(lower=0.0)
        if not older_units.empty:
            row_summary["probability_bayesian_prior_rate"] = float(older_units.mean())
            row_summary["probability_bayesian_prior_event_count"] = float(len(older_units.index))
        row_summary.update(
            {
                "probability_bayesian_recent_units_sum": float(recent_units.sum())
                if not recent_units.empty
                else 0.0,
                "probability_bayesian_recent_event_count": float(len(recent_units.index)),
                "probability_bayesian_recent_mean_units": float(recent_units.mean())
                if not recent_units.empty
                else float("nan"),
                "probability_bayesian_recent_variance": _series_variance(recent_units),
            }
        )

        units_lift = same_or_better_rows["_units_lift"].dropna()
        same_discount_response = same_discount_rows["_units_lift"].dropna()
        row_summary.update(
            {
                "probability_units_lift_mean": float(units_lift.mean())
                if not units_lift.empty
                else float("nan"),
                "probability_units_lift_variance": _series_variance(units_lift),
                "probability_units_lift_sample_size": float(len(units_lift.index)),
                "probability_same_discount_response_mean": float(same_discount_response.mean())
                if not same_discount_response.empty
                else float("nan"),
                "probability_same_discount_response_variance": _series_variance(
                    same_discount_response
                ),
                "probability_same_discount_response_sample_size": float(
                    len(same_discount_response.index)
                ),
            }
        )

        basket_reference_rows = same_or_better_rows.loc[
            same_or_better_rows["_transaction_count"].fillna(0.0) > 0.0
        ].copy()
        if basket_reference_rows.empty:
            basket_reference_rows = completed_prior_rows.loc[
                completed_prior_rows["_transaction_count"].fillna(0.0) > 0.0
            ].copy()
        if not basket_reference_rows.empty:
            tx_counts = basket_reference_rows["_transaction_count"].clip(lower=0.0)
            total_transaction_count = float(tx_counts.sum())
            if total_transaction_count > 0.0:
                row_summary["probability_sold_in_multi_item_basket_rate"] = float(
                    basket_reference_rows["_multi_item_transaction_count"].clip(lower=0.0).sum()
                    / total_transaction_count
                )
                row_summary["probability_sold_as_solo_item_rate"] = float(
                    basket_reference_rows["_solo_transaction_count"].clip(lower=0.0).sum()
                    / total_transaction_count
                )
                row_summary["probability_basket_depth_when_sold_mean"] = float(
                    basket_reference_rows["_basket_item_count_sum"].clip(lower=0.0).sum()
                    / total_transaction_count
                )
            row_summary["probability_companion_dependency_score_prior_mean"] = _weighted_average(
                basket_reference_rows["_companion_dependency_score"],
                tx_counts,
            )
            row_summary["probability_companion_overallocation_risk_proxy"] = _weighted_average(
                basket_reference_rows["_companion_overallocation_risk_proxy"],
                tx_counts,
            )
            basket_attach_rate_lift = basket_reference_rows["_basket_attach_rate_lift"].dropna()
            row_summary.update(
                {
                    "probability_basket_attach_rate_lift_mean": float(
                        basket_attach_rate_lift.mean()
                    )
                    if not basket_attach_rate_lift.empty
                    else float("nan"),
                    "probability_basket_attach_rate_lift_variance": _series_variance(
                        basket_attach_rate_lift
                    ),
                    "probability_basket_attach_rate_lift_sample_size": float(
                        len(basket_attach_rate_lift.index)
                    ),
                }
            )

        rows.append(row_summary)

    return pd.DataFrame(rows, index=candidate_typed.index)


def _series_variance(series: pd.Series) -> float:
    if len(series.index) <= 1:
        return float("nan")
    return float(pd.to_numeric(series, errors="coerce").var(ddof=0))


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    valid_mask = values.notna() & weights.notna() & (weights > 0.0)
    if not valid_mask.any():
        return float("nan")
    valid_values = pd.to_numeric(values.loc[valid_mask], errors="coerce")
    valid_weights = pd.to_numeric(weights.loc[valid_mask], errors="coerce")
    denominator = float(valid_weights.sum())
    if denominator <= 0.0:
        return float("nan")
    return float((valid_values * valid_weights).sum() / denominator)


def _split_bayesian_history_rows(history_rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if history_rows.empty:
        return history_rows.copy(), history_rows.copy()
    recent_count = 2 if len(history_rows.index) >= 4 else 1
    recent_rows = history_rows.iloc[-recent_count:].copy()
    older_rows = history_rows.iloc[:-recent_count].copy()
    return older_rows, recent_rows