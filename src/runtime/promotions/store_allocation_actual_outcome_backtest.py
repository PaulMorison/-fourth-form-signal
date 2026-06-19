from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd

from runtime.promotions.input_source_provenance import (
    add_provenance_columns,
    build_input_source_manifest,
    certification_failed,
    write_input_source_manifest,
)


JOIN_KEY_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)

STAGE11_DIAGNOSTIC_REQUIRED_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "sku_description",
    "store_action_label",
    "raw_model_order_units",
    "final_store_order_units",
    "raw_model_order_value",
    "final_store_order_value",
    "current_soh",
    "projected_SOH_at_promo_start",
    "floor_units_required",
    "expected_promo_demand",
    "available_to_sell_before_floor",
    "projected_stock_gap_units",
    "retail_risk_reward_ratio",
    "availability_risk_label",
    "capital_drag_label",
    "order_reconciliation_reason",
)

STAGE11_MASTER_REQUIRED_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_name",
    "promotion_start_date",
    "sku_number",
    "expected_gp_on_speculative_units",
)

ACTUAL_REVIEW_REQUIRED_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotional_end_date",
    "promotion_name",
    "sku_number",
    "sku_description",
    "current_soh",
    "qty_on_order",
    "pl_allocation_qty",
    "store_adjusted_qty",
    "total_stock_available",
    "actual_units_sold",
    "estimated_stock_left_after_promo",
    "avg_8_wk_unit_sales",
    "avg_daily_units",
    "promo_days",
    "expected_units_during_promo",
    "actual_units_vs_expected_units",
    "capital_accepted_by_store_at_cost",
    "capital_left_in_unsold_store_allocation",
    "estimated_actual_gross_profit",
    "allocation_quality_summary",
    "customer_sell_through_result",
    "capital_effectiveness_result",
)

CORRECT_OUTCOME_LABELS = frozenset(
    {
        "PERFECT_ALLOCATION",
        "SAFE_NO_ORDER",
        "GOOD_REDUCE_HOLDING",
        "GOOD_PROTECT_AVAILABILITY",
    }
)

MISSED_SALES_OUTCOME_LABELS = frozenset(
    {
        "MISSED_SALES_RISK",
        "UNDER_ALLOCATED_DEMAND",
        "BAD_REDUCE_HOLDING_MISSED_SALES",
    }
)

CAPITAL_DRAG_OUTCOME_LABELS = frozenset(
    {
        "OVER_ALLOCATED_CAPITAL_DRAG",
        "BAD_PROTECT_AVAILABILITY_OVERBUY",
    }
)

TARGET_ALLOCATION_CORRECT_RATE = 0.75
LOW_SOH_POLICY_TARGET_ALLOCATION_LIFT = 0.03
LOW_SOH_POLICY_TARGET_MISSED_SALES_DROP = 0.05
LOW_SOH_POLICY_MAX_CAPITAL_DRAG_RATE = 0.05
LOW_SOH_POLICY_MAX_ENDING_EXCESS_RATE_DELTA = 0.02
LOW_SOH_POLICY_REDUCE_HOLDING_MIN_CORRECT_RATE = 0.95
LOW_SOH_POLICY_HOLD_STOCK_MIN_MISSED_SALES_DROP = 0.05
LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS = 3
LOW_SOH_POLICY_MAX_PACK_SIZE_AUTO_ORDER = 3
LOW_SOH_POLICY_MAX_UNIT_COST_AUTO_ORDER = 60.0
LOW_SOH_POLICY_MAX_FLOOR_BUFFER_CAPITAL = 60.0
MODEL_PROGRESS_TARGET_SCORE = 98.0
MODEL_PROGRESS_TARGET_CORRECT_RATE = 0.98
MODEL_PROGRESS_MAX_TARGET_EXCESS_RATE = 0.02
MODEL_PROGRESS_MAX_NEGATIVE_CASH_CONVERSION_RATE = 0.02
MODEL_PROGRESS_MAX_PL_FALSE_SUCCESS_RATE = 0.05
SMALL_OPERATING_BUFFER_CAPITAL = 25.0
DEFAULT_MAX_UNMATCHED_ROWS = 5
DEFAULT_MAX_UNMATCHED_RATE = 0.005
MIN_SEGMENT_ROWS = 8
MIN_CALIBRATION_ROWS = 12

LOW_SOH_POLICY_ELIGIBLE_LABELS = frozenset(
    {
        "HOLD_STOCK",
        "HOLD_STOCK_FLOOR_SAFE",
        "LOW_SOH_NO_AUTO_BUY",
        "LOW_SOH_PROTECT_AVAILABILITY",
        "LOW_SOH_BORDERLINE_REVIEW",
        "NO_DEMAND",
        "NEVER_SOLD_IN_PROMO",
        "NO_PRIOR_PROMO_EVIDENCE",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW",
        "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
        "BORDERLINE_OOS_REVIEW",
    }
)

FLOOR_PROTECTION_CLAIM_RE = re.compile(
    r"floor is protected|already protects the .*unit (?:availability )?floor|floor is already protected",
    re.IGNORECASE,
)


class StoreAllocationActualOutcomeBacktestError(RuntimeError):
    """Raised when the diagnostics-only allocation backtest cannot continue safely."""


@dataclass(frozen=True)
class StoreAllocationActualOutcomeArtifacts:
    rows_csv_path: str
    summary_csv_path: str
    gap_accuracy_csv_path: str
    gap_bias_by_segment_csv_path: str
    blind_spot_summary_csv_path: str
    shadow_comparison_csv_path: str
    reason_quality_audit_csv_path: str
    low_soh_protection_shadow_audit_csv_path: str
    low_soh_protection_shadow_summary_csv_path: str
    pl_vs_ff_allocation_mistake_comparison_csv_path: str
    pl_vs_ff_allocation_scorecard_csv_path: str
    capital_reallocation_waterfall_csv_path: str
    score_98_blocker_diagnostic_csv_path: str
    model_98_readiness_scorecard_csv_path: str
    executive_premeeting_summary_csv_path: str
    input_source_manifest_json_path: str
    input_source_manifest_csv_path: str


@dataclass(frozen=True)
class StoreAllocationActualOutcomeResult:
    rows_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    gap_accuracy_frame: pd.DataFrame
    gap_bias_by_segment_frame: pd.DataFrame
    blind_spot_summary_frame: pd.DataFrame
    shadow_comparison_frame: pd.DataFrame
    reason_quality_audit_frame: pd.DataFrame
    low_soh_protection_shadow_audit_frame: pd.DataFrame
    low_soh_protection_shadow_summary_frame: pd.DataFrame
    pl_vs_ff_allocation_mistake_comparison_frame: pd.DataFrame
    pl_vs_ff_allocation_scorecard_frame: pd.DataFrame
    capital_reallocation_waterfall_frame: pd.DataFrame
    score_98_blocker_diagnostic_frame: pd.DataFrame
    model_98_readiness_scorecard_frame: pd.DataFrame
    executive_premeeting_summary_frame: pd.DataFrame


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False)
    if frame.empty:
        raise StoreAllocationActualOutcomeBacktestError(f"CSV is empty: {path}")
    return frame


def _require_columns(frame: pd.DataFrame, required_columns: tuple[str, ...], *, source_name: str) -> None:
    missing = [column_name for column_name in required_columns if column_name not in frame.columns]
    if missing:
        raise StoreAllocationActualOutcomeBacktestError(
            f"{source_name} is missing required columns: {missing}"
        )


def _normalize_identifier(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    normalized = numeric.round(0).astype("Int64").astype(str)
    normalized = normalized.replace("<NA>", "")
    return normalized.str.strip()


def _normalize_text(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.casefold()
    )


def _normalize_date(series: pd.Series) -> pd.Series:
    series_text = series.astype(str).str.strip()
    values = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    iso_mask = series_text.str.fullmatch(r"\d{4}-\d{2}-\d{2}")
    if iso_mask.any():
        values.loc[iso_mask] = pd.to_datetime(
            series_text.loc[iso_mask], format="%Y-%m-%d", errors="coerce"
        )

    dmy_mask = series_text.str.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}")
    if dmy_mask.any():
        values.loc[dmy_mask] = pd.to_datetime(
            series_text.loc[dmy_mask], format="%d/%m/%Y", errors="coerce"
        )

    remaining_mask = values.isna() & series_text.ne("")
    if remaining_mask.any():
        values.loc[remaining_mask] = pd.to_datetime(
            series_text.loc[remaining_mask], errors="coerce"
        )
    return values.dt.strftime("%Y-%m-%d").fillna("")


def _attach_join_key(
    frame: pd.DataFrame,
    *,
    store_column: str,
    promotion_start_column: str,
    promotion_name_column: str,
    sku_column: str,
) -> pd.DataFrame:
    out = frame.copy()
    out["_key_store_number"] = _normalize_identifier(out[store_column])
    out["_key_promotion_start_date"] = _normalize_date(out[promotion_start_column])
    out["_key_promotion_name"] = _normalize_text(out[promotion_name_column])
    out["_key_sku_number"] = _normalize_identifier(out[sku_column])
    out["join_key"] = (
        out["_key_store_number"]
        + "|"
        + out["_key_promotion_start_date"]
        + "|"
        + out["_key_promotion_name"]
        + "|"
        + out["_key_sku_number"]
    )
    return out


def _validate_unique_join_key(frame: pd.DataFrame, *, source_name: str) -> None:
    duplicate_mask = frame["join_key"].duplicated(keep=False)
    if not duplicate_mask.any():
        return
    duplicates = frame.loc[duplicate_mask, list(JOIN_KEY_COLUMNS)].head(10).to_dict(orient="records")
    raise StoreAllocationActualOutcomeBacktestError(
        f"{source_name} contains duplicate Stage 11/actual join keys (first up to 10): {duplicates}"
    )


def _validate_unmatched(
    *,
    unmatched_rows: int,
    total_rows: int,
    source_name: str,
    max_unmatched_rows: int,
    max_unmatched_rate: float,
) -> None:
    if total_rows <= 0:
        return
    unmatched_rate = float(unmatched_rows) / float(total_rows)
    if unmatched_rows <= max_unmatched_rows and unmatched_rate <= max_unmatched_rate:
        return
    raise StoreAllocationActualOutcomeBacktestError(
        f"{source_name} exceeded unmatched tolerance: unmatched_rows={unmatched_rows} total_rows={total_rows} unmatched_rate={unmatched_rate:.4f}"
    )


def _numeric_series(frame: pd.DataFrame, column_name: str, *, default: float = 0.0) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce").fillna(default)


def _text_series(frame: pd.DataFrame, column_name: str, *, default: str = "") -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="object")
    return frame[column_name].fillna(default).astype(str).str.strip()


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator_numeric = pd.to_numeric(numerator, errors="coerce")
    denominator_numeric = pd.to_numeric(denominator, errors="coerce")
    return numerator_numeric.divide(denominator_numeric.where(denominator_numeric.ne(0.0))).replace([np.inf, -np.inf], np.nan)


def _band_numeric(series: pd.Series, *, bins: list[float], labels: list[str]) -> pd.Series:
    return pd.cut(series.fillna(-1.0), bins=bins, labels=labels).astype(str).fillna("unavailable")


def _floor_protected(
    *,
    projected_soh: pd.Series,
    expected_demand: pd.Series,
    available_to_sell_before_floor: pd.Series,
    floor_units_required: pd.Series,
) -> pd.Series:
    projected = pd.to_numeric(projected_soh, errors="coerce").fillna(0.0).clip(lower=0.0)
    expected = pd.to_numeric(expected_demand, errors="coerce").fillna(0.0).clip(lower=0.0)
    available = pd.to_numeric(available_to_sell_before_floor, errors="coerce").fillna(0.0).clip(lower=0.0)
    floor = pd.to_numeric(floor_units_required, errors="coerce").fillna(0.0).clip(lower=0.0)
    return expected.le(available) | projected.sub(expected).ge(floor)


def _material_gap_tolerance(pack_size_value: float | int | None) -> float:
    pack_size_numeric = max(float(pack_size_value or 0.0), 0.0)
    if pack_size_numeric <= 1.0:
        return 2.0
    return max(2.0, pack_size_numeric)


def _gap_direction(error_units: float) -> str:
    if error_units > 0:
        return "OVERSTATED"
    if error_units < 0:
        return "UNDERSTATED"
    return "EVEN"


def _classify_gap_bias_label(*, projected_gap_units: float, actual_gap_units: float, pack_size_value: float | int | None) -> str:
    error_units = float(projected_gap_units or 0.0) - float(actual_gap_units or 0.0)
    if abs(error_units) <= 1.0:
        return "GAP_CORRECT"
    material_tolerance = _material_gap_tolerance(pack_size_value)
    if error_units >= material_tolerance:
        return "GAP_OVERSTATED"
    if error_units <= -material_tolerance:
        return "GAP_UNDERSTATED"
    return "GAP_CORRECT"


def _store_action_family(label_value: str) -> str:
    label_upper = str(label_value or "").strip().upper()
    if label_upper in {"BUY", "PROTECT_AVAILABILITY"}:
        return "AVAILABILITY_ORDER"
    if label_upper in {"REDUCE_HOLDING"}:
        return "REDUCE_HOLDING"
    if label_upper in {
        "NO_DEMAND",
        "NEVER_SOLD_IN_PROMO",
        "NO_PRIOR_PROMO_EVIDENCE",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK",
        "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
        "HOLD_STOCK",
        "HOLD_STOCK_FLOOR_SAFE",
        "LOW_SOH_NO_AUTO_BUY",
    }:
        return "NO_ORDER"
    if label_upper in {
        "BORDERLINE_OOS_REVIEW",
        "LOW_SOH_BORDERLINE_REVIEW",
        "LOW_SOH_PROTECT_AVAILABILITY",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW",
        "DATA_QUALITY_REVIEW",
    }:
        return "REVIEW"
    return "OTHER"


def _prepare_stage11_frames(
    *,
    stage11_diagnostic_frame: pd.DataFrame,
    stage11_master_frame: pd.DataFrame,
    max_unmatched_rows: int,
    max_unmatched_rate: float,
) -> pd.DataFrame:
    _require_columns(
        stage11_diagnostic_frame,
        STAGE11_DIAGNOSTIC_REQUIRED_COLUMNS,
        source_name="Stage 11 reconciliation diagnostic",
    )
    _require_columns(
        stage11_master_frame,
        STAGE11_MASTER_REQUIRED_COLUMNS,
        source_name="Stage 11 master CSV",
    )

    diagnostic = _attach_join_key(
        stage11_diagnostic_frame,
        store_column="store_number",
        promotion_start_column="promotion_start_date",
        promotion_name_column="promotion_name",
        sku_column="sku_number",
    )
    master = _attach_join_key(
        stage11_master_frame,
        store_column="store_number",
        promotion_start_column="promotion_start_date",
        promotion_name_column="promotion_name",
        sku_column="sku_number",
    )
    _validate_unique_join_key(diagnostic, source_name="Stage 11 reconciliation diagnostic")
    _validate_unique_join_key(master, source_name="Stage 11 master CSV")

    master_columns = [
        "join_key",
        *[column_name for column_name in JOIN_KEY_COLUMNS if column_name in master.columns],
        *[
            column_name
            for column_name in (
                "promotion_header_key",
                "expected_gp_on_speculative_units",
                "predicted_units_total_promo",
                "predicted_units_until_promo_start",
                "promo_start_target_soh_units",
                "current_soh_units",
                "qty_on_order_units",
                "promo_allocated_units",
                "promo_type",
                "discount_percent",
                "normal_price",
                "promo_price",
            )
            if column_name in master.columns
        ],
    ]
    master_slice = master.loc[:, master_columns].copy()
    merged = diagnostic.merge(
        master_slice,
        on="join_key",
        how="left",
        validate="1:1",
        indicator="_stage11_master_merge",
        suffixes=("", "_master"),
    )
    unmatched_master_rows = int(merged["_stage11_master_merge"].eq("left_only").sum())
    _validate_unmatched(
        unmatched_rows=unmatched_master_rows,
        total_rows=int(len(merged.index)),
        source_name="Stage 11 diagnostic-to-master join",
        max_unmatched_rows=max_unmatched_rows,
        max_unmatched_rate=max_unmatched_rate,
    )
    merged = merged.drop(columns=["_stage11_master_merge"])
    merged = merged.rename(
        columns={
            "current_soh": "stage11_current_soh",
            "promotion_id": "stage11_promotion_id",
            "current_soh_units": "stage11_master_current_soh_units",
            "qty_on_order_units": "stage11_master_qty_on_order_units",
            "promo_allocated_units": "stage11_master_promo_allocated_units",
            "discount_percent": "stage11_discount_percent",
            "promo_type": "stage11_promo_type",
            "normal_price": "stage11_normal_price",
            "promo_price": "stage11_promo_price",
        }
    )
    return merged


def _prepare_actual_review_frame(actual_review_frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        actual_review_frame,
        ACTUAL_REVIEW_REQUIRED_COLUMNS,
        source_name="Actual promotion review CSV",
    )
    actual = _attach_join_key(
        actual_review_frame,
        store_column="store_number",
        promotion_start_column="promotion_start_date",
        promotion_name_column="promotion_name",
        sku_column="sku_number",
    )
    _validate_unique_join_key(actual, source_name="Actual promotion review CSV")
    return actual


def _join_stage11_to_actual(
    *,
    stage11_frame: pd.DataFrame,
    actual_review_frame: pd.DataFrame,
    max_unmatched_rows: int,
    max_unmatched_rate: float,
) -> pd.DataFrame:
    outer = stage11_frame.merge(
        actual_review_frame,
        on="join_key",
        how="outer",
        indicator=True,
        suffixes=("", "_actual"),
    )
    stage11_only_rows = int(outer["_merge"].eq("left_only").sum())
    actual_only_rows = int(outer["_merge"].eq("right_only").sum())
    _validate_unmatched(
        unmatched_rows=stage11_only_rows,
        total_rows=int(len(stage11_frame.index)),
        source_name="Stage 11 rows missing actual review matches",
        max_unmatched_rows=max_unmatched_rows,
        max_unmatched_rate=max_unmatched_rate,
    )
    _validate_unmatched(
        unmatched_rows=actual_only_rows,
        total_rows=int(len(actual_review_frame.index)),
        source_name="Actual review rows missing Stage 11 matches",
        max_unmatched_rows=max_unmatched_rows,
        max_unmatched_rate=max_unmatched_rate,
    )
    joined = stage11_frame.merge(
        actual_review_frame,
        on="join_key",
        how="inner",
        validate="1:1",
        suffixes=("", "_actual"),
    )
    joined["join_store_number"] = joined["store_number"].astype(str)
    joined["join_promotion_start_date"] = joined["promotion_start_date"].astype(str)
    joined["join_promotion_name"] = joined["promotion_name"].astype(str)
    joined["join_sku_number"] = joined["sku_number"].astype(str)
    promotion_end_match = _normalize_date(joined["promotion_end_date"]).eq(
        _normalize_date(joined["promotional_end_date"])
    )
    joined["promotion_end_date_match_flag"] = promotion_end_match.astype(int)
    return joined


def _build_band_columns(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    out["discount_band"] = _band_numeric(
        _numeric_series(out, "discount_percent"),
        bins=[-0.001, 5.0, 10.0, 20.0, 30.0, 50.0, 1_000.0],
        labels=["0-5pct", "5-10pct", "10-20pct", "20-30pct", "30-50pct", "50pct_plus"],
    )
    out["current_soh_band"] = _band_numeric(
        _numeric_series(out, "current_soh"),
        bins=[-0.001, 0.0, 1.0, 2.0, 5.0, 10.0, 1_000_000.0],
        labels=["0", "1", "2", "3-5", "6-10", "11_plus"],
    )
    out["projected_soh_band"] = _band_numeric(
        _numeric_series(out, "projected_SOH_at_promo_start"),
        bins=[-0.001, 0.0, 1.0, 2.0, 5.0, 10.0, 1_000_000.0],
        labels=["0", "1", "2", "3-5", "6-10", "11_plus"],
    )
    out["actual_sales_band"] = _band_numeric(
        _numeric_series(out, "actual_units_sold"),
        bins=[-0.001, 0.0, 1.0, 5.0, 10.0, 25.0, 1_000_000.0],
        labels=["0", "1", "2-5", "6-10", "11-25", "26_plus"],
    )
    out["avg_8_wk_unit_sales_band"] = _band_numeric(
        _numeric_series(out, "avg_8_wk_unit_sales"),
        bins=[-0.001, 0.0, 0.25, 0.5, 1.0, 2.0, 1_000_000.0],
        labels=["0", "0-0.25", "0.25-0.5", "0.5-1", "1-2", "2_plus"],
    )
    out["supplier_allocation_band"] = _band_numeric(
        _numeric_series(out, "pl_allocation_qty"),
        bins=[-0.001, 0.0, 2.0, 5.0, 10.0, 25.0, 1_000_000.0],
        labels=["0", "1-2", "3-5", "6-10", "11-25", "26_plus"],
    )
    out["pack_size_band"] = _band_numeric(
        _numeric_series(out, "pack_size"),
        bins=[-0.001, 1.0, 3.0, 6.0, 12.0, 1_000_000.0],
        labels=["1", "2-3", "4-6", "7-12", "13_plus"],
    )
    out["price_band"] = _band_numeric(
        _numeric_series(out, "promo_price"),
        bins=[-0.001, 5.0, 10.0, 20.0, 40.0, 1_000_000.0],
        labels=["under_5", "5-10", "10-20", "20-40", "40_plus"],
    )
    out["margin_band"] = _band_numeric(
        _numeric_series(out, "promo_gm_pct"),
        bins=[-10_000.0, 0.0, 20.0, 40.0, 60.0, 1_000_000.0],
        labels=["negative_or_zero", "0-20pct", "20-40pct", "40-60pct", "60pct_plus"],
    )
    out["low_velocity_flag"] = _numeric_series(out, "low_velocity_allocation_breach_flag").gt(0.0).astype(int)
    out["never_sold_in_promo_flag"] = _numeric_series(out, "actual_units_sold").le(0.0).astype(int)
    out["store_action_family"] = _text_series(out, "store_action_label").map(_store_action_family)
    return out


def _build_calibration_tables(rows: pd.DataFrame) -> tuple[list[tuple[tuple[str, ...], dict[tuple[object, ...], dict[str, float]]]], dict[str, float]]:
    calibration_source = rows.copy()
    calibration_source["gap_ratio"] = _safe_ratio(
        calibration_source["actual_stock_gap_units"].add(1.0),
        calibration_source["projected_stock_gap_units_raw"].add(1.0),
    ).fillna(1.0).clip(lower=0.0, upper=3.0)
    calibration_source["gap_bias_delta_units"] = calibration_source["actual_stock_gap_units"].sub(
        calibration_source["projected_stock_gap_units_raw"]
    )

    hierarchy = [
        ("category", "promo_type", "discount_band", "projected_soh_band", "store_action_family"),
        ("category", "projected_soh_band", "store_action_family"),
        ("promo_type", "projected_soh_band", "store_action_family"),
        ("store_action_family",),
    ]

    tables: list[tuple[tuple[str, ...], dict[tuple[object, ...], dict[str, float]]]] = []
    for columns in hierarchy:
        records: dict[tuple[object, ...], dict[str, float]] = {}
        grouped = calibration_source.groupby(list(columns), dropna=False)
        for key_values, group in grouped:
            row_count = int(len(group.index))
            if row_count < MIN_CALIBRATION_ROWS:
                continue
            actual_units = _numeric_series(group, "actual_units_sold")
            records[tuple(key_values if isinstance(key_values, tuple) else (key_values,))] = {
                "row_count": float(row_count),
                "median_gap_ratio": round(float(group["gap_ratio"].median()), 4),
                "mean_gap_bias_delta_units": round(float(group["gap_bias_delta_units"].mean()), 4),
                "mean_actual_gap_units": round(float(group["actual_stock_gap_units"].mean()), 4),
                "q50_actual_units_sold": round(float(actual_units.quantile(0.50)), 4),
                "q70_actual_units_sold": round(float(actual_units.quantile(0.70)), 4),
                "q85_actual_units_sold": round(float(actual_units.quantile(0.85)), 4),
                "q95_actual_units_sold": round(float(actual_units.quantile(0.95)), 4),
            }
        tables.append((columns, records))

    global_actual_units = _numeric_series(calibration_source, "actual_units_sold")
    global_record = {
        "row_count": float(len(calibration_source.index)),
        "median_gap_ratio": round(float(calibration_source["gap_ratio"].median()), 4),
        "mean_gap_bias_delta_units": round(float(calibration_source["gap_bias_delta_units"].mean()), 4),
        "mean_actual_gap_units": round(float(calibration_source["actual_stock_gap_units"].mean()), 4),
        "q50_actual_units_sold": round(float(global_actual_units.quantile(0.50)), 4),
        "q70_actual_units_sold": round(float(global_actual_units.quantile(0.70)), 4),
        "q85_actual_units_sold": round(float(global_actual_units.quantile(0.85)), 4),
        "q95_actual_units_sold": round(float(global_actual_units.quantile(0.95)), 4),
    }
    return tables, global_record


def _select_shadow_quantile_name(row: pd.Series) -> str:
    label_value = str(row.get("store_action_label", "")).strip().upper()
    projected_soh = float(row.get("projected_SOH_at_promo_start", 0.0) or 0.0)
    risk_reward_ratio = float(row.get("retail_risk_reward_ratio", 0.0) or 0.0)
    if label_value in {"NO_DEMAND", "NEVER_SOLD_IN_PROMO", "REDUCE_HOLDING"}:
        return "q50_actual_units_sold"
    if projected_soh <= 1.0 and risk_reward_ratio >= 1.0:
        return "q95_actual_units_sold"
    if label_value == "PROTECT_AVAILABILITY" or projected_soh <= 2.0:
        return "q85_actual_units_sold"
    return "q70_actual_units_sold"


def _resolve_calibration_record(
    row: pd.Series,
    calibration_tables: list[tuple[tuple[str, ...], dict[tuple[object, ...], dict[str, float]]]],
    global_record: dict[str, float],
) -> tuple[dict[str, float], str]:
    for columns, records in calibration_tables:
        lookup_key = tuple(row.get(column_name, "unavailable") for column_name in columns)
        record = records.get(lookup_key)
        if record is not None:
            return record, "+".join(columns)
    return global_record, "global"


def _apply_shadow_pack_rounding(*, gap_units: float, pack_size_value: float, weak_demand: bool) -> tuple[int, str]:
    if gap_units <= 0.0:
        return 0, "ZERO_GAP"
    rounded_units = int(math.ceil(gap_units))
    pack_size = int(max(round(float(pack_size_value or 0.0)), 1))
    if pack_size <= 1:
        return rounded_units, "UNIT_ROUND_UP"
    rounded_pack_units = int(math.ceil(gap_units / float(pack_size)) * pack_size)
    if weak_demand and rounded_pack_units - gap_units >= max(float(pack_size) / 2.0, 1.0):
        return rounded_units, "PACK_OVERHANG_CAPPED_TO_UNIT_GAP"
    return rounded_pack_units, "PACK_ROUND_UP"


def _classify_current_outcome(row: pd.Series) -> str:
    label_value = str(row.get("store_action_label", "")).strip().upper()
    final_units = float(row.get("final_store_order_units", 0.0) or 0.0)
    current_oos = bool(row.get("current_oos_proxy_flag", False))
    ending_excess = bool(row.get("current_ending_excess_stock_flag", False))
    weak_demand = bool(row.get("weak_actual_demand_flag", False))
    actual_units_sold = float(row.get("actual_units_sold", 0.0) or 0.0)
    projected_soh = float(row.get("projected_SOH_at_promo_start", 0.0) or 0.0)
    current_left_after = float(row.get("current_estimated_stock_left_after_promo", 0.0) or 0.0)
    available_before_floor = float(row.get("available_to_sell_before_floor", 0.0) or 0.0)
    current_capital_left = float(row.get("current_capital_left_unsold_value", 0.0) or 0.0)
    no_order = final_units <= 0.0
    actual_demand_positive = actual_units_sold > 0.0
    safe_no_order = no_order and actual_units_sold <= available_before_floor and not current_oos and current_left_after <= projected_soh

    if label_value == "REDUCE_HOLDING":
        if no_order and not current_oos and current_left_after <= projected_soh:
            return "GOOD_REDUCE_HOLDING"
        if no_order and current_oos and actual_demand_positive:
            return "BAD_REDUCE_HOLDING_MISSED_SALES"

    if label_value == "PROTECT_AVAILABILITY":
        if final_units > 0.0 and not current_oos and not ending_excess:
            return "GOOD_PROTECT_AVAILABILITY"
        if final_units > 0.0 and (weak_demand or not actual_demand_positive) and ending_excess:
            return "BAD_PROTECT_AVAILABILITY_OVERBUY"

    if safe_no_order:
        return "SAFE_NO_ORDER"
    if no_order and actual_demand_positive and (current_oos or actual_units_sold > available_before_floor):
        return "MISSED_SALES_RISK"
    if final_units > 0.0 and actual_demand_positive and current_oos:
        return "UNDER_ALLOCATED_DEMAND"
    if final_units > 0.0 and (weak_demand or not actual_demand_positive) and ending_excess and current_capital_left > 0.01:
        return "OVER_ALLOCATED_CAPITAL_DRAG"
    if final_units > 0.0 and not current_oos and not ending_excess:
        return "PERFECT_ALLOCATION"
    if no_order and not current_oos:
        return "SAFE_NO_ORDER"
    if final_units > 0.0 and ending_excess:
        return "OVER_ALLOCATED_CAPITAL_DRAG"
    if current_oos:
        return "UNDER_ALLOCATED_DEMAND" if final_units > 0.0 else "MISSED_SALES_RISK"
    return "SAFE_NO_ORDER"


def _classify_shadow_outcome(row: pd.Series) -> str:
    final_units = float(row.get("shadow_final_store_order_units", 0.0) or 0.0)
    shadow_oos = bool(row.get("shadow_oos_proxy_flag", False))
    ending_excess = bool(row.get("shadow_ending_excess_stock_flag", False))
    weak_demand = bool(row.get("weak_actual_demand_flag", False))
    actual_units_sold = float(row.get("actual_units_sold", 0.0) or 0.0)
    projected_soh = float(row.get("projected_SOH_at_promo_start", 0.0) or 0.0)
    shadow_left_after = float(row.get("shadow_estimated_stock_left_after_promo", 0.0) or 0.0)
    available_before_floor = float(row.get("available_to_sell_before_floor", 0.0) or 0.0)
    shadow_capital_left = float(row.get("shadow_capital_left_unsold_value", 0.0) or 0.0)
    no_order = final_units <= 0.0
    actual_demand_positive = actual_units_sold > 0.0

    if no_order and actual_units_sold <= available_before_floor and not shadow_oos and shadow_left_after <= projected_soh:
        return "SAFE_NO_ORDER"
    if no_order and actual_demand_positive and (shadow_oos or actual_units_sold > available_before_floor):
        return "MISSED_SALES_RISK"
    if final_units > 0.0 and actual_demand_positive and shadow_oos:
        return "UNDER_ALLOCATED_DEMAND"
    if final_units > 0.0 and (weak_demand or not actual_demand_positive) and ending_excess and shadow_capital_left > 0.01:
        return "OVER_ALLOCATED_CAPITAL_DRAG"
    if final_units > 0.0 and not shadow_oos and not ending_excess:
        return "PERFECT_ALLOCATION"
    if no_order and not shadow_oos:
        return "SAFE_NO_ORDER"
    if final_units > 0.0 and ending_excess:
        return "OVER_ALLOCATED_CAPITAL_DRAG"
    if shadow_oos:
        return "UNDER_ALLOCATED_DEMAND" if final_units > 0.0 else "MISSED_SALES_RISK"
    return "SAFE_NO_ORDER"


def _apply_low_soh_protection_shadow(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    label_upper = _text_series(out, "store_action_label").str.upper()
    label_v2 = _text_series(out, "store_action_label_v2")
    label_v2 = label_v2.where(label_v2.ne(""), _text_series(out, "store_action_label"))
    out["store_action_label_v2"] = label_v2

    projected_soh = _numeric_series(out, "projected_SOH_at_promo_start").clip(lower=0.0)
    expected_demand = _numeric_series(out, "expected_promo_demand").clip(lower=0.0)
    available_before_floor = _numeric_series(out, "available_to_sell_before_floor").clip(lower=0.0)
    floor_units = _numeric_series(out, "floor_units_required", default=2.0).clip(lower=0.0)
    current_final_units = _numeric_series(out, "final_store_order_units").clip(lower=0.0)
    raw_units = _numeric_series(out, "raw_model_order_units").clip(lower=0.0)
    pack_size = _numeric_series(out, "pack_size", default=1.0).clip(lower=1.0)
    unit_cost = _numeric_series(out, "allocation_unit_cost").clip(lower=0.0)
    avg_8wk_units = _numeric_series(out, "avg_8_wk_unit_sales").clip(lower=0.0)
    avg_daily_units = _numeric_series(out, "avg_daily_units").clip(lower=0.0)
    capital_drag_label = _text_series(out, "capital_drag_label").str.upper()

    base_candidate = (
        projected_soh.le(1.0)
        & expected_demand.gt(available_before_floor)
        & label_upper.isin(LOW_SOH_POLICY_ELIGIBLE_LABELS)
        & current_final_units.le(0.0)
    )
    low_soh_segment_missed_rate = (
        float(out.loc[base_candidate, "current_missed_sales_risk_flag"].mean())
        if bool(base_candidate.any())
        else 0.0
    )
    out["low_soh_segment_missed_sales_risk_rate"] = round(low_soh_segment_missed_rate, 4)

    baseline_demand_signal = avg_8wk_units.gt(0.0) | avg_daily_units.gt(0.0)
    segment_underprotected_signal = base_candidate & (low_soh_segment_missed_rate >= 0.20)
    demand_signal = baseline_demand_signal | segment_underprotected_signal
    data_quality_blocker = label_upper.eq("DATA_QUALITY_REVIEW")
    high_pack_blocker = pack_size.gt(LOW_SOH_POLICY_MAX_PACK_SIZE_AUTO_ORDER)
    high_capital_blocker = unit_cost.gt(LOW_SOH_POLICY_MAX_UNIT_COST_AUTO_ORDER)
    strong_capital_drag_blocker = capital_drag_label.eq("CAPITAL_DRAG_HIGH") & ~baseline_demand_signal

    floor_gap_units = floor_units.sub(projected_soh).clip(lower=0.0)
    demand_gap_units = expected_demand.sub(available_before_floor).clip(lower=0.0)
    controlled_need_units = np.maximum(floor_gap_units, np.minimum(demand_gap_units, LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS))
    provisional_units = np.ceil(controlled_need_units).clip(0.0, float(LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS))
    raw_cap_units = raw_units.where(raw_units.gt(0.0), provisional_units)
    provisional_units = np.minimum(provisional_units, raw_cap_units)

    expected_le_one_cap = expected_demand.le(1.0) & projected_soh.gt(0.0)
    expected_le_two_cap = expected_demand.le(2.0) & projected_soh.gt(0.0)
    provisional_units = np.where(expected_le_one_cap, np.minimum(provisional_units, 1.0), provisional_units)
    provisional_units = np.where(expected_le_two_cap, np.minimum(provisional_units, 2.0), provisional_units)
    provisional_units = pd.Series(provisional_units, index=out.index, dtype="float64").clip(0.0, float(LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS))

    auto_order_mask = (
        base_candidate
        & demand_signal
        & ~data_quality_blocker
        & ~high_pack_blocker
        & ~high_capital_blocker
        & ~strong_capital_drag_blocker
        & provisional_units.gt(0.0)
    )
    review_mask = base_candidate & demand_signal & ~auto_order_mask
    no_auto_buy_mask = base_candidate & ~demand_signal

    final_units = pd.Series(0.0, index=out.index, dtype="float64")
    final_units = final_units.where(~auto_order_mask, provisional_units)
    shadow_total_order_units = current_final_units.where(~base_candidate, final_units)
    units_added = shadow_total_order_units.sub(current_final_units).clip(lower=0.0)
    capital_added = units_added.mul(unit_cost)
    expected_value = units_added.mul(_numeric_series(out, "expected_gp_per_unit"))

    reason = pd.Series("Not a low-SOH protection candidate.", index=out.index, dtype="object")
    reason = reason.where(~no_auto_buy_mask, "Projected SOH is low, but demand evidence is too weak for automatic capital deployment.")
    reason = reason.where(~review_mask, "Low-SOH protection remains review-only because one or more automatic-order guardrails failed.")
    reason = reason.where(
        ~auto_order_mask,
        "Low-SOH segment is under-protected; apply a tightly capped shadow order to protect the operating floor.",
    )

    cap_reason = pd.Series("not_applicable", index=out.index, dtype="object")
    cap_reason = cap_reason.where(~base_candidate, "not_low_soh_candidate")
    cap_reason = cap_reason.where(~(base_candidate & ~demand_signal), "insufficient_demand_evidence")
    cap_reason = cap_reason.where(~(base_candidate & data_quality_blocker), "data_quality_blocker")
    cap_reason = cap_reason.where(~(base_candidate & high_pack_blocker), "pack_size_exceeds_3_unit_auto_order_cap")
    cap_reason = cap_reason.where(~(base_candidate & high_capital_blocker), "unit_cost_exceeds_low_soh_cap")
    cap_reason = cap_reason.where(~(base_candidate & strong_capital_drag_blocker), "capital_drag_high_without_baseline_signal")
    cap_reason = cap_reason.where(~auto_order_mask, "within_low_soh_floor_protection_cap")

    decision = pd.Series("NOT_CANDIDATE", index=out.index, dtype="object")
    decision = decision.where(~no_auto_buy_mask, "NO_AUTO_BUY")
    decision = decision.where(~review_mask, "BORDERLINE_REVIEW")
    decision = decision.where(~auto_order_mask, "SHADOW_PROTECT_AVAILABILITY")

    shadow_label = label_v2.copy()
    shadow_label = shadow_label.where(~no_auto_buy_mask, "LOW_SOH_NO_AUTO_BUY")
    shadow_label = shadow_label.where(~review_mask, "LOW_SOH_BORDERLINE_REVIEW")
    shadow_label = shadow_label.where(~auto_order_mask, "LOW_SOH_PROTECT_AVAILABILITY")

    score = pd.Series(0.0, index=out.index, dtype="float64")
    score = score.add(projected_soh.le(0.0).astype(float).mul(0.25))
    score = score.add(expected_demand.gt(available_before_floor).astype(float).mul(0.20))
    score = score.add(baseline_demand_signal.astype(float).mul(0.20))
    score = score.add(segment_underprotected_signal.astype(float).mul(0.25))
    score = score.add(unit_cost.le(LOW_SOH_POLICY_MAX_UNIT_COST_AUTO_ORDER).astype(float).mul(0.10))
    score = score.where(base_candidate, 0.0)

    shadow_total_stock = projected_soh.add(shadow_total_order_units)
    shadow_left_after = shadow_total_stock.sub(_numeric_series(out, "actual_units_sold"))
    shadow_oos = (
        shadow_left_after.le(0.0)
        | _numeric_series(out, "actual_units_sold").gt(shadow_total_stock)
    )
    governed_floor_buffer = (
        units_added.gt(0.0)
        & shadow_left_after.gt(projected_soh)
        & shadow_left_after.le(floor_units)
        & units_added.le(2.0)
        & capital_added.le(LOW_SOH_POLICY_MAX_FLOOR_BUFFER_CAPITAL)
    )
    current_correct = _numeric_series(out, "current_allocation_correct_flag").astype(int)
    current_missed = _numeric_series(out, "current_missed_sales_risk_flag").astype(int)
    current_capital_drag = _numeric_series(out, "current_capital_drag_flag").astype(int)
    current_ending_excess = _numeric_series(out, "current_ending_excess_stock_flag").astype(int)
    unchanged_mask = units_added.le(0.0)

    shadow_ending_excess = (
        units_added.gt(0.0)
        & shadow_left_after.gt(np.maximum(projected_soh, floor_units))
    ) | (unchanged_mask & current_ending_excess.eq(1))
    weak_actual_demand = _numeric_series(out, "weak_actual_demand_flag").gt(0.0)
    shadow_capital_drag = (
        units_added.gt(0.0)
        & (
            _numeric_series(out, "actual_units_sold").le(0.0)
            | weak_actual_demand
        )
        & shadow_left_after.gt(projected_soh)
        & ~governed_floor_buffer
    ) | (units_added.gt(0.0) & shadow_ending_excess) | (unchanged_mask & current_capital_drag.eq(1))
    shadow_missed = (
        (unchanged_mask & current_missed.eq(1))
        | (units_added.gt(0.0) & _numeric_series(out, "actual_units_sold").gt(0.0) & shadow_oos)
    )
    shadow_correct = (
        (unchanged_mask & current_correct.eq(1))
        | (units_added.gt(0.0) & _numeric_series(out, "actual_units_sold").gt(0.0) & ~shadow_oos & ~shadow_ending_excess)
        | governed_floor_buffer
    ) & ~shadow_capital_drag

    outcome_label = pd.Series("CURRENT_POLICY_UNCHANGED", index=out.index, dtype="object")
    outcome_label = outcome_label.where(~(units_added.gt(0.0) & shadow_correct), "LOW_SOH_PROTECTION_SUCCESS")
    outcome_label = outcome_label.where(~(units_added.gt(0.0) & shadow_missed), "LOW_SOH_STILL_MISSED_SALES")
    outcome_label = outcome_label.where(~(units_added.gt(0.0) & shadow_capital_drag), "LOW_SOH_CAPITAL_DRAG")
    outcome_label = outcome_label.where(~(unchanged_mask & current_missed.eq(1)), "CURRENT_MISSED_SALES_RISK")
    outcome_label = outcome_label.where(~(unchanged_mask & current_correct.eq(1)), "CURRENT_CORRECT")

    out["current_final_store_order_units"] = current_final_units.astype(int)
    out["low_soh_protection_candidate_flag"] = base_candidate.astype(int)
    out["low_soh_protection_reason"] = reason
    out["low_soh_protection_score"] = score.round(4)
    out["low_soh_protection_decision"] = decision
    out["low_soh_protection_shadow_order_units"] = provisional_units.where(base_candidate, 0.0).round(0).astype(int)
    out["low_soh_protection_final_order_units"] = final_units.round(0).astype(int)
    out["low_soh_protection_cap_reason"] = cap_reason
    out["low_soh_protection_expected_value"] = expected_value.round(2)
    out["low_soh_protection_capital_at_risk"] = capital_added.round(2)
    out["low_soh_policy_shadow_order_units"] = shadow_total_order_units.round(0).astype(int)
    out["low_soh_policy_shadow_label"] = shadow_label
    out["low_soh_policy_shadow_total_stock_available_units"] = shadow_total_stock.round(4)
    out["low_soh_policy_shadow_estimated_stock_left_after_promo"] = shadow_left_after.round(4)
    out["low_soh_policy_shadow_oos_proxy_flag"] = shadow_oos.astype(int)
    out["low_soh_policy_shadow_ending_excess_stock_flag"] = shadow_ending_excess.astype(int)
    out["low_soh_policy_shadow_capital_drag_flag"] = shadow_capital_drag.astype(int)
    out["low_soh_policy_shadow_missed_sales_risk_flag"] = shadow_missed.astype(int)
    out["low_soh_policy_shadow_allocation_correct_flag"] = shadow_correct.astype(int)
    out["low_soh_policy_shadow_outcome_label"] = outcome_label
    out["low_soh_policy_shadow_improved_flag"] = out["low_soh_policy_shadow_allocation_correct_flag"].gt(current_correct).astype(int)
    out["low_soh_policy_shadow_worsened_flag"] = out["low_soh_policy_shadow_allocation_correct_flag"].lt(current_correct).astype(int)
    out["promote_candidate_flag"] = (
        auto_order_mask
        & out["low_soh_policy_shadow_improved_flag"].eq(1)
        & out["low_soh_policy_shadow_worsened_flag"].eq(0)
    ).astype(int)
    promote_blocker = pd.Series("not_blocked", index=out.index, dtype="object")
    promote_blocker = promote_blocker.where(~out["low_soh_policy_shadow_worsened_flag"].eq(1), "shadow_worsens_current_outcome")
    promote_blocker = promote_blocker.where(~review_mask, cap_reason)
    promote_blocker = promote_blocker.where(~no_auto_buy_mask, "insufficient_demand_evidence")
    promote_blocker = promote_blocker.where(~(~base_candidate), "not_low_soh_candidate")
    out["promote_blocker_reason"] = promote_blocker

    out["projected_gap_understated_material_flag"] = out["projected_gap_bias_label"].eq("GAP_UNDERSTATED").astype(int)
    out["projected_gap_overstated_material_flag"] = out["projected_gap_bias_label"].eq("GAP_OVERSTATED").astype(int)
    out["low_soh_gap_underprotection_flag"] = (
        projected_soh.le(1.0)
        & out["actual_stock_gap_units"].gt(out["projected_stock_gap_units_raw"])
        & out["current_missed_sales_risk_flag"].eq(1)
    ).astype(int)
    out["hidden_demand_underprotection_flag"] = (
        base_candidate
        & _numeric_series(out, "actual_units_sold").gt(0.0)
        & out["current_missed_sales_risk_flag"].eq(1)
    ).astype(int)

    blind_label = pd.Series("TRUE_NO_DEMAND", index=out.index, dtype="object")
    blind_label = blind_label.where(~(base_candidate & _numeric_series(out, "actual_units_sold").gt(0.0)), "LOW_SOH_HIDDEN_DEMAND")
    blind_label = blind_label.where(~(projected_soh.le(0.0) & _numeric_series(out, "actual_units_sold").gt(0.0)), "ZERO_SOH_REAL_DEMAND")
    blind_label = blind_label.where(~(label_upper.isin({"HOLD_STOCK", "HOLD_STOCK_FLOOR_SAFE"}) & projected_soh.le(0.0)), "HOLD_STOCK_WITH_NO_STOCK")
    blind_label = blind_label.where(~(label_upper.str.contains("NEVER_SOLD|NO_PRIOR_PROMO", regex=True) & _numeric_series(out, "actual_units_sold").gt(0.0)), "NO_PRIOR_PROMO_EVIDENCE_BUT_SOLD")
    blind_label = blind_label.where(~(baseline_demand_signal & out["current_missed_sales_risk_flag"].eq(1)), "BASELINE_DEMAND_IGNORED")
    blind_label = blind_label.where(~(review_mask & high_pack_blocker), "PACK_SIZE_BLOCKED_PROTECTION")
    blind_label = blind_label.where(~(strong_capital_drag_blocker & out["current_allocation_correct_flag"].eq(1)), "CAPITAL_DRAG_CORRECTLY_SUPPRESSED")
    out["stock_gap_decision_blind_spot_label"] = blind_label
    return out


def _compute_row_frame(joined: pd.DataFrame) -> pd.DataFrame:
    rows = _build_band_columns(joined)
    rows["promotion_id"] = _text_series(rows, "stage11_promotion_id")
    if "promotion_header_key" in rows.columns:
        rows["promotion_id"] = rows["promotion_id"].where(
            rows["promotion_id"].ne(""),
            _text_series(rows, "promotion_header_key"),
        )
    rows["floor_units_required"] = _numeric_series(rows, "floor_units_required", default=2.0).clip(lower=0.0)
    rows["expected_promo_demand"] = _numeric_series(rows, "expected_promo_demand").clip(lower=0.0)
    rows["projected_SOH_at_promo_start"] = _numeric_series(rows, "projected_SOH_at_promo_start").clip(lower=0.0)
    rows["available_to_sell_before_floor"] = _numeric_series(rows, "available_to_sell_before_floor").clip(lower=0.0)
    rows["projected_stock_gap_units"] = _numeric_series(rows, "projected_stock_gap_units").clip(lower=0.0)
    rows["projected_stock_gap_units_raw"] = rows["projected_stock_gap_units"]
    rows["raw_model_order_units"] = _numeric_series(rows, "raw_model_order_units").clip(lower=0.0)
    rows["final_store_order_units"] = _numeric_series(rows, "final_store_order_units").clip(lower=0.0)
    rows["raw_model_order_value"] = _numeric_series(rows, "raw_model_order_value").clip(lower=0.0)
    rows["final_store_order_value"] = _numeric_series(rows, "final_store_order_value").clip(lower=0.0)
    rows["retail_risk_reward_ratio"] = _numeric_series(rows, "retail_risk_reward_ratio")
    rows["actual_units_sold"] = _numeric_series(rows, "actual_units_sold").clip(lower=0.0)
    rows["expected_units_during_promo"] = _numeric_series(rows, "expected_units_during_promo").clip(lower=0.0)
    rows["estimated_stock_left_after_promo"] = _numeric_series(rows, "estimated_stock_left_after_promo")
    rows["total_stock_available"] = _numeric_series(rows, "total_stock_available").clip(lower=0.0)
    rows["actual_units_vs_expected_units_numeric"] = _numeric_series(rows, "actual_units_vs_expected_units")
    rows["capital_left_in_unsold_store_allocation"] = _numeric_series(
        rows, "capital_left_in_unsold_store_allocation"
    ).clip(lower=0.0)
    rows["estimated_actual_gross_profit"] = _numeric_series(rows, "estimated_actual_gross_profit")
    rows["estimated_gross_profit_after_priceline_fees"] = _numeric_series(
        rows, "estimated_gross_profit_after_priceline_fees"
    )
    rows["pack_size"] = _numeric_series(rows, "pack_size", default=1.0).clip(lower=1.0)
    rows["expected_gp_on_speculative_units"] = _numeric_series(rows, "expected_gp_on_speculative_units")
    rows["current_floor_protected_flag"] = _floor_protected(
        projected_soh=rows["projected_SOH_at_promo_start"],
        expected_demand=rows["expected_promo_demand"],
        available_to_sell_before_floor=rows["available_to_sell_before_floor"],
        floor_units_required=rows["floor_units_required"],
    ).astype(int)

    unit_cost = _safe_ratio(rows["raw_model_order_value"], rows["raw_model_order_units"])
    unit_cost = unit_cost.where(unit_cost.notna(), _numeric_series(rows, "last_received_cost"))
    unit_cost = unit_cost.where(unit_cost.notna(), _numeric_series(rows, "promo_effective_cost"))
    unit_cost = unit_cost.where(unit_cost.notna(), _numeric_series(rows, "promo_cost_price"))
    rows["allocation_unit_cost"] = unit_cost.fillna(0.0).clip(lower=0.0)

    expected_gp_per_unit = _safe_ratio(
        rows["expected_gp_on_speculative_units"], rows["raw_model_order_units"]
    )
    expected_gp_per_unit = expected_gp_per_unit.where(
        expected_gp_per_unit.notna(), rows["allocation_unit_cost"].mul(rows["retail_risk_reward_ratio"])
    )
    rows["expected_gp_per_unit"] = expected_gp_per_unit.fillna(0.0)

    rows["actual_stock_gap_units"] = (
        rows["actual_units_sold"].add(rows["floor_units_required"]).sub(rows["projected_SOH_at_promo_start"])
    ).clip(lower=0.0)
    rows["projected_gap_error_units"] = rows["projected_stock_gap_units_raw"].sub(rows["actual_stock_gap_units"])
    rows["projected_gap_abs_error_units"] = rows["projected_gap_error_units"].abs()
    rows["projected_gap_direction"] = rows["projected_gap_error_units"].map(_gap_direction)
    rows["projected_gap_material_tolerance_units"] = rows["pack_size"].map(_material_gap_tolerance)
    rows["projected_gap_bias_label"] = [
        _classify_gap_bias_label(
            projected_gap_units=projected_gap,
            actual_gap_units=actual_gap,
            pack_size_value=pack_size,
        )
        for projected_gap, actual_gap, pack_size in zip(
            rows["projected_stock_gap_units_raw"].tolist(),
            rows["actual_stock_gap_units"].tolist(),
            rows["pack_size"].tolist(),
            strict=False,
        )
    ]
    rows["projected_gap_material_bias_flag"] = (
        rows["projected_gap_bias_label"].isin({"GAP_OVERSTATED", "GAP_UNDERSTATED"}).astype(int)
    )

    weak_or_no_demand_text = (
        _text_series(rows, "allocation_quality_summary").str.upper()
        + " | "
        + _text_series(rows, "customer_sell_through_result").str.upper()
        + " | "
        + _text_series(rows, "capital_effectiveness_result").str.upper()
    )
    rows["weak_actual_demand_flag"] = (
        rows["actual_units_sold"].le(0.0)
        | rows["actual_units_vs_expected_units_numeric"].lt(0.5)
        | weak_or_no_demand_text.str.contains("NO DEMAND|POOR SELL THROUGH|WEAK", na=False)
    )
    rows["actual_review_oos_proxy_flag"] = (
        rows["estimated_stock_left_after_promo"].le(0.0)
        | rows["actual_units_sold"].gt(rows["total_stock_available"])
    ).astype(int)

    rows["current_total_stock_available_units"] = rows["projected_SOH_at_promo_start"].add(rows["final_store_order_units"])
    rows["current_estimated_stock_left_after_promo"] = rows["current_total_stock_available_units"].sub(rows["actual_units_sold"])
    rows["current_floor_breach_flag"] = rows["current_estimated_stock_left_after_promo"].lt(rows["floor_units_required"]).astype(int)
    rows["current_oos_proxy_flag"] = (
        rows["current_estimated_stock_left_after_promo"].le(0.0)
        | rows["actual_units_sold"].gt(rows["current_total_stock_available_units"])
    ).astype(int)
    rows["current_ending_excess_stock_flag"] = (
        rows["current_estimated_stock_left_after_promo"].gt(rows["projected_SOH_at_promo_start"])
        | rows["current_estimated_stock_left_after_promo"].gt(rows["floor_units_required"].clip(lower=2.0))
    ).astype(int)
    rows["current_capital_at_risk"] = rows["final_store_order_units"].mul(rows["allocation_unit_cost"])
    rows["current_capital_left_unsold_value"] = rows["current_estimated_stock_left_after_promo"].clip(lower=0.0).mul(rows["allocation_unit_cost"])
    rows["current_expected_gp"] = rows["final_store_order_units"].mul(rows["expected_gp_per_unit"])
    rows["current_risk_reward_ratio"] = _safe_ratio(
        rows["current_expected_gp"], rows["current_capital_at_risk"]
    ).fillna(0.0)

    calibration_tables, global_record = _build_calibration_tables(rows)
    shadow_gap_values: list[float] = []
    shadow_gap_factors: list[float] = []
    shadow_gap_reasons: list[str] = []
    shadow_gap_quantiles: list[str] = []
    shadow_final_units_values: list[int] = []
    shadow_rounding_classes: list[str] = []

    for _, row in rows.iterrows():
        calibration_record, calibration_level = _resolve_calibration_record(
            row, calibration_tables, global_record
        )
        quantile_name = _select_shadow_quantile_name(row)
        raw_gap_units = float(row["projected_stock_gap_units_raw"] or 0.0)
        projected_soh = float(row["projected_SOH_at_promo_start"] or 0.0)
        floor_units = float(row["floor_units_required"] or 0.0)
        bias_factor = max(float(calibration_record.get("median_gap_ratio", 1.0) or 1.0), 0.0)
        additive_gap = max(raw_gap_units + float(calibration_record.get("mean_gap_bias_delta_units", 0.0) or 0.0), 0.0)
        multiplicative_gap = max(raw_gap_units * bias_factor, 0.0)
        base_calibrated_gap = max((additive_gap + multiplicative_gap) / 2.0, 0.0)
        quantile_units = max(float(calibration_record.get(quantile_name, 0.0) or 0.0), 0.0)
        quantile_gap_units = max((quantile_units + floor_units) - projected_soh, 0.0)
        action_family = str(row.get("store_action_family", "OTHER"))
        if action_family in {"NO_ORDER", "REDUCE_HOLDING"}:
            calibrated_gap_units = min(base_calibrated_gap, quantile_gap_units if quantile_gap_units > 0.0 else base_calibrated_gap)
        else:
            calibrated_gap_units = max(base_calibrated_gap, quantile_gap_units)
        shadow_final_units, rounding_class = _apply_shadow_pack_rounding(
            gap_units=calibrated_gap_units,
            pack_size_value=float(row.get("pack_size", 1.0) or 1.0),
            weak_demand=bool(row.get("weak_actual_demand_flag", False)),
        )
        shadow_gap_values.append(round(calibrated_gap_units, 4))
        shadow_gap_factors.append(round(calibrated_gap_units / raw_gap_units, 4) if raw_gap_units > 0.0 else round(calibrated_gap_units, 4))
        shadow_gap_quantiles.append(quantile_name)
        shadow_final_units_values.append(shadow_final_units)
        shadow_rounding_classes.append(rounding_class)
        shadow_gap_reasons.append(
            f"bias={bias_factor:.3f}; additive_delta={float(calibration_record.get('mean_gap_bias_delta_units', 0.0) or 0.0):.3f}; quantile={quantile_name}; level={calibration_level}; rounding={rounding_class}"
        )

    rows["projected_stock_gap_units_calibrated_shadow"] = pd.Series(shadow_gap_values, index=rows.index, dtype="float64")
    rows["projected_stock_gap_calibration_factor"] = pd.Series(shadow_gap_factors, index=rows.index, dtype="float64")
    rows["projected_stock_gap_calibration_reason"] = pd.Series(shadow_gap_reasons, index=rows.index, dtype="object")
    rows["shadow_gap_quantile_name"] = pd.Series(shadow_gap_quantiles, index=rows.index, dtype="object")
    rows["shadow_final_store_order_units"] = pd.Series(shadow_final_units_values, index=rows.index, dtype="int64")
    rows["shadow_rounding_class"] = pd.Series(shadow_rounding_classes, index=rows.index, dtype="object")

    rows["shadow_total_stock_available_units"] = rows["projected_SOH_at_promo_start"].add(rows["shadow_final_store_order_units"])
    rows["shadow_estimated_stock_left_after_promo"] = rows["shadow_total_stock_available_units"].sub(rows["actual_units_sold"])
    rows["shadow_floor_breach_flag"] = rows["shadow_estimated_stock_left_after_promo"].lt(rows["floor_units_required"]).astype(int)
    rows["shadow_oos_proxy_flag"] = (
        rows["shadow_estimated_stock_left_after_promo"].le(0.0)
        | rows["actual_units_sold"].gt(rows["shadow_total_stock_available_units"])
    ).astype(int)
    rows["shadow_ending_excess_stock_flag"] = (
        rows["shadow_estimated_stock_left_after_promo"].gt(rows["projected_SOH_at_promo_start"])
        | rows["shadow_estimated_stock_left_after_promo"].gt(rows["floor_units_required"].clip(lower=2.0))
    ).astype(int)
    rows["shadow_capital_at_risk"] = rows["shadow_final_store_order_units"].mul(rows["allocation_unit_cost"])
    rows["shadow_capital_left_unsold_value"] = rows["shadow_estimated_stock_left_after_promo"].clip(lower=0.0).mul(rows["allocation_unit_cost"])
    rows["shadow_expected_gp"] = rows["shadow_final_store_order_units"].mul(rows["expected_gp_per_unit"])
    rows["shadow_risk_reward_ratio"] = _safe_ratio(
        rows["shadow_expected_gp"], rows["shadow_capital_at_risk"]
    ).fillna(0.0)

    rows["allocation_outcome_label"] = rows.apply(_classify_current_outcome, axis=1)
    rows["current_allocation_outcome_label"] = rows["allocation_outcome_label"]
    rows["allocation_correct_flag"] = rows["allocation_outcome_label"].isin(CORRECT_OUTCOME_LABELS).astype(int)
    rows["current_allocation_correct_flag"] = rows["allocation_correct_flag"]
    rows["current_missed_sales_risk_flag"] = rows["allocation_outcome_label"].isin(MISSED_SALES_OUTCOME_LABELS).astype(int)
    rows["current_capital_drag_flag"] = rows["allocation_outcome_label"].isin(CAPITAL_DRAG_OUTCOME_LABELS).astype(int)

    rows["shadow_allocation_outcome_label"] = rows.apply(_classify_shadow_outcome, axis=1)
    rows["shadow_allocation_correct_flag"] = rows["shadow_allocation_outcome_label"].isin(
        {"PERFECT_ALLOCATION", "SAFE_NO_ORDER"}
    ).astype(int)
    rows["shadow_missed_sales_risk_flag"] = rows["shadow_allocation_outcome_label"].isin(
        {"MISSED_SALES_RISK", "UNDER_ALLOCATED_DEMAND"}
    ).astype(int)
    rows["shadow_capital_drag_flag"] = rows["shadow_allocation_outcome_label"].eq("OVER_ALLOCATED_CAPITAL_DRAG").astype(int)
    rows["shadow_improves_outcome_flag"] = (
        rows["shadow_allocation_correct_flag"].gt(rows["current_allocation_correct_flag"])
        | (
            rows["shadow_allocation_correct_flag"].eq(rows["current_allocation_correct_flag"])
            & rows["shadow_capital_at_risk"].lt(rows["current_capital_at_risk"])
            & rows["shadow_missed_sales_risk_flag"].le(rows["current_missed_sales_risk_flag"])
        )
    ).astype(int)

    rows = _apply_low_soh_protection_shadow(rows)

    rows["floor_protection_claim_flag"] = _text_series(rows, "order_reconciliation_reason").str.contains(
        FLOOR_PROTECTION_CLAIM_RE,
        na=False,
    ).astype(int)
    rows["reason_quality_issue_flag"] = (
        rows["floor_protection_claim_flag"].eq(1)
        & rows["current_floor_protected_flag"].eq(0)
    ).astype(int)
    rows["reason_quality_issue_class"] = np.where(
        rows["reason_quality_issue_flag"].eq(1),
        "FALSE_FLOOR_PROTECTION_CLAIM",
        "OK",
    )
    rows["reason_quality_recommended_text"] = np.where(
        rows["reason_quality_issue_flag"].eq(1),
        "Do not auto-order. Projected SOH is below the 2-unit floor, but demand evidence is weak, so the system is not allocating extra capital automatically.",
        "",
    )

    return rows


def _summarize_rates(rows: pd.DataFrame) -> dict[str, object]:
    protect_mask = _text_series(rows, "store_action_label").eq("PROTECT_AVAILABILITY")
    reduce_mask = _text_series(rows, "store_action_label").eq("REDUCE_HOLDING")
    no_demand_mask = _text_series(rows, "store_action_label").eq("NO_DEMAND")
    never_sold_mask = _text_series(rows, "store_action_label").eq("NEVER_SOLD_IN_PROMO")
    gap_overstated_rate = float(rows["projected_gap_bias_label"].eq("GAP_OVERSTATED").mean())
    gap_understated_rate = float(rows["projected_gap_bias_label"].eq("GAP_UNDERSTATED").mean())
    gap_correct_rate = float(rows["projected_gap_bias_label"].eq("GAP_CORRECT").mean())
    allocation_correct_rate = float(rows["allocation_correct_flag"].mean())
    shadow_correct_rate = float(rows["shadow_allocation_correct_flag"].mean())
    summary = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "row_count": int(len(rows.index)),
        "allocation_correct_rate": round(allocation_correct_rate, 4),
        "missed_sales_risk_rate": round(float(rows["current_missed_sales_risk_flag"].mean()), 4),
        "overallocated_capital_drag_rate": round(float(rows["current_capital_drag_flag"].mean()), 4),
        "oos_proxy_rate": round(float(rows["current_oos_proxy_flag"].mean()), 4),
        "ending_excess_stock_rate": round(float(rows["current_ending_excess_stock_flag"].mean()), 4),
        "safe_no_order_rate": round(float(rows["allocation_outcome_label"].eq("SAFE_NO_ORDER").mean()), 4),
        "protect_availability_success_rate": round(
            float(rows.loc[protect_mask, "allocation_outcome_label"].eq("GOOD_PROTECT_AVAILABILITY").mean()) if protect_mask.any() else 0.0,
            4,
        ),
        "reduce_holding_success_rate": round(
            float(rows.loc[reduce_mask, "allocation_outcome_label"].eq("GOOD_REDUCE_HOLDING").mean()) if reduce_mask.any() else 0.0,
            4,
        ),
        "no_demand_success_rate": round(
            float(rows.loc[no_demand_mask, "allocation_correct_flag"].mean()) if no_demand_mask.any() else 0.0,
            4,
        ),
        "never_sold_success_rate": round(
            float(rows.loc[never_sold_mask, "allocation_correct_flag"].mean()) if never_sold_mask.any() else 0.0,
            4,
        ),
        "projected_gap_overstated_rate": round(gap_overstated_rate, 4),
        "projected_gap_understated_rate": round(gap_understated_rate, 4),
        "projected_gap_correct_rate": round(gap_correct_rate, 4),
        "mean_projected_gap_error_units": round(float(rows["projected_gap_error_units"].mean()), 4),
        "mean_projected_gap_abs_error_units": round(float(rows["projected_gap_abs_error_units"].mean()), 4),
        "shadow_allocation_correct_rate": round(shadow_correct_rate, 4),
        "shadow_correct_rate_delta": round(shadow_correct_rate - allocation_correct_rate, 4),
        "shadow_missed_sales_risk_rate": round(float(rows["shadow_missed_sales_risk_flag"].mean()), 4),
        "shadow_overallocated_capital_drag_rate": round(float(rows["shadow_capital_drag_flag"].mean()), 4),
        "shadow_oos_proxy_rate": round(float(rows["shadow_oos_proxy_flag"].mean()), 4),
        "shadow_ending_excess_stock_rate": round(float(rows["shadow_ending_excess_stock_flag"].mean()), 4),
        "shadow_improved_row_count": int(rows["shadow_improves_outcome_flag"].sum()),
        "reason_quality_issue_count": int(rows["reason_quality_issue_flag"].sum()),
        "allocation_target_rate": TARGET_ALLOCATION_CORRECT_RATE,
        "allocation_target_status": "PASS" if allocation_correct_rate >= TARGET_ALLOCATION_CORRECT_RATE else "WARN_BELOW_TARGET",
    }
    if (
        shadow_correct_rate >= max(allocation_correct_rate + 0.03, TARGET_ALLOCATION_CORRECT_RATE)
        and float(rows["shadow_missed_sales_risk_flag"].mean()) <= float(rows["current_missed_sales_risk_flag"].mean())
        and float(rows["shadow_capital_drag_flag"].mean()) <= float(rows["current_capital_drag_flag"].mean())
    ):
        summary["shadow_promotion_recommendation"] = "PROMOTE_FROM_SHADOW"
        summary["shadow_promotion_reason"] = (
            "Shadow calibration improves allocation correctness above target without worsening missed-sales or capital-drag rates on this actual-outcome review file."
        )
    elif shadow_correct_rate > allocation_correct_rate:
        summary["shadow_promotion_recommendation"] = "KEEP_IN_SHADOW_AND_EXPAND_BACKTEST"
        summary["shadow_promotion_reason"] = (
            "Shadow calibration shows directional lift, but the evidence is still single-review diagnostics and should remain shadow-only until adjacent replays confirm the trade-offs."
        )
    else:
        summary["shadow_promotion_recommendation"] = "DO_NOT_PROMOTE_FROM_SHADOW"
        summary["shadow_promotion_reason"] = (
            "Shadow calibration does not yet deliver a clean enough lift versus current governed allocation outcomes. Keep it diagnostics-only."
        )
    return summary


def _rate(rows: pd.DataFrame, column_name: str, mask: pd.Series | None = None) -> float:
    source = rows if mask is None else rows.loc[mask]
    if source.empty:
        return 0.0
    return float(_numeric_series(source, column_name).mean())


def _summarize_low_soh_policy_shadow(rows: pd.DataFrame) -> pd.DataFrame:
    label_upper = _text_series(rows, "store_action_label").str.upper()
    label_v2_upper = _text_series(rows, "store_action_label_v2").str.upper()
    reduce_mask = label_upper.eq("REDUCE_HOLDING")
    hold_or_low_soh_mask = label_upper.isin(
        {
            "HOLD_STOCK",
            "HOLD_STOCK_FLOOR_SAFE",
            "LOW_SOH_NO_AUTO_BUY",
            "LOW_SOH_PROTECT_AVAILABILITY",
            "LOW_SOH_BORDERLINE_REVIEW",
        }
    ) | label_v2_upper.isin(
        {
            "HOLD_STOCK",
            "HOLD_STOCK_FLOOR_SAFE",
            "LOW_SOH_NO_AUTO_BUY",
            "LOW_SOH_PROTECT_AVAILABILITY",
            "LOW_SOH_BORDERLINE_REVIEW",
        }
    )
    candidate_mask = _numeric_series(rows, "low_soh_protection_candidate_flag").gt(0.0)

    current_correct_rate = _rate(rows, "current_allocation_correct_flag")
    shadow_correct_rate = _rate(rows, "low_soh_policy_shadow_allocation_correct_flag")
    current_missed_rate = _rate(rows, "current_missed_sales_risk_flag")
    shadow_missed_rate = _rate(rows, "low_soh_policy_shadow_missed_sales_risk_flag")
    current_capital_drag_rate = _rate(rows, "current_capital_drag_flag")
    shadow_capital_drag_rate = _rate(rows, "low_soh_policy_shadow_capital_drag_flag")
    current_ending_excess_rate = _rate(rows, "current_ending_excess_stock_flag")
    shadow_ending_excess_rate = _rate(rows, "low_soh_policy_shadow_ending_excess_stock_flag")
    reduce_current_correct_rate = _rate(rows, "current_allocation_correct_flag", reduce_mask)
    reduce_shadow_correct_rate = _rate(rows, "low_soh_policy_shadow_allocation_correct_flag", reduce_mask)
    hold_current_missed_rate = _rate(rows, "current_missed_sales_risk_flag", hold_or_low_soh_mask)
    low_soh_shadow_missed_rate = _rate(rows, "low_soh_policy_shadow_missed_sales_risk_flag", hold_or_low_soh_mask)

    rows_improved = int(_numeric_series(rows, "low_soh_policy_shadow_improved_flag").sum())
    rows_worsened = int(_numeric_series(rows, "low_soh_policy_shadow_worsened_flag").sum())
    units_added = _numeric_series(rows, "low_soh_policy_shadow_order_units").sub(
        _numeric_series(rows, "current_final_store_order_units")
    ).clip(lower=0.0)
    capital_added = units_added.mul(_numeric_series(rows, "allocation_unit_cost")).sum()

    promote = (
        shadow_correct_rate >= current_correct_rate + LOW_SOH_POLICY_TARGET_ALLOCATION_LIFT
        and current_missed_rate - shadow_missed_rate >= LOW_SOH_POLICY_TARGET_MISSED_SALES_DROP
        and shadow_capital_drag_rate <= LOW_SOH_POLICY_MAX_CAPITAL_DRAG_RATE
        and shadow_ending_excess_rate <= current_ending_excess_rate + LOW_SOH_POLICY_MAX_ENDING_EXCESS_RATE_DELTA
        and (not bool(reduce_mask.any()) or reduce_shadow_correct_rate >= LOW_SOH_POLICY_REDUCE_HOLDING_MIN_CORRECT_RATE)
        and hold_current_missed_rate - low_soh_shadow_missed_rate >= LOW_SOH_POLICY_HOLD_STOCK_MIN_MISSED_SALES_DROP
    )
    if promote:
        recommendation = "PROMOTE_LOW_SOH_POLICY_FROM_SHADOW"
        reason = (
            "Low-SOH shadow improves allocation correctness and missed-sales risk while keeping capital drag, ending stock, and REDUCE_HOLDING guardrails controlled."
        )
    elif shadow_correct_rate > current_correct_rate and shadow_missed_rate < current_missed_rate:
        recommendation = "KEEP_SHADOW_ONLY_AND_EXPAND_REPLAY"
        reason = (
            "Low-SOH shadow is directionally better, but one or more promotion guardrails or replay breadth requirements are not yet clean enough for production routing."
        )
    else:
        recommendation = "DO_NOT_PROMOTE_LOW_SOH_POLICY"
        reason = (
            "Low-SOH shadow does not improve the combined allocation score enough to justify changing governed executable orders."
        )

    return pd.DataFrame(
        [
            {
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "total_rows": int(len(rows.index)),
                "candidate_rows": int(candidate_mask.sum()),
                "current_allocation_correct_rate": round(current_correct_rate, 4),
                "shadow_allocation_correct_rate": round(shadow_correct_rate, 4),
                "current_missed_sales_risk_rate": round(current_missed_rate, 4),
                "shadow_missed_sales_risk_rate": round(shadow_missed_rate, 4),
                "current_overallocated_capital_drag_rate": round(current_capital_drag_rate, 4),
                "shadow_overallocated_capital_drag_rate": round(shadow_capital_drag_rate, 4),
                "current_ending_excess_stock_rate": round(current_ending_excess_rate, 4),
                "shadow_ending_excess_stock_rate": round(shadow_ending_excess_rate, 4),
                "reduce_holding_current_correct_rate": round(reduce_current_correct_rate, 4),
                "reduce_holding_shadow_correct_rate": round(reduce_shadow_correct_rate, 4),
                "hold_stock_current_missed_sales_risk_rate": round(hold_current_missed_rate, 4),
                "low_soh_shadow_missed_sales_risk_rate": round(low_soh_shadow_missed_rate, 4),
                "rows_improved": rows_improved,
                "rows_worsened": rows_worsened,
                "units_added_by_shadow": int(round(float(units_added.sum()))),
                "capital_added_by_shadow": round(float(capital_added), 2),
                "promote_policy_recommendation": recommendation,
                "promote_policy_reason": reason,
            }
        ]
    )


def _target_end_soh_details(rows: pd.DataFrame) -> pd.DataFrame:
    avg_daily = _numeric_series(rows, "avg_daily_units").clip(lower=0.0)
    target_raw = avg_daily.mul(30.0)
    target_final = pd.Series(np.maximum(2.0, target_raw), index=rows.index, dtype="float64")

    avg_daily_quality_label = pd.Series("ZERO_OR_UNKNOWN_DEMAND", index=rows.index, dtype="object")
    avg_daily_quality_label = avg_daily_quality_label.where(~avg_daily.gt(0.0), "LOW_DAILY_DEMAND")
    avg_daily_quality_label = avg_daily_quality_label.where(~avg_daily.ge(0.05), "NORMAL_DAILY_DEMAND")
    avg_daily_quality_label = avg_daily_quality_label.where(~avg_daily.ge(0.5), "HIGH_DAILY_DEMAND")

    confidence = pd.Series("LOW_BASELINE_CONFIDENCE", index=rows.index, dtype="object")
    confidence = confidence.where(~avg_daily.gt(0.0), "LOW_BASELINE_CONFIDENCE")
    confidence = confidence.where(~avg_daily.ge(0.05), "MEDIUM_BASELINE_CONFIDENCE")
    confidence = confidence.where(~avg_daily.ge(0.2), "HIGH_BASELINE_CONFIDENCE")

    adjust_reason = pd.Series("FALLBACK_TO_2_UNIT_FLOOR", index=rows.index, dtype="object")
    adjust_reason = adjust_reason.where(~avg_daily.gt(0.0), "LOW_DAILY_BASELINE_USE_2_UNIT_FLOOR")
    adjust_reason = adjust_reason.where(~target_raw.gt(2.0), "USE_30_DAY_SUPPLY_TARGET")

    return pd.DataFrame(
        {
            "target_end_soh_units_raw": target_raw.round(4),
            "target_end_soh_units_final": target_final.round(4),
            "target_end_soh_confidence_label": confidence,
            "target_end_soh_adjustment_reason": adjust_reason,
            "avg_daily_units_quality_label": avg_daily_quality_label,
        },
        index=rows.index,
    )


def _days_supply(ending_units: pd.Series, avg_daily_units: pd.Series) -> pd.Series:
    avg_daily = pd.to_numeric(avg_daily_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    ending = pd.to_numeric(ending_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    days = ending.divide(avg_daily.where(avg_daily.gt(0.0))).replace([np.inf, -np.inf], np.nan)
    fallback = pd.Series(np.where(ending.gt(0.0), 999.0, 0.0), index=ending.index, dtype="float64")
    return days.fillna(fallback)


def _days_supply_band(days_supply: pd.Series) -> pd.Series:
    days = pd.to_numeric(days_supply, errors="coerce").fillna(0.0).clip(lower=0.0)
    band = pd.Series("0-30_DAYS", index=days.index, dtype="object")
    band = band.where(~days.gt(30.0), "31-60_DAYS")
    band = band.where(~days.gt(60.0), "61-90_DAYS")
    band = band.where(~days.gt(90.0), "90_PLUS_DAYS")
    return band


def _target_excess_severity(
    *,
    excess_units: pd.Series,
    excess_capital: pd.Series,
    ending_soh: pd.Series,
    target_end_soh: pd.Series,
) -> pd.Series:
    excess_units_numeric = pd.to_numeric(excess_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    excess_capital_numeric = pd.to_numeric(excess_capital, errors="coerce").fillna(0.0).clip(lower=0.0)
    ending_numeric = pd.to_numeric(ending_soh, errors="coerce").fillna(0.0).clip(lower=0.0)
    target_numeric = pd.to_numeric(target_end_soh, errors="coerce").fillna(0.0).clip(lower=0.0)

    no_excess = excess_units_numeric.le(0.0)
    small_buffer = (
        (excess_units_numeric.le(1.0) & ending_numeric.le(np.maximum(3.0, target_numeric + 1.0)))
        | excess_capital_numeric.le(SMALL_OPERATING_BUFFER_CAPITAL)
    ) & ~no_excess
    severe_excess = (excess_units_numeric.ge(4.0) | excess_capital_numeric.ge(100.0)) & ~no_excess
    material_excess = (~no_excess) & (~small_buffer) & (~severe_excess)

    severity = pd.Series("NO_EXCESS", index=excess_units_numeric.index, dtype="object")
    severity = severity.where(~small_buffer, "SMALL_OPERATING_BUFFER_EXCESS")
    severity = severity.where(~material_excess, "MATERIAL_EXCESS")
    severity = severity.where(~severe_excess, "SEVERE_EXCESS")
    return severity


def _policy_economic_frame(
    *,
    rows: pd.DataFrame,
    policy_name: str,
    order_units: pd.Series,
    target_end_soh_units: pd.Series,
) -> pd.DataFrame:
    units = pd.to_numeric(order_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    projected_soh = _numeric_series(rows, "projected_SOH_at_promo_start").clip(lower=0.0)
    actual_units = _numeric_series(rows, "actual_units_sold").clip(lower=0.0)
    unit_cost = _numeric_series(rows, "allocation_unit_cost").clip(lower=0.0)
    avg_daily_units = _numeric_series(rows, "avg_daily_units").clip(lower=0.0)
    gross_profit_total = _numeric_series(rows, "estimated_gross_profit_after_priceline_fees")
    gross_profit_per_unit = _safe_ratio(gross_profit_total, actual_units)
    gross_profit_per_unit = gross_profit_per_unit.where(gross_profit_per_unit.notna(), _numeric_series(rows, "expected_gp_per_unit"))
    gross_profit_per_unit = gross_profit_per_unit.fillna(0.0)

    total_stock = projected_soh.add(units)
    ending_soh = total_stock.sub(actual_units)
    stockout = actual_units.gt(total_stock) | ending_soh.lt(0.0)
    units_needed_from_order = actual_units.sub(projected_soh).clip(lower=0.0)
    incremental_units_sold = pd.Series(np.minimum(units, units_needed_from_order), index=rows.index, dtype="float64")
    unneeded_units = units.sub(units_needed_from_order).clip(lower=0.0)
    excess_target_units = ending_soh.clip(lower=0.0).sub(target_end_soh_units).clip(lower=0.0)
    capital_at_risk = units.mul(unit_cost)
    excess_target_capital = excess_target_units.mul(unit_cost)
    target_excess_severity = _target_excess_severity(
        excess_units=excess_target_units,
        excess_capital=excess_target_capital,
        ending_soh=ending_soh,
        target_end_soh=target_end_soh_units,
    )
    target_excess_flag = target_excess_severity.isin({"MATERIAL_EXCESS", "SEVERE_EXCESS"}).astype(int)
    realized_gp_on_order_units = incremental_units_sold.mul(gross_profit_per_unit)
    net_cash_conversion_value = realized_gp_on_order_units.sub(excess_target_capital)
    cash_conversion_rate = _safe_ratio(net_cash_conversion_value, capital_at_risk).fillna(0.0)
    roi = _safe_ratio(realized_gp_on_order_units, capital_at_risk).fillna(0.0)
    correct = (~stockout & target_excess_severity.isin({"NO_EXCESS", "SMALL_OPERATING_BUFFER_EXCESS"})).astype(int)
    capital_free_success = units.le(0.0) & ~stockout & excess_target_units.le(0.0)
    negative_cash_conversion = capital_at_risk.gt(0.0) & net_cash_conversion_value.lt(0.0)
    false_success = units.gt(0.0) & ~stockout & target_excess_flag.eq(1)

    is_pl_policy = policy_name.upper().startswith("PL")
    mistake_label = pd.Series("BALANCED_ALLOCATION", index=rows.index, dtype="object")
    mistake_label = mistake_label.where(~capital_free_success, "CAPITAL_FREE_SUCCESS")
    mistake_label = mistake_label.where(~(units.le(0.0) & stockout), "MISSED_SALES_NO_ORDER")
    mistake_label = mistake_label.where(~(units.gt(0.0) & stockout), "UNDER_ALLOCATED_DEMAND")
    mistake_label = mistake_label.where(~(false_success & is_pl_policy), "PL_FALSE_SUCCESS_TARGET_EXCESS")
    mistake_label = mistake_label.where(~(false_success & (not is_pl_policy)), "TARGET_EXCESS_CAPITAL_DRAG")
    mistake_label = mistake_label.where(~negative_cash_conversion, "NEGATIVE_CASH_CONVERSION")

    return pd.DataFrame(
        {
            f"{policy_name}_allocation_units": units.round(0).astype(int),
            f"{policy_name}_total_stock_available_units": total_stock.round(4),
            f"{policy_name}_estimated_ending_soh_units": ending_soh.round(4),
            f"{policy_name}_ending_days_supply": _days_supply(ending_soh, avg_daily_units).round(4),
            f"{policy_name}_unneeded_units": unneeded_units.round(4),
            f"{policy_name}_excess_target_units": excess_target_units.round(4),
            f"{policy_name}_target_excess_severity": target_excess_severity,
            f"{policy_name}_target_excess_flag": target_excess_flag,
            f"{policy_name}_capital_at_risk": capital_at_risk.round(2),
            f"{policy_name}_excess_target_capital": excess_target_capital.round(2),
            f"{policy_name}_realized_gp_on_order_units": realized_gp_on_order_units.round(2),
            f"{policy_name}_net_cash_conversion_value": net_cash_conversion_value.round(2),
            f"{policy_name}_cash_conversion_rate": cash_conversion_rate.round(4),
            f"{policy_name}_roi": roi.round(4),
            f"{policy_name}_mistake_label": mistake_label,
            f"{policy_name}_allocation_correct_flag": correct,
            f"{policy_name}_capital_free_success_flag": capital_free_success.astype(int),
            f"{policy_name}_false_success_flag": false_success.astype(int),
            f"{policy_name}_negative_cash_conversion_flag": negative_cash_conversion.astype(int),
            f"{policy_name}_stockout_flag": stockout.astype(int),
        },
        index=rows.index,
    )


def _select_allocation_winners(comparison: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    winners: list[str] = []
    reasons: list[str] = []
    for _, row in comparison.iterrows():
        policy_scores: dict[str, tuple[int, float, float]] = {}
        for policy_name in ("pl", "ff_current", "ff_low_soh"):
            policy_scores[policy_name] = (
                int(row.get(f"{policy_name}_allocation_correct_flag", 0) or 0),
                float(row.get(f"{policy_name}_net_cash_conversion_value", 0.0) or 0.0),
                -float(row.get(f"{policy_name}_capital_at_risk", 0.0) or 0.0),
            )
        winner = max(policy_scores, key=policy_scores.get)
        winners.append(winner.upper())
        if winner == "ff_low_soh":
            reasons.append("FF low-SOH policy best balances correctness, cash conversion, and capital discipline.")
        elif winner == "ff_current":
            reasons.append("Current FF decision avoids incremental capital without losing allocation correctness.")
        else:
            reasons.append("PL allocation has the strongest row-level economic score after actual outcome review.")
    return pd.Series(winners, index=comparison.index, dtype="object"), pd.Series(reasons, index=comparison.index, dtype="object")


def _build_pl_vs_ff_allocation_mistake_comparison(rows: pd.DataFrame) -> pd.DataFrame:
    target_details = _target_end_soh_details(rows)
    target_end_soh = _numeric_series(target_details, "target_end_soh_units_final").clip(lower=0.0)
    current_ff_units = _numeric_series(rows, "current_final_store_order_units").clip(lower=0.0)
    stage11_low_soh_eligible = _numeric_series(rows, "low_soh_policy_production_eligible_flag").clip(lower=0.0)
    stage11_low_soh_units = _numeric_series(rows, "low_soh_policy_final_order_units").clip(lower=0.0)
    stage11_low_soh_units = stage11_low_soh_units.where(stage11_low_soh_eligible.gt(0.0), 0.0)
    shadow_low_soh_units = _numeric_series(rows, "low_soh_policy_shadow_order_units").clip(lower=0.0)
    if "shadow_policy_order_units" in rows.columns:
        shadow_low_soh_units = shadow_low_soh_units.where(
            shadow_low_soh_units.gt(0.0),
            _numeric_series(rows, "shadow_policy_order_units").clip(lower=0.0),
        )
    ff_low_soh_units = current_ff_units.where(stage11_low_soh_units.le(0.0), stage11_low_soh_units)
    ff_low_soh_units = ff_low_soh_units.where(stage11_low_soh_units.gt(0.0) | shadow_low_soh_units.le(0.0), shadow_low_soh_units)

    comparison = rows.loc[
        :,
        [
            "store_number",
            "promotion_id",
            "promotion_start_date",
            "promotion_name",
            "sku_number",
            "sku_description",
            "store_action_label",
            "current_soh",
            "actual_units_sold",
            "projected_SOH_at_promo_start",
            "avg_daily_units",
            "pack_size",
            "allocation_unit_cost",
            "promo_days",
        ],
    ].copy()
    comparison = pd.concat([comparison, target_details], axis=1)
    comparison["target_end_soh_units"] = _numeric_series(comparison, "target_end_soh_units_final").round(4)
    comparison["target_end_soh_basis"] = np.where(_numeric_series(comparison, "target_end_soh_units_raw").gt(2.0), "30_DAY_SUPPLY", "2_UNIT_FLOOR")
    comparison["low_soh_policy_production_eligible_flag"] = _numeric_series(rows, "low_soh_policy_production_eligible_flag").astype(int)

    comparison = pd.concat(
        [
            comparison,
            _policy_economic_frame(
                rows=rows,
                policy_name="pl",
                order_units=_numeric_series(rows, "pl_allocation_qty").clip(lower=0.0),
                target_end_soh_units=target_end_soh,
            ),
            _policy_economic_frame(
                rows=rows,
                policy_name="ff_current",
                order_units=current_ff_units,
                target_end_soh_units=target_end_soh,
            ),
            _policy_economic_frame(
                rows=rows,
                policy_name="ff_low_soh",
                order_units=ff_low_soh_units,
                target_end_soh_units=target_end_soh,
            ),
        ],
        axis=1,
    )
    comparison["ff_low_soh_incremental_units_vs_current"] = comparison["ff_low_soh_allocation_units"].sub(
        comparison["ff_current_allocation_units"]
    )
    comparison["ff_low_soh_net_cash_delta_vs_pl"] = comparison["ff_low_soh_net_cash_conversion_value"].sub(
        comparison["pl_net_cash_conversion_value"]
    ).round(2)
    comparison["ff_low_soh_capital_delta_vs_pl"] = comparison["ff_low_soh_capital_at_risk"].sub(
        comparison["pl_capital_at_risk"]
    ).round(2)
    comparison["ff_low_soh_correct_delta_vs_pl"] = comparison["ff_low_soh_allocation_correct_flag"].sub(
        comparison["pl_allocation_correct_flag"]
    )
    winners, reasons = _select_allocation_winners(comparison)
    comparison["allocation_winner"] = winners
    comparison["allocation_winner_reason"] = reasons
    comparison["days_supply_band_start"] = _days_supply_band(
        _days_supply(_numeric_series(comparison, "projected_SOH_at_promo_start"), _numeric_series(comparison, "avg_daily_units"))
    )
    comparison["days_supply_band_after_ff"] = _days_supply_band(_numeric_series(comparison, "ff_low_soh_ending_days_supply"))
    comparison["days_supply_band_after_pl"] = _days_supply_band(_numeric_series(comparison, "pl_ending_days_supply"))

    pl_units = _numeric_series(comparison, "pl_allocation_units").clip(lower=0.0)
    projected_soh = _numeric_series(comparison, "projected_SOH_at_promo_start").clip(lower=0.0)
    actual_units = _numeric_series(comparison, "actual_units_sold").clip(lower=0.0)
    target_end = _numeric_series(comparison, "target_end_soh_units_final").clip(lower=0.0)
    pl_excess_units = _numeric_series(comparison, "pl_excess_target_units").clip(lower=0.0)
    pl_excess_capital = _numeric_series(comparison, "pl_excess_target_capital").clip(lower=0.0)
    pl_negative_cash = _numeric_series(comparison, "pl_negative_cash_conversion_flag").gt(0.0)
    pl_stockout = _numeric_series(comparison, "pl_stockout_flag").gt(0.0)

    comparison["pl_allocated_units_sold_flag"] = (pl_units.gt(0.0) & actual_units.gt(0.0)).astype(int)
    comparison["pl_starting_soh_already_sufficient_flag"] = projected_soh.ge(actual_units).astype(int)
    comparison["pl_target_buffer_already_sufficient_flag"] = projected_soh.ge(np.maximum(actual_units, target_end)).astype(int)
    comparison["pl_allocation_economically_needed_flag"] = (projected_soh.lt(actual_units) | projected_soh.lt(target_end)).astype(int)
    comparison["pl_materially_reduced_missed_sales_risk_flag"] = (pl_units.gt(0.0) & ~pl_stockout & projected_soh.lt(actual_units)).astype(int)
    comparison["pl_false_success_flag"] = (
        pl_units.gt(0.0)
        & (
            comparison["pl_starting_soh_already_sufficient_flag"].eq(1)
            | comparison["pl_target_buffer_already_sufficient_flag"].eq(1)
        )
        & pl_excess_units.gt(0.0)
        & pl_excess_capital.gt(0.0)
        & comparison["pl_materially_reduced_missed_sales_risk_flag"].eq(0)
    ).astype(int)
    comparison["pl_false_success_reason"] = np.where(
        comparison["pl_false_success_flag"].eq(1),
        "PL allocated despite sufficient start SOH/target buffer and created excess capital without material demand-risk reduction.",
        "",
    )
    comparison["pl_false_success_capital_value"] = pl_excess_capital.where(comparison["pl_false_success_flag"].eq(1), 0.0).round(2)
    comparison["pl_false_success_units"] = pl_excess_units.where(comparison["pl_false_success_flag"].eq(1), 0.0).round(4)

    no_demand_alloc = pl_units.gt(0.0) & actual_units.le(0.0)
    soh_sufficient_alloc = pl_units.gt(0.0) & comparison["pl_starting_soh_already_sufficient_flag"].eq(1)
    target_excess_alloc = pl_units.gt(0.0) & _numeric_series(comparison, "pl_target_excess_flag").gt(0.0)
    over_insured = pl_units.gt(0.0) & pl_excess_units.gt(0.0) & comparison["pl_materially_reduced_missed_sales_risk_flag"].eq(0)
    good_alloc = (
        pl_units.gt(0.0)
        & comparison["pl_allocation_economically_needed_flag"].eq(1)
        & _numeric_series(comparison, "pl_target_excess_flag").le(0.0)
        & ~pl_negative_cash
        & ~pl_stockout
    )
    missed_low_soh = pl_units.le(0.0) & projected_soh.le(1.0) & actual_units.gt(projected_soh)
    true_no_demand_no_alloc = pl_units.le(0.0) & actual_units.le(0.0)
    pl_mistake = pd.Series("PL_UNCLEAR_REVIEW", index=comparison.index, dtype="object")
    pl_mistake = pl_mistake.where(~true_no_demand_no_alloc, "PL_TRUE_NO_DEMAND_NO_ALLOCATION")
    pl_mistake = pl_mistake.where(~missed_low_soh, "PL_MISSED_LOW_SOH_DEMAND")
    pl_mistake = pl_mistake.where(~good_alloc, "PL_GOOD_ALLOCATION")
    pl_mistake = pl_mistake.where(~over_insured, "PL_OVER_INSURED_AVAILABILITY")
    pl_mistake = pl_mistake.where(~target_excess_alloc, "PL_ALLOCATED_INTO_30_DAY_EXCESS")
    pl_mistake = pl_mistake.where(~soh_sufficient_alloc, "PL_ALLOCATED_WHEN_SOH_ALREADY_SUFFICIENT")
    pl_mistake = pl_mistake.where(~no_demand_alloc, "PL_ALLOCATED_NO_DEMAND")
    comparison["pl_mistake_label"] = pl_mistake
    comparison["pl_correct_flag"] = (pl_mistake.eq("PL_GOOD_ALLOCATION") | pl_mistake.eq("PL_TRUE_NO_DEMAND_NO_ALLOCATION")).astype(int)
    comparison["pl_allocation_correct_flag"] = comparison["pl_correct_flag"]
    comparison["pl_missed_low_soh_demand_flag"] = missed_low_soh.astype(int)
    comparison["pl_allocated_into_excess_flag"] = target_excess_alloc.astype(int)
    comparison["pl_allocated_when_soh_already_sufficient_flag"] = soh_sufficient_alloc.astype(int)

    ff_stockout = _numeric_series(comparison, "ff_low_soh_stockout_flag").gt(0.0)
    ff_target_excess_flag = _numeric_series(comparison, "ff_low_soh_target_excess_flag").gt(0.0)
    ff_negative_cash = _numeric_series(comparison, "ff_low_soh_negative_cash_conversion_flag").gt(0.0)
    pack_size = _numeric_series(comparison, "pack_size", default=1.0).clip(lower=1.0)
    avg_quality = _text_series(comparison, "avg_daily_units_quality_label").str.upper()
    low_soh_eligible = _numeric_series(comparison, "low_soh_policy_production_eligible_flag").gt(0.0)

    comparison["ff_missed_low_soh_demand_flag"] = (ff_stockout & projected_soh.le(1.0) & actual_units.gt(0.0)).astype(int)
    failure_type = pd.Series("REVIEW_REQUIRED", index=comparison.index, dtype="object")
    failure_reason = pd.Series("Review required before automatic change.", index=comparison.index, dtype="object")
    no_failure = _numeric_series(comparison, "ff_low_soh_allocation_correct_flag").gt(0.0)
    missed = comparison["ff_missed_low_soh_demand_flag"].eq(1)
    target_excess = ff_target_excess_flag
    neg_cash = ff_negative_cash
    pack_blocked = pack_size.gt(LOW_SOH_POLICY_MAX_PACK_SIZE_AUTO_ORDER) & low_soh_eligible.eq(0)
    avg_distortion = avg_quality.isin({"ZERO_OR_UNKNOWN_DEMAND", "LOW_DAILY_DEMAND"}) & target_excess
    weak_demand = avg_quality.eq("ZERO_OR_UNKNOWN_DEMAND") & _numeric_series(comparison, "ff_low_soh_allocation_units").gt(0.0) & actual_units.le(0.0)

    failure_type = failure_type.where(~pack_blocked, "PACK_MOQ_BLOCKED")
    failure_reason = failure_reason.where(~pack_blocked, "Pack or MOQ settings blocked a safe low-SOH auto-order.")
    failure_type = failure_type.where(~weak_demand, "WEAK_DEMAND_SIGNAL")
    failure_reason = failure_reason.where(~weak_demand, "Demand signal quality is weak for automatic low-SOH ordering.")
    failure_type = failure_type.where(~avg_distortion, "AVG_DAILY_UNITS_TARGET_DISTORTION")
    failure_reason = failure_reason.where(~avg_distortion, "Low daily-demand baseline distorted 30-day target interpretation.")
    failure_type = failure_type.where(~neg_cash, "NEGATIVE_CASH_CONVERSION")
    failure_reason = failure_reason.where(~neg_cash, "Net cash conversion turned negative for the FF low-SOH decision.")
    failure_type = failure_type.where(~target_excess, "TARGET_EXCESS")
    failure_reason = failure_reason.where(~target_excess, "FF low-SOH decision ended with material target excess stock.")
    failure_type = failure_type.where(~missed, "MISSED_DEMAND")
    failure_reason = failure_reason.where(~missed, "FF low-SOH decision missed real low-SOH demand.")
    failure_type = failure_type.where(~no_failure, "NO_SAFE_AUTO_FIX")
    failure_reason = failure_reason.where(~no_failure, "No failure detected; keep governed low-SOH decision.")

    safe_adjustment_units = pd.Series(0.0, index=comparison.index, dtype="float64")
    safe_adjustment_units = safe_adjustment_units.where(~target_excess, _numeric_series(comparison, "ff_low_soh_excess_target_units").clip(lower=0.0).clip(upper=1.0))
    safe_adjustment_units = safe_adjustment_units.where(~missed, np.minimum(LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS - _numeric_series(comparison, "ff_low_soh_allocation_units"), 1.0).clip(lower=0.0))
    safe_adjustment_capital = safe_adjustment_units.mul(_numeric_series(comparison, "allocation_unit_cost")).round(2)
    safe_auto = (
        failure_type.isin({"MISSED_DEMAND", "TARGET_EXCESS", "AVG_DAILY_UNITS_TARGET_DISTORTION"})
        & pack_size.le(LOW_SOH_POLICY_MAX_PACK_SIZE_AUTO_ORDER)
        & _numeric_series(comparison, "ff_low_soh_allocation_units").le(LOW_SOH_POLICY_MAX_AUTO_ORDER_UNITS)
    )
    adjustment_action = pd.Series("REVIEW_REQUIRED", index=comparison.index, dtype="object")
    adjustment_action = adjustment_action.where(~(safe_auto & failure_type.eq("MISSED_DEMAND")), "ADD_1_UNIT_IF_CAP_SAFE")
    adjustment_action = adjustment_action.where(~(safe_auto & failure_type.isin({"TARGET_EXCESS", "AVG_DAILY_UNITS_TARGET_DISTORTION"})), "TRIM_1_UNIT_SMALL_BUFFER")
    adjustment_action = adjustment_action.where(~no_failure, "NO_CHANGE")

    comparison["ff_target_excess_flag"] = ff_target_excess_flag.astype(int)
    comparison["ff_negative_cash_conversion_flag"] = ff_negative_cash.astype(int)
    comparison["ff_low_soh_failure_type"] = failure_type
    comparison["ff_low_soh_failure_reason"] = failure_reason
    comparison["ff_low_soh_safe_adjustment_units"] = safe_adjustment_units.round(4)
    comparison["ff_low_soh_safe_adjustment_capital"] = safe_adjustment_capital
    comparison["ff_low_soh_adjustment_action"] = adjustment_action
    comparison["ff_low_soh_safe_to_auto_fix_flag"] = safe_auto.astype(int)
    comparison["ff_mistake_label"] = comparison["ff_low_soh_failure_type"].where(
        _numeric_series(comparison, "ff_low_soh_allocation_correct_flag").le(0.0),
        "FF_GOOD_ALLOCATION",
    )
    comparison["ff_low_soh_policy_correct_flag"] = _numeric_series(comparison, "ff_low_soh_allocation_correct_flag").astype(int)
    comparison["ff_final_store_order_units"] = _numeric_series(comparison, "ff_current_allocation_units").astype(int)
    comparison["ff_low_soh_policy_order_units"] = _numeric_series(comparison, "ff_low_soh_allocation_units").astype(int)
    comparison["soh_at_promotion_advice"] = _numeric_series(comparison, "current_soh")
    return comparison


def _build_pl_vs_ff_allocation_scorecard(comparison: pd.DataFrame) -> pd.DataFrame:
    row_count = int(len(comparison.index))
    if row_count <= 0:
        return pd.DataFrame()
    promo_days = pd.to_numeric(comparison.get("promo_days", pd.Series(7.0, index=comparison.index)), errors="coerce").fillna(7.0).clip(lower=1.0)
    pl_correct_rate = float(comparison["pl_allocation_correct_flag"].mean())
    ff_current_correct_rate = float(comparison["ff_current_allocation_correct_flag"].mean())
    ff_low_soh_correct_rate = float(comparison["ff_low_soh_allocation_correct_flag"].mean())
    ff_target_excess_rate = float(_numeric_series(comparison, "ff_target_excess_flag").mean())
    ff_negative_cash_rate = float(comparison["ff_low_soh_negative_cash_conversion_flag"].mean())
    pl_false_success_rate = float(_numeric_series(comparison, "pl_false_success_flag").mean())
    net_cash_delta_vs_pl = float(comparison["ff_low_soh_net_cash_delta_vs_pl"].sum())
    annualised_net_cash_delta_vs_pl = net_cash_delta_vs_pl * (365.0 / float(promo_days.median()))
    ff_beats_pl_rate = float(comparison["allocation_winner"].eq("FF_LOW_SOH").mean())

    thresholds = {
        "ff_low_soh_correct_rate": ff_low_soh_correct_rate >= MODEL_PROGRESS_TARGET_CORRECT_RATE,
        "ff_low_soh_target_excess_rate": ff_target_excess_rate <= MODEL_PROGRESS_MAX_TARGET_EXCESS_RATE,
        "ff_low_soh_negative_cash_conversion_rate": ff_negative_cash_rate <= MODEL_PROGRESS_MAX_NEGATIVE_CASH_CONVERSION_RATE,
        "pl_false_success_rate": pl_false_success_rate <= MODEL_PROGRESS_MAX_PL_FALSE_SUCCESS_RATE,
        "net_cash_delta_vs_pl": net_cash_delta_vs_pl >= 0.0,
    }
    raw_score = 70.0
    raw_score += min(ff_low_soh_correct_rate, 1.0) * 18.0
    raw_score += max(0.0, ff_low_soh_correct_rate - pl_correct_rate) * 400.0
    raw_score += max(0.0, 1.0 - ff_target_excess_rate) * 4.0
    raw_score += max(0.0, 1.0 - ff_negative_cash_rate) * 4.0
    raw_score += max(0.0, ff_beats_pl_rate) * 4.0
    if net_cash_delta_vs_pl > 0.0:
        raw_score += 2.0
    all_thresholds_pass = all(thresholds.values())
    model_progress_score = min(raw_score, 100.0)
    if not all_thresholds_pass:
        model_progress_score = min(model_progress_score, MODEL_PROGRESS_TARGET_SCORE - 1.0)
    else:
        model_progress_score = max(model_progress_score, MODEL_PROGRESS_TARGET_SCORE)

    failed_thresholds = [metric_name for metric_name, passed in thresholds.items() if not passed]
    if all_thresholds_pass:
        label = "98_PLUS_PRODUCTION_READY"
        reason = "All correctness, target-stock, cash-conversion, and PL false-success thresholds pass."
        next_lift = "Maintain governed replay evidence and monitor drift."
    else:
        label = "BELOW_98_GOVERNED_PROGRESS"
        reason = "Score capped below 98 because one or more production evidence thresholds failed."
        next_lift = ";".join(failed_thresholds)

    return pd.DataFrame(
        [
            {
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "row_count": row_count,
                "pl_allocation_correct_rate": round(pl_correct_rate, 4),
                "ff_current_allocation_correct_rate": round(ff_current_correct_rate, 4),
                "ff_low_soh_allocation_correct_rate": round(ff_low_soh_correct_rate, 4),
                "ff_low_soh_correct_rate_delta_vs_pl": round(ff_low_soh_correct_rate - pl_correct_rate, 4),
                "ff_low_soh_correct_rate_delta_vs_current_ff": round(ff_low_soh_correct_rate - ff_current_correct_rate, 4),
                "pl_false_success_rate": round(pl_false_success_rate, 4),
                "capital_free_success_rate": round(float(_numeric_series(comparison, "ff_low_soh_capital_free_success_flag").mean()), 4),
                "ff_low_soh_target_excess_rate": round(ff_target_excess_rate, 4),
                "ff_low_soh_negative_cash_conversion_rate": round(ff_negative_cash_rate, 4),
                "ff_low_soh_beats_pl_rate": round(ff_beats_pl_rate, 4),
                "pl_capital_at_risk": round(float(comparison["pl_capital_at_risk"].sum()), 2),
                "ff_current_capital_at_risk": round(float(comparison["ff_current_capital_at_risk"].sum()), 2),
                "ff_low_soh_capital_at_risk": round(float(comparison["ff_low_soh_capital_at_risk"].sum()), 2),
                "net_cash_delta_vs_pl": round(net_cash_delta_vs_pl, 2),
                "annualised_net_cash_delta_vs_pl": round(annualised_net_cash_delta_vs_pl, 2),
                "all_98_thresholds_pass_flag": int(all_thresholds_pass),
                "model_progress_score_100": round(model_progress_score, 2),
                "model_progress_label": label,
                "model_progress_reason": reason,
                "next_lift_to_98": next_lift,
            }
        ]
    )


def _build_score_98_blocker_diagnostic(comparison: pd.DataFrame) -> pd.DataFrame:
    blocker_type = pd.Series("", index=comparison.index, dtype="object")
    blocker_reason = pd.Series("", index=comparison.index, dtype="object")
    proposed_fix = pd.Series("", index=comparison.index, dtype="object")
    safe_auto = pd.Series(0, index=comparison.index, dtype="int64")

    priority = [
        ("ff_negative_cash_conversion_flag", "FF_NEGATIVE_CASH_CONVERSION", "FF low-SOH net cash conversion is negative.", "trim_or_hold_low_soh_order"),
        ("ff_missed_low_soh_demand_flag", "FF_MISSED_LOW_SOH_DEMAND", "FF low-SOH decision missed low-SOH demand.", "add_1_unit_if_guardrails_pass"),
        ("ff_target_excess_flag", "FF_TARGET_EXCESS", "FF low-SOH decision ends with material target excess.", "trim_small_buffer_or_review"),
        ("pl_false_success_flag", "PL_FALSE_SUCCESS", "PL allocation was not economically needed.", "tighten_pl_false_success_rules"),
        ("pl_allocated_into_excess_flag", "PL_ALLOCATED_INTO_EXCESS", "PL allocation pushed stock into excess above target.", "explicit_target_excess_penalty"),
        ("pl_allocated_when_soh_already_sufficient_flag", "PL_ALLOCATED_WHEN_SOH_SUFFICIENT", "PL allocated despite sufficient SOH.", "explicit_soh_sufficient_penalty"),
    ]
    for flag, label, reason, fix in priority:
        mask = _numeric_series(comparison, flag).gt(0.0) & blocker_type.eq("")
        blocker_type = blocker_type.where(~mask, label)
        blocker_reason = blocker_reason.where(~mask, reason)
        proposed_fix = proposed_fix.where(~mask, fix)
        safe_auto = safe_auto.where(~mask, _numeric_series(comparison, "ff_low_soh_safe_to_auto_fix_flag").astype(int))

    unresolved = blocker_type.eq("")
    blocker_type = blocker_type.where(~unresolved, "UNCLEAR_REVIEW")
    blocker_reason = blocker_reason.where(~unresolved, "Row did not map cleanly to a blocker class.")
    proposed_fix = proposed_fix.where(~unresolved, "manual_review")

    out = comparison.loc[
        :,
        [
            "store_number",
            "promotion_id",
            "promotion_name",
            "sku_number",
            "sku_description",
            "soh_at_promotion_advice",
            "avg_daily_units",
            "target_end_soh_units_final",
            "actual_units_sold",
            "pl_allocation_units",
            "ff_final_store_order_units",
            "ff_low_soh_policy_order_units",
            "pl_mistake_label",
            "ff_mistake_label",
            "pl_correct_flag",
            "ff_low_soh_policy_correct_flag",
            "pl_false_success_flag",
            "ff_target_excess_flag",
            "ff_negative_cash_conversion_flag",
            "ff_missed_low_soh_demand_flag",
        ],
    ].copy()
    out = out.rename(columns={"target_end_soh_units_final": "target_end_soh_units", "pl_allocation_units": "pl_allocation_qty"})
    out["blocker_type"] = blocker_type
    out["blocker_reason"] = blocker_reason
    out["proposed_fix_type"] = proposed_fix
    out["safe_to_auto_fix_flag"] = safe_auto.astype(int)
    mask = (
        _numeric_series(out, "pl_false_success_flag").gt(0.0)
        | _numeric_series(out, "ff_target_excess_flag").gt(0.0)
        | _numeric_series(out, "ff_negative_cash_conversion_flag").gt(0.0)
        | _numeric_series(out, "ff_missed_low_soh_demand_flag").gt(0.0)
        | out["blocker_type"].eq("UNCLEAR_REVIEW")
    )
    return out.loc[mask].reset_index(drop=True)


def _build_model_98_readiness_scorecard(
    *,
    comparison: pd.DataFrame,
    scorecard: pd.DataFrame,
    reason_quality_issue_count: int,
    reduce_holding_current_correct_rate: float,
) -> pd.DataFrame:
    if scorecard.empty:
        return pd.DataFrame()
    score = scorecard.iloc[0]
    ff_correct = float(score.get("ff_low_soh_allocation_correct_rate", 0.0) or 0.0)
    pl_correct = float(score.get("pl_allocation_correct_rate", 0.0) or 0.0)
    target_excess_rate = float(score.get("ff_low_soh_target_excess_rate", 0.0) or 0.0)
    neg_cash_rate = float(score.get("ff_low_soh_negative_cash_conversion_rate", 0.0) or 0.0)
    pl_false = float(score.get("pl_false_success_rate", 0.0) or 0.0)
    annualised = float(score.get("annualised_net_cash_delta_vs_pl", 0.0) or 0.0)
    ff_capital_drag_rate = float(_numeric_series(comparison, "ff_negative_cash_conversion_flag").mean())
    ff_missed_rate = float(_numeric_series(comparison, "ff_missed_low_soh_demand_flag").mean())

    rows = [
        ("economic_correctness", ff_correct - pl_correct, 0.03, ff_correct > pl_correct, 15, "FF low-SOH must clearly beat PL."),
        ("missed_sales_risk_control", 1.0 - ff_missed_rate, 0.90, ff_missed_rate <= 0.10, 10, "Keep missed-demand failures controlled."),
        ("target_excess_control", 1.0 - target_excess_rate, 0.98, target_excess_rate <= MODEL_PROGRESS_MAX_TARGET_EXCESS_RATE, 15, "Keep material target excess rare."),
        ("capital_drag_control", 1.0 - ff_capital_drag_rate, 0.95, ff_capital_drag_rate <= LOW_SOH_POLICY_MAX_CAPITAL_DRAG_RATE, 10, "Capital drag must stay below 5%."),
        ("cash_conversion_quality", 1.0 - neg_cash_rate, 0.98, neg_cash_rate <= MODEL_PROGRESS_MAX_NEGATIVE_CASH_CONVERSION_RATE, 10, "Negative cash conversion must remain rare."),
        ("pl_false_success_detection", pl_false, MODEL_PROGRESS_MAX_PL_FALSE_SUCCESS_RATE, pl_false <= MODEL_PROGRESS_MAX_PL_FALSE_SUCCESS_RATE, 10, "PL false-success should be explicit and reduced."),
        ("reason_quality", float(reason_quality_issue_count), 0.0, reason_quality_issue_count == 0, 10, "Reason quality issues must remain zero."),
        ("governance_safety", reduce_holding_current_correct_rate, 0.95, reduce_holding_current_correct_rate >= 0.95, 10, "REDUCE_HOLDING correctness must remain >=95%."),
        ("annualised_value", annualised, 0.0, annualised > 0.0, 5, "Annualised value versus PL must remain positive."),
    ]
    scored_rows: list[dict[str, object]] = []
    total_points = 0
    earned_points = 0
    for metric_name, current_value, target_value, passed, points, reason_text in rows:
        total_points += points
        pts = points if passed else 0
        earned_points += pts
        scored_rows.append(
            {
                "metric_name": metric_name,
                "current_value": round(float(current_value), 4),
                "target_value": round(float(target_value), 4),
                "pass_flag": int(bool(passed)),
                "points_available": points,
                "points_earned": pts,
                "reason": reason_text,
                "next_action": "none" if passed else "improve_threshold_metric",
            }
        )
    overall_score = round((earned_points / max(total_points, 1)) * 100.0, 2)
    scored_rows.append(
        {
            "metric_name": "overall_score",
            "current_value": overall_score,
            "target_value": MODEL_PROGRESS_TARGET_SCORE,
            "pass_flag": int(overall_score >= MODEL_PROGRESS_TARGET_SCORE),
            "points_available": total_points,
            "points_earned": earned_points,
            "reason": "Composite readiness score from governed blocker metrics.",
            "next_action": "promote_when_all_pass" if overall_score >= MODEL_PROGRESS_TARGET_SCORE else "close_remaining_blockers",
        }
    )
    return pd.DataFrame(scored_rows)


def _build_executive_premeeting_summary(scorecard: pd.DataFrame, readiness: pd.DataFrame) -> pd.DataFrame:
    if scorecard.empty:
        return pd.DataFrame()
    score = scorecard.iloc[0]
    failures = readiness.loc[
        readiness["pass_flag"].eq(0) & readiness["metric_name"].ne("overall_score"),
        "metric_name",
    ].tolist() if not readiness.empty else []
    remaining_limitation = ", ".join(failures[:3]) if failures else "No critical blocker remains."
    next_improvement = (
        "Reduce material target-excess and PL false-success rows while lifting FF low-SOH correctness under guardrails."
        if failures
        else "Maintain governed replay safety and monitor drift weekly."
    )
    return pd.DataFrame(
        [
            {
                "model_progress_score_100": float(score.get("model_progress_score_100", 0.0) or 0.0),
                "model_progress_label": str(score.get("model_progress_label", "UNKNOWN")),
                "core_message": "Fourth Form is now measuring whether stock was economically needed, not just whether allocated stock sold.",
                "what_changed": "Low-SOH governed decisions now classify target excess severity, PL false-success, and FF failure causes explicitly.",
                "why_it_matters": "This prevents false wins that look sold-through but still create avoidable capital drag.",
                "proof_point_1": f"FF low-SOH economic correctness {float(score.get('ff_low_soh_allocation_correct_rate', 0.0) or 0.0):.4f} vs PL {float(score.get('pl_allocation_correct_rate', 0.0) or 0.0):.4f}.",
                "proof_point_2": f"Net cash delta vs PL is ${float(score.get('net_cash_delta_vs_pl', 0.0) or 0.0):,.2f}.",
                "proof_point_3": f"Annualised value remains positive at ${float(score.get('annualised_net_cash_delta_vs_pl', 0.0) or 0.0):,.2f}.",
                "remaining_limitation": remaining_limitation,
                "next_improvement": next_improvement,
                "meeting_talk_track": "Fourth Form improved economic correctness while staying governed. We still need to cut residual target-excess and PL false-success rows to move from 97 to 98+ without relaxing capital discipline.",
            }
        ]
    )


def _build_capital_reallocation_waterfall(comparison: pd.DataFrame, scorecard: pd.DataFrame) -> pd.DataFrame:
    annualised_delta = float(scorecard.iloc[0].get("annualised_net_cash_delta_vs_pl", 0.0)) if not scorecard.empty else 0.0
    rows = [
        {
            "waterfall_step": "01_pl_allocated_capital",
            "description": "Capital accepted through PL allocation.",
            "capital_value": round(float(comparison["pl_capital_at_risk"].sum()), 2),
        },
        {
            "waterfall_step": "02_remove_pl_target_excess_capital",
            "description": "Capital tied up above the governed max(2 units, 30 days supply) end-SOH target.",
            "capital_value": round(-float(comparison["pl_excess_target_capital"].sum()), 2),
        },
        {
            "waterfall_step": "03_current_ff_allocated_capital",
            "description": "Current FF governed final-order capital.",
            "capital_value": round(float(comparison["ff_current_capital_at_risk"].sum()), 2),
        },
        {
            "waterfall_step": "04_low_soh_guarded_capital",
            "description": "FF low-SOH governed capital after caps and blockers.",
            "capital_value": round(float(comparison["ff_low_soh_capital_at_risk"].sum()), 2),
        },
        {
            "waterfall_step": "05_ff_low_soh_net_cash_delta_vs_pl",
            "description": "Actual-outcome net cash conversion delta versus PL allocation.",
            "capital_value": round(float(comparison["ff_low_soh_net_cash_delta_vs_pl"].sum()), 2),
        },
        {
            "waterfall_step": "06_annualised_net_cash_delta_vs_pl",
            "description": "Annualised effect from the reviewed promotion period.",
            "capital_value": round(annualised_delta, 2),
        },
    ]
    return pd.DataFrame(rows)


def _group_dimension_labels(rows: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "store_action_label": _text_series(rows, "store_action_label").replace("", "unavailable"),
        "department": _text_series(rows, "department").replace("", "unavailable"),
        "category": _text_series(rows, "category").replace("", "unavailable"),
        "catalogue_position": _text_series(rows, "catalogue_position").replace("", "unavailable"),
        "promo_type": _text_series(rows, "promo_type").replace("", "unavailable"),
        "customer_offer": _text_series(rows, "customer_offer").replace("", "unavailable"),
        "discount_band": _text_series(rows, "discount_band").replace("", "unavailable"),
        "current_soh_band": _text_series(rows, "current_soh_band").replace("", "unavailable"),
        "projected_SOH_at_promo_start_band": _text_series(rows, "projected_soh_band").replace("", "unavailable"),
        "actual_sales_band": _text_series(rows, "actual_sales_band").replace("", "unavailable"),
        "avg_8_wk_unit_sales_band": _text_series(rows, "avg_8_wk_unit_sales_band").replace("", "unavailable"),
        "low_velocity_flag": _numeric_series(rows, "low_velocity_flag").astype(int).astype(str),
        "never_sold_in_promo_flag": _numeric_series(rows, "never_sold_in_promo_flag").astype(int).astype(str),
        "supplier_allocation_band": _text_series(rows, "supplier_allocation_band").replace("", "unavailable"),
        "pack_size_band": _text_series(rows, "pack_size_band").replace("", "unavailable"),
        "price_band": _text_series(rows, "price_band").replace("", "unavailable"),
        "margin_band": _text_series(rows, "margin_band").replace("", "unavailable"),
    }


def _build_group_summary(rows: pd.DataFrame) -> pd.DataFrame:
    summaries: list[dict[str, object]] = []
    for dimension_name, labels in _group_dimension_labels(rows).items():
        grouped = rows.assign(_segment_value=labels.values).groupby("_segment_value", dropna=False)
        for segment_value, group in grouped:
            row_count = int(len(group.index))
            if row_count < MIN_SEGMENT_ROWS:
                continue
            allocation_correct_rate = float(group["allocation_correct_flag"].mean())
            missed_sales_risk_rate = float(group["current_missed_sales_risk_flag"].mean())
            capital_drag_rate = float(group["current_capital_drag_flag"].mean())
            if missed_sales_risk_rate >= 0.20 and capital_drag_rate >= 0.20:
                blind_spot_class = "BOTH_SIDES_UNSTABLE"
            elif missed_sales_risk_rate >= 0.20:
                blind_spot_class = "UNDER_PROTECTING_DEMAND"
            elif capital_drag_rate >= 0.20:
                blind_spot_class = "OVER_ALLOCATING_CAPITAL"
            else:
                blind_spot_class = "BALANCED_OR_INCONCLUSIVE"
            summaries.append(
                {
                    "segment_dimension": dimension_name,
                    "segment_value": str(segment_value),
                    "row_count": row_count,
                    "allocation_correct_rate": round(allocation_correct_rate, 4),
                    "shadow_allocation_correct_rate": round(float(group["shadow_allocation_correct_flag"].mean()), 4),
                    "missed_sales_risk_rate": round(missed_sales_risk_rate, 4),
                    "overallocated_capital_drag_rate": round(capital_drag_rate, 4),
                    "oos_proxy_rate": round(float(group["current_oos_proxy_flag"].mean()), 4),
                    "ending_excess_stock_rate": round(float(group["current_ending_excess_stock_flag"].mean()), 4),
                    "safe_no_order_rate": round(float(group["allocation_outcome_label"].eq("SAFE_NO_ORDER").mean()), 4),
                    "average_projected_gap_units": round(float(group["projected_stock_gap_units_raw"].mean()), 4),
                    "average_actual_gap_units": round(float(group["actual_stock_gap_units"].mean()), 4),
                    "average_projected_gap_error_units": round(float(group["projected_gap_error_units"].mean()), 4),
                    "gap_overstated_rate": round(float(group["projected_gap_bias_label"].eq("GAP_OVERSTATED").mean()), 4),
                    "gap_understated_rate": round(float(group["projected_gap_bias_label"].eq("GAP_UNDERSTATED").mean()), 4),
                    "gap_correct_rate": round(float(group["projected_gap_bias_label"].eq("GAP_CORRECT").mean()), 4),
                    "actual_units_sold_total": round(float(group["actual_units_sold"].sum()), 4),
                    "current_estimated_ending_soh_mean": round(float(group["current_estimated_stock_left_after_promo"].mean()), 4),
                    "capital_left_unsold_total": round(float(group["capital_left_in_unsold_store_allocation"].sum()), 4),
                    "gross_profit_after_fees_total": round(float(group["estimated_gross_profit_after_priceline_fees"].sum()), 4),
                    "current_risk_reward_ratio_mean": round(float(group["current_risk_reward_ratio"].mean()), 4),
                    "shadow_risk_reward_ratio_mean": round(float(group["shadow_risk_reward_ratio"].mean()), 4),
                    "blind_spot_class": blind_spot_class,
                    "blind_spot_priority_score": round(
                        ((1.0 - allocation_correct_rate) * math.log1p(row_count)) + missed_sales_risk_rate + capital_drag_rate,
                        4,
                    ),
                }
            )
    if not summaries:
        return pd.DataFrame(
            columns=[
                "segment_dimension",
                "segment_value",
                "row_count",
                "allocation_correct_rate",
                "shadow_allocation_correct_rate",
                "missed_sales_risk_rate",
                "overallocated_capital_drag_rate",
                "oos_proxy_rate",
                "ending_excess_stock_rate",
                "safe_no_order_rate",
                "average_projected_gap_units",
                "average_actual_gap_units",
                "average_projected_gap_error_units",
                "gap_overstated_rate",
                "gap_understated_rate",
                "gap_correct_rate",
                "actual_units_sold_total",
                "current_estimated_ending_soh_mean",
                "capital_left_unsold_total",
                "gross_profit_after_fees_total",
                "current_risk_reward_ratio_mean",
                "shadow_risk_reward_ratio_mean",
                "blind_spot_class",
                "blind_spot_priority_score",
            ]
        )
    summary_frame = pd.DataFrame(summaries)
    return summary_frame.sort_values(
        by=["blind_spot_priority_score", "row_count"],
        ascending=[False, False],
        kind="mergesort",
    ).reset_index(drop=True)


def build_store_allocation_actual_outcome_backtest(
    *,
    stage11_diagnostic_frame: pd.DataFrame,
    stage11_master_frame: pd.DataFrame,
    actual_review_frame: pd.DataFrame,
    max_unmatched_rows: int = DEFAULT_MAX_UNMATCHED_ROWS,
    max_unmatched_rate: float = DEFAULT_MAX_UNMATCHED_RATE,
) -> StoreAllocationActualOutcomeResult:
    stage11 = _prepare_stage11_frames(
        stage11_diagnostic_frame=stage11_diagnostic_frame,
        stage11_master_frame=stage11_master_frame,
        max_unmatched_rows=max_unmatched_rows,
        max_unmatched_rate=max_unmatched_rate,
    )
    actual = _prepare_actual_review_frame(actual_review_frame)
    joined = _join_stage11_to_actual(
        stage11_frame=stage11,
        actual_review_frame=actual,
        max_unmatched_rows=max_unmatched_rows,
        max_unmatched_rate=max_unmatched_rate,
    )
    rows = _compute_row_frame(joined)
    summary_frame = pd.DataFrame([_summarize_rates(rows)])
    low_soh_protection_shadow_summary_frame = _summarize_low_soh_policy_shadow(rows)
    pl_vs_ff_allocation_mistake_comparison_frame = _build_pl_vs_ff_allocation_mistake_comparison(rows)
    pl_vs_ff_allocation_scorecard_frame = _build_pl_vs_ff_allocation_scorecard(
        pl_vs_ff_allocation_mistake_comparison_frame
    )
    score_98_blocker_diagnostic_frame = _build_score_98_blocker_diagnostic(
        pl_vs_ff_allocation_mistake_comparison_frame
    )
    reduce_holding_mask = _text_series(rows, "store_action_label").str.upper().eq("REDUCE_HOLDING")
    reduce_holding_current_correct_rate = (
        float(_numeric_series(rows.loc[reduce_holding_mask], "current_allocation_correct_flag").mean())
        if bool(reduce_holding_mask.any())
        else 1.0
    )
    reason_quality_issue_count = int(_numeric_series(rows, "reason_quality_issue_flag").sum())
    model_98_readiness_scorecard_frame = _build_model_98_readiness_scorecard(
        comparison=pl_vs_ff_allocation_mistake_comparison_frame,
        scorecard=pl_vs_ff_allocation_scorecard_frame,
        reason_quality_issue_count=reason_quality_issue_count,
        reduce_holding_current_correct_rate=reduce_holding_current_correct_rate,
    )
    executive_premeeting_summary_frame = _build_executive_premeeting_summary(
        pl_vs_ff_allocation_scorecard_frame,
        model_98_readiness_scorecard_frame,
    )
    capital_reallocation_waterfall_frame = _build_capital_reallocation_waterfall(
        pl_vs_ff_allocation_mistake_comparison_frame,
        pl_vs_ff_allocation_scorecard_frame,
    )
    gap_accuracy_frame = rows.loc[
        :,
        [
            "store_number",
            "promotion_start_date",
            "promotion_name",
            "sku_number",
            "sku_description",
            "store_action_label",
            "raw_model_order_units",
            "final_store_order_units",
            "projected_SOH_at_promo_start",
            "floor_units_required",
            "expected_promo_demand",
            "available_to_sell_before_floor",
            "projected_stock_gap_units_raw",
            "actual_stock_gap_units",
            "projected_gap_error_units",
            "projected_gap_abs_error_units",
            "projected_gap_direction",
            "projected_gap_bias_label",
            "projected_gap_material_tolerance_units",
            "projected_gap_material_bias_flag",
            "projected_gap_understated_material_flag",
            "projected_gap_overstated_material_flag",
            "low_soh_gap_underprotection_flag",
            "hidden_demand_underprotection_flag",
            "stock_gap_decision_blind_spot_label",
            "actual_units_sold",
            "allocation_outcome_label",
            "allocation_correct_flag",
        ],
    ].copy()
    group_summary = _build_group_summary(rows)
    gap_bias_by_segment_frame = group_summary.loc[
        :,
        [
            "segment_dimension",
            "segment_value",
            "row_count",
            "average_projected_gap_units",
            "average_actual_gap_units",
            "average_projected_gap_error_units",
            "gap_overstated_rate",
            "gap_understated_rate",
            "gap_correct_rate",
            "allocation_correct_rate",
            "missed_sales_risk_rate",
            "overallocated_capital_drag_rate",
        ],
    ].copy()
    blind_spot_summary_frame = group_summary.copy()
    shadow_comparison_frame = rows.loc[
        :,
        [
            "store_number",
            "promotion_start_date",
            "promotion_name",
            "sku_number",
            "sku_description",
            "store_action_label",
            "raw_model_order_units",
            "final_store_order_units",
            "current_final_store_order_units",
            "low_soh_policy_shadow_order_units",
            "low_soh_policy_shadow_label",
            "low_soh_policy_shadow_outcome_label",
            "current_allocation_correct_flag",
            "low_soh_policy_shadow_allocation_correct_flag",
            "current_missed_sales_risk_flag",
            "low_soh_policy_shadow_missed_sales_risk_flag",
            "current_capital_drag_flag",
            "low_soh_policy_shadow_capital_drag_flag",
            "current_ending_excess_stock_flag",
            "low_soh_policy_shadow_ending_excess_stock_flag",
            "projected_stock_gap_units_raw",
            "projected_stock_gap_units_calibrated_shadow",
            "projected_stock_gap_calibration_factor",
            "projected_stock_gap_calibration_reason",
            "shadow_gap_quantile_name",
            "shadow_rounding_class",
            "shadow_final_store_order_units",
            "actual_units_sold",
            "current_allocation_outcome_label",
            "shadow_allocation_outcome_label",
            "shadow_allocation_correct_flag",
            "shadow_missed_sales_risk_flag",
            "shadow_capital_drag_flag",
            "current_expected_gp",
            "shadow_expected_gp",
            "current_capital_at_risk",
            "shadow_capital_at_risk",
            "current_risk_reward_ratio",
            "shadow_risk_reward_ratio",
            "current_estimated_stock_left_after_promo",
            "shadow_estimated_stock_left_after_promo",
            "shadow_improves_outcome_flag",
        ],
    ].copy()
    low_soh_protection_shadow_audit_frame = rows.loc[
        :,
        [
            "store_number",
            "promotion_id",
            "promotion_name",
            "promotion_start_date",
            "promotion_end_date",
            "sku_number",
            "sku_description",
            "store_action_label",
            "store_action_label_v2",
            "current_soh",
            "projected_SOH_at_promo_start",
            "floor_units_required",
            "expected_promo_demand",
            "available_to_sell_before_floor",
            "actual_units_sold",
            "estimated_stock_left_after_promo",
            "raw_model_order_units",
            "final_store_order_units",
            "low_soh_protection_candidate_flag",
            "low_soh_protection_score",
            "low_soh_policy_shadow_order_units",
            "low_soh_policy_shadow_label",
            "low_soh_protection_reason",
            "low_soh_protection_decision",
            "low_soh_protection_shadow_order_units",
            "low_soh_protection_final_order_units",
            "low_soh_protection_cap_reason",
            "low_soh_protection_expected_value",
            "low_soh_protection_capital_at_risk",
            "current_allocation_correct_flag",
            "low_soh_policy_shadow_allocation_correct_flag",
            "current_missed_sales_risk_flag",
            "low_soh_policy_shadow_missed_sales_risk_flag",
            "current_capital_drag_flag",
            "low_soh_policy_shadow_capital_drag_flag",
            "current_ending_excess_stock_flag",
            "low_soh_policy_shadow_ending_excess_stock_flag",
            "projected_gap_understated_material_flag",
            "projected_gap_overstated_material_flag",
            "low_soh_gap_underprotection_flag",
            "hidden_demand_underprotection_flag",
            "stock_gap_decision_blind_spot_label",
            "promote_candidate_flag",
            "promote_blocker_reason",
        ],
    ].copy()
    reason_quality_audit_frame = rows.loc[
        :,
        [
            "store_number",
            "promotion_start_date",
            "promotion_name",
            "sku_number",
            "store_action_label",
            "order_reconciliation_reason",
            "projected_SOH_at_promo_start",
            "floor_units_required",
            "expected_promo_demand",
            "available_to_sell_before_floor",
            "floor_protection_claim_flag",
            "current_floor_protected_flag",
            "reason_quality_issue_flag",
            "reason_quality_issue_class",
            "reason_quality_recommended_text",
        ],
    ].copy()
    return StoreAllocationActualOutcomeResult(
        rows_frame=rows,
        summary_frame=summary_frame,
        gap_accuracy_frame=gap_accuracy_frame,
        gap_bias_by_segment_frame=gap_bias_by_segment_frame,
        blind_spot_summary_frame=blind_spot_summary_frame,
        shadow_comparison_frame=shadow_comparison_frame,
        reason_quality_audit_frame=reason_quality_audit_frame,
        low_soh_protection_shadow_audit_frame=low_soh_protection_shadow_audit_frame,
        low_soh_protection_shadow_summary_frame=low_soh_protection_shadow_summary_frame,
        pl_vs_ff_allocation_mistake_comparison_frame=pl_vs_ff_allocation_mistake_comparison_frame,
        pl_vs_ff_allocation_scorecard_frame=pl_vs_ff_allocation_scorecard_frame,
        capital_reallocation_waterfall_frame=capital_reallocation_waterfall_frame,
        score_98_blocker_diagnostic_frame=score_98_blocker_diagnostic_frame,
        model_98_readiness_scorecard_frame=model_98_readiness_scorecard_frame,
        executive_premeeting_summary_frame=executive_premeeting_summary_frame,
    )


def write_store_allocation_actual_outcome_backtest(
    *,
    stage11_diagnostic_csv_path: str | Path,
    stage11_master_csv_path: str | Path,
    actual_review_csv_path: str | Path,
    output_root: str | Path,
    run_id: str | None = None,
    max_unmatched_rows: int = DEFAULT_MAX_UNMATCHED_ROWS,
    max_unmatched_rate: float = DEFAULT_MAX_UNMATCHED_RATE,
) -> StoreAllocationActualOutcomeArtifacts:
    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)

    stage11_diagnostic_frame = _read_csv(stage11_diagnostic_csv_path)
    stage11_master_frame = _read_csv(stage11_master_csv_path)
    actual_review_frame = _read_csv(actual_review_csv_path)
    manifest = build_input_source_manifest(
        run_id=run_id or output_path.name or "store_allocation_actual_outcome_backtest",
        feature_inspection_csv_path=stage11_diagnostic_csv_path,
        feature_inspection_frame=stage11_diagnostic_frame,
        allocation_report_csv_path=stage11_master_csv_path,
        allocation_report_frame=stage11_master_frame,
        actual_review_csv_path_requested=actual_review_csv_path,
        actual_review_csv_path_used=actual_review_csv_path,
        actual_review_source_status="EXACT_REQUESTED_FILE_USED",
        actual_review_frame=actual_review_frame,
    )
    if certification_failed(manifest):
        raise StoreAllocationActualOutcomeBacktestError(str(manifest["source_certification_reason"]))

    result = build_store_allocation_actual_outcome_backtest(
        stage11_diagnostic_frame=stage11_diagnostic_frame,
        stage11_master_frame=stage11_master_frame,
        actual_review_frame=actual_review_frame,
        max_unmatched_rows=max_unmatched_rows,
        max_unmatched_rate=max_unmatched_rate,
    )

    rows_csv_path = output_path / "store_allocation_actual_outcome_backtest.csv"
    summary_csv_path = output_path / "store_allocation_actual_outcome_summary.csv"
    gap_accuracy_csv_path = output_path / "projected_stock_gap_accuracy.csv"
    gap_bias_by_segment_csv_path = output_path / "projected_stock_gap_bias_by_segment.csv"
    blind_spot_summary_csv_path = output_path / "allocation_blind_spot_summary.csv"
    shadow_comparison_csv_path = output_path / "shadow_gap_calibration_comparison.csv"
    reason_quality_audit_csv_path = output_path / "store_action_reason_quality_audit.csv"
    low_soh_protection_shadow_audit_csv_path = output_path / "low_soh_protection_shadow_audit.csv"
    low_soh_protection_shadow_summary_csv_path = output_path / "low_soh_protection_shadow_summary.csv"
    pl_vs_ff_allocation_mistake_comparison_csv_path = output_path / "pl_vs_ff_allocation_mistake_comparison.csv"
    pl_vs_ff_allocation_scorecard_csv_path = output_path / "pl_vs_ff_allocation_scorecard.csv"
    capital_reallocation_waterfall_csv_path = output_path / "capital_reallocation_waterfall.csv"
    score_98_blocker_diagnostic_csv_path = output_path / "score_98_blocker_diagnostic.csv"
    model_98_readiness_scorecard_csv_path = output_path / "model_98_readiness_scorecard.csv"
    executive_premeeting_summary_csv_path = output_path / "executive_premeeting_summary.csv"
    manifest_json_path, manifest_csv_path = write_input_source_manifest(manifest, output_path)

    result.rows_frame.to_csv(rows_csv_path, index=False)
    add_provenance_columns(result.summary_frame, manifest).to_csv(summary_csv_path, index=False)
    result.gap_accuracy_frame.to_csv(gap_accuracy_csv_path, index=False)
    result.gap_bias_by_segment_frame.to_csv(gap_bias_by_segment_csv_path, index=False)
    result.blind_spot_summary_frame.to_csv(blind_spot_summary_csv_path, index=False)
    result.shadow_comparison_frame.to_csv(shadow_comparison_csv_path, index=False)
    result.reason_quality_audit_frame.to_csv(reason_quality_audit_csv_path, index=False)
    result.low_soh_protection_shadow_audit_frame.to_csv(low_soh_protection_shadow_audit_csv_path, index=False)
    add_provenance_columns(result.low_soh_protection_shadow_summary_frame, manifest).to_csv(low_soh_protection_shadow_summary_csv_path, index=False)
    result.pl_vs_ff_allocation_mistake_comparison_frame.to_csv(pl_vs_ff_allocation_mistake_comparison_csv_path, index=False)
    add_provenance_columns(result.pl_vs_ff_allocation_scorecard_frame, manifest).to_csv(pl_vs_ff_allocation_scorecard_csv_path, index=False)
    result.capital_reallocation_waterfall_frame.to_csv(capital_reallocation_waterfall_csv_path, index=False)
    result.score_98_blocker_diagnostic_frame.to_csv(score_98_blocker_diagnostic_csv_path, index=False)
    add_provenance_columns(result.model_98_readiness_scorecard_frame, manifest).to_csv(model_98_readiness_scorecard_csv_path, index=False)
    add_provenance_columns(result.executive_premeeting_summary_frame, manifest).to_csv(executive_premeeting_summary_csv_path, index=False)

    return StoreAllocationActualOutcomeArtifacts(
        rows_csv_path=str(rows_csv_path),
        summary_csv_path=str(summary_csv_path),
        gap_accuracy_csv_path=str(gap_accuracy_csv_path),
        gap_bias_by_segment_csv_path=str(gap_bias_by_segment_csv_path),
        blind_spot_summary_csv_path=str(blind_spot_summary_csv_path),
        shadow_comparison_csv_path=str(shadow_comparison_csv_path),
        reason_quality_audit_csv_path=str(reason_quality_audit_csv_path),
        low_soh_protection_shadow_audit_csv_path=str(low_soh_protection_shadow_audit_csv_path),
        low_soh_protection_shadow_summary_csv_path=str(low_soh_protection_shadow_summary_csv_path),
        pl_vs_ff_allocation_mistake_comparison_csv_path=str(pl_vs_ff_allocation_mistake_comparison_csv_path),
        pl_vs_ff_allocation_scorecard_csv_path=str(pl_vs_ff_allocation_scorecard_csv_path),
        capital_reallocation_waterfall_csv_path=str(capital_reallocation_waterfall_csv_path),
        score_98_blocker_diagnostic_csv_path=str(score_98_blocker_diagnostic_csv_path),
        model_98_readiness_scorecard_csv_path=str(model_98_readiness_scorecard_csv_path),
        executive_premeeting_summary_csv_path=str(executive_premeeting_summary_csv_path),
        input_source_manifest_json_path=str(manifest_json_path),
        input_source_manifest_csv_path=str(manifest_csv_path),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the diagnostics-only Stage 11 allocation actual-outcome backtest."
    )
    parser.add_argument("--stage11-diagnostic-csv", required=True)
    parser.add_argument("--stage11-master-csv", required=True)
    parser.add_argument("--actual-review-csv", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--max-unmatched-rows", type=int, default=DEFAULT_MAX_UNMATCHED_ROWS)
    parser.add_argument("--max-unmatched-rate", type=float, default=DEFAULT_MAX_UNMATCHED_RATE)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    artifacts = write_store_allocation_actual_outcome_backtest(
        stage11_diagnostic_csv_path=args.stage11_diagnostic_csv,
        stage11_master_csv_path=args.stage11_master_csv,
        actual_review_csv_path=args.actual_review_csv,
        output_root=args.output_root,
        run_id=args.run_id,
        max_unmatched_rows=args.max_unmatched_rows,
        max_unmatched_rate=args.max_unmatched_rate,
    )
    print("store_allocation_actual_outcome_backtest", artifacts.rows_csv_path)
    print("store_allocation_actual_outcome_summary", artifacts.summary_csv_path)
    print("projected_stock_gap_accuracy", artifacts.gap_accuracy_csv_path)
    print("projected_stock_gap_bias_by_segment", artifacts.gap_bias_by_segment_csv_path)
    print("allocation_blind_spot_summary", artifacts.blind_spot_summary_csv_path)
    print("shadow_gap_calibration_comparison", artifacts.shadow_comparison_csv_path)
    print("store_action_reason_quality_audit", artifacts.reason_quality_audit_csv_path)
    print("low_soh_protection_shadow_audit", artifacts.low_soh_protection_shadow_audit_csv_path)
    print("low_soh_protection_shadow_summary", artifacts.low_soh_protection_shadow_summary_csv_path)
    print("pl_vs_ff_allocation_mistake_comparison", artifacts.pl_vs_ff_allocation_mistake_comparison_csv_path)
    print("pl_vs_ff_allocation_scorecard", artifacts.pl_vs_ff_allocation_scorecard_csv_path)
    print("capital_reallocation_waterfall", artifacts.capital_reallocation_waterfall_csv_path)
    print("score_98_blocker_diagnostic", artifacts.score_98_blocker_diagnostic_csv_path)
    print("model_98_readiness_scorecard", artifacts.model_98_readiness_scorecard_csv_path)
    print("executive_premeeting_summary", artifacts.executive_premeeting_summary_csv_path)
    print("input_source_manifest_json", artifacts.input_source_manifest_json_path)
    print("input_source_manifest_csv", artifacts.input_source_manifest_csv_path)


if __name__ == "__main__":
    main()