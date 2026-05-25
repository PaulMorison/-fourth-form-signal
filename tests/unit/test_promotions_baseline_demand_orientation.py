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
from state.promotions.feature_engineering.demand.ft_baseline_demand_orientation import (  # noqa: E402
    BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS,
    apply_ft_baseline_demand_orientation,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


def _baseline_row(
    *,
    promotion_row_key: str,
    promotion_start_date_date: str,
    promotional_end_date_date: str,
    store_number_key: int = 1,
    sku_number_key: int = 1001,
    pre_28d_units: float = 56.0,
    feature_non_promo_units_56d: float = 84.0,
    baseline_daily_units: float = 3.0,
    pre_56d_avg_daily_units: float = 1.5,
    pre_28d_std_daily_units: float = 0.5,
    pre_56d_std_daily_units: float = 0.75,
    pre_7d_days_with_sales: float = 7.0,
    pre_28d_days_with_sales: float = 20.0,
    pre_56d_days_with_sales: float = 30.0,
) -> dict[str, object]:
    return {
        "promotion_row_key": promotion_row_key,
        "promotion_start_date_date": promotion_start_date_date,
        "promotional_end_date_date": promotional_end_date_date,
        "store_number_key": store_number_key,
        "sku_number_key": sku_number_key,
        "pre_28d_units": pre_28d_units,
        "feature_non_promo_units_56d": feature_non_promo_units_56d,
        "baseline_daily_units": baseline_daily_units,
        "pre_56d_avg_daily_units": pre_56d_avg_daily_units,
        "pre_28d_std_daily_units": pre_28d_std_daily_units,
        "pre_56d_std_daily_units": pre_56d_std_daily_units,
        "pre_7d_days_with_sales": pre_7d_days_with_sales,
        "pre_28d_days_with_sales": pre_28d_days_with_sales,
        "pre_56d_days_with_sales": pre_56d_days_with_sales,
    }


class PromotionBaselineDemandOrientationTests(unittest.TestCase):
    def test_baseline_orientation_emits_non_promo_level_and_trend_features(self) -> None:
        candidate = pd.DataFrame(
            [
                _baseline_row(
                    promotion_row_key="candidate",
                    promotion_start_date_date="2024-09-01",
                    promotional_end_date_date="2024-09-14",
                )
            ]
        )
        history = pd.DataFrame(
            [
                _baseline_row(
                    promotion_row_key="hist-1",
                    promotion_start_date_date="2024-08-01",
                    promotional_end_date_date="2024-08-15",
                    pre_56d_avg_daily_units=1.4,
                ),
                _baseline_row(
                    promotion_row_key="hist-2",
                    promotion_start_date_date="2024-07-01",
                    promotional_end_date_date="2024-07-15",
                    pre_56d_avg_daily_units=1.6,
                ),
            ]
        )

        result = apply_ft_baseline_demand_orientation(candidate, reference_frame=history)

        self.assertEqual(
            list(BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS),
            [column_name for column_name in BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_30d_avg_daily_units"], 62.0 / 30.0)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_56d_avg_daily_units"], 1.5)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_84d_avg_daily_units"], 1.5)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_30d_std_daily_units"], 0.5)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_56d_std_daily_units"], 0.75)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_base_trend_30d_vs_56d"], (62.0 / 30.0 - 1.5) / 1.5)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_base_trend_30d_vs_84d"], (62.0 / 30.0 - 1.5) / 1.5)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_days_with_sales_ratio_30d"], 22.0 / 30.0)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_days_with_sales_ratio_56d"], 30.0 / 56.0)
        self.assertGreater(result.loc[0, "feature_non_promo_recent_acceleration_score"], 0.05)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_base_demand_growing_flag"], 1.0)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_history_available_flag"], 1.0)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_low_history_flag"], 0.0)
        self.assertAlmostEqual(result.loc[0, "feature_non_promo_stable_history_flag"], 1.0)

    def test_baseline_orientation_contract_is_registered_model_use_output(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertTrue(set(BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS).issubset(default_model_use_columns))
        self.assertIn("feature_non_promo_base_demand_growing_flag", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_non_promo_stable_history_flag", BOUNDED_ZERO_ONE_COLUMNS)


if __name__ == "__main__":
    unittest.main()