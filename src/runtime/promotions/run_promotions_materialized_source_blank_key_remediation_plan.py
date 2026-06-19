from __future__ import annotations

"""Planner-only blank-key remediation plan for materialized promotions."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_blank_key_remediation_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DIAGNOSTIC_PACKET_ROOT_NAME = "last5_promotions_diagnostic_packets"
REVIEW_TEMPLATE_FOLDER_NAME = "materialized_source_operator_audit_template"
LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"

BLANK_KEY_REMEDIATION_REQUIRED = "BLANK_KEY_REMEDIATION_REQUIRED"
BLANK_KEY_REMEDIATION_NOT_REQUIRED = "BLANK_KEY_REMEDIATION_NOT_REQUIRED"
BLANK_KEY_REMEDIATION_BLOCKED_MISSING_SOURCE_ROWS = "BLANK_KEY_REMEDIATION_BLOCKED_MISSING_SOURCE_ROWS"

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
REMEDIATION_ROW_COLUMNS: tuple[str, ...] = (
    "source_csv_line_number",
    "store_number",
    "promotion_start_date",
    "promotion_end_date_or_promotional_end_date",
    "promotion_name",
    "sku_number",
    "sku_description",
    "source_file",
    "advice_batch_row_number",
    "promotion_row_key",
    "surrounding_row_context",
    "structural_row_likelihood",
    "merchandise_row_likelihood",
    "recommended_action",
    "reason",
)
RECOMMENDED_ACTION_COLUMNS: tuple[str, ...] = (
    "source_csv_line_number",
    "promotion_row_key",
    "recommended_action",
    "reason",
)
VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

RECOMMENDED_ACTION = "REQUIRE_UPSTREAM_SOURCE_CORRECTION_OR_EXPLICIT_QUARANTINE"


class PromotionsMaterializedSourceBlankKeyRemediationPlanError(RuntimeError):
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
class PromotionsMaterializedSourceBlankKeyRemediationPlanResult:
    selected_promotion: PromotionSelection
    remediation_status: str
    blank_key_row_count: int
    source_rows_path: str
    live_operator_audit_path: str
    source_packets_mutated_flag: int
    remediation_rows_frame: pd.DataFrame
    recommended_actions_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str

    @property
    def blank_key_rows_count(self) -> int:
        return self.blank_key_row_count

    @property
    def source_packets_unchanged_flag(self) -> int:
        return int(not self.source_packets_mutated_flag)


@dataclass(frozen=True)
class PromotionsMaterializedSourceBlankKeyRemediationPlanArtifacts:
    output_root: str
    summary_csv_path: str
    blank_key_rows_csv_path: str
    blank_key_recommended_actions_csv_path: str
    remediation_validation_csv_path: str
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


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = promotion_key.split("|", 3)
    if len(parts) != 4:
        raise PromotionsMaterializedSourceBlankKeyRemediationPlanError(
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


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceBlankKeyRemediationPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceBlankKeyRemediationPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceBlankKeyRemediationPlanError(f"CSV is empty: {csv_path}")
    return frame


def _candidate_source_roots(packet_root: Path) -> list[Path]:
    return [
        packet_root / SOURCE_MATERIALIZED_FOLDER_NAME,
        packet_root / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / SOURCE_MATERIALIZED_FOLDER_NAME,
    ]


def _resolve_source_root(packet_root: Path) -> Path:
    for root in _candidate_source_roots(packet_root):
        if root.exists():
            return root
    raise PromotionsMaterializedSourceBlankKeyRemediationPlanError(
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
    raise PromotionsMaterializedSourceBlankKeyRemediationPlanError(
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


def _blank_key_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    mask = pd.Series([False] * len(frame.index), index=frame.index)
    for column in REQUIRED_JOIN_KEY_COLUMNS:
        if column not in frame.columns:
            mask = mask | True
            continue
        mask = mask | frame[column].astype(str).map(_normalize_text).eq("")
    return mask


def _structural_likelihood(row: pd.Series) -> str:
    has_source_file = _normalize_text(row.get("source_file")) != ""
    has_batch_row = _normalize_text(row.get("advice_batch_row_number")) != ""
    has_row_key = _normalize_text(row.get("promotion_row_key")) != ""
    if has_source_file and has_batch_row and has_row_key:
        return "LOW"
    if has_source_file or has_batch_row or has_row_key:
        return "MEDIUM"
    return "HIGH"


def _merchandise_likelihood(row: pd.Series) -> str:
    sku_number = _normalize_text(row.get("sku_number"))
    sku_description = _normalize_text(row.get("sku_description"))
    promo_type = _normalize_text(row.get("promo_type"))
    if sku_number or sku_description or promo_type:
        return "MEDIUM"
    return "LOW"


def _context_lines(rows: pd.DataFrame, row_index: int) -> str:
    indices = [idx for idx in (row_index - 1, row_index, row_index + 1) if 0 <= idx < len(rows.index)]
    snippets: list[str] = []
    for idx in indices:
        row = rows.iloc[idx]
        snippets.append(
            " | ".join(
                [
                    f"line={idx + 2}",
                    f"sku_number={_normalize_text(row.get('sku_number'))}",
                    f"sku_description={_normalize_text(row.get('sku_description'))}",
                    f"source_file={_normalize_text(row.get('source_file'))}",
                    f"advice_batch_row_number={_normalize_text(row.get('advice_batch_row_number'))}",
                ]
            )
        )
    return " ; ".join(snippets)


def _blank_key_rows_frame(source_rows_frame: pd.DataFrame) -> pd.DataFrame:
    if source_rows_frame.empty:
        return pd.DataFrame(columns=REMEDIATION_ROW_COLUMNS)
    rows: list[dict[str, object]] = []
    blank_mask = _blank_key_mask(source_rows_frame)
    for row_index, row in source_rows_frame.loc[blank_mask].iterrows():
        promotion_end_date = row.get("promotion_end_date") if "promotion_end_date" in source_rows_frame.columns else row.get("promotional_end_date")
        row_dict = {
            "source_csv_line_number": int(row_index) + 2,
            "store_number": _normalize_text(row.get("store_number")),
            "promotion_start_date": _normalize_text(row.get("promotion_start_date")),
            "promotion_end_date_or_promotional_end_date": _normalize_text(promotion_end_date),
            "promotion_name": _normalize_text(row.get("promotion_name")),
            "sku_number": _normalize_text(row.get("sku_number")),
            "sku_description": _normalize_text(row.get("sku_description")),
            "source_file": _normalize_text(row.get("source_file")),
            "advice_batch_row_number": _normalize_text(row.get("advice_batch_row_number")),
            "promotion_row_key": _normalize_text(row.get("promotion_row_key")),
            "surrounding_row_context": _context_lines(source_rows_frame, int(row_index)),
            "structural_row_likelihood": _structural_likelihood(row),
            "merchandise_row_likelihood": _merchandise_likelihood(row),
            "recommended_action": RECOMMENDED_ACTION,
            "reason": "Blank join-key fields block governed OPERATOR_AUDIT template generation; this row should be corrected upstream or explicitly quarantined.",
        }
        rows.append(row_dict)
    return pd.DataFrame(rows, columns=REMEDIATION_ROW_COLUMNS)


def _recommended_actions_frame(blank_key_rows_frame: pd.DataFrame) -> pd.DataFrame:
    if blank_key_rows_frame.empty:
        return pd.DataFrame(columns=RECOMMENDED_ACTION_COLUMNS)
    return blank_key_rows_frame.loc[:, ["source_csv_line_number", "promotion_row_key", "recommended_action", "reason"]].copy()


def _build_validation_frame(
    *,
    source_rows_path: Path,
    source_rows_frame: pd.DataFrame,
    blank_key_rows_frame: pd.DataFrame,
    source_hash_before: str,
    source_hash_after: str,
) -> tuple[pd.DataFrame, str]:
    validations: list[dict[str, object]] = []

    source_exists_flag = int(source_rows_path.exists())
    validations.append(_validation_row("SOURCE_ROWS_FILE_EXISTS", "PASS" if source_exists_flag else "FAIL", source_exists_flag, f"source_rows_path={source_rows_path}"))

    non_empty_flag = int(source_exists_flag == 1 and not source_rows_frame.empty)
    validations.append(_validation_row("SOURCE_ROWS_NOT_EMPTY", "PASS" if non_empty_flag else "FAIL", non_empty_flag, "Source rows must contain at least one row."))

    blank_key_count = int(len(blank_key_rows_frame.index))
    remediation_required_flag = int(blank_key_count > 0)
    validations.append(_validation_row("BLANK_KEY_ROWS_PRESENT", "PASS" if remediation_required_flag else "FAIL", remediation_required_flag, f"blank_key_row_count={blank_key_count}"))

    no_mutation_flag = int(source_hash_before == source_hash_after)
    validations.append(_validation_row("SOURCE_PACKETS_UNCHANGED", "PASS" if no_mutation_flag else "FAIL", no_mutation_flag, "Source packets under source_materialized_promotions must not be mutated."))

    if not source_exists_flag:
        status = BLANK_KEY_REMEDIATION_BLOCKED_MISSING_SOURCE_ROWS
    elif remediation_required_flag:
        status = BLANK_KEY_REMEDIATION_REQUIRED
    else:
        status = BLANK_KEY_REMEDIATION_NOT_REQUIRED

    return pd.DataFrame(validations, columns=VALIDATION_COLUMNS), status


def _build_summary_frame(
    *,
    selection: PromotionSelection,
    source_rows_path: Path,
    live_operator_audit_path: Path,
    blank_key_row_count: int,
    remediation_status: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _summary_row("SELECTED_PROMOTION_KEY", selection.promotion_key, "Promotion selected for blank-key remediation planning."),
            _summary_row("PROMOTION_SLUG", selection.promotion_slug, "Promotion slug derived from the selected promotion key."),
            _summary_row("PROMOTION_FOLDER_NAME", selection.promotion_folder_name, "Promotion folder resolved from the governed source contract."),
            _summary_row("REMEDIATION_STATUS", remediation_status, "Planner-only blank-key remediation status."),
            _summary_row("SOURCE_ROWS_PATH", str(source_rows_path), "Read-only source rows input path."),
            _summary_row("LIVE_OPERATOR_AUDIT_PATH", str(live_operator_audit_path), "Governed OPERATOR_AUDIT path that was not written."),
            _summary_row("BLANK_KEY_ROW_COUNT", blank_key_row_count, "Rows with blank required join-key fields."),
            _summary_row("TEMPLATE_BLOCKED_FLAG", 1 if blank_key_row_count > 0 else 0, "OPERATOR_AUDIT template promotion remains blocked until the blank key is corrected or quarantined."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", 0, "Source packets are read-only and were not mutated."),
        ],
        columns=SUMMARY_COLUMNS,
    )


def _build_memo_markdown(
    *,
    selection: PromotionSelection,
    remediation_status: str,
    source_rows_path: Path,
    live_operator_audit_path: Path,
    blank_key_row_count: int,
    blank_key_rows_frame: pd.DataFrame,
) -> str:
    action_note = "No auto-fill and no silent exclusion are permitted."
    if blank_key_row_count > 0:
        next_step = "OPERATOR_AUDIT template promotion is blocked until the blank key is corrected upstream or explicitly quarantined."
    else:
        next_step = "No blank-key remediation is required for this promotion."
    return "\n".join(
        [
            "# Blank Key Remediation Plan",
            "",
            "Planner-only review artifact.",
            "This plan reads source rows and writes only to the separate blank-key remediation folder.",
            "It does not create or modify the governed OPERATOR_AUDIT file.",
            "",
            f"Selected promotion key: {selection.promotion_key}",
            f"Remediation status: {remediation_status}",
            f"Source rows path: {source_rows_path}",
            f"Live governed OPERATOR_AUDIT path not written: {live_operator_audit_path}",
            f"Blank key row count: {blank_key_row_count}",
            "",
            "## Required behavior",
            action_note,
            next_step,
            "",
            "## Row evidence",
            "Rows with blank required join-key fields are captured in blank_key_rows.csv and a matching recommended-actions file.",
        ]
    ).strip()


def build_promotions_materialized_source_blank_key_remediation_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyRemediationPlanResult:
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
    blank_key_rows_frame = _blank_key_rows_frame(source_rows_frame)

    if output_root is not None:
        output_root_path = Path(output_root)
    elif packet_root_path.name == DIAGNOSTIC_PACKET_ROOT_NAME:
        output_root_path = packet_root_path / OUTPUT_FOLDER_NAME
    else:
        output_root_path = packet_root_path / "tmp" / DIAGNOSTIC_PACKET_ROOT_NAME / OUTPUT_FOLDER_NAME
    output_root_path.mkdir(parents=True, exist_ok=True)

    live_operator_audit_path = source_root / promotion_folder_name / LIVE_GOVERNED_OPERATOR_AUDIT_FILE_NAME
    validation_frame, remediation_status = _build_validation_frame(
        source_rows_path=source_rows_path,
        source_rows_frame=source_rows_frame,
        blank_key_rows_frame=blank_key_rows_frame,
        source_hash_before=source_hash_before,
        source_hash_after=_source_hash(source_root),
    )

    summary_csv_path = output_root_path / "blank_key_remediation_summary.csv"
    blank_key_rows_csv_path = output_root_path / "blank_key_rows.csv"
    recommended_actions_csv_path = output_root_path / "blank_key_recommended_actions.csv"
    validation_csv_path = output_root_path / "blank_key_remediation_validation.csv"
    memo_md_path = output_root_path / "blank_key_remediation_memo.md"

    summary_frame = _build_summary_frame(
        selection=selection,
        source_rows_path=source_rows_path,
        live_operator_audit_path=live_operator_audit_path,
        blank_key_row_count=int(len(blank_key_rows_frame.index)),
        remediation_status=remediation_status,
    )
    recommended_actions_frame = _recommended_actions_frame(blank_key_rows_frame)
    memo_markdown = _build_memo_markdown(
        selection=selection,
        remediation_status=remediation_status,
        source_rows_path=source_rows_path,
        live_operator_audit_path=live_operator_audit_path,
        blank_key_row_count=int(len(blank_key_rows_frame.index)),
        blank_key_rows_frame=blank_key_rows_frame,
    )

    blank_key_rows_frame.to_csv(blank_key_rows_csv_path, index=False)
    recommended_actions_frame.to_csv(recommended_actions_csv_path, index=False)
    summary_frame.to_csv(summary_csv_path, index=False)
    validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyRemediationPlanResult(
        selected_promotion=selection,
        remediation_status=remediation_status,
        blank_key_row_count=int(len(blank_key_rows_frame.index)),
        source_rows_path=str(source_rows_path),
        live_operator_audit_path=str(live_operator_audit_path),
        source_packets_mutated_flag=0,
        remediation_rows_frame=blank_key_rows_frame,
        recommended_actions_frame=recommended_actions_frame,
        summary_frame=summary_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_blank_key_remediation_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceBlankKeyRemediationPlanArtifacts:
    result = build_promotions_materialized_source_blank_key_remediation_plan(
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

    summary_csv_path = output_root_path / "blank_key_remediation_summary.csv"
    blank_key_rows_csv_path = output_root_path / "blank_key_rows.csv"
    recommended_actions_csv_path = output_root_path / "blank_key_recommended_actions.csv"
    validation_csv_path = output_root_path / "blank_key_remediation_validation.csv"
    memo_md_path = output_root_path / "blank_key_remediation_memo.md"

    result.summary_frame.to_csv(summary_csv_path, index=False)
    result.remediation_rows_frame.to_csv(blank_key_rows_csv_path, index=False)
    result.recommended_actions_frame.to_csv(recommended_actions_csv_path, index=False)
    result.validation_frame.to_csv(validation_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceBlankKeyRemediationPlanArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_csv_path),
        blank_key_rows_csv_path=str(blank_key_rows_csv_path),
        blank_key_recommended_actions_csv_path=str(recommended_actions_csv_path),
        remediation_validation_csv_path=str(validation_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a planner-only blank-key remediation plan for promotions.")
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    write_promotions_materialized_source_blank_key_remediation_plan(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
