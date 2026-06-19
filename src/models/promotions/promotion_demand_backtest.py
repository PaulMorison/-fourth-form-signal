from __future__ import annotations

"""Completed-promotion demand backtest harness.

Given a frame of completed promotions with a `predicted_units_total_promo`
column and an `actual_units_sold_promo` ground-truth column, write:

    promotion_demand_backtest.csv
    promotion_demand_backtest_summary.json

Row-level columns:
    promotion_row_key
    store_number
    sku_number
    promotion_start_date
    promotional_end_date
    discount_percent
    predicted_units_total_promo
    actual_units_sold_promo
    absolute_error_units
    absolute_pct_error
    within_10pct_flag
    within_20pct_flag
    overforecast_flag
    underforecast_flag
    promotion_period_days
    predicted_units_per_day
    actual_units_per_day
    period_absolute_error_units_per_day
    target_end_stock_units
    actual_end_stock_units
    floor_breach_flag
    zero_oos_flag
    target_hit_flag
    end_shape_success_flag
    high_demand_14d_success_flag
    capital_tied_above_trust_target
    speculative_capital_drag_dollars
    speculative_units_sold
    missed_trust_units
    missed_upside_units
    gp_per_capital_committed
    gp_per_speculative_capital
    sell_through_on_accepted_capital

Summary JSON:
    completed_promotions_evaluated
    within_10pct_rate
    within_20pct_rate
    median_absolute_pct_error
    mean_absolute_pct_error
    overforecast_rate
    underforecast_rate
    generated_at_utc

`absolute_pct_error` uses the symmetric SMAPE-style denominator
`(|pred| + |actual|) / 2` so a zero-actual row with a non-zero prediction
yields 200%, not infinity. Rows with both prediction AND actual equal to
zero are scored as 0% error and counted within tolerance.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd


LOGGER = logging.getLogger(__name__)

REQUIRED_BACKTEST_COLUMNS: tuple[str, ...] = (
    "promotion_row_key",
    "predicted_units_total_promo",
    "actual_units_sold_promo",
)

OPTIONAL_PASSTHROUGH_COLUMNS: tuple[str, ...] = (
    "store_number",
    "sku_number",
    "promotion_start_date",
    "promotional_end_date",
    "discount_percent",
)


@dataclass(frozen=True)
class BacktestArtifactPaths:
    rows_csv_path: str
    summary_json_path: str
    summary_csv_path: str


class PromotionBacktestContractError(ValueError):
    """Raised when the backtest input is missing required columns."""


def compute_backtest_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the per-row backtest table without writing artifacts."""

    missing = [name for name in REQUIRED_BACKTEST_COLUMNS if name not in frame.columns]
    if missing:
        raise PromotionBacktestContractError(
            f"Backtest input missing required columns: {missing}"
        )
    predicted = pd.to_numeric(frame["predicted_units_total_promo"], errors="coerce").fillna(0.0)
    actual = pd.to_numeric(frame["actual_units_sold_promo"], errors="coerce").fillna(0.0)
    period_days = _resolve_period_days(frame)
    accepted_units = _first_numeric_series(
        frame,
        ("promo_allocated_units", "pl_allocation_qty", "suggested_order_units", "recommended_order_units"),
    ).where(lambda series: series.notna(), predicted).fillna(0.0).clip(lower=0.0)
    unit_cost = _first_numeric_series(
        frame,
        ("effective_cost_per_unit", "promo_unit_cost", "unit_cost", "cost_per_unit"),
    ).fillna(0.0).clip(lower=0.0)
    unit_gp = _first_numeric_series(
        frame,
        ("promo_gm_unit", "unit_gross_profit", "gross_profit_per_unit"),
    )
    gross_profit_total = _first_numeric_series(
        frame,
        ("actual_gross_profit_promo_dollars", "gross_profit_promo_dollars", "predicted_gross_profit_dollars"),
    )
    unit_gp = unit_gp.where(unit_gp.notna(), gross_profit_total.divide(actual.where(actual.gt(0.0)))).fillna(0.0)
    target_end_stock = _first_numeric_series(
        frame,
        ("target_end_stock_units", "feature_end_of_promo_target_units", "base_units_target"),
    ).fillna(0.0).clip(lower=0.0)
    target_floor_units = _first_numeric_series(
        frame,
        ("feature_end_of_promo_target_floor_units", "target_end_stock_floor_units", "base_units_target"),
    ).where(lambda series: series.notna(), target_end_stock).fillna(0.0).clip(lower=0.0)
    actual_end_stock = _first_numeric_series(
        frame,
        ("actual_end_stock_units", "ending_soh_units", "post_promo_soh_units"),
    )
    actual_end_stock = actual_end_stock.where(
        actual_end_stock.notna(),
        (accepted_units - actual).clip(lower=0.0),
    ).fillna(0.0).clip(lower=0.0)
    high_demand_flag = _first_numeric_series(
        frame,
        ("feature_high_base_demand_end_cover_flag", "high_demand_14d_cover_flag"),
    ).fillna(0.0).clip(lower=0.0, upper=1.0)

    abs_error = (predicted - actual).abs()
    smape_denom = ((predicted.abs() + actual.abs()) / 2.0).replace(0.0, np.nan)
    abs_pct_error = (abs_error / smape_denom * 100.0).fillna(0.0).clip(lower=0.0, upper=200.0)
    predicted_per_day = predicted.divide(period_days.where(period_days.gt(0.0), 1.0)).fillna(0.0)
    actual_per_day = actual.divide(period_days.where(period_days.gt(0.0), 1.0)).fillna(0.0)
    period_abs_error_per_day = (predicted_per_day - actual_per_day).abs()

    within_10 = (abs_pct_error <= 10.0).astype(int)
    within_20 = (abs_pct_error <= 20.0).astype(int)
    over_flag = (predicted > actual).astype(int)
    under_flag = (predicted < actual).astype(int)
    floor_breach_flag = actual_end_stock.lt(target_floor_units).astype(int)
    zero_oos_flag = actual_end_stock.le(0.0).astype(int)
    target_hit_flag = actual_end_stock.ge(target_end_stock).astype(int)
    end_shape_success_flag = (target_hit_flag.eq(1) & zero_oos_flag.eq(0)).astype(int)
    high_demand_14d_success_flag = (target_hit_flag.eq(1) & high_demand_flag.ge(1.0)).astype(int)
    units_above_trust_target = _first_numeric_series(
        frame,
        ("units_above_trust_target", "feature_units_above_trust_target"),
    ).where(lambda series: series.notna(), (actual_end_stock - target_end_stock).clip(lower=0.0)).clip(lower=0.0)
    capital_tied_above_trust_target = _first_numeric_series(
        frame,
        ("capital_tied_above_trust_target", "feature_capital_tied_above_trust_target"),
    ).where(lambda series: series.notna(), units_above_trust_target * unit_cost).clip(lower=0.0)
    speculative_capital_drag_dollars = ((actual_end_stock - target_end_stock).clip(lower=0.0) * unit_cost).clip(lower=0.0)
    speculative_units_sold = (actual - target_floor_units).clip(lower=0.0)
    missed_trust_units = (target_floor_units - actual_end_stock).clip(lower=0.0)
    missed_upside_units = (actual - predicted).clip(lower=0.0)
    realised_gp_proxy = (actual * unit_gp).clip(lower=0.0)
    expected_gp_on_trust_floor_units = (pd.concat([actual, target_floor_units], axis=1).min(axis=1) * unit_gp).clip(lower=0.0)
    expected_gp_on_speculative_units = (speculative_units_sold * unit_gp).clip(lower=0.0)
    capital_committed = (accepted_units * unit_cost).clip(lower=0.0)
    gp_per_capital_committed = realised_gp_proxy.divide(capital_committed.where(capital_committed.gt(0.0))).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    gp_per_speculative_capital = expected_gp_on_speculative_units.divide(
        capital_tied_above_trust_target.where(capital_tied_above_trust_target.gt(0.0))
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    sell_through_on_accepted_capital = actual.divide(accepted_units.where(accepted_units.gt(0.0))).replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(lower=0.0)

    out = pd.DataFrame(
        {
            "promotion_row_key": frame["promotion_row_key"].astype(str),
            "predicted_units_total_promo": predicted.round(2),
            "actual_units_sold_promo": actual.round(2),
            "absolute_error_units": abs_error.round(2),
            "absolute_pct_error": abs_pct_error.round(2),
            "within_10pct_flag": within_10,
            "within_20pct_flag": within_20,
            "overforecast_flag": over_flag,
            "underforecast_flag": under_flag,
            "promotion_period_days": period_days.round(2),
            "predicted_units_per_day": predicted_per_day.round(4),
            "actual_units_per_day": actual_per_day.round(4),
            "period_absolute_error_units_per_day": period_abs_error_per_day.round(4),
            "accepted_capital_units": accepted_units.round(2),
            "target_end_stock_units": target_end_stock.round(2),
            "target_floor_units": target_floor_units.round(2),
            "actual_end_stock_units": actual_end_stock.round(2),
            "floor_breach_flag": floor_breach_flag,
            "zero_oos_flag": zero_oos_flag,
            "target_hit_flag": target_hit_flag,
            "end_shape_success_flag": end_shape_success_flag,
            "high_demand_14d_flag": high_demand_flag.round(0).astype(int),
            "high_demand_14d_success_flag": high_demand_14d_success_flag,
            "units_above_trust_target": units_above_trust_target.round(2),
            "capital_tied_above_trust_target": capital_tied_above_trust_target.round(2),
            "speculative_capital_drag_dollars": speculative_capital_drag_dollars.round(2),
            "speculative_units_sold": speculative_units_sold.round(2),
            "missed_trust_units": missed_trust_units.round(2),
            "missed_upside_units": missed_upside_units.round(2),
            "expected_gp_on_trust_floor_units": expected_gp_on_trust_floor_units.round(2),
            "expected_gp_on_speculative_units": expected_gp_on_speculative_units.round(2),
            "realised_gp_proxy_dollars": realised_gp_proxy.round(2),
            "gp_per_capital_committed": gp_per_capital_committed.round(4),
            "gp_per_speculative_capital": gp_per_speculative_capital.round(4),
            "sell_through_on_accepted_capital": sell_through_on_accepted_capital.round(4),
        }
    )
    for column_name in OPTIONAL_PASSTHROUGH_COLUMNS:
        if column_name in frame.columns:
            out.insert(1, column_name, frame[column_name].values)
    return out


def compute_backtest_summary(rows: pd.DataFrame) -> dict[str, object]:
    """Aggregate per-row table into the summary JSON payload."""

    if rows.empty:
        return {
            "completed_promotions_evaluated": 0,
            "within_10pct_rate": 0.0,
            "within_20pct_rate": 0.0,
            "median_absolute_pct_error": 0.0,
            "mean_absolute_pct_error": 0.0,
            "overforecast_rate": 0.0,
            "underforecast_rate": 0.0,
            "floor_breach_rate": 0.0,
            "target_hit_rate": 0.0,
            "end_shape_success_rate": 0.0,
            "zero_oos_rate": 0.0,
            "zero_oos_success_rate": 0.0,
            "high_demand_14d_success_rate": 0.0,
            "total_capital_above_trust_target": 0.0,
            "total_speculative_capital_drag_dollars": 0.0,
            "total_speculative_units_sold": 0.0,
            "total_missed_trust_units": 0.0,
            "total_missed_upside_units": 0.0,
            "gp_per_capital_committed": 0.0,
            "gp_per_speculative_capital": 0.0,
            "sell_through_on_accepted_capital": 0.0,
            "period_absolute_error_units_per_day_mean": 0.0,
            "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        }
    n = int(len(rows.index))
    high_demand_rows = rows.loc[pd.to_numeric(rows["high_demand_14d_flag"], errors="coerce").fillna(0).ge(1)]
    return {
        "completed_promotions_evaluated": n,
        "within_10pct_rate": round(float(rows["within_10pct_flag"].mean()), 4),
        "within_20pct_rate": round(float(rows["within_20pct_flag"].mean()), 4),
        "median_absolute_pct_error": round(float(rows["absolute_pct_error"].median()), 2),
        "mean_absolute_pct_error": round(float(rows["absolute_pct_error"].mean()), 2),
        "overforecast_rate": round(float(rows["overforecast_flag"].mean()), 4),
        "underforecast_rate": round(float(rows["underforecast_flag"].mean()), 4),
        "floor_breach_rate": round(float(rows["floor_breach_flag"].mean()), 4),
        "target_hit_rate": round(float(rows["target_hit_flag"].mean()), 4),
        "end_shape_success_rate": round(float(rows["end_shape_success_flag"].mean()), 4),
        "zero_oos_rate": round(float(rows["zero_oos_flag"].mean()), 4),
        "zero_oos_success_rate": round(float(1.0 - rows["zero_oos_flag"].mean()), 4),
        "high_demand_14d_success_rate": round(float(high_demand_rows["high_demand_14d_success_flag"].mean()), 4) if not high_demand_rows.empty else 0.0,
        "total_capital_above_trust_target": round(float(rows["capital_tied_above_trust_target"].sum()), 2),
        "total_speculative_capital_drag_dollars": round(float(rows["speculative_capital_drag_dollars"].sum()), 2),
        "total_speculative_units_sold": round(float(rows["speculative_units_sold"].sum()), 2),
        "total_missed_trust_units": round(float(rows["missed_trust_units"].sum()), 2),
        "total_missed_upside_units": round(float(rows["missed_upside_units"].sum()), 2),
        "gp_per_capital_committed": round(float(rows["gp_per_capital_committed"].mean()), 4),
        "gp_per_speculative_capital": round(float(rows["gp_per_speculative_capital"].mean()), 4),
        "sell_through_on_accepted_capital": round(float(rows["sell_through_on_accepted_capital"].mean()), 4),
        "period_absolute_error_units_per_day_mean": round(float(rows["period_absolute_error_units_per_day"].mean()), 4),
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
    }


def write_backtest_artifacts(
    *,
    frame: pd.DataFrame,
    output_root: Path,
) -> BacktestArtifactPaths:
    """Write the two governed backtest artifacts and return their paths."""

    output_root.mkdir(parents=True, exist_ok=True)
    rows = compute_backtest_rows(frame)
    summary = compute_backtest_summary(rows)
    rows_csv_path = output_root / "promotion_demand_backtest.csv"
    summary_json_path = output_root / "promotion_demand_backtest_summary.json"
    summary_csv_path = output_root / "promotion_demand_backtest_summary.csv"
    rows.to_csv(rows_csv_path, index=False)
    pd.DataFrame([summary]).to_csv(summary_csv_path, index=False)
    summary_json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    LOGGER.info(
        "Promotion demand backtest written: rows=%s within_10pct=%.4f within_20pct=%.4f",
        summary["completed_promotions_evaluated"],
        summary["within_10pct_rate"],
        summary["within_20pct_rate"],
    )
    return BacktestArtifactPaths(
        rows_csv_path=str(rows_csv_path),
        summary_json_path=str(summary_json_path),
        summary_csv_path=str(summary_csv_path),
    )


def _first_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    resolved = pd.Series(np.nan, index=frame.index, dtype="float64")
    for column_name in column_names:
        if column_name not in frame.columns:
            continue
        candidate = pd.to_numeric(frame[column_name], errors="coerce")
        resolved = resolved.where(resolved.notna(), candidate)
    return resolved


def _resolve_period_days(frame: pd.DataFrame) -> pd.Series:
    period_days = _first_numeric_series(
        frame,
        ("promotion_period_days", "feature_promo_period_days", "live_promo_window_days", "promo_days"),
    ).replace(0.0, np.nan)
    if "promotion_start_date" in frame.columns and "promotional_end_date" in frame.columns:
        derived = (
            pd.to_datetime(frame["promotional_end_date"], errors="coerce")
            - pd.to_datetime(frame["promotion_start_date"], errors="coerce")
        ).dt.days.add(1)
        period_days = period_days.where(period_days.notna(), derived)
    return period_days.fillna(1.0).clip(lower=1.0)
