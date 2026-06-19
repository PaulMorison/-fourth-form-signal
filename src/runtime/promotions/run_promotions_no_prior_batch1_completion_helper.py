from __future__ import annotations

import argparse
from dataclasses import dataclass
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
)
from runtime.promotions.run_promotions_no_prior_operator_review_sequence import (
    BATCH_1_FAST_HIGH_VALUE,
)


OUTPUT_FOLDER_NAME = "batch1_completion_helper"
INPUT_ROWS_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/operator_review_sequence/no_prior_operator_review_sequence_rows.csv"
)
MANUAL_COMPLETION_ROWS_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/manual_completion_pack/no_prior_manual_completion_rows.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
    str(MANUAL_COMPLETION_ROWS_RELATIVE_PATH),
)

INGEST_REQUIRED_COLUMNS: tuple[str, ...] = (
    "review_priority_rank",
    "operator_decision",
    "operator_action",
    "order_units",
    "proposed_review_action",
)

MANUAL_COMPLETION_JOIN_COLUMNS: tuple[str, ...] = (
    "operator_decision",
    "operator_action",
    "order_units",
    "proposed_review_action",
)

PRESERVED_COLUMNS: tuple[str, ...] = (
    "operator_review_sequence_rank",
    "review_sequence_group",
    "review_sequence_reason",
    "expected_learning_value",
    "estimated_review_difficulty",
    "recommended_review_time_minutes",
    "review_batch",
    "sku_number",
    "sku_description",
    "department",
    "actual_units_sold",
    "expected_promo_demand",
    "forecast_error_units",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "current_soh_units",
    "on_order_units",
    "projected_on_hand_at_promo_start",
    "target_stock_day_one_units",
    "human_review_question",
    "why_review_required",
    "inspection_priority",
    "primary_evidence_to_check",
    "secondary_evidence_to_check",
    "possible_cause_labels_to_consider",
    "candidate_caution_note",
    "shadow_only_note",
    "operator_decision_prompt",
    "do_not_auto_label_flag",
)

MANUAL_COLUMNS: tuple[str, ...] = (
    "manual_cause_label",
    "manual_confidence_score",
    "manual_notes",
    "manual_next_action",
    "should_add_review_rule_candidate",
    "should_remain_shadow_only",
)

HELPER_COLUMNS: tuple[str, ...] = (
    "batch1_review_instruction",
    "what_to_check_first",
    "candidate_threshold_reminder",
    "completion_required_flag",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)

BATCH_1_REVIEW_BATCH_ALIASES: tuple[str, ...] = (BATCH_1_FAST_HIGH_VALUE, "BATCH_1")


class PromotionsNoPriorBatch1CompletionHelperError(RuntimeError):
    """Raised when the Batch 1 completion helper cannot be built safely."""


@dataclass(frozen=True)
class PromotionsNoPriorBatch1CompletionHelperResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    guide_markdown: str


@dataclass(frozen=True)
class PromotionsNoPriorBatch1CompletionHelperArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    guide_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsNoPriorBatch1CompletionHelperError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsNoPriorBatch1CompletionHelperError(
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
        raise PromotionsNoPriorBatch1CompletionHelperError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsNoPriorBatch1CompletionHelperError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _summary_row(
    metric_group: str,
    metric_name: str,
    metric_value: object,
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


def _batch1_match(row: pd.Series) -> bool:
    review_sequence_group = str(row.get("review_sequence_group", "")).strip()
    review_batch = str(row.get("review_batch", "")).strip()
    return review_sequence_group == BATCH_1_FAST_HIGH_VALUE or review_batch in BATCH_1_REVIEW_BATCH_ALIASES


def _batch1_review_instruction(row: pd.Series) -> str:
    return (
        f"Complete the manual fields for Batch 1 rank {int(row['operator_review_sequence_rank'])} first, then merge the completed fields back into the main manual worksheet before rerunning ingest."
    )


def _what_to_check_first(row: pd.Series) -> str:
    primary = str(row["primary_evidence_to_check"]).strip()
    secondary = str(row["secondary_evidence_to_check"]).strip()
    if secondary and secondary != primary:
        return f"Start with: {primary} Then confirm: {secondary}"
    return f"Start with: {primary}"


def _candidate_threshold_reminder() -> str:
    return (
        "Only use ADD_TO_REVIEW_RULE_CANDIDATES when the cause looks repeatable and commercially sensible. Otherwise prefer KEEP_SHADOW_ONLY, INSPECT_DATA_QUALITY, NO_CHANGE, or ESCALATE_FOR_OPERATOR_REVIEW as appropriate."
    )


def _merge_ingest_columns(
    *,
    batch1_rows: pd.DataFrame,
    manual_completion_rows_frame: pd.DataFrame,
) -> pd.DataFrame:
    merged = batch1_rows.copy()

    manual_completion_lookup = manual_completion_rows_frame.copy()
    _require_columns(
        manual_completion_lookup,
        ("sku_number",) + MANUAL_COMPLETION_JOIN_COLUMNS,
        frame_name="manual_completion_rows_frame",
    )
    manual_completion_lookup = manual_completion_lookup.loc[
        :,
        ["sku_number", *MANUAL_COMPLETION_JOIN_COLUMNS],
    ].drop_duplicates(subset=["sku_number"], keep="first")

    merged = merged.merge(
        manual_completion_lookup,
        on="sku_number",
        how="left",
        suffixes=("", "__manual_completion"),
    )

    if "review_priority_rank" in merged.columns:
        merged["review_priority_rank"] = pd.to_numeric(
            merged["review_priority_rank"],
            errors="coerce",
        )
    else:
        merged["review_priority_rank"] = pd.NA
    merged["review_priority_rank"] = merged["review_priority_rank"].fillna(
        pd.to_numeric(merged["operator_review_sequence_rank"], errors="coerce")
    )

    for column_name in ("operator_decision", "operator_action", "order_units", "proposed_review_action"):
        if column_name not in merged.columns:
            merged[column_name] = ""
        fallback_column_name = f"{column_name}__manual_completion"
        if fallback_column_name in merged.columns:
            merged[column_name] = merged[column_name].where(
                merged[column_name].astype(str).str.strip().ne(""),
                merged[fallback_column_name],
            )

    cleanup_columns = [
        column_name
        for column_name in merged.columns
        if column_name.endswith("__manual_completion")
    ]
    if cleanup_columns:
        merged = merged.drop(columns=cleanup_columns)

    return merged


def _sequence_rank_gap_count(rows_frame: pd.DataFrame) -> int:
    ranks = pd.to_numeric(rows_frame["operator_review_sequence_rank"], errors="coerce").fillna(0).astype(int)
    if ranks.empty:
        return 0
    expected = set(range(int(ranks.min()), int(ranks.max()) + 1))
    actual = set(ranks.tolist())
    duplicate_count = len(ranks.tolist()) - len(actual)
    missing_count = len(expected - actual)
    return duplicate_count + missing_count


def _build_rows_frame(
    operator_review_sequence_rows_frame: pd.DataFrame,
    manual_completion_rows_frame: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(
        operator_review_sequence_rows_frame,
        PRESERVED_COLUMNS + MANUAL_COLUMNS,
        frame_name="operator_review_sequence_rows_frame",
    )

    batch1_rows = operator_review_sequence_rows_frame.loc[
        operator_review_sequence_rows_frame.apply(_batch1_match, axis=1)
    ].copy()
    if batch1_rows.empty:
        raise PromotionsNoPriorBatch1CompletionHelperError(
            "No Batch 1 rows found in the operator review sequence."
        )

    batch1_rows = batch1_rows.sort_values(
        by=["operator_review_sequence_rank", "sku_number"],
        ascending=[True, True],
        kind="stable",
    ).reset_index(drop=True)

    batch1_rows = _merge_ingest_columns(
        batch1_rows=batch1_rows,
        manual_completion_rows_frame=manual_completion_rows_frame,
    )

    rows_frame = batch1_rows.loc[:, PRESERVED_COLUMNS + INGEST_REQUIRED_COLUMNS].copy()
    for column_name in MANUAL_COLUMNS:
        rows_frame[column_name] = ""

    rows_frame["batch1_review_instruction"] = rows_frame.apply(_batch1_review_instruction, axis=1)
    rows_frame["what_to_check_first"] = rows_frame.apply(_what_to_check_first, axis=1)
    rows_frame["candidate_threshold_reminder"] = _candidate_threshold_reminder()
    rows_frame["completion_required_flag"] = 1
    return rows_frame.loc[:, PRESERVED_COLUMNS + INGEST_REQUIRED_COLUMNS + MANUAL_COLUMNS + HELPER_COLUMNS]


def _build_summary_frame(
    rows_frame: pd.DataFrame,
    source_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows_prepared = int(len(rows_frame.index))
    do_not_auto_label_rows = int(
        pd.to_numeric(rows_frame["do_not_auto_label_flag"], errors="coerce").fillna(0).eq(1).sum()
    )
    do_not_auto_label_warning_rows = int(
        pd.to_numeric(rows_frame["do_not_auto_label_flag"], errors="coerce").fillna(0).ne(1).sum()
    )
    manual_fields_blank_rows = int(
        rows_frame.loc[:, MANUAL_COLUMNS].fillna("").astype(str).eq("").all(axis=1).sum()
    )
    completion_required_rows = int(
        pd.to_numeric(rows_frame["completion_required_flag"], errors="coerce").fillna(0).eq(1).sum()
    )
    total_gross_profit = round(
        float(pd.to_numeric(rows_frame["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
        2,
    )
    total_recommended_review_minutes = int(
        pd.to_numeric(rows_frame["recommended_review_time_minutes"], errors="coerce").fillna(0).sum()
    )
    first_sequence_rank = int(
        pd.to_numeric(rows_frame["operator_review_sequence_rank"], errors="coerce").fillna(0).min()
    )
    last_sequence_rank = int(
        pd.to_numeric(rows_frame["operator_review_sequence_rank"], errors="coerce").fillna(0).max()
    )
    sequence_rank_gap_count = _sequence_rank_gap_count(rows_frame)
    production_order_changes = 0
    stage12_changes = 0
    if "production_order_change_flag" in source_frame.columns:
        production_order_changes = int(
            pd.to_numeric(source_frame["production_order_change_flag"], errors="coerce").fillna(0).sum()
        )
    if "stage_12_change_flag" in source_frame.columns:
        stage12_changes = int(
            pd.to_numeric(source_frame["stage_12_change_flag"], errors="coerce").fillna(0).sum()
        )

    rows = [
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "ROWS_PREPARED",
            rows_prepared,
            "rows",
            _format_int(rows_prepared),
            "Batch 1 rows prepared for manual completion.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "DO_NOT_AUTO_LABEL_ROWS",
            do_not_auto_label_rows,
            "rows",
            _format_int(do_not_auto_label_rows),
            "Rows that remain operator-labelled only.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "MANUAL_FIELDS_BLANK_ROWS",
            manual_fields_blank_rows,
            "rows",
            _format_int(manual_fields_blank_rows),
            "The Batch 1 helper leaves all manual judgement fields blank.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "COMPLETION_REQUIRED_ROWS",
            completion_required_rows,
            "rows",
            _format_int(completion_required_rows),
            "Rows flagged for completion before the next ingest pass.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "TOTAL_GROSS_PROFIT_REPRESENTED",
            total_gross_profit,
            "dollars",
            _format_money(total_gross_profit),
            "Gross profit represented by the Batch 1 rows.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "TOTAL_RECOMMENDED_REVIEW_MINUTES",
            total_recommended_review_minutes,
            "minutes",
            _format_int(total_recommended_review_minutes),
            "Estimated review time for Batch 1.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "FIRST_SEQUENCE_RANK",
            first_sequence_rank,
            "rank",
            _format_int(first_sequence_rank),
            "First operator review sequence rank in Batch 1.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "LAST_SEQUENCE_RANK",
            last_sequence_rank,
            "rank",
            _format_int(last_sequence_rank),
            "Last operator review sequence rank in Batch 1.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "SEQUENCE_RANK_GAP_COUNT",
            sequence_rank_gap_count,
            "count",
            _format_int(sequence_rank_gap_count),
            "Batch 1 rows should stay in operator sequence order without missing ranks.",
        ),
        _summary_row(
            "BATCH1_COMPLETION_HELPER",
            "RECOMMENDATION",
            "COMPLETE_BATCH1_FIRST",
            "label",
            "COMPLETE_BATCH1_FIRST",
            "Complete Batch 1 first, then hand the completed fields back to the main worksheet or ingest path.",
        ),
        _summary_row(
            "VALIDATION",
            "DO_NOT_AUTO_LABEL_WARNING_ROWS",
            do_not_auto_label_warning_rows,
            "rows",
            _format_int(do_not_auto_label_warning_rows),
            "Rows where do_not_auto_label_flag was not equal to 1.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            production_order_changes,
            "rows",
            _format_int(production_order_changes),
            "This helper does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage12_changes,
            "rows",
            _format_int(stage12_changes),
            "This helper does not change Stage 12.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_guide_markdown(rows_frame: pd.DataFrame) -> str:
    rows_prepared = int(len(rows_frame.index))
    total_gross_profit = round(
        float(pd.to_numeric(rows_frame["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
        2,
    )
    total_minutes = int(
        pd.to_numeric(rows_frame["recommended_review_time_minutes"], errors="coerce").fillna(0).sum()
    )
    sku_list = ", ".join(rows_frame["sku_number"].astype(str).tolist())
    lines = [
        "# No-Prior Batch 1 Completion Helper Guide",
        "",
        "This is not an order file.",
        "This does not infer labels.",
        "Production order changes = 0.",
        "Stage 12 changes = 0.",
        "",
        f"The purpose is to complete only Batch 1 first for these {rows_prepared} rows.",
        "Batch 1 should be reviewed first because it has the fastest high-value learning potential.",
        f"Batch 1 SKUs: {sku_list}.",
        f"Batch 1 gross profit represented: {_format_money(total_gross_profit)}.",
        f"Estimated review time: {_format_int(total_minutes)} minutes.",
        "",
        "How to use this helper:",
        "1. Fill only the manual judgement fields for these Batch 1 rows.",
        "2. Keep the final manual_cause_label and manual_next_action as human decisions only.",
        "3. After completion, either paste those manual fields back into the main no_prior_manual_completion_rows.csv file or run run_promotions_no_prior_manual_inspection_ingest.py with --worksheet-path pointing to a completed Batch 1 file.",
        "4. Candidate decisions remain shadow-only until repeated evidence appears across more promotions.",
        "",
        f"Allowed manual_cause_label values: {', '.join(MANUAL_CAUSE_LABEL_VALUES)}.",
        f"Allowed manual_next_action values: {', '.join(MANUAL_NEXT_ACTION_VALUES)}.",
    ]
    return "\n".join(lines) + "\n"


def build_promotions_no_prior_batch1_completion_helper(
    *,
    operator_review_sequence_rows_frame: pd.DataFrame,
    manual_completion_rows_frame: pd.DataFrame,
) -> PromotionsNoPriorBatch1CompletionHelperResult:
    rows_frame = _build_rows_frame(
        operator_review_sequence_rows_frame,
        manual_completion_rows_frame,
    )
    summary_frame = _build_summary_frame(rows_frame, operator_review_sequence_rows_frame)
    guide_markdown = _build_guide_markdown(rows_frame)
    return PromotionsNoPriorBatch1CompletionHelperResult(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        guide_markdown=guide_markdown,
    )


def write_promotions_no_prior_batch1_completion_helper(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsNoPriorBatch1CompletionHelperArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsNoPriorBatch1CompletionHelperError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_no_prior_batch1_completion_helper(
        operator_review_sequence_rows_frame=_read_csv(review_artifact_path / INPUT_ROWS_RELATIVE_PATH),
        manual_completion_rows_frame=_read_csv(review_artifact_path / MANUAL_COMPLETION_ROWS_RELATIVE_PATH),
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

    rows_csv_path = destination_root / "no_prior_batch1_completion_rows.csv"
    summary_csv_path = destination_root / "no_prior_batch1_completion_summary.csv"
    guide_md_path = destination_root / "no_prior_batch1_completion_guide.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    guide_md_path.write_text(result.guide_markdown, encoding="utf-8")

    return PromotionsNoPriorBatch1CompletionHelperArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        guide_md_path=str(guide_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed Batch 1 manual-completion helper for no-prior operator review sequence rows."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_no_prior_batch1_completion_helper(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("no_prior_batch1_completion_rows", artifacts.rows_csv_path)
    print("no_prior_batch1_completion_summary", artifacts.summary_csv_path)
    print("no_prior_batch1_completion_guide", artifacts.guide_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())