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
from runtime.promotions.rebuild_promotions_training_dataset import main  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class PromotionTrainingDatasetRebuildTests(unittest.TestCase):
    def test_rebuild_from_governed_base_parquet_writes_dataset_and_inspection_artifacts(self) -> None:
        base_frame = build_completed_promotions_base_frame()
        base_frame["promotion_header_key"] = "PROMO-HEADER-1"

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            source_run_id = "completed-source-run"
            rebuild_run_id = "completed-rebuild-run"

            source_base_path = artifact_paths.extracted_base_path(source_run_id)
            source_base_path.parent.mkdir(parents=True, exist_ok=True)
            base_frame.to_parquet(source_base_path, index=False)

            prior_manifest_path = artifact_paths.dataset_manifest_path(source_run_id)
            prior_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            prior_manifest_path.write_text(
                json.dumps(
                    {
                        "feature_columns": ["feature_historical_promo_events_same_discount"],
                        "target_columns": ["target_actual_units_sold"],
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--run-id",
                        rebuild_run_id,
                        "--source-run-id",
                        source_run_id,
                        "--artifact-root",
                        str(artifact_paths.root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            dataset_path = Path(payload["training_ready_parquet_path"])
            sample_csv_path = Path(payload["training_data_sample_csv_path"])
            quality_summary_path = Path(payload["training_data_quality_summary_json_path"])
            coverage_summary_path = Path(payload["model_use_feature_coverage_summary_json_path"])

            self.assertTrue(dataset_path.exists())
            self.assertTrue(sample_csv_path.exists())
            self.assertTrue(quality_summary_path.exists())
            self.assertTrue(coverage_summary_path.exists())

            dataset = pd.read_parquet(dataset_path)
            for column_name in (
                "feature_historical_promo_events_same_discount",
                "feature_expected_lost_units_below_trust_floor",
                "feature_end_of_promo_target_floor_units",
                "feature_uplift_allocation_discipline_score",
            ):
                self.assertIn(column_name, dataset.columns)
            self.assertNotIn("feature_pca_structure_residual_score", dataset.columns)

            quality_summary = json.loads(quality_summary_path.read_text(encoding="utf-8"))
            self.assertNotIn(
                "feature_pca_structure_residual_score",
                quality_summary["model_use_engineered_feature_columns_present"],
            )
            self.assertNotIn(
                "feature_pca_structure_residual_score",
                quality_summary["engineered_feature_columns_present"],
            )
            self.assertIn(
                "same_discount_promo_history",
                payload["feature_families_fully_present"],
            )
            self.assertIn("target_stock_shape", payload["feature_families_fully_present"])
            self.assertIn("pca", payload["feature_families_review_only"])
            self.assertGreater(
                len(
                    quality_summary["prior_manifest_comparison"][
                        "new_feature_columns_since_prior_build"
                    ]
                ),
                0,
            )

    def test_rebuild_inherits_quarantine_policy_for_negative_stock_rows(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        base_frame["promotion_header_key"] = "PROMO-HEADER-1"
        base_frame.loc[0, "current_soh"] = -5.0
        base_frame.loc[0, "total_stock_available"] = -5.0
        offending_key = str(base_frame.loc[0, "promotion_row_key"])

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            source_run_id = "completed-source-run-negative-stock"
            rebuild_run_id = "completed-rebuild-run-negative-stock"

            source_base_path = artifact_paths.extracted_base_path(source_run_id)
            source_base_path.parent.mkdir(parents=True, exist_ok=True)
            base_frame.to_parquet(source_base_path, index=False)

            prior_manifest_path = artifact_paths.dataset_manifest_path(source_run_id)
            prior_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            prior_manifest_path.write_text(
                json.dumps(
                    {
                        "feature_columns": ["feature_historical_promo_events_same_discount"],
                        "target_columns": ["target_actual_units_sold"],
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--run-id",
                        rebuild_run_id,
                        "--source-run-id",
                        source_run_id,
                        "--artifact-root",
                        str(artifact_paths.root),
                        "--negative-stock-quarantine-max-fraction",
                        "0.5",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            dataset = pd.read_parquet(payload["training_ready_parquet_path"])
            manifest = json.loads(Path(payload["dataset_manifest_path"]).read_text(encoding="utf-8"))

            self.assertNotIn(offending_key, dataset["promotion_row_key"].astype(str).tolist())
            self.assertEqual(
                manifest["validation_report"]["negative_stock_policy"],
                "quarantine_and_proceed",
            )
            self.assertEqual(manifest["validation_report"]["negative_stock_quarantined_rows"], 1)
            self.assertIn("negative_stock_posture_quarantine_path", manifest)


if __name__ == "__main__":
    unittest.main()