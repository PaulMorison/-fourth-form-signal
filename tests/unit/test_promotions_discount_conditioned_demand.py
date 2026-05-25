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
from state.promotions.feature_engineering.demand.ft_discount_conditioned_demand import (  # noqa: E402
    DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS,
    apply_ft_discount_conditioned_demand,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


def _history_row(
    *,
    promotion_row_key: str,
    promotion_start_date_date: str,
    promotional_end_date_date: str,
    store_number_key: int = 1,
    sku_number_key: int = 1001,
    discount_percent: float = 20.0,
    live_promo_window_days: float = 14.0,
    baseline_expected_units: float = 28.0,
    stock_basis_units: float = 50.0,
    target_actual_units_sold: float = 44.0,
) -> dict[str, object]:
    return {
        "promotion_row_key": promotion_row_key,
        "promotion_start_date_date": promotion_start_date_date,
        "promotional_end_date_date": promotional_end_date_date,
        "store_number_key": store_number_key,
        "sku_number_key": sku_number_key,
        "discount_percent": discount_percent,
        "live_promo_window_days": live_promo_window_days,
        "baseline_expected_units": baseline_expected_units,
        "stock_basis_units": stock_basis_units,
        "target_actual_units_sold": target_actual_units_sold,
    }


class PromotionDiscountConditionedDemandTests(unittest.TestCase):
    def test_discount_conditioned_demand_uses_strict_same_discount_history_only(self) -> None:
        candidate = pd.DataFrame(
            [
                _history_row(
                    promotion_row_key="candidate",
                    promotion_start_date_date="2024-09-01",
                    promotional_end_date_date="2024-09-14",
                ),
                _history_row(
                    promotion_row_key="no-history",
                    promotion_start_date_date="2024-09-01",
                    promotional_end_date_date="2024-09-14",
                    sku_number_key=9999,
                ),
            ]
        )
        history = pd.DataFrame(
            [
                _history_row(
                    promotion_row_key="hist-1",
                    promotion_start_date_date="2024-05-01",
                    promotional_end_date_date="2024-05-15",
                    target_actual_units_sold=44.0,
                    stock_basis_units=50.0,
                ),
                _history_row(
                    promotion_row_key="hist-2",
                    promotion_start_date_date="2024-08-01",
                    promotional_end_date_date="2024-08-15",
                    target_actual_units_sold=42.0,
                    stock_basis_units=60.0,
                ),
                _history_row(
                    promotion_row_key="hist-other-discount",
                    promotion_start_date_date="2024-07-01",
                    promotional_end_date_date="2024-07-14",
                    discount_percent=25.0,
                    target_actual_units_sold=55.0,
                    stock_basis_units=70.0,
                ),
            ]
        )

        result = apply_ft_discount_conditioned_demand(candidate, reference_frame=history)

        self.assertEqual(
            list(DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS),
            [column_name for column_name in DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_event_count"], 2.0)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_units_avg"], 43.0)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_units_median"], 43.0)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_units_std"], 1.0)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_sell_through_avg"], 0.79)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_stock_cover_avg"], 17.9545454545)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_uplift_ratio_avg"], 0.5357142857)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_uplift_ratio_median"], 0.5357142857)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_prior_uplift_ratio_std"], 0.0357142857)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_recent_event_count"], 1.0)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_days_since_last_event"], 17.0)
        self.assertAlmostEqual(result.loc[0, "feature_same_discount_history_available_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_same_discount_prior_event_count"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_same_discount_recent_event_count"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_same_discount_history_available_flag"], 0.0)
        self.assertTrue(pd.isna(result.loc[1, "feature_same_discount_prior_units_avg"]))

    def test_discount_conditioned_demand_contract_is_registered_model_use_output(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertTrue(set(DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS).issubset(default_model_use_columns))
        self.assertIn("feature_same_discount_history_available_flag", BOUNDED_ZERO_ONE_COLUMNS)


if __name__ == "__main__":
    unittest.main()