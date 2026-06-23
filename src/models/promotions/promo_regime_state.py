from __future__ import annotations

"""Phase 5K — store regime state layer and brain-first promo decisioning."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_optimal_stock_learning import (
    apply_optimal_stock_learning,
    simulate_stock_position_outcomes,
)
from models.promotions.promo_stock_outcome_optimisation import (
    DEFAULT_UNIT_COST_PROXY,
    apply_stock_outcome_optimisation,
)
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5k01_regime_state_brain_decisioning")
CAPITAL_CAP_UNITS = 500.0

REGIME_FIELDS: tuple[str, ...] = (
    "store_sales_regime", "store_traffic_regime", "store_conversion_regime", "store_gp_regime",
    "store_operational_regime", "store_visibility_regime",
    "customer_loyalty_regime", "customer_price_sensitivity_regime", "customer_basket_trust_regime",
    "customer_repeat_behaviour_regime",
    "sku_demand_regime", "department_demand_regime", "recent_momentum_regime", "promo_response_regime",
    "stock_position_regime", "stock_constraint_regime", "capital_drag_regime",
    "promo_start_stock_regime", "promo_exit_stock_regime",
    "supplier_replenishment_regime", "supplier_risk_regime", "supplier_flexibility_regime",
    "promo_discount_regime", "promo_event_regime", "promo_duration_regime",
    "promo_convexity_regime", "promo_value_regime",
    "cash_efficiency_regime", "cash_tied_above_optimal_regime", "capital_at_risk_regime",
)


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _first_col(frame: pd.DataFrame, names: tuple[str, ...], default: float = 0.0) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    return pd.Series(default, index=frame.index, dtype=float)


def _clip_score(series: pd.Series) -> pd.Series:
    return series.clip(0.0, 100.0).round(1)


def build_promo_regime_state_frame(df: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Build regime/state features at promo SKU grain."""
    del config
    out = df.copy()
    avg = _numeric(out, "average_daily_units")
    promo_days = _numeric(out, "promo_days", 7.0).replace(0, 7.0)
    discount = _first_col(out, ("discount_percent",))
    convexity = _numeric(out, "promo_convexity_score")
    uplift = _numeric(out, "expected_promo_uplift_units")
    position = out.get("current_stock_position_label", pd.Series("UNKNOWN_STOCK_POSITION", index=out.index)).astype(str)
    soh_quality = out.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str)
    stockout = _numeric(out, "stockout_suspected_flag").astype(int).eq(1)
    dept = out.get("department", pd.Series("", index=out.index)).astype(str)
    hist = _first_col(out, ("historical_units_same_discount_avg", "feature_historical_units_same_discount_avg"))
    basket = _first_col(out, ("feature_basket_structure_evidence_available_flag",), default=0.0)
    sparse = _first_col(out, ("feature_sparse_demand_evidence_available_flag",), default=0.0)

    store_sales = np.where(avg.ge(avg.quantile(0.75) if avg.gt(0).any() else 1), "HIGH_TRAFFIC", np.where(avg.le(avg.quantile(0.25) if avg.gt(0).any() else 0), "LOW_TRAFFIC", "NORMAL"))
    out["store_sales_regime"] = store_sales
    out["store_traffic_regime"] = store_sales
    expected_normal = avg * promo_days
    out["store_conversion_regime"] = np.where(uplift.gt(expected_normal * 0.5), "HIGH_CONVERSION", "LOW_CONVERSION")
    out["store_gp_regime"] = np.where(_first_col(out, ("promo_gm_unit",), default=0) >= 5, "HIGH_GP_PRESSURE", "NORMAL")
    out["store_operational_regime"] = "NORMAL"
    out["store_visibility_regime"] = np.where(discount.ge(20), "SIGNAGE_UPLIFT", "NORMAL")

    out["customer_loyalty_regime"] = np.where(hist.ge(hist.quantile(0.75) if hist.gt(0).any() else 1), "LOYALTY_HIGH", "LOYALTY_LOW")
    out["customer_price_sensitivity_regime"] = np.where(discount.ge(25), "PRICE_SENSITIVE", "NORMAL")
    out["customer_basket_trust_regime"] = np.where(basket.gt(0), "BASKET_TRUST_STRONG", "BASKET_TRUST_RISK")
    out["customer_repeat_behaviour_regime"] = np.where(hist.gt(0) & sparse.eq(0), "REPEAT_VISIT_STRENGTHENING", "WEAK_REPEAT_SIGNAL")

    out["sku_demand_regime"] = np.where(avg.lt(0.07), "INTERMITTENT_LOW_VOLUME", np.where(avg.ge(avg.quantile(0.75) if avg.gt(0).any() else 1), "STABLE_BASE_DEMAND", "STABLE_BASE_DEMAND"))
    out["department_demand_regime"] = out.groupby(dept)["sku_demand_regime"].transform(lambda s: s.mode().iloc[0] if len(s.mode()) else "STABLE_BASE_DEMAND")
    out["recent_momentum_regime"] = np.where(uplift.gt(avg * promo_days * 0.25), "RISING_MOMENTUM", np.where(uplift.lt(avg), "FALLING_MOMENTUM", "STABLE"))
    out["promo_response_regime"] = np.where(convexity.ge(50), "HIGH_PROMO_CONVEXITY", np.where(convexity.le(15), "LOW_PROMO_RESPONSE", "NORMAL"))

    out["stock_position_regime"] = position.replace({"UNKNOWN_STOCK_POSITION": "UNKNOWN"})
    out["stock_constraint_regime"] = np.where(stockout | soh_quality.eq("UNSAFE"), "CENSORED_DEMAND_RISK", "NORMAL")
    cash_above = (_numeric(out, "current_soh") - _numeric(out, "optimal_base_soh_units")).clip(lower=0.0)
    out["capital_drag_regime"] = np.where(cash_above.gt(_numeric(out, "optimal_base_soh_units") * 0.5), "CAPITAL_DRAG_HIGH", "NORMAL")
    out["promo_start_stock_regime"] = np.where(soh_quality.eq("UNKNOWN"), "UNKNOWN", position)
    out["promo_exit_stock_regime"] = out.get("end_stock_position_label", pd.Series("UNKNOWN", index=out.index)).astype(str)

    repl = out.get("replenishment_risk_class", out.get("supplier_replenishment_class_repaired", pd.Series("UNKNOWN", index=out.index))).astype(str)
    out["supplier_replenishment_regime"] = repl
    out["supplier_risk_regime"] = np.where(
        out.get("supplier_number_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str).eq("UNKNOWN"),
        "UNKNOWN_SUPPLIER",
        repl,
    )
    out["supplier_flexibility_regime"] = out.get("supplier_reorder_flexibility_repaired", out.get("supplier_reorder_flexibility", pd.Series("LOW", index=out.index))).astype(str).replace({"HIGH": "HIGH_FLEXIBILITY", "LOW": "LOW_FLEXIBILITY"})

    out["promo_discount_regime"] = np.where(discount.ge(30), "DEEP_DISCOUNT", np.where(discount.ge(15), "NORMAL_DISCOUNT", "SHALLOW_DISCOUNT"))
    out["promo_event_regime"] = out.get("promo_type", pd.Series("STANDARD", index=out.index)).astype(str)
    out["promo_duration_regime"] = np.where(promo_days.le(7), "SHORT_EVENT", "FORTNIGHT_PROMO")
    out["promo_convexity_regime"] = np.where(convexity.ge(50), "HIGH_CONVEXITY", np.where(convexity.le(15), "LOW_CONVEXITY", "NORMAL"))
    out["promo_value_regime"] = np.where(uplift.gt(0), "VALUE_UPLIFT", "LOW_VALUE")

    dist = _numeric(out, "distance_to_optimal_end_soh")
    out["cash_efficiency_regime"] = np.where(dist.le(2), "CAPITAL_EFFICIENT", "CASH_TIE_UP_RISK")
    out["cash_tied_above_optimal_regime"] = np.where(cash_above.gt(0), "CASH_TIE_UP_RISK", "CAPITAL_EFFICIENT")
    out["capital_at_risk_regime"] = np.where(
        position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]),
        "CASH_RELEASE_PRIORITY",
        np.where(cash_above.gt(10), "HIGH_CAPITAL_AT_RISK", "NORMAL"),
    )

    # Numeric scores (state descriptors, not hard actions)
    out["store_regime_score"] = _clip_score(50 + (avg / max(float(avg.quantile(0.9)), 0.01)) * 25)
    out["customer_regime_score"] = _clip_score(40 + basket * 30 + np.where(hist.gt(0), 20, 0))
    out["demand_regime_score"] = _clip_score(30 + convexity * 0.5 + np.where(avg.gt(0), 20, 0))
    out["stock_regime_score"] = _clip_score(70 - dist * 5 - np.where(position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]), 25, 0))
    out["supplier_regime_score"] = _clip_score(
        np.where(out["supplier_risk_regime"].eq("UNKNOWN_SUPPLIER"), 25, 60)
        + np.where(out["supplier_flexibility_regime"].eq("HIGH_FLEXIBILITY"), 20, 0)
    )
    out["promo_regime_score"] = _clip_score(convexity + discount.clip(0, 30) * 0.5)
    out["cash_regime_score"] = _clip_score(80 - cash_above.clip(0, 50) * 0.8)

    out["overall_regime_opportunity_score"] = _clip_score(
        out["promo_regime_score"] * 0.35
        + out["demand_regime_score"] * 0.20
        + np.where(out["capital_at_risk_regime"].eq("CASH_RELEASE_PRIORITY"), 15, 0)
        + out["customer_regime_score"] * 0.15
    )
    out["overall_regime_risk_score"] = _clip_score(
        np.where(soh_quality.eq("UNKNOWN"), 25, 0)
        + np.where(out["supplier_risk_regime"].eq("UNKNOWN_SUPPLIER"), 20, 0)
        + np.where(stockout, 20, 0)
        + np.where(out["stock_constraint_regime"].eq("CENSORED_DEMAND_RISK"), 15, 0)
    )
    out["overall_regime_conviction_score"] = _clip_score(
        100 - out["overall_regime_risk_score"] * 0.5 + out.get("promo_start_soh_confidence_score", pd.Series(0, index=out.index)) * 0.3
    )

    return out.fillna(0.0)


def compute_regime_decision_targets(frame: pd.DataFrame) -> pd.DataFrame:
    """Regime-conditioned learning targets and action labels."""
    out = frame.copy()
    actual = _numeric(out, "actual_units_sold_promo")
    gp_unit = _first_col(out, ("promo_gm_unit",), default=DEFAULT_UNIT_COST_PROXY * 0.35)
    optimal = _numeric(out, "optimal_base_soh_units")
    current = _numeric(out, "current_soh")
    dist_before = (current - optimal).abs()
    dist_after = _numeric(out, "distance_to_optimal_end_soh")
    missed = _numeric(out, "simulated_missed_demand_units")
    cash_above = (_numeric(out, "leftover_units_above_optimal")).clip(lower=0.0)
    uplift = _numeric(out, "expected_promo_uplift_units")
    normal = _numeric(out, "expected_normal_units_during_promo")

    out["distance_to_optimal_improvement"] = (dist_before - dist_after).round(3)
    out["promo_uplift_capture_ratio"] = (_safe_ratio(actual - normal, uplift)).round(3)
    out["missed_demand_penalty"] = (missed * gp_unit).round(3)
    out["cash_drag_penalty"] = (cash_above * DEFAULT_UNIT_COST_PROXY).round(3)
    out["stockout_trust_penalty"] = np.where(
        out.get("stock_constraint_regime", pd.Series("", index=out.index)).astype(str).eq("CENSORED_DEMAND_RISK"),
        missed * gp_unit * 0.5,
        0.0,
    ).round(3)
    run_down = np.where(
        out.get("current_stock_position_label", pd.Series("", index=out.index)).astype(str).isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]),
        (current - optimal).clip(lower=0.0) * DEFAULT_UNIT_COST_PROXY * 0.25,
        0.0,
    )
    out["overstock_run_down_reward"] = pd.Series(run_down, index=out.index).round(3)
    uplift_reward = (uplift * gp_unit * 0.15 * (1.0 + _numeric(out, "promo_convexity_score") / 100.0)).round(3)
    out["promo_uplift_capture_reward"] = uplift_reward
    gp_captured = (actual * gp_unit).round(3)

    out["regime_adjusted_decision_value"] = (
        gp_captured + out["overstock_run_down_reward"] + uplift_reward
        - out["missed_demand_penalty"] - out["cash_drag_penalty"] - out["stockout_trust_penalty"]
    ).round(3)

    proposal = _numeric(out, "optimal_stock_position_order_units")
    opp = _numeric(out, "overall_regime_opportunity_score")
    risk = _numeric(out, "overall_regime_risk_score")
    position = out.get("current_stock_position_label", pd.Series("", index=out.index)).astype(str)

    out["regime_adjusted_action_label"] = np.select(
        [
            position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]),
            proposal.le(0) & ~position.eq("UNDERSTOCKED"),
            proposal.gt(0) & proposal.le(5),
            proposal.gt(5) & opp.ge(60) & risk.le(40),
            proposal.gt(5) & opp.ge(45),
            proposal.gt(0),
        ],
        [
            "NO_BUY_RUN_DOWN",
            "HOLD_FOR_REPLENISHMENT",
            "TOP_UP_TO_OPTIMAL",
            "AGGRESSIVE_BUY",
            "CONTROLLED_BUY",
            "CONTROLLED_BUY",
        ],
        default="HOLD_FOR_REPLENISHMENT",
    )
    return out


def _safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    with np.errstate(divide="ignore", invalid="ignore"):
        return (num / den.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def apply_brain_constraint_interpretation(
    frame: pd.DataFrame,
    *,
    gate_recommendation: str = "NO_RELEASE",
) -> pd.DataFrame:
    """Separate brain proposal, constraint layer, and interpretation."""
    out = compute_regime_decision_targets(build_promo_regime_state_frame(frame))
    proposal = _numeric(out, "optimal_stock_position_order_units").round(0)
    out["brain_order_units_proposal"] = proposal
    out["brain_action_label"] = out["regime_adjusted_action_label"]

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in out.columns else "promo_demand_source_quality"
    unsafe = out.get(quality_col, pd.Series("UNSAFE", index=out.index)).astype(str).eq("UNSAFE")
    unknown_soh = out.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str).eq("UNKNOWN")
    capital_breach = proposal.gt(CAPITAL_CAP_UNITS)
    gate_blocked = gate_recommendation == "NO_RELEASE"

    block = unsafe | (unknown_soh & proposal.gt(10)) | capital_breach | (gate_blocked & proposal.gt(20))
    block_reason = np.select(
        [unsafe, unknown_soh & proposal.gt(10), capital_breach, gate_blocked & proposal.gt(20)],
        ["UNSAFE_row_blocked", "unknown_stock_truth_blocks_large_buy", "capital_cap_breached", "release_gate_blocked"],
        default="",
    )

    governed_units = proposal.where(~block, 0.0)
    overstock = out.get("current_stock_position_label", pd.Series("", index=out.index)).astype(str).isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])
    governed_units = np.where(overstock, 0.0, governed_units)

    out["constraint_block_flag"] = np.where(block | overstock, "YES", "NO")
    out["constraint_block_reason"] = np.where(overstock, "overstock_run_down_no_buy", block_reason)
    out["final_governed_order_units"] = pd.Series(governed_units, index=out.index).round(0)
    out["final_governed_action_label"] = np.where(
        block | overstock,
        np.where(unsafe, "BLOCKED_UNSAFE", np.where(overstock, "NO_BUY_RUN_DOWN", "HOLD_FOR_REPLENISHMENT")),
        out["brain_action_label"],
    )

    family_scores = pd.DataFrame({
        "promo": _numeric(out, "promo_regime_score"),
        "stock": _numeric(out, "stock_regime_score"),
        "cash": _numeric(out, "cash_regime_score"),
        "supplier": _numeric(out, "supplier_regime_score"),
        "demand": _numeric(out, "demand_regime_score"),
    }, index=out.index)
    ranked = family_scores.apply(lambda row: row.sort_values(ascending=False).index.tolist()[:3], axis=1)
    out["top_regime_driver_1"] = [r[0] if len(r) > 0 else "demand" for r in ranked]
    out["top_regime_driver_2"] = [r[1] if len(r) > 1 else "stock" for r in ranked]
    out["top_regime_driver_3"] = [r[2] if len(r) > 2 else "cash" for r in ranked]
    out["human_interpretation_summary"] = (
        "Brain proposes " + out["brain_action_label"].astype(str)
        + " for " + out["brain_order_units_proposal"].astype(int).astype(str) + " units; "
        + "top drivers: " + out["top_regime_driver_1"] + ", " + out["top_regime_driver_2"] + ", " + out["top_regime_driver_3"]
        + "; constraints: " + out["constraint_block_reason"].astype(str).replace("", "none")
    )
    return out.fillna(0.0)


def build_regime_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for field in REGIME_FIELDS:
        if field not in frame.columns:
            continue
        for value, chunk in frame.groupby(field, dropna=False):
            rows.append({
                "regime_field": field,
                "regime_value": str(value),
                "row_count": int(len(chunk)),
                "avg_opportunity_score": float(_numeric(chunk, "overall_regime_opportunity_score").mean()),
                "avg_risk_score": float(_numeric(chunk, "overall_regime_risk_score").mean()),
                "avg_decision_value": float(_numeric(chunk, "regime_adjusted_decision_value").mean()),
            })
    return pd.DataFrame(rows)


def build_regime_score_summary(frame: pd.DataFrame) -> pd.DataFrame:
    score_cols = [
        "store_regime_score", "customer_regime_score", "demand_regime_score", "stock_regime_score",
        "supplier_regime_score", "promo_regime_score", "cash_regime_score",
        "overall_regime_opportunity_score", "overall_regime_risk_score", "overall_regime_conviction_score",
    ]
    rows = []
    for col in score_cols:
        if col not in frame.columns:
            continue
        s = _numeric(frame, col)
        rows.append({
            "score_field": col,
            "mean": float(s.mean()),
            "p25": float(s.quantile(0.25)),
            "p50": float(s.quantile(0.50)),
            "p75": float(s.quantile(0.75)),
            "min": float(s.min()),
            "max": float(s.max()),
        })
    return pd.DataFrame(rows)


def build_action_value_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{
        "row_count": int(len(frame)),
        "avg_regime_adjusted_decision_value": float(_numeric(frame, "regime_adjusted_decision_value").mean()),
        "total_expected_gp_proxy": float((_numeric(frame, "actual_units_sold_promo") * _first_col(frame, ("promo_gm_unit",), default=4)).sum()),
        "total_cash_drag_penalty": float(_numeric(frame, "cash_drag_penalty").sum()),
        "total_missed_demand_penalty": float(_numeric(frame, "missed_demand_penalty").sum()),
        "total_overstock_run_down_reward": float(_numeric(frame, "overstock_run_down_reward").sum()),
        "total_stockout_trust_penalty": float(_numeric(frame, "stockout_trust_penalty").sum()),
        "aggressive_buy_count": int(frame.get("brain_action_label", pd.Series("", index=frame.index)).eq("AGGRESSIVE_BUY").sum()),
        "no_buy_run_down_count": int(frame.get("brain_action_label", pd.Series("", index=frame.index)).eq("NO_BUY_RUN_DOWN").sum()),
        "constraint_block_count": int(frame.get("constraint_block_flag", pd.Series("NO", index=frame.index)).eq("YES").sum()),
    }])


def evaluate_regime_release_gate(frame: pd.DataFrame, *, model_bias_pct: float = -23.6) -> tuple[str, str, pd.DataFrame]:
    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in frame.columns else "promo_demand_release_ready_flag"
    limited = int(
        (
            frame.get("regime_release_ready_flag", pd.Series("NO")).eq("YES")
            & frame.get(quality_col, pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
        ).sum()
    ) if "regime_release_ready_flag" in frame.columns else 0

    recommendation = "NO_RELEASE"
    blocker = "model_bias_dangerously_negative" if model_bias_pct < -15.0 else "pending_evaluation"
    if model_bias_pct >= -15.0 and limited > 0 and float(_numeric(frame, "regime_adjusted_decision_value").mean()) > 0:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "regime_brain_shadow_only_bias_or_evidence_not_exceptional"
    if model_bias_pct >= -15.0 and limited > 100 and float(_numeric(frame, "overall_regime_conviction_score").mean()) >= 50:
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"

    gate = pd.DataFrame([{
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "limited_release_rows": limited,
        "release_ready_rows": int(frame.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "unsafe_rows": int(frame.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "avg_opportunity_score": float(_numeric(frame, "overall_regime_opportunity_score").mean()),
        "avg_risk_score": float(_numeric(frame, "overall_regime_risk_score").mean()),
        "constraint_block_count": int(frame.get("constraint_block_flag", pd.Series("NO")).eq("YES").sum()),
        "notes": "phase5k_blocks_full_customer_release_by_default",
    }])
    return recommendation, blocker, gate


def apply_regime_brain_decisioning(
    scored_df: pd.DataFrame,
    *,
    gate_recommendation: str = "NO_RELEASE",
) -> pd.DataFrame:
    out = apply_brain_constraint_interpretation(scored_df, gate_recommendation=gate_recommendation)
    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in out.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in out.columns else "promo_demand_release_ready_flag"
    ready = (
        (gate_recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        & out.get(release_col, pd.Series("NO", index=out.index)).astype(str).eq("YES")
        & out.get(quality_col, pd.Series("UNSAFE", index=out.index)).astype(str).isin(["HIGH", "MEDIUM"])
        & out.get("constraint_block_flag", pd.Series("NO", index=out.index)).astype(str).eq("NO")
        & _numeric(out, "overall_regime_conviction_score").ge(45)
    )
    out["regime_release_ready_flag"] = np.where(ready, "YES", "NO")
    return out


def write_phase5k01_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    source = frame if frame is not None else apply_stock_truth_repair(load_stock_truth_source(rebuild=rebuild))
    source = apply_stock_outcome_optimisation(source, gate_recommendation="NO_RELEASE")
    source = apply_optimal_stock_learning(source, gate_recommendation="NO_RELEASE")
    working = simulate_stock_position_outcomes(source)

    recommendation, blocker, gate = evaluate_regime_release_gate(working)
    enriched = apply_regime_brain_decisioning(working, gate_recommendation=recommendation)
    recommendation, blocker, gate = evaluate_regime_release_gate(enriched)

    build_regime_distribution(enriched).to_csv(diagnostics_dir / "phase5k01_regime_distribution.csv", index=False)
    build_regime_score_summary(enriched).to_csv(diagnostics_dir / "phase5k01_regime_score_summary.csv", index=False)
    build_action_value_summary(enriched).to_csv(diagnostics_dir / "phase5k01_action_value_summary.csv", index=False)

    brain_cols = [
        c for c in (
            "sku_number", "sku_description", "department", "promotion_name",
            "brain_action_label", "brain_order_units_proposal", "constraint_block_flag",
            "constraint_block_reason", "final_governed_action_label", "final_governed_order_units",
            "top_regime_driver_1", "top_regime_driver_2", "top_regime_driver_3", "human_interpretation_summary",
        ) if c in enriched.columns
    ]
    enriched[brain_cols].to_csv(diagnostics_dir / "phase5k01_brain_vs_governed_actions.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5k01_release_gate.csv", index=False)

    drivers = enriched[["top_regime_driver_1", "top_regime_driver_2", "top_regime_driver_3"]].stack().value_counts().head(5)
    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in enriched.columns else "promo_demand_source_quality"

    return {
        "high_opportunity_sku_count": int((_numeric(enriched, "overall_regime_opportunity_score") >= 60).sum()),
        "high_risk_sku_count": int((_numeric(enriched, "overall_regime_risk_score") >= 50).sum()),
        "high_conviction_sku_count": int((_numeric(enriched, "overall_regime_conviction_score") >= 60).sum()),
        "brain_aggressive_buy_count": int(enriched.get("brain_action_label", pd.Series("", index=enriched.index)).eq("AGGRESSIVE_BUY").sum()),
        "brain_no_buy_run_down_count": int(enriched.get("brain_action_label", pd.Series("", index=enriched.index)).eq("NO_BUY_RUN_DOWN").sum()),
        "governed_buy_count": int(enriched.get("final_governed_action_label", pd.Series("", index=enriched.index)).isin(["AGGRESSIVE_BUY", "CONTROLLED_BUY", "TOP_UP_TO_OPTIMAL"]).sum()),
        "governed_hold_count": int(enriched.get("final_governed_action_label", pd.Series("", index=enriched.index)).eq("HOLD_FOR_REPLENISHMENT").sum()),
        "governed_no_buy_count": int(enriched.get("final_governed_action_label", pd.Series("", index=enriched.index)).isin(["NO_BUY_RUN_DOWN", "BLOCKED_UNSAFE"]).sum()),
        "constraint_blocked_count": int(enriched.get("constraint_block_flag", pd.Series("NO", index=enriched.index)).eq("YES").sum()),
        "top_regime_drivers": drivers.to_dict(),
        "release_ready_rows": int(enriched.get("promo_demand_release_ready_flag_repaired", enriched.get("promo_demand_release_ready_flag", pd.Series("NO"))).eq("YES").sum()),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(enriched.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5k01_regime_state(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5k01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def load_regime_artifacts(diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR) -> tuple[pd.DataFrame, str]:
    gate_path = diagnostics_dir / "phase5k01_release_gate.csv"
    if not gate_path.exists():
        return pd.DataFrame(), "NO_RELEASE"
    gate = pd.read_csv(gate_path)
    return gate, str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
