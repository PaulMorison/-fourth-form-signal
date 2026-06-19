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
    LOW_SELL_THROUGH_THRESHOLD,
    MATERIAL_ACTUAL_UNITS,
    MATERIAL_CAPITAL_LEFT,
    MATERIAL_UNIT_DELTA,
    STRONG_SELL_THROUGH_THRESHOLD,
)


TARGET_ISSUE_TYPE = "CAPITAL_DRAG_HIGH_BUT_STRONG_SELL_THROUGH"
OUTPUT_FOLDER_NAME = "capital_drag_strong_sellthrough_review"
OVERRIDE_VALIDATION_FOLDER_NAME = "override_validation"
LOW_RESIDUAL_CAPITAL_LEFT = 3.0
OVERRIDE_VISIBLE_RISK_FLAG = "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW"
OVERRIDE_VISIBLE_REASON_SHORT = (
    "Strong sell-through with low residual capital. Review capital-drag headline; do not auto-buy."
)

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
    "actual_units_sold",
    "store_adjusted_qty",
    "actual_sell_through_vs_store_adjusted",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "expected_promo_demand",
    "forecast_error_units",
    "recommended_order_units",
    "final_store_order_units",
    "capital_drag_label",
    "availability_risk_label",
    "demand_evidence_label",
    "diagnostic_classification",
    "proposed_next_action",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "summary_kind",
    "label_name",
    "row_count",
    "actual_units_total",
    "store_adjusted_qty_total",
    "actual_gross_profit_total",
    "capital_left_total",
    "average_sell_through",
    "average_forecast_error_units",
    "share_of_remaining_cleanup_issues",
    "sample_skus",
)

BY_DEPARTMENT_COLUMNS: tuple[str, ...] = (
    "department",
    "row_count",
    "actual_units_total",
    "store_adjusted_qty_total",
    "actual_gross_profit_total",
    "capital_left_total",
    "average_sell_through",
    "average_forecast_error_units",
    "true_capital_drag_rows",
    "strong_converter_wrong_risk_headline_rows",
    "review_not_auto_buy_rows",
    "data_or_label_conflict_rows",
    "keep_guardrail_active_rows",
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

OVERRIDE_VALIDATION_ROWS_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "operator_decision",
    "original_operator_action",
    "operator_action",
    "original_order_units",
    "order_units",
    "original_reason_short",
    "reason_short",
    "original_risk_flag",
    "risk_flag",
    "original_review_flag",
    "review_flag",
    "override_candidate_flag",
    "override_applied_flag",
    "visible_override_state",
    "actual_units_sold",
    "store_adjusted_qty",
    "actual_sell_through_vs_store_adjusted",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "expected_promo_demand",
    "forecast_error_units",
    "recommended_order_units",
    "final_store_order_units",
    "capital_drag_label",
    "availability_risk_label",
    "demand_evidence_label",
    "diagnostic_classification",
    "proposed_next_action",
    "production_order_changed_flag",
)

OVERRIDE_VALIDATION_SUMMARY_COLUMNS: tuple[str, ...] = (
    "summary_kind",
    "label_name",
    "row_count",
    "override_candidate_rows",
    "rows_updated_to_strong_conversion_capital_drag_review",
    "actual_gross_profit_total",
    "capital_left_total",
    "production_order_change_count",
    "stage12_change_count",
    "remaining_true_capital_drag_rows",
    "sample_skus",
)

CLASSIFICATION_PRIORITY: dict[str, int] = {
    "TRUE_CAPITAL_DRAG": 1,
    "KEEP_GUARDRAIL_ACTIVE": 2,
    "REVIEW_NOT_AUTO_BUY": 3,
    "STRONG_CONVERTER_WRONG_RISK_HEADLINE": 4,
    "DATA_OR_LABEL_CONFLICT": 5,
}

ACTION_PRIORITY: dict[str, int] = {
    "KEEP_CAPITAL_GUARDRAIL": 1,
    "ADD_CAPITAL_DRAG_OVERRIDE_REVIEW_FLAG": 2,
    "CHANGE_VISIBLE_RISK_TO_STRONG_CONVERSION_REVIEW": 3,
    "INSPECT_DEPARTMENT_PATTERN": 4,
    "NO_CHANGE": 5,
}


class PromotionsCapitalDragStrongSellthroughReviewError(RuntimeError):
    """Raised when the capital-drag strong-sell-through review cannot run safely."""


@dataclass(frozen=True)
class PromotionsCapitalDragStrongSellthroughReviewResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    action_recommendations_frame: pd.DataFrame
    memo_markdown: str
    override_validation_rows_frame: pd.DataFrame
    override_validation_summary_frame: pd.DataFrame
    override_validation_memo_markdown: str


@dataclass(frozen=True)
class PromotionsCapitalDragStrongSellthroughReviewArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    by_department_csv_path: str
    action_recommendations_csv_path: str
    memo_md_path: str
    override_validation_rows_csv_path: str
    override_validation_summary_csv_path: str
    override_validation_memo_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsCapitalDragStrongSellthroughReviewError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsCapitalDragStrongSellthroughReviewError(
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
        raise PromotionsCapitalDragStrongSellthroughReviewError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsCapitalDragStrongSellthroughReviewError(
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
        raise PromotionsCapitalDragStrongSellthroughReviewError(
            f"{frame_name} has blank sku_number values after normalization (rows={blank_count})"
        )
    duplicate_mask = subset["_sku_key"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicate_values = subset.loc[duplicate_mask, "_sku_key"].head(10).tolist()
        sample = ", ".join(duplicate_values)
        raise PromotionsCapitalDragStrongSellthroughReviewError(
            f"{frame_name} has duplicate sku_number values after normalization: {sample}"
        )
    return subset.drop(columns=["sku_number"])


def _sample_skus(values: pd.Series, *, limit: int = 5) -> str:
    unique_values = []
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


def _classify_row(row: pd.Series) -> str:
    sell_through = float(row["actual_sell_through_vs_store_adjusted"])
    actual_gross_profit = float(row["actual_gross_profit"])
    capital_left = float(row["capital_left_in_unsold_store_allocation"])
    actual_units = float(row["actual_units_sold"])
    forecast_error = float(row["forecast_error_units"])
    operator_decision_token = _normalize_token(row["operator_decision"])
    risk_flag_token = _normalize_token(row["risk_flag"])
    capital_drag_label_token = _normalize_token(row["capital_drag_label"])

    if capital_left >= MATERIAL_CAPITAL_LEFT and sell_through < LOW_SELL_THROUGH_THRESHOLD:
        return "TRUE_CAPITAL_DRAG"
    if capital_left >= MATERIAL_CAPITAL_LEFT and sell_through >= STRONG_SELL_THROUGH_THRESHOLD:
        return "KEEP_GUARDRAIL_ACTIVE"
    if capital_drag_label_token != "capital_drag_high":
        return "DATA_OR_LABEL_CONFLICT"
    if operator_decision_token != "reduce_holding":
        return "DATA_OR_LABEL_CONFLICT"
    if risk_flag_token != "capital_drag_high":
        return "DATA_OR_LABEL_CONFLICT"
    if sell_through < STRONG_SELL_THROUGH_THRESHOLD or actual_gross_profit <= 0.0:
        return "DATA_OR_LABEL_CONFLICT"
    if forecast_error >= MATERIAL_UNIT_DELTA or actual_units >= MATERIAL_ACTUAL_UNITS:
        return "REVIEW_NOT_AUTO_BUY"
    return "STRONG_CONVERTER_WRONG_RISK_HEADLINE"


def _proposed_next_action(classification: str) -> str:
    if classification in {"TRUE_CAPITAL_DRAG", "KEEP_GUARDRAIL_ACTIVE"}:
        return "KEEP_CAPITAL_GUARDRAIL"
    if classification == "STRONG_CONVERTER_WRONG_RISK_HEADLINE":
        return "CHANGE_VISIBLE_RISK_TO_STRONG_CONVERSION_REVIEW"
    if classification == "REVIEW_NOT_AUTO_BUY":
        return "ADD_CAPITAL_DRAG_OVERRIDE_REVIEW_FLAG"
    return "NO_CHANGE"


def _has_capital_drag_signal(row: pd.Series) -> bool:
    risk_flag_token = _normalize_token(row["risk_flag"])
    capital_drag_label_token = _normalize_token(row["capital_drag_label"])
    return "capital_drag" in risk_flag_token or "capital_drag" in capital_drag_label_token


def _is_override_candidate(row: pd.Series) -> bool:
    if str(row.get("diagnostic_classification", "")) not in {
        "REVIEW_NOT_AUTO_BUY",
        "STRONG_CONVERTER_WRONG_RISK_HEADLINE",
    }:
        return False
    if not _has_capital_drag_signal(row):
        return False
    if float(row["actual_sell_through_vs_store_adjusted"]) < STRONG_SELL_THROUGH_THRESHOLD:
        return False
    capital_left = float(row["capital_left_in_unsold_store_allocation"])
    actual_units = float(row["actual_units_sold"])
    return capital_left <= LOW_RESIDUAL_CAPITAL_LEFT or actual_units >= MATERIAL_ACTUAL_UNITS


def _build_override_validation_rows_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=OVERRIDE_VALIDATION_ROWS_COLUMNS)

    rows = rows_frame.copy()
    rows["original_operator_action"] = rows["operator_action"].astype(str)
    rows["original_order_units"] = pd.to_numeric(rows["order_units"], errors="coerce").fillna(0.0)
    rows["original_reason_short"] = rows["reason_short"].astype(str)
    rows["original_risk_flag"] = rows["risk_flag"].astype(str)
    rows["original_review_flag"] = pd.to_numeric(rows["review_flag"], errors="coerce").fillna(0.0).round(0).astype(int)
    rows["override_candidate_flag"] = rows.apply(_is_override_candidate, axis=1).astype(int)
    rows["override_applied_flag"] = rows["override_candidate_flag"].astype(int)
    rows["visible_override_state"] = rows["override_candidate_flag"].map(
        {1: OVERRIDE_VISIBLE_RISK_FLAG, 0: ""}
    )

    override_mask = rows["override_candidate_flag"].eq(1)
    rows.loc[override_mask, "operator_action"] = "REVIEW"
    rows.loc[override_mask, "review_flag"] = 1
    rows.loc[override_mask, "risk_flag"] = OVERRIDE_VISIBLE_RISK_FLAG
    rows.loc[override_mask, "reason_short"] = OVERRIDE_VISIBLE_REASON_SHORT
    rows["review_flag"] = pd.to_numeric(rows["review_flag"], errors="coerce").fillna(0.0).round(0).astype(int)
    rows["production_order_changed_flag"] = rows["order_units"].ne(rows["original_order_units"]).astype(int)

    rows = rows.sort_values(
        by=["override_applied_flag", "actual_gross_profit", "sku_number"],
        ascending=[False, False, True],
        kind="stable",
    )
    return rows.loc[:, OVERRIDE_VALIDATION_ROWS_COLUMNS].reset_index(drop=True)


def _build_override_validation_summary_frame(
    override_validation_rows_frame: pd.DataFrame,
    *,
    cleanup_summary_frame: pd.DataFrame,
) -> pd.DataFrame:
    remaining_true_capital_drag_rows = int(
        override_validation_rows_frame["diagnostic_classification"].eq("TRUE_CAPITAL_DRAG").sum()
    ) if not override_validation_rows_frame.empty else 0

    def summarize(label_name: str, frame: pd.DataFrame, *, summary_kind: str) -> dict[str, object]:
        row_count = int(len(frame.index))
        return {
            "summary_kind": summary_kind,
            "label_name": label_name,
            "row_count": row_count,
            "override_candidate_rows": int(frame["override_candidate_flag"].sum()) if row_count else 0,
            "rows_updated_to_strong_conversion_capital_drag_review": int(frame["override_applied_flag"].sum()) if row_count else 0,
            "actual_gross_profit_total": round(float(frame["actual_gross_profit"].sum()), 2) if row_count else 0.0,
            "capital_left_total": round(float(frame["capital_left_in_unsold_store_allocation"].sum()), 2) if row_count else 0.0,
            "production_order_change_count": int(frame["production_order_changed_flag"].sum()) if row_count else 0,
            "stage12_change_count": 0,
            "remaining_true_capital_drag_rows": remaining_true_capital_drag_rows,
            "sample_skus": _sample_skus(frame["sku_number"]) if row_count else "",
        }

    if override_validation_rows_frame.empty:
        return pd.DataFrame(
            [summarize("ALL_ROWS", override_validation_rows_frame, summary_kind="TOTAL")],
            columns=OVERRIDE_VALIDATION_SUMMARY_COLUMNS,
        )

    summary_rows = [
        summarize("ALL_ROWS", override_validation_rows_frame, summary_kind="TOTAL"),
        summarize(
            "OVERRIDE_CANDIDATE",
            override_validation_rows_frame.loc[
                override_validation_rows_frame["override_candidate_flag"].eq(1)
            ],
            summary_kind="OVERRIDE",
        ),
        summarize(
            "NON_CANDIDATE",
            override_validation_rows_frame.loc[
                override_validation_rows_frame["override_candidate_flag"].ne(1)
            ],
            summary_kind="OVERRIDE",
        ),
    ]
    for classification, group in override_validation_rows_frame.groupby(
        "diagnostic_classification",
        sort=False,
        dropna=False,
    ):
        summary_rows.append(
            summarize(str(classification), group, summary_kind="CLASSIFICATION")
        )
    summary_frame = pd.DataFrame(summary_rows, columns=OVERRIDE_VALIDATION_SUMMARY_COLUMNS)
    del cleanup_summary_frame
    return summary_frame.sort_values(
        by=["summary_kind", "row_count", "label_name"],
        ascending=[True, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_override_validation_memo(
    *,
    override_validation_rows_frame: pd.DataFrame,
    override_validation_summary_frame: pd.DataFrame,
    manifest: dict[str, object] | None,
) -> str:
    del override_validation_summary_frame
    manifest = manifest or {}
    total_rows = int(len(override_validation_rows_frame.index))
    override_candidate_rows = int(
        override_validation_rows_frame["override_candidate_flag"].sum()
    ) if total_rows else 0
    updated_rows = int(
        override_validation_rows_frame["override_applied_flag"].sum()
    ) if total_rows else 0
    production_order_change_count = int(
        override_validation_rows_frame["production_order_changed_flag"].sum()
    ) if total_rows else 0
    remaining_true_capital_drag_rows = int(
        override_validation_rows_frame["diagnostic_classification"].eq("TRUE_CAPITAL_DRAG").sum()
    ) if total_rows else 0
    gross_profit_total = round(float(override_validation_rows_frame["actual_gross_profit"].sum()), 2) if total_rows else 0.0
    capital_left_total = round(float(override_validation_rows_frame["capital_left_in_unsold_store_allocation"].sum()), 2) if total_rows else 0.0

    memo_lines = [
        "# Capital-Drag Override Validation",
        "",
        "## 1. Purpose",
        "This validation applies visible/reporting review logic only. It does not change production policy, normal Stage 11 generation, or Stage 12 publishing.",
        "",
        "## 2. Override rule",
        f"A row is an override candidate only when capital-drag evidence is present, actual sell-through is at least {STRONG_SELL_THROUGH_THRESHOLD:.2f}, and either `capital_left_in_unsold_store_allocation <= {LOW_RESIDUAL_CAPITAL_LEFT:.1f}` or `actual_units_sold >= {int(MATERIAL_ACTUAL_UNITS)}`.",
        "When that rule is satisfied, the derived visible state is `STRONG_CONVERSION_CAPITAL_DRAG_REVIEW` with `operator_action=REVIEW`, `review_flag=1`, unchanged `order_units`, and the governed review-only wording.",
        "",
        "## 3. Validation outcome",
        f"- Override candidate rows: {override_candidate_rows}",
        f"- Rows updated to `STRONG_CONVERSION_CAPITAL_DRAG_REVIEW`: {updated_rows}",
        f"- Production order changes: {production_order_change_count}",
        "- Stage 12 changes: 0",
        f"- Remaining true capital drag rows in this slice: {remaining_true_capital_drag_rows}",
        f"- Gross profit represented by validated rows: ${gross_profit_total:.2f}",
        f"- Capital left represented by validated rows: ${capital_left_total:.2f}",
        "",
        "## 4. Governance guardrails",
        "- The capital-drag guardrail remains active.",
        "- No auto-ordering is promoted.",
        "- No demand proxy is relaxed.",
        "- Normal Stage 11 generation still does not require actual outcome data.",
        "- This override is only materialized when actual outcome evidence is already available inside the diagnostics runtime.",
        "",
        "## 5. Recommendation",
        "Adopt `STRONG_CONVERSION_CAPITAL_DRAG_REVIEW` as a visible/reporting override candidate state in diagnostics and future review tooling, while keeping the underlying capital-drag production guardrail and Stage 12 flow unchanged.",
        "",
        "## 6. Source certification",
        f"- Source certification: {manifest.get('source_certification_status', 'UNKNOWN')}",
        f"- Actual outcome source: {manifest.get('actual_review_csv_path_used', '')}",
    ]
    return "\n".join(memo_lines).strip() + "\n"


def _build_rows_frame(
    *,
    cleanup_issue_frame: pd.DataFrame,
    recalibration_rows_frame: pd.DataFrame,
    visible_report_frame: pd.DataFrame,
    audit_report_frame: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(
        cleanup_issue_frame,
        ("sku_number", "issue_type"),
        frame_name="cleanup_issue_frame",
    )

    issue_rows = cleanup_issue_frame.loc[
        cleanup_issue_frame["issue_type"].astype(str).eq(TARGET_ISSUE_TYPE),
        ["sku_number", "issue_type"],
    ].copy()
    if issue_rows.empty:
        return pd.DataFrame(columns=ROWS_OUTPUT_COLUMNS)

    issue_rows["sku_number"] = _normalize_identifier(issue_rows["sku_number"])
    if issue_rows["sku_number"].duplicated(keep=False).any():
        duplicate_values = issue_rows.loc[
            issue_rows["sku_number"].duplicated(keep=False), "sku_number"
        ].head(10).tolist()
        sample = ", ".join(duplicate_values)
        raise PromotionsCapitalDragStrongSellthroughReviewError(
            "cleanup_issue_frame has duplicate target issue rows for sku_number values: " + sample
        )
    issue_rows["_sku_key"] = issue_rows["sku_number"]

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
        ),
    )
    audit_rows = _prepare_join_frame(
        audit_report_frame,
        frame_name="audit_report_frame",
        columns=(
            "sku_number",
            "recommended_order_units",
            "final_store_order_units",
            "capital_drag_label",
            "availability_risk_label",
            "demand_evidence_label",
        ),
    )

    rows = issue_rows.loc[:, ["sku_number", "_sku_key"]].merge(
        visible_rows,
        on="_sku_key",
        how="left",
        validate="one_to_one",
    )
    rows = rows.merge(
        audit_rows,
        on="_sku_key",
        how="left",
        validate="one_to_one",
    )
    rows = rows.merge(
        recalibration_rows,
        on="_sku_key",
        how="left",
        validate="one_to_one",
    )

    required_join_columns = (
        "sku_description",
        "department",
        "operator_decision",
        "operator_action",
        "order_units",
        "reason_short",
        "risk_flag",
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
        "capital_drag_label",
        "availability_risk_label",
        "demand_evidence_label",
    )
    missing_mask = rows.loc[:, required_join_columns].isna().any(axis=1)
    if missing_mask.any():
        missing_skus = rows.loc[missing_mask, "sku_number"].astype(str).head(10).tolist()
        sample = ", ".join(missing_skus)
        raise PromotionsCapitalDragStrongSellthroughReviewError(
            "capital-drag review inputs are missing joined row context for sku_number values: " + sample
        )

    text_columns = (
        "sku_number",
        "sku_description",
        "department",
        "operator_decision",
        "operator_action",
        "reason_short",
        "risk_flag",
        "capital_drag_label",
        "availability_risk_label",
        "demand_evidence_label",
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
    )
    for column_name in numeric_columns:
        rows[column_name] = pd.to_numeric(rows[column_name], errors="coerce").fillna(0.0)

    rows = rows.rename(
        columns={
            "store_adjusted_units": "store_adjusted_qty",
            "estimated_actual_gross_profit": "actual_gross_profit",
            "capital_left_unsold": "capital_left_in_unsold_store_allocation",
            "forecast_abs_error_units": "forecast_error_units",
        }
    )
    rows["review_flag"] = rows["review_flag"].round(0).astype(int)
    rows["diagnostic_classification"] = rows.apply(_classify_row, axis=1)
    rows["proposed_next_action"] = rows["diagnostic_classification"].map(_proposed_next_action)

    rows["_classification_priority"] = rows["diagnostic_classification"].map(CLASSIFICATION_PRIORITY).fillna(99)
    rows = rows.sort_values(
        by=[
            "_classification_priority",
            "capital_left_in_unsold_store_allocation",
            "actual_gross_profit",
            "sku_number",
        ],
        ascending=[True, False, False, True],
        kind="stable",
    ).drop(columns=["_classification_priority", "_sku_key"])
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
            "store_adjusted_qty_total": round(float(frame["store_adjusted_qty"].sum()), 2) if row_count else 0.0,
            "actual_gross_profit_total": round(float(frame["actual_gross_profit"].sum()), 2) if row_count else 0.0,
            "capital_left_total": round(float(frame["capital_left_in_unsold_store_allocation"].sum()), 2) if row_count else 0.0,
            "average_sell_through": round(float(frame["actual_sell_through_vs_store_adjusted"].mean()), 4) if row_count else 0.0,
            "average_forecast_error_units": round(float(frame["forecast_error_units"].mean()), 4) if row_count else 0.0,
            "share_of_remaining_cleanup_issues": round(float(share), 6),
            "sample_skus": _sample_skus(frame["sku_number"]) if row_count else "",
        }

    if rows_frame.empty:
        return pd.DataFrame([summarize("ALL_ROWS", rows_frame, summary_kind="TOTAL")], columns=SUMMARY_COLUMNS)

    summary_rows = [summarize("ALL_ROWS", rows_frame, summary_kind="TOTAL")]
    for classification, group in rows_frame.groupby("diagnostic_classification", sort=False, dropna=False):
        summary_rows.append(
            summarize(str(classification), group, summary_kind="CLASSIFICATION")
        )
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
                "store_adjusted_qty_total": round(float(group["store_adjusted_qty"].sum()), 2),
                "actual_gross_profit_total": round(float(group["actual_gross_profit"].sum()), 2),
                "capital_left_total": round(float(group["capital_left_in_unsold_store_allocation"].sum()), 2),
                "average_sell_through": round(float(group["actual_sell_through_vs_store_adjusted"].mean()), 4),
                "average_forecast_error_units": round(float(group["forecast_error_units"].mean()), 4),
                "true_capital_drag_rows": int(group["diagnostic_classification"].eq("TRUE_CAPITAL_DRAG").sum()),
                "strong_converter_wrong_risk_headline_rows": int(
                    group["diagnostic_classification"].eq("STRONG_CONVERTER_WRONG_RISK_HEADLINE").sum()
                ),
                "review_not_auto_buy_rows": int(group["diagnostic_classification"].eq("REVIEW_NOT_AUTO_BUY").sum()),
                "data_or_label_conflict_rows": int(group["diagnostic_classification"].eq("DATA_OR_LABEL_CONFLICT").sum()),
                "keep_guardrail_active_rows": int(group["diagnostic_classification"].eq("KEEP_GUARDRAIL_ACTIVE").sum()),
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
    if action_name == "KEEP_CAPITAL_GUARDRAIL":
        return "Keep the capital-drag guardrail in place because the row still ties up material capital or proves the protection logic was commercially sensible."
    if action_name == "CHANGE_VISIBLE_RISK_TO_STRONG_CONVERSION_REVIEW":
        return "The row converted well with acceptable residual capital, so the visible capital-drag headline is too blunt and should become a review-only strong-conversion message."
    if action_name == "ADD_CAPITAL_DRAG_OVERRIDE_REVIEW_FLAG":
        return "The row converted strongly, but the forecast miss or actual sales magnitude is material enough that the next step should be review-only, not auto-buy."
    if action_name == "INSPECT_DEPARTMENT_PATTERN":
        return "This department carries a repeated cluster of strong-conversion rows and should be inspected for consistent capital-drag headline behavior."
    return "The row needs more evidence review before any contract or policy change is recommended."


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
        department_rows = rows_frame.loc[rows_frame["department"].astype(str).eq(str(row["department"]))]
        dominant_classification = ""
        if not department_rows.empty:
            dominant_classification = str(
                department_rows["diagnostic_classification"].value_counts().idxmax()
            )
        records.append(
            {
                "recommendation_scope": "DEPARTMENT_PATTERN",
                "proposed_next_action": "INSPECT_DEPARTMENT_PATTERN",
                "diagnostic_classification": dominant_classification,
                "department": str(row["department"]),
                "row_count": int(row["row_count"]),
                "actual_gross_profit_total": round(float(row["actual_gross_profit_total"]), 2),
                "capital_left_total": round(float(row["capital_left_total"]), 2),
                "sample_skus": str(row["sample_skus"]),
                "rationale": _action_rationale("INSPECT_DEPARTMENT_PATTERN"),
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
    manifest = manifest or {}
    total_rows = int(len(rows_frame.index))
    total_cleanup_issues = _remaining_cleanup_issue_count(cleanup_summary_frame)
    gross_profit_total = round(float(rows_frame["actual_gross_profit"].sum()), 2) if total_rows else 0.0
    capital_left_total = round(float(rows_frame["capital_left_in_unsold_store_allocation"].sum()), 2) if total_rows else 0.0
    counts = rows_frame["diagnostic_classification"].value_counts().to_dict() if total_rows else {}

    def count(label_name: str) -> int:
        return int(counts.get(label_name, 0))

    top_departments_text = "None."
    if not by_department_frame.empty:
        top_departments = []
        for _, row in by_department_frame.head(3).iterrows():
            top_departments.append(
                f"{row['department']}: {int(row['row_count'])} rows, ${float(row['actual_gross_profit_total']):.2f} gross profit, ${float(row['capital_left_total']):.2f} capital left"
            )
        top_departments_text = "\n".join(f"- {entry}" for entry in top_departments)

    share_text = "0.00%"
    if total_cleanup_issues > 0:
        share_text = f"{(total_rows / float(total_cleanup_issues)) * 100.0:.2f}%"

    recommendation_lines: list[str] = []
    recommendation_lines.append(
        "Keep the capital-drag guardrail for genuine overstock rows; do not remove capital drag from the governed action layer."
    )
    if count("REVIEW_NOT_AUTO_BUY") > 0:
        recommendation_lines.append(
            "Add a review-only override state for strong converters when sell-through stays at or above "
            f"{STRONG_SELL_THROUGH_THRESHOLD:.2f}, residual capital stays below ${MATERIAL_CAPITAL_LEFT:.0f}, and either forecast error is at least {int(MATERIAL_UNIT_DELTA)} units or actual sales reach at least {int(MATERIAL_ACTUAL_UNITS)} units."
        )
    if count("STRONG_CONVERTER_WRONG_RISK_HEADLINE") > 0:
        recommendation_lines.append(
            "For lower-error strong converters with acceptable leftover, change the visible risk headline to a strong-conversion review message rather than a blunt capital-drag warning."
        )
    if count("DATA_OR_LABEL_CONFLICT") > 0:
        recommendation_lines.append(
            "Investigate any residual data or label conflicts before changing the cleaned visible contract."
        )

    memo_lines = [
        "# Capital-Drag High With Strong Sell-Through Review",
        "",
        "## 1. Governed scope",
        "- Diagnostics-only pass over the validated clean-visible model-vs-actual review outputs.",
        "- No production ordering logic was changed.",
        "- No Stage 12 logic was changed.",
        "- No cleaned visible operator-contract fields were changed in this pass.",
        "",
        "## 2. Evidence base",
        f"- Reviewed {total_rows} `{TARGET_ISSUE_TYPE}` rows out of {total_cleanup_issues} remaining cleanup issues ({share_text} of the residual cleanup set).",
        f"- Gross profit represented by this slice: ${gross_profit_total:.2f}.",
        f"- Capital left represented by this slice: ${capital_left_total:.2f}.",
        f"- Source certification: {manifest.get('source_certification_status', 'UNKNOWN')}.",
        f"- Actual outcome source: {manifest.get('actual_review_csv_path_used', '')}.",
        "",
        "## 3. Classification split",
        f"- TRUE_CAPITAL_DRAG: {count('TRUE_CAPITAL_DRAG')}",
        f"- STRONG_CONVERTER_WRONG_RISK_HEADLINE: {count('STRONG_CONVERTER_WRONG_RISK_HEADLINE')}",
        f"- REVIEW_NOT_AUTO_BUY: {count('REVIEW_NOT_AUTO_BUY')}",
        f"- DATA_OR_LABEL_CONFLICT: {count('DATA_OR_LABEL_CONFLICT')}",
        f"- KEEP_GUARDRAIL_ACTIVE: {count('KEEP_GUARDRAIL_ACTIVE')}",
        "",
        "## 4. Department concentration",
        top_departments_text,
        "",
        "## 5. Recommendation",
        " ".join(recommendation_lines),
        "",
        "## 6. Decision guardrail",
        "This evidence supports a review-only override path for strong converters, not a blanket removal of capital-drag protection and not an auto-buy promotion.",
    ]
    return "\n".join(memo_lines).strip() + "\n"


def build_promotions_capital_drag_strong_sellthrough_review(
    *,
    cleanup_issue_frame: pd.DataFrame,
    recalibration_rows_frame: pd.DataFrame,
    visible_report_frame: pd.DataFrame,
    audit_report_frame: pd.DataFrame,
    review_summary_frame: pd.DataFrame,
    cleanup_summary_frame: pd.DataFrame,
    manifest: dict[str, object] | None = None,
) -> PromotionsCapitalDragStrongSellthroughReviewResult:
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
    override_validation_rows_frame = _build_override_validation_rows_frame(rows_frame)
    override_validation_summary_frame = _build_override_validation_summary_frame(
        override_validation_rows_frame,
        cleanup_summary_frame=cleanup_summary_frame,
    )
    memo_markdown = _build_memo(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_department_frame=by_department_frame,
        cleanup_summary_frame=cleanup_summary_frame,
        manifest=manifest,
    )
    override_validation_memo_markdown = _build_override_validation_memo(
        override_validation_rows_frame=override_validation_rows_frame,
        override_validation_summary_frame=override_validation_summary_frame,
        manifest=manifest,
    )
    del review_summary_frame
    return PromotionsCapitalDragStrongSellthroughReviewResult(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_department_frame=by_department_frame,
        action_recommendations_frame=action_recommendations_frame,
        memo_markdown=memo_markdown,
        override_validation_rows_frame=override_validation_rows_frame,
        override_validation_summary_frame=override_validation_summary_frame,
        override_validation_memo_markdown=override_validation_memo_markdown,
    )


def write_promotions_capital_drag_strong_sellthrough_review(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsCapitalDragStrongSellthroughReviewArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsCapitalDragStrongSellthroughReviewError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    visible_path = _resolve_manifest_path(manifest.get("allocation_report_csv_path", ""), review_artifact_path)
    audit_path = _resolve_manifest_path(manifest.get("audit_only_report_csv_path", ""), review_artifact_path)
    if not visible_path.exists():
        raise PromotionsCapitalDragStrongSellthroughReviewError(
            f"Visible report from manifest does not exist: {visible_path}"
        )
    if not audit_path.exists():
        raise PromotionsCapitalDragStrongSellthroughReviewError(
            f"Audit report from manifest does not exist: {audit_path}"
        )

    cleanup_issue_frame = _read_csv(review_artifact_path / "model_vs_actual_report_cleanup_issues.csv")
    cleanup_summary_frame = _read_csv(review_artifact_path / "report_contract_cleanup_summary.csv")
    review_summary_frame = _read_csv(review_artifact_path / "model_vs_actual_summary.csv")
    recalibration_rows_frame = _read_csv(review_artifact_path / "action_layer_recalibration_rows.csv")
    visible_report_frame = _read_csv(visible_path)
    audit_report_frame = _read_csv(audit_path)

    result = build_promotions_capital_drag_strong_sellthrough_review(
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

    rows_csv_path = destination_root / "capital_drag_strong_sellthrough_rows.csv"
    summary_csv_path = destination_root / "capital_drag_strong_sellthrough_summary.csv"
    by_department_csv_path = destination_root / "capital_drag_strong_sellthrough_by_department.csv"
    action_recommendations_csv_path = (
        destination_root / "capital_drag_strong_sellthrough_action_recommendations.csv"
    )
    memo_md_path = destination_root / "capital_drag_strong_sellthrough_memo.md"
    override_validation_root = destination_root / OVERRIDE_VALIDATION_FOLDER_NAME
    override_validation_root.mkdir(parents=True, exist_ok=True)
    override_validation_rows_csv_path = (
        override_validation_root / "capital_drag_override_validation_rows.csv"
    )
    override_validation_summary_csv_path = (
        override_validation_root / "capital_drag_override_validation_summary.csv"
    )
    override_validation_memo_md_path = (
        override_validation_root / "capital_drag_override_validation_memo.md"
    )

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
    result.override_validation_rows_frame.to_csv(
        override_validation_rows_csv_path,
        index=False,
    )
    add_provenance_columns(result.override_validation_summary_frame.copy(), manifest).to_csv(
        override_validation_summary_csv_path,
        index=False,
    )
    override_validation_memo_md_path.write_text(
        result.override_validation_memo_markdown,
        encoding="utf-8",
    )

    return PromotionsCapitalDragStrongSellthroughReviewArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        action_recommendations_csv_path=str(action_recommendations_csv_path),
        memo_md_path=str(memo_md_path),
        override_validation_rows_csv_path=str(override_validation_rows_csv_path),
        override_validation_summary_csv_path=str(override_validation_summary_csv_path),
        override_validation_memo_md_path=str(override_validation_memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the governed capital-drag-high strong-sell-through diagnostics pass."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_capital_drag_strong_sellthrough_review(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("capital_drag_strong_sellthrough_rows", artifacts.rows_csv_path)
    print("capital_drag_strong_sellthrough_summary", artifacts.summary_csv_path)
    print("capital_drag_strong_sellthrough_memo", artifacts.memo_md_path)
    print("capital_drag_override_validation_rows", artifacts.override_validation_rows_csv_path)
    print("capital_drag_override_validation_summary", artifacts.override_validation_summary_csv_path)
    print("capital_drag_override_validation_memo", artifacts.override_validation_memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())