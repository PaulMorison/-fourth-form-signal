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


OUTPUT_FOLDER_NAME = "no_prior_demand_manual_inspection"
TARGET_OVERLAY_CATEGORY = "NO_PRIOR_DEMAND_SURPRISE_REVIEW"

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    "review_overlay_packet/operator_review_memo/operator_review_priority_list.csv",
)

MANUAL_CAUSE_LABEL_VALUES: tuple[str, ...] = (
    "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
    "STORE_SPECIFIC_DEMAND_NOT_CAPTURED",
    "ONLINE_OR_AVAILABILITY_EFFECT",
    "PRICE_OR_PROMO_MECHANIC_EFFECT",
    "BASKET_OR_MISSION_EFFECT",
    "DATA_GAP_OR_LABEL_ERROR",
    "RANDOM_ONE_OFF_DEMAND",
    "UNKNOWN_REQUIRES_REVIEW",
)

MANUAL_NEXT_ACTION_VALUES: tuple[str, ...] = (
    "ADD_TO_REVIEW_RULE_CANDIDATES",
    "KEEP_SHADOW_ONLY",
    "INSPECT_DATA_QUALITY",
    "NO_CHANGE",
    "ESCALATE_FOR_OPERATOR_REVIEW",
)

ROWS_OUTPUT_COLUMNS: tuple[str, ...] = (
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

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)


class PromotionsNoPriorDemandManualInspectionError(RuntimeError):
    """Raised when the manual-inspection worksheet cannot be built safely."""


@dataclass(frozen=True)
class PromotionsNoPriorDemandManualInspectionResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsNoPriorDemandManualInspectionArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    memo_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsNoPriorDemandManualInspectionError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsNoPriorDemandManualInspectionError(
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
        raise PromotionsNoPriorDemandManualInspectionError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsNoPriorDemandManualInspectionError(
            f"{frame_name} is missing required columns: {missing}"
        )


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


def _build_rows_frame(priority_list_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        priority_list_frame,
        (
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
        ),
        frame_name="operator_review_priority_list_frame",
    )
    filtered = priority_list_frame.loc[
        priority_list_frame["overlay_category"].astype(str).eq(TARGET_OVERLAY_CATEGORY)
    ].copy()
    if filtered.empty:
        raise PromotionsNoPriorDemandManualInspectionError(
            "No NO_PRIOR_DEMAND_SURPRISE_REVIEW rows were found in operator_review_priority_list.csv."
        )

    if not filtered["review_priority_rank"].astype(int).eq(1).all():
        raise PromotionsNoPriorDemandManualInspectionError(
            "The no-prior-demand inspection slice must remain the highest-priority review set."
        )

    if int(pd.to_numeric(filtered["production_order_change_flag"], errors="coerce").fillna(0).sum()) != 0:
        raise PromotionsNoPriorDemandManualInspectionError(
            "Manual inspection input attempted to carry production order changes."
        )
    if int(pd.to_numeric(filtered["stage_12_change_flag"], errors="coerce").fillna(0).sum()) != 0:
        raise PromotionsNoPriorDemandManualInspectionError(
            "Manual inspection input attempted to carry Stage 12 changes."
        )

    filtered["actual_gross_profit_sort"] = pd.to_numeric(
        filtered["actual_gross_profit"], errors="coerce"
    ).fillna(0.0)
    filtered["forecast_error_sort"] = pd.to_numeric(
        filtered["forecast_error_units"], errors="coerce"
    ).fillna(0.0)
    filtered = filtered.sort_values(
        by=["review_priority_rank", "actual_gross_profit_sort", "forecast_error_sort", "sku_number"],
        ascending=[True, False, False, True],
        kind="stable",
    ).drop(columns=["overlay_category", "actual_gross_profit_sort", "forecast_error_sort"])

    filtered["manual_cause_label"] = ""
    filtered["manual_confidence_score"] = ""
    filtered["manual_notes"] = ""
    filtered["manual_next_action"] = ""
    filtered["should_add_review_rule_candidate"] = ""
    filtered["should_remain_shadow_only"] = ""
    return filtered.loc[:, ROWS_OUTPUT_COLUMNS].reset_index(drop=True)


def _build_summary_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    total_rows = len(rows_frame.index)
    total_gross_profit = float(pd.to_numeric(rows_frame["actual_gross_profit"], errors="coerce").fillna(0.0).sum())
    total_capital_left = float(
        pd.to_numeric(rows_frame["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0).sum()
    )
    department_totals = (
        rows_frame.groupby("department", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            actual_gross_profit_total=("actual_gross_profit", lambda series: float(pd.to_numeric(series, errors="coerce").fillna(0.0).sum())),
        )
        .reset_index()
        .sort_values(
            by=["row_count", "actual_gross_profit_total", "department"],
            ascending=[False, False, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    rows = [
        _summary_row(
            "MANUAL_INSPECTION",
            "ROWS_PREPARED",
            total_rows,
            "rows",
            _format_int(total_rows),
            "No-prior-demand surprise rows prepared for operator manual classification.",
        ),
        _summary_row(
            "MANUAL_INSPECTION",
            "TOTAL_GROSS_PROFIT_REPRESENTED",
            round(total_gross_profit, 2),
            "dollars",
            _format_money(total_gross_profit),
            "Gross profit represented by the manual-inspection worksheet.",
        ),
        _summary_row(
            "MANUAL_INSPECTION",
            "TOTAL_CAPITAL_LEFT_REPRESENTED",
            round(total_capital_left, 2),
            "dollars",
            _format_money(total_capital_left),
            "Capital left represented by the manual-inspection worksheet.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            0,
            "rows",
            "0",
            "This worksheet does not change production ordering.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            0,
            "rows",
            "0",
            "This worksheet does not change Stage 12.",
        ),
    ]
    for rank, row in enumerate(department_totals.head(3).itertuples(index=False), start=1):
        rows.append(
            _summary_row(
                "TOP_DEPARTMENT",
                f"RANK_{rank}",
                int(row.row_count),
                "rows",
                f"{row.department} ({_format_int(row.row_count)})",
                f"Gross profit represented: {_format_money(float(row.actual_gross_profit_total))}.",
            )
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(rows_frame: pd.DataFrame) -> str:
    total_rows = len(rows_frame.index)
    total_gross_profit = float(pd.to_numeric(rows_frame["actual_gross_profit"], errors="coerce").fillna(0.0).sum())
    total_capital_left = float(
        pd.to_numeric(rows_frame["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0).sum()
    )
    department_totals = (
        rows_frame.groupby("department", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            actual_gross_profit_total=("actual_gross_profit", lambda series: float(pd.to_numeric(series, errors="coerce").fillna(0.0).sum())),
        )
        .reset_index()
        .sort_values(
            by=["row_count", "actual_gross_profit_total", "department"],
            ascending=[False, False, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    top_departments = ", ".join(
        f"{row.department} ({_format_int(row.row_count)})"
        for row in department_totals.head(3).itertuples(index=False)
    )
    first_skus = _sample_skus(rows_frame["sku_number"])

    lines = [
        "# No Prior Demand Manual Inspection",
        "",
        "This is not an order file. It is a manual-inspection worksheet for the no-prior-demand surprise rows only.",
        "",
        f"Production order changes = 0.",
        f"Stage 12 changes = 0.",
        "",
        (
            f"The goal is to learn why prior promo evidence failed on these {_format_int(total_rows)} rows, not to auto-buy and not to change the demand proxy."
        ),
        (
            f"These rows represent {_format_money(total_gross_profit)} gross profit and {_format_money(total_capital_left)} capital left."
        ),
        f"Top departments in this worksheet: {top_departments}.",
        f"Start with these SKUs: {first_skus}.",
        "",
        "How to use the manual columns:",
        f"- `manual_cause_label` should use one of: {', '.join(MANUAL_CAUSE_LABEL_VALUES)}.",
        f"- `manual_next_action` should use one of: {', '.join(MANUAL_NEXT_ACTION_VALUES)}.",
        "- Leave the worksheet review-only; do not convert any row into an ordering change from this file.",
        "",
        (
            f"Recommendation: review these {_format_int(total_rows)} rows before making any model or action-layer change, then use the manual labels to decide whether any issue belongs in review-rule candidates, shadow-only follow-up, or data-quality inspection."
        ),
    ]
    return "\n".join(lines) + "\n"


def build_promotions_no_prior_demand_manual_inspection(
    *,
    operator_review_priority_list_frame: pd.DataFrame,
) -> PromotionsNoPriorDemandManualInspectionResult:
    rows_frame = _build_rows_frame(operator_review_priority_list_frame)
    summary_frame = _build_summary_frame(rows_frame)
    memo_markdown = _build_memo(rows_frame)
    return PromotionsNoPriorDemandManualInspectionResult(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_no_prior_demand_manual_inspection(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsNoPriorDemandManualInspectionArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsNoPriorDemandManualInspectionError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    priority_list_path = (
        review_artifact_path
        / "review_overlay_packet"
        / "operator_review_memo"
        / "operator_review_priority_list.csv"
    )
    result = build_promotions_no_prior_demand_manual_inspection(
        operator_review_priority_list_frame=_read_csv(priority_list_path),
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else review_artifact_path
        / "review_overlay_packet"
        / "operator_review_memo"
        / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "no_prior_demand_manual_inspection_rows.csv"
    summary_csv_path = destination_root / "no_prior_demand_manual_inspection_summary.csv"
    memo_md_path = destination_root / "no_prior_demand_manual_inspection_memo.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsNoPriorDemandManualInspectionArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed manual-inspection worksheet for no-prior-demand surprise rows."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_no_prior_demand_manual_inspection(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("no_prior_demand_manual_inspection_rows", artifacts.rows_csv_path)
    print("no_prior_demand_manual_inspection_summary", artifacts.summary_csv_path)
    print("no_prior_demand_manual_inspection_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())