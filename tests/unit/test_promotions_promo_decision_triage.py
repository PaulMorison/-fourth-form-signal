from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_decision_triage import (  # noqa: E402
    apply_promo_decision_triage,
    build_promo_decision_triage_frame,
    build_workload_summary,
    compute_buyer_review_priority_score,
    write_phase5m01_diagnostics,
)
from models.promotions.promo_conviction_calibration import apply_conviction_calibration  # noqa: E402
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
        "department": ["Grocery"] * n,
        "promotion_name": ["Summer"] * n,
        "promotion_start_date": ["2024-06-01"] * n,
        "promo_days": [7] * n,
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
        "supplier_number_source_quality": _rep(["HIGH", "HIGH", "HIGH", "HIGH", "UNKNOWN", "HIGH", "HIGH", "HIGH", "HIGH", "HIGH"]),
        "replenishment_risk_class": ["OVERNIGHT_REPLENISHMENT"] * n,
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


def _pipeline(**overrides: object) -> pd.DataFrame:
    frame = _frame(**overrides)
    regime = build_promo_regime_state_frame(frame)
    brain = apply_regime_brain_decisioning(regime, gate_recommendation="NO_RELEASE")
    return apply_conviction_calibration(brain, gate_recommendation="NO_RELEASE")


class PromoDecisionTriageTests(unittest.TestCase):
    def test_unsafe_rows_auto_block(self) -> None:
        out = build_promo_decision_triage_frame(_pipeline())
        unsafe = out[out["promo_demand_source_quality"].eq("UNSAFE")]
        self.assertTrue(unsafe["decision_triage_class"].eq("AUTO_BLOCK_UNSAFE").all())

    def test_unknown_soh_large_order_auto_blocks(self) -> None:
        out = _pipeline()
        out.loc[0, "promo_start_soh_source_quality"] = "UNKNOWN"
        out.loc[0, "brain_order_units_proposal"] = 25.0
        out.loc[0, "promo_demand_source_quality"] = "MEDIUM"
        out = build_promo_decision_triage_frame(out)
        self.assertEqual(out.loc[0, "decision_triage_class"], "AUTO_BLOCK_DATA_QUALITY")

    def test_overstock_becomes_run_down_review(self) -> None:
        out = build_promo_decision_triage_frame(_pipeline())
        over = out[out["current_stock_position_label"].eq("SEVERELY_OVERSTOCKED")]
        self.assertTrue(
            over["decision_triage_class"].isin([
                "HIGH_PRIORITY_RUN_DOWN_REVIEW",
                "STANDARD_RUN_DOWN_REVIEW",
                "AUTO_BLOCK_CAPITAL_RISK",
            ]).all()
        )

    def test_high_opportunity_becomes_high_priority_buy(self) -> None:
        out = _pipeline()
        mask = out["promo_demand_source_quality"].ne("UNSAFE") & ~out["current_stock_position_label"].isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])
        out.loc[mask, "overall_regime_opportunity_score"] = 65.0
        out.loc[mask, "overall_regime_risk_score"] = 30.0
        out.loc[mask, "brain_action_label"] = "CONTROLLED_BUY"
        out = build_promo_decision_triage_frame(out)
        self.assertTrue((out.loc[mask, "decision_triage_class"] == "HIGH_PRIORITY_BUY_REVIEW").any())

    def test_low_opportunity_becomes_watchlist_or_no_action(self) -> None:
        out = _pipeline()
        mask = out["promo_demand_source_quality"].ne("UNSAFE") & ~out["current_stock_position_label"].isin(["OVERSTOCKED", "SEVERELY_OVERSTOCKED"])
        out.loc[mask, "overall_regime_opportunity_score"] = 10.0
        out.loc[mask, "overall_regime_risk_score"] = 10.0
        out.loc[mask, "brain_action_label"] = "HOLD_FOR_REPLENISHMENT"
        out.loc[mask, "optimal_stock_position_order_units"] = 0.0
        out.loc[mask, "brain_order_units_proposal"] = 0.0
        out = build_promo_decision_triage_frame(out)
        self.assertTrue(out.loc[mask, "decision_triage_class"].isin(["WATCHLIST_ONLY", "NO_ACTION"]).all())

    def test_future_auto_approve_requires_strong_evidence(self) -> None:
        out = build_promo_decision_triage_frame(_pipeline(), config={"gate_recommendation": "NO_RELEASE"})
        self.assertEqual(int(out["future_auto_approve_candidate_flag"].eq("YES").sum()), 0)

    def test_priority_score_bounded(self) -> None:
        score = compute_buyer_review_priority_score(_pipeline())
        self.assertTrue(score.between(0, 100).all())

    def test_high_decision_value_increases_priority(self) -> None:
        low = _pipeline()
        high = _pipeline()
        low["regime_adjusted_decision_value"] = 1.0
        high["regime_adjusted_decision_value"] = 80.0
        self.assertGreater(
            float(compute_buyer_review_priority_score(high).mean()),
            float(compute_buyer_review_priority_score(low).mean()),
        )

    def test_unsafe_lowers_priority(self) -> None:
        out = _pipeline()
        score = compute_buyer_review_priority_score(out)
        unsafe = out["promo_demand_source_quality"].eq("UNSAFE")
        if unsafe.any():
            self.assertLess(float(score[unsafe].max()), float(score[~unsafe].max()))

    def test_unknown_soh_lowers_priority(self) -> None:
        out = _pipeline()
        score = compute_buyer_review_priority_score(out)
        unknown = out["promo_start_soh_source_quality"].eq("UNKNOWN")
        if unknown.any():
            self.assertLess(float(score[unknown].max()), float(score[~unknown].max()))

    def test_high_cash_tie_up_lowers_priority(self) -> None:
        low = _pipeline()
        high = _pipeline()
        low["cash_drag_penalty"] = 0.0
        high["cash_drag_penalty"] = 300.0
        self.assertGreater(
            float(compute_buyer_review_priority_score(low).mean()),
            float(compute_buyer_review_priority_score(high).mean()),
        )

    def test_missed_demand_increases_priority(self) -> None:
        low = _pipeline()
        high = _pipeline()
        low["missed_demand_penalty"] = 0.0
        high["missed_demand_penalty"] = 80.0
        self.assertGreater(
            float(compute_buyer_review_priority_score(high).mean()),
            float(compute_buyer_review_priority_score(low).mean()),
        )

    def test_low_conviction_lowers_priority(self) -> None:
        low = _pipeline()
        high = _pipeline()
        low["calibrated_regime_conviction_score"] = 10.0
        high["calibrated_regime_conviction_score"] = 55.0
        self.assertGreater(
            float(compute_buyer_review_priority_score(high).mean()),
            float(compute_buyer_review_priority_score(low).mean()),
        )

    def test_review_queue_rank_unique(self) -> None:
        out = apply_promo_decision_triage(_pipeline())
        ranks = out.loc[out["buyer_review_queue_rank"].gt(0), "buyer_review_queue_rank"]
        self.assertEqual(len(ranks), ranks.nunique())

    def test_top_50_bucket(self) -> None:
        out = apply_promo_decision_triage(_pipeline())
        self.assertGreater(int(out["buyer_review_queue_bucket"].eq("TOP_50").sum()), 0)
        self.assertLessEqual(int(out["buyer_review_queue_bucket"].eq("TOP_50").sum()), 50)

    def test_top_250_bucket(self) -> None:
        out = apply_promo_decision_triage(_pipeline())
        top250 = int(out["buyer_review_queue_bucket"].isin(["TOP_50", "TOP_100", "TOP_250"]).sum())
        self.assertGreater(top250, 0)
        self.assertLessEqual(top250, 250)

    def test_auto_block_not_in_review_queue(self) -> None:
        out = apply_promo_decision_triage(_pipeline())
        blocked = out[out["auto_block_flag"].eq("YES")]
        self.assertTrue((blocked["buyer_review_required_flag_triaged"] == "NO").all())

    def test_workload_reduced(self) -> None:
        source = _pipeline()
        before = int(source["buyer_review_required_flag"].eq("YES").sum())
        out = apply_promo_decision_triage(source)
        after = int(out["buyer_review_required_flag_triaged"].eq("YES").sum())
        self.assertLess(after, before)

    def test_diagnostics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            source = _pipeline()
            source = apply_promo_decision_triage(source)
            result = write_phase5m01_diagnostics(frame=source, diagnostics_dir=diag)
            for name in (
                "phase5m01_triage_distribution.csv",
                "phase5m01_top_review_queue.csv",
                "phase5m01_auto_block_summary.csv",
                "phase5m01_workload_summary.csv",
                "phase5m01_release_gate.csv",
            ):
                self.assertTrue((diag / name).exists(), msg=name)
            self.assertIn("buyer_review_required_after", result)

    def test_workload_summary_reconciles(self) -> None:
        out = apply_promo_decision_triage(_pipeline())
        before = int(out["buyer_review_required_flag"].eq("YES").sum())
        summary = build_workload_summary(out, review_before=before, release_recommendation="NO_RELEASE").iloc[0]
        self.assertEqual(int(summary["total_rows"]), len(out))
        self.assertEqual(int(summary["buyer_review_required_before"]), before)

    def test_no_nan_numeric_outputs(self) -> None:
        out = apply_promo_decision_triage(_pipeline())
        numeric = out.select_dtypes(include=[np.number])
        self.assertFalse(numeric.isna().any().any())


if __name__ == "__main__":
    unittest.main()
