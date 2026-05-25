from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionRuntimeConfigError  # noqa: E402
from runtime.promotions.run_promotions_operator import main as operator_main  # noqa: E402


class PromotionOperatorCliTests(unittest.TestCase):
    @patch("runtime.promotions.run_promotions_operator._dispatch_smoke")
    def test_smoke_command_forwards_operator_args(self, dispatch_smoke) -> None:
        operator_main(
            [
                "smoke",
                "--run-id",
                "smoke-observation-run",
                "--artifact-root",
                "/tmp/promotions-operator-smoke",
                "--local-inspection-root",
                "/tmp/promotions-operator-smoke-local",
                "--mode",
                "smoke_patched_extraction",
                "--completed-base-path",
                "/tmp/completed.parquet",
                "--future-base-path",
                "/tmp/future.parquet",
            ]
        )

        dispatch_smoke.assert_called_once()
        forwarded_argv = dispatch_smoke.call_args.args[0]
        self.assertIn("--run-id", forwarded_argv)
        self.assertIn("smoke-observation-run", forwarded_argv)
        self.assertIn("--mode", forwarded_argv)
        self.assertIn("smoke_patched_extraction", forwarded_argv)
        self.assertIn("--completed-base-path", forwarded_argv)
        self.assertIn("/tmp/future.parquet", forwarded_argv)

    @patch("runtime.promotions.run_promotions_operator._dispatch_live")
    def test_live_command_forwards_partition_and_planner_flags(self, dispatch_live) -> None:
        stream = StringIO()
        operator_main(
            [
                "live",
                "--run-id",
                "live-observation-run",
                "--artifact-root",
                "/tmp/promotions-operator-live",
                "--connect-timeout-seconds",
                "15",
                "--connect-retry-attempts",
                "2",
                "--connect-retry-backoff-seconds",
                "1.5",
                "--query-timeout-seconds",
                "60",
                "--partition-strategy",
                "promotion_row_key_hash_bucket",
                "--partition-count",
                "16",
                "--auto-repartition-completed",
                "false",
                "--max-completed-repartition-attempts",
                "2",
                "--max-completed-partition-count",
                "128",
                "--proof-mode",
                "--proof-future-fallback-mode",
                "proof_slice",
                "--proof-future-fallback-topn-limit",
                "40",
                "--proof-future-fallback-slice-promotions",
                "12",
                "--proof-completed-fallback-mode",
                "diagnostic_topn",
                "--proof-completed-fallback-topn-limit",
                "25",
                "--proof-completed-fallback-slice-promotions",
                "12",
                "--planner-only",
            ],
            stream=stream,
        )

        dispatch_live.assert_called_once()
        forwarded_argv = dispatch_live.call_args.args[0]
        self.assertIn("--connect-timeout-seconds", forwarded_argv)
        self.assertIn("15", forwarded_argv)
        self.assertIn("--connect-retry-attempts", forwarded_argv)
        self.assertIn("2", forwarded_argv)
        self.assertIn("--connect-retry-backoff-seconds", forwarded_argv)
        self.assertIn("1.5", forwarded_argv)
        self.assertIn("--query-timeout-seconds", forwarded_argv)
        self.assertIn("60", forwarded_argv)
        self.assertIn("--partition-strategy", forwarded_argv)
        self.assertIn("promotion_row_key_hash_bucket", forwarded_argv)
        self.assertIn("--auto-repartition-completed", forwarded_argv)
        self.assertIn("false", forwarded_argv)
        self.assertIn("--max-completed-repartition-attempts", forwarded_argv)
        self.assertIn("2", forwarded_argv)
        self.assertIn("--max-completed-partition-count", forwarded_argv)
        self.assertIn("128", forwarded_argv)
        self.assertIn("--planner-only", forwarded_argv)
        rendered_output = stream.getvalue()
        self.assertIn("PROMOTIONS OPERATOR CLI", rendered_output)
        self.assertIn("execution_mode: live_sql", rendered_output)
        self.assertIn("command_line:", rendered_output)
        self.assertIn("proof_future_fallback_mode: proof_slice", rendered_output)
        self.assertIn("proof_future_fallback_topn_limit: 40", rendered_output)
        self.assertIn("proof_future_fallback_slice_promotions: 12", rendered_output)
        self.assertIn("proof_completed_fallback_mode: diagnostic_topn", rendered_output)
        self.assertIn("proof_completed_fallback_topn_limit: 25", rendered_output)
        self.assertIn("proof_completed_fallback_slice_promotions: 12", rendered_output)
        self.assertIn(
            "-m runtime.promotions.run_promotions_operator live --run-id live-observation-run",
            rendered_output,
        )
        self.assertIn("--proof-mode", forwarded_argv)
        self.assertIn("--proof-future-fallback-mode", forwarded_argv)
        self.assertIn("proof_slice", forwarded_argv)
        self.assertIn("--proof-future-fallback-topn-limit", forwarded_argv)
        self.assertIn("40", forwarded_argv)
        self.assertIn("--proof-future-fallback-slice-promotions", forwarded_argv)
        self.assertIn("12", forwarded_argv)
        self.assertIn("--proof-completed-fallback-mode", forwarded_argv)
        self.assertIn("diagnostic_topn", forwarded_argv)
        self.assertIn("--proof-completed-fallback-topn-limit", forwarded_argv)
        self.assertIn("25", forwarded_argv)
        self.assertIn("--proof-completed-fallback-slice-promotions", forwarded_argv)
        self.assertIn("12", forwarded_argv)

    @patch("runtime.promotions.run_promotions_operator._dispatch_live")
    def test_live_command_parses_without_optional_completed_proof_fallback_flags(self, dispatch_live) -> None:
        operator_main(
            [
                "live",
                "--run-id",
                "live-compat-run",
                "--artifact-root",
                "/tmp/promotions-operator-live",
            ]
        )

        dispatch_live.assert_called_once()
        forwarded_argv = dispatch_live.call_args.args[0]
        self.assertNotIn("--proof-completed-fallback-mode", forwarded_argv)
        self.assertNotIn("--proof-completed-fallback-topn-limit", forwarded_argv)
        self.assertNotIn("--proof-completed-fallback-slice-promotions", forwarded_argv)
        self.assertNotIn("--proof-future-fallback-mode", forwarded_argv)
        self.assertNotIn("--proof-future-fallback-topn-limit", forwarded_argv)
        self.assertNotIn("--proof-future-fallback-slice-promotions", forwarded_argv)

    def test_live_help_text_includes_completed_proof_fallback_flags(self) -> None:
        stream = StringIO()
        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(stream), redirect_stderr(stream):
                operator_main(["live", "--help"])

        self.assertEqual(raised.exception.code, 0)
        rendered_output = stream.getvalue()
        self.assertIn("--proof-future-fallback-mode", rendered_output)
        self.assertIn("--proof-future-fallback-topn-limit", rendered_output)
        self.assertIn("--proof-future-fallback-slice-promotions", rendered_output)
        self.assertIn("--proof-completed-fallback-mode", rendered_output)
        self.assertIn("--proof-completed-fallback-topn-limit", rendered_output)
        self.assertIn("--proof-completed-fallback-slice-promotions", rendered_output)
    @patch("runtime.promotions.run_promotions_operator._dispatch_inspect")
    def test_inspect_command_maps_mode_to_extraction_mode(self, dispatch_inspect) -> None:
        operator_main(
            [
                "inspect",
                "--run-id",
                "sql-inspection-run",
                "--artifact-root",
                "/tmp/promotions-operator-inspect",
                "--mode",
                "diagnostic_topn",
                "--selection-mode",
                "completed",
                "--run-row-count-probe",
                "--save-rendered-sql",
            ]
        )

        dispatch_inspect.assert_called_once()
        forwarded_argv = dispatch_inspect.call_args.args[0]
        self.assertIn("--extraction-mode", forwarded_argv)
        self.assertIn("diagnostic_topn", forwarded_argv)
        self.assertIn("--run-row-count-probe", forwarded_argv)
        self.assertIn("--save-rendered-sql", forwarded_argv)

    @patch("runtime.promotions.run_promotions_operational_cycle.main")
    def test_module_entrypoint_live_command_is_covered_via_runpy(self, live_main) -> None:
        stdout = StringIO()
        argv = [
            "runtime.promotions.run_promotions_operator",
            "live",
            "--run-id",
            "entrypoint-live-run",
            "--artifact-root",
            "/tmp/promotions-operator-live",
            "--query-timeout-seconds",
            "60",
            "--partition-strategy",
            "promotion_row_key_hash_bucket",
            "--partition-count",
            "16",
        ]

        original_argv = sys.argv[:]
        try:
            sys.argv = argv
            with redirect_stdout(stdout):
                runpy.run_module("runtime.promotions.run_promotions_operator", run_name="__main__")
        finally:
            sys.argv = original_argv

        live_main.assert_called_once()
        rendered_output = stdout.getvalue()
        self.assertIn("PROMOTIONS OPERATOR CLI", rendered_output)
        self.assertIn("run_id: entrypoint-live-run", rendered_output)

    @patch("runtime.promotions.run_promotions_operator._dispatch_live", side_effect=RuntimeError("boom"))
    def test_runtime_dispatch_failure_is_shaped_without_traceback(self, _dispatch_live) -> None:
        stream = StringIO()

        with self.assertRaises(SystemExit) as raised:
            operator_main(
                [
                    "live",
                    "--run-id",
                    "failed-live-run",
                    "--artifact-root",
                    "/tmp/promotions-operator-live",
                ],
                stream=stream,
            )

        self.assertEqual(raised.exception.code, 1)
        rendered_output = stream.getvalue()
        self.assertIn("FATAL OPERATOR CLI ERROR", rendered_output)
        self.assertIn("command_received:", rendered_output)
        self.assertIn(
            "-m runtime.promotions.run_promotions_operator live --run-id failed-live-run",
            rendered_output,
        )
        self.assertIn("cause_type: RuntimeError", rendered_output)

    @patch(
        "runtime.promotions.run_promotions_operator._dispatch_live",
        side_effect=PromotionRuntimeConfigError(
            "Missing required promotions SQL setting 'server'.",
            field_name="server",
            source="env:PROMOTIONS_MSSQL_SERVER",
            expected_from=("--server", "PROMOTIONS_MSSQL_SERVER", "PROMOTIONS_SQL_SERVER"),
            next_action="Set --server or define PROMOTIONS_MSSQL_SERVER and rerun.",
        ),
    )
    def test_config_failure_surfaces_expected_sources_and_next_action(self, _dispatch_live) -> None:
        stream = StringIO()

        with self.assertRaises(SystemExit) as raised:
            operator_main(
                [
                    "live",
                    "--run-id",
                    "failed-config-run",
                    "--artifact-root",
                    "/tmp/promotions-operator-live",
                ],
                stream=stream,
            )

        self.assertEqual(raised.exception.code, 1)
        rendered_output = stream.getvalue()
        self.assertIn("field: server", rendered_output)
        self.assertIn("source: env:PROMOTIONS_MSSQL_SERVER", rendered_output)
        self.assertIn(
            "expected_from: --server, PROMOTIONS_MSSQL_SERVER, PROMOTIONS_SQL_SERVER",
            rendered_output,
        )
        self.assertIn("next_action: Set --server or define PROMOTIONS_MSSQL_SERVER and rerun.", rendered_output)