from __future__ import annotations

"""Phase 6D orchestrator — DAG population, adjacent calibration, active learning pack."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_active_learning_review_pack import write_active_learning_review_pack_diagnostics
from models.promotions.promo_adjacent_path_simulation import (
    assign_adjacent_path_policies,
    write_phase6d_adjacent_calibration_diagnostics,
)
from models.promotions.promo_bias_segment_calibration import build_bias_calibration_frame
from models.promotions.promo_decision_graph_memory import write_phase6d_graph_diagnostics
from models.promotions.promo_demand_backtest import compute_wape
from models.promotions.promo_phase6c_active_learning_graph_validation import (
    _merge_frame,
    build_active_learning_review_queue,
    validate_adjacent_path_against_actuals,
)
from models.promotions.promo_phase6b_orchestrator import _load_source_frame

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6d01_dag_active_learning_adjacent_calibration")
PHASE6B_DIR = Path("Diagnostics/phase6b01_brain_state_adjacent_graph_reporting")
PHASE6C_DIR = Path("Diagnostics/phase6c01_active_learning_graph_validation")
PHASE6A_DIR = Path("Diagnostics/phase6a01_segment_bias_calibration")
IDENTITY_COLUMNS = ("store_number", "promotion_id", "sku_number")

RELEASE_RECOMMENDATION = "NO_RELEASE"
PRIMARY_BLOCKER = "no_segment_calibration_allowed_rows"

FEATURE_SOURCE_MODULES = {
    "demand_uplift": "promo_demand_features",
    "basket_trust": "promo_basket_trust",
    "stock_optimal": "promo_stock_optimal",
    "regime_brain": "promo_regime_brain",
    "economic_triage": "promo_economic_triage",
    "quality_governance": "promo_governance",
    "dag_knowledge_graph_memory": "promo_decision_graph_memory",
    "shadow_human_feedback": "promo_human_review_capture",
    "lesson_weighted_learning": "promo_lesson_weighted",
}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _numeric(series: pd.Series | Any, default: float = 0.0) -> pd.Series:
    if not isinstance(series, pd.Series):
        return pd.Series([pd.to_numeric(series, errors="coerce")]).fillna(default)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _load_merged_frame(source_frame: pd.DataFrame | None = None) -> pd.DataFrame:
    frame = _load_source_frame(source_frame)
    adjacent = _read_csv(PHASE6B_DIR / "phase6b01_adjacent_path_simulation.csv")
    graph_mem = _read_csv(PHASE6B_DIR / "phase6b01_graph_memory_features.csv")
    ats = _read_csv(PHASE6B_DIR / "phase6b01_available_to_sell_confidence.csv")
    segment = _read_csv(PHASE6A_DIR / "phase6a01_bias_calibration_frame_sample.csv")
    merged = _merge_frame(frame, adjacent, graph_mem, segment)
    if not ats.empty:
        merged = _merge_frame(merged, ats, pd.DataFrame(), pd.DataFrame())
    return merged


def build_feature_merge_opportunity_review(
    source_frame: pd.DataFrame,
    visibility_df: pd.DataFrame,
    recon_detail: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Review catalogued features missing from source frame."""
    in_source = set(source_frame.columns.astype(str))
    detail = recon_detail if recon_detail is not None else _read_csv(PHASE6C_DIR / "phase6c01_feature_inventory_reconciliation_detail.csv")
    rows: list[dict[str, Any]] = []
    for _, row in visibility_df.iterrows():
        feat = str(row["feature_name"])
        present = feat in in_source
        brain = str(row.get("used_by_brain_model_flag", "NO"))
        if present:
            continue
        if brain != "YES" and str(row.get("available_in_source_frame_flag", "NO")) != "YES":
            continue
        family = str(row.get("feature_family", "unknown"))
        det = detail.loc[detail["column_name"].astype(str).eq(feat)] if not detail.empty else pd.DataFrame()
        raw_avail = "YES" if str(row.get("available_in_source_frame_flag", "NO")) == "YES" else "PARTIAL"
        merge_blocker = str(det.iloc[0]["exclusion_reason"]) if not det.empty and pd.notna(det.iloc[0].get("exclusion_reason")) else "NOT_MERGED_INTO_FRAME"
        if str(row.get("legacy_hardcoded_limit_flag", "NO")) == "YES":
            merge_blocker = "LEGACY_HARDCODED_LIMIT"
        priority = 1 if brain == "YES" and not present else (2 if brain == "YES" else 3)
        rows.append({
            "feature_name": feat,
            "feature_family": family,
            "currently_in_source_frame_flag": "YES" if present else "NO",
            "brain_eligible_flag": brain,
            "source_module": FEATURE_SOURCE_MODULES.get(family, "derived_or_phase_extension"),
            "raw_data_available_flag": raw_avail,
            "derived_feature_available_flag": "YES" if family in FEATURE_SOURCE_MODULES else "MAYBE",
            "merge_blocker": merge_blocker or "BUILD_OR_MERGE_FEATURE",
            "decision_value": "HIGH" if brain == "YES" else "MEDIUM",
            "recommended_merge_action": str(row.get("recommended_action", "BUILD_OR_MERGE_FEATURE")),
            "priority": priority,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["priority", "feature_name"])
    return out


def build_segment_calibration_eligibility_repair(frame: pd.DataFrame | None = None) -> pd.DataFrame:
    """Explain why segment calibration rows are blocked and path to eligibility."""
    cal = frame.copy() if frame is not None and not frame.empty else build_bias_calibration_frame()
    cal = cal.reset_index(drop=True)
    if "segment_calibration_allowed_flag" not in cal.columns:
        from models.promotions.promo_bias_segment_calibration import (
            apply_asymmetric_segment_calibration,
            estimate_segment_bias_factors,
        )
        factors = estimate_segment_bias_factors(cal)
        cal = apply_asymmetric_segment_calibration(cal, factors).reset_index(drop=True)

    def _mask(series: pd.Series) -> pd.Series:
        return pd.Series(series.values, index=cal.index)

    rows: list[dict[str, Any]] = []
    groups = [
        ("not_segment_calibration_eligible", _mask(cal.get("segment_calibration_eligible_flag", pd.Series("NO", index=cal.index)).astype(str).ne("YES"))),
        ("low_segment_factor_quality", _mask(cal.get("segment_bias_factor_quality", pd.Series("LOW", index=cal.index)).astype(str).eq("LOW"))),
        ("factor_out_of_bounds", _mask(~_numeric(cal.get("segment_bias_factor", 1.0)).between(0.5, 2.0))),
        ("zero_segment_adjusted_forecast", _mask(_numeric(cal.get("segment_calibrated_expected_units", 0)).le(0))),
        ("calibration_eligible_flag_no", _mask(cal.get("calibration_eligible_flag", pd.Series("NO", index=cal.index)).astype(str).ne("YES"))),
        ("demand_quality_unsafe", _mask(cal.get("promo_demand_source_quality", pd.Series("UNSAFE", index=cal.index)).astype(str).isin(["LOW", "UNSAFE", "UNKNOWN"]))),
        ("observation_quality_low", _mask(cal.get("demand_observation_quality", pd.Series("LOW", index=cal.index)).astype(str).ne("HIGH"))),
        ("stockout_censored", _mask(_numeric(cal.get("stockout_suspected_flag", 0)).gt(0))),
    ]
    for reason, mask in groups:
        chunk = cal.loc[mask]
        if chunk.empty:
            continue
        actual = _numeric(chunk.get("actual_units_sold_promo", 0))
        forecast = _numeric(chunk.get("segment_calibrated_expected_units", chunk.get("model_expected_units_total_promo", 0)))
        bias_pct = float((forecast - actual).sum() / max(actual.sum(), 1) * 100.0)
        wape = float(compute_wape(actual, forecast)) if actual.sum() > 0 else np.nan
        rows.append({
            "block_reason": reason,
            "row_count": int(len(chunk)),
            "bias_pct": round(bias_pct, 4),
            "wape": round(wape, 6) if not np.isnan(wape) else np.nan,
            "calibration_factor_proposed": float(_numeric(chunk.get("segment_bias_factor", 1.0)).median()),
            "why_not_eligible": reason.replace("_", " "),
            "data_quality_fix_required": "YES" if reason in {"demand_quality_unsafe", "observation_quality_low", "stockout_censored"} else "MAYBE",
            "human_approval_required_flag": "YES",
            "path_to_eligibility": (
                "Improve promo_demand_source_quality and demand_observation_quality to HIGH; clear stockout flags"
                if reason in {"demand_quality_unsafe", "observation_quality_low", "stockout_censored", "calibration_eligible_flag_no"}
                else "Review segment factor bounds and sample size"
            ),
            "expected_bias_impact_if_repaired": round(abs(bias_pct) * 0.3, 2),
        })
    return pd.DataFrame(rows).sort_values("row_count", ascending=False)


def write_phase6d_diagnostics(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    source_frame: pd.DataFrame | None = None,
    export_dir: Path | None = None,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    merged = _load_merged_frame(source_frame)
    visibility = _read_csv(PHASE6B_DIR / "phase6b01_feature_visibility_audit.csv")
    recon_detail = _read_csv(PHASE6C_DIR / "phase6c01_feature_inventory_reconciliation_detail.csv")

    graph = write_phase6d_graph_diagnostics(merged, diagnostics_dir=diagnostics_dir)
    dag_frame = graph["dag_state_df"]
    adjacent = write_phase6d_adjacent_calibration_diagnostics(merged, diagnostics_dir=diagnostics_dir)
    calibrated = adjacent["calibrated_df"]
    merge_cols = [c for c in IDENTITY_COLUMNS if c in dag_frame.columns and c in calibrated.columns]
    if merge_cols:
        for col in merge_cols:
            dag_frame[col] = dag_frame[col].astype(str)
            calibrated = calibrated.copy()
            calibrated[col] = calibrated[col].astype(str)
        add_cols = [c for c in calibrated.columns if c.startswith("adjacent_") and c not in dag_frame.columns]
        combined = dag_frame.merge(calibrated[merge_cols + add_cols].drop_duplicates(subset=merge_cols), on=merge_cols, how="left")
    else:
        combined = dag_frame.join(calibrated[[c for c in calibrated.columns if c.startswith("adjacent_")]], rsuffix="_adj")

    adj_valid = validate_adjacent_path_against_actuals(combined)
    learning_queue = build_active_learning_review_queue(adj_valid)
    review_pack = write_active_learning_review_pack_diagnostics(
        learning_queue, diagnostics_dir=diagnostics_dir, export_dir=export_dir,
    )

    merge_review = build_feature_merge_opportunity_review(merged, visibility, recon_detail)
    merge_review.to_csv(diagnostics_dir / "phase6d01_feature_merge_opportunity_review.csv", index=False)
    seg_repair = build_segment_calibration_eligibility_repair(merged)
    seg_repair.to_csv(diagnostics_dir / "phase6d01_segment_calibration_eligibility_repair.csv", index=False)

    gate6a = _read_csv(PHASE6A_DIR / "phase6a01_release_gate.csv")
    primary = str(gate6a.iloc[0]["primary_blocker"]) if not gate6a.empty else PRIMARY_BLOCKER
    high_priority_merge = int(merge_review.loc[merge_review["priority"].eq(1)].shape[0]) if not merge_review.empty else 0
    top_seg_blocker = str(seg_repair.iloc[0]["block_reason"]) if not seg_repair.empty else primary

    gate = pd.DataFrame([{
        "customer_release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": primary,
        "phase6a_deployment_status": "PROPOSED_NOT_DEPLOYED",
        "dag_state_coverage_score_v2": graph["dag_state_coverage_score_v2"],
        "dag_repairable_nodes_populated_count": graph["dag_repairable_nodes_populated_count"],
        "dag_unpopulated_repairable_nodes_count": graph.get("dag_unpopulated_repairable_nodes_count", 0),
        "adjacent_confidence_raw_avg": adjacent["adjacent_confidence_raw_avg"],
        "adjacent_confidence_calibrated_avg": adjacent["adjacent_confidence_calibrated_avg"],
        "adjacent_path_use_policy_dominant": adjacent["adjacent_path_use_policy_dominant"],
        "active_learning_review_rows": review_pack["active_learning_review_rows"],
        "top_active_learning_reason": review_pack["top_active_learning_reason"],
        "feature_merge_high_priority_count": high_priority_merge,
        "segment_calibration_eligibility_top_blocker": top_seg_blocker,
        "auto_orders_approved": "NO",
        "notes": "Phase 6D populates repairable DAG state and recalibrates adjacent confidence; no deployment",
    }])
    gate.to_csv(diagnostics_dir / "phase6d01_release_gate.csv", index=False)

    return {
        "dag_state_coverage_score_v2": float(graph["dag_state_coverage_score_v2"]),
        "dag_repairable_nodes_populated_count": int(graph["dag_repairable_nodes_populated_count"]),
        "dag_unpopulated_repairable_nodes_count": int(graph["dag_unpopulated_repairable_nodes_count"]),
        "adjacent_confidence_raw_avg": float(adjacent["adjacent_confidence_raw_avg"]),
        "adjacent_confidence_calibrated_avg": float(adjacent["adjacent_confidence_calibrated_avg"]),
        "adjacent_path_use_policy_dominant": adjacent["adjacent_path_use_policy_dominant"],
        "active_learning_review_rows": int(review_pack["active_learning_review_rows"]),
        "top_active_learning_reason": review_pack["top_active_learning_reason"],
        "feature_merge_high_priority_count": high_priority_merge,
        "segment_calibration_eligibility_top_blocker": top_seg_blocker,
        "release_recommendation": RELEASE_RECOMMENDATION,
        "primary_blocker": primary,
        "governed_actions_overwritten": False,
        "auto_order_created": False,
    }


def run_phase6d01_dag_active_learning_adjacent_calibration(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    source_frame: pd.DataFrame | None = None,
    export_dir: Path | None = None,
) -> dict[str, Any]:
    return write_phase6d_diagnostics(
        diagnostics_dir=diagnostics_dir, source_frame=source_frame, export_dir=export_dir,
    )
