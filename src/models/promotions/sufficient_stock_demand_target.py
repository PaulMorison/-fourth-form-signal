from __future__ import annotations

"""Governed sufficient-stock demand target construction for units-model training.

Phase 4B step 1: pure target/label construction only. Does not train models or
change scoring outputs.
"""

from typing import Iterable

import numpy as np
import pandas as pd

APPROVED_TARGET_QUALITY_LABELS: tuple[str, ...] = (
    "CLEAN_REALIZED_DEMAND",
    "STOCK_CONSTRAINED_REPAIRED",
    "INVENTORY_INTEGRITY_CONTAMINATED",
    "INSUFFICIENT_EVIDENCE",
    "EXCLUDED_FROM_TARGET",
)

SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS: tuple[str, ...] = (
    "realized_sales_units",
    "stock_constrained_flag",
    "stock_integrity_issue_flag",
    "sufficient_stock_observed_flag",
    "sufficient_stock_demand_units_target",
    "target_quality_label",
    "target_weight",
    "target_repair_basis",
    "target_warning",
)

REALIZED_SALES_SOURCE_COLUMNS: tuple[str, ...] = (
    "actual_units_sold",
    "actual_units",
    "actual_units_sold_promo",
    "target_actual_units_sold",
)

STOCK_BASIS_SOURCE_COLUMNS: tuple[str, ...] = (
    "stock_basis_units",
    "store_adjusted_qty",
    "pl_allocation_qty",
    "total_units_commited",
    "total_stock_available",
)

PROMO_WINDOW_DAY_COLUMNS: tuple[str, ...] = (
    "live_promo_window_days",
    "promo_window_days",
    "promotion_days",
    "promo_days",
)

PROMO_SALES_DAY_COLUMNS: tuple[str, ...] = (
    "promo_sales_day_count",
    "actual_days_with_sales_promo",
)

TINY_BASELINE_THRESHOLD = 0.01
SELL_THROUGH_CLEAN_MAX = 0.85
SELL_THROUGH_SATURATED_MIN = 0.98
SELL_THROUGH_BORDERLINE_MAX = 0.98
LEFTOVER_CLEAN_MIN = 0.05
PARTIAL_WINDOW_DAY_SHARE = 0.5
PARTIAL_WINDOW_SELL_THROUGH_MIN = 0.90


class SufficientStockDemandTargetError(ValueError):
    """Raised when minimum realized-sales evidence is unavailable."""


def build_sufficient_stock_demand_target_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Append governed sufficient-stock demand target columns to a copy of ``frame``."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    if frame.empty:
        return _empty_output_frame(frame.index)

    working = frame.copy()
    realized = _resolve_realized_sales_units(working)
    stock_basis = _resolve_stock_basis_units(working)
    demand_reference = _resolve_demand_reference_units(working)
    baseline_expected = _optional_numeric(working, "baseline_expected_units")
    promo_window_days = _resolve_promo_window_days(working)
    promo_sales_days = _resolve_promo_sales_day_count(working)
    post_14d_units = _optional_numeric(working, "post_14d_units")
    current_soh = _optional_numeric(working, "current_soh")
    actual_refund_units = _optional_numeric(working, "actual_refund_units")
    feature_consensus = _optional_numeric(working, "feature_probability_expected_units_consensus")
    no_promo_history = _optional_numeric(working, "feature_no_promo_history_flag")

    sell_through = _safe_ratio(realized, stock_basis.where(stock_basis > 0.0))
    leftover_pct = _safe_ratio((stock_basis - realized).clip(lower=0.0), stock_basis.where(stock_basis > 0.0))

    stockout_flag = _resolve_stockout_flag(working, realized=realized, stock_basis=stock_basis, sell_through=sell_through, post_14d_units=post_14d_units)
    pure_underallocation_flag = _resolve_pure_underallocation_flag(
        working,
        stock_basis=stock_basis,
        demand_reference=demand_reference,
    )
    underallocation_flag = (pure_underallocation_flag | stockout_flag.ge(1.0)).astype(int)

    integrity_flag = _resolve_integrity_issue_flag(
        working,
        realized=realized,
        stock_basis=stock_basis,
        current_soh=current_soh,
        actual_refund_units=actual_refund_units,
    )

    partial_window_flag = (
        promo_sales_days.gt(0.0)
        & promo_window_days.gt(0.0)
        & promo_sales_days.lt(promo_window_days * PARTIAL_WINDOW_DAY_SHARE)
        & sell_through.ge(PARTIAL_WINDOW_SELL_THROUGH_MIN)
    )

    stock_constrained = (
        stockout_flag.ge(1.0)
        | underallocation_flag.ge(1.0)
        | _optional_numeric(working, "stock_constrained_sales_evidence_flag").ge(1.0)
        | _optional_numeric(working, "observed_zero_soh_event_flag").ge(1.0)
        | _optional_numeric(working, "actual_stockout_flag").ge(1.0)
        | partial_window_flag
    ).astype(int)

    sufficient_stock_observed = (
        integrity_flag.eq(0)
        & stock_basis.gt(0.0)
        & stockout_flag.eq(0)
        & pure_underallocation_flag.eq(0)
        & (
            sell_through.lt(SELL_THROUGH_CLEAN_MAX)
            | leftover_pct.ge(LEFTOVER_CLEAN_MIN)
            | (
                sell_through.ge(SELL_THROUGH_CLEAN_MAX)
                & sell_through.lt(SELL_THROUGH_BORDERLINE_MAX)
                & post_14d_units.le(0.0)
                & pure_underallocation_flag.eq(0)
            )
        )
    ).astype(int)

    target_units = pd.Series(np.nan, index=working.index, dtype="float64")
    target_label = pd.Series("INSUFFICIENT_EVIDENCE", index=working.index, dtype="object")
    target_weight = pd.Series(0.0, index=working.index, dtype="float64")
    target_repair_basis = pd.Series("", index=working.index, dtype="object")
    target_warning = pd.Series("", index=working.index, dtype="object")

    null_realized = realized.isna()
    if null_realized.any():
        target_label = target_label.where(~null_realized, "INSUFFICIENT_EVIDENCE")
        target_warning = _append_warning(target_warning.where(~null_realized, "NULL_REALIZED_SALES"), null_realized, "NULL_REALIZED_SALES")

    integrity_mask = integrity_flag.eq(1) & ~null_realized
    target_label = target_label.where(~integrity_mask, "INVENTORY_INTEGRITY_CONTAMINATED")
    target_weight = target_weight.where(~integrity_mask, 0.0)
    target_repair_basis = target_repair_basis.where(~integrity_mask, "NO_REPAIR_INTEGRITY")
    target_warning = _append_warning(target_warning, integrity_mask, "INVENTORY_INTEGRITY_ISSUE")

    no_evidence_mask = (
        ~null_realized
        & ~integrity_mask
        & realized.le(0.0)
        & promo_sales_days.le(0.0)
        & (stock_basis.isna() | stock_basis.le(0.0))
    )
    target_label = target_label.where(~no_evidence_mask, "INSUFFICIENT_EVIDENCE")
    target_warning = _append_warning(target_warning, no_evidence_mask, "NO_EVIDENCE_NO_SALES")

    sparse_mask = (
        ~null_realized
        & ~integrity_mask
        & ~no_evidence_mask
        & realized.le(0.0)
        & promo_sales_days.le(0.0)
        & no_promo_history.ge(1.0)
        & baseline_expected.le(TINY_BASELINE_THRESHOLD)
    )
    target_label = target_label.where(~sparse_mask, "INSUFFICIENT_EVIDENCE")
    target_warning = _append_warning(target_warning, sparse_mask, "SPARSE_NO_HISTORY")

    clean_mask = (
        ~null_realized
        & ~integrity_mask
        & ~no_evidence_mask
        & ~sparse_mask
        & sufficient_stock_observed.eq(1)
    )
    target_units = target_units.where(~clean_mask, realized.clip(lower=0.0))
    target_label = target_label.where(~clean_mask, "CLEAN_REALIZED_DEMAND")
    borderline_clean = clean_mask & sell_through.ge(SELL_THROUGH_CLEAN_MAX) & sell_through.lt(SELL_THROUGH_BORDERLINE_MAX)
    target_weight = target_weight.where(~clean_mask, 1.0)
    target_weight = target_weight.where(~borderline_clean, 0.85)
    target_repair_basis = target_repair_basis.where(~clean_mask, "CLEAN_REALIZED")

    unresolved = ~null_realized & ~integrity_mask & ~no_evidence_mask & ~sparse_mask & ~clean_mask

    repair_post14_mask = (
        unresolved
        & stockout_flag.ge(1.0)
        & post_14d_units.gt(0.0)
        & demand_reference.notna()
    )
    repair_post14_value = np.maximum(
        realized.clip(lower=0.0),
        _cap_repair(
            realized.clip(lower=0.0) + np.minimum(post_14d_units, post_14d_units * 0.5),
            demand_reference,
            stock_basis * 1.25,
        ),
    )
    target_units = target_units.where(~repair_post14_mask, repair_post14_value)
    target_label = target_label.where(~repair_post14_mask, "STOCK_CONSTRAINED_REPAIRED")
    target_weight = target_weight.where(~repair_post14_mask, 0.50)
    target_repair_basis = target_repair_basis.where(~repair_post14_mask, "REPAIR_POST14_FOLLOWTHROUGH")
    unresolved = unresolved & ~repair_post14_mask

    repair_saturated_mask = (
        unresolved
        & stockout_flag.ge(1.0)
        & sell_through.ge(SELL_THROUGH_SATURATED_MIN)
        & stock_basis.gt(0.0)
        & demand_reference.notna()
    )
    repair_saturated_value = np.maximum(
        realized.clip(lower=0.0),
        _cap_repair(
            np.maximum(realized.clip(lower=0.0), np.minimum(demand_reference, stock_basis * 1.15)),
            demand_reference,
            stock_basis * 1.15,
        ),
    )
    target_units = target_units.where(~repair_saturated_mask, repair_saturated_value)
    target_label = target_label.where(~repair_saturated_mask, "STOCK_CONSTRAINED_REPAIRED")
    target_weight = target_weight.where(~repair_saturated_mask, 0.40)
    target_repair_basis = target_repair_basis.where(~repair_saturated_mask, "REPAIR_SATURATED_SELLTHROUGH")
    unresolved = unresolved & ~repair_saturated_mask

    repair_underalloc_mask = (
        unresolved
        & pure_underallocation_flag.ge(1.0)
        & stockout_flag.lt(1.0)
        & demand_reference.notna()
    )
    repair_underalloc_value = np.maximum(realized.clip(lower=0.0), demand_reference * 0.85)
    target_units = target_units.where(~repair_underalloc_mask, repair_underalloc_value)
    target_label = target_label.where(~repair_underalloc_mask, "STOCK_CONSTRAINED_REPAIRED")
    target_weight = target_weight.where(~repair_underalloc_mask, 0.35)
    target_repair_basis = target_repair_basis.where(~repair_underalloc_mask, "REPAIR_UNDERALLOCATION")
    unresolved = unresolved & ~repair_underalloc_mask

    repair_partial_mask = (
        unresolved
        & partial_window_flag
        & baseline_expected.notna()
        & demand_reference.notna()
    )
    repair_partial_value = np.maximum(
        realized.clip(lower=0.0),
        np.minimum(
            np.maximum(realized.clip(lower=0.0), baseline_expected),
            demand_reference,
        ),
    )
    target_units = target_units.where(~repair_partial_mask, repair_partial_value)
    target_label = target_label.where(~repair_partial_mask, "STOCK_CONSTRAINED_REPAIRED")
    target_weight = target_weight.where(~repair_partial_mask, 0.30)
    target_repair_basis = target_repair_basis.where(~repair_partial_mask, "REPAIR_PARTIAL_SELLING_DAYS")
    unresolved = unresolved & ~repair_partial_mask

    unrepairable_stockout_mask = unresolved & stock_constrained.eq(1)
    target_label = target_label.where(~unrepairable_stockout_mask, "INSUFFICIENT_EVIDENCE")
    target_warning = _append_warning(target_warning, unrepairable_stockout_mask, "UNREPAIRABLE_STOCK_CONSTRAINT")

    missing_stock_evidence_mask = unresolved & stock_constrained.eq(0) & stock_basis.isna()
    target_label = target_label.where(~missing_stock_evidence_mask, "INSUFFICIENT_EVIDENCE")
    target_warning = _append_warning(target_warning, missing_stock_evidence_mask, "MISSING_STOCK_EVIDENCE")

    conservative_mask = unresolved & ~unrepairable_stockout_mask & ~missing_stock_evidence_mask
    target_label = target_label.where(~conservative_mask, "EXCLUDED_FROM_TARGET")
    target_warning = _append_warning(target_warning, conservative_mask, "CONSERVATIVE_NO_CLEAN_PROOF")

    if feature_consensus.notna().any():
        consensus_diagnostic = feature_consensus.notna() & (
            target_units.isna() | (feature_consensus.sub(target_units).abs().gt(0.01))
        )
        target_warning = _append_warning(
            target_warning,
            consensus_diagnostic,
            "FEATURE_CONSENSUS_DIAGNOSTIC_ONLY",
        )

    target_units = target_units.where(target_units.isna() | target_units.ge(0.0), np.nan)
    target_units = target_units.clip(lower=0.0)

    derived = pd.DataFrame(
        {
            "realized_sales_units": realized,
            "stock_constrained_flag": stock_constrained,
            "stock_integrity_issue_flag": integrity_flag.astype(int),
            "sufficient_stock_observed_flag": sufficient_stock_observed,
            "sufficient_stock_demand_units_target": target_units,
            "target_quality_label": target_label,
            "target_weight": target_weight.clip(lower=0.0, upper=1.0),
            "target_repair_basis": target_repair_basis,
            "target_warning": target_warning,
        },
        index=working.index,
    )
    invalid_labels = ~derived["target_quality_label"].isin(APPROVED_TARGET_QUALITY_LABELS)
    if bool(invalid_labels.any()):
        bad = derived.loc[invalid_labels, "target_quality_label"].unique().tolist()
        raise SufficientStockDemandTargetError(f"Internal label contract violation: {bad}")

    return pd.concat([working, derived], axis=1)


def _empty_output_frame(index: pd.Index) -> pd.DataFrame:
    return pd.DataFrame(
        {column_name: pd.Series(dtype="float64" if column_name.endswith("_flag") or column_name.endswith("_units") or column_name.endswith("_weight") else "object") for column_name in SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS},
        index=index,
    )


def _resolve_realized_sales_units(frame: pd.DataFrame) -> pd.Series:
    if not any(column_name in frame.columns for column_name in REALIZED_SALES_SOURCE_COLUMNS):
        raise SufficientStockDemandTargetError(
            "Missing realized-sales source column. Expected one of: "
            + ", ".join(REALIZED_SALES_SOURCE_COLUMNS)
        )
    values = _first_optional_numeric(frame, REALIZED_SALES_SOURCE_COLUMNS)
    return values.clip(lower=0.0)


def _resolve_stock_basis_units(frame: pd.DataFrame) -> pd.Series:
    basis = _first_optional_numeric(frame, STOCK_BASIS_SOURCE_COLUMNS, positive_only=True)
    if basis.notna().any():
        return basis
    if "current_soh" in frame.columns or "qty_on_order" in frame.columns:
        current_soh = _optional_numeric(frame, "current_soh")
        qty_on_order = _optional_numeric(frame, "qty_on_order")
        combined = current_soh.fillna(0.0) + qty_on_order.fillna(0.0)
        return combined.where(combined.gt(0.0))
    return basis


def _resolve_demand_reference_units(frame: pd.DataFrame) -> pd.Series:
    if "demand_reference_units" in frame.columns:
        return _optional_numeric(frame, "demand_reference_units")
    baseline = _optional_numeric(frame, "baseline_expected_units")
    required = _optional_numeric(frame, "required_implied_units")
    if baseline.notna().any() or required.notna().any():
        return pd.concat([baseline, required], axis=1).max(axis=1, skipna=True)
    return pd.Series(np.nan, index=frame.index, dtype="float64")


def _resolve_promo_window_days(frame: pd.DataFrame) -> pd.Series:
    return _first_optional_numeric(frame, PROMO_WINDOW_DAY_COLUMNS, positive_only=True)


def _resolve_promo_sales_day_count(frame: pd.DataFrame) -> pd.Series:
    return _first_optional_numeric(frame, PROMO_SALES_DAY_COLUMNS).fillna(0.0)


def _resolve_stockout_flag(
    frame: pd.DataFrame,
    *,
    realized: pd.Series,
    stock_basis: pd.Series,
    sell_through: pd.Series,
    post_14d_units: pd.Series,
) -> pd.Series:
    if "target_stockout_flag" in frame.columns:
        return _optional_numeric(frame, "target_stockout_flag").fillna(0.0).ge(1.0).astype(int)
    observed = _optional_numeric(frame, "actual_stockout_flag")
    if observed.notna().any():
        return observed.fillna(0.0).ge(1.0).astype(int)
    zero_soh = _optional_numeric(frame, "observed_zero_soh_event_flag").ge(1.0)
    constrained = _optional_numeric(frame, "stock_constrained_sales_evidence_flag").ge(1.0)
    heuristic = (
        stock_basis.gt(0.0)
        & (
            realized.ge(stock_basis * 0.98)
            | ((post_14d_units.gt(0.0)) & (sell_through.ge(0.9)))
        )
    )
    return (zero_soh | constrained | heuristic).astype(int)


def _resolve_pure_underallocation_flag(
    frame: pd.DataFrame,
    *,
    stock_basis: pd.Series,
    demand_reference: pd.Series,
) -> pd.Series:
    if "target_underallocation_flag" in frame.columns and "target_stockout_flag" in frame.columns:
        underalloc = _optional_numeric(frame, "target_underallocation_flag").fillna(0.0).ge(1.0)
        stockout = _optional_numeric(frame, "target_stockout_flag").fillna(0.0).ge(1.0)
        return (underalloc & ~stockout).astype(int)
    valid = stock_basis.gt(0.0) & demand_reference.notna() & demand_reference.gt(0.0)
    return (valid & stock_basis.lt(demand_reference * 0.85)).astype(int)


def _resolve_integrity_issue_flag(
    frame: pd.DataFrame,
    *,
    realized: pd.Series,
    stock_basis: pd.Series,
    current_soh: pd.Series,
    actual_refund_units: pd.Series,
) -> pd.Series:
    provided = _optional_numeric(frame, "stock_integrity_issue_flag")
    if provided.notna().any():
        return provided.fillna(0.0).ge(1.0).astype(int)
    negative_soh = _optional_numeric(frame, "observed_negative_soh_event_flag").ge(1.0)
    current_negative = current_soh.lt(0.0)
    missing_basis_with_sales = stock_basis.isna() & realized.gt(0.0)
    zero_basis_with_sales = stock_basis.le(0.0) & realized.gt(0.0)
    refund_dominated = actual_refund_units.notna() & realized.gt(0.0) & actual_refund_units.ge(realized)
    return (
        negative_soh | current_negative | missing_basis_with_sales | zero_basis_with_sales | refund_dominated
    ).astype(int)


def _first_optional_numeric(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    positive_only: bool = False,
) -> pd.Series:
    present_columns = [column_name for column_name in columns if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    if positive_only:
        candidate_frame = candidate_frame.where(candidate_frame > 0.0)
    return candidate_frame.bfill(axis=1).iloc[:, 0]


def _optional_numeric(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    valid = denominator.notna() & denominator.gt(0.0)
    ratio = numerator / denominator.where(valid)
    return ratio.where(valid)


def _cap_repair(value: pd.Series, *ceilings: pd.Series) -> pd.Series:
    capped = value.copy()
    for ceiling in ceilings:
        capped = np.minimum(capped, ceiling)
    return capped


def _append_warning(existing: pd.Series, mask: pd.Series, code: str) -> pd.Series:
    updated = existing.fillna("").astype(str)
    apply_mask = mask.fillna(False)
    appended = np.where(
        apply_mask,
        np.where(updated.eq(""), code, updated + "|" + code),
        updated,
    )
    return pd.Series(appended, index=existing.index, dtype="object")
