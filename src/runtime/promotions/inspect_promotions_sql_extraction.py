from __future__ import annotations

"""Thin dry-run and explain entrypoint for governed promotions SQL extraction."""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
import argparse
import json
from pathlib import Path
import shlex
import sys
from typing import TextIO

from data.promotions.extracted_dataset_writer import PromotionExtractionWriter
from data.promotions.mssql_query_executor import SqlAlchemyMssqlQueryExecutor
from data.promotions.promotion_base_extractor import (
    PromotionBaseExtractor,
    PromotionExtractionPreflightResult,
    PromotionExtractionTelemetry,
    write_extraction_observability,
    write_rendered_query_artifacts,
)
from data.promotions.sql import PromotionBaseQueryOptions, render_promotion_base_query
from runtime.promotions.config import (
    PromotionArtifactPaths,
    PromotionCompletedExtractionRuntimeSettings,
    PromotionCompletedPartitionSettings,
    PromotionCompletedPreflightPlannerSettings,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
    PromotionRuntimeConfigError,
)
from runtime.promotions.print_completed_stage3_validation import (
    collect_completed_stage3_validation_summary,
)
from runtime.promotions.run_promotions_operational_cycle import _extract_promotions_base_artifact


@dataclass(frozen=True)
class PromotionSqlInspectionSummary:
    run_id: str
    as_of_date: str
    selection_mode: str
    extraction_mode: str
    partition_strategy: str | None
    partition_count: int | None
    partition_index: int | None
    server: str
    database: str
    schema: str
    promotion_advice_table: str
    pwlogd_table: str
    query_version: str
    connect_timeout_seconds: int | None
    connect_retry_attempts: int
    connect_retry_backoff_seconds: float
    query_timeout_seconds: int | None
    enable_landed_batches: bool
    batch_row_count: int
    completed_sales_history_start_date: str
    enable_chunked_fetch: bool
    chunk_row_count: int
    resume_completed_partitions: bool
    stage_temp_chunk_files: bool
    rendered_query_parameter_summary: dict[str, object]
    diagnostic_filter_summary: dict[str, object]
    estimated_window_summary: dict[str, object]
    rendered_sql: str
    planner_verdict: str | None = None
    planner_reason: str | None = None
    recommended_partition_strategy: str | None = None
    recommended_partition_count: int | None = None
    observed_max_grouped_live_window_span_days: int | None = None
    observed_max_live_promo_days: int | None = None
    theoretical_completed_window_span_days_max: int | None = None
    preflight_summary: dict[str, object] | None = None
    preflight_summary_json_path: str | None = None
    preflight_summary_csv_path: str | None = None
    rendered_preflight_sql_path: str | None = None
    rendered_preflight_sql_parameters_path: str | None = None
    recommended_rerun_command: str | None = None
    rendered_sql_path: str | None = None
    rendered_sql_parameters_path: str | None = None
    connection_test: dict[str, object] | None = None
    row_count_probe: dict[str, object] | None = None
    execution_result: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def main(argv: list[str] | None = None, *, stream: TextIO | None = None) -> None:
    output_stream = stream or sys.stdout
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        settings = _build_settings(args)
    except PromotionRuntimeConfigError as error:
        _render_config_error(error, stream=output_stream)
        raise SystemExit(1) from error
    _render_startup(args=args, settings=settings, stream=output_stream)
    summary = inspect_sql_extraction(
        settings=settings,
        run_id=args.run_id,
        selection_mode=args.selection_mode,
        query_options=_build_query_options(args),
        test_connection=args.test_connection,
        save_rendered_sql=args.save_rendered_sql,
        run_row_count_probe=args.run_row_count_probe,
        run_preflight=args.run_preflight,
        planner_only=args.planner_only,
        run_extraction=args.run_extraction,
    )
    render_sql_inspection_report(summary, stream=output_stream)


def _render_startup(
    *,
    args: argparse.Namespace,
    settings: PromotionPipelineSettings,
    stream: TextIO,
) -> None:
    print("PROMOTIONS SQL EXTRACTION STARTUP", file=stream)
    print(f"run_id: {args.run_id}", file=stream)
    print(f"selection_mode: {args.selection_mode}", file=stream)
    print(f"extraction_mode: {args.extraction_mode}", file=stream)
    print(
        f"partition_strategy: {args.partition_strategy or 'disabled'}",
        file=stream,
    )
    print(
        (
            "partition_count: "
            f"{args.partition_count if args.partition_count is not None else 'disabled'}"
        ),
        file=stream,
    )
    print(
        (
            "partition_index: "
            f"{args.partition_index if args.partition_index is not None else 'disabled'}"
        ),
        file=stream,
    )
    print(f"as_of_date: {settings.as_of_date.isoformat()}", file=stream)
    print(
        f"enable_landed_batches: {str(settings.completed_extraction_runtime.enable_landed_batches).lower()}",
        file=stream,
    )
    print(
        f"batch_row_count: {settings.completed_extraction_runtime.batch_row_count}",
        file=stream,
    )
    print(
        "completed_sales_history_start_date: "
        f"{settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()}",
        file=stream,
    )
    print(
        f"enable_chunked_fetch: {str(settings.completed_extraction_runtime.enable_chunked_fetch).lower()}",
        file=stream,
    )
    print(
        f"chunk_row_count: {settings.completed_extraction_runtime.chunk_row_count}",
        file=stream,
    )
    print(
        "resume_completed_partitions: "
        f"{str(settings.completed_extraction_runtime.resume_completed_partitions).lower()}",
        file=stream,
    )
    print(
        f"stage_temp_chunk_files: {str(settings.completed_extraction_runtime.stage_temp_chunk_files).lower()}",
        file=stream,
    )
    for line in settings.sql.safe_summary().render_lines():
        print(line, file=stream)


def _render_config_error(error: PromotionRuntimeConfigError, *, stream: TextIO) -> None:
    print("FATAL PROMOTIONS SQL CONFIG ERROR", file=stream)
    if error.field_name:
        print(f"field: {error.field_name}", file=stream)
    if error.source:
        print(f"source: {error.source}", file=stream)
    if error.expected_from:
        print(f"expected_from: {', '.join(error.expected_from)}", file=stream)
    print(f"cause: {error}", file=stream)
    if error.next_action:
        print(f"next_action: {error.next_action}", file=stream)


def inspect_sql_extraction(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    selection_mode: str,
    query_options: PromotionBaseQueryOptions | None = None,
    test_connection: bool = False,
    save_rendered_sql: bool = False,
    run_row_count_probe: bool = False,
    run_preflight: bool = False,
    planner_only: bool = False,
    run_extraction: bool = False,
) -> PromotionSqlInspectionSummary:
    resolved_query_options = query_options or PromotionBaseQueryOptions()
    should_run_preflight = (
        planner_only
        or run_preflight
        or (run_extraction and selection_mode == "completed")
    )
    if planner_only:
        run_row_count_probe = False
        run_extraction = False
    rendered_query = render_promotion_base_query(
        settings=settings,
        selection_mode=selection_mode,
        query_options=resolved_query_options,
    )
    rendered_sql_path = None
    rendered_sql_parameters_path = None
    persist_rendered_sql_artifacts = save_rendered_sql or run_extraction
    if persist_rendered_sql_artifacts:
        rendered_sql_artifacts = write_rendered_query_artifacts(
            run_id=run_id,
            artifact_paths=settings.artifacts,
            rendered_query=rendered_query,
        )
        rendered_sql_path = rendered_sql_artifacts.sql_path
        rendered_sql_parameters_path = rendered_sql_artifacts.parameters_path

    connection_test = None
    row_count_probe = None
    execution_result = None
    preflight_result: PromotionExtractionPreflightResult | None = None
    executor = (
        SqlAlchemyMssqlQueryExecutor.from_settings(settings.sql)
        if test_connection or run_row_count_probe or run_extraction or should_run_preflight
        else None
    )
    if test_connection and executor is not None:
        connection_result = executor.test_connection()
        connection_test = {
            "connected_at_utc": connection_result.connected_at_utc,
            "elapsed_seconds": connection_result.elapsed_seconds,
            "connect_timeout_seconds": connection_result.connect_timeout_seconds,
            "connect_retry_attempts": connection_result.connect_retry_attempts,
            "connect_retry_backoff_seconds": connection_result.connect_retry_backoff_seconds,
            "connect_attempt_count": connection_result.connect_attempt_count,
            "query_timeout_seconds": connection_result.query_timeout_seconds,
            "query_timeout_applied": connection_result.query_timeout_applied,
        }
    if should_run_preflight and executor is not None:
        preflight_result = PromotionBaseExtractor(executor=executor).run_preflight(
            run_id=run_id,
            settings=settings,
            selection_mode=selection_mode,
            query_options=resolved_query_options,
        )
    if run_row_count_probe and executor is not None and not run_extraction:
        probe_result = executor.fetch_dataframe(
            sql=rendered_query.candidate_count_sql,
            parameters=rendered_query.parameters,
        )
        row_count_probe = {
            "candidate_promotion_row_count": _extract_candidate_promotion_row_count(
                probe_result.frame
            ),
            "phase_elapsed_seconds": probe_result.telemetry.to_dict()["phase_elapsed_seconds"],
            "query_timeout_seconds": probe_result.telemetry.query_timeout_seconds,
            "query_timeout_applied": probe_result.telemetry.query_timeout_applied,
        }
    if run_extraction and executor is not None:
        if (
            preflight_result is not None
            and preflight_result.summary.verdict != "SAFE_TO_EXTRACT"
        ):
            recommended_rerun_command = _build_recommended_rerun_command(
                settings=settings,
                run_id=run_id,
                selection_mode=selection_mode,
                extraction_mode=resolved_query_options.extraction_mode,
                partition_strategy=(
                    preflight_result.summary.recommended_partition_strategy
                    or resolved_query_options.completed_partition.strategy
                    if resolved_query_options.completed_partition is not None
                    else None
                ),
                partition_count=(
                    preflight_result.summary.recommended_partition_count
                    or resolved_query_options.completed_partition.partition_count
                    if resolved_query_options.completed_partition is not None
                    else None
                ),
                partition_index=(
                    resolved_query_options.completed_partition.partition_index
                    if resolved_query_options.completed_partition is not None
                    else None
                ),
            )
            execution_result = {
                "status": "skipped_preflight_rejected",
                "planner_verdict": preflight_result.summary.verdict,
                "planner_reason": preflight_result.summary.reason,
                "recommended_partition_strategy": preflight_result.summary.recommended_partition_strategy,
                "recommended_partition_count": preflight_result.summary.recommended_partition_count,
                "observed_max_grouped_live_window_span_days": preflight_result.summary.observed_max_grouped_live_window_span_days,
                "observed_max_live_promo_days": preflight_result.summary.observed_max_live_promo_days,
                "theoretical_completed_window_span_days_max": preflight_result.summary.theoretical_completed_window_span_days_max,
                "preflight_summary_json_path": preflight_result.artifacts.summary_json_path,
                "recommended_rerun_command": recommended_rerun_command,
            }
        else:
            execution_result = _run_diagnostic_extraction(
                settings=settings,
                run_id=run_id,
                selection_mode=selection_mode,
                query_options=resolved_query_options,
                executor=executor,
            )

    return PromotionSqlInspectionSummary(
        run_id=run_id,
        as_of_date=settings.as_of_date.isoformat(),
        selection_mode=selection_mode,
        extraction_mode=resolved_query_options.extraction_mode,
        partition_strategy=(
            resolved_query_options.completed_partition.strategy
            if resolved_query_options.completed_partition is not None
            else None
        ),
        partition_count=(
            resolved_query_options.completed_partition.partition_count
            if resolved_query_options.completed_partition is not None
            else None
        ),
        partition_index=(
            resolved_query_options.completed_partition.partition_index
            if resolved_query_options.completed_partition is not None
            else None
        ),
        server=settings.sql.server,
        database=settings.sql.database,
        schema=settings.sql.schema,
        promotion_advice_table=settings.sql.promotion_advice_table,
        pwlogd_table=settings.sql.pwlogd_table,
        query_version=rendered_query.query_version,
        connect_timeout_seconds=settings.sql.connect_timeout_seconds,
        connect_retry_attempts=settings.sql.connect_retry_attempts,
        connect_retry_backoff_seconds=settings.sql.connect_retry_backoff_seconds,
        query_timeout_seconds=settings.sql.query_timeout_seconds,
        enable_landed_batches=settings.completed_extraction_runtime.enable_landed_batches,
        batch_row_count=settings.completed_extraction_runtime.batch_row_count,
        completed_sales_history_start_date=(
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
        ),
        enable_chunked_fetch=settings.completed_extraction_runtime.enable_chunked_fetch,
        chunk_row_count=settings.completed_extraction_runtime.chunk_row_count,
        resume_completed_partitions=settings.completed_extraction_runtime.resume_completed_partitions,
        stage_temp_chunk_files=settings.completed_extraction_runtime.stage_temp_chunk_files,
        rendered_query_parameter_summary=dict(rendered_query.parameters),
        diagnostic_filter_summary=dict(rendered_query.diagnostic_filter_summary),
        estimated_window_summary=dict(rendered_query.estimated_window_summary),
        rendered_sql=rendered_query.sql,
        planner_verdict=(
            preflight_result.summary.verdict if preflight_result is not None else None
        ),
        planner_reason=(
            preflight_result.summary.reason if preflight_result is not None else None
        ),
        recommended_partition_strategy=(
            preflight_result.summary.recommended_partition_strategy
            if preflight_result is not None
            else None
        ),
        recommended_partition_count=(
            preflight_result.summary.recommended_partition_count
            if preflight_result is not None
            else None
        ),
        observed_max_grouped_live_window_span_days=(
            preflight_result.summary.observed_max_grouped_live_window_span_days
            if preflight_result is not None
            else None
        ),
        observed_max_live_promo_days=(
            preflight_result.summary.observed_max_live_promo_days
            if preflight_result is not None
            else None
        ),
        theoretical_completed_window_span_days_max=(
            preflight_result.summary.theoretical_completed_window_span_days_max
            if preflight_result is not None
            else None
        ),
        preflight_summary=(
            preflight_result.summary.to_dict() if preflight_result is not None else None
        ),
        preflight_summary_json_path=(
            preflight_result.artifacts.summary_json_path if preflight_result is not None else None
        ),
        preflight_summary_csv_path=(
            preflight_result.artifacts.summary_csv_path if preflight_result is not None else None
        ),
        rendered_preflight_sql_path=(
            preflight_result.artifacts.rendered_sql_path if preflight_result is not None else None
        ),
        rendered_preflight_sql_parameters_path=(
            preflight_result.artifacts.rendered_sql_parameters_path
            if preflight_result is not None
            else None
        ),
        recommended_rerun_command=(
            execution_result.get("recommended_rerun_command")
            if execution_result is not None
            else None
        ),
        rendered_sql_path=rendered_sql_path,
        rendered_sql_parameters_path=rendered_sql_parameters_path,
        connection_test=connection_test,
        row_count_probe=row_count_probe,
        execution_result=execution_result,
    )


def render_sql_inspection_report(
    summary: PromotionSqlInspectionSummary,
    *,
    stream: TextIO,
) -> None:
    print("PROMOTIONS SQL EXTRACTION INSPECTION", file=stream)
    print(f"run_id: {summary.run_id}", file=stream)
    print(f"selection_mode: {summary.selection_mode}", file=stream)
    print(f"extraction_mode: {summary.extraction_mode}", file=stream)
    print(f"partition_strategy: {summary.partition_strategy or 'disabled'}", file=stream)
    print(
        "partition_count: "
        f"{summary.partition_count if summary.partition_count is not None else 'disabled'}",
        file=stream,
    )
    print(
        "partition_index: "
        f"{summary.partition_index if summary.partition_index is not None else 'disabled'}",
        file=stream,
    )
    print(f"as_of_date: {summary.as_of_date}", file=stream)
    print(f"server: {summary.server}", file=stream)
    print(f"database: {summary.database}", file=stream)
    print(f"schema: {summary.schema}", file=stream)
    print(f"promotion_advice_table: {summary.promotion_advice_table}", file=stream)
    print(f"pwlogd_table: {summary.pwlogd_table}", file=stream)
    print(f"query_version: {summary.query_version}", file=stream)
    print(
        "connect_timeout_seconds: "
        f"{summary.connect_timeout_seconds if summary.connect_timeout_seconds is not None else 'disabled'}",
        file=stream,
    )
    print(
        f"connect_retry_attempts: {summary.connect_retry_attempts}",
        file=stream,
    )
    print(
        f"connect_retry_backoff_seconds: {summary.connect_retry_backoff_seconds}",
        file=stream,
    )
    print(
        "query_timeout_seconds: "
        f"{summary.query_timeout_seconds if summary.query_timeout_seconds is not None else 'disabled'}",
        file=stream,
    )
    print(f"enable_landed_batches: {str(summary.enable_landed_batches).lower()}", file=stream)
    print(f"batch_row_count: {summary.batch_row_count}", file=stream)
    print(
        f"completed_sales_history_start_date: {summary.completed_sales_history_start_date}",
        file=stream,
    )
    print(f"enable_chunked_fetch: {str(summary.enable_chunked_fetch).lower()}", file=stream)
    print(f"chunk_row_count: {summary.chunk_row_count}", file=stream)
    print(
        f"resume_completed_partitions: {str(summary.resume_completed_partitions).lower()}",
        file=stream,
    )
    print(
        f"stage_temp_chunk_files: {str(summary.stage_temp_chunk_files).lower()}",
        file=stream,
    )
    print(
        f"estimated_window_summary: {json.dumps(summary.estimated_window_summary, sort_keys=True)}",
        file=stream,
    )
    print(
        (
            "rendered_query_parameter_summary: "
            f"{json.dumps(summary.rendered_query_parameter_summary, sort_keys=True)}"
        ),
        file=stream,
    )
    print(
        f"diagnostic_filter_summary: {json.dumps(summary.diagnostic_filter_summary, sort_keys=True)}",
        file=stream,
    )
    print(f"planner_verdict: {summary.planner_verdict or 'not_run'}", file=stream)
    print(f"planner_reason: {summary.planner_reason or 'n/a'}", file=stream)
    print(
        "observed_max_grouped_live_window_span_days: "
        f"{summary.observed_max_grouped_live_window_span_days if summary.observed_max_grouped_live_window_span_days is not None else 'n/a'}",
        file=stream,
    )
    print(
        "observed_max_live_promo_days: "
        f"{summary.observed_max_live_promo_days if summary.observed_max_live_promo_days is not None else 'n/a'}",
        file=stream,
    )
    print(
        "theoretical_completed_window_span_days_max: "
        f"{summary.theoretical_completed_window_span_days_max if summary.theoretical_completed_window_span_days_max is not None else 'n/a'}",
        file=stream,
    )
    print(
        "recommended_partition_strategy: "
        f"{summary.recommended_partition_strategy or 'n/a'}",
        file=stream,
    )
    print(
        "recommended_partition_count: "
        f"{summary.recommended_partition_count if summary.recommended_partition_count is not None else 'n/a'}",
        file=stream,
    )
    print(
        f"preflight_summary_json_path: {summary.preflight_summary_json_path or 'not_saved'}",
        file=stream,
    )
    print(
        f"preflight_summary_csv_path: {summary.preflight_summary_csv_path or 'not_saved'}",
        file=stream,
    )
    print(
        f"rendered_preflight_sql_path: {summary.rendered_preflight_sql_path or 'not_saved'}",
        file=stream,
    )
    print(
        "rendered_preflight_sql_parameters_path: "
        f"{summary.rendered_preflight_sql_parameters_path or 'not_saved'}",
        file=stream,
    )
    print(
        f"preflight_summary: {json.dumps(summary.preflight_summary, sort_keys=True) if summary.preflight_summary is not None else 'skipped'}",
        file=stream,
    )
    if summary.planner_verdict not in (None, "SAFE_TO_EXTRACT"):
        print(
            "next_recommended_partition_strategy: "
            f"{summary.recommended_partition_strategy or 'n/a'}",
            file=stream,
        )
        print(
            "next_recommended_partition_count: "
            f"{summary.recommended_partition_count if summary.recommended_partition_count is not None else 'n/a'}",
            file=stream,
        )
        print(
            f"recommended_rerun_command: {summary.recommended_rerun_command or 'n/a'}",
            file=stream,
        )
    print(
        f"rendered_sql_path: {summary.rendered_sql_path or 'not_saved'}",
        file=stream,
    )
    print(
        f"rendered_sql_parameters_path: {summary.rendered_sql_parameters_path or 'not_saved'}",
        file=stream,
    )
    print(
        f"connection_test: {json.dumps(summary.connection_test, sort_keys=True) if summary.connection_test is not None else 'skipped'}",
        file=stream,
    )
    print(
        f"row_count_probe: {json.dumps(summary.row_count_probe, sort_keys=True) if summary.row_count_probe is not None else 'skipped'}",
        file=stream,
    )
    print(
        f"execution_result: {json.dumps(summary.execution_result, sort_keys=True) if summary.execution_result is not None else 'skipped'}",
        file=stream,
    )
    print("", file=stream)
    print("RENDERED SQL", file=stream)
    print(summary.rendered_sql, file=stream)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect the governed promotions SQL extraction query without running the full pipeline."
    )
    parser.add_argument("--env-file")
    parser.add_argument("--server")
    parser.add_argument("--database")
    parser.add_argument("--schema")
    parser.add_argument("--promotion-advice-table")
    parser.add_argument("--pwlogd-table")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--odbc-driver")
    parser.add_argument("--connect-timeout-seconds", type=int)
    parser.add_argument("--connect-retry-attempts", type=int)
    parser.add_argument("--connect-retry-backoff-seconds", type=float)
    parser.add_argument("--query-timeout-seconds", type=int)
    parser.add_argument("--enable-landed-batches", choices=("true", "false"))
    parser.add_argument("--batch-row-count", type=int)
    parser.add_argument("--completed-sales-history-start-date")
    parser.add_argument("--enable-chunked-fetch", choices=("true", "false"))
    parser.add_argument("--chunk-row-count", type=int)
    parser.add_argument("--resume-completed-partitions", choices=("true", "false"))
    parser.add_argument("--stage-temp-chunk-files", choices=("true", "false"))
    parser.add_argument("--encrypt", choices=("yes", "no"))
    parser.add_argument("--trust-server-certificate", choices=("yes", "no"))
    parser.add_argument("--artifact-root")
    parser.add_argument("--as-of-date")
    parser.add_argument(
        "--run-id",
        default=f"promotions-sql-inspection-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}",
    )
    parser.add_argument("--selection-mode", choices=("completed", "future"), default="completed")
    parser.add_argument("--extraction-mode", choices=("live_sql", "diagnostic_topn"), default="live_sql")
    parser.add_argument("--limit-promotions", type=int)
    parser.add_argument("--promotion-name-like")
    parser.add_argument("--store-number", type=int)
    parser.add_argument("--supplier-number", type=int)
    parser.add_argument(
        "--partition-strategy",
        choices=(
            "store_number",
            "supplier_number",
            "store_sku_hash_bucket",
            "promotion_name_hash_bucket",
            "promotion_row_key_hash_bucket",
        ),
    )
    parser.add_argument("--partition-count", type=int)
    parser.add_argument("--partition-index", type=int)
    parser.add_argument("--save-rendered-sql", action="store_true")
    parser.add_argument("--test-connection", action="store_true")
    parser.add_argument("--run-preflight", action="store_true")
    parser.add_argument("--max-candidate-promotion-rows", type=int)
    parser.add_argument("--max-candidate-store-sku", type=int)
    parser.add_argument("--max-window-span-days-total", type=int)
    parser.add_argument("--max-window-span-days-max", type=int)
    parser.add_argument("--planner-only", action="store_true")
    parser.add_argument("--run-row-count-probe", action="store_true")
    parser.add_argument("--run-extraction", action="store_true")
    return parser


def _build_recommended_rerun_command(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    selection_mode: str,
    extraction_mode: str,
    partition_strategy: str | None,
    partition_count: int | None,
    partition_index: int | None,
) -> str | None:
    if partition_strategy is None or partition_count is None or partition_index is None:
        return None
    arguments: list[str] = [
        sys.executable,
        "-m",
        "runtime.promotions.inspect_promotions_sql_extraction",
        "--selection-mode",
        selection_mode,
        "--extraction-mode",
        extraction_mode,
        "--as-of-date",
        settings.as_of_date.isoformat(),
        "--run-id",
        run_id,
        "--partition-strategy",
        partition_strategy,
        "--partition-count",
        str(partition_count),
        "--partition-index",
        str(partition_index),
        "--run-extraction",
        "--enable-landed-batches",
        str(settings.completed_extraction_runtime.enable_landed_batches).lower(),
        "--batch-row-count",
        str(settings.completed_extraction_runtime.batch_row_count),
        "--completed-sales-history-start-date",
        settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat(),
        "--enable-chunked-fetch",
        str(settings.completed_extraction_runtime.enable_chunked_fetch).lower(),
        "--chunk-row-count",
        str(settings.completed_extraction_runtime.chunk_row_count),
        "--resume-completed-partitions",
        str(settings.completed_extraction_runtime.resume_completed_partitions).lower(),
        "--stage-temp-chunk-files",
        str(settings.completed_extraction_runtime.stage_temp_chunk_files).lower(),
        "--save-rendered-sql",
        "--connect-retry-attempts",
        str(settings.sql.connect_retry_attempts),
        "--connect-retry-backoff-seconds",
        str(settings.sql.connect_retry_backoff_seconds),
    ]
    if settings.sql.connect_timeout_seconds is not None:
        arguments.extend(
            ["--connect-timeout-seconds", str(settings.sql.connect_timeout_seconds)]
        )
    if settings.sql.query_timeout_seconds is not None:
        arguments.extend(["--query-timeout-seconds", str(settings.sql.query_timeout_seconds)])
    return " ".join(shlex.quote(argument) for argument in arguments)


def _build_settings(args: argparse.Namespace) -> PromotionPipelineSettings:
    try:
        runtime_date = (
            date.fromisoformat(args.as_of_date)
            if args.as_of_date
            else datetime.now(tz=UTC).date()
        )
    except ValueError as error:
        raise PromotionRuntimeConfigError(
            "Invalid promotions runtime setting 'as_of_date' from cli:--as-of-date. Use YYYY-MM-DD.",
            field_name="as_of_date",
            source="cli:--as-of-date",
            expected_from=("--as-of-date",),
            next_action="Provide --as-of-date in YYYY-MM-DD format and rerun.",
        ) from error
    artifact_paths = PromotionArtifactPaths.from_env(
        root=Path(args.artifact_root) if args.artifact_root else None,
        enable_local_inspection_copy=False,
        env_file=args.env_file,
    )
    return PromotionPipelineSettings.for_runtime_date(
        sql=PromotionMssqlSettings.from_env(
            promotion_advice_table=args.promotion_advice_table,
            pwlogd_table=args.pwlogd_table,
            env_file=args.env_file,
            server=args.server,
            database=args.database,
            schema=args.schema,
            username=args.username,
            password=args.password,
            odbc_driver=args.odbc_driver,
            connect_timeout_seconds=args.connect_timeout_seconds,
            connect_retry_attempts=args.connect_retry_attempts,
            connect_retry_backoff_seconds=args.connect_retry_backoff_seconds,
            query_timeout_seconds=args.query_timeout_seconds,
            encrypt=args.encrypt,
            trust_server_certificate=args.trust_server_certificate,
        ),
        runtime_date=runtime_date,
        artifacts=artifact_paths,
        completed_partitioning=_build_completed_partitioning_from_args(args),
        completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings.from_env(
            enable_landed_batches=args.enable_landed_batches,
            batch_row_count=args.batch_row_count,
            completed_sales_history_start_date=args.completed_sales_history_start_date,
            enable_chunked_fetch=args.enable_chunked_fetch,
            chunk_row_count=args.chunk_row_count,
            resume_completed_partitions=args.resume_completed_partitions,
            stage_temp_chunk_files=args.stage_temp_chunk_files,
            env_file=args.env_file,
        ),
        completed_preflight_planner=_build_completed_preflight_planner_from_args(args),
    )


def _build_query_options(args: argparse.Namespace) -> PromotionBaseQueryOptions:
    return PromotionBaseQueryOptions(
        extraction_mode=args.extraction_mode,
        limit_promotions=args.limit_promotions,
        promotion_name_like=args.promotion_name_like,
        store_number=args.store_number,
        supplier_number=args.supplier_number,
        completed_partition=_build_completed_partitioning_from_args(args),
    )


def _run_diagnostic_extraction(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    selection_mode: str,
    query_options: PromotionBaseQueryOptions,
    executor: SqlAlchemyMssqlQueryExecutor,
) -> dict[str, object]:
    del executor
    staged_progress_events: list[str] = []
    try:
        extraction_artifact = _extract_promotions_base_artifact(
            settings=settings,
            run_id=run_id,
            selection_mode=selection_mode,
            progress_callback=staged_progress_events.append,
            query_options=query_options,
        )
        telemetry_payload = (
            json.loads(Path(extraction_artifact.telemetry_json_path).read_text(encoding="utf-8"))
            if extraction_artifact.telemetry_json_path is not None
            else {}
        )
        staged_validation_summary = None
        if selection_mode == "completed":
            staged_validation_summary = collect_completed_stage3_validation_summary(
                artifact_paths=settings.artifacts,
                run_id=run_id,
                partition_index=extraction_artifact.partition_index,
                partition_count=extraction_artifact.partition_count,
            ).to_dict()
        return {
            "status": "completed",
            "partition_strategy": extraction_artifact.partition_strategy,
            "partition_count": extraction_artifact.partition_count,
            "partition_index": extraction_artifact.partition_index,
            "candidate_promotion_row_count": extraction_artifact.candidate_promotion_row_count,
            "row_count": int(len(extraction_artifact.frame.index)),
            "final_extracted_row_count": int(len(extraction_artifact.frame.index)),
            "base_path": extraction_artifact.base_path,
            "manifest_path": extraction_artifact.manifest_path,
            "rendered_sql_path": extraction_artifact.rendered_sql_path,
            "rendered_sql_parameters_path": extraction_artifact.rendered_sql_parameters_path,
            "telemetry_json_path": extraction_artifact.telemetry_json_path,
            "telemetry_csv_path": extraction_artifact.telemetry_csv_path,
            "sql_diagnostics_summary_json_path": extraction_artifact.diagnostics_summary_json_path,
            "sql_diagnostics_summary_txt_path": extraction_artifact.diagnostics_summary_txt_path,
            "phase_elapsed_seconds": telemetry_payload.get("phase_elapsed_seconds"),
            "fetch_mode": extraction_artifact.fetch_mode,
            "chunk_count": extraction_artifact.chunk_count,
            "completed_chunk_count": extraction_artifact.completed_chunk_count,
            "cumulative_rows_written": extraction_artifact.cumulative_rows_written,
            "partition_completion_state": extraction_artifact.partition_completion_state,
            "resume_state": extraction_artifact.resume_state,
            "skipped_due_to_existing_completion": extraction_artifact.skipped_due_to_existing_completion,
            "partition_progress_path": extraction_artifact.partition_progress_path,
            "partition_completion_marker_path": extraction_artifact.partition_completion_marker_path,
            "staged_progress_events": staged_progress_events,
            "staged_partition_validation": staged_validation_summary,
        }
    except Exception as error:
        telemetry = getattr(error, "promotion_extraction_telemetry", None)
        if isinstance(telemetry, PromotionExtractionTelemetry):
            telemetry.output_parquet_path = str(settings.artifacts.extracted_base_path(run_id))
            telemetry.output_manifest_path = str(settings.artifacts.extracted_manifest_path(run_id))
            telemetry.mark_failure(error, stage=telemetry.current_sql_subphase)
            observability = write_extraction_observability(
                telemetry=telemetry,
                settings=settings,
                artifact_paths=settings.artifacts,
            )
            setattr(error, "telemetry_json_path", observability.telemetry_json_path)
            setattr(error, "sql_diagnostics_summary_txt_path", observability.diagnostics_summary_txt_path)
        raise


def _extract_candidate_promotion_row_count(frame) -> int:
    if frame.empty:
        return 0
    return int(frame.iloc[0, 0])


def _build_completed_partitioning_from_args(
    args: argparse.Namespace,
) -> PromotionCompletedPartitionSettings | None:
    if (
        args.partition_strategy is None
        and args.partition_count is None
        and args.partition_index is None
    ):
        return None
    if args.partition_strategy is None or args.partition_count is None or args.partition_index is None:
        raise ValueError(
            "partition_strategy, partition_count, and partition_index must all be provided for partitioned SQL inspection."
        )
    return PromotionCompletedPartitionSettings(
        strategy=args.partition_strategy,
        partition_count=args.partition_count,
        partition_index=args.partition_index,
    )


def _build_completed_preflight_planner_from_args(
    args: argparse.Namespace,
) -> PromotionCompletedPreflightPlannerSettings:
    defaults = PromotionCompletedPreflightPlannerSettings()
    return PromotionCompletedPreflightPlannerSettings(
        run_preflight=args.run_preflight,
        planner_only=args.planner_only,
        max_candidate_promotion_rows=(
            args.max_candidate_promotion_rows
            if args.max_candidate_promotion_rows is not None
            else defaults.max_candidate_promotion_rows
        ),
        max_candidate_store_sku=(
            args.max_candidate_store_sku
            if args.max_candidate_store_sku is not None
            else defaults.max_candidate_store_sku
        ),
        max_window_span_days_total=(
            args.max_window_span_days_total
            if args.max_window_span_days_total is not None
            else defaults.max_window_span_days_total
        ),
        max_window_span_days_max=(
            args.max_window_span_days_max
            if args.max_window_span_days_max is not None
            else defaults.max_window_span_days_max
        ),
        default_partition_strategy=defaults.default_partition_strategy,
    )


if __name__ == "__main__":
    main()