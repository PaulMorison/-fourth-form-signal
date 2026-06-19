from __future__ import annotations

"""Planner-only OPERATOR_AUDIT materialisation remediation plan for materialized promotions."""

from dataclasses import dataclass
from pathlib import Path
import argparse
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_operator_audit_remediation_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
PROMOTION_RUNS_FOLDER_NAME = "promotion_runs"
DIAGNOSTIC_PACKET_ROOT_NAME = "last5_promotions_diagnostic_packets"
LOCAL_INSPECTION_ROOT_NAME = "promotions_local_inspection"

STAGE_1_FOLDER_NAME = "materialized_source_join_key_validation"
STAGE_2_FOLDER_NAME = "materialized_source_join_spec_pack"
QUEUE_FOLDER_NAME = "materialized_source_multi_promotion_reconstruction_queue"
ISOLATION_PLAN_FOLDER_NAME = "materialized_source_promotion_isolation_plan"

RECOMMENDED_OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"
RECOMMENDED_OPERATOR_AUDIT_FILE_PATH = f"{SOURCE_MATERIALIZED_FOLDER_NAME}/{RECOMMENDED_OPERATOR_AUDIT_FILE_NAME}"
APPROVED_JOIN_KEY = "store_number + promotion_start_date + promotion_name + sku_number"
REQUIRED_JOIN_KEY_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)
MINIMUM_SCHEMA_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_end_date",
    "promotion_name",
    "sku_number",
    "sku_description",
    "operator_audit_status",
    "operator_audit_decision",
    "operator_audit_reason",
    "operator_audit_timestamp",
    "operator_audit_user",
)
OPTIONAL_SCHEMA_COLUMNS: tuple[str, ...] = ("approved_join_key",)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
SCHEMA_COLUMNS: tuple[str, ...] = (
    "field_name",
    "required_flag",
    "data_type",
    "notes",
)
FILE_CONTRACT_COLUMNS: tuple[str, ...] = (
    "file_name",
    "expected_location",
    "required_flag",
    "discovery_scope",
    "notes",
)
VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

REMEDIATION_REQUIRED = "OPERATOR_AUDIT_REMEDIATION_REQUIRED"
REMEDIATION_READY = "OPERATOR_AUDIT_REMEDIATION_READY_FOR_STAGE_1_2_RECHECK"


class PromotionsMaterializedSourceOperatorAuditRemediationPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionSelection:
    promotion_key: str
    promotion_slug: str
    promotion_name: str
    promotion_start_date: str
    promotion_end_date: str
    promotion_folder_name: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceOperatorAuditRemediationPlanResult:
    selected_promotion: PromotionSelection
    remediation_status: str
    operator_audit_like_file_exists_flag: int
    operator_audit_candidate_path: str
    data_materialization_remediation_required_flag: int
    code_change_required_flag: int
    stage_1_operator_source_status: str
    stage_1_actual_source_status: str
    stage_2_spec_status: str
    queue_status: str
    execution_mode_recommendation: str
    isolation_plan_status: str
    shared_root_risk_status: str
    summary_frame: pd.DataFrame
    expected_schema_frame: pd.DataFrame
    required_file_contract_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceOperatorAuditRemediationPlanArtifacts:
    output_root: str
    summary_csv_path: str
    expected_schema_csv_path: str
    required_file_contract_csv_path: str
    remediation_validation_csv_path: str
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
        raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError(f"CSV is empty: {csv_path}")
    return frame


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(validation_name: str, validation_status: str, validation_flag: int, details: str) -> dict[str, object]:
    return {
        "validation_name": validation_name,
        "validation_status": validation_status,
        "validation_flag": int(validation_flag),
        "details": details,
    }


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError(
            f"Promotion key is not in the expected pipe-delimited format: {promotion_key}"
        )
    store_number, promotion_start_date, promotion_end_date, promotion_name = parts
    return store_number, promotion_start_date, promotion_end_date, promotion_name


def _promotion_slug_from_key(promotion_key: str) -> str:
    store_number, promotion_start_date, promotion_end_date, promotion_name = _promotion_parts_from_key(promotion_key)
    cleaned_name = re.sub(r"[^a-z0-9]+", "-", promotion_name.lower()).strip("-")
    return f"promotion_{store_number}-{promotion_start_date}-{promotion_end_date}-{cleaned_name}"


def _normalized_promotion_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _promotion_key_matches(candidate_key: str, requested_key: str) -> bool:
    candidate_store, candidate_start, candidate_end, candidate_name = _promotion_parts_from_key(candidate_key)
    requested_store, requested_start, requested_end, requested_name = _promotion_parts_from_key(requested_key)
    return (
        candidate_store == requested_store
        and candidate_start == requested_start
        and candidate_end == requested_end
        and _normalized_promotion_name(candidate_name) == _normalized_promotion_name(requested_name)
    )


def _candidate_source_roots(packet_root: Path) -> list[Path]:
    return [
        packet_root / SOURCE_MATERIALIZED_FOLDER_NAME,
        packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / SOURCE_MATERIALIZED_FOLDER_NAME,
    ]


def _candidate_queue_roots(packet_root: Path) -> list[Path]:
    return [
        packet_root / "materialized_source_multi_promotion_reconstruction_queue",
        packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / "materialized_source_multi_promotion_reconstruction_queue",
    ]


def _candidate_isolation_roots(packet_root: Path) -> list[Path]:
    return [
        packet_root / ISOLATION_PLAN_FOLDER_NAME,
        packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / ISOLATION_PLAN_FOLDER_NAME,
    ]


def _candidate_stage_roots(packet_root: Path, promotion_slug: str, stage_folder_name: str) -> list[Path]:
    return [
        packet_root / PROMOTION_RUNS_FOLDER_NAME / promotion_slug / stage_folder_name,
        packet_root / "tmp" / LOCAL_INSPECTION_ROOT_NAME / promotion_slug / stage_folder_name,
    ]


def _selected_promotion_folder_name(source_root: Path, promotion_key: str) -> str:
    target_store, target_start, target_end, target_name = _promotion_parts_from_key(promotion_key)
    normalized_target_name = re.sub(r"\s+", " ", target_name).strip().upper()
    for folder in sorted(candidate for candidate in source_root.iterdir() if candidate.is_dir()):
        manifest_path = folder / "promotion_source_manifest.csv"
        if not manifest_path.exists():
            continue
        manifest_frame = _read_csv(manifest_path, allow_empty=True)
        if manifest_frame.empty:
            continue
        manifest_row = manifest_frame.iloc[0]
        if (
            _normalize_text(manifest_row.get("store_number")) == target_store
            and _normalize_text(manifest_row.get("promotion_start_date")) == target_start
            and _normalize_text(manifest_row.get("promotion_end_date")) == target_end
            and _normalized_promotion_name(_normalize_text(manifest_row.get("promotion_name"))) == _normalized_promotion_name(target_name)
        ):
            return folder.name
    raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError(
        f"Could not resolve source-materialized folder for promotion: {promotion_key}"
    )


def _resolve_existing_csv_path(candidates: Sequence[Path], file_name: str, *, allow_empty: bool = False) -> tuple[Path, pd.DataFrame]:
    for root in candidates:
        candidate = root / file_name
        if candidate.exists():
            return candidate, _read_csv(candidate, allow_empty=allow_empty)
    raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError(
        f"CSV not found in any candidate location: {file_name}"
    )


def _read_stage_summary(stage_root: Path, file_name: str) -> pd.DataFrame:
    return _read_csv(stage_root / file_name)


def _metric_lookup(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"]))


def _discover_operator_audit_candidate(source_root: Path, promotion_folder_root: Path) -> Path | None:
    recommended_path = source_root / RECOMMENDED_OPERATOR_AUDIT_FILE_NAME
    if recommended_path.exists():
        return recommended_path

    promotion_level_match = promotion_folder_root / RECOMMENDED_OPERATOR_AUDIT_FILE_NAME
    if promotion_level_match.exists():
        return promotion_level_match

    for candidate in sorted(promotion_folder_root.iterdir() if promotion_folder_root.exists() else []):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() not in {".csv", ".tsv"}:
            continue
        if re.search(r"operator|audit|review", candidate.name, flags=re.IGNORECASE):
            return candidate
    return None


def _is_blank_frame(frame: pd.DataFrame) -> bool:
    return frame.empty or frame.shape[0] == 0 or frame.shape[1] == 0


def _candidate_has_required_schema(frame: pd.DataFrame) -> tuple[bool, list[str]]:
    missing = [column for column in MINIMUM_SCHEMA_COLUMNS if column not in frame.columns]
    return len(missing) == 0, missing


def _candidate_has_required_join_key_columns(frame: pd.DataFrame) -> tuple[bool, list[str]]:
    missing = [column for column in REQUIRED_JOIN_KEY_COLUMNS if column not in frame.columns]
    return len(missing) == 0, missing


def _candidate_join_key_blank_issues(frame: pd.DataFrame) -> dict[str, int]:
    issues: dict[str, int] = {}
    for column in REQUIRED_JOIN_KEY_COLUMNS:
        if column not in frame.columns:
            continue
        issues[column] = int(frame[column].astype(str).map(_normalize_text).eq("").sum())
    return issues


def _candidate_promotion_identity_matches(frame: pd.DataFrame, selection: PromotionSelection) -> bool:
    if frame.empty:
        return False
    store_number, promotion_start_date, promotion_end_date, promotion_name = _promotion_parts_from_key(selection.promotion_key)
    normalized_name = re.sub(r"\s+", " ", promotion_name).strip().upper()
    normalized_names = frame.get("promotion_name", pd.Series(dtype="object")).astype(str).map(
        lambda value: re.sub(r"\s+", " ", _normalize_text(value)).strip().upper()
    )
    return bool(
        frame.get("store_number", pd.Series(dtype="object")).astype(str).map(_normalize_text).eq(store_number).all()
        and frame.get("promotion_start_date", pd.Series(dtype="object")).astype(str).map(_normalize_text).eq(promotion_start_date).all()
        and frame.get("promotion_end_date", pd.Series(dtype="object")).astype(str).map(_normalize_text).eq(promotion_end_date).all()
        and normalized_names.eq(normalized_name).all()
    )


def _candidate_approved_join_key_valid(frame: pd.DataFrame) -> tuple[bool, str]:
    if "approved_join_key" not in frame.columns:
        return True, "approved_join_key column not provided."
    normalized = frame["approved_join_key"].astype(str).map(_normalize_text)
    nonblank = normalized[normalized.ne("")]
    if nonblank.empty:
        return True, "approved_join_key column is present but blank; this is acceptable only when omitted from the contract."
    if not nonblank.eq(APPROVED_JOIN_KEY).all():
        return False, f"approved_join_key must equal {APPROVED_JOIN_KEY}."
    return True, f"approved_join_key matches {APPROVED_JOIN_KEY}."


def _build_expected_schema_frame() -> pd.DataFrame:
    rows = [
        {"field_name": column, "required_flag": 1, "data_type": "string", "notes": "Required governed operator-audit field."}
        for column in MINIMUM_SCHEMA_COLUMNS
    ]
    rows.append(
        {
            "field_name": "approved_join_key",
            "required_flag": 0,
            "data_type": "string",
            "notes": f"Optional. If present, it must equal {APPROVED_JOIN_KEY}.",
        }
    )
    return pd.DataFrame(rows, columns=SCHEMA_COLUMNS)


def _expected_operator_audit_file_path(source_root: Path, selection: PromotionSelection) -> str:
    return str(source_root / selection.promotion_folder_name / RECOMMENDED_OPERATOR_AUDIT_FILE_NAME)


def _build_required_file_contract_frame(selection: PromotionSelection, source_root: Path) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "file_name": RECOMMENDED_OPERATOR_AUDIT_FILE_NAME,
                "expected_location": _expected_operator_audit_file_path(source_root, selection),
                "required_flag": 1,
                "discovery_scope": "selected promotion source-materialized folder",
                "notes": "Recommended governed operator-audit materialization location for the selected promotion.",
            }
        ],
        columns=FILE_CONTRACT_COLUMNS,
    )


def _build_validation_frame(
    *,
    candidate_path: Path | None,
    candidate_frame: pd.DataFrame,
    selection: PromotionSelection,
    source_packet_hash_before: str,
    source_packet_hash_after: str,
    code_change_required_flag: int,
) -> tuple[pd.DataFrame, int, int]:
    checks: list[dict[str, object]] = []

    file_exists_flag = int(candidate_path is not None and candidate_path.exists())
    checks.append(
        _validation_row(
            "OPERATOR_AUDIT_FILE_EXISTS",
            "PASS" if file_exists_flag else "FAIL",
            file_exists_flag,
            f"candidate_path={candidate_path or ''}",
        )
    )

    non_empty_flag = int(file_exists_flag == 1 and not _is_blank_frame(candidate_frame))
    checks.append(
        _validation_row(
            "OPERATOR_AUDIT_FILE_NOT_EMPTY",
            "PASS" if non_empty_flag else "FAIL",
            non_empty_flag,
            "Operator-audit candidate file must contain at least one row and one column.",
        )
    )

    required_schema_present_flag, missing_schema_columns = _candidate_has_required_schema(candidate_frame)
    checks.append(
        _validation_row(
            "REQUIRED_SCHEMA_PRESENT",
            "PASS" if required_schema_present_flag else "FAIL",
            int(required_schema_present_flag),
            "Missing required columns: " + ", ".join(missing_schema_columns) if missing_schema_columns else "All required schema columns are present.",
        )
    )

    required_join_key_present_flag, missing_join_key_columns = _candidate_has_required_join_key_columns(candidate_frame)
    checks.append(
        _validation_row(
            "REQUIRED_JOIN_KEY_COLUMNS_PRESENT",
            "PASS" if required_join_key_present_flag else "FAIL",
            int(required_join_key_present_flag),
            "Missing join key columns: " + ", ".join(missing_join_key_columns) if missing_join_key_columns else "All required join key columns are present.",
        )
    )

    blank_join_key_issues = _candidate_join_key_blank_issues(candidate_frame)
    no_blank_join_key_flag = int(all(count == 0 for count in blank_join_key_issues.values()) if blank_join_key_issues else False)
    checks.append(
        _validation_row(
            "NO_BLANK_REQUIRED_JOIN_KEYS",
            "PASS" if no_blank_join_key_flag else "FAIL",
            no_blank_join_key_flag,
            "Blank counts: " + "; ".join(f"{column}={count}" for column, count in blank_join_key_issues.items())
            if blank_join_key_issues
            else "No join key columns available to validate.",
        )
    )

    no_blank_sku_flag = int(candidate_frame.get("sku_number", pd.Series(dtype="object")).astype(str).map(_normalize_text).ne("").all()) if "sku_number" in candidate_frame.columns and not candidate_frame.empty else 0
    checks.append(
        _validation_row(
            "NO_BLANK_SKU_NUMBER",
            "PASS" if no_blank_sku_flag else "FAIL",
            no_blank_sku_flag,
            "sku_number may not be blank.",
        )
    )

    no_blank_promotion_name_flag = int(candidate_frame.get("promotion_name", pd.Series(dtype="object")).astype(str).map(_normalize_text).ne("").all()) if "promotion_name" in candidate_frame.columns and not candidate_frame.empty else 0
    checks.append(
        _validation_row(
            "NO_BLANK_PROMOTION_NAME",
            "PASS" if no_blank_promotion_name_flag else "FAIL",
            no_blank_promotion_name_flag,
            "promotion_name may not be blank.",
        )
    )

    promotion_identity_matches_flag = int(_candidate_promotion_identity_matches(candidate_frame, selection)) if not candidate_frame.empty else 0
    checks.append(
        _validation_row(
            "PROMOTION_IDENTITY_MATCHES",
            "PASS" if promotion_identity_matches_flag else "FAIL",
            promotion_identity_matches_flag,
            "Candidate rows must match the selected promotion key identity.",
        )
    )

    approved_join_key_valid_flag, approved_join_key_reason = _candidate_approved_join_key_valid(candidate_frame)
    checks.append(
        _validation_row(
            "APPROVED_JOIN_KEY_VALID",
            "PASS" if approved_join_key_valid_flag else "FAIL",
            int(approved_join_key_valid_flag),
            approved_join_key_reason,
        )
    )

    source_packets_unchanged_flag = int(source_packet_hash_before == source_packet_hash_after)
    checks.append(
        _validation_row(
            "SOURCE_PACKETS_UNCHANGED",
            "PASS" if source_packets_unchanged_flag else "FAIL",
            source_packets_unchanged_flag,
            "Source packets under source_materialized_promotions must not be mutated.",
        )
    )

    candidate_valid_flag = int(
        file_exists_flag == 1
        and non_empty_flag == 1
        and required_schema_present_flag == 1
        and required_join_key_present_flag == 1
        and no_blank_join_key_flag == 1
        and no_blank_sku_flag == 1
        and no_blank_promotion_name_flag == 1
        and promotion_identity_matches_flag == 1
        and approved_join_key_valid_flag
    )
    remediation_required_flag = int(candidate_valid_flag == 0)
    recheck_required_flag = int(candidate_valid_flag == 1)
    checks.append(
        _validation_row(
            "MATERIALIZATION_REMEDIATION_REQUIRED",
            "PASS" if remediation_required_flag else "FAIL",
            remediation_required_flag,
            "Governed operator-audit materialization is still required until a valid candidate is available." if remediation_required_flag else "A valid candidate exists; rerun Stage 1 and Stage 2 before any Stage 3 retry.",
        )
    )
    checks.append(
        _validation_row(
            "STAGE_1_2_RECHECK_REQUIRED",
            "PASS" if recheck_required_flag else "FAIL",
            recheck_required_flag,
            "A valid operator-audit candidate exists and Stage 1/2 should be rechecked." if recheck_required_flag else "No valid operator-audit candidate is available for Stage 1/2 recheck.",
        )
    )
    checks.append(
        _validation_row(
            "CODE_CHANGE_NOT_REQUIRED",
            "PASS" if code_change_required_flag == 0 else "FAIL",
            int(code_change_required_flag == 0),
            "This remediation is governed data/materialization only; no code change is required.",
        )
    )

    return pd.DataFrame(checks, columns=VALIDATION_COLUMNS), remediation_required_flag, recheck_required_flag


def _build_summary_frame(
    *,
    source_root: Path,
    selection: PromotionSelection,
    candidate_path: Path | None,
    candidate_exists_flag: int,
    remediation_status: str,
    stage_1_operator_source_status: str,
    stage_1_actual_source_status: str,
    stage_2_spec_status: str,
    queue_status: str,
    execution_mode_recommendation: str,
    isolation_plan_status: str,
    shared_root_risk_status: str,
    code_change_required_flag: int,
    data_materialization_remediation_required_flag: int,
    recheck_required_flag: int,
    recommended_next_validation_step: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION_KEY", selection.promotion_key, "Promotion selected for the remediation plan."),
            _summary_row("PROMOTION_SLUG", selection.promotion_slug, "Promotion slug derived from the selected promotion key."),
            _summary_row("PROMOTION_FOLDER_NAME", selection.promotion_folder_name, "Source-materialized promotion folder used for the plan."),
            _summary_row("REMEDIATION_STATUS", remediation_status, "Overall remediation status for the planner-only contract."),
            _summary_row("CURRENT_OPERATOR_SOURCE_STATUS", stage_1_operator_source_status, "Current OPERATOR_AUDIT availability reported by Stage 1."),
            _summary_row("CURRENT_STAGE_1_STATUS", stage_1_operator_source_status, "Current Stage 1 operator-source status."),
            _summary_row("CURRENT_STAGE_1_ACTUAL_SOURCE_STATUS", stage_1_actual_source_status, "Current Stage 1 actual-outcome source status."),
            _summary_row("CURRENT_STAGE_2_STATUS", stage_2_spec_status, "Current Stage 2 join-spec status."),
            _summary_row("QUEUE_STATUS", queue_status, "Current promotion queue status."),
            _summary_row("EXECUTION_MODE_RECOMMENDATION", execution_mode_recommendation, "Planner recommendation from the reconstruction queue and isolation plan."),
            _summary_row("ISOLATION_PLAN_STATUS", isolation_plan_status, "Current promotion-isolation plan status."),
            _summary_row("SHARED_ROOT_RISK_STATUS", shared_root_risk_status, "Whether shared packet-root risk still exists."),
            _summary_row("EXPECTED_OPERATOR_AUDIT_FILE_PATH", _expected_operator_audit_file_path(source_root, selection), "Recommended governed file path for the operator-audit source."),
            _summary_row("EXPECTED_OPERATOR_AUDIT_FILE_NAME", RECOMMENDED_OPERATOR_AUDIT_FILE_NAME, "Recommended governed file name for the operator-audit source."),
            _summary_row("REQUIRED_JOIN_KEY_COLUMNS", ", ".join(REQUIRED_JOIN_KEY_COLUMNS), "Required join-key columns for the governed operator-audit source."),
            _summary_row("APPROVED_JOIN_KEY", APPROVED_JOIN_KEY, "Approved key string required by Stage 3."),
            _summary_row("OPERATOR_AUDIT_LIKE_FILE_EXISTS", candidate_exists_flag, "Whether an operator-audit-like file already exists."),
            _summary_row("DATA_MATERIALIZATION_REMEDIATION_REQUIRED", data_materialization_remediation_required_flag, "Whether governed data/materialization remediation is still required."),
            _summary_row("STAGE_1_2_RECHECK_REQUIRED", recheck_required_flag, "Whether Stage 1 and Stage 2 need to be rerun after materialization."),
            _summary_row("CODE_CHANGE_REQUIRED", code_change_required_flag, "Whether a runtime code change is required."),
            _summary_row("RECOMMENDED_NEXT_VALIDATION_STEP", recommended_next_validation_step, "Recommended next validation step before any Stage 3 retry."),
            _summary_row("EXPECTED_CANDIDATE_PATH", str(candidate_path or ""), "Discovered candidate file path, if any."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _build_memo_markdown(
    *,
    source_root: Path,
    selection: PromotionSelection,
    remediation_status: str,
    candidate_exists_flag: int,
    candidate_path: str,
    code_change_required_flag: int,
    data_materialization_remediation_required_flag: int,
    stage_1_operator_source_status: str,
    stage_2_spec_status: str,
    queue_status: str,
    execution_mode_recommendation: str,
    isolation_plan_status: str,
    shared_root_risk_status: str,
    recommended_next_validation_step: str,
) -> str:
    return "\n".join(
        [
            "# Operator-Audit Materialisation Remediation Plan",
            "",
            "This is a planner-only remediation artifact.",
            "It does not create, mutate, or publish the OPERATOR_AUDIT source.",
            "Stage 3 must not be rerun until Stage 1 and Stage 2 pass with a governed operator-audit source present.",
            "",
            f"Selected promotion key: {selection.promotion_key}",
            f"Promotion slug: {selection.promotion_slug}",
            f"Remediation status: {remediation_status}",
            f"Operator-audit-like file exists: {candidate_exists_flag}",
            f"Candidate path: {candidate_path or ''}",
            f"Current Stage 1 operator-source status: {stage_1_operator_source_status}",
            f"Current Stage 2 status: {stage_2_spec_status}",
            f"Queue status: {queue_status}",
            f"Execution mode recommendation: {execution_mode_recommendation}",
            f"Isolation plan status: {isolation_plan_status}",
            f"Shared-root risk status: {shared_root_risk_status}",
            f"Code change required: {code_change_required_flag}",
            f"Data/materialization remediation required: {data_materialization_remediation_required_flag}",
            "",
            "## Required governed file contract",
            f"Expected file path: {_expected_operator_audit_file_path(source_root, selection)}",
            f"Required join key: {APPROVED_JOIN_KEY}",
            "",
            "## Next validation step",
            recommended_next_validation_step,
        ]
    ).strip()


def build_promotions_materialized_source_operator_audit_remediation_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceOperatorAuditRemediationPlanResult:
    packet_root_path = Path(packet_root)
    source_root = next((candidate for candidate in _candidate_source_roots(packet_root_path) if candidate.exists()), None)
    if source_root is None:
        raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError(
            f"Could not locate source-materialized promotions root under: {packet_root_path}"
        )
    source_packet_before = _hash_source_folder(source_root)

    promotion_folder_name = _selected_promotion_folder_name(source_root, promotion_key)
    promotion_folder_root = source_root / promotion_folder_name
    selection = PromotionSelection(
        promotion_key=promotion_key,
        promotion_slug=promotion_folder_name,
        promotion_name=_promotion_parts_from_key(promotion_key)[3],
        promotion_start_date=_promotion_parts_from_key(promotion_key)[1],
        promotion_end_date=_promotion_parts_from_key(promotion_key)[2],
        promotion_folder_name=promotion_folder_name,
    )

    stage_1_root, stage_1_summary = _resolve_existing_csv_path(
        _candidate_stage_roots(packet_root_path, promotion_folder_name, STAGE_1_FOLDER_NAME),
        "materialized_source_join_key_validation_summary.csv",
    )
    stage_2_root, stage_2_summary = _resolve_existing_csv_path(
        _candidate_stage_roots(packet_root_path, promotion_folder_name, STAGE_2_FOLDER_NAME),
        "materialized_source_join_spec_summary.csv",
    )

    stage_1_metrics = _metric_lookup(stage_1_summary)
    stage_2_metrics = _metric_lookup(stage_2_summary)
    stage_1_operator_source_status = _normalize_text(stage_1_metrics.get("OPERATOR_SOURCE_STATUS"))
    stage_1_actual_source_status = _normalize_text(stage_1_metrics.get("ACTUAL_SOURCE_STATUS"))
    stage_2_spec_status = _normalize_text(stage_2_metrics.get("SPEC_STATUS"))

    queue_by_promotion_path, queue_frame = _resolve_existing_csv_path(
        _candidate_queue_roots(packet_root_path),
        "multi_promotion_reconstruction_queue_by_promotion.csv",
        allow_empty=True,
    )
    queue_row = _select_promotion_row(queue_frame, promotion_key)
    queue_status = _normalize_text(queue_row.get("queue_status"))
    execution_mode_recommendation = _normalize_text(queue_row.get("execution_mode_recommendation"))

    isolation_summary_path, isolation_summary = _resolve_existing_csv_path(
        _candidate_isolation_roots(packet_root_path),
        "promotion_isolation_plan_summary.csv",
        allow_empty=True,
    )
    isolation_stage_mapping_path = isolation_summary_path.with_name("promotion_isolation_plan_stage_mapping.csv")
    isolation_metrics = _metric_lookup(isolation_summary)
    isolation_plan_status = _normalize_text(isolation_metrics.get("ISOLATION_PLAN_STATUS"))
    shared_root_risk_status = _normalize_text(isolation_metrics.get("SHARED_ROOT_RISK_STATUS"))
    if not shared_root_risk_status and isolation_stage_mapping_path.exists():
        isolation_stage_mapping_frame = _read_csv(isolation_stage_mapping_path, allow_empty=True)
        shared_root_risk_status = _normalize_text(
            isolation_stage_mapping_frame.loc[
                isolation_stage_mapping_frame["promotion_key"].astype(str).eq(promotion_key),
                "shared_root_risk_status",
            ].iloc[0]
            if not isolation_stage_mapping_frame.empty and "shared_root_risk_status" in isolation_stage_mapping_frame.columns and not isolation_stage_mapping_frame.loc[isolation_stage_mapping_frame["promotion_key"].astype(str).eq(promotion_key)].empty
            else ""
        )

    candidate_path = _discover_operator_audit_candidate(source_root, promotion_folder_root)
    candidate_exists_flag = int(candidate_path is not None)
    candidate_frame = _read_csv(candidate_path, allow_empty=True) if candidate_path is not None else pd.DataFrame()

    code_change_required_flag = 0
    validation_frame, data_materialization_remediation_required_flag, recheck_required_flag = _build_validation_frame(
        candidate_path=candidate_path,
        candidate_frame=candidate_frame,
        selection=selection,
        source_packet_hash_before=source_packet_before,
        source_packet_hash_after=_hash_source_folder(source_root),
        code_change_required_flag=code_change_required_flag,
    )
    remediation_status = REMEDIATION_READY if recheck_required_flag else REMEDIATION_REQUIRED
    recommended_next_validation_step = (
        "Rerun Stage 1 join-key validation and Stage 2 join-spec pack against the governed operator-audit source, then retry Stage 3 PREVIEW_JOIN only after both stages pass."
        if recheck_required_flag
        else "Materialize a governed operator_audit_source.csv at the recommended location, then rerun Stage 1 join-key validation and Stage 2 join-spec pack before any Stage 3 retry."
    )

    summary_frame = _build_summary_frame(
        source_root=source_root,
        selection=selection,
        candidate_path=candidate_path,
        candidate_exists_flag=candidate_exists_flag,
        remediation_status=remediation_status,
        stage_1_operator_source_status=stage_1_operator_source_status,
        stage_1_actual_source_status=stage_1_actual_source_status,
        stage_2_spec_status=stage_2_spec_status,
        queue_status=queue_status,
        execution_mode_recommendation=execution_mode_recommendation,
        isolation_plan_status=isolation_plan_status,
        shared_root_risk_status=shared_root_risk_status,
        code_change_required_flag=code_change_required_flag,
        data_materialization_remediation_required_flag=data_materialization_remediation_required_flag,
        recheck_required_flag=recheck_required_flag,
        recommended_next_validation_step=recommended_next_validation_step,
    )
    expected_schema_frame = _build_expected_schema_frame()
    required_file_contract_frame = _build_required_file_contract_frame(selection, source_root)
    memo_markdown = _build_memo_markdown(
        source_root=source_root,
        selection=selection,
        remediation_status=remediation_status,
        candidate_exists_flag=candidate_exists_flag,
        candidate_path=str(candidate_path or ""),
        code_change_required_flag=code_change_required_flag,
        data_materialization_remediation_required_flag=data_materialization_remediation_required_flag,
        stage_1_operator_source_status=stage_1_operator_source_status,
        stage_2_spec_status=stage_2_spec_status,
        queue_status=queue_status,
        execution_mode_recommendation=execution_mode_recommendation,
        isolation_plan_status=isolation_plan_status,
        shared_root_risk_status=shared_root_risk_status,
        recommended_next_validation_step=recommended_next_validation_step,
    )

    return PromotionsMaterializedSourceOperatorAuditRemediationPlanResult(
        selected_promotion=selection,
        remediation_status=remediation_status,
        operator_audit_like_file_exists_flag=candidate_exists_flag,
        operator_audit_candidate_path=str(candidate_path or ""),
        data_materialization_remediation_required_flag=data_materialization_remediation_required_flag,
        code_change_required_flag=code_change_required_flag,
        stage_1_operator_source_status=stage_1_operator_source_status,
        stage_1_actual_source_status=stage_1_actual_source_status,
        stage_2_spec_status=stage_2_spec_status,
        queue_status=queue_status,
        execution_mode_recommendation=execution_mode_recommendation,
        isolation_plan_status=isolation_plan_status,
        shared_root_risk_status=shared_root_risk_status,
        summary_frame=summary_frame,
        expected_schema_frame=expected_schema_frame,
        required_file_contract_frame=required_file_contract_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_operator_audit_remediation_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceOperatorAuditRemediationPlanArtifacts:
    packet_root_path = Path(packet_root)
    if output_root is not None:
        output_root_path = Path(output_root)
    elif packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
    else:
        output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    result = build_promotions_materialized_source_operator_audit_remediation_plan(
        packet_root=packet_root_path,
        promotion_key=promotion_key,
        output_root=output_root_path,
    )
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "operator_audit_remediation_summary.csv"
    expected_schema_csv_path = output_root_path / "operator_audit_expected_schema.csv"
    required_file_contract_csv_path = output_root_path / "operator_audit_required_file_contract.csv"
    remediation_validation_csv_path = output_root_path / "operator_audit_remediation_validation.csv"
    memo_md_path = output_root_path / "operator_audit_remediation_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.expected_schema_frame.to_csv(expected_schema_csv_path, index=False)
    result.required_file_contract_frame.to_csv(required_file_contract_csv_path, index=False)
    result.validation_frame.to_csv(remediation_validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceOperatorAuditRemediationPlanArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        expected_schema_csv_path=str(expected_schema_csv_path),
        required_file_contract_csv_path=str(required_file_contract_csv_path),
        remediation_validation_csv_path=str(remediation_validation_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _select_promotion_row(frame: pd.DataFrame, promotion_key: str) -> pd.Series:
    if frame.empty:
        raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError("Queue by-promotion file is empty.")
    matches = frame.loc[frame["promotion_key"].astype(str).eq(promotion_key)]
    if matches.empty and "promotion_name" in frame.columns:
        normalized_requested_key = _promotion_key_matches
        requested_store, requested_start, requested_end, requested_name = _promotion_parts_from_key(promotion_key)
        normalized_requested_name = _normalized_promotion_name(requested_name)
        normalized_rows = frame.loc[
            frame["promotion_key"].astype(str).map(
                lambda value: _promotion_key_matches(value, promotion_key) if "|" in value else False
            )
        ]
        if not normalized_rows.empty:
            matches = normalized_rows
    if matches.empty:
        raise PromotionsMaterializedSourceOperatorAuditRemediationPlanError(
            f"Promotion key not found in queue: {promotion_key}"
        )
    return matches.iloc[0]


def _hash_source_folder(source_root: Path) -> str:
    fingerprints: list[str] = []
    if not source_root.exists():
        return ""
    for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
        try:
            fingerprints.append(f"{path.relative_to(source_root)}::{path.stat().st_size}::{path.read_bytes()[:64].hex()}")
        except OSError:
            fingerprints.append(f"{path.relative_to(source_root)}::ERROR")
    return "|".join(fingerprints)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a planner-only governed remediation contract for a missing OPERATOR_AUDIT source."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    artifacts = write_promotions_materialized_source_operator_audit_remediation_plan(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    summary_frame = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary_frame)
    print("selected_promotion_key", _normalize_text(metrics.get("SELECTED_PROMOTION_KEY", "")))
    print("remediation_status", _normalize_text(metrics.get("REMEDIATION_STATUS", "")))
    print("expected_operator_audit_file_path", _normalize_text(metrics.get("EXPECTED_OPERATOR_AUDIT_FILE_PATH", "")))
    print("required_join_key_columns", _normalize_text(metrics.get("REQUIRED_JOIN_KEY_COLUMNS", "")))
    print("operator_audit_like_file_exists", _normalize_text(metrics.get("OPERATOR_AUDIT_LIKE_FILE_EXISTS", 0)))
    print("code_change_required", _normalize_text(metrics.get("CODE_CHANGE_REQUIRED", 0)))
    print("data_materialization_remediation_required", _normalize_text(metrics.get("DATA_MATERIALIZATION_REMEDIATION_REQUIRED", 0)))
    print("operator_audit_remediation_summary", artifacts.summary_csv_path)
    print("operator_audit_expected_schema", artifacts.expected_schema_csv_path)
    print("operator_audit_required_file_contract", artifacts.required_file_contract_csv_path)
    print("operator_audit_remediation_validation", artifacts.remediation_validation_csv_path)
    print("operator_audit_remediation_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())