from __future__ import annotations

"""Planner-only readiness check for future OPERATOR_AUDIT template promotion."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_operator_audit_promotion_readiness"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DIAGNOSTIC_PACKET_ROOT_NAME = "last5_promotions_diagnostic_packets"
TEMPLATE_FOLDER_NAME = "materialized_source_operator_audit_template"
QUARANTINE_SIDECAR_BUILD_FOLDER_NAME = "materialized_source_blank_key_quarantine_sidecar_build"
TEMPLATE_FILE_NAME = "operator_audit_source_TEMPLATE.csv"
TEMPLATE_SUMMARY_FILE_NAME = "operator_audit_template_summary.csv"
QUARANTINE_EVIDENCE_FILE_NAME = "operator_audit_template_quarantine_evidence.csv"
SIDECAR_FILE_NAME = "blank_key_quarantine_sidecar.csv"
SUMMARY_FILE_NAME = "operator_audit_promotion_readiness_summary.csv"
CHECKS_FILE_NAME = "operator_audit_promotion_readiness_checks.csv"
CANDIDATE_FILE_NAME = "operator_audit_promotion_readiness_candidate.csv"
VALIDATION_FILE_NAME = "operator_audit_promotion_readiness_validation.csv"
MEMO_FILE_NAME = "operator_audit_promotion_readiness_memo.md"
LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"

TEMPLATE_READY = "OPERATOR_AUDIT_TEMPLATE_READY"
TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE = "OPERATOR_AUDIT_TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE"

OPERATOR_AUDIT_PROMOTION_READY = "OPERATOR_AUDIT_PROMOTION_READY"
OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_NOT_READY = "OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_NOT_READY"
OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_MISSING = "OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_MISSING"
OPERATOR_AUDIT_PROMOTION_BLOCKED_BLANK_JOIN_KEYS = "OPERATOR_AUDIT_PROMOTION_BLOCKED_BLANK_JOIN_KEYS"
OPERATOR_AUDIT_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH = "OPERATOR_AUDIT_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH"
OPERATOR_AUDIT_PROMOTION_BLOCKED_QUARANTINE_EVIDENCE_MISMATCH = "OPERATOR_AUDIT_PROMOTION_BLOCKED_QUARANTINE_EVIDENCE_MISMATCH"
OPERATOR_AUDIT_PROMOTION_BLOCKED_GOVERNED_FILE_ALREADY_EXISTS = "OPERATOR_AUDIT_PROMOTION_BLOCKED_GOVERNED_FILE_ALREADY_EXISTS"
OPERATOR_AUDIT_PROMOTION_BLOCKED_SOURCE_MUTATION_RISK = "OPERATOR_AUDIT_PROMOTION_BLOCKED_SOURCE_MUTATION_RISK"

REQUIRED_JOIN_KEY_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
CHECKS_COLUMNS: tuple[str, ...] = (
    "readiness_check",
    "check_status",
    "check_flag",
    "metric_value",
    "details",
)
CANDIDATE_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "promotion_folder_name",
    "template_status_used",
    "template_source_path",
    "quarantine_evidence_path",
    "sidecar_path",
    "future_governed_destination_path",
    "source_row_count",
    "template_row_count",
    "quarantined_row_count",
    "readiness_status",
)
VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)


class PromotionsMaterializedSourceOperatorAuditPromotionReadinessError(RuntimeError):
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
class PromotionsMaterializedSourceOperatorAuditPromotionReadinessResult:
    selected_promotion: PromotionSelection
    readiness_status: str
    template_status_used: str
    source_row_count: int
    template_row_count: int
    quarantined_row_count: int
    blank_join_key_count_in_template: int
    quarantine_evidence_matched_flag: int
    future_governed_destination_path: str
    source_packets_mutated_flag: int
    governed_file_created_flag: int
    checks_frame: pd.DataFrame
    candidate_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str

    @property
    def source_packets_unchanged_flag(self) -> int:
        return int(not self.source_packets_mutated_flag)


@dataclass(frozen=True)
class PromotionsMaterializedSourceOperatorAuditPromotionReadinessArtifacts:
    output_root: str
    summary_csv_path: str
    checks_csv_path: str
    candidate_csv_path: str
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
        raise PromotionsMaterializedSourceOperatorAuditPromotionReadinessError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceOperatorAuditPromotionReadinessError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceOperatorAuditPromotionReadinessError(f"CSV is empty: {csv_path}")
    return frame


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _check_row(readiness_check: str, check_status: str, check_flag: int, metric_value: object, details: str) -> dict[str, object]:
    return {
        "readiness_check": readiness_check,
        "check_status": check_status,
        "check_flag": int(check_flag),
        "metric_value": metric_value,
        "details": details,
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
        raise PromotionsMaterializedSourceOperatorAuditPromotionReadinessError(
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
    raise PromotionsMaterializedSourceOperatorAuditPromotionReadinessError(
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
    raise PromotionsMaterializedSourceOperatorAuditPromotionReadinessError(
        f"Could not resolve source-materialized folder for promotion: {promotion_key}"
    )


def _source_hash(source_root: Path) -> str:
    fingerprints: list[str] = []
    for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
        try:
            fingerprints.append(f"{path.relative_to(source_root)}::{path.stat().st_size}::{path.read_bytes()[:64].hex()}")
        except OSError:
            fingerprints.append(f"{path.relative_to(source_root)}::ERROR")
    return "|".join(fingerprints)


def _template_root(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / TEMPLATE_FOLDER_NAME
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / TEMPLATE_FOLDER_NAME


def _sidecar_path(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / QUARANTINE_SIDECAR_BUILD_FOLDER_NAME / SIDECAR_FILE_NAME
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / QUARANTINE_SIDECAR_BUILD_FOLDER_NAME / SIDECAR_FILE_NAME


def _metric_lookup(summary_frame: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if summary_frame.empty or "metric_name" not in summary_frame.columns or "metric_value" not in summary_frame.columns:
        return lookup
    for row in summary_frame.itertuples(index=False):
        lookup[str(getattr(row, "metric_name"))] = _normalize_text(getattr(row, "metric_value"))
    return lookup


def _to_int(value: object) -> int:
    text = _normalize_text(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError as exc:
        raise PromotionsMaterializedSourceOperatorAuditPromotionReadinessError(f"Expected integer-like value, got {value!r}") from exc


def _blank_join_key_count(frame: pd.DataFrame) -> int:
    if frame.empty or any(column not in frame.columns for column in REQUIRED_JOIN_KEY_COLUMNS):
        return 0 if not frame.empty else 0
    blank_mask = pd.Series(False, index=frame.index)
    for column in REQUIRED_JOIN_KEY_COLUMNS:
        blank_mask = blank_mask | frame[column].astype(str).map(_normalize_text).eq("")
    return int(blank_mask.sum())


def _evidence_matches_sidecar(evidence_frame: pd.DataFrame, sidecar_frame: pd.DataFrame) -> int:
    if evidence_frame.empty:
        return int(sidecar_frame.empty)
    if sidecar_frame.empty:
        return 0
    evidence_rows = set(evidence_frame["advice_batch_row_number"].astype(str).map(_normalize_text))
    sidecar_rows = set(sidecar_frame["advice_batch_row_number"].astype(str).map(_normalize_text))
    return int(evidence_rows == sidecar_rows)


def _determine_status(
    *,
    template_exists_flag: int,
    template_status_used: str,
    blank_join_key_count: int,
    row_count_match_flag: int,
    quarantine_evidence_match_flag: int,
    governed_file_exists_flag: int,
    source_unchanged_flag: int,
) -> str:
    if not source_unchanged_flag:
        return OPERATOR_AUDIT_PROMOTION_BLOCKED_SOURCE_MUTATION_RISK
    if governed_file_exists_flag:
        return OPERATOR_AUDIT_PROMOTION_BLOCKED_GOVERNED_FILE_ALREADY_EXISTS
    if not template_exists_flag:
        return OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_MISSING
    if template_status_used not in {TEMPLATE_READY, TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE}:
        return OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_NOT_READY
    if blank_join_key_count > 0:
        return OPERATOR_AUDIT_PROMOTION_BLOCKED_BLANK_JOIN_KEYS
    if not row_count_match_flag:
        return OPERATOR_AUDIT_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH
    if not quarantine_evidence_match_flag:
        return OPERATOR_AUDIT_PROMOTION_BLOCKED_QUARANTINE_EVIDENCE_MISMATCH
    return OPERATOR_AUDIT_PROMOTION_READY


def build_promotions_materialized_source_operator_audit_promotion_readiness(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceOperatorAuditPromotionReadinessResult:
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

    template_root = _template_root(packet_root_path)
    template_summary_path = template_root / TEMPLATE_SUMMARY_FILE_NAME
    template_path = template_root / TEMPLATE_FILE_NAME
    quarantine_evidence_path = template_root / QUARANTINE_EVIDENCE_FILE_NAME
    sidecar_path = _sidecar_path(packet_root_path)
    future_governed_destination_path = source_root / promotion_folder_name / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME

    template_summary_frame = _read_csv(template_summary_path)
    template_exists_flag = int(template_path.exists())
    template_frame = _read_csv(template_path, allow_empty=True) if template_exists_flag else pd.DataFrame()
    quarantine_evidence_frame = _read_csv(quarantine_evidence_path, allow_empty=True)
    sidecar_frame = _read_csv(sidecar_path, allow_empty=True)

    summary_lookup = _metric_lookup(template_summary_frame)
    template_status_used = summary_lookup.get("TEMPLATE_STATUS", "")
    source_row_count = _to_int(summary_lookup.get("SOURCE_ROW_COUNT", 0))
    template_row_count = _to_int(summary_lookup.get("TEMPLATE_ROW_COUNT", len(template_frame.index)))
    quarantined_row_count = _to_int(summary_lookup.get("QUARANTINED_ROW_COUNT", len(quarantine_evidence_frame.index)))

    blank_join_key_count = _blank_join_key_count(template_frame)
    row_count_match_flag = int(template_row_count == source_row_count - quarantined_row_count)
    quarantine_evidence_count_match_flag = int(len(quarantine_evidence_frame.index) == quarantined_row_count)
    quarantine_evidence_match_flag = int(quarantine_evidence_count_match_flag and _evidence_matches_sidecar(quarantine_evidence_frame, sidecar_frame))
    governed_file_exists_flag = int(future_governed_destination_path.exists())
    source_unchanged_flag = int(source_hash_before == _source_hash(source_root))

    readiness_status = _determine_status(
        template_exists_flag=template_exists_flag,
        template_status_used=template_status_used,
        blank_join_key_count=blank_join_key_count,
        row_count_match_flag=row_count_match_flag,
        quarantine_evidence_match_flag=quarantine_evidence_match_flag,
        governed_file_exists_flag=governed_file_exists_flag,
        source_unchanged_flag=source_unchanged_flag,
    )

    checks_frame = pd.DataFrame(
        [
            _check_row("TEMPLATE_STATUS_READY", "PASS" if template_status_used in {TEMPLATE_READY, TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE} else "FAIL", int(template_status_used in {TEMPLATE_READY, TEMPLATE_READY_WITH_QUARANTINE_EVIDENCE}), template_status_used, "Template summary status must be READY or READY_WITH_QUARANTINE_EVIDENCE."),
            _check_row("TEMPLATE_FILE_EXISTS", "PASS" if template_exists_flag else "FAIL", template_exists_flag, template_exists_flag, f"template_path={template_path}"),
            _check_row("ROW_COUNT_MATCH", "PASS" if row_count_match_flag else "FAIL", row_count_match_flag, template_row_count, f"source_row_count={source_row_count} quarantined_row_count={quarantined_row_count}"),
            _check_row("NO_BLANK_JOIN_KEYS_IN_TEMPLATE", "PASS" if blank_join_key_count == 0 else "FAIL", int(blank_join_key_count == 0), blank_join_key_count, "Template must not contain blank required join keys."),
            _check_row("QUARANTINE_EVIDENCE_MATCHES_SIDECAR", "PASS" if quarantine_evidence_match_flag else "FAIL", quarantine_evidence_match_flag, len(quarantine_evidence_frame.index), f"sidecar_row_count={len(sidecar_frame.index)}"),
            _check_row("SOURCE_PACKETS_UNCHANGED", "PASS" if source_unchanged_flag else "FAIL", source_unchanged_flag, source_unchanged_flag, "Source packets under source_materialized_promotions must not be mutated."),
            _check_row("GOVERNED_FILE_ABSENT", "PASS" if governed_file_exists_flag == 0 else "FAIL", int(governed_file_exists_flag == 0), governed_file_exists_flag, f"future_governed_destination_path={future_governed_destination_path}"),
        ],
        columns=CHECKS_COLUMNS,
    )

    candidate_frame = pd.DataFrame(
        [
            {
                "promotion_key": selection.promotion_key,
                "promotion_folder_name": selection.promotion_folder_name,
                "template_status_used": template_status_used,
                "template_source_path": str(template_path),
                "quarantine_evidence_path": str(quarantine_evidence_path),
                "sidecar_path": str(sidecar_path),
                "future_governed_destination_path": str(future_governed_destination_path),
                "source_row_count": source_row_count,
                "template_row_count": template_row_count,
                "quarantined_row_count": quarantined_row_count,
                "readiness_status": readiness_status,
            }
        ],
        columns=CANDIDATE_COLUMNS,
    )

    summary_frame = pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION_KEY", selection.promotion_key, "Promotion selected for OPERATOR_AUDIT promotion-readiness checking."),
            _summary_row("PROMOTION_SLUG", selection.promotion_slug, "Promotion slug derived from the selected promotion key."),
            _summary_row("PROMOTION_FOLDER_NAME", selection.promotion_folder_name, "Promotion folder resolved from source manifests."),
            _summary_row("READINESS_STATUS", readiness_status, "Planner-only readiness status for future governed promotion of the review template."),
            _summary_row("TEMPLATE_STATUS_USED", template_status_used, "Template status consumed from the OPERATOR_AUDIT template summary."),
            _summary_row("SOURCE_ROW_COUNT", source_row_count, "Row count reported by the template summary."),
            _summary_row("TEMPLATE_ROW_COUNT", template_row_count, "Review-only template row count."),
            _summary_row("QUARANTINED_ROW_COUNT", quarantined_row_count, "Quarantine evidence row count expected to reconcile with source minus template rows."),
            _summary_row("BLANK_JOIN_KEY_COUNT_IN_TEMPLATE", blank_join_key_count, "Blank required join-key rows present in the review-only template."),
            _summary_row("QUARANTINE_EVIDENCE_MATCHED_FLAG", quarantine_evidence_match_flag, "Whether quarantine evidence exactly matches the governed sidecar by advice_batch_row_number."),
            _summary_row("FUTURE_GOVERNED_DESTINATION_PATH", str(future_governed_destination_path), "Future governed destination path that this planner does not write."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", 0, "Source packets are read-only and were not mutated."),
            _summary_row("GOVERNED_FILE_CREATED_FLAG", 0, "This readiness planner did not create the governed OPERATOR_AUDIT file."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    validation_frame = pd.DataFrame(
        [
            _validation_row("CHECKS_FILE_ROWS_PRESENT", "PASS" if not checks_frame.empty else "FAIL", int(not checks_frame.empty), f"check_row_count={len(checks_frame.index)}"),
            _validation_row("CANDIDATE_ROWS_PRESENT", "PASS" if len(candidate_frame.index) == 1 else "FAIL", int(len(candidate_frame.index) == 1), f"candidate_row_count={len(candidate_frame.index)}"),
            _validation_row("SOURCE_PACKETS_UNCHANGED", "PASS" if source_unchanged_flag else "FAIL", source_unchanged_flag, "Source packets under source_materialized_promotions must not be mutated."),
            _validation_row("GOVERNED_FILE_NOT_CREATED", "PASS", 1, f"future_governed_destination_path={future_governed_destination_path}"),
            _validation_row("READINESS_STATUS_ALLOWED", "PASS" if readiness_status in {
                OPERATOR_AUDIT_PROMOTION_READY,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_NOT_READY,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_MISSING,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_BLANK_JOIN_KEYS,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_QUARANTINE_EVIDENCE_MISMATCH,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_GOVERNED_FILE_ALREADY_EXISTS,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_SOURCE_MUTATION_RISK,
            } else "FAIL", int(readiness_status in {
                OPERATOR_AUDIT_PROMOTION_READY,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_NOT_READY,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_TEMPLATE_MISSING,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_BLANK_JOIN_KEYS,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_ROW_COUNT_MISMATCH,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_QUARANTINE_EVIDENCE_MISMATCH,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_GOVERNED_FILE_ALREADY_EXISTS,
                OPERATOR_AUDIT_PROMOTION_BLOCKED_SOURCE_MUTATION_RISK,
            }), f"readiness_status={readiness_status}"),
        ],
        columns=VALIDATION_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# OPERATOR_AUDIT Promotion Readiness",
            "",
            "Planner-only readiness artifact.",
            "This planner determines whether the review-only OPERATOR_AUDIT template would be safe to promote later.",
            "No promotion is performed by this planner.",
            "No governed OPERATOR_AUDIT file is created or overwritten by this planner.",
            "",
            f"Selected promotion key: {selection.promotion_key}",
            f"Readiness status: {readiness_status}",
            f"Template status used: {template_status_used}",
            f"Future governed destination path: {future_governed_destination_path}",
            f"Source row count: {source_row_count}",
            f"Template row count: {template_row_count}",
            f"Quarantined row count: {quarantined_row_count}",
            f"Blank join-key count in template: {blank_join_key_count}",
        ]
    ).strip()

    if output_root is not None:
        output_root_path = Path(output_root)
    elif packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
    else:
        output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / SUMMARY_FILE_NAME
    checks_csv_path = output_root_path / CHECKS_FILE_NAME
    candidate_csv_path = output_root_path / CANDIDATE_FILE_NAME
    validation_csv_path = output_root_path / VALIDATION_FILE_NAME
    memo_md_path = output_root_path / MEMO_FILE_NAME

    summary_frame.to_csv(summary_csv_path, index=False)
    checks_frame.to_csv(checks_csv_path, index=False)
    candidate_frame.to_csv(candidate_csv_path, index=False)
    validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceOperatorAuditPromotionReadinessResult(
        selected_promotion=selection,
        readiness_status=readiness_status,
        template_status_used=template_status_used,
        source_row_count=source_row_count,
        template_row_count=template_row_count,
        quarantined_row_count=quarantined_row_count,
        blank_join_key_count_in_template=blank_join_key_count,
        quarantine_evidence_matched_flag=quarantine_evidence_match_flag,
        future_governed_destination_path=str(future_governed_destination_path),
        source_packets_mutated_flag=0,
        governed_file_created_flag=0,
        checks_frame=checks_frame,
        candidate_frame=candidate_frame,
        summary_frame=summary_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_operator_audit_promotion_readiness(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceOperatorAuditPromotionReadinessArtifacts:
    build_promotions_materialized_source_operator_audit_promotion_readiness(
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
    return PromotionsMaterializedSourceOperatorAuditPromotionReadinessArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(output_root_path / SUMMARY_FILE_NAME),
        checks_csv_path=str(output_root_path / CHECKS_FILE_NAME),
        candidate_csv_path=str(output_root_path / CANDIDATE_FILE_NAME),
        validation_csv_path=str(output_root_path / VALIDATION_FILE_NAME),
        memo_md_path=str(output_root_path / MEMO_FILE_NAME),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a planner-only readiness check for future OPERATOR_AUDIT template promotion.")
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    result = build_promotions_materialized_source_operator_audit_promotion_readiness(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    print("selected_promotion_key", result.selected_promotion.promotion_key)
    print("readiness_status", result.readiness_status)
    print("template_status_used", result.template_status_used)
    print("future_governed_destination_path", result.future_governed_destination_path)
    print("source_row_count", result.source_row_count)
    print("template_row_count", result.template_row_count)
    print("quarantined_row_count", result.quarantined_row_count)
    print("blank_join_key_count_in_template", result.blank_join_key_count_in_template)
    print("quarantine_evidence_matched_flag", result.quarantine_evidence_matched_flag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())