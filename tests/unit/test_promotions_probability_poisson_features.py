from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.feature_engineering.demand.probability.ft_probability_poisson_features import (  # noqa: E402
    build_probability_poisson_features,
)


class ProbabilityPoissonFeatureTests(unittest.TestCase):
    def test_stable_low_volume_history_emits_new_poisson_contract(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "probability_same_or_better_event_count": 4.0,
                    "probability_same_or_better_units_mean": 1.5,
                    "probability_same_or_better_units_variance": 1.25,
                    "probability_order_threshold_units": 2.0,
                }
            ]
        )

        features = build_probability_poisson_features(summary).iloc[0]

        self.assertAlmostEqual(features["feature_probability_poisson_expected_units"], 1.5)
        self.assertAlmostEqual(
            features["feature_probability_poisson_zero_sale_probability"],
            np.exp(-1.5),
            places=6,
        )
        self.assertAlmostEqual(
            features["feature_probability_poisson_one_or_more_sale_probability"],
            1.0 - np.exp(-1.5),
            places=6,
        )
        self.assertAlmostEqual(
            features["feature_probability_poisson_tail_probability"],
            0.4421746,
            places=6,
        )
        self.assertGreaterEqual(
            features["feature_probability_poisson_overallocation_risk_score"],
            features["feature_probability_poisson_zero_sale_probability"],
        )

    def test_overdispersed_history_leaves_new_poisson_outputs_blank(self) -> None:
        summary = pd.DataFrame(
            [
                {
                    "probability_same_or_better_event_count": 4.0,
                    "probability_same_or_better_units_mean": 3.0,
                    "probability_same_or_better_units_variance": 12.0,
                    "probability_order_threshold_units": 4.0,
                }
            ]
        )

        features = build_probability_poisson_features(summary).iloc[0]

        self.assertTrue(pd.isna(features["feature_probability_poisson_expected_units"]))
        self.assertTrue(pd.isna(features["feature_probability_poisson_zero_sale_probability"]))
        self.assertTrue(pd.isna(features["feature_probability_poisson_tail_probability"]))


if __name__ == "__main__":
    unittest.main()