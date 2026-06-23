from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_optimal_stock_learning import (  # noqa: E402
    COSMETICS_LEAD_DAYS,
    DAILY_SUPPLIER_NUMBER,
    MIN_OPEN_FOR_SALE,
    OPTIMAL_DAYS_COVER,
    apply_optimal_stock_learning,
    assign_replenishment_model,
    compute_day_one_and_exit_targets,
    compute_optimal_base_stock,
    compute_optimal_stock_position_order,
    compute_pre_promo_bridge,
    compute_promo_uplift,
    evaluate_optimal_stock_release_gate,
    simulate_stock_position_outcomes,
)


def _frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": [772, 772, 772, 772],
        "sku_number": ["1", "2", "3", "4"],
        "promotion_start_date": ["2024-06-01"] * 4,
        "promo_days": [7, 7, 7, 7],
        "days_to_promo_start": [14, 14, 14, 14],
        "baseline_expected_units_total_promo": [7.0, 70.0, 210.0, 7.0],
        "model_expected_units_total_promo": [10.0, 100.0, 350.0, 5.0],
        "actual_units_sold_promo": [8.0, 90.0, 300.0, 2.0],
        "current_soh": [1.0, 50.0, 1200.0, 2.0],
        "department": ["Grocery", "Cosmetics", "Haircare", "Grocery"],
        "category": ["Food", "Colour Cosmetics", "Shampoo", "Food"],
        "supplier_number_resolved": [1001, 1001, DAILY_SUPPLIER_NUMBER, 0],
        "supplier_number_source_quality": ["HIGH", "HIGH", "HIGH", "UNKNOWN"],
        "promo_start_soh_source_quality": ["HIGH", "HIGH", "HIGH", "UNKNOWN"],
        "reliable_inbound_units_before_or_during_promo": [0.0, 5.0, 0.0, 0.0],
        "promo_demand_source_quality": ["HIGH", "HIGH", "HIGH", "MEDIUM"],
        "promo_demand_release_ready_flag": ["YES"] * 4,
    }
    base.update(overrides)
    return pd.DataFrame(base)


class PromoOptimalStockLearningTests(unittest.TestCase):
    def test_optimal_base_soh_rule(self) -> None:
        out = compute_optimal_base_stock(_frame(baseline_expected_units_total_promo=[7.0, 70.0, 210.0, 0.35]))
        self.assertAlmostEqual(float(out.loc[0, "optimal_base_soh_units"]), max(1.0 * OPTIMAL_DAYS_COVER, MIN_OPEN_FOR_SALE), places=3)
        self.assertAlmostEqual(float(out.loc[3, "optimal_base_soh_units"]), MIN_OPEN_FOR_SALE, places=3)

    def test_low_volume_minimum_open_for_sale(self) -> None:
        out = compute_optimal_base_stock(_frame(baseline_expected_units_total_promo=[0.7, 0.7, 0.7, 0.7]))
        self.assertTrue((out["optimal_base_soh_units"] >= MIN_OPEN_FOR_SALE).all())

    def test_minimum_not_treated_as_forecast(self) -> None:
        out = compute_promo_uplift(compute_optimal_base_stock(_frame(baseline_expected_units_total_promo=[0.7] * 4)))
        self.assertTrue((out["expected_normal_units_during_promo"] <= 1.0).all())

    def test_stock_position_labels(self) -> None:
        out = compute_optimal_base_stock(_frame())
        self.assertEqual(out.loc[0, "current_stock_position_label"], "UNDERSTOCKED")
        self.assertIn(out.loc[2, "current_stock_position_label"], {"OVERSTOCKED", "SEVERELY_OVERSTOCKED"})

    def test_pre_promo_bridge_demand(self) -> None:
        out = compute_pre_promo_bridge(compute_optimal_base_stock(_frame()))
        row = out.iloc[0]
        expected = float(row["average_daily_units"] * row["days_until_promo_start"])
        self.assertAlmostEqual(float(row["expected_units_until_promo_start"]), expected, places=3)

    def test_expected_soh_at_promo_start(self) -> None:
        out = compute_pre_promo_bridge(compute_optimal_base_stock(_frame()))
        row = out.iloc[1]
        expected = max(0.0, row["current_soh"] + row["reliable_inbound_units_before_or_during_promo"] - row["expected_units_until_promo_start"])
        self.assertAlmostEqual(float(row["expected_soh_at_promo_start_before_order"]), expected, places=3)

    def test_unknown_soh_lowers_bridge_quality(self) -> None:
        out = compute_pre_promo_bridge(compute_optimal_base_stock(_frame()))
        self.assertEqual(out.loc[3, "pre_promo_bridge_quality"], "UNKNOWN")

    def test_uplift_separation(self) -> None:
        out = compute_promo_uplift(compute_optimal_base_stock(_frame()))
        row = out.iloc[1]
        self.assertAlmostEqual(
            float(row["expected_promo_uplift_units"]),
            max(0.0, row["model_expected_units_total_promo"] - row["expected_normal_units_during_promo"]),
            places=3,
        )

    def test_uplift_non_negative(self) -> None:
        out = compute_promo_uplift(compute_optimal_base_stock(_frame(model_expected_units_total_promo=[1.0, 1.0, 1.0, 1.0])))
        self.assertTrue((out["expected_promo_uplift_units"] >= 0).all())

    def test_convexity_bounded(self) -> None:
        out = compute_promo_uplift(compute_optimal_base_stock(_frame()))
        self.assertTrue(out["promo_convexity_score"].between(0, 100).all())

    def test_actual_uplift_in_backtest(self) -> None:
        out = simulate_stock_position_outcomes(_frame())
        row = out.iloc[1]
        self.assertAlmostEqual(
            float(row["actual_promo_uplift_units"]),
            max(0.0, row["actual_units_sold_promo"] - row["expected_normal_units_during_promo"]),
            places=3,
        )

    def test_day_one_includes_base_plus_uplift(self) -> None:
        out = compute_day_one_and_exit_targets(compute_promo_uplift(compute_pre_promo_bridge(compute_optimal_base_stock(_frame()))))
        row = out.iloc[0]
        self.assertAlmostEqual(float(row["target_day_one_promo_soh"]), float(row["optimal_base_soh_units"] + row["expected_promo_uplift_units"]), places=3)

    def test_overstocked_skus_not_ordered_unnecessarily(self) -> None:
        out = compute_optimal_stock_position_order(
            compute_day_one_and_exit_targets(
                compute_promo_uplift(compute_pre_promo_bridge(compute_optimal_base_stock(_frame())))
            )
        )
        over = out[out["current_stock_position_label"].isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])]
        self.assertTrue((over["optimal_stock_position_order_units"] == 0).all())

    def test_target_end_equals_optimal_base(self) -> None:
        out = compute_day_one_and_exit_targets(compute_optimal_base_stock(_frame()))
        pd.testing.assert_series_equal(out["target_end_promo_soh"], out["optimal_base_soh_units"], check_names=False)

    def test_distance_to_optimal_end_soh(self) -> None:
        out = simulate_stock_position_outcomes(_frame())
        row = out.iloc[0]
        self.assertAlmostEqual(
            float(row["distance_to_optimal_end_soh"]),
            abs(float(row["simulated_end_soh"]) - float(row["target_end_promo_soh"])),
            places=3,
        )

    def test_cosmetics_longer_lead_time(self) -> None:
        out = assign_replenishment_model(_frame())
        cos = out[out["department"].eq("Cosmetics")].iloc[0]
        self.assertEqual(int(cos["replenishment_lead_time_days"]), COSMETICS_LEAD_DAYS)

    def test_supplier_99999_daily(self) -> None:
        out = assign_replenishment_model(_frame())
        daily = out[out["supplier_number_resolved"].eq(DAILY_SUPPLIER_NUMBER)].iloc[0]
        self.assertEqual(int(daily["replenishment_lead_time_days"]), 1)
        self.assertEqual(daily["replenishment_reliability"], "HIGH")

    def test_non_cosmetics_overnight(self) -> None:
        out = assign_replenishment_model(_frame())
        row = out[out["department"].eq("Grocery") & out["supplier_number_resolved"].ne(DAILY_SUPPLIER_NUMBER)].iloc[0]
        self.assertEqual(int(row["replenishment_lead_time_days"]), 1)

    def test_unknown_supplier_conservative(self) -> None:
        out = assign_replenishment_model(_frame())
        row = out[out["supplier_number_source_quality"].eq("UNKNOWN")].iloc[0]
        self.assertEqual(row["replenishment_reliability"], "UNKNOWN")

    def test_release_gate_blocks_worse_distance(self) -> None:
        before = pd.DataFrame([{"average_distance_to_optimal_after": 10.0, "missed_demand_risk_units": 100.0, "cash_tied_above_optimal": 100.0, "net_value_proxy": 1000.0}])
        after = pd.DataFrame([{"average_distance_to_optimal_after": 12.0, "missed_demand_risk_units": 80.0, "cash_tied_above_optimal": 90.0, "net_value_proxy": 900.0, "promo_exit_success_rate": 5.0}])
        rec, blocker, _ = evaluate_optimal_stock_release_gate(before, after, _frame(), model_bias_pct=-5.0)
        self.assertEqual(rec, "NO_RELEASE")
        self.assertEqual(blocker, "distance_to_optimal_not_improved")

    def test_release_gate_blocks_cash_explosion(self) -> None:
        before = pd.DataFrame([{"average_distance_to_optimal_after": 20.0, "missed_demand_risk_units": 100.0, "cash_tied_above_optimal": 100.0, "net_value_proxy": 1000.0}])
        after = pd.DataFrame([{"average_distance_to_optimal_after": 10.0, "missed_demand_risk_units": 50.0, "cash_tied_above_optimal": 200.0, "net_value_proxy": 900.0, "promo_exit_success_rate": 8.0}])
        rec, blocker, _ = evaluate_optimal_stock_release_gate(before, after, _frame(), model_bias_pct=-5.0)
        self.assertEqual(rec, "NO_RELEASE")
        self.assertEqual(blocker, "cash_tied_above_optimal_explosion")

    def test_limited_release_when_improves(self) -> None:
        before = pd.DataFrame([{"average_distance_to_optimal_after": 20.0, "missed_demand_risk_units": 200.0, "cash_tied_above_optimal": 100.0, "net_value_proxy": 1000.0}])
        after = pd.DataFrame([{"average_distance_to_optimal_after": 10.0, "missed_demand_risk_units": 100.0, "cash_tied_above_optimal": 90.0, "net_value_proxy": 1200.0, "promo_exit_success_rate": 10.0}])
        frame = apply_optimal_stock_learning(_frame())
        frame["stock_position_release_ready_flag"] = "YES"
        rec, blocker, _ = evaluate_optimal_stock_release_gate(before, after, frame, model_bias_pct=-5.0)
        self.assertEqual(rec, "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")


if __name__ == "__main__":
    unittest.main()
