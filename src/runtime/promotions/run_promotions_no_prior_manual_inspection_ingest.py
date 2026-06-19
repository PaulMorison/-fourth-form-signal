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


OUTPUT_FOLDER_NAME = "inspection_ingest"
INPUT_ROWS_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/no_prior_demand_manual_inspection_rows.csv"
)

FULL_NO_PRIOR_18 = "FULL_NO_PRIOR_18"
BATCH_1_FAST_HIGH_VALUE = "BATCH_1_FAST_HIGH_VALUE"
INSPECTION_SCOPE_CHOICES: tuple[str, ...] = (
    FULL_NO_PRIOR_18,
    BATCH_1_FAST_HIGH_VALUE,
)
INSPECTION_SCOPE_EXPECTED_ROWS: dict[str, int] = {
    FULL_NO_PRIOR_18: 18,
    BATCH_1_FAST_HIGH_VALUE: 8,
}
INSPECTION_SCOPE_PARTIAL_FLAGS: dict[str, int] = {
    FULL_NO_PRIOR_18: 0,
    BATCH_1_FAST_HIGH_VALUE: 1,
}
INSPECTION_SCOPE_OUTPUT_RELATIVE_PATHS: dict[str, Path] = {
    FULL_NO_PRIOR_18: Path(
        "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/inspection_ingest"
    ),
    BATCH_1_FAST_HIGH_VALUE: Path(
        "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/batch1_completion_helper/inspection_ingest"
    ),
}
SCOPE_METADATA_COLUMNS: tuple[str, ...] = (
    "inspection_scope",
    "expected_scope_rows",
    "actual_scope_rows",
    "partial_review_flag",
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
)

CANDIDATE_RULE_BY_CAUSE: dict[str, str] = {
    "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED": "NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE",
    "STORE_SPECIFIC_DEMAND_NOT_CAPTURED": "NO_PRIOR_STORE_SPECIFIC_DEMAND_REVIEW_RULE",
    "ONLINE_OR_AVAILABILITY_EFFECT": "NO_PRIOR_ONLINE_AVAILABILITY_REVIEW_RULE",
    "PRICE_OR_PROMO_MECHANIC_EFFECT": "NO_PRIOR_PRICE_MECHANIC_REVIEW_RULE",
    "BASKET_OR_MISSION_EFFECT": "NO_PRIOR_BASKET_MISSION_REVIEW_RULE",
    "DATA_GAP_OR_LABEL_ERROR": "NO_PRIOR_DATA_QUALITY_REVIEW_RULE",
}

REPEATABLE_CAUSE_LABELS: tuple[str, ...] = tuple(CANDIDATE_RULE_BY_CAUSE.keys())
ONE_OFF_CAUSE_LABEL = "RANDOM_ONE_OFF_DEMAND"
UNKNOWN_CAUSE_LABEL = "UNKNOWN_REQUIRES_REVIEW"

REQUIRED_WORKSHEET_COLUMNS: tuple[str, ...] = (
    "review_priority_rank",
    "sku_number",
    "sku_description",
    "department",
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
    "manual_cause_label",
    "manual_confidence_score",
    "manual_notes",
    "manual_next_action",
    "should_add_review_rule_candidate",
    "should_remain_shadow_only",
)

OPTIONAL_GUARDRAIL_COLUMNS: tuple[str, ...] = (
    "production_order_change_flag",
    "stage_12_change_flag",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)

BY_CAUSE_COLUMNS: tuple[str, ...] = (
    "manual_cause_label_group",
    "cause_group_type",
    "row_count",
    "complete_rows",
    "incomplete_rows",
    "invalid_rows",
    "candidate_ready_rows",
    "gross_profit_total",
    "candidate_gross_profit_total",
    "capital_left_total",
    "sample_skus",
)

CANDIDATE_OUTPUT_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "manual_cause_label",
    "manual_confidence_score",
    "manual_notes",
    "actual_units_sold",
    "expected_promo_demand",
    "forecast_error_units",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "current_soh_units",
    "on_order_units",
    "projected_on_hand_at_promo_start",
    "target_stock_day_one_units",
    "proposed_review_rule_candidate",
    "candidate_reason",
    "production_order_change_flag",
    "stage_12_change_flag",
)


class PromotionsNoPriorManualInspectionIngestError(RuntimeError):
    """Raised when the no-prior manual inspection ingest layer cannot run safely."""


@dataclass(frozen=True)
class PromotionsNoPriorManualInspectionIngestResult:
    validated_rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_cause_frame: pd.DataFrame
    candidate_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsNoPriorManualInspectionIngestArtifacts:
    validated_rows_csv_path: str
    summary_csv_path: str
    by_cause_csv_path: str
    review_rule_candidates_csv_path: str
    memo_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsNoPriorManualInspectionIngestError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsNoPriorManualInspectionIngestError(
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
        raise PromotionsNoPriorManualInspectionIngestError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _resolve_rows_path(
    review_artifact_root: Path,
    worksheet_path: str | Path | None,
) -> Path:
    if worksheet_path is None:
        return review_artifact_root / INPUT_ROWS_RELATIVE_PATH

    candidate_path = Path(worksheet_path)
    if candidate_path.is_absolute():
        return candidate_path

    review_relative_path = review_artifact_root / candidate_path
    if review_relative_path.exists():
        return review_relative_path
    return candidate_path


def _require_inspection_scope(inspection_scope: str) -> str:
    normalized_scope = str(inspection_scope).strip()
    if normalized_scope not in INSPECTION_SCOPE_CHOICES:
        raise PromotionsNoPriorManualInspectionIngestError(
            f"inspection_scope must be one of: {', '.join(INSPECTION_SCOPE_CHOICES)}"
        )
    return normalized_scope


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsNoPriorManualInspectionIngestError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


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


def _with_scope_metadata(
    frame: pd.DataFrame,
    *,
    inspection_scope: str,
    expected_scope_rows: int,
    actual_scope_rows: int,
    partial_review_flag: int,
) -> pd.DataFrame:
    scoped_frame = frame.copy()
    scoped_frame["inspection_scope"] = inspection_scope
    scoped_frame["expected_scope_rows"] = int(expected_scope_rows)
    scoped_frame["actual_scope_rows"] = int(actual_scope_rows)
    scoped_frame["partial_review_flag"] = int(partial_review_flag)
    return scoped_frame


def _validate_scope_row_count(*, inspection_scope: str, actual_scope_rows: int) -> None:
    expected_scope_rows = INSPECTION_SCOPE_EXPECTED_ROWS[inspection_scope]
    if int(actual_scope_rows) != int(expected_scope_rows):
        raise PromotionsNoPriorManualInspectionIngestError(
            f"inspection_scope {inspection_scope} expects {expected_scope_rows} worksheet rows but received {actual_scope_rows}."
        )


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


def _normalize_choice(value: object, *, allowed_values: set[str], field_name: str) -> tuple[str, str | None]:
    cleaned = _normalize_text(value)
    if not cleaned:
        return "", None
    normalized = cleaned.upper()
    if normalized in allowed_values:
        return normalized, None
    return cleaned, f"{field_name} is not an allowed value"


def _normalize_confidence(value: object) -> tuple[object, float | None, str | None]:
    cleaned = _normalize_text(value)
    if not cleaned:
        return "", None, None
    try:
        numeric_value = float(cleaned)
    except ValueError:
        return cleaned, None, "manual_confidence_score must be numeric between 0 and 100"
    if numeric_value < 0 or numeric_value > 100:
        return cleaned, None, "manual_confidence_score must be numeric between 0 and 100"
    return numeric_value, numeric_value, None


def _normalize_optional_boolean(value: object, *, field_name: str) -> tuple[object, int | None, str | None]:
    cleaned = _normalize_text(value)
    if not cleaned:
        return "", None, None
    lowered = cleaned.lower()
    if lowered in {"true", "yes", "y", "1"}:
        return 1, 1, None
    if lowered in {"false", "no", "n", "0"}:
        return 0, 0, None
    try:
        numeric_value = float(cleaned)
    except ValueError:
        return cleaned, None, f"{field_name} must be 0/1, TRUE/FALSE, Yes/No, or blank"
    if numeric_value in {0.0, 1.0}:
        normalized = int(numeric_value)
        return normalized, normalized, None
    return cleaned, None, f"{field_name} must be 0/1, TRUE/FALSE, Yes/No, or blank"


def _cause_group_type(cause_label: str, *, status: str) -> str:
    if cause_label in REPEATABLE_CAUSE_LABELS:
        return "REPEATABLE_CAUSE"
    if cause_label == ONE_OFF_CAUSE_LABEL:
        return "ONE_OFF_DEMAND"
    if cause_label == UNKNOWN_CAUSE_LABEL:
        return "UNKNOWN_REQUIRES_REVIEW"
    if status == "INCOMPLETE":
        return "UNASSIGNED"
    return "INVALID_OR_OTHER"


def _build_candidate_reason(cause_label: str, confidence_score: float) -> str:
    return (
        f"Manual review tagged {cause_label} at {confidence_score:.0f}% confidence and requested a "
        "shadow-only review-rule candidate pending repeated evidence across more promotions."
    )


def _build_validated_rows_frame(worksheet_frame: pd.DataFrame) -> pd.DataFrame:
    frame = worksheet_frame.copy()
    for column_name in OPTIONAL_GUARDRAIL_COLUMNS:
        if column_name not in frame.columns:
            frame[column_name] = 0

    _require_columns(
        frame,
        REQUIRED_WORKSHEET_COLUMNS,
        frame_name="manual_inspection_rows_frame",
    )

    production_changes = int(pd.to_numeric(frame["production_order_change_flag"], errors="coerce").fillna(0).sum())
    stage12_changes = int(pd.to_numeric(frame["stage_12_change_flag"], errors="coerce").fillna(0).sum())
    if production_changes != 0:
        raise PromotionsNoPriorManualInspectionIngestError(
            "Manual inspection ingest attempted to carry production order changes."
        )
    if stage12_changes != 0:
        raise PromotionsNoPriorManualInspectionIngestError(
            "Manual inspection ingest attempted to carry Stage 12 changes."
        )

    normalized_cause_labels: list[object] = []
    normalized_confidence_scores: list[object] = []
    normalized_next_actions: list[object] = []
    normalized_add_flags: list[object] = []
    normalized_shadow_flags: list[object] = []
    manual_review_statuses: list[str] = []
    validation_issues: list[str] = []
    candidate_ready_flags: list[int] = []
    proposed_review_rule_candidates: list[str] = []
    candidate_reasons: list[str] = []
    manual_cause_label_groups: list[str] = []
    cause_group_types: list[str] = []

    allowed_cause_values = set(MANUAL_CAUSE_LABEL_VALUES)
    allowed_next_action_values = set(MANUAL_NEXT_ACTION_VALUES)

    for _, row in frame.iterrows():
        issues: list[str] = []
        normalized_cause_label, cause_issue = _normalize_choice(
            row["manual_cause_label"],
            allowed_values=allowed_cause_values,
            field_name="manual_cause_label",
        )
        if cause_issue:
            issues.append(cause_issue)

        normalized_confidence_score, parsed_confidence_score, confidence_issue = _normalize_confidence(
            row["manual_confidence_score"]
        )
        if confidence_issue:
            issues.append(confidence_issue)

        normalized_next_action, next_action_issue = _normalize_choice(
            row["manual_next_action"],
            allowed_values=allowed_next_action_values,
            field_name="manual_next_action",
        )
        if next_action_issue:
            issues.append(next_action_issue)

        normalized_add_flag, parsed_add_flag, add_issue = _normalize_optional_boolean(
            row["should_add_review_rule_candidate"],
            field_name="should_add_review_rule_candidate",
        )
        if add_issue:
            issues.append(add_issue)

        normalized_shadow_flag, _, shadow_issue = _normalize_optional_boolean(
            row["should_remain_shadow_only"],
            field_name="should_remain_shadow_only",
        )
        if shadow_issue:
            issues.append(shadow_issue)

        missing_required_fields: list[str] = []
        if not normalized_cause_label:
            missing_required_fields.append("manual_cause_label")
        if parsed_confidence_score is None:
            missing_required_fields.append("manual_confidence_score")
        if not normalized_next_action:
            missing_required_fields.append("manual_next_action")

        if issues:
            manual_review_status = "INVALID"
            validation_issue = "; ".join(issues)
        elif missing_required_fields:
            manual_review_status = "INCOMPLETE"
            validation_issue = ""
        else:
            manual_review_status = "COMPLETE"
            validation_issue = ""

        candidate_ready = int(
            manual_review_status == "COMPLETE"
            and parsed_add_flag == 1
            and parsed_confidence_score is not None
            and parsed_confidence_score >= 70.0
            and normalized_cause_label in CANDIDATE_RULE_BY_CAUSE
            and normalized_next_action == "ADD_TO_REVIEW_RULE_CANDIDATES"
        )
        proposed_review_rule_candidate = (
            CANDIDATE_RULE_BY_CAUSE[normalized_cause_label] if candidate_ready else ""
        )
        candidate_reason = (
            _build_candidate_reason(normalized_cause_label, parsed_confidence_score or 0.0)
            if candidate_ready
            else ""
        )
        manual_cause_label_group = (
            normalized_cause_label if normalized_cause_label else "UNASSIGNED"
        )
        cause_group_type = _cause_group_type(normalized_cause_label, status=manual_review_status)

        normalized_cause_labels.append(normalized_cause_label)
        normalized_confidence_scores.append(normalized_confidence_score)
        normalized_next_actions.append(normalized_next_action)
        normalized_add_flags.append(normalized_add_flag)
        normalized_shadow_flags.append(normalized_shadow_flag)
        manual_review_statuses.append(manual_review_status)
        validation_issues.append(validation_issue)
        candidate_ready_flags.append(candidate_ready)
        proposed_review_rule_candidates.append(proposed_review_rule_candidate)
        candidate_reasons.append(candidate_reason)
        manual_cause_label_groups.append(manual_cause_label_group)
        cause_group_types.append(cause_group_type)

    frame["normalized_manual_cause_label"] = normalized_cause_labels
    frame["normalized_manual_confidence_score"] = normalized_confidence_scores
    frame["normalized_manual_next_action"] = normalized_next_actions
    frame["normalized_should_add_review_rule_candidate"] = normalized_add_flags
    frame["normalized_should_remain_shadow_only"] = normalized_shadow_flags
    frame["manual_review_status"] = manual_review_statuses
    frame["validation_issue"] = validation_issues
    frame["candidate_ready_flag"] = candidate_ready_flags
    frame["proposed_review_rule_candidate"] = proposed_review_rule_candidates
    frame["candidate_reason"] = candidate_reasons
    frame["manual_cause_label_group"] = manual_cause_label_groups
    frame["cause_group_type"] = cause_group_types
    return frame.reset_index(drop=True)


def _build_by_cause_frame(validated_rows_frame: pd.DataFrame) -> pd.DataFrame:
    working = validated_rows_frame.copy()
    working["gross_profit_numeric"] = pd.to_numeric(working["actual_gross_profit"], errors="coerce").fillna(0.0)
    working["capital_left_numeric"] = pd.to_numeric(
        working["capital_left_in_unsold_store_allocation"], errors="coerce"
    ).fillna(0.0)
    working["candidate_gross_profit_component"] = (
        working["gross_profit_numeric"] * working["candidate_ready_flag"].astype(int)
    )

    by_cause_rows: list[dict[str, object]] = []
    for (manual_cause_label_group, cause_group_type), cause_frame in working.groupby(
        ["manual_cause_label_group", "cause_group_type"], dropna=False
    ):
        by_cause_rows.append(
            {
                "manual_cause_label_group": manual_cause_label_group,
                "cause_group_type": cause_group_type,
                "row_count": int(len(cause_frame.index)),
                "complete_rows": int(cause_frame["manual_review_status"].eq("COMPLETE").sum()),
                "incomplete_rows": int(cause_frame["manual_review_status"].eq("INCOMPLETE").sum()),
                "invalid_rows": int(cause_frame["manual_review_status"].eq("INVALID").sum()),
                "candidate_ready_rows": int(cause_frame["candidate_ready_flag"].astype(int).sum()),
                "gross_profit_total": round(float(cause_frame["gross_profit_numeric"].sum()), 2),
                "candidate_gross_profit_total": round(
                    float(cause_frame["candidate_gross_profit_component"].sum()), 2
                ),
                "capital_left_total": round(float(cause_frame["capital_left_numeric"].sum()), 2),
                "sample_skus": _sample_skus(cause_frame["sku_number"]),
            }
        )

    by_cause_frame = pd.DataFrame(by_cause_rows, columns=BY_CAUSE_COLUMNS)
    if by_cause_frame.empty:
        return pd.DataFrame(columns=BY_CAUSE_COLUMNS)
    return by_cause_frame.sort_values(
        by=["row_count", "candidate_ready_rows", "manual_cause_label_group"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_candidate_frame(validated_rows_frame: pd.DataFrame) -> pd.DataFrame:
    candidate_frame = validated_rows_frame.loc[
        validated_rows_frame["candidate_ready_flag"].astype(int).eq(1)
    ].copy()
    candidate_frame["manual_cause_label"] = candidate_frame["normalized_manual_cause_label"]
    candidate_frame["manual_confidence_score"] = candidate_frame[
        "normalized_manual_confidence_score"
    ]
    candidate_frame = candidate_frame.loc[:, CANDIDATE_OUTPUT_COLUMNS]
    return candidate_frame.reset_index(drop=True)


def _build_summary_frame(
    validated_rows_frame: pd.DataFrame,
    by_cause_frame: pd.DataFrame,
    candidate_frame: pd.DataFrame,
) -> pd.DataFrame:
    total_rows = int(len(validated_rows_frame.index))
    complete_rows = int(validated_rows_frame["manual_review_status"].eq("COMPLETE").sum())
    incomplete_rows = int(validated_rows_frame["manual_review_status"].eq("INCOMPLETE").sum())
    invalid_rows = int(validated_rows_frame["manual_review_status"].eq("INVALID").sum())
    candidate_ready_rows = int(candidate_frame.shape[0])
    repeatable_complete_rows = int(
        (
            validated_rows_frame["manual_review_status"].eq("COMPLETE")
            & validated_rows_frame["normalized_manual_cause_label"].isin(REPEATABLE_CAUSE_LABELS)
        ).sum()
    )
    one_off_complete_rows = int(
        (
            validated_rows_frame["manual_review_status"].eq("COMPLETE")
            & validated_rows_frame["normalized_manual_cause_label"].eq(ONE_OFF_CAUSE_LABEL)
        ).sum()
    )
    unknown_complete_rows = int(
        (
            validated_rows_frame["manual_review_status"].eq("COMPLETE")
            & validated_rows_frame["normalized_manual_cause_label"].eq(UNKNOWN_CAUSE_LABEL)
        ).sum()
    )
    candidate_gross_profit = round(
        float(pd.to_numeric(candidate_frame.get("actual_gross_profit", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()),
        2,
    )
    candidate_capital_left = round(
        float(
            pd.to_numeric(
                candidate_frame.get(
                    "capital_left_in_unsold_store_allocation", pd.Series(dtype=float)
                ),
                errors="coerce",
            ).fillna(0.0).sum()
        ),
        2,
    )

    rows = [
        _summary_row(
            "MANUAL_INSPECTION_INGEST",
            "INPUT_ROWS",
            total_rows,
            "rows",
            _format_int(total_rows),
            "Rows read from the completed no-prior-demand manual-inspection worksheet.",
        ),
        _summary_row(
            "MANUAL_INSPECTION_INGEST",
            "COMPLETE_ROWS",
            complete_rows,
            "rows",
            _format_int(complete_rows),
            "Rows with valid manual cause, confidence score, and next action.",
        ),
        _summary_row(
            "MANUAL_INSPECTION_INGEST",
            "INCOMPLETE_ROWS",
            incomplete_rows,
            "rows",
            _format_int(incomplete_rows),
            "Rows retained with blank required manual fields.",
        ),
        _summary_row(
            "MANUAL_INSPECTION_INGEST",
            "INVALID_ROWS",
            invalid_rows,
            "rows",
            _format_int(invalid_rows),
            "Rows retained but surfaced with validation issues.",
        ),
        _summary_row(
            "MANUAL_INSPECTION_INGEST",
            "CANDIDATE_READY_ROWS",
            candidate_ready_rows,
            "rows",
            _format_int(candidate_ready_rows),
            "Complete rows that qualified as shadow-only learning candidates.",
        ),
        _summary_row(
            "CAUSE_BREAKDOWN",
            "COMPLETE_REPEATABLE_CAUSE_ROWS",
            repeatable_complete_rows,
            "rows",
            _format_int(repeatable_complete_rows),
            "Complete rows tagged with repeatable manual causes.",
        ),
        _summary_row(
            "CAUSE_BREAKDOWN",
            "COMPLETE_ONE_OFF_DEMAND_ROWS",
            one_off_complete_rows,
            "rows",
            _format_int(one_off_complete_rows),
            "Complete rows tagged as one-off demand rather than a repeatable cause.",
        ),
        _summary_row(
            "CAUSE_BREAKDOWN",
            "COMPLETE_UNKNOWN_REVIEW_ROWS",
            unknown_complete_rows,
            "rows",
            _format_int(unknown_complete_rows),
            "Complete rows that still require human interpretation.",
        ),
        _summary_row(
            "CANDIDATE_FINANCIALS",
            "CANDIDATE_GROSS_PROFIT_REPRESENTED",
            candidate_gross_profit,
            "dollars",
            _format_money(candidate_gross_profit),
            "Gross profit represented by candidate-ready rows only.",
        ),
        _summary_row(
            "CANDIDATE_FINANCIALS",
            "CANDIDATE_CAPITAL_LEFT_REPRESENTED",
            candidate_capital_left,
            "dollars",
            _format_money(candidate_capital_left),
            "Capital left represented by candidate-ready rows only.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            0,
            "rows",
            "0",
            "This ingest layer does not change production ordering.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            0,
            "rows",
            "0",
            "This ingest layer does not change Stage 12.",
        ),
    ]

    for rank, row in enumerate(by_cause_frame.head(3).itertuples(index=False), start=1):
        rows.append(
            _summary_row(
                "TOP_MANUAL_CAUSE",
                f"RANK_{rank}",
                int(row.row_count),
                "rows",
                f"{row.manual_cause_label_group} ({_format_int(row.row_count)})",
                (
                    f"{row.cause_group_type}; complete={_format_int(row.complete_rows)}, "
                    f"candidate_ready={_format_int(row.candidate_ready_rows)}."
                ),
            )
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(
    validated_rows_frame: pd.DataFrame,
    by_cause_frame: pd.DataFrame,
    candidate_frame: pd.DataFrame,
) -> str:
    total_rows = len(validated_rows_frame.index)
    complete_rows = int(validated_rows_frame["manual_review_status"].eq("COMPLETE").sum())
    incomplete_rows = int(validated_rows_frame["manual_review_status"].eq("INCOMPLETE").sum())
    invalid_rows = int(validated_rows_frame["manual_review_status"].eq("INVALID").sum())
    candidate_ready_rows = int(candidate_frame.shape[0])
    repeatable_frame = by_cause_frame.loc[
        by_cause_frame["cause_group_type"].eq("REPEATABLE_CAUSE")
    ].copy()
    one_off_frame = by_cause_frame.loc[
        by_cause_frame["cause_group_type"].eq("ONE_OFF_DEMAND")
    ].copy()
    unknown_frame = by_cause_frame.loc[
        by_cause_frame["cause_group_type"].eq("UNKNOWN_REQUIRES_REVIEW")
    ].copy()

    repeatable_text = (
        ", ".join(
            f"{row.manual_cause_label_group} ({_format_int(row.complete_rows)})"
            for row in repeatable_frame.head(3).itertuples(index=False)
            if int(row.complete_rows) > 0
        )
        or "No completed repeatable manual causes yet."
    )
    one_off_text = (
        ", ".join(
            f"{row.manual_cause_label_group} ({_format_int(row.complete_rows)})"
            for row in one_off_frame.head(3).itertuples(index=False)
            if int(row.complete_rows) > 0
        )
        or "No completed one-off demand labels yet."
    )
    unknown_text = (
        ", ".join(
            f"{row.manual_cause_label_group} ({_format_int(row.complete_rows)})"
            for row in unknown_frame.head(3).itertuples(index=False)
            if int(row.complete_rows) > 0
        )
        or "No completed unknown-review labels yet."
    )
    candidate_gross_profit = round(
        float(pd.to_numeric(candidate_frame.get("actual_gross_profit", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()),
        2,
    )
    candidate_capital_left = round(
        float(
            pd.to_numeric(
                candidate_frame.get(
                    "capital_left_in_unsold_store_allocation", pd.Series(dtype=float)
                ),
                errors="coerce",
            ).fillna(0.0).sum()
        ),
        2,
    )

    lines = [
        "# No Prior Manual Inspection Ingest",
        "",
        "This is not an order file. It is a governed learning artifact built from the completed no-prior-demand manual-inspection worksheet.",
        "",
        "Production order changes = 0.",
        "Stage 12 changes = 0.",
        "",
        (
            f"The ingest read {_format_int(total_rows)} rows and classified {_format_int(complete_rows)} complete, "
            f"{_format_int(incomplete_rows)} incomplete, and {_format_int(invalid_rows)} invalid rows."
        ),
        (
            f"Candidate-ready rows = {_format_int(candidate_ready_rows)} and they represent "
            f"{_format_money(candidate_gross_profit)} gross profit with {_format_money(candidate_capital_left)} capital left."
        ),
        "",
        "Repeatable manual causes:",
        repeatable_text,
        "",
        "One-off demand labels:",
        one_off_text,
        "",
        "Unknown-review labels:",
        unknown_text,
        "",
        "Invalid rows are retained in the validated output with explicit validation_issue text; incomplete rows remain visible and are not dropped.",
        "Candidate rows, if any, are shadow-only learning candidates and must not change production ordering or Stage 12.",
        "Recommendation: keep any review-rule candidates shadow-only until repeated evidence appears across more promotions, and resolve incomplete or invalid rows before using the cause distribution for governance decisions.",
    ]
    return "\n".join(lines) + "\n"


def build_promotions_no_prior_manual_inspection_ingest(
    *,
    manual_inspection_rows_frame: pd.DataFrame,
    inspection_scope: str = FULL_NO_PRIOR_18,
) -> PromotionsNoPriorManualInspectionIngestResult:
    normalized_scope = _require_inspection_scope(inspection_scope)
    expected_scope_rows = INSPECTION_SCOPE_EXPECTED_ROWS[normalized_scope]
    actual_scope_rows = int(len(manual_inspection_rows_frame.index))
    partial_review_flag = INSPECTION_SCOPE_PARTIAL_FLAGS[normalized_scope]

    validated_rows_frame = _build_validated_rows_frame(manual_inspection_rows_frame)
    by_cause_frame = _build_by_cause_frame(validated_rows_frame)
    candidate_frame = _build_candidate_frame(validated_rows_frame)
    summary_frame = _build_summary_frame(validated_rows_frame, by_cause_frame, candidate_frame)

    validated_rows_frame = _with_scope_metadata(
        validated_rows_frame,
        inspection_scope=normalized_scope,
        expected_scope_rows=expected_scope_rows,
        actual_scope_rows=actual_scope_rows,
        partial_review_flag=partial_review_flag,
    )
    by_cause_frame = _with_scope_metadata(
        by_cause_frame,
        inspection_scope=normalized_scope,
        expected_scope_rows=expected_scope_rows,
        actual_scope_rows=actual_scope_rows,
        partial_review_flag=partial_review_flag,
    )
    candidate_frame = _with_scope_metadata(
        candidate_frame,
        inspection_scope=normalized_scope,
        expected_scope_rows=expected_scope_rows,
        actual_scope_rows=actual_scope_rows,
        partial_review_flag=partial_review_flag,
    )
    summary_frame = _with_scope_metadata(
        summary_frame,
        inspection_scope=normalized_scope,
        expected_scope_rows=expected_scope_rows,
        actual_scope_rows=actual_scope_rows,
        partial_review_flag=partial_review_flag,
    )

    memo_markdown = _build_memo(validated_rows_frame, by_cause_frame, candidate_frame)
    return PromotionsNoPriorManualInspectionIngestResult(
        validated_rows_frame=validated_rows_frame,
        summary_frame=summary_frame,
        by_cause_frame=by_cause_frame,
        candidate_frame=candidate_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_no_prior_manual_inspection_ingest(
    *,
    review_artifact_root: str | Path,
    worksheet_path: str | Path | None = None,
    inspection_scope: str = FULL_NO_PRIOR_18,
    output_root: str | Path | None = None,
) -> PromotionsNoPriorManualInspectionIngestArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)
    normalized_scope = _require_inspection_scope(inspection_scope)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsNoPriorManualInspectionIngestError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    rows_path = _resolve_rows_path(review_artifact_path, worksheet_path)
    if not rows_path.exists():
        raise PromotionsNoPriorManualInspectionIngestError(
            f"Manual inspection worksheet does not exist: {rows_path}"
        )
    rows_frame = _read_csv(rows_path)
    _validate_scope_row_count(
        inspection_scope=normalized_scope,
        actual_scope_rows=int(len(rows_frame.index)),
    )
    result = build_promotions_no_prior_manual_inspection_ingest(
        manual_inspection_rows_frame=rows_frame,
        inspection_scope=normalized_scope,
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else review_artifact_path / INSPECTION_SCOPE_OUTPUT_RELATIVE_PATHS[normalized_scope]
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    validated_rows_csv_path = destination_root / "no_prior_manual_inspection_validated_rows.csv"
    summary_csv_path = destination_root / "no_prior_manual_inspection_summary.csv"
    by_cause_csv_path = destination_root / "no_prior_manual_inspection_by_cause.csv"
    review_rule_candidates_csv_path = (
        destination_root / "no_prior_manual_review_rule_candidates.csv"
    )
    memo_md_path = destination_root / "no_prior_manual_inspection_memo.md"

    add_provenance_columns(result.validated_rows_frame.copy(), manifest).to_csv(
        validated_rows_csv_path, index=False
    )
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(
        summary_csv_path, index=False
    )
    add_provenance_columns(result.by_cause_frame.copy(), manifest).to_csv(
        by_cause_csv_path, index=False
    )
    add_provenance_columns(result.candidate_frame.copy(), manifest).to_csv(
        review_rule_candidates_csv_path, index=False
    )
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsNoPriorManualInspectionIngestArtifacts(
        validated_rows_csv_path=str(validated_rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        by_cause_csv_path=str(by_cause_csv_path),
        review_rule_candidates_csv_path=str(review_rule_candidates_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and ingest a completed no-prior-demand manual-inspection worksheet."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--worksheet-path")
    parser.add_argument(
        "--inspection-scope",
        choices=INSPECTION_SCOPE_CHOICES,
        default=FULL_NO_PRIOR_18,
    )
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_no_prior_manual_inspection_ingest(
        review_artifact_root=args.review_artifact_root,
        worksheet_path=args.worksheet_path,
        inspection_scope=args.inspection_scope,
        output_root=args.output_root,
    )
    print("no_prior_manual_inspection_validated_rows", artifacts.validated_rows_csv_path)
    print("no_prior_manual_inspection_summary", artifacts.summary_csv_path)
    print("no_prior_manual_inspection_by_cause", artifacts.by_cause_csv_path)
    print("no_prior_manual_review_rule_candidates", artifacts.review_rule_candidates_csv_path)
    print("no_prior_manual_inspection_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())