"""Tests for commercial report builder."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from surfaces.promotions.reporting.commercial_report_builder import (
    ALLOWED_DECISIONS,
    ORDER_PLAN_COLUMNS,
    assemble_commercial_order_rows,
    quality_scorecard,
)


def test_assemble_commercial_order_rows_basic_contract() -> None:
    frame = pd.DataFrame(
        {
            "sku_number": [1, 2],
            "sku_description": ["A", "B"],
            "current_soh": [2.0, 0.0],
            "on_order_at_advice_time": [0.0, 1.0],
            "expected_units_before_promo_start": [1.0, 0.5],
            "target_SOH_at_promo_start": [5.0, 3.0],
            "floor_units_required": [2.0, 2.0],
            "discount_percent": [20.0, 15.0],
            "raw_model_order_units": [3, 0],
            "model_confidence_percent": [60.0, 30.0],
            "operator_action": ["REVIEW", "DO_NOT_BUY"],
            "review_flag": [0, 1],
            "risk_flag": [0, 0],
            "expected_units_per_day": [0.5, 0.1],
            "historical_units_same_discount_avg": [2.0, 0.0],
            "promotion_period_days": [7, 7],
            "promotion_start_date": ["2026-07-23", "2026-07-23"],
            "promotion_end_date": ["2026-07-29", "2026-07-29"],
            "capital_at_risk_adjusted_dollars": [10.0, 0.0],
            "feature_expected_gp_on_trust_floor_units": [1.0, 0.0],
            "feature_expected_gp_on_speculative_units": [0.5, 0.0],
        }
    )
    out = assemble_commercial_order_rows(
        frame,
        store_number=772,
        promotion_name="SE01 skincare sales event",
        prediction_date="2026-07-22",
    )
    assert set(out.columns).issuperset(set(ORDER_PLAN_COLUMNS) - {"priority_rank"})
    assert out.loc[0, "decision"] == "BUY"
    assert out.loc[0, "recommended_order_units"] > 0
    assert out.loc[1, "recommended_order_units"] == 0
    assert set(out["decision"]).issubset(ALLOWED_DECISIONS)


def test_quality_scorecard_flags_zero_buy() -> None:
    plan = pd.DataFrame({
        "sku_number": [1],
        "decision": ["BUY"],
        "recommended_order_units": [0],
        "estimated_demand_before_promo_start_units": [1],
        "predicted_promo_period_sales_units": [2],
        "model_status": ["SHADOW_NOT_PRODUCTION"],
        "confidence_score": [50],
        "data_quality_score": [50],
        "human_review_required": ["YES"],
    })
    summary = pd.DataFrame([{"total_recommended_order_units": 0}])
    scorecard, score = quality_scorecard(plan, summary)
    assert int(scorecard.loc[scorecard["metric"] == "buy_positive_units", "score"].iloc[0]) == 0


@pytest.mark.skipif(
    not Path("/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/2026-07-23").exists(),
    reason="runtime SE01 folder not present",
)
def test_build_se01_integration() -> None:
    from surfaces.promotions.reporting.commercial_report_builder import build_se01_commercial_pack

    pred = Path("/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/2026-07-23")
    out = Path("/tmp/se01_commercial_test_pack")
    art = build_se01_commercial_pack(prediction_dir=pred, output_dir=out, diagnostics_dir=None)
    assert art.row_count == 3531
    assert art.decision_counts.get("BUY", 0) > 0
    assert art.total_recommended_order_units > 0
