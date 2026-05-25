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
    PromotionModelTrainer,
    _build_policy_replay_diagnostic_frame,
    _build_policy_replay_effectiveness_artifacts,
)
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


class PromotionPolicyReplayEffectivenessArtifactTests(unittest.TestCase):
    def test_replay_formulas_use_historical_allocation_and_realised_units(self) -> None:
        dataset = pd.DataFrame(
            {
                "pl_allocation_qty": [10.0, 8.0, pd.NA, 5.0, pd.NA],
                "actual_units_sold_promo": [6.0, 9.0, 4.0, pd.NA, pd.NA],
                "effective_cost_per_unit": [2.0, 3.0, 4.0, 5.0, pd.NA],
            }
        )
        policy_adjustments = pd.DataFrame(
            {
                "policy_units_removed": [3.0, 2.0, 1.0, 1.0, 1.0],
                "policy_adjustment_fired_flag": [1.0, 1.0, 1.0, 1.0, 1.0],
            },
            index=dataset.index,
        )

        replay_frame = _build_policy_replay_diagnostic_frame(
            dataset,
            policy_adjustments=policy_adjustments,
        )

        self.assertEqual(float(replay_frame.loc[0, "historical_allocated_units"]), 10.0)
        self.assertEqual(float(replay_frame.loc[0, "realised_units_sold_promo"]), 6.0)
        self.assertEqual(float(replay_frame.loc[0, "historical_excess_units"]), 4.0)
        self.assertEqual(float(replay_frame.loc[0, "replay_policy_units"]), 7.0)
        self.assertEqual(float(replay_frame.loc[0, "replay_policy_excess_units"]), 1.0)
        self.assertEqual(float(replay_frame.loc[0, "replay_units_removed"]), 3.0)
        self.assertEqual(float(replay_frame.loc[0, "replay_capital_removed"]), 6.0)

        self.assertEqual(float(replay_frame.loc[1, "historical_excess_units"]), 0.0)
        self.assertEqual(float(replay_frame.loc[1, "replay_policy_excess_units"]), 0.0)
        self.assertEqual(float(replay_frame.loc[1, "replay_units_removed"]), 0.0)
        self.assertEqual(float(replay_frame.loc[1, "replay_capital_removed"]), 0.0)

        self.assertEqual(float(replay_frame.loc[2, "replay_measurement_eligible_flag"]), 0.0)
        self.assertEqual(
            replay_frame.loc[2, "replay_exclusion_reason"],
            "missing_historical_allocation_units",
        )
        self.assertEqual(float(replay_frame.loc[3, "replay_measurement_eligible_flag"]), 0.0)
        self.assertEqual(
            replay_frame.loc[3, "replay_exclusion_reason"],
            "missing_realised_promo_units",
        )
        self.assertEqual(float(replay_frame.loc[4, "replay_measurement_eligible_flag"]), 0.0)
        self.assertEqual(
            replay_frame.loc[4, "replay_exclusion_reason"],
            "multiple_missing_replay_inputs",
        )

    def test_replay_bucket_ranking_reports_truthful_bucket_metrics(self) -> None:
        rows = pd.DataFrame(
            {
                "weak_same_discount_history": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
                "weak_uplift": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
                "weak_elasticity": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
                "falling_base": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "launch_total_conflict": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "feature_order_risk_reason_stock_vs_supported_gap_high_flag": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "sparse_history_multi_driver": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "replay_measurement_eligible_flag": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                "policy_adjustment_fired_flag": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                "policy_adjustment_reason": [
                    "same_discount_uplift_cap",
                    "same_discount_uplift_cap",
                    "same_discount_uplift_cap",
                    "weak_elasticity_cap",
                    "weak_elasticity_cap",
                    "weak_elasticity_cap",
                ],
                "historical_excess_units": [5.0, 4.0, 3.0, 6.0, 5.0, 4.0],
                "historical_excess_capital": [50.0, 40.0, 30.0, 120.0, 100.0, 80.0],
                "replay_policy_excess_units": [1.0, 1.0, 0.0, 5.0, 4.0, 3.0],
                "replay_policy_excess_capital": [10.0, 10.0, 0.0, 100.0, 80.0, 60.0],
                "replay_units_removed": [4.0, 3.0, 3.0, 1.0, 1.0, 1.0],
                "replay_capital_removed": [40.0, 30.0, 30.0, 20.0, 20.0, 20.0],
                "promotion_row_key": ["a", "b", "c", "d", "e", "f"],
                "store_number": ["1", "1", "2", "2", "3", "3"],
                "sku_number": ["11", "12", "13", "14", "15", "16"],
                "split_name": ["validation", "validation", "test", "validation", "test", "test"],
                "historical_allocation_source_column": ["pl_allocation_qty"] * 6,
                "realised_units_source_column": ["actual_units_sold_promo"] * 6,
                "replay_unit_cost_source_column": ["effective_cost_per_unit"] * 6,
                "historical_allocated_units": [10.0, 9.0, 8.0, 11.0, 10.0, 9.0],
                "realised_units_sold_promo": [5.0, 5.0, 5.0, 5.0, 5.0, 5.0],
                "replay_policy_units": [6.0, 6.0, 5.0, 10.0, 9.0, 8.0],
                "review_override_flag": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                "stock_vs_supported_gap_units": [0.0, 0.0, 0.0, 2.0, 2.0, 1.0],
            }
        )

        artifacts = _build_policy_replay_effectiveness_artifacts(rows)

        summary_payload = artifacts["summary_payload"]
        ranking_payload = artifacts["bucket_ranking_payload"]
        ranking_frame = artifacts["bucket_ranking_frame"]

        self.assertEqual(set(summary_payload["by_major_bucket"].keys()), EXPECTED_POLICY_BUCKETS)
        weak_bucket_metrics = summary_payload["by_major_bucket"]["weak_same_discount_and_uplift"]
        elasticity_bucket_metrics = summary_payload["by_major_bucket"]["weak_elasticity"]
        self.assertEqual(int(weak_bucket_metrics["row_count"]), 3)
        self.assertAlmostEqual(float(weak_bucket_metrics["historical_excess_capital_mean"]), 40.0)
        self.assertAlmostEqual(float(weak_bucket_metrics["replay_policy_excess_capital_mean"]), 20.0 / 3.0)
        self.assertEqual(int(elasticity_bucket_metrics["row_count"]), 3)
        self.assertAlmostEqual(float(elasticity_bucket_metrics["replay_policy_excess_capital_mean"]), 80.0)
        self.assertEqual(ranking_payload["worst_remaining_bucket"], "weak_elasticity")
        self.assertEqual(str(ranking_frame.iloc[0]["bucket_name"]), "weak_elasticity")
        self.assertTrue(bool(ranking_frame.iloc[0]["materially_bad_flag"]))
        self.assertAlmostEqual(float(ranking_frame.iloc[0]["share_of_total_historical_excess_capital"]), 300.0 / 420.0)

    def test_replay_zero_residual_guard_leaves_no_worst_bucket(self) -> None:
        rows = pd.DataFrame(
            {
                "weak_same_discount_history": [1.0, 0.0],
                "weak_uplift": [1.0, 0.0],
                "weak_elasticity": [0.0, 1.0],
                "falling_base": [0.0, 0.0],
                "launch_total_conflict": [0.0, 0.0],
                "feature_order_risk_reason_stock_vs_supported_gap_high_flag": [0.0, 0.0],
                "sparse_history_multi_driver": [0.0, 0.0],
                "replay_measurement_eligible_flag": [1.0, 1.0],
                "policy_adjustment_fired_flag": [1.0, 1.0],
                "policy_adjustment_reason": ["same_discount_uplift_cap", "weak_elasticity_cap"],
                "historical_excess_units": [2.0, 3.0],
                "historical_excess_capital": [10.0, 12.0],
                "replay_policy_excess_units": [0.0, 0.0],
                "replay_policy_excess_capital": [0.0, 0.0],
                "replay_units_removed": [2.0, 3.0],
                "replay_capital_removed": [10.0, 12.0],
            }
        )

        artifacts = _build_policy_replay_effectiveness_artifacts(rows)

        self.assertIsNone(artifacts["bucket_ranking_payload"]["worst_remaining_bucket"])
        self.assertTrue(artifacts["worst_bucket_residual_frame"].empty)

    def test_replay_artifacts_persist_with_trainer_owned_paths(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-policy-replay-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            training_artifacts = PromotionModelTrainer().train(
                run_id="promotions-policy-replay-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            replay_paths = training_artifacts.policy_replay_effectiveness_artifact_paths or {}
            self.assertEqual(
                set(replay_paths.keys()),
                {
                    "summary_json_path",
                    "summary_csv_path",
                    "bucket_ranking_json_path",
                    "bucket_ranking_csv_path",
                    "worst_bucket_residual_json_path",
                    "worst_bucket_residual_csv_path",
                },
            )
            for path_value in replay_paths.values():
                self.assertTrue(Path(path_value).exists())

            summary_payload = json.loads(Path(replay_paths["summary_json_path"]).read_text(encoding="utf-8"))
            summary_frame = pd.read_csv(replay_paths["summary_csv_path"])
            ranking_payload = json.loads(Path(replay_paths["bucket_ranking_json_path"]).read_text(encoding="utf-8"))
            ranking_frame = pd.read_csv(replay_paths["bucket_ranking_csv_path"])
            residual_payload = json.loads(
                Path(replay_paths["worst_bucket_residual_json_path"]).read_text(encoding="utf-8")
            )
            residual_frame = pd.read_csv(replay_paths["worst_bucket_residual_csv_path"])

            self.assertEqual(summary_payload["row_scope"], "out_of_sample_validation_and_test")
            self.assertEqual(set(summary_payload["by_major_bucket"].keys()), EXPECTED_POLICY_BUCKETS)
            self.assertIn("replay_exclusion_reason_counts", summary_payload)
            self.assertIn("section", summary_frame.columns)
            self.assertIn("metric_name", summary_frame.columns)
            self.assertIn("metric_value", summary_frame.columns)
            self.assertEqual(set(ranking_frame["bucket_name"].astype(str).tolist()), EXPECTED_POLICY_BUCKETS)
            self.assertEqual(ranking_payload["worst_remaining_bucket"], residual_payload["bucket_name"])
            self.assertLessEqual(len(residual_frame.index), 20)


if __name__ == "__main__":
    unittest.main()
