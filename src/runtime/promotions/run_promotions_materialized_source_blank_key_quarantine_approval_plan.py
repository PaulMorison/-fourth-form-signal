from __future__ import annotations

"""Planner-only explicit quarantine approval plan for blank-key source rows."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_blank_key_quarantine_approval_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DIAGNOSTIC_PACKET_ROOT_NAME = "last5_promotions_diagnostic_packets"
REMEDIATION_FOLDER_NAME = "materialized_source_blank_key_remediation_plan"
LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"

BLANK_KEY_QUARANTINE_APPROVAL_REQUIRED = "BLANK_KEY_QUARANTINE_APPROVAL_REQUIRED"
BLANK_KEY_QUARANTINE_APPROVAL_NOT_REQUIRED = "BLANK_KEY_QUARANTINE_APPROVAL_NOT_REQUIRED"
BLANK_KEY_QUARANTINE_APPROVAL_BLOCKED_MISSING_REMEDIATION_ROWS = "BLANK_KEY_QUARANTINE_APPROVAL_BLOCKED_MISSING_REMEDIATION_ROWS"

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


class PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanError(RuntimeError):
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
class PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanResult:
    selected_promotion: PromotionSelection
    quarantine_approval_status: str
    decision_row_count: int
    blank_key_rows_path: str
    recommended_actions_path: str
    source_rows_path: str
    live_operator_audit_path: str
    source_packets_mutated_flag: int
    decision_template_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str

    @property
    def source_packets_unchanged_flag(self) -> int:
        return int(not self.source_packets_mutated_flag)


@dataclass(frozen=True)
class PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanArtifacts:
    output_root: str
    summary_csv_path: str
    decision_template_csv_path: str
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
        raise PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanError(f"CSV is empty: {csv_path}")
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
        raise PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanError(
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


def _candidate_source_roots(packet_root: Path) -> list[Path]:
    return [
        packet_root / SOURCE_MATERIALIZED_FOLDER_NAME,
        packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / SOURCE_MATERIALIZED_FOLDER_NAME,
    ]


def _resolve_source_root(packet_root: Path) -> Path:
    for root in _candidate_source_roots(packet_root):
        if root.exists():
            return root
    raise PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanError(
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
    raise PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanError(
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


def _blank_key_fields(row: pd.Series) -> str:
    fields: list[str] = []
    for column in ("store_number", "promotion_start_date", "promotion_name", "sku_number"):
        if _normalize_text(row.get(column)) == "":
            fields.append(column)
    return ",".join(fields)


def _decision_template_frame(*, promotion_key: str, blank_key_rows_frame: pd.DataFrame, recommended_actions_frame: pd.DataFrame) -> pd.DataFrame:
    if blank_key_rows_frame.empty:
        return pd.DataFrame(columns=DECISION_TEMPLATE_COLUMNS)

    actions_by_line: dict[int, str] = {}
    if not recommended_actions_frame.empty:
        for _, row in recommended_actions_frame.iterrows():
            line_number = int(row.get("source_csv_line_number", 0))
            actions_by_line[line_number] = _normalize_text(row.get("recommended_action"))

    rows: list[dict[str, object]] = []
    for _, row in blank_key_rows_frame.iterrows():
        line_number = int(row.get("source_csv_line_number", 0))
        rows.append(
            {
                "promotion_key": promotion_key,
                "source_csv_line_number": line_number,
                "advice_batch_row_number": _normalize_text(row.get("advice_batch_row_number")),
                "source_file": _normalize_text(row.get("source_file")),
                "promotion_name": _normalize_text(row.get("promotion_name")),
                "sku_number": _normalize_text(row.get("sku_number")),
                "sku_description": _normalize_text(row.get("sku_description")),
                "blank_key_fields": _blank_key_fields(row),
                "recommended_action": actions_by_line.get(line_number, _normalize_text(row.get("recommended_action"))),
                "quarantine_decision": "",
                "quarantine_reason": "",
                "approved_by": "",
                "approved_timestamp": "",
                "source_correction_available_flag": "",
                "notes": "",
            }
        )
    return pd.DataFrame(rows, columns=DECISION_TEMPLATE_COLUMNS)


def _build_validation_frame(
    *,
    blank_key_rows_path: Path,
    blank_key_rows_frame: pd.DataFrame,
    decision_template_frame: pd.DataFrame,
    source_hash_before: str,
    source_hash_after: str,
) -> tuple[pd.DataFrame, str]:
    validations: list[dict[str, object]] = []

    remediation_rows_exists_flag = int(blank_key_rows_path.exists())
    validations.append(
        _validation_row(
            "REMEDIATION_ROWS_FILE_EXISTS",
            "PASS" if remediation_rows_exists_flag else "FAIL",
            remediation_rows_exists_flag,
            f"blank_key_rows_path={blank_key_rows_path}",
        )
    )

    blank_rows_count = int(len(blank_key_rows_frame.index))
    decision_row_count = int(len(decision_template_frame.index))
    row_count_match_flag = int(blank_rows_count == decision_row_count)
    validations.append(
        _validation_row(
            "DECISION_TEMPLATE_ROW_COUNT_MATCHES_REMEDIATION_ROWS",
            "PASS" if row_count_match_flag else "FAIL",
            row_count_match_flag,
            f"blank_key_row_count={blank_rows_count} decision_row_count={decision_row_count}",
        )
    )

    approval_required_flag = int(blank_rows_count > 0)
    validations.append(
        _validation_row(
            "QUARANTINE_APPROVAL_REQUIRED",
            "PASS" if approval_required_flag else "FAIL",
            approval_required_flag,
            "Approval is required when remediation rows exist for blank-key source records.",
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

    if remediation_rows_exists_flag == 0:
        status = BLANK_KEY_QUARANTINE_APPROVAL_BLOCKED_MISSING_REMEDIATION_ROWS
    elif blank_rows_count > 0:
        status = BLANK_KEY_QUARANTINE_APPROVAL_REQUIRED
    else:
        status = BLANK_KEY_QUARANTINE_APPROVAL_NOT_REQUIRED

    return pd.DataFrame(validations, columns=VALIDATION_COLUMNS), status


def _build_summary_frame(
    *,
    selection: PromotionSelection,
    source_rows_path: Path,
    blank_key_rows_path: Path,
    recommended_actions_path: Path,
    decision_template_path: Path,
    live_operator_audit_path: Path,
    quarantine_approval_status: str,
    decision_row_count: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION_KEY", selection.promotion_key, "Promotion selected for blank-key quarantine approval planning."),
            _summary_row("PROMOTION_SLUG", selection.promotion_slug, "Promotion slug derived from the selected promotion key."),
            _summary_row("PROMOTION_FOLDER_NAME", selection.promotion_folder_name, "Promotion folder resolved from source-materialized manifests."),
            _summary_row("QUARANTINE_APPROVAL_STATUS", quarantine_approval_status, "Planner-only blank-key quarantine approval status."),
            _summary_row("SOURCE_ROWS_PATH", str(source_rows_path), "Read-only source rows input path."),
            _summary_row("BLANK_KEY_ROWS_PATH", str(blank_key_rows_path), "Read-only blank-key remediation rows input path."),
            _summary_row("RECOMMENDED_ACTIONS_PATH", str(recommended_actions_path), "Read-only blank-key recommended-actions input path."),
            _summary_row("DECISION_TEMPLATE_PATH", str(decision_template_path), "Reviewable quarantine decision template path."),
            _summary_row("DECISION_ROW_COUNT", decision_row_count, "Decision template row count."),
            _summary_row("LIVE_OPERATOR_AUDIT_PATH", str(live_operator_audit_path), "Governed OPERATOR_AUDIT path that was not written."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", 0, "Source packets are read-only and were not mutated."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _build_memo_markdown(
    *,
    selection: PromotionSelection,
    quarantine_approval_status: str,
    decision_template_path: Path,
    live_operator_audit_path: Path,
    decision_row_count: int,
) -> str:
    return "\n".join(
        [
            "# Blank Key Quarantine Approval Plan",
            "",
            "Planner-only review artifact.",
            "This plan does not mutate source rows and does not create governed OPERATOR_AUDIT output.",
            "",
            f"Selected promotion key: {selection.promotion_key}",
            f"Quarantine approval status: {quarantine_approval_status}",
            f"Decision template path: {decision_template_path}",
            f"Decision row count: {decision_row_count}",
            f"Live governed OPERATOR_AUDIT path not written: {live_operator_audit_path}",
            "",
            "## Governance rules",
            "No row is quarantined until the decision template is completed and promoted through a governed step.",
            "Upstream correction is preferred if a true SKU can be recovered.",
            "Silent exclusion and SKU auto-fill are prohibited.",
        ]
    ).strip()


def build_promotions_materialized_source_blank_key_quarantine_approval_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanResult:
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

    if output_root is not None:
        output_root_path = Path(output_root)
    elif packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
    else:
        output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)

    remediation_root = packet_root_path / REMEDIATION_FOLDER_NAME if packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME else packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / REMEDIATION_FOLDER_NAME
    blank_key_rows_path = remediation_root / "blank_key_rows.csv"
    recommended_actions_path = remediation_root / "blank_key_recommended_actions.csv"

    blank_key_rows_frame = _read_csv(blank_key_rows_path, allow_empty=True)
    recommended_actions_frame = _read_csv(recommended_actions_path, allow_empty=True)

    decision_template_frame = _decision_template_frame(
        promotion_key=promotion_key,
        blank_key_rows_frame=blank_key_rows_frame,
        recommended_actions_frame=recommended_actions_frame,
    )

    summary_csv_path = output_root_path / "blank_key_quarantine_approval_summary.csv"
    decision_template_csv_path = output_root_path / "blank_key_quarantine_decision_TEMPLATE.csv"
    validation_csv_path = output_root_path / "blank_key_quarantine_approval_validation.csv"
    memo_md_path = output_root_path / "blank_key_quarantine_approval_memo.md"

    source_rows_path = _source_rows_path(source_root, promotion_folder_name)
    live_operator_audit_path = source_root / promotion_folder_name / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME

    validation_frame, quarantine_approval_status = _build_validation_frame(
        blank_key_rows_path=blank_key_rows_path,
        blank_key_rows_frame=blank_key_rows_frame,
        decision_template_frame=decision_template_frame,
        source_hash_before=source_hash_before,
        source_hash_after=_source_hash(source_root),
    )

    summary_frame = _build_summary_frame(
        selection=selection,
        source_rows_path=source_rows_path,
        blank_key_rows_path=blank_key_rows_path,
        recommended_actions_path=recommended_actions_path,
        decision_template_path=decision_template_csv_path,
        live_operator_audit_path=live_operator_audit_path,
        quarantine_approval_status=quarantine_approval_status,
        decision_row_count=int(len(decision_template_frame.index)),
    )
    memo_markdown = _build_memo_markdown(
        selection=selection,
        quarantine_approval_status=quarantine_approval_status,
        decision_template_path=decision_template_csv_path,
        live_operator_audit_path=live_operator_audit_path,
        decision_row_count=int(len(decision_template_frame.index)),
    )

    summary_frame.to_csv(summary_csv_path, index=False)
    decision_template_frame.to_csv(decision_template_csv_path, index=False)
    validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanResult(
        selected_promotion=selection,
        quarantine_approval_status=quarantine_approval_status,
        decision_row_count=int(len(decision_template_frame.index)),
        blank_key_rows_path=str(blank_key_rows_path),
        recommended_actions_path=str(recommended_actions_path),
        source_rows_path=str(source_rows_path),
        live_operator_audit_path=str(live_operator_audit_path),
        source_packets_mutated_flag=0,
        decision_template_frame=decision_template_frame,
        summary_frame=summary_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_blank_key_quarantine_approval_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanArtifacts:
    result = build_promotions_materialized_source_blank_key_quarantine_approval_plan(
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

    summary_csv_path = output_root_path / "blank_key_quarantine_approval_summary.csv"
    decision_template_csv_path = output_root_path / "blank_key_quarantine_decision_TEMPLATE.csv"
    validation_csv_path = output_root_path / "blank_key_quarantine_approval_validation.csv"
    memo_md_path = output_root_path / "blank_key_quarantine_approval_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.decision_template_frame.to_csv(decision_template_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyQuarantineApprovalPlanArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        decision_template_csv_path=str(decision_template_csv_path),
        validation_csv_path=str(validation_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a planner-only blank-key quarantine approval plan for promotions.")
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    write_promotions_materialized_source_blank_key_quarantine_approval_plan(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
