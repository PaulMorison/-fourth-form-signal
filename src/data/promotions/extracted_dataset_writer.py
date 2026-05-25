from __future__ import annotations

"""Persistence for governed promotions extraction outputs.

Canon ownership:
- Materializes the extracted base dataset and its manifest to surfaced artifact
  paths so later dataset, training, and scoring runs consume a stable asset.
- Keeps persistence decisions explicit at the artifact boundary instead of
  burying writes inside extraction logic.
- Does not own SQL execution, dataset assembly, or model artifact storage.
"""

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from data.promotions.promotion_base_extractor import PromotionExtractionManifest
from runtime.promotions.config import PromotionArtifactPaths


@dataclass(frozen=True)
class PersistedPromotionExtraction:
    base_path: Path
    manifest_path: Path


class PromotionExtractionWriter:
    """Write extracted promotions assets to deterministic parquet and JSON files."""

    def write(
        self,
        *,
        base_frame: pd.DataFrame,
        manifest: PromotionExtractionManifest,
        artifact_paths: PromotionArtifactPaths,
    ) -> PersistedPromotionExtraction:
        """Persist the base frame and manifest under the configured extraction root."""

        base_path = artifact_paths.extracted_base_path(manifest.run_id)
        manifest_path = artifact_paths.extracted_manifest_path(manifest.run_id)
        base_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: stage to *.tmp siblings then os.replace into the final
        # target so partially-written parquet/manifest files are never visible
        # to downstream readers. Matches the chunked writer's finalize contract.
        temp_base_path = base_path.with_suffix(base_path.suffix + ".tmp")
        temp_manifest_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        if temp_base_path.exists():
            temp_base_path.unlink()
        if temp_manifest_path.exists():
            temp_manifest_path.unlink()
        base_frame.to_parquet(temp_base_path, index=False)
        temp_manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_base_path.replace(base_path)
        temp_manifest_path.replace(manifest_path)
        return PersistedPromotionExtraction(
            base_path=base_path,
            manifest_path=manifest_path,
        )