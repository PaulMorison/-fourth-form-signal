from __future__ import annotations

"""Advisory shadow retraining helpers using dynamic feature registry (Phase 6G)."""

from pathlib import Path
from typing import Any

import pandas as pd

from models.promotions.promo_brain_feature_learning import _all_feature_names, train_brain_value_models
from models.promotions.promo_dynamic_feature_registry import (
    DEFAULT_DIAGNOSTICS_DIR,
    build_dynamic_model_matrix,
    load_dynamic_model_feature_names,
    select_model_features_from_registry,
)
from models.promotions.promo_dynamic_feature_registry import build_dynamic_feature_registry as _build_registry

SHADOW_MODE = "SHADOW_DRY_RUN_ONLY"


def resolve_shadow_feature_names(
    model_name: str | None = None,
    *,
    use_dynamic_registry: bool = True,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> list[str]:
    """Resolve feature names for advisory shadow pipelines; legacy fallback preserved."""
    if use_dynamic_registry:
        dynamic = load_dynamic_model_feature_names(model_name, diagnostics_dir=diagnostics_dir)
        if dynamic:
            return dynamic
        registry = _build_registry()
        if not registry.empty and model_name:
            return select_model_features_from_registry(registry, model_name).loc[
                lambda d: d["included_flag"].eq("YES"), "feature_name"
            ].astype(str).tolist()
    return _all_feature_names()


def run_shadow_matrix_dry_run(
    frame: pd.DataFrame,
    model_name: str,
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    """Build advisory model matrix only; does not persist production models."""
    registry = _build_registry()
    matrix, summary, detail = build_dynamic_model_matrix(frame, registry, model_name)
    return {
        "shadow_mode": SHADOW_MODE,
        "model_name": model_name,
        "matrix": matrix,
        "summary": summary,
        "detail": detail,
        "feature_names": resolve_shadow_feature_names(model_name, diagnostics_dir=diagnostics_dir),
    }


def run_advisory_shadow_training_dry_run(
    training_df: pd.DataFrame,
    *,
    model_name: str | None = None,
    use_dynamic_registry: bool = True,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> dict[str, Any]:
    """Optional lightweight shadow sanity train; never deploys artifacts."""
    feature_names = resolve_shadow_feature_names(model_name, use_dynamic_registry=use_dynamic_registry, diagnostics_dir=diagnostics_dir)
    result = train_brain_value_models(
        training_df,
        config={
            "feature_names": feature_names,
            "use_dynamic_registry": use_dynamic_registry,
            "model_name": model_name,
            "shadow_mode": SHADOW_MODE,
        },
    )
    result["shadow_mode"] = SHADOW_MODE
    result["production_deployed"] = False
    return result
