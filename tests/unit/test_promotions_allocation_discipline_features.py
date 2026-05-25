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
from models.promotions.allocation_calibration import apply_allocation_aware_units_cap  # noqa: E402
from state.promotions.feature_engineering.demand.ft_allocation_discipline import (  # noqa: E402
    ALLOCATION_DISCIPLINE_FEATURE_COLUMNS,
    apply_ft_allocation_discipline,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


class PromotionAllocationDisciplineFeatureTests(unittest.TestCase):
    def test_allocation_discipline_features_price_probability_backed_excess(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [120.0, 50.0, 120.0],
                "effective_cost_per_unit": [2.5, 3.0, 4.0],
                "feature_baseline_units_expected_promo_window": [20.0, 20.0, 20.0],
                "feature_probability_expected_units_consensus": [80.0, 100.0, 80.0],
                "feature_probability_uplift_supported_units": [40.0, 40.0, 40.0],
                "feature_probability_uplift_upper_units": [55.0, 50.0, 55.0],
                "feature_probability_uplift_confidence": [0.8, 0.7, 0.9],
                "feature_window_blend_conflict_score": [0.1, 0.2, 0.1],
                "feature_probability_demand_confidence_score": [0.75, 0.60, 0.90],
                "feature_probability_model_use_flag": [1.0, 1.0, 0.0],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        self.assertEqual(
            list(ALLOCATION_DISCIPLINE_FEATURE_COLUMNS),
            [column_name for column_name in ALLOCATION_DISCIPLINE_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertAlmostEqual(result.loc[0, "feature_allocation_vs_probability_expected_units_ratio"], 1.5)
        self.assertAlmostEqual(result.loc[0, "feature_allocated_units_minus_probability_expected_units"], 40.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_expected_excess_units"], 40.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_expected_excess_units_pct"], 0.5)
        self.assertAlmostEqual(result.loc[0, "feature_probability_expected_sell_through_pct"], 80.0 / 120.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_excess_capital_at_risk"], 100.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_allocation_discipline_score"], 0.27)
        self.assertAlmostEqual(result.loc[0, "feature_allocation_vs_uplift_supported_units_ratio"], 2.0)
        self.assertAlmostEqual(result.loc[0, "feature_allocated_units_minus_uplift_supported_units"], 60.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_supported_excess_units"], 45.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_supported_excess_units_pct"], 45.0 / 75.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_supported_sell_through_pct"], 0.5)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_supported_excess_capital_at_risk"], 112.5)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_allocation_discipline_score"], 0.27)
        self.assertAlmostEqual(result.loc[1, "feature_probability_expected_excess_units"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_probability_expected_sell_through_pct"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_uplift_supported_excess_units"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_uplift_supported_sell_through_pct"], 1.0)
        self.assertTrue(result.loc[2, list(ALLOCATION_DISCIPLINE_FEATURE_COLUMNS)].isna().all())

    def test_allocation_discipline_features_are_registered_model_use_outputs(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertTrue(set(ALLOCATION_DISCIPLINE_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(ALLOCATION_DISCIPLINE_FEATURE_COLUMNS).issubset(default_model_use_columns))
        self.assertIn("feature_probability_expected_sell_through_pct", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_probability_allocation_discipline_score", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_uplift_supported_sell_through_pct", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_uplift_allocation_discipline_score", BOUNDED_ZERO_ONE_COLUMNS)

    def test_allocation_aware_units_cap_is_one_way_and_evidence_gated(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_baseline_units_expected_promo_window": [20.0, 20.0, 20.0, 20.0],
                "feature_probability_expected_units_consensus": [60.0, 60.0, 60.0, 60.0],
                "feature_probability_uplift_supported_units": [30.0, 30.0, 30.0, 30.0],
                "feature_probability_uplift_upper_units": [40.0, 40.0, 40.0, 40.0],
                "feature_probability_tail_risk_consensus": [0.0, 0.0, 0.0, 0.0],
                "feature_probability_demand_confidence_score": [1.0, 1.0, 1.0, 1.0],
                "feature_probability_uplift_confidence": [1.0, 1.0, 1.0, 1.0],
                "feature_probability_allocation_discipline_score": [0.2, 0.1, 0.2, 0.2],
                "feature_uplift_allocation_discipline_score": [0.2, 0.1, 0.2, 0.2],
                "feature_probability_model_use_flag": [1.0, 1.0, 0.0, 1.0],
            }
        )
        raw_prediction = pd.Series([90.0, 90.0, 90.0, 50.0], index=frame.index)

        capped = apply_allocation_aware_units_cap(frame, raw_prediction)

        self.assertEqual(capped.tolist(), [60.0, 90.0, 90.0, 50.0])


if __name__ == "__main__":
    unittest.main()