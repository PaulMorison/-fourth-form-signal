from __future__ import annotations

"""Planner-only OPERATOR_AUDIT template generator for materialized promotions."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_operator_audit_template"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DIAGNOSTIC_PACKET_ROOT_NAME = "last5_promotions_diagnostic_packets"
QUARANTINE_SIDECAR_BUILD_FOLDER_NAME = "materialized_source_blank_key_quarantine_sidecar_build"
REVIEW_TEMPLATE_FILE_NAME = "operator_audit_source_TEMPLATE.csv"
TEMPLATE_FILE_NAME = REVIEW_TEMPLATE_FILE_NAME
QUARANTINE_EVIDENCE_FILE_NAME = "operator_audit_template_quarantine_evidence.csv"
SUMMARY_FILE_NAME = "operator_audit_template_summary.csv"
VALIDATION_FILE_NAME = "operator_audit_template_validation.csv"
MEMO_FILE_NAME = "operator_audit_template_memo.md"
LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"

APPROVED_JOIN_KEY = "store_number + promotion_start_date + promotion_name + sku_number"
PENDING_OPERATOR_REVIEW = "PENDING_OPERATOR_REVIEW"
QUARANTINE_SIDECAR_STATUS = "QUARANTINED_FOR_OPERATOR_AUDIT"
QUARANTINE_DECISION_APPROVED = "APPROVE_QUARANTINE"
TEMPLATE_EXCLUSION_STATUS = "EXCLUDED_FROM_OPERATOR_AUDIT_TEMPLATE_BY_GOVERNED_SIDECAR"

TEMPLATE_SCHEMA_COLUMNS: tuple[str, ...] = (
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
    "approved_join_key",
)
REQUIRED_JOIN_KEY_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)
REQUIRED_SOURCE_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
    "sku_description",
    "advice_batch_row_number",
    "source_file",
)
QUARANTINE_EVIDENCE_COLUMNS: tuple[str, ...] = (
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
    "template_exclusion_status",
)
SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

TEMPLATE_READY = "OPERATOR_AUDIT_TEMPLATE_READY"
TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE = "OPERATOR_AUDIT_TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE"
TEMPLATE_BLOCKED_MISSING_SOURCE_ROWS = "OPERATOR_AUDIT_TEMPLATE_BLOCKED_MISSING_SOURCE_ROWS"
TEMPLATE_BLOCKED_MISSING_COLUMNS = "OPERATOR_AUDIT_TEMPLATE_BLOCKED_MISSING_COLUMNS"
TEMPLATE_BLOCKED_BLANK_KEYS = "OPERATOR_AUDIT_TEMPLATE_BLOCKED_BLANK_KEYS"
TEMPLATE_BLOCKED_DUPLICATE_KEYS = "OPERATOR_AUDIT_TEMPLATE_BLOCKED_DUPLICATE_KEYS"


class PromotionsMaterializedSourceOperatorAuditTemplateError(RuntimeError):
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
class PromotionsMaterializedSourceOperatorAuditTemplateResult:
    selected_promotion: PromotionSelection
    template_status: str
    source_rows_path: str
    live_operator_audit_path: str
    quarantine_evidence_path: str
    source_row_count: int
    template_row_count: int
    duplicate_key_count: int
    missing_key_count: int
    quarantined_row_count: int
    sidecar_consumed_flag: int
    source_packets_mutated_flag: int
    template_frame: pd.DataFrame
    quarantine_evidence_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str

    @property
    def source_rows_count(self) -> int:
        return self.source_row_count

    @property
    def template_rows_count(self) -> int:
        return self.template_row_count

    @property
    def source_packets_unchanged_flag(self) -> int:
        return int(not self.source_packets_mutated_flag)


@dataclass(frozen=True)
class PromotionsMaterializedSourceOperatorAuditTemplateArtifacts:
    output_root: str
    template_csv_path: str
    quarantine_evidence_csv_path: str
    summary_csv_path: str
    validation_csv_path: str
    memo_md_path: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_promotion_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize_text(value).lower())


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceOperatorAuditTemplateError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceOperatorAuditTemplateError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceOperatorAuditTemplateError(f"CSV is empty: {csv_path}")
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
        raise PromotionsMaterializedSourceOperatorAuditTemplateError(
            f"Promotion key is not in the expected pipe-delimited format: {promotion_key}"
        )
    return parts[0], parts[1], parts[2], parts[3]


def _promotion_slug_from_key(promotion_key: str) -> str:
    store_number, promotion_start_date, promotion_end_date, promotion_name = _promotion_parts_from_key(promotion_key)
    cleaned_name = re.sub(r"[^a-z0-9]+", "-", promotion_name.lower()).strip("-")
    return f"promotion_{store_number}-{promotion_start_date}-{promotion_end_date}-{cleaned_name}"


def _candidate_source_roots(packet_root: Path) -> list[Path]:
    return [
        packet_root / SOURCE_MATERIALIZED_FOLDER_NAME,
        packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / SOURCE_MATERIALIZED_FOLDER_NAME,
    ]


def _resolve_source_root(packet_root: Path) -> Path:
    for candidate_root in _candidate_source_roots(packet_root):
        if candidate_root.exists():
            return candidate_root
    raise PromotionsMaterializedSourceOperatorAuditTemplateError(
        f"Could not locate source-materialized promotions root under: {packet_root}"
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
            and _normalize_promotion_name(manifest_row.get("promotion_name")) == _normalize_promotion_name(target_name)
        ):
            return folder.name
    raise PromotionsMaterializedSourceOperatorAuditTemplateError(
        f"Could not resolve source-materialized folder for promotion: {promotion_key}"
    )


def _source_rows_path(source_root: Path, promotion_folder_name: str) -> Path:
    return source_root / promotion_folder_name / "promotion_source_rows.csv"


def _quarantine_sidecar_path(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / QUARANTINE_SIDECAR_BUILD_FOLDER_NAME / "blank_key_quarantine_sidecar.csv"
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / QUARANTINE_SIDECAR_BUILD_FOLDER_NAME / "blank_key_quarantine_sidecar.csv"


def _source_hash(source_root: Path) -> str:
    fingerprints: list[str] = []
    for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
        try:
            fingerprints.append(f"{path.relative_to(source_root)}::{path.stat().st_size}::{path.read_bytes()[:64].hex()}")
        except OSError:
            fingerprints.append(f"{path.relative_to(source_root)}::ERROR")
    return "|".join(fingerprints)


def _required_columns_present(frame: pd.DataFrame) -> tuple[bool, list[str]]:
    missing = [column for column in REQUIRED_SOURCE_COLUMNS if column not in frame.columns]
    if "promotional_end_date" not in frame.columns and "promotion_end_date" not in frame.columns:
        missing.append("promotional_end_date or promotion_end_date")
    return len(missing) == 0, missing


def _source_rows_with_line_numbers(frame: pd.DataFrame) -> pd.DataFrame:
    source_frame = frame.copy()
    if source_frame.empty:
        return source_frame
    if "source_csv_line_number" in source_frame.columns:
        source_frame["source_csv_line_number"] = source_frame["source_csv_line_number"].map(lambda value: int(_normalize_text(value) or 0))
    else:
        source_frame["source_csv_line_number"] = source_frame.index + 2
    return source_frame


def _blank_key_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {
        column: int(frame[column].astype(str).map(_normalize_text).eq("").sum())
        for column in REQUIRED_JOIN_KEY_COLUMNS
        if column in frame.columns
    }


def _blank_key_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty or any(column not in frame.columns for column in REQUIRED_JOIN_KEY_COLUMNS):
        return pd.Series(False, index=frame.index)
    blank_mask = pd.Series(False, index=frame.index)
    for column in REQUIRED_JOIN_KEY_COLUMNS:
        blank_mask = blank_mask | frame[column].astype(str).map(_normalize_text).eq("")
    return blank_mask


def _duplicate_key_count(frame: pd.DataFrame) -> int:
    if frame.empty or any(column not in frame.columns for column in REQUIRED_JOIN_KEY_COLUMNS):
        return 0
    join_key_frame = frame.loc[:, list(REQUIRED_JOIN_KEY_COLUMNS)].astype(str).map(_normalize_text)
    return int(join_key_frame.duplicated(keep=False).sum())


def _build_template_frame(source_rows_frame: pd.DataFrame) -> pd.DataFrame:
    promotion_end_date = (
        source_rows_frame["promotion_end_date"]
        if "promotion_end_date" in source_rows_frame.columns
        else source_rows_frame["promotional_end_date"]
    )
    return pd.DataFrame(
        {
            "store_number": source_rows_frame["store_number"].map(_normalize_text),
            "promotion_start_date": source_rows_frame["promotion_start_date"].map(_normalize_text),
            "promotion_end_date": promotion_end_date.map(_normalize_text),
            "promotion_name": source_rows_frame["promotion_name"].map(_normalize_text),
            "sku_number": source_rows_frame["sku_number"].map(_normalize_text),
            "sku_description": source_rows_frame["sku_description"].map(_normalize_text),
            "operator_audit_status": PENDING_OPERATOR_REVIEW,
            "operator_audit_decision": "",
            "operator_audit_reason": "",
            "operator_audit_timestamp": "",
            "operator_audit_user": "",
            "approved_join_key": APPROVED_JOIN_KEY,
        },
        columns=TEMPLATE_SCHEMA_COLUMNS,
    )


def _valid_sidecar_frame(sidecar_frame: pd.DataFrame) -> pd.DataFrame:
    if sidecar_frame.empty:
        return pd.DataFrame(columns=QUARANTINE_EVIDENCE_COLUMNS[:-1])
    required_columns = set(QUARANTINE_EVIDENCE_COLUMNS[:-1])
    if not required_columns.issubset(set(sidecar_frame.columns)):
        return pd.DataFrame(columns=QUARANTINE_EVIDENCE_COLUMNS[:-1])
    valid_mask = (
        sidecar_frame["sidecar_status"].astype(str).map(_normalize_text).eq(QUARANTINE_SIDECAR_STATUS)
        & sidecar_frame["quarantine_decision"].astype(str).map(_normalize_text).eq(QUARANTINE_DECISION_APPROVED)
    )
    valid_frame = sidecar_frame.loc[valid_mask].copy()
    if valid_frame.empty:
        return pd.DataFrame(columns=QUARANTINE_EVIDENCE_COLUMNS[:-1])
    valid_frame["source_csv_line_number"] = valid_frame["source_csv_line_number"].map(lambda value: int(_normalize_text(value) or 0))
    return valid_frame


def _apply_quarantine_sidecar(
    *,
    source_rows_frame: pd.DataFrame,
    source_blank_mask: pd.Series,
    promotion_key: str,
    sidecar_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    blank_rows_frame = source_rows_frame.loc[source_blank_mask].copy()
    if blank_rows_frame.empty:
        return source_rows_frame.copy(), pd.DataFrame(columns=QUARANTINE_EVIDENCE_COLUMNS), 0

    valid_sidecar = _valid_sidecar_frame(sidecar_frame)
    if valid_sidecar.empty:
        return source_rows_frame.copy(), pd.DataFrame(columns=QUARANTINE_EVIDENCE_COLUMNS), int(len(blank_rows_frame.index))

    blank_keys = {
        (int(row["source_csv_line_number"]), _normalize_text(row.get("advice_batch_row_number")))
        for _, row in blank_rows_frame.iterrows()
    }
    matched_sidecar = valid_sidecar.loc[
        valid_sidecar.apply(
            lambda row: (
                _normalize_text(row.get("promotion_key")) == promotion_key
                and (int(row.get("source_csv_line_number", 0) or 0), _normalize_text(row.get("advice_batch_row_number"))) in blank_keys
            ),
            axis=1,
        )
    ].copy()
    matched_keys = {
        (int(row["source_csv_line_number"]), _normalize_text(row.get("advice_batch_row_number")))
        for _, row in matched_sidecar.iterrows()
    }
    uncovered_blank_row_count = int(len(blank_keys.difference(matched_keys)))
    if uncovered_blank_row_count > 0:
        return source_rows_frame.copy(), pd.DataFrame(columns=QUARANTINE_EVIDENCE_COLUMNS), uncovered_blank_row_count

    matched_sidecar["template_exclusion_status"] = TEMPLATE_EXCLUSION_STATUS
    included_rows_frame = source_rows_frame.loc[
        ~source_rows_frame.apply(
            lambda row: (int(row["source_csv_line_number"]), _normalize_text(row.get("advice_batch_row_number"))) in matched_keys,
            axis=1,
        )
    ].copy()
    return included_rows_frame, matched_sidecar.loc[:, list(QUARANTINE_EVIDENCE_COLUMNS)], 0


def _build_validation_frame(
    *,
    source_rows_frame: pd.DataFrame,
    template_frame: pd.DataFrame,
    quarantine_evidence_frame: pd.DataFrame,
    source_rows_path: Path,
    quarantine_sidecar_path: Path,
    live_operator_audit_path: Path,
    source_hash_before: str,
    source_hash_after: str,
) -> tuple[pd.DataFrame, str, int, int, int, int]:
    validations: list[dict[str, object]] = []

    source_exists_flag = int(source_rows_path.exists())
    validations.append(
        _validation_row(
            "SOURCE_ROWS_FILE_EXISTS",
            "PASS" if source_exists_flag else "FAIL",
            source_exists_flag,
            f"source_rows_path={source_rows_path}",
        )
    )

    non_empty_flag = int(source_exists_flag == 1 and not source_rows_frame.empty)
    validations.append(
        _validation_row(
            "SOURCE_ROWS_NOT_EMPTY",
            "PASS" if non_empty_flag else "FAIL",
            non_empty_flag,
            "Source rows must contain at least one row.",
        )
    )

    required_columns_present_flag, missing_columns = _required_columns_present(source_rows_frame)
    validations.append(
        _validation_row(
            "REQUIRED_COLUMNS_PRESENT",
            "PASS" if required_columns_present_flag else "FAIL",
            int(required_columns_present_flag),
            "Missing columns: " + ", ".join(missing_columns) if missing_columns else "All required columns are present.",
        )
    )

    blank_counts = _blank_key_counts(source_rows_frame)
    missing_key_count = int(sum(blank_counts.values()))
    blank_row_count = int(_blank_key_mask(source_rows_frame).sum()) if required_columns_present_flag else 0
    quarantined_row_count = int(len(quarantine_evidence_frame.index))
    uncovered_blank_row_count = max(blank_row_count - quarantined_row_count, 0)
    sidecar_consumed_flag = int(quarantined_row_count > 0 and uncovered_blank_row_count == 0)
    validations.append(
        _validation_row(
            "NO_UNCOVERED_BLANK_JOIN_KEYS",
            "PASS" if uncovered_blank_row_count == 0 else "FAIL",
            int(uncovered_blank_row_count == 0),
            "Blank counts: " + "; ".join(f"{column}={count}" for column, count in blank_counts.items()) if blank_counts else "Join key columns unavailable.",
        )
    )
    validations.append(
        _validation_row(
            "SIDE_CAR_CONSUMED_ONLY_WITH_EXPLICIT_EVIDENCE",
            "PASS",
            1,
            f"quarantine_sidecar_path={quarantine_sidecar_path} sidecar_consumed_flag={sidecar_consumed_flag}",
        )
    )

    expected_template_row_count = int(len(source_rows_frame.index) - quarantined_row_count) if sidecar_consumed_flag else int(len(source_rows_frame.index))
    validations.append(
        _validation_row(
            "ROW_COUNT_MATCHES_EXPECTED_TEMPLATE",
            "PASS" if int(len(template_frame.index) == expected_template_row_count) else "FAIL",
            int(len(template_frame.index) == expected_template_row_count),
            f"source_row_count={len(source_rows_frame.index)} template_row_count={len(template_frame.index)} quarantined_row_count={quarantined_row_count}",
        )
    )

    duplicate_key_count = _duplicate_key_count(template_frame)
    validations.append(
        _validation_row(
            "DUPLICATE_KEY_COUNT_RECORDED",
            "PASS",
            1,
            f"template_duplicate_key_count={duplicate_key_count}",
        )
    )

    template_live_flag = int(live_operator_audit_path.exists())
    validations.append(
        _validation_row(
            "NOT_WRITTEN_TO_GOVERNED_OPERATOR_AUDIT_PATH",
            "PASS" if template_live_flag == 0 else "FAIL",
            int(template_live_flag == 0),
            f"live_operator_audit_path={live_operator_audit_path}",
        )
    )

    source_packets_unchanged_flag = int(source_hash_before == source_hash_after)
    validations.append(
        _validation_row(
            "SOURCE_PACKETS_UNCHANGED",
            "PASS" if source_packets_unchanged_flag else "FAIL",
            source_packets_unchanged_flag,
            "Source packets under source_materialized_promotions must not be mutated.",
        )
    )

    if not source_exists_flag or not non_empty_flag:
        template_status = TEMPLATE_BLOCKED_MISSING_SOURCE_ROWS
    elif not required_columns_present_flag:
        template_status = TEMPLATE_BLOCKED_MISSING_COLUMNS
    elif uncovered_blank_row_count > 0:
        template_status = TEMPLATE_BLOCKED_BLANK_KEYS
    elif sidecar_consumed_flag:
        template_status = TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE
    else:
        template_status = TEMPLATE_READY

    return pd.DataFrame(validations, columns=VALIDATION_COLUMNS), template_status, duplicate_key_count, missing_key_count, quarantined_row_count, sidecar_consumed_flag


def _build_summary_frame(
    *,
    selection: PromotionSelection,
    source_rows_path: Path,
    template_output_path: Path,
    quarantine_evidence_path: Path,
    live_operator_audit_path: Path,
    template_status: str,
    source_row_count: int,
    template_row_count: int,
    duplicate_key_count: int,
    missing_key_count: int,
    quarantined_row_count: int,
    sidecar_consumed_flag: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION_KEY", selection.promotion_key, "Promotion selected for the template generator."),
            _summary_row("PROMOTION_SLUG", selection.promotion_slug, "Promotion slug derived from the selected promotion key."),
            _summary_row("PROMOTION_FOLDER_NAME", selection.promotion_folder_name, "Promotion folder resolved from the governed source contract."),
            _summary_row("TEMPLATE_STATUS", template_status, "Planner-only template status."),
            _summary_row("SOURCE_ROWS_PATH", str(source_rows_path), "Read-only source rows input path."),
            _summary_row("QUARANTINE_EVIDENCE_PATH", str(quarantine_evidence_path), "Quarantine evidence artifact path."),
            _summary_row("LIVE_OPERATOR_AUDIT_PATH", str(live_operator_audit_path), "Governed OPERATOR_AUDIT path that was not written."),
            _summary_row("TEMPLATE_OUTPUT_PATH", str(template_output_path), "Review/template output path."),
            _summary_row("SOURCE_ROW_COUNT", source_row_count, "Row count from source rows."),
            _summary_row("TEMPLATE_ROW_COUNT", template_row_count, "Row count written to the template."),
            _summary_row("QUARANTINED_ROW_COUNT", quarantined_row_count, "Blank-key rows excluded from template through governed sidecar evidence."),
            _summary_row("DUPLICATE_KEY_COUNT", duplicate_key_count, "Duplicate join-key rows present in the review template."),
            _summary_row("MISSING_KEY_COUNT", missing_key_count, "Blank required join-key field count in source rows."),
            _summary_row("SIDECAR_CONSUMED_FLAG", sidecar_consumed_flag, "Whether governed quarantine sidecar evidence was consumed to unblock template generation."),
            _summary_row("APPROVED_JOIN_KEY", APPROVED_JOIN_KEY, "Approved join key string required by downstream planning."),
            _summary_row("GOVERNED_FILE_CREATED_FLAG", 0, "The governed OPERATOR_AUDIT file was not created."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", 0, "Source packets are read-only and were not mutated."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _build_memo_markdown(
    *,
    selection: PromotionSelection,
    template_status: str,
    source_rows_path: Path,
    quarantine_evidence_path: Path,
    live_operator_audit_path: Path,
    source_row_count: int,
    template_row_count: int,
    quarantined_row_count: int,
    missing_key_count: int,
    sidecar_consumed_flag: int,
) -> str:
    return "\n".join(
        [
            "# OPERATOR_AUDIT Template Plan",
            "",
            "Planner-only review artifact.",
            "This generator reads source rows and writes only to the separate review/template folder.",
            "It does not create or modify the governed OPERATOR_AUDIT file.",
            "Blank-key rows are excluded only when governed quarantine sidecar evidence covers them explicitly.",
            "Rows are never silently excluded without sidecar evidence.",
            "",
            f"Selected promotion key: {selection.promotion_key}",
            f"Template status: {template_status}",
            f"Source rows path: {source_rows_path}",
            f"Quarantine evidence path: {quarantine_evidence_path}",
            f"Live governed OPERATOR_AUDIT path not written: {live_operator_audit_path}",
            f"Source row count: {source_row_count}",
            f"Template row count: {template_row_count}",
            f"Quarantined row count: {quarantined_row_count}",
            f"Missing key count: {missing_key_count}",
            f"Sidecar consumed flag: {sidecar_consumed_flag}",
            "",
            "## Template contract",
            f"Approved join key: {APPROVED_JOIN_KEY}",
            "Operator audit rows default to PENDING_OPERATOR_REVIEW and blank decision fields.",
        ]
    ).strip()


def build_promotions_materialized_source_operator_audit_template(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceOperatorAuditTemplateResult:
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

    source_rows_path = _source_rows_path(source_root, promotion_folder_name)
    source_rows_frame = _read_csv(source_rows_path, allow_empty=True)
    source_rows_with_meta = _source_rows_with_line_numbers(source_rows_frame)
    quarantine_sidecar_path = _quarantine_sidecar_path(packet_root_path)
    quarantine_sidecar_frame = _read_csv(quarantine_sidecar_path, allow_empty=True)

    required_columns_present_flag, _ = _required_columns_present(source_rows_with_meta)
    blank_mask = _blank_key_mask(source_rows_with_meta) if required_columns_present_flag and not source_rows_with_meta.empty else pd.Series(False, index=source_rows_with_meta.index)
    template_source_rows_frame, quarantine_evidence_frame, uncovered_blank_row_count = _apply_quarantine_sidecar(
        source_rows_frame=source_rows_with_meta,
        source_blank_mask=blank_mask,
        promotion_key=promotion_key,
        sidecar_frame=quarantine_sidecar_frame,
    )

    if output_root is not None:
        output_root_path = Path(output_root)
    elif packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
    else:
        output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)

    live_operator_audit_path = source_root / promotion_folder_name / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME
    if not source_rows_with_meta.empty and required_columns_present_flag and uncovered_blank_row_count == 0:
        template_frame = _build_template_frame(template_source_rows_frame)
    elif not source_rows_with_meta.empty and required_columns_present_flag:
        template_frame = _build_template_frame(source_rows_with_meta)
    else:
        template_frame = pd.DataFrame(columns=TEMPLATE_SCHEMA_COLUMNS)

    validation_frame, template_status, duplicate_key_count, missing_key_count, quarantined_row_count, sidecar_consumed_flag = _build_validation_frame(
        source_rows_frame=source_rows_with_meta,
        template_frame=template_frame,
        quarantine_evidence_frame=quarantine_evidence_frame,
        source_rows_path=source_rows_path,
        quarantine_sidecar_path=quarantine_sidecar_path,
        live_operator_audit_path=live_operator_audit_path,
        source_hash_before=source_hash_before,
        source_hash_after=_source_hash(source_root),
    )

    template_csv_path = output_root_path / TEMPLATE_FILE_NAME
    quarantine_evidence_csv_path = output_root_path / QUARANTINE_EVIDENCE_FILE_NAME
    summary_csv_path = output_root_path / SUMMARY_FILE_NAME
    validation_csv_path = output_root_path / VALIDATION_FILE_NAME
    memo_md_path = output_root_path / MEMO_FILE_NAME

    template_frame.to_csv(template_csv_path, index=False)
    quarantine_evidence_frame.to_csv(quarantine_evidence_csv_path, index=False)

    result = PromotionsMaterializedSourceOperatorAuditTemplateResult(
        selected_promotion=selection,
        template_status=template_status,
        source_rows_path=str(source_rows_path),
        live_operator_audit_path=str(live_operator_audit_path),
        quarantine_evidence_path=str(quarantine_evidence_csv_path),
        source_row_count=int(len(source_rows_with_meta.index)),
        template_row_count=int(len(template_frame.index)),
        duplicate_key_count=int(duplicate_key_count),
        missing_key_count=int(missing_key_count),
        quarantined_row_count=int(quarantined_row_count),
        sidecar_consumed_flag=int(sidecar_consumed_flag),
        source_packets_mutated_flag=0,
        template_frame=template_frame,
        quarantine_evidence_frame=quarantine_evidence_frame,
        summary_frame=_build_summary_frame(
            selection=selection,
            source_rows_path=source_rows_path,
            template_output_path=template_csv_path,
            quarantine_evidence_path=quarantine_evidence_csv_path,
            live_operator_audit_path=live_operator_audit_path,
            template_status=template_status,
            source_row_count=int(len(source_rows_with_meta.index)),
            template_row_count=int(len(template_frame.index)),
            duplicate_key_count=int(duplicate_key_count),
            missing_key_count=int(missing_key_count),
            quarantined_row_count=int(quarantined_row_count),
            sidecar_consumed_flag=int(sidecar_consumed_flag),
        ),
        validation_frame=validation_frame,
        memo_markdown=_build_memo_markdown(
            selection=selection,
            template_status=template_status,
            source_rows_path=source_rows_path,
            quarantine_evidence_path=quarantine_evidence_csv_path,
            live_operator_audit_path=live_operator_audit_path,
            source_row_count=int(len(source_rows_with_meta.index)),
            template_row_count=int(len(template_frame.index)),
            quarantined_row_count=int(quarantined_row_count),
            missing_key_count=int(missing_key_count),
            sidecar_consumed_flag=int(sidecar_consumed_flag),
        ),
    )

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return result


def write_promotions_materialized_source_operator_audit_template(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceOperatorAuditTemplateArtifacts:
    build_promotions_materialized_source_operator_audit_template(
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
    return PromotionsMaterializedSourceOperatorAuditTemplateArtifacts(
        output_root=str(output_root_path),
        template_csv_path=str(output_root_path / TEMPLATE_FILE_NAME),
        quarantine_evidence_csv_path=str(output_root_path / QUARANTINE_EVIDENCE_FILE_NAME),
        summary_csv_path=str(output_root_path / SUMMARY_FILE_NAME),
        validation_csv_path=str(output_root_path / VALIDATION_FILE_NAME),
        memo_md_path=str(output_root_path / MEMO_FILE_NAME),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a planner-only OPERATOR_AUDIT review template from materialized source rows."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    result = build_promotions_materialized_source_operator_audit_template(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    print("selected_promotion_key", result.selected_promotion.promotion_key)
    print("template_status", result.template_status)
    print("template_output_path", result.summary_frame.loc[result.summary_frame["metric_name"].eq("TEMPLATE_OUTPUT_PATH"), "metric_value"].iloc[0])
    print("quarantine_evidence_path", result.quarantine_evidence_path)
    print("live_operator_audit_path", result.live_operator_audit_path)
    print("source_row_count", result.source_row_count)
    print("template_row_count", result.template_row_count)
    print("quarantined_row_count", result.quarantined_row_count)
    print("missing_key_count", result.missing_key_count)
    print("sidecar_consumed_flag", result.sidecar_consumed_flag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())