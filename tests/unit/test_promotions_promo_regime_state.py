from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_regime_state import (  # noqa: E402
    apply_brain_constraint_interpretation,
    apply_regime_brain_decisioning,
    build_promo_regime_state_frame,
    compute_regime_decision_targets,
    write_phase5k01_diagnostics,
)
from surfaces.promotions.reporting.commercial_report_builder import ORDER_PLAN_COLUMNS  # noqa: E402


def _frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": [772] * 6,
        "sku_number": ["1", "2", "3", "4", "5", "6"],
        "sku_description": ["A", "B", "C", "D", "E", "F"],
        "department": ["Grocery", "Grocery", "Haircare", "Cosmetics", "Grocery", "Grocery"],
        "promotion_name": ["Summer"] * 6,
        "promotion_start_date": ["2024-06-01"] * 6,
        "promo_days": [7] * 6,
        "discount_percent": [10.0, 15.0, 35.0, 20.0, 5.0, 10.0],
        "average_daily_units": [0.05, 2.0, 5.0, 1.0, 0.5, 1.0],
        "baseline_expected_units_total_promo": [0.35, 14.0, 35.0, 7.0, 3.5, 7.0],
        "model_expected_units_total_promo": [1.0, 20.0, 50.0, 15.0, 5.0, 8.0],
        "actual_units_sold_promo": [0.0, 18.0, 45.0, 12.0, 2.0, 6.0],
        "current_soh": [2.0, 10.0, 200.0, 5.0, 1.0, 3.0],
        "optimal_base_soh_units": [2.0, 30.0, 30.0, 30.0, 2.0, 30.0],
        "expected_promo_uplift_units": [0.5, 6.0, 15.0, 8.0, 1.5, 1.0],
        "expected_normal_units_during_promo": [0.35, 14.0, 35.0, 7.0, 3.5, 7.0],
        "promo_convexity_score": [5.0, 25.0, 65.0, 40.0, 10.0, 20.0],
        "current_stock_position_label": ["OPTIMAL", "UNDERSTOCKED", "SEVERELY_OVERSTOCKED", "UNDERSTOCKED", "OPTIMAL", "UNDERSTOCKED"],
        "distance_to_optimal_end_soh": [1.0, 8.0, 50.0, 5.0, 2.0, 4.0],
        "optimal_stock_position_order_units": [0.0, 20.0, 0.0, 12.0, 0.0, 8.0],
        "simulated_missed_demand_units": [0.0, 5.0, 0.0, 2.0, 0.0, 1.0],
        "leftover_units_above_optimal": [0.0, 0.0, 170.0, 0.0, 0.0, 0.0],
        "promo_start_soh_source_quality": ["HIGH", "HIGH", "HIGH", "UNKNOWN", "HIGH", "HIGH"],
        "supplier_number_source_quality": ["HIGH", "HIGH", "HIGH", "UNKNOWN", "HIGH", "HIGH"],
        "replenishment_risk_class": ["OVERNIGHT_REPLENISHMENT", "OVERNIGHT_REPLENISHMENT", "DAILY_REPLENISHMENT", "UNKNOWN", "OVERNIGHT_REPLENISHMENT", "OVERNIGHT_REPLENISHMENT"],
        "supplier_reorder_flexibility_repaired": ["HIGH", "HIGH", "LOW", "LOW", "HIGH", "HIGH"],
        "stockout_suspected_flag": [0, 0, 0, 1, 0, 0],
        "promo_demand_source_quality": ["HIGH", "HIGH", "HIGH", "MEDIUM", "UNSAFE", "HIGH"],
        "promo_demand_release_ready_flag": ["YES", "YES", "YES", "YES", "NO", "YES"],
        "feature_basket_structure_evidence_available_flag": [0.0, 1.0, 1.0, 0.0, 0.0, 1.0],
        "feature_sparse_demand_evidence_available_flag": [1.0, 0.0, 0.0, 1.0, 1.0, 0.0],
        "historical_units_same_discount_avg": [0.0, 20.0, 40.0, 5.0, 0.0, 10.0],
        "promo_start_soh_confidence_score": [80.0, 70.0, 75.0, 20.0, 60.0, 65.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


class PromoRegimeStateTests(unittest.TestCase):
    def test_high_traffic_regime_classification(self) -> None:
        out = build_promo_regime_state_frame(_frame(average_daily_units=[0.05, 0.1, 8.0, 1.0, 0.5, 1.0]))
        self.assertEqual(out.loc[2, "store_traffic_regime"], "HIGH_TRAFFIC")

    def test_intermittent_low_volume_demand(self) -> None:
        out = build_promo_regime_state_frame(_frame())
        self.assertEqual(out.loc[0, "sku_demand_regime"], "INTERMITTENT_LOW_VOLUME")

    def test_overstock_cash_release_opportunity(self) -> None:
        out = build_promo_regime_state_frame(_frame())
        self.assertEqual(out.loc[2, "capital_at_risk_regime"], "CASH_RELEASE_PRIORITY")

    def test_unknown_supplier_increases_risk(self) -> None:
        out = build_promo_regime_state_frame(_frame())
        self.assertEqual(out.loc[3, "supplier_risk_regime"], "UNKNOWN_SUPPLIER")
        self.assertGreater(float(out.loc[3, "overall_regime_risk_score"]), float(out.loc[1, "overall_regime_risk_score"]))

    def test_deep_discount_increases_convexity_opportunity(self) -> None:
        shallow = build_promo_regime_state_frame(_frame(discount_percent=[5.0] * 6, promo_convexity_score=[10.0] * 6))
        deep = build_promo_regime_state_frame(_frame(discount_percent=[35.0] * 6, promo_convexity_score=[65.0] * 6))
        self.assertEqual(deep.iloc[0]["promo_discount_regime"], "DEEP_DISCOUNT")
        self.assertGreater(float(deep["overall_regime_opportunity_score"].mean()), float(shallow["overall_regime_opportunity_score"].mean()))

    def test_censored_demand_increases_risk(self) -> None:
        out = build_promo_regime_state_frame(_frame())
        self.assertEqual(out.loc[3, "stock_constraint_regime"], "CENSORED_DEMAND_RISK")

    def test_all_regime_scores_bounded(self) -> None:
        out = build_promo_regime_state_frame(_frame())
        score_cols = [c for c in out.columns if c.endswith("_score")]
        for col in score_cols:
            self.assertTrue(out[col].between(0, 100).all(), msg=col)

    def test_opportunity_score_increases_with_convexity(self) -> None:
        low = build_promo_regime_state_frame(_frame(promo_convexity_score=[5.0] * 6))
        high = build_promo_regime_state_frame(_frame(promo_convexity_score=[80.0] * 6))
        self.assertGreater(float(high["overall_regime_opportunity_score"].mean()), float(low["overall_regime_opportunity_score"].mean()))

    def test_risk_score_increases_with_unknown_stock_supplier(self) -> None:
        out = build_promo_regime_state_frame(_frame())
        self.assertGreater(float(out.loc[3, "overall_regime_risk_score"]), float(out.loc[1, "overall_regime_risk_score"]))

    def test_conviction_falls_with_poor_evidence(self) -> None:
        out = build_promo_regime_state_frame(_frame())
        self.assertLess(float(out.loc[3, "overall_regime_conviction_score"]), float(out.loc[1, "overall_regime_conviction_score"]))

    def test_missed_demand_penalty_non_negative(self) -> None:
        out = compute_regime_decision_targets(build_promo_regime_state_frame(_frame()))
        self.assertTrue((out["missed_demand_penalty"] >= 0).all())

    def test_cash_drag_penalty_non_negative(self) -> None:
        out = compute_regime_decision_targets(build_promo_regime_state_frame(_frame()))
        self.assertTrue((out["cash_drag_penalty"] >= 0).all())

    def test_overstock_run_down_reward_positive(self) -> None:
        out = compute_regime_decision_targets(build_promo_regime_state_frame(_frame()))
        self.assertGreater(float(out.loc[2, "overstock_run_down_reward"]), 0.0)

    def test_decision_value_changes_with_regime(self) -> None:
        low = compute_regime_decision_targets(build_promo_regime_state_frame(_frame(promo_convexity_score=[5.0] * 6)))
        high = compute_regime_decision_targets(build_promo_regime_state_frame(_frame(promo_convexity_score=[80.0] * 6)))
        self.assertNotAlmostEqual(float(low["regime_adjusted_decision_value"].mean()), float(high["regime_adjusted_decision_value"].mean()), places=3)

    def test_brain_proposal_preserved_when_blocked(self) -> None:
        out = apply_brain_constraint_interpretation(build_promo_regime_state_frame(_frame()), gate_recommendation="NO_RELEASE")
        blocked = out[out["constraint_block_flag"] == "YES"]
        self.assertTrue((blocked["brain_order_units_proposal"] >= 0).all())
        self.assertTrue((blocked["final_governed_order_units"] <= blocked["brain_order_units_proposal"]).all())

    def test_constraint_layer_can_reduce_final_order(self) -> None:
        out = apply_brain_constraint_interpretation(
            build_promo_regime_state_frame(_frame(optimal_stock_position_order_units=[100.0] * 6)),
            gate_recommendation="NO_RELEASE",
        )
        self.assertTrue((out["final_governed_order_units"] < out["brain_order_units_proposal"]).any())

    def test_interpretation_does_not_change_final_order(self) -> None:
        before = apply_brain_constraint_interpretation(build_promo_regime_state_frame(_frame()))
        after = before.copy()
        after["human_interpretation_summary"] = "manual edit only"
        self.assertTrue(before["final_governed_order_units"].equals(after["final_governed_order_units"]))

    def test_final_governed_action_traceable(self) -> None:
        out = apply_brain_constraint_interpretation(build_promo_regime_state_frame(_frame()))
        blocked = out[out["constraint_block_flag"] == "YES"]
        self.assertTrue(blocked["constraint_block_reason"].astype(str).str.len().gt(0).all())
        self.assertTrue(blocked["brain_action_label"].notna().all())

    def test_diagnostics_files_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase5k01_diagnostics(frame=_frame(), diagnostics_dir=diag)
            for name in (
                "phase5k01_regime_distribution.csv",
                "phase5k01_regime_score_summary.csv",
                "phase5k01_action_value_summary.csv",
                "phase5k01_brain_vs_governed_actions.csv",
                "phase5k01_release_gate.csv",
            ):
                self.assertTrue((diag / name).exists(), msg=name)
            self.assertIn("customer_release_recommendation", result)

    def test_no_nan_numeric_outputs(self) -> None:
        out = apply_regime_brain_decisioning(_frame())
        numeric = out.select_dtypes(include=[np.number])
        self.assertFalse(numeric.isna().any().any())

    def test_order_plan_fields_exist(self) -> None:
        required = {
            "store_sales_regime", "customer_loyalty_regime", "sku_demand_regime",
            "stock_position_regime", "supplier_replenishment_regime", "promo_convexity_regime",
            "cash_efficiency_regime", "overall_regime_opportunity_score", "overall_regime_risk_score",
            "overall_regime_conviction_score", "regime_adjusted_decision_value", "brain_action_label",
            "brain_order_units_proposal", "constraint_block_flag", "constraint_block_reason",
            "final_governed_action_label", "final_governed_order_units", "top_regime_driver_1",
            "top_regime_driver_2", "top_regime_driver_3", "human_interpretation_summary",
        }
        missing = required - set(ORDER_PLAN_COLUMNS)
        self.assertEqual(missing, set())


if __name__ == "__main__":
    unittest.main()
