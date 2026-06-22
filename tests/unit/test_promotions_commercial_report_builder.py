"""Tests for commercial report builder."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from surfaces.promotions.reporting.commercial_report_builder import (
    ALLOWED_DECISIONS,
    FORMULA_TOLERANCE,
    ORDER_PLAN_COLUMNS,
    assemble_commercial_order_rows,
    quality_scorecard,
    build_review_exceptions,
)


def _test_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1, 2],
            "sku_description": ["A", "B"],
            "current_soh": [2.0, 0.0],
            "on_order_at_advice_time": [0.0, 1.0],
            "floor_units_required": [2.0, 2.0],
            "discount_percent": [20.0, 15.0],
            "raw_model_order_units": [3, 0],
            "model_confidence_percent": [60.0, 30.0],
            "operator_action": ["REVIEW", "DO_NOT_BUY"],
            "review_flag": [0, 1],
            "risk_flag": [0, 0],
            "expected_units_per_day": [0.5, 0.1],
            "expected_units_total_promo": [3.5, 0.7],
            "historical_units_same_discount_avg": [2.0, 0.0],
            "lead_up_demand_units": [56.0, 5.6],
            "days_to_promo_start": [56, 56],
            "promotion_period_days": [7, 7],
            "promotion_start_date": ["2026-07-23", "2026-07-23"],
            "promotion_end_date": ["2026-07-29", "2026-07-29"],
            "capital_at_risk_adjusted_dollars": [10.0, 0.0],
            "feature_expected_gp_on_trust_floor_units": [1.0, 0.0],
            "feature_expected_gp_on_speculative_units": [0.5, 0.0],
        }
    )


def test_assemble_commercial_order_rows_basic_contract() -> None:
    out, _calc = assemble_commercial_order_rows(
        _test_frame(),
        store_number=772,
        promotion_name="SE01 skincare sales event",
        prediction_date="2026-07-22",
    )
    assert set(out.columns).issuperset(set(ORDER_PLAN_COLUMNS) - {"priority_rank"})
    assert out.loc[0, "decision"] == "BUY"
    assert out.loc[0, "recommended_order_units"] > 0
    assert out.loc[1, "recommended_order_units"] == 0
    assert set(out["decision"]).issubset(ALLOWED_DECISIONS)
    assert out.loc[0, "estimated_demand_before_promo_start_units"] <= 2.0
    assert out.loc[0, "predicted_promo_period_sales_units"] == 3.5
    optimal = out.loc[0, "predicted_promo_period_sales_units"] + out.loc[0, "target_stock_on_hand_at_promo_end_units"]
    assert abs(out.loc[0, "optimal_stock_on_hand_day_one_units"] - optimal) <= FORMULA_TOLERANCE


def test_pre_promo_uses_days_until_not_period_total() -> None:
    frame = _test_frame()
    frame.loc[0, "expected_units_before_promo_start"] = 56.0
    out, _ = assemble_commercial_order_rows(
        frame,
        store_number=772,
        promotion_name="SE01 skincare sales event",
        prediction_date="2026-07-22",
    )
    assert out.loc[0, "estimated_demand_before_promo_start_units"] == 1.0


def test_quality_scorecard_flags_zero_buy() -> None:
    plan = pd.DataFrame({
        "sku_number": [1],
        "decision": ["BUY"],
        "recommended_order_units": [0],
        "estimated_demand_before_promo_start_units": [1],
        "predicted_promo_period_sales_units": [2],
        "target_stock_on_hand_at_promo_end_units": [2],
        "optimal_stock_on_hand_day_one_units": [4],
        "days_until_promotion_start": [1],
        "avg_promo_demand_same_discount_units": [2],
        "model_status": ["SHADOW_NOT_PRODUCTION"],
        "confidence_score": [50],
        "data_quality_score": [50],
        "human_review_required": ["YES"],
    })
    summary = pd.DataFrame([{"total_recommended_order_units": 0, "review_exception_count": 0}])
    exceptions = build_review_exceptions(plan)
    scorecard, score = quality_scorecard(plan, summary, exceptions)
    assert int(scorecard.loc[scorecard["metric"] == "buy_positive_units", "score"].iloc[0]) == 0


@pytest.mark.skipif(
    not Path("/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/2026-07-23").exists(),
    reason="runtime SE01 folder not present",
)
def test_build_se01_integration() -> None:
    from surfaces.promotions.reporting.commercial_report_builder import build_se01_commercial_pack

    pred = Path("/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/2026-07-23")
    out = Path("/tmp/se01_commercial_test_pack_5b4")
    art = build_se01_commercial_pack(prediction_dir=pred, output_dir=out, diagnostics_dir=None)
    assert art.row_count == 3531
    assert art.decision_counts.get("BUY", 0) > 0
    assert art.report_quality_score >= 95
