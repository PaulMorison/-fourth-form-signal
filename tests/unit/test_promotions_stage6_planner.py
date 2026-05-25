from __future__ import annotations

"""Unit tests for the Stage 6 future-extraction cost/survivability planner."""

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
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
from data.promotions.sql import PromotionBaseQueryOptions  # noqa: E402
from runtime.promotions.config import (  # noqa: E402
    PromotionArtifactPaths,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from runtime.promotions.run_promotions_operational_cycle import (  # noqa: E402
    PromotionOperationalCycleExtractionArtifacts,
    _Stage6ExecutionPlan,
    _optional_error_output_path,
    _plan_stage6_future_extraction,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persist_extraction(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    selection_mode: str,
    frame: pd.DataFrame,
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
        columns=tuple(str(c) for c in frame.columns),
        extraction_mode="live_sql",
        candidate_promotion_row_count=int(len(frame.index)),
    )
    persisted = PromotionExtractionWriter().write(
        base_frame=frame,
        manifest=manifest,
        artifact_paths=artifact_paths,
    )
    for path_obj in [
        artifact_paths.manifests_run_root(run_id) / "rendered_sql.sql",
        artifact_paths.manifests_run_root(run_id) / "rendered_sql_parameters.json",
        artifact_paths.extraction_telemetry_json_path(run_id),
        artifact_paths.extraction_telemetry_csv_path(run_id),
        artifact_paths.sql_diagnostics_summary_json_path(run_id),
        artifact_paths.sql_diagnostics_summary_txt_path(run_id),
    ]:
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text("{}", encoding="utf-8")
    return PromotionOperationalCycleExtractionArtifacts(
        selection_mode=selection_mode,
        frame=frame,
        base_path=str(persisted.base_path),
        manifest_path=str(persisted.manifest_path),
        rendered_sql_path=str(
            artifact_paths.manifests_run_root(run_id) / "rendered_sql.sql"
        ),
        rendered_sql_parameters_path=str(
            artifact_paths.manifests_run_root(run_id) / "rendered_sql_parameters.json"
        ),
        telemetry_json_path=str(artifact_paths.extraction_telemetry_json_path(run_id)),
        telemetry_csv_path=str(artifact_paths.extraction_telemetry_csv_path(run_id)),
        diagnostics_summary_json_path=str(
            artifact_paths.sql_diagnostics_summary_json_path(run_id)
        ),
        diagnostics_summary_txt_path=str(
            artifact_paths.sql_diagnostics_summary_txt_path(run_id)
        ),
        candidate_promotion_row_count=int(len(frame.index)),
        manifest=manifest.to_dict(),
        extraction_mode="live_sql",
    )


def _build_preflight_result(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    as_of_date: str,
    verdict: str = "SAFE_TO_EXTRACT",
    reason: str = "within completed extraction thresholds",
) -> PromotionExtractionPreflightResult:
    summary_json_path = artifact_paths.extraction_preflight_summary_json_path(run_id)
    summary_csv_path = artifact_paths.extraction_preflight_summary_csv_path(run_id)
    rendered_sql_path = artifact_paths.rendered_preflight_sql_path(run_id)
    rendered_sql_parameters_path = artifact_paths.rendered_preflight_sql_parameters_path(run_id)
    for path_obj in (
        summary_json_path,
        summary_csv_path,
        rendered_sql_path,
        rendered_sql_parameters_path,
    ):
        path_obj.parent.mkdir(parents=True, exist_ok=True)
    rendered_sql_path.write_text("SELECT 1\n", encoding="utf-8")
    rendered_sql_parameters_path.write_text("{}\n", encoding="utf-8")
    summary = PromotionExtractionPreflightSummary(
        run_id=run_id,
        selection_mode="completed",
        extraction_mode="live_sql",
        as_of_date=as_of_date,
        query_version="promotion_base_v4",
        preflight_status="succeeded",
        verdict=verdict,
        reason=reason,
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
    summary_csv_path.write_text("metric,value\nverdict,%s\n" % verdict, encoding="utf-8")
    return PromotionExtractionPreflightResult(
        summary=summary,
        artifacts=PromotionExtractionPreflightArtifacts(
            summary_json_path=str(summary_json_path),
            summary_csv_path=str(summary_csv_path),
            rendered_sql_path=str(rendered_sql_path),
            rendered_sql_parameters_path=str(rendered_sql_parameters_path),
        ),
    )


def _build_pilot_validation_noop(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
) -> SimpleNamespace:
    validation_root = artifact_paths.root / "validation" / run_id
    validation_root.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        pilot_validation_summary_csv_path=str(validation_root / "pilot_validation_summary.csv"),
        pilot_validation_summary_json_path=str(validation_root / "pilot_validation_summary.json"),
        pilot_validation_failures_csv_path=str(validation_root / "pilot_validation_failures.csv"),
        gold_standard_acceptance_results_csv_path=str(
            validation_root / "gold_standard_acceptance_results.csv"
        ),
        gold_standard_acceptance_results_json_path=str(
            validation_root / "gold_standard_acceptance_results.json"
        ),
        validation_manifest_path=str(validation_root / "validation_manifest.json"),
        validation_status="SKIPPED",
        validation_status_reason="test_harness_stage6_guardrail_focus",
        validation_skipped_flag=True,
        validation_skip_class="TEST_HARNESS_NOOP",
        validation_skip_message="Stage 6 guardrail test bypassed downstream pilot validation.",
        validation_skip_summary_path=str(validation_root / "validation_skip_summary.json"),
        validation_reference_cycle_path="not_applicable",
        validation_failure_count=0,
        gold_standard_failure_count=0,
    )


# ---------------------------------------------------------------------------
# _plan_stage6_future_extraction — pure unit tests (no I/O)
# ---------------------------------------------------------------------------


class TestPlanStage6FutureExtraction(unittest.TestCase):
    def test_proof_mode_with_limit_returns_proof_bounded(self) -> None:
        plan = _plan_stage6_future_extraction(
            proof_mode=True,
            proof_max_future_promotions=500,
            query_timeout_seconds=180,
        )
        self.assertIsInstance(plan, _Stage6ExecutionPlan)
        self.assertEqual(plan.execution_scope, "proof_bounded_scope")
        self.assertEqual(plan.future_extraction_mode, "diagnostic_topn")
        self.assertIsNotNone(plan.future_query_options)
        assert plan.future_query_options is not None
        self.assertEqual(plan.future_query_options.extraction_mode, "diagnostic_topn")
        self.assertEqual(plan.future_query_options.limit_promotions, 500)
        self.assertEqual(plan.proof_max_future_promotions, 500)
        self.assertTrue(plan.proof_bounded)
        self.assertEqual(plan.query_timeout_seconds, 180)
        self.assertEqual(plan.planner_verdict, "PROOF_BOUNDED_SCOPE")
        self.assertTrue(plan.proof_bounding_supported_flag)
        self.assertIn("diagnostic_topn", plan.proof_bounding_reason)
        self.assertIn("proof_mode is active", plan.guardrail_reason)

    def test_proof_mode_without_limit_uses_bounded_fallback(self) -> None:
        plan = _plan_stage6_future_extraction(
            proof_mode=True,
            proof_max_future_promotions=None,
            query_timeout_seconds=180,
        )
        self.assertEqual(plan.execution_scope, "proof_bounded_scope")
        self.assertEqual(plan.future_extraction_mode, "diagnostic_topn")
        self.assertIsNotNone(plan.future_query_options)
        assert plan.future_query_options is not None
        self.assertEqual(plan.future_query_options.extraction_mode, "diagnostic_topn")
        self.assertEqual(plan.future_query_options.limit_promotions, 50)
        self.assertTrue(plan.proof_bounded)
        self.assertEqual(plan.planner_verdict, "PROOF_BOUNDED_FALLBACK")
        self.assertTrue(plan.proof_bounding_supported_flag)
        self.assertTrue(plan.proof_fallback_used)
        self.assertEqual(plan.proof_fallback_mode, "diagnostic_topn")
        self.assertIn("limit_promotions=50", plan.proof_fallback_reason or "")

    def test_proof_mode_without_limit_uses_proof_slice_fallback_when_requested(self) -> None:
        plan = _plan_stage6_future_extraction(
            proof_mode=True,
            proof_max_future_promotions=None,
            proof_future_fallback_mode="proof_slice",
            proof_future_fallback_slice_promotions=12,
            query_timeout_seconds=180,
        )
        self.assertEqual(plan.execution_scope, "proof_bounded_scope")
        self.assertEqual(plan.future_extraction_mode, "diagnostic_topn")
        self.assertIsNotNone(plan.future_query_options)
        assert plan.future_query_options is not None
        self.assertEqual(plan.future_query_options.limit_promotions, 12)
        self.assertTrue(plan.proof_fallback_used)
        self.assertEqual(plan.proof_fallback_mode, "proof_slice")
        self.assertIn("proof_slice", plan.proof_fallback_reason or "")

    def test_no_proof_mode_with_limit_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires proof_mode=true"):
            _plan_stage6_future_extraction(
                proof_mode=False,
                proof_max_future_promotions=500,
                query_timeout_seconds=180,
            )

    def test_no_proof_mode_with_fallback_controls_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "require proof_mode=true"):
            _plan_stage6_future_extraction(
                proof_mode=False,
                proof_max_future_promotions=None,
                proof_future_fallback_mode="diagnostic_topn",
                query_timeout_seconds=180,
            )

    def test_no_proof_mode_no_limit_returns_full_scope(self) -> None:
        plan = _plan_stage6_future_extraction(
            proof_mode=False,
            proof_max_future_promotions=None,
            query_timeout_seconds=420,
        )
        self.assertEqual(plan.execution_scope, "full_scope")
        self.assertEqual(plan.future_extraction_mode, "live_sql")
        self.assertIsNone(plan.future_query_options)
        self.assertFalse(plan.proof_bounded)
        self.assertEqual(plan.planner_verdict, "FULL_SCOPE")
        self.assertEqual(plan.query_timeout_seconds, 420)

    def test_none_query_timeout_is_propagated(self) -> None:
        plan = _plan_stage6_future_extraction(
            proof_mode=True,
            proof_max_future_promotions=25,
            query_timeout_seconds=None,
        )
        self.assertIsNone(plan.query_timeout_seconds)
        self.assertEqual(plan.execution_scope, "proof_bounded_scope")

    def test_optional_error_output_path_uses_fallback(self) -> None:
        error = RuntimeError("stage6 failure")
        self.assertEqual(
            _optional_error_output_path(
                error,
                "stage6_future_extraction_plan_path",
                fallback="/tmp/fallback-plan.json",
            ),
            "/tmp/fallback-plan.json",
        )


# ---------------------------------------------------------------------------
# Stage 6 integration — guardrail artifact and query_options propagation
# ---------------------------------------------------------------------------


class TestStage6GuardrailArtifact(unittest.TestCase):
    """Verify that Stage 6 writes the guardrail file and passes query_options to the extractor."""

    def _build_settings(
        self, artifact_paths: PromotionArtifactPaths, as_of_date: datetime
    ) -> PromotionPipelineSettings:
        return PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
                query_timeout_seconds=180,
            ),
            runtime_date=as_of_date.date(),
            artifacts=artifact_paths,
        )

    def test_proof_mode_writes_proof_bounded_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "artifacts",
                local_inspection_root=None,
            )
            settings = self._build_settings(
                artifact_paths, datetime(2024, 9, 1, tzinfo=UTC)
            )
            run_id = "s6-proof-test"
            score_run_id = f"{run_id}-score"
            completed_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id=run_id,
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id=score_run_id,
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            captured_calls: list[dict] = []

            def _mock_extractor(**kwargs):
                captured_calls.append(dict(kwargs))
                selection_mode = kwargs["selection_mode"]
                if selection_mode == "completed":
                    return completed_extraction
                return future_extraction

            original_publish = StorePredictionPublisher.publish

            def _publish_without_zero_fail(self_pub, **kwargs):
                try:
                    return original_publish(
                        self_pub,
                        exclusion_threshold_policy=PromotionPosExclusionThresholdPolicy(
                            fail_if_zero_published=False,
                        ),
                        **kwargs,
                    )
                except PromotionStoreExecutionValidationError as exc:
                    if "FAIL_NO_ELIGIBLE_ROWS" not in str(exc):
                        raise
                    run_id_inner = str(kwargs["run_id"])
                    summary_path = artifact_paths.commercial_publication_summary_csv_path(run_id_inner)
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

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publish_without_zero_fail,
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle."
                "PromotionPilotValidationService.write_validation_outputs",
                return_value=_build_pilot_validation_noop(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                ),
            ):
                run_operational_cycle(
                    settings=settings,
                    run_id=run_id,
                    score_run_id=score_run_id,
                    decision_surface_run_id=f"{run_id}-ds",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    execution_mode="live_sql",
                    extraction_provider=_mock_extractor,
                    proof_mode=True,
                    proof_max_future_promotions=25,
                )

            # Verify the Stage 6 extractor call received query_options with limit_promotions=25.
            future_call = next(
                c for c in captured_calls if c.get("selection_mode") == "future"
            )
            query_options = future_call.get("query_options")
            self.assertIsNotNone(query_options, "query_options should be passed to Stage 6 extractor in proof mode")
            self.assertIsInstance(query_options, PromotionBaseQueryOptions)
            assert query_options is not None
            self.assertEqual(query_options.extraction_mode, "diagnostic_topn")
            self.assertEqual(query_options.limit_promotions, 25)

            # Verify the guardrail JSON artifact was written.
            guardrail_path = (
                artifact_paths.manifests_run_root(score_run_id)
                / "stage6_future_extraction_guardrail.json"
            )
            self.assertTrue(guardrail_path.exists(), "stage6_future_extraction_guardrail.json must exist")
            guardrail = json.loads(guardrail_path.read_text(encoding="utf-8"))
            self.assertEqual(guardrail["stage"], 6)
            self.assertTrue(guardrail["requested_proof_mode_flag"])
            self.assertEqual(guardrail["requested_proof_max_future_promotions"], 25)
            self.assertEqual(guardrail["resolved_execution_scope"], "proof_bounded_scope")
            self.assertEqual(guardrail["execution_scope"], "proof_bounded_scope")
            self.assertEqual(guardrail["future_extraction_mode"], "diagnostic_topn")
            self.assertTrue(guardrail["proof_mode"])
            self.assertEqual(guardrail["proof_max_future_promotions"], 25)
            self.assertFalse(guardrail["proof_fallback_used"])
            self.assertIsNone(guardrail["proof_fallback_mode"])
            self.assertIsNone(guardrail["proof_fallback_reason"])
            self.assertEqual(guardrail["future_query_options"]["limit_promotions"], 25)
            self.assertEqual(guardrail["future_query_options"]["extraction_mode"], "diagnostic_topn")
            self.assertEqual(guardrail["planner_verdict"], "PROOF_BOUNDED_SCOPE")
            self.assertTrue(guardrail["proof_bounding_supported_flag"])
            self.assertEqual(guardrail["query_timeout_seconds"], 180)

            operational_manifest_path = artifact_paths.operational_cycle_manifest_path(run_id)
            manifest = json.loads(operational_manifest_path.read_text(encoding="utf-8"))
            final_outputs = manifest.get("final_outputs", {})
            self.assertEqual(final_outputs.get("stage6_execution_scope"), "proof_bounded_scope")
            self.assertEqual(final_outputs.get("stage6_planner_verdict"), "PROOF_BOUNDED_SCOPE")
            self.assertEqual(final_outputs.get("stage6_proof_fallback_used"), "false")
            self.assertEqual(final_outputs.get("stage6_proof_fallback_mode"), "none")

    def test_full_scope_writes_full_scope_guardrail_and_no_query_options(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "artifacts",
                local_inspection_root=None,
            )
            settings = self._build_settings(
                artifact_paths, datetime(2024, 9, 1, tzinfo=UTC)
            )
            run_id = "s6-full-scope-test"
            score_run_id = f"{run_id}-score"
            completed_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id=run_id,
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id=score_run_id,
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            captured_calls: list[dict] = []

            def _mock_extractor(**kwargs):
                captured_calls.append(dict(kwargs))
                selection_mode = kwargs["selection_mode"]
                if selection_mode == "completed":
                    return completed_extraction
                return future_extraction

            original_publish = StorePredictionPublisher.publish

            def _publish_without_zero_fail(self_pub, **kwargs):
                try:
                    return original_publish(
                        self_pub,
                        exclusion_threshold_policy=PromotionPosExclusionThresholdPolicy(
                            fail_if_zero_published=False,
                        ),
                        **kwargs,
                    )
                except PromotionStoreExecutionValidationError as exc:
                    if "FAIL_NO_ELIGIBLE_ROWS" not in str(exc):
                        raise
                    run_id_inner = str(kwargs["run_id"])
                    summary_path = artifact_paths.commercial_publication_summary_csv_path(run_id_inner)
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

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publish_without_zero_fail,
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle."
                "PromotionPilotValidationService.write_validation_outputs",
                return_value=_build_pilot_validation_noop(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                ),
            ):
                run_operational_cycle(
                    settings=settings,
                    run_id=run_id,
                    score_run_id=score_run_id,
                    decision_surface_run_id=f"{run_id}-ds",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    execution_mode="live_sql",
                    extraction_provider=_mock_extractor,
                    proof_mode=False,
                    proof_max_future_promotions=None,
                )

            # Verify the Stage 6 extractor call received no query_options (full scope).
            future_call = next(
                c for c in captured_calls if c.get("selection_mode") == "future"
            )
            query_options = future_call.get("query_options")
            self.assertIsNone(query_options, "query_options should be None for full-scope Stage 6")

            # Verify the guardrail JSON artifact was written with FULL_SCOPE.
            guardrail_path = (
                artifact_paths.manifests_run_root(score_run_id)
                / "stage6_future_extraction_guardrail.json"
            )
            self.assertTrue(guardrail_path.exists(), "stage6_future_extraction_guardrail.json must exist")
            guardrail = json.loads(guardrail_path.read_text(encoding="utf-8"))
            self.assertFalse(guardrail["requested_proof_mode_flag"])
            self.assertIsNone(guardrail["requested_proof_max_future_promotions"])
            self.assertEqual(guardrail["resolved_execution_scope"], "full_scope")
            self.assertEqual(guardrail["execution_scope"], "full_scope")
            self.assertEqual(guardrail["future_extraction_mode"], "live_sql")
            self.assertFalse(guardrail["proof_mode"])
            self.assertFalse(guardrail["proof_fallback_used"])
            self.assertIsNone(guardrail["proof_fallback_mode"])
            self.assertIsNone(guardrail["proof_fallback_reason"])
            self.assertIsNone(guardrail["future_query_options"]["limit_promotions"])
            self.assertIsNone(guardrail["future_query_options"]["extraction_mode"])
            self.assertEqual(guardrail["planner_verdict"], "FULL_SCOPE")

    def test_planner_rejection_writes_stage6_rejection_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "artifacts",
                local_inspection_root=None,
            )
            settings = self._build_settings(
                artifact_paths, datetime(2024, 9, 1, tzinfo=UTC)
            )
            run_id = "s6-planner-reject-test"
            score_run_id = f"{run_id}-score"
            completed_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id=run_id,
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            captured_calls: list[dict] = []

            def _mock_extractor(**kwargs):
                captured_calls.append(dict(kwargs))
                if kwargs["selection_mode"] == "completed":
                    return completed_extraction
                raise AssertionError("future extraction should not run after planner rejection")

            original_publish = StorePredictionPublisher.publish

            def _publish_without_zero_fail(self_pub, **kwargs):
                try:
                    return original_publish(
                        self_pub,
                        exclusion_threshold_policy=PromotionPosExclusionThresholdPolicy(
                            fail_if_zero_published=False,
                        ),
                        **kwargs,
                    )
                except PromotionStoreExecutionValidationError as exc:
                    if "FAIL_NO_ELIGIBLE_ROWS" not in str(exc):
                        raise
                    run_id_inner = str(kwargs["run_id"])
                    summary_path = artifact_paths.commercial_publication_summary_csv_path(run_id_inner)
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

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publish_without_zero_fail,
            ):
                with self.assertRaisesRegex(ValueError, "requires proof_mode=true"):
                    run_operational_cycle(
                        settings=settings,
                        run_id=run_id,
                        score_run_id=score_run_id,
                        decision_surface_run_id=f"{run_id}-ds",
                        minimum_cohort_sample_size=1,
                        similarity_threshold=0.50,
                        archetype_confidence_floor=0.35,
                        row_model_confidence_floor=0.35,
                        execution_mode="live_sql",
                        extraction_provider=_mock_extractor,
                        proof_mode=False,
                        proof_max_future_promotions=25,
                    )

            self.assertEqual(
                [call["selection_mode"] for call in captured_calls],
                ["completed"],
            )
            guardrail_path = (
                artifact_paths.manifests_run_root(score_run_id)
                / "stage6_future_extraction_guardrail.json"
            )
            plan_path = (
                artifact_paths.manifests_run_root(score_run_id)
                / "stage6_future_extraction_plan.json"
            )
            failure_path = (
                artifact_paths.manifests_run_root(score_run_id)
                / "stage6_future_extraction_failure_summary.json"
            )
            self.assertTrue(guardrail_path.exists())
            self.assertTrue(plan_path.exists())
            self.assertTrue(failure_path.exists())

            failure_summary = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(failure_summary["failure_phase"], "planner_rejection")
            self.assertEqual(failure_summary["planner_verdict"], "PLANNER_REJECTED")
            self.assertFalse(failure_summary["requested_proof_mode_flag"])
            self.assertEqual(failure_summary["requested_proof_max_future_promotions"], 25)
            self.assertFalse(failure_summary["proof_fallback_used"])
            self.assertIsNone(failure_summary["proof_fallback_mode"])
            self.assertIsNone(failure_summary["future_extraction_mode"])
            self.assertIn("planner rejected", failure_summary["operator_message"].lower())
            self.assertIn("requires proof_mode=true", failure_summary["reason"])

            operational_manifest_path = artifact_paths.operational_cycle_manifest_path(run_id)
            manifest = json.loads(operational_manifest_path.read_text(encoding="utf-8"))
            final_outputs = manifest.get("final_outputs", {})
            self.assertEqual(final_outputs.get("stage6_planner_verdict"), "PLANNER_REJECTED")
            self.assertEqual(final_outputs.get("stage6_proof_fallback_used"), "false")
            self.assertEqual(final_outputs.get("stage6_proof_fallback_mode"), "none")

    def test_stage6_runtime_failure_preserves_primary_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "artifacts",
                local_inspection_root=None,
            )
            settings = self._build_settings(
                artifact_paths, datetime(2024, 9, 1, tzinfo=UTC)
            )
            run_id = "s6-runtime-failure-test"
            score_run_id = f"{run_id}-score"
            completed_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id=run_id,
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            def _mock_extractor(**kwargs):
                if kwargs["selection_mode"] == "completed":
                    return completed_extraction
                raise RuntimeError("primary stage6 failure sentinel")

            original_publish = StorePredictionPublisher.publish

            def _publish_without_zero_fail(self_pub, **kwargs):
                try:
                    return original_publish(
                        self_pub,
                        exclusion_threshold_policy=PromotionPosExclusionThresholdPolicy(
                            fail_if_zero_published=False,
                        ),
                        **kwargs,
                    )
                except PromotionStoreExecutionValidationError as exc:
                    if "FAIL_NO_ELIGIBLE_ROWS" not in str(exc):
                        raise
                    run_id_inner = str(kwargs["run_id"])
                    summary_path = artifact_paths.commercial_publication_summary_csv_path(run_id_inner)
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

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publish_without_zero_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "primary stage6 failure sentinel"):
                    run_operational_cycle(
                        settings=settings,
                        run_id=run_id,
                        score_run_id=score_run_id,
                        decision_surface_run_id=f"{run_id}-ds",
                        minimum_cohort_sample_size=1,
                        similarity_threshold=0.50,
                        archetype_confidence_floor=0.35,
                        row_model_confidence_floor=0.35,
                        execution_mode="live_sql",
                        extraction_provider=_mock_extractor,
                        proof_mode=True,
                        proof_max_future_promotions=25,
                    )

            failure_path = (
                artifact_paths.manifests_run_root(score_run_id)
                / "stage6_future_extraction_failure_summary.json"
            )
            self.assertTrue(failure_path.exists())
            failure_summary = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(failure_summary["failure_phase"], "sql_runtime_failure")
            self.assertEqual(failure_summary["planner_verdict"], "PROOF_BOUNDED_SCOPE")
            self.assertEqual(failure_summary["exception_type"], "RuntimeError")
            self.assertEqual(failure_summary["reason"], "primary stage6 failure sentinel")
            self.assertFalse(failure_summary["proof_fallback_used"])
            self.assertIsNone(failure_summary["proof_fallback_mode"])
            self.assertIn("proof-bounded", failure_summary["operator_message"].lower())


