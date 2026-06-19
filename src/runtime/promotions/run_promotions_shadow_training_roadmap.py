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


OUTPUT_FOLDER_NAME = "shadow_training_roadmap"
CLEANUP_ISSUE_BASELINE = 777

TRAINING_READINESS_CURRENT_SCORE = 5.2
TRAINING_READINESS_TARGET_SCORE = 9.0
AUTO_ORDERING_CURRENT_SCORE = 5.0
AUTO_ORDERING_TARGET_SCORE = 9.0
OPERATOR_REVIEW_CURRENT_SCORE = 9.2
OPERATOR_REVIEW_TARGET_SCORE = 9.2
GOVERNANCE_CURRENT_SCORE = 9.5
GOVERNANCE_TARGET_SCORE = 9.5

TRAINING_READINESS_EXPECTED_AFTER_NEXT_ACTION = 6.2
AUTO_ORDERING_EXPECTED_AFTER_NEXT_ACTION = 5.2
OPERATOR_REVIEW_EXPECTED_AFTER_NEXT_ACTION = 9.2
GOVERNANCE_EXPECTED_AFTER_NEXT_ACTION = 9.5

ROADMAP_STEPS: tuple[str, ...] = (
    "COMPLETE_MANUAL_NO_PRIOR_LABELS",
    "INGEST_MANUAL_LABELS",
    "GENERATE_SHADOW_REVIEW_RULE_CANDIDATES",
    "RUN_SHADOW_ONLY_DATA_INSPECTION",
    "RUN_SHADOW_ONLY_DRY_TRAIN",
    "RUN_ACTION_LAYER_SHADOW_CALIBRATION",
    "COMPARE_SHADOW_VS_BASELINE",
    "REPEAT_ACROSS_MULTIPLE_PROMOTIONS",
    "ONLY_THEN_CONSIDER_LIMITED_PRODUCTION_PILOT",
)

ACTION_LAYER_BLOCKING_LABELS: tuple[str, ...] = (
    "ACTION_TOO_CONSERVATIVE",
    "REVIEW_SHOULD_HAVE_TRIGGERED",
    "ACTION_TOO_AGGRESSIVE",
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    "pretrain_readiness_inspection/pretrain_readiness_summary.csv",
    "pretrain_readiness_inspection/pretrain_readiness_blockers.csv",
    "pretrain_readiness_inspection/pretrain_readiness_recommendations.csv",
    "model_vs_actual_summary.csv",
    "action_layer_recalibration_summary.csv",
    "learning_scoreboard/promotion_learning_scoreboard_summary.csv",
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/inspection_ingest/no_prior_manual_inspection_summary.csv",
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/inspection_ingest/no_prior_manual_review_rule_candidates.csv",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "metric_status",
    "notes",
)

STEPS_COLUMNS: tuple[str, ...] = (
    "roadmap_step",
    "step_order",
    "current_status",
    "blocking_flag",
    "required_input",
    "required_output",
    "success_metric",
    "minimum_threshold",
    "target_threshold",
    "why_it_matters",
    "next_action",
    "production_order_change_flag",
    "stage_12_change_flag",
)

EVIDENCE_REQUIREMENTS_COLUMNS: tuple[str, ...] = (
    "evidence_requirement",
    "current_state",
    "minimum_threshold",
    "target_threshold",
    "blocking_flag",
    "why_it_matters",
    "next_action",
    "source_artifact",
)

SCORE_LIFT_TARGET_COLUMNS: tuple[str, ...] = (
    "score_area",
    "current_score",
    "target_score",
    "largest_blocker",
    "next_lift_action",
    "expected_score_after_next_action",
    "evidence_required_for_9",
)


class PromotionsShadowTrainingRoadmapError(RuntimeError):
    """Raised when the shadow-training roadmap cannot be built safely."""


@dataclass(frozen=True)
class PromotionsShadowTrainingRoadmapMetrics:
    final_recommendation: str
    next_immediate_action: str
    full_train_allowed_flag: bool
    shadow_only_dry_run_allowed_flag: bool
    top_blocker: str
    top_blocker_reason: str
    blocked_readiness_checks: tuple[str, ...]
    warning_checks: tuple[str, ...]
    manual_input_rows: int
    manual_complete_rows: int
    manual_incomplete_rows: int
    manual_invalid_rows: int
    candidate_ready_rows: int
    candidate_file_rows: int
    candidate_gross_profit: float
    forecast_correlation: float
    forecast_bias_units: float
    unresolved_action_layer_rows: int
    cleanup_issues_reduced: int
    cleanup_residual_issues: int
    rows_reviewed: int
    production_order_changes: int
    stage12_changes: int


@dataclass(frozen=True)
class PromotionsShadowTrainingRoadmapResult:
    summary_frame: pd.DataFrame
    steps_frame: pd.DataFrame
    evidence_requirements_frame: pd.DataFrame
    score_lift_targets_frame: pd.DataFrame
    memo_markdown: str
    final_recommendation: str
    full_train_allowed_flag: bool
    shadow_only_dry_run_allowed_flag: bool
    top_blocker: str
    next_immediate_action: str


@dataclass(frozen=True)
class PromotionsShadowTrainingRoadmapArtifacts:
    summary_csv_path: str
    steps_csv_path: str
    evidence_requirements_csv_path: str
    score_lift_targets_csv_path: str
    memo_md_path: str


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty and not allow_empty:
        raise PromotionsShadowTrainingRoadmapError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsShadowTrainingRoadmapError(f"Manifest must be a JSON object: {path}")
    return payload


def _validate_review_artifact_root(review_artifact_root: Path) -> None:
    missing = [
        artifact_name
        for artifact_name in REQUIRED_REVIEW_ARTIFACTS
        if not (review_artifact_root / artifact_name).exists()
    ]
    if missing:
        raise PromotionsShadowTrainingRoadmapError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsShadowTrainingRoadmapError(
            f"{frame_name} is missing required columns: {missing}"
        )


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
        raise PromotionsShadowTrainingRoadmapError(
            f"{frame_name} is missing required metric_name: {metric_name}"
        )
    return lookup[metric_name]


def _get_row_lookup(
    frame: pd.DataFrame,
    *,
    key_column: str,
    frame_name: str,
) -> dict[str, pd.Series]:
    _require_columns(frame, (key_column,), frame_name=frame_name)
    if frame[key_column].astype(str).duplicated().any():
        duplicates = (
            frame.loc[frame[key_column].astype(str).duplicated(), key_column]
            .astype(str)
            .drop_duplicates()
            .tolist()
        )
        raise PromotionsShadowTrainingRoadmapError(
            f"{frame_name} has duplicate {key_column} values: {duplicates}"
        )
    return {
        str(row[key_column]): row
        for _, row in frame.iterrows()
    }


def _get_single_row(frame: pd.DataFrame, *, frame_name: str) -> pd.Series:
    if frame.shape[0] != 1:
        raise PromotionsShadowTrainingRoadmapError(
            f"{frame_name} must contain exactly one row; found {frame.shape[0]}."
        )
    return frame.iloc[0]


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
    metric_group: str,
    metric_name: str,
    metric_value: object,
    metric_unit: str,
    metric_display: str,
    metric_status: str,
    notes: str,
) -> dict[str, object]:
    return {
        "metric_group": metric_group,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit,
        "metric_display": metric_display,
        "metric_status": metric_status,
        "notes": notes,
    }


def _step_row(
    roadmap_step: str,
    step_order: int,
    current_status: str,
    blocking_flag: int,
    required_input: str,
    required_output: str,
    success_metric: str,
    minimum_threshold: str,
    target_threshold: str,
    why_it_matters: str,
    next_action: str,
    production_order_change_flag: int,
    stage_12_change_flag: int,
) -> dict[str, object]:
    return {
        "roadmap_step": roadmap_step,
        "step_order": int(step_order),
        "current_status": current_status,
        "blocking_flag": int(blocking_flag),
        "required_input": required_input,
        "required_output": required_output,
        "success_metric": success_metric,
        "minimum_threshold": minimum_threshold,
        "target_threshold": target_threshold,
        "why_it_matters": why_it_matters,
        "next_action": next_action,
        "production_order_change_flag": int(production_order_change_flag),
        "stage_12_change_flag": int(stage_12_change_flag),
    }


def _extract_metrics(
    *,
    pretrain_readiness_summary_frame: pd.DataFrame,
    pretrain_readiness_blockers_frame: pd.DataFrame,
    pretrain_readiness_recommendations_frame: pd.DataFrame,
    model_vs_actual_summary_frame: pd.DataFrame,
    action_layer_recalibration_summary_frame: pd.DataFrame,
    learning_scoreboard_summary_frame: pd.DataFrame,
    manual_inspection_summary_frame: pd.DataFrame,
    review_rule_candidates_frame: pd.DataFrame,
) -> PromotionsShadowTrainingRoadmapMetrics:
    readiness_lookup = _get_row_lookup(
        pretrain_readiness_summary_frame,
        key_column="readiness_check",
        frame_name="pretrain_readiness_summary_frame",
    )
    recommendation_lookup = _get_row_lookup(
        pretrain_readiness_recommendations_frame,
        key_column="recommendation_scope",
        frame_name="pretrain_readiness_recommendations_frame",
    )

    _require_columns(
        pretrain_readiness_blockers_frame,
        ("readiness_check", "reason"),
        frame_name="pretrain_readiness_blockers_frame",
    )
    if pretrain_readiness_blockers_frame.empty:
        raise PromotionsShadowTrainingRoadmapError(
            "pretrain_readiness_blockers_frame must contain at least one blocker row."
        )

    _require_columns(
        model_vs_actual_summary_frame,
        ("row_count", "forecast_correlation", "forecast_bias_units"),
        frame_name="model_vs_actual_summary_frame",
    )
    model_row = _get_single_row(model_vs_actual_summary_frame, frame_name="model_vs_actual_summary_frame")
    forecast_correlation = float(pd.to_numeric(model_row["forecast_correlation"], errors="raise"))
    forecast_bias_units = float(pd.to_numeric(model_row["forecast_bias_units"], errors="raise"))
    rows_reviewed = int(round(float(pd.to_numeric(model_row["row_count"], errors="raise"))))

    scoreboard_lookup = _get_metric_lookup(
        learning_scoreboard_summary_frame,
        frame_name="learning_scoreboard_summary_frame",
    )
    manual_lookup = _get_metric_lookup(
        manual_inspection_summary_frame,
        frame_name="manual_inspection_summary_frame",
    )

    manual_input_rows = int(round(_require_metric(manual_lookup, "INPUT_ROWS", frame_name="manual_inspection_summary_frame")))
    manual_complete_rows = int(round(_require_metric(manual_lookup, "COMPLETE_ROWS", frame_name="manual_inspection_summary_frame")))
    manual_incomplete_rows = int(round(_require_metric(manual_lookup, "INCOMPLETE_ROWS", frame_name="manual_inspection_summary_frame")))
    manual_invalid_rows = int(round(_require_metric(manual_lookup, "INVALID_ROWS", frame_name="manual_inspection_summary_frame")))
    candidate_ready_rows = int(round(_require_metric(manual_lookup, "CANDIDATE_READY_ROWS", frame_name="manual_inspection_summary_frame")))
    candidate_file_rows = int(len(review_rule_candidates_frame.index))
    candidate_gross_profit = _sum_numeric_column(review_rule_candidates_frame, "actual_gross_profit")

    unresolved_action_layer_rows = int(
        round(
            sum(
                _get_action_layer_issue_count(
                    action_layer_recalibration_summary_frame,
                    label_name=label_name,
                )
                for label_name in ACTION_LAYER_BLOCKING_LABELS
            )
        )
    )

    cleanup_issues_reduced = int(round(_require_metric(
        scoreboard_lookup,
        "CLEANUP_ISSUES_REDUCED",
        frame_name="learning_scoreboard_summary_frame",
    )))
    cleanup_residual_issues = CLEANUP_ISSUE_BASELINE - cleanup_issues_reduced
    if cleanup_residual_issues < 0:
        raise PromotionsShadowTrainingRoadmapError(
            "Cleanup issues reduced exceeds the governed baseline."
        )

    scoreboard_rows_reviewed = int(round(_require_metric(
        scoreboard_lookup,
        "TOTAL_ROWS_REVIEWED",
        frame_name="learning_scoreboard_summary_frame",
    )))
    if rows_reviewed != scoreboard_rows_reviewed:
        raise PromotionsShadowTrainingRoadmapError(
            "Model-vs-actual row_count does not match the learning scoreboard reviewed-row count."
        )

    production_order_changes = int(round(_require_metric(
        scoreboard_lookup,
        "PRODUCTION_ORDER_CHANGE_COUNT",
        frame_name="learning_scoreboard_summary_frame",
    )))
    production_order_changes += int(round(_require_metric(
        manual_lookup,
        "PRODUCTION_ORDER_CHANGES",
        frame_name="manual_inspection_summary_frame",
    )))
    production_order_changes += int(round(_sum_numeric_column(review_rule_candidates_frame, "production_order_change_flag")))

    stage12_changes = int(round(_require_metric(
        scoreboard_lookup,
        "STAGE12_CHANGE_COUNT",
        frame_name="learning_scoreboard_summary_frame",
    )))
    stage12_changes += int(round(_require_metric(
        manual_lookup,
        "STAGE12_CHANGES",
        frame_name="manual_inspection_summary_frame",
    )))
    stage12_changes += int(round(_sum_numeric_column(review_rule_candidates_frame, "stage_12_change_flag")))

    full_train_row = recommendation_lookup.get("FULL_TRAIN")
    next_action_row = recommendation_lookup.get("NEXT_HIGH_VALUE_ACTION")
    shadow_only_row = recommendation_lookup.get("SHADOW_ONLY_DRY_RUN")
    if full_train_row is None or next_action_row is None or shadow_only_row is None:
        raise PromotionsShadowTrainingRoadmapError(
            "pretrain_readiness_recommendations_frame must contain FULL_TRAIN, NEXT_HIGH_VALUE_ACTION, and SHADOW_ONLY_DRY_RUN rows."
        )

    full_train_allowed_flag = bool(int(round(float(pd.to_numeric(full_train_row["allowed_flag"], errors="raise")))))
    shadow_only_dry_run_allowed_flag = bool(
        int(round(float(pd.to_numeric(shadow_only_row["allowed_flag"], errors="raise"))))
    )

    top_blocker_row = pretrain_readiness_blockers_frame.iloc[0]
    blocked_readiness_checks = tuple(
        pretrain_readiness_blockers_frame["readiness_check"].astype(str).tolist()
    )
    warning_checks = tuple(
        pretrain_readiness_summary_frame.loc[
            pretrain_readiness_summary_frame["status"].astype(str).eq("WARN"),
            "readiness_check",
        ].astype(str).tolist()
    )

    return PromotionsShadowTrainingRoadmapMetrics(
        final_recommendation=str(full_train_row["recommendation"]),
        next_immediate_action=str(next_action_row["recommendation"]),
        full_train_allowed_flag=full_train_allowed_flag,
        shadow_only_dry_run_allowed_flag=shadow_only_dry_run_allowed_flag,
        top_blocker=str(top_blocker_row["readiness_check"]),
        top_blocker_reason=str(top_blocker_row["reason"]),
        blocked_readiness_checks=blocked_readiness_checks,
        warning_checks=warning_checks,
        manual_input_rows=manual_input_rows,
        manual_complete_rows=manual_complete_rows,
        manual_incomplete_rows=manual_incomplete_rows,
        manual_invalid_rows=manual_invalid_rows,
        candidate_ready_rows=candidate_ready_rows,
        candidate_file_rows=candidate_file_rows,
        candidate_gross_profit=candidate_gross_profit,
        forecast_correlation=forecast_correlation,
        forecast_bias_units=forecast_bias_units,
        unresolved_action_layer_rows=unresolved_action_layer_rows,
        cleanup_issues_reduced=cleanup_issues_reduced,
        cleanup_residual_issues=cleanup_residual_issues,
        rows_reviewed=rows_reviewed,
        production_order_changes=production_order_changes,
        stage12_changes=stage12_changes,
    )


def _build_summary_frame(metrics: PromotionsShadowTrainingRoadmapMetrics) -> pd.DataFrame:
    rows = [
        _summary_row(
            "ROADMAP_GATE",
            "FINAL_RECOMMENDATION",
            metrics.final_recommendation,
            "label",
            metrics.final_recommendation,
            "BLOCKED" if not metrics.full_train_allowed_flag else "READY",
            "The roadmap inherits the current governed pre-train gate recommendation.",
        ),
        _summary_row(
            "ROADMAP_GATE",
            "FULL_TRAIN_ALLOWED",
            int(metrics.full_train_allowed_flag),
            "flag",
            "YES" if metrics.full_train_allowed_flag else "NO",
            "BLOCKED" if not metrics.full_train_allowed_flag else "READY",
            "Full train remains blocked until roadmap evidence is accumulated.",
        ),
        _summary_row(
            "ROADMAP_GATE",
            "SHADOW_ONLY_DRY_RUN_ALLOWED",
            int(metrics.shadow_only_dry_run_allowed_flag),
            "flag",
            "YES" if metrics.shadow_only_dry_run_allowed_flag else "NO",
            "ALLOWED" if metrics.shadow_only_dry_run_allowed_flag else "BLOCKED",
            "Shadow-only work remains the highest-governance next pass.",
        ),
        _summary_row(
            "ROADMAP_GATE",
            "NEXT_IMMEDIATE_ACTION",
            metrics.next_immediate_action,
            "label",
            metrics.next_immediate_action,
            "READY",
            "This is the next governed action with the highest score-lift leverage.",
        ),
        _summary_row(
            "ROADMAP_GATE",
            "TOP_BLOCKER",
            metrics.top_blocker,
            "label",
            metrics.top_blocker,
            "BLOCKED",
            metrics.top_blocker_reason,
        ),
        _summary_row(
            "ROADMAP_SCOPE",
            "ROADMAP_STEP_COUNT",
            len(ROADMAP_STEPS),
            "steps",
            _format_int(len(ROADMAP_STEPS)),
            "INFO",
            "The roadmap stays diagnostic-only and sequenced.",
        ),
        _summary_row(
            "ROADMAP_SCOPE",
            "BLOCKING_CHECK_COUNT",
            len(metrics.blocked_readiness_checks),
            "checks",
            _format_int(len(metrics.blocked_readiness_checks)),
            "BLOCKED",
            "Current readiness blockers are carried directly into the roadmap.",
        ),
        _summary_row(
            "ROADMAP_SCOPE",
            "WARNING_CHECK_COUNT",
            len(metrics.warning_checks),
            "checks",
            _format_int(len(metrics.warning_checks)),
            "WARN" if metrics.warning_checks else "INFO",
            "Warnings continue as backlog even when they do not block the next shadow step.",
        ),
        _summary_row(
            "NO_PRIOR_EVIDENCE",
            "MANUAL_COMPLETE_ROWS",
            metrics.manual_complete_rows,
            "rows",
            _format_int(metrics.manual_complete_rows),
            "BLOCKED" if metrics.manual_complete_rows < metrics.manual_input_rows else "READY",
            f"Manual rows complete: {_format_int(metrics.manual_complete_rows)} of {_format_int(metrics.manual_input_rows)}.",
        ),
        _summary_row(
            "NO_PRIOR_EVIDENCE",
            "CANDIDATE_READY_ROWS",
            metrics.candidate_ready_rows,
            "rows",
            _format_int(metrics.candidate_ready_rows),
            "BLOCKED" if metrics.candidate_ready_rows <= 0 else "READY",
            "Candidate rows should only arise from completed manual labels.",
        ),
        _summary_row(
            "FORECAST_HEAD",
            "FORECAST_CORRELATION",
            metrics.forecast_correlation,
            "correlation",
            _format_float(metrics.forecast_correlation),
            "BLOCKED" if metrics.forecast_correlation < 0.50 else "READY",
            "Forecast correlation must improve before full train is reconsidered.",
        ),
        _summary_row(
            "FORECAST_HEAD",
            "FORECAST_BIAS_UNITS",
            metrics.forecast_bias_units,
            "units",
            _format_signed_int(metrics.forecast_bias_units),
            "BLOCKED" if metrics.forecast_bias_units > 0 else "INFO",
            "Bias needs to come down materially from the current positive over-forecast.",
        ),
        _summary_row(
            "ACTION_LAYER",
            "UNRESOLVED_RULE_FLAG_ROWS",
            metrics.unresolved_action_layer_rows,
            "rows",
            _format_int(metrics.unresolved_action_layer_rows),
            "BLOCKED" if metrics.unresolved_action_layer_rows > 0 else "READY",
            "Action-layer calibration needs repeated shadow evidence before policy trust can rise.",
        ),
        _summary_row(
            "REPORT_CLEANUP",
            "RESIDUAL_CLEANUP_ISSUES",
            metrics.cleanup_residual_issues,
            "issues",
            _format_int(metrics.cleanup_residual_issues),
            "WARN" if metrics.cleanup_residual_issues > 0 else "READY",
            f"Cleanup backlog improved by {_format_int(metrics.cleanup_issues_reduced)} issues but is not yet zero.",
        ),
        _summary_row(
            "SCORE_LIFT",
            "TRAINING_READINESS_CURRENT_SCORE",
            TRAINING_READINESS_CURRENT_SCORE,
            "score",
            _format_float(TRAINING_READINESS_CURRENT_SCORE, decimals=1),
            "INFO",
            "Current training-readiness planning score.",
        ),
        _summary_row(
            "SCORE_LIFT",
            "TRAINING_READINESS_TARGET_SCORE",
            TRAINING_READINESS_TARGET_SCORE,
            "score",
            _format_float(TRAINING_READINESS_TARGET_SCORE, decimals=1),
            "TARGET",
            "Roadmap target for governed training readiness.",
        ),
        _summary_row(
            "SCORE_LIFT",
            "AUTO_ORDERING_CURRENT_SCORE",
            AUTO_ORDERING_CURRENT_SCORE,
            "score",
            _format_float(AUTO_ORDERING_CURRENT_SCORE, decimals=1),
            "INFO",
            "Current auto-ordering planning score.",
        ),
        _summary_row(
            "SCORE_LIFT",
            "AUTO_ORDERING_TARGET_SCORE",
            AUTO_ORDERING_TARGET_SCORE,
            "score",
            _format_float(AUTO_ORDERING_TARGET_SCORE, decimals=1),
            "TARGET",
            "Roadmap target for governed auto-ordering readiness.",
        ),
        _summary_row(
            "GUARDRAILS",
            "PRODUCTION_ORDER_CHANGES",
            metrics.production_order_changes,
            "rows",
            _format_int(metrics.production_order_changes),
            "LOCKED" if metrics.production_order_changes == 0 else "BLOCKED",
            "The roadmap must not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAILS",
            "STAGE12_CHANGES",
            metrics.stage12_changes,
            "rows",
            _format_int(metrics.stage12_changes),
            "LOCKED" if metrics.stage12_changes == 0 else "BLOCKED",
            "The roadmap must not change Stage 12.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_steps_frame(metrics: PromotionsShadowTrainingRoadmapMetrics) -> pd.DataFrame:
    rows = [
        _step_row(
            "COMPLETE_MANUAL_NO_PRIOR_LABELS",
            1,
            "BLOCKED_INCOMPLETE_LABELS" if metrics.manual_complete_rows < metrics.manual_input_rows or metrics.manual_invalid_rows > 0 else "PASS",
            1 if metrics.manual_complete_rows < metrics.manual_input_rows or metrics.manual_invalid_rows > 0 else 0,
            "18-row no-prior manual worksheet",
            "18 complete governed manual rows with 0 invalid rows",
            "manual_complete_rows",
            f"{_format_int(metrics.manual_input_rows)}/{_format_int(metrics.manual_input_rows)} complete and 0 invalid",
            "All 18 rows complete with stable human cause labels and notes",
            "The roadmap cannot accumulate governed label evidence until the manual worksheet is complete.",
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
            0,
            0,
        ),
        _step_row(
            "INGEST_MANUAL_LABELS",
            2,
            "WAITING_ON_COMPLETE_LABELS" if metrics.manual_complete_rows < metrics.manual_input_rows else "READY_TO_INGEST",
            1,
            "Completed no-prior manual worksheet",
            "Validated ingest summary with complete rows, 0 invalid rows, and reconciled candidate counts",
            "ingest_complete_rows_and_invalid_rows",
            f"{_format_int(metrics.manual_input_rows)} complete rows, 0 invalid rows",
            "Validated ingest run that preserves zero production and zero Stage 12 changes",
            "The ingest pass converts manual operator knowledge into governed machine-readable evidence.",
            "RERUN_INGEST_AFTER_MANUAL_COMPLETION",
            0,
            0,
        ),
        _step_row(
            "GENERATE_SHADOW_REVIEW_RULE_CANDIDATES",
            3,
            "WAITING_ON_INGESTED_LABELS" if metrics.candidate_file_rows <= 0 else "PASS",
            1 if metrics.candidate_file_rows <= 0 else 0,
            "Validated manual-inspection ingest outputs",
            "Shadow review rule candidate CSV sourced only from completed manual labels",
            "candidate_ready_rows",
            ">= 1 candidate-ready row and summary/file counts match",
            "Candidate rows exist with governed reasons and positive represented learning value",
            "No shadow-learning slice exists until candidate rows are generated from completed labels.",
            "GENERATE_CANDIDATES_FROM_COMPLETED_LABELS",
            0,
            0,
        ),
        _step_row(
            "RUN_SHADOW_ONLY_DATA_INSPECTION",
            4,
            "WAITING_ON_CANDIDATE_ROWS" if metrics.candidate_file_rows <= 0 else "READY_FOR_SHADOW_INSPECTION",
            1,
            "Candidate rows plus current governed baseline summaries",
            "Diagnostic-only inspection packet comparing candidate evidence to current forecast and action behavior",
            "forecast_correlation_and_bias_direction",
            "Correlation trend improves toward 0.50 and bias direction improves from +1,235",
            "Shadow inspection shows cleaner evidence and narrower forecast/action error seams",
            "This step accumulates diagnostic evidence without loosening any production guardrails.",
            "RUN_SHADOW_ONLY_DATA_INSPECTION",
            0,
            0,
        ),
        _step_row(
            "RUN_SHADOW_ONLY_DRY_TRAIN",
            5,
            "ALLOWED_SHADOW_ONLY_AFTER_DATA_INSPECTION" if metrics.shadow_only_dry_run_allowed_flag else "BLOCKED_BY_GUARDRAILS",
            0 if metrics.shadow_only_dry_run_allowed_flag else 1,
            "Shadow-only inspection outputs and the current governed review root",
            "Shadow-only dry-train diagnostics with zero production-order and Stage 12 changes",
            "shadow_only_dry_train_guardrails",
            "Zero production-order changes and zero Stage 12 changes",
            "Repeatable dry-train diagnostics ready for comparison, still fully shadow-only",
            "Shadow-only dry train is the highest-value executable step once the evidence packet is ready, because it does not change production logic.",
            "RUN_SHADOW_ONLY_DRY_TRAIN",
            0,
            0,
        ),
        _step_row(
            "RUN_ACTION_LAYER_SHADOW_CALIBRATION",
            6,
            "WAITING_ON_SHADOW_DRY_TRAIN" if metrics.unresolved_action_layer_rows > 0 else "PASS",
            1 if metrics.unresolved_action_layer_rows > 0 else 0,
            "Shadow dry-train diagnostics and action-layer recalibration summary",
            "Reduced unresolved action-layer rule-flag rows with shadow-only calibration notes",
            "unresolved_action_layer_rule_flag_rows",
            f"Lower than {_format_int(metrics.unresolved_action_layer_rows)} unresolved rows and trending down",
            "0 unresolved action-layer rule-flag rows before any production pilot is discussed",
            "Action-layer routing has to get safer in shadow before any production trust score can rise.",
            "RUN_ACTION_LAYER_SHADOW_CALIBRATION",
            0,
            0,
        ),
        _step_row(
            "COMPARE_SHADOW_VS_BASELINE",
            7,
            "WAITING_ON_SHADOW_CALIBRATION",
            1,
            "Shadow-only dry-train outputs plus current baseline summaries",
            "Comparison packet showing shadow versus baseline overstock and missed-sales risk",
            "shadow_overstock_risk_and_missed_sales_delta",
            "Shadow comparison shows lower overstock risk and lower missed-sales risk than baseline",
            "Repeated lower-risk comparisons with no production or Stage 12 changes",
            "Readiness cannot move toward 9/10 without a like-for-like comparison that proves the shadow path is safer than the baseline.",
            "COMPARE_SHADOW_VS_BASELINE",
            0,
            0,
        ),
        _step_row(
            "REPEAT_ACROSS_MULTIPLE_PROMOTIONS",
            8,
            "WAITING_ON_REPEATED_SHADOW_EVIDENCE",
            1,
            "Shadow-versus-baseline comparison outputs from the first promotion",
            "Repeated shadow wins across more than one promotion",
            "promotion_count_with_repeated_shadow_wins",
            "> 1 promotion with repeated shadow wins",
            "Multiple promotions show the same lower-risk shadow pattern before any pilot discussion",
            "Auto-ordering readiness cannot reach 9/10 on a single governed case; it needs repeated wins across multiple promotions.",
            "REPEAT_ACROSS_MULTIPLE_PROMOTIONS",
            0,
            0,
        ),
        _step_row(
            "ONLY_THEN_CONSIDER_LIMITED_PRODUCTION_PILOT",
            9,
            "LOCKED_UNTIL_REPEATED_SHADOW_WINS",
            1,
            "Repeated multi-promotion shadow evidence plus zero guardrail changes",
            "Pilot decision memo only after repeated shadow evidence reaches governance thresholds",
            "auto_ordering_readiness_score",
            "Training readiness near 9/10 and auto-ordering readiness near 9/10 with repeated evidence",
            "Limited pilot considered only after repeated lower-risk shadow wins and sustained guardrail discipline",
            "The roadmap ends in a pilot consideration memo, not an automatic production change, because evidence comes before policy movement.",
            "KEEP_PRODUCTION_GUARDRAILS_LOCKED",
            0,
            0,
        ),
    ]
    return pd.DataFrame(rows, columns=STEPS_COLUMNS)


def _build_evidence_requirements_frame(
    metrics: PromotionsShadowTrainingRoadmapMetrics,
) -> pd.DataFrame:
    rows = [
        {
            "evidence_requirement": "MANUAL_LABELS_COMPLETE_FOR_NO_PRIOR_ROWS",
            "current_state": f"{_format_int(metrics.manual_complete_rows)} complete / {_format_int(metrics.manual_input_rows)} total / {_format_int(metrics.manual_invalid_rows)} invalid",
            "minimum_threshold": f"{_format_int(metrics.manual_input_rows)}/{_format_int(metrics.manual_input_rows)} complete and 0 invalid rows",
            "target_threshold": "All 18 rows complete with durable human notes and governed cause labels",
            "blocking_flag": 1,
            "why_it_matters": "Manual labels are the first governed evidence source for the no-prior slice.",
            "next_action": "COMPLETE_MANUAL_WORKSHEET_FIRST",
            "source_artifact": "no_prior_manual_inspection_summary.csv",
        },
        {
            "evidence_requirement": "CANDIDATE_READY_ROWS_ONLY_FROM_COMPLETED_LABELS",
            "current_state": f"summary={_format_int(metrics.candidate_ready_rows)}; file={_format_int(metrics.candidate_file_rows)}; gross_profit={_format_money(metrics.candidate_gross_profit)}",
            "minimum_threshold": ">= 1 candidate-ready row and summary/file counts match",
            "target_threshold": "Candidate rows exist only from completed manual labels and remain shadow-only",
            "blocking_flag": 1,
            "why_it_matters": "Candidate rows are the governed learning slice that converts manual evidence into shadow-training evidence.",
            "next_action": "GENERATE_CANDIDATES_FROM_COMPLETED_LABELS",
            "source_artifact": "no_prior_manual_review_rule_candidates.csv",
        },
        {
            "evidence_requirement": "FORECAST_CORRELATION_IMPROVES_TOWARD_FULL_TRAIN_FLOOR",
            "current_state": f"correlation={_format_float(metrics.forecast_correlation)}",
            "minimum_threshold": "Forecast correlation reaches at least 0.50 before full training is reconsidered",
            "target_threshold": "Forecast correlation stays at or above 0.50 across repeated shadow comparisons",
            "blocking_flag": 1,
            "why_it_matters": "Training readiness cannot move toward 9/10 while the forecast head remains materially under-trusted.",
            "next_action": "RUN_SHADOW_ONLY_DATA_INSPECTION",
            "source_artifact": "model_vs_actual_summary.csv",
        },
        {
            "evidence_requirement": "FORECAST_BIAS_REDUCES_MATERIALLY",
            "current_state": f"bias={_format_signed_int(metrics.forecast_bias_units)} units",
            "minimum_threshold": f"Bias is materially lower than {_format_signed_int(metrics.forecast_bias_units)} units",
            "target_threshold": "Bias continues shrinking toward a much flatter governed shadow profile",
            "blocking_flag": 1,
            "why_it_matters": "Positive bias keeps overstock risk elevated even if correlation improves.",
            "next_action": "RUN_SHADOW_ONLY_DATA_INSPECTION",
            "source_artifact": "model_vs_actual_summary.csv",
        },
        {
            "evidence_requirement": "ACTION_LAYER_RULE_FLAGS_REDUCE_FROM_100",
            "current_state": f"{_format_int(metrics.unresolved_action_layer_rows)} unresolved rule-flag rows",
            "minimum_threshold": f"Lower than {_format_int(metrics.unresolved_action_layer_rows)} unresolved rows and trending down",
            "target_threshold": "Unresolved action-layer rule-flag rows approach 0 before any pilot is considered",
            "blocking_flag": 1,
            "why_it_matters": "Action routing must become safer in shadow before auto-ordering trust can rise.",
            "next_action": "RUN_ACTION_LAYER_SHADOW_CALIBRATION",
            "source_artifact": "action_layer_recalibration_summary.csv",
        },
        {
            "evidence_requirement": "SHADOW_ONLY_COMPARISON_BEATS_BASELINE_RISK",
            "current_state": "Not yet produced from the current governed artifact set",
            "minimum_threshold": "Shadow-only comparison shows lower overstock risk and lower missed-sales risk than the baseline",
            "target_threshold": "Lower-risk shadow comparison repeats across multiple promotions",
            "blocking_flag": 1,
            "why_it_matters": "Improving scores requires proof that shadow behavior is safer, not just different.",
            "next_action": "COMPARE_SHADOW_VS_BASELINE",
            "source_artifact": "future_shadow_vs_baseline_comparison",
        },
        {
            "evidence_requirement": "REPEATED_EVIDENCE_ACROSS_MULTIPLE_PROMOTIONS",
            "current_state": "Single governed review root only; repeated multi-promotion evidence not yet available",
            "minimum_threshold": "> 1 promotions with repeated shadow wins",
            "target_threshold": "Repeated shadow wins across multiple promotions before any limited production pilot",
            "blocking_flag": 1,
            "why_it_matters": "Auto-ordering readiness reaches 9/10 only after the shadow path keeps winning beyond a single promotion.",
            "next_action": "REPEAT_ACROSS_MULTIPLE_PROMOTIONS",
            "source_artifact": "future_multi_promotion_shadow_evidence",
        },
    ]
    return pd.DataFrame(rows, columns=EVIDENCE_REQUIREMENTS_COLUMNS)


def _build_score_lift_targets_frame(
    metrics: PromotionsShadowTrainingRoadmapMetrics,
) -> pd.DataFrame:
    rows = [
        {
            "score_area": "TRAINING_READINESS",
            "current_score": TRAINING_READINESS_CURRENT_SCORE,
            "target_score": TRAINING_READINESS_TARGET_SCORE,
            "largest_blocker": metrics.top_blocker,
            "next_lift_action": metrics.next_immediate_action,
            "expected_score_after_next_action": TRAINING_READINESS_EXPECTED_AFTER_NEXT_ACTION,
            "evidence_required_for_9": "Complete all 18 manual labels, generate candidate-ready rows from those labels, push forecast correlation to at least 0.50, reduce bias materially, and shrink action-layer rule flags before reconsidering full train.",
        },
        {
            "score_area": "AUTO_ORDERING_READINESS",
            "current_score": AUTO_ORDERING_CURRENT_SCORE,
            "target_score": AUTO_ORDERING_TARGET_SCORE,
            "largest_blocker": "forecast_head_reliability_and_multi_promotion_shadow_evidence",
            "next_lift_action": "RUN_SHADOW_ONLY_DATA_INSPECTION",
            "expected_score_after_next_action": AUTO_ORDERING_EXPECTED_AFTER_NEXT_ACTION,
            "evidence_required_for_9": "Auto-ordering needs repeated shadow-only comparisons showing lower overstock risk and lower missed-sales risk than baseline across more than one promotion, with production ordering and Stage 12 still unchanged.",
        },
        {
            "score_area": "OPERATOR_REVIEW",
            "current_score": OPERATOR_REVIEW_CURRENT_SCORE,
            "target_score": OPERATOR_REVIEW_TARGET_SCORE,
            "largest_blocker": "manual_worksheet_loop_not_closed",
            "next_lift_action": metrics.next_immediate_action,
            "expected_score_after_next_action": OPERATOR_REVIEW_EXPECTED_AFTER_NEXT_ACTION,
            "evidence_required_for_9": "Already above 9/10; keep operator packets aligned, preserve provenance, and close the 18-row manual worksheet loop without changing production logic.",
        },
        {
            "score_area": "GOVERNANCE",
            "current_score": GOVERNANCE_CURRENT_SCORE,
            "target_score": GOVERNANCE_TARGET_SCORE,
            "largest_blocker": "none_keep_guardrails_locked",
            "next_lift_action": "MAINTAIN_SHADOW_ONLY_GUARDRAILS",
            "expected_score_after_next_action": GOVERNANCE_EXPECTED_AFTER_NEXT_ACTION,
            "evidence_required_for_9": "Already above 9/10; maintain zero production-order changes, zero Stage 12 changes, shadow-only policy, and governed provenance on every new artifact.",
        },
    ]
    return pd.DataFrame(rows, columns=SCORE_LIFT_TARGET_COLUMNS)


def _build_memo(metrics: PromotionsShadowTrainingRoadmapMetrics) -> str:
    blocked_checks = ", ".join(metrics.blocked_readiness_checks)
    warning_checks = ", ".join(metrics.warning_checks) if metrics.warning_checks else "none"
    lines = [
        "# Shadow Training Roadmap",
        "",
        "This roadmap does not start training.",
        "Full train remains blocked.",
        f"Shadow-only dry run remains {'allowed' if metrics.shadow_only_dry_run_allowed_flag else 'blocked'}.",
        f"Production order changes = {_format_int(metrics.production_order_changes)}.",
        f"Stage 12 changes = {_format_int(metrics.stage12_changes)}.",
        "",
        f"Current training readiness score: {_format_float(TRAINING_READINESS_CURRENT_SCORE, decimals=1)} / 10.",
        f"Target training readiness score: {_format_float(TRAINING_READINESS_TARGET_SCORE, decimals=1)} / 10.",
        f"Current auto-ordering readiness score: {_format_float(AUTO_ORDERING_CURRENT_SCORE, decimals=1)} / 10.",
        f"Target auto-ordering readiness score: {_format_float(AUTO_ORDERING_TARGET_SCORE, decimals=1)} / 10.",
        "",
        "The path to 9/10 is evidence accumulation, not looser guardrails.",
        "Training readiness can improve faster than auto-ordering readiness because training only needs enough governed shadow evidence to justify another controlled diagnostic pass, while auto-ordering needs repeated proof that shadow behavior is safer than the current baseline before any production pilot is even discussed.",
        "Auto-ordering to 9/10 requires repeated shadow evidence across multiple promotions.",
        "",
        "Current blockers to work through in order:",
        f"1. Manual no-prior labels are still incomplete: {_format_int(metrics.manual_complete_rows)} complete and {_format_int(metrics.manual_incomplete_rows)} incomplete out of {_format_int(metrics.manual_input_rows)} rows.",
        f"2. Candidate-ready rows do not exist yet: {_format_int(metrics.candidate_file_rows)} current rows representing {_format_money(metrics.candidate_gross_profit)}.",
        f"3. Forecast-head reliability is still weak: correlation {_format_float(metrics.forecast_correlation)} and bias {_format_signed_int(metrics.forecast_bias_units)} units.",
        f"4. Action-layer calibration still has {_format_int(metrics.unresolved_action_layer_rows)} unresolved rule-flag rows.",
        "",
        f"Cleanup remains a warning only: {_format_int(metrics.cleanup_residual_issues)} residual issues remain after reducing {_format_int(metrics.cleanup_issues_reduced)} issues.",
        f"Blocked readiness checks: {blocked_checks}.",
        f"Warning checks: {warning_checks}.",
        "",
        "Recommended sequence:",
        "1. Finish the manual no-prior worksheet.",
        "2. Re-ingest the completed worksheet and generate shadow review rule candidates.",
        "3. Use those candidates to run shadow-only inspection and shadow-only dry-train diagnostics.",
        "4. Compare shadow outputs against the current baseline for overstock and missed-sales risk.",
        "5. Repeat the comparison across more than one promotion before even considering a limited pilot.",
        "",
        "Next immediate action: complete the 18-row manual worksheet.",
    ]
    return "\n".join(lines) + "\n"


def build_promotions_shadow_training_roadmap(
    *,
    pretrain_readiness_summary_frame: pd.DataFrame,
    pretrain_readiness_blockers_frame: pd.DataFrame,
    pretrain_readiness_recommendations_frame: pd.DataFrame,
    model_vs_actual_summary_frame: pd.DataFrame,
    action_layer_recalibration_summary_frame: pd.DataFrame,
    learning_scoreboard_summary_frame: pd.DataFrame,
    manual_inspection_summary_frame: pd.DataFrame,
    review_rule_candidates_frame: pd.DataFrame,
) -> PromotionsShadowTrainingRoadmapResult:
    metrics = _extract_metrics(
        pretrain_readiness_summary_frame=pretrain_readiness_summary_frame,
        pretrain_readiness_blockers_frame=pretrain_readiness_blockers_frame,
        pretrain_readiness_recommendations_frame=pretrain_readiness_recommendations_frame,
        model_vs_actual_summary_frame=model_vs_actual_summary_frame,
        action_layer_recalibration_summary_frame=action_layer_recalibration_summary_frame,
        learning_scoreboard_summary_frame=learning_scoreboard_summary_frame,
        manual_inspection_summary_frame=manual_inspection_summary_frame,
        review_rule_candidates_frame=review_rule_candidates_frame,
    )
    summary_frame = _build_summary_frame(metrics)
    steps_frame = _build_steps_frame(metrics)
    evidence_requirements_frame = _build_evidence_requirements_frame(metrics)
    score_lift_targets_frame = _build_score_lift_targets_frame(metrics)
    memo_markdown = _build_memo(metrics)
    return PromotionsShadowTrainingRoadmapResult(
        summary_frame=summary_frame,
        steps_frame=steps_frame,
        evidence_requirements_frame=evidence_requirements_frame,
        score_lift_targets_frame=score_lift_targets_frame,
        memo_markdown=memo_markdown,
        final_recommendation=metrics.final_recommendation,
        full_train_allowed_flag=metrics.full_train_allowed_flag,
        shadow_only_dry_run_allowed_flag=metrics.shadow_only_dry_run_allowed_flag,
        top_blocker=metrics.top_blocker,
        next_immediate_action=metrics.next_immediate_action,
    )


def write_promotions_shadow_training_roadmap(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsShadowTrainingRoadmapArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsShadowTrainingRoadmapError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_shadow_training_roadmap(
        pretrain_readiness_summary_frame=_read_csv(
            review_artifact_path / "pretrain_readiness_inspection" / "pretrain_readiness_summary.csv"
        ),
        pretrain_readiness_blockers_frame=_read_csv(
            review_artifact_path / "pretrain_readiness_inspection" / "pretrain_readiness_blockers.csv"
        ),
        pretrain_readiness_recommendations_frame=_read_csv(
            review_artifact_path / "pretrain_readiness_inspection" / "pretrain_readiness_recommendations.csv"
        ),
        model_vs_actual_summary_frame=_read_csv(review_artifact_path / "model_vs_actual_summary.csv"),
        action_layer_recalibration_summary_frame=_read_csv(
            review_artifact_path / "action_layer_recalibration_summary.csv"
        ),
        learning_scoreboard_summary_frame=_read_csv(
            review_artifact_path / "learning_scoreboard" / "promotion_learning_scoreboard_summary.csv"
        ),
        manual_inspection_summary_frame=_read_csv(
            review_artifact_path
            / "review_overlay_packet"
            / "operator_review_memo"
            / "no_prior_demand_manual_inspection"
            / "inspection_ingest"
            / "no_prior_manual_inspection_summary.csv"
        ),
        review_rule_candidates_frame=_read_csv(
            review_artifact_path
            / "review_overlay_packet"
            / "operator_review_memo"
            / "no_prior_demand_manual_inspection"
            / "inspection_ingest"
            / "no_prior_manual_review_rule_candidates.csv",
            allow_empty=True,
        ),
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    summary_csv_path = destination_root / "shadow_training_roadmap_summary.csv"
    steps_csv_path = destination_root / "shadow_training_roadmap_steps.csv"
    evidence_requirements_csv_path = destination_root / "shadow_training_roadmap_evidence_requirements.csv"
    score_lift_targets_csv_path = destination_root / "shadow_training_roadmap_score_lift_targets.csv"
    memo_md_path = destination_root / "shadow_training_roadmap_memo.md"

    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    add_provenance_columns(result.steps_frame.copy(), manifest).to_csv(steps_csv_path, index=False)
    add_provenance_columns(result.evidence_requirements_frame.copy(), manifest).to_csv(
        evidence_requirements_csv_path,
        index=False,
    )
    add_provenance_columns(result.score_lift_targets_frame.copy(), manifest).to_csv(
        score_lift_targets_csv_path,
        index=False,
    )
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsShadowTrainingRoadmapArtifacts(
        summary_csv_path=str(summary_csv_path),
        steps_csv_path=str(steps_csv_path),
        evidence_requirements_csv_path=str(evidence_requirements_csv_path),
        score_lift_targets_csv_path=str(score_lift_targets_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed shadow-training roadmap from existing review artifacts only."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_shadow_training_roadmap(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("shadow_training_roadmap_summary", artifacts.summary_csv_path)
    print("shadow_training_roadmap_steps", artifacts.steps_csv_path)
    print("shadow_training_roadmap_evidence_requirements", artifacts.evidence_requirements_csv_path)
    print("shadow_training_roadmap_score_lift_targets", artifacts.score_lift_targets_csv_path)
    print("shadow_training_roadmap_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())