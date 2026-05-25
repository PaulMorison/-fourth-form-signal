from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


EXPECTED_POLICY_BUCKETS = {
    "weak_same_discount_and_uplift",
    "weak_elasticity",
    "falling_base_launch_conflict",
    "stock_gap_high",
    "sparse_history_multi_driver",
}


class PromotionPolicyEffectivenessArtifactTests(unittest.TestCase):
    def test_policy_effectiveness_artifacts_persist_and_match_scoreboard_metrics(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-policy-effectiveness-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            training_artifacts = PromotionModelTrainer().train(
                run_id="promotions-policy-effectiveness-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            policy_paths = training_artifacts.policy_effectiveness_artifact_paths or {}
            self.assertEqual(
                set(policy_paths.keys()),
                {
                    "summary_json_path",
                    "summary_csv_path",
                    "bucket_ranking_json_path",
                    "bucket_ranking_csv_path",
                    "worst_bucket_residual_json_path",
                    "worst_bucket_residual_csv_path",
                },
            )
            for path_value in policy_paths.values():
                self.assertTrue(Path(path_value).exists())

            summary_payload = json.loads(Path(policy_paths["summary_json_path"]).read_text(encoding="utf-8"))
            summary_frame = pd.read_csv(policy_paths["summary_csv_path"])
            ranking_payload = json.loads(Path(policy_paths["bucket_ranking_json_path"]).read_text(encoding="utf-8"))
            ranking_frame = pd.read_csv(policy_paths["bucket_ranking_csv_path"])
            residual_payload = json.loads(
                Path(policy_paths["worst_bucket_residual_json_path"]).read_text(encoding="utf-8")
            )
            residual_frame = pd.read_csv(policy_paths["worst_bucket_residual_csv_path"])
            scoreboard_payload = json.loads(
                Path(training_artifacts.allocation_decision_scoreboard_json_path).read_text(encoding="utf-8")
            )

            self.assertEqual(summary_payload["row_scope"], "out_of_sample_validation_and_test")
            self.assertEqual(set(summary_payload["by_major_bucket"].keys()), EXPECTED_POLICY_BUCKETS)
            self.assertIn("section", summary_frame.columns)
            self.assertIn("metric_name", summary_frame.columns)
            self.assertIn("metric_value", summary_frame.columns)
            self.assertEqual(set(ranking_frame["bucket_name"].astype(str).tolist()), EXPECTED_POLICY_BUCKETS)
            self.assertEqual(ranking_payload["row_scope"], "out_of_sample_validation_and_test")
            self.assertEqual(ranking_payload["worst_remaining_bucket"], residual_payload["bucket_name"])
            self.assertLessEqual(len(residual_frame.index), 20)

            self.assertAlmostEqual(
                summary_payload["excess_units_mae_raw"],
                scoreboard_payload["policy_comparison_overall"]["excess_units_mae_raw"],
            )
            self.assertAlmostEqual(
                summary_payload["excess_units_mae_calibrated"],
                scoreboard_payload["policy_comparison_overall"]["excess_units_mae_calibrated"],
            )
            self.assertAlmostEqual(
                summary_payload["excess_units_mae_policy_adjusted"],
                scoreboard_payload["policy_comparison_overall"]["excess_units_mae_policy_adjusted"],
            )
            self.assertAlmostEqual(
                summary_payload["excess_capital_mae_raw"],
                scoreboard_payload["policy_comparison_overall"]["excess_capital_mae_raw"],
            )
            self.assertAlmostEqual(
                summary_payload["excess_capital_mae_calibrated"],
                scoreboard_payload["policy_comparison_overall"]["excess_capital_mae_calibrated"],
            )
            self.assertAlmostEqual(
                summary_payload["excess_capital_mae_policy_adjusted"],
                scoreboard_payload["policy_comparison_overall"]["excess_capital_mae_policy_adjusted"],
            )

            for column_name in (
                "bucket_name",
                "row_count",
                "raw_excess_capital_mae",
                "calibrated_excess_capital_mae",
                "policy_adjusted_excess_capital_mae",
                "improvement_amount",
                "improvement_percent",
                "top_policy_reason",
                "still_materially_bad_after_policy",
            ):
                self.assertIn(column_name, ranking_frame.columns)

            for column_name in (
                "bucket_name",
                "promotion_row_key",
                "policy_adjusted_excess_capital_abs_error",
                "policy_fired_flag",
                "policy_adjustment_reason",
                "review_override_flag",
                "same_discount_history_available_flag",
                "elasticity_confidence_score",
                "uplift_confidence_score",
                "base_trend_state",
                "launch_vs_total_conflict_score",
                "stock_vs_supported_gap_units",
            ):
                self.assertIn(column_name, residual_frame.columns)


if __name__ == "__main__":
    unittest.main()