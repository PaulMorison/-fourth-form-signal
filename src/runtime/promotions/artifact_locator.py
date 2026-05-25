from __future__ import annotations

"""Deterministic resolution of persisted promotions artifacts.

Canon ownership:
- Resolves explicit or latest persisted training-ready dataset artifacts.
- Resolves explicit or latest persisted promotions model bundles.
- Loads the manifest metadata needed for lineage-safe runtime selection.
- Does not own scoring, compatibility policy, or decision-surface reporting.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from models.promotions.model_bundle import read_json
from runtime.promotions.config import PromotionArtifactPaths


class PromotionArtifactLocatorError(FileNotFoundError):
    """Raised when a requested promotions artifact cannot be resolved safely."""


@dataclass(frozen=True)
class ResolvedPromotionTrainingReadyArtifact:
    dataset_path: str
    dataset_manifest_path: str
    run_id: str | None
    created_at_utc: str | None
    manifest: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedPromotionModelBundle:
    model_bundle_path: str
    model_manifest_path: str
    inference_schema_path: str
    run_id: str | None
    created_at_utc: str | None
    manifest: dict[str, object]
    inference_schema: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_training_ready_artifact(
    *,
    artifact_paths: PromotionArtifactPaths,
    dataset_path: str | Path | None = None,
    dataset_run_id: str | None = None,
) -> ResolvedPromotionTrainingReadyArtifact:
    """Resolve an explicit or latest persisted training-ready promotions artifact."""

    resolved_run_id: str | None = dataset_run_id
    if dataset_path is not None:
        resolved_dataset_path = Path(dataset_path).expanduser()
        resolved_run_id = resolved_dataset_path.parent.name or dataset_run_id
    elif dataset_run_id is not None:
        resolved_dataset_path = artifact_paths.training_dataset_path(dataset_run_id)
    else:
        latest_root = _latest_complete_run_root(
            artifact_paths.datasets_root,
            required_paths=("training_ready.parquet",),
            artifact_label="training-ready dataset",
        )
        resolved_dataset_path = latest_root / "training_ready.parquet"
        resolved_run_id = latest_root.name or None
    dataset_manifest_path = _resolve_dataset_manifest_path(
        artifact_paths=artifact_paths,
        resolved_dataset_path=resolved_dataset_path,
        run_id=resolved_run_id,
    )
    if not resolved_dataset_path.exists():
        raise PromotionArtifactLocatorError(
            f"Could not resolve training-ready dataset artifact: {resolved_dataset_path}"
        )
    manifest = _read_required_json(
        dataset_manifest_path,
        artifact_label="training-ready dataset manifest",
    )
    return ResolvedPromotionTrainingReadyArtifact(
        dataset_path=str(resolved_dataset_path),
        dataset_manifest_path=str(dataset_manifest_path),
        run_id=_string_or_none(manifest.get("run_id")) or resolved_run_id or resolved_dataset_path.parent.name,
        created_at_utc=_string_or_none(manifest.get("created_at_utc")),
        manifest=manifest,
    )


def resolve_model_bundle(
    *,
    artifact_paths: PromotionArtifactPaths,
    model_bundle_path: str | Path | None = None,
    model_run_id: str | None = None,
) -> ResolvedPromotionModelBundle:
    """Resolve an explicit or latest persisted promotions model bundle."""

    if model_bundle_path is not None:
        resolved_model_root = Path(model_bundle_path).expanduser()
    elif model_run_id is not None:
        resolved_model_root = artifact_paths.model_family_root(model_run_id)
    else:
        resolved_model_root = _latest_complete_run_root(
            artifact_paths.models_root,
            required_paths=("run_manifest.json", "inference_schema.json"),
            artifact_label="promotions model bundle",
        )
    if not resolved_model_root.exists():
        raise PromotionArtifactLocatorError(
            f"Could not resolve promotions model bundle: {resolved_model_root}"
        )
    manifest_path = resolved_model_root / "run_manifest.json"
    inference_schema_path = resolved_model_root / "inference_schema.json"
    manifest = _read_required_json(
        manifest_path,
        artifact_label="promotions model bundle manifest",
    )
    inference_schema = _read_required_json(
        inference_schema_path,
        artifact_label="promotions model inference schema",
    )
    return ResolvedPromotionModelBundle(
        model_bundle_path=str(resolved_model_root),
        model_manifest_path=str(manifest_path),
        inference_schema_path=str(inference_schema_path),
        run_id=_string_or_none(manifest.get("run_id")) or resolved_model_root.name,
        created_at_utc=_string_or_none(manifest.get("trained_at_utc")),
        manifest=manifest,
        inference_schema=inference_schema,
    )


def _latest_complete_run_root(
    root: Path,
    *,
    required_paths: tuple[str, ...],
    artifact_label: str,
) -> Path:
    if not root.exists():
        raise PromotionArtifactLocatorError(
            f"No persisted {artifact_label} roots exist under {root}"
        )
    candidate_roots = []
    for child in sorted(root.iterdir(), key=lambda path: path.name, reverse=True):
        if not child.is_dir():
            continue
        if all((child / relative_path).exists() for relative_path in required_paths):
            candidate_roots.append(child)
    if not candidate_roots:
        raise PromotionArtifactLocatorError(
            f"No complete persisted {artifact_label} artifacts exist under {root}"
        )
    return candidate_roots[0]


def _read_required_json(path: Path, *, artifact_label: str) -> dict[str, Any]:
    if not path.exists():
        raise PromotionArtifactLocatorError(f"Missing {artifact_label}: {path}")
    try:
        payload = read_json(path)
    except Exception as exc:  # pragma: no cover - defensive error shaping
        raise PromotionArtifactLocatorError(
            f"Could not read {artifact_label}: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise PromotionArtifactLocatorError(
            f"Invalid {artifact_label}: expected a JSON object in {path}"
        )
    return payload


def _resolve_dataset_manifest_path(
    *,
    artifact_paths: PromotionArtifactPaths,
    resolved_dataset_path: Path,
    run_id: str | None,
) -> Path:
    if run_id:
        manifest_path = artifact_paths.dataset_manifest_path(run_id)
        if manifest_path.exists():
            return manifest_path
    return resolved_dataset_path.with_name("dataset_manifest.json")


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None