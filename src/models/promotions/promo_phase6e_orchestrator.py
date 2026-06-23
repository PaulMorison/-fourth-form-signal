from __future__ import annotations

"""Phase 6E orchestrator — feature merge, ATS evidence, calibration eligibility."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_adjacent_path_simulation import assign_adjacent_path_policies
from models.promotions.promo_available_to_sell_evidence import write_phase6e_ats_diagnostics
from models.promotions.promo_bias_segment_calibration import (
    SEGMENT_HIERARCHY,
    apply_asymmetric_segment_calibration,
    build_bias_calibration_frame,
    estimate_segment_bias_factors,
)
from models.promotions.promo_core_feature_merge import write_phase6e_feature_merge_diagnostics
from models.promotions.promo_decision_graph_memory import derive_dag_state_features, populate_repairable_dag_nodes
from models.promotions.promo_demand_backtest import compute_wape
from models.promotions.promo_phase6c_active_learning_graph_validation import (
    _merge_frame,
    build_active_learning_review_queue,
)
from models.promotions.promo_phase6b_orchestrator import _load_source_frame

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6e01_feature_merge_calibration_ats")
PHASE6B_DIR = Path("Diagnostics/phase6b01_brain_state_adjacent_graph_reporting")
PHASE6C_DIR = Path("Diagnostics/phase6c01_active_learning_graph_validation")
PHASE6D_DIR = Path("Diagnostics/phase6d01_dag_active_learning_adjacent_calibration")
PHASE6A_DIR = Path("Diagnostics/phase6a01_segment_bias_calibration")
IDENTITY_COLUMNS = ("store_number", "promotion_id", "sku_number")

RELEASE_RECOMMENDATION = "NO_RELEASE"
PRIMARY_BLOCKER = "no_segment_calibration_allowed_rows"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _numeric(series: pd.Series | Any, default: float = 0.0) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series([pd.to_numeric(series, errors="coerce")]).fillna(default)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _load_enrichment_frame(source_frame: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    core = _load_source_frame(source_frame)
    adjacent = _read_csv(PHASE6B_DIR / "phase6b01_adjacent_path_simulation.csv")
    graph_mem = _read_csv(PHASE6B_DIR / "phase6b01_graph_memory_features.csv")
    ats = _read_csv(PHASE6B_DIR / "phase6b01_available_to_sell_confidence.csv")
    segment = _read_csv(PHASE6A_DIR / "phase6a01_bias_calibration_frame_sample.csv")

    merged = _merge_frame(core, adjacent, graph_mem, segment)
    if not ats.empty:
        merged = _merge_frame(merged, ats, pd.DataFrame(), pd.DataFrame())

    enrichment = assign_adjacent_path_policies(merged)
    dag = derive_dag_state_features(populate_repairable_dag_nodes(enrichment))
    for col in dag.columns:
        if col not in enrichment.columns:
            enrichment[col] = dag[col].values
    queue = build_active_learning_review_queue(enrichment)
    for col in queue.columns:
        if col.startswith(("active_learning", "expected_information", "which_model", "priority_bucket", "human_review_question")):
            enrichment[col] = queue[col].values
    return core, enrichment


def _eligibility_mask(frame: pd.DataFrame) -> pd.Series:
    quality = frame.get("promo_demand_source_quality", pd.Series("UNSAFE", index=frame.index)).astype(str)
    obs = frame.get("demand_observation_quality", pd.Series("LOW", index=frame.index)).astype(str)
    cal = frame.get("calibration_eligible_flag", pd.Series("NO", index=frame.index)).astype(str)
    ats = frame.get("ats_calibration_eligibility_support_flag", pd.Series("NO", index=frame.index)).astype(str)
    seg_elig = frame.get("segment_calibration_eligible_flag", pd.Series("NO", index=frame.index)).astype(str)
    return (
        quality.isin(["HIGH", "MEDIUM"])
        & obs.eq("HIGH")
        & cal.eq("YES")
        & _numeric(frame.get("stockout_suspected_flag", 0)).astype(int).eq(0)
        & seg_elig.eq("YES")
        & ats.eq("YES")
    )


def build_segment_calibration_eligibility_after_merge(
    before_frame: pd.DataFrame,
    after_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Compare segment eligibility before and after feature merge + ATS strengthening."""
    rows: list[dict[str, Any]] = []

    def _prep(frame: pd.DataFrame) -> pd.DataFrame:
        from models.promotions.promo_bias_segment_calibration import (
            _eligible_for_segment_fit,
            add_calibration_bands,
            assign_observation_quality,
        )
        cal = frame.copy()
        if "segment_calibration_eligible_flag" not in cal.columns:
            cal = add_calibration_bands(cal)
            cal = assign_observation_quality(cal)
            cal["segment_calibration_eligible_flag"] = _eligible_for_segment_fit(cal).map({True: "YES", False: "NO"})
        if "segment_calibrated_expected_units" not in cal.columns:
            factors = estimate_segment_bias_factors(cal)
            cal = apply_asymmetric_segment_calibration(cal, factors)
        return cal.reset_index(drop=True)

    before = _prep(before_frame)
    after = _prep(after_frame)
    before_allowed = before.get("segment_calibration_allowed_flag", pd.Series("NO", index=before.index)).astype(str).eq("YES")
    after_mask = _eligibility_mask(after)
    after_allowed = after.get("segment_calibration_allowed_flag", pd.Series("NO", index=after.index)).astype(str).eq("YES") & after_mask

    for level_name, cols in SEGMENT_HIERARCHY:
        if not cols or any(c not in after.columns for c in cols):
            continue
        for key_vals, chunk_after in after.groupby(list(cols), dropna=False):
            if not isinstance(key_vals, tuple):
                key_vals = (key_vals,)
            key = "|".join(str(v) for v in key_vals)
            chunk_before = before.loc[
                np.logical_and.reduce([before[c].astype(str) == str(v) for c, v in zip(cols, key_vals)])
            ] if not chunk_after.empty else before.iloc[0:0]
            elig_before = int(before_allowed.loc[chunk_before.index].sum()) if not chunk_before.empty else 0
            elig_after = int(after_allowed.loc[chunk_after.index].sum())
            actual = _numeric(chunk_after.get("actual_units_sold_promo", 0))
            forecast = _numeric(chunk_after.get("segment_calibrated_expected_units", 0))
            bias = float((forecast - actual).sum() / max(actual.sum(), 1) * 100.0)
            wape = float(compute_wape(actual, forecast)) if actual.sum() > 0 else np.nan
            blocker_before = "not_segment_calibration_eligible" if elig_before == 0 else ""
            blocker_after = "not_segment_calibration_eligible" if elig_after == 0 else (
                "ats_support_missing" if chunk_after.get("ats_calibration_eligibility_support_flag", pd.Series("NO")).astype(str).ne("YES").all()
                else ""
            )
            if elig_after > elig_before:
                status = "READY_FOR_HUMAN_APPROVAL_REVIEW"
            elif elig_after > 0:
                status = "READY_FOR_HUMAN_APPROVAL_REVIEW"
            elif blocker_after == "ats_support_missing":
                status = "DATA_REPAIR_REQUIRED"
            else:
                status = "STILL_BLOCKED"
            rows.append({
                "segment_key": key,
                "row_count": int(len(chunk_after)),
                "bias_pct": round(bias, 4),
                "wape": round(wape, 6) if not np.isnan(wape) else np.nan,
                "eligibility_before": elig_before,
                "eligibility_after": elig_after,
                "eligibility_status": status,
                "eligibility_blocker_before": blocker_before,
                "eligibility_blocker_after": blocker_after,
                "ats_support_flag": "YES" if chunk_after.get("ats_calibration_eligibility_support_flag", pd.Series("NO")).astype(str).eq("YES").any() else "NO",
                "feature_merge_support_flag": "YES" if any(c in chunk_after.columns for c in ("ats_evidence_score", "dag_state_coverage_score_v2")) else "NO",
                "human_review_support_flag": "YES" if chunk_after.get("human_review_status", pd.Series("PENDING")).astype(str).ne("").any() else "NO",
                "safe_for_human_approval_review_flag": "YES" if status == "READY_FOR_HUMAN_APPROVAL_REVIEW" else "NO",
                "deployment_status": "PROPOSED_NOT_DEPLOYED",
            })
    if not rows:
        rows.append({
            "segment_key": "total",
            "row_count": int(len(after)),
            "bias_pct": 0.0,
            "wape": np.nan,
            "eligibility_before": int(before_allowed.sum()),
            "eligibility_after": int(after_allowed.sum()),
            "eligibility_status": "STILL_BLOCKED" if after_allowed.sum() == 0 else "READY_FOR_HUMAN_APPROVAL_REVIEW",
            "eligibility_blocker_before": "not_segment_calibration_eligible",
            "eligibility_blocker_after": "ats_or_quality" if after_allowed.sum() == 0 else "",
            "ats_support_flag": "YES" if after.get("ats_calibration_eligibility_support_flag", pd.Series("NO")).astype(str).eq("YES").any() else "NO",
            "feature_merge_support_flag": "YES",
            "human_review_support_flag": "NO",
            "safe_for_human_approval_review_flag": "NO",
            "deployment_status": "PROPOSED_NOT_DEPLOYED",
        })
    return pd.DataFrame(rows)


def build_brain_retraining_readiness(
    merged_frame: pd.DataFrame,
    merge_plan: pd.DataFrame,
    segment_eligibility: pd.DataFrame,
) -> pd.DataFrame:
    """Audit leak-safe retraining readiness without retraining."""
    leak_safe = int(merge_plan.loc[merge_plan["merge_safety_status"].eq("SAFE")].shape[0])
    ats_rows = int(merged_frame.get("ats_calibration_eligibility_support_flag", pd.Series("NO")).astype(str).eq("YES").sum())
    cal_segments = int(segment_eligibility.loc[
        segment_eligibility["eligibility_status"].eq("READY_FOR_HUMAN_APPROVAL_REVIEW")
    ].shape[0]) if not segment_eligibility.empty else 0
    human = int(merged_frame.get("human_review_status", pd.Series("", index=merged_frame.index)).astype(str).eq("COMPLETE").sum())
    actuals = int(_numeric(merged_frame.get("actual_units_sold_promo", 0)).gt(0).sum())
    unsafe = int(merged_frame.get("promo_demand_source_quality", pd.Series("UNSAFE")).astype(str).eq("UNSAFE").sum())

    if leak_safe >= 10 and ats_rows > 0 and actuals > 50:
        status = "READY_FOR_LEAK_SAFE_BACKTEST_ONLY"
    elif leak_safe >= 5:
        status = "READY_FOR_SHADOW_RETRAINING"
    else:
        status = "DO_NOT_RETRAIN_YET"

    return pd.DataFrame([{
        "merged_feature_count": int(merge_plan["merge_status"].isin({"MERGED_SAFE", "READY_TO_MERGE"}).sum()),
        "leak_safe_feature_count": leak_safe,
        "ATS_supported_rows": ats_rows,
        "calibration_eligible_segments": cal_segments,
        "human_reviewed_rows": human,
        "actual_outcome_rows": actuals,
        "unsafe_rows": unsafe,
        "recommended_training_status": status,
    }])


def write_phase6e_diagnostics(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    source_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    core, enrichment = _load_enrichment_frame(source_frame)
    visibility = _read_csv(PHASE6B_DIR / "phase6b01_feature_visibility_audit.csv")
    opportunity = _read_csv(PHASE6D_DIR / "phase6d01_feature_merge_opportunity_review.csv")

    merge_result = write_phase6e_feature_merge_diagnostics(
        core, enrichment, diagnostics_dir=diagnostics_dir,
        opportunity_df=opportunity, visibility_df=visibility,
    )
    merged = merge_result["merged_frame"]
    ats_result = write_phase6e_ats_diagnostics(merged, diagnostics_dir=diagnostics_dir)
    strengthened = ats_result["strengthened_frame"]

    seg_elig = build_segment_calibration_eligibility_after_merge(merged, strengthened)
    seg_elig.to_csv(diagnostics_dir / "phase6e01_segment_calibration_eligibility_after_merge.csv", index=False)

    retrain = build_brain_retraining_readiness(strengthened, merge_result["merge_plan"], seg_elig)
    retrain.to_csv(diagnostics_dir / "phase6e01_brain_retraining_readiness.csv", index=False)

    ready_human = int(seg_elig.loc[seg_elig["safe_for_human_approval_review_flag"].eq("YES")].shape[0])
    gate6a = _read_csv(PHASE6A_DIR / "phase6a01_release_gate.csv")
    primary = str(gate6a.iloc[0]["primary_blocker"]) if not gate6a.empty else PRIMARY_BLOCKER

    gate = pd.DataFrame([{
        "customer_release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": primary,
        "phase6a_deployment_status": "PROPOSED_NOT_DEPLOYED",
        "feature_merge_plan_generated": "YES",
        "safe_merged_features_count": merge_result["safe_merged_feature_count"],
        "blocked_feature_count": merge_result["blocked_feature_count"],
        "diagnostics_only_feature_count": merge_result["diagnostics_only_feature_count"],
        "core_frame_columns_before": merge_result["core_frame_columns_before"],
        "core_frame_columns_after": merge_result["core_frame_columns_after"],
        "ats_strong_evidence_rows": ats_result["ats_strong_evidence_rows"],
        "ats_weak_evidence_rows": ats_result["ats_weak_evidence_rows"],
        "ats_supported_calibration_rows": ats_result["ats_supported_calibration_rows"],
        "calibration_segments_ready_for_human_approval": ready_human,
        "brain_retraining_readiness_status": str(retrain.iloc[0]["recommended_training_status"]),
        "auto_orders_approved": "NO",
        "notes": "Phase 6E merges safe features and strengthens ATS; does not deploy calibration",
    }])
    gate.to_csv(diagnostics_dir / "phase6e01_release_gate.csv", index=False)

    return {
        "feature_merge_plan_generated": True,
        "safe_merged_feature_count": merge_result["safe_merged_feature_count"],
        "blocked_feature_count": merge_result["blocked_feature_count"],
        "diagnostics_only_feature_count": merge_result["diagnostics_only_feature_count"],
        "core_frame_columns_before": merge_result["core_frame_columns_before"],
        "core_frame_columns_after": merge_result["core_frame_columns_after"],
        "ats_strong_evidence_rows": ats_result["ats_strong_evidence_rows"],
        "ats_weak_evidence_rows": ats_result["ats_weak_evidence_rows"],
        "ats_supported_calibration_rows": ats_result["ats_supported_calibration_rows"],
        "calibration_segments_ready_for_human_approval": ready_human,
        "brain_retraining_readiness_status": str(retrain.iloc[0]["recommended_training_status"]),
        "release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": primary,
        "governed_actions_overwritten": False,
        "auto_order_created": False,
    }


def run_phase6e01_feature_merge_calibration_ats(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    source_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    return write_phase6e_diagnostics(diagnostics_dir=diagnostics_dir, source_frame=source_frame)
