from __future__ import annotations

"""Phase 5H — promo stock outcome optimisation and supplier lead-time truth."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_demand_backtest import (
    DEFAULT_HISTORICAL_SOURCE,
    ORDER_COLUMN_CANDIDATES,
    UNIT_COST_CANDIDATES,
    _first_numeric,
    compute_wape,
    load_historical_promo_backtest_source,
)
from models.promotions.promo_demand_bias_repair import (
    apply_underforecast_bias_adjustments,
    load_bias_repair_artifacts,
    load_repaired_calibrated_frame,
)
from models.promotions.promo_demand_calibration import (
    DEFAULT_BIAS_MAX_PCT,
    DEFAULT_BIAS_MIN_PCT,
)

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5h01_stock_outcome_optimisation")
DAILY_SUPPLIER_NUMBER = 99999
DEFAULT_LONG_LEAD_DAYS = 21
DEFAULT_DAYS_COVER_CAP = 30.0
DEFAULT_UNIT_COST_PROXY = 4.82
DEFAULT_GP_PROXY = 4.82
LONG_LEAD_RISK_MULTIPLIER = 1.15
STRONG_EVIDENCE_RISK_MULTIPLIER = 1.10

SUPPLIER_COLUMN_CANDIDATES: tuple[str, ...] = (
    "supplier_number",
    "inferred_supplier_number",
)

SOH_COLUMN_CANDIDATES: tuple[str, ...] = (
    "promo_start_soh",
    "current_soh",
    "current_soh_units",
)

INBOUND_COLUMN_CANDIDATES: tuple[str, ...] = (
    "reliable_inbound_units_before_or_during_promo",
    "confirmed_inbound_units_before_promo_start",
    "on_order_at_advice_time",
    "on_order_units",
    "qty_on_order",
)

STOCK_OUTCOME_LABELS = frozenset({
    "MISSED_DEMAND_RISK",
    "CLEAN_EXIT",
    "CONTROLLED_RESIDUAL",
    "OVERSTOCKED",
    "UNOBSERVABLE_DEMAND",
    "SUPPLIER_CONSTRAINED",
})


def _nan_safe_float(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(out):
        return default
    return out


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _first_col(frame: pd.DataFrame, names: tuple[str, ...], default: float = 0.0) -> pd.Series:
    return _first_numeric(frame, names) if any(n in frame.columns for n in names) else pd.Series(default, index=frame.index)


def _safe_div(num: float, den: float) -> float:
    if den == 0.0:
        return 0.0
    return float(num / den)


def _baseline_daily(frame: pd.DataFrame) -> pd.Series:
    baseline_period = _numeric(frame, "baseline_expected_units_total_promo")
    promo_days = _numeric(frame, "promo_days", 7.0).replace(0, 7.0)
    return (baseline_period / promo_days).clip(lower=0.0)


def assign_supplier_lead_time(frame: pd.DataFrame) -> pd.DataFrame:
    """Map supplier number to lead-time and replenishment class."""
    out = frame.copy()
    supplier = _first_col(out, SUPPLIER_COLUMN_CANDIDATES, default=np.nan)
    supplier = supplier.fillna(0).round(0).astype(int)
    out["supplier_number"] = supplier

    is_daily = supplier.eq(DAILY_SUPPLIER_NUMBER)
    explicit_lead = _numeric(out, "supplier_lead_time_days")
    has_explicit = explicit_lead.gt(0) & (~is_daily)

    out["supplier_lead_time_days"] = np.where(
        is_daily,
        1,
        np.where(has_explicit, explicit_lead, DEFAULT_LONG_LEAD_DAYS),
    ).astype(float)
    out["supplier_replenishment_class"] = np.where(
        is_daily,
        "DAILY_REPLENISHMENT",
        "LONG_LEAD_TIME",
    )
    out["supplier_reorder_flexibility"] = np.where(is_daily, "HIGH", "LOW")
    out["supplier_stock_risk_multiplier"] = np.where(
        is_daily,
        0.85,
        LONG_LEAD_RISK_MULTIPLIER,
    ).astype(float)
    return out


def _expected_low_volume_probe_units(frame: pd.DataFrame, forecast: pd.Series) -> pd.Series:
    baseline_period = _numeric(frame, "baseline_expected_units_total_promo")
    probe = np.minimum(forecast, np.maximum(2.0, baseline_period * 0.25))
    return pd.Series(probe, index=frame.index).clip(lower=0.0)


def estimate_promo_start_soh(frame: pd.DataFrame) -> pd.Series:
    """Estimate promo-start stock on hand for backtest or live rows."""
    if "promo_start_soh" in frame.columns:
        explicit = _numeric(frame, "promo_start_soh")
        if explicit.notna().any():
            return explicit.clip(lower=0.0).round(3)
    explicit = _first_col(frame, SOH_COLUMN_CANDIDATES)
    if explicit.gt(0).any():
        return explicit.clip(lower=0.0).round(3)

    pl_alloc = _numeric(frame, "pl_allocation_qty")
    actual = _numeric(frame, "actual_units_sold_promo")
    stockout = _numeric(frame, "stockout_suspected_flag").astype(int).eq(1)
    stock_basis = _first_col(frame, ("stock_basis_units", "total_stock_available", "store_adjusted_qty", "pl_allocation_qty"))

    soh = pl_alloc.copy()
    soh = np.where(stockout & actual.gt(0), np.maximum(pl_alloc, actual * 0.98), soh)
    soh = np.where((pl_alloc <= 0) & actual.gt(0), np.maximum(actual, stock_basis), soh)
    soh = np.where((pl_alloc <= 0) & actual.eq(0), 0.0, soh)
    return pd.Series(soh, index=frame.index).clip(lower=0.0).round(3)


def classify_stock_outcome_row(
    *,
    promo_start_soh: float,
    actual_units: float,
    end_soh: float,
    end_days_cover: float,
    stockout_flag: bool,
    supplier_class: str,
    buyer_blocked: bool = False,
) -> tuple[str, str, str]:
    """Classify one row's stock outcome and success reason."""
    if buyer_blocked:
        return "SUPPLIER_CONSTRAINED", "NO", "buyer_or_supplier_blocked"
    if promo_start_soh <= 0:
        return "UNOBSERVABLE_DEMAND", "NO", "zero_start_soh"
    if promo_start_soh == 1 and actual_units == 1:
        return "UNOBSERVABLE_DEMAND", "NO", "start_soh_one_sold_one_censored"
    if stockout_flag or (actual_units >= max(promo_start_soh * 0.95, 1.0) and actual_units > 0):
        return "MISSED_DEMAND_RISK", "NO", "stockout_or_sell_through"
    if end_days_cover > DEFAULT_DAYS_COVER_CAP:
        return "OVERSTOCKED", "NO", "end_days_cover_above_cap"
    if 0 <= end_soh <= 2:
        return "CLEAN_EXIT", "YES", "end_soh_within_clean_exit_band"
    if end_soh > 2 and end_days_cover <= DEFAULT_DAYS_COVER_CAP:
        return "CONTROLLED_RESIDUAL", "YES", "residual_within_days_cover_cap"
    if supplier_class == "LONG_LEAD_TIME" and end_soh < 2 and actual_units > promo_start_soh:
        return "MISSED_DEMAND_RISK", "NO", "long_lead_underprotected"
    return "CONTROLLED_RESIDUAL", "YES", "default_controlled"


def compute_target_end_soh_units(
    frame: pd.DataFrame,
    *,
    baseline_daily: pd.Series | None = None,
) -> pd.Series:
    """Supplier-aware end-of-promo stock target."""
    daily = baseline_daily if baseline_daily is not None else _baseline_daily(frame)
    thirty_day_cover = (daily * DEFAULT_DAYS_COVER_CAP).clip(lower=0.0)
    lead_cover = (daily * _numeric(frame, "supplier_lead_time_days", DEFAULT_LONG_LEAD_DAYS)).clip(lower=0.0)
    risk = _numeric(frame, "supplier_stock_risk_multiplier", 1.0)

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"
    quality = frame.get(quality_col, pd.Series("UNSAFE", index=frame.index)).astype(str)
    strong = quality.isin(["HIGH", "MEDIUM"])
    risk = risk.where(~strong, risk * STRONG_EVIDENCE_RISK_MULTIPLIER)

    is_daily = frame.get("supplier_replenishment_class", pd.Series("", index=frame.index)).astype(str).eq("DAILY_REPLENISHMENT")
    long_lead_target = np.maximum(2.0, lead_cover * risk)
    long_lead_target = np.where(strong, long_lead_target, np.minimum(long_lead_target, np.maximum(2.0, thirty_day_cover * 0.15)))
    target = np.where(is_daily, np.minimum(2.0, thirty_day_cover), long_lead_target)
    target = np.minimum(target, thirty_day_cover)
    return pd.Series(target, index=frame.index).clip(lower=0.0).round(3)


def compute_stock_outcome_order_target(
    frame: pd.DataFrame,
    *,
    forecast_col: str = "forecast_demand_units",
    capital_cap: float | None = None,
) -> pd.DataFrame:
    """Compute commercially correct stock-outcome order target."""
    out = assign_supplier_lead_time(frame)
    forecast = _numeric(out, forecast_col)
    out["forecast_demand_units"] = forecast.round(3)

    out["promo_start_soh"] = estimate_promo_start_soh(out)
    probe = _expected_low_volume_probe_units(out, forecast)
    out["min_start_soh_rule"] = 2.0
    out["target_promo_start_soh"] = np.maximum(out["min_start_soh_rule"], probe).round(3)
    out["promo_start_soh_gap"] = (out["target_promo_start_soh"] - out["promo_start_soh"]).clip(lower=0.0).round(3)

    baseline_daily = _baseline_daily(out)
    out["target_end_soh_units"] = compute_target_end_soh_units(out, baseline_daily=baseline_daily)
    inbound = _first_col(out, INBOUND_COLUMN_CANDIDATES).clip(lower=0.0)

    raw_target = (
        out["promo_start_soh_gap"]
        + forecast
        + out["target_end_soh_units"]
        - out["promo_start_soh"]
        - inbound
    ).clip(lower=0.0)

    unit_cost = _first_col(out, UNIT_COST_CANDIDATES, default=DEFAULT_UNIT_COST_PROXY).clip(lower=0.01)
    if capital_cap is not None and capital_cap > 0:
        max_units = capital_cap / unit_cost
        raw_target = np.minimum(raw_target, max_units)

    days_cap_units = (baseline_daily * DEFAULT_DAYS_COVER_CAP).clip(lower=0.0)
    max_total_order = forecast + out["promo_start_soh_gap"] + np.minimum(out["target_end_soh_units"], days_cap_units)
    raw_target = np.minimum(raw_target, max_total_order)

    end_cap_units = (out["promo_start_soh"] + raw_target + inbound - forecast).clip(lower=0.0)
    over_cap = end_cap_units.gt(days_cap_units) & days_cap_units.gt(0)
    raw_target = np.where(
        over_cap,
        np.maximum(0.0, forecast + out["promo_start_soh_gap"] + days_cap_units - out["promo_start_soh"] - inbound),
        raw_target,
    )

    existing_order = _first_col(out, ("target_order_units_stock_outcome", "recommended_order_units", *ORDER_COLUMN_CANDIDATES))
    out["target_order_units_stock_outcome"] = pd.Series(raw_target, index=out.index).round(0).astype(float)
    out["order_units_stock_outcome_adjustment"] = (
        out["target_order_units_stock_outcome"] - existing_order
    ).round(3)

    out["stock_outcome_order_reason"] = np.select(
        [
            out["promo_start_soh_gap"].gt(0),
            out.get("supplier_replenishment_class", pd.Series("", index=out.index)).astype(str).eq("LONG_LEAD_TIME"),
            out.get("supplier_replenishment_class", pd.Series("", index=out.index)).astype(str).eq("DAILY_REPLENISHMENT"),
        ],
        [
            "start_soh_below_observation_minimum",
            "long_lead_supplier_protection",
            "daily_supplier_conservative_end_stock",
        ],
        default="stock_outcome_balanced_order",
    )
    return out


def enrich_stock_outcome_fields(frame: pd.DataFrame, *, order_col: str = "target_order_units_stock_outcome") -> pd.DataFrame:
    """Add end-of-promo stock outcome labels and success flags."""
    out = compute_stock_outcome_order_target(frame) if "target_order_units_stock_outcome" not in frame.columns else assign_supplier_lead_time(frame.copy())
    if order_col not in out.columns:
        out = compute_stock_outcome_order_target(out, forecast_col="forecast_demand_units")

    actual = _numeric(out, "actual_units_sold_promo")
    order = _numeric(out, order_col)
    start_soh = _numeric(out, "promo_start_soh")
    inbound = _first_col(out, INBOUND_COLUMN_CANDIDATES)
    baseline_daily = _baseline_daily(out).replace(0, np.nan)

    simulated_end = (start_soh + order + inbound - actual).clip(lower=0.0).round(3)
    out["promo_end_soh"] = simulated_end
    out["promo_end_days_cover"] = (simulated_end / baseline_daily).replace([np.inf, -np.inf], np.nan).fillna(0.0).round(3)

    missed = (actual - start_soh - order - inbound).clip(lower=0.0).round(3)
    leftover = simulated_end.copy()
    out["simulated_missed_sales_units"] = missed
    out["simulated_leftover_units"] = leftover

    labels: list[str] = []
    success_flags: list[str] = []
    reasons: list[str] = []
    stockout = _numeric(out, "stockout_suspected_flag").astype(int).eq(1)
    supplier_class = out.get("supplier_replenishment_class", pd.Series("LONG_LEAD_TIME", index=out.index)).astype(str)
    for idx in out.index:
        label, success, reason = classify_stock_outcome_row(
            promo_start_soh=float(start_soh.loc[idx]),
            actual_units=float(actual.loc[idx]),
            end_soh=float(simulated_end.loc[idx]),
            end_days_cover=float(out["promo_end_days_cover"].loc[idx]),
            stockout_flag=bool(stockout.loc[idx]),
            supplier_class=str(supplier_class.loc[idx]),
        )
        labels.append(label)
        success_flags.append(success)
        reasons.append(reason)

    out["stock_outcome_label"] = labels
    out["end_stock_success_flag"] = success_flags
    out["end_stock_success_reason"] = reasons
    return out.fillna(0.0)


def _forecast_col(frame: pd.DataFrame, variant: str) -> str:
    if variant == "bias_adjusted":
        if "bias_adjusted_expected_units_total_promo" in frame.columns:
            return "bias_adjusted_expected_units_total_promo"
    if variant == "baseline":
        return "baseline_expected_units_total_promo"
    if variant == "stock_outcome":
        return "forecast_demand_units"
    if "model_expected_units_total_promo_calibrated" in frame.columns:
        return "model_expected_units_total_promo_calibrated"
    return "model_expected_units_total_promo"


def build_stock_outcome_backtest_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Simulate stock outcomes for multiple order logic variants."""
    working = frame.copy()
    if "bias_adjusted_expected_units_total_promo" not in working.columns:
        factors, _, rec = load_bias_repair_artifacts()
        if not factors.empty:
            working = apply_underforecast_bias_adjustments(working, factors, gate_recommendation=rec)

    variants = {
        "current_model": _forecast_col(working, "calibrated"),
        "bias_adjusted": "bias_adjusted_expected_units_total_promo",
        "baseline": "baseline_expected_units_total_promo",
    }
    rows: list[pd.DataFrame] = []
    for variant_name, col in variants.items():
        if col not in working.columns:
            continue
        chunk = working.copy()
        chunk["forecast_demand_units"] = _numeric(chunk, col)
        chunk["logic_variant"] = variant_name
        if variant_name == "current_model":
            order = _first_col(chunk, ORDER_COLUMN_CANDIDATES)
            predicted = _numeric(chunk, "predicted_units_total_promo")
            chunk["target_order_units_stock_outcome"] = order.where(order.gt(0), predicted)
        else:
            chunk = compute_stock_outcome_order_target(chunk, forecast_col="forecast_demand_units")
        chunk = enrich_stock_outcome_fields(chunk)
        rows.append(chunk)
    stock_chunk = working.copy()
    stock_chunk["forecast_demand_units"] = _numeric(
        stock_chunk,
        _forecast_col(stock_chunk, "bias_adjusted") if "bias_adjusted_expected_units_total_promo" in stock_chunk.columns else "model_expected_units_total_promo_calibrated",
    )
    stock_chunk["logic_variant"] = "stock_outcome"
    stock_chunk = enrich_stock_outcome_fields(compute_stock_outcome_order_target(stock_chunk))
    rows.append(stock_chunk)
    if not rows:
        return working
    combined = pd.concat(rows, ignore_index=True)
    unit_cost = _first_col(combined, UNIT_COST_CANDIDATES, default=DEFAULT_UNIT_COST_PROXY).clip(lower=0.01)
    gp_unit = _numeric(combined, "promo_gm_unit", DEFAULT_GP_PROXY).clip(lower=0.01)
    gp_unit = gp_unit.where(gp_unit.gt(0), unit_cost * 0.35)
    actual = _numeric(combined, "actual_units_sold_promo")
    missed = _numeric(combined, "simulated_missed_sales_units")
    leftover = _numeric(combined, "simulated_leftover_units")
    combined["economic_value_proxy"] = (actual * gp_unit - leftover * unit_cost - missed * gp_unit).round(3)
    combined["cash_tied_up_cost_proxy"] = (leftover * unit_cost).round(3)
    combined["missed_gp_proxy"] = (missed * gp_unit).round(3)
    return combined


def _aggregate_stock_metrics(chunk: pd.DataFrame, label: str) -> dict[str, Any]:
    n = len(chunk)
    success = chunk.get("end_stock_success_flag", pd.Series("NO", index=chunk.index)).astype(str).eq("YES")
    labels = chunk.get("stock_outcome_label", pd.Series("", index=chunk.index)).astype(str)
    start_gap = _numeric(chunk, "promo_start_soh_gap")
    target_start = _numeric(chunk, "target_promo_start_soh")
    start_soh = _numeric(chunk, "promo_start_soh")
    start_compliant = start_soh.ge(2) | target_start.le(start_soh)
    return {
        "segment": label,
        "row_count": int(n),
        "start_soh_compliance_rate": float(start_compliant.mean() * 100.0) if n else 0.0,
        "end_stock_success_rate": float(success.mean() * 100.0) if n else 0.0,
        "missed_demand_risk_count": int(labels.eq("MISSED_DEMAND_RISK").sum()),
        "overstocked_count": int(labels.eq("OVERSTOCKED").sum()),
        "clean_exit_count": int(labels.eq("CLEAN_EXIT").sum()),
        "controlled_residual_count": int(labels.eq("CONTROLLED_RESIDUAL").sum()),
        "unobservable_demand_count": int(labels.eq("UNOBSERVABLE_DEMAND").sum()),
        "cash_tied_up_units": float(_numeric(chunk, "simulated_leftover_units").sum()),
        "cash_tied_up_cost_proxy": float(_numeric(chunk, "cash_tied_up_cost_proxy").sum()),
        "days_cover_p95": float(_numeric(chunk, "promo_end_days_cover").quantile(0.95)) if n else 0.0,
        "supplier_99999_success_rate": float(
            success[chunk.get("supplier_number", pd.Series(0, index=chunk.index)).astype(int).eq(DAILY_SUPPLIER_NUMBER)].mean() * 100.0
        ) if n else 0.0,
        "long_lead_supplier_success_rate": float(
            success[chunk.get("supplier_replenishment_class", pd.Series("", index=chunk.index)).astype(str).eq("LONG_LEAD_TIME")].mean() * 100.0
        ) if n else 0.0,
        "estimated_missed_sales_units": float(_numeric(chunk, "simulated_missed_sales_units").sum()),
        "estimated_leftover_units": float(_numeric(chunk, "simulated_leftover_units").sum()),
        "economic_value_proxy": float(_numeric(chunk, "economic_value_proxy").sum()),
    }


def build_stock_outcome_summary(backtest_df: pd.DataFrame) -> pd.DataFrame:
    """Summarise stock outcome metrics by segment."""
    stock_only = backtest_df[backtest_df.get("logic_variant", pd.Series("", index=backtest_df.index)).eq("stock_outcome")].copy()
    if stock_only.empty:
        stock_only = backtest_df.copy()
    rows = [_aggregate_stock_metrics(stock_only, "total")]
    specs = [
        ("supplier_replenishment_class", "supplier_replenishment_class"),
        ("department", "department"),
        ("category", "category"),
        ("promotion_type", "promo_type"),
        ("demand_band", "_actual_demand_band"),
        ("evidence_quality", "promo_demand_source_quality_repaired"),
        ("release_ready", "promo_demand_release_ready_flag_repaired"),
    ]
    for prefix, col in specs:
        if col not in stock_only.columns:
            alt = col.replace("_repaired", "")
            if alt in stock_only.columns:
                col = alt
            else:
                continue
        for value, chunk in stock_only.groupby(col, dropna=False):
            rows.append(_aggregate_stock_metrics(chunk, f"{prefix}={value}"))
    return pd.DataFrame(rows)


def build_stock_outcome_backtest_summary(backtest_df: pd.DataFrame) -> pd.DataFrame:
    """Compare order logic variants on stock outcome metrics."""
    rows: list[dict[str, Any]] = []
    for variant, chunk in backtest_df.groupby("logic_variant", dropna=False):
        labels = chunk.get("stock_outcome_label", pd.Series("", index=chunk.index)).astype(str)
        success = chunk.get("end_stock_success_flag", pd.Series("NO", index=chunk.index)).astype(str).eq("YES")
        actual = _numeric(chunk, "actual_units_sold_promo")
        forecast = _numeric(chunk, "forecast_demand_units")
        bias_units = float((forecast - actual).sum())
        actual_total = float(actual.sum())
        rows.append({
            "logic_variant": str(variant),
            "row_count": int(len(chunk)),
            "missed_sales_units": float(_numeric(chunk, "simulated_missed_sales_units").sum()),
            "leftover_units": float(_numeric(chunk, "simulated_leftover_units").sum()),
            "end_stock_success_rate": float(success.mean() * 100.0),
            "clean_exit_rate": float(labels.eq("CLEAN_EXIT").mean() * 100.0),
            "controlled_residual_rate": float(labels.eq("CONTROLLED_RESIDUAL").mean() * 100.0),
            "overstock_rate": float(labels.eq("OVERSTOCKED").mean() * 100.0),
            "cash_tied_up_cost_proxy": float(_numeric(chunk, "cash_tied_up_cost_proxy").sum()),
            "gp_captured_proxy": float((actual * _numeric(chunk, "promo_gm_unit", DEFAULT_GP_PROXY)).sum()),
            "gp_missed_proxy": float(_numeric(chunk, "missed_gp_proxy").sum()),
            "net_value_proxy": float(_numeric(chunk, "economic_value_proxy").sum()),
            "wape": compute_wape(actual, forecast),
            "bias_pct": _safe_div(bias_units, actual_total) * 100.0 if actual_total > 0 else 0.0,
            "start_soh_compliance_rate": float(
                (_numeric(chunk, "promo_start_soh").ge(2) | _numeric(chunk, "promo_start_soh_gap").le(0)).mean() * 100.0
            ),
        })
    return pd.DataFrame(rows)


def evaluate_stock_outcome_release_gate(
    summary: pd.DataFrame,
    stock_summary: pd.DataFrame,
    scored_df: pd.DataFrame,
    *,
    bias_min_pct: float = DEFAULT_BIAS_MIN_PCT,
    bias_max_pct: float = DEFAULT_BIAS_MAX_PCT,
) -> tuple[str, str, pd.DataFrame]:
    """Release gate combining WAPE/bias with stock outcome success."""
    baseline = summary[summary["logic_variant"].eq("baseline")]
    current = summary[summary["logic_variant"].eq("current_model")]
    stock = summary[summary["logic_variant"].eq("stock_outcome")]
    if stock.empty:
        stock = summary.iloc[-1:]
    if current.empty:
        current = summary.iloc[0:1]
    if baseline.empty:
        baseline = summary.iloc[-1:]

    cur = current.iloc[0]
    base = baseline.iloc[0]
    stk = stock.iloc[0]

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in scored_df.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in scored_df.columns else "promo_demand_release_ready_flag"
    release_ready_rows = int(scored_df.get(release_col, pd.Series("NO")).eq("YES").sum())
    unsafe_rows = int(scored_df.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum())
    limited_rows = int(
        (
            scored_df.get("stock_outcome_release_ready_flag", pd.Series("NO")).eq("YES")
            & scored_df.get(quality_col, pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
        ).sum()
    ) if "stock_outcome_release_ready_flag" in scored_df.columns else 0

    total_row = stock_summary[stock_summary["segment"].eq("total")]
    total_metrics = total_row.iloc[0] if not total_row.empty else {}

    recommendation = "NO_RELEASE"
    blocker = "pending_evaluation"
    stk_wape = float(stk["wape"])
    base_wape = float(base["wape"])
    stk_bias = float(stk["bias_pct"])
    stock_success = float(stk["end_stock_success_rate"])
    current_success = float(cur["end_stock_success_rate"])
    improvement = stock_success - current_success

    if stk_wape >= base_wape:
        blocker = "stock_outcome_wape_not_better_than_baseline"
    elif float(stk["cash_tied_up_cost_proxy"]) > float(cur["cash_tied_up_cost_proxy"]) * 1.25:
        blocker = "stock_outcome_cash_tie_up_explosion"
    elif float(stk["overstock_rate"]) > float(cur["overstock_rate"]) + 5.0:
        blocker = "stock_outcome_overstock_explosion"
    elif stk_bias < bias_min_pct:
        blocker = "stock_outcome_bias_dangerously_negative"
    elif improvement < 2.0:
        blocker = "stock_outcome_success_not_materially_improved"
    elif limited_rows <= 0:
        blocker = "no_stock_outcome_release_ready_rows"
    elif float(stk["net_value_proxy"]) <= 0:
        blocker = "negative_net_value_proxy"
    elif stk_wape < base_wape and improvement >= 2.0 and bias_min_pct <= stk_bias <= bias_max_pct:
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"
    elif stk_wape < base_wape and improvement > 0:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "stock_outcome_improves_but_threshold_not_met"
    else:
        blocker = "overall_gate_not_met"

    gate = pd.DataFrame([{
        "current_model_wape": float(cur["wape"]),
        "stock_outcome_wape": stk_wape,
        "baseline_wape": base_wape,
        "current_model_bias_pct": float(cur["bias_pct"]),
        "stock_outcome_bias_pct": stk_bias,
        "current_end_stock_success_rate": current_success,
        "stock_outcome_end_stock_success_rate": stock_success,
        "stock_outcome_success_improvement_pct_points": improvement,
        "start_soh_compliance_rate": float(total_metrics.get("start_soh_compliance_rate", stk.get("start_soh_compliance_rate", 0.0))),
        "release_ready_rows": release_ready_rows,
        "limited_release_rows": limited_rows,
        "unsafe_rows": unsafe_rows,
        "economic_value_proxy": float(stk["net_value_proxy"]),
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "notes": "phase5h_blocks_full_customer_release_by_default",
    }])
    return recommendation, blocker, gate


def apply_stock_outcome_optimisation(
    scored_df: pd.DataFrame,
    *,
    gate_recommendation: str = "NO_RELEASE",
    forecast_col: str | None = None,
) -> pd.DataFrame:
    """Apply stock outcome fields to live scored rows without overwriting demand forecasts."""
    out = scored_df.copy()
    if forecast_col is None:
        bias_allowed = out.get("bias_adjusted_forecast_allowed_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")
        if bias_allowed.any() and "bias_adjusted_expected_units_total_promo" in out.columns:
            forecast = _numeric(out, "bias_adjusted_expected_units_total_promo")
        elif "model_expected_units_total_promo_calibrated" in out.columns:
            forecast = _numeric(out, "model_expected_units_total_promo_calibrated")
        else:
            forecast = _numeric(out, "model_expected_units_total_promo")
    else:
        forecast = _numeric(out, forecast_col)
    out["forecast_demand_units"] = forecast.round(3)
    enriched = enrich_stock_outcome_fields(out)

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in enriched.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in enriched.columns else "promo_demand_release_ready_flag"
    release_ready = (
        (gate_recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        & enriched.get(release_col, pd.Series("NO", index=enriched.index)).astype(str).eq("YES")
        & enriched.get(quality_col, pd.Series("UNSAFE", index=enriched.index)).astype(str).isin(["HIGH", "MEDIUM"])
        & (
            enriched.get("end_stock_success_flag", pd.Series("NO", index=enriched.index)).astype(str).eq("YES")
            | enriched.get("stock_outcome_label", pd.Series("", index=enriched.index)).isin(["CLEAN_EXIT", "CONTROLLED_RESIDUAL"])
        )
    )
    enriched["stock_outcome_release_ready_flag"] = np.where(release_ready, "YES", "NO")
    return enriched.fillna(0.0)


def load_stock_outcome_backtest_source(*, rebuild: bool = False) -> pd.DataFrame:
    """Load repaired calibrated frame enriched with historical stock/supplier fields."""
    frame = load_repaired_calibrated_frame(rebuild=rebuild)
    hist = load_historical_promo_backtest_source()
    keys = [c for c in ("store_number", "sku_number", "promotion_start_date") if c in frame.columns and c in hist.columns]
    enrich_cols = [
        c for c in (
            "pl_allocation_qty",
            "predicted_units_total_promo",
            "promo_gm_unit",
            "feature_end_of_promo_target_days_cover",
            "feature_day_one_target_stock_units",
            *SUPPLIER_COLUMN_CANDIDATES,
        )
        if c in hist.columns
    ]
    if keys and enrich_cols:
        hist_sub = hist[keys + enrich_cols].copy()
        for key in keys:
            hist_sub[key] = hist_sub[key].astype(str)
            frame[key] = frame[key].astype(str)
        frame = frame.merge(hist_sub, on=keys, how="left", suffixes=("", "_hist"))
    if "supplier_number" not in frame.columns and "inferred_supplier_number_hist" in frame.columns:
        frame["supplier_number"] = frame["inferred_supplier_number_hist"]
    elif "inferred_supplier_number" in frame.columns and "supplier_number" not in frame.columns:
        frame["supplier_number"] = frame["inferred_supplier_number"]
    return frame


def write_phase5h01_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Run Phase 5H pipeline and write diagnostics."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    source = frame if frame is not None else load_stock_outcome_backtest_source(rebuild=rebuild)
    backtest = build_stock_outcome_backtest_frame(source)
    stock_summary = build_stock_outcome_summary(backtest)
    variant_summary = build_stock_outcome_backtest_summary(backtest)

    current = variant_summary[variant_summary["logic_variant"].eq("current_model")]
    stock = variant_summary[variant_summary["logic_variant"].eq("stock_outcome")]
    cur_row = current.iloc[0] if not current.empty else variant_summary.iloc[0]
    stk_row = stock.iloc[0] if not stock.empty else variant_summary.iloc[-1]

    enriched = apply_stock_outcome_optimisation(source, gate_recommendation="NO_RELEASE")
    recommendation, blocker, gate = evaluate_stock_outcome_release_gate(variant_summary, stock_summary, enriched)
    enriched = apply_stock_outcome_optimisation(source, gate_recommendation=recommendation)
    recommendation, blocker, gate = evaluate_stock_outcome_release_gate(variant_summary, stock_summary, enriched)

    export_cols = [
        c for c in (
            "store_number", "sku_number", "promotion_start_date", "logic_variant",
            "actual_units_sold_promo", "forecast_demand_units", "predicted_units_total_promo",
            "target_order_units_stock_outcome", "promo_start_soh", "promo_end_soh",
            "simulated_missed_sales_units", "simulated_leftover_units", "promo_end_days_cover",
            "stock_outcome_label", "supplier_replenishment_class", "economic_value_proxy",
            "cash_tied_up_cost_proxy", "missed_gp_proxy",
        )
        if c in backtest.columns
    ]
    backtest[export_cols].to_csv(diagnostics_dir / "phase5h01_stock_outcome_backtest.csv", index=False)
    stock_summary.to_csv(diagnostics_dir / "phase5h01_stock_outcome_summary.csv", index=False)
    variant_summary.to_csv(diagnostics_dir / "phase5h01_stock_outcome_backtest_summary.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5h01_stock_outcome_release_gate.csv", index=False)

    total = stock_summary[stock_summary["segment"].eq("total")].iloc[0] if not stock_summary.empty else {}
    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in enriched.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in enriched.columns else "promo_demand_release_ready_flag"

    return {
        "wape": float(stk_row["wape"]),
        "bias_pct": float(stk_row["bias_pct"]),
        "start_soh_compliance_rate": float(total.get("start_soh_compliance_rate", 0.0)),
        "end_stock_success_rate": float(stk_row["end_stock_success_rate"]),
        "missed_sales_before": float(cur_row["missed_sales_units"]),
        "missed_sales_after": float(stk_row["missed_sales_units"]),
        "leftover_before": float(cur_row["leftover_units"]),
        "leftover_after": float(stk_row["leftover_units"]),
        "cash_tied_up_before": float(cur_row["cash_tied_up_cost_proxy"]),
        "cash_tied_up_after": float(stk_row["cash_tied_up_cost_proxy"]),
        "supplier_99999_success_rate": _nan_safe_float(total.get("supplier_99999_success_rate", 0.0)),
        "long_lead_supplier_success_rate": float(total.get("long_lead_supplier_success_rate", 0.0)),
        "release_ready_rows": int(enriched.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(enriched.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5h01_stock_outcome_optimisation(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
) -> dict[str, Any]:
    return write_phase5h01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def load_stock_outcome_artifacts(
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    gate_path = diagnostics_dir / "phase5h01_stock_outcome_release_gate.csv"
    summary_path = diagnostics_dir / "phase5h01_stock_outcome_backtest_summary.csv"
    if not gate_path.exists():
        return pd.DataFrame(), pd.DataFrame(), "NO_RELEASE"
    gate = pd.read_csv(gate_path)
    summary = pd.read_csv(summary_path) if summary_path.exists() else pd.DataFrame()
    recommendation = str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
    return summary, gate, recommendation
