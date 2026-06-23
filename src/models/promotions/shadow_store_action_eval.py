"""Shadow-only store action evaluation helpers (Phase 4B.9+). Not used in production Stage 11."""
from __future__ import annotations

import numpy as np
import pandas as pd

from surfaces.promotions.reporting.allocation_stock_contract import (
    build_allocation_stock_contract_frame,
)

SHADOW_ACTION_CAP_BASIS = "MIN_STOCK_BASIS_DEMAND_REFERENCE"
MIN_FLOOR_UNITS = 2.0
BUY_NOW_LEAD_DAYS = 21


def _days_until_promo(frame: pd.DataFrame) -> pd.Series:
    start = pd.to_datetime(frame["promotion_start_date"], errors="coerce")
    as_of = pd.to_datetime(frame["extraction_as_of_date"], errors="coerce")
    return (start - as_of).dt.days.fillna(14).clip(lower=0).astype("int64")


def _promo_window_days(frame: pd.DataFrame) -> pd.Series:
    start = pd.to_datetime(frame["promotion_start_date"], errors="coerce")
    end = pd.to_datetime(frame["promotional_end_date"], errors="coerce")
    days = (end - start).dt.days + 1
    return days.fillna(frame.get("promo_days", 14)).fillna(14).clip(lower=1).astype("int64")


def _pre_promo_demand(frame: pd.DataFrame, lead_days: pd.Series) -> pd.Series:
    baseline7 = pd.to_numeric(frame["feature_expected_baseline_units_first_7_days"], errors="coerce").fillna(0.0)
    daily = pd.to_numeric(frame["avg_daily_units"], errors="coerce").fillna(0.0)
    from_daily = daily * lead_days.astype("float64")
    return np.maximum(baseline7 * (lead_days.astype("float64") / 7.0), from_daily).clip(lower=0.0)


def _floor_units(frame: pd.DataFrame) -> pd.Series:
    end_floor = pd.to_numeric(frame["feature_end_of_promo_target_floor_units"], errors="coerce")
    trust = pd.to_numeric(frame["feature_trust_floor_units_dynamic"], errors="coerce")
    floor = pd.concat([end_floor, trust], axis=1).max(axis=1)
    return floor.fillna(MIN_FLOOR_UNITS).clip(lower=MIN_FLOOR_UNITS)


def build_shadow_store_action_frame(
    frame: pd.DataFrame,
    *,
    demand_col: str,
    variant: str,
) -> pd.DataFrame:
    """Build store actions from predicted demand via allocation stock contract (evaluation only)."""
    lead = _days_until_promo(frame)
    pre = _pre_promo_demand(frame, lead)
    floor = _floor_units(frame)
    promo_demand = pd.to_numeric(frame[demand_col], errors="coerce").fillna(0.0).clip(lower=0.0)
    contract = build_allocation_stock_contract_frame(
        model_run_date=frame["extraction_as_of_date"].astype(str),
        promotion_start_date=frame["promotion_start_date"],
        promotion_end_date=frame["promotional_end_date"],
        current_soh_at_model_run=frame["current_soh"],
        confirmed_inbound_units_before_promo_start=frame["qty_on_order"],
        expected_pre_promo_demand_units=pre,
        expected_promo_window_demand_units=promo_demand,
        floor_units_required_at_promo_start=floor,
        pack_size=frame["pack_size"],
        allow_floor_only_replenishment=True,
    )
    out = frame.copy()
    out["variant"] = variant
    out["expected_promo_demand"] = promo_demand
    out["raw_stock_gap_units"] = contract["raw_stock_gap_units"]
    out["uncapped_order_units"] = contract["recommended_order_units"]
    out["final_order_units"] = out["uncapped_order_units"]
    out["days_until_promo_start"] = lead
    out["promo_window_days"] = _promo_window_days(frame)
    return _assign_store_action_fields(out)


def _assign_store_action_fields(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    order = pd.to_numeric(out["final_order_units"], errors="coerce").fillna(0).clip(lower=0).round(0).astype("int64")
    promo_demand = pd.to_numeric(out["expected_promo_demand"], errors="coerce").fillna(0.0)
    lead = pd.to_numeric(out["days_until_promo_start"], errors="coerce").fillna(0)
    stock_basis = pd.to_numeric(out["stock_basis_units"], errors="coerce")
    demand_ref = pd.to_numeric(out["demand_reference_units"], errors="coerce")

    out["final_order_units"] = order
    out["store_action"] = np.where(order.gt(0), "BUY", np.where(promo_demand.gt(0), "HOLD", "DO_NOT_BUY"))
    out["priority_band"] = np.where(
        order.gt(0) & lead.le(BUY_NOW_LEAD_DAYS),
        "BUY_NOW",
        np.where(order.gt(0), "WATCH", np.where(promo_demand.gt(0), "HOLD", "DO_NOT_BUY")),
    )
    out["risk_over_stock_basis"] = (order.gt(stock_basis) & stock_basis.gt(0)).astype(int)
    out["risk_over_demand_reference"] = (order.gt(demand_ref) & demand_ref.gt(0)).astype(int)
    out["risk_over_2x_demand_reference"] = (order.gt(2 * demand_ref) & demand_ref.gt(0)).astype(int)
    out["risk_tiny_demand"] = promo_demand.le(1).astype(int)
    return out


def apply_shadow_conservative_action_cap(
    frame: pd.DataFrame,
    *,
    realized_sales_col: str = "realized_sales_units",
) -> pd.DataFrame:
    """Cap shadow evaluation order units after pack rounding; does not alter demand forecast."""
    out = frame.copy()
    if "uncapped_order_units" not in out.columns:
        out["uncapped_order_units"] = pd.to_numeric(out["final_order_units"], errors="coerce").fillna(0)

    uncapped = pd.to_numeric(out["uncapped_order_units"], errors="coerce").fillna(0).clip(lower=0).round(0)
    stock_basis = pd.to_numeric(out["stock_basis_units"], errors="coerce")
    demand_ref = pd.to_numeric(out["demand_reference_units"], errors="coerce")
    realized = pd.to_numeric(out.get(realized_sales_col), errors="coerce").fillna(0.0)
    promo_demand = pd.to_numeric(out["expected_promo_demand"], errors="coerce").fillna(0.0)

    has_both = stock_basis.notna() & stock_basis.gt(0) & demand_ref.notna() & demand_ref.gt(0)
    cap_ceiling = np.minimum(stock_basis, demand_ref)
    capped = uncapped.copy()
    if bool(has_both.any()):
        cap_int = cap_ceiling.loc[has_both].round(0).astype("int64")
        capped.loc[has_both] = np.minimum(uncapped.loc[has_both].round(0), cap_int).astype("int64")
    capped = capped.round(0).astype("int64")

    removed = (uncapped - capped).clip(lower=0)
    applied = has_both & removed.gt(0)
    realized_exceeds = has_both & realized.gt(cap_ceiling)
    review = applied | realized_exceeds

    repaired = out.get("target_quality_label", pd.Series("", index=out.index)).astype(str).eq("STOCK_CONSTRAINED_REPAIRED")
    stockout = pd.to_numeric(out.get("target_stockout_flag"), errors="coerce").fillna(0).ge(1)
    strong_evidence = repaired | stockout

    out["action_cap_applied_flag"] = applied.astype(int)
    out["action_cap_basis"] = np.where(has_both, SHADOW_ACTION_CAP_BASIS, "")
    out["action_cap_units_removed"] = removed.round(0).astype("int64")
    out["realized_exceeds_action_cap_flag"] = realized_exceeds.astype(int)
    out["action_cap_review_flag"] = review.astype(int)
    out["final_order_units"] = capped

    # Zero-order BUY forbidden; strong evidence -> review on HOLD not BUY.
    store_action = np.where(
        capped.gt(0),
        "BUY",
        np.where(
            promo_demand.gt(0),
            np.where(strong_evidence & applied, "REVIEW", "HOLD"),
            "DO_NOT_BUY",
        ),
    )
    out["store_action"] = store_action
    out["zero_order_buy_invalid_flag"] = ((store_action == "BUY") & capped.le(0)).astype(int)
    return _assign_store_action_fields(out)


def shadow_action_summary_metrics(actions: pd.DataFrame) -> dict[str, float | int]:
    order = pd.to_numeric(actions["final_order_units"], errors="coerce").fillna(0)
    demand = pd.to_numeric(actions["expected_promo_demand"], errors="coerce").fillna(0)
    sb = pd.to_numeric(actions["stock_basis_units"], errors="coerce")
    dr = pd.to_numeric(actions["demand_reference_units"], errors="coerce")
    buy = actions["store_action"].astype(str).eq("BUY")
    cap_flag = actions["action_cap_applied_flag"] if "action_cap_applied_flag" in actions.columns else pd.Series(0, index=actions.index)
    cap_removed = actions["action_cap_units_removed"] if "action_cap_units_removed" in actions.columns else pd.Series(0, index=actions.index)
    realized_ex = actions["realized_exceeds_action_cap_flag"] if "realized_exceeds_action_cap_flag" in actions.columns else pd.Series(0, index=actions.index)
    zero_buy = actions["zero_order_buy_invalid_flag"] if "zero_order_buy_invalid_flag" in actions.columns else pd.Series(0, index=actions.index)
    return {
        "buy_count": int(buy.sum()),
        "hold_count": int(actions["store_action"].astype(str).eq("HOLD").sum()),
        "total_order_units": float(order.sum()),
        "tiny_demand_rows": int(demand.le(1).sum()),
        "tiny_demand_buy": int((demand.le(1) & buy).sum()),
        "order_over_stock_basis": int((order.gt(sb) & sb.gt(0)).sum()),
        "order_over_demand_reference": int((order.gt(dr) & dr.gt(0)).sum()),
        "order_over_2x_demand_reference": int((order.gt(2 * dr) & dr.gt(0)).sum()),
        "p99_order": float(order.quantile(0.99)),
        "max_order": float(order.max()),
        "caps_applied": int(pd.to_numeric(cap_flag, errors="coerce").fillna(0).sum()),
        "units_removed_by_cap": float(pd.to_numeric(cap_removed, errors="coerce").fillna(0).sum()),
        "realized_exceeds_cap": int(pd.to_numeric(realized_ex, errors="coerce").fillna(0).sum()),
        "zero_order_buy": int(pd.to_numeric(zero_buy, errors="coerce").fillna(0).sum()),
    }
