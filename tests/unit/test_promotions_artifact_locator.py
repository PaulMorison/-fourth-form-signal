from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.artifact_locator import (  # noqa: E402
    resolve_model_bundle,
    resolve_training_ready_artifact,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_repeating_promotions_base_frame  # noqa: E402


def _assemble_dataset(artifact_paths: PromotionArtifactPaths, run_id: str):
    base_frame = build_repeating_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    return PromotionDatasetAssembler().assemble_training_dataset(
        run_id=run_id,
        base_frame=base_frame,
        target_frame=target_result.frame,
        feature_frame=feature_result.frame,
        target_columns=target_result.target_columns,
        feature_columns=feature_result.feature_columns,
        artifact_paths=artifact_paths,
    )


class PromotionArtifactLocatorTests(unittest.TestCase):
    def test_locator_resolves_explicit_path_and_latest_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            old_dataset = _assemble_dataset(artifact_paths, run_id="20240101T000000Z")
            latest_dataset = _assemble_dataset(artifact_paths, run_id="20240201T000000Z")

            resolved_explicit = resolve_training_ready_artifact(
                artifact_paths=artifact_paths,
                dataset_path=old_dataset.dataset_path,
            )
            resolved_latest = resolve_training_ready_artifact(artifact_paths=artifact_paths)

            self.assertEqual(resolved_explicit.dataset_path, old_dataset.dataset_path)
            self.assertEqual(resolved_explicit.run_id, "20240101T000000Z")
            self.assertEqual(resolved_latest.dataset_path, latest_dataset.dataset_path)
            self.assertEqual(resolved_latest.run_id, "20240201T000000Z")
            self.assertIsNotNone(resolved_latest.created_at_utc)

    def test_locator_resolves_explicit_path_and_latest_model_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            old_dataset = _assemble_dataset(artifact_paths, run_id="20240101T000000Z")
            latest_dataset = _assemble_dataset(artifact_paths, run_id="20240201T000000Z")
            old_model = PromotionModelTrainer().train(
                run_id="20240101T010000Z",
                dataset=old_dataset.frame,
                dataset_path=old_dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            PromotionModelTrainer().train(
                run_id="20240201T010000Z",
                dataset=latest_dataset.frame,
                dataset_path=latest_dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            resolved_explicit = resolve_model_bundle(
                artifact_paths=artifact_paths,
                model_bundle_path=Path(old_model.artifact_root),
            )
            resolved_latest = resolve_model_bundle(artifact_paths=artifact_paths)

            self.assertEqual(resolved_explicit.model_bundle_path, old_model.artifact_root)
            self.assertEqual(resolved_explicit.run_id, "20240101T010000Z")
            self.assertEqual(
                resolved_latest.model_bundle_path,
                str(artifact_paths.model_family_root("20240201T010000Z")),
            )
            self.assertEqual(resolved_latest.run_id, "20240201T010000Z")
            self.assertIsNotNone(resolved_latest.created_at_utc)
