from __future__ import annotations

"""Explicit stock, demand, and order-unit calculation contract for store allocation reports."""

from dataclasses import dataclass
import logging
import math
import time
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ALLOCATION_CONTRACT_STEP_NUMBER = 11

# Canonical contract columns in business-reading order.
ALLOCATION_CONTRACT_COLUMN_ORDER: tuple[str, ...] = (
    # Identification (subset — full identity lives in store-facing schema)
    "store_number",
    "promotion_id",
    "promotion_name",
    "sku_number",
    "sku_description",
    # Dates
    "model_run_date",
    "promotion_start_date",
    "promotion_end_date",
    "days_until_promo_start",
    "promo_window_days",
    # Stock at model run
    "current_soh_at_model_run",
    "confirmed_inbound_units_before_promo_start",
    # Demand
    "expected_pre_promo_demand_units",
    "expected_promo_window_demand_units",
    "total_expected_demand_model_run_to_promo_end_units",
    # Promo start stock logic
    "projected_soh_at_promo_start_before_order",
    "floor_units_required_at_promo_start",
    "target_soh_at_promo_start",
    "raw_stock_gap_units",
    # Order decision
    "recommended_order_units_before_pack_rounding",
    "recommended_order_units",
    "projected_soh_at_promo_start_after_order",
    "projected_soh_at_promo_end_after_order",
    # Decision explanation
    "priority_band",
    "operator_decision",
    "operator_action",
    "stock_position_status",
    "order_reason_code",
    "risk_flag",
    "review_flag",
    "audit_notes",
)

# Deprecated alias columns retained for one release.
ALLOCATION_CONTRACT_ALIAS_COLUMNS: dict[str, str] = {
    "expected_units_before_promo_start": "expected_pre_promo_demand_units",
    "projected_SOH_at_promo_start": "projected_soh_at_promo_start_before_order",
    "expected_promo_demand": "expected_promo_window_demand_units",
    "projected_stock_gap_units": "raw_stock_gap_units",
    "order_units": "recommended_order_units",
    "current_soh": "current_soh_at_model_run",
    "on_order_at_advice_time": "confirmed_inbound_units_before_promo_start",
}

HARD_ORDER_BLOCKER_CODES: frozenset[str] = frozenset(
    {
        "blocked_by_sparse_history",
        "blocked_by_low_confidence",
        "blocked_by_capital_rule",
        "blocked_by_manual_review",
        "blocked_by_supplier_or_pack_constraint",
        "blocked_by_invalid_data",
    }
)

DEMAND_LABEL_NO_DEMAND = "NO_DEMAND"


@dataclass(frozen=True)
class AllocationStockContractRow:
    model_run_date: str
    promotion_start_date: str
    promotion_end_date: str
    days_until_promo_start: int
    promo_window_days: int
    current_soh_at_model_run: float
    confirmed_inbound_units_before_promo_start: float
    expected_pre_promo_demand_units: float
    expected_promo_window_demand_units: float
    floor_units_required_at_promo_start: float
    pack_size: float = 1.0
    allow_floor_only_replenishment: bool = True

    def compute(self) -> dict[str, int | float | str]:
        return compute_allocation_stock_contract_row(self)


def _as_whole_units(value: float) -> int:
    return int(max(round(float(value)), 0))


def _round_up_to_pack(units: float, pack_size: float) -> int:
    gap = max(float(units), 0.0)
    pack = max(float(pack_size or 1.0), 1.0)
    if pack <= 1.0:
        return int(math.ceil(gap))
    return int(math.ceil(gap / pack) * pack)


def compute_days_until_promo_start(
    *,
    model_run_date: str | pd.Timestamp | None,
    promotion_start_date: str | pd.Timestamp | None,
) -> int:
    model_dt = pd.to_datetime(model_run_date, errors="coerce")
    promo_start_dt = pd.to_datetime(promotion_start_date, errors="coerce")
    if pd.isna(model_dt) or pd.isna(promo_start_dt):
        return 0
    return max(int((promo_start_dt - model_dt).days), 0)


def compute_promo_window_days(
    *,
    promotion_start_date: str | pd.Timestamp | None,
    promotion_end_date: str | pd.Timestamp | None,
) -> int:
    start_dt = pd.to_datetime(promotion_start_date, errors="coerce")
    end_dt = pd.to_datetime(promotion_end_date, errors="coerce")
    if pd.isna(start_dt) or pd.isna(end_dt):
        return 1
    return max(int((end_dt - start_dt).days) + 1, 1)


def compute_allocation_stock_contract_row(row: AllocationStockContractRow) -> dict[str, int | float | str]:
    """Compute one auditable allocation row from explicit stock/demand inputs."""
    current_soh = max(float(row.current_soh_at_model_run), 0.0)
    inbound = max(float(row.confirmed_inbound_units_before_promo_start), 0.0)
    pre_promo_demand = max(float(row.expected_pre_promo_demand_units), 0.0)
    promo_demand = max(float(row.expected_promo_window_demand_units), 0.0)
    floor = max(float(row.floor_units_required_at_promo_start), 0.0)

    projected_before = max(current_soh + inbound - pre_promo_demand, 0.0)
    target_start = promo_demand + floor
    if promo_demand <= 0.0 and not row.allow_floor_only_replenishment:
        target_start = 0.0
    raw_gap = max(target_start - projected_before, 0.0)
    before_pack = _as_whole_units(raw_gap)
    recommended = _round_up_to_pack(before_pack, row.pack_size)
    projected_after = projected_before + recommended
    projected_end = max(projected_after - promo_demand, 0.0)
    total_demand = pre_promo_demand + promo_demand

    stock_position_status = _derive_stock_position_status(
        projected_before=projected_before,
        target_start=target_start,
        raw_gap=raw_gap,
        promo_demand=promo_demand,
    )

    return {
        "model_run_date": str(row.model_run_date or ""),
        "promotion_start_date": str(row.promotion_start_date or ""),
        "promotion_end_date": str(row.promotion_end_date or ""),
        "days_until_promo_start": int(row.days_until_promo_start),
        "promo_window_days": int(row.promo_window_days),
        "current_soh_at_model_run": _as_whole_units(current_soh),
        "confirmed_inbound_units_before_promo_start": _as_whole_units(inbound),
        "expected_pre_promo_demand_units": _as_whole_units(pre_promo_demand),
        "expected_promo_window_demand_units": _as_whole_units(promo_demand),
        "projected_soh_at_promo_start_before_order": _as_whole_units(projected_before),
        "floor_units_required_at_promo_start": _as_whole_units(floor),
        "target_soh_at_promo_start": _as_whole_units(target_start),
        "raw_stock_gap_units": _as_whole_units(raw_gap),
        "recommended_order_units_before_pack_rounding": before_pack,
        "recommended_order_units": recommended,
        "projected_soh_at_promo_start_after_order": _as_whole_units(projected_after),
        "projected_soh_at_promo_end_after_order": _as_whole_units(projected_end),
        "total_expected_demand_model_run_to_promo_end_units": _as_whole_units(total_demand),
        "stock_position_status": stock_position_status,
        "order_reason_code": "",
    }


def _derive_stock_position_status(
    *,
    projected_before: float,
    target_start: float,
    raw_gap: float,
    promo_demand: float,
) -> str:
    if raw_gap > 0.0:
        return "SHORT_AT_PROMO_START"
    if projected_before >= target_start and promo_demand > 0.0:
        return "COVERED_FOR_PROMO"
    if projected_before >= target_start and promo_demand <= 0.0:
        return "NO_PROMO_DEMAND_COVERED"
    return "AT_OR_ABOVE_TARGET"


def build_allocation_stock_contract_frame(
    *,
    model_run_date: str | pd.Series | None,
    promotion_start_date: pd.Series,
    promotion_end_date: pd.Series,
    current_soh_at_model_run: pd.Series,
    confirmed_inbound_units_before_promo_start: pd.Series,
    expected_pre_promo_demand_units: pd.Series,
    expected_promo_window_demand_units: pd.Series,
    floor_units_required_at_promo_start: pd.Series,
    pack_size: pd.Series | None = None,
    allow_floor_only_replenishment: bool = True,
) -> pd.DataFrame:
    """Vectorised contract builder for store-facing allocation rows."""
    index = promotion_start_date.index
    if pack_size is None:
        pack_size = pd.Series(1.0, index=index, dtype="float64")
    if isinstance(model_run_date, pd.Series):
        model_run_series = model_run_date.astype(str)
    else:
        model_run_series = pd.Series(str(model_run_date or ""), index=index, dtype="object")

    days_until = pd.Series(
        [
            compute_days_until_promo_start(
                model_run_date=model_run,
                promotion_start_date=promo_start,
            )
            for model_run, promo_start in zip(
                model_run_series.tolist(),
                promotion_start_date.tolist(),
                strict=False,
            )
        ],
        index=index,
        dtype="int64",
    )
    promo_window = pd.Series(
        [
            compute_promo_window_days(
                promotion_start_date=promo_start,
                promotion_end_date=promo_end,
            )
            for promo_start, promo_end in zip(
                promotion_start_date.tolist(),
                promotion_end_date.tolist(),
                strict=False,
            )
        ],
        index=index,
        dtype="int64",
    )

    current_soh = pd.to_numeric(current_soh_at_model_run, errors="coerce").fillna(0.0).clip(lower=0.0)
    inbound = pd.to_numeric(confirmed_inbound_units_before_promo_start, errors="coerce").fillna(0.0).clip(lower=0.0)
    pre_promo = pd.to_numeric(expected_pre_promo_demand_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    promo_demand = pd.to_numeric(expected_promo_window_demand_units, errors="coerce").fillna(0.0).clip(lower=0.0)
    floor = pd.to_numeric(floor_units_required_at_promo_start, errors="coerce").fillna(0.0).clip(lower=0.0)
    pack = pd.to_numeric(pack_size, errors="coerce").fillna(1.0).clip(lower=1.0)

    projected_before = (current_soh + inbound - pre_promo).clip(lower=0.0)
    target_start = promo_demand + floor
    if not allow_floor_only_replenishment:
        target_start = target_start.where(promo_demand.gt(0.0), 0.0)
    raw_gap = (target_start - projected_before).clip(lower=0.0)
    before_pack = raw_gap.round(0).astype("int64")
    recommended = pd.Series(
        [
            _round_up_to_pack(gap_value, pack_value)
            for gap_value, pack_value in zip(before_pack.tolist(), pack.tolist(), strict=False)
        ],
        index=index,
        dtype="int64",
    )
    projected_after = projected_before + recommended.astype("float64")
    projected_end = (projected_after - promo_demand).clip(lower=0.0)
    total_demand = pre_promo + promo_demand

    stock_position_status = pd.Series("AT_OR_ABOVE_TARGET", index=index, dtype="object")
    stock_position_status = stock_position_status.where(raw_gap.le(0.0), "SHORT_AT_PROMO_START")
    stock_position_status = stock_position_status.where(
        ~(raw_gap.le(0.0) & projected_before.ge(target_start) & promo_demand.gt(0.0)),
        "COVERED_FOR_PROMO",
    )
    stock_position_status = stock_position_status.where(
        ~(raw_gap.le(0.0) & projected_before.ge(target_start) & promo_demand.le(0.0)),
        "NO_PROMO_DEMAND_COVERED",
    )

    return pd.DataFrame(
        {
            "model_run_date": model_run_series.astype(str),
            "promotion_start_date": promotion_start_date.astype(str),
            "promotion_end_date": promotion_end_date.astype(str),
            "days_until_promo_start": days_until,
            "promo_window_days": promo_window,
            "current_soh_at_model_run": current_soh.round(0).astype("int64"),
            "confirmed_inbound_units_before_promo_start": inbound.round(0).astype("int64"),
            "expected_pre_promo_demand_units": pre_promo.round(0).astype("int64"),
            "expected_promo_window_demand_units": promo_demand.round(0).astype("int64"),
            "projected_soh_at_promo_start_before_order": projected_before.round(0).astype("int64"),
            "floor_units_required_at_promo_start": floor.round(0).astype("int64"),
            "target_soh_at_promo_start": target_start.round(0).astype("int64"),
            "raw_stock_gap_units": raw_gap.round(0).astype("int64"),
            "recommended_order_units_before_pack_rounding": before_pack,
            "recommended_order_units": recommended,
            "projected_soh_at_promo_start_after_order": projected_after.round(0).astype("int64"),
            "projected_soh_at_promo_end_after_order": projected_end.round(0).astype("int64"),
            "total_expected_demand_model_run_to_promo_end_units": total_demand.round(0).astype("int64"),
            "stock_position_status": stock_position_status.astype(str),
            "order_reason_code": pd.Series([""] * len(index), index=index, dtype="object"),
        },
        index=index,
    )


def apply_allocation_order_blockers(
    *,
    contract_frame: pd.DataFrame,
    hard_blocker_codes: pd.Series,
    pack_blocker_mask: pd.Series | None = None,
) -> pd.DataFrame:
    """Apply documented hard blockers that may zero recommended order units."""
    out = contract_frame.copy()
    blocker = hard_blocker_codes.fillna("").astype(str).str.strip()
    if pack_blocker_mask is not None:
        blocker = blocker.where(~pack_blocker_mask, "blocked_by_supplier_or_pack_constraint")
    has_hard_blocker = blocker.isin(HARD_ORDER_BLOCKER_CODES)
    raw_gap = pd.to_numeric(out["raw_stock_gap_units"], errors="coerce").fillna(0.0)
    recommended = pd.to_numeric(out["recommended_order_units"], errors="coerce").fillna(0.0)
    recommended = recommended.where(~has_hard_blocker, 0.0)
    recommended = recommended.where(~((raw_gap.gt(0.0)) & has_hard_blocker), 0.0)
    out["order_reason_code"] = blocker.where(has_hard_blocker, out["order_reason_code"].astype(str))
    out["recommended_order_units"] = recommended.round(0).astype("int64")
    projected_before = pd.to_numeric(
        out["projected_soh_at_promo_start_before_order"], errors="coerce"
    ).fillna(0.0)
    promo_demand = pd.to_numeric(out["expected_promo_window_demand_units"], errors="coerce").fillna(0.0)
    projected_after = projected_before + out["recommended_order_units"].astype("float64")
    out["projected_soh_at_promo_start_after_order"] = projected_after.round(0).astype("int64")
    out["projected_soh_at_promo_end_after_order"] = (
        (projected_after - promo_demand).clip(lower=0.0).round(0).astype("int64")
    )
    return out


def sync_allocation_contract_aliases(frame: pd.DataFrame) -> pd.DataFrame:
    """Populate deprecated alias columns from canonical contract fields."""
    out = frame.copy()
    for alias, canonical in ALLOCATION_CONTRACT_ALIAS_COLUMNS.items():
        if canonical in out.columns:
            out[alias] = out[canonical]
    return out


def compose_contract_audit_demand_label(
    *,
    expected_promo_window_demand_units: float,
    demand_evidence_label: str,
) -> str:
    promo_demand = max(float(expected_promo_window_demand_units), 0.0)
    label = str(demand_evidence_label or "").strip().upper()
    if promo_demand > 0.0 and label == DEMAND_LABEL_NO_DEMAND:
        return "PROMO_DEMAND_PRESENT"
    if promo_demand <= 0.0 and not label:
        return DEMAND_LABEL_NO_DEMAND
    return label or ("PROMO_DEMAND_PRESENT" if promo_demand > 0.0 else DEMAND_LABEL_NO_DEMAND)


def compose_contract_audit_notes(
    *,
    order_reason_code: str,
    expected_promo_window_demand_units: float,
    demand_evidence_label: str,
    stock_position_status: str,
    raw_stock_gap_units: float,
    recommended_order_units: float,
    review_reason: str = "",
    blocker_reason: str = "",
    confidence_pct: float = 0.0,
) -> str:
    parts: list[str] = []
    review_text = str(review_reason or "").strip()
    blocker_text = str(blocker_reason or "").strip()
    if review_text:
        parts.append(f"review={review_text}")
    if blocker_text:
        parts.append(f"blocker={blocker_text}")
    order_reason = str(order_reason_code or "").strip()
    if order_reason:
        parts.append(f"order_reason={order_reason}")
    demand_label = compose_contract_audit_demand_label(
        expected_promo_window_demand_units=expected_promo_window_demand_units,
        demand_evidence_label=demand_evidence_label,
    )
    parts.extend(
        [
            f"demand={demand_label}",
            f"stock_position={str(stock_position_status or '').strip()}",
            f"raw_gap={int(max(round(float(raw_stock_gap_units)), 0))}",
            f"recommended_units={int(max(round(float(recommended_order_units)), 0))}",
            f"confidence_pct={int(max(round(float(confidence_pct)), 0))}",
        ]
    )
    return "; ".join(part for part in parts if part and not part.endswith("="))


def reconcile_priority_and_operator_action(
    *,
    priority_band: pd.Series,
    operator_action: pd.Series,
    raw_stock_gap_units: pd.Series,
    recommended_order_units: pd.Series,
    order_reason_code: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Prevent BUY_NOW + DO_NOT_BUY unless a hard blocker is documented."""
    band = priority_band.astype(str).str.strip().str.upper()
    action = operator_action.astype(str).str.strip().str.upper()
    gap = pd.to_numeric(raw_stock_gap_units, errors="coerce").fillna(0.0)
    order = pd.to_numeric(recommended_order_units, errors="coerce").fillna(0.0)
    blocker = order_reason_code.fillna("").astype(str).str.strip()
    has_hard_blocker = blocker.isin(HARD_ORDER_BLOCKER_CODES)

    buy_now_do_not_buy = band.eq("BUY_NOW") & action.eq("DO_NOT_BUY")
    fix_action = buy_now_do_not_buy & gap.gt(0.0) & order.gt(0.0) & ~has_hard_blocker
    action = action.where(~fix_action, "BUY")

    review_instead = buy_now_do_not_buy & gap.gt(0.0) & ~has_hard_blocker & order.le(0.0)
    action = action.where(~review_instead, "REVIEW")
    band = band.where(~review_instead, "REVIEW")

    blocked_buy_now = buy_now_do_not_buy & has_hard_blocker
    band = band.where(~blocked_buy_now, "REVIEW")

    return band.astype(str), action.astype(str)


@dataclass(frozen=True)
class AllocationContractValidationSummary:
    row_count: int
    rows_with_positive_stock_gap: int
    rows_with_positive_order_units: int
    rows_with_gap_but_zero_order: int
    rows_with_no_demand_label_but_positive_demand: int
    rows_with_buy_now_but_do_not_buy: int
    rows_failing_stock_identity: int
    rows_failing_target_identity: int
    rows_failing_total_demand_identity: int

    def to_dict(self) -> dict[str, int]:
        return {
            "row_count": self.row_count,
            "rows_with_positive_stock_gap": self.rows_with_positive_stock_gap,
            "rows_with_positive_order_units": self.rows_with_positive_order_units,
            "rows_with_gap_but_zero_order": self.rows_with_gap_but_zero_order,
            "rows_with_no_demand_label_but_positive_demand": self.rows_with_no_demand_label_but_positive_demand,
            "rows_with_buy_now_but_do_not_buy": self.rows_with_buy_now_but_do_not_buy,
            "rows_failing_stock_identity": self.rows_failing_stock_identity,
            "rows_failing_target_identity": self.rows_failing_target_identity,
            "rows_failing_total_demand_identity": self.rows_failing_total_demand_identity,
        }


def validate_allocation_stock_contract_frame(
    frame: pd.DataFrame,
    *,
    audit_notes_column: str = "audit_notes",
    priority_band_column: str = "priority_band",
    operator_action_column: str = "operator_action",
) -> tuple[AllocationContractValidationSummary, pd.DataFrame]:
    """Validate allocation contract invariants and return issue rows."""
    required_numeric = (
        "current_soh_at_model_run",
        "confirmed_inbound_units_before_promo_start",
        "expected_pre_promo_demand_units",
        "expected_promo_window_demand_units",
        "projected_soh_at_promo_start_before_order",
        "floor_units_required_at_promo_start",
        "target_soh_at_promo_start",
        "raw_stock_gap_units",
        "recommended_order_units",
        "total_expected_demand_model_run_to_promo_end_units",
    )
    working = frame.copy()
    for column in required_numeric:
        if column not in working.columns:
            working[column] = np.nan
        working[column] = pd.to_numeric(working[column], errors="coerce")

    current_soh = working["current_soh_at_model_run"].fillna(0.0)
    inbound = working["confirmed_inbound_units_before_promo_start"].fillna(0.0)
    pre_promo = working["expected_pre_promo_demand_units"].fillna(0.0)
    promo_demand = working["expected_promo_window_demand_units"].fillna(0.0)
    projected_before = working["projected_soh_at_promo_start_before_order"].fillna(0.0)
    floor = working["floor_units_required_at_promo_start"].fillna(0.0)
    target = working["target_soh_at_promo_start"].fillna(0.0)
    raw_gap = working["raw_stock_gap_units"].fillna(0.0)
    recommended = working["recommended_order_units"].fillna(0.0)
    total_demand = working["total_expected_demand_model_run_to_promo_end_units"].fillna(0.0)
    order_reason = working.get("order_reason_code", pd.Series("", index=working.index)).fillna("").astype(str)

    expected_projected = (current_soh + inbound - pre_promo).clip(lower=0.0).round(0)
    expected_target = (promo_demand + floor).round(0)
    expected_gap = (expected_target - expected_projected).clip(lower=0.0).round(0)
    expected_total = (pre_promo + promo_demand).round(0)

    stock_identity_fail = ~projected_before.round(0).eq(expected_projected)
    target_identity_fail = ~target.round(0).eq(expected_target)
    total_demand_fail = ~total_demand.round(0).eq(expected_total)
    gap_identity_fail = ~raw_gap.round(0).eq(expected_gap)

    has_hard_blocker = order_reason.str.strip().isin(HARD_ORDER_BLOCKER_CODES)
    gap_but_zero_order = raw_gap.gt(0.0) & recommended.le(0.0) & ~has_hard_blocker

    audit_notes = working.get(audit_notes_column, pd.Series("", index=working.index)).fillna("").astype(str)
    no_demand_contradiction = audit_notes.str.contains("demand=NO_DEMAND", regex=False) & promo_demand.gt(0.0)

    priority_band = working.get(priority_band_column, pd.Series("", index=working.index)).fillna("").astype(str).str.upper()
    operator_action = working.get(operator_action_column, pd.Series("", index=working.index)).fillna("").astype(str).str.upper()
    buy_now_do_not_buy = priority_band.eq("BUY_NOW") & operator_action.eq("DO_NOT_BUY") & ~has_hard_blocker

    null_required = pd.Series(False, index=working.index)
    for column in required_numeric:
        null_required = null_required | working[column].isna()

    issue_rows: list[dict[str, Any]] = []

    def _append_issues(mask: pd.Series, issue_type: str) -> None:
        for row_index in working.index[mask.fillna(False)]:
            issue_rows.append(
                {
                    "issue_type": issue_type,
                    "row_index": int(row_index) if isinstance(row_index, (int, np.integer)) else str(row_index),
                    "sku_number": str(working.at[row_index, "sku_number"]) if "sku_number" in working.columns else "",
                }
            )

    _append_issues(stock_identity_fail, "stock_identity_fail")
    _append_issues(target_identity_fail, "target_identity_fail")
    _append_issues(gap_identity_fail, "gap_identity_fail")
    _append_issues(total_demand_fail, "total_demand_identity_fail")
    _append_issues(gap_but_zero_order, "gap_but_zero_order_without_blocker")
    _append_issues(no_demand_contradiction, "no_demand_label_with_positive_promo_demand")
    _append_issues(buy_now_do_not_buy, "buy_now_with_do_not_buy_without_blocker")
    _append_issues(null_required, "required_numeric_null")

    summary = AllocationContractValidationSummary(
        row_count=int(len(working.index)),
        rows_with_positive_stock_gap=int(raw_gap.gt(0.0).sum()),
        rows_with_positive_order_units=int(recommended.gt(0.0).sum()),
        rows_with_gap_but_zero_order=int(gap_but_zero_order.sum()),
        rows_with_no_demand_label_but_positive_demand=int(no_demand_contradiction.sum()),
        rows_with_buy_now_but_do_not_buy=int(buy_now_do_not_buy.sum()),
        rows_failing_stock_identity=int(stock_identity_fail.sum()),
        rows_failing_target_identity=int(target_identity_fail.sum()),
        rows_failing_total_demand_identity=int(total_demand_fail.sum()),
    )
    issue_frame = pd.DataFrame(issue_rows)
    return summary, issue_frame


def log_allocation_contract_validation(
    summary: AllocationContractValidationSummary,
    *,
    step_number: int = ALLOCATION_CONTRACT_STEP_NUMBER,
    started_at: float | None = None,
) -> None:
    elapsed = 0.0 if started_at is None else max(time.perf_counter() - started_at, 0.0)
    issue_count = (
        summary.rows_failing_stock_identity
        + summary.rows_failing_target_identity
        + summary.rows_failing_total_demand_identity
        + summary.rows_with_gap_but_zero_order
        + summary.rows_with_no_demand_label_but_positive_demand
        + summary.rows_with_buy_now_but_do_not_buy
    )
    logger.info(
        "STEP %s: Validate allocation arithmetic ... ✅ DONE (%.2f s) | rows=%s issues=%s",
        step_number,
        elapsed,
        summary.row_count,
        issue_count,
    )


def build_allocation_contract_validation_summary_frame(
    summary: AllocationContractValidationSummary,
) -> pd.DataFrame:
    return pd.DataFrame([summary.to_dict()])
