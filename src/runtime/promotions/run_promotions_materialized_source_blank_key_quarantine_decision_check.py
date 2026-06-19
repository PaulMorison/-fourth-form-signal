from __future__ import annotations

"""Planner-only checker for blank-key quarantine decisions."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_blank_key_quarantine_decision_check"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DIAGNOSTIC_PACKET_ROOT_NAME = "last5_promotions_diagnostic_packets"
QUARANTINE_APPROVAL_FOLDER_NAME = "materialized_source_blank_key_quarantine_approval_plan"
DEFAULT_DECISION_FILE_NAME = "blank_key_quarantine_decision_TEMPLATE.csv"
LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"

BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE = "BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE"
BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR = "BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR"
BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION = "BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION"
BLANK_KEY_QUARANTINE_DECISION_INVALID = "BLANK_KEY_QUARANTINE_DECISION_INVALID"
BLANK_KEY_QUARANTINE_DECISION_BLOCKED_MISSING_FILE = "BLANK_KEY_QUARANTINE_DECISION_BLOCKED_MISSING_FILE"

DECISION_APPROVE_QUARANTINE = "APPROVE_QUARANTINE"
DECISION_REQUIRE_SOURCE_CORRECTION = "REQUIRE_SOURCE_CORRECTION"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)
CHECK_ROWS_COLUMNS: tuple[str, ...] = (
    "promotion_key",
    "source_csv_line_number",
    "advice_batch_row_number",
    "quarantine_decision",
    "row_check_status",
    "missing_approval_fields",
    "decision_target",
    "details",
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


class PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckError(RuntimeError):
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
class PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckResult:
    selected_promotion: PromotionSelection
    decision_check_status: str
    decision_row_count: int
    decision_file_path: str
    source_rows_path: str
    live_operator_audit_path: str
    source_packets_mutated_flag: int
    check_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str

    @property
    def source_packets_unchanged_flag(self) -> int:
        return int(not self.source_packets_mutated_flag)


@dataclass(frozen=True)
class PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckArtifacts:
    output_root: str
    summary_csv_path: str
    check_rows_csv_path: str
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
        raise PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckError(f"CSV is empty: {csv_path}")
    return frame


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckError(
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
    raise PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckError(
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
    raise PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckError(
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


def _default_decision_file(packet_root: Path) -> Path:
    if packet_root.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        return packet_root / QUARANTINE_APPROVAL_FOLDER_NAME / DEFAULT_DECISION_FILE_NAME
    return packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / QUARANTINE_APPROVAL_FOLDER_NAME / DEFAULT_DECISION_FILE_NAME


def _validate_decision_row(row: pd.Series) -> dict[str, object]:
    decision = _normalize_text(row.get("quarantine_decision"))
    missing_fields: list[str] = []
    status = "READY"
    target = ""
    details = ""

    if decision == "":
        status = BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE
        details = "quarantine_decision is blank."
    elif decision == DECISION_APPROVE_QUARANTINE:
        target = BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR
        for field in ("quarantine_reason", "approved_by", "approved_timestamp", "source_correction_available_flag"):
            if _normalize_text(row.get(field)) == "":
                missing_fields.append(field)
        if missing_fields:
            status = BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE
            details = "Missing required approval fields for APPROVE_QUARANTINE."
    elif decision == DECISION_REQUIRE_SOURCE_CORRECTION:
        target = BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION
        for field in ("quarantine_reason", "approved_by", "approved_timestamp"):
            if _normalize_text(row.get(field)) == "":
                missing_fields.append(field)
        if missing_fields:
            status = BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE
            details = "Missing required approval fields for REQUIRE_SOURCE_CORRECTION."
    else:
        status = BLANK_KEY_QUARANTINE_DECISION_INVALID
        details = f"Unsupported quarantine_decision value: {decision}"

    if status == "READY":
        status = target
        details = "Decision row is complete for its declared path."

    return {
        "promotion_key": _normalize_text(row.get("promotion_key")),
        "source_csv_line_number": int(row.get("source_csv_line_number", 0) or 0),
        "advice_batch_row_number": _normalize_text(row.get("advice_batch_row_number")),
        "quarantine_decision": decision,
        "row_check_status": status,
        "missing_approval_fields": ",".join(missing_fields),
        "decision_target": target,
        "details": details,
    }


def _build_check_rows(decision_frame: pd.DataFrame) -> pd.DataFrame:
    if decision_frame.empty:
        return pd.DataFrame(columns=CHECK_ROWS_COLUMNS)
    rows = [_validate_decision_row(row) for _, row in decision_frame.iterrows()]
    return pd.DataFrame(rows, columns=CHECK_ROWS_COLUMNS)


def _overall_status(check_rows_frame: pd.DataFrame, *, decision_file_exists: bool) -> str:
    if not decision_file_exists:
        return BLANK_KEY_QUARANTINE_DECISION_BLOCKED_MISSING_FILE
    if check_rows_frame.empty:
        return BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE

    statuses = set(check_rows_frame["row_check_status"].astype(str))
    if BLANK_KEY_QUARANTINE_DECISION_INVALID in statuses:
        return BLANK_KEY_QUARANTINE_DECISION_INVALID
    if BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE in statuses:
        return BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE

    targets = set(check_rows_frame["decision_target"].astype(str))
    if targets == {BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR}:
        return BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR
    if targets == {BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION}:
        return BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION
    return BLANK_KEY_QUARANTINE_DECISION_INVALID


def _build_validation_frame(
    *,
    decision_file_path: Path,
    decision_file_exists_flag: int,
    decision_frame: pd.DataFrame,
    check_rows_frame: pd.DataFrame,
    status: str,
    source_hash_before: str,
    source_hash_after: str,
) -> pd.DataFrame:
    validations: list[dict[str, object]] = []
    validations.append(
        _validation_row(
            "DECISION_FILE_EXISTS",
            "PASS" if decision_file_exists_flag else "FAIL",
            decision_file_exists_flag,
            f"decision_file_path={decision_file_path}",
        )
    )
    validations.append(
        _validation_row(
            "DECISION_ROW_COUNT_PRESENT",
            "PASS" if int(len(decision_frame.index) > 0) else "FAIL",
            int(len(decision_frame.index) > 0),
            f"decision_row_count={len(decision_frame.index)}",
        )
    )
    invalid_rows_flag = int((check_rows_frame["row_check_status"] == BLANK_KEY_QUARANTINE_DECISION_INVALID).any()) if not check_rows_frame.empty else 0
    validations.append(
        _validation_row(
            "NO_INVALID_DECISION_VALUES",
            "PASS" if invalid_rows_flag == 0 else "FAIL",
            int(invalid_rows_flag == 0),
            "No unsupported quarantine_decision values are allowed.",
        )
    )
    incomplete_rows_count = int((check_rows_frame["row_check_status"] == BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE).sum()) if not check_rows_frame.empty else 0
    validations.append(
        _validation_row(
            "INCOMPLETE_DECISION_ROWS",
            "PASS" if incomplete_rows_count == 0 else "FAIL",
            int(incomplete_rows_count == 0),
            f"incomplete_rows={incomplete_rows_count}",
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
    validations.append(
        _validation_row(
            "OVERALL_STATUS",
            "PASS" if status in {
                BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE,
                BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR,
                BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION,
            } else "FAIL",
            int(status in {
                BLANK_KEY_QUARANTINE_DECISION_INCOMPLETE,
                BLANK_KEY_QUARANTINE_DECISION_READY_FOR_QUARANTINE_SIDECAR,
                BLANK_KEY_QUARANTINE_DECISION_READY_FOR_SOURCE_CORRECTION,
            }),
            f"decision_check_status={status}",
        )
    )
    return pd.DataFrame(validations, columns=VALIDATION_COLUMNS)


def _build_summary_frame(
    *,
    selection: PromotionSelection,
    decision_file_path: Path,
    check_rows_path: Path,
    status: str,
    decision_row_count: int,
    live_operator_audit_path: Path,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION_KEY", selection.promotion_key, "Promotion selected for quarantine decision checking."),
            _summary_row("PROMOTION_SLUG", selection.promotion_slug, "Promotion slug derived from promotion key."),
            _summary_row("PROMOTION_FOLDER_NAME", selection.promotion_folder_name, "Promotion folder resolved from source manifests."),
            _summary_row("DECISION_CHECK_STATUS", status, "Planner-only quarantine decision check status."),
            _summary_row("DECISION_FILE_PATH", str(decision_file_path), "Input decision template path."),
            _summary_row("CHECK_ROWS_PATH", str(check_rows_path), "Row-level decision check output path."),
            _summary_row("DECISION_ROW_COUNT", decision_row_count, "Decision row count read from template."),
            _summary_row("LIVE_OPERATOR_AUDIT_PATH", str(live_operator_audit_path), "Governed OPERATOR_AUDIT path that was not written."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", 0, "Source packets are read-only and were not mutated."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _build_memo_markdown(
    *,
    selection: PromotionSelection,
    status: str,
    decision_file_path: Path,
    decision_row_count: int,
) -> str:
    return "\n".join(
        [
            "# Blank Key Quarantine Decision Check",
            "",
            "Planner-only checker artifact.",
            "This checker reports readiness only and does not create any quarantine sidecar or governed OPERATOR_AUDIT output.",
            "",
            f"Selected promotion key: {selection.promotion_key}",
            f"Decision check status: {status}",
            f"Decision file path: {decision_file_path}",
            f"Decision row count: {decision_row_count}",
            "",
            "## Rules enforced",
            "If quarantine_decision is blank, status remains incomplete.",
            "APPROVE_QUARANTINE requires quarantine_reason, approved_by, approved_timestamp, and source_correction_available_flag.",
            "REQUIRE_SOURCE_CORRECTION requires quarantine_reason, approved_by, and approved_timestamp.",
            "Any other decision value is invalid.",
        ]
    ).strip()


def build_promotions_materialized_source_blank_key_quarantine_decision_check(
    *,
    packet_root: str | Path,
    promotion_key: str,
    decision_file: str | Path | None = None,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckResult:
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

    if decision_file is not None:
        decision_file_path = Path(decision_file)
    else:
        decision_file_path = _default_decision_file(packet_root_path)

    decision_exists = int(decision_file_path.exists())
    decision_frame = _read_csv(decision_file_path, allow_empty=True) if decision_exists else pd.DataFrame(columns=DECISION_TEMPLATE_COLUMNS)
    check_rows_frame = _build_check_rows(decision_frame)
    status = _overall_status(check_rows_frame, decision_file_exists=bool(decision_exists))

    if output_root is not None:
        output_root_path = Path(output_root)
    elif packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
    else:
        output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_root_path / "blank_key_quarantine_decision_check_summary.csv"
    check_rows_csv_path = output_root_path / "blank_key_quarantine_decision_check_rows.csv"
    validation_csv_path = output_root_path / "blank_key_quarantine_decision_check_validation.csv"
    memo_md_path = output_root_path / "blank_key_quarantine_decision_check_memo.md"

    source_rows_path = _source_rows_path(source_root, promotion_folder_name)
    live_operator_audit_path = source_root / promotion_folder_name / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME

    validation_frame = _build_validation_frame(
        decision_file_path=decision_file_path,
        decision_file_exists_flag=decision_exists,
        decision_frame=decision_frame,
        check_rows_frame=check_rows_frame,
        status=status,
        source_hash_before=source_hash_before,
        source_hash_after=_source_hash(source_root),
    )
    summary_frame = _build_summary_frame(
        selection=selection,
        decision_file_path=decision_file_path,
        check_rows_path=check_rows_csv_path,
        status=status,
        decision_row_count=int(len(decision_frame.index)),
        live_operator_audit_path=live_operator_audit_path,
    )
    memo_markdown = _build_memo_markdown(
        selection=selection,
        status=status,
        decision_file_path=decision_file_path,
        decision_row_count=int(len(decision_frame.index)),
    )

    summary_frame.to_csv(summary_csv_path, index=False)
    check_rows_frame.to_csv(check_rows_csv_path, index=False)
    validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckResult(
        selected_promotion=selection,
        decision_check_status=status,
        decision_row_count=int(len(decision_frame.index)),
        decision_file_path=str(decision_file_path),
        source_rows_path=str(source_rows_path),
        live_operator_audit_path=str(live_operator_audit_path),
        source_packets_mutated_flag=0,
        check_rows_frame=check_rows_frame,
        summary_frame=summary_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_blank_key_quarantine_decision_check(
    *,
    packet_root: str | Path,
    promotion_key: str,
    decision_file: str | Path | None = None,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckArtifacts:
    result = build_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=packet_root,
        promotion_key=promotion_key,
        decision_file=decision_file,
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

    summary_csv_path = output_root_path / "blank_key_quarantine_decision_check_summary.csv"
    check_rows_csv_path = output_root_path / "blank_key_quarantine_decision_check_rows.csv"
    validation_csv_path = output_root_path / "blank_key_quarantine_decision_check_validation.csv"
    memo_md_path = output_root_path / "blank_key_quarantine_decision_check_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.check_rows_frame.to_csv(check_rows_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyQuarantineDecisionCheckArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        check_rows_csv_path=str(check_rows_csv_path),
        validation_csv_path=str(validation_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a planner-only blank-key quarantine decision checker.")
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--decision-file")
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    write_promotions_materialized_source_blank_key_quarantine_decision_check(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        decision_file=args.decision_file,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
