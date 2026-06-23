from __future__ import annotations

"""Phase 5M — governed decision triage and buyer workload prioritisation."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_conviction_calibration import (
    DEFAULT_MODEL_BIAS_PCT,
    apply_conviction_calibration,
    load_conviction_artifacts,
)
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

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5m01_decision_triage")
LARGE_ORDER_UNITS = 10.0
SEVERE_CASH_DRAG_DOLLARS = 100.0
HIGH_VALUE_EXCEPTION_SCORE = 70.0

REVIEW_CLASSES = frozenset({
    "HIGH_PRIORITY_BUY_REVIEW",
    "HIGH_PRIORITY_RUN_DOWN_REVIEW",
    "STANDARD_BUY_REVIEW",
    "STANDARD_RUN_DOWN_REVIEW",
})

AUTO_BLOCK_CLASSES = frozenset({
    "AUTO_BLOCK_UNSAFE",
    "AUTO_BLOCK_DATA_QUALITY",
    "AUTO_BLOCK_CAPITAL_RISK",
})


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def _release_col(frame: pd.DataFrame) -> str:
    return "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in frame.columns else "promo_demand_release_ready_flag"


def _clip_score(series: pd.Series) -> pd.Series:
    return series.clip(0.0, 100.0).round(1)


def _priority_label(score: pd.Series) -> pd.Series:
    return pd.cut(
        score,
        bins=[-0.1, 20, 40, 60, 79.9, 100.0],
        labels=["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
    ).astype(str)


def compute_buyer_review_priority_score(frame: pd.DataFrame, *, model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT) -> pd.Series:
    """Score 0–100 for buyer review queue ordering."""
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    score = pd.Series(20.0, index=frame.index)
    score += _numeric(frame, "regime_adjusted_decision_value").clip(-50, 50).add(50).div(100).mul(20)
    score += _numeric(frame, "overall_regime_opportunity_score").mul(0.15)
    score += _numeric(frame, "promo_convexity_score").mul(0.08)
    score += _numeric(frame, "missed_demand_penalty").clip(0, 100).mul(0.08)
    score += _numeric(frame, "expected_promo_uplift_units").clip(0, 50).mul(0.2)
    score += np.where(
        frame.get("capital_at_risk_regime", pd.Series("", index=frame.index)).astype(str).eq("CASH_RELEASE_PRIORITY"),
        8.0,
        0.0,
    )
    score += np.where(
        frame.get("customer_basket_trust_regime", pd.Series("", index=frame.index)).astype(str).eq("BASKET_TRUST_RISK"),
        5.0,
        0.0,
    )
    score += np.where(frame.get(_release_col(frame), pd.Series("NO", index=frame.index)).astype(str).eq("YES"), 5.0, 0.0)
    score += np.where(
        frame.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=frame.index)).astype(str).eq("HIGH"),
        5.0,
        0.0,
    )
    score += np.where(quality.isin(["HIGH", "MEDIUM"]), 5.0, 0.0)

    score -= np.where(quality.eq("UNSAFE"), 45.0, 0.0)
    score -= np.where(
        frame.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=frame.index)).astype(str).eq("UNKNOWN"),
        20.0,
        0.0,
    )
    score -= np.where(
        frame.get("supplier_number_source_quality", pd.Series("UNKNOWN", index=frame.index)).astype(str).eq("UNKNOWN"),
        10.0,
        0.0,
    )
    score -= _numeric(frame, "cash_drag_penalty").clip(0, 200).mul(0.05)
    score -= _numeric(frame, "regime_historical_wape").clip(0, 1).mul(15)
    score -= np.where(model_bias_pct < -15.0, 10.0, 0.0)
    score -= np.where(frame.get("constraint_block_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES"), 12.0, 0.0)
    score -= (100 - _numeric(frame, "calibrated_regime_conviction_score")).mul(0.15)

    unsafe = quality.eq("UNSAFE")
    score = np.where(unsafe, np.minimum(score, 65.0), score)
    return _clip_score(pd.Series(score, index=frame.index))


def build_promo_decision_triage_frame(df: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
    """Assign triage class, priority, and review queue fields."""
    cfg = config or {}
    model_bias_pct = float(cfg.get("model_bias_pct", DEFAULT_MODEL_BIAS_PCT))
    gate_recommendation = str(cfg.get("gate_recommendation", "NO_RELEASE"))
    out = df.copy()

    quality = out.get(_quality_col(out), pd.Series("UNSAFE", index=out.index)).astype(str)
    release = out.get(_release_col(out), pd.Series("NO", index=out.index)).astype(str)
    unsafe = quality.eq("UNSAFE")
    unknown_soh = out.get("promo_start_soh_source_quality", pd.Series("UNKNOWN", index=out.index)).astype(str).eq("UNKNOWN")
    blocked = out.get("constraint_block_flag", pd.Series("NO", index=out.index)).astype(str).eq("YES")
    brain_units = _numeric(out, "brain_order_units_proposal")
    position = out.get("current_stock_position_label", pd.Series("", index=out.index)).astype(str)
    overstock = position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])
    cash_drag = _numeric(out, "cash_drag_penalty")
    cash_above = _numeric(out, "leftover_units_above_optimal") * DEFAULT_UNIT_COST_PROXY
    opp = _numeric(out, "overall_regime_opportunity_score")
    risk = _numeric(out, "overall_regime_risk_score")
    decision_value = _numeric(out, "regime_adjusted_decision_value")
    brain_action = out.get("brain_action_label", pd.Series("", index=out.index)).astype(str)
    buy_action = brain_action.isin(["AGGRESSIVE_BUY", "CONTROLLED_BUY", "TOP_UP_TO_OPTIMAL"])
    run_down = brain_action.eq("NO_BUY_RUN_DOWN") | overstock
    high_value_exception = (
        release.eq("YES")
        & quality.isin(["HIGH", "MEDIUM"])
        & decision_value.ge(HIGH_VALUE_EXCEPTION_SCORE)
        & opp.ge(45)
    )

    out["buyer_review_priority_score"] = compute_buyer_review_priority_score(out, model_bias_pct=model_bias_pct)
    out["buyer_review_priority_label"] = _priority_label(out["buyer_review_priority_score"])

    triage_class = np.select(
        [
            unsafe & ~high_value_exception,
            unknown_soh & brain_units.gt(LARGE_ORDER_UNITS),
            (cash_drag.ge(SEVERE_CASH_DRAG_DOLLARS) | cash_above.ge(SEVERE_CASH_DRAG_DOLLARS * 2)) & blocked,
            overstock & cash_above.gt(0) & opp.ge(40) & out["buyer_review_priority_score"].ge(55),
            overstock & cash_above.gt(0),
            buy_action & opp.ge(50) & risk.le(45) & ~unsafe,
            buy_action & ~unsafe,
            run_down & ~overstock,
            (
                release.eq("YES")
                & quality.isin(["HIGH", "MEDIUM"])
                & ~blocked
                & ~unsafe
                & out.get("calibrated_conviction_label", pd.Series("LOW", index=out.index)).astype(str).isin(["MEDIUM", "HIGH", "VERY_HIGH"])
                & decision_value.gt(0)
                & (gate_recommendation != "NO_RELEASE")
            ),
            opp.le(25) & risk.le(25) & ~buy_action & ~run_down,
            opp.le(15) & risk.le(20),
        ],
        [
            "AUTO_BLOCK_UNSAFE",
            "AUTO_BLOCK_DATA_QUALITY",
            "AUTO_BLOCK_CAPITAL_RISK",
            "HIGH_PRIORITY_RUN_DOWN_REVIEW",
            "STANDARD_RUN_DOWN_REVIEW",
            "HIGH_PRIORITY_BUY_REVIEW",
            "STANDARD_BUY_REVIEW",
            "STANDARD_RUN_DOWN_REVIEW",
            "FUTURE_AUTO_APPROVE_CANDIDATE",
            "WATCHLIST_ONLY",
            "NO_ACTION",
        ],
        default="WATCHLIST_ONLY",
    )
    out["decision_triage_class"] = triage_class

    triage_reason = np.select(
        [
            pd.Series(triage_class, index=out.index).eq("AUTO_BLOCK_UNSAFE").to_numpy(),
            pd.Series(triage_class, index=out.index).eq("AUTO_BLOCK_DATA_QUALITY").to_numpy(),
            pd.Series(triage_class, index=out.index).eq("AUTO_BLOCK_CAPITAL_RISK").to_numpy(),
            pd.Series(triage_class, index=out.index).eq("HIGH_PRIORITY_BUY_REVIEW").to_numpy(),
            pd.Series(triage_class, index=out.index).eq("HIGH_PRIORITY_RUN_DOWN_REVIEW").to_numpy(),
            pd.Series(triage_class, index=out.index).eq("STANDARD_BUY_REVIEW").to_numpy(),
            pd.Series(triage_class, index=out.index).eq("STANDARD_RUN_DOWN_REVIEW").to_numpy(),
            pd.Series(triage_class, index=out.index).eq("FUTURE_AUTO_APPROVE_CANDIDATE").to_numpy(),
            pd.Series(triage_class, index=out.index).eq("WATCHLIST_ONLY").to_numpy(),
        ],
        [
            "unsafe_source_quality_auto_block",
            "unknown_stock_truth_large_order_block",
            "severe_capital_risk_block",
            "high_opportunity_controlled_risk_buy",
            "overstock_cash_release_priority",
            "standard_buy_review",
            "standard_run_down_review",
            "strong_evidence_future_auto_approve",
            "low_opportunity_watchlist",
        ],
        default="no_action_required",
    )
    out["decision_triage_reason"] = triage_reason

    out["auto_block_flag"] = np.where(out["decision_triage_class"].isin(list(AUTO_BLOCK_CLASSES)), "YES", "NO")
    out["watchlist_flag"] = np.where(out["decision_triage_class"].eq("WATCHLIST_ONLY"), "YES", "NO")
    out["future_auto_approve_candidate_flag"] = np.where(
        out["decision_triage_class"].eq("FUTURE_AUTO_APPROVE_CANDIDATE"), "YES", "NO"
    )
    out["buyer_review_required_flag_triaged"] = np.where(
        out["decision_triage_class"].isin(list(REVIEW_CLASSES)), "YES", "NO"
    )

    review_mask = out["buyer_review_required_flag_triaged"].eq("YES")
    ranks = pd.Series(0, index=out.index, dtype=int)
    if review_mask.any():
        review_scores = out.loc[review_mask, "buyer_review_priority_score"].rank(method="first", ascending=False)
        ranks.loc[review_mask] = review_scores.astype(int)
    out["buyer_review_queue_rank"] = ranks

    bucket = np.select(
        [
            ~review_mask,
            ranks.between(1, 50),
            ranks.between(51, 100),
            ranks.between(101, 250),
            ranks.between(251, 500),
            review_mask & ranks.gt(500),
        ],
        ["NOT_FOR_REVIEW", "TOP_50", "TOP_100", "TOP_250", "TOP_500", "BACKLOG"],
        default="NOT_FOR_REVIEW",
    )
    out["buyer_review_queue_bucket"] = bucket
    out["recommended_review_batch"] = np.select(
        [
            bucket == "TOP_50",
            bucket == "TOP_100",
            bucket == "TOP_250",
            bucket == "TOP_500",
            bucket == "BACKLOG",
        ],
        ["BATCH_1_TOP_50", "BATCH_2_TOP_100", "BATCH_3_TOP_250", "BATCH_4_TOP_500", "BATCH_BACKLOG"],
        default="NONE",
    )
    out["triage_governance_note"] = (
        "Triage class "
        + out["decision_triage_class"].astype(str)
        + "; priority "
        + out["buyer_review_priority_label"].astype(str)
        + "; queue "
        + out["buyer_review_queue_bucket"].astype(str)
        + "; brain preserved; no production order"
    )

    numeric_cols = out.select_dtypes(include=[np.number]).columns
    out[numeric_cols] = out[numeric_cols].fillna(0.0)
    return out


def build_triage_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    quality = _quality_col(frame)
    for field in (
        "decision_triage_class",
        "buyer_review_priority_label",
        "buyer_review_queue_bucket",
        _release_col(frame),
        quality,
        "constraint_block_flag",
    ):
        if field not in frame.columns:
            continue
        for value, chunk in frame.groupby(field, dropna=False):
            rows.append({
                "group_field": field,
                "group_value": str(value),
                "row_count": int(len(chunk)),
                "avg_priority_score": float(_numeric(chunk, "buyer_review_priority_score").mean()),
                "total_decision_value": float(_numeric(chunk, "regime_adjusted_decision_value").sum()),
            })
    return pd.DataFrame(rows)


def build_auto_block_summary(frame: pd.DataFrame) -> pd.DataFrame:
    blocked = frame[frame.get("auto_block_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")]
    if blocked.empty:
        return pd.DataFrame(columns=["decision_triage_class", "decision_triage_reason", "row_count"])
    return (
        blocked.groupby(["decision_triage_class", "decision_triage_reason"], dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values("row_count", ascending=False)
    )


def build_workload_summary(
    frame: pd.DataFrame,
    *,
    review_before: int,
    release_recommendation: str,
) -> pd.DataFrame:
    review_after = int(frame.get("buyer_review_required_flag_triaged", pd.Series("NO", index=frame.index)).eq("YES").sum())
    review_queue = frame[frame.get("buyer_review_required_flag_triaged", pd.Series("NO", index=frame.index)).astype(str).eq("YES")]

    def _bucket_value(max_rank: int) -> float:
        chunk = review_queue[_numeric(review_queue, "buyer_review_queue_rank").between(1, max_rank)]
        return float(_numeric(chunk, "regime_adjusted_decision_value").sum())

    def _bucket_cash_release(max_rank: int) -> float:
        chunk = review_queue[_numeric(review_queue, "buyer_review_queue_rank").between(1, max_rank)]
        return float((_numeric(chunk, "leftover_units_above_optimal") * DEFAULT_UNIT_COST_PROXY).sum())

    def _bucket_missed_reduction(max_rank: int) -> float:
        chunk = review_queue[_numeric(review_queue, "buyer_review_queue_rank").between(1, max_rank)]
        return float(_numeric(chunk, "missed_demand_penalty").sum())

    triage = frame.get("decision_triage_class", pd.Series("", index=frame.index)).astype(str)
    return pd.DataFrame([{
        "total_rows": int(len(frame)),
        "buyer_review_required_before": int(review_before),
        "buyer_review_required_after": review_after,
        "auto_block_count": int(frame.get("auto_block_flag", pd.Series("NO")).eq("YES").sum()),
        "watchlist_count": int(frame.get("watchlist_flag", pd.Series("NO")).eq("YES").sum()),
        "no_action_count": int(triage.eq("NO_ACTION").sum()),
        "high_priority_review_count": int(triage.isin(["HIGH_PRIORITY_BUY_REVIEW", "HIGH_PRIORITY_RUN_DOWN_REVIEW"]).sum()),
        "standard_review_count": int(triage.isin(["STANDARD_BUY_REVIEW", "STANDARD_RUN_DOWN_REVIEW"]).sum()),
        "top_50_total_decision_value": _bucket_value(50),
        "top_250_total_decision_value": _bucket_value(250),
        "top_500_total_decision_value": _bucket_value(500),
        "expected_cash_release_from_review_queue": _bucket_cash_release(250),
        "expected_missed_demand_reduction_from_review_queue": _bucket_missed_reduction(250),
        "release_recommendation": release_recommendation,
    }])


def evaluate_triage_release_gate(
    frame: pd.DataFrame,
    *,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> tuple[str, str, pd.DataFrame]:
    quality = _quality_col(frame)
    release = _release_col(frame)
    limited = int(
        (
            frame.get("triage_release_ready_flag", pd.Series("NO")).eq("YES")
            & frame.get(quality, pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
            & frame.get("buyer_review_queue_bucket", pd.Series("", index=frame.index)).isin(["TOP_50", "TOP_100"])
        ).sum()
    ) if "triage_release_ready_flag" in frame.columns else 0

    recommendation = "NO_RELEASE"
    blocker = "model_bias_dangerously_negative" if model_bias_pct < -15.0 else "triage_workload_not_release_ready"
    if model_bias_pct >= -15.0 and limited > 0:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "triage_shadow_only_bias_or_evidence_not_exceptional"
    if model_bias_pct >= -15.0 and limited > 50 and int(frame.get("future_auto_approve_candidate_flag", pd.Series("NO")).eq("YES").sum()) > 0:
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"

    gate = pd.DataFrame([{
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "limited_release_rows": limited,
        "release_ready_rows": int(frame.get(release, pd.Series("NO")).eq("YES").sum()),
        "unsafe_rows": int(frame.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "buyer_review_required_after": int(frame.get("buyer_review_required_flag_triaged", pd.Series("NO")).eq("YES").sum()),
        "auto_block_count": int(frame.get("auto_block_flag", pd.Series("NO")).eq("YES").sum()),
        "notes": "phase5m_practical_buyer_workload_no_customer_release",
    }])
    return recommendation, blocker, gate


def apply_promo_decision_triage(
    scored_df: pd.DataFrame,
    *,
    gate_recommendation: str = "NO_RELEASE",
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> pd.DataFrame:
    review_before = int(scored_df.get("buyer_review_required_flag", pd.Series("NO", index=scored_df.index)).eq("YES").sum())
    out = build_promo_decision_triage_frame(
        scored_df,
        config={"gate_recommendation": gate_recommendation, "model_bias_pct": model_bias_pct},
    )
    out["buyer_review_required_before_triage"] = review_before
    quality = _quality_col(out)
    release = _release_col(out)
    ready = (
        (gate_recommendation == "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        & out.get(release, pd.Series("NO", index=out.index)).astype(str).eq("YES")
        & out.get(quality, pd.Series("UNSAFE", index=out.index)).astype(str).isin(["HIGH", "MEDIUM"])
        & out.get("auto_block_flag", pd.Series("NO", index=out.index)).astype(str).eq("NO")
        & out.get("buyer_review_queue_bucket", pd.Series("", index=out.index)).isin(["TOP_50", "TOP_100"])
    )
    out["triage_release_ready_flag"] = np.where(ready, "YES", "NO")
    return out


def write_phase5m01_diagnostics(
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

    review_before = int(calibrated.get("buyer_review_required_flag", pd.Series("NO", index=calibrated.index)).eq("YES").sum())
    recommendation, blocker, gate = evaluate_triage_release_gate(calibrated, model_bias_pct=model_bias_pct)
    triaged = apply_promo_decision_triage(calibrated, gate_recommendation=recommendation, model_bias_pct=model_bias_pct)
    recommendation, blocker, gate = evaluate_triage_release_gate(triaged, model_bias_pct=model_bias_pct)

    build_triage_distribution(triaged).to_csv(diagnostics_dir / "phase5m01_triage_distribution.csv", index=False)

    top_cols = [
        c for c in (
            "sku_number", "sku_description", "department", "promotion_name",
            "decision_triage_class", "buyer_review_priority_score", "buyer_review_queue_rank",
            "brain_action_label", "final_governed_action_label", "final_governed_order_units",
            "optimal_stock_position_order_units", "regime_adjusted_decision_value",
            "expected_promo_uplift_units", "leftover_units_above_optimal", "missed_demand_penalty",
            "calibrated_regime_conviction_score", "conviction_downgrade_reason",
            "decision_triage_reason", "human_interpretation_summary",
        ) if c in triaged.columns
    ]
    top_queue = triaged.loc[triaged["buyer_review_required_flag_triaged"].eq("YES")].sort_values(
        "buyer_review_queue_rank", kind="mergesort"
    ).copy()
    top_queue["cash_tied_above_optimal"] = (_numeric(top_queue, "leftover_units_above_optimal") * DEFAULT_UNIT_COST_PROXY).round(3)
    export_cols = [c for c in top_cols if c in top_queue.columns]
    if "cash_tied_above_optimal" in top_queue.columns and "cash_tied_above_optimal" not in export_cols:
        export_cols.append("cash_tied_above_optimal")
    top_queue[export_cols].head(500).to_csv(diagnostics_dir / "phase5m01_top_review_queue.csv", index=False)
    build_auto_block_summary(triaged).to_csv(diagnostics_dir / "phase5m01_auto_block_summary.csv", index=False)
    build_workload_summary(triaged, review_before=review_before, release_recommendation=recommendation).to_csv(
        diagnostics_dir / "phase5m01_workload_summary.csv", index=False
    )
    gate.to_csv(diagnostics_dir / "phase5m01_release_gate.csv", index=False)

    review_after = int(triaged.get("buyer_review_required_flag_triaged", pd.Series("NO")).eq("YES").sum())
    workload = build_workload_summary(triaged, review_before=review_before, release_recommendation=recommendation).iloc[0]
    quality = _quality_col(triaged)
    release = _release_col(triaged)

    return {
        "buyer_review_required_before": review_before,
        "buyer_review_required_after": review_after,
        "auto_block_count": int(triaged.get("auto_block_flag", pd.Series("NO")).eq("YES").sum()),
        "watchlist_count": int(triaged.get("watchlist_flag", pd.Series("NO")).eq("YES").sum()),
        "high_priority_review_count": int(workload["high_priority_review_count"]),
        "top_50_total_decision_value": float(workload["top_50_total_decision_value"]),
        "top_250_total_decision_value": float(workload["top_250_total_decision_value"]),
        "top_500_total_decision_value": float(workload["top_500_total_decision_value"]),
        "release_ready_rows": int(triaged.get(release, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(triaged.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5m01_decision_triage(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5m01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def load_triage_artifacts(diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR) -> str:
    gate_path = diagnostics_dir / "phase5m01_release_gate.csv"
    if not gate_path.exists():
        return "NO_RELEASE"
    gate = pd.read_csv(gate_path)
    return str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
