from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Sequence

import pandas as pd

from runtime.promotions.input_source_provenance import (
    add_provenance_columns,
    certification_failed,
)


OUTPUT_FOLDER_NAME = "review_overlay_packet"

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    "learning_scoreboard/promotion_learning_scoreboard_summary.csv",
    "learning_scoreboard/promotion_learning_scoreboard_decision_table.csv",
    "learning_scoreboard/promotion_learning_scoreboard_issue_backlog.csv",
    "learning_scoreboard/promotion_learning_scoreboard_next_actions.csv",
    "report_contract_cleanup_summary.csv",
    "model_vs_actual_report_cleanup_issues.csv",
    "capital_drag_strong_sellthrough_review/override_validation/capital_drag_override_validation_rows.csv",
    "low_soh_material_demand_review/low_soh_material_demand_rows.csv",
    "no_prior_demand_surprise_rows.csv",
    "action_layer_recalibration_rows.csv",
)

ROWS_OUTPUT_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "overlay_category",
    "operator_decision",
    "operator_action",
    "order_units",
    "reason_short",
    "risk_flag",
    "review_flag",
    "actual_units_sold",
    "expected_promo_demand",
    "forecast_error_units",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "current_soh_units",
    "on_order_units",
    "projected_on_hand_at_promo_start",
    "target_stock_day_one_units",
    "recommended_order_units",
    "final_store_order_units",
    "proposed_review_action",
    "why_review_required",
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

BY_REASON_COLUMNS: tuple[str, ...] = (
    "overlay_category",
    "proposed_review_action",
    "why_review_required",
    "row_count",
    "actual_units_total",
    "actual_gross_profit_total",
    "capital_left_total",
    "sample_skus",
)

BY_DEPARTMENT_COLUMNS: tuple[str, ...] = (
    "department",
    "row_count",
    "actual_units_total",
    "actual_gross_profit_total",
    "capital_left_total",
    "true_low_soh_missed_demand_review_rows",
    "online_floor_protection_review_rows",
    "no_prior_demand_surprise_review_rows",
    "strong_conversion_capital_drag_review_rows",
    "action_layer_shadow_calibration_review_rows",
    "zero_order_text_cleanup_review_rows",
    "top_overlay_category",
    "sample_skus",
)

OVERLAY_CATEGORY_PRIORITY: dict[str, int] = {
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": 1,
    "ONLINE_FLOOR_PROTECTION_REVIEW": 2,
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": 3,
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": 4,
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": 5,
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": 6,
}

PROPOSED_REVIEW_ACTION_BY_CATEGORY: dict[str, str] = {
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": "INSPECT_TRUE_MISSED_DEMAND",
    "ONLINE_FLOOR_PROTECTION_REVIEW": "INSPECT_ONLINE_FLOOR_RISK",
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": "INSPECT_STRONG_CONVERTER_CAPITAL_DRAG_HEADLINE",
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": "KEEP_SHADOW_ONLY_FOR_ACTION_LAYER",
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": "FIX_VISIBLE_REASON_TEXT",
}

WHY_REVIEW_REQUIRED_BY_CATEGORY: dict[str, str] = {
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": "Material demand landed while the row stayed low-SOH suppressed, so a human should inspect missed demand before any policy change.",
    "ONLINE_FLOOR_PROTECTION_REVIEW": "The row needs a human floor-risk check because low-SOH or floor-protection context stayed review-only and must not auto-order.",
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": "Material demand landed without strong prior promo evidence, so the row needs governed human inspection rather than a demand-proxy change.",
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": "Strong sell-through contradicted the visible capital-drag headline, so the row should be inspected as a review-only headline correction.",
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": "The action layer was too conservative or missed a governed review trigger, so any response must stay shadow-only and human-reviewed.",
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": "Visible wording still implies buy or order on a zero-order row, so the row needs contract cleanup review before operator use.",
}

LOW_SOH_CLASS_TO_OVERLAY_CATEGORY: dict[str, str] = {
    "TRUE_LOW_SOH_MISSED_DEMAND": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
    "ONLINE_FLOOR_PROTECTION_REVIEW": "ONLINE_FLOOR_PROTECTION_REVIEW",
    "LOW_SOH_BUT_COVERED_BY_ON_ORDER": "ONLINE_FLOOR_PROTECTION_REVIEW",
    "NO_CHANGE_CAPITAL_PROTECTED": "ONLINE_FLOOR_PROTECTION_REVIEW",
    "FORECAST_UNDERCALIBRATION_LOW_SOH": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
    "DATA_OR_LABEL_CONFLICT": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
}

HIGH_VALUE_REVIEW_CATEGORIES: tuple[str, ...] = (
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
    "ONLINE_FLOOR_PROTECTION_REVIEW",
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
)


class PromotionsReviewOverlayPacketError(RuntimeError):
    """Raised when the review overlay packet cannot run safely."""


@dataclass(frozen=True)
class PromotionsReviewOverlayPacketResult:
    summary_frame: pd.DataFrame
    rows_frame: pd.DataFrame
    by_reason_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsReviewOverlayPacketArtifacts:
    summary_csv_path: str
    rows_csv_path: str
    by_reason_csv_path: str
    by_department_csv_path: str
    memo_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsReviewOverlayPacketError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsReviewOverlayPacketError(f"Manifest must be a JSON object: {path}")
    return payload


def _normalize_identifier(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    normalized = numeric.round(0).astype("Int64").astype(str).replace("<NA>", "")
    fallback = series.fillna("").astype(str).str.strip()
    return normalized.where(normalized.ne(""), fallback).astype(str).str.strip()


def _normalize_token(value: object) -> str:
    return re.sub(r"\s+", "_", str(value).strip().casefold())


def _resolve_manifest_path(path_value: object, review_artifact_root: Path) -> Path:
    candidate = Path(str(path_value))
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        cwd_candidate = (Path.cwd() / candidate).resolve()
        if cwd_candidate.exists():
            return cwd_candidate
        review_candidate = (review_artifact_root / candidate).resolve()
        if review_candidate.exists():
            return review_candidate
    return candidate


def _validate_review_artifact_root(review_artifact_root: Path) -> None:
    missing = [
        artifact_name
        for artifact_name in REQUIRED_REVIEW_ARTIFACTS
        if not (review_artifact_root / artifact_name).exists()
    ]
    if missing:
        raise PromotionsReviewOverlayPacketError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsReviewOverlayPacketError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _build_prefixed_lookup(
    frame: pd.DataFrame,
    *,
    frame_name: str,
    columns: Sequence[str],
    prefix: str,
) -> pd.DataFrame:
    _require_columns(frame, columns, frame_name=frame_name)
    subset = frame.loc[:, columns].copy()
    subset["_sku_key"] = _normalize_identifier(subset["sku_number"])
    if subset["_sku_key"].eq("").any():
        blank_count = int(subset["_sku_key"].eq("").sum())
        raise PromotionsReviewOverlayPacketError(
            f"{frame_name} has blank sku_number values after normalization (rows={blank_count})"
        )
    duplicate_mask = subset["_sku_key"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicate_values = subset.loc[duplicate_mask, "_sku_key"].head(10).tolist()
        sample = ", ".join(duplicate_values)
        raise PromotionsReviewOverlayPacketError(
            f"{frame_name} has duplicate sku_number values after normalization: {sample}"
        )

    rename_map = {
        column_name: f"{prefix}{column_name}"
        for column_name in columns
        if column_name != "sku_number"
    }
    return subset.rename(columns=rename_map).drop(columns=["sku_number"])


def _lookup_summary_metric(
    summary_frame: pd.DataFrame,
    *,
    metric_group: str,
    metric_name: str,
) -> pd.Series:
    _require_columns(
        summary_frame,
        ("metric_group", "metric_name", "metric_value"),
        frame_name="scoreboard_summary_frame",
    )
    matched = summary_frame.loc[
        summary_frame["metric_group"].astype(str).eq(metric_group)
        & summary_frame["metric_name"].astype(str).eq(metric_name)
    ]
    if len(matched.index) != 1:
        raise PromotionsReviewOverlayPacketError(
            f"scoreboard_summary_frame expected one row for {metric_group}/{metric_name}, found {len(matched.index)}"
        )
    return matched.iloc[0]


def _lookup_table_row(
    frame: pd.DataFrame,
    *,
    frame_name: str,
    key_column: str,
    key_value: str,
) -> pd.Series:
    _require_columns(frame, (key_column,), frame_name=frame_name)
    matched = frame.loc[frame[key_column].astype(str).eq(key_value)]
    if len(matched.index) != 1:
        raise PromotionsReviewOverlayPacketError(
            f"{frame_name} expected one row for {key_column}={key_value}, found {len(matched.index)}"
        )
    return matched.iloc[0]


def _select_optional_table_row(
    frame: pd.DataFrame,
    *,
    frame_name: str,
    key_column: str,
    key_value: str,
) -> pd.Series | None:
    _require_columns(frame, (key_column,), frame_name=frame_name)
    matched = frame.loc[frame[key_column].astype(str).eq(key_value)]
    if matched.empty:
        return None
    if len(matched.index) != 1:
        raise PromotionsReviewOverlayPacketError(
            f"{frame_name} expected at most one row for {key_column}={key_value}, found {len(matched.index)}"
        )
    return matched.iloc[0]


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="raise").iloc[0])


def _as_int(value: object) -> int:
    return int(round(_as_float(value)))


def _coalesce_text(frame: pd.DataFrame, *columns: str, default: str = "") -> pd.Series:
    values = pd.Series([""] * len(frame.index), index=frame.index, dtype="object")
    for column_name in columns:
        if column_name not in frame.columns:
            continue
        candidate = frame[column_name].fillna("").astype(str).str.strip()
        values = values.where(values.astype(str).str.strip().ne(""), candidate)
    return values.fillna(default).astype(str)


def _coalesce_numeric(frame: pd.DataFrame, *columns: str, default: float = 0.0) -> pd.Series:
    values = pd.Series([pd.NA] * len(frame.index), index=frame.index, dtype="Float64")
    for column_name in columns:
        if column_name not in frame.columns:
            continue
        candidate = pd.to_numeric(frame[column_name], errors="coerce")
        values = values.fillna(candidate)
    return values.fillna(default).astype(float)


def _normalize_review_flag(frame: pd.DataFrame, *columns: str) -> pd.Series:
    values = pd.Series([0] * len(frame.index), index=frame.index, dtype="int64")
    for column_name in columns:
        if column_name not in frame.columns:
            continue
        numeric = pd.to_numeric(frame[column_name], errors="coerce")
        numeric_positive = numeric.fillna(0.0).ge(1.0).astype(int)
        text = frame[column_name].fillna("").astype(str).map(_normalize_token)
        text_positive = text.isin({"review", "1"}) | text.str.contains("manual_review", regex=False)
        values = values.where(values.eq(1), (numeric_positive | text_positive).astype(int))
    return values.astype(int)


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


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_float(value: float, *, decimals: int = 3, signed: bool = False) -> str:
    sign = "+" if signed else ""
    return f"{value:{sign},.{decimals}f}"


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _scoreboard_contract_values(
    *,
    scoreboard_summary_frame: pd.DataFrame,
    decision_table_frame: pd.DataFrame,
    issue_backlog_frame: pd.DataFrame,
    next_actions_frame: pd.DataFrame,
) -> dict[str, float | int]:
    capital_drag_overlay_rows = _as_int(
        _lookup_summary_metric(
            scoreboard_summary_frame,
            metric_group="CAPITAL_DRAG_OVERLAY",
            metric_name="OVERLAY_ROWS",
        )["metric_value"]
    )
    low_soh_overlay_rows = _as_int(
        _lookup_summary_metric(
            scoreboard_summary_frame,
            metric_group="LOW_SOH_OVERLAY",
            metric_name="OVERLAY_ROWS",
        )["metric_value"]
    )
    forecast_correlation = _as_float(
        _lookup_summary_metric(
            scoreboard_summary_frame,
            metric_group="FORECAST_HEAD",
            metric_name="FORECAST_CORRELATION",
        )["metric_value"]
    )
    forecast_bias_units = _as_float(
        _lookup_summary_metric(
            scoreboard_summary_frame,
            metric_group="FORECAST_HEAD",
            metric_name="FORECAST_BIAS_UNITS",
        )["metric_value"]
    )
    cleanup_issues_reduced = _as_int(
        _lookup_summary_metric(
            scoreboard_summary_frame,
            metric_group="REPORT_CLEANUP",
            metric_name="CLEANUP_ISSUES_REDUCED",
        )["metric_value"]
    )
    total_rows_reviewed = _as_int(
        _lookup_summary_metric(
            scoreboard_summary_frame,
            metric_group="REVIEW_SCOPE",
            metric_name="TOTAL_ROWS_REVIEWED",
        )["metric_value"]
    )

    production_decision = _lookup_table_row(
        decision_table_frame,
        frame_name="decision_table_frame",
        key_column="decision_category",
        key_value="PRODUCTION_ORDERING_UNCHANGED",
    )
    stage12_decision = _lookup_table_row(
        decision_table_frame,
        frame_name="decision_table_frame",
        key_column="decision_category",
        key_value="STAGE_12_UNCHANGED",
    )
    auto_ordering_decision = _lookup_table_row(
        decision_table_frame,
        frame_name="decision_table_frame",
        key_column="decision_category",
        key_value="AUTO_ORDERING_NOT_READY",
    )

    if str(production_decision.get("decision_status", "")) != "LOCKED":
        raise PromotionsReviewOverlayPacketError(
            "Scoreboard decision table no longer locks production ordering unchanged."
        )
    if str(stage12_decision.get("decision_status", "")) != "LOCKED":
        raise PromotionsReviewOverlayPacketError(
            "Scoreboard decision table no longer locks Stage 12 unchanged."
        )
    if str(auto_ordering_decision.get("decision_status", "")) != "BLOCKED":
        raise PromotionsReviewOverlayPacketError(
            "Scoreboard decision table no longer blocks auto-ordering."
        )

    review_overlay_action = _lookup_table_row(
        next_actions_frame,
        frame_name="next_actions_frame",
        key_column="next_action_recommendation",
        key_value="BUILD_REVIEW_OVERLAY_PACKET",
    )
    no_prior_action = _lookup_table_row(
        next_actions_frame,
        frame_name="next_actions_frame",
        key_column="next_action_recommendation",
        key_value="INSPECT_NO_PRIOR_DEMAND_SURPRISE_SKUS",
    )
    shadow_action = _lookup_table_row(
        next_actions_frame,
        frame_name="next_actions_frame",
        key_column="next_action_recommendation",
        key_value="CALIBRATE_ACTION_LAYER_SHADOW_ONLY",
    )

    if str(review_overlay_action.get("action_status", "")) != "READY":
        raise PromotionsReviewOverlayPacketError(
            "Scoreboard next actions no longer mark BUILD_REVIEW_OVERLAY_PACKET as READY."
        )

    no_prior_backlog = _lookup_table_row(
        issue_backlog_frame,
        frame_name="issue_backlog_frame",
        key_column="issue_backlog_category",
        key_value="NO_PRIOR_DEMAND_SURPRISE",
    )
    zero_order_backlog = _lookup_table_row(
        issue_backlog_frame,
        frame_name="issue_backlog_frame",
        key_column="issue_backlog_category",
        key_value="ZERO_ORDER_TEXT_RESIDUAL",
    )

    return {
        "capital_drag_overlay_rows": capital_drag_overlay_rows,
        "low_soh_overlay_rows": low_soh_overlay_rows,
        "forecast_correlation": forecast_correlation,
        "forecast_bias_units": forecast_bias_units,
        "cleanup_issues_reduced": cleanup_issues_reduced,
        "total_rows_reviewed": total_rows_reviewed,
        "review_overlay_ready_rows": _as_int(review_overlay_action["row_count"]),
        "no_prior_review_rows": _as_int(no_prior_action["row_count"]),
        "action_layer_shadow_rows": _as_int(shadow_action["row_count"]),
        "no_prior_backlog_rows": _as_int(no_prior_backlog["issue_count"]),
        "zero_order_text_rows": _as_int(zero_order_backlog["issue_count"]),
    }


def _build_low_soh_candidates(low_soh_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        low_soh_rows_frame,
        (
            "sku_number",
            "diagnostic_classification",
        ),
        frame_name="low_soh_rows_frame",
    )
    rows = low_soh_rows_frame.copy()
    rows["overlay_category"] = rows["diagnostic_classification"].map(
        LOW_SOH_CLASS_TO_OVERLAY_CATEGORY
    )
    rows = rows.loc[rows["overlay_category"].notna()].copy()
    rows["source_name"] = "low_soh"
    rows["_overlay_priority"] = rows["overlay_category"].map(OVERLAY_CATEGORY_PRIORITY)
    return rows


def _build_capital_drag_candidates(capital_drag_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        capital_drag_rows_frame,
        (
            "sku_number",
            "override_candidate_flag",
        ),
        frame_name="capital_drag_rows_frame",
    )
    rows = capital_drag_rows_frame.loc[
        pd.to_numeric(capital_drag_rows_frame["override_candidate_flag"], errors="coerce")
        .fillna(0.0)
        .ge(1.0)
    ].copy()
    rows["overlay_category"] = "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW"
    rows["source_name"] = "capital_drag"
    rows["_overlay_priority"] = OVERLAY_CATEGORY_PRIORITY["STRONG_CONVERSION_CAPITAL_DRAG_REVIEW"]
    return rows


def _build_no_prior_candidates(no_prior_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        no_prior_rows_frame,
        ("sku_number",),
        frame_name="no_prior_rows_frame",
    )
    rows = no_prior_rows_frame.copy()
    rows["overlay_category"] = "NO_PRIOR_DEMAND_SURPRISE_REVIEW"
    rows["source_name"] = "no_prior"
    rows["_overlay_priority"] = OVERLAY_CATEGORY_PRIORITY["NO_PRIOR_DEMAND_SURPRISE_REVIEW"]
    return rows


def _build_action_layer_candidates(
    action_layer_rows_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    _require_columns(
        action_layer_rows_frame,
        (
            "sku_number",
            "action_too_conservative_flag",
            "review_should_have_triggered_flag",
        ),
        frame_name="action_layer_rows_frame",
    )
    conservative = pd.to_numeric(
        action_layer_rows_frame["action_too_conservative_flag"], errors="coerce"
    ).fillna(0.0)
    missing_review = pd.to_numeric(
        action_layer_rows_frame["review_should_have_triggered_flag"], errors="coerce"
    ).fillna(0.0)
    issue_count = int(conservative.ge(1.0).sum() + missing_review.ge(1.0).sum())
    rows = action_layer_rows_frame.loc[(conservative.ge(1.0) | missing_review.ge(1.0))].copy()
    rows["overlay_category"] = "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW"
    rows["source_name"] = "action_layer"
    rows["_overlay_priority"] = OVERLAY_CATEGORY_PRIORITY["ACTION_LAYER_SHADOW_CALIBRATION_REVIEW"]
    return rows, issue_count


def _build_zero_order_text_candidates(
    *,
    cleanup_summary_frame: pd.DataFrame,
    cleanup_issues_frame: pd.DataFrame,
    visible_frame: pd.DataFrame,
    audit_frame: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(
        cleanup_summary_frame,
        (
            "issue_type",
            "issue_count",
            "sample_skus",
        ),
        frame_name="cleanup_summary_frame",
    )
    _require_columns(
        cleanup_issues_frame,
        (
            "sku_number",
            "issue_type",
        ),
        frame_name="cleanup_issues_frame",
    )
    _require_columns(
        visible_frame,
        (
            "sku_number",
            "sku_description",
            "operator_decision",
            "operator_action",
            "order_units",
            "reason_short",
            "risk_flag",
            "review_flag",
            "current_soh",
            "on_order_at_advice_time",
            "projected_SOH_at_promo_start",
            "target_SOH_at_promo_start",
        ),
        frame_name="visible_frame",
    )
    _require_columns(
        audit_frame,
        (
            "sku_number",
            "recommended_order_units",
            "final_store_order_units",
            "recommended_action",
            "order_reconciliation_reason",
            "decision_reason",
        ),
        frame_name="audit_frame",
    )

    cleanup_summary_row = _select_optional_table_row(
        cleanup_summary_frame,
        frame_name="cleanup_summary_frame",
        key_column="issue_type",
        key_value="BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS",
    )
    if cleanup_summary_row is None:
        return pd.DataFrame(columns=list(visible_frame.columns) + ["overlay_category", "source_name", "_overlay_priority"])

    summary_issue_count = _as_int(cleanup_summary_row["issue_count"])
    issue_rows = cleanup_issues_frame.loc[
        cleanup_issues_frame["issue_type"].astype(str).eq("BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS")
    ].copy()
    if issue_rows.empty:
        sampled_skus = [
            value.strip()
            for value in str(cleanup_summary_row.get("sample_skus", "")).split(",")
            if value.strip()
        ]
        sampled_skus = list(dict.fromkeys(sampled_skus))
        if summary_issue_count > len(sampled_skus):
            raise PromotionsReviewOverlayPacketError(
                "Cleanup summary identifies more zero-order text issues than can be recovered from sample_skus."
            )
        issue_rows = pd.DataFrame({"sku_number": sampled_skus})

    issue_rows["_sku_key"] = _normalize_identifier(issue_rows["sku_number"])
    issue_rows = issue_rows.drop_duplicates(subset=["_sku_key"], keep="first")
    if len(issue_rows.index) != summary_issue_count:
        raise PromotionsReviewOverlayPacketError(
            "Zero-order cleanup issue rows do not match the validated cleanup summary count."
        )

    visible_subset = visible_frame.copy()
    visible_subset["_sku_key"] = _normalize_identifier(visible_subset["sku_number"])
    audit_subset = audit_frame.loc[
        :,
        (
            "sku_number",
            "recommended_order_units",
            "final_store_order_units",
            "recommended_action",
            "order_reconciliation_reason",
            "decision_reason",
        ),
    ].copy()
    audit_subset["_sku_key"] = _normalize_identifier(audit_subset["sku_number"])
    audit_subset = audit_subset.drop(columns=["sku_number"])

    rows = visible_subset.merge(audit_subset, on="_sku_key", how="left")
    rows = rows.loc[rows["_sku_key"].isin(issue_rows["_sku_key"])].copy()
    missing_sku_keys = sorted(set(issue_rows["_sku_key"]) - set(rows["_sku_key"]))
    if missing_sku_keys:
        sample = ", ".join(missing_sku_keys[:10])
        raise PromotionsReviewOverlayPacketError(
            f"Zero-order cleanup issue rows could not be found in the visible report: {sample}"
        )

    rows["overlay_category"] = "ZERO_ORDER_TEXT_CLEANUP_REVIEW"
    rows["source_name"] = "zero_order_text"
    rows["_overlay_priority"] = OVERLAY_CATEGORY_PRIORITY["ZERO_ORDER_TEXT_CLEANUP_REVIEW"]
    return rows


def _enrich_candidates(
    candidates_frame: pd.DataFrame,
    *,
    action_layer_lookup: pd.DataFrame,
    visible_lookup: pd.DataFrame,
    audit_lookup: pd.DataFrame,
) -> pd.DataFrame:
    if candidates_frame.empty:
        return pd.DataFrame(columns=ROWS_OUTPUT_COLUMNS + ("_sku_key", "_overlay_priority"))

    rows = candidates_frame.copy()
    rows["_sku_key"] = _normalize_identifier(rows["sku_number"])
    rows = rows.merge(action_layer_lookup, on="_sku_key", how="left")
    rows = rows.merge(visible_lookup, on="_sku_key", how="left")
    rows = rows.merge(audit_lookup, on="_sku_key", how="left")

    packet_rows = pd.DataFrame(index=rows.index)
    packet_rows["sku_number"] = _coalesce_text(rows, "sku_number")
    packet_rows["sku_description"] = _coalesce_text(
        rows,
        "sku_description",
        "action_layer_sku_description",
        "visible_sku_description",
    )
    packet_rows["department"] = _coalesce_text(
        rows,
        "department",
        "action_layer_department",
        default="UNKNOWN",
    )
    packet_rows["overlay_category"] = rows["overlay_category"].astype(str)
    packet_rows["operator_decision"] = _coalesce_text(
        rows,
        "operator_decision",
        "visible_operator_decision",
        "action_layer_operator_decision",
    )
    packet_rows["operator_action"] = _coalesce_text(
        rows,
        "operator_action",
        "visible_operator_action",
        "action_layer_operator_action",
    )
    packet_rows["order_units"] = _coalesce_numeric(
        rows,
        "order_units",
        "visible_order_units",
        "audit_final_store_order_units",
    )
    packet_rows["reason_short"] = _coalesce_text(
        rows,
        "reason_short",
        "visible_reason_short",
        "action_layer_reason_short",
        "audit_order_reconciliation_reason",
    )
    packet_rows["risk_flag"] = _coalesce_text(
        rows,
        "risk_flag",
        "visible_risk_flag",
        "action_layer_risk_flag",
    )
    packet_rows["review_flag"] = _normalize_review_flag(
        rows,
        "review_flag",
        "visible_review_flag",
        "action_layer_review_flag",
    )
    packet_rows["actual_units_sold"] = _coalesce_numeric(
        rows,
        "actual_units_sold",
        "action_layer_actual_units_sold",
    )
    packet_rows["expected_promo_demand"] = _coalesce_numeric(
        rows,
        "expected_promo_demand",
        "action_layer_expected_promo_demand",
    )
    packet_rows["forecast_error_units"] = _coalesce_numeric(
        rows,
        "forecast_error_units",
        "action_layer_forecast_abs_error_units",
    )
    packet_rows["actual_gross_profit"] = _coalesce_numeric(
        rows,
        "actual_gross_profit",
        "action_layer_estimated_actual_gross_profit",
    )
    packet_rows["capital_left_in_unsold_store_allocation"] = _coalesce_numeric(
        rows,
        "capital_left_in_unsold_store_allocation",
        "capital_left",
        "action_layer_capital_left_unsold",
    )
    packet_rows["current_soh_units"] = _coalesce_numeric(
        rows,
        "current_soh_units",
        "visible_current_soh",
        "audit_current_soh",
    )
    packet_rows["on_order_units"] = _coalesce_numeric(
        rows,
        "on_order_units",
        "visible_on_order_at_advice_time",
        "audit_on_order_at_advice_time",
    )
    packet_rows["projected_on_hand_at_promo_start"] = _coalesce_numeric(
        rows,
        "projected_on_hand_at_promo_start",
        "visible_projected_SOH_at_promo_start",
        "audit_projected_SOH_at_promo_start",
    )
    packet_rows["target_stock_day_one_units"] = _coalesce_numeric(
        rows,
        "target_stock_day_one_units",
        "visible_target_SOH_at_promo_start",
        "audit_target_SOH_at_promo_start",
    )
    packet_rows["recommended_order_units"] = _coalesce_numeric(
        rows,
        "recommended_order_units",
        "audit_recommended_order_units",
        "action_layer_recommended_order_units",
    )
    packet_rows["final_store_order_units"] = _coalesce_numeric(
        rows,
        "final_store_order_units",
        "audit_final_store_order_units",
    )
    packet_rows["proposed_review_action"] = packet_rows["overlay_category"].map(
        PROPOSED_REVIEW_ACTION_BY_CATEGORY
    )
    packet_rows["why_review_required"] = packet_rows["overlay_category"].map(
        WHY_REVIEW_REQUIRED_BY_CATEGORY
    )
    packet_rows["production_order_change_flag"] = 0
    packet_rows["stage_12_change_flag"] = 0
    packet_rows["_sku_key"] = rows["_sku_key"].astype(str)
    packet_rows["_overlay_priority"] = rows["_overlay_priority"].astype(int)

    return packet_rows


def _build_packet_rows_frame(
    *,
    cleanup_summary_frame: pd.DataFrame,
    cleanup_issues_frame: pd.DataFrame,
    capital_drag_rows_frame: pd.DataFrame,
    low_soh_rows_frame: pd.DataFrame,
    no_prior_rows_frame: pd.DataFrame,
    action_layer_rows_frame: pd.DataFrame,
    visible_frame: pd.DataFrame,
    audit_frame: pd.DataFrame,
    scoreboard_contract: dict[str, float | int],
) -> pd.DataFrame:
    action_layer_lookup = _build_prefixed_lookup(
        action_layer_rows_frame,
        frame_name="action_layer_rows_frame",
        columns=(
            "sku_number",
            "sku_description",
            "department",
            "operator_decision",
            "operator_action",
            "recommended_order_units",
            "reason_short",
            "risk_flag",
            "review_flag",
            "expected_promo_demand",
            "actual_units_sold",
            "forecast_abs_error_units",
            "estimated_actual_gross_profit",
            "capital_left_unsold",
        ),
        prefix="action_layer_",
    )
    visible_lookup = _build_prefixed_lookup(
        visible_frame,
        frame_name="visible_frame",
        columns=(
            "sku_number",
            "sku_description",
            "operator_decision",
            "operator_action",
            "order_units",
            "reason_short",
            "risk_flag",
            "review_flag",
            "current_soh",
            "on_order_at_advice_time",
            "projected_SOH_at_promo_start",
            "target_SOH_at_promo_start",
        ),
        prefix="visible_",
    )
    audit_lookup = _build_prefixed_lookup(
        audit_frame,
        frame_name="audit_frame",
        columns=(
            "sku_number",
            "recommended_order_units",
            "final_store_order_units",
            "order_reconciliation_reason",
            "current_soh",
            "on_order_at_advice_time",
            "projected_SOH_at_promo_start",
            "target_SOH_at_promo_start",
        ),
        prefix="audit_",
    )

    low_soh_candidates = _build_low_soh_candidates(low_soh_rows_frame)
    capital_drag_candidates = _build_capital_drag_candidates(capital_drag_rows_frame)
    no_prior_candidates = _build_no_prior_candidates(no_prior_rows_frame)
    action_layer_candidates, action_layer_issue_count = _build_action_layer_candidates(
        action_layer_rows_frame
    )
    zero_order_candidates = _build_zero_order_text_candidates(
        cleanup_summary_frame=cleanup_summary_frame,
        cleanup_issues_frame=cleanup_issues_frame,
        visible_frame=visible_frame,
        audit_frame=audit_frame,
    )

    review_overlay_candidate_rows = len(capital_drag_candidates.index) + len(low_soh_candidates.index)
    if review_overlay_candidate_rows != int(scoreboard_contract["review_overlay_ready_rows"]):
        raise PromotionsReviewOverlayPacketError(
            "Scoreboard BUILD_REVIEW_OVERLAY_PACKET row_count does not match capital-drag + low-SOH review overlay source rows."
        )
    if len(capital_drag_candidates.index) != int(scoreboard_contract["capital_drag_overlay_rows"]):
        raise PromotionsReviewOverlayPacketError(
            "Capital-drag override validation rows do not match the validated scoreboard overlay count."
        )
    if len(low_soh_candidates.index) != int(scoreboard_contract["low_soh_overlay_rows"]):
        raise PromotionsReviewOverlayPacketError(
            "Low-SOH review rows do not match the validated scoreboard overlay count."
        )
    if len(no_prior_candidates.index) != int(scoreboard_contract["no_prior_review_rows"]):
        raise PromotionsReviewOverlayPacketError(
            "No-prior demand surprise rows do not match the validated scoreboard review count."
        )
    if action_layer_issue_count != int(scoreboard_contract["action_layer_shadow_rows"]):
        raise PromotionsReviewOverlayPacketError(
            "Action-layer shadow calibration issue counts do not match the validated scoreboard review count."
        )
    if len(zero_order_candidates.index) != int(scoreboard_contract["zero_order_text_rows"]):
        raise PromotionsReviewOverlayPacketError(
            "Zero-order text cleanup rows do not match the validated scoreboard backlog count."
        )

    candidate_frames = [
        _enrich_candidates(
            low_soh_candidates,
            action_layer_lookup=action_layer_lookup,
            visible_lookup=visible_lookup,
            audit_lookup=audit_lookup,
        ),
        _enrich_candidates(
            capital_drag_candidates,
            action_layer_lookup=action_layer_lookup,
            visible_lookup=visible_lookup,
            audit_lookup=audit_lookup,
        ),
        _enrich_candidates(
            no_prior_candidates,
            action_layer_lookup=action_layer_lookup,
            visible_lookup=visible_lookup,
            audit_lookup=audit_lookup,
        ),
        _enrich_candidates(
            action_layer_candidates,
            action_layer_lookup=action_layer_lookup,
            visible_lookup=visible_lookup,
            audit_lookup=audit_lookup,
        ),
        _enrich_candidates(
            zero_order_candidates,
            action_layer_lookup=action_layer_lookup,
            visible_lookup=visible_lookup,
            audit_lookup=audit_lookup,
        ),
    ]
    combined = pd.concat(candidate_frames, ignore_index=True)
    combined = combined.sort_values(
        by=["_overlay_priority", "actual_gross_profit", "actual_units_sold", "sku_number"],
        ascending=[True, False, False, True],
        kind="stable",
    )
    packet_rows = combined.drop_duplicates(subset=["_sku_key"], keep="first").copy()
    packet_rows = packet_rows.sort_values(
        by=["_overlay_priority", "actual_gross_profit", "actual_units_sold", "sku_number"],
        ascending=[True, False, False, True],
        kind="stable",
    ).reset_index(drop=True)

    if packet_rows["production_order_change_flag"].sum() != 0:
        raise PromotionsReviewOverlayPacketError(
            "Review overlay packet attempted to introduce production order changes."
        )
    if packet_rows["stage_12_change_flag"].sum() != 0:
        raise PromotionsReviewOverlayPacketError(
            "Review overlay packet attempted to introduce Stage 12 changes."
        )

    return packet_rows.loc[:, list(ROWS_OUTPUT_COLUMNS) + ["_sku_key", "_overlay_priority"]]


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


def _build_summary_frame(
    *,
    rows_frame: pd.DataFrame,
    scoreboard_contract: dict[str, float | int],
) -> pd.DataFrame:
    rows = [
        _summary_row(
            "SCOREBOARD",
            "TOTAL_ROWS_REVIEWED",
            int(scoreboard_contract["total_rows_reviewed"]),
            "rows",
            _format_int(scoreboard_contract["total_rows_reviewed"]),
            "Validated scoreboard review population.",
        ),
        _summary_row(
            "SCOREBOARD",
            "FORECAST_CORRELATION",
            float(scoreboard_contract["forecast_correlation"]),
            "correlation",
            _format_float(float(scoreboard_contract["forecast_correlation"]), decimals=3),
            "Auto-ordering remains blocked because the forecast head is still weak.",
        ),
        _summary_row(
            "SCOREBOARD",
            "FORECAST_BIAS_UNITS",
            float(scoreboard_contract["forecast_bias_units"]),
            "units",
            _format_float(float(scoreboard_contract["forecast_bias_units"]), decimals=0, signed=True),
            "Positive bias remains materially high.",
        ),
        _summary_row(
            "SCOREBOARD",
            "CLEANUP_ISSUES_REDUCED",
            int(scoreboard_contract["cleanup_issues_reduced"]),
            "issues",
            _format_int(scoreboard_contract["cleanup_issues_reduced"]),
            "Visible contract cleanup is materially improved but still leaves a residual review backlog.",
        ),
        _summary_row(
            "PACKET",
            "TOTAL_REVIEW_ROWS",
            int(len(rows_frame.index)),
            "rows",
            _format_int(len(rows_frame.index)),
            "Deduplicated review packet rows after overlay priority assignment.",
        ),
        _summary_row(
            "PACKET",
            "TOTAL_GROSS_PROFIT_REPRESENTED",
            round(float(rows_frame["actual_gross_profit"].sum()), 2),
            "dollars",
            _format_money(float(rows_frame["actual_gross_profit"].sum())),
            "Gross profit represented by the review packet rows.",
        ),
        _summary_row(
            "PACKET",
            "TOTAL_CAPITAL_LEFT_REPRESENTED",
            round(float(rows_frame["capital_left_in_unsold_store_allocation"].sum()), 2),
            "dollars",
            _format_money(float(rows_frame["capital_left_in_unsold_store_allocation"].sum())),
            "Capital left represented by the review packet rows.",
        ),
        _summary_row(
            "PACKET",
            "PRODUCTION_ORDER_CHANGES",
            0,
            "rows",
            "0",
            "This review packet does not alter production ordering.",
        ),
        _summary_row(
            "PACKET",
            "STAGE12_CHANGES",
            0,
            "rows",
            "0",
            "This review packet does not alter Stage 12.",
        ),
    ]
    for overlay_category, group in rows_frame.groupby("overlay_category", sort=False, dropna=False):
        rows.append(
            _summary_row(
                "OVERLAY_CATEGORY",
                str(overlay_category),
                int(len(group.index)),
                "rows",
                _format_int(len(group.index)),
                f"Deduplicated packet rows assigned to {overlay_category}.",
            )
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_by_reason_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for overlay_category, group in rows_frame.groupby("overlay_category", sort=False, dropna=False):
        rows.append(
            {
                "overlay_category": str(overlay_category),
                "proposed_review_action": str(group["proposed_review_action"].iloc[0]),
                "why_review_required": str(group["why_review_required"].iloc[0]),
                "row_count": int(len(group.index)),
                "actual_units_total": round(float(group["actual_units_sold"].sum()), 2),
                "actual_gross_profit_total": round(float(group["actual_gross_profit"].sum()), 2),
                "capital_left_total": round(float(group["capital_left_in_unsold_store_allocation"].sum()), 2),
                "sample_skus": _sample_skus(group["sku_number"]),
            }
        )
    frame = pd.DataFrame(rows, columns=BY_REASON_COLUMNS)
    return frame.sort_values(
        by=["row_count", "actual_gross_profit_total", "overlay_category"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_by_department_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for department, group in rows_frame.groupby("department", sort=False, dropna=False):
        overlay_counts = group["overlay_category"].value_counts(dropna=False)
        rows.append(
            {
                "department": str(department),
                "row_count": int(len(group.index)),
                "actual_units_total": round(float(group["actual_units_sold"].sum()), 2),
                "actual_gross_profit_total": round(float(group["actual_gross_profit"].sum()), 2),
                "capital_left_total": round(float(group["capital_left_in_unsold_store_allocation"].sum()), 2),
                "true_low_soh_missed_demand_review_rows": int(
                    overlay_counts.get("TRUE_LOW_SOH_MISSED_DEMAND_REVIEW", 0)
                ),
                "online_floor_protection_review_rows": int(
                    overlay_counts.get("ONLINE_FLOOR_PROTECTION_REVIEW", 0)
                ),
                "no_prior_demand_surprise_review_rows": int(
                    overlay_counts.get("NO_PRIOR_DEMAND_SURPRISE_REVIEW", 0)
                ),
                "strong_conversion_capital_drag_review_rows": int(
                    overlay_counts.get("STRONG_CONVERSION_CAPITAL_DRAG_REVIEW", 0)
                ),
                "action_layer_shadow_calibration_review_rows": int(
                    overlay_counts.get("ACTION_LAYER_SHADOW_CALIBRATION_REVIEW", 0)
                ),
                "zero_order_text_cleanup_review_rows": int(
                    overlay_counts.get("ZERO_ORDER_TEXT_CLEANUP_REVIEW", 0)
                ),
                "top_overlay_category": str(
                    overlay_counts.sort_values(ascending=False, kind="stable").index[0]
                ),
                "sample_skus": _sample_skus(group["sku_number"]),
            }
        )
    frame = pd.DataFrame(rows, columns=BY_DEPARTMENT_COLUMNS)
    return frame.sort_values(
        by=["row_count", "actual_gross_profit_total", "department"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _highest_value_inspection_row(by_reason_frame: pd.DataFrame) -> pd.Series:
    filtered = by_reason_frame.loc[
        by_reason_frame["overlay_category"].astype(str).isin(HIGH_VALUE_REVIEW_CATEGORIES)
    ].copy()
    if filtered.empty:
        return by_reason_frame.sort_values(
            by=["actual_gross_profit_total", "row_count", "overlay_category"],
            ascending=[False, False, True],
            kind="stable",
        ).iloc[0]
    filtered["_priority"] = filtered["overlay_category"].map(OVERLAY_CATEGORY_PRIORITY)
    filtered = filtered.sort_values(
        by=["actual_gross_profit_total", "row_count", "_priority", "overlay_category"],
        ascending=[False, False, True, True],
        kind="stable",
    )
    return filtered.iloc[0]


def _build_memo(
    *,
    rows_frame: pd.DataFrame,
    by_reason_frame: pd.DataFrame,
    by_department_frame: pd.DataFrame,
    scoreboard_contract: dict[str, float | int],
    manifest: dict[str, object] | None = None,
) -> str:
    highest_value = _highest_value_inspection_row(by_reason_frame)
    top_department = by_department_frame.iloc[0] if not by_department_frame.empty else None

    lines = [
        "# Review Overlay Packet",
        "",
        "This file is a governed review packet, not an order file. It is designed to convert validated diagnostics into a controlled human inspection list without changing production order quantities.",
        "",
        "## What changed and what did not",
        f"- Deduplicated packet rows: {_format_int(len(rows_frame.index))}.",
        "- Production order changes: 0.",
        "- Stage 12 changes: 0.",
        "- No production ordering logic was changed.",
        "- No Stage 12 logic was changed.",
        "- No auto-ordering was promoted.",
        "- No demand proxy was relaxed.",
        "- No shadow policy was promoted.",
        "- No downstream feature family was promoted into the units-head core.",
        "",
        "## Why auto-ordering remains blocked",
        (
            f"- Forecast correlation remains {_format_float(float(scoreboard_contract['forecast_correlation']), decimals=3)} "
            f"with {_format_float(float(scoreboard_contract['forecast_bias_units']), decimals=0, signed=True)} units of bias."
        ),
        "- The validated scoreboard still shows the action layer as too conservative, so any action-layer response must remain shadow-only and review-led.",
        "",
        "## Highest-value inspection set",
        (
            f"- Start with {highest_value['overlay_category']} because it represents {int(highest_value['row_count'])} row(s), "
            f"{_format_money(float(highest_value['actual_gross_profit_total']))} gross profit, and "
            f"{_format_money(float(highest_value['capital_left_total']))} capital left."
        ),
        f"- Recommended review action: {highest_value['proposed_review_action']}.",
    ]
    if top_department is not None:
        lines.append(
            f"- The largest department slice is {top_department['department']} with {int(top_department['row_count'])} row(s)."
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            (
                f"- Work the packet in overlay-priority order, starting with {highest_value['overlay_category']}, "
                "then complete the remaining review-only overlay rows before any shadow-only action-layer calibration is revisited."
            ),
            "",
            f"Source certification: {manifest.get('source_certification_status', 'UNKNOWN') if manifest else 'UNKNOWN'}.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_promotions_review_overlay_packet(
    *,
    scoreboard_summary_frame: pd.DataFrame,
    decision_table_frame: pd.DataFrame,
    issue_backlog_frame: pd.DataFrame,
    next_actions_frame: pd.DataFrame,
    cleanup_summary_frame: pd.DataFrame,
    cleanup_issues_frame: pd.DataFrame,
    capital_drag_rows_frame: pd.DataFrame,
    low_soh_rows_frame: pd.DataFrame,
    no_prior_rows_frame: pd.DataFrame,
    action_layer_rows_frame: pd.DataFrame,
    visible_frame: pd.DataFrame,
    audit_frame: pd.DataFrame,
    manifest: dict[str, object] | None = None,
) -> PromotionsReviewOverlayPacketResult:
    scoreboard_contract = _scoreboard_contract_values(
        scoreboard_summary_frame=scoreboard_summary_frame,
        decision_table_frame=decision_table_frame,
        issue_backlog_frame=issue_backlog_frame,
        next_actions_frame=next_actions_frame,
    )
    rows_frame = _build_packet_rows_frame(
        cleanup_summary_frame=cleanup_summary_frame,
        cleanup_issues_frame=cleanup_issues_frame,
        capital_drag_rows_frame=capital_drag_rows_frame,
        low_soh_rows_frame=low_soh_rows_frame,
        no_prior_rows_frame=no_prior_rows_frame,
        action_layer_rows_frame=action_layer_rows_frame,
        visible_frame=visible_frame,
        audit_frame=audit_frame,
        scoreboard_contract=scoreboard_contract,
    )
    summary_frame = _build_summary_frame(
        rows_frame=rows_frame,
        scoreboard_contract=scoreboard_contract,
    )
    by_reason_frame = _build_by_reason_frame(rows_frame)
    by_department_frame = _build_by_department_frame(rows_frame)
    memo_markdown = _build_memo(
        rows_frame=rows_frame,
        by_reason_frame=by_reason_frame,
        by_department_frame=by_department_frame,
        scoreboard_contract=scoreboard_contract,
        manifest=manifest,
    )
    return PromotionsReviewOverlayPacketResult(
        summary_frame=summary_frame,
        rows_frame=rows_frame.loc[:, ROWS_OUTPUT_COLUMNS].copy(),
        by_reason_frame=by_reason_frame,
        by_department_frame=by_department_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_review_overlay_packet(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsReviewOverlayPacketArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsReviewOverlayPacketError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    visible_path = _resolve_manifest_path(manifest.get("allocation_report_csv_path", ""), review_artifact_path)
    audit_path = _resolve_manifest_path(manifest.get("audit_only_report_csv_path", ""), review_artifact_path)
    if not visible_path.exists():
        raise PromotionsReviewOverlayPacketError(f"Visible report CSV not found: {visible_path}")
    if not audit_path.exists():
        raise PromotionsReviewOverlayPacketError(f"Audit report CSV not found: {audit_path}")

    result = build_promotions_review_overlay_packet(
        scoreboard_summary_frame=_read_csv(
            review_artifact_path
            / "learning_scoreboard"
            / "promotion_learning_scoreboard_summary.csv"
        ),
        decision_table_frame=_read_csv(
            review_artifact_path
            / "learning_scoreboard"
            / "promotion_learning_scoreboard_decision_table.csv"
        ),
        issue_backlog_frame=_read_csv(
            review_artifact_path
            / "learning_scoreboard"
            / "promotion_learning_scoreboard_issue_backlog.csv"
        ),
        next_actions_frame=_read_csv(
            review_artifact_path
            / "learning_scoreboard"
            / "promotion_learning_scoreboard_next_actions.csv"
        ),
        cleanup_summary_frame=_read_csv(
            review_artifact_path / "report_contract_cleanup_summary.csv"
        ),
        cleanup_issues_frame=_read_csv(
            review_artifact_path / "model_vs_actual_report_cleanup_issues.csv"
        ),
        capital_drag_rows_frame=_read_csv(
            review_artifact_path
            / "capital_drag_strong_sellthrough_review"
            / "override_validation"
            / "capital_drag_override_validation_rows.csv"
        ),
        low_soh_rows_frame=_read_csv(
            review_artifact_path
            / "low_soh_material_demand_review"
            / "low_soh_material_demand_rows.csv"
        ),
        no_prior_rows_frame=_read_csv(
            review_artifact_path / "no_prior_demand_surprise_rows.csv"
        ),
        action_layer_rows_frame=_read_csv(
            review_artifact_path / "action_layer_recalibration_rows.csv"
        ),
        visible_frame=_read_csv(visible_path),
        audit_frame=_read_csv(audit_path),
        manifest=manifest,
    )

    destination_root = (
        Path(output_root) if output_root is not None else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    summary_csv_path = destination_root / "review_overlay_packet_summary.csv"
    rows_csv_path = destination_root / "review_overlay_packet_rows.csv"
    by_reason_csv_path = destination_root / "review_overlay_packet_by_reason.csv"
    by_department_csv_path = destination_root / "review_overlay_packet_by_department.csv"
    memo_md_path = destination_root / "review_overlay_packet_memo.md"

    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.by_reason_frame.copy(), manifest).to_csv(
        by_reason_csv_path,
        index=False,
    )
    add_provenance_columns(result.by_department_frame.copy(), manifest).to_csv(
        by_department_csv_path,
        index=False,
    )
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsReviewOverlayPacketArtifacts(
        summary_csv_path=str(summary_csv_path),
        rows_csv_path=str(rows_csv_path),
        by_reason_csv_path=str(by_reason_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed promotions review overlay packet from the validated learning scoreboard."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_review_overlay_packet(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("review_overlay_packet_summary", artifacts.summary_csv_path)
    print("review_overlay_packet_rows", artifacts.rows_csv_path)
    print("review_overlay_packet_by_reason", artifacts.by_reason_csv_path)
    print("review_overlay_packet_by_department", artifacts.by_department_csv_path)
    print("review_overlay_packet_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())