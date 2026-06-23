from __future__ import annotations

"""Phase 5J — optimal base stock, promo uplift, and stock position learning."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_demand_backtest import compute_wape, load_historical_promo_backtest_source
from models.promotions.promo_stock_outcome_optimisation import (
    DAILY_SUPPLIER_NUMBER,
    DEFAULT_UNIT_COST_PROXY,
    _numeric,
    apply_stock_outcome_optimisation,
)
from models.promotions.promo_stock_truth_repair import (
    apply_stock_truth_repair,
    load_stock_truth_source,
)

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5j01_optimal_stock_position_learning")
OPTIMAL_DAYS_COVER = 30.0
MIN_OPEN_FOR_SALE = 2.0
UNKNOWN_LEAD_DAYS = 7
COSMETICS_LEAD_DAYS = 21
DEFAULT_LEAD_DAYS = 1

COSMETICS_KEYWORDS = frozenset({
    "cosmetic", "cosmetics", "colour", "color", "fragrance", "direct", "makeup", "skincare",
})


def _first_col(frame: pd.DataFrame, names: tuple[str, ...], default: float = 0.0) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    return pd.Series(default, index=frame.index, dtype=float)


def _safe_div(num: pd.Series | float, den: pd.Series | float) -> pd.Series | float:
    if isinstance(den, (int, float, np.floating)):
        if float(den) == 0.0:
            return 0.0
        return float(num) / float(den)
    if isinstance(num, (int, float, np.floating)):
        num = pd.Series([num], index=den.index[:1])
    with np.errstate(divide="ignore", invalid="ignore"):
        out = num / den.replace(0.0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _average_daily_units(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    promo_days = _numeric(frame, "promo_days", 7.0).replace(0, 7.0)
    baseline_period = _numeric(frame, "baseline_expected_units_total_promo")
    from_baseline = (baseline_period / promo_days).clip(lower=0.0)
    hist = _first_col(frame, ("historical_units_same_discount_avg", "feature_historical_units_same_discount_avg"))
    from_hist = (hist / promo_days).where(hist > 0, 0.0)
    avg = from_baseline.where(from_baseline.gt(0), from_hist)
    source = np.where(from_baseline.gt(0), "baseline_leakage_safe", np.where(from_hist.gt(0), "same_discount_history", "missing"))
    return avg.round(6), pd.Series(source, index=frame.index)


def _is_cosmetics(frame: pd.DataFrame) -> pd.Series:
    dept = frame.get("department", pd.Series("", index=frame.index)).astype(str).str.lower()
    cat = frame.get("category", pd.Series("", index=frame.index)).astype(str).str.lower()
    combined = dept + " " + cat
    mask = pd.Series(False, index=frame.index)
    for kw in COSMETICS_KEYWORDS:
        mask = mask | combined.str.contains(kw, na=False)
    return mask


def assign_replenishment_model(frame: pd.DataFrame) -> pd.DataFrame:
    """Department-aware replenishment lead time and reliability."""
    out = frame.copy()
    supplier = _first_col(out, ("supplier_number_resolved", "supplier_number"), default=0.0).round(0).astype(int)
    cosmetics = _is_cosmetics(out)
    known = supplier.gt(0) | out.get("supplier_number_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str).ne("UNKNOWN")

    lead = np.full(len(out), UNKNOWN_LEAD_DAYS, dtype=float)
    reliability = np.full(len(out), "UNKNOWN", dtype=object)
    risk = np.full(len(out), "UNKNOWN_REPLENISHMENT", dtype=object)
    source = np.full(len(out), "default_unknown", dtype=object)

    daily_mask = supplier.eq(DAILY_SUPPLIER_NUMBER)
    lead[daily_mask] = 1.0
    reliability[daily_mask] = "HIGH"
    risk[daily_mask] = "DAILY_REPLENISHMENT"
    source[daily_mask] = "supplier_99999_daily"

    cos_mask = cosmetics & ~daily_mask
    lead[cos_mask] = float(COSMETICS_LEAD_DAYS)
    reliability[cos_mask] = "MEDIUM"
    risk[cos_mask] = "LONG_LEAD_COSMETICS"
    source[cos_mask] = "cosmetics_direct_21d"

    other_mask = known & ~daily_mask & ~cos_mask
    lead[other_mask] = float(DEFAULT_LEAD_DAYS)
    reliability[other_mask] = "HIGH"
    risk[other_mask] = "OVERNIGHT_REPLENISHMENT"
    source[other_mask] = "non_cosmetics_overnight"

    out["replenishment_model_source"] = source
    out["replenishment_lead_time_days"] = lead
    out["replenishment_reliability"] = reliability
    out["replenishment_risk_class"] = risk
    return out


def compute_optimal_base_stock(frame: pd.DataFrame) -> pd.DataFrame:
    """Optimal base SOH = max(30-day supply, 2 open-for-sale units)."""
    out = frame.copy()
    avg, avg_source = _average_daily_units(out)
    optimal_base = np.maximum(avg * OPTIMAL_DAYS_COVER, MIN_OPEN_FOR_SALE).round(3)
    current = _first_col(
        out,
        ("current_soh", "current_soh_units", "promo_start_soh_resolved", "promo_start_soh"),
    )
    current_days = _safe_div(current, avg.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    low_volume = avg.lt(0.07)
    understock = current.lt(optimal_base * 0.75)
    optimal_band = current.between(optimal_base * 0.75, optimal_base * 1.25)
    overstock = current.gt(optimal_base * 1.25) & current.le(optimal_base * 2.0)
    severe = current.gt(optimal_base * 2.0) | current_days.gt(OPTIMAL_DAYS_COVER * 2)
    unknown = out.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str).eq("UNKNOWN")

    label = np.where(unknown, "UNKNOWN_STOCK_POSITION", np.where(severe, "SEVERELY_OVERSTOCKED", np.where(overstock, "OVERSTOCKED", np.where(understock, "UNDERSTOCKED", np.where(low_volume & optimal_band, "OPTIMAL_LOW_VOLUME", "OPTIMAL")))))

    out["average_daily_units"] = avg
    out["optimal_days_cover"] = OPTIMAL_DAYS_COVER
    out["optimal_base_soh_units"] = optimal_base
    out["minimum_open_for_sale_units"] = MIN_OPEN_FOR_SALE
    out["optimal_base_soh_rule"] = "max(average_daily_units*30,2)"
    out["current_soh"] = current.round(3)
    out["current_days_cover"] = current_days.round(3)
    out["current_stock_position_label"] = label
    out["average_daily_source"] = avg_source
    return out


def compute_pre_promo_bridge(frame: pd.DataFrame) -> pd.DataFrame:
    """Bridge demand from prediction date to promo start."""
    out = frame.copy()
    days = _numeric(out, "days_to_promo_start")
    if days.sum() == 0:
        days = _numeric(out, "days_until_promo_start")
    if days.sum() == 0:
        days = _numeric(out, "lead_days_to_promo_start")
    avg = _numeric(out, "average_daily_units")
    expected_bridge = (avg * days).round(3)
    inbound = _first_col(out, ("reliable_inbound_units_before_or_during_promo", "inbound_units_before_promo", "qty_on_order", "on_order_at_advice_time"))
    current = _numeric(out, "current_soh")
    expected_start = (current + inbound - expected_bridge).clip(lower=0.0).round(3)

    soh_quality = out.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str)
    bridge_quality = np.where(soh_quality.eq("UNKNOWN"), "UNKNOWN", np.where(avg.gt(0), "MEDIUM", "LOW"))

    out["prediction_date"] = out.get("prediction_date", pd.Series("", index=out.index)).astype(str)
    out["promotion_start_date"] = out.get("promotion_start_date", pd.Series("", index=out.index)).astype(str)
    out["days_until_promo_start"] = days.astype(int)
    out["expected_units_until_promo_start"] = expected_bridge
    out["expected_soh_at_promo_start_before_order"] = expected_start
    out["pre_promo_bridge_source"] = out.get("average_daily_source", pd.Series("baseline", index=out.index)).astype(str)
    out["pre_promo_bridge_quality"] = bridge_quality
    return out


def compute_promo_uplift(frame: pd.DataFrame) -> pd.DataFrame:
    """Separate normal promo demand from promotional uplift."""
    out = frame.copy()
    promo_days = _numeric(out, "promo_days", 7.0).replace(0, 7.0)
    avg = _numeric(out, "average_daily_units")
    expected_normal = (avg * promo_days).round(3)

    forecast = _first_col(out, ("bias_adjusted_expected_units_total_promo", "model_expected_units_total_promo_calibrated", "model_expected_units_total_promo", "forecast_demand_units"))
    uplift = (forecast - expected_normal).clip(lower=0.0).round(3)
    total = (expected_normal + uplift).round(3)
    multiplier = (_safe_div(forecast, expected_normal.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)).round(3)
    discount = _first_col(out, ("discount_percent", "_discount_band"), default=0.0)
    convexity = ((multiplier - 1.0).clip(lower=0.0) * 50.0 + discount.clip(0, 50) * 0.5).clip(0, 100).round(1)

    actual = _numeric(out, "actual_units_sold_promo")
    actual_uplift = (actual - expected_normal).clip(lower=0.0).round(3)

    quality = np.where(forecast.gt(0) & avg.gt(0), "MEDIUM", "LOW")
    out["expected_normal_units_during_promo"] = expected_normal
    out["expected_promo_uplift_units"] = uplift
    out["expected_total_promo_demand_units"] = total
    out["actual_promo_uplift_units"] = actual_uplift
    out["promo_uplift_multiplier"] = multiplier
    out["promo_convexity_score"] = convexity
    out["promo_uplift_source"] = "model_minus_baseline_normal"
    out["promo_uplift_quality"] = quality
    return out


def compute_day_one_and_exit_targets(frame: pd.DataFrame) -> pd.DataFrame:
    """Day-one promo SOH target and promo exit target."""
    out = frame.copy()
    optimal_base = _numeric(out, "optimal_base_soh_units")
    uplift = _numeric(out, "expected_promo_uplift_units")
    expected_start = _numeric(out, "expected_soh_at_promo_start_before_order")
    position = out.get("current_stock_position_label", pd.Series("UNKNOWN_STOCK_POSITION", index=out.index)).astype(str)

    raw_target = (optimal_base + uplift).round(3)
    overstocked = position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])
    target_day_one = raw_target.where(~overstocked, np.minimum(expected_start, raw_target).round(3))
    gap = (target_day_one - expected_start).clip(lower=0.0).round(3)

    target_end = optimal_base.round(3)
    out["target_day_one_promo_soh"] = target_day_one
    out["day_one_promo_soh_gap"] = gap
    out["day_one_promo_soh_quality"] = np.where(
        out.get("pre_promo_bridge_quality", pd.Series("LOW", index=out.index)).astype(str).eq("UNKNOWN"),
        "UNKNOWN",
        "MEDIUM",
    )
    out["target_day_one_reason"] = np.where(
        overstocked,
        "Overstocked SKU: cap day-one target at expected start SOH",
        "Optimal base SOH plus promo uplift",
    )
    out["target_end_promo_soh"] = target_end
    return out


def compute_optimal_stock_position_order(frame: pd.DataFrame) -> pd.DataFrame:
    """Commercially optimal order quantity toward day-one stock position."""
    out = frame.copy()
    target_day_one = _numeric(out, "target_day_one_promo_soh")
    expected_start = _numeric(out, "expected_soh_at_promo_start_before_order")
    position = out.get("current_stock_position_label", pd.Series("", index=out.index)).astype(str)
    overstocked = position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])

    raw_order = (target_day_one - expected_start).clip(lower=0.0)
    raw_order = np.where(overstocked & expected_start.gt(target_day_one), 0.0, raw_order)

    days_cap_units = (_numeric(out, "average_daily_units") * OPTIMAL_DAYS_COVER).clip(lower=MIN_OPEN_FOR_SALE)
    raw_order = np.minimum(raw_order, days_cap_units + _numeric(out, "expected_promo_uplift_units"))

    reason = np.where(
        overstocked & expected_start.gt(target_day_one),
        "Use promotion to run down excess stock toward optimal SOH",
        np.where(raw_order.gt(0), "Order to reach day-one optimal stock position", "No order required for optimal position"),
    )

    out["optimal_stock_position_order_units"] = pd.Series(raw_order, index=out.index).round(0)
    out["stock_position_order_reason"] = reason
    return out


def simulate_stock_position_outcomes(frame: pd.DataFrame, *, order_units_col: str | None = None) -> pd.DataFrame:
    """Simulate end-of-promo stock position vs optimal base."""
    out = compute_optimal_stock_position_order(
        compute_day_one_and_exit_targets(
            compute_promo_uplift(
                compute_pre_promo_bridge(
                    compute_optimal_base_stock(
                        assign_replenishment_model(frame)
                    )
                )
            )
        )
    )
    if order_units_col and order_units_col in frame.columns:
        out["optimal_stock_position_order_units"] = _numeric(frame, order_units_col).round(0)
    order = _numeric(out, "optimal_stock_position_order_units")
    expected_start = _numeric(out, "expected_soh_at_promo_start_before_order")
    promo_demand = _numeric(out, "expected_total_promo_demand_units")
    actual = _numeric(out, "actual_units_sold_promo")
    demand_used = np.where(actual.gt(0), actual, promo_demand)
    target_end = _numeric(out, "target_end_promo_soh")
    optimal_base = _numeric(out, "optimal_base_soh_units")
    avg = _numeric(out, "average_daily_units")

    simulated_end = (expected_start + order - demand_used).clip(lower=0.0).round(3)
    distance = (simulated_end - target_end).abs().round(3)
    end_days = _safe_div(simulated_end, avg.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    low_vol = avg.lt(0.07)
    success = (
        (low_vol & simulated_end.le(MIN_OPEN_FOR_SALE + 0.01))
        | ((~low_vol) & end_days.le(OPTIMAL_DAYS_COVER + 0.01))
        | (distance.le(optimal_base * 0.25))
    )
    end_label = np.where(
        simulated_end.gt(optimal_base * 1.5),
        "OVERSTOCKED",
        np.where(simulated_end.lt(optimal_base * 0.5), "UNDERSTOCKED", "NEAR_OPTIMAL"),
    )

    missed = (demand_used - expected_start - order).clip(lower=0.0).round(3)
    leftover_above = (simulated_end - target_end).clip(lower=0.0).round(3)

    out["expected_end_promo_soh_after_order"] = simulated_end
    out["simulated_end_soh"] = simulated_end
    out["distance_to_optimal_end_soh"] = distance
    out["end_stock_position_label"] = end_label
    out["promo_exit_success_flag"] = np.where(success, "YES", "NO")
    out["promo_exit_success_reason"] = np.where(
        success,
        "End SOH within optimal base tolerance",
        "End SOH outside optimal base tolerance",
    )
    out["simulated_missed_demand_units"] = missed
    out["leftover_units_above_optimal"] = leftover_above
    out["cash_tied_above_optimal"] = (leftover_above * DEFAULT_UNIT_COST_PROXY).round(3)
    return out


def build_stock_position_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate stock-position learning metrics."""
    position = frame.get("current_stock_position_label", pd.Series("", index=frame.index)).astype(str)
    success = frame.get("promo_exit_success_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    distance = _numeric(frame, "distance_to_optimal_end_soh")
    missed = _numeric(frame, "simulated_missed_demand_units")
    leftover = _numeric(frame, "leftover_units_above_optimal")
    cash = _numeric(frame, "cash_tied_above_optimal")
    actual = _numeric(frame, "actual_units_sold_promo")
    gp = _first_col(frame, ("promo_gm_unit",), default=DEFAULT_UNIT_COST_PROXY * 0.35)

    return pd.DataFrame([{
        "row_count": int(len(frame)),
        "understocked_count": int(position.eq("UNDERSTOCKED").sum()),
        "overstocked_count": int(position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]).sum()),
        "optimal_base_soh_coverage_pct": float(frame.get("optimal_base_soh_units", pd.Series(0, index=frame.index)).gt(0).mean() * 100.0),
        "average_distance_to_optimal_before": float((_numeric(frame, "current_soh") - _numeric(frame, "optimal_base_soh_units")).abs().mean()),
        "average_distance_to_optimal_after": float(distance.mean()),
        "promo_exit_success_rate": float(success.mean() * 100.0),
        "missed_demand_risk_units": float(missed.sum()),
        "leftover_units_above_optimal": float(leftover.sum()),
        "cash_tied_above_optimal": float(cash.sum()),
        "gp_captured_proxy": float((actual * gp).sum()),
        "gp_missed_proxy": float((missed * gp).sum()),
        "net_value_proxy": float((actual * gp - leftover * DEFAULT_UNIT_COST_PROXY - missed * gp).sum()),
        "expected_promo_uplift_units_total": float(_numeric(frame, "expected_promo_uplift_units").sum()),
        "expected_units_until_promo_start_total": float(_numeric(frame, "expected_units_until_promo_start").sum()),
    }])


def evaluate_optimal_stock_release_gate(
    before_summary: pd.DataFrame,
    after_summary: pd.DataFrame,
    frame: pd.DataFrame,
    *,
    baseline_wape: float = 1.083,
    model_wape: float = 0.675,
    model_bias_pct: float = -23.6,
) -> tuple[str, str, pd.DataFrame]:
    """Release gate based on distance-to-optimal stock position."""
    before = before_summary.iloc[0]
    after = after_summary.iloc[0]

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in frame.columns else "promo_demand_release_ready_flag"
    limited_rows = int(
        (
            frame.get("stock_position_release_ready_flag", pd.Series("NO")).eq("YES")
            & frame.get(quality_col, pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
        ).sum()
    ) if "stock_position_release_ready_flag" in frame.columns else 0

    dist_improve = float(before["average_distance_to_optimal_after"]) - float(after["average_distance_to_optimal_after"])
    missed_improve = float(before["missed_demand_risk_units"]) - float(after["missed_demand_risk_units"])
    cash_ratio = float(after["cash_tied_above_optimal"]) / max(float(before["cash_tied_above_optimal"]), 1.0)
    overstock_no_buy = int(
        (
            frame.get("current_stock_position_label", pd.Series("", index=frame.index)).isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])
            & _numeric(frame, "optimal_stock_position_order_units").eq(0)
        ).sum()
    )

    recommendation = "NO_RELEASE"
    blocker = "pending_evaluation"

    if model_wape >= baseline_wape:
        blocker = "model_wape_not_better_than_baseline"
    elif model_bias_pct < -15.0:
        blocker = "model_bias_dangerously_negative"
    elif dist_improve <= 0:
        blocker = "distance_to_optimal_not_improved"
    elif cash_ratio > 1.25:
        blocker = "cash_tied_above_optimal_explosion"
    elif missed_improve <= 0:
        blocker = "missed_demand_risk_not_improved"
    elif limited_rows <= 0:
        blocker = "no_stock_position_release_ready_rows"
    elif float(after["net_value_proxy"]) <= 0:
        blocker = "negative_net_value_proxy"
    elif dist_improve > 0 and missed_improve > 0 and cash_ratio <= 1.25 and -15.0 <= model_bias_pct <= 20.0:
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"
    elif dist_improve > 0:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "stock_position_improves_but_threshold_not_met"
    else:
        blocker = "overall_gate_not_met"

    gate = pd.DataFrame([{
        "baseline_wape": baseline_wape,
        "model_wape": model_wape,
        "model_bias_pct": model_bias_pct,
        "distance_to_optimal_before": float(before["average_distance_to_optimal_after"]),
        "distance_to_optimal_after": float(after["average_distance_to_optimal_after"]),
        "distance_improvement_units": dist_improve,
        "missed_demand_before": float(before["missed_demand_risk_units"]),
        "missed_demand_after": float(after["missed_demand_risk_units"]),
        "cash_tied_above_optimal_before": float(before["cash_tied_above_optimal"]),
        "cash_tied_above_optimal_after": float(after["cash_tied_above_optimal"]),
        "promo_exit_success_rate": float(after["promo_exit_success_rate"]),
        "overstock_no_buy_count": overstock_no_buy,
        "limited_release_rows": limited_rows,
        "unsafe_rows": int(frame.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "notes": "phase5j_blocks_full_customer_release_by_default",
    }])
    return recommendation, blocker, gate


def apply_optimal_stock_learning(
    scored_df: pd.DataFrame,
    *,
    gate_recommendation: str = "NO_RELEASE",
) -> pd.DataFrame:
    """Apply optimal stock position learning to scored rows."""
    out = simulate_stock_position_outcomes(scored_df)
    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in out.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in out.columns else "promo_demand_release_ready_flag"
    release_ready = (
        (gate_recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        & out.get(release_col, pd.Series("NO", index=out.index)).astype(str).eq("YES")
        & out.get(quality_col, pd.Series("UNSAFE", index=out.index)).astype(str).isin(["HIGH", "MEDIUM"])
        & out.get("promo_exit_success_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")
        & out.get("pre_promo_bridge_quality", pd.Series("LOW", index=out.index)).astype(str).ne("UNKNOWN")
    )
    out["stock_position_release_ready_flag"] = np.where(release_ready, "YES", "NO")
    return out.fillna(0.0)


def write_phase5j01_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Run Phase 5J stock position learning pipeline."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    source = frame if frame is not None else apply_stock_truth_repair(load_stock_truth_source(rebuild=rebuild))
    source = apply_stock_outcome_optimisation(source, gate_recommendation="NO_RELEASE")

    before_out = simulate_stock_position_outcomes(source, order_units_col="target_order_units_stock_outcome")
    before_summary = build_stock_position_summary(before_out)

    after_out = simulate_stock_position_outcomes(source)
    after_summary = build_stock_position_summary(after_out)

    recommendation, blocker, gate = evaluate_optimal_stock_release_gate(before_summary, after_summary, after_out)
    after_out = apply_optimal_stock_learning(source, gate_recommendation=recommendation)
    recommendation, blocker, gate = evaluate_optimal_stock_release_gate(before_summary, build_stock_position_summary(after_out), after_out)

    export_cols = [
        c for c in after_out.columns if c in {
            "store_number", "sku_number", "promotion_start_date",
            "current_soh", "optimal_base_soh_units", "expected_units_until_promo_start",
            "expected_soh_at_promo_start_before_order", "expected_normal_units_during_promo",
            "expected_promo_uplift_units", "target_day_one_promo_soh",
            "optimal_stock_position_order_units", "simulated_end_soh", "target_end_promo_soh",
            "distance_to_optimal_end_soh", "promo_exit_success_flag", "stock_position_order_reason",
            "current_stock_position_label", "replenishment_lead_time_days", "replenishment_risk_class",
        }
    ]
    after_out[export_cols].to_csv(diagnostics_dir / "phase5j01_stock_position_backtest.csv", index=False)
    pd.concat([
        before_summary.assign(stage="phase5i_stock_outcome_order"),
        after_summary.assign(stage="phase5j_optimal_stock_position"),
    ], ignore_index=True).to_csv(diagnostics_dir / "phase5j01_optimal_stock_position_summary.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5j01_release_gate.csv", index=False)

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in after_out.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in after_out.columns else "promo_demand_release_ready_flag"

    return {
        "optimal_base_soh_coverage": float(after_summary["optimal_base_soh_coverage_pct"].iloc[0]),
        "understocked_count": int(after_summary["understocked_count"].iloc[0]),
        "overstocked_count": int(after_summary["overstocked_count"].iloc[0]),
        "expected_units_until_promo_start": float(after_summary["expected_units_until_promo_start_total"].iloc[0]),
        "expected_promo_uplift_units": float(after_summary["expected_promo_uplift_units_total"].iloc[0]),
        "distance_to_optimal_before": float(before_summary["average_distance_to_optimal_after"].iloc[0]),
        "distance_to_optimal_after": float(after_summary["average_distance_to_optimal_after"].iloc[0]),
        "missed_demand_before": float(before_summary["missed_demand_risk_units"].iloc[0]),
        "missed_demand_after": float(after_summary["missed_demand_risk_units"].iloc[0]),
        "cash_tied_above_optimal_before": float(before_summary["cash_tied_above_optimal"].iloc[0]),
        "cash_tied_above_optimal_after": float(after_summary["cash_tied_above_optimal"].iloc[0]),
        "promo_exit_success_rate": float(after_summary["promo_exit_success_rate"].iloc[0]),
        "release_ready_rows": int(after_out.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(after_out.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5j01_optimal_stock_learning(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5j01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def load_optimal_stock_artifacts(diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR) -> tuple[pd.DataFrame, str]:
    gate_path = diagnostics_dir / "phase5j01_release_gate.csv"
    if not gate_path.exists():
        return pd.DataFrame(), "NO_RELEASE"
    gate = pd.read_csv(gate_path)
    return gate, str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
