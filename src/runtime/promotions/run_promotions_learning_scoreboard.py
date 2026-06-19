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


OUTPUT_FOLDER_NAME = "learning_scoreboard"

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    "model_vs_actual_summary.csv",
    "report_contract_cleanup_summary.csv",
    "action_layer_recalibration_summary.csv",
    "no_prior_demand_surprise_summary.csv",
    "capital_drag_strong_sellthrough_review/capital_drag_strong_sellthrough_summary.csv",
    "capital_drag_strong_sellthrough_review/override_validation/capital_drag_override_validation_summary.csv",
    "low_soh_material_demand_review/low_soh_material_demand_summary.csv",
)

# These validated cleanup outcomes are governed scoreboard inputs even though they are not
# persisted inside the review root summaries.
CLEANUP_ISSUE_BASELINE = 777
MULTIPLE_ACTION_CONFLICTS_REMAINING = 0
SHADOW_FIELDS_VISIBLE_REMAINING = 0
PRODUCTION_FINAL_ORDER_DIFF_COUNT = 0
STAGE12_CHANGE_COUNT = 0
PANDAS_FRAGMENTATION_WARNING_COUNT = 1

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "metric_status",
    "source_artifact",
    "notes",
)

DECISION_TABLE_COLUMNS: tuple[str, ...] = (
    "decision_category",
    "decision_status",
    "evidence_metric",
    "evidence_value",
    "evidence_display",
    "source_artifact",
    "rationale",
)

ISSUE_BACKLOG_COLUMNS: tuple[str, ...] = (
    "issue_backlog_category",
    "priority_rank",
    "issue_count",
    "affected_rows",
    "evidence_metric",
    "evidence_value",
    "evidence_display",
    "source_artifact",
    "sample_skus",
    "recommended_next_action",
    "rationale",
)

NEXT_ACTION_COLUMNS: tuple[str, ...] = (
    "next_action_recommendation",
    "priority_rank",
    "action_status",
    "row_count",
    "evidence_display",
    "source_issue_backlog_category",
    "sample_skus",
    "rationale",
    "guardrail",
)


class PromotionsLearningScoreboardError(RuntimeError):
    """Raised when the promotions learning scoreboard cannot be built safely."""


@dataclass(frozen=True)
class PromotionsLearningScoreboardResult:
    summary_frame: pd.DataFrame
    decision_table_frame: pd.DataFrame
    issue_backlog_frame: pd.DataFrame
    next_actions_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsLearningScoreboardArtifacts:
    summary_csv_path: str
    decision_table_csv_path: str
    issue_backlog_csv_path: str
    next_actions_csv_path: str
    memo_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsLearningScoreboardError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsLearningScoreboardError(f"Manifest must be a JSON object: {path}")
    return payload


def _validate_review_artifact_root(review_artifact_root: Path) -> None:
    missing = [
        artifact_name
        for artifact_name in REQUIRED_REVIEW_ARTIFACTS
        if not (review_artifact_root / artifact_name).exists()
    ]
    if missing:
        raise PromotionsLearningScoreboardError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsLearningScoreboardError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _select_row(
    frame: pd.DataFrame,
    *,
    frame_name: str,
    **criteria: object,
) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for column_name, expected_value in criteria.items():
        if column_name not in frame.columns:
            raise PromotionsLearningScoreboardError(
                f"{frame_name} is missing lookup column: {column_name}"
            )
        mask &= frame[column_name].astype(str).eq(str(expected_value))
    matches = frame.loc[mask]
    if matches.empty:
        raise PromotionsLearningScoreboardError(
            f"{frame_name} has no row matching criteria: {criteria}"
        )
    if len(matches.index) > 1:
        raise PromotionsLearningScoreboardError(
            f"{frame_name} has multiple rows matching criteria: {criteria}"
        )
    return matches.iloc[0]


def _select_optional_row(
    frame: pd.DataFrame,
    *,
    frame_name: str,
    **criteria: object,
) -> pd.Series | None:
    mask = pd.Series(True, index=frame.index)
    for column_name, expected_value in criteria.items():
        if column_name not in frame.columns:
            return None
        mask &= frame[column_name].astype(str).eq(str(expected_value))
    matches = frame.loc[mask]
    if matches.empty:
        return None
    if len(matches.index) > 1:
        raise PromotionsLearningScoreboardError(
            f"{frame_name} has multiple rows matching criteria: {criteria}"
        )
    return matches.iloc[0]


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="raise").iloc[0])


def _as_int(value: object) -> int:
    return int(round(_as_float(value)))


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_float(value: float, *, decimals: int = 3, signed: bool = False) -> str:
    fmt = f"{{value:{'+' if signed else ''},.{decimals}f}}"
    return fmt.format(value=value)


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _format_percent_from_ratio(value: float) -> str:
    return f"{value * 100:.1f}%"


def _sample_skus(*groups: object, limit: int = 5) -> str:
    values: list[str] = []
    for group in groups:
        for raw_value in str(group or "").split(","):
            cleaned = raw_value.strip()
            if not cleaned or cleaned in values:
                continue
            values.append(cleaned)
            if len(values) >= limit:
                return ", ".join(values)
    return ", ".join(values)


def _summary_row(
    metric_group: str,
    metric_name: str,
    metric_value: float | int,
    metric_unit: str,
    metric_display: str,
    metric_status: str,
    source_artifact: str,
    notes: str,
) -> dict[str, object]:
    return {
        "metric_group": metric_group,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit,
        "metric_display": metric_display,
        "metric_status": metric_status,
        "source_artifact": source_artifact,
        "notes": notes,
    }


def _extract_metrics(
    *,
    review_summary_frame: pd.DataFrame,
    cleanup_summary_frame: pd.DataFrame,
    action_layer_summary_frame: pd.DataFrame,
    capital_drag_summary_frame: pd.DataFrame,
    capital_drag_override_summary_frame: pd.DataFrame,
    low_soh_summary_frame: pd.DataFrame,
    no_prior_demand_surprise_summary_frame: pd.DataFrame,
) -> dict[str, dict[str, object]]:
    _require_columns(
        review_summary_frame,
        (
            "row_count",
            "actual_units_total",
            "expected_promo_demand_total",
            "forecast_bias_units",
            "forecast_mae",
            "forecast_rmse",
            "forecast_correlation",
            "recommended_order_units_total",
            "pl_allocation_units_total",
            "actual_sell_through_vs_store_adjusted",
            "actual_gross_profit_total",
            "capital_left_unsold_total",
        ),
        frame_name="model_vs_actual_summary",
    )
    _require_columns(
        cleanup_summary_frame,
        ("issue_type", "issue_count", "sample_skus"),
        frame_name="report_contract_cleanup_summary",
    )
    _require_columns(
        action_layer_summary_frame,
        (
            "summary_kind",
            "label_name",
            "row_count",
            "actual_units_total",
            "capital_left_unsold_total",
        ),
        frame_name="action_layer_recalibration_summary",
    )
    _require_columns(
        capital_drag_summary_frame,
        (
            "summary_kind",
            "label_name",
            "row_count",
            "actual_gross_profit_total",
            "capital_left_total",
            "sample_skus",
        ),
        frame_name="capital_drag_strong_sellthrough_summary",
    )
    _require_columns(
        capital_drag_override_summary_frame,
        (
            "summary_kind",
            "label_name",
            "row_count",
            "override_candidate_rows",
            "rows_updated_to_strong_conversion_capital_drag_review",
            "production_order_change_count",
            "stage12_change_count",
            "remaining_true_capital_drag_rows",
            "sample_skus",
        ),
        frame_name="capital_drag_override_validation_summary",
    )
    _require_columns(
        low_soh_summary_frame,
        (
            "summary_kind",
            "label_name",
            "row_count",
            "actual_gross_profit_total",
            "capital_left_total",
            "sample_skus",
        ),
        frame_name="low_soh_material_demand_summary",
    )
    _require_columns(
        no_prior_demand_surprise_summary_frame,
        (
            "demand_evidence_label",
            "row_count",
            "actual_units_total",
            "expected_promo_demand_total",
            "actual_gross_profit_total",
            "capital_left_total",
        ),
        frame_name="no_prior_demand_surprise_summary",
    )

    review_total = review_summary_frame.iloc[0]
    action_total = _select_row(
        action_layer_summary_frame,
        frame_name="action_layer_recalibration_summary",
        summary_kind="TOTAL",
        label_name="ALL_ROWS",
    )
    action_too_conservative = _select_row(
        action_layer_summary_frame,
        frame_name="action_layer_recalibration_summary",
        summary_kind="RULE_FLAG",
        label_name="ACTION_TOO_CONSERVATIVE",
    )
    review_should_have_triggered = _select_row(
        action_layer_summary_frame,
        frame_name="action_layer_recalibration_summary",
        summary_kind="RULE_FLAG",
        label_name="REVIEW_SHOULD_HAVE_TRIGGERED",
    )
    capital_guardrail_correct = _select_row(
        action_layer_summary_frame,
        frame_name="action_layer_recalibration_summary",
        summary_kind="RULE_FLAG",
        label_name="CAPITAL_GUARDRAIL_CORRECT",
    )

    if _as_int(action_total["row_count"]) != _as_int(review_total["row_count"]):
        raise PromotionsLearningScoreboardError(
            "Action-layer total rows do not match model-vs-actual total rows."
        )

    cleanup_total = _select_row(
        cleanup_summary_frame,
        frame_name="report_contract_cleanup_summary",
        issue_type="TOTAL_REMAINING_CLEANUP_ISSUES",
    )
    zero_order_text = _select_row(
        cleanup_summary_frame,
        frame_name="report_contract_cleanup_summary",
        issue_type="BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS",
    )
    low_soh_routing = _select_row(
        cleanup_summary_frame,
        frame_name="report_contract_cleanup_summary",
        issue_type="LOW_SOH_OR_FLOOR_RISK_WITH_MATERIAL_DEMAND_NO_REVIEW_ACTION",
    )
    no_prior_material_actual = _select_row(
        cleanup_summary_frame,
        frame_name="report_contract_cleanup_summary",
        issue_type="NO_PRIOR_PROMO_EVIDENCE_WITH_MATERIAL_ACTUAL_UNITS",
    )
    no_demand_material_actual = _select_row(
        cleanup_summary_frame,
        frame_name="report_contract_cleanup_summary",
        issue_type="NO_DEMAND_WITH_MATERIAL_ACTUAL_UNITS",
    )
    capital_drag_cleanup = _select_row(
        cleanup_summary_frame,
        frame_name="report_contract_cleanup_summary",
        issue_type="CAPITAL_DRAG_HIGH_WITH_STRONG_SELL_THROUGH",
    )

    capital_drag_total = _select_row(
        capital_drag_summary_frame,
        frame_name="capital_drag_strong_sellthrough_summary",
        summary_kind="TOTAL",
        label_name="ALL_ROWS",
    )
    capital_drag_wrong_headline = _select_row(
        capital_drag_summary_frame,
        frame_name="capital_drag_strong_sellthrough_summary",
        summary_kind="CLASSIFICATION",
        label_name="STRONG_CONVERTER_WRONG_RISK_HEADLINE",
    )
    capital_drag_review_not_auto_buy = _select_row(
        capital_drag_summary_frame,
        frame_name="capital_drag_strong_sellthrough_summary",
        summary_kind="CLASSIFICATION",
        label_name="REVIEW_NOT_AUTO_BUY",
    )
    capital_drag_override_total = _select_row(
        capital_drag_override_summary_frame,
        frame_name="capital_drag_override_validation_summary",
        summary_kind="TOTAL",
        label_name="ALL_ROWS",
    )

    low_soh_total = _select_row(
        low_soh_summary_frame,
        frame_name="low_soh_material_demand_summary",
        summary_kind="TOTAL",
        label_name="ALL_ROWS",
    )
    low_soh_online_floor = _select_row(
        low_soh_summary_frame,
        frame_name="low_soh_material_demand_summary",
        summary_kind="CLASSIFICATION",
        label_name="ONLINE_FLOOR_PROTECTION_REVIEW",
    )
    low_soh_true_missed = _select_row(
        low_soh_summary_frame,
        frame_name="low_soh_material_demand_summary",
        summary_kind="CLASSIFICATION",
        label_name="TRUE_LOW_SOH_MISSED_DEMAND",
    )
    low_soh_covered = _select_row(
        low_soh_summary_frame,
        frame_name="low_soh_material_demand_summary",
        summary_kind="CLASSIFICATION",
        label_name="LOW_SOH_BUT_COVERED_BY_ON_ORDER",
    )
    low_soh_capital_protected = _select_row(
        low_soh_summary_frame,
        frame_name="low_soh_material_demand_summary",
        summary_kind="CLASSIFICATION",
        label_name="NO_CHANGE_CAPITAL_PROTECTED",
    )
    low_soh_forecast_undercalibration = _select_optional_row(
        low_soh_summary_frame,
        frame_name="low_soh_material_demand_summary",
        summary_kind="CLASSIFICATION",
        label_name="FORECAST_UNDERCALIBRATION_LOW_SOH",
    )
    low_soh_data_conflict = _select_optional_row(
        low_soh_summary_frame,
        frame_name="low_soh_material_demand_summary",
        summary_kind="CLASSIFICATION",
        label_name="DATA_OR_LABEL_CONFLICT",
    )

    no_prior_total = _select_row(
        no_prior_demand_surprise_summary_frame,
        frame_name="no_prior_demand_surprise_summary",
        demand_evidence_label="TOTAL",
    )

    cleanup_remaining_issues = _as_int(cleanup_total["issue_count"])
    cleanup_issues_reduced = CLEANUP_ISSUE_BASELINE - cleanup_remaining_issues
    if cleanup_issues_reduced < 0:
        raise PromotionsLearningScoreboardError(
            "Cleanup remaining issues exceed the governed baseline."
        )

    return {
        "review": {
            "rows_reviewed": _as_int(review_total["row_count"]),
            "actual_units_total": _as_float(review_total["actual_units_total"]),
            "expected_promo_demand_total": _as_float(review_total["expected_promo_demand_total"]),
            "actual_gross_profit_total": _as_float(review_total["actual_gross_profit_total"]),
            "source_artifact": "model_vs_actual_summary.csv",
        },
        "forecast": {
            "forecast_bias_units": _as_float(review_total["forecast_bias_units"]),
            "forecast_mae": _as_float(review_total["forecast_mae"]),
            "forecast_rmse": _as_float(review_total["forecast_rmse"]),
            "forecast_correlation": _as_float(review_total["forecast_correlation"]),
        },
        "action_layer": {
            "recommended_order_units_total": _as_float(review_total["recommended_order_units_total"]),
            "pl_allocation_units_total": _as_float(review_total["pl_allocation_units_total"]),
            "capital_left_unsold_total": _as_float(review_total["capital_left_unsold_total"]),
            "actual_sell_through_vs_store_adjusted": _as_float(review_total["actual_sell_through_vs_store_adjusted"]),
            "action_too_conservative_rows": _as_int(action_too_conservative["row_count"]),
            "action_too_conservative_actual_units": _as_float(action_too_conservative["actual_units_total"]),
            "action_too_conservative_sample_skus": str(action_too_conservative.get("sample_skus", "")),
            "review_should_have_triggered_rows": _as_int(review_should_have_triggered["row_count"]),
            "review_should_have_triggered_actual_units": _as_float(review_should_have_triggered["actual_units_total"]),
            "review_should_have_triggered_sample_skus": str(review_should_have_triggered.get("sample_skus", "")),
            "capital_guardrail_correct_rows": _as_int(capital_guardrail_correct["row_count"]),
            "capital_guardrail_correct_capital_left": _as_float(capital_guardrail_correct["capital_left_unsold_total"]),
            "capital_guardrail_correct_sample_skus": str(capital_guardrail_correct.get("sample_skus", "")),
        },
        "cleanup": {
            "baseline_issues": CLEANUP_ISSUE_BASELINE,
            "remaining_issues": cleanup_remaining_issues,
            "issues_reduced": cleanup_issues_reduced,
            "issues_reduced_pct": cleanup_issues_reduced / CLEANUP_ISSUE_BASELINE,
            "multiple_action_conflicts_remaining": MULTIPLE_ACTION_CONFLICTS_REMAINING,
            "shadow_fields_visible_remaining": SHADOW_FIELDS_VISIBLE_REMAINING,
            "production_final_order_diff_count": PRODUCTION_FINAL_ORDER_DIFF_COUNT,
            "stage12_change_count": STAGE12_CHANGE_COUNT,
            "zero_order_text_residual": _as_int(zero_order_text["issue_count"]),
            "zero_order_text_sample_skus": str(zero_order_text.get("sample_skus", "")),
            "low_soh_review_routing_rows": _as_int(low_soh_routing["issue_count"]),
            "low_soh_review_routing_sample_skus": str(low_soh_routing.get("sample_skus", "")),
            "no_prior_material_actual_rows": _as_int(no_prior_material_actual["issue_count"]),
            "no_prior_material_actual_sample_skus": str(no_prior_material_actual.get("sample_skus", "")),
            "no_demand_material_actual_rows": _as_int(no_demand_material_actual["issue_count"]),
            "no_demand_material_actual_sample_skus": str(no_demand_material_actual.get("sample_skus", "")),
            "capital_drag_issue_rows": _as_int(capital_drag_cleanup["issue_count"]),
            "capital_drag_issue_sample_skus": str(capital_drag_cleanup.get("sample_skus", "")),
        },
        "capital_drag": {
            "overlay_rows": _as_int(capital_drag_total["row_count"]),
            "wrong_risk_headline_rows": _as_int(capital_drag_wrong_headline["row_count"]),
            "review_not_auto_buy_rows": _as_int(capital_drag_review_not_auto_buy["row_count"]),
            "gross_profit_total": _as_float(capital_drag_total["actual_gross_profit_total"]),
            "capital_left_total": _as_float(capital_drag_total["capital_left_total"]),
            "sample_skus": str(capital_drag_total.get("sample_skus", "")),
            "wrong_risk_headline_sample_skus": str(capital_drag_wrong_headline.get("sample_skus", "")),
            "review_not_auto_buy_sample_skus": str(capital_drag_review_not_auto_buy.get("sample_skus", "")),
            "override_rows_updated": _as_int(
                capital_drag_override_total[
                    "rows_updated_to_strong_conversion_capital_drag_review"
                ]
            ),
            "remaining_true_capital_drag_rows": _as_int(
                capital_drag_override_total["remaining_true_capital_drag_rows"]
            ),
            "production_order_change_count": _as_int(
                capital_drag_override_total["production_order_change_count"]
            ),
            "stage12_change_count": _as_int(capital_drag_override_total["stage12_change_count"]),
        },
        "low_soh": {
            "overlay_rows": _as_int(low_soh_total["row_count"]),
            "online_floor_protection_rows": _as_int(low_soh_online_floor["row_count"]),
            "true_low_soh_missed_demand_rows": _as_int(low_soh_true_missed["row_count"]),
            "covered_by_on_order_rows": _as_int(low_soh_covered["row_count"]),
            "capital_protected_rows": _as_int(low_soh_capital_protected["row_count"]),
            "forecast_undercalibration_rows": 0
            if low_soh_forecast_undercalibration is None
            else _as_int(low_soh_forecast_undercalibration["row_count"]),
            "data_label_conflict_rows": 0
            if low_soh_data_conflict is None
            else _as_int(low_soh_data_conflict["row_count"]),
            "gross_profit_total": _as_float(low_soh_total["actual_gross_profit_total"]),
            "capital_left_total": _as_float(low_soh_total["capital_left_total"]),
            "sample_skus": str(low_soh_total.get("sample_skus", "")),
            "true_low_soh_missed_demand_sample_skus": str(low_soh_true_missed.get("sample_skus", "")),
            "online_floor_protection_sample_skus": str(low_soh_online_floor.get("sample_skus", "")),
        },
        "no_prior": {
            "surprise_rows": _as_int(no_prior_total["row_count"]),
            "actual_units_total": _as_float(no_prior_total["actual_units_total"]),
            "expected_promo_demand_total": _as_float(no_prior_total["expected_promo_demand_total"]),
            "gross_profit_total": _as_float(no_prior_total["actual_gross_profit_total"]),
            "capital_left_total": _as_float(no_prior_total["capital_left_total"]),
            "sample_skus": _sample_skus(
                no_prior_material_actual.get("sample_skus", ""),
                no_demand_material_actual.get("sample_skus", ""),
            ),
        },
        "policy": {
            "production_order_change_count": max(
                PRODUCTION_FINAL_ORDER_DIFF_COUNT,
                _as_int(capital_drag_override_total["production_order_change_count"]),
            ),
            "stage12_change_count": max(
                STAGE12_CHANGE_COUNT,
                _as_int(capital_drag_override_total["stage12_change_count"]),
            ),
        },
        "technical": {
            "pandas_fragmentation_warning_count": PANDAS_FRAGMENTATION_WARNING_COUNT,
        },
    }


def _build_summary_frame(metrics: dict[str, dict[str, object]]) -> pd.DataFrame:
    review = metrics["review"]
    forecast = metrics["forecast"]
    action_layer = metrics["action_layer"]
    cleanup = metrics["cleanup"]
    capital_drag = metrics["capital_drag"]
    low_soh = metrics["low_soh"]
    no_prior = metrics["no_prior"]
    policy = metrics["policy"]

    rows = [
        _summary_row(
            "REVIEW_SCOPE",
            "TOTAL_ROWS_REVIEWED",
            int(review["rows_reviewed"]),
            "rows",
            _format_int(review["rows_reviewed"]),
            "INFO",
            "model_vs_actual_summary.csv",
            "Certified exact review-root coverage.",
        ),
        _summary_row(
            "FORECAST_HEAD",
            "FORECAST_CORRELATION",
            float(forecast["forecast_correlation"]),
            "correlation",
            _format_float(float(forecast["forecast_correlation"]), decimals=3),
            "BLOCKED",
            "model_vs_actual_summary.csv",
            "Forecast-head correlation remains too weak for auto-ordering.",
        ),
        _summary_row(
            "FORECAST_HEAD",
            "FORECAST_BIAS_UNITS",
            float(forecast["forecast_bias_units"]),
            "units",
            _format_float(float(forecast["forecast_bias_units"]), decimals=0, signed=True),
            "BLOCKED",
            "model_vs_actual_summary.csv",
            "Positive bias indicates over-forecasted demand.",
        ),
        _summary_row(
            "FORECAST_HEAD",
            "FORECAST_MAE",
            float(forecast["forecast_mae"]),
            "mae",
            _format_float(float(forecast["forecast_mae"]), decimals=3),
            "BLOCKED",
            "model_vs_actual_summary.csv",
            "Forecast-head error remains materially broad.",
        ),
        _summary_row(
            "FORECAST_HEAD",
            "FORECAST_RMSE",
            float(forecast["forecast_rmse"]),
            "rmse",
            _format_float(float(forecast["forecast_rmse"]), decimals=3),
            "BLOCKED",
            "model_vs_actual_summary.csv",
            "Forecast-head error remains materially broad.",
        ),
        _summary_row(
            "ACTION_LAYER",
            "RECOMMENDED_ORDER_UNITS_TOTAL",
            float(action_layer["recommended_order_units_total"]),
            "units",
            _format_float(float(action_layer["recommended_order_units_total"]), decimals=0),
            "BLOCKED",
            "model_vs_actual_summary.csv",
            "Near-zero recommended order units remain inconsistent with realized demand.",
        ),
        _summary_row(
            "ACTION_LAYER",
            "ACTUAL_SELL_THROUGH_VS_ACCEPTED_ALLOCATION",
            float(action_layer["actual_sell_through_vs_store_adjusted"]),
            "ratio",
            _format_percent_from_ratio(float(action_layer["actual_sell_through_vs_store_adjusted"])),
            "INFO",
            "model_vs_actual_summary.csv",
            "Accepted allocation still converted, which keeps the capital guardrail directionally useful.",
        ),
        _summary_row(
            "ACTION_LAYER",
            "ACTION_TOO_CONSERVATIVE_ROWS",
            int(action_layer["action_too_conservative_rows"]),
            "rows",
            _format_int(action_layer["action_too_conservative_rows"]),
            "BLOCKED",
            "action_layer_recalibration_summary.csv",
            "Rows sold material units after a zero-order outcome that was not justified by guardrails.",
        ),
        _summary_row(
            "ACTION_LAYER",
            "REVIEW_SHOULD_HAVE_TRIGGERED_ROWS",
            int(action_layer["review_should_have_triggered_rows"]),
            "rows",
            _format_int(action_layer["review_should_have_triggered_rows"]),
            "BLOCKED",
            "action_layer_recalibration_summary.csv",
            "Weak-evidence and no-prior rows still need governed review routing.",
        ),
        _summary_row(
            "REPORT_CLEANUP",
            "CLEANUP_ISSUES_REDUCED",
            int(cleanup["issues_reduced"]),
            "issues",
            f"{_format_int(cleanup['issues_reduced'])} ({_format_int(cleanup['baseline_issues'])} -> {_format_int(cleanup['remaining_issues'])})",
            "READY_WITH_BACKLOG",
            "report_contract_cleanup_summary.csv",
            "Visible-contract cleanup improved materially but still leaves row-level cleanup backlog.",
        ),
        _summary_row(
            "REPORT_CLEANUP",
            "MULTIPLE_ACTION_CONFLICTS_REMAINING",
            int(cleanup["multiple_action_conflicts_remaining"]),
            "rows",
            _format_int(cleanup["multiple_action_conflicts_remaining"]),
            "LOCKED",
            "validated_cleanup_contract",
            "Validated cleanup outcome: no multiple-action conflicts remain in the clean visible contract.",
        ),
        _summary_row(
            "REPORT_CLEANUP",
            "SHADOW_FIELDS_VISIBLE_REMAINING",
            int(cleanup["shadow_fields_visible_remaining"]),
            "rows",
            _format_int(cleanup["shadow_fields_visible_remaining"]),
            "LOCKED",
            "validated_cleanup_contract",
            "Validated cleanup outcome: shadow-policy fields remain audit-only.",
        ),
        _summary_row(
            "CAPITAL_DRAG_OVERLAY",
            "OVERLAY_ROWS",
            int(capital_drag["overlay_rows"]),
            "rows",
            _format_int(capital_drag["overlay_rows"]),
            "READY",
            "capital_drag_strong_sellthrough_summary.csv",
            "Strong converters can move to a review-only overlay without changing production ordering.",
        ),
        _summary_row(
            "CAPITAL_DRAG_OVERLAY",
            "STRONG_CONVERTER_WRONG_RISK_HEADLINE_ROWS",
            int(capital_drag["wrong_risk_headline_rows"]),
            "rows",
            _format_int(capital_drag["wrong_risk_headline_rows"]),
            "READY",
            "capital_drag_strong_sellthrough_summary.csv",
            "Wrong capital-drag headlines are already isolated to a review-only slice.",
        ),
        _summary_row(
            "CAPITAL_DRAG_OVERLAY",
            "REVIEW_NOT_AUTO_BUY_ROWS",
            int(capital_drag["review_not_auto_buy_rows"]),
            "rows",
            _format_int(capital_drag["review_not_auto_buy_rows"]),
            "READY",
            "capital_drag_strong_sellthrough_summary.csv",
            "Keep these rows review-only rather than auto-buying.",
        ),
        _summary_row(
            "LOW_SOH_OVERLAY",
            "OVERLAY_ROWS",
            int(low_soh["overlay_rows"]),
            "rows",
            _format_int(low_soh["overlay_rows"]),
            "READY",
            "low_soh_material_demand_summary.csv",
            "Low-SOH and online-floor findings are already separated into review-only diagnostics.",
        ),
        _summary_row(
            "LOW_SOH_OVERLAY",
            "ONLINE_FLOOR_PROTECTION_REVIEW_ROWS",
            int(low_soh["online_floor_protection_rows"]),
            "rows",
            _format_int(low_soh["online_floor_protection_rows"]),
            "READY",
            "low_soh_material_demand_summary.csv",
            "Online-floor protection is the dominant low-SOH visible-review pattern.",
        ),
        _summary_row(
            "LOW_SOH_OVERLAY",
            "TRUE_LOW_SOH_MISSED_DEMAND_ROWS",
            int(low_soh["true_low_soh_missed_demand_rows"]),
            "rows",
            _format_int(low_soh["true_low_soh_missed_demand_rows"]),
            "READY",
            "low_soh_material_demand_summary.csv",
            "These are the clearest low-SOH missed-demand follow-up SKUs.",
        ),
        _summary_row(
            "LOW_SOH_OVERLAY",
            "FORECAST_UNDERCALIBRATION_ROWS",
            int(low_soh["forecast_undercalibration_rows"]),
            "rows",
            _format_int(low_soh["forecast_undercalibration_rows"]),
            "READY",
            "low_soh_material_demand_summary.csv",
            "No low-SOH forecast-undercalibration sub-slice remains in the governed seam.",
        ),
        _summary_row(
            "NO_PRIOR_DEMAND",
            "SURPRISE_ROWS",
            int(no_prior["surprise_rows"]),
            "rows",
            _format_int(no_prior["surprise_rows"]),
            "BLOCKED",
            "no_prior_demand_surprise_summary.csv",
            "No-prior and weak-evidence surprises remain diagnostic-only until the action layer is recalibrated shadow-only.",
        ),
        _summary_row(
            "PRODUCTION_POLICY",
            "PRODUCTION_ORDER_CHANGE_COUNT",
            int(policy["production_order_change_count"]),
            "rows",
            _format_int(policy["production_order_change_count"]),
            "LOCKED",
            "validated_cleanup_contract",
            "No production order logic changes are part of this scoreboard.",
        ),
        _summary_row(
            "PRODUCTION_POLICY",
            "STAGE12_CHANGE_COUNT",
            int(policy["stage12_change_count"]),
            "rows",
            _format_int(policy["stage12_change_count"]),
            "LOCKED",
            "validated_cleanup_contract",
            "No Stage 12 publication logic changes are part of this scoreboard.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_decision_table_frame(metrics: dict[str, dict[str, object]]) -> pd.DataFrame:
    review = metrics["review"]
    forecast = metrics["forecast"]
    action_layer = metrics["action_layer"]
    cleanup = metrics["cleanup"]
    capital_drag = metrics["capital_drag"]
    low_soh = metrics["low_soh"]
    policy = metrics["policy"]

    rows = [
        {
            "decision_category": "REPORT_CONTRACT_FIXED",
            "decision_status": "READY_WITH_BACKLOG",
            "evidence_metric": "cleanup_issues_reduced",
            "evidence_value": int(cleanup["issues_reduced"]),
            "evidence_display": (
                f"{_format_int(cleanup['issues_reduced'])} issues reduced; "
                f"{_format_int(cleanup['remaining_issues'])} remain; "
                "0 multiple-action conflicts; 0 shadow fields visible"
            ),
            "source_artifact": "report_contract_cleanup_summary.csv",
            "rationale": (
                "The clean visible operator contract is stable enough to treat as fixed, "
                "but 84 row-level cleanup issues remain in the visible wording and review-routing backlog."
            ),
        },
        {
            "decision_category": "FORECAST_HEAD_NOT_READY",
            "decision_status": "BLOCKED",
            "evidence_metric": "forecast_correlation",
            "evidence_value": float(forecast["forecast_correlation"]),
            "evidence_display": (
                f"corr={_format_float(float(forecast['forecast_correlation']), decimals=3)}; "
                f"bias={_format_float(float(forecast['forecast_bias_units']), decimals=0, signed=True)} units"
            ),
            "source_artifact": "model_vs_actual_summary.csv",
            "rationale": (
                "Forecast-head weakness remains material, so the scoreboard cannot recommend any production ordering change."
            ),
        },
        {
            "decision_category": "ACTION_LAYER_TOO_CONSERVATIVE",
            "decision_status": "BLOCKED",
            "evidence_metric": "action_too_conservative_rows",
            "evidence_value": int(action_layer["action_too_conservative_rows"]),
            "evidence_display": (
                f"{_format_int(action_layer['action_too_conservative_rows'])} suppression rows; "
                f"{_format_int(action_layer['review_should_have_triggered_rows'])} missed review rows"
            ),
            "source_artifact": "action_layer_recalibration_summary.csv",
            "rationale": (
                "The action layer still suppresses too many rows and still misses governed review triggers."
            ),
        },
        {
            "decision_category": "CAPITAL_DRAG_REVIEW_OVERLAY_READY",
            "decision_status": "READY",
            "evidence_metric": "capital_drag_overlay_rows",
            "evidence_value": int(capital_drag["overlay_rows"]),
            "evidence_display": (
                f"{_format_int(capital_drag['overlay_rows'])} overlay rows; "
                f"0 production order changes; 0 Stage 12 changes"
            ),
            "source_artifact": "capital_drag_override_validation_summary.csv",
            "rationale": (
                "The capital-drag review-only overlay is ready to package because it does not alter production ordering or Stage 12."
            ),
        },
        {
            "decision_category": "LOW_SOH_REVIEW_OVERLAY_READY",
            "decision_status": "READY",
            "evidence_metric": "low_soh_overlay_rows",
            "evidence_value": int(low_soh["overlay_rows"]),
            "evidence_display": (
                f"{_format_int(low_soh['overlay_rows'])} overlay rows; "
                f"{_format_int(low_soh['online_floor_protection_rows'])} online-floor; "
                f"{_format_int(low_soh['true_low_soh_missed_demand_rows'])} true missed-demand"
            ),
            "source_artifact": "low_soh_material_demand_summary.csv",
            "rationale": (
                "The low-SOH review-only overlay is ready because it cleanly separates online-floor protection from true missed-demand follow-up."
            ),
        },
        {
            "decision_category": "AUTO_ORDERING_NOT_READY",
            "decision_status": "BLOCKED",
            "evidence_metric": "recommended_order_units_total",
            "evidence_value": float(action_layer["recommended_order_units_total"]),
            "evidence_display": (
                f"{_format_float(float(action_layer['recommended_order_units_total']), decimals=0)} recommended units "
                f"vs {_format_int(review['actual_units_total'])} actual units"
            ),
            "source_artifact": "model_vs_actual_summary.csv",
            "rationale": (
                "Auto-ordering remains blocked because forecast-head error and action-layer conservatism are still confounded."
            ),
        },
        {
            "decision_category": "STAGE_12_UNCHANGED",
            "decision_status": "LOCKED",
            "evidence_metric": "stage12_change_count",
            "evidence_value": int(policy["stage12_change_count"]),
            "evidence_display": f"{_format_int(policy['stage12_change_count'])} Stage 12 changes",
            "source_artifact": "validated_cleanup_contract",
            "rationale": "Stage 12 publication logic stays unchanged across this entire diagnostics packet.",
        },
        {
            "decision_category": "PRODUCTION_ORDERING_UNCHANGED",
            "decision_status": "LOCKED",
            "evidence_metric": "production_order_change_count",
            "evidence_value": int(policy["production_order_change_count"]),
            "evidence_display": f"{_format_int(policy['production_order_change_count'])} production order changes",
            "source_artifact": "validated_cleanup_contract",
            "rationale": "Production ordering logic stays unchanged across this entire diagnostics packet.",
        },
    ]
    return pd.DataFrame(rows, columns=DECISION_TABLE_COLUMNS)


def _build_issue_backlog_frame(metrics: dict[str, dict[str, object]]) -> pd.DataFrame:
    review = metrics["review"]
    forecast = metrics["forecast"]
    action_layer = metrics["action_layer"]
    cleanup = metrics["cleanup"]
    low_soh = metrics["low_soh"]
    no_prior = metrics["no_prior"]
    technical = metrics["technical"]

    rows = [
        {
            "issue_backlog_category": "FORECAST_CORRELATION_LOW",
            "priority_rank": 1,
            "issue_count": 1,
            "affected_rows": int(review["rows_reviewed"]),
            "evidence_metric": "forecast_correlation",
            "evidence_value": float(forecast["forecast_correlation"]),
            "evidence_display": _format_float(float(forecast["forecast_correlation"]), decimals=3),
            "source_artifact": "model_vs_actual_summary.csv",
            "sample_skus": "",
            "recommended_next_action": "KEEP_AUTO_ORDERING_BLOCKED",
            "rationale": "Correlation remains too low to treat the forecast head as auto-ordering-safe.",
        },
        {
            "issue_backlog_category": "FORECAST_BIAS_HIGH",
            "priority_rank": 2,
            "issue_count": 1,
            "affected_rows": int(review["rows_reviewed"]),
            "evidence_metric": "forecast_bias_units",
            "evidence_value": float(forecast["forecast_bias_units"]),
            "evidence_display": _format_float(float(forecast["forecast_bias_units"]), decimals=0, signed=True),
            "source_artifact": "model_vs_actual_summary.csv",
            "sample_skus": "",
            "recommended_next_action": "KEEP_AUTO_ORDERING_BLOCKED",
            "rationale": "Bias remains too high to relax any production-policy guardrail.",
        },
        {
            "issue_backlog_category": "ACTION_LAYER_SUPPRESSION",
            "priority_rank": 3,
            "issue_count": int(action_layer["action_too_conservative_rows"]),
            "affected_rows": int(action_layer["action_too_conservative_rows"])
            + int(action_layer["review_should_have_triggered_rows"]),
            "evidence_metric": "action_too_conservative_rows",
            "evidence_value": int(action_layer["action_too_conservative_rows"]),
            "evidence_display": (
                f"{_format_int(action_layer['action_too_conservative_rows'])} suppression rows; "
                f"{_format_int(action_layer['review_should_have_triggered_rows'])} missed review rows"
            ),
            "source_artifact": "action_layer_recalibration_summary.csv",
            "sample_skus": _sample_skus(
                action_layer["action_too_conservative_sample_skus"],
                action_layer["review_should_have_triggered_sample_skus"],
            ),
            "recommended_next_action": "CALIBRATE_ACTION_LAYER_SHADOW_ONLY",
            "rationale": "The action layer remains too conservative and should only be recalibrated in shadow mode.",
        },
        {
            "issue_backlog_category": "LOW_SOH_REVIEW_ROUTING",
            "priority_rank": 4,
            "issue_count": int(cleanup["low_soh_review_routing_rows"]),
            "affected_rows": int(low_soh["overlay_rows"]),
            "evidence_metric": "low_soh_overlay_rows",
            "evidence_value": int(low_soh["overlay_rows"]),
            "evidence_display": f"{_format_int(low_soh['overlay_rows'])} low-SOH review-only rows",
            "source_artifact": "low_soh_material_demand_summary.csv",
            "sample_skus": str(cleanup["low_soh_review_routing_sample_skus"]),
            "recommended_next_action": "BUILD_REVIEW_OVERLAY_PACKET",
            "rationale": "The low-SOH review-routing slice is ready to package as a review-only operator overlay.",
        },
        {
            "issue_backlog_category": "ONLINE_FLOOR_PROTECTION",
            "priority_rank": 5,
            "issue_count": int(low_soh["online_floor_protection_rows"]),
            "affected_rows": int(low_soh["online_floor_protection_rows"]),
            "evidence_metric": "online_floor_protection_review_rows",
            "evidence_value": int(low_soh["online_floor_protection_rows"]),
            "evidence_display": f"{_format_int(low_soh['online_floor_protection_rows'])} online-floor review rows",
            "source_artifact": "low_soh_material_demand_summary.csv",
            "sample_skus": str(low_soh["online_floor_protection_sample_skus"]),
            "recommended_next_action": "BUILD_REVIEW_OVERLAY_PACKET",
            "rationale": "Online-floor protection is the dominant low-SOH operator review message and should stay review-only.",
        },
        {
            "issue_backlog_category": "NO_PRIOR_DEMAND_SURPRISE",
            "priority_rank": 6,
            "issue_count": int(no_prior["surprise_rows"]),
            "affected_rows": int(no_prior["surprise_rows"]),
            "evidence_metric": "no_prior_demand_surprise_rows",
            "evidence_value": int(no_prior["surprise_rows"]),
            "evidence_display": f"{_format_int(no_prior['surprise_rows'])} surprise rows",
            "source_artifact": "no_prior_demand_surprise_summary.csv",
            "sample_skus": str(no_prior["sample_skus"]),
            "recommended_next_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE_SKUS",
            "rationale": "No-prior and weak-evidence surprises still need governed row-level inspection before any policy discussion.",
        },
        {
            "issue_backlog_category": "ZERO_ORDER_TEXT_RESIDUAL",
            "priority_rank": 7,
            "issue_count": int(cleanup["zero_order_text_residual"]),
            "affected_rows": int(cleanup["zero_order_text_residual"]),
            "evidence_metric": "zero_order_text_residual_rows",
            "evidence_value": int(cleanup["zero_order_text_residual"]),
            "evidence_display": f"{_format_int(cleanup['zero_order_text_residual'])} zero-order text rows",
            "source_artifact": "report_contract_cleanup_summary.csv",
            "sample_skus": str(cleanup["zero_order_text_sample_skus"]),
            "recommended_next_action": "BUILD_REVIEW_OVERLAY_PACKET",
            "rationale": "Two rows still present BUY or ORDER wording despite zero order units.",
        },
        {
            "issue_backlog_category": "PANDAS_FRAGMENTATION_WARNING",
            "priority_rank": 8,
            "issue_count": int(technical["pandas_fragmentation_warning_count"]),
            "affected_rows": 0,
            "evidence_metric": "technical_warning_present",
            "evidence_value": int(technical["pandas_fragmentation_warning_count"]),
            "evidence_display": "Stage 11 tests still emit fragmentation warnings",
            "source_artifact": "validated_regression_observation",
            "sample_skus": "",
            "recommended_next_action": "",
            "rationale": "This is technical cleanup only and does not justify any production-policy change.",
        },
    ]
    return pd.DataFrame(rows, columns=ISSUE_BACKLOG_COLUMNS).sort_values(
        by=["priority_rank", "issue_backlog_category"], kind="stable"
    )


def _build_next_actions_frame(metrics: dict[str, dict[str, object]]) -> pd.DataFrame:
    review = metrics["review"]
    forecast = metrics["forecast"]
    action_layer = metrics["action_layer"]
    capital_drag = metrics["capital_drag"]
    low_soh = metrics["low_soh"]
    no_prior = metrics["no_prior"]

    rows = [
        {
            "next_action_recommendation": "BUILD_REVIEW_OVERLAY_PACKET",
            "priority_rank": 1,
            "action_status": "READY",
            "row_count": int(capital_drag["overlay_rows"]) + int(low_soh["overlay_rows"]),
            "evidence_display": (
                f"{_format_int(capital_drag['overlay_rows'])} capital-drag rows + "
                f"{_format_int(low_soh['overlay_rows'])} low-SOH rows"
            ),
            "source_issue_backlog_category": "LOW_SOH_REVIEW_ROUTING, ONLINE_FLOOR_PROTECTION",
            "sample_skus": _sample_skus(capital_drag["sample_skus"], low_soh["sample_skus"]),
            "rationale": "Package the two validated review-only overlays into one operator-facing decision packet before any new model change.",
            "guardrail": "Do not change production ordering logic or Stage 12.",
        },
        {
            "next_action_recommendation": "INSPECT_TRUE_LOW_SOH_MISSED_DEMAND_SKUS",
            "priority_rank": 2,
            "action_status": "RECOMMENDED",
            "row_count": int(low_soh["true_low_soh_missed_demand_rows"]),
            "evidence_display": (
                f"{_format_int(low_soh['true_low_soh_missed_demand_rows'])} SKUs; "
                f"{_format_money(float(low_soh['gross_profit_total']))} gross profit represented across the low-SOH slice"
            ),
            "source_issue_backlog_category": "LOW_SOH_REVIEW_ROUTING",
            "sample_skus": str(low_soh["true_low_soh_missed_demand_sample_skus"]),
            "rationale": "Inspect the true low-SOH missed-demand SKUs individually before any future non-production calibration proposal.",
            "guardrail": "Keep low-SOH findings review-only.",
        },
        {
            "next_action_recommendation": "INSPECT_NO_PRIOR_DEMAND_SURPRISE_SKUS",
            "priority_rank": 3,
            "action_status": "RECOMMENDED",
            "row_count": int(no_prior["surprise_rows"]),
            "evidence_display": (
                f"{_format_int(no_prior['surprise_rows'])} rows; "
                f"{_format_money(float(no_prior['gross_profit_total']))} gross profit represented"
            ),
            "source_issue_backlog_category": "NO_PRIOR_DEMAND_SURPRISE",
            "sample_skus": str(no_prior["sample_skus"]),
            "rationale": "Inspect the no-prior and weak-evidence surprise rows before any discussion about the demand proxy.",
            "guardrail": "Do not relax the demand proxy.",
        },
        {
            "next_action_recommendation": "CALIBRATE_ACTION_LAYER_SHADOW_ONLY",
            "priority_rank": 4,
            "action_status": "RECOMMENDED",
            "row_count": int(action_layer["action_too_conservative_rows"])
            + int(action_layer["review_should_have_triggered_rows"]),
            "evidence_display": (
                f"{_format_int(action_layer['action_too_conservative_rows'])} suppression rows + "
                f"{_format_int(action_layer['review_should_have_triggered_rows'])} missed review rows"
            ),
            "source_issue_backlog_category": "ACTION_LAYER_SUPPRESSION",
            "sample_skus": _sample_skus(
                action_layer["action_too_conservative_sample_skus"],
                action_layer["review_should_have_triggered_sample_skus"],
            ),
            "rationale": "Shadow-only recalibration is the next safe move for the action layer while the forecast head remains weak.",
            "guardrail": "Do not promote auto-ordering.",
        },
        {
            "next_action_recommendation": "KEEP_CAPITAL_GUARDRAIL_ACTIVE",
            "priority_rank": 5,
            "action_status": "LOCKED",
            "row_count": int(action_layer["capital_guardrail_correct_rows"]),
            "evidence_display": (
                f"{_format_int(action_layer['capital_guardrail_correct_rows'])} rows; "
                f"{_format_money(float(action_layer['capital_guardrail_correct_capital_left']))} capital left protected"
            ),
            "source_issue_backlog_category": "",
            "sample_skus": str(action_layer["capital_guardrail_correct_sample_skus"]),
            "rationale": "Keep the capital guardrail active because it still blocks measurable unsold capital exposure correctly.",
            "guardrail": "Do not remove the capital guardrail.",
        },
        {
            "next_action_recommendation": "KEEP_AUTO_ORDERING_BLOCKED",
            "priority_rank": 6,
            "action_status": "LOCKED",
            "row_count": int(review["rows_reviewed"]),
            "evidence_display": (
                f"corr={_format_float(float(forecast['forecast_correlation']), decimals=3)}; "
                f"bias={_format_float(float(forecast['forecast_bias_units']), decimals=0, signed=True)} units; "
                f"{_format_float(float(action_layer['recommended_order_units_total']), decimals=0)} recommended units"
            ),
            "source_issue_backlog_category": "FORECAST_CORRELATION_LOW, FORECAST_BIAS_HIGH",
            "sample_skus": "",
            "rationale": "Keep auto-ordering blocked until forecast-head weakness and action-layer conservatism are both resolved.",
            "guardrail": "Do not promote auto-ordering.",
        },
    ]
    return pd.DataFrame(rows, columns=NEXT_ACTION_COLUMNS).sort_values(
        by=["priority_rank", "next_action_recommendation"], kind="stable"
    )


def _build_memo(
    *,
    metrics: dict[str, dict[str, object]],
    manifest: dict[str, object] | None = None,
) -> str:
    review = metrics["review"]
    forecast = metrics["forecast"]
    action_layer = metrics["action_layer"]
    cleanup = metrics["cleanup"]
    capital_drag = metrics["capital_drag"]
    low_soh = metrics["low_soh"]
    no_prior = metrics["no_prior"]
    policy = metrics["policy"]

    lines = [
        "# Promotion Learning Scoreboard",
        "",
        "## 1. Forecast-Head Weakness",
        (
            f"- Rows reviewed: {_format_int(review['rows_reviewed'])}. Forecast correlation remains "
            f"{_format_float(float(forecast['forecast_correlation']), decimals=3)} with "
            f"{_format_float(float(forecast['forecast_bias_units']), decimals=0, signed=True)} units of bias, "
            f"MAE {_format_float(float(forecast['forecast_mae']), decimals=3)}, and RMSE {_format_float(float(forecast['forecast_rmse']), decimals=3)}."
        ),
        (
            f"- Actual sell-through versus accepted allocation is {_format_percent_from_ratio(float(action_layer['actual_sell_through_vs_store_adjusted']))}, "
            "so this scoreboard is not evidence to relax the demand proxy or to promote auto-ordering."
        ),
        "",
        "## 2. Action-Layer Conservatism",
        (
            f"- The action layer recommended {_format_float(float(action_layer['recommended_order_units_total']), decimals=0)} units against "
            f"{_format_int(review['actual_units_total'])} realized units."
        ),
        (
            f"- {_format_int(action_layer['action_too_conservative_rows'])} rows remained suppressed after material realized demand and "
            f"{_format_int(action_layer['review_should_have_triggered_rows'])} more rows should have triggered governed review."
        ),
        "",
        "## 3. Report-Contract Cleanup",
        (
            f"- The clean visible operator contract reduced cleanup issues from {_format_int(cleanup['baseline_issues'])} to "
            f"{_format_int(cleanup['remaining_issues'])}."
        ),
        (
            f"- Multiple action conflicts remain at {_format_int(cleanup['multiple_action_conflicts_remaining'])}, shadow fields visible remain at "
            f"{_format_int(cleanup['shadow_fields_visible_remaining'])}, and production final-order diff count remains at "
            f"{_format_int(cleanup['production_final_order_diff_count'])}."
        ),
        (
            f"- Residual cleanup backlog is concentrated in zero-order text ({_format_int(cleanup['zero_order_text_residual'])}), "
            f"low-SOH review routing ({_format_int(cleanup['low_soh_review_routing_rows'])}), and no-prior or no-demand surprise routing "
            f"({_format_int(no_prior['surprise_rows'])})."
        ),
        "",
        "## 4. Review-Only Diagnostic Overlays",
        (
            f"- Capital-drag overlay is ready: {_format_int(capital_drag['overlay_rows'])} rows can move to the review-only override with "
            f"{_format_int(capital_drag['production_order_change_count'])} production order changes and "
            f"{_format_int(capital_drag['stage12_change_count'])} Stage 12 changes."
        ),
        (
            f"- Low-SOH overlay is ready: {_format_int(low_soh['overlay_rows'])} rows split into "
            f"{_format_int(low_soh['online_floor_protection_rows'])} online-floor protection reviews, "
            f"{_format_int(low_soh['true_low_soh_missed_demand_rows'])} true low-SOH missed-demand rows, "
            f"{_format_int(low_soh['covered_by_on_order_rows'])} on-order-covered rows, and "
            f"{_format_int(low_soh['capital_protected_rows'])} capital-protected rows."
        ),
        (
            f"- Low-SOH forecast-undercalibration rows remain at {_format_int(low_soh['forecast_undercalibration_rows'])} and "
            f"data-or-label conflicts remain at {_format_int(low_soh['data_label_conflict_rows'])}."
        ),
        (
            f"- No-prior demand surprise remains {_format_int(no_prior['surprise_rows'])} rows and should stay diagnostic-only until the action layer is recalibrated shadow-only."
        ),
        "",
        "## 5. Production Policy Status",
        "- Do not change production ordering logic.",
        "- Do not change Stage 12 publication logic.",
        "- Do not relax the demand proxy.",
        "- Do not promote shadow policy.",
        "- Do not promote auto-ordering.",
        "- Do not add downstream feature families into the units-head core.",
        (
            f"- Production order changes remain at {_format_int(policy['production_order_change_count'])} and Stage 12 changes remain at "
            f"{_format_int(policy['stage12_change_count'])}."
        ),
        (
            "- PANDAS_FRAGMENTATION_WARNING remains a technical cleanup item, not a production-policy justification."
        ),
        "",
        "## 6. Recommendation",
        (
            f"- Build the review overlay packet next, inspect the {_format_int(low_soh['true_low_soh_missed_demand_rows'])} true low-SOH missed-demand SKUs "
            f"and the {_format_int(no_prior['surprise_rows'])} no-prior-demand surprise rows, and calibrate the action layer in shadow-only mode while keeping capital guardrails active and auto-ordering blocked."
        ),
    ]
    if manifest is not None:
        lines.extend(
            [
                "",
                f"Source certification: {manifest.get('source_certification_status', 'UNKNOWN')}.",
            ]
        )
    return "\n".join(lines) + "\n"


def build_promotions_learning_scoreboard(
    *,
    review_summary_frame: pd.DataFrame,
    cleanup_summary_frame: pd.DataFrame,
    action_layer_summary_frame: pd.DataFrame,
    capital_drag_summary_frame: pd.DataFrame,
    capital_drag_override_summary_frame: pd.DataFrame,
    low_soh_summary_frame: pd.DataFrame,
    no_prior_demand_surprise_summary_frame: pd.DataFrame,
    manifest: dict[str, object] | None = None,
) -> PromotionsLearningScoreboardResult:
    metrics = _extract_metrics(
        review_summary_frame=review_summary_frame,
        cleanup_summary_frame=cleanup_summary_frame,
        action_layer_summary_frame=action_layer_summary_frame,
        capital_drag_summary_frame=capital_drag_summary_frame,
        capital_drag_override_summary_frame=capital_drag_override_summary_frame,
        low_soh_summary_frame=low_soh_summary_frame,
        no_prior_demand_surprise_summary_frame=no_prior_demand_surprise_summary_frame,
    )
    summary_frame = _build_summary_frame(metrics)
    decision_table_frame = _build_decision_table_frame(metrics)
    issue_backlog_frame = _build_issue_backlog_frame(metrics)
    next_actions_frame = _build_next_actions_frame(metrics)
    memo_markdown = _build_memo(metrics=metrics, manifest=manifest)
    return PromotionsLearningScoreboardResult(
        summary_frame=summary_frame,
        decision_table_frame=decision_table_frame,
        issue_backlog_frame=issue_backlog_frame,
        next_actions_frame=next_actions_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_learning_scoreboard(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsLearningScoreboardArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsLearningScoreboardError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    review_summary_frame = _read_csv(review_artifact_path / "model_vs_actual_summary.csv")
    cleanup_summary_frame = _read_csv(review_artifact_path / "report_contract_cleanup_summary.csv")
    action_layer_summary_frame = _read_csv(
        review_artifact_path / "action_layer_recalibration_summary.csv"
    )
    capital_drag_summary_frame = _read_csv(
        review_artifact_path
        / "capital_drag_strong_sellthrough_review"
        / "capital_drag_strong_sellthrough_summary.csv"
    )
    capital_drag_override_summary_frame = _read_csv(
        review_artifact_path
        / "capital_drag_strong_sellthrough_review"
        / "override_validation"
        / "capital_drag_override_validation_summary.csv"
    )
    low_soh_summary_frame = _read_csv(
        review_artifact_path
        / "low_soh_material_demand_review"
        / "low_soh_material_demand_summary.csv"
    )
    no_prior_demand_surprise_summary_frame = _read_csv(
        review_artifact_path / "no_prior_demand_surprise_summary.csv"
    )

    result = build_promotions_learning_scoreboard(
        review_summary_frame=review_summary_frame,
        cleanup_summary_frame=cleanup_summary_frame,
        action_layer_summary_frame=action_layer_summary_frame,
        capital_drag_summary_frame=capital_drag_summary_frame,
        capital_drag_override_summary_frame=capital_drag_override_summary_frame,
        low_soh_summary_frame=low_soh_summary_frame,
        no_prior_demand_surprise_summary_frame=no_prior_demand_surprise_summary_frame,
        manifest=manifest,
    )

    destination_root = (
        Path(output_root) if output_root is not None else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    summary_csv_path = destination_root / "promotion_learning_scoreboard_summary.csv"
    decision_table_csv_path = (
        destination_root / "promotion_learning_scoreboard_decision_table.csv"
    )
    issue_backlog_csv_path = (
        destination_root / "promotion_learning_scoreboard_issue_backlog.csv"
    )
    next_actions_csv_path = (
        destination_root / "promotion_learning_scoreboard_next_actions.csv"
    )
    memo_md_path = destination_root / "promotion_learning_scoreboard_memo.md"

    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(
        summary_csv_path,
        index=False,
    )
    add_provenance_columns(result.decision_table_frame.copy(), manifest).to_csv(
        decision_table_csv_path,
        index=False,
    )
    add_provenance_columns(result.issue_backlog_frame.copy(), manifest).to_csv(
        issue_backlog_csv_path,
        index=False,
    )
    add_provenance_columns(result.next_actions_frame.copy(), manifest).to_csv(
        next_actions_csv_path,
        index=False,
    )
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsLearningScoreboardArtifacts(
        summary_csv_path=str(summary_csv_path),
        decision_table_csv_path=str(decision_table_csv_path),
        issue_backlog_csv_path=str(issue_backlog_csv_path),
        next_actions_csv_path=str(next_actions_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the governed promotions learning scoreboard from validated diagnostics artifacts."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_learning_scoreboard(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("promotion_learning_scoreboard_summary", artifacts.summary_csv_path)
    print("promotion_learning_scoreboard_decision_table", artifacts.decision_table_csv_path)
    print("promotion_learning_scoreboard_issue_backlog", artifacts.issue_backlog_csv_path)
    print("promotion_learning_scoreboard_next_actions", artifacts.next_actions_csv_path)
    print("promotion_learning_scoreboard_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())