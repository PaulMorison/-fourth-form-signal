from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.decision_surface_service import (  # noqa: E402
    load_training_ready_artifact,
    score_training_ready_rows,
)
from runtime.promotions.run_promotions_decision_surface import run_decision_surface  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_repeating_promotions_base_frame  # noqa: E402


def _build_training_ready_dataset(artifact_paths: PromotionArtifactPaths):
    base_frame = build_repeating_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    return PromotionDatasetAssembler().assemble_training_dataset(
        run_id="decision-surface-dataset",
        base_frame=base_frame,
        target_frame=target_result.frame,
        feature_frame=feature_result.frame,
        target_columns=target_result.target_columns,
        feature_columns=feature_result.feature_columns,
        artifact_paths=artifact_paths,
    )


class PromotionDecisionSurfaceRuntimeTests(unittest.TestCase):
    def test_dataset_scoring_uses_persisted_training_ready_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = _build_training_ready_dataset(artifact_paths)
            PromotionModelTrainer().train(
                run_id="decision-surface-model",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            loaded_artifact = load_training_ready_artifact(dataset.dataset_path)
            scored = score_training_ready_rows(
                loaded_artifact.frame,
                model_bundle_path=artifact_paths.model_family_root("decision-surface-model"),
            )

            self.assertEqual(loaded_artifact.dataset_path, dataset.dataset_path)
            self.assertIsNotNone(loaded_artifact.dataset_manifest)
            self.assertIn("predicted_units_sold", scored.scored_frame.columns)
            self.assertIn("predicted_overallocation_risk", scored.scored_frame.columns)
            self.assertIn("row_model_confidence_score", scored.scored_frame.columns)
            self.assertGreaterEqual(scored.model_reliability_score, 0.0)
            self.assertGreater(scored.feature_column_count, 0)

    def test_runtime_runner_writes_decision_surface_outputs_and_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = _build_training_ready_dataset(artifact_paths)
            PromotionModelTrainer().train(
                run_id="decision-surface-model",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            artifacts = run_decision_surface(
                dataset_path=dataset.dataset_path,
                model_bundle_path=str(artifact_paths.model_family_root("decision-surface-model")),
                artifact_root=str(artifact_paths.root),
                run_id="decision-surface-run",
                as_of_date="2024-09-01",
                minimum_cohort_sample_size=1,
                similarity_threshold=0.50,
                archetype_confidence_floor=0.35,
                row_model_confidence_floor=0.35,
            )

            self.assertTrue(Path(artifacts.decision_surface_manifest_path).exists())
            self.assertTrue(Path(artifacts.decision_surface_metrics_path).exists())
            self.assertTrue(Path(artifacts.calibration_summary_path).exists())
            self.assertTrue(Path(artifacts.calibration_thresholds_path).exists())
            self.assertTrue(Path(artifacts.diagnostics_summary_path).exists())
            self.assertIn("promotion_decision_surface", artifacts.report_paths)
            self.assertIn("promotion_sparse_history_list", artifacts.report_paths)
            self.assertIn("diagnostics_by_archetype", artifacts.report_paths)
            self.assertNotEqual(
                Path(artifacts.decision_surface_manifest_path),
                artifact_paths.cohort_manifest_path("decision-surface-run"),
            )
            self.assertNotEqual(
                Path(artifacts.decision_surface_manifest_path),
                artifact_paths.cohort_report_manifest_path("decision-surface-run"),
            )
