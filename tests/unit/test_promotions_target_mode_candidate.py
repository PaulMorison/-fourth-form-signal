from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import (  # noqa: E402
    DEFAULT_PROMOTION_TRAINER_TARGET_MODE,
    PromotionModelTrainer,
    _ensure_historical_allocation_candidate_target_bundle,
    _resolve_promotion_trainer_target_mode,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


def _assembled_training_dataset(temp_dir: str, *, run_id: str):
    completed_base_frame = build_completed_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(completed_base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts", local_inspection_root=None)
    dataset = PromotionDatasetAssembler().assemble_training_dataset(
        run_id=run_id,
        base_frame=completed_base_frame,
        target_frame=target_result.frame,
        feature_frame=feature_result.frame,
        target_columns=target_result.target_columns,
        feature_columns=feature_result.feature_columns,
        artifact_paths=artifact_paths,
    )
    return dataset, artifact_paths


class PromotionTargetModeCandidateTests(unittest.TestCase):
    def test_target_mode_selection_is_strict_and_defaults_to_current_contract(self) -> None:
        self.assertEqual(
            _resolve_promotion_trainer_target_mode(None),
            DEFAULT_PROMOTION_TRAINER_TARGET_MODE,
        )
        self.assertEqual(
            _resolve_promotion_trainer_target_mode("historical_allocation_candidate"),
            "historical_allocation_candidate",
        )
        with self.assertRaisesRegex(ValueError, "Unsupported promotions trainer target_mode"):
            _resolve_promotion_trainer_target_mode("silent_primary_switch")

    def test_default_training_manifest_keeps_current_contract_and_no_target_mode_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_training_dataset(temp_dir, run_id="target-mode-default")
            training_artifacts = PromotionModelTrainer().train(
                run_id="target-mode-default",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            manifest_payload = json.loads(Path(training_artifacts.manifest_path).read_text(encoding="utf-8"))

        self.assertEqual(training_artifacts.target_mode, "current_trainer_contract")
        self.assertEqual(manifest_payload["target_mode"], "current_trainer_contract")
        self.assertIsNone(training_artifacts.target_mode_artifact_paths)
        self.assertNotIn("target_mode_comparison_summary_json", training_artifacts.artifact_files)

    def test_dual_contract_mode_writes_comparison_gate_and_shadow_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_training_dataset(temp_dir, run_id="target-mode-dual")
            training_artifacts = PromotionModelTrainer().train(
                run_id="target-mode-dual",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
                target_mode="dual_contract_diagnostics",
            )
            target_mode_paths = training_artifacts.target_mode_artifact_paths or {}
            summary_payload = json.loads(Path(target_mode_paths["summary_json_path"]).read_text(encoding="utf-8"))
            gate_payload = json.loads(Path(target_mode_paths["promotion_gate_json_path"]).read_text(encoding="utf-8"))
            bucket_payload = json.loads(Path(target_mode_paths["bucket_ranking_json_path"]).read_text(encoding="utf-8"))
            residual_payload = json.loads(Path(target_mode_paths["residual_examples_json_path"]).read_text(encoding="utf-8"))
            summary_frame = pd.read_csv(target_mode_paths["summary_csv_path"])
            for path_value in target_mode_paths.values():
                self.assertTrue(Path(path_value).exists())

        self.assertEqual(training_artifacts.target_mode, "dual_contract_diagnostics")
        self.assertEqual(summary_payload["target_mode"], "dual_contract_diagnostics")
        self.assertFalse(summary_payload["production_training_target_was_replaced"])
        self.assertEqual(summary_payload["production_training_target_contract"], "current_trainer_contract")
        self.assertIn("current_trainer_contract_shadow_model_vs_historical_business_target", summary_payload["comparison_blocks"])
        self.assertIn("historical_allocation_candidate_shadow_model_vs_historical_business_target", summary_payload["comparison_blocks"])
        self.assertTrue(gate_payload["historical_allocation_candidate_better_than_current_on_comparable_rows"])
        self.assertTrue(gate_payload["should_promote_to_candidate_for_shadow_training"])
        self.assertFalse(gate_payload["should_promote_to_candidate_for_primary_training"])
        self.assertTrue(gate_payload["should_current_trainer_contract_remain_primary"])
        self.assertTrue(gate_payload["policy_remains_paused"])
        self.assertFalse(gate_payload["policy_is_dominant_bottleneck"])
        self.assertIn("ranking_rows", bucket_payload)
        self.assertIn("rows", residual_payload)
        self.assertIn("metric_name", summary_frame.columns)

    def test_historical_candidate_mode_writes_shadow_artifacts_without_primary_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_training_dataset(temp_dir, run_id="target-mode-candidate")
            training_artifacts = PromotionModelTrainer().train(
                run_id="target-mode-candidate",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
                target_mode="historical_allocation_candidate",
            )
            target_mode_paths = training_artifacts.target_mode_artifact_paths or {}
            gate_payload = json.loads(Path(target_mode_paths["promotion_gate_json_path"]).read_text(encoding="utf-8"))

        self.assertEqual(training_artifacts.target_mode, "historical_allocation_candidate")
        self.assertTrue(target_mode_paths)
        self.assertFalse(gate_payload["should_promote_to_candidate_for_primary_training"])
        self.assertTrue(gate_payload["should_current_trainer_contract_remain_primary"])

    def test_historical_candidate_mode_fails_loud_when_evidence_is_missing(self) -> None:
        frame = pd.DataFrame(
            {
                "target_actual_units_sold": [5.0],
                "target_overallocation_flag": [0],
                "stock_basis_units": [6.0],
            }
        )

        with self.assertRaisesRegex(ValueError, "missing explicit historical allocation units source column"):
            _ensure_historical_allocation_candidate_target_bundle(frame)


if __name__ == "__main__":
    unittest.main()