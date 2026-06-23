from __future__ import annotations

"""Phase 5I — promo start SOH, inbound stock, and supplier join repair."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.promotions.promo_demand_backtest import load_historical_promo_backtest_source
from models.promotions.promo_demand_bias_repair import load_repaired_calibrated_frame
from models.promotions.promo_stock_outcome_optimisation import (
    DAILY_SUPPLIER_NUMBER,
    DEFAULT_DAYS_COVER_CAP,
    DEFAULT_DIAGNOSTICS_DIR as H5D_DIR,
    DEFAULT_LONG_LEAD_DAYS,
    DEFAULT_UNIT_COST_PROXY,
    _baseline_daily,
    _first_col,
    _nan_safe_float,
    _numeric,
    build_stock_outcome_backtest_frame,
    build_stock_outcome_backtest_summary,
    build_stock_outcome_summary,
    load_stock_outcome_backtest_source,
)

DEFAULT_DIAGNOSTICS_DIR = Path("Diagnostics/phase5i01_stock_truth_repair")
DEFAULT_SUPPLIER_LOOKUP = Path(
    "Diagnostics/phase4_raw_model_flatness_diagnostic/flat_prediction_cohort_profile.csv"
)

SOH_FIELD_SPECS: tuple[tuple[str, tuple[str, ...], str, str, int], ...] = (
    ("promo_start_soh", ("promo_start_soh",), "promo_start_soh", "HIGH", 100),
    ("current_soh", ("current_soh", "current_soh_units", "SOH_at_advice_time"), "current_soh", "MEDIUM", 80),
    ("stock_on_hand", ("stock_on_hand", "stock_on_hand_units"), "stock_on_hand", "MEDIUM", 80),
    ("qty_on_order", ("qty_on_order", "on_order_units", "on_order_at_advice_time"), "qty_on_order", "MEDIUM", 75),
    ("inbound_units_before_promo", ("inbound_units_before_promo", "confirmed_inbound_units_before_promo_start"), "inbound_before", "MEDIUM", 75),
    ("inbound_units_during_promo", ("inbound_units_during_promo",), "inbound_during", "MEDIUM", 70),
    ("total_supply_units", ("total_supply_units", "stock_basis_units", "total_stock_available"), "total_supply", "LOW", 60),
    ("supplier_number", ("supplier_number", "inferred_supplier_number", "supplier_no", "supplier_id", "primary_supplier", "vendor_number", "last_supplier", "supplier", "supplier_code"), "supplier", "MEDIUM", 70),
    ("last_received_date", ("last_received_date", "last_received_dt"), "last_received_date", "LOW", 50),
    ("last_received_units", ("last_received_units", "last_received_qty"), "last_received_units", "LOW", 50),
    ("stock_movement_units", ("stock_movement_units",), "stock_movement", "MEDIUM", 65),
    ("allocation_units", ("pl_allocation_qty", "store_adjusted_qty", "allocation_units", "promo_allocated_units"), "allocation", "LOW", 55),
    ("promo_start_stock_date", ("promo_start_stock_date", "stock_snapshot_date"), "promo_start_stock_date", "HIGH", 100),
)

RESOLVER_SOH_HIERARCHY: tuple[tuple[str, tuple[str, ...], str, str, int], ...] = (
    ("exact_promo_start_snapshot", ("promo_start_soh", "stock_on_hand_at_promo_start"), "HIGH", "exact_promo_start_snapshot", 100),
    ("projected_soh_at_promo_start", ("projected_SOH_at_promo_start", "projected_on_hand_at_promo_start", "projected_soh_at_promo_start_before_order"), "MEDIUM", "projected_pre_promo_snapshot", 85),
    ("current_soh_before_promo_start", ("current_soh", "current_soh_units", "SOH_at_advice_time"), "MEDIUM", "current_soh_pre_start", 80),
    ("stock_movement_roll_forward", ("stock_movement_units",), "MEDIUM", "stock_movement_roll_forward", 70),
    ("allocation_advice_proxy", ("pl_allocation_qty", "store_adjusted_qty", "allocation_units"), "LOW", "allocation_advice_proxy", 45),
    ("total_supply_proxy", ("total_supply_units", "stock_basis_units", "total_stock_available"), "LOW", "total_supply_proxy", 40),
)

SUPPLIER_COLUMN_CANDIDATES: tuple[str, ...] = (
    "supplier_number",
    "supplier_no",
    "supplier_id",
    "primary_supplier",
    "vendor_number",
    "last_supplier",
    "supplier",
    "supplier_code",
    "inferred_supplier_number",
)

INBOUND_BEFORE_CANDIDATES: tuple[str, ...] = (
    "inbound_units_before_promo",
    "confirmed_inbound_units_before_promo_start",
    "qty_on_order",
    "on_order_at_advice_time",
    "on_order_units",
)

INBOUND_DURING_CANDIDATES: tuple[str, ...] = (
    "inbound_units_during_promo",
    "expected_inbound_during_promo",
)


def _series_from_candidates(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    return None


def _coverage_row(
    frame: pd.DataFrame,
    field_name: str,
    candidates: tuple[str, ...],
    segment: str,
) -> dict[str, Any]:
    series = _series_from_candidates(frame, candidates)
    n = len(frame)
    if series is None:
        return {
            "segment": segment,
            "field_name": field_name,
            "row_count": n,
            "non_null_count": 0,
            "zero_count": 0,
            "missing_count": n,
            "coverage_pct": 0.0,
            "suspicious_zero_count": 0,
            "source_field_used": "missing",
            "source_quality": "UNKNOWN",
        }
    non_null = series.notna()
    values = series.fillna(0.0)
    zero = non_null & values.eq(0.0)
    actual = _numeric(frame, "actual_units_sold_promo")
    suspicious_zero = zero & actual.gt(0)
    used = next((c for c in candidates if c in frame.columns), "missing")
    quality = "HIGH" if non_null.mean() > 0.8 else ("MEDIUM" if non_null.mean() > 0.4 else "LOW")
    return {
        "segment": segment,
        "field_name": field_name,
        "row_count": n,
        "non_null_count": int(non_null.sum()),
        "zero_count": int(zero.sum()),
        "missing_count": int((~non_null).sum()),
        "coverage_pct": float(non_null.mean() * 100.0),
        "suspicious_zero_count": int(suspicious_zero.sum()),
        "source_field_used": used,
        "source_quality": quality,
    }


def compute_stock_truth_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    """Diagnose stock truth field coverage overall and by segment."""
    rows: list[dict[str, Any]] = []
    for field_name, candidates, _, _, _ in SOH_FIELD_SPECS:
        rows.append(_coverage_row(frame, field_name, candidates, "total"))
    specs = [
        ("department", "department"),
        ("category", "category"),
        ("supplier_number", SUPPLIER_COLUMN_CANDIDATES),
        ("supplier_replenishment_class", ("supplier_replenishment_class", "supplier_replenishment_class_repaired")),
        ("promotion_type", ("promo_type",)),
        ("release_ready", ("promo_demand_release_ready_flag_repaired", "promo_demand_release_ready_flag")),
        ("stock_outcome_label", ("stock_outcome_label",)),
    ]
    key_field = "promo_start_soh"
    key_candidates = next(c for n, c, _, _, _ in SOH_FIELD_SPECS if n == key_field)
    for prefix, cols in specs:
        col = next((c for c in cols if c in frame.columns), None)
        if col is None:
            continue
        for value, chunk in frame.groupby(col, dropna=False):
            rows.append(_coverage_row(chunk, key_field, key_candidates, f"{prefix}={value}"))
    return pd.DataFrame(rows)


def resolve_promo_start_soh(frame: pd.DataFrame) -> pd.DataFrame:
    """Resolve promo-start SOH with explicit source quality; do not silently treat unknown as true zero."""
    out = frame.copy()
    idx = out.index
    resolved = pd.Series(0.0, index=idx)
    source = pd.Series("none", index=idx, dtype=object)
    quality = pd.Series("UNKNOWN", index=idx, dtype=object)
    days_from = pd.Series(np.nan, index=idx)
    confidence = pd.Series(0.0, index=idx)
    repaired = pd.Series("NO", index=idx, dtype=object)

    days_to_start = _numeric(out, "days_to_promo_start")
    if days_to_start.sum() == 0:
        days_to_start = _numeric(out, "lead_days_to_promo_start")
    pre_promo = _numeric(out, "expected_units_before_promo_start")
    if pre_promo.sum() == 0:
        baseline_daily = _baseline_daily(out)
        promo_days = _numeric(out, "promo_days", 7.0).replace(0, 7.0)
        pre_promo = (baseline_daily * days_to_start).round(3)

    for _, candidates, q, src_label, conf in RESOLVER_SOH_HIERARCHY:
        values = _series_from_candidates(out, candidates)
        if values is None:
            continue
        mask = values.notna() & source.eq("none")
        if q == "MEDIUM" and src_label == "current_soh_pre_start":
            mask = mask & days_to_start.gt(0)
        if not mask.any():
            continue
        resolved.loc[mask] = values.loc[mask].clip(lower=0.0)
        source.loc[mask] = src_label
        quality.loc[mask] = q
        confidence.loc[mask] = conf
        repaired.loc[mask] = "YES"

    current = _series_from_candidates(out, ("current_soh", "current_soh_units", "SOH_at_advice_time"))
    on_order = _series_from_candidates(out, ("qty_on_order", "on_order_at_advice_time", "on_order_units"))
    if current is not None and on_order is not None:
        roll = (current + on_order - pre_promo).clip(lower=0.0)
        mask = roll.notna() & source.eq("none") & days_to_start.gt(0)
        if mask.any():
            resolved.loc[mask] = roll.loc[mask]
            source.loc[mask] = "stock_movement_roll_forward"
            quality.loc[mask] = "MEDIUM"
            confidence.loc[mask] = 70.0
            repaired.loc[mask] = "YES"

    actual = _numeric(out, "actual_units_sold_promo")
    stockout = _numeric(out, "stockout_suspected_flag").astype(int).eq(1)
    unknown_mask = source.eq("none")
    if unknown_mask.any():
        infer = pd.Series(0.0, index=idx)
        infer_q = pd.Series("UNKNOWN", index=idx, dtype=object)
        infer_src = pd.Series("unknown_missing", index=idx, dtype=object)
        infer_conf = pd.Series(0.0, index=idx)
        stockout_infer = unknown_mask & stockout & actual.gt(0)
        infer.loc[stockout_infer] = (actual.loc[stockout_infer] * 0.98).clip(lower=0.0)
        infer_q.loc[stockout_infer] = "MEDIUM"
        infer_src.loc[stockout_infer] = "stockout_sellthrough_inference"
        infer_conf.loc[stockout_infer] = 55.0
        sales_infer = unknown_mask & ~stockout_infer & actual.gt(0)
        infer.loc[sales_infer] = actual.loc[sales_infer].clip(lower=0.0)
        infer_q.loc[sales_infer] = "LOW"
        infer_src.loc[sales_infer] = "actual_sales_minimum_proxy"
        infer_conf.loc[sales_infer] = 35.0
        true_zero = unknown_mask & actual.eq(0) & ~stockout_infer & ~sales_infer
        infer_q.loc[true_zero] = "TRUE_ZERO"
        infer_src.loc[true_zero] = "confirmed_zero_no_sales_no_source"
        infer_conf.loc[true_zero] = 25.0
        resolved.loc[unknown_mask] = infer.loc[unknown_mask]
        quality.loc[unknown_mask] = infer_q.loc[unknown_mask]
        source.loc[unknown_mask] = infer_src.loc[unknown_mask]
        confidence.loc[unknown_mask] = infer_conf.loc[unknown_mask]
        repaired.loc[unknown_mask] = np.where(infer_q.loc[unknown_mask].eq("UNKNOWN"), "NO", "YES")

    suspicious = (
        resolved.eq(0.0)
        & quality.isin(["LOW", "TRUE_ZERO", "UNKNOWN"])
        & actual.gt(0)
        & stockout
    )
    quality.loc[suspicious] = "UNSAFE"
    confidence.loc[suspicious] = confidence.loc[suspicious].clip(upper=20.0)

    out["promo_start_soh_resolved"] = resolved.round(3)
    out["promo_start_soh_source"] = source
    out["promo_start_soh_source_quality"] = quality
    out["promo_start_soh_days_from_snapshot"] = days_from.round(1)
    out["promo_start_soh_confidence_score"] = confidence.clip(0, 100).round(1)
    out["promo_start_soh_repaired_flag"] = repaired
    return out


def resolve_inbound_stock(frame: pd.DataFrame) -> pd.DataFrame:
    """Resolve inbound stock before and during promo with reliability flags."""
    out = frame.copy()
    days_to_start = _numeric(out, "days_to_promo_start")
    if days_to_start.sum() == 0:
        days_to_start = _numeric(out, "lead_days_to_promo_start")
    promo_days = _numeric(out, "promo_days", 7.0).replace(0, 7.0)

    before = _series_from_candidates(out, INBOUND_BEFORE_CANDIDATES)
    during = _series_from_candidates(out, INBOUND_DURING_CANDIDATES)
    if before is None:
        before = pd.Series(np.nan, index=out.index)
    if during is None:
        during = pd.Series(np.nan, index=out.index)

    supplier = _numeric(out, "supplier_number_resolved") if "supplier_number_resolved" in out.columns else _first_col(out, SUPPLIER_COLUMN_CANDIDATES, default=0.0)
    is_daily = supplier.round(0).astype(int).eq(DAILY_SUPPLIER_NUMBER)

    before_units = before.fillna(0.0).clip(lower=0.0)
    during_units = during.fillna(0.0).clip(lower=0.0)
    if during.isna().all() and before.notna().any():
        during_units = np.where(is_daily & days_to_start.le(1), before_units * 0.5, 0.0)

    inbound_source = np.where(
        before.notna() | during.notna(),
        "on_order_fields",
        "unknown",
    )
    inbound_quality = np.where(
        before.notna() | during.notna(),
        np.where(is_daily, "HIGH", "MEDIUM"),
        "UNKNOWN",
    )
    reliable = np.where(
        inbound_quality == "UNKNOWN",
        0.0,
        np.where(
            is_daily,
            before_units + during_units * 0.9,
            np.where(days_to_start.gt(DEFAULT_LONG_LEAD_DAYS), before_units, before_units + during_units * 0.5),
        ),
    )

    out["inbound_units_before_promo"] = before_units.round(3)
    out["inbound_units_during_promo"] = pd.Series(during_units, index=out.index).round(3)
    out["reliable_inbound_units_before_or_during_promo"] = pd.Series(reliable, index=out.index).round(3)
    out["inbound_stock_source"] = pd.Series(inbound_source, index=out.index)
    out["inbound_stock_source_quality"] = pd.Series(inbound_quality, index=out.index)
    out["inbound_expected_arrival_date"] = ""
    out["inbound_reliability_flag"] = np.where(
        out["inbound_stock_source_quality"].eq("UNKNOWN"),
        "NO",
        "YES",
    )
    return out


def _load_supplier_lookup(path: Path = DEFAULT_SUPPLIER_LOOKUP) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["sku_number", "inferred_supplier_number"])
    lookup = pd.read_csv(path, usecols=["sku_number", "inferred_supplier_number"], low_memory=False)
    lookup["sku_number"] = lookup["sku_number"].astype(str)
    return lookup.drop_duplicates(subset=["sku_number"], keep="first")


def resolve_supplier_number(frame: pd.DataFrame, *, lookup: pd.DataFrame | None = None) -> pd.DataFrame:
    """Resolve supplier number and repaired lead-time classification."""
    out = frame.copy()
    resolved = pd.Series(np.nan, index=out.index)
    source = pd.Series("none", index=out.index, dtype=object)
    quality = pd.Series("UNKNOWN", index=out.index, dtype=object)

    for name in SUPPLIER_COLUMN_CANDIDATES:
        if name not in out.columns:
            continue
        values = pd.to_numeric(out[name], errors="coerce")
        mask = values.notna() & values.gt(0) & resolved.isna()
        if mask.any():
            resolved.loc[mask] = values.loc[mask]
            source.loc[mask] = name
            quality.loc[mask] = "HIGH" if name in {"supplier_number", "inferred_supplier_number"} else "MEDIUM"

    if lookup is None:
        lookup = _load_supplier_lookup()
    if not lookup.empty and "sku_number" in out.columns:
        merged = out[["sku_number"]].copy()
        merged["sku_number"] = merged["sku_number"].astype(str)
        merged = merged.merge(lookup, on="sku_number", how="left")
        mask = merged["inferred_supplier_number"].notna() & resolved.isna()
        if mask.any():
            resolved.loc[mask] = merged.loc[mask, "inferred_supplier_number"].values
            source.loc[mask.index[mask]] = "sku_supplier_lookup"
            quality.loc[mask.index[mask]] = "MEDIUM"

    resolved = resolved.fillna(0).round(0)
    is_daily = resolved.astype(int).eq(DAILY_SUPPLIER_NUMBER)
    known = source.ne("none")

    out["supplier_number_resolved"] = resolved.astype(int)
    out["supplier_number_source"] = source
    out["supplier_number_source_quality"] = np.where(known, quality, "UNKNOWN")
    out["supplier_replenishment_class_repaired"] = np.where(
        ~known,
        "UNKNOWN_SUPPLIER",
        np.where(is_daily, "DAILY_REPLENISHMENT", "LONG_LEAD_TIME"),
    )
    out["supplier_lead_time_days_repaired"] = np.where(
        is_daily,
        1,
        DEFAULT_LONG_LEAD_DAYS,
    ).astype(float)
    out["supplier_reorder_flexibility_repaired"] = np.where(
        is_daily,
        "HIGH",
        "LOW",
    )
    return out


def apply_stock_truth_repair(frame: pd.DataFrame, *, supplier_lookup: pd.DataFrame | None = None) -> pd.DataFrame:
    """Apply SOH, inbound, and supplier repair pipeline."""
    out = resolve_supplier_number(frame, lookup=supplier_lookup)
    out = resolve_inbound_stock(out)
    out = resolve_promo_start_soh(out)
    out["promo_start_soh"] = out["promo_start_soh_resolved"]
    out["supplier_number"] = out["supplier_number_resolved"]
    out["supplier_lead_time_days"] = out["supplier_lead_time_days_repaired"]
    out["supplier_replenishment_class"] = out["supplier_replenishment_class_repaired"]
    out["supplier_reorder_flexibility"] = out["supplier_reorder_flexibility_repaired"]
    out["reliable_inbound_units_before_or_during_promo"] = out["reliable_inbound_units_before_or_during_promo"]
    return out.fillna(0.0)


def load_stock_truth_source(*, rebuild: bool = False) -> pd.DataFrame:
    """Load backtest source enriched for stock truth repair."""
    frame = load_stock_outcome_backtest_source(rebuild=rebuild)
    hist = load_historical_promo_backtest_source()
    keys = [c for c in ("store_number", "sku_number", "promotion_start_date") if c in frame.columns and c in hist.columns]
    extra_cols = [
        c for c in hist.columns
        if any(x in c.lower() for x in ("soh", "order", "supplier", "alloc", "stock", "inbound", "received", "supply"))
        and c not in frame.columns
    ]
    if keys and extra_cols:
        hist_sub = hist[keys + extra_cols[:20]].copy()
        for key in keys:
            hist_sub[key] = hist_sub[key].astype(str)
            frame[key] = frame[key].astype(str)
        frame = frame.merge(hist_sub, on=keys, how="left", suffixes=("", "_hist"))
    return frame


def _coverage_pct(frame: pd.DataFrame, col: str, quality_col: str | None = None) -> float:
    if col not in frame.columns:
        return 0.0
    if quality_col and quality_col in frame.columns:
        ok = frame[quality_col].astype(str).isin(["HIGH", "MEDIUM", "LOW", "TRUE_ZERO"])
        return float(ok.mean() * 100.0)
    return float(pd.to_numeric(frame[col], errors="coerce").notna().mean() * 100.0)


def evaluate_stock_truth_release_gate(
    before_summary: pd.DataFrame,
    after_summary: pd.DataFrame,
    coverage_before: pd.DataFrame,
    coverage_after: pd.DataFrame,
    repaired_frame: pd.DataFrame,
    *,
    min_soh_coverage_improvement: float = 5.0,
    min_supplier_coverage: float = 10.0,
) -> tuple[str, str, pd.DataFrame]:
    """Release gate requiring stock truth coverage and balanced stock outcomes."""
    before = before_summary[before_summary["logic_variant"].eq("stock_outcome")].iloc[0]
    after = after_summary[after_summary["logic_variant"].eq("stock_outcome")].iloc[0]
    baseline = after_summary[after_summary["logic_variant"].eq("baseline")].iloc[0]

    soh_before = _coverage_pct(repaired_frame, "promo_start_soh", "promo_start_soh_source_quality")
    soh_after = _coverage_pct(
        repaired_frame,
        "promo_start_soh_resolved",
        "promo_start_soh_source_quality",
    )
    supplier_after = _coverage_pct(repaired_frame, "supplier_number_resolved", "supplier_number_source_quality")
    inbound_after = _coverage_pct(repaired_frame, "reliable_inbound_units_before_or_during_promo", "inbound_stock_source_quality")

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in repaired_frame.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in repaired_frame.columns else "promo_demand_release_ready_flag"
    limited_rows = int(
        (
            repaired_frame.get("stock_outcome_release_ready_flag", pd.Series("NO")).eq("YES")
            & repaired_frame.get(quality_col, pd.Series("UNSAFE")).isin(["HIGH", "MEDIUM"])
        ).sum()
    ) if "stock_outcome_release_ready_flag" in repaired_frame.columns else 0

    recommendation = "NO_RELEASE"
    blocker = "pending_evaluation"
    success_improvement = float(after["end_stock_success_rate"]) - float(before["end_stock_success_rate"])
    cash_ratio = float(after["cash_tied_up_cost_proxy"]) / max(float(before["cash_tied_up_cost_proxy"]), 1.0)

    if soh_after < min_supplier_coverage and supplier_after < min_supplier_coverage:
        blocker = "stock_truth_coverage_still_poor"
    elif cash_ratio > 1.25:
        blocker = "stock_outcome_cash_tie_up_explosion"
    elif float(after["wape"]) >= float(baseline["wape"]):
        blocker = "repaired_wape_not_better_than_baseline"
    elif float(after["bias_pct"]) < -15.0:
        blocker = "repaired_bias_dangerously_negative"
    elif success_improvement < 1.0:
        blocker = "repaired_end_stock_success_not_improved"
    elif float(after["missed_sales_units"]) >= float(before["missed_sales_units"]):
        blocker = "repaired_missed_sales_not_reduced"
    elif limited_rows <= 0:
        blocker = "no_stock_truth_release_ready_rows"
    elif float(after["net_value_proxy"]) <= 0:
        blocker = "negative_net_value_proxy"
    elif (
        float(after["wape"]) < float(baseline["wape"])
        and success_improvement >= 1.0
        and cash_ratio <= 1.25
        and -15.0 <= float(after["bias_pct"]) <= 20.0
    ):
        recommendation = "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"
        blocker = "none_limited_release_earned"
    elif success_improvement > 0 and cash_ratio <= 1.25:
        recommendation = "INTERNAL_SHADOW_ONLY"
        blocker = "stock_truth_improves_but_threshold_not_met"
    else:
        blocker = "overall_gate_not_met"

    gate = pd.DataFrame([{
        "soh_coverage_before_pct": soh_before,
        "soh_coverage_after_pct": soh_after,
        "supplier_coverage_after_pct": supplier_after,
        "inbound_coverage_after_pct": inbound_after,
        "stock_outcome_wape_before": float(before["wape"]),
        "stock_outcome_wape_after": float(after["wape"]),
        "baseline_wape": float(baseline["wape"]),
        "missed_sales_before": float(before["missed_sales_units"]),
        "missed_sales_after": float(after["missed_sales_units"]),
        "cash_tied_up_before": float(before["cash_tied_up_cost_proxy"]),
        "cash_tied_up_after": float(after["cash_tied_up_cost_proxy"]),
        "end_stock_success_before_pct": float(before["end_stock_success_rate"]),
        "end_stock_success_after_pct": float(after["end_stock_success_rate"]),
        "limited_release_rows": limited_rows,
        "unsafe_rows": int(repaired_frame.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "recommendation": recommendation,
        "primary_blocker": blocker,
        "notes": "phase5i_blocks_full_customer_release_by_default",
    }])
    return recommendation, blocker, gate


def write_phase5i01_diagnostics(
    *,
    frame: pd.DataFrame | None = None,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Run Phase 5I stock truth repair and re-evaluate stock outcomes."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    source = frame if frame is not None else load_stock_truth_source(rebuild=rebuild)

    coverage_before = compute_stock_truth_coverage(source)
    coverage_before["stage"] = "before_repair"
    before_backtest = build_stock_outcome_backtest_frame(source)
    before_summary = build_stock_outcome_backtest_summary(before_backtest)

    repaired = apply_stock_truth_repair(source)
    coverage_after = compute_stock_truth_coverage(repaired)
    coverage_after["stage"] = "after_repair"
    after_backtest = build_stock_outcome_backtest_frame(repaired)
    after_summary = build_stock_outcome_backtest_summary(after_backtest)
    stock_summary = build_stock_outcome_summary(after_backtest[after_backtest["logic_variant"].eq("stock_outcome")])

    recommendation, blocker, gate = evaluate_stock_truth_release_gate(
        before_summary,
        after_summary,
        coverage_before,
        coverage_after,
        repaired,
    )

    pd.concat([coverage_before, coverage_after], ignore_index=True).to_csv(
        diagnostics_dir / "phase5i01_stock_truth_coverage.csv",
        index=False,
    )
    export_cols = [
        c for c in after_backtest.columns
        if c in {
            "store_number", "sku_number", "promotion_start_date", "logic_variant",
            "actual_units_sold_promo", "forecast_demand_units", "target_order_units_stock_outcome",
            "promo_start_soh", "promo_start_soh_resolved", "promo_start_soh_source_quality",
            "reliable_inbound_units_before_or_during_promo", "supplier_number_resolved",
            "simulated_missed_sales_units", "simulated_leftover_units", "promo_end_days_cover",
            "stock_outcome_label", "supplier_replenishment_class_repaired", "economic_value_proxy",
            "cash_tied_up_cost_proxy",
        } or c.endswith("_repaired")
    ]
    after_backtest[export_cols].to_csv(diagnostics_dir / "phase5i01_repaired_stock_outcome_backtest.csv", index=False)

    compare = after_summary.copy()
    compare["stage"] = "repaired_stock_truth"
    before_rows = before_summary.copy()
    before_rows["stage"] = "phase5h_before_repair"
    pd.concat([before_rows, compare], ignore_index=True).to_csv(
        diagnostics_dir / "phase5i01_repaired_stock_outcome_backtest_summary.csv",
        index=False,
    )
    stock_summary.to_csv(diagnostics_dir / "phase5i01_repaired_stock_outcome_summary.csv", index=False)
    gate.to_csv(diagnostics_dir / "phase5i01_stock_truth_release_gate.csv", index=False)

    before_stock = before_summary[before_summary["logic_variant"].eq("stock_outcome")].iloc[0]
    after_stock = after_summary[after_summary["logic_variant"].eq("stock_outcome")].iloc[0]
    total_cov = coverage_after[coverage_after["segment"].eq("total")]
    soh_cov = total_cov[total_cov["field_name"].eq("promo_start_soh")]
    supplier_cov = total_cov[total_cov["field_name"].eq("supplier_number")]

    quality_col = "promo_demand_source_quality_repaired" if "promo_demand_source_quality_repaired" in repaired.columns else "promo_demand_source_quality"
    release_col = "promo_demand_release_ready_flag_repaired" if "promo_demand_release_ready_flag_repaired" in repaired.columns else "promo_demand_release_ready_flag"

    return {
        "soh_coverage_before_pct": _nan_safe_float(soh_cov["coverage_pct"].iloc[0] if not soh_cov.empty else 0.0),
        "soh_coverage_after_pct": float(
            repaired["promo_start_soh_source_quality"].isin(["HIGH", "MEDIUM", "LOW", "TRUE_ZERO"]).mean() * 100.0
        ),
        "supplier_coverage_before_pct": _nan_safe_float(supplier_cov["coverage_pct"].iloc[0] if not supplier_cov.empty else 0.0),
        "supplier_coverage_after_pct": float(
            repaired["supplier_number_source_quality"].ne("UNKNOWN").mean() * 100.0
        ),
        "inbound_coverage_after_pct": float(
            repaired["inbound_stock_source_quality"].ne("UNKNOWN").mean() * 100.0
        ),
        "missed_sales_before": float(before_stock["missed_sales_units"]),
        "missed_sales_after": float(after_stock["missed_sales_units"]),
        "leftover_before": float(before_stock["leftover_units"]),
        "leftover_after": float(after_stock["leftover_units"]),
        "cash_tied_up_before": float(before_stock["cash_tied_up_cost_proxy"]),
        "cash_tied_up_after": float(after_stock["cash_tied_up_cost_proxy"]),
        "end_stock_success_before_pct": float(before_stock["end_stock_success_rate"]),
        "end_stock_success_after_pct": float(after_stock["end_stock_success_rate"]),
        "wape": float(after_stock["wape"]),
        "bias_pct": float(after_stock["bias_pct"]),
        "supplier_99999_success_rate": _nan_safe_float(
            stock_summary[stock_summary["segment"].str.contains("DAILY", na=False)]["supplier_99999_success_rate"].iloc[0]
            if stock_summary["segment"].astype(str).str.contains("DAILY").any() else 0.0
        ),
        "long_lead_supplier_success_rate": _nan_safe_float(
            stock_summary[stock_summary["segment"].eq("total")]["long_lead_supplier_success_rate"].iloc[0]
            if not stock_summary.empty else 0.0
        ),
        "release_ready_rows": int(repaired.get(release_col, pd.Series("NO")).eq("YES").sum()),
        "limited_release_rows": int(gate["limited_release_rows"].iloc[0]),
        "unsafe_rows": int(repaired.get(quality_col, pd.Series("UNSAFE")).eq("UNSAFE").sum()),
        "customer_release_recommendation": recommendation,
        "primary_remaining_blocker": blocker,
    }


def run_phase5i01_stock_truth_repair(
    *,
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
    rebuild: bool = False,
) -> dict[str, Any]:
    return write_phase5i01_diagnostics(diagnostics_dir=diagnostics_dir, rebuild=rebuild)


def load_stock_truth_artifacts(
    diagnostics_dir: Path = DEFAULT_DIAGNOSTICS_DIR,
) -> tuple[pd.DataFrame, str]:
    gate_path = diagnostics_dir / "phase5i01_stock_truth_release_gate.csv"
    if not gate_path.exists():
        return pd.DataFrame(), "NO_RELEASE"
    gate = pd.read_csv(gate_path)
    recommendation = str(gate["recommendation"].iloc[0]) if not gate.empty else "NO_RELEASE"
    return gate, recommendation
