from __future__ import annotations

import argparse
from dataclasses import dataclass
from importlib.util import find_spec
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from runtime.promotions.input_source_provenance import (
    add_provenance_columns,
    certification_failed,
)
from runtime.promotions.run_promotions_no_prior_demand_manual_inspection import (
    MANUAL_CAUSE_LABEL_VALUES,
    MANUAL_NEXT_ACTION_VALUES,
    TARGET_OVERLAY_CATEGORY,
)


OUTPUT_FOLDER_NAME = "manual_completion_pack"
INPUT_ROWS_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/no_prior_demand_manual_inspection_rows.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
)

BASE_CONTEXT_COLUMNS: tuple[str, ...] = (
    "review_priority_rank",
    "sku_number",
    "sku_description",
    "department",
    "overlay_category",
    "operator_decision",
    "operator_action",
    "order_units",
    "actual_units_sold",
    "expected_promo_demand",
    "forecast_error_units",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "current_soh_units",
    "on_order_units",
    "projected_on_hand_at_promo_start",
    "target_stock_day_one_units",
    "proposed_review_action",
    "why_review_required",
    "human_review_question",
)

MANUAL_COLUMNS: tuple[str, ...] = (
    "manual_cause_label",
    "manual_confidence_score",
    "manual_notes",
    "manual_next_action",
    "should_add_review_rule_candidate",
    "should_remain_shadow_only",
)

GUIDANCE_COLUMNS: tuple[str, ...] = (
    "cause_label_guidance",
    "confidence_score_guidance",
    "next_action_guidance",
    "candidate_rule_guidance",
    "shadow_only_guidance",
    "review_completion_status",
)

OPTIONAL_GUARDRAIL_COLUMNS: tuple[str, ...] = (
    "production_order_change_flag",
    "stage_12_change_flag",
)

ALLOWED_VALUES_COLUMNS: tuple[str, ...] = (
    "field_name",
    "allowed_value",
    "display_order",
    "operator_guidance",
    "recommended_manual_next_action",
    "recommended_should_add_review_rule_candidate",
    "recommended_should_remain_shadow_only",
)

CHECKLIST_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "gross_profit",
    "forecast_error_units",
    "completion_required",
    "has_manual_cause_label",
    "has_confidence_score",
    "has_manual_next_action",
    "has_rule_candidate_flag",
    "has_shadow_only_flag",
    "ready_for_ingest",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)


class PromotionsNoPriorManualCompletionPackError(RuntimeError):
    """Raised when the no-prior manual-completion pack cannot be built safely."""


@dataclass(frozen=True)
class PromotionsNoPriorManualCompletionPackResult:
    rows_frame: pd.DataFrame
    allowed_values_frame: pd.DataFrame
    checklist_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    guide_markdown: str


@dataclass(frozen=True)
class PromotionsNoPriorManualCompletionPackArtifacts:
    rows_csv_path: str
    allowed_values_csv_path: str
    checklist_csv_path: str
    summary_csv_path: str
    guide_md_path: str
    workbook_xlsx_path: str | None


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsNoPriorManualCompletionPackError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsNoPriorManualCompletionPackError(
            f"Manifest must be a JSON object: {path}"
        )
    return payload


def _validate_review_artifact_root(review_artifact_root: Path) -> None:
    missing = [
        artifact_name
        for artifact_name in REQUIRED_REVIEW_ARTIFACTS
        if not (review_artifact_root / artifact_name).exists()
    ]
    if missing:
        raise PromotionsNoPriorManualCompletionPackError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsNoPriorManualCompletionPackError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _summary_row(
    metric_group: str,
    metric_name: str,
    metric_value: float | int,
    metric_unit: str,
    metric_display: str,
    notes: str,
) -> dict[str, object]:
    return {
        "metric_group": metric_group,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit,
        "metric_display": metric_display,
        "notes": notes,
    }


def _blank_text_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series([""] * len(frame.index), index=frame.index, dtype="object")
    return frame[column_name].astype(str).fillna("").str.strip()


def _build_rows_frame(manual_inspection_rows_frame: pd.DataFrame) -> pd.DataFrame:
    frame = manual_inspection_rows_frame.copy()
    if "overlay_category" not in frame.columns:
        frame["overlay_category"] = TARGET_OVERLAY_CATEGORY
    for column_name in OPTIONAL_GUARDRAIL_COLUMNS:
        if column_name not in frame.columns:
            frame[column_name] = 0

    _require_columns(
        frame,
        BASE_CONTEXT_COLUMNS + MANUAL_COLUMNS,
        frame_name="manual_inspection_rows_frame",
    )

    cause_label_guidance = (
        "Choose one allowed cause label only. Use RANDOM_ONE_OFF_DEMAND or "
        "UNKNOWN_REQUIRES_REVIEW when the demand cause does not look repeatable."
    )
    confidence_score_guidance = (
        "Enter a number from 0 to 100. Use 70+ only when you can explain the demand cause clearly."
    )
    next_action_guidance = (
        "Choose one allowed next action. For DATA_GAP_OR_LABEL_ERROR, prefer INSPECT_DATA_QUALITY."
    )
    candidate_rule_guidance = (
        "Set should_add_review_rule_candidate to 1 only when the cause appears repeatable and commercially sensible. "
        "Keep it 0 for RANDOM_ONE_OFF_DEMAND and UNKNOWN_REQUIRES_REVIEW."
    )
    shadow_only_guidance = (
        "Set should_remain_shadow_only to 1 when the row is interesting but not strong enough for a future rule yet."
    )

    rows_frame = frame.loc[:, BASE_CONTEXT_COLUMNS].copy()
    for column_name in MANUAL_COLUMNS:
        rows_frame[column_name] = ""
    rows_frame["cause_label_guidance"] = cause_label_guidance
    rows_frame["confidence_score_guidance"] = confidence_score_guidance
    rows_frame["next_action_guidance"] = next_action_guidance
    rows_frame["candidate_rule_guidance"] = candidate_rule_guidance
    rows_frame["shadow_only_guidance"] = shadow_only_guidance
    rows_frame["review_completion_status"] = "NOT_STARTED"
    return rows_frame.loc[:, BASE_CONTEXT_COLUMNS + MANUAL_COLUMNS + GUIDANCE_COLUMNS].reset_index(drop=True)


def _cause_guidance(cause_label: str) -> tuple[str, str, str]:
    if cause_label == "DATA_GAP_OR_LABEL_ERROR":
        return (
            "Use when missing labels, promo history, or source data likely explain the surprise demand.",
            "INSPECT_DATA_QUALITY",
            "0 until the data-quality issue is understood",
        )
    if cause_label == "RANDOM_ONE_OFF_DEMAND":
        return (
            "Use when the demand looks isolated and not commercially repeatable.",
            "NO_CHANGE",
            "0",
        )
    if cause_label == "UNKNOWN_REQUIRES_REVIEW":
        return (
            "Use when the row still needs human escalation before a clear cause can be named.",
            "ESCALATE_FOR_OPERATOR_REVIEW",
            "0",
        )
    return (
        "Use when the demand cause looks commercially understandable and may be repeatable.",
        "ADD_TO_REVIEW_RULE_CANDIDATES or KEEP_SHADOW_ONLY",
        "1 only if repeatable and commercially sensible",
    )


def _build_allowed_values_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for display_order, cause_label in enumerate(MANUAL_CAUSE_LABEL_VALUES, start=1):
        cause_guidance, recommended_next_action, recommended_rule_candidate = _cause_guidance(cause_label)
        rows.append(
            {
                "field_name": "manual_cause_label",
                "allowed_value": cause_label,
                "display_order": display_order,
                "operator_guidance": cause_guidance,
                "recommended_manual_next_action": recommended_next_action,
                "recommended_should_add_review_rule_candidate": recommended_rule_candidate,
                "recommended_should_remain_shadow_only": "1 if interesting but still needs shadow-only evidence",
            }
        )

    rows.append(
        {
            "field_name": "manual_confidence_score",
            "allowed_value": "0-100",
            "display_order": 1,
            "operator_guidance": "70+ means the operator can explain the demand cause clearly.",
            "recommended_manual_next_action": "",
            "recommended_should_add_review_rule_candidate": "",
            "recommended_should_remain_shadow_only": "",
        }
    )

    for display_order, next_action in enumerate(MANUAL_NEXT_ACTION_VALUES, start=1):
        guidance = "Choose the next action that best matches the manual cause and commercial confidence."
        if next_action == "INSPECT_DATA_QUALITY":
            guidance = "Use when the surprising demand may be explained by missing or incorrect source data."
        elif next_action == "ADD_TO_REVIEW_RULE_CANDIDATES":
            guidance = "Use only when the cause looks repeatable and commercially sensible."
        elif next_action == "KEEP_SHADOW_ONLY":
            guidance = "Use when the row is interesting but not yet strong enough for a future rule."
        elif next_action == "NO_CHANGE":
            guidance = "Use when the row looks like one-off demand and no review rule should be proposed."
        elif next_action == "ESCALATE_FOR_OPERATOR_REVIEW":
            guidance = "Use when more human context is required before a cause can be trusted."
        rows.append(
            {
                "field_name": "manual_next_action",
                "allowed_value": next_action,
                "display_order": display_order,
                "operator_guidance": guidance,
                "recommended_manual_next_action": next_action,
                "recommended_should_add_review_rule_candidate": "",
                "recommended_should_remain_shadow_only": "",
            }
        )

    for display_order, allowed_value in enumerate(("1 / TRUE / Yes", "0 / FALSE / No", "blank"), start=1):
        rows.append(
            {
                "field_name": "should_add_review_rule_candidate",
                "allowed_value": allowed_value,
                "display_order": display_order,
                "operator_guidance": "Use 1 only when the cause appears repeatable and commercially sensible. Use 0 for RANDOM_ONE_OFF_DEMAND and UNKNOWN_REQUIRES_REVIEW.",
                "recommended_manual_next_action": "",
                "recommended_should_add_review_rule_candidate": "1 only for repeatable, sensible causes",
                "recommended_should_remain_shadow_only": "",
            }
        )
        rows.append(
            {
                "field_name": "should_remain_shadow_only",
                "allowed_value": allowed_value,
                "display_order": display_order,
                "operator_guidance": "Use 1 when the row is worth watching but does not yet justify a future review rule.",
                "recommended_manual_next_action": "",
                "recommended_should_add_review_rule_candidate": "",
                "recommended_should_remain_shadow_only": "1 when evidence is still thin",
            }
        )

    return pd.DataFrame(rows, columns=ALLOWED_VALUES_COLUMNS)


def _build_checklist_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    has_manual_cause_label = _blank_text_series(rows_frame, "manual_cause_label").ne("").astype(int)
    has_confidence_score = _blank_text_series(rows_frame, "manual_confidence_score").ne("").astype(int)
    has_manual_next_action = _blank_text_series(rows_frame, "manual_next_action").ne("").astype(int)
    has_rule_candidate_flag = _blank_text_series(rows_frame, "should_add_review_rule_candidate").ne("").astype(int)
    has_shadow_only_flag = _blank_text_series(rows_frame, "should_remain_shadow_only").ne("").astype(int)

    ready_for_ingest = (
        has_manual_cause_label.eq(1)
        & has_confidence_score.eq(1)
        & has_manual_next_action.eq(1)
        & has_rule_candidate_flag.eq(1)
        & has_shadow_only_flag.eq(1)
    ).astype(int)

    checklist_frame = pd.DataFrame(
        {
            "sku_number": rows_frame["sku_number"],
            "sku_description": rows_frame["sku_description"],
            "department": rows_frame["department"],
            "gross_profit": rows_frame["actual_gross_profit"],
            "forecast_error_units": rows_frame["forecast_error_units"],
            "completion_required": 1,
            "has_manual_cause_label": has_manual_cause_label,
            "has_confidence_score": has_confidence_score,
            "has_manual_next_action": has_manual_next_action,
            "has_rule_candidate_flag": has_rule_candidate_flag,
            "has_shadow_only_flag": has_shadow_only_flag,
            "ready_for_ingest": ready_for_ingest,
        }
    )
    return checklist_frame.loc[:, CHECKLIST_COLUMNS].reset_index(drop=True)


def _build_summary_frame(
    rows_frame: pd.DataFrame,
    checklist_frame: pd.DataFrame,
    source_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows_prepared = int(len(rows_frame.index))
    ready_for_ingest_rows = int(checklist_frame["ready_for_ingest"].astype(int).sum())
    not_ready_rows = rows_prepared - ready_for_ingest_rows
    production_order_changes = 0
    stage12_changes = 0
    for column_name in OPTIONAL_GUARDRAIL_COLUMNS:
        if column_name not in source_frame.columns:
            continue
        numeric_sum = int(pd.to_numeric(source_frame[column_name], errors="coerce").fillna(0).sum())
        if column_name == "production_order_change_flag":
            production_order_changes = numeric_sum
        if column_name == "stage_12_change_flag":
            stage12_changes = numeric_sum

    total_gross_profit = round(
        float(pd.to_numeric(rows_frame["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
        2,
    )
    total_capital_left = round(
        float(
            pd.to_numeric(
                rows_frame["capital_left_in_unsold_store_allocation"], errors="coerce"
            ).fillna(0.0).sum()
        ),
        2,
    )

    rows = [
        _summary_row(
            "MANUAL_COMPLETION_PACK",
            "ROWS_PREPARED",
            rows_prepared,
            "rows",
            _format_int(rows_prepared),
            "Rows prepared for human manual completion.",
        ),
        _summary_row(
            "MANUAL_COMPLETION_PACK",
            "READY_FOR_INGEST_ROWS",
            ready_for_ingest_rows,
            "rows",
            _format_int(ready_for_ingest_rows),
            "Rows with all manual completion fields present.",
        ),
        _summary_row(
            "MANUAL_COMPLETION_PACK",
            "NOT_READY_ROWS",
            not_ready_rows,
            "rows",
            _format_int(not_ready_rows),
            "Rows still needing human completion before ingest.",
        ),
        _summary_row(
            "MANUAL_COMPLETION_PACK",
            "TOTAL_GROSS_PROFIT_REPRESENTED",
            total_gross_profit,
            "dollars",
            _format_money(total_gross_profit),
            "Gross profit represented by the completion pack rows.",
        ),
        _summary_row(
            "MANUAL_COMPLETION_PACK",
            "TOTAL_CAPITAL_LEFT_REPRESENTED",
            total_capital_left,
            "dollars",
            _format_money(total_capital_left),
            "Capital left represented by the completion pack rows.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            production_order_changes,
            "rows",
            _format_int(production_order_changes),
            "This completion pack does not change production ordering.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage12_changes,
            "rows",
            _format_int(stage12_changes),
            "This completion pack does not change Stage 12.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_guide_markdown(rows_frame: pd.DataFrame, workbook_supported: bool) -> str:
    rows_prepared = int(len(rows_frame.index))
    workbook_note = ""
    if not workbook_supported:
        workbook_note = (
            "\nCSV outputs are the supported completion format in this environment because no Excel writer engine is installed.\n"
        )

    lines = [
        "# No Prior Manual Completion Pack",
        "",
        "This is not an order file. It is a human-completion pack for the no-prior-demand surprise review rows.",
        "",
        "Production order changes = 0.",
        "Stage 12 changes = 0.",
        "",
        (
            f"The goal is to identify why these {_format_int(rows_prepared)} SKUs sold despite weak or no prior promo evidence."
        ),
        "The purpose is learning and future review-rule candidates, not auto-buying and not changing the demand proxy.",
        "",
        "How to complete the pack:",
        "1. Open no_prior_manual_completion_rows.csv and fill only the manual fields for each SKU.",
        "2. Use no_prior_manual_completion_allowed_values.csv when choosing the cause label, confidence score, next action, and rule-candidate flags.",
        "3. Use no_prior_manual_completion_checklist.csv to track which rows are ready for ingest.",
        "4. Save the completed CSV, then rerun run_promotions_no_prior_manual_inspection_ingest.py with --worksheet-path pointing to no_prior_manual_completion_rows.csv.",
        workbook_note.strip(),
        "",
        "Recommendation: keep any future review-rule candidates shadow-only until repeated evidence appears across more promotions.",
    ]
    return "\n".join(line for line in lines if line != "") + "\n"


def _excel_writer_supported() -> bool:
    return bool(find_spec("openpyxl") or find_spec("xlsxwriter"))


def _maybe_write_workbook(
    *,
    rows_frame: pd.DataFrame,
    allowed_values_frame: pd.DataFrame,
    checklist_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    destination_root: Path,
) -> str | None:
    if not _excel_writer_supported():
        return None
    workbook_path = destination_root / "NO_PRIOR_MANUAL_COMPLETION_WORKBOOK.xlsx"
    try:
        with pd.ExcelWriter(workbook_path) as writer:
            rows_frame.to_excel(writer, sheet_name="completion_rows", index=False)
            allowed_values_frame.to_excel(writer, sheet_name="allowed_values", index=False)
            checklist_frame.to_excel(writer, sheet_name="checklist", index=False)
            summary_frame.to_excel(writer, sheet_name="summary", index=False)
    except Exception:
        return None
    return str(workbook_path)


def build_promotions_no_prior_manual_completion_pack(
    *,
    manual_inspection_rows_frame: pd.DataFrame,
) -> PromotionsNoPriorManualCompletionPackResult:
    rows_frame = _build_rows_frame(manual_inspection_rows_frame)
    allowed_values_frame = _build_allowed_values_frame()
    checklist_frame = _build_checklist_frame(rows_frame)
    summary_frame = _build_summary_frame(rows_frame, checklist_frame, manual_inspection_rows_frame)
    guide_markdown = _build_guide_markdown(rows_frame, workbook_supported=_excel_writer_supported())
    return PromotionsNoPriorManualCompletionPackResult(
        rows_frame=rows_frame,
        allowed_values_frame=allowed_values_frame,
        checklist_frame=checklist_frame,
        summary_frame=summary_frame,
        guide_markdown=guide_markdown,
    )


def write_promotions_no_prior_manual_completion_pack(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsNoPriorManualCompletionPackArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsNoPriorManualCompletionPackError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    source_rows_path = review_artifact_path / INPUT_ROWS_RELATIVE_PATH
    source_rows_frame = _read_csv(source_rows_path)
    result = build_promotions_no_prior_manual_completion_pack(
        manual_inspection_rows_frame=source_rows_frame,
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else review_artifact_path
        / "review_overlay_packet"
        / "operator_review_memo"
        / "no_prior_demand_manual_inspection"
        / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "no_prior_manual_completion_rows.csv"
    allowed_values_csv_path = destination_root / "no_prior_manual_completion_allowed_values.csv"
    checklist_csv_path = destination_root / "no_prior_manual_completion_checklist.csv"
    summary_csv_path = destination_root / "no_prior_manual_completion_summary.csv"
    guide_md_path = destination_root / "no_prior_manual_completion_guide.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.allowed_values_frame.copy(), manifest).to_csv(
        allowed_values_csv_path, index=False
    )
    add_provenance_columns(result.checklist_frame.copy(), manifest).to_csv(
        checklist_csv_path, index=False
    )
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(
        summary_csv_path, index=False
    )
    guide_md_path.write_text(result.guide_markdown, encoding="utf-8")

    workbook_xlsx_path = _maybe_write_workbook(
        rows_frame=result.rows_frame,
        allowed_values_frame=result.allowed_values_frame,
        checklist_frame=result.checklist_frame,
        summary_frame=result.summary_frame,
        destination_root=destination_root,
    )

    return PromotionsNoPriorManualCompletionPackArtifacts(
        rows_csv_path=str(rows_csv_path),
        allowed_values_csv_path=str(allowed_values_csv_path),
        checklist_csv_path=str(checklist_csv_path),
        summary_csv_path=str(summary_csv_path),
        guide_md_path=str(guide_md_path),
        workbook_xlsx_path=workbook_xlsx_path,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a guided manual-completion pack for no-prior-demand surprise rows."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_no_prior_manual_completion_pack(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("no_prior_manual_completion_rows", artifacts.rows_csv_path)
    print("no_prior_manual_completion_allowed_values", artifacts.allowed_values_csv_path)
    print("no_prior_manual_completion_checklist", artifacts.checklist_csv_path)
    print("no_prior_manual_completion_summary", artifacts.summary_csv_path)
    print("no_prior_manual_completion_guide", artifacts.guide_md_path)
    if artifacts.workbook_xlsx_path is not None:
        print("NO_PRIOR_MANUAL_COMPLETION_WORKBOOK", artifacts.workbook_xlsx_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())