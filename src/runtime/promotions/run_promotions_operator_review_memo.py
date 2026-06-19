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


OUTPUT_FOLDER_NAME = "operator_review_memo"

REQUIRED_REVIEW_PACKET_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    "review_overlay_packet/review_overlay_packet_summary.csv",
    "review_overlay_packet/review_overlay_packet_rows.csv",
    "review_overlay_packet/review_overlay_packet_by_reason.csv",
    "review_overlay_packet/review_overlay_packet_by_department.csv",
    "review_overlay_packet/review_overlay_packet_memo.md",
)

PRIORITY_LIST_COLUMNS: tuple[str, ...] = (
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

BY_CATEGORY_COLUMNS: tuple[str, ...] = (
    "review_priority_rank",
    "overlay_category",
    "row_count",
    "actual_units_total",
    "expected_promo_demand_total",
    "actual_gross_profit_total",
    "capital_left_total",
    "proposed_review_action",
    "human_review_question",
    "why_review_required",
    "sample_skus",
)

BY_DEPARTMENT_COLUMNS: tuple[str, ...] = (
    "department",
    "row_count",
    "actual_units_total",
    "actual_gross_profit_total",
    "capital_left_total",
    "top_overlay_category",
    "top_review_priority_rank",
    "sample_skus",
)

OVERLAY_PRIORITY: dict[str, int] = {
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": 1,
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": 2,
    "ONLINE_FLOOR_PROTECTION_REVIEW": 3,
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": 4,
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": 5,
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": 6,
}

HUMAN_REVIEW_QUESTION_BY_CATEGORY: dict[str, str] = {
    "NO_PRIOR_DEMAND_SURPRISE_REVIEW": "Why did this SKU sell despite weak/no prior promo evidence?",
    "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW": "Would a small review-only floor have protected sales without overstocking?",
    "ONLINE_FLOOR_PROTECTION_REVIEW": "Was online availability exposed by low stock depth?",
    "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW": "Is the capital-drag headline too harsh given strong conversion and low residual capital?",
    "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW": "Should this remain shadow-only until repeated evidence appears?",
    "ZERO_ORDER_TEXT_CLEANUP_REVIEW": "Does the visible reason text imply ordering when order units are zero?",
}


class PromotionsOperatorReviewMemoError(RuntimeError):
    """Raised when the operator review memo cannot be built safely."""


@dataclass(frozen=True)
class PromotionsOperatorReviewMemoResult:
    priority_list_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_category_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsOperatorReviewMemoArtifacts:
    priority_list_csv_path: str
    summary_csv_path: str
    by_category_csv_path: str
    by_department_csv_path: str
    memo_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsOperatorReviewMemoError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsOperatorReviewMemoError(f"Manifest must be a JSON object: {path}")
    return payload


def _validate_review_artifact_root(review_artifact_root: Path) -> None:
    missing = [
        artifact_name
        for artifact_name in REQUIRED_REVIEW_PACKET_ARTIFACTS
        if not (review_artifact_root / artifact_name).exists()
    ]
    if missing:
        raise PromotionsOperatorReviewMemoError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsOperatorReviewMemoError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _lookup_summary_metric(
    summary_frame: pd.DataFrame,
    *,
    metric_group: str,
    metric_name: str,
) -> pd.Series:
    _require_columns(
        summary_frame,
        ("metric_group", "metric_name", "metric_value"),
        frame_name="review_overlay_summary_frame",
    )
    matched = summary_frame.loc[
        summary_frame["metric_group"].astype(str).eq(metric_group)
        & summary_frame["metric_name"].astype(str).eq(metric_name)
    ]
    if len(matched.index) != 1:
        raise PromotionsOperatorReviewMemoError(
            f"review_overlay_summary_frame expected one row for {metric_group}/{metric_name}, found {len(matched.index)}"
        )
    return matched.iloc[0]


def _as_int(value: object) -> int:
    return int(round(float(pd.to_numeric(pd.Series([value]), errors="raise").iloc[0])))


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="raise").iloc[0])


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


def _validate_overlay_inputs(
    *,
    review_overlay_summary_frame: pd.DataFrame,
    review_overlay_rows_frame: pd.DataFrame,
    review_overlay_by_reason_frame: pd.DataFrame,
    review_overlay_by_department_frame: pd.DataFrame,
    review_overlay_memo_text: str,
) -> None:
    _require_columns(
        review_overlay_rows_frame,
        (
            "sku_number",
            "department",
            "overlay_category",
            "actual_gross_profit",
            "capital_left_in_unsold_store_allocation",
            "production_order_change_flag",
            "stage_12_change_flag",
        ),
        frame_name="review_overlay_rows_frame",
    )
    _require_columns(
        review_overlay_by_reason_frame,
        (
            "overlay_category",
            "row_count",
            "actual_gross_profit_total",
            "capital_left_total",
        ),
        frame_name="review_overlay_by_reason_frame",
    )
    _require_columns(
        review_overlay_by_department_frame,
        (
            "department",
            "row_count",
            "actual_gross_profit_total",
            "capital_left_total",
        ),
        frame_name="review_overlay_by_department_frame",
    )
    if not review_overlay_memo_text.strip():
        raise PromotionsOperatorReviewMemoError("review_overlay_packet_memo.md must not be empty.")

    expected_total_rows = _as_int(
        _lookup_summary_metric(
            review_overlay_summary_frame,
            metric_group="PACKET",
            metric_name="TOTAL_REVIEW_ROWS",
        )["metric_value"]
    )
    if expected_total_rows != len(review_overlay_rows_frame.index):
        raise PromotionsOperatorReviewMemoError(
            "Review overlay summary total rows do not match the review overlay rows file."
        )

    expected_gross_profit = _as_float(
        _lookup_summary_metric(
            review_overlay_summary_frame,
            metric_group="PACKET",
            metric_name="TOTAL_GROSS_PROFIT_REPRESENTED",
        )["metric_value"]
    )
    observed_gross_profit = float(
        pd.to_numeric(review_overlay_rows_frame["actual_gross_profit"], errors="coerce").fillna(0.0).sum()
    )
    if round(expected_gross_profit - observed_gross_profit, 2) != 0:
        raise PromotionsOperatorReviewMemoError(
            "Review overlay summary gross profit does not match the review overlay rows file."
        )

    expected_capital_left = _as_float(
        _lookup_summary_metric(
            review_overlay_summary_frame,
            metric_group="PACKET",
            metric_name="TOTAL_CAPITAL_LEFT_REPRESENTED",
        )["metric_value"]
    )
    observed_capital_left = float(
        pd.to_numeric(
            review_overlay_rows_frame["capital_left_in_unsold_store_allocation"],
            errors="coerce",
        ).fillna(0.0).sum()
    )
    if round(expected_capital_left - observed_capital_left, 2) != 0:
        raise PromotionsOperatorReviewMemoError(
            "Review overlay summary capital-left total does not match the review overlay rows file."
        )

    if _as_int(
        _lookup_summary_metric(
            review_overlay_summary_frame,
            metric_group="PACKET",
            metric_name="PRODUCTION_ORDER_CHANGES",
        )["metric_value"]
    ) != 0:
        raise PromotionsOperatorReviewMemoError(
            "Review overlay summary shows non-zero production order changes."
        )
    if _as_int(
        _lookup_summary_metric(
            review_overlay_summary_frame,
            metric_group="PACKET",
            metric_name="STAGE12_CHANGES",
        )["metric_value"]
    ) != 0:
        raise PromotionsOperatorReviewMemoError(
            "Review overlay summary shows non-zero Stage 12 changes."
        )
    if int(pd.to_numeric(review_overlay_rows_frame["production_order_change_flag"], errors="coerce").fillna(0).sum()) != 0:
        raise PromotionsOperatorReviewMemoError(
            "Review overlay rows include production order changes, which this memo must not promote."
        )
    if int(pd.to_numeric(review_overlay_rows_frame["stage_12_change_flag"], errors="coerce").fillna(0).sum()) != 0:
        raise PromotionsOperatorReviewMemoError(
            "Review overlay rows include Stage 12 changes, which this memo must not promote."
        )

    expected_reason = (
        review_overlay_rows_frame.groupby("overlay_category", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            actual_gross_profit_total=("actual_gross_profit", lambda series: round(float(pd.to_numeric(series, errors="coerce").fillna(0.0).sum()), 2)),
            capital_left_total=("capital_left_in_unsold_store_allocation", lambda series: round(float(pd.to_numeric(series, errors="coerce").fillna(0.0).sum()), 2)),
        )
        .reset_index()
        .set_index("overlay_category")
    )
    provided_reason = review_overlay_by_reason_frame.set_index("overlay_category")
    if set(expected_reason.index.astype(str)) != set(provided_reason.index.astype(str)):
        raise PromotionsOperatorReviewMemoError(
            "Review overlay by-reason categories do not match the review overlay rows file."
        )
    for overlay_category in expected_reason.index.astype(str):
        expected_row = expected_reason.loc[overlay_category]
        provided_row = provided_reason.loc[overlay_category]
        if int(provided_row["row_count"]) != int(expected_row["row_count"]):
            raise PromotionsOperatorReviewMemoError(
                f"Review overlay by-reason row_count mismatch for {overlay_category}."
            )

    expected_department = (
        review_overlay_rows_frame.groupby("department", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            actual_gross_profit_total=("actual_gross_profit", lambda series: round(float(pd.to_numeric(series, errors="coerce").fillna(0.0).sum()), 2)),
            capital_left_total=("capital_left_in_unsold_store_allocation", lambda series: round(float(pd.to_numeric(series, errors="coerce").fillna(0.0).sum()), 2)),
        )
        .reset_index()
        .set_index("department")
    )
    provided_department = review_overlay_by_department_frame.set_index("department")
    if set(expected_department.index.astype(str)) != set(provided_department.index.astype(str)):
        raise PromotionsOperatorReviewMemoError(
            "Review overlay by-department rows do not match the review overlay rows file."
        )
    for department in expected_department.index.astype(str):
        expected_row = expected_department.loc[department]
        provided_row = provided_department.loc[department]
        if int(provided_row["row_count"]) != int(expected_row["row_count"]):
            raise PromotionsOperatorReviewMemoError(
                f"Review overlay by-department row_count mismatch for {department}."
            )


def _build_priority_list_frame(review_overlay_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        review_overlay_rows_frame,
        (
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
            "production_order_change_flag",
            "stage_12_change_flag",
        ),
        frame_name="review_overlay_rows_frame",
    )
    priority_list = review_overlay_rows_frame.loc[
        :,
        (
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
            "production_order_change_flag",
            "stage_12_change_flag",
        ),
    ].copy()
    priority_list["review_priority_rank"] = priority_list["overlay_category"].map(OVERLAY_PRIORITY)
    if priority_list["review_priority_rank"].isna().any():
        categories = sorted(
            priority_list.loc[priority_list["review_priority_rank"].isna(), "overlay_category"].astype(str).drop_duplicates().tolist()
        )
        raise PromotionsOperatorReviewMemoError(
            "Review overlay rows contain unsupported overlay categories: " + ", ".join(categories)
        )
    priority_list["review_priority_rank"] = priority_list["review_priority_rank"].astype(int)
    priority_list["human_review_question"] = priority_list["overlay_category"].map(
        HUMAN_REVIEW_QUESTION_BY_CATEGORY
    )
    priority_list["actual_gross_profit_sort"] = pd.to_numeric(
        priority_list["actual_gross_profit"], errors="coerce"
    ).fillna(0.0)
    priority_list["forecast_error_sort"] = pd.to_numeric(
        priority_list["forecast_error_units"], errors="coerce"
    ).fillna(0.0)
    priority_list = priority_list.sort_values(
        by=["review_priority_rank", "actual_gross_profit_sort", "forecast_error_sort", "sku_number"],
        ascending=[True, False, False, True],
        kind="stable",
    ).drop(columns=["actual_gross_profit_sort", "forecast_error_sort"])
    return priority_list.loc[:, PRIORITY_LIST_COLUMNS].reset_index(drop=True)


def _build_by_category_frame(priority_list_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for overlay_category, group in priority_list_frame.groupby("overlay_category", sort=False, dropna=False):
        rows.append(
            {
                "review_priority_rank": int(group["review_priority_rank"].iloc[0]),
                "overlay_category": str(overlay_category),
                "row_count": int(len(group.index)),
                "actual_units_total": round(float(pd.to_numeric(group["actual_units_sold"], errors="coerce").fillna(0.0).sum()), 2),
                "expected_promo_demand_total": round(float(pd.to_numeric(group["expected_promo_demand"], errors="coerce").fillna(0.0).sum()), 2),
                "actual_gross_profit_total": round(float(pd.to_numeric(group["actual_gross_profit"], errors="coerce").fillna(0.0).sum()), 2),
                "capital_left_total": round(float(pd.to_numeric(group["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0).sum()), 2),
                "proposed_review_action": str(group["proposed_review_action"].iloc[0]),
                "human_review_question": str(group["human_review_question"].iloc[0]),
                "why_review_required": str(group["why_review_required"].iloc[0]),
                "sample_skus": _sample_skus(group["sku_number"]),
            }
        )
    frame = pd.DataFrame(rows, columns=BY_CATEGORY_COLUMNS)
    return frame.sort_values(
        by=["review_priority_rank", "actual_gross_profit_total", "overlay_category"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_by_department_frame(priority_list_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for department, group in priority_list_frame.groupby("department", sort=False, dropna=False):
        ordered_group = group.sort_values(
            by=["review_priority_rank", "actual_gross_profit", "forecast_error_units", "sku_number"],
            ascending=[True, False, False, True],
            kind="stable",
        )
        top_row = ordered_group.iloc[0]
        rows.append(
            {
                "department": str(department),
                "row_count": int(len(group.index)),
                "actual_units_total": round(float(pd.to_numeric(group["actual_units_sold"], errors="coerce").fillna(0.0).sum()), 2),
                "actual_gross_profit_total": round(float(pd.to_numeric(group["actual_gross_profit"], errors="coerce").fillna(0.0).sum()), 2),
                "capital_left_total": round(float(pd.to_numeric(group["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0).sum()), 2),
                "top_overlay_category": str(top_row["overlay_category"]),
                "top_review_priority_rank": int(top_row["review_priority_rank"]),
                "sample_skus": _sample_skus(ordered_group["sku_number"]),
            }
        )
    frame = pd.DataFrame(rows, columns=BY_DEPARTMENT_COLUMNS)
    return frame.sort_values(
        by=["row_count", "actual_gross_profit_total", "department"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_summary_frame(
    *,
    review_overlay_summary_frame: pd.DataFrame,
    priority_list_frame: pd.DataFrame,
    by_category_frame: pd.DataFrame,
    by_department_frame: pd.DataFrame,
) -> pd.DataFrame:
    top_category = by_category_frame.sort_values(
        by=["row_count", "actual_gross_profit_total", "review_priority_rank", "overlay_category"],
        ascending=[False, False, True, True],
        kind="stable",
    ).iloc[0]
    top_department = by_department_frame.iloc[0]
    priority_one = by_category_frame.loc[
        by_category_frame["overlay_category"].astype(str).eq("NO_PRIOR_DEMAND_SURPRISE_REVIEW")
    ]
    if len(priority_one.index) != 1:
        raise PromotionsOperatorReviewMemoError(
            "Expected one NO_PRIOR_DEMAND_SURPRISE_REVIEW row in the operator review category summary."
        )
    priority_one_row = priority_one.iloc[0]
    forecast_correlation = _as_float(
        _lookup_summary_metric(
            review_overlay_summary_frame,
            metric_group="SCOREBOARD",
            metric_name="FORECAST_CORRELATION",
        )["metric_value"]
    )
    forecast_bias_units = _as_float(
        _lookup_summary_metric(
            review_overlay_summary_frame,
            metric_group="SCOREBOARD",
            metric_name="FORECAST_BIAS_UNITS",
        )["metric_value"]
    )
    total_gross_profit = float(pd.to_numeric(priority_list_frame["actual_gross_profit"], errors="coerce").fillna(0.0).sum())
    total_capital_left = float(
        pd.to_numeric(priority_list_frame["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0).sum()
    )

    rows = [
        _summary_row(
            "MEMO_SCOPE",
            "TOTAL_REVIEW_ROWS",
            len(priority_list_frame.index),
            "rows",
            _format_int(len(priority_list_frame.index)),
            "Operator review rows sorted by governed inspection priority.",
        ),
        _summary_row(
            "MEMO_SCOPE",
            "TOTAL_GROSS_PROFIT_REPRESENTED",
            round(total_gross_profit, 2),
            "dollars",
            _format_money(total_gross_profit),
            "Gross profit represented by the operator review memo rows.",
        ),
        _summary_row(
            "MEMO_SCOPE",
            "TOTAL_CAPITAL_LEFT_REPRESENTED",
            round(total_capital_left, 2),
            "dollars",
            _format_money(total_capital_left),
            "Capital left represented by the operator review memo rows.",
        ),
        _summary_row(
            "MEMO_SCOPE",
            "PRIORITY_ONE_ROWS",
            int(priority_one_row["row_count"]),
            "rows",
            _format_int(priority_one_row["row_count"]),
            "Row count in the first inspection set: NO_PRIOR_DEMAND_SURPRISE_REVIEW.",
        ),
        _summary_row(
            "MEMO_SCOPE",
            "TOP_CATEGORY_BY_ROWS",
            int(top_category["row_count"]),
            "rows",
            f"{top_category['overlay_category']} ({_format_int(top_category['row_count'])})",
            "Largest overlay category by row count.",
        ),
        _summary_row(
            "MEMO_SCOPE",
            "TOP_DEPARTMENT_BY_ROWS",
            int(top_department["row_count"]),
            "rows",
            f"{top_department['department']} ({_format_int(top_department['row_count'])})",
            "Largest department by row count.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            0,
            "rows",
            "0",
            "This memo does not change production ordering.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            0,
            "rows",
            "0",
            "This memo does not change Stage 12.",
        ),
        _summary_row(
            "AUTO_ORDERING",
            "STATUS",
            0,
            "flag",
            "BLOCKED",
            "Auto-ordering remains blocked.",
        ),
        _summary_row(
            "AUTO_ORDERING",
            "FORECAST_CORRELATION",
            forecast_correlation,
            "correlation",
            _format_float(forecast_correlation, decimals=3),
            "Forecast correlation remains too weak for auto-ordering promotion.",
        ),
        _summary_row(
            "AUTO_ORDERING",
            "FORECAST_BIAS_UNITS",
            forecast_bias_units,
            "units",
            _format_float(forecast_bias_units, decimals=0, signed=True),
            "Forecast bias remains materially high.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(
    *,
    priority_list_frame: pd.DataFrame,
    by_category_frame: pd.DataFrame,
    by_department_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    review_overlay_memo_text: str,
    manifest: dict[str, object] | None = None,
) -> str:
    priority_one = by_category_frame.loc[
        by_category_frame["overlay_category"].astype(str).eq("NO_PRIOR_DEMAND_SURPRISE_REVIEW")
    ]
    if len(priority_one.index) != 1:
        raise PromotionsOperatorReviewMemoError(
            "Expected one NO_PRIOR_DEMAND_SURPRISE_REVIEW row when building the operator memo."
        )
    priority_one_row = priority_one.iloc[0]
    top_department = by_department_frame.iloc[0]
    forecast_correlation = summary_frame.loc[
        (summary_frame["metric_group"] == "AUTO_ORDERING")
        & (summary_frame["metric_name"] == "FORECAST_CORRELATION"),
        "metric_value",
    ].iloc[0]
    forecast_bias_units = summary_frame.loc[
        (summary_frame["metric_group"] == "AUTO_ORDERING")
        & (summary_frame["metric_name"] == "FORECAST_BIAS_UNITS"),
        "metric_value",
    ].iloc[0]
    action_layer = by_category_frame.loc[
        by_category_frame["overlay_category"].astype(str).eq("ACTION_LAYER_SHADOW_CALIBRATION_REVIEW")
    ]
    action_layer_count = int(action_layer.iloc[0]["row_count"]) if not action_layer.empty else 0
    top_priority_rows = priority_list_frame.loc[
        priority_list_frame["overlay_category"].astype(str).eq("NO_PRIOR_DEMAND_SURPRISE_REVIEW")
    ].head(5)

    lines = [
        "# Operator Review Memo",
        "",
        "This is not an order file. It is a governed human-inspection memo built from the review-overlay packet.",
        "",
        "Start with NO_PRIOR_DEMAND_SURPRISE_REVIEW.",
        (
            f"That first inspection set contains {_format_int(priority_one_row['row_count'])} row(s), "
            f"{_format_money(float(priority_one_row['actual_gross_profit_total']))} gross profit, and "
            f"{_format_money(float(priority_one_row['capital_left_total']))} capital left."
        ),
        f"Use this question first: {priority_one_row['human_review_question']}",
        f"Suggested first SKUs: {priority_one_row['sample_skus']}.",
        "",
        "First inspection list:",
    ]
    for row in top_priority_rows.itertuples(index=False):
        lines.append(
            (
                f"- {row.sku_number} {row.sku_description} ({row.department}): "
                f"gross profit {_format_money(float(row.actual_gross_profit))}, "
                f"forecast error {float(row.forecast_error_units):.1f}, "
                f"question: {row.human_review_question}"
            )
        )

    lines.extend(
        [
            "",
            "Production order changes = 0.",
            "Stage 12 changes = 0.",
            "",
            "Auto-ordering remains blocked.",
            (
                f"Forecast correlation remains {_format_float(float(forecast_correlation), decimals=3)} and forecast bias remains "
                f"{_format_float(float(forecast_bias_units), decimals=0, signed=True)} units."
            ),
            (
                f"The action-layer calibration slice still has {_format_int(action_layer_count)} row(s), so that response must stay shadow-only until repeated evidence improves trust."
            ),
            "",
            (
                f"The largest department slice is {top_department['department']} with {_format_int(top_department['row_count'])} row(s) "
                f"and {_format_money(float(top_department['actual_gross_profit_total']))} gross profit represented."
            ),
            "",
            "Recommendation:",
            "Inspect the no-prior demand surprise rows first, then move to true low-SOH missed demand and online floor-protection cases before reviewing capital-drag headline corrections. Keep action-layer calibration shadow-only and limit zero-order text cases to wording cleanup.",
            "",
            f"Source certification: {manifest.get('source_certification_status', 'UNKNOWN') if manifest else 'UNKNOWN'}.",
        ]
    )
    if review_overlay_memo_text.strip():
        lines.extend(
            [
                "",
                "The upstream review-overlay packet already confirmed this remains a review-only inspection workflow.",
            ]
        )
    return "\n".join(lines) + "\n"


def build_promotions_operator_review_memo(
    *,
    review_overlay_summary_frame: pd.DataFrame,
    review_overlay_rows_frame: pd.DataFrame,
    review_overlay_by_reason_frame: pd.DataFrame,
    review_overlay_by_department_frame: pd.DataFrame,
    review_overlay_memo_text: str,
    manifest: dict[str, object] | None = None,
) -> PromotionsOperatorReviewMemoResult:
    _validate_overlay_inputs(
        review_overlay_summary_frame=review_overlay_summary_frame,
        review_overlay_rows_frame=review_overlay_rows_frame,
        review_overlay_by_reason_frame=review_overlay_by_reason_frame,
        review_overlay_by_department_frame=review_overlay_by_department_frame,
        review_overlay_memo_text=review_overlay_memo_text,
    )
    priority_list_frame = _build_priority_list_frame(review_overlay_rows_frame)
    by_category_frame = _build_by_category_frame(priority_list_frame)
    by_department_frame = _build_by_department_frame(priority_list_frame)
    summary_frame = _build_summary_frame(
        review_overlay_summary_frame=review_overlay_summary_frame,
        priority_list_frame=priority_list_frame,
        by_category_frame=by_category_frame,
        by_department_frame=by_department_frame,
    )
    memo_markdown = _build_memo(
        priority_list_frame=priority_list_frame,
        by_category_frame=by_category_frame,
        by_department_frame=by_department_frame,
        summary_frame=summary_frame,
        review_overlay_memo_text=review_overlay_memo_text,
        manifest=manifest,
    )
    return PromotionsOperatorReviewMemoResult(
        priority_list_frame=priority_list_frame,
        summary_frame=summary_frame,
        by_category_frame=by_category_frame,
        by_department_frame=by_department_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_operator_review_memo(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsOperatorReviewMemoArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsOperatorReviewMemoError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    packet_root = review_artifact_path / "review_overlay_packet"
    result = build_promotions_operator_review_memo(
        review_overlay_summary_frame=_read_csv(packet_root / "review_overlay_packet_summary.csv"),
        review_overlay_rows_frame=_read_csv(packet_root / "review_overlay_packet_rows.csv"),
        review_overlay_by_reason_frame=_read_csv(packet_root / "review_overlay_packet_by_reason.csv"),
        review_overlay_by_department_frame=_read_csv(packet_root / "review_overlay_packet_by_department.csv"),
        review_overlay_memo_text=(packet_root / "review_overlay_packet_memo.md").read_text(encoding="utf-8"),
        manifest=manifest,
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else packet_root / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    priority_list_csv_path = destination_root / "operator_review_priority_list.csv"
    summary_csv_path = destination_root / "operator_review_summary.csv"
    by_category_csv_path = destination_root / "operator_review_by_category.csv"
    by_department_csv_path = destination_root / "operator_review_by_department.csv"
    memo_md_path = destination_root / "operator_review_memo.md"

    add_provenance_columns(result.priority_list_frame.copy(), manifest).to_csv(
        priority_list_csv_path,
        index=False,
    )
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(
        summary_csv_path,
        index=False,
    )
    add_provenance_columns(result.by_category_frame.copy(), manifest).to_csv(
        by_category_csv_path,
        index=False,
    )
    add_provenance_columns(result.by_department_frame.copy(), manifest).to_csv(
        by_department_csv_path,
        index=False,
    )
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsOperatorReviewMemoArtifacts(
        priority_list_csv_path=str(priority_list_csv_path),
        summary_csv_path=str(summary_csv_path),
        by_category_csv_path=str(by_category_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed operator review memo from the review-overlay packet."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_operator_review_memo(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("operator_review_priority_list", artifacts.priority_list_csv_path)
    print("operator_review_summary", artifacts.summary_csv_path)
    print("operator_review_by_category", artifacts.by_category_csv_path)
    print("operator_review_by_department", artifacts.by_department_csv_path)
    print("operator_review_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())