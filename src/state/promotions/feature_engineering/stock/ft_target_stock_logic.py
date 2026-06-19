from __future__ import annotations

"""Period-aware target end-stock logic for promotions."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    resolve_allocation_basis_units,
    resolve_promo_window_days,
)


DEFAULT_PROMO_TARGET_FLOOR_UNITS = 2.0
LOW_HISTORY_PROMO_TARGET_FLOOR_UNITS = 1.0
HIGH_BASE_DEMAND_END_COVER_DAYS = 14.0
BILLING_CYCLE_DAYS = 30.0
MONTH_END_RUNOFF_WINDOW_DAYS = 7
MONTH_END_CASHFLOW_MAX_DAYS_COVER = 7.0
HIGH_UNDERLYING_DEMAND_DAILY_UNITS = 1.0

TARGET_STOCK_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_end_of_promo_target_regime",
)

TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_promo_period_days",
    "feature_promo_period_target_units",
    "feature_day_one_target_stock_units",
    "feature_end_of_promo_target_floor_units",
    "feature_trust_floor_units_dynamic",
    "feature_end_of_promo_target_days_cover",
    "feature_end_of_promo_target_units",
    "feature_high_underlying_demand_flag",
    "feature_high_base_demand_end_cover_flag",
    "feature_no_promo_history_flag",
    "feature_month_end_cash_runoff_pressure_flag",
    "feature_month_end_inventory_efficiency_target",
    "feature_days_cover_vs_billing_cycle_target",
    "feature_cash_runoff_target_days_cover",
    "feature_days_cover_cap_for_cashflow",
    "feature_units_needed_for_trust_floor",
    "feature_units_needed_for_high_demand_cover",
    "feature_trust_floor_breach_risk_score",
    "feature_end_shape_success_target_flag",
    "feature_excess_month_end_capital_drag",
    "feature_cashflow_efficiency_score",
    "feature_target_units_above_current_logic",
    "feature_target_units_below_current_logic",
)

TARGET_STOCK_FEATURE_COLUMNS: tuple[str, ...] = (
    *TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
    *TARGET_STOCK_REVIEW_ONLY_FEATURE_COLUMNS,
)

REGIME_PROMO_FLOOR_2 = "promo_floor_2"
REGIME_PROMO_FLOOR_1_LOW_HISTORY = "promo_floor_1_low_history"
REGIME_HIGH_BASE_DEMAND_14D = "promo_end_14d_cover_high_base_demand"
REGIME_MONTH_END_RUNOFF_7D = "month_end_runoff_max_7d_cover"


def apply_ft_target_stock_logic(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append governed period-aware target end-stock and trust features.

    Purpose:
        Transform prior-safe demand and calendar context into auditable target
        stock, trust-floor, high-demand-cover, and month-end-cash-efficiency
        features without using realised promotion outcomes.

    Inputs:
        frame: candidate promotions carrying prior demand, history evidence,
            and stock-basis fields.
        reference_frame: accepted for registry compatibility and unused.

    Outputs:
        A copy of ``frame`` with ``TARGET_STOCK_FEATURE_COLUMNS`` appended.

    Failure behavior:
        Raises ``ValueError`` when promotion duration is missing or non-positive
        for any row. Missing stock-basis evidence is treated as zero available
        units, not as safe sufficiency.
    """

    del reference_frame
    working = frame.copy()
    promo_period_days = resolve_promo_window_days(working).astype("float64")
    _validate_promo_period_days(promo_period_days)

    baseline_daily_units = _baseline_daily_units(working)
    no_promo_history_flag = _no_promo_history_flag(working)
    high_underlying_demand_flag = baseline_daily_units.ge(HIGH_UNDERLYING_DEMAND_DAILY_UNITS).astype(float)
    target_floor_units = _target_floor_units(no_promo_history_flag)
    available_units = _available_units_at_promo_start(working)
    base_target_units = _base_end_stock_target_units(
        target_floor_units=target_floor_units,
        baseline_daily_units=baseline_daily_units,
        high_underlying_demand_flag=high_underlying_demand_flag,
    )
    month_end_cash_flag = _month_end_cash_runoff_pressure_flag(
        working,
        promo_period_days=promo_period_days,
    )
    final_target_units = _apply_month_end_cash_cap(
        base_target_units=base_target_units,
        target_floor_units=target_floor_units,
        baseline_daily_units=baseline_daily_units,
        month_end_cash_flag=month_end_cash_flag,
    )
    promo_period_target_units = baseline_daily_units.multiply(promo_period_days).clip(lower=0.0)
    day_one_target_stock_units = promo_period_target_units.add(final_target_units).clip(lower=0.0)
    units_needed_for_trust_floor = (target_floor_units - available_units).clip(lower=0.0)
    units_needed_for_high_demand_cover = (
        baseline_daily_units.multiply(HIGH_BASE_DEMAND_END_COVER_DAYS) - available_units
    ).clip(lower=0.0)
    current_logic_units = _current_logic_target_units(working)
    target_days_cover = safe_ratio(
        final_target_units,
        baseline_daily_units.where(baseline_daily_units.gt(0.0)),
    )
    target_days_cover_vs_billing_cycle = safe_ratio(
        target_days_cover,
        pd.Series(BILLING_CYCLE_DAYS, index=working.index, dtype="float64"),
    )
    feature_unit_cost = _unit_cost(working)
    excess_month_end_capital_drag = (
        (base_target_units - final_target_units).clip(lower=0.0) * feature_unit_cost
    ).clip(lower=0.0)
    trust_floor_breach_risk_score = safe_ratio(
        units_needed_for_trust_floor,
        target_floor_units.where(target_floor_units.gt(0.0)),
    ).clip(lower=0.0, upper=1.0)
    end_shape_success_target_flag = (
        final_target_units.ge(target_floor_units)
        & (~month_end_cash_flag.astype(bool) | target_days_cover.le(MONTH_END_CASHFLOW_MAX_DAYS_COVER))
    ).astype(float)
    cashflow_efficiency_score = (
        1.0
        - safe_ratio(
            excess_month_end_capital_drag,
            (base_target_units * feature_unit_cost).where(lambda values: values.gt(0.0)),
        )
    ).clip(lower=0.0, upper=1.0)
    target_regime = _target_regime(
        no_promo_history_flag=no_promo_history_flag,
        high_underlying_demand_flag=high_underlying_demand_flag,
        month_end_cash_flag=month_end_cash_flag,
        base_target_units=base_target_units,
        final_target_units=final_target_units,
    )
    derived_columns = pd.DataFrame(
        {
            "feature_promo_period_days": promo_period_days,
            "feature_promo_period_target_units": promo_period_target_units,
            "feature_day_one_target_stock_units": day_one_target_stock_units,
            "feature_end_of_promo_target_floor_units": target_floor_units,
            "feature_trust_floor_units_dynamic": target_floor_units,
            "feature_end_of_promo_target_days_cover": target_days_cover,
            "feature_end_of_promo_target_units": final_target_units,
            "feature_end_of_promo_target_regime": target_regime,
            "feature_high_underlying_demand_flag": high_underlying_demand_flag,
            "feature_high_base_demand_end_cover_flag": high_underlying_demand_flag,
            "feature_no_promo_history_flag": no_promo_history_flag,
            "feature_month_end_cash_runoff_pressure_flag": month_end_cash_flag,
            "feature_month_end_inventory_efficiency_target": final_target_units,
            "feature_days_cover_vs_billing_cycle_target": target_days_cover_vs_billing_cycle,
            "feature_cash_runoff_target_days_cover": month_end_cash_flag * MONTH_END_CASHFLOW_MAX_DAYS_COVER,
            "feature_days_cover_cap_for_cashflow": MONTH_END_CASHFLOW_MAX_DAYS_COVER,
            "feature_units_needed_for_trust_floor": units_needed_for_trust_floor,
            "feature_units_needed_for_high_demand_cover": units_needed_for_high_demand_cover,
            "feature_trust_floor_breach_risk_score": trust_floor_breach_risk_score,
            "feature_end_shape_success_target_flag": end_shape_success_target_flag,
            "feature_excess_month_end_capital_drag": excess_month_end_capital_drag,
            "feature_cashflow_efficiency_score": cashflow_efficiency_score,
            "feature_target_units_above_current_logic": (final_target_units - current_logic_units).clip(lower=0.0),
            "feature_target_units_below_current_logic": (current_logic_units - final_target_units).clip(lower=0.0),
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _validate_promo_period_days(promo_period_days: pd.Series) -> None:
    """Fail loud when governed promotion duration is missing or invalid."""

    missing_mask = promo_period_days.isna() | promo_period_days.le(0.0)
    if bool(missing_mask.any()):
        raise ValueError(
            "ft_target_stock_logic requires positive promotion period days for every row. "
            f"invalid_rows={int(missing_mask.sum())}"
        )


def _baseline_daily_units(frame: pd.DataFrame) -> pd.Series:
    """Return the prior-safe baseline daily demand used for stock targets."""

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
    return candidates.bfill(axis=1).iloc[:, 0].clip(lower=0.0)


def _no_promo_history_flag(frame: pd.DataFrame) -> pd.Series:
    """Return rows with no governed historical promotional demand evidence."""

    evidence_strength = ensure_numeric_series(frame, "feature_promo_history_evidence_strength")
    same_discount_events = ensure_numeric_series(frame, "feature_historical_promo_events_same_discount")
    same_or_better_events = ensure_numeric_series(frame, "feature_historical_promo_events_same_or_better_discount")
    event_count = pd.concat([same_discount_events, same_or_better_events], axis=1).max(axis=1, skipna=True)
    no_history = evidence_strength.fillna(0.0).le(0.0) & event_count.fillna(0.0).le(0.0)
    return no_history.astype(float)


def _target_floor_units(no_promo_history_flag: pd.Series) -> pd.Series:
    """Return the governed dynamic trust floor in units."""

    return pd.Series(
        np.where(
            no_promo_history_flag.ge(1.0),
            LOW_HISTORY_PROMO_TARGET_FLOOR_UNITS,
            DEFAULT_PROMO_TARGET_FLOOR_UNITS,
        ),
        index=no_promo_history_flag.index,
        dtype="float64",
    )


def _available_units_at_promo_start(frame: pd.DataFrame) -> pd.Series:
    """Return governed available units at the promotion start decision point."""

    return resolve_allocation_basis_units(frame).fillna(0.0).clip(lower=0.0)


def _base_end_stock_target_units(
    *,
    target_floor_units: pd.Series,
    baseline_daily_units: pd.Series,
    high_underlying_demand_flag: pd.Series,
) -> pd.Series:
    """Return the unconstrained end-of-promo target before month-end runoff."""

    high_demand_target_units = baseline_daily_units.multiply(HIGH_BASE_DEMAND_END_COVER_DAYS)
    high_demand_target_units = pd.concat([target_floor_units, high_demand_target_units], axis=1).max(axis=1)
    return target_floor_units.where(high_underlying_demand_flag.lt(1.0), high_demand_target_units)


def _month_end_cash_runoff_pressure_flag(
    frame: pd.DataFrame,
    *,
    promo_period_days: pd.Series,
) -> pd.Series:
    """Return month-end runoff pressure rows using resolved promo end date."""

    end_dates = pd.to_datetime(frame.get("promotional_end_date_date"), errors="coerce")
    start_dates = pd.to_datetime(frame.get("promotion_start_date_date"), errors="coerce")
    derived_end_dates = start_dates + pd.to_timedelta(promo_period_days.sub(1.0).clip(lower=0.0), unit="D")
    resolved_end_dates = end_dates.where(end_dates.notna(), derived_end_dates)
    month_end_dates = resolved_end_dates + pd.offsets.MonthEnd(0)
    days_to_month_end = (month_end_dates - resolved_end_dates).dt.days.astype("float64")
    pressure = days_to_month_end.between(0.0, float(MONTH_END_RUNOFF_WINDOW_DAYS - 1), inclusive="both")
    return pressure.fillna(False).astype(float)


def _apply_month_end_cash_cap(
    *,
    base_target_units: pd.Series,
    target_floor_units: pd.Series,
    baseline_daily_units: pd.Series,
    month_end_cash_flag: pd.Series,
) -> pd.Series:
    """Apply the governed month-end 7-day-cover cap without breaching floor."""

    cash_cap_units = baseline_daily_units.multiply(MONTH_END_CASHFLOW_MAX_DAYS_COVER)
    capped_units = pd.concat([target_floor_units, pd.concat([base_target_units, cash_cap_units], axis=1).min(axis=1)], axis=1).max(axis=1)
    return base_target_units.where(month_end_cash_flag.lt(1.0), capped_units)


def _current_logic_target_units(frame: pd.DataFrame) -> pd.Series:
    """Return the legacy trust-floor target for comparison diagnostics."""

    current_logic = ensure_numeric_series(frame, "feature_base_soh_trust_floor_units")
    return current_logic.where(current_logic.notna(), DEFAULT_PROMO_TARGET_FLOOR_UNITS).clip(lower=0.0)


def _unit_cost(frame: pd.DataFrame) -> pd.Series:
    """Return governed per-unit cost for capital-drag diagnostics."""

    candidates = pd.DataFrame(
        {
            "effective_cost_per_unit": ensure_numeric_series(frame, "effective_cost_per_unit", default=float("nan")),
            "promo_unit_cost": ensure_numeric_series(frame, "promo_unit_cost", default=float("nan")),
            "unit_cost": ensure_numeric_series(frame, "unit_cost", default=float("nan")),
            "cost_per_unit": ensure_numeric_series(frame, "cost_per_unit", default=float("nan")),
        },
        index=frame.index,
    )
    return candidates.bfill(axis=1).iloc[:, 0].fillna(0.0).clip(lower=0.0)


def _target_regime(
    *,
    no_promo_history_flag: pd.Series,
    high_underlying_demand_flag: pd.Series,
    month_end_cash_flag: pd.Series,
    base_target_units: pd.Series,
    final_target_units: pd.Series,
) -> pd.Series:
    """Return the governing regime label for the final target-stock shape."""

    regime = pd.Series(REGIME_PROMO_FLOOR_2, index=no_promo_history_flag.index, dtype="object")
    regime = regime.where(no_promo_history_flag.lt(1.0), REGIME_PROMO_FLOOR_1_LOW_HISTORY)
    regime = regime.where(high_underlying_demand_flag.lt(1.0), REGIME_HIGH_BASE_DEMAND_14D)
    cash_cap_applied = month_end_cash_flag.ge(1.0) & final_target_units.lt(base_target_units)
    regime = regime.where(~cash_cap_applied, REGIME_MONTH_END_RUNOFF_7D)
    return regime