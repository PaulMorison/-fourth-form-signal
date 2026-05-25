from __future__ import annotations

from datetime import UTC, date
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.mssql_query_executor import (  # noqa: E402
    PromotionQueryExecutionResult,
    PromotionSqlConnectionCheckResult,
    PromotionSqlExecutionTelemetry,
)
from data.promotions.promotion_base_extractor import (  # noqa: E402
    PromotionBaseExtractor,
    PromotionExtractionPreflightArtifacts,
    PromotionExtractionPreflightResult,
    PromotionExtractionPreflightSummary,
    write_extraction_observability,
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
from runtime.promotions.inspect_promotions_sql_extraction import (  # noqa: E402
    PromotionSqlInspectionSummary,
    _build_completed_preflight_planner_from_args,
    _build_parser,
    _build_query_options,
    inspect_sql_extraction,
    main,
    render_sql_inspection_report,
)
from runtime.promotions.run_promotions_operational_cycle import (  # noqa: E402
    PromotionOperationalCycleExtractionArtifacts,
)
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class _FakeQueryExecutor:
    def __init__(self, frame, telemetry: PromotionSqlExecutionTelemetry) -> None:
        self._frame = frame
        self._telemetry = telemetry

    def fetch_dataframe(self, *, sql, parameters, phase_callback=None):
        if "candidate_promotion_row_count" in sql:
            return PromotionQueryExecutionResult(
                frame=pd.DataFrame({"candidate_promotion_row_count": [len(self._frame.index)]}),
                telemetry=self._telemetry,
            )
        if phase_callback is not None:
            phase_callback("SQL executing")
            phase_callback("SQL fetch in progress")
        return PromotionQueryExecutionResult(
            frame=self._frame,
            telemetry=self._telemetry,
        )


class _PreflightOnlyExecutor:
    def __init__(self, frame, telemetry: PromotionSqlExecutionTelemetry) -> None:
        self._frame = frame
        self._telemetry = telemetry

    def fetch_dataframe(self, *, sql, parameters, phase_callback=None):
        return PromotionQueryExecutionResult(
            frame=self._frame,
            telemetry=self._telemetry,
        )


def _build_preflight_result(
    *,
    artifact_paths: PromotionArtifactPaths,
    run_id: str,
    as_of_date: str,
    verdict: str,
    reason: str,
    recommended_partition_strategy: str | None = None,
    recommended_partition_count: int | None = None,
    observed_max_live_promo_days: int | None = None,
    theoretical_completed_window_span_days_max: int | None = None,
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
        candidate_promotion_row_count=1200,
        candidate_store_sku_count=2400,
        candidate_window_count=2400,
        candidate_window_span_days_total=4000,
        candidate_window_span_days_max=14,
        observed_max_live_promo_days=observed_max_live_promo_days,
        theoretical_completed_window_span_days_max=theoretical_completed_window_span_days_max,
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


class PromotionSqlExtractionObservabilityTests(unittest.TestCase):
    def test_extractor_writes_telemetry_and_diagnostics_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    connect_timeout_seconds=15,
                    connect_retry_attempts=2,
                    connect_retry_backoff_seconds=1.5,
                    query_timeout_seconds=45,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
            )
            base_frame = build_completed_promotions_base_frame()
            executor = _FakeQueryExecutor(
                frame=base_frame,
                telemetry=PromotionSqlExecutionTelemetry(
                    sql_connection_started_at_utc="2024-09-01T00:00:01+00:00",
                    sql_connection_completed_at_utc="2024-09-01T00:00:02+00:00",
                    query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                    query_execution_completed_at_utc="2024-09-01T00:00:03+00:00",
                    fetch_started_at_utc="2024-09-01T00:00:03+00:00",
                    fetch_completed_at_utc="2024-09-01T00:00:04+00:00",
                    current_sql_subphase="SQL fetch in progress",
                    connect_timeout_seconds=15,
                    connect_retry_attempts=2,
                    connect_retry_backoff_seconds=1.5,
                    connect_attempt_count=1,
                    query_timeout_seconds=45,
                    query_timeout_applied=True,
                ),
            )

            phase_updates: list[str] = []
            result = PromotionBaseExtractor(executor=executor).extract(
                run_id="observability-run",
                settings=settings,
                selection_mode="completed",
                phase_callback=phase_updates.append,
                query_options=PromotionBaseQueryOptions(
                    completed_partition=PromotionCompletedPartitionSettings(
                        strategy="store_number",
                        partition_count=8,
                        partition_index=3,
                    )
                ),
            )
            result.telemetry.current_sql_subphase = "writing extracted parquet and manifest"
            result.telemetry.dataframe_write_started_at_utc = "2024-09-01T00:00:04+00:00"
            result.telemetry.dataframe_write_completed_at_utc = "2024-09-01T00:00:05+00:00"
            result.telemetry.output_parquet_path = str(artifact_paths.extracted_base_path("observability-run"))
            result.telemetry.output_manifest_path = str(artifact_paths.extracted_manifest_path("observability-run"))
            result.telemetry.mark_success()

            observability = write_extraction_observability(
                telemetry=result.telemetry,
                settings=settings,
                artifact_paths=artifact_paths,
            )

            telemetry_payload = json.loads(Path(observability.telemetry_json_path).read_text(encoding="utf-8"))
            diagnostics_payload = json.loads(
                Path(observability.diagnostics_summary_json_path).read_text(encoding="utf-8")
            )
            diagnostics_text = Path(observability.diagnostics_summary_txt_path).read_text(encoding="utf-8")
            telemetry_csv = Path(observability.telemetry_csv_path).read_text(encoding="utf-8")

            self.assertIn("SQL query render in progress", phase_updates)
            self.assertIn("SQL fetch in progress", phase_updates)
            self.assertEqual(telemetry_payload["connect_timeout_seconds"], 15)
            self.assertEqual(telemetry_payload["connect_retry_attempts"], 2)
            self.assertEqual(telemetry_payload["connect_retry_backoff_seconds"], 1.5)
            self.assertEqual(telemetry_payload["query_timeout_seconds"], 45)
            self.assertEqual(telemetry_payload["candidate_promotion_row_count"], len(result.base_frame.index))
            self.assertEqual(telemetry_payload["row_count"], len(result.base_frame.index))
            self.assertEqual(telemetry_payload["partition_strategy"], "store_number")
            self.assertEqual(telemetry_payload["partition_count"], 8)
            self.assertEqual(telemetry_payload["partition_index"], 3)
            self.assertTrue(telemetry_payload["rendered_sql_path"].endswith("rendered_sql.sql"))
            self.assertEqual(
                diagnostics_payload["output_paths"]["telemetry_json_path"],
                observability.telemetry_json_path,
            )
            self.assertEqual(
                diagnostics_payload["output_paths"]["rendered_sql_path"],
                telemetry_payload["rendered_sql_path"],
            )
            self.assertEqual(
                diagnostics_payload["query_windows"]["estimated_sales_lookback_days"],
                settings.windows.baseline_lookback_days,
            )
            self.assertEqual(
                diagnostics_payload["query_windows"]["completed_promotion_buffer_days"],
                settings.completed_promotion_buffer_days,
            )
            self.assertIn("phase_elapsed_seconds", diagnostics_text)
            self.assertIn("candidate_promotion_row_count", diagnostics_text)
            self.assertIn("rendered_query_parameter_summary", diagnostics_text)
            self.assertIn("phase_elapsed_seconds", telemetry_csv)

    def test_sql_inspection_renders_summary_and_optional_connection_test(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
                connect_timeout_seconds=15,
                connect_retry_attempts=2,
                connect_retry_backoff_seconds=1.5,
                query_timeout_seconds=30,
            ),
            runtime_date=date(2024, 9, 1),
        )

        with patch(
            "runtime.promotions.inspect_promotions_sql_extraction.SqlAlchemyMssqlQueryExecutor.from_settings"
        ) as executor_factory:
            executor_factory.return_value.test_connection.return_value = PromotionSqlConnectionCheckResult(
                connected_at_utc="2024-09-01T00:00:05+00:00",
                elapsed_seconds=0.321,
                connect_timeout_seconds=15,
                connect_retry_attempts=2,
                connect_retry_backoff_seconds=1.5,
                connect_attempt_count=1,
                query_timeout_seconds=30,
                query_timeout_applied=True,
            )
            summary = inspect_sql_extraction(
                settings=settings,
                run_id="inspection-summary-run",
                selection_mode="future",
                test_connection=True,
            )

        stream = StringIO()
        render_sql_inspection_report(summary, stream=stream)
        rendered_output = stream.getvalue()

        self.assertEqual(summary.selection_mode, "future")
        self.assertEqual(summary.connect_timeout_seconds, 15)
        self.assertEqual(summary.connect_retry_attempts, 2)
        self.assertEqual(summary.connect_retry_backoff_seconds, 1.5)
        self.assertEqual(summary.query_timeout_seconds, 30)
        self.assertIsNotNone(summary.connection_test)
        self.assertIn("PROMOTIONS SQL EXTRACTION INSPECTION", rendered_output)
        self.assertIn("selection_mode: future", rendered_output)
        self.assertIn("connect_timeout_seconds: 15", rendered_output)
        self.assertIn("connect_retry_attempts: 2", rendered_output)
        self.assertIn("connect_retry_backoff_seconds: 1.5", rendered_output)
        self.assertIn("connection_test:", rendered_output)
        self.assertIn("RENDERED SQL", rendered_output)
        self.assertIn("promotion_base_v4", rendered_output)

    def test_main_prints_source_aware_startup_summary_without_secret_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".promotions.env"
            env_path.write_text(
                "\n".join(
                    (
                        "PROMOTIONS_MSSQL_SERVER=test-server",
                        "PROMOTIONS_MSSQL_DATABASE=test-database",
                        "PROMOTIONS_MSSQL_USERNAME=test-user",
                        "PROMOTIONS_MSSQL_PASSWORD=test-password",
                        "PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS=15",
                        "PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS=2",
                        "PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS=1.5",
                        "PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS=45",
                        "PROMOTIONS_MSSQL_ENCRYPT=yes",
                        "PROMOTIONS_MSSQL_TRUST_SERVER_CERTIFICATE=no",
                        "PROMOTIONS_ADVICE_TABLE=PromotionAdvice",
                    )
                ),
                encoding="utf-8",
            )
            summary = PromotionSqlInspectionSummary(
                run_id="inspect-startup-run",
                as_of_date="2024-09-01",
                selection_mode="completed",
                extraction_mode="live_sql",
                partition_strategy=None,
                partition_count=None,
                partition_index=None,
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
                query_version="promotion_base_v4",
                connect_timeout_seconds=15,
                connect_retry_attempts=2,
                connect_retry_backoff_seconds=1.5,
                query_timeout_seconds=45,
                enable_landed_batches=True,
                batch_row_count=1000,
                completed_sales_history_start_date="2024-01-01",
                enable_chunked_fetch=True,
                chunk_row_count=5000,
                resume_completed_partitions=True,
                stage_temp_chunk_files=True,
                rendered_query_parameter_summary={},
                diagnostic_filter_summary={},
                estimated_window_summary={},
                rendered_sql="SELECT 1",
            )

            stream = StringIO()
            with patch(
                "runtime.promotions.inspect_promotions_sql_extraction.inspect_sql_extraction",
                return_value=summary,
            ):
                main(
                    [
                        "--env-file",
                        str(env_path),
                        "--run-id",
                        "inspect-startup-run",
                        "--test-connection",
                    ],
                    stream=stream,
                )

        rendered_output = stream.getvalue()
        self.assertIn("PROMOTIONS SQL EXTRACTION STARTUP", rendered_output)
        self.assertIn("PROMOTIONS MSSQL SETTINGS", rendered_output)
        self.assertIn(f"config_source: explicit_env_file:{env_path}", rendered_output)
        self.assertIn("server: test-server (env:PROMOTIONS_MSSQL_SERVER)", rendered_output)
        self.assertIn("database: test-database (env:PROMOTIONS_MSSQL_DATABASE)", rendered_output)
        self.assertIn("user: test-user (env:PROMOTIONS_MSSQL_USERNAME)", rendered_output)
        self.assertIn("password_present: true (env:PROMOTIONS_MSSQL_PASSWORD)", rendered_output)
        self.assertIn(
            "connect_timeout_seconds: 15 (env:PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS)",
            rendered_output,
        )
        self.assertIn("query_timeout_seconds: 45 (env:PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS)", rendered_output)
        self.assertIn("encrypt: true (env:PROMOTIONS_MSSQL_ENCRYPT)", rendered_output)
        self.assertIn(
            "trust_server_certificate: false (env:PROMOTIONS_MSSQL_TRUST_SERVER_CERTIFICATE)",
            rendered_output,
        )
        self.assertNotIn("test-password", rendered_output)

    def test_main_shapes_missing_sql_config_without_traceback(self) -> None:
        stream = StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".promotions.env"
            env_path.write_text("PROMOTIONS_ADVICE_TABLE=PromotionAdvice\n", encoding="utf-8")
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(SystemExit) as raised:
                    main(
                        [
                            "--env-file",
                            str(env_path),
                        ],
                        stream=stream,
                    )

        self.assertEqual(raised.exception.code, 1)
        rendered_output = stream.getvalue()
        self.assertIn("FATAL PROMOTIONS SQL CONFIG ERROR", rendered_output)
        self.assertIn("field: server", rendered_output)
        self.assertIn(
            "expected_from: --server, PROMOTIONS_MSSQL_SERVER, PROMOTIONS_SQL_SERVER",
            rendered_output,
        )
        self.assertIn("next_action:", rendered_output)
        self.assertNotIn("Traceback", rendered_output)

    def test_inspector_writes_rendered_sql_and_parameter_json_with_row_count_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=15,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
            )

            with patch(
                "runtime.promotions.inspect_promotions_sql_extraction.SqlAlchemyMssqlQueryExecutor.from_settings"
            ) as executor_factory:
                executor_factory.return_value.fetch_dataframe.return_value = PromotionQueryExecutionResult(
                    frame=pd.DataFrame({"candidate_promotion_row_count": [12]}),
                    telemetry=PromotionSqlExecutionTelemetry(
                        query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                        query_execution_completed_at_utc="2024-09-01T00:00:03+00:00",
                        fetch_started_at_utc="2024-09-01T00:00:03+00:00",
                        fetch_completed_at_utc="2024-09-01T00:00:03+00:00",
                        current_sql_subphase="SQL fetch in progress",
                        query_timeout_seconds=15,
                        query_timeout_applied=True,
                    ),
                )
                summary = inspect_sql_extraction(
                    settings=settings,
                    run_id="inspect-rendered-sql-run",
                    selection_mode="completed",
                    query_options=PromotionBaseQueryOptions(
                        extraction_mode="diagnostic_topn",
                        limit_promotions=12,
                        store_number=5,
                        completed_partition=PromotionCompletedPartitionSettings(
                            strategy="supplier_number",
                            partition_count=16,
                            partition_index=4,
                        ),
                    ),
                    save_rendered_sql=True,
                    run_row_count_probe=True,
                )

            self.assertIsNotNone(summary.rendered_sql_path)
            self.assertIsNotNone(summary.rendered_sql_parameters_path)
            self.assertTrue(Path(summary.rendered_sql_path).exists())
            self.assertTrue(Path(summary.rendered_sql_parameters_path).exists())
            self.assertEqual(summary.row_count_probe["candidate_promotion_row_count"], 12)
            self.assertEqual(summary.partition_strategy, "supplier_number")
            self.assertEqual(summary.partition_count, 16)
            self.assertEqual(summary.partition_index, 4)
            parameter_payload = json.loads(
                Path(summary.rendered_sql_parameters_path).read_text(encoding="utf-8")
            )
            self.assertEqual(parameter_payload["limit_promotions"], 12)
            self.assertEqual(parameter_payload["diagnostic_store_number"], 5)
            self.assertEqual(parameter_payload["partition_strategy"], "supplier_number")
            self.assertEqual(parameter_payload["partition_count"], 16)
            self.assertEqual(parameter_payload["partition_index"], 4)
            self.assertEqual(parameter_payload["partition_bucket_index"], 3)

    def test_inspector_diagnostic_narrowing_flags_are_parsed_and_forwarded(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--selection-mode",
                "completed",
                "--extraction-mode",
                "diagnostic_topn",
                "--limit-promotions",
                "25",
                "--promotion-name-like",
                "Mega Sale",
                "--store-number",
                "7",
                "--supplier-number",
                "11",
                "--partition-strategy",
                "promotion_row_key_hash_bucket",
                "--partition-count",
                "32",
                "--partition-index",
                "6",
            ]
        )

        query_options = _build_query_options(args)

        self.assertEqual(query_options.extraction_mode, "diagnostic_topn")
        self.assertEqual(query_options.limit_promotions, 25)
        self.assertEqual(query_options.promotion_name_like, "Mega Sale")
        self.assertEqual(query_options.store_number, 7)
        self.assertEqual(query_options.supplier_number, 11)
        self.assertEqual(query_options.completed_partition.strategy, "promotion_row_key_hash_bucket")
        self.assertEqual(query_options.completed_partition.partition_count, 32)
        self.assertEqual(query_options.completed_partition.partition_index, 6)

    def test_preflight_planner_recommends_more_partitions_when_scope_is_too_wide(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=45,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
                completed_partitioning=PromotionCompletedPartitionSettings(
                    strategy="store_sku_hash_bucket",
                    partition_count=2,
                ),
                completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                    run_preflight=True,
                    max_candidate_store_sku=1000,
                ),
            )
            executor = _PreflightOnlyExecutor(
                frame=pd.DataFrame(
                    {
                        "candidate_promotion_row_count": [1200],
                        "candidate_store_sku_count": [2400],
                        "candidate_window_count": [2400],
                        "candidate_window_span_days_total": [4000],
                        "candidate_window_span_days_max": [14],
                        "observed_max_live_promo_days": [14],
                        "candidate_window_span_days_avg": [1.67],
                        "candidate_global_min_date": ["2024-01-01"],
                        "candidate_global_max_date": ["2024-09-01"],
                        "distinct_store_count": [80],
                        "distinct_sku_count": [600],
                    }
                ),
                telemetry=PromotionSqlExecutionTelemetry(
                    query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                    query_execution_completed_at_utc="2024-09-01T00:00:03+00:00",
                    fetch_started_at_utc="2024-09-01T00:00:03+00:00",
                    fetch_completed_at_utc="2024-09-01T00:00:03+00:00",
                    current_sql_subphase="SQL fetch in progress",
                    query_timeout_seconds=45,
                    query_timeout_applied=True,
                ),
            )

            result = PromotionBaseExtractor(executor=executor).run_preflight(
                run_id="planner-recommendation-run",
                settings=settings,
                selection_mode="completed",
                query_options=PromotionBaseQueryOptions(
                    completed_partition=settings.completed_partitioning.with_partition_index(1),
                ),
            )

            self.assertEqual(result.summary.verdict, "TOO_WIDE_REPARTITION_REQUIRED")
            self.assertEqual(result.summary.recommended_partition_strategy, "store_sku_hash_bucket")
            # Planner applies a 1.5x skew-safety multiplier on top of the
            # proportional bump so a single retry escapes hash-bucket skew
            # rather than creeping up by 1-2 partitions per attempt.
            # current=2, dominant_ratio=2400/1000=2.4, multiplier=1.5
            # -> ceil(2 * 2.4 * 1.5) = ceil(7.2) = 8
            self.assertEqual(result.summary.recommended_partition_count, 8)
            self.assertTrue(Path(result.artifacts.summary_json_path).exists())
            self.assertTrue(Path(result.artifacts.rendered_sql_path).exists())

    def test_preflight_planner_recommends_more_partitions_when_slice_is_too_expensive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=60,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
                completed_partitioning=PromotionCompletedPartitionSettings(
                    strategy="promotion_row_key_hash_bucket",
                    partition_count=2,
                ),
                completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                    run_preflight=True,
                    max_estimated_cost_score=1.0,
                    max_candidate_promotion_rows=100_000,
                    max_candidate_store_sku=100_000,
                    max_window_span_days_total=None,
                    preflight_query_execution_seconds_multiplier=20.0,
                ),
            )
            executor = _PreflightOnlyExecutor(
                frame=pd.DataFrame(
                    {
                        "candidate_promotion_row_count": [25],
                        "candidate_store_sku_count": [25],
                        "candidate_window_count": [25],
                        "candidate_window_span_days_total": [220_000],
                        "candidate_window_span_days_max": [100],
                        "observed_max_live_promo_days": [30],
                        "candidate_window_span_days_avg": [8800.0],
                        "candidate_global_min_date": ["2024-01-01"],
                        "candidate_global_max_date": ["2024-09-01"],
                        "distinct_store_count": [1],
                        "distinct_sku_count": [25],
                    }
                ),
                telemetry=PromotionSqlExecutionTelemetry(
                    query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                    query_execution_completed_at_utc="2024-09-01T00:00:17.500000+00:00",
                    fetch_started_at_utc="2024-09-01T00:00:17.500000+00:00",
                    fetch_completed_at_utc="2024-09-01T00:00:17.600000+00:00",
                    current_sql_subphase="SQL fetch in progress",
                    query_timeout_seconds=60,
                    query_timeout_applied=True,
                ),
            )

            result = PromotionBaseExtractor(executor=executor).run_preflight(
                run_id="planner-cost-run",
                settings=settings,
                selection_mode="completed",
                query_options=PromotionBaseQueryOptions(
                    completed_partition=settings.completed_partitioning.with_partition_index(1),
                ),
            )

            self.assertEqual(result.summary.verdict, "TOO_WIDE_REPARTITION_REQUIRED")
            self.assertGreater(result.summary.estimated_cost_score or 0.0, 1.0)
            self.assertEqual(
                result.summary.cost_guardrail_verdict,
                "TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET",
            )
            self.assertIn("decomposed model", (result.summary.cost_guardrail_reason or "").lower())
            self.assertEqual(result.summary.recommended_partition_strategy, "promotion_row_key_hash_bucket")
            self.assertGreaterEqual(result.summary.recommended_partition_count or 0, 3)

    def test_completed_preflight_allows_window_span_within_grouped_grain_theoretical_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=300,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
                completed_partitioning=PromotionCompletedPartitionSettings(
                    strategy="promotion_row_key_hash_bucket",
                    partition_count=30,
                ),
                completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                    run_preflight=True,
                ),
            )
            executor = _PreflightOnlyExecutor(
                frame=pd.DataFrame(
                    {
                        "candidate_promotion_row_count": [873],
                        "candidate_store_sku_count": [833],
                        "candidate_window_count": [833],
                        "candidate_window_span_days_total": [68917],
                        "candidate_window_span_days_max": [149],
                        "observed_max_grouped_live_window_span_days": [79],
                        "observed_max_live_promo_days": [30],
                        "candidate_window_span_days_avg": [82.733],
                        "candidate_global_min_date": ["2024-04-16"],
                        "candidate_global_max_date": ["2024-09-13"],
                        "distinct_store_count": [1],
                        "distinct_sku_count": [833],
                    }
                ),
                telemetry=PromotionSqlExecutionTelemetry(
                    query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                    query_execution_completed_at_utc="2024-09-01T00:00:04+00:00",
                    fetch_started_at_utc="2024-09-01T00:00:04+00:00",
                    fetch_completed_at_utc="2024-09-01T00:00:04.100000+00:00",
                    current_sql_subphase="SQL fetch in progress",
                    query_timeout_seconds=300,
                    query_timeout_applied=True,
                ),
            )

            result = PromotionBaseExtractor(executor=executor).run_preflight(
                run_id="dynamic-window-safe-run",
                settings=settings,
                selection_mode="completed",
                query_options=PromotionBaseQueryOptions(
                    completed_partition=settings.completed_partitioning.with_partition_index(1),
                ),
            )

            self.assertEqual(result.summary.verdict, "SAFE_TO_EXTRACT")
            self.assertEqual(result.summary.observed_max_grouped_live_window_span_days, 79)
            self.assertEqual(result.summary.observed_max_live_promo_days, 30)
            self.assertEqual(result.summary.theoretical_completed_window_span_days_max, 149)
            self.assertEqual(result.summary.planner_thresholds["max_window_span_days_max"], 149)
            self.assertIn("did not exceed", result.summary.reason)
            self.assertIn("grouped store/SKU merged candidate-window grain", result.summary.reason)

    def test_completed_preflight_rejects_window_span_above_grouped_grain_theoretical_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=300,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
                completed_partitioning=PromotionCompletedPartitionSettings(
                    strategy="promotion_row_key_hash_bucket",
                    partition_count=30,
                ),
                completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                    run_preflight=True,
                ),
            )
            executor = _PreflightOnlyExecutor(
                frame=pd.DataFrame(
                    {
                        "candidate_promotion_row_count": [873],
                        "candidate_store_sku_count": [833],
                        "candidate_window_count": [833],
                        "candidate_window_span_days_total": [68917],
                        "candidate_window_span_days_max": [150],
                        "observed_max_grouped_live_window_span_days": [79],
                        "observed_max_live_promo_days": [30],
                        "candidate_window_span_days_avg": [82.733],
                        "candidate_global_min_date": ["2024-04-16"],
                        "candidate_global_max_date": ["2024-09-13"],
                        "distinct_store_count": [1],
                        "distinct_sku_count": [833],
                    }
                ),
                telemetry=PromotionSqlExecutionTelemetry(
                    query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                    query_execution_completed_at_utc="2024-09-01T00:00:04+00:00",
                    fetch_started_at_utc="2024-09-01T00:00:04+00:00",
                    fetch_completed_at_utc="2024-09-01T00:00:04.100000+00:00",
                    current_sql_subphase="SQL fetch in progress",
                    query_timeout_seconds=300,
                    query_timeout_applied=True,
                ),
            )

            result = PromotionBaseExtractor(executor=executor).run_preflight(
                run_id="dynamic-window-reject-run",
                settings=settings,
                selection_mode="completed",
                query_options=PromotionBaseQueryOptions(
                    completed_partition=settings.completed_partitioning.with_partition_index(1),
                ),
            )

            self.assertEqual(result.summary.verdict, "TOO_WIDE_REPARTITION_REQUIRED")
            self.assertEqual(result.summary.observed_max_grouped_live_window_span_days, 79)
            self.assertEqual(result.summary.observed_max_live_promo_days, 30)
            self.assertEqual(result.summary.theoretical_completed_window_span_days_max, 149)
            self.assertEqual(result.summary.planner_thresholds["max_window_span_days_max"], 149)
            self.assertIn("exceeds the theoretical completed max 149", result.summary.reason)
            self.assertIn("grouped store/SKU merged candidate-window grain", result.summary.reason)

    def test_future_preflight_behavior_remains_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    query_timeout_seconds=45,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
                completed_preflight_planner=PromotionCompletedPreflightPlannerSettings(
                    run_preflight=True,
                    max_window_span_days_max=120,
                ),
            )
            executor = _PreflightOnlyExecutor(
                frame=pd.DataFrame(
                    {
                        "candidate_promotion_row_count": [1200],
                        "candidate_store_sku_count": [2400],
                        "candidate_window_count": [2400],
                        "candidate_window_span_days_total": [400000],
                        "candidate_window_span_days_max": [999],
                        "observed_max_live_promo_days": [999],
                        "candidate_window_span_days_avg": [166.7],
                        "candidate_global_min_date": ["2024-01-01"],
                        "candidate_global_max_date": ["2024-09-01"],
                        "distinct_store_count": [80],
                        "distinct_sku_count": [600],
                    }
                ),
                telemetry=PromotionSqlExecutionTelemetry(
                    query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                    query_execution_completed_at_utc="2024-09-01T00:00:03+00:00",
                    fetch_started_at_utc="2024-09-01T00:00:03+00:00",
                    fetch_completed_at_utc="2024-09-01T00:00:03+00:00",
                    current_sql_subphase="SQL fetch in progress",
                    query_timeout_seconds=45,
                    query_timeout_applied=True,
                ),
            )

            result = PromotionBaseExtractor(executor=executor).run_preflight(
                run_id="future-preflight-run",
                settings=settings,
                selection_mode="future",
                query_options=PromotionBaseQueryOptions(),
            )

            self.assertEqual(result.summary.verdict, "SAFE_TO_EXTRACT")
            self.assertEqual(
                result.summary.reason,
                "Preflight planner thresholds are enforced only for completed extraction mode.",
            )
            self.assertIsNone(result.summary.theoretical_completed_window_span_days_max)
            self.assertEqual(result.summary.planner_thresholds["max_window_span_days_max"], 120)

    def test_inspector_planner_only_reports_preflight_rejection_without_running_extraction(self) -> None:
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
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
            )
            preflight_result = _build_preflight_result(
                artifact_paths=artifact_paths,
                run_id="planner-only-run",
                as_of_date=settings.as_of_date.isoformat(),
                verdict="TOO_WIDE_REPARTITION_REQUIRED",
                reason="candidate_store_sku_count exceeds configured threshold",
                recommended_partition_strategy="store_sku_hash_bucket",
                recommended_partition_count=3,
            )

            with patch(
                "runtime.promotions.inspect_promotions_sql_extraction.SqlAlchemyMssqlQueryExecutor.from_settings"
            ) as executor_factory, patch(
                "runtime.promotions.inspect_promotions_sql_extraction.PromotionBaseExtractor.run_preflight",
                return_value=preflight_result,
            ):
                executor_factory.return_value = object()
                summary = inspect_sql_extraction(
                    settings=settings,
                    run_id="planner-only-run",
                    selection_mode="completed",
                    planner_only=True,
                )

            self.assertEqual(summary.planner_verdict, "TOO_WIDE_REPARTITION_REQUIRED")
            self.assertEqual(summary.recommended_partition_strategy, "store_sku_hash_bucket")
            self.assertEqual(summary.recommended_partition_count, 3)
            self.assertIsNone(summary.row_count_probe)
            self.assertIsNone(summary.execution_result)
            self.assertTrue(summary.preflight_summary_json_path.endswith("extraction_preflight_summary.json"))

    def test_inspector_preflight_rejection_renders_recommended_rerun_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            settings = PromotionPipelineSettings.for_runtime_date(
                sql=PromotionMssqlSettings(
                    server="test-server",
                    database="test-database",
                    schema="dbo",
                    promotion_advice_table="dbo.PromotionAdvice",
                    pwlogd_table="dbo.PwlogD",
                    connect_timeout_seconds=30,
                    connect_retry_attempts=2,
                    connect_retry_backoff_seconds=2.0,
                    query_timeout_seconds=300,
                ),
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
                completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings.from_env(
                    enable_landed_batches=True,
                    batch_row_count=1000,
                    completed_sales_history_start_date="2024-01-01",
                    enable_chunked_fetch=True,
                    chunk_row_count=5000,
                    resume_completed_partitions=True,
                    stage_temp_chunk_files=True,
                ),
            )
            preflight_result = _build_preflight_result(
                artifact_paths=artifact_paths,
                run_id="rerun-command-run",
                as_of_date=settings.as_of_date.isoformat(),
                verdict="TOO_WIDE_REPARTITION_REQUIRED",
                reason="candidate_store_sku_count exceeds configured threshold",
                recommended_partition_strategy="promotion_row_key_hash_bucket",
                recommended_partition_count=24,
                observed_max_live_promo_days=54,
                theoretical_completed_window_span_days_max=124,
            )

            with patch(
                "runtime.promotions.inspect_promotions_sql_extraction.SqlAlchemyMssqlQueryExecutor.from_settings"
            ) as executor_factory, patch(
                "runtime.promotions.inspect_promotions_sql_extraction.PromotionBaseExtractor.run_preflight",
                return_value=preflight_result,
            ):
                executor_factory.return_value = object()
                summary = inspect_sql_extraction(
                    settings=settings,
                    run_id="rerun-command-run",
                    selection_mode="completed",
                    run_extraction=True,
                    query_options=PromotionBaseQueryOptions(
                        completed_partition=PromotionCompletedPartitionSettings(
                            strategy="promotion_row_key_hash_bucket",
                            partition_count=8,
                            partition_index=1,
                        )
                    ),
                )

            self.assertIsNotNone(summary.recommended_rerun_command)
            self.assertIn("--connect-timeout-seconds 30", summary.recommended_rerun_command)
            self.assertIn("--connect-retry-attempts 2", summary.recommended_rerun_command)
            self.assertIn("--connect-retry-backoff-seconds 2.0", summary.recommended_rerun_command)
            self.assertIn("--query-timeout-seconds 300", summary.recommended_rerun_command)
            self.assertIn("--enable-landed-batches true", summary.recommended_rerun_command)
            self.assertIn("--batch-row-count 1000", summary.recommended_rerun_command)
            self.assertIn(
                "--completed-sales-history-start-date 2024-01-01",
                summary.recommended_rerun_command,
            )
            self.assertIn("--partition-count 24", summary.recommended_rerun_command)
            self.assertIn("--partition-strategy promotion_row_key_hash_bucket", summary.recommended_rerun_command)
            self.assertEqual(summary.observed_max_live_promo_days, 54)
            self.assertEqual(summary.theoretical_completed_window_span_days_max, 124)

            stream = StringIO()
            render_sql_inspection_report(summary, stream=stream)
            rendered_output = stream.getvalue()

            self.assertIn("next_recommended_partition_count: 24", rendered_output)
            self.assertIn(
                "next_recommended_partition_strategy: promotion_row_key_hash_bucket",
                rendered_output,
            )
            self.assertIn("observed_max_live_promo_days: 54", rendered_output)
            self.assertIn("theoretical_completed_window_span_days_max: 124", rendered_output)
            self.assertIn("recommended_rerun_command:", rendered_output)

    def test_inspector_preflight_builder_preserves_default_thresholds_when_cli_flags_omitted(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--selection-mode", "completed"])

        planner = _build_completed_preflight_planner_from_args(args)

        self.assertFalse(planner.run_preflight)
        self.assertFalse(planner.planner_only)
        self.assertEqual(planner.max_candidate_promotion_rows, 2000)
        self.assertEqual(planner.max_candidate_store_sku, 1000)
        self.assertEqual(planner.max_window_span_days_total, 125000)
        self.assertEqual(planner.max_window_span_days_max, 120)

    def test_inspector_main_forwards_planner_flags(self) -> None:
        with patch(
            "runtime.promotions.inspect_promotions_sql_extraction.inspect_sql_extraction"
        ) as inspect_mock, patch(
            "runtime.promotions.inspect_promotions_sql_extraction.render_sql_inspection_report"
        ):
            inspect_mock.return_value = PromotionSqlConnectionCheckResult(
                connected_at_utc="2024-09-01T00:00:05+00:00",
                elapsed_seconds=0.321,
                query_timeout_seconds=30,
                query_timeout_applied=True,
            )
            main(
                [
                    "--selection-mode",
                    "completed",
                    "--run-preflight",
                    "--planner-only",
                    "--as-of-date",
                    "2024-09-01",
                ]
            )

        self.assertTrue(inspect_mock.called)
        self.assertTrue(inspect_mock.call_args.kwargs["run_preflight"])
        self.assertTrue(inspect_mock.call_args.kwargs["planner_only"])

    def test_inspector_execution_result_includes_staged_partition_validation_summary(self) -> None:
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
                runtime_date=date(2024, 9, 1),
                artifacts=artifact_paths,
            )
            run_id = "inspect-stage3-summary"
            frame = build_completed_promotions_base_frame().iloc[:1].reset_index(drop=True)
            batch_run_id = f"{run_id}-batch-000001"
            base_stage_run_id = f"{batch_run_id}-base"
            partition_manifest_path = artifact_paths.extracted_manifest_path(run_id)
            batch_manifest_path = artifact_paths.extracted_manifest_path(batch_run_id)
            base_stage_manifest_path = artifact_paths.extracted_manifest_path(base_stage_run_id)
            for path in (
                partition_manifest_path,
                batch_manifest_path,
                base_stage_manifest_path,
                artifact_paths.extraction_telemetry_json_path(run_id),
                artifact_paths.extraction_telemetry_json_path(batch_run_id),
                artifact_paths.extraction_telemetry_json_path(base_stage_run_id),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
            partition_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "partition_count": 8,
                        "partition_index": 2,
                        "completed_sales_history_start_date": "2024-01-01",
                        "child_batch_manifest_paths": [str(batch_manifest_path)],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_partition_progress_path(run_id).write_text(
                json.dumps({"batch_row_count": 1000}, sort_keys=True),
                encoding="utf-8",
            )
            batch_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": batch_run_id,
                        "row_count": 1,
                        "completed_sales_history_start_date": "2024-01-01",
                        "child_stage_manifest_paths": [str(base_stage_manifest_path)],
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            base_stage_manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": base_stage_run_id,
                        "extraction_stage": "completed_base",
                        "row_count": 1,
                        "completed_sales_history_start_date": "2024-01-01",
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifact_paths.extraction_telemetry_json_path(run_id).write_text(
                json.dumps({"phase_elapsed_seconds": {}, "total_elapsed_seconds": 10.0}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.extraction_telemetry_json_path(batch_run_id).write_text(
                json.dumps({"total_elapsed_seconds": 1.0}, sort_keys=True),
                encoding="utf-8",
            )
            artifact_paths.extraction_telemetry_json_path(base_stage_run_id).write_text(
                json.dumps({"total_elapsed_seconds": 0.5}, sort_keys=True),
                encoding="utf-8",
            )

            extraction_artifact = PromotionOperationalCycleExtractionArtifacts(
                selection_mode="completed",
                frame=frame,
                base_path=str(artifact_paths.extracted_base_path(run_id)),
                manifest_path=str(partition_manifest_path),
                rendered_sql_path=str(artifact_paths.manifests_run_root(run_id) / "rendered_sql.sql"),
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
                candidate_promotion_row_count=1,
                manifest={
                    "run_id": run_id,
                    "row_count": 1,
                },
                extraction_mode="live_sql",
                partition_strategy="promotion_row_key_hash_bucket",
                partition_count=8,
                partition_index=2,
            )

            with patch(
                "runtime.promotions.inspect_promotions_sql_extraction._extract_promotions_base_artifact",
                return_value=extraction_artifact,
            ), patch(
                "runtime.promotions.inspect_promotions_sql_extraction.PromotionBaseExtractor.run_preflight",
                return_value=_build_preflight_result(
                    artifact_paths=artifact_paths,
                    run_id=run_id,
                    as_of_date=settings.as_of_date.isoformat(),
                    verdict="SAFE_TO_EXTRACT",
                    reason="test preflight stub",
                ),
            ):
                summary = inspect_sql_extraction(
                    settings=settings,
                    run_id=run_id,
                    selection_mode="completed",
                    run_extraction=True,
                    query_options=PromotionBaseQueryOptions(
                        completed_partition=PromotionCompletedPartitionSettings(
                            strategy="promotion_row_key_hash_bucket",
                            partition_count=8,
                            partition_index=2,
                        )
                    ),
                )

            self.assertIsNotNone(summary.execution_result)
            staged_validation = summary.execution_result.get("staged_partition_validation")
            self.assertIsInstance(staged_validation, dict)
            self.assertEqual(staged_validation.get("partition_index"), 2)
            self.assertEqual(staged_validation.get("partition_count"), 8)
            self.assertEqual(
                staged_validation.get("completed_sales_history_start_date"),
                "2024-01-01",
            )
            records = staged_validation.get("records")
            self.assertIsInstance(records, list)
            self.assertTrue(any(record.get("stage_name") == "completed_base" for record in records))