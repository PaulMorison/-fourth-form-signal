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
from runtime.promotions.repair_promotions_training_dataset_hygiene import main  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.feature_engineering.demand.ft_basket_structure_dependency import (  # noqa: E402
    BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_micro_market_equilibrium import (  # noqa: E402
    MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_sparse_demand_noise import (  # noqa: E402
    SPARSE_DEMAND_NOISE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.stock.ft_target_stock_logic import (  # noqa: E402
    TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
)
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class PromotionTrainingDatasetHygieneRepairTests(unittest.TestCase):
    def test_hygiene_repair_removes_review_only_columns_and_repairs_required_feature(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        target_result = PromotionTargetEngineer().engineer(base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            assembled = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="repair-run",
                base_frame=base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )

            dirty_dataset = assembled.frame.copy()
            dirty_dataset["feature_probability_units_given_multi_item_basket"] = feature_result.frame[
                "feature_probability_units_given_multi_item_basket"
            ].values
            dirty_dataset["feature_pca_structure_residual_score"] = feature_result.frame[
                "feature_pca_structure_residual_score"
            ].values
            dirty_dataset["feature_uplift_allocation_discipline_score"] = pd.NA
            dirty_dataset["feature_probability_excess_capital_at_risk"] = pd.NA
            dirty_dataset["target_actual_units_sold"] = pd.NA
            dirty_dataset = dirty_dataset.drop(
                columns=[
                    *TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
                    *BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS,
                    *SPARSE_DEMAND_NOISE_FEATURE_COLUMNS,
                    *MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS,
                ],
                errors="ignore",
            )
            dirty_dataset.to_parquet(artifact_paths.training_dataset_path("repair-run"), index=False)

            manifest_path = artifact_paths.dataset_manifest_path("repair-run")
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_payload["feature_columns"] = [
                column_name
                for column_name in feature_result.feature_columns
                if column_name
                not in set(
                    [
                        *TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
                        *BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS,
                        *SPARSE_DEMAND_NOISE_FEATURE_COLUMNS,
                        *MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS,
                    ]
                )
            ]
            manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--run-id",
                        "repair-run",
                        "--artifact-root",
                        str(artifact_paths.root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            repaired_dataset = pd.read_parquet(payload["training_ready_parquet_path"])
            repaired_manifest = json.loads(Path(payload["dataset_manifest_path"]).read_text(encoding="utf-8"))

            self.assertNotIn("feature_probability_units_given_multi_item_basket", repaired_dataset.columns)
            self.assertNotIn("feature_pca_structure_residual_score", repaired_dataset.columns)
            self.assertIn("feature_uplift_allocation_discipline_score", repaired_dataset.columns)
            self.assertFalse(repaired_dataset["feature_uplift_allocation_discipline_score"].isna().all())
            self.assertIn("feature_promo_period_target_units", repaired_dataset.columns)
            self.assertIn("feature_day_one_target_stock_units", repaired_dataset.columns)
            self.assertIn("feature_trust_floor_units_dynamic", repaired_dataset.columns)
            self.assertIn("feature_basket_anchor_sku_score", repaired_dataset.columns)
            self.assertIn("feature_sparse_demand_noise_regime_score", repaired_dataset.columns)
            self.assertIn("feature_micro_market_clearing_pressure", repaired_dataset.columns)
            self.assertNotIn("feature_probability_units_given_multi_item_basket", repaired_manifest["feature_columns"])
            self.assertNotIn("feature_pca_structure_residual_score", repaired_manifest["feature_columns"])
            self.assertIn("feature_promo_period_target_units", repaired_manifest["feature_columns"])
            self.assertIn("feature_day_one_target_stock_units", repaired_manifest["feature_columns"])
            self.assertIn("feature_trust_floor_units_dynamic", repaired_manifest["feature_columns"])
            self.assertIn("feature_basket_anchor_sku_score", repaired_manifest["feature_columns"])
            self.assertIn("feature_sparse_demand_noise_regime_score", repaired_manifest["feature_columns"])
            self.assertIn("feature_micro_market_clearing_pressure", repaired_manifest["feature_columns"])
            self.assertFalse(repaired_dataset["feature_probability_excess_capital_at_risk"].isna().any())
            self.assertFalse(repaired_dataset["target_actual_units_sold"].isna().any())
            self.assertGreater(
                repaired_manifest["governed_numeric_zero_fill_summary"]["numeric_zero_filled_cell_count"],
                0,
            )
            self.assertIn(
                "feature_probability_units_given_multi_item_basket",
                repaired_manifest["excluded_review_only_feature_columns"],
            )
            coverage_payload = json.loads(
                Path(payload["model_use_feature_coverage_summary_json_path"]).read_text(encoding="utf-8")
            )
            target_stock_row = next(
                row for row in coverage_payload["feature_family_rows"] if row["feature_family"] == "target_stock_shape"
            )
            self.assertEqual(target_stock_row["family_status"], "model_use_covered")
            basket_context_row = next(
                row for row in coverage_payload["feature_family_rows"] if row["feature_family"] == "basket_context"
            )
            self.assertEqual(basket_context_row["family_status"], "model_use_covered")
            baseline_uplift_row = next(
                row for row in coverage_payload["feature_family_rows"] if row["feature_family"] == "baseline_discount_uplift"
            )
            self.assertEqual(baseline_uplift_row["family_status"], "model_use_covered")
            fragility_shape_row = next(
                row for row in coverage_payload["feature_family_rows"] if row["feature_family"] == "fragility_opportunity_shape"
            )
            self.assertEqual(fragility_shape_row["family_status"], "model_use_covered")
            self.assertTrue(Path(payload["training_data_full_parquet_path"]).exists())
            self.assertTrue(Path(payload["training_data_sample_csv_path"]).exists())
            self.assertTrue(Path(payload["training_data_quality_summary_json_path"]).exists())


if __name__ == "__main__":
    unittest.main()