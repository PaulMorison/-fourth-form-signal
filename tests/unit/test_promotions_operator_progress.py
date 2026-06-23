from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths, PromotionMssqlSettings  # noqa: E402
from data.promotions.mssql_query_executor import (  # noqa: E402
    PromotionMssqlConnectionTimeoutError,
    PromotionMssqlQueryTimeoutError,
)
from runtime.promotions.operator_progress import (  # noqa: E402
    PromotionOperatorProgress,
    classify_operator_failure,
)


class PromotionOperatorProgressTests(unittest.TestCase):
    def test_progress_persists_logs_summaries_and_failure_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            stream = StringIO()
            progress = PromotionOperatorProgress(
                run_id="operator-progress-run",
                artifact_paths=artifact_paths,
                stream=stream,
            )
            sql_settings_summary = PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
                username="config-user",
                password="super-secret",
                connect_timeout_seconds=15,
                connect_retry_attempts=2,
                connect_retry_backoff_seconds=1.5,
                query_timeout_seconds=60,
            ).safe_summary()

            progress.start_run(
                as_of_date="2024-09-01",
                artifact_root=artifact_paths.root,
                local_inspection_root=artifact_paths.local_inspection_root,
                server="test-server",
                database="test-database",
                connect_timeout_seconds=15,
                connect_retry_attempts=2,
                connect_retry_backoff_seconds=1.5,
                query_timeout_seconds=60,
                partition_strategy="promotion_row_key_hash_bucket",
                partition_count=16,
                auto_repartition_completed=False,
                max_completed_repartition_attempts=2,
                max_completed_partition_count=128,
                sql_settings_summary=sql_settings_summary,
            )
            progress.start_stage(1, 11, "Load runtime config")
            progress.complete_stage(
                output_paths=(artifact_paths.root,),
                note="Runtime settings resolved.",
            )
            progress.start_stage(2, 11, "Validate NAS output roots")
            error = ValueError("PROMOTIONS_MSSQL_SERVER must be set before runtime execution")
            setattr(error, "current_sql_subphase", "SQL executing")
            setattr(error, "extraction_telemetry_json_path", str(artifact_paths.extraction_telemetry_json_path("operator-progress-run")))
            setattr(error, "extraction_telemetry_csv_path", str(artifact_paths.extraction_telemetry_csv_path("operator-progress-run")))
            setattr(error, "sql_diagnostics_summary_json_path", str(artifact_paths.sql_diagnostics_summary_json_path("operator-progress-run")))
            setattr(error, "sql_diagnostics_summary_txt_path", str(artifact_paths.sql_diagnostics_summary_txt_path("operator-progress-run")))
            failure_record = progress.fail(error)
            artifacts = progress.persist(status="failed")

            summary_payload = json.loads(Path(artifacts.summary_path).read_text(encoding="utf-8"))
            rendered_output = stream.getvalue()

            self.assertIn("START STAGE 1/11: Load runtime config", rendered_output)
            self.assertIn("FINISH STAGE 1/11: Load runtime config", rendered_output)
            self.assertIn("mode: live_sql", rendered_output)
            self.assertIn("execution_mode: live_sql", rendered_output)
            self.assertIn("local_inspection_root:", rendered_output)
            self.assertIn("PROMOTIONS MSSQL SETTINGS", rendered_output)
            self.assertIn("user: config-user (manual_object)", rendered_output)
            self.assertIn("authentication_mode: sql_username_password (derived)", rendered_output)
            self.assertIn("password_present: true (manual_object)", rendered_output)
            self.assertIn("connect_timeout_seconds: 15", rendered_output)
            self.assertIn("connect_retry_attempts: 2", rendered_output)
            self.assertIn("connect_retry_backoff_seconds: 1.5", rendered_output)
            self.assertIn("query_timeout_seconds: 60", rendered_output)
            self.assertIn("partition_strategy: promotion_row_key_hash_bucket", rendered_output)
            self.assertIn("partition_count: 16", rendered_output)
            self.assertIn("auto_repartition_completed: false", rendered_output)
            self.assertIn("max_completed_repartition_attempts: 2", rendered_output)
            self.assertIn("max_completed_partition_count: 128", rendered_output)
            self.assertIn("operator_summary_csv:", rendered_output)
            self.assertIn("FAILED STAGE", rendered_output)
            self.assertIn("stage: 2/11 Validate NAS output roots", rendered_output)
            self.assertIn("exception_type: ValueError", rendered_output)
            self.assertIn("subphase: SQL executing", rendered_output)
            self.assertIn("next_action:", rendered_output)
            self.assertIn("extraction_telemetry_path:", rendered_output)
            self.assertIn("sql_diagnostics_summary_path:", rendered_output)
            self.assertIn("operator_log_path:", rendered_output)
            self.assertIn("manifest_root:", rendered_output)
            self.assertGreaterEqual(rendered_output.count("run_id: operator-progress-run"), 2)
            self.assertNotIn("super-secret", rendered_output)
            self.assertEqual(failure_record.owner, "operator")
            self.assertEqual(failure_record.exception_type, "ValueError")
            self.assertEqual(failure_record.sql_subphase, "SQL executing")
            self.assertEqual(len(failure_record.failure_artifact_paths), 4)
            self.assertTrue(Path(artifacts.log_path).exists())
            self.assertTrue(Path(artifacts.summary_path).exists())
            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.stage_timings_path).exists())
            self.assertEqual(summary_payload["status"], "failed")
            self.assertEqual(summary_payload["stages"][1]["owner"], "operator")

    def test_progress_heartbeat_output_is_line_oriented_and_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            stream = StringIO()
            progress = PromotionOperatorProgress(
                run_id="operator-heartbeat-run",
                artifact_paths=artifact_paths,
                stream=stream,
            )

            progress.start_run(
                as_of_date="2024-09-01",
                artifact_root=artifact_paths.root,
                local_inspection_root=artifact_paths.local_inspection_root,
                server="test-server",
                database="test-database",
                execution_mode="smoke_synthetic",
                query_timeout_seconds=None,
            )
            progress.start_stage(3, 11, "Extract completed promotions")
            with progress.heartbeat(
                "waiting on SQL extraction",
                heartbeat_seconds=0.01,
                row_count=42,
            ):
                progress.update_heartbeat(subtask="SQL fetch in progress", row_count=42, emit_now=True)
                time.sleep(0.04)
            progress.complete_stage(
                row_count=42,
                file_count=2,
                output_paths=(artifact_paths.root,),
                note="Completed promotions base extract persisted.",
            )
            artifacts = progress.persist(status="completed")
            rendered_output = stream.getvalue()

            self.assertTrue(Path(artifacts.log_path).exists())
            self.assertIn("HEARTBEAT STAGE 3/11 | Extract completed promotions", rendered_output)
            self.assertIn("SQL fetch in progress", rendered_output)
            self.assertIn("elapsed_seconds:", rendered_output)
            self.assertIn("rows: 42", rendered_output)

    def test_query_timeout_failure_is_shaped_as_sql_diagnostics_action(self) -> None:
        owner, reason, action = classify_operator_failure(
            PromotionMssqlQueryTimeoutError("Query timeout expired during SQL executing")
        )

        self.assertEqual(owner, "operator")
        self.assertIn("Query timeout expired", reason)
        self.assertIn("SQL diagnostics summary", action)

    def test_connect_timeout_failure_is_shaped_as_connect_login_action(self) -> None:
        owner, reason, action = classify_operator_failure(
            PromotionMssqlConnectionTimeoutError(
                "Promotions MSSQL connect/login timed out before SQL execution started."
            )
        )

        self.assertEqual(owner, "operator")
        self.assertIn("connect/login timed out", reason)
        self.assertIn("before execution started", action)

    def test_cost_guardrail_failure_is_shaped_as_live_timeout_budget_action(self) -> None:
        error = type(
            "PromotionCompletedPreflightRejectedError",
            (RuntimeError,),
            {},
        )("slice is too expensive for the live timeout budget")
        setattr(error, "cost_guardrail_verdict", "TOO_EXPENSIVE_FOR_LIVE_TIMEOUT_BUDGET")

        owner, reason, action = classify_operator_failure(error)

        self.assertEqual(owner, "operator")
        self.assertIn("too expensive", reason)
        self.assertIn("live timeout budget", action)

    def test_interrupted_failure_is_shaped_as_operator_cancellation_action(self) -> None:
        error = RuntimeError("Stage 3 extraction interrupted")
        setattr(error, "stage3_interrupted", True)

        owner, reason, action = classify_operator_failure(error)

        self.assertEqual(owner, "operator")
        self.assertIn("interrupted", reason)
        self.assertIn("operator cancellation", action)

    def test_operator_display_mode_formats_clean_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "promotions_artifacts",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            stream = StringIO()
            progress = PromotionOperatorProgress(
                run_id="operator-display-run",
                artifact_paths=artifact_paths,
                stream=stream,
                display_mode="operator",
            )
            progress.start_run(
                as_of_date="2026-05-20",
                artifact_root=artifact_paths.root,
                local_inspection_root=artifact_paths.local_inspection_root,
                server="test-server",
                database="test-database",
                execution_mode="live_sql",
            )
            progress.start_stage(1, 14, "Load runtime config")
            progress.complete_stage(note="ready")
            progress.start_stage(5, 14, "Train model bundle")
            progress.complete_stage(row_count=1200, note="trained")
            progress.persist(status="completed")
            progress.finalize_operator_view(status="completed")

            rendered_output = stream.getvalue()
            self.assertIn("PROMOTIONS RUN", rendered_output)
            self.assertIn("[ 1/14] Load runtime config", rendered_output)
            self.assertIn("RUN SUMMARY", rendered_output)
            self.assertNotIn("PROMOTIONS MSSQL SETTINGS", rendered_output)
            self.assertNotIn("START STAGE", rendered_output)
