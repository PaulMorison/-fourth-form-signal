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
from surfaces.promotions.reporting.pilot_validation import (  # noqa: E402
    PromotionPilotValidationError,
    PromotionPilotValidationService,
    load_gold_standard_acceptance_config,
)


def _source_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": ["0772", "0772"],
            "promotion_header_key": ["PROMO_A", "PROMO_A"],
            "promotion_id": ["PROMO_A", "PROMO_A"],
            "promotion_name": ["Spring Launch", "Spring Launch"],
            "promotion_start_date": ["2024-09-05", "2024-09-05"],
            "promotion_end_date": ["2024-09-12", "2024-09-12"],
            "sku_number": ["1001", "1002"],
            "action_code": ["ORDER", "HOLD"],
            "review_required_flag": [False, True],
            "manual_review_flag": [False, True],
        }
    )


def _stage11_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": ["0772", "0772"],
            "promotion_header_key": ["PROMO_A", "PROMO_A"],
            "promotion_id": ["PROMO_A", "PROMO_A"],
            "promotion_name": ["Spring Launch", "Spring Launch"],
            "promotion_start_date": ["2024-09-05", "2024-09-05"],
            "promotion_end_date": ["2024-09-12", "2024-09-12"],
            "sku_number": ["1001", "1002"],
            "action_code": ["ORDER", "HOLD"],
            "review_required_flag": [False, True],
            "manual_review_flag": [False, True],
        }
    )


def _published_store_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "priority_rank": [1, 2],
            "priority_band": ["BUY_NOW", "REVIEW"],
            "sku_number": ["1001", "1002"],
            "sku_description": ["SKU 1001", "SKU 1002"],
            "store_action": ["BUY", "REVIEW"],
            "operator_status": ["ORDER_READY", "REVIEW_REQUIRED"],
            "recommended_order_units": [3, 0],
            "primary_review_reason": ["", "Needs review"],
            "decision_reason": ["reason", "reason"],
        }
    )


def _minimal_published_store_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": ["1001", "1002"],
            "store_action": ["BUY", "REVIEW"],
        }
    )


def _stage13_review_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": ["0772", "0772"],
            "promotion_header_key": ["PROMO_A", "PROMO_A"],
            "promotion_id": ["PROMO_A", "PROMO_A"],
            "promotion_name": ["Spring Launch", "Spring Launch"],
            "promotion_start_date": ["2024-09-05", "2024-09-05"],
            "promotion_break_date": ["2024-09-12", "2024-09-12"],
            "sku_number": ["1001", "1002"],
            "sku_description": ["SKU 1001", "SKU 1002"],
            "recommended_order_quantity": [3, 0],
            "decision_action": ["ORDER", "HOLD"],
            "decision_reason": ["reason", "reason"],
        }
    )


def _stage13_pos_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": ["0772", "0772"],
            "sku_number": ["1001", "1002"],
            "description": ["SKU 1001", "SKU 1002"],
            "order_quantity": [3, 0],
            "target_soh_on_break_date": [7, 6],
        }
    )


def _stage13_reconciliation_frame(status: str = "PASS") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": ["0772"],
            "promotion_header_key": ["PROMO_A"],
            "promotion_id": ["PROMO_A"],
            "source_row_count": [2],
            "output_row_count": [2],
            "source_sku_count": [2],
            "output_sku_count": [2],
            "status": [status],
        }
    )


def _canonical_stage11_path(artifact_paths: PromotionArtifactPaths, *, run_id: str = "pilot-run") -> Path:
    return artifact_paths.store_prediction_store_promotion_csv_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
    )


def _colliding_stage11_path(
    artifact_paths: PromotionArtifactPaths,
    *,
    run_id: str = "pilot-run",
    collision_key: str,
) -> Path:
    return artifact_paths.store_prediction_store_promotion_csv_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
        collision_key=collision_key,
    )


def _canonical_stage13_paths(
    artifact_paths: PromotionArtifactPaths,
    *,
    run_id: str = "pilot-run",
) -> tuple[Path, Path, Path]:
    review_path = artifact_paths.store_prediction_store_promotion_artifact_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
        artifact_name="store-prediction-review",
        extension="csv",
    )
    pos_path = artifact_paths.store_prediction_store_promotion_artifact_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
        artifact_name="pos-order-upload",
        extension="csv",
    )
    reconciliation_path = artifact_paths.store_prediction_store_promotion_artifact_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
        artifact_name="reconciliation",
        extension="csv",
    )
    return review_path, pos_path, reconciliation_path


def _colliding_stage13_paths(
    artifact_paths: PromotionArtifactPaths,
    *,
    run_id: str = "pilot-run",
    collision_key: str,
) -> tuple[Path, Path, Path]:
    review_path = artifact_paths.store_prediction_store_promotion_artifact_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
        artifact_name="store-prediction-review",
        extension="csv",
        collision_key=collision_key,
    )
    pos_path = artifact_paths.store_prediction_store_promotion_artifact_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
        artifact_name="pos-order-upload",
        extension="csv",
        collision_key=collision_key,
    )
    reconciliation_path = artifact_paths.store_prediction_store_promotion_artifact_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
        artifact_name="reconciliation",
        extension="csv",
        collision_key=collision_key,
    )
    return review_path, pos_path, reconciliation_path


def _prediction_manifest_path(
    artifact_paths: PromotionArtifactPaths,
    *,
    run_id: str = "pilot-run",
    collision_key: str | None = None,
) -> Path:
    return artifact_paths.store_prediction_store_promotion_artifact_path(
        run_id=run_id,
        store_number="0772",
        promotion_start_date="2024-09-05",
        promotion_name="Spring Launch",
        artifact_name="prediction-manifest",
        extension="json",
        collision_key=collision_key,
    )


def _write_prediction_manifest(
    *,
    manifest_path: Path,
    promotion_cycle_id: str,
    review_path: Path,
    pos_path: Path,
    reconciliation_path: Path,
) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "store_number": "0772",
                "promotion_header_key": "PROMO_A",
                "promotion_cycle_id": promotion_cycle_id,
                "output_files": {
                    "store_prediction_review_csv": str(review_path),
                    "pos_order_upload_csv": str(pos_path),
                    "reconciliation_csv": str(reconciliation_path),
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


class PromotionPilotValidationTests(unittest.TestCase):
    def test_acceptance_config_loader_validation_fails_on_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "acceptance.csv"
            pd.DataFrame(
                {
                    "store_number": ["0772"],
                    "promotion_name": ["Spring Launch"],
                }
            ).to_csv(config_path, index=False)

            with self.assertRaises(PromotionPilotValidationError):
                load_gold_standard_acceptance_config(config_path)

    def test_source_output_reconciliation_pass_case_writes_manifest_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")

            store_promo_path = _canonical_stage11_path(artifact_paths)
            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _stage11_frame().to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)

            artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id="pilot-run",
                as_of_date="2024-09-01",
                source_frame=_source_frame(),
                stage11_store_promotion_paths=(str(store_promo_path),),
                stage13_review_paths=(str(review_path),),
                stage13_pos_upload_paths=(str(pos_path),),
                stage13_reconciliation_paths=(str(reconciliation_path),),
                artifact_paths=artifact_paths,
            )

            self.assertEqual(artifacts.validation_failure_count, 0)
            self.assertEqual(artifacts.gold_standard_failure_count, 0)
            self.assertTrue(Path(artifacts.pilot_validation_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.validation_manifest_path).exists())
            self.assertTrue(Path(artifacts.validation_skip_summary_path).exists())
            manifest = json.loads(Path(artifacts.validation_manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["validation_status"], "PASS")
            self.assertEqual(manifest["validation_skip_class"], "VALIDATION_EXECUTED")

    def test_source_output_reconciliation_accepts_clean_stage11_store_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")

            store_promo_path = _canonical_stage11_path(artifact_paths)
            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _stage11_frame().drop(
                columns=["promotion_header_key", "promotion_id", "action_code", "review_required_flag", "manual_review_flag"]
            ).to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)

            artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id="pilot-run",
                as_of_date="2024-09-01",
                source_frame=_source_frame(),
                stage11_store_promotion_paths=(str(store_promo_path),),
                stage13_review_paths=(str(review_path),),
                stage13_pos_upload_paths=(str(pos_path),),
                stage13_reconciliation_paths=(str(reconciliation_path),),
                artifact_paths=artifact_paths,
            )

            self.assertEqual(artifacts.validation_failure_count, 0)
            self.assertIn("/promotions/priceline/0772/prediction/2024-09-05/", str(store_promo_path))

    def test_manifest_resolves_existing_published_store_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")

            store_promo_path = _canonical_stage11_path(artifact_paths)
            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            manifest_path = _prediction_manifest_path(artifact_paths)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path, manifest_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _published_store_frame().to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)
            _write_prediction_manifest(
                manifest_path=manifest_path,
                promotion_cycle_id=store_promo_path.stem,
                review_path=review_path,
                pos_path=pos_path,
                reconciliation_path=reconciliation_path,
            )

            artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id="pilot-run",
                as_of_date="2024-09-01",
                source_frame=_source_frame(),
                stage11_store_promotion_paths=tuple(),
                stage13_review_paths=(str(review_path),),
                stage13_pos_upload_paths=(str(pos_path),),
                stage13_reconciliation_paths=(str(reconciliation_path),),
                artifact_paths=artifact_paths,
            )

            self.assertEqual(artifacts.validation_failure_count, 0)

    def test_manifest_resolution_wins_over_deterministic_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            collision_key = "duplicate-cycle"

            store_promo_path = _colliding_stage11_path(artifact_paths, collision_key=collision_key)
            review_path, pos_path, reconciliation_path = _colliding_stage13_paths(
                artifact_paths,
                collision_key=collision_key,
            )
            manifest_path = _prediction_manifest_path(artifact_paths, collision_key=collision_key)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path, manifest_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _published_store_frame().to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)
            _write_prediction_manifest(
                manifest_path=manifest_path,
                promotion_cycle_id=store_promo_path.stem,
                review_path=review_path,
                pos_path=pos_path,
                reconciliation_path=reconciliation_path,
            )

            artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id="pilot-run",
                as_of_date="2024-09-01",
                source_frame=_source_frame(),
                stage11_store_promotion_paths=(str(_canonical_stage11_path(artifact_paths)),),
                stage13_review_paths=(str(review_path),),
                stage13_pos_upload_paths=(str(pos_path),),
                stage13_reconciliation_paths=(str(reconciliation_path),),
                artifact_paths=artifact_paths,
            )

            self.assertEqual(artifacts.validation_failure_count, 0)

    def test_store_csv_without_rich_columns_does_not_trigger_missing_file_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")

            store_promo_path = _canonical_stage11_path(artifact_paths)
            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            manifest_path = _prediction_manifest_path(artifact_paths)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path, manifest_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _minimal_published_store_frame().to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)
            _write_prediction_manifest(
                manifest_path=manifest_path,
                promotion_cycle_id=store_promo_path.stem,
                review_path=review_path,
                pos_path=pos_path,
                reconciliation_path=reconciliation_path,
            )

            artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id="pilot-run",
                as_of_date="2024-09-01",
                source_frame=_source_frame(),
                stage11_store_promotion_paths=tuple(),
                stage13_review_paths=(str(review_path),),
                stage13_pos_upload_paths=(str(pos_path),),
                stage13_reconciliation_paths=(str(reconciliation_path),),
                artifact_paths=artifact_paths,
            )

            self.assertEqual(artifacts.validation_failure_count, 0)
            summary = pd.read_csv(artifacts.pilot_validation_summary_csv_path)
            self.assertFalse(
                summary["failure_reason"].astype(str).str.contains("missing_store_promotion_output_file").any()
            )

    def test_missing_prediction_manifest_uses_deterministic_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")

            store_promo_path = _canonical_stage11_path(artifact_paths)
            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _published_store_frame().to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)

            artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id="pilot-run",
                as_of_date="2024-09-01",
                source_frame=_source_frame(),
                stage11_store_promotion_paths=tuple(),
                stage13_review_paths=(str(review_path),),
                stage13_pos_upload_paths=(str(pos_path),),
                stage13_reconciliation_paths=(str(reconciliation_path),),
                artifact_paths=artifact_paths,
            )

            self.assertEqual(artifacts.validation_failure_count, 0)

    def test_stage13_skips_when_stage12_noop_and_no_new_publications(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")

            artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id="pilot-run-noop",
                as_of_date="2024-09-01",
                source_frame=_source_frame(),
                stage11_store_promotion_paths=tuple(),
                stage13_review_paths=tuple(),
                stage13_pos_upload_paths=tuple(),
                stage13_reconciliation_paths=tuple(),
                artifact_paths=artifact_paths,
                stage12_publish_status="NOOP_ALREADY_PUBLISHED",
                stage12_publish_status_reason="all_candidates_already_published",
            )

            self.assertEqual(artifacts.validation_status, "SKIPPED_NO_NEW_PUBLICATIONS")
            self.assertTrue(artifacts.validation_skipped_flag)
            manifest = json.loads(Path(artifacts.validation_manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["validation_status"], "SKIPPED_NO_NEW_PUBLICATIONS")
            self.assertTrue(manifest["validation_skipped_flag"])
            self.assertEqual(manifest["validation_skip_class"], "STAGE12_NOOP_ALREADY_PUBLISHED")

    def test_stage13_skips_when_stage12_noop_no_publishable_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")

            artifacts = PromotionPilotValidationService().write_validation_outputs(
                run_id="pilot-run-noop-no-publishable",
                as_of_date="2024-09-01",
                source_frame=_source_frame(),
                stage11_store_promotion_paths=tuple(),
                stage13_review_paths=tuple(),
                stage13_pos_upload_paths=tuple(),
                stage13_reconciliation_paths=tuple(),
                artifact_paths=artifact_paths,
                stage12_publish_status="NOOP_VALID_NO_PUBLISHABLE_ROWS",
                stage12_publish_status_reason="legitimate_non_publishable_rows",
            )

            self.assertEqual(artifacts.validation_status, "SKIPPED_NO_NEW_PUBLICATIONS")
            self.assertEqual(artifacts.validation_skip_class, "STAGE12_NOOP_NO_PUBLISHABLE_ROWS")
            self.assertTrue(Path(artifacts.validation_skip_summary_path).exists())
            skip_summary = json.loads(Path(artifacts.validation_skip_summary_path).read_text(encoding="utf-8"))
            self.assertEqual(skip_summary["validation_skip_class"], "STAGE12_NOOP_NO_PUBLISHABLE_ROWS")

    def test_missing_sku_failure_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            store_promo_path = _canonical_stage11_path(artifact_paths)
            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _stage11_frame().iloc[[0]].to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)

            with self.assertRaises(PromotionPilotValidationError):
                PromotionPilotValidationService().write_validation_outputs(
                    run_id="pilot-run",
                    as_of_date="2024-09-01",
                    source_frame=_source_frame(),
                    stage11_store_promotion_paths=(str(store_promo_path),),
                    stage13_review_paths=(str(review_path),),
                    stage13_pos_upload_paths=(str(pos_path),),
                    stage13_reconciliation_paths=(str(reconciliation_path),),
                    artifact_paths=artifact_paths,
                )

            failures = pd.read_csv(artifact_paths.pilot_validation_failures_csv_path("pilot-run"))
            self.assertTrue(failures["failure_reason"].astype(str).str.contains("output_has_fewer_skus_than_source").any())

    def test_duplicate_sku_failure_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            store_promo_path = _canonical_stage11_path(artifact_paths)
            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            duplicate = pd.concat([_stage11_frame(), _stage11_frame().iloc[[0]]], ignore_index=True)
            duplicate.to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)

            with self.assertRaises(PromotionPilotValidationError):
                PromotionPilotValidationService().write_validation_outputs(
                    run_id="pilot-run",
                    as_of_date="2024-09-01",
                    source_frame=_source_frame(),
                    stage11_store_promotion_paths=(str(store_promo_path),),
                    stage13_review_paths=(str(review_path),),
                    stage13_pos_upload_paths=(str(pos_path),),
                    stage13_reconciliation_paths=(str(reconciliation_path),),
                    artifact_paths=artifact_paths,
                )

            failures = pd.read_csv(artifact_paths.pilot_validation_failures_csv_path("pilot-run"))
            self.assertTrue(failures["failure_reason"].astype(str).str.contains("duplicate_store_promotion_sku_rows").any())

    def test_exact_sku_count_mismatch_failure_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            acceptance_path = artifact_paths.promotion_gold_standard_acceptance_config_path()
            acceptance_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {
                    "client_code": ["priceline"],
                    "store_number": ["0772"],
                    "promotion_id": ["PROMO_A"],
                    "promotion_header_key": ["PROMO_A"],
                    "promotion_name": ["Spring Launch"],
                    "promotion_start_date": ["2024-09-05"],
                    "promotion_end_date": ["2024-09-12"],
                    "expected_min_sku_count": [1],
                    "expected_exact_sku_count": [3],
                    "notes": ["gold"],
                    "active_flag": [True],
                }
            ).to_csv(acceptance_path, index=False)

            store_promo_path = _canonical_stage11_path(artifact_paths)
            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            for path in (store_promo_path, review_path, pos_path, reconciliation_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _stage11_frame().to_csv(store_promo_path, index=False)
            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)

            with self.assertRaises(PromotionPilotValidationError):
                PromotionPilotValidationService().write_validation_outputs(
                    run_id="pilot-run",
                    as_of_date="2024-09-01",
                    source_frame=_source_frame(),
                    stage11_store_promotion_paths=(str(store_promo_path),),
                    stage13_review_paths=(str(review_path),),
                    stage13_pos_upload_paths=(str(pos_path),),
                    stage13_reconciliation_paths=(str(reconciliation_path),),
                    artifact_paths=artifact_paths,
                    acceptance_config_path=acceptance_path,
                )

            results = pd.read_csv(artifact_paths.gold_standard_acceptance_results_csv_path("pilot-run"))
            self.assertTrue(results["failure_reason"].astype(str).str.contains("acceptance_exact_sku_count_mismatch").any())

    def test_missing_output_file_failure_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            acceptance_path = artifact_paths.promotion_gold_standard_acceptance_config_path()
            acceptance_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {
                    "client_code": ["priceline"],
                    "store_number": ["0772"],
                    "promotion_id": ["PROMO_A"],
                    "promotion_header_key": ["PROMO_A"],
                    "promotion_name": ["Spring Launch"],
                    "promotion_start_date": ["2024-09-05"],
                    "promotion_end_date": ["2024-09-12"],
                    "expected_min_sku_count": [1],
                    "expected_exact_sku_count": [2],
                    "notes": ["gold"],
                    "active_flag": [True],
                }
            ).to_csv(acceptance_path, index=False)

            review_path, pos_path, reconciliation_path = _canonical_stage13_paths(artifact_paths)
            for path in (review_path, pos_path, reconciliation_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            _stage13_review_frame().to_csv(review_path, index=False)
            _stage13_pos_frame().to_csv(pos_path, index=False)
            _stage13_reconciliation_frame("PASS").to_csv(reconciliation_path, index=False)

            with self.assertRaises(PromotionPilotValidationError):
                PromotionPilotValidationService().write_validation_outputs(
                    run_id="pilot-run",
                    as_of_date="2024-09-01",
                    source_frame=_source_frame(),
                    stage11_store_promotion_paths=tuple(),
                    stage13_review_paths=(str(review_path),),
                    stage13_pos_upload_paths=(str(pos_path),),
                    stage13_reconciliation_paths=(str(reconciliation_path),),
                    artifact_paths=artifact_paths,
                    acceptance_config_path=acceptance_path,
                )

            results = pd.read_csv(artifact_paths.gold_standard_acceptance_results_csv_path("pilot-run"))
            self.assertTrue(results["failure_reason"].astype(str).str.contains("missing_store_promotion_output_file").any())
