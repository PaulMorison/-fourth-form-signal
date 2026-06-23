from __future__ import annotations

"""Phase 5O — buyer action pack with long-tail basket trust protection."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_conviction_calibration import (
    DEFAULT_MODEL_BIAS_PCT,
    apply_conviction_calibration,
    load_conviction_artifacts,
)
from models.promotions.promo_decision_triage import apply_promo_decision_triage, load_triage_artifacts
from models.promotions.promo_economic_value_scoring import (
    apply_promo_economic_value_scoring,
    load_economic_artifacts,
)
from models.promotions.promo_optimal_stock_learning import (
    apply_optimal_stock_learning,
    simulate_stock_position_outcomes,
)
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
from models.promotions.promo_stock_outcome_optimisation import apply_stock_outcome_optimisation
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5o01_buyer_action_pack")

LONG_TAIL_ACTION_COLUMNS = (
    "long_tail_sku_flag",
    "basket_completion_sku_flag",
    "basket_attachment_score",
    "basket_mission_importance_score",
    "long_tail_stockout_risk_score",
    "basket_loss_multiplier",
    "long_tail_protection_value",
    "basket_trust_convexity_value",
    "long_tail_basket_protection_reason",
)

BUYER_CHECK_RECOMMENDATIONS = (
    "Protect long-tail basket SKU; verify 2-unit minimum SOH",
    "Check basket-completion item before promo starts",
    "Low unit seller but high basket/trust value",
    "Do not remove from range without basket impact review",
)


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def _base_action_columns(frame: pd.DataFrame) -> list[str]:
    cols = [
        "sku_number", "sku_description", "department", "promotion_name",
        "decision_triage_class", "economic_priority_rank", "economic_net_value_score",
        "missed_sales_avoidance_value", "brain_action_label", "final_governed_action_label",
        "current_soh", "expected_soh_at_promo_start_before_order",
        *LONG_TAIL_ACTION_COLUMNS,
        "recommended_buyer_checks",
    ]
    return [c for c in cols if c in frame.columns]


def _attach_buyer_checks(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    checks = []
    for _, row in out.iterrows():
        items: list[str] = []
        if row.get("long_tail_open_for_sale_required_flag") == "YES":
            items.append(BUYER_CHECK_RECOMMENDATIONS[0])
        if row.get("basket_completion_sku_flag") == "YES":
            items.append(BUYER_CHECK_RECOMMENDATIONS[1])
        if row.get("long_tail_sku_flag") == "YES" and _numeric(pd.DataFrame([row]), "basket_attachment_score").iloc[0] >= 35:
            items.append(BUYER_CHECK_RECOMMENDATIONS[2])
        if row.get("long_tail_sku_flag") == "YES" or row.get("basket_completion_sku_flag") == "YES":
            items.append(BUYER_CHECK_RECOMMENDATIONS[3])
        checks.append("; ".join(dict.fromkeys(items)))
    out["recommended_buyer_checks"] = checks
    return out


def build_buyer_top_50_actions(frame: pd.DataFrame) -> pd.DataFrame:
    review = frame.loc[frame.get("buyer_review_required_flag_triaged", pd.Series("NO", index=frame.index)).astype(str).eq("YES")]
    top = review.loc[_numeric(review, "economic_priority_rank").between(1, 50)].sort_values("economic_priority_rank", kind="mergesort")
    return _attach_buyer_checks(top)[_base_action_columns(top)]


def build_buyer_top_250_review(frame: pd.DataFrame) -> pd.DataFrame:
    review = frame.loc[frame.get("buyer_review_required_flag_triaged", pd.Series("NO", index=frame.index)).astype(str).eq("YES")]
    top = review.loc[_numeric(review, "economic_priority_rank").between(1, 250)].sort_values("economic_priority_rank", kind="mergesort")
    return _attach_buyer_checks(top)[_base_action_columns(top)]


def build_missed_demand_protection_actions(frame: pd.DataFrame) -> pd.DataFrame:
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    uplift = _numeric(frame, "expected_promo_uplift_units")
    current = _numeric(frame, "current_soh")
    expected = _numeric(frame, "expected_soh_at_promo_start_before_order", current)
    mask = (
        quality.ne("UNSAFE")
        & frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
        & uplift.le(2)
        & (current.lt(2) | expected.lt(2))
        & _numeric(frame, "basket_attachment_score").ge(25)
    )
    cols = _base_action_columns(frame) + ["long_tail_minimum_soh_required", "long_tail_open_for_sale_required_flag"]
    cols = [c for c in cols if c in frame.columns]
    out = frame.loc[mask, cols].copy()
    return out.sort_values(
        ["long_tail_protection_value", "basket_trust_convexity_value", "missed_sales_avoidance_value"],
        ascending=False,
        kind="mergesort",
    )


def build_blocked_data_quality_review(frame: pd.DataFrame) -> pd.DataFrame:
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    basket_unknown = frame.get("basket_3plus_attachment_rate", pd.Series("UNKNOWN", index=frame.index)).astype(str).eq("UNKNOWN")
    long_tail = frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    high_risk = _numeric(frame, "long_tail_stockout_risk_score").ge(40)
    mask = quality.eq("UNSAFE") | ((long_tail | high_risk) & basket_unknown)
    out = frame.loc[mask].copy()
    idx = out.index
    basket_unknown_out = out.get("basket_3plus_attachment_rate", pd.Series("UNKNOWN", index=idx)).astype(str).eq("UNKNOWN")
    long_tail_out = out.get("long_tail_sku_flag", pd.Series("NO", index=idx)).astype(str).eq("YES")
    out["data_fix_required"] = np.select(
        [
            basket_unknown_out & long_tail_out,
            _numeric(out, "current_soh").lt(2),
            out.get("basket_completion_sku_flag", pd.Series("NO", index=idx)).astype(str).eq("YES"),
            basket_unknown_out,
        ],
        [
            "Need basket attachment evidence",
            "Verify long-tail SOH",
            "Confirm SKU is basket-completion item",
            "Resolve transaction attachment history",
        ],
        default="Check online/front-door availability",
    )
    cols = [
        "sku_number", "sku_description", "department", "promotion_name",
        _quality_col(frame), "long_tail_sku_flag", "basket_completion_sku_flag",
        "basket_3plus_attachment_rate", "long_tail_stockout_risk_score",
        "long_tail_protection_value", "data_fix_required",
    ]
    cols = [c for c in cols if c in out.columns]
    return out[cols].sort_values("long_tail_stockout_risk_score", ascending=False, kind="mergesort")


def build_long_tail_basket_trust_summary(frame: pd.DataFrame) -> pd.DataFrame:
    review = frame.loc[frame.get("buyer_review_required_flag_triaged", pd.Series("NO", index=frame.index)).astype(str).eq("YES")]
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    long_tail = frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    below_min = long_tail & _numeric(frame, "current_soh").lt(2)
    rank = _numeric(frame, "economic_priority_rank")
    return pd.DataFrame([{
        "total_long_tail_skus": int(long_tail.sum()),
        "long_tail_skus_below_2_soh": int(below_min.sum()),
        "long_tail_basket_completion_skus": int(
            (long_tail & frame.get("basket_completion_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")).sum()
        ),
        "high_basket_trust_risk_rows": int(_numeric(frame, "long_tail_stockout_risk_score").ge(50).sum()),
        "long_tail_protection_value_total": float(_numeric(frame, "long_tail_protection_value").sum()),
        "basket_trust_convexity_value_total": float(_numeric(frame, "basket_trust_convexity_value").sum()),
        "long_tail_rows_in_top_50": int((long_tail & rank.between(1, 50)).sum()),
        "long_tail_rows_in_top_250": int((long_tail & rank.between(1, 250)).sum()),
        "long_tail_blocked_due_to_data_quality": int((long_tail & quality.eq("UNSAFE")).sum()),
        "estimated_basket_gp_at_risk_proxy": float(
            pd.to_numeric(frame.get("avg_basket_gp_when_present", pd.Series(0, index=frame.index)), errors="coerce")
            .fillna(0)
            .mul(long_tail.astype(float))
            .sum()
        ),
        "release_recommendation": "NO_RELEASE",
    }])


def build_long_tail_stockout_risk_review(frame: pd.DataFrame) -> pd.DataFrame:
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    long_tail = frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    current = _numeric(frame, "current_soh")
    expected = _numeric(frame, "expected_soh_at_promo_start_before_order", current)
    basket_unknown = frame.get("basket_3plus_attachment_rate", pd.Series("UNKNOWN", index=frame.index)).astype(str).eq("UNKNOWN")
    material = _numeric(frame, "long_tail_stockout_risk_score").ge(25)
    mask = long_tail & ((current.lt(2) | expected.lt(2) | material) | basket_unknown)
    out = frame.loc[mask].copy()
    idx = out.index
    quality_out = quality.loc[idx]
    basket_unknown_out = basket_unknown.loc[idx]
    out["action_recommendation"] = np.select(
        [
            out.get("long_tail_open_for_sale_required_flag", pd.Series("NO", index=idx)).astype(str).eq("YES"),
            out.get("basket_completion_sku_flag", pd.Series("NO", index=idx)).astype(str).eq("YES"),
            _numeric(out, "long_tail_stockout_risk_score").ge(25),
        ],
        [
            "Protect long-tail basket SKU; verify 2-unit minimum SOH",
            "Check basket-completion item before promo starts",
            "Review long-tail stockout risk before promo",
        ],
        default="Monitor long-tail basket role",
    )
    out["data_fix_required"] = np.where(
        basket_unknown_out,
        "Need basket attachment evidence",
        np.where(quality_out.eq("UNSAFE"), "Resolve unsafe demand/SOH evidence", "None"),
    )
    out["human_interpretation"] = np.where(
        out.get("long_tail_sku_flag", pd.Series("NO", index=idx)).astype(str).eq("YES")
        & _numeric(out, "basket_attachment_score").ge(35),
        "Low unit seller but high basket/trust value",
        "Long-tail SKU with potential basket role",
    )
    cols = [
        "sku_number", "sku_description", "department", "current_soh",
        "expected_soh_at_promo_start_before_order", "long_tail_minimum_soh_required",
        "basket_attachment_score", "basket_mission_importance_score",
        "long_tail_stockout_risk_score", "long_tail_protection_value",
        "basket_trust_convexity_value", "action_recommendation",
        "data_fix_required", "human_interpretation",
    ]
    cols = [c for c in cols if c in out.columns]
    rename = {"sku_number": "SKU", "sku_description": "description"}
    return out[cols].rename(columns=rename).sort_values("long_tail_protection_value", ascending=False, kind="mergesort")


def evaluate_buyer_action_pack_release_gate(frame: pd.DataFrame) -> tuple[str, str, pd.DataFrame]:
    quality = _quality_col(frame)
    recommendation = "NO_RELEASE"
    blocker = "model_bias_dangerously_negative"
    gate = pd.DataFrame([{
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "long_tail_skus": int(frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES").sum()),
        "long_tail_open_for_sale_rows": int(
            frame.get("long_tail_open_for_sale_required_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES").sum()
        ),
        "unsafe_rows": int(frame.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "notes": "phase5o_long_tail_basket_trust_review_only_no_auto_order",
    }])
    return recommendation, blocker, gate


def write_phase5o01_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    if frame is not None:
        enriched = frame
    else:
        source = apply_stock_truth_repair(load_stock_truth_source(rebuild=rebuild))
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
        econ_rec = load_economic_artifacts()
        enriched = apply_promo_economic_value_scoring(triaged, gate_recommendation=econ_rec, model_bias_pct=model_bias_pct)

    build_buyer_top_50_actions(enriched).to_csv(diagnostics_dir / "phase5o01_buyer_top_50_actions.csv", index=False)
    build_buyer_top_250_review(enriched).to_csv(diagnostics_dir / "phase5o01_buyer_top_250_review.csv", index=False)
    build_missed_demand_protection_actions(enriched).to_csv(
        diagnostics_dir / "phase5o01_missed_demand_protection_actions.csv", index=False
    )
    build_blocked_data_quality_review(enriched).to_csv(
        diagnostics_dir / "phase5o01_blocked_data_quality_review.csv", index=False
    )
    build_long_tail_basket_trust_summary(enriched).to_csv(
        diagnostics_dir / "phase5o01_long_tail_basket_trust_summary.csv", index=False
    )
    build_long_tail_stockout_risk_review(enriched).to_csv(
        diagnostics_dir / "phase5o01_long_tail_stockout_risk_review.csv", index=False
    )
    recommendation, blocker, gate = evaluate_buyer_action_pack_release_gate(enriched)
    gate.to_csv(diagnostics_dir / "phase5o01_release_gate.csv", index=False)

    summary = build_long_tail_basket_trust_summary(enriched).iloc[0]
    return {
        "total_long_tail_skus": int(summary["total_long_tail_skus"]),
        "long_tail_protection_value_total": float(summary["long_tail_protection_value_total"]),
        "long_tail_rows_in_top_50": int(summary["long_tail_rows_in_top_50"]),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5o01_buyer_action_pack(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5o01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)
