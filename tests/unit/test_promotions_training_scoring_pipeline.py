from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.scoring_service import (  # noqa: E402
    PromotionModelScorer,
    PromotionScoringSchemaError,
)
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.feature_engineering.demand.ft_discount_elasticity import (  # noqa: E402
    DISCOUNT_ELASTICITY_FEATURE_COLUMNS,
)
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from surfaces.promotions.reporting.report_builder import PromotionReportBuilder  # noqa: E402
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)


class PromotionTrainingScoringPipelineTests(unittest.TestCase):
    def test_training_and_scoring_flow_persists_outputs(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
        self.assertIn("feature_expected_baseline_units_promo_window", feature_result.frame.columns)
        self.assertIn("feature_expected_total_units_from_baseline_plus_uplift", feature_result.frame.columns)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-train-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            training_artifacts = PromotionModelTrainer().train(
                run_id="promotions-train-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            allocation_metrics = training_artifacts.metrics["allocation_outcomes"]
            self.assertIn("test_excess_units_mae_raw", allocation_metrics)
            self.assertIn("test_excess_units_mae_calibrated", allocation_metrics)
            self.assertIn("test_excess_units_mae_policy_adjusted", allocation_metrics)
            self.assertIn("test_excess_capital_mae_raw", allocation_metrics)
            self.assertIn("test_excess_capital_mae_calibrated", allocation_metrics)
            self.assertIn("test_excess_capital_mae_policy_adjusted", allocation_metrics)
            self.assertIn("test_excess_units_mae", allocation_metrics)
            self.assertIn("test_raw_excess_units_mae", allocation_metrics)
            self.assertIn("test_excess_capital_at_risk_mae", allocation_metrics)
            self.assertIn("test_raw_excess_capital_at_risk_mae", allocation_metrics)
            self.assertIn("test_uplift_units_mae", allocation_metrics)
            self.assertIn("test_raw_uplift_units_mae", allocation_metrics)
            self.assertIn("test_allocation_aware_units_cap_count", allocation_metrics)
            self.assertIn("test_overallocation_false_positive_cost_proxy", allocation_metrics)
            self.assertIn("test_overallocation_false_negative_excess_capital_proxy", allocation_metrics)
            self.assertIn("test_overallocation_calibration_0_25_row_count", allocation_metrics)
            self.assertIn("test_excess_units_mae_by_same_discount_history_bucket", allocation_metrics)
            self.assertIn("test_excess_capital_mae_by_window_conflict_bucket", allocation_metrics)
            self.assertIn("test_policy_metric_comparison_by_major_bucket", allocation_metrics)
            self.assertTrue(Path(training_artifacts.allocation_decision_scoreboard_json_path).exists())
            self.assertTrue(Path(training_artifacts.allocation_decision_scoreboard_csv_path).exists())
            self.assertIsNotNone(training_artifacts.policy_replay_effectiveness_artifact_paths)
            self.assertTrue(
                Path(training_artifacts.policy_replay_effectiveness_artifact_paths["summary_json_path"]).exists()
            )
            self.assertIsNotNone(training_artifacts.policy_rule_contribution_artifact_paths)
            self.assertTrue(
                Path(training_artifacts.policy_rule_contribution_artifact_paths["summary_json_path"]).exists()
            )
            self.assertIsNotNone(training_artifacts.target_contract_artifact_paths)
            self.assertTrue(
                Path(training_artifacts.target_contract_artifact_paths["summary_json_path"]).exists()
            )
            scoreboard_payload = json.loads(
                Path(training_artifacts.allocation_decision_scoreboard_json_path).read_text(encoding="utf-8")
            )
            self.assertIn("overall_summary", scoreboard_payload)
            self.assertIn("bucket_summaries", scoreboard_payload)
            self.assertIn("policy_comparison_overall", scoreboard_payload)
            self.assertIn("policy_comparison_by_major_bucket", scoreboard_payload)
            self.assertIn("policy_adjustment_summary", scoreboard_payload)
            self.assertIn("evidence_coverage_report", scoreboard_payload)
            future_base_frame = build_future_promotions_base_frame()
            scoring_artifacts = PromotionModelScorer().score(
                run_id="promotions-score-run",
                model_run_id="promotions-train-run",
                future_base_frame=future_base_frame,
                historical_reference_frame=dataset.frame,
                artifact_paths=artifact_paths,
            )
            reporting_artifacts = PromotionReportBuilder().write_reports(
                run_id="promotions-score-run",
                scored_rows=scoring_artifacts.row_frame,
                artifact_paths=artifact_paths,
            )

            self.assertTrue(Path(training_artifacts.manifest_path).exists())
            self.assertIn("raw_predicted_units_sold", scoring_artifacts.row_frame.columns)
            self.assertIn("calibrated_predicted_units_sold", scoring_artifacts.row_frame.columns)
            self.assertIn("policy_adjusted_predicted_units_sold", scoring_artifacts.row_frame.columns)
            self.assertIn("predicted_units_sold", scoring_artifacts.row_frame.columns)
            self.assertIn("policy_adjustment_reason", scoring_artifacts.row_frame.columns)
            self.assertIn("review_override_flag", scoring_artifacts.row_frame.columns)
            self.assertIn("feature_expected_baseline_units_promo_window", scoring_artifacts.row_frame.columns)
            self.assertIn("feature_expected_total_units_from_baseline_plus_uplift", scoring_artifacts.row_frame.columns)
            self.assertIn("recommendation_flag", scoring_artifacts.row_frame.columns)
            self.assertTrue(
                (
                    scoring_artifacts.row_frame["predicted_units_sold"]
                    <= scoring_artifacts.row_frame["calibrated_predicted_units_sold"]
                ).all()
            )
            self.assertIn("allocation_decision_diagnostics_csv_path", scoring_artifacts.diagnostic_paths)
            self.assertTrue(Path(scoring_artifacts.diagnostic_paths["allocation_decision_diagnostics_csv_path"]).exists())
            self.assertTrue(Path(scoring_artifacts.diagnostic_paths["allocation_decision_diagnostics_json_path"]).exists())
            allocation_diagnostics_payload = json.loads(
                Path(scoring_artifacts.diagnostic_paths["allocation_decision_diagnostics_json_path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("evidence_coverage_report", allocation_diagnostics_payload)
            self.assertIn("order_cap_reason_counts", allocation_diagnostics_payload)
            self.assertIn("policy_adjustment_summary", allocation_diagnostics_payload)
            self.assertTrue(
                Path(reporting_artifacts.report_paths["promotion_performance_forecast"]).exists()
            )

    def test_scoring_projects_legacy_schema_columns_from_current_future_fields(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
        legacy_columns = [
            "promo_gm_pct",
            "promo_days",
            "gmroi_8w",
            "sales_promo_period_avg",
            "required_implied_daily",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-train-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            PromotionModelTrainer().train(
                run_id="promotions-train-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            future_base_frame = build_future_promotions_base_frame().drop(columns=legacy_columns)
            self.assertFalse(set(legacy_columns).intersection(future_base_frame.columns))

            scoring_artifacts = PromotionModelScorer().score(
                run_id="promotions-score-run",
                model_run_id="promotions-train-run",
                future_base_frame=future_base_frame,
                historical_reference_frame=dataset.frame,
                artifact_paths=artifact_paths,
            )

            for column_name in legacy_columns:
                self.assertIn(column_name, scoring_artifacts.row_frame.columns)
            self.assertEqual(
                scoring_artifacts.row_frame["promo_days"].tolist(),
                scoring_artifacts.row_frame["live_promo_window_days"].tolist(),
            )

    def test_scoring_zero_future_rows_persists_empty_artifacts(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-train-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            PromotionModelTrainer().train(
                run_id="promotions-train-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            empty_future_frame = build_future_promotions_base_frame().iloc[0:0].copy()

            with patch(
                "runtime.promotions.scoring_service.joblib.load",
                side_effect=AssertionError("zero-row scoring must not load sklearn predictors"),
            ):
                scoring_artifacts = PromotionModelScorer().score(
                    run_id="promotions-score-run",
                    model_run_id="promotions-train-run",
                    future_base_frame=empty_future_frame,
                    historical_reference_frame=dataset.frame,
                    artifact_paths=artifact_paths,
                )

            self.assertEqual(len(scoring_artifacts.row_frame.index), 0)
            for column_name in DISCOUNT_ELASTICITY_FEATURE_COLUMNS:
                self.assertIn(column_name, scoring_artifacts.row_frame.columns)
            for column_name in (
                "raw_predicted_units_sold",
                "calibrated_predicted_units_sold",
                "policy_adjusted_predicted_units_sold",
                "predicted_units_sold",
                "recommendation_flag",
                "recommendation_reason",
            ):
                self.assertIn(column_name, scoring_artifacts.row_frame.columns)
            self.assertTrue(Path(scoring_artifacts.row_predictions_path).exists())
            manifest_payload = json.loads(Path(scoring_artifacts.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest_payload["row_count"], 0)
            self.assertEqual(len(scoring_artifacts.summary_frames["promotion_summary"].index), 0)
            inspection_root = artifact_paths.inspection_run_root("promotions-score-run")
            model_input_metadata = json.loads(
                (inspection_root / "model_scoring_input_metadata.json").read_text(encoding="utf-8")
            )
            contract_validation = json.loads(
                (inspection_root / "final_model_contract_validation_scoring.json").read_text(encoding="utf-8")
            )
            self.assertEqual(model_input_metadata["row_count"], 0)
            self.assertEqual(contract_validation["row_count"], 0)
            self.assertTrue((inspection_root / "model_scoring_input.parquet").exists())
            self.assertTrue((inspection_root / "model_scoring_input_sample.csv").exists())
            self.assertTrue((inspection_root / "feature_lineage_audit_scoring.csv").exists())
            diagnostic_payload = json.loads(
                Path(scoring_artifacts.diagnostic_paths["allocation_decision_diagnostics_json_path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(diagnostic_payload["row_count"], 0)

    def test_scoring_stays_fail_loud_for_unknown_missing_schema_columns(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-train-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            PromotionModelTrainer().train(
                run_id="promotions-train-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            inference_schema_path = artifact_paths.model_family_root("promotions-train-run") / "inference_schema.json"
            inference_schema = json.loads(inference_schema_path.read_text(encoding="utf-8"))
            inference_schema["feature_columns"].append("unexpected_runtime_drift_column")
            inference_schema_path.write_text(
                json.dumps(inference_schema, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(PromotionScoringSchemaError, "unexpected_runtime_drift_column"):
                PromotionModelScorer().score(
                    run_id="promotions-score-run",
                    model_run_id="promotions-train-run",
                    future_base_frame=build_future_promotions_base_frame(),
                    historical_reference_frame=dataset.frame,
                    artifact_paths=artifact_paths,
                )