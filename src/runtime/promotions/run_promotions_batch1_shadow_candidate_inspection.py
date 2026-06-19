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


OUTPUT_FOLDER_NAME = "shadow_candidate_inspection"
INPUT_ROWS_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/batch1_completion_helper/inspection_ingest/no_prior_manual_review_rule_candidates.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
)

PRESERVED_COLUMNS: tuple[str, ...] = (
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

INSPECTION_COLUMNS: tuple[str, ...] = (
    "shadow_candidate_inspection_status",
    "rule_concentration_flag",
    "brand_category_pattern_flag",
    "low_capital_risk_flag",
    "positive_gross_profit_flag",
    "forecast_blindspot_flag",
    "shadow_only_keep_flag",
    "inspection_reason",
    "recommended_next_action",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)

BY_RULE_COLUMNS: tuple[str, ...] = (
    "proposed_review_rule_candidate",
    "row_count",
    "share_of_rows",
    "keep_shadow_candidate_rows",
    "needs_more_evidence_rows",
    "reject_candidate_rows",
    "departments_covered",
    "manual_causes",
    "average_manual_confidence_score",
    "gross_profit_total",
    "capital_left_total",
    "sample_skus",
)

KEEP_SHADOW_CANDIDATE = "KEEP_SHADOW_CANDIDATE"
NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"
REJECT_CANDIDATE = "REJECT_CANDIDATE"

KEEP_AS_SHADOW_REVIEW_RULE_CANDIDATE = "KEEP_AS_SHADOW_REVIEW_RULE_CANDIDATE"
REVIEW_MORE_PROMOTIONS_FOR_REPEATABILITY = "REVIEW_MORE_PROMOTIONS_FOR_REPEATABILITY"
COMPLETE_FULL_18_ROW_MANUAL_REVIEW = "COMPLETE_FULL_18_ROW_MANUAL_REVIEW"
DO_NOT_PROMOTE_TO_PRODUCTION = "DO_NOT_PROMOTE_TO_PRODUCTION"

RULE_CONCENTRATION_THRESHOLD = 0.75
PATTERN_CONCENTRATION_THRESHOLD = 0.75
LOW_CAPITAL_LEFT_THRESHOLD = 5.0
HIGH_CONFIDENCE_THRESHOLD = 70.0


class PromotionsBatch1ShadowCandidateInspectionError(RuntimeError):
    """Raised when the Batch 1 shadow-only candidate inspection cannot run safely."""


@dataclass(frozen=True)
class PromotionsBatch1ShadowCandidateInspectionResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_rule_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsBatch1ShadowCandidateInspectionArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    by_rule_csv_path: str
    memo_md_path: str


def _read_csv(
    path: str | Path,
    *,
    allow_empty: bool = False,
    empty_columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame(columns=list(empty_columns or ()))
        raise PromotionsBatch1ShadowCandidateInspectionError(f"CSV is empty: {path}")
    if frame.empty and not allow_empty:
        raise PromotionsBatch1ShadowCandidateInspectionError(f"CSV is empty: {path}")
    if frame.empty and empty_columns is not None:
        for column_name in empty_columns:
            if column_name not in frame.columns:
                frame[column_name] = pd.Series(dtype="object")
        frame = frame.loc[:, list(dict.fromkeys([*frame.columns.tolist(), *empty_columns]))]
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsBatch1ShadowCandidateInspectionError(
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
        raise PromotionsBatch1ShadowCandidateInspectionError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsBatch1ShadowCandidateInspectionError(
            f"{frame_name} is missing required columns: {missing}"
        )


def _as_float(value: object) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _format_int(value: float | int) -> str:
    return f"{int(round(float(value))):,}"


def _format_share(value: float) -> str:
    return f"{value * 100:.1f}%"


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


def _sample_values(values: pd.Series, *, limit: int = 5) -> str:
    unique_values: list[str] = []
    for value in values.astype(str).tolist():
        cleaned = value.strip()
        if not cleaned or cleaned in unique_values:
            continue
        unique_values.append(cleaned)
        if len(unique_values) >= limit:
            break
    return ", ".join(unique_values)


def _dominant_value_stats(values: pd.Series) -> tuple[str, int, float]:
    cleaned = values.fillna("").astype(str).str.strip()
    cleaned = cleaned.loc[cleaned.ne("")]
    if cleaned.empty:
        return "", 0, 0.0
    counts = cleaned.value_counts(dropna=False)
    dominant_value = str(counts.index[0]).strip()
    dominant_count = int(counts.iloc[0])
    share = dominant_count / float(len(cleaned.index))
    return dominant_value, dominant_count, share


def _reason_parts(
    *,
    row: pd.Series,
    dominant_rule: str,
    dominant_department: str,
    dominant_manual_cause: str,
) -> list[str]:
    reasons: list[str] = []
    if int(row["rule_concentration_flag"]) == 1 and dominant_rule:
        reasons.append(f"shares the dominant proposed rule {dominant_rule}")
    if int(row["brand_category_pattern_flag"]) == 1:
        reasons.append(
            f"matches the dominant {dominant_department or 'category'} / {dominant_manual_cause or 'manual-cause'} pattern"
        )
    if int(row["low_capital_risk_flag"]) == 1:
        reasons.append("capital left is near zero")
    else:
        reasons.append("capital left still needs caution")
    if int(row["positive_gross_profit_flag"]) == 1:
        reasons.append(f"gross profit remains positive at {_format_money(_as_float(row['actual_gross_profit']))}")
    else:
        reasons.append("gross profit is not positive")
    if int(row["forecast_blindspot_flag"]) == 1:
        units_outperformance = max(
            _as_float(row["actual_units_sold"]) - _as_float(row["expected_promo_demand"]),
            0.0,
        )
        reasons.append(
            f"actual units sold exceeded expected promo demand by {_format_int(units_outperformance)} units"
        )
    else:
        reasons.append("actual demand did not clearly exceed expected promo demand")
    if int(row["shadow_only_keep_flag"]) == 1:
        reasons.append("candidate remains shadow-only and is not production-ready")
    return reasons


def _recommended_next_action(status: str, row: pd.Series) -> str:
    if status == REJECT_CANDIDATE:
        return DO_NOT_PROMOTE_TO_PRODUCTION
    if status == NEEDS_MORE_EVIDENCE:
        if int(_as_float(row.get("partial_review_flag", 0.0))) == 1:
            return COMPLETE_FULL_18_ROW_MANUAL_REVIEW
        return REVIEW_MORE_PROMOTIONS_FOR_REPEATABILITY
    return KEEP_AS_SHADOW_REVIEW_RULE_CANDIDATE


def _inspection_status(row: pd.Series) -> str:
    if _as_float(row["production_order_change_flag"]) != 0.0 or _as_float(row["stage_12_change_flag"]) != 0.0:
        return REJECT_CANDIDATE
    if int(row["positive_gross_profit_flag"]) == 0:
        return REJECT_CANDIDATE
    strength_score = sum(
        int(row[column_name])
        for column_name in (
            "rule_concentration_flag",
            "brand_category_pattern_flag",
            "low_capital_risk_flag",
            "positive_gross_profit_flag",
            "forecast_blindspot_flag",
            "shadow_only_keep_flag",
        )
    )
    confidence_ok = _as_float(row["manual_confidence_score"]) >= HIGH_CONFIDENCE_THRESHOLD
    if int(row["shadow_only_keep_flag"]) == 1 and confidence_ok and strength_score >= 5:
        return KEEP_SHADOW_CANDIDATE
    if int(row["shadow_only_keep_flag"]) == 1 and strength_score >= 3:
        return NEEDS_MORE_EVIDENCE
    return REJECT_CANDIDATE


def _build_rows_frame(candidate_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(candidate_frame, PRESERVED_COLUMNS, frame_name="candidate_frame")

    rows_frame = candidate_frame.loc[:, PRESERVED_COLUMNS].copy()
    if rows_frame.empty:
        for column_name in INSPECTION_COLUMNS:
            rows_frame[column_name] = pd.Series(dtype="object")
        return rows_frame.loc[:, PRESERVED_COLUMNS + INSPECTION_COLUMNS]

    dominant_rule, _, dominant_rule_share = _dominant_value_stats(rows_frame["proposed_review_rule_candidate"])
    dominant_department, _, dominant_department_share = _dominant_value_stats(rows_frame["department"])
    dominant_manual_cause, _, dominant_manual_cause_share = _dominant_value_stats(rows_frame["manual_cause_label"])
    pattern_present = (
        dominant_department_share >= PATTERN_CONCENTRATION_THRESHOLD
        and dominant_manual_cause_share >= PATTERN_CONCENTRATION_THRESHOLD
    )

    rows_frame["rule_concentration_flag"] = rows_frame["proposed_review_rule_candidate"].apply(
        lambda value: int(
            dominant_rule_share >= RULE_CONCENTRATION_THRESHOLD
            and _normalize_text(value) != ""
            and _normalize_text(value) == dominant_rule
        )
    )
    rows_frame["brand_category_pattern_flag"] = rows_frame.apply(
        lambda row: int(
            pattern_present
            and _normalize_text(row["department"]) == dominant_department
            and _normalize_text(row["manual_cause_label"]) == dominant_manual_cause
        ),
        axis=1,
    )
    rows_frame["low_capital_risk_flag"] = rows_frame[
        "capital_left_in_unsold_store_allocation"
    ].apply(lambda value: int(_as_float(value) <= LOW_CAPITAL_LEFT_THRESHOLD))
    rows_frame["positive_gross_profit_flag"] = rows_frame["actual_gross_profit"].apply(
        lambda value: int(_as_float(value) > 0.0)
    )
    rows_frame["forecast_blindspot_flag"] = rows_frame.apply(
        lambda row: int(_as_float(row["actual_units_sold"]) > _as_float(row["expected_promo_demand"])),
        axis=1,
    )
    rows_frame["shadow_only_keep_flag"] = rows_frame.apply(
        lambda row: int(
            _normalize_text(row["proposed_review_rule_candidate"]) != ""
            and int(row["positive_gross_profit_flag"]) == 1
            and int(row["forecast_blindspot_flag"]) == 1
            and _as_float(row["production_order_change_flag"]) == 0.0
            and _as_float(row["stage_12_change_flag"]) == 0.0
        ),
        axis=1,
    )
    rows_frame["shadow_candidate_inspection_status"] = rows_frame.apply(_inspection_status, axis=1)
    rows_frame["inspection_reason"] = rows_frame.apply(
        lambda row: "; ".join(
            _reason_parts(
                row=row,
                dominant_rule=dominant_rule,
                dominant_department=dominant_department,
                dominant_manual_cause=dominant_manual_cause,
            )
        ),
        axis=1,
    )
    rows_frame["recommended_next_action"] = rows_frame.apply(
        lambda row: _recommended_next_action(str(row["shadow_candidate_inspection_status"]), row),
        axis=1,
    )
    return rows_frame.loc[:, PRESERVED_COLUMNS + INSPECTION_COLUMNS]


def _build_summary_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    rows_inspected = int(len(rows_frame.index))
    candidate_rule_count = int(
        rows_frame["proposed_review_rule_candidate"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique()
    )
    dominant_rule, dominant_rule_count, dominant_rule_share = _dominant_value_stats(
        rows_frame["proposed_review_rule_candidate"]
    )
    dominant_department, _, _ = _dominant_value_stats(rows_frame["department"])
    gross_profit_represented = round(
        float(pd.to_numeric(rows_frame.get("actual_gross_profit", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()),
        2,
    )
    capital_left_represented = round(
        float(
            pd.to_numeric(
                rows_frame.get("capital_left_in_unsold_store_allocation", pd.Series(dtype=float)),
                errors="coerce",
            )
            .fillna(0.0)
            .sum()
        ),
        2,
    )
    keep_rows = int(rows_frame.get("shadow_candidate_inspection_status", pd.Series(dtype=str)).eq(KEEP_SHADOW_CANDIDATE).sum())
    needs_more_evidence_rows = int(
        rows_frame.get("shadow_candidate_inspection_status", pd.Series(dtype=str)).eq(NEEDS_MORE_EVIDENCE).sum()
    )
    reject_rows = int(rows_frame.get("shadow_candidate_inspection_status", pd.Series(dtype=str)).eq(REJECT_CANDIDATE).sum())
    production_order_changes = int(
        pd.to_numeric(rows_frame.get("production_order_change_flag", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    )
    stage12_changes = int(
        pd.to_numeric(rows_frame.get("stage_12_change_flag", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    )

    if rows_inspected == 0:
        overall_status = NEEDS_MORE_EVIDENCE
        recommendation = REVIEW_MORE_PROMOTIONS_FOR_REPEATABILITY
        status_reason = "No Batch 1 candidate-ready rows were available to inspect."
    elif keep_rows == rows_inspected:
        overall_status = KEEP_SHADOW_CANDIDATE
        recommendation = KEEP_AS_SHADOW_REVIEW_RULE_CANDIDATE
        status_reason = "The Batch 1 candidate slice forms a coherent shadow-only review-rule candidate set, but it is still not production-ready."
    elif reject_rows == rows_inspected:
        overall_status = REJECT_CANDIDATE
        recommendation = DO_NOT_PROMOTE_TO_PRODUCTION
        status_reason = "The Batch 1 candidate slice does not support a safe shadow-only rule candidate."
    else:
        overall_status = NEEDS_MORE_EVIDENCE
        recommendation = REVIEW_MORE_PROMOTIONS_FOR_REPEATABILITY
        status_reason = "The Batch 1 candidate slice is directionally useful, but it still needs broader repeatability evidence and the remaining 18-row review context."

    rows = [
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "ROWS_INSPECTED",
            rows_inspected,
            "rows",
            _format_int(rows_inspected),
            "Batch 1 candidate-ready rows inspected in this shadow-only pass.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "CANDIDATE_RULE_COUNT",
            candidate_rule_count,
            "rules",
            _format_int(candidate_rule_count),
            "Distinct proposed review rules represented in the Batch 1 candidate slice.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "DOMINANT_PROPOSED_RULE",
            dominant_rule or "NONE",
            "label",
            dominant_rule or "NONE",
            "Most common proposed review rule in the Batch 1 candidate slice.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "DOMINANT_RULE_SHARE",
            round(dominant_rule_share, 4),
            "share",
            _format_share(dominant_rule_share),
            "Share of candidate rows covered by the dominant proposed review rule.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "DOMINANT_DEPARTMENT",
            dominant_department or "NONE",
            "label",
            dominant_department or "NONE",
            "Most common department represented in the Batch 1 candidate slice.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "GROSS_PROFIT_REPRESENTED",
            gross_profit_represented,
            "dollars",
            _format_money(gross_profit_represented),
            "Gross profit represented by the inspected Batch 1 candidates.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "CAPITAL_LEFT_REPRESENTED",
            capital_left_represented,
            "dollars",
            _format_money(capital_left_represented),
            "Capital left represented by the inspected Batch 1 candidates.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "KEEP_SHADOW_CANDIDATE_ROWS",
            keep_rows,
            "rows",
            _format_int(keep_rows),
            "Rows strong enough to keep as shadow-only review-rule candidates.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "NEEDS_MORE_EVIDENCE_ROWS",
            needs_more_evidence_rows,
            "rows",
            _format_int(needs_more_evidence_rows),
            "Rows that look directionally useful but still need more repeatability evidence.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "REJECT_CANDIDATE_ROWS",
            reject_rows,
            "rows",
            _format_int(reject_rows),
            "Rows that should not be carried forward as shadow-only review-rule candidates.",
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "OVERALL_INSPECTION_STATUS",
            overall_status,
            "label",
            overall_status,
            status_reason,
        ),
        _summary_row(
            "BATCH1_SHADOW_CANDIDATE_INSPECTION",
            "RECOMMENDATION",
            recommendation,
            "label",
            recommendation,
            "Recommended next step for this Batch 1 shadow-only candidate slice.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            production_order_changes,
            "rows",
            _format_int(production_order_changes),
            "This inspection pass does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage12_changes,
            "rows",
            _format_int(stage12_changes),
            "This inspection pass does not change Stage 12.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_by_rule_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_RULE_COLUMNS)

    total_rows = len(rows_frame.index)
    for proposed_rule, group in rows_frame.groupby("proposed_review_rule_candidate", sort=False, dropna=False):
        records.append(
            {
                "proposed_review_rule_candidate": str(proposed_rule),
                "row_count": int(len(group.index)),
                "share_of_rows": round(float(len(group.index)) / float(total_rows), 4) if total_rows > 0 else 0.0,
                "keep_shadow_candidate_rows": int(group["shadow_candidate_inspection_status"].eq(KEEP_SHADOW_CANDIDATE).sum()),
                "needs_more_evidence_rows": int(group["shadow_candidate_inspection_status"].eq(NEEDS_MORE_EVIDENCE).sum()),
                "reject_candidate_rows": int(group["shadow_candidate_inspection_status"].eq(REJECT_CANDIDATE).sum()),
                "departments_covered": int(group["department"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()),
                "manual_causes": _sample_values(group["manual_cause_label"]),
                "average_manual_confidence_score": round(
                    float(pd.to_numeric(group["manual_confidence_score"], errors="coerce").fillna(0.0).mean()),
                    2,
                ),
                "gross_profit_total": round(
                    float(pd.to_numeric(group["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
                    2,
                ),
                "capital_left_total": round(
                    float(
                        pd.to_numeric(
                            group["capital_left_in_unsold_store_allocation"],
                            errors="coerce",
                        )
                        .fillna(0.0)
                        .sum()
                    ),
                    2,
                ),
                "sample_skus": _sample_values(group["sku_number"]),
            }
        )
    by_rule_frame = pd.DataFrame(records, columns=BY_RULE_COLUMNS)
    return by_rule_frame.sort_values(
        by=["row_count", "gross_profit_total", "proposed_review_rule_candidate"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_memo(rows_frame: pd.DataFrame, summary_frame: pd.DataFrame, by_rule_frame: pd.DataFrame) -> str:
    rows_lookup = summary_frame.set_index("metric_name")
    rows_inspected = int(rows_lookup.loc["ROWS_INSPECTED", "metric_value"])
    dominant_rule = str(rows_lookup.loc["DOMINANT_PROPOSED_RULE", "metric_value"])
    gross_profit_represented = float(rows_lookup.loc["GROSS_PROFIT_REPRESENTED", "metric_value"])
    capital_left_represented = float(rows_lookup.loc["CAPITAL_LEFT_REPRESENTED", "metric_value"])
    overall_status = str(rows_lookup.loc["OVERALL_INSPECTION_STATUS", "metric_value"])
    recommendation = str(rows_lookup.loc["RECOMMENDATION", "metric_value"])
    production_order_changes = int(rows_lookup.loc["PRODUCTION_ORDER_CHANGES", "metric_value"])
    stage12_changes = int(rows_lookup.loc["STAGE12_CHANGES", "metric_value"])
    keep_rows = int(rows_lookup.loc["KEEP_SHADOW_CANDIDATE_ROWS", "metric_value"])
    candidate_rule_count = int(rows_lookup.loc["CANDIDATE_RULE_COUNT", "metric_value"])
    top_rule_text = "none"
    if not by_rule_frame.empty:
        first_rule = by_rule_frame.iloc[0]
        top_rule_text = (
            f"{first_rule['proposed_review_rule_candidate']} "
            f"({int(first_rule['row_count'])} rows; {_format_money(_as_float(first_rule['gross_profit_total']))} gross profit)"
        )

    lines = [
        "# Batch 1 Shadow-Only Candidate Inspection Memo",
        "",
        "This is not an order file.",
        "No training was started.",
        f"Production order changes = {production_order_changes}.",
        f"Stage 12 changes = {stage12_changes}.",
        "",
    ]

    if rows_inspected == 0:
        lines.extend(
            [
                "No Batch 1 candidate-ready rows were available to inspect in this pass.",
                "That means there is no shadow-only review-rule candidate set to evaluate yet.",
            ]
        )
    else:
        lines.extend(
            [
                f"This pass inspected {rows_inspected} Batch 1 candidate-ready rows representing {_format_money(gross_profit_represented)} gross profit and {_format_money(capital_left_represented)} capital left.",
                f"The dominant proposed rule is {dominant_rule}, and the strongest rule cluster is {top_rule_text}.",
                (
                    f"{keep_rows} of {rows_inspected} rows currently look strong enough to keep as shadow-only review-rule candidates."
                    if overall_status == KEEP_SHADOW_CANDIDATE
                    else "The inspected rows are directionally useful, but they still need more evidence before they should be treated as a stable shadow-only rule candidate set."
                    if overall_status == NEEDS_MORE_EVIDENCE
                    else "The inspected rows do not currently support a safe shadow-only rule candidate set."
                ),
                "Any rule candidate found here remains shadow-only and is not production-ready.",
            ]
        )

    lines.extend(
        [
            "",
            "Full train remains blocked.",
            "Shadow-only data inspection remains allowed.",
            "Production promotion still requires repeated evidence across more promotions and completion of the full 18-row manual review.",
            "",
            f"Overall inspection status: {overall_status}.",
            f"Recommendation: {recommendation}.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_promotions_batch1_shadow_candidate_inspection(
    *,
    candidate_rows_frame: pd.DataFrame,
) -> PromotionsBatch1ShadowCandidateInspectionResult:
    rows_frame = _build_rows_frame(candidate_rows_frame)
    summary_frame = _build_summary_frame(rows_frame)
    by_rule_frame = _build_by_rule_frame(rows_frame)
    memo_markdown = _build_memo(rows_frame, summary_frame, by_rule_frame)
    return PromotionsBatch1ShadowCandidateInspectionResult(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_rule_frame=by_rule_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_batch1_shadow_candidate_inspection(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsBatch1ShadowCandidateInspectionArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsBatch1ShadowCandidateInspectionError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_batch1_shadow_candidate_inspection(
        candidate_rows_frame=_read_csv(
            review_artifact_path / INPUT_ROWS_RELATIVE_PATH,
            allow_empty=True,
            empty_columns=PRESERVED_COLUMNS,
        ),
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else review_artifact_path
        / "review_overlay_packet"
        / "operator_review_memo"
        / "no_prior_demand_manual_inspection"
        / "batch1_completion_helper"
        / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "batch1_shadow_candidate_inspection_rows.csv"
    summary_csv_path = destination_root / "batch1_shadow_candidate_inspection_summary.csv"
    by_rule_csv_path = destination_root / "batch1_shadow_candidate_inspection_by_rule.csv"
    memo_md_path = destination_root / "batch1_shadow_candidate_inspection_memo.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    add_provenance_columns(result.by_rule_frame.copy(), manifest).to_csv(by_rule_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsBatch1ShadowCandidateInspectionArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        by_rule_csv_path=str(by_rule_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a governed shadow-only inspection pass for Batch 1 no-prior review-rule candidates without starting training or changing production logic."
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_batch1_shadow_candidate_inspection(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("batch1_shadow_candidate_inspection_rows", artifacts.rows_csv_path)
    print("batch1_shadow_candidate_inspection_summary", artifacts.summary_csv_path)
    print("batch1_shadow_candidate_inspection_by_rule", artifacts.by_rule_csv_path)
    print("batch1_shadow_candidate_inspection_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())