from __future__ import annotations

"""Preflight MSSQL connectivity check for the promotions runtime.

Usage:
    python -m runtime.promotions.check_promotions_mssql_connectivity \
        --env-file .env [--connect-timeout-seconds 30]

Performs exactly one connect + `SELECT 1`. Prints a structured JSON diagnostic
on stdout and exits non-zero on failure. Designed to be safe and fast (no
extraction, no schema reads, no secrets in output) so operators can validate
SQL reachability before starting a multi-hour operational cycle.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from data.promotions.mssql_query_executor import (
    PromotionMssqlAuthenticationError,
    PromotionMssqlConfigurationError,
    PromotionMssqlConnectionError,
    PromotionMssqlConnectionTimeoutError,
    PromotionMssqlConnectivityError,
    SqlAlchemyMssqlQueryExecutor,
    classify_promotions_mssql_connection_error,
)
from runtime.promotions.config import PromotionMssqlSettings


_NEXT_ACTION_BY_CLASSIFICATION: dict[str, str] = {
    "success": "Connectivity OK. Proceed with the operational cycle.",
    "transient_timeout": (
        "Increase PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS, confirm VPN/firewall, "
        "and retry. If persistent, escalate Azure SQL gateway latency."
    ),
    "transient_connectivity": (
        "Check DNS resolution, VPN, TCP 1433 egress, and TLS handshake. "
        "Re-run the preflight; if persistent, escalate network path."
    ),
    "auth_failure": (
        "Authentication rejected — verify PROMOTIONS_MSSQL_USERNAME / "
        "PROMOTIONS_MSSQL_PASSWORD and that the login has access to the database. "
        "This is NOT a transient condition."
    ),
    "config_failure": (
        "Driver / DSN / server config invalid — verify PROMOTIONS_MSSQL_DRIVER is "
        "installed, PROMOTIONS_MSSQL_SERVER resolves, and PROMOTIONS_MSSQL_DATABASE exists."
    ),
    "unknown": (
        "Unclassified failure. Inspect the driver detail and rerun the preflight; "
        "if reproducible, capture full pyodbc/SQLAlchemy traceback for triage."
    ),
}


def _safe_settings_summary(settings: PromotionMssqlSettings) -> dict[str, object]:
    return {
        "server": settings.server,
        "database": settings.database,
        "odbc_driver": settings.odbc_driver,
        "connect_timeout_seconds": settings.connect_timeout_seconds,
        "connect_retry_attempts": settings.connect_retry_attempts,
        "connect_retry_backoff_seconds": settings.connect_retry_backoff_seconds,
        "auth_mode": "sql_login" if settings.username else "integrated_or_external",
        "encrypt": settings.encrypt,
        "trust_server_certificate": settings.trust_server_certificate,
    }


def run_preflight(
    *,
    env_file: str | Path | None = None,
    connect_timeout_seconds: int | None = None,
    connect_retry_attempts: int | None = None,
    connect_retry_backoff_seconds: float | None = None,
) -> dict[str, object]:
    settings = PromotionMssqlSettings.from_env(
        env_file=env_file,
        connect_timeout_seconds=connect_timeout_seconds,
        connect_retry_attempts=connect_retry_attempts,
        connect_retry_backoff_seconds=connect_retry_backoff_seconds,
    )
    # Force exactly one attempt during preflight to give a clean signal even if
    # the operational cycle is configured for retries.
    executor = SqlAlchemyMssqlQueryExecutor.from_settings(settings)
    executor = SqlAlchemyMssqlQueryExecutor(
        connection_url=executor.connection_url,
        connect_timeout_seconds=executor.connect_timeout_seconds,
        connect_retry_attempts=0,
        connect_retry_backoff_seconds=0.0,
        query_timeout_seconds=executor.query_timeout_seconds,
    )

    started_perf = time.perf_counter()
    result_payload: dict[str, object] = {
        "preflight": "promotions_mssql_connectivity",
        "settings": _safe_settings_summary(settings),
    }
    try:
        check = executor.test_connection()
        elapsed = round(time.perf_counter() - started_perf, 3)
        result_payload.update(
            {
                "success": True,
                "classification": "success",
                "elapsed_seconds": elapsed,
                "connected_at_utc": check.connected_at_utc,
                "next_action": _NEXT_ACTION_BY_CLASSIFICATION["success"],
            }
        )
        return result_payload
    except (
        PromotionMssqlConnectionTimeoutError,
        PromotionMssqlConnectivityError,
        PromotionMssqlAuthenticationError,
        PromotionMssqlConfigurationError,
        PromotionMssqlConnectionError,
    ) as error:
        elapsed = round(time.perf_counter() - started_perf, 3)
        # The connection error already carries the classified message; recover
        # the token from the underlying driver exception to keep telemetry
        # consistent with the executor's own classifier.
        underlying = error.__cause__ or error
        classification = classify_promotions_mssql_connection_error(underlying)
        result_payload.update(
            {
                "success": False,
                "classification": classification,
                "exception_type": type(error).__name__,
                "operator_message": str(error),
                "elapsed_seconds": elapsed,
                "next_action": _NEXT_ACTION_BY_CLASSIFICATION.get(
                    classification, _NEXT_ACTION_BY_CLASSIFICATION["unknown"]
                ),
            }
        )
        return result_payload


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight MSSQL connectivity check for promotions runtime.")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--connect-retry-attempts", type=int, default=None)
    parser.add_argument("--connect-retry-backoff-seconds", type=float, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    payload = run_preflight(
        env_file=args.env_file,
        connect_timeout_seconds=args.connect_timeout_seconds,
        connect_retry_attempts=args.connect_retry_attempts,
        connect_retry_backoff_seconds=args.connect_retry_backoff_seconds,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("success") else 2


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
