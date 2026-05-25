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
from state.promotions.feature_engineering.demand.ft_discount_elasticity import (  # noqa: E402
    DISCOUNT_ELASTICITY_FEATURE_COLUMNS,
    apply_ft_discount_elasticity,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


def _elasticity_row(
    *,
    promotion_row_key: str,
    promotion_start_date_date: str,
    promotional_end_date_date: str,
    discount_percent: float,
    target_actual_units_sold: float,
    store_number_key: int = 1,
    sku_number_key: int = 1001,
    baseline_expected_units: float = 100.0,
) -> dict[str, object]:
    return {
        "promotion_row_key": promotion_row_key,
        "promotion_start_date_date": promotion_start_date_date,
        "promotional_end_date_date": promotional_end_date_date,
        "store_number_key": store_number_key,
        "sku_number_key": sku_number_key,
        "discount_percent": discount_percent,
        "baseline_expected_units": baseline_expected_units,
        "target_actual_units_sold": target_actual_units_sold,
    }


class PromotionDiscountElasticityTests(unittest.TestCase):
    def test_discount_elasticity_uses_prior_completed_store_sku_history(self) -> None:
        candidate = pd.DataFrame(
            [
                _elasticity_row(
                    promotion_row_key="candidate",
                    promotion_start_date_date="2024-09-01",
                    promotional_end_date_date="2024-09-14",
                    discount_percent=30.0,
                    target_actual_units_sold=0.0,
                )
            ]
        )
        history = pd.DataFrame(
            [
                _elasticity_row(
                    promotion_row_key="hist-1",
                    promotion_start_date_date="2024-05-01",
                    promotional_end_date_date="2024-05-14",
                    discount_percent=10.0,
                    target_actual_units_sold=110.0,
                ),
                _elasticity_row(
                    promotion_row_key="hist-2",
                    promotion_start_date_date="2024-06-01",
                    promotional_end_date_date="2024-06-14",
                    discount_percent=20.0,
                    target_actual_units_sold=130.0,
                ),
                _elasticity_row(
                    promotion_row_key="hist-3",
                    promotion_start_date_date="2024-07-01",
                    promotional_end_date_date="2024-07-14",
                    discount_percent=30.0,
                    target_actual_units_sold=160.0,
                ),
            ]
        )

        result = apply_ft_discount_elasticity(candidate, reference_frame=history)

        self.assertEqual(
            list(DISCOUNT_ELASTICITY_FEATURE_COLUMNS),
            [column_name for column_name in DISCOUNT_ELASTICITY_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertAlmostEqual(result.loc[0, "feature_discount_response_slope"], 2.5)
        self.assertAlmostEqual(result.loc[0, "feature_discount_elasticity_estimate"], 0.75)
        self.assertAlmostEqual(result.loc[0, "feature_discount_elasticity_abs"], 0.75)
        self.assertGreater(result.loc[0, "feature_discount_elasticity_confidence_score"], 0.30)
        self.assertGreater(result.loc[0, "feature_discount_response_r_squared"], 0.95)
        self.assertAlmostEqual(result.loc[0, "feature_discount_response_event_count"], 3.0)
        self.assertAlmostEqual(result.loc[0, "feature_discount_response_direction_consistent_flag"], 1.0)
        self.assertGreater(result.loc[0, "feature_discount_response_instability_score"], 0.0)

    def test_discount_elasticity_contract_is_registered_model_use_output(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertTrue(set(DISCOUNT_ELASTICITY_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(DISCOUNT_ELASTICITY_FEATURE_COLUMNS).issubset(default_model_use_columns))
        self.assertIn("feature_discount_elasticity_confidence_score", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_discount_response_direction_consistent_flag", BOUNDED_ZERO_ONE_COLUMNS)


if __name__ == "__main__":
    unittest.main()