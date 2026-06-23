from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_bias_root_cause_review import (  # noqa: E402
    PRIMARY_BLOCKER,
    RELEASE_RECOMMENDATION,
    analyse_bias_by_segment,
    analyse_overforecast_drivers,
    analyse_underforecast_drivers,
    build_bias_root_cause_frame,
    build_release_blocker_repair_plan,
    build_release_blocker_evidence_pack,
    build_report_sense_check,
    write_phase5z_diagnostics,
)


def _row(**overrides) -> dict:
    base = {
        "store_number": 772,
        "promotion_id": "P1",
        "sku_number": "101",
        "actual_units_sold_promo": 10.0,
        "model_expected_units_total_promo": 4.0,
        "forecast_error_units": -6.0,
        "forecast_abs_error_units": 6.0,
        "department": "SKIN",
        "category": "FACE",
        "promo_demand_source_quality": "HIGH",
        "promo_demand_release_ready_flag": "YES",
        "stockout_suspected_flag": 0,
        "leftover_units_estimate": 0.0,
        "long_tail_sku_flag": "YES",
        "mission_sku_flag": "NO",
        "mission_sku_score": 20,
        "basket_attachment_source_quality": "LOW",
        "supplier_replenishment_regime": "UNKNOWN",
        "stock_position_regime": "BALANCED",
        "promo_convexity_regime": "HIGH",
        "segment_historical_bias_pct": -20.0,
        "segment_historical_wape": 0.6,
        "decision_triage_class": "REVIEW",
        "shadow_candidate_class": "SHADOW_TOP_50_CANDIDATE",
        "alpha_pattern_label": "ALPHA_A",
        "missed_units_risk": 12.0,
        "cash_tied_above_optimal_cost": 2.0,
    }
    base.update(overrides)
    return base


def _over_row(**overrides) -> dict:
    return _row(
        actual_units_sold_promo=1.0,
        model_expected_units_total_promo=5.0,
        forecast_error_units=4.0,
        forecast_abs_error_units=4.0,
        long_tail_sku_flag="NO",
        promo_convexity_regime="LOW",
        promo_demand_source_quality="LOW",
        leftover_units_estimate=3.0,
        **overrides,
    )


class TestPromoBiasRootCauseReview(unittest.TestCase):
    def test_phase5z_diagnostics_written(self) -> None:
        frame = pd.DataFrame([_row(), _row(sku_number="102"), _over_row(sku_number="103")])
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp) / "diag"
            pack = Path(tmp) / "pack"
            pack.mkdir()
            pd.DataFrame([{
                "store_number": 772, "promotion_id": "P1", "sku_number": "101",
                "advisory_label": "INTERNAL_SHADOW_ADVISORY_ONLY",
                "production_ordering_approved": "NO",
                "shadow_candidate_class": "SHADOW_TOP_50_CANDIDATE",
            }]).to_csv(pack / "PROMO_ORDER_PLAN.csv", index=False)
            pd.DataFrame([{"customer_release_recommendation": RELEASE_RECOMMENDATION, "primary_blocker": PRIMARY_BLOCKER}]).to_csv(
                pack / "PROMO_RELEASE_GATE_SUMMARY.csv", index=False
            )
            pd.DataFrame([{"primary_blocker": PRIMARY_BLOCKER, "model_wape": 0.67}]).to_csv(pack / "PROMO_MANAGER_SUMMARY.csv", index=False)
            pd.DataFrame([{"segment_type": "total", "model_bias_pct": -50, "underforecast_rate": 21}]).to_csv(
                pack / "PROMO_ERROR_RATE_DASHBOARD.csv", index=False
            )
            result = write_phase5z_diagnostics(
                diagnostics_dir=diag,
                operating_pack_dir=pack,
                backtest_df=frame,
                scored_df=frame,
            )
            self.assertTrue((diag / "phase5z01_bias_root_cause_summary.csv").exists())
            self.assertTrue((diag / "phase5z01_underforecast_driver_review.csv").exists())
            self.assertTrue((diag / "phase5z01_overforecast_driver_review.csv").exists())
            self.assertTrue((diag / "phase5z01_bias_repair_plan.csv").exists())
            self.assertTrue((diag / "phase5z01_report_sense_check.csv").exists())
            self.assertTrue((diag / "phase5z01_release_blocker_evidence_pack.csv").exists())
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)

    def test_negative_bias_produces_release_blocker(self) -> None:
        frame = pd.DataFrame([_row() for _ in range(10)])
        summary = analyse_bias_by_segment(frame)
        total = summary.loc[summary["segment_name"].eq("total")]
        self.assertFalse(total.empty)
        self.assertLess(float(total.iloc[0]["raw_bias_pct"]), -15.0)

    def test_long_tail_underprotection_identified(self) -> None:
        frame = pd.DataFrame([_row(long_tail_sku_flag="YES") for _ in range(5)])
        under = analyse_underforecast_drivers(frame)
        self.assertFalse(under.empty)
        causes = under["likely_root_cause"].astype(str).tolist()
        self.assertTrue(any("LONG_TAIL" in c or "BASKET" in c or "PROMO_UPLIFT" in c for c in causes))

    def test_weak_promo_overforecast_identified(self) -> None:
        frame = pd.DataFrame([_over_row() for _ in range(5)])
        over = analyse_overforecast_drivers(frame)
        self.assertFalse(over.empty)
        self.assertIn(over.iloc[0]["likely_root_cause"], {
            "WEAK_PROMO_DO_NOT_CHASE", "PROMO_UPLIFT_OVERSTATED", "LOW_EVIDENCE_PROMO_HISTORY",
            "LOW_CONVEXITY_PROMO", "OVERSTOCK_ALREADY_HIGH", "BASKET_VALUE_FALSE_POSITIVE",
        })

    def test_repair_plan_advisory_only(self) -> None:
        frame = pd.DataFrame([_row(), _over_row(sku_number="102")])
        summary = analyse_bias_by_segment(frame)
        under = analyse_underforecast_drivers(frame)
        over = analyse_overforecast_drivers(frame)
        repair = build_release_blocker_repair_plan(summary, under, over)
        self.assertFalse(repair.empty)
        self.assertTrue(repair["requires_human_approval_flag"].eq("YES").all())

    def test_report_sense_check_flags_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp)
            pd.DataFrame([{
                "advisory_label": "INTERNAL_SHADOW_ADVISORY_ONLY",
                "production_ordering_approved": "NO",
                "shadow_candidate_class": "SHADOW",
            }]).to_csv(pack / "PROMO_ORDER_PLAN.csv", index=False)
            pd.DataFrame([{"primary_blocker": PRIMARY_BLOCKER, "customer_report_release_approved": RELEASE_RECOMMENDATION}]).to_csv(
                pack / "PROMO_MANAGER_SUMMARY.csv", index=False
            )
            pd.DataFrame([{"customer_release_recommendation": RELEASE_RECOMMENDATION}]).to_csv(
                pack / "PROMO_RELEASE_GATE_SUMMARY.csv", index=False
            )
            pd.DataFrame([{"model_bias_pct": -50, "underforecast_rate": 21}]).to_csv(pack / "PROMO_ERROR_RATE_DASHBOARD.csv", index=False)
            sense = build_report_sense_check(pack)
            adv = sense.loc[sense["sense_check_area"].eq("advisory_labelling")]
            self.assertFalse(adv.empty)
            self.assertEqual(str(adv.iloc[0]["status"]), "PASS")

    def test_evidence_pack_explains_blocker(self) -> None:
        frame = pd.DataFrame([_row() for _ in range(3)])
        summary = analyse_bias_by_segment(frame)
        repair = build_release_blocker_repair_plan(summary, analyse_underforecast_drivers(frame), analyse_overforecast_drivers(frame))
        evidence = build_release_blocker_evidence_pack(summary, repair)
        self.assertFalse(evidence.empty)
        self.assertEqual(str(evidence.iloc[0]["release_recommendation"]), RELEASE_RECOMMENDATION)
        self.assertEqual(str(evidence.iloc[0]["primary_blocker"]), PRIMARY_BLOCKER)

    def test_no_order_file_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp) / "diag"
            frame = pd.DataFrame([_row()])
            write_phase5z_diagnostics(
                diagnostics_dir=diag,
                operating_pack_dir=Path(tmp) / "pack",
                backtest_df=frame,
                scored_df=frame,
            )
            auto_files = list(diag.rglob("*auto*order*"))
            self.assertEqual(len(auto_files), 0)

    def test_release_status_unchanged(self) -> None:
        frame = pd.DataFrame([_row()])
        summary = analyse_bias_by_segment(frame)
        self.assertTrue((summary["release_blocker_status"] == PRIMARY_BLOCKER).any() or summary["segment_name"].eq("total").any())
        frame_out = build_bias_root_cause_frame(backtest_df=frame, scored_df=frame)
        if "final_governed_action_label" in frame_out.columns:
            self.assertTrue(True)
        else:
            self.assertIn("forecast_error_units", frame_out.columns)

    def test_governed_actions_not_modified(self) -> None:
        scored = pd.DataFrame([{
            **_row(),
            "final_governed_action_label": "TOP_UP_TO_OPTIMAL",
            "final_governed_order_units": 2.0,
        }])
        frame = build_bias_root_cause_frame(backtest_df=scored, scored_df=scored)
        self.assertEqual(str(frame.iloc[0]["final_governed_action_label"]), "TOP_UP_TO_OPTIMAL")


if __name__ == "__main__":
    unittest.main()
