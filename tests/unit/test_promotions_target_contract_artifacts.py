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
    _build_target_contract_artifacts,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


def _base_target_contract_row() -> dict[str, object]:
    return {
        "promotion_row_key": "row",
        "store_number": "1",
        "sku_number": "100",
        "split_name": "validation",
        "stock_basis_units": 10.0,
        "demand_reference_units": 5.0,
        "actual_units_sold": 5.0,
        "unit_cost": 2.0,
        "raw_predicted_units_total_promo": 5.0,
        "calibrated_predicted_units_total_promo": 5.0,
        "policy_adjusted_predicted_units_total_promo": 5.0,
        "actual_overallocation_flag": 1.0,
        "replay_measurement_eligible_flag": 1.0,
        "replay_exclusion_reason": "eligible",
        "historical_allocated_units": 10.0,
        "realised_units_sold_promo": 5.0,
        "replay_unit_cost": 2.0,
    }


def _target_contract_row(name: str, **overrides: object) -> dict[str, object]:
    row = _base_target_contract_row()
    row["promotion_row_key"] = name
    row["store_number"] = str(overrides.pop("store_number", name))
    row["sku_number"] = str(overrides.pop("sku_number", name))
    row.update(overrides)
    return row


class PromotionTargetContractArtifactTests(unittest.TestCase):
    def test_target_contract_diagnostics_separate_divergence_drivers_and_contract_gaps(self) -> None:
        rows = pd.DataFrame(
            [
                _target_contract_row(
                    "stock-basis",
                    stock_basis_units=20.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=5.0,
                    realised_units_sold_promo=5.0,
                    demand_reference_units=5.0,
                    unit_cost=2.0,
                    replay_unit_cost=2.0,
                    calibrated_predicted_units_total_promo=8.0,
                    policy_adjusted_predicted_units_total_promo=7.0,
                    actual_overallocation_flag=1.0,
                ),
                _target_contract_row(
                    "realised-promo",
                    stock_basis_units=10.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=10.0,
                    realised_units_sold_promo=4.0,
                    demand_reference_units=4.0,
                    unit_cost=3.0,
                    replay_unit_cost=3.0,
                    calibrated_predicted_units_total_promo=9.0,
                    policy_adjusted_predicted_units_total_promo=8.0,
                    actual_overallocation_flag=0.0,
                ),
                _target_contract_row(
                    "cost-basis",
                    stock_basis_units=10.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=5.0,
                    realised_units_sold_promo=5.0,
                    demand_reference_units=5.0,
                    unit_cost=1.0,
                    replay_unit_cost=4.0,
                    calibrated_predicted_units_total_promo=6.0,
                    policy_adjusted_predicted_units_total_promo=5.0,
                    actual_overallocation_flag=1.0,
                ),
                _target_contract_row(
                    "demand-reference",
                    stock_basis_units=10.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=5.0,
                    realised_units_sold_promo=5.0,
                    demand_reference_units=25.0,
                    unit_cost=2.0,
                    replay_unit_cost=2.0,
                    calibrated_predicted_units_total_promo=5.0,
                    policy_adjusted_predicted_units_total_promo=5.0,
                    actual_overallocation_flag=0.0,
                ),
                _target_contract_row(
                    "missing-historical",
                    historical_allocated_units=pd.NA,
                    replay_measurement_eligible_flag=0.0,
                    replay_exclusion_reason="missing_historical_allocation_units",
                ),
                _target_contract_row(
                    "missing-realised",
                    realised_units_sold_promo=pd.NA,
                    replay_measurement_eligible_flag=0.0,
                    replay_exclusion_reason="missing_realised_promo_units",
                ),
            ]
        )

        artifacts = _build_target_contract_artifacts(rows)

        diagnostic_frame = artifacts["divergence_diagnostics_frame"]
        summary_payload = artifacts["summary_payload"]
        comparison_blocks = summary_payload["comparison_blocks"]

        self.assertEqual(
            diagnostic_frame["dominant_divergence_driver"].astype(str).tolist(),
            [
                "stock_basis_proxy_mismatch",
                "realised_promo_units_mismatch",
                "cost_basis_mismatch",
                "demand_reference_mismatch",
                "missing_historical_allocation_evidence",
                "missing_realised_promo_evidence",
            ],
        )
        self.assertTrue(summary_payload["current_trainer_target_misaligned_with_business_mistake"])
        self.assertEqual(summary_payload["top_divergence_driver"], "stock_basis_proxy_mismatch")
        self.assertAlmostEqual(
            float(comparison_blocks["current_trainer_vs_historical_allocation_contract"]["capital_gap_abs_total"]),
            53.0,
        )
        self.assertAlmostEqual(
            float(comparison_blocks["calibrated_forecast_vs_historical_allocation_contract"]["capital_gap_abs_total"]),
            33.0,
        )
        self.assertAlmostEqual(
            float(comparison_blocks["policy_replay_vs_historical_allocation_contract"]["capital_gap_abs_total"]),
            42.0,
        )
        self.assertEqual(
            int(comparison_blocks["current_target_flag_vs_historical_allocation_contract"]["disagreement_row_count"]),
            2,
        )

    def test_target_contract_candidate_prefers_historical_allocation_when_stock_basis_dominates(self) -> None:
        rows = pd.DataFrame(
            [
                _target_contract_row(
                    f"stock-{index}",
                    stock_basis_units=20.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=5.0,
                    realised_units_sold_promo=5.0,
                    demand_reference_units=5.0,
                    unit_cost=2.0,
                    replay_unit_cost=2.0,
                    calibrated_predicted_units_total_promo=8.0,
                    policy_adjusted_predicted_units_total_promo=7.0,
                    actual_overallocation_flag=1.0,
                )
                for index in range(5)
            ]
            + [
                _target_contract_row(
                    "cost-noise",
                    stock_basis_units=10.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=5.0,
                    realised_units_sold_promo=5.0,
                    demand_reference_units=5.0,
                    unit_cost=1.0,
                    replay_unit_cost=2.0,
                    calibrated_predicted_units_total_promo=5.0,
                    policy_adjusted_predicted_units_total_promo=5.0,
                    actual_overallocation_flag=1.0,
                )
            ]
        )

        artifacts = _build_target_contract_artifacts(rows)
        candidate_payload = artifacts["next_target_refinement_candidate_payload"]

        self.assertEqual(
            candidate_payload["next_target_refinement_candidate"],
            "historical_allocation_target_refinement",
        )
        self.assertEqual(candidate_payload["replay_target_design_position"], "candidate_for_target_design")
        self.assertTrue(candidate_payload["policy_work_should_remain_paused"])

    def test_target_contract_candidate_returns_none_when_divergence_is_diffuse(self) -> None:
        rows = pd.DataFrame(
            [
                _target_contract_row(
                    f"stock-{index}",
                    stock_basis_units=20.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=5.0,
                    realised_units_sold_promo=5.0,
                    demand_reference_units=5.0,
                    unit_cost=2.0,
                    replay_unit_cost=2.0,
                    calibrated_predicted_units_total_promo=8.0,
                    policy_adjusted_predicted_units_total_promo=7.0,
                    actual_overallocation_flag=1.0,
                )
                for index in range(5)
            ]
            + [
                _target_contract_row(
                    f"realised-{index}",
                    stock_basis_units=10.0,
                    historical_allocated_units=10.0,
                    actual_units_sold=10.0,
                    realised_units_sold_promo=5.0,
                    demand_reference_units=5.0,
                    unit_cost=4.0,
                    replay_unit_cost=4.0,
                    calibrated_predicted_units_total_promo=9.0,
                    policy_adjusted_predicted_units_total_promo=8.0,
                    actual_overallocation_flag=0.0,
                )
                for index in range(5)
            ]
        )

        artifacts = _build_target_contract_artifacts(rows)
        candidate_payload = artifacts["next_target_refinement_candidate_payload"]

        self.assertEqual(candidate_payload["next_target_refinement_candidate"], "none")
        self.assertIn("too close in weight", candidate_payload["explanation"])

    def test_target_contract_artifacts_persist_with_trainer_owned_paths(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-target-contract-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            training_artifacts = PromotionModelTrainer().train(
                run_id="promotions-target-contract-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            target_contract_paths = training_artifacts.target_contract_artifact_paths or {}
            self.assertEqual(
                set(target_contract_paths.keys()),
                {
                    "summary_json_path",
                    "summary_csv_path",
                    "bucket_ranking_json_path",
                    "bucket_ranking_csv_path",
                    "residual_examples_json_path",
                    "residual_examples_csv_path",
                    "row_diagnostics_parquet_path",
                    "divergence_diagnostics_csv_path",
                    "divergence_summary_json_path",
                    "next_target_refinement_candidate_json_path",
                    "next_target_promotion_decision_json_path",
                },
            )
            for path_value in target_contract_paths.values():
                self.assertTrue(Path(path_value).exists())

            summary_payload = json.loads(Path(target_contract_paths["summary_json_path"]).read_text(encoding="utf-8"))
            summary_frame = pd.read_csv(target_contract_paths["summary_csv_path"])
            ranking_payload = json.loads(
                Path(target_contract_paths["bucket_ranking_json_path"]).read_text(encoding="utf-8")
            )
            divergence_summary_payload = json.loads(
                Path(target_contract_paths["divergence_summary_json_path"]).read_text(encoding="utf-8")
            )
            candidate_payload = json.loads(
                Path(target_contract_paths["next_target_refinement_candidate_json_path"]).read_text(encoding="utf-8")
            )
            decision_payload = json.loads(
                Path(target_contract_paths["next_target_promotion_decision_json_path"]).read_text(encoding="utf-8")
            )
            row_diagnostics_frame = pd.read_parquet(target_contract_paths["row_diagnostics_parquet_path"])

            self.assertEqual(summary_payload["row_scope"], "out_of_sample_validation_and_test")
            self.assertIn("contract_blocks", summary_payload)
            self.assertIn("comparison_blocks", summary_payload)
            self.assertIn("contract_prediction_metrics", summary_payload)
            self.assertIn("section", summary_frame.columns)
            self.assertIn("metric_name", summary_frame.columns)
            self.assertIn("metric_value", summary_frame.columns)
            self.assertIn("ranking_rows", ranking_payload)
            self.assertIn("by_driver", divergence_summary_payload)
            self.assertIn("next_target_refinement_candidate", candidate_payload)
            self.assertIn("replay_target_design_position", candidate_payload)
            self.assertIn("decision", decision_payload)
            self.assertIn("current_trainer_target_value", row_diagnostics_frame.columns)
            self.assertIn("historical_allocation_target_value", row_diagnostics_frame.columns)


if __name__ == "__main__":
    unittest.main()