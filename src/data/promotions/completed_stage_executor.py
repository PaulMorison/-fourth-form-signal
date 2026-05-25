from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from typing import Callable

import pandas as pd

from data.promotions.chunked_extraction_writer import PromotionChunkedExtractionWriter
from data.promotions.mssql_query_executor import (
    PromotionQueryExecutor,
    PromotionSqlChunkFetchProgress,
    PromotionSqlExecutionTelemetry,
    PromotionSqlSubphaseCallback,
)
from data.promotions.promotion_base_extractor import (
    PromotionExtractionManifest,
    PromotionExtractionTelemetry,
    write_extraction_observability,
)
from runtime.promotions.config import PromotionPipelineSettings


_COMPLETED_BASE_STAGE_NAME = "completed_base"
_SOURCE_SKU_COLUMN = "sku_number"
_GOVERNED_SKU_KEY_COLUMN = "sku_number_key"
_SOURCE_SKU_DIAGNOSTIC_COLUMNS = (
    "advice_batch_row_number",
    "source_file",
    "promotion_name",
    "promotion_row_key",
    "store_number",
    "sku_number",
    "sku_number_key",
)


class PromotionCompletedSourceIdentityError(ValueError):
    """Raised when completed Stage 3 advice-source identity cannot be governed."""


@dataclass(frozen=True)
class PromotionCompletedRenderedStageQuery:
    sql: str
    parameters: dict[str, object]
    query_version: str
    stage_name: str
    diagnostic_filter_summary: dict[str, object]
    estimated_window_summary: dict[str, object]


@dataclass(frozen=True)
class PromotionCompletedStageArtifact:
    run_id: str
    stage_name: str
    frame: pd.DataFrame
    base_path: str
    manifest_path: str
    progress_path: str
    completion_marker_path: str
    rendered_sql_path: str
    rendered_sql_parameters_path: str
    telemetry_json_path: str
    telemetry_csv_path: str
    diagnostics_summary_json_path: str
    diagnostics_summary_txt_path: str
    manifest: dict[str, object]
    fetch_mode: str
    chunk_mode: str
    chunk_count: int
    completed_chunk_count: int
    cumulative_rows_written: int
    row_count: int
    promotion_row_key_checksum_sha256: str | None


def execute_completed_sql_stage(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    stage_name: str,
    executor: PromotionQueryExecutor,
    rendered_query: PromotionCompletedRenderedStageQuery,
    candidate_promotion_row_count: int | None = None,
    phase_callback: Callable[[str], None] | None = None,
) -> PromotionCompletedStageArtifact:
    telemetry = PromotionExtractionTelemetry(
        run_id=run_id,
        selection_mode="completed",
        as_of_date=settings.as_of_date.isoformat(),
        query_version=rendered_query.query_version,
        extraction_mode="live_sql",
        advice_source_table=settings.sql.promotion_advice_table,
        realised_sales_source_table=settings.sql.pwlogd_table,
        rendered_query_parameter_summary=dict(rendered_query.parameters),
        diagnostic_filter_summary=dict(rendered_query.diagnostic_filter_summary),
        estimated_window_summary=dict(rendered_query.estimated_window_summary),
        connect_timeout_seconds=settings.sql.connect_timeout_seconds,
        connect_retry_attempts=settings.sql.connect_retry_attempts,
        connect_retry_backoff_seconds=settings.sql.connect_retry_backoff_seconds,
        query_timeout_seconds=settings.sql.query_timeout_seconds,
        fetch_mode=(
            "chunked_fetch"
            if settings.completed_extraction_runtime.enable_chunked_fetch
            else "full_fetch"
        ),
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
        candidate_promotion_row_count=candidate_promotion_row_count,
        completed_sales_history_start_date=(
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
        ),
        staged_extraction_enabled=True,
        completed_extraction_stage_mode="completed_staged_enrichment_v1",
        extraction_stage=stage_name,
    )
    writer = PromotionChunkedExtractionWriter(
        artifact_paths=settings.artifacts,
        run_id=run_id,
        stage_temp_chunk_files=settings.completed_extraction_runtime.stage_temp_chunk_files,
    )
    try:
        telemetry.current_sql_subphase = "SQL query render in progress"
        telemetry.query_render_started_at_utc = _utc_now_iso()
        _notify_phase(phase_callback, stage_name, telemetry.current_sql_subphase)
        rendered_sql_path, rendered_sql_parameters_path = _write_rendered_stage_query_artifacts(
            run_id=run_id,
            settings=settings,
            rendered_query=rendered_query,
        )
        telemetry.rendered_sql_path = rendered_sql_path
        telemetry.rendered_sql_parameters_path = rendered_sql_parameters_path
        telemetry.query_render_completed_at_utc = _utc_now_iso()

        if settings.completed_extraction_runtime.enable_chunked_fetch:
            return _execute_stage_in_chunks(
                settings=settings,
                run_id=run_id,
                stage_name=stage_name,
                executor=executor,
                rendered_query=rendered_query,
                telemetry=telemetry,
                writer=writer,
                phase_callback=phase_callback,
            )
        return _execute_stage_full_fetch(
            settings=settings,
            run_id=run_id,
            stage_name=stage_name,
            executor=executor,
            rendered_query=rendered_query,
            telemetry=telemetry,
            writer=writer,
            phase_callback=phase_callback,
        )
    except Exception as error:
        sql_telemetry = getattr(error, "sql_execution_telemetry", None)
        if isinstance(sql_telemetry, PromotionSqlExecutionTelemetry):
            telemetry.apply_sql_execution_telemetry(sql_telemetry)
        writer.mark_failure(failure_message=str(error))
        telemetry.output_partition_progress_path = str(writer.progress_path)
        telemetry.output_partition_completion_path = str(writer.completion_marker_path)
        telemetry.partition_completion_state = "failed_incomplete"
        telemetry.completion_state = "failed_incomplete"
        telemetry.mark_failure(error, stage=telemetry.current_sql_subphase)
        observability = write_extraction_observability(
            telemetry=telemetry,
            settings=settings,
            artifact_paths=settings.artifacts,
        )
        setattr(error, "extraction_telemetry_json_path", observability.telemetry_json_path)
        setattr(error, "extraction_telemetry_csv_path", observability.telemetry_csv_path)
        setattr(
            error,
            "sql_diagnostics_summary_json_path",
            observability.diagnostics_summary_json_path,
        )
        setattr(
            error,
            "sql_diagnostics_summary_txt_path",
            observability.diagnostics_summary_txt_path,
        )
        raise


def _execute_stage_in_chunks(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    stage_name: str,
    executor: PromotionQueryExecutor,
    rendered_query: PromotionCompletedRenderedStageQuery,
    telemetry: PromotionExtractionTelemetry,
    writer: PromotionChunkedExtractionWriter,
    phase_callback: Callable[[str], None] | None,
) -> PromotionCompletedStageArtifact:
    writer.start_partition(
        fetch_mode="chunked_fetch",
        chunk_row_count=settings.completed_extraction_runtime.chunk_row_count,
    )
    total_rows_written = 0
    duplicate_promotion_row_keys = 0
    seen_promotion_row_keys: set[object] = set()
    checksum_digest = hashlib.sha256()
    promotion_row_key_seen = False
    expected_columns: tuple[str, ...] | None = None

    def _consume_chunk(frame: pd.DataFrame, chunk_progress: PromotionSqlChunkFetchProgress) -> None:
        nonlocal total_rows_written, duplicate_promotion_row_keys, expected_columns, promotion_row_key_seen
        current_columns = tuple(str(column_name) for column_name in frame.columns)
        if expected_columns is None:
            expected_columns = current_columns
        elif current_columns != expected_columns:
            raise ValueError(
                f"Completed staged extraction changed columns mid-stage for {stage_name}."
            )
        telemetry.current_sql_subphase = "validating completed base source SKU identity"
        _validate_completed_base_source_sku_identity(
            frame=frame,
            settings=settings,
            stage_name=stage_name,
            fetch_context=f"chunk_index={chunk_progress.chunk_index}",
        )
        if "promotion_row_key" in frame.columns:
            promotion_row_key_seen = True
            for row_key in frame["promotion_row_key"].tolist():
                checksum_digest.update(str(row_key).encode("utf-8"))
                checksum_digest.update(b"\n")
                if row_key in seen_promotion_row_keys:
                    duplicate_promotion_row_keys += 1
                else:
                    seen_promotion_row_keys.add(row_key)
        persisted_path = writer.write_chunk(frame, chunk_index=chunk_progress.chunk_index)
        total_rows_written += len(frame.index)
        if phase_callback is not None:
            phase_callback(
                f"{stage_name} | chunk {chunk_progress.chunk_index} | rows {chunk_progress.chunk_row_count} | "
                f"cumulative_rows {chunk_progress.cumulative_row_count} | persisted {persisted_path or writer.progress_path}"
            )

    execution_result = executor.fetch_dataframe_in_chunks(
        sql=rendered_query.sql,
        parameters=rendered_query.parameters,
        chunk_row_count=settings.completed_extraction_runtime.chunk_row_count,
        chunk_consumer=_consume_chunk,
        phase_callback=_wrapped_phase_callback(stage_name, phase_callback),
    )
    telemetry.apply_sql_execution_telemetry(execution_result.telemetry)
    telemetry.current_sql_subphase = "compacting staged extraction parquet and writing manifest"
    _notify_phase(phase_callback, stage_name, telemetry.current_sql_subphase)
    telemetry.dataframe_write_started_at_utc = _utc_now_iso()
    manifest = _build_stage_manifest(
        settings=settings,
        run_id=run_id,
        rendered_query=rendered_query,
        columns=(expected_columns or execution_result.columns),
        row_count=total_rows_written,
        duplicate_promotion_row_keys=duplicate_promotion_row_keys,
        chunk_count=telemetry.chunk_count,
        completed_chunk_count=telemetry.completed_chunk_count,
        cumulative_rows_written=telemetry.cumulative_rows_written,
        candidate_promotion_row_count=telemetry.candidate_promotion_row_count,
        promotion_row_key_checksum_sha256=(
            checksum_digest.hexdigest() if promotion_row_key_seen else None
        ),
        stage_name=stage_name,
    )
    persisted = writer.finalize(manifest=manifest)
    final_frame = pd.read_parquet(persisted.base_path)
    telemetry.extracted_at_utc = manifest.extracted_at_utc
    telemetry.row_count = row_count = int(len(final_frame.index))
    telemetry.column_count = int(len(final_frame.columns))
    telemetry.duplicate_promotion_row_keys = duplicate_promotion_row_keys
    telemetry.total_landed_rows = row_count
    telemetry.promotion_row_key_checksum_sha256 = manifest.promotion_row_key_checksum_sha256
    telemetry.output_parquet_path = str(persisted.base_path)
    telemetry.output_manifest_path = str(persisted.manifest_path)
    telemetry.output_partition_progress_path = str(persisted.progress_path)
    telemetry.output_partition_completion_path = str(persisted.completion_marker_path)
    telemetry.partition_completion_state = persisted.partition_completion_state
    telemetry.resume_state = persisted.resume_state
    telemetry.completion_state = manifest.completion_state
    telemetry.dataframe_write_completed_at_utc = _utc_now_iso()
    telemetry.mark_success()
    observability = write_extraction_observability(
        telemetry=telemetry,
        settings=settings,
        artifact_paths=settings.artifacts,
    )
    return PromotionCompletedStageArtifact(
        run_id=run_id,
        stage_name=stage_name,
        frame=final_frame,
        base_path=str(persisted.base_path),
        manifest_path=str(persisted.manifest_path),
        progress_path=str(persisted.progress_path),
        completion_marker_path=str(persisted.completion_marker_path),
        rendered_sql_path=telemetry.rendered_sql_path or "",
        rendered_sql_parameters_path=telemetry.rendered_sql_parameters_path or "",
        telemetry_json_path=observability.telemetry_json_path,
        telemetry_csv_path=observability.telemetry_csv_path,
        diagnostics_summary_json_path=observability.diagnostics_summary_json_path,
        diagnostics_summary_txt_path=observability.diagnostics_summary_txt_path,
        manifest=manifest.to_dict(),
        fetch_mode=telemetry.fetch_mode,
        chunk_mode=telemetry.chunk_mode,
        chunk_count=telemetry.chunk_count,
        completed_chunk_count=telemetry.completed_chunk_count,
        cumulative_rows_written=telemetry.cumulative_rows_written,
        row_count=row_count,
        promotion_row_key_checksum_sha256=manifest.promotion_row_key_checksum_sha256,
    )


def _execute_stage_full_fetch(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    stage_name: str,
    executor: PromotionQueryExecutor,
    rendered_query: PromotionCompletedRenderedStageQuery,
    telemetry: PromotionExtractionTelemetry,
    writer: PromotionChunkedExtractionWriter,
    phase_callback: Callable[[str], None] | None,
) -> PromotionCompletedStageArtifact:
    execution_result = executor.fetch_dataframe(
        sql=rendered_query.sql,
        parameters=rendered_query.parameters,
        phase_callback=_wrapped_phase_callback(stage_name, phase_callback),
    )
    frame = execution_result.frame
    telemetry.apply_sql_execution_telemetry(execution_result.telemetry)
    telemetry.current_sql_subphase = "validating completed base source SKU identity"
    _notify_phase(phase_callback, stage_name, telemetry.current_sql_subphase)
    _validate_completed_base_source_sku_identity(
        frame=frame,
        settings=settings,
        stage_name=stage_name,
        fetch_context="full_fetch",
    )
    telemetry.current_sql_subphase = "writing staged extraction parquet and manifest"
    _notify_phase(phase_callback, stage_name, telemetry.current_sql_subphase)
    telemetry.dataframe_write_started_at_utc = _utc_now_iso()
    writer.start_partition(
        fetch_mode="full_fetch",
        chunk_row_count=max(1, int(len(frame.index) or 1)),
    )
    writer.write_chunk(frame, chunk_index=1)
    manifest = _build_stage_manifest(
        settings=settings,
        run_id=run_id,
        rendered_query=rendered_query,
        columns=tuple(str(column_name) for column_name in frame.columns),
        row_count=int(len(frame.index)),
        duplicate_promotion_row_keys=int(
            frame["promotion_row_key"].duplicated().sum()
            if "promotion_row_key" in frame.columns
            else 0
        ),
        chunk_count=1 if len(frame.index) > 0 else 0,
        completed_chunk_count=1 if len(frame.index) > 0 else 0,
        cumulative_rows_written=int(len(frame.index)),
        candidate_promotion_row_count=telemetry.candidate_promotion_row_count,
        promotion_row_key_checksum_sha256=_compute_promotion_row_key_checksum(frame),
        stage_name=stage_name,
    )
    persisted = writer.finalize(manifest=manifest)
    telemetry.extracted_at_utc = manifest.extracted_at_utc
    telemetry.row_count = int(len(frame.index))
    telemetry.column_count = int(len(frame.columns))
    telemetry.duplicate_promotion_row_keys = int(
        frame["promotion_row_key"].duplicated().sum()
        if "promotion_row_key" in frame.columns
        else 0
    )
    telemetry.chunk_count = 1 if len(frame.index) > 0 else 0
    telemetry.completed_chunk_count = 1 if len(frame.index) > 0 else 0
    telemetry.cumulative_rows_written = int(len(frame.index))
    telemetry.total_landed_rows = int(len(frame.index))
    telemetry.promotion_row_key_checksum_sha256 = manifest.promotion_row_key_checksum_sha256
    telemetry.output_parquet_path = str(persisted.base_path)
    telemetry.output_manifest_path = str(persisted.manifest_path)
    telemetry.output_partition_progress_path = str(persisted.progress_path)
    telemetry.output_partition_completion_path = str(persisted.completion_marker_path)
    telemetry.partition_completion_state = persisted.partition_completion_state
    telemetry.resume_state = persisted.resume_state
    telemetry.completion_state = manifest.completion_state
    telemetry.dataframe_write_completed_at_utc = _utc_now_iso()
    telemetry.mark_success()
    observability = write_extraction_observability(
        telemetry=telemetry,
        settings=settings,
        artifact_paths=settings.artifacts,
    )
    return PromotionCompletedStageArtifact(
        run_id=run_id,
        stage_name=stage_name,
        frame=frame,
        base_path=str(persisted.base_path),
        manifest_path=str(persisted.manifest_path),
        progress_path=str(persisted.progress_path),
        completion_marker_path=str(persisted.completion_marker_path),
        rendered_sql_path=telemetry.rendered_sql_path or "",
        rendered_sql_parameters_path=telemetry.rendered_sql_parameters_path or "",
        telemetry_json_path=observability.telemetry_json_path,
        telemetry_csv_path=observability.telemetry_csv_path,
        diagnostics_summary_json_path=observability.diagnostics_summary_json_path,
        diagnostics_summary_txt_path=observability.diagnostics_summary_txt_path,
        manifest=manifest.to_dict(),
        fetch_mode=telemetry.fetch_mode,
        chunk_mode=telemetry.chunk_mode,
        chunk_count=telemetry.chunk_count,
        completed_chunk_count=telemetry.completed_chunk_count,
        cumulative_rows_written=telemetry.cumulative_rows_written,
        row_count=int(len(frame.index)),
        promotion_row_key_checksum_sha256=manifest.promotion_row_key_checksum_sha256,
    )


def _build_stage_manifest(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    rendered_query: PromotionCompletedRenderedStageQuery,
    columns: tuple[str, ...],
    row_count: int,
    duplicate_promotion_row_keys: int,
    chunk_count: int,
    completed_chunk_count: int,
    cumulative_rows_written: int,
    candidate_promotion_row_count: int | None,
    promotion_row_key_checksum_sha256: str | None,
    stage_name: str,
) -> PromotionExtractionManifest:
    return PromotionExtractionManifest(
        run_id=run_id,
        selection_mode="completed",
        query_version=rendered_query.query_version,
        as_of_date=settings.as_of_date.isoformat(),
        extracted_at_utc=_utc_now_iso(),
        row_count=row_count,
        column_count=int(len(columns)),
        duplicate_promotion_row_keys=duplicate_promotion_row_keys,
        advice_source_table=settings.sql.promotion_advice_table,
        realised_sales_source_table=settings.sql.pwlogd_table,
        columns=columns,
        extraction_mode="live_sql",
        fetch_mode=(
            "chunked_fetch"
            if settings.completed_extraction_runtime.enable_chunked_fetch
            else "full_fetch"
        ),
        chunk_mode=(
            "chunked_fetch"
            if settings.completed_extraction_runtime.enable_chunked_fetch
            else "full_fetch"
        ),
        chunk_count=chunk_count,
        completed_chunk_count=completed_chunk_count,
        cumulative_rows_written=cumulative_rows_written,
        batch_count=0,
        finalized_batch_count=0,
        resumed_batch_count=0,
        rebuilt_batch_count=0,
        total_landed_rows=row_count,
        completion_state="finalized",
        partition_completion_state="finalized",
        resume_state="new_stage",
        skipped_due_to_existing_completion=False,
        promotion_row_key_checksum_sha256=promotion_row_key_checksum_sha256,
        completed_sales_history_start_date=(
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
        ),
        staged_extraction_enabled=True,
        completed_extraction_stage_mode="completed_staged_enrichment_v1",
        extraction_stage=stage_name,
        candidate_promotion_row_count=candidate_promotion_row_count,
    )


def _write_rendered_stage_query_artifacts(
    *,
    run_id: str,
    settings: PromotionPipelineSettings,
    rendered_query: PromotionCompletedRenderedStageQuery,
) -> tuple[str, str]:
    run_root = settings.artifacts.manifests_run_root(run_id)
    sql_path = run_root / "rendered_sql.sql"
    parameters_path = run_root / "rendered_sql_parameters.json"
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    parameters_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.write_text(rendered_query.sql, encoding="utf-8")
    parameters_path.write_text(
        json.dumps(rendered_query.parameters, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return str(sql_path), str(parameters_path)


def _compute_promotion_row_key_checksum(frame: pd.DataFrame) -> str | None:
    if "promotion_row_key" not in frame.columns:
        return None
    digest = hashlib.sha256()
    for row_key in frame["promotion_row_key"].tolist():
        digest.update(str(row_key).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _validate_completed_base_source_sku_identity(
    *,
    frame: pd.DataFrame,
    settings: PromotionPipelineSettings,
    stage_name: str,
    fetch_context: str,
) -> None:
    if stage_name != _COMPLETED_BASE_STAGE_NAME:
        return
    required_columns = (_SOURCE_SKU_COLUMN, _GOVERNED_SKU_KEY_COLUMN)
    missing_columns = tuple(column for column in required_columns if column not in frame.columns)
    if missing_columns:
        raise PromotionCompletedSourceIdentityError(
            "Completed Stage 3 source SKU identity validation failed for completed_base: "
            f"advice_source_table={settings.sql.promotion_advice_table}; "
            f"fetch_context={fetch_context}; missing_columns={','.join(missing_columns)}. "
            "The completed-base SQL must expose raw sku_number and derived sku_number_key; "
            "rows were not repaired, filtered, or finalized."
        )

    key_source = frame[_GOVERNED_SKU_KEY_COLUMN]
    key_numeric = pd.to_numeric(key_source, errors="coerce")
    blank_key = key_source.map(lambda value: isinstance(value, str) and value.strip() == "")
    null_key = key_source.isna() | blank_key
    non_numeric_key = key_numeric.isna() & ~null_key
    non_finite_key = key_numeric.map(_is_non_finite_number)
    non_integer_key = key_numeric.map(_is_non_integer_number)
    invalid_key = null_key | non_numeric_key | non_finite_key | non_integer_key
    invalid_rows = int(invalid_key.sum())
    if invalid_rows == 0:
        return

    sample_rows = _format_source_sku_identity_samples(frame.loc[invalid_key])
    raise PromotionCompletedSourceIdentityError(
        "Completed Stage 3 source SKU identity validation failed for completed_base: "
        f"advice_source_table={settings.sql.promotion_advice_table}; "
        f"fetch_context={fetch_context}; invalid_rows={invalid_rows}; "
        f"sku_number_key_nulls={int(null_key.sum())}; "
        f"sku_number_key_non_numeric={int(non_numeric_key.sum())}; "
        f"sku_number_key_non_finite={int(non_finite_key.sum())}; "
        f"sku_number_key_non_integer={int(non_integer_key.sum())}; "
        "raw advice-source sku_number could not derive a governed integer sku_number_key. "
        f"sample_rows={sample_rows}. "
        "Fix the advice-source table or upstream header mapping before rerun; "
        "rows were not repaired, filtered, or finalized."
    )


def _is_non_finite_number(value: object) -> bool:
    if pd.isna(value):
        return False
    return not math.isfinite(float(value))


def _is_non_integer_number(value: object) -> bool:
    if pd.isna(value) or _is_non_finite_number(value):
        return False
    return float(value) != float(round(float(value), 0))


def _format_source_sku_identity_samples(frame: pd.DataFrame, *, max_rows: int = 5) -> str:
    diagnostic_columns = [
        column for column in _SOURCE_SKU_DIAGNOSTIC_COLUMNS if column in frame.columns
    ]
    if not diagnostic_columns:
        diagnostic_columns = [_SOURCE_SKU_COLUMN, _GOVERNED_SKU_KEY_COLUMN]
    records = []
    for record in frame.loc[:, diagnostic_columns].head(max_rows).to_dict("records"):
        records.append(
            {
                str(column): _json_safe_source_value(value)
                for column, value in record.items()
            }
        )
    return json.dumps(records, sort_keys=True)


def _json_safe_source_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _notify_phase(
    phase_callback: Callable[[str], None] | None,
    stage_name: str,
    message: str,
) -> None:
    if phase_callback is not None:
        phase_callback(f"{stage_name} | {message}")


def _wrapped_phase_callback(
    stage_name: str,
    phase_callback: Callable[[str], None] | None,
) -> PromotionSqlSubphaseCallback | None:
    if phase_callback is None:
        return None
    return lambda subphase: phase_callback(f"{stage_name} | {subphase}")


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()