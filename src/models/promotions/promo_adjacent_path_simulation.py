from __future__ import annotations

"""Phase 6B — nearest-adjacent path simulation for weak-history and new-line SKUs."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6b01_brain_state_adjacent_graph_reporting")

MATCH_COLUMNS = (
    "department", "category", "supplier_replenishment_regime", "stock_position_regime",
    "long_tail_sku_flag", "promo_convexity_regime", "basket_attachment_source_quality",
)
NUMERIC_MATCH = ("discount_percent", "mission_sku_score", "average_daily_units")


def _numeric(series: pd.Series | Any, default: float = 0.0) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series([pd.to_numeric(series, errors="coerce")]).fillna(default)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _col(frame: pd.DataFrame, col: str, default: str = "UNKNOWN") -> pd.Series:
    return frame.get(col, pd.Series(default, index=frame.index)).astype(str)


def build_available_to_sell_confidence(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive available-to-sell confidence from existing stock and quality signals."""
    out = frame.copy()
    n = len(out)
    soh = _numeric(out.get("current_soh", out.get("actual_start_soh", 0))).values
    expected = _numeric(out.get("expected_soh_at_promo_start_before_order", out.get("promo_start_soh_resolved", 0))).values
    stockout = _numeric(out.get("stockout_suspected_flag", out.get("actual_stockout_flag", 0))).astype(int).values
    quality = _col(out, "promo_start_soh_source_quality").replace("nan", "UNKNOWN").values
    demand_q = _col(out, "promo_demand_source_quality").values
    actual = _numeric(out.get("actual_units_sold_promo", 0)).values
    supplier_risk = _numeric(out.get("supplier_risk_cost", out.get("supplier_economic_risk_cost", 0))).values

    score = np.full(n, 0.5, dtype=float)
    score += np.where(soh > 0, 0.15, -0.2)
    score += np.where(expected > 0, 0.1, -0.1)
    score += np.where(stockout == 0, 0.15, -0.25)
    score += np.where(np.isin(quality, ["HIGH", "MEDIUM"]), 0.1, -0.15)
    score += np.where(np.isin(demand_q, ["HIGH", "MEDIUM"]), 0.05, -0.1)
    score += np.where((actual > 0) & (soh > 0), 0.1, 0.0)
    score -= np.clip(supplier_risk / 100.0, 0, 0.15)
    score = np.clip(score, 0.0, 1.0)

    out["available_to_sell_confidence_score"] = np.round(score, 4)
    out["ats_confidence_label"] = np.where(
        score >= 0.7, "HIGH",
        np.where(score >= 0.45, "MEDIUM", "LOW"),
    )
    out["ats_missing_reason"] = np.where(
        np.isin(quality, ["UNKNOWN"]) | np.isin(demand_q, ["UNSAFE"]), "STOCK_OR_DEMAND_QUALITY_WEAK", "",
    )
    out["ats_stockout_censoring_risk"] = np.where(stockout == 1, "YES", "NO")
    out["ats_false_zero_demand_risk"] = np.where(
        (actual <= 0.01) & (soh > 0) & (score < 0.45), "YES", "NO",
    )
    out["ats_do_not_learn_zero_sales_flag"] = np.where(
        (out["ats_false_zero_demand_risk"].values == "YES") | (out["ats_stockout_censoring_risk"].values == "YES"),
        "YES", "NO",
    )
    return out


def _history_strength(row: pd.Series) -> float:
    actual = float(_numeric(pd.Series([row.get("actual_units_sold_promo", 0)])).iloc[0])
    promo_days = float(_numeric(pd.Series([row.get("promo_days", 7)])).iloc[0])
    uplift = float(_numeric(pd.Series([row.get("expected_promo_uplift_units", row.get("model_expected_units_total_promo", 0))])).iloc[0])
    quality = str(row.get("promo_demand_source_quality", "UNSAFE"))
    score = min(1.0, actual / max(promo_days, 1.0) / 2.0)
    if quality in {"HIGH", "MEDIUM"}:
        score += 0.2
    if uplift > 0:
        score += 0.1
    return float(np.clip(score, 0.0, 1.0))


def build_new_line_weak_history_flags(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    strengths = out.apply(_history_strength, axis=1)
    out["history_strength_score"] = strengths.round(4)
    out["weak_history_flag"] = np.where(strengths.lt(0.25), "YES", "NO")
    out["new_line_flag"] = np.where(
        (_numeric(out.get("actual_units_sold_promo", 0)).le(0.01))
        & (_col(out, "promo_demand_source_quality").isin(["LOW", "UNKNOWN", "UNSAFE"])),
        "YES", "NO",
    )
    out["nearest_adjacent_simulation_required_flag"] = np.where(
        out["weak_history_flag"].eq("YES") | out["new_line_flag"].eq("YES")
        | _col(out, "basket_attachment_source_quality").isin(["LOW", "UNKNOWN"]),
        "YES", "NO",
    )
    return out


def build_nearest_adjacent_reference_set(
    frame: pd.DataFrame,
    *,
    max_refs: int = 5,
    min_pool: int = 3,
) -> pd.DataFrame:
    """Find nearest adjacent promo-SKU references within the same frame."""
    out = build_new_line_weak_history_flags(frame)
    if out.empty:
        return out

    group_key = out.get("department", pd.Series("UNKNOWN", index=out.index)).astype(str)
    if "category" in out.columns:
        group_key = group_key + "|" + out["category"].astype(str)
    group_sizes = group_key.groupby(group_key).transform("count") - 1
    ref_counts = group_sizes.clip(lower=0).astype(int)
    ref_quality = np.where(ref_counts >= min_pool, "HIGH", np.where(ref_counts > 0, "MEDIUM", "LOW"))
    ref_reason = np.where(
        ref_counts >= min_pool, "DEPARTMENT_CATEGORY_REGIME_MATCH",
        np.where(ref_counts > 0, "PARTIAL_ADJACENT_MATCH", "INSUFFICIENT_ADJACENT_POOL"),
    )
    out["adjacent_reference_count"] = np.minimum(ref_counts, max_refs)
    out["adjacent_reference_quality"] = ref_quality
    out["adjacent_reference_reason"] = ref_reason
    return out


def simulate_adjacent_outcome_paths(
    frame: pd.DataFrame,
    *,
    max_refs: int = 5,
) -> pd.DataFrame:
    """Simulate advisory adjacent outcomes — does not replace forecast."""
    out = build_nearest_adjacent_reference_set(frame, max_refs=max_refs)
    out = build_available_to_sell_confidence(out)

    group_key = out.get("department", pd.Series("UNKNOWN", index=out.index)).astype(str)
    if "category" in out.columns:
        group_key = group_key + "|" + out["category"].astype(str)

    actual = _numeric(out.get("actual_units_sold_promo", 0))
    forecast = _numeric(out.get("model_expected_units_total_promo", out.get("expected_promo_uplift_units", 0)))
    group_actual_mean = actual.groupby(group_key).transform("mean")
    group_forecast_mean = forecast.groupby(group_key).transform("mean")
    sim_units = np.where(group_actual_mean > 0, group_actual_mean, group_forecast_mean)
    needs_sim = out.get("nearest_adjacent_simulation_required_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")
    sim_units = np.where(needs_sim & (sim_units <= 0), 0.5, sim_units)
    sim_units = np.where(~needs_sim, forecast.values, sim_units)

    out["adjacent_expected_units"] = np.round(sim_units, 4)
    out["adjacent_expected_uplift_units"] = np.round(sim_units * 0.45, 4)
    out["adjacent_expected_gp"] = np.round(sim_units * 4.82 * 0.35, 4)
    out["adjacent_stockout_risk"] = np.where(
        _numeric(out.get("stockout_suspected_flag", 0)).gt(0), "YES", "NO",
    )
    out["adjacent_basket_trust_risk"] = np.where(
        _col(out, "basket_attachment_source_quality").isin(["LOW", "UNKNOWN"]), "YES", "NO",
    )
    out["adjacent_path_used_flag"] = np.where(needs_sim, "YES", "ADVISORY_ONLY")
    out["adjacent_path_warning"] = "ADVISORY_SIMULATION_NOT_DEPLOYED"
    out["new_line_decision_support_reason"] = np.where(
        needs_sim, "SIMULATED_FROM_GROUP_ADJACENT_REFS", "BASELINE_FORECAST",
    )
    return out


def score_adjacent_path_confidence(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    ref_q = out.get("adjacent_reference_quality", pd.Series("LOW", index=out.index)).astype(str)
    ref_n = _numeric(out.get("adjacent_reference_count", 0))
    hist = _numeric(out.get("history_strength_score", 0))
    ats = _numeric(out.get("available_to_sell_confidence_score", 0.5))

    conf = (
        np.where(ref_q.eq("HIGH"), 0.75, np.where(ref_q.eq("MEDIUM"), 0.55, 0.35))
        + np.clip(ref_n / 10.0, 0, 0.15)
        + hist * 0.1
        + ats * 0.1
    )
    conf = np.clip(conf, 0.0, 1.0)
    out["adjacent_confidence_score"] = np.round(conf, 4)
    out["new_line_adjacent_path_confidence"] = np.where(
        out.get("new_line_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES"),
        out["adjacent_confidence_score"],
        np.nan,
    )
    return out


def build_new_line_weak_history_review(frame: pd.DataFrame) -> pd.DataFrame:
    sim = score_adjacent_path_confidence(simulate_adjacent_outcome_paths(frame))
    cols = [
        "store_number", "promotion_id", "sku_number", "department", "category",
        "new_line_flag", "weak_history_flag", "history_strength_score",
        "nearest_adjacent_simulation_required_flag", "adjacent_reference_count",
        "adjacent_reference_quality", "adjacent_expected_units", "adjacent_confidence_score",
        "new_line_adjacent_path_confidence", "new_line_decision_support_reason",
        "adjacent_path_warning", "model_expected_units_total_promo", "actual_units_sold_promo",
    ]
    use = [c for c in cols if c in sim.columns]
    review = sim[use].copy()
    if "model_expected_units_total_promo" in review.columns:
        review["does_not_default_to_zero"] = (
            (review.get("nearest_adjacent_simulation_required_flag", pd.Series("NO")).astype(str).eq("YES"))
            & (_numeric(review.get("adjacent_expected_units", 0)).gt(0))
        ).map({True: "YES", False: "NA"})
    return review


def write_phase6b_adjacent_path_diagnostics(
    frame: pd.DataFrame,
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    sim = score_adjacent_path_confidence(simulate_adjacent_outcome_paths(frame))
    review = build_new_line_weak_history_review(sim)
    ats = sim[[c for c in sim.columns if c.startswith("ats_") or c == "available_to_sell_confidence_score"]].copy()
    ats_keys = [c for c in ("store_number", "promotion_id", "sku_number") if c in sim.columns]
    if ats_keys:
        ats = sim[ats_keys + [c for c in sim.columns if c.startswith("ats_") or c == "available_to_sell_confidence_score"]]

    export_cols = [
        c for c in sim.columns
        if c.startswith("adjacent_") or c.startswith("new_line_") or c.startswith("weak_")
        or c.startswith("history_") or c.startswith("nearest_")
    ]
    key_cols = [c for c in ("store_number", "promotion_id", "sku_number", "department") if c in sim.columns]
    sim[key_cols + export_cols].to_csv(diagnostics_dir / "phase6b01_adjacent_path_simulation.csv", index=False)
    review.to_csv(diagnostics_dir / "phase6b01_new_line_weak_history_review.csv", index=False)
    ats.to_csv(diagnostics_dir / "phase6b01_available_to_sell_confidence.csv", index=False)

    return {
        "weak_history_rows": int(sim.get("weak_history_flag", pd.Series("NO")).astype(str).eq("YES").sum()),
        "new_line_rows": int(sim.get("new_line_flag", pd.Series("NO")).astype(str).eq("YES").sum()),
        "adjacent_path_avg_confidence": float(_numeric(sim.get("adjacent_confidence_score", 0)).mean()),
        "false_zero_demand_risk_count": int(sim.get("ats_false_zero_demand_risk", pd.Series("NO")).astype(str).eq("YES").sum()),
        "ats_avg_confidence": float(_numeric(sim.get("available_to_sell_confidence_score", 0)).mean()),
        "simulation_df": sim,
    }
