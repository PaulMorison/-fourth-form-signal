from __future__ import annotations

"""Phase 5S — bias-controlled shadow candidate selection for internal brain observation."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_basket_attachment_features import apply_basket_attachment_to_promo_frame
from models.promotions.promo_brain_feature_learning import apply_brain_feature_learning
from models.promotions.promo_brain_leakage_audit import apply_brain_leakage_validation
from models.promotions.promo_conviction_calibration import (
    DEFAULT_MODEL_BIAS_PCT,
    apply_conviction_calibration,
    build_regime_error_profile,
    load_conviction_artifacts,
)
from models.promotions.promo_decision_triage import apply_promo_decision_triage, load_triage_artifacts
from models.promotions.promo_economic_value_scoring import apply_promo_economic_value_scoring, load_economic_artifacts
from models.promotions.promo_optimal_stock_learning import apply_optimal_stock_learning, simulate_stock_position_outcomes
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, load_regime_artifacts
from models.promotions.promo_stock_outcome_optimisation import apply_stock_outcome_optimisation
from models.promotions.promo_stock_truth_repair import apply_stock_truth_repair, load_stock_truth_source

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5s01_bias_controlled_shadow_candidates")
UNKNOWN = "UNKNOWN"

SHADOW_CLASSES = (
    "SHADOW_TOP_50_CANDIDATE",
    "SHADOW_TOP_100_CANDIDATE",
    "SHADOW_MISSION_SKU_CANDIDATE",
    "SHADOW_OVERSTOCK_RUN_DOWN_CANDIDATE",
    "SHADOW_UNDERSTOCKED_CONVEXITY_CANDIDATE",
    "SHADOW_DATA_REPAIR_ONLY",
    "NOT_SHADOW_SAFE",
)

OUTPUT_COLUMNS = (
    "shadow_candidate_flag",
    "shadow_candidate_class",
    "shadow_candidate_reason",
    "shadow_candidate_score",
    "shadow_candidate_rank",
    "shadow_candidate_bucket",
    "shadow_bias_risk_score",
    "shadow_economic_risk_score",
    "shadow_data_quality_score",
    "shadow_expected_learning_value",
    "shadow_observation_plan",
    "segment_historical_bias_pct",
    "segment_historical_wape",
    "segment_bias_control_status",
    "segment_bias_control_reason",
    "action_difference_flag",
    "action_difference_type",
    "expected_shadow_learning_question",
)

BIAS_CONTROLLED_MIN = -15.0
BIAS_CONTROLLED_MAX = 20.0
BIAS_MODERATE_MIN = -25.0
BIAS_MODERATE_MAX = 30.0
HIGH_WAPE_THRESHOLD = 0.50


def _numeric(frame: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[col], errors="coerce").fillna(default)


def _quality_col(frame: pd.DataFrame) -> str:
    return "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in frame.columns else "promo_demand_source_quality"


def _segment_bias_status(bias_pct: float, row_count: float = 100.0) -> tuple[str, str]:
    if row_count < 10:
        return "INSUFFICIENT_SEGMENT_EVIDENCE", "Segment sample too small for bias control."
    if BIAS_CONTROLLED_MIN <= bias_pct <= BIAS_CONTROLLED_MAX:
        return "BIAS_CONTROLLED", "Segment bias within controlled band."
    if BIAS_MODERATE_MIN <= bias_pct <= BIAS_MODERATE_MAX:
        return "BIAS_MODERATE_REVIEW", "Segment bias in moderate review band."
    return "BIAS_DANGEROUS_BLOCK", "Segment bias outside safe shadow band."


def _attach_segment_bias(frame: pd.DataFrame, error_profile: pd.DataFrame | None = None) -> pd.DataFrame:
    out = frame.copy()
    if "regime_historical_bias_pct" in out.columns and "regime_historical_wape" in out.columns:
        bias = _numeric(out, "regime_historical_bias_pct")
        wape = _numeric(out, "regime_historical_wape")
        row_count = _numeric(out, "regime_error_profile_row_count", 100.0)
    elif error_profile is not None and not error_profile.empty and "regime_error_profile_key" in out.columns:
        prof = error_profile.set_index("regime_error_profile_key")
        out["segment_historical_bias_pct"] = out["regime_error_profile_key"].map(prof.get("bias_pct", pd.Series(dtype=float))).fillna(DEFAULT_MODEL_BIAS_PCT)
        out["segment_historical_wape"] = out["regime_error_profile_key"].map(prof.get("WAPE", pd.Series(dtype=float))).fillna(0.35)
        out["regime_error_profile_row_count"] = out["regime_error_profile_key"].map(prof.get("row_count", pd.Series(dtype=float))).fillna(0)
        bias = _numeric(out, "segment_historical_bias_pct")
        wape = _numeric(out, "segment_historical_wape")
        row_count = _numeric(out, "regime_error_profile_row_count")
    else:
        out["segment_historical_bias_pct"] = DEFAULT_MODEL_BIAS_PCT
        out["segment_historical_wape"] = 0.35
        out["regime_error_profile_row_count"] = 0.0
        bias = _numeric(out, "segment_historical_bias_pct")
        wape = _numeric(out, "segment_historical_wape")
        row_count = _numeric(out, "regime_error_profile_row_count", 0.0)

    statuses, reasons = zip(*[_segment_bias_status(float(b), float(n)) for b, n in zip(bias, row_count)])
    out["segment_historical_bias_pct"] = bias.round(3)
    out["segment_historical_wape"] = wape.round(4)
    out["segment_bias_control_status"] = list(statuses)
    out["segment_bias_control_reason"] = list(reasons)
    return out


def _data_quality_score(frame: pd.DataFrame) -> pd.Series:
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    soh_q = frame.get("promo_start_soh_source_quality", pd.Series(UNKNOWN, index=frame.index)).astype(str)
    basket_q = frame.get("basket_attachment_source_quality", frame.get("feature_basket_attachment_quality", pd.Series(UNKNOWN, index=frame.index))).astype(str)
    real_basket = frame.get("basket_attachment_used_real_transactions_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    score = pd.Series(50.0, index=frame.index)
    score = score.where(~quality.eq("UNSAFE"), 0.0)
    score = score + np.where(soh_q.isin(["HIGH", "MEDIUM"]), 20.0, np.where(soh_q.eq(UNKNOWN), -15.0, 0.0))
    score = score + np.where(real_basket, 20.0, np.where(basket_q.eq("HIGH"), 10.0, np.where(basket_q.eq(UNKNOWN), -10.0, 0.0)))
    score = score + frame.get("brain_leak_safe_feature_count", pd.Series(0, index=frame.index)).astype(float).clip(0, 56) / 56.0 * 15.0
    return score.clip(0, 100).round(1)


def _learning_value(frame: pd.DataFrame) -> pd.Series:
    mission = _numeric(frame, "mission_sku_score")
    long_tail = frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    real_basket = frame.get("basket_attachment_used_real_transactions_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    attach = _numeric(frame, "feature_basket_3plus_attach_rate")
    convexity = _numeric(frame, "promo_convexity_score")
    position = frame.get("current_stock_position_label", pd.Series("", index=frame.index)).astype(str)
    alpha = frame.get("alpha_pattern_id", pd.Series("", index=frame.index)).astype(str)
    validation = frame.get("brain_validation_status", pd.Series("", index=frame.index)).astype(str)
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)

    value = pd.Series(10.0, index=frame.index)
    value = value + mission.clip(0, 100) * 0.25
    value = value + np.where(long_tail & real_basket, 25.0, 0.0)
    value = value + np.where(position.eq("UNDERSTOCKED") & convexity.ge(40), 20.0, 0.0)
    value = value + np.where(position.isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]), 15.0, 0.0)
    value = value + np.where(alpha.eq("REGIME_SHIFT_OPPORTUNITY"), 12.0, 0.0)
    value = value + np.where(alpha.eq("MISSION_SKU_STOCKOUT_TRUST_RISK"), 18.0, 0.0)
    value = value + attach.clip(0, 1) * 15.0
    value = value - np.where(quality.eq("UNSAFE") | alpha.eq("UNKNOWN_DATA_DO_NOT_LEARN"), 40.0, 0.0)
    value = value - np.where(validation.eq("EXPERIMENTAL_FAILED_LEAKAGE_CONTROL"), 30.0, 0.0)
    value = value - np.where(_numeric(frame, "average_daily_units").gt(50), 10.0, 0.0)
    return value.clip(0, 100).round(1)


def _reject_reasons(frame: pd.DataFrame) -> pd.Series:
    quality = frame.get(_quality_col(frame), pd.Series("UNSAFE", index=frame.index)).astype(str)
    unsafe = frame.get("unsafe_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    soh_q = frame.get("promo_start_soh_source_quality", pd.Series(UNKNOWN, index=frame.index)).astype(str)
    order_units = _numeric(frame, "final_governed_order_units")
    constraint = frame.get("constraint_block_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    validation = frame.get("brain_validation_status", pd.Series("", index=frame.index)).astype(str)
    survives = frame.get("brain_value_survives_leakage_control_flag", pd.Series("NO", index=frame.index)).astype(str)
    bias_status = frame.get("segment_bias_control_status", pd.Series("BIAS_DANGEROUS_BLOCK", index=frame.index)).astype(str)
    econ = _numeric(frame, "economic_net_value_score")
    learn = _numeric(frame, "shadow_expected_learning_value")
    wape = _numeric(frame, "segment_historical_wape")
    supplier = frame.get("supplier_replenishment_regime", pd.Series(UNKNOWN, index=frame.index)).astype(str)
    real_basket = frame.get("basket_attachment_used_real_transactions_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    basket_q = frame.get("basket_attachment_source_quality", pd.Series(UNKNOWN, index=frame.index)).astype(str)
    cash = _numeric(frame, "cash_tied_above_optimal_cost")

    return pd.Series(
        np.select(
            [
                unsafe | quality.eq("UNSAFE"),
                constraint,
                validation.eq("EXPERIMENTAL_FAILED_LEAKAGE_CONTROL"),
                survives.ne("YES") & validation.ne("LEAK_SAFE_VALIDATED"),
                soh_q.isin([UNKNOWN, "UNSAFE"]) & order_units.gt(0),
                ~real_basket & ~basket_q.isin(["HIGH", "MEDIUM"]),
                supplier.eq(UNKNOWN) & cash.gt(100),
                wape.gt(HIGH_WAPE_THRESHOLD),
                bias_status.eq("BIAS_DANGEROUS_BLOCK"),
                bias_status.eq("INSUFFICIENT_SEGMENT_EVIDENCE"),
                (econ <= 0) & learn.lt(25),
                cash.gt(500),
            ],
            [
                "UNSAFE_BLOCKED",
                "CONSTRAINT_BLOCKED",
                "BRAIN_VALIDATION_FAILED",
                "LEAKAGE_CONTROL_NOT_SURVIVED",
                "UNKNOWN_SOH_WITH_PROPOSED_BUY",
                "INSUFFICIENT_BASKET_EVIDENCE",
                "SUPPLIER_UNKNOWN_MATERIAL_RISK",
                "HIGH_WAPE_REGIME",
                "DANGEROUS_BIAS_REGIME",
                "INSUFFICIENT_SEGMENT_EVIDENCE",
                "NEGATIVE_ECONOMIC_AND_LOW_LEARNING_VALUE",
                "EXCESS_CASH_TIE_UP",
            ],
            default="",
        ),
        index=frame.index,
    )


def _classify_row(row: pd.Series, rank: int) -> str:
    if row.get("shadow_candidate_flag") != "YES":
        return "NOT_SHADOW_SAFE"
    if rank <= 50:
        return "SHADOW_TOP_50_CANDIDATE"
    if rank <= 100:
        return "SHADOW_TOP_100_CANDIDATE"
    if str(row.get("long_tail_mission_sku_flag", "NO")) == "YES" or float(row.get("mission_sku_score", 0)) >= 45:
        return "SHADOW_MISSION_SKU_CANDIDATE"
    if str(row.get("current_stock_position_label", "")) in {"OVERSTOCKED", "SEVERELY_OVERSTOCKED"}:
        return "SHADOW_OVERSTOCK_RUN_DOWN_CANDIDATE"
    if str(row.get("current_stock_position_label", "")) == "UNDERSTOCKED" and float(row.get("promo_convexity_score", 0)) >= 40:
        return "SHADOW_UNDERSTOCKED_CONVEXITY_CANDIDATE"
    if str(row.get("alpha_pattern_id", "")) == "UNKNOWN_DATA_DO_NOT_LEARN":
        return "SHADOW_DATA_REPAIR_ONLY"
    return "SHADOW_DATA_REPAIR_ONLY"


def _action_difference(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    governed = frame.get("final_governed_action_label", pd.Series("", index=frame.index)).astype(str)
    validated = frame.get("brain_validated_action_label", pd.Series("", index=frame.index)).astype(str)
    diff = governed.ne(validated) & validated.ne("") & validated.ne("VALIDATION_INSUFFICIENT")
    diff_flag = diff.map({True: "YES", False: "NO"})

    brain_aggressive = validated.isin(["AGGRESSIVE_BUY", "CONTROLLED_BUY", "TOP_UP_TO_OPTIMAL"]) & governed.isin(["HOLD", "DO_NOT_BUY", "REVIEW"])
    brain_conservative = validated.isin(["NO_BUY_RUN_DOWN", "HOLD_FOR_REPLENISHMENT"]) & governed.isin(["BUY", "REVIEW"])
    diff_type = pd.Series("ALIGNED", index=frame.index)
    diff_type = diff_type.mask(diff & brain_aggressive, "BRAIN_MORE_AGGRESSIVE")
    diff_type = diff_type.mask(diff & brain_conservative, "BRAIN_MORE_CONSERVATIVE")
    diff_type = diff_type.mask(diff & diff_type.eq("ALIGNED"), "ACTION_MISMATCH")

    questions = pd.Series("Does the brain align with governed buyer action?", index=frame.index)
    questions = questions.mask(
        frame.get("long_tail_mission_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES"),
        "Does the brain correctly protect long-tail mission SKU?",
    )
    questions = questions.mask(
        frame.get("current_stock_position_label", pd.Series("", index=frame.index)).astype(str).isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"]),
        "Does the brain identify run-down opportunity humans may miss?",
    )
    questions = questions.mask(
        (_numeric(frame, "promo_convexity_score") < 15) & diff,
        "Does the brain avoid overbuying weak-convexity SKU?",
    )
    questions = questions.mask(
        frame.get("basket_attachment_used_real_transactions_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES"),
        "Does basket attachment predict trust-sensitive demand?",
    )
    return diff_flag, diff_type, questions


def build_shadow_candidate_selection_frame(
    df: pd.DataFrame,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Select bias-controlled shadow observation candidates."""
    cfg = config or {}
    out = _attach_segment_bias(df, error_profile=cfg.get("error_profile_df"))
    out["shadow_expected_learning_value"] = _learning_value(out)
    out["shadow_data_quality_score"] = _data_quality_score(out)
    out["shadow_bias_risk_score"] = (
        _numeric(out, "segment_historical_wape").clip(0, 1) * 50
        + np.where(out["segment_bias_control_status"].eq("BIAS_DANGEROUS_BLOCK"), 40.0, 0.0)
        + np.where(out["segment_bias_control_status"].eq("BIAS_MODERATE_REVIEW"), 15.0, 0.0)
    ).clip(0, 100).round(1)
    out["shadow_economic_risk_score"] = (
        _numeric(out, "cash_tied_above_optimal_cost").clip(0, 1000) / 10.0
        + np.where(_numeric(out, "economic_net_value_score") < 0, 25.0, 0.0)
    ).clip(0, 100).round(1)

    reject = _reject_reasons(out)
    moderate_ok = (
        out["segment_bias_control_status"].eq("BIAS_MODERATE_REVIEW")
        & (_numeric(out, "economic_net_value_score").gt(20) | _numeric(out, "shadow_expected_learning_value").gt(40))
    )
    eligible = (
        reject.eq("")
        & out["segment_bias_control_status"].isin(["BIAS_CONTROLLED", "BIAS_MODERATE_REVIEW"])
        & (out["segment_bias_control_status"].eq("BIAS_CONTROLLED") | moderate_ok)
        & (_numeric(out, "economic_net_value_score").gt(0) | _numeric(out, "shadow_expected_learning_value").gt(25))
        & out["shadow_data_quality_score"].ge(40)
    )

    out["shadow_candidate_score"] = (
        _numeric(out, "shadow_expected_learning_value") * 0.45
        + _numeric(out, "brain_validated_expected_value").clip(-50, 100).clip(lower=0) * 0.25
        + out["shadow_data_quality_score"] * 0.2
        - out["shadow_bias_risk_score"] * 0.15
        - out["shadow_economic_risk_score"] * 0.1
    ).clip(0, 100).round(1)
    out.loc[~eligible, "shadow_candidate_score"] = 0.0

    ranked = out[eligible].sort_values("shadow_candidate_score", ascending=False, kind="mergesort")
    rank_map = {idx: r + 1 for r, idx in enumerate(ranked.index)}
    out["shadow_candidate_rank"] = out.index.map(rank_map).fillna(0).astype(int)
    out["shadow_candidate_flag"] = np.where(eligible, "YES", "NO")
    out["shadow_candidate_reason"] = np.where(
        eligible,
        "Bias-controlled segment with positive learning/economic signal.",
        reject.replace("", "NOT_ELIGIBLE"),
    )

    classes = []
    for idx, row in out.iterrows():
        classes.append(_classify_row(row, int(row.get("shadow_candidate_rank", 0))))
    out["shadow_candidate_class"] = classes

    top50 = out["shadow_candidate_rank"].between(1, 50)
    top100 = out["shadow_candidate_rank"].between(1, 100)
    out.loc[top50 & eligible, "shadow_candidate_class"] = "SHADOW_TOP_50_CANDIDATE"
    out.loc[top100 & ~top50 & eligible, "shadow_candidate_class"] = "SHADOW_TOP_100_CANDIDATE"

    out["shadow_candidate_bucket"] = np.select(
        [top50, top100, eligible],
        ["TOP_50", "TOP_100", "ELIGIBLE"],
        default="EXCLUDED",
    )
    diff_flag, diff_type, questions = _action_difference(out)
    out["action_difference_flag"] = diff_flag
    out["action_difference_type"] = diff_type
    out["expected_shadow_learning_question"] = questions
    out["shadow_observation_plan"] = np.where(
        eligible,
        "Internal shadow observation only; compare brain vs buyer; no auto-order.",
        "Not selected for shadow observation.",
    )
    return out


def apply_shadow_candidate_selection(
    frame: pd.DataFrame,
    *,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Apply shadow candidate fields without changing governed actions."""
    scored = build_shadow_candidate_selection_frame(frame, config=config)
    for col in OUTPUT_COLUMNS:
        if col not in scored.columns:
            scored[col] = UNKNOWN
    return scored


def build_shadow_candidate_summary(frame: pd.DataFrame) -> pd.DataFrame:
    eligible = frame.get("shadow_candidate_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    classes = frame.get("shadow_candidate_class", pd.Series("NOT_SHADOW_SAFE", index=frame.index)).astype(str)
    return pd.DataFrame([{
        "total_rows": int(len(frame)),
        "eligible_shadow_candidates": int(eligible.sum()),
        "top_50_candidates": int(classes.eq("SHADOW_TOP_50_CANDIDATE").sum()),
        "top_100_candidates": int(classes.isin(["SHADOW_TOP_50_CANDIDATE", "SHADOW_TOP_100_CANDIDATE"]).sum()),
        "mission_sku_candidates": int(classes.eq("SHADOW_MISSION_SKU_CANDIDATE").sum()),
        "overstock_run_down_candidates": int(classes.eq("SHADOW_OVERSTOCK_RUN_DOWN_CANDIDATE").sum()),
        "understocked_convexity_candidates": int(classes.eq("SHADOW_UNDERSTOCKED_CONVEXITY_CANDIDATE").sum()),
        "data_repair_only_count": int(classes.eq("SHADOW_DATA_REPAIR_ONLY").sum()),
        "not_shadow_safe_count": int(classes.eq("NOT_SHADOW_SAFE").sum()),
        "average_segment_bias": float(_numeric(frame, "segment_historical_bias_pct").mean()),
        "average_shadow_candidate_score": float(_numeric(frame.loc[eligible], "shadow_candidate_score").mean()) if eligible.any() else 0.0,
        "estimated_learning_value": float(_numeric(frame.loc[eligible], "shadow_expected_learning_value").sum()) if eligible.any() else 0.0,
        "estimated_economic_value": float(_numeric(frame.loc[eligible], "brain_validated_expected_value").sum()) if eligible.any() else 0.0,
        "release_recommendation": "NO_RELEASE",
    }])


def build_shadow_top_50(frame: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "store_number", "promotion_id", "promotion_name", "promotion_start_date", "promotion_end_date",
        "sku_number", "sku_description", "department", "shadow_candidate_class", "shadow_candidate_score",
        "shadow_candidate_rank", "final_governed_action_label", "final_governed_order_units",
        "brain_validated_action_label", "brain_validated_expected_value", "action_difference_type",
        "segment_historical_bias_pct", "segment_historical_wape", "economic_net_value_score",
        "shadow_expected_learning_value", "mission_sku_score", "long_tail_sku_flag",
        "basket_attachment_source_quality", "promo_start_soh_source_quality", "supplier_replenishment_regime",
        "expected_shadow_learning_question", "shadow_observation_plan",
    ]
    cols = [c for c in cols if c in frame.columns]
    top = frame[frame.get("shadow_candidate_class", pd.Series("", index=frame.index)).astype(str).eq("SHADOW_TOP_50_CANDIDATE")]
    top = top.sort_values("shadow_candidate_rank", kind="mergesort")
    out = top[cols].head(50).copy()
    if "promo_start_soh_source_quality" in out.columns:
        out = out.rename(columns={"promo_start_soh_source_quality": "stock_truth_quality"})
    if "final_governed_action_label" in out.columns:
        out = out.rename(columns={"final_governed_action_label": "current_governed_action"})
    if "final_governed_order_units" in out.columns:
        out = out.rename(columns={"final_governed_order_units": "current_governed_order_units"})
    return out


def build_rejection_reasons(frame: pd.DataFrame) -> pd.DataFrame:
    ineligible = frame.get("shadow_candidate_flag", pd.Series("NO", index=frame.index)).astype(str).eq("NO")
    reasons = frame.loc[ineligible, "shadow_candidate_reason"].astype(str)
    reasons = reasons[reasons.ne("Bias-controlled segment with positive learning/economic signal.")]
    counts = reasons.value_counts().reset_index()
    counts.columns = ["rejection_reason", "row_count"]
    return counts


def build_bias_controlled_segment_review(frame: pd.DataFrame, error_profile: pd.DataFrame | None = None) -> pd.DataFrame:
    if error_profile is not None and not error_profile.empty:
        prof = error_profile.copy()
        prof["candidate_count"] = 0
        if "regime_error_profile_key" in frame.columns:
            counts = frame[frame.get("shadow_candidate_flag", pd.Series("NO")).astype(str).eq("YES")].groupby("regime_error_profile_key").size()
            prof["candidate_count"] = prof["regime_error_profile_key"].map(counts).fillna(0).astype(int)
        prof["segment_bias_control_status"] = prof["bias_pct"].apply(lambda b: _segment_bias_status(float(b), 100.0)[0])
        return prof
    grouped = frame.groupby("segment_bias_control_status", dropna=False).agg(
        row_count=("sku_number", "count"),
        candidate_count=("shadow_candidate_flag", lambda s: int(s.eq("YES").sum())),
        average_bias=("segment_historical_bias_pct", "mean"),
        average_wape=("segment_historical_wape", "mean"),
        average_learning_value=("shadow_expected_learning_value", "mean"),
    ).reset_index()
    return grouped


def recommend_shadow_trial_gate(summary: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    top50 = int(summary.get("top_50_candidates", pd.Series([0])).iloc[0])
    eligible = int(summary.get("eligible_shadow_candidates", pd.Series([0])).iloc[0])
    avg_bias = float(summary.get("average_segment_bias", pd.Series([DEFAULT_MODEL_BIAS_PCT])).iloc[0])
    learn_val = float(summary.get("estimated_learning_value", pd.Series([0])).iloc[0])
    econ_val = float(summary.get("estimated_economic_value", pd.Series([0])).iloc[0])
    unsafe_excluded = int(frame.get("unsafe_flag", pd.Series("NO")).astype(str).eq("YES").sum())

    recommendation = "INTERNAL_DIAGNOSTIC_ONLY"
    reason = "Default internal diagnostics; customer release not earned."

    controlled_top50 = frame[
        frame.get("shadow_candidate_class", pd.Series("", index=frame.index)).astype(str).eq("SHADOW_TOP_50_CANDIDATE")
        & frame.get("segment_bias_control_status", pd.Series("", index=frame.index)).isin(["BIAS_CONTROLLED", "BIAS_MODERATE_REVIEW"])
    ]
    if top50 >= 50 and len(controlled_top50) >= 40 and learn_val > 0 and econ_val > 0:
        recommendation = "SHADOW_TOP_50_REVIEW"
        reason = "Top 50 bias-controlled candidates with positive learning and economic value; observation only."
    elif eligible >= 100 and learn_val > 0:
        recommendation = "SHADOW_TOP_100_REVIEW"
        reason = "Broader shadow queue for internal brain comparison."

    if avg_bias < BIAS_MODERATE_MIN or avg_bias > BIAS_MODERATE_MAX:
        recommendation = "INTERNAL_DIAGNOSTIC_ONLY"
        reason = f"Global bias ({avg_bias:.1f}%) outside moderate band; shadow capped."

    return pd.DataFrame([{
        "recommendation": recommendation,
        "top_50_candidates": top50,
        "eligible_candidates": eligible,
        "average_segment_bias": round(avg_bias, 3),
        "estimated_learning_value": round(learn_val, 3),
        "estimated_economic_value": round(econ_val, 3),
        "unsafe_rows_excluded": unsafe_excluded,
        "auto_order_created": "NO",
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": "model_bias_dangerously_negative" if avg_bias < BIAS_CONTROLLED_MIN else "brain_shadow_observation_only",
        "reason": reason,
    }])


def write_phase5s_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    if frame is None:
        source = apply_stock_truth_repair(load_stock_truth_source(rebuild=rebuild))
        source = apply_stock_outcome_optimisation(source, gate_recommendation="NO_RELEASE")
        source = apply_optimal_stock_learning(source, gate_recommendation="NO_RELEASE")
        working = simulate_stock_position_outcomes(source)
        _rg, regime_rec = load_regime_artifacts()
        regime = apply_regime_brain_decisioning(working, gate_recommendation=regime_rec)
        prof, conv_rec = load_conviction_artifacts()
        calibrated = apply_conviction_calibration(
            regime, error_profile_df=prof if not prof.empty else None, gate_recommendation=conv_rec, model_bias_pct=model_bias_pct,
        )
        triage_rec = load_triage_artifacts()
        triaged = apply_promo_decision_triage(calibrated, gate_recommendation=triage_rec, model_bias_pct=model_bias_pct)
        basket = apply_basket_attachment_to_promo_frame(triaged)
        econ_rec = load_economic_artifacts()
        enriched = apply_promo_economic_value_scoring(basket, gate_recommendation=econ_rec, model_bias_pct=model_bias_pct)
        enriched = apply_brain_feature_learning(enriched)
        enriched = apply_brain_leakage_validation(enriched, config={"skip_full_validation": True})
    else:
        enriched = frame

    profile = build_regime_error_profile(enriched, enriched)
    selected = apply_shadow_candidate_selection(enriched, config={"error_profile_df": profile})
    summary = build_shadow_candidate_summary(selected)

    summary.to_csv(diagnostics_dir / "phase5s01_shadow_candidate_summary.csv", index=False)
    build_shadow_top_50(selected).to_csv(diagnostics_dir / "phase5s01_shadow_top_50_candidates.csv", index=False)
    build_rejection_reasons(selected).to_csv(diagnostics_dir / "phase5s01_shadow_candidate_rejection_reasons.csv", index=False)
    build_bias_controlled_segment_review(selected, error_profile=profile).to_csv(
        diagnostics_dir / "phase5s01_bias_controlled_segment_review.csv", index=False
    )
    gate = recommend_shadow_trial_gate(summary, selected)
    gate.to_csv(diagnostics_dir / "phase5s01_shadow_trial_gate.csv", index=False)

    quality = _quality_col(selected)
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in selected.columns else "promo_demand_release_ready_flag"
    eligible = selected.get("shadow_candidate_flag", pd.Series("NO")).astype(str).eq("YES")

    return {
        "eligible_shadow_candidates": int(eligible.sum()),
        "top_50_candidate_count": int(summary["top_50_candidates"].iloc[0]),
        "top_100_candidate_count": int(summary["top_100_candidates"].iloc[0]),
        "average_candidate_bias": float(summary["average_segment_bias"].iloc[0]),
        "estimated_economic_value": float(summary["estimated_economic_value"].iloc[0]),
        "estimated_learning_value": float(summary["estimated_learning_value"].iloc[0]),
        "mission_sku_candidate_count": int(summary["mission_sku_candidates"].iloc[0]),
        "overstock_run_down_candidate_count": int(summary["overstock_run_down_candidates"].iloc[0]),
        "understocked_convexity_candidate_count": int(summary["understocked_convexity_candidates"].iloc[0]),
        "shadow_trial_recommendation": str(gate["recommendation"].iloc[0]),
        "release_ready_rows": int(selected.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "unsafe_rows": int(selected.get(quality, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": str(gate["primary_blocker"].iloc[0]),
    }


def run_phase5s01_shadow_candidate_selection(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR, rebuild: bool = False) -> dict[str, Any]:
    return write_phase5s_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)
