from __future__ import annotations

"""Governed promotions basket and mission context feature bundle.

The bundle scans strictly prior completed same-store same-SKU promotion history
once and builds a compact summary from transaction-structure aggregates already
joined onto completed rows. It intentionally refuses to fabricate buyer-level or
companion-category features because the current governed transaction seam does
not expose those fields.
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.ft_basket_context_features import (
    BASKET_CONTEXT_FEATURE_COLUMNS,
    build_basket_context_features,
)
from state.promotions.feature_engineering.demand.ft_basket_probability_features import (
    BASKET_PROBABILITY_FEATURE_COLUMNS,
    build_basket_probability_features,
)
from state.promotions.feature_engineering.demand.ft_companion_item_features import (
    COMPANION_ITEM_FEATURE_COLUMNS,
    build_companion_item_features,
)
from state.promotions.feature_engineering.demand.ft_stock_constrained_demand_features import (
    STOCK_CONSTRAINED_DEMAND_FEATURE_COLUMNS,
    build_stock_constrained_demand_features,
)
from state.promotions.feature_engineering.demand.ft_transaction_mission_features import (
    TRANSACTION_MISSION_FEATURE_COLUMNS,
    build_transaction_mission_features,
)
from state.promotions.feature_engineering.shared.ft_base_math import (
    ensure_numeric_series,
    first_non_null_series,
)
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    coerce_promotions_frame_types,
)


BASKET_HISTORY_BUNDLE_AGGREGATE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_basket_history_evidence_promo_count",
    "feature_basket_history_transaction_count",
    "feature_basket_history_missing_evidence_flag",
)

BASKET_HISTORY_FEATURE_BUNDLE_COLUMNS: tuple[str, ...] = (
    *BASKET_CONTEXT_FEATURE_COLUMNS,
    *COMPANION_ITEM_FEATURE_COLUMNS,
    *TRANSACTION_MISSION_FEATURE_COLUMNS,
    *STOCK_CONSTRAINED_DEMAND_FEATURE_COLUMNS,
    *BASKET_PROBABILITY_FEATURE_COLUMNS,
    *BASKET_HISTORY_BUNDLE_AGGREGATE_FEATURE_COLUMNS,
)

# The basket layer emits richer descriptive diagnostics than the model should
# learn from directly. Keep the more decision-shaped dependency and evidence
# fields in the trained schema, and leave the weaker descriptive complements for
# review and audit surfaces by default.
BASKET_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_basket_attach_rate",
    "feature_sku_basket_dependency_score",
    "feature_top_companion_sku_1_share",
    "feature_companion_concentration_index",
    "feature_transactions_with_sku_per_day",
    "feature_units_per_transaction_when_sku_present",
    "feature_weekend_share_with_sku",
    "feature_pay_cycle_sensitivity_score",
    "feature_stock_constrained_history_flag",
    "feature_lost_sales_risk_score",
    "feature_probability_sku_in_multi_item_basket",
    "feature_probability_zero_units_given_low_traffic",
    "feature_companion_absence_risk_score",
    "feature_basket_history_evidence_promo_count",
    "feature_basket_history_transaction_count",
    "feature_basket_history_missing_evidence_flag",
)

BASKET_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    column_name
    for column_name in BASKET_HISTORY_FEATURE_BUNDLE_COLUMNS
    if column_name not in set(BASKET_MODEL_USE_FEATURE_COLUMNS)
)

_LOW_TRAFFIC_TRANSACTIONS_PER_DAY_THRESHOLD = 0.75
_STOCK_CAP_HIT_THRESHOLD = 0.95


def apply_ft_basket_context_feature_bundle(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    candidate = frame.copy()
    history_source = reference_frame if reference_frame is not None else candidate
    basket_history_input_frame = _build_basket_history_input_frame(
        candidate_typed=coerce_promotions_frame_types(candidate),
        history_typed=coerce_promotions_frame_types(history_source),
    )
    feature_frames = (
        build_basket_context_features(basket_history_input_frame),
        build_companion_item_features(basket_history_input_frame),
        build_transaction_mission_features(basket_history_input_frame),
        build_stock_constrained_demand_features(basket_history_input_frame),
        build_basket_probability_features(basket_history_input_frame),
        _build_basket_history_aggregate_features(basket_history_input_frame),
    )
    for feature_frame in feature_frames:
        for column_name in feature_frame.columns:
            candidate[column_name] = feature_frame[column_name]
    return candidate


def _build_basket_history_input_frame(
    *,
    candidate_typed: pd.DataFrame,
    history_typed: pd.DataFrame,
) -> pd.DataFrame:
    history = history_typed.copy()
    history = history.assign(
        _start=_datetime_series_or_nat(history, "promotion_start_date_date"),
        _end=_datetime_series_or_nat(history, "promotional_end_date_date"),
        _transaction_count=ensure_numeric_series(
            history,
            "realised_transaction_count",
            default=float("nan"),
        ).clip(lower=0.0),
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
        _basket_item_count_median=ensure_numeric_series(
            history,
            "realised_basket_item_count_median_when_sku_present",
            default=float("nan"),
        ).clip(lower=0.0),
        _basket_value_sum=ensure_numeric_series(
            history,
            "realised_basket_sales_ex_gst_sum_when_sku_present",
            default=float("nan"),
        ).clip(lower=0.0),
        _basket_value_median=ensure_numeric_series(
            history,
            "realised_basket_sales_ex_gst_median_when_sku_present",
            default=float("nan"),
        ).clip(lower=0.0),
        _units_in_multi_item_baskets=ensure_numeric_series(
            history,
            "realised_units_in_multi_item_baskets",
            default=float("nan"),
        ).clip(lower=0.0),
        _multi_item_multi_unit_transaction_count=ensure_numeric_series(
            history,
            "realised_multi_item_multi_unit_transaction_count",
            default=float("nan"),
        ).clip(lower=0.0),
        _weekend_transaction_count=ensure_numeric_series(
            history,
            "realised_weekend_transaction_count_with_sku",
            default=float("nan"),
        ).clip(lower=0.0),
        _pay_cycle_transaction_count=ensure_numeric_series(
            history,
            "realised_pay_cycle_transaction_count_with_sku",
            default=float("nan"),
        ).clip(lower=0.0),
        _top_companion_sku_1_share=ensure_numeric_series(
            history,
            "realised_top_companion_sku_1_share",
            default=float("nan"),
        ).clip(lower=0.0, upper=1.0),
        _top_companion_sku_2_share=ensure_numeric_series(
            history,
            "realised_top_companion_sku_2_share",
            default=float("nan"),
        ).clip(lower=0.0, upper=1.0),
        _companion_concentration_index=ensure_numeric_series(
            history,
            "realised_companion_concentration_index",
            default=float("nan"),
        ).clip(lower=0.0, upper=1.0),
        _actual_units_sold_promo=ensure_numeric_series(
            history,
            "actual_units_sold_promo",
            default=float("nan"),
        ).clip(lower=0.0),
        _actual_days_with_sales_promo=first_non_null_series(
            history,
            ("actual_days_with_sales_promo", "promo_sales_day_count"),
        ).where(lambda series: series >= 0.0),
        _promo_window_days=first_non_null_series(
            history,
            ("live_promo_window_days", "promo_days"),
            positive_only=True,
        ).where(lambda series: series > 0.0),
        _stock_basis_units=first_non_null_series(
            history,
            ("stock_basis_units", "total_stock_available", "pl_allocated"),
            positive_only=True,
        ).where(lambda series: series > 0.0),
    )

    grouped_history: dict[tuple[object, object], pd.DataFrame] = {}
    if {"store_number_key", "sku_number_key"}.issubset(history.columns):
        for key, group in history.groupby(
            ["store_number_key", "sku_number_key"],
            dropna=False,
            sort=False,
        ):
            grouped_history[tuple(key)] = group.loc[group["_end"].notna()].sort_values(
                "_end",
                kind="mergesort",
            )

    candidate_start_dates = _datetime_series_or_nat(
        candidate_typed,
        "promotion_start_date_date",
    )
    candidate_store_keys = _object_series_or_none(candidate_typed, "store_number_key")
    candidate_sku_keys = _object_series_or_none(candidate_typed, "sku_number_key")

    rows: list[dict[str, object]] = []
    for row_index in range(len(candidate_typed.index)):
        row_summary = {
            "basket_history_event_count": 0.0,
            "basket_history_transaction_count": 0.0,
            "basket_history_solo_transaction_count": 0.0,
            "basket_history_multi_item_transaction_count": 0.0,
            "basket_history_item_count_sum": float("nan"),
            "basket_history_item_count_median": float("nan"),
            "basket_history_basket_value_sum": float("nan"),
            "basket_history_basket_value_median": float("nan"),
            "basket_history_top_companion_sku_1_share": float("nan"),
            "basket_history_top_companion_sku_2_share": float("nan"),
            "basket_history_companion_concentration_index": float("nan"),
            "basket_history_weekend_transaction_count": float("nan"),
            "basket_history_pay_cycle_transaction_count": float("nan"),
            "basket_history_total_promo_days": float("nan"),
            "basket_history_total_pay_cycle_days": float("nan"),
            "basket_history_total_units_sold": float("nan"),
            "basket_history_units_in_multi_item_baskets": float("nan"),
            "basket_history_multi_item_multi_unit_transaction_count": float("nan"),
            "basket_history_low_traffic_event_count": 0.0,
            "basket_history_low_traffic_zero_unit_event_count": 0.0,
            "basket_history_stock_constrained_event_count": 0.0,
            "basket_history_stock_constrained_event_share": float("nan"),
            "basket_history_lost_sales_proxy_mean": float("nan"),
        }
        candidate_start_date = candidate_start_dates.iloc[row_index]
        if pd.isna(candidate_start_date):
            rows.append(row_summary)
            continue
        candidate_key = (
            candidate_store_keys.iloc[row_index],
            candidate_sku_keys.iloc[row_index],
        )
        prior_rows = grouped_history.get(candidate_key)
        if prior_rows is None or prior_rows.empty:
            rows.append(row_summary)
            continue
        completed_prior_rows = prior_rows.loc[prior_rows["_end"] < candidate_start_date].copy()
        row_summary["basket_history_event_count"] = float(len(completed_prior_rows.index))
        if completed_prior_rows.empty:
            rows.append(row_summary)
            continue

        transaction_rows = completed_prior_rows.loc[
            completed_prior_rows["_transaction_count"].fillna(0.0) > 0.0
        ].copy()
        transaction_count = (
            float(transaction_rows["_transaction_count"].sum())
            if not transaction_rows.empty
            else 0.0
        )
        row_summary["basket_history_transaction_count"] = transaction_count
        row_summary["basket_history_solo_transaction_count"] = (
            float(transaction_rows["_solo_transaction_count"].sum())
            if not transaction_rows.empty
            else 0.0
        )
        row_summary["basket_history_multi_item_transaction_count"] = (
            float(transaction_rows["_multi_item_transaction_count"].sum())
            if not transaction_rows.empty
            else 0.0
        )
        row_summary["basket_history_weekend_transaction_count"] = (
            float(transaction_rows["_weekend_transaction_count"].sum())
            if not transaction_rows.empty
            else float("nan")
        )
        row_summary["basket_history_pay_cycle_transaction_count"] = (
            float(transaction_rows["_pay_cycle_transaction_count"].sum())
            if not transaction_rows.empty
            else float("nan")
        )
        row_summary["basket_history_total_units_sold"] = float(
            completed_prior_rows["_actual_units_sold_promo"].sum()
        )
        row_summary["basket_history_total_promo_days"] = (
            float(completed_prior_rows["_promo_window_days"].dropna().sum())
            if completed_prior_rows["_promo_window_days"].notna().any()
            else float("nan")
        )
        row_summary["basket_history_total_pay_cycle_days"] = float(
            sum(
                _count_pay_cycle_days(start, end)
                for start, end in zip(
                    completed_prior_rows["_start"],
                    completed_prior_rows["_end"],
                )
            )
        )

        if transaction_count > 0.0:
            row_summary["basket_history_item_count_sum"] = float(
                transaction_rows["_basket_item_count_sum"].sum()
            )
            row_summary["basket_history_item_count_median"] = (
                float(transaction_rows["_basket_item_count_median"].dropna().median())
                if transaction_rows["_basket_item_count_median"].notna().any()
                else float("nan")
            )
            row_summary["basket_history_basket_value_sum"] = float(
                transaction_rows["_basket_value_sum"].sum()
            )
            row_summary["basket_history_basket_value_median"] = (
                float(transaction_rows["_basket_value_median"].dropna().median())
                if transaction_rows["_basket_value_median"].notna().any()
                else float("nan")
            )
            row_summary["basket_history_units_in_multi_item_baskets"] = float(
                transaction_rows["_units_in_multi_item_baskets"].sum()
            )
            row_summary[
                "basket_history_multi_item_multi_unit_transaction_count"
            ] = float(transaction_rows["_multi_item_multi_unit_transaction_count"].sum())
            row_summary["basket_history_top_companion_sku_1_share"] = _weighted_mean(
                transaction_rows["_top_companion_sku_1_share"],
                transaction_rows["_transaction_count"],
            )
            row_summary["basket_history_top_companion_sku_2_share"] = _weighted_mean(
                transaction_rows["_top_companion_sku_2_share"],
                transaction_rows["_transaction_count"],
            )
            row_summary["basket_history_companion_concentration_index"] = _weighted_mean(
                transaction_rows["_companion_concentration_index"],
                transaction_rows["_transaction_count"],
            )

        transaction_per_day = completed_prior_rows["_transaction_count"].divide(
            completed_prior_rows["_promo_window_days"].replace(0.0, np.nan)
        )
        low_traffic_rows = completed_prior_rows.loc[
            transaction_per_day.fillna(0.0) < _LOW_TRAFFIC_TRANSACTIONS_PER_DAY_THRESHOLD
        ]
        row_summary["basket_history_low_traffic_event_count"] = float(
            len(low_traffic_rows.index)
        )
        if not low_traffic_rows.empty:
            row_summary["basket_history_low_traffic_zero_unit_event_count"] = float(
                (low_traffic_rows["_actual_units_sold_promo"].fillna(0.0) <= 0.0).sum()
            )

        stock_proxy_frame = _build_stock_constrained_proxy_frame(completed_prior_rows)
        valid_stock_rows = stock_proxy_frame["lost_sales_proxy"].notna()
        row_summary["basket_history_stock_constrained_event_count"] = float(
            valid_stock_rows.sum()
        )
        if valid_stock_rows.any():
            row_summary["basket_history_stock_constrained_event_share"] = float(
                stock_proxy_frame.loc[valid_stock_rows, "stock_cap_hit_flag"].mean()
            )
            row_summary["basket_history_lost_sales_proxy_mean"] = float(
                stock_proxy_frame.loc[valid_stock_rows, "lost_sales_proxy"].mean()
            )

        rows.append(row_summary)

    return pd.DataFrame(rows, index=candidate_typed.index)


def _build_basket_history_aggregate_features(summary_frame: pd.DataFrame) -> pd.DataFrame:
    evidence_promo_count = ensure_numeric_series(
        summary_frame,
        "basket_history_event_count",
        default=0.0,
    )
    transaction_count = ensure_numeric_series(
        summary_frame,
        "basket_history_transaction_count",
        default=0.0,
    )
    missing_evidence_flag = (evidence_promo_count <= 0.0).astype(float)
    return pd.DataFrame(
        {
            "feature_basket_history_evidence_promo_count": evidence_promo_count,
            "feature_basket_history_transaction_count": transaction_count,
            "feature_basket_history_missing_evidence_flag": missing_evidence_flag,
        },
        index=summary_frame.index,
    )


def _datetime_series_or_nat(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    return pd.to_datetime(frame[column_name], errors="coerce")


def _object_series_or_none(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(None, index=frame.index, dtype="object")
    return frame[column_name]


def _weighted_mean(series: pd.Series, weights: pd.Series) -> float:
    valid = series.notna() & weights.notna() & (weights > 0.0)
    if not valid.any():
        return float("nan")
    return float(
        np.average(
            series.loc[valid].to_numpy(dtype=float),
            weights=weights.loc[valid].to_numpy(dtype=float),
        )
    )


def _count_pay_cycle_days(start: object, end: object) -> int:
    if pd.isna(start) or pd.isna(end):
        return 0
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if end_ts < start_ts:
        return 0
    return sum(
        1
        for current_day in pd.date_range(start_ts, end_ts, freq="D")
        if current_day.day >= 25 or current_day.day <= 3
    )


def _build_stock_constrained_proxy_frame(prior_rows: pd.DataFrame) -> pd.DataFrame:
    promo_days = prior_rows["_promo_window_days"].replace(0.0, np.nan)
    stock_basis = prior_rows["_stock_basis_units"]
    actual_units = prior_rows["_actual_units_sold_promo"]
    days_with_sales = prior_rows["_actual_days_with_sales_promo"].clip(lower=0.0)
    valid = stock_basis.notna() & promo_days.notna() & (promo_days > 0.0)
    stock_cap_hit_flag = actual_units.ge(stock_basis * _STOCK_CAP_HIT_THRESHOLD).where(valid)
    day_shortfall_share = (
        (promo_days - days_with_sales).clip(lower=0.0).divide(promo_days)
    ).where(valid)
    lost_sales_proxy = (
        stock_cap_hit_flag.fillna(False).astype(float) * day_shortfall_share.fillna(0.0)
    ).where(valid)
    return pd.DataFrame(
        {
            "stock_cap_hit_flag": pd.to_numeric(stock_cap_hit_flag, errors="coerce"),
            "lost_sales_proxy": lost_sales_proxy,
        },
        index=prior_rows.index,
    )