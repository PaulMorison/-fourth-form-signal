from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_rebuild_queue"
READINESS_AUDIT_FOLDER_NAME = "materialized_source_readiness_audit"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"

QUEUE_READY_TO_EXECUTE = "READY_TO_EXECUTE"
QUEUE_BLOCKED_MISSING_JOIN_SOURCE = "BLOCKED_MISSING_JOIN_SOURCE"
QUEUE_BLOCKED_MISSING_SCHEMA_MAPPING = "BLOCKED_MISSING_SCHEMA_MAPPING"
QUEUE_WAITING_FOR_PRIOR_STEP = "WAITING_FOR_PRIOR_STEP"
QUEUE_VALIDATION_REQUIRED = "VALIDATION_REQUIRED"
QUEUE_NOT_REQUIRED = "NOT_REQUIRED"

ACTION_JOIN_ACTUAL_OUTCOME_SOURCE = "JOIN_ACTUAL_OUTCOME_SOURCE"
ACTION_JOIN_OPERATOR_AUDIT_SOURCE = "JOIN_OPERATOR_AUDIT_SOURCE"
ACTION_MAP_CANONICAL_REVIEW_SCHEMA = "MAP_CANONICAL_REVIEW_SCHEMA"
ACTION_VALIDATE_JOIN_KEY_COVERAGE = "VALIDATE_JOIN_KEY_COVERAGE"
ACTION_VALIDATE_NO_ACTUALS_AS_ZERO = "VALIDATE_NO_ACTUALS_AS_ZERO"
ACTION_VALIDATE_ROW_COUNT_CONSERVATION = "VALIDATE_ROW_COUNT_CONSERVATION"
ACTION_VALIDATE_PRODUCTION_AND_STAGE12_GUARDRAILS = (
    "VALIDATE_PRODUCTION_AND_STAGE12_GUARDRAILS"
)
ACTION_MARK_READY_FOR_GOVERNED_REVIEW_REBUILD = (
    "MARK_READY_FOR_GOVERNED_REVIEW_REBUILD"
)

JOIN_ROLE_ACTUAL_OUTCOME = "ACTUAL_OUTCOME"
JOIN_ROLE_OPERATOR_AUDIT = "OPERATOR_AUDIT"
JOIN_ROLE_INSPECTION_REVIEW_PACKET = "INSPECTION_REVIEW_PACKET"
JOIN_ROLE_UNKNOWN = "UNKNOWN"

QUEUE_ACTION_ORDER: tuple[str, ...] = (
    ACTION_VALIDATE_JOIN_KEY_COVERAGE,
    ACTION_JOIN_ACTUAL_OUTCOME_SOURCE,
    ACTION_JOIN_OPERATOR_AUDIT_SOURCE,
    ACTION_MAP_CANONICAL_REVIEW_SCHEMA,
    ACTION_VALIDATE_NO_ACTUALS_AS_ZERO,
    ACTION_VALIDATE_ROW_COUNT_CONSERVATION,
    ACTION_VALIDATE_PRODUCTION_AND_STAGE12_GUARDRAILS,
    ACTION_MARK_READY_FOR_GOVERNED_REVIEW_REBUILD,
)

QUEUE_ROWS_COLUMNS: tuple[str, ...] = (
    "queue_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "required_action",
    "action_status",
    "blocking_flag",
    "source_file_path",
    "candidate_join_source_path",
    "join_key_columns",
    "missing_fields_addressed",
    "guardrail_check_required",
    "expected_output",
    "recommended_next_step",
    "reason",
)

BY_PROMOTION_COLUMNS: tuple[str, ...] = (
    "promotion_priority_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "queue_row_count",
    "actual_outcome_join_required_flag",
    "actual_outcome_join_candidate_flag",
    "operator_audit_join_required_flag",
    "operator_audit_join_candidate_flag",
    "schema_mapping_required_flag",
    "blocked_flag",
    "potentially_ready_after_joins_flag",
    "first_required_action",
    "source_file_path",
    "recommended_next_step",
    "reason",
)

JOIN_EXECUTION_PLAN_COLUMNS: tuple[str, ...] = (
    "promotion_priority_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "required_action",
    "action_status",
    "blocking_flag",
    "source_file_path",
    "candidate_join_source_path",
    "join_key_columns",
    "missing_fields_addressed",
    "expected_output",
    "recommended_next_step",
    "reason",
)

SCHEMA_MAPPING_PLAN_COLUMNS: tuple[str, ...] = (
    "promotion_priority_rank",
    "promotion_key",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "source_file_path",
    "source_manifest_path",
    "manifest_missing_canonical_fields",
    "missing_fields_addressed",
    "action_status",
    "blocking_flag",
    "expected_output",
    "recommended_next_step",
    "reason",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)


class PromotionsMaterializedSourceRebuildQueueError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionQueueContext:
    priority_rank: int
    promotion_key: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    source_file_path: str
    source_manifest_path: str
    join_key_columns: tuple[str, ...]
    actual_join_required_flag: int
    actual_join_candidate_flag: int
    operator_join_required_flag: int
    operator_join_candidate_flag: int
    schema_mapping_required_flag: int
    blocked_actual_join_flag: int
    blocked_operator_join_flag: int
    blocked_schema_mapping_flag: int
    blocked_flag: int
    potentially_ready_after_joins_flag: int
    missing_actual_outcome_fields: tuple[str, ...]
    missing_prediction_action_fields: tuple[str, ...]
    missing_identity_fields: tuple[str, ...]
    missing_economics_fields: tuple[str, ...]
    missing_fields_for_schema_mapping: tuple[str, ...]
    critical_missing_column_count: int
    production_guardrail_failure_flag: int
    stage12_guardrail_failure_flag: int
    actual_candidate_join_sources: tuple[str, ...]
    operator_candidate_join_sources: tuple[str, ...]
    manifest_missing_canonical_fields: tuple[str, ...]
    manifest_downstream_full_packet_reason: str
    recommended_next_step: str
    reason: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceRebuildQueueResult:
    queue_rows_frame: pd.DataFrame
    by_promotion_frame: pd.DataFrame
    join_execution_plan_frame: pd.DataFrame
    schema_mapping_plan_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceRebuildQueueArtifacts:
    output_root: str
    queue_rows_csv_path: str
    by_promotion_csv_path: str
    join_execution_plan_csv_path: str
    schema_mapping_plan_csv_path: str
    summary_csv_path: str
    memo_md_path: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()


def _parse_date_text(value: object) -> pd.Timestamp:
    text = _normalize_text(value)
    if not text:
        return pd.NaT
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
        return pd.to_datetime(text, dayfirst=True, errors="coerce")
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", text):
        return pd.to_datetime(text, format="%Y/%m/%d", errors="coerce")
    return pd.to_datetime(text, errors="coerce")


def _as_int(value: object) -> int:
    return int(round(float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])))


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceRebuildQueueError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceRebuildQueueError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceRebuildQueueError(f"CSV is empty: {csv_path}")
    return frame


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _parse_list(value: object) -> tuple[str, ...]:
    normalized = _normalize_text(value)
    if not normalized:
        return ()
    values = [item.strip() for item in normalized.split(";")]
    deduped: list[str] = []
    for item in values:
        if not item or item in deduped:
            continue
        deduped.append(item)
    return tuple(deduped)


def _format_list(values: Iterable[str]) -> str:
    deduped: list[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in deduped:
            continue
        deduped.append(normalized)
    return "; ".join(deduped)


def _candidate_role_priority(source_role: str, *, for_operator_join: bool) -> int:
    if for_operator_join:
        priority = {
            JOIN_ROLE_OPERATOR_AUDIT: 0,
            JOIN_ROLE_INSPECTION_REVIEW_PACKET: 1,
            JOIN_ROLE_ACTUAL_OUTCOME: 2,
            JOIN_ROLE_UNKNOWN: 3,
        }
    else:
        priority = {
            JOIN_ROLE_ACTUAL_OUTCOME: 0,
            JOIN_ROLE_INSPECTION_REVIEW_PACKET: 1,
            JOIN_ROLE_OPERATOR_AUDIT: 2,
            JOIN_ROLE_UNKNOWN: 3,
        }
    return priority.get(source_role, 4)


def _candidate_lookup(candidate_join_sources_frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for row in candidate_join_sources_frame.to_dict(orient="records"):
        source_path = _normalize_text(row.get("source_path"))
        if not source_path:
            continue
        lookup[source_path] = row
    return lookup


def _ordered_candidate_paths(
    candidate_paths: Sequence[str],
    *,
    candidate_lookup: dict[str, dict[str, object]],
    for_operator_join: bool,
) -> tuple[str, ...]:
    decorated: list[tuple[int, int, str]] = []
    for candidate_path in candidate_paths:
        row = candidate_lookup.get(candidate_path, {})
        decorated.append(
            (
                _candidate_role_priority(_normalize_text(row.get("source_role")), for_operator_join=for_operator_join),
                -_as_int(row.get("matching_promotion_count")),
                candidate_path,
            )
        )
    decorated.sort()
    return tuple(candidate_path for _, _, candidate_path in decorated)


def _join_keys_for_candidates(
    candidate_paths: Sequence[str],
    *,
    candidate_lookup: dict[str, dict[str, object]],
    fallback_join_keys: Sequence[str],
) -> tuple[str, ...]:
    join_keys: list[str] = []
    for candidate_path in candidate_paths:
        row = candidate_lookup.get(candidate_path, {})
        for key_name in _parse_list(row.get("possible_join_keys")):
            if key_name not in join_keys:
                join_keys.append(key_name)
    if not join_keys:
        for key_name in fallback_join_keys:
            if key_name not in join_keys:
                join_keys.append(key_name)
    return tuple(join_keys)


def _manifest_lookup(packet_root: Path) -> dict[str, dict[str, object]]:
    materialized_root = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME
    manifests: dict[str, dict[str, object]] = {}
    for manifest_path in sorted(materialized_root.glob("*/promotion_source_manifest.csv")):
        frame = _read_csv(manifest_path)
        row = frame.iloc[0].to_dict() if not frame.empty else {}
        manifests[manifest_path.parent.name] = {
            **row,
            "source_manifest_path": str(manifest_path),
        }
    return manifests


def _priority_sort_key(context: PromotionQueueContext) -> tuple[int, int, int, int, str]:
    start_timestamp = _parse_date_text(context.promotion_start_date)
    date_ordinal = -int(start_timestamp.value) if not pd.isna(start_timestamp) else 0
    return (
        -context.actual_join_candidate_flag,
        -context.operator_join_candidate_flag,
        context.critical_missing_column_count,
        date_ordinal,
        context.promotion_key,
    )


def _promotion_first_required_action(context: PromotionQueueContext) -> str:
    if context.actual_join_required_flag or context.operator_join_required_flag:
        if context.blocked_actual_join_flag:
            return ACTION_JOIN_ACTUAL_OUTCOME_SOURCE
        if context.blocked_operator_join_flag:
            return ACTION_JOIN_OPERATOR_AUDIT_SOURCE
        return ACTION_VALIDATE_JOIN_KEY_COVERAGE
    if context.schema_mapping_required_flag:
        return ACTION_MAP_CANONICAL_REVIEW_SCHEMA
    return ACTION_VALIDATE_PRODUCTION_AND_STAGE12_GUARDRAILS


def _promotion_recommended_next_step(
    *,
    actual_join_required_flag: int,
    actual_candidate_join_sources: Sequence[str],
    operator_join_required_flag: int,
    operator_candidate_join_sources: Sequence[str],
    schema_mapping_required_flag: int,
) -> str:
    if actual_join_required_flag and not actual_candidate_join_sources:
        return (
            "Locate a governed actual-outcome source for the promotion keys before any schema mapping or rebuild work."
        )
    if operator_join_required_flag and not operator_candidate_join_sources:
        return (
            "Locate a governed operator-audit source for the promotion keys before any schema mapping or rebuild work."
        )
    if actual_join_required_flag or operator_join_required_flag:
        return (
            "Validate join key coverage first, then author diagnostics-only join specs without running the joins yet."
        )
    if schema_mapping_required_flag:
        return (
            "Author the canonical review-schema mapping for this materialized source packet before any governed rebuild is attempted."
        )
    return "Run queue validations and then mark the promotion ready for governed review rebuild."


def _promotion_reason(
    *,
    actual_join_required_flag: int,
    actual_candidate_join_sources: Sequence[str],
    operator_join_required_flag: int,
    operator_candidate_join_sources: Sequence[str],
    schema_mapping_required_flag: int,
    missing_actual_outcome_fields: Sequence[str],
    missing_prediction_action_fields: Sequence[str],
    manifest_downstream_full_packet_reason: str,
) -> str:
    fragments: list[str] = []
    if actual_join_required_flag:
        if actual_candidate_join_sources:
            fragments.append(
                "Actual outcome fields remain missing until a diagnostics-only join plan is executed."
            )
        else:
            fragments.append(
                "Actual outcome fields are missing and no candidate actual-outcome join source was found."
            )
    if operator_join_required_flag:
        if operator_candidate_join_sources:
            fragments.append(
                "Operator-audit evidence can be staged from a matched diagnostics source once join key coverage is validated."
            )
        else:
            fragments.append(
                "Operator-audit evidence is required but no matched operator join source was found."
            )
    if schema_mapping_required_flag:
        fragments.append(
            "Canonical governed review-schema mapping is still required before a full review rebuild can run."
        )
    if missing_actual_outcome_fields:
        fragments.append(
            "Missing actuals remain missing and must not be converted into zero sales."
        )
    if missing_prediction_action_fields:
        fragments.append(
            "Prediction/action gaps still need either join support or explicit canonical mapping."
        )
    if manifest_downstream_full_packet_reason:
        fragments.append(manifest_downstream_full_packet_reason)
    return " ".join(fragment for fragment in fragments if fragment)


def _build_contexts(
    *,
    packet_root: Path,
    readiness_rows_frame: pd.DataFrame,
    candidate_join_sources_frame: pd.DataFrame,
) -> list[PromotionQueueContext]:
    manifests = _manifest_lookup(packet_root)
    candidate_lookup = _candidate_lookup(candidate_join_sources_frame)
    contexts: list[PromotionQueueContext] = []
    for row in readiness_rows_frame.to_dict(orient="records"):
        promotion_folder_name = _normalize_text(row.get("promotion_folder_name"))
        manifest_row = manifests.get(promotion_folder_name, {})
        actual_missing_fields = _parse_list(row.get("missing_actual_outcome_fields"))
        prediction_missing_fields = _parse_list(row.get("prediction_action_columns_missing"))
        identity_missing_fields = _parse_list(row.get("identity_columns_missing"))
        economics_missing_fields = _parse_list(row.get("economics_columns_missing"))
        actual_candidate_paths = _ordered_candidate_paths(
            _parse_list(row.get("candidate_actual_join_sources")),
            candidate_lookup=candidate_lookup,
            for_operator_join=False,
        )
        operator_candidate_paths = _ordered_candidate_paths(
            _parse_list(row.get("candidate_operator_join_sources")),
            candidate_lookup=candidate_lookup,
            for_operator_join=True,
        )
        actual_join_required_flag = int(
            bool(actual_missing_fields) or _as_int(row.get("actual_outcome_fields_present_but_blank_count")) > 0
        )
        operator_join_required_flag = int(_as_int(row.get("needs_operator_audit_join_flag")) > 0)
        schema_mapping_required_flag = int(_as_int(row.get("needs_canonical_review_schema_mapping_flag")) > 0)
        blocked_actual_join_flag = int(actual_join_required_flag and not actual_candidate_paths)
        blocked_operator_join_flag = int(
            operator_join_required_flag and not operator_candidate_paths
        )
        blocked_schema_mapping_flag = int(schema_mapping_required_flag)
        blocked_flag = int(
            blocked_actual_join_flag or blocked_operator_join_flag or blocked_schema_mapping_flag
        )
        potentially_ready_after_joins_flag = int(
            not blocked_actual_join_flag and not blocked_operator_join_flag
        )
        missing_fields_for_schema_mapping = (
            identity_missing_fields
            + prediction_missing_fields
            + economics_missing_fields
            + actual_missing_fields
        )
        source_file_path = _normalize_text(manifest_row.get("source_file_path")) or _normalize_text(
            row.get("source_file_path")
        )
        contexts.append(
            PromotionQueueContext(
                priority_rank=0,
                promotion_key=_normalize_text(row.get("promotion_key")),
                promotion_name=_normalize_text(row.get("promotion_name")),
                promotion_start_date=_normalize_text(row.get("promotion_start_date")),
                promotion_end_date=_normalize_text(row.get("promotion_end_date")),
                source_file_path=source_file_path,
                source_manifest_path=_normalize_text(manifest_row.get("source_manifest_path")),
                join_key_columns=_parse_list(row.get("join_keys_available")),
                actual_join_required_flag=actual_join_required_flag,
                actual_join_candidate_flag=int(bool(actual_candidate_paths)),
                operator_join_required_flag=operator_join_required_flag,
                operator_join_candidate_flag=int(bool(operator_candidate_paths)),
                schema_mapping_required_flag=schema_mapping_required_flag,
                blocked_actual_join_flag=blocked_actual_join_flag,
                blocked_operator_join_flag=blocked_operator_join_flag,
                blocked_schema_mapping_flag=blocked_schema_mapping_flag,
                blocked_flag=blocked_flag,
                potentially_ready_after_joins_flag=potentially_ready_after_joins_flag,
                missing_actual_outcome_fields=actual_missing_fields,
                missing_prediction_action_fields=prediction_missing_fields,
                missing_identity_fields=identity_missing_fields,
                missing_economics_fields=economics_missing_fields,
                missing_fields_for_schema_mapping=missing_fields_for_schema_mapping,
                critical_missing_column_count=_as_int(row.get("critical_missing_column_count")),
                production_guardrail_failure_flag=int(_as_int(row.get("production_order_changes")) > 0),
                stage12_guardrail_failure_flag=int(_as_int(row.get("stage_12_changes")) > 0),
                actual_candidate_join_sources=actual_candidate_paths,
                operator_candidate_join_sources=operator_candidate_paths,
                manifest_missing_canonical_fields=_parse_list(
                    manifest_row.get("missing_canonical_fields")
                ),
                manifest_downstream_full_packet_reason=_normalize_text(
                    manifest_row.get("downstream_full_packet_reason")
                ),
                recommended_next_step="",
                reason="",
            )
        )

    ordered_contexts = sorted(contexts, key=_priority_sort_key)
    finalized_contexts: list[PromotionQueueContext] = []
    for index, context in enumerate(ordered_contexts, start=1):
        recommended_next_step = _promotion_recommended_next_step(
            actual_join_required_flag=context.actual_join_required_flag,
            actual_candidate_join_sources=context.actual_candidate_join_sources,
            operator_join_required_flag=context.operator_join_required_flag,
            operator_candidate_join_sources=context.operator_candidate_join_sources,
            schema_mapping_required_flag=context.schema_mapping_required_flag,
        )
        reason = _promotion_reason(
            actual_join_required_flag=context.actual_join_required_flag,
            actual_candidate_join_sources=context.actual_candidate_join_sources,
            operator_join_required_flag=context.operator_join_required_flag,
            operator_candidate_join_sources=context.operator_candidate_join_sources,
            schema_mapping_required_flag=context.schema_mapping_required_flag,
            missing_actual_outcome_fields=context.missing_actual_outcome_fields,
            missing_prediction_action_fields=context.missing_prediction_action_fields,
            manifest_downstream_full_packet_reason=context.manifest_downstream_full_packet_reason,
        )
        finalized_contexts.append(
            PromotionQueueContext(
                priority_rank=index,
                promotion_key=context.promotion_key,
                promotion_name=context.promotion_name,
                promotion_start_date=context.promotion_start_date,
                promotion_end_date=context.promotion_end_date,
                source_file_path=context.source_file_path,
                source_manifest_path=context.source_manifest_path,
                join_key_columns=context.join_key_columns,
                actual_join_required_flag=context.actual_join_required_flag,
                actual_join_candidate_flag=context.actual_join_candidate_flag,
                operator_join_required_flag=context.operator_join_required_flag,
                operator_join_candidate_flag=context.operator_join_candidate_flag,
                schema_mapping_required_flag=context.schema_mapping_required_flag,
                blocked_actual_join_flag=context.blocked_actual_join_flag,
                blocked_operator_join_flag=context.blocked_operator_join_flag,
                blocked_schema_mapping_flag=context.blocked_schema_mapping_flag,
                blocked_flag=context.blocked_flag,
                potentially_ready_after_joins_flag=context.potentially_ready_after_joins_flag,
                missing_actual_outcome_fields=context.missing_actual_outcome_fields,
                missing_prediction_action_fields=context.missing_prediction_action_fields,
                missing_identity_fields=context.missing_identity_fields,
                missing_economics_fields=context.missing_economics_fields,
                missing_fields_for_schema_mapping=context.missing_fields_for_schema_mapping,
                critical_missing_column_count=context.critical_missing_column_count,
                production_guardrail_failure_flag=context.production_guardrail_failure_flag,
                stage12_guardrail_failure_flag=context.stage12_guardrail_failure_flag,
                actual_candidate_join_sources=context.actual_candidate_join_sources,
                operator_candidate_join_sources=context.operator_candidate_join_sources,
                manifest_missing_canonical_fields=context.manifest_missing_canonical_fields,
                manifest_downstream_full_packet_reason=context.manifest_downstream_full_packet_reason,
                recommended_next_step=recommended_next_step,
                reason=reason,
            )
        )
    return finalized_contexts


def _queue_row(
    *,
    context: PromotionQueueContext,
    required_action: str,
    action_status: str,
    blocking_flag: int,
    candidate_join_source_path: str,
    join_key_columns: Sequence[str],
    missing_fields_addressed: Sequence[str],
    guardrail_check_required: int,
    expected_output: str,
    reason: str,
) -> dict[str, object]:
    return {
        "queue_rank": 0,
        "promotion_key": context.promotion_key,
        "promotion_name": context.promotion_name,
        "promotion_start_date": context.promotion_start_date,
        "promotion_end_date": context.promotion_end_date,
        "required_action": required_action,
        "action_status": action_status,
        "blocking_flag": blocking_flag,
        "source_file_path": context.source_file_path,
        "candidate_join_source_path": candidate_join_source_path,
        "join_key_columns": _format_list(join_key_columns),
        "missing_fields_addressed": _format_list(missing_fields_addressed),
        "guardrail_check_required": guardrail_check_required,
        "expected_output": expected_output,
        "recommended_next_step": context.recommended_next_step,
        "reason": reason,
    }


def _build_queue_rows_for_promotion(
    *,
    context: PromotionQueueContext,
    candidate_lookup: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    primary_actual_source = context.actual_candidate_join_sources[0] if context.actual_candidate_join_sources else ""
    primary_operator_source = context.operator_candidate_join_sources[0] if context.operator_candidate_join_sources else ""
    actual_join_keys = _join_keys_for_candidates(
        context.actual_candidate_join_sources,
        candidate_lookup=candidate_lookup,
        fallback_join_keys=context.join_key_columns,
    )
    operator_join_keys = _join_keys_for_candidates(
        context.operator_candidate_join_sources,
        candidate_lookup=candidate_lookup,
        fallback_join_keys=context.join_key_columns,
    )
    queue_rows: list[dict[str, object]] = []

    if context.actual_join_required_flag or context.operator_join_required_flag:
        validate_join_status = (
            QUEUE_BLOCKED_MISSING_JOIN_SOURCE
            if context.blocked_actual_join_flag or context.blocked_operator_join_flag
            else QUEUE_READY_TO_EXECUTE
        )
        validate_join_blocking = int(validate_join_status.startswith("BLOCKED"))
    else:
        validate_join_status = QUEUE_NOT_REQUIRED
        validate_join_blocking = 0
    queue_rows.append(
        _queue_row(
            context=context,
            required_action=ACTION_VALIDATE_JOIN_KEY_COVERAGE,
            action_status=validate_join_status,
            blocking_flag=validate_join_blocking,
            candidate_join_source_path=_format_list(
                (*context.actual_candidate_join_sources, *context.operator_candidate_join_sources)
            ),
            join_key_columns=(*actual_join_keys, *operator_join_keys),
            missing_fields_addressed=(
                *context.missing_actual_outcome_fields,
                *context.missing_prediction_action_fields,
            ),
            guardrail_check_required=1,
            expected_output=(
                "Diagnostics-only proof that source packet keys align with the candidate join sources before any enrichment is attempted."
            ),
            reason=(
                "Validate store, promotion, and SKU coverage before any join spec is authored or executed."
            ),
        )
    )

    if context.actual_join_required_flag:
        actual_join_status = (
            QUEUE_BLOCKED_MISSING_JOIN_SOURCE
            if context.blocked_actual_join_flag
            else QUEUE_WAITING_FOR_PRIOR_STEP
        )
        actual_join_blocking = int(actual_join_status.startswith("BLOCKED"))
    else:
        actual_join_status = QUEUE_NOT_REQUIRED
        actual_join_blocking = 0
    queue_rows.append(
        _queue_row(
            context=context,
            required_action=ACTION_JOIN_ACTUAL_OUTCOME_SOURCE,
            action_status=actual_join_status,
            blocking_flag=actual_join_blocking,
            candidate_join_source_path=primary_actual_source,
            join_key_columns=actual_join_keys,
            missing_fields_addressed=context.missing_actual_outcome_fields,
            guardrail_check_required=0,
            expected_output=(
                "A diagnostics-only actual-outcome enrichment specification that fills the missing actual fields without mutating the source packet."
            ),
            reason=(
                "Missing actuals remain missing until matched actual-outcome fields are joined; never convert them to zero sales."
            ),
        )
    )

    if context.operator_join_required_flag:
        operator_join_status = (
            QUEUE_BLOCKED_MISSING_JOIN_SOURCE
            if context.blocked_operator_join_flag
            else QUEUE_WAITING_FOR_PRIOR_STEP
        )
        operator_join_blocking = int(operator_join_status.startswith("BLOCKED"))
    else:
        operator_join_status = QUEUE_NOT_REQUIRED
        operator_join_blocking = 0
    queue_rows.append(
        _queue_row(
            context=context,
            required_action=ACTION_JOIN_OPERATOR_AUDIT_SOURCE,
            action_status=operator_join_status,
            blocking_flag=operator_join_blocking,
            candidate_join_source_path=primary_operator_source,
            join_key_columns=operator_join_keys,
            missing_fields_addressed=context.missing_prediction_action_fields,
            guardrail_check_required=0,
            expected_output=(
                "A diagnostics-only operator-audit enrichment specification for missing action evidence fields."
            ),
            reason=(
                "Operator-audit joins are for governed review preparation only and must not change production ordering logic or Stage 12."
            ),
        )
    )

    mapping_status = (
        QUEUE_BLOCKED_MISSING_SCHEMA_MAPPING
        if context.schema_mapping_required_flag
        else QUEUE_NOT_REQUIRED
    )
    mapping_blocking = int(mapping_status.startswith("BLOCKED"))
    queue_rows.append(
        _queue_row(
            context=context,
            required_action=ACTION_MAP_CANONICAL_REVIEW_SCHEMA,
            action_status=mapping_status,
            blocking_flag=mapping_blocking,
            candidate_join_source_path="",
            join_key_columns=context.join_key_columns,
            missing_fields_addressed=(
                *context.missing_fields_for_schema_mapping,
                *context.manifest_missing_canonical_fields,
            ),
            guardrail_check_required=0,
            expected_output=(
                "A canonical governed review-schema mapping plan that identifies how enriched source columns land in the governed review packet contract."
            ),
            reason=(
                "The queue does not author or execute schema mapping; it records that mapping is still required before any full governed rebuild can run."
            ),
        )
    )

    validate_actuals_status = (
        QUEUE_BLOCKED_MISSING_JOIN_SOURCE
        if context.blocked_actual_join_flag
        else QUEUE_WAITING_FOR_PRIOR_STEP
        if context.actual_join_required_flag or context.schema_mapping_required_flag
        else QUEUE_NOT_REQUIRED
    )
    queue_rows.append(
        _queue_row(
            context=context,
            required_action=ACTION_VALIDATE_NO_ACTUALS_AS_ZERO,
            action_status=validate_actuals_status,
            blocking_flag=int(validate_actuals_status.startswith("BLOCKED")),
            candidate_join_source_path=_format_list(context.actual_candidate_join_sources),
            join_key_columns=actual_join_keys,
            missing_fields_addressed=context.missing_actual_outcome_fields,
            guardrail_check_required=1,
            expected_output=(
                "A diagnostics-only validation record confirming that missing actual fields remain null or blank until a matched source join provides them."
            ),
            reason=(
                "This queue must preserve the rule that missing actuals are never rewritten as zero sales or zero gross profit."
            ),
        )
    )

    validate_row_count_status = (
        QUEUE_WAITING_FOR_PRIOR_STEP
        if context.actual_join_required_flag or context.operator_join_required_flag or context.schema_mapping_required_flag
        else QUEUE_VALIDATION_REQUIRED
    )
    queue_rows.append(
        _queue_row(
            context=context,
            required_action=ACTION_VALIDATE_ROW_COUNT_CONSERVATION,
            action_status=validate_row_count_status,
            blocking_flag=0,
            candidate_join_source_path="",
            join_key_columns=context.join_key_columns,
            missing_fields_addressed=(),
            guardrail_check_required=1,
            expected_output=(
                "A diagnostics-only validation that the prepared rebuild frame preserves row counts across joins and schema mapping."
            ),
            reason=(
                "Row conservation must hold before any governed review rebuild is allowed to proceed."
            ),
        )
    )

    validate_guardrails_status = (
        QUEUE_WAITING_FOR_PRIOR_STEP
        if context.schema_mapping_required_flag or context.actual_join_required_flag or context.operator_join_required_flag
        else QUEUE_VALIDATION_REQUIRED
    )
    queue_rows.append(
        _queue_row(
            context=context,
            required_action=ACTION_VALIDATE_PRODUCTION_AND_STAGE12_GUARDRAILS,
            action_status=validate_guardrails_status,
            blocking_flag=0,
            candidate_join_source_path="",
            join_key_columns=context.join_key_columns,
            missing_fields_addressed=(),
            guardrail_check_required=1,
            expected_output=(
                "A diagnostics-only guardrail validation proving that the preparation queue does not start training, alter production ordering logic, or alter Stage 12 behavior."
            ),
            reason=(
                "Production and Stage 12 guardrails must remain unchanged throughout queue preparation and later rebuild work."
            ),
        )
    )

    mark_ready_status = (
        QUEUE_BLOCKED_MISSING_JOIN_SOURCE
        if context.blocked_actual_join_flag or context.blocked_operator_join_flag
        else QUEUE_WAITING_FOR_PRIOR_STEP
        if context.schema_mapping_required_flag or context.actual_join_required_flag or context.operator_join_required_flag
        else QUEUE_VALIDATION_REQUIRED
    )
    queue_rows.append(
        _queue_row(
            context=context,
            required_action=ACTION_MARK_READY_FOR_GOVERNED_REVIEW_REBUILD,
            action_status=mark_ready_status,
            blocking_flag=int(mark_ready_status.startswith("BLOCKED")),
            candidate_join_source_path="",
            join_key_columns=context.join_key_columns,
            missing_fields_addressed=(
                *context.missing_actual_outcome_fields,
                *context.missing_prediction_action_fields,
                *context.missing_identity_fields,
                *context.missing_economics_fields,
            ),
            guardrail_check_required=1,
            expected_output=(
                "A diagnostics-only readiness marker showing the promotion can enter a later governed review rebuild without mutating the original materialized source packet."
            ),
            reason=(
                "A promotion can be marked ready only after joins, schema mapping, row conservation, and production guardrail validations are all complete."
            ),
        )
    )
    return queue_rows


def _build_by_promotion_rows(contexts: Sequence[PromotionQueueContext]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for context in contexts:
        rows.append(
            {
                "promotion_priority_rank": context.priority_rank,
                "promotion_key": context.promotion_key,
                "promotion_name": context.promotion_name,
                "promotion_start_date": context.promotion_start_date,
                "promotion_end_date": context.promotion_end_date,
                "queue_row_count": len(QUEUE_ACTION_ORDER),
                "actual_outcome_join_required_flag": context.actual_join_required_flag,
                "actual_outcome_join_candidate_flag": context.actual_join_candidate_flag,
                "operator_audit_join_required_flag": context.operator_join_required_flag,
                "operator_audit_join_candidate_flag": context.operator_join_candidate_flag,
                "schema_mapping_required_flag": context.schema_mapping_required_flag,
                "blocked_flag": context.blocked_flag,
                "potentially_ready_after_joins_flag": context.potentially_ready_after_joins_flag,
                "first_required_action": _promotion_first_required_action(context),
                "source_file_path": context.source_file_path,
                "recommended_next_step": context.recommended_next_step,
                "reason": context.reason,
            }
        )
    return rows


def _build_join_execution_plan(queue_rows_frame: pd.DataFrame, contexts: Sequence[PromotionQueueContext]) -> pd.DataFrame:
    priority_lookup = {context.promotion_key: context.priority_rank for context in contexts}
    filtered = queue_rows_frame.loc[
        queue_rows_frame["required_action"].astype(str).isin(
            (
                ACTION_VALIDATE_JOIN_KEY_COVERAGE,
                ACTION_JOIN_ACTUAL_OUTCOME_SOURCE,
                ACTION_JOIN_OPERATOR_AUDIT_SOURCE,
            )
        )
    ].copy()
    filtered.insert(
        0,
        "promotion_priority_rank",
        filtered["promotion_key"].map(priority_lookup).fillna(0).astype(int),
    )
    return filtered.loc[:, JOIN_EXECUTION_PLAN_COLUMNS]


def _build_schema_mapping_plan(contexts: Sequence[PromotionQueueContext]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for context in contexts:
        if not context.schema_mapping_required_flag:
            continue
        rows.append(
            {
                "promotion_priority_rank": context.priority_rank,
                "promotion_key": context.promotion_key,
                "promotion_name": context.promotion_name,
                "promotion_start_date": context.promotion_start_date,
                "promotion_end_date": context.promotion_end_date,
                "source_file_path": context.source_file_path,
                "source_manifest_path": context.source_manifest_path,
                "manifest_missing_canonical_fields": _format_list(
                    context.manifest_missing_canonical_fields
                ),
                "missing_fields_addressed": _format_list(
                    context.missing_fields_for_schema_mapping
                ),
                "action_status": QUEUE_BLOCKED_MISSING_SCHEMA_MAPPING,
                "blocking_flag": 1,
                "expected_output": (
                    "A field-level canonical review-schema mapping plan for later diagnostics-only enrichment and governed rebuild preparation."
                ),
                "recommended_next_step": context.recommended_next_step,
                "reason": context.reason,
            }
        )
    return pd.DataFrame(rows, columns=SCHEMA_MAPPING_PLAN_COLUMNS)


def _build_summary_frame(contexts: Sequence[PromotionQueueContext], queue_rows_frame: pd.DataFrame) -> pd.DataFrame:
    rows = [
        _summary_row("PROMOTIONS_IN_QUEUE", len(contexts), "Promotions included in the diagnostics-only rebuild queue."),
        _summary_row("TOTAL_QUEUE_ROWS", len(queue_rows_frame.index), "Ordered queue rows generated across all promotions."),
        _summary_row(
            "PROMOTIONS_WITH_ACTUAL_OUTCOME_JOIN_CANDIDATE",
            sum(context.actual_join_candidate_flag for context in contexts),
            "Promotions with at least one candidate actual-outcome join source.",
        ),
        _summary_row(
            "PROMOTIONS_MISSING_ACTUAL_OUTCOME_JOIN_CANDIDATE",
            sum(
                int(context.actual_join_required_flag and not context.actual_join_candidate_flag)
                for context in contexts
            ),
            "Promotions that still need actual-outcome fields but have no matched join source candidate.",
        ),
        _summary_row(
            "PROMOTIONS_WITH_OPERATOR_AUDIT_JOIN_CANDIDATE",
            sum(context.operator_join_candidate_flag for context in contexts),
            "Promotions with at least one candidate operator-audit join source.",
        ),
        _summary_row(
            "PROMOTIONS_MISSING_OPERATOR_AUDIT_JOIN_CANDIDATE",
            sum(
                int(context.operator_join_required_flag and not context.operator_join_candidate_flag)
                for context in contexts
            ),
            "Promotions that still need operator-audit evidence but have no matched join source candidate.",
        ),
        _summary_row(
            "PROMOTIONS_NEEDING_SCHEMA_MAPPING",
            sum(context.schema_mapping_required_flag for context in contexts),
            "Promotions that still require canonical governed review-schema mapping.",
        ),
        _summary_row(
            "PROMOTIONS_BLOCKED",
            sum(context.blocked_flag for context in contexts),
            "Promotions with at least one blocking queue action.",
        ),
        _summary_row(
            "PROMOTIONS_POTENTIALLY_READY_AFTER_JOINS",
            sum(context.potentially_ready_after_joins_flag for context in contexts),
            "Promotions that could become ready once joins and schema mapping are completed.",
        ),
        _summary_row(
            "PRODUCTION_GUARDRAIL_FAILURES",
            sum(context.production_guardrail_failure_flag for context in contexts),
            "Promotions already showing a production-ordering guardrail change flag.",
        ),
        _summary_row(
            "STAGE12_GUARDRAIL_FAILURES",
            sum(context.stage12_guardrail_failure_flag for context in contexts),
            "Promotions already showing a Stage 12 guardrail change flag.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(
    *,
    contexts: Sequence[PromotionQueueContext],
    summary_frame: pd.DataFrame,
) -> str:
    summary_lookup = dict(zip(summary_frame["metric_name"].astype(str), summary_frame["metric_value"]))
    first_promotion = contexts[0] if contexts else None
    first_line = (
        f"Work first on {first_promotion.promotion_name} starting {first_promotion.promotion_start_date}."
        if first_promotion is not None
        else "No promotions were queued."
    )
    blocked_lines = [
        f"- {context.promotion_name}: {context.reason}"
        for context in contexts
        if context.blocked_flag
    ] or ["- No blocking promotions were detected."]
    return "\n".join(
        [
            "# Materialized Source Rebuild Queue",
            "",
            "This is not a rebuild.",
            "This is not training.",
            "This is not an order file.",
            "This is a diagnostics-only execution queue for preparing a later governed review rebuild.",
            "Missing actuals remain missing until a matched source join provides them.",
            "Production ordering logic remains unchanged.",
            "Stage 12 remains unchanged.",
            "Shadow rules remain diagnostics-only and are not promoted by this queue.",
            "",
            "## 1. Queue summary",
            f"Promotions queued = {int(summary_lookup.get('PROMOTIONS_IN_QUEUE', 0))}.",
            f"Total queue rows = {int(summary_lookup.get('TOTAL_QUEUE_ROWS', 0))}.",
            f"Promotions with actual-outcome join candidate = {int(summary_lookup.get('PROMOTIONS_WITH_ACTUAL_OUTCOME_JOIN_CANDIDATE', 0))}.",
            f"Promotions missing actual-outcome join candidate = {int(summary_lookup.get('PROMOTIONS_MISSING_ACTUAL_OUTCOME_JOIN_CANDIDATE', 0))}.",
            f"Promotions needing schema mapping = {int(summary_lookup.get('PROMOTIONS_NEEDING_SCHEMA_MAPPING', 0))}.",
            f"Blocked promotions = {int(summary_lookup.get('PROMOTIONS_BLOCKED', 0))}.",
            "",
            "## 2. Work order",
            first_line,
            "Prioritise promotions with actual-outcome join candidates first, then promotions with operator-audit candidates, then the lowest critical-missing-field count, then the most recent promotions.",
            "",
            "## 3. Blocking conditions",
            *blocked_lines,
            "",
            "## 4. Before a full governed review rebuild can run",
            "Join key coverage must be validated.",
            "Missing actuals must remain missing until matched actual-outcome fields are joined.",
            "Canonical review-schema mapping must be authored and reviewed.",
            "Row-count conservation must be validated after enrichment planning.",
            "Production ordering and Stage 12 guardrails must remain unchanged.",
        ]
    ).strip()


def build_promotions_materialized_source_rebuild_queue(
    *,
    packet_root: str | Path,
) -> PromotionsMaterializedSourceRebuildQueueResult:
    packet_root_path = Path(packet_root)
    readiness_root = packet_root_path / READINESS_AUDIT_FOLDER_NAME
    readiness_rows_frame = _read_csv(readiness_root / "materialized_source_readiness_rows.csv")
    candidate_join_sources_frame = _read_csv(
        readiness_root / "materialized_source_candidate_join_sources.csv",
        allow_empty=True,
    )
    contexts = _build_contexts(
        packet_root=packet_root_path,
        readiness_rows_frame=readiness_rows_frame,
        candidate_join_sources_frame=candidate_join_sources_frame,
    )
    candidate_lookup = _candidate_lookup(candidate_join_sources_frame)
    queue_rows: list[dict[str, object]] = []
    for context in contexts:
        queue_rows.extend(
            _build_queue_rows_for_promotion(
                context=context,
                candidate_lookup=candidate_lookup,
            )
        )
    for rank, row in enumerate(queue_rows, start=1):
        row["queue_rank"] = rank
    queue_rows_frame = pd.DataFrame(queue_rows, columns=QUEUE_ROWS_COLUMNS)
    by_promotion_frame = pd.DataFrame(
        _build_by_promotion_rows(contexts),
        columns=BY_PROMOTION_COLUMNS,
    )
    join_execution_plan_frame = _build_join_execution_plan(queue_rows_frame, contexts)
    schema_mapping_plan_frame = _build_schema_mapping_plan(contexts)
    summary_frame = _build_summary_frame(contexts, queue_rows_frame)
    memo_markdown = _build_memo(contexts=contexts, summary_frame=summary_frame)
    return PromotionsMaterializedSourceRebuildQueueResult(
        queue_rows_frame=queue_rows_frame,
        by_promotion_frame=by_promotion_frame,
        join_execution_plan_frame=join_execution_plan_frame,
        schema_mapping_plan_frame=schema_mapping_plan_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_rebuild_queue(
    *,
    packet_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceRebuildQueueArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = (
        Path(output_root) if output_root is not None else packet_root_path / OUTPUT_FOLDER_NAME
    )
    result = build_promotions_materialized_source_rebuild_queue(packet_root=packet_root_path)
    output_root_path.mkdir(parents=True, exist_ok=True)
    queue_rows_csv_path = output_root_path / "materialized_source_rebuild_queue_rows.csv"
    by_promotion_csv_path = output_root_path / "materialized_source_rebuild_queue_by_promotion.csv"
    join_execution_plan_csv_path = output_root_path / "materialized_source_join_execution_plan.csv"
    schema_mapping_plan_csv_path = output_root_path / "materialized_source_schema_mapping_plan.csv"
    summary_csv_path = output_root_path / "materialized_source_rebuild_queue_summary.csv"
    memo_md_path = output_root_path / "materialized_source_rebuild_queue_memo.md"
    result.queue_rows_frame.to_csv(queue_rows_csv_path, index=False)
    result.by_promotion_frame.to_csv(by_promotion_csv_path, index=False)
    result.join_execution_plan_frame.to_csv(join_execution_plan_csv_path, index=False)
    result.schema_mapping_plan_frame.to_csv(schema_mapping_plan_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")
    return PromotionsMaterializedSourceRebuildQueueArtifacts(
        output_root=str(output_root_path),
        queue_rows_csv_path=str(queue_rows_csv_path),
        by_promotion_csv_path=str(by_promotion_csv_path),
        join_execution_plan_csv_path=str(join_execution_plan_csv_path),
        schema_mapping_plan_csv_path=str(schema_mapping_plan_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a diagnostics-only execution queue for preparing materialized promotion packets for a later governed review rebuild."
        )
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_materialized_source_rebuild_queue(
        packet_root=args.packet_root,
        output_root=args.output_root,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    summary_lookup = dict(
        zip(
            summary_frame.get("metric_name", pd.Series(dtype="object")).astype(str),
            summary_frame.get("metric_value", pd.Series(dtype="object")),
        )
    )
    by_promotion_frame = _read_csv(artifacts.by_promotion_csv_path, allow_empty=True)
    first_promotion = _normalize_text(
        by_promotion_frame.iloc[0].get("promotion_key") if not by_promotion_frame.empty else ""
    )
    print("promotions_queued", _as_int(summary_lookup.get("PROMOTIONS_IN_QUEUE", 0)))
    print("total_queue_rows", _as_int(summary_lookup.get("TOTAL_QUEUE_ROWS", 0)))
    print(
        "promotions_with_actual_outcome_join_candidate",
        _as_int(summary_lookup.get("PROMOTIONS_WITH_ACTUAL_OUTCOME_JOIN_CANDIDATE", 0)),
    )
    print(
        "promotions_missing_actual_outcome_join_candidate",
        _as_int(summary_lookup.get("PROMOTIONS_MISSING_ACTUAL_OUTCOME_JOIN_CANDIDATE", 0)),
    )
    print(
        "promotions_with_operator_audit_join_candidate",
        _as_int(summary_lookup.get("PROMOTIONS_WITH_OPERATOR_AUDIT_JOIN_CANDIDATE", 0)),
    )
    print(
        "promotions_needing_schema_mapping",
        _as_int(summary_lookup.get("PROMOTIONS_NEEDING_SCHEMA_MAPPING", 0)),
    )
    print("promotions_blocked", _as_int(summary_lookup.get("PROMOTIONS_BLOCKED", 0)))
    print("first_promotion_to_work", first_promotion)
    print("materialized_source_rebuild_queue_rows", artifacts.queue_rows_csv_path)
    print("materialized_source_rebuild_queue_by_promotion", artifacts.by_promotion_csv_path)
    print("materialized_source_join_execution_plan", artifacts.join_execution_plan_csv_path)
    print("materialized_source_schema_mapping_plan", artifacts.schema_mapping_plan_csv_path)
    print("materialized_source_rebuild_queue_summary", artifacts.summary_csv_path)
    print("materialized_source_rebuild_queue_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())