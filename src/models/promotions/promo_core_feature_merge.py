from __future__ import annotations

"""Phase 6E — safe merge of high-value derived features into the core frame."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_brain_leakage_audit import FORCE_EXCLUDED_FEATURES, LEAKAGE_KEYWORDS

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6e01_feature_merge_calibration_ats")
PHASE6D_DIR = Path("Diagnostics/phase6d01_dag_active_learning_adjacent_calibration")
IDENTITY_COLUMNS = ("store_number", "promotion_id", "sku_number")

MERGE_STATUS_VALUES = (
    "MERGED_SAFE", "READY_TO_MERGE", "DIAGNOSTICS_ONLY", "BLOCKED_LEAKAGE_RISK",
    "BLOCKED_MISSING_SOURCE", "BLOCKED_DUPLICATE_SEMANTIC", "BLOCKED_LOW_VALUE",
)

POST_PROMO_BLOCKLIST = frozenset({
    "actual_units_sold_promo", "forecast_error_units", "forecast_abs_error_units",
    "forecast_pct_error", "model_bias_units", "leftover_units_estimate",
    "realised_outcome", "lesson_learned_label",
})

SEMANTIC_DUPLICATES: dict[str, str] = {
    "available_to_sell_confidence_score": "ats_evidence_score",
    "dag_state_coverage_score": "dag_state_coverage_score_v2",
    "adjacent_confidence_score": "adjacent_confidence_calibrated",
}

PRIORITY_MERGE_FEATURES: tuple[str, ...] = (
    "available_to_sell_confidence_score", "ats_confidence_label", "ats_stockout_censoring_risk",
    "ats_false_zero_demand_risk", "ats_do_not_learn_zero_sales_flag",
    "dag_state_coverage_score_v2", "dag_decision_path_quality_v2", "dag_state_missingness_risk_score",
    "kg_basket_centrality_score", "kg_substitute_availability_score", "kg_supplier_dependency_score",
    "kg_mission_role_strength", "kg_history_similarity_score", "kg_stockout_memory_score",
    "kg_human_override_memory_score",
    "adjacent_reference_count", "adjacent_reference_quality", "adjacent_confidence_calibrated",
    "adjacent_path_use_policy", "adjacent_path_warning",
    "active_learning_score", "active_learning_reason", "expected_information_gain",
    "which_model_component_will_learn",
)

DAG_NODE_FLAG_SUFFIXES = ("_available_flag", "_source_quality")


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _is_leakage_risk(name: str) -> bool:
    lower = name.lower()
    if name in FORCE_EXCLUDED_FEATURES or name in POST_PROMO_BLOCKLIST:
        return True
    if any(k in lower for k in LEAKAGE_KEYWORDS) and name not in PRIORITY_MERGE_FEATURES:
        return "actual_" in lower or "realised" in lower or "leftover" in lower
    return False


def _dtype_policy(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series):
        return "float64"
    return "string"


def _missing_policy(name: str, series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series):
        return "KEEP_NAN_NOT_ZERO"
    return "KEEP_UNKNOWN_LABEL"


def validate_feature_merge_safety(
    feature_name: str,
    *,
    enrichment_frame: pd.DataFrame,
    core_frame: pd.DataFrame,
    source_module: str = "unknown",
    feature_family: str = "unknown",
) -> dict[str, Any]:
    """Evaluate whether a single feature can be merged safely."""
    in_enrichment = feature_name in enrichment_frame.columns
    in_core = feature_name in core_frame.columns
    leakage = _is_leakage_risk(feature_name)
    duplicate_of = SEMANTIC_DUPLICATES.get(feature_name)
    duplicate_blocked = bool(
        duplicate_of and duplicate_of in core_frame.columns and duplicate_of != feature_name
    )
    pre_decision = feature_name not in POST_PROMO_BLOCKLIST and not leakage
    priority = feature_name in PRIORITY_MERGE_FEATURES or any(
        feature_name.startswith("dag_") and feature_name.endswith(s)
        for s in DAG_NODE_FLAG_SUFFIXES
    )

    if not in_enrichment:
        status = "BLOCKED_MISSING_SOURCE"
        blocker = "NOT_IN_ENRICHMENT_FRAME"
    elif leakage:
        status = "BLOCKED_LEAKAGE_RISK"
        blocker = "LEAKAGE_OR_POST_PROMO"
    elif duplicate_blocked:
        status = "BLOCKED_DUPLICATE_SEMANTIC"
        blocker = f"DUPLICATE_OF_{duplicate_of}"
    elif not pre_decision:
        status = "BLOCKED_LEAKAGE_RISK"
        blocker = "NOT_PRE_DECISION"
    elif feature_name.startswith("adjacent_expected_units"):
        status = "DIAGNOSTICS_ONLY"
        blocker = "ADJACENT_MUST_NOT_REPLACE_FORECAST"
    elif not priority and not feature_name.startswith(("dag_", "kg_", "ats_", "active_learning")):
        status = "BLOCKED_LOW_VALUE"
        blocker = "NOT_IN_PHASE6E_PRIORITY_SET"
    elif in_core:
        status = "MERGED_SAFE"
        blocker = ""
    else:
        status = "READY_TO_MERGE"
        blocker = ""

    series = enrichment_frame[feature_name] if in_enrichment else pd.Series(dtype=float)
    return {
        "feature_name": feature_name,
        "feature_family": feature_family,
        "source_module": source_module,
        "merge_status": status,
        "merge_priority": 1 if priority else 2,
        "merge_safety_status": "SAFE" if status in {"MERGED_SAFE", "READY_TO_MERGE"} else "BLOCKED",
        "leakage_risk_level": "HIGH" if leakage else ("LOW" if pre_decision else "MEDIUM"),
        "available_pre_decision_flag": "YES" if pre_decision else "NO",
        "missing_value_policy": _missing_policy(feature_name, series) if in_enrichment else "N/A",
        "dtype_policy": _dtype_policy(series) if in_enrichment else "unknown",
        "expected_decision_value": "HIGH" if priority else "MEDIUM",
        "merge_blocker": blocker,
        "recommended_action": "MERGE" if status == "READY_TO_MERGE" else ("KEEP" if status == "MERGED_SAFE" else status),
    }


def build_feature_merge_plan(
    core_frame: pd.DataFrame,
    enrichment_frame: pd.DataFrame,
    *,
    opportunity_df: pd.DataFrame | None = None,
    visibility_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build merge plan for priority and opportunity features."""
    opportunity = opportunity_df if opportunity_df is not None else _read_csv(
        PHASE6D_DIR / "phase6d01_feature_merge_opportunity_review.csv"
    )
    visibility = visibility_df if visibility_df is not None else pd.DataFrame()

    candidates: set[str] = set(PRIORITY_MERGE_FEATURES)
    candidates.update(enrichment_frame.columns.astype(str))
    if not opportunity.empty:
        candidates.update(opportunity["feature_name"].astype(str))
    for node_col in enrichment_frame.columns:
        c = str(node_col)
        if c.startswith("dag_") and (c.endswith("_available_flag") or c.endswith("_source_quality")):
            candidates.add(c)

    family_map = {}
    module_map = {}
    if not opportunity.empty:
        family_map = dict(zip(opportunity["feature_name"].astype(str), opportunity["feature_family"].astype(str)))
        module_map = dict(zip(opportunity["feature_name"].astype(str), opportunity["source_module"].astype(str)))
    if not visibility.empty:
        for _, row in visibility.iterrows():
            fn = str(row["feature_name"])
            family_map.setdefault(fn, str(row.get("feature_family", "unknown")))
            module_map.setdefault(fn, "promo_brain_state_audit")

    rows = [
        validate_feature_merge_safety(
            feat,
            enrichment_frame=enrichment_frame,
            core_frame=core_frame,
            source_module=module_map.get(feat, "phase6e_enrichment"),
            feature_family=family_map.get(feat, "derived_or_phase_extension"),
        )
        for feat in sorted(candidates)
        if feat not in IDENTITY_COLUMNS
    ]
    plan = pd.DataFrame(rows)
    if not plan.empty:
        plan = plan.sort_values(["merge_priority", "merge_status", "feature_name"])
    return plan


def merge_safe_features_into_core_frame(
    core_frame: pd.DataFrame,
    enrichment_frame: pd.DataFrame,
    merge_plan: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge READY_TO_MERGE and re-affirm MERGED_SAFE features into core frame."""
    out = core_frame.copy()
    merge_cols = [c for c in IDENTITY_COLUMNS if c in out.columns and c in enrichment_frame.columns]
    audit_rows: list[dict[str, Any]] = []

    safe_statuses = {"MERGED_SAFE", "READY_TO_MERGE"}
    to_merge = merge_plan.loc[merge_plan["merge_status"].isin(safe_statuses)].copy()

    if merge_cols:
        left = out.copy()
        right = enrichment_frame.copy()
        for col in merge_cols:
            left[col] = left[col].astype(str)
            right[col] = right[col].astype(str)
        add_feats = [str(r["feature_name"]) for _, r in to_merge.iterrows() if str(r["feature_name"]) not in out.columns]
        re_feats = [str(r["feature_name"]) for _, r in to_merge.iterrows() if str(r["feature_name"]) in out.columns]
        if add_feats:
            right_sub = right[merge_cols + add_feats].drop_duplicates(subset=merge_cols, keep="first")
            out = left.merge(right_sub, on=merge_cols, how="left")
        for feat in re_feats:
            if feat in enrichment_frame.columns:
                merged = left.merge(
                    right[merge_cols + [feat]].drop_duplicates(subset=merge_cols, keep="first"),
                    on=merge_cols, how="left", suffixes=("", "_enr"),
                )
                enr_col = f"{feat}_enr" if f"{feat}_enr" in merged.columns else feat
                if enr_col in merged.columns:
                    out[feat] = merged[enr_col]

    for _, row in merge_plan.iterrows():
        feat = str(row["feature_name"])
        if feat not in out.columns and str(row["merge_status"]) == "READY_TO_MERGE" and feat in enrichment_frame.columns:
            if len(enrichment_frame) == len(out):
                out[feat] = enrichment_frame[feat].values
            elif merge_cols:
                pass  # already merged via keys
            else:
                out[feat] = enrichment_frame[feat].iloc[: len(out)].values
        audit_rows.append({
            "feature_name": feat,
            "merge_status": str(row["merge_status"]),
            "present_in_core_after": "YES" if feat in out.columns else "NO",
        })

    for col in out.select_dtypes(include="object").columns:
        if col.endswith("_label") or col.endswith("_quality") or col.endswith("_flag"):
            out[col] = out[col].astype(str).replace({"nan": "UNKNOWN", "None": "UNKNOWN"})

    row_audit = pd.DataFrame(audit_rows)
    return out, row_audit


def build_core_frame_merge_audit(
    core_before: pd.DataFrame,
    core_after: pd.DataFrame,
    merge_plan: pd.DataFrame,
    visibility_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarise before/after core frame merge impact."""
    visibility = visibility_df if visibility_df is not None else pd.DataFrame()
    brain_before = int(visibility["used_by_brain_model_flag"].eq("YES").sum()) if not visibility.empty else 0
    brain_cols_after = set(core_after.columns.astype(str))
    brain_after = brain_before
    if not visibility.empty:
        brain_after = int(visibility.loc[
            visibility["feature_name"].astype(str).isin(brain_cols_after)
            & visibility["used_by_brain_model_flag"].eq("YES")
        ].shape[0])

    summary = pd.DataFrame([{
        "source_frame_columns_before": int(len(core_before.columns)),
        "source_frame_columns_after": int(len(core_after.columns)),
        "merged_features_count": int(merge_plan["merge_status"].isin({"MERGED_SAFE", "READY_TO_MERGE"}).sum()),
        "blocked_features_count": int(merge_plan["merge_status"].astype(str).str.startswith("BLOCKED").sum()),
        "diagnostics_only_features_count": int(merge_plan["merge_status"].eq("DIAGNOSTICS_ONLY").sum()),
        "brain_used_features_before": brain_before,
        "brain_used_features_after": brain_after,
        "governance_used_features_before": int(visibility["used_by_governance_flag"].eq("YES").sum()) if not visibility.empty else 0,
        "report_used_features_before": int(visibility["used_by_report_flag"].eq("YES").sum()) if not visibility.empty else 0,
        "report_used_features_after": int(visibility["used_by_report_flag"].eq("YES").sum()) if not visibility.empty else 0,
        "leakage_risk_features_excluded": int(merge_plan["merge_status"].eq("BLOCKED_LEAKAGE_RISK").sum()),
        "duplicate_semantic_fields_excluded": int(merge_plan["merge_status"].eq("BLOCKED_DUPLICATE_SEMANTIC").sum()),
        "safe_merged_feature_count": int(merge_plan.loc[
            merge_plan["merge_status"].isin({"MERGED_SAFE", "READY_TO_MERGE"})
        ].shape[0]),
    }])
    return summary


def write_phase6e_feature_merge_diagnostics(
    core_frame: pd.DataFrame,
    enrichment_frame: pd.DataFrame,
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    opportunity_df: pd.DataFrame | None = None,
    visibility_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    plan = build_feature_merge_plan(
        core_frame, enrichment_frame, opportunity_df=opportunity_df, visibility_df=visibility_df,
    )
    merged_frame, row_audit = merge_safe_features_into_core_frame(core_frame, enrichment_frame, plan)
    plan = plan.merge(
        row_audit[["feature_name", "present_in_core_after"]] if not row_audit.empty else pd.DataFrame(),
        on="feature_name", how="left",
    )
    plan["present_in_core_after"] = plan["present_in_core_after"].fillna(
        plan["feature_name"].isin(merged_frame.columns).map({True: "YES", False: "NO"})
    )
    audit = build_core_frame_merge_audit(core_frame, merged_frame, plan, visibility_df=visibility_df)

    plan.to_csv(diagnostics_dir / "phase6e01_feature_merge_plan.csv", index=False)
    audit.to_csv(diagnostics_dir / "phase6e01_core_frame_feature_merge_audit.csv", index=False)

    safe_count = int(plan.loc[plan["merge_status"].isin({"MERGED_SAFE", "READY_TO_MERGE"})].shape[0])
    return {
        "feature_merge_plan_generated": True,
        "safe_merged_feature_count": safe_count,
        "blocked_feature_count": int(plan["merge_status"].astype(str).str.startswith("BLOCKED").sum()),
        "diagnostics_only_feature_count": int(plan["merge_status"].eq("DIAGNOSTICS_ONLY").sum()),
        "core_frame_columns_before": int(len(core_frame.columns)),
        "core_frame_columns_after": int(len(merged_frame.columns)),
        "merged_frame": merged_frame,
        "merge_plan": plan,
        "merge_audit": audit,
    }
