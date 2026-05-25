from __future__ import annotations

"""Leakage-safe same-discount demand history features.

Canon ownership:
- same store, same SKU, prior completed promotions only
- strict same-discount evidence separated from same-or-better discount evidence
- no pooling across stores or SKUs
- explicit no-history flags rather than fake precision
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.ft_prior_promo_memory import _DISCOUNT_TOLERANCE_DECIMAL
from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series, first_non_null_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import coerce_promotions_frame_types, normalize_discount_decimal


DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_same_discount_prior_event_count",
    "feature_same_discount_prior_units_avg",
    "feature_same_discount_prior_units_median",
    "feature_same_discount_prior_units_std",
    "feature_same_discount_prior_sell_through_avg",
    "feature_same_discount_prior_stock_cover_avg",
    "feature_same_discount_prior_uplift_ratio_avg",
    "feature_same_discount_prior_uplift_ratio_median",
    "feature_same_discount_prior_uplift_ratio_std",
    "feature_same_discount_recent_event_count",
    "feature_same_discount_days_since_last_event",
    "feature_same_discount_history_available_flag",
)

_RECENT_EVENT_WINDOW_DAYS = 84.0


@dataclass(frozen=True)
class _SameDiscountHistorySummary:
    prior_event_count: float
    prior_units_avg: float
    prior_units_median: float
    prior_units_std: float
    prior_sell_through_avg: float
    prior_stock_cover_avg: float
    prior_uplift_ratio_avg: float
    prior_uplift_ratio_median: float
    prior_uplift_ratio_std: float
    recent_event_count: float
    days_since_last_event: float
    history_available_flag: float


def apply_ft_discount_conditioned_demand(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append strict same-discount demand history features."""

    candidate = frame.copy()
    history_source = reference_frame if reference_frame is not None else candidate
    candidate_typed = coerce_promotions_frame_types(candidate)
    history_typed = build_discount_conditioned_history_frame(history_source)
    summaries = build_same_discount_history_summaries(
        candidate_typed=candidate_typed,
        history_typed=history_typed,
    )
    derived_columns = pd.DataFrame(
        {
            "feature_same_discount_prior_event_count": [summary.prior_event_count for summary in summaries],
            "feature_same_discount_prior_units_avg": [summary.prior_units_avg for summary in summaries],
            "feature_same_discount_prior_units_median": [summary.prior_units_median for summary in summaries],
            "feature_same_discount_prior_units_std": [summary.prior_units_std for summary in summaries],
            "feature_same_discount_prior_sell_through_avg": [summary.prior_sell_through_avg for summary in summaries],
            "feature_same_discount_prior_stock_cover_avg": [summary.prior_stock_cover_avg for summary in summaries],
            "feature_same_discount_prior_uplift_ratio_avg": [summary.prior_uplift_ratio_avg for summary in summaries],
            "feature_same_discount_prior_uplift_ratio_median": [summary.prior_uplift_ratio_median for summary in summaries],
            "feature_same_discount_prior_uplift_ratio_std": [summary.prior_uplift_ratio_std for summary in summaries],
            "feature_same_discount_recent_event_count": [summary.recent_event_count for summary in summaries],
            "feature_same_discount_days_since_last_event": [summary.days_since_last_event for summary in summaries],
            "feature_same_discount_history_available_flag": [summary.history_available_flag for summary in summaries],
        },
        index=candidate.index,
    )
    base_columns = candidate.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def build_discount_conditioned_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a typed history frame with same-discount comparison columns."""

    history = coerce_promotions_frame_types(frame).copy()
    promo_window_days = first_non_null_series(history, ("live_promo_window_days", "promo_days"), positive_only=True)
    baseline_expected_units = ensure_numeric_series(history, "baseline_expected_units", default=float("nan"))
    baseline_daily_units = first_non_null_series(
        history,
        ("baseline_daily_units", "feature_pre_promo_baseline_daily_units", "pre_28d_avg_daily_units", "pre_56d_avg_daily_units"),
        positive_only=True,
    )
    baseline_reference_units = baseline_expected_units.where(
        baseline_expected_units.notna(),
        baseline_daily_units * promo_window_days.where(promo_window_days > 0.0, np.nan),
    )
    stock_basis_units = first_non_null_series(
        history,
        ("stock_basis_units", "total_stock_available", "pl_allocated", "pl_allocation_qty", "store_adjusted_qty", "required_implied_units"),
        positive_only=True,
    )
    actual_units_sold = first_non_null_series(
        history,
        ("actual_units_sold_promo", "target_actual_units_sold", "actual_units_sold"),
    ).where(lambda values: values >= 0.0)
    daily_units = safe_ratio(actual_units_sold, promo_window_days.where(promo_window_days > 0.0, np.nan))

    history["_promotion_start"] = pd.to_datetime(history.get("promotion_start_date_date"), errors="coerce")
    history["_promotion_end"] = pd.to_datetime(history.get("promotional_end_date_date"), errors="coerce")
    history["_discount_decimal"] = normalize_discount_decimal(
        ensure_numeric_series(history, "discount_percent", default=float("nan"))
    )
    history["_actual_units_sold"] = actual_units_sold
    history["_baseline_reference_units"] = baseline_reference_units
    history["_stock_basis_units"] = stock_basis_units
    history["_sell_through_ratio"] = safe_ratio(
        actual_units_sold,
        stock_basis_units.where(stock_basis_units > 0.0, np.nan),
    ).clip(lower=0.0)
    history["_stock_cover_days"] = safe_ratio(
        stock_basis_units,
        daily_units.where(daily_units > 0.0, np.nan),
    ).clip(lower=0.0)
    history["_uplift_ratio"] = safe_ratio(
        actual_units_sold - baseline_reference_units,
        baseline_reference_units.where(baseline_reference_units > 0.0, np.nan),
    )
    return history


def build_same_discount_history_summaries(
    *,
    candidate_typed: pd.DataFrame,
    history_typed: pd.DataFrame,
) -> list[_SameDiscountHistorySummary]:
    """Build strict prior same-discount summaries for each candidate row."""

    grouped_history: dict[tuple[object, object], pd.DataFrame] = {}
    for key, group in history_typed.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False):
        grouped_history[tuple(key)] = group.loc[group["_promotion_end"].notna()].sort_values(
            "_promotion_end",
            kind="mergesort",
        )

    candidate_start_dates = pd.to_datetime(candidate_typed.get("promotion_start_date_date"), errors="coerce")
    candidate_discount = normalize_discount_decimal(
        ensure_numeric_series(candidate_typed, "discount_percent", default=float("nan"))
    )
    store_keys = candidate_typed.get("store_number_key")
    sku_keys = candidate_typed.get("sku_number_key")

    summaries: list[_SameDiscountHistorySummary] = []
    for row_index in range(len(candidate_typed.index)):
        candidate_start_date = candidate_start_dates.iloc[row_index]
        if pd.isna(candidate_start_date):
            summaries.append(_empty_same_discount_summary())
            continue
        candidate_key = (
            store_keys.iloc[row_index] if store_keys is not None else None,
            sku_keys.iloc[row_index] if sku_keys is not None else None,
        )
        prior_rows = grouped_history.get(candidate_key)
        if prior_rows is None or prior_rows.empty:
            summaries.append(_empty_same_discount_summary())
            continue
        strict_prior_rows = prior_rows.loc[prior_rows["_promotion_end"] < candidate_start_date].copy()
        if strict_prior_rows.empty:
            summaries.append(_empty_same_discount_summary())
            continue
        candidate_discount_value = candidate_discount.iloc[row_index]
        same_discount_mask = (
            strict_prior_rows["_discount_decimal"] - candidate_discount_value
        ).abs().le(_DISCOUNT_TOLERANCE_DECIMAL)
        same_discount_rows = strict_prior_rows.loc[same_discount_mask].copy()
        if same_discount_rows.empty:
            summaries.append(_empty_same_discount_summary())
            continue
        days_back = (candidate_start_date - same_discount_rows["_promotion_end"]).dt.days.astype("float64")
        summaries.append(
            _SameDiscountHistorySummary(
                prior_event_count=float(len(same_discount_rows.index)),
                prior_units_avg=_series_mean_or_nan(same_discount_rows["_actual_units_sold"]),
                prior_units_median=_series_median_or_nan(same_discount_rows["_actual_units_sold"]),
                prior_units_std=_series_std_or_nan(same_discount_rows["_actual_units_sold"]),
                prior_sell_through_avg=_series_mean_or_nan(same_discount_rows["_sell_through_ratio"]),
                prior_stock_cover_avg=_series_mean_or_nan(same_discount_rows["_stock_cover_days"]),
                prior_uplift_ratio_avg=_series_mean_or_nan(same_discount_rows["_uplift_ratio"]),
                prior_uplift_ratio_median=_series_median_or_nan(same_discount_rows["_uplift_ratio"]),
                prior_uplift_ratio_std=_series_std_or_nan(same_discount_rows["_uplift_ratio"]),
                recent_event_count=float((days_back <= _RECENT_EVENT_WINDOW_DAYS).sum()),
                days_since_last_event=float(days_back.min()) if not days_back.empty else float("nan"),
                history_available_flag=1.0,
            )
        )
    return summaries


def _empty_same_discount_summary() -> _SameDiscountHistorySummary:
    return _SameDiscountHistorySummary(
        prior_event_count=0.0,
        prior_units_avg=float("nan"),
        prior_units_median=float("nan"),
        prior_units_std=float("nan"),
        prior_sell_through_avg=float("nan"),
        prior_stock_cover_avg=float("nan"),
        prior_uplift_ratio_avg=float("nan"),
        prior_uplift_ratio_median=float("nan"),
        prior_uplift_ratio_std=float("nan"),
        recent_event_count=0.0,
        days_since_last_event=float("nan"),
        history_available_flag=0.0,
    )


def _series_mean_or_nan(series: pd.Series) -> float:
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    return float(cleaned.mean()) if not cleaned.empty else float("nan")


def _series_median_or_nan(series: pd.Series) -> float:
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    return float(cleaned.median()) if not cleaned.empty else float("nan")


def _series_std_or_nan(series: pd.Series) -> float:
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    return float(cleaned.std(ddof=0)) if len(cleaned.index) > 1 else float("nan")