from __future__ import annotations

"""Artifact manifests and inference schema for promotions model families."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromotionInferenceSchema:
    feature_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    target_columns: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionTrainingManifest:
    run_id: str
    trained_at_utc: str
    dataset_path: str
    target_mode: str
    split_summary: dict[str, str | int]
    feature_list_path: str
    metrics_path: str
    inference_schema_path: str
    artifact_files: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
