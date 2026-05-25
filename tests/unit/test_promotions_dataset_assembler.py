from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.datasets.dataset_validators import (  # noqa: E402
    NegativeStockPosturePolicy,
    PromotionDatasetValidationError,
)
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class PromotionDatasetAssemblerTests(unittest.TestCase):
    def test_assembly_preserves_rows_with_display_sku_number_variants_when_key_valid(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        original_row_count = len(base_frame.index)
        base_frame["sku_number"] = base_frame["sku_number"].astype(object)
        base_frame["sku_number_key"] = base_frame["sku_number_key"].astype(float).astype(str)
        base_frame.loc[0, "sku_number"] = "TUESDAY, 24 SEPTEMBER 2024 4:03 PM"
        base_frame.loc[1, "sku_number"] = "12345.0"
        base_frame.loc[2, "sku_number"] = ""
        base_frame.loc[3, "sku_number"] = None
        base_frame.loc[4, "sku_number"] = "NA"
        base_frame.loc[1, "sku_number_key"] = "12345.0"
        target_result = PromotionTargetEngineer().engineer(base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            assembled = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="display-sku-valid-key-test",
                base_frame=base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=PromotionArtifactPaths(root=Path(temp_dir)),
            )

        self.assertEqual(len(assembled.frame.index), original_row_count)
        self.assertEqual(assembled.manifest.row_count, original_row_count)
        expected_display_sku = (
            pd.to_numeric(assembled.frame["sku_number_key"], errors="coerce")
            .astype("int64")
            .astype(str)
            .tolist()
        )
        self.assertEqual(assembled.frame["sku_number"].astype(str).tolist(), expected_display_sku)
        self.assertEqual(
            assembled.frame.loc[assembled.frame.index[0], "sku_number"],
            "100",
        )
        self.assertEqual(assembled.frame.loc[assembled.frame.index[1], "sku_number"], "12345")
        self.assertNotIn(
            "TUESDAY, 24 SEPTEMBER 2024 4:03 PM",
            assembled.frame["sku_number"].astype(str).tolist(),
        )

    def test_assembly_fails_loud_for_blank_null_or_na_like_sku_number_key(self) -> None:
        for invalid_value in ("", None, "NA", "12345.5"):
            with self.subTest(invalid_value=invalid_value):
                base_frame = build_completed_promotions_base_frame().copy()
                base_frame["sku_number_key"] = base_frame["sku_number_key"].astype(object)
                base_frame.loc[0, "sku_number_key"] = invalid_value
                target_result = PromotionTargetEngineer().engineer(base_frame)
                feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

                with tempfile.TemporaryDirectory() as temp_dir:
                    with self.assertRaises(PromotionDatasetValidationError) as error_context:
                        PromotionDatasetAssembler().assemble_training_dataset(
                            run_id="invalid-governed-sku-key-test",
                            base_frame=base_frame,
                            target_frame=target_result.frame,
                            feature_frame=feature_result.frame,
                            target_columns=target_result.target_columns,
                            feature_columns=feature_result.feature_columns,
                            artifact_paths=PromotionArtifactPaths(root=Path(temp_dir)),
                        )

                self.assertEqual(error_context.exception.details["rule"], "governed_numeric_key")
                self.assertIn("sku_number_key", error_context.exception.details["invalid_key_columns"])
                self.assertEqual(len(base_frame.index), 8)
                column_issue = error_context.exception.details["column_issues"]["sku_number_key"]
                self.assertEqual(column_issue["invalid_row_count"], 1)

    def test_duplicate_promotion_rows_raise_validation_error(self) -> None:
        duplicated_base_frame = build_completed_promotions_base_frame().iloc[[0, 0]].copy()
        target_result = PromotionTargetEngineer().engineer(duplicated_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(PromotionDatasetValidationError):
                PromotionDatasetAssembler().assemble_training_dataset(
                    run_id="duplicate-dataset-test",
                    base_frame=duplicated_base_frame,
                    target_frame=target_result.frame,
                    feature_frame=feature_result.frame,
                    target_columns=target_result.target_columns,
                    feature_columns=feature_result.feature_columns,
                    artifact_paths=PromotionArtifactPaths(root=Path(temp_dir)),
                )

    def test_negative_stock_rows_write_governed_artifacts_before_validation_error(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        base_frame.loc[0, "current_soh"] = -5.0
        base_frame.loc[0, "total_stock_available"] = -5.0
        target_result = PromotionTargetEngineer().engineer(base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir))
            with self.assertRaises(PromotionDatasetValidationError) as error_context:
                PromotionDatasetAssembler().assemble_training_dataset(
                    run_id="negative-stock-debug-test",
                    base_frame=base_frame,
                    target_frame=target_result.frame,
                    feature_frame=feature_result.frame,
                    target_columns=target_result.target_columns,
                    feature_columns=feature_result.feature_columns,
                    artifact_paths=artifact_paths,
                )

            error = error_context.exception
            self.assertEqual(error.details["rule"], "negative_stock_posture")
            self.assertEqual(error.details["row_count"], 1)
            self.assertEqual(
                error.details["resolver"],
                "resolve_stock_posture_integrity",
            )

            csv_path = Path(str(error.details["csv_path"]))
            parquet_path = Path(str(error.details["parquet_path"]))
            report_path = Path(str(error.details["report_path"]))
            by_reason_path = Path(str(error.details["negative_stock_posture_by_reason_path"]))
            stage4_diagnostics_path = Path(str(error.details["stage4_stock_posture_diagnostics_path"]))
            repairs_or_escalations_path = Path(
                str(error.details["negative_stock_posture_repairs_or_escalations_path"])
            )
            self.assertTrue(csv_path.exists())
            self.assertTrue(parquet_path.exists())
            self.assertTrue(report_path.exists())
            self.assertTrue(by_reason_path.exists())
            self.assertTrue(stage4_diagnostics_path.exists())
            self.assertTrue(repairs_or_escalations_path.exists())

            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report_payload["rule"], "negative_stock_posture")
            self.assertEqual(report_payload["computed_stock_posture_column"], "computed_stock_posture_value")

            debug_frame = pd.read_parquet(parquet_path)
            self.assertEqual(len(debug_frame.index), 1)
            self.assertEqual(
                debug_frame.iloc[0]["promotion_row_key"],
                base_frame.loc[0, "promotion_row_key"],
            )
            self.assertIn("current_soh", debug_frame.columns)
            self.assertIn("total_stock_available", debug_frame.columns)
            self.assertIn("stock_basis_units", debug_frame.columns)
            self.assertIn("required_implied_units", debug_frame.columns)
            self.assertIn("feature_stock_sufficiency_gap_units", debug_frame.columns)
            self.assertIn("computed_stock_posture_value", debug_frame.columns)
            self.assertIn("stock_posture_failure_class", debug_frame.columns)
            self.assertIn("stock_posture_failure_reason", debug_frame.columns)
            self.assertIn("source_data_negative_flag", debug_frame.columns)
            self.assertIn("transform_inconsistency_flag", debug_frame.columns)
            self.assertIn("missing_inventory_inputs_flag", debug_frame.columns)
            self.assertIn("business_edge_case_flag", debug_frame.columns)
            self.assertEqual(debug_frame.iloc[0]["current_soh"], -5.0)
            self.assertEqual(debug_frame.iloc[0]["total_stock_available"], -5.0)
            self.assertEqual(
                debug_frame.iloc[0]["negative_stock_source_columns"],
                "current_soh,total_stock_available",
            )
            self.assertEqual(
                debug_frame.iloc[0]["stock_posture_failure_class"],
                "source_data_negative_inventory",
            )

            by_reason_frame = pd.read_csv(by_reason_path)
            self.assertEqual(int(by_reason_frame["row_count"].sum()), 1)

            stage4_payload = json.loads(stage4_diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(stage4_payload["failing_row_count"], 1)
            self.assertEqual(
                stage4_payload["repair_policy"],
                "fail_loud_no_silent_repair",
            )

            repairs_or_escalations_frame = pd.read_csv(repairs_or_escalations_path)
            self.assertEqual(len(repairs_or_escalations_frame.index), 1)
            self.assertEqual(
                repairs_or_escalations_frame.iloc[0]["repair_status"],
                "not_repaired_fail_loud",
            )

    def test_unknown_stock_sentinel_negative_one_does_not_fail_validation(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        base_frame.loc[0, "current_soh"] = -1.0
        base_frame.loc[0, "total_stock_available"] = -1.0
        target_result = PromotionTargetEngineer().engineer(base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir))
            assembled = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="negative-one-sentinel-test",
                base_frame=base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )

            self.assertEqual(
                assembled.manifest.validation_report.negative_stock_rows,
                0,
            )

    def test_quarantine_policy_drops_failing_rows_and_persists_governed_artifacts(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        # Mark exactly one row as source-data negative (real defect).
        base_frame.loc[0, "current_soh"] = -5.0
        base_frame.loc[0, "total_stock_available"] = -5.0
        offending_promotion_row_key = base_frame.loc[0, "promotion_row_key"]
        target_result = PromotionTargetEngineer().engineer(base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir))
            assembled = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="negative-stock-quarantine-test",
                base_frame=base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
                negative_stock_policy=NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED,
                # Test fixture is intentionally tiny (~8 rows). Relax the
                # fractional guardrail so the single seeded defect does not
                # itself trip the systemic-regression circuit-breaker that
                # protects production runs.
                negative_stock_quarantine_max_fraction=0.50,
            )

            report = assembled.manifest.validation_report
            self.assertEqual(report.negative_stock_rows, 1)
            self.assertEqual(report.negative_stock_quarantined_rows, 1)
            self.assertEqual(
                report.negative_stock_policy,
                NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED.value,
            )
            self.assertIn(
                str(offending_promotion_row_key),
                report.negative_stock_quarantined_grain_keys,
            )
            self.assertEqual(
                report.negative_stock_quarantine_classification_counts.get(
                    "source_data_negative_inventory"
                ),
                1,
            )
            # The training dataset must no longer contain the quarantined row.
            self.assertNotIn(
                offending_promotion_row_key,
                assembled.frame["promotion_row_key"].tolist(),
            )
            self.assertEqual(
                assembled.manifest.row_count,
                int(len(assembled.frame.index)),
            )

            # Quarantine artifact + keys list must be persisted.
            inspection_root = artifact_paths.inspection_run_root(
                "negative-stock-quarantine-test"
            )
            quarantine_path = inspection_root / "negative_stock_posture_quarantine.parquet"
            quarantine_keys_path = (
                inspection_root / "negative_stock_posture_quarantined_keys.json"
            )
            self.assertTrue(quarantine_path.exists())
            self.assertTrue(quarantine_keys_path.exists())
            payload = json.loads(quarantine_keys_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["quarantined_row_count"], 1)
            self.assertEqual(
                payload["policy"],
                NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED.value,
            )

            # Manifest payload on disk must record the quarantine artifact path.
            manifest_payload = json.loads(
                Path(assembled.manifest_path).read_text(encoding="utf-8")
            )
            self.assertIn("negative_stock_posture_quarantine_path", manifest_payload)
            self.assertEqual(
                manifest_payload["negative_stock_posture_quarantine_path"],
                str(quarantine_path),
            )

    def test_quarantine_policy_still_fails_loud_when_absolute_guardrail_breached(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        # Mark every row as source-data negative; all of them must trip
        # the absolute guardrail because the dataset is small.
        base_frame.loc[:, "current_soh"] = -5.0
        base_frame.loc[:, "total_stock_available"] = -5.0
        target_result = PromotionTargetEngineer().engineer(base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir))
            with self.assertRaises(PromotionDatasetValidationError) as error_context:
                PromotionDatasetAssembler().assemble_training_dataset(
                    run_id="negative-stock-quarantine-guardrail-test",
                    base_frame=base_frame,
                    target_frame=target_result.frame,
                    feature_frame=feature_result.frame,
                    target_columns=target_result.target_columns,
                    feature_columns=feature_result.feature_columns,
                    artifact_paths=artifact_paths,
                    negative_stock_policy=NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED,
                    negative_stock_quarantine_max_fraction=0.10,
                    negative_stock_quarantine_max_absolute=0,
                )
            details = error_context.exception.details
            self.assertEqual(
                details["negative_stock_policy"],
                NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED.value,
            )
            self.assertIn(
                "absolute quarantine guardrail breached",
                str(details["quarantine_guardrail_breached_reason"]),
            )

    def test_quarantine_policy_still_fails_loud_when_fractional_guardrail_breached(self) -> None:
        base_frame = build_completed_promotions_base_frame().copy()
        base_frame.loc[0, "current_soh"] = -5.0
        base_frame.loc[0, "total_stock_available"] = -5.0
        target_result = PromotionTargetEngineer().engineer(base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir))
            with self.assertRaises(PromotionDatasetValidationError) as error_context:
                PromotionDatasetAssembler().assemble_training_dataset(
                    run_id="negative-stock-quarantine-fraction-test",
                    base_frame=base_frame,
                    target_frame=target_result.frame,
                    feature_frame=feature_result.frame,
                    target_columns=target_result.target_columns,
                    feature_columns=feature_result.feature_columns,
                    artifact_paths=artifact_paths,
                    negative_stock_policy=NegativeStockPosturePolicy.QUARANTINE_AND_PROCEED,
                    # Force the single failing row to exceed the fractional cap.
                    negative_stock_quarantine_max_fraction=0.0001,
                    negative_stock_quarantine_max_absolute=10_000,
                )
            self.assertIn(
                "fractional quarantine guardrail breached",
                str(error_context.exception.details["quarantine_guardrail_breached_reason"]),
            )
