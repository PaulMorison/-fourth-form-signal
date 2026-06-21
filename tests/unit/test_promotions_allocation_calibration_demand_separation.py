from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.allocation_calibration import compute_allocation_aware_cap_units  # noqa: E402


class AllocationCalibrationDemandSeparationTests(unittest.TestCase):
    def test_allocation_cap_units_separate_from_calibrated_demand(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_baseline_units_expected_promo_window": [20.0],
                "feature_probability_expected_units_consensus": [60.0],
                "feature_probability_uplift_supported_units": [30.0],
                "feature_probability_uplift_upper_units": [40.0],
                "feature_probability_tail_risk_consensus": [0.0],
                "feature_probability_demand_confidence_score": [1.0],
                "feature_probability_uplift_confidence": [1.0],
                "feature_probability_allocation_discipline_score": [0.2],
                "feature_uplift_allocation_discipline_score": [0.2],
                "feature_probability_model_use_flag": [1.0],
            }
        )
        raw = pd.Series([90.0], index=frame.index)
        calibrated_demand = raw.clip(lower=0.0)
        allocation_cap = compute_allocation_aware_cap_units(frame, raw)

        self.assertEqual(float(calibrated_demand.iloc[0]), 90.0)
        self.assertEqual(float(allocation_cap.iloc[0]), 60.0)
        self.assertGreater(float(calibrated_demand.iloc[0]), float(allocation_cap.iloc[0]))


if __name__ == "__main__":
    unittest.main()
