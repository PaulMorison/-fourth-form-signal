from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.mssql_query_executor import (  # noqa: E402
    PromotionMssqlAuthenticationError,
    PromotionMssqlConfigurationError,
    PromotionMssqlConnectionError,
    PromotionMssqlConnectionTimeoutError,
    PromotionMssqlConnectivityError,
    PromotionSqlExecutionTelemetry,
    SqlAlchemyMssqlQueryExecutor,
    classify_promotions_mssql_connection_error,
)


# ---------------------------------------------------------------------------
# Stub DBAPI/SQLAlchemy exception types: behave like pyodbc.OperationalError /
# sqlalchemy.exc.OperationalError. The executor only needs `isinstance` against
# the operational/interface error types injected into _open_connection, plus
# the `.orig.args[0]` / `.args[0]` SQLSTATE shape and `str(error)` body that
# the classifier inspects.
# ---------------------------------------------------------------------------
class _StubOperationalError(Exception):
    def __init__(self, sqlstate: str, message: str) -> None:
        # Match pyodbc shape: args = (SQLSTATE, "[SQLSTATE] [Driver] message ...")
        formatted = f"({sqlstate!r}, '[{sqlstate}] [ODBC Driver 18 for SQL Server]{message}')"
        super().__init__(sqlstate, formatted)
        # Match SQLAlchemy shape: .orig is the underlying DBAPI exception.
        self.orig = _StubDbapiError(sqlstate, message)

    def __str__(self) -> str:
        return str(self.orig)


class _StubInterfaceError(_StubOperationalError):
    pass


class _StubDbapiError(Exception):
    def __init__(self, sqlstate: str, message: str) -> None:
        body = f"[{sqlstate}] [ODBC Driver 18 for SQL Server]{message}"
        super().__init__(sqlstate, body)


def _login_timeout() -> _StubOperationalError:
    return _StubOperationalError(
        "HYT00",
        "Login timeout expired (0) (SQLDriverConnect)",
    )


def _transport_failure() -> _StubOperationalError:
    return _StubOperationalError(
        "08S01",
        "TCP Provider: An existing connection was forcibly closed by the remote host.",
    )


def _auth_failure() -> _StubOperationalError:
    return _StubOperationalError(
        "28000",
        "Login failed for user 'svc_promotions'.",
    )


def _bad_driver() -> _StubInterfaceError:
    return _StubInterfaceError(
        "IM002",
        "Data source name not found and no default driver specified.",
    )


def _bad_hostname() -> _StubOperationalError:
    return _StubOperationalError(
        "08001",
        "TCP Provider: nodename nor servname provided, or not known.",
    )


def _azure_throttle() -> _StubOperationalError:
    return _StubOperationalError(
        "40197",
        "The service has encountered an error processing your request: 40613 Database is currently unavailable.",
    )


# ---------------------------------------------------------------------------
# Classifier tests
# ---------------------------------------------------------------------------
class ClassifierTests(unittest.TestCase):
    def test_login_timeout_is_transient_timeout(self) -> None:
        self.assertEqual(
            classify_promotions_mssql_connection_error(_login_timeout()),
            "transient_timeout",
        )

    def test_transport_failure_is_transient_connectivity(self) -> None:
        self.assertEqual(
            classify_promotions_mssql_connection_error(_transport_failure()),
            "transient_connectivity",
        )

    def test_azure_throttle_is_transient_connectivity(self) -> None:
        self.assertEqual(
            classify_promotions_mssql_connection_error(_azure_throttle()),
            "transient_connectivity",
        )

    def test_auth_failure_is_not_retried(self) -> None:
        self.assertEqual(
            classify_promotions_mssql_connection_error(_auth_failure()),
            "auth_failure",
        )

    def test_bad_driver_is_config_failure(self) -> None:
        self.assertEqual(
            classify_promotions_mssql_connection_error(_bad_driver()),
            "config_failure",
        )

    def test_unresolvable_hostname_is_config_failure(self) -> None:
        self.assertEqual(
            classify_promotions_mssql_connection_error(_bad_hostname()),
            "config_failure",
        )


# ---------------------------------------------------------------------------
# Retry loop tests — drive _open_connection with a stubbed engine.
# ---------------------------------------------------------------------------
@dataclass
class _StubEngine:
    """Engine stub whose .connect() raises a scripted sequence of exceptions
    and finally returns a sentinel connection object."""

    failures: list[Exception]
    success_value: object = "STUB_CONNECTION"
    call_count: int = 0

    def connect(self) -> object:
        self.call_count += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.success_value


def _new_executor(retry_attempts: int, backoff_seconds: float = 0.0) -> SqlAlchemyMssqlQueryExecutor:
    return SqlAlchemyMssqlQueryExecutor(
        connection_url="stub://",
        connect_timeout_seconds=30,
        connect_retry_attempts=retry_attempts,
        connect_retry_backoff_seconds=backoff_seconds,
        query_timeout_seconds=None,
    )


def _initial_telemetry(executor: SqlAlchemyMssqlQueryExecutor) -> PromotionSqlExecutionTelemetry:
    return PromotionSqlExecutionTelemetry(
        connect_timeout_seconds=executor.connect_timeout_seconds,
        connect_retry_attempts=executor.connect_retry_attempts,
        connect_retry_backoff_seconds=executor.connect_retry_backoff_seconds,
        query_timeout_seconds=executor.query_timeout_seconds,
    )


class OpenConnectionRetryTests(unittest.TestCase):
    def test_transient_timeout_retried_then_succeeds(self) -> None:
        executor = _new_executor(retry_attempts=2)
        engine = _StubEngine(failures=[_login_timeout()])
        connection, telemetry = executor._open_connection(
            engine=engine,
            telemetry=_initial_telemetry(executor),
            phase_callback=None,
            operational_error_type=_StubOperationalError,
            interface_error_type=_StubInterfaceError,
        )
        self.assertEqual(connection, "STUB_CONNECTION")
        self.assertEqual(engine.call_count, 2)
        self.assertEqual(len(telemetry.connect_attempts), 2)
        self.assertEqual(telemetry.connect_attempts[0]["classification"], "transient_timeout")
        self.assertEqual(telemetry.connect_attempts[0]["outcome"], "failure_retryable")
        self.assertEqual(telemetry.connect_attempts[1]["classification"], "success")
        self.assertEqual(telemetry.connect_attempts[1]["outcome"], "success")

    def test_transient_timeout_exhausts_attempts_raises_timeout_error(self) -> None:
        executor = _new_executor(retry_attempts=2)
        engine = _StubEngine(failures=[_login_timeout(), _login_timeout(), _login_timeout()])
        with self.assertRaises(PromotionMssqlConnectionTimeoutError) as ctx:
            executor._open_connection(
                engine=engine,
                telemetry=_initial_telemetry(executor),
                phase_callback=None,
                operational_error_type=_StubOperationalError,
                interface_error_type=_StubInterfaceError,
            )
        self.assertEqual(engine.call_count, 3)
        telemetry = getattr(ctx.exception, "sql_execution_telemetry")
        self.assertEqual(len(telemetry.connect_attempts), 3)
        self.assertEqual(telemetry.connect_attempts[-1]["outcome"], "failure_terminal")
        # Operator message states next action and classification.
        self.assertIn("Attempts exhausted after 3", str(ctx.exception))

    def test_auth_failure_is_not_retried(self) -> None:
        executor = _new_executor(retry_attempts=5)
        engine = _StubEngine(failures=[_auth_failure(), _auth_failure()])
        with self.assertRaises(PromotionMssqlAuthenticationError) as ctx:
            executor._open_connection(
                engine=engine,
                telemetry=_initial_telemetry(executor),
                phase_callback=None,
                operational_error_type=_StubOperationalError,
                interface_error_type=_StubInterfaceError,
            )
        # Exactly one attempt — no retries for auth.
        self.assertEqual(engine.call_count, 1)
        telemetry = getattr(ctx.exception, "sql_execution_telemetry")
        self.assertEqual(len(telemetry.connect_attempts), 1)
        self.assertEqual(telemetry.connect_attempts[0]["classification"], "auth_failure")
        self.assertEqual(telemetry.connect_attempts[0]["outcome"], "failure_terminal")
        self.assertIn("NOT retried", str(ctx.exception))

    def test_config_failure_is_not_retried(self) -> None:
        executor = _new_executor(retry_attempts=5)
        engine = _StubEngine(failures=[_bad_driver()])
        with self.assertRaises(PromotionMssqlConfigurationError) as ctx:
            executor._open_connection(
                engine=engine,
                telemetry=_initial_telemetry(executor),
                phase_callback=None,
                operational_error_type=_StubOperationalError,
                interface_error_type=_StubInterfaceError,
            )
        self.assertEqual(engine.call_count, 1)
        telemetry = getattr(ctx.exception, "sql_execution_telemetry")
        self.assertEqual(telemetry.connect_attempts[0]["classification"], "config_failure")
        self.assertIn("NOT retried", str(ctx.exception))

    def test_connectivity_then_success(self) -> None:
        executor = _new_executor(retry_attempts=3)
        engine = _StubEngine(failures=[_transport_failure(), _transport_failure()])
        connection, telemetry = executor._open_connection(
            engine=engine,
            telemetry=_initial_telemetry(executor),
            phase_callback=None,
            operational_error_type=_StubOperationalError,
            interface_error_type=_StubInterfaceError,
        )
        self.assertEqual(connection, "STUB_CONNECTION")
        self.assertEqual(engine.call_count, 3)
        classifications = [a["classification"] for a in telemetry.connect_attempts]
        self.assertEqual(
            classifications,
            ["transient_connectivity", "transient_connectivity", "success"],
        )

    def test_unknown_failure_is_not_retried_and_surfaces_generic_error(self) -> None:
        executor = _new_executor(retry_attempts=4)
        engine = _StubEngine(
            failures=[_StubOperationalError("XX999", "Something unclassified happened.")]
        )
        with self.assertRaises(PromotionMssqlConnectionError) as ctx:
            executor._open_connection(
                engine=engine,
                telemetry=_initial_telemetry(executor),
                phase_callback=None,
                operational_error_type=_StubOperationalError,
                interface_error_type=_StubInterfaceError,
            )
        self.assertEqual(engine.call_count, 1)
        # Generic class — must NOT be auth/config/timeout/connectivity subclass.
        self.assertNotIsInstance(ctx.exception, PromotionMssqlConnectionTimeoutError)
        self.assertNotIsInstance(ctx.exception, PromotionMssqlConnectivityError)
        self.assertNotIsInstance(ctx.exception, PromotionMssqlAuthenticationError)
        self.assertNotIsInstance(ctx.exception, PromotionMssqlConfigurationError)
        telemetry = getattr(ctx.exception, "sql_execution_telemetry")
        self.assertEqual(telemetry.connect_attempts[0]["classification"], "unknown")


if __name__ == "__main__":
    unittest.main()
