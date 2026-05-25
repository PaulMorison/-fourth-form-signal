from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.run_promotions_decision_surface import run_decision_surface  # noqa: E402
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


class PromotionDecisionSurfaceRealArtifactRuntimeTests(unittest.TestCase):
    def test_runtime_resolves_latest_real_artifacts_and_writes_inspection_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            old_dataset = _assemble_dataset(artifact_paths, run_id="20240101T000000Z")
            latest_dataset = _assemble_dataset(artifact_paths, run_id="20240201T000000Z")
            PromotionModelTrainer().train(
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

            artifacts = run_decision_surface(
                dataset_path=None,
                dataset_run_id=None,
                model_bundle_path=None,
                model_run_id=None,
                artifact_root=str(artifact_paths.root),
                run_id="decision-surface-real-artifacts",
                as_of_date="2024-09-01",
                minimum_cohort_sample_size=1,
                similarity_threshold=0.50,
                archetype_confidence_floor=0.35,
                row_model_confidence_floor=0.35,
            )

            self.assertTrue(Path(artifacts.decision_surface_manifest_path).exists())
            self.assertTrue(Path(artifacts.execution_summary_path).exists())
            self.assertTrue(Path(artifacts.inspection_manifest_path).exists())
            self.assertIn("inspection_management_review_rollup", artifacts.inspection_report_paths)
            self.assertIn("inspection_summary_by_archetype_secondary", artifacts.inspection_report_paths)

            decision_manifest = json.loads(
                Path(artifacts.decision_surface_manifest_path).read_text(encoding="utf-8")
            )
            execution_summary = json.loads(
                Path(artifacts.execution_summary_path).read_text(encoding="utf-8")
            )
            inspection_archetype_summary = pd.read_csv(
                artifacts.inspection_report_paths["inspection_summary_by_archetype_secondary"]["csv"]
            )

            self.assertEqual(decision_manifest["dataset_run_id"], "20240201T000000Z")
            self.assertEqual(decision_manifest["model_run_id"], "20240201T010000Z")
            self.assertEqual(decision_manifest["artifact_compatibility"]["status"], "compatible")
            self.assertEqual(
                execution_summary["dataset_artifact"]["run_id"],
                "20240201T000000Z",
            )
            self.assertEqual(
                execution_summary["model_artifact"]["run_id"],
                "20240201T010000Z",
            )
            self.assertEqual(
                execution_summary["inspection_manifest_path"],
                artifacts.inspection_manifest_path,
            )
            self.assertFalse(inspection_archetype_summary.empty)
            self.assertIn("cohort_key_archetype_secondary", inspection_archetype_summary.columns)
