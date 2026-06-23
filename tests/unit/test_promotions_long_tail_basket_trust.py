from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_buyer_action_pack import (  # noqa: E402
    build_blocked_data_quality_review,
    build_buyer_top_50_actions,
    build_long_tail_basket_trust_summary,
    build_long_tail_stockout_risk_review,
    build_missed_demand_protection_actions,
    write_phase5o01_diagnostics,
)
from models.promotions.promo_conviction_calibration import apply_conviction_calibration  # noqa: E402
from models.promotions.promo_decision_triage import apply_promo_decision_triage  # noqa: E402
from models.promotions.promo_economic_value_scoring import (  # noqa: E402
    apply_economic_review_rerank,
    apply_promo_economic_value_scoring,
    build_promo_economic_value_frame,
)
from models.promotions.promo_long_tail_basket_trust import (  # noqa: E402
    MIN_OPEN_FOR_SALE,
    build_long_tail_basket_trust_frame,
)
from models.promotions.promo_regime_state import build_promo_regime_state_frame  # noqa: E402


def _frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": [772, 772, 772, 772],
        "sku_number": ["1", "2", "3", "4"],
        "sku_description": ["Best seller", "Long tail basket", "Long tail no evidence", "Unsafe long tail"],
        "department": ["Grocery", "Grocery", "Grocery", "Grocery"],
        "category": ["Food", "Food", "Food", "Food"],
        "promotion_name": ["Summer"] * 4,
        "promotion_start_date": ["2024-06-01"] * 4,
        "promo_days": [7] * 4,
        "average_daily_units": [5.0, 0.03, 0.02, 0.04],
        "current_soh": [20.0, 1.0, 1.0, 1.0],
        "expected_soh_at_promo_start_before_order": [20.0, 1.0, 1.0, 1.0],
        "expected_promo_uplift_units": [30.0, 1.0, 0.5, 1.0],
        "simulated_missed_demand_units": [5.0, 0.5, 0.2, 0.5],
        "promo_convexity_score": [60.0, 20.0, 10.0, 15.0],
        "promo_demand_source_quality": ["HIGH", "HIGH", "HIGH", "UNSAFE"],
        "promo_demand_release_ready_flag": ["YES", "YES", "YES", "NO"],
        "feature_basket_structure_evidence_available_flag": [1.0, 1.0, 0.0, 1.0],
        "feature_basket_attach_rate": [0.8, 0.7, None, 0.6],
        "feature_basket_drag_along_dependency_score": [0.2, 0.65, None, 0.55],
        "feature_long_tail_dependency_flag": [0.0, 1.0, 0.0, 1.0],
        "customer_basket_trust_regime": ["BASKET_TRUST_STRONG", "BASKET_TRUST_RISK", "BASKET_TRUST_RISK", "BASKET_TRUST_RISK"],
        "customer_loyalty_regime": ["LOYALTY_HIGH", "LOYALTY_HIGH", "LOYALTY_LOW", "LOYALTY_HIGH"],
        "historical_units_same_discount_avg": [100.0, 2.0, 0.0, 1.0],
        "optimal_base_soh_units": [25.0, 2.0, 2.0, 2.0],
        "leftover_units_above_optimal": [0.0, 0.0, 0.0, 0.0],
        "brain_order_units_proposal": [10.0, 1.0, 0.0, 0.0],
        "final_governed_action_label": ["CONTROLLED_BUY", "HOLD_FOR_REPLENISHMENT", "NO_BUY_RUN_DOWN", "BLOCKED_UNSAFE"],
        "final_governed_order_units": [10.0, 0.0, 0.0, 0.0],
        "auto_block_flag": ["NO", "NO", "NO", "YES"],
        "buyer_review_required_flag_triaged": ["YES", "YES", "YES", "NO"],
        "buyer_review_priority_score": [80.0, 40.0, 25.0, 10.0],
        "decision_triage_class": ["HIGH_PRIORITY_BUY_REVIEW"] * 4,
        "overall_regime_opportunity_score": [70.0, 55.0, 30.0, 20.0],
        "calibrated_regime_conviction_score": [45.0, 35.0, 20.0, 10.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _enriched(**overrides: object) -> pd.DataFrame:
    frame = _frame(**overrides)
    regime = build_promo_regime_state_frame(frame)
    triaged = apply_promo_decision_triage(regime, gate_recommendation="NO_RELEASE", model_bias_pct=-20.0)
    return apply_promo_economic_value_scoring(triaged, gate_recommendation="NO_RELEASE", model_bias_pct=-20.0)


class TestLongTailBasketTrust(unittest.TestCase):
    def test_low_volume_high_basket_attachment_gets_priority(self) -> None:
        low = _enriched()
        low_vol = low.loc[low["sku_number"].eq("2")].iloc[0]
        best = low.loc[low["sku_number"].eq("1")].iloc[0]
        self.assertEqual(low_vol["long_tail_sku_flag"], "YES")
        self.assertGreater(float(low_vol["long_tail_protection_value"]), 0.0)
        self.assertGreater(float(low_vol["basket_attachment_score"]), float(best["basket_attachment_score"]) * 0.5)

    def test_long_tail_below_two_soh_gets_protection_flag(self) -> None:
        out = build_long_tail_basket_trust_frame(_frame())
        row = out.loc[out["sku_number"].eq("2")].iloc[0]
        self.assertEqual(row["long_tail_sku_flag"], "YES")
        self.assertEqual(row["long_tail_open_for_sale_required_flag"], "YES")
        self.assertEqual(float(row["long_tail_minimum_soh_required"]), MIN_OPEN_FOR_SALE)

    def test_two_unit_minimum_is_open_for_sale_not_forecast(self) -> None:
        out = build_long_tail_basket_trust_frame(_frame())
        row = out.loc[out["sku_number"].eq("2")].iloc[0]
        self.assertEqual(float(row["long_tail_minimum_soh_required"]), 2.0)
        self.assertIn("2_unit", row["long_tail_basket_protection_reason"])

    def test_missing_basket_evidence_labelled_unknown_not_zero(self) -> None:
        out = build_long_tail_basket_trust_frame(_frame())
        row = out.loc[out["sku_number"].eq("3")].iloc[0]
        self.assertEqual(row["basket_3plus_attachment_rate"], "UNKNOWN")
        self.assertEqual(row["mission_basket_attachment_rate"], "UNKNOWN")

    def test_unsafe_rows_blocked_from_long_tail_value(self) -> None:
        out = build_long_tail_basket_trust_frame(_frame())
        row = out.loc[out["sku_number"].eq("4")].iloc[0]
        self.assertEqual(float(row["long_tail_protection_value"]), 0.0)
        self.assertEqual(float(row["basket_trust_convexity_value"]), 0.0)
        self.assertIn("unsafe", row["long_tail_basket_protection_reason"])

    def test_long_tail_increases_review_priority_not_auto_order(self) -> None:
        enriched = _enriched()
        long_tail = enriched.loc[enriched["sku_number"].eq("2")].iloc[0]
        self.assertGreater(float(long_tail["long_tail_protection_value"]), 0.0)
        self.assertEqual(float(long_tail["final_governed_order_units"]), 0.0)
        self.assertNotEqual(long_tail["final_governed_action_label"], "AGGRESSIVE_BUY")

    def test_best_seller_still_protected_by_volume_gp(self) -> None:
        enriched = _enriched()
        best = enriched.loc[enriched["sku_number"].eq("1")].iloc[0]
        self.assertEqual(best["long_tail_sku_flag"], "NO")
        self.assertGreater(float(best["expected_gp_capture_value"]), float(best["long_tail_protection_value"]))

    def test_economic_net_value_includes_long_tail_components(self) -> None:
        out = build_promo_economic_value_frame(_frame())
        row = out.loc[out["sku_number"].eq("2")].iloc[0]
        expected = (
            row["expected_gp_capture_value"]
            + row["missed_sales_avoidance_value"]
            + row["basket_trust_protection_value"]
            + row["long_tail_protection_value"]
            + row["basket_trust_convexity_value"]
            + row["overstock_cash_release_value"]
            - row["cash_tied_above_optimal_cost"]
            - row["supplier_risk_cost"]
            - row["review_effort_cost"]
        )
        self.assertAlmostEqual(float(row["economic_net_value_score"]), float(expected), places=3)

    def test_action_pack_columns_present(self) -> None:
        enriched = _enriched()
        top50 = build_buyer_top_50_actions(enriched)
        for col in (
            "long_tail_sku_flag",
            "basket_completion_sku_flag",
            "basket_attachment_score",
            "long_tail_protection_value",
            "long_tail_basket_protection_reason",
        ):
            self.assertIn(col, top50.columns)

    def test_missed_demand_protection_sorts_by_long_tail_value(self) -> None:
        enriched = _enriched()
        actions = build_missed_demand_protection_actions(enriched)
        if not actions.empty:
            values = actions["long_tail_protection_value"].tolist()
            self.assertEqual(values, sorted(values, reverse=True))

    def test_blocked_data_quality_includes_long_tail_fixes(self) -> None:
        enriched = _enriched()
        blocked = build_blocked_data_quality_review(enriched)
        self.assertFalse(blocked.empty)
        self.assertTrue(blocked["data_fix_required"].astype(str).str.contains("basket|SOH|completion|attachment", case=False).any())

    def test_diagnostics_written(self) -> None:
        enriched = _enriched()
        with tempfile.TemporaryDirectory() as tmp:
            diag_dir = Path(tmp)
            result = write_phase5o01_diagnostics(frame=enriched, diagnostics_dir=diag_dir)
            self.assertGreater(result["total_long_tail_skus"], 0)
            self.assertTrue((diag_dir / "phase5o01_long_tail_basket_trust_summary.csv").exists())
            self.assertTrue((diag_dir / "phase5o01_long_tail_stockout_risk_review.csv").exists())
            self.assertTrue((diag_dir / "phase5o01_buyer_top_50_actions.csv").exists())

    def test_stockout_risk_review_has_required_columns(self) -> None:
        enriched = _enriched()
        review = build_long_tail_stockout_risk_review(enriched)
        for col in (
            "SKU",
            "description",
            "department",
            "current_soh",
            "long_tail_minimum_soh_required",
            "basket_attachment_score",
            "action_recommendation",
        ):
            self.assertIn(col, review.columns)

    def test_long_tail_summary_counts(self) -> None:
        enriched = _enriched()
        summary = build_long_tail_basket_trust_summary(enriched).iloc[0]
        self.assertGreaterEqual(int(summary["total_long_tail_skus"]), 1)
        self.assertGreaterEqual(float(summary["long_tail_protection_value_total"]), 0.0)


if __name__ == "__main__":
    unittest.main()
