from __future__ import annotations

"""Shared runtime configuration for the promotions modelling pipeline.

Canon ownership:
- Declares the explicit runtime, windowing, and artifact-path settings used by
  promotions extraction, dataset assembly, training, scoring, and reporting.
- Keeps output paths, SQL source names, and observation windows surfaced at the
  workflow boundary so later modules do not bury behavioral constants.
- Does not own SQL execution, feature definitions, target semantics, model
  training logic, or reporting assembly.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
import os
from pathlib import Path
from typing import Literal, Mapping

from dotenv import load_dotenv

from runtime.promotions.commercial_output_paths import PromotionCommercialOutputPathBuilder


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ENV_FILE = _REPO_ROOT / ".env"
_DEFAULT_ARTIFACT_ROOT = _REPO_ROOT / "artifacts" / "promotions"
_DEFAULT_LOCAL_INSPECTION_ROOT = _REPO_ROOT / "tmp" / "promotions_local_inspection"
DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS = 2
DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS = 5.0

_PROMOTIONS_MSSQL_ENV_MAP = {
    "server": ("PROMOTIONS_MSSQL_SERVER", "PROMOTIONS_SQL_SERVER"),
    "database": ("PROMOTIONS_MSSQL_DATABASE", "PROMOTIONS_SQL_DATABASE"),
    "username": ("PROMOTIONS_MSSQL_USERNAME", "PROMOTIONS_SQL_USERNAME"),
    "password": ("PROMOTIONS_MSSQL_PASSWORD", "PROMOTIONS_SQL_PASSWORD"),
    "odbc_driver": ("PROMOTIONS_MSSQL_DRIVER", "PROMOTIONS_SQL_DRIVER"),
    "connect_timeout_seconds": (
        "PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS",
        "PROMOTIONS_SQL_CONNECT_TIMEOUT_SECONDS",
    ),
    "connect_retry_attempts": (
        "PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS",
        "PROMOTIONS_SQL_CONNECT_RETRY_ATTEMPTS",
    ),
    "connect_retry_backoff_seconds": (
        "PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS",
        "PROMOTIONS_SQL_CONNECT_RETRY_BACKOFF_SECONDS",
    ),
    "query_timeout_seconds": (
        "PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS",
        "PROMOTIONS_SQL_QUERY_TIMEOUT_SECONDS",
    ),
    "encrypt": ("PROMOTIONS_MSSQL_ENCRYPT", "PROMOTIONS_SQL_ENCRYPT"),
    "trust_server_certificate": (
        "PROMOTIONS_MSSQL_TRUST_SERVER_CERTIFICATE",
        "PROMOTIONS_SQL_TRUST_SERVER_CERTIFICATE",
    ),
}
_PROMOTIONS_MSSQL_CLI_FLAG_MAP = {
    "server": "--server",
    "database": "--database",
    "username": "--username",
    "password": "--password",
    "odbc_driver": "--odbc-driver",
    "connect_timeout_seconds": "--connect-timeout-seconds",
    "connect_retry_attempts": "--connect-retry-attempts",
    "connect_retry_backoff_seconds": "--connect-retry-backoff-seconds",
    "query_timeout_seconds": "--query-timeout-seconds",
    "encrypt": "--encrypt",
    "trust_server_certificate": "--trust-server-certificate",
}
_PROMOTIONS_RUNTIME_ENV_MAP = {
    "promotion_advice_table": ("PROMOTIONS_ADVICE_TABLE",),
    "pwlogd_table": ("PROMOTIONS_PWLOGD_TABLE",),
    "schema": ("PROMOTIONS_SCHEMA",),
    "artifact_root": ("PROMOTIONS_NAS_ROOT", "PROMOTIONS_ARTIFACT_ROOT"),
    "local_inspection_root": ("PROMOTIONS_LOCAL_INSPECTION_ROOT",),
    "enable_local_inspection_copy": ("PROMOTIONS_ENABLE_LOCAL_INSPECTION_COPY",),
}
_PROMOTIONS_COMPLETED_EXTRACTION_ENV_MAP = {
    "enable_landed_batches": ("PROMOTIONS_COMPLETED_ENABLE_LANDED_BATCHES",),
    "batch_row_count": ("PROMOTIONS_COMPLETED_BATCH_ROW_COUNT",),
    "completed_sales_history_start_date": (
        "PROMOTIONS_COMPLETED_SALES_HISTORY_START_DATE",
    ),
    "enable_chunked_fetch": ("PROMOTIONS_COMPLETED_ENABLE_CHUNKED_FETCH",),
    "chunk_row_count": ("PROMOTIONS_COMPLETED_CHUNK_ROW_COUNT",),
    "resume_completed_partitions": ("PROMOTIONS_COMPLETED_RESUME_COMPLETED_PARTITIONS",),
    "stage_temp_chunk_files": ("PROMOTIONS_COMPLETED_STAGE_TEMP_CHUNK_FILES",),
}
_PROMOTIONS_RUNTIME_CLI_FLAG_MAP = {
    "promotion_advice_table": "--promotion-advice-table",
    "pwlogd_table": "--pwlogd-table",
    "schema": "--schema",
}
_PROMOTIONS_COMPLETED_EXTRACTION_CLI_FLAG_MAP = {
    "enable_landed_batches": "--enable-landed-batches",
    "batch_row_count": "--batch-row-count",
    "completed_sales_history_start_date": "--completed-sales-history-start-date",
    "enable_chunked_fetch": "--enable-chunked-fetch",
    "chunk_row_count": "--chunk-row-count",
    "resume_completed_partitions": "--resume-completed-partitions",
    "stage_temp_chunk_files": "--stage-temp-chunk-files",
}


class PromotionRuntimeConfigError(ValueError):
    """Raised when a promotions runtime setting is missing or invalid."""

    def __init__(
        self,
        message: str,
        *,
        field_name: str | None = None,
        source: str | None = None,
        expected_from: tuple[str, ...] = (),
        next_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.field_name = field_name
        self.source = source
        self.expected_from = expected_from
        self.next_action = next_action


@dataclass(frozen=True)
class PromotionResolvedSetting:
    value: object | None
    source: str


@dataclass(frozen=True)
class PromotionMssqlSettingsResolution:
    config_source: str
    env_file_path: str | None
    field_sources: Mapping[str, str]


@dataclass(frozen=True)
class PromotionMssqlSettingsSummary:
    config_source: str
    env_file_path: str | None
    server: str
    server_source: str
    database: str
    database_source: str
    schema: str
    schema_source: str
    promotion_advice_table: str
    promotion_advice_table_source: str
    pwlogd_table: str
    pwlogd_table_source: str
    user: str | None
    user_source: str
    authentication_mode: str
    password_present: bool
    password_source: str
    connect_timeout_seconds: int | None
    connect_timeout_seconds_source: str
    connect_retry_attempts: int
    connect_retry_attempts_source: str
    connect_retry_backoff_seconds: float
    connect_retry_backoff_seconds_source: str
    query_timeout_seconds: int | None
    query_timeout_seconds_source: str
    encrypt: bool
    encrypt_source: str
    trust_server_certificate: bool
    trust_server_certificate_source: str

    def to_context_dict(self) -> dict[str, str]:
        return {
            "config_source": self.config_source,
            "env_file_path": self.env_file_path or "not_loaded",
            "server": self.server,
            "database": self.database,
            "schema": self.schema,
            "promotion_advice_table": self.promotion_advice_table,
            "pwlogd_table": self.pwlogd_table,
            "user": self.user or "not_set",
            "authentication_mode": self.authentication_mode,
            "password_present": _format_bool(self.password_present),
            "connect_timeout_seconds": _format_optional_number(self.connect_timeout_seconds),
            "connect_retry_attempts": str(self.connect_retry_attempts),
            "connect_retry_backoff_seconds": str(self.connect_retry_backoff_seconds),
            "query_timeout_seconds": _format_optional_number(self.query_timeout_seconds),
            "encrypt": _format_bool(self.encrypt),
            "trust_server_certificate": _format_bool(self.trust_server_certificate),
        }

    def render_lines(self, *, heading: str = "PROMOTIONS MSSQL SETTINGS") -> tuple[str, ...]:
        return (
            heading,
            f"config_source: {self.config_source}",
            f"server: {_render_summary_value(self.server, self.server_source)}",
            f"database: {_render_summary_value(self.database, self.database_source)}",
            f"schema: {_render_summary_value(self.schema, self.schema_source)}",
            (
                "promotion_advice_table: "
                f"{_render_summary_value(self.promotion_advice_table, self.promotion_advice_table_source)}"
            ),
            f"pwlogd_table: {_render_summary_value(self.pwlogd_table, self.pwlogd_table_source)}",
            f"user: {_render_summary_value(self.user or 'not_set', self.user_source)}",
            f"authentication_mode: {self.authentication_mode} (derived)",
            f"password_present: {_render_summary_value(_format_bool(self.password_present), self.password_source)}",
            (
                "connect_timeout_seconds: "
                f"{_render_summary_value(_format_optional_number(self.connect_timeout_seconds), self.connect_timeout_seconds_source)}"
            ),
            (
                "connect_retry_attempts: "
                f"{_render_summary_value(self.connect_retry_attempts, self.connect_retry_attempts_source)}"
            ),
            (
                "connect_retry_backoff_seconds: "
                f"{_render_summary_value(self.connect_retry_backoff_seconds, self.connect_retry_backoff_seconds_source)}"
            ),
            (
                "query_timeout_seconds: "
                f"{_render_summary_value(_format_optional_number(self.query_timeout_seconds), self.query_timeout_seconds_source)}"
            ),
            f"encrypt: {_render_summary_value(_format_bool(self.encrypt), self.encrypt_source)}",
            (
                "trust_server_certificate: "
                f"{_render_summary_value(_format_bool(self.trust_server_certificate), self.trust_server_certificate_source)}"
            ),
        )


def load_promotions_env(env_file: str | Path | None = None) -> Path | None:
    """Load a repo-local or explicit `.env` file into process environment state."""

    candidate = Path(env_file) if env_file is not None else _DEFAULT_ENV_FILE
    if not candidate.exists():
        return None
    load_dotenv(candidate, override=True)
    return candidate


def _resolve_bool_setting(raw_value: str | bool | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean setting '{raw_value}'. Use yes/no, true/false, or 1/0.")


def _format_bool(value: bool) -> str:
    return str(value).lower()


def _format_optional_number(value: int | float | None) -> str:
    return str(value) if value is not None else "disabled"


def _render_summary_value(value: object, source: str) -> str:
    return f"{value} ({source})"


def _primary_env_name(env_names: tuple[str, ...]) -> str:
    return env_names[0]


def _resolve_int_setting(
    raw_value: str | int | None,
    *,
    minimum: int = 1,
) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        if raw_value < minimum:
            raise ValueError(f"Integer setting must be >= {minimum}. Received {raw_value}.")
        return raw_value
    normalized = raw_value.strip()
    if normalized == "":
        return None
    try:
        resolved_value = int(normalized)
    except ValueError as error:
        raise ValueError(f"Invalid integer setting '{raw_value}'.") from error
    if resolved_value < minimum:
        raise ValueError(f"Integer setting must be >= {minimum}. Received {resolved_value}.")
    return resolved_value


def _resolve_float_setting(
    raw_value: str | float | int | None,
    *,
    minimum: float = 0.0,
) -> float | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        resolved_value = float(raw_value)
        if resolved_value < minimum:
            raise ValueError(
                f"Float setting must be >= {minimum}. Received {resolved_value}."
            )
        return resolved_value
    normalized = raw_value.strip()
    if normalized == "":
        return None
    try:
        resolved_value = float(normalized)
    except ValueError as error:
        raise ValueError(f"Invalid float setting '{raw_value}'.") from error
    if resolved_value < minimum:
        raise ValueError(f"Float setting must be >= {minimum}. Received {resolved_value}.")
    return resolved_value


def _resolve_iso_date_setting(
    raw_value: str | date | None,
) -> date | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, date):
        return raw_value
    normalized = raw_value.strip()
    if normalized == "":
        return None
    try:
        return date.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(
            f"Invalid ISO date setting '{raw_value}'. Expected YYYY-MM-DD."
        ) from error


def _coalesce_env_value(
    override: str | None,
    env_names: tuple[str, ...],
    *,
    default: str | None = None,
) -> str | None:
    if override is not None and override.strip() != "":
        return override
    for env_name in env_names:
        value = os.getenv(env_name)
        if value is not None and value.strip() != "":
            return value
    return default


def _resolve_setting_with_source(
    override: object | None,
    env_names: tuple[str, ...],
    *,
    cli_flag: str,
    default: object | None = None,
) -> PromotionResolvedSetting:
    if override is not None:
        if not isinstance(override, str) or override.strip() != "":
            return PromotionResolvedSetting(override, f"cli:{cli_flag}")
    for env_name in env_names:
        value = os.getenv(env_name)
        if value is not None and value.strip() != "":
            return PromotionResolvedSetting(value, f"env:{env_name}")
    if default is not None:
        return PromotionResolvedSetting(default, "default")
    return PromotionResolvedSetting(None, "not_provided")


def _config_source_label(
    env_file: str | Path | None,
    loaded_env_file: Path | None,
) -> tuple[str, str | None]:
    if loaded_env_file is not None:
        if env_file is not None:
            return (f"explicit_env_file:{loaded_env_file}", str(loaded_env_file))
        return (f"repo_default_env_file:{loaded_env_file}", str(loaded_env_file))
    if env_file is not None:
        requested_env_file = str(Path(env_file))
        return (f"explicit_env_file_missing:{requested_env_file}", requested_env_file)
    return ("process_environment_only", None)


def _expected_sources_for_field(field_name: str) -> tuple[str, ...]:
    if field_name in _PROMOTIONS_MSSQL_ENV_MAP:
        return (
            _PROMOTIONS_MSSQL_CLI_FLAG_MAP[field_name],
            *_PROMOTIONS_MSSQL_ENV_MAP[field_name],
        )
    if field_name in _PROMOTIONS_RUNTIME_ENV_MAP:
        cli_flag = _PROMOTIONS_RUNTIME_CLI_FLAG_MAP.get(field_name)
        sources = tuple(_PROMOTIONS_RUNTIME_ENV_MAP[field_name])
        if cli_flag is None:
            return sources
        return (cli_flag, *sources)
    return ()


def _missing_runtime_setting_error(
    *,
    field_name: str,
    config_source: str,
) -> PromotionRuntimeConfigError:
    expected_from = _expected_sources_for_field(field_name)
    expected_label = ", ".join(expected_from)
    next_action = (
        f"Set {expected_from[0]} or define one of {', '.join(expected_from[1:])}. "
        f"Current config source: {config_source}."
        if len(expected_from) > 1
        else f"Set {expected_label}. Current config source: {config_source}."
    )
    return PromotionRuntimeConfigError(
        (
            f"Missing required promotions SQL setting '{field_name}'. "
            f"Expected from: {expected_label}. Config source: {config_source}."
        ),
        field_name=field_name,
        expected_from=expected_from,
        next_action=next_action,
    )


def _invalid_runtime_setting_error(
    *,
    field_name: str,
    source: str,
    message: str,
) -> PromotionRuntimeConfigError:
    expected_from = _expected_sources_for_field(field_name)
    return PromotionRuntimeConfigError(
        f"Invalid promotions SQL setting '{field_name}' from {source}: {message}",
        field_name=field_name,
        source=source,
        expected_from=expected_from,
        next_action=(
            f"Correct {source} for '{field_name}' and rerun. Supported sources: {', '.join(expected_from)}."
        ),
    )


def _resolve_int_setting_with_source(
    *,
    field_name: str,
    override: str | int | None,
    default: int | None,
    minimum: int,
) -> PromotionResolvedSetting:
    resolved = _resolve_setting_with_source(
        override,
        _PROMOTIONS_MSSQL_ENV_MAP[field_name],
        cli_flag=_PROMOTIONS_MSSQL_CLI_FLAG_MAP[field_name],
        default=default,
    )
    try:
        return PromotionResolvedSetting(
            _resolve_int_setting(resolved.value, minimum=minimum),
            resolved.source,
        )
    except ValueError as error:
        raise _invalid_runtime_setting_error(
            field_name=field_name,
            source=resolved.source,
            message=str(error),
        ) from error


def _resolve_float_setting_with_source(
    *,
    field_name: str,
    override: str | float | int | None,
    default: float | None,
    minimum: float,
) -> PromotionResolvedSetting:
    resolved = _resolve_setting_with_source(
        override,
        _PROMOTIONS_MSSQL_ENV_MAP[field_name],
        cli_flag=_PROMOTIONS_MSSQL_CLI_FLAG_MAP[field_name],
        default=default,
    )
    try:
        return PromotionResolvedSetting(
            _resolve_float_setting(resolved.value, minimum=minimum),
            resolved.source,
        )
    except ValueError as error:
        raise _invalid_runtime_setting_error(
            field_name=field_name,
            source=resolved.source,
            message=str(error),
        ) from error


def _resolve_bool_setting_with_source(
    *,
    field_name: str,
    override: str | bool | None,
    default: bool,
) -> PromotionResolvedSetting:
    resolved = _resolve_setting_with_source(
        override,
        _PROMOTIONS_MSSQL_ENV_MAP[field_name],
        cli_flag=_PROMOTIONS_MSSQL_CLI_FLAG_MAP[field_name],
    )
    try:
        return PromotionResolvedSetting(
            _resolve_bool_setting(resolved.value, default=default),
            resolved.source if resolved.value is not None else "default",
        )
    except ValueError as error:
        raise _invalid_runtime_setting_error(
            field_name=field_name,
            source=resolved.source,
            message=str(error),
        ) from error


def build_promotions_mssql_settings_summary(
    settings: "PromotionMssqlSettings",
) -> PromotionMssqlSettingsSummary:
    resolution = settings.resolution or PromotionMssqlSettingsResolution(
        config_source="manual_object",
        env_file_path=None,
        field_sources={},
    )
    field_sources = resolution.field_sources
    authentication_mode = (
        "sql_username_password"
        if settings.username and settings.password
        else "driver_or_integrated_auth"
    )
    return PromotionMssqlSettingsSummary(
        config_source=resolution.config_source,
        env_file_path=resolution.env_file_path,
        server=settings.server,
        server_source=field_sources.get("server", "manual_object"),
        database=settings.database,
        database_source=field_sources.get("database", "manual_object"),
        schema=settings.schema,
        schema_source=field_sources.get("schema", "manual_object"),
        promotion_advice_table=settings.promotion_advice_table,
        promotion_advice_table_source=field_sources.get(
            "promotion_advice_table",
            "manual_object",
        ),
        pwlogd_table=settings.pwlogd_table,
        pwlogd_table_source=field_sources.get("pwlogd_table", "manual_object"),
        user=settings.username,
        user_source=field_sources.get(
            "username",
            "manual_object" if settings.username else "not_provided",
        ),
        authentication_mode=authentication_mode,
        password_present=bool(settings.password),
        password_source=field_sources.get(
            "password",
            "manual_object" if settings.password else "not_provided",
        ),
        connect_timeout_seconds=settings.connect_timeout_seconds,
        connect_timeout_seconds_source=field_sources.get(
            "connect_timeout_seconds",
            "manual_object",
        ),
        connect_retry_attempts=settings.connect_retry_attempts,
        connect_retry_attempts_source=field_sources.get(
            "connect_retry_attempts",
            "manual_object",
        ),
        connect_retry_backoff_seconds=settings.connect_retry_backoff_seconds,
        connect_retry_backoff_seconds_source=field_sources.get(
            "connect_retry_backoff_seconds",
            "manual_object",
        ),
        query_timeout_seconds=settings.query_timeout_seconds,
        query_timeout_seconds_source=field_sources.get(
            "query_timeout_seconds",
            "manual_object",
        ),
        encrypt=settings.encrypt,
        encrypt_source=field_sources.get("encrypt", "manual_object"),
        trust_server_certificate=settings.trust_server_certificate,
        trust_server_certificate_source=field_sources.get(
            "trust_server_certificate",
            "manual_object",
        ),
    )


def _qualify_table_name(table_name: str, schema: str) -> str:
    normalized = table_name.strip()
    if "." in normalized:
        return normalized
    return f"{schema}.{normalized}"


def _resolve_artifact_root(root_value: str | Path) -> Path:
    root_path = Path(root_value)
    if root_path.is_absolute():
        return root_path
    return _REPO_ROOT / root_path


@dataclass(frozen=True)
class PromotionWindowSettings:
    """Named temporal windows used across extraction, labels, and features."""

    baseline_lookback_days: int = 56
    short_baseline_days: int = 28
    immediate_baseline_days: int = 7
    post_promo_days: int = 14


PromotionPartitionStrategy = Literal[
    "store_number",
    "supplier_number",
    "store_sku_hash_bucket",
    "promotion_name_hash_bucket",
    "promotion_row_key_hash_bucket",
]


@dataclass(frozen=True)
class PromotionCompletedPreflightPlannerSettings:
    """Thresholds and execution controls for completed-extraction preflight planning."""

    run_preflight: bool = False
    planner_only: bool = False
    auto_repartition_completed: bool = True
    max_completed_repartition_attempts: int = 6
    max_completed_partition_count: int = 512
    max_candidate_promotion_rows: int | None = 2_000
    max_candidate_store_sku: int | None = 1_000
    max_window_span_days_total: int | None = 125_000
    max_window_span_days_max: int | None = 120
    max_estimated_cost_score: float | None = 1.0
    preflight_query_execution_seconds_multiplier: float = 20.0
    proof_completed_fallback_mode: str = "diagnostic_topn"
    proof_completed_fallback_topn_limit: int = 50
    proof_completed_fallback_slice_promotion_count: int = 25
    default_partition_strategy: PromotionPartitionStrategy = "store_sku_hash_bucket"
    # When the planner recommends a larger partition_count to bring the dominant
    # volumetric metric within threshold, multiply the proportional bump by this
    # factor so a single retry escapes hash-bucket skew rather than creeping up
    # by 1–2 partitions per attempt. Must be >= 1.0; set to 1.0 to disable
    # skew anticipation. Does not apply to per-row width metrics that cannot be
    # reduced by partitioning (e.g. candidate_window_span_days_max).
    repartition_skew_safety_multiplier: float = 1.5

    def __post_init__(self) -> None:
        positive_thresholds = {
            "max_candidate_promotion_rows": self.max_candidate_promotion_rows,
            "max_candidate_store_sku": self.max_candidate_store_sku,
            "max_window_span_days_total": self.max_window_span_days_total,
            "max_window_span_days_max": self.max_window_span_days_max,
        }
        for field_name, value in positive_thresholds.items():
            if value is not None and value < 1:
                raise ValueError(f"{field_name} must be >= 1 when provided.")
        if self.max_estimated_cost_score is not None and self.max_estimated_cost_score <= 0.0:
            raise ValueError("max_estimated_cost_score must be > 0 when provided.")
        if self.preflight_query_execution_seconds_multiplier <= 0.0:
            raise ValueError(
                "preflight_query_execution_seconds_multiplier must be > 0."
            )
        if self.proof_completed_fallback_mode not in {
            "diagnostic_topn",
            "proof_slice",
        }:
            raise ValueError(
                "proof_completed_fallback_mode must be 'diagnostic_topn' or 'proof_slice'."
            )
        if self.proof_completed_fallback_topn_limit < 1:
            raise ValueError("proof_completed_fallback_topn_limit must be >= 1.")
        if self.proof_completed_fallback_slice_promotion_count < 1:
            raise ValueError("proof_completed_fallback_slice_promotion_count must be >= 1.")
        if self.max_completed_repartition_attempts < 1:
            raise ValueError("max_completed_repartition_attempts must be >= 1.")
        if self.max_completed_partition_count < 1:
            raise ValueError("max_completed_partition_count must be >= 1.")
        if self.repartition_skew_safety_multiplier < 1.0:
            raise ValueError(
                "repartition_skew_safety_multiplier must be >= 1.0 so the planner never recommends fewer partitions than the proportional bump."
            )

    def thresholds_dict(self) -> dict[str, int | None]:
        return {
            "max_candidate_promotion_rows": self.max_candidate_promotion_rows,
            "max_candidate_store_sku": self.max_candidate_store_sku,
            "max_window_span_days_total": self.max_window_span_days_total,
            "max_window_span_days_max": self.max_window_span_days_max,
        }

    def cost_guardrail_dict(self) -> dict[str, float | None]:
        return {
            "max_estimated_cost_score": self.max_estimated_cost_score,
            "preflight_query_execution_seconds_multiplier": (
                self.preflight_query_execution_seconds_multiplier
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "run_preflight": self.run_preflight,
            "planner_only": self.planner_only,
            "auto_repartition_completed": self.auto_repartition_completed,
            "max_completed_repartition_attempts": self.max_completed_repartition_attempts,
            "max_completed_partition_count": self.max_completed_partition_count,
            **self.thresholds_dict(),
            **self.cost_guardrail_dict(),
            "proof_completed_fallback_mode": self.proof_completed_fallback_mode,
            "proof_completed_fallback_topn_limit": self.proof_completed_fallback_topn_limit,
            "proof_completed_fallback_slice_promotion_count": (
                self.proof_completed_fallback_slice_promotion_count
            ),
            "default_partition_strategy": self.default_partition_strategy,
            "repartition_skew_safety_multiplier": self.repartition_skew_safety_multiplier,
        }


@dataclass(frozen=True)
class PromotionCompletedPartitionSettings:
    """Governed completed-extraction partition settings.

    `partition_index` is 1-based so the runtime and inspector can surface the
    same human-readable labels that operators use in terminal output.
    """

    strategy: PromotionPartitionStrategy
    partition_count: int
    partition_index: int | None = None

    def __post_init__(self) -> None:
        if self.partition_count < 1:
            raise ValueError("partition_count must be >= 1.")
        if self.partition_index is not None and not 1 <= self.partition_index <= self.partition_count:
            raise ValueError(
                f"partition_index must be between 1 and partition_count ({self.partition_count})."
            )

    def with_partition_index(self, partition_index: int) -> "PromotionCompletedPartitionSettings":
        return PromotionCompletedPartitionSettings(
            strategy=self.strategy,
            partition_count=self.partition_count,
            partition_index=partition_index,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "partition_count": self.partition_count,
            "partition_index": self.partition_index,
        }


@dataclass(frozen=True)
class PromotionCompletedExtractionRuntimeSettings:
    """Execution controls for completed stage-3 landed-batch extraction and resume behavior."""

    enable_landed_batches: bool = True
    batch_row_count: int = 1_000
    completed_sales_history_start_date: date = date(2024, 1, 1)
    enable_chunked_fetch: bool = True
    chunk_row_count: int = 5_000
    resume_completed_partitions: bool = True
    stage_temp_chunk_files: bool = True

    def __post_init__(self) -> None:
        if self.batch_row_count < 1:
            raise ValueError("batch_row_count must be >= 1.")
        if self.chunk_row_count < 1:
            raise ValueError("chunk_row_count must be >= 1.")

    def to_dict(self) -> dict[str, object]:
        return {
            "enable_landed_batches": self.enable_landed_batches,
            "batch_row_count": self.batch_row_count,
            "completed_sales_history_start_date": (
                self.completed_sales_history_start_date.isoformat()
            ),
            "enable_chunked_fetch": self.enable_chunked_fetch,
            "chunk_row_count": self.chunk_row_count,
            "resume_completed_partitions": self.resume_completed_partitions,
            "stage_temp_chunk_files": self.stage_temp_chunk_files,
        }

    @classmethod
    def from_env(
        cls,
        *,
        enable_landed_batches: str | bool | None = None,
        batch_row_count: str | int | None = None,
        completed_sales_history_start_date: str | date | None = None,
        enable_chunked_fetch: str | bool | None = None,
        chunk_row_count: str | int | None = None,
        resume_completed_partitions: str | bool | None = None,
        stage_temp_chunk_files: str | bool | None = None,
        env_file: str | Path | None = None,
    ) -> "PromotionCompletedExtractionRuntimeSettings":
        load_promotions_env(env_file)
        resolved_enable_landed_batches = _resolve_bool_setting(
            _coalesce_env_value(
                str(enable_landed_batches) if enable_landed_batches is not None else None,
                _PROMOTIONS_COMPLETED_EXTRACTION_ENV_MAP["enable_landed_batches"],
            ),
            default=True,
        )
        resolved_batch_row_count = _resolve_int_setting(
            _coalesce_env_value(
                str(batch_row_count) if batch_row_count is not None else None,
                _PROMOTIONS_COMPLETED_EXTRACTION_ENV_MAP["batch_row_count"],
            ),
            minimum=1,
        )
        resolved_completed_sales_history_start_date = _resolve_iso_date_setting(
            completed_sales_history_start_date
            if isinstance(completed_sales_history_start_date, date)
            else _coalesce_env_value(
                (
                    str(completed_sales_history_start_date)
                    if completed_sales_history_start_date is not None
                    else None
                ),
                _PROMOTIONS_COMPLETED_EXTRACTION_ENV_MAP[
                    "completed_sales_history_start_date"
                ],
            )
        )
        resolved_enable_chunked_fetch = _resolve_bool_setting(
            _coalesce_env_value(
                str(enable_chunked_fetch) if enable_chunked_fetch is not None else None,
                _PROMOTIONS_COMPLETED_EXTRACTION_ENV_MAP["enable_chunked_fetch"],
            ),
            default=True,
        )
        resolved_chunk_row_count = _resolve_int_setting(
            _coalesce_env_value(
                str(chunk_row_count) if chunk_row_count is not None else None,
                _PROMOTIONS_COMPLETED_EXTRACTION_ENV_MAP["chunk_row_count"],
            ),
            minimum=1,
        )
        resolved_resume_completed_partitions = _resolve_bool_setting(
            _coalesce_env_value(
                (
                    str(resume_completed_partitions)
                    if resume_completed_partitions is not None
                    else None
                ),
                _PROMOTIONS_COMPLETED_EXTRACTION_ENV_MAP["resume_completed_partitions"],
            ),
            default=True,
        )
        resolved_stage_temp_chunk_files = _resolve_bool_setting(
            _coalesce_env_value(
                str(stage_temp_chunk_files) if stage_temp_chunk_files is not None else None,
                _PROMOTIONS_COMPLETED_EXTRACTION_ENV_MAP["stage_temp_chunk_files"],
            ),
            default=True,
        )
        return cls(
            enable_landed_batches=resolved_enable_landed_batches,
            batch_row_count=resolved_batch_row_count or 1_000,
            completed_sales_history_start_date=(
                resolved_completed_sales_history_start_date or date(2024, 1, 1)
            ),
            enable_chunked_fetch=resolved_enable_chunked_fetch,
            chunk_row_count=resolved_chunk_row_count or 5_000,
            resume_completed_partitions=resolved_resume_completed_partitions,
            stage_temp_chunk_files=resolved_stage_temp_chunk_files,
        )


@dataclass(frozen=True)
class PromotionMssqlSettings:
    """Connection and source-table settings for promotions extraction."""

    server: str
    database: str
    schema: str = "dbo"
    promotion_advice_table: str = "dbo.PromotionAdvice"
    pwlogd_table: str = "dbo.pwlogD"
    odbc_driver: str = "ODBC Driver 18 for SQL Server"
    connect_timeout_seconds: int | None = None
    connect_retry_attempts: int = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS
    connect_retry_backoff_seconds: float = DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS
    query_timeout_seconds: int | None = None
    username: str | None = None
    password: str | None = None
    trust_server_certificate: bool = True
    encrypt: bool = True
    resolution: PromotionMssqlSettingsResolution | None = None

    def safe_summary(self) -> PromotionMssqlSettingsSummary:
        return build_promotions_mssql_settings_summary(self)

    @classmethod
    def from_env(
        cls,
        *,
        promotion_advice_table: str | None = None,
        pwlogd_table: str | None = None,
        env_file: str | Path | None = None,
        server: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        username: str | None = None,
        password: str | None = None,
        odbc_driver: str | None = None,
        connect_timeout_seconds: str | int | None = None,
        connect_retry_attempts: str | int | None = None,
        connect_retry_backoff_seconds: str | float | int | None = None,
        query_timeout_seconds: str | int | None = None,
        encrypt: str | bool | None = None,
        trust_server_certificate: str | bool | None = None,
    ) -> "PromotionMssqlSettings":
        """Build typed SQL settings from `.env` values with optional CLI overrides."""

        loaded_env_file = load_promotions_env(env_file)
        config_source, env_file_path = _config_source_label(env_file, loaded_env_file)
        resolved_server = _resolve_setting_with_source(
            server,
            _PROMOTIONS_MSSQL_ENV_MAP["server"],
            cli_flag=_PROMOTIONS_MSSQL_CLI_FLAG_MAP["server"],
        )
        if not resolved_server.value:
            raise _missing_runtime_setting_error(field_name="server", config_source=config_source)
        resolved_database = _resolve_setting_with_source(
            database,
            _PROMOTIONS_MSSQL_ENV_MAP["database"],
            cli_flag=_PROMOTIONS_MSSQL_CLI_FLAG_MAP["database"],
        )
        if not resolved_database.value:
            raise _missing_runtime_setting_error(field_name="database", config_source=config_source)
        resolved_schema = _resolve_setting_with_source(
            schema,
            _PROMOTIONS_RUNTIME_ENV_MAP["schema"],
            cli_flag=_PROMOTIONS_RUNTIME_CLI_FLAG_MAP["schema"],
            default="dbo",
        )
        resolved_advice_table = _resolve_setting_with_source(
            promotion_advice_table,
            _PROMOTIONS_RUNTIME_ENV_MAP["promotion_advice_table"],
            cli_flag=_PROMOTIONS_RUNTIME_CLI_FLAG_MAP["promotion_advice_table"],
        )
        if not resolved_advice_table.value:
            raise _missing_runtime_setting_error(
                field_name="promotion_advice_table",
                config_source=config_source,
            )
        resolved_username = _resolve_setting_with_source(
            username,
            _PROMOTIONS_MSSQL_ENV_MAP["username"],
            cli_flag=_PROMOTIONS_MSSQL_CLI_FLAG_MAP["username"],
        )
        resolved_password = _resolve_setting_with_source(
            password,
            _PROMOTIONS_MSSQL_ENV_MAP["password"],
            cli_flag=_PROMOTIONS_MSSQL_CLI_FLAG_MAP["password"],
        )
        if bool(resolved_username.value) ^ bool(resolved_password.value):
            raise PromotionRuntimeConfigError(
                (
                    "Incomplete promotions SQL authentication settings. Provide both username and password "
                    f"from {_PROMOTIONS_MSSQL_CLI_FLAG_MAP['username']}/{_PROMOTIONS_MSSQL_CLI_FLAG_MAP['password']} "
                    "or the matching PROMOTIONS_MSSQL_* environment variables."
                ),
                field_name="username/password",
                source=(
                    resolved_username.source
                    if resolved_username.value
                    else resolved_password.source
                ),
                expected_from=(
                    _PROMOTIONS_MSSQL_CLI_FLAG_MAP["username"],
                    *_PROMOTIONS_MSSQL_ENV_MAP["username"],
                    _PROMOTIONS_MSSQL_CLI_FLAG_MAP["password"],
                    *_PROMOTIONS_MSSQL_ENV_MAP["password"],
                ),
                next_action=(
                    "Provide both username and password, or remove the partial SQL-auth setting so the driver can use integrated or external authentication."
                ),
            )
        resolved_driver = _resolve_setting_with_source(
            odbc_driver,
            _PROMOTIONS_MSSQL_ENV_MAP["odbc_driver"],
            cli_flag=_PROMOTIONS_MSSQL_CLI_FLAG_MAP["odbc_driver"],
            default="ODBC Driver 18 for SQL Server",
        )
        resolved_connect_timeout_seconds = _resolve_int_setting_with_source(
            field_name="connect_timeout_seconds",
            override=connect_timeout_seconds,
            default=None,
            minimum=1,
        )
        resolved_connect_retry_attempts = _resolve_int_setting_with_source(
            field_name="connect_retry_attempts",
            override=connect_retry_attempts,
            default=DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_ATTEMPTS,
            minimum=0,
        )
        resolved_connect_retry_backoff_seconds = _resolve_float_setting_with_source(
            field_name="connect_retry_backoff_seconds",
            override=connect_retry_backoff_seconds,
            default=DEFAULT_PROMOTIONS_MSSQL_CONNECT_RETRY_BACKOFF_SECONDS,
            minimum=0.0,
        )
        resolved_query_timeout_seconds = _resolve_int_setting_with_source(
            field_name="query_timeout_seconds",
            override=query_timeout_seconds,
            default=None,
            minimum=1,
        )
        resolved_encrypt = _resolve_bool_setting_with_source(
            field_name="encrypt",
            override=encrypt,
            default=True,
        )
        resolved_trust_server_certificate = _resolve_bool_setting_with_source(
            field_name="trust_server_certificate",
            override=trust_server_certificate,
            default=True,
        )
        resolved_pwlogd_table = _resolve_setting_with_source(
            pwlogd_table,
            _PROMOTIONS_RUNTIME_ENV_MAP["pwlogd_table"],
            cli_flag=_PROMOTIONS_RUNTIME_CLI_FLAG_MAP["pwlogd_table"],
            default="PwlogD",
        )
        field_sources = {
            "server": resolved_server.source,
            "database": resolved_database.source,
            "schema": resolved_schema.source,
            "promotion_advice_table": resolved_advice_table.source,
            "pwlogd_table": resolved_pwlogd_table.source,
            "username": resolved_username.source,
            "password": resolved_password.source,
            "odbc_driver": resolved_driver.source,
            "connect_timeout_seconds": resolved_connect_timeout_seconds.source,
            "connect_retry_attempts": resolved_connect_retry_attempts.source,
            "connect_retry_backoff_seconds": resolved_connect_retry_backoff_seconds.source,
            "query_timeout_seconds": resolved_query_timeout_seconds.source,
            "encrypt": resolved_encrypt.source,
            "trust_server_certificate": resolved_trust_server_certificate.source,
        }
        return cls(
            server=str(resolved_server.value),
            database=str(resolved_database.value),
            schema=str(resolved_schema.value or "dbo"),
            promotion_advice_table=_qualify_table_name(
                str(resolved_advice_table.value),
                str(resolved_schema.value or "dbo"),
            ),
            pwlogd_table=_qualify_table_name(
                str(resolved_pwlogd_table.value or "PwlogD"),
                str(resolved_schema.value or "dbo"),
            ),
            odbc_driver=str(resolved_driver.value or "ODBC Driver 18 for SQL Server"),
            connect_timeout_seconds=(
                int(resolved_connect_timeout_seconds.value)
                if resolved_connect_timeout_seconds.value is not None
                else None
            ),
            connect_retry_attempts=int(resolved_connect_retry_attempts.value or 0),
            connect_retry_backoff_seconds=float(resolved_connect_retry_backoff_seconds.value or 0.0),
            query_timeout_seconds=(
                int(resolved_query_timeout_seconds.value)
                if resolved_query_timeout_seconds.value is not None
                else None
            ),
            username=(str(resolved_username.value) if resolved_username.value is not None else None),
            password=(str(resolved_password.value) if resolved_password.value is not None else None),
            trust_server_certificate=bool(resolved_trust_server_certificate.value),
            encrypt=bool(resolved_encrypt.value),
            resolution=PromotionMssqlSettingsResolution(
                config_source=config_source,
                env_file_path=env_file_path,
                field_sources=field_sources,
            ),
        )


@dataclass(frozen=True)
class PromotionArtifactPaths:
    """Materialized artifact paths for a single promotions workflow root."""

    root: Path = _DEFAULT_ARTIFACT_ROOT
    local_inspection_root: Path | None = _DEFAULT_LOCAL_INSPECTION_ROOT

    @classmethod
    def from_env(
        cls,
        *,
        root: str | Path | None = None,
        local_inspection_root: str | Path | None = None,
        enable_local_inspection_copy: str | bool | None = None,
        env_file: str | Path | None = None,
    ) -> "PromotionArtifactPaths":
        load_promotions_env(env_file)
        resolved_root = _coalesce_env_value(
            str(root) if root is not None else None,
            _PROMOTIONS_RUNTIME_ENV_MAP["artifact_root"],
            default=str(_DEFAULT_ARTIFACT_ROOT),
        )
        local_copy_enabled = _resolve_bool_setting(
            _coalesce_env_value(
                str(enable_local_inspection_copy)
                if enable_local_inspection_copy is not None
                else None,
                _PROMOTIONS_RUNTIME_ENV_MAP["enable_local_inspection_copy"],
            ),
            default=True,
        )
        resolved_local_inspection_root: Path | None = None
        if local_copy_enabled:
            raw_local_inspection_root = _coalesce_env_value(
                str(local_inspection_root) if local_inspection_root is not None else None,
                _PROMOTIONS_RUNTIME_ENV_MAP["local_inspection_root"],
                default=str(_DEFAULT_LOCAL_INSPECTION_ROOT),
            )
            resolved_local_inspection_root = _resolve_artifact_root(
                raw_local_inspection_root or _DEFAULT_LOCAL_INSPECTION_ROOT
            )
        return cls(
            root=_resolve_artifact_root(resolved_root or _DEFAULT_ARTIFACT_ROOT),
            local_inspection_root=resolved_local_inspection_root,
        )

    @property
    def cleaned_data_root(self) -> Path:
        return self.root / "cleaned_data"

    @property
    def training_root(self) -> Path:
        return self.root / "training"

    @property
    def prediction_root(self) -> Path:
        return self.root / "prediction"

    @property
    def artefacts_root(self) -> Path:
        return self.root / "artefacts"

    @property
    def logs_root(self) -> Path:
        return self.root / "logs"

    @property
    def manifests_root(self) -> Path:
        return self.root / "manifests"

    @property
    def inspection_root(self) -> Path:
        return self.root / "inspection"

    @property
    def audit_root(self) -> Path:
        return self.root / "audit"

    @property
    def clients_root(self) -> Path:
        return self.root / "clients"

    @property
    def registries_root(self) -> Path:
        return self.root / "registries"

    @property
    def validation_root(self) -> Path:
        return self.root / "validation"

    @property
    def has_local_inspection_root(self) -> bool:
        return self.local_inspection_root is not None

    @property
    def extracted_root(self) -> Path:
        return self.cleaned_data_root / "extracted"

    @property
    def datasets_root(self) -> Path:
        return self.training_root / "datasets"

    @property
    def models_root(self) -> Path:
        return self.training_root / "models"

    @property
    def scoring_root(self) -> Path:
        return self.prediction_root / "scoring"

    @property
    def prediction_download_root(self) -> Path:
        return self.prediction_root / "store_downloads"

    @property
    def reports_root(self) -> Path:
        return self.artefacts_root / "reports"

    @property
    def cohorts_root(self) -> Path:
        return self.artefacts_root / "cohorts"

    @property
    def decision_surface_root(self) -> Path:
        return self.artefacts_root / "decision_surface"

    @property
    def operational_cycle_root(self) -> Path:
        return self.audit_root / "operational_cycles"

    def manifests_run_root(self, run_id: str) -> Path:
        return self.manifests_root / run_id

    def logs_run_root(self, run_id: str) -> Path:
        return self.logs_root / run_id

    def extracted_run_root(self, run_id: str) -> Path:
        return self.extracted_root / run_id

    def extracted_base_path(self, run_id: str) -> Path:
        return self.extracted_run_root(run_id) / "promotion_base.parquet"

    def extracted_chunk_root(self, run_id: str) -> Path:
        return self.extracted_run_root(run_id) / "chunks"

    def extracted_chunk_path(self, run_id: str, chunk_index: int) -> Path:
        return self.extracted_chunk_root(run_id) / f"chunk_{chunk_index:06d}.parquet"

    def extracted_compaction_temp_path(self, run_id: str) -> Path:
        return self.extracted_run_root(run_id) / "promotion_base.compacting.parquet"

    def extracted_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "extraction_manifest.json"

    def extraction_partition_progress_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "extraction_partition_progress.json"

    def extraction_partition_completion_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "extraction_partition_completion.json"

    def extraction_telemetry_json_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "extraction_telemetry.json"

    def extraction_telemetry_csv_path(self, run_id: str) -> Path:
        return self.logs_run_root(run_id) / "extraction_telemetry.csv"

    def rendered_preflight_sql_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "rendered_preflight_sql.sql"

    def rendered_preflight_sql_parameters_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "rendered_preflight_sql_parameters.json"

    def extraction_preflight_summary_json_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "extraction_preflight_summary.json"

    def extraction_preflight_summary_csv_path(self, run_id: str) -> Path:
        return self.logs_run_root(run_id) / "extraction_preflight_summary.csv"

    def completed_preflight_cost_diagnostic_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "completed_preflight_cost_diagnostic.json"

    def completed_preflight_model_learning_diagnostic_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "completed_preflight_model_learning_diagnostic.json"

    def sql_diagnostics_summary_json_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "sql_diagnostics_summary.json"

    def sql_diagnostics_summary_txt_path(self, run_id: str) -> Path:
        return self.logs_run_root(run_id) / "sql_diagnostics_summary.txt"

    def completed_partition_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "completed_partition_summary.json"

    def partition_rollup_registry_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "partition_rollup_registry.json"

    def stage4_performance_summary_json_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "stage4_performance_summary.json"

    def stage4_performance_summary_csv_path(self, run_id: str) -> Path:
        return self.logs_run_root(run_id) / "stage4_performance_summary.csv"

    def completed_partition_retries_json_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "completed_partition_retries.json"

    def completed_partition_retries_csv_path(self, run_id: str) -> Path:
        return self.logs_run_root(run_id) / "completed_partition_retries.csv"

    def training_dataset_path(self, run_id: str) -> Path:
        return self.datasets_root / run_id / "training_ready.parquet"

    def dataset_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "dataset_manifest.json"

    def model_family_root(self, run_id: str) -> Path:
        return self.models_root / run_id

    def allocation_decision_scoreboard_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "allocation_decision_scoreboard.json"

    def allocation_decision_scoreboard_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "allocation_decision_scoreboard.csv"

    def policy_effectiveness_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_effectiveness_summary.json"

    def policy_effectiveness_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_effectiveness_summary.csv"

    def policy_bucket_ranking_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_bucket_ranking.json"

    def policy_bucket_ranking_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_bucket_ranking.csv"

    def policy_worst_remaining_bucket_residual_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_worst_remaining_bucket_residual.json"

    def policy_worst_remaining_bucket_residual_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_worst_remaining_bucket_residual.csv"

    def policy_replay_effectiveness_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_replay_effectiveness_summary.json"

    def policy_replay_effectiveness_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_replay_effectiveness_summary.csv"

    def policy_replay_bucket_ranking_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_replay_bucket_ranking.json"

    def policy_replay_bucket_ranking_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_replay_bucket_ranking.csv"

    def policy_replay_worst_remaining_bucket_residual_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_replay_worst_remaining_bucket_residual.json"

    def policy_replay_worst_remaining_bucket_residual_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_replay_worst_remaining_bucket_residual.csv"

    def policy_rule_contribution_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_rule_contribution_summary.json"

    def policy_rule_contribution_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_rule_contribution_summary.csv"

    def policy_rule_overlap_matrix_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_rule_overlap_matrix.json"

    def policy_rule_overlap_matrix_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_rule_overlap_matrix.csv"

    def policy_rule_solo_vs_overlap_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_rule_solo_vs_overlap.json"

    def policy_rule_solo_vs_overlap_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_rule_solo_vs_overlap.csv"

    def policy_rule_refinement_candidate_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "policy_rule_refinement_candidate.json"

    def target_contract_comparison_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_comparison_summary.json"

    def target_contract_comparison_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_comparison_summary.csv"

    def target_contract_bucket_ranking_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_bucket_ranking.json"

    def target_contract_bucket_ranking_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_bucket_ranking.csv"

    def target_contract_residual_examples_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_residual_examples.json"

    def target_contract_residual_examples_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_residual_examples.csv"

    def target_contract_row_diagnostics_parquet_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_row_diagnostics.parquet"

    def target_contract_divergence_diagnostics_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_divergence_diagnostics.csv"

    def target_contract_divergence_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_divergence_summary.json"

    def next_target_refinement_candidate_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "next_target_refinement_candidate.json"

    def next_target_promotion_decision_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "next_target_promotion_decision.json"

    def target_mode_comparison_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_comparison_summary.json"

    def target_mode_comparison_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_comparison_summary.csv"

    def target_mode_bucket_ranking_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_bucket_ranking.json"

    def target_mode_bucket_ranking_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_bucket_ranking.csv"

    def target_mode_residual_examples_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_residual_examples.json"

    def target_mode_residual_examples_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_residual_examples.csv"

    def target_contract_promotion_gate_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_promotion_gate.json"

    def target_mode_shadow_model_path(self, run_id: str, model_name: str) -> Path:
        return self.model_family_root(run_id) / f"target_mode_{model_name}.joblib"

    def target_mode_multi_slice_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_multi_slice_summary.json"

    def target_mode_multi_slice_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_multi_slice_summary.csv"

    def target_mode_multi_slice_bucket_ranking_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_multi_slice_bucket_ranking.json"

    def target_mode_multi_slice_bucket_ranking_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_multi_slice_bucket_ranking.csv"

    def target_mode_multi_slice_residual_examples_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_multi_slice_residual_examples.json"

    def target_mode_multi_slice_residual_examples_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_multi_slice_residual_examples.csv"

    def target_mode_shadow_stability_gate_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_shadow_stability_gate.json"

    def target_mode_multi_slice_manifest_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_mode_multi_slice_manifest.json"

    def target_contract_design_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_design_summary.json"

    def target_contract_design_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_design_summary.csv"

    def target_contract_design_bucket_ranking_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_design_bucket_ranking.json"

    def target_contract_design_bucket_ranking_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_design_bucket_ranking.csv"

    def target_contract_design_residual_examples_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_design_residual_examples.json"

    def target_contract_design_residual_examples_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_design_residual_examples.csv"

    def target_contract_design_proposal_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_design_proposal.json"

    def completed_slice_inventory_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "completed_slice_inventory.json"

    def completed_slice_inventory_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "completed_slice_inventory.csv"

    def target_design_repeated_evidence_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_design_repeated_evidence_summary.json"

    def target_design_repeated_evidence_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_design_repeated_evidence_summary.csv"

    def target_design_repeated_evidence_gate_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_design_repeated_evidence_gate.json"

    def target_design_repeated_evidence_residual_examples_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_design_repeated_evidence_residual_examples.json"

    def target_design_repeated_evidence_residual_examples_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_design_repeated_evidence_residual_examples.csv"

    def target_design_repeated_evidence_manifest_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_design_repeated_evidence_manifest.json"

    def target_contract_three_way_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_three_way_summary.json"

    def target_contract_three_way_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_three_way_summary.csv"

    def target_contract_three_way_bucket_ranking_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_three_way_bucket_ranking.json"

    def target_contract_three_way_bucket_ranking_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_three_way_bucket_ranking.csv"

    def target_contract_three_way_residual_examples_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_three_way_residual_examples.json"

    def target_contract_three_way_residual_examples_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_three_way_residual_examples.csv"

    def target_contract_three_way_proposal_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_three_way_proposal.json"

    def target_contract_three_way_manifest_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "target_contract_three_way_manifest.json"

    def promotion_readiness_scoreboard_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "promotion_readiness_scoreboard.json"

    def promotion_readiness_scoreboard_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "promotion_readiness_scoreboard.csv"

    def promotion_readiness_blocker_ranking_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "promotion_readiness_blocker_ranking.json"

    def promotion_readiness_residual_examples_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "promotion_readiness_residual_examples.json"

    def promotion_readiness_decision_packet_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "promotion_readiness_decision_packet.json"

    def promotion_readiness_runtime_manifest_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "promotion_readiness_runtime_manifest.json"

    def weak_slice_repair_summary_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "weak_slice_repair_summary.json"

    def weak_slice_repair_summary_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "weak_slice_repair_summary.csv"

    def weak_slice_repair_plan_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "weak_slice_repair_plan.json"

    def weak_slice_repair_plan_csv_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "weak_slice_repair_plan.csv"

    def weak_slice_repair_residual_examples_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "weak_slice_repair_residual_examples.json"

    def weak_slice_repair_decision_packet_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "weak_slice_repair_decision_packet.json"

    def weak_slice_repair_runtime_manifest_json_path(self, run_id: str) -> Path:
        return self.model_family_root(run_id) / "weak_slice_repair_runtime_manifest.json"

    def scoring_rows_path(self, run_id: str) -> Path:
        return self.scoring_root / run_id / "promotion_row_predictions.parquet"

    def scoring_allocation_decision_diagnostics_csv_path(self, run_id: str) -> Path:
        return self.scoring_root / run_id / "allocation_decision_diagnostics.csv"

    def scoring_allocation_decision_diagnostics_json_path(self, run_id: str) -> Path:
        return self.scoring_root / run_id / "allocation_decision_diagnostics.json"

    def scoring_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "scoring_manifest.json"

    def prediction_report_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "prediction_report_manifest.json"

    def store_prediction_download_path(
        self,
        run_id: str,
        *,
        as_of_date: str | None = None,
    ) -> Path:
        filename = "promotions_store_download_master.csv"
        if as_of_date:
            safe_date = as_of_date.replace("-", "")
            filename = f"promotions_store_download_master_{safe_date}.csv"
        return self.store_prediction_master_root(run_id) / filename

    def store_prediction_download_run_root(self, run_id: str) -> Path:
        return self.prediction_download_root / run_id

    def store_prediction_master_root(self, run_id: str) -> Path:
        return self.store_prediction_download_run_root(run_id) / "System Audit" / "Master"

    def store_prediction_stores_root(self, run_id: str) -> Path:
        return self.store_prediction_download_run_root(run_id) / "System Audit" / "Store Summaries"

    def store_prediction_store_promotions_root(self, run_id: str) -> Path:
        return self.store_prediction_download_run_root(run_id) / "Store Data"

    def store_prediction_manifests_root(self, run_id: str) -> Path:
        return self.store_prediction_download_run_root(run_id) / "Manifests"

    def store_prediction_diagnostics_root(self, run_id: str) -> Path:
        return self.store_prediction_download_run_root(run_id) / "Diagnostics"

    def store_prediction_reconciliation_root(self, run_id: str) -> Path:
        return self.store_prediction_download_run_root(run_id) / "System Audit" / "Reconciliation"

    def store_prediction_validation_root(self, run_id: str) -> Path:
        return self.store_prediction_download_run_root(run_id) / "Validation"

    def store_prediction_store_csv_path(
        self,
        *,
        run_id: str,
        as_of_date: str,
        store_number: str,
    ) -> Path:
        return self.commercial_output_path_builder().store_prediction_summary_csv_path(
            store_number=store_number,
            as_of_date=as_of_date,
        )

    def store_prediction_store_promotion_csv_path(
        self,
        *,
        run_id: str,
        store_number: str,
        promotion_start_date: str,
        promotion_name: str,
        collision_key: str | None = None,
    ) -> Path:
        return self.commercial_output_path_builder().store_promotion_prediction_csv_path(
            store_number=store_number,
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            collision_key=collision_key,
        )

    def store_prediction_store_promotion_artifact_path(
        self,
        *,
        run_id: str,
        store_number: str,
        promotion_start_date: str,
        promotion_name: str,
        artifact_name: str,
        extension: str,
        collision_key: str | None = None,
    ) -> Path:
        return self.commercial_output_path_builder().store_promotion_prediction_artifact_path(
            store_number=store_number,
            promotion_start_date=promotion_start_date,
            promotion_name=promotion_name,
            artifact_name=artifact_name,
            extension=extension,
            collision_key=collision_key,
        )

    def commercial_output_path_builder(self) -> PromotionCommercialOutputPathBuilder:
        return PromotionCommercialOutputPathBuilder(self.root)

    def store_prediction_manifest_path(self, run_id: str) -> Path:
        return self.store_prediction_manifests_root(run_id) / "store_prediction_download_manifest.json"

    def store_prediction_manifest_csv_path(self, run_id: str) -> Path:
        return self.store_prediction_manifests_root(run_id) / "store_prediction_download_manifest.csv"

    def store_prediction_grouping_diagnostics_csv_path(self, run_id: str) -> Path:
        return self.store_prediction_diagnostics_root(run_id) / "store_prediction_download_grouping_diagnostics.csv"

    def store_prediction_grouping_diagnostics_json_path(self, run_id: str) -> Path:
        return self.store_prediction_diagnostics_root(run_id) / "store_prediction_download_grouping_diagnostics.json"

    def store_prediction_allocation_decision_summary_csv_path(self, run_id: str) -> Path:
        return self.store_prediction_diagnostics_root(run_id) / "allocation_decision_summary.csv"

    def store_prediction_allocation_decision_summary_json_path(self, run_id: str) -> Path:
        return self.store_prediction_diagnostics_root(run_id) / "allocation_decision_summary.json"

    def store_prediction_grouping_validation_failures_path(self, run_id: str) -> Path:
        return self.store_prediction_validation_root(run_id) / "store_prediction_download_grouping_validation_failures.json"

    def store_prediction_reconciliation_csv_path(self, run_id: str) -> Path:
        return self.store_prediction_reconciliation_root(run_id) / "store_prediction_reconciliation.csv"

    def commercial_publication_summary_csv_path(self, run_id: str) -> Path:
        return self.store_prediction_manifests_root(run_id) / "publication_summary.csv"

    def promotion_store_client_mapping_path(self) -> Path:
        return self.registries_root / "promotion_store_client_mapping.csv"

    def promotion_gold_standard_acceptance_config_path(self) -> Path:
        return self.registries_root / "promotion_gold_standard_acceptance.csv"

    def pilot_validation_run_root(self, run_id: str) -> Path:
        return self.validation_root / "pilot" / run_id

    def gold_standard_validation_run_root(self, run_id: str) -> Path:
        return self.validation_root / "gold_standard" / run_id

    def validation_manifest_path(self, run_id: str) -> Path:
        return self.validation_root / run_id / "validation_manifest.json"

    def validation_skip_summary_path(self, run_id: str) -> Path:
        return self.validation_root / run_id / "validation_skip_summary.json"

    def pilot_validation_summary_csv_path(self, run_id: str) -> Path:
        return self.pilot_validation_run_root(run_id) / "pilot_validation_summary.csv"

    def pilot_validation_summary_json_path(self, run_id: str) -> Path:
        return self.pilot_validation_run_root(run_id) / "pilot_validation_summary.json"

    def pilot_validation_failures_csv_path(self, run_id: str) -> Path:
        return self.pilot_validation_run_root(run_id) / "pilot_validation_failures.csv"

    def gold_standard_acceptance_results_csv_path(self, run_id: str) -> Path:
        return self.gold_standard_validation_run_root(run_id) / "gold_standard_acceptance_results.csv"

    def gold_standard_acceptance_results_json_path(self, run_id: str) -> Path:
        return self.gold_standard_validation_run_root(run_id) / "gold_standard_acceptance_results.json"

    def prediction_registry_path(self) -> Path:
        return self.registries_root / "promotion_prediction_registry.parquet"

    def client_store_prediction_cycle_root(
        self,
        *,
        client_name: str,
        store_slug: str,
        store_number: str,
        promotion_cycle_id: str,
        promotion_start_date: str,
        promotion_name: str,
        collision_key: str | None = None,
    ) -> Path:
        return self.commercial_output_path_builder().store_promotion_prediction_directory(
            store_number=store_number,
            promotion_start_date=promotion_start_date,
        )

    def reports_run_root(self, run_id: str) -> Path:
        return self.reports_root / run_id

    def cohort_run_root(self, run_id: str) -> Path:
        return self.cohorts_root / run_id

    def decision_surface_run_root(self, run_id: str) -> Path:
        return self.decision_surface_root / run_id

    def inspection_run_root(self, run_id: str) -> Path:
        return self.inspection_root / run_id

    def operational_cycle_run_root(self, run_id: str) -> Path:
        return self.operational_cycle_root / run_id

    def cohort_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "cohort_backtest_manifest.json"

    def cohort_report_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "cohort_report_manifest.json"

    def cohort_backtest_metrics_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "cohort_backtest_metrics.json"

    def decision_surface_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "decision_surface_manifest.json"

    def decision_surface_metrics_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "decision_surface_metrics.json"

    def decision_surface_calibration_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "calibration_summary.json"

    def decision_surface_calibration_thresholds_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "calibration_thresholds.json"

    def decision_surface_diagnostics_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "diagnostics_summary.json"

    def decision_surface_inspection_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "decision_surface_inspection_manifest.json"

    def decision_surface_execution_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "decision_surface_execution_summary.json"

    def operational_cycle_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "operational_cycle_manifest.json"

    def nas_bootstrap_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "nas_bootstrap_summary.json"

    def operator_log_path(self, run_id: str) -> Path:
        return self.logs_run_root(run_id) / "operator_run.log"

    def operator_stage_timings_path(self, run_id: str) -> Path:
        return self.logs_run_root(run_id) / "operator_stage_timings.csv"

    def operator_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "operator_run_summary.json"

    def operator_summary_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "operator_run_summary.csv"

    def commercial_run_outcome_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_run_outcome_summary.json"

    def publication_freshness_diagnostic_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "publication_freshness_diagnostic.json"

    def publish_reconciliation_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "publish_reconciliation_summary.json"

    def commercial_stage_timing_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_stage_timing_summary.json"

    def duplicate_registry_skip_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "duplicate_registry_skip_summary.json"

    def commercial_replay_safety_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_replay_safety_summary.json"

    def commercial_delta_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_delta_summary.json"

    def commercial_delta_top_changes_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_delta_top_changes.csv"

    def commercial_delta_store_summary_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_delta_store_summary.csv"

    def commercial_change_explanations_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_change_explanations.csv"

    def commercial_priority_queue_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_priority_queue.csv"

    def commercial_action_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_action_summary.json"

    def commercial_outcome_attribution_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_outcome_attribution.csv"

    def recommendation_effectiveness_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "recommendation_effectiveness_summary.json"

    def recommendation_effectiveness_by_reason_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "recommendation_effectiveness_by_reason.csv"

    def recommendation_learning_priority_queue_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "recommendation_learning_priority_queue.csv"

    def commercial_policy_calibration_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_policy_calibration_summary.json"

    def commercial_policy_calibration_by_segment_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_policy_calibration_by_segment.csv"

    def commercial_policy_watchlist_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_policy_watchlist.csv"

    def commercial_policy_calibration_brief_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_policy_calibration_brief.md"

    def commercial_policy_simulation_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_policy_simulation_summary.json"

    def commercial_policy_simulation_by_segment_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_policy_simulation_by_segment.csv"

    def commercial_policy_simulation_watchlist_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_policy_simulation_watchlist.csv"

    def commercial_policy_simulation_brief_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_policy_simulation_brief.md"

    def commercial_action_instruction_summary_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_action_instruction_summary.json"

    def commercial_action_priority_queue_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_action_priority_queue.csv"

    def commercial_action_by_segment_csv_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_action_by_segment.csv"

    def commercial_action_instruction_brief_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_action_instruction_brief.md"

    def commercial_operator_brief_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "commercial_operator_brief.md"

    def audit_manifest_path(self, run_id: str) -> Path:
        return self.manifests_run_root(run_id) / "operational_cycle_audit_manifest.json"

    def local_inspection_run_root(self, run_id: str) -> Path:
        return self._require_local_inspection_root() / run_id

    def local_store_prediction_download_path(
        self,
        run_id: str,
        *,
        as_of_date: str | None = None,
    ) -> Path:
        filename = f"{run_id}_store_prediction_download.csv"
        if as_of_date:
            safe_date = as_of_date.replace("-", "")
            filename = f"{run_id}_store_prediction_download_{safe_date}.csv"
        return self.local_inspection_run_root(run_id) / filename

    def local_decision_surface_csv_path(self, run_id: str) -> Path:
        return self.local_inspection_run_root(run_id) / f"{run_id}_decision_surface.csv"

    def local_review_packet_csv_path(self, run_id: str) -> Path:
        return self.local_inspection_run_root(run_id) / f"{run_id}_inspection_review_packet.csv"

    def local_operator_summary_json_path(self, run_id: str) -> Path:
        return self.local_inspection_run_root(run_id) / "operator_run_summary.json"

    def local_operator_summary_csv_path(self, run_id: str) -> Path:
        return self.local_inspection_run_root(run_id) / "operator_run_summary.csv"

    def local_audit_summary_json_path(self, run_id: str) -> Path:
        return self.local_inspection_run_root(run_id) / "operational_cycle_run_summary.json"

    def local_audit_summary_csv_path(self, run_id: str) -> Path:
        return self.local_inspection_run_root(run_id) / "operational_cycle_run_summary.csv"

    def local_run_summary_path(self, run_id: str) -> Path:
        return self.local_inspection_run_root(run_id) / f"{run_id}_run_summary.json"

    def governed_directory_map(self) -> Mapping[str, Path]:
        return {
            "cleaned_data": self.cleaned_data_root,
            "training": self.training_root,
            "prediction": self.prediction_root,
            "artefacts": self.artefacts_root,
            "logs": self.logs_root,
            "manifests": self.manifests_root,
            "inspection": self.inspection_root,
            "audit": self.audit_root,
            "operational_cycles": self.operational_cycle_root,
            "decision_surface": self.decision_surface_root,
            "cohorts": self.cohorts_root,
            "models": self.models_root,
            "datasets": self.datasets_root,
            "scoring": self.scoring_root,
            "reports": self.reports_root,
        }

    def _require_local_inspection_root(self) -> Path:
        if self.local_inspection_root is None:
            raise ValueError("Local inspection output is disabled for this promotions run.")
        return self.local_inspection_root


@dataclass(frozen=True)
class PromotionPipelineSettings:
    """Top-level settings passed through orchestrated promotions workflows."""

    as_of_date: date
    sql: PromotionMssqlSettings
    windows: PromotionWindowSettings = PromotionWindowSettings()
    artifacts: PromotionArtifactPaths = PromotionArtifactPaths()
    completed_promotion_buffer_days: int = 1
    completed_partitioning: PromotionCompletedPartitionSettings | None = None
    completed_extraction_runtime: PromotionCompletedExtractionRuntimeSettings = (
        PromotionCompletedExtractionRuntimeSettings()
    )
    completed_preflight_planner: PromotionCompletedPreflightPlannerSettings = (
        PromotionCompletedPreflightPlannerSettings()
    )

    @classmethod
    def for_runtime_date(
        cls,
        *,
        sql: PromotionMssqlSettings,
        runtime_date: date | None = None,
        windows: PromotionWindowSettings | None = None,
        artifacts: PromotionArtifactPaths | None = None,
        completed_promotion_buffer_days: int = 1,
        completed_partitioning: PromotionCompletedPartitionSettings | None = None,
        completed_extraction_runtime: PromotionCompletedExtractionRuntimeSettings | None = None,
        completed_preflight_planner: PromotionCompletedPreflightPlannerSettings | None = None,
    ) -> "PromotionPipelineSettings":
        current_date = runtime_date or datetime.now(tz=UTC).date()
        return cls(
            as_of_date=current_date,
            sql=sql,
            windows=windows or PromotionWindowSettings(),
            artifacts=artifacts or PromotionArtifactPaths(),
            completed_promotion_buffer_days=completed_promotion_buffer_days,
            completed_partitioning=completed_partitioning,
            completed_extraction_runtime=(
                completed_extraction_runtime or PromotionCompletedExtractionRuntimeSettings()
            ),
            completed_preflight_planner=(
                completed_preflight_planner or PromotionCompletedPreflightPlannerSettings()
            ),
        )