from __future__ import annotations

"""Phase 6B — brain state coverage audit and legacy hard-coded limit review."""

import ast
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_brain_feature_learning import FEATURE_FAMILIES as BRAIN_FEATURE_FAMILIES
from models.promotions.promo_brain_leakage_audit import FORCE_EXCLUDED_FEATURES

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6b01_brain_state_adjacent_graph_reporting")
PHASE5U_SCORED = Path("Diagnostics/phase5u01_shadow_outcome_learning/phase5u01_shadow_scored_outcomes.csv")
PHASE5D_BACKTEST = Path("Diagnostics/phase5d01_forecast_backtest_validation/phase5d01_backtest_frame.csv")
PHASE5Q_SCHEMA = Path("Diagnostics/phase5q01_full_feature_brain_learning/phase5q01_training_frame_schema.csv")
PHASE6A_GATE = Path("Diagnostics/phase6a01_segment_bias_calibration/phase6a01_release_gate.csv")

RELEASE_RECOMMENDATION = "NO_RELEASE"
PRIMARY_BLOCKER = "no_segment_calibration_allowed_rows"

EXTENDED_FEATURE_FAMILIES: dict[str, tuple[str, ...]] = {
    **BRAIN_FEATURE_FAMILIES,
    "shadow_human_feedback": (
        "shadow_candidate_class", "shadow_candidate_score", "human_buyer_decision",
        "human_override_flag", "human_review_status", "lesson_learned_label",
    ),
    "lesson_weighted_learning": (
        "lesson_weight", "brain_update_recommendation", "governance_update_recommendation",
    ),
    "bias_calibration": (
        "segment_bias_factor", "segment_calibrated_expected_units", "model_expected_units_total_promo_calibrated",
    ),
    "dag_knowledge_graph_memory": (
        "kg_basket_centrality_score", "kg_substitute_availability_score", "dag_state_coverage_score",
        "dag_decision_path_quality",
    ),
}

GOVERNANCE_COLUMNS = (
    "final_governed_action_label", "final_governed_order_units", "constraint_block_flag",
    "promo_demand_release_ready_flag", "unsafe_flag", "calibration_eligible_flag",
)
REPORT_COLUMNS = (
    "decision", "recommended_order_units", "advisory_label", "production_ordering_approved",
    "model_wape", "model_bias_pct", "release_recommendation", "primary_blocker",
)
SCAN_PATHS = (
    "src/models/promotions/promo_brain_feature_learning.py",
    "src/models/promotions/promo_brain_leakage_audit.py",
    "src/models/promotions/promo_shadow_candidate_selection.py",
    "src/models/promotions/promo_bias_segment_calibration.py",
    "src/models/promotions/promo_economic_value_scoring.py",
    "src/surfaces/promotions/reporting/commercial_report_builder.py",
    "src/surfaces/promotions/reporting/promo_operating_pack_export.py",
    "src/models/promotions/promo_decision_graph_memory.py",
)

HARDCODED_PATTERNS = (
    (r"FEATURE_FAMILIES", "static_feature_family_map", "WARNING"),
    (r"FORCE_EXCLUDED_FEATURES", "leakage_exclusion_list", "INFO"),
    (r"frozenset\(\{", "hardcoded_frozenset", "WARNING"),
    (r"ALLOWLIST|allowlist|FEATURE_COLUMNS\s*=", "restrictive_feature_selector", "ERROR"),
)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_brain_feature_inventory(
    source_frame: pd.DataFrame,
    *,
    schema_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Inventory all feature families and columns available vs expected."""
    schema = schema_df if schema_df is not None else _read_csv(PHASE5Q_SCHEMA)
    rows: list[dict[str, Any]] = []
    source_cols = set(source_frame.columns.astype(str))
    schema_cols = set(schema["column_name"].astype(str)) if not schema.empty and "column_name" in schema.columns else set()

    for family, cols in EXTENDED_FEATURE_FAMILIES.items():
        for col in cols:
            in_source = col in source_cols
            in_schema = col in schema_cols
            rows.append({
                "feature_name": col,
                "feature_family": family,
                "in_source_frame": in_source,
                "in_training_schema": in_schema,
                "source_dtype": str(source_frame[col].dtype) if in_source else "",
            })
    for col in sorted(source_cols):
        if any(col in cols for cols in EXTENDED_FEATURE_FAMILIES.values()):
            continue
        if col.startswith(("feature_", "brain_", "shadow_", "segment_", "kg_", "dag_", "adjacent_", "ats_")):
            rows.append({
                "feature_name": col,
                "feature_family": "derived_or_phase_extension",
                "in_source_frame": True,
                "in_training_schema": col in schema_cols,
                "source_dtype": str(source_frame[col].dtype),
            })
    return pd.DataFrame(rows)


def audit_brain_feature_visibility(
    source_frame: pd.DataFrame,
    *,
    inventory_df: pd.DataFrame | None = None,
    leak_excluded: frozenset[str] | None = None,
) -> pd.DataFrame:
    """Audit which features are visible to brain, governance, reports, and graph."""
    inventory = inventory_df if inventory_df is not None else build_brain_feature_inventory(source_frame)
    excluded = leak_excluded or FORCE_EXCLUDED_FEATURES
    source_cols = set(source_frame.columns.astype(str))
    rows: list[dict[str, Any]] = []

    all_features = set(inventory["feature_name"].astype(str))
    brain_features = set()
    for family, cols in BRAIN_FEATURE_FAMILIES.items():
        brain_features.update(cols)

    for feat in sorted(all_features):
        in_source = feat in source_cols
        used_brain = feat in brain_features and feat not in excluded
        used_gov = feat in GOVERNANCE_COLUMNS or feat in {
            "promo_demand_source_quality", "promo_demand_release_ready_flag", "constraint_block_flag",
        }
        used_report = feat in REPORT_COLUMNS or feat.startswith(("brain_", "shadow_", "lesson_"))
        used_dag = feat.startswith(("kg_", "dag_")) or feat in {"basket_attachment_source_quality", "mission_sku_score"}
        used_kg = used_dag or feat in {
            "department", "category", "supplier_replenishment_regime", "long_tail_sku_flag",
        }

        exclude_reason = ""
        legacy_flag = "NO"
        dtype_issue = "NO"
        missing_issue = "NO"
        encoding_issue = "NO"
        action = "KEEP"

        if feat in excluded:
            exclude_reason = "leakage_audit_exclusion"
            used_brain = False
        elif feat not in brain_features and feat in source_cols and not feat.startswith("target_"):
            exclude_reason = "not_in_brain_feature_families"
            legacy_flag = "YES"
            action = "ADD_TO_BRAIN_FAMILY_OR_DIAGNOSTICS"
        elif not in_source:
            missing_issue = "YES"
            action = "BUILD_OR_MERGE_FEATURE"
        elif in_source and feat in source_frame.columns:
            miss_rate = float(source_frame[feat].isna().mean()) if len(source_frame) else 1.0
            if miss_rate > 0.5:
                missing_issue = "YES"
            if source_frame[feat].dtype == object and source_frame[feat].astype(str).eq("UNKNOWN").mean() > 0.3:
                encoding_issue = "YES"
                action = "REPAIR_ENCODING_OR_DEFAULTS"

        rows.append({
            "feature_name": feat,
            "feature_family": str(inventory.loc[inventory["feature_name"].eq(feat), "feature_family"].iloc[0])
            if feat in set(inventory["feature_name"].astype(str)) else "unknown",
            "available_in_source_frame_flag": "YES" if in_source else "NO",
            "used_by_brain_model_flag": "YES" if used_brain else "NO",
            "used_by_governance_flag": "YES" if used_gov else "NO",
            "used_by_report_flag": "YES" if used_report else "NO",
            "used_by_dag_flag": "YES" if used_dag else "NO",
            "used_by_knowledge_graph_flag": "YES" if used_kg else "NO",
            "excluded_from_brain_reason": exclude_reason,
            "legacy_hardcoded_limit_flag": legacy_flag,
            "dtype_issue_flag": dtype_issue,
            "missingness_issue_flag": missing_issue,
            "encoding_issue_flag": encoding_issue,
            "recommended_action": action,
        })
    return pd.DataFrame(rows)


def detect_legacy_hardcoded_feature_limits(
    *,
    repo_root: Path | None = None,
) -> pd.DataFrame:
    """Scan promotion modules for restrictive hard-coded feature lists."""
    root = repo_root or _repo_root()
    rows: list[dict[str, Any]] = []
    for rel in SCAN_PATHS:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(text)
            functions = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        except SyntaxError:
            functions = set()
        for pattern, risk_type, severity in HARDCODED_PATTERNS:
            for i, line in enumerate(text.splitlines(), start=1):
                if re.search(pattern, line):
                    fn = ""
                    for name in functions:
                        if name in line:
                            fn = name
                            break
                    rows.append({
                        "file_path": rel,
                        "function_name": fn,
                        "line_number": i,
                        "hardcoded_item": line.strip()[:120],
                        "risk_type": risk_type,
                        "risk_description": f"Hard-coded selector pattern `{pattern}` may exclude newer features",
                        "recommended_fix": "Extend allowlist dynamically from feature inventory; document exclusions",
                        "severity": severity,
                    })
    if not rows:
        rows.append({
            "file_path": "", "function_name": "", "line_number": 0,
            "hardcoded_item": "none_found", "risk_type": "none",
            "risk_description": "No patterns matched", "recommended_fix": "Continue periodic audit",
            "severity": "INFO",
        })
    return pd.DataFrame(rows)


def audit_model_input_contracts(
    source_frame: pd.DataFrame,
    visibility_df: pd.DataFrame,
) -> pd.DataFrame:
    """Summarise model input contract gaps."""
    brain_used = int(visibility_df["used_by_brain_model_flag"].eq("YES").sum())
    available = int(visibility_df["available_in_source_frame_flag"].eq("YES").sum())
    excluded_legacy = int(visibility_df["legacy_hardcoded_limit_flag"].eq("YES").sum())
    report_only = int(
        visibility_df.loc[
            visibility_df["used_by_report_flag"].eq("YES") & visibility_df["used_by_brain_model_flag"].eq("NO")
        ].shape[0]
    )
    brain_only = int(
        visibility_df.loc[
            visibility_df["used_by_brain_model_flag"].eq("YES") & visibility_df["used_by_report_flag"].eq("NO")
        ].shape[0]
    )
    return pd.DataFrame([{
        "source_row_count": int(len(source_frame)),
        "source_column_count": int(len(source_frame.columns)),
        "total_features_audited": int(len(visibility_df)),
        "features_available_in_source": available,
        "features_used_by_brain": brain_used,
        "features_excluded_legacy_limits": excluded_legacy,
        "report_only_features": report_only,
        "brain_only_features": brain_only,
        "contract_gap_count": report_only + excluded_legacy,
    }])


def build_ml_innovation_audit() -> pd.DataFrame:
    """Practical audit of ML/RL techniques — recommend, defer, or reject."""
    methods = [
        ("adjacent_path_simulation", "new-line and weak-history SKU reasoning", "READY", "existing promo-SKU frame", "LOW", "IMPLEMENT_NOW", 1, "Phase 6B adjacent path module"),
        ("available_to_sell_confidence", "false-zero-demand blind spot", "READY", "SOH and stockout flags", "LOW", "IMPLEMENT_NOW", 1, "Phase 6B ATS score"),
        ("active_learning_human_review", "prioritise shadow review queue", "READY", "shadow journal + human feedback", "LOW", "IMPLEMENT_NOW", 2, "Use economic + learning value ranking"),
        ("bayesian_hierarchical_shrinkage", "segment bias repair", "PARTIAL", "backtest segments", "MEDIUM", "IMPLEMENT_NOW", 2, "Extend Phase 6A with hierarchical priors"),
        ("contextual_bandit_shadow", "shadow action learning", "PARTIAL", "shadow scored outcomes", "MEDIUM", "PROTOTYPE_NEXT", 3, "Offline policy eval first"),
        ("doubly_robust_policy_eval", "human vs brain comparison", "PARTIAL", "human review records", "MEDIUM", "PROTOTYPE_NEXT", 3, "Need more completed reviews"),
        ("uplift_modelling", "promo incrementality", "PARTIAL", "backtest actuals", "MEDIUM", "PROTOTYPE_NEXT", 4, "Segment uplift after ATS repair"),
        ("quantile_regression_conformal", "forecast intervals", "PARTIAL", "backtest residuals", "LOW", "DEFER", 5, "After bias stabilises"),
        ("causal_forests_hte", "heterogeneous promo effects", "LOW", "large labelled set", "HIGH", "DEFER", 6, "Need cleaner causal labels"),
        ("graph_neural_network", "KG feature learning", "LOW", "stable KG coverage", "HIGH", "DEFER", 7, "After DAG/KG coverage stable"),
        ("offline_reinforcement_learning", "order policy learning", "LOW", "live decision records", "HIGH", "DEFER", 8, "Need human-reviewed outcomes"),
        ("meta_learning_sparse_sku", "new-line generalisation", "PARTIAL", "adjacent path refs", "MEDIUM", "PROTOTYPE_NEXT", 4, "Build on adjacent simulation"),
        ("counterfactual_simulation", "what-if order paths", "PARTIAL", "stock simulation", "MEDIUM", "PROTOTYPE_NEXT", 5, "Extend adjacent paths"),
    ]
    return pd.DataFrame([{
        "method_name": m[0], "use_case": m[1], "current_readiness": m[2], "data_required": m[3],
        "risk": m[4], "recommended_status": m[5], "implementation_priority": m[6], "next_safe_step": m[7],
    } for m in methods])


def write_phase6b_state_audit_diagnostics(
    *,
    source_frame: pd.DataFrame,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    inventory = build_brain_feature_inventory(source_frame)
    visibility = audit_brain_feature_visibility(source_frame, inventory_df=inventory)
    legacy = detect_legacy_hardcoded_feature_limits()
    contract = audit_model_input_contracts(source_frame, visibility)
    ml_audit = build_ml_innovation_audit()

    visibility.to_csv(diagnostics_dir / "phase6b01_feature_visibility_audit.csv", index=False)
    legacy.to_csv(diagnostics_dir / "phase6b01_legacy_hardcoded_limit_review.csv", index=False)
    ml_audit.to_csv(diagnostics_dir / "phase6b01_ml_innovation_audit.csv", index=False)

    return {
        "total_available_features": int(visibility["available_in_source_frame_flag"].eq("YES").sum()),
        "features_used_by_brain": int(visibility["used_by_brain_model_flag"].eq("YES").sum()),
        "features_excluded_legacy_limits": int(visibility["legacy_hardcoded_limit_flag"].eq("YES").sum()),
        "ml_innovation_top_recommendation": str(ml_audit.sort_values("implementation_priority").iloc[0]["method_name"]),
        "visibility_df": visibility,
        "legacy_df": legacy,
        "contract_df": contract,
        "ml_audit_df": ml_audit,
    }
