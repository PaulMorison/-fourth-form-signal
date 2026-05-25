from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.completed_stage_executor import (  # noqa: E402
    PromotionCompletedRenderedStageQuery,
    PromotionCompletedSourceIdentityError,
    execute_completed_sql_stage,
)
from data.promotions.mssql_query_executor import (  # noqa: E402
    PromotionChunkedQueryExecutionResult,
    PromotionQueryExecutionResult,
    PromotionSqlChunkFetchProgress,
    PromotionSqlExecutionTelemetry,
)
from runtime.promotions.config import (  # noqa: E402
    PromotionArtifactPaths,
    PromotionCompletedExtractionRuntimeSettings,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)


class _FullFetchExecutor:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def fetch_dataframe(self, *, sql, parameters, phase_callback=None):
        return PromotionQueryExecutionResult(
            frame=self._frame,
            telemetry=PromotionSqlExecutionTelemetry(
                query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                query_execution_completed_at_utc="2024-09-01T00:00:03+00:00",
                fetch_started_at_utc="2024-09-01T00:00:03+00:00",
                fetch_completed_at_utc="2024-09-01T00:00:04+00:00",
                current_sql_subphase="SQL fetch in progress",
            ),
        )


class _ChunkedFetchExecutor:
    def __init__(self, chunks: tuple[pd.DataFrame, ...]) -> None:
        self._chunks = chunks

    def fetch_dataframe_in_chunks(
        self,
        *,
        sql,
        parameters,
        chunk_row_count,
        chunk_consumer,
        phase_callback=None,
    ):
        columns: tuple[str, ...] = ()
        cumulative_row_count = 0
        for chunk_index, chunk in enumerate(self._chunks, start=1):
            columns = tuple(str(column) for column in chunk.columns)
            cumulative_row_count += len(chunk.index)
            chunk_consumer(
                chunk,
                PromotionSqlChunkFetchProgress(
                    chunk_index=chunk_index,
                    chunk_row_count=len(chunk.index),
                    cumulative_row_count=cumulative_row_count,
                    chunk_fetch_seconds=0.01,
                    cumulative_elapsed_seconds=0.01 * chunk_index,
                ),
            )
        return PromotionChunkedQueryExecutionResult(
            columns=columns,
            telemetry=PromotionSqlExecutionTelemetry(
                query_execution_started_at_utc="2024-09-01T00:00:02+00:00",
                query_execution_completed_at_utc="2024-09-01T00:00:03+00:00",
                fetch_started_at_utc="2024-09-01T00:00:03+00:00",
                fetch_completed_at_utc="2024-09-01T00:00:04+00:00",
                current_sql_subphase="SQL fetch in progress",
                chunk_count=len(self._chunks),
                completed_chunk_count=len(self._chunks),
                cumulative_rows_written=cumulative_row_count,
            ),
        )


class PromotionCompletedStageExecutorTests(unittest.TestCase):
    def test_completed_base_full_fetch_rejects_bad_source_sku_before_parquet_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _build_settings(temp_dir, enable_chunked_fetch=False)
            bad_frame = pd.DataFrame(
                {
                    "advice_batch_row_number": [17],
                    "source_file": ["03082024_xmas_seasonal_2024_additional_stock_s.csv"],
                    "promotion_name": ["Xmas Seasonal 2024 Additional Stock"],
                    "promotion_row_key": [
                        "772|TUESDAY, 24 SEPTEMBER 2024 4:03 PM|2024-09-01|2024-09-07"
                    ],
                    "store_number": [772],
                    "sku_number": ["TUESDAY, 24 SEPTEMBER 2024 4:03 PM"],
                    "sku_number_key": [None],
                }
            )

            with self.assertRaises(PromotionCompletedSourceIdentityError) as raised:
                execute_completed_sql_stage(
                    settings=settings,
                    run_id="bad-source-sku-full-fetch",
                    stage_name="completed_base",
                    executor=_FullFetchExecutor(bad_frame),
                    rendered_query=_rendered_query(),
                )

            message = str(raised.exception)
            self.assertIn("advice_source_table=dbo.PromotionAdvice", message)
            self.assertIn("fetch_context=full_fetch", message)
            self.assertIn("invalid_rows=1", message)
            self.assertIn("TUESDAY, 24 SEPTEMBER 2024 4:03 PM", message)
            self.assertIn("source_file", message)
            self.assertIn("rows were not repaired, filtered, or finalized", message)
            self.assertFalse(settings.artifacts.extracted_base_path("bad-source-sku-full-fetch").exists())

            diagnostics_path = Path(
                getattr(raised.exception, "sql_diagnostics_summary_json_path")
            )
            diagnostics_payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(diagnostics_payload["extraction_status"], "failed")
            self.assertIn("source SKU identity", diagnostics_payload["failure_message"])

    def test_completed_base_chunked_fetch_rejects_bad_source_sku_before_chunk_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _build_settings(temp_dir, enable_chunked_fetch=True)
            bad_chunk = pd.DataFrame(
                {
                    "promotion_row_key": ["772|MONDAY, 23 SEPTEMBER 2024 3:49 PM"],
                    "source_file": ["03062024_allocation_report_op1_10_tuesday.csv"],
                    "sku_number": ["MONDAY, 23 SEPTEMBER 2024 3:49 PM"],
                    "sku_number_key": [None],
                }
            )

            with self.assertRaises(PromotionCompletedSourceIdentityError) as raised:
                execute_completed_sql_stage(
                    settings=settings,
                    run_id="bad-source-sku-chunked-fetch",
                    stage_name="completed_base",
                    executor=_ChunkedFetchExecutor((bad_chunk,)),
                    rendered_query=_rendered_query(),
                )

            self.assertIn("fetch_context=chunk_index=1", str(raised.exception))
            self.assertFalse(settings.artifacts.extracted_base_path("bad-source-sku-chunked-fetch").exists())

    def test_completed_base_accepts_valid_source_sku_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _build_settings(temp_dir, enable_chunked_fetch=False)
            valid_frame = pd.DataFrame(
                {
                    "promotion_row_key": ["772|186513|2024-09-01|2024-09-07"],
                    "store_number": [772],
                    "sku_number": ["186513"],
                    "sku_number_key": [186513],
                }
            )

            result = execute_completed_sql_stage(
                settings=settings,
                run_id="valid-source-sku-full-fetch",
                stage_name="completed_base",
                executor=_FullFetchExecutor(valid_frame),
                rendered_query=_rendered_query(),
            )

            self.assertEqual(result.row_count, 1)
            self.assertTrue(Path(result.base_path).exists())
            persisted = pd.read_parquet(result.base_path)
            self.assertEqual(persisted.loc[0, "sku_number_key"], 186513)


def _build_settings(temp_dir: str, *, enable_chunked_fetch: bool) -> PromotionPipelineSettings:
    return PromotionPipelineSettings.for_runtime_date(
        sql=PromotionMssqlSettings(
            server="test-server",
            database="test-database",
            schema="dbo",
            promotion_advice_table="dbo.PromotionAdvice",
            pwlogd_table="dbo.PwlogD",
        ),
        runtime_date=date(2024, 9, 1),
        artifacts=PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts"),
        completed_extraction_runtime=PromotionCompletedExtractionRuntimeSettings(
            enable_chunked_fetch=enable_chunked_fetch,
            chunk_row_count=500,
        ),
    )


def _rendered_query() -> PromotionCompletedRenderedStageQuery:
    return PromotionCompletedRenderedStageQuery(
        sql="SELECT 1",
        parameters={},
        query_version="promotion_completed_base_v1",
        stage_name="completed_base",
        diagnostic_filter_summary={},
        estimated_window_summary={},
    )


if __name__ == "__main__":
    unittest.main()