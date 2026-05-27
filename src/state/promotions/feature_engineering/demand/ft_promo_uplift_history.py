from __future__ import annotations

"""Promo-uplift-history ft module."""

from collections import deque

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import coerce_promotions_frame_types


_HISTORY_REFERENCE_COLUMNS: tuple[str, ...] = (
    "promotion_row_key",
    "store_number_key",
    "sku_number_key",
    "promotion_start_date_date",
    "promotional_end_date_date",
    "target_realised_uplift_vs_baseline",
    "actual_units_sold",
    "target_actual_units_sold",
    "baseline_expected_units",
)
_ROW_KEY_SOURCE_COLUMNS: tuple[str, ...] = (
    "store_number",
    "store_number_key",
    "sku_number",
    "sku_number_key",
    "promotion_start_date",
    "promotion_start_date_date",
    "promotional_end_date",
    "promotional_end_date_date",
    "promotional_sku_id",
    "promotional_sku_id_key",
    "promotion_name",
)


def apply_ft_promo_uplift_history(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add prior same-sku promo response and markdown-dependence features."""

    candidate = frame.copy()
    historical_reference = reference_frame if reference_frame is not None else candidate
    combined = _build_history_reference(historical_reference, candidate)
    realised_uplift_reference = _resolve_realised_uplift_reference(combined)
    history_feature_columns = [
        "feature_prior_promo_response_same_sku_store",
        "feature_prior_promo_response_same_sku_network",
        "feature_prior_markdown_dependence",
    ]
    combined_with_reference = pd.concat(
        [
            combined.drop(columns=["__realised_uplift_reference", *history_feature_columns], errors="ignore"),
            pd.DataFrame(
                {"__realised_uplift_reference": realised_uplift_reference},
                index=combined.index,
            ),
        ],
        axis=1,
    )
    prior_store_response = _shifted_expanding_mean(
        combined_with_reference,
        group_columns=["sku_number_key", "store_number_key"],
        value_column="__realised_uplift_reference",
    )
    prior_network_response = _shifted_expanding_mean(
        combined_with_reference,
        group_columns=["sku_number_key"],
        value_column="__realised_uplift_reference",
    )
    prior_markdown_dependence = _shifted_cumulative_ratio(
        combined_with_reference,
        group_columns=["sku_number_key", "store_number_key"],
        numerator_column="target_actual_units_sold",
        denominator_column="baseline_expected_units",
    )
    combined = pd.concat(
        [
            combined.drop(columns=history_feature_columns, errors="ignore"),
            pd.DataFrame(
                {
                    "feature_prior_promo_response_same_sku_store": prior_store_response,
                    "feature_prior_promo_response_same_sku_network": prior_network_response,
                    "feature_prior_markdown_dependence": prior_markdown_dependence,
                },
                index=combined.index,
            ),
        ],
        axis=1,
    )
    return candidate.drop(columns=history_feature_columns, errors="ignore").merge(
        combined[
            [
                "promotion_row_key",
                "feature_prior_promo_response_same_sku_store",
                "feature_prior_promo_response_same_sku_network",
                "feature_prior_markdown_dependence",
            ]
        ],
        on="promotion_row_key",
        how="left",
    )


def _build_history_reference(reference_frame: pd.DataFrame, candidate_frame: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat(
        [
            coerce_promotions_frame_types(_select_history_reference_columns(reference_frame)),
            coerce_promotions_frame_types(_select_history_reference_columns(candidate_frame)),
        ],
        ignore_index=True,
        sort=False,
    )
    combined = combined.drop_duplicates(subset=["promotion_row_key"], keep="last")
    return combined.sort_values(
        ["promotion_start_date_date", "promotional_end_date_date", "promotion_row_key"],
        kind="mergesort",
    ).reset_index(drop=True)


def _select_history_reference_columns(frame: pd.DataFrame) -> pd.DataFrame:
    selected_columns = list(_HISTORY_REFERENCE_COLUMNS)
    if "promotion_row_key" not in frame.columns:
        selected_columns.extend(_ROW_KEY_SOURCE_COLUMNS)
    available_columns = tuple(dict.fromkeys(column_name for column_name in selected_columns if column_name in frame.columns))
    return frame.loc[:, available_columns].copy()


def _resolve_realised_uplift_reference(frame: pd.DataFrame) -> pd.Series:
    if "target_realised_uplift_vs_baseline" in frame.columns:
        return ensure_numeric_series(frame, "target_realised_uplift_vs_baseline")
    return safe_ratio(
        ensure_numeric_series(frame, "actual_units_sold") - ensure_numeric_series(frame, "baseline_expected_units"),
        ensure_numeric_series(frame, "baseline_expected_units"),
    )


def _shifted_expanding_mean(
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    value_column: str,
) -> pd.Series:
    return (
        frame.groupby(group_columns, group_keys=False)[value_column]
        .apply(lambda values: values.shift().expanding().mean())
        .fillna(0.0)
    )


def _shifted_cumulative_ratio(
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    numerator_column: str,
    denominator_column: str,
) -> pd.Series:
    numerator = ensure_numeric_series(frame, numerator_column)
    denominator = ensure_numeric_series(frame, denominator_column)
    group_keys = [frame[column_name] for column_name in group_columns]
    numerator_cumsum = numerator.groupby(group_keys).cumsum().groupby(group_keys).shift().fillna(0.0)
    denominator_cumsum = denominator.groupby(group_keys).cumsum().groupby(group_keys).shift().fillna(0.0)
    return safe_ratio(numerator_cumsum, denominator_cumsum)


def rolling_past_density(
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    date_column: str,
    lookback_days: int,
) -> pd.Series:
    """Shared density helper reused by promo recurrence features."""

    result = pd.Series(0.0, index=frame.index, dtype="float64")
    for _, group in frame.groupby(group_columns, sort=False):
        history: deque[pd.Timestamp] = deque()
        event_dates = pd.to_datetime(group[date_column], errors="coerce")
        for index, event_date in zip(group.index, event_dates, strict=False):
            while history and (event_date - history[0]).days > lookback_days:
                history.popleft()
            result.loc[index] = len(history) / lookback_days if lookback_days > 0 else 0.0
            history.append(event_date)
    return result.fillna(0.0)
