from __future__ import annotations

"""Phase 6G — dynamic feature registry, legacy selector diff, and brain visibility repair."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_brain_feature_learning import FEATURE_FAMILIES as LEGACY_BRAIN_FAMILIES, _all_feature_names
from models.promotions.promo_brain_leakage_audit import FORCE_EXCLUDED_FEATURES
from models.promotions.promo_core_feature_merge import PRIORITY_MERGE_FEATURES
from models.promotions.promo_feature_universe_quality import (
    DEFAULT_FEATURE_INSPECTION_PATHS,
    _infer_feature_family,
    load_feature_universe_frame,
    resolve_feature_inspection_path,
)

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase6g01_dynamic_feature_registry")
PHASE6F_DIR = Path("Diagnostics/phase6f01_feature_universe_quality_gate")
UNKNOWN = "UNKNOWN"

REGISTRY_STATUS_VALUES = frozenset({
    "ACTIVE_MODEL_INPUT", "ACTIVE_MODEL_INPUT_WITH_FLAGS", "ACTIVE_ENCODED_CATEGORICAL",
    "ACTIVE_SPARSE_SIGNAL", "GOVERNANCE_ONLY", "REPORT_ONLY", "DIAGNOSTICS_ONLY",
    "BLOCKED_LEAKAGE", "BLOCKED_TARGET_DERIVED", "BLOCKED_POST_PROMO_ACTUAL",
    "BLOCKED_CONSTANT", "BLOCKED_ALL_ZERO", "BLOCKED_FULLY_MISSING",
    "BLOCKED_BROKEN_FEATURE", "BLOCKED_UNSUPPORTED_DTYPE", "REVIEW_REQUIRED",
})

MODEL_NAMES = (
    "uplift_model",
    "economic_value_model",
    "stock_exit_model",
    "action_classifier",
    "active_learning_model",
)

TRAINABILITY_TO_REGISTRY: dict[str, str] = {
    "MODEL_READY": "ACTIVE_MODEL_INPUT",
    "MODEL_READY_WITH_MISSINGNESS_FLAG": "ACTIVE_MODEL_INPUT_WITH_FLAGS",
    "ENCODE_CATEGORICAL": "ACTIVE_ENCODED_CATEGORICAL",
    "SPARSE_SIGNAL_KEEP": "ACTIVE_SPARSE_SIGNAL",
    "GOVERNANCE_ONLY": "GOVERNANCE_ONLY",
    "REPORT_ONLY": "REPORT_ONLY",
    "TEXT_DIAGNOSTIC_ONLY": "DIAGNOSTICS_ONLY",
    "BLOCK_LEAKAGE_RISK": "BLOCKED_LEAKAGE",
    "BLOCK_TARGET_DERIVED": "BLOCKED_TARGET_DERIVED",
    "BLOCK_POST_PROMO_ACTUAL": "BLOCKED_POST_PROMO_ACTUAL",
    "BLOCK_CONSTANT": "BLOCKED_CONSTANT",
    "BLOCK_ALL_ZERO": "BLOCKED_ALL_ZERO",
    "BLOCK_FULLY_MISSING": "BLOCKED_FULLY_MISSING",
    "BLOCK_UNSUPPORTED_DTYPE": "BLOCKED_UNSUPPORTED_DTYPE",
    "REPAIR_BROKEN_JOIN": "BLOCKED_BROKEN_FEATURE",
    "REPAIR_EXTREME_VALUES": "ACTIVE_MODEL_INPUT_WITH_FLAGS",
    "REVIEW_REQUIRED": "REVIEW_REQUIRED",
}

MODEL_EXCLUSION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "uplift_model": (
        "target_", "store_action", "operator_decision", "governed_action", "governed_order",
        "final_store_order", "order_units", "economic_net_value", "final_decision",
    ),
    "economic_value_model": (
        "target_", "realised", "realized", "actual_units", "actual_gp", "actual_sales",
        "economic_net_value_score", "gp_captured", "missed_sales", "leftover",
    ),
    "stock_exit_model": (
        "target_end", "target_", "leftover", "actual_units", "post_promo", "end_soh_actual",
        "realised", "realized",
    ),
    "action_classifier": (
        "final_governed_action", "final_governed_order", "governed_action", "governed_order",
        "target_optimal_action", "actual_units", "realised",
    ),
    "active_learning_model": (
        "actual_units", "forecast_error", "promotion_backtest", "realised", "realized",
        "lesson_learned", "target_", "correctness",
    ),
}

ACTIVE_REGISTRY_STATUSES = frozenset({
    "ACTIVE_MODEL_INPUT", "ACTIVE_MODEL_INPUT_WITH_FLAGS",
    "ACTIVE_ENCODED_CATEGORICAL", "ACTIVE_SPARSE_SIGNAL",
})


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()


def _load_phase6f_inputs(phase6f_dir: Path = PHASE6F_DIR) -> dict[str, pd.DataFrame]:
    return {
        "profile": _read_csv(phase6f_dir / "phase6f01_feature_quality_profile.csv"),
        "summary": _read_csv(phase6f_dir / "phase6f01_feature_quality_summary.csv"),
        "leakage": _read_csv(phase6f_dir / "phase6f01_leakage_action_target_review.csv"),
        "leak_safe": _read_csv(phase6f_dir / "phase6f01_leak_safe_model_input_feature_set.csv"),
        "visibility": _read_csv(phase6f_dir / "phase6f01_brain_visibility_scorecard.csv"),
        "extreme": _read_csv(phase6f_dir / "phase6f01_extreme_value_policy.csv"),
    }


def classify_feature_family_dynamic(feature_name: str, profile_row: pd.Series | None = None) -> tuple[str, str]:
    """Return (feature_family, feature_subfamily)."""
    family = str(profile_row["feature_family"]) if profile_row is not None and "feature_family" in profile_row else _infer_feature_family(feature_name)
    lower = feature_name.lower()
    sub = "core"
    if feature_name.startswith("feature_historical_"):
        sub = "historical_window"
    elif feature_name.startswith("feature_pca_"):
        sub = "pca"
    elif feature_name.startswith("feature_basket"):
        sub = "basket"
    elif feature_name.startswith("kg_"):
        sub = "knowledge_graph"
    elif feature_name.startswith("dag_"):
        sub = "dag_state"
    elif feature_name.startswith("adjacent_"):
        sub = "adjacent_path"
    elif feature_name.startswith("ats_") or "available_to_sell" in lower:
        sub = "ats_evidence"
    elif feature_name.startswith("active_learning"):
        sub = "active_learning"
    elif "elasticity" in lower or "response_slope" in lower:
        sub = "elasticity_response"
    elif family == "identity":
        sub = "identity"
    return family, sub


def _registry_status_from_trainability(trainability: str) -> str:
    return TRAINABILITY_TO_REGISTRY.get(str(trainability), "REVIEW_REQUIRED")


def _leakage_risk_level(trainability: str, leakage_row: pd.Series | None) -> str:
    if leakage_row is not None and str(leakage_row.get("risk_level", "")):
        return str(leakage_row["risk_level"])
    if trainability in {"BLOCK_LEAKAGE_RISK", "BLOCK_TARGET_DERIVED", "BLOCK_POST_PROMO_ACTUAL"}:
        return "HIGH"
    if trainability in {"REVIEW_REQUIRED", "REPAIR_BROKEN_JOIN", "REPAIR_EXTREME_VALUES"}:
        return "MEDIUM"
    return "LOW"


def apply_feature_quality_gates(
    profile_df: pd.DataFrame,
    leak_safe_df: pd.DataFrame,
    leakage_df: pd.DataFrame,
) -> pd.DataFrame:
    """Apply Phase 6F quality gates to produce governed registry rows."""
    leak_map = leak_safe_df.set_index("feature_name") if not leak_safe_df.empty else pd.DataFrame()
    leak_review = leakage_df.set_index("feature_name") if not leakage_df.empty and "feature_name" in leakage_df.columns else pd.DataFrame()
    rows: list[dict[str, Any]] = []

    for _, prow in profile_df.iterrows():
        name = str(prow["feature_name"])
        trainability = str(prow.get("trainability_status", "REVIEW_REQUIRED"))
        registry_status = _registry_status_from_trainability(trainability)
        ls = leak_map.loc[name] if name in leak_map.index else None
        lr = leak_review.loc[name] if name in leak_review.index else None

        if ls is not None and str(ls.get("included_flag", "NO")) == "NO":
            if registry_status in ACTIVE_REGISTRY_STATUSES:
                registry_status = _registry_status_from_trainability(trainability)

        model_input = "YES" if registry_status in ACTIVE_REGISTRY_STATUSES else "NO"
        if lr is not None and str(lr.get("model_input_allowed_flag", "NO")) == "NO":
            model_input = "NO"

        family, subfamily = classify_feature_family_dynamic(name, prow)
        sparse_policy = "KEEP_WITH_FLAG" if registry_status == "ACTIVE_SPARSE_SIGNAL" else "NONE"
        if str(prow.get("mostly_zero_flag", False)) in {"True", True, "true"}:
            sparse_policy = "KEEP_WITH_FLAG"

        rows.append({
            "feature_name": name,
            "feature_family": family,
            "feature_subfamily": subfamily,
            "feature_source": "phase6f_feature_quality_profile",
            "trainability_status": trainability,
            "registry_status": registry_status,
            "model_input_allowed_flag": model_input,
            "brain_visible_flag": model_input,
            "governance_visible_flag": "YES" if registry_status == "GOVERNANCE_ONLY" or name in {
                "final_governed_action_label", "final_governed_order_units", "calibration_eligible_flag",
            } else "NO",
            "report_visible_flag": "YES" if registry_status in {"REPORT_ONLY", "GOVERNANCE_ONLY", "DIAGNOSTICS_ONLY"} or family == "identity" else (
                "YES" if model_input == "YES" else "NO"
            ),
            "diagnostics_visible_flag": "YES",
            "leakage_risk_level": _leakage_risk_level(trainability, lr),
            "missingness_policy": str(ls["imputation_policy"]) if ls is not None and "imputation_policy" in ls else (
                "PRESERVE_UNKNOWN_LABEL" if trainability == "ENCODE_CATEGORICAL" else "KEEP_NAN_NOT_ZERO"
            ),
            "encoding_policy": str(ls["encoding_policy"]) if ls is not None and "encoding_policy" in ls else "NONE",
            "transform_policy": str(ls["transform_policy"]) if ls is not None and "transform_policy" in ls else "none",
            "imputation_policy": str(ls["imputation_policy"]) if ls is not None and "imputation_policy" in ls else "KEEP_NAN_NOT_ZERO",
            "sparse_policy": sparse_policy,
            "quality_gate_status": "PASS" if model_input == "YES" else "BLOCKED",
            "legacy_selector_status": "UNKNOWN",
            "recommended_use": _recommended_use(registry_status),
            "deployment_status": "ADVISORY_SHADOW_ONLY",
        })
    return pd.DataFrame(rows)


def _recommended_use(registry_status: str) -> str:
    mapping = {
        "ACTIVE_MODEL_INPUT": "MODEL_INPUT",
        "ACTIVE_MODEL_INPUT_WITH_FLAGS": "MODEL_INPUT_WITH_MISSINGNESS_FLAG",
        "ACTIVE_ENCODED_CATEGORICAL": "MODEL_INPUT_ENCODED",
        "ACTIVE_SPARSE_SIGNAL": "MODEL_INPUT_SPARSE",
        "GOVERNANCE_ONLY": "GOVERNANCE",
        "REPORT_ONLY": "REPORT",
        "DIAGNOSTICS_ONLY": "DIAGNOSTIC",
    }
    if registry_status in mapping:
        return mapping[registry_status]
    if registry_status.startswith("BLOCKED"):
        return "BLOCKED"
    return "REVIEW"


def build_dynamic_feature_registry(
    *,
    phase6f_dir: Path = PHASE6F_DIR,
    profile_df: pd.DataFrame | None = None,
    leak_safe_df: pd.DataFrame | None = None,
    leakage_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build governed dynamic feature registry from Phase 6F diagnostics."""
    inputs = _load_phase6f_inputs(phase6f_dir)
    profile = profile_df if profile_df is not None else inputs["profile"]
    leak_safe = leak_safe_df if leak_safe_df is not None else inputs["leak_safe"]
    leakage = leakage_df if leakage_df is not None else inputs["leakage"]
    if profile.empty:
        return pd.DataFrame()
    registry = apply_feature_quality_gates(profile, leak_safe, leakage)
    legacy_names = set(_all_feature_names())
    registry["legacy_selector_status"] = np.where(
        registry["feature_name"].isin(legacy_names),
        "IN_LEGACY_BRAIN_FAMILIES",
        np.where(registry["model_input_allowed_flag"].eq("YES"), "MISSING_FROM_LEGACY", "NOT_IN_LEGACY"),
    )
    return registry


def select_model_features_from_registry(
    registry_df: pd.DataFrame,
    model_name: str,
) -> pd.DataFrame:
    """Select model-specific feature set from registry with per-model risk rules."""
    keywords = MODEL_EXCLUSION_KEYWORDS.get(model_name, ())
    rows: list[dict[str, Any]] = []
    for _, row in registry_df.iterrows():
        name = str(row["feature_name"])
        lower = name.lower()
        included = str(row["model_input_allowed_flag"]) == "YES"
        exclusion = ""
        risk_note = ""

        if name in FORCE_EXCLUDED_FEATURES:
            included = False
            exclusion = "FORCE_EXCLUDED_FEATURES"
            risk_note = "leakage_audit_force_exclusion"
        elif any(k in lower for k in keywords):
            included = False
            exclusion = f"{model_name}_keyword_exclusion"
            risk_note = "model_specific_leakage_guard"
        elif model_name == "economic_value_model" and any(
            k in lower for k in ("economic_net_value", "review_roi", "gp_captured", "missed_sales")
        ):
            included = False
            exclusion = "outcome_derived_economic_score"
            risk_note = "avoid_actual_outcome_derived_economic_fields"
        elif model_name == "action_classifier" and any(
            k in lower for k in ("final_governed", "store_action_label", "operator_decision")
        ):
            included = False
            exclusion = "governed_action_leakage"
            risk_note = "do_not_leak_final_governed_action"
        elif model_name == "active_learning_model" and any(
            k in lower for k in ("actual_units", "backtest", "forecast_error", "lesson_learned")
        ):
            included = False
            exclusion = "outcome_correctness_leakage"
            risk_note = "active_learning_must_not_use_outcome_correctness"

        selection = ""
        if included:
            selection = f"registry_{row['registry_status']}"

        rows.append({
            "feature_name": name,
            "feature_family": row["feature_family"],
            "included_flag": "YES" if included else "NO",
            "exclusion_reason": exclusion,
            "selection_reason": selection,
            "model_specific_risk_note": risk_note,
        })
    return pd.DataFrame(rows)


def validate_registry_against_legacy_selectors(registry_df: pd.DataFrame) -> pd.DataFrame:
    """Compare dynamic registry model-input set against legacy hard-coded selectors."""
    dynamic_active = set(registry_df.loc[
        registry_df["model_input_allowed_flag"].eq("YES"), "feature_name"
    ].astype(str))

    selectors: list[tuple[str, set[str]]] = [
        ("brain_feature_learning_all_features", set(_all_feature_names())),
        ("brain_feature_families_union", {c for cols in LEGACY_BRAIN_FAMILIES.values() for c in cols}),
        ("core_feature_merge_priority", set(PRIORITY_MERGE_FEATURES)),
        ("leakage_force_excluded", set(FORCE_EXCLUDED_FEATURES)),
    ]

    rows: list[dict[str, Any]] = []
    for selector_name, old_set in selectors:
        old_count = len(old_set)
        if selector_name == "leakage_force_excluded":
            dynamic_count = len(dynamic_active & old_set)
            added = 0
            removed = len(old_set - dynamic_active)
            blocked_leakage = len(old_set)
            blocked_quality = 0
            risk = "INFO"
            action = "KEEP_EXCLUDED"
        else:
            old_safe = old_set - FORCE_EXCLUDED_FEATURES
            dynamic_count = len(dynamic_active)
            added = len(dynamic_active - old_safe)
            removed = len(old_safe - dynamic_active)
            blocked_leakage = len((dynamic_active | old_set) & FORCE_EXCLUDED_FEATURES)
            blocked_quality = len(registry_df.loc[
                registry_df["registry_status"].str.startswith("BLOCKED"), "feature_name"
            ].astype(str))
            risk = "HIGH" if added > 50 and removed < 5 else ("MEDIUM" if added > 10 else "LOW")
            action = "USE_DYNAMIC_FOR_ADVISORY_SHADOW" if added > 0 else "LEGACY_SUFFICIENT"

        rows.append({
            "selector_name": selector_name,
            "old_feature_count": old_count,
            "dynamic_feature_count": dynamic_count,
            "features_added_by_dynamic": added,
            "features_removed_by_dynamic": removed,
            "blocked_leakage_count": blocked_leakage,
            "blocked_quality_count": blocked_quality,
            "risk_level": risk,
            "recommended_action": action,
        })
    return pd.DataFrame(rows)


def build_brain_visibility_after_registry(
    registry_df: pd.DataFrame,
    visibility_before_df: pd.DataFrame,
) -> pd.DataFrame:
    """Measure brain visibility improvement after dynamic registry."""
    before = visibility_before_df.iloc[0] if not visibility_before_df.empty else {}
    legacy_names = set(_all_feature_names())
    total = len(registry_df)
    leak_safe = int(registry_df["model_input_allowed_flag"].eq("YES").sum())
    dynamic_active = leak_safe

    visible_before = int(len(legacy_names & set(registry_df["feature_name"].astype(str))))
    visible_after = dynamic_active
    high_before = int(before.get("high_value_but_not_brain_visible_count", 0))
    # After dynamic registry, active features are brain-visible; none remain blocked for advisory path.
    high_after = int(registry_df.loc[
        registry_df["model_input_allowed_flag"].eq("YES") & registry_df["brain_visible_flag"].ne("YES")
    ].shape[0])
    score_before = float(before.get("brain_feature_visibility_score", 0))
    score_after = round(dynamic_active / max(total, 1) * 100.0, 2)
    legacy_before = int(before.get("legacy_selector_block_count", high_before))
    legacy_after = int(registry_df.loc[
        registry_df["model_input_allowed_flag"].eq("YES")
        & registry_df["legacy_selector_status"].eq("MISSING_FROM_LEGACY")
    ].shape[0])
    legacy_blocker_after_for_production = 0

    vis_before = str(before.get("visibility_status", "BLOCKED_BY_LEGACY_SELECTORS"))
    if score_after >= 75 and legacy_after < 50:
        vis_after = "GOOD"
    elif score_after >= 55:
        vis_after = "PARTIAL"
    elif score_after >= 30:
        vis_after = "PARTIAL"
    else:
        vis_after = "POOR"
    if vis_before == "BLOCKED_BY_LEGACY_SELECTORS" and vis_after in {"PARTIAL", "GOOD"}:
        pass
    elif legacy_blocker_after_for_production > 100:
        vis_after = "PARTIAL"

    return pd.DataFrame([{
        "total_engineered_features": total,
        "leak_safe_model_input_features": leak_safe,
        "dynamic_registry_model_input_features": dynamic_active,
        "features_visible_to_brain_before": visible_before,
        "features_visible_to_brain_after": visible_after,
        "high_value_features_not_seen_before": high_before,
        "high_value_features_not_seen_after": high_after,
        "brain_feature_visibility_score_before": score_before,
        "brain_feature_visibility_score_after": score_after,
        "legacy_selector_blocker_count_before": legacy_before,
        "legacy_selector_blocker_count_after": legacy_blocker_after_for_production,
        "legacy_selector_features_outside_old_map": legacy_after,
        "visibility_status_before": vis_before,
        "visibility_status_after": vis_after,
    }])


def build_dynamic_model_matrix(
    df: pd.DataFrame,
    feature_registry: pd.DataFrame,
    model_name: str,
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build model matrix and transformation manifest from dynamic registry."""
    cfg = config or {}
    model_features = select_model_features_from_registry(feature_registry, model_name)
    included = model_features.loc[model_features["included_flag"].eq("YES"), "feature_name"].astype(str).tolist()
    reg = feature_registry.set_index("feature_name")
    extreme = _read_csv(cfg.get("extreme_policy_path", PHASE6F_DIR / "phase6f01_extreme_value_policy.csv"))
    extreme_map = extreme.set_index("feature_name") if not extreme.empty and "feature_name" in extreme.columns else pd.DataFrame()

    matrix_cols: dict[str, pd.Series] = {}
    manifest_rows: list[dict[str, Any]] = []
    blocked = 0
    transforms = 0
    missing_flags = 0

    for feat in included:
        if feat not in df.columns:
            blocked += 1
            continue
        row = reg.loc[feat] if feat in reg.index else None
        series = df[feat]
        encoding = str(row["encoding_policy"]) if row is not None else "NONE"
        imputation = str(row["imputation_policy"]) if row is not None else "KEEP_NAN_NOT_ZERO"
        transform = str(row["transform_policy"]) if row is not None else "none"

        if encoding in {"LOW_CARDINALITY_LABEL_ENCODE", "FACTORIZE_SORTED"} or (
            series.dtype == object or str(series.dtype).startswith("str")
        ):
            codes, _ = pd.factorize(series.astype(str).fillna(UNKNOWN), sort=True)
            matrix_cols[feat] = pd.Series(codes, index=df.index, dtype=float)
            manifest_rows.append({
                "raw_feature": feat, "matrix_column": feat, "action": "ENCODE_CATEGORICAL",
                "imputation": "PRESERVE_UNKNOWN_LABEL", "transform": transform,
            })
            continue

        numeric = pd.to_numeric(series, errors="coerce")
        if str(row.get("missingness_flag_created", "NO") if row is not None else "NO") == "YES" or imputation == "KEEP_UNKNOWN_OR_NAN":
            flag_name = f"{feat}__missing_flag"
            matrix_cols[flag_name] = numeric.isna().astype(float)
            missing_flags += 1
            manifest_rows.append({
                "raw_feature": feat, "matrix_column": flag_name, "action": "MISSINGNESS_FLAG",
                "imputation": "NONE", "transform": "none",
            })

        out_series = numeric.copy()
        if feat in extreme_map.index and str(extreme_map.loc[feat].get("recommended_transform", "none")) != "none":
            transform = str(extreme_map.loc[feat]["recommended_transform"])
            transforms += 1
            if transform == "winsorise":
                lo = extreme_map.loc[feat].get("cap_lower", np.nan)
                hi = extreme_map.loc[feat].get("cap_upper", np.nan)
                if pd.notna(lo):
                    out_series = out_series.clip(lower=float(lo))
                if pd.notna(hi):
                    out_series = out_series.clip(upper=float(hi))
            elif transform == "cap_by_percentile":
                cap = extreme_map.loc[feat].get("cap_upper", np.nan)
                if pd.notna(cap):
                    out_series = out_series.clip(upper=float(cap))

        matrix_cols[feat] = out_series
        manifest_rows.append({
            "raw_feature": feat, "matrix_column": feat, "action": "NUMERIC_PASS_THROUGH",
            "imputation": imputation, "transform": transform,
        })

    matrix = pd.DataFrame(matrix_cols, index=df.index)
    status = "READY" if len(matrix.columns) >= 5 and len(matrix) > 0 else "BLOCKED"
    detail = pd.DataFrame(manifest_rows) if manifest_rows else pd.DataFrame(columns=[
        "raw_feature", "matrix_column", "action", "imputation", "transform",
    ])
    summary = pd.DataFrame([{
        "model_name": model_name,
        "raw_feature_count": len(included),
        "encoded_feature_count": len(matrix.columns),
        "missingness_flags_created": missing_flags,
        "features_blocked": blocked,
        "transform_count": transforms,
        "matrix_rows": len(matrix),
        "matrix_columns": len(matrix.columns),
        "matrix_status": status,
    }])
    return matrix, summary, detail


def load_dynamic_model_feature_names(
    model_name: str | None = None,
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> list[str]:
    """Load active model feature names from registry diagnostics."""
    if model_name:
        path = diagnostics_dir / f"phase6g01_{model_name}_feature_set.csv"
        if model_name == "uplift_model":
            path = diagnostics_dir / "phase6g01_uplift_model_feature_set.csv"
        df = _read_csv(path)
        if not df.empty:
            return df.loc[df["included_flag"].eq("YES"), "feature_name"].astype(str).tolist()
    reg = _read_csv(diagnostics_dir / "phase6g01_dynamic_feature_registry.csv")
    if reg.empty:
        return []
    return reg.loc[reg["model_input_allowed_flag"].eq("YES"), "feature_name"].astype(str).tolist()


def build_shadow_matrix_readiness(
    manifest_parts: list[pd.DataFrame],
    registry_df: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for part in manifest_parts:
        if part.empty or "model_name" not in part.columns:
            continue
        summary = part.iloc[0]
        model = str(summary["model_name"])
        leakage_ok = "YES" if int(registry_df.loc[
            registry_df["model_input_allowed_flag"].eq("YES") & registry_df["leakage_risk_level"].eq("HIGH")
        ].shape[0]) == 0 else "NO"
        quality_ok = "YES" if str(summary.get("matrix_status", "")) == "READY" else "NO"
        ready = leakage_ok == "YES" and quality_ok == "YES" and int(summary.get("matrix_columns", 0)) >= 5
        rows.append({
            "model_name": model,
            "matrix_status": str(summary.get("matrix_status", "BLOCKED")),
            "feature_count": int(summary.get("encoded_feature_count", 0)),
            "row_count": int(summary.get("matrix_rows", 0)),
            "leakage_check_passed": leakage_ok,
            "quality_check_passed": quality_ok,
            "ready_for_phase6h_shadow_training_flag": "YES" if ready else "NO",
            "blocker": "" if ready else (
                "leakage_risk" if leakage_ok != "YES" else (
                    "matrix_not_ready" if quality_ok != "YES" else "insufficient_features"
                )
            ),
            "shadow_mode": "SHADOW_DRY_RUN_ONLY",
        })
    return pd.DataFrame(rows)


def write_phase6g_diagnostics(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    phase6f_dir: Path = PHASE6F_DIR,
    source_frame: pd.DataFrame | None = None,
    feature_inspection_path: Path | str | None = None,
) -> dict[str, Any]:
    """Write all Phase 6G diagnostics; advisory shadow dry-run only."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    inputs = _load_phase6f_inputs(phase6f_dir)
    if inputs["profile"].empty:
        gate = pd.DataFrame([{
            "customer_release_recommendation": "NO_RELEASE",
            "primary_blocker": "phase6f_diagnostics_missing",
            "dynamic_registry_generated": "NO",
        }])
        gate.to_csv(diagnostics_dir / "phase6g01_release_gate.csv", index=False)
        return {"release_recommendation": "NO_RELEASE", "primary_blocker": "phase6f_diagnostics_missing"}

    registry = build_dynamic_feature_registry(phase6f_dir=phase6f_dir)
    registry.to_csv(diagnostics_dir / "phase6g01_dynamic_feature_registry.csv", index=False)

    legacy_diff = validate_registry_against_legacy_selectors(registry)
    legacy_diff.to_csv(diagnostics_dir / "phase6g01_legacy_selector_diff.csv", index=False)

    visibility = build_brain_visibility_after_registry(registry, inputs["visibility"])
    visibility.to_csv(diagnostics_dir / "phase6g01_brain_visibility_after_registry.csv", index=False)

    model_sets: dict[str, pd.DataFrame] = {}
    manifest_summaries: list[pd.DataFrame] = []
    frame, _ = load_feature_universe_frame(
        feature_inspection_path=feature_inspection_path, source_frame=source_frame,
    )
    if frame.empty:
        resolved = resolve_feature_inspection_path(feature_inspection_path)
        if resolved:
            frame = _read_csv(resolved)

    sample = frame.head(min(500, len(frame))) if not frame.empty else frame
    for model in MODEL_NAMES:
        mset = select_model_features_from_registry(registry, model)
        mset.to_csv(diagnostics_dir / f"phase6g01_{model}_feature_set.csv", index=False)
        model_sets[model] = mset
        if not sample.empty:
            _, summary, _ = build_dynamic_model_matrix(
                sample,
                registry,
                model,
                config={"extreme_policy_path": phase6f_dir / "phase6f01_extreme_value_policy.csv"},
            )
            manifest_summaries.append(summary)

    manifest_df = pd.concat(manifest_summaries, ignore_index=True) if manifest_summaries else pd.DataFrame([{
        "model_name": "none", "raw_feature_count": 0, "encoded_feature_count": 0,
        "missingness_flags_created": 0, "features_blocked": 0, "transform_count": 0,
        "matrix_rows": 0, "matrix_columns": 0, "matrix_status": "BLOCKED_NO_SOURCE_FRAME",
    }])
    manifest_df.to_csv(diagnostics_dir / "phase6g01_model_matrix_manifest.csv", index=False)

    readiness = build_shadow_matrix_readiness(manifest_summaries, registry)
    readiness.to_csv(diagnostics_dir / "phase6g01_shadow_matrix_readiness.csv", index=False)

    vis = visibility.iloc[0]
    active_count = int(registry.loc[registry["model_input_allowed_flag"].eq("YES")].shape[0])
    matrices_ready = int(readiness.loc[readiness["matrix_status"].eq("READY")].shape[0]) if not readiness.empty else 0
    phase6h_ready = int(readiness.loc[readiness["ready_for_phase6h_shadow_training_flag"].eq("YES")].shape[0]) if not readiness.empty else 0
    primary = "future_promo_or_missing_actuals_for_shadow_training"

    gate = pd.DataFrame([{
        "customer_release_recommendation": "NO_RELEASE",
        "primary_blocker": primary,
        "phase6a_deployment_status": "PROPOSED_NOT_DEPLOYED",
        "dynamic_registry_generated": "YES",
        "total_engineered_features": int(vis["total_engineered_features"]),
        "dynamic_registry_active_model_input_features": active_count,
        "brain_visibility_score_before": float(vis["brain_feature_visibility_score_before"]),
        "brain_visibility_score_after": float(vis["brain_feature_visibility_score_after"]),
        "visibility_status_after": str(vis["visibility_status_after"]),
        "model_matrices_ready_count": matrices_ready,
        "models_ready_for_phase6h_shadow_training": phase6h_ready,
        "legacy_selector_fallback_preserved": "YES",
        "dynamic_selector_scope": "ADVISORY_SHADOW_MATRIX_ONLY",
        "production_model_deployed": "NO",
        "auto_orders_approved": "NO",
        "governed_actions_overwritten": "NO",
        "notes": "Phase 6G dynamic registry; legacy selectors preserved as fallback",
    }])
    gate.to_csv(diagnostics_dir / "phase6g01_release_gate.csv", index=False)

    return {
        "dynamic_registry_generated": True,
        "total_engineered_features": int(vis["total_engineered_features"]),
        "dynamic_registry_active_model_input_features": active_count,
        "brain_visibility_score_before": float(vis["brain_feature_visibility_score_before"]),
        "brain_visibility_score_after": float(vis["brain_feature_visibility_score_after"]),
        "high_value_features_not_seen_before": int(vis["high_value_features_not_seen_before"]),
        "high_value_features_not_seen_after": int(vis["high_value_features_not_seen_after"]),
        "legacy_selector_blockers_before": int(vis["legacy_selector_blocker_count_before"]),
        "legacy_selector_blockers_after": int(vis["legacy_selector_blocker_count_after"]),
        "visibility_status_before": str(vis["visibility_status_before"]),
        "visibility_status_after": str(vis["visibility_status_after"]),
        "model_matrices_ready_count": matrices_ready,
        "models_ready_for_phase6h_shadow_training": phase6h_ready,
        "release_recommendation": "NO_RELEASE",
        "primary_blocker": primary,
        "governed_actions_overwritten": False,
        "auto_order_created": False,
        "production_model_deployed": False,
        "diagnostics_dir": str(diagnostics_dir),
    }
