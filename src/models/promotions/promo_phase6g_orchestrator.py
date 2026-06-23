from __future__ import annotations

"""Phase 6G orchestrator — dynamic feature registry and advisory shadow matrix dry-run."""

from pathlib import Path
from typing import Any

import pandas as pd

from models.promotions.promo_dynamic_feature_registry import (
    DEFAULT_DIAGNOSTICS_DIR,
    write_phase6g_diagnostics,
)

PHASE6F_DIR = Path("Diagnostics/phase6f01_feature_universe_quality_gate")
PHASE6A_DIR = Path("Diagnostics/phase6a01_segment_bias_calibration")
RELEASE_RECOMMENDATION = "NO_RELEASE"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def run_phase6g01_dynamic_feature_registry(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    phase6f_dir: Path = PHASE6F_DIR,
    source_frame: pd.DataFrame | None = None,
    feature_inspection_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build dynamic registry and matrix dry-run; never deploys production models."""
    result = write_phase6g_diagnostics(
        diagnostics_dir=diagnostics_dir,
        phase6f_dir=phase6f_dir,
        source_frame=source_frame,
        feature_inspection_path=feature_inspection_path,
    )
    gate6a = _read_csv(PHASE6A_DIR / "phase6a01_release_gate.csv")
    if not gate6a.empty and "primary_blocker" in gate6a.columns:
        if result.get("primary_blocker", "").startswith("awaiting"):
            pass
        elif result.get("primary_blocker") == "no_segment_calibration_allowed_rows":
            result["primary_blocker"] = str(gate6a.iloc[0]["primary_blocker"])
    result["release_recommendation"] = RELEASE_RECOMMENDATION
    return result


def write_phase6g_store_export_status(
    export_folder: str,
    phase6g_result: dict[str, Any],
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> pd.DataFrame:
    status = pd.DataFrame([{
        "run_id": "phase6g01_store_772_export",
        "export_folder": export_folder,
        "reports_exported": ";".join([
            "PROMO_DYNAMIC_FEATURE_REGISTRY.csv",
            "PROMO_LEGACY_SELECTOR_DIFF.csv",
            "PROMO_BRAIN_VISIBILITY_AFTER_REGISTRY.csv",
            "PROMO_UPLIFT_MODEL_FEATURE_SET.csv",
            "PROMO_ECONOMIC_VALUE_MODEL_FEATURE_SET.csv",
            "PROMO_STOCK_EXIT_MODEL_FEATURE_SET.csv",
            "PROMO_ACTION_CLASSIFIER_FEATURE_SET.csv",
            "PROMO_ACTIVE_LEARNING_MODEL_FEATURE_SET.csv",
            "PROMO_MODEL_MATRIX_MANIFEST.csv",
            "PROMO_SHADOW_MATRIX_READINESS.csv",
            "PROMO_PHASE6G_RELEASE_GATE.csv",
        ]),
        "dynamic_registry_active_model_input_features": phase6g_result.get("dynamic_registry_active_model_input_features", 0),
        "brain_visibility_score_after": phase6g_result.get("brain_visibility_score_after", 0),
        "visibility_status_after": phase6g_result.get("visibility_status_after", ""),
        "models_ready_for_phase6h_shadow_training": phase6g_result.get("models_ready_for_phase6h_shadow_training", 0),
        "release_recommendation": phase6g_result.get("release_recommendation", RELEASE_RECOMMENDATION),
        "primary_blocker": phase6g_result.get("primary_blocker", ""),
    }])
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    status.to_csv(diagnostics_dir / "phase6g01_store_reporting_export_status.csv", index=False)
    return status
