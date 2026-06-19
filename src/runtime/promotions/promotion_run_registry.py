from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from runtime.promotions.config import PromotionArtifactPaths


_APPROVED_DRIFT_SIGNALS = {
    "stable",
    "improving",
    "degraded",
    "unknown",
}


@dataclass(frozen=True)
class PromotionRunRegistrySnapshot:
    model_approved: bool
    schema_approved: bool
    drift_signal: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


def resolve_artifact_paths(
    *,
    artifact_root: str | Path,
    env_file: str | Path | None,
    local_inspection_root: str | Path | None,
) -> PromotionArtifactPaths:
    return PromotionArtifactPaths.from_env(
        root=artifact_root,
        env_file=env_file,
        local_inspection_root=local_inspection_root,
    )


def inspect_registry_state(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    as_of_date: str | None,
) -> PromotionRunRegistrySnapshot:
    del run_id
    del as_of_date

    warnings: list[str] = []

    approved_model_registry_path = artifact_paths.registries_root / "approved_model_registry.json"
    schema_registry_path = artifact_paths.registries_root / "schema_contract_registry.json"

    model_approved = approved_model_registry_path.exists()
    if not model_approved:
        warnings.append(
            "approved_model_registry.json not found; treating model approval as unknown for this run."
        )

    schema_approved = schema_registry_path.exists()
    if not schema_approved:
        warnings.append(
            "schema_contract_registry.json not found; schema checks will block non-validation modes."
        )

    drift_signal = os.environ.get("PROMOTIONS_DRIFT_SIGNAL", "unknown").strip().lower()
    if drift_signal not in _APPROVED_DRIFT_SIGNALS:
        warnings.append(
            f"Unrecognized PROMOTIONS_DRIFT_SIGNAL '{drift_signal}'; using unknown."
        )
        drift_signal = "unknown"

    if not artifact_paths.root.exists():
        warnings.append(
            f"Artifact root does not exist yet: {artifact_paths.root}. It will be created by downstream runtime when needed."
        )

    return PromotionRunRegistrySnapshot(
        model_approved=model_approved,
        schema_approved=schema_approved,
        drift_signal=drift_signal,
        warnings=tuple(warnings),
    )


def expected_artifact_locations(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
) -> dict[str, str]:
    return {
        "operational_cycle_manifest": str(artifact_paths.operational_cycle_manifest_path(run_id)),
        "decision_surface_manifest": str(artifact_paths.decision_surface_manifest_path(run_id)),
        "store_prediction_manifest": str(artifact_paths.store_prediction_manifest_path(run_id)),
        "commercial_outcome_summary": str(artifact_paths.commercial_run_outcome_summary_path(run_id)),
    }
