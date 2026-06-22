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
    workflow_cols = {
        "action_tier", "execution_ready_flag", "execution_blocker", "review_subtype",
        "review_burden_class", "commercial_action_value_score", "review_priority_score",
        "no_buy_trust_score", "overall_row_priority_score",
        "commercial_value_score", "commercial_value_label", "operator_priority_group",
    }
    assert set(out.columns).issuperset(set(ORDER_PLAN_COLUMNS) - {"priority_rank"} - workflow_cols)
    assert set(out["decision"]).issubset(ALLOWED_DECISIONS)
    assert "full_target_order_units" in out.columns
    assert "commercial_recommended_order_units" in out.columns
    assert "order_needed_to_cover_promo_sales" in out.columns
    assert out.loc[0, "recommended_order_units"] == out.loc[0, "commercial_recommended_order_units"]
    assert out["decision_quality_label"].ne("N_A").all()
    assert out.loc[0, "projected_day_one_soh_after_recommended_order_units"] == pytest.approx(
        out.loc[0, "projected_day_one_soh_before_order_units"] + out.loc[0, "recommended_order_units"],
        abs=FORMULA_TOLERANCE,
    )


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
        "remaining_day_one_shortfall_units": [0],
        "remaining_promo_sales_stock_gap": [0],
        "remaining_end_stock_gap": [0],
        "order_strategy": ["FULL_TARGET_ORDER"],
        "full_target_order_units": [0],
        "order_needed_to_cover_promo_sales": [0],
        "order_needed_to_reach_full_stock_target": [0],
        "recommended_promo_cover_order_units": [0],
        "recommended_base_stock_order_units": [0],
        "promo_units_expected_to_sell": [2],
        "stock_needed_to_finish_with_target_cover": [2],
        "commercial_recommended_order_units": [0],
        "commercial_coverage_ratio": [0],
        "target_order_units_to_hit_day_one_soh": [0],
        "estimated_demand_before_promo_start_units": [1],
        "predicted_promo_period_sales_units": [2],
        "target_day_one_soh_units": [4],
        "target_stock_on_hand_at_promo_end_units": [2],
        "projected_day_one_soh_before_order_units": [0],
        "projected_day_one_soh_after_recommended_order_units": [0],
        "current_soh_units": [1],
        "on_order_units": [0],
        "days_until_promotion_start": [1],
        "avg_promo_demand_same_discount_units": [2],
        "recommendation_coverage_ratio": [0],
        "model_status": ["SHADOW_NOT_PRODUCTION"],
        "confidence_score": [50],
        "data_quality_score": [50],
        "human_review_required": ["YES"],
        "decision_quality_label": ["REVIEW_LOW_CONFIDENCE"],
    })
    summary = pd.DataFrame([{"total_recommended_order_units": 0, "review_exception_count": 0}])
    exceptions = build_review_exceptions(plan)
    scorecard, structural_score, commercial_score, primary_blocker = quality_scorecard(plan, summary, exceptions)
    assert int(scorecard.loc[scorecard["metric"] == "buy_positive_units", "score"].iloc[0]) == 0


@pytest.mark.skipif(
    not Path("/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/2026-07-23").exists(),
    reason="runtime SE01 folder not present",
)
def test_build_se01_integration() -> None:
    from surfaces.promotions.reporting.commercial_report_builder import build_se01_commercial_pack

    pred = Path("/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/2026-07-23")
    out = Path("/tmp/se01_commercial_test_pack_5b8")
    art = build_se01_commercial_pack(prediction_dir=pred, output_dir=out, diagnostics_dir=None)
    assert art.row_count == 3531
    assert art.decision_counts.get("BUY", 0) >= 0
