from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.export_promotions_training_data_sample import main  # noqa: E402
from state.promotions.datasets.model_input_export import (  # noqa: E402
    NUMERIC_EXPORT_DECIMALS,
    PromotionTrainingDataExportError,
    write_training_data_sample_artifacts,
)


def _build_training_export_frame(row_count: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "promotion_row_key": [f"772|{1000 + row_index}|2024-05-01" for row_index in range(row_count)],
            "store_number": [772] * row_count,
            "promotion_header_key": ["PROMO-WK19"] * row_count,
            "promotion_name": ["  Allocation Report WK19  "] * row_count,
            "sku_number": [str(1000 + row_index) for row_index in range(row_count)],
            "sku_number_key": [1000 + row_index for row_index in range(row_count)],
            "promotion_start_date_date": ["2024-05-01"] * row_count,
            "discount_percent": [50.123456 + row_index for row_index in range(row_count)],
            "target_actual_units_sold": [12.987654 + row_index for row_index in range(row_count)],
            "target_stockout_flag": [True if row_index % 2 == 0 else False for row_index in range(row_count)],
            "feature_probability_zero_demand_same_or_better_discount": [
                0.123456 + (row_index / 10_000)
                for row_index in range(row_count)
            ],
            "feature_micro_market_clearing_pressure": [
                0.456789 + (row_index / 10_000)
                for row_index in range(row_count)
            ],
            "feature_pca_structure_residual_score": [
                0.987654 - (row_index / 10_000)
                for row_index in range(row_count)
            ],
        }
    )


class TrainingDataSampleExportTests(unittest.TestCase):
    def test_sample_writes_top_10000_rows_schema_quality_and_keeps_review_only_columns(self) -> None:
        frame = _build_training_export_frame(row_count=10_005)
        feature_columns = (
            "feature_probability_zero_demand_same_or_better_discount",
            "feature_micro_market_clearing_pressure",
            "feature_pca_structure_residual_score",
        )
        target_columns = (
            "target_actual_units_sold",
            "target_stockout_flag",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_training_data_sample_artifacts(
                run_id="training-export-test",
                dataset_frame=frame,
                output_root=Path(temp_dir) / "inspection",
                row_limit=10_000,
                feature_columns=feature_columns,
                target_columns=target_columns,
            )

            self.assertTrue(Path(paths.full_parquet_path).exists())
            self.assertTrue(Path(paths.sample_csv_path).exists())
            self.assertTrue(Path(paths.schema_csv_path).exists())
            self.assertTrue(Path(paths.quality_summary_json_path).exists())
            self.assertTrue(Path(str(paths.feature_coverage_audit_csv_path)).exists())
            self.assertTrue(Path(str(paths.model_use_feature_coverage_summary_csv_path)).exists())
            self.assertTrue(Path(str(paths.model_use_feature_coverage_summary_json_path)).exists())
            self.assertTrue(Path(str(paths.feature_role_audit_csv_path)).exists())
            self.assertTrue(Path(str(paths.feature_role_audit_summary_json_path)).exists())
            self.assertTrue(Path(str(paths.core_head_candidate_review_csv_path)).exists())
            self.assertTrue(Path(str(paths.core_head_candidate_review_summary_json_path)).exists())

            sample = pd.read_csv(paths.sample_csv_path)
            schema = pd.read_csv(paths.schema_csv_path)
            quality = json.loads(Path(paths.quality_summary_json_path).read_text(encoding="utf-8"))
            role_audit = pd.read_csv(paths.feature_role_audit_csv_path)
            core_review = pd.read_csv(paths.core_head_candidate_review_csv_path)

            self.assertEqual(len(sample.index), 10_000)
            self.assertIn("feature_pca_structure_residual_score", sample.columns)
            self.assertIn("feature_pca_structure_residual_score", schema["column_name"].astype(str).tolist())
            self.assertEqual(
                quality["requested_family_visibility"]["probability"]["status"],
                "present",
            )
            self.assertEqual(
                quality["requested_family_visibility"]["PCA"]["status"],
                "present",
            )
            self.assertIn("feature_probability_zero_demand_same_or_better_discount", quality["engineered_feature_columns_present"])
            self.assertIn("feature_probability_zero_demand_same_or_better_discount", quality["model_use_engineered_feature_columns_present"])
            self.assertIn("feature_pca_structure_residual_score", quality["review_only_engineered_feature_columns_present"])
            self.assertNotIn("feature_pca_structure_residual_score", quality["model_use_engineered_feature_columns_present"])
            self.assertIn(
                "training_dataset_model_use_feature_coverage_summary.csv",
                quality["artifact_files"],
            )
            self.assertIn("feature_role_audit.csv", quality["artifact_files"])
            self.assertIn("core_head_candidate_review.csv", quality["artifact_files"])
            self.assertIn("probability", quality["units_head_core_feature_families_present"])
            self.assertIn(
                "micro_market_equilibrium",
                quality["downstream_decision_support_feature_families_present"],
            )
            self.assertIn("pca", quality["review_only_feature_families_present"])
            self.assertIn("feature_role", role_audit.columns)
            self.assertIn("feature_family", role_audit.columns)
            self.assertIn("recommendation_label", core_review.columns)

    def test_numeric_columns_round_to_four_decimals_and_flags_normalize(self) -> None:
        frame = _build_training_export_frame(row_count=2)
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_training_data_sample_artifacts(
                run_id="rounding-test",
                dataset_frame=frame,
                output_root=Path(temp_dir) / "inspection",
            )

            sample = pd.read_csv(paths.sample_csv_path)
            self.assertEqual(sample.loc[0, "discount_percent"], 50.1235)
            self.assertEqual(sample.loc[0, "target_actual_units_sold"], 12.9877)
            self.assertEqual(
                sample.loc[0, "feature_probability_zero_demand_same_or_better_discount"],
                round(frame.loc[0, "feature_probability_zero_demand_same_or_better_discount"], NUMERIC_EXPORT_DECIMALS),
            )
            self.assertEqual(sample.loc[0, "target_stockout_flag"], 1)
            self.assertEqual(sample.loc[1, "target_stockout_flag"], 0)
            self.assertEqual(sample.loc[0, "promotion_start_date_date"], "2024-05-01")
            self.assertEqual(sample.loc[0, "promotion_name"], "Allocation Report WK19")

    def test_numeric_blanks_zero_fill_but_text_and_dates_stay_blank(self) -> None:
        frame = _build_training_export_frame(row_count=2)
        frame.loc[0, "discount_percent"] = pd.NA
        frame.loc[0, "target_actual_units_sold"] = pd.NA
        frame.loc[0, "feature_probability_zero_demand_same_or_better_discount"] = pd.NA
        frame.loc[0, "catalogue_position"] = "CATA"
        frame.loc[0, "promotion_name"] = None
        frame.loc[0, "promotion_start_date_date"] = None

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_training_data_sample_artifacts(
                run_id="zero-fill-export-test",
                dataset_frame=frame,
                output_root=Path(temp_dir) / "inspection",
            )

            sample = pd.read_csv(paths.sample_csv_path)
            full = pd.read_parquet(paths.full_parquet_path)
            role_summary = json.loads(Path(paths.feature_role_audit_summary_json_path).read_text(encoding="utf-8"))

        self.assertEqual(sample.loc[0, "discount_percent"], 0.0)
        self.assertEqual(sample.loc[0, "target_actual_units_sold"], 0.0)
        self.assertEqual(sample.loc[0, "feature_probability_zero_demand_same_or_better_discount"], 0.0)
        self.assertEqual(sample.loc[0, "catalogue_position"], "CATA")
        self.assertEqual(float(full.loc[0, "discount_percent"]), 0.0)
        self.assertEqual(float(full.loc[0, "target_actual_units_sold"]), 0.0)
        self.assertEqual(str(full.loc[0, "catalogue_position"]), "CATA")
        self.assertTrue(pd.isna(sample.loc[0, "promotion_start_date_date"]))
        self.assertTrue(pd.isna(sample.loc[0, "promotion_name"]))
        self.assertGreater(
            int(role_summary["numeric_zero_fill_summary"]["numeric_zero_filled_cell_count"]),
            0,
        )

    def test_mixed_type_expected_numeric_columns_fail_loud(self) -> None:
        frame = _build_training_export_frame(row_count=2)
        frame["feature_probability_zero_demand_same_or_better_discount"] = ["0.1234", "not-a-number"]

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(PromotionTrainingDataExportError) as raised:
                write_training_data_sample_artifacts(
                    run_id="mixed-type-test",
                    dataset_frame=frame,
                    output_root=Path(temp_dir) / "inspection",
                )

        self.assertIn(
            "feature_probability_zero_demand_same_or_better_discount",
            raised.exception.details["invalid_numeric_columns"],
        )

    def test_family_coverage_reports_missing_requested_families(self) -> None:
        frame = _build_training_export_frame(row_count=3)
        frame = frame.drop(columns=["feature_micro_market_clearing_pressure"])

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_training_data_sample_artifacts(
                run_id="family-coverage-test",
                dataset_frame=frame,
                output_root=Path(temp_dir) / "inspection",
            )

            quality = json.loads(Path(paths.quality_summary_json_path).read_text(encoding="utf-8"))
            self.assertEqual(
                quality["requested_family_visibility"]["same_discount_history"]["status"],
                "missing",
            )
            self.assertEqual(
                quality["requested_family_visibility"]["basket_equilibrium_or_transaction_object"]["status"],
                "missing",
            )


class TrainingDataSampleExportCliTests(unittest.TestCase):
    def test_cli_resolves_governed_defaults(self) -> None:
        frame = _build_training_export_frame(row_count=3)
        manifest_payload = {
            "feature_columns": [
                "feature_probability_zero_demand_same_or_better_discount",
                "feature_pca_structure_residual_score",
            ],
            "target_columns": [
                "target_actual_units_sold",
                "target_stockout_flag",
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "artifacts")
            dataset_path = artifact_paths.training_dataset_path("cli-run")
            manifest_path = artifact_paths.dataset_manifest_path("cli-run")
            dataset_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(dataset_path, index=False)
            manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--run-id",
                        "cli-run",
                        "--artifact-root",
                        str(artifact_paths.root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            inspection_root = artifact_paths.inspection_run_root("cli-run") / "training_data_export"
            self.assertTrue((inspection_root / "training_data_full.parquet").exists())
            self.assertTrue((inspection_root / "training_data_sample_top_10000.csv").exists())
            self.assertTrue((inspection_root / "training_data_sample_schema.csv").exists())
            self.assertTrue((inspection_root / "training_data_sample_quality_summary.json").exists())
            self.assertTrue((inspection_root / "training_dataset_feature_coverage_audit.csv").exists())
            self.assertTrue((inspection_root / "training_dataset_model_use_feature_coverage_summary.csv").exists())
            self.assertTrue((inspection_root / "training_dataset_model_use_feature_coverage_summary.json").exists())
            self.assertTrue((inspection_root / "feature_role_audit.csv").exists())
            self.assertTrue((inspection_root / "feature_role_audit_summary.json").exists())
            self.assertTrue((inspection_root / "core_head_candidate_review.csv").exists())
            self.assertTrue((inspection_root / "core_head_candidate_review_summary.json").exists())


if __name__ == "__main__":
    unittest.main()