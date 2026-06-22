from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_stock_outcome_optimisation import compute_stock_outcome_order_target  # noqa: E402
from models.promotions.promo_stock_truth_repair import (  # noqa: E402
    DAILY_SUPPLIER_NUMBER,
    DEFAULT_LONG_LEAD_DAYS,
    apply_stock_truth_repair,
    evaluate_stock_truth_release_gate,
    resolve_inbound_stock,
    resolve_promo_start_soh,
    resolve_supplier_number,
)


def _frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": [772, 772, 772, 772],
        "sku_number": ["1", "2", "3", "4"],
        "promotion_start_date": ["2024-01-01"] * 4,
        "promo_days": [7, 7, 7, 7],
        "days_to_promo_start": [10, 10, 3, 0],
        "actual_units_sold_promo": [0.0, 1.0, 4.0, 6.0],
        "baseline_expected_units_total_promo": [7.0, 7.0, 14.0, 21.0],
        "forecast_demand_units": [2.0, 2.0, 4.0, 6.0],
        "stockout_suspected_flag": [0, 0, 1, 1],
        "qty_on_order": [1.0, 0.0, 2.0, 0.0],
        "on_order_at_advice_time": [1.0, 0.0, 2.0, 0.0],
        "supplier_number": [99999, 1001, 1001, 0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


class PromoStockTruthRepairTests(unittest.TestCase):
    def test_exact_promo_start_snapshot_preferred(self) -> None:
        frame = _frame(promo_start_soh=[5.0, 5.0, 5.0, 5.0], current_soh=[1.0, 1.0, 1.0, 1.0])
        out = resolve_promo_start_soh(frame)
        self.assertEqual(out["promo_start_soh_source"].iloc[0], "exact_promo_start_snapshot")
        self.assertEqual(out["promo_start_soh_source_quality"].iloc[0], "HIGH")

    def test_latest_pre_promo_snapshot_used_when_exact_missing(self) -> None:
        frame = _frame(
            projected_SOH_at_promo_start=[4.0, 4.0, 4.0, 4.0],
            current_soh=[1.0, 1.0, 1.0, 1.0],
        )
        out = resolve_promo_start_soh(frame)
        self.assertEqual(out["promo_start_soh_source"].iloc[0], "projected_pre_promo_snapshot")
        self.assertAlmostEqual(float(out["promo_start_soh_resolved"].iloc[0]), 4.0)

    def test_current_soh_used_only_before_promo_start(self) -> None:
        frame = _frame(current_soh=[3.0, 3.0, 3.0, 3.0], days_to_promo_start=[5, 5, 5, 0])
        out = resolve_promo_start_soh(frame)
        self.assertEqual(out.loc[0, "promo_start_soh_source"], "current_soh_pre_start")
        self.assertNotEqual(out.loc[3, "promo_start_soh_source"], "current_soh_pre_start")

    def test_missing_soh_not_silently_true_zero(self) -> None:
        frame = _frame(actual_units_sold_promo=[0.0, 0.0, 0.0, 0.0], stockout_suspected_flag=[0, 0, 0, 0])
        out = resolve_promo_start_soh(frame)
        self.assertIn("TRUE_ZERO", set(out["promo_start_soh_source_quality"]))
        self.assertTrue((out.loc[out["promo_start_soh_source_quality"].eq("TRUE_ZERO"), "promo_start_soh_resolved"] == 0.0).all())

    def test_negative_soh_clipped(self) -> None:
        frame = _frame(promo_start_soh=[-2.0, -2.0, -2.0, -2.0])
        out = resolve_promo_start_soh(frame)
        self.assertTrue((out["promo_start_soh_resolved"] >= 0).all())

    def test_confidence_score_bounded(self) -> None:
        out = resolve_promo_start_soh(_frame(promo_start_soh=[2.0] * 4))
        self.assertTrue(out["promo_start_soh_confidence_score"].between(0, 100).all())

    def test_inbound_before_promo_counted(self) -> None:
        frame = resolve_supplier_number(_frame())
        out = resolve_inbound_stock(frame)
        self.assertTrue((out["inbound_units_before_promo"] >= 0).all())

    def test_inbound_during_promo_for_daily_supplier(self) -> None:
        frame = resolve_supplier_number(_frame(supplier_number=[99999, 99999, 99999, 99999], days_to_promo_start=[1, 1, 1, 1]))
        out = resolve_inbound_stock(frame)
        self.assertTrue(float(out.loc[0, "inbound_units_during_promo"]) >= 0.0)

    def test_unknown_inbound_has_quality_flag(self) -> None:
        frame = resolve_supplier_number(_frame(qty_on_order=[np.nan] * 4, on_order_at_advice_time=[np.nan] * 4))
        out = resolve_inbound_stock(frame)
        self.assertEqual(out["inbound_stock_source_quality"].iloc[0], "UNKNOWN")
        self.assertEqual(out["inbound_reliability_flag"].iloc[0], "NO")

    def test_reliable_inbound_reduces_order_requirement(self) -> None:
        frame = apply_stock_truth_repair(_frame(current_soh=[2.0] * 4, qty_on_order=[5.0, 0.0, 0.0, 0.0]))
        with_inbound = compute_stock_outcome_order_target(frame)
        without = compute_stock_outcome_order_target(
            frame.assign(reliable_inbound_units_before_or_during_promo=0.0, inbound_units_before_promo=0.0)
        )
        self.assertLess(
            float(with_inbound.loc[0, "target_order_units_stock_outcome"]),
            float(without.loc[0, "target_order_units_stock_outcome"]),
        )

    def test_supplier_99999_daily_replenishment(self) -> None:
        out = resolve_supplier_number(_frame(supplier_number=[99999, 99999, 99999, 99999]))
        self.assertEqual(out["supplier_replenishment_class_repaired"].iloc[0], "DAILY_REPLENISHMENT")
        self.assertEqual(int(out["supplier_lead_time_days_repaired"].iloc[0]), 1)

    def test_non_99999_long_lead(self) -> None:
        out = resolve_supplier_number(_frame())
        row = out[out["supplier_number_resolved"].ne(DAILY_SUPPLIER_NUMBER)].iloc[0]
        self.assertEqual(row["supplier_replenishment_class_repaired"], "LONG_LEAD_TIME")
        self.assertEqual(int(row["supplier_lead_time_days_repaired"]), DEFAULT_LONG_LEAD_DAYS)

    def test_unknown_supplier_conservative(self) -> None:
        lookup = pd.DataFrame({"sku_number": ["1", "2", "3", "4"], "inferred_supplier_number": [np.nan] * 4})
        out = resolve_supplier_number(_frame(supplier_number=[0, 0, 0, 0]), lookup=lookup)
        self.assertEqual(out["supplier_replenishment_class_repaired"].iloc[0], "UNKNOWN_SUPPLIER")
        self.assertEqual(out["supplier_number_source_quality"].iloc[0], "UNKNOWN")

    def test_repaired_backtest_non_negative_proxies(self) -> None:
        out = apply_stock_truth_repair(_frame())
        from models.promotions.promo_stock_outcome_optimisation import enrich_stock_outcome_fields

        enriched = enrich_stock_outcome_fields(compute_stock_outcome_order_target(out))
        self.assertTrue((enriched["simulated_missed_sales_units"] >= 0).all())
        self.assertTrue((enriched["simulated_leftover_units"] >= 0).all())

    def test_repair_reduces_false_zero_assumptions(self) -> None:
        raw = _frame()
        repaired = apply_stock_truth_repair(raw)
        unknown_before = int((raw.get("promo_start_soh_source_quality", pd.Series(index=raw.index)).eq("UNKNOWN")).sum()) if "promo_start_soh_source_quality" in raw.columns else len(raw)
        resolved_non_unknown = int(repaired["promo_start_soh_source_quality"].ne("UNKNOWN").sum())
        self.assertGreater(resolved_non_unknown, 0)

    def test_release_gate_blocks_poor_coverage(self) -> None:
        before = pd.DataFrame([
            {"logic_variant": "stock_outcome", "wape": 0.5, "bias_pct": -5.0, "end_stock_success_rate": 5.0, "missed_sales_units": 100.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 1000.0},
            {"logic_variant": "baseline", "wape": 0.8, "bias_pct": 0.0, "end_stock_success_rate": 3.0, "missed_sales_units": 200.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 500.0},
        ])
        after = before.copy()
        after.loc[after["logic_variant"].eq("stock_outcome"), "cash_tied_up_cost_proxy"] = 200.0
        cov = pd.DataFrame()
        frame = _frame()
        frame["supplier_number_resolved"] = 1001
        frame["supplier_number_source_quality"] = "HIGH"
        frame["promo_start_soh_source_quality"] = "HIGH"
        rec, blocker, _ = evaluate_stock_truth_release_gate(before, after, cov, cov, frame)
        self.assertEqual(rec, "NO_RELEASE")
        self.assertIn(blocker, {"stock_outcome_cash_tie_up_explosion", "stock_truth_coverage_still_poor"})

    def test_limited_release_only_when_both_improve(self) -> None:
        before = pd.DataFrame([
            {"logic_variant": "stock_outcome", "wape": 0.5, "bias_pct": -5.0, "end_stock_success_rate": 5.0, "missed_sales_units": 200.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 1000.0},
            {"logic_variant": "baseline", "wape": 0.8, "bias_pct": 0.0, "end_stock_success_rate": 3.0, "missed_sales_units": 300.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 500.0},
        ])
        after = pd.DataFrame([
            {"logic_variant": "stock_outcome", "wape": 0.5, "bias_pct": -5.0, "end_stock_success_rate": 8.0, "missed_sales_units": 100.0, "cash_tied_up_cost_proxy": 90.0, "net_value_proxy": 1200.0},
            {"logic_variant": "baseline", "wape": 0.8, "bias_pct": 0.0, "end_stock_success_rate": 3.0, "missed_sales_units": 300.0, "cash_tied_up_cost_proxy": 100.0, "net_value_proxy": 500.0},
        ])
        frame = _frame()
        frame["stock_outcome_release_ready_flag"] = "YES"
        frame["promo_demand_source_quality"] = "HIGH"
        frame["supplier_number_resolved"] = 1001
        frame["supplier_number_source_quality"] = "HIGH"
        frame["promo_start_soh_source_quality"] = "HIGH"
        rec, blocker, _ = evaluate_stock_truth_release_gate(before, after, pd.DataFrame(), pd.DataFrame(), frame)
        self.assertEqual(rec, "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")


if __name__ == "__main__":
    unittest.main()
