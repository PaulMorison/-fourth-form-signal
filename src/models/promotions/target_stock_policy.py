from __future__ import annotations

"""Deterministic target-stock policy layer for promotion execution diagnostics."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_schema_helpers import resolve_promo_window_days


TRUST_FLOOR_DEFAULT_UNITS = 2.0
TRUST_FLOOR_NO_HISTORY_UNITS = 1.0
HIGH_BASE_DEMAND_DAILY_UNITS = 1.0
HIGH_BASE_DEMAND_END_COVER_DAYS = 14.0
MONTH_END_RUNOFF_MAX_DAYS_COVER = 7.0
MONTH_END_MIN_DAYS_COVER = 2.0
MONTH_END_RUNOFF_WINDOW_DAYS = 7

TARGET_STOCK_POLICY_COLUMNS: tuple[str, ...] = (
    "promotion_duration_days",
    "trust_floor_target_units",
    "target_soh_at_promo_end_units",
    "target_soh_at_promo_start_units",
    "month_end_runoff_target_units",
    "high_base_demand_cover_target_units",
    "no_history_minimum_target_units",
    "capital_discipline_cap_units",
    "duration_aware_stock_target_units",
    "target_stock_policy_class",
)

POLICY_CLASS_NO_HISTORY = "no_history_minimum"
POLICY_CLASS_HIGH_BASE_DEMAND = "high_base_demand_14d_cover"
POLICY_CLASS_MONTH_END_RUNOFF = "month_end_runoff_max_7d_cover"
POLICY_CLASS_DEFAULT_TRUST_FLOOR = "default_trust_floor"


def build_target_stock_policy_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return deterministic target-stock policy targets for each row.

    Purpose:
        Separate demand forecasting from governed stock-shape policy by
        converting prior-safe demand and calendar context into start/end SOH,
        trust-floor, month-end, high-demand, and capital-discipline targets.

    Inputs:
        frame: promotion rows carrying promotion duration/date fields,
            baseline demand, and promotional-history evidence.

    Outputs:
        A frame indexed like ``frame`` with ``TARGET_STOCK_POLICY_COLUMNS``.

    Failure behavior:
        Raises ``ValueError`` when duration cannot be resolved to a positive
        number. Missing demand evidence is treated as zero demand but remains
        governed by the trust floor.
    """

    duration_days = _resolve_governed_duration_days(frame)
    invalid_duration = duration_days.isna() | duration_days.le(0.0)
    if bool(invalid_duration.any()):
        raise ValueError(
            "target_stock_policy requires positive promotion duration for every row. "
            f"invalid_rows={int(invalid_duration.sum())}"
        )
    baseline_daily = _baseline_daily_units(frame)
    no_history_flag = _no_promo_history_flag(frame)
    trust_floor_units = pd.Series(
        np.where(no_history_flag.ge(1.0), TRUST_FLOOR_NO_HISTORY_UNITS, TRUST_FLOOR_DEFAULT_UNITS),
        index=frame.index,
        dtype="float64",
    )
    high_base_target = baseline_daily.multiply(HIGH_BASE_DEMAND_END_COVER_DAYS)
    high_base_target = pd.concat([trust_floor_units, high_base_target], axis=1).max(axis=1)
    base_end_target = trust_floor_units.where(
        baseline_daily.lt(HIGH_BASE_DEMAND_DAILY_UNITS),
        high_base_target,
    )
    month_end_flag = _month_end_runoff_pressure_flag(frame, duration_days=duration_days)
    min_runoff_units = pd.concat(
        [trust_floor_units, baseline_daily.multiply(MONTH_END_MIN_DAYS_COVER)],
        axis=1,
    ).max(axis=1)
    month_end_cap_units = baseline_daily.multiply(MONTH_END_RUNOFF_MAX_DAYS_COVER)
    month_end_runoff_target = pd.concat(
        [min_runoff_units, pd.concat([base_end_target, month_end_cap_units], axis=1).min(axis=1)],
        axis=1,
    ).max(axis=1)
    end_target = base_end_target.where(month_end_flag.lt(1.0), month_end_runoff_target)
    promo_demand_target = baseline_daily.multiply(duration_days)
    start_target = promo_demand_target.add(end_target).clip(lower=0.0)
    capital_cap = pd.concat([end_target, month_end_runoff_target], axis=1).min(axis=1)
    policy_class = _policy_class(
        no_history_flag=no_history_flag,
        baseline_daily=baseline_daily,
        month_end_flag=month_end_flag,
    )
    return pd.DataFrame(
        {
            "promotion_duration_days": duration_days,
            "trust_floor_target_units": trust_floor_units,
            "target_soh_at_promo_end_units": end_target,
            "target_soh_at_promo_start_units": start_target,
            "month_end_runoff_target_units": month_end_runoff_target,
            "high_base_demand_cover_target_units": high_base_target,
            "no_history_minimum_target_units": pd.Series(TRUST_FLOOR_NO_HISTORY_UNITS, index=frame.index),
            "capital_discipline_cap_units": capital_cap,
            "duration_aware_stock_target_units": start_target,
            "target_stock_policy_class": policy_class,
        },
        index=frame.index,
        columns=TARGET_STOCK_POLICY_COLUMNS,
    )


def _resolve_governed_duration_days(frame: pd.DataFrame) -> pd.Series:
    """Resolve governed promotion duration from dates, numeric fields, or type."""

    duration = resolve_promo_window_days(frame).astype("float64")
    type_duration = _duration_from_promotion_type(frame)
    return type_duration.where(type_duration.notna(), duration)


def _duration_from_promotion_type(frame: pd.DataFrame) -> pd.Series:
    """Map governed promotion type text to canonical duration days."""

    text = pd.Series("", index=frame.index, dtype="object")
    for column_name in ("promotion_type", "promo_type", "promotion_name"):
        if column_name not in frame.columns:
            continue
        text = text.where(text.astype(str).str.len().gt(0), frame[column_name].fillna("").astype(str).str.lower())
    duration = pd.Series(np.nan, index=frame.index, dtype="float64")
    duration = duration.where(~text.str.contains("online", na=False), 1.0)
    duration = duration.where(~text.str.contains("sales event|sale event", regex=True, na=False), 7.0)
    duration = duration.where(~text.str.contains("new line|new_line", regex=True, na=False), 30.0)
    duration = duration.where(~text.str.contains("normal catalogue|catalogue", regex=True, na=False), 14.0)
    return duration


def _baseline_daily_units(frame: pd.DataFrame) -> pd.Series:
    """Return the prior-safe baseline daily units used for cover targets."""

    candidates = pd.DataFrame(
        {
            "feature_pre_promo_baseline_daily_units": ensure_numeric_series(
                frame,
                "feature_pre_promo_baseline_daily_units",
                default=float("nan"),
            ),
            "baseline_daily_units": ensure_numeric_series(frame, "baseline_daily_units", default=float("nan")),
            "avg_daily_units": ensure_numeric_series(frame, "avg_daily_units", default=float("nan")),
        },
        index=frame.index,
    )
    return candidates.bfill(axis=1).iloc[:, 0].fillna(0.0).clip(lower=0.0)


def _no_promo_history_flag(frame: pd.DataFrame) -> pd.Series:
    """Return rows with no governed historical promotional demand evidence."""

    evidence_strength = ensure_numeric_series(frame, "feature_promo_history_evidence_strength")
    same_discount_events = ensure_numeric_series(frame, "feature_historical_promo_events_same_discount")
    same_or_better_events = ensure_numeric_series(frame, "feature_historical_promo_events_same_or_better_discount")
    event_count = pd.concat([same_discount_events, same_or_better_events], axis=1).max(axis=1, skipna=True)
    return (evidence_strength.fillna(0.0).le(0.0) & event_count.fillna(0.0).le(0.0)).astype(float)


def _month_end_runoff_pressure_flag(
    frame: pd.DataFrame,
    *,
    duration_days: pd.Series,
) -> pd.Series:
    """Return month-end pressure rows whose promotion ends near month close."""

    end_dates = pd.to_datetime(frame.get("promotional_end_date_date"), errors="coerce")
    start_dates = pd.to_datetime(frame.get("promotion_start_date_date"), errors="coerce")
    derived_end_dates = start_dates + pd.to_timedelta(duration_days.sub(1.0).clip(lower=0.0), unit="D")
    resolved_end_dates = end_dates.where(end_dates.notna(), derived_end_dates)
    month_end_dates = resolved_end_dates + pd.offsets.MonthEnd(0)
    days_to_month_end = (month_end_dates - resolved_end_dates).dt.days.astype("float64")
    return days_to_month_end.between(0.0, float(MONTH_END_RUNOFF_WINDOW_DAYS - 1), inclusive="both").fillna(False).astype(float)


def _policy_class(
    *,
    no_history_flag: pd.Series,
    baseline_daily: pd.Series,
    month_end_flag: pd.Series,
) -> pd.Series:
    """Resolve the primary target-stock policy class for each row."""

    policy_class = pd.Series(POLICY_CLASS_DEFAULT_TRUST_FLOOR, index=no_history_flag.index, dtype="object")
    policy_class = policy_class.where(no_history_flag.lt(1.0), POLICY_CLASS_NO_HISTORY)
    policy_class = policy_class.where(baseline_daily.lt(HIGH_BASE_DEMAND_DAILY_UNITS), POLICY_CLASS_HIGH_BASE_DEMAND)
    policy_class = policy_class.where(month_end_flag.lt(1.0), POLICY_CLASS_MONTH_END_RUNOFF)
    return policy_class