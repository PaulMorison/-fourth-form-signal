from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.export_promotions_model_inputs import _build_filters  # noqa: E402
from runtime.promotions.scoring_service import PromotionModelScorer  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.datasets.model_input_export import (  # noqa: E402
    NUMERIC_EXPORT_DECIMALS,
    PromotionFinalModelContractError,
    PromotionModelInputCsvExportError,
    _round_for_export,
    _validate_final_model_contract,
    write_model_input_audit_artifacts,
    write_model_input_csv_diagnosis_bundle,
    write_model_input_inspection_artifacts,
)
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)


class RoundForExportTests(unittest.TestCase):
    def test_floats_rounded_to_four_decimals_ints_preserved(self) -> None:
        frame = pd.DataFrame(
            {
                "int_col": pd.Series([1, 2, 3], dtype="int64"),
                "float_col": [1.123456, 2.987654, 3.5],
                "object_col": ["a", "b", "c"],
            }
        )
        rounded = _round_for_export(frame, decimals=NUMERIC_EXPORT_DECIMALS)
        # Ints unchanged.
        self.assertEqual(rounded["int_col"].tolist(), [1, 2, 3])
        self.assertTrue(pd.api.types.is_integer_dtype(rounded["int_col"]))
        # Floats rounded to 4dp.
        self.assertEqual(rounded["float_col"].tolist(), [1.1235, 2.9877, 3.5])
        # Object passthrough.
        self.assertEqual(rounded["object_col"].tolist(), ["a", "b", "c"])


class ContractValidationFailLoudTests(unittest.TestCase):
    def test_target_leakage_raises(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_a": [1.0, 2.0, 3.0],
                "target_actual_units_sold": [10, 20, 30],
            }
        )
        with self.assertRaises(PromotionFinalModelContractError):
            _validate_final_model_contract(
                model_input=frame,
                expected_feature_columns=("feature_a",),
                target_columns=("target_actual_units_sold",),
            )

    def test_raw_advice_leakage_raises(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_a": [1.0, 2.0, 3.0],
                "actual_units_sold": [10, 20, 30],
            }
        )
        with self.assertRaises(PromotionFinalModelContractError):
            _validate_final_model_contract(
                model_input=frame,
                expected_feature_columns=("feature_a", "actual_units_sold"),
                target_columns=(),
            )

    def test_inf_in_feature_columns_raises(self) -> None:
        frame = pd.DataFrame({"feature_a": [1.0, np.inf, 3.0]})
        with self.assertRaises(PromotionFinalModelContractError):
            _validate_final_model_contract(
                model_input=frame,
                expected_feature_columns=("feature_a",),
                target_columns=(),
            )

    def test_constant_columns_are_warning_not_error(self) -> None:
        frame = pd.DataFrame({"feature_a": [1.0, 1.0, 1.0], "feature_b": [1.0, 2.0, 3.0]})
        report = _validate_final_model_contract(
            model_input=frame,
            expected_feature_columns=("feature_a", "feature_b"),
            target_columns=(),
            required_engineered_features=(),
        )
        self.assertTrue(report["passed"])
        self.assertIn("feature_a", report["constant_columns"])
        self.assertIn("unexpected_constant_columns", report["warnings"])

    def test_clean_frame_passes(self) -> None:
        frame = pd.DataFrame({"feature_a": [1.0, 2.0, 3.0], "feature_b": [4.0, 5.0, 6.0]})
        report = _validate_final_model_contract(
            model_input=frame,
            expected_feature_columns=("feature_a", "feature_b"),
            target_columns=("target_actual_units_sold",),
            required_engineered_features=(),
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["issues"], [])


class ModelInputInspectionExportTests(unittest.TestCase):
    def test_writes_required_inspection_artifacts_with_filters(self) -> None:
        frame = pd.DataFrame(
            {
                "store_number": [772, 772, 101],
                "promotion_name": ["Week 19", "Week 20", "Week 19"],
                "feature_sales": [1.123456, 2.0, 3.0],
                "feature_discount_depth_pct": [20.0, 20.0, 10.0],
                "feature_historical_promo_events_same_discount": [2.0, 0.0, 1.0],
                "feature_sales_interval_days_cv_56d": [0.2, 0.3, 0.4],
                "feature_intermittent_demand_flag": [0.0, 1.0, 0.0],
                "feature_sparse_null_signal": [None, None, 1.0],
                "feature_constant": [5.0, 5.0, 5.0],
                "actual_units_sold": [10, 20, 30],
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_model_input_inspection_artifacts(
                model_input_frame=frame,
                output_root=Path(temp_dir) / "inspection",
                run_id="inspect-run",
                source_path=Path(temp_dir) / "model_scoring_input.parquet",
                stage="scoring",
                filters={"store_number": ["772"]},
                sample_rows=10_000,
            )

            for path in paths.__dict__.values():
                self.assertTrue(Path(path).exists(), path)

            full = pd.read_parquet(paths.full_parquet_path)
            self.assertEqual(full["store_number"].astype(str).tolist(), ["772", "772"])
            sample = pd.read_csv(paths.sample_csv_path)
            self.assertEqual(sample["feature_sales"].tolist()[0], 1.1235)
            metadata = json.loads(Path(paths.metadata_json_path).read_text(encoding="utf-8"))
            self.assertEqual(metadata["row_count"], 2)
            self.assertEqual(metadata["source_row_count"], 3)
            self.assertEqual(metadata["filters_applied"], {"store_number": ["772"]})
            self.assertIn("feature_discount_depth_pct", metadata["engineered_feature_names"])
            self.assertIn("feature_discount_depth_pct", metadata["discount_related_feature_names"])
            self.assertIn(
                "feature_historical_promo_events_same_discount",
                metadata["same_discount_history_feature_names"],
            )
            self.assertIn(
                "feature_intermittent_demand_flag",
                metadata["intermittent_demand_feature_names"],
            )
            self.assertIn("feature_sparse_null_signal", metadata["high_null_warning_columns"])
            self.assertIn("feature_constant", metadata["constant_columns"])
            self.assertIn("actual_units_sold", metadata["suspected_leakage_columns"])
            self.assertIn("constant_columns", metadata["suspicious_column_warnings"])
            null_profile = pd.read_csv(paths.null_profile_csv_path)
            self.assertIn("null_rate", null_profile.columns)
            constant_columns = pd.read_csv(paths.constant_columns_csv_path)
            self.assertIn("feature_constant", set(constant_columns["column_name"]))
            feature_list = pd.read_csv(paths.feature_list_csv_path)
            self.assertIn("is_feature_column", feature_list.columns)
            self.assertIn("is_discount_related_feature", feature_list.columns)
            self.assertIn("is_same_discount_history_feature", feature_list.columns)
            self.assertIn("is_intermittent_demand_feature", feature_list.columns)

    def test_filter_missing_column_fails_loud(self) -> None:
        frame = pd.DataFrame({"feature_sales": [1.0, 2.0]})
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(PromotionFinalModelContractError):
                write_model_input_inspection_artifacts(
                    model_input_frame=frame,
                    output_root=Path(temp_dir) / "inspection",
                    filters={"store_number": ["772"]},
                )


class ModelInputCsvDiagnosisExportTests(unittest.TestCase):
    def test_writes_full_csv_bundle_with_filters_and_dictionary(self) -> None:
        promotion_name = "Allocation Report - WK47&48 WINTER PART 1"
        completed_raw = pd.DataFrame(
            {
                "promotion_row_key": ["772|1001|2024-05-01", "772|1002|2024-05-08", "101|1003|2024-05-01"],
                "store_number": [772, 772, 101],
                "promotion_name": [promotion_name, "Allocation Report - WK47&48 WINTER PART 2", promotion_name],
                "sku_number": [1001, 1002, 1003],
                "sku_description": ["Serum", "Vitamins", "Cleanser"],
                "target_actual_units_sold": [24.0, 3.0, 5.0],
                "current_soh": [2.0, 10.0, 1.0],
                "qty_on_order": [0.0, 2.0, 0.0],
                "pl_allocation_qty": [6.0, 1.0, 2.0],
                "discount_percent": [50.0, 20.0, 50.0],
                "feature_historical_promo_events_same_discount": [2.0, 0.0, 1.0],
                "feature_historical_units_same_discount_avg": [8.0, 0.0, 4.0],
                "feature_prior_promo_units_56d": [18.0, 0.0, 6.0],
                "feature_discount_band_response_avg": [7.0, 0.0, 3.0],
                "feature_basket_attach_rate": [0.75, 0.10, 0.50],
                "feature_companion_absence_risk_score": [0.32, 0.02, 0.18],
                "feature_transactions_with_sku_per_day": [1.8, 0.4, 0.9],
                "feature_capital_at_risk": [35.5, 4.0, 8.0],
            }
        )
        completed_features = pd.DataFrame(
            {
                "current_soh": [2.0, 10.0, 1.0],
                "discount_percent": [50.0, 20.0, 50.0],
                "feature_historical_promo_events_same_discount": [2.0, 0.0, 1.0],
                "feature_historical_units_same_discount_avg": [8.0, 0.0, 4.0],
                "feature_prior_promo_units_56d": [18.0, 0.0, 6.0],
                "feature_discount_band_response_avg": [7.0, 0.0, 3.0],
                "feature_basket_attach_rate": [0.75, 0.10, 0.50],
                "feature_companion_absence_risk_score": [0.32, 0.02, 0.18],
                "feature_transactions_with_sku_per_day": [1.8, 0.4, 0.9],
                "feature_capital_at_risk": [35.5, 4.0, 8.0],
                "promotion_name": [promotion_name, "Allocation Report - WK47&48 WINTER PART 2", promotion_name],
                "sku_description": ["Serum", "Vitamins", "Cleanser"],
            }
        )
        future_raw = pd.DataFrame(
            {
                "promotion_row_key": ["772|2001|2024-06-01", "101|2002|2024-06-01"],
                "store_number": [772, 101],
                "promotion_name": [promotion_name, promotion_name],
                "sku_number": [2001, 2002],
                "sku_description": ["Night Cream", "Lip Balm"],
                "current_soh": [1.0, 8.0],
                "qty_on_order": [0.0, 1.0],
                "pl_allocation_qty": [12.0, 3.0],
                "discount_percent": [50.0, 30.0],
                "feature_historical_promo_events_same_discount": [0.0, 3.0],
                "feature_historical_units_same_discount_avg": [0.0, 5.0],
                "feature_prior_promo_units_56d": [0.0, 9.0],
                "feature_discount_band_response_avg": [0.0, 4.0],
                "feature_basket_attach_rate": [0.0, 0.65],
                "feature_companion_absence_risk_score": [0.0, 0.27],
                "feature_transactions_with_sku_per_day": [0.0, 1.1],
                "feature_capital_at_risk": [99.0, 12.0],
            }
        )
        future_features = pd.DataFrame(
            {
                "current_soh": [1.0, 8.0],
                "discount_percent": [50.0, 30.0],
                "feature_historical_promo_events_same_discount": [0.0, 3.0],
                "feature_historical_units_same_discount_avg": [0.0, 5.0],
                "feature_prior_promo_units_56d": [0.0, 9.0],
                "feature_discount_band_response_avg": [0.0, 4.0],
                "feature_basket_attach_rate": [0.0, 0.65],
                "feature_companion_absence_risk_score": [0.0, 0.27],
                "feature_transactions_with_sku_per_day": [0.0, 1.1],
                "feature_capital_at_risk": [99.0, 12.0],
                "promotion_name": [promotion_name, promotion_name],
                "sku_description": ["Night Cream", "Lip Balm"],
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_model_input_csv_diagnosis_bundle(
                output_root=Path(temp_dir) / "promotions" / "inspection" / "run-1" / "model_input_csv_export" / "store-772-week-19",
                run_id="run-1",
                completed_raw_frame=completed_raw,
                completed_feature_frame=completed_features,
                future_raw_frame=future_raw,
                future_feature_frame=future_features,
                filters={"store_number": ["772"], "promotion_name": [promotion_name]},
                source_paths={
                    "completed_raw_parquet": "training_ready.parquet",
                    "completed_feature_parquet": "model_training_input.parquet",
                    "future_raw_parquet": "promotion_base.parquet",
                    "future_feature_parquet": "model_scoring_input.parquet",
                },
                as_of_date="2024-06-01",
            )

            for path in paths.__dict__.values():
                if path is not None:
                    self.assertTrue(Path(path).exists(), path)

            completed_raw_csv = pd.read_csv(paths.completed_raw_csv_path)
            completed_features_csv = pd.read_csv(paths.completed_features_csv_path)
            future_raw_csv = pd.read_csv(paths.future_raw_csv_path)
            future_features_csv = pd.read_csv(paths.future_features_csv_path)
            dictionary = pd.read_csv(paths.column_dictionary_csv_path)
            manifest = json.loads(Path(paths.manifest_json_path).read_text(encoding="utf-8"))

            self.assertEqual(len(completed_raw_csv.index), 1)
            self.assertEqual(len(completed_features_csv.index), 1)
            self.assertEqual(len(future_raw_csv.index), 1)
            self.assertEqual(len(future_features_csv.index), 1)
            self.assertEqual(manifest["row_counts"]["completed_raw_rows"], 1)
            self.assertEqual(manifest["row_counts"]["future_feature_rows"], 1)
            self.assertTrue(str(paths.output_root).endswith("store-772-week-19"))
            self.assertEqual(completed_raw_csv.loc[0, "promotion_name"], promotion_name)
            self.assertEqual(future_raw_csv.loc[0, "promotion_name"], promotion_name)
            self.assertEqual(manifest["filters_applied"]["promotion_name"], [promotion_name])

            for trace_column in ("promotion_row_key", "store_number", "promotion_name", "sku_number"):
                self.assertIn(trace_column, completed_raw_csv.columns)
                self.assertIn(trace_column, future_raw_csv.columns)

            expected_identifier_prefix = [
                "promotion_row_key",
                "store_number",
                "trace_promotion_name",
                "sku_number",
                "trace_sku_description",
            ]
            completed_identifier_count = len(expected_identifier_prefix)
            self.assertEqual(list(completed_features_csv.columns[:completed_identifier_count]), expected_identifier_prefix)
            self.assertEqual(list(future_features_csv.columns[:completed_identifier_count]), expected_identifier_prefix)
            self.assertEqual(len(completed_features_csv.columns), len(set(completed_features_csv.columns)))
            self.assertEqual(len(future_features_csv.columns), len(set(future_features_csv.columns)))
            self.assertEqual(completed_features_csv.loc[0, "trace_promotion_name"], promotion_name)
            self.assertEqual(future_features_csv.loc[0, "trace_promotion_name"], promotion_name)
            self.assertEqual(completed_features_csv.loc[0, "promotion_name"], promotion_name)
            self.assertEqual(future_features_csv.loc[0, "promotion_name"], promotion_name)
            self.assertEqual(
                list(completed_features_csv.columns[completed_identifier_count:]),
                list(completed_features.columns),
            )
            self.assertEqual(
                list(future_features_csv.columns[completed_identifier_count:]),
                list(future_features.columns),
            )
            self.assertIn("target_actual_units_sold", completed_raw_csv.columns)
            self.assertNotIn("target_actual_units_sold", future_raw_csv.columns)
            self.assertIn("feature_historical_promo_events_same_discount", completed_raw_csv.columns)
            self.assertIn("current_soh", completed_features_csv.columns)
            self.assertFalse(any(column_name.startswith("__") for column_name in completed_raw_csv.columns))

            required_dictionary_columns = {
                "column_name",
                "column_role",
                "source_module",
                "description",
                "nullable_flag",
                "example_value",
                "whether_used_in_training",
                "whether_used_in_scoring",
                "source_family",
            }
            self.assertTrue(required_dictionary_columns.issubset(dictionary.columns))
            historical_row = dictionary.loc[
                dictionary["column_name"].eq("feature_historical_promo_events_same_discount")
            ].iloc[0]
            self.assertEqual(historical_row["column_role"], "engineered_feature")
            self.assertTrue(bool(historical_row["whether_used_in_training"]))
            self.assertTrue(bool(historical_row["whether_used_in_scoring"]))
            self.assertEqual(historical_row["source_family"], "prior_promotion_memory")
            discount_band_row = dictionary.loc[
                dictionary["column_name"].eq("feature_discount_band_response_avg")
            ].iloc[0]
            self.assertEqual(discount_band_row["source_family"], "prior_promotion_memory")
            basket_row = dictionary.loc[
                dictionary["column_name"].eq("feature_basket_attach_rate")
            ].iloc[0]
            self.assertEqual(basket_row["source_family"], "demand_basket_mission")
            basket_probability_row = dictionary.loc[
                dictionary["column_name"].eq("feature_companion_absence_risk_score")
            ].iloc[0]
            self.assertEqual(
                basket_probability_row["source_family"],
                "demand_basket_mission",
            )
            basket_velocity_row = dictionary.loc[
                dictionary["column_name"].eq("feature_transactions_with_sku_per_day")
            ].iloc[0]
            self.assertEqual(
                basket_velocity_row["source_family"],
                "demand_basket_mission",
            )
            trace_promotion_row = dictionary.loc[dictionary["column_name"].eq("trace_promotion_name")].iloc[0]
            self.assertEqual(trace_promotion_row["column_role"], "identifier")
            self.assertFalse(bool(trace_promotion_row["whether_used_in_training"]))
            model_promotion_row = dictionary.loc[dictionary["column_name"].eq("promotion_name")].iloc[0]
            self.assertEqual(model_promotion_row["column_role"], "raw_input")
            self.assertTrue(bool(model_promotion_row["whether_used_in_training"]))
            target_row = dictionary.loc[dictionary["column_name"].eq("target_actual_units_sold")].iloc[0]
            self.assertEqual(target_row["column_role"], "target")
            self.assertFalse(bool(target_row["whether_used_in_scoring"]))
            self.assertNotEqual(
                completed_raw_csv.loc[0, "promotion_row_key"],
                future_raw_csv.loc[0, "promotion_row_key"],
            )

            with self.assertRaises(PromotionModelInputCsvExportError):
                write_model_input_csv_diagnosis_bundle(
                    output_root=Path(paths.output_root),
                    run_id="run-1",
                    completed_raw_frame=completed_raw,
                    completed_feature_frame=completed_features,
                    future_raw_frame=future_raw,
                    future_feature_frame=future_features,
                    filters={"store_number": ["772"], "promotion_name": [promotion_name]},
                )

    def test_full_csv_bundle_fails_loud_on_row_mismatch(self) -> None:
        raw_frame = pd.DataFrame(
            {
                "promotion_row_key": ["a", "b"],
                "store_number": [1, 2],
                "promotion_name": ["Promo", "Promo"],
            }
        )
        feature_frame = pd.DataFrame({"feature_a": [1.0]})
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(PromotionModelInputCsvExportError) as raised:
                write_model_input_csv_diagnosis_bundle(
                    output_root=Path(temp_dir) / "export",
                    run_id="row-mismatch",
                    completed_raw_frame=raw_frame,
                    completed_feature_frame=feature_frame,
                )
        self.assertIn("do not align", str(raised.exception))


class ModelInputCsvDiagnosisCliTests(unittest.TestCase):
    def test_promotion_key_filters_header_key_not_row_key(self) -> None:
        filters = _build_filters(
            store_numbers=["772"],
            promotion_names=["Allocation Report - WK47&48 WINTER PART 1"],
            promotion_header_keys=["PROMO-WK47-48-P1"],
            promotion_row_keys=["772|1001|2024-05-01"],
        )
        self.assertEqual(filters["store_number"], ["772"])
        self.assertEqual(filters["promotion_name"], ["Allocation Report - WK47&48 WINTER PART 1"])
        self.assertEqual(filters["promotion_header_key"], ["PROMO-WK47-48-P1"])
        self.assertEqual(filters["promotion_row_key"], ["772|1001|2024-05-01"])


class TrainingScoringAuditArtifactsTests(unittest.TestCase):
    def test_training_and_scoring_write_audit_artifacts(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="audit-train",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            training_artifacts = PromotionModelTrainer().train(
                run_id="audit-train",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            self.assertIsNotNone(training_artifacts.model_input_audit_paths)
            audit = training_artifacts.model_input_audit_paths
            assert audit is not None  # for type-checker
            self.assertTrue(Path(audit.parquet_path).exists())
            self.assertTrue(Path(audit.sample_csv_path).exists())
            self.assertTrue(Path(audit.metadata_json_path).exists())
            self.assertTrue(Path(audit.feature_lineage_csv_path).exists())
            self.assertTrue(Path(audit.feature_lineage_json_path).exists())
            self.assertTrue(Path(audit.contract_validation_json_path).exists())
            self.assertTrue(Path(audit.feature_quality_audit_csv_path).exists())
            self.assertTrue(Path(audit.feature_quality_audit_json_path).exists())
            self.assertTrue(Path(audit.feature_leakage_review_csv_path).exists())
            self.assertTrue(Path(audit.feature_correlation_review_csv_path).exists())
            self.assertTrue(Path(audit.model_input_quality_summary_csv_path).exists())
            self.assertTrue(Path(audit.model_input_quality_summary_json_path).exists())
            self.assertTrue(Path(audit.model_input_quality_summary_txt_path).exists())

            # Parquet contains the EXACT model input frame.
            parquet_frame = pd.read_parquet(audit.parquet_path)
            self.assertGreater(parquet_frame.shape[0], 0)

            # Sample CSV is row-capped and 4dp-rounded for non-integer numerics.
            sample_frame = pd.read_csv(audit.sample_csv_path)
            self.assertLessEqual(len(sample_frame.index), 10_000)
            for column_name in sample_frame.columns:
                series = sample_frame[column_name]
                if pd.api.types.is_float_dtype(series) and series.notna().any():
                    decimals = (
                        series.dropna()
                        .round(NUMERIC_EXPORT_DECIMALS)
                        .sub(series.dropna())
                        .abs()
                        .max()
                    )
                    self.assertAlmostEqual(decimals, 0.0, places=10)

            # Metadata reports source artifact and column ordering.
            metadata = json.loads(Path(audit.metadata_json_path).read_text(encoding="utf-8"))
            self.assertEqual(metadata["stage"], "training")
            self.assertEqual(metadata["source_artifact_path"], dataset.dataset_path)
            self.assertEqual(
                list(metadata["model_input_columns_in_order"]),
                list(parquet_frame.columns),
            )
            self.assertEqual(metadata["sample_csv_numeric_decimals"], NUMERIC_EXPORT_DECIMALS)
            self.assertEqual(
                metadata["feature_quality_audit_csv_path"],
                audit.feature_quality_audit_csv_path,
            )
            self.assertEqual(
                metadata["model_input_quality_summary_txt_path"],
                audit.model_input_quality_summary_txt_path,
            )

            # Feature lineage detects targets-not-leaking and engineered-not-passed
            # gaps via the suspected_leakage_flag column.
            lineage_frame = pd.read_csv(audit.feature_lineage_csv_path)
            self.assertIn("suspected_leakage_flag", lineage_frame.columns)
            target_rows = lineage_frame.loc[lineage_frame["is_target"]]
            self.assertGreater(len(target_rows.index), 0)
            # No target should be present in the model input.
            leaking_targets = target_rows.loc[
                target_rows["stage_present_model_input"]
            ]
            self.assertEqual(len(leaking_targets.index), 0)

            # Contract validation passes.
            contract = json.loads(
                Path(audit.contract_validation_json_path).read_text(encoding="utf-8")
            )
            self.assertTrue(contract["passed"])
            self.assertEqual(contract["target_leaking_into_features"], [])
            self.assertEqual(contract["raw_advice_columns_in_features"], [])

            quality_audit_frame = pd.read_csv(audit.feature_quality_audit_csv_path)
            included_quality_columns = quality_audit_frame.loc[
                quality_audit_frame["included_in_clean_model_flag"].astype(bool),
                ["column_name", "model_input_ordinal"],
            ].sort_values("model_input_ordinal")["column_name"].astype(str)
            self.assertEqual(list(included_quality_columns), list(parquet_frame.columns))

            quality_summary = json.loads(
                Path(audit.model_input_quality_summary_json_path).read_text(encoding="utf-8")
            )
            self.assertEqual(quality_summary["stage"], "training")
            self.assertEqual(
                quality_summary["summary"]["feature_count"],
                parquet_frame.shape[1],
            )
            self.assertEqual(
                quality_summary["summary"]["source_row_count"],
                parquet_frame.shape[0],
            )

            quality_summary_text = Path(audit.model_input_quality_summary_txt_path).read_text(
                encoding="utf-8"
            )
            self.assertIn("PROMOTIONS MODEL INPUT QUALITY AUDIT", quality_summary_text)
            self.assertIn("stage: training", quality_summary_text)

            # Now run scoring and confirm scoring-side audit artifacts.
            future_base_frame = build_future_promotions_base_frame()
            PromotionModelScorer().score(
                run_id="audit-score",
                model_run_id="audit-train",
                future_base_frame=future_base_frame,
                historical_reference_frame=dataset.frame,
                artifact_paths=artifact_paths,
            )
            scoring_inspection_root = artifact_paths.inspection_run_root("audit-score")
            self.assertTrue(
                (scoring_inspection_root / "model_scoring_input.parquet").exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "model_scoring_input_sample.csv").exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "model_scoring_input_metadata.json").exists()
            )
            self.assertTrue(
                (
                    scoring_inspection_root
                    / "feature_lineage_audit_scoring.csv"
                ).exists()
            )
            self.assertTrue(
                (
                    scoring_inspection_root
                    / "final_model_contract_validation_scoring.json"
                ).exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "feature_quality_audit_scoring.csv").exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "feature_quality_audit_scoring.json").exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "feature_leakage_review_scoring.csv").exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "feature_correlation_review_scoring.csv").exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "model_input_quality_summary_scoring.csv").exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "model_input_quality_summary_scoring.json").exists()
            )
            self.assertTrue(
                (scoring_inspection_root / "model_input_quality_summary_scoring.txt").exists()
            )

            # Scoring metadata records the trained-model-run manifest as source.
            scoring_metadata = json.loads(
                (scoring_inspection_root / "model_scoring_input_metadata.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(scoring_metadata["stage"], "scoring")
            self.assertIn("run_manifest.json", scoring_metadata["source_artifact_path"])

            # The training and scoring audits must use the same expected feature
            # columns by construction (this is the leakage-safety invariant).
            training_metadata = json.loads(
                Path(audit.metadata_json_path).read_text(encoding="utf-8")
            )
            self.assertEqual(
                list(training_metadata["feature_column_names"]),
                list(scoring_metadata["feature_column_names"]),
            )


if __name__ == "__main__":
    unittest.main()
