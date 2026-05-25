from __future__ import annotations

"""Risk-adjusted capital-at-risk and retail risk/reward.

This module exposes a single, documented, fail-loud-on-bad-shape function
that computes the user-governed risk-adjusted commercial measures under
their canonical names:

    model_confidence_percent
    capital_at_risk_adjusted_dollars
    expected_incremental_units
    expected_incremental_margin_dollars
    retail_risk_reward_ratio

Formulas (kept simple and inspectable):

    model_confidence_percent
        = round(clip(final_confidence_score, 0, 1) * 100, 0)
        Range: 0..100 integer percentage.

    confidence_fraction
        = clip(final_confidence_score, 0, 1)

    risk_adjustment_factor
        = clip( (1 - confidence_fraction)
                * evidence_factor
                * overstock_factor,
                CAPITAL_AT_RISK_MIN_FACTOR,
                CAPITAL_AT_RISK_MAX_FACTOR )

        - evidence_factor: 1.0 healthy, 1.2 sparse history, 1.5 no evidence.
        - overstock_factor: 1.0 low, 1.2 medium, 1.5 high.
        - Floor and ceiling stop the factor from collapsing to zero on a
          99% confident healthy row, or exploding on an unbounded outlier.

    exposure_dollars
        = max(order_exposure_dollars, leftover_cost_dollars)

        - order_exposure_dollars  = recommended_order_units * unit_cost
        - leftover_cost_dollars   = expected_leftover_units * unit_cost

        Either side can dominate: pre-promo this is usually order exposure;
        post-launch it is more often unsold leftover.

    capital_at_risk_adjusted_dollars
        = round(exposure_dollars * risk_adjustment_factor, 2)

        Higher when confidence is lower; higher when evidence is weaker;
        higher when overstock risk is greater. Bounded above by
        exposure_dollars * CAPITAL_AT_RISK_MAX_FACTOR.

    expected_incremental_units
        = max(predicted_units_total_promo - baseline_expected_units, 0)

        Pure incremental units beyond the baseline you'd have sold
        without a promo. Floored at 0 — a "negative lift" is not a
        commercial reward.

    expected_incremental_margin_dollars
        = round(expected_incremental_units * promo_gm_unit, 2)

        Gross-margin dollars from incremental units only (not total
        promo dollars), which is the right reward to compare against
        commercial capital risk.

    retail_risk_reward_ratio
        = round( expected_incremental_margin_dollars
                 / max(capital_at_risk_adjusted_dollars,
                       CAPITAL_AT_RISK_FLOOR_DOLLARS),
                 2 )

        > 1 means each adjusted-risk dollar buys more than one dollar of
        incremental margin. Floored denominator stops divide-by-zero on
        zero-exposure rows.

Monotonic guarantees enforced by tests:
- Holding everything else fixed, lower `final_confidence_score` (i.e.
  lower confidence) produces higher `capital_at_risk_adjusted_dollars`
  (until the cap is hit).
- Holding `capital_at_risk_adjusted_dollars` fixed, higher
  `expected_incremental_margin_dollars` produces higher
  `retail_risk_reward_ratio`.
"""

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


CAPITAL_AT_RISK_MIN_FACTOR = 0.05
CAPITAL_AT_RISK_MAX_FACTOR = 1.0
CAPITAL_AT_RISK_FLOOR_DOLLARS = 1.0

EVIDENCE_FACTOR_HEALTHY = 1.0
EVIDENCE_FACTOR_SPARSE = 1.2
EVIDENCE_FACTOR_NONE = 1.5

OVERSTOCK_FACTOR_LOW = 1.0
OVERSTOCK_FACTOR_MEDIUM = 1.2
OVERSTOCK_FACTOR_HIGH = 1.5

EVIDENCE_SPARSE_LABELS = frozenset({"low_nonzero_demand", "cold_start_new_line", "sparse_repeat_purchase"})
EVIDENCE_NONE_LABELS = frozenset({"true_zero_demand", "no_evidence", "artificial_collapse"})

REQUIRED_INPUT_COLUMNS: tuple[str, ...] = (
    "final_confidence_score",
    "predicted_units_total_promo",
    "baseline_expected_units",
    "promo_gm_unit",
    "unit_cost",
    "recommended_order_units",
    "expected_leftover_units",
)


@dataclass(frozen=True)
class RiskAdjustedEconomicsResult:
    frame: pd.DataFrame
    output_columns: tuple[str, ...]


OUTPUT_COLUMNS: tuple[str, ...] = (
    "model_confidence_percent",
    "capital_at_risk_adjusted_dollars",
    "expected_incremental_units",
    "expected_incremental_margin_dollars",
    "retail_risk_reward_ratio",
)


class RiskAdjustedEconomicsContractError(ValueError):
    """Raised when required inputs for risk-adjusted economics are missing."""


def compute_risk_adjusted_economics(
    frame: pd.DataFrame,
    *,
    evidence_class_column: str | None = "demand_evidence_class",
    overstock_band_column: str | None = "overstock_risk_band",
) -> RiskAdjustedEconomicsResult:
    """Compute and append the five governed risk-adjusted columns.

    Required input columns: see `REQUIRED_INPUT_COLUMNS`.
    `evidence_class_column` and `overstock_band_column` are optional —
    when absent or null we treat them as healthy/low.
    """

    missing = [name for name in REQUIRED_INPUT_COLUMNS if name not in frame.columns]
    if missing:
        raise RiskAdjustedEconomicsContractError(
            f"Risk-adjusted economics missing required columns: {missing}"
        )

    out = frame.copy()
    confidence_score = pd.to_numeric(out["final_confidence_score"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    out["model_confidence_percent"] = (confidence_score * 100.0).round(0).astype(int)

    evidence_factor = _resolve_evidence_factor(out, evidence_class_column)
    overstock_factor = _resolve_overstock_factor(out, overstock_band_column)
    risk_adjustment_factor = (
        (1.0 - confidence_score) * evidence_factor * overstock_factor
    ).clip(lower=CAPITAL_AT_RISK_MIN_FACTOR, upper=CAPITAL_AT_RISK_MAX_FACTOR)

    unit_cost = pd.to_numeric(out["unit_cost"], errors="coerce").fillna(0.0).clip(lower=0.0)
    rec_units = pd.to_numeric(out["recommended_order_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    leftover_units = pd.to_numeric(out["expected_leftover_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    order_exposure = rec_units * unit_cost
    leftover_cost = leftover_units * unit_cost
    exposure_dollars = pd.concat([order_exposure, leftover_cost], axis=1).max(axis=1)

    out["capital_at_risk_adjusted_dollars"] = (exposure_dollars * risk_adjustment_factor).round(2).astype(float)

    predicted_promo_units = pd.to_numeric(out["predicted_units_total_promo"], errors="coerce").fillna(0.0)
    baseline_units = pd.to_numeric(out["baseline_expected_units"], errors="coerce").fillna(0.0)
    incremental_units = (predicted_promo_units - baseline_units).clip(lower=0.0)
    out["expected_incremental_units"] = incremental_units.astype(float)

    promo_gm_unit = pd.to_numeric(out["promo_gm_unit"], errors="coerce").fillna(0.0)
    incremental_margin = (incremental_units * promo_gm_unit).round(2)
    out["expected_incremental_margin_dollars"] = incremental_margin.astype(float)

    risk_divisor = out["capital_at_risk_adjusted_dollars"].where(
        out["capital_at_risk_adjusted_dollars"] >= CAPITAL_AT_RISK_FLOOR_DOLLARS,
        CAPITAL_AT_RISK_FLOOR_DOLLARS,
    )
    out["retail_risk_reward_ratio"] = (incremental_margin / risk_divisor).round(2).astype(float)

    return RiskAdjustedEconomicsResult(frame=out, output_columns=OUTPUT_COLUMNS)


def _resolve_evidence_factor(frame: pd.DataFrame, column_name: str | None) -> pd.Series:
    if column_name is None or column_name not in frame.columns:
        return pd.Series(EVIDENCE_FACTOR_HEALTHY, index=frame.index, dtype="float64")
    series = frame[column_name].fillna("").astype(str).str.lower()
    factor = pd.Series(EVIDENCE_FACTOR_HEALTHY, index=frame.index, dtype="float64")
    factor = factor.where(~series.isin(EVIDENCE_SPARSE_LABELS), EVIDENCE_FACTOR_SPARSE)
    factor = factor.where(~series.isin(EVIDENCE_NONE_LABELS), EVIDENCE_FACTOR_NONE)
    return factor


def _resolve_overstock_factor(frame: pd.DataFrame, column_name: str | None) -> pd.Series:
    if column_name is None or column_name not in frame.columns:
        return pd.Series(OVERSTOCK_FACTOR_LOW, index=frame.index, dtype="float64")
    series = frame[column_name].fillna("").astype(str).str.upper()
    factor = pd.Series(OVERSTOCK_FACTOR_LOW, index=frame.index, dtype="float64")
    factor = factor.where(series != "MEDIUM", OVERSTOCK_FACTOR_MEDIUM)
    factor = factor.where(series != "HIGH", OVERSTOCK_FACTOR_HIGH)
    return factor
