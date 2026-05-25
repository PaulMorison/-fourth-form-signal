from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.model_input_quality import (  # noqa: E402
    BOUNDED_ZERO_ONE_COLUMNS,
    iter_default_model_use_feature_columns,
)
from state.promotions.feature_engineering.demand.ft_uplift_decomposition import (  # noqa: E402
    UPLIFT_DECOMPOSITION_FEATURE_COLUMNS,
    apply_ft_uplift_decomposition,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


class PromotionUpliftDecompositionTests(unittest.TestCase):
    def test_uplift_decomposition_separates_baseline_from_supported_uplift(self) -> None:
        frame = pd.DataFrame(
            {
                "promotion_row_key": ["candidate"],
                "live_promo_window_days": [14.0],
                "feature_non_promo_30d_avg_daily_units": [2.0],
                "feature_same_discount_prior_event_count": [2.0],
                "feature_same_discount_prior_uplift_ratio_avg": [0.5],
                "feature_same_discount_prior_uplift_ratio_median": [0.6],
                "feature_same_discount_prior_uplift_ratio_std": [0.1],
                "feature_same_discount_history_available_flag": [1.0],
                "feature_discount_elasticity_estimate": [0.4],
                "feature_discount_elasticity_abs": [0.4],
                "feature_discount_elasticity_confidence_score": [0.6],
                "feature_discount_response_direction_consistent_flag": [1.0],
                "feature_probability_demand_confidence_score": [0.8],
            }
        )

        result = apply_ft_uplift_decomposition(frame)

        self.assertEqual(
            list(UPLIFT_DECOMPOSITION_FEATURE_COLUMNS),
            [column_name for column_name in UPLIFT_DECOMPOSITION_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertAlmostEqual(result.loc[0, "feature_expected_baseline_units_promo_window"], 28.0)
        self.assertAlmostEqual(result.loc[0, "feature_expected_baseline_units_first_7_days"], 14.0)
        self.assertAlmostEqual(result.loc[0, "feature_expected_incremental_uplift_units_same_discount"], 11.2)
        self.assertAlmostEqual(result.loc[0, "feature_expected_incremental_uplift_units_first_7_days"], 5.6)
        self.assertAlmostEqual(result.loc[0, "feature_expected_total_units_from_baseline_plus_uplift"], 39.2)
        self.assertAlmostEqual(result.loc[0, "feature_expected_total_units_first_7_days"], 19.6)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_share_of_total_expected_units"], 11.2 / 39.2)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_support_event_count"], 2.0)
        self.assertGreater(result.loc[0, "feature_uplift_confidence_score"], 0.70)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_instability_score"], 1.0 / 6.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_vs_base_ratio"], 0.4)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_demand_support_flag"], 1.0)

    def test_uplift_decomposition_contract_is_registered_model_use_output(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertTrue(set(UPLIFT_DECOMPOSITION_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(UPLIFT_DECOMPOSITION_FEATURE_COLUMNS).issubset(default_model_use_columns))
        self.assertIn("feature_uplift_confidence_score", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_uplift_share_of_total_expected_units", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_uplift_demand_support_flag", BOUNDED_ZERO_ONE_COLUMNS)


if __name__ == "__main__":
    unittest.main()