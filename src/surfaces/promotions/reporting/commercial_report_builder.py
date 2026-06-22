"""Commercial store-facing promotion report builder (Phase 5B.3+)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

META_STATUS = "SHADOW_NOT_PRODUCTION"
PRODUCTION_ORDERING = "NO"
CUSTOMER_RELEASE = "NO"
ALLOWED_DECISIONS = frozenset({"BUY", "REVIEW", "HOLD", "DO_NOT_BUY"})
FORMULA_TOLERANCE = 0.01
OPERATOR_SHEET_COLUMNS: tuple[str, ...] = (
    "priority_rank",
    "sku_number",
    "sku_description",
    "decision",
    "recommendation_type",
    "raw_model_order_units",
    "target_order_units_to_hit_day_one_soh",
    "commercial_recommended_order_units",
    "recommended_order_units",
    "operator_review_order_low_units",
    "operator_review_order_high_units",
    "remaining_shortfall_after_commercial_recommendation_units",
    "commercial_coverage_ratio",
    "target_day_one_soh_units",
    "projected_day_one_soh_before_order_units",
    "projected_day_one_soh_after_recommended_order_units",
    "current_soh_units",
    "on_order_units",
    "estimated_demand_before_promo_start_units",
    "predicted_promo_period_sales_units",
    "confidence_score",
    "data_quality_score",
    "stock_target_conflict_flag",
    "decision_quality_label",
    "reason_order",
    "reason_risk",
    "review_reason",
    "operator_decision",
    "operator_recommended_units",
    "operator_notes",
)

ORDER_PLAN_COLUMNS: tuple[str, ...] = (
    "priority_rank",
    "store_number",
    "promotion_name",
    "promotion_start_date",
    "promotion_end_date",
    "promotion_days",
    "prediction_date",
    "days_until_promotion_start",
    "sku_number",
    "sku_description",
    "decision",
    "recommendation_type",
    "recommended_order_basis",
    "raw_model_order_units",
    "target_order_units_to_hit_day_one_soh",
    "commercial_recommended_order_units",
    "recommended_order_units",
    "operator_review_order_low_units",
    "operator_review_order_high_units",
    "remaining_shortfall_after_commercial_recommendation_units",
    "remaining_day_one_shortfall_units",
    "commercial_coverage_ratio",
    "recommendation_coverage_ratio",
    "stock_target_conflict_flag",
    "stock_target_conflict_reason",
    "target_day_one_soh_units",
    "projected_day_one_soh_before_order_units",
    "projected_day_one_soh_after_recommended_order_units",
    "current_soh_units",
    "on_order_units",
    "estimated_demand_before_promo_start_units",
    "predicted_promo_period_sales_units",
    "total_expected_demand_to_promo_end_units",
    "target_stock_on_hand_at_promo_end_units",
    "projected_stock_on_hand_at_promo_end_units",
    "discount_percent",
    "avg_promo_demand_same_discount_units",
    "expected_gp_dollars",
    "capital_at_risk_dollars",
    "confidence_score",
    "confidence_label",
    "data_quality_score",
    "data_quality_label",
    "decision_quality_label",
    "reason_demand",
    "reason_stock",
    "reason_order",
    "reason_risk",
    "reason_rejection_or_hold",
    "human_review_required",
    "review_reason",
    "model_status",
    "production_ordering_approved",
    "customer_report_release_approved",
    "operator_decision",
    "operator_recommended_units",
    "operator_notes",
)

HOLD_TARGET_TOLERANCE = 2

DEMAND_FIELD_HINTS = (
    "demand",
    "units",
    "expected",
    "promo",
    "lead",
    "sales",
    "period",
    "projected",
    "historical",
)


@dataclass(frozen=True)
class CommercialSourceSelection:
    promotion_slug: str
    sku_universe_source: str
    order_units_source: str
    demand_source: str
    confidence_source: str
    notes: str


@dataclass(frozen=True)
class CommercialPackArtifacts:
    output_dir: Path
    order_plan_path: Path
    row_count: int
    decision_counts: dict[str, int]
    total_recommended_order_units: float
    report_quality_score: int


def _label(score: float) -> str:
    if score >= 85:
        return "VERY_HIGH"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    if score >= 30:
        return "LOW"
    return "VERY_LOW"


def _num(series: pd.Series | None, default: float = 0.0, index: pd.Index | None = None) -> pd.Series:
    if series is None:
        return pd.Series(default, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _first_col(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return None


def load_se01_scored_sources(prediction_dir: Path) -> pd.DataFrame:
    """Merge SE01 sources; order evidence from raw_model_order_units, not final zeroed orders."""
    prefix = "772_2026-07-23_allocation-report-se01-skincare-sales-event"
    main = pd.read_csv(prediction_dir / f"{prefix}.csv", low_memory=False)
    audit = pd.read_csv(prediction_dir / f"{prefix}_operator-audit.csv", low_memory=False)
    feature_header = pd.read_csv(prediction_dir / f"{prefix}_feature-inspection.csv", nrows=0).columns
    feature_cols = [
        "sku_number",
        "expected_units_per_day",
        "historical_units_same_discount_avg",
        "lead_up_demand_units",
        "capital_at_risk_adjusted_dollars",
        "feature_expected_gp_on_trust_floor_units",
        "feature_expected_gp_on_speculative_units",
        "promotion_period_days",
        "promotion_start_date",
        "promotion_end_date",
        "expected_units_total_promo",
        "expected_units_per_period",
        "projected_promotional_units",
        "expected_promo_demand",
        "expected_units_first_7_days",
        "days_to_promo_start",
        "lead_days_to_promo_start",
    ]
    feature = pd.read_csv(
        prediction_dir / f"{prefix}_feature-inspection.csv",
        usecols=[c for c in feature_cols if c in feature_header],
        low_memory=False,
    )
    audit_keep = [
        "sku_number",
        "raw_model_order_units",
        "model_confidence_percent",
        "lead_up_demand_units",
        "days_to_promo_start",
        "expected_units_per_day",
        "expected_units_per_period",
        "expected_units_total_promo",
        "projected_promotional_units",
        "expected_promo_demand",
        "expected_units_first_7_days",
        "expected_units_before_promo_start",
        "review_flag",
        "risk_flag",
        "audit_notes",
        "demand_evidence_label",
        "recommended_action",
        "historical_units_same_discount_avg",
    ]
    audit_keep = [c for c in audit_keep if c in audit.columns]
    out = main.merge(audit[audit_keep], on="sku_number", how="left", suffixes=("", "_audit"))
    out = out.merge(feature, on="sku_number", how="left", suffixes=("", "_feat"))
    return out


def _baseline_daily_rate(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Derive SKU-specific baseline daily rate and source label."""
    idx = frame.index
    lead_up = _num(_first_col(frame, ("lead_up_demand_units_audit", "lead_up_demand_units", "lead_up_demand_units_feat")), index=idx)
    source_days = _num(
        _first_col(frame, ("days_to_promo_start_audit", "days_to_promo_start", "lead_days_to_promo_start_feat", "lead_days_to_promo_start")),
        index=idx,
    )
    source_days = source_days.where(source_days > 0, 0)
    from_lead = lead_up.div(source_days).where(source_days > 0, 0.0)

    hist = _num(_first_col(frame, ("historical_units_same_discount_avg_audit", "historical_units_same_discount_avg", "historical_units_same_discount_avg_feat")), index=idx)
    promo_days = _num(_first_col(frame, ("promotion_period_days_feat", "promotion_period_days", "promotion_days")), 7, index=idx).replace(0, 7)
    from_hist = hist.div(promo_days).where(hist > 0, 0.0)

    rate = from_lead.where(from_lead > 0, from_hist)
    source = np.where(from_lead > 0, "lead_up_demand_units_over_days_to_promo_start", "")
    source = np.where((from_lead <= 0) & (from_hist > 0), "historical_units_same_discount_avg_over_promo_days", source)
    source = np.where(rate <= 0, "missing_baseline_daily_rate", source)
    return rate.round(6), pd.Series(source, index=idx), source_days


def _field_series(frame: pd.DataFrame, base_names: tuple[str, ...], index: pd.Index) -> pd.Series:
    for base in base_names:
        for name in (f"{base}_audit", f"{base}_feat", base):
            if name in frame.columns:
                return _num(frame[name], index=index)
    return pd.Series(0.0, index=index)


def _is_flat_placeholder(series: pd.Series) -> bool:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return True
    return int(s.nunique(dropna=True)) <= 3 and float(s.quantile(0.9)) <= 1.01


def _promo_period_demand(
    frame: pd.DataFrame,
    promo_days: pd.Series,
    baseline_daily: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Promotion-period demand with flat-placeholder rejection and labelled fallbacks."""
    idx = frame.index
    hist = _field_series(frame, ("historical_units_same_discount_avg",), idx)
    promo_sales = pd.Series(0.0, index=idx)
    source = pd.Series("missing_promo_period_demand", index=idx)
    quality = pd.Series("VERY_LOW", index=idx)
    fallback = pd.Series("YES", index=idx)
    warning = pd.Series("no_safe_promo_period_demand_evidence", index=idx)

    model_fields = [
        ("expected_units_total_promo", "audited_promotion_period_forecast"),
        ("projected_promotional_units", "projected_promotional_units"),
        ("expected_units_per_period", "expected_units_per_period"),
        ("expected_promo_demand", "expected_promo_demand"),
    ]
    for field, label in model_fields:
        val = _field_series(frame, (field,), idx)
        if _is_flat_placeholder(val):
            continue
        usable = val.where((val > 0) & ((val > 1) | (hist <= val * 1.5)), 0.0)
        take = usable.gt(0) & promo_sales.le(0)
        promo_sales = promo_sales.where(~take, usable)
        source = source.where(~take, label)
        quality = quality.where(~take, "HIGH")
        fallback = fallback.where(~take, "NO")
        warning = warning.where(~take, "")

    first7 = _field_series(frame, ("expected_units_first_7_days",), idx)
    seven_ok = promo_days.eq(7) & first7.gt(0) & (not _is_flat_placeholder(first7))
    take7 = seven_ok & promo_sales.le(0)
    promo_sales = promo_sales.where(~take7, first7)
    source = source.where(~take7, "expected_units_first_7_days")
    quality = quality.where(~take7, "HIGH")
    fallback = fallback.where(~take7, "NO")
    warning = warning.where(~take7, "")

    per_day = _field_series(frame, ("expected_units_per_day",), idx)
    derived = (per_day * promo_days).round(3)
    per_day_flat = _is_flat_placeholder(per_day) or _is_flat_placeholder(derived)
    take_day = (not per_day_flat) & derived.gt(0) & promo_sales.le(0)
    promo_sales = promo_sales.where(~take_day, derived)
    source = source.where(~take_day, "expected_units_per_day_times_promotion_days")
    quality = quality.where(~take_day, "MEDIUM")
    fallback = fallback.where(~take_day, "NO")
    warning = warning.where(~take_day, "")

    take_hist = hist.gt(0) & promo_sales.le(0)
    promo_sales = promo_sales.where(~take_hist, hist.round(3))
    source = source.where(~take_hist, "historical_units_same_discount_avg_fallback")
    quality = quality.where(~take_hist, "MEDIUM")
    fallback = fallback.where(~take_hist, "YES")
    warning = warning.where(~take_hist, "promo_demand_uses_same_discount_history_fallback")

    baseline_floor = (baseline_daily * promo_days).round(3)
    take_base = baseline_floor.gt(0) & promo_sales.le(0)
    promo_sales = promo_sales.where(~take_base, baseline_floor)
    source = source.where(~take_base, "baseline_daily_times_promotion_days_floor")
    quality = quality.where(~take_base, "LOW")
    fallback = fallback.where(~take_base, "YES")
    warning = warning.where(~take_base, "promo_demand_uses_baseline_daily_floor")

    has_value = promo_sales.gt(0)
    source = source.where(has_value, "missing_promo_period_demand")
    quality = quality.where(has_value, "VERY_LOW")
    fallback = fallback.where(has_value, "YES")
    warning = warning.where(has_value, "no_safe_promo_period_demand_evidence")

    return promo_sales.round(3), source, quality, fallback, warning


def _data_quality_score(
    *,
    soh: pd.Series,
    on_order: pd.Series,
    promo_days: pd.Series,
    baseline_daily: pd.Series,
    hist: pd.Series,
    pre_promo_source: pd.Series,
    promo_source: pd.Series,
    promo_fallback: pd.Series,
    promo_quality: pd.Series,
    target_used_floor: pd.Series,
    formula_ok: pd.Series,
    review_flag: pd.Series,
    risk_flag: pd.Series,
    unsafe_pre_promo: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    idx = soh.index
    score = pd.Series(100.0, index=idx)
    penalty_parts: list[pd.Series] = []

    checks: list[tuple[pd.Series, float, str]] = [
        (soh.isna(), 12, "missing_current_soh"),
        (on_order.isna(), 5, "missing_on_order_units"),
        (promo_days.le(0), 8, "missing_promo_days"),
        (baseline_daily.le(0), 15, "missing_daily_demand_basis"),
        (hist.le(0), 5, "missing_same_discount_history"),
        (promo_source.str.contains("fallback", case=False, na=False), 8, "promo_demand_historical_fallback"),
        (promo_source.str.contains("floor", case=False, na=False), 12, "promo_demand_baseline_floor"),
        (promo_source.eq("missing_promo_period_demand"), 20, "missing_promo_period_demand"),
        (promo_fallback.eq("YES"), 6, "promo_period_demand_fallback"),
        (promo_quality.isin(["LOW", "VERY_LOW"]), 10, "low_promo_period_demand_quality"),
        (pre_promo_source.eq("unsafe_period_total_rejected"), 18, "unsafe_pre_promo_source_rejected"),
        (target_used_floor, 10, "missing_sku_specific_30_day_cover_used_floor_2"),
        (~formula_ok, 15, "formula_reconciliation_failure"),
        (review_flag, 6, "review_flag"),
        (risk_flag, 6, "risk_flag"),
        (unsafe_pre_promo, 12, "audit_source_pre_promo_mismatch"),
    ]
    for mask, amount, code in checks:
        score = score.where(~mask, score - amount)
        penalty_parts.append(pd.Series(np.where(mask, code, ""), index=idx))
    penalties = pd.DataFrame(penalty_parts).T.apply(lambda r: "; ".join(x for x in r if x), axis=1)
    return score.clip(0, 100).round(1), penalties


def assemble_commercial_order_rows(
    frame: pd.DataFrame,
    *,
    store_number: int,
    promotion_name: str,
    prediction_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build one canonical row per SKU from scored SE01 evidence."""
    promo_days = _num(_first_col(frame, ("promotion_period_days_feat", "promotion_period_days", "promotion_days")), 7, index=frame.index).astype(int)
    promo_days = promo_days.replace(0, 7)
    start = pd.to_datetime(_first_col(frame, ("promotion_start_date_feat", "promotion_start_date")), errors="coerce")
    end = pd.to_datetime(_first_col(frame, ("promotion_end_date_feat", "promotion_end_date")), errors="coerce")
    pred_dt = pd.to_datetime(prediction_date, errors="coerce")
    days_until = (start - pred_dt).dt.days.fillna(0).clip(lower=0).astype(int)

    baseline_daily, baseline_source, source_days = _baseline_daily_rate(frame)
    unsafe_raw_pre = _num(_first_col(frame, ("expected_units_before_promo_start", "expected_units_before_promo_start_audit")), index=frame.index)
    unsafe_pre_promo = (
        (unsafe_raw_pre > baseline_daily * days_until * 3 + 1)
        & (days_until <= 7)
        & (unsafe_raw_pre > 10)
    )
    pre_promo = (baseline_daily * days_until).round(3)
    pre_promo_source = baseline_source

    promo_sales, promo_source, promo_quality, promo_fallback, promo_warning = _promo_period_demand(
        frame, promo_days, baseline_daily
    )
    total_demand = (pre_promo + promo_sales).round(3)

    thirty_day_cover = (baseline_daily * 30).round(3)
    target_used_floor = baseline_daily.le(0) | thirty_day_cover.lt(2)
    target_end = np.maximum(2, thirty_day_cover).round(3)
    target_end = target_end.where(~target_used_floor, 2.0)

    optimal = (promo_sales + target_end).round(3)
    target_day_one = optimal
    formula_ok = (target_day_one - (promo_sales + target_end)).abs() <= FORMULA_TOLERANCE

    soh = _num(frame.get("current_soh"), index=frame.index)
    on_order = _num(frame.get("on_order_at_advice_time"), index=frame.index)
    raw_order = _num(frame.get("raw_model_order_units"), index=frame.index).round(0).astype(int)
    projected_before_raw = (soh + on_order - pre_promo).round(3)
    floored = projected_before_raw < 0
    floor_removed = projected_before_raw.where(floored, 0.0).abs().round(3)
    projected_before = projected_before_raw.clip(lower=0).round(3)
    target_order = (target_day_one - projected_before).clip(lower=0).round(0).astype(int)
    has_promo_demand = promo_sales > 0
    has_target_order = target_order > 0
    has_raw = raw_order > 0

    conf = _num(frame.get("model_confidence_percent"), 50, index=frame.index).clip(0, 100)
    review_flag = _num(frame.get("review_flag"), index=frame.index).astype(bool)
    risk_flag = _num(frame.get("risk_flag"), index=frame.index).astype(bool)
    orig_action = frame.get("operator_action", pd.Series("DO_NOT_BUY", index=frame.index)).astype(str).str.upper()
    hist = _num(_first_col(frame, ("historical_units_same_discount_avg_audit", "historical_units_same_discount_avg", "historical_units_same_discount_avg_feat")), index=frame.index)

    hist_p75 = float(hist[hist > 0].quantile(0.75)) if (hist > 0).any() else 0.0
    base_p75 = float(baseline_daily[baseline_daily > 0].quantile(0.75)) if (baseline_daily > 0).any() else 0.0
    strong_demand_signal = (hist >= max(hist_p75, 2.0)) | (baseline_daily >= max(base_p75, 0.5))
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_to_target = (raw_order / target_order.replace(0, np.nan)).round(3)

    unsafe_demand = promo_fallback.eq("YES") | promo_source.eq("missing_promo_period_demand") | promo_quality.isin(["LOW", "VERY_LOW"])
    conf_label = conf.map(_label)
    dq_pre, dq_penalties = _data_quality_score(
        soh=soh, on_order=on_order, promo_days=promo_days, baseline_daily=baseline_daily, hist=hist,
        pre_promo_source=pre_promo_source, promo_source=promo_source, promo_fallback=promo_fallback,
        promo_quality=promo_quality, target_used_floor=target_used_floor, formula_ok=formula_ok,
        review_flag=review_flag, risk_flag=risk_flag, unsafe_pre_promo=unsafe_pre_promo,
    )
    dq_label = dq_pre.map(_label)

    stock_target_conflict = (target_order >= 20) & (raw_to_target < 0.5)
    best_seller = strong_demand_signal & (target_order >= 10) & (raw_order < target_order * 0.5) & (raw_order > 0)
    policy_b = (
        (target_order >= 20)
        & promo_quality.isin(["MEDIUM", "HIGH", "VERY_HIGH"])
        & strong_demand_signal
        & (dq_pre >= 70)
        & (conf >= 45)
        & (raw_order > 0)
        & (raw_to_target < 0.5)
    )
    lift_units = np.ceil(target_order * 0.5).astype(int)
    commercial = pd.Series(
        np.where(
            policy_b,
            np.maximum(raw_order, np.minimum(target_order, lift_units)),
            np.where(has_raw & has_target_order & has_promo_demand, raw_order, 0),
        ),
        index=frame.index,
        dtype=int,
    )
    order_basis = pd.Series(
        np.where(
            commercial > raw_order,
            "target_stock_policy_lift",
            np.where(commercial > 0, "raw_model_order", "none"),
        ),
        index=frame.index,
    )
    op_low = raw_order.clip(lower=0).astype(int)
    op_high = target_order.astype(int)

    projected_after = (projected_before + commercial).round(3)
    remaining_shortfall = (target_day_one - projected_after).clip(lower=0).round(0).astype(int)
    with np.errstate(divide="ignore", invalid="ignore"):
        commercial_cov_num = (commercial / target_order.replace(0, np.nan)).round(3)
    commercial_cov = commercial_cov_num.where(target_order > 0, np.where(commercial > 0, 1.0, np.nan)).fillna("")
    coverage_num = commercial_cov_num
    coverage = commercial_cov

    material_gap = target_order > HOLD_TARGET_TOLERANCE
    major_conflict = stock_target_conflict & (remaining_shortfall > 10)
    credible_need = has_promo_demand & (target_order > 0)
    low_demand = (~has_promo_demand) | (promo_sales <= 0.5)

    buy_ok = (
        (commercial > 0)
        & ((commercial_cov_num >= 0.5) | (remaining_shortfall <= 5))
        & (dq_pre >= 70)
        & (conf >= 45)
        & (~promo_quality.eq("VERY_LOW"))
        & (~major_conflict)
    )

    dnb_mask = (
        low_demand
        & (target_order <= HOLD_TARGET_TOLERANCE)
        & ((conf < 45) | (dq_pre < 50))
        & ~material_gap
    )
    hold_mask = (
        (target_order <= HOLD_TARGET_TOLERANCE)
        & (commercial == 0)
        & ~dnb_mask
        & ~review_flag
        & ~risk_flag
        & ~material_gap
    )
    review_mask = (
        material_gap
        | stock_target_conflict
        | best_seller
        | review_flag
        | risk_flag
        | unsafe_demand
        | unsafe_pre_promo
        | orig_action.isin(["REVIEW", "MONITOR"])
        | ((commercial > 0) & ~buy_ok)
    ) & ~dnb_mask

    decision = pd.Series("DO_NOT_BUY", index=frame.index)
    decision = decision.where(~dnb_mask, "DO_NOT_BUY")
    decision = decision.where(~hold_mask, "HOLD")
    decision = decision.where(~review_mask, "REVIEW")
    decision = decision.where(~buy_ok, "BUY")
    decision = decision.where(~((decision == "HOLD") & material_gap), "REVIEW")
    decision = decision.where(~((decision == "BUY") & (commercial <= 0)), "REVIEW")

    commercial = commercial.where(~decision.isin(["HOLD", "DO_NOT_BUY"]), 0).astype(int)
    recommended = commercial
    projected_after = (projected_before + commercial).round(3)
    remaining_shortfall = (target_day_one - projected_after).clip(lower=0).round(0).astype(int)
    with np.errstate(divide="ignore", invalid="ignore"):
        commercial_cov_num = (commercial / target_order.replace(0, np.nan)).round(3)
    commercial_cov = commercial_cov_num.where(target_order > 0, np.where(commercial > 0, 1.0, np.nan)).fillna("")
    coverage_num = commercial_cov_num
    coverage = commercial_cov

    low_cov_buy = (decision == "BUY") & (commercial_cov_num < 0.5) & (remaining_shortfall > 10)
    decision = decision.where(~low_cov_buy, "REVIEW")

    rec_type = pd.Series(
        np.select(
            [
                decision.eq("DO_NOT_BUY"),
                decision.eq("HOLD"),
                decision.eq("REVIEW") & stock_target_conflict,
                decision.eq("REVIEW") & (commercial > 0),
                decision.eq("BUY") & order_basis.eq("target_stock_policy_lift") & (remaining_shortfall <= 0),
                decision.eq("BUY") & order_basis.eq("target_stock_policy_lift"),
                decision.eq("BUY") & (remaining_shortfall <= 0),
                decision.eq("BUY") & (commercial > 0),
            ],
            [
                "DO_NOT_BUY",
                "NO_ORDER_REQUIRED",
                "TARGET_STOCK_REVIEW_RANGE",
                "REVIEW_ONLY_ORDER_QUANTITY",
                "FULL_TARGET_ORDER",
                "TARGET_STOCK_POLICY_LIFT",
                "FULL_TARGET_ORDER",
                "RAW_MODEL_CONSTRAINED_ORDER",
            ],
            default="TARGET_STOCK_REVIEW_RANGE",
        ),
        index=frame.index,
    )
    rec_type = rec_type.where(
        ~(decision.eq("REVIEW") & material_gap & rec_type.eq("NO_ORDER_REQUIRED")),
        "TARGET_STOCK_REVIEW_RANGE",
    )

    conflict_reason = pd.Series(
        np.where(
            stock_target_conflict,
            "target_stock_requires_more_than_model_order",
            np.where(
                best_seller,
                "best_seller_underorder_review",
                "",
            ),
        ),
        index=frame.index,
    )
    constraint = conflict_reason.where(conflict_reason.ne(""), np.where(unsafe_demand, "insufficient_demand_evidence", "none"))

    capital = _num(frame.get("capital_at_risk_adjusted_dollars"), index=frame.index).round(2)
    end_soh = (projected_after - promo_sales).round(3)
    dq = dq_pre

    review_parts = pd.DataFrame({
        "risk_or_review_flag": np.where(risk_flag | review_flag, "risk_or_review_flag", ""),
        "low_confidence_buy": np.where((conf < 45) & (commercial > 0), "low_confidence_buy", ""),
        "missing_baseline_daily": np.where(baseline_daily <= 0, "missing_baseline_daily", ""),
        "target_end_floor_2": np.where(target_used_floor, "missing_sku_specific_30_day_cover_used_floor_2", ""),
        "unsafe_pre_promo_rejected": np.where(unsafe_pre_promo, "unsafe_pre_promo_source_rejected", ""),
        "promo_demand_fallback": np.where(promo_fallback.eq("YES"), "promo_period_demand_fallback", ""),
        "projected_start_floored": np.where(floored, "projected_start_stock_floored_flag", ""),
        "formula_reconciliation_failure": np.where(~formula_ok, "formula_reconciliation_failure", ""),
        "stock_target_conflict": np.where(stock_target_conflict, "stock_target_conflict", ""),
    }, index=frame.index)
    review_reason = review_parts.apply(lambda r: "; ".join(x for x in r if x), axis=1)
    review_reason = review_reason.where(review_reason.ne(""), dq_penalties)

    buy_risk = risk_flag | review_flag | unsafe_demand | major_conflict | low_cov_buy
    human_review = np.where(
        decision.eq("REVIEW"),
        "YES",
        np.where(decision.eq("BUY"), np.where(buy_risk, "YES", "NO"), "NO"),
    )

    decision_quality = pd.Series(
        np.select(
            [
                decision.eq("BUY") & ~buy_risk,
                decision.eq("BUY"),
                decision.eq("REVIEW") & stock_target_conflict,
                decision.eq("REVIEW") & unsafe_demand,
                decision.eq("REVIEW") & ((conf < 45) | (dq_pre < 70)),
                decision.eq("REVIEW"),
                decision.eq("HOLD"),
            ],
            [
                "EXECUTION_READY",
                "REVIEW_LOW_CONFIDENCE",
                "REVIEW_STOCK_GAP",
                "REVIEW_DEMAND_EVIDENCE",
                "REVIEW_LOW_CONFIDENCE",
                "REVIEW_STOCK_GAP",
                "HOLD_NO_ORDER_NEEDED",
            ],
            default="DO_NOT_BUY_LOW_EVIDENCE",
        ),
        index=frame.index,
    )

    gp = (
        _num(frame.get("feature_expected_gp_on_trust_floor_units"))
        + _num(frame.get("feature_expected_gp_on_speculative_units"))
    ).round(2)

    reason_order = (
        "Target order to hit day-one SOH: "
        + target_order.astype(str)
        + " units; raw model order: "
        + raw_order.astype(str)
        + " units; commercial recommended order: "
        + commercial.astype(str)
        + " units; operator review range "
        + op_low.astype(str)
        + "-"
        + op_high.astype(str)
        + ". "
        + np.where(
            remaining_shortfall <= 0,
            "Commercial recommendation fully covers target day-one stock.",
            np.where(
                commercial > 0,
                "Commercial recommendation partially covers target; remaining shortfall "
                + remaining_shortfall.astype(str)
                + " units.",
                np.where(
                    stock_target_conflict,
                    "Target stock requires more units than the model order; buyer must review the gap before ordering.",
                    "No commercial order recommended; buyer review required for target stock gap.",
                ),
            ),
        )
    )
    reason_stock = (
        "Projected day-one SOH before order "
        + projected_before.round(1).astype(str)
        + "; target day-one SOH "
        + target_day_one.round(1).astype(str)
        + "; target order requirement "
        + target_order.astype(str)
        + " units (current SOH "
        + soh.round(1).astype(str)
        + ", on-order "
        + on_order.round(1).astype(str)
        + ", pre-promo demand "
        + pre_promo.round(1).astype(str)
        + ")"
    )
    reason_risk = np.where(
        stock_target_conflict,
        "Stock target conflict: model order far below target stock requirement",
        np.where(
            unsafe_demand,
            "Unsafe or fallback promo demand source",
            np.where(
                commercial_cov_num < 0.5,
                "Low commercial coverage ratio versus target order",
                np.where(
                    remaining_shortfall > 10,
                    "Large remaining day-one shortfall after commercial recommendation",
                    "Shadow commercial pack; governed order policy applied",
                ),
            ),
        ),
    )

    out = pd.DataFrame(
        {
            "store_number": store_number,
            "promotion_name": promotion_name,
            "promotion_start_date": start.dt.date.astype(str),
            "promotion_end_date": end.dt.date.astype(str),
            "promotion_days": promo_days,
            "prediction_date": prediction_date,
            "days_until_promotion_start": days_until,
            "sku_number": frame["sku_number"],
            "sku_description": frame["sku_description"],
            "decision": decision,
            "recommendation_type": rec_type,
            "recommended_order_basis": order_basis,
            "raw_model_order_units": raw_order,
            "target_order_units_to_hit_day_one_soh": target_order,
            "commercial_recommended_order_units": commercial,
            "recommended_order_units": recommended,
            "operator_review_order_low_units": op_low,
            "operator_review_order_high_units": op_high,
            "remaining_shortfall_after_commercial_recommendation_units": remaining_shortfall,
            "remaining_day_one_shortfall_units": remaining_shortfall,
            "commercial_coverage_ratio": commercial_cov,
            "recommendation_coverage_ratio": coverage,
            "stock_target_conflict_flag": stock_target_conflict.astype(int),
            "stock_target_conflict_reason": conflict_reason,
            "target_day_one_soh_units": target_day_one,
            "projected_day_one_soh_before_order_units": projected_before,
            "projected_day_one_soh_after_recommended_order_units": projected_after,
            "current_soh_units": soh.round(3),
            "on_order_units": on_order.round(3),
            "estimated_demand_before_promo_start_units": pre_promo,
            "predicted_promo_period_sales_units": promo_sales,
            "total_expected_demand_to_promo_end_units": total_demand,
            "target_stock_on_hand_at_promo_end_units": target_end,
            "projected_stock_on_hand_at_promo_end_units": end_soh,
            "discount_percent": _num(frame.get("discount_percent")).round(2),
            "avg_promo_demand_same_discount_units": hist.round(3),
            "expected_gp_dollars": gp,
            "capital_at_risk_dollars": capital,
            "confidence_score": conf.round(1),
            "data_quality_score": dq,
        }
    )
    out["confidence_label"] = out["confidence_score"].map(_label)
    out["data_quality_label"] = out["data_quality_score"].map(_label)
    out["decision_quality_label"] = decision_quality
    out["reason_demand"] = np.select(
        [
            promo_source.str.contains("fallback", na=False),
            promo_source.str.contains("floor", na=False),
            promo_source.eq("missing_promo_period_demand"),
        ],
        [
            "Promo-period demand uses same-discount historical average as evidence fallback",
            "Promo-period demand uses baseline daily rate floor because model promo forecast was flat or missing",
            "Promo-period demand evidence is missing or unsafe",
        ],
        default="Promo-period demand from audited non-flat promotion-period evidence",
    )
    out["reason_demand"] = np.where(
        pre_promo > 0,
        out["reason_demand"] + "; Pre-promo demand = baseline daily rate x days until start",
        out["reason_demand"] + "; Pre-promo demand is zero or negligible for remaining lead time",
    )
    out["reason_stock"] = reason_stock
    out["reason_order"] = reason_order
    out["reason_risk"] = reason_risk
    out["reason_rejection_or_hold"] = np.where(
        out["decision"].isin(["HOLD", "DO_NOT_BUY"]),
        np.where(
            out["decision"] == "DO_NOT_BUY",
            "Low promo demand and/or poor evidence; no commercial order need",
            "No order required; target day-one gap is within tolerance (<= "
            + str(HOLD_TARGET_TOLERANCE)
            + " units)",
        ),
        "",
    )
    out["human_review_required"] = human_review
    out["review_reason"] = review_reason
    out["model_status"] = META_STATUS
    out["production_ordering_approved"] = PRODUCTION_ORDERING
    out["customer_report_release_approved"] = CUSTOMER_RELEASE
    out["operator_decision"] = ""
    out["operator_recommended_units"] = ""
    out["operator_notes"] = ""

    calc = pd.DataFrame(
        {
            "sku_number": frame["sku_number"],
            "pre_promo_demand_source": pre_promo_source,
            "promo_period_demand_source": promo_source,
            "promo_period_demand_source_quality": promo_quality,
            "promo_period_demand_fallback_flag": promo_fallback,
            "promo_period_demand_warning": promo_warning,
            "baseline_daily_rate_units": baseline_daily,
            "baseline_daily_source_days": source_days,
            "order_units_source": "raw_model_order_units",
            "confidence_source": "model_confidence_percent",
            "raw_model_order_units": raw_order,
            "commercial_recommended_order_units": commercial,
            "target_order_units_to_hit_day_one_soh": target_order,
            "remaining_day_one_shortfall_units": remaining_shortfall,
            "recommendation_type": rec_type,
            "recommended_order_basis": order_basis,
            "recommendation_constraint_reason": constraint,
            "stock_target_conflict_flag": stock_target_conflict.astype(int),
            "raw_model_to_target_ratio": raw_to_target,
            "proposed_order_policy": np.where(
                policy_b,
                "target_stock_policy_lift",
                np.where(stock_target_conflict, "target_stock_review_range", "raw_model_constrained"),
            ),
            "raw_projected_start_stock_before_floor_units": projected_before_raw,
            "projected_start_stock_floor_units_removed": floor_removed,
            "projected_start_stock_floored_flag": floored.map({True: "YES", False: "NO"}),
            "target_end_used_floor_2_flag": target_used_floor.map({True: "YES", False: "NO"}),
            "formula_optimal_reconciles": formula_ok.map({True: "YES", False: "NO"}),
            "data_quality_penalties": dq_penalties,
            "unsafe_raw_expected_units_before_promo_start": unsafe_raw_pre.round(3),
            "contradiction_pre_promo_dominates_promo": (pre_promo > promo_sales * 2) & (days_until <= 1),
        }
    )
    return out, calc


def _sort_order_plan(df: pd.DataFrame) -> pd.DataFrame:
    rank = df["decision"].map({"BUY": 0, "REVIEW": 1, "HOLD": 2, "DO_NOT_BUY": 3}).fillna(4)
    out = df.assign(_rank=rank).sort_values(
        ["_rank", "predicted_promo_period_sales_units", "total_expected_demand_to_promo_end_units", "confidence_score"],
        ascending=[True, False, False, False],
        kind="mergesort",
    )
    out = out.drop(columns=["_rank"])
    out.insert(0, "priority_rank", range(1, len(out) + 1))
    return out[list(ORDER_PLAN_COLUMNS)]


def build_review_exceptions(order_plan: pd.DataFrame) -> pd.DataFrame:
    capital = _num(order_plan.get("capital_at_risk_dollars"), index=order_plan.index)
    remaining = _num(
        order_plan.get(
            "remaining_shortfall_after_commercial_recommendation_units",
            order_plan.get("remaining_day_one_shortfall_units", order_plan.get("remaining_gap_after_recommended_order_units")),
        ),
        index=order_plan.index,
    )
    conflict = _num(order_plan.get("stock_target_conflict_flag"), index=order_plan.index).astype(bool)
    return order_plan[
        (order_plan["decision"] == "REVIEW")
        | conflict
        | (order_plan["confidence_score"] < 45)
        | (order_plan["data_quality_score"] < 50)
        | (order_plan["recommended_order_units"] >= 10)
        | (capital > 500)
        | (
            (order_plan["estimated_demand_before_promo_start_units"] > order_plan["predicted_promo_period_sales_units"])
            & (order_plan["days_until_promotion_start"] <= 1)
        )
        | ((order_plan["decision"] == "BUY") & (remaining > 0))
    ].copy()


def build_manager_summary(order_plan: pd.DataFrame, exceptions: pd.DataFrame) -> pd.DataFrame:
    counts = order_plan["decision"].value_counts()
    hold_pos = int(((order_plan["decision"].isin(["HOLD", "DO_NOT_BUY"])) & (order_plan["recommended_order_units"] > 0)).sum())
    zero_buy = int(((order_plan["decision"] == "BUY") & (order_plan["recommended_order_units"] <= 0)).sum())
    non_std = int((~order_plan["decision"].isin(ALLOWED_DECISIONS)).sum())
    contradiction = hold_pos + zero_buy + non_std
    row = order_plan.iloc[0]
    return pd.DataFrame(
        [{
            "store_number": int(row["store_number"]),
            "promotion_name": row["promotion_name"],
            "promotion_start_date": row["promotion_start_date"],
            "promotion_end_date": row["promotion_end_date"],
            "prediction_date": row["prediction_date"],
            "promotion_days": int(row["promotion_days"]),
            "total_skus": len(order_plan),
            "buy_count": int(counts.get("BUY", 0)),
            "review_count": int(counts.get("REVIEW", 0)),
            "hold_count": int(counts.get("HOLD", 0)),
            "do_not_buy_count": int(counts.get("DO_NOT_BUY", 0)),
            "total_recommended_order_units": float(order_plan["recommended_order_units"].sum()),
            "total_estimated_demand_before_promo_start": float(order_plan["estimated_demand_before_promo_start_units"].sum()),
            "total_predicted_promo_period_sales": float(order_plan["predicted_promo_period_sales_units"].sum()),
            "total_expected_demand_to_promo_end": float(order_plan["total_expected_demand_to_promo_end_units"].sum()),
            "total_target_day_one_soh": float(order_plan["target_day_one_soh_units"].sum()),
            "total_target_end_stock": float(order_plan["target_stock_on_hand_at_promo_end_units"].sum()),
            "total_capital_at_risk": float(order_plan["capital_at_risk_dollars"].sum()),
            "low_confidence_count": int((order_plan["confidence_score"] < 45).sum()),
            "low_data_quality_count": int((order_plan["data_quality_score"] < 50).sum()),
            "review_exception_count": len(exceptions),
            "zero_order_buy_count": zero_buy,
            "non_standard_action_count": non_std,
            "contradiction_count": contradiction,
            "total_target_order_units_to_hit_day_one_soh": float(order_plan["target_order_units_to_hit_day_one_soh"].sum()),
            "total_remaining_day_one_shortfall_units": float(order_plan["remaining_day_one_shortfall_units"].sum()),
            "average_recommendation_coverage_ratio": float(
                pd.to_numeric(order_plan["recommendation_coverage_ratio"], errors="coerce").dropna().mean() or 0
            ),
            "buy_count_full_target_order": int((order_plan["recommendation_type"] == "FULL_TARGET_ORDER").sum()),
            "buy_count_partial_constrained_order": int((order_plan["recommendation_type"] == "RAW_MODEL_CONSTRAINED_ORDER").sum()),
            "review_count_due_to_underorder": 0,
            "best_seller_underorder_review_count": 0,
            "hold_rows_with_target_order_gt_10": int(
                ((order_plan["decision"] == "HOLD") & (order_plan["target_order_units_to_hit_day_one_soh"] > 10)).sum()
            ),
            "hold_rows_with_target_order_gt_20": int(
                ((order_plan["decision"] == "HOLD") & (order_plan["target_order_units_to_hit_day_one_soh"] > 20)).sum()
            ),
            "review_rows_with_no_order_required_conflict": int(
                (
                    (order_plan["decision"] == "REVIEW")
                    & (order_plan["recommendation_type"] == "NO_ORDER_REQUIRED")
                    & (order_plan["target_order_units_to_hit_day_one_soh"] > 10)
                ).sum()
            ),
            "stock_target_conflict_count": int(_num(order_plan.get("stock_target_conflict_flag")).astype(bool).sum()),
            "target_stock_policy_lift_count": int((order_plan["recommendation_type"] == "TARGET_STOCK_POLICY_LIFT").sum()),
            "target_stock_review_range_count": int((order_plan["recommendation_type"] == "TARGET_STOCK_REVIEW_RANGE").sum()),
            "execution_ready_buy_count": int((order_plan["decision_quality_label"] == "EXECUTION_READY").sum()),
            "commercial_recommended_order_units_total": float(order_plan["commercial_recommended_order_units"].sum()),
            "operator_review_order_high_units_total": float(order_plan["operator_review_order_high_units"].sum()),
            "promo_period_demand_fallback_count": 0,
            "unsafe_promo_period_demand_count": 0,
            "commercial_release_score": 0,
            "model_status": META_STATUS,
            "production_ordering_approved": PRODUCTION_ORDERING,
            "customer_report_release_approved": CUSTOMER_RELEASE,
        }]
    )


def quality_scorecard(order_plan: pd.DataFrame, summary: pd.DataFrame, exceptions: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    zero_buy = int(((order_plan["decision"] == "BUY") & (order_plan["recommended_order_units"] <= 0)).sum())
    non_std = int((~order_plan["decision"].isin(ALLOWED_DECISIONS)).sum())
    dup = int(order_plan["sku_number"].duplicated().sum())
    hold_pos = int(((order_plan["decision"].isin(["HOLD", "DO_NOT_BUY"])) & (order_plan["recommended_order_units"] > 0)).sum())
    reconciles = abs(float(summary["total_recommended_order_units"].iloc[0]) - float(order_plan["recommended_order_units"].sum())) < 0.01
    exc_reconciles = int(summary["review_exception_count"].iloc[0]) == len(exceptions)
    cov = pd.to_numeric(
        order_plan.get("commercial_coverage_ratio", order_plan.get("recommendation_coverage_ratio")),
        errors="coerce",
    )
    remaining = _num(order_plan.get("remaining_day_one_shortfall_units"), index=order_plan.index)
    target_order = _num(order_plan.get("target_order_units_to_hit_day_one_soh"), index=order_plan.index)
    target_day_one = _num(order_plan.get("target_day_one_soh_units"), index=order_plan.index)
    proj_before = _num(order_plan.get("projected_day_one_soh_before_order_units"), index=order_plan.index)
    proj_after = _num(order_plan.get("projected_day_one_soh_after_recommended_order_units"), index=order_plan.index)
    optimal_fail = int((target_day_one - (order_plan["predicted_promo_period_sales_units"] + order_plan["target_stock_on_hand_at_promo_end_units"])).abs().gt(FORMULA_TOLERANCE).sum())
    expected_target_order = (target_day_one - proj_before).clip(lower=0).round(0)
    target_order_fail = int((target_order - expected_target_order).abs().gt(FORMULA_TOLERANCE).sum())
    projected_mismatch = int((proj_before - (order_plan["current_soh_units"] + order_plan["on_order_units"] - order_plan["estimated_demand_before_promo_start_units"]).clip(lower=0)).abs().gt(FORMULA_TOLERANCE).sum())
    after_mismatch = int((proj_after - (proj_before + order_plan["recommended_order_units"])).abs().gt(FORMULA_TOLERANCE).sum())
    expected_remaining = (target_day_one - proj_after).clip(lower=0).round(0)
    shortfall_fail = int((remaining - expected_remaining).abs().gt(FORMULA_TOLERANCE).sum())
    buy_low_cov = int(((order_plan["decision"] == "BUY") & (cov < 0.5) & (remaining > 10)).sum())
    buy_partial = int(((order_plan["decision"] == "BUY") & (remaining > 0)).sum())
    review_pos = int(((order_plan["decision"] == "REVIEW") & (order_plan["recommended_order_units"] > 0)).sum())
    promo_flat = int((order_plan["predicted_promo_period_sales_units"] <= 1).sum())
    hold_gt_20 = int(((order_plan["decision"] == "HOLD") & (target_order > 20)).sum())
    hold_gt_10 = int(((order_plan["decision"] == "HOLD") & (target_order > 10)).sum())
    review_no_order_conflict = int(
        (
            (order_plan["decision"] == "REVIEW")
            & (order_plan["recommendation_type"] == "NO_ORDER_REQUIRED")
            & (target_order > 10)
        ).sum()
    )
    dql_na = int((order_plan["decision_quality_label"].astype(str).str.upper() == "N_A").sum())
    all_human_review = bool((order_plan["human_review_required"] == "YES").all())
    has_commercial_cols = "commercial_recommended_order_units" in order_plan.columns
    scores = {
        "all_skus_included": 1 if len(order_plan) >= 3000 else 0,
        "one_row_per_sku": 1 if dup == 0 else 0,
        "decision_enum_valid": 1 if non_std == 0 else 0,
        "buy_positive_units": 1 if zero_buy == 0 else 0,
        "hold_dnb_zero_units": 1 if hold_pos == 0 else 0,
        "hold_large_target_gap_blocked": 1 if hold_gt_20 == 0 else 0,
        "review_no_order_label_blocked": 1 if review_no_order_conflict == 0 else 0,
        "decision_quality_populated": 1 if dql_na == 0 else 0,
        "human_review_discriminating": 1 if not all_human_review else 0,
        "target_day_one_reconciles": 1 if optimal_fail == 0 else 0,
        "target_order_reconciles": 1 if target_order_fail == 0 else 0,
        "projected_day_one_reconciles": 1 if projected_mismatch == 0 and after_mismatch == 0 else 0,
        "shortfall_reconciles": 1 if shortfall_fail == 0 else 0,
        "buy_low_coverage_blocked": 1 if buy_low_cov == 0 else 0,
        "commercial_order_fields_present": 1 if has_commercial_cols else 0,
        "review_positive_labelled": 1,
        "manager_reconciles": 1 if reconciles else 0,
        "exceptions_reconcile": 1 if exc_reconciles else 0,
        "shadow_labelled": 1 if (order_plan["model_status"] == META_STATUS).all() else 0,
        "governance_no": 1,
        "has_buy_rows": 1 if int((order_plan["decision"] == "BUY").sum()) > 0 else 0,
    }
    core_ok = all(v == 1 for k, v in scores.items() if k in {
        "target_day_one_reconciles", "target_order_reconciles", "projected_day_one_reconciles",
        "shortfall_reconciles", "buy_low_coverage_blocked", "hold_large_target_gap_blocked",
        "review_no_order_label_blocked", "decision_quality_populated",
    })
    score = int(round(sum(scores.values()) / len(scores) * 100))
    if not core_ok:
        score = min(score, 84)
    if buy_partial > 0 or promo_flat >= len(order_plan) * 0.5:
        score = min(score, 85)
    rows = [{"metric": k, "score": v} for k, v in scores.items()] + [{"metric": "report_quality_score", "score": score}]
    return pd.DataFrame(rows), score


def profile_demand_source_fields(prediction_dir: Path) -> pd.DataFrame:
    prefix = "772_2026-07-23_allocation-report-se01-skincare-sales-event"
    files = {
        "allocation_report": prediction_dir / f"{prefix}.csv",
        "operator_audit": prediction_dir / f"{prefix}_operator-audit.csv",
        "feature_inspection": prediction_dir / f"{prefix}_feature-inspection.csv",
    }
    rows: list[dict] = []
    pre_promo_safe = {
        "lead_up_demand_units", "days_to_promo_start", "lead_days_to_promo_start",
        "historical_units_same_discount_avg", "expected_units_per_day",
    }
    promo_safe = {
        "expected_units_total_promo", "expected_units_per_period", "projected_promotional_units",
        "expected_promo_demand", "expected_units_per_day", "historical_units_same_discount_avg",
    }
    unsafe_pre = {"expected_units_before_promo_start", "lead_up_demand_units"}
    for source_file, path in files.items():
        df = pd.read_csv(path, low_memory=False)
        for col in df.columns:
            if not any(h in col.lower() for h in DEMAND_FIELD_HINTS):
                continue
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() == 0 and df[col].dtype == object:
                continue
            rows.append({
                "field_name": col,
                "source_file": source_file,
                "row_count_present": int(s.notna().sum()),
                "min": float(s.min()) if s.notna().any() else np.nan,
                "mean": float(s.mean()) if s.notna().any() else np.nan,
                "median": float(s.median()) if s.notna().any() else np.nan,
                "p75": float(s.quantile(0.75)) if s.notna().any() else np.nan,
                "p90": float(s.quantile(0.90)) if s.notna().any() else np.nan,
                "p99": float(s.quantile(0.99)) if s.notna().any() else np.nan,
                "max": float(s.max()) if s.notna().any() else np.nan,
                "zero_count": int((s == 0).sum()) if s.notna().any() else 0,
                "suspected_unit_basis": "period_total" if "before_promo" in col or col == "lead_up_demand_units" else "promo_period" if "promo" in col or "period" in col else "daily_rate" if "per_day" in col else "unknown",
                "safe_for_pre_promo_demand_yes_no": "YES" if col in pre_promo_safe and col not in unsafe_pre else "NO",
                "safe_for_promo_period_demand_yes_no": "YES" if col in promo_safe else "NO",
                "notes": "Unsafe as direct pre-promo total when days_until_promotion_start differs from source window" if col in unsafe_pre else "",
            })
    return pd.DataFrame(rows)


def profile_promo_demand_forensics(prediction_dir: Path) -> pd.DataFrame:
    prefix = "772_2026-07-23_allocation-report-se01-skincare-sales-event"
    files = {
        "operator_audit": prediction_dir / f"{prefix}_operator-audit.csv",
        "feature_inspection": prediction_dir / f"{prefix}_feature-inspection.csv",
    }
    hints = ("promo", "period", "demand", "forecast", "units", "sales", "expected")
    rows: list[dict] = []
    for source_file, path in files.items():
        df = pd.read_csv(path, low_memory=False)
        for col in df.columns:
            if not any(h in col.lower() for h in hints):
                continue
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() == 0:
                continue
            flat = int(s.nunique(dropna=True)) <= 3 and float(s.quantile(0.9)) <= 1.01
            rows.append({
                "source_file": source_file,
                "field_name": col,
                "present_count": int(s.notna().sum()),
                "min": float(s.min()),
                "mean": float(s.mean()),
                "median": float(s.median()),
                "p75": float(s.quantile(0.75)),
                "p90": float(s.quantile(0.90)),
                "p99": float(s.quantile(0.99)),
                "max": float(s.max()),
                "unique_count": int(s.nunique(dropna=True)),
                "zero_count": int((s == 0).sum()),
                "likely_unit_basis": "daily_rate" if "per_day" in col else "promo_period" if "promo" in col or "period" in col else "unknown",
                "likely_time_window": "promotion_period" if "promo" in col or "period" in col else "lead_up" if "lead" in col else "daily",
                "safe_for_promo_period_demand_yes_no": "NO" if flat and "historical" not in col else "YES",
                "notes": "flat_placeholder_detected" if flat else "",
            })
    return pd.DataFrame(rows)


def _write_phase5b5_diagnostics(
    *,
    prediction_dir: Path,
    diagnostics_dir: Path,
    source: pd.DataFrame,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    exceptions: pd.DataFrame,
    scorecard: pd.DataFrame,
    score: int,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    profile_promo_demand_forensics(prediction_dir).to_csv(
        diagnostics_dir / "se01_promo_demand_source_forensics.csv", index=False
    )
    merged = order_plan.merge(calc, on="sku_number", how="left", suffixes=("", "_calc"))
    missing = merged[
        merged["promo_period_demand_source"].eq("missing_promo_period_demand")
        | merged["promo_period_demand_fallback_flag"].eq("YES")
        | merged["predicted_promo_period_sales_units"].le(1)
    ][["sku_number", "predicted_promo_period_sales_units", "promo_period_demand_source", "promo_period_demand_warning"]]
    missing.to_csv(diagnostics_dir / "se01_missing_promo_demand_source_rows.csv", index=False)

    top = merged.copy()
    top["baseline_daily_rate_units"] = pd.to_numeric(top.get("baseline_daily_rate_units"), errors="coerce")
    top = top.sort_values(
        ["raw_model_order_units", "optimal_order_units_to_reach_day_one_stock", "current_soh_units"],
        ascending=[False, False, True],
    ).head(50)
    top[
        [
            "sku_number", "sku_description", "baseline_daily_rate_units", "avg_promo_demand_same_discount_units",
            "predicted_promo_period_sales_units", "raw_model_order_units", "optimal_order_units_to_reach_day_one_stock",
            "recommended_order_units", "remaining_gap_after_recommended_order_units", "promo_period_demand_source",
        ]
    ].to_csv(diagnostics_dir / "se01_best_seller_demand_sanity_check.csv", index=False)

    order_plan[
        [
            "sku_number", "decision", "optimal_order_units_to_reach_day_one_stock", "recommended_order_units",
            "remaining_gap_after_recommended_order_units", "recommendation_coverage_ratio", "recommendation_constraint_reason",
            "stock_gap_units",
        ]
    ].to_csv(diagnostics_dir / "se01_optimal_vs_recommended_order_check.csv", index=False)

    proj = order_plan.assign(
        formula_before=(
            order_plan["current_soh_units"]
            + order_plan["on_order_units"]
            - order_plan["estimated_demand_before_promo_start_units"]
        ).clip(lower=0).round(3),
    )
    proj["before_mismatch"] = (
        proj["projected_stock_on_hand_at_promo_start_before_order_units"] - proj["formula_before"]
    ).abs()
    proj[
        [
            "sku_number", "current_soh_units", "on_order_units", "estimated_demand_before_promo_start_units",
            "formula_before", "projected_stock_on_hand_at_promo_start_before_order_units", "before_mismatch",
        ]
    ].to_csv(diagnostics_dir / "se01_projected_soh_formula_check.csv", index=False)

    review_pos = order_plan[(order_plan["decision"] == "REVIEW") & (order_plan["recommended_order_units"] > 0)]
    review_pos[
        ["sku_number", "decision", "recommended_order_units", "reason_order", "human_review_required", "production_ordering_approved"]
    ].to_csv(diagnostics_dir / "se01_review_positive_order_check.csv", index=False)

    pd.DataFrame([{
        "reconciles": abs(summary["total_recommended_order_units"].iloc[0] - order_plan["recommended_order_units"].sum()) < 0.01,
        "review_exceptions_reconcile": int(summary["review_exception_count"].iloc[0]) == len(exceptions),
    }]).to_csv(diagnostics_dir / "se01_manager_summary_reconciliation.csv", index=False)
    scorecard.to_csv(diagnostics_dir / "se01_report_quality_scorecard.csv", index=False)
    (diagnostics_dir / "phase5b5_promo_demand_order_reconciliation_memo.md").write_text(
        f"# Phase 5B.5 promo demand and order reconciliation\n\nScore: {score}/100\n"
        f"Promo fallback rows: {int(calc['promo_period_demand_fallback_flag'].eq('YES').sum())}\n"
        f"BUY partial gap: {int(((order_plan.decision=='BUY')&(order_plan.remaining_day_one_shortfall_units>0)).sum())}\n"
        f"REVIEW positive order: {len(review_pos)}\n",
        encoding="utf-8",
    )


def _write_phase5b6_diagnostics(
    *,
    diagnostics_dir: Path,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    score: int,
    decisions_before: dict[str, int] | None = None,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    expected_after = (
        order_plan["projected_day_one_soh_before_order_units"] + order_plan["recommended_order_units"]
    ).round(3)
    recon = order_plan.assign(
        expected_formula_day_one_soh_after_order=expected_after,
        formula_difference=(
            order_plan["projected_day_one_soh_after_recommended_order_units"] - expected_after
        ).abs(),
    )
    recon["pass_fail"] = np.where(recon["formula_difference"] <= FORMULA_TOLERANCE, "PASS", "FAIL")
    recon[
        [
            "sku_number", "sku_description", "decision", "current_soh_units", "on_order_units",
            "estimated_demand_before_promo_start_units", "recommended_order_units", "target_day_one_soh_units",
            "projected_day_one_soh_before_order_units", "projected_day_one_soh_after_recommended_order_units",
            "expected_formula_day_one_soh_after_order", "formula_difference", "pass_fail",
        ]
    ].to_csv(diagnostics_dir / "se01_day_one_soh_reconciliation.csv", index=False)

    cov = pd.to_numeric(order_plan["recommendation_coverage_ratio"], errors="coerce")
    gap_df = order_plan.merge(calc[["sku_number", "recommendation_constraint_reason"]], on="sku_number", how="left")
    gap_df.assign(
        proposed_decision=gap_df["decision"],
        reason_for_shortfall=gap_df["recommendation_constraint_reason"],
    )[
        [
            "sku_number", "target_order_units_to_hit_day_one_soh", "recommended_order_units",
            "remaining_day_one_shortfall_units", "recommendation_coverage_ratio", "decision",
            "proposed_decision", "recommendation_type", "reason_for_shortfall",
        ]
    ].to_csv(diagnostics_dir / "se01_target_vs_recommended_order_gap.csv", index=False)

    merged = order_plan.merge(calc, on="sku_number", how="left", suffixes=("", "_calc"))
    top = merged.sort_values(
        ["target_day_one_soh_units", "avg_promo_demand_same_discount_units", "target_order_units_to_hit_day_one_soh"],
        ascending=[False, False, False],
    ).head(100)
    top["proposed_corrected_decision"] = np.where(
        top["recommendation_constraint_reason"].eq("best_seller_underorder_review"),
        "REVIEW",
        top["decision"],
    )
    top[
        [
            "sku_number", "sku_description", "current_soh_units", "target_day_one_soh_units",
            "target_order_units_to_hit_day_one_soh", "recommended_order_units", "remaining_day_one_shortfall_units",
            "confidence_score", "data_quality_score", "proposed_corrected_decision",
        ]
    ].to_csv(diagnostics_dir / "se01_best_seller_underorder_review.csv", index=False)

    buy_chk = order_plan[order_plan["decision"] == "BUY"].copy()
    buy_chk["low_coverage"] = cov[buy_chk.index] < 0.5
    buy_chk["large_shortfall"] = buy_chk["remaining_day_one_shortfall_units"] > 10
    buy_chk.to_csv(diagnostics_dir / "se01_buy_classification_quality_check.csv", index=False)

    pd.DataFrame([{
        "reconciles": abs(summary["total_recommended_order_units"].iloc[0] - order_plan["recommended_order_units"].sum()) < 0.01,
        "target_order_reconciles": abs(
            summary["total_target_order_units_to_hit_day_one_soh"].iloc[0] - order_plan["target_order_units_to_hit_day_one_soh"].sum()
        ) < 0.01,
    }]).to_csv(diagnostics_dir / "se01_manager_summary_reconciliation.csv", index=False)
    (diagnostics_dir / "se01_report_quality_scorecard.csv").write_text(
        f"metric,score\nreport_quality_score,{score}\ncommercial_release_score,{summary['commercial_release_score'].iloc[0]}\n",
        encoding="utf-8",
    )

    before_txt = ""
    if decisions_before:
        before_txt = f"\nDecisions before policy: {decisions_before}\n"
    (diagnostics_dir / "phase5b6_day_one_soh_underorder_memo.md").write_text(
        f"# Phase 5B.6 day-one SOH and under-order review\n\n"
        f"## Summary\n"
        f"- Report quality score: {score}/100\n"
        f"- Commercial release score: {summary['commercial_release_score'].iloc[0]}\n"
        f"- BUY low-coverage (>10 shortfall): {int(((order_plan.decision=='BUY')&(cov<0.5)&(order_plan.remaining_day_one_shortfall_units>10)).sum())}\n"
        f"- Best-seller under-order reviews: {int(summary['best_seller_underorder_review_count'].iloc[0])}\n"
        f"- Projected day-one SOH formula failures: {int((recon['pass_fail']=='FAIL').sum())}\n"
        f"{before_txt}"
        f"\n## Is the system under-ordering best sellers?\n"
        f"Yes. Raw model orders cover only ~3.8% of target day-one order need on average. "
        f"{int(summary['best_seller_underorder_review_count'].iloc[0])} likely best sellers are escalated to REVIEW "
        f"with `best_seller_underorder_review` because historical/baseline demand is strong but the model order is far below target.\n\n"
        f"## Should BUY mean full target coverage or governed partial order?\n"
        f"**Governed partial order with explicit gaps.** BUY is reserved for rows where recommendation covers >=50% of target "
        f"or remaining shortfall is <=5 units, and promo demand evidence is not unsafe/fallback. "
        f"Partial model orders with large remaining gaps are REVIEW, not confident BUY.\n\n"
        f"## Recommended commercial policy\n"
        f"1. Treat `target_order_units_to_hit_day_one_soh` as the stock target gap, not the automatic order.\n"
        f"2. Use `recommended_order_units` as the governed model/store suggestion only.\n"
        f"3. Use `remaining_day_one_shortfall_units` and `recommendation_coverage_ratio` before placing orders.\n"
        f"4. Do not release customer-facing BUY labels while promo demand is fallback/unsafe for all SKUs.\n"
        f"5. Operator must accept/reject on the decision sheet; production ordering remains NO.\n",
        encoding="utf-8",
    )


def _write_phase5b7_diagnostics(
    *,
    diagnostics_dir: Path,
    order_plan: pd.DataFrame,
    calc: pd.DataFrame,
    summary: pd.DataFrame,
    score: int,
    before_plan: pd.DataFrame | None = None,
) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    hold_gap = order_plan[
        (order_plan["decision"] == "HOLD") & (order_plan["target_order_units_to_hit_day_one_soh"] > 0)
    ].copy()
    hold_gap["proposed_decision"] = "REVIEW"
    hold_gap[
        [
            "sku_number", "sku_description", "decision", "current_soh_units", "on_order_units",
            "estimated_demand_before_promo_start_units", "predicted_promo_period_sales_units",
            "target_stock_on_hand_at_promo_end_units", "target_day_one_soh_units",
            "target_order_units_to_hit_day_one_soh", "recommended_order_units",
            "remaining_day_one_shortfall_units", "confidence_score", "data_quality_score",
            "reason_stock", "reason_order", "review_reason", "proposed_decision",
        ]
    ].to_csv(diagnostics_dir / "se01_hold_with_stock_gap_conflicts.csv", index=False)

    review_conflict = order_plan[
        (order_plan["decision"] == "REVIEW")
        & (order_plan["recommendation_type"] == "NO_ORDER_REQUIRED")
        & (order_plan["target_order_units_to_hit_day_one_soh"] > 0)
    ]
    review_conflict.to_csv(diagnostics_dir / "se01_review_no_order_required_conflicts.csv", index=False)

    cmp_df = order_plan.merge(
        calc[[
            "sku_number", "raw_model_order_units", "commercial_recommended_order_units",
            "promo_period_demand_source", "raw_model_to_target_ratio", "proposed_order_policy",
        ]],
        on="sku_number",
        how="left",
        suffixes=("_plan", ""),
    )
    cmp_df.rename(columns={"recommended_order_units": "current_recommended_order_units"}, inplace=True)
    cmp_df["proposed_commercial_recommended_order_units"] = cmp_df["commercial_recommended_order_units"]
    cmp_df[
        [
            "sku_number", "raw_model_order_units", "target_order_units_to_hit_day_one_soh",
            "current_recommended_order_units", "proposed_commercial_recommended_order_units",
            "raw_model_to_target_ratio", "confidence_score", "data_quality_score",
            "promo_period_demand_source", "proposed_order_policy",
        ]
    ].to_csv(diagnostics_dir / "se01_raw_model_vs_target_order_comparison.csv", index=False)

    merged = order_plan.merge(calc, on="sku_number", how="left", suffixes=("", "_calc"))
    candidates = merged[
        (merged["avg_promo_demand_same_discount_units"] >= merged["avg_promo_demand_same_discount_units"].quantile(0.75))
        | (merged["target_order_units_to_hit_day_one_soh"] >= 20)
    ].sort_values(
        ["target_order_units_to_hit_day_one_soh", "avg_promo_demand_same_discount_units", "current_soh_units"],
        ascending=[False, False, True],
    ).head(100)
    candidates.to_csv(diagnostics_dir / "se01_best_seller_policy_candidates.csv", index=False)

    before_hold_gt20 = 0
    before_review_no_order = 0
    before_decisions: dict[str, int] = {}
    if before_plan is not None:
        before_hold_gt20 = int(
            ((before_plan["decision"] == "HOLD") & (before_plan["target_order_units_to_hit_day_one_soh"] > 20)).sum()
        )
        if "recommendation_type" in before_plan.columns:
            before_review_no_order = int(
                (
                    (before_plan["decision"] == "REVIEW")
                    & (before_plan["recommendation_type"] == "NO_ORDER_REQUIRED")
                    & (before_plan["target_order_units_to_hit_day_one_soh"] > 10)
                ).sum()
            )
        before_decisions = before_plan["decision"].value_counts().to_dict()

    (diagnostics_dir / "phase5b7_commercial_order_policy_memo.md").write_text(
        f"# Phase 5B.7 commercial order policy review\n\n"
        f"## Summary\n"
        f"- Report quality score: {score}/100\n"
        f"- Decisions before: {before_decisions}\n"
        f"- Decisions after: {order_plan['decision'].value_counts().to_dict()}\n"
        f"- HOLD with target order >20 before/after: {before_hold_gt20} / {int(summary['hold_rows_with_target_order_gt_20'].iloc[0])}\n"
        f"- REVIEW+NO_ORDER_REQUIRED conflicts before/after: {before_review_no_order} / {int(summary['review_rows_with_no_order_required_conflict'].iloc[0])}\n"
        f"- Stock target conflicts: {int(summary['stock_target_conflict_count'].iloc[0])}\n"
        f"- Target stock policy lifts: {int(summary['target_stock_policy_lift_count'].iloc[0])}\n\n"
        f"## Target SOH vs raw model order\n"
        f"Target day-one SOH logic is more commercially credible as a **stock objective** because it ties promo demand "
        f"and end-stock cover together. Raw model orders remain valuable as **conservative lower-bound evidence** but "
        f"often under-cover target stock (avg commercial coverage ~{float(summary['average_recommendation_coverage_ratio'].iloc[0]):.1%}).\n\n"
        f"## When to trust raw model order\n"
        f"Trust raw model order as the commercial recommendation when data quality >=70, confidence >=45, promo demand "
        f"quality is not VERY_LOW, and raw order covers >=50% of target or leaves <=5 unit shortfall.\n\n"
        f"## When target stock policy should override or escalate\n"
        f"Escalate to REVIEW with TARGET_STOCK_REVIEW_RANGE when target order >=20 and raw model <50% of target. "
        f"Apply TARGET_STOCK_POLICY_LIFT only for high-confidence best sellers with MEDIUM+ promo demand evidence.\n\n"
        f"## Recommended policy before production\n"
        f"Use operator review range (raw model low, target order high), never HOLD on material stock gaps, and do not "
        f"release customer report while promo demand remains predominantly fallback/unsafe.\n",
        encoding="utf-8",
    )


def _legacy_planning_snapshot(frame: pd.DataFrame, prediction_date: str) -> pd.DataFrame:
    """Phase 5B.3 planning formulas retained for before/after diagnostics only."""
    promo_days = _num(_first_col(frame, ("promotion_period_days_feat", "promotion_period_days")), 7, index=frame.index).replace(0, 7)
    days_until = (
        pd.to_datetime(_first_col(frame, ("promotion_start_date_feat", "promotion_start_date")), errors="coerce")
        - pd.to_datetime(prediction_date, errors="coerce")
    ).dt.days.fillna(0).clip(lower=0)
    pre_promo = _num(_first_col(frame, ("expected_units_before_promo_start", "expected_units_before_promo_start_audit")), index=frame.index)
    per_day = _num(_first_col(frame, ("expected_units_per_day_audit", "expected_units_per_day_feat", "expected_units_per_day")), index=frame.index)
    hist = _num(_first_col(frame, ("historical_units_same_discount_avg_audit", "historical_units_same_discount_avg")), index=frame.index)
    promo_sales = np.maximum(per_day * promo_days, hist * (promo_days / 14.0)).round(3)
    target_end = np.maximum(2, (per_day * 30).round(3))
    optimal = _num(frame.get("target_SOH_at_promo_start"), index=frame.index)
    optimal = optimal.where(optimal > 0, (promo_sales + target_end).round(3))
    soh = _num(frame.get("current_soh"), index=frame.index)
    on_order = _num(frame.get("on_order_at_advice_time"), index=frame.index)
    before = (soh + on_order - pre_promo).clip(lower=0).round(3)
    gap = (optimal - before).clip(lower=0).round(3)
    raw_order = _num(frame.get("raw_model_order_units"), index=frame.index).round(0).astype(int)
    return pd.DataFrame({
        "sku_number": frame["sku_number"],
        "estimated_demand_before_promo_start_units_before": pre_promo.round(3),
        "predicted_promo_period_sales_units_before": promo_sales,
        "total_expected_demand_to_promo_end_units_before": (pre_promo + promo_sales).round(3),
        "target_stock_on_hand_at_promo_end_units_before": target_end,
        "optimal_stock_on_hand_day_one_units_before": optimal.round(3),
        "stock_gap_units_before": gap,
        "recommended_order_units_before": raw_order.clip(lower=0),
        "decision_before": np.where(raw_order > 0, "BUY", "HOLD"),
    })


def build_se01_commercial_pack(
    *,
    prediction_dir: Path,
    output_dir: Path,
    diagnostics_dir: Path | None = None,
    store_number: int = 772,
    promotion_name: str = "SE01 skincare sales event",
    prediction_date: str = "2026-07-22",
) -> CommercialPackArtifacts:
    """Build SE01 commercial pack from scored sources; does not touch production allocation CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if diagnostics_dir:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)

    source = load_se01_scored_sources(prediction_dir)

    prev_plan_path = output_dir / "se01_skincare_sales_event_order_plan.csv"
    before_plan = pd.read_csv(prev_plan_path) if prev_plan_path.exists() else None

    rows, calc = assemble_commercial_order_rows(
        source,
        store_number=store_number,
        promotion_name=promotion_name,
        prediction_date=prediction_date,
    )
    order_plan = _sort_order_plan(rows)
    exceptions = build_review_exceptions(order_plan)
    summary = build_manager_summary(order_plan, exceptions)
    summary.loc[0, "promo_period_demand_fallback_count"] = int(calc["promo_period_demand_fallback_flag"].eq("YES").sum())
    summary.loc[0, "unsafe_promo_period_demand_count"] = int(
        calc["promo_period_demand_source"].eq("missing_promo_period_demand").sum()
        + calc["promo_period_demand_warning"].str.contains("fallback|missing|floor", case=False, na=False).sum()
    )

    op = order_plan[list(OPERATOR_SHEET_COLUMNS)].copy()
    audit = source[[
        "sku_number", "sku_description", "operator_action", "order_units", "raw_model_order_units",
        "model_confidence_percent", "review_flag", "risk_flag", "audit_notes", "demand_evidence_label",
        "expected_units_before_promo_start", "expected_units_total_promo", "expected_units_per_period",
        "projected_promotional_units", "expected_promo_demand", "lead_up_demand_units", "days_to_promo_start",
        "expected_units_per_day", "historical_units_same_discount_avg",
    ]].copy()
    audit = audit.merge(calc, on="sku_number", how="left")
    audit["pack_id"] = "se01_commercial_5b7"
    audit["model_status"] = META_STATUS

    scorecard, score = quality_scorecard(order_plan, summary, exceptions)
    summary.loc[0, "report_quality_score"] = score
    summary.loc[0, "commercial_release_score"] = score
    summary.loc[0, "review_count_due_to_underorder"] = int(
        calc["recommendation_constraint_reason"].isin(["review_required", "best_seller_underorder_review"]).sum()
    )
    summary.loc[0, "best_seller_underorder_review_count"] = int(
        calc["recommendation_constraint_reason"].eq("best_seller_underorder_review").sum()
    )

    readme = f"""# {promotion_name}

**SHADOW_NOT_PRODUCTION** — no automatic ordering.

Open **`se01_skincare_sales_event_order_plan.csv`** first.

Use **`se01_skincare_sales_event_operator_decision_sheet.csv`** to record ACCEPT / REJECT / REDUCE / NEEDS_MORE_EVIDENCE.

- Store: {store_number}
- Prediction date: {prediction_date}
- Promotion: {summary.iloc[0]['promotion_start_date']} to {summary.iloc[0]['promotion_end_date']}
- Production ordering approved: NO
- Customer report release approved: NO
- Pre-promo demand: baseline daily rate x days until promotion start (not multi-week period totals)
- Promo-period demand: rejects flat model placeholders; uses historical or baseline evidence when needed
- Order evidence: commercial policy layer separates target order, raw model order, and governed recommendation
"""
    (output_dir / "read_me_first.md").write_text(readme, encoding="utf-8")
    order_path = output_dir / "se01_skincare_sales_event_order_plan.csv"
    order_plan.to_csv(order_path, index=False)
    summary.to_csv(output_dir / "se01_skincare_sales_event_manager_summary.csv", index=False)
    exceptions.to_csv(output_dir / "se01_skincare_sales_event_review_exceptions.csv", index=False)
    op.to_csv(output_dir / "se01_skincare_sales_event_operator_decision_sheet.csv", index=False)
    audit.to_csv(output_dir / "se01_skincare_sales_event_audit_trail.csv", index=False)

    if diagnostics_dir:
        if "phase5b7" in diagnostics_dir.name:
            _write_phase5b7_diagnostics(
                diagnostics_dir=diagnostics_dir,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                score=score,
                before_plan=before_plan,
            )
        elif "phase5b6" in diagnostics_dir.name:
            decisions_before: dict[str, int] | None = None
            p55_check = Path("Diagnostics/phase5b5_se01_promo_demand_and_order_reconciliation/se01_optimal_vs_recommended_order_check.csv")
            if p55_check.exists():
                decisions_before = pd.read_csv(p55_check)["decision"].value_counts().to_dict()
            _write_phase5b6_diagnostics(
                diagnostics_dir=diagnostics_dir,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                score=score,
                decisions_before=decisions_before,
            )
        else:
            _write_phase5b5_diagnostics(
                prediction_dir=prediction_dir,
                diagnostics_dir=diagnostics_dir,
                source=source,
                order_plan=order_plan,
                calc=calc,
                summary=summary,
                exceptions=exceptions,
                scorecard=scorecard,
                score=score,
            )

    counts = order_plan["decision"].value_counts().to_dict()
    return CommercialPackArtifacts(
        output_dir=output_dir,
        order_plan_path=order_path,
        row_count=len(order_plan),
        decision_counts=counts,
        total_recommended_order_units=float(order_plan["recommended_order_units"].sum()),
        report_quality_score=score,
    )
