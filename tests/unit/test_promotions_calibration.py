from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.cohorts import PromotionDecisionCalibrator  # noqa: E402


def _calibration_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "promotion_row_key": ["a", "b", "c", "d", "e"],
            "nearest_archetype_similarity": [0.42, 0.55, 0.64, 0.78, 0.86],
            "nearest_archetype_sample_size": [1, 3, 5, 8, 13],
            "row_model_confidence_score": [0.30, 0.46, 0.55, 0.68, 0.82],
            "nearest_archetype_confidence_score": [0.25, 0.40, 0.52, 0.67, 0.84],
            "nearest_archetype_destructiveness_score": [0.15, 0.32, 0.48, 0.74, 0.91],
            "nearest_archetype_repeatability_score": [0.18, 0.35, 0.58, 0.76, 0.89],
            "nearest_archetype_strength_score": [0.20, 0.40, 0.59, 0.73, 0.88],
            "nearest_archetype_fragility_score": [0.12, 0.28, 0.34, 0.60, 0.81],
            "predicted_units_sold": [42.0, 50.0, 57.0, 64.0, 72.0],
            "nearest_archetype_expected_units": [40.0, 48.0, 53.0, 61.0, 70.0],
            "predicted_sales_ex_gst": [620.0, 710.0, 790.0, 890.0, 1010.0],
            "nearest_archetype_expected_sales_ex_gst": [610.0, 690.0, 770.0, 860.0, 980.0],
            "predicted_gross_profit_dollars": [48.0, 62.0, 76.0, 90.0, 108.0],
            "nearest_archetype_expected_gp": [44.0, 58.0, 70.0, 82.0, 100.0],
            "predicted_sell_through_pct": [0.52, 0.60, 0.66, 0.74, 0.82],
            "nearest_archetype_expected_sell_through": [0.50, 0.58, 0.64, 0.72, 0.80],
            "predicted_overallocation_risk": [0.44, 0.36, 0.28, 0.22, 0.15],
            "nearest_archetype_expected_overallocation_rate": [0.46, 0.38, 0.26, 0.20, 0.14],
            "predicted_underallocation_risk": [0.18, 0.16, 0.14, 0.12, 0.10],
            "nearest_archetype_expected_underallocation_rate": [0.20, 0.18, 0.14, 0.10, 0.08],
            "predicted_stockout_risk": [0.22, 0.20, 0.16, 0.12, 0.10],
            "nearest_archetype_expected_stockout_rate": [0.20, 0.18, 0.15, 0.11, 0.09],
        }
    )


class PromotionDecisionCalibrationTests(unittest.TestCase):
    def test_calibration_derives_threshold_payloads(self) -> None:
        calibration = PromotionDecisionCalibrator().calibrate(_calibration_frame(), minimum_sample_size=2)

        self.assertIn("similarity_threshold_suggestion", calibration.thresholds)
        self.assertIn("sparse_cohort_penalty_curve", calibration.thresholds)
        self.assertIn("disagreement_penalty_cutoffs", calibration.thresholds)
        self.assertGreaterEqual(calibration.thresholds["similarity_threshold_suggestion"], 0.45)
        self.assertLessEqual(calibration.thresholds["row_model_confidence_floor_suggestion"], 0.80)
        self.assertGreaterEqual(
            calibration.thresholds["minimum_archetype_sample_size_breakpoints"]["stable"],
            calibration.thresholds["minimum_archetype_sample_size_breakpoints"]["developing"],
        )

    def test_calibration_handles_zero_sample_size_rows(self) -> None:
        frame = _calibration_frame()
        frame["nearest_archetype_sample_size"] = 0

        calibration = PromotionDecisionCalibrator().calibrate(frame, minimum_sample_size=3)

        breakpoints = calibration.thresholds["minimum_archetype_sample_size_breakpoints"]
        self.assertEqual(breakpoints["critical"], 3)
        self.assertEqual(breakpoints["developing"], 4)
        self.assertEqual(breakpoints["stable"], 5)
