from __future__ import annotations

"""Phase 5V — lesson-weighted brain update and governance threshold review."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_brain_feature_learning import FEATURE_FAMILIES
from models.promotions.promo_conviction_calibration import DEFAULT_MODEL_BIAS_PCT
from models.promotions.promo_shadow_observation_journal import (
    HUMAN_FILLED_FILENAME,
    LESSON_LEARNED_LABELS,
    PHASE5U_DIAGNOSTICS_DIR,
)

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5v01_lesson_weighted_updates")
PHASE5U_SCORED_PATH = PHASE5U_DIAGNOSTICS_DIR / "phase5u01_shadow_scored_outcomes.csv"
PHASE5U_SCORECARD_PATH = PHASE5U_DIAGNOSTICS_DIR / "phase5u01_brain_vs_human_scorecard.csv"
PHASE5U_HUMAN_SUMMARY_PATH = PHASE5U_DIAGNOSTICS_DIR / "phase5u01_human_review_ingestion_summary.csv"
PHASE5T_DIAGNOSTICS_DIR = Path("Diagnostics/phase5t01_shadow_observation_journal")
HUMAN_FILLED_PATH = PHASE5T_DIAGNOSTICS_DIR / HUMAN_FILLED_FILENAME

BRAIN_UPDATE_TYPES = (
    "INCREASE_FEATURE_WEIGHT",
    "DECREASE_FEATURE_WEIGHT",
    "REVIEW_ACTION_CLASSIFIER",
    "REVIEW_TARGET_LABEL_LOGIC",
    "REVIEW_LONG_TAIL_VALUE_MODEL",
    "REVIEW_SUPPLIER_RISK_MODEL",
    "REVIEW_STOCK_TRUTH_MODEL",
    "NO_MODEL_UPDATE_DATA_INSUFFICIENT",
)

GOVERNANCE_RECOMMENDATIONS = (
    "KEEP",
    "REVIEW_FOR_RELAXATION",
    "REVIEW_FOR_TIGHTENING",
    "REQUIRE_MORE_EVIDENCE",
    "BLOCK_CHANGE",
)

LESSON_WEIGHT_CONFIG: dict[str, dict[str, Any]] = {
    "LONG_TAIL_PROTECTION_CONFIRMED": {
        "lesson_weight": 1.25,
        "brain_positive_reinforcement_weight": 0.20,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "YES",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "REVIEW_LONG_TAIL_VALUE_MODEL",
        "governance_update_recommendation": "MAINTAIN_LONG_TAIL_MIN_SOH",
        "long_tail_update_recommendation": "INCREASE_PROTECTION_PRIORITY_CAPPED",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "MAINTAIN_BASKET_EVIDENCE",
        "next_learning_action": "REINFORCE_BASKET_TRUST_FEATURES",
        "feature_family": "basket_trust",
        "brain_update_type": "INCREASE_FEATURE_WEIGHT",
        "weight_direction": "UP",
    },
    "BRAIN_WRONG_HUMAN_RIGHT": {
        "lesson_weight": 1.15,
        "brain_positive_reinforcement_weight": 0.0,
        "brain_negative_reinforcement_weight": 0.25,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "YES",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "REVIEW_ACTION_CLASSIFIER",
        "governance_update_recommendation": "MAINTAIN_HUMAN_REVIEW",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_HUMAN_REVIEW",
        "data_quality_update_recommendation": "NONE",
        "next_learning_action": "PENALISE_BRAIN_ACTION_PATTERN",
        "feature_family": "action_classifier",
        "brain_update_type": "REVIEW_ACTION_CLASSIFIER",
        "weight_direction": "DOWN",
    },
    "GOVERNANCE_TOO_CONSERVATIVE": {
        "lesson_weight": 1.10,
        "brain_positive_reinforcement_weight": 0.05,
        "brain_negative_reinforcement_weight": 0.10,
        "governance_relaxation_candidate_flag": "YES",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "YES",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "REVIEW_UNDERSTOCK_SEGMENTS",
        "governance_update_recommendation": "REVIEW_THRESHOLDS_NOT_AUTO_RELAX",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "REVIEW_GOVERNANCE_WITH_HUMAN",
        "data_quality_update_recommendation": "NONE",
        "next_learning_action": "REVIEW_GOVERNANCE_THRESHOLDS",
        "feature_family": "stock_optimal",
        "brain_update_type": "REVIEW_TARGET_LABEL_LOGIC",
        "weight_direction": "REVIEW",
    },
    "BRAIN_RIGHT_HUMAN_WRONG": {
        "lesson_weight": 1.05,
        "brain_positive_reinforcement_weight": 0.15,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "YES",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "REINFORCE_BRAIN_PATTERN_REVIEW_REQUIRED",
        "governance_update_recommendation": "NO_AUTO_CHANGE",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_HUMAN_REVIEW",
        "data_quality_update_recommendation": "NONE",
        "next_learning_action": "REINFORCE_BRAIN_WITH_REVIEW",
        "feature_family": "action_classifier",
        "brain_update_type": "INCREASE_FEATURE_WEIGHT",
        "weight_direction": "UP",
    },
    "BRAIN_RIGHT_HUMAN_RIGHT": {
        "lesson_weight": 1.0,
        "brain_positive_reinforcement_weight": 0.05,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "MONITOR_ALIGNED_PATTERN",
        "governance_update_recommendation": "MONITOR",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "NONE",
        "next_learning_action": "MONITOR",
        "feature_family": "action_classifier",
        "brain_update_type": "NO_MODEL_UPDATE_DATA_INSUFFICIENT",
        "weight_direction": "NONE",
    },
    "BOTH_WRONG": {
        "lesson_weight": 1.20,
        "brain_positive_reinforcement_weight": 0.0,
        "brain_negative_reinforcement_weight": 0.15,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "YES",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "YES",
        "data_quality_repair_priority_flag": "YES",
        "brain_update_recommendation": "REVIEW_ALL_ACTORS",
        "governance_update_recommendation": "REVIEW_GOVERNANCE",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_HUMAN_REVIEW",
        "data_quality_update_recommendation": "REVIEW_DATA_QUALITY",
        "next_learning_action": "STRUCTURAL_REVIEW",
        "feature_family": "multi_family",
        "brain_update_type": "REVIEW_TARGET_LABEL_LOGIC",
        "weight_direction": "REVIEW",
    },
    "DATA_QUALITY_BLOCKED_LEARNING": {
        "lesson_weight": 0.50,
        "brain_positive_reinforcement_weight": 0.0,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "YES",
        "brain_update_recommendation": "NO_MODEL_UPDATE_DATA_INSUFFICIENT",
        "governance_update_recommendation": "BLOCK_CHANGE",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "REPAIR_SOURCE_QUALITY",
        "next_learning_action": "REPAIR_DATA_BEFORE_LEARNING",
        "feature_family": "data_quality",
        "brain_update_type": "NO_MODEL_UPDATE_DATA_INSUFFICIENT",
        "weight_direction": "NONE",
    },
    "SUPPLIER_FAILURE": {
        "lesson_weight": 0.75,
        "brain_positive_reinforcement_weight": 0.0,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "YES",
        "brain_update_recommendation": "NO_MODEL_FAILURE",
        "governance_update_recommendation": "REVIEW_SUPPLIER_DATA",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "REVIEW_SUPPLIER_DATA",
        "next_learning_action": "REVIEW_SUPPLIER_RISK",
        "feature_family": "supplier_replenishment",
        "brain_update_type": "REVIEW_SUPPLIER_RISK_MODEL",
        "weight_direction": "REVIEW",
    },
    "CENSORED_BY_STOCKOUT": {
        "lesson_weight": 0.40,
        "brain_positive_reinforcement_weight": 0.0,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "YES",
        "brain_update_recommendation": "NO_CLEAN_TRAINING_TARGET",
        "governance_update_recommendation": "MAINTAIN_GOVERNANCE",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "REPAIR_SOH_TRUTH",
        "next_learning_action": "EXCLUDE_FROM_TRAINING",
        "feature_family": "stock_optimal",
        "brain_update_type": "REVIEW_STOCK_TRUTH_MODEL",
        "weight_direction": "REVIEW",
    },
    "INSUFFICIENT_OUTCOME_SIGNAL": {
        "lesson_weight": 0.30,
        "brain_positive_reinforcement_weight": 0.0,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "YES",
        "brain_update_recommendation": "NO_MODEL_UPDATE_DATA_INSUFFICIENT",
        "governance_update_recommendation": "MONITOR",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "REPAIR_DEMAND_ACTUALS",
        "next_learning_action": "WAIT_FOR_OUTCOMES",
        "feature_family": "demand_uplift",
        "brain_update_type": "NO_MODEL_UPDATE_DATA_INSUFFICIENT",
        "weight_direction": "NONE",
    },
    "BASKET_TRUST_SIGNAL_CONFIRMED": {
        "lesson_weight": 1.20,
        "brain_positive_reinforcement_weight": 0.18,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "YES",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "REINFORCE_BASKET_FEATURES",
        "governance_update_recommendation": "MAINTAIN_GOVERNANCE",
        "long_tail_update_recommendation": "INCREASE_PROTECTION_PRIORITY_CAPPED",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "MAINTAIN_BASKET_EVIDENCE",
        "next_learning_action": "REINFORCE_BASKET_TRUST",
        "feature_family": "basket_trust",
        "brain_update_type": "INCREASE_FEATURE_WEIGHT",
        "weight_direction": "UP",
    },
    "GOVERNANCE_RIGHT_BRAIN_TOO_AGGRESSIVE": {
        "lesson_weight": 1.10,
        "brain_positive_reinforcement_weight": 0.0,
        "brain_negative_reinforcement_weight": 0.20,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "YES",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "YES",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "REDUCE_BRAIN_AGGRESSION",
        "governance_update_recommendation": "MAINTAIN_GOVERNANCE",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_HUMAN_REVIEW",
        "data_quality_update_recommendation": "NONE",
        "next_learning_action": "TIGHTEN_BRAIN_AGGRESSION",
        "feature_family": "action_classifier",
        "brain_update_type": "DECREASE_FEATURE_WEIGHT",
        "weight_direction": "DOWN",
    },
    "OVERSTOCK_RUN_DOWN_CONFIRMED": {
        "lesson_weight": 1.05,
        "brain_positive_reinforcement_weight": 0.10,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "NO",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "REINFORCE_RUN_DOWN_ACTIONS",
        "governance_update_recommendation": "MAINTAIN_CASH_RELEASE_QUEUE",
        "long_tail_update_recommendation": "NO_CHANGE",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "NONE",
        "next_learning_action": "REINFORCE_RUN_DOWN",
        "feature_family": "stock_optimal",
        "brain_update_type": "REVIEW_TARGET_LABEL_LOGIC",
        "weight_direction": "REVIEW",
    },
    "MISSION_SKU_SIGNAL_CONFIRMED": {
        "lesson_weight": 1.30,
        "brain_positive_reinforcement_weight": 0.22,
        "brain_negative_reinforcement_weight": 0.0,
        "governance_relaxation_candidate_flag": "NO",
        "governance_tightening_candidate_flag": "NO",
        "long_tail_reinforcement_flag": "YES",
        "human_review_reinforcement_flag": "NO",
        "data_quality_repair_priority_flag": "NO",
        "brain_update_recommendation": "REINFORCE_MISSION_SKU_FEATURES",
        "governance_update_recommendation": "MAINTAIN_LONG_TAIL_MIN_SOH",
        "long_tail_update_recommendation": "INCREASE_PROTECTION_PRIORITY_CAPPED",
        "human_review_policy_recommendation": "MAINTAIN_REVIEW",
        "data_quality_update_recommendation": "MAINTAIN_BASKET_EVIDENCE",
        "next_learning_action": "REINFORCE_MISSION_SKU",
        "feature_family": "basket_trust",
        "brain_update_type": "INCREASE_FEATURE_WEIGHT",
        "weight_direction": "UP",
    },
}

DEFAULT_LESSON_CONFIG = {
    "lesson_weight": 0.80,
    "brain_positive_reinforcement_weight": 0.0,
    "brain_negative_reinforcement_weight": 0.0,
    "governance_relaxation_candidate_flag": "NO",
    "governance_tightening_candidate_flag": "NO",
    "long_tail_reinforcement_flag": "NO",
    "human_review_reinforcement_flag": "NO",
    "data_quality_repair_priority_flag": "NO",
    "brain_update_recommendation": "MONITOR",
    "governance_update_recommendation": "MONITOR",
    "long_tail_update_recommendation": "NO_CHANGE",
    "human_review_policy_recommendation": "MAINTAIN_REVIEW",
    "data_quality_update_recommendation": "NONE",
    "next_learning_action": "MONITOR",
    "feature_family": "unknown",
    "brain_update_type": "NO_MODEL_UPDATE_DATA_INSUFFICIENT",
    "weight_direction": "NONE",
}

ADVISORY_COLUMNS = (
    "lesson_weight",
    "brain_positive_reinforcement_weight",
    "brain_negative_reinforcement_weight",
    "governance_relaxation_candidate_flag",
    "governance_tightening_candidate_flag",
    "long_tail_reinforcement_flag",
    "human_review_reinforcement_flag",
    "data_quality_repair_priority_flag",
    "brain_update_recommendation",
    "governance_update_recommendation",
    "long_tail_update_recommendation",
    "human_review_policy_recommendation",
    "data_quality_update_recommendation",
    "next_learning_action",
)


def _numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _lesson_config(label: str) -> dict[str, Any]:
    return LESSON_WEIGHT_CONFIG.get(str(label).strip(), DEFAULT_LESSON_CONFIG)


def _affected_features(family: str, row: pd.Series | None = None) -> str:
    features = FEATURE_FAMILIES.get(family, ())
    if row is not None:
        top = [str(row.get(c, "")) for c in ("brain_top_feature_1", "brain_top_feature_2", "brain_top_feature_3")]
        top = [f for f in top if f and f != "nan"]
        if top:
            return ";".join(top[:3])
    return ";".join(features[:5]) if features else "none"


def build_lesson_weighted_training_frame(
    scored_df: pd.DataFrame,
    enriched_df: pd.DataFrame | None = None,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build lesson-weighted advisory training frame from Phase 5U scored outcomes."""
    del config
    if scored_df.empty:
        return pd.DataFrame(columns=list(scored_df.columns) + list(ADVISORY_COLUMNS))

    frame = scored_df.copy()
    if enriched_df is not None and not enriched_df.empty:
        merge_cols = [c for c in ("store_number", "promotion_id", "sku_number") if c in frame.columns and c in enriched_df.columns]
        enrich_cols = [c for c in enriched_df.columns if c not in frame.columns or c in merge_cols]
        if merge_cols:
            left = frame.copy()
            right = enriched_df[enrich_cols].drop_duplicates(subset=merge_cols, keep="first").copy()
            for col in merge_cols:
                left[col] = left[col].astype(str)
                right[col] = right[col].astype(str)
            frame = left.merge(right, on=merge_cols, how="left", suffixes=("", "_enrich"))

    labels = frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str)
    for col in ADVISORY_COLUMNS:
        frame[col] = pd.Series([None] * len(frame), index=frame.index, dtype=object)

    for idx, label in labels.items():
        cfg = _lesson_config(label)
        for key in ADVISORY_COLUMNS:
            frame.at[idx, key] = cfg.get(key, DEFAULT_LESSON_CONFIG.get(key, ""))

    return frame


def derive_brain_update_weights(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive brain model update recommendations from lesson-weighted frame."""
    if frame.empty:
        return pd.DataFrame(columns=[
            "lesson_label", "row_count", "affected_feature_family", "affected_features",
            "recommended_update_type", "recommended_weight_direction", "confidence",
            "evidence_note", "risk_note",
        ])

    rows = []
    grouped = frame.groupby("lesson_learned_label", dropna=False)
    for label, grp in grouped:
        cfg = _lesson_config(str(label))
        sample = grp.iloc[0]
        row_count = int(len(grp))
        confidence = "HIGH" if row_count >= 15 else "MEDIUM" if row_count >= 5 else "LOW"
        if str(label) in {"DATA_QUALITY_BLOCKED_LEARNING", "INSUFFICIENT_OUTCOME_SIGNAL", "CENSORED_BY_STOCKOUT"}:
            confidence = "LOW"
        rows.append({
            "lesson_label": label,
            "row_count": row_count,
            "affected_feature_family": cfg["feature_family"],
            "affected_features": _affected_features(cfg["feature_family"], sample),
            "recommended_update_type": cfg["brain_update_type"],
            "recommended_weight_direction": cfg["weight_direction"],
            "confidence": confidence,
            "evidence_note": str(sample.get("lesson_learned_note", "")),
            "risk_note": (
                "Advisory only; no automatic model weight change."
                if cfg["brain_update_type"] != "NO_MODEL_UPDATE_DATA_INSUFFICIENT"
                else "Insufficient clean signal; do not train on these rows."
            ),
        })
    return pd.DataFrame(rows).sort_values("row_count", ascending=False)


def derive_governance_threshold_recommendations(
    frame: pd.DataFrame,
    *,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> pd.DataFrame:
    """Review governance thresholds based on shadow outcome evidence."""
    rows: list[dict[str, Any]] = []
    n = len(frame)
    human_wins = int(frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str).eq("BRAIN_WRONG_HUMAN_RIGHT").sum())
    gov_conservative = int(frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str).eq("GOVERNANCE_TOO_CONSERVATIVE").sum())
    long_tail = int(frame.get("long_tail_reinforcement_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES").sum())
    value_at_risk = float(_numeric(frame.get("brain_validated_expected_value", pd.Series(0, index=frame.index))).sum())

    rows.append({
        "governance_rule": "model_bias_release_gate",
        "current_threshold": f"bias_pct<={abs(model_bias_pct):.1f}%",
        "recommended_direction": "KEEP",
        "affected_rows": n,
        "evidence_label": "aggregate_bias_still_dangerous",
        "estimated_value_at_risk": round(value_at_risk, 2),
        "estimated_risk_if_relaxed": "HIGH",
        "recommendation": "BLOCK_CHANGE",
        "requires_human_approval_flag": "YES",
    })
    rows.append({
        "governance_rule": "long_tail_review_priority_weight",
        "current_threshold": "baseline",
        "recommended_direction": "UP" if long_tail >= 10 else "HOLD",
        "affected_rows": long_tail,
        "evidence_label": "LONG_TAIL_PROTECTION_CONFIRMED",
        "estimated_value_at_risk": float(_numeric(frame.get("shadow_expected_learning_value", pd.Series(0, index=frame.index))).sum()),
        "estimated_risk_if_relaxed": "MEDIUM",
        "recommendation": "REVIEW_FOR_RELAXATION" if long_tail >= 10 else "REQUIRE_MORE_EVIDENCE",
        "requires_human_approval_flag": "YES",
    })
    rows.append({
        "governance_rule": "governance_conservative_buy_threshold",
        "current_threshold": "governed_action_cap",
        "recommended_direction": "REVIEW",
        "affected_rows": gov_conservative,
        "evidence_label": "GOVERNANCE_TOO_CONSERVATIVE",
        "estimated_value_at_risk": float(
            _numeric(frame.loc[frame.get("lesson_learned_label", "").astype(str).eq("GOVERNANCE_TOO_CONSERVATIVE"), "brain_validated_expected_value"]).sum()
        ) if gov_conservative else 0.0,
        "estimated_risk_if_relaxed": "HIGH",
        "recommendation": "REVIEW_FOR_RELAXATION" if gov_conservative >= 10 else "REQUIRE_MORE_EVIDENCE",
        "requires_human_approval_flag": "YES",
    })
    rows.append({
        "governance_rule": "buyer_review_required_threshold",
        "current_threshold": "human_review_mandatory",
        "recommended_direction": "KEEP",
        "affected_rows": human_wins,
        "evidence_label": "BRAIN_WRONG_HUMAN_RIGHT",
        "estimated_value_at_risk": 0.0,
        "estimated_risk_if_relaxed": "HIGH",
        "recommendation": "KEEP" if human_wins >= 10 else "REQUIRE_MORE_EVIDENCE",
        "requires_human_approval_flag": "YES",
    })
    rows.append({
        "governance_rule": "shadow_operational_trial_gate",
        "current_threshold": "NO_RELEASE",
        "recommended_direction": "KEEP",
        "affected_rows": n,
        "evidence_label": "shadow_top_100_review_only",
        "estimated_value_at_risk": 0.0,
        "estimated_risk_if_relaxed": "HIGH",
        "recommendation": "BLOCK_CHANGE",
        "requires_human_approval_flag": "YES",
    })
    return pd.DataFrame(rows)


def derive_human_review_policy_recommendations(frame: pd.DataFrame, scorecard: pd.DataFrame | None = None) -> pd.DataFrame:
    """Derive human review policy recommendations from scored lessons."""
    if scorecard is not None and not scorecard.empty:
        sc = scorecard.iloc[0]
        brain_wins = int(sc.get("brain_wins", 0))
        human_wins = int(sc.get("human_wins", 0))
        governed_wins = int(sc.get("governed_wins", 0))
        unscorable = int(sc.get("unscorable_rows", 0))
    else:
        labels = frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str)
        brain_wins = int(labels.isin(["BRAIN_RIGHT_HUMAN_WRONG", "MISSION_SKU_SIGNAL_CONFIRMED"]).sum())
        human_wins = int(labels.eq("BRAIN_WRONG_HUMAN_RIGHT").sum())
        governed_wins = int(labels.isin(["GOVERNANCE_RIGHT_BRAIN_TOO_AGGRESSIVE", "GOVERNANCE_TOO_CONSERVATIVE"]).sum())
        unscorable = int(frame.get("brain_action_correctness_label", pd.Series("", index=frame.index)).astype(str).eq("UNSCORABLE").sum())

    human_beat = frame.loc[
        frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str).eq("BRAIN_WRONG_HUMAN_RIGHT"),
        "sku_number",
    ].astype(str).head(5).tolist() if not frame.empty else []
    brain_watch = frame.loc[
        frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str).eq("BRAIN_RIGHT_HUMAN_WRONG"),
        "sku_number",
    ].astype(str).head(5).tolist() if not frame.empty else []

    return pd.DataFrame([{
        "human_wins": human_wins,
        "brain_wins": brain_wins,
        "governed_wins": governed_wins,
        "unscorable": unscorable,
        "review_required_recommendation": "MAINTAIN_HUMAN_REVIEW",
        "review_queue_change_recommendation": "CONTINUE_TOP_100_SHADOW_REVIEW",
        "where_human_still_beats_brain": ";".join(human_beat) if human_beat else "BRAIN_WRONG_HUMAN_RIGHT_segments",
        "where_brain_should_be_watched_more_closely": ";".join(brain_watch) if brain_watch else "BRAIN_RIGHT_HUMAN_WRONG_segments",
        "operational_trial_recommendation": "DO_NOT_MOVE_TO_OPERATIONAL_TRIAL",
    }])


def build_long_tail_reinforcement_review(frame: pd.DataFrame) -> pd.DataFrame:
    """Review long-tail basket trust reinforcement from shadow lessons."""
    long_tail_mask = frame.get("long_tail_sku_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES")
    confirmed = frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str).isin(
        {"LONG_TAIL_PROTECTION_CONFIRMED", "BASKET_TRUST_SIGNAL_CONFIRMED", "MISSION_SKU_SIGNAL_CONFIRMED"}
    )
    false_positive = long_tail_mask & ~confirmed & frame.get("actual_outcome_quality", pd.Series("", index=frame.index)).astype(str).eq("HIGH")
    mission_confirmed = frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str).eq("MISSION_SKU_SIGNAL_CONFIRMED").sum()
    trust_before = float(_numeric(frame.get("long_tail_protection_value", pd.Series(0, index=frame.index))).mean())
    confirmed_count = int(confirmed.sum())
    adjustment = min(0.15, 0.05 + confirmed_count * 0.002) if confirmed_count >= 10 else 0.0
    top_skus = (
        frame.loc[confirmed, "sku_number"].astype(str).value_counts().head(5).index.tolist()
        if confirmed.any() else []
    )
    recommendation = (
        "INCREASE_REVIEW_PRIORITY_WITHIN_CAPS"
        if confirmed_count >= 10
        else "REQUIRE_MORE_EVIDENCE"
    )
    return pd.DataFrame([{
        "long_tail_rows_scored": int(long_tail_mask.sum()),
        "long_tail_confirmed_count": confirmed_count,
        "long_tail_false_positive_count": int(false_positive.sum()),
        "mission_sku_confirmed_count": int(mission_confirmed),
        "basket_trust_value_before": round(trust_before, 3),
        "basket_trust_value_recommended_adjustment": round(adjustment, 3),
        "top_confirmed_long_tail_skus": ";".join(top_skus),
        "recommendation": recommendation,
    }])


def build_data_quality_update_priorities(
    frame: pd.DataFrame,
    *,
    human_review_complete_rate: float = 0.0,
) -> pd.DataFrame:
    """Prioritise data gaps that block shadow learning."""
    rows: list[dict[str, Any]] = []
    n = len(frame)

    if human_review_complete_rate <= 0.0 and not HUMAN_FILLED_PATH.exists():
        rows.append({
            "data_issue": "missing_filled_human_review_file",
            "affected_rows": n,
            "learning_blocked_value": float(_numeric(frame.get("shadow_expected_learning_value", pd.Series(0, index=frame.index))).sum()),
            "recommended_fix": f"Complete {HUMAN_FILLED_FILENAME} for shadow_run_id keys",
            "priority": "HIGH",
        })

    unknown_soh = int(frame.get("actual_start_soh", pd.Series(np.nan, index=frame.index)).isna().sum()) if "actual_start_soh" in frame.columns else 0
    if unknown_soh:
        rows.append({
            "data_issue": "unknown_soh",
            "affected_rows": unknown_soh,
            "learning_blocked_value": float(_numeric(frame.get("brain_validated_expected_value", pd.Series(0, index=frame.index))).sum()),
            "recommended_fix": "Repair promo_start_soh_resolved and stock truth",
            "priority": "HIGH" if unknown_soh >= 10 else "MEDIUM",
        })

    unknown_basket = int(
        frame.get("basket_attachment_source_quality", pd.Series("UNKNOWN", index=frame.index)).astype(str).isin({"UNKNOWN", "LOW"}).sum()
    ) if "basket_attachment_source_quality" in frame.columns else 0
    if unknown_basket:
        rows.append({
            "data_issue": "unknown_basket_evidence",
            "affected_rows": unknown_basket,
            "learning_blocked_value": float(_numeric(frame.get("feature_avg_basket_gp_when_present", pd.Series(0, index=frame.index))).sum()),
            "recommended_fix": "Improve basket attachment evidence coverage",
            "priority": "MEDIUM",
        })

    supplier_uncertainty = int(frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str).eq("SUPPLIER_FAILURE").sum())
    if supplier_uncertainty:
        rows.append({
            "data_issue": "supplier_uncertainty",
            "affected_rows": supplier_uncertainty,
            "learning_blocked_value": 0.0,
            "recommended_fix": "Track supplier availability separately from model error",
            "priority": "MEDIUM",
        })

    censored = int(frame.get("lesson_learned_label", pd.Series("", index=frame.index)).astype(str).eq("CENSORED_BY_STOCKOUT").sum())
    if censored:
        rows.append({
            "data_issue": "censored_demand",
            "affected_rows": censored,
            "learning_blocked_value": float(_numeric(frame.get("actual_lost_sales_proxy", pd.Series(0, index=frame.index))).sum()),
            "recommended_fix": "Exclude censored rows from clean training targets",
            "priority": "MEDIUM",
        })

    dq_blocked = int(frame.get("data_quality_repair_priority_flag", pd.Series("NO", index=frame.index)).astype(str).eq("YES").sum())
    if dq_blocked:
        rows.append({
            "data_issue": "data_quality_blocked_learning",
            "affected_rows": dq_blocked,
            "learning_blocked_value": float(_numeric(frame.get("shadow_expected_learning_value", pd.Series(0, index=frame.index))).sum()),
            "recommended_fix": "Repair source quality before lesson-weighted training",
            "priority": "HIGH",
        })

    unscorable = int(frame.get("brain_action_correctness_label", pd.Series("", index=frame.index)).astype(str).eq("UNSCORABLE").sum())
    if unscorable:
        rows.append({
            "data_issue": "unscorable_outcomes",
            "affected_rows": unscorable,
            "learning_blocked_value": 0.0,
            "recommended_fix": "Improve actual outcome merge completeness",
            "priority": "LOW",
        })

    if not rows:
        rows.append({
            "data_issue": "none_identified",
            "affected_rows": 0,
            "learning_blocked_value": 0.0,
            "recommended_fix": "MONITOR",
            "priority": "LOW",
        })
    return pd.DataFrame(rows).sort_values(["priority", "affected_rows"], ascending=[True, False])


def build_phase5v_release_gate(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{
        "recommendation": "NO_RELEASE",
        "shadow_recommendation": "SHADOW_TOP_100_REVIEW",
        "lesson_rows_processed": int(len(frame)),
        "auto_order_created": "NO",
        "governed_actions_overwritten": "NO",
        "production_predictions_overwritten": "NO",
        "primary_blocker": "model_bias_dangerously_negative",
        "reason": "Lesson-weighted updates are advisory only; customer release not earned.",
    }])


def write_phase5v_diagnostics(
    *,
    scored_df: pd.DataFrame | None = None,
    enriched_df: pd.DataFrame | None = None,
    scorecard_df: pd.DataFrame | None = None,
    human_summary_df: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    model_bias_pct: float = DEFAULT_MODEL_BIAS_PCT,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    if scored_df is None:
        if not PHASE5U_SCORED_PATH.exists():
            raise FileNotFoundError(f"Phase 5U scored outcomes not found: {PHASE5U_SCORED_PATH}")
        scored_df = pd.read_csv(PHASE5U_SCORED_PATH)
    if scorecard_df is None and PHASE5U_SCORECARD_PATH.exists():
        scorecard_df = pd.read_csv(PHASE5U_SCORECARD_PATH)
    if human_summary_df is None and PHASE5U_HUMAN_SUMMARY_PATH.exists():
        human_summary_df = pd.read_csv(PHASE5U_HUMAN_SUMMARY_PATH)

    frame = build_lesson_weighted_training_frame(scored_df, enriched_df=enriched_df)
    brain_updates = derive_brain_update_weights(frame)
    governance_review = derive_governance_threshold_recommendations(frame, model_bias_pct=model_bias_pct)
    human_policy = derive_human_review_policy_recommendations(frame, scorecard=scorecard_df)
    long_tail_review = build_long_tail_reinforcement_review(frame)
    human_rate = float(human_summary_df["human_review_completion_rate"].iloc[0]) if human_summary_df is not None and not human_summary_df.empty else 0.0
    data_quality = build_data_quality_update_priorities(frame, human_review_complete_rate=human_rate)
    gate = build_phase5v_release_gate(frame)

    brain_updates.to_csv(diagnostics_dir / "phase5v01_brain_update_recommendations.csv", index=False)
    governance_review.to_csv(diagnostics_dir / "phase5v01_governance_threshold_review.csv", index=False)
    long_tail_review.to_csv(diagnostics_dir / "phase5v01_long_tail_reinforcement_review.csv", index=False)
    human_policy.to_csv(diagnostics_dir / "phase5v01_human_review_policy.csv", index=False)
    data_quality.to_csv(diagnostics_dir / "phase5v01_data_quality_update_priorities.csv", index=False)
    frame.to_csv(diagnostics_dir / "phase5v01_lesson_weighted_training_frame.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5v01_release_gate.csv", index=False)

    top_dq = data_quality.sort_values("priority").head(3)["data_issue"].tolist()
    top_brain = brain_updates["recommended_update_type"].head(5).tolist() if not brain_updates.empty else []
    top_gov = governance_review["recommendation"].tolist() if not governance_review.empty else []

    return {
        "lesson_rows_processed": int(len(frame)),
        "brain_update_recommendations": top_brain,
        "governance_threshold_recommendations": top_gov,
        "long_tail_reinforcement_recommendation": str(long_tail_review.iloc[0]["recommendation"]) if not long_tail_review.empty else "",
        "human_review_policy_recommendation": str(human_policy.iloc[0]["review_required_recommendation"]) if not human_policy.empty else "MAINTAIN_HUMAN_REVIEW",
        "top_data_quality_priorities": top_dq,
        "release_recommendation": "NO_RELEASE",
        "primary_blocker": "model_bias_dangerously_negative",
    }


def run_phase5v01_lesson_weighted_updates(*, diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR) -> dict[str, Any]:
    return write_phase5v_diagnostics(diagnostics_dir=diagnostics_dir)
