from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.extracted_dataset_writer import PromotionExtractionWriter  # noqa: E402
from data.promotions.mssql_query_executor import (  # noqa: E402
    PromotionMssqlQueryError,
    PromotionMssqlQueryTimeoutError,
)
from data.promotions.promotion_base_extractor import (  # noqa: E402
    PromotionBaseExtractionResult,
    PromotionExtractionManifest,
    PromotionExtractionPreflightArtifacts,
    PromotionExtractionPreflightResult,
    PromotionExtractionPreflightSummary,
    PromotionExtractionTelemetry,
)
from data.promotions.sql import PromotionBaseQueryOptions  # noqa: E402
from runtime.promotions.config import (  # noqa: E402
    PromotionArtifactPaths,
    PromotionCompletedExtractionRuntimeSettings,
    PromotionCompletedPartitionSettings,
    PromotionCompletedPreflightPlannerSettings,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from runtime.promotions.completed_extraction_batches import (  # noqa: E402
    PromotionCompletedPartitionArtifactResolutionError,
    execute_completed_partition_landed_batches,
)
from runtime.promotions.run_promotions_operational_cycle import (  # noqa: E402
    PromotionCompletedExtractionInterruptedError,
    PromotionCompletedPreflightRejectedError,
    PromotionOperationalCycleExtractionArtifacts,
    _build_failure_final_outputs,
    _build_parser,
    _build_settings,
    _completed_partition_run_id,
    _derive_stage12_legitimate_excluded_row_count,
    _extract_promotions_base_artifact,
    _load_existing_completed_partition_artifact,
    _validate_artifact_roots,
    run_operational_cycle,
)
from surfaces.promotions.reporting.store_prediction_publisher import (  # noqa: E402
    PromotionStoreExecutionPublishArtifacts,
    PromotionStoreExecutionValidationError,
    PromotionPosExclusionThresholdPolicy,
    StorePredictionPublisher,
)
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)


SQL_RETRY_ENV_KEYS = (
    "PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS",
    "PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS",
    "PROMOTIONS_SQL_CONNECT_RETRY_ATTEMPTS",
    "PROMOTIONS_SQL_CONNECT_RETRY_BACKOFF_SECONDS",
)


class OperationalCycleRuntimeSettingsTests(unittest.TestCase):
    def test_stage12_legitimate_exclusions_do_not_subtract_registry_duplicates(self) -> None:
        artifacts = PromotionStoreExecutionPublishArtifacts(
            prediction_registry_path="registry.parquet",
            store_cycle_manifest_paths=tuple(),
            pos_upload_paths=tuple(),
            review_paths=tuple(),
            summary_paths=tuple(),
            reconciliation_paths=tuple(),
            diagnostics_paths=tuple(),
            skipped_paths=tuple(),
            publication_summary_path="publication_summary.csv",
            stores_published=1,
            promotion_cycles_published=1,
            pos_upload_row_count=0,
            pos_excluded_row_count=1000,
            skipped_duplicate_prediction_count=500,
            skipped_due_to_registry_duplicate_count=500,
            skipped_due_to_review_count=1000,
            skipped_due_to_schema_count=0,
            skipped_due_to_mapping_count=0,
            skipped_due_to_null_sku_count=0,
            candidate_row_count=1500,
            pos_candidate_row_count=1000,
            prior_publication_detected_flag=True,
            noop_already_published_flag=False,
            publish_status="NOOP_VALID_NO_PUBLISHABLE_ROWS",
            publish_status_reason="all_cycles_valid_no_publishable_rows",
        )

        self.assertEqual(_derive_stage12_legitimate_excluded_row_count(artifacts), 0)

    def test_omitted_connect_retry_args_resolve_to_governed_defaults(self) -> None:
        previous_values = {key: os.environ.get(key) for key in SQL_RETRY_ENV_KEYS}
        for key in SQL_RETRY_ENV_KEYS:
            os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".promotions.env"
                env_path.write_text(
                    "\n".join(
                        (
                            "PROMOTIONS_MSSQL_SERVER=test-server",
                            "PROMOTIONS_MSSQL_DATABASE=test-database",
                            "PROMOTIONS_ADVICE_TABLE=PromotionAdvice",
                        )
                    ),
                    encoding="utf-8",
                )
                args = _build_parser().parse_args(
                    [
                        "--env-file",
                        str(env_path),
                        "--artifact-root",
                        str(Path(temp_dir) / "artifacts"),
                        "--disable-local-inspection-copy",
                        "--run-id",
                        "retry-default-regression",
                        "--as-of-date",
                        "2026-05-14",
                    ]
                )
                settings = _build_settings(args)
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(settings.sql.connect_retry_attempts, 2)
        self.assertEqual(settings.sql.connect_retry_backoff_seconds, 5.0)
        summary = settings.sql.safe_summary()
        self.assertEqual(summary.connect_retry_attempts_source, "default")
        self.assertEqual(summary.connect_retry_backoff_seconds_source, "default")

    def test_explicit_zero_connect_retry_args_remain_visible_operator_override(self) -> None:
        previous_values = {key: os.environ.get(key) for key in SQL_RETRY_ENV_KEYS}
        for key in SQL_RETRY_ENV_KEYS:
            os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".promotions.env"
                env_path.write_text(
                    "\n".join(
                        (
                            "PROMOTIONS_MSSQL_SERVER=test-server",
                            "PROMOTIONS_MSSQL_DATABASE=test-database",
                            "PROMOTIONS_ADVICE_TABLE=PromotionAdvice",
                        )
                    ),
                    encoding="utf-8",
                )
                args = _build_parser().parse_args(
                    [
                        "--env-file",
                        str(env_path),
                        "--artifact-root",
                        str(Path(temp_dir) / "artifacts"),
                        "--disable-local-inspection-copy",
                        "--run-id",
                        "retry-zero-regression",
                        "--as-of-date",
                        "2026-05-14",
                        "--connect-retry-attempts",
                        "0",
                        "--connect-retry-backoff-seconds",
                        "0.0",
                    ]
                )
                settings = _build_settings(args)
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(settings.sql.connect_retry_attempts, 0)
        self.assertEqual(settings.sql.connect_retry_backoff_seconds, 0.0)
        summary = settings.sql.safe_summary()
        self.assertEqual(summary.connect_retry_attempts_source, "cli:--connect-retry-attempts")
        self.assertEqual(
            summary.connect_retry_backoff_seconds_source,
            "cli:--connect-retry-backoff-seconds",
        )


def _persist_extraction(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    selection_mode: str,
    frame,
    as_of_date: str,
    partition_settings: PromotionCompletedPartitionSettings | None = None,
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
        extraction_mode="live_sql",
        candidate_promotion_row_count=int(len(frame.index)),
        partition_strategy=(partition_settings.strategy if partition_settings is not None else None),
        partition_count=(partition_settings.partition_count if partition_settings is not None else None),
        partition_index=(partition_settings.partition_index if partition_settings is not None else None),
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
    rendered_sql_parameters_path.write_text(
        json.dumps(
            {
                "as_of_date": "2024-09-01",
                "partition_strategy": (
                    partition_settings.strategy if partition_settings is not None else None
                ),
                "partition_count": (
                    partition_settings.partition_count if partition_settings is not None else None
                ),
                "partition_index": (
                    partition_settings.partition_index if partition_settings is not None else None
                ),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    telemetry_json_path.write_text(
        json.dumps(
            {
                "extraction_status": "succeeded",
                "candidate_promotion_row_count": int(len(frame.index)),
                "row_count": int(len(frame.index)),
                "partition_strategy": (
                    partition_settings.strategy if partition_settings is not None else None
                ),
                "partition_count": (
                    partition_settings.partition_count if partition_settings is not None else None
                ),
                "partition_index": (
                    partition_settings.partition_index if partition_settings is not None else None
                ),
                "phase_elapsed_seconds": {
                    "query_render": 0.0,
                    "sql_connection": 0.1,
                    "query_execution": 0.2,
                    "fetch": 0.3,
                    "dataframe_write": 0.1,
                },
                "total_elapsed_seconds": 0.7,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
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
        extraction_mode="live_sql",
        partition_strategy=(partition_settings.strategy if partition_settings is not None else None),
        partition_count=(partition_settings.partition_count if partition_settings is not None else None),
        partition_index=(partition_settings.partition_index if partition_settings is not None else None),
    )


def _build_preflight_result(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    as_of_date: str,
    partition_settings: PromotionCompletedPartitionSettings | None = None,
    verdict: str = "SAFE_TO_EXTRACT",
    reason: str = "within completed extraction thresholds",
    candidate_promotion_row_count: int = 8,
    candidate_store_sku_count: int = 6,
    candidate_window_count: int = 6,
    candidate_window_span_days_total: int = 42,
    candidate_window_span_days_max: int = 7,
    estimated_cost_score: float | None = None,
    cost_guardrail_verdict: str | None = None,
    cost_guardrail_reason: str | None = None,
    recommended_partition_strategy: str | None = None,
    recommended_partition_count: int | None = None,
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
        partition_strategy=(partition_settings.strategy if partition_settings is not None else None),
        partition_count=(partition_settings.partition_count if partition_settings is not None else None),
        partition_index=(partition_settings.partition_index if partition_settings is not None else None),
        candidate_promotion_row_count=candidate_promotion_row_count,
        candidate_store_sku_count=candidate_store_sku_count,
        candidate_window_count=candidate_window_count,
        candidate_window_span_days_total=candidate_window_span_days_total,
        candidate_window_span_days_max=candidate_window_span_days_max,
        estimated_cost_score=estimated_cost_score,
        cost_guardrail_verdict=cost_guardrail_verdict,
        cost_guardrail_reason=cost_guardrail_reason,
        recommended_partition_strategy=recommended_partition_strategy,
        recommended_partition_count=recommended_partition_count,
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


def _frame_for_partition(
    frame: pd.DataFrame,
    partition_settings: PromotionCompletedPartitionSettings | None,
) -> pd.DataFrame:
    normalized_frame = frame.reset_index(drop=True)
    if partition_settings is None or partition_settings.partition_index is None:
        return normalized_frame
    partition_offset = partition_settings.partition_index - 1
    mask = normalized_frame.index.to_series().mod(partition_settings.partition_count) == partition_offset
    return normalized_frame.loc[mask].reset_index(drop=True)


def _write_partition_completion_marker(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    row_count: int,
    chunk_count: int = 1,
    resume_state: str = "new_partition",
) -> None:
    completion_marker_path = artifact_paths.extraction_partition_completion_path(run_id)
    completion_marker_path.parent.mkdir(parents=True, exist_ok=True)
    completion_marker_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "fetch_mode": "chunked_fetch",
                "chunk_row_count": 5000,
                "chunk_count": chunk_count,
                "completed_chunk_count": chunk_count,
                "cumulative_rows_written": row_count,
                "partition_completion_state": "finalized",
                "resume_state": resume_state,
                "skipped_due_to_existing_completion": False,
                "base_path": str(artifact_paths.extracted_base_path(run_id)),
                "manifest_path": str(artifact_paths.extracted_manifest_path(run_id)),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_partition_progress_state(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    partition_completion_state: str,
    resume_state: str,
) -> None:
    progress_path = artifact_paths.extraction_partition_progress_path(run_id)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "fetch_mode": "chunked_fetch",
                "chunk_row_count": 5000,
                "chunk_count": 1,
                "completed_chunk_count": 0,
                "cumulative_rows_written": 0,
                "partition_completion_state": partition_completion_state,
                "resume_state": resume_state,
                "skipped_due_to_existing_completion": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _promotion_row_key_checksum(frame: pd.DataFrame) -> str | None:
    if "promotion_row_key" not in frame.columns:
        return None
    digest = __import__("hashlib").sha256()
    for row_key in frame["promotion_row_key"].tolist():
        digest.update(str(row_key).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _build_publish_without_zero_fail(
    *,
    artifact_paths: PromotionArtifactPaths,
    original_publish,
):
    def _publish_without_zero_fail(self, **kwargs):
        try:
            result = original_publish(
                self,
                exclusion_threshold_policy=PromotionPosExclusionThresholdPolicy(
                    fail_if_zero_published=False,
                ),
                **kwargs,
            )
            if int(result.pos_upload_row_count) == 0:
                return replace(
                    result,
                    publish_status="NOOP_ALREADY_PUBLISHED",
                    publish_status_reason="test_harness_zero_upload_rows",
                    noop_already_published_flag=True,
                )
            return result
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


def _remove_run_outputs(artifact_paths: PromotionArtifactPaths, run_id: str) -> None:
    for path in (
        artifact_paths.extracted_run_root(run_id),
        artifact_paths.manifests_run_root(run_id),
        artifact_paths.logs_run_root(run_id),
    ):
        if path.exists():
            shutil.rmtree(path)


class _StaticCandidateCountExecutor:
    def __init__(self, candidate_count: int) -> None:
        self.candidate_count = candidate_count
        self.calls = 0

    def fetch_dataframe(self, *, sql, parameters):
        self.calls += 1
        return SimpleNamespace(
            frame=pd.DataFrame(
                {"candidate_promotion_row_count": [self.candidate_count]}
            )
        )


class _FailingCandidateCountExecutor:
    def fetch_dataframe(self, *, sql, parameters):
        raise AssertionError("candidate count probe should not run when finalized landed batches are reused")


class _FakeCompletedBaseStageExtractor:
    def __init__(self, frames_by_batch: dict[int, pd.DataFrame]) -> None:
        self._frames_by_batch = {
            batch_index: frame.reset_index(drop=True).copy()
            for batch_index, frame in frames_by_batch.items()
        }
        self.calls: list[int] = []

    def extract_stage(
        self,
        *,
        run_id,
        settings,
        query_options,
        phase_callback=None,
    ):
        batch_slice = query_options.completed_batch
        self.calls.append(batch_slice.batch_index)
        frame = self._frames_by_batch[batch_slice.batch_index].copy()
        if phase_callback is not None:
            phase_callback("completed_base | executing landed batch")
        return _fake_stage_artifact(
            run_id=run_id,
            stage_name="completed_base",
            frame=frame,
            settings=settings,
        )


class _FakeCompletedWindowAggregatesExtractor:
    def extract_stage(
        self,
        *,
        run_id,
        settings,
        base_frame,
        phase_callback=None,
    ):
        if phase_callback is not None:
            phase_callback("completed_window_aggregates | executing landed batch")
        return _fake_stage_artifact(
            run_id=run_id,
            stage_name="completed_window_aggregates",
            frame=base_frame.loc[:, ["promotion_row_key"]].copy(),
            settings=settings,
        )


class _FailingCompletedWindowAggregatesExtractor:
    def extract_stage(
        self,
        *,
        run_id,
        settings,
        base_frame,
        phase_callback=None,
    ):
        del run_id, settings, base_frame, phase_callback
        raise RuntimeError("window aggregate stage failure")


class _FakeCompletedTransactionAggregatesExtractor:
    def extract_stage(
        self,
        *,
        run_id,
        settings,
        base_frame,
        phase_callback=None,
    ):
        if phase_callback is not None:
            phase_callback("completed_transaction_aggregates | executing landed batch")
        return _fake_stage_artifact(
            run_id=run_id,
            stage_name="completed_transaction_aggregates",
            frame=base_frame.loc[:, ["promotion_row_key"]].copy(),
            settings=settings,
        )


class _PassthroughCompletedDatasetJoiner:
    def join(
        self,
        *,
        run_id,
        as_of_date,
        query_version,
        advice_source_table_name,
        realised_sales_source_table_name,
        base_frame,
        window_aggregate_frame,
        transaction_aggregate_frame,
        extracted_at_utc=None,
    ):
        return base_frame.reset_index(drop=True).copy()


class _FailingCompletedBaseStageExtractor:
    def extract_stage(self, **kwargs):
        raise AssertionError("landed batch extraction should not rerun for a finalized reusable partition")


def _fake_stage_artifact(
    *,
    run_id: str,
    stage_name: str,
    frame: pd.DataFrame,
    settings: PromotionPipelineSettings,
):
    checksum = _promotion_row_key_checksum(frame)
    manifests_run_root = settings.artifacts.manifests_run_root(run_id)
    return SimpleNamespace(
        run_id=run_id,
        stage_name=stage_name,
        frame=frame.reset_index(drop=True).copy(),
        base_path=str(settings.artifacts.extracted_base_path(run_id)),
        manifest_path=str(settings.artifacts.extracted_manifest_path(run_id)),
        progress_path=str(settings.artifacts.extraction_partition_progress_path(run_id)),
        completion_marker_path=str(settings.artifacts.extraction_partition_completion_path(run_id)),
        rendered_sql_path=str(manifests_run_root / "rendered_sql.sql"),
        rendered_sql_parameters_path=str(
            manifests_run_root / "rendered_sql_parameters.json"
        ),
        telemetry_json_path=str(settings.artifacts.extraction_telemetry_json_path(run_id)),
        telemetry_csv_path=str(settings.artifacts.extraction_telemetry_csv_path(run_id)),
        diagnostics_summary_json_path=str(settings.artifacts.sql_diagnostics_summary_json_path(run_id)),
        diagnostics_summary_txt_path=str(settings.artifacts.sql_diagnostics_summary_txt_path(run_id)),
        manifest={
            "run_id": run_id,
            "stage_name": stage_name,
            "row_count": int(len(frame.index)),
        },
        fetch_mode="chunked_fetch",
        chunk_mode="chunked_fetch",
        chunk_count=1,
        completed_chunk_count=1,
        cumulative_rows_written=int(len(frame.index)),
        row_count=int(len(frame.index)),
        promotion_row_key_checksum_sha256=checksum,
    )


class PromotionOperationalCycleTests(unittest.TestCase):
    def test_validate_artifact_roots_rejects_repo_local_runtime_root(self) -> None:
        artifact_paths = PromotionArtifactPaths(root=REPO_ROOT / "artifacts" / "promotions")

        with self.assertRaisesRegex(ValueError, "PROMOTIONS_NAS_ROOT"):
            _validate_artifact_roots(artifact_paths)

    def test_completed_proof_fallback_bypasses_landed_batches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    enable_chunked_fetch=True,
                ),
            )
            base_frame = pd.DataFrame(
                {
                    "promotion_row_key": ["proof-row-1"],
                    "store_number": [772],
                    "sku_number": [1001],
                }
            )
            manifest = PromotionExtractionManifest(
                run_id="proof-fallback-route",
                selection_mode="completed",
                query_version="promotion_base_v4",
                as_of_date=settings.as_of_date.isoformat(),
                extracted_at_utc=datetime.now(tz=UTC).isoformat(),
                row_count=int(len(base_frame.index)),
                column_count=int(len(base_frame.columns)),
                duplicate_promotion_row_keys=0,
                advice_source_table="dbo.PromotionAdvice",
                realised_sales_source_table="dbo.PwlogD",
                columns=tuple(str(column_name) for column_name in base_frame.columns),
                extraction_mode="diagnostic_topn",
                candidate_promotion_row_count=int(len(base_frame.index)),
            )
            telemetry = PromotionExtractionTelemetry(
                run_id="proof-fallback-route",
                selection_mode="completed",
                as_of_date=settings.as_of_date.isoformat(),
                query_version="promotion_base_v4",
                extraction_mode="diagnostic_topn",
                candidate_promotion_row_count=int(len(base_frame.index)),
                row_count=int(len(base_frame.index)),
                column_count=int(len(base_frame.columns)),
                duplicate_promotion_row_keys=0,
                connect_retry_attempts=settings.sql.connect_retry_attempts,
                connect_retry_backoff_seconds=settings.sql.connect_retry_backoff_seconds,
            )
            extraction_result = PromotionBaseExtractionResult(
                base_frame=base_frame,
                manifest=manifest,
                telemetry=telemetry,
            )
            fake_extractor = MagicMock()
            fake_extractor.extract.return_value = extraction_result
            query_options = PromotionBaseQueryOptions(
                extraction_mode="diagnostic_topn",
                limit_promotions=2000,
            )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle.SqlAlchemyMssqlQueryExecutor.from_settings",
                return_value=object(),
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle.execute_completed_partition_landed_batches"
            ) as landed_batches, patch(
                "runtime.promotions.run_promotions_operational_cycle.PromotionBaseExtractor",
                return_value=fake_extractor,
            ):
                artifact = _extract_promotions_base_artifact(
                    settings=settings,
                    run_id="proof-fallback-route",
                    selection_mode="completed",
                    query_options=query_options,
                )

            landed_batches.assert_not_called()
            fake_extractor.extract.assert_called_once()
            self.assertIs(fake_extractor.extract.call_args.kwargs["query_options"], query_options)
            self.assertEqual(artifact.extraction_mode, "diagnostic_topn")
            self.assertEqual(artifact.manifest["extraction_mode"], "diagnostic_topn")

    def test_operational_cycle_live_mode_audit_allows_missing_training_ready_dataset_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                run_id="audit-live-optional-dataset",
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="audit-live-optional-dataset-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            from runtime.promotions.audit_promotions_operational_cycle import (
                audit_operational_cycle as _real_audit_operational_cycle,
            )
            original_publish = StorePredictionPublisher.publish

            def _publish_without_zero_fail(self, **kwargs):
                try:
                    result = original_publish(
                        self,
                        exclusion_threshold_policy=PromotionPosExclusionThresholdPolicy(
                            fail_if_zero_published=False,
                        ),
                        **kwargs,
                    )
                    if int(result.pos_upload_row_count) == 0:
                        return replace(
                            result,
                            publish_status="NOOP_ALREADY_PUBLISHED",
                            publish_status_reason="test_harness_zero_upload_rows",
                            noop_already_published_flag=True,
                        )
                    return result
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

            def _audit_after_removing_training_dataset(**kwargs):
                manifest_path = Path(str(kwargs["operational_cycle_manifest_path"]))
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                dataset_path = Path(str(payload["training_dataset"]["dataset_path"]))
                if dataset_path.exists():
                    dataset_path.unlink()
                return _real_audit_operational_cycle(**kwargs)

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="audit-live-optional-dataset",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle._extract_promotions_base_artifact",
                side_effect=[completed_extraction, future_extraction],
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle.audit_operational_cycle",
                side_effect=_audit_after_removing_training_dataset,
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publish_without_zero_fail,
            ):
                artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="audit-live-optional-dataset",
                    score_run_id="audit-live-optional-dataset-score",
                    decision_surface_run_id="audit-live-optional-dataset-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    execution_mode="live_sql",
                )

            audit_summary = json.loads(Path(artifacts.audit_summary_json_path).read_text(encoding="utf-8"))
            artifact_contract = {
                item["artifact_name"]: item for item in audit_summary["audit_artifact_contract"]
            }
            training_ready_contract = artifact_contract["training_ready.parquet"]
            self.assertEqual(training_ready_contract["artifact_required_flag"], False)
            self.assertEqual(training_ready_contract["artifact_exists_flag"], False)
            self.assertEqual(training_ready_contract["artifact_status"], "unavailable_for_run_mode")
            self.assertEqual(training_ready_contract["artifact_status_reason"], "not_produced_in_live_mode")

    def test_operational_cycle_writes_top_level_manifest_and_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                run_id="operational-run",
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="operational-run-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )

            original_publish = StorePredictionPublisher.publish

            def _publish_without_zero_fail(self, **kwargs):
                try:
                    result = original_publish(
                        self,
                        exclusion_threshold_policy=PromotionPosExclusionThresholdPolicy(
                            fail_if_zero_published=False,
                        ),
                        **kwargs,
                    )
                    if int(result.pos_upload_row_count) == 0:
                        return replace(
                            result,
                            publish_status="NOOP_ALREADY_PUBLISHED",
                            publish_status_reason="test_harness_zero_upload_rows",
                            noop_already_published_flag=True,
                        )
                    return result
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

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="operational-run",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle._extract_promotions_base_artifact",
                side_effect=[completed_extraction, future_extraction],
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_publish_without_zero_fail,
            ):
                artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="operational-run",
                    score_run_id="operational-run-score",
                    decision_surface_run_id="operational-run-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.0,
                    row_model_confidence_floor=0.0,
                )

            self.assertTrue(Path(artifacts.manifest_path).exists())
            self.assertTrue(Path(artifacts.nas_bootstrap_summary_path).exists())
            self.assertTrue(Path(artifacts.scoring_manifest_path).exists())
            self.assertTrue(Path(artifacts.score_report_manifest_path).exists())
            self.assertTrue(Path(artifacts.decision_surface_manifest_path).exists())
            self.assertTrue(Path(artifacts.decision_surface_execution_summary_path).exists())
            self.assertTrue(Path(artifacts.decision_surface_inspection_manifest_path).exists())
            self.assertTrue(Path(artifacts.inspection_review_packet_csv_path).exists())
            self.assertTrue(Path(artifacts.store_prediction_download_path).exists())
            self.assertTrue(Path(artifacts.store_prediction_manifest_path).exists())
            self.assertTrue(Path(artifacts.local_store_prediction_download_path).exists())
            self.assertTrue(Path(artifacts.local_decision_surface_csv_path).exists())
            self.assertTrue(Path(artifacts.local_review_packet_csv_path).exists())
            self.assertTrue(Path(artifacts.local_run_summary_path).exists())
            self.assertTrue(Path(artifacts.audit_manifest_path).exists())
            self.assertTrue(Path(artifacts.audit_summary_json_path).exists())
            self.assertTrue(Path(artifacts.audit_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.operator_log_path).exists())
            self.assertTrue(Path(artifacts.operator_summary_path).exists())
            self.assertTrue(Path(artifacts.operator_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.operator_stage_timings_path).exists())
            self.assertTrue(Path(artifacts.pilot_validation_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.pilot_validation_summary_json_path).exists())
            self.assertTrue(Path(artifacts.pilot_validation_failures_csv_path).exists())
            self.assertTrue(Path(artifacts.gold_standard_acceptance_results_csv_path).exists())
            self.assertTrue(Path(artifacts.gold_standard_acceptance_results_json_path).exists())
            self.assertTrue(Path(artifacts.validation_manifest_path).exists())

            manifest = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            decision_surface_execution_summary = json.loads(
                Path(artifacts.decision_surface_execution_summary_path).read_text(encoding="utf-8")
            )
            decision_surface_inspection_manifest = json.loads(
                Path(artifacts.decision_surface_inspection_manifest_path).read_text(encoding="utf-8")
            )
            audit_summary = json.loads(Path(artifacts.audit_summary_json_path).read_text(encoding="utf-8"))
            nas_bootstrap_summary = json.loads(
                Path(artifacts.nas_bootstrap_summary_path).read_text(encoding="utf-8")
            )
            local_run_summary = json.loads(Path(artifacts.local_run_summary_path).read_text(encoding="utf-8"))
            commercial_outcome_summary = json.loads(
                Path(artifacts.commercial_run_outcome_summary_path).read_text(encoding="utf-8")
            )
            operator_summary = json.loads(Path(artifacts.operator_summary_path).read_text(encoding="utf-8"))
            operator_log = Path(artifacts.operator_log_path).read_text(encoding="utf-8")
            store_download = pd.read_csv(artifacts.store_prediction_download_path)
            store_prediction_manifest_csv = pd.read_csv(artifacts.store_prediction_manifest_csv_path)
            inspection_review_packet = pd.read_csv(artifacts.inspection_review_packet_csv_path)

            self.assertEqual(manifest["run_id"], "operational-run")
            self.assertEqual(manifest["score_run_id"], "operational-run-score")
            self.assertEqual(
                manifest["decision_surface_run_id"],
                "operational-run-decision-surface",
            )
            self.assertEqual(manifest["execution_mode"], "live_sql")
            self.assertEqual(manifest["nas_root"], str(artifact_paths.root))
            self.assertEqual(manifest["local_inspection_root"], str(artifact_paths.local_inspection_root))
            self.assertEqual(manifest["completed_extraction"]["selection_mode"], "completed")
            self.assertEqual(manifest["future_extraction"]["selection_mode"], "future")
            self.assertEqual(
                manifest["runtime_settings"]["completed_preflight_planner"]["max_candidate_store_sku"],
                1000,
            )
            self.assertEqual(
                manifest["completed_extraction"]["rendered_sql_path"],
                completed_extraction.rendered_sql_path,
            )
            self.assertEqual(
                manifest["completed_extraction"]["preflight_verdict"],
                "SAFE_TO_EXTRACT",
            )
            self.assertTrue(
                manifest["completed_extraction"]["preflight_summary_json_path"].endswith(
                    "extraction_preflight_summary.json"
                )
            )
            self.assertEqual(
                manifest["completed_extraction"]["telemetry_json_path"],
                completed_extraction.telemetry_json_path,
            )
            self.assertEqual(
                manifest["future_extraction"]["sql_diagnostics_summary_json_path"],
                future_extraction.diagnostics_summary_json_path,
            )
            self.assertEqual(
                manifest["future_extraction"]["candidate_promotion_row_count"],
                future_extraction.candidate_promotion_row_count,
            )
            self.assertEqual(
                manifest["nas_bootstrap"]["summary_path"],
                artifacts.nas_bootstrap_summary_path,
            )
            self.assertEqual(
                decision_surface_execution_summary["inspection_manifest_path"],
                artifacts.decision_surface_inspection_manifest_path,
            )
            self.assertIn("audit", manifest)
            self.assertEqual(manifest["audit"]["summary_json_path"], artifacts.audit_summary_json_path)
            self.assertEqual(manifest["audit"]["manifest_path"], artifacts.audit_manifest_path)
            self.assertEqual(
                manifest["store_outputs"]["user_facing_prediction_csv_path"],
                artifacts.store_prediction_download_path,
            )
            self.assertIn(
                artifacts.store_prediction_download_path,
                manifest["store_outputs"]["user_facing_prediction_csv_paths"],
            )
            self.assertEqual(
                manifest["store_outputs"]["internal_master_csv_path"],
                artifacts.store_prediction_master_csv_path,
            )
            self.assertEqual(
                manifest["store_outputs"]["reconciliation_csv_path"],
                artifacts.store_prediction_reconciliation_csv_path,
            )
            self.assertEqual(
                manifest["store_outputs"]["local_store_prediction_csv_path"],
                artifacts.local_store_prediction_download_path,
            )
            self.assertEqual(
                manifest["operator_progress"]["summary_path"],
                artifacts.operator_summary_path,
            )
            self.assertEqual(
                manifest["operator_progress"]["summary_csv_path"],
                artifacts.operator_summary_csv_path,
            )
            self.assertEqual(
                manifest["final_outputs"]["inspection_review_packet_csv_path"],
                artifacts.inspection_review_packet_csv_path,
            )
            self.assertNotIn("store_prediction_reconciliation_csv_path", manifest["final_outputs"])
            self.assertEqual(
                manifest["final_outputs"]["commercial_publication_summary_path"],
                artifacts.commercial_publication_summary_path,
            )
            self.assertIn("commercial_publish_status", manifest["final_outputs"])
            self.assertIn("commercial_publish_status_reason", manifest["final_outputs"])
            self.assertIn("commercial_pos_excluded_row_count", manifest["final_outputs"])
            self.assertIn("commercial_prior_publication_detected_flag", manifest["final_outputs"])
            self.assertIn("commercial_duplicate_registry_skip_count", manifest["final_outputs"])
            self.assertIn("commercial_noop_already_published_flag", manifest["final_outputs"])
            self.assertIn("validation_status", manifest["final_outputs"])
            self.assertIn("validation_status_reason", manifest["final_outputs"])
            self.assertIn("validation_skipped_flag", manifest["final_outputs"])
            self.assertIn("validation_reference_cycle_path", manifest["final_outputs"])
            self.assertIn("commercial_diagnostics_paths", manifest["final_outputs"])
            self.assertIn("commercial_skipped_paths", manifest["final_outputs"])
            self.assertIn("commercial_outcome_class", manifest["final_outputs"])
            self.assertIn("commercial_outcome_reason", manifest["final_outputs"])
            self.assertIn("commercial_outcome_message", manifest["final_outputs"])
            self.assertIn("commercial_run_outcome_summary_path", manifest["final_outputs"])
            self.assertIn("publication_freshness_diagnostic_path", manifest["final_outputs"])
            self.assertIn("validation_skip_class", manifest["final_outputs"])
            self.assertIn("validation_skip_summary_path", manifest["final_outputs"])
            self.assertEqual(
                manifest["final_outputs"]["store_prediction_download_path"],
                artifacts.store_prediction_download_path,
            )
            self.assertEqual(
                manifest["final_outputs"]["nas_store_prediction_download_path"],
                artifacts.store_prediction_download_path,
            )
            self.assertIn(
                artifacts.store_prediction_download_path,
                json.loads(manifest["final_outputs"]["store_prediction_user_csv_paths"]),
            )
            for path in (
                artifacts.store_prediction_download_path,
                artifacts.local_store_prediction_download_path,
            ):
                self.assertIn("/promotions/priceline/", path)
                self.assertIn("/prediction/", path)
                self.assertNotIn("/System Audit/", path)
                self.assertNotIn("/Store Data/", path)
                self.assertNotIn("/promotion_cycles/", path)
                self.assertNotIn("default_client", path)
            self.assertEqual(
                manifest["final_outputs"]["pilot_validation_summary_csv_path"],
                artifacts.pilot_validation_summary_csv_path,
            )
            self.assertEqual(
                manifest["final_outputs"]["validation_manifest_path"],
                artifacts.validation_manifest_path,
            )
            self.assertEqual(
                manifest["final_outputs"]["validation_skip_summary_path"],
                artifacts.validation_skip_summary_path,
            )
            self.assertEqual(
                manifest["final_outputs"]["decision_surface_csv_path"],
                manifest["decision_surface"]["report_paths"]["promotion_decision_surface"]["csv"],
            )
            self.assertEqual(
                manifest["final_outputs"]["completed_rendered_sql_path"],
                completed_extraction.rendered_sql_path,
            )
            self.assertEqual(
                manifest["final_outputs"]["completed_extraction_telemetry_json_path"],
                completed_extraction.telemetry_json_path,
            )
            self.assertEqual(
                manifest["final_outputs"]["future_extraction_telemetry_json_path"],
                future_extraction.telemetry_json_path,
            )
            self.assertTrue(
                manifest["final_outputs"]["completed_preflight_summary_path"].endswith(
                    "extraction_preflight_summary.json"
                )
            )
            self.assertEqual(
                manifest["final_outputs"]["completed_sql_diagnostics_summary_path"],
                completed_extraction.diagnostics_summary_json_path,
            )
            self.assertEqual(
                manifest["final_outputs"]["local_inspection_csv_path"],
                artifacts.local_store_prediction_download_path,
            )
            self.assertEqual(
                manifest["local_inspection"]["store_prediction_csv_path"],
                artifacts.local_store_prediction_download_path,
            )
            self.assertEqual(
                manifest["local_inspection"]["operator_summary_csv_path"],
                artifacts.local_inspection_root and local_run_summary["local_operator_summary_csv_path"],
            )
            self.assertIn(
                "inspection_promotion_review_packet",
                decision_surface_inspection_manifest["report_paths"],
            )
            self.assertGreater(audit_summary["rows_scored"], 0)
            self.assertFalse(store_download.empty)
            self.assertEqual(len(store_download.columns), len(set(store_download.columns)))
            # Stage 11/12 store-facing CSV redesign: action-critical columns must lead.
            self.assertIn("recommended_order_units", store_download.columns)
            self.assertIn("projected_promotional_units", store_download.columns)
            self.assertIn("lead_up_demand_units", store_download.columns)
            self.assertIn("model_reason_summary", store_download.columns)
            self.assertIn("capital_at_risk_adjusted_dollars", store_download.columns)
            self.assertIn("retail_risk_reward_ratio", store_download.columns)
            self.assertIn("model_confidence_percent", store_download.columns)
            self.assertIn("discount_percent", store_download.columns)
            self.assertIn("predicted_units_first_day", inspection_review_packet.columns)
            self.assertTrue(pd.api.types.is_numeric_dtype(inspection_review_packet["predicted_units_first_day"]))
            self.assertIn("master", set(store_prediction_manifest_csv["file_type"]))
            self.assertIn(
                "store_promotion_manager_summary",
                set(store_prediction_manifest_csv["file_type"]),
            )
            self.assertIn(
                "store_promotion_feature_inspection",
                set(store_prediction_manifest_csv["file_type"]),
            )
            self.assertIn("reports", {directory["name"] for directory in nas_bootstrap_summary["directories"]})
            self.assertIn("FINAL OUTPUTS", operator_log)
            self.assertIn("local_inspection_csv_path", operator_log)
            self.assertIn("completed_rendered_sql_path", operator_log)
            self.assertIn("completed_sql_diagnostics_summary_path", operator_log)
            self.assertEqual(local_run_summary["local_store_prediction_csv_path"], artifacts.local_store_prediction_download_path)
            self.assertEqual(local_run_summary["audit_summary_csv_path"], artifacts.audit_summary_csv_path)
            self.assertEqual(local_run_summary["operator_summary_csv_path"], artifacts.operator_summary_csv_path)
            self.assertTrue(Path(artifacts.store_prediction_reconciliation_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_publication_summary_path).exists())
            self.assertTrue(Path(artifacts.commercial_run_outcome_summary_path).exists())
            self.assertTrue(Path(artifacts.publication_freshness_diagnostic_path).exists())
            self.assertTrue(Path(artifacts.commercial_delta_summary_path).exists())
            self.assertTrue(Path(artifacts.commercial_delta_top_changes_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_delta_store_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_change_explanations_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_priority_queue_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_action_summary_path).exists())
            self.assertTrue(Path(artifacts.commercial_outcome_attribution_csv_path).exists())
            self.assertTrue(Path(artifacts.recommendation_effectiveness_summary_path).exists())
            self.assertTrue(Path(artifacts.recommendation_effectiveness_by_reason_csv_path).exists())
            self.assertTrue(Path(artifacts.recommendation_learning_priority_queue_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_policy_calibration_summary_path).exists())
            self.assertTrue(Path(artifacts.commercial_policy_calibration_by_segment_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_policy_watchlist_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_policy_calibration_brief_path).exists())
            self.assertTrue(Path(artifacts.commercial_policy_simulation_summary_path).exists())
            self.assertTrue(Path(artifacts.commercial_policy_simulation_by_segment_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_policy_simulation_watchlist_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_policy_simulation_brief_path).exists())
            self.assertTrue(Path(artifacts.commercial_action_instruction_summary_path).exists())
            self.assertTrue(Path(artifacts.commercial_action_priority_queue_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_action_by_segment_csv_path).exists())
            self.assertTrue(Path(artifacts.commercial_action_instruction_brief_path).exists())
            self.assertEqual(
                commercial_outcome_summary["commercial_outcome_class"],
                operator_summary["final_outputs"]["commercial_outcome_class"],
            )
            self.assertEqual(
                commercial_outcome_summary["publication_summary_csv_path"],
                artifacts.commercial_publication_summary_path,
            )
            self.assertIn("pilot_validation", manifest["commercial_execution_outputs"])
            self.assertIn("publish_status", manifest["commercial_execution_outputs"])
            self.assertIn("publish_status_reason", manifest["commercial_execution_outputs"])
            self.assertIn("prior_publication_detected_flag", manifest["commercial_execution_outputs"])
            self.assertIn("noop_already_published_flag", manifest["commercial_execution_outputs"])
            self.assertIn("skipped_due_to_registry_duplicate_count", manifest["commercial_execution_outputs"])
            self.assertIn("pos_excluded_row_count", manifest["commercial_execution_outputs"])
            self.assertIn("diagnostics_paths", manifest["commercial_execution_outputs"])
            self.assertIn("skipped_paths", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_outcome", manifest["commercial_execution_outputs"])
            self.assertIn("publication_freshness_diagnostic", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_run_outcome_summary_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_delta_summary_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_delta_top_changes_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_delta_store_summary_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_change_explanations_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_priority_queue_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_action_summary_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_outcome_attribution_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("recommendation_effectiveness_summary_path", manifest["commercial_execution_outputs"])
            self.assertIn("recommendation_effectiveness_by_reason_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("recommendation_learning_priority_queue_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_policy_calibration_summary_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_policy_calibration_by_segment_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_policy_watchlist_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_policy_calibration_brief_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_policy_simulation_summary_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_policy_simulation_by_segment_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_policy_simulation_watchlist_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_policy_simulation_brief_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_action_instruction_summary_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_action_priority_queue_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_action_by_segment_csv_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_action_instruction_brief_path", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_action_instruction_readiness_class", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_top_model_owner_action_class", manifest["commercial_execution_outputs"])
            self.assertIn("commercial_delta_class", manifest["final_outputs"])
            self.assertIn("commercial_delta_reason", manifest["final_outputs"])
            self.assertIn("commercial_materiality_class", manifest["final_outputs"])
            self.assertIn("commercial_materiality_reason", manifest["final_outputs"])
            self.assertIn("commercial_materially_changed_flag", manifest["final_outputs"])
            self.assertIn("commercial_operator_attention_recommended_flag", manifest["final_outputs"])
            self.assertIn("comparable_prior_cycle_found_flag", manifest["final_outputs"])
            self.assertIn("comparable_prior_cycle_run_id", manifest["final_outputs"])
            self.assertIn("commercial_delta_summary_path", manifest["final_outputs"])
            self.assertIn("commercial_delta_top_changes_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_delta_store_summary_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_action_summary_path", manifest["final_outputs"])
            self.assertIn("commercial_change_explanations_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_priority_queue_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_top_operator_action_class", manifest["final_outputs"])
            self.assertIn("commercial_top_operator_priority_band", manifest["final_outputs"])
            self.assertIn("commercial_review_now_count", manifest["final_outputs"])
            self.assertIn("commercial_publish_now_count", manifest["final_outputs"])
            self.assertIn("commercial_defect_action_count", manifest["final_outputs"])
            self.assertIn("commercial_outcome_attribution_csv_path", manifest["final_outputs"])
            self.assertIn("recommendation_effectiveness_summary_path", manifest["final_outputs"])
            self.assertIn("recommendation_effectiveness_by_reason_csv_path", manifest["final_outputs"])
            self.assertIn("recommendation_learning_priority_queue_csv_path", manifest["final_outputs"])
            self.assertIn("attribution_ready_count", manifest["final_outputs"])
            self.assertIn("attribution_effective_count", manifest["final_outputs"])
            self.assertIn("attribution_harmful_count", manifest["final_outputs"])
            self.assertIn("attribution_inconclusive_count", manifest["final_outputs"])
            self.assertIn("commercial_learning_signal_strength_class", manifest["final_outputs"])
            self.assertIn("commercial_policy_calibration_summary_path", manifest["final_outputs"])
            self.assertIn("commercial_policy_calibration_by_segment_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_policy_watchlist_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_policy_calibration_brief_path", manifest["final_outputs"])
            self.assertIn("policy_signal_class", manifest["final_outputs"])
            self.assertIn("calibration_readiness_class", manifest["final_outputs"])
            self.assertIn("threshold_direction_class", manifest["final_outputs"])
            self.assertIn("commercial_policy_confidence_class", manifest["final_outputs"])
            self.assertIn("commercial_policy_simulation_summary_path", manifest["final_outputs"])
            self.assertIn("commercial_policy_simulation_by_segment_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_policy_simulation_watchlist_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_policy_simulation_brief_path", manifest["final_outputs"])
            self.assertIn("commercial_action_instruction_summary_path", manifest["final_outputs"])
            self.assertIn("commercial_action_priority_queue_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_action_by_segment_csv_path", manifest["final_outputs"])
            self.assertIn("commercial_action_instruction_brief_path", manifest["final_outputs"])
            self.assertIn("commercial_action_instruction_readiness_class", manifest["final_outputs"])
            self.assertIn("commercial_top_model_owner_action_class", manifest["final_outputs"])
            self.assertIn("simulation_readiness_class", manifest["final_outputs"])
            self.assertIn("simulated_policy_direction_class", manifest["final_outputs"])
            self.assertIn("simulated_materiality_class", manifest["final_outputs"])
            self.assertIn("simulated_risk_class", manifest["final_outputs"])
            self.assertEqual(
                manifest["commercial_execution_outputs"]["pilot_validation"]["validation_manifest_path"],
                artifacts.validation_manifest_path,
            )
            self.assertIn("validation_status", manifest["commercial_execution_outputs"]["pilot_validation"])
            self.assertIn("validation_status_reason", manifest["commercial_execution_outputs"]["pilot_validation"])
            self.assertIn("validation_skipped_flag", manifest["commercial_execution_outputs"]["pilot_validation"])
            self.assertIn("validation_skip_class", manifest["commercial_execution_outputs"]["pilot_validation"])
            self.assertIn("validation_skip_summary_path", manifest["commercial_execution_outputs"]["pilot_validation"])

            brief_path = Path(commercial_outcome_summary["commercial_operator_brief_path"])
            brief_content = brief_path.read_text(encoding="utf-8")
            self.assertIn("## Delta vs Prior Cycle", brief_content)
            self.assertIn("## Materiality", brief_content)
            self.assertIn("## Why Rows Changed", brief_content)
            self.assertIn("## Immediate Operator Actions", brief_content)
            self.assertIn("## Priority Queue", brief_content)
            self.assertIn("## Outcome Attribution", brief_content)
            self.assertIn("## What Worked", brief_content)
            self.assertIn("## What Failed", brief_content)
            self.assertIn("## What to Learn Next", brief_content)
            self.assertIn("## Policy Calibration", brief_content)
            self.assertIn("## What to tighten", brief_content)
            self.assertIn("## What to loosen", brief_content)
            self.assertIn("## What to leave unchanged", brief_content)
            self.assertIn("## Watchlist", brief_content)
            self.assertIn("## Policy Simulation", brief_content)
            self.assertIn("## Baseline vs Simulated Outcome", brief_content)
            self.assertIn("## Biggest Winners", brief_content)
            self.assertIn("## Biggest Risks", brief_content)
            self.assertIn("## Simulation Watchlist", brief_content)
            self.assertIn("## Action Instructions", brief_content)
            self.assertIn("### Immediate Priorities", brief_content)
            self.assertIn("### Top Operator Actions", brief_content)
            self.assertIn("### Top Model Owner Actions", brief_content)
            self.assertIn("### Action Queue Preview", brief_content)

    def test_zero_future_scored_rows_complete_as_governed_noop_before_decision_surface(self) -> None:
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
                run_id="zero-future-noop-run",
                selection_mode="completed",
                frame=build_completed_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            empty_future_frame = build_future_promotions_base_frame().iloc[0:0].copy()
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="zero-future-noop-run-score",
                selection_mode="future",
                frame=empty_future_frame,
                as_of_date=settings.as_of_date.isoformat(),
            )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="zero-future-noop-run",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle._extract_promotions_base_artifact",
                side_effect=[completed_extraction, future_extraction],
            ), patch(
                "runtime.promotions.run_promotions_operational_cycle.run_decision_surface_for_scored_rows",
                side_effect=AssertionError("Stage 8 should be skipped for zero future scored rows"),
            ) as decision_surface_mock:
                artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="zero-future-noop-run",
                    score_run_id="zero-future-noop-run-score",
                    decision_surface_run_id="zero-future-noop-run-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.0,
                    row_model_confidence_floor=0.0,
                )

            decision_surface_mock.assert_not_called()

            manifest = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            scoring_manifest = json.loads(Path(artifacts.scoring_manifest_path).read_text(encoding="utf-8"))
            commercial_outcome_summary = json.loads(
                Path(artifacts.commercial_run_outcome_summary_path).read_text(encoding="utf-8")
            )
            validation_skip_summary = json.loads(
                Path(artifacts.validation_skip_summary_path).read_text(encoding="utf-8")
            )
            publication_freshness = json.loads(
                Path(artifacts.publication_freshness_diagnostic_path).read_text(encoding="utf-8")
            )
            operator_summary = json.loads(Path(artifacts.operator_summary_path).read_text(encoding="utf-8"))

            self.assertEqual(manifest["future_extraction"]["manifest"]["row_count"], 0)
            self.assertEqual(scoring_manifest["row_count"], 0)
            self.assertTrue(Path(scoring_manifest["row_predictions_path"]).exists())
            self.assertEqual(manifest["scoring"]["row_count"], 0)
            self.assertEqual(manifest["decision_surface"]["status"], "skipped")
            self.assertEqual(manifest["decision_surface"]["skip_reason"], "zero_future_scored_rows")
            self.assertEqual(
                manifest["operational_noop"]["noop_outcome_class"],
                "COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS",
            )
            self.assertEqual(
                manifest["operational_noop"]["noop_publish_status"],
                "NOOP_VALID_NO_PUBLISHABLE_ROWS",
            )
            self.assertEqual(
                manifest["commercial_execution_outputs"]["commercial_outcome_class"],
                "COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS",
            )
            self.assertFalse(manifest["commercial_execution_outputs"]["commercial_failure_flag"])
            self.assertEqual(
                manifest["operational_noop"]["skipped_stage_numbers"],
                [8, 9, 10, 11, 12, 13, 14],
            )
            self.assertEqual(
                commercial_outcome_summary["commercial_outcome_class"],
                "COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS",
            )
            self.assertEqual(commercial_outcome_summary["commercial_outcome_reason"], "zero_future_scored_rows")
            self.assertFalse(commercial_outcome_summary["commercial_failure_flag"])
            self.assertEqual(validation_skip_summary["stage13_skip_class"], "STAGE12_NOOP_NO_PUBLISHABLE_ROWS")
            self.assertTrue(validation_skip_summary["validation_skipped_flag"])
            self.assertEqual(validation_skip_summary["stage12_publish_status"], "NOOP_VALID_NO_PUBLISHABLE_ROWS")
            self.assertTrue(publication_freshness["stage8_skipped_flag"])
            self.assertEqual(publication_freshness["noop_reason"], "zero_future_scored_rows")
            self.assertFalse(publication_freshness["ready_for_fresh_publication_test_flag"])
            self.assertEqual(
                operator_summary["final_outputs"]["commercial_outcome_class"],
                "COMMERCIAL_SUCCESS_GOVERNED_NOOP_NO_PUBLISHABLE_ROWS",
            )
            self.assertEqual(operator_summary["final_outputs"]["commercial_failure_flag"], "false")
            self.assertEqual(operator_summary["final_outputs"]["commercial_noop_flag"], "true")
            self.assertEqual(operator_summary["final_outputs"]["stage8_skip_reason"], "zero_future_scored_rows")
            self.assertEqual(
                operator_summary["final_outputs"]["stage12_publish_status"],
                "NOOP_VALID_NO_PUBLISHABLE_ROWS",
            )
            self.assertIn(
                "zero_future_empty_output_pack_summary_path",
                operator_summary["final_outputs"],
            )
            self.assertIn(
                "zero_future_empty_output_pack_note_path",
                operator_summary["final_outputs"],
            )
            empty_output_pack_summary_path = Path(
                operator_summary["final_outputs"]["zero_future_empty_output_pack_summary_path"]
            )
            empty_output_pack_note_path = Path(
                operator_summary["final_outputs"]["zero_future_empty_output_pack_note_path"]
            )
            self.assertTrue(empty_output_pack_summary_path.exists())
            self.assertTrue(empty_output_pack_note_path.exists())
            empty_output_pack_summary = json.loads(
                empty_output_pack_summary_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                empty_output_pack_summary["empty_pack_class"],
                "ZERO_FUTURE_SCORED_ROWS",
            )
            self.assertEqual(
                empty_output_pack_summary["commercial_run_outcome_summary_path"],
                str(Path(artifacts.commercial_run_outcome_summary_path)),
            )
            self.assertEqual(
                empty_output_pack_summary["validation_skip_summary_path"],
                str(Path(artifacts.validation_skip_summary_path)),
            )
            self.assertEqual(
                empty_output_pack_summary["publication_freshness_diagnostic_path"],
                str(Path(artifacts.publication_freshness_diagnostic_path)),
            )
            empty_output_pack_note = empty_output_pack_note_path.read_text(encoding="utf-8")
            self.assertIn("NOOP_VALID_NO_PUBLISHABLE_ROWS", empty_output_pack_note)
            self.assertIn("zero_future_scored_rows", empty_output_pack_note)
            self.assertIn(str(Path(artifacts.commercial_run_outcome_summary_path)), empty_output_pack_note)

    def test_operational_cycle_partitioned_completed_extraction_combines_child_partitions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            completed_partitioning = PromotionCompletedPartitionSettings(
                strategy="store_number",
                partition_count=2,
            )
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
                completed_partitioning=completed_partitioning,
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=False,
                ),
            )
            completed_source_frame = build_completed_promotions_base_frame()
            partition_frames = {
                1: completed_source_frame.iloc[::2].reset_index(drop=True),
                2: completed_source_frame.iloc[1::2].reset_index(drop=True),
            }
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="partitioned-run-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            original_publish = StorePredictionPublisher.publish

            def _partitioned_extract(
                *,
                settings,
                run_id,
                selection_mode,
                progress_callback=None,
                query_options=None,
            ):
                if selection_mode == "future":
                    return future_extraction
                self.assertIsNotNone(query_options)
                self.assertIsNotNone(query_options.completed_partition)
                current_partition = query_options.completed_partition
                return _persist_extraction(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    selection_mode=selection_mode,
                    frame=partition_frames[current_partition.partition_index].copy(),
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=current_partition,
                )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                side_effect=lambda *, settings, run_id, query_options: _build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=query_options.completed_partition,
                ),
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_build_publish_without_zero_fail(
                    artifact_paths=artifact_paths,
                    original_publish=original_publish,
                ),
            ):
                artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="partitioned-run",
                    score_run_id="partitioned-run-score",
                    decision_surface_run_id="partitioned-run-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    extraction_provider=_partitioned_extract,
                )

            combined_frame = pd.read_parquet(artifacts.completed_base_path)
            combined_manifest = json.loads(
                Path(artifacts.completed_base_manifest_path).read_text(encoding="utf-8")
            )
            partition_summary = json.loads(
                Path(artifacts.completed_partition_summary_path).read_text(encoding="utf-8")
            )
            operational_manifest = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            operator_log = Path(artifacts.operator_log_path).read_text(encoding="utf-8")

            self.assertEqual(partition_summary["partition_strategy"], "store_number")
            self.assertEqual(partition_summary["partition_count"], 2)
            self.assertEqual(partition_summary["partitions_succeeded"], 2)
            self.assertEqual(partition_summary["partitions_failed"], 0)
            self.assertEqual(
                partition_summary["total_candidate_promotion_row_count"],
                len(completed_source_frame.index),
            )
            self.assertEqual(
                partition_summary["total_extracted_row_count"],
                len(completed_source_frame.index),
            )
            self.assertEqual(len(partition_summary["partitions"]), 2)
            self.assertEqual(
                partition_summary["partitions"][0]["preflight_verdict"],
                "SAFE_TO_EXTRACT",
            )
            self.assertTrue(
                partition_summary["partitions"][0]["preflight_summary_json_path"].endswith(
                    "extraction_preflight_summary.json"
                )
            )
            self.assertEqual(combined_manifest["partition_strategy"], "store_number")
            self.assertEqual(combined_manifest["partition_count"], 2)
            self.assertEqual(len(combined_manifest["child_partition_manifest_paths"]), 2)
            self.assertListEqual(list(combined_frame.columns), list(completed_source_frame.columns))
            self.assertEqual(set(combined_frame["promotion_row_key"]), set(completed_source_frame["promotion_row_key"]))
            self.assertEqual(
                operational_manifest["completed_extraction"]["partition_summary_path"],
                artifacts.completed_partition_summary_path,
            )
            self.assertEqual(
                operational_manifest["final_outputs"]["completed_partition_summary_path"],
                artifacts.completed_partition_summary_path,
            )
            self.assertIn("total_completed_candidate_rows", operator_log)
            self.assertIn("partitions_succeeded", operator_log)
            self.assertIn("completed_partition_summary_path", operator_log)

    def test_operational_cycle_skips_finalized_completed_partition_when_resume_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            completed_partitioning = PromotionCompletedPartitionSettings(
                strategy="store_number",
                partition_count=2,
            )
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
                completed_partitioning=completed_partitioning,
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=False,
                ),
            )
            completed_source_frame = build_completed_promotions_base_frame()
            partition_frames = {
                1: completed_source_frame.iloc[::2].reset_index(drop=True),
                2: completed_source_frame.iloc[1::2].reset_index(drop=True),
            }
            partition_one_settings = completed_partitioning.with_partition_index(1)
            partition_one_run_id = _completed_partition_run_id(
                "partition-resume-skip",
                partition_one_settings,
            )
            _persist_extraction(
                artifact_paths=artifact_paths,
                run_id=partition_one_run_id,
                selection_mode="completed",
                frame=partition_frames[1].copy(),
                as_of_date=settings.as_of_date.isoformat(),
                partition_settings=partition_one_settings,
            )
            _write_partition_completion_marker(
                artifact_paths=artifact_paths,
                run_id=partition_one_run_id,
                row_count=len(partition_frames[1].index),
                chunk_count=2,
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="partition-resume-skip-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            completed_partition_calls: list[int] = []
            original_publish = StorePredictionPublisher.publish

            def _extract_with_reuse(
                *,
                settings,
                run_id,
                selection_mode,
                progress_callback=None,
                query_options=None,
            ):
                if selection_mode == "future":
                    return future_extraction
                current_partition = query_options.completed_partition
                completed_partition_calls.append(current_partition.partition_index)
                frame = partition_frames[current_partition.partition_index].copy()
                artifact = _persist_extraction(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    selection_mode=selection_mode,
                    frame=frame,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=current_partition,
                )
                _write_partition_completion_marker(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    row_count=len(frame.index),
                    chunk_count=2,
                )
                return replace(
                    artifact,
                    fetch_mode="chunked_fetch",
                    chunk_count=2,
                    completed_chunk_count=2,
                    cumulative_rows_written=len(frame.index),
                    partition_completion_state="finalized",
                )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                side_effect=lambda *, settings, run_id, query_options: _build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=query_options.completed_partition,
                ),
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_build_publish_without_zero_fail(
                    artifact_paths=artifact_paths,
                    original_publish=original_publish,
                ),
            ):
                artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="partition-resume-skip",
                    score_run_id="partition-resume-skip-score",
                    decision_surface_run_id="partition-resume-skip-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    extraction_provider=_extract_with_reuse,
                )

            partition_summary = json.loads(
                Path(artifacts.completed_partition_summary_path).read_text(encoding="utf-8")
            )
            operator_log = Path(artifacts.operator_log_path).read_text(encoding="utf-8")

            self.assertEqual(completed_partition_calls, [2])
            self.assertEqual(
                partition_summary["partitions_skipped_due_to_existing_completion"],
                1,
            )
            self.assertEqual(
                partition_summary["partitions"][0]["resume_state"],
                "skip_finalized_partition",
            )
            self.assertTrue(
                partition_summary["partitions"][0]["skipped_due_to_existing_completion"]
            )
            self.assertEqual(
                partition_summary["partitions"][1]["resume_state"],
                "new_partition",
            )
            self.assertIn(
                "partition_resume_state[1/2]: skip_finalized_partition",
                operator_log,
            )

    def test_operational_cycle_restarts_incomplete_completed_partition_from_first_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            completed_partitioning = PromotionCompletedPartitionSettings(
                strategy="store_number",
                partition_count=2,
            )
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
                completed_partitioning=completed_partitioning,
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=False,
                ),
            )
            completed_source_frame = build_completed_promotions_base_frame()
            partition_frames = {
                1: completed_source_frame.iloc[::2].reset_index(drop=True),
                2: completed_source_frame.iloc[1::2].reset_index(drop=True),
            }
            partition_one_settings = completed_partitioning.with_partition_index(1)
            partition_one_run_id = _completed_partition_run_id(
                "partition-resume-incomplete",
                partition_one_settings,
            )
            _persist_extraction(
                artifact_paths=artifact_paths,
                run_id=partition_one_run_id,
                selection_mode="completed",
                frame=partition_frames[1].copy(),
                as_of_date=settings.as_of_date.isoformat(),
                partition_settings=partition_one_settings,
            )
            _write_partition_completion_marker(
                artifact_paths=artifact_paths,
                run_id=partition_one_run_id,
                row_count=len(partition_frames[1].index),
                chunk_count=2,
            )
            partition_two_settings = completed_partitioning.with_partition_index(2)
            partition_two_run_id = _completed_partition_run_id(
                "partition-resume-incomplete",
                partition_two_settings,
            )
            _write_partition_progress_state(
                artifact_paths=artifact_paths,
                run_id=partition_two_run_id,
                partition_completion_state="failed_incomplete",
                resume_state="resume_incomplete_partition",
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="partition-resume-incomplete-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            completed_partition_calls: list[int] = []
            original_publish = StorePredictionPublisher.publish

            def _extract_from_incomplete(
                *,
                settings,
                run_id,
                selection_mode,
                progress_callback=None,
                query_options=None,
            ):
                if selection_mode == "future":
                    return future_extraction
                current_partition = query_options.completed_partition
                completed_partition_calls.append(current_partition.partition_index)
                frame = partition_frames[current_partition.partition_index].copy()
                artifact = _persist_extraction(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    selection_mode=selection_mode,
                    frame=frame,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=current_partition,
                )
                _write_partition_completion_marker(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    row_count=len(frame.index),
                    chunk_count=2,
                    resume_state="resume_incomplete_partition",
                )
                return replace(
                    artifact,
                    fetch_mode="chunked_fetch",
                    chunk_count=2,
                    completed_chunk_count=2,
                    cumulative_rows_written=len(frame.index),
                    partition_completion_state="finalized",
                )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                side_effect=lambda *, settings, run_id, query_options: _build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=query_options.completed_partition,
                ),
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_build_publish_without_zero_fail(
                    artifact_paths=artifact_paths,
                    original_publish=original_publish,
                ),
            ):
                artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="partition-resume-incomplete",
                    score_run_id="partition-resume-incomplete-score",
                    decision_surface_run_id="partition-resume-incomplete-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    extraction_provider=_extract_from_incomplete,
                )

            partition_summary = json.loads(
                Path(artifacts.completed_partition_summary_path).read_text(encoding="utf-8")
            )
            operator_log = Path(artifacts.operator_log_path).read_text(encoding="utf-8")

            self.assertEqual(completed_partition_calls, [2])
            self.assertEqual(
                partition_summary["partitions_skipped_due_to_existing_completion"],
                1,
            )
            self.assertEqual(
                partition_summary["partitions_resumed_from_incomplete"],
                1,
            )
            self.assertEqual(
                partition_summary["partitions"][1]["resume_state"],
                "resume_incomplete_partition",
            )
            self.assertIn(
                "partition_resume_state[2/2]: resume_incomplete_partition",
                operator_log,
            )

    def test_operational_cycle_timeout_failure_surfaces_rendered_sql_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=60,
                ),
                runtime_date=datetime(2024, 9, 1, tzinfo=UTC).date(),
                artifacts=artifact_paths,
            )

            def _raise_timeout(
                *,
                settings,
                run_id,
                selection_mode,
                progress_callback=None,
                query_options=None,
            ):
                error = PromotionMssqlQueryTimeoutError("Query timeout expired during SQL executing")
                setattr(error, "selection_mode", selection_mode)
                setattr(error, "as_of_date", settings.as_of_date.isoformat())
                setattr(error, "current_sql_subphase", "SQL executing")
                setattr(error, "query_timeout_seconds", 60)
                setattr(error, "rendered_sql_path", str(artifact_paths.manifests_run_root(run_id) / "rendered_sql.sql"))
                setattr(
                    error,
                    "rendered_sql_parameters_path",
                    str(artifact_paths.manifests_run_root(run_id) / "rendered_sql_parameters.json"),
                )
                setattr(error, "extraction_telemetry_json_path", str(artifact_paths.extraction_telemetry_json_path(run_id)))
                setattr(error, "extraction_telemetry_csv_path", str(artifact_paths.extraction_telemetry_csv_path(run_id)))
                setattr(error, "sql_diagnostics_summary_json_path", str(artifact_paths.sql_diagnostics_summary_json_path(run_id)))
                setattr(error, "sql_diagnostics_summary_txt_path", str(artifact_paths.sql_diagnostics_summary_txt_path(run_id)))
                raise error

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="operational-timeout-run",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ):
                with self.assertRaises(PromotionMssqlQueryTimeoutError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="operational-timeout-run",
                        extraction_provider=_raise_timeout,
                    )

            operator_log = artifact_paths.operator_log_path("operational-timeout-run").read_text(
                encoding="utf-8"
            )
            self.assertIn("FAILED STAGE", operator_log)
            self.assertIn("stage: 3/14 Extract completed promotions", operator_log)
            self.assertIn("mode: completed", operator_log)
            self.assertIn("query_timeout_seconds_applied: 60", operator_log)
            self.assertIn("rendered_sql_path:", operator_log)
            self.assertIn("rendered_sql_parameters_path:", operator_log)
            self.assertIn(
                "suggestion: python -m runtime.promotions.inspect_promotions_sql_extraction",
                operator_log,
            )
            self.assertIn("FINAL OUTPUTS", operator_log)

            manifest_path = artifact_paths.operational_cycle_manifest_path("operational-timeout-run")
            self.assertTrue(manifest_path.exists())
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_payload["run_id"], "operational-timeout-run")
            self.assertEqual(
                manifest_payload["failure"]["stage_name"],
                "Extract completed promotions",
            )
            self.assertEqual(
                manifest_payload["final_outputs"]["operational_cycle_manifest_path"],
                str(manifest_path),
            )
            self.assertEqual(
                manifest_payload["final_outputs"]["operator_summary_csv_path"],
                str(artifact_paths.operator_summary_csv_path("operational-timeout-run")),
            )

    def test_stage6_failure_keeps_completed_partition_summary_path_when_stage3_succeeded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=60,
                ),
                runtime_date=datetime(2024, 9, 1, tzinfo=UTC).date(),
                artifacts=artifact_paths,
                completed_partitioning=PromotionCompletedPartitionSettings(
                    strategy="store_number",
                    partition_count=2,
                ),
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=False,
                ),
            )
            completed_source_frame = build_completed_promotions_base_frame()
            partition_frames = {
                1: completed_source_frame.iloc[::2].reset_index(drop=True),
                2: completed_source_frame.iloc[1::2].reset_index(drop=True),
            }

            def _extract_then_fail_future(
                *,
                settings,
                run_id,
                selection_mode,
                progress_callback=None,
                query_options=None,
            ):
                if selection_mode == "future":
                    error = PromotionMssqlQueryTimeoutError("Query timeout during SQL executing")
                    setattr(error, "selection_mode", "future")
                    setattr(error, "current_sql_subphase", "SQL executing")
                    raise error

                self.assertIsNotNone(query_options)
                self.assertIsNotNone(query_options.completed_partition)
                current_partition = query_options.completed_partition
                return _persist_extraction(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    selection_mode=selection_mode,
                    frame=partition_frames[current_partition.partition_index].copy(),
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=current_partition,
                )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                side_effect=lambda *, settings, run_id, query_options: _build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=query_options.completed_partition,
                ),
            ):
                with self.assertRaises(PromotionMssqlQueryTimeoutError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="stage6-failure-keeps-completed-summary",
                        score_run_id="stage6-failure-keeps-completed-summary-score",
                        decision_surface_run_id="stage6-failure-keeps-completed-summary-decision-surface",
                        extraction_provider=_extract_then_fail_future,
                    )

            manifest = json.loads(
                artifact_paths.operational_cycle_manifest_path(
                    "stage6-failure-keeps-completed-summary"
                ).read_text(encoding="utf-8")
            )
            partition_summary_path = artifact_paths.completed_partition_summary_path(
                "stage6-failure-keeps-completed-summary"
            )

            self.assertTrue(partition_summary_path.exists())
            self.assertEqual(
                manifest["completed_extraction"]["partition_summary_path"],
                str(partition_summary_path),
            )
            self.assertEqual(
                manifest["final_outputs"]["completed_partition_summary_path"],
                str(partition_summary_path),
            )

    def test_build_failure_final_outputs_leaves_completed_partition_summary_path_unavailable_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=60,
                ),
                runtime_date=datetime(2024, 9, 1, tzinfo=UTC).date(),
                artifacts=artifact_paths,
            )
            failure_outputs = _build_failure_final_outputs(
                settings=settings,
                run_id="stage3-failure-no-completed-summary",
                score_run_id="stage3-failure-no-completed-summary-score",
                decision_surface_run_id="stage3-failure-no-completed-summary-decision-surface",
                manifest_path=artifact_paths.operational_cycle_manifest_path(
                    "stage3-failure-no-completed-summary"
                ),
                error=RuntimeError("synthetic failure before any completed partition summary exists"),
            )
            partition_summary_path = artifact_paths.completed_partition_summary_path(
                "stage3-failure-no-completed-summary"
            )

            self.assertFalse(partition_summary_path.exists())
            self.assertEqual(
                failure_outputs["completed_partition_summary_path"],
                "unavailable",
            )

    def test_operational_cycle_accepts_completed_repartition_retry_and_reruns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_partitioning=PromotionCompletedPartitionSettings(
                    strategy="promotion_row_key_hash_bucket",
                    partition_count=2,
                ),
            )
            completed_source_frame = build_completed_promotions_base_frame()
            future_source_frame = build_future_promotions_base_frame()
            extraction_calls: list[tuple[str, int | None, int | None]] = []
            original_publish = StorePredictionPublisher.publish

            def _extract_with_partitions(
                *,
                settings,
                run_id,
                selection_mode,
                progress_callback=None,
                query_options=None,
            ):
                partition_settings = (
                    query_options.completed_partition if query_options is not None else None
                )
                extraction_calls.append(
                    (
                        selection_mode,
                        partition_settings.partition_count if partition_settings is not None else None,
                        partition_settings.partition_index if partition_settings is not None else None,
                    )
                )
                source_frame = (
                    future_source_frame
                    if selection_mode == "future"
                    else _frame_for_partition(completed_source_frame, partition_settings)
                )
                return _persist_extraction(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    selection_mode=selection_mode,
                    frame=source_frame,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=partition_settings,
                )

            def _preflight_side_effect(*, settings, run_id, query_options):
                partition_settings = query_options.completed_partition if query_options is not None else None
                if (
                    partition_settings is not None
                    and partition_settings.partition_count == 2
                    and partition_settings.partition_index == 1
                ):
                    return _build_preflight_result(
                        artifact_paths=artifact_paths,
                        run_id=run_id,
                        as_of_date=settings.as_of_date.isoformat(),
                        partition_settings=partition_settings,
                        verdict="TOO_WIDE_REPARTITION_REQUIRED",
                        reason="completed slice is too expensive for the live timeout budget",
                        estimated_cost_score=1.6,
                        cost_guardrail_verdict="TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET",
                        cost_guardrail_reason=(
                            "estimated live SQL cost exceeded the configured live timeout budget"
                        ),
                        recommended_partition_strategy="promotion_row_key_hash_bucket",
                        recommended_partition_count=3,
                    )
                return _build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=partition_settings,
                )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                side_effect=_preflight_side_effect,
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_build_publish_without_zero_fail(
                    artifact_paths=artifact_paths,
                    original_publish=original_publish,
                ),
            ):
                artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="operational-repartition-accepted",
                    score_run_id="operational-repartition-accepted-score",
                    decision_surface_run_id="operational-repartition-accepted-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    extraction_provider=_extract_with_partitions,
                )

            retry_json_path = artifact_paths.completed_partition_retries_json_path(
                "operational-repartition-accepted"
            )
            retry_csv_path = artifact_paths.completed_partition_retries_csv_path(
                "operational-repartition-accepted"
            )
            retry_payload = json.loads(retry_json_path.read_text(encoding="utf-8"))
            manifest_payload = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            operator_log = Path(artifacts.operator_log_path).read_text(encoding="utf-8")

            self.assertTrue(retry_json_path.exists())
            self.assertTrue(retry_csv_path.exists())
            self.assertEqual(retry_payload["accepted_retry_count"], 1)
            self.assertEqual(retry_payload["retry_event_count"], 1)
            self.assertEqual(retry_payload["attempts"][0]["status"], "accepted")
            self.assertEqual(retry_payload["attempts"][0]["initial_partition_count"], 2)
            self.assertEqual(retry_payload["attempts"][0]["accepted_partition_count"], 3)
            self.assertEqual(
                retry_payload["attempts"][0]["cost_guardrail_verdict"],
                "TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET",
            )
            self.assertEqual(retry_payload["attempts"][0]["estimated_cost_score"], 1.6)
            self.assertEqual(
                manifest_payload["runtime_settings"]["completed_partitioning"]["partition_count"],
                3,
            )
            self.assertEqual(
                manifest_payload["completed_extraction"]["partition_retries_json_path"],
                str(retry_json_path),
            )
            self.assertEqual(
                manifest_payload["final_outputs"]["completed_partition_retries_csv_path"],
                str(retry_csv_path),
            )
            self.assertTrue(
                any(
                    selection_mode == "completed" and partition_count == 3
                    for selection_mode, partition_count, _ in extraction_calls
                )
            )
            self.assertIn("repartition_attempt_number: 1", operator_log)
            self.assertIn("cost_guardrail_verdict: TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET", operator_log)
            self.assertIn("repartition_recommended_partition_count: 3", operator_log)
            self.assertIn("repartition_decision: accepted", operator_log)
            self.assertIn("accepted_partition_count: 3", operator_log)

    def test_operational_cycle_repartition_retry_is_capped_by_max_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_partitioning=PromotionCompletedPartitionSettings(
                    strategy="promotion_row_key_hash_bucket",
                    partition_count=2,
                ),
                completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                    auto_repartition_completed=True,
                    max_completed_repartition_attempts=1,
                ),
            )
            extraction_called = False

            def _should_not_extract(**kwargs):
                nonlocal extraction_called
                extraction_called = True
                raise AssertionError("completed extraction should not run while repartition preflight keeps rejecting")

            def _preflight_side_effect(*, settings, run_id, query_options):
                partition_settings = query_options.completed_partition if query_options is not None else None
                if (
                    partition_settings is not None
                    and partition_settings.partition_count == 2
                    and partition_settings.partition_index == 1
                ):
                    return _build_preflight_result(
                        artifact_paths=artifact_paths,
                        run_id=run_id,
                        as_of_date=settings.as_of_date.isoformat(),
                        partition_settings=partition_settings,
                        verdict="TOO_WIDE_REPARTITION_REQUIRED",
                        reason="candidate_store_sku_count exceeds configured threshold",
                        candidate_store_sku_count=2400,
                        recommended_partition_strategy="promotion_row_key_hash_bucket",
                        recommended_partition_count=3,
                    )
                return _build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=partition_settings,
                    verdict="TOO_WIDE_REPARTITION_REQUIRED",
                    reason="candidate_store_sku_count still exceeds configured threshold",
                    candidate_store_sku_count=1800,
                    recommended_partition_strategy="promotion_row_key_hash_bucket",
                    recommended_partition_count=4,
                )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                side_effect=_preflight_side_effect,
            ):
                with self.assertRaises(PromotionCompletedPreflightRejectedError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="operational-repartition-max-attempts",
                        extraction_provider=_should_not_extract,
                    )

            self.assertFalse(extraction_called)
            retry_payload = json.loads(
                artifact_paths.completed_partition_retries_json_path(
                    "operational-repartition-max-attempts"
                ).read_text(encoding="utf-8")
            )
            operator_log = artifact_paths.operator_log_path(
                "operational-repartition-max-attempts"
            ).read_text(encoding="utf-8")
            manifest_payload = json.loads(
                artifact_paths.operational_cycle_manifest_path(
                    "operational-repartition-max-attempts"
                ).read_text(encoding="utf-8")
            )

            self.assertEqual(len(retry_payload["attempts"]), 2)
            self.assertEqual(retry_payload["attempts"][0]["status"], "accepted")
            self.assertEqual(retry_payload["attempts"][1]["status"], "rejected_max_attempts")
            self.assertIn("repartition_decision: rejected_max_attempts", operator_log)
            self.assertIn("completed_repartition_attempts_tried: 1", operator_log)
            self.assertIn("completed_partition_retries_json_path", operator_log)
            self.assertIn("FINAL OUTPUTS", operator_log)
            self.assertEqual(
                manifest_payload["final_outputs"]["completed_partition_retries_json_path"],
                str(
                    artifact_paths.completed_partition_retries_json_path(
                        "operational-repartition-max-attempts"
                    )
                ),
            )

    def test_operational_cycle_repartition_retry_is_capped_by_max_partition_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_partitioning=PromotionCompletedPartitionSettings(
                    strategy="promotion_row_key_hash_bucket",
                    partition_count=2,
                ),
                completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                    auto_repartition_completed=True,
                    max_completed_partition_count=4,
                ),
            )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                side_effect=lambda *, settings, run_id, query_options: _build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                    partition_settings=query_options.completed_partition,
                    verdict="TOO_WIDE_REPARTITION_REQUIRED",
                    reason="candidate_store_sku_count exceeds configured threshold",
                    candidate_store_sku_count=2400,
                    recommended_partition_strategy="promotion_row_key_hash_bucket",
                    recommended_partition_count=8,
                ),
            ):
                with self.assertRaises(PromotionCompletedPreflightRejectedError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="operational-repartition-max-count",
                        extraction_provider=lambda **kwargs: (_ for _ in ()).throw(
                            AssertionError("completed extraction should not run when the partition cap rejects the retry")
                        ),
                    )

            retry_json_path = artifact_paths.completed_partition_retries_json_path(
                "operational-repartition-max-count"
            )
            retry_csv_path = artifact_paths.completed_partition_retries_csv_path(
                "operational-repartition-max-count"
            )
            partition_summary_path = artifact_paths.completed_partition_summary_path(
                "operational-repartition-max-count"
            )
            manifest_path = artifact_paths.operational_cycle_manifest_path(
                "operational-repartition-max-count"
            )
            operator_log = artifact_paths.operator_log_path(
                "operational-repartition-max-count"
            ).read_text(encoding="utf-8")
            retry_payload = json.loads(retry_json_path.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(retry_json_path.exists())
            self.assertTrue(retry_csv_path.exists())
            self.assertTrue(partition_summary_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertEqual(len(retry_payload["attempts"]), 1)
            self.assertEqual(
                retry_payload["attempts"][0]["status"],
                "rejected_max_partition_count",
            )
            self.assertIn("repartition_decision: rejected_max_partition_count", operator_log)
            self.assertIn("max_completed_partition_count: 4", operator_log)
            self.assertIn("completed_partition_summary_path", operator_log)
            self.assertIn("completed_partition_retries_csv_path", operator_log)
            self.assertEqual(
                manifest_payload["final_outputs"]["completed_partition_retries_csv_path"],
                str(retry_csv_path),
            )

    def test_operational_cycle_rejects_completed_extraction_before_heavy_sql_when_preflight_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                    auto_repartition_completed=False,
                ),
            )
            extraction_called = False

            def _should_not_extract(**kwargs):
                nonlocal extraction_called
                extraction_called = True
                raise AssertionError("completed extraction should not run after preflight rejection")

            rejected_preflight = _build_preflight_result(
                artifact_paths=artifact_paths,
                run_id="operational-preflight-rejected",
                as_of_date=settings.as_of_date.isoformat(),
                verdict="TOO_WIDE_REPARTITION_REQUIRED",
                reason="completed slice is too expensive for the live timeout budget",
                estimated_cost_score=1.8,
                cost_guardrail_verdict="TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET",
                cost_guardrail_reason=(
                    "estimated live SQL cost exceeded the configured live timeout budget"
                ),
                recommended_partition_strategy="store_sku_hash_bucket",
                recommended_partition_count=3,
            )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=rejected_preflight,
            ):
                with self.assertRaises(PromotionCompletedPreflightRejectedError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="operational-preflight-rejected",
                        extraction_provider=_should_not_extract,
                    )

            self.assertFalse(extraction_called)
            operator_log = artifact_paths.operator_log_path(
                "operational-preflight-rejected"
            ).read_text(encoding="utf-8")
            self.assertIn("preflight_verdict: TOO_WIDE_REPARTITION_REQUIRED", operator_log)
            self.assertIn("cost_guardrail_verdict: TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET", operator_log)
            self.assertIn("cost_guardrail_reason: estimated live SQL cost exceeded", operator_log)
            self.assertIn("recommended_partition_strategy: store_sku_hash_bucket", operator_log)
            self.assertIn("recommended_partition_count: 3", operator_log)
            self.assertIn("FINAL OUTPUTS", operator_log)

            manifest_path = artifact_paths.operational_cycle_manifest_path(
                "operational-preflight-rejected"
            )
            self.assertTrue(manifest_path.exists())
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_payload["run_id"], "operational-preflight-rejected")
            self.assertEqual(
                manifest_payload["failure"]["exception_type"],
                "PromotionCompletedPreflightRejectedError",
            )
            self.assertEqual(
                manifest_payload["final_outputs"]["completed_preflight_summary_path"],
                str(artifact_paths.extraction_preflight_summary_json_path("operational-preflight-rejected")),
            )
            retry_payload = json.loads(
                artifact_paths.completed_partition_retries_json_path(
                    "operational-preflight-rejected"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                retry_payload["attempts"][0]["status"],
                "rejected_auto_repartition_disabled",
            )

    def test_stage3_system_error_is_normalized_and_writes_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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

            def _raise_stage3_system_error(**kwargs):
                raise SystemError("<class 'pyodbc.Error'> returned a result with an exception set")

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="stage3-systemerror",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ):
                with self.assertRaises(PromotionMssqlQueryError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="stage3-systemerror",
                        extraction_provider=_raise_stage3_system_error,
                    )

            manifest = json.loads(
                artifact_paths.operational_cycle_manifest_path("stage3-systemerror").read_text(
                    encoding="utf-8"
                )
            )
            final_outputs = manifest["final_outputs"]
            self.assertEqual(manifest["failure"]["exception_type"], "PromotionMssqlQueryError")
            self.assertNotEqual(
                final_outputs["stage3_completed_extraction_failure_summary_path"],
                "unavailable",
            )
            summary_payload = json.loads(
                Path(final_outputs["stage3_completed_extraction_failure_summary_path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                summary_payload["normalized_failure_classification"],
                "mssql_driver_runtime_failure",
            )
            self.assertFalse(summary_payload["interrupted"])

    def test_stage3_keyboard_interrupt_is_normalized_as_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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

            def _raise_stage3_interrupt(**kwargs):
                raise KeyboardInterrupt()

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="stage3-interrupted",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ):
                with self.assertRaises(PromotionCompletedExtractionInterruptedError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="stage3-interrupted",
                        extraction_provider=_raise_stage3_interrupt,
                    )

            manifest = json.loads(
                artifact_paths.operational_cycle_manifest_path("stage3-interrupted").read_text(
                    encoding="utf-8"
                )
            )
            final_outputs = manifest["final_outputs"]
            summary_payload = json.loads(
                Path(final_outputs["stage3_completed_extraction_failure_summary_path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["failure"]["exception_type"],
                "PromotionCompletedExtractionInterruptedError",
            )
            self.assertTrue(summary_payload["interrupted"])
            self.assertEqual(summary_payload["normalized_failure_classification"], "interrupted")

    def test_stage3_timeout_failure_keeps_timeout_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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

            def _raise_stage3_timeout(**kwargs):
                raise PromotionMssqlQueryTimeoutError("Query timeout during SQL executing")

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="stage3-timeout",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ):
                with self.assertRaises(PromotionMssqlQueryTimeoutError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="stage3-timeout",
                        extraction_provider=_raise_stage3_timeout,
                    )

            manifest = json.loads(
                artifact_paths.operational_cycle_manifest_path("stage3-timeout").read_text(
                    encoding="utf-8"
                )
            )
            summary_payload = json.loads(
                Path(
                    manifest["final_outputs"]["stage3_completed_extraction_failure_summary_path"]
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(summary_payload["normalized_failure_classification"], "mssql_query_timeout")

    def test_stage3_generic_runtime_failure_is_diagnosed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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

            def _raise_stage3_runtime_error(**kwargs):
                raise ValueError("stage3 synthetic failure")

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="stage3-generic",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ):
                with self.assertRaises(ValueError):
                    run_operational_cycle(
                        settings=settings,
                        run_id="stage3-generic",
                        extraction_provider=_raise_stage3_runtime_error,
                    )

            manifest = json.loads(
                artifact_paths.operational_cycle_manifest_path("stage3-generic").read_text(
                    encoding="utf-8"
                )
            )
            summary_payload = json.loads(
                Path(
                    manifest["final_outputs"]["stage3_completed_extraction_failure_summary_path"]
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(summary_payload["normalized_failure_classification"], "runtime_failure")

    def test_completed_landed_batch_runner_reuses_finalized_partition_with_multiple_batches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    batch_row_count=2,
                    chunk_row_count=2,
                ),
            )
            completed_frame = build_completed_promotions_base_frame().iloc[:4].reset_index(drop=True)
            frames_by_batch = {
                1: completed_frame.iloc[:2].reset_index(drop=True),
                2: completed_frame.iloc[2:4].reset_index(drop=True),
            }

            initial_result = execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-reuse",
                executor=_StaticCandidateCountExecutor(candidate_count=4),
                base_extractor=_FakeCompletedBaseStageExtractor(frames_by_batch),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )
            reused_result = execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-reuse",
                executor=_FailingCandidateCountExecutor(),
                base_extractor=_FailingCompletedBaseStageExtractor(),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )

            self.assertEqual(initial_result.batch_count, 2)
            self.assertEqual(reused_result.resume_state, "skip_finalized_partition")
            self.assertTrue(reused_result.skipped_due_to_existing_completion)
            self.assertEqual(reused_result.batch_count, 2)
            self.assertEqual(reused_result.finalized_batch_count, 2)
            self.assertEqual(reused_result.total_landed_rows, 4)

    def test_completed_landed_batch_runner_rebuilds_missing_parent_partition_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    batch_row_count=2,
                    chunk_row_count=2,
                ),
            )
            completed_frame = build_completed_promotions_base_frame().iloc[:4].reset_index(drop=True)
            frames_by_batch = {
                1: completed_frame.iloc[:2].reset_index(drop=True),
                2: completed_frame.iloc[2:4].reset_index(drop=True),
            }

            execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-rebuild-parent",
                executor=_StaticCandidateCountExecutor(candidate_count=4),
                base_extractor=_FakeCompletedBaseStageExtractor(frames_by_batch),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )
            artifact_paths.extracted_base_path("landed-batch-rebuild-parent").unlink()

            reused_result = execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-rebuild-parent",
                executor=_FailingCandidateCountExecutor(),
                base_extractor=_FailingCompletedBaseStageExtractor(),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )

            self.assertEqual(reused_result.resume_state, "skip_finalized_partition")
            self.assertTrue(reused_result.skipped_due_to_existing_completion)
            self.assertEqual(reused_result.total_landed_rows, 4)
            self.assertTrue(artifact_paths.extracted_base_path("landed-batch-rebuild-parent").exists())

    def test_completed_landed_batch_runner_raises_domain_error_for_unrecoverable_parent_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    batch_row_count=2,
                    chunk_row_count=2,
                ),
            )
            completed_frame = build_completed_promotions_base_frame().iloc[:2].reset_index(drop=True)
            frames_by_batch = {1: completed_frame}

            execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-unrecoverable-parent",
                executor=_StaticCandidateCountExecutor(candidate_count=2),
                base_extractor=_FakeCompletedBaseStageExtractor(frames_by_batch),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )
            _remove_run_outputs(
                artifact_paths,
                "landed-batch-unrecoverable-parent-batch-000001",
            )
            artifact_paths.extracted_base_path("landed-batch-unrecoverable-parent").unlink()

            with self.assertRaises(PromotionCompletedPartitionArtifactResolutionError):
                execute_completed_partition_landed_batches(
                    settings=settings,
                    run_id="landed-batch-unrecoverable-parent",
                    executor=_FailingCandidateCountExecutor(),
                    base_extractor=_FailingCompletedBaseStageExtractor(),
                    window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                    transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                    dataset_joiner=_PassthroughCompletedDatasetJoiner(),
                )

    def test_operational_cycle_loader_rebuilds_missing_parent_partition_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            partition_settings = PromotionCompletedPartitionSettings(
                strategy="store_number",
                partition_count=2,
                partition_index=1,
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    batch_row_count=2,
                    chunk_row_count=2,
                ),
            )
            completed_frame = build_completed_promotions_base_frame().iloc[:4].reset_index(drop=True)
            frames_by_batch = {
                1: completed_frame.iloc[:2].reset_index(drop=True),
                2: completed_frame.iloc[2:4].reset_index(drop=True),
            }

            execute_completed_partition_landed_batches(
                settings=settings,
                run_id="partition-loader-rebuild",
                executor=_StaticCandidateCountExecutor(candidate_count=4),
                query_options=PromotionBaseQueryOptions(
                    completed_partition=partition_settings,
                ),
                base_extractor=_FakeCompletedBaseStageExtractor(frames_by_batch),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )
            artifact_paths.extracted_base_path("partition-loader-rebuild").unlink()

            loaded = _load_existing_completed_partition_artifact(
                settings=settings,
                run_id="partition-loader-rebuild",
                partition_settings=partition_settings,
            )

            self.assertEqual(int(loaded.manifest["row_count"]), 4)
            self.assertEqual(loaded.resume_state, "skip_finalized_partition")
            self.assertTrue(artifact_paths.extracted_base_path("partition-loader-rebuild").exists())

    def test_completed_landed_batch_runner_emits_staged_progress_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    batch_row_count=2,
                    chunk_row_count=2,
                ),
            )
            completed_frame = build_completed_promotions_base_frame().iloc[:2].reset_index(drop=True)
            frames_by_batch = {1: completed_frame}
            progress_messages: list[str] = []

            execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-progress",
                executor=_StaticCandidateCountExecutor(candidate_count=2),
                base_extractor=_FakeCompletedBaseStageExtractor(frames_by_batch),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
                progress_callback=progress_messages.append,
            )

            joined_messages = "\n".join(progress_messages)
            self.assertIn("completed_sales_history_start_date: 2024-01-01", joined_messages)
            self.assertIn("stage_start: completed_base", joined_messages)
            self.assertIn("stage_finished: completed_base", joined_messages)
            self.assertIn("stage_start: completed_window_aggregates", joined_messages)
            self.assertIn("stage_finished: completed_window_aggregates", joined_messages)
            self.assertIn("stage_start: completed_transaction_aggregates", joined_messages)
            self.assertIn("stage_finished: completed_transaction_aggregates", joined_messages)
            self.assertIn("stage_start: completed_final_assembler", joined_messages)
            self.assertIn("stage_finished: completed_final_assembler", joined_messages)

    def test_completed_landed_batch_runner_marks_failed_stage_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    batch_row_count=2,
                    chunk_row_count=2,
                ),
            )
            completed_frame = build_completed_promotions_base_frame().iloc[:2].reset_index(drop=True)
            frames_by_batch = {1: completed_frame}

            with self.assertRaisesRegex(RuntimeError, "window aggregate stage failure") as raised:
                execute_completed_partition_landed_batches(
                    settings=settings,
                    run_id="landed-batch-stage-failure",
                    executor=_StaticCandidateCountExecutor(candidate_count=2),
                    base_extractor=_FakeCompletedBaseStageExtractor(frames_by_batch),
                    window_aggregates_extractor=_FailingCompletedWindowAggregatesExtractor(),
                    transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                    dataset_joiner=_PassthroughCompletedDatasetJoiner(),
                )

            error = raised.exception
            self.assertEqual(
                getattr(error, "completed_stage_failure_label", None),
                "completed_window_aggregates",
            )
            self.assertEqual(getattr(error, "selection_mode", None), "completed")
            self.assertEqual(
                getattr(error, "completed_sales_history_start_date", None),
                "2024-01-01",
            )
            self.assertIn(
                "landed-batch-stage-failure-batch-000001-window-aggregates",
                getattr(error, "completed_batch_stage_run_id", ""),
            )
            self.assertIn(
                "rendered_sql.sql",
                getattr(error, "rendered_sql_path", ""),
            )
            self.assertIn(
                "extraction_telemetry.json",
                getattr(error, "extraction_telemetry_json_path", ""),
            )

    def test_completed_landed_batch_runner_resumes_from_first_incomplete_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    batch_row_count=2,
                    chunk_row_count=2,
                ),
            )
            completed_frame = build_completed_promotions_base_frame().iloc[:4].reset_index(drop=True)
            frames_by_batch = {
                1: completed_frame.iloc[:2].reset_index(drop=True),
                2: completed_frame.iloc[2:4].reset_index(drop=True),
            }
            execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-resume",
                executor=_StaticCandidateCountExecutor(candidate_count=4),
                base_extractor=_FakeCompletedBaseStageExtractor(frames_by_batch),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )
            _remove_run_outputs(artifact_paths, "landed-batch-resume")
            _remove_run_outputs(artifact_paths, "landed-batch-resume-batch-000002")

            resumed_extractor = _FakeCompletedBaseStageExtractor(frames_by_batch)
            resumed_result = execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-resume",
                executor=_StaticCandidateCountExecutor(candidate_count=4),
                base_extractor=resumed_extractor,
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )

            self.assertEqual(resumed_extractor.calls, [2])
            self.assertEqual(resumed_result.resumed_batch_count, 1)
            self.assertEqual(resumed_result.rebuilt_batch_count, 0)
            self.assertEqual(resumed_result.batch_count, 2)
            self.assertEqual(int(resumed_result.manifest["row_count"]), 4)

    def test_completed_landed_batch_runner_rebuilds_corrupt_batch_marker_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
                    enable_landed_batches=True,
                    batch_row_count=2,
                    chunk_row_count=2,
                ),
            )
            completed_frame = build_completed_promotions_base_frame().iloc[:2].reset_index(drop=True)
            frames_by_batch = {1: completed_frame}
            execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-corrupt",
                executor=_StaticCandidateCountExecutor(candidate_count=2),
                base_extractor=_FakeCompletedBaseStageExtractor(frames_by_batch),
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )
            _remove_run_outputs(artifact_paths, "landed-batch-corrupt")
            completion_path = artifact_paths.extraction_partition_completion_path(
                "landed-batch-corrupt-batch-000001"
            )
            completion_path.write_text("{not-json", encoding="utf-8")

            rebuilt_extractor = _FakeCompletedBaseStageExtractor(frames_by_batch)
            rebuilt_result = execute_completed_partition_landed_batches(
                settings=settings,
                run_id="landed-batch-corrupt",
                executor=_StaticCandidateCountExecutor(candidate_count=2),
                base_extractor=rebuilt_extractor,
                window_aggregates_extractor=_FakeCompletedWindowAggregatesExtractor(),
                transaction_aggregates_extractor=_FakeCompletedTransactionAggregatesExtractor(),
                dataset_joiner=_PassthroughCompletedDatasetJoiner(),
            )

            self.assertEqual(rebuilt_extractor.calls, [1])
            self.assertEqual(rebuilt_result.rebuilt_batch_count, 1)
            self.assertEqual(rebuilt_result.finalized_batch_count, 1)
            self.assertEqual(rebuilt_result.total_landed_rows, 2)

    def test_operational_cycle_builds_dataset_from_landed_completed_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
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
            completed_frame = build_completed_promotions_base_frame()
            persisted_completed = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="landed-dataset-run",
                selection_mode="completed",
                frame=completed_frame.copy(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            future_extraction = _persist_extraction(
                artifact_paths=artifact_paths,
                run_id="landed-dataset-run-score",
                selection_mode="future",
                frame=build_future_promotions_base_frame(),
                as_of_date=settings.as_of_date.isoformat(),
            )
            original_publish = StorePredictionPublisher.publish

            def _extract_from_landed_parquet(
                *,
                settings,
                run_id,
                selection_mode,
                progress_callback=None,
                query_options=None,
            ):
                if selection_mode == "future":
                    return future_extraction
                return replace(
                    persisted_completed,
                    frame=persisted_completed.frame.iloc[0:0].copy(),
                    fetch_mode="landed_batch_fetch",
                    chunk_mode="chunked_fetch",
                    batch_count=2,
                    finalized_batch_count=2,
                    resumed_batch_count=1,
                    rebuilt_batch_count=0,
                    total_landed_rows=len(completed_frame.index),
                    completion_state="finalized",
                    partition_completion_state="finalized",
                )

            with patch(
                "runtime.promotions.run_promotions_operational_cycle._run_completed_preflight_probe",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id="landed-dataset-run",
                    as_of_date=settings.as_of_date.isoformat(),
                ),
            ), patch.object(
                StorePredictionPublisher,
                "publish",
                new=_build_publish_without_zero_fail(
                    artifact_paths=artifact_paths,
                    original_publish=original_publish,
                ),
            ):
                artifacts = run_operational_cycle(
                    settings=settings,
                    run_id="landed-dataset-run",
                    score_run_id="landed-dataset-run-score",
                    decision_surface_run_id="landed-dataset-run-decision-surface",
                    minimum_cohort_sample_size=1,
                    similarity_threshold=0.50,
                    archetype_confidence_floor=0.35,
                    row_model_confidence_floor=0.35,
                    extraction_provider=_extract_from_landed_parquet,
                )
            dataset_manifest = json.loads(
                Path(artifacts.dataset_manifest_path).read_text(encoding="utf-8")
            )
            operational_manifest = json.loads(
                Path(artifacts.manifest_path).read_text(encoding="utf-8")
            )

            self.assertEqual(dataset_manifest["row_count"], len(completed_frame.index))
            self.assertEqual(
                operational_manifest["completed_extraction"]["fetch_mode"],
                "landed_batch_fetch",
            )
            self.assertEqual(
                operational_manifest["completed_extraction"]["batch_count"],
                2,
            )
            self.assertEqual(
                operational_manifest["completed_extraction"]["chunk_mode"],
                "chunked_fetch",
            )


