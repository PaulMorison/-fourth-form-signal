from __future__ import annotations

"""Governed demand-forecast contract for the promotions allocation pipeline.

This contract produces *clean expected-demand* fields that the allocation stock
contract consumes. The guiding principle is that forecasted units represent the
expected customer demand under sufficient stock, not raw historical sales which
may be stock-constrained.

The contract deliberately separates:
  - demand before the promotion starts (lead-up / leakage), and
  - demand during the promotion window itself,

and it never silently fills missing demand with zero. Missing or weak evidence
routes to REVIEW; stock-constrained history is flagged and protected from being
mistaken for genuinely weak demand.
"""

from dataclasses import dataclass
import logging
import math
import time
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEMAND_FORECAST_CONTRACT_STEP_NUMBER = 10

# Canonical contract columns in business-reading order.
DEMAND_FORECAST_CONTRACT_COLUMN_ORDER: tuple[str, ...] = (
    "model_run_date",
    "promotion_start_date",
    "promotion_end_date",
    "days_until_promo_start",
    "promo_window_days",
    "baseline_daily_units",
    "promo_uplift_factor",
    "pre_promo_demand_units",
    "promo_window_demand_units",
    "total_expected_demand_units",
    "stock_constraint_adjustment_units",
    "stock_constraint_flag",
    "demand_forecast_units_q50",
    "demand_forecast_units_q70",
    "demand_forecast_units_q85",
    "demand_forecast_units_q95",
    "selected_demand_quantile",
    "selected_demand_units",
    "demand_forecast_confidence",
    "demand_forecast_basis",
    "demand_forecast_reason_code",
    "demand_forecast_warning",
)

# Deprecated alias columns retained for one release so existing reports/consumers
# do not break while they migrate to the canonical demand-forecast field names.
DEMAND_FORECAST_ALIAS_COLUMNS: dict[str, str] = {
    "expected_promo_demand": "selected_demand_units",
    "expected_units_total_promo": "promo_window_demand_units",
    "expected_units_before_promo_start": "pre_promo_demand_units",
}

# Confidence vocabulary (closed set).
CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_REVIEW = "REVIEW"
DEMAND_CONFIDENCE_LEVELS: frozenset[str] = frozenset(
    {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW, CONFIDENCE_REVIEW}
)

# Demand basis vocabulary.
BASIS_MODEL_PREDICTION = "MODEL_PREDICTION"
BASIS_BASELINE_UPLIFT = "BASELINE_UPLIFT"
BASIS_REVIEW = "REVIEW_DEMAND_FORECAST"
BASIS_STOCK_CONSTRAINED_HISTORY = "STOCK_CONSTRAINED_HISTORY"
BASIS_INVENTORY_INTEGRITY_CONTAMINATED = "INVENTORY_INTEGRITY_CONTAMINATED"

# Reason codes (always populated).
REASON_MODEL_PREDICTION_USED = "MODEL_PREDICTION_USED"
REASON_BASELINE_UPLIFT_USED = "BASELINE_UPLIFT_USED"
REASON_REVIEW_NO_DEMAND_EVIDENCE = "REVIEW_DEMAND_FORECAST"
REASON_STOCK_CONSTRAINED_HISTORY = "STOCK_CONSTRAINED_HISTORY_ADJUSTED"
REASON_INVENTORY_INTEGRITY = "INVENTORY_INTEGRITY_CONTAMINATED"

# Selected-quantile vocabulary.
QUANTILE_Q50 = "q50"
QUANTILE_Q70 = "q70"
QUANTILE_Q85 = "q85"
QUANTILE_Q95 = "q95"
QUANTILE_OVERRIDE = "override"

# Confidence thresholds on the [0, 1] fraction.
CONFIDENCE_HIGH_THRESHOLD = 0.66
CONFIDENCE_MEDIUM_THRESHOLD = 0.40

# Quantile spread shape. Spread `s` scales with uncertainty so that the gap
# between q50 and q95 widens when we are unsure and narrows when we are sure.
QUANTILE_SPREAD_FLOOR = 0.10
QUANTILE_SPREAD_GAIN = 0.90
QUANTILE_MULTIPLIER_Q70 = 0.40
QUANTILE_MULTIPLIER_Q85 = 0.90
QUANTILE_MULTIPLIER_Q95 = 1.60

# Documented uplift applied when prior comparable promo sales were stock
# constrained (SOH hit zero). We must not treat that suppressed history as
# genuinely weak demand.
STOCK_CONSTRAINED_DEMAND_UPLIFT = 0.25

DEFAULT_PROMO_UPLIFT_FACTOR = 1.0

# Patch B - demand-collapse guard. Surface (never auto-correct) the high-risk
# case where the model/source promo-window demand collapses to 0 or 1 unit while
# a feature-layer demand signal is materially higher. We do not inflate demand
# and do not route to REVIEW; we only populate demand_forecast_warning so the
# defect is visible in customer output and diagnostics/validation.
DEMAND_COLLAPSE_PROMO_UNITS_MAX = 1
DEMAND_COLLAPSE_FEATURE_FLOOR = 5.0
DEMAND_COLLAPSE_FEATURE_RATIO = 3.0
DEMAND_COLLAPSE_RISK_WARNING = "DEMAND_COLLAPSE_RISK_FEATURE_SIGNAL_HIGHER"
DEMAND_COLLAPSE_RISK_DETAIL = "MODEL_PREDICTION_COLLAPSE_RISK"


@dataclass(frozen=True)
class DemandForecastInputRow:
    model_run_date: str
    promotion_start_date: str
    promotion_end_date: str
    baseline_daily_units: float = 0.0
    promo_uplift_factor: float = DEFAULT_PROMO_UPLIFT_FACTOR
    promo_window_days: int | None = None
    days_until_promo_start: int | None = None
    # Optional, horizon-bounded pre-promo demand (a documented modifier path).
    pre_promo_demand_units_input: float | None = None
    pre_promo_modifier: float = 1.0
    # Model promo-window prediction (units across the whole promo window).
    model_promo_window_units: float | None = None
    model_prediction_valid: bool = True
    # Uncertainty / trust inputs.
    confidence_fraction: float = 0.5
    sparse_or_weak_evidence: bool = False
    # Stock-truth signals.
    soh_zero_in_comparable_promo: bool = False
    negative_soh_detected: bool = False
    # Selection-policy inputs.
    high_stockout_cost: bool = False
    high_basket_importance: bool = False
    high_capital_drag: bool = False
    # Optional documented hard override of selected demand units.
    selected_demand_units_override: float | None = None
    # Optional feature-layer demand signal used only to detect (not correct) a
    # model/source demand collapse. Never overwrites the model prediction.
    feature_demand_signal: float | None = None

    def compute(self) -> dict[str, Any]:
        return compute_demand_forecast_row(self)


def _is_valid_number(value: float | None) -> bool:
    if value is None:
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(numeric)


def _as_whole_units(value: float) -> int:
    return int(max(round(float(value)), 0))


def compute_days_until_promo_start(
    *,
    model_run_date: str | pd.Timestamp | None,
    promotion_start_date: str | pd.Timestamp | None,
) -> int:
    model_dt = pd.to_datetime(model_run_date, errors="coerce")
    promo_start_dt = pd.to_datetime(promotion_start_date, errors="coerce")
    if pd.isna(model_dt) or pd.isna(promo_start_dt):
        return 0
    return max(int((promo_start_dt - model_dt).days), 0)


def compute_promo_window_days(
    *,
    promotion_start_date: str | pd.Timestamp | None,
    promotion_end_date: str | pd.Timestamp | None,
) -> int:
    start_dt = pd.to_datetime(promotion_start_date, errors="coerce")
    end_dt = pd.to_datetime(promotion_end_date, errors="coerce")
    if pd.isna(start_dt) or pd.isna(end_dt):
        return 1
    return max(int((end_dt - start_dt).days) + 1, 1)


def _resolve_confidence_level(
    *,
    confidence_fraction: float,
    routed_to_review: bool,
) -> str:
    if routed_to_review:
        return CONFIDENCE_REVIEW
    fraction = max(min(float(confidence_fraction), 1.0), 0.0)
    if fraction >= CONFIDENCE_HIGH_THRESHOLD:
        return CONFIDENCE_HIGH
    if fraction >= CONFIDENCE_MEDIUM_THRESHOLD:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _resolve_uncertainty(
    *,
    confidence_fraction: float,
    confidence_level: str,
    sparse_or_weak_evidence: bool,
    stock_constraint_flag: bool,
) -> float:
    fraction = max(min(float(confidence_fraction), 1.0), 0.0)
    uncertainty = 1.0 - fraction
    if confidence_level == CONFIDENCE_REVIEW:
        uncertainty = max(uncertainty, 0.85)
    if sparse_or_weak_evidence:
        uncertainty = max(uncertainty, 0.6)
    if stock_constraint_flag:
        uncertainty = max(uncertainty, 0.5)
    return max(min(uncertainty, 1.0), 0.0)


def _compute_quantiles(*, base_units: float, uncertainty: float) -> tuple[int, int, int, int]:
    base = max(float(base_units), 0.0)
    spread = QUANTILE_SPREAD_FLOOR + QUANTILE_SPREAD_GAIN * max(min(uncertainty, 1.0), 0.0)
    q50 = _as_whole_units(base)
    q70 = _as_whole_units(base * (1.0 + QUANTILE_MULTIPLIER_Q70 * spread))
    q85 = _as_whole_units(base * (1.0 + QUANTILE_MULTIPLIER_Q85 * spread))
    q95 = _as_whole_units(base * (1.0 + QUANTILE_MULTIPLIER_Q95 * spread))
    # Enforce monotonicity defensively against rounding ties.
    q70 = max(q70, q50)
    q85 = max(q85, q70)
    q95 = max(q95, q85)
    return q50, q70, q85, q95


def _select_quantile(
    *,
    confidence_level: str,
    high_stockout_cost: bool,
    high_basket_importance: bool,
    high_capital_drag: bool,
    sparse_or_weak_evidence: bool,
) -> str:
    # Review/low trust always stays at the conservative base quantile.
    if confidence_level in {CONFIDENCE_REVIEW, CONFIDENCE_LOW}:
        return QUANTILE_Q50
    # High trust facing a costly stockout protects availability with the top
    # quantile, even under capital drag: we trust the demand and the stockout
    # is expensive.
    if high_stockout_cost and confidence_level == CONFIDENCE_HIGH:
        return QUANTILE_Q95
    # Otherwise weak evidence / heavy capital drag stays conservative at q50.
    if high_capital_drag or sparse_or_weak_evidence:
        return QUANTILE_Q50
    if high_stockout_cost or high_basket_importance:
        return QUANTILE_Q85
    return QUANTILE_Q50


def compute_demand_forecast_row(row: DemandForecastInputRow) -> dict[str, Any]:
    """Compute one governed demand-forecast row from explicit demand inputs."""
    days_until = (
        int(row.days_until_promo_start)
        if row.days_until_promo_start is not None
        else compute_days_until_promo_start(
            model_run_date=row.model_run_date,
            promotion_start_date=row.promotion_start_date,
        )
    )
    days_until = max(days_until, 0)
    promo_window_days = (
        int(row.promo_window_days)
        if row.promo_window_days is not None
        else compute_promo_window_days(
            promotion_start_date=row.promotion_start_date,
            promotion_end_date=row.promotion_end_date,
        )
    )
    promo_window_days = max(promo_window_days, 1)

    baseline_daily = max(float(row.baseline_daily_units), 0.0)
    uplift = float(row.promo_uplift_factor) if _is_valid_number(row.promo_uplift_factor) else DEFAULT_PROMO_UPLIFT_FACTOR
    uplift = max(uplift, 0.0)

    # ---- Pre-promo demand (leakage before the promotion starts) ----------
    pre_promo_modifier = max(float(row.pre_promo_modifier), 0.0)
    if _is_valid_number(row.pre_promo_demand_units_input):
        pre_promo = max(float(row.pre_promo_demand_units_input), 0.0) * pre_promo_modifier
    else:
        pre_promo = baseline_daily * float(days_until) * pre_promo_modifier
    pre_promo = max(pre_promo, 0.0)

    # ---- Promo-window demand (sufficient-stock expectation) ---------------
    model_units_valid = bool(row.model_prediction_valid) and _is_valid_number(row.model_promo_window_units)
    if model_units_valid and float(row.model_promo_window_units) >= 0.0:
        base_promo = max(float(row.model_promo_window_units), 0.0)
        basis = BASIS_MODEL_PREDICTION
        reason_code = REASON_MODEL_PREDICTION_USED
        routed_to_review = False
    elif baseline_daily > 0.0:
        base_promo = baseline_daily * uplift * float(promo_window_days)
        basis = BASIS_BASELINE_UPLIFT
        reason_code = REASON_BASELINE_UPLIFT_USED
        routed_to_review = False
    else:
        # Neither model nor baseline is usable: never silently zero.
        base_promo = 0.0
        basis = BASIS_REVIEW
        reason_code = REASON_REVIEW_NO_DEMAND_EVIDENCE
        routed_to_review = True

    warnings: list[str] = []

    # ---- Stock-truth handling ---------------------------------------------
    stock_constraint_flag = False
    stock_constraint_adjustment = 0.0
    if bool(row.negative_soh_detected):
        stock_constraint_flag = True
        basis = BASIS_INVENTORY_INTEGRITY_CONTAMINATED
        reason_code = REASON_INVENTORY_INTEGRITY
        warnings.append(
            "Negative SOH detected in source inventory; demand history is integrity-contaminated and must be reviewed."
        )
    elif bool(row.soh_zero_in_comparable_promo):
        stock_constraint_flag = True
        # Protect against treating stock-constrained low sales as weak demand:
        # uplift the base expectation by a documented factor.
        stock_constraint_adjustment = base_promo * STOCK_CONSTRAINED_DEMAND_UPLIFT
        base_promo = base_promo + stock_constraint_adjustment
        if basis not in {BASIS_REVIEW, BASIS_INVENTORY_INTEGRITY_CONTAMINATED}:
            basis = BASIS_STOCK_CONSTRAINED_HISTORY
            reason_code = REASON_STOCK_CONSTRAINED_HISTORY
        warnings.append(
            "Comparable prior promo hit zero SOH; historical sales were stock-constrained and likely understate true demand."
        )

    promo_window = max(base_promo, 0.0)
    total_demand = pre_promo + promo_window

    confidence_level = _resolve_confidence_level(
        confidence_fraction=row.confidence_fraction,
        routed_to_review=routed_to_review,
    )
    uncertainty = _resolve_uncertainty(
        confidence_fraction=row.confidence_fraction,
        confidence_level=confidence_level,
        sparse_or_weak_evidence=bool(row.sparse_or_weak_evidence),
        stock_constraint_flag=stock_constraint_flag,
    )

    q50, q70, q85, q95 = _compute_quantiles(base_units=promo_window, uncertainty=uncertainty)
    quantile_lookup = {
        QUANTILE_Q50: q50,
        QUANTILE_Q70: q70,
        QUANTILE_Q85: q85,
        QUANTILE_Q95: q95,
    }

    selected_quantile = _select_quantile(
        confidence_level=confidence_level,
        high_stockout_cost=bool(row.high_stockout_cost),
        high_basket_importance=bool(row.high_basket_importance),
        high_capital_drag=bool(row.high_capital_drag),
        sparse_or_weak_evidence=bool(row.sparse_or_weak_evidence),
    )
    if _is_valid_number(row.selected_demand_units_override):
        selected_quantile = QUANTILE_OVERRIDE
        selected_units = _as_whole_units(max(float(row.selected_demand_units_override), 0.0))
    else:
        selected_units = int(quantile_lookup[selected_quantile])

    if routed_to_review:
        warnings.append("Demand evidence missing or too weak to forecast; routed to REVIEW_DEMAND_FORECAST.")

    # ---- Demand-collapse guard (Patch B) ----------------------------------
    # If the model/source promo-window demand collapsed to 0/1 while the
    # feature-layer demand signal is materially higher, surface a warning. We do
    # NOT inflate demand and do NOT route to REVIEW; the numeric forecast stays
    # exactly as predicted so the collapse remains visible rather than masked.
    promo_window_units = _as_whole_units(promo_window)
    if _is_valid_number(row.feature_demand_signal):
        feature_signal = max(float(row.feature_demand_signal), 0.0)
        collapse_candidate = promo_window_units <= DEMAND_COLLAPSE_PROMO_UNITS_MAX
        feature_threshold = max(
            DEMAND_COLLAPSE_FEATURE_FLOOR,
            float(promo_window_units) * DEMAND_COLLAPSE_FEATURE_RATIO,
        )
        if collapse_candidate and feature_signal >= feature_threshold:
            warnings.append(
                f"{DEMAND_COLLAPSE_RISK_WARNING}: model promo-window demand is "
                f"{promo_window_units} unit(s) but feature-layer demand signal is "
                f"{feature_signal:.1f}; review demand bridge ({DEMAND_COLLAPSE_RISK_DETAIL})."
            )

    return {
        "model_run_date": str(row.model_run_date or ""),
        "promotion_start_date": str(row.promotion_start_date or ""),
        "promotion_end_date": str(row.promotion_end_date or ""),
        "days_until_promo_start": int(days_until),
        "promo_window_days": int(promo_window_days),
        "baseline_daily_units": round(float(baseline_daily), 4),
        "promo_uplift_factor": round(float(uplift), 4),
        "pre_promo_demand_units": _as_whole_units(pre_promo),
        "promo_window_demand_units": _as_whole_units(promo_window),
        "total_expected_demand_units": _as_whole_units(total_demand),
        "stock_constraint_adjustment_units": _as_whole_units(stock_constraint_adjustment),
        "stock_constraint_flag": bool(stock_constraint_flag),
        "demand_forecast_units_q50": int(q50),
        "demand_forecast_units_q70": int(q70),
        "demand_forecast_units_q85": int(q85),
        "demand_forecast_units_q95": int(q95),
        "selected_demand_quantile": str(selected_quantile),
        "selected_demand_units": int(selected_units),
        "demand_forecast_confidence": str(confidence_level),
        "demand_forecast_basis": str(basis),
        "demand_forecast_reason_code": str(reason_code),
        "demand_forecast_warning": " ".join(warnings).strip(),
    }


def build_demand_forecast_contract_frame(
    *,
    model_run_date: str | pd.Series | None,
    promotion_start_date: pd.Series,
    promotion_end_date: pd.Series,
    baseline_daily_units: pd.Series,
    promo_uplift_factor: pd.Series | float = DEFAULT_PROMO_UPLIFT_FACTOR,
    promo_window_days: pd.Series | None = None,
    days_until_promo_start: pd.Series | None = None,
    pre_promo_demand_units_input: pd.Series | None = None,
    pre_promo_modifier: pd.Series | float = 1.0,
    model_promo_window_units: pd.Series | None = None,
    model_prediction_valid: pd.Series | None = None,
    confidence_fraction: pd.Series | float = 0.5,
    sparse_or_weak_evidence: pd.Series | None = None,
    soh_zero_in_comparable_promo: pd.Series | None = None,
    negative_soh_detected: pd.Series | None = None,
    high_stockout_cost: pd.Series | None = None,
    high_basket_importance: pd.Series | None = None,
    high_capital_drag: pd.Series | None = None,
    selected_demand_units_override: pd.Series | None = None,
    feature_demand_signal: pd.Series | None = None,
) -> pd.DataFrame:
    """Vectorised builder that produces the governed demand-forecast frame."""
    index = promotion_start_date.index

    def _series(value: Any, default: Any, dtype: str | None = None) -> pd.Series:
        if value is None:
            return pd.Series([default] * len(index), index=index, dtype=dtype)
        if isinstance(value, pd.Series):
            return value
        return pd.Series([value] * len(index), index=index, dtype=dtype)

    if isinstance(model_run_date, pd.Series):
        model_run_series = model_run_date.astype(str)
    else:
        model_run_series = pd.Series([str(model_run_date or "")] * len(index), index=index, dtype="object")

    baseline_series = pd.to_numeric(baseline_daily_units, errors="coerce").fillna(0.0)
    uplift_series = pd.to_numeric(_series(promo_uplift_factor, DEFAULT_PROMO_UPLIFT_FACTOR), errors="coerce").fillna(
        DEFAULT_PROMO_UPLIFT_FACTOR
    )
    window_series = _series(promo_window_days, None)
    days_series = _series(days_until_promo_start, None)
    pre_promo_input_series = _series(pre_promo_demand_units_input, None)
    pre_promo_modifier_series = pd.to_numeric(_series(pre_promo_modifier, 1.0), errors="coerce").fillna(1.0)
    model_units_series = _series(model_promo_window_units, None)
    model_valid_series = _series(model_prediction_valid, True)
    confidence_series = pd.to_numeric(_series(confidence_fraction, 0.5), errors="coerce").fillna(0.5)
    sparse_series = _series(sparse_or_weak_evidence, False)
    soh_zero_series = _series(soh_zero_in_comparable_promo, False)
    negative_soh_series = _series(negative_soh_detected, False)
    stockout_cost_series = _series(high_stockout_cost, False)
    basket_series = _series(high_basket_importance, False)
    capital_drag_series = _series(high_capital_drag, False)
    override_series = _series(selected_demand_units_override, None)
    feature_signal_series = _series(feature_demand_signal, None)

    def _opt_float(value: Any) -> float | None:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        if pd.isna(value):
            return None
        return float(value)

    def _opt_int(value: Any) -> int | None:
        opt = _opt_float(value)
        return None if opt is None else int(round(opt))

    records: list[dict[str, Any]] = []
    for position in range(len(index)):
        input_row = DemandForecastInputRow(
            model_run_date=model_run_series.iloc[position],
            promotion_start_date=str(promotion_start_date.iloc[position]),
            promotion_end_date=str(promotion_end_date.iloc[position]),
            baseline_daily_units=float(baseline_series.iloc[position]),
            promo_uplift_factor=float(uplift_series.iloc[position]),
            promo_window_days=_opt_int(window_series.iloc[position]),
            days_until_promo_start=_opt_int(days_series.iloc[position]),
            pre_promo_demand_units_input=_opt_float(pre_promo_input_series.iloc[position]),
            pre_promo_modifier=float(pre_promo_modifier_series.iloc[position]),
            model_promo_window_units=_opt_float(model_units_series.iloc[position]),
            model_prediction_valid=bool(model_valid_series.iloc[position]),
            confidence_fraction=float(confidence_series.iloc[position]),
            sparse_or_weak_evidence=bool(sparse_series.iloc[position]),
            soh_zero_in_comparable_promo=bool(soh_zero_series.iloc[position]),
            negative_soh_detected=bool(negative_soh_series.iloc[position]),
            high_stockout_cost=bool(stockout_cost_series.iloc[position]),
            high_basket_importance=bool(basket_series.iloc[position]),
            high_capital_drag=bool(capital_drag_series.iloc[position]),
            selected_demand_units_override=_opt_float(override_series.iloc[position]),
            feature_demand_signal=_opt_float(feature_signal_series.iloc[position]),
        )
        records.append(compute_demand_forecast_row(input_row))

    frame = pd.DataFrame(records, index=index)
    return frame.loc[:, list(DEMAND_FORECAST_CONTRACT_COLUMN_ORDER)]


def sync_demand_forecast_aliases(frame: pd.DataFrame) -> pd.DataFrame:
    """Populate deprecated alias columns from canonical demand-forecast fields."""
    out = frame.copy()
    for alias, canonical in DEMAND_FORECAST_ALIAS_COLUMNS.items():
        if canonical in out.columns:
            out[alias] = out[canonical]
    return out


@dataclass(frozen=True)
class DemandForecastValidationSummary:
    row_count: int
    rows_with_positive_promo_demand: int
    rows_routed_to_review: int
    rows_stock_constrained: int
    rows_inventory_contaminated: int
    rows_failing_total_demand_identity: int
    rows_failing_quantile_monotonicity: int
    rows_with_negative_units: int
    rows_with_selected_mismatch: int
    rows_with_missing_reason_code: int
    rows_with_invalid_confidence: int
    rows_with_demand_collapse_risk: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "row_count": self.row_count,
            "rows_with_positive_promo_demand": self.rows_with_positive_promo_demand,
            "rows_routed_to_review": self.rows_routed_to_review,
            "rows_stock_constrained": self.rows_stock_constrained,
            "rows_inventory_contaminated": self.rows_inventory_contaminated,
            "rows_failing_total_demand_identity": self.rows_failing_total_demand_identity,
            "rows_failing_quantile_monotonicity": self.rows_failing_quantile_monotonicity,
            "rows_with_negative_units": self.rows_with_negative_units,
            "rows_with_selected_mismatch": self.rows_with_selected_mismatch,
            "rows_with_missing_reason_code": self.rows_with_missing_reason_code,
            "rows_with_invalid_confidence": self.rows_with_invalid_confidence,
            "rows_with_demand_collapse_risk": self.rows_with_demand_collapse_risk,
        }


def validate_demand_forecast_contract_frame(
    frame: pd.DataFrame,
) -> tuple[DemandForecastValidationSummary, pd.DataFrame]:
    """Validate demand-forecast invariants and return issue rows."""
    working = frame.copy()
    numeric_columns = (
        "pre_promo_demand_units",
        "promo_window_demand_units",
        "total_expected_demand_units",
        "demand_forecast_units_q50",
        "demand_forecast_units_q70",
        "demand_forecast_units_q85",
        "demand_forecast_units_q95",
        "selected_demand_units",
    )
    for column in numeric_columns:
        if column not in working.columns:
            working[column] = np.nan
        working[column] = pd.to_numeric(working[column], errors="coerce")

    pre_promo = working["pre_promo_demand_units"]
    promo_window = working["promo_window_demand_units"]
    total_demand = working["total_expected_demand_units"]
    q50 = working["demand_forecast_units_q50"]
    q70 = working["demand_forecast_units_q70"]
    q85 = working["demand_forecast_units_q85"]
    q95 = working["demand_forecast_units_q95"]
    selected_units = working["selected_demand_units"]
    selected_quantile = working.get(
        "selected_demand_quantile", pd.Series("", index=working.index)
    ).fillna("").astype(str)
    confidence = working.get(
        "demand_forecast_confidence", pd.Series("", index=working.index)
    ).fillna("").astype(str)
    reason_code = working.get(
        "demand_forecast_reason_code", pd.Series("", index=working.index)
    ).fillna("").astype(str)
    basis = working.get("demand_forecast_basis", pd.Series("", index=working.index)).fillna("").astype(str)

    total_identity_fail = ~total_demand.round(0).eq((pre_promo + promo_window).round(0))
    monotonic_fail = ~(q50.le(q70) & q70.le(q85) & q85.le(q95))
    negative_units = (
        pre_promo.lt(0.0)
        | promo_window.lt(0.0)
        | total_demand.lt(0.0)
        | q50.lt(0.0)
        | selected_units.lt(0.0)
    )

    quantile_lookup = {
        QUANTILE_Q50: q50,
        QUANTILE_Q70: q70,
        QUANTILE_Q85: q85,
        QUANTILE_Q95: q95,
    }
    expected_selected = pd.Series(np.nan, index=working.index, dtype="float64")
    for quantile_key, quantile_series in quantile_lookup.items():
        expected_selected = expected_selected.where(
            ~selected_quantile.eq(quantile_key), quantile_series
        )
    selected_mismatch = (
        ~selected_quantile.eq(QUANTILE_OVERRIDE)
        & expected_selected.notna()
        & ~selected_units.round(0).eq(expected_selected.round(0))
    )

    missing_reason = reason_code.str.strip().eq("")
    invalid_confidence = ~confidence.str.strip().str.upper().isin(DEMAND_CONFIDENCE_LEVELS)
    warning_text = working.get(
        "demand_forecast_warning", pd.Series("", index=working.index)
    ).fillna("").astype(str)
    demand_collapse_risk = warning_text.str.contains(DEMAND_COLLAPSE_RISK_WARNING, regex=False)
    routed_to_review = basis.eq(BASIS_REVIEW)
    stock_constrained = basis.eq(BASIS_STOCK_CONSTRAINED_HISTORY)
    inventory_contaminated = basis.eq(BASIS_INVENTORY_INTEGRITY_CONTAMINATED)

    issue_rows: list[dict[str, Any]] = []

    def _append_issues(mask: pd.Series, issue_type: str) -> None:
        for row_index in working.index[mask.fillna(False)]:
            issue_rows.append(
                {
                    "issue_type": issue_type,
                    "row_index": int(row_index) if isinstance(row_index, (int, np.integer)) else str(row_index),
                    "sku_number": str(working.at[row_index, "sku_number"]) if "sku_number" in working.columns else "",
                }
            )

    _append_issues(total_identity_fail, "total_demand_identity_fail")
    _append_issues(monotonic_fail, "quantile_monotonicity_fail")
    _append_issues(negative_units, "negative_demand_units")
    _append_issues(selected_mismatch, "selected_quantile_mismatch")
    _append_issues(missing_reason, "missing_reason_code")
    _append_issues(invalid_confidence, "invalid_confidence_level")
    # Diagnostic-only: surfaced as a soft issue/count, not a hard invariant.
    _append_issues(demand_collapse_risk, "demand_collapse_risk")

    summary = DemandForecastValidationSummary(
        row_count=int(len(working.index)),
        rows_with_positive_promo_demand=int(promo_window.gt(0.0).sum()),
        rows_routed_to_review=int(routed_to_review.sum()),
        rows_stock_constrained=int(stock_constrained.sum()),
        rows_inventory_contaminated=int(inventory_contaminated.sum()),
        rows_failing_total_demand_identity=int(total_identity_fail.sum()),
        rows_failing_quantile_monotonicity=int(monotonic_fail.sum()),
        rows_with_negative_units=int(negative_units.sum()),
        rows_with_selected_mismatch=int(selected_mismatch.sum()),
        rows_with_missing_reason_code=int(missing_reason.sum()),
        rows_with_invalid_confidence=int(invalid_confidence.sum()),
        rows_with_demand_collapse_risk=int(demand_collapse_risk.sum()),
    )
    issue_frame = pd.DataFrame(issue_rows)
    return summary, issue_frame


def log_demand_forecast_validation(
    summary: DemandForecastValidationSummary,
    *,
    step_number: int = DEMAND_FORECAST_CONTRACT_STEP_NUMBER,
    started_at: float | None = None,
) -> None:
    elapsed = 0.0 if started_at is None else max(time.perf_counter() - started_at, 0.0)
    issue_count = (
        summary.rows_failing_total_demand_identity
        + summary.rows_failing_quantile_monotonicity
        + summary.rows_with_negative_units
        + summary.rows_with_selected_mismatch
        + summary.rows_with_missing_reason_code
        + summary.rows_with_invalid_confidence
    )
    logger.info(
        "STEP %s: Validate demand forecast contract ... ✅ DONE (%.2f s) | rows=%s issues=%s",
        step_number,
        elapsed,
        summary.row_count,
        issue_count,
    )


def build_demand_forecast_validation_summary_frame(
    summary: DemandForecastValidationSummary,
) -> pd.DataFrame:
    return pd.DataFrame([summary.to_dict()])
