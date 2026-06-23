from __future__ import annotations

"""Phase 5N — economic value scoring and review queue ROI calibration."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_long_tail_basket_trust import build_long_tail_basket_trust_frame
from models.promotions.promo_conviction_calibration import (
    DEFAULT_MODEL_BIAS_PCT,
    apply_conviction_calibration,
    load_conviction_artifacts,
)
from models.promotions.promo_decision_triage import apply_promo_decision_triage, load_triage_artifacts
from models.promotions.promo_optimal_stock_learning import (
    apply_optimal_stock_learning,
    simulate_stock_position_outcomes,
)
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
from models.promotions.promo_stock_outcome_optimisation import (
    DEFAULT_UNIT_COST_PROXY,
    apply_stock_outcome_optimisation,
)
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5n01_economic_value_scoring")
REVIEW_COST_PER_MINUTE = 2.0
ROI_FLOOR = 1.0
GP_MARGIN_PROXY = 0.35
MAX_MISSED_VALUE_PROXY = 500.0
MAX_BASKET_VALUE_PROXY = 200.0
MAX_CASH_RELEASE_PROXY = 2000.0

COSMETICS_KEYWORDS = frozenset({"cosmetic", "cosmetics", "colour", "color", "fragrance", "direct", "makeup", "skincare"})


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _first_col(frame: pd.DataFrame, names: tuple[str, ...], default: float = 0.0) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce").fillna(default)
    return pd.Series(default, index=frame.index, dtype=float)


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def _release_col(frame: pd.DataFrame) -> str:
    return "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in frame.columns else "promo_demand_release_ready_flag"


def _gp_unit(frame: pd.DataFrame) -> pd.Series:
    return _first_col(frame, ("promo_gm_unit",), default=DEFAULT_UNIT_COST_PROXY * GP_MARGIN_PROXY)


def _is_cosmetics(frame: pd.DataFrame) -> pd.Series:
    dept = frame.get("department", pd.Series("", index=frame.index)).astype(str).str.lower()
    cat = frame.get("category", pd.Series("", index=frame.index)).astype(str).str.lower()
    combined = dept + " " + cat
    mask = pd.Series(False, index=frame.index)
    for kw in COSMETICS_KEYWORDS:
        mask = mask | combined.str.contains(kw, na=False)
    return mask


def _economic_label(score: pd.Series) -> pd.Series:
    return pd.cut(
        score,
        bins=[-1e9, 0, 25, 75, 200, 1e9],
        labels=["NEGATIVE", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
    ).astype(str)


def _roi_label(score: pd.Series) -> pd.Series:
    return pd.cut(
        score,
        bins=[-0.1, 1, 5, 15, 50, 1e9],
        labels=["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
    ).astype(str)


def build_promo_economic_value_frame(df: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Build economic value components and net score at promo SKU grain."""
    del config
    out = df.copy()
    quality = out.get(_quality_col(out), pd.Series("UNSAFE", index=out.index)).astype(str)
    unsafe = quality.eq("UNSAFE")
    gp = _gp_unit(out)
    uplift = _numeric(out, "expected_promo_uplift_units")
    convexity = _numeric(out, "promo_convexity_score").div(100).clip(0, 1)
    loyalty = out.get("customer_loyalty_regime", pd.Series("", index=out.index)).astype(str).eq("LOYALTY_HIGH")
    basket_risk = out.get("customer_basket_trust_regime", pd.Series("", index=out.index)).astype(str).eq("BASKET_TRUST_RISK")
    hist = _first_col(out, ("historical_units_same_discount_avg",))

    out["expected_gp_capture_value"] = (uplift * gp * (0.5 + convexity * 0.5)).clip(0, 500).round(3)

    missed_units = _numeric(out, "simulated_missed_demand_units")
    out["missed_units_risk"] = missed_units.round(3)
    missed_mult = (1.0 + convexity + loyalty.astype(float) * 0.5 + basket_risk.astype(float) * 0.3)
    out["missed_gp_value_proxy"] = (missed_units * gp * missed_mult).clip(0, MAX_MISSED_VALUE_PROXY).round(3)
    out["missed_sales_avoidance_value"] = np.where(unsafe, 0.0, out["missed_gp_value_proxy"])
    out["missed_sales_avoidance_value"] = pd.Series(out["missed_sales_avoidance_value"], index=out.index).round(3)

    out["basket_trust_risk_score"] = (
        basket_risk.astype(float) * 40
        + out.get("stock_constraint_regime", pd.Series("", index=out.index)).astype(str).eq("CENSORED_DEMAND_RISK").astype(float) * 30
        + (hist.gt(hist.quantile(0.75) if hist.gt(0).any() else 1)).astype(float) * 20
    ).clip(0, 100).round(1)
    out["basket_trust_value_proxy"] = (out["basket_trust_risk_score"] * gp * 0.15).clip(0, MAX_BASKET_VALUE_PROXY).round(3)
    out["basket_trust_protection_value"] = np.where(unsafe, 0.0, out["basket_trust_value_proxy"])
    out["basket_trust_protection_value"] = pd.Series(out["basket_trust_protection_value"], index=out.index).round(3)
    out["customer_disappointment_risk"] = np.where(
        out["basket_trust_risk_score"].ge(50) & missed_units.gt(0),
        "HIGH",
        np.where(out["basket_trust_risk_score"].ge(25), "MEDIUM", "LOW"),
    )
    out["mission_sku_flag"] = np.where(
        loyalty & basket_risk & hist.gt(0),
        "YES",
        "NO",
    )

    optimal = _numeric(out, "optimal_base_soh_units")
    current = _numeric(out, "current_soh")
    leftover = _numeric(out, "leftover_units_above_optimal")
    overstock_units = (current - optimal).clip(lower=0.0)
    overstock_units = np.where(leftover.gt(0), leftover, overstock_units)
    out["overstock_units_above_optimal"] = pd.Series(overstock_units, index=out.index).round(3)
    out["overstock_cost_above_optimal"] = (out["overstock_units_above_optimal"] * DEFAULT_UNIT_COST_PROXY).round(3)
    run_down_units = np.minimum(
        out["overstock_units_above_optimal"],
        np.maximum(uplift * 0.5, _numeric(out, "average_daily_units") * _numeric(out, "promo_days", 7.0)),
    )
    out["expected_cash_release_units"] = pd.Series(run_down_units, index=out.index).round(3)
    out["expected_cash_release_value"] = (run_down_units * DEFAULT_UNIT_COST_PROXY * 0.25).clip(0, MAX_CASH_RELEASE_PROXY).round(3)
    out["overstock_cash_release_value"] = out["expected_cash_release_value"]
    out["cash_release_priority_score"] = (
        out["expected_cash_release_value"].div(MAX_CASH_RELEASE_PROXY).mul(100)
        + out.get("capital_at_risk_regime", pd.Series("", index=out.index)).astype(str).eq("CASH_RELEASE_PRIORITY").astype(float) * 20
    ).clip(0, 100).round(1)

    out["cash_tied_above_optimal_cost"] = (leftover.clip(lower=0) * DEFAULT_UNIT_COST_PROXY).clip(0, 5000).round(3)

    repl = out.get("replenishment_risk_class", out.get("supplier_replenishment_class_repaired", pd.Series("", index=out.index))).astype(str)
    unknown_supplier = out.get("supplier_number_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str).eq("UNKNOWN")
    cosmetics = _is_cosmetics(out)
    brain_units = _numeric(out, "brain_order_units_proposal")
    position = out.get("current_stock_position_label", pd.Series("", index=out.index)).astype(str)

    out["replenishment_failure_cost_proxy"] = np.where(
        repl.str.contains("21", na=False) | cosmetics,
        missed_units * gp * 0.5,
        missed_units * gp * 0.2,
    ).clip(0, 300).round(3)
    out["long_lead_underbuy_penalty"] = np.where(
        (repl.str.contains("21", na=False) | cosmetics) & position.eq("UNDERSTOCKED") & brain_units.gt(0),
        brain_units * gp * 0.3,
        0.0,
    ).round(3)
    out["overnight_overbuy_penalty"] = np.where(
        repl.str.contains("OVERNIGHT", na=False) & brain_units.gt(_numeric(out, "expected_promo_uplift_units")),
        (brain_units - uplift).clip(lower=0) * DEFAULT_UNIT_COST_PROXY * 0.15,
        0.0,
    ).round(3)
    out["supplier_economic_risk_cost"] = (
        np.where(unknown_supplier, 25.0, 0.0)
        + out["replenishment_failure_cost_proxy"] * 0.2
        + out["long_lead_underbuy_penalty"] * 0.3
        + out["overnight_overbuy_penalty"] * 0.3
    ).clip(0, 500).round(3)
    out["supplier_risk_cost"] = out["supplier_economic_risk_cost"]

    triage_class = out.get("decision_triage_class", pd.Series("", index=out.index)).astype(str)
    review_triaged = out.get("buyer_review_required_flag_triaged", pd.Series("NO", index=out.index)).astype(str).eq("YES")
    effort = np.select(
        [
            triage_class.str.contains("HIGH_PRIORITY", na=False),
            triage_class.str.contains("STANDARD", na=False),
            triage_class.str.contains("RUN_DOWN", na=False),
        ],
        [12.0, 8.0, 6.0],
        default=5.0,
    )
    effort = np.where(unsafe, 3.0, effort)
    effort = np.where(~review_triaged, 0.0, effort)
    out["review_effort_minutes_estimate"] = pd.Series(effort, index=out.index).round(1)
    out["review_effort_cost"] = (out["review_effort_minutes_estimate"] * REVIEW_COST_PER_MINUTE).round(3)

    out = build_long_tail_basket_trust_frame(out)

    out["economic_net_value_score"] = (
        out["expected_gp_capture_value"]
        + out["missed_sales_avoidance_value"]
        + out["basket_trust_protection_value"]
        + out["long_tail_protection_value"]
        + out["basket_trust_convexity_value"]
        + out["overstock_cash_release_value"]
        - out["cash_tied_above_optimal_cost"]
        - out["supplier_risk_cost"]
        - out["review_effort_cost"]
    ).round(3)

    confidence = (
        40.0
        + np.where(quality.isin(["HIGH", "MEDIUM"]), 25.0, 0.0)
        + np.where(out.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str).eq("HIGH"), 15.0, 0.0)
        + _numeric(out, "calibrated_regime_conviction_score").mul(0.2)
        - np.where(unsafe, 40.0, 0.0)
        - _numeric(out, "regime_historical_wape").clip(0, 1).mul(20)
    )
    out["economic_value_confidence_score"] = confidence.clip(0, 100).round(1)
    out["economic_value_label"] = _economic_label(out["economic_net_value_score"])

    out["review_roi_score"] = (
        out["economic_net_value_score"] / out["review_effort_cost"].clip(lower=ROI_FLOOR)
    ).clip(-100, 500).round(3)
    out["review_roi_label"] = _roi_label(out["review_roi_score"].clip(lower=0))

    drivers = pd.DataFrame({
        "gp_capture": out["expected_gp_capture_value"],
        "missed_sales": out["missed_sales_avoidance_value"],
        "basket_trust": out["basket_trust_protection_value"],
        "long_tail": out["long_tail_protection_value"],
        "basket_convexity": out["basket_trust_convexity_value"],
        "cash_release": out["overstock_cash_release_value"],
        "cash_tied_cost": out["cash_tied_above_optimal_cost"],
        "supplier_cost": out["supplier_risk_cost"],
    }, index=out.index)
    ranked = drivers.apply(lambda row: row.sort_values(ascending=False).index.tolist()[:3], axis=1)
    out["economic_value_driver_1"] = [r[0] if len(r) > 0 else "gp_capture" for r in ranked]
    out["economic_value_driver_2"] = [r[1] if len(r) > 1 else "missed_sales" for r in ranked]
    out["economic_value_driver_3"] = [r[2] if len(r) > 2 else "cash_release" for r in ranked]

    numeric_cols = out.select_dtypes(include=[np.number]).columns
    out[numeric_cols] = out[numeric_cols].fillna(0.0)
    return out


def _normalize_series(series: pd.Series) -> pd.Series:
    lo = float(series.min())
    hi = float(series.max())
    if hi <= lo:
        return pd.Series(50.0, index=series.index)
    return ((series - lo) / (hi - lo) * 100.0).clip(0, 100)


def apply_economic_review_rerank(frame: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Re-rank buyer review queue using economic value and ROI."""
    cfg = config or {}
    out = build_promo_economic_value_frame(frame, config=cfg)
    old_rank = _numeric(out, "buyer_review_queue_rank")
    roi_norm = _normalize_series(_numeric(out, "review_roi_score"))
    econ_norm = _normalize_series(_numeric(out, "economic_net_value_score"))
    out["triage_priority_score_v2"] = (
        roi_norm * 0.30
        + econ_norm * 0.30
        + _numeric(out, "buyer_review_priority_score") * 0.15
        + _numeric(out, "overall_regime_opportunity_score") * 0.10
        + _numeric(out, "calibrated_regime_conviction_score") * 0.05
        + _normalize_series(_numeric(out, "long_tail_protection_value")) * 0.05
        + _normalize_series(_numeric(out, "basket_trust_convexity_value")) * 0.05
    ).clip(0, 100).round(1)

    review = out.get("buyer_review_required_flag_triaged", pd.Series("NO", index=out.index)).astype(str).eq("YES")
    econ_rank = pd.Series(0, index=out.index, dtype=int)
    if review.any():
        econ_rank.loc[review] = (
            out.loc[review, "triage_priority_score_v2"].rank(method="first", ascending=False).astype(int)
        )
    out["economic_priority_rank"] = econ_rank

    bucket = np.select(
        [
            ~review,
            econ_rank.between(1, 50),
            econ_rank.between(51, 100),
            econ_rank.between(101, 250),
            econ_rank.between(251, 500),
            review & econ_rank.gt(500),
        ],
        ["NOT_FOR_REVIEW", "TOP_50", "TOP_100", "TOP_250", "TOP_500", "BACKLOG"],
        default="NOT_FOR_REVIEW",
    )
    out["economic_review_queue_bucket"] = bucket
    out["economic_review_batch"] = np.select(
        [
            bucket == "TOP_50",
            bucket == "TOP_100",
            bucket == "TOP_250",
            bucket == "TOP_500",
            bucket == "BACKLOG",
        ],
        ["ECON_BATCH_1_TOP_50", "ECON_BATCH_2_TOP_100", "ECON_BATCH_3_TOP_250", "ECON_BATCH_4_TOP_500", "ECON_BATCH_BACKLOG"],
        default="NONE",
    )

    rank_change = np.where(review & old_rank.gt(0) & econ_rank.gt(0), old_rank - econ_rank, 0)
    out["priority_rank_change"] = pd.Series(rank_change, index=out.index).astype(int)
    out["priority_rank_change_reason"] = np.select(
        [
            rank_change >= 50,
            rank_change >= 10,
            rank_change <= -50,
            rank_change <= -10,
            review & (rank_change == 0),
        ],
        [
            "economic_roi_major_uplift",
            "economic_value_uplift",
            "economic_value_major_downgrade",
            "economic_value_downgrade",
            "rank_unchanged",
        ],
        default="not_in_review_queue",
    )

    return out


def build_economic_value_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "expected_gp_capture_value", "missed_sales_avoidance_value", "basket_trust_protection_value",
        "long_tail_protection_value", "basket_trust_convexity_value",
        "overstock_cash_release_value", "cash_tied_above_optimal_cost", "supplier_risk_cost",
        "review_effort_cost", "economic_net_value_score", "review_roi_score",
    ]
    rows = []
    for col in cols:
        if col not in frame.columns:
            continue
        s = _numeric(frame, col)
        rows.append({
            "component": col,
            "row_count": int(len(frame)),
            "total": float(s.sum()),
            "mean": float(s.mean()),
            "p50": float(s.quantile(0.5)),
            "p75": float(s.quantile(0.75)),
            "max": float(s.max()),
        })
    return pd.DataFrame(rows)


def build_economic_by_triage_class(frame: pd.DataFrame) -> pd.DataFrame:
    if "decision_triage_class" not in frame.columns:
        return pd.DataFrame()
    return (
        frame.groupby("decision_triage_class", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            avg_economic_net_value=("economic_net_value_score", "mean"),
            total_economic_net_value=("economic_net_value_score", "sum"),
            avg_review_roi=("review_roi_score", "mean"),
            avg_missed_avoidance=("missed_sales_avoidance_value", "mean"),
            avg_cash_release=("overstock_cash_release_value", "mean"),
        )
        .reset_index()
        .sort_values("total_economic_net_value", ascending=False)
    )


def _bucket_economic_value(frame: pd.DataFrame, rank_col: str, max_rank: int, value_col: str = "economic_net_value_score") -> float:
    review = frame.get("buyer_review_required_flag_triaged", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    chunk = frame[review & _numeric(frame, rank_col).between(1, max_rank)]
    if value_col not in chunk.columns:
        value_col = "regime_adjusted_decision_value"
    return float(_numeric(chunk, value_col).sum())


def build_workload_value_summary(
    before_frame: pd.DataFrame,
    after_frame: pd.DataFrame,
    *,
    release_recommendation: str,
) -> pd.DataFrame:
    def _top(frame: pd.DataFrame, rank_col: str, n: int, value_col: str) -> float:
        return _bucket_economic_value(frame, rank_col, n, value_col=value_col)

    review = after_frame.get("buyer_review_required_flag_triaged", pd.Series("NO", index=after_frame.index)).astype(str).eq("YES")
    queue = after_frame[review]
    return pd.DataFrame([{
        "top_50_decision_value_phase5m": _top(before_frame, "buyer_review_queue_rank", 50, "regime_adjusted_decision_value"),
        "top_250_decision_value_phase5m": _top(before_frame, "buyer_review_queue_rank", 250, "regime_adjusted_decision_value"),
        "top_500_decision_value_phase5m": _top(before_frame, "buyer_review_queue_rank", 500, "regime_adjusted_decision_value"),
        "top_50_economic_value_phase5n": _top(after_frame, "economic_priority_rank", 50, "economic_net_value_score"),
        "top_250_economic_value_phase5n": _top(after_frame, "economic_priority_rank", 250, "economic_net_value_score"),
        "top_500_economic_value_phase5n": _top(after_frame, "economic_priority_rank", 500, "economic_net_value_score"),
        "total_missed_sales_avoidance_value": float(_numeric(after_frame, "missed_sales_avoidance_value").sum()),
        "total_basket_trust_protection_value": float(_numeric(after_frame, "basket_trust_protection_value").sum()),
        "total_overstock_cash_release_value": float(_numeric(after_frame, "overstock_cash_release_value").sum()),
        "total_review_effort_cost": float(_numeric(queue, "review_effort_cost").sum()),
        "avg_review_roi": float(_numeric(queue, "review_roi_score").mean()) if len(queue) else 0.0,
        "release_recommendation": release_recommendation,
    }])


def evaluate_economic_release_gate(
    frame: pd.DataFrame,
    *,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> tuple[str, str, pd.DataFrame]:
    quality = _quality_col(frame)
    release = _release_col(frame)
    limited = int(
        (
            frame.get("economic_release_ready_flag", pd.Series("NO")).eq("YES")
            & frame.get(quality, pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
        ).sum()
    ) if "economic_release_ready_flag" in frame.columns else 0

    recommendation = "NO_RELEASE"
    blocker = "model_bias_dangerously_negative" if model_bias_pct < -15.0 else "economic_value_not_release_ready"
    if model_bias_pct >= -15.0 and limited > 0:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "economic_shadow_only_bias_or_evidence_not_exceptional"
    if model_bias_pct >= -15.0 and limited > 100:
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"

    gate = pd.DataFrame([{
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "limited_release_rows": limited,
        "release_ready_rows": int(frame.get(release, pd.Series("NO")).eq("YES").sum()),
        "unsafe_rows": int(frame.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "high_economic_value_rows": int(_numeric(frame, "economic_net_value_score").ge(75).sum()),
        "avg_review_roi": float(_numeric(frame, "review_roi_score").mean()),
        "notes": "phase5n_economic_ranking_no_customer_release",
    }])
    return recommendation, blocker, gate


def apply_promo_economic_value_scoring(
    triaged_df: pd.DataFrame,
    *,
    gate_recommendation: str = "NO_RELEASE",
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> pd.DataFrame:
    before = triaged_df.copy()
    out = apply_economic_review_rerank(triaged_df, config={"model_bias_pct": model_bias_pct})
    quality = _quality_col(out)
    release = _release_col(out)
    ready = (
        (gate_recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        & out.get(release, pd.Series("NO", index=out.index)).astype(str).eq("YES")
        & out.get(quality, pd.Series("UNSAFE", index=out.index)).astype(str).isin(["HIGH", "MEDIUM"])
        & out.get("auto_block_flag", pd.Series("NO", index=out.index)).astype(str).eq("NO")
        & out.get("economic_review_queue_bucket", pd.Series("", index=out.index)).isin(["TOP_50", "TOP_100"])
        & _numeric(out, "economic_value_confidence_score").ge(45)
    )
    out["economic_release_ready_flag"] = np.where(ready, "YES", "NO")
    out["_phase5m_snapshot_rank"] = _numeric(before, "buyer_review_queue_rank")
    return out


def write_phase5n01_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    source = frame if frame is not None else apply_stock_truth_repair(load_stock_truth_source(rebuild=rebuild))
    source = apply_stock_outcome_optimisation(source, gate_recommendation="NO_RELEASE")
    source = apply_optimal_stock_learning(source, gate_recommendation="NO_RELEASE")
    working = simulate_stock_position_outcomes(source)
    _regime_gate, regime_rec = load_regime_artifacts()
    regime_enriched = apply_regime_brain_decisioning(working, gate_recommendation=regime_rec)
    _conv_profile, conv_rec = load_conviction_artifacts()
    calibrated = apply_conviction_calibration(
        regime_enriched,
        error_profile_df=_conv_profile if not _conv_profile.empty else None,
        gate_recommendation=conv_rec,
        model_bias_pct=model_bias_pct,
    )
    triage_rec = load_triage_artifacts()
    triaged = apply_promo_decision_triage(calibrated, gate_recommendation=triage_rec, model_bias_pct=model_bias_pct)
    before_econ = triaged.copy()

    recommendation, blocker, gate = evaluate_economic_release_gate(triaged, model_bias_pct=model_bias_pct)
    enriched = apply_promo_economic_value_scoring(triaged, gate_recommendation=recommendation, model_bias_pct=model_bias_pct)
    recommendation, blocker, gate = evaluate_economic_release_gate(enriched, model_bias_pct=model_bias_pct)

    build_economic_value_distribution(enriched).to_csv(diagnostics_dir / "phase5n01_economic_value_distribution.csv", index=False)
    build_economic_by_triage_class(enriched).to_csv(diagnostics_dir / "phase5n01_economic_value_by_triage_class.csv", index=False)

    roi_cols = [
        c for c in (
            "sku_number", "sku_description", "department", "promotion_name",
            "decision_triage_class", "buyer_review_priority_score", "triage_priority_score_v2",
            "economic_priority_rank", "economic_net_value_score", "review_roi_score", "review_roi_label",
            "expected_gp_capture_value", "missed_sales_avoidance_value", "overstock_cash_release_value",
            "brain_action_label", "final_governed_action_label", "priority_rank_change", "priority_rank_change_reason",
        ) if c in enriched.columns
    ]
    review = enriched.loc[enriched["buyer_review_required_flag_triaged"].eq("YES")].sort_values(
        "economic_priority_rank", kind="mergesort"
    )
    review[roi_cols].head(500).to_csv(diagnostics_dir / "phase5n01_review_queue_roi.csv", index=False)

    rank_change = enriched.loc[
        enriched["buyer_review_required_flag_triaged"].eq("YES")
        & enriched["priority_rank_change"].abs().gt(0)
    ].sort_values("priority_rank_change", ascending=False)
    rank_change_cols = [c for c in roi_cols if c in rank_change.columns]
    rank_change[rank_change_cols].head(500).to_csv(diagnostics_dir / "phase5n01_rank_change_review.csv", index=False)

    build_workload_value_summary(before_econ, enriched, release_recommendation=recommendation).to_csv(
        diagnostics_dir / "phase5n01_workload_value_summary.csv", index=False
    )
    gate.to_csv(diagnostics_dir / "phase5n01_release_gate.csv", index=False)

    quality = _quality_col(enriched)
    release = _release_col(enriched)
    workload = build_workload_value_summary(before_econ, enriched, release_recommendation=recommendation).iloc[0]

    return {
        "top_50_value_before": float(workload["top_50_decision_value_phase5m"]),
        "top_50_value_after": float(workload["top_50_economic_value_phase5n"]),
        "top_250_value_before": float(workload["top_250_decision_value_phase5m"]),
        "top_250_value_after": float(workload["top_250_economic_value_phase5n"]),
        "top_500_value_before": float(workload["top_500_decision_value_phase5m"]),
        "top_500_value_after": float(workload["top_500_economic_value_phase5n"]),
        "missed_sales_avoidance_value": float(workload["total_missed_sales_avoidance_value"]),
        "basket_trust_protection_value": float(workload["total_basket_trust_protection_value"]),
        "overstock_cash_release_value": float(workload["total_overstock_cash_release_value"]),
        "review_roi_avg": float(workload["avg_review_roi"]),
        "high_economic_value_rows": int(_numeric(enriched, "economic_net_value_score").ge(75).sum()),
        "release_ready_rows": int(enriched.get(release, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(enriched.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5n01_economic_value_scoring(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5n01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def load_economic_artifacts(diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR) -> str:
    gate_path = diagnostics_dir / "phase5n01_release_gate.csv"
    if not gate_path.exists():
        return "NO_RELEASE"
    gate = pd.read_csv(gate_path)
    return str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
