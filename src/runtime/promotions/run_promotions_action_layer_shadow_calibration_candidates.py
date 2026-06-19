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


OUTPUT_FOLDER_NAME = "action_layer_shadow_calibration_candidates"
INPUT_ROWS_RELATIVE_PATH = Path(
    "action_layer_unresolved_inspection/action_layer_unresolved_inspection_rows.csv"
)
INPUT_SUMMARY_RELATIVE_PATH = Path(
    "action_layer_unresolved_inspection/action_layer_unresolved_inspection_summary.csv"
)
INPUT_BY_BUCKET_RELATIVE_PATH = Path(
    "action_layer_unresolved_inspection/action_layer_unresolved_inspection_by_bucket.csv"
)
READINESS_SUMMARY_RELATIVE_PATH = Path(
    "pretrain_readiness_inspection/pretrain_readiness_summary.csv"
)

REQUIRED_REVIEW_ARTIFACTS: tuple[str, ...] = (
    "input_source_manifest.json",
    str(INPUT_ROWS_RELATIVE_PATH),
    str(INPUT_SUMMARY_RELATIVE_PATH),
    str(INPUT_BY_BUCKET_RELATIVE_PATH),
    str(READINESS_SUMMARY_RELATIVE_PATH),
)

CORE_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "action_layer_inspection_bucket",
)

PRESERVED_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "department",
    "source_rule_flag",
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
    "commercial_priority",
    "inspection_reason",
    "recommended_next_action",
    "production_order_change_flag",
    "stage_12_change_flag",
    "source_row_number",
)

ROW_OUTPUT_COLUMNS: tuple[str, ...] = (
    "shadow_calibration_rule_candidate",
    "shadow_rule_family",
    "shadow_rule_strength",
    "shadow_rule_risk_level",
    "shadow_rule_test_status",
    "shadow_rule_reason",
    "recommended_shadow_test_action",
)

RULES_COLUMNS: tuple[str, ...] = (
    "shadow_calibration_rule_candidate",
    "shadow_rule_family",
    "row_count",
    "unique_skus",
    "share_of_rows",
    "high_priority_candidate_rows",
    "source_rule_flags",
    "departments_covered",
    "description_patterns",
    "average_actual_units_sold",
    "average_forecast_error_units",
    "gross_profit_total",
    "capital_left_total",
    "strength_distribution",
    "risk_distribution",
    "sample_skus",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_group",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_display",
    "notes",
)

OVER_SUPPRESSION_CANDIDATE = "OVER_SUPPRESSION_CANDIDATE"

HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER = "HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER"
FORECAST_BLINDSPOT_REVIEW_TRIGGER = "FORECAST_BLINDSPOT_REVIEW_TRIGGER"
ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW = (
    "ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW"
)
HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW = "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW"
CATEGORY_OR_BRAND_PATTERN_REVIEW = "CATEGORY_OR_BRAND_PATTERN_REVIEW"

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

SHADOW_ONLY_NOT_PRODUCTION = "SHADOW_ONLY_NOT_PRODUCTION"

TEST_IN_SHADOW_ACROSS_MORE_PROMOTIONS = "TEST_IN_SHADOW_ACROSS_MORE_PROMOTIONS"
KEEP_AS_REVIEW_TRIGGER_ONLY = "KEEP_AS_REVIEW_TRIGGER_ONLY"
DO_NOT_PROMOTE_TO_AUTO_ORDER = "DO_NOT_PROMOTE_TO_AUTO_ORDER"
REQUIRE_MORE_EVIDENCE = "REQUIRE_MORE_EVIDENCE"

FINAL_RECOMMENDATION = "TEST_IN_SHADOW_ACROSS_MORE_PROMOTIONS"

HIGH_GROSS_PROFIT_THRESHOLD = 40.0
MEDIUM_GROSS_PROFIT_THRESHOLD = 20.0
HIGH_ACTUAL_UNITS_THRESHOLD = 9.0
MEDIUM_ACTUAL_UNITS_THRESHOLD = 5.0
HIGH_FORECAST_ERROR_THRESHOLD = 8.0
MEDIUM_FORECAST_ERROR_THRESHOLD = 5.0
LOW_CAPITAL_LEFT_THRESHOLD = 1.0
PATTERN_DEPARTMENT_MIN_ROWS = 4
PATTERN_PREFIX_MIN_ROWS = 3


class PromotionsActionLayerShadowCalibrationCandidatesError(RuntimeError):
    """Raised when the shadow-only action-layer candidate pack cannot run safely."""


@dataclass(frozen=True)
class PromotionsActionLayerShadowCalibrationCandidatesResult:
    rows_frame: pd.DataFrame
    rules_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsActionLayerShadowCalibrationCandidatesArtifacts:
    rows_csv_path: str
    rules_csv_path: str
    summary_csv_path: str
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
        raise PromotionsActionLayerShadowCalibrationCandidatesError(f"CSV is empty: {path}")
    if frame.empty and not allow_empty:
        raise PromotionsActionLayerShadowCalibrationCandidatesError(f"CSV is empty: {path}")
    if frame.empty and empty_columns is not None:
        for column_name in empty_columns:
            if column_name not in frame.columns:
                frame[column_name] = pd.Series(dtype="object")
        frame = frame.loc[:, list(dict.fromkeys([*frame.columns.tolist(), *empty_columns]))]
    return frame


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionsActionLayerShadowCalibrationCandidatesError(
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
        raise PromotionsActionLayerShadowCalibrationCandidatesError(
            "Review artifact root is missing required files: " + ", ".join(sorted(missing))
        )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str) -> None:
    missing = [column_name for column_name in columns if column_name not in frame.columns]
    if missing:
        raise PromotionsActionLayerShadowCalibrationCandidatesError(
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


def _all_missing_or_blank(values: pd.Series) -> bool:
    normalized = values.fillna("").astype(str).str.strip()
    return normalized.eq("").all()


def _distribution_text(values: pd.Series) -> str:
    counts = values.astype(str).value_counts(dropna=False)
    parts = [f"{label}={int(count)}" for label, count in counts.items()]
    return ", ".join(parts)


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


def _description_prefix(value: object) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    first_token = re.split(r"\s+", text, maxsplit=1)[0]
    return re.sub(r"[^A-Za-z0-9]+", "", first_token).upper()


def _ensure_columns(source_frame: pd.DataFrame) -> pd.DataFrame:
    frame = source_frame.copy()

    for column_name in PRESERVED_COLUMNS:
        if column_name not in frame.columns:
            frame[column_name] = pd.Series(dtype="object")

    if not frame.empty:
        if _all_missing_or_blank(frame["order_units"]):
            frame["order_units"] = pd.to_numeric(
                frame.get("recommended_order_units"),
                errors="coerce",
            ).fillna(0.0)
        if _all_missing_or_blank(frame["final_store_order_units"]):
            frame["final_store_order_units"] = pd.to_numeric(
                frame.get("recommended_order_units"),
                errors="coerce",
            ).fillna(0.0)
        if _all_missing_or_blank(frame["commercial_priority"]):
            frame["commercial_priority"] = LOW
        if _all_missing_or_blank(frame["inspection_reason"]):
            frame["inspection_reason"] = ""
        if _all_missing_or_blank(frame["recommended_next_action"]):
            frame["recommended_next_action"] = ""
        if _all_missing_or_blank(frame["source_row_number"]):
            frame["source_row_number"] = range(1, len(frame.index) + 1)

    numeric_columns = (
        "order_units",
        "actual_units_sold",
        "expected_promo_demand",
        "forecast_error_units",
        "actual_gross_profit",
        "capital_left_in_unsold_store_allocation",
        "recommended_order_units",
        "final_store_order_units",
    )
    for column_name in numeric_columns:
        frame[column_name] = pd.to_numeric(frame.get(column_name), errors="coerce").fillna(0.0)

    frame["production_order_change_flag"] = pd.to_numeric(
        frame.get("production_order_change_flag"),
        errors="coerce",
    ).fillna(0).astype(int)
    frame["stage_12_change_flag"] = pd.to_numeric(
        frame.get("stage_12_change_flag"),
        errors="coerce",
    ).fillna(0).astype(int)
    frame["source_row_number"] = pd.to_numeric(
        frame.get("source_row_number"),
        errors="coerce",
    ).fillna(0).astype(int)
    frame["commercial_priority"] = frame["commercial_priority"].astype(str).replace({"": LOW})
    frame["description_prefix"] = frame["sku_description"].map(_description_prefix)

    return frame


def _expected_over_suppression_count(summary_frame: pd.DataFrame | None) -> int:
    if summary_frame is None or summary_frame.empty:
        return 0
    _require_columns(
        summary_frame,
        ("metric_name", "metric_value"),
        frame_name="action_layer_unresolved_inspection_summary_frame",
    )
    matched = summary_frame.loc[
        summary_frame["metric_name"].astype(str).eq("OVER_SUPPRESSION_CANDIDATE_ROWS")
    ]
    if matched.empty:
        return 0
    return int(pd.to_numeric(matched.iloc[0]["metric_value"], errors="coerce"))


def _filter_candidate_rows(source_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(source_frame, CORE_COLUMNS, frame_name="action_layer_unresolved_inspection_rows_frame")
    frame = _ensure_columns(source_frame)
    filtered = frame.loc[
        frame["action_layer_inspection_bucket"].astype(str).eq(OVER_SUPPRESSION_CANDIDATE)
        & frame["production_order_change_flag"].eq(0)
        & frame["stage_12_change_flag"].eq(0)
    ].copy()
    return filtered.reset_index(drop=True)


def _signal_count(row: pd.Series) -> int:
    count = 0
    if _as_float(row["actual_gross_profit"]) > 0.0:
        count += 1
    if _as_float(row["actual_units_sold"]) > 0.0:
        count += 1
    if _as_float(row["forecast_error_units"]) >= MEDIUM_FORECAST_ERROR_THRESHOLD:
        count += 1
    if _as_float(row["capital_left_in_unsold_store_allocation"]) <= LOW_CAPITAL_LEFT_THRESHOLD:
        count += 1
    if _normalize_text(row["commercial_priority"]).upper() == HIGH:
        count += 1
    return count


def _shadow_rule_strength(row: pd.Series) -> str:
    signals = _signal_count(row)
    if signals >= 4:
        return HIGH
    if signals >= 2:
        return MEDIUM
    return LOW


def _shadow_rule_risk_level(row: pd.Series, strength: str) -> str:
    capital_left = _as_float(row["capital_left_in_unsold_store_allocation"])
    gross_profit = _as_float(row["actual_gross_profit"])
    if capital_left > 5.0 or strength == LOW:
        return HIGH
    if capital_left <= LOW_CAPITAL_LEFT_THRESHOLD and gross_profit > 0.0:
        return LOW
    return MEDIUM


def _family_reason(
    family: str,
    *,
    row: pd.Series,
    department_count: int,
    prefix_count: int,
) -> str:
    actual_units = _format_int(_as_float(row["actual_units_sold"]))
    expected_units = _format_int(_as_float(row["expected_promo_demand"]))
    forecast_error = _format_int(_as_float(row["forecast_error_units"]))
    gross_profit = _format_money(_as_float(row["actual_gross_profit"]))
    capital_left = _format_money(_as_float(row["capital_left_in_unsold_store_allocation"]))
    priority = _normalize_text(row["commercial_priority"]).upper() or LOW
    if family == HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW:
        return (
            f"Commercial priority is {priority} with {gross_profit} gross profit and {actual_units} sold units, so this row is a strong shadow-only review trigger candidate."
        )
    if family == FORECAST_BLINDSPOT_REVIEW_TRIGGER:
        return (
            f"Forecast error is +{forecast_error} units against {expected_units} expected units, indicating a likely forecast blindspot that should be tested as a shadow review trigger."
        )
    if family == HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER:
        return (
            f"Gross profit {gross_profit} and positive sold units {actual_units} suggest commercially valid demand that was suppressed too aggressively."
        )
    if family == CATEGORY_OR_BRAND_PATTERN_REVIEW:
        return (
            f"This row sits inside a repeated department/pattern cluster ({department_count} department rows; {prefix_count} matching description-prefix rows), making it a candidate category-style shadow rule."
        )
    return (
        f"Capital left is only {capital_left}, so the suppression did not appear to protect working capital on this slice and is suitable for shadow-only review testing."
    )


def _recommended_shadow_test_action(family: str, strength: str) -> str:
    if strength == LOW:
        return REQUIRE_MORE_EVIDENCE
    if family in {
        HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW,
        FORECAST_BLINDSPOT_REVIEW_TRIGGER,
        HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER,
    }:
        return TEST_IN_SHADOW_ACROSS_MORE_PROMOTIONS
    if family == CATEGORY_OR_BRAND_PATTERN_REVIEW:
        return KEEP_AS_REVIEW_TRIGGER_ONLY
    return DO_NOT_PROMOTE_TO_AUTO_ORDER


def _assign_row_candidates(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=[*rows_frame.columns.tolist(), *ROW_OUTPUT_COLUMNS])

    rows = rows_frame.copy()
    department_counts = rows["department"].astype(str).value_counts(dropna=False).to_dict()
    prefix_counts = rows["description_prefix"].astype(str).value_counts(dropna=False).to_dict()

    family_values: list[str] = []
    candidate_values: list[str] = []
    strength_values: list[str] = []
    risk_values: list[str] = []
    reason_values: list[str] = []
    action_values: list[str] = []

    for row in rows.itertuples(index=False):
        row_series = pd.Series(row._asdict())
        department = _normalize_text(getattr(row, "department"))
        prefix = _normalize_text(getattr(row, "description_prefix"))
        source_rule_flag = _normalize_text(getattr(row, "source_rule_flag"))
        department_count = int(department_counts.get(department, 0))
        prefix_count = int(prefix_counts.get(prefix, 0))
        gross_profit = _as_float(getattr(row, "actual_gross_profit"))
        actual_units = _as_float(getattr(row, "actual_units_sold"))
        forecast_error = _as_float(getattr(row, "forecast_error_units"))
        capital_left = _as_float(getattr(row, "capital_left_in_unsold_store_allocation"))
        priority = _normalize_text(getattr(row, "commercial_priority")).upper()

        pattern_candidate = (
            department_count >= PATTERN_DEPARTMENT_MIN_ROWS
            or prefix_count >= PATTERN_PREFIX_MIN_ROWS
        )

        if priority == HIGH:
            family = HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW
        elif source_rule_flag == "REVIEW_SHOULD_HAVE_TRIGGERED" or forecast_error >= HIGH_FORECAST_ERROR_THRESHOLD:
            family = FORECAST_BLINDSPOT_REVIEW_TRIGGER
        elif gross_profit >= MEDIUM_GROSS_PROFIT_THRESHOLD and actual_units >= MEDIUM_ACTUAL_UNITS_THRESHOLD:
            family = HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER
        elif pattern_candidate:
            family = CATEGORY_OR_BRAND_PATTERN_REVIEW
        elif capital_left <= LOW_CAPITAL_LEFT_THRESHOLD:
            family = ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW
        else:
            family = HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER

        if family == CATEGORY_OR_BRAND_PATTERN_REVIEW:
            candidate_name = (
                f"{family}__{re.sub(r'[^A-Z0-9]+', '_', department.upper()).strip('_') or 'UNKNOWN'}"
            )
        elif family == HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER:
            candidate_name = (
                f"{family}__{re.sub(r'[^A-Z0-9]+', '_', department.upper()).strip('_') or 'UNKNOWN'}"
            )
        else:
            candidate_name = f"{family}__{source_rule_flag or 'UNSPECIFIED'}"

        strength = _shadow_rule_strength(row_series)
        risk_level = _shadow_rule_risk_level(row_series, strength)
        rule_reason = _family_reason(
            family,
            row=row_series,
            department_count=department_count,
            prefix_count=prefix_count,
        )
        test_action = _recommended_shadow_test_action(family, strength)

        family_values.append(family)
        candidate_values.append(candidate_name)
        strength_values.append(strength)
        risk_values.append(risk_level)
        reason_values.append(rule_reason)
        action_values.append(test_action)

    rows["shadow_rule_family"] = family_values
    rows["shadow_calibration_rule_candidate"] = candidate_values
    rows["shadow_rule_strength"] = strength_values
    rows["shadow_rule_risk_level"] = risk_values
    rows["shadow_rule_test_status"] = SHADOW_ONLY_NOT_PRODUCTION
    rows["shadow_rule_reason"] = reason_values
    rows["recommended_shadow_test_action"] = action_values

    priority_rank = {HIGH: 0, MEDIUM: 1, LOW: 2}
    strength_rank = {HIGH: 0, MEDIUM: 1, LOW: 2}
    rows["_priority_rank"] = rows["commercial_priority"].astype(str).map(priority_rank).fillna(9)
    rows["_strength_rank"] = rows["shadow_rule_strength"].astype(str).map(strength_rank).fillna(9)
    rows = rows.sort_values(
        by=[
            "_priority_rank",
            "_strength_rank",
            "actual_gross_profit",
            "actual_units_sold",
            "shadow_rule_family",
            "sku_number",
        ],
        ascending=[True, True, False, False, True, True],
        kind="stable",
    ).drop(columns=["_priority_rank", "_strength_rank"])

    output_columns = list(dict.fromkeys([*PRESERVED_COLUMNS, *ROW_OUTPUT_COLUMNS]))
    return rows.loc[:, output_columns].reset_index(drop=True)


def _build_rules_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    if rows_frame.empty:
        return pd.DataFrame(columns=RULES_COLUMNS)

    records: list[dict[str, object]] = []
    total_rows = float(len(rows_frame.index))

    for candidate_name, group in rows_frame.groupby("shadow_calibration_rule_candidate", sort=False, dropna=False):
        family = _normalize_text(group["shadow_rule_family"].iloc[0])
        strength_distribution = _distribution_text(group["shadow_rule_strength"])
        risk_distribution = _distribution_text(group["shadow_rule_risk_level"])
        records.append(
            {
                "shadow_calibration_rule_candidate": str(candidate_name),
                "shadow_rule_family": family,
                "row_count": int(len(group.index)),
                "unique_skus": int(group["sku_number"].astype(str).nunique()),
                "share_of_rows": float(len(group.index)) / total_rows,
                "high_priority_candidate_rows": int(group["commercial_priority"].astype(str).eq(HIGH).sum()),
                "source_rule_flags": _sample_values(group["source_rule_flag"]),
                "departments_covered": _sample_values(group["department"]),
                "description_patterns": _sample_values(group["sku_description"].map(_description_prefix)),
                "average_actual_units_sold": float(pd.to_numeric(group["actual_units_sold"], errors="coerce").fillna(0.0).mean()),
                "average_forecast_error_units": float(pd.to_numeric(group["forecast_error_units"], errors="coerce").fillna(0.0).mean()),
                "gross_profit_total": float(pd.to_numeric(group["actual_gross_profit"], errors="coerce").fillna(0.0).sum()),
                "capital_left_total": float(pd.to_numeric(group["capital_left_in_unsold_store_allocation"], errors="coerce").fillna(0.0).sum()),
                "strength_distribution": strength_distribution,
                "risk_distribution": risk_distribution,
                "sample_skus": _sample_values(group["sku_number"]),
            }
        )

    rules_frame = pd.DataFrame(records, columns=RULES_COLUMNS)
    return rules_frame.sort_values(
        by=["row_count", "high_priority_candidate_rows", "shadow_calibration_rule_candidate"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)


def _build_summary_frame(
    rows_frame: pd.DataFrame,
    *,
    input_rows: int,
) -> pd.DataFrame:
    candidate_rows = int(len(rows_frame.index))
    unique_skus = int(rows_frame["sku_number"].astype(str).nunique()) if candidate_rows > 0 else 0
    high_priority_rows = int(rows_frame["commercial_priority"].astype(str).eq(HIGH).sum()) if candidate_rows > 0 else 0
    family_counts = rows_frame["shadow_rule_family"].astype(str).value_counts(dropna=False) if candidate_rows > 0 else pd.Series(dtype="int64")
    family_count = int(len(family_counts.index))
    dominant_family = str(family_counts.index[0]) if not family_counts.empty else ""
    dominant_family_rows = int(family_counts.iloc[0]) if not family_counts.empty else 0
    dominant_family_share = dominant_family_rows / float(candidate_rows) if candidate_rows > 0 else 0.0

    unique_view = rows_frame.drop_duplicates(subset=["source_row_number"]) if candidate_rows > 0 else rows_frame
    gross_profit_total = float(pd.to_numeric(unique_view.get("actual_gross_profit"), errors="coerce").fillna(0.0).sum())
    capital_left_total = float(
        pd.to_numeric(
            unique_view.get("capital_left_in_unsold_store_allocation"),
            errors="coerce",
        ).fillna(0.0).sum()
    )
    production_changes = int(pd.to_numeric(rows_frame.get("production_order_change_flag"), errors="coerce").fillna(0).sum()) if candidate_rows > 0 else 0
    stage12_changes = int(pd.to_numeric(rows_frame.get("stage_12_change_flag"), errors="coerce").fillna(0).sum()) if candidate_rows > 0 else 0

    rows = [
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "INPUT_ROWS",
            input_rows,
            "rows",
            _format_int(input_rows),
            "Rows available in the unresolved inspection input before filtering to over-suppression candidates.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "OVER_SUPPRESSION_CANDIDATE_ROWS_SELECTED",
            candidate_rows,
            "rows",
            _format_int(candidate_rows),
            "Rows selected into the shadow calibration candidate pack after keeping only over-suppression rows with zero production and Stage 12 changes.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "UNIQUE_SKUS",
            unique_skus,
            "rows",
            _format_int(unique_skus),
            "Unique SKUs represented in the shadow calibration candidate pack.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "HIGH_PRIORITY_CANDIDATE_ROWS",
            high_priority_rows,
            "rows",
            _format_int(high_priority_rows),
            "Candidate rows already marked HIGH on commercial priority.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "CANDIDATE_RULE_FAMILIES_COUNT",
            family_count,
            "families",
            _format_int(family_count),
            "Distinct shadow rule families represented in the candidate pack.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "DOMINANT_RULE_FAMILY",
            dominant_family,
            "label",
            dominant_family,
            "Most common shadow calibration rule family in the candidate pack.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "DOMINANT_RULE_FAMILY_SHARE",
            dominant_family_share,
            "share",
            _format_share(dominant_family_share),
            "Share of candidate rows covered by the dominant rule family.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "GROSS_PROFIT_REPRESENTED",
            gross_profit_total,
            "dollars",
            _format_money(gross_profit_total),
            "Gross profit represented by the unique source rows behind the candidate pack.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "CAPITAL_LEFT_REPRESENTED",
            capital_left_total,
            "dollars",
            _format_money(capital_left_total),
            "Capital left represented by the unique source rows behind the candidate pack.",
        ),
        _summary_row(
            "GUARDRAIL",
            "PRODUCTION_ORDER_CHANGES",
            production_changes,
            "rows",
            _format_int(production_changes),
            "This shadow calibration design pack does not change production ordering logic.",
        ),
        _summary_row(
            "GUARDRAIL",
            "STAGE12_CHANGES",
            stage12_changes,
            "rows",
            _format_int(stage12_changes),
            "This shadow calibration design pack does not change Stage 12.",
        ),
        _summary_row(
            "ACTION_LAYER_SHADOW_CALIBRATION_CANDIDATES",
            "FINAL_RECOMMENDATION",
            FINAL_RECOMMENDATION,
            "label",
            FINAL_RECOMMENDATION,
            "Shadow-only next step for testing these calibration candidates across more promotions.",
        ),
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _build_memo(
    *,
    rows_frame: pd.DataFrame,
    rules_frame: pd.DataFrame,
    summary_frame: pd.DataFrame,
    pretrain_readiness_summary_frame: pd.DataFrame | None,
) -> str:
    summary_lookup = _metric_lookup(summary_frame)
    candidate_rows = int(_as_float(summary_lookup.get("OVER_SUPPRESSION_CANDIDATE_ROWS_SELECTED", 0)))
    unique_skus = int(_as_float(summary_lookup.get("UNIQUE_SKUS", 0)))
    high_priority_rows = int(_as_float(summary_lookup.get("HIGH_PRIORITY_CANDIDATE_ROWS", 0)))
    dominant_family = _normalize_text(summary_lookup.get("DOMINANT_RULE_FAMILY"))
    recommendation = _normalize_text(summary_lookup.get("FINAL_RECOMMENDATION"))

    forecast_reason = _readiness_reason(pretrain_readiness_summary_frame, "forecast_head_reliability")
    action_layer_reason = _readiness_reason(pretrain_readiness_summary_frame, "action_layer_calibration_ready")

    rule_lines: list[str] = []
    for row in rules_frame.head(5).itertuples(index=False):
        rule_lines.append(
            f"- {getattr(row, 'shadow_calibration_rule_candidate')}: {getattr(row, 'row_count')} rows, "
            f"{getattr(row, 'unique_skus')} SKUs, high_priority={getattr(row, 'high_priority_candidate_rows')}, "
            f"family={getattr(row, 'shadow_rule_family')}"
        )
    if not rule_lines:
        rule_lines.append("- No shadow calibration candidates were available after filtering.")

    sample_row_lines: list[str] = []
    for row in rows_frame.drop_duplicates(subset=["source_row_number"]).head(5).itertuples(index=False):
        sample_row_lines.append(
            f"- SKU {getattr(row, 'sku_number')}: {getattr(row, 'sku_description')} | "
            f"family={getattr(row, 'shadow_rule_family')} | strength={getattr(row, 'shadow_rule_strength')} | "
            f"test_action={getattr(row, 'recommended_shadow_test_action')}"
        )
    if not sample_row_lines:
        sample_row_lines.append("- No candidate rows were available to sample.")

    return "\n".join(
        [
            "# Governed Shadow-Only Action-Layer Calibration Candidates",
            "",
            "This is not an order file.",
            "No training was started.",
            "Production order changes = 0.",
            "Stage 12 changes = 0.",
            "",
            "## 1. Executive conclusion",
            "The action layer appears over-conservative in this slice, so the right next step is structured shadow-only calibration testing rather than production change.",
            f"Candidate rows selected = {candidate_rows} across {unique_skus} unique SKUs, with {high_priority_rows} already marked HIGH priority.",
            f"Dominant rule family = {dominant_family or 'none'}.",
            f"Final recommendation = {recommendation or FINAL_RECOMMENDATION}.",
            "",
            "## 2. Why these remain shadow-only",
            "These candidates remain shadow-only and are not production-ready.",
            "Repeated evidence across more promotions is required before any production consideration.",
            "Do not promote any of these rule families to auto-ordering from this pack.",
            "",
            "## 3. Candidate rule view",
            *rule_lines,
            "",
            "## 4. Sample candidate rows",
            *sample_row_lines,
            "",
            "## 5. Readiness connection",
            (action_layer_reason or "Action-layer calibration remains an open readiness blocker."),
            (forecast_reason or "Forecast-head reliability remains a separate training blocker."),
            "This pack is a shadow calibration design layer intended to improve readiness evidence without changing production ordering logic or Stage 12.",
        ]
    )


def build_promotions_action_layer_shadow_calibration_candidates(
    *,
    action_layer_unresolved_inspection_rows_frame: pd.DataFrame,
    action_layer_unresolved_inspection_summary_frame: pd.DataFrame | None = None,
    action_layer_unresolved_inspection_by_bucket_frame: pd.DataFrame | None = None,
    pretrain_readiness_summary_frame: pd.DataFrame | None = None,
) -> PromotionsActionLayerShadowCalibrationCandidatesResult:
    rows_frame = _filter_candidate_rows(action_layer_unresolved_inspection_rows_frame)

    expected_count = _expected_over_suppression_count(action_layer_unresolved_inspection_summary_frame)
    if expected_count > 0 and expected_count != int(len(rows_frame.index)):
        raise PromotionsActionLayerShadowCalibrationCandidatesError(
            "Filtered over-suppression candidate rows do not match the unresolved inspection summary count: "
            f"expected {expected_count}, found {len(rows_frame.index)}."
        )

    if action_layer_unresolved_inspection_by_bucket_frame is not None and not action_layer_unresolved_inspection_by_bucket_frame.empty:
        _require_columns(
            action_layer_unresolved_inspection_by_bucket_frame,
            ("action_layer_inspection_bucket", "row_count"),
            frame_name="action_layer_unresolved_inspection_by_bucket_frame",
        )

    candidate_rows_frame = _assign_row_candidates(rows_frame)
    rules_frame = _build_rules_frame(candidate_rows_frame)
    summary_frame = _build_summary_frame(
        candidate_rows_frame,
        input_rows=int(len(action_layer_unresolved_inspection_rows_frame.index)),
    )
    memo_markdown = _build_memo(
        rows_frame=candidate_rows_frame,
        rules_frame=rules_frame,
        summary_frame=summary_frame,
        pretrain_readiness_summary_frame=pretrain_readiness_summary_frame,
    )

    return PromotionsActionLayerShadowCalibrationCandidatesResult(
        rows_frame=candidate_rows_frame,
        rules_frame=rules_frame,
        summary_frame=summary_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_action_layer_shadow_calibration_candidates(
    *,
    review_artifact_root: str | Path,
    output_root: str | Path | None = None,
) -> PromotionsActionLayerShadowCalibrationCandidatesArtifacts:
    review_artifact_path = Path(review_artifact_root)
    _validate_review_artifact_root(review_artifact_path)

    manifest_path = review_artifact_path / "input_source_manifest.json"
    manifest = _read_json(manifest_path)
    if certification_failed(manifest):
        raise PromotionsActionLayerShadowCalibrationCandidatesError(
            str(manifest.get("source_certification_reason", "source certification failed"))
        )

    result = build_promotions_action_layer_shadow_calibration_candidates(
        action_layer_unresolved_inspection_rows_frame=_read_csv(
            review_artifact_path / INPUT_ROWS_RELATIVE_PATH,
            allow_empty=True,
            empty_columns=[*CORE_COLUMNS],
        ),
        action_layer_unresolved_inspection_summary_frame=_read_csv(
            review_artifact_path / INPUT_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
        action_layer_unresolved_inspection_by_bucket_frame=_read_csv(
            review_artifact_path / INPUT_BY_BUCKET_RELATIVE_PATH,
            allow_empty=True,
        ),
        pretrain_readiness_summary_frame=_read_csv(
            review_artifact_path / READINESS_SUMMARY_RELATIVE_PATH,
            allow_empty=True,
        ),
    )

    destination_root = (
        Path(output_root) if output_root is not None else review_artifact_path / OUTPUT_FOLDER_NAME
    )
    destination_root.mkdir(parents=True, exist_ok=True)

    rows_csv_path = destination_root / "action_layer_shadow_calibration_candidate_rows.csv"
    rules_csv_path = destination_root / "action_layer_shadow_calibration_candidate_rules.csv"
    summary_csv_path = destination_root / "action_layer_shadow_calibration_candidate_summary.csv"
    memo_md_path = destination_root / "action_layer_shadow_calibration_candidate_memo.md"

    add_provenance_columns(result.rows_frame.copy(), manifest).to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.rules_frame.copy(), manifest).to_csv(rules_csv_path, index=False)
    add_provenance_columns(result.summary_frame.copy(), manifest).to_csv(summary_csv_path, index=False)
    memo_md_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsActionLayerShadowCalibrationCandidatesArtifacts(
        rows_csv_path=str(rows_csv_path),
        rules_csv_path=str(rules_csv_path),
        summary_csv_path=str(summary_csv_path),
        memo_md_path=str(memo_md_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a governed shadow-only action-layer calibration candidate pack "
            "without starting training or changing production logic."
        )
    )
    parser.add_argument("--review-artifact-root", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_action_layer_shadow_calibration_candidates(
        review_artifact_root=args.review_artifact_root,
        output_root=args.output_root,
    )
    print("action_layer_shadow_calibration_candidate_rows", artifacts.rows_csv_path)
    print("action_layer_shadow_calibration_candidate_rules", artifacts.rules_csv_path)
    print("action_layer_shadow_calibration_candidate_summary", artifacts.summary_csv_path)
    print("action_layer_shadow_calibration_candidate_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())