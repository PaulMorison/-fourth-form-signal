from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_conviction_calibration import apply_conviction_calibration  # noqa: E402
from models.promotions.promo_decision_triage import apply_promo_decision_triage  # noqa: E402
from models.promotions.promo_economic_value_scoring import (  # noqa: E402
    apply_economic_review_rerank,
    apply_promo_economic_value_scoring,
    build_promo_economic_value_frame,
    write_phase5n01_diagnostics,
)
from models.promotions.promo_regime_state import apply_regime_brain_decisioning, build_promo_regime_state_frame  # noqa: E402


def _frame(n: int = 10, **overrides: object) -> pd.DataFrame:
    def _rep(values: list[object]) -> list[object]:
        if n <= len(values):
            return values[:n]
        return (values * ((n // len(values)) + 1))[:n]

    base = {
        "store_number": [772] * n,
        "sku_number": [str(i) for i in range(n)],
        "sku_description": [f"SKU{i}" for i in range(n)],
        "department": _rep(["Grocery", "Cosmetics", "Grocery", "Haircare", "Grocery", "Grocery", "Cosmetics", "Grocery", "Grocery", "Grocery"]),
        "category": _rep(["Food", "Colour Cosmetics", "Food", "Shampoo", "Food", "Food", "Skincare", "Food", "Food", "Food"]),
        "promotion_name": ["Summer"] * n,
        "promotion_start_date": ["2024-06-01"] * n,
        "promo_days": [7] * n,
        "discount_percent": [15.0] * n,
        "average_daily_units": _rep([2.0, 0.05, 5.0, 1.0, 0.5, 3.0, 4.0, 1.0, 2.0, 1.5]),
        "actual_units_sold_promo": _rep([10.0, 1.0, 50.0, 8.0, 2.0, 30.0, 40.0, 5.0, 12.0, 6.0]),
        "model_expected_units_total_promo": _rep([12.0, 5.0, 45.0, 6.0, 8.0, 25.0, 35.0, 5.0, 15.0, 7.0]),
        "current_soh": _rep([5.0, 2.0, 10.0, 200.0, 1.0, 15.0, 20.0, 3.0, 8.0, 4.0]),
        "optimal_base_soh_units": _rep([30.0, 2.0, 30.0, 30.0, 2.0, 30.0, 30.0, 30.0, 30.0, 30.0]),
        "expected_promo_uplift_units": _rep([6.0, 0.5, 15.0, 1.0, 1.5, 5.0, 8.0, 1.0, 4.0, 2.0]),
        "expected_normal_units_during_promo": _rep([14.0, 0.35, 35.0, 7.0, 3.5, 21.0, 28.0, 7.0, 14.0, 10.5]),
        "promo_convexity_score": _rep([30.0, 5.0, 65.0, 10.0, 20.0, 40.0, 55.0, 8.0, 25.0, 15.0]),
        "current_stock_position_label": _rep(["UNDERSTOCKED", "OPTIMAL", "UNDERSTOCKED", "SEVERELY_OVERSTOCKED", "OPTIMAL", "UNDERSTOCKED", "UNDERSTOCKED", "OPTIMAL", "UNDERSTOCKED", "OPTIMAL"]),
        "distance_to_optimal_end_soh": _rep([5.0, 1.0, 8.0, 50.0, 2.0, 6.0, 4.0, 2.0, 5.0, 1.0]),
        "optimal_stock_position_order_units": _rep([20.0, 0.0, 15.0, 0.0, 0.0, 10.0, 12.0, 0.0, 8.0, 0.0]),
        "simulated_missed_demand_units": _rep([5.0, 0.0, 8.0, 0.0, 0.0, 2.0, 1.0, 0.0, 3.0, 0.0]),
        "leftover_units_above_optimal": _rep([0.0, 0.0, 0.0, 170.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        "promo_start_soh_source_quality": _rep(["HIGH", "HIGH", "HIGH", "HIGH", "UNKNOWN", "HIGH", "HIGH", "HIGH", "HIGH", "HIGH"]),
        "supplier_number_source_quality": _rep(["HIGH", "HIGH", "HIGH", "UNKNOWN", "UNKNOWN", "HIGH", "HIGH", "HIGH", "HIGH", "HIGH"]),
        "replenishment_risk_class": _rep(["OVERNIGHT_REPLENISHMENT", "OVERNIGHT_REPLENISHMENT", "DIRECT_21_DAY_SUPPLY", "OVERNIGHT_REPLENISHMENT", "OVERNIGHT_REPLENISHMENT", "OVERNIGHT_REPLENISHMENT", "DIRECT_21_DAY_SUPPLY", "OVERNIGHT_REPLENISHMENT", "OVERNIGHT_REPLENISHMENT", "OVERNIGHT_REPLENISHMENT"]),
        "supplier_reorder_flexibility_repaired": ["HIGH"] * n,
        "stockout_suspected_flag": _rep([0, 0, 0, 0, 1, 0, 0, 0, 0, 0]),
        "promo_demand_source_quality": _rep(["HIGH", "HIGH", "HIGH", "HIGH", "UNSAFE", "MEDIUM", "HIGH", "HIGH", "HIGH", "LOW"]),
        "promo_demand_release_ready_flag": _rep(["YES", "YES", "YES", "YES", "NO", "YES", "YES", "NO", "YES", "NO"]),
        "feature_basket_structure_evidence_available_flag": _rep([1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0]),
        "feature_sparse_demand_evidence_available_flag": _rep([0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0]),
        "historical_units_same_discount_avg": _rep([20.0, 0.0, 40.0, 5.0, 0.0, 15.0, 25.0, 0.0, 10.0, 0.0]),
        "promo_start_soh_confidence_score": _rep([80.0, 70.0, 75.0, 75.0, 20.0, 65.0, 70.0, 60.0, 72.0, 55.0]),
        "cash_drag_penalty": _rep([0.0, 0.0, 0.0, 500.0, 0.0, 10.0, 5.0, 0.0, 0.0, 0.0]),
        "missed_demand_penalty": _rep([20.0, 0.0, 32.0, 0.0, 0.0, 8.0, 4.0, 0.0, 12.0, 0.0]),
        "regime_historical_wape": _rep([0.2, 0.5, 0.15, 0.4, 0.6, 0.25, 0.1, 0.3, 0.2, 0.45]),
        "calibrated_regime_conviction_score": _rep([35.0, 15.0, 45.0, 20.0, 10.0, 40.0, 50.0, 25.0, 38.0, 18.0]),
        "calibrated_conviction_label": _rep(["LOW", "VERY_LOW", "MEDIUM", "LOW", "VERY_LOW", "MEDIUM", "MEDIUM", "LOW", "LOW", "VERY_LOW"]),
        "conviction_downgrade_reason": ["high_wape_regime_cap"] * n,
        "buyer_review_required_flag": ["YES"] * n,
        "buyer_review_reason": ["low_calibrated_conviction"] * n,
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _triaged(**overrides: object) -> pd.DataFrame:
    frame = _frame(**overrides)
    regime = build_promo_regime_state_frame(frame)
    brain = apply_regime_brain_decisioning(regime, gate_recommendation="NO_RELEASE")
    calibrated = apply_conviction_calibration(brain, gate_recommendation="NO_RELEASE")
    return apply_promo_decision_triage(calibrated, gate_recommendation="NO_RELEASE")


class PromoEconomicValueScoringTests(unittest.TestCase):
    def test_gp_capture_non_negative(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        self.assertTrue((out["expected_gp_capture_value"] >= 0).all())

    def test_missed_sales_avoidance_non_negative(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        self.assertTrue((out["missed_sales_avoidance_value"] >= 0).all())

    def test_basket_trust_bounded(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        self.assertTrue((out["basket_trust_protection_value"] <= 200).all())

    def test_cash_tied_cost_non_negative(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        self.assertTrue((out["cash_tied_above_optimal_cost"] >= 0).all())

    def test_supplier_risk_non_negative(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        self.assertTrue((out["supplier_risk_cost"] >= 0).all())

    def test_economic_net_value_formula(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        expected = (
            out["expected_gp_capture_value"]
            + out["missed_sales_avoidance_value"]
            + out["basket_trust_protection_value"]
            + out["long_tail_protection_value"]
            + out["basket_trust_convexity_value"]
            + out["overstock_cash_release_value"]
            - out["cash_tied_above_optimal_cost"]
            - out["supplier_risk_cost"]
            - out["review_effort_cost"]
        ).round(3)
        self.assertTrue((out["economic_net_value_score"] - expected).abs().le(0.01).all())

    def test_overstock_units_calculated(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        over = out[out["current_stock_position_label"].eq("SEVERELY_OVERSTOCKED")]
        self.assertTrue((over["overstock_units_above_optimal"] > 0).all())

    def test_overstock_cash_release_positive(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        over = out[out["current_stock_position_label"].eq("SEVERELY_OVERSTOCKED")]
        self.assertTrue((over["overstock_cash_release_value"] > 0).all())

    def test_run_down_positive_economic_value(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        run_down = out[out["decision_triage_class"].str.contains("RUN_DOWN", na=False)]
        if not run_down.empty:
            self.assertTrue((run_down["economic_net_value_score"] >= 0).any())

    def test_overstock_value_not_buy_order(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        over = out[out["current_stock_position_label"].eq("SEVERELY_OVERSTOCKED")]
        self.assertTrue((over["final_governed_order_units"] == 0).all())

    def test_long_lead_underbuy_penalty(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        long_lead = out[out["replenishment_risk_class"].astype(str).str.contains("21", na=False)]
        self.assertTrue((long_lead["long_lead_underbuy_penalty"] >= 0).any())

    def test_overnight_overbuy_penalty(self) -> None:
        tri = _triaged()
        tri.loc[tri.index[0], "brain_order_units_proposal"] = 50.0
        tri.loc[tri.index[0], "replenishment_risk_class"] = "OVERNIGHT_REPLENISHMENT"
        out = build_promo_economic_value_frame(tri)
        self.assertGreater(float(out.loc[tri.index[0], "overnight_overbuy_penalty"]), 0.0)

    def test_unknown_supplier_cost(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        unknown = out[out["supplier_number_source_quality"].eq("UNKNOWN")]
        self.assertTrue((unknown["supplier_economic_risk_cost"] > 0).any())

    def test_review_effort_included(self) -> None:
        out = build_promo_economic_value_frame(_triaged())
        self.assertTrue((out["review_effort_cost"] > 0).any())

    def test_review_roi_ranks_high_value_higher(self) -> None:
        tri = _triaged()
        low = apply_economic_review_rerank(tri)
        high = tri.copy()
        high["expected_promo_uplift_units"] = 50.0
        high["simulated_missed_demand_units"] = 20.0
        high = apply_economic_review_rerank(high)
        self.assertGreater(
            float(high.loc[high["buyer_review_required_flag_triaged"].eq("YES"), "review_roi_score"].max()),
            float(low.loc[low["buyer_review_required_flag_triaged"].eq("YES"), "review_roi_score"].median()),
        )

    def test_economic_priority_rank_exists(self) -> None:
        out = apply_promo_economic_value_scoring(_triaged())
        review = out[out["buyer_review_required_flag_triaged"].eq("YES")]
        self.assertTrue((review["economic_priority_rank"] > 0).any())

    def test_old_priority_preserved(self) -> None:
        tri = _triaged()
        before = tri["buyer_review_priority_score"].copy()
        out = apply_promo_economic_value_scoring(tri)
        self.assertTrue(out["buyer_review_priority_score"].equals(before))

    def test_rank_change_calculated(self) -> None:
        out = apply_promo_economic_value_scoring(_triaged())
        self.assertIn("priority_rank_change", out.columns)
        self.assertIn("priority_rank_change_reason", out.columns)

    def test_unsafe_remain_blocked(self) -> None:
        out = apply_promo_economic_value_scoring(_triaged())
        unsafe = out[out["promo_demand_source_quality"].eq("UNSAFE")]
        self.assertTrue((unsafe["auto_block_flag"] == "YES").all())

    def test_diagnostics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5n01_diagnostics(frame=_triaged(), diagnostics_dir=diag)
            for name in (
                "phase5n01_economic_value_distribution.csv",
                "phase5n01_review_queue_roi.csv",
                "phase5n01_rank_change_review.csv",
                "phase5n01_economic_value_by_triage_class.csv",
                "phase5n01_workload_value_summary.csv",
                "phase5n01_release_gate.csv",
            ):
                self.assertTrue((diag / name).exists(), msg=name)
            self.assertIn("top_50_value_after", result)

    def test_no_nan_numeric_outputs(self) -> None:
        out = apply_promo_economic_value_scoring(_triaged())
        numeric = out.select_dtypes(include=[np.number])
        self.assertFalse(numeric.isna().any().any())


if __name__ == "__main__":
    unittest.main()
