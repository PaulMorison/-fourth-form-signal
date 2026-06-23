from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_bias_segment_calibration import (  # noqa: E402
    PRIMARY_BLOCKER,
    RELEASE_RECOMMENDATION,
    apply_asymmetric_segment_calibration,
    build_bias_calibration_frame,
    estimate_segment_bias_factors,
    evaluate_bias_repair,
    write_phase6a_diagnostics,
)


def _row(**overrides) -> dict:
    base = {
        "store_number": 772,
        "promotion_id": "P1",
        "sku_number": "101",
        "actual_units_sold_promo": 10.0,
        "model_expected_units_total_promo": 4.0,
        "baseline_expected_units_total_promo": 5.0,
        "historical_proxy_expected_units_total_promo": 5.0,
        "forecast_error_units": -6.0,
        "forecast_abs_error_units": 6.0,
        "department": "SKIN",
        "category": "FACE",
        "promo_days": 7.0,
        "promotion_start_date": "2026-01-01",
        "promotion_end_date": "2026-01-14",
        "discount_percent": 15.0,
        "promo_demand_source_quality": "HIGH",
        "promo_demand_release_ready_flag": "YES",
        "stockout_suspected_flag": 0,
        "leftover_units_estimate": 0.0,
        "long_tail_sku_flag": "YES",
        "mission_sku_score": 20,
        "basket_attachment_source_quality": "HIGH",
        "segment_historical_wape": 0.3,
        "segment_historical_bias_pct": -10.0,
    }
    base.update(overrides)
    return base


class TestPromoBiasSegmentCalibration(unittest.TestCase):
    def test_build_bias_calibration_frame(self) -> None:
        frame = build_bias_calibration_frame(backtest_df=pd.DataFrame([_row(), _row(sku_number="102")]))
        self.assertFalse(frame.empty)
        self.assertIn("model_expected_units_total_promo_calibrated", frame.columns)
        self.assertIn("segment_calibration_eligible_flag", frame.columns)
        self.assertTrue(frame["requires_human_approval_flag"].eq("YES").all())

    def test_estimate_segment_bias_factors(self) -> None:
        rows = [_row(actual_units_sold_promo=20.0, model_expected_units_total_promo=5.0) for _ in range(40)]
        frame = build_bias_calibration_frame(backtest_df=pd.DataFrame(rows))
        factors = estimate_segment_bias_factors(frame, min_sample=5)
        self.assertFalse(factors.empty)
        self.assertIn("factor_applied", factors.columns)
        total = factors.loc[factors["segment_level"].eq("total")]
        self.assertFalse(total.empty)
        self.assertGreaterEqual(float(total.iloc[0]["factor_applied"]), 1.0)

    def test_apply_asymmetric_segment_calibration(self) -> None:
        frame = build_bias_calibration_frame(backtest_df=pd.DataFrame([_row() for _ in range(20)]))
        factors = estimate_segment_bias_factors(frame, min_sample=3)
        out = apply_asymmetric_segment_calibration(frame, factors)
        self.assertIn("segment_calibrated_expected_units", out.columns)
        self.assertTrue((out["segment_calibrated_expected_units"] >= out["model_expected_units_total_promo_calibrated"]).any())
        self.assertTrue(out["segment_calibration_status"].eq("PROPOSED_NOT_DEPLOYED").all())

    def test_evaluate_bias_repair(self) -> None:
        frame = build_bias_calibration_frame(backtest_df=pd.DataFrame([_row() for _ in range(30)]))
        factors = estimate_segment_bias_factors(frame, min_sample=3)
        calibrated = apply_asymmetric_segment_calibration(frame, factors)
        evaluation, gate = evaluate_bias_repair(calibrated)
        self.assertEqual(len(evaluation), 4)
        self.assertIn("segment_calibrated_model", evaluation["model_variant"].tolist())
        self.assertEqual(str(gate.iloc[0]["customer_release_recommendation"]), RELEASE_RECOMMENDATION)

    def test_write_phase6a_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diag = Path(tmp)
            result = write_phase6a_diagnostics(
                diagnostics_dir=diag,
                backtest_df=pd.DataFrame([_row() for _ in range(25)]),
            )
            self.assertTrue((diag / "phase6a01_segment_bias_factors.csv").exists())
            self.assertTrue((diag / "phase6a01_bias_repair_evaluation.csv").exists())
            self.assertTrue((diag / "phase6a01_release_gate.csv").exists())
            self.assertTrue((diag / "phase6a01_bias_calibration_frame_sample.csv").exists())
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)
            self.assertFalse(result["governed_actions_overwritten"])
            self.assertFalse(result["auto_order_created"])

    def test_bias_improves_with_underforecast(self) -> None:
        frame = build_bias_calibration_frame(
            backtest_df=pd.DataFrame([_row(actual_units_sold_promo=20.0, model_expected_units_total_promo=5.0) for _ in range(50)])
        )
        factors = estimate_segment_bias_factors(frame, min_sample=5)
        calibrated = apply_asymmetric_segment_calibration(frame, factors)
        evaluation, _ = evaluate_bias_repair(calibrated)
        cal_bias = float(evaluation.loc[evaluation["model_variant"].eq("calibrated_model"), "bias_pct"].iloc[0])
        seg_bias = float(evaluation.loc[evaluation["model_variant"].eq("segment_calibrated_model"), "bias_pct"].iloc[0])
        self.assertGreater(seg_bias, cal_bias)

    def test_release_not_inflated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = write_phase6a_diagnostics(
                diagnostics_dir=Path(tmp),
                backtest_df=pd.DataFrame([_row() for _ in range(30)]),
            )
            self.assertEqual(result["release_recommendation"], RELEASE_RECOMMENDATION)
            self.assertIn(
                result["primary_blocker"],
                {
                    PRIMARY_BLOCKER,
                    "segment_repair_improves_metrics_but_not_release_ready",
                    "segment_calibration_did_not_improve_bias",
                    "no_segment_calibration_allowed_rows",
                },
            )

    def test_governed_fields_not_overwritten(self) -> None:
        rows = [_row() for _ in range(10)]
        rows[0]["final_governed_action_label"] = "TOP_UP_TO_OPTIMAL"
        rows[0]["final_governed_order_units"] = 3.0
        frame = build_bias_calibration_frame(backtest_df=pd.DataFrame(rows), scored_df=pd.DataFrame(rows))
        if "final_governed_action_label" in frame.columns:
            self.assertEqual(str(frame.iloc[0]["final_governed_action_label"]), "TOP_UP_TO_OPTIMAL")


if __name__ == "__main__":
    unittest.main()
