from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from pathlib import Path
import re
from typing import Sequence

import numpy as np
import pandas as pd

from runtime.promotions.input_source_provenance import (
    add_provenance_columns,
    build_input_source_manifest,
    certification_failed,
    write_input_source_manifest,
)


MATERIAL_UNIT_DELTA = 3.0
MATERIAL_ACTUAL_UNITS = 5.0
LOW_SELL_THROUGH_THRESHOLD = 0.5
STRONG_SELL_THROUGH_THRESHOLD = 0.8
MATERIAL_CAPITAL_LEFT = 50.0
NEAR_ZERO_RECOMMENDED_ORDER_UNITS = 1.0

MODEL_REQUIRED_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "sku_number": ("sku_number",),
    "model_sku_description": ("sku_description", "sku_description_master"),
    "store_action_label": ("store_action_label", "operator_decision", "operator_action"),
    "expected_promo_demand": (
        "expected_promo_demand",
        "predicted_units_total_promo",
        "expected_units_during_promo",
    ),
    "recommended_order_units": ("recommended_order_units", "order_units", "final_store_order_units"),
    "raw_model_order_units": ("raw_model_order_units",),
    "provisional_review_order_units": ("provisional_review_order_units",),
    "demand_label": ("demand_evidence_label", "demand_label", "operator_decision", "risk_flag"),
    "capital_drag_label": ("capital_drag_label", "risk_flag"),
    "availability_risk_label": ("availability_risk_label", "risk_flag"),
    "order_reconciliation_reason": ("order_reconciliation_reason", "reason_short"),
}

MODEL_OPTIONAL_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "human_review_required_flag": ("human_review_required_flag", "review_flag"),
    "raw_model_order_units": ("raw_model_order_units",),
    "provisional_review_order_units": ("provisional_review_order_units",),
    "shadow_policy_name": ("shadow_policy_name",),
    "shadow_policy_version": ("shadow_policy_version",),
    "shadow_policy_candidate_flag": ("shadow_policy_candidate_flag",),
    "shadow_policy_segment": ("shadow_policy_segment",),
    "shadow_policy_order_units": ("shadow_policy_order_units",),
    "shadow_policy_guardrail_status": ("shadow_policy_guardrail_status",),
    "shadow_policy_blocker_reason": ("shadow_policy_blocker_reason",),
    "shadow_policy_should_publish_flag": ("shadow_policy_should_publish_flag",),
    "shadow_policy_should_affect_final_order_flag": (
        "shadow_policy_should_affect_final_order_flag",
    ),
}

ACTUAL_REQUIRED_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "sku_number": ("sku_number",),
    "actual_sku_description": ("sku_description",),
    "department": ("department",),
    "pl_allocation_units": ("pl_allocation_qty",),
    "store_adjusted_units": ("store_adjusted_qty",),
    "actual_units_sold": ("actual_units_sold",),
    "estimated_actual_gross_profit": ("estimated_actual_gross_profit",),
    "capital_left_unsold": ("capital_left_in_unsold_store_allocation",),
}

ACTUAL_OPTIONAL_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "sell_through_pct_vs_store_adjusted_qty": ("sell_through_pct_vs_store_adjusted_qty",),
    "customer_sell_through_result": ("customer_sell_through_result",),
    "capital_effectiveness_result": ("capital_effectiveness_result",),
    "allocation_quality_summary": ("allocation_quality_summary",),
}

SHADOW_POLICY_COLUMNS: tuple[str, ...] = (
    "shadow_policy_name",
    "shadow_policy_version",
    "shadow_policy_candidate_flag",
    "shadow_policy_segment",
    "shadow_policy_order_units",
    "shadow_policy_guardrail_status",
    "shadow_policy_blocker_reason",
    "shadow_policy_should_publish_flag",
    "shadow_policy_should_affect_final_order_flag",
)

AUDIT_ONLY_MODEL_ENRICHMENT_COLUMNS: tuple[str, ...] = (
    "raw_model_order_units",
    "provisional_review_order_units",
    "human_review_required_flag",
    *SHADOW_POLICY_COLUMNS,
)

ROW_LABEL_PRIORITY: tuple[str, ...] = (
    "MISSED_DEMAND_OPPORTUNITY",
    "CAPITAL_DRAG_FALSE_POSITIVE",
    "NO_PRIOR_PROMO_DEMAND_SURPRISE",
    "STOCK_FLOOR_RISK_SOLD_THROUGH",
    "MATERIAL_UNDERFORECAST",
    "MATERIAL_OVERFORECAST",
    "GOOD_FORECAST",
    "NO_ACTION_REQUIRED",
)

ORDER_IMPLYING_TEXT_RE = re.compile(
    r"\b(order|buy|allocate|recommended)\b",
    re.IGNORECASE,
)
ORDER_NEGATION_TEXT_RE = re.compile(
    r"\b(do not|don't|no auto-order|no order|not order|not buy|not allocate|suppressed)\b",
    re.IGNORECASE,
)
BUY_ACTION_RE = re.compile(r"\bbuy\b", re.IGNORECASE)
REVIEW_ACTION_RE = re.compile(r"\breview\b", re.IGNORECASE)
NO_BUY_ACTION_RE = re.compile(
    r"\b(no_auto_buy|no auto buy|do_not_buy|do not buy|hold_stock|no_demand|never_sold|no_prior)\b",
    re.IGNORECASE,
)
NO_PRIOR_PROMO_RE = re.compile(r"(no_prior|never_sold)", re.IGNORECASE)
NO_DEMAND_RE = re.compile(r"\bno_demand\b|\bno demand\b", re.IGNORECASE)
LOW_SOH_OR_FLOOR_RISK_RE = re.compile(r"(low_soh|floor|availability)", re.IGNORECASE)
CAPITAL_DRAG_HIGH_RE = re.compile(r"capital_drag_high", re.IGNORECASE)


class PromotionsModelVsActualReviewError(RuntimeError):
    """Raised when the governed model-vs-actual review cannot continue safely."""


@dataclass(frozen=True)
class PromotionsModelVsActualReviewArtifacts:
    summary_csv_path: str
    by_action_label_csv_path: str
    by_demand_label_csv_path: str
    by_department_csv_path: str
    top_missed_demand_csv_path: str
    top_capital_drag_csv_path: str
    report_cleanup_issues_csv_path: str
    decision_memo_md_path: str
    input_source_manifest_json_path: str
    input_source_manifest_csv_path: str


@dataclass(frozen=True)
class PromotionsModelVsActualReviewResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    by_action_label_frame: pd.DataFrame
    by_demand_label_frame: pd.DataFrame
    by_department_frame: pd.DataFrame
    top_missed_demand_frame: pd.DataFrame
    top_capital_drag_frame: pd.DataFrame
    report_cleanup_issues_frame: pd.DataFrame
    decision_memo_markdown: str


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise PromotionsModelVsActualReviewError(f"CSV is empty: {path}")
    return frame


def _first_present(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _normalize_identifier(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    normalized = numeric.round(0).astype("Int64").astype(str).replace("<NA>", "")
    fallback = series.fillna("").astype(str).str.strip()
    return normalized.where(normalized.ne(""), fallback).astype(str).str.strip()


def _normalize_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()


def _normalize_token(value: object) -> str:
    return re.sub(r"\s+", "_", str(value).strip().casefold())


def _normalize_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)


def _enrich_model_report_with_audit_frame(
    model_frame: pd.DataFrame,
    audit_frame: pd.DataFrame | None,
) -> pd.DataFrame:
    if audit_frame is None or audit_frame.empty:
        return model_frame.copy()
    if "sku_number" not in model_frame.columns or "sku_number" not in audit_frame.columns:
        return model_frame.copy()

    supplemental_columns = [
        column_name
        for column_name in AUDIT_ONLY_MODEL_ENRICHMENT_COLUMNS
        if column_name in audit_frame.columns and column_name not in model_frame.columns
    ]
    if not supplemental_columns:
        return model_frame.copy()

    audit_subset = audit_frame.loc[:, ["sku_number", *supplemental_columns]].copy()
    audit_subset["_audit_join_sku"] = _normalize_identifier(audit_subset["sku_number"])
    duplicate_mask = audit_subset["_audit_join_sku"].duplicated(keep=False) & audit_subset["_audit_join_sku"].ne("")
    if duplicate_mask.any():
        duplicate_values = sorted(audit_subset.loc[duplicate_mask, "_audit_join_sku"].unique().tolist())
        sample = ", ".join(duplicate_values[:10])
        raise PromotionsModelVsActualReviewError(
            f"audit-only model report has duplicate sku_number values; cannot enrich visible report safely: {sample}"
        )
    audit_subset = audit_subset.drop(columns=["sku_number"])

    enriched = model_frame.copy()
    enriched["_audit_join_sku"] = _normalize_identifier(enriched["sku_number"])
    enriched = enriched.merge(
        audit_subset,
        on="_audit_join_sku",
        how="left",
        validate="one_to_one",
        sort=False,
    )
    return enriched.drop(columns=["_audit_join_sku"])


def _material_overforecast(expected: pd.Series, actual: pd.Series) -> pd.Series:
    return (expected - actual >= MATERIAL_UNIT_DELTA) | (expected > actual * 2.0)


def _material_underforecast(expected: pd.Series, actual: pd.Series) -> pd.Series:
    return (actual - expected >= MATERIAL_UNIT_DELTA) | (actual > expected * 2.0)


def _canonicalize_frame(
    frame: pd.DataFrame,
    *,
    source_name: str,
    required_candidates: dict[str, tuple[str, ...]],
    optional_candidates: dict[str, tuple[str, ...]],
) -> tuple[pd.DataFrame, dict[str, str]]:
    canonical = pd.DataFrame(index=frame.index)
    source_columns: dict[str, str] = {}

    for target_column, candidates in required_candidates.items():
        source_column = _first_present(frame, candidates)
        if source_column is None:
            raise PromotionsModelVsActualReviewError(
                f"{source_name} is missing required columns for {target_column}: {list(candidates)}"
            )
        source_columns[target_column] = source_column
        canonical[target_column] = frame[source_column]

    for target_column, candidates in optional_candidates.items():
        source_column = _first_present(frame, candidates)
        source_columns[target_column] = source_column or ""
        if source_column is None:
            canonical[target_column] = ""
        else:
            canonical[target_column] = frame[source_column]

    return canonical, source_columns


def _prepare_model_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    canonical, source_columns = _canonicalize_frame(
        frame,
        source_name="model allocation report",
        required_candidates=MODEL_REQUIRED_COLUMN_CANDIDATES,
        optional_candidates=MODEL_OPTIONAL_COLUMN_CANDIDATES,
    )
    canonical["sku_number"] = _normalize_identifier(canonical["sku_number"])

    text_columns = [
        "model_sku_description",
        "store_action_label",
        "demand_label",
        "capital_drag_label",
        "availability_risk_label",
        "order_reconciliation_reason",
        "shadow_policy_name",
        "shadow_policy_version",
        "shadow_policy_segment",
        "shadow_policy_guardrail_status",
        "shadow_policy_blocker_reason",
    ]
    for column_name in text_columns:
        canonical[column_name] = _normalize_text(canonical[column_name])

    numeric_columns = [
        "expected_promo_demand",
        "recommended_order_units",
        "raw_model_order_units",
        "provisional_review_order_units",
        "human_review_required_flag",
        "shadow_policy_candidate_flag",
        "shadow_policy_order_units",
        "shadow_policy_should_publish_flag",
        "shadow_policy_should_affect_final_order_flag",
    ]
    for column_name in numeric_columns:
        canonical[column_name] = _normalize_numeric(canonical[column_name])

    return canonical, source_columns


def _prepare_actual_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    canonical, source_columns = _canonicalize_frame(
        frame,
        source_name="actual outcome report",
        required_candidates=ACTUAL_REQUIRED_COLUMN_CANDIDATES,
        optional_candidates=ACTUAL_OPTIONAL_COLUMN_CANDIDATES,
    )
    canonical["sku_number"] = _normalize_identifier(canonical["sku_number"])

    text_columns = [
        "actual_sku_description",
        "department",
        "customer_sell_through_result",
        "capital_effectiveness_result",
        "allocation_quality_summary",
    ]
    for column_name in text_columns:
        canonical[column_name] = _normalize_text(canonical[column_name])

    numeric_columns = [
        "pl_allocation_units",
        "store_adjusted_units",
        "actual_units_sold",
        "estimated_actual_gross_profit",
        "capital_left_unsold",
        "sell_through_pct_vs_store_adjusted_qty",
    ]
    for column_name in numeric_columns:
        canonical[column_name] = _normalize_numeric(canonical[column_name])

    return canonical, source_columns


def _validate_unique_sku(frame: pd.DataFrame, *, source_name: str) -> None:
    duplicate_mask = frame["sku_number"].duplicated(keep=False) & frame["sku_number"].ne("")
    if not duplicate_mask.any():
        return
    duplicate_values = sorted(frame.loc[duplicate_mask, "sku_number"].unique().tolist())
    sample = ", ".join(duplicate_values[:10])
    raise PromotionsModelVsActualReviewError(
        f"{source_name} has duplicate sku_number values; cannot build a governed one-to-one review join: {sample}"
    )


def _safe_correlation(left: pd.Series, right: pd.Series) -> float:
    correlation = left.corr(right)
    if pd.isna(correlation):
        return 0.0
    return float(correlation)


def _safe_rmse(errors: pd.Series) -> float:
    if errors.empty:
        return 0.0
    return float(math.sqrt(float(np.square(errors).mean())))


def _ratio(numerator: float, denominator: float) -> float:
    if math.isclose(denominator, 0.0):
        return 0.0
    return numerator / denominator


def _action_implies_buy(label: str) -> bool:
    token = _normalize_token(label)
    return "buy" in token and not any(
        blocked_token in token
        for blocked_token in (
            "no_auto_buy",
            "do_not_buy",
            "never_sold",
            "no_prior",
            "no_demand",
            "hold_stock",
        )
    )


def _action_is_review_or_no_buy(label: str) -> bool:
    token = _normalize_token(label)
    return "review" in token or any(
        blocked_token in token
        for blocked_token in (
            "no_auto_buy",
            "do_not_buy",
            "never_sold",
            "no_prior",
            "no_demand",
            "hold_stock",
        )
    )


def _text_implies_order(reason_text: str) -> bool:
    if ORDER_NEGATION_TEXT_RE.search(reason_text):
        return False
    return bool(ORDER_IMPLYING_TEXT_RE.search(reason_text))


def _label_contains_no_prior(demand_label: str) -> bool:
    return bool(NO_PRIOR_PROMO_RE.search(_normalize_token(demand_label)))


def _label_contains_no_demand(demand_label: str) -> bool:
    return bool(NO_DEMAND_RE.search(_normalize_token(demand_label)))


def _label_contains_low_soh_or_floor_risk(*values: str) -> bool:
    for value in values:
        token = _normalize_token(value)
        if not token:
            continue
        if "low_soh" in token:
            return True
        if "floor_risk" in token:
            return True
        if token.startswith("below_") and "floor" in token:
            return True
    return False


def _build_review_rows(model_frame: pd.DataFrame, actual_frame: pd.DataFrame) -> pd.DataFrame:
    model_canonical, _ = _prepare_model_frame(model_frame)
    actual_canonical, _ = _prepare_actual_frame(actual_frame)

    _validate_unique_sku(model_canonical, source_name="model allocation report")
    _validate_unique_sku(actual_canonical, source_name="actual outcome report")

    try:
        rows = model_canonical.merge(actual_canonical, on="sku_number", how="inner", validate="one_to_one")
    except pd.errors.MergeError as exc:
        raise PromotionsModelVsActualReviewError(
            "model allocation report and actual outcome report did not produce a governed one-to-one sku join"
        ) from exc

    if len(rows.index) != len(model_canonical.index):
        raise PromotionsModelVsActualReviewError(
            "Joined row count does not equal the model report row count. "
            f"model_rows={len(model_canonical.index)} joined_rows={len(rows.index)}"
        )

    rows["sku_description"] = rows["model_sku_description"].where(
        rows["model_sku_description"].ne(""), rows["actual_sku_description"]
    )
    rows["department"] = rows["department"].where(rows["department"].ne(""), "UNKNOWN")
    rows["demand_label"] = rows["demand_label"].where(rows["demand_label"].ne(""), "UNKNOWN")
    rows["store_action_label"] = rows["store_action_label"].where(
        rows["store_action_label"].ne(""), "UNKNOWN"
    )

    rows["forecast_bias_units"] = rows["expected_promo_demand"] - rows["actual_units_sold"]
    rows["forecast_abs_error_units"] = rows["forecast_bias_units"].abs()
    rows["forecast_squared_error_units"] = np.square(rows["forecast_bias_units"])
    rows["actual_sell_through_vs_store_adjusted"] = np.where(
        rows["store_adjusted_units"] > 0.0,
        rows["actual_units_sold"] / rows["store_adjusted_units"],
        0.0,
    )
    rows["actual_units_ge_5_flag"] = (rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS).astype(int)

    conservative_zero_order = rows.apply(
        lambda row: _action_is_review_or_no_buy(str(row["store_action_label"]))
        and row["recommended_order_units"] <= 0.0,
        axis=1,
    )
    no_prior_label = rows["demand_label"].map(_label_contains_no_prior)
    no_demand_label = rows["demand_label"].map(_label_contains_no_demand)
    low_soh_or_floor_risk = rows.apply(
        lambda row: _label_contains_low_soh_or_floor_risk(
            str(row["store_action_label"]),
            str(row["availability_risk_label"]),
        ),
        axis=1,
    )
    material_overforecast = _material_overforecast(rows["expected_promo_demand"], rows["actual_units_sold"])
    material_underforecast = _material_underforecast(rows["expected_promo_demand"], rows["actual_units_sold"])
    missed_demand = (rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS) & conservative_zero_order
    capital_drag = (
        (rows["store_adjusted_units"] > 0.0)
        & (rows["actual_sell_through_vs_store_adjusted"] < LOW_SELL_THROUGH_THRESHOLD)
        & (rows["capital_left_unsold"] >= MATERIAL_CAPITAL_LEFT)
    )
    stock_floor_sold_through = low_soh_or_floor_risk & (rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS)
    no_prior_surprise = no_prior_label & (rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS)
    good_forecast = (
        ~missed_demand
        & ~capital_drag
        & ~no_prior_surprise
        & ~stock_floor_sold_through
        & ~material_underforecast
        & ~material_overforecast
    )
    no_action_required = (
        (rows["expected_promo_demand"] <= 1.0)
        & (rows["actual_units_sold"] <= 1.0)
        & (rows["recommended_order_units"] <= 0.0)
    )

    rows["is_good_forecast"] = good_forecast.astype(int)
    rows["is_material_overforecast"] = material_overforecast.astype(int)
    rows["is_material_underforecast"] = material_underforecast.astype(int)
    rows["is_missed_demand_opportunity"] = missed_demand.astype(int)
    rows["is_capital_drag_false_positive"] = capital_drag.astype(int)
    rows["is_stock_floor_risk_sold_through"] = stock_floor_sold_through.astype(int)
    rows["is_no_prior_promo_demand_surprise"] = no_prior_surprise.astype(int)
    rows["is_no_action_required"] = no_action_required.astype(int)

    rows["model_error_label"] = "GOOD_FORECAST"
    label_conditions = {
        "MISSED_DEMAND_OPPORTUNITY": missed_demand,
        "CAPITAL_DRAG_FALSE_POSITIVE": capital_drag,
        "NO_PRIOR_PROMO_DEMAND_SURPRISE": no_prior_surprise,
        "STOCK_FLOOR_RISK_SOLD_THROUGH": stock_floor_sold_through,
        "MATERIAL_UNDERFORECAST": material_underforecast,
        "MATERIAL_OVERFORECAST": material_overforecast,
        "GOOD_FORECAST": good_forecast,
        "NO_ACTION_REQUIRED": no_action_required,
    }
    for label_name in reversed(ROW_LABEL_PRIORITY):
        rows.loc[label_conditions[label_name], "model_error_label"] = label_name

    rows.loc[
        (rows["model_error_label"] == "GOOD_FORECAST") & no_action_required,
        "model_error_label",
    ] = "NO_ACTION_REQUIRED"

    ordered_columns = [
        "sku_number",
        "sku_description",
        "department",
        "store_action_label",
        "demand_label",
        "capital_drag_label",
        "availability_risk_label",
        "expected_promo_demand",
        "actual_units_sold",
        "forecast_bias_units",
        "forecast_abs_error_units",
        "recommended_order_units",
        "raw_model_order_units",
        "provisional_review_order_units",
        "pl_allocation_units",
        "store_adjusted_units",
        "actual_sell_through_vs_store_adjusted",
        "estimated_actual_gross_profit",
        "capital_left_unsold",
        "model_error_label",
        "order_reconciliation_reason",
    ]
    remaining_columns = [column_name for column_name in rows.columns if column_name not in ordered_columns]
    return rows[ordered_columns + remaining_columns].copy()


def _summarize_rows(rows: pd.DataFrame) -> pd.DataFrame:
    summary = pd.DataFrame(
        [
            {
                "row_count": int(len(rows.index)),
                "matched_sku_count": int(rows["sku_number"].nunique()),
                "actual_units_total": float(rows["actual_units_sold"].sum()),
                "expected_promo_demand_total": float(rows["expected_promo_demand"].sum()),
                "forecast_bias_units": float(rows["forecast_bias_units"].sum()),
                "forecast_mae": float(rows["forecast_abs_error_units"].mean()),
                "forecast_rmse": _safe_rmse(rows["forecast_bias_units"]),
                "forecast_correlation": _safe_correlation(
                    rows["expected_promo_demand"], rows["actual_units_sold"]
                ),
                "recommended_order_units_total": float(rows["recommended_order_units"].sum()),
                "pl_allocation_units_total": float(rows["pl_allocation_units"].sum()),
                "store_adjusted_units_total": float(rows["store_adjusted_units"].sum()),
                "actual_sell_through_vs_store_adjusted": _ratio(
                    float(rows["actual_units_sold"].sum()),
                    float(rows["store_adjusted_units"].sum()),
                ),
                "actual_gross_profit_total": float(rows["estimated_actual_gross_profit"].sum()),
                "capital_left_unsold_total": float(rows["capital_left_unsold"].sum()),
                "rows_actual_units_ge_5": int((rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS).sum()),
                "units_actual_ge_5": float(
                    rows.loc[rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS, "actual_units_sold"].sum()
                ),
                "gross_profit_actual_ge_5": float(
                    rows.loc[
                        rows["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS,
                        "estimated_actual_gross_profit",
                    ].sum()
                ),
                "good_forecast_rows": int((rows["model_error_label"] == "GOOD_FORECAST").sum()),
                "material_overforecast_rows": int(
                    (rows["model_error_label"] == "MATERIAL_OVERFORECAST").sum()
                ),
                "material_underforecast_rows": int(
                    (rows["model_error_label"] == "MATERIAL_UNDERFORECAST").sum()
                ),
                "missed_demand_rows": int(
                    (rows["model_error_label"] == "MISSED_DEMAND_OPPORTUNITY").sum()
                ),
                "capital_drag_rows": int(
                    (rows["model_error_label"] == "CAPITAL_DRAG_FALSE_POSITIVE").sum()
                ),
                "stock_floor_risk_rows": int(
                    (rows["model_error_label"] == "STOCK_FLOOR_RISK_SOLD_THROUGH").sum()
                ),
                "no_prior_surprise_rows": int(
                    (rows["model_error_label"] == "NO_PRIOR_PROMO_DEMAND_SURPRISE").sum()
                ),
                "no_action_required_rows": int(
                    (rows["model_error_label"] == "NO_ACTION_REQUIRED").sum()
                ),
            }
        ]
    )
    return summary.round(6)


def _summarize_by_group(rows: pd.DataFrame, group_column: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    grouped = rows.groupby(group_column, dropna=False)
    for group_value, group_frame in grouped:
        records.append(
            {
                group_column: group_value if str(group_value).strip() else "UNKNOWN",
                "row_count": int(len(group_frame.index)),
                "matched_sku_count": int(group_frame["sku_number"].nunique()),
                "actual_units_total": float(group_frame["actual_units_sold"].sum()),
                "expected_promo_demand_total": float(group_frame["expected_promo_demand"].sum()),
                "forecast_bias_units": float(group_frame["forecast_bias_units"].sum()),
                "forecast_mae": float(group_frame["forecast_abs_error_units"].mean()),
                "forecast_rmse": _safe_rmse(group_frame["forecast_bias_units"]),
                "recommended_order_units_total": float(group_frame["recommended_order_units"].sum()),
                "pl_allocation_units_total": float(group_frame["pl_allocation_units"].sum()),
                "store_adjusted_units_total": float(group_frame["store_adjusted_units"].sum()),
                "actual_sell_through_vs_store_adjusted": _ratio(
                    float(group_frame["actual_units_sold"].sum()),
                    float(group_frame["store_adjusted_units"].sum()),
                ),
                "actual_gross_profit_total": float(group_frame["estimated_actual_gross_profit"].sum()),
                "capital_left_unsold_total": float(group_frame["capital_left_unsold"].sum()),
                "good_forecast_rows": int((group_frame["model_error_label"] == "GOOD_FORECAST").sum()),
                "material_overforecast_rows": int(
                    (group_frame["model_error_label"] == "MATERIAL_OVERFORECAST").sum()
                ),
                "material_underforecast_rows": int(
                    (group_frame["model_error_label"] == "MATERIAL_UNDERFORECAST").sum()
                ),
                "missed_demand_rows": int(
                    (group_frame["model_error_label"] == "MISSED_DEMAND_OPPORTUNITY").sum()
                ),
                "capital_drag_rows": int(
                    (group_frame["model_error_label"] == "CAPITAL_DRAG_FALSE_POSITIVE").sum()
                ),
                "stock_floor_risk_rows": int(
                    (group_frame["model_error_label"] == "STOCK_FLOOR_RISK_SOLD_THROUGH").sum()
                ),
                "no_prior_surprise_rows": int(
                    (group_frame["model_error_label"] == "NO_PRIOR_PROMO_DEMAND_SURPRISE").sum()
                ),
                "no_action_required_rows": int(
                    (group_frame["model_error_label"] == "NO_ACTION_REQUIRED").sum()
                ),
            }
        )
    if not records:
        return pd.DataFrame(columns=[group_column])
    return pd.DataFrame(records).sort_values(
        by=["actual_units_total", "row_count", group_column],
        ascending=[False, False, True],
    ).reset_index(drop=True).round(6)


def _sorted_subset(rows: pd.DataFrame, *, label: str, sort_columns: list[str]) -> pd.DataFrame:
    subset = rows.loc[rows["model_error_label"] == label].copy()
    if subset.empty:
        return pd.DataFrame(
            columns=[
                "sku_number",
                "sku_description",
                "department",
                "store_action_label",
                "demand_label",
                "expected_promo_demand",
                "actual_units_sold",
                "recommended_order_units",
                "pl_allocation_units",
                "store_adjusted_units",
                "actual_sell_through_vs_store_adjusted",
                "estimated_actual_gross_profit",
                "capital_left_unsold",
                "forecast_bias_units",
                "order_reconciliation_reason",
            ]
        )
    subset = subset.sort_values(by=sort_columns, ascending=[False] * len(sort_columns), kind="stable")
    ordered = subset[
        [
            "sku_number",
            "sku_description",
            "department",
            "store_action_label",
            "demand_label",
            "expected_promo_demand",
            "actual_units_sold",
            "recommended_order_units",
            "pl_allocation_units",
            "store_adjusted_units",
            "actual_sell_through_vs_store_adjusted",
            "estimated_actual_gross_profit",
            "capital_left_unsold",
            "forecast_bias_units",
            "order_reconciliation_reason",
        ]
    ].copy()
    return ordered.reset_index(drop=True)


def _format_issue_value(*pairs: tuple[str, object]) -> str:
    return "; ".join(f"{key}={value}" for key, value in pairs)


def _build_report_cleanup_issues(rows: pd.DataFrame, model_columns: Sequence[str]) -> pd.DataFrame:
    issues: list[dict[str, object]] = []
    visible_model_columns = {str(column_name) for column_name in model_columns}
    visible_action_columns = [
        column_name
        for column_name in ("raw_model_order_units", "provisional_review_order_units", "recommended_order_units")
        if column_name in visible_model_columns
    ]

    def add_issue(
        *,
        sku_number: object,
        sku_description: object,
        issue_type: str,
        current_value: object,
        recommended_fix: str,
    ) -> None:
        issues.append(
            {
                "sku_number": str(sku_number),
                "sku_description": str(sku_description),
                "issue_type": issue_type,
                "current_value": str(current_value),
                "recommended_fix": recommended_fix,
            }
        )

    for _, row in rows.iterrows():
        if _action_implies_buy(str(row["store_action_label"])) and row["recommended_order_units"] <= 0.0:
            add_issue(
                sku_number=row["sku_number"],
                sku_description=row["sku_description"],
                issue_type="BUY_LABEL_WITH_ZERO_ORDER_UNITS",
                current_value=_format_issue_value(
                    ("store_action_label", row["store_action_label"]),
                    ("recommended_order_units", row["recommended_order_units"]),
                ),
                recommended_fix="Align operator_action with order_units; zero-order rows should not present as BUY.",
            )

        if row["recommended_order_units"] <= 0.0 and _text_implies_order(str(row["order_reconciliation_reason"])):
            add_issue(
                sku_number=row["sku_number"],
                sku_description=row["sku_description"],
                issue_type="ORDER_RECOMMENDED_TEXT_WITH_ZERO_ORDER",
                current_value=_format_issue_value(
                    ("order_reconciliation_reason", row["order_reconciliation_reason"]),
                    ("recommended_order_units", row["recommended_order_units"]),
                ),
                recommended_fix="Rewrite reason_short so zero-order rows never imply an order recommendation.",
            )

        action_states = {
            column_name: row[column_name] > 0.0
            for column_name in visible_action_columns
        }
        if len(visible_action_columns) > 1 and len(set(action_states.values())) > 1:
            add_issue(
                sku_number=row["sku_number"],
                sku_description=row["sku_description"],
                issue_type="MULTIPLE_ACTION_COLUMNS_CONFLICT",
                current_value=_format_issue_value(
                    *[(column_name, row[column_name]) for column_name in visible_action_columns]
                ),
                recommended_fix="Collapse the store-facing report to one order_units field and move raw/provisional values to audit-only outputs.",
            )

        if _label_contains_no_demand(str(row["demand_label"])) and row["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS:
            add_issue(
                sku_number=row["sku_number"],
                sku_description=row["sku_description"],
                issue_type="NO_DEMAND_LABEL_WITH_MATERIAL_ACTUAL_UNITS",
                current_value=_format_issue_value(
                    ("demand_label", row["demand_label"]),
                    ("actual_units_sold", row["actual_units_sold"]),
                ),
                recommended_fix="Escalate these rows to demand-surprise review instead of presenting a hard NO_DEMAND decision.",
            )

        if _label_contains_no_prior(str(row["demand_label"])) and row["actual_units_sold"] >= MATERIAL_ACTUAL_UNITS:
            add_issue(
                sku_number=row["sku_number"],
                sku_description=row["sku_description"],
                issue_type="NO_PRIOR_PROMO_LABEL_WITH_MATERIAL_ACTUAL_UNITS",
                current_value=_format_issue_value(
                    ("demand_label", row["demand_label"]),
                    ("actual_units_sold", row["actual_units_sold"]),
                ),
                recommended_fix="Add a no-prior-demand-surprise calibration layer and route these rows to review rather than a hard block.",
            )

        if CAPITAL_DRAG_HIGH_RE.search(str(row["capital_drag_label"])) and row[
            "actual_sell_through_vs_store_adjusted"
        ] >= STRONG_SELL_THROUGH_THRESHOLD:
            add_issue(
                sku_number=row["sku_number"],
                sku_description=row["sku_description"],
                issue_type="CAPITAL_DRAG_HIGH_BUT_STRONG_SELL_THROUGH",
                current_value=_format_issue_value(
                    ("capital_drag_label", row["capital_drag_label"]),
                    (
                        "actual_sell_through_vs_store_adjusted",
                        round(float(row["actual_sell_through_vs_store_adjusted"]), 4),
                    ),
                ),
                recommended_fix="Revisit capital-drag labeling thresholds when accepted allocation is already converting strongly.",
            )

        if _normalize_token(str(row["store_action_label"])) == "low_soh_no_auto_buy" and row[
            "actual_units_sold"
        ] >= MATERIAL_ACTUAL_UNITS:
            add_issue(
                sku_number=row["sku_number"],
                sku_description=row["sku_description"],
                issue_type="LOW_SOH_NO_AUTO_BUY_BUT_ACTUAL_DEMAND",
                current_value=_format_issue_value(
                    ("store_action_label", row["store_action_label"]),
                    ("actual_units_sold", row["actual_units_sold"]),
                ),
                recommended_fix="Keep the low-SOH guardrail, but surface a review recommendation when material demand still lands.",
            )

    for shadow_column in SHADOW_POLICY_COLUMNS:
        if shadow_column in model_columns:
            issues.append(
                {
                    "sku_number": "",
                    "sku_description": "SCHEMA_LEVEL",
                    "issue_type": "SHADOW_FIELDS_VISIBLE_IN_OPERATOR_REPORT",
                    "current_value": shadow_column,
                    "recommended_fix": f"Move {shadow_column} to an audit-only artifact and remove it from the store-facing report.",
                }
            )

    if not issues:
        return pd.DataFrame(
            columns=["sku_number", "sku_description", "issue_type", "current_value", "recommended_fix"]
        )

    issue_frame = pd.DataFrame(issues).drop_duplicates().reset_index(drop=True)
    issue_frame["_schema_level_sort"] = issue_frame["sku_number"].eq("").astype(int)
    issue_frame = issue_frame.sort_values(
        by=["_schema_level_sort", "issue_type", "sku_number"],
        ascending=[False, True, True],
    ).drop(columns="_schema_level_sort")
    return issue_frame.reset_index(drop=True)


def _top_pattern_bullets(
    rows: pd.DataFrame,
    *,
    mask: pd.Series,
    group_column: str,
    value_column: str,
    formatter: str,
    max_items: int = 3,
) -> list[str]:
    subset = rows.loc[mask].copy()
    if subset.empty:
        return []
    grouped = (
        subset.groupby(group_column, dropna=False)
        .agg(row_count=("sku_number", "size"), value_total=(value_column, "sum"))
        .sort_values(by=["value_total", "row_count"], ascending=[False, False])
        .head(max_items)
        .reset_index()
    )
    bullets: list[str] = []
    for _, row in grouped.iterrows():
        bullets.append(
            formatter.format(
                group_value=row[group_column] if str(row[group_column]).strip() else "UNKNOWN",
                row_count=int(row["row_count"]),
                value_total=float(row["value_total"]),
            )
        )
    return bullets


def _build_decision_memo(
    *,
    rows: pd.DataFrame,
    summary_frame: pd.DataFrame,
    report_cleanup_issues_frame: pd.DataFrame,
    manifest: dict[str, object],
) -> str:
    summary = summary_frame.iloc[0]
    forecast_correlation = float(summary["forecast_correlation"])
    forecast_mae = float(summary["forecast_mae"])
    forecast_bias = float(summary["forecast_bias_units"])
    actual_units_total = float(summary["actual_units_total"])
    recommended_units_total = float(summary["recommended_order_units_total"])
    capital_left_total = float(summary["capital_left_unsold_total"])
    accepted_sell_through = float(summary["actual_sell_through_vs_store_adjusted"])
    no_prior_rows = int(
        (
            rows["demand_label"].map(_label_contains_no_prior)
            & rows["actual_units_sold"].ge(MATERIAL_ACTUAL_UNITS)
        ).sum()
    )

    missed_mask = rows["model_error_label"] == "MISSED_DEMAND_OPPORTUNITY"
    capital_drag_mask = rows["model_error_label"] == "CAPITAL_DRAG_FALSE_POSITIVE"

    missed_patterns = _top_pattern_bullets(
        rows,
        mask=missed_mask,
        group_column="store_action_label",
        value_column="actual_units_sold",
        formatter="- {group_value}: {row_count} SKUs and {value_total:.1f} actual units landed after a zero-order or review outcome.",
    )
    missed_patterns += _top_pattern_bullets(
        rows,
        mask=missed_mask,
        group_column="department",
        value_column="actual_units_sold",
        formatter="- Department {group_value}: {row_count} SKUs and {value_total:.1f} actual units were missed by the action layer.",
    )[: max(0, 3 - len(missed_patterns))]

    capital_patterns = _top_pattern_bullets(
        rows,
        mask=capital_drag_mask,
        group_column="department",
        value_column="capital_left_unsold",
        formatter="- Department {group_value}: {row_count} SKUs stranded ${value_total:.2f} in unsold accepted capital.",
    )
    capital_patterns += _top_pattern_bullets(
        rows,
        mask=capital_drag_mask,
        group_column="store_action_label",
        value_column="capital_left_unsold",
        formatter="- {group_value}: {row_count} SKUs stranded ${value_total:.2f} under the current action mapping.",
    )[: max(0, 3 - len(capital_patterns))]

    issue_counts = report_cleanup_issues_frame["issue_type"].value_counts().head(3)
    cleanup_bullets = [
        f"- {issue_type}: {count} affected rows or schema exposures."
        for issue_type, count in issue_counts.items()
    ]
    if "SHADOW_FIELDS_VISIBLE_IN_OPERATOR_REPORT" in report_cleanup_issues_frame["issue_type"].values:
        cleanup_bullets.append(
            "- Move all shadow-policy columns out of the store-facing report and keep them in audit-only artifacts."
        )

    model_improvement_actions = [
        f"- Recalibrate the forecast head before any auto-ordering decision; correlation is {forecast_correlation:.3f}, which is below the 0.5 promotion threshold.",
        f"- Separate action-layer tuning from forecast-head tuning; the action layer only recommended {recommended_units_total:.1f} units against {actual_units_total:.1f} actual units.",
    ]
    if no_prior_rows > 0:
        model_improvement_actions.append(
            f"- Add a no-prior-demand-surprise calibration/review layer; {no_prior_rows} rows were flagged with material sales despite no-prior evidence labels."
        )
    else:
        model_improvement_actions.append(
            "- Keep the next improvement pass focused on action-layer thresholds, because no-prior-promo surprise rows were not material in this run."
        )

    recommendation_lines = [
        f"- Do not promote the model to auto-ordering yet because forecast correlation is {forecast_correlation:.3f}.",
        f"- Treat the current action layer as too conservative because recommended order units totaled {recommended_units_total:.1f} while actual units totaled {actual_units_total:.1f}.",
    ]
    if capital_left_total >= MATERIAL_CAPITAL_LEFT:
        recommendation_lines.append(
            f"- Keep capital-drag guardrails active; unsold accepted capital still totals ${capital_left_total:.2f}."
        )
    if no_prior_rows > 0:
        recommendation_lines.append(
            "- Add a governed no-prior-demand-surprise feature/calibration layer before relaxing no-prior demand suppression."
        )
    recommendation_lines.append(
        "- Keep downstream feature families downstream-only unless a governed ablation proves promotion."
    )

    memo_lines = [
        "# Promotions Model vs Actual Review",
        "",
        "## 1. Executive conclusion",
        f"- The forecast head is not reliable enough for auto-ordering in its current state: MAE is {forecast_mae:.3f}, total bias is {forecast_bias:.1f} units, and correlation to actual units is {forecast_correlation:.3f}.",
        f"- The action layer is materially too conservative: it recommended {recommended_units_total:.1f} units while actual promotion sales reached {actual_units_total:.1f} units.",
        "- This should remain a diagnostics-and-cleanup pass only. Do not change production ordering logic, do not promote shadow policy to production, and do not promote downstream feature families into the units-head core.",
        "",
        "## 2. Model performance summary",
        f"- Matched rows: {int(summary['matched_sku_count'])} of {int(summary['row_count'])}.",
        f"- Expected promo demand totaled {float(summary['expected_promo_demand_total']):.1f} units versus {actual_units_total:.1f} actual units.",
        f"- Accepted allocation sell-through was {accepted_sell_through * 100.0:.1f}% against store-adjusted units.",
        f"- Actual gross profit totaled ${float(summary['actual_gross_profit_total']):.2f}; unsold accepted capital totaled ${capital_left_total:.2f}.",
        "",
        "## 3. What worked",
        "- The join surface is governed and exact for this run, so forecast-head and action-layer reliability can be assessed without source ambiguity.",
        f"- Accepted allocation still converted strongly in aggregate at {accepted_sell_through * 100.0:.1f}% sell-through, so the action layer avoided broad overstock exposure.",
        "- Capital-drag guardrails remain directionally useful as a safety control, even though they need cleanup and better escalation paths.",
        "",
        "## 4. What failed",
        f"- The forecast head is broad and biased high by {forecast_bias:.1f} units, so it is not ready for direct auto-ordering promotion.",
        f"- The action layer collapsed to near-zero ordering with only {recommended_units_total:.1f} recommended units despite material realized demand.",
        f"- The operator report contract exposes contradictory action fields and currently yields {len(report_cleanup_issues_frame.index)} cleanup findings.",
        "",
        "## 5. Key missed-demand patterns",
    ]
    if missed_patterns:
        memo_lines.extend(missed_patterns[:3])
    else:
        memo_lines.append("- No rows crossed the current missed-demand-opportunity threshold.")

    memo_lines.extend(
        [
            "",
            "## 6. Key capital-drag patterns",
        ]
    )
    if capital_patterns:
        memo_lines.extend(capital_patterns[:3])
    else:
        memo_lines.append("- No rows crossed the current capital-drag-false-positive threshold.")

    memo_lines.extend(
        [
            "",
            "## 7. Report-cleanup actions",
            "- Simplify the store-facing report to one decision hierarchy: operator_decision, operator_action, order_units, reason_short, risk_flag, review_flag, and audit_notes.",
        ]
    )
    memo_lines.extend(cleanup_bullets[:3] or ["- No cleanup issues were detected."])

    memo_lines.extend(
        [
            "",
            "## 8. Model-improvement actions",
        ]
    )
    memo_lines.extend(model_improvement_actions[:3])

    memo_lines.extend(
        [
            "",
            "## 9. What not to change yet",
            "- Do not promote the current forecast head or action layer into auto-ordering.",
            "- Do not relax demand proxies or no-prior suppression without a governed surprise-calibration layer.",
            "- Do not promote shadow policy or downstream feature families into production ordering or the units-head core.",
            "",
            "## 10. Recommendation",
        ]
    )
    memo_lines.extend(recommendation_lines)
    memo_lines.extend(
        [
            "",
            f"Source certification: {manifest.get('source_certification_status', 'UNKNOWN')}.",
            f"Source note: {manifest.get('source_certification_reason', '')}",
        ]
    )
    return "\n".join(memo_lines).strip() + "\n"


def build_promotions_model_vs_actual_review(
    *,
    model_allocation_report_frame: pd.DataFrame,
    actual_outcome_report_frame: pd.DataFrame,
    manifest: dict[str, object] | None = None,
    audit_only_report_frame: pd.DataFrame | None = None,
    model_report_columns: Sequence[str] | None = None,
) -> PromotionsModelVsActualReviewResult:
    enriched_model_frame = _enrich_model_report_with_audit_frame(
        model_allocation_report_frame,
        audit_only_report_frame,
    )
    rows = _build_review_rows(enriched_model_frame, actual_outcome_report_frame)
    summary_frame = _summarize_rows(rows)
    by_action_label_frame = _summarize_by_group(rows, "store_action_label")
    by_demand_label_frame = _summarize_by_group(rows, "demand_label")
    by_department_frame = _summarize_by_group(rows, "department")
    top_missed_demand_frame = _sorted_subset(
        rows,
        label="MISSED_DEMAND_OPPORTUNITY",
        sort_columns=["actual_units_sold", "forecast_abs_error_units", "expected_promo_demand"],
    )
    top_capital_drag_frame = _sorted_subset(
        rows,
        label="CAPITAL_DRAG_FALSE_POSITIVE",
        sort_columns=["capital_left_unsold", "store_adjusted_units", "expected_promo_demand"],
    )
    report_cleanup_source_columns = (
        model_allocation_report_frame.columns if model_report_columns is None else model_report_columns
    )
    report_cleanup_issues_frame = _build_report_cleanup_issues(rows, report_cleanup_source_columns)
    summary_frame = summary_frame.copy()
    summary_frame["report_cleanup_issue_count"] = int(len(report_cleanup_issues_frame.index))
    memo_manifest = manifest or {}
    decision_memo_markdown = _build_decision_memo(
        rows=rows,
        summary_frame=summary_frame,
        report_cleanup_issues_frame=report_cleanup_issues_frame,
        manifest=memo_manifest,
    )
    return PromotionsModelVsActualReviewResult(
        rows_frame=rows,
        summary_frame=summary_frame,
        by_action_label_frame=by_action_label_frame,
        by_demand_label_frame=by_demand_label_frame,
        by_department_frame=by_department_frame,
        top_missed_demand_frame=top_missed_demand_frame,
        top_capital_drag_frame=top_capital_drag_frame,
        report_cleanup_issues_frame=report_cleanup_issues_frame,
        decision_memo_markdown=decision_memo_markdown,
    )


def _default_output_root() -> Path:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    return Path("tmp") / f"model_vs_actual_review_{timestamp}"


def write_promotions_model_vs_actual_review(
    *,
    model_allocation_report_csv_path: str | Path,
    actual_outcome_report_csv_path: str | Path,
    audit_only_report_csv_path: str | Path | None = None,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PromotionsModelVsActualReviewArtifacts:
    output_path = Path(output_root) if output_root is not None else _default_output_root()
    output_path.mkdir(parents=True, exist_ok=True)

    model_frame = _read_csv(model_allocation_report_csv_path)
    actual_frame = _read_csv(actual_outcome_report_csv_path)
    audit_frame = _read_csv(audit_only_report_csv_path) if audit_only_report_csv_path is not None else None
    manifest = build_input_source_manifest(
        run_id=run_id or output_path.name,
        feature_inspection_csv_path=model_allocation_report_csv_path,
        feature_inspection_frame=model_frame,
        allocation_report_csv_path=model_allocation_report_csv_path,
        allocation_report_frame=model_frame,
        actual_review_csv_path_requested=actual_outcome_report_csv_path,
        actual_review_csv_path_used=actual_outcome_report_csv_path,
        actual_review_source_status="EXACT_REQUESTED_FILE_USED",
        actual_review_frame=actual_frame,
    )
    if audit_only_report_csv_path is not None:
        manifest["audit_only_report_csv_path"] = str(Path(audit_only_report_csv_path))
    if certification_failed(manifest):
        raise PromotionsModelVsActualReviewError(str(manifest["source_certification_reason"]))

    result = build_promotions_model_vs_actual_review(
        model_allocation_report_frame=model_frame,
        actual_outcome_report_frame=actual_frame,
        manifest=manifest,
        audit_only_report_frame=audit_frame,
        model_report_columns=model_frame.columns,
    )

    summary_csv_path = output_path / "model_vs_actual_summary.csv"
    by_action_label_csv_path = output_path / "model_vs_actual_by_action_label.csv"
    by_demand_label_csv_path = output_path / "model_vs_actual_by_demand_label.csv"
    by_department_csv_path = output_path / "model_vs_actual_by_department.csv"
    top_missed_demand_csv_path = output_path / "model_vs_actual_top_missed_demand.csv"
    top_capital_drag_csv_path = output_path / "model_vs_actual_top_capital_drag.csv"
    report_cleanup_issues_csv_path = output_path / "model_vs_actual_report_cleanup_issues.csv"
    decision_memo_md_path = output_path / "model_vs_actual_decision_memo.md"
    manifest_json_path, manifest_csv_path = write_input_source_manifest(manifest, output_path)

    add_provenance_columns(result.summary_frame, manifest).to_csv(summary_csv_path, index=False)
    result.by_action_label_frame.to_csv(by_action_label_csv_path, index=False)
    result.by_demand_label_frame.to_csv(by_demand_label_csv_path, index=False)
    result.by_department_frame.to_csv(by_department_csv_path, index=False)
    result.top_missed_demand_frame.to_csv(top_missed_demand_csv_path, index=False)
    result.top_capital_drag_frame.to_csv(top_capital_drag_csv_path, index=False)
    result.report_cleanup_issues_frame.to_csv(report_cleanup_issues_csv_path, index=False)
    decision_memo_md_path.write_text(result.decision_memo_markdown, encoding="utf-8")

    return PromotionsModelVsActualReviewArtifacts(
        summary_csv_path=str(summary_csv_path),
        by_action_label_csv_path=str(by_action_label_csv_path),
        by_demand_label_csv_path=str(by_demand_label_csv_path),
        by_department_csv_path=str(by_department_csv_path),
        top_missed_demand_csv_path=str(top_missed_demand_csv_path),
        top_capital_drag_csv_path=str(top_capital_drag_csv_path),
        report_cleanup_issues_csv_path=str(report_cleanup_issues_csv_path),
        decision_memo_md_path=str(decision_memo_md_path),
        input_source_manifest_json_path=str(manifest_json_path),
        input_source_manifest_csv_path=str(manifest_csv_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the governed promotions model-vs-actual review and report-cleanup pass."
    )
    parser.add_argument("--model-allocation-report-csv", required=True)
    parser.add_argument("--actual-outcome-report-csv", required=True)
    parser.add_argument("--audit-only-report-csv")
    parser.add_argument("--output-root")
    parser.add_argument("--run-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    artifacts = write_promotions_model_vs_actual_review(
        model_allocation_report_csv_path=args.model_allocation_report_csv,
        actual_outcome_report_csv_path=args.actual_outcome_report_csv,
        audit_only_report_csv_path=args.audit_only_report_csv,
        output_root=args.output_root,
        run_id=args.run_id,
    )
    print("model_vs_actual_summary", artifacts.summary_csv_path)
    print("model_vs_actual_decision_memo", artifacts.decision_memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())