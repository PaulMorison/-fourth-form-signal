from __future__ import annotations

"""MSSQL execution seam for promotions extraction.

Canon ownership:
- Encapsulates how the promotions extractor turns a rendered SQL query into a
  pandas DataFrame.
- Keeps credential-bearing connection construction at the runtime boundary and
  uses parameterized SQL execution instead of string interpolation.
- Does not own query rendering, extraction manifests, feature generation, or
  any downstream dataset semantics.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import time
from typing import Any, Mapping, Protocol
from urllib.parse import quote_plus

import pandas as pd

from runtime.promotions.config import (
    DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS,
    DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS,
    PromotionMssqlSettings,
)


PromotionSqlSubphaseCallback = Callable[[str], None]
PromotionSqlChunkConsumer = Callable[[pd.DataFrame, "PromotionSqlChunkFetchProgress"], None]


@dataclass(frozen=True)
class PromotionSqlExecutionTelemetry:
    sql_connection_started_at_utc: str | None = None
    sql_connection_completed_at_utc: str | None = None
    query_execution_started_at_utc: str | None = None
    query_execution_completed_at_utc: str | None = None
    fetch_started_at_utc: str | None = None
    fetch_completed_at_utc: str | None = None
    current_sql_subphase: str | None = None
    connect_timeout_seconds: int | None = None
    connect_retry_attempts: int = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS
    connect_retry_backoff_seconds: float = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS
    connect_attempt_count: int | None = None
    query_timeout_seconds: int | None = None
    query_timeout_applied: bool | None = None
    fetch_mode: str = "full_fetch"
    fetch_chunk_row_count: int | None = None
    chunk_count: int = 0
    completed_chunk_count: int = 0
    cumulative_fetched_row_count: int = 0
    failure_stage: str | None = None
    failure_exception_type: str | None = None
    failure_message: str | None = None
    # Per-attempt connect telemetry. Each entry is a small dict with keys:
    # attempt_number, total_allowed_attempts, connect_timeout_seconds_applied,
    # retry_backoff_seconds_applied, classification, error_excerpt,
    # elapsed_seconds, started_at_utc, completed_at_utc, outcome
    # ("success" | "failure_retryable" | "failure_terminal").
    connect_attempts: tuple[dict, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["phase_elapsed_seconds"] = {
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
        }
        return payload


@dataclass(frozen=True)
class PromotionQueryExecutionResult:
    frame: pd.DataFrame
    telemetry: PromotionSqlExecutionTelemetry


@dataclass(frozen=True)
class PromotionSqlChunkFetchProgress:
    chunk_index: int
    chunk_row_count: int
    cumulative_row_count: int
    chunk_fetch_seconds: float
    cumulative_elapsed_seconds: float


@dataclass(frozen=True)
class PromotionChunkedQueryExecutionResult:
    columns: tuple[str, ...]
    telemetry: PromotionSqlExecutionTelemetry


@dataclass(frozen=True)
class PromotionSqlConnectionCheckResult:
    connected_at_utc: str
    elapsed_seconds: float
    connect_timeout_seconds: int | None = None
    connect_retry_attempts: int = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS
    connect_retry_backoff_seconds: float = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS
    connect_attempt_count: int = 1
    query_timeout_seconds: int | None = None
    query_timeout_applied: bool = False


class PromotionQueryExecutor(Protocol):
    def fetch_dataframe(
        self,
        *,
        sql: str,
        parameters: Mapping[str, object],
        phase_callback: PromotionSqlSubphaseCallback | None = None,
    ) -> PromotionQueryExecutionResult:
        """Execute a rendered SQL statement and return the frame plus SQL telemetry."""

    def fetch_dataframe_in_chunks(
        self,
        *,
        sql: str,
        parameters: Mapping[str, object],
        chunk_row_count: int,
        chunk_consumer: PromotionSqlChunkConsumer,
        phase_callback: PromotionSqlSubphaseCallback | None = None,
    ) -> PromotionChunkedQueryExecutionResult:
        """Execute a rendered SQL statement and hand off bounded chunks to the consumer."""


class PromotionMssqlConnectionError(RuntimeError):
    """Raised when the promotions runtime cannot connect to MSSQL."""


class PromotionMssqlConnectionTimeoutError(PromotionMssqlConnectionError):
    """Raised when MSSQL connect/login times out before SQL execution starts."""


class PromotionMssqlConnectivityError(PromotionMssqlConnectionError):
    """Raised when MSSQL connect fails due to transient network/transport issues."""


class PromotionMssqlAuthenticationError(PromotionMssqlConnectionError):
    """Raised when MSSQL rejects the supplied credentials (NOT retried)."""


class PromotionMssqlConfigurationError(PromotionMssqlConnectionError):
    """Raised when the MSSQL driver/DSN/server config is invalid (NOT retried)."""


class PromotionMssqlQueryError(RuntimeError):
    """Raised when the promotions runtime can connect but query execution fails."""


class PromotionMssqlQueryTimeoutError(PromotionMssqlQueryError):
    """Raised when the live promotions SQL execution exceeds the configured timeout."""


class PromotionMssqlFetchStreamError(PromotionMssqlQueryError):
    """Raised when MSSQL result transfer fails during row fetch after execution succeeds."""


@dataclass(frozen=True)
class SqlAlchemyMssqlQueryExecutor:
    """SQLAlchemy-backed executor for governed promotions extraction queries."""

    connection_url: str
    connect_timeout_seconds: int | None = None
    connect_retry_attempts: int = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS
    connect_retry_backoff_seconds: float = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS
    query_timeout_seconds: int | None = None

    @classmethod
    def from_settings(cls, settings: PromotionMssqlSettings) -> "SqlAlchemyMssqlQueryExecutor":
        return cls(
            connection_url=_build_mssql_connection_url(settings),
            connect_timeout_seconds=settings.connect_timeout_seconds,
            connect_retry_attempts=settings.connect_retry_attempts,
            connect_retry_backoff_seconds=settings.connect_retry_backoff_seconds,
            query_timeout_seconds=settings.query_timeout_seconds,
        )

    def fetch_dataframe(
        self,
        *,
        sql: str,
        parameters: Mapping[str, object],
        phase_callback: PromotionSqlSubphaseCallback | None = None,
    ) -> PromotionQueryExecutionResult:
        """Run the query through SQLAlchemy so values stay bound and auditable."""

        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError, SQLAlchemyError
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "SQLAlchemy is required for promotions MSSQL extraction."
            ) from error

        engine = None
        connection = None
        try:
            engine = create_engine(self.connection_url, future=True)
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "The configured MSSQL connection requires a DBAPI driver such as pyodbc."
            ) from error
        telemetry = PromotionSqlExecutionTelemetry(
            connect_timeout_seconds=self.connect_timeout_seconds,
            connect_retry_attempts=self.connect_retry_attempts,
            connect_retry_backoff_seconds=self.connect_retry_backoff_seconds,
            query_timeout_seconds=self.query_timeout_seconds,
        )
        try:
            connection, telemetry = self._open_connection(
                engine=engine,
                telemetry=telemetry,
                phase_callback=phase_callback,
                operational_error_type=OperationalError,
                interface_error_type=InterfaceError,
            )
            telemetry = _replace_telemetry(
                telemetry,
                query_timeout_applied=_apply_query_timeout(
                    connection,
                    self.query_timeout_seconds,
                ),
            )
            _notify_phase(phase_callback, "SQL executing")
            telemetry = _replace_telemetry(
                telemetry,
                current_sql_subphase="SQL executing",
                query_execution_started_at_utc=_utc_now_iso(),
            )
            result = connection.execute(text(sql), dict(parameters))
            telemetry = _replace_telemetry(
                telemetry,
                query_execution_completed_at_utc=_utc_now_iso(),
            )
            _notify_phase(phase_callback, "SQL fetch in progress")
            telemetry = _replace_telemetry(
                telemetry,
                current_sql_subphase="SQL fetch in progress",
                fetch_started_at_utc=_utc_now_iso(),
            )
            # SQLAlchemy and pandas only expose row counts after the result set is materialized,
            # so stage heartbeats cannot surface incremental fetch progress safely here.
            rows = result.fetchall()
            columns = tuple(str(column_name) for column_name in result.keys())
            result.close()
            telemetry = _replace_telemetry(
                telemetry,
                fetch_completed_at_utc=_utc_now_iso(),
                chunk_count=1 if rows else 0,
                completed_chunk_count=1 if rows else 0,
                cumulative_fetched_row_count=len(rows),
            )
            return PromotionQueryExecutionResult(
                frame=pd.DataFrame(rows, columns=columns),
                telemetry=telemetry,
            )
        except (OperationalError, InterfaceError) as error:
            current_stage = telemetry.current_sql_subphase or "SQL connecting"
            if _is_query_timeout(error):
                raised_error: RuntimeError = PromotionMssqlQueryTimeoutError(
                    "Promotions MSSQL query timed out during live extraction. "
                    "Inspect the SQL diagnostics summary, confirm whether the runtime window is expected, "
                    "and tune the query plan or increase PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS if needed. "
                    f"Driver detail: {_error_detail(error)}"
                )
            elif current_stage == "SQL connecting":
                raised_error = _build_connection_error(
                    error,
                    attempt_count=telemetry.connect_attempt_count or 1,
                )
            elif current_stage == "SQL fetch in progress":
                raised_error = PromotionMssqlFetchStreamError(
                    "Promotions MSSQL result transfer failed during row fetch after SQL execution completed. "
                    "Inspect the SQL diagnostics summary, review fetch progress, and rerun the incomplete partition. "
                    f"Driver detail: {_error_detail(error)}"
                )
            else:
                raised_error = PromotionMssqlQueryError(
                    "Promotions MSSQL execution failed after connection setup. "
                    "Inspect the SQL diagnostics summary and verify live query compatibility and performance. "
                    f"Driver detail: {_error_detail(error)}"
                )
            raise _attach_sql_execution_telemetry(
                raised_error,
                telemetry=telemetry,
                stage=current_stage,
                error_detail=error,
            ) from error
        except ProgrammingError as error:
            raise _attach_sql_execution_telemetry(
                PromotionMssqlQueryError(
                "Promotions MSSQL query failed. Verify PROMOTIONS_SCHEMA, PROMOTIONS_ADVICE_TABLE, "
                "PROMOTIONS_PWLOGD_TABLE, and the live source column names. "
                f"Driver detail: {_error_detail(error)}"
                ),
                telemetry=telemetry,
                stage=telemetry.current_sql_subphase or "SQL executing",
                error_detail=error,
            ) from error
        except SQLAlchemyError as error:
            raise _attach_sql_execution_telemetry(
                PromotionMssqlQueryError(
                "Promotions MSSQL execution failed after connection setup. Verify the live SQL schema and runtime query compatibility. "
                f"Driver detail: {_error_detail(error)}"
                ),
                telemetry=telemetry,
                stage=telemetry.current_sql_subphase or "SQL executing",
                error_detail=error,
            ) from error
        finally:
            if connection is not None:
                connection.close()
            if engine is not None:
                engine.dispose()

    def fetch_dataframe_in_chunks(
        self,
        *,
        sql: str,
        parameters: Mapping[str, object],
        chunk_row_count: int,
        chunk_consumer: PromotionSqlChunkConsumer,
        phase_callback: PromotionSqlSubphaseCallback | None = None,
    ) -> PromotionChunkedQueryExecutionResult:
        """Run the query and hand off bounded DataFrame chunks as rows stream back."""

        if chunk_row_count < 1:
            raise ValueError("chunk_row_count must be >= 1.")

        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError, SQLAlchemyError
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "SQLAlchemy is required for promotions MSSQL extraction."
            ) from error

        engine = None
        connection = None
        try:
            engine = create_engine(self.connection_url, future=True)
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "The configured MSSQL connection requires a DBAPI driver such as pyodbc."
            ) from error
        telemetry = PromotionSqlExecutionTelemetry(
            connect_timeout_seconds=self.connect_timeout_seconds,
            connect_retry_attempts=self.connect_retry_attempts,
            connect_retry_backoff_seconds=self.connect_retry_backoff_seconds,
            query_timeout_seconds=self.query_timeout_seconds,
            fetch_mode="chunked_fetch",
            fetch_chunk_row_count=chunk_row_count,
        )
        try:
            connection, telemetry = self._open_connection(
                engine=engine,
                telemetry=telemetry,
                phase_callback=phase_callback,
                operational_error_type=OperationalError,
                interface_error_type=InterfaceError,
            )
            telemetry = _replace_telemetry(
                telemetry,
                query_timeout_applied=_apply_query_timeout(
                    connection,
                    self.query_timeout_seconds,
                ),
            )
            _notify_phase(phase_callback, "SQL executing")
            telemetry = _replace_telemetry(
                telemetry,
                current_sql_subphase="SQL executing",
                query_execution_started_at_utc=_utc_now_iso(),
            )
            result = connection.execute(text(sql), dict(parameters))
            telemetry = _replace_telemetry(
                telemetry,
                query_execution_completed_at_utc=_utc_now_iso(),
            )
            _notify_phase(phase_callback, "SQL fetch in progress")
            telemetry = _replace_telemetry(
                telemetry,
                current_sql_subphase="SQL fetch in progress",
                fetch_started_at_utc=_utc_now_iso(),
            )
            columns = tuple(str(column_name) for column_name in result.keys())
            fetch_started_perf = time.perf_counter()
            chunk_index = 0
            cumulative_row_count = 0
            while True:
                chunk_started_perf = time.perf_counter()
                rows = result.fetchmany(chunk_row_count)
                chunk_fetch_seconds = round(time.perf_counter() - chunk_started_perf, 3)
                if not rows:
                    break
                chunk_index += 1
                chunk_frame = pd.DataFrame(rows, columns=columns)
                cumulative_row_count += len(chunk_frame.index)
                chunk_progress = PromotionSqlChunkFetchProgress(
                    chunk_index=chunk_index,
                    chunk_row_count=len(chunk_frame.index),
                    cumulative_row_count=cumulative_row_count,
                    chunk_fetch_seconds=chunk_fetch_seconds,
                    cumulative_elapsed_seconds=round(
                        time.perf_counter() - fetch_started_perf,
                        3,
                    ),
                )
                try:
                    chunk_consumer(chunk_frame, chunk_progress)
                except Exception as error:
                    setattr(error, "sql_execution_telemetry", telemetry)
                    setattr(error, "current_sql_subphase", telemetry.current_sql_subphase)
                    raise
                telemetry = _replace_telemetry(
                    telemetry,
                    chunk_count=chunk_index,
                    completed_chunk_count=chunk_index,
                    cumulative_fetched_row_count=cumulative_row_count,
                )
            result.close()
            telemetry = _replace_telemetry(
                telemetry,
                fetch_completed_at_utc=_utc_now_iso(),
                chunk_count=chunk_index,
                completed_chunk_count=chunk_index,
                cumulative_fetched_row_count=cumulative_row_count,
            )
            return PromotionChunkedQueryExecutionResult(
                columns=columns,
                telemetry=telemetry,
            )
        except (OperationalError, InterfaceError) as error:
            current_stage = telemetry.current_sql_subphase or "SQL connecting"
            if _is_query_timeout(error):
                raised_error: RuntimeError = PromotionMssqlQueryTimeoutError(
                    "Promotions MSSQL query timed out during live extraction. "
                    "Inspect the SQL diagnostics summary, confirm whether the runtime window is expected, "
                    "and tune the query plan or increase PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS if needed. "
                    f"Driver detail: {_error_detail(error)}"
                )
            elif current_stage == "SQL connecting":
                raised_error = _build_connection_error(
                    error,
                    attempt_count=telemetry.connect_attempt_count or 1,
                )
            elif current_stage == "SQL fetch in progress":
                raised_error = PromotionMssqlFetchStreamError(
                    "Promotions MSSQL result transfer failed during row fetch after SQL execution completed. "
                    "Inspect the SQL diagnostics summary, review fetch progress, and rerun the incomplete partition. "
                    f"Driver detail: {_error_detail(error)}"
                )
            else:
                raised_error = PromotionMssqlQueryError(
                    "Promotions MSSQL execution failed after connection setup. "
                    "Inspect the SQL diagnostics summary and verify live query compatibility and performance. "
                    f"Driver detail: {_error_detail(error)}"
                )
            raise _attach_sql_execution_telemetry(
                raised_error,
                telemetry=telemetry,
                stage=current_stage,
                error_detail=error,
            ) from error
        except ProgrammingError as error:
            raise _attach_sql_execution_telemetry(
                PromotionMssqlQueryError(
                    "Promotions MSSQL query failed. Verify PROMOTIONS_SCHEMA, PROMOTIONS_ADVICE_TABLE, "
                    "PROMOTIONS_PWLOGD_TABLE, and the live source column names. "
                    f"Driver detail: {_error_detail(error)}"
                ),
                telemetry=telemetry,
                stage=telemetry.current_sql_subphase or "SQL executing",
                error_detail=error,
            ) from error
        except SQLAlchemyError as error:
            raise _attach_sql_execution_telemetry(
                PromotionMssqlQueryError(
                    "Promotions MSSQL execution failed after connection setup. Verify the live SQL schema and runtime query compatibility. "
                    f"Driver detail: {_error_detail(error)}"
                ),
                telemetry=telemetry,
                stage=telemetry.current_sql_subphase or "SQL executing",
                error_detail=error,
            ) from error
        finally:
            if connection is not None:
                connection.close()
            if engine is not None:
                engine.dispose()

    def test_connection(self) -> PromotionSqlConnectionCheckResult:
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "SQLAlchemy is required for promotions MSSQL extraction."
            ) from error

        started_at = datetime.now(tz=UTC)
        engine = None
        connection = None
        try:
            engine = create_engine(self.connection_url, future=True)
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "The configured MSSQL connection requires a DBAPI driver such as pyodbc."
            ) from error
        telemetry = PromotionSqlExecutionTelemetry(
            connect_timeout_seconds=self.connect_timeout_seconds,
            connect_retry_attempts=self.connect_retry_attempts,
            connect_retry_backoff_seconds=self.connect_retry_backoff_seconds,
            query_timeout_seconds=self.query_timeout_seconds,
        )
        try:
            connection, telemetry = self._open_connection(
                engine=engine,
                telemetry=telemetry,
                phase_callback=None,
                operational_error_type=OperationalError,
                interface_error_type=InterfaceError,
            )
            timeout_applied = _apply_query_timeout(connection, self.query_timeout_seconds)
            connection.execute(text("SELECT 1"))
        except (OperationalError, InterfaceError) as error:
            if _is_query_timeout(error):
                raise PromotionMssqlQueryTimeoutError(
                    "Promotions MSSQL query timed out after SQL connect/login completed during the connection test. "
                    f"Driver detail: {_error_detail(error)}"
                ) from error
            raise PromotionMssqlQueryError(
                "Promotions MSSQL connection test failed after SQL connect/login completed. "
                f"Driver detail: {_error_detail(error)}"
            ) from error
        except SQLAlchemyError as error:
            raise PromotionMssqlQueryError(
                "Promotions MSSQL connection test failed after connection setup. "
                f"Driver detail: {_error_detail(error)}"
            ) from error
        finally:
            if connection is not None:
                connection.close()
            if engine is not None:
                engine.dispose()
        completed_at = datetime.now(tz=UTC)
        return PromotionSqlConnectionCheckResult(
            connected_at_utc=completed_at.isoformat(),
            elapsed_seconds=round((completed_at - started_at).total_seconds(), 3),
            connect_timeout_seconds=self.connect_timeout_seconds,
            connect_retry_attempts=self.connect_retry_attempts,
            connect_retry_backoff_seconds=self.connect_retry_backoff_seconds,
            connect_attempt_count=telemetry.connect_attempt_count or 1,
            query_timeout_seconds=self.query_timeout_seconds,
            query_timeout_applied=timeout_applied,
        )

    def _open_connection(
        self,
        *,
        engine: Any,
        telemetry: PromotionSqlExecutionTelemetry,
        phase_callback: PromotionSqlSubphaseCallback | None,
        operational_error_type: type[Exception],
        interface_error_type: type[Exception],
    ) -> tuple[Any, PromotionSqlExecutionTelemetry]:
        total_attempts = 1 + self.connect_retry_attempts
        started_at = telemetry.sql_connection_started_at_utc or _utc_now_iso()
        last_error: Exception | None = None
        attempt_records: list[dict] = list(telemetry.connect_attempts)

        for attempt_number in range(1, total_attempts + 1):
            phase_name = (
                f"SQL connecting (attempt {attempt_number}/{total_attempts})"
                if total_attempts > 1
                else "SQL connecting"
            )
            _notify_phase(phase_callback, phase_name)
            telemetry = _replace_telemetry(
                telemetry,
                current_sql_subphase="SQL connecting",
                sql_connection_started_at_utc=started_at,
                connect_attempt_count=attempt_number,
            )
            attempt_started_at = _utc_now_iso()
            attempt_started_perf = time.perf_counter()
            try:
                connection = engine.connect()
                attempt_elapsed = round(time.perf_counter() - attempt_started_perf, 3)
                attempt_records.append(
                    {
                        "attempt_number": attempt_number,
                        "total_allowed_attempts": total_attempts,
                        "connect_timeout_seconds_applied": self.connect_timeout_seconds,
                        "retry_backoff_seconds_applied": self.connect_retry_backoff_seconds,
                        "classification": "success",
                        "error_excerpt": None,
                        "started_at_utc": attempt_started_at,
                        "completed_at_utc": _utc_now_iso(),
                        "elapsed_seconds": attempt_elapsed,
                        "outcome": "success",
                    }
                )
                telemetry = _replace_telemetry(
                    telemetry,
                    current_sql_subphase="SQL connecting",
                    sql_connection_completed_at_utc=_utc_now_iso(),
                    connect_attempt_count=attempt_number,
                    connect_attempts=tuple(attempt_records),
                )
                return connection, telemetry
            except (operational_error_type, interface_error_type) as error:
                last_error = error
                attempt_elapsed = round(time.perf_counter() - attempt_started_perf, 3)
                classification = classify_promotions_mssql_connection_error(error)
                is_retryable = classification in {
                    "transient_timeout",
                    "transient_connectivity",
                }
                remaining_after_this = total_attempts - attempt_number
                terminal = (not is_retryable) or remaining_after_this <= 0
                attempt_records.append(
                    {
                        "attempt_number": attempt_number,
                        "total_allowed_attempts": total_attempts,
                        "connect_timeout_seconds_applied": self.connect_timeout_seconds,
                        "retry_backoff_seconds_applied": (
                            self.connect_retry_backoff_seconds if not terminal else 0.0
                        ),
                        "classification": classification,
                        "error_excerpt": _error_detail(error)[:400],
                        "started_at_utc": attempt_started_at,
                        "completed_at_utc": _utc_now_iso(),
                        "elapsed_seconds": attempt_elapsed,
                        "outcome": (
                            "failure_terminal" if terminal else "failure_retryable"
                        ),
                    }
                )
                telemetry = _replace_telemetry(
                    telemetry,
                    current_sql_subphase="SQL connecting",
                    connect_attempt_count=attempt_number,
                    connect_attempts=tuple(attempt_records),
                )
                if terminal:
                    break
                retry_notice = (
                    f"SQL connect/login failed (classification={classification}); "
                    f"retrying after {self.connect_retry_backoff_seconds:.1f}s "
                    f"(attempt {attempt_number + 1}/{total_attempts})"
                )
                _notify_phase(phase_callback, retry_notice)
                if self.connect_retry_backoff_seconds > 0:
                    time.sleep(self.connect_retry_backoff_seconds)

        assert last_error is not None
        raised_error = _build_connection_error(
            last_error,
            attempt_count=telemetry.connect_attempt_count or total_attempts,
        )
        raise _attach_sql_execution_telemetry(
            raised_error,
            telemetry=telemetry,
            stage="SQL connecting",
            error_detail=last_error,
        ) from last_error


def _build_mssql_connection_url(settings: PromotionMssqlSettings) -> str:
    """Build an ODBC-backed SQLAlchemy URL from surfaced runtime settings."""

    connection_parts = [
        f"DRIVER={{{settings.odbc_driver}}}",
        f"SERVER={settings.server}",
        f"DATABASE={settings.database}",
        f"Encrypt={'yes' if settings.encrypt else 'no'}",
        (
            "TrustServerCertificate=yes"
            if settings.trust_server_certificate
            else "TrustServerCertificate=no"
        ),
    ]
    if settings.connect_timeout_seconds is not None:
        connection_parts.append(f"Connection Timeout={settings.connect_timeout_seconds}")
    if settings.username and settings.password:
        connection_parts.extend(
            [f"UID={settings.username}", f"PWD={settings.password}"]
        )
    else:
        connection_parts.append("Trusted_Connection=yes")
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(';'.join(connection_parts))}"


def _error_detail(error: Exception) -> str:
    raw_detail = str(getattr(error, "orig", "") or str(error)).strip()
    if not raw_detail:
        return error.__class__.__name__
    return " ".join(raw_detail.split())


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _elapsed_seconds(started_at_utc: str | None, completed_at_utc: str | None) -> float | None:
    if started_at_utc is None or completed_at_utc is None:
        return None
    started_at = datetime.fromisoformat(started_at_utc)
    completed_at = datetime.fromisoformat(completed_at_utc)
    return round((completed_at - started_at).total_seconds(), 3)


def _notify_phase(
    phase_callback: PromotionSqlSubphaseCallback | None,
    phase_name: str,
) -> None:
    if phase_callback is not None:
        phase_callback(phase_name)


def _replace_telemetry(
    telemetry: PromotionSqlExecutionTelemetry,
    **changes: object,
) -> PromotionSqlExecutionTelemetry:
    payload = telemetry.to_dict()
    payload.pop("phase_elapsed_seconds", None)
    payload.update(changes)
    return PromotionSqlExecutionTelemetry(**payload)


def _apply_query_timeout(connection: Any, query_timeout_seconds: int | None) -> bool:
    if query_timeout_seconds is None:
        return False
    raw_connection = getattr(connection, "connection", None)
    if raw_connection is None:
        return False
    dbapi_connection = (
        getattr(raw_connection, "driver_connection", None)
        or getattr(raw_connection, "dbapi_connection", None)
        or raw_connection
    )
    if hasattr(dbapi_connection, "timeout"):
        setattr(dbapi_connection, "timeout", query_timeout_seconds)
        return True
    return False


def _attach_sql_execution_telemetry(
    error: RuntimeError,
    *,
    telemetry: PromotionSqlExecutionTelemetry,
    stage: str,
    error_detail: Exception,
) -> RuntimeError:
    enriched_telemetry = _replace_telemetry(
        telemetry,
        failure_stage=stage,
        failure_exception_type=type(error_detail).__name__,
        failure_message=_error_detail(error_detail),
    )
    setattr(error, "sql_execution_telemetry", enriched_telemetry)
    setattr(error, "current_sql_subphase", stage)
    setattr(error, "connect_timeout_seconds", telemetry.connect_timeout_seconds)
    setattr(error, "connect_retry_attempts", telemetry.connect_retry_attempts)
    setattr(error, "connect_retry_backoff_seconds", telemetry.connect_retry_backoff_seconds)
    setattr(error, "connect_attempt_count", telemetry.connect_attempt_count)
    setattr(error, "query_timeout_seconds", telemetry.query_timeout_seconds)
    return error


def _build_connection_error(error: Exception, *, attempt_count: int) -> RuntimeError:
    detail = _error_detail(error)
    classification = classify_promotions_mssql_connection_error(error)
    if classification == "transient_timeout":
        return PromotionMssqlConnectionTimeoutError(
            "Promotions MSSQL connect/login timed out before SQL execution started. "
            f"Attempts exhausted after {attempt_count} connect/login attempt(s). "
            "Next action: verify SQL Server network reachability and Azure SQL gateway latency, "
            "raise PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS if the network is known-slow, "
            "and confirm VPN / firewall egress to TCP 1433. "
            f"Driver detail: {detail}"
        )
    if classification == "transient_connectivity":
        return PromotionMssqlConnectivityError(
            "Promotions MSSQL connect/login failed due to a transient connectivity/transport error before SQL execution started. "
            f"Attempts exhausted after {attempt_count} connect/login attempt(s). "
            "Next action: check network path to the SQL server (DNS, VPN, firewall, TLS handshake), "
            "then retry. "
            f"Driver detail: {detail}"
        )
    if classification == "auth_failure":
        return PromotionMssqlAuthenticationError(
            "Promotions MSSQL authentication failed — credentials were rejected by the server. "
            "This is NOT retried. "
            "Next action: confirm PROMOTIONS_MSSQL_USERNAME / PROMOTIONS_MSSQL_PASSWORD (or the Azure AD login) "
            "and that the login has access to the configured database. "
            f"Driver detail: {detail}"
        )
    if classification == "config_failure":
        return PromotionMssqlConfigurationError(
            "Promotions MSSQL driver/configuration is invalid. This is NOT retried. "
            "Next action: verify PROMOTIONS_MSSQL_DRIVER is installed (e.g. 'ODBC Driver 18 for SQL Server'), "
            "PROMOTIONS_MSSQL_SERVER hostname resolves, and PROMOTIONS_MSSQL_DATABASE exists. "
            f"Driver detail: {detail}"
        )
    return PromotionMssqlConnectionError(
        "Promotions MSSQL connect/login failed before SQL execution started with an unclassified error. "
        f"Attempts exhausted after {attempt_count} connect/login attempt(s). "
        "Next action: inspect the raw driver detail below and rerun the connectivity preflight "
        "(python -m runtime.promotions.check_promotions_mssql_connectivity). "
        f"Driver detail: {detail}"
    )


# Classification ---------------------------------------------------------------
# Returned values are stable string tokens that flow into telemetry and tests.
_CONNECTION_ERROR_CLASSIFICATION_VALUES = (
    "transient_timeout",
    "transient_connectivity",
    "auth_failure",
    "config_failure",
    "unknown",
)


def classify_promotions_mssql_connection_error(error: Exception) -> str:
    """Classify a connect-time DBAPI/SQLAlchemy error.

    Returns one of the tokens in `_CONNECTION_ERROR_CLASSIFICATION_VALUES`.
    Only `transient_timeout` and `transient_connectivity` are eligible for
    retry; `auth_failure` and `config_failure` must surface immediately so
    operators are not waiting on retries that cannot succeed.
    """

    detail = _error_detail(error).lower()
    sqlstate = _extract_sqlstate(error, detail)

    # --- Auth (never retry) ---------------------------------------------------
    # SQLSTATE 28000 = invalid authorization specification.
    # 42000 + "cannot open" = login refused for the database.
    # "login failed for user" is the canonical MSSQL message.
    if sqlstate == "28000" or "login failed for user" in detail:
        return "auth_failure"
    if sqlstate == "42000" and ("cannot open" in detail or "permission" in detail):
        return "auth_failure"
    if "password did not match" in detail or "password expired" in detail:
        return "auth_failure"

    # --- Config (never retry) -------------------------------------------------
    # IM002 = data source not found / driver not installed.
    # IM003 = driver could not be loaded.
    # "can't open lib" / "image not found" = driver binary missing.
    if sqlstate in {"im001", "im002", "im003", "im004", "im005", "im006"}:
        return "config_failure"
    if (
        "data source name not found" in detail
        or "no default driver specified" in detail
        or "driver's sqlallochandle" in detail
        or "can't open lib" in detail
        or "image not found" in detail
        or "library not loaded" in detail
        or "specified driver could not be loaded" in detail
    ):
        return "config_failure"
    # Server hostname truly unresolvable is config-grade.
    if "name or service not known" in detail or "nodename nor servname" in detail:
        return "config_failure"

    # --- Transient timeout (retry) -------------------------------------------
    if (
        "login timeout expired" in detail
        or "connection timeout expired" in detail
        or "timeout expired" in detail and "query timeout" not in detail
        or sqlstate == "hyt00"
        or sqlstate == "hyt01"
    ):
        return "transient_timeout"

    # --- Transient connectivity (retry) --------------------------------------
    # SQLSTATE 08001 = client unable to establish connection.
    # 08S01 = communication link failure.
    # 08003 = connection does not exist (transient).
    # 08004 = server rejected the connection (often transient gateway).
    # 40613 = Azure SQL DB unavailable (transient).
    # 49918/49919/49920 = Azure throttling/transient.
    if sqlstate in {"08001", "08s01", "08003", "08004"}:
        return "transient_connectivity"
    if any(token in detail for token in (
        "40613",  # Azure SQL DB unavailable
        "49918",  # cannot process request, not enough resources
        "49919",  # cannot process create or update request, too many ops
        "49920",  # cannot process request, too many operations
        "tcp provider",
        "named pipes provider",
        "communication link failure",
        "connection forcibly closed",
        "connection was reset",
        "broken pipe",
        "an existing connection was forcibly closed",
        "transport-level error",
    )):
        return "transient_connectivity"

    return "unknown"


def _extract_sqlstate(error: Exception, lowered_detail: str) -> str | None:
    """Best-effort extraction of the SQLSTATE/ODBC state code from a driver error.

    pyodbc encodes SQLSTATE as `error.args[0]`. SQLAlchemy may wrap it; we also
    fall back to a regex scan of the message body for tokens like `[HYT00]`.
    """

    candidate: Any = None
    orig = getattr(error, "orig", None)
    if orig is not None and getattr(orig, "args", None):
        candidate = orig.args[0]
    elif getattr(error, "args", None):
        candidate = error.args[0]
    if isinstance(candidate, str) and candidate:
        token = candidate.strip().lower()
        # Some drivers stash the message in args[0] too; constrain to short codes.
        if 4 <= len(token) <= 5 and all(ch.isalnum() for ch in token):
            return token
    # Fallback: scan lowered detail for bracketed [xxxxx] code.
    import re

    match = re.search(r"\[([0-9a-z]{4,5})\]", lowered_detail)
    if match:
        return match.group(1)
    return None


def _is_query_timeout(error: Exception) -> bool:
    detail = _error_detail(error).lower()
    if "login timeout expired" in detail or "sqldriverconnect" in detail:
        return False
    return "query timeout expired" in detail or "hyt00" in detail


def _is_connection_timeout(error: Exception) -> bool:
    detail = _error_detail(error).lower()
    return (
        "login timeout expired" in detail
        or "connection timeout expired" in detail
        or "sqldriverconnect" in detail
        or "hyt01" in detail
    )
