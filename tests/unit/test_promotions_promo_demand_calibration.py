from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_demand_backtest import compute_wape  # noqa: E402
from models.promotions.promo_demand_calibration import (  # noqa: E402
    DEFAULT_MIN_SAMPLE,
    apply_promo_demand_calibration,
    assign_observation_quality,
    build_calibrated_backtest_summary,
    compute_bias_diagnostics,
    evaluate_limited_release_gate,
    fit_promo_demand_calibration_factors,
)


def _backtest_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": [772] * 6,
            "sku_number": [1, 2, 3, 4, 5, 6],
            "promotion_start_date": ["2024-01-01"] * 6,
            "promotion_end_date": ["2024-01-07"] * 6,
            "promo_days": [7] * 6,
            "department": ["A", "A", "A", "B", "B", "B"],
            "category": ["c1"] * 6,
            "discount_percent": [15, 15, 15, 25, 25, 25],
            "actual_units_sold_promo": [10.0, 8.0, 12.0, 4.0, 0.0, 6.0],
            "model_expected_units_total_promo": [5.0, 4.0, 6.0, 3.0, 2.0, 2.0],
            "baseline_expected_units_total_promo": [8.0, 8.0, 8.0, 5.0, 5.0, 5.0],
            "historical_proxy_expected_units_total_promo": [7.0, 7.0, 7.0, 4.0, 4.0, 4.0],
            "promo_demand_source_quality": ["HIGH", "HIGH", "MEDIUM", "MEDIUM", "UNSAFE", "HIGH"],
            "promo_demand_release_ready_flag": ["YES"] * 6,
            "model_beats_baseline_flag": [1, 1, 1, 1, 0, 1],
            "model_beats_historical_proxy_flag": [1, 1, 1, 1, 0, 1],
            "stockout_suspected_flag": [0, 1, 0, 0, 0, 0],
            "leftover_units_estimate": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            "under_order_risk_units": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
    )


class PromoDemandCalibrationTests(unittest.TestCase):
    def test_bias_pct_and_wape(self) -> None:
        frame = _backtest_frame()
        total = compute_bias_diagnostics(frame)
        row = total[total["segment"].eq("total")].iloc[0]
        actual = frame["actual_units_sold_promo"].sum()
        forecast = frame["model_expected_units_total_promo"].sum()
        expected_bias = (forecast - actual) / actual * 100.0
        self.assertAlmostEqual(float(row["forecast_bias_pct"]), expected_bias, places=4)
        self.assertAlmostEqual(float(row["wape"]), compute_wape(frame["actual_units_sold_promo"], frame["model_expected_units_total_promo"]), places=4)

    def test_segmentation_preserves_totals(self) -> None:
        diag = compute_bias_diagnostics(_backtest_frame())
        total = int(diag[diag["segment"].eq("total")]["row_count"].iloc[0])
        self.assertEqual(total, 6)

    def test_observation_quality_rules(self) -> None:
        enriched = assign_observation_quality(_backtest_frame())
        stockout = enriched[enriched["sku_number"].eq(2)].iloc[0]
        zero_actual = enriched[enriched["sku_number"].eq(5)].iloc[0]
        clean = enriched[enriched["sku_number"].eq(1)].iloc[0]
        self.assertEqual(stockout["demand_observation_quality"], "CENSORED")
        self.assertEqual(stockout["actual_units_observed_is_censored_flag"], "YES")
        self.assertEqual(zero_actual["demand_observation_quality"], "LOW")
        self.assertEqual(clean["demand_observation_quality"], "HIGH")
        self.assertEqual(clean["calibration_eligible_flag"], "YES")
        self.assertEqual(stockout["calibration_eligible_flag"], "NO")

    def test_calibration_factor_math_and_bounds(self) -> None:
        frame = _backtest_frame()
        factors = fit_promo_demand_calibration_factors(frame, min_sample=2)
        total = factors[factors["segment_level"].eq("total")].iloc[0]
        eligible = assign_observation_quality(frame)
        eligible = eligible[eligible["calibration_eligible_flag"].eq("YES")]
        expected_raw = eligible["actual_units_sold_promo"].sum() / eligible["model_expected_units_total_promo"].sum()
        self.assertGreaterEqual(float(total["factor_applied"]), 0.75)
        self.assertLessEqual(float(total["factor_applied"]), 2.50)
        self.assertAlmostEqual(float(total["raw_factor"]), expected_raw, places=3)
        self.assertFalse(factors[["raw_factor", "shrunk_factor", "factor_applied"]].isna().any().any())
        self.assertFalse(np.isinf(factors[["raw_factor", "shrunk_factor", "factor_applied"]].to_numpy()).any())

    def test_segment_hierarchy_fallback(self) -> None:
        factors = fit_promo_demand_calibration_factors(_backtest_frame(), min_sample=2)
        self.assertTrue((factors["segment_level"] == "total").any())
        self.assertTrue((factors["segment_level"] == "department").any())

    def test_small_sample_shrinks_toward_total(self) -> None:
        factors = fit_promo_demand_calibration_factors(_backtest_frame(), min_sample=DEFAULT_MIN_SAMPLE)
        total_factor = float(factors[factors["segment_level"].eq("total")]["factor_applied"].iloc[0])
        dept = factors[(factors["segment_level"].eq("department")) & (factors["sample_size_ok_flag"].eq("NO"))]
        if not dept.empty:
            raw = float(dept.iloc[0]["raw_factor"])
            shrunk = float(dept.iloc[0]["shrunk_factor"])
            if raw != total_factor:
                self.assertNotEqual(shrunk, raw)

    def test_apply_preserves_raw_and_creates_calibrated(self) -> None:
        frame = _backtest_frame()
        factors = fit_promo_demand_calibration_factors(frame, min_sample=2)
        out = apply_promo_demand_calibration(frame, factors)
        pd.testing.assert_series_equal(
            out["model_expected_units_total_promo_raw"],
            frame["model_expected_units_total_promo"],
            check_names=False,
        )
        self.assertTrue((out["model_expected_units_total_promo_calibrated"] >= 0).all())
        self.assertFalse(out[["model_expected_units_total_promo_calibrated", "promo_demand_calibration_factor"]].isna().any().any())
        self.assertFalse(np.isinf(out["model_expected_units_total_promo_calibrated"]).any())
        self.assertGreater(out["model_expected_units_total_promo_calibrated"].nunique(), 3)

    def test_release_gate_blocks_and_allows(self) -> None:
        frame = _backtest_frame()
        factors = fit_promo_demand_calibration_factors(frame, min_sample=2)
        calibrated = apply_promo_demand_calibration(frame, factors)
        summary = build_calibrated_backtest_summary(frame, calibrated)

        bad_summary = summary.copy()
        bad_summary.loc[bad_summary["variant"].eq("calibrated_model"), "wape"] = 9.0
        rec, blocker, _ = evaluate_limited_release_gate(bad_summary, calibrated)
        self.assertEqual(rec, "NO_RELEASE")
        self.assertEqual(blocker, "calibrated_wape_not_better_than_baseline")

        bias_bad = summary.copy()
        bias_bad.loc[bias_bad["variant"].eq("calibrated_model"), "bias_pct"] = -80.0
        rec2, blocker2, _ = evaluate_limited_release_gate(bias_bad, calibrated)
        self.assertEqual(rec2, "NO_RELEASE")
        self.assertEqual(blocker2, "calibrated_bias_outside_allowed_range")

        unsafe = calibrated.copy()
        unsafe["promo_demand_source_quality"] = "UNSAFE"
        unsafe["calibration_release_ready_flag"] = "NO"
        rec3, _, _ = evaluate_limited_release_gate(summary, unsafe)
        self.assertNotEqual(rec3, "CUSTOMER_RELEASE_READY")

        rec4, _, _ = evaluate_limited_release_gate(summary, calibrated)
        self.assertNotEqual(rec4, "CUSTOMER_RELEASE_READY")
        self.assertIn(rec4, {"NO_RELEASE", "INTERNAL_SHADOW_ONLY", "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY"})

    def test_limited_release_when_gate_conditions_pass(self) -> None:
        scored = pd.DataFrame(
            {
                "promo_demand_source_quality": ["HIGH", "MEDIUM"],
                "calibration_release_ready_flag": ["YES", "YES"],
                "calibration_quality": ["HIGH", "MEDIUM"],
                "model_expected_units_total_promo_calibrated": [3.0, 4.0],
            }
        )
        summary = pd.DataFrame(
            [
                {"variant": "raw_model", "wape": 0.8, "bias_pct": -40.0, "estimated_net_value_proxy": 100.0},
                {"variant": "calibrated_model", "wape": 0.6, "bias_pct": -5.0, "estimated_net_value_proxy": 500.0},
                {"variant": "baseline", "wape": 0.9, "bias_pct": 0.0, "estimated_net_value_proxy": 0.0},
                {"variant": "historical_proxy", "wape": 0.9, "bias_pct": 0.0, "estimated_net_value_proxy": 0.0},
            ]
        )
        rec, blocker, gate = evaluate_limited_release_gate(summary, scored)
        self.assertEqual(rec, "LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY")
        self.assertEqual(blocker, "none_limited_release_earned")
        self.assertEqual(int(gate["limited_release_rows"].iloc[0]), 2)


if __name__ == "__main__":
    unittest.main()
