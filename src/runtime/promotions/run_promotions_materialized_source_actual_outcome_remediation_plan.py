from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_actual_outcome_remediation_plan"
PROMOTION_RUNS_FOLDER_NAME = "promotion_runs"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
JOIN_VALIDATION_FOLDER_NAME = "materialized_source_join_key_validation"

SUMMARY_FILE_NAME = "actual_outcome_remediation_summary.csv"
SCHEMA_FILE_NAME = "actual_outcome_source_schema_diagnosis.csv"
CONTRACT_FILE_NAME = "actual_outcome_required_contract.csv"
CANDIDATE_FILE_NAME = "actual_outcome_candidate_search_results.csv"
VALIDATION_FILE_NAME = "actual_outcome_remediation_validation.csv"
MEMO_FILE_NAME = "actual_outcome_remediation_memo.md"

JOIN_VALIDATION_SUMMARY_FILE_NAME = "materialized_source_join_key_validation_summary.csv"
JOIN_VALIDATION_PLAN_FILE_NAME = "materialized_source_join_key_validation_plan.csv"

SOURCE_ROLE_ACTUAL_OUTCOME = "ACTUAL_OUTCOME"
JOIN_BLOCKED_MISSING_KEYS = "JOIN_BLOCKED_MISSING_KEYS"
REMEDIATION_STATUS_REQUIRED = "ACTUAL_OUTCOME_REMEDIATION_REQUIRED"

REQUIRED_JOIN_KEY_FIELDS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)

REQUIRED_SOURCE_CONTRACT_FIELDS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
    "actual_units",
    "actual_sales_ex_gst",
    "actual_gross_profit",
    "actual_stockout_flag",
    "actual_leftover_units",
    "actual_result_source",
    "actual_result_as_of_date",
)

SAFE_SKU_ALIAS_COLUMNS: tuple[str, ...] = (
    "sku",
    "item_number",
    "product_number",
    "product_code",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

SCHEMA_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_folder_name",
    "actual_outcome_source_path",
    "actual_outcome_source_exists_flag",
    "actual_outcome_source_row_count",
    "actual_outcome_source_column_count",
    "actual_outcome_source_columns",
    "missing_required_join_keys",
    "sku_like_columns_found",
    "safe_sku_alias_exists_flag",
    "stage1_actual_source_status",
)

CONTRACT_COLUMNS: tuple[str, ...] = (
    "contract_field",
    "required_flag",
    "notes",
)

CANDIDATE_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_folder_name",
    "candidate_source_path",
    "candidate_file_name",
    "candidate_exists_flag",
    "candidate_row_count",
    "candidate_column_count",
    "candidate_columns",
    "contains_all_required_join_keys_flag",
    "missing_required_join_keys",
    "sku_like_columns_found",
    "is_promotion_scoped_candidate_flag",
    "notes",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)


class PromotionsMaterializedSourceActualOutcomeRemediationPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceSchemaDiagnosis:
    source_path: str
    source_exists_flag: int
    row_count: int
    column_count: int
    columns: tuple[str, ...]
    missing_required_join_keys: tuple[str, ...]
    sku_like_columns_found: tuple[str, ...]
    safe_sku_alias_exists_flag: int


@dataclass(frozen=True)
class PromotionsMaterializedSourceActualOutcomeRemediationPlanResult:
    remediation_status: str
    promotion_key: str
    promotion_folder_name: str
    stage1_summary_path: str
    stage1_plan_path: str
    stage1_actual_source_status: str
    actual_outcome_source_path: str
    actual_outcome_source_exists_flag: int
    actual_outcome_source_row_count: int
    actual_outcome_source_column_count: int
    missing_required_join_keys: tuple[str, ...]
    sku_like_columns_found: tuple[str, ...]
    safe_sku_alias_exists_flag: int
    candidate_promotion_scoped_ready_source_found_flag: int
    source_packets_mutated_flag: int
    operator_audit_overwritten_flag: int
    actual_outcome_governed_file_created_flag: int
    summary_frame: pd.DataFrame
    schema_diagnosis_frame: pd.DataFrame
    required_contract_frame: pd.DataFrame
    candidate_search_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceActualOutcomeRemediationPlanArtifacts:
    output_root: str
    summary_csv_path: str
    schema_diagnosis_csv_path: str
    required_contract_csv_path: str
    candidate_search_csv_path: str
    validation_csv_path: str
    memo_md_path: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceActualOutcomeRemediationPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceActualOutcomeRemediationPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceActualOutcomeRemediationPlanError(f"CSV is empty: {csv_path}")
    return frame


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(name: str, status: str, flag: int, details: str) -> dict[str, object]:
    return {
        "validation_name": name,
        "validation_status": status,
        "validation_flag": int(flag),
        "details": details,
    }


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = [part.strip() for part in promotion_key.split("|", maxsplit=3)]
    if len(parts) != 4 or not all(parts):
        raise PromotionsMaterializedSourceActualOutcomeRemediationPlanError(
            f"Invalid promotion key format: {promotion_key}"
        )
    return parts[0], parts[1], parts[2], parts[3]


def _slugify(value: str) -> str:
    lowered = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    return re.sub(r"-{2,}", "-", slug).strip("-")


def _promotion_folder_from_key(promotion_key: str) -> str:
    store, start_date, end_date, promotion_name = _promotion_parts_from_key(promotion_key)
    return f"promotion_{store}-{start_date}-{end_date}-{_slugify(promotion_name)}"


def _source_root_fingerprint(source_root: Path) -> str:
    if not source_root.exists():
        return ""
    parts: list[str] = []
    for file_path in sorted(path for path in source_root.rglob("*") if path.is_file()):
        rel = str(file_path.relative_to(source_root))
        data = file_path.read_bytes()
        parts.append(f"{rel}:{len(data)}:{data[:64].hex()}")
    return "|".join(parts)


def _resolve_output_root(packet_root: Path, output_root: str | Path | None) -> Path:
    if output_root is not None:
        return Path(output_root)
    return packet_root / OUTPUT_FOLDER_NAME


def _resolve_stage1_artifacts(packet_root: Path, promotion_key: str) -> tuple[Path, Path, str]:
    expected_folder = _promotion_folder_from_key(promotion_key)
    expected_root = packet_root / PROMOTION_RUNS_FOLDER_NAME / expected_folder / JOIN_VALIDATION_FOLDER_NAME
    expected_summary = expected_root / JOIN_VALIDATION_SUMMARY_FILE_NAME
    expected_plan = expected_root / JOIN_VALIDATION_PLAN_FILE_NAME
    if expected_summary.exists() and expected_plan.exists():
        return expected_summary, expected_plan, expected_folder

    promotion_runs_root = packet_root / PROMOTION_RUNS_FOLDER_NAME
    if not promotion_runs_root.exists():
        raise PromotionsMaterializedSourceActualOutcomeRemediationPlanError(
            f"Promotion runs folder not found: {promotion_runs_root}"
        )

    for plan_path in sorted(promotion_runs_root.rglob(JOIN_VALIDATION_PLAN_FILE_NAME)):
        plan_frame = _read_csv(plan_path, allow_empty=True)
        if plan_frame.empty:
            continue
        mask = (
            plan_frame.get("promotion_key", pd.Series(dtype="object")).astype(str).eq(promotion_key)
            & plan_frame.get("candidate_source_role", pd.Series(dtype="object")).astype(str).eq(SOURCE_ROLE_ACTUAL_OUTCOME)
        )
        if not mask.any():
            continue
        row = plan_frame.loc[mask].iloc[0]
        folder_name = _normalize_text(row.get("promotion_folder_name")) or plan_path.parents[1].name
        summary_path = plan_path.parent / JOIN_VALIDATION_SUMMARY_FILE_NAME
        if summary_path.exists():
            return summary_path, plan_path, folder_name

    raise PromotionsMaterializedSourceActualOutcomeRemediationPlanError(
        f"Could not resolve Stage 1 join-key validation artifacts for promotion key: {promotion_key}"
    )


def _collect_stage1_actual_row(plan_frame: pd.DataFrame, promotion_key: str) -> pd.Series:
    matches = plan_frame.loc[
        plan_frame["promotion_key"].astype(str).eq(promotion_key)
        & plan_frame["candidate_source_role"].astype(str).eq(SOURCE_ROLE_ACTUAL_OUTCOME)
    ]
    if matches.empty:
        raise PromotionsMaterializedSourceActualOutcomeRemediationPlanError(
            f"ACTUAL_OUTCOME row not found in Stage 1 plan for promotion key: {promotion_key}"
        )
    return matches.iloc[0]


def _scan_source_schema(source_path: str) -> SourceSchemaDiagnosis:
    normalized = _normalize_text(source_path)
    if not normalized:
        return SourceSchemaDiagnosis(
            source_path="",
            source_exists_flag=0,
            row_count=0,
            column_count=0,
            columns=(),
            missing_required_join_keys=REQUIRED_JOIN_KEY_FIELDS,
            sku_like_columns_found=(),
            safe_sku_alias_exists_flag=0,
        )

    file_path = Path(normalized)
    if not file_path.exists():
        return SourceSchemaDiagnosis(
            source_path=normalized,
            source_exists_flag=0,
            row_count=0,
            column_count=0,
            columns=(),
            missing_required_join_keys=REQUIRED_JOIN_KEY_FIELDS,
            sku_like_columns_found=(),
            safe_sku_alias_exists_flag=0,
        )

    frame = _read_csv(file_path, allow_empty=True)
    columns = tuple(str(col) for col in frame.columns)
    missing = tuple(field for field in REQUIRED_JOIN_KEY_FIELDS if field not in columns)
    sku_like_tokens = ("sku", "item", "product", "upc", "ean", "plu", "article")
    sku_like_columns = tuple(
        column
        for column in columns
        if any(token in column.lower() for token in sku_like_tokens)
    )
    safe_alias_exists = int(
        "sku_number" not in columns and any(alias in columns for alias in SAFE_SKU_ALIAS_COLUMNS)
    )

    return SourceSchemaDiagnosis(
        source_path=normalized,
        source_exists_flag=1,
        row_count=int(len(frame.index)),
        column_count=int(len(columns)),
        columns=columns,
        missing_required_join_keys=missing,
        sku_like_columns_found=sku_like_columns,
        safe_sku_alias_exists_flag=safe_alias_exists,
    )


def _candidate_search_rows(
    *,
    packet_root: Path,
    promotion_key: str,
    promotion_folder_name: str,
) -> tuple[list[dict[str, object]], int]:
    source_folder = packet_root / SOURCE_MATERIALIZED_FOLDER_NAME / promotion_folder_name
    candidates: list[dict[str, object]] = []
    ready_found = 0

    if not source_folder.exists():
        return candidates, ready_found

    for candidate_path in sorted(source_folder.rglob("*.csv")):
        file_name = candidate_path.name.lower()
        if "actual" not in file_name and "outcome" not in file_name:
            continue
        frame = _read_csv(candidate_path, allow_empty=True)
        columns = tuple(str(col) for col in frame.columns)
        missing = tuple(field for field in REQUIRED_JOIN_KEY_FIELDS if field not in columns)
        contains_all_required = int(len(missing) == 0)
        ready_found = max(ready_found, contains_all_required)
        sku_like_tokens = ("sku", "item", "product", "upc", "ean", "plu", "article")
        sku_like_columns = tuple(
            column
            for column in columns
            if any(token in column.lower() for token in sku_like_tokens)
        )
        candidates.append(
            {
                "promotion_key": promotion_key,
                "promotion_folder_name": promotion_folder_name,
                "candidate_source_path": str(candidate_path),
                "candidate_file_name": candidate_path.name,
                "candidate_exists_flag": 1,
                "candidate_row_count": int(len(frame.index)),
                "candidate_column_count": int(len(columns)),
                "candidate_columns": "; ".join(columns),
                "contains_all_required_join_keys_flag": contains_all_required,
                "missing_required_join_keys": "; ".join(missing),
                "sku_like_columns_found": "; ".join(sku_like_columns),
                "is_promotion_scoped_candidate_flag": 1,
                "notes": (
                    "Promotion-scoped candidate includes all approved join keys."
                    if contains_all_required
                    else "Promotion-scoped candidate is missing one or more approved join keys."
                ),
            }
        )

    return candidates, ready_found


def build_promotions_materialized_source_actual_outcome_remediation_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceActualOutcomeRemediationPlanResult:
    packet_root_path = Path(packet_root)
    stage1_summary_path, stage1_plan_path, promotion_folder_name = _resolve_stage1_artifacts(
        packet_root_path,
        promotion_key,
    )

    source_root = packet_root_path / SOURCE_MATERIALIZED_FOLDER_NAME
    promotion_folder_root = source_root / promotion_folder_name
    source_rows_path = promotion_folder_root / "promotion_source_rows.csv"
    operator_audit_path = promotion_folder_root / "operator_audit_source.csv"
    actual_outcome_governed_path = promotion_folder_root / "actual_outcome_source.csv"

    source_root_before = _source_root_fingerprint(source_root)
    source_rows_before = source_rows_path.read_bytes() if source_rows_path.exists() else b""
    operator_before = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    governed_actual_before_exists = int(actual_outcome_governed_path.exists())

    stage1_plan_frame = _read_csv(stage1_plan_path)

    stage1_actual_row = _collect_stage1_actual_row(stage1_plan_frame, promotion_key)
    actual_source_path = _normalize_text(stage1_actual_row.get("candidate_source_path"))
    stage1_actual_source_status = _normalize_text(stage1_actual_row.get("join_readiness_status"))

    schema = _scan_source_schema(actual_source_path)

    candidate_rows, candidate_ready_found = _candidate_search_rows(
        packet_root=packet_root_path,
        promotion_key=promotion_key,
        promotion_folder_name=promotion_folder_name,
    )

    remediation_status = REMEDIATION_STATUS_REQUIRED
    schema_frame = pd.DataFrame(
        [
            {
                "promotion_key": promotion_key,
                "promotion_folder_name": promotion_folder_name,
                "actual_outcome_source_path": schema.source_path,
                "actual_outcome_source_exists_flag": schema.source_exists_flag,
                "actual_outcome_source_row_count": schema.row_count,
                "actual_outcome_source_column_count": schema.column_count,
                "actual_outcome_source_columns": "; ".join(schema.columns),
                "missing_required_join_keys": "; ".join(schema.missing_required_join_keys),
                "sku_like_columns_found": "; ".join(schema.sku_like_columns_found),
                "safe_sku_alias_exists_flag": schema.safe_sku_alias_exists_flag,
                "stage1_actual_source_status": stage1_actual_source_status,
            }
        ],
        columns=SCHEMA_COLUMNS,
    )

    required_contract_frame = pd.DataFrame(
        [
            {
                "contract_field": field,
                "required_flag": 1,
                "notes": "Required for governed ACTUAL_OUTCOME remediation source contract.",
            }
            for field in REQUIRED_SOURCE_CONTRACT_FIELDS
        ],
        columns=CONTRACT_COLUMNS,
    )

    candidate_search_frame = pd.DataFrame(candidate_rows, columns=CANDIDATE_COLUMNS)

    source_rows_after = source_rows_path.read_bytes() if source_rows_path.exists() else b""
    operator_after = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    source_root_after = _source_root_fingerprint(source_root)
    governed_actual_after_exists = int(actual_outcome_governed_path.exists())

    source_packets_mutated_flag = int(source_root_before != source_root_after or source_rows_before != source_rows_after)
    operator_audit_overwritten_flag = int(operator_before != operator_after)
    actual_outcome_governed_file_created_flag = int(
        governed_actual_before_exists == 0 and governed_actual_after_exists == 1
    )

    missing_join_keys_text = "; ".join(schema.missing_required_join_keys)
    sku_like_text = "; ".join(schema.sku_like_columns_found)

    summary_frame = pd.DataFrame(
        [
            _summary_row("REMEDIATION_STATUS", remediation_status, "Planner-only ACTUAL_OUTCOME remediation status."),
            _summary_row("PROMOTION_KEY", promotion_key, "Promotion key for remediation diagnosis."),
            _summary_row("PROMOTION_FOLDER_NAME", promotion_folder_name, "Promotion-scoped packet folder used for diagnosis."),
            _summary_row("STAGE1_SUMMARY_PATH", str(stage1_summary_path), "Stage 1 summary consumed as read-only input."),
            _summary_row("STAGE1_PLAN_PATH", str(stage1_plan_path), "Stage 1 plan consumed as read-only input."),
            _summary_row("STAGE1_ACTUAL_SOURCE_STATUS", stage1_actual_source_status, "Stage 1 ACTUAL_OUTCOME status at diagnosis time."),
            _summary_row("ACTUAL_OUTCOME_SOURCE_PATH", schema.source_path, "ACTUAL_OUTCOME source path currently selected by Stage 1."),
            _summary_row("ACTUAL_OUTCOME_SOURCE_EXISTS_FLAG", schema.source_exists_flag, "Whether the selected ACTUAL_OUTCOME source exists on disk."),
            _summary_row("ACTUAL_OUTCOME_SOURCE_ROW_COUNT", schema.row_count, "Row count of the selected ACTUAL_OUTCOME source."),
            _summary_row("ACTUAL_OUTCOME_SOURCE_COLUMN_COUNT", schema.column_count, "Column count of the selected ACTUAL_OUTCOME source."),
            _summary_row("MISSING_REQUIRED_JOIN_KEYS", missing_join_keys_text, "Missing fields from approved ACTUAL_OUTCOME join key contract."),
            _summary_row("SKU_LIKE_COLUMNS_FOUND", sku_like_text, "SKU-like columns discovered in selected ACTUAL_OUTCOME source."),
            _summary_row("SAFE_SKU_ALIAS_EXISTS_FLAG", schema.safe_sku_alias_exists_flag, "Whether a safe alias to sku_number exists in the selected source."),
            _summary_row("CANDIDATE_PROMOTION_SCOPED_READY_SOURCE_FOUND_FLAG", candidate_ready_found, "Whether any promotion-scoped ACTUAL_OUTCOME candidate contains all approved join keys."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", source_packets_mutated_flag, "Planner must not mutate source packets."),
            _summary_row("OPERATOR_AUDIT_OVERWRITTEN_FLAG", operator_audit_overwritten_flag, "Planner must not overwrite operator_audit_source.csv."),
            _summary_row("ACTUAL_OUTCOME_GOVERNED_FILE_CREATED_FLAG", actual_outcome_governed_file_created_flag, "Planner must not create governed ACTUAL_OUTCOME files."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    status_ok = int(remediation_status == REMEDIATION_STATUS_REQUIRED)
    missing_key_detected = int("sku_number" in schema.missing_required_join_keys)

    validation_frame = pd.DataFrame(
        [
            _validation_row(
                "STAGE1_REPORTS_ACTUAL_BLOCKED",
                "PASS" if stage1_actual_source_status == JOIN_BLOCKED_MISSING_KEYS else "FAIL",
                int(stage1_actual_source_status == JOIN_BLOCKED_MISSING_KEYS),
                f"stage1_actual_source_status={stage1_actual_source_status}",
            ),
            _validation_row(
                "REMEDIATION_STATUS_REQUIRED",
                "PASS" if status_ok else "FAIL",
                status_ok,
                f"remediation_status={remediation_status}",
            ),
            _validation_row(
                "ACTUAL_SOURCE_PATH_RECORDED",
                "PASS" if int(bool(schema.source_path)) else "FAIL",
                int(bool(schema.source_path)),
                f"actual_outcome_source_path={schema.source_path}",
            ),
            _validation_row(
                "MISSING_SKU_NUMBER_KEY_DETECTED",
                "PASS" if missing_key_detected else "FAIL",
                missing_key_detected,
                f"missing_required_join_keys={missing_join_keys_text}",
            ),
            _validation_row(
                "SAFE_SKU_ALIAS_NOT_AVAILABLE",
                "PASS" if schema.safe_sku_alias_exists_flag == 0 else "FAIL",
                int(schema.safe_sku_alias_exists_flag == 0),
                f"safe_sku_alias_exists_flag={schema.safe_sku_alias_exists_flag}",
            ),
            _validation_row(
                "NO_PROMOTION_SCOPED_READY_ACTUAL_OUTCOME_SOURCE",
                "PASS" if candidate_ready_found == 0 else "FAIL",
                int(candidate_ready_found == 0),
                f"candidate_promotion_scoped_ready_source_found_flag={candidate_ready_found}",
            ),
            _validation_row(
                "SOURCE_PACKETS_UNCHANGED",
                "PASS" if source_packets_mutated_flag == 0 else "FAIL",
                int(source_packets_mutated_flag == 0),
                "promotion_source_rows.csv and sibling source packet files are unchanged.",
            ),
            _validation_row(
                "OPERATOR_AUDIT_UNCHANGED",
                "PASS" if operator_audit_overwritten_flag == 0 else "FAIL",
                int(operator_audit_overwritten_flag == 0),
                f"operator_audit_source_path={operator_audit_path}",
            ),
            _validation_row(
                "NO_GOVERNED_ACTUAL_OUTCOME_FILE_CREATED",
                "PASS" if actual_outcome_governed_file_created_flag == 0 else "FAIL",
                int(actual_outcome_governed_file_created_flag == 0),
                f"actual_outcome_governed_path={actual_outcome_governed_path}",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# ACTUAL_OUTCOME Remediation Plan",
            "",
            "Planner-only remediation artifact.",
            "This step does not execute joins, does not run Stage 2 or Stage 3, and does not mutate source packets.",
            "",
            f"Promotion key: {promotion_key}",
            f"Promotion folder: {promotion_folder_name}",
            f"Remediation status: {remediation_status}",
            f"Stage 1 ACTUAL_OUTCOME status: {stage1_actual_source_status}",
            f"Current ACTUAL_OUTCOME source path: {schema.source_path}",
            f"Missing required join keys: {missing_join_keys_text or 'none'}",
            f"SKU-like columns found: {sku_like_text or 'none'}",
            f"Safe SKU alias exists: {schema.safe_sku_alias_exists_flag}",
            f"Promotion-scoped ready ACTUAL_OUTCOME source found: {candidate_ready_found}",
            "",
            "Required governed source contract fields:",
            *[f"- {field}" for field in REQUIRED_SOURCE_CONTRACT_FIELDS],
            "",
            "Recommendation: Keep Stage 1 blocked until a governed ACTUAL_OUTCOME source with the approved SKU-level key is available.",
        ]
    )

    return PromotionsMaterializedSourceActualOutcomeRemediationPlanResult(
        remediation_status=remediation_status,
        promotion_key=promotion_key,
        promotion_folder_name=promotion_folder_name,
        stage1_summary_path=str(stage1_summary_path),
        stage1_plan_path=str(stage1_plan_path),
        stage1_actual_source_status=stage1_actual_source_status,
        actual_outcome_source_path=schema.source_path,
        actual_outcome_source_exists_flag=schema.source_exists_flag,
        actual_outcome_source_row_count=schema.row_count,
        actual_outcome_source_column_count=schema.column_count,
        missing_required_join_keys=schema.missing_required_join_keys,
        sku_like_columns_found=schema.sku_like_columns_found,
        safe_sku_alias_exists_flag=schema.safe_sku_alias_exists_flag,
        candidate_promotion_scoped_ready_source_found_flag=candidate_ready_found,
        source_packets_mutated_flag=source_packets_mutated_flag,
        operator_audit_overwritten_flag=operator_audit_overwritten_flag,
        actual_outcome_governed_file_created_flag=actual_outcome_governed_file_created_flag,
        summary_frame=summary_frame,
        schema_diagnosis_frame=schema_frame,
        required_contract_frame=required_contract_frame,
        candidate_search_frame=candidate_search_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_actual_outcome_remediation_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceActualOutcomeRemediationPlanArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = _resolve_output_root(packet_root_path, output_root)
    result = build_promotions_materialized_source_actual_outcome_remediation_plan(
        packet_root=packet_root_path,
        promotion_key=promotion_key,
        output_root=output_root,
    )

    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_path = output_root_path / SUMMARY_FILE_NAME
    schema_path = output_root_path / SCHEMA_FILE_NAME
    contract_path = output_root_path / CONTRACT_FILE_NAME
    candidate_path = output_root_path / CANDIDATE_FILE_NAME
    validation_path = output_root_path / VALIDATION_FILE_NAME
    memo_path = output_root_path / MEMO_FILE_NAME

    result.summary_frame.to_csv(summary_path, index=False)
    result.schema_diagnosis_frame.to_csv(schema_path, index=False)
    result.required_contract_frame.to_csv(contract_path, index=False)
    result.candidate_search_frame.to_csv(candidate_path, index=False)
    result.validation_frame.to_csv(validation_path, index=False)
    memo_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceActualOutcomeRemediationPlanArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_path),
        schema_diagnosis_csv_path=str(schema_path),
        required_contract_csv_path=str(contract_path),
        candidate_search_csv_path=str(candidate_path),
        validation_csv_path=str(validation_path),
        memo_md_path=str(memo_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a planner-only ACTUAL_OUTCOME remediation artifact when SKU-level join keys are missing."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    artifacts = write_promotions_materialized_source_actual_outcome_remediation_plan(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    summary = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = dict(zip(summary["metric_name"].astype(str), summary["metric_value"])) if not summary.empty else {}
    print("remediation_status", _normalize_text(metrics.get("REMEDIATION_STATUS", "")))
    print("actual_outcome_source_path", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_PATH", "")))
    print("actual_outcome_source_exists_flag", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_EXISTS_FLAG", 0)))
    print("actual_outcome_source_row_count", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_ROW_COUNT", 0)))
    print("actual_outcome_source_column_count", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_COLUMN_COUNT", 0)))
    print("missing_required_join_keys", _normalize_text(metrics.get("MISSING_REQUIRED_JOIN_KEYS", "")))
    print("sku_like_columns_found", _normalize_text(metrics.get("SKU_LIKE_COLUMNS_FOUND", "")))
    print("safe_sku_alias_exists_flag", _normalize_text(metrics.get("SAFE_SKU_ALIAS_EXISTS_FLAG", 0)))
    print("candidate_promotion_scoped_ready_source_found_flag", _normalize_text(metrics.get("CANDIDATE_PROMOTION_SCOPED_READY_SOURCE_FOUND_FLAG", 0)))
    print("source_packets_mutated_flag", _normalize_text(metrics.get("SOURCE_PACKETS_MUTATED_FLAG", 0)))
    print("operator_audit_overwritten_flag", _normalize_text(metrics.get("OPERATOR_AUDIT_OVERWRITTEN_FLAG", 0)))
    print("actual_outcome_remediation_summary", artifacts.summary_csv_path)
    print("actual_outcome_source_schema_diagnosis", artifacts.schema_diagnosis_csv_path)
    print("actual_outcome_required_contract", artifacts.required_contract_csv_path)
    print("actual_outcome_candidate_search_results", artifacts.candidate_search_csv_path)
    print("actual_outcome_remediation_validation", artifacts.validation_csv_path)
    print("actual_outcome_remediation_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
