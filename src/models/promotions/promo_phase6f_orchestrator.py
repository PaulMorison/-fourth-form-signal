from __future__ import annotations

"""Phase 6F orchestrator — feature universe quality gate and advisory shadow comparison."""

from pathlib import Path
from typing import Any

import pandas as pd

from models.promotions.promo_feature_universe_quality import (
    DEFAULT_DIAGNOSTICS_DIR,
    write_phase6f_feature_quality_diagnostics,
)

PHASE6E_DIR = Path("Diagnostics/phase6e01_feature_merge_calibration_ats")
PHASE6A_DIR = Path("Diagnostics/phase6a01_segment_bias_calibration")

RELEASE_RECOMMENDATION = "NO_RELEASE"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _load_phase6e_feature_names() -> list[str]:
    plan = _read_csv(PHASE6E_DIR / "phase6e01_feature_merge_plan.csv")
    if plan.empty or "feature_name" not in plan.columns:
        return []
    safe = plan.loc[plan.get("merge_safety_status", plan.get("merge_status", pd.Series(""))).astype(str).eq("SAFE")]
    if safe.empty:
        safe = plan.loc[plan.get("merge_status", pd.Series("")).astype(str).isin({"MERGED_SAFE", "READY_TO_MERGE"})]
    return safe["feature_name"].astype(str).tolist()


def run_phase6f01_feature_universe_quality_gate(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    feature_inspection_path: Path | str | None = None,
    source_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Execute Phase 6F quality gate; never deploys production models."""
    phase6e_features = _load_phase6e_feature_names()
    result = write_phase6f_feature_quality_diagnostics(
        diagnostics_dir=diagnostics_dir,
        feature_inspection_path=feature_inspection_path,
        source_frame=source_frame,
        phase6e_feature_names=phase6e_features,
    )
    gate6a = _read_csv(PHASE6A_DIR / "phase6a01_release_gate.csv")
    if not gate6a.empty and "primary_blocker" in gate6a.columns:
        if result.get("primary_blocker") == "no_segment_calibration_allowed_rows":
            result["primary_blocker"] = str(gate6a.iloc[0]["primary_blocker"])
    result["release_recommendation"] = RELEASE_RECOMMENDATION
    return result


def write_phase6f_store_export_status(
    export_folder: str,
    phase6f_result: dict[str, Any],
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> pd.DataFrame:
    status = pd.DataFrame([{
        "run_id": f"phase6f01_store_772_export",
        "export_folder": export_folder,
        "reports_exported": ";".join([
            "PROMO_FEATURE_QUALITY_SUMMARY.csv",
            "PROMO_FEATURE_QUALITY_PROFILE.csv",
            "PROMO_BROKEN_FEATURE_REPAIR_PLAN.csv",
            "PROMO_EXTREME_VALUE_POLICY.csv",
            "PROMO_LEAKAGE_ACTION_TARGET_REVIEW.csv",
            "PROMO_BRAIN_VISIBILITY_SCORECARD.csv",
            "PROMO_LEAK_SAFE_MODEL_INPUT_FEATURE_SET.csv",
            "PROMO_SHADOW_MODEL_PERFORMANCE.csv",
            "PROMO_PHASE6F_RELEASE_GATE.csv",
        ]),
        "leak_safe_model_input_count": phase6f_result.get("leak_safe_model_input_count", 0),
        "brain_feature_visibility_score": phase6f_result.get("brain_feature_visibility_score", 0),
        "visibility_status": phase6f_result.get("visibility_status", ""),
        "shadow_training_status": phase6f_result.get("shadow_training_status", ""),
        "release_recommendation": phase6f_result.get("release_recommendation", RELEASE_RECOMMENDATION),
        "primary_blocker": phase6f_result.get("primary_blocker", ""),
    }])
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    status.to_csv(diagnostics_dir / "phase6f01_store_reporting_export_status.csv", index=False)
    return status
