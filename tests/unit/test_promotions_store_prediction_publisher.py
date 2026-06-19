from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import json
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from surfaces.promotions.reporting.store_prediction_publisher import (  # noqa: E402
    PromotionStoreExecutionValidationError,
    StorePredictionPublisher,
)


def _scored_frame(as_of_date: str = "2024-09-01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": ["0772", "0772", "0772", "0701"],
            "promotion_id": ["PROMO_A", "PROMO_A", "PROMO_B", "PROMO_A"],
            "promotion_start_date_date": ["2024-09-05", "2024-09-05", "2024-09-07", "2024-09-05"],
            "promotional_end_date_date": ["2024-09-12", "2024-09-12", "2024-09-14", "2024-09-12"],
            "sku_number": [1001, 1002, 1003, 1004],
            "as_of_date": [as_of_date, as_of_date, as_of_date, as_of_date],
        }
    )


def _store_download_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": ["0772", "0772", "0772", "0701"],
            "promotion_header_key": ["PROMO_A", "PROMO_A", "PROMO_B", "PROMO_A"],
            "promotion_name": ["Spring Launch", "Spring Launch", "Beauty Blitz", "Spring Launch"],
            "promotion_start_date": ["2024-09-05", "2024-09-05", "2024-09-07", "2024-09-05"],
            "promotion_end_date": ["2024-09-12", "2024-09-12", "2024-09-14", "2024-09-12"],
            "sku_number": [1001, 1002, 1003, 1004],
            "product_description": ["SKU 1001", "SKU 1002", "SKU 1003", "SKU 1004"],
            "current_soh_units": [2, 2, 3, 1],
            "qty_on_order_units": [1, 0, 1, 0],
            "predicted_units_until_promo_start": [1, 1, 1, 1],
            "predicted_units_first_7_days_of_promo": [8, 7, 5, 4],
            "predicted_units_total_promo": [8, 7, 5, 4],
            "base_units_target": [2, 2, 2, 2],
            "promo_start_target_soh_units": [11, 7, 6, 5],
            "suggested_order_units": [10, 5, 4, 3],
            "expected_leftover_units_end_of_promo": [2, 1, 1, 0],
            "suggested_order_value": [100.0, 50.0, 40.0, 30.0],
            "client_reason": ["reason", "reason", "reason", "reason"],
            "decision_reason": ["reason", "reason", "reason", "reason"],
            "operational_note": ["note", "note", "note", "note"],
            "decision_recommendation": ["ORDER", "ORDER", "HOLD", "ORDER"],
            "final_decision_score": [0.8, 0.8, 0.7, 0.8],
            "final_confidence_score": [0.8, 0.82, 0.65, 0.76],
        }
    )


def _write_mapping(artifact_paths: PromotionArtifactPaths, *, active: bool = True) -> None:
    mapping = pd.DataFrame(
        {
            "client_code": ["priceline", "priceline"],
            "client_name": ["Priceline", "Priceline"],
            "store_number": ["0772", "0701"],
            "store_name": ["Collins Arcade", "Bourke Street Mall"],
            "store_slug": ["collins_arcade", "bourke_street_mall"],
            "upload_target_name": ["priceline_pos", "priceline_pos"],
            "pos_format_name": ["default", "default"],
            "active_flag": [active, active],
        }
    )
    mapping_path = artifact_paths.promotion_store_client_mapping_path()
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(mapping_path, index=False)


class PromotionStorePredictionPublisherTests(unittest.TestCase):
    def test_publisher_publication_unit_is_store_plus_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-unit-grain",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=_store_download_frame(),
                artifact_paths=artifact_paths,
                model_version="model-v1",
                planning_horizon_days=35,
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            # Store 0772 has PROMO_A and PROMO_B; store 0701 has PROMO_A => 3 publication units.
            self.assertEqual(artifacts.promotion_cycles_published, 3)
            self.assertEqual(len(artifacts.review_paths), 3)
            self.assertTrue(
                any(
                    "/promotions/priceline/0772/prediction/2024-09-05/0772_2024-09-05_spring-launch_store-prediction-review.csv" in path
                    for path in artifacts.review_paths
                )
            )
            for path in (
                *artifacts.review_paths,
                *artifacts.pos_upload_paths,
                *artifacts.summary_paths,
                *artifacts.reconciliation_paths,
                *artifacts.store_cycle_manifest_paths,
            ):
                self.assertIn("/promotions/priceline/", path)
                self.assertIn("/prediction/", path)
                self.assertNotIn("/promotion_cycles/", path)
                self.assertNotIn("default_client", path)
                self.assertNotIn("/store_", path)

    def test_stage12_publish_accepts_stage11_commercial_schema_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            stage11_like_frame = _store_download_frame().copy()
            stage11_like_frame["sku_number"] = stage11_like_frame["sku_number"].astype(str)

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-stage11-schema-compat",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=stage11_like_frame,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                planning_horizon_days=35,
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertGreater(int(artifacts.pos_upload_row_count), 0)
            self.assertTrue(Path(artifacts.publication_summary_path).exists())

    def test_publisher_writes_client_store_cycle_pack_and_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=_store_download_frame(),
                artifact_paths=artifact_paths,
                model_version="model-v1",
                planning_horizon_days=35,
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertGreaterEqual(artifacts.stores_published, 2)
            self.assertGreaterEqual(artifacts.promotion_cycles_published, 1)
            self.assertTrue(Path(artifacts.prediction_registry_path).exists())
            self.assertTrue(all(Path(path).exists() for path in artifacts.pos_upload_paths))
            self.assertTrue(all(Path(path).exists() for path in artifacts.review_paths))
            self.assertEqual(len(artifacts.summary_paths), 3)
            self.assertTrue(all(Path(path).exists() for path in artifacts.summary_paths))
            self.assertTrue(all(Path(path).exists() for path in artifacts.reconciliation_paths))
            self.assertTrue(all(Path(path).exists() for path in artifacts.store_cycle_manifest_paths))
            self.assertTrue(Path(artifacts.publication_summary_path).exists())

            pos_frame = pd.read_csv(artifacts.pos_upload_paths[0])
            review_frame = pd.read_csv(artifacts.review_paths[0])
            self.assertEqual(
                list(pos_frame.columns),
                ["store_number", "sku_number", "description", "order_quantity", "target_soh_on_break_date"],
            )
            self.assertTrue((pos_frame["order_quantity"] >= 0).all())
            self.assertTrue(pos_frame["target_soh_on_break_date"].notna().all())
            self.assertGreaterEqual(int(review_frame["sku_number"].nunique(dropna=True)), 1)

    def test_publisher_disambiguates_canonical_publication_path_collisions(self) -> None:
        scored_frame = pd.DataFrame(
            {
                "store_number": ["0772", "0772", "0772", "0772"],
                "promotion_id": ["PROMO_A", "PROMO_A", "PROMO_C", "PROMO_C"],
                "promotion_start_date_date": ["2024-09-05", "2024-09-05", "2024-09-05", "2024-09-05"],
                "promotional_end_date_date": ["2024-09-12", "2024-09-12", "2024-09-12", "2024-09-12"],
                "sku_number": [1001, 1002, 1005, 1006],
                "as_of_date": ["2024-09-01", "2024-09-01", "2024-09-01", "2024-09-01"],
            }
        )
        store_download_frame = pd.concat(
            [_store_download_frame().iloc[[0, 1]].copy(), _store_download_frame().iloc[[0, 1]].copy()],
            ignore_index=True,
        )
        store_download_frame["promotion_header_key"] = ["PROMO_A", "PROMO_A", "PROMO_C", "PROMO_C"]
        store_download_frame["sku_number"] = [1001, 1002, 1005, 1006]
        store_download_frame["promotion_name"] = ["Spring Launch"] * 4
        store_download_frame["promotion_start_date"] = ["2024-09-05"] * 4
        store_download_frame["promotion_end_date"] = ["2024-09-12"] * 4

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            first = StorePredictionPublisher().publish(
                run_id="publisher-collision-a",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored_frame,
                store_download_frame=store_download_frame,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                planning_horizon_days=35,
                allow_reprediction=False,
                strict_store_mapping=True,
            )
            second = StorePredictionPublisher().publish(
                run_id="publisher-collision-b",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored_frame,
                store_download_frame=store_download_frame,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                planning_horizon_days=35,
                allow_reprediction=True,
                strict_store_mapping=True,
            )

            first_names = sorted(Path(path).name for path in first.review_paths)
            second_names = sorted(Path(path).name for path in second.review_paths)

            self.assertEqual(first_names, second_names)
            self.assertEqual(len(first_names), 2)
            self.assertEqual(len(set(first_names)), 2)
            for name in first_names:
                self.assertRegex(
                    name,
                    r"^0772_2024-09-05_spring-launch-[0-9a-f]{8}_store-prediction-review\.csv$",
                )

    def test_publisher_skips_duplicate_predictions_when_reprediction_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            publisher = StorePredictionPublisher()
            first = publisher.publish(
                run_id="publisher-run-first",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=_store_download_frame(),
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )
            second = publisher.publish(
                run_id="publisher-run-second",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=_store_download_frame(),
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertGreater(first.pos_upload_row_count, 0)
            self.assertEqual(second.pos_upload_row_count, 0)
            self.assertGreater(second.skipped_duplicate_prediction_count, 0)
            self.assertEqual(second.publish_status, "NOOP_ALREADY_PUBLISHED")
            self.assertTrue(second.noop_already_published_flag)
            self.assertTrue(second.prior_publication_detected_flag)

    def test_publisher_versions_predictions_when_reprediction_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            publisher = StorePredictionPublisher()
            publisher.publish(
                run_id="publisher-run-v1",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=_store_download_frame(),
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )
            publisher.publish(
                run_id="publisher-run-v2",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=_store_download_frame(),
                artifact_paths=artifact_paths,
                model_version="model-v2",
                allow_reprediction=True,
                strict_store_mapping=True,
            )

            registry = pd.read_parquet(artifact_paths.prediction_registry_path())
            self.assertIn("prediction_version", registry.columns)
            self.assertGreaterEqual(int(registry["prediction_version"].max()), 2)
            self.assertIn("superseded", set(registry["status"]))
            self.assertIn("active", set(registry["status"]))

    def test_publisher_fails_validation_on_duplicate_store_promotion_sku_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            duplicate_store_download = _store_download_frame().copy()
            duplicate_store_download = pd.concat(
                [duplicate_store_download, duplicate_store_download.iloc[[0]].copy()],
                ignore_index=True,
            )

            with self.assertRaises(PromotionStoreExecutionValidationError):
                StorePredictionPublisher().publish(
                    run_id="publisher-run-dup",
                    as_of_date="2024-09-01",
                    scored_decision_surface_frame=_scored_frame(),
                    store_download_frame=duplicate_store_download,
                    artifact_paths=artifact_paths,
                    model_version="model-v1",
                    allow_reprediction=False,
                    strict_store_mapping=True,
                )

    def test_publisher_fails_when_store_mapping_missing_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )

            with self.assertRaises(PromotionStoreExecutionValidationError):
                StorePredictionPublisher().publish(
                    run_id="publisher-run-missing-map",
                    as_of_date="2024-09-01",
                    scored_decision_surface_frame=_scored_frame(),
                    store_download_frame=_store_download_frame(),
                    artifact_paths=artifact_paths,
                    model_version="model-v1",
                    allow_reprediction=False,
                    strict_store_mapping=True,
                )

    def test_publisher_fails_when_store_is_inactive_in_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths, active=False)

            with self.assertRaises(PromotionStoreExecutionValidationError):
                StorePredictionPublisher().publish(
                    run_id="publisher-run-inactive-map",
                    as_of_date="2024-09-01",
                    scored_decision_surface_frame=_scored_frame(),
                    store_download_frame=_store_download_frame(),
                    artifact_paths=artifact_paths,
                    model_version="model-v1",
                    allow_reprediction=False,
                    strict_store_mapping=True,
                )

    def test_null_sku_rows_are_excluded_from_pos_and_written_to_review_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().copy()
            scored = _scored_frame().copy()

            null_row_download = store_download.iloc[[0]].copy()
            null_row_download["sku_number"] = ""
            null_row_download["sku_description"] = ""
            store_download = pd.concat([store_download, null_row_download], ignore_index=True)

            null_row_scored = scored.iloc[[0]].copy()
            null_row_scored["sku_number"] = ""
            scored = pd.concat([scored, null_row_scored], ignore_index=True)

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-null-sku",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored,
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            review_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.review_paths],
                ignore_index=True,
            )
            pos_frame = pd.concat(
                [pd.read_csv(path) for path in artifacts.pos_upload_paths],
                ignore_index=True,
            )
            publication_summary = pd.read_csv(artifacts.publication_summary_path)

            self.assertFalse(pos_frame["sku_number"].astype(str).str.strip().eq("").any())
            self.assertFalse(pos_frame["sku_number"].astype(str).str.lower().eq("nan").any())
            self.assertIn("pos_eligible_flag", review_frame.columns)
            self.assertIn("null_sku_flag", review_frame.columns)
            self.assertGreaterEqual(
                int(pd.to_numeric(review_frame["null_sku_flag"], errors="coerce").fillna(0).sum()),
                1,
            )
            self.assertGreaterEqual(int(publication_summary["null_sku_excluded_row_count"].sum()), 1)

    def test_mixed_valid_invalid_rows_publish_with_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().copy()
            scored = _scored_frame().copy()
            store_download.loc[0, "review_required_flag"] = 1

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-pass-with-exclusions",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored,
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertEqual(artifacts.publish_status, "PASS_WITH_EXCLUSIONS")
            self.assertGreater(artifacts.pos_upload_row_count, 0)
            self.assertGreater(artifacts.pos_excluded_row_count, 0)

    def test_all_review_only_rows_end_in_governed_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().copy()
            store_download["review_required_flag"] = 1

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-all-review-only",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )
            self.assertEqual(artifacts.pos_upload_row_count, 0)
            self.assertEqual(artifacts.publish_status, "NOOP_VALID_NO_PUBLISHABLE_ROWS")

    def test_hold_and_do_not_order_rows_are_legitimate_non_publishable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().iloc[[0, 1]].copy().reset_index(drop=True)
            store_download["decision_recommendation"] = ["HOLD", "DO_NOT_ORDER"]
            store_download["publish_eligibility_reason"] = [
                "excluded_legitimate_hold_inventory_sufficient",
                "excluded_legitimate_do_not_order_low_incremental_value",
            ]
            store_download["review_reason"] = ["", ""]

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-non-buy-legitimate-noop",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame().iloc[[0, 1]].reset_index(drop=True),
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertEqual(artifacts.pos_upload_row_count, 0)
            self.assertEqual(artifacts.pos_excluded_row_count, 2)
            self.assertEqual(artifacts.publish_status, "NOOP_VALID_NO_PUBLISHABLE_ROWS")
            summary = pd.read_csv(artifacts.publication_summary_path, keep_default_na=False)
            self.assertEqual(int(summary.iloc[0]["review_only_row_count"]), 0)
            self.assertEqual(int(summary.iloc[0]["excluded_legitimate_row_count"]), 2)

    def test_blank_review_reason_survives_stage11_csv_handoff_as_blank(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            artifact_paths = PromotionArtifactPaths(
                root=temp_root / "promotions_runtime_governed",
                local_inspection_root=temp_root / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().iloc[[0]].copy().reset_index(drop=True)
            store_download["decision_recommendation"] = ["HOLD"]
            store_download["publish_eligibility_reason"] = ["excluded_legitimate_hold_inventory_sufficient"]
            store_download["review_reason"] = [""]

            csv_path = temp_root / "stage11_master_handoff.csv"
            store_download.to_csv(csv_path, index=False)
            round_tripped = pd.read_csv(csv_path, keep_default_na=False)
            scored = _scored_frame().iloc[[0]].copy().reset_index(drop=True)
            scored["store_number"] = [772]

            self.assertEqual(str(round_tripped.loc[0, "review_reason"]), "")

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-blank-review-roundtrip",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored,
                store_download_frame=round_tripped,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=False,
            )

            summary = pd.read_csv(artifacts.publication_summary_path, keep_default_na=False)
            self.assertEqual(artifacts.pos_upload_row_count, 0)
            self.assertEqual(int(summary.iloc[0]["review_only_row_count"]), 0)
            self.assertEqual(int(summary.iloc[0]["excluded_legitimate_row_count"]), 1)

    def test_nan_review_reason_does_not_count_as_review_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            artifact_paths = PromotionArtifactPaths(
                root=temp_root / "promotions_runtime_governed",
                local_inspection_root=temp_root / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().iloc[[0]].copy().reset_index(drop=True)
            store_download["decision_recommendation"] = ["HOLD"]
            store_download["publish_eligibility_reason"] = ["excluded_legitimate_hold_inventory_sufficient"]
            store_download["review_reason"] = [""]

            csv_path = temp_root / "stage11_master_nan_review.csv"
            store_download.to_csv(csv_path, index=False)
            default_round_tripped = pd.read_csv(csv_path)
            scored = _scored_frame().iloc[[0]].copy().reset_index(drop=True)
            scored["store_number"] = [772]

            self.assertTrue(pd.isna(default_round_tripped.loc[0, "review_reason"]))

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-nan-review-text",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored,
                store_download_frame=default_round_tripped,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=False,
            )

            summary = pd.read_csv(artifacts.publication_summary_path, keep_default_na=False)
            self.assertEqual(artifacts.pos_upload_row_count, 0)
            self.assertEqual(int(summary.iloc[0]["review_only_row_count"]), 0)
            self.assertEqual(int(summary.iloc[0]["excluded_legitimate_row_count"]), 1)

    def test_true_review_row_stays_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().iloc[[0]].copy().reset_index(drop=True)
            store_download["decision_recommendation"] = ["REVIEW"]
            store_download["review_reason"] = ["policy_stock_gap_high"]

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-review-only-row",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame().iloc[[0]].reset_index(drop=True),
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            summary = pd.read_csv(artifacts.publication_summary_path, keep_default_na=False)
            self.assertEqual(artifacts.pos_upload_row_count, 0)
            self.assertEqual(int(summary.iloc[0]["review_only_row_count"]), 1)
            self.assertEqual(int(summary.iloc[0]["excluded_legitimate_row_count"]), 0)

    def test_manual_review_rows_backfill_structured_review_reason_from_client_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().iloc[[0, 1, 2]].copy().reset_index(drop=True)
            store_download["decision_recommendation"] = ["REVIEW", "REVIEW", "REVIEW"]
            store_download["review_reason"] = ["", "", ""]
            store_download["publish_eligibility_reason"] = ["", "", ""]
            store_download["client_reason"] = [
                "Likely capital trap risk: resolve quantity manually before release.",
                "Review required: confidence is below production threshold, so local store context should guide the final call.",
                "Launch demand support is weaker than the total-promo signal; confirm replenishment timing before releasing quantity.",
            ]

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-manual-review-reason-fallback",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame().iloc[[0, 1, 2]].reset_index(drop=True),
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            review = pd.concat([pd.read_csv(path) for path in artifacts.review_paths], ignore_index=True)
            self.assertEqual(artifacts.pos_upload_row_count, 0)
            self.assertEqual(
                set(review["review_reason"].astype(str)),
                {
                    "review_high_leftover_risk",
                    "review_low_confidence",
                    "review_launch_window_support_conflict",
                },
            )
            self.assertEqual(
                set(review["publish_eligibility_reason"].astype(str)),
                {
                    "review_high_leftover_risk",
                    "review_low_confidence",
                    "review_launch_window_support_conflict",
                },
            )

    def test_all_defect_rows_still_fail_loud(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().copy()
            store_download["suggested_order_units"] = -1

            with self.assertRaises(PromotionStoreExecutionValidationError) as exc:
                StorePredictionPublisher().publish(
                    run_id="publisher-run-all-defects",
                    as_of_date="2024-09-01",
                    scored_decision_surface_frame=_scored_frame(),
                    store_download_frame=store_download,
                    artifact_paths=artifact_paths,
                    model_version="model-v1",
                    allow_reprediction=False,
                    strict_store_mapping=True,
                )
            self.assertIn("FAIL_NO_ELIGIBLE_ROWS", str(exc.exception))
            self.assertIn("all_rows_excluded_defect", str(exc.exception))

    def test_noop_already_published_writes_governed_summary_and_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            publisher = StorePredictionPublisher()

            publisher.publish(
                run_id="publisher-run-noop-first",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=_store_download_frame(),
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )
            second_store_download = _store_download_frame().copy()
            second_store_download["review_required_flag"] = 1
            second = publisher.publish(
                run_id="publisher-run-noop-second",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=second_store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertEqual(second.publish_status, "NOOP_ALREADY_PUBLISHED")
            self.assertTrue(second.noop_already_published_flag)
            self.assertEqual(second.pos_candidate_row_count, 0)
            self.assertEqual(second.pos_excluded_row_count, 0)
            self.assertEqual(second.skipped_due_to_registry_duplicate_count, 4)
            self.assertEqual(second.skipped_due_to_review_count, 0)
            self.assertTrue(Path(second.publication_summary_path).exists())
            summary_frame = pd.read_csv(second.publication_summary_path)
            self.assertIn("skipped_due_to_registry_duplicate_count", summary_frame.columns)
            self.assertIn("cycle_identity_present_flag", summary_frame.columns)
            self.assertIn("prior_publication_detected_flag", summary_frame.columns)
            self.assertIn("publish_status_message", summary_frame.columns)
            self.assertEqual(int(summary_frame.iloc[0]["source_row_count"]), 4)
            self.assertEqual(int(summary_frame.iloc[0]["candidate_row_count"]), 4)
            self.assertEqual(int(summary_frame.iloc[0]["pos_candidate_row_count"]), 0)
            self.assertEqual(int(summary_frame.iloc[0]["pos_excluded_row_count"]), 0)
            self.assertEqual(int(summary_frame.iloc[0]["skipped_row_count"]), 4)
            self.assertEqual(int(summary_frame.iloc[0]["skipped_due_to_registry_duplicate_count"]), 4)
            self.assertEqual(int(summary_frame.iloc[0]["skipped_due_to_review_count"]), 0)
            self.assertIn("already published", str(summary_frame.iloc[0]["publish_status_message"]).lower())
            gate_counts_path = Path(second.publication_summary_path).parent / "publish_gate_counts.json"
            gate_counts = json.loads(gate_counts_path.read_text(encoding="utf-8"))
            self.assertEqual(int(gate_counts["post_policy_row_count"]), 0)
            self.assertTrue(bool(gate_counts["counts_reconciled_flag"]))
            self.assertTrue(second.diagnostics_paths)
            self.assertEqual(len(second.skipped_paths), 0)

    def test_mixed_registry_duplicate_and_review_only_noop_is_not_already_published(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            publisher = StorePredictionPublisher()

            publisher.publish(
                run_id="publisher-run-mixed-first",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame().iloc[[0]].reset_index(drop=True),
                store_download_frame=_store_download_frame().iloc[[0]].reset_index(drop=True),
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            scored = _scored_frame().iloc[[0, 1]].reset_index(drop=True)
            store_download = _store_download_frame().iloc[[0, 1]].reset_index(drop=True)
            store_download["review_required_flag"] = 1

            second = publisher.publish(
                run_id="publisher-run-mixed-second",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored,
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertEqual(second.pos_upload_row_count, 0)
            self.assertEqual(second.publish_status, "NOOP_VALID_NO_PUBLISHABLE_ROWS")
            self.assertEqual(second.publish_status_reason, "all_cycles_valid_no_publishable_rows")
            self.assertFalse(second.noop_already_published_flag)
            self.assertTrue(second.prior_publication_detected_flag)
            self.assertEqual(second.skipped_due_to_registry_duplicate_count, 1)
            self.assertEqual(second.skipped_due_to_review_count, 1)

            summary_frame = pd.read_csv(second.publication_summary_path)
            self.assertEqual(str(summary_frame.iloc[0]["publish_status"]), "NOOP_VALID_NO_PUBLISHABLE_ROWS")
            self.assertEqual(str(summary_frame.iloc[0]["publish_status_reason"]), "review_only_rows_no_publish")
            self.assertEqual(int(summary_frame.iloc[0]["source_row_count"]), 2)
            self.assertEqual(int(summary_frame.iloc[0]["candidate_row_count"]), 2)
            self.assertEqual(int(summary_frame.iloc[0]["pos_candidate_row_count"]), 1)
            self.assertEqual(int(summary_frame.iloc[0]["pos_excluded_row_count"]), 1)
            self.assertEqual(int(summary_frame.iloc[0]["skipped_row_count"]), 2)
            self.assertEqual(int(summary_frame.iloc[0]["skipped_due_to_registry_duplicate_count"]), 1)
            self.assertEqual(int(summary_frame.iloc[0]["skipped_due_to_review_count"]), 1)
            self.assertNotIn("every candidate row was already published", str(summary_frame.iloc[0]["publish_status_message"]).lower())

    def test_duplicate_pos_eligible_rows_still_fail_hard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)
            duplicate_store_download = _store_download_frame().copy()
            duplicate_store_download = pd.concat(
                [duplicate_store_download, duplicate_store_download.iloc[[0]].copy()],
                ignore_index=True,
            )

            with self.assertRaises(PromotionStoreExecutionValidationError) as exc:
                StorePredictionPublisher().publish(
                    run_id="publisher-run-dup-hard",
                    as_of_date="2024-09-01",
                    scored_decision_surface_frame=_scored_frame(),
                    store_download_frame=duplicate_store_download,
                    artifact_paths=artifact_paths,
                    model_version="model-v1",
                    allow_reprediction=False,
                    strict_store_mapping=True,
                )
            self.assertIn("duplicate store_number + promotion_header_key + sku_number", str(exc.exception))

    def test_publication_summary_counts_reconcile_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().copy()
            store_download.loc[0, "review_required_flag"] = 1

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-summary-reconcile",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )
            summary_frame = pd.read_csv(artifacts.publication_summary_path)
            self.assertFalse(summary_frame.empty)
            self.assertIn("publish_status_message", summary_frame.columns)
            for row in summary_frame.itertuples(index=False):
                registry_duplicate_count = int(row.skipped_due_to_registry_duplicate_count)
                self.assertEqual(int(row.source_row_count), int(row.candidate_row_count))
                self.assertEqual(int(row.candidate_row_count), int(row.pos_candidate_row_count) + registry_duplicate_count)
                self.assertEqual(
                    int(row.pos_candidate_row_count),
                    int(row.pos_published_row_count) + int(row.pos_excluded_row_count),
                )
                self.assertEqual(int(row.skipped_row_count), int(row.pos_excluded_row_count) + registry_duplicate_count)
                self.assertTrue(str(row.publish_status_message).strip())

    def test_publish_identity_matching_normalizes_decimal_sku_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            scored = _scored_frame().copy()
            scored["sku_number"] = scored["sku_number"].astype(float)

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-sku-normalization",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored,
                store_download_frame=_store_download_frame(),
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertGreater(artifacts.pos_upload_row_count, 0)
            self.assertNotEqual(artifacts.publish_status, "FAIL_NO_ELIGIBLE_ROWS")

    def test_no_candidate_noop_diagnostics_include_gate_breakdown_and_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().copy()
            scored = _scored_frame().copy()
            scored["promotion_start_date_date"] = "2024-10-01"
            scored["promotional_end_date_date"] = "2024-10-08"

            run_id = "publisher-run-no-candidate-diagnostics"
            with self.assertRaises(PromotionStoreExecutionValidationError) as exc:
                StorePredictionPublisher().publish(
                    run_id=run_id,
                    as_of_date="2024-09-01",
                    scored_decision_surface_frame=scored,
                    store_download_frame=store_download,
                    artifact_paths=artifact_paths,
                    model_version="model-v1",
                    allow_reprediction=False,
                    strict_store_mapping=True,
                )
            self.assertIn("FAIL_NO_ELIGIBLE_ROWS", str(exc.exception))
            self.assertIn("no_candidate_rows", str(exc.exception))

            summary_frame = pd.read_csv(artifact_paths.commercial_publication_summary_csv_path(run_id))
            self.assertFalse(summary_frame.empty)
            self.assertEqual(int(summary_frame.iloc[0]["source_row_count"]), int(len(store_download.index)))
            self.assertEqual(int(summary_frame.iloc[0]["candidate_row_count"]), 0)

            diagnostics_path = artifact_paths.commercial_publication_summary_csv_path(run_id).parent / "publication_noop_diagnostics.json"
            diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            gate_counts = diagnostics.get("candidate_gate_counts", {})
            self.assertEqual(int(diagnostics.get("source_row_count", 0)), int(len(store_download.index)))
            self.assertEqual(int(gate_counts.get("store_download_input_row_count", -1)), int(len(store_download.index)))
            self.assertEqual(int(gate_counts.get("publish_base_row_count", -1)), 0)
            self.assertGreater(int(gate_counts.get("rejected_not_in_scored_scope_count", 0)), 0)

    def test_stage12_demand_evidence_exclusion_counts_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            scored = pd.DataFrame(
                {
                    "store_number": ["0772", "0772", "0772", "0772"],
                    "promotion_id": ["PROMO_A", "PROMO_A", "PROMO_A", "PROMO_A"],
                    "promotion_start_date_date": ["2024-09-05", "2024-09-05", "2024-09-05", "2024-09-05"],
                    "promotional_end_date_date": ["2024-09-12", "2024-09-12", "2024-09-12", "2024-09-12"],
                    "sku_number": [1001, 1002, 1003, 1004],
                }
            )
            store_download = _store_download_frame().copy()
            store_download = store_download.loc[store_download["store_number"].astype(str).eq("0772")].reset_index(drop=True)
            extra_row = store_download.iloc[[0]].copy()
            extra_row["sku_number"] = 1004
            extra_row["product_description"] = "SKU 1004"
            extra_row["suggested_order_units"] = 3
            store_download = pd.concat([store_download, extra_row], ignore_index=True)
            store_download["promotion_header_key"] = "PROMO_A"
            store_download["promotion_name"] = "Spring Launch"
            store_download["promotion_start_date"] = "2024-09-05"
            store_download["promotion_end_date"] = "2024-09-12"
            store_download["sku_number"] = [1001, 1002, 1003, 1004]
            store_download["demand_evidence_class"] = [
                "true_zero_demand",
                "cold_start_new_line",
                "low_nonzero_demand",
                "artificial_collapse",
            ]
            store_download["publish_eligibility_reason"] = [
                "excluded_true_zero_demand",
                "excluded_cold_start_new_line_review_required",
                "eligible_low_nonzero_demand",
                "excluded_artificial_collapse",
            ]
            store_download["review_reason"] = [
                "true_zero_demand_no_order",
                "cold_start_new_line_insufficient_history",
                "",
                "artificial_collapse_requires_review",
            ]
            store_download.loc[2, "decision_recommendation"] = "ORDER"
            store_download["cold_start_flag"] = [0, 1, 0, 0]
            store_download["insufficient_history_flag"] = [0, 1, 0, 0]

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-demand-evidence",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored,
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertEqual(artifacts.pos_upload_row_count, 1)
            self.assertEqual(artifacts.pos_excluded_row_count, 3)

            summary_frame = pd.read_csv(artifacts.publication_summary_path)
            self.assertEqual(int(summary_frame["demand_true_zero_count"].sum()), 1)
            self.assertEqual(int(summary_frame["demand_cold_start_count"].sum()), 1)
            self.assertEqual(int(summary_frame["demand_low_nonzero_count"].sum()), 1)
            self.assertEqual(int(summary_frame["demand_artificial_collapse_count"].sum()), 1)

            manifest_payload = json.loads(Path(artifacts.store_cycle_manifest_paths[0]).read_text(encoding="utf-8"))
            output_files = manifest_payload["output_files"]
            self.assertTrue(Path(output_files["rows_by_demand_evidence_class_csv"]).exists())
            self.assertTrue(Path(output_files["cold_start_new_line_rows_csv"]).exists())
            self.assertTrue(Path(output_files["true_zero_demand_rows_csv"]).exists())
            self.assertTrue(Path(output_files["artificial_collapse_rows_csv"]).exists())
            self.assertTrue(Path(output_files["publish_exclusion_reasons_csv"]).exists())

    def test_legitimate_true_zero_only_cycle_is_noop_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            scored = pd.DataFrame(
                {
                    "store_number": ["0772", "0772"],
                    "promotion_id": ["PROMO_A", "PROMO_A"],
                    "promotion_start_date_date": ["2024-09-05", "2024-09-05"],
                    "promotional_end_date_date": ["2024-09-12", "2024-09-12"],
                    "sku_number": [1001, 1002],
                }
            )
            store_download = _store_download_frame().copy().iloc[:2].reset_index(drop=True)
            store_download["promotion_header_key"] = "PROMO_A"
            store_download["demand_evidence_class"] = ["true_zero_demand", "true_zero_demand"]
            store_download["publish_eligibility_reason"] = ["excluded_true_zero_demand", "excluded_true_zero_demand"]
            store_download["decision_recommendation"] = ["HOLD", "DO_NOT_ORDER"]

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-legitimate-noop",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=scored,
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            self.assertEqual(artifacts.publish_status, "NOOP_VALID_NO_PUBLISHABLE_ROWS")
            self.assertEqual(artifacts.pos_upload_row_count, 0)

            summary = pd.read_csv(artifacts.publication_summary_path)
            self.assertEqual(str(summary.iloc[0]["publish_status_reason"]), "legitimate_non_publishable_rows")
            self.assertEqual(int(summary.iloc[0]["excluded_legitimate_row_count"]), 2)

            noop_summary_path = Path(artifacts.publication_summary_path).parent / "publish_noop_summary.json"
            self.assertTrue(noop_summary_path.exists())
            noop_summary = json.loads(noop_summary_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(int(noop_summary.get("noop_cycle_count", 0)), 1)
            self.assertIn("legitimate_non_publishable_rows", noop_summary.get("noop_reason_counts", {}))

    def test_publish_gate_counts_and_breakdown_files_are_written_and_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().copy()
            store_download.loc[0, "review_required_flag"] = 1

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-gate-counts",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            diagnostics_root = Path(artifacts.publication_summary_path).parent
            gate_counts_path = diagnostics_root / "publish_gate_counts.json"
            breakdown_path = diagnostics_root / "publish_eligibility_breakdown.csv"
            review_only_path = diagnostics_root / "publish_review_only_rows.csv"
            legitimate_path = diagnostics_root / "publish_excluded_legitimate_rows.csv"
            defect_path = diagnostics_root / "publish_excluded_defect_rows.csv"

            self.assertTrue(gate_counts_path.exists())
            self.assertTrue(breakdown_path.exists())
            self.assertTrue(review_only_path.exists())
            self.assertTrue(legitimate_path.exists())
            self.assertTrue(defect_path.exists())

            gate_counts = json.loads(gate_counts_path.read_text(encoding="utf-8"))
            self.assertEqual(int(gate_counts["source_row_count"]), int(len(store_download.index)))
            self.assertEqual(
                int(gate_counts["post_policy_row_count"]),
                int(gate_counts["final_published_row_count"])
                + int(gate_counts["publish_eligibility_class_counts"].get("review_only", 0))
                + int(gate_counts["publish_eligibility_class_counts"].get("excluded_legitimate", 0))
                + int(gate_counts["publish_eligibility_class_counts"].get("excluded_defect", 0)),
            )
            self.assertTrue(bool(gate_counts["counts_reconciled_flag"]))

    def test_stage11_demand_classification_fields_flow_into_stage12_review_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_runtime_governed",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            _write_mapping(artifact_paths)

            store_download = _store_download_frame().copy()
            store_download["demand_evidence_class"] = [
                "low_nonzero_demand",
                "cold_start_new_line",
                "true_zero_demand",
                "artificial_collapse",
            ]
            store_download["publish_eligibility_reason"] = [
                "eligible_low_nonzero_demand",
                "excluded_cold_start_new_line_review_required",
                "excluded_true_zero_demand",
                "excluded_artificial_collapse",
            ]
            store_download["review_reason"] = [
                "",
                "cold_start_new_line_insufficient_history",
                "true_zero_demand_no_order",
                "artificial_collapse_requires_review",
            ]

            artifacts = StorePredictionPublisher().publish(
                run_id="publisher-run-continuity",
                as_of_date="2024-09-01",
                scored_decision_surface_frame=_scored_frame(),
                store_download_frame=store_download,
                artifact_paths=artifact_paths,
                model_version="model-v1",
                allow_reprediction=False,
                strict_store_mapping=True,
            )

            review = pd.concat([pd.read_csv(path) for path in artifacts.review_paths], ignore_index=True)
            self.assertIn("publish_eligibility_class", review.columns)
            self.assertIn("publish_noop_reason", review.columns)
            self.assertIn("excluded_from_publish_flag", review.columns)
            self.assertTrue(
                set(review["demand_evidence_class"].astype(str).unique()).issubset(
                    {"low_nonzero_demand", "cold_start_new_line", "true_zero_demand", "artificial_collapse"}
                )
            )
