from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import shutil
import time
from typing import Callable

import pandas as pd

from data.promotions.completed_base_extractor import PromotionCompletedBaseExtractor
from data.promotions.completed_transaction_aggregates_extractor import (
    PromotionCompletedTransactionAggregatesExtractor,
)
from data.promotions.completed_window_aggregates_extractor import (
    PromotionCompletedWindowAggregatesExtractor,
)
from data.promotions.chunked_extraction_writer import PromotionChunkedExtractionWriter
from data.promotions.extracted_dataset_writer import PromotionExtractionWriter
from data.promotions.mssql_query_executor import PromotionQueryExecutor
from data.promotions.promotion_base_extractor import (
    PromotionExtractionManifest,
    PromotionExtractionTelemetry,
    write_extraction_observability,
    write_rendered_query_artifacts,
)
from data.promotions.sql import (
    PromotionBaseQueryOptions,
    PromotionCompletedBatchSlice,
    render_promotion_base_query,
)
from runtime.promotions.config import PromotionArtifactPaths, PromotionPipelineSettings
from state.promotions.datasets.completed_dataset_joiner import (
    PromotionCompletedDatasetJoiner,
)


@dataclass(frozen=True)
class PromotionCompletedBatchArtifact:
    batch_index: int
    batch_run_id: str
    row_start: int
    row_end: int
    row_count: int
    candidate_promotion_row_count: int | None
    base_path: str
    manifest_path: str
    completion_marker_path: str
    telemetry_json_path: str | None
    telemetry_csv_path: str | None
    diagnostics_summary_json_path: str | None
    diagnostics_summary_txt_path: str | None
    fetch_mode: str
    chunk_mode: str
    chunk_count: int
    completed_chunk_count: int
    cumulative_rows_written: int
    resume_state: str
    skipped_due_to_existing_completion: bool
    rebuilt: bool
    promotion_row_key_checksum_sha256: str | None
    manifest: dict[str, object]


@dataclass(frozen=True)
class PromotionCompletedPartitionBatchResult:
    frame: pd.DataFrame
    base_path: str
    manifest_path: str
    rendered_sql_path: str | None
    rendered_sql_parameters_path: str | None
    telemetry_json_path: str | None
    telemetry_csv_path: str | None
    diagnostics_summary_json_path: str | None
    diagnostics_summary_txt_path: str | None
    candidate_promotion_row_count: int | None
    manifest: dict[str, object]
    extraction_mode: str
    partition_strategy: str | None
    partition_count: int | None
    partition_index: int | None
    fetch_mode: str
    chunk_mode: str
    chunk_count: int
    completed_chunk_count: int
    cumulative_rows_written: int
    batch_count: int
    finalized_batch_count: int
    resumed_batch_count: int
    rebuilt_batch_count: int
    total_landed_rows: int
    completion_state: str | None
    partition_completion_state: str | None
    resume_state: str | None
    skipped_due_to_existing_completion: bool
    partition_progress_path: str | None
    partition_completion_marker_path: str | None
    batch_artifacts: tuple[PromotionCompletedBatchArtifact, ...]


@dataclass(frozen=True)
class _ExistingBatchValidation:
    artifact: PromotionCompletedBatchArtifact | None
    outputs_exist: bool
    rebuild_reason: str | None


class PromotionCompletedPartitionArtifactResolutionError(RuntimeError):
    """Raised when a finalized completed partition cannot be resolved or rebuilt safely."""


def execute_completed_partition_landed_batches(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    executor: PromotionQueryExecutor,
    query_options: PromotionBaseQueryOptions | None = None,
    progress_callback: Callable[[str], None] | None = None,
    base_extractor: PromotionCompletedBaseExtractor | None = None,
    window_aggregates_extractor: PromotionCompletedWindowAggregatesExtractor | None = None,
    transaction_aggregates_extractor: PromotionCompletedTransactionAggregatesExtractor | None = None,
    dataset_joiner: PromotionCompletedDatasetJoiner | None = None,
) -> PromotionCompletedPartitionBatchResult:
    resolved_query_options = query_options or PromotionBaseQueryOptions()
    if resolved_query_options.completed_batch is not None:
        raise ValueError("completed_batch is owned by the landed-batch runner and must not be pre-set.")
    resolved_base_extractor = base_extractor or PromotionCompletedBaseExtractor(executor=executor)
    resolved_window_aggregates_extractor = (
        window_aggregates_extractor
        or PromotionCompletedWindowAggregatesExtractor(executor=executor)
    )
    resolved_transaction_aggregates_extractor = (
        transaction_aggregates_extractor
        or PromotionCompletedTransactionAggregatesExtractor(executor=executor)
    )
    resolved_dataset_joiner = dataset_joiner or PromotionCompletedDatasetJoiner()

    telemetry = PromotionExtractionTelemetry(
        run_id=run_id,
        selection_mode="completed",
        as_of_date=settings.as_of_date.isoformat(),
        advice_source_table=settings.sql.promotion_advice_table,
        realised_sales_source_table=settings.sql.pwlogd_table,
        connect_timeout_seconds=settings.sql.connect_timeout_seconds,
        connect_retry_attempts=settings.sql.connect_retry_attempts,
        connect_retry_backoff_seconds=settings.sql.connect_retry_backoff_seconds,
        query_timeout_seconds=settings.sql.query_timeout_seconds,
        fetch_mode="landed_batch_fetch",
        chunk_mode=(
            "chunked_fetch"
            if settings.completed_extraction_runtime.enable_chunked_fetch
            else "full_fetch"
        ),
        fetch_chunk_row_count=(
            settings.completed_extraction_runtime.chunk_row_count
            if settings.completed_extraction_runtime.enable_chunked_fetch
            else None
        ),
        completed_sales_history_start_date=(
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
        ),
        staged_extraction_enabled=True,
        completed_extraction_stage_mode="completed_staged_enrichment_v1",
        extraction_stage="completed_partition_execution",
    )
    if resolved_query_options.completed_partition is not None:
        telemetry.partition_strategy = resolved_query_options.completed_partition.strategy
        telemetry.partition_count = resolved_query_options.completed_partition.partition_count
        telemetry.partition_index = resolved_query_options.completed_partition.partition_index

    progress_path = settings.artifacts.extraction_partition_progress_path(run_id)
    completion_path = settings.artifacts.extraction_partition_completion_path(run_id)
    telemetry.output_partition_progress_path = str(progress_path)
    telemetry.output_partition_completion_path = str(completion_path)
    try:
        telemetry.current_sql_subphase = "SQL query render in progress"
        telemetry.query_render_started_at_utc = _utc_now_iso()
        if progress_callback is not None:
            progress_callback("planning landed completed batches")
        rendered_query = render_promotion_base_query(
            settings=settings,
            selection_mode="completed",
            query_options=resolved_query_options,
        )
        telemetry.query_render_completed_at_utc = _utc_now_iso()
        telemetry.query_version = rendered_query.query_version
        telemetry.extraction_mode = rendered_query.extraction_mode
        telemetry.rendered_query_parameter_summary = dict(rendered_query.parameters)
        telemetry.diagnostic_filter_summary = dict(rendered_query.diagnostic_filter_summary)
        telemetry.estimated_window_summary = dict(rendered_query.estimated_window_summary)
        rendered_artifacts = write_rendered_query_artifacts(
            run_id=run_id,
            artifact_paths=settings.artifacts,
            rendered_query=rendered_query,
        )
        telemetry.rendered_sql_path = rendered_artifacts.sql_path
        telemetry.rendered_sql_parameters_path = rendered_artifacts.parameters_path

        existing_partition = _try_load_existing_finalized_partition_artifact(
            settings=settings,
            run_id=run_id,
            query_options=resolved_query_options,
        )
        if existing_partition is not None:
            if settings.completed_extraction_runtime.resume_completed_partitions:
                if progress_callback is not None:
                    progress_callback(
                        "landed batch reuse enabled | skipping finalized partition artifact"
                    )
                return existing_partition
            _cleanup_partition_and_batch_outputs(settings.artifacts, run_id)
            telemetry.resume_state = "restart_completed_partition"
        else:
            telemetry.resume_state = (
                "resume_incomplete_partition"
                if progress_path.exists() or _any_child_batch_outputs_exist(settings.artifacts, run_id)
                else "new_partition"
            )

        telemetry.current_sql_subphase = "candidate promotion row count probe"
        if progress_callback is not None:
            progress_callback("probing candidate rows for landed batch plan")
        candidate_count_result = executor.fetch_dataframe(
            sql=rendered_query.candidate_count_sql,
            parameters=rendered_query.parameters,
        )
        candidate_promotion_row_count = _extract_candidate_count(candidate_count_result.frame)
        telemetry.candidate_promotion_row_count = candidate_promotion_row_count
        batch_count = max(
            1,
            math.ceil(
                candidate_promotion_row_count
                / settings.completed_extraction_runtime.batch_row_count
            ),
        )
        telemetry.batch_count = batch_count
        _write_partition_progress(
            artifact_paths=settings.artifacts,
            run_id=run_id,
            fetch_mode=telemetry.fetch_mode,
            chunk_mode=telemetry.chunk_mode,
            batch_row_count=settings.completed_extraction_runtime.batch_row_count,
            batch_count=batch_count,
            finalized_batch_count=0,
            resumed_batch_count=0,
            rebuilt_batch_count=0,
            total_landed_rows=0,
            chunk_count=0,
            completed_chunk_count=0,
            cumulative_rows_written=0,
            partition_completion_state="in_progress",
            completion_state="in_progress",
            resume_state=telemetry.resume_state or "new_partition",
            skipped_due_to_existing_completion=False,
        )

        batch_artifacts: list[PromotionCompletedBatchArtifact] = []
        resumed_batch_count = 0
        rebuilt_batch_count = 0
        finalized_batch_count = 0
        telemetry.sql_connection_started_at_utc = _utc_now_iso()
        telemetry.query_execution_started_at_utc = telemetry.sql_connection_started_at_utc
        telemetry.fetch_started_at_utc = telemetry.sql_connection_started_at_utc
        for batch_index in range(1, batch_count + 1):
            batch_slice = _build_completed_batch_slice(
                batch_index=batch_index,
                batch_row_count=settings.completed_extraction_runtime.batch_row_count,
            )
            validation = _validate_existing_batch_artifact(
                artifact_paths=settings.artifacts,
                partition_run_id=run_id,
                batch_slice=batch_slice,
            )
            if validation.artifact is not None:
                resumed_batch_count += 1
                finalized_batch_count += 1
                batch_artifacts.append(validation.artifact)
                if telemetry.resume_state == "new_partition":
                    telemetry.resume_state = "resume_incomplete_partition"
                if progress_callback is not None:
                    progress_callback(
                        "batch "
                        f"{batch_index}/{batch_count} | reuse finalized landed batch | "
                        f"rows {validation.artifact.row_count}"
                    )
            else:
                if validation.outputs_exist:
                    rebuilt_batch_count += 1
                    telemetry.resume_state = "resume_incomplete_partition"
                    if progress_callback is not None and validation.rebuild_reason is not None:
                        progress_callback(
                            "batch "
                            f"{batch_index}/{batch_count} | rebuild stale landed batch | "
                            f"reason {validation.rebuild_reason}"
                        )
                batch_artifact = _execute_completed_batch(
                    settings=settings,
                    run_id=run_id,
                    batch_slice=batch_slice,
                    base_query_options=resolved_query_options,
                    progress_callback=progress_callback,
                    rebuilt=validation.outputs_exist,
                    base_extractor=resolved_base_extractor,
                    window_aggregates_extractor=resolved_window_aggregates_extractor,
                    transaction_aggregates_extractor=resolved_transaction_aggregates_extractor,
                    dataset_joiner=resolved_dataset_joiner,
                )
                finalized_batch_count += 1
                batch_artifacts.append(batch_artifact)

            _write_partition_progress(
                artifact_paths=settings.artifacts,
                run_id=run_id,
                fetch_mode=telemetry.fetch_mode,
                chunk_mode=telemetry.chunk_mode,
                batch_row_count=settings.completed_extraction_runtime.batch_row_count,
                batch_count=batch_count,
                finalized_batch_count=finalized_batch_count,
                resumed_batch_count=resumed_batch_count,
                rebuilt_batch_count=rebuilt_batch_count,
                total_landed_rows=sum(artifact.row_count for artifact in batch_artifacts),
                chunk_count=sum(artifact.chunk_count for artifact in batch_artifacts),
                completed_chunk_count=sum(
                    artifact.completed_chunk_count for artifact in batch_artifacts
                ),
                cumulative_rows_written=sum(
                    artifact.cumulative_rows_written for artifact in batch_artifacts
                ),
                partition_completion_state="in_progress",
                completion_state="in_progress",
                resume_state=telemetry.resume_state or "new_partition",
                skipped_due_to_existing_completion=False,
            )

        telemetry.fetch_completed_at_utc = _utc_now_iso()
        telemetry.query_execution_completed_at_utc = telemetry.fetch_completed_at_utc
        telemetry.sql_connection_completed_at_utc = telemetry.fetch_completed_at_utc
        telemetry.current_sql_subphase = "combining finalized landed batch artifacts"
        telemetry.dataframe_write_started_at_utc = _utc_now_iso()
        if progress_callback is not None:
            progress_callback(
                "combining finalized landed batch artifacts into the completed partition parquet"
            )
        combined_frame = _combine_batch_frames(batch_artifacts)
        combined_manifest = _build_partition_manifest(
            settings=settings,
            run_id=run_id,
            query_version="promotion_completed_enriched_v1",
            frame=combined_frame,
            candidate_promotion_row_count=candidate_promotion_row_count,
            query_options=resolved_query_options,
            chunk_mode=telemetry.chunk_mode,
            batch_count=batch_count,
            finalized_batch_count=finalized_batch_count,
            resumed_batch_count=resumed_batch_count,
            rebuilt_batch_count=rebuilt_batch_count,
            batch_artifacts=batch_artifacts,
            resume_state=telemetry.resume_state or "new_partition",
        )
        persisted = PromotionExtractionWriter().write(
            base_frame=combined_frame,
            manifest=combined_manifest,
            artifact_paths=settings.artifacts,
        )
        telemetry.output_parquet_path = str(persisted.base_path)
        telemetry.output_manifest_path = str(persisted.manifest_path)
        telemetry.row_count = combined_manifest.row_count
        telemetry.column_count = combined_manifest.column_count
        telemetry.duplicate_promotion_row_keys = combined_manifest.duplicate_promotion_row_keys
        telemetry.chunk_count = combined_manifest.chunk_count
        telemetry.completed_chunk_count = combined_manifest.completed_chunk_count
        telemetry.cumulative_rows_written = combined_manifest.cumulative_rows_written
        telemetry.batch_count = combined_manifest.batch_count
        telemetry.finalized_batch_count = combined_manifest.finalized_batch_count
        telemetry.resumed_batch_count = combined_manifest.resumed_batch_count
        telemetry.rebuilt_batch_count = combined_manifest.rebuilt_batch_count
        telemetry.total_landed_rows = combined_manifest.total_landed_rows
        telemetry.completion_state = combined_manifest.completion_state
        telemetry.partition_completion_state = combined_manifest.partition_completion_state
        telemetry.resume_state = combined_manifest.resume_state
        telemetry.skipped_due_to_existing_completion = False
        telemetry.promotion_row_key_checksum_sha256 = (
            combined_manifest.promotion_row_key_checksum_sha256
        )
        telemetry.query_version = combined_manifest.query_version
        telemetry.completed_extraction_stage_mode = (
            combined_manifest.completed_extraction_stage_mode
        )
        telemetry.extraction_stage = combined_manifest.extraction_stage
        telemetry.extracted_at_utc = combined_manifest.extracted_at_utc
        telemetry.dataframe_write_completed_at_utc = _utc_now_iso()
        telemetry.mark_success()
        observability = write_extraction_observability(
            telemetry=telemetry,
            settings=settings,
            artifact_paths=settings.artifacts,
        )
        _write_partition_completion(
            artifact_paths=settings.artifacts,
            run_id=run_id,
            manifest=combined_manifest,
            batch_row_count=settings.completed_extraction_runtime.batch_row_count,
            base_path=persisted.base_path,
            manifest_path=persisted.manifest_path,
        )
        _write_partition_progress(
            artifact_paths=settings.artifacts,
            run_id=run_id,
            fetch_mode=combined_manifest.fetch_mode,
            chunk_mode=combined_manifest.chunk_mode,
            batch_row_count=settings.completed_extraction_runtime.batch_row_count,
            batch_count=combined_manifest.batch_count,
            finalized_batch_count=combined_manifest.finalized_batch_count,
            resumed_batch_count=combined_manifest.resumed_batch_count,
            rebuilt_batch_count=combined_manifest.rebuilt_batch_count,
            total_landed_rows=combined_manifest.total_landed_rows,
            chunk_count=combined_manifest.chunk_count,
            completed_chunk_count=combined_manifest.completed_chunk_count,
            cumulative_rows_written=combined_manifest.cumulative_rows_written,
            partition_completion_state="finalized",
            completion_state=combined_manifest.completion_state or "finalized",
            resume_state=combined_manifest.resume_state or "new_partition",
            skipped_due_to_existing_completion=False,
        )
        return PromotionCompletedPartitionBatchResult(
            frame=combined_frame,
            base_path=str(persisted.base_path),
            manifest_path=str(persisted.manifest_path),
            rendered_sql_path=telemetry.rendered_sql_path,
            rendered_sql_parameters_path=telemetry.rendered_sql_parameters_path,
            telemetry_json_path=observability.telemetry_json_path,
            telemetry_csv_path=observability.telemetry_csv_path,
            diagnostics_summary_json_path=observability.diagnostics_summary_json_path,
            diagnostics_summary_txt_path=observability.diagnostics_summary_txt_path,
            candidate_promotion_row_count=candidate_promotion_row_count,
            manifest=combined_manifest.to_dict(),
            extraction_mode=telemetry.extraction_mode,
            partition_strategy=telemetry.partition_strategy,
            partition_count=telemetry.partition_count,
            partition_index=telemetry.partition_index,
            fetch_mode=combined_manifest.fetch_mode,
            chunk_mode=combined_manifest.chunk_mode,
            chunk_count=combined_manifest.chunk_count,
            completed_chunk_count=combined_manifest.completed_chunk_count,
            cumulative_rows_written=combined_manifest.cumulative_rows_written,
            batch_count=combined_manifest.batch_count,
            finalized_batch_count=combined_manifest.finalized_batch_count,
            resumed_batch_count=combined_manifest.resumed_batch_count,
            rebuilt_batch_count=combined_manifest.rebuilt_batch_count,
            total_landed_rows=combined_manifest.total_landed_rows,
            completion_state=combined_manifest.completion_state,
            partition_completion_state=combined_manifest.partition_completion_state,
            resume_state=combined_manifest.resume_state,
            skipped_due_to_existing_completion=False,
            partition_progress_path=str(progress_path),
            partition_completion_marker_path=str(completion_path),
            batch_artifacts=tuple(batch_artifacts),
        )
    except Exception as error:
        telemetry.mark_failure(error)
        _write_partition_progress(
            artifact_paths=settings.artifacts,
            run_id=run_id,
            fetch_mode=telemetry.fetch_mode,
            chunk_mode=telemetry.chunk_mode,
            batch_row_count=settings.completed_extraction_runtime.batch_row_count,
            batch_count=telemetry.batch_count,
            finalized_batch_count=telemetry.finalized_batch_count,
            resumed_batch_count=telemetry.resumed_batch_count,
            rebuilt_batch_count=telemetry.rebuilt_batch_count,
            total_landed_rows=telemetry.total_landed_rows,
            chunk_count=telemetry.chunk_count,
            completed_chunk_count=telemetry.completed_chunk_count,
            cumulative_rows_written=telemetry.cumulative_rows_written,
            partition_completion_state="failed_incomplete",
            completion_state="failed_incomplete",
            resume_state=telemetry.resume_state or "new_partition",
            skipped_due_to_existing_completion=False,
            failure_message=str(error),
        )
        setattr(error, "promotion_extraction_telemetry", telemetry)
        raise


def _execute_completed_batch(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    batch_slice: PromotionCompletedBatchSlice,
    base_query_options: PromotionBaseQueryOptions,
    progress_callback: Callable[[str], None] | None,
    rebuilt: bool,
    base_extractor: PromotionCompletedBaseExtractor,
    window_aggregates_extractor: PromotionCompletedWindowAggregatesExtractor,
    transaction_aggregates_extractor: PromotionCompletedTransactionAggregatesExtractor,
    dataset_joiner: PromotionCompletedDatasetJoiner,
) -> PromotionCompletedBatchArtifact:
    batch_run_id = _completed_batch_run_id(run_id, batch_slice.batch_index)
    batch_query_options = replace(base_query_options, completed_batch=batch_slice)
    _cleanup_batch_stage_outputs(settings.artifacts, batch_run_id)
    completed_sales_history_start_date = (
        settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
    )

    batch_telemetry: PromotionExtractionTelemetry | None = None
    observability = None
    try:
        stage_artifacts = []
        if progress_callback is not None:
            progress_callback(
                "batch "
                f"{batch_slice.batch_index} | row_window {batch_slice.row_start}-{batch_slice.row_end} | staged completed extraction"
            )
            progress_callback(
                f"batch {batch_slice.batch_index} | completed_sales_history_start_date: {completed_sales_history_start_date}"
            )
        base_stage_run_id = _completed_batch_stage_run_id(batch_run_id, "base")
        if progress_callback is not None:
            progress_callback(
                f"batch {batch_slice.batch_index} | stage_start: completed_base"
            )
        base_started_at = time.perf_counter()
        try:
            base_artifact = base_extractor.extract_stage(
                settings=settings,
                run_id=base_stage_run_id,
                query_options=batch_query_options,
                phase_callback=_batch_progress_callback(progress_callback, batch_slice.batch_index),
            )
        except Exception as error:
            _annotate_completed_stage_failure(
                error=error,
                settings=settings,
                stage_name="completed_base",
                stage_run_id=base_stage_run_id,
                batch_run_id=batch_run_id,
                as_of_date=settings.as_of_date.isoformat(),
                completed_sales_history_start_date=completed_sales_history_start_date,
            )
            if progress_callback is not None:
                progress_callback(
                    f"batch {batch_slice.batch_index} | stage_failed: completed_base | elapsed_seconds: {time.perf_counter() - base_started_at:.3f}"
                )
            raise
        if progress_callback is not None:
            progress_callback(
                "batch "
                f"{batch_slice.batch_index} | stage_finished: completed_base | rows: {base_artifact.row_count} | "
                f"elapsed_seconds: {time.perf_counter() - base_started_at:.3f} | manifest_path: {base_artifact.manifest_path}"
            )
        stage_artifacts.append(base_artifact)
        window_stage_run_id = _completed_batch_stage_run_id(batch_run_id, "window-aggregates")
        if progress_callback is not None:
            progress_callback(
                f"batch {batch_slice.batch_index} | stage_start: completed_window_aggregates"
            )
        window_started_at = time.perf_counter()
        try:
            window_artifact = window_aggregates_extractor.extract_stage(
                settings=settings,
                run_id=window_stage_run_id,
                base_frame=base_artifact.frame,
                phase_callback=_batch_progress_callback(progress_callback, batch_slice.batch_index),
            )
        except Exception as error:
            _annotate_completed_stage_failure(
                error=error,
                settings=settings,
                stage_name="completed_window_aggregates",
                stage_run_id=window_stage_run_id,
                batch_run_id=batch_run_id,
                as_of_date=settings.as_of_date.isoformat(),
                completed_sales_history_start_date=completed_sales_history_start_date,
            )
            if progress_callback is not None:
                progress_callback(
                    "batch "
                    f"{batch_slice.batch_index} | stage_failed: completed_window_aggregates | "
                    f"elapsed_seconds: {time.perf_counter() - window_started_at:.3f}"
                )
            raise
        if progress_callback is not None:
            progress_callback(
                "batch "
                f"{batch_slice.batch_index} | stage_finished: completed_window_aggregates | rows: {window_artifact.row_count} | "
                f"elapsed_seconds: {time.perf_counter() - window_started_at:.3f} | manifest_path: {window_artifact.manifest_path}"
            )
        stage_artifacts.append(window_artifact)
        transaction_stage_run_id = _completed_batch_stage_run_id(batch_run_id, "transaction-aggregates")
        if progress_callback is not None:
            progress_callback(
                f"batch {batch_slice.batch_index} | stage_start: completed_transaction_aggregates"
            )
        transaction_started_at = time.perf_counter()
        try:
            transaction_artifact = transaction_aggregates_extractor.extract_stage(
                settings=settings,
                run_id=transaction_stage_run_id,
                base_frame=base_artifact.frame,
                phase_callback=_batch_progress_callback(progress_callback, batch_slice.batch_index),
            )
        except Exception as error:
            _annotate_completed_stage_failure(
                error=error,
                settings=settings,
                stage_name="completed_transaction_aggregates",
                stage_run_id=transaction_stage_run_id,
                batch_run_id=batch_run_id,
                as_of_date=settings.as_of_date.isoformat(),
                completed_sales_history_start_date=completed_sales_history_start_date,
            )
            if progress_callback is not None:
                progress_callback(
                    "batch "
                    f"{batch_slice.batch_index} | stage_failed: completed_transaction_aggregates | "
                    f"elapsed_seconds: {time.perf_counter() - transaction_started_at:.3f}"
                )
            raise
        if progress_callback is not None:
            progress_callback(
                "batch "
                f"{batch_slice.batch_index} | stage_finished: completed_transaction_aggregates | rows: {transaction_artifact.row_count} | "
                f"elapsed_seconds: {time.perf_counter() - transaction_started_at:.3f} | manifest_path: {transaction_artifact.manifest_path}"
            )
        stage_artifacts.append(transaction_artifact)
        assembled_at_utc = _utc_now_iso()
        if progress_callback is not None:
            progress_callback(
                f"batch {batch_slice.batch_index} | stage_start: completed_final_assembler"
            )
        assembler_started_at = time.perf_counter()
        try:
            assembled_frame = dataset_joiner.join(
                run_id=batch_run_id,
                as_of_date=settings.as_of_date.isoformat(),
                query_version="promotion_completed_enriched_v1",
                advice_source_table_name=settings.sql.promotion_advice_table,
                realised_sales_source_table_name=settings.sql.pwlogd_table,
                base_frame=base_artifact.frame,
                window_aggregate_frame=window_artifact.frame,
                transaction_aggregate_frame=transaction_artifact.frame,
                extracted_at_utc=assembled_at_utc,
            )
        except Exception as error:
            _annotate_completed_stage_failure(
                error=error,
                settings=settings,
                stage_name="completed_final_assembler",
                stage_run_id=batch_run_id,
                batch_run_id=batch_run_id,
                as_of_date=settings.as_of_date.isoformat(),
                completed_sales_history_start_date=completed_sales_history_start_date,
            )
            if progress_callback is not None:
                progress_callback(
                    "batch "
                    f"{batch_slice.batch_index} | stage_failed: completed_final_assembler | "
                    f"elapsed_seconds: {time.perf_counter() - assembler_started_at:.3f}"
                )
            raise
        if progress_callback is not None:
            progress_callback(
                "batch "
                f"{batch_slice.batch_index} | stage_finished: completed_final_assembler | rows: {int(len(assembled_frame.index))} | "
                f"elapsed_seconds: {time.perf_counter() - assembler_started_at:.3f}"
            )
        writer = PromotionChunkedExtractionWriter(
            artifact_paths=settings.artifacts,
            run_id=batch_run_id,
            stage_temp_chunk_files=settings.completed_extraction_runtime.stage_temp_chunk_files,
        )
        writer.start_partition(
            fetch_mode="landed_batch_fetch",
            chunk_row_count=max(1, int(len(assembled_frame.index) or 1)),
        )
        writer.write_chunk(assembled_frame, chunk_index=1)
        finalized_manifest = _build_batch_manifest(
            settings=settings,
            batch_run_id=batch_run_id,
            frame=assembled_frame,
            candidate_promotion_row_count=base_artifact.row_count,
            stage_artifacts=stage_artifacts,
            rebuilt=rebuilt,
        )
        persisted = writer.finalize(manifest=finalized_manifest)
        batch_telemetry = PromotionExtractionTelemetry(
            run_id=batch_run_id,
            selection_mode="completed",
            as_of_date=settings.as_of_date.isoformat(),
            query_version=finalized_manifest.query_version,
            extraction_mode="live_sql",
            advice_source_table=settings.sql.promotion_advice_table,
            realised_sales_source_table=settings.sql.pwlogd_table,
            connect_timeout_seconds=settings.sql.connect_timeout_seconds,
            connect_retry_attempts=settings.sql.connect_retry_attempts,
            connect_retry_backoff_seconds=settings.sql.connect_retry_backoff_seconds,
            query_timeout_seconds=settings.sql.query_timeout_seconds,
            fetch_mode=finalized_manifest.fetch_mode,
            chunk_mode=finalized_manifest.chunk_mode,
            chunk_count=finalized_manifest.chunk_count,
            completed_chunk_count=finalized_manifest.completed_chunk_count,
            cumulative_rows_written=finalized_manifest.cumulative_rows_written,
            batch_count=finalized_manifest.batch_count,
            finalized_batch_count=finalized_manifest.finalized_batch_count,
            resumed_batch_count=finalized_manifest.resumed_batch_count,
            rebuilt_batch_count=finalized_manifest.rebuilt_batch_count,
            total_landed_rows=finalized_manifest.total_landed_rows,
            completion_state=finalized_manifest.completion_state,
            partition_completion_state=finalized_manifest.partition_completion_state,
            resume_state=finalized_manifest.resume_state,
            skipped_due_to_existing_completion=False,
            candidate_promotion_row_count=base_artifact.row_count,
            row_count=int(len(assembled_frame.index)),
            column_count=int(len(assembled_frame.columns)),
            duplicate_promotion_row_keys=int(
                assembled_frame["promotion_row_key"].duplicated().sum()
                if "promotion_row_key" in assembled_frame.columns
                else 0
            ),
            extracted_at_utc=assembled_at_utc,
            dataframe_write_started_at_utc=assembled_at_utc,
            dataframe_write_completed_at_utc=_utc_now_iso(),
            promotion_row_key_checksum_sha256=finalized_manifest.promotion_row_key_checksum_sha256,
            completed_sales_history_start_date=finalized_manifest.completed_sales_history_start_date,
            staged_extraction_enabled=True,
            completed_extraction_stage_mode=finalized_manifest.completed_extraction_stage_mode,
            extraction_stage=finalized_manifest.extraction_stage,
            diagnostic_filter_summary={
                "batch_index": batch_slice.batch_index,
                "row_start": batch_slice.row_start,
                "row_end": batch_slice.row_end,
                "staged_extraction_enabled": True,
            },
            estimated_window_summary={
                "completed_sales_history_start_date": finalized_manifest.completed_sales_history_start_date,
                "baseline_lookback_days": settings.windows.baseline_lookback_days,
                "short_baseline_days": settings.windows.short_baseline_days,
                "immediate_baseline_days": settings.windows.immediate_baseline_days,
                "post_promo_days": settings.windows.post_promo_days,
                "as_of_date": settings.as_of_date.isoformat(),
            },
        )

        batch_telemetry.output_parquet_path = str(persisted.base_path)
        batch_telemetry.output_manifest_path = str(persisted.manifest_path)
        batch_telemetry.output_partition_progress_path = str(persisted.progress_path)
        batch_telemetry.output_partition_completion_path = str(persisted.completion_marker_path)
        batch_telemetry.mark_success()
        observability = write_extraction_observability(
            telemetry=batch_telemetry,
            settings=settings,
            artifact_paths=settings.artifacts,
        )
        return PromotionCompletedBatchArtifact(
            batch_index=batch_slice.batch_index,
            batch_run_id=batch_run_id,
            row_start=batch_slice.row_start,
            row_end=batch_slice.row_end,
            row_count=finalized_manifest.row_count,
            candidate_promotion_row_count=finalized_manifest.candidate_promotion_row_count,
            base_path=str(persisted.base_path),
            manifest_path=str(persisted.manifest_path),
            completion_marker_path=str(persisted.completion_marker_path),
            telemetry_json_path=(
                observability.telemetry_json_path if observability is not None else None
            ),
            telemetry_csv_path=(
                observability.telemetry_csv_path if observability is not None else None
            ),
            diagnostics_summary_json_path=(
                observability.diagnostics_summary_json_path if observability is not None else None
            ),
            diagnostics_summary_txt_path=(
                observability.diagnostics_summary_txt_path if observability is not None else None
            ),
            fetch_mode=finalized_manifest.fetch_mode,
            chunk_mode=finalized_manifest.chunk_mode,
            chunk_count=finalized_manifest.chunk_count,
            completed_chunk_count=finalized_manifest.completed_chunk_count,
            cumulative_rows_written=finalized_manifest.cumulative_rows_written,
            resume_state=finalized_manifest.resume_state or "new_batch",
            skipped_due_to_existing_completion=False,
            rebuilt=rebuilt,
            promotion_row_key_checksum_sha256=finalized_manifest.promotion_row_key_checksum_sha256,
            manifest=finalized_manifest.to_dict(),
        )
    except Exception as error:
        if batch_telemetry is not None:
            batch_telemetry.partition_completion_state = "failed_incomplete"
            batch_telemetry.completion_state = "failed_incomplete"
            batch_telemetry.resume_state = (
                "rebuilt_incomplete_batch" if rebuilt else "new_batch"
            )
            batch_telemetry.mark_failure(error)
            batch_observability = write_extraction_observability(
                telemetry=batch_telemetry,
                settings=settings,
                artifact_paths=settings.artifacts,
            )
            setattr(error, "extraction_telemetry_json_path", batch_observability.telemetry_json_path)
            setattr(error, "extraction_telemetry_csv_path", batch_observability.telemetry_csv_path)
            setattr(
                error,
                "sql_diagnostics_summary_json_path",
                batch_observability.diagnostics_summary_json_path,
            )
            setattr(
                error,
                "sql_diagnostics_summary_txt_path",
                batch_observability.diagnostics_summary_txt_path,
            )
        raise


def _build_batch_manifest(
    *,
    settings: PromotionPipelineSettings,
    batch_run_id: str,
    frame: pd.DataFrame,
    candidate_promotion_row_count: int,
    stage_artifacts: list[object],
    rebuilt: bool,
) -> PromotionExtractionManifest:
    return PromotionExtractionManifest(
        run_id=batch_run_id,
        selection_mode="completed",
        query_version="promotion_completed_enriched_v1",
        as_of_date=settings.as_of_date.isoformat(),
        extracted_at_utc=_utc_now_iso(),
        row_count=int(len(frame.index)),
        column_count=int(len(frame.columns)),
        duplicate_promotion_row_keys=int(
            frame["promotion_row_key"].duplicated().sum()
            if "promotion_row_key" in frame.columns
            else 0
        ),
        advice_source_table=settings.sql.promotion_advice_table,
        realised_sales_source_table=settings.sql.pwlogd_table,
        columns=tuple(str(column_name) for column_name in frame.columns),
        extraction_mode="live_sql",
        fetch_mode="landed_batch_fetch",
        chunk_mode=(
            "chunked_fetch"
            if settings.completed_extraction_runtime.enable_chunked_fetch
            else "full_fetch"
        ),
        chunk_count=sum(int(getattr(artifact, "chunk_count", 0) or 0) for artifact in stage_artifacts),
        completed_chunk_count=sum(
            int(getattr(artifact, "completed_chunk_count", 0) or 0)
            for artifact in stage_artifacts
        ),
        cumulative_rows_written=sum(
            int(getattr(artifact, "cumulative_rows_written", 0) or 0)
            for artifact in stage_artifacts
        ),
        batch_count=1,
        finalized_batch_count=1,
        resumed_batch_count=0,
        rebuilt_batch_count=(1 if rebuilt else 0),
        total_landed_rows=int(len(frame.index)),
        completion_state="finalized",
        partition_completion_state="finalized",
        resume_state=("rebuilt_incomplete_batch" if rebuilt else "new_batch"),
        skipped_due_to_existing_completion=False,
        promotion_row_key_checksum_sha256=_compute_promotion_row_key_checksum(frame),
        completed_sales_history_start_date=(
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
        ),
        staged_extraction_enabled=True,
        completed_extraction_stage_mode="completed_staged_enrichment_v1",
        extraction_stage="completed_assembled_batch",
        candidate_promotion_row_count=candidate_promotion_row_count,
        child_stage_manifest_paths=tuple(
            str(getattr(artifact, "manifest_path")) for artifact in stage_artifacts
        ),
        child_stage_parquet_paths=tuple(
            str(getattr(artifact, "base_path")) for artifact in stage_artifacts
        ),
    )


def _batch_progress_callback(
    progress_callback: Callable[[str], None] | None,
    batch_index: int,
) -> Callable[[str], None] | None:
    if progress_callback is None:
        return None
    return lambda message: progress_callback(f"batch {batch_index} | {message}")


def _completed_batch_stage_run_id(batch_run_id: str, stage_name: str) -> str:
    return f"{batch_run_id}-{stage_name}"


def _annotate_completed_stage_failure(
    *,
    error: Exception,
    settings: PromotionPipelineSettings,
    stage_name: str,
    stage_run_id: str,
    batch_run_id: str,
    as_of_date: str,
    completed_sales_history_start_date: str,
) -> None:
    manifests_run_root = settings.artifacts.manifests_run_root(stage_run_id)
    setattr(error, "selection_mode", "completed")
    setattr(error, "as_of_date", as_of_date)
    setattr(error, "completed_stage_failure_label", stage_name)
    setattr(error, "completed_batch_run_id", batch_run_id)
    setattr(error, "completed_batch_stage_run_id", stage_run_id)
    setattr(error, "completed_sales_history_start_date", completed_sales_history_start_date)
    setattr(error, "completed_stage_base_path", str(settings.artifacts.extracted_base_path(stage_run_id)))
    setattr(error, "completed_stage_manifest_path", str(settings.artifacts.extracted_manifest_path(stage_run_id)))
    setattr(error, "rendered_sql_path", str(manifests_run_root / "rendered_sql.sql"))
    setattr(
        error,
        "rendered_sql_parameters_path",
        str(manifests_run_root / "rendered_sql_parameters.json"),
    )
    if getattr(error, "extraction_telemetry_json_path", None) is None:
        setattr(
            error,
            "extraction_telemetry_json_path",
            str(settings.artifacts.extraction_telemetry_json_path(stage_run_id)),
        )
    if getattr(error, "extraction_telemetry_csv_path", None) is None:
        setattr(
            error,
            "extraction_telemetry_csv_path",
            str(settings.artifacts.extraction_telemetry_csv_path(stage_run_id)),
        )
    if getattr(error, "sql_diagnostics_summary_json_path", None) is None:
        setattr(
            error,
            "sql_diagnostics_summary_json_path",
            str(settings.artifacts.sql_diagnostics_summary_json_path(stage_run_id)),
        )
    if getattr(error, "sql_diagnostics_summary_txt_path", None) is None:
        setattr(
            error,
            "sql_diagnostics_summary_txt_path",
            str(settings.artifacts.sql_diagnostics_summary_txt_path(stage_run_id)),
        )


def _build_partition_manifest(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    query_version: str,
    frame: pd.DataFrame,
    candidate_promotion_row_count: int,
    query_options: PromotionBaseQueryOptions,
    chunk_mode: str,
    batch_count: int,
    finalized_batch_count: int,
    resumed_batch_count: int,
    rebuilt_batch_count: int,
    batch_artifacts: list[PromotionCompletedBatchArtifact],
    resume_state: str,
) -> PromotionExtractionManifest:
    extracted_at_utc = _utc_now_iso()
    return PromotionExtractionManifest(
        run_id=run_id,
        selection_mode="completed",
        query_version=query_version,
        as_of_date=settings.as_of_date.isoformat(),
        extracted_at_utc=extracted_at_utc,
        row_count=int(len(frame.index)),
        column_count=int(len(frame.columns)),
        duplicate_promotion_row_keys=int(
            frame["promotion_row_key"].duplicated().sum()
            if "promotion_row_key" in frame.columns
            else 0
        ),
        advice_source_table=settings.sql.promotion_advice_table,
        realised_sales_source_table=settings.sql.pwlogd_table,
        columns=tuple(str(column_name) for column_name in frame.columns),
        extraction_mode="live_sql",
        fetch_mode="landed_batch_fetch",
        chunk_mode=chunk_mode,
        chunk_count=sum(batch.chunk_count for batch in batch_artifacts),
        completed_chunk_count=sum(
            batch.completed_chunk_count for batch in batch_artifacts
        ),
        cumulative_rows_written=sum(
            batch.cumulative_rows_written for batch in batch_artifacts
        ),
        batch_count=batch_count,
        finalized_batch_count=finalized_batch_count,
        resumed_batch_count=resumed_batch_count,
        rebuilt_batch_count=rebuilt_batch_count,
        total_landed_rows=int(len(frame.index)),
        completion_state="finalized",
        partition_completion_state="finalized",
        resume_state=resume_state,
        skipped_due_to_existing_completion=False,
        promotion_row_key_checksum_sha256=_compute_promotion_row_key_checksum(frame),
        candidate_promotion_row_count=candidate_promotion_row_count,
        completed_sales_history_start_date=(
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
        ),
        staged_extraction_enabled=True,
        completed_extraction_stage_mode="completed_staged_enrichment_v1",
        extraction_stage="completed_partition_assembly",
        partition_strategy=(
            query_options.completed_partition.strategy
            if query_options.completed_partition is not None
            else None
        ),
        partition_count=(
            query_options.completed_partition.partition_count
            if query_options.completed_partition is not None
            else None
        ),
        partition_index=(
            query_options.completed_partition.partition_index
            if query_options.completed_partition is not None
            else None
        ),
        child_batch_manifest_paths=tuple(batch.manifest_path for batch in batch_artifacts),
        child_batch_parquet_paths=tuple(batch.base_path for batch in batch_artifacts),
    )


def _combine_batch_frames(
    batch_artifacts: list[PromotionCompletedBatchArtifact],
) -> pd.DataFrame:
    if not batch_artifacts:
        return pd.DataFrame()
    normalized_frames: list[pd.DataFrame] = []
    expected_columns: list[str] | None = None
    for artifact in batch_artifacts:
        frame = pd.read_parquet(artifact.base_path)
        current_columns = [str(column_name) for column_name in frame.columns]
        if expected_columns is None:
            expected_columns = current_columns
        elif current_columns != expected_columns:
            raise ValueError(
                "Completed landed batches produced a schema mismatch before partition combination."
            )
        normalized_frames.append(frame)
    return pd.concat(normalized_frames, ignore_index=True)


def load_existing_finalized_partition_artifact(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    query_options: PromotionBaseQueryOptions | None = None,
) -> PromotionCompletedPartitionBatchResult | None:
    return _try_load_existing_finalized_partition_artifact(
        settings=settings,
        run_id=run_id,
        query_options=query_options or PromotionBaseQueryOptions(),
    )


def _try_load_existing_finalized_partition_artifact(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    query_options: PromotionBaseQueryOptions,
) -> PromotionCompletedPartitionBatchResult | None:
    base_path = settings.artifacts.extracted_base_path(run_id)
    manifest_path = settings.artifacts.extracted_manifest_path(run_id)
    completion_path = settings.artifacts.extraction_partition_completion_path(run_id)
    if not manifest_path.exists() and not completion_path.exists() and not base_path.exists():
        return None
    if not completion_path.exists():
        return None
    completion_payload = _load_required_partition_payload(
        run_id=run_id,
        label="completion marker",
        path=completion_path,
    )
    if completion_payload.get("partition_completion_state") != "finalized":
        return None
    if not manifest_path.exists():
        raise _partition_resolution_error(
            run_id=run_id,
            message=(
                "Completed partition completion marker is finalized but the partition manifest is missing."
            ),
            base_path=base_path,
            manifest_path=manifest_path,
            completion_path=completion_path,
        )
    manifest_payload = _load_required_partition_payload(
        run_id=run_id,
        label="manifest",
        path=manifest_path,
    )
    if manifest_payload.get("fetch_mode") != "landed_batch_fetch":
        return None
    batch_count = int(
        manifest_payload.get("batch_count")
        or completion_payload.get("batch_count")
        or 0
    )
    if batch_count < 1:
        raise _partition_resolution_error(
            run_id=run_id,
            message=(
                "Completed partition manifest declares a finalized landed-batch artifact without a valid batch_count."
            ),
            base_path=base_path,
            manifest_path=manifest_path,
            completion_path=completion_path,
        )
    batch_artifacts: list[PromotionCompletedBatchArtifact] = []
    batch_row_count = int(completion_payload.get("batch_row_count", 0) or 0)
    batch_failures: list[str] = []
    for batch_index in range(1, batch_count + 1):
        batch_slice = _build_completed_batch_slice(
            batch_index=batch_index,
            batch_row_count=max(1, batch_row_count or batch_count),
        )
        validation = _validate_existing_batch_artifact(
            artifact_paths=settings.artifacts,
            partition_run_id=run_id,
            batch_slice=batch_slice,
        )
        if validation.artifact is None:
            batch_failures.append(
                (
                    f"batch {batch_index}: {validation.rebuild_reason}"
                    if validation.rebuild_reason is not None
                    else f"batch {batch_index}: finalized landed batch artifacts missing"
                )
            )
            continue
        batch_artifacts.append(validation.artifact)
    if batch_failures:
        raise _partition_resolution_error(
            run_id=run_id,
            message=(
                "Completed partition resume requested but the finalized partition cannot be rebuilt "
                f"from child landed batches: {'; '.join(batch_failures)}."
            ),
            base_path=base_path,
            manifest_path=manifest_path,
            completion_path=completion_path,
        )

    if base_path.exists():
        try:
            frame = pd.read_parquet(base_path)
        except Exception as error:
            raise _partition_resolution_error(
                run_id=run_id,
                message=(
                    "Completed partition parquet exists but could not be read during resume "
                    f"({type(error).__name__})."
                ),
                base_path=base_path,
                manifest_path=manifest_path,
                completion_path=completion_path,
            ) from error
    else:
        frame = _rebuild_finalized_partition_parquet(
            settings=settings,
            run_id=run_id,
            manifest_payload=manifest_payload,
            completion_payload=completion_payload,
            batch_artifacts=batch_artifacts,
        )

    _validate_resolved_partition_frame(
        run_id=run_id,
        frame=frame,
        manifest_payload=manifest_payload,
        base_path=base_path,
        manifest_path=manifest_path,
        completion_path=completion_path,
    )
    telemetry_json_path = settings.artifacts.extraction_telemetry_json_path(run_id)
    telemetry_csv_path = settings.artifacts.extraction_telemetry_csv_path(run_id)
    diagnostics_json_path = settings.artifacts.sql_diagnostics_summary_json_path(run_id)
    diagnostics_txt_path = settings.artifacts.sql_diagnostics_summary_txt_path(run_id)
    return _build_existing_partition_result(
        frame=frame,
        settings=settings,
        run_id=run_id,
        query_options=query_options,
        manifest_payload=manifest_payload,
        completion_payload=completion_payload,
        batch_artifacts=batch_artifacts,
        telemetry_json_path=telemetry_json_path,
        telemetry_csv_path=telemetry_csv_path,
        diagnostics_json_path=diagnostics_json_path,
        diagnostics_txt_path=diagnostics_txt_path,
    )


def _build_existing_partition_result(
    *,
    frame: pd.DataFrame,
    settings: PromotionPipelineSettings,
    run_id: str,
    query_options: PromotionBaseQueryOptions,
    manifest_payload: dict[str, object],
    completion_payload: dict[str, object],
    batch_artifacts: list[PromotionCompletedBatchArtifact],
    telemetry_json_path: Path,
    telemetry_csv_path: Path,
    diagnostics_json_path: Path,
    diagnostics_txt_path: Path,
) -> PromotionCompletedPartitionBatchResult:
    base_path = settings.artifacts.extracted_base_path(run_id)
    manifest_path = settings.artifacts.extracted_manifest_path(run_id)
    completion_path = settings.artifacts.extraction_partition_completion_path(run_id)
    batch_count = int(manifest_payload.get("batch_count", 0) or 0)
    return PromotionCompletedPartitionBatchResult(
        frame=frame,
        base_path=str(base_path),
        manifest_path=str(manifest_path),
        rendered_sql_path=_read_json_field(telemetry_json_path, "rendered_sql_path"),
        rendered_sql_parameters_path=_read_json_field(
            telemetry_json_path,
            "rendered_sql_parameters_path",
        ),
        telemetry_json_path=_optional_existing_path(telemetry_json_path),
        telemetry_csv_path=_optional_existing_path(telemetry_csv_path),
        diagnostics_summary_json_path=_optional_existing_path(diagnostics_json_path),
        diagnostics_summary_txt_path=_optional_existing_path(diagnostics_txt_path),
        candidate_promotion_row_count=int(
            manifest_payload.get("candidate_promotion_row_count", 0) or 0
        ),
        manifest=manifest_payload,
        extraction_mode=str(manifest_payload.get("extraction_mode", "live_sql")),
        partition_strategy=(
            str(manifest_payload.get("partition_strategy"))
            if manifest_payload.get("partition_strategy") is not None
            else (
                query_options.completed_partition.strategy
                if query_options.completed_partition is not None
                else None
            )
        ),
        partition_count=(
            int(manifest_payload.get("partition_count", 0) or 0)
            if manifest_payload.get("partition_count") is not None
            else (
                query_options.completed_partition.partition_count
                if query_options.completed_partition is not None
                else None
            )
        ),
        partition_index=(
            int(manifest_payload.get("partition_index", 0) or 0)
            if manifest_payload.get("partition_index") is not None
            else (
                query_options.completed_partition.partition_index
                if query_options.completed_partition is not None
                else None
            )
        ),
        fetch_mode=str(manifest_payload.get("fetch_mode", "landed_batch_fetch")),
        chunk_mode=str(manifest_payload.get("chunk_mode", "chunked_fetch")),
        chunk_count=int(manifest_payload.get("chunk_count", 0) or 0),
        completed_chunk_count=int(manifest_payload.get("completed_chunk_count", 0) or 0),
        cumulative_rows_written=int(manifest_payload.get("cumulative_rows_written", 0) or 0),
        batch_count=batch_count,
        finalized_batch_count=int(manifest_payload.get("finalized_batch_count", batch_count) or 0),
        resumed_batch_count=int(manifest_payload.get("resumed_batch_count", 0) or 0),
        rebuilt_batch_count=int(manifest_payload.get("rebuilt_batch_count", 0) or 0),
        total_landed_rows=int(manifest_payload.get("total_landed_rows", 0) or 0),
        completion_state=(
            str(manifest_payload.get("completion_state"))
            if manifest_payload.get("completion_state") is not None
            else None
        ),
        partition_completion_state=str(
            completion_payload.get("partition_completion_state", "finalized")
        ),
        resume_state="skip_finalized_partition",
        skipped_due_to_existing_completion=True,
        partition_progress_path=_optional_existing_path(
            settings.artifacts.extraction_partition_progress_path(run_id)
        ),
        partition_completion_marker_path=str(completion_path),
        batch_artifacts=tuple(batch_artifacts),
    )


def _load_required_partition_payload(
    *,
    run_id: str,
    label: str,
    path: Path,
) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise _partition_resolution_error(
            run_id=run_id,
            message=(
                f"Completed partition {label} could not be parsed ({type(error).__name__})."
            ),
            base_path=path.parent.parent / "cleaned_data_placeholder",
            manifest_path=path if label == "manifest" else path.parent.parent / "manifest_placeholder",
            completion_path=path if label == "completion marker" else path.parent.parent / "completion_placeholder",
        ) from error
    if not isinstance(payload, dict):
        raise _partition_resolution_error(
            run_id=run_id,
            message=f"Completed partition {label} must contain a JSON object payload.",
            base_path=path.parent.parent / "cleaned_data_placeholder",
            manifest_path=path if label == "manifest" else path.parent.parent / "manifest_placeholder",
            completion_path=path if label == "completion marker" else path.parent.parent / "completion_placeholder",
        )
    return payload


def _rebuild_finalized_partition_parquet(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    manifest_payload: dict[str, object],
    completion_payload: dict[str, object],
    batch_artifacts: list[PromotionCompletedBatchArtifact],
) -> pd.DataFrame:
    frame = _combine_batch_frames(batch_artifacts)
    _validate_resolved_partition_frame(
        run_id=run_id,
        frame=frame,
        manifest_payload=manifest_payload,
        base_path=settings.artifacts.extracted_base_path(run_id),
        manifest_path=settings.artifacts.extracted_manifest_path(run_id),
        completion_path=settings.artifacts.extraction_partition_completion_path(run_id),
    )
    PromotionExtractionWriter().write(
        base_frame=frame,
        manifest=_manifest_from_payload(manifest_payload),
        artifact_paths=settings.artifacts,
    )
    _write_partition_progress(
        artifact_paths=settings.artifacts,
        run_id=run_id,
        fetch_mode=str(manifest_payload.get("fetch_mode", "landed_batch_fetch")),
        chunk_mode=str(manifest_payload.get("chunk_mode", "chunked_fetch")),
        batch_row_count=int(completion_payload.get("batch_row_count", 0) or 0),
        batch_count=int(manifest_payload.get("batch_count", 0) or 0),
        finalized_batch_count=int(
            manifest_payload.get("finalized_batch_count")
            or manifest_payload.get("batch_count")
            or 0
        ),
        resumed_batch_count=int(manifest_payload.get("resumed_batch_count", 0) or 0),
        rebuilt_batch_count=int(manifest_payload.get("rebuilt_batch_count", 0) or 0),
        total_landed_rows=int(manifest_payload.get("total_landed_rows") or len(frame.index) or 0),
        chunk_count=int(manifest_payload.get("chunk_count", 0) or 0),
        completed_chunk_count=int(manifest_payload.get("completed_chunk_count", 0) or 0),
        cumulative_rows_written=int(
            manifest_payload.get("cumulative_rows_written") or len(frame.index) or 0
        ),
        partition_completion_state="finalized",
        completion_state=str(manifest_payload.get("completion_state", "finalized")),
        resume_state="rebuild_finalized_partition_artifact",
        skipped_due_to_existing_completion=True,
    )
    return frame


def _validate_resolved_partition_frame(
    *,
    run_id: str,
    frame: pd.DataFrame,
    manifest_payload: dict[str, object],
    base_path: Path,
    manifest_path: Path,
    completion_path: Path,
) -> None:
    expected_row_count = int(manifest_payload.get("row_count", 0) or 0)
    if int(len(frame.index)) != expected_row_count:
        raise _partition_resolution_error(
            run_id=run_id,
            message=(
                "Completed partition row count does not match the finalized partition manifest after resolution."
            ),
            base_path=base_path,
            manifest_path=manifest_path,
            completion_path=completion_path,
        )
    checksum = _compute_promotion_row_key_checksum(frame)
    expected_checksum = manifest_payload.get("promotion_row_key_checksum_sha256")
    if expected_checksum is not None and checksum != expected_checksum:
        raise _partition_resolution_error(
            run_id=run_id,
            message=(
                "Completed partition checksum does not match the finalized partition manifest after resolution."
            ),
            base_path=base_path,
            manifest_path=manifest_path,
            completion_path=completion_path,
        )


def _manifest_from_payload(payload: dict[str, object]) -> PromotionExtractionManifest:
    def _tuple_or_none(value: object) -> tuple[str, ...] | None:
        if value is None:
            return None
        return tuple(str(item) for item in value)

    return PromotionExtractionManifest(
        run_id=str(payload.get("run_id")),
        selection_mode=str(payload.get("selection_mode", "completed")),
        query_version=str(payload.get("query_version", "promotion_completed_enriched_v1")),
        as_of_date=str(payload.get("as_of_date")),
        extracted_at_utc=str(payload.get("extracted_at_utc")),
        row_count=int(payload.get("row_count", 0) or 0),
        column_count=int(payload.get("column_count", 0) or 0),
        duplicate_promotion_row_keys=int(payload.get("duplicate_promotion_row_keys", 0) or 0),
        advice_source_table=str(payload.get("advice_source_table", "")),
        realised_sales_source_table=str(payload.get("realised_sales_source_table", "")),
        columns=tuple(str(column_name) for column_name in payload.get("columns", ())),
        extraction_mode=str(payload.get("extraction_mode", "live_sql")),
        fetch_mode=str(payload.get("fetch_mode", "full_fetch")),
        chunk_mode=str(payload.get("chunk_mode", "full_fetch")),
        chunk_count=int(payload.get("chunk_count", 0) or 0),
        completed_chunk_count=int(payload.get("completed_chunk_count", 0) or 0),
        cumulative_rows_written=int(payload.get("cumulative_rows_written", 0) or 0),
        batch_count=int(payload.get("batch_count", 0) or 0),
        finalized_batch_count=int(payload.get("finalized_batch_count", 0) or 0),
        resumed_batch_count=int(payload.get("resumed_batch_count", 0) or 0),
        rebuilt_batch_count=int(payload.get("rebuilt_batch_count", 0) or 0),
        total_landed_rows=int(payload.get("total_landed_rows", 0) or 0),
        completion_state=(
            str(payload.get("completion_state"))
            if payload.get("completion_state") is not None
            else None
        ),
        partition_completion_state=(
            str(payload.get("partition_completion_state"))
            if payload.get("partition_completion_state") is not None
            else None
        ),
        resume_state=(str(payload.get("resume_state")) if payload.get("resume_state") is not None else None),
        skipped_due_to_existing_completion=bool(
            payload.get("skipped_due_to_existing_completion", False)
        ),
        promotion_row_key_checksum_sha256=(
            str(payload.get("promotion_row_key_checksum_sha256"))
            if payload.get("promotion_row_key_checksum_sha256") is not None
            else None
        ),
        completed_sales_history_start_date=(
            str(payload.get("completed_sales_history_start_date"))
            if payload.get("completed_sales_history_start_date") is not None
            else None
        ),
        staged_extraction_enabled=bool(payload.get("staged_extraction_enabled", False)),
        completed_extraction_stage_mode=(
            str(payload.get("completed_extraction_stage_mode"))
            if payload.get("completed_extraction_stage_mode") is not None
            else None
        ),
        extraction_stage=(
            str(payload.get("extraction_stage"))
            if payload.get("extraction_stage") is not None
            else None
        ),
        candidate_promotion_row_count=(
            int(payload.get("candidate_promotion_row_count", 0) or 0)
            if payload.get("candidate_promotion_row_count") is not None
            else None
        ),
        partition_strategy=(
            str(payload.get("partition_strategy"))
            if payload.get("partition_strategy") is not None
            else None
        ),
        partition_count=(
            int(payload.get("partition_count", 0) or 0)
            if payload.get("partition_count") is not None
            else None
        ),
        partition_index=(
            int(payload.get("partition_index", 0) or 0)
            if payload.get("partition_index") is not None
            else None
        ),
        child_partition_manifest_paths=_tuple_or_none(payload.get("child_partition_manifest_paths")),
        child_batch_manifest_paths=_tuple_or_none(payload.get("child_batch_manifest_paths")),
        child_batch_parquet_paths=_tuple_or_none(payload.get("child_batch_parquet_paths")),
        child_stage_manifest_paths=_tuple_or_none(payload.get("child_stage_manifest_paths")),
        child_stage_parquet_paths=_tuple_or_none(payload.get("child_stage_parquet_paths")),
    )


def _partition_resolution_error(
    *,
    run_id: str,
    message: str,
    base_path: Path,
    manifest_path: Path,
    completion_path: Path,
) -> PromotionCompletedPartitionArtifactResolutionError:
    error = PromotionCompletedPartitionArtifactResolutionError(message)
    setattr(error, "run_id", run_id)
    setattr(error, "completed_partition_base_path", str(base_path))
    setattr(error, "completed_partition_manifest_path", str(manifest_path))
    setattr(error, "completed_partition_completion_path", str(completion_path))
    return error


def _validate_existing_batch_artifact(
    *,
    artifact_paths: PromotionArtifactPaths,
    partition_run_id: str,
    batch_slice: PromotionCompletedBatchSlice,
) -> _ExistingBatchValidation:
    batch_run_id = _completed_batch_run_id(partition_run_id, batch_slice.batch_index)
    base_path = artifact_paths.extracted_base_path(batch_run_id)
    manifest_path = artifact_paths.extracted_manifest_path(batch_run_id)
    completion_path = artifact_paths.extraction_partition_completion_path(batch_run_id)
    progress_path = artifact_paths.extraction_partition_progress_path(batch_run_id)
    outputs_exist = any(
        path.exists() for path in (base_path, manifest_path, completion_path, progress_path)
    ) or _any_batch_stage_outputs_exist(artifact_paths, batch_run_id)
    if not outputs_exist:
        return _ExistingBatchValidation(artifact=None, outputs_exist=False, rebuild_reason=None)
    try:
        completion_payload = json.loads(completion_path.read_text(encoding="utf-8"))
    except Exception as error:
        _cleanup_batch_stage_outputs(artifact_paths, batch_run_id)
        return _ExistingBatchValidation(
            artifact=None,
            outputs_exist=True,
            rebuild_reason=f"invalid completion marker ({type(error).__name__})",
        )
    if completion_payload.get("partition_completion_state") != "finalized":
        _cleanup_batch_stage_outputs(artifact_paths, batch_run_id)
        return _ExistingBatchValidation(
            artifact=None,
            outputs_exist=True,
            rebuild_reason="completion marker not finalized",
        )
    if not base_path.exists() or not manifest_path.exists():
        _cleanup_batch_stage_outputs(artifact_paths, batch_run_id)
        return _ExistingBatchValidation(
            artifact=None,
            outputs_exist=True,
            rebuild_reason="finalized parquet or manifest missing",
        )
    try:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        frame = pd.read_parquet(base_path)
    except Exception as error:
        _cleanup_batch_stage_outputs(artifact_paths, batch_run_id)
        return _ExistingBatchValidation(
            artifact=None,
            outputs_exist=True,
            rebuild_reason=f"persisted batch could not be read ({type(error).__name__})",
        )
    expected_row_count = int(
        completion_payload.get("row_count")
        or manifest_payload.get("row_count")
        or 0
    )
    if int(len(frame.index)) != expected_row_count:
        _cleanup_batch_stage_outputs(artifact_paths, batch_run_id)
        return _ExistingBatchValidation(
            artifact=None,
            outputs_exist=True,
            rebuild_reason="row count mismatch between finalized parquet and marker",
        )
    checksum = _compute_promotion_row_key_checksum(frame)
    expected_checksum = (
        completion_payload.get("promotion_row_key_checksum_sha256")
        or manifest_payload.get("promotion_row_key_checksum_sha256")
    )
    if expected_checksum is not None and checksum != expected_checksum:
        _cleanup_batch_stage_outputs(artifact_paths, batch_run_id)
        return _ExistingBatchValidation(
            artifact=None,
            outputs_exist=True,
            rebuild_reason="checksum mismatch between finalized parquet and marker",
        )
    telemetry_json_path = artifact_paths.extraction_telemetry_json_path(batch_run_id)
    telemetry_csv_path = artifact_paths.extraction_telemetry_csv_path(batch_run_id)
    diagnostics_json_path = artifact_paths.sql_diagnostics_summary_json_path(batch_run_id)
    diagnostics_txt_path = artifact_paths.sql_diagnostics_summary_txt_path(batch_run_id)
    return _ExistingBatchValidation(
        artifact=PromotionCompletedBatchArtifact(
            batch_index=batch_slice.batch_index,
            batch_run_id=batch_run_id,
            row_start=batch_slice.row_start,
            row_end=batch_slice.row_end,
            row_count=expected_row_count,
            candidate_promotion_row_count=(
                int(manifest_payload.get("candidate_promotion_row_count", 0) or 0)
                if manifest_payload.get("candidate_promotion_row_count") is not None
                else None
            ),
            base_path=str(base_path),
            manifest_path=str(manifest_path),
            completion_marker_path=str(completion_path),
            telemetry_json_path=_optional_existing_path(telemetry_json_path),
            telemetry_csv_path=_optional_existing_path(telemetry_csv_path),
            diagnostics_summary_json_path=_optional_existing_path(diagnostics_json_path),
            diagnostics_summary_txt_path=_optional_existing_path(diagnostics_txt_path),
            fetch_mode=str(manifest_payload.get("fetch_mode", "chunked_fetch")),
            chunk_mode=str(manifest_payload.get("chunk_mode", "chunked_fetch")),
            chunk_count=int(manifest_payload.get("chunk_count", 0) or 0),
            completed_chunk_count=int(
                manifest_payload.get("completed_chunk_count", 0) or 0
            ),
            cumulative_rows_written=int(
                manifest_payload.get("cumulative_rows_written", expected_row_count) or 0
            ),
            resume_state="skip_finalized_batch",
            skipped_due_to_existing_completion=True,
            rebuilt=False,
            promotion_row_key_checksum_sha256=checksum,
            manifest=manifest_payload,
        ),
        outputs_exist=True,
        rebuild_reason=None,
    )


def _write_partition_progress(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    fetch_mode: str,
    chunk_mode: str,
    batch_row_count: int,
    batch_count: int,
    finalized_batch_count: int,
    resumed_batch_count: int,
    rebuilt_batch_count: int,
    total_landed_rows: int,
    chunk_count: int,
    completed_chunk_count: int,
    cumulative_rows_written: int,
    partition_completion_state: str,
    completion_state: str,
    resume_state: str,
    skipped_due_to_existing_completion: bool,
    failure_message: str | None = None,
) -> None:
    progress_path = artifact_paths.extraction_partition_progress_path(run_id)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "fetch_mode": fetch_mode,
                "chunk_mode": chunk_mode,
                "batch_row_count": batch_row_count,
                "batch_count": batch_count,
                "finalized_batch_count": finalized_batch_count,
                "resumed_batch_count": resumed_batch_count,
                "rebuilt_batch_count": rebuilt_batch_count,
                "total_landed_rows": total_landed_rows,
                "chunk_count": chunk_count,
                "completed_chunk_count": completed_chunk_count,
                "cumulative_rows_written": cumulative_rows_written,
                "partition_completion_state": partition_completion_state,
                "completion_state": completion_state,
                "resume_state": resume_state,
                "skipped_due_to_existing_completion": skipped_due_to_existing_completion,
                "failure_message": failure_message,
                "updated_at_utc": _utc_now_iso(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_partition_completion(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    manifest: PromotionExtractionManifest,
    batch_row_count: int,
    base_path: Path,
    manifest_path: Path,
) -> None:
    completion_path = artifact_paths.extraction_partition_completion_path(run_id)
    completion_path.parent.mkdir(parents=True, exist_ok=True)
    completion_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "fetch_mode": manifest.fetch_mode,
                "chunk_mode": manifest.chunk_mode,
                "batch_row_count": batch_row_count,
                "batch_count": manifest.batch_count,
                "finalized_batch_count": manifest.finalized_batch_count,
                "resumed_batch_count": manifest.resumed_batch_count,
                "rebuilt_batch_count": manifest.rebuilt_batch_count,
                "total_landed_rows": manifest.total_landed_rows,
                "chunk_count": manifest.chunk_count,
                "completed_chunk_count": manifest.completed_chunk_count,
                "cumulative_rows_written": manifest.cumulative_rows_written,
                "row_count": manifest.row_count,
                "promotion_row_key_checksum_sha256": (
                    manifest.promotion_row_key_checksum_sha256
                ),
                "completion_state": manifest.completion_state,
                "partition_completion_state": manifest.partition_completion_state,
                "resume_state": manifest.resume_state,
                "skipped_due_to_existing_completion": False,
                "base_path": str(base_path),
                "manifest_path": str(manifest_path),
                "completed_at_utc": _utc_now_iso(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _completed_batch_run_id(run_id: str, batch_index: int) -> str:
    return f"{run_id}-batch-{batch_index:06d}"


def _build_completed_batch_slice(
    *,
    batch_index: int,
    batch_row_count: int,
) -> PromotionCompletedBatchSlice:
    row_start = ((batch_index - 1) * batch_row_count) + 1
    row_end = batch_index * batch_row_count
    return PromotionCompletedBatchSlice(
        batch_index=batch_index,
        row_start=row_start,
        row_end=row_end,
    )


def _any_child_batch_outputs_exist(artifact_paths: PromotionArtifactPaths, run_id: str) -> bool:
    return any(
        root.name.startswith(f"{run_id}-batch-")
        for root in artifact_paths.manifests_root.glob(f"{run_id}-batch-*")
    )


def _any_batch_stage_outputs_exist(
    artifact_paths: PromotionArtifactPaths,
    batch_run_id: str,
) -> bool:
    return any(
        root.name.startswith(f"{batch_run_id}-")
        for root in artifact_paths.manifests_root.glob(f"{batch_run_id}-*")
    )


def _cleanup_partition_and_batch_outputs(
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
) -> None:
    _cleanup_run_outputs(artifact_paths, run_id)
    for root in (
        artifact_paths.extracted_root,
        artifact_paths.manifests_root,
        artifact_paths.logs_root,
    ):
        for child in root.glob(f"{run_id}-batch-*"):
            if child.is_dir():
                shutil.rmtree(child)
            elif child.exists():
                child.unlink()


def _cleanup_batch_stage_outputs(
    artifact_paths: PromotionArtifactPaths,
    batch_run_id: str,
) -> None:
    _cleanup_run_outputs(artifact_paths, batch_run_id)
    for root in (
        artifact_paths.extracted_root,
        artifact_paths.manifests_root,
        artifact_paths.logs_root,
    ):
        for child in root.glob(f"{batch_run_id}-*"):
            if child.is_dir():
                shutil.rmtree(child)
            elif child.exists():
                child.unlink()


def _cleanup_run_outputs(artifact_paths: PromotionArtifactPaths, run_id: str) -> None:
    for root in (
        artifact_paths.extracted_run_root(run_id),
        artifact_paths.manifests_run_root(run_id),
        artifact_paths.logs_run_root(run_id),
    ):
        if root.exists():
            shutil.rmtree(root)


def _extract_candidate_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    if "candidate_promotion_row_count" not in frame.columns:
        raise ValueError("Candidate count probe did not return candidate_promotion_row_count.")
    return int(frame.iloc[0]["candidate_promotion_row_count"])


def _compute_promotion_row_key_checksum(frame: pd.DataFrame) -> str | None:
    if "promotion_row_key" not in frame.columns:
        return None
    digest = __import__("hashlib").sha256()
    for row_key in frame["promotion_row_key"].tolist():
        digest.update(str(row_key).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _optional_existing_path(path: Path) -> str | None:
    return str(path) if path.exists() else None


def _read_json_field(path: Path, field_name: str) -> str | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = payload.get(field_name)
    return str(value) if value is not None else None


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()