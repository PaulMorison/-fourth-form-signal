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


OUTPUT_FOLDER_NAME = "operator_review_sequence"
INPUT_ROWS_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/manual_label_assistance_pack/no_prior_manual_label_assistance_rows.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
)

PRESERVED_COLUMNS: tuple[str, ...] = (
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

SEQUENCE_COLUMNS: tuple[str, ...] = (
    "operator_review_sequence_rank",
    "review_sequence_group",
    "review_sequence_reason",
    "expected_learning_value",
    "estimated_review_difficulty",
    "recommended_review_time_minutes",
    "review_batch",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)

BY_DEPARTMENT_COLUMNS: tuple[str, ...] = (
    "department",
    "row_count",
    "high_priority_rows",
    "batch_1_rows",
    "batch_2_rows",
    "batch_3_rows",
    "batch_4_rows",
    "very_high_learning_value_rows",
    "average_recommended_review_time_minutes",
    "actual_gross_profit_total",
    "first_sequence_rank",
    "sample_skus",
)

BATCH_1_FAST_HIGH_VALUE = "BATCH_1_FAST_HIGH_VALUE"
BATCH_2_CATEGORY_PATTERN_CHECK = "BATCH_2_CATEGORY_PATTERN_CHECK"
BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK = "BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK"
BATCH_4_LOW_VALUE_OR_UNCLEAR = "BATCH_4_LOW_VALUE_OR_UNCLEAR"

REVIEW_SEQUENCE_GROUP_ORDER: dict[str, int] = {
    BATCH_1_FAST_HIGH_VALUE: 1,
    BATCH_2_CATEGORY_PATTERN_CHECK: 2,
    BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK: 3,
    BATCH_4_LOW_VALUE_OR_UNCLEAR: 4,
}

REVIEW_BATCH_LABELS: dict[str, str] = {
    BATCH_1_FAST_HIGH_VALUE: "BATCH_1",
    BATCH_2_CATEGORY_PATTERN_CHECK: "BATCH_2",
    BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK: "BATCH_3",
    BATCH_4_LOW_VALUE_OR_UNCLEAR: "BATCH_4",
}

LEARNING_VALUE_ORDER: dict[str, int] = {
    "VERY_HIGH": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}

DIFFICULTY_ORDER: dict[str, int] = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
}

RECOMMENDED_MINUTES_BY_DIFFICULTY: dict[str, int] = {
    "LOW": 3,
    "MEDIUM": 5,
    "HIGH": 8,
}

HIGH_GROSS_PROFIT_THRESHOLD = 40.0
VERY_HIGH_GROSS_PROFIT_THRESHOLD = 60.0
LOW_GROSS_PROFIT_THRESHOLD = 15.0
HIGH_FORECAST_ERROR_THRESHOLD = 5.0
VERY_HIGH_FORECAST_ERROR_THRESHOLD = 8.0
LOW_CAPITAL_LEFT_THRESHOLD = 5.0


class PromotionsNoPriorOperatorReviewSequenceError(RuntimeError):
    """Raised when the governed operator review sequence cannot be built safely."""


@dataclass(frozen=True)
class PromotionsNoPriorOperatorReviewSequenceResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    guide_markdown: str


@dataclass(frozen=True)
class PromotionsNoPriorOperatorReviewSequenceArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    by_department_csv_path: str
    guide_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsNoPriorOperatorReviewSequenceError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsNoPriorOperatorReviewSequenceError(
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
        raise PromotionsNoPriorOperatorReviewSequenceError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsNoPriorOperatorReviewSequenceError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


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


def _sample_skus(values: pd.Series, *, limit: int = 5) -> str:
    unique_values: list[str] = []
    for value in values.astype(str).tolist():
        cleaned = value.strip()
        if not cleaned or cleaned in unique_values:
            continue
        unique_values.append(cleaned)
        if len(unique_values) >= limit:
            break
    return ", ".join(unique_values)


def _high_priority_flag(row: pd.Series) -> bool:
    return str(row["inspection_priority"]).strip().upper() == "HIGH"


def _high_forecast_error(row: pd.Series) -> bool:
    return abs(_as_float(row["forecast_error_units"])) >= HIGH_FORECAST_ERROR_THRESHOLD


def _very_high_forecast_error(row: pd.Series) -> bool:
    return abs(_as_float(row["forecast_error_units"])) >= VERY_HIGH_FORECAST_ERROR_THRESHOLD


def _low_capital_left(row: pd.Series) -> bool:
    return _as_float(row["capital_left_in_unsold_store_allocation"]) <= LOW_CAPITAL_LEFT_THRESHOLD


def _low_availability(row: pd.Series) -> bool:
    current_soh = _as_float(row["current_soh_units"])
    projected_on_hand = _as_float(row["projected_on_hand_at_promo_start"])
    target_stock = _as_float(row["target_stock_day_one_units"])
    return current_soh <= target_stock or projected_on_hand <= target_stock


def _is_skincare(row: pd.Series) -> bool:
    return str(row["department"]).strip().upper() == "SKINCARE"


def _review_sequence_group(row: pd.Series) -> str:
    if _high_priority_flag(row) and _low_capital_left(row):
        return BATCH_1_FAST_HIGH_VALUE
    if _is_skincare(row):
        return BATCH_2_CATEGORY_PATTERN_CHECK
    if _low_availability(row):
        return BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK
    return BATCH_4_LOW_VALUE_OR_UNCLEAR


def _expected_learning_value(row: pd.Series, review_sequence_group: str) -> str:
    gross_profit = _as_float(row["actual_gross_profit"])
    if review_sequence_group == BATCH_1_FAST_HIGH_VALUE:
        if gross_profit >= VERY_HIGH_GROSS_PROFIT_THRESHOLD or _very_high_forecast_error(row):
            return "VERY_HIGH"
        return "HIGH"
    if review_sequence_group == BATCH_2_CATEGORY_PATTERN_CHECK:
        if gross_profit >= LOW_GROSS_PROFIT_THRESHOLD or _high_forecast_error(row):
            return "HIGH"
        return "MEDIUM"
    if review_sequence_group == BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK:
        return "MEDIUM"
    if gross_profit <= LOW_GROSS_PROFIT_THRESHOLD:
        return "LOW"
    return "MEDIUM"


def _estimated_review_difficulty(row: pd.Series, review_sequence_group: str) -> str:
    if review_sequence_group == BATCH_1_FAST_HIGH_VALUE:
        return "HIGH" if _low_availability(row) else "MEDIUM"
    if review_sequence_group == BATCH_2_CATEGORY_PATTERN_CHECK:
        if _low_availability(row) or _high_forecast_error(row):
            return "MEDIUM"
        return "LOW"
    if review_sequence_group == BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK:
        return "HIGH" if _low_availability(row) else "MEDIUM"
    if _as_float(row["actual_gross_profit"]) <= LOW_GROSS_PROFIT_THRESHOLD:
        return "LOW"
    return "MEDIUM"


def _recommended_review_time_minutes(estimated_review_difficulty: str) -> int:
    return RECOMMENDED_MINUTES_BY_DIFFICULTY[estimated_review_difficulty]


def _review_sequence_reason(row: pd.Series, review_sequence_group: str) -> str:
    if review_sequence_group == BATCH_1_FAST_HIGH_VALUE:
        if _high_forecast_error(row):
            return (
                "High gross profit, a large forecast miss, and little capital left make this an early high-value review."
            )
        return (
            "High gross profit and little capital left make this an early high-value review even though the forecast miss is less extreme."
        )
    if review_sequence_group == BATCH_2_CATEGORY_PATTERN_CHECK:
        return (
            "Review this SKINCARE row alongside similar category rows so the operator can detect repeatable pattern signals faster."
        )
    if review_sequence_group == BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK:
        return (
            "Availability or operational context may explain the surprise, so review it after the high-value and category-pattern passes."
        )
    return (
        "This is lower-value or less clear, so leave it until the higher-value and clearer rows are finished."
    )


def _priority_score(row: pd.Series, review_sequence_group: str) -> float:
    gross_profit = _as_float(row["actual_gross_profit"])
    forecast_error_abs = abs(_as_float(row["forecast_error_units"]))
    score = gross_profit + (forecast_error_abs * 6.0)
    if _low_capital_left(row):
        score += 10.0
    if _low_availability(row):
        score += 8.0
    if review_sequence_group == BATCH_2_CATEGORY_PATTERN_CHECK:
        score += 6.0
    if review_sequence_group == BATCH_4_LOW_VALUE_OR_UNCLEAR:
        score -= 10.0
    return score


def _sequence_rank_gap_count(rows_frame: pd.DataFrame) -> int:
    expected_ranks = set(range(1, len(rows_frame.index) + 1))
    actual_ranks = pd.to_numeric(
        rows_frame["operator_review_sequence_rank"],
        errors="coerce",
    ).fillna(0).astype(int)
    actual_rank_set = set(actual_ranks.tolist())
    duplicate_count = len(actual_ranks.tolist()) - len(actual_rank_set)
    missing_count = len(expected_ranks - actual_rank_set)
    return duplicate_count + missing_count


def _build_rows_frame(manual_label_assistance_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        manual_label_assistance_rows_frame,
        PRESERVED_COLUMNS + MANUAL_COLUMNS,
        frame_name="manual_label_assistance_rows_frame",
    )

    rows_frame = manual_label_assistance_rows_frame.loc[:, PRESERVED_COLUMNS].copy()
    for column_name in MANUAL_COLUMNS:
        rows_frame[column_name] = ""

    rows_frame["review_sequence_group"] = manual_label_assistance_rows_frame.apply(
        _review_sequence_group,
        axis=1,
    )
    rows_frame["review_sequence_reason"] = rows_frame.apply(
        lambda row: _review_sequence_reason(row, str(row["review_sequence_group"])),
        axis=1,
    )
    rows_frame["expected_learning_value"] = rows_frame.apply(
        lambda row: _expected_learning_value(row, str(row["review_sequence_group"])),
        axis=1,
    )
    rows_frame["estimated_review_difficulty"] = rows_frame.apply(
        lambda row: _estimated_review_difficulty(row, str(row["review_sequence_group"])),
        axis=1,
    )
    rows_frame["recommended_review_time_minutes"] = rows_frame[
        "estimated_review_difficulty"
    ].map(_recommended_review_time_minutes)
    rows_frame["review_batch"] = rows_frame["review_sequence_group"].map(REVIEW_BATCH_LABELS)

    rows_frame["_group_order"] = rows_frame["review_sequence_group"].map(REVIEW_SEQUENCE_GROUP_ORDER)
    rows_frame["_learning_order"] = rows_frame["expected_learning_value"].map(LEARNING_VALUE_ORDER)
    rows_frame["_difficulty_order"] = rows_frame["estimated_review_difficulty"].map(DIFFICULTY_ORDER)
    rows_frame["_priority_score"] = rows_frame.apply(
        lambda row: _priority_score(row, str(row["review_sequence_group"])),
        axis=1,
    )

    rows_frame = rows_frame.sort_values(
        by=[
            "_group_order",
            "_learning_order",
            "_priority_score",
            "_difficulty_order",
            "department",
            "sku_number",
        ],
        ascending=[True, False, False, True, True, True],
        kind="stable",
    ).reset_index(drop=True)
    rows_frame["operator_review_sequence_rank"] = list(range(1, len(rows_frame.index) + 1))
    return rows_frame.loc[
        :,
        PRESERVED_COLUMNS + MANUAL_COLUMNS + SEQUENCE_COLUMNS,
    ]


def _build_summary_frame(
    rows_frame: pd.DataFrame,
    source_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows_sequenced = int(len(rows_frame.index))
    high_priority_rows = int(rows_frame["inspection_priority"].astype(str).str.upper().eq("HIGH").sum())
    do_not_auto_label_rows = int(
        pd.to_numeric(rows_frame["do_not_auto_label_flag"], errors="coerce").fillna(0).eq(1).sum()
    )
    do_not_auto_label_warning_rows = int(
        pd.to_numeric(rows_frame["do_not_auto_label_flag"], errors="coerce").fillna(0).ne(1).sum()
    )
    manual_fields_blank_rows = int(
        rows_frame.loc[:, MANUAL_COLUMNS].fillna("").astype(str).eq("").all(axis=1).sum()
    )
    sequence_rank_gap_count = _sequence_rank_gap_count(rows_frame)
    total_recommended_review_minutes = int(
        pd.to_numeric(rows_frame["recommended_review_time_minutes"], errors="coerce").fillna(0).sum()
    )
    departments_covered = int(rows_frame["department"].astype(str).nunique(dropna=True))

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
            "OPERATOR_REVIEW_SEQUENCE",
            "ROWS_SEQUENCED",
            rows_sequenced,
            "rows",
            _format_int(rows_sequenced),
            "Rows ranked into the governed manual-review sequence.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "BATCH_1_ROWS",
            int(rows_frame["review_sequence_group"].eq(BATCH_1_FAST_HIGH_VALUE).sum()),
            "rows",
            _format_int(int(rows_frame["review_sequence_group"].eq(BATCH_1_FAST_HIGH_VALUE).sum())),
            "Start with these fast high-value rows.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "BATCH_2_ROWS",
            int(rows_frame["review_sequence_group"].eq(BATCH_2_CATEGORY_PATTERN_CHECK).sum()),
            "rows",
            _format_int(int(rows_frame["review_sequence_group"].eq(BATCH_2_CATEGORY_PATTERN_CHECK).sum())),
            "Then review the category-pattern rows together.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "BATCH_3_ROWS",
            int(rows_frame["review_sequence_group"].eq(BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK).sum()),
            "rows",
            _format_int(int(rows_frame["review_sequence_group"].eq(BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK).sum())),
            "Then review operational or availability-driven rows.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "BATCH_4_ROWS",
            int(rows_frame["review_sequence_group"].eq(BATCH_4_LOW_VALUE_OR_UNCLEAR).sum()),
            "rows",
            _format_int(int(rows_frame["review_sequence_group"].eq(BATCH_4_LOW_VALUE_OR_UNCLEAR).sum())),
            "Finish with the lower-value or less-clear rows.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "HIGH_PRIORITY_ROWS",
            high_priority_rows,
            "rows",
            _format_int(high_priority_rows),
            "Rows already marked HIGH in the assistance pack.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "DO_NOT_AUTO_LABEL_ROWS",
            do_not_auto_label_rows,
            "rows",
            _format_int(do_not_auto_label_rows),
            "Rows still governed as operator-labelled only.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "MANUAL_FIELDS_BLANK_ROWS",
            manual_fields_blank_rows,
            "rows",
            _format_int(manual_fields_blank_rows),
            "The sequence pack leaves every manual judgement field blank.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "SEQUENCE_RANK_GAP_COUNT",
            sequence_rank_gap_count,
            "count",
            _format_int(sequence_rank_gap_count),
            "The ranked sequence should run from 1 to N without gaps.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "DEPARTMENTS_COVERED",
            departments_covered,
            "departments",
            _format_int(departments_covered),
            "Unique departments represented in the sequence pack.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "TOTAL_RECOMMENDED_REVIEW_MINUTES",
            total_recommended_review_minutes,
            "minutes",
            _format_int(total_recommended_review_minutes),
            "Estimated total operator review time for the full sequence.",
        ),
        _summary_row(
            "OPERATOR_REVIEW_SEQUENCE",
            "RECOMMENDATION",
            "START_WITH_BATCH_1_FAST_HIGH_VALUE",
            "label",
            "START_WITH_BATCH_1_FAST_HIGH_VALUE",
            "Start with BATCH_1_FAST_HIGH_VALUE, then follow the ranked sequence.",
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
            "This sequence pack does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage12_changes,
            "rows",
            _format_int(stage12_changes),
            "This sequence pack does not change Stage 12.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_by_department_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for department, group in rows_frame.groupby("department", sort=False, dropna=False):
        records.append(
            {
                "department": str(department),
                "row_count": int(len(group.index)),
                "high_priority_rows": int(group["inspection_priority"].astype(str).str.upper().eq("HIGH").sum()),
                "batch_1_rows": int(group["review_sequence_group"].eq(BATCH_1_FAST_HIGH_VALUE).sum()),
                "batch_2_rows": int(group["review_sequence_group"].eq(BATCH_2_CATEGORY_PATTERN_CHECK).sum()),
                "batch_3_rows": int(group["review_sequence_group"].eq(BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK).sum()),
                "batch_4_rows": int(group["review_sequence_group"].eq(BATCH_4_LOW_VALUE_OR_UNCLEAR).sum()),
                "very_high_learning_value_rows": int(group["expected_learning_value"].eq("VERY_HIGH").sum()),
                "average_recommended_review_time_minutes": round(
                    float(pd.to_numeric(group["recommended_review_time_minutes"], errors="coerce").fillna(0).mean()),
                    2,
                ),
                "actual_gross_profit_total": round(
                    float(pd.to_numeric(group["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
                    2,
                ),
                "first_sequence_rank": int(
                    pd.to_numeric(group["operator_review_sequence_rank"], errors="coerce").fillna(0).min()
                ),
                "sample_skus": _sample_skus(group["sku_number"]),
            }
        )
    by_department_frame = pd.DataFrame(records, columns=BY_DEPARTMENT_COLUMNS)
    return by_department_frame.sort_values(
        by=["row_count", "first_sequence_rank", "actual_gross_profit_total", "department"],
        ascending=[False, True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_guide_markdown(
    rows_frame: pd.DataFrame,
    by_department_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
) -> str:
    rows_sequenced = int(len(rows_frame.index))
    batch_1_rows = int(rows_frame["review_sequence_group"].eq(BATCH_1_FAST_HIGH_VALUE).sum())
    batch_2_rows = int(rows_frame["review_sequence_group"].eq(BATCH_2_CATEGORY_PATTERN_CHECK).sum())
    batch_3_rows = int(rows_frame["review_sequence_group"].eq(BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK).sum())
    batch_4_rows = int(rows_frame["review_sequence_group"].eq(BATCH_4_LOW_VALUE_OR_UNCLEAR).sum())
    top_departments = ", ".join(
        f"{row.department} ({int(row.row_count)})"
        for row in by_department_frame.head(3).itertuples(index=False)
    )
    warning_rows = int(
        summary_frame.loc[
            (summary_frame["metric_group"] == "VALIDATION")
            & (summary_frame["metric_name"] == "DO_NOT_AUTO_LABEL_WARNING_ROWS"),
            "metric_value",
        ].iloc[0]
    )
    lines = [
        "# No-Prior Operator Review Sequence Guide",
        "",
        "This is not an order file.",
        "This does not infer labels.",
        "Production order changes = 0.",
        "Stage 12 changes = 0.",
        "",
        f"The goal is to complete the {rows_sequenced} manual labels efficiently.",
        f"Top departments: {top_departments if top_departments else 'none'}.",
        "Recommend starting with BATCH_1_FAST_HIGH_VALUE.",
        "Candidate decisions remain shadow-only until repeated evidence appears across more promotions.",
        "",
        "Batch flow:",
        f"1. BATCH_1_FAST_HIGH_VALUE: {batch_1_rows} rows. Start with the highest-value rows that should give the fastest learning.",
        f"2. BATCH_2_CATEGORY_PATTERN_CHECK: {batch_2_rows} rows. Review similar category rows together, especially SKINCARE, while context is fresh.",
        f"3. BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK: {batch_3_rows} rows. Review rows where stock or operational context may explain the surprise.",
        f"4. BATCH_4_LOW_VALUE_OR_UNCLEAR: {batch_4_rows} rows. Finish with the lower-value or less-clear rows.",
        "",
        "The sequence helps the operator move faster, but the operator must still choose the final manual label.",
    ]
    if warning_rows > 0:
        lines.extend(
            [
                "",
                f"Validation warning: {warning_rows} rows arrived with do_not_auto_label_flag not equal to 1. Review those rows carefully before use.",
            ]
        )
    return "\n".join(lines) + "\n"


def build_promotions_no_prior_operator_review_sequence(
    *,
    manual_label_assistance_rows_frame: pd.DataFrame,
) -> PromotionsNoPriorOperatorReviewSequenceResult:
    rows_frame = _build_rows_frame(manual_label_assistance_rows_frame)
    summary_frame = _build_summary_frame(rows_frame, manual_label_assistance_rows_frame)
    by_department_frame = _build_by_department_frame(rows_frame)
    guide_markdown = _build_guide_markdown(rows_frame, by_department_frame, summary_frame)
    return PromotionsNoPriorOperatorReviewSequenceResult(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_department_frame=by_department_frame,
        guide_markdown=guide_markdown,
    )


def write_promotions_no_prior_operator_review_sequence(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsNoPriorOperatorReviewSequenceArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsNoPriorOperatorReviewSequenceError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_no_prior_operator_review_sequence(
        manual_label_assistance_rows_frame=_read_csv(review_artifact_path / INPUT_ROWS_RELATIVE_PATH),
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

    rows_csv_path = destination_root / "no_prior_operator_review_sequence_rows.csv"
    summary_csv_path = destination_root / "no_prior_operator_review_sequence_summary.csv"
    by_department_csv_path = destination_root / "no_prior_operator_review_sequence_by_department.csv"
    guide_md_path = destination_root / "no_prior_operator_review_sequence_guide.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    add_provenance_columns(result.by_department_frame.copy(), manifest).to_csv(
        by_department_csv_path,
        index=False,
    )
    guide_md_path.write_text(result.guide_markdown, encoding="utf-8")

    return PromotionsNoPriorOperatorReviewSequenceArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        guide_md_path=str(guide_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed operator review sequence for no-prior-demand manual-label assistance rows without inferring final labels."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_no_prior_operator_review_sequence(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("no_prior_operator_review_sequence_rows", artifacts.rows_csv_path)
    print("no_prior_operator_review_sequence_summary", artifacts.summary_csv_path)
    print("no_prior_operator_review_sequence_by_department", artifacts.by_department_csv_path)
    print("no_prior_operator_review_sequence_guide", artifacts.guide_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())