from __future__ import annotations

"""Build governed evidence-only blank-key quarantine sidecar artifacts."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_blank_key_quarantine_sidecar_build"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DIAGNOSTIC_PACKET_ROOT_NAME = "last5_promotions_diagnostic_packets"
SIDECAR_PLAN_FOLDER_NAME = "materialized_source_blank_key_quarantine_sidecar_plan"
DECISION_CHECK_FOLDER_NAME = "materialized_source_blank_key_quarantine_decision_check"
DECISION_APPROVAL_FOLDER_NAME = "materialized_source_blank_key_quarantine_approval_plan"
LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"

BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR = "BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR"
BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD = "BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD"
BLANK_KEY_QUARANTINE_SIDECAR_BUILT = "BLANK_KEY_QUARANTINE_SIDECAR_BUILT"
BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_NOT_READY = "BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_NOT_READY"
BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_DECISION_NOT_APPROVED = "BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_DECISION_NOT_APPROVED"
BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_ROW_COUNT_MISMATCH = "BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_ROW_COUNT_MISMATCH"
BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_SOURCE_MUTATION_RISK = "BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_SOURCE_MUTATION_RISK"

DECISION_APPROVE_QUARANTINE = "APPROVE_QUARANTINE"
SIDECAR_ROW_STATUS = "QUARANTINED_FOR_OPERATOR_AUDIT"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
SIDECAR_COLUMNS: tuple[str, ...] = (
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


class PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError(RuntimeError):
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
class PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildResult:
    selected_promotion: PromotionSelection
    sidecar_build_status: str
    sidecar_plan_status: str
    decision_checker_status: str
    decision_row_count: int
    sidecar_path: str
    source_rows_path: str
    live_operator_audit_path: str
    source_packets_mutated_flag: int
    sidecar_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str

    @property
    def source_packets_unchanged_flag(self) -> int:
        return int(not self.source_packets_mutated_flag)


@dataclass(frozen=True)
class PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildArtifacts:
    output_root: str
    sidecar_csv_path: str
    summary_csv_path: str
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
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError(f"CSV is empty: {csv_path}")
    return frame


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError(
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
    raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError(
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
    raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError(
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


def _sidecar_plan_root(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / SIDECAR_PLAN_FOLDER_NAME
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / SIDECAR_PLAN_FOLDER_NAME


def _decision_check_root(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / DECISION_CHECK_FOLDER_NAME
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / DECISION_CHECK_FOLDER_NAME


def _decision_approval_root(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / DECISION_APPROVAL_FOLDER_NAME
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / DECISION_APPROVAL_FOLDER_NAME


def _metric_value(summary_frame: pd.DataFrame, metric_name: str) -> str:
    if summary_frame.empty:
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError("Summary frame is empty.")
    match = summary_frame.loc[summary_frame["metric_name"].astype(str).eq(metric_name), "metric_value"]
    if match.empty:
        raise PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildError(f"Metric not found in summary: {metric_name}")
    return _normalize_text(match.iloc[0])


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _decision_rows_to_sidecar(decision_rows: pd.DataFrame) -> pd.DataFrame:
    if decision_rows.empty:
        return pd.DataFrame(columns=SIDECAR_COLUMNS)
    created_timestamp = _current_timestamp()
    rows: list[dict[str, object]] = []
    for _, row in decision_rows.iterrows():
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
                "sidecar_status": SIDECAR_ROW_STATUS,
                "sidecar_created_timestamp": created_timestamp,
            }
        )
    return pd.DataFrame(rows, columns=SIDECAR_COLUMNS)


def _build_status(
    *,
    sidecar_plan_status: str,
    decision_checker_status: str,
    candidate_row_count: int,
    decision_checker_row_count: int,
    decision_row_count: int,
    all_decisions_approved_flag: int,
    source_hash_before: str,
    source_hash_after: str,
    live_operator_audit_exists_flag: int,
) -> str:
    if live_operator_audit_exists_flag or source_hash_before != source_hash_after:
        return BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_SOURCE_MUTATION_RISK
    if sidecar_plan_status != BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD:
        return BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_NOT_READY
    if decision_checker_status != BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR:
        return BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_NOT_READY
    if candidate_row_count <= 0:
        return BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_NOT_READY
    if not (candidate_row_count == decision_checker_row_count == decision_row_count):
        return BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_ROW_COUNT_MISMATCH
    if not all_decisions_approved_flag:
        return BLANK_KEY_QUARANTINE_SIDECAR_BUILD_BLOCKED_DECISION_NOT_APPROVED
    return BLANK_KEY_QUARANTINE_SIDECAR_BUILT


def _build_validation_frame(
    *,
    sidecar_plan_status: str,
    decision_checker_status: str,
    candidate_row_count: int,
    decision_checker_row_count: int,
    decision_row_count: int,
    all_decisions_approved_flag: int,
    source_hash_before: str,
    source_hash_after: str,
    live_operator_audit_path: Path,
    build_status: str,
    sidecar_row_count: int,
) -> pd.DataFrame:
    source_unchanged_flag = int(source_hash_before == source_hash_after)
    live_operator_audit_missing_flag = int(not live_operator_audit_path.exists())
    validations = [
        _validation_row(
            "SIDECAR_PLAN_READY",
            "PASS" if sidecar_plan_status == BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD else "FAIL",
            int(sidecar_plan_status == BLANK_KEY_QUARANTINE_SIDECAR_READY_TO_BUILD),
            f"sidecar_plan_status={sidecar_plan_status}",
        ),
        _validation_row(
            "DECISION_CHECKER_READY",
            "PASS" if decision_checker_status == BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR else "FAIL",
            int(decision_checker_status == BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR),
            f"decision_checker_status={decision_checker_status}",
        ),
        _validation_row(
            "ROW_COUNTS_MATCH",
            "PASS" if candidate_row_count == decision_checker_row_count == decision_row_count and candidate_row_count > 0 else "FAIL",
            int(candidate_row_count == decision_checker_row_count == decision_row_count and candidate_row_count > 0),
            f"candidate_row_count={candidate_row_count} decision_checker_row_count={decision_checker_row_count} decision_row_count={decision_row_count}",
        ),
        _validation_row(
            "ALL_DECISIONS_APPROVED_QUARANTINE",
            "PASS" if all_decisions_approved_flag else "FAIL",
            all_decisions_approved_flag,
            "All governed decision rows must remain APPROVE_QUARANTINE.",
        ),
        _validation_row(
            "SOURCE_PACKETS_UNCHANGED",
            "PASS" if source_unchanged_flag else "FAIL",
            source_unchanged_flag,
            "Source packets under source_materialized_promotions must not be mutated.",
        ),
        _validation_row(
            "LIVE_OPERATOR_AUDIT_NOT_CREATED",
            "PASS" if live_operator_audit_missing_flag else "FAIL",
            live_operator_audit_missing_flag,
            f"live_operator_audit_path={live_operator_audit_path}",
        ),
        _validation_row(
            "SIDECAR_ROWS_WRITTEN_ONLY_WHEN_BUILT",
            "PASS" if ((build_status == BLANK_KEY_QUARANTINE_SIDECAR_BUILT and sidecar_row_count > 0) or (build_status != BLANK_KEY_QUARANTINE_SIDECAR_BUILT and sidecar_row_count == 0)) else "FAIL",
            int((build_status == BLANK_KEY_QUARANTINE_SIDECAR_BUILT and sidecar_row_count > 0) or (build_status != BLANK_KEY_QUARANTINE_SIDECAR_BUILT and sidecar_row_count == 0)),
            f"sidecar_build_status={build_status} sidecar_row_count={sidecar_row_count}",
        ),
    ]
    return pd.DataFrame(validations, columns=VALIDATION_COLUMNS)


def _build_summary_frame(
    *,
    selection: PromotionSelection,
    sidecar_build_status: str,
    sidecar_plan_status: str,
    decision_checker_status: str,
    sidecar_csv_path: Path,
    decision_row_count: int,
    sidecar_row_count: int,
    live_operator_audit_path: Path,
) -> pd.DataFrame:
    rows = [
        _summary_row("SELECTED_PROMOTION_KEY", selection.promotion_key, "Promotion selected for blank-key quarantine sidecar build."),
        _summary_row("PROMOTION_SLUG", selection.promotion_slug, "Promotion slug derived from promotion key."),
        _summary_row("PROMOTION_FOLDER_NAME", selection.promotion_folder_name, "Promotion folder resolved from source manifests."),
        _summary_row("SIDECAR_PLAN_STATUS", sidecar_plan_status, "Planner-only sidecar plan status consumed by this build step."),
        _summary_row("DECISION_CHECKER_STATUS", decision_checker_status, "Decision checker status consumed by this build step."),
        _summary_row("SIDECAR_BUILD_STATUS", sidecar_build_status, "Governed evidence-only sidecar build status."),
        _summary_row("SIDECAR_PATH", str(sidecar_csv_path), "Evidence-only quarantine sidecar path."),
        _summary_row("DECISION_ROW_COUNT", decision_row_count, "Decision row count read from the approval template."),
        _summary_row("SIDECAR_ROW_COUNT", sidecar_row_count, "Rows written to the evidence-only sidecar."),
        _summary_row("LIVE_OPERATOR_AUDIT_PATH", str(live_operator_audit_path), "Governed OPERATOR_AUDIT path that was not written."),
        _summary_row("SOURCE_PACKETS_MUTATED_FLAG", 0, "Source packets are read-only and were not mutated."),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo_markdown(
    *,
    selection: PromotionSelection,
    sidecar_build_status: str,
    sidecar_row_count: int,
) -> str:
    return "\n".join(
        [
            "# Blank Key Quarantine Sidecar Build",
            "",
            "Evidence-only governed artifact.",
            "This build writes a separate quarantine sidecar and does not promote OPERATOR_AUDIT.",
            "It does not mutate source rows and does not create the live OPERATOR_AUDIT file.",
            "",
            f"Selected promotion key: {selection.promotion_key}",
            f"Sidecar build status: {sidecar_build_status}",
            f"Sidecar row count: {sidecar_row_count}",
            "",
            "## Governance",
            "Blank SKU fields are preserved exactly as blank evidence.",
            "The approved quarantine decision is carried forward without alteration.",
            "This sidecar is evidence only and does not promote OPERATOR_AUDIT.",
        ]
    ).strip()


def build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildResult:
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

    sidecar_plan_root = _sidecar_plan_root(packet_root_path)
    decision_check_root = _decision_check_root(packet_root_path)
    decision_approval_root = _decision_approval_root(packet_root_path)

    sidecar_plan_summary_path = sidecar_plan_root / "blank_key_quarantine_sidecar_plan_summary.csv"
    sidecar_candidate_rows_path = sidecar_plan_root / "blank_key_quarantine_sidecar_candidate_rows.csv"
    decision_checker_rows_path = decision_check_root / "blank_key_quarantine_decision_check_rows.csv"
    decision_template_path = decision_approval_root / "blank_key_quarantine_decision_TEMPLATE.csv"

    sidecar_plan_summary_frame = _read_csv(sidecar_plan_summary_path)
    sidecar_candidate_rows_frame = _read_csv(sidecar_candidate_rows_path, allow_empty=True)
    decision_checker_rows_frame = _read_csv(decision_checker_rows_path, allow_empty=True)
    decision_template_frame = _read_csv(decision_template_path, allow_empty=True)

    sidecar_plan_status = _metric_value(sidecar_plan_summary_frame, "SIDECAR_PLAN_STATUS")
    decision_checker_status = _metric_value(sidecar_plan_summary_frame, "DECISION_CHECKER_STATUS")

    if output_root is not None:
        output_root_path = Path(output_root)
    elif packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
    else:
        output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)

    sidecar_csv_path = output_root_path / "blank_key_quarantine_sidecar.csv"
    summary_csv_path = output_root_path / "blank_key_quarantine_sidecar_build_summary.csv"
    validation_csv_path = output_root_path / "blank_key_quarantine_sidecar_build_validation.csv"
    memo_md_path = output_root_path / "blank_key_quarantine_sidecar_build_memo.md"

    source_rows_path = _source_rows_path(source_root, promotion_folder_name)
    live_operator_audit_path = source_root / promotion_folder_name / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME
    source_hash_after = _source_hash(source_root)
    candidate_row_count = int(len(sidecar_candidate_rows_frame.index))
    decision_checker_row_count = int(len(decision_checker_rows_frame.index))
    decision_row_count = int(len(decision_template_frame.index))
    all_decisions_approved_flag = int(
        decision_row_count > 0
        and decision_template_frame["quarantine_decision"].map(_normalize_text).eq(DECISION_APPROVE_QUARANTINE).all()
    )

    build_status = _build_status(
        sidecar_plan_status=sidecar_plan_status,
        decision_checker_status=decision_checker_status,
        candidate_row_count=candidate_row_count,
        decision_checker_row_count=decision_checker_row_count,
        decision_row_count=decision_row_count,
        all_decisions_approved_flag=all_decisions_approved_flag,
        source_hash_before=source_hash_before,
        source_hash_after=source_hash_after,
        live_operator_audit_exists_flag=int(live_operator_audit_path.exists()),
    )
    sidecar_frame = _decision_rows_to_sidecar(decision_template_frame)
    if build_status != BLANK_KEY_QUARANTINE_SIDECAR_BUILT:
        sidecar_frame = pd.DataFrame(columns=SIDECAR_COLUMNS)

    validation_frame = _build_validation_frame(
        sidecar_plan_status=sidecar_plan_status,
        decision_checker_status=decision_checker_status,
        candidate_row_count=candidate_row_count,
        decision_checker_row_count=decision_checker_row_count,
        decision_row_count=decision_row_count,
        all_decisions_approved_flag=all_decisions_approved_flag,
        source_hash_before=source_hash_before,
        source_hash_after=source_hash_after,
        live_operator_audit_path=live_operator_audit_path,
        build_status=build_status,
        sidecar_row_count=int(len(sidecar_frame.index)),
    )
    summary_frame = _build_summary_frame(
        selection=selection,
        sidecar_build_status=build_status,
        sidecar_plan_status=sidecar_plan_status,
        decision_checker_status=decision_checker_status,
        sidecar_csv_path=sidecar_csv_path,
        decision_row_count=decision_row_count,
        sidecar_row_count=int(len(sidecar_frame.index)),
        live_operator_audit_path=live_operator_audit_path,
    )
    memo_markdown = _build_memo_markdown(
        selection=selection,
        sidecar_build_status=build_status,
        sidecar_row_count=int(len(sidecar_frame.index)),
    )

    sidecar_frame.to_csv(sidecar_csv_path, index=False)
    summary_frame.to_csv(summary_csv_path, index=False)
    validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildResult(
        selected_promotion=selection,
        sidecar_build_status=build_status,
        sidecar_plan_status=sidecar_plan_status,
        decision_checker_status=decision_checker_status,
        decision_row_count=decision_row_count,
        sidecar_path=str(sidecar_csv_path),
        source_rows_path=str(source_rows_path),
        live_operator_audit_path=str(live_operator_audit_path),
        source_packets_mutated_flag=0,
        sidecar_frame=sidecar_frame,
        summary_frame=summary_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_blank_key_quarantine_sidecar_build(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildArtifacts:
    result = build_promotions_materialized_source_blank_key_quarantine_sidecar_build(
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

    sidecar_csv_path = output_root_path / "blank_key_quarantine_sidecar.csv"
    summary_csv_path = output_root_path / "blank_key_quarantine_sidecar_build_summary.csv"
    validation_csv_path = output_root_path / "blank_key_quarantine_sidecar_build_validation.csv"
    memo_md_path = output_root_path / "blank_key_quarantine_sidecar_build_memo.md"

    result.sidecar_frame.to_csv(sidecar_csv_path, index=False)
    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyQuarantineSidecarBuildArtifacts(
        output_root=str(output_root_path),
        sidecar_csv_path=str(sidecar_csv_path),
        summary_csv_path=str(summary_csv_path),
        validation_csv_path=str(validation_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a governed evidence-only blank-key quarantine sidecar artifact.")
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    write_promotions_materialized_source_blank_key_quarantine_sidecar_build(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())