from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.completed_transaction_aggregates_extractor import (  # noqa: E402
    render_completed_transaction_aggregates_query,
)
from data.promotions.completed_window_aggregates_extractor import (  # noqa: E402
    render_completed_window_aggregates_query,
)
from data.promotions.sql.promotion_base_query import (  # noqa: E402
    PromotionBaseQueryOptions,
    render_promotion_base_query,
)
from runtime.promotions.config import (  # noqa: E402
    PromotionArtifactPaths,
    PromotionCompletedExtractionRuntimeSettings,
    PromotionCompletedPartitionSettings,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
    PromotionRuntimeConfigError,
)


ENV_KEYS = (
    "PROMOTIONS_NAS_ROOT",
    "PROMOTIONS_MSSQL_SERVER",
    "PROMOTIONS_MSSQL_DATABASE",
    "PROMOTIONS_MSSQL_USERNAME",
    "PROMOTIONS_MSSQL_PASSWORD",
    "PROMOTIONS_MSSQL_DRIVER",
    "PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS",
    "PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS",
    "PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS",
    "PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS",
    "PROMOTIONS_MSSQL_ENCRYPT",
    "PROMOTIONS_MSSQL_TRUST_SERVER_CERTIFICATE",
    "PROMOTIONS_SQL_SERVER",
    "PROMOTIONS_SQL_DATABASE",
    "PROMOTIONS_SQL_USERNAME",
    "PROMOTIONS_SQL_PASSWORD",
    "PROMOTIONS_SQL_DRIVER",
    "PROMOTIONS_SQL_CONNECT_TIMEOUT_SECONDS",
    "PROMOTIONS_SQL_CONNECT_RETRY_ATTEMPTS",
    "PROMOTIONS_SQL_CONNECT_RETRY_BACKOFF_SECONDS",
    "PROMOTIONS_SQL_QUERY_TIMEOUT_SECONDS",
    "PROMOTIONS_SQL_ENCRYPT",
    "PROMOTIONS_SQL_TRUST_SERVER_CERTIFICATE",
    "PROMOTIONS_ADVICE_TABLE",
    "PROMOTIONS_PWLOGD_TABLE",
    "PROMOTIONS_SCHEMA",
    "PROMOTIONS_ARTIFACT_ROOT",
)


class PromotionEnvConfigTests(unittest.TestCase):
    def test_from_env_prefers_env_file_over_preexisting_shell_values(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["PROMOTIONS_MSSQL_USERNAME"] = "shell-user"
        os.environ["PROMOTIONS_MSSQL_PASSWORD"] = "bad-pass"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".promotions.env"
                env_path.write_text(
                    "\n".join(
                        (
                            "PROMOTIONS_MSSQL_SERVER=test-server",
                            "PROMOTIONS_MSSQL_DATABASE=test-database",
                            "PROMOTIONS_MSSQL_USERNAME=file-user",
                            "PROMOTIONS_MSSQL_PASSWORD=file-pass#",
                            "PROMOTIONS_MSSQL_DRIVER=Test Driver",
                            "PROMOTIONS_ADVICE_TABLE=promotions",
                        )
                    ),
                    encoding="utf-8",
                )
                settings = PromotionMssqlSettings.from_env(env_file=env_path)
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(settings.username, "file-user")
        self.assertEqual(settings.password, "file-pass#")

    def test_from_env_loads_expected_sql_settings(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".promotions.env"
            env_path.write_text(
                "\n".join(
                    (
                        "PROMOTIONS_MSSQL_SERVER=test-server",
                        "PROMOTIONS_MSSQL_DATABASE=test-database",
                        "PROMOTIONS_MSSQL_USERNAME=test-user",
                        "PROMOTIONS_MSSQL_PASSWORD=test-password",
                        "PROMOTIONS_MSSQL_DRIVER=Test Driver",
                        "PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS=15",
                        "PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS=2",
                        "PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS=1.5",
                        "PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS=45",
                        "PROMOTIONS_MSSQL_ENCRYPT=no",
                        "PROMOTIONS_MSSQL_TRUST_SERVER_CERTIFICATE=yes",
                        "PROMOTIONS_SCHEMA=analytics",
                        "PROMOTIONS_ADVICE_TABLE=PromotionAdvice",
                        "PROMOTIONS_PWLOGD_TABLE=PwlogD",
                        "PROMOTIONS_NAS_ROOT=artifacts/promotions-env",
                    )
                ),
                encoding="utf-8",
            )
            try:
                settings = PromotionMssqlSettings.from_env(env_file=env_path)
                artifact_paths = PromotionArtifactPaths.from_env(env_file=env_path)
            finally:
                for key, value in previous_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(settings.server, "test-server")
        self.assertEqual(settings.database, "test-database")
        self.assertEqual(settings.schema, "analytics")
        self.assertEqual(settings.promotion_advice_table, "analytics.PromotionAdvice")
        self.assertEqual(settings.pwlogd_table, "analytics.PwlogD")
        self.assertEqual(settings.username, "test-user")
        self.assertEqual(settings.password, "test-password")
        self.assertEqual(settings.odbc_driver, "Test Driver")
        self.assertEqual(settings.connect_timeout_seconds, 15)
        self.assertEqual(settings.connect_retry_attempts, 2)
        self.assertEqual(settings.connect_retry_backoff_seconds, 1.5)
        self.assertEqual(settings.query_timeout_seconds, 45)
        self.assertFalse(settings.encrypt)
        self.assertTrue(settings.trust_server_certificate)
        self.assertEqual(artifact_paths.root, REPO_ROOT / "artifacts" / "promotions-env")

    def test_from_env_uses_bounded_retry_defaults_when_omitted(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".promotions.env"
                env_path.write_text(
                    "\n".join(
                        (
                            "PROMOTIONS_MSSQL_SERVER=test-server",
                            "PROMOTIONS_MSSQL_DATABASE=test-database",
                            "PROMOTIONS_ADVICE_TABLE=promotions",
                        )
                    ),
                    encoding="utf-8",
                )
                settings = PromotionMssqlSettings.from_env(env_file=env_path)
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(settings.connect_retry_attempts, 2)
        self.assertEqual(settings.connect_retry_backoff_seconds, 5.0)
        summary = settings.safe_summary()
        self.assertEqual(summary.connect_retry_attempts_source, "default")
        self.assertEqual(summary.connect_retry_backoff_seconds_source, "default")

    def test_from_env_preserves_explicit_zero_retry_override(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".promotions.env"
                env_path.write_text(
                    "\n".join(
                        (
                            "PROMOTIONS_MSSQL_SERVER=test-server",
                            "PROMOTIONS_MSSQL_DATABASE=test-database",
                            "PROMOTIONS_ADVICE_TABLE=promotions",
                        )
                    ),
                    encoding="utf-8",
                )
                settings = PromotionMssqlSettings.from_env(
                    env_file=env_path,
                    connect_retry_attempts=0,
                    connect_retry_backoff_seconds=0.0,
                )
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(settings.connect_retry_attempts, 0)
        self.assertEqual(settings.connect_retry_backoff_seconds, 0.0)
        summary = settings.safe_summary()
        self.assertEqual(summary.connect_retry_attempts_source, "cli:--connect-retry-attempts")
        self.assertEqual(
            summary.connect_retry_backoff_seconds_source,
            "cli:--connect-retry-backoff-seconds",
        )

    def test_from_env_preserves_env_zero_retry_override(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".promotions.env"
                env_path.write_text(
                    "\n".join(
                        (
                            "PROMOTIONS_MSSQL_SERVER=test-server",
                            "PROMOTIONS_MSSQL_DATABASE=test-database",
                            "PROMOTIONS_ADVICE_TABLE=promotions",
                            "PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS=0",
                            "PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS=0.0",
                        )
                    ),
                    encoding="utf-8",
                )
                settings = PromotionMssqlSettings.from_env(env_file=env_path)
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(settings.connect_retry_attempts, 0)
        self.assertEqual(settings.connect_retry_backoff_seconds, 0.0)
        summary = settings.safe_summary()
        self.assertEqual(
            summary.connect_retry_attempts_source,
            "env:PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS",
        )
        self.assertEqual(
            summary.connect_retry_backoff_seconds_source,
            "env:PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS",
        )

    def test_safe_summary_redacts_password_and_tracks_setting_sources(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
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
                        "PROMOTIONS_MSSQL_ENCRYPT=no",
                        "PROMOTIONS_MSSQL_TRUST_SERVER_CERTIFICATE=yes",
                        "PROMOTIONS_ADVICE_TABLE=PromotionAdvice",
                    )
                ),
                encoding="utf-8",
            )
            try:
                settings = PromotionMssqlSettings.from_env(env_file=env_path)
            finally:
                for key, value in previous_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        summary = settings.safe_summary()
        rendered_summary = "\n".join(summary.render_lines())

        self.assertEqual(summary.config_source, f"explicit_env_file:{env_path}")
        self.assertEqual(summary.server_source, "env:PROMOTIONS_MSSQL_SERVER")
        self.assertEqual(summary.database_source, "env:PROMOTIONS_MSSQL_DATABASE")
        self.assertEqual(summary.user_source, "env:PROMOTIONS_MSSQL_USERNAME")
        self.assertTrue(summary.password_present)
        self.assertEqual(summary.password_source, "env:PROMOTIONS_MSSQL_PASSWORD")
        self.assertEqual(summary.connect_timeout_seconds_source, "env:PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS")
        self.assertEqual(summary.query_timeout_seconds_source, "env:PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS")
        self.assertEqual(summary.encrypt_source, "env:PROMOTIONS_MSSQL_ENCRYPT")
        self.assertEqual(
            summary.trust_server_certificate_source,
            "env:PROMOTIONS_MSSQL_TRUST_SERVER_CERTIFICATE",
        )
        self.assertNotIn("test-password", rendered_summary)
        self.assertIn("password_present: true", rendered_summary)

    def test_missing_required_setting_error_is_structured(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        try:
            with self.assertRaises(PromotionRuntimeConfigError) as raised:
                PromotionMssqlSettings.from_env(
                    database="test-database",
                    promotion_advice_table="dbo.PromotionAdvice",
                    env_file=Path("/tmp/does-not-exist.promotions.env"),
                )
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        error = raised.exception
        self.assertEqual(error.field_name, "server")
        self.assertIn("--server", error.expected_from)
        self.assertIn("PROMOTIONS_MSSQL_SERVER", error.expected_from)
        self.assertIn("PROMOTIONS_SQL_SERVER", error.expected_from)
        self.assertIn("Current config source", error.next_action)

    def test_from_env_rejects_non_positive_query_timeout(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".promotions.env"
                env_path.write_text(
                    "\n".join(
                        (
                            "PROMOTIONS_MSSQL_SERVER=test-server",
                            "PROMOTIONS_MSSQL_DATABASE=test-database",
                            "PROMOTIONS_ADVICE_TABLE=promotions",
                            "PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS=0",
                        )
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, ">= 1"):
                    PromotionMssqlSettings.from_env(env_file=env_path)
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_from_env_requires_server_database_and_advice_table(self) -> None:
        previous_values = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                env_path = Path(temp_dir) / ".promotions.env"
                env_path.write_text("", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "PROMOTIONS_ADVICE_TABLE"):
                    PromotionMssqlSettings.from_env(
                        env_file=env_path,
                        server="override-server",
                        database="override-database",
                    )
        finally:
            for key, value in previous_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_rendered_query_exposes_requested_realised_alias_fields(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
            )
        )

        rendered = render_promotion_base_query(
            settings=settings,
            selection_mode="completed",
        )

        expected_fields = (
            "actual_units_sold_promo",
            "actual_sales_ex_gst_promo",
            "actual_sales_inc_gst_promo",
            "actual_transaction_count_promo",
            "actual_days_with_sales_promo",
            "actual_avg_units_per_selling_day_promo",
            "actual_avg_sales_per_selling_day_promo",
            "actual_units_pre_56d",
            "actual_units_pre_28d",
            "actual_units_pre_7d",
            "actual_sales_ex_gst_pre_56d",
            "actual_sales_ex_gst_pre_28d",
            "actual_sales_ex_gst_pre_7d",
            "actual_units_post_14d",
            "actual_sales_ex_gst_post_14d",
            "actual_refund_units_promo",
            "actual_refund_sales_ex_gst_promo",
        )

        for field_name in expected_fields:
            self.assertIn(f" AS {field_name}", rendered.sql)
        self.assertEqual(rendered.query_version, "promotion_base_v4")
        self.assertIsNone(rendered.diagnostic_filter_summary["partition_strategy"])
        self.assertNotIn("partition_count", rendered.parameters)

    def test_completed_runtime_setting_defaults_and_serializes_history_start_date(self) -> None:
        settings = PromotionCompletedExtractionRuntimeSettings.from_env()

        self.assertEqual(
            settings.completed_sales_history_start_date.isoformat(),
            "2024-01-01",
        )
        self.assertEqual(
            settings.to_dict()["completed_sales_history_start_date"],
            "2024-01-01",
        )

    def test_completed_runtime_setting_accepts_iso_override(self) -> None:
        settings = PromotionCompletedExtractionRuntimeSettings.from_env(
            completed_sales_history_start_date="2024-02-15",
        )

        self.assertEqual(
            settings.completed_sales_history_start_date.isoformat(),
            "2024-02-15",
        )

    def test_completed_runtime_setting_rejects_invalid_iso_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            PromotionCompletedExtractionRuntimeSettings.from_env(
                completed_sales_history_start_date="15/02/2024",
            )

    def test_rendered_completed_query_applies_governed_sales_history_lower_bound_only_for_completed(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
            )
        )

        completed_rendered = render_promotion_base_query(
            settings=settings,
            selection_mode="completed",
        )
        future_rendered = render_promotion_base_query(
            settings=settings,
            selection_mode="future",
        )

        self.assertEqual(
            completed_rendered.parameters["completed_sales_history_start_date"],
            "2024-01-01",
        )
        self.assertIn(
            "CAST(pw.Calendar_Date AS date) >= CAST(:completed_sales_history_start_date AS date)",
            completed_rendered.sql,
        )
        self.assertNotIn("completed_sales_history_start_date", future_rendered.parameters)
        self.assertNotIn(
            "CAST(pw.Calendar_Date AS date) >= CAST(:completed_sales_history_start_date AS date)",
            future_rendered.sql,
        )

    def test_staged_completed_aggregate_queries_use_openjson_scope_and_lower_bound(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
            )
        )
        base_scope = pd.DataFrame(
            {
                "promotion_row_key": ["promo-1"],
                "store_number_key": [101],
                "sku_number_key": [202],
                "promotion_start_date_date": ["2024-08-01"],
                "promotional_end_date_date": ["2024-08-07"],
                "promotional_sku_id_key": ["sku-1"],
            }
        )

        for stage_name, rendered in (
            (
                "window",
                render_completed_window_aggregates_query(
                    settings=settings,
                    base_frame=base_scope,
                ),
            ),
            (
                "transaction",
                render_completed_transaction_aggregates_query(
                    settings=settings,
                    base_frame=base_scope,
                ),
            ),
        ):
            with self.subTest(stage_name=stage_name):
                self.assertIn("OPENJSON", rendered.sql)
                self.assertIn("completed_base_scope_rows_json", rendered.parameters)
                self.assertEqual(
                    rendered.parameters["completed_sales_history_start_date"],
                    "2024-01-01",
                )
                self.assertIn(
                    "CAST(:completed_sales_history_start_date AS date)",
                    rendered.sql,
                )

    def test_window_aggregates_query_handles_non_numeric_scope_identifiers_with_try_cast_filters(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
            )
        )
        base_scope = pd.DataFrame(
            {
                "promotion_row_key": ["promo-valid", "promo-bad-store", "promo-bad-sku"],
                "store_number_key": ["101", "not-a-number", "102"],
                "sku_number_key": ["202", "203", "bad-sku"],
                "promotion_start_date_date": ["2024-08-01", "2024-08-01", "2024-08-01"],
                "promotional_end_date_date": ["2024-08-07", "2024-08-07", "2024-08-07"],
                "promotional_sku_id_key": ["sku-1", "sku-2", "sku-3"],
            }
        )

        rendered = render_completed_window_aggregates_query(
            settings=settings,
            base_frame=base_scope,
        )

        self.assertIn(
            "store_number_key_raw nvarchar(128) '$.store_number_key'",
            rendered.sql,
        )
        self.assertIn(
            "sku_number_key_raw nvarchar(128) '$.sku_number_key'",
            rendered.sql,
        )
        self.assertIn(
            "TRY_CAST(scope_raw.store_number_key_raw AS bigint) AS store_number_key",
            rendered.sql,
        )
        self.assertIn(
            "TRY_CAST(scope_raw.sku_number_key_raw AS bigint) AS sku_number_key",
            rendered.sql,
        )
        self.assertIn(
            "WHERE TRY_CAST(scope_raw.store_number_key_raw AS bigint) IS NOT NULL",
            rendered.sql,
        )
        self.assertIn(
            "AND TRY_CAST(scope_raw.sku_number_key_raw AS bigint) IS NOT NULL",
            rendered.sql,
        )
        self.assertIn(
            "WHERE TRY_CAST(pw.Store_Number AS bigint) IS NOT NULL",
            rendered.sql,
        )
        self.assertIn(
            "AND TRY_CAST(pw.SKU_Number AS bigint) IS NOT NULL",
            rendered.sql,
        )
        self.assertIn(
            "ON pw.store_number_key = candidate_scope.store_number_key",
            rendered.sql,
        )
        self.assertIn(
            "AND pw.sku_number_key = candidate_scope.sku_number_key",
            rendered.sql,
        )

    def test_transaction_aggregates_query_handles_non_numeric_scope_identifiers_with_try_cast_filters(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
            )
        )
        base_scope = pd.DataFrame(
            {
                "promotion_row_key": ["promo-valid", "promo-bad-store", "promo-bad-sku"],
                "store_number_key": ["101", "not-a-number", "102"],
                "sku_number_key": ["202", "203", "bad-sku"],
                "promotion_start_date_date": ["2024-08-01", "2024-08-01", "2024-08-01"],
                "promotional_end_date_date": ["2024-08-07", "2024-08-07", "2024-08-07"],
                "promotional_sku_id_key": ["sku-1", "sku-2", "sku-3"],
            }
        )

        rendered = render_completed_transaction_aggregates_query(
            settings=settings,
            base_frame=base_scope,
        )

        self.assertNotIn(
            "store_number_key bigint '$.store_number_key'",
            rendered.sql,
        )
        self.assertNotIn(
            "sku_number_key bigint '$.sku_number_key'",
            rendered.sql,
        )
        self.assertIn(
            "store_number_key_raw nvarchar(128) '$.store_number_key'",
            rendered.sql,
        )
        self.assertIn(
            "sku_number_key_raw nvarchar(128) '$.sku_number_key'",
            rendered.sql,
        )
        self.assertIn(
            "TRY_CAST(scope_raw.store_number_key_raw AS bigint) AS store_number_key",
            rendered.sql,
        )
        self.assertIn(
            "TRY_CAST(scope_raw.sku_number_key_raw AS bigint) AS sku_number_key",
            rendered.sql,
        )
        self.assertIn(
            "WHERE TRY_CAST(scope_raw.store_number_key_raw AS bigint) IS NOT NULL",
            rendered.sql,
        )
        self.assertIn(
            "AND TRY_CAST(scope_raw.sku_number_key_raw AS bigint) IS NOT NULL",
            rendered.sql,
        )
        self.assertIn(
            "WHERE TRY_CAST(pw.Store_Number AS bigint) IS NOT NULL",
            rendered.sql,
        )
        self.assertIn(
            "AND TRY_CAST(pw.SKU_Number AS bigint) IS NOT NULL",
            rendered.sql,
        )
        self.assertIn(
            "ON pw.store_number_key = candidate_scope.store_number_key",
            rendered.sql,
        )
        self.assertIn(
            "AND pw.sku_number_key = candidate_scope.sku_number_key",
            rendered.sql,
        )

    def test_rendered_completed_query_supports_diagnostic_narrowing_and_keeps_windows(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
            )
        )

        rendered = render_promotion_base_query(
            settings=settings,
            selection_mode="completed",
            query_options=PromotionBaseQueryOptions(
                extraction_mode="diagnostic_topn",
                limit_promotions=25,
                promotion_name_like="Mega Sale",
                store_number=10,
                supplier_number=20,
            ),
        )

        self.assertEqual(rendered.parameters["limit_promotions"], 25)
        self.assertEqual(rendered.parameters["promotion_name_like"], "%Mega Sale%")
        self.assertEqual(rendered.parameters["diagnostic_store_number"], 10)
        self.assertEqual(rendered.parameters["diagnostic_supplier_number"], 20)
        self.assertIn("candidate_store_sku_windows", rendered.sql)
        self.assertIn("TOP (CAST(:limit_promotions AS int))", rendered.sql)
        self.assertIn("TRY_CAST(ar.store_number AS bigint) = CAST(:diagnostic_store_number AS bigint)", rendered.sql)
        self.assertIn("TRY_CAST(ar.supplier_number AS bigint) = CAST(:diagnostic_supplier_number AS bigint)", rendered.sql)
        self.assertIn("CAST(:baseline_lookback_days AS int)", rendered.sql)
        self.assertIn("CAST(:post_promo_days AS int)", rendered.sql)
        self.assertNotIn("CROSS JOIN advice_bounds", rendered.sql)
        self.assertIn("candidate_promotion_row_count", rendered.candidate_count_sql)

    def test_rendered_completed_query_supports_date_diverse_proof_slice(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
            )
        )

        rendered = render_promotion_base_query(
            settings=settings,
            selection_mode="completed",
            query_options=PromotionBaseQueryOptions(
                extraction_mode="diagnostic_topn",
                limit_promotions=25,
                completed_proof_slice_date_count=3,
            ),
        )

        self.assertEqual(rendered.parameters["limit_promotions"], 25)
        self.assertEqual(rendered.parameters["completed_proof_slice_date_count"], 3)
        self.assertEqual(
            rendered.diagnostic_filter_summary["completed_proof_slice_date_count"],
            3,
        )
        self.assertIn("AS advice_date_rank", rendered.sql)
        self.assertIn("AS advice_date_row_number", rendered.sql)
        self.assertIn("PARTITION BY CAST(ar.promotion_start_date AS date)", rendered.sql)
        self.assertIn(
            "ar.advice_date_rank <= CAST(:completed_proof_slice_date_count AS int)",
            rendered.sql,
        )
        self.assertIn(
            "ar.advice_date_row_number <= CAST(:limit_promotions AS int)",
            rendered.sql,
        )
        self.assertNotIn("TOP (CAST(:limit_promotions AS int))", rendered.sql)
        self.assertIn("AS advice_date_rank", rendered.candidate_count_sql)
        self.assertIn("AS advice_date_rank", rendered.preflight_sql)

    def test_rendered_completed_query_supports_partition_filters_for_all_strategies(self) -> None:
        settings = PromotionPipelineSettings.for_runtime_date(
            sql=PromotionMssqlSettings(
                server="test-server",
                database="test-database",
                schema="dbo",
                promotion_advice_table="dbo.PromotionAdvice",
                pwlogd_table="dbo.PwlogD",
            )
        )

        expectations = {
            "store_number": "CHECKSUM(COALESCE(CAST(ar.store_number AS nvarchar(64)), N''))",
            "supplier_number": "CHECKSUM(COALESCE(CAST(ar.supplier_number AS nvarchar(64)), N''))",
            "store_sku_hash_bucket": "COALESCE(CAST(ar.sku_number AS nvarchar(64)), N'')",
            "promotion_name_hash_bucket": "CHECKSUM(COALESCE(CAST(ar.promotion_name AS nvarchar(255)), N''))",
            "promotion_row_key_hash_bucket": "COALESCE(CAST(ar.promotional_sku_id AS nvarchar(128)), N'')",
        }

        for strategy, expected_fragment in expectations.items():
            with self.subTest(strategy=strategy):
                rendered = render_promotion_base_query(
                    settings=settings,
                    selection_mode="completed",
                    query_options=PromotionBaseQueryOptions(
                        completed_partition=PromotionCompletedPartitionSettings(
                            strategy=strategy,
                            partition_count=8,
                            partition_index=3,
                        )
                    ),
                )

                self.assertEqual(rendered.parameters["partition_strategy"], strategy)
                self.assertEqual(rendered.parameters["partition_count"], 8)
                self.assertEqual(rendered.parameters["partition_index"], 3)
                self.assertEqual(rendered.parameters["partition_bucket_index"], 2)
                self.assertIn(expected_fragment, rendered.sql)
                self.assertIn(expected_fragment, rendered.candidate_count_sql)