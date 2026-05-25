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
from state.promotions.feature_engineering.demand.ft_demand_uplift import (  # noqa: E402
    DEMAND_UPLIFT_FEATURE_COLUMNS,
    DEMAND_UPLIFT_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_demand_uplift,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


def _promo_row(
    *,
    promotion_row_key: str,
    promotion_start_date_date: str,
    promotional_end_date_date: str,
    store_number_key: int = 1,
    sku_number_key: int = 1001,
    discount_percent: float = 20.0,
    baseline_daily_units: float = 2.0,
    live_promo_window_days: float = 14.0,
    baseline_expected_units: float = 28.0,
    stock_basis_units: float = 50.0,
    target_actual_units_sold: float = 0.0,
    actual_units_sold_first_7_days: float = 0.0,
    feature_probability_expected_units_consensus: float = 40.0,
    feature_probability_tail_risk_consensus: float = 0.1,
    feature_probability_demand_confidence_score: float = 0.8,
    feature_probability_model_use_flag: float = 1.0,
    feature_historical_discount_response_confidence: float = 0.7,
    feature_promo_history_evidence_strength: float = 0.6,
    feature_order_evidence_quality_score: float = 0.65,
    feature_basket_attach_rate: float = 0.4,
    feature_sku_basket_dependency_score: float = 0.5,
    feature_probability_sku_in_multi_item_basket: float = 0.6,
    feature_companion_concentration_index: float = 0.35,
    effective_cost_per_unit: float = 2.5,
    as_of_date: str = "2024-08-28",
) -> dict[str, object]:
    return {
        "promotion_row_key": promotion_row_key,
        "promotion_start_date_date": promotion_start_date_date,
        "promotional_end_date_date": promotional_end_date_date,
        "store_number_key": store_number_key,
        "sku_number_key": sku_number_key,
        "discount_percent": discount_percent,
        "baseline_daily_units": baseline_daily_units,
        "live_promo_window_days": live_promo_window_days,
        "baseline_expected_units": baseline_expected_units,
        "stock_basis_units": stock_basis_units,
        "target_actual_units_sold": target_actual_units_sold,
        "actual_units_sold_first_7_days": actual_units_sold_first_7_days,
        "feature_probability_expected_units_consensus": feature_probability_expected_units_consensus,
        "feature_probability_tail_risk_consensus": feature_probability_tail_risk_consensus,
        "feature_probability_demand_confidence_score": feature_probability_demand_confidence_score,
        "feature_probability_model_use_flag": feature_probability_model_use_flag,
        "feature_historical_discount_response_confidence": feature_historical_discount_response_confidence,
        "feature_promo_history_evidence_strength": feature_promo_history_evidence_strength,
        "feature_order_evidence_quality_score": feature_order_evidence_quality_score,
        "feature_basket_attach_rate": feature_basket_attach_rate,
        "feature_sku_basket_dependency_score": feature_sku_basket_dependency_score,
        "feature_probability_sku_in_multi_item_basket": feature_probability_sku_in_multi_item_basket,
        "feature_companion_concentration_index": feature_companion_concentration_index,
        "effective_cost_per_unit": effective_cost_per_unit,
        "as_of_date": as_of_date,
    }


class PromotionDemandUpliftFeatureTests(unittest.TestCase):
    def test_demand_uplift_features_separate_baseline_and_incremental_promo_demand(self) -> None:
        candidate = pd.DataFrame(
            [
                _promo_row(
                    promotion_row_key="candidate",
                    promotion_start_date_date="2024-09-01",
                    promotional_end_date_date="2024-09-14",
                    target_actual_units_sold=45.0,
                    actual_units_sold_first_7_days=20.0,
                )
            ]
        )
        history = pd.DataFrame(
            [
                _promo_row(
                    promotion_row_key="hist-1",
                    promotion_start_date_date="2024-06-01",
                    promotional_end_date_date="2024-06-14",
                    target_actual_units_sold=44.0,
                    actual_units_sold_first_7_days=22.0,
                ),
                _promo_row(
                    promotion_row_key="hist-2",
                    promotion_start_date_date="2024-07-01",
                    promotional_end_date_date="2024-07-14",
                    discount_percent=25.0,
                    target_actual_units_sold=38.0,
                    actual_units_sold_first_7_days=19.0,
                ),
            ]
        )

        result = apply_ft_demand_uplift(candidate, reference_frame=history)

        self.assertEqual(
            list(DEMAND_UPLIFT_FEATURE_COLUMNS),
            [column_name for column_name in DEMAND_UPLIFT_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertAlmostEqual(result.loc[0, "feature_baseline_units_expected_promo_window"], 28.0)
        self.assertAlmostEqual(result.loc[0, "feature_baseline_units_expected_first_7_days"], 14.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_uplift_supported_units"], 12.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_uplift_upper_units"], 28.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_units_expected_total"], 12.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_units_expected_first_7_days"], 6.0)
        self.assertAlmostEqual(result.loc[0, "feature_actual_units_minus_baseline"], 17.0)
        self.assertAlmostEqual(result.loc[0, "feature_actual_units_minus_baseline_first_7_days"], 6.0)
        self.assertAlmostEqual(result.loc[0, "feature_leadup_units_pressure"], 8.0 / 50.0)
        self.assertAlmostEqual(result.loc[0, "feature_launch_window_units_pressure"], 20.0 / 50.0)
        self.assertAlmostEqual(result.loc[0, "feature_total_promo_units_pressure"], 40.0 / 50.0)
        self.assertGreaterEqual(result.loc[0, "feature_uplift_history_event_count"], 2.0)
        self.assertGreater(result.loc[0, "feature_uplift_confidence_score"], 0.0)

    def test_demand_uplift_features_fail_loud_on_contradictory_baseline_inputs(self) -> None:
        frame = pd.DataFrame(
            [
                _promo_row(
                    promotion_row_key="contradiction",
                    promotion_start_date_date="2024-09-01",
                    promotional_end_date_date="2024-09-14",
                    baseline_expected_units=30.0,
                )
            ]
        )

        with self.assertRaisesRegex(ValueError, "contradictory baseline_expected_units"):
            apply_ft_demand_uplift(frame)

    def test_demand_uplift_legacy_module_is_not_registered_but_shared_outputs_remain_governed(self) -> None:
        registered_module_names = {definition.name for definition in iter_registered_feature_modules()}
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertNotIn("ft_demand_uplift", registered_module_names)
        self.assertTrue(set(DEMAND_UPLIFT_REVIEW_ONLY_FEATURE_COLUMNS).isdisjoint(default_model_use_columns))
        self.assertIn("feature_uplift_confidence_score", default_model_use_columns)
        self.assertIn("feature_uplift_confidence_score", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_uplift_share_of_total_expected_units", BOUNDED_ZERO_ONE_COLUMNS)


if __name__ == "__main__":
    unittest.main()