from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.extracted_dataset_writer import PromotionExtractionWriter  # noqa: E402
from data.promotions.promotion_base_extractor import (  # noqa: E402
    PromotionExtractionManifest,
    PromotionExtractionPreflightArtifacts,
    PromotionExtractionPreflightResult,
    PromotionExtractionPreflightSummary,
)
from runtime.promotions.audit_promotions_operational_cycle import audit_operational_cycle  # noqa: E402
from runtime.promotions.config import (  # noqa: E402
    PromotionArtifactPaths,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from surfaces.promotions.reporting.operational_cycle_audit_builder import (  # noqa: E402
    PromotionOperationalCycleAuditError,
)
from runtime.promotions.run_promotions_operational_cycle import (  # noqa: E402
    PromotionOperationalCycleExtractionArtifacts,
    run_operational_cycle,
)
from surfaces.promotions.reporting.store_prediction_publisher import (  # noqa: E402
    PromotionPosExclusionThresholdPolicy,
    PromotionStoreExecutionPublishArtifacts,
    PromotionStoreExecutionValidationError,
    StorePredictionPublisher,
)
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)


def _persist_extraction(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    selection_mode: str,
    frame,
    as_of_date: str,
) -> PromotionOperationalCycleExtractionArtifacts:
    manifest = PromotionExtractionManifest(
        run_id=run_id,
        selection_mode=selection_mode,
        query_version="promotion_base_v4",
        as_of_date=as_of_date,
        extracted_at_utc=datetime.now(tz=UTC).isoformat(),
        row_count=int(len(frame.index)),
        column_count=int(len(frame.columns)),
        duplicate_promotion_row_keys=int(frame["promotion_row_key"].duplicated().sum()),
        advice_source_table="dbo.PromotionAdvice",
        realised_sales_source_table="dbo.PwlogD",
        columns=tuple(str(column_name) for column_name in frame.columns),
        candidate_promotion_row_count=int(len(frame.index)),
    )
    persisted = PromotionExtractionWriter().write(
        base_frame=frame,
        manifest=manifest,
        artifact_paths=artifact_paths,
    )
    rendered_sql_path = artifact_paths.manifests_run_root(run_id) / "rendered_sql.sql"
    rendered_sql_parameters_path = artifact_paths.manifests_run_root(run_id) / "rendered_sql_parameters.json"
    telemetry_json_path = artifact_paths.extraction_telemetry_json_path(run_id)
    telemetry_csv_path = artifact_paths.extraction_telemetry_csv_path(run_id)
    diagnostics_summary_json_path = artifact_paths.sql_diagnostics_summary_json_path(run_id)
    diagnostics_summary_txt_path = artifact_paths.sql_diagnostics_summary_txt_path(run_id)
    rendered_sql_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_sql_parameters_path.parent.mkdir(parents=True, exist_ok=True)
    telemetry_json_path.parent.mkdir(parents=True, exist_ok=True)
    telemetry_csv_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_summary_txt_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_sql_path.write_text("SELECT 1\n", encoding="utf-8")
    rendered_sql_parameters_path.write_text('{"as_of_date": "2024-09-01"}', encoding="utf-8")
    telemetry_json_path.write_text('{"status": "succeeded"}', encoding="utf-8")
    telemetry_csv_path.write_text("status\nsucceeded\n", encoding="utf-8")
    diagnostics_summary_json_path.write_text('{"status": "succeeded"}', encoding="utf-8")
    diagnostics_summary_txt_path.write_text("status: succeeded\n", encoding="utf-8")
    return PromotionOperationalCycleExtractionArtifacts(
        selection_mode=selection_mode,
        frame=frame,
        base_path=str(persisted.base_path),
        manifest_path=str(persisted.manifest_path),
        rendered_sql_path=str(rendered_sql_path),
        rendered_sql_parameters_path=str(rendered_sql_parameters_path),
        telemetry_json_path=str(telemetry_json_path),
        telemetry_csv_path=str(telemetry_csv_path),
        diagnostics_summary_json_path=str(diagnostics_summary_json_path),
        diagnostics_summary_txt_path=str(diagnostics_summary_txt_path),
        candidate_promotion_row_count=int(len(frame.index)),
        manifest=manifest.to_dict(),
    )


def _build_preflight_result(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    as_of_date: str,
) -> PromotionExtractionPreflightResult:
    summary_json_path = artifact_paths.extraction_preflight_summary_json_path(run_id)
    summary_csv_path = artifact_paths.extraction_preflight_summary_csv_path(run_id)
    rendered_sql_path = artifact_paths.rendered_preflight_sql_path(run_id)
    rendered_sql_parameters_path = artifact_paths.rendered_preflight_sql_parameters_path(run_id)
    for path in (
        summary_json_path,
        summary_csv_path,
        rendered_sql_path,
        rendered_sql_parameters_path,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    rendered_sql_path.write_text("SELECT 1\n", encoding="utf-8")
    rendered_sql_parameters_path.write_text("{}\n", encoding="utf-8")
    summary = PromotionExtractionPreflightSummary(
        run_id=run_id,
        selection_mode="completed",
        extraction_mode="live_sql",
        as_of_date=as_of_date,
        query_version="promotion_base_v4",
        preflight_status="succeeded",
        verdict="SAFE_TO_EXTRACT",
        reason="within completed extraction thresholds",
        rendered_query_parameter_summary={},
        diagnostic_filter_summary={},
        estimated_window_summary={},
        planner_thresholds={
            "max_candidate_promotion_rows": 2000,
            "max_candidate_store_sku": 1000,
            "max_window_span_days_total": 125000,
            "max_window_span_days_max": 120,
        },
        constraint_results={},
        candidate_promotion_row_count=8,
        candidate_store_sku_count=6,
        candidate_window_count=6,
        candidate_window_span_days_total=42,
        candidate_window_span_days_max=7,
    )
    summary_json_path.write_text(json.dumps(summary.to_dict(), sort_keys=True), encoding="utf-8")
    summary_csv_path.write_text("metric,value\nverdict,SAFE_TO_EXTRACT\n", encoding="utf-8")
    return PromotionExtractionPreflightResult(
        summary=summary,
        artifacts=PromotionExtractionPreflightArtifacts(
            summary_json_path=str(summary_json_path),
            summary_csv_path=str(summary_csv_path),
            rendered_sql_path=str(rendered_sql_path),
            rendered_sql_parameters_path=str(rendered_sql_parameters_path),
        ),
    )


def _publisher_with_noop_fallback(artifact_paths: PromotionArtifactPaths):
    original_publish = StorePredictionPublisher.publish

    def _publish_without_zero_fail(self, **kwargs):
        try:
            return original_publish(
                self,
                exclusion_threshold_policy=PromotionPosExclusionThresholdPolicy(
                    fail_if_zero_published=False,
                ),
                **kwargs,
            )
        except PromotionStoreExecutionValidationError as exc:
            if "FAIL_NO_ELIGIBLE_ROWS" not in str(exc):
                raise
            run_id = str(kwargs["run_id"])
            summary_path = artifact_paths.commercial_publication_summary_csv_path(run_id)
            diagnostics_path = summary_path.parent / "publication_noop_diagnostics.json"
            skipped_path = summary_path.parent / "publication_noop_skipped_predictions.csv"
            return PromotionStoreExecutionPublishArtifacts(
                prediction_registry_path=str(artifact_paths.prediction_registry_path()),
                store_cycle_manifest_paths=tuple(),
                pos_upload_paths=tuple(),
                review_paths=tuple(),
                summary_paths=tuple(),
                reconciliation_paths=tuple(),
                diagnostics_paths=(str(diagnostics_path),),
                skipped_paths=(str(skipped_path),),
                publication_summary_path=str(summary_path),
                stores_published=0,
                promotion_cycles_published=0,
                pos_upload_row_count=0,
                pos_excluded_row_count=0,
                skipped_duplicate_prediction_count=0,
                skipped_due_to_registry_duplicate_count=0,
                skipped_due_to_review_count=0,
                skipped_due_to_schema_count=0,
                skipped_due_to_mapping_count=0,
                skipped_due_to_null_sku_count=0,
                candidate_row_count=0,
                pos_candidate_row_count=0,
                prior_publication_detected_flag=False,
                noop_already_published_flag=True,
                publish_status="NOOP_ALREADY_PUBLISHED",
                publish_status_reason="test_harness_no_eligible_rows",
            )

    return _publish_without_zero_fail


class PromotionOperationalCycleAuditTests(unittest.TestCase):
    def test_audit_runner_writes_expected_operational_cycle_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                ),
                runtime_date=datetime(2024, 9, 1, tzinfo=UTC).date(),
                artifacts=artifact_paths,
            )
            completed_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="audit-run",
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="audit-run-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="audit-run",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle._extract_promotions_base_artifact",
                side_effect=[completed_extraction, future_extraction],
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publisher_with_noop_fallback(artifact_paths),
            ):
                cycle_artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="audit-run",
                    score_run_id="audit-run-score",
                    decision_surface_run_id="audit-run-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                )

            audit_artifacts = audit_operational_cycle(
                operational_cycle_manifest_path=cycle_artifacts.manifest_path,
                artifact_root=str(artifact_paths.root),
            )
            summary_payload = json.loads(Path(audit_artifacts.summary_json_path).read_text(encoding="utf-8"))
            top_opportunities = pd.read_csv(audit_artifacts.report_paths["top_predicted_opportunities"]["csv"])
            supplier_summary = pd.read_csv(audit_artifacts.report_paths["supplier_run_summary"]["csv"])

            self.assertTrue(Path(audit_artifacts.summary_json_path).exists())
            self.assertTrue(Path(audit_artifacts.summary_csv_path).exists())
            self.assertTrue(Path(audit_artifacts.audit_manifest_path).exists())
            self.assertIn("top_margin_traps", audit_artifacts.report_paths)
            self.assertIn("top_leftover_risks", audit_artifacts.report_paths)
            self.assertIn("top_stockout_risks", audit_artifacts.report_paths)
            self.assertIn("top_row_vs_cohort_disagreements", audit_artifacts.report_paths)
            self.assertIn("supplier_run_summary", audit_artifacts.report_paths)
            self.assertIn("department_run_summary", audit_artifacts.report_paths)
            self.assertIn("store_run_summary", audit_artifacts.report_paths)
            self.assertGreater(summary_payload["rows_scored"], 0)
            self.assertIn("calibration_thresholds_used", summary_payload)
            self.assertIn("artifact_paths_produced", summary_payload)
            self.assertEqual(
                summary_payload["artifact_paths_produced"]["store_prediction_download_path"],
                cycle_artifacts.store_prediction_download_path,
            )
            self.assertEqual(
                summary_payload["artifact_paths_produced"]["inspection_review_packet_csv_path"],
                cycle_artifacts.inspection_review_packet_csv_path,
            )
            self.assertFalse(top_opportunities.empty)
            self.assertIn("predicted_gross_profit", top_opportunities.columns)
            self.assertFalse(supplier_summary.empty)

    def test_audit_runner_marks_training_dataset_unavailable_for_live_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                ),
                runtime_date=datetime(2024, 9, 1, tzinfo=UTC).date(),
                artifacts=artifact_paths,
            )
            completed_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="audit-live-contract",
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="audit-live-contract-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="audit-live-contract",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle._extract_promotions_base_artifact",
                side_effect=[completed_extraction, future_extraction],
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publisher_with_noop_fallback(artifact_paths),
            ):
                cycle_artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="audit-live-contract",
                    score_run_id="audit-live-contract-score",
                    decision_surface_run_id="audit-live-contract-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    execution_mode="live_sql",
                )

            manifest_path = Path(cycle_artifacts.manifest_path)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            dataset_path = Path(str(payload["training_dataset"]["dataset_path"]))
            if dataset_path.exists():
                dataset_path.unlink()

            audit_artifacts = audit_operational_cycle(
                operational_cycle_manifest_path=cycle_artifacts.manifest_path,
                artifact_root=str(artifact_paths.root),
            )
            summary_payload = json.loads(Path(audit_artifacts.summary_json_path).read_text(encoding="utf-8"))
            audit_manifest_payload = json.loads(
                Path(audit_artifacts.audit_manifest_path).read_text(encoding="utf-8")
            )
            contract = {
                item["artifact_name"]: item
                for item in summary_payload["audit_artifact_contract"]
            }
            training_contract = contract["training_ready.parquet"]
            manifest_contract = {
                item["artifact_name"]: item
                for item in audit_manifest_payload["audit_artifact_contract"]
            }

            self.assertEqual(training_contract["artifact_required_flag"], False)
            self.assertEqual(training_contract["artifact_exists_flag"], False)
            self.assertEqual(training_contract["artifact_status"], "unavailable_for_run_mode")
            self.assertEqual(training_contract["artifact_status_reason"], "not_produced_in_live_mode")
            self.assertEqual(
                manifest_contract["training_ready.parquet"]["artifact_status"],
                "unavailable_for_run_mode",
            )

    def test_audit_runner_fails_when_training_mode_requires_missing_training_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                ),
                runtime_date=datetime(2024, 9, 1, tzinfo=UTC).date(),
                artifacts=artifact_paths,
            )
            completed_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="audit-training-contract",
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="audit-training-contract-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="audit-training-contract",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle._extract_promotions_base_artifact",
                side_effect=[completed_extraction, future_extraction],
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publisher_with_noop_fallback(artifact_paths),
            ):
                cycle_artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="audit-training-contract",
                    score_run_id="audit-training-contract-score",
                    decision_surface_run_id="audit-training-contract-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    execution_mode="live_sql",
                )

            manifest_path = Path(cycle_artifacts.manifest_path)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["execution_mode"] = "training_hybrid"
            dataset_path = Path(str(payload["training_dataset"]["dataset_path"]))
            if dataset_path.exists():
                dataset_path.unlink()
            manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

            with self.assertRaises(PromotionOperationalCycleAuditError):
                audit_operational_cycle(
                    operational_cycle_manifest_path=cycle_artifacts.manifest_path,
                    artifact_root=str(artifact_paths.root),
                )
