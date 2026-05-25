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

    abs_error = (predicted - actual).abs()
    smape_denom = ((predicted.abs() + actual.abs()) / 2.0).replace(0.0, np.nan)
    abs_pct_error = (abs_error / smape_denom * 100.0).fillna(0.0).clip(lower=0.0, upper=200.0)

    within_10 = (abs_pct_error <= 10.0).astype(int)
    within_20 = (abs_pct_error <= 20.0).astype(int)
    over_flag = (predicted > actual).astype(int)
    under_flag = (predicted < actual).astype(int)

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
            "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        }
    n = int(len(rows.index))
    return {
        "completed_promotions_evaluated": n,
        "within_10pct_rate": round(float(rows["within_10pct_flag"].mean()), 4),
        "within_20pct_rate": round(float(rows["within_20pct_flag"].mean()), 4),
        "median_absolute_pct_error": round(float(rows["absolute_pct_error"].median()), 2),
        "mean_absolute_pct_error": round(float(rows["absolute_pct_error"].mean()), 2),
        "overforecast_rate": round(float(rows["overforecast_flag"].mean()), 4),
        "underforecast_rate": round(float(rows["underforecast_flag"].mean()), 4),
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
    rows.to_csv(rows_csv_path, index=False)
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
    )
