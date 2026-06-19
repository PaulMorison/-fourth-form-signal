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


OUTPUT_FOLDER_NAME = "action_layer_unresolved_inspection"
INPUT_ROWS_RELATIVE_PATH = Path("action_layer_recalibration_rows.csv")
INPUT_SUMMARY_RELATIVE_PATH = Path("action_layer_recalibration_summary.csv")
READINESS_SUMMARY_RELATIVE_PATH = Path(
    "pretrain_readiness_inspection/pretrain_readiness_summary.csv"
)
BATCH1_SHADOW_SUMMARY_RELATIVE_PATH = Path(
    "review_overlay_packet/operator_review_memo/no_prior_demand_manual_inspection/"
    "batch1_completion_helper/shadow_candidate_inspection/"
    "batch1_shadow_candidate_inspection_summary.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
    str(INPUT_SUMMARY_RELATIVE_PATH),
    str(READINESS_SUMMARY_RELATIVE_PATH),
    str(BATCH1_SHADOW_SUMMARY_RELATIVE_PATH),
)

CORE_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
)

FLAG_COLUMNS: tuple[str, ...] = (
    "action_too_conservative_flag",
    "review_should_have_triggered_flag",
    "action_too_aggressive_flag",
)

REQUESTED_COLUMNS: tuple[str, ...] = (
    "operator_decision",
    "operator_action",
    "order_units",
    "actual_units_sold",
    "expected_promo_demand",
    "forecast_error_units",
    "actual_gross_profit",
    "capital_left_in_unsold_store_allocation",
    "recommended_order_units",
    "final_store_order_units",
    "action_too_conservative_flag",
    "review_should_have_triggered_flag",
    "production_order_change_flag",
    "stage_12_change_flag",
)

INSPECTION_COLUMNS: tuple[str, ...] = (
    "source_row_number",
    "source_rule_flag",
    "action_layer_inspection_bucket",
    "over_suppression_candidate_flag",
    "valid_conservative_block_flag",
    "reporting_or_text_issue_flag",
    "needs_more_evidence_flag",
    "commercial_priority",
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

BY_BUCKET_COLUMNS: tuple[str, ...] = (
    "action_layer_inspection_bucket",
    "row_count",
    "unique_source_rows",
    "share_of_rows",
    "high_priority_rows",
    "source_rule_flags",
    "departments_covered",
    "actual_units_total",
    "forecast_error_units_total",
    "gross_profit_total",
    "capital_left_total",
    "sample_skus",
)

UNRESOLVED_FLAG_LABELS: tuple[str, ...] = (
    "ACTION_TOO_CONSERVATIVE",
    "REVIEW_SHOULD_HAVE_TRIGGERED",
    "ACTION_TOO_AGGRESSIVE",
)

OVER_SUPPRESSION_CANDIDATE = "OVER_SUPPRESSION_CANDIDATE"
VALID_CONSERVATIVE_BLOCK = "VALID_CONSERVATIVE_BLOCK"
REPORTING_OR_TEXT_ISSUE = "REPORTING_OR_TEXT_ISSUE"
NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"

LOW = "LOW"
MEDIUM = "MEDIUM"
HIGH = "HIGH"

OVER_SUPPRESSION_DOMINANT = "OVER_SUPPRESSION_DOMINANT"
MIXED_REVIEW_DEBT = "MIXED_REVIEW_DEBT"
CONSERVATIVE_BLOCKS_MOSTLY_VALID = "CONSERVATIVE_BLOCKS_MOSTLY_VALID"

SHADOW_ONLY_TARGETED_ACTION_LAYER_REVIEW = "SHADOW_ONLY_TARGETED_ACTION_LAYER_REVIEW"
FIX_REPORTING_AND_ROUTING_SHADOW_ONLY = "FIX_REPORTING_AND_ROUTING_SHADOW_ONLY"
GATHER_MORE_EVIDENCE_SHADOW_ONLY = "GATHER_MORE_EVIDENCE_SHADOW_ONLY"

TEST_SHADOW_ONLY_ACTION_LAYER_RELAXATION = "TEST_SHADOW_ONLY_ACTION_LAYER_RELAXATION"
TEST_SHADOW_ONLY_REVIEW_TRIGGER = "TEST_SHADOW_ONLY_REVIEW_TRIGGER"
KEEP_CONSERVATIVE_BLOCK_AND_GATHER_MORE_CASES = (
    "KEEP_CONSERVATIVE_BLOCK_AND_GATHER_MORE_CASES"
)
FIX_REPORTING_TEXT_AND_ROUTING = "FIX_REPORTING_TEXT_AND_ROUTING"
COLLECT_MORE_EVIDENCE_BEFORE_RULE_CHANGE = (
    "COLLECT_MORE_EVIDENCE_BEFORE_RULE_CHANGE"
)

HIGH_GROSS_PROFIT_THRESHOLD = 40.0
MEDIUM_GROSS_PROFIT_THRESHOLD = 10.0
HIGH_ACTUAL_UNITS_THRESHOLD = 10.0
MEDIUM_ACTUAL_UNITS_THRESHOLD = 6.0
HIGH_DEMAND_GAP_THRESHOLD = 8.0
MEDIUM_DEMAND_GAP_THRESHOLD = 4.0
WEAK_GROSS_PROFIT_THRESHOLD = 5.0
MEANINGFUL_CAPITAL_LEFT_THRESHOLD = 20.0


class PromotionsActionLayerUnresolvedInspectionError(RuntimeError):
    """Raised when the unresolved action-layer inspection cannot run safely."""


@dataclass(frozen=True)
class PromotionsActionLayerUnresolvedInspectionResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_bucket_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsActionLayerUnresolvedInspectionArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    by_bucket_csv_path: str
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
        raise PromotionsActionLayerUnresolvedInspectionError(f"CSV is empty: {path}")
    if frame.empty and not allow_empty:
        raise PromotionsActionLayerUnresolvedInspectionError(f"CSV is empty: {path}")
    if frame.empty and empty_columns is not None:
        for column_name in empty_columns:
            if column_name not in frame.columns:
                frame[column_name] = pd.Series(dtype="object")
        frame = frame.loc[:, list(dict.fromkeys([*frame.columns.tolist(), *empty_columns]))]
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsActionLayerUnresolvedInspectionError(
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
        raise PromotionsActionLayerUnresolvedInspectionError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsActionLayerUnresolvedInspectionError(
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


def _format_float(value: float, *, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


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


def _all_missing_or_blank(values: pd.Series) -> bool:
    normalized = values.fillna("").astype(str).str.strip()
    return normalized.eq("").all()


def _metric_lookup(frame: pd.DataFrame | None) -> dict[str, object]:
    if frame is None or frame.empty or "metric_name" not in frame.columns:
        return {}
    lookup: dict[str, object] = {}
    for row in frame.itertuples(index=False):
        lookup[str(getattr(row, "metric_name"))] = getattr(row, "metric_value")
    return lookup


def _readiness_reason(frame: pd.DataFrame | None, readiness_check: str) -> str:
    if frame is None or frame.empty:
        return ""
    if "readiness_check" not in frame.columns or "reason" not in frame.columns:
        return ""
    matched = frame.loc[frame["readiness_check"].astype(str).eq(readiness_check)]
    if matched.empty:
        return ""
    return _normalize_text(matched.iloc[0]["reason"])


def _ensure_requested_columns(source_frame: pd.DataFrame) -> pd.DataFrame:
    frame = source_frame.copy()

    for column_name in REQUESTED_COLUMNS:
        if column_name not in frame.columns:
            frame[column_name] = pd.Series(dtype="object")

    if not frame.empty:
        actual_units = pd.to_numeric(frame.get("actual_units_sold"), errors="coerce").fillna(0.0)
        expected_demand = pd.to_numeric(frame.get("expected_promo_demand"), errors="coerce").fillna(0.0)

        if _all_missing_or_blank(frame["order_units"]):
            frame["order_units"] = pd.to_numeric(
                frame.get("recommended_order_units"),
                errors="coerce",
            ).fillna(0.0)

        if _all_missing_or_blank(frame["forecast_error_units"]):
            frame["forecast_error_units"] = actual_units - expected_demand

        if _all_missing_or_blank(frame["actual_gross_profit"]):
            frame["actual_gross_profit"] = pd.to_numeric(
                frame.get("estimated_actual_gross_profit"),
                errors="coerce",
            ).fillna(0.0)

        if _all_missing_or_blank(frame["capital_left_in_unsold_store_allocation"]):
            frame["capital_left_in_unsold_store_allocation"] = pd.to_numeric(
                frame.get("capital_left_unsold"),
                errors="coerce",
            ).fillna(0.0)

        if _all_missing_or_blank(frame["final_store_order_units"]):
            frame["final_store_order_units"] = pd.to_numeric(
                frame.get("store_adjusted_units", frame.get("provisional_review_order_units")),
                errors="coerce",
            ).fillna(0.0)

    frame["recommended_order_units"] = pd.to_numeric(
        frame.get("recommended_order_units"),
        errors="coerce",
    ).fillna(0.0)
    frame["order_units"] = pd.to_numeric(frame.get("order_units"), errors="coerce").fillna(0.0)
    frame["actual_units_sold"] = pd.to_numeric(
        frame.get("actual_units_sold"),
        errors="coerce",
    ).fillna(0.0)
    frame["expected_promo_demand"] = pd.to_numeric(
        frame.get("expected_promo_demand"),
        errors="coerce",
    ).fillna(0.0)
    frame["forecast_error_units"] = pd.to_numeric(
        frame.get("forecast_error_units"),
        errors="coerce",
    ).fillna(0.0)
    frame["actual_gross_profit"] = pd.to_numeric(
        frame.get("actual_gross_profit"),
        errors="coerce",
    ).fillna(0.0)
    frame["capital_left_in_unsold_store_allocation"] = pd.to_numeric(
        frame.get("capital_left_in_unsold_store_allocation"),
        errors="coerce",
    ).fillna(0.0)
    frame["final_store_order_units"] = pd.to_numeric(
        frame.get("final_store_order_units"),
        errors="coerce",
    ).fillna(0.0)
    frame["production_order_change_flag"] = pd.to_numeric(
        frame.get("production_order_change_flag"),
        errors="coerce",
    ).fillna(0).astype(int)
    frame["stage_12_change_flag"] = pd.to_numeric(
        frame.get("stage_12_change_flag"),
        errors="coerce",
    ).fillna(0).astype(int)

    for column_name in FLAG_COLUMNS:
        frame[column_name] = pd.to_numeric(frame.get(column_name), errors="coerce").fillna(0).astype(int)

    return frame


def _expand_unresolved_rule_flags(source_frame: pd.DataFrame) -> pd.DataFrame:
    expanded_rows: list[dict[str, object]] = []

    for row_number, row in enumerate(source_frame.to_dict(orient="records"), start=1):
        active_flags: list[str] = []
        if int(row.get("action_too_conservative_flag", 0) or 0) == 1:
            active_flags.append("ACTION_TOO_CONSERVATIVE")
        if int(row.get("review_should_have_triggered_flag", 0) or 0) == 1:
            active_flags.append("REVIEW_SHOULD_HAVE_TRIGGERED")
        if int(row.get("action_too_aggressive_flag", 0) or 0) == 1:
            active_flags.append("ACTION_TOO_AGGRESSIVE")
        for source_rule_flag in active_flags:
            expanded_row = dict(row)
            expanded_row["source_row_number"] = row_number
            expanded_row["source_rule_flag"] = source_rule_flag
            expanded_rows.append(expanded_row)

    if not expanded_rows:
        return pd.DataFrame(columns=[*source_frame.columns.tolist(), *INSPECTION_COLUMNS])

    return pd.DataFrame(expanded_rows)


def _demand_gap_units(row: pd.Series) -> float:
    return _as_float(row["actual_units_sold"]) - _as_float(row["expected_promo_demand"])


def _suppressed_action(row: pd.Series) -> bool:
    operator_decision = _normalize_text(row.get("operator_decision")).upper()
    operator_action = _normalize_text(row.get("operator_action")).upper()
    reason_short = _normalize_text(row.get("reason_short")).lower()
    recommended_order_units = _as_float(row.get("recommended_order_units"))
    if recommended_order_units > 0.0:
        return False
    if operator_decision in {"DO_NOT_BUY", "REVIEW", "HOLD"}:
        return True
    if operator_action in {"NO_ORDER", "MANUAL_REVIEW", "HOLD_STOCK"}:
        return True
    return "do not" in reason_short or "review" in reason_short


def _looks_like_reporting_or_text_issue(row: pd.Series) -> bool:
    source_rule_flag = _normalize_text(row.get("source_rule_flag")).upper()
    if source_rule_flag == "ACTION_TOO_AGGRESSIVE":
        return True

    operator_decision = _normalize_text(row.get("operator_decision")).upper()
    operator_action = _normalize_text(row.get("operator_action")).upper()
    reason_short = _normalize_text(row.get("reason_short")).lower()
    recommended_order_units = _as_float(row.get("recommended_order_units"))

    if recommended_order_units > 0.0 and (
        "review" in reason_short or "do not" in reason_short
    ):
        return True
    if operator_decision == "BUY" and operator_action.startswith("ORDER_") and "review" in reason_short:
        return True
    return False


def _commercial_priority(row: pd.Series) -> str:
    gross_profit = _as_float(row.get("actual_gross_profit"))
    actual_units = _as_float(row.get("actual_units_sold"))
    demand_gap = _demand_gap_units(row)

    score = 0
    if gross_profit >= HIGH_GROSS_PROFIT_THRESHOLD:
        score += 2
    elif gross_profit >= MEDIUM_GROSS_PROFIT_THRESHOLD:
        score += 1

    if actual_units >= HIGH_ACTUAL_UNITS_THRESHOLD:
        score += 2
    elif actual_units >= MEDIUM_ACTUAL_UNITS_THRESHOLD:
        score += 1

    if demand_gap >= HIGH_DEMAND_GAP_THRESHOLD:
        score += 2
    elif demand_gap >= MEDIUM_DEMAND_GAP_THRESHOLD:
        score += 1

    if score >= 4:
        return HIGH
    if score >= 2:
        return MEDIUM
    return LOW


def _inspection_bucket(row: pd.Series) -> str:
    actual_units = _as_float(row.get("actual_units_sold"))
    gross_profit = _as_float(row.get("actual_gross_profit"))
    capital_left = _as_float(row.get("capital_left_in_unsold_store_allocation"))
    demand_gap = _demand_gap_units(row)
    source_rule_flag = _normalize_text(row.get("source_rule_flag")).upper()

    if _looks_like_reporting_or_text_issue(row):
        return REPORTING_OR_TEXT_ISSUE

    if (
        source_rule_flag == "REVIEW_SHOULD_HAVE_TRIGGERED"
        and gross_profit <= WEAK_GROSS_PROFIT_THRESHOLD
        and actual_units <= MEDIUM_ACTUAL_UNITS_THRESHOLD
    ):
        return VALID_CONSERVATIVE_BLOCK

    if capital_left >= MEANINGFUL_CAPITAL_LEFT_THRESHOLD:
        return VALID_CONSERVATIVE_BLOCK

    if _suppressed_action(row) and (
        actual_units >= HIGH_ACTUAL_UNITS_THRESHOLD
        or demand_gap >= MEDIUM_DEMAND_GAP_THRESHOLD
        or gross_profit >= HIGH_GROSS_PROFIT_THRESHOLD
    ):
        return OVER_SUPPRESSION_CANDIDATE

    if source_rule_flag == "REVIEW_SHOULD_HAVE_TRIGGERED" and _suppressed_action(row) and (
        actual_units >= MEDIUM_ACTUAL_UNITS_THRESHOLD
        and demand_gap >= 3.0
        and gross_profit >= MEDIUM_GROSS_PROFIT_THRESHOLD
    ):
        return OVER_SUPPRESSION_CANDIDATE

    if (
        gross_profit <= WEAK_GROSS_PROFIT_THRESHOLD
        or actual_units <= 2.0
        or (capital_left >= 5.0 and gross_profit <= MEDIUM_GROSS_PROFIT_THRESHOLD)
    ):
        return VALID_CONSERVATIVE_BLOCK

    return NEEDS_MORE_EVIDENCE


def _inspection_reason(row: pd.Series) -> str:
    bucket = _normalize_text(row.get("action_layer_inspection_bucket"))
    source_rule_flag = _normalize_text(row.get("source_rule_flag"))
    actual_units = _as_float(row.get("actual_units_sold"))
    expected_demand = _as_float(row.get("expected_promo_demand"))
    demand_gap = _demand_gap_units(row)
    gross_profit = _as_float(row.get("actual_gross_profit"))
    capital_left = _as_float(row.get("capital_left_in_unsold_store_allocation"))
    reason_short = _normalize_text(row.get("reason_short"))

    if bucket == OVER_SUPPRESSION_CANDIDATE:
        return (
            f"{source_rule_flag} stayed suppressed even though actual units { _format_int(actual_units) } "
            f"beat expected demand { _format_int(expected_demand) } by { _format_int(demand_gap) } "
            f"with { _format_money(gross_profit) } gross profit."
        )

    if bucket == VALID_CONSERVATIVE_BLOCK:
        details: list[str] = []
        if gross_profit <= WEAK_GROSS_PROFIT_THRESHOLD:
            details.append(f"gross profit is only { _format_money(gross_profit) }")
        if capital_left >= 5.0:
            details.append(f"capital left remains { _format_money(capital_left) }")
        if actual_units <= 2.0:
            details.append(f"actual sales are still low at { _format_int(actual_units) } units")
        if not details:
            details.append("commercial upside is still limited")
        return f"{source_rule_flag} still looks commercially cautious because " + " and ".join(details) + "."

    if bucket == REPORTING_OR_TEXT_ISSUE:
        return (
            f"{source_rule_flag} looks more like a visible action or reason conflict than a clean missed-sales case; "
            f"reason text = {reason_short or 'blank'}."
        )

    return (
        f"{source_rule_flag} is inconclusive: actual units { _format_int(actual_units) }, expected demand "
        f"{ _format_int(expected_demand) }, gross profit { _format_money(gross_profit) }, capital left "
        f"{ _format_money(capital_left) }."
    )


def _recommended_next_action(row: pd.Series) -> str:
    bucket = _normalize_text(row.get("action_layer_inspection_bucket"))
    source_rule_flag = _normalize_text(row.get("source_rule_flag"))

    if bucket == OVER_SUPPRESSION_CANDIDATE:
        if source_rule_flag == "REVIEW_SHOULD_HAVE_TRIGGERED":
            return TEST_SHADOW_ONLY_REVIEW_TRIGGER
        return TEST_SHADOW_ONLY_ACTION_LAYER_RELAXATION
    if bucket == VALID_CONSERVATIVE_BLOCK:
        return KEEP_CONSERVATIVE_BLOCK_AND_GATHER_MORE_CASES
    if bucket == REPORTING_OR_TEXT_ISSUE:
        return FIX_REPORTING_TEXT_AND_ROUTING
    return COLLECT_MORE_EVIDENCE_BEFORE_RULE_CHANGE


def _overall_status(bucket_counts: dict[str, int]) -> str:
    total_rows = sum(bucket_counts.values())
    if total_rows == 0:
        return MIXED_REVIEW_DEBT

    over_suppression_rows = bucket_counts.get(OVER_SUPPRESSION_CANDIDATE, 0)
    valid_rows = bucket_counts.get(VALID_CONSERVATIVE_BLOCK, 0)

    if over_suppression_rows / float(total_rows) >= 0.60:
        return OVER_SUPPRESSION_DOMINANT
    if valid_rows / float(total_rows) >= 0.50 and valid_rows > over_suppression_rows:
        return CONSERVATIVE_BLOCKS_MOSTLY_VALID
    return MIXED_REVIEW_DEBT


def _overall_recommendation(bucket_counts: dict[str, int]) -> str:
    over_suppression_rows = bucket_counts.get(OVER_SUPPRESSION_CANDIDATE, 0)
    reporting_rows = bucket_counts.get(REPORTING_OR_TEXT_ISSUE, 0)
    valid_rows = bucket_counts.get(VALID_CONSERVATIVE_BLOCK, 0)

    if over_suppression_rows >= max(reporting_rows, valid_rows, 1):
        return SHADOW_ONLY_TARGETED_ACTION_LAYER_REVIEW
    if reporting_rows > 0:
        return FIX_REPORTING_AND_ROUTING_SHADOW_ONLY
    return GATHER_MORE_EVIDENCE_SHADOW_ONLY


def _build_rows_frame(action_layer_recalibration_rows_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        action_layer_recalibration_rows_frame,
        [*CORE_COLUMNS, *FLAG_COLUMNS],
        frame_name="action_layer_recalibration_rows_frame",
    )

    source_frame = _ensure_requested_columns(action_layer_recalibration_rows_frame)
    rows = _expand_unresolved_rule_flags(source_frame)

    if rows.empty:
        output_columns = list(dict.fromkeys([*source_frame.columns.tolist(), *INSPECTION_COLUMNS]))
        return pd.DataFrame(columns=output_columns)

    rows["action_layer_inspection_bucket"] = rows.apply(_inspection_bucket, axis=1)
    rows["over_suppression_candidate_flag"] = (
        rows["action_layer_inspection_bucket"].astype(str).eq(OVER_SUPPRESSION_CANDIDATE)
    ).astype(int)
    rows["valid_conservative_block_flag"] = (
        rows["action_layer_inspection_bucket"].astype(str).eq(VALID_CONSERVATIVE_BLOCK)
    ).astype(int)
    rows["reporting_or_text_issue_flag"] = (
        rows["action_layer_inspection_bucket"].astype(str).eq(REPORTING_OR_TEXT_ISSUE)
    ).astype(int)
    rows["needs_more_evidence_flag"] = (
        rows["action_layer_inspection_bucket"].astype(str).eq(NEEDS_MORE_EVIDENCE)
    ).astype(int)
    rows["commercial_priority"] = rows.apply(_commercial_priority, axis=1)
    rows["inspection_reason"] = rows.apply(_inspection_reason, axis=1)
    rows["recommended_next_action"] = rows.apply(_recommended_next_action, axis=1)

    priority_rank = {HIGH: 0, MEDIUM: 1, LOW: 2}
    bucket_rank = {
        OVER_SUPPRESSION_CANDIDATE: 0,
        VALID_CONSERVATIVE_BLOCK: 1,
        REPORTING_OR_TEXT_ISSUE: 2,
        NEEDS_MORE_EVIDENCE: 3,
    }
    rows["_priority_rank"] = rows["commercial_priority"].map(priority_rank).fillna(9)
    rows["_bucket_rank"] = rows["action_layer_inspection_bucket"].map(bucket_rank).fillna(9)
    rows = rows.sort_values(
        by=[
            "_priority_rank",
            "_bucket_rank",
            "actual_gross_profit",
            "actual_units_sold",
            "source_row_number",
            "source_rule_flag",
        ],
        ascending=[True, True, False, False, True, True],
        kind="stable",
    ).drop(columns=["_priority_rank", "_bucket_rank"])

    output_columns = list(
        dict.fromkeys([
            *action_layer_recalibration_rows_frame.columns.tolist(),
            *REQUESTED_COLUMNS,
            *INSPECTION_COLUMNS,
        ])
    )
    return rows.loc[:, output_columns].reset_index(drop=True)


def _expected_unresolved_count(action_layer_recalibration_summary_frame: pd.DataFrame | None) -> int:
    if action_layer_recalibration_summary_frame is None or action_layer_recalibration_summary_frame.empty:
        return 0
    _require_columns(
        action_layer_recalibration_summary_frame,
        ("summary_kind", "label_name", "row_count"),
        frame_name="action_layer_recalibration_summary_frame",
    )
    relevant_rows = action_layer_recalibration_summary_frame.loc[
        action_layer_recalibration_summary_frame["summary_kind"].astype(str).eq("RULE_FLAG")
        & action_layer_recalibration_summary_frame["label_name"].astype(str).isin(UNRESOLVED_FLAG_LABELS)
    ]
    if relevant_rows.empty:
        return 0
    return int(pd.to_numeric(relevant_rows["row_count"], errors="coerce").fillna(0).sum())


def _build_summary_frame(
    rows_frame: pd.DataFrame,
    *,
    expected_unresolved_rows: int,
) -> pd.DataFrame:
    bucket_counts = {
        bucket_name: int(rows_frame["action_layer_inspection_bucket"].astype(str).eq(bucket_name).sum())
        for bucket_name in (
            OVER_SUPPRESSION_CANDIDATE,
            VALID_CONSERVATIVE_BLOCK,
            REPORTING_OR_TEXT_ISSUE,
            NEEDS_MORE_EVIDENCE,
        )
    }
    total_rows = int(len(rows_frame.index))
    unique_source_rows = int(rows_frame["source_row_number"].nunique()) if total_rows > 0 else 0
    high_priority_rows = int(rows_frame["commercial_priority"].astype(str).eq(HIGH).sum()) if total_rows > 0 else 0
    unique_source_view = rows_frame.drop_duplicates(subset=["source_row_number"]) if total_rows > 0 else rows_frame
    gross_profit_total = float(pd.to_numeric(unique_source_view.get("actual_gross_profit"), errors="coerce").fillna(0.0).sum())
    capital_left_total = float(
        pd.to_numeric(
            unique_source_view.get("capital_left_in_unsold_store_allocation"),
            errors="coerce",
        ).fillna(0.0).sum()
    )

    dominant_bucket = NEEDS_MORE_EVIDENCE
    dominant_bucket_count = 0
    if bucket_counts:
        dominant_bucket, dominant_bucket_count = max(
            bucket_counts.items(),
            key=lambda item: (item[1], item[0]),
        )
    dominant_bucket_share = (
        dominant_bucket_count / float(total_rows)
        if total_rows > 0
        else 0.0
    )

    overall_status = _overall_status(bucket_counts)
    recommendation = _overall_recommendation(bucket_counts)

    rows: list[dict[str, object]] = [
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "ROWS_INSPECTED",
            total_rows,
            "rows",
            _format_int(total_rows),
            "Expanded unresolved rule-flag instances inspected in this diagnostics-only pass.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "UNIQUE_SOURCE_ROWS",
            unique_source_rows,
            "rows",
            _format_int(unique_source_rows),
            "Unique source rows represented underneath the unresolved rule-flag instances.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "EXPECTED_UNRESOLVED_RULE_FLAG_ROWS",
            expected_unresolved_rows,
            "rows",
            _format_int(expected_unresolved_rows),
            "Readiness-aligned unresolved rule-flag count from action_layer_recalibration_summary.csv.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "OVER_SUPPRESSION_CANDIDATE_ROWS",
            bucket_counts[OVER_SUPPRESSION_CANDIDATE],
            "rows",
            _format_int(bucket_counts[OVER_SUPPRESSION_CANDIDATE]),
            "Rows that look commercially strong enough to justify shadow-only action-layer review.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "VALID_CONSERVATIVE_BLOCK_ROWS",
            bucket_counts[VALID_CONSERVATIVE_BLOCK],
            "rows",
            _format_int(bucket_counts[VALID_CONSERVATIVE_BLOCK]),
            "Rows where conservative blocking still looks commercially defensible.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "REPORTING_OR_TEXT_ISSUE_ROWS",
            bucket_counts[REPORTING_OR_TEXT_ISSUE],
            "rows",
            _format_int(bucket_counts[REPORTING_OR_TEXT_ISSUE]),
            "Rows that appear to be routing or visible-text conflicts rather than clean commercial misses.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "NEEDS_MORE_EVIDENCE_ROWS",
            bucket_counts[NEEDS_MORE_EVIDENCE],
            "rows",
            _format_int(bucket_counts[NEEDS_MORE_EVIDENCE]),
            "Rows that are still inconclusive on current evidence.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "HIGH_PRIORITY_ROWS",
            high_priority_rows,
            "rows",
            _format_int(high_priority_rows),
            "Rows ranked HIGH on commercial priority using actual units, demand gap, and gross profit.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "UNIQUE_GROSS_PROFIT_REPRESENTED",
            gross_profit_total,
            "dollars",
            _format_money(gross_profit_total),
            "Gross profit represented by the unique source rows behind the unresolved inspection slice.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "UNIQUE_CAPITAL_LEFT_REPRESENTED",
            capital_left_total,
            "dollars",
            _format_money(capital_left_total),
            "Capital left represented by the unique source rows behind the unresolved inspection slice.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "DOMINANT_BUCKET",
            dominant_bucket,
            "label",
            dominant_bucket,
            "Most common inspection bucket across the unresolved rule-flag instances.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "DOMINANT_BUCKET_SHARE",
            dominant_bucket_share,
            "share",
            _format_share(dominant_bucket_share),
            "Share of unresolved rule-flag instances covered by the dominant bucket.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "OVERALL_INSPECTION_STATUS",
            overall_status,
            "label",
            overall_status,
            "High-level diagnostic view of whether the unresolved action-layer debt looks like over-suppression or mixed review debt.",
        ),
        _summary_row(
            "ACTION_LAYER_UNRESOLVED_INSPECTION",
            "RECOMMENDATION",
            recommendation,
            "label",
            recommendation,
            "Governed next step for this action-layer unresolved inspection pack.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            int(pd.to_numeric(rows_frame.get("production_order_change_flag"), errors="coerce").fillna(0).sum()) if total_rows > 0 else 0,
            "rows",
            _format_int(
                int(pd.to_numeric(rows_frame.get("production_order_change_flag"), errors="coerce").fillna(0).sum()) if total_rows > 0 else 0
            ),
            "This diagnostics pass does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            int(pd.to_numeric(rows_frame.get("stage_12_change_flag"), errors="coerce").fillna(0).sum()) if total_rows > 0 else 0,
            "rows",
            _format_int(
                int(pd.to_numeric(rows_frame.get("stage_12_change_flag"), errors="coerce").fillna(0).sum()) if total_rows > 0 else 0
            ),
            "This diagnostics pass does not change Stage 12.",
        ),
    ]

    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_by_bucket_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=BY_BUCKET_COLUMNS)

    records: list[dict[str, object]] = []
    total_rows = float(len(rows_frame.index))

    for bucket_name, group in rows_frame.groupby("action_layer_inspection_bucket", sort=False, dropna=False):
        unique_group = group.drop_duplicates(subset=["source_row_number"])
        records.append(
            {
                "action_layer_inspection_bucket": str(bucket_name),
                "row_count": int(len(group.index)),
                "unique_source_rows": int(len(unique_group.index)),
                "share_of_rows": float(len(group.index)) / total_rows,
                "high_priority_rows": int(group["commercial_priority"].astype(str).eq(HIGH).sum()),
                "source_rule_flags": _sample_values(group["source_rule_flag"]),
                "departments_covered": _sample_values(unique_group["department"]),
                "actual_units_total": float(pd.to_numeric(unique_group["actual_units_sold"], errors="coerce").fillna(0.0).sum()),
                "forecast_error_units_total": float(pd.to_numeric(unique_group["forecast_error_units"], errors="coerce").fillna(0.0).sum()),
                "gross_profit_total": float(pd.to_numeric(unique_group["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
                "capital_left_total": float(pd.to_numeric(unique_group["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0).sum()),
                "sample_skus": _sample_values(unique_group["sku_number"]),
            }
        )

    by_bucket_frame = pd.DataFrame(records, columns=BY_BUCKET_COLUMNS)
    return by_bucket_frame.sort_values(
        by=["row_count", "high_priority_rows", "action_layer_inspection_bucket"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _overall_status_sentence(overall_status: str) -> str:
    if overall_status == OVER_SUPPRESSION_DOMINANT:
        return (
            "Most of the unresolved action-layer debt looks like true over-suppression, but any relaxation still needs shadow-only testing."
        )
    if overall_status == CONSERVATIVE_BLOCKS_MOSTLY_VALID:
        return (
            "Most unresolved action-layer debt still looks like commercially valid conservative blocking rather than a clean missed-demand issue."
        )
    return (
        "The unresolved action-layer debt looks mixed: some rows resemble true over-suppression, while others still look like cautious review debt or routing noise."
    )


def _top_high_priority_rows(rows_frame: pd.DataFrame, *, limit: int = 5) -> pd.DataFrame:
    if rows_frame.empty:
        return rows_frame
    unique_high_priority = rows_frame.loc[
        rows_frame["commercial_priority"].astype(str).eq(HIGH)
    ].drop_duplicates(subset=["source_row_number"])
    if unique_high_priority.empty:
        unique_high_priority = rows_frame.drop_duplicates(subset=["source_row_number"]).head(limit)
    return unique_high_priority.head(limit)


def _build_memo(
    *,
    rows_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    by_bucket_frame: pd.DataFrame,
    pretrain_readiness_summary_frame: pd.DataFrame | None,
    batch1_shadow_candidate_summary_frame: pd.DataFrame | None,
) -> str:
    summary_lookup = _metric_lookup(summary_frame)
    batch1_lookup = _metric_lookup(batch1_shadow_candidate_summary_frame)

    rows_inspected = int(_as_float(summary_lookup.get("ROWS_INSPECTED", 0)))
    unique_source_rows = int(_as_float(summary_lookup.get("UNIQUE_SOURCE_ROWS", 0)))
    over_suppression_rows = int(_as_float(summary_lookup.get("OVER_SUPPRESSION_CANDIDATE_ROWS", 0)))
    valid_rows = int(_as_float(summary_lookup.get("VALID_CONSERVATIVE_BLOCK_ROWS", 0)))
    reporting_rows = int(_as_float(summary_lookup.get("REPORTING_OR_TEXT_ISSUE_ROWS", 0)))
    needs_more_evidence_rows = int(_as_float(summary_lookup.get("NEEDS_MORE_EVIDENCE_ROWS", 0)))
    high_priority_rows = int(_as_float(summary_lookup.get("HIGH_PRIORITY_ROWS", 0)))
    overall_status = _normalize_text(summary_lookup.get("OVERALL_INSPECTION_STATUS"))
    recommendation = _normalize_text(summary_lookup.get("RECOMMENDATION"))

    forecast_reason = _readiness_reason(
        pretrain_readiness_summary_frame,
        "forecast_head_reliability",
    )
    action_layer_reason = _readiness_reason(
        pretrain_readiness_summary_frame,
        "action_layer_calibration_ready",
    )
    batch1_status = _normalize_text(batch1_lookup.get("OVERALL_INSPECTION_STATUS"))
    batch1_recommendation = _normalize_text(batch1_lookup.get("RECOMMENDATION"))

    high_priority_lines = []
    for row in _top_high_priority_rows(rows_frame).itertuples(index=False):
        high_priority_lines.append(
            f"- SKU {getattr(row, 'sku_number')}: {getattr(row, 'sku_description')} | "
            f"bucket={getattr(row, 'action_layer_inspection_bucket')} | "
            f"gross_profit={_format_money(_as_float(getattr(row, 'actual_gross_profit')))} | "
            f"next_action={getattr(row, 'recommended_next_action')}"
        )
    if not high_priority_lines:
        high_priority_lines.append("- No high-priority rows were present in this slice.")

    by_bucket_lines = []
    for row in by_bucket_frame.itertuples(index=False):
        by_bucket_lines.append(
            f"- {getattr(row, 'action_layer_inspection_bucket')}: {getattr(row, 'row_count')} rule-flag rows "
            f"across {getattr(row, 'unique_source_rows')} unique source rows; high_priority={getattr(row, 'high_priority_rows')}; "
            f"source_flags={getattr(row, 'source_rule_flags')}"
        )
    if not by_bucket_lines:
        by_bucket_lines.append("- No unresolved rule-flag rows were available to group.")

    return "\n".join(
        [
            "# Governed Action-Layer Unresolved Inspection",
            "",
            "This is not an order file.",
            "No training was started.",
            "Production order changes = 0.",
            "Stage 12 changes = 0.",
            "",
            "## 1. Executive conclusion",
            _overall_status_sentence(overall_status),
            f"The pass inspected {rows_inspected} unresolved rule-flag rows backed by {unique_source_rows} unique source rows.",
            f"Recommendation: {recommendation}.",
            "",
            "## 2. Bucket view",
            *by_bucket_lines,
            "",
            "## 3. What the unresolved debt looks like",
            (
                f"Over-suppression candidates = {over_suppression_rows}; valid conservative blocks = {valid_rows}; "
                f"reporting or text issues = {reporting_rows}; needs more evidence = {needs_more_evidence_rows}."
            ),
            "The rows that look like genuine rule misses should remain shadow-only until tested across more promotions.",
            "",
            "## 4. High-priority rows",
            f"High-priority rows = {high_priority_rows}.",
            *high_priority_lines,
            "",
            "## 5. Readiness connection",
            (forecast_reason or "Forecast-head reliability still remains an independent blocker for training readiness."),
            (action_layer_reason or "Action-layer calibration still remains an open blocker for training readiness."),
            (
                f"Batch 1 shadow candidate status remains {batch1_status or 'unknown'} with recommendation "
                f"{batch1_recommendation or 'unknown'}."
            ),
            "Improving this action-layer review debt is about cleaner shadow-only diagnostics first, not direct auto-ordering promotion.",
            "Auto-ordering readiness still depends on both better forecast reliability and repeated safe shadow evidence on the action layer.",
        ]
    )


def build_promotions_action_layer_unresolved_inspection(
    *,
    action_layer_recalibration_rows_frame: pd.DataFrame,
    action_layer_recalibration_summary_frame: pd.DataFrame | None = None,
    pretrain_readiness_summary_frame: pd.DataFrame | None = None,
    batch1_shadow_candidate_summary_frame: pd.DataFrame | None = None,
) -> PromotionsActionLayerUnresolvedInspectionResult:
    rows_frame = _build_rows_frame(action_layer_recalibration_rows_frame)

    expected_unresolved_rows = _expected_unresolved_count(action_layer_recalibration_summary_frame)
    if expected_unresolved_rows > 0 and expected_unresolved_rows != int(len(rows_frame.index)):
        raise PromotionsActionLayerUnresolvedInspectionError(
            "Expanded unresolved rule-flag rows do not match the readiness-aligned summary count: "
            f"expected {expected_unresolved_rows}, found {len(rows_frame.index)}."
        )

    summary_frame = _build_summary_frame(
        rows_frame,
        expected_unresolved_rows=expected_unresolved_rows or int(len(rows_frame.index)),
    )
    by_bucket_frame = _build_by_bucket_frame(rows_frame)
    memo_markdown = _build_memo(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_bucket_frame=by_bucket_frame,
        pretrain_readiness_summary_frame=pretrain_readiness_summary_frame,
        batch1_shadow_candidate_summary_frame=batch1_shadow_candidate_summary_frame,
    )

    return PromotionsActionLayerUnresolvedInspectionResult(
        rows_frame=rows_frame,
        summary_frame=summary_frame,
        by_bucket_frame=by_bucket_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_action_layer_unresolved_inspection(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsActionLayerUnresolvedInspectionArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsActionLayerUnresolvedInspectionError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_action_layer_unresolved_inspection(
        action_layer_recalibration_rows_frame=_read_csv(
            review_artifact_path / INPUT_ROWS_RELATIVE_PATH,
            allow_empty=True,
            empty_columns=[*CORE_COLUMNS, *FLAG_COLUMNS],
        ),
        action_layer_recalibration_summary_frame=_read_csv(
            review_artifact_path / INPUT_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
        pretrain_readiness_summary_frame=_read_csv(
            review_artifact_path / READINESS_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
        batch1_shadow_candidate_summary_frame=_read_csv(
            review_artifact_path / BATCH1_SHADOW_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
    )

    destination_root = (
        Path(output_root)
        if output_root is not None
        else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "action_layer_unresolved_inspection_rows.csv"
    summary_csv_path = destination_root / "action_layer_unresolved_inspection_summary.csv"
    by_bucket_csv_path = destination_root / "action_layer_unresolved_inspection_by_bucket.csv"
    memo_md_path = destination_root / "action_layer_unresolved_inspection_memo.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    add_provenance_columns(result.by_bucket_frame.copy(), manifest).to_csv(
        by_bucket_csv_path,
        index=False,
    )
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsActionLayerUnresolvedInspectionArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        by_bucket_csv_path=str(by_bucket_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a governed diagnostics-only inspection pass for unresolved action-layer rule flags "
            "without starting training or changing production logic."
        )
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_action_layer_unresolved_inspection(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("action_layer_unresolved_inspection_rows", artifacts.rows_csv_path)
    print("action_layer_unresolved_inspection_summary", artifacts.summary_csv_path)
    print("action_layer_unresolved_inspection_by_bucket", artifacts.by_bucket_csv_path)
    print("action_layer_unresolved_inspection_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())