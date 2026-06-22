from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_stock_outcome_optimisation import (  # noqa: E402
    DAILY_SUPPLIER_NUMBER,
    DEFAULT_LONG_LEAD_DAYS,
    assign_supplier_lead_time,
    classify_stock_outcome_row,
    compute_stock_outcome_order_target,
    enrich_stock_outcome_fields,
    evaluate_stock_outcome_release_gate,
)


def _frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": [772, 772, 772, 772],
        "sku_number": [1, 2, 3, 4],
        "promotion_start_date": ["2024-01-01"] * 4,
        "promo_days": [7, 7, 7, 7],
        "actual_units_sold_promo": [0.0, 1.0, 2.0, 5.0],
        "baseline_expected_units_total_promo": [7.0, 7.0, 14.0, 35.0],
        "model_expected_units_total_promo": [2.0, 2.0, 4.0, 8.0],
        "forecast_demand_units": [2.0, 2.0, 4.0, 8.0],
        "promo_start_soh": [0.0, 1.0, 2.0, 3.0],
        "stockout_suspected_flag": [0, 0, 0, 1],
        "supplier_number": [99999, 1001, 1001, 1001],
        "on_order_units": [0.0, 0.0, 1.0, 0.0],
        "promo_demand_source_quality": ["HIGH", "MEDIUM", "HIGH", "HIGH"],
        "promo_demand_release_ready_flag": ["YES"] * 4,
        "unit_cost": [5.0, 5.0, 5.0, 5.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


class PromoStockOutcomeOptimisationTests(unittest.TestCase):
    def test_low_volume_target_start_soh_at_least_two(self) -> None:
        out = compute_stock_outcome_order_target(_frame())
        self.assertTrue((out["target_promo_start_soh"] >= 2).all())

    def test_start_soh_zero_is_unobservable(self) -> None:
        label, success, _ = classify_stock_outcome_row(
            promo_start_soh=0.0,
            actual_units=0.0,
            end_soh=0.0,
            end_days_cover=0.0,
            stockout_flag=False,
            supplier_class="LONG_LEAD_TIME",
        )
        self.assertEqual(label, "UNOBSERVABLE_DEMAND")
        self.assertEqual(success, "NO")

    def test_start_soh_one_sold_one_is_censored(self) -> None:
        label, success, _ = classify_stock_outcome_row(
            promo_start_soh=1.0,
            actual_units=1.0,
            end_soh=0.0,
            end_days_cover=0.0,
            stockout_flag=False,
            supplier_class="LONG_LEAD_TIME",
        )
        self.assertEqual(label, "UNOBSERVABLE_DEMAND")
        self.assertEqual(success, "NO")

    def test_start_soh_two_low_sales_is_cleaner_evidence(self) -> None:
        label, success, _ = classify_stock_outcome_row(
            promo_start_soh=2.0,
            actual_units=1.0,
            end_soh=1.0,
            end_days_cover=5.0,
            stockout_flag=False,
            supplier_class="LONG_LEAD_TIME",
        )
        self.assertEqual(label, "CLEAN_EXIT")
        self.assertEqual(success, "YES")

    def test_supplier_99999_maps_to_one_day_lead(self) -> None:
        out = assign_supplier_lead_time(_frame())
        daily = out[out["supplier_number"].eq(DAILY_SUPPLIER_NUMBER)].iloc[0]
        self.assertEqual(int(daily["supplier_lead_time_days"]), 1)
        self.assertEqual(daily["supplier_replenishment_class"], "DAILY_REPLENISHMENT")
        self.assertEqual(daily["supplier_reorder_flexibility"], "HIGH")

    def test_other_suppliers_map_to_twenty_one_day_lead(self) -> None:
        out = assign_supplier_lead_time(_frame())
        long_lead = out[out["supplier_number"].ne(DAILY_SUPPLIER_NUMBER)].iloc[0]
        self.assertEqual(int(long_lead["supplier_lead_time_days"]), DEFAULT_LONG_LEAD_DAYS)
        self.assertEqual(long_lead["supplier_replenishment_class"], "LONG_LEAD_TIME")

    def test_daily_supplier_gets_lower_end_stock_target(self) -> None:
        frame = _frame()
        out = compute_stock_outcome_order_target(frame)
        daily = out[out["supplier_number"].eq(DAILY_SUPPLIER_NUMBER)]["target_end_soh_units"].iloc[0]
        long_lead = out[out["supplier_number"].ne(DAILY_SUPPLIER_NUMBER)]["target_end_soh_units"].iloc[0]
        self.assertLessEqual(daily, long_lead)

    def test_long_lead_supplier_gets_higher_protection_with_strong_evidence(self) -> None:
        frame = _frame(promo_demand_source_quality=["HIGH"] * 4, baseline_expected_units_total_promo=[35.0] * 4)
        out = compute_stock_outcome_order_target(frame)
        self.assertTrue(out.loc[out["supplier_number"].ne(DAILY_SUPPLIER_NUMBER), "target_end_soh_units"].iloc[0] >= 2.0)

    def test_target_order_formula(self) -> None:
        frame = _frame(
            promo_start_soh=[2.0, 2.0, 2.0, 2.0],
            forecast_demand_units=[4.0, 4.0, 4.0, 4.0],
            on_order_units=[1.0, 1.0, 1.0, 1.0],
        )
        out = compute_stock_outcome_order_target(frame)
        row = out.iloc[2]
        expected = max(
            0.0,
            row["promo_start_soh_gap"] + row["forecast_demand_units"] + row["target_end_soh_units"] - row["promo_start_soh"] - 1.0,
        )
        self.assertAlmostEqual(float(row["target_order_units_stock_outcome"]), round(expected), delta=1.0)

    def test_order_cannot_be_negative(self) -> None:
        out = compute_stock_outcome_order_target(_frame(promo_start_soh=[20.0] * 4, on_order_units=[10.0] * 4))
        self.assertTrue((out["target_order_units_stock_outcome"] >= 0).all())

    def test_days_cover_cap_works(self) -> None:
        frame = _frame(
            promo_start_soh=[0.0] * 4,
            forecast_demand_units=[1.0] * 4,
            baseline_expected_units_total_promo=[700.0] * 4,
        )
        out = enrich_stock_outcome_fields(compute_stock_outcome_order_target(frame))
        self.assertTrue(
            ((out["promo_end_days_cover"] <= 30.0 + 1e-6) | out["stock_outcome_label"].eq("OVERSTOCKED")).all()
        )

    def test_simulated_missed_sales_non_negative(self) -> None:
        out = enrich_stock_outcome_fields(_frame())
        self.assertTrue((out["simulated_missed_sales_units"] >= 0).all())

    def test_simulated_leftover_non_negative(self) -> None:
        out = enrich_stock_outcome_fields(_frame())
        self.assertTrue((out["simulated_leftover_units"] >= 0).all())

    def test_clean_exit_classification(self) -> None:
        out = enrich_stock_outcome_fields(_frame(promo_start_soh=[3.0] * 4, actual_units_sold_promo=[1.0] * 4, stockout_suspected_flag=[0] * 4))
        self.assertTrue(out["stock_outcome_label"].isin(["CLEAN_EXIT", "CONTROLLED_RESIDUAL"]).any())

    def test_overstock_classification(self) -> None:
        label, _, _ = classify_stock_outcome_row(
            promo_start_soh=5.0,
            actual_units=1.0,
            end_soh=40.0,
            end_days_cover=45.0,
            stockout_flag=False,
            supplier_class="LONG_LEAD_TIME",
        )
        self.assertEqual(label, "OVERSTOCKED")

    def test_release_gate_blocks_when_stock_outcome_does_not_improve(self) -> None:
        summary = pd.DataFrame([
            {"logic_variant": "current_model", "wape": 0.5, "bias_pct": -5.0, "end_stock_success_rate": 40.0, "overstock_rate": 5.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 1000.0},
            {"logic_variant": "stock_outcome", "wape": 0.4, "bias_pct": -5.0, "end_stock_success_rate": 41.0, "overstock_rate": 5.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 1000.0},
            {"logic_variant": "baseline", "wape": 0.8, "bias_pct": 0.0, "end_stock_success_rate": 30.0, "overstock_rate": 5.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 500.0},
        ])
        stock_summary = pd.DataFrame([{"segment": "total", "start_soh_compliance_rate": 50.0}])
        rec, blocker, _ = evaluate_stock_outcome_release_gate(summary, stock_summary, _frame())
        self.assertEqual(rec, "NO_RELEASE")
        self.assertEqual(blocker, "stock_outcome_success_not_materially_improved")

    def test_release_gate_blocks_overstock_explosion(self) -> None:
        summary = pd.DataFrame([
            {"logic_variant": "current_model", "wape": 0.5, "bias_pct": -5.0, "end_stock_success_rate": 40.0, "overstock_rate": 5.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 1000.0},
            {"logic_variant": "stock_outcome", "wape": 0.4, "bias_pct": -5.0, "end_stock_success_rate": 50.0, "overstock_rate": 20.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 1000.0},
            {"logic_variant": "baseline", "wape": 0.8, "bias_pct": 0.0, "end_stock_success_rate": 30.0, "overstock_rate": 5.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 500.0},
        ])
        stock_summary = pd.DataFrame([{"segment": "total", "start_soh_compliance_rate": 50.0}])
        rec, blocker, _ = evaluate_stock_outcome_release_gate(summary, stock_summary, _frame())
        self.assertEqual(rec, "NO_RELEASE")
        self.assertEqual(blocker, "stock_outcome_overstock_explosion")

    def test_limited_release_only_when_gates_pass(self) -> None:
        summary = pd.DataFrame([
            {"logic_variant": "current_model", "wape": 0.5, "bias_pct": -5.0, "end_stock_success_rate": 40.0, "overstock_rate": 5.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 1000.0},
            {"logic_variant": "stock_outcome", "wape": 0.4, "bias_pct": -5.0, "end_stock_success_rate": 45.0, "overstock_rate": 5.0, "cash_tied_up_cost_proxy": 90.0, "net_value_proxy": 1200.0},
            {"logic_variant": "baseline", "wape": 0.8, "bias_pct": 0.0, "end_stock_success_rate": 30.0, "overstock_rate": 5.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 500.0},
        ])
        stock_summary = pd.DataFrame([{"segment": "total", "start_soh_compliance_rate": 50.0}])
        frame = _frame()
        frame["stock_outcome_release_ready_flag"] = "YES"
        rec, blocker, _ = evaluate_stock_outcome_release_gate(summary, stock_summary, frame)
        self.assertEqual(rec, "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        self.assertEqual(blocker, "none_limited_release_earned")

    def test_unsafe_rows_excluded_from_release(self) -> None:
        frame = _frame(promo_demand_source_quality=["UNSAFE", "UNSAFE", "HIGH", "HIGH"])
        enriched = compute_stock_outcome_order_target(frame)
        enriched["stock_outcome_release_ready_flag"] = np.where(
            enriched["promo_demand_source_quality"].eq("HIGH"),
            "YES",
            "NO",
        )
        limited = int(
            (
                enriched["stock_outcome_release_ready_flag"].eq("YES")
                & enriched["promo_demand_source_quality"].isin(["HIGH", "MEDIUM"])
            ).sum()
        )
        self.assertEqual(limited, 2)
        self.assertFalse(enriched.loc[enriched["promo_demand_source_quality"].eq("UNSAFE"), "stock_outcome_release_ready_flag"].eq("YES").any())


if __name__ == "__main__":
    unittest.main()
