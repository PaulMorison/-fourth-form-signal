from __future__ import annotations

"""Non-promotional baseline-demand orientation features."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series, first_non_null_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import coerce_promotions_frame_types


BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_non_promo_30d_avg_daily_units",
    "feature_non_promo_56d_avg_daily_units",
    "feature_non_promo_84d_avg_daily_units",
    "feature_non_promo_30d_std_daily_units",
    "feature_non_promo_56d_std_daily_units",
    "feature_non_promo_base_trend_30d_vs_56d",
    "feature_non_promo_base_trend_30d_vs_84d",
    "feature_non_promo_days_with_sales_ratio_30d",
    "feature_non_promo_days_with_sales_ratio_56d",
    "feature_non_promo_recent_acceleration_score",
    "feature_non_promo_base_demand_growing_flag",
    "feature_non_promo_history_available_flag",
    "feature_non_promo_low_history_flag",
    "feature_non_promo_stable_history_flag",
)

_LONG_HORIZON_WINDOW_DAYS = 84.0


@dataclass(frozen=True)
class _LongHorizonBaselineSummary:
    avg_daily_units_84d: float
    support_event_count: float


def apply_ft_baseline_demand_orientation(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append current non-promotional base-demand level and trend features."""

    candidate = frame.copy()
    history_source = reference_frame if reference_frame is not None else candidate
    candidate_typed = coerce_promotions_frame_types(candidate)
    history_typed = coerce_promotions_frame_types(history_source)

    non_promo_28_units = first_non_null_series(
        candidate_typed,
        ("feature_non_promo_units_28d", "pre_28d_units"),
    ).clip(lower=0.0)
    non_promo_56_units = first_non_null_series(
        candidate_typed,
        ("feature_non_promo_units_56d", "pre_56d_units"),
    ).clip(lower=0.0)
    non_promo_28_avg = first_non_null_series(
        candidate_typed,
        ("feature_non_promo_avg_daily_units_28d",),
    ).where(lambda values: values > 0.0, non_promo_28_units / 28.0)
    non_promo_56_avg = first_non_null_series(
        candidate_typed,
        ("feature_non_promo_avg_daily_units_56d", "pre_56d_avg_daily_units", "feature_pre_promo_baseline_daily_units", "baseline_daily_units"),
        positive_only=True,
    )
    non_promo_56_avg = non_promo_56_avg.where(non_promo_56_avg > 0.0, non_promo_56_units / 56.0)
    short_horizon_daily = first_non_null_series(
        candidate_typed,
        ("baseline_daily_units", "feature_pre_promo_baseline_daily_units", "pre_28d_avg_daily_units"),
        positive_only=True,
    ).where(lambda values: values > 0.0, non_promo_28_avg)
    non_promo_30_avg = ((non_promo_28_avg * 28.0) + (short_horizon_daily * 2.0)) / 30.0

    pre_28_std = ensure_numeric_series(candidate_typed, "pre_28d_std_daily_units", default=float("nan"))
    pre_56_std = ensure_numeric_series(candidate_typed, "pre_56d_std_daily_units", default=float("nan"))
    non_promo_30_std = pre_28_std.where(pre_28_std > 0.0, pre_56_std)
    non_promo_56_std = pre_56_std.where(pre_56_std > 0.0, pre_28_std)

    pre_7_days_with_sales = ensure_numeric_series(candidate_typed, "pre_7d_days_with_sales")
    pre_28_days_with_sales = ensure_numeric_series(candidate_typed, "pre_28d_days_with_sales")
    pre_56_days_with_sales = ensure_numeric_series(candidate_typed, "pre_56d_days_with_sales")
    days_with_sales_ratio_30d = (
        (pre_28_days_with_sales.clip(lower=0.0, upper=28.0) + ((pre_7_days_with_sales / 7.0).clip(lower=0.0, upper=1.0) * 2.0))
        / 30.0
    ).clip(lower=0.0, upper=1.0)
    days_with_sales_ratio_56d = (pre_56_days_with_sales / 56.0).clip(lower=0.0, upper=1.0)

    long_horizon_summaries = _build_long_horizon_baseline_summaries(
        candidate_typed=candidate_typed,
        history_typed=history_typed,
    )
    non_promo_84_avg = pd.Series(
        [summary.avg_daily_units_84d for summary in long_horizon_summaries],
        index=candidate.index,
        dtype="float64",
    )
    non_promo_84_avg = non_promo_84_avg.where(
        non_promo_84_avg > 0.0,
        non_promo_56_avg.where(non_promo_56_avg > 0.0, non_promo_30_avg),
    )
    long_horizon_support_count = pd.Series(
        [summary.support_event_count for summary in long_horizon_summaries],
        index=candidate.index,
        dtype="float64",
    )

    trend_30d_vs_56d = safe_ratio(
        non_promo_30_avg - non_promo_56_avg,
        non_promo_56_avg.where(non_promo_56_avg > 0.0, np.nan),
    )
    trend_30d_vs_84d = safe_ratio(
        non_promo_30_avg - non_promo_84_avg,
        non_promo_84_avg.where(non_promo_84_avg > 0.0, np.nan),
    )
    recent_acceleration_score = pd.concat(
        [trend_30d_vs_56d, trend_30d_vs_84d],
        axis=1,
    ).mean(axis=1, skipna=True).astype("float64")

    history_available_flag = (
        pre_56_days_with_sales.gt(0.0)
        | long_horizon_support_count.gt(0.0)
        | non_promo_56_avg.gt(0.0)
    ).astype(float)
    low_history_flag = (
        history_available_flag.eq(1.0)
        & ((pre_56_days_with_sales < 8.0) | (days_with_sales_ratio_56d < 0.15) | long_horizon_support_count.lt(1.0))
    ).astype(float)
    stability_ratio = safe_ratio(
        non_promo_56_std,
        non_promo_56_avg.where(non_promo_56_avg > 0.0, np.nan),
    )
    stable_history_flag = (
        history_available_flag.eq(1.0)
        & low_history_flag.eq(0.0)
        & pre_56_days_with_sales.ge(16.0)
        & days_with_sales_ratio_56d.ge(0.30)
        & stability_ratio.fillna(2.0).le(1.0)
    ).astype(float)
    base_demand_growing_flag = (
        history_available_flag.eq(1.0)
        & recent_acceleration_score.fillna(0.0).gt(0.05)
        & days_with_sales_ratio_30d.ge(days_with_sales_ratio_56d * 0.9)
    ).astype(float)

    derived_columns = pd.DataFrame(
        {
            "feature_non_promo_30d_avg_daily_units": non_promo_30_avg,
            "feature_non_promo_56d_avg_daily_units": non_promo_56_avg,
            "feature_non_promo_84d_avg_daily_units": non_promo_84_avg,
            "feature_non_promo_30d_std_daily_units": non_promo_30_std,
            "feature_non_promo_56d_std_daily_units": non_promo_56_std,
            "feature_non_promo_base_trend_30d_vs_56d": trend_30d_vs_56d,
            "feature_non_promo_base_trend_30d_vs_84d": trend_30d_vs_84d,
            "feature_non_promo_days_with_sales_ratio_30d": days_with_sales_ratio_30d,
            "feature_non_promo_days_with_sales_ratio_56d": days_with_sales_ratio_56d,
            "feature_non_promo_recent_acceleration_score": recent_acceleration_score,
            "feature_non_promo_base_demand_growing_flag": base_demand_growing_flag,
            "feature_non_promo_history_available_flag": history_available_flag,
            "feature_non_promo_low_history_flag": low_history_flag,
            "feature_non_promo_stable_history_flag": stable_history_flag,
        },
        index=candidate.index,
    )
    base_columns = candidate.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _build_long_horizon_baseline_summaries(
    *,
    candidate_typed: pd.DataFrame,
    history_typed: pd.DataFrame,
) -> list[_LongHorizonBaselineSummary]:
    history = history_typed.copy()
    history["_promotion_end"] = pd.to_datetime(history.get("promotional_end_date_date"), errors="coerce")
    history["_reference_daily_units"] = first_non_null_series(
        history,
        ("pre_56d_avg_daily_units", "baseline_daily_units", "feature_pre_promo_baseline_daily_units", "pre_28d_avg_daily_units"),
        positive_only=True,
    )
    grouped_history: dict[tuple[object, object], pd.DataFrame] = {}
    for key, group in history.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False):
        grouped_history[tuple(key)] = group.loc[group["_promotion_end"].notna()].sort_values(
            "_promotion_end",
            kind="mergesort",
        )

    candidate_start_dates = pd.to_datetime(candidate_typed.get("promotion_start_date_date"), errors="coerce")
    store_keys = candidate_typed.get("store_number_key")
    sku_keys = candidate_typed.get("sku_number_key")
    summaries: list[_LongHorizonBaselineSummary] = []
    for row_index in range(len(candidate_typed.index)):
        candidate_start_date = candidate_start_dates.iloc[row_index]
        if pd.isna(candidate_start_date):
            summaries.append(_LongHorizonBaselineSummary(avg_daily_units_84d=float("nan"), support_event_count=0.0))
            continue
        candidate_key = (
            store_keys.iloc[row_index] if store_keys is not None else None,
            sku_keys.iloc[row_index] if sku_keys is not None else None,
        )
        prior_rows = grouped_history.get(candidate_key)
        if prior_rows is None or prior_rows.empty:
            summaries.append(_LongHorizonBaselineSummary(avg_daily_units_84d=float("nan"), support_event_count=0.0))
            continue
        strict_prior_rows = prior_rows.loc[prior_rows["_promotion_end"] < candidate_start_date].copy()
        if strict_prior_rows.empty:
            summaries.append(_LongHorizonBaselineSummary(avg_daily_units_84d=float("nan"), support_event_count=0.0))
            continue
        days_back = (candidate_start_date - strict_prior_rows["_promotion_end"]).dt.days.astype("float64")
        recent_rows = strict_prior_rows.loc[days_back <= _LONG_HORIZON_WINDOW_DAYS].copy()
        if recent_rows.empty:
            summaries.append(_LongHorizonBaselineSummary(avg_daily_units_84d=float("nan"), support_event_count=0.0))
            continue
        recent_daily_units = pd.to_numeric(recent_rows["_reference_daily_units"], errors="coerce").dropna()
        summaries.append(
            _LongHorizonBaselineSummary(
                avg_daily_units_84d=float(recent_daily_units.mean()) if not recent_daily_units.empty else float("nan"),
                support_event_count=float(len(recent_daily_units.index)),
            )
        )
    return summaries