from __future__ import annotations

"""Historical and future promotions base extraction service.

Canon ownership:
- Executes the governed SQL extraction query for completed or future promotion
  advice rows and returns one stable row per promotion x sku x store candidate.
- Adds extraction lineage fields needed by downstream dataset, model, and
  reporting modules.
- Does not own artifact persistence, target definitions, or model semantics.
"""

import csv
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from typing import Literal

import pandas as pd

from data.promotions.mssql_query_executor import (
    PromotionChunkedQueryExecutionResult,
    PromotionMssqlQueryError,
    PromotionQueryExecutor,
    PromotionSqlChunkFetchProgress,
    PromotionSqlExecutionTelemetry,
    PromotionSqlSubphaseCallback,
)
from data.promotions.sql import (
    PromotionBaseQueryOptions,
    RenderedPromotionBaseQuery,
    render_promotion_base_query,
)
from runtime.promotions.completed_extraction_cost_model import (
    CompletedExtractionCostModelEstimator,
    CompletedExtractionCostModelSettings,
    CompletedExtractionPreflightMetrics,
)
from runtime.promotions.config import (
    DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS,
    DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS,
    PromotionArtifactPaths,
    PromotionCompletedPreflightPlannerSettings,
    PromotionPipelineSettings,
)


PromotionSelectionMode = Literal["completed", "future"]
PromotionPreflightPlannerVerdict = Literal[
    "SAFE_TO_EXTRACT",
    "TOO_WIDE_REPARTITION_REQUIRED",
    "INVALID_PARTITION_KEY",
]
PromotionPreflightCostGuardrailVerdict = Literal[
    "WITHIN_LIVE_TIMEOUT_BUDGET",
    "TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET",
    "NOT_APPLIED_COST_GUARDRAIL_DISABLED",
    "NOT_APPLIED_QUERY_TIMEOUT_DISABLED",
    "NOT_APPLIED_MISSING_PREFLIGHT_QUERY_EXECUTION_SECONDS",
    "NOT_EVALUATED_PREFLIGHT_FAILED",
]

_DATE_COLUMNS = (
    "promotion_start_date",
    "promotional_end_date",
    "promotion_start_date_date",
    "promotional_end_date_date",
    "ingested_at",
    "extracted_at_utc",
    "extraction_as_of_date",
)


@dataclass(frozen=True)
class PromotionExtractionManifest:
    run_id: str
    selection_mode: PromotionSelectionMode
    query_version: str
    as_of_date: str
    extracted_at_utc: str
    row_count: int
    column_count: int
    duplicate_promotion_row_keys: int
    advice_source_table: str
    realised_sales_source_table: str
    columns: tuple[str, ...]
    extraction_mode: str = "live_sql"
    fetch_mode: str = "full_fetch"
    chunk_mode: str = "full_fetch"
    chunk_count: int = 0
    completed_chunk_count: int = 0
    cumulative_rows_written: int = 0
    batch_count: int = 0
    finalized_batch_count: int = 0
    resumed_batch_count: int = 0
    rebuilt_batch_count: int = 0
    total_landed_rows: int = 0
    completion_state: str | None = None
    partition_completion_state: str | None = None
    resume_state: str | None = None
    skipped_due_to_existing_completion: bool = False
    promotion_row_key_checksum_sha256: str | None = None
    completed_sales_history_start_date: str | None = None
    staged_extraction_enabled: bool = False
    completed_extraction_stage_mode: str | None = None
    extraction_stage: str | None = None
    candidate_promotion_row_count: int | None = None
    partition_strategy: str | None = None
    partition_count: int | None = None
    partition_index: int | None = None
    child_partition_manifest_paths: tuple[str, ...] | None = None
    child_batch_manifest_paths: tuple[str, ...] | None = None
    child_batch_parquet_paths: tuple[str, ...] | None = None
    child_stage_manifest_paths: tuple[str, ...] | None = None
    child_stage_parquet_paths: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionBaseExtractionResult:
    base_frame: pd.DataFrame
    manifest: PromotionExtractionManifest
    telemetry: "PromotionExtractionTelemetry"


@dataclass(frozen=True)
class PromotionChunkedExtractionResult:
    manifest: PromotionExtractionManifest
    telemetry: "PromotionExtractionTelemetry"


@dataclass
class PromotionExtractionTelemetry:
    run_id: str
    selection_mode: PromotionSelectionMode
    as_of_date: str
    query_version: str | None = None
    extraction_mode: str = "live_sql"
    advice_source_table: str | None = None
    realised_sales_source_table: str | None = None
    rendered_query_parameter_summary: dict[str, object] = field(default_factory=dict)
    diagnostic_filter_summary: dict[str, object] = field(default_factory=dict)
    estimated_window_summary: dict[str, object] = field(default_factory=dict)
    partition_strategy: str | None = None
    partition_count: int | None = None
    partition_index: int | None = None
    query_render_started_at_utc: str | None = None
    query_render_completed_at_utc: str | None = None
    sql_connection_started_at_utc: str | None = None
    sql_connection_completed_at_utc: str | None = None
    query_execution_started_at_utc: str | None = None
    query_execution_completed_at_utc: str | None = None
    fetch_started_at_utc: str | None = None
    fetch_completed_at_utc: str | None = None
    dataframe_write_started_at_utc: str | None = None
    dataframe_write_completed_at_utc: str | None = None
    extracted_at_utc: str | None = None
    completed_at_utc: str | None = None
    candidate_promotion_row_count: int | None = None
    row_count: int | None = None
    column_count: int | None = None
    duplicate_promotion_row_keys: int | None = None
    extraction_status: str = "started"
    failure_stage: str | None = None
    failure_exception_type: str | None = None
    failure_message: str | None = None
    current_sql_subphase: str | None = None
    connect_timeout_seconds: int | None = None
    connect_retry_attempts: int = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS
    connect_retry_backoff_seconds: float = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS
    connect_attempt_count: int | None = None
    query_timeout_seconds: int | None = None
    query_timeout_applied: bool | None = None
    fetch_mode: str = "full_fetch"
    chunk_mode: str = "full_fetch"
    fetch_chunk_row_count: int | None = None
    chunk_count: int = 0
    completed_chunk_count: int = 0
    cumulative_rows_written: int = 0
    batch_count: int = 0
    finalized_batch_count: int = 0
    resumed_batch_count: int = 0
    rebuilt_batch_count: int = 0
    total_landed_rows: int = 0
    completion_state: str | None = None
    partition_completion_state: str | None = None
    resume_state: str | None = None
    skipped_due_to_existing_completion: bool = False
    promotion_row_key_checksum_sha256: str | None = None
    completed_sales_history_start_date: str | None = None
    staged_extraction_enabled: bool = False
    completed_extraction_stage_mode: str | None = None
    extraction_stage: str | None = None
    chunk_metrics: list[dict[str, object]] = field(default_factory=list)
    rendered_sql_path: str | None = None
    rendered_sql_parameters_path: str | None = None
    output_parquet_path: str | None = None
    output_manifest_path: str | None = None
    output_partition_progress_path: str | None = None
    output_partition_completion_path: str | None = None
    output_telemetry_json_path: str | None = None
    output_telemetry_csv_path: str | None = None
    output_sql_diagnostics_summary_json_path: str | None = None
    output_sql_diagnostics_summary_txt_path: str | None = None

    def apply_sql_execution_telemetry(self, telemetry: PromotionSqlExecutionTelemetry) -> None:
        self.sql_connection_started_at_utc = telemetry.sql_connection_started_at_utc
        self.sql_connection_completed_at_utc = telemetry.sql_connection_completed_at_utc
        self.query_execution_started_at_utc = telemetry.query_execution_started_at_utc
        self.query_execution_completed_at_utc = telemetry.query_execution_completed_at_utc
        self.fetch_started_at_utc = telemetry.fetch_started_at_utc
        self.fetch_completed_at_utc = telemetry.fetch_completed_at_utc
        self.current_sql_subphase = telemetry.current_sql_subphase
        self.connect_timeout_seconds = telemetry.connect_timeout_seconds
        self.connect_retry_attempts = telemetry.connect_retry_attempts
        self.connect_retry_backoff_seconds = telemetry.connect_retry_backoff_seconds
        self.connect_attempt_count = telemetry.connect_attempt_count
        self.query_timeout_seconds = telemetry.query_timeout_seconds
        self.query_timeout_applied = telemetry.query_timeout_applied
        self.fetch_mode = telemetry.fetch_mode
        self.fetch_chunk_row_count = telemetry.fetch_chunk_row_count
        self.chunk_count = telemetry.chunk_count
        self.completed_chunk_count = telemetry.completed_chunk_count
        self.cumulative_rows_written = telemetry.cumulative_fetched_row_count
        if telemetry.failure_stage is not None:
            self.failure_stage = telemetry.failure_stage
        if telemetry.failure_exception_type is not None:
            self.failure_exception_type = telemetry.failure_exception_type
        if telemetry.failure_message is not None:
            self.failure_message = telemetry.failure_message

    def mark_failure(self, error: BaseException, *, stage: str | None = None) -> None:
        self.extraction_status = "cancelled" if isinstance(error, KeyboardInterrupt) else "failed"
        self.failure_stage = stage or self.current_sql_subphase or self.failure_stage
        self.failure_exception_type = type(error).__name__
        self.failure_message = _normalize_error_message(error)
        self.completed_at_utc = _utc_now_iso()

    def mark_success(self) -> None:
        self.extraction_status = "succeeded"
        self.completed_at_utc = self.dataframe_write_completed_at_utc or _utc_now_iso()

    def phase_elapsed_seconds(self) -> dict[str, float | None]:
        return {
            "query_render": _elapsed_seconds(
                self.query_render_started_at_utc,
                self.query_render_completed_at_utc,
            ),
            "sql_connection": _elapsed_seconds(
                self.sql_connection_started_at_utc,
                self.sql_connection_completed_at_utc,
            ),
            "query_execution": _elapsed_seconds(
                self.query_execution_started_at_utc,
                self.query_execution_completed_at_utc,
            ),
            "fetch": _elapsed_seconds(
                self.fetch_started_at_utc,
                self.fetch_completed_at_utc,
            ),
            "dataframe_write": _elapsed_seconds(
                self.dataframe_write_started_at_utc,
                self.dataframe_write_completed_at_utc,
            ),
        }

    def total_elapsed_seconds(self) -> float | None:
        return _elapsed_seconds(self.query_render_started_at_utc, self.completed_at_utc)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["phase_elapsed_seconds"] = self.phase_elapsed_seconds()
        payload["total_elapsed_seconds"] = self.total_elapsed_seconds()
        payload["final_extracted_row_count"] = self.row_count
        return payload


@dataclass(frozen=True)
class PromotionSqlDiagnosticsSummary:
    run_id: str
    selection_mode: PromotionSelectionMode
    extraction_mode: str
    extraction_status: str
    current_sql_subphase: str | None
    failure_stage: str | None
    failure_exception_type: str | None
    failure_message: str | None
    as_of_date: str
    extracted_at_utc: str | None
    completed_at_utc: str | None
    query_version: str | None
    connect_timeout_seconds: int | None
    connect_retry_attempts: int
    connect_retry_backoff_seconds: float
    connect_attempt_count: int | None
    query_timeout_seconds: int | None
    query_timeout_applied: bool | None
    fetch_mode: str
    chunk_mode: str
    fetch_chunk_row_count: int | None
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
    completed_sales_history_start_date: str | None
    staged_extraction_enabled: bool
    completed_extraction_stage_mode: str | None
    extraction_stage: str | None
    server: str
    database: str
    schema: str
    advice_source_table: str
    realised_sales_source_table: str
    rendered_query_parameter_summary: dict[str, object]
    diagnostic_filter_summary: dict[str, object]
    query_windows: dict[str, object]
    partition_strategy: str | None
    partition_count: int | None
    partition_index: int | None
    candidate_promotion_row_count: int | None
    phase_elapsed_seconds: dict[str, float | None]
    total_elapsed_seconds: float | None
    row_count: int | None
    final_extracted_row_count: int | None
    column_count: int | None
    duplicate_promotion_row_keys: int | None
    promotion_row_key_checksum_sha256: str | None
    output_paths: dict[str, str | None]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = (
            f"run_id: {self.run_id}",
            f"selection_mode: {self.selection_mode}",
            f"extraction_mode: {self.extraction_mode}",
            f"extraction_status: {self.extraction_status}",
            f"current_sql_subphase: {self.current_sql_subphase or 'n/a'}",
            f"failure_stage: {self.failure_stage or 'n/a'}",
            f"failure_exception_type: {self.failure_exception_type or 'n/a'}",
            f"failure_message: {self.failure_message or 'n/a'}",
            f"as_of_date: {self.as_of_date}",
            f"query_version: {self.query_version or 'n/a'}",
            f"connect_timeout_seconds: {self.connect_timeout_seconds if self.connect_timeout_seconds is not None else 'n/a'}",
            f"connect_retry_attempts: {self.connect_retry_attempts}",
            f"connect_retry_backoff_seconds: {self.connect_retry_backoff_seconds}",
            f"connect_attempt_count: {self.connect_attempt_count if self.connect_attempt_count is not None else 'n/a'}",
            f"query_timeout_seconds: {self.query_timeout_seconds if self.query_timeout_seconds is not None else 'n/a'}",
            f"query_timeout_applied: {self.query_timeout_applied}",
            f"fetch_mode: {self.fetch_mode}",
            f"chunk_mode: {self.chunk_mode}",
            f"fetch_chunk_row_count: {self.fetch_chunk_row_count if self.fetch_chunk_row_count is not None else 'n/a'}",
            f"chunk_count: {self.chunk_count}",
            f"completed_chunk_count: {self.completed_chunk_count}",
            f"cumulative_rows_written: {self.cumulative_rows_written}",
            f"batch_count: {self.batch_count}",
            f"finalized_batch_count: {self.finalized_batch_count}",
            f"resumed_batch_count: {self.resumed_batch_count}",
            f"rebuilt_batch_count: {self.rebuilt_batch_count}",
            f"total_landed_rows: {self.total_landed_rows}",
            f"completion_state: {self.completion_state or 'n/a'}",
            f"partition_completion_state: {self.partition_completion_state or 'n/a'}",
            f"resume_state: {self.resume_state or 'n/a'}",
            f"skipped_due_to_existing_completion: {self.skipped_due_to_existing_completion}",
            (
                "completed_sales_history_start_date: "
                f"{self.completed_sales_history_start_date or 'n/a'}"
            ),
            f"staged_extraction_enabled: {self.staged_extraction_enabled}",
            (
                "completed_extraction_stage_mode: "
                f"{self.completed_extraction_stage_mode or 'n/a'}"
            ),
            f"extraction_stage: {self.extraction_stage or 'n/a'}",
            f"server: {self.server}",
            f"database: {self.database}",
            f"schema: {self.schema}",
            f"advice_source_table: {self.advice_source_table}",
            f"realised_sales_source_table: {self.realised_sales_source_table}",
            (
                "candidate_promotion_row_count: "
                f"{self.candidate_promotion_row_count if self.candidate_promotion_row_count is not None else 'n/a'}"
            ),
            f"row_count: {self.row_count if self.row_count is not None else 'n/a'}",
            (
                "final_extracted_row_count: "
                f"{self.final_extracted_row_count if self.final_extracted_row_count is not None else 'n/a'}"
            ),
            f"column_count: {self.column_count if self.column_count is not None else 'n/a'}",
            (
                "duplicate_promotion_row_keys: "
                f"{self.duplicate_promotion_row_keys if self.duplicate_promotion_row_keys is not None else 'n/a'}"
            ),
            (
                "promotion_row_key_checksum_sha256: "
                f"{self.promotion_row_key_checksum_sha256 or 'n/a'}"
            ),
            f"total_elapsed_seconds: {self.total_elapsed_seconds if self.total_elapsed_seconds is not None else 'n/a'}",
            f"phase_elapsed_seconds: {json.dumps(self.phase_elapsed_seconds, sort_keys=True)}",
            f"rendered_query_parameter_summary: {json.dumps(self.rendered_query_parameter_summary, sort_keys=True)}",
            f"diagnostic_filter_summary: {json.dumps(self.diagnostic_filter_summary, sort_keys=True)}",
            f"query_windows: {json.dumps(self.query_windows, sort_keys=True)}",
            f"partition_strategy: {self.partition_strategy or 'n/a'}",
            f"partition_count: {self.partition_count if self.partition_count is not None else 'n/a'}",
            f"partition_index: {self.partition_index if self.partition_index is not None else 'n/a'}",
            f"output_paths: {json.dumps(self.output_paths, sort_keys=True)}",
        )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class PromotionExtractionObservabilityArtifacts:
    telemetry_json_path: str
    telemetry_csv_path: str
    diagnostics_summary_json_path: str
    diagnostics_summary_txt_path: str


@dataclass(frozen=True)
class PromotionRenderedQueryArtifacts:
    sql_path: str
    parameters_path: str


@dataclass(frozen=True)
class PromotionPreflightPlannerDecision:
    verdict: PromotionPreflightPlannerVerdict
    reason: str
    recommended_partition_strategy: str | None
    recommended_partition_count: int | None
    constraint_results: dict[str, dict[str, object]]
    estimated_cost_score: float | None = None
    cost_guardrail_verdict: PromotionPreflightCostGuardrailVerdict | None = None
    cost_guardrail_reason: str | None = None
    observed_max_grouped_live_window_span_days: int | None = None
    observed_max_live_promo_days: int | None = None
    theoretical_completed_window_span_days_max: int | None = None
    estimated_extract_query_seconds: float | None = None
    fixed_overhead_seconds: float | None = None
    variable_cost_signal: float | None = None
    cost_model_version: str | None = None


@dataclass(frozen=True)
class PromotionExtractionPreflightSummary:
    run_id: str
    selection_mode: PromotionSelectionMode
    extraction_mode: str
    as_of_date: str
    query_version: str | None
    preflight_status: str
    verdict: PromotionPreflightPlannerVerdict
    reason: str
    rendered_query_parameter_summary: dict[str, object]
    diagnostic_filter_summary: dict[str, object]
    estimated_window_summary: dict[str, object]
    planner_thresholds: dict[str, int | float | None]
    constraint_results: dict[str, dict[str, object]]
    partition_strategy: str | None = None
    partition_count: int | None = None
    partition_index: int | None = None
    candidate_promotion_row_count: int | None = None
    candidate_store_sku_count: int | None = None
    candidate_window_count: int | None = None
    candidate_window_span_days_total: int | None = None
    candidate_window_span_days_max: int | None = None
    candidate_window_span_days_avg: float | None = None
    candidate_global_min_date: str | None = None
    candidate_global_max_date: str | None = None
    observed_max_grouped_live_window_span_days: int | None = None
    observed_max_live_promo_days: int | None = None
    theoretical_completed_window_span_days_max: int | None = None
    distinct_store_count: int | None = None
    distinct_sku_count: int | None = None
    estimated_cost_score: float | None = None
    estimated_extract_query_seconds: float | None = None
    fixed_overhead_seconds: float | None = None
    variable_cost_signal: float | None = None
    cost_model_version: str | None = None
    cost_guardrail_verdict: PromotionPreflightCostGuardrailVerdict | None = None
    cost_guardrail_reason: str | None = None
    recommended_partition_strategy: str | None = None
    recommended_partition_count: int | None = None
    query_timeout_seconds: int | None = None
    query_timeout_applied: bool | None = None
    phase_elapsed_seconds: dict[str, float | None] = field(default_factory=dict)
    total_elapsed_seconds: float | None = None
    failure_exception_type: str | None = None
    failure_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PromotionExtractionPreflightArtifacts:
    summary_json_path: str
    summary_csv_path: str
    rendered_sql_path: str
    rendered_sql_parameters_path: str


@dataclass(frozen=True)
class PromotionExtractionPreflightResult:
    summary: PromotionExtractionPreflightSummary
    artifacts: PromotionExtractionPreflightArtifacts


class PromotionBaseExtractor:
    """Extract promotion advice rows joined to realized and baseline behavior."""

    def __init__(self, *, executor: PromotionQueryExecutor) -> None:
        self._executor = executor

    def run_preflight(
        self,
        *,
        run_id: str,
        settings: PromotionPipelineSettings,
        selection_mode: PromotionSelectionMode,
        query_options: PromotionBaseQueryOptions | None = None,
        persist_rendered_preflight_artifacts: bool = True,
    ) -> PromotionExtractionPreflightResult:
        """Run the cheap transaction-scope preflight probe and persist its governed artifacts."""

        resolved_query_options = query_options or PromotionBaseQueryOptions()
        rendered_query = render_promotion_base_query(
            settings=settings,
            selection_mode=selection_mode,
            query_options=resolved_query_options,
        )
        rendered_artifacts = write_rendered_preflight_artifacts(
            run_id=run_id,
            artifact_paths=settings.artifacts,
            rendered_query=rendered_query,
            write_artifacts=persist_rendered_preflight_artifacts,
        )
        try:
            execution_result = self._executor.fetch_dataframe(
                sql=rendered_query.preflight_sql,
                parameters=rendered_query.parameters,
            )
            summary = build_extraction_preflight_summary(
                run_id=run_id,
                selection_mode=selection_mode,
                settings=settings,
                rendered_query=rendered_query,
                frame=execution_result.frame,
                sql_execution_telemetry=execution_result.telemetry,
                query_options=resolved_query_options,
            )
        except Exception as error:
            if not _is_invalid_partition_key_error(error, resolved_query_options):
                raise
            summary = build_extraction_preflight_summary_from_error(
                run_id=run_id,
                selection_mode=selection_mode,
                settings=settings,
                rendered_query=rendered_query,
                error=error,
                query_options=resolved_query_options,
            )
        summary_artifacts = write_extraction_preflight_summary(
            run_id=run_id,
            artifact_paths=settings.artifacts,
            summary=summary,
            rendered_artifacts=rendered_artifacts,
        )
        return PromotionExtractionPreflightResult(
            summary=summary,
            artifacts=summary_artifacts,
        )

    def extract(
        self,
        *,
        run_id: str,
        settings: PromotionPipelineSettings,
        selection_mode: PromotionSelectionMode,
        phase_callback: PromotionSqlSubphaseCallback | None = None,
        query_options: PromotionBaseQueryOptions | None = None,
        persist_rendered_query_artifacts: bool = True,
    ) -> PromotionBaseExtractionResult:
        """Execute the bounded extraction query and attach stable lineage fields."""

        telemetry = PromotionExtractionTelemetry(
            run_id=run_id,
            selection_mode=selection_mode,
            as_of_date=settings.as_of_date.isoformat(),
            advice_source_table=settings.sql.promotion_advice_table,
            realised_sales_source_table=settings.sql.pwlogd_table,
            connect_timeout_seconds=settings.sql.connect_timeout_seconds,
            connect_retry_attempts=settings.sql.connect_retry_attempts,
            connect_retry_backoff_seconds=settings.sql.connect_retry_backoff_seconds,
            query_timeout_seconds=settings.sql.query_timeout_seconds,
        )
        try:
            resolved_query_options = query_options or PromotionBaseQueryOptions()
            telemetry.current_sql_subphase = "SQL query render in progress"
            telemetry.query_render_started_at_utc = _utc_now_iso()
            _notify_phase(phase_callback, telemetry.current_sql_subphase)
            rendered_query = render_promotion_base_query(
                settings=settings,
                selection_mode=selection_mode,
                query_options=resolved_query_options,
            )
            telemetry.query_render_completed_at_utc = _utc_now_iso()
            telemetry.query_version = rendered_query.query_version
            telemetry.extraction_mode = rendered_query.extraction_mode
            telemetry.rendered_query_parameter_summary = dict(rendered_query.parameters)
            telemetry.diagnostic_filter_summary = dict(rendered_query.diagnostic_filter_summary)
            telemetry.estimated_window_summary = dict(rendered_query.estimated_window_summary)
            if resolved_query_options.completed_partition is not None:
                telemetry.partition_strategy = resolved_query_options.completed_partition.strategy
                telemetry.partition_count = resolved_query_options.completed_partition.partition_count
                telemetry.partition_index = resolved_query_options.completed_partition.partition_index
            if persist_rendered_query_artifacts:
                rendered_artifacts = write_rendered_query_artifacts(
                    run_id=run_id,
                    artifact_paths=settings.artifacts,
                    rendered_query=rendered_query,
                )
                telemetry.rendered_sql_path = rendered_artifacts.sql_path
                telemetry.rendered_sql_parameters_path = rendered_artifacts.parameters_path

            telemetry.current_sql_subphase = "candidate promotion row count probe"
            _notify_phase(phase_callback, telemetry.current_sql_subphase)
            candidate_count_result = self._executor.fetch_dataframe(
                sql=rendered_query.candidate_count_sql,
                parameters=rendered_query.parameters,
            )
            telemetry.candidate_promotion_row_count = _extract_candidate_count(
                candidate_count_result.frame
            )

            execution_result = self._executor.fetch_dataframe(
                sql=rendered_query.sql,
                parameters=rendered_query.parameters,
                phase_callback=phase_callback,
            )
            telemetry.apply_sql_execution_telemetry(execution_result.telemetry)
            telemetry.current_sql_subphase = "normalizing extracted promotion frame"

            extracted_at = datetime.now(tz=UTC)
            normalized = self._normalize_frame(
                frame=execution_result.frame,
                run_id=run_id,
                selection_mode=selection_mode,
                extracted_at=extracted_at,
                as_of_date=settings.as_of_date.isoformat(),
            )
            promotion_row_key_checksum = _compute_promotion_row_key_checksum(normalized)
            duplicate_count = int(
                normalized["promotion_row_key"].duplicated().sum()
                if "promotion_row_key" in normalized.columns
                else 0
            )
            telemetry.extracted_at_utc = extracted_at.isoformat()
            telemetry.row_count = len(normalized.index)
            telemetry.column_count = len(normalized.columns)
            telemetry.duplicate_promotion_row_keys = duplicate_count
            telemetry.total_landed_rows = len(normalized.index)
            telemetry.promotion_row_key_checksum_sha256 = promotion_row_key_checksum
            telemetry.extraction_status = "ready_to_write"
            manifest = PromotionExtractionManifest(
                run_id=run_id,
                selection_mode=selection_mode,
                query_version=rendered_query.query_version,
                as_of_date=settings.as_of_date.isoformat(),
                extracted_at_utc=extracted_at.isoformat(),
                row_count=len(normalized.index),
                column_count=len(normalized.columns),
                duplicate_promotion_row_keys=duplicate_count,
                advice_source_table=settings.sql.promotion_advice_table,
                realised_sales_source_table=settings.sql.pwlogd_table,
                columns=tuple(str(column_name) for column_name in normalized.columns),
                extraction_mode=telemetry.extraction_mode,
                fetch_mode=telemetry.fetch_mode,
                chunk_mode=telemetry.chunk_mode,
                chunk_count=telemetry.chunk_count,
                completed_chunk_count=telemetry.completed_chunk_count,
                cumulative_rows_written=telemetry.row_count or 0,
                batch_count=telemetry.batch_count,
                finalized_batch_count=telemetry.finalized_batch_count,
                resumed_batch_count=telemetry.resumed_batch_count,
                rebuilt_batch_count=telemetry.rebuilt_batch_count,
                total_landed_rows=telemetry.total_landed_rows,
                completion_state=telemetry.completion_state,
                partition_completion_state=telemetry.partition_completion_state,
                resume_state=telemetry.resume_state,
                skipped_due_to_existing_completion=telemetry.skipped_due_to_existing_completion,
                promotion_row_key_checksum_sha256=promotion_row_key_checksum,
                candidate_promotion_row_count=telemetry.candidate_promotion_row_count,
                partition_strategy=telemetry.partition_strategy,
                partition_count=telemetry.partition_count,
                partition_index=telemetry.partition_index,
            )
            return PromotionBaseExtractionResult(
                base_frame=normalized,
                manifest=manifest,
                telemetry=telemetry,
            )
        except Exception as error:
            sql_telemetry = getattr(error, "sql_execution_telemetry", None)
            if isinstance(sql_telemetry, PromotionSqlExecutionTelemetry):
                telemetry.apply_sql_execution_telemetry(sql_telemetry)
            telemetry.mark_failure(error)
            setattr(error, "promotion_extraction_telemetry", telemetry)
            raise

    def extract_in_chunks(
        self,
        *,
        run_id: str,
        settings: PromotionPipelineSettings,
        selection_mode: PromotionSelectionMode,
        chunk_row_count: int,
        chunk_consumer: callable,
        phase_callback: PromotionSqlSubphaseCallback | None = None,
        query_options: PromotionBaseQueryOptions | None = None,
        persist_rendered_query_artifacts: bool = True,
    ) -> PromotionChunkedExtractionResult:
        """Execute the bounded extraction query and hand normalized chunks to the caller."""

        telemetry = PromotionExtractionTelemetry(
            run_id=run_id,
            selection_mode=selection_mode,
            as_of_date=settings.as_of_date.isoformat(),
            advice_source_table=settings.sql.promotion_advice_table,
            realised_sales_source_table=settings.sql.pwlogd_table,
            connect_timeout_seconds=settings.sql.connect_timeout_seconds,
            connect_retry_attempts=settings.sql.connect_retry_attempts,
            connect_retry_backoff_seconds=settings.sql.connect_retry_backoff_seconds,
            query_timeout_seconds=settings.sql.query_timeout_seconds,
            fetch_mode="chunked_fetch",
            chunk_mode="chunked_fetch",
            fetch_chunk_row_count=chunk_row_count,
        )
        total_rows_written = 0
        duplicate_count = 0
        seen_promotion_row_keys: set[object] = set()
        normalized_columns: tuple[str, ...] | None = None
        promotion_row_key_digest = hashlib.sha256()
        promotion_row_key_seen = False
        extracted_at = datetime.now(tz=UTC)
        try:
            resolved_query_options = query_options or PromotionBaseQueryOptions()
            telemetry.current_sql_subphase = "SQL query render in progress"
            telemetry.query_render_started_at_utc = _utc_now_iso()
            _notify_phase(phase_callback, telemetry.current_sql_subphase)
            rendered_query = render_promotion_base_query(
                settings=settings,
                selection_mode=selection_mode,
                query_options=resolved_query_options,
            )
            telemetry.query_render_completed_at_utc = _utc_now_iso()
            telemetry.query_version = rendered_query.query_version
            telemetry.extraction_mode = rendered_query.extraction_mode
            telemetry.rendered_query_parameter_summary = dict(rendered_query.parameters)
            telemetry.diagnostic_filter_summary = dict(rendered_query.diagnostic_filter_summary)
            telemetry.estimated_window_summary = dict(rendered_query.estimated_window_summary)
            if resolved_query_options.completed_partition is not None:
                telemetry.partition_strategy = resolved_query_options.completed_partition.strategy
                telemetry.partition_count = resolved_query_options.completed_partition.partition_count
                telemetry.partition_index = resolved_query_options.completed_partition.partition_index
            if persist_rendered_query_artifacts:
                rendered_artifacts = write_rendered_query_artifacts(
                    run_id=run_id,
                    artifact_paths=settings.artifacts,
                    rendered_query=rendered_query,
                )
                telemetry.rendered_sql_path = rendered_artifacts.sql_path
                telemetry.rendered_sql_parameters_path = rendered_artifacts.parameters_path

            telemetry.current_sql_subphase = "candidate promotion row count probe"
            _notify_phase(phase_callback, telemetry.current_sql_subphase)
            candidate_count_result = self._executor.fetch_dataframe(
                sql=rendered_query.candidate_count_sql,
                parameters=rendered_query.parameters,
            )
            telemetry.candidate_promotion_row_count = _extract_candidate_count(
                candidate_count_result.frame
            )

            def _consume_chunk(frame: pd.DataFrame, chunk_progress: PromotionSqlChunkFetchProgress) -> None:
                nonlocal total_rows_written, duplicate_count, normalized_columns, promotion_row_key_seen
                normalized = self._normalize_frame(
                    frame=frame,
                    run_id=run_id,
                    selection_mode=selection_mode,
                    extracted_at=extracted_at,
                    as_of_date=settings.as_of_date.isoformat(),
                )
                current_columns = tuple(str(column_name) for column_name in normalized.columns)
                if normalized_columns is None:
                    normalized_columns = current_columns
                elif current_columns != normalized_columns:
                    raise ValueError(
                        "Chunked promotions extraction changed columns mid-partition."
                    )
                if "promotion_row_key" in normalized.columns:
                    promotion_row_key_seen = True
                    _update_promotion_row_key_checksum(
                        promotion_row_key_digest,
                        normalized["promotion_row_key"].tolist(),
                    )
                    for row_key in normalized["promotion_row_key"].tolist():
                        if row_key in seen_promotion_row_keys:
                            duplicate_count += 1
                        else:
                            seen_promotion_row_keys.add(row_key)
                chunk_consumer(normalized, chunk_progress)
                total_rows_written += len(normalized.index)
                telemetry.chunk_count = chunk_progress.chunk_index
                telemetry.completed_chunk_count = chunk_progress.chunk_index
                telemetry.cumulative_rows_written = total_rows_written
                telemetry.chunk_metrics.append(
                    {
                        "chunk_index": chunk_progress.chunk_index,
                        "chunk_row_count": chunk_progress.chunk_row_count,
                        "cumulative_row_count": chunk_progress.cumulative_row_count,
                        "chunk_fetch_seconds": chunk_progress.chunk_fetch_seconds,
                        "cumulative_elapsed_seconds": chunk_progress.cumulative_elapsed_seconds,
                    }
                )

            execution_result = self._executor.fetch_dataframe_in_chunks(
                sql=rendered_query.sql,
                parameters=rendered_query.parameters,
                chunk_row_count=chunk_row_count,
                chunk_consumer=_consume_chunk,
                phase_callback=phase_callback,
            )
            telemetry.apply_sql_execution_telemetry(execution_result.telemetry)
            telemetry.current_sql_subphase = "finalizing chunked promotion extraction"
            telemetry.extracted_at_utc = extracted_at.isoformat()
            telemetry.row_count = total_rows_written
            telemetry.column_count = len(normalized_columns or execution_result.columns)
            telemetry.duplicate_promotion_row_keys = duplicate_count
            telemetry.total_landed_rows = total_rows_written
            telemetry.promotion_row_key_checksum_sha256 = (
                promotion_row_key_digest.hexdigest() if promotion_row_key_seen else None
            )
            telemetry.extraction_status = "ready_to_write"
            manifest = PromotionExtractionManifest(
                run_id=run_id,
                selection_mode=selection_mode,
                query_version=rendered_query.query_version,
                as_of_date=settings.as_of_date.isoformat(),
                extracted_at_utc=extracted_at.isoformat(),
                row_count=total_rows_written,
                column_count=len(normalized_columns or execution_result.columns),
                duplicate_promotion_row_keys=duplicate_count,
                advice_source_table=settings.sql.promotion_advice_table,
                realised_sales_source_table=settings.sql.pwlogd_table,
                columns=normalized_columns or execution_result.columns,
                extraction_mode=telemetry.extraction_mode,
                fetch_mode=telemetry.fetch_mode,
                chunk_mode=telemetry.chunk_mode,
                chunk_count=telemetry.chunk_count,
                completed_chunk_count=telemetry.completed_chunk_count,
                cumulative_rows_written=telemetry.cumulative_rows_written,
                batch_count=telemetry.batch_count,
                finalized_batch_count=telemetry.finalized_batch_count,
                resumed_batch_count=telemetry.resumed_batch_count,
                rebuilt_batch_count=telemetry.rebuilt_batch_count,
                total_landed_rows=telemetry.total_landed_rows,
                completion_state=telemetry.completion_state,
                partition_completion_state=telemetry.partition_completion_state,
                resume_state=telemetry.resume_state,
                skipped_due_to_existing_completion=telemetry.skipped_due_to_existing_completion,
                promotion_row_key_checksum_sha256=telemetry.promotion_row_key_checksum_sha256,
                candidate_promotion_row_count=telemetry.candidate_promotion_row_count,
                partition_strategy=telemetry.partition_strategy,
                partition_count=telemetry.partition_count,
                partition_index=telemetry.partition_index,
            )
            return PromotionChunkedExtractionResult(
                manifest=manifest,
                telemetry=telemetry,
            )
        except Exception as error:
            sql_telemetry = getattr(error, "sql_execution_telemetry", None)
            if isinstance(sql_telemetry, PromotionSqlExecutionTelemetry):
                telemetry.apply_sql_execution_telemetry(sql_telemetry)
            telemetry.mark_failure(error)
            setattr(error, "promotion_extraction_telemetry", telemetry)
            raise

    def _normalize_frame(
        self,
        *,
        frame: pd.DataFrame,
        run_id: str,
        selection_mode: PromotionSelectionMode,
        extracted_at: datetime,
        as_of_date: str,
    ) -> pd.DataFrame:
        """Standardize extraction lineage and datetime columns for downstream reuse."""

        normalized = frame.copy()
        for column_name in _DATE_COLUMNS:
            if column_name in normalized.columns:
                normalized[column_name] = pd.to_datetime(
                    normalized[column_name],
                    utc=False,
                    errors="coerce",
                )
        normalized["extraction_run_id"] = run_id
        normalized["extraction_selection_mode"] = selection_mode
        normalized["extraction_materialized_at_utc"] = extracted_at.isoformat()
        normalized["extraction_materialized_as_of_date"] = as_of_date
        return normalized


def build_sql_diagnostics_summary(
    *,
    telemetry: PromotionExtractionTelemetry,
    settings: PromotionPipelineSettings,
) -> PromotionSqlDiagnosticsSummary:
    return PromotionSqlDiagnosticsSummary(
        run_id=telemetry.run_id,
        selection_mode=telemetry.selection_mode,
        extraction_mode=telemetry.extraction_mode,
        extraction_status=telemetry.extraction_status,
        current_sql_subphase=telemetry.current_sql_subphase,
        failure_stage=telemetry.failure_stage,
        failure_exception_type=telemetry.failure_exception_type,
        failure_message=telemetry.failure_message,
        as_of_date=telemetry.as_of_date,
        extracted_at_utc=telemetry.extracted_at_utc,
        completed_at_utc=telemetry.completed_at_utc,
        query_version=telemetry.query_version,
        connect_timeout_seconds=telemetry.connect_timeout_seconds,
        connect_retry_attempts=telemetry.connect_retry_attempts,
        connect_retry_backoff_seconds=telemetry.connect_retry_backoff_seconds,
        connect_attempt_count=telemetry.connect_attempt_count,
        query_timeout_seconds=telemetry.query_timeout_seconds,
        query_timeout_applied=telemetry.query_timeout_applied,
        fetch_mode=telemetry.fetch_mode,
        chunk_mode=telemetry.chunk_mode,
        fetch_chunk_row_count=telemetry.fetch_chunk_row_count,
        chunk_count=telemetry.chunk_count,
        completed_chunk_count=telemetry.completed_chunk_count,
        cumulative_rows_written=telemetry.cumulative_rows_written,
        batch_count=telemetry.batch_count,
        finalized_batch_count=telemetry.finalized_batch_count,
        resumed_batch_count=telemetry.resumed_batch_count,
        rebuilt_batch_count=telemetry.rebuilt_batch_count,
        total_landed_rows=telemetry.total_landed_rows,
        completion_state=telemetry.completion_state,
        partition_completion_state=telemetry.partition_completion_state,
        resume_state=telemetry.resume_state,
        skipped_due_to_existing_completion=telemetry.skipped_due_to_existing_completion,
        completed_sales_history_start_date=telemetry.completed_sales_history_start_date,
        staged_extraction_enabled=telemetry.staged_extraction_enabled,
        completed_extraction_stage_mode=telemetry.completed_extraction_stage_mode,
        extraction_stage=telemetry.extraction_stage,
        server=settings.sql.server,
        database=settings.sql.database,
        schema=settings.sql.schema,
        advice_source_table=settings.sql.promotion_advice_table,
        realised_sales_source_table=settings.sql.pwlogd_table,
        rendered_query_parameter_summary=dict(telemetry.rendered_query_parameter_summary),
        diagnostic_filter_summary=dict(telemetry.diagnostic_filter_summary),
        query_windows=(
            dict(telemetry.estimated_window_summary)
            if telemetry.estimated_window_summary
            else {
                "baseline_lookback_days": settings.windows.baseline_lookback_days,
                "short_baseline_days": settings.windows.short_baseline_days,
                "immediate_baseline_days": settings.windows.immediate_baseline_days,
                "post_promo_days": settings.windows.post_promo_days,
                "completed_promotion_buffer_days": settings.completed_promotion_buffer_days,
                "as_of_date": settings.as_of_date.isoformat(),
            }
        ),
        partition_strategy=telemetry.partition_strategy,
        partition_count=telemetry.partition_count,
        partition_index=telemetry.partition_index,
        candidate_promotion_row_count=telemetry.candidate_promotion_row_count,
        phase_elapsed_seconds=telemetry.phase_elapsed_seconds(),
        total_elapsed_seconds=telemetry.total_elapsed_seconds(),
        row_count=telemetry.row_count,
        final_extracted_row_count=telemetry.row_count,
        column_count=telemetry.column_count,
        duplicate_promotion_row_keys=telemetry.duplicate_promotion_row_keys,
        promotion_row_key_checksum_sha256=telemetry.promotion_row_key_checksum_sha256,
        output_paths={
            "rendered_sql_path": telemetry.rendered_sql_path,
            "rendered_sql_parameters_path": telemetry.rendered_sql_parameters_path,
            "base_path": telemetry.output_parquet_path,
            "manifest_path": telemetry.output_manifest_path,
            "partition_progress_path": telemetry.output_partition_progress_path,
            "partition_completion_path": telemetry.output_partition_completion_path,
            "telemetry_json_path": telemetry.output_telemetry_json_path,
            "telemetry_csv_path": telemetry.output_telemetry_csv_path,
            "sql_diagnostics_summary_json_path": telemetry.output_sql_diagnostics_summary_json_path,
            "sql_diagnostics_summary_txt_path": telemetry.output_sql_diagnostics_summary_txt_path,
        },
    )


def write_extraction_observability(
    *,
    telemetry: PromotionExtractionTelemetry,
    settings: PromotionPipelineSettings,
    artifact_paths: PromotionArtifactPaths,
) -> PromotionExtractionObservabilityArtifacts:
    telemetry_json_path = artifact_paths.extraction_telemetry_json_path(telemetry.run_id)
    telemetry_csv_path = artifact_paths.extraction_telemetry_csv_path(telemetry.run_id)
    diagnostics_json_path = artifact_paths.sql_diagnostics_summary_json_path(telemetry.run_id)
    diagnostics_txt_path = artifact_paths.sql_diagnostics_summary_txt_path(telemetry.run_id)

    telemetry.output_telemetry_json_path = str(telemetry_json_path)
    telemetry.output_telemetry_csv_path = str(telemetry_csv_path)
    telemetry.output_sql_diagnostics_summary_json_path = str(diagnostics_json_path)
    telemetry.output_sql_diagnostics_summary_txt_path = str(diagnostics_txt_path)

    telemetry_payload = telemetry.to_dict()
    diagnostics_summary = build_sql_diagnostics_summary(
        telemetry=telemetry,
        settings=settings,
    )

    telemetry_json_path.parent.mkdir(parents=True, exist_ok=True)
    telemetry_csv_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_json_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_txt_path.parent.mkdir(parents=True, exist_ok=True)

    telemetry_json_path.write_text(
        json.dumps(telemetry_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_flat_csv_row(telemetry_csv_path, telemetry_payload)
    diagnostics_json_path.write_text(
        json.dumps(diagnostics_summary.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    diagnostics_txt_path.write_text(
        diagnostics_summary.to_text(),
        encoding="utf-8",
    )
    return PromotionExtractionObservabilityArtifacts(
        telemetry_json_path=str(telemetry_json_path),
        telemetry_csv_path=str(telemetry_csv_path),
        diagnostics_summary_json_path=str(diagnostics_json_path),
        diagnostics_summary_txt_path=str(diagnostics_txt_path),
    )


def _compute_promotion_row_key_checksum(frame: pd.DataFrame) -> str | None:
    if "promotion_row_key" not in frame.columns:
        return None
    digest = hashlib.sha256()
    _update_promotion_row_key_checksum(digest, frame["promotion_row_key"].tolist())
    return digest.hexdigest()


def _update_promotion_row_key_checksum(
    digest: "hashlib._Hash",
    row_keys: list[object],
) -> None:
    for row_key in row_keys:
        digest.update(str(row_key).encode("utf-8"))
        digest.update(b"\n")


def write_rendered_query_artifacts(
    *,
    run_id: str,
    artifact_paths: PromotionArtifactPaths,
    rendered_query: RenderedPromotionBaseQuery,
) -> PromotionRenderedQueryArtifacts:
    run_root = artifact_paths.manifests_run_root(run_id)
    sql_path = run_root / "rendered_sql.sql"
    parameters_path = run_root / "rendered_sql_parameters.json"
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    parameters_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.write_text(rendered_query.sql, encoding="utf-8")
    parameters_path.write_text(
        json.dumps(rendered_query.parameters, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return PromotionRenderedQueryArtifacts(
        sql_path=str(sql_path),
        parameters_path=str(parameters_path),
    )


def write_rendered_preflight_artifacts(
    *,
    run_id: str,
    artifact_paths: PromotionArtifactPaths,
    rendered_query: RenderedPromotionBaseQuery,
    write_artifacts: bool = True,
) -> PromotionRenderedQueryArtifacts:
    sql_path = artifact_paths.rendered_preflight_sql_path(run_id)
    parameters_path = artifact_paths.rendered_preflight_sql_parameters_path(run_id)
    if write_artifacts:
        sql_path.parent.mkdir(parents=True, exist_ok=True)
        parameters_path.parent.mkdir(parents=True, exist_ok=True)
        sql_path.write_text(rendered_query.preflight_sql, encoding="utf-8")
        parameters_path.write_text(
            json.dumps(rendered_query.parameters, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return PromotionRenderedQueryArtifacts(
        sql_path=str(sql_path),
        parameters_path=str(parameters_path),
    )


def write_extraction_preflight_summary(
    *,
    run_id: str,
    artifact_paths: PromotionArtifactPaths,
    summary: PromotionExtractionPreflightSummary,
    rendered_artifacts: PromotionRenderedQueryArtifacts,
) -> PromotionExtractionPreflightArtifacts:
    summary_json_path = artifact_paths.extraction_preflight_summary_json_path(run_id)
    summary_csv_path = artifact_paths.extraction_preflight_summary_csv_path(run_id)
    summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_flat_csv_row(summary_csv_path, summary.to_dict())
    return PromotionExtractionPreflightArtifacts(
        summary_json_path=str(summary_json_path),
        summary_csv_path=str(summary_csv_path),
        rendered_sql_path=rendered_artifacts.sql_path,
        rendered_sql_parameters_path=rendered_artifacts.parameters_path,
    )


def build_extraction_preflight_summary(
    *,
    run_id: str,
    selection_mode: PromotionSelectionMode,
    settings: PromotionPipelineSettings,
    rendered_query: RenderedPromotionBaseQuery,
    frame: pd.DataFrame,
    sql_execution_telemetry: PromotionSqlExecutionTelemetry,
    query_options: PromotionBaseQueryOptions,
) -> PromotionExtractionPreflightSummary:
    metrics = _extract_preflight_metrics(frame)
    planner_settings = settings.completed_preflight_planner
    decision = _plan_preflight_verdict(
        selection_mode=selection_mode,
        planner_settings=planner_settings,
        settings=settings,
        query_options=query_options,
        metrics=metrics,
        sql_execution_telemetry=sql_execution_telemetry,
    )
    telemetry_payload = sql_execution_telemetry.to_dict()
    return PromotionExtractionPreflightSummary(
        run_id=run_id,
        selection_mode=selection_mode,
        extraction_mode=rendered_query.extraction_mode,
        as_of_date=settings.as_of_date.isoformat(),
        query_version=rendered_query.query_version,
        preflight_status="succeeded",
        verdict=decision.verdict,
        reason=decision.reason,
        rendered_query_parameter_summary=dict(rendered_query.parameters),
        diagnostic_filter_summary=dict(rendered_query.diagnostic_filter_summary),
        estimated_window_summary=dict(rendered_query.estimated_window_summary),
        planner_thresholds={
            **_resolve_preflight_thresholds_for_summary(
                selection_mode=selection_mode,
                planner_settings=planner_settings,
                decision=decision,
            ),
            **planner_settings.cost_guardrail_dict(),
        },
        constraint_results=decision.constraint_results,
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
        candidate_promotion_row_count=metrics["candidate_promotion_row_count"],
        candidate_store_sku_count=metrics["candidate_store_sku_count"],
        candidate_window_count=metrics["candidate_window_count"],
        candidate_window_span_days_total=metrics["candidate_window_span_days_total"],
        candidate_window_span_days_max=metrics["candidate_window_span_days_max"],
        candidate_window_span_days_avg=metrics["candidate_window_span_days_avg"],
        candidate_global_min_date=metrics["candidate_global_min_date"],
        candidate_global_max_date=metrics["candidate_global_max_date"],
        observed_max_grouped_live_window_span_days=(
            decision.observed_max_grouped_live_window_span_days
        ),
        observed_max_live_promo_days=decision.observed_max_live_promo_days,
        theoretical_completed_window_span_days_max=(
            decision.theoretical_completed_window_span_days_max
        ),
        distinct_store_count=metrics["distinct_store_count"],
        distinct_sku_count=metrics["distinct_sku_count"],
        estimated_cost_score=decision.estimated_cost_score,
        estimated_extract_query_seconds=decision.estimated_extract_query_seconds,
        fixed_overhead_seconds=decision.fixed_overhead_seconds,
        variable_cost_signal=decision.variable_cost_signal,
        cost_model_version=decision.cost_model_version,
        cost_guardrail_verdict=decision.cost_guardrail_verdict,
        cost_guardrail_reason=decision.cost_guardrail_reason,
        recommended_partition_strategy=decision.recommended_partition_strategy,
        recommended_partition_count=decision.recommended_partition_count,
        query_timeout_seconds=sql_execution_telemetry.query_timeout_seconds,
        query_timeout_applied=sql_execution_telemetry.query_timeout_applied,
        phase_elapsed_seconds=telemetry_payload["phase_elapsed_seconds"],
        total_elapsed_seconds=_sum_elapsed_seconds(telemetry_payload["phase_elapsed_seconds"]),
    )


def build_extraction_preflight_summary_from_error(
    *,
    run_id: str,
    selection_mode: PromotionSelectionMode,
    settings: PromotionPipelineSettings,
    rendered_query: RenderedPromotionBaseQuery,
    error: BaseException,
    query_options: PromotionBaseQueryOptions,
) -> PromotionExtractionPreflightSummary:
    sql_execution_telemetry = getattr(error, "sql_execution_telemetry", None)
    phase_elapsed_seconds = (
        sql_execution_telemetry.to_dict()["phase_elapsed_seconds"]
        if isinstance(sql_execution_telemetry, PromotionSqlExecutionTelemetry)
        else {"sql_connection": None, "query_execution": None, "fetch": None}
    )
    partition_strategy = (
        query_options.completed_partition.strategy
        if query_options.completed_partition is not None
        else None
    )
    reason = (
        f"Partition strategy '{partition_strategy}' is not valid against the current advice source. "
        f"{_normalize_error_message(error)}"
        if partition_strategy is not None
        else _normalize_error_message(error)
    )
    return PromotionExtractionPreflightSummary(
        run_id=run_id,
        selection_mode=selection_mode,
        extraction_mode=rendered_query.extraction_mode,
        as_of_date=settings.as_of_date.isoformat(),
        query_version=rendered_query.query_version,
        preflight_status="failed",
        verdict="INVALID_PARTITION_KEY",
        reason=reason,
        rendered_query_parameter_summary=dict(rendered_query.parameters),
        diagnostic_filter_summary=dict(rendered_query.diagnostic_filter_summary),
        estimated_window_summary=dict(rendered_query.estimated_window_summary),
        planner_thresholds={
            **settings.completed_preflight_planner.thresholds_dict(),
            **settings.completed_preflight_planner.cost_guardrail_dict(),
        },
        constraint_results={},
        partition_strategy=partition_strategy,
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
        failure_exception_type=type(error).__name__,
        failure_message=_normalize_error_message(error),
        observed_max_grouped_live_window_span_days=None,
        observed_max_live_promo_days=None,
        theoretical_completed_window_span_days_max=None,
        estimated_cost_score=None,
        estimated_extract_query_seconds=None,
        fixed_overhead_seconds=None,
        variable_cost_signal=None,
        cost_model_version=None,
        cost_guardrail_verdict="NOT_EVALUATED_PREFLIGHT_FAILED",
        cost_guardrail_reason="Cost guardrail was not evaluated because the preflight probe failed.",
        query_timeout_seconds=(
            sql_execution_telemetry.query_timeout_seconds
            if isinstance(sql_execution_telemetry, PromotionSqlExecutionTelemetry)
            else settings.sql.query_timeout_seconds
        ),
        query_timeout_applied=(
            sql_execution_telemetry.query_timeout_applied
            if isinstance(sql_execution_telemetry, PromotionSqlExecutionTelemetry)
            else None
        ),
        phase_elapsed_seconds=phase_elapsed_seconds,
        total_elapsed_seconds=_sum_elapsed_seconds(phase_elapsed_seconds),
    )


def _notify_phase(
    phase_callback: PromotionSqlSubphaseCallback | None,
    phase_name: str,
) -> None:
    if phase_callback is not None:
        phase_callback(phase_name)


def _write_flat_csv_row(path: Path, payload: dict[str, object]) -> None:
    flattened = {key: _csv_safe_value(value) for key, value in payload.items()}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(flattened.keys()))
        writer.writeheader()
        writer.writerow(flattened)


def _csv_safe_value(value: object) -> object:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return value


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _elapsed_seconds(started_at_utc: str | None, completed_at_utc: str | None) -> float | None:
    if started_at_utc is None or completed_at_utc is None:
        return None
    started_at = datetime.fromisoformat(started_at_utc)
    completed_at = datetime.fromisoformat(completed_at_utc)
    return round((completed_at - started_at).total_seconds(), 3)


def _normalize_error_message(error: BaseException) -> str:
    message = str(error).strip()
    if not message:
        return error.__class__.__name__
    return " ".join(message.split())


def _extract_candidate_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    candidate_value = frame.iloc[0, 0]
    try:
        return int(candidate_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Unable to coerce candidate promotion row count from value {candidate_value!r}."
        ) from error


def _extract_preflight_metrics(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        row: dict[str, object] = {}
    else:
        row = frame.iloc[0].to_dict()
    return {
        "candidate_promotion_row_count": _coerce_optional_int(
            row.get("candidate_promotion_row_count")
        ),
        "candidate_store_sku_count": _coerce_optional_int(row.get("candidate_store_sku_count")),
        "candidate_window_count": _coerce_optional_int(row.get("candidate_window_count")),
        "candidate_window_span_days_total": _coerce_optional_int(
            row.get("candidate_window_span_days_total")
        ),
        "candidate_window_span_days_max": _coerce_optional_int(
            row.get("candidate_window_span_days_max")
        ),
        "candidate_window_span_days_avg": _coerce_optional_float(
            row.get("candidate_window_span_days_avg")
        ),
        "candidate_global_min_date": _coerce_optional_date(row.get("candidate_global_min_date")),
        "candidate_global_max_date": _coerce_optional_date(row.get("candidate_global_max_date")),
        "observed_max_grouped_live_window_span_days": _coerce_optional_int(
            row.get("observed_max_grouped_live_window_span_days")
        ),
        "observed_max_live_promo_days": _coerce_optional_int(
            row.get("observed_max_live_promo_days")
        ),
        "distinct_store_count": _coerce_optional_int(row.get("distinct_store_count")),
        "distinct_sku_count": _coerce_optional_int(row.get("distinct_sku_count")),
    }


def _plan_preflight_verdict(
    *,
    selection_mode: PromotionSelectionMode,
    planner_settings: PromotionCompletedPreflightPlannerSettings,
    settings: PromotionPipelineSettings,
    query_options: PromotionBaseQueryOptions,
    metrics: dict[str, object],
    sql_execution_telemetry: PromotionSqlExecutionTelemetry,
) -> PromotionPreflightPlannerDecision:
    if selection_mode != "completed":
        return PromotionPreflightPlannerDecision(
            verdict="SAFE_TO_EXTRACT",
            reason="Preflight planner thresholds are enforced only for completed extraction mode.",
            recommended_partition_strategy=None,
            recommended_partition_count=None,
            constraint_results={},
            observed_max_grouped_live_window_span_days=None,
            observed_max_live_promo_days=None,
            theoretical_completed_window_span_days_max=None,
        )

    constraint_results: dict[str, dict[str, object]] = {}
    observed_max_grouped_live_window_span_days = _coerce_optional_int(
        metrics.get("observed_max_grouped_live_window_span_days")
    )
    observed_max_live_promo_days = _coerce_optional_int(
        metrics.get("observed_max_live_promo_days")
    )
    theoretical_completed_window_span_days_max = _resolve_theoretical_completed_window_span_days_max(
        settings=settings,
        observed_max_grouped_live_window_span_days=observed_max_grouped_live_window_span_days,
        fallback_threshold=planner_settings.max_window_span_days_max,
    )
    threshold_map = {
        "candidate_promotion_row_count": planner_settings.max_candidate_promotion_rows,
        "candidate_store_sku_count": planner_settings.max_candidate_store_sku,
        "candidate_window_span_days_total": planner_settings.max_window_span_days_total,
        "candidate_window_span_days_max": theoretical_completed_window_span_days_max,
    }
    for metric_name, threshold in threshold_map.items():
        observed = metrics.get(metric_name)
        observed_value = float(observed) if isinstance(observed, (int, float)) else None
        threshold_value = float(threshold) if threshold is not None else None
        ratio = (
            round(observed_value / threshold_value, 3)
            if observed_value is not None and threshold_value not in (None, 0.0)
            else None
        )
        is_over_limit = (
            observed_value is not None
            and threshold_value is not None
            and observed_value > threshold_value
        )
        constraint_results[metric_name] = {
            "observed": observed,
            "threshold": threshold,
            "status": "over_limit" if is_over_limit else "within_limit",
            "overage_ratio": ratio,
        }
        if metric_name == "candidate_window_span_days_max":
            constraint_results[metric_name]["threshold_reason"] = (
                _build_completed_window_span_threshold_reason(
                    settings=settings,
                    observed_value=_coerce_optional_int(observed),
                    observed_max_grouped_live_window_span_days=(
                        observed_max_grouped_live_window_span_days
                    ),
                    observed_max_live_promo_days=observed_max_live_promo_days,
                    theoretical_completed_window_span_days_max=(
                        theoretical_completed_window_span_days_max
                    ),
                )
            )

    (
        estimated_cost_score,
        cost_guardrail_verdict,
        cost_guardrail_reason,
        cost_overage_ratio,
        cost_model_payload,
    ) = _estimate_cost_guardrail(
        planner_settings=planner_settings,
        metrics=metrics,
        sql_execution_telemetry=sql_execution_telemetry,
    )
    if cost_guardrail_verdict is None:
        cost_constraint_status = "not_applicable"
    elif cost_guardrail_verdict == "TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET":
        cost_constraint_status = "over_limit"
    elif cost_guardrail_verdict == "WITHIN_LIVE_TIMEOUT_BUDGET":
        cost_constraint_status = "within_limit"
    else:
        cost_constraint_status = "not_applicable"
    constraint_results["estimated_cost_score"] = {
        "observed": estimated_cost_score,
        "threshold": planner_settings.max_estimated_cost_score,
        "status": cost_constraint_status,
        "overage_ratio": cost_overage_ratio,
        "reason": cost_guardrail_reason,
    }

    over_limit_constraints = [
        (metric_name, payload)
        for metric_name, payload in constraint_results.items()
        if payload["status"] == "over_limit"
    ]
    if not over_limit_constraints:
        safe_reason = (
            "Observed transaction-scope metrics are within the configured preflight planner thresholds "
            "and the estimated live timeout cost is within budget."
            if cost_guardrail_verdict == "WITHIN_LIVE_TIMEOUT_BUDGET"
            else (
                "Observed transaction-scope metrics are within the configured preflight planner thresholds. "
                f"{cost_guardrail_reason}"
                if cost_guardrail_reason is not None
                else "Observed transaction-scope metrics are within the configured preflight planner thresholds."
            )
        )
        return PromotionPreflightPlannerDecision(
            verdict="SAFE_TO_EXTRACT",
            reason=_append_completed_window_span_reason(
                safe_reason=safe_reason,
                settings=settings,
                observed_window_span_days_max=_coerce_optional_int(
                    metrics.get("candidate_window_span_days_max")
                ),
                observed_max_grouped_live_window_span_days=(
                    observed_max_grouped_live_window_span_days
                ),
                observed_max_live_promo_days=observed_max_live_promo_days,
                theoretical_completed_window_span_days_max=(
                    theoretical_completed_window_span_days_max
                ),
                exceeded=False,
            ),
            recommended_partition_strategy=None,
            recommended_partition_count=None,
            constraint_results=constraint_results,
            estimated_cost_score=estimated_cost_score,
            estimated_extract_query_seconds=(
                _coerce_optional_float(cost_model_payload.get("estimated_extract_query_seconds"))
                if cost_model_payload is not None
                else None
            ),
            fixed_overhead_seconds=(
                _coerce_optional_float(cost_model_payload.get("fixed_overhead_seconds"))
                if cost_model_payload is not None
                else None
            ),
            variable_cost_signal=(
                _coerce_optional_float(cost_model_payload.get("variable_cost_signal"))
                if cost_model_payload is not None
                else None
            ),
            cost_model_version=(
                str(cost_model_payload.get("model_version"))
                if cost_model_payload is not None
                and cost_model_payload.get("model_version") is not None
                else None
            ),
            cost_guardrail_verdict=cost_guardrail_verdict,
            cost_guardrail_reason=cost_guardrail_reason,
            observed_max_grouped_live_window_span_days=(
                observed_max_grouped_live_window_span_days
            ),
            observed_max_live_promo_days=observed_max_live_promo_days,
            theoretical_completed_window_span_days_max=(
                theoretical_completed_window_span_days_max
            ),
        )

    dominant_metric_name, dominant_constraint = max(
        over_limit_constraints,
        key=lambda item: float(item[1]["overage_ratio"] or 0.0),
    )
    current_partition_count = (
        query_options.completed_partition.partition_count
        if query_options.completed_partition is not None
        else 1
    )
    recommended_partition_strategy = (
        query_options.completed_partition.strategy
        if query_options.completed_partition is not None
        else planner_settings.default_partition_strategy
    )
    dominant_ratio = float(dominant_constraint["overage_ratio"] or 1.0)
    # Per-row width metrics like candidate_window_span_days_max cannot be
    # reduced by partitioning (each surviving row still has its own window),
    # so we keep the proportional formula exactly as-is for that case and
    # fail loudly once the cap is reached. For volumetric metrics we apply a
    # skew-safety multiplier so a single retry escapes hash-bucket skew
    # instead of creeping up by 1-2 partitions per attempt.
    skew_sensitive = dominant_metric_name != "candidate_window_span_days_max"
    safety_multiplier = (
        float(planner_settings.repartition_skew_safety_multiplier)
        if skew_sensitive
        else 1.0
    )
    proportional_bump = math.ceil(
        current_partition_count * dominant_ratio * safety_multiplier
    )
    recommended_partition_count = max(
        current_partition_count + 1,
        proportional_bump,
    )
    if dominant_metric_name == "estimated_cost_score" and cost_guardrail_reason is not None:
        reason = (
            f"{cost_guardrail_reason} Recommend {recommended_partition_strategy} with partition_count "
            f"{recommended_partition_count} based on estimated cost overage ratio {dominant_ratio:.2f}."
        )
    elif dominant_metric_name == "candidate_window_span_days_max":
        reason = _build_completed_window_span_rejection_reason(
            settings=settings,
            observed_window_span_days_max=_coerce_optional_int(
                metrics.get("candidate_window_span_days_max")
            ),
            observed_max_grouped_live_window_span_days=(
                observed_max_grouped_live_window_span_days
            ),
            observed_max_live_promo_days=observed_max_live_promo_days,
            theoretical_completed_window_span_days_max=(
                theoretical_completed_window_span_days_max
            ),
            recommended_partition_strategy=recommended_partition_strategy,
            recommended_partition_count=recommended_partition_count,
            dominant_ratio=dominant_ratio,
        )
    else:
        reason = (
            f"{dominant_metric_name} observed {dominant_constraint['observed']} exceeds the configured "
            f"threshold {dominant_constraint['threshold']}; recommend {recommended_partition_strategy} "
            f"with partition_count {recommended_partition_count} based on overage ratio {dominant_ratio:.2f}."
        )
    return PromotionPreflightPlannerDecision(
        verdict="TOO_WIDE_REPARTITION_REQUIRED",
        reason=reason,
        recommended_partition_strategy=recommended_partition_strategy,
        recommended_partition_count=recommended_partition_count,
        constraint_results=constraint_results,
        estimated_cost_score=estimated_cost_score,
        estimated_extract_query_seconds=(
            _coerce_optional_float(cost_model_payload.get("estimated_extract_query_seconds"))
            if cost_model_payload is not None
            else None
        ),
        fixed_overhead_seconds=(
            _coerce_optional_float(cost_model_payload.get("fixed_overhead_seconds"))
            if cost_model_payload is not None
            else None
        ),
        variable_cost_signal=(
            _coerce_optional_float(cost_model_payload.get("variable_cost_signal"))
            if cost_model_payload is not None
            else None
        ),
        cost_model_version=(
            str(cost_model_payload.get("model_version"))
            if cost_model_payload is not None and cost_model_payload.get("model_version") is not None
            else None
        ),
        cost_guardrail_verdict=cost_guardrail_verdict,
        cost_guardrail_reason=cost_guardrail_reason,
        observed_max_grouped_live_window_span_days=observed_max_grouped_live_window_span_days,
        observed_max_live_promo_days=observed_max_live_promo_days,
        theoretical_completed_window_span_days_max=theoretical_completed_window_span_days_max,
    )


def _resolve_preflight_thresholds_for_summary(
    *,
    selection_mode: PromotionSelectionMode,
    planner_settings: PromotionCompletedPreflightPlannerSettings,
    decision: PromotionPreflightPlannerDecision,
) -> dict[str, int | float | None]:
    thresholds = planner_settings.thresholds_dict()
    if selection_mode == "completed":
        thresholds["max_window_span_days_max"] = (
            decision.theoretical_completed_window_span_days_max
        )
    return thresholds


def _resolve_theoretical_completed_window_span_days_max(
    *,
    settings: PromotionPipelineSettings,
    observed_max_grouped_live_window_span_days: int | None,
    fallback_threshold: int | None,
) -> int | None:
    if observed_max_grouped_live_window_span_days is None:
        return fallback_threshold
    return (
        settings.windows.baseline_lookback_days
        + settings.windows.post_promo_days
        + observed_max_grouped_live_window_span_days
    )


def _build_completed_window_span_threshold_reason(
    *,
    settings: PromotionPipelineSettings,
    observed_value: int | None,
    observed_max_grouped_live_window_span_days: int | None,
    observed_max_live_promo_days: int | None,
    theoretical_completed_window_span_days_max: int | None,
) -> str | None:
    if theoretical_completed_window_span_days_max is None:
        return None
    relation = "within" if observed_value is None or observed_value <= theoretical_completed_window_span_days_max else "exceeds"
    return (
        "Completed-mode max window span uses grouped store/SKU merged candidate-window grain. "
        "Dynamic threshold is "
        f"{theoretical_completed_window_span_days_max} derived from baseline_lookback_days "
        f"{settings.windows.baseline_lookback_days} + post_promo_days {settings.windows.post_promo_days} "
        f"+ observed_max_grouped_live_window_span_days {observed_max_grouped_live_window_span_days if observed_max_grouped_live_window_span_days is not None else 'n/a'}; "
        f"raw promotion-duration grain max observed_max_live_promo_days={observed_max_live_promo_days if observed_max_live_promo_days is not None else 'n/a'} (informational only); "
        f"observed candidate_window_span_days_max {observed_value if observed_value is not None else 'n/a'} {relation} that theoretical completed max."
    )


def _append_completed_window_span_reason(
    *,
    safe_reason: str,
    settings: PromotionPipelineSettings,
    observed_window_span_days_max: int | None,
    observed_max_grouped_live_window_span_days: int | None,
    observed_max_live_promo_days: int | None,
    theoretical_completed_window_span_days_max: int | None,
    exceeded: bool,
) -> str:
    if theoretical_completed_window_span_days_max is None:
        return safe_reason
    relation = "exceeded" if exceeded else "did not exceed"
    return (
        f"{safe_reason} completed dynamic max window span check {relation}: observed "
        f"candidate_window_span_days_max {observed_window_span_days_max if observed_window_span_days_max is not None else 'n/a'} "
        f"against theoretical_completed_window_span_days_max {theoretical_completed_window_span_days_max} "
        f"(grouped store/SKU merged candidate-window grain: baseline_lookback_days {settings.windows.baseline_lookback_days} + post_promo_days {settings.windows.post_promo_days} + observed_max_grouped_live_window_span_days {observed_max_grouped_live_window_span_days if observed_max_grouped_live_window_span_days is not None else 'n/a'}; raw promotion-duration grain observed_max_live_promo_days {observed_max_live_promo_days if observed_max_live_promo_days is not None else 'n/a'} informational only)."
    )


def _build_completed_window_span_rejection_reason(
    *,
    settings: PromotionPipelineSettings,
    observed_window_span_days_max: int | None,
    observed_max_grouped_live_window_span_days: int | None,
    observed_max_live_promo_days: int | None,
    theoretical_completed_window_span_days_max: int | None,
    recommended_partition_strategy: str,
    recommended_partition_count: int,
    dominant_ratio: float,
) -> str:
    if theoretical_completed_window_span_days_max is None:
        return (
            f"candidate_window_span_days_max observed {observed_window_span_days_max} exceeds the configured threshold; "
            f"recommend {recommended_partition_strategy} with partition_count {recommended_partition_count} based on overage ratio {dominant_ratio:.2f}."
        )
    return (
        f"candidate_window_span_days_max observed {observed_window_span_days_max} (grouped store/SKU merged candidate-window grain) exceeds the theoretical completed max "
        f"{theoretical_completed_window_span_days_max} derived from baseline_lookback_days {settings.windows.baseline_lookback_days} + "
        f"post_promo_days {settings.windows.post_promo_days} + observed_max_grouped_live_window_span_days {observed_max_grouped_live_window_span_days if observed_max_grouped_live_window_span_days is not None else 'n/a'}; "
        f"raw promotion-duration grain observed_max_live_promo_days {observed_max_live_promo_days if observed_max_live_promo_days is not None else 'n/a'} is informational only; "
        f"recommend {recommended_partition_strategy} with partition_count {recommended_partition_count} based on overage ratio {dominant_ratio:.2f}."
    )


def _estimate_cost_guardrail(
    *,
    planner_settings: PromotionCompletedPreflightPlannerSettings,
    metrics: dict[str, object],
    sql_execution_telemetry: PromotionSqlExecutionTelemetry,
) -> tuple[
    float | None,
    PromotionPreflightCostGuardrailVerdict | None,
    str | None,
    float | None,
    dict[str, object] | None,
]:
    """Estimate extraction cost and evaluate against guardrail thresholds.
    
    Uses decomposed cost model (fixed overhead + variable components) to estimate
    full extraction cost from preflight telemetry and candidate metrics.
    """
    max_estimated_cost_score = planner_settings.max_estimated_cost_score
    if max_estimated_cost_score is None:
        return (
            None,
            "NOT_APPLIED_COST_GUARDRAIL_DISABLED",
            "Cost guardrail not applied because max_estimated_cost_score is disabled.",
            None,
            None,
        )
    query_timeout_seconds = sql_execution_telemetry.query_timeout_seconds
    if query_timeout_seconds is None:
        return (
            None,
            "NOT_APPLIED_QUERY_TIMEOUT_DISABLED",
            "Cost guardrail not applied because query_timeout_seconds is disabled, so there is no live timeout budget for admission control.",
            None,
            None,
        )
    phase_elapsed_seconds = sql_execution_telemetry.to_dict()["phase_elapsed_seconds"]
    query_execution_seconds = phase_elapsed_seconds.get("query_execution")
    if query_execution_seconds is None:
        return (
            None,
            "NOT_APPLIED_MISSING_PREFLIGHT_QUERY_EXECUTION_SECONDS",
            "Cost guardrail not applied because the preflight probe did not expose query_execution timing.",
            None,
            None,
        )

    # Build preflight metrics for the cost model.
    preflight_metrics = CompletedExtractionPreflightMetrics(
        observed_preflight_execution_seconds=query_execution_seconds,
        candidate_promotion_row_count=_coerce_optional_int(metrics.get("candidate_promotion_row_count")),
        candidate_store_sku_count=_coerce_optional_int(metrics.get("candidate_store_sku_count")),
        candidate_window_span_days_total=_coerce_optional_int(
            metrics.get("candidate_window_span_days_total")
        ),
        candidate_window_span_days_max=_coerce_optional_int(
            metrics.get("candidate_window_span_days_max")
        ),
    )

    # Initialize cost model with settings derived from planner config.
    # Map the old multiplier to conservative fallback for backward compatibility.
    cost_model_settings = CompletedExtractionCostModelSettings(
        use_conservative_multiplier_fallback=True,
        conservative_multiplier_fallback=planner_settings.preflight_query_execution_seconds_multiplier,
    )
    estimator = CompletedExtractionCostModelEstimator(settings=cost_model_settings)

    # Estimate extraction cost.
    estimation = estimator.estimate_extraction_cost(
        preflight_metrics=preflight_metrics,
        query_timeout_seconds=query_timeout_seconds,
    )
    estimation_payload = estimation.to_dict()

    estimated_cost_score = estimation.estimated_cost_score
    overage_ratio = round(
        estimated_cost_score / max_estimated_cost_score,
        3,
    ) if max_estimated_cost_score > 0 else None

    reason = estimation.explanation_message

    if estimated_cost_score > max_estimated_cost_score:
        return (
            estimated_cost_score,
            "TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET",
            reason,
            overage_ratio,
            estimation_payload,
        )
    return (
        estimated_cost_score,
        "WITHIN_LIVE_TIMEOUT_BUDGET",
        reason,
        overage_ratio,
        estimation_payload,
    )



def _is_invalid_partition_key_error(
    error: BaseException,
    query_options: PromotionBaseQueryOptions,
) -> bool:
    if query_options.completed_partition is None:
        return False
    if not isinstance(error, PromotionMssqlQueryError):
        return False
    message = _normalize_error_message(error).lower()
    return "invalid column name" in message


def _coerce_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Unable to coerce integer preflight metric from value {value!r}.") from error


def _coerce_optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Unable to coerce float preflight metric from value {value!r}.") from error


def _coerce_optional_date(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        iso_value = value.isoformat()
        return iso_value[:10] if len(iso_value) >= 10 else iso_value
    return str(value)


def _sum_elapsed_seconds(phase_elapsed_seconds: dict[str, float | None]) -> float | None:
    populated = [value for value in phase_elapsed_seconds.values() if value is not None]
    if not populated:
        return None
    return round(sum(populated), 3)
