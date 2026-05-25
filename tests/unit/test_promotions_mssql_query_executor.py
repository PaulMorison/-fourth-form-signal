from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from sqlalchemy.exc import InterfaceError, OperationalError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.mssql_query_executor import (  # noqa: E402
    PromotionMssqlConnectionTimeoutError,
    PromotionMssqlFetchStreamError,
    PromotionMssqlQueryTimeoutError,
    SqlAlchemyMssqlQueryExecutor,
)


class _FakeRawConnection:
    def __init__(self) -> None:
        self.timeout: int | None = None


class _FakeConnection:
    def __init__(
        self,
        *,
        execute_error: Exception | None = None,
        execute_result=None,
    ) -> None:
        self.execute_error = execute_error
        self.execute_result = execute_result
        self.closed = False
        self.connection = _FakeRawConnection()

    def execute(self, *_args, **_kwargs):
        if self.execute_error is not None:
            raise self.execute_error
        if self.execute_result is not None:
            return self.execute_result
        raise AssertionError("This fake connection only supports configured test paths.")

    def close(self) -> None:
        self.closed = True


class _FakeChunkedResult:
    def __init__(
        self,
        *,
        columns: tuple[str, ...],
        batches: list[list[tuple[object, ...]]],
        fetchmany_error: Exception | None = None,
        fail_on_call: int | None = None,
    ) -> None:
        self._columns = columns
        self._batches = list(batches)
        self._fetchmany_error = fetchmany_error
        self._fail_on_call = fail_on_call
        self._call_count = 0

    def keys(self):
        return self._columns

    def fetchall(self):
        rows: list[tuple[object, ...]] = []
        for batch in self._batches:
            rows.extend(batch)
        return rows

    def fetchmany(self, _size: int):
        self._call_count += 1
        if self._fail_on_call is not None and self._call_count == self._fail_on_call:
            if self._fetchmany_error is None:
                raise AssertionError("fetchmany_error must be provided when fail_on_call is set")
            raise self._fetchmany_error
        if not self._batches:
            return []
        return self._batches.pop(0)

    def close(self) -> None:
        return None


class _FailingConnectEngine:
    def __init__(self, error_factory) -> None:
        self._error_factory = error_factory
        self.connect_calls = 0
        self.disposed = False

    def connect(self):
        self.connect_calls += 1
        raise self._error_factory()

    def dispose(self) -> None:
        self.disposed = True


class _StaticConnectionEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection
        self.connect_calls = 0
        self.disposed = False

    def connect(self):
        self.connect_calls += 1
        return self._connection

    def dispose(self) -> None:
        self.disposed = True


class PromotionMssqlQueryExecutorTests(unittest.TestCase):
    def test_connect_login_timeout_uses_connection_failure_path_and_retries(self) -> None:
        executor = SqlAlchemyMssqlQueryExecutor(
            connection_url="mssql+pyodbc:///?odbc_connect=test",
            connect_timeout_seconds=15,
            connect_retry_attempts=2,
            connect_retry_backoff_seconds=0.25,
            query_timeout_seconds=60,
        )
        engine = _FailingConnectEngine(
            lambda: InterfaceError("", {}, Exception("Login timeout expired"))
        )

        with patch("sqlalchemy.create_engine", return_value=engine), patch(
            "data.promotions.mssql_query_executor.time.sleep"
        ) as sleep_mock:
            with self.assertRaises(PromotionMssqlConnectionTimeoutError) as raised:
                executor.fetch_dataframe(sql="SELECT 1", parameters={})

        error = raised.exception
        self.assertEqual(engine.connect_calls, 3)
        self.assertEqual(sleep_mock.call_count, 2)
        self.assertTrue(engine.disposed)
        self.assertEqual(getattr(error, "current_sql_subphase"), "SQL connecting")
        self.assertEqual(getattr(error, "connect_timeout_seconds"), 15)
        self.assertEqual(getattr(error, "connect_retry_attempts"), 2)
        self.assertEqual(getattr(error, "connect_retry_backoff_seconds"), 0.25)
        self.assertEqual(getattr(error, "connect_attempt_count"), 3)
        self.assertEqual(getattr(error, "query_timeout_seconds"), 60)
        self.assertIn("connect/login timed out", str(error))

    def test_query_timeout_after_connection_stays_in_query_failure_path(self) -> None:
        executor = SqlAlchemyMssqlQueryExecutor(
            connection_url="mssql+pyodbc:///?odbc_connect=test",
            connect_timeout_seconds=15,
            connect_retry_attempts=3,
            connect_retry_backoff_seconds=1.0,
            query_timeout_seconds=60,
        )
        connection = _FakeConnection(
            execute_error=OperationalError("", {}, Exception("Query timeout expired"))
        )
        engine = _StaticConnectionEngine(connection)

        with patch("sqlalchemy.create_engine", return_value=engine), patch(
            "data.promotions.mssql_query_executor.time.sleep"
        ) as sleep_mock:
            with self.assertRaises(PromotionMssqlQueryTimeoutError) as raised:
                executor.fetch_dataframe(sql="SELECT 1", parameters={})

        error = raised.exception
        self.assertEqual(engine.connect_calls, 1)
        sleep_mock.assert_not_called()
        self.assertTrue(engine.disposed)
        self.assertTrue(connection.closed)
        self.assertEqual(connection.connection.timeout, 60)
        self.assertEqual(getattr(error, "current_sql_subphase"), "SQL executing")
        self.assertEqual(getattr(error, "connect_attempt_count"), 1)
        self.assertEqual(getattr(error, "query_timeout_seconds"), 60)
        self.assertIn("query timed out", str(error).lower())

    def test_chunked_fetch_reports_multiple_chunks_and_aggregate_telemetry(self) -> None:
        executor = SqlAlchemyMssqlQueryExecutor(
            connection_url="mssql+pyodbc:///?odbc_connect=test",
            connect_timeout_seconds=15,
            connect_retry_attempts=0,
            connect_retry_backoff_seconds=0.0,
            query_timeout_seconds=60,
        )
        result = _FakeChunkedResult(
            columns=("promotion_id", "promotion_name"),
            batches=[
                [(1, "one"), (2, "two")],
                [(3, "three")],
                [],
            ],
        )
        connection = _FakeConnection(execute_result=result)
        engine = _StaticConnectionEngine(connection)
        consumed_chunks: list[tuple[list[object], int]] = []

        with patch("sqlalchemy.create_engine", return_value=engine):
            execution_result = executor.fetch_dataframe_in_chunks(
                sql="SELECT promotion_id, promotion_name FROM dbo.PromotionAdvice",
                parameters={},
                chunk_row_count=2,
                chunk_consumer=lambda frame, progress: consumed_chunks.append(
                    (frame["promotion_id"].tolist(), progress.chunk_index)
                ),
            )

        self.assertEqual(consumed_chunks, [([1, 2], 1), ([3], 2)])
        self.assertEqual(execution_result.columns, ("promotion_id", "promotion_name"))
        self.assertEqual(execution_result.telemetry.fetch_mode, "chunked_fetch")
        self.assertEqual(execution_result.telemetry.fetch_chunk_row_count, 2)
        self.assertEqual(execution_result.telemetry.chunk_count, 2)
        self.assertEqual(execution_result.telemetry.completed_chunk_count, 2)
        self.assertEqual(execution_result.telemetry.cumulative_fetched_row_count, 3)
        self.assertTrue(connection.closed)
        self.assertTrue(engine.disposed)

    def test_chunked_fetch_stream_error_is_classified_after_query_executes(self) -> None:
        executor = SqlAlchemyMssqlQueryExecutor(
            connection_url="mssql+pyodbc:///?odbc_connect=test",
            connect_timeout_seconds=15,
            connect_retry_attempts=0,
            connect_retry_backoff_seconds=0.0,
            query_timeout_seconds=60,
        )
        result = _FakeChunkedResult(
            columns=("promotion_id",),
            batches=[[(1,)]],
            fetchmany_error=OperationalError("", {}, Exception("Communication link failure")),
            fail_on_call=2,
        )
        connection = _FakeConnection(execute_result=result)
        engine = _StaticConnectionEngine(connection)

        with patch("sqlalchemy.create_engine", return_value=engine):
            with self.assertRaises(PromotionMssqlFetchStreamError) as raised:
                executor.fetch_dataframe_in_chunks(
                    sql="SELECT promotion_id FROM dbo.PromotionAdvice",
                    parameters={},
                    chunk_row_count=1,
                    chunk_consumer=lambda *_args: None,
                )

        error = raised.exception
        self.assertEqual(getattr(error, "current_sql_subphase"), "SQL fetch in progress")
        self.assertEqual(getattr(error, "query_timeout_seconds"), 60)
        self.assertTrue(connection.closed)
        self.assertTrue(engine.disposed)