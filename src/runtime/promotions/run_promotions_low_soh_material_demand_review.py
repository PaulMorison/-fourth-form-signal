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
from runtime.promotions.run_promotions_model_vs_actual_review import (
    MATERIAL_ACTUAL_UNITS,
    MATERIAL_CAPITAL_LEFT,
    MATERIAL_UNIT_DELTA,
)


TARGET_ISSUE_TYPES: tuple[str, ...] = (
    "LOW_SOH_NO_AUTO_BUY_BUT_ACTUAL_DEMAND",
    "LOW_SOH_OR_FLOOR_RISK_WITH_MATERIAL_DEMAND_NO_REVIEW_ACTION",
)
OUTPUT_FOLDER_NAME = "low_soh_material_demand_review"

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    "model_vs_actual_report_cleanup_issues.csv",
    "report_contract_cleanup_summary.csv",
    "model_vs_actual_summary.csv",
    "action_layer_recalibration_rows.csv",
)

ROWS_OUTPUT_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "operator_decision",
    "operator_action",
    "order_units",
    "reason_short",
    "risk_flag",
    "review_flag",
    "audit_notes",
    "actual_units_sold",
    "store_adjusted_qty",
    "actual_sell_through_vs_store_adjusted",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "expected_promo_demand",
    "forecast_error_units",
    "current_soh_units",
    "on_order_units",
    "projected_on_hand_at_promo_start",
    "target_stock_day_one_units",
    "available_to_sell_before_floor",
    "projected_stock_gap_units",
    "recommended_order_units",
    "final_store_order_units",
    "availability_risk_label",
    "demand_evidence_label",
    "store_action_label",
    "issue_type_evidence",
    "explicit_issue_alias_flag",
    "covered_by_on_order_flag",
    "projected_covers_target_flag",
    "material_underforecast_flag",
    "diagnostic_classification",
    "proposed_next_action",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "summary_kind",
    "label_name",
    "row_count",
    "actual_units_total",
    "actual_gross_profit_total",
    "capital_left_total",
    "average_forecast_error_units",
    "average_projected_stock_gap_units",
    "covered_by_on_order_rows",
    "explicit_issue_alias_rows",
    "material_underforecast_rows",
    "share_of_remaining_cleanup_issues",
    "sample_skus",
)

BY_DEPARTMENT_COLUMNS: tuple[str, ...] = (
    "department",
    "row_count",
    "actual_units_total",
    "actual_gross_profit_total",
    "capital_left_total",
    "average_forecast_error_units",
    "average_projected_stock_gap_units",
    "covered_by_on_order_rows",
    "explicit_issue_alias_rows",
    "true_low_soh_missed_demand_rows",
    "online_floor_protection_review_rows",
    "low_soh_but_covered_by_on_order_rows",
    "forecast_undercalibration_low_soh_rows",
    "no_change_capital_protected_rows",
    "data_or_label_conflict_rows",
    "top_proposed_next_action",
    "sample_skus",
)

ACTION_RECOMMENDATION_COLUMNS: tuple[str, ...] = (
    "recommendation_scope",
    "proposed_next_action",
    "diagnostic_classification",
    "department",
    "row_count",
    "actual_gross_profit_total",
    "capital_left_total",
    "sample_skus",
    "rationale",
)

CLASSIFICATION_PRIORITY: dict[str, int] = {
    "TRUE_LOW_SOH_MISSED_DEMAND": 1,
    "ONLINE_FLOOR_PROTECTION_REVIEW": 2,
    "FORECAST_UNDERCALIBRATION_LOW_SOH": 3,
    "LOW_SOH_BUT_COVERED_BY_ON_ORDER": 4,
    "NO_CHANGE_CAPITAL_PROTECTED": 5,
    "DATA_OR_LABEL_CONFLICT": 6,
}

ACTION_PRIORITY: dict[str, int] = {
    "ADD_LOW_SOH_REVIEW_FLAG": 1,
    "ADD_ONLINE_FLOOR_REVIEW_FLAG": 2,
    "IMPROVE_LOW_SOH_DEMAND_CALIBRATION": 3,
    "KEEP_CURRENT_GUARDRAIL": 4,
    "NO_CHANGE": 5,
    "INSPECT_DATA_CONFLICT": 6,
}


class PromotionsLowSohMaterialDemandReviewError(RuntimeError):
    """Raised when the low-SOH material-demand review cannot run safely."""


@dataclass(frozen=True)
class PromotionsLowSohMaterialDemandReviewResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    action_recommendations_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsLowSohMaterialDemandReviewArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    by_department_csv_path: str
    action_recommendations_csv_path: str
    memo_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsLowSohMaterialDemandReviewError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsLowSohMaterialDemandReviewError(
            f"Manifest must be a JSON object: {path}"
        )
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
        raise PromotionsLowSohMaterialDemandReviewError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsLowSohMaterialDemandReviewError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _prepare_join_frame(
    frame: pd.DataFrame,
    *,
    frame_name: str,
    columns: Sequence[str],
) -> pd.DataFrame:
    _require_columns(frame, columns, frame_name=frame_name)
    subset = frame.loc[:, columns].copy()
    subset["_sku_key"] = _normalize_identifier(subset["sku_number"])
    if subset["_sku_key"].eq("").any():
        blank_count = int(subset["_sku_key"].eq("").sum())
        raise PromotionsLowSohMaterialDemandReviewError(
            f"{frame_name} has blank sku_number values after normalization (rows={blank_count})"
        )
    duplicate_mask = subset["_sku_key"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicate_values = subset.loc[duplicate_mask, "_sku_key"].head(10).tolist()
        sample = ", ".join(duplicate_values)
        raise PromotionsLowSohMaterialDemandReviewError(
            f"{frame_name} has duplicate sku_number values after normalization: {sample}"
        )
    return subset.drop(columns=["sku_number"])


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


def _remaining_cleanup_issue_count(cleanup_summary_frame: pd.DataFrame) -> int:
    if cleanup_summary_frame.empty:
        return 0
    summary_rows = cleanup_summary_frame.loc[
        cleanup_summary_frame["issue_type"].astype(str).eq("TOTAL_REMAINING_CLEANUP_ISSUES")
    ]
    if summary_rows.empty:
        return 0
    return int(pd.to_numeric(summary_rows["issue_count"], errors="coerce").fillna(0.0).iloc[0])


def _label_contains_low_soh_or_floor_risk(*values: object) -> bool:
    for value in values:
        token = _normalize_token(value)
        if not token:
            continue
        if "low_soh" in token:
            return True
        if "floor" in token:
            return True
        if "availability" in token:
            return True
        if token.startswith("below_") and "risk" in token:
            return True
    return False


def _has_direct_low_soh_signal(*values: object) -> bool:
    for value in values:
        token = _normalize_token(value)
        if not token:
            continue
        if "low_soh" in token:
            return True
        if "below_2_unit" in token:
            return True
        if "zero_soh" in token:
            return True
    return False


def _has_floor_protection_signal(*values: object) -> bool:
    for value in values:
        token = _normalize_token(value)
        if not token:
            continue
        if "floor_protection" in token:
            return True
        if "hold_stock_floor_safe" in token:
            return True
    return False


def _has_clear_review_state(row: pd.Series) -> bool:
    decision_token = _normalize_token(row["operator_decision"])
    action_token = _normalize_token(row["operator_action"])
    review_token = _normalize_token(row["review_flag"])
    review_numeric = pd.to_numeric(pd.Series([row["review_flag"]]), errors="coerce").iloc[0]
    review_is_positive = pd.notna(review_numeric) and float(review_numeric) >= 1.0
    return (
        decision_token == "review"
        or action_token == "review"
        or "manual_review" in action_token
        or review_token == "review"
        or review_is_positive
    )


def _is_material_underforecast(row: pd.Series) -> bool:
    actual_units = float(row["actual_units_sold"])
    expected_units = float(row["expected_promo_demand"])
    forecast_error = float(
        row.get("forecast_error_units", row.get("forecast_abs_error_units", 0.0))
    )
    return forecast_error >= MATERIAL_UNIT_DELTA or (actual_units - expected_units) >= MATERIAL_UNIT_DELTA


def _build_issue_alias_lookup(cleanup_issue_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        cleanup_issue_frame,
        ("sku_number", "issue_type"),
        frame_name="cleanup_issue_frame",
    )
    if cleanup_issue_frame.empty:
        return pd.DataFrame(columns=["_sku_key", "issue_type_evidence"])

    issue_rows = cleanup_issue_frame.loc[
        cleanup_issue_frame["issue_type"].astype(str).isin(TARGET_ISSUE_TYPES),
        ["sku_number", "issue_type"],
    ].copy()
    if issue_rows.empty:
        return pd.DataFrame(columns=["_sku_key", "issue_type_evidence"])

    issue_rows["_sku_key"] = _normalize_identifier(issue_rows["sku_number"])
    issue_rows = issue_rows.loc[issue_rows["_sku_key"].ne("")].copy()
    lookup = (
        issue_rows.groupby("_sku_key", sort=False)["issue_type"]
        .agg(lambda values: "|".join(sorted({str(value).strip() for value in values if str(value).strip()})))
        .reset_index(name="issue_type_evidence")
    )
    return lookup


def _classify_row(row: pd.Series) -> str:
    if not bool(row["low_soh_or_floor_risk_flag"]) or bool(row["clear_review_action_flag"]):
        return "DATA_OR_LABEL_CONFLICT"
    if float(row["actual_units_sold"]) < MATERIAL_ACTUAL_UNITS:
        return "DATA_OR_LABEL_CONFLICT"

    covered = bool(row["covered_by_on_order_flag"]) or bool(row["projected_covers_target_flag"])
    capital_left = float(
        row.get(
            "capital_left_in_unsold_store_allocation",
            row.get("capital_left_unsold", 0.0),
        )
    )
    if covered and capital_left >= MATERIAL_CAPITAL_LEFT:
        return "NO_CHANGE_CAPITAL_PROTECTED"
    if covered:
        return "LOW_SOH_BUT_COVERED_BY_ON_ORDER"

    if _has_direct_low_soh_signal(
        row["store_action_label"],
        row["risk_flag"],
        row["availability_risk_label"],
        row["demand_evidence_label"],
    ):
        return "TRUE_LOW_SOH_MISSED_DEMAND"

    if _has_floor_protection_signal(
        row["availability_risk_label"],
        row["demand_evidence_label"],
        row["store_action_label"],
    ):
        return "ONLINE_FLOOR_PROTECTION_REVIEW"

    if bool(row["material_underforecast_flag"]):
        return "FORECAST_UNDERCALIBRATION_LOW_SOH"

    return "DATA_OR_LABEL_CONFLICT"


def _proposed_next_action(classification: str) -> str:
    if classification == "TRUE_LOW_SOH_MISSED_DEMAND":
        return "ADD_LOW_SOH_REVIEW_FLAG"
    if classification == "ONLINE_FLOOR_PROTECTION_REVIEW":
        return "ADD_ONLINE_FLOOR_REVIEW_FLAG"
    if classification == "FORECAST_UNDERCALIBRATION_LOW_SOH":
        return "IMPROVE_LOW_SOH_DEMAND_CALIBRATION"
    if classification == "NO_CHANGE_CAPITAL_PROTECTED":
        return "KEEP_CURRENT_GUARDRAIL"
    if classification == "LOW_SOH_BUT_COVERED_BY_ON_ORDER":
        return "NO_CHANGE"
    return "INSPECT_DATA_CONFLICT"


def _build_rows_frame(
    *,
    cleanup_issue_frame: pd.DataFrame,
    recalibration_rows_frame: pd.DataFrame,
    visible_report_frame: pd.DataFrame,
    audit_report_frame: pd.DataFrame,
) -> pd.DataFrame:
    issue_alias_lookup = _build_issue_alias_lookup(cleanup_issue_frame)
    recalibration_rows = _prepare_join_frame(
        recalibration_rows_frame,
        frame_name="action_layer_recalibration_rows",
        columns=(
            "sku_number",
            "department",
            "actual_units_sold",
            "store_adjusted_units",
            "actual_sell_through_vs_store_adjusted",
            "estimated_actual_gross_profit",
            "capital_left_unsold",
            "expected_promo_demand",
            "forecast_abs_error_units",
            "availability_risk_label",
            "store_action_label",
            "demand_label",
        ),
    )
    visible_rows = _prepare_join_frame(
        visible_report_frame,
        frame_name="visible_report_frame",
        columns=(
            "sku_number",
            "sku_description",
            "operator_decision",
            "operator_action",
            "order_units",
            "reason_short",
            "risk_flag",
            "review_flag",
            "audit_notes",
        ),
    )
    audit_rows = _prepare_join_frame(
        audit_report_frame,
        frame_name="audit_report_frame",
        columns=(
            "sku_number",
            "recommended_order_units",
            "final_store_order_units",
            "availability_risk_label",
            "demand_evidence_label",
            "current_soh",
            "on_order_at_advice_time",
            "projected_on_hand_at_promo_start",
            "projected_SOH_at_promo_start",
            "target_stock_day_one_units",
            "target_SOH_at_promo_start",
            "minimum_launch_stock_units",
            "floor_units_required",
            "available_to_sell_before_floor",
            "projected_stock_gap_units",
        ),
    )

    rows = recalibration_rows.loc[:, ["_sku_key", "department", "actual_units_sold", "store_adjusted_units", "actual_sell_through_vs_store_adjusted", "estimated_actual_gross_profit", "capital_left_unsold", "expected_promo_demand", "forecast_abs_error_units", "availability_risk_label", "store_action_label", "demand_label"]].copy()
    rows = rows.rename(columns={"availability_risk_label": "slice_availability_risk_label"})
    rows = rows.merge(visible_rows, on="_sku_key", how="left", validate="one_to_one")
    rows = rows.merge(audit_rows, on="_sku_key", how="left", validate="one_to_one")
    rows = rows.merge(issue_alias_lookup, on="_sku_key", how="left", validate="one_to_one")

    required_join_columns = (
        "sku_description",
        "operator_decision",
        "operator_action",
        "order_units",
        "reason_short",
        "risk_flag",
        "review_flag",
        "recommended_order_units",
        "final_store_order_units",
        "availability_risk_label",
        "demand_evidence_label",
        "current_soh",
        "on_order_at_advice_time",
        "projected_on_hand_at_promo_start",
        "projected_SOH_at_promo_start",
        "target_stock_day_one_units",
        "target_SOH_at_promo_start",
        "minimum_launch_stock_units",
        "floor_units_required",
        "available_to_sell_before_floor",
        "projected_stock_gap_units",
    )
    missing_mask = rows.loc[:, required_join_columns].isna().any(axis=1)
    if missing_mask.any():
        missing_skus = rows.loc[missing_mask, "_sku_key"].astype(str).head(10).tolist()
        sample = ", ".join(missing_skus)
        raise PromotionsLowSohMaterialDemandReviewError(
            "low-SOH material-demand review inputs are missing joined row context for sku_number values: "
            + sample
        )

    rows["sku_number"] = rows["_sku_key"].astype(str)
    text_columns = (
        "sku_number",
        "sku_description",
        "department",
        "operator_decision",
        "operator_action",
        "reason_short",
        "risk_flag",
        "audit_notes",
        "availability_risk_label",
        "demand_evidence_label",
        "store_action_label",
        "demand_label",
        "issue_type_evidence",
    )
    for column_name in text_columns:
        rows[column_name] = rows[column_name].fillna("").astype(str).str.strip()

    numeric_columns = (
        "order_units",
        "review_flag",
        "actual_units_sold",
        "store_adjusted_units",
        "actual_sell_through_vs_store_adjusted",
        "estimated_actual_gross_profit",
        "capital_left_unsold",
        "expected_promo_demand",
        "forecast_abs_error_units",
        "recommended_order_units",
        "final_store_order_units",
        "current_soh",
        "on_order_at_advice_time",
        "projected_on_hand_at_promo_start",
        "projected_SOH_at_promo_start",
        "target_stock_day_one_units",
        "target_SOH_at_promo_start",
        "minimum_launch_stock_units",
        "floor_units_required",
        "available_to_sell_before_floor",
        "projected_stock_gap_units",
    )
    for column_name in numeric_columns:
        rows[column_name] = pd.to_numeric(rows[column_name], errors="coerce").fillna(0.0)

    rows["projected_on_hand_at_promo_start"] = rows["projected_on_hand_at_promo_start"].where(
        rows["projected_on_hand_at_promo_start"].ne(0.0),
        rows["projected_SOH_at_promo_start"],
    )
    rows["target_stock_day_one_units"] = rows["target_stock_day_one_units"].where(
        rows["target_stock_day_one_units"].gt(0.0),
        rows["target_SOH_at_promo_start"],
    )
    rows["target_stock_day_one_units"] = rows["target_stock_day_one_units"].where(
        rows["target_stock_day_one_units"].gt(0.0),
        rows["minimum_launch_stock_units"],
    )
    rows["target_stock_day_one_units"] = rows["target_stock_day_one_units"].where(
        rows["target_stock_day_one_units"].gt(0.0),
        rows["floor_units_required"],
    )

    rows["current_soh_units"] = rows["current_soh"]
    rows["on_order_units"] = rows["on_order_at_advice_time"]
    coverage_target = rows["target_stock_day_one_units"].clip(lower=1.0)
    rows["low_soh_or_floor_risk_flag"] = rows.apply(
        lambda row: _label_contains_low_soh_or_floor_risk(
            row["operator_decision"],
            row["risk_flag"],
            row["slice_availability_risk_label"],
            row["store_action_label"],
        ),
        axis=1,
    )
    rows["clear_review_action_flag"] = rows.apply(_has_clear_review_state, axis=1)
    rows["covered_by_on_order_flag"] = rows["current_soh_units"].add(rows["on_order_units"]).ge(coverage_target)
    rows["projected_covers_target_flag"] = rows["projected_on_hand_at_promo_start"].ge(coverage_target)
    rows["material_underforecast_flag"] = rows.apply(_is_material_underforecast, axis=1)
    rows["explicit_issue_alias_flag"] = rows["issue_type_evidence"].ne("")

    candidate_mask = (
        rows["low_soh_or_floor_risk_flag"]
        & rows["actual_units_sold"].ge(MATERIAL_ACTUAL_UNITS)
        & ~rows["clear_review_action_flag"]
    )
    rows = rows.loc[candidate_mask].copy()
    if rows.empty:
        return pd.DataFrame(columns=ROWS_OUTPUT_COLUMNS)

    rows["diagnostic_classification"] = rows.apply(_classify_row, axis=1)
    rows["proposed_next_action"] = rows["diagnostic_classification"].map(_proposed_next_action)
    rows["review_flag"] = rows["review_flag"].round(0).astype(int)
    rows["explicit_issue_alias_flag"] = rows["explicit_issue_alias_flag"].astype(int)
    rows["covered_by_on_order_flag"] = rows["covered_by_on_order_flag"].astype(int)
    rows["projected_covers_target_flag"] = rows["projected_covers_target_flag"].astype(int)
    rows["material_underforecast_flag"] = rows["material_underforecast_flag"].astype(int)

    rows = rows.rename(
        columns={
            "store_adjusted_units": "store_adjusted_qty",
            "estimated_actual_gross_profit": "actual_gross_profit",
            "capital_left_unsold": "capital_left_in_unsold_store_allocation",
            "forecast_abs_error_units": "forecast_error_units",
        }
    )

    rows["_classification_priority"] = (
        rows["diagnostic_classification"].map(CLASSIFICATION_PRIORITY).fillna(99)
    )
    rows = rows.sort_values(
        by=[
            "_classification_priority",
            "forecast_error_units",
            "projected_stock_gap_units",
            "actual_units_sold",
            "sku_number",
        ],
        ascending=[True, False, False, False, True],
        kind="stable",
    ).drop(columns=["_classification_priority", "_sku_key", "current_soh", "on_order_at_advice_time", "projected_SOH_at_promo_start", "target_SOH_at_promo_start", "minimum_launch_stock_units", "floor_units_required", "demand_label", "slice_availability_risk_label", "low_soh_or_floor_risk_flag", "clear_review_action_flag"])
    return rows.loc[:, ROWS_OUTPUT_COLUMNS].reset_index(drop=True)


def _build_summary_frame(
    rows_frame: pd.DataFrame,
    *,
    cleanup_summary_frame: pd.DataFrame,
) -> pd.DataFrame:
    total_cleanup_issues = _remaining_cleanup_issue_count(cleanup_summary_frame)

    def summarize(label_name: str, frame: pd.DataFrame, *, summary_kind: str) -> dict[str, object]:
        row_count = int(len(frame.index))
        share = 0.0 if total_cleanup_issues <= 0 else row_count / float(total_cleanup_issues)
        return {
            "summary_kind": summary_kind,
            "label_name": label_name,
            "row_count": row_count,
            "actual_units_total": round(float(frame["actual_units_sold"].sum()), 2) if row_count else 0.0,
            "actual_gross_profit_total": round(float(frame["actual_gross_profit"].sum()), 2) if row_count else 0.0,
            "capital_left_total": round(float(frame["capital_left_in_unsold_store_allocation"].sum()), 2) if row_count else 0.0,
            "average_forecast_error_units": round(float(frame["forecast_error_units"].mean()), 4) if row_count else 0.0,
            "average_projected_stock_gap_units": round(float(frame["projected_stock_gap_units"].mean()), 4) if row_count else 0.0,
            "covered_by_on_order_rows": int(frame["covered_by_on_order_flag"].sum()) if row_count else 0,
            "explicit_issue_alias_rows": int(frame["explicit_issue_alias_flag"].sum()) if row_count else 0,
            "material_underforecast_rows": int(frame["material_underforecast_flag"].sum()) if row_count else 0,
            "share_of_remaining_cleanup_issues": round(float(share), 6),
            "sample_skus": _sample_skus(frame["sku_number"]) if row_count else "",
        }

    if rows_frame.empty:
        return pd.DataFrame([summarize("ALL_ROWS", rows_frame, summary_kind="TOTAL")], columns=SUMMARY_COLUMNS)

    summary_rows = [summarize("ALL_ROWS", rows_frame, summary_kind="TOTAL")]
    for classification, group in rows_frame.groupby("diagnostic_classification", sort=False, dropna=False):
        summary_rows.append(summarize(str(classification), group, summary_kind="CLASSIFICATION"))
    summary_frame = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    return summary_frame.sort_values(
        by=["summary_kind", "row_count", "label_name"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_by_department_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_DEPARTMENT_COLUMNS)

    records: list[dict[str, object]] = []
    grouped = rows_frame.groupby("department", sort=False, dropna=False)
    for department, group in grouped:
        action_count_rows = (
            group["proposed_next_action"]
            .value_counts(dropna=False)
            .rename_axis("proposed_next_action")
            .reset_index(name="row_count")
        )
        if action_count_rows.empty:
            top_action = ""
        else:
            action_count_rows["action_priority"] = (
                action_count_rows["proposed_next_action"].map(ACTION_PRIORITY).fillna(99)
            )
            action_count_rows = action_count_rows.sort_values(
                by=["row_count", "action_priority", "proposed_next_action"],
                ascending=[False, True, True],
                kind="stable",
            )
            top_action = str(action_count_rows.iloc[0]["proposed_next_action"])

        records.append(
            {
                "department": str(department),
                "row_count": int(len(group.index)),
                "actual_units_total": round(float(group["actual_units_sold"].sum()), 2),
                "actual_gross_profit_total": round(float(group["actual_gross_profit"].sum()), 2),
                "capital_left_total": round(float(group["capital_left_in_unsold_store_allocation"].sum()), 2),
                "average_forecast_error_units": round(float(group["forecast_error_units"].mean()), 4),
                "average_projected_stock_gap_units": round(float(group["projected_stock_gap_units"].mean()), 4),
                "covered_by_on_order_rows": int(group["covered_by_on_order_flag"].sum()),
                "explicit_issue_alias_rows": int(group["explicit_issue_alias_flag"].sum()),
                "true_low_soh_missed_demand_rows": int(group["diagnostic_classification"].eq("TRUE_LOW_SOH_MISSED_DEMAND").sum()),
                "online_floor_protection_review_rows": int(group["diagnostic_classification"].eq("ONLINE_FLOOR_PROTECTION_REVIEW").sum()),
                "low_soh_but_covered_by_on_order_rows": int(group["diagnostic_classification"].eq("LOW_SOH_BUT_COVERED_BY_ON_ORDER").sum()),
                "forecast_undercalibration_low_soh_rows": int(group["diagnostic_classification"].eq("FORECAST_UNDERCALIBRATION_LOW_SOH").sum()),
                "no_change_capital_protected_rows": int(group["diagnostic_classification"].eq("NO_CHANGE_CAPITAL_PROTECTED").sum()),
                "data_or_label_conflict_rows": int(group["diagnostic_classification"].eq("DATA_OR_LABEL_CONFLICT").sum()),
                "top_proposed_next_action": top_action,
                "sample_skus": _sample_skus(group["sku_number"]),
            }
        )

    by_department_frame = pd.DataFrame(records, columns=BY_DEPARTMENT_COLUMNS)
    return by_department_frame.sort_values(
        by=["row_count", "actual_gross_profit_total", "department"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _action_rationale(action_name: str) -> str:
    if action_name == "ADD_LOW_SOH_REVIEW_FLAG":
        return "Material demand landed on a direct low-SOH row with no visible review state, so the next step should be an explicit review flag rather than an automatic buy promotion."
    if action_name == "ADD_ONLINE_FLOOR_REVIEW_FLAG":
        return "The row looks like floor protection or online availability suppression, so the visible report should surface a review-only floor flag instead of a silent no-order outcome."
    if action_name == "IMPROVE_LOW_SOH_DEMAND_CALIBRATION":
        return "The low-SOH guardrail likely stayed in place because demand calibration understated realized demand, so the next action is calibration work, not a production ordering change."
    if action_name == "KEEP_CURRENT_GUARDRAIL":
        return "Existing stock cover and residual capital indicate the guardrail is still doing its job and should stay unchanged."
    if action_name == "NO_CHANGE":
        return "Existing or inbound stock already covers the day-one target, so this row does not need a new review state or policy change."
    return "The row does not fit the expected low-SOH or floor-risk pattern cleanly and should be inspected before any contract change is considered."


def _build_action_recommendations_frame(
    rows_frame: pd.DataFrame,
    *,
    by_department_frame: pd.DataFrame,
) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=ACTION_RECOMMENDATION_COLUMNS)

    records: list[dict[str, object]] = []
    grouped = rows_frame.groupby("proposed_next_action", sort=False, dropna=False)
    for action_name, group in grouped:
        classifications = ", ".join(
            group["diagnostic_classification"].astype(str).drop_duplicates().tolist()
        )
        records.append(
            {
                "recommendation_scope": "ROW_CLASSIFICATION",
                "proposed_next_action": str(action_name),
                "diagnostic_classification": classifications,
                "department": "",
                "row_count": int(len(group.index)),
                "actual_gross_profit_total": round(float(group["actual_gross_profit"].sum()), 2),
                "capital_left_total": round(float(group["capital_left_in_unsold_store_allocation"].sum()), 2),
                "sample_skus": _sample_skus(group["sku_number"]),
                "rationale": _action_rationale(str(action_name)),
            }
        )

    clustered_departments = by_department_frame.loc[by_department_frame["row_count"] >= 3].copy()
    for _, row in clustered_departments.iterrows():
        department_rows = rows_frame.loc[
            rows_frame["department"].astype(str).eq(str(row["department"]))
        ]
        dominant_classification = ""
        if not department_rows.empty:
            dominant_classification = str(
                department_rows["diagnostic_classification"].value_counts().idxmax()
            )
        records.append(
            {
                "recommendation_scope": "DEPARTMENT_PATTERN",
                "proposed_next_action": "INSPECT_DATA_CONFLICT",
                "diagnostic_classification": dominant_classification,
                "department": str(row["department"]),
                "row_count": int(row["row_count"]),
                "actual_gross_profit_total": round(float(row["actual_gross_profit_total"]), 2),
                "capital_left_total": round(float(row["capital_left_total"]), 2),
                "sample_skus": str(row["sample_skus"]),
                "rationale": "This department carries a concentrated low-SOH or floor-risk pattern and should be inspected before broadening any review-state vocabulary.",
            }
        )

    recommendations_frame = pd.DataFrame(records, columns=ACTION_RECOMMENDATION_COLUMNS)
    recommendations_frame["_action_priority"] = recommendations_frame["proposed_next_action"].map(ACTION_PRIORITY).fillna(99)
    recommendations_frame["_scope_priority"] = recommendations_frame["recommendation_scope"].map(
        {"ROW_CLASSIFICATION": 1, "DEPARTMENT_PATTERN": 2}
    ).fillna(99)
    recommendations_frame = recommendations_frame.sort_values(
        by=["_scope_priority", "_action_priority", "row_count", "department"],
        ascending=[True, True, False, True],
        kind="stable",
    ).drop(columns=["_action_priority", "_scope_priority"])
    return recommendations_frame.reset_index(drop=True)


def _build_memo(
    *,
    rows_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    by_department_frame: pd.DataFrame,
    cleanup_summary_frame: pd.DataFrame,
    manifest: dict[str, object] | None,
) -> str:
    del summary_frame
    manifest = manifest or {}
    total_rows = int(len(rows_frame.index))
    total_cleanup_issues = _remaining_cleanup_issue_count(cleanup_summary_frame)
    gross_profit_total = round(float(rows_frame["actual_gross_profit"].sum()), 2) if total_rows else 0.0
    capital_left_total = round(float(rows_frame["capital_left_in_unsold_store_allocation"].sum()), 2) if total_rows else 0.0
    explicit_issue_alias_rows = int(rows_frame["explicit_issue_alias_flag"].sum()) if total_rows else 0
    counts = rows_frame["diagnostic_classification"].value_counts().to_dict() if total_rows else {}

    def count(label_name: str) -> int:
        return int(counts.get(label_name, 0))

    share_text = "0.00%"
    if total_cleanup_issues > 0:
        share_text = f"{(total_rows / float(total_cleanup_issues)) * 100.0:.2f}%"

    top_departments_text = "None."
    if not by_department_frame.empty:
        top_departments = []
        for _, row in by_department_frame.head(3).iterrows():
            top_departments.append(
                f"{row['department']}: {int(row['row_count'])} rows, ${float(row['actual_gross_profit_total']):.2f} gross profit, ${float(row['capital_left_total']):.2f} capital left"
            )
        top_departments_text = "\n".join(f"- {entry}" for entry in top_departments)

    recommendation_lines = [
        "Keep this pass diagnostics-only and review-oriented; do not convert these rows into automatic buy promotions.",
    ]
    if count("TRUE_LOW_SOH_MISSED_DEMAND") > 0:
        recommendation_lines.append(
            "Add a visible low-SOH review flag for direct low-SOH misses where material demand landed with no explicit review state."
        )
    if count("ONLINE_FLOOR_PROTECTION_REVIEW") > 0:
        recommendation_lines.append(
            "Add a separate online or floor-protection review flag for floor-risk rows that were suppressed but still converted materially."
        )
    if count("FORECAST_UNDERCALIBRATION_LOW_SOH") > 0:
        recommendation_lines.append(
            f"Treat material low-SOH misses with forecast error of at least {int(MATERIAL_UNIT_DELTA)} units as calibration work first, not as an ordering-policy promotion."
        )
    if count("LOW_SOH_BUT_COVERED_BY_ON_ORDER") > 0 or count("NO_CHANGE_CAPITAL_PROTECTED") > 0:
        recommendation_lines.append(
            "Keep the current guardrail unchanged where existing or inbound stock already covers the day-one target."
        )
    if count("DATA_OR_LABEL_CONFLICT") > 0:
        recommendation_lines.append(
            "Inspect rows that only match the slice through broad availability wording before changing the cleaned visible contract."
        )

    memo_lines = [
        "# Low-SOH / Floor-Risk Material-Demand Review",
        "",
        "## 1. Governed scope",
        "- Diagnostics-only pass over the validated clean-visible model-vs-actual review outputs.",
        "- No production ordering logic was changed.",
        "- No Stage 12 logic was changed.",
        "- No cleaned visible operator-contract fields were changed in this pass.",
        "",
        "## 2. Evidence base",
        f"- Reviewed {total_rows} low-SOH or floor-risk rows with `actual_units_sold >= {int(MATERIAL_ACTUAL_UNITS)}` and no clear visible review state.",
        f"- This slice represents {share_text} of the remaining cleanup issue set.",
        f"- Explicit legacy issue-alias rows inside this governed slice: {explicit_issue_alias_rows}.",
        f"- Gross profit represented by this slice: ${gross_profit_total:.2f}.",
        f"- Capital left represented by this slice: ${capital_left_total:.2f}.",
        f"- Source certification: {manifest.get('source_certification_status', 'UNKNOWN')}.",
        f"- Actual outcome source: {manifest.get('actual_review_csv_path_used', '')}.",
        "",
        "## 3. Classification split",
        f"- TRUE_LOW_SOH_MISSED_DEMAND: {count('TRUE_LOW_SOH_MISSED_DEMAND')}",
        f"- ONLINE_FLOOR_PROTECTION_REVIEW: {count('ONLINE_FLOOR_PROTECTION_REVIEW')}",
        f"- FORECAST_UNDERCALIBRATION_LOW_SOH: {count('FORECAST_UNDERCALIBRATION_LOW_SOH')}",
        f"- LOW_SOH_BUT_COVERED_BY_ON_ORDER: {count('LOW_SOH_BUT_COVERED_BY_ON_ORDER')}",
        f"- NO_CHANGE_CAPITAL_PROTECTED: {count('NO_CHANGE_CAPITAL_PROTECTED')}",
        f"- DATA_OR_LABEL_CONFLICT: {count('DATA_OR_LABEL_CONFLICT')}",
        "",
        "## 4. Department concentration",
        top_departments_text,
        "",
        "## 5. Recommendation",
        " ".join(recommendation_lines),
        "",
        "## 6. Decision guardrail",
        "This evidence supports review-only surfacing and calibration follow-up, not auto-ordering, not a Stage 12 change, and not a relaxation of the low-SOH demand guardrail.",
    ]
    return "\n".join(memo_lines).strip() + "\n"


def build_promotions_low_soh_material_demand_review(
    *,
    cleanup_issue_frame: pd.DataFrame,
    recalibration_rows_frame: pd.DataFrame,
    visible_report_frame: pd.DataFrame,
    audit_report_frame: pd.DataFrame,
    review_summary_frame: pd.DataFrame,
    cleanup_summary_frame: pd.DataFrame,
    manifest: dict[str, object] | None = None,
) -> PromotionsLowSohMaterialDemandReviewResult:
    rows_frame = _build_rows_frame(
        cleanup_issue_frame=cleanup_issue_frame,
        recalibration_rows_frame=recalibration_rows_frame,
        visible_report_frame=visible_report_frame,
        audit_report_frame=audit_report_frame,
    )
    summary_frame = _build_summary_frame(
        rows_frame,
        cleanup_summary_frame=cleanup_summary_frame,
    )
    by_department_frame = _build_by_department_frame(rows_frame)
    action_recommendations_frame = _build_action_recommendations_frame(
        rows_frame,
        by_department_frame=by_department_frame,
    )
    memo_markdown = _build_memo(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_department_frame=by_department_frame,
        cleanup_summary_frame=cleanup_summary_frame,
        manifest=manifest,
    )
    del review_summary_frame
    return PromotionsLowSohMaterialDemandReviewResult(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_department_frame=by_department_frame,
        action_recommendations_frame=action_recommendations_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_low_soh_material_demand_review(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsLowSohMaterialDemandReviewArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsLowSohMaterialDemandReviewError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    visible_path = _resolve_manifest_path(manifest.get("allocation_report_csv_path", ""), review_artifact_path)
    audit_path = _resolve_manifest_path(manifest.get("audit_only_report_csv_path", ""), review_artifact_path)
    if not visible_path.exists():
        raise PromotionsLowSohMaterialDemandReviewError(
            f"Visible report from manifest does not exist: {visible_path}"
        )
    if not audit_path.exists():
        raise PromotionsLowSohMaterialDemandReviewError(
            f"Audit report from manifest does not exist: {audit_path}"
        )

    cleanup_issue_frame = _read_csv(review_artifact_path / "model_vs_actual_report_cleanup_issues.csv")
    cleanup_summary_frame = _read_csv(review_artifact_path / "report_contract_cleanup_summary.csv")
    review_summary_frame = _read_csv(review_artifact_path / "model_vs_actual_summary.csv")
    recalibration_rows_frame = _read_csv(review_artifact_path / "action_layer_recalibration_rows.csv")
    visible_report_frame = _read_csv(visible_path)
    audit_report_frame = _read_csv(audit_path)

    result = build_promotions_low_soh_material_demand_review(
        cleanup_issue_frame=cleanup_issue_frame,
        recalibration_rows_frame=recalibration_rows_frame,
        visible_report_frame=visible_report_frame,
        audit_report_frame=audit_report_frame,
        review_summary_frame=review_summary_frame,
        cleanup_summary_frame=cleanup_summary_frame,
        manifest=manifest,
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "low_soh_material_demand_rows.csv"
    summary_csv_path = destination_root / "low_soh_material_demand_summary.csv"
    by_department_csv_path = destination_root / "low_soh_material_demand_by_department.csv"
    action_recommendations_csv_path = (
        destination_root / "low_soh_material_demand_action_recommendations.csv"
    )
    memo_md_path = destination_root / "low_soh_material_demand_memo.md"

    result.rows_frame.to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    add_provenance_columns(result.by_department_frame.copy(), manifest).to_csv(
        by_department_csv_path,
        index=False,
    )
    add_provenance_columns(result.action_recommendations_frame.copy(), manifest).to_csv(
        action_recommendations_csv_path,
        index=False,
    )
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsLowSohMaterialDemandReviewArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        action_recommendations_csv_path=str(action_recommendations_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the governed low-SOH or floor-risk material-demand diagnostics pass."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_low_soh_material_demand_review(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("low_soh_material_demand_rows", artifacts.rows_csv_path)
    print("low_soh_material_demand_summary", artifacts.summary_csv_path)
    print("low_soh_material_demand_by_department", artifacts.by_department_csv_path)
    print("low_soh_material_demand_action_recommendations", artifacts.action_recommendations_csv_path)
    print("low_soh_material_demand_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())