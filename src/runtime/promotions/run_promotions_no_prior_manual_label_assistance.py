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
)


OUTPUT_FOLDER_NAME = "manual_label_assistance_pack"
INPUT_ROWS_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/manual_completion_pack/no_prior_manual_completion_rows.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
)

PRESERVED_COLUMNS: tuple[str, ...] = (
    "review_priority_rank",
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
)

MANUAL_COLUMNS: tuple[str, ...] = (
    "manual_cause_label",
    "manual_confidence_score",
    "manual_notes",
    "manual_next_action",
    "should_add_review_rule_candidate",
    "should_remain_shadow_only",
)

ASSISTANCE_COLUMNS: tuple[str, ...] = (
    "inspection_priority",
    "primary_evidence_to_check",
    "secondary_evidence_to_check",
    "possible_cause_labels_to_consider",
    "candidate_caution_note",
    "shadow_only_note",
    "operator_decision_prompt",
    "do_not_auto_label_flag",
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

BY_DEPARTMENT_COLUMNS: tuple[str, ...] = (
    "department",
    "row_count",
    "high_priority_rows",
    "normal_priority_rows",
    "low_availability_rows",
    "high_forecast_error_low_capital_rows",
    "actual_units_sold_total",
    "actual_gross_profit_total",
    "primary_evidence_focus",
    "sample_skus",
)

HIGH_GROSS_PROFIT_THRESHOLD = 40.0
HIGH_FORECAST_ERROR_THRESHOLD = 5.0
LOW_CAPITAL_LEFT_THRESHOLD = 5.0
LOW_GROSS_PROFIT_THRESHOLD = 15.0


class PromotionsNoPriorManualLabelAssistanceError(RuntimeError):
    """Raised when the no-prior manual-label assistance pack cannot be built safely."""


@dataclass(frozen=True)
class PromotionsNoPriorManualLabelAssistanceResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    guide_markdown: str


@dataclass(frozen=True)
class PromotionsNoPriorManualLabelAssistanceArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    by_department_csv_path: str
    guide_md_path: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsNoPriorManualLabelAssistanceError(f"CSV is empty: {path}")
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsNoPriorManualLabelAssistanceError(
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
        raise PromotionsNoPriorManualLabelAssistanceError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsNoPriorManualLabelAssistanceError(
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


def _high_forecast_error(row: pd.Series) -> bool:
    return abs(_as_float(row["forecast_error_units"])) >= HIGH_FORECAST_ERROR_THRESHOLD


def _low_capital_left(row: pd.Series) -> bool:
    return _as_float(row["capital_left_in_unsold_store_allocation"]) <= LOW_CAPITAL_LEFT_THRESHOLD


def _low_availability(row: pd.Series) -> bool:
    current_soh = _as_float(row["current_soh_units"])
    projected_on_hand = _as_float(row["projected_on_hand_at_promo_start"])
    target_stock = _as_float(row["target_stock_day_one_units"])
    return current_soh <= target_stock or projected_on_hand <= target_stock


def _department_focus_and_labels(department: str) -> tuple[str, tuple[str, ...]]:
    normalized = department.upper().strip()
    if normalized == "SKINCARE":
        return (
            "Check brand strength, category trust, gift or beauty mission, and promo mechanic.",
            (
                "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
                "BASKET_OR_MISSION_EFFECT",
                "PRICE_OR_PROMO_MECHANIC_EFFECT",
            ),
        )
    if normalized == "ORAL HEALTH":
        return (
            "Check essential-item demand, basket completion, and price sensitivity.",
            (
                "BASKET_OR_MISSION_EFFECT",
                "PRICE_OR_PROMO_MECHANIC_EFFECT",
                "STORE_SPECIFIC_DEMAND_NOT_CAPTURED",
            ),
        )
    if "NUTRITION" in normalized or "WELLBEIN" in normalized:
        return (
            "Check health-mission demand and stock availability.",
            (
                "BASKET_OR_MISSION_EFFECT",
                "ONLINE_OR_AVAILABILITY_EFFECT",
                "STORE_SPECIFIC_DEMAND_NOT_CAPTURED",
            ),
        )
    return (
        "Check store context, promo mechanic, and whether demand looks repeatable.",
        (
            "STORE_SPECIFIC_DEMAND_NOT_CAPTURED",
            "PRICE_OR_PROMO_MECHANIC_EFFECT",
            "BASKET_OR_MISSION_EFFECT",
        ),
    )


def _possible_cause_labels_to_consider(row: pd.Series) -> str:
    _, department_labels = _department_focus_and_labels(str(row["department"]))

    labels: list[str] = list(department_labels)
    if _high_forecast_error(row) and _low_capital_left(row):
        labels.extend(
            (
                "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
                "STORE_SPECIFIC_DEMAND_NOT_CAPTURED",
                "PRICE_OR_PROMO_MECHANIC_EFFECT",
                "BASKET_OR_MISSION_EFFECT",
            )
        )
    if _low_availability(row):
        labels.append("ONLINE_OR_AVAILABILITY_EFFECT")
    if _as_float(row["actual_gross_profit"]) <= LOW_GROSS_PROFIT_THRESHOLD:
        labels.append("RANDOM_ONE_OFF_DEMAND")
    labels.extend(("DATA_GAP_OR_LABEL_ERROR", "UNKNOWN_REQUIRES_REVIEW"))

    ordered_labels: list[str] = []
    for label_name in labels:
        if label_name not in MANUAL_CAUSE_LABEL_VALUES or label_name in ordered_labels:
            continue
        ordered_labels.append(label_name)
    return ", ".join(ordered_labels)


def _primary_evidence_to_check(row: pd.Series) -> str:
    if _high_forecast_error(row) and _low_capital_left(row):
        return "Check whether the demand was real and repeatable rather than a one-off surprise."
    if _low_availability(row):
        return "Check whether low stock or projected on-hand may have constrained sales."
    department_focus, _ = _department_focus_and_labels(str(row["department"]))
    return department_focus


def _secondary_evidence_to_check(row: pd.Series) -> str:
    parts: list[str] = []
    primary = _primary_evidence_to_check(row)
    department_focus, _ = _department_focus_and_labels(str(row["department"]))

    if department_focus != primary:
        parts.append(department_focus)
    if _low_availability(row) and "constrained sales" not in primary:
        parts.append("Check whether current SOH or projected on-hand suggests availability constrained sales.")
    if not parts:
        parts.append("Check nearby stores, promo mechanic, and any data gaps before choosing the final cause label.")
    return " ".join(parts)


def _inspection_priority(row: pd.Series) -> str:
    if _as_float(row["actual_gross_profit"]) >= HIGH_GROSS_PROFIT_THRESHOLD:
        return "HIGH"
    return "NORMAL"


def _candidate_caution_note(row: pd.Series) -> str:
    if _as_float(row["actual_gross_profit"]) <= LOW_GROSS_PROFIT_THRESHOLD:
        return (
            "Low gross profit means the operator should be especially cautious before proposing a review-rule candidate; prefer RANDOM_ONE_OFF_DEMAND, DATA_GAP_OR_LABEL_ERROR, or KEEP_SHADOW_ONLY when the cause is unclear."
        )
    if _low_availability(row):
        return (
            "Availability may be masking the cause; verify stock effects before marking any candidate."
        )
    if _high_forecast_error(row) and _low_capital_left(row):
        return (
            "Do not add a review-rule candidate unless the demand looks real, repeatable, and commercially sensible."
        )
    return (
        "Keep candidate judgement conservative; only flag a candidate when the cause looks repeatable and commercially sensible."
    )


def _shadow_only_note() -> str:
    return "Any candidate remains shadow-only until repeated evidence appears across more promotions."


def _operator_decision_prompt() -> str:
    return (
        "Use these prompts to inspect the row, then choose the final manual_cause_label yourself. If the cause stays unclear, use UNKNOWN_REQUIRES_REVIEW and explain why."
    )


def _build_rows_frame(manual_completion_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        manual_completion_rows_frame,
        PRESERVED_COLUMNS + MANUAL_COLUMNS,
        frame_name="manual_completion_rows_frame",
    )

    rows_frame = manual_completion_rows_frame.loc[:, PRESERVED_COLUMNS].copy()
    for column_name in MANUAL_COLUMNS:
        rows_frame[column_name] = ""

    rows_frame["inspection_priority"] = manual_completion_rows_frame.apply(
        _inspection_priority,
        axis=1,
    )
    rows_frame["primary_evidence_to_check"] = manual_completion_rows_frame.apply(
        _primary_evidence_to_check,
        axis=1,
    )
    rows_frame["secondary_evidence_to_check"] = manual_completion_rows_frame.apply(
        _secondary_evidence_to_check,
        axis=1,
    )
    rows_frame["possible_cause_labels_to_consider"] = manual_completion_rows_frame.apply(
        _possible_cause_labels_to_consider,
        axis=1,
    )
    rows_frame["candidate_caution_note"] = manual_completion_rows_frame.apply(
        _candidate_caution_note,
        axis=1,
    )
    rows_frame["shadow_only_note"] = _shadow_only_note()
    rows_frame["operator_decision_prompt"] = _operator_decision_prompt()
    rows_frame["do_not_auto_label_flag"] = 1
    return rows_frame.loc[:, PRESERVED_COLUMNS + MANUAL_COLUMNS + ASSISTANCE_COLUMNS].reset_index(drop=True)


def _build_summary_frame(
    rows_frame: pd.DataFrame,
    source_frame: pd.DataFrame,
) -> pd.DataFrame:
    rows_prepared = int(len(rows_frame.index))
    high_priority_rows = int(rows_frame["inspection_priority"].astype(str).eq("HIGH").sum())
    normal_priority_rows = rows_prepared - high_priority_rows
    do_not_auto_label_rows = int(pd.to_numeric(rows_frame["do_not_auto_label_flag"], errors="coerce").fillna(0).sum())
    manual_fields_blank_rows = int(
        rows_frame.loc[:, MANUAL_COLUMNS].fillna("").astype(str).eq("").all(axis=1).sum()
    )
    total_gross_profit = round(
        float(pd.to_numeric(rows_frame["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
        2,
    )
    total_capital_left = round(
        float(pd.to_numeric(rows_frame["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0).sum()),
        2,
    )
    departments_covered = int(rows_frame["department"].astype(str).nunique(dropna=True))

    production_order_changes = 0
    stage12_changes = 0
    for column_name in OPTIONAL_GUARDRAIL_COLUMNS:
        if column_name not in source_frame.columns:
            continue
        numeric_sum = int(pd.to_numeric(source_frame[column_name], errors="coerce").fillna(0).sum())
        if column_name == "production_order_change_flag":
            production_order_changes = numeric_sum
        if column_name == "stage_12_change_flag":
            stage12_changes = numeric_sum

    rows = [
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "ROWS_PREPARED",
            rows_prepared,
            "rows",
            _format_int(rows_prepared),
            "Rows prepared for human label assistance.",
        ),
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "HIGH_PRIORITY_ROWS",
            high_priority_rows,
            "rows",
            _format_int(high_priority_rows),
            "Rows with higher gross-profit stakes for manual review.",
        ),
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "NORMAL_PRIORITY_ROWS",
            normal_priority_rows,
            "rows",
            _format_int(normal_priority_rows),
            "Rows that still need review but carry lower gross-profit stakes.",
        ),
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "DO_NOT_AUTO_LABEL_ROWS",
            do_not_auto_label_rows,
            "rows",
            _format_int(do_not_auto_label_rows),
            "Every row remains operator-labelled only.",
        ),
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "MANUAL_FIELDS_BLANK_ROWS",
            manual_fields_blank_rows,
            "rows",
            _format_int(manual_fields_blank_rows),
            "The assistance pack leaves all manual fields blank for human judgement.",
        ),
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "DEPARTMENTS_COVERED",
            departments_covered,
            "departments",
            _format_int(departments_covered),
            "Unique departments represented in the assistance pack.",
        ),
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "TOTAL_GROSS_PROFIT_REPRESENTED",
            total_gross_profit,
            "dollars",
            _format_money(total_gross_profit),
            "Gross profit represented by the 18 no-prior rows.",
        ),
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "TOTAL_CAPITAL_LEFT_REPRESENTED",
            total_capital_left,
            "dollars",
            _format_money(total_capital_left),
            "Capital left represented by the 18 no-prior rows.",
        ),
        _summary_row(
            "MANUAL_LABEL_ASSISTANCE",
            "RECOMMENDATION",
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
            "label",
            "COMPLETE_MANUAL_WORKSHEET_FIRST",
            "Use this assistance pack to finish the manual worksheet consistently.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            production_order_changes,
            "rows",
            _format_int(production_order_changes),
            "This assistance pack does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage12_changes,
            "rows",
            _format_int(stage12_changes),
            "This assistance pack does not change Stage 12.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_by_department_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for department, group in rows_frame.groupby("department", sort=False, dropna=False):
        current_soh = pd.to_numeric(group["current_soh_units"], errors="coerce").fillna(0.0)
        projected = pd.to_numeric(group["projected_on_hand_at_promo_start"], errors="coerce").fillna(0.0)
        target = pd.to_numeric(group["target_stock_day_one_units"], errors="coerce").fillna(0.0)
        forecast_error = pd.to_numeric(group["forecast_error_units"], errors="coerce").fillna(0.0)
        capital_left = pd.to_numeric(group["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0)
        low_availability_rows = int((current_soh.le(target) | projected.le(target)).sum())
        high_error_low_capital_rows = int(
            (forecast_error.abs().ge(HIGH_FORECAST_ERROR_THRESHOLD) & capital_left.le(LOW_CAPITAL_LEFT_THRESHOLD)).sum()
        )
        department_focus, _ = _department_focus_and_labels(str(department))
        records.append(
            {
                "department": str(department),
                "row_count": int(len(group.index)),
                "high_priority_rows": int(group["inspection_priority"].astype(str).eq("HIGH").sum()),
                "normal_priority_rows": int(group["inspection_priority"].astype(str).eq("NORMAL").sum()),
                "low_availability_rows": low_availability_rows,
                "high_forecast_error_low_capital_rows": high_error_low_capital_rows,
                "actual_units_sold_total": round(
                    float(pd.to_numeric(group["actual_units_sold"], errors="coerce").fillna(0.0).sum()),
                    2,
                ),
                "actual_gross_profit_total": round(
                    float(pd.to_numeric(group["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
                    2,
                ),
                "primary_evidence_focus": department_focus,
                "sample_skus": _sample_skus(group["sku_number"]),
            }
        )
    by_department_frame = pd.DataFrame(records, columns=BY_DEPARTMENT_COLUMNS)
    return by_department_frame.sort_values(
        by=["row_count", "actual_gross_profit_total", "department"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_guide_markdown(
    rows_frame: pd.DataFrame,
    by_department_frame: pd.DataFrame,
) -> str:
    rows_prepared = int(len(rows_frame.index))
    high_priority_rows = int(rows_frame["inspection_priority"].astype(str).eq("HIGH").sum())
    top_departments = ", ".join(
        f"{row.department} ({int(row.row_count)})"
        for row in by_department_frame.head(3).itertuples(index=False)
    )
    lines = [
        "# No-Prior Manual Label Assistance Guide",
        "",
        "This is not an order file.",
        "This does not complete the manual labels.",
        "Production order changes = 0.",
        "Stage 12 changes = 0.",
        "",
        f"The goal is to help the operator classify the {rows_prepared} rows faster and more consistently.",
        "The operator must still choose the final `manual_cause_label` for every row.",
        "Any candidate remains shadow-only until repeated evidence appears across more promotions.",
        "",
        f"High-priority rows: {_format_int(high_priority_rows)}.",
        f"Top departments: {top_departments if top_departments else 'none'}.",
        "",
        "How to use this pack:",
        "1. Start with the HIGH-priority rows because they carry the largest gross-profit signal.",
        "2. Read the primary and secondary evidence prompts before deciding on a cause label.",
        "3. Treat the possible cause labels as options to consider, not as a final answer.",
        "4. Keep manual fields blank until the operator decides the final label, confidence score, notes, and next action.",
        "5. Keep any interesting candidate shadow-only unless repeated evidence appears beyond this single promotion.",
        "",
        "This pack does not infer a final label automatically. It is only a human-support layer.",
    ]
    return "\n".join(lines) + "\n"


def build_promotions_no_prior_manual_label_assistance(
    *,
    manual_completion_rows_frame: pd.DataFrame,
) -> PromotionsNoPriorManualLabelAssistanceResult:
    rows_frame = _build_rows_frame(manual_completion_rows_frame)
    summary_frame = _build_summary_frame(rows_frame, manual_completion_rows_frame)
    by_department_frame = _build_by_department_frame(rows_frame)
    guide_markdown = _build_guide_markdown(rows_frame, by_department_frame)
    return PromotionsNoPriorManualLabelAssistanceResult(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_department_frame=by_department_frame,
        guide_markdown=guide_markdown,
    )


def write_promotions_no_prior_manual_label_assistance(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsNoPriorManualLabelAssistanceArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsNoPriorManualLabelAssistanceError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_no_prior_manual_label_assistance(
        manual_completion_rows_frame=_read_csv(review_artifact_path / INPUT_ROWS_RELATIVE_PATH),
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

    rows_csv_path = destination_root / "no_prior_manual_label_assistance_rows.csv"
    summary_csv_path = destination_root / "no_prior_manual_label_assistance_summary.csv"
    by_department_csv_path = destination_root / "no_prior_manual_label_assistance_by_department.csv"
    guide_md_path = destination_root / "no_prior_manual_label_assistance_guide.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    add_provenance_columns(result.by_department_frame.copy(), manifest).to_csv(
        by_department_csv_path,
        index=False,
    )
    guide_md_path.write_text(result.guide_markdown, encoding="utf-8")

    return PromotionsNoPriorManualLabelAssistanceArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        guide_md_path=str(guide_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed human-support pack for no-prior-demand surprise rows without inferring final labels."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_no_prior_manual_label_assistance(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("no_prior_manual_label_assistance_rows", artifacts.rows_csv_path)
    print("no_prior_manual_label_assistance_summary", artifacts.summary_csv_path)
    print("no_prior_manual_label_assistance_by_department", artifacts.by_department_csv_path)
    print("no_prior_manual_label_assistance_guide", artifacts.guide_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())