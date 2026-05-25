from __future__ import annotations

"""Explicit compatibility checks for promotions dataset and model artifacts.

Canon ownership:
- Validates that a persisted training-ready dataset manifest and a persisted
  promotions model bundle agree on the governed feature and target contract.
- Produces a deterministic compatibility result suitable for runtime failure,
  manifests, and operator inspection.
- Does not own artifact discovery, row scoring, or report persistence.
"""

from dataclasses import asdict, dataclass
from pathlib import Path

from runtime.promotions.artifact_locator import (
    ResolvedPromotionModelBundle,
    ResolvedPromotionTrainingReadyArtifact,
)


class PromotionArtifactCompatibilityError(ValueError):
    """Raised when persisted promotions artifacts are incompatible."""


@dataclass(frozen=True)
class PromotionArtifactCompatibilityResult:
    is_compatible: bool
    status: str
    dataset_run_id: str | None
    dataset_path: str
    dataset_manifest_path: str
    dataset_created_at: str | None
    dataset_feature_column_count: int | None
    dataset_target_column_count: int | None
    model_run_id: str | None
    model_bundle_path: str
    model_manifest_path: str
    model_created_at: str | None
    model_feature_column_count: int | None
    model_target_column_count: int | None
    dataset_lineage_relation: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_artifact_compatibility_result(
    *,
    dataset_artifact: ResolvedPromotionTrainingReadyArtifact,
    model_bundle: ResolvedPromotionModelBundle,
) -> PromotionArtifactCompatibilityResult:
    """Compare dataset and model manifests using explicit feature and target rules."""

    reasons: list[str] = []
    dataset_feature_columns = _string_tuple(dataset_artifact.manifest.get("feature_columns"))
    dataset_target_columns = _string_tuple(dataset_artifact.manifest.get("target_columns"))
    model_feature_columns = tuple(
        column_name
        for column_name in _string_tuple(model_bundle.inference_schema.get("feature_columns"))
        if column_name.startswith("feature_")
    )
    model_target_columns = _string_tuple(model_bundle.inference_schema.get("target_columns"))

    if dataset_feature_columns is None:
        reasons.append("dataset manifest is missing feature_columns")
    if dataset_target_columns is None:
        reasons.append("dataset manifest is missing target_columns")
    if not model_feature_columns:
        reasons.append("model inference schema is missing feature columns")
    if not model_target_columns:
        reasons.append("model inference schema is missing target columns")

    if (
        dataset_feature_columns is not None
        and model_feature_columns
        and not set(model_feature_columns).issubset(set(dataset_feature_columns))
    ):
        reasons.append(
            "dataset feature columns do not cover model inference feature columns"
        )
    if (
        dataset_target_columns is not None
        and model_target_columns
        and not set(model_target_columns).issubset(set(dataset_target_columns))
    ):
        reasons.append(
            "dataset target columns do not match model inference target columns"
        )

    model_training_dataset_path = Path(str(model_bundle.manifest.get("dataset_path", "") or "")).expanduser()
    dataset_lineage_relation = "incompatible"
    if not reasons:
        if model_training_dataset_path and Path(dataset_artifact.dataset_path).expanduser() == model_training_dataset_path:
            dataset_lineage_relation = "same_training_dataset"
        elif dataset_artifact.run_id == _dataset_run_id_from_model_path(model_training_dataset_path):
            dataset_lineage_relation = "same_training_dataset"
        else:
            dataset_lineage_relation = "schema_compatible_different_dataset"

    return PromotionArtifactCompatibilityResult(
        is_compatible=not reasons,
        status="compatible" if not reasons else "incompatible",
        dataset_run_id=dataset_artifact.run_id,
        dataset_path=dataset_artifact.dataset_path,
        dataset_manifest_path=dataset_artifact.dataset_manifest_path,
        dataset_created_at=dataset_artifact.created_at_utc,
        dataset_feature_column_count=len(dataset_feature_columns) if dataset_feature_columns is not None else None,
        dataset_target_column_count=len(dataset_target_columns) if dataset_target_columns is not None else None,
        model_run_id=model_bundle.run_id,
        model_bundle_path=model_bundle.model_bundle_path,
        model_manifest_path=model_bundle.model_manifest_path,
        model_created_at=model_bundle.created_at_utc,
        model_feature_column_count=len(model_feature_columns) if model_feature_columns else None,
        model_target_column_count=len(model_target_columns) if model_target_columns else None,
        dataset_lineage_relation=dataset_lineage_relation,
        reasons=tuple(reasons),
    )


def assert_artifact_compatibility(
    *,
    dataset_artifact: ResolvedPromotionTrainingReadyArtifact,
    model_bundle: ResolvedPromotionModelBundle,
) -> PromotionArtifactCompatibilityResult:
    """Return compatibility details or fail loudly with a deterministic message."""

    result = build_artifact_compatibility_result(
        dataset_artifact=dataset_artifact,
        model_bundle=model_bundle,
    )
    if not result.is_compatible:
        raise PromotionArtifactCompatibilityError(
            "Promotions artifact compatibility failed: " + "; ".join(result.reasons)
        )
    return result


def _string_tuple(raw_value: object) -> tuple[str, ...] | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, (list, tuple)):
        return None
    return tuple(str(value) for value in raw_value)


def _dataset_run_id_from_model_path(model_dataset_path: Path) -> str | None:
    if not model_dataset_path:
        return None
    if model_dataset_path.name != "training_ready.parquet":
        return None
    return model_dataset_path.parent.name or None