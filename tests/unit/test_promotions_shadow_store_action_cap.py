from __future__ import annotations

import pandas as pd
import pytest

from models.promotions.shadow_store_action_eval import (
    SHADOW_ACTION_CAP_BASIS,
    apply_shadow_conservative_action_cap,
    build_shadow_store_action_frame,
)


def _eval_row(**overrides: object) -> pd.DataFrame:
    base = {
        "promotion_row_key": "k1",
        "promotion_start_date": "2026-06-01",
        "promotional_end_date": "2026-06-14",
        "extraction_as_of_date": "2026-05-20",
        "current_soh": 1.0,
        "qty_on_order": 0.0,
        "pack_size": 1.0,
        "avg_daily_units": 0.5,
        "feature_expected_baseline_units_first_7_days": 2.0,
        "feature_end_of_promo_target_floor_units": 2.0,
        "feature_trust_floor_units_dynamic": 2.0,
        "stock_basis_units": 5.0,
        "demand_reference_units": 4.0,
        "target_quality_label": "STOCK_CONSTRAINED_REPAIRED",
        "target_stockout_flag": 1,
        "target_repair_basis": "REPAIR_UNDERALLOCATION|CEILING_MIN_DEMAND_STOCK",
        "target_weight": 0.2,
        "shadow_predicted_demand": 10.0,
        "realized_sales_units": 3.0,
    }
    base.update(overrides)
    return pd.DataFrame([base])


def test_shadow_action_cap_applies_min_stock_and_demand() -> None:
    built = build_shadow_store_action_frame(_eval_row(), demand_col="shadow_predicted_demand", variant="shadow")
    uncapped = int(built.iloc[0]["uncapped_order_units"])
    capped = apply_shadow_conservative_action_cap(built)
    assert uncapped > 4
    assert int(capped.iloc[0]["final_order_units"]) == 4
    assert capped.iloc[0]["action_cap_applied_flag"] == 1
    assert capped.iloc[0]["action_cap_basis"] == SHADOW_ACTION_CAP_BASIS


def test_cap_does_not_alter_demand_forecast() -> None:
    built = build_shadow_store_action_frame(_eval_row(), demand_col="shadow_predicted_demand", variant="shadow")
    demand_before = float(built.iloc[0]["expected_promo_demand"])
    capped = apply_shadow_conservative_action_cap(built)
    assert float(capped.iloc[0]["expected_promo_demand"]) == demand_before


def test_uncapped_order_preserved() -> None:
    built = build_shadow_store_action_frame(_eval_row(), demand_col="shadow_predicted_demand", variant="shadow")
    capped = apply_shadow_conservative_action_cap(built)
    assert int(capped.iloc[0]["uncapped_order_units"]) == int(built.iloc[0]["uncapped_order_units"])
    assert int(capped.iloc[0]["action_cap_units_removed"]) > 0


def test_realized_exceeds_cap_sets_review_flag() -> None:
    built = build_shadow_store_action_frame(
        _eval_row(realized_sales_units=8.0, stock_basis_units=5.0, demand_reference_units=6.0),
        demand_col="shadow_predicted_demand",
        variant="shadow",
    )
    capped = apply_shadow_conservative_action_cap(built)
    assert capped.iloc[0]["realized_exceeds_action_cap_flag"] == 1
    assert capped.iloc[0]["action_cap_review_flag"] == 1


def test_zero_capped_order_not_buy() -> None:
    built = build_shadow_store_action_frame(
        _eval_row(current_soh=20.0, shadow_predicted_demand=1.0, stock_basis_units=0.0, demand_reference_units=0.0),
        demand_col="shadow_predicted_demand",
        variant="shadow",
    )
    capped = apply_shadow_conservative_action_cap(built)
    assert capped.iloc[0]["store_action"] != "BUY"
    assert capped.iloc[0]["zero_order_buy_invalid_flag"] == 0


def test_final_order_does_not_exceed_cap_after_rounding() -> None:
    built = build_shadow_store_action_frame(
        _eval_row(pack_size=3.0, shadow_predicted_demand=12.0, stock_basis_units=5.0, demand_reference_units=4.0),
        demand_col="shadow_predicted_demand",
        variant="shadow",
    )
    capped = apply_shadow_conservative_action_cap(built)
    assert int(capped.iloc[0]["final_order_units"]) <= 4


def test_missing_caps_do_not_apply_silent_cap() -> None:
    built = build_shadow_store_action_frame(
        _eval_row(stock_basis_units=float("nan"), demand_reference_units=float("nan")),
        demand_col="shadow_predicted_demand",
        variant="shadow",
    )
    capped = apply_shadow_conservative_action_cap(built)
    assert capped.iloc[0]["action_cap_applied_flag"] == 0
    assert capped.iloc[0]["action_cap_basis"] == ""


def test_legacy_build_path_has_no_cap_fields_by_default() -> None:
    built = build_shadow_store_action_frame(
        _eval_row(shadow_predicted_demand=3.0).rename(columns={"shadow_predicted_demand": "legacy_predicted_demand"}),
        demand_col="legacy_predicted_demand",
        variant="legacy",
    )
    assert "uncapped_order_units" in built.columns
    assert "action_cap_applied_flag" not in built.columns
