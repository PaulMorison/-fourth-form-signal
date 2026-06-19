from __future__ import annotations

"""Planner-only blank-key quarantine sidecar plan."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_blank_key_quarantine_sidecar_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DIAGNOSTIC_PACKET_ROOT_NAME = "last5_promotions_diagnostic_packets"
DECISION_CHECK_FOLDER_NAME = "materialized_source_blank_key_quarantine_decision_check"
DECISION_APPROVAL_FOLDER_NAME = "materialized_source_blank_key_quarantine_approval_plan"
LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"

BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE = "BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE"
BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR = "BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR"
BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION = "BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION"
BLANK_KEY_QUARANTINE_DECISION_INVALID = "BLANK_KEY_QUARANTINE_DECISION_INVALID"

BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INCOMPLETE = "BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INCOMPLETE"
BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INVALID = "BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INVALID"
BLANK_KEY_QUARANTINE_SIDECAR_NOT_REQUIRED_SOURCE_CORRECTION = "BLANK_KEY_QUARANTINE_SIDECAR_NOT_REQUIRED_SOURCE_CORRECTION"
BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD = "BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
REQUIRED_SCHEMA_COLUMNS: tuple[str, ...] = (
    "field_name",
    "required_flag",
    "data_type",
    "notes",
)
CANDIDATE_ROWS_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "source_csv_line_number",
    "advice_batch_row_number",
    "source_file",
    "promotion_name",
    "sku_number",
    "sku_description",
    "blank_key_fields",
    "quarantine_decision",
    "quarantine_reason",
    "approved_by",
    "approved_timestamp",
    "source_correction_available_flag",
    "sidecar_status",
    "sidecar_created_timestamp",
)
VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

DECISION_TEMPLATE_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "source_csv_line_number",
    "advice_batch_row_number",
    "source_file",
    "promotion_name",
    "sku_number",
    "sku_description",
    "blank_key_fields",
    "recommended_action",
    "quarantine_decision",
    "quarantine_reason",
    "approved_by",
    "approved_timestamp",
    "source_correction_available_flag",
    "notes",
)


class PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError(RuntimeError):
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
class PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanResult:
    selected_promotion: PromotionSelection
    sidecar_plan_status: str
    decision_checker_status: str
    decision_row_count: int
    source_rows_path: str
    live_operator_audit_path: str
    source_packets_mutated_flag: int
    required_schema_frame: pd.DataFrame
    candidate_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str

    @property
    def source_packets_unchanged_flag(self) -> int:
        return int(not self.source_packets_mutated_flag)


@dataclass(frozen=True)
class PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanArtifacts:
    output_root: str
    summary_csv_path: str
    required_schema_csv_path: str
    candidate_rows_csv_path: str
    validation_csv_path: str
    memo_md_path: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


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


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError(f"CSV is empty: {csv_path}")
    return frame


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError(
            f"Promotion key is not in the expected pipe-delimited format: {promotion_key}"
        )
    return parts[0], parts[1], parts[2], parts[3]


def _promotion_slug_from_key(promotion_key: str) -> str:
    store_number, promotion_start_date, promotion_end_date, promotion_name = _promotion_parts_from_key(promotion_key)
    cleaned_name = re.sub(r"[^a-z0-9]+", "-", promotion_name.lower()).strip("-")
    return f"promotion_{store_number}-{promotion_start_date}-{promotion_end_date}-{cleaned_name}"


def _normalized_promotion_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _candidate_source_roots(packet_root: Path) -> list[Path]:
    return [
        packet_root / SOURCE_MATERIALIZED_FOLDER_NAME,
        packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / SOURCE_MATERIALIZED_FOLDER_NAME,
    ]


def _resolve_source_root(packet_root: Path) -> Path:
    for root in _candidate_source_roots(packet_root):
        if root.exists():
            return root
    raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError(
        f"Could not locate source-materialized promotions root under packet root: {packet_root}"
    )


def _selected_promotion_folder_name(source_root: Path, promotion_key: str) -> str:
    target_store, target_start, target_end, target_name = _promotion_parts_from_key(promotion_key)
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
    raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError(
        f"Could not resolve source-materialized folder for promotion: {promotion_key}"
    )


def _source_rows_path(source_root: Path, promotion_folder_name: str) -> Path:
    return source_root / promotion_folder_name / "promotion_source_rows.csv"


def _source_hash(source_root: Path) -> str:
    fingerprints: list[str] = []
    for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
        try:
            fingerprints.append(f"{path.relative_to(source_root)}::{path.stat().st_size}::{path.read_bytes()[:64].hex()}")
        except OSError:
            fingerprints.append(f"{path.relative_to(source_root)}::ERROR")
    return "|".join(fingerprints)


def _decision_check_root(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / DECISION_CHECK_FOLDER_NAME
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / DECISION_CHECK_FOLDER_NAME


def _decision_approval_root(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / DECISION_APPROVAL_FOLDER_NAME
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / DECISION_APPROVAL_FOLDER_NAME


def _read_decision_checker_status(summary_frame: pd.DataFrame) -> str:
    if summary_frame.empty:
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError("Decision checker summary is empty.")
    match = summary_frame.loc[summary_frame["metric_name"].astype(str).eq("DECISION_CHECK_STATUS"), "metric_value"]
    if match.empty:
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError("DECISION_CHECK_STATUS metric was not found in checker summary.")
    return _normalize_text(match.iloc[0])


def _map_sidecar_status(decision_status: str) -> str:
    if decision_status == BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE:
        return BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INCOMPLETE
    if decision_status == BLANK_KEY_QUARANTINE_DECISION_INVALID:
        return BLANK_KEY_QUARANTINE_SIDECAR_BLOCKED_DECISION_INVALID
    if decision_status == BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION:
        return BLANK_KEY_QUARANTINE_SIDECAR_NOT_REQUIRED_SOURCE_CORRECTION
    if decision_status == BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR:
        return BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD
    raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanError(
        f"Unsupported decision checker status for sidecar planning: {decision_status}"
    )


def _required_schema_frame() -> pd.DataFrame:
    rows = [
        {"field_name": "promotion_key", "required_flag": 1, "data_type": "string", "notes": "Promotion identity key."},
        {"field_name": "source_csv_line_number", "required_flag": 1, "data_type": "integer", "notes": "Source CSV line number of malformed row."},
        {"field_name": "advice_batch_row_number", "required_flag": 1, "data_type": "string", "notes": "Upstream advice batch row identifier."},
        {"field_name": "source_file", "required_flag": 1, "data_type": "string", "notes": "Original source file name."},
        {"field_name": "promotion_name", "required_flag": 1, "data_type": "string", "notes": "Promotion name from source row."},
        {"field_name": "sku_number", "required_flag": 1, "data_type": "string", "notes": "SKU identifier, possibly blank for malformed row."},
        {"field_name": "sku_description", "required_flag": 1, "data_type": "string", "notes": "SKU description from source row."},
        {"field_name": "blank_key_fields", "required_flag": 1, "data_type": "string", "notes": "Comma-delimited blank key fields."},
        {"field_name": "quarantine_decision", "required_flag": 1, "data_type": "string", "notes": "Approved decision from decision template."},
        {"field_name": "quarantine_reason", "required_flag": 1, "data_type": "string", "notes": "Governed reason for decision."},
        {"field_name": "approved_by", "required_flag": 1, "data_type": "string", "notes": "Decision approver identity."},
        {"field_name": "approved_timestamp", "required_flag": 1, "data_type": "string", "notes": "Decision approval timestamp."},
        {"field_name": "source_correction_available_flag", "required_flag": 1, "data_type": "string", "notes": "Flag for upstream source-correction availability."},
        {"field_name": "sidecar_status", "required_flag": 1, "data_type": "string", "notes": "Future sidecar row lifecycle status."},
        {"field_name": "sidecar_created_timestamp", "required_flag": 1, "data_type": "string", "notes": "Future sidecar creation timestamp."},
    ]
    return pd.DataFrame(rows, columns=REQUIRED_SCHEMA_COLUMNS)


def _candidate_rows_frame(decision_template_frame: pd.DataFrame) -> pd.DataFrame:
    if decision_template_frame.empty:
        return pd.DataFrame(columns=CANDIDATE_ROWS_COLUMNS)
    rows: list[dict[str, object]] = []
    for _, row in decision_template_frame.iterrows():
        rows.append(
            {
                "promotion_key": _normalize_text(row.get("promotion_key")),
                "source_csv_line_number": int(row.get("source_csv_line_number", 0) or 0),
                "advice_batch_row_number": _normalize_text(row.get("advice_batch_row_number")),
                "source_file": _normalize_text(row.get("source_file")),
                "promotion_name": _normalize_text(row.get("promotion_name")),
                "sku_number": _normalize_text(row.get("sku_number")),
                "sku_description": _normalize_text(row.get("sku_description")),
                "blank_key_fields": _normalize_text(row.get("blank_key_fields")),
                "quarantine_decision": _normalize_text(row.get("quarantine_decision")),
                "quarantine_reason": _normalize_text(row.get("quarantine_reason")),
                "approved_by": _normalize_text(row.get("approved_by")),
                "approved_timestamp": _normalize_text(row.get("approved_timestamp")),
                "source_correction_available_flag": _normalize_text(row.get("source_correction_available_flag")),
                "sidecar_status": "",
                "sidecar_created_timestamp": "",
            }
        )
    return pd.DataFrame(rows, columns=CANDIDATE_ROWS_COLUMNS)


def _build_validation_frame(
    *,
    decision_checker_summary_path: Path,
    decision_checker_rows_path: Path,
    decision_template_path: Path,
    sidecar_status: str,
    decision_checker_status: str,
    candidate_rows_frame: pd.DataFrame,
    source_hash_before: str,
    source_hash_after: str,
) -> pd.DataFrame:
    validations: list[dict[str, object]] = []
    validations.append(
        _validation_row(
            "DECISION_CHECKER_SUMMARY_EXISTS",
            "PASS" if decision_checker_summary_path.exists() else "FAIL",
            int(decision_checker_summary_path.exists()),
            f"summary_path={decision_checker_summary_path}",
        )
    )
    validations.append(
        _validation_row(
            "DECISION_CHECKER_ROWS_EXISTS",
            "PASS" if decision_checker_rows_path.exists() else "FAIL",
            int(decision_checker_rows_path.exists()),
            f"rows_path={decision_checker_rows_path}",
        )
    )
    validations.append(
        _validation_row(
            "DECISION_TEMPLATE_EXISTS",
            "PASS" if decision_template_path.exists() else "FAIL",
            int(decision_template_path.exists()),
            f"decision_template_path={decision_template_path}",
        )
    )
    validations.append(
        _validation_row(
            "SIDECAR_STATUS_MAP_VALID",
            "PASS",
            1,
            f"decision_checker_status={decision_checker_status} sidecar_plan_status={sidecar_status}",
        )
    )
    ready_to_build_flag = int(sidecar_status == BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD)
    validations.append(
        _validation_row(
            "READY_STATUS_REQUIRES_APPROVED_DECISION",
            "PASS" if (ready_to_build_flag == 0 or decision_checker_status == BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR) else "FAIL",
            int(ready_to_build_flag == 0 or decision_checker_status == BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR),
            "Planner may mark READY_TO_BUILD only when checker status is READY_FOR_QUARANTINE_SIDECAR.",
        )
    )
    validations.append(
        _validation_row(
            "CANDIDATE_ROWS_PRESENT",
            "PASS" if int(len(candidate_rows_frame.index) > 0) else "FAIL",
            int(len(candidate_rows_frame.index) > 0),
            f"candidate_row_count={len(candidate_rows_frame.index)}",
        )
    )
    source_unchanged_flag = int(source_hash_before == source_hash_after)
    validations.append(
        _validation_row(
            "SOURCE_PACKETS_UNCHANGED",
            "PASS" if source_unchanged_flag else "FAIL",
            source_unchanged_flag,
            "Source packets under source_materialized_promotions must not be mutated.",
        )
    )
    return pd.DataFrame(validations, columns=VALIDATION_COLUMNS)


def _build_summary_frame(
    *,
    selection: PromotionSelection,
    sidecar_status: str,
    decision_checker_status: str,
    decision_row_count: int,
    summary_path: Path,
    rows_path: Path,
    decision_template_path: Path,
    live_operator_audit_path: Path,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION_KEY", selection.promotion_key, "Promotion selected for sidecar plan."),
            _summary_row("PROMOTION_SLUG", selection.promotion_slug, "Promotion slug derived from promotion key."),
            _summary_row("PROMOTION_FOLDER_NAME", selection.promotion_folder_name, "Promotion folder resolved from source manifests."),
            _summary_row("DECISION_CHECKER_STATUS", decision_checker_status, "Decision checker status consumed by this planner."),
            _summary_row("SIDECAR_PLAN_STATUS", sidecar_status, "Planner-only sidecar plan status."),
            _summary_row("DECISION_CHECKER_SUMMARY_PATH", str(summary_path), "Read-only decision checker summary input."),
            _summary_row("DECISION_CHECKER_ROWS_PATH", str(rows_path), "Read-only decision checker rows input."),
            _summary_row("DECISION_TEMPLATE_PATH", str(decision_template_path), "Read-only decision template input."),
            _summary_row("DECISION_ROW_COUNT", decision_row_count, "Decision row count from decision template."),
            _summary_row("LIVE_OPERATOR_AUDIT_PATH", str(live_operator_audit_path), "Governed OPERATOR_AUDIT path that was not written."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", 0, "Source packets are read-only and were not mutated."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _build_memo_markdown(
    *,
    selection: PromotionSelection,
    sidecar_status: str,
    decision_checker_status: str,
) -> str:
    return "\n".join(
        [
            "# Blank Key Quarantine Sidecar Plan",
            "",
            "Planner-only artifact.",
            "This planner does not build the quarantine sidecar and does not apply quarantine decisions.",
            "",
            f"Selected promotion key: {selection.promotion_key}",
            f"Decision checker status used: {decision_checker_status}",
            f"Sidecar plan status: {sidecar_status}",
            "",
            "## Governance",
            "This planner only defines future sidecar contract requirements.",
            "No source rows are mutated by this planner.",
            "No governed OPERATOR_AUDIT output is written by this planner.",
        ]
    ).strip()


def build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanResult:
    packet_root_path = Path(packet_root)
    source_root = _resolve_source_root(packet_root_path)
    source_hash_before = _source_hash(source_root)
    promotion_folder_name = _selected_promotion_folder_name(source_root, promotion_key)
    selection = PromotionSelection(
        promotion_key=promotion_key,
        promotion_slug=_promotion_slug_from_key(promotion_key),
        promotion_name=_promotion_parts_from_key(promotion_key)[3],
        promotion_start_date=_promotion_parts_from_key(promotion_key)[1],
        promotion_end_date=_promotion_parts_from_key(promotion_key)[2],
        promotion_folder_name=promotion_folder_name,
    )

    decision_check_root = _decision_check_root(packet_root_path)
    decision_approval_root = _decision_approval_root(packet_root_path)

    decision_checker_summary_path = decision_check_root / "blank_key_quarantine_decision_check_summary.csv"
    decision_checker_rows_path = decision_check_root / "blank_key_quarantine_decision_check_rows.csv"
    decision_template_path = decision_approval_root / "blank_key_quarantine_decision_TEMPLATE.csv"

    checker_summary_frame = _read_csv(decision_checker_summary_path)
    _ = _read_csv(decision_checker_rows_path)
    decision_template_frame = _read_csv(decision_template_path, allow_empty=True)

    decision_checker_status = _read_decision_checker_status(checker_summary_frame)
    sidecar_plan_status = _map_sidecar_status(decision_checker_status)

    required_schema_frame = _required_schema_frame()
    candidate_rows_frame = _candidate_rows_frame(decision_template_frame)

    if output_root is not None:
        output_root_path = Path(output_root)
    elif packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
    else:
        output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "blank_key_quarantine_sidecar_plan_summary.csv"
    required_schema_csv_path = output_root_path / "blank_key_quarantine_sidecar_required_schema.csv"
    candidate_rows_csv_path = output_root_path / "blank_key_quarantine_sidecar_candidate_rows.csv"
    validation_csv_path = output_root_path / "blank_key_quarantine_sidecar_plan_validation.csv"
    memo_md_path = output_root_path / "blank_key_quarantine_sidecar_plan_memo.md"

    source_rows_path = _source_rows_path(source_root, promotion_folder_name)
    live_operator_audit_path = source_root / promotion_folder_name / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME

    validation_frame = _build_validation_frame(
        decision_checker_summary_path=decision_checker_summary_path,
        decision_checker_rows_path=decision_checker_rows_path,
        decision_template_path=decision_template_path,
        sidecar_status=sidecar_plan_status,
        decision_checker_status=decision_checker_status,
        candidate_rows_frame=candidate_rows_frame,
        source_hash_before=source_hash_before,
        source_hash_after=_source_hash(source_root),
    )
    summary_frame = _build_summary_frame(
        selection=selection,
        sidecar_status=sidecar_plan_status,
        decision_checker_status=decision_checker_status,
        decision_row_count=int(len(decision_template_frame.index)),
        summary_path=decision_checker_summary_path,
        rows_path=decision_checker_rows_path,
        decision_template_path=decision_template_path,
        live_operator_audit_path=live_operator_audit_path,
    )
    memo_markdown = _build_memo_markdown(
        selection=selection,
        sidecar_status=sidecar_plan_status,
        decision_checker_status=decision_checker_status,
    )

    summary_frame.to_csv(summary_csv_path, index=False)
    required_schema_frame.to_csv(required_schema_csv_path, index=False)
    candidate_rows_frame.to_csv(candidate_rows_csv_path, index=False)
    validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanResult(
        selected_promotion=selection,
        sidecar_plan_status=sidecar_plan_status,
        decision_checker_status=decision_checker_status,
        decision_row_count=int(len(decision_template_frame.index)),
        source_rows_path=str(source_rows_path),
        live_operator_audit_path=str(live_operator_audit_path),
        source_packets_mutated_flag=0,
        required_schema_frame=required_schema_frame,
        candidate_rows_frame=candidate_rows_frame,
        summary_frame=summary_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanArtifacts:
    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=packet_root,
        promotion_key=promotion_key,
        output_root=output_root,
    )

    if output_root is not None:
        output_root_path = Path(output_root)
    else:
        packet_root_path = Path(packet_root)
        if packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
            output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
        else:
            output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "blank_key_quarantine_sidecar_plan_summary.csv"
    required_schema_csv_path = output_root_path / "blank_key_quarantine_sidecar_required_schema.csv"
    candidate_rows_csv_path = output_root_path / "blank_key_quarantine_sidecar_candidate_rows.csv"
    validation_csv_path = output_root_path / "blank_key_quarantine_sidecar_plan_validation.csv"
    memo_md_path = output_root_path / "blank_key_quarantine_sidecar_plan_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.required_schema_frame.to_csv(required_schema_csv_path, index=False)
    result.candidate_rows_frame.to_csv(candidate_rows_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyQuarantineSidecarPlanArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        required_schema_csv_path=str(required_schema_csv_path),
        candidate_rows_csv_path=str(candidate_rows_csv_path),
        validation_csv_path=str(validation_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a planner-only blank-key quarantine sidecar plan.")
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    write_promotions_materialized_source_blank_key_quarantine_sidecar_plan(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
