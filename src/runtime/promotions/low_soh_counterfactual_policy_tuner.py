from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from runtime.promotions.input_source_provenance import (
    SOURCE_WARNING_TEXT,
    add_provenance_columns,
    build_input_source_manifest,
    certification_failed,
    resolve_actual_review_source,
    source_warning,
    write_input_source_manifest,
)


BASE_COLUMNS: tuple[str, ...] = (
    "store_number",
    "promotion_id",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "sku_number",
    "sku_description",
    "store_action_label",
    "store_action_label_v2",
    "demand_evidence_label",
    "availability_risk_label",
    "capital_drag_label",
    "current_soh",
    "projected_SOH_at_promo_start",
    "floor_units_required",
    "available_to_sell_before_floor",
    "expected_promo_demand",
    "avg_daily_units",
    "target_end_soh_units",
    "actual_units_sold",
    "actual_gross_profit_per_unit",
    "unit_cost",
    "pack_size",
    "pl_allocation_qty",
    "ff_current_order_units",
    "low_soh_shadow_segment",
)

GRID_COLUMNS: tuple[str, ...] = BASE_COLUMNS + (
    "candidate_policy_name",
    "candidate_order_units",
    "candidate_capital_deployed",
    "candidate_units_available",
    "candidate_missed_units",
    "candidate_missed_sales_flag",
    "candidate_units_sold_from_order",
    "candidate_protected_gp",
    "candidate_ending_soh",
    "candidate_excess_units_above_target",
    "candidate_excess_capital_above_target",
    "candidate_net_cash_value",
    "candidate_cash_roi",
    "candidate_result_label",
    "candidate_blocker_reason",
)

SCORECARD_COLUMNS: tuple[str, ...] = (
    "candidate_policy_name",
    "row_count",
    "order_rows",
    "order_units",
    "capital_deployed",
    "missed_sales_rows",
    "missed_units",
    "missed_units_reduced_vs_current_ff",
    "missed_units_reduction_rate_vs_current_ff",
    "excess_rows_above_target",
    "material_excess_rows",
    "excess_units_above_target",
    "excess_capital_above_target",
    "protected_gp",
    "net_cash_value",
    "cash_roi",
    "negative_cash_conversion_rows",
    "pack_moq_blocked_rows",
    "target_excess_blocked_rows",
    "score_100",
    "policy_rank",
    "production_recommendation",
    "reason",
)

SEGMENT_SCORECARD_COLUMNS: tuple[str, ...] = (
    "low_soh_shadow_segment",
    "row_count",
    "actual_sales_rows",
    "actual_units_sold",
    "current_ff_missed_units",
    "pl_missed_units",
    "pl_allocation_units",
    "pl_excess_units_above_target",
    "best_candidate_policy_name",
    "best_candidate_order_units",
    "best_candidate_capital_deployed",
    "best_candidate_missed_units",
    "missed_units_reduced_vs_current_ff",
    "protected_gp",
    "excess_capital_above_target",
    "net_cash_value",
    "cash_roi",
    "negative_cash_conversion_rows",
    "production_recommendation",
    "reason",
)

SHADOW_RECOMMENDATION_COLUMNS: tuple[str, ...] = (
    "candidate_policy_name",
    "eligible_segments",
    "order_cap_units",
    "row_count",
    "order_rows",
    "order_units",
    "capital_deployed",
    "missed_units_reduced_vs_current_ff",
    "excess_capital_above_target",
    "net_cash_value",
    "cash_roi",
    "recommendation",
    "recommendation_reason",
    "shadow_test_priority",
    "guardrails_required",
    "should_promote_to_stage11",
    "should_promote_to_shadow",
)

MISSED_DEMAND_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "store_action_label",
    "demand_evidence_label",
    "availability_risk_label",
    "capital_drag_label",
    "current_soh",
    "projected_SOH_at_promo_start",
    "expected_promo_demand",
    "avg_daily_units",
    "actual_units_sold",
    "ff_current_order_units",
    "pl_allocation_qty",
    "ff_missed_units",
    "pl_missed_units",
    "unit_cost",
    "gross_profit_per_unit",
    "missed_gp_value",
    "likely_failure_type",
    "recommended_policy_to_test",
    "plain_english_reason",
)

ACTUAL_EXPECTED_COLUMNS: tuple[str, ...] = (
    "sku_number",
    "sku_description",
    "store_action_label",
    "demand_evidence_label",
    "expected_promo_demand",
    "actual_units_sold",
    "demand_error_units",
    "demand_error_abs_units",
    "demand_error_direction",
    "expected_bucket",
    "actual_bucket",
    "failure_type",
    "suggested_feature_fix",
)

LOW_SOH_LABELS = frozenset(
    {
        "LOW_SOH_NO_AUTO_BUY",
        "LOW_SOH_PROTECT_AVAILABILITY",
        "LOW_SOH_BORDERLINE_REVIEW",
        "ZERO_SOH_RISK",
        "NO_PRIOR_PROMO_EVIDENCE_LOW_SOH_REVIEW",
        "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
    }
)

CREDIBLE_DEMAND_LABELS = frozenset(
    {
        "CREDIBLE_PROMO_DEMAND",
        "LOW_NONZERO_DEMAND",
        "SPARSE_HISTORY",
        "BASELINE_DEMAND",
        "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
    }
)

LOW_SOH_SHADOW_SEGMENTS: tuple[str, ...] = (
    "ZERO_SOH_REPEAT_DEMAND",
    "ZERO_SOH_HIDDEN_DEMAND",
    "LOW_SOH_REPEAT_DEMAND",
    "LOW_SOH_BASELINE_DEMAND",
    "LOW_SOH_WEAK_DEMAND",
    "LOW_SOH_NO_DEMAND",
    "PACK_MOQ_UNECONOMIC",
    "HIGH_COST_LOW_CONFIDENCE",
    "PL_PROVED_DEMAND_BUT_OVERBOUGHT",
    "REVIEW_REQUIRED",
)

SEGMENTED_POLICY_NAMES: tuple[str, ...] = (
    "SEGMENTED_ZERO_SOH_ORDER_1",
    "SEGMENTED_LOW_SOH_BASELINE_ORDER_1",
    "SEGMENTED_PL_PROVED_ORDER_1",
    "SEGMENTED_COMBINED_ORDER_1",
)

SEGMENTED_POLICY_ELIGIBLE_SEGMENTS: dict[str, tuple[str, ...]] = {
    "SEGMENTED_ZERO_SOH_ORDER_1": ("ZERO_SOH_REPEAT_DEMAND", "ZERO_SOH_HIDDEN_DEMAND"),
    "SEGMENTED_LOW_SOH_BASELINE_ORDER_1": ("LOW_SOH_REPEAT_DEMAND", "LOW_SOH_BASELINE_DEMAND"),
    "SEGMENTED_PL_PROVED_ORDER_1": ("PL_PROVED_DEMAND_BUT_OVERBOUGHT",),
    "SEGMENTED_COMBINED_ORDER_1": (
        "ZERO_SOH_REPEAT_DEMAND",
        "ZERO_SOH_HIDDEN_DEMAND",
        "LOW_SOH_REPEAT_DEMAND",
        "LOW_SOH_BASELINE_DEMAND",
        "PL_PROVED_DEMAND_BUT_OVERBOUGHT",
    ),
}

POLICY_NAMES: tuple[str, ...] = (
    "NO_ORDER_0",
    "CURRENT_FF",
    "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND",
    "ORDER_2_IF_ZERO_SOH_AND_FLOOR_REQUIRED",
    "ORDER_1_IF_LOW_SOH_AND_ACTUAL_BASELINE_SIGNAL",
    "ORDER_CAPPED_DEMAND_GAP_MAX_2",
    "ORDER_CAPPED_FLOOR_GAP_MAX_2",
    "ORDER_CAPPED_HYBRID_MAX_3",
    "ORDER_PACK_SIZE_ADJUSTED_FLOOR_GAP",
    "SEGMENTED_ZERO_SOH_ORDER_1",
    "SEGMENTED_LOW_SOH_BASELINE_ORDER_1",
    "SEGMENTED_PL_PROVED_ORDER_1",
    "SEGMENTED_COMBINED_ORDER_1",
    "PL_ALLOCATION",
)


class LowSohCounterfactualPolicyTunerError(RuntimeError):
    """Raised when low-SOH counterfactual tuning inputs are invalid."""


@dataclass(frozen=True)
class LowSohCounterfactualConfig:
    max_auto_order_units: int = 3
    max_pack_size: int = 3
    max_unit_cost: float = 60.0
    max_capital_drag_rate: float = 250.0


@dataclass(frozen=True)
class LowSohCounterfactualArtifacts:
    policy_grid_csv_path: str
    policy_scorecard_csv_path: str
    segment_scorecard_csv_path: str
    shadow_policy_recommendations_csv_path: str
    missed_demand_diagnostic_csv_path: str
    actual_vs_expected_demand_diagnostic_csv_path: str
    final_summary_csv_path: str
    input_source_manifest_json_path: str
    input_source_manifest_csv_path: str


@dataclass(frozen=True)
class LowSohCounterfactualResult:
    base_frame: pd.DataFrame
    policy_grid_frame: pd.DataFrame
    policy_scorecard_frame: pd.DataFrame
    segment_scorecard_frame: pd.DataFrame
    shadow_policy_recommendations_frame: pd.DataFrame
    missed_demand_diagnostic_frame: pd.DataFrame
    actual_vs_expected_demand_diagnostic_frame: pd.DataFrame


def _infer_run_id(output_root: str | Path, explicit_run_id: str | None = None) -> str:
    if explicit_run_id and explicit_run_id.strip():
        return explicit_run_id.strip()
    return Path(output_root).name or "low_soh_counterfactual_tuner"


def _read_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False, low_memory=False)
    if frame.empty:
        raise LowSohCounterfactualPolicyTunerError(f"CSV is empty: {path}")
    return frame


def _first_existing(frame: pd.DataFrame, names: tuple[str, ...], *, default: object = "") -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series(default, index=frame.index)


def _text(frame: pd.DataFrame, names: str | tuple[str, ...], *, default: str = "") -> pd.Series:
    aliases = (names,) if isinstance(names, str) else names
    return _first_existing(frame, aliases, default=default).fillna(default).astype(str).str.strip()


def _numeric(frame: pd.DataFrame, names: str | tuple[str, ...], *, default: float = 0.0) -> pd.Series:
    aliases = (names,) if isinstance(names, str) else names
    return pd.to_numeric(_first_existing(frame, aliases, default=default), errors="coerce").fillna(default).astype("float64")


def _normalize_identifier(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    normalized = numeric.round(0).astype("Int64").astype(str).replace("<NA>", "")
    fallback = series.fillna("").astype(str).str.strip()
    return normalized.where(normalized.ne(""), fallback).astype(str).str.strip()


def _normalize_date(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True, format="mixed")
    formatted = parsed.dt.strftime("%Y-%m-%d")
    return formatted.fillna(series.fillna("").astype(str).str.strip())


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator_numeric = pd.to_numeric(denominator, errors="coerce")
    ratio = pd.to_numeric(numerator, errors="coerce").divide(
        denominator_numeric.where(denominator_numeric.ne(0.0))
    )
    return ratio.replace([np.inf, -np.inf], np.nan)


def _canonicalize_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    out["store_number"] = _normalize_identifier(_first_existing(frame, ("store_number",), default=""))
    out["promotion_id"] = _text(frame, ("promotion_id", "promotion_row_key", "promotional_sku_id_key"))
    out["promotion_name"] = _text(frame, "promotion_name")
    out["promotion_start_date"] = _normalize_date(_first_existing(frame, ("promotion_start_date",), default=""))
    out["promotion_end_date"] = _normalize_date(_first_existing(frame, ("promotion_end_date", "promotional_end_date"), default=""))
    out["sku_number"] = _normalize_identifier(_first_existing(frame, ("sku_number", "sku_number_key"), default=""))
    out["sku_description"] = _text(frame, "sku_description")
    out["store_action_label"] = _text(frame, "store_action_label").str.upper()
    out["store_action_label_v2"] = _text(frame, ("store_action_label_v2", "store_action", "recommended_action")).str.upper()
    out["demand_evidence_label"] = _text(frame, "demand_evidence_label").str.upper()
    out["availability_risk_label"] = _text(frame, "availability_risk_label").str.upper()
    out["capital_drag_label"] = _text(frame, "capital_drag_label").str.upper()
    out["current_soh"] = _numeric(frame, ("current_soh", "current_soh_units", "SOH_at_advice_time"))
    out["projected_SOH_at_promo_start"] = _numeric(frame, ("projected_SOH_at_promo_start", "projected_on_hand_at_promo_start"))
    out["floor_units_required"] = _numeric(frame, ("floor_units_required", "minimum_launch_stock_units"), default=2.0)
    out["available_to_sell_before_floor"] = _numeric(frame, "available_to_sell_before_floor")
    out["expected_promo_demand"] = _numeric(frame, ("expected_promo_demand", "expected_units_total_promo", "projected_promotional_units"))
    out["avg_daily_units"] = _numeric(frame, ("avg_daily_units", "feature_non_promo_56d_avg_daily_units", "expected_units_per_day"))
    out["target_end_soh_units"] = _numeric(frame, ("target_end_soh_units", "target_end_stock_units"), default=np.nan)
    target_fallback = pd.Series(np.maximum(2.0, out["avg_daily_units"].clip(lower=0.0) * 30.0), index=out.index)
    out["target_end_soh_units"] = out["target_end_soh_units"].fillna(target_fallback).clip(lower=0.0)
    out["actual_gross_profit_per_unit"] = _numeric(frame, ("actual_gross_profit_per_unit", "gross_profit_per_unit", "expected_gp_per_unit"), default=np.nan)
    out["unit_cost"] = _numeric(frame, ("unit_cost", "allocation_unit_cost", "last_received_cost", "promo_effective_cost", "unit_cost_dollars"), default=np.nan)
    out["pack_size"] = _numeric(frame, ("pack_size", "moq", "minimum_order_quantity"), default=1.0).clip(lower=1.0)
    out["pl_allocation_qty"] = _numeric(frame, ("pl_allocation_qty", "pl_allocated", "pl_allocation_units"), default=np.nan)
    out["ff_current_order_units"] = _numeric(frame, ("final_store_order_units", "recommended_order_units", "ff_current_order_units"))
    return out


def _canonicalize_actual_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    out["sku_number"] = _normalize_identifier(_first_existing(frame, ("sku_number", "sku_number_key"), default=""))
    out["actual_units_sold"] = _numeric(frame, ("actual_units_sold", "actual_units_sold_promo"), default=np.nan)
    total_gp = _numeric(frame, ("estimated_actual_gross_profit", "estimated_gross_profit_after_priceline_fees", "actual_gross_profit"), default=np.nan)
    gp_per_unit = _numeric(frame, ("actual_gross_profit_per_unit", "gross_profit_per_unit", "expected_gp_per_unit"), default=np.nan)
    out["actual_gross_profit_per_unit_actual"] = gp_per_unit.fillna(_safe_ratio(total_gp, out["actual_units_sold"]))
    out["unit_cost_actual"] = _numeric(frame, ("unit_cost", "allocation_unit_cost", "last_received_cost", "promo_effective_cost", "promo_cost_price"), default=np.nan)
    out["pack_size_actual"] = _numeric(frame, ("pack_size", "moq", "minimum_order_quantity"), default=np.nan)
    out["pl_allocation_qty_actual"] = _numeric(frame, ("pl_allocation_qty", "pl_allocated", "pl_allocation_units"), default=np.nan)
    return out.drop_duplicates(subset=["sku_number"], keep="first")


def _canonicalize_allocation_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    out["sku_number"] = _normalize_identifier(_first_existing(frame, ("sku_number", "sku_number_key"), default=""))
    out["pl_allocation_qty_allocation"] = _numeric(frame, ("pl_allocation_qty", "pl_allocated", "pl_allocation_units"), default=np.nan)
    out["unit_cost_allocation"] = _numeric(frame, ("unit_cost", "allocation_unit_cost", "last_received_cost", "promo_effective_cost", "unit_cost_dollars"), default=np.nan)
    return out.drop_duplicates(subset=["sku_number"], keep="first")


def build_counterfactual_base_frame(
    *,
    feature_inspection_frame: pd.DataFrame,
    actual_review_frame: pd.DataFrame,
    allocation_report_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    features = _canonicalize_feature_frame(feature_inspection_frame)
    actuals = _canonicalize_actual_frame(actual_review_frame)
    if features["sku_number"].eq("").any() or actuals["sku_number"].eq("").any():
        raise LowSohCounterfactualPolicyTunerError("Input rows contain blank sku_number values.")
    merged = features.merge(actuals, on="sku_number", how="left", validate="many_to_one")
    if merged["actual_units_sold"].isna().any():
        unmatched = int(merged["actual_units_sold"].isna().sum())
        raise LowSohCounterfactualPolicyTunerError(f"Actual review did not match {unmatched} feature rows by sku_number.")
    if allocation_report_frame is not None:
        merged = merged.merge(_canonicalize_allocation_frame(allocation_report_frame), on="sku_number", how="left", validate="many_to_one")
    else:
        merged["pl_allocation_qty_allocation"] = np.nan
        merged["unit_cost_allocation"] = np.nan
    merged["actual_gross_profit_per_unit"] = merged["actual_gross_profit_per_unit_actual"].fillna(merged["actual_gross_profit_per_unit"]).fillna(0.0).clip(lower=0.0)
    merged["unit_cost"] = merged["unit_cost"].fillna(merged["unit_cost_actual"]).fillna(merged["unit_cost_allocation"]).fillna(0.0).clip(lower=0.0)
    merged["pack_size"] = merged["pack_size"].where(merged["pack_size"].gt(0.0), merged["pack_size_actual"]).fillna(1.0).clip(lower=1.0)
    merged["pl_allocation_qty"] = merged["pl_allocation_qty"].fillna(merged["pl_allocation_qty_actual"]).fillna(merged["pl_allocation_qty_allocation"]).fillna(0.0).clip(lower=0.0)
    base = merged.loc[:, [column for column in BASE_COLUMNS if column != "low_soh_shadow_segment"]].copy()
    return _with_low_soh_shadow_segments(base)


def _low_soh_mask(rows: pd.DataFrame) -> pd.Series:
    action = rows["store_action_label"].astype(str).str.upper()
    availability = rows["availability_risk_label"].astype(str).str.upper()
    return action.isin(LOW_SOH_LABELS) | availability.str.contains("LOW_SOH|ZERO_SOH|FLOOR", regex=True)


def _credible_or_baseline_mask(rows: pd.DataFrame) -> pd.Series:
    action = rows["store_action_label"].astype(str).str.upper()
    demand = rows["demand_evidence_label"].astype(str).str.upper()
    return demand.isin(CREDIBLE_DEMAND_LABELS) | demand.str.contains("CREDIBLE|BASELINE|LOW_NONZERO|SPARSE", regex=True) | action.str.contains("BASELINE", regex=False)


def classify_low_soh_shadow_segments(
    rows: pd.DataFrame,
    *,
    config: LowSohCounterfactualConfig | None = None,
) -> pd.Series:
    resolved = config or LowSohCounterfactualConfig()
    projected = rows["projected_SOH_at_promo_start"].clip(lower=0.0)
    actual = rows["actual_units_sold"].clip(lower=0.0)
    expected = rows["expected_promo_demand"].clip(lower=0.0)
    average_daily_units = rows["avg_daily_units"].clip(lower=0.0)
    target = rows["target_end_soh_units"].clip(lower=0.0)
    unit_cost = rows["unit_cost"].clip(lower=0.0)
    pack_size = rows["pack_size"].clip(lower=1.0)
    gross_profit = rows["actual_gross_profit_per_unit"].clip(lower=0.0)
    ff_available = projected.add(rows["ff_current_order_units"].clip(lower=0.0))
    pl_units = rows["pl_allocation_qty"].clip(lower=0.0)
    pl_available = projected.add(pl_units)
    ff_missed = actual.sub(ff_available).clip(lower=0.0)
    pl_missed = actual.sub(pl_available).clip(lower=0.0)
    pl_excess_units = pl_available.sub(actual).clip(lower=0.0).sub(target).clip(lower=0.0)
    one_unit_excess_units = projected.add(1.0).sub(actual).clip(lower=0.0).sub(target).clip(lower=0.0)
    one_unit_net_cash = pd.Series(np.minimum(1.0, actual.sub(projected).clip(lower=0.0)), index=rows.index).mul(gross_profit).sub(one_unit_excess_units.mul(unit_cost))
    pack_order_excess_units = projected.add(pack_size).sub(actual).clip(lower=0.0).sub(target).clip(lower=0.0)
    demand_label = rows["demand_evidence_label"].astype(str).str.upper()
    action = rows["store_action_label"].astype(str).str.upper()
    credible_or_baseline = _credible_or_baseline_mask(rows) | demand_label.str.contains("REPEAT", regex=False)
    weak_evidence = ~credible_or_baseline | demand_label.str.contains("WEAK|NO_DEMAND|NEVER", regex=True)
    low_soh = _low_soh_mask(rows) | projected.le(2.0)
    segment = pd.Series("REVIEW_REQUIRED", index=rows.index, dtype="object")

    segment = segment.mask(low_soh & actual.le(0.0), "LOW_SOH_NO_DEMAND")
    segment = segment.mask(low_soh & expected.lt(1.0) & actual.le(1.0) & weak_evidence, "LOW_SOH_WEAK_DEMAND")
    segment = segment.mask(low_soh & credible_or_baseline & expected.ge(1.0) & average_daily_units.gt(0.0), "LOW_SOH_BASELINE_DEMAND")
    segment = segment.mask(projected.between(1.0, 2.0, inclusive="both") & actual.gt(projected) & average_daily_units.gt(0.0) & credible_or_baseline, "LOW_SOH_REPEAT_DEMAND")
    segment = segment.mask(projected.le(0.0) & actual.gt(0.0) & (expected.ge(1.0) | credible_or_baseline | action.str.contains("BASELINE", regex=False)) & pack_size.le(2.0) & average_daily_units.le(0.20) & low_soh, "ZERO_SOH_REPEAT_DEMAND")
    segment = segment.mask(projected.le(0.0) & actual.gt(0.0) & expected.lt(1.0) & (average_daily_units.le(0.10) | actual.gt(expected)) & low_soh, "ZERO_SOH_HIDDEN_DEMAND")

    pl_proved_overbought = pl_units.gt(0.0) & actual.gt(ff_available) & pl_missed.lt(ff_missed) & (pl_excess_units.ge(2.0) | pl_excess_units.mul(unit_cost).ge(50.0))
    high_cost_low_confidence = unit_cost.gt(float(resolved.max_unit_cost)) & low_soh & weak_evidence & one_unit_net_cash.le(0.0)
    pack_moq_uneconomic = pack_size.gt(float(resolved.max_pack_size)) | (pack_order_excess_units.ge(2.0) | pack_order_excess_units.mul(unit_cost).ge(50.0))
    segment = segment.mask(pl_proved_overbought, "PL_PROVED_DEMAND_BUT_OVERBOUGHT")
    segment = segment.mask(pack_moq_uneconomic, "PACK_MOQ_UNECONOMIC")
    segment = segment.mask(high_cost_low_confidence, "HIGH_COST_LOW_CONFIDENCE")
    return segment


def _with_low_soh_shadow_segments(
    rows: pd.DataFrame,
    *,
    config: LowSohCounterfactualConfig | None = None,
) -> pd.DataFrame:
    out = rows.copy()
    out["low_soh_shadow_segment"] = classify_low_soh_shadow_segments(out, config=config)
    return out


def _append_blocker(blocker: pd.Series, mask: pd.Series, reason: str) -> pd.Series:
    blocker = blocker.mask(mask & blocker.eq(""), reason)
    return blocker.mask(mask & blocker.ne("") & ~blocker.str.contains(reason, regex=False), blocker + ";" + reason)


def _guardrails(
    rows: pd.DataFrame,
    raw_units: pd.Series,
    *,
    config: LowSohCounterfactualConfig,
    block_high_drag: bool,
    block_target_excess: bool,
) -> tuple[pd.Series, pd.Series]:
    units = pd.to_numeric(raw_units, errors="coerce").fillna(0.0).clip(lower=0.0, upper=float(config.max_auto_order_units)).round(0)
    blocker = pd.Series("", index=rows.index, dtype="object")
    ending = rows["projected_SOH_at_promo_start"].clip(lower=0.0).add(units).sub(rows["expected_promo_demand"].clip(lower=0.0))
    projected_excess = ending.clip(lower=0.0).sub(rows["target_end_soh_units"].clip(lower=0.0)).clip(lower=0.0)
    blocker = _append_blocker(blocker, rows["pack_size"].gt(float(config.max_pack_size)) & units.gt(0.0), "pack_moq_exceeds_3_unit_cap")
    blocker = _append_blocker(blocker, rows["unit_cost"].gt(float(config.max_unit_cost)) & units.gt(0.0), "unit_cost_exceeds_threshold")
    blocker = _append_blocker(blocker, units.mul(rows["unit_cost"]).gt(float(config.max_capital_drag_rate)) & units.gt(0.0), "capital_deployment_exceeds_threshold")
    blocker = _append_blocker(blocker, rows["capital_drag_label"].astype(str).str.contains("HIGH") & units.gt(0.0) & block_high_drag, "capital_drag_high")
    blocker = _append_blocker(blocker, (projected_excess.ge(2.0) | projected_excess.mul(rows["unit_cost"]).ge(50.0)) & units.gt(0.0) & block_target_excess, "projected_target_excess_risk")
    return units.where(blocker.eq(""), 0.0), blocker


def _cash_conversion_guardrails(rows: pd.DataFrame, units: pd.Series, blocker: pd.Series) -> tuple[pd.Series, pd.Series]:
    projected = rows["projected_SOH_at_promo_start"].clip(lower=0.0)
    actual = rows["actual_units_sold"].clip(lower=0.0)
    unit_cost = rows["unit_cost"].clip(lower=0.0)
    sold_from_order = pd.Series(np.minimum(units, actual.sub(projected).clip(lower=0.0)), index=rows.index).clip(lower=0.0)
    protected_gp = sold_from_order.mul(rows["actual_gross_profit_per_unit"].clip(lower=0.0))
    excess_capital = projected.add(units).sub(actual).clip(lower=0.0).sub(rows["target_end_soh_units"].clip(lower=0.0)).clip(lower=0.0).mul(unit_cost)
    net_cash = protected_gp.sub(excess_capital)
    negative_cash = units.gt(0.0) & net_cash.lt(0.0)
    blocker = _append_blocker(blocker, negative_cash, "candidate_negative_cash_conversion")
    return units.where(~negative_cash, 0.0), blocker


def _candidate_units(rows: pd.DataFrame, policy_name: str, config: LowSohCounterfactualConfig) -> tuple[pd.Series, pd.Series]:
    projected = rows["projected_SOH_at_promo_start"].clip(lower=0.0)
    expected = rows["expected_promo_demand"].clip(lower=0.0)
    floor_required = rows["floor_units_required"].clip(lower=0.0)
    available = rows["available_to_sell_before_floor"].clip(lower=0.0)
    floor_gap = floor_required.sub(projected).clip(lower=0.0)
    demand_gap = expected.sub(available).clip(lower=0.0)
    empty_blocker = pd.Series("", index=rows.index, dtype="object")
    if policy_name == "NO_ORDER_0":
        return pd.Series(0.0, index=rows.index), empty_blocker
    if policy_name == "CURRENT_FF":
        return rows["ff_current_order_units"].clip(lower=0.0).round(0), empty_blocker
    if policy_name == "PL_ALLOCATION":
        return rows["pl_allocation_qty"].clip(lower=0.0).round(0), empty_blocker
    raw = pd.Series(0.0, index=rows.index, dtype="float64")
    block_high_drag = True
    block_target_excess = False
    if policy_name == "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND":
        raw = raw.mask(projected.le(0.0) & expected.ge(1.0), 1.0)
    elif policy_name == "ORDER_2_IF_ZERO_SOH_AND_FLOOR_REQUIRED":
        raw = raw.mask(projected.le(0.0) & floor_required.ge(2.0) & expected.ge(1.0), 2.0)
        block_high_drag = False
    elif policy_name == "ORDER_1_IF_LOW_SOH_AND_ACTUAL_BASELINE_SIGNAL":
        raw = raw.mask(projected.le(1.0) & rows["avg_daily_units"].gt(0.0) & expected.ge(1.0), 1.0)
    elif policy_name == "ORDER_CAPPED_DEMAND_GAP_MAX_2":
        raw = pd.Series(np.minimum(np.ceil(demand_gap), 2.0), index=rows.index).where(_low_soh_mask(rows), 0.0)
        block_target_excess = True
    elif policy_name == "ORDER_CAPPED_FLOOR_GAP_MAX_2":
        raw = pd.Series(np.minimum(np.ceil(floor_gap), 2.0), index=rows.index).where(_low_soh_mask(rows) & expected.ge(1.0), 0.0)
    elif policy_name == "ORDER_CAPPED_HYBRID_MAX_3":
        raw = pd.Series(np.minimum(np.ceil(np.maximum(floor_gap, demand_gap)), float(config.max_auto_order_units)), index=rows.index).where(_credible_or_baseline_mask(rows), 0.0)
        block_target_excess = True
    elif policy_name == "ORDER_PACK_SIZE_ADJUSTED_FLOOR_GAP":
        pack_size = rows["pack_size"].clip(lower=1.0).round(0)
        raw_floor_units = pd.Series(np.ceil(floor_gap), index=rows.index)
        raw = pd.Series(np.ceil(raw_floor_units / pack_size).mul(pack_size), index=rows.index).where(_low_soh_mask(rows) & expected.ge(1.0), 0.0)
        block_target_excess = True
    elif policy_name in SEGMENTED_POLICY_NAMES:
        segments = rows["low_soh_shadow_segment"].astype(str).str.upper()
        raw = raw.mask(segments.isin(SEGMENTED_POLICY_ELIGIBLE_SEGMENTS[policy_name]), 1.0)
        block_target_excess = True
    else:
        raise LowSohCounterfactualPolicyTunerError(f"Unsupported candidate policy: {policy_name}")
    units, blocker = _guardrails(rows, raw, config=config, block_high_drag=block_high_drag, block_target_excess=block_target_excess)
    if policy_name in SEGMENTED_POLICY_NAMES:
        return _cash_conversion_guardrails(rows, units, blocker)
    return units, blocker


def _result_labels(rows: pd.DataFrame, units: pd.Series, missed: pd.Series, protected_gp: pd.Series, excess_units: pd.Series, excess_capital: pd.Series, net_cash: pd.Series, blocker: pd.Series) -> pd.Series:
    actual = rows["actual_units_sold"].clip(lower=0.0)
    projected = rows["projected_SOH_at_promo_start"].clip(lower=0.0)
    label = pd.Series("REVIEW_REQUIRED", index=rows.index, dtype="object")
    label = label.mask(actual.le(0.0) & units.le(0.0), "TRUE_NO_DEMAND")
    label = label.mask(units.le(0.0) & missed.le(0.0) & actual.gt(0.0) & projected.ge(actual), "CAPITAL_FREE_SUCCESS")
    label = label.mask(units.gt(0.0) & missed.le(0.0) & protected_gp.gt(0.0) & net_cash.ge(0.0) & excess_capital.le(25.0), "GOOD_LOW_SOH_PROTECTION")
    label = label.mask(missed.gt(0.0), "MISSED_DEMAND")
    label = label.mask((excess_units.ge(2.0) | excess_capital.ge(50.0)) & units.gt(0.0), "OVER_ALLOCATED_CAPITAL")
    label = label.mask(units.gt(0.0) & net_cash.lt(0.0), "NEGATIVE_CASH_CONVERSION")
    label = label.mask(blocker.str.contains("pack_moq", regex=False), "PACK_MOQ_FORCED_EXCESS")
    return label


def build_low_soh_counterfactual_policy_grid(rows: pd.DataFrame, *, config: LowSohCounterfactualConfig | None = None) -> pd.DataFrame:
    resolved = config or LowSohCounterfactualConfig()
    rows = _with_low_soh_shadow_segments(rows, config=resolved)
    frames: list[pd.DataFrame] = []
    for policy_name in POLICY_NAMES:
        units, blocker = _candidate_units(rows, policy_name, resolved)
        projected = rows["projected_SOH_at_promo_start"].clip(lower=0.0)
        actual = rows["actual_units_sold"].clip(lower=0.0)
        unit_cost = rows["unit_cost"].clip(lower=0.0)
        available = projected.add(units)
        missed = actual.sub(available).clip(lower=0.0)
        sold_from_order = pd.Series(np.minimum(units, actual.sub(projected).clip(lower=0.0)), index=rows.index).clip(lower=0.0)
        protected_gp = sold_from_order.mul(rows["actual_gross_profit_per_unit"].clip(lower=0.0))
        ending = available.sub(actual)
        excess_units = ending.clip(lower=0.0).sub(rows["target_end_soh_units"].clip(lower=0.0)).clip(lower=0.0)
        excess_capital = excess_units.mul(unit_cost)
        capital = units.mul(unit_cost)
        net_cash = protected_gp.sub(excess_capital)
        candidate = rows.copy()
        candidate["candidate_policy_name"] = policy_name
        candidate["candidate_order_units"] = units.astype(int)
        candidate["candidate_capital_deployed"] = capital.round(2)
        candidate["candidate_units_available"] = available.round(4)
        candidate["candidate_missed_units"] = missed.round(4)
        candidate["candidate_missed_sales_flag"] = missed.gt(0.0).astype(int)
        candidate["candidate_units_sold_from_order"] = sold_from_order.round(4)
        candidate["candidate_protected_gp"] = protected_gp.round(2)
        candidate["candidate_ending_soh"] = ending.round(4)
        candidate["candidate_excess_units_above_target"] = excess_units.round(4)
        candidate["candidate_excess_capital_above_target"] = excess_capital.round(2)
        candidate["candidate_net_cash_value"] = net_cash.round(2)
        candidate["candidate_cash_roi"] = _safe_ratio(protected_gp, capital).fillna(0.0).round(4)
        candidate["candidate_result_label"] = _result_labels(rows, units, missed, protected_gp, excess_units, excess_capital, net_cash, blocker)
        candidate["candidate_blocker_reason"] = blocker
        frames.append(candidate.loc[:, GRID_COLUMNS])
    return pd.concat(frames, ignore_index=True)


def _aggregate_policy_metrics(policy_frame: pd.DataFrame, *, current_missed: float, row_count: int) -> dict[str, object]:
    missed = float(policy_frame["candidate_missed_units"].sum())
    capital = float(policy_frame["candidate_capital_deployed"].sum())
    protected_gp = float(policy_frame["candidate_protected_gp"].sum())
    net_cash = float(policy_frame["candidate_net_cash_value"].sum())
    material_mask = policy_frame["candidate_result_label"].isin(["OVER_ALLOCATED_CAPITAL", "NEGATIVE_CASH_CONVERSION", "PACK_MOQ_FORCED_EXCESS"])
    return {
        "candidate_policy_name": str(policy_frame["candidate_policy_name"].iloc[0]) if not policy_frame.empty else "",
        "row_count": int(row_count),
        "order_rows": int(policy_frame["candidate_order_units"].gt(0).sum()),
        "order_units": int(policy_frame["candidate_order_units"].sum()),
        "capital_deployed": round(capital, 2),
        "missed_sales_rows": int(policy_frame["candidate_missed_sales_flag"].sum()),
        "missed_units": round(missed, 4),
        "missed_units_reduced_vs_current_ff": round(current_missed - missed, 4),
        "missed_units_reduction_rate_vs_current_ff": round((current_missed - missed) / current_missed, 6) if current_missed > 0.0 else 0.0,
        "excess_rows_above_target": int(policy_frame["candidate_excess_units_above_target"].gt(0.0).sum()),
        "material_excess_rows": int(material_mask.sum()),
        "excess_units_above_target": round(float(policy_frame["candidate_excess_units_above_target"].sum()), 4),
        "excess_capital_above_target": round(float(policy_frame["candidate_excess_capital_above_target"].sum()), 2),
        "protected_gp": round(protected_gp, 2),
        "net_cash_value": round(net_cash, 2),
        "cash_roi": round(float(_safe_ratio(pd.Series([protected_gp]), pd.Series([capital])).fillna(0.0).iloc[0]), 4),
        "negative_cash_conversion_rows": int(policy_frame["candidate_result_label"].eq("NEGATIVE_CASH_CONVERSION").sum()),
        "pack_moq_blocked_rows": int(policy_frame["candidate_blocker_reason"].astype(str).str.contains("pack_moq", regex=False).sum()),
        "target_excess_blocked_rows": int(policy_frame["candidate_blocker_reason"].astype(str).str.contains("target_excess", regex=False).sum()),
    }


def _score_and_recommend(row: pd.Series) -> tuple[float, str, str]:
    policy_name = str(row["candidate_policy_name"])
    row_count = max(float(row["row_count"]), 1.0)
    reduction_rate = max(float(row["missed_units_reduction_rate_vs_current_ff"]), 0.0)
    breadth = float(row["order_rows"]) / row_count
    capital = max(float(row["capital_deployed"]), 0.0)
    protected_gp = max(float(row["protected_gp"]), 0.0)
    net_cash = float(row["net_cash_value"])
    excess_capital = max(float(row["excess_capital_above_target"]), 0.0)
    negative_rows = float(row["negative_cash_conversion_rows"])
    material_rows = float(row["material_excess_rows"])
    efficiency = max(net_cash, 0.0) / max(protected_gp, capital, 1.0)
    score = 50.0 + min(reduction_rate, 1.0) * 35.0 + min(efficiency, 1.0) * 12.0
    score += max(0.0, 1.0 - breadth / 0.20) * 10.0
    score -= min(capital / 1000.0, 20.0) + min(excess_capital / 250.0, 20.0)
    score -= negative_rows * 2.5 + material_rows * 0.5
    missed_units_reduced = float(row["missed_units_reduced_vs_current_ff"])
    if policy_name in {"NO_ORDER_0", "CURRENT_FF"} or missed_units_reduced <= 0.0:
        score = min(score, 30.0)
    if policy_name == "PL_ALLOCATION":
        score -= 25.0
    score = round(float(np.clip(score, 0.0, 100.0)), 4)
    if policy_name == "CURRENT_FF":
        return score, "KEEP_AS_ANALYSIS_ONLY", "Current FF is the baseline, not a new policy."
    if policy_name == "PL_ALLOCATION":
        return min(score, 10.0), "REJECT_TOO_BROAD", "PL allocation is comparison-only and too broad for production promotion."
    if missed_units_reduced <= 0.0:
        return min(score, 15.0), "REJECT_WEAK_EVIDENCE", "Policy does not reduce missed units versus current FF."
    if negative_rows > 0.0 or excess_capital > max(protected_gp, 25.0):
        return min(score, 32.0), "REJECT_CAPITAL_DRAG", "Capital drag or negative cash conversion is too high."
    if breadth > 0.20 and float(row["order_rows"]) > 25.0:
        return min(score, 34.0), "REJECT_TOO_BROAD", "Policy orders too many rows for a narrow low-SOH rule."
    if score >= 35.0:
        return score, "PROMOTE_TO_SHADOW", "Candidate is suitable for governed shadow validation only; production remains unchanged."
    return score, "KEEP_AS_ANALYSIS_ONLY", "Useful diagnostic policy but not strong enough for shadow promotion."


def build_low_soh_counterfactual_policy_scorecard(grid: pd.DataFrame) -> pd.DataFrame:
    current = grid.loc[grid["candidate_policy_name"].eq("CURRENT_FF")]
    current_missed = max(float(current["candidate_missed_units"].sum()), 0.0)
    row_count = int(current.shape[0])
    records: list[dict[str, object]] = []
    for policy_name, policy_frame in grid.groupby("candidate_policy_name", sort=False):
        record = _aggregate_policy_metrics(policy_frame, current_missed=current_missed, row_count=row_count)
        record["score_100"], record["production_recommendation"], record["reason"] = _score_and_recommend(pd.Series(record))
        records.append(record)
    scorecard = pd.DataFrame(records)
    promotable = scorecard["production_recommendation"].eq("PROMOTE_TO_SHADOW")
    if promotable.sum() > 1:
        best_index = scorecard.loc[promotable].sort_values(["score_100", "missed_units_reduced_vs_current_ff", "net_cash_value"], ascending=[False, False, False]).index[0]
        demote = promotable & scorecard.index.to_series().ne(best_index)
        scorecard.loc[demote, "production_recommendation"] = "KEEP_AS_ANALYSIS_ONLY"
        scorecard.loc[demote, "reason"] = "Not the strongest policy candidate in this offline scorecard."
    scorecard = scorecard.sort_values(["score_100", "missed_units_reduced_vs_current_ff", "net_cash_value"], ascending=[False, False, False]).reset_index(drop=True)
    scorecard["policy_rank"] = np.arange(1, len(scorecard) + 1)
    return scorecard.loc[:, SCORECARD_COLUMNS]


def build_low_soh_shadow_segment_scorecard(grid: pd.DataFrame) -> pd.DataFrame:
    current = grid.loc[grid["candidate_policy_name"].eq("CURRENT_FF")]
    pl = grid.loc[grid["candidate_policy_name"].eq("PL_ALLOCATION")]
    segmented = grid.loc[grid["candidate_policy_name"].isin(SEGMENTED_POLICY_NAMES)]
    records: list[dict[str, object]] = []
    for segment in LOW_SOH_SHADOW_SEGMENTS:
        current_segment = current.loc[current["low_soh_shadow_segment"].eq(segment)]
        pl_segment = pl.loc[pl["low_soh_shadow_segment"].eq(segment)]
        row_count = int(current_segment.shape[0])
        current_missed = float(current_segment["candidate_missed_units"].sum()) if row_count else 0.0
        best_record: dict[str, object] | None = None
        if row_count:
            candidate_records: list[dict[str, object]] = []
            for _policy_name, policy_frame in segmented.loc[segmented["low_soh_shadow_segment"].eq(segment)].groupby("candidate_policy_name", sort=False):
                aggregate = _aggregate_policy_metrics(policy_frame, current_missed=current_missed, row_count=row_count)
                aggregate["score_100"], aggregate["production_recommendation"], aggregate["reason"] = _score_and_recommend(pd.Series(aggregate))
                candidate_records.append(aggregate)
            if candidate_records:
                best_record = max(
                    candidate_records,
                    key=lambda record: (
                        float(record["score_100"]),
                        float(record["missed_units_reduced_vs_current_ff"]),
                        float(record["net_cash_value"]),
                    ),
                )
        if best_record is None:
            best_record = {
                "candidate_policy_name": "",
                "order_units": 0,
                "capital_deployed": 0.0,
                "missed_units": 0.0,
                "missed_units_reduced_vs_current_ff": 0.0,
                "protected_gp": 0.0,
                "excess_capital_above_target": 0.0,
                "net_cash_value": 0.0,
                "cash_roi": 0.0,
                "negative_cash_conversion_rows": 0,
                "production_recommendation": "KEEP_AS_ANALYSIS_ONLY",
                "reason": "No rows in this segment for the current certified input.",
            }
        records.append(
            {
                "low_soh_shadow_segment": segment,
                "row_count": row_count,
                "actual_sales_rows": int(current_segment["actual_units_sold"].gt(0.0).sum()) if row_count else 0,
                "actual_units_sold": round(float(current_segment["actual_units_sold"].sum()), 4) if row_count else 0.0,
                "current_ff_missed_units": round(current_missed, 4),
                "pl_missed_units": round(float(pl_segment["candidate_missed_units"].sum()), 4) if row_count else 0.0,
                "pl_allocation_units": int(pl_segment["candidate_order_units"].sum()) if row_count else 0,
                "pl_excess_units_above_target": round(float(pl_segment["candidate_excess_units_above_target"].sum()), 4) if row_count else 0.0,
                "best_candidate_policy_name": best_record["candidate_policy_name"],
                "best_candidate_order_units": best_record["order_units"],
                "best_candidate_capital_deployed": best_record["capital_deployed"],
                "best_candidate_missed_units": best_record["missed_units"],
                "missed_units_reduced_vs_current_ff": best_record["missed_units_reduced_vs_current_ff"],
                "protected_gp": best_record["protected_gp"],
                "excess_capital_above_target": best_record["excess_capital_above_target"],
                "net_cash_value": best_record["net_cash_value"],
                "cash_roi": best_record["cash_roi"],
                "negative_cash_conversion_rows": best_record["negative_cash_conversion_rows"],
                "production_recommendation": best_record["production_recommendation"],
                "reason": best_record["reason"],
            }
        )
    return pd.DataFrame(records).loc[:, SEGMENT_SCORECARD_COLUMNS]


def _eligible_segments_for_policy(policy_name: str) -> str:
    if policy_name in SEGMENTED_POLICY_ELIGIBLE_SEGMENTS:
        return "|".join(SEGMENTED_POLICY_ELIGIBLE_SEGMENTS[policy_name])
    if policy_name in {"NO_ORDER_0", "CURRENT_FF", "PL_ALLOCATION"}:
        return "COMPARISON_ONLY"
    return "BROAD_LOW_SOH_RULE"


def _order_cap_for_policy(policy_name: str, config: LowSohCounterfactualConfig) -> int:
    if policy_name == "NO_ORDER_0":
        return 0
    if policy_name in SEGMENTED_POLICY_NAMES or policy_name.startswith("ORDER_1_"):
        return 1
    if policy_name in {"ORDER_2_IF_ZERO_SOH_AND_FLOOR_REQUIRED", "ORDER_CAPPED_DEMAND_GAP_MAX_2", "ORDER_CAPPED_FLOOR_GAP_MAX_2"}:
        return 2
    if policy_name == "PL_ALLOCATION":
        return -1
    return int(config.max_auto_order_units)


def _shadow_recommendation(row: pd.Series, *, is_segmented: bool) -> tuple[str, str, int]:
    policy_name = str(row["candidate_policy_name"])
    row_count = max(float(row["row_count"]), 1.0)
    order_rows = float(row["order_rows"])
    missed_reduced = float(row["missed_units_reduced_vs_current_ff"])
    net_cash = float(row["net_cash_value"])
    excess_capital = float(row["excess_capital_above_target"])
    negative_rows = float(row["negative_cash_conversion_rows"])
    material_rows = float(row["material_excess_rows"])
    protected_gp = float(row["protected_gp"])
    breadth = order_rows / row_count
    if policy_name == "CURRENT_FF":
        return "KEEP_BASELINE", "Current FF is the certified baseline, not a shadow candidate.", 90
    if policy_name == "NO_ORDER_0":
        return "KEEP_AS_CONTROL", "No-order is retained as a control policy only.", 95
    if policy_name == "PL_ALLOCATION":
        return "REJECT_COMPARISON_ONLY", "PL allocation is an offline benchmark and cannot become a Stage 11 rule.", 95
    if not is_segmented:
        if breadth > 0.20:
            return "REJECT_TOO_BROAD", "Broad row count is too high for this shadow refinement pass.", 80
        return "REJECT_NOT_SEGMENTED", "This pass only promotes segmented low-SOH candidates to shadow testing.", 75
    if missed_reduced <= 0.0 or order_rows <= 0.0:
        return "REJECT_WEAK_EVIDENCE", "Segmented policy does not reduce missed units versus current FF.", 70
    if negative_rows > 0.0 or net_cash < 0.0:
        return "REJECT_NEGATIVE_CASH_CONVERSION", "One or more ordered rows have negative cash conversion.", 60
    if excess_capital > max(protected_gp, 25.0) or material_rows > max(1.0, order_rows * 0.10):
        return "REJECT_CAPITAL_DRAG", "Material target excess or capital drag remains too high.", 55
    if order_rows > 250.0:
        return "REJECT_TOO_BROAD", "Segmented rule still orders too many rows for shadow promotion.", 50
    return "PROMOTE_TO_SHADOW_CANDIDATE", "Segmented one-unit policy passes offline shadow guardrails; Stage 11 remains unchanged.", 10


def _segmented_recommendation_metrics_from_grid(grid: pd.DataFrame, policy_name: str) -> dict[str, object] | None:
    if policy_name not in SEGMENTED_POLICY_ELIGIBLE_SEGMENTS:
        return None
    policy_frame = grid.loc[grid["candidate_policy_name"].eq(policy_name)].copy()
    eligible = policy_frame.loc[policy_frame["low_soh_shadow_segment"].isin(SEGMENTED_POLICY_ELIGIBLE_SEGMENTS[policy_name])].copy()
    if eligible.empty:
        return {
            "candidate_policy_name": policy_name,
            "row_count": 0,
            "order_rows": 0,
            "order_units": 0,
            "capital_deployed": 0.0,
            "missed_units_reduced_vs_current_ff": 0.0,
            "excess_capital_above_target": 0.0,
            "net_cash_value": 0.0,
            "cash_roi": 0.0,
            "negative_cash_conversion_rows": 0,
            "material_excess_rows": 0,
            "protected_gp": 0.0,
        }
    current_frame = grid.loc[grid["candidate_policy_name"].eq("CURRENT_FF")].set_index("sku_number")
    current_eligible = current_frame.loc[eligible["sku_number"]]
    current_missed = float(current_eligible["candidate_missed_units"].sum())
    candidate_missed = float(eligible["candidate_missed_units"].sum())
    capital = float(eligible["candidate_capital_deployed"].sum())
    protected_gp = float(eligible["candidate_protected_gp"].sum())
    material_mask = eligible["candidate_result_label"].isin(["OVER_ALLOCATED_CAPITAL", "NEGATIVE_CASH_CONVERSION", "PACK_MOQ_FORCED_EXCESS"])
    return {
        "candidate_policy_name": policy_name,
        "row_count": int(eligible.shape[0]),
        "order_rows": int(eligible["candidate_order_units"].gt(0).sum()),
        "order_units": int(eligible["candidate_order_units"].sum()),
        "capital_deployed": round(capital, 2),
        "missed_units_reduced_vs_current_ff": round(current_missed - candidate_missed, 4),
        "excess_capital_above_target": round(float(eligible["candidate_excess_capital_above_target"].sum()), 2),
        "net_cash_value": round(float(eligible["candidate_net_cash_value"].sum()), 2),
        "cash_roi": round(float(_safe_ratio(pd.Series([protected_gp]), pd.Series([capital])).fillna(0.0).iloc[0]), 4),
        "negative_cash_conversion_rows": int(eligible["candidate_result_label"].eq("NEGATIVE_CASH_CONVERSION").sum()),
        "material_excess_rows": int(material_mask.sum()),
        "protected_gp": round(protected_gp, 2),
    }


def build_low_soh_shadow_policy_recommendations(
    scorecard: pd.DataFrame,
    grid: pd.DataFrame | None = None,
    *,
    config: LowSohCounterfactualConfig | None = None,
) -> pd.DataFrame:
    resolved = config or LowSohCounterfactualConfig()
    scorecard_by_policy = {str(row["candidate_policy_name"]): row for _, row in scorecard.iterrows()}
    records: list[dict[str, object]] = []
    for policy_name in POLICY_NAMES:
        if policy_name not in scorecard_by_policy:
            continue
        row = scorecard_by_policy[policy_name]
        is_segmented = policy_name in SEGMENTED_POLICY_NAMES
        recommendation_row = row
        if is_segmented and grid is not None:
            segmented_metrics = _segmented_recommendation_metrics_from_grid(grid, policy_name)
            if segmented_metrics is not None:
                recommendation_row = pd.Series(segmented_metrics)
        recommendation, reason, priority = _shadow_recommendation(recommendation_row, is_segmented=is_segmented)
        records.append(
            {
                "candidate_policy_name": policy_name,
                "eligible_segments": _eligible_segments_for_policy(policy_name),
                "order_cap_units": _order_cap_for_policy(policy_name, resolved),
                "row_count": int(recommendation_row["row_count"]),
                "order_rows": int(recommendation_row["order_rows"]),
                "order_units": int(recommendation_row["order_units"]),
                "capital_deployed": float(recommendation_row["capital_deployed"]),
                "missed_units_reduced_vs_current_ff": float(recommendation_row["missed_units_reduced_vs_current_ff"]),
                "excess_capital_above_target": float(recommendation_row["excess_capital_above_target"]),
                "net_cash_value": float(recommendation_row["net_cash_value"]),
                "cash_roi": float(recommendation_row["cash_roi"]),
                "recommendation": recommendation,
                "recommendation_reason": reason,
                "shadow_test_priority": priority,
                "guardrails_required": "source_certified_exact;offline_shadow_only;stage11_unchanged;order_cap_enforced;pack_size<=3;unit_cost<=threshold;no_material_target_excess;positive_cash_conversion",
                "should_promote_to_stage11": False,
                "should_promote_to_shadow": False,
            }
        )
    recommendations = pd.DataFrame(records)
    candidate_mask = recommendations["recommendation"].eq("PROMOTE_TO_SHADOW_CANDIDATE")
    if candidate_mask.any():
        ranked = recommendations.loc[candidate_mask].sort_values(
            ["missed_units_reduced_vs_current_ff", "net_cash_value", "cash_roi"],
            ascending=[False, False, False],
        )
        best_policy = str(ranked.iloc[0]["candidate_policy_name"])
        best_mask = recommendations["candidate_policy_name"].eq(best_policy)
        recommendations.loc[best_mask, "recommendation"] = "PROMOTE_TO_SHADOW"
        recommendations.loc[best_mask, "should_promote_to_shadow"] = True
        recommendations.loc[best_mask, "shadow_test_priority"] = 1
        lower_mask = candidate_mask & ~best_mask
        recommendations.loc[lower_mask, "recommendation"] = "KEEP_AS_ANALYSIS_ONLY"
        recommendations.loc[lower_mask, "recommendation_reason"] = "Acceptable segmented policy, but not the strongest shadow candidate in this scorecard."
        recommendations.loc[lower_mask, "shadow_test_priority"] = 20
    return recommendations.loc[:, SHADOW_RECOMMENDATION_COLUMNS]


def _failure_type(row: pd.Series) -> str:
    label = str(row["store_action_label"]).upper()
    demand_label = str(row["demand_evidence_label"]).upper()
    projected = float(row["projected_SOH_at_promo_start"])
    actual = float(row["actual_units_sold"])
    expected = float(row["expected_promo_demand"])
    if float(row["pack_size"]) > 3.0:
        return "PACK_SIZE_BLOCKED"
    if projected <= 0.0 and actual > 0.0:
        return "ZERO_SOH_REAL_DEMAND"
    if projected <= 1.0 and actual > 0.0:
        return "LOW_SOH_REAL_DEMAND"
    if float(row["avg_daily_units"]) > 0.0 and expected <= 1.0 and actual > expected:
        return "BASELINE_DEMAND_IGNORED"
    if "NO_PRIOR_PROMO_EVIDENCE" in label and actual > 0.0:
        return "NO_PRIOR_PROMO_EVIDENCE_BUT_SOLD"
    if "REDUCE_HOLDING" in label and actual > expected:
        return "REDUCE_HOLDING_BUT_DEMAND_SPIKED"
    if ("NO_DEMAND" in label or demand_label in {"NO_DEMAND", "NEVER_SOLD_IN_PROMO"}) and actual > 0.0:
        return "FALSE_NO_DEMAND"
    return "UNKNOWN"


def _policy_for_failure(failure_type: str) -> str:
    return {
        "ZERO_SOH_REAL_DEMAND": "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND",
        "LOW_SOH_REAL_DEMAND": "ORDER_1_IF_LOW_SOH_AND_ACTUAL_BASELINE_SIGNAL",
        "BASELINE_DEMAND_IGNORED": "ORDER_1_IF_LOW_SOH_AND_ACTUAL_BASELINE_SIGNAL",
        "NO_PRIOR_PROMO_EVIDENCE_BUT_SOLD": "ORDER_CAPPED_HYBRID_MAX_3",
        "REDUCE_HOLDING_BUT_DEMAND_SPIKED": "ORDER_CAPPED_DEMAND_GAP_MAX_2",
        "FALSE_NO_DEMAND": "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND",
        "PACK_SIZE_BLOCKED": "PACK_SIZE_REVIEW_ONLY",
    }.get(failure_type, "REVIEW_REQUIRED")


def build_missed_demand_diagnostic(rows: pd.DataFrame) -> pd.DataFrame:
    diagnostic = rows.copy()
    ff_available = diagnostic["projected_SOH_at_promo_start"].clip(lower=0.0).add(diagnostic["ff_current_order_units"].clip(lower=0.0))
    pl_available = diagnostic["projected_SOH_at_promo_start"].clip(lower=0.0).add(diagnostic["pl_allocation_qty"].clip(lower=0.0))
    diagnostic["ff_missed_units"] = diagnostic["actual_units_sold"].sub(ff_available).clip(lower=0.0).round(4)
    diagnostic["pl_missed_units"] = diagnostic["actual_units_sold"].sub(pl_available).clip(lower=0.0).round(4)
    diagnostic = diagnostic.loc[diagnostic["ff_missed_units"].gt(0.0)].copy()
    diagnostic["gross_profit_per_unit"] = diagnostic["actual_gross_profit_per_unit"]
    diagnostic["missed_gp_value"] = diagnostic["ff_missed_units"].mul(diagnostic["gross_profit_per_unit"]).round(2)
    diagnostic["likely_failure_type"] = diagnostic.apply(_failure_type, axis=1)
    diagnostic["recommended_policy_to_test"] = diagnostic["likely_failure_type"].map(_policy_for_failure)
    diagnostic["plain_english_reason"] = diagnostic.apply(
        lambda row: f"FF missed {row['ff_missed_units']:.0f} unit(s) with projected SOH {row['projected_SOH_at_promo_start']:.0f}, expected demand {row['expected_promo_demand']:.1f}, and actual sales {row['actual_units_sold']:.0f}.",
        axis=1,
    )
    return diagnostic.loc[:, MISSED_DEMAND_COLUMNS].reset_index(drop=True)


def _demand_bucket(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return pd.cut(values, bins=[-0.01, 0.0, 1.0, 2.0, 5.0, np.inf], labels=["ZERO", "LE_1", "LE_2", "LE_5", "GT_5"]).astype(str)


def build_actual_vs_expected_demand_diagnostic(rows: pd.DataFrame) -> pd.DataFrame:
    diagnostic = rows.loc[:, ["sku_number", "sku_description", "store_action_label", "demand_evidence_label", "expected_promo_demand", "actual_units_sold"]].copy()
    diagnostic["demand_error_units"] = diagnostic["actual_units_sold"].sub(diagnostic["expected_promo_demand"]).round(4)
    diagnostic["demand_error_abs_units"] = diagnostic["demand_error_units"].abs().round(4)
    diagnostic["demand_error_direction"] = np.select(
        [diagnostic["demand_error_units"].gt(0.0), diagnostic["demand_error_units"].lt(0.0)],
        ["ACTUAL_ABOVE_EXPECTED", "ACTUAL_BELOW_EXPECTED"],
        default="MATCHED",
    )
    diagnostic["expected_bucket"] = _demand_bucket(diagnostic["expected_promo_demand"])
    diagnostic["actual_bucket"] = _demand_bucket(diagnostic["actual_units_sold"])
    compression = diagnostic["expected_promo_demand"].le(1.0) & diagnostic["actual_units_sold"].gt(2.0)
    diagnostic["failure_type"] = np.where(compression, "DEMAND_COMPRESSED_TO_0_1_RANGE", "NO_COMPRESSION_FLAG")
    diagnostic["suggested_feature_fix"] = np.where(
        compression,
        "stronger baseline daily demand signal; zero-SOH hidden demand feature; brand/category promotion response feature; PL allocation signal as non-production benchmark only; recent sales velocity before promo; catalogue position / basket role feature; price discount elasticity bucket; supplier/brand recurring promo response memory",
        "No specific demand-compression fix flagged for this row.",
    )
    return diagnostic.loc[:, ACTUAL_EXPECTED_COLUMNS].reset_index(drop=True)


def build_low_soh_counterfactual_final_summary(
    *,
    scorecard: pd.DataFrame,
    shadow_recommendations: pd.DataFrame | None = None,
    manifest: dict[str, object],
) -> pd.DataFrame:
    best = scorecard.iloc[0] if not scorecard.empty else pd.Series(dtype="object")
    shadow = pd.Series(dtype="object")
    if shadow_recommendations is not None and not shadow_recommendations.empty and shadow_recommendations["should_promote_to_shadow"].astype(bool).any():
        shadow = shadow_recommendations.loc[shadow_recommendations["should_promote_to_shadow"].astype(bool)].iloc[0]
    return pd.DataFrame(
        [
            {
                "run_id": manifest.get("run_id", ""),
                "actual_review_source_status": manifest.get("actual_review_source_status", "UNKNOWN"),
                "source_certification_status": manifest.get("source_certification_status", "FAILED_MISSING_SOURCE"),
                "source_certification_reason": manifest.get("source_certification_reason", ""),
                "actual_review_csv_path_requested": manifest.get("actual_review_csv_path_requested", ""),
                "actual_review_csv_path_used": manifest.get("actual_review_csv_path_used", ""),
                "actual_review_file_hash_sha256": manifest.get("actual_review_file_hash_sha256", ""),
                "matched_sku_count": manifest.get("matched_sku_count", 0),
                "unmatched_feature_sku_count": manifest.get("unmatched_feature_sku_count", 0),
                "unmatched_actual_sku_count": manifest.get("unmatched_actual_sku_count", 0),
                "source_warning": source_warning(manifest),
                "best_candidate_policy": best.get("candidate_policy_name", ""),
                "score_100": best.get("score_100", 0.0),
                "current_missed_units": scorecard.loc[scorecard["candidate_policy_name"].eq("CURRENT_FF"), "missed_units"].iloc[0]
                if not scorecard.empty and scorecard["candidate_policy_name"].eq("CURRENT_FF").any()
                else 0.0,
                "best_policy_missed_units": best.get("missed_units", 0.0),
                "best_policy_missed_units_reduced": best.get("missed_units_reduced_vs_current_ff", 0.0),
                "capital_deployed": best.get("capital_deployed", 0.0),
                "net_cash_value": best.get("net_cash_value", 0.0),
                "production_recommendation": best.get("production_recommendation", ""),
                "recommended_shadow_policy": shadow.get("candidate_policy_name", ""),
                "shadow_recommendation": shadow.get("recommendation", ""),
                "should_promote_to_stage11": bool(shadow.get("should_promote_to_stage11", False)),
                "should_promote_to_shadow": bool(shadow.get("should_promote_to_shadow", False)),
            }
        ]
    )


def build_low_soh_counterfactual_tuner(
    *,
    feature_inspection_frame: pd.DataFrame,
    actual_review_frame: pd.DataFrame,
    allocation_report_frame: pd.DataFrame | None = None,
    config: LowSohCounterfactualConfig | None = None,
) -> LowSohCounterfactualResult:
    resolved = config or LowSohCounterfactualConfig()
    base = build_counterfactual_base_frame(
        feature_inspection_frame=feature_inspection_frame,
        actual_review_frame=actual_review_frame,
        allocation_report_frame=allocation_report_frame,
    )
    grid = build_low_soh_counterfactual_policy_grid(base, config=resolved)
    scorecard = build_low_soh_counterfactual_policy_scorecard(grid)
    segment_scorecard = build_low_soh_shadow_segment_scorecard(grid)
    shadow_recommendations = build_low_soh_shadow_policy_recommendations(scorecard, grid=grid, config=resolved)
    missed = build_missed_demand_diagnostic(base)
    actual_expected = build_actual_vs_expected_demand_diagnostic(base)
    return LowSohCounterfactualResult(base, grid, scorecard, segment_scorecard, shadow_recommendations, missed, actual_expected)


def write_low_soh_counterfactual_tuner(
    *,
    feature_inspection_csv_path: str | Path,
    actual_review_csv_path: str | Path,
    output_root: str | Path,
    allocation_report_csv_path: str | Path | None = None,
    config: LowSohCounterfactualConfig | None = None,
    run_id: str | None = None,
    allow_substitute_actual_review: bool = False,
    actual_review_substitute_csv_path: str | Path | None = None,
) -> LowSohCounterfactualArtifacts:
    source_resolution = resolve_actual_review_source(
        requested_actual_review_csv_path=actual_review_csv_path,
        allow_substitute_actual_review=allow_substitute_actual_review,
        substitute_actual_review_csv_path=actual_review_substitute_csv_path,
    )
    feature_frame = _read_csv(feature_inspection_csv_path)
    actual_frame = _read_csv(source_resolution.used_actual_review_csv_path) if source_resolution.used_actual_review_csv_path else pd.DataFrame()
    allocation_frame = _read_csv(allocation_report_csv_path) if allocation_report_csv_path else None
    manifest = build_input_source_manifest(
        run_id=_infer_run_id(output_root, run_id),
        feature_inspection_csv_path=feature_inspection_csv_path,
        feature_inspection_frame=feature_frame,
        allocation_report_csv_path=allocation_report_csv_path,
        allocation_report_frame=allocation_frame,
        actual_review_csv_path_requested=actual_review_csv_path,
        actual_review_csv_path_used=source_resolution.used_actual_review_csv_path,
        actual_review_source_status=source_resolution.actual_review_source_status,
        actual_review_frame=actual_frame,
    )
    if source_warning(manifest):
        print(SOURCE_WARNING_TEXT, file=sys.stderr)
    if certification_failed(manifest):
        raise LowSohCounterfactualPolicyTunerError(str(manifest["source_certification_reason"]))
    result = build_low_soh_counterfactual_tuner(
        feature_inspection_frame=feature_frame,
        actual_review_frame=actual_frame,
        allocation_report_frame=allocation_frame,
        config=config,
    )
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    grid_path = output / "low_soh_counterfactual_policy_grid.csv"
    scorecard_path = output / "low_soh_counterfactual_policy_scorecard.csv"
    segment_scorecard_path = output / "low_soh_shadow_segment_scorecard.csv"
    shadow_recommendations_path = output / "low_soh_shadow_policy_recommendations.csv"
    missed_path = output / "missed_demand_diagnostic.csv"
    actual_expected_path = output / "actual_vs_expected_demand_diagnostic.csv"
    final_summary_path = output / "low_soh_counterfactual_final_summary.csv"
    manifest_json_path, manifest_csv_path = write_input_source_manifest(manifest, output)
    result.policy_grid_frame.to_csv(grid_path, index=False)
    scorecard_with_provenance = add_provenance_columns(result.policy_scorecard_frame, manifest)
    segment_scorecard_with_provenance = add_provenance_columns(result.segment_scorecard_frame, manifest)
    shadow_recommendations_with_provenance = add_provenance_columns(result.shadow_policy_recommendations_frame, manifest)
    missed_with_provenance = add_provenance_columns(result.missed_demand_diagnostic_frame, manifest)
    actual_expected_with_provenance = add_provenance_columns(result.actual_vs_expected_demand_diagnostic_frame, manifest)
    final_summary = build_low_soh_counterfactual_final_summary(
        scorecard=scorecard_with_provenance,
        shadow_recommendations=shadow_recommendations_with_provenance,
        manifest=manifest,
    )
    scorecard_with_provenance.to_csv(scorecard_path, index=False)
    segment_scorecard_with_provenance.to_csv(segment_scorecard_path, index=False)
    shadow_recommendations_with_provenance.to_csv(shadow_recommendations_path, index=False)
    missed_with_provenance.to_csv(missed_path, index=False)
    actual_expected_with_provenance.to_csv(actual_expected_path, index=False)
    final_summary.to_csv(final_summary_path, index=False)
    return LowSohCounterfactualArtifacts(
        str(grid_path),
        str(scorecard_path),
        str(segment_scorecard_path),
        str(shadow_recommendations_path),
        str(missed_path),
        str(actual_expected_path),
        str(final_summary_path),
        str(manifest_json_path),
        str(manifest_csv_path),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline low-SOH counterfactual policy tuner.")
    parser.add_argument("--feature-inspection-csv", required=True)
    parser.add_argument("--actual-review-csv", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--allocation-report-csv")
    parser.add_argument("--allow-substitute-actual-review", action="store_true")
    parser.add_argument("--actual-review-substitute-csv")
    parser.add_argument("--max-auto-order-units", type=int, default=3)
    parser.add_argument("--max-pack-size", type=int, default=3)
    parser.add_argument("--max-unit-cost", type=float, default=60.0)
    parser.add_argument("--max-capital-drag-rate", type=float, default=250.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    artifacts = write_low_soh_counterfactual_tuner(
        feature_inspection_csv_path=args.feature_inspection_csv,
        actual_review_csv_path=args.actual_review_csv,
        actual_review_substitute_csv_path=args.actual_review_substitute_csv,
        allow_substitute_actual_review=args.allow_substitute_actual_review,
        allocation_report_csv_path=args.allocation_report_csv,
        output_root=args.output_root,
        run_id=args.run_id,
        config=LowSohCounterfactualConfig(
            max_auto_order_units=args.max_auto_order_units,
            max_pack_size=args.max_pack_size,
            max_unit_cost=args.max_unit_cost,
            max_capital_drag_rate=args.max_capital_drag_rate,
        ),
    )
    print("low_soh_counterfactual_policy_grid", artifacts.policy_grid_csv_path)
    print("low_soh_counterfactual_policy_scorecard", artifacts.policy_scorecard_csv_path)
    print("low_soh_shadow_segment_scorecard", artifacts.segment_scorecard_csv_path)
    print("low_soh_shadow_policy_recommendations", artifacts.shadow_policy_recommendations_csv_path)
    print("missed_demand_diagnostic", artifacts.missed_demand_diagnostic_csv_path)
    print("actual_vs_expected_demand_diagnostic", artifacts.actual_vs_expected_demand_diagnostic_csv_path)
    print("low_soh_counterfactual_final_summary", artifacts.final_summary_csv_path)
    print("input_source_manifest_json", artifacts.input_source_manifest_json_path)
    print("input_source_manifest_csv", artifacts.input_source_manifest_csv_path)


if __name__ == "__main__":
    main()
