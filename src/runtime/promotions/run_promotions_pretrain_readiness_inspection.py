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


OUTPUT_FOLDER_NAME = "pretrain_readiness_inspection"
FORECAST_CORRELATION_THRESHOLD = 0.50

FULL_MANUAL_SCOPE = "FULL_NO_PRIOR_18"
BATCH1_MANUAL_SCOPE = "BATCH_1_FAST_HIGH_VALUE"
FULL_MANUAL_EXPECTED_ROWS = 18
BATCH1_MANUAL_EXPECTED_ROWS = 8
CANONICAL_MANUAL_SUMMARY_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/inspection_ingest/no_prior_manual_inspection_summary.csv"
)
CANONICAL_MANUAL_CANDIDATES_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/inspection_ingest/no_prior_manual_review_rule_candidates.csv"
)
BATCH1_MANUAL_SUMMARY_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/batch1_completion_helper/inspection_ingest/no_prior_manual_inspection_summary.csv"
)
BATCH1_MANUAL_CANDIDATES_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/batch1_completion_helper/inspection_ingest/no_prior_manual_review_rule_candidates.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    "model_vs_actual_summary.csv",
    "action_layer_recalibration_summary.csv",
    "report_contract_cleanup_summary.csv",
    "learning_scoreboard/promotion_learning_scoreboard_summary.csv",
    "review_overlay_packet/review_overlay_packet_summary.csv",
    "review_overlay_packet/operator_review_memo/operator_review_summary.csv",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "readiness_check",
    "status",
    "metric_value",
    "threshold",
    "blocking_flag",
    "reason",
    "recommended_next_action",
)

BLOCKERS_COLUMNS: tuple[str, ...] = (
    "blocker_rank",
    "readiness_check",
    "status",
    "metric_value",
    "threshold",
    "blocking_flag",
    "reason",
    "recommended_next_action",
)

RECOMMENDATIONS_COLUMNS: tuple[str, ...] = (
    "recommendation_rank",
    "recommendation_scope",
    "recommendation",
    "allowed_flag",
    "reason",
)

ACTION_LAYER_BLOCKING_LABELS: tuple[str, ...] = (
    "ACTION_TOO_CONSERVATIVE",
    "REVIEW_SHOULD_HAVE_TRIGGERED",
    "ACTION_TOO_AGGRESSIVE",
)


class PromotionsPretrainReadinessInspectionError(RuntimeError):
    """Raised when the pre-train readiness inspection cannot be built safely."""


@dataclass(frozen=True)
class PromotionsPretrainReadinessInspectionResult:
    summary_frame: pd.DataFrame
    blockers_frame: pd.DataFrame
    recommendations_frame: pd.DataFrame
    memo_markdown: str
    final_recommendation: str
    full_train_allowed_flag: bool
    shadow_only_dry_run_allowed_flag: bool


@dataclass(frozen=True)
class PromotionsPretrainReadinessInspectionArtifacts:
    summary_csv_path: str
    blockers_csv_path: str
    recommendations_csv_path: str
    memo_md_path: str


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty and not allow_empty:
        raise PromotionsPretrainReadinessInspectionError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsPretrainReadinessInspectionError(
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
        raise PromotionsPretrainReadinessInspectionError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsPretrainReadinessInspectionError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_float(value: float, *, decimals: int = 3) -> str:
    return f"{value:.{decimals}f}"


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _format_signed_int(value: float | int) -> str:
    rounded = int(round(float(value)))
    if rounded > 0:
        return f"+{rounded:,}"
    return f"{rounded:,}"


def _summary_row(
    readiness_check: str,
    status: str,
    metric_value: str,
    threshold: str,
    blocking_flag: int,
    reason: str,
    recommended_next_action: str,
) -> dict[str, object]:
    return {
        "readiness_check": readiness_check,
        "status": status,
        "metric_value": metric_value,
        "threshold": threshold,
        "blocking_flag": int(blocking_flag),
        "reason": reason,
        "recommended_next_action": recommended_next_action,
    }


def _get_single_row(frame: pd.DataFrame, *, frame_name: str) -> pd.Series:
    if frame.shape[0] != 1:
        raise PromotionsPretrainReadinessInspectionError(
            f"{frame_name} must contain exactly one row; found {frame.shape[0]}."
        )
    return frame.iloc[0]


def _get_metric_lookup(frame: pd.DataFrame, *, frame_name: str) -> dict[str, float]:
    _require_columns(frame, ("metric_name", "metric_value"), frame_name=frame_name)
    lookup: dict[str, float] = {}
    for row in frame.itertuples(index=False):
        metric_name = str(getattr(row, "metric_name"))
        metric_value = float(pd.to_numeric(getattr(row, "metric_value"), errors="raise"))
        lookup[metric_name] = metric_value
    return lookup


def _require_metric(lookup: dict[str, float], metric_name: str, *, frame_name: str) -> float:
    if metric_name not in lookup:
        raise PromotionsPretrainReadinessInspectionError(
            f"{frame_name} is missing required metric_name: {metric_name}"
        )
    return lookup[metric_name]


def _get_issue_count(report_contract_cleanup_summary_frame: pd.DataFrame, issue_type: str) -> float:
    _require_columns(
        report_contract_cleanup_summary_frame,
        ("issue_type", "issue_count"),
        frame_name="report_contract_cleanup_summary_frame",
    )
    matched = report_contract_cleanup_summary_frame.loc[
        report_contract_cleanup_summary_frame["issue_type"].astype(str).eq(issue_type)
    ]
    if matched.shape[0] != 1:
        raise PromotionsPretrainReadinessInspectionError(
            f"Expected exactly one cleanup issue row for {issue_type!r}; found {matched.shape[0]}."
        )
    return float(pd.to_numeric(matched.iloc[0]["issue_count"], errors="raise"))


def _get_action_layer_issue_count(
    action_layer_recalibration_summary_frame: pd.DataFrame,
    *,
    label_name: str,
) -> float:
    _require_columns(
        action_layer_recalibration_summary_frame,
        ("summary_kind", "label_name", "row_count"),
        frame_name="action_layer_recalibration_summary_frame",
    )
    matched = action_layer_recalibration_summary_frame.loc[
        action_layer_recalibration_summary_frame["summary_kind"].astype(str).eq("RULE_FLAG")
        & action_layer_recalibration_summary_frame["label_name"].astype(str).eq(label_name)
    ]
    if matched.empty:
        return 0.0
    return float(pd.to_numeric(matched.iloc[0]["row_count"], errors="raise"))


def _sum_numeric_column(frame: pd.DataFrame, column_name: str) -> float:
    if column_name not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column_name], errors="coerce").fillna(0.0).sum())


def _metric_or_default(
    lookup: dict[str, float],
    metric_name: str,
    *,
    default: float = 0.0,
) -> float:
    return float(lookup.get(metric_name, default))


def _detect_manual_scope(summary_frame: pd.DataFrame, *, default_scope: str) -> str:
    if "inspection_scope" not in summary_frame.columns:
        return default_scope
    scopes = [
        str(value).strip()
        for value in summary_frame["inspection_scope"].astype(str).tolist()
        if str(value).strip()
    ]
    return scopes[0] if scopes else default_scope


def _extract_scope_counts(
    summary_frame: pd.DataFrame,
    *,
    expected_rows_fallback: int,
    scope_default: str,
) -> tuple[str, float, float, float, float, float]:
    lookup = _get_metric_lookup(summary_frame, frame_name="manual_inspection_summary_frame")
    inspection_scope = _detect_manual_scope(summary_frame, default_scope=scope_default)
    complete_rows = _require_metric(lookup, "COMPLETE_ROWS", frame_name="manual_inspection_summary_frame")
    incomplete_rows = _require_metric(lookup, "INCOMPLETE_ROWS", frame_name="manual_inspection_summary_frame")
    invalid_rows = _require_metric(lookup, "INVALID_ROWS", frame_name="manual_inspection_summary_frame")
    candidate_ready_rows = _require_metric(
        lookup,
        "CANDIDATE_READY_ROWS",
        frame_name="manual_inspection_summary_frame",
    )
    expected_rows = _metric_or_default(
        lookup,
        "EXPECTED_SCOPE_ROWS",
        default=float(expected_rows_fallback),
    )
    actual_rows = _metric_or_default(
        lookup,
        "ACTUAL_SCOPE_ROWS",
        default=_metric_or_default(lookup, "INPUT_ROWS", default=float(expected_rows_fallback)),
    )
    return (
        inspection_scope,
        expected_rows,
        actual_rows,
        complete_rows,
        incomplete_rows,
        invalid_rows,
        candidate_ready_rows,
    )


def _build_summary_frame(
    *,
    model_vs_actual_summary_frame: pd.DataFrame,
    action_layer_recalibration_summary_frame: pd.DataFrame,
    report_contract_cleanup_summary_frame: pd.DataFrame,
    learning_scoreboard_summary_frame: pd.DataFrame,
    review_overlay_packet_summary_frame: pd.DataFrame,
    operator_review_summary_frame: pd.DataFrame,
    full_manual_inspection_summary_frame: pd.DataFrame,
    full_review_rule_candidates_frame: pd.DataFrame,
    batch1_manual_inspection_summary_frame: pd.DataFrame | None,
    batch1_review_rule_candidates_frame: pd.DataFrame | None,
) -> pd.DataFrame:
    _require_columns(
        model_vs_actual_summary_frame,
        ("forecast_correlation", "forecast_bias_units"),
        frame_name="model_vs_actual_summary_frame",
    )
    model_row = _get_single_row(model_vs_actual_summary_frame, frame_name="model_vs_actual_summary_frame")
    forecast_correlation = float(pd.to_numeric(model_row["forecast_correlation"], errors="raise"))
    forecast_bias_units = float(pd.to_numeric(model_row["forecast_bias_units"], errors="raise"))

    scoreboard_lookup = _get_metric_lookup(
        learning_scoreboard_summary_frame,
        frame_name="learning_scoreboard_summary_frame",
    )
    overlay_lookup = _get_metric_lookup(
        review_overlay_packet_summary_frame,
        frame_name="review_overlay_packet_summary_frame",
    )
    operator_lookup = _get_metric_lookup(
        operator_review_summary_frame,
        frame_name="operator_review_summary_frame",
    )
    (
        full_manual_scope,
        full_manual_rows_expected,
        full_manual_rows_actual,
        full_manual_complete_rows,
        full_manual_incomplete_rows,
        full_manual_invalid_rows,
        full_candidate_ready_rows_summary,
    ) = _extract_scope_counts(
        full_manual_inspection_summary_frame,
        expected_rows_fallback=FULL_MANUAL_EXPECTED_ROWS,
        scope_default=FULL_MANUAL_SCOPE,
    )

    batch1_summary_available = batch1_manual_inspection_summary_frame is not None
    if batch1_summary_available and batch1_manual_inspection_summary_frame is not None:
        (
            batch1_manual_scope,
            batch1_rows_expected,
            batch1_rows_actual,
            batch1_rows_complete,
            batch1_rows_incomplete,
            batch1_rows_invalid,
            batch1_candidate_ready_rows_summary,
        ) = _extract_scope_counts(
            batch1_manual_inspection_summary_frame,
            expected_rows_fallback=BATCH1_MANUAL_EXPECTED_ROWS,
            scope_default=BATCH1_MANUAL_SCOPE,
        )
    else:
        batch1_manual_scope = BATCH1_MANUAL_SCOPE
        batch1_rows_expected = float(BATCH1_MANUAL_EXPECTED_ROWS)
        batch1_rows_actual = 0.0
        batch1_rows_complete = 0.0
        batch1_rows_incomplete = 0.0
        batch1_rows_invalid = 0.0
        batch1_candidate_ready_rows_summary = 0.0

    canonical_looks_like_legacy_batch1 = (
        int(round(full_manual_rows_actual)) == BATCH1_MANUAL_EXPECTED_ROWS
        and int(round(full_manual_rows_expected)) != BATCH1_MANUAL_EXPECTED_ROWS
        and int(round(full_manual_complete_rows + full_manual_incomplete_rows + full_manual_invalid_rows))
        == BATCH1_MANUAL_EXPECTED_ROWS
    )
    if (
        full_manual_scope == BATCH1_MANUAL_SCOPE
        or canonical_looks_like_legacy_batch1
    ):
        if not batch1_summary_available:
            batch1_summary_available = True
        if batch1_review_rule_candidates_frame is None or batch1_review_rule_candidates_frame.empty:
            batch1_review_rule_candidates_frame = full_review_rule_candidates_frame.copy()
        batch1_rows_expected = float(BATCH1_MANUAL_EXPECTED_ROWS)
        batch1_rows_actual = full_manual_rows_actual
        batch1_rows_complete = full_manual_complete_rows
        batch1_rows_incomplete = full_manual_incomplete_rows
        batch1_rows_invalid = full_manual_invalid_rows
        batch1_candidate_ready_rows_summary = full_candidate_ready_rows_summary
        full_manual_rows_expected = float(FULL_MANUAL_EXPECTED_ROWS)
        full_manual_rows_actual = 0.0
        full_manual_complete_rows = 0.0
        full_manual_incomplete_rows = float(FULL_MANUAL_EXPECTED_ROWS)
        full_manual_invalid_rows = 0.0
        full_candidate_ready_rows_summary = 0.0
        full_review_rule_candidates_frame = pd.DataFrame(columns=full_review_rule_candidates_frame.columns)

    full_candidate_rows_file_count = float(len(full_review_rule_candidates_frame.index))
    full_candidate_gross_profit = _sum_numeric_column(full_review_rule_candidates_frame, "actual_gross_profit")
    batch1_review_rule_candidates_frame = (
        batch1_review_rule_candidates_frame
        if batch1_review_rule_candidates_frame is not None
        else pd.DataFrame(columns=["sku_number", "actual_gross_profit", "production_order_change_flag", "stage_12_change_flag"])
    )
    batch1_candidate_rows_file_count = float(len(batch1_review_rule_candidates_frame.index))
    batch1_candidate_gross_profit = _sum_numeric_column(batch1_review_rule_candidates_frame, "actual_gross_profit")

    partial_manual_review_flag = int(
        int(round(batch1_rows_complete)) > 0 and int(round(full_manual_complete_rows)) < int(round(full_manual_rows_expected))
    )

    unresolved_action_layer_rows = sum(
        _get_action_layer_issue_count(
            action_layer_recalibration_summary_frame,
            label_name=label_name,
        )
        for label_name in ACTION_LAYER_BLOCKING_LABELS
    )

    cleanup_issues_remaining = _get_issue_count(
        report_contract_cleanup_summary_frame,
        "TOTAL_REMAINING_CLEANUP_ISSUES",
    )
    cleanup_issues_reduced = _require_metric(
        scoreboard_lookup,
        "CLEANUP_ISSUES_REDUCED",
        frame_name="learning_scoreboard_summary_frame",
    )
    initial_cleanup_issue_count = cleanup_issues_remaining + cleanup_issues_reduced
    multiple_action_conflicts_remaining = _require_metric(
        scoreboard_lookup,
        "MULTIPLE_ACTION_CONFLICTS_REMAINING",
        frame_name="learning_scoreboard_summary_frame",
    )
    shadow_fields_visible_remaining = _require_metric(
        scoreboard_lookup,
        "SHADOW_FIELDS_VISIBLE_REMAINING",
        frame_name="learning_scoreboard_summary_frame",
    )

    overlay_total_rows = _require_metric(
        overlay_lookup,
        "TOTAL_REVIEW_ROWS",
        frame_name="review_overlay_packet_summary_frame",
    )
    overlay_no_prior_rows = _require_metric(
        overlay_lookup,
        "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
        frame_name="review_overlay_packet_summary_frame",
    )
    overlay_production_changes = _require_metric(
        overlay_lookup,
        "PRODUCTION_ORDER_CHANGES",
        frame_name="review_overlay_packet_summary_frame",
    )
    overlay_stage12_changes = _require_metric(
        overlay_lookup,
        "STAGE12_CHANGES",
        frame_name="review_overlay_packet_summary_frame",
    )

    operator_total_rows = _require_metric(
        operator_lookup,
        "TOTAL_REVIEW_ROWS",
        frame_name="operator_review_summary_frame",
    )
    priority_one_rows = _require_metric(
        operator_lookup,
        "PRIORITY_ONE_ROWS",
        frame_name="operator_review_summary_frame",
    )
    operator_production_changes = _require_metric(
        operator_lookup,
        "PRODUCTION_ORDER_CHANGES",
        frame_name="operator_review_summary_frame",
    )
    operator_stage12_changes = _require_metric(
        operator_lookup,
        "STAGE12_CHANGES",
        frame_name="operator_review_summary_frame",
    )

    scoreboard_production_changes = _require_metric(
        scoreboard_lookup,
        "PRODUCTION_ORDER_CHANGE_COUNT",
        frame_name="learning_scoreboard_summary_frame",
    )
    scoreboard_stage12_changes = _require_metric(
        scoreboard_lookup,
        "STAGE12_CHANGE_COUNT",
        frame_name="learning_scoreboard_summary_frame",
    )
    full_manual_lookup = _get_metric_lookup(
        full_manual_inspection_summary_frame,
        frame_name="full_manual_inspection_summary_frame",
    )
    manual_production_changes = _metric_or_default(
        full_manual_lookup,
        "PRODUCTION_ORDER_CHANGES",
        default=0.0,
    )
    manual_stage12_changes = _metric_or_default(
        full_manual_lookup,
        "STAGE12_CHANGES",
        default=0.0,
    )
    batch1_manual_production_changes = 0.0
    batch1_manual_stage12_changes = 0.0
    if batch1_summary_available and batch1_manual_inspection_summary_frame is not None:
        batch1_manual_lookup = _get_metric_lookup(
            batch1_manual_inspection_summary_frame,
            frame_name="batch1_manual_inspection_summary_frame",
        )
        batch1_manual_production_changes = _metric_or_default(
            batch1_manual_lookup,
            "PRODUCTION_ORDER_CHANGES",
            default=0.0,
        )
        batch1_manual_stage12_changes = _metric_or_default(
            batch1_manual_lookup,
            "STAGE12_CHANGES",
            default=0.0,
        )
    candidate_production_changes = _sum_numeric_column(full_review_rule_candidates_frame, "production_order_change_flag")
    candidate_stage12_changes = _sum_numeric_column(full_review_rule_candidates_frame, "stage_12_change_flag")
    batch1_candidate_production_changes = _sum_numeric_column(
        batch1_review_rule_candidates_frame,
        "production_order_change_flag",
    )
    batch1_candidate_stage12_changes = _sum_numeric_column(
        batch1_review_rule_candidates_frame,
        "stage_12_change_flag",
    )

    rows: list[dict[str, object]] = []

    if full_manual_invalid_rows > 0:
        manual_status = "BLOCK"
        manual_reason = (
            f"{_format_int(full_manual_invalid_rows)} full-scope manual rows are invalid and must be corrected before any label-driven learning rerun."
        )
    elif full_manual_complete_rows == 0 and batch1_rows_complete > 0:
        manual_status = "WARN"
        manual_reason = "Batch 1 partial review completed; full 18-row manual review remains incomplete."
    elif full_manual_complete_rows == 0:
        manual_status = "BLOCK"
        manual_reason = (
            f"No full-scope manual no-prior rows are complete yet; {_format_int(full_manual_incomplete_rows)} rows still need governed human labels."
        )
    elif full_manual_complete_rows < full_manual_rows_expected:
        manual_status = "WARN"
        manual_reason = (
            f"{_format_int(full_manual_complete_rows)} of {_format_int(full_manual_rows_expected)} full-scope manual rows are complete, so evidence remains partial."
        )
    else:
        manual_status = "PASS"
        manual_reason = "All full-scope manual no-prior rows are complete and valid."
    rows.append(
        _summary_row(
            "manual_no_prior_labels_complete",
            manual_status,
            (
                f"full={_format_int(full_manual_complete_rows)}/{_format_int(full_manual_rows_expected)} complete; "
                f"batch1={_format_int(batch1_rows_complete)}/{_format_int(batch1_rows_expected)} complete"
            ),
            "> 0 complete rows required; all 18 complete preferred",
            int(manual_status == "BLOCK"),
            manual_reason,
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
        )
    )

    if int(round(full_candidate_ready_rows_summary)) != int(round(full_candidate_rows_file_count)):
        candidate_status = "BLOCK"
        candidate_reason = (
            f"Full-scope candidate-ready summary count ({_format_int(full_candidate_ready_rows_summary)}) does not match the candidate file row count ({_format_int(full_candidate_rows_file_count)})."
        )
    elif full_candidate_rows_file_count > 0:
        candidate_status = "PASS"
        candidate_reason = "Full-scope candidate-ready shadow-only learning rows exist."
    elif batch1_candidate_rows_file_count > 0 or batch1_candidate_ready_rows_summary > 0:
        candidate_status = "PASS"
        if int(round(batch1_candidate_ready_rows_summary)) != int(round(batch1_candidate_rows_file_count)):
            candidate_reason = (
                "Batch 1 candidate-ready shadow-only learning rows exist for data inspection, but the summary/file counts differ and should be reconciled before broader governance use."
            )
        else:
            candidate_reason = "Batch 1 candidate-ready shadow-only learning rows exist for data inspection, but full-scope candidates are not complete yet."
    else:
        candidate_status = "BLOCK"
        candidate_reason = "No candidate-ready rows exist yet, so there is no governed learning slice to carry into a rerun."
    rows.append(
        _summary_row(
            "candidate_rows_available",
            candidate_status,
            (
                f"full={_format_int(full_candidate_rows_file_count)} rows / {_format_money(full_candidate_gross_profit)}; "
                f"batch1={_format_int(batch1_candidate_rows_file_count)} rows / {_format_money(batch1_candidate_gross_profit)}"
            ),
            ">= 1 candidate-ready row",
            int(candidate_status == "BLOCK"),
            candidate_reason,
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
        )
    )

    if forecast_correlation < FORECAST_CORRELATION_THRESHOLD:
        forecast_status = "BLOCK"
        forecast_reason = (
            f"Forecast correlation {_format_float(forecast_correlation)} is below the {FORECAST_CORRELATION_THRESHOLD:.2f} floor and bias remains {_format_signed_int(forecast_bias_units)} units."
        )
    else:
        forecast_status = "PASS"
        forecast_reason = "Forecast-head reliability meets the minimum full-train floor."
    rows.append(
        _summary_row(
            "forecast_head_reliability",
            forecast_status,
            f"correlation={_format_float(forecast_correlation)}; bias={_format_signed_int(forecast_bias_units)} units",
            f"correlation >= {FORECAST_CORRELATION_THRESHOLD:.2f}",
            int(forecast_status == "BLOCK"),
            forecast_reason,
            "RUN_SHADOW_ONLY_DATA_INSPECTION",
        )
    )

    if unresolved_action_layer_rows > 0:
        action_layer_status = "BLOCK"
        action_layer_reason = (
            f"Action-layer calibration is unresolved with {_format_int(unresolved_action_layer_rows)} rule-flag rows still open."
        )
    else:
        action_layer_status = "PASS"
        action_layer_reason = "Action-layer calibration blockers are resolved."
    rows.append(
        _summary_row(
            "action_layer_calibration_ready",
            action_layer_status,
            f"{_format_int(unresolved_action_layer_rows)} unresolved action-layer rule-flag rows",
            "0 unresolved rule-flag rows",
            int(action_layer_status == "BLOCK"),
            action_layer_reason,
            "RUN_SHADOW_ONLY_DATA_INSPECTION",
        )
    )

    if multiple_action_conflicts_remaining > 0 or shadow_fields_visible_remaining > 0:
        cleanup_status = "BLOCK"
        cleanup_blocking_flag = 1
        cleanup_reason = (
            f"Visible-contract cleanup still has structural conflicts: multiple-action={_format_int(multiple_action_conflicts_remaining)}, shadow-fields-visible={_format_int(shadow_fields_visible_remaining)}."
        )
    elif cleanup_issues_remaining > 0:
        cleanup_status = "WARN"
        cleanup_blocking_flag = 0
        cleanup_reason = (
            f"Cleanup improved from {_format_int(initial_cleanup_issue_count)} to {_format_int(cleanup_issues_remaining)} residual issues, but a review-only backlog remains."
        )
    else:
        cleanup_status = "PASS"
        cleanup_blocking_flag = 0
        cleanup_reason = "No residual report-contract cleanup issues remain."
    rows.append(
        _summary_row(
            "report_contract_clean_enough",
            cleanup_status,
            f"{_format_int(initial_cleanup_issue_count)} -> {_format_int(cleanup_issues_remaining)} residual issues",
            "0 structural conflicts required; residual backlog should continue falling",
            cleanup_blocking_flag,
            cleanup_reason,
            "RUN_END_TO_END_DRY_RUN_ONLY",
        )
    )

    if overlay_total_rows <= 0 or operator_total_rows <= 0:
        overlay_status = "BLOCK"
        overlay_reason = "Review-overlay packet and operator review memo must both contain rows before readiness can be assessed."
    elif int(round(overlay_total_rows)) != int(round(operator_total_rows)):
        overlay_status = "BLOCK"
        overlay_reason = (
            f"Review-overlay packet rows ({_format_int(overlay_total_rows)}) do not match operator review memo rows ({_format_int(operator_total_rows)})."
        )
    elif int(round(overlay_no_prior_rows)) != int(round(priority_one_rows)):
        overlay_status = "BLOCK"
        overlay_reason = (
            f"No-prior overlay rows ({_format_int(overlay_no_prior_rows)}) do not match operator priority-one rows ({_format_int(priority_one_rows)})."
        )
    elif partial_manual_review_flag:
        overlay_status = "WARN"
        overlay_reason = "Batch 1 partial review completed; full 18-row manual review remains incomplete."
    elif int(round(priority_one_rows)) != int(round(full_manual_rows_actual)):
        if partial_manual_review_flag:
            overlay_status = "WARN"
            overlay_reason = "Batch 1 partial review completed; full 18-row manual review remains incomplete."
        else:
            overlay_status = "BLOCK"
            overlay_reason = (
                f"Operator priority-one rows ({_format_int(priority_one_rows)}) do not match full manual inspection input rows ({_format_int(full_manual_rows_actual)})."
            )
    elif int(round(full_manual_rows_actual)) != int(round(full_manual_rows_expected)):
        overlay_status = "WARN"
        overlay_reason = (
            f"Full manual inspection rows currently cover {_format_int(full_manual_rows_actual)} of {_format_int(full_manual_rows_expected)} expected rows."
        )
    elif overlay_production_changes != 0 or overlay_stage12_changes != 0 or operator_production_changes != 0 or operator_stage12_changes != 0:
        overlay_status = "BLOCK"
        overlay_reason = "Review-overlay artifacts attempted to carry production-order or Stage 12 changes."
    else:
        overlay_status = "PASS"
        overlay_reason = "Review-overlay packet, operator memo, and manual no-prior seam are aligned for diagnostics."
    rows.append(
        _summary_row(
            "review_overlay_packet_ready",
            overlay_status,
            (
                f"overlay={_format_int(overlay_total_rows)}; operator_memo={_format_int(operator_total_rows)}; "
                f"priority_one={_format_int(priority_one_rows)}; full_manual_rows={_format_int(full_manual_rows_actual)}; batch1_rows={_format_int(batch1_rows_actual)}"
            ),
            "Aligned overlay, operator memo, and manual-input counts",
            int(overlay_status == "BLOCK"),
            overlay_reason,
            "RUN_END_TO_END_DRY_RUN_ONLY",
        )
    )

    production_guardrail_total = (
        scoreboard_production_changes
        + overlay_production_changes
        + operator_production_changes
        + manual_production_changes
        + candidate_production_changes
        + batch1_manual_production_changes
        + batch1_candidate_production_changes
    )
    if production_guardrail_total != 0:
        production_status = "BLOCK"
        production_reason = (
            f"Production-order changes are nonzero across the diagnostics chain: {_format_int(production_guardrail_total)} total."
        )
    else:
        production_status = "PASS"
        production_reason = "Production-order guardrails remain unchanged at 0 across all governed diagnostic artifacts."
    rows.append(
        _summary_row(
            "production_order_guardrails_unchanged",
            production_status,
            _format_int(production_guardrail_total),
            "0 production-order changes",
            int(production_status == "BLOCK"),
            production_reason,
            "DO_NOT_RUN_FULL_TRAIN_YET",
        )
    )

    stage12_guardrail_total = (
        scoreboard_stage12_changes
        + overlay_stage12_changes
        + operator_stage12_changes
        + manual_stage12_changes
        + candidate_stage12_changes
        + batch1_manual_stage12_changes
        + batch1_candidate_stage12_changes
    )
    if stage12_guardrail_total != 0:
        stage12_status = "BLOCK"
        stage12_reason = (
            f"Stage 12 changes are nonzero across the diagnostics chain: {_format_int(stage12_guardrail_total)} total."
        )
    else:
        stage12_status = "PASS"
        stage12_reason = "Stage 12 guardrails remain unchanged at 0 across all governed diagnostic artifacts."
    rows.append(
        _summary_row(
            "stage_12_unchanged",
            stage12_status,
            _format_int(stage12_guardrail_total),
            "0 Stage 12 changes",
            int(stage12_status == "BLOCK"),
            stage12_reason,
            "DO_NOT_RUN_FULL_TRAIN_YET",
        )
    )

    rows.append(
        _summary_row(
            "full_manual_rows_expected",
            "INFO",
            _format_int(full_manual_rows_expected),
            str(FULL_MANUAL_EXPECTED_ROWS),
            0,
            "Expected full-scope manual rows for the governed 18-row worksheet.",
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
        )
    )
    rows.append(
        _summary_row(
            "full_manual_rows_complete",
            "INFO",
            _format_int(full_manual_complete_rows),
            f"<= {_format_int(full_manual_rows_expected)}",
            0,
            "Completed rows in the canonical full manual scope.",
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
        )
    )
    rows.append(
        _summary_row(
            "batch1_rows_expected",
            "INFO",
            _format_int(batch1_rows_expected),
            str(BATCH1_MANUAL_EXPECTED_ROWS),
            0,
            "Expected rows in the Batch 1 partial review slice.",
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
        )
    )
    rows.append(
        _summary_row(
            "batch1_rows_complete",
            "INFO",
            _format_int(batch1_rows_complete),
            f"<= {_format_int(batch1_rows_expected)}",
            0,
            "Completed rows in the Batch 1 partial review slice.",
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
        )
    )
    rows.append(
        _summary_row(
            "batch1_candidate_ready_rows",
            "INFO",
            _format_int(batch1_candidate_rows_file_count),
            ">= 0",
            0,
            "Candidate-ready rows available from the Batch 1 partial review slice.",
            "RUN_SHADOW_ONLY_DATA_INSPECTION",
        )
    )
    rows.append(
        _summary_row(
            "partial_manual_review_flag",
            "INFO",
            _format_int(partial_manual_review_flag),
            "1 means Batch 1 is ahead of the full 18-row scope",
            0,
            "Indicates whether a partial manual review slice exists without a matching full-scope completion.",
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
        )
    )

    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_blockers_frame(summary_frame: pd.DataFrame) -> pd.DataFrame:
    blockers_frame = summary_frame.loc[summary_frame["blocking_flag"].astype(int).eq(1)].copy()
    blockers_frame.insert(0, "blocker_rank", range(1, len(blockers_frame.index) + 1))
    return blockers_frame.loc[:, BLOCKERS_COLUMNS].reset_index(drop=True)


def _build_recommendations_frame(
    summary_frame: pd.DataFrame,
    *,
    full_train_allowed_flag: bool,
    shadow_only_dry_run_allowed_flag: bool,
) -> tuple[pd.DataFrame, str]:
    rows: list[dict[str, object]] = []

    rows.append(
        {
            "recommendation_rank": 1,
            "recommendation_scope": "FULL_TRAIN",
            "recommendation": "RUN_FULL_TRAIN_ONLY_AFTER_LABELS" if full_train_allowed_flag else "DO_NOT_RUN_FULL_TRAIN_YET",
            "allowed_flag": int(full_train_allowed_flag),
            "reason": (
                "Full train can only be reconsidered after governed labels and repeated evidence exist across more than one promotion."
                if full_train_allowed_flag
                else "Full train is blocked by the current readiness blockers and should not be started now."
            ),
        }
    )
    rows.append(
        {
            "recommendation_rank": 2,
            "recommendation_scope": "NEXT_HIGH_VALUE_ACTION",
            "recommendation": "COMPLETE_MANUAL_WORKSHEET_FIRST",
            "allowed_flag": 1,
            "reason": "Finish the no-prior manual worksheet so governed labels can create or rule out shadow-only learning candidates.",
        }
    )
    rows.append(
        {
            "recommendation_rank": 3,
            "recommendation_scope": "DATA_INSPECTION",
            "recommendation": "RUN_SHADOW_ONLY_DATA_INSPECTION",
            "allowed_flag": 1,
            "reason": "Keep the next pass diagnostic-only while forecast reliability and action-layer calibration remain unresolved.",
        }
    )
    rows.append(
        {
            "recommendation_rank": 4,
            "recommendation_scope": "SHADOW_ONLY_DRY_RUN",
            "recommendation": "RUN_END_TO_END_DRY_RUN_ONLY",
            "allowed_flag": int(shadow_only_dry_run_allowed_flag),
            "reason": (
                "A shadow-only end-to-end dry run is allowed because review artifacts are aligned and production/Stage 12 guardrails remain unchanged."
                if shadow_only_dry_run_allowed_flag
                else "A shadow-only dry run is not allowed until the review artifacts and guardrails are stable."
            ),
        }
    )

    recommendations_frame = pd.DataFrame(rows, columns=RECOMMENDATIONS_COLUMNS)
    final_recommendation = str(recommendations_frame.iloc[0]["recommendation"])
    return recommendations_frame, final_recommendation


def _build_memo(
    *,
    summary_frame: pd.DataFrame,
    final_recommendation: str,
    full_train_allowed_flag: bool,
    shadow_only_dry_run_allowed_flag: bool,
) -> str:
    blocking_checks = summary_frame.loc[
        summary_frame["blocking_flag"].astype(int).eq(1), "readiness_check"
    ].astype(str).tolist()
    warning_checks = summary_frame.loc[
        summary_frame["status"].astype(str).eq("WARN"), "readiness_check"
    ].astype(str).tolist()

    manual_reason = str(
        summary_frame.loc[
            summary_frame["readiness_check"].astype(str).eq("manual_no_prior_labels_complete"), "reason"
        ].iloc[0]
    )
    candidate_reason = str(
        summary_frame.loc[
            summary_frame["readiness_check"].astype(str).eq("candidate_rows_available"), "reason"
        ].iloc[0]
    )
    forecast_reason = str(
        summary_frame.loc[
            summary_frame["readiness_check"].astype(str).eq("forecast_head_reliability"), "reason"
        ].iloc[0]
    )
    action_layer_reason = str(
        summary_frame.loc[
            summary_frame["readiness_check"].astype(str).eq("action_layer_calibration_ready"), "reason"
        ].iloc[0]
    )

    lines = [
        "# Pretrain Readiness Inspection",
        "",
        "This is a diagnostic gate only. No training was started.",
        "",
        f"Run full train now: {'YES' if full_train_allowed_flag else 'NO'}.",
        f"Run shadow-only dry run now: {'YES' if shadow_only_dry_run_allowed_flag else 'NO'}.",
        "Production order changes = 0.",
        "Stage 12 changes = 0.",
        "",
        f"Final recommendation: {final_recommendation}.",
        "",
        "Why full train is blocked:",
        f"- {manual_reason}",
        f"- {candidate_reason}",
        f"- {forecast_reason}",
        f"- {action_layer_reason}",
        "",
        "Full train:",
        (
            "Do not run full train now. The gate remains blocked until manual labels exist, candidate rows exist, and the forecast/action seams improve."
            if not full_train_allowed_flag
            else "Only reconsider full train after labels and repeated evidence exist across more than one promotion."
        ),
        "",
        "Shadow-only dry run:",
        (
            "A shadow-only end-to-end dry run is allowed for diagnostics only."
            if shadow_only_dry_run_allowed_flag
            else "A shadow-only dry run is not allowed until the diagnostics chain is stable."
        ),
        "",
        "Data inspection:",
        "Keep the next pass diagnostic-only while finishing manual labels and resolving forecast and action-layer blockers.",
        "",
        f"Blocking checks: {', '.join(blocking_checks) if blocking_checks else 'none'}.",
        f"Warning checks: {', '.join(warning_checks) if warning_checks else 'none'}.",
        "",
        "Next highest-value action: COMPLETE_MANUAL_WORKSHEET_FIRST.",
    ]
    return "\n".join(lines) + "\n"


def build_promotions_pretrain_readiness_inspection(
    *,
    model_vs_actual_summary_frame: pd.DataFrame,
    action_layer_recalibration_summary_frame: pd.DataFrame,
    report_contract_cleanup_summary_frame: pd.DataFrame,
    learning_scoreboard_summary_frame: pd.DataFrame,
    review_overlay_packet_summary_frame: pd.DataFrame,
    operator_review_summary_frame: pd.DataFrame,
    full_manual_inspection_summary_frame: pd.DataFrame,
    full_review_rule_candidates_frame: pd.DataFrame,
    batch1_manual_inspection_summary_frame: pd.DataFrame | None = None,
    batch1_review_rule_candidates_frame: pd.DataFrame | None = None,
) -> PromotionsPretrainReadinessInspectionResult:
    summary_frame = _build_summary_frame(
        model_vs_actual_summary_frame=model_vs_actual_summary_frame,
        action_layer_recalibration_summary_frame=action_layer_recalibration_summary_frame,
        report_contract_cleanup_summary_frame=report_contract_cleanup_summary_frame,
        learning_scoreboard_summary_frame=learning_scoreboard_summary_frame,
        review_overlay_packet_summary_frame=review_overlay_packet_summary_frame,
        operator_review_summary_frame=operator_review_summary_frame,
        full_manual_inspection_summary_frame=full_manual_inspection_summary_frame,
        full_review_rule_candidates_frame=full_review_rule_candidates_frame,
        batch1_manual_inspection_summary_frame=batch1_manual_inspection_summary_frame,
        batch1_review_rule_candidates_frame=batch1_review_rule_candidates_frame,
    )
    blockers_frame = _build_blockers_frame(summary_frame)

    full_train_allowed_flag = blockers_frame.empty and bool(
        str(
            summary_frame.loc[
                summary_frame["readiness_check"].astype(str).eq("manual_no_prior_labels_complete"),
                "status",
            ].iloc[0]
        )
        == "PASS"
    )
    production_guardrails_pass = bool(
        str(
            summary_frame.loc[
                summary_frame["readiness_check"].astype(str).eq("production_order_guardrails_unchanged"),
                "status",
            ].iloc[0]
        )
        == "PASS"
    )
    stage12_guardrails_pass = bool(
        str(
            summary_frame.loc[
                summary_frame["readiness_check"].astype(str).eq("stage_12_unchanged"),
                "status",
            ].iloc[0]
        )
        == "PASS"
    )
    overlay_status = str(
        str(
            summary_frame.loc[
                summary_frame["readiness_check"].astype(str).eq("review_overlay_packet_ready"),
                "status",
            ].iloc[0]
        )
    )
    overlay_ready = overlay_status == "PASS"
    shadow_only_dry_run_allowed_flag = (
        production_guardrails_pass
        and stage12_guardrails_pass
        and overlay_ready
        and bool(
            str(
                summary_frame.loc[
                    summary_frame["readiness_check"].astype(str).eq("candidate_rows_available"),
                    "status",
                ].iloc[0]
            )
            == "PASS"
        )
    )

    recommendations_frame, final_recommendation = _build_recommendations_frame(
        summary_frame,
        full_train_allowed_flag=full_train_allowed_flag,
        shadow_only_dry_run_allowed_flag=shadow_only_dry_run_allowed_flag,
    )
    memo_markdown = _build_memo(
        summary_frame=summary_frame,
        final_recommendation=final_recommendation,
        full_train_allowed_flag=full_train_allowed_flag,
        shadow_only_dry_run_allowed_flag=shadow_only_dry_run_allowed_flag,
    )

    return PromotionsPretrainReadinessInspectionResult(
        summary_frame=summary_frame,
        blockers_frame=blockers_frame,
        recommendations_frame=recommendations_frame,
        memo_markdown=memo_markdown,
        final_recommendation=final_recommendation,
        full_train_allowed_flag=full_train_allowed_flag,
        shadow_only_dry_run_allowed_flag=shadow_only_dry_run_allowed_flag,
    )


def write_promotions_pretrain_readiness_inspection(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsPretrainReadinessInspectionArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsPretrainReadinessInspectionError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_pretrain_readiness_inspection(
        model_vs_actual_summary_frame=_read_csv(review_artifact_path / "model_vs_actual_summary.csv"),
        action_layer_recalibration_summary_frame=_read_csv(
            review_artifact_path / "action_layer_recalibration_summary.csv"
        ),
        report_contract_cleanup_summary_frame=_read_csv(
            review_artifact_path / "report_contract_cleanup_summary.csv"
        ),
        learning_scoreboard_summary_frame=_read_csv(
            review_artifact_path / "learning_scoreboard" / "promotion_learning_scoreboard_summary.csv"
        ),
        review_overlay_packet_summary_frame=_read_csv(
            review_artifact_path / "review_overlay_packet" / "review_overlay_packet_summary.csv"
        ),
        operator_review_summary_frame=_read_csv(
            review_artifact_path
            / "review_overlay_packet"
            / "operator_review_memo"
            / "operator_review_summary.csv"
        ),
        full_manual_inspection_summary_frame=_read_csv(
            review_artifact_path / CANONICAL_MANUAL_SUMMARY_RELATIVE_PATH
        ),
        full_review_rule_candidates_frame=_read_csv(
            review_artifact_path / CANONICAL_MANUAL_CANDIDATES_RELATIVE_PATH,
            allow_empty=True,
        ),
        batch1_manual_inspection_summary_frame=(
            _read_csv(review_artifact_path / BATCH1_MANUAL_SUMMARY_RELATIVE_PATH)
            if (review_artifact_path / BATCH1_MANUAL_SUMMARY_RELATIVE_PATH).exists()
            else None
        ),
        batch1_review_rule_candidates_frame=(
            _read_csv(review_artifact_path / BATCH1_MANUAL_CANDIDATES_RELATIVE_PATH, allow_empty=True)
            if (review_artifact_path / BATCH1_MANUAL_CANDIDATES_RELATIVE_PATH).exists()
            else None
        ),
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    summary_csv_path = destination_root / "pretrain_readiness_summary.csv"
    blockers_csv_path = destination_root / "pretrain_readiness_blockers.csv"
    recommendations_csv_path = destination_root / "pretrain_readiness_recommendations.csv"
    memo_md_path = destination_root / "pretrain_readiness_memo.md"

    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    add_provenance_columns(result.blockers_frame.copy(), manifest).to_csv(blockers_csv_path, index=False)
    add_provenance_columns(result.recommendations_frame.copy(), manifest).to_csv(
        recommendations_csv_path, index=False
    )
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsPretrainReadinessInspectionArtifacts(
        summary_csv_path=str(summary_csv_path),
        blockers_csv_path=str(blockers_csv_path),
        recommendations_csv_path=str(recommendations_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed pre-train readiness inspection gate without starting training."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_pretrain_readiness_inspection(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("pretrain_readiness_summary", artifacts.summary_csv_path)
    print("pretrain_readiness_blockers", artifacts.blockers_csv_path)
    print("pretrain_readiness_recommendations", artifacts.recommendations_csv_path)
    print("pretrain_readiness_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())