from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_join_spec_pack"
VALIDATION_FOLDER_NAME = "materialized_source_join_key_validation"

VALIDATION_SUMMARY_FILE_NAME = "materialized_source_join_key_validation_summary.csv"
VALIDATION_PLAN_FILE_NAME = "materialized_source_join_key_validation_plan.csv"
VALIDATION_FAILURES_FILE_NAME = "materialized_source_join_key_validation_failures.csv"
VALIDATION_DUPLICATES_FILE_NAME = "materialized_source_join_key_validation_duplicates.csv"

REQUIRED_VALIDATION_FILE_NAMES: tuple[str, ...] = (
    VALIDATION_SUMMARY_FILE_NAME,
    VALIDATION_PLAN_FILE_NAME,
    VALIDATION_FAILURES_FILE_NAME,
    VALIDATION_DUPLICATES_FILE_NAME,
)

JOIN_READY = "JOIN_READY"
JOIN_READY_WITH_DUPLICATE_REVIEW = "JOIN_READY_WITH_DUPLICATE_REVIEW"
JOIN_BLOCKED_LOW_COVERAGE = "JOIN_BLOCKED_LOW_COVERAGE"
JOIN_BLOCKED_ROW_EXPLOSION_RISK = "JOIN_BLOCKED_ROW_EXPLOSION_RISK"
JOIN_BLOCKED_MISSING_KEYS = "JOIN_BLOCKED_MISSING_KEYS"
JOIN_SOURCE_NOT_AVAILABLE = "JOIN_SOURCE_NOT_AVAILABLE"

SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN = "SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN"
SPEC_READY_WITH_QUARANTINE = "SPEC_READY_WITH_QUARANTINE"
SPEC_BLOCKED_DUPLICATE_REVIEW_REQUIRED = "SPEC_BLOCKED_DUPLICATE_REVIEW_REQUIRED"
SPEC_BLOCKED_ROW_EXPLOSION_RISK = "SPEC_BLOCKED_ROW_EXPLOSION_RISK"
SPEC_BLOCKED_LOW_COVERAGE = "SPEC_BLOCKED_LOW_COVERAGE"
SPEC_BLOCKED_MISSING_SOURCE = "SPEC_BLOCKED_MISSING_SOURCE"

SOURCE_ROLE_ACTUAL_OUTCOME = "ACTUAL_OUTCOME"
SOURCE_ROLE_OPERATOR_AUDIT = "OPERATOR_AUDIT"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

SOURCES_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "join_source_type",
    "source_file_path",
    "join_key_columns",
    "match_rate",
    "matched_source_rows",
    "unmatched_source_rows",
    "duplicate_key_count",
    "row_explosion_risk_flag",
    "join_spec_status",
    "execution_allowed_flag",
    "execution_block_reason",
)

KEYS_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "join_source_type",
    "join_key_columns",
    "source_row_count",
    "candidate_source_row_count",
    "matched_source_rows",
    "unmatched_source_rows",
    "match_rate",
    "join_readiness_status",
    "join_spec_status",
    "recommended_for_preview_join_flag",
    "notes",
)

QUARANTINE_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_row_number",
    "store_number",
    "promotion_name_raw",
    "promotion_start_date_raw",
    "sku_number",
    "quarantine_reason",
    "remediation_required",
)

GUARDRAILS_COLUMNS: tuple[str, ...] = (
    "guardrail_name",
    "guardrail_status",
    "enforced_flag",
    "details",
)

EXECUTION_CHECKLIST_COLUMNS: tuple[str, ...] = (
    "checklist_step_number",
    "checklist_step",
    "check_status",
    "blocking_flag",
    "notes",
)

QUARANTINE_FAILURE_INPUT_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "candidate_source_role",
    "candidate_source_path",
    "recommended_join_key",
    "failure_type",
    "source_row_number",
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
    "normalized_join_key",
    "failure_reason",
)

DUPLICATE_INPUT_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "candidate_source_role",
    "candidate_source_path",
    "dataset_role",
    "recommended_join_key",
    "normalized_join_key",
    "duplicate_row_count",
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)


class PromotionsMaterializedSourceJoinSpecPackError(RuntimeError):
    pass


@dataclass(frozen=True)
class JoinSpecSource:
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    join_source_type: str
    source_file_path: str
    join_key_columns: str
    match_rate: float
    matched_source_rows: int
    unmatched_source_rows: int
    duplicate_key_count: int
    row_explosion_risk_flag: int
    join_readiness_status: str
    join_spec_status: str
    execution_allowed_flag: int
    execution_block_reason: str
    candidate_source_row_count: int
    source_row_count: int


@dataclass(frozen=True)
class PromotionsMaterializedSourceJoinSpecPackResult:
    selected_promotion_key: str
    selected_promotion_name: str
    selected_promotion_start_date: str
    selected_promotion_end_date: str
    overall_spec_status: str
    execution_allowed_flag: int
    sources_frame: pd.DataFrame
    keys_frame: pd.DataFrame
    quarantine_rows_frame: pd.DataFrame
    guardrails_frame: pd.DataFrame
    execution_checklist_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceJoinSpecPackArtifacts:
    output_root: str
    summary_csv_path: str
    sources_csv_path: str
    keys_csv_path: str
    quarantine_rows_csv_path: str
    guardrails_csv_path: str
    execution_checklist_csv_path: str
    memo_md_path: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _as_int(value: object) -> int:
    return int(round(float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])))


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceJoinSpecPackError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceJoinSpecPackError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceJoinSpecPackError(f"CSV is empty: {csv_path}")
    return frame


def _has_required_validation_files(validation_root: Path) -> bool:
    return all((validation_root / file_name).exists() for file_name in REQUIRED_VALIDATION_FILE_NAMES)


def _resolve_validation_root(
    *,
    packet_root: Path,
    upstream_root: str | Path | None,
) -> Path:
    if upstream_root is None:
        return packet_root / VALIDATION_FOLDER_NAME
    upstream_root_path = Path(upstream_root)
    candidate_roots = (
        upstream_root_path / VALIDATION_FOLDER_NAME,
        upstream_root_path,
    )
    for candidate_root in candidate_roots:
        if _has_required_validation_files(candidate_root):
            return candidate_root
    candidate_locations = ", ".join(str(path) for path in candidate_roots)
    missing_files = ", ".join(REQUIRED_VALIDATION_FILE_NAMES)
    raise PromotionsMaterializedSourceJoinSpecPackError(
        "--upstream-root was provided, but required join-key validation artifacts were not found. "
        f"Looked under: {candidate_locations}. Expected files: {missing_files}."
    )


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _ensure_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    if frame.empty and list(frame.columns) == []:
        return pd.DataFrame(columns=columns)
    normalized = frame.copy()
    for column in columns:
        if column not in normalized.columns:
            normalized[column] = ""
    return normalized.loc[:, list(columns)]


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceJoinSpecPackError(
            f"Promotion key is not in the expected pipe-delimited format: {promotion_key}"
        )
    _, start_date, end_date, promotion_name = parts
    return promotion_key, start_date, end_date, promotion_name


def _resolve_selected_promotion_key(
    summary_frame: pd.DataFrame,
    plan_frame: pd.DataFrame,
    *,
    promotion_key: str | None,
) -> str:
    if promotion_key:
        return promotion_key
    summary_lookup = _metric_lookup(summary_frame)
    selected = _normalize_text(summary_lookup.get("SELECTED_PROMOTION"))
    if selected:
        return selected
    if plan_frame.empty:
        raise PromotionsMaterializedSourceJoinSpecPackError("Validation plan is empty.")
    return _normalize_text(plan_frame.iloc[0].get("promotion_key"))


def _spec_status_from_join_source(
    *,
    join_readiness_status: str,
    duplicate_risk_flag: int,
    row_explosion_risk_flag: int,
    quarantine_row_count: int,
) -> tuple[str, int, str]:
    if row_explosion_risk_flag > 0 or join_readiness_status == JOIN_BLOCKED_ROW_EXPLOSION_RISK:
        return (
            SPEC_BLOCKED_ROW_EXPLOSION_RISK,
            0,
            "Row explosion risk is present; no preview join may be authored or executed on this source yet.",
        )
    if join_readiness_status == JOIN_SOURCE_NOT_AVAILABLE:
        return (
            SPEC_BLOCKED_MISSING_SOURCE,
            0,
            "The required join source is missing and the diagnostics-only preview join remains blocked.",
        )
    if join_readiness_status in {JOIN_BLOCKED_LOW_COVERAGE, JOIN_BLOCKED_MISSING_KEYS}:
        return (
            SPEC_BLOCKED_LOW_COVERAGE,
            0,
            "Coverage or key completeness is below the minimum threshold for a safe diagnostics-only preview join.",
        )
    if duplicate_risk_flag > 0 or join_readiness_status == JOIN_READY_WITH_DUPLICATE_REVIEW:
        return (
            SPEC_BLOCKED_DUPLICATE_REVIEW_REQUIRED,
            0,
            "Duplicate review is required before any diagnostics-only preview join may be authored or executed.",
        )
    if quarantine_row_count > 0:
        return (
            SPEC_READY_WITH_QUARANTINE,
            1,
            "Preview join may be authored only with the quarantined incomplete-key source rows excluded or remediated first.",
        )
    return (
        SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN,
        1,
        "Preview join may be authored on the recommended key under diagnostics-only guardrails.",
    )


def _overall_spec_status(source_rows: list[JoinSpecSource]) -> tuple[str, int, str]:
    statuses = {row.join_spec_status for row in source_rows}
    if SPEC_BLOCKED_ROW_EXPLOSION_RISK in statuses:
        return (
            SPEC_BLOCKED_ROW_EXPLOSION_RISK,
            0,
            "At least one included source still has row-explosion risk.",
        )
    if SPEC_BLOCKED_MISSING_SOURCE in statuses:
        return (
            SPEC_BLOCKED_MISSING_SOURCE,
            0,
            "At least one required source is missing from the join specification pack.",
        )
    if SPEC_BLOCKED_LOW_COVERAGE in statuses:
        return (
            SPEC_BLOCKED_LOW_COVERAGE,
            0,
            "At least one required source is below the minimum safe coverage threshold.",
        )
    if SPEC_BLOCKED_DUPLICATE_REVIEW_REQUIRED in statuses:
        return (
            SPEC_BLOCKED_DUPLICATE_REVIEW_REQUIRED,
            0,
            "Duplicate review is still required before preview join authoring can proceed.",
        )
    if SPEC_READY_WITH_QUARANTINE in statuses:
        return (
            SPEC_READY_WITH_QUARANTINE,
            1,
            "The preview join contract is ready, but quarantined incomplete-key source rows must stay excluded or be remediated first.",
        )
    return (
        SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN,
        1,
        "The preview join contract is ready under diagnostics-only guardrails.",
    )


def _build_quarantine_rows(
    failures_frame: pd.DataFrame,
    *,
    promotion_key: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
) -> pd.DataFrame:
    selected = failures_frame.loc[
        failures_frame["promotion_key"].astype(str).eq(promotion_key)
        & failures_frame["failure_type"].astype(str).eq("MISSING_SOURCE_KEY_VALUE")
    ].copy()
    if selected.empty:
        return pd.DataFrame(columns=QUARANTINE_COLUMNS)

    selected["_source_row_number"] = selected["source_row_number"].map(_as_int)
    selected = selected.sort_values(by=["_source_row_number", "candidate_source_role"])
    selected = selected.drop_duplicates(
        subset=[
            "_source_row_number",
            "store_number",
            "promotion_start_date",
            "promotion_name",
            "sku_number",
        ],
        keep="first",
    )
    rows = []
    for _, row in selected.iterrows():
        rows.append(
            {
                "promotion_key": promotion_key,
                "promotion_name": promotion_name,
                "promotion_start_date": promotion_start_date,
                "promotion_end_date": promotion_end_date,
                "source_row_number": _as_int(row.get("source_row_number")),
                "store_number": _normalize_text(row.get("store_number")),
                "promotion_name_raw": _normalize_text(row.get("promotion_name")),
                "promotion_start_date_raw": _normalize_text(row.get("promotion_start_date")),
                "sku_number": _normalize_text(row.get("sku_number")),
                "quarantine_reason": _normalize_text(row.get("failure_reason"))
                or "At least one required key field is blank after normalization.",
                "remediation_required": "Populate or remediate the missing join-key fields before any preview join includes this row.",
            }
        )
    return pd.DataFrame(rows, columns=QUARANTINE_COLUMNS)


def _build_source_rows(
    plan_frame: pd.DataFrame,
    duplicates_frame: pd.DataFrame,
    *,
    promotion_key: str,
    quarantine_row_count: int,
) -> list[JoinSpecSource]:
    selected = plan_frame.loc[plan_frame["promotion_key"].astype(str).eq(promotion_key)].copy()
    if selected.empty:
        raise PromotionsMaterializedSourceJoinSpecPackError(
            f"No validation plan rows found for promotion: {promotion_key}"
        )
    rows: list[JoinSpecSource] = []
    for _, row in selected.iterrows():
        join_source_type = _normalize_text(row.get("candidate_source_role"))
        duplicate_rows = duplicates_frame.loc[
            duplicates_frame["promotion_key"].astype(str).eq(promotion_key)
            & duplicates_frame["candidate_source_role"].astype(str).eq(join_source_type)
        ]
        duplicate_key_count = _as_int(row.get("duplicate_key_count_source")) + _as_int(row.get("duplicate_key_count_candidate"))
        duplicate_risk_flag = int(duplicate_key_count > 0 or not duplicate_rows.empty)
        spec_status, execution_allowed_flag, execution_block_reason = _spec_status_from_join_source(
            join_readiness_status=_normalize_text(row.get("join_readiness_status")),
            duplicate_risk_flag=duplicate_risk_flag,
            row_explosion_risk_flag=_as_int(row.get("row_explosion_risk_flag")),
            quarantine_row_count=quarantine_row_count,
        )
        parsed_key, start_date, end_date, promotion_name = _promotion_parts_from_key(promotion_key)
        rows.append(
            JoinSpecSource(
                promotion_key=parsed_key,
                promotion_name=promotion_name,
                promotion_start_date=start_date,
                promotion_end_date=end_date,
                join_source_type=join_source_type,
                source_file_path=_normalize_text(row.get("candidate_source_path")),
                join_key_columns=_normalize_text(row.get("recommended_join_key")),
                match_rate=_as_float(row.get("match_rate")),
                matched_source_rows=_as_int(row.get("matched_source_rows")),
                unmatched_source_rows=_as_int(row.get("unmatched_source_rows")),
                duplicate_key_count=duplicate_key_count,
                row_explosion_risk_flag=_as_int(row.get("row_explosion_risk_flag")),
                join_readiness_status=_normalize_text(row.get("join_readiness_status")),
                join_spec_status=spec_status,
                execution_allowed_flag=execution_allowed_flag,
                execution_block_reason=execution_block_reason,
                candidate_source_row_count=_as_int(row.get("candidate_source_row_count")),
                source_row_count=_as_int(row.get("source_row_count")),
            )
        )
    return rows


def _sources_frame_from_rows(source_rows: list[JoinSpecSource]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "promotion_key": row.promotion_key,
                "promotion_name": row.promotion_name,
                "promotion_start_date": row.promotion_start_date,
                "promotion_end_date": row.promotion_end_date,
                "join_source_type": row.join_source_type,
                "source_file_path": row.source_file_path,
                "join_key_columns": row.join_key_columns,
                "match_rate": round(row.match_rate, 6),
                "matched_source_rows": row.matched_source_rows,
                "unmatched_source_rows": row.unmatched_source_rows,
                "duplicate_key_count": row.duplicate_key_count,
                "row_explosion_risk_flag": row.row_explosion_risk_flag,
                "join_spec_status": row.join_spec_status,
                "execution_allowed_flag": row.execution_allowed_flag,
                "execution_block_reason": row.execution_block_reason,
            }
            for row in source_rows
        ],
        columns=SOURCES_COLUMNS,
    )


def _keys_frame_from_rows(source_rows: list[JoinSpecSource]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "promotion_key": row.promotion_key,
                "join_source_type": row.join_source_type,
                "join_key_columns": row.join_key_columns,
                "source_row_count": row.source_row_count,
                "candidate_source_row_count": row.candidate_source_row_count,
                "matched_source_rows": row.matched_source_rows,
                "unmatched_source_rows": row.unmatched_source_rows,
                "match_rate": round(row.match_rate, 6),
                "join_readiness_status": row.join_readiness_status,
                "join_spec_status": row.join_spec_status,
                "recommended_for_preview_join_flag": int(row.execution_allowed_flag > 0),
                "notes": row.execution_block_reason,
            }
            for row in source_rows
        ],
        columns=KEYS_COLUMNS,
    )


def _guardrails_frame(*, overall_spec_status: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "guardrail_name": "NO_MISSING_ACTUALS_AS_ZERO",
                "guardrail_status": "REQUIRED",
                "enforced_flag": 1,
                "details": "Missing actuals must remain missing and may not be filled with zero during any future preview join.",
            },
            {
                "guardrail_name": "NO_SOURCE_PACKET_MUTATION",
                "guardrail_status": "REQUIRED",
                "enforced_flag": 1,
                "details": "The spec pack may not mutate materialized source packets.",
            },
            {
                "guardrail_name": "ROW_COUNT_CONSERVATION_REQUIRED",
                "guardrail_status": "REQUIRED",
                "enforced_flag": 1,
                "details": "Row count conservation must be checked before and after any future diagnostics-only preview join.",
            },
            {
                "guardrail_name": "NO_PRODUCTION_ORDER_MUTATION",
                "guardrail_status": "REQUIRED",
                "enforced_flag": 1,
                "details": "Production ordering fields must not be changed.",
            },
            {
                "guardrail_name": "NO_STAGE12_MUTATION",
                "guardrail_status": "REQUIRED",
                "enforced_flag": 1,
                "details": "Stage 12 fields must not be changed.",
            },
            {
                "guardrail_name": "FULL_REBUILD_BLOCKED_UNTIL_PREVIEW_VALIDATION",
                "guardrail_status": "BLOCKED" if overall_spec_status in {SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN, SPEC_READY_WITH_QUARANTINE} else "BLOCKED",
                "enforced_flag": 1,
                "details": "Full governed review rebuild remains blocked until diagnostics-only preview join validation passes.",
            },
            {
                "guardrail_name": "TRAINING_BLOCKED",
                "guardrail_status": "BLOCKED",
                "enforced_flag": 1,
                "details": "Training remains blocked.",
            },
        ],
        columns=GUARDRAILS_COLUMNS,
    )


def _check_status(condition: bool) -> str:
    return "CONFIRMED" if condition else "BLOCKED"


def _execution_checklist_frame(
    *,
    promotion_key: str,
    join_key_columns: str,
    actual_source_row: JoinSpecSource | None,
    operator_source_row: JoinSpecSource | None,
    quarantine_row_count: int,
    duplicate_risk_flag: int,
    row_explosion_risk_flag: int,
    overall_execution_allowed_flag: int,
) -> pd.DataFrame:
    checklist_rows = [
        {
            "checklist_step_number": 1,
            "checklist_step": "Confirm selected promotion.",
            "check_status": _check_status(bool(promotion_key)),
            "blocking_flag": 0 if promotion_key else 1,
            "notes": promotion_key,
        },
        {
            "checklist_step_number": 2,
            "checklist_step": "Confirm 4-column join key.",
            "check_status": _check_status(join_key_columns == "store_number + promotion_start_date + promotion_name + sku_number"),
            "blocking_flag": 0 if join_key_columns == "store_number + promotion_start_date + promotion_name + sku_number" else 1,
            "notes": join_key_columns,
        },
        {
            "checklist_step_number": 3,
            "checklist_step": "Confirm actual source path.",
            "check_status": _check_status(bool(actual_source_row and actual_source_row.source_file_path)),
            "blocking_flag": 0 if actual_source_row and actual_source_row.source_file_path else 1,
            "notes": actual_source_row.source_file_path if actual_source_row else "",
        },
        {
            "checklist_step_number": 4,
            "checklist_step": "Confirm operator source path.",
            "check_status": _check_status(bool(operator_source_row and operator_source_row.source_file_path)),
            "blocking_flag": 0 if operator_source_row and operator_source_row.source_file_path else 1,
            "notes": operator_source_row.source_file_path if operator_source_row else "",
        },
        {
            "checklist_step_number": 5,
            "checklist_step": "Quarantine incomplete-key row.",
            "check_status": _check_status(quarantine_row_count >= 0),
            "blocking_flag": 0,
            "notes": f"quarantine_row_count={quarantine_row_count}",
        },
        {
            "checklist_step_number": 6,
            "checklist_step": "Confirm no duplicate key risk.",
            "check_status": _check_status(duplicate_risk_flag == 0),
            "blocking_flag": 1 if duplicate_risk_flag > 0 else 0,
            "notes": f"duplicate_risk_flag={duplicate_risk_flag}",
        },
        {
            "checklist_step_number": 7,
            "checklist_step": "Confirm no row explosion risk.",
            "check_status": _check_status(row_explosion_risk_flag == 0),
            "blocking_flag": 1 if row_explosion_risk_flag > 0 else 0,
            "notes": f"row_explosion_risk_flag={row_explosion_risk_flag}",
        },
        {
            "checklist_step_number": 8,
            "checklist_step": "Confirm missing actuals remain missing.",
            "check_status": "CONFIRMED",
            "blocking_flag": 0,
            "notes": "No preview join may fill missing actuals with zero.",
        },
        {
            "checklist_step_number": 9,
            "checklist_step": "Confirm future preview join will be diagnostics-only.",
            "check_status": "CONFIRMED",
            "blocking_flag": 0,
            "notes": "Any future preview join remains diagnostics-only and does not run the full governed rebuild.",
        },
        {
            "checklist_step_number": 10,
            "checklist_step": "Confirm no production/Stage 12 mutation.",
            "check_status": "CONFIRMED",
            "blocking_flag": 0,
            "notes": "Production ordering fields and Stage 12 fields remain unchanged.",
        },
    ]
    if overall_execution_allowed_flag == 0:
        checklist_rows[8]["notes"] += " Execution remains blocked until the spec blockers are cleared."
    return pd.DataFrame(checklist_rows, columns=EXECUTION_CHECKLIST_COLUMNS)


def _summary_frame(
    *,
    promotion_key: str,
    promotion_name: str,
    promotion_start_date: str,
    promotion_end_date: str,
    overall_spec_status: str,
    execution_allowed_flag: int,
    actual_source_included_flag: int,
    operator_source_included_flag: int,
    join_key_columns: str,
    quarantine_row_count: int,
    duplicate_risk_flag: int,
    row_explosion_risk_flag: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION", promotion_key, "Promotion selected for the diagnostics-only join specification pack."),
            _summary_row("PROMOTION_NAME", promotion_name, "Selected promotion name."),
            _summary_row("PROMOTION_START_DATE", promotion_start_date, "Selected promotion start date."),
            _summary_row("PROMOTION_END_DATE", promotion_end_date, "Selected promotion end date."),
            _summary_row("SPEC_STATUS", overall_spec_status, "Overall diagnostics-only join specification status."),
            _summary_row("EXECUTION_ALLOWED_FLAG", execution_allowed_flag, "Whether a diagnostics-only preview join may be authored and later executed under this spec contract."),
            _summary_row("ACTUAL_SOURCE_INCLUDED_FLAG", actual_source_included_flag, "Whether the actual-outcome source is included in the spec pack."),
            _summary_row("OPERATOR_SOURCE_INCLUDED_FLAG", operator_source_included_flag, "Whether the operator-audit source is included in the spec pack."),
            _summary_row("JOIN_KEY", join_key_columns, "Recommended join key for the included sources."),
            _summary_row("QUARANTINE_ROW_COUNT", quarantine_row_count, "Count of unique source rows that must be quarantined or remediated before any preview join includes them."),
            _summary_row("DUPLICATE_RISK_FLAG", duplicate_risk_flag, "Whether duplicate-key review is still required."),
            _summary_row("ROW_EXPLOSION_RISK_FLAG", row_explosion_risk_flag, "Whether any included source still has row-explosion risk."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _memo_markdown(
    *,
    promotion_key: str,
    promotion_name: str,
    overall_spec_status: str,
    execution_allowed_flag: int,
    join_key_columns: str,
    actual_source_included_flag: int,
    operator_source_included_flag: int,
    quarantine_row_count: int,
    duplicate_risk_flag: int,
    row_explosion_risk_flag: int,
) -> str:
    return "\n".join(
        [
            "# Materialized Source Join Specification Pack",
            "",
            "This is not a join execution.",
            "This is not a rebuild.",
            "This is not training.",
            "This does not mutate source packets.",
            "This does not change production ordering logic.",
            "This does not change Stage 12.",
            "Missing actuals remain missing until a later diagnostics-only preview join is explicitly validated and executed.",
            "",
            "## 1. Selected promotion",
            f"Promotion key: {promotion_key}",
            f"Promotion name: {promotion_name}",
            "",
            "## 2. Spec contract",
            f"Spec status: {overall_spec_status}",
            f"Execution allowed flag: {execution_allowed_flag}",
            f"Join key: {join_key_columns}",
            f"Actual source included: {actual_source_included_flag}",
            f"Operator source included: {operator_source_included_flag}",
            "",
            "## 3. Risks",
            f"Quarantine row count: {quarantine_row_count}",
            f"Duplicate risk flag: {duplicate_risk_flag}",
            f"Row explosion risk flag: {row_explosion_risk_flag}",
            "",
            "## 4. Recommendation",
            (
                "Author the diagnostics-only preview join contract next, but keep the quarantined incomplete-key source rows excluded or remediated first."
                if overall_spec_status == SPEC_READY_WITH_QUARANTINE
                else "Author the diagnostics-only preview join contract next under the documented guardrails."
                if overall_spec_status == SPEC_READY_FOR_DIAGNOSTIC_PREVIEW_JOIN
                else "Do not author or execute the preview join yet; resolve the blocking issues first."
            ),
        ]
    ).strip()


def build_promotions_materialized_source_join_spec_pack(
    *,
    packet_root: str | Path,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceJoinSpecPackResult:
    packet_root_path = Path(packet_root)
    validation_root = _resolve_validation_root(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
    )
    summary_frame = _read_csv(validation_root / VALIDATION_SUMMARY_FILE_NAME)
    plan_frame = _read_csv(validation_root / VALIDATION_PLAN_FILE_NAME)
    failures_frame = _ensure_columns(
        _read_csv(validation_root / VALIDATION_FAILURES_FILE_NAME, allow_empty=True),
        QUARANTINE_FAILURE_INPUT_COLUMNS,
    )
    duplicates_frame = _ensure_columns(
        _read_csv(validation_root / VALIDATION_DUPLICATES_FILE_NAME, allow_empty=True),
        DUPLICATE_INPUT_COLUMNS,
    )

    resolved_promotion_key = _resolve_selected_promotion_key(
        summary_frame,
        plan_frame,
        promotion_key=promotion_key,
    )
    _, promotion_start_date, promotion_end_date, promotion_name = _promotion_parts_from_key(resolved_promotion_key)
    quarantine_rows_frame = _build_quarantine_rows(
        failures_frame,
        promotion_key=resolved_promotion_key,
        promotion_name=promotion_name,
        promotion_start_date=promotion_start_date,
        promotion_end_date=promotion_end_date,
    )
    quarantine_row_count = int(len(quarantine_rows_frame.index))
    source_rows = _build_source_rows(
        plan_frame,
        duplicates_frame,
        promotion_key=resolved_promotion_key,
        quarantine_row_count=quarantine_row_count,
    )
    overall_spec_status, execution_allowed_flag, _ = _overall_spec_status(source_rows)

    actual_source_row = next((row for row in source_rows if row.join_source_type == SOURCE_ROLE_ACTUAL_OUTCOME), None)
    operator_source_row = next((row for row in source_rows if row.join_source_type == SOURCE_ROLE_OPERATOR_AUDIT), None)
    actual_source_included_flag = int(actual_source_row is not None and bool(actual_source_row.source_file_path))
    operator_source_included_flag = int(operator_source_row is not None and bool(operator_source_row.source_file_path))
    duplicate_risk_flag = int(any(row.duplicate_key_count > 0 for row in source_rows))
    row_explosion_risk_flag = int(any(row.row_explosion_risk_flag > 0 for row in source_rows))
    join_key_columns = actual_source_row.join_key_columns if actual_source_row else operator_source_row.join_key_columns if operator_source_row else ""

    sources_frame = _sources_frame_from_rows(source_rows)
    keys_frame = _keys_frame_from_rows(source_rows)
    guardrails_frame = _guardrails_frame(overall_spec_status=overall_spec_status)
    execution_checklist_frame = _execution_checklist_frame(
        promotion_key=resolved_promotion_key,
        join_key_columns=join_key_columns,
        actual_source_row=actual_source_row,
        operator_source_row=operator_source_row,
        quarantine_row_count=quarantine_row_count,
        duplicate_risk_flag=duplicate_risk_flag,
        row_explosion_risk_flag=row_explosion_risk_flag,
        overall_execution_allowed_flag=execution_allowed_flag,
    )
    result_summary_frame = _summary_frame(
        promotion_key=resolved_promotion_key,
        promotion_name=promotion_name,
        promotion_start_date=promotion_start_date,
        promotion_end_date=promotion_end_date,
        overall_spec_status=overall_spec_status,
        execution_allowed_flag=execution_allowed_flag,
        actual_source_included_flag=actual_source_included_flag,
        operator_source_included_flag=operator_source_included_flag,
        join_key_columns=join_key_columns,
        quarantine_row_count=quarantine_row_count,
        duplicate_risk_flag=duplicate_risk_flag,
        row_explosion_risk_flag=row_explosion_risk_flag,
    )
    memo_markdown = _memo_markdown(
        promotion_key=resolved_promotion_key,
        promotion_name=promotion_name,
        overall_spec_status=overall_spec_status,
        execution_allowed_flag=execution_allowed_flag,
        join_key_columns=join_key_columns,
        actual_source_included_flag=actual_source_included_flag,
        operator_source_included_flag=operator_source_included_flag,
        quarantine_row_count=quarantine_row_count,
        duplicate_risk_flag=duplicate_risk_flag,
        row_explosion_risk_flag=row_explosion_risk_flag,
    )

    return PromotionsMaterializedSourceJoinSpecPackResult(
        selected_promotion_key=resolved_promotion_key,
        selected_promotion_name=promotion_name,
        selected_promotion_start_date=promotion_start_date,
        selected_promotion_end_date=promotion_end_date,
        overall_spec_status=overall_spec_status,
        execution_allowed_flag=execution_allowed_flag,
        sources_frame=sources_frame,
        keys_frame=keys_frame,
        quarantine_rows_frame=quarantine_rows_frame,
        guardrails_frame=guardrails_frame,
        execution_checklist_frame=execution_checklist_frame,
        summary_frame=result_summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_join_spec_pack(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
    upstream_root: str | Path | None = None,
    promotion_key: str | None = None,
) -> PromotionsMaterializedSourceJoinSpecPackArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_join_spec_pack(
        packet_root=packet_root_path,
        upstream_root=upstream_root,
        promotion_key=promotion_key,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "materialized_source_join_spec_summary.csv"
    sources_csv_path = output_root_path / "materialized_source_join_spec_sources.csv"
    keys_csv_path = output_root_path / "materialized_source_join_spec_keys.csv"
    quarantine_rows_csv_path = output_root_path / "materialized_source_join_spec_quarantine_rows.csv"
    guardrails_csv_path = output_root_path / "materialized_source_join_spec_guardrails.csv"
    execution_checklist_csv_path = output_root_path / "materialized_source_join_spec_execution_checklist.csv"
    memo_md_path = output_root_path / "materialized_source_join_spec_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.sources_frame.to_csv(sources_csv_path, index=False)
    result.keys_frame.to_csv(keys_csv_path, index=False)
    result.quarantine_rows_frame.to_csv(quarantine_rows_csv_path, index=False)
    result.guardrails_frame.to_csv(guardrails_csv_path, index=False)
    result.execution_checklist_frame.to_csv(execution_checklist_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceJoinSpecPackArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        sources_csv_path=str(sources_csv_path),
        keys_csv_path=str(keys_csv_path),
        quarantine_rows_csv_path=str(quarantine_rows_csv_path),
        guardrails_csv_path=str(guardrails_csv_path),
        execution_checklist_csv_path=str(execution_checklist_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a diagnostics-only join specification pack from the validated materialized-source join contract."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--promotion-key")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_join_spec_pack(
        packet_root=args.packet_root,
        output_root=args.output_root,
        upstream_root=args.upstream_root,
        promotion_key=args.promotion_key,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion", _normalize_text(metrics.get("SELECTED_PROMOTION", "")))
    print("spec_status", _normalize_text(metrics.get("SPEC_STATUS", "")))
    print("execution_allowed_flag", _normalize_text(metrics.get("EXECUTION_ALLOWED_FLAG", 0)))
    print("actual_source_included", _normalize_text(metrics.get("ACTUAL_SOURCE_INCLUDED_FLAG", 0)))
    print("operator_source_included", _normalize_text(metrics.get("OPERATOR_SOURCE_INCLUDED_FLAG", 0)))
    print("join_key", _normalize_text(metrics.get("JOIN_KEY", "")))
    print("quarantine_row_count", _normalize_text(metrics.get("QUARANTINE_ROW_COUNT", 0)))
    print("duplicate_risk", _normalize_text(metrics.get("DUPLICATE_RISK_FLAG", 0)))
    print("row_explosion_risk", _normalize_text(metrics.get("ROW_EXPLOSION_RISK_FLAG", 0)))
    print("materialized_source_join_spec_summary", artifacts.summary_csv_path)
    print("materialized_source_join_spec_sources", artifacts.sources_csv_path)
    print("materialized_source_join_spec_keys", artifacts.keys_csv_path)
    print("materialized_source_join_spec_quarantine_rows", artifacts.quarantine_rows_csv_path)
    print("materialized_source_join_spec_guardrails", artifacts.guardrails_csv_path)
    print("materialized_source_join_spec_execution_checklist", artifacts.execution_checklist_csv_path)
    print("materialized_source_join_spec_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())