from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.model_input_quality import iter_default_model_use_feature_columns  # noqa: E402
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402
from state.promotions.feature_engineering.stock.ft_target_stock_logic import (  # noqa: E402
    TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS,
    TARGET_STOCK_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_target_stock_logic,
)


class PromotionTargetStockLogicTests(unittest.TestCase):
    def test_promotion_period_days_flow_from_actual_dates(self) -> None:
        frame = _base_frame(
            promotion_start_date_date=["2024-06-01", "2024-06-01", "2024-06-01", "2024-06-01"],
            promotional_end_date_date=["2024-06-07", "2024-06-01", "2024-06-14", "2024-06-30"],
            baseline_daily_units=[0.2, 0.2, 0.2, 0.2],
            feature_historical_promo_events_same_discount=[1.0, 1.0, 1.0, 1.0],
            feature_historical_promo_events_same_or_better_discount=[1.0, 1.0, 1.0, 1.0],
            feature_promo_history_evidence_strength=[0.5, 0.5, 0.5, 0.5],
        )

        result = apply_ft_target_stock_logic(frame)

        self.assertEqual(result["feature_promo_period_days"].tolist(), [7.0, 1.0, 14.0, 30.0])
        self.assertEqual(result["feature_promo_period_target_units"].round(1).tolist(), [1.4, 0.2, 2.8, 6.0])
        self.assertTrue((result["feature_day_one_target_stock_units"] >= result["feature_end_of_promo_target_units"]).all())

    def test_no_promo_history_uses_floor_one(self) -> None:
        frame = _base_frame(
            baseline_daily_units=[0.2],
            feature_historical_promo_events_same_discount=[0.0],
            feature_historical_promo_events_same_or_better_discount=[0.0],
            feature_promo_history_evidence_strength=[0.0],
        )

        result = apply_ft_target_stock_logic(frame)

        self.assertEqual(result.loc[0, "feature_no_promo_history_flag"], 1.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_floor_units"], 1.0)
        self.assertEqual(result.loc[0, "feature_trust_floor_units_dynamic"], 1.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_units"], 1.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_regime"], "promo_floor_1_low_history")
        self.assertGreaterEqual(result.loc[0, "feature_units_needed_for_trust_floor"], 1.0)
        self.assertEqual(result.loc[0, "feature_target_units_below_current_logic"], 1.0)

    def test_default_history_uses_floor_two(self) -> None:
        frame = _base_frame(
            baseline_daily_units=[0.2],
            feature_historical_promo_events_same_discount=[2.0],
            feature_historical_promo_events_same_or_better_discount=[2.0],
            feature_promo_history_evidence_strength=[0.5],
        )

        result = apply_ft_target_stock_logic(frame)

        self.assertEqual(result.loc[0, "feature_no_promo_history_flag"], 0.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_floor_units"], 2.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_units"], 2.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_regime"], "promo_floor_2")

    def test_high_underlying_demand_uses_fourteen_day_end_cover(self) -> None:
        frame = _base_frame(
            baseline_daily_units=[1.5],
            feature_historical_promo_events_same_discount=[2.0],
            feature_historical_promo_events_same_or_better_discount=[2.0],
            feature_promo_history_evidence_strength=[0.5],
        )

        result = apply_ft_target_stock_logic(frame)

        self.assertEqual(result.loc[0, "feature_high_underlying_demand_flag"], 1.0)
        self.assertEqual(result.loc[0, "feature_high_base_demand_end_cover_flag"], 1.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_units"], 21.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_days_cover"], 14.0)
        self.assertGreater(result.loc[0, "feature_units_needed_for_high_demand_cover"], 0.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_regime"], "promo_end_14d_cover_high_base_demand")

    def test_month_end_cashflow_caps_to_seven_days_cover_preserving_floor(self) -> None:
        frame = _base_frame(
            promotion_start_date_date=["2024-06-20", "2024-06-20"],
            promotional_end_date_date=["2024-06-28", "2024-06-28"],
            baseline_daily_units=[1.5, 0.2],
            feature_historical_promo_events_same_discount=[2.0, 2.0],
            feature_historical_promo_events_same_or_better_discount=[2.0, 2.0],
            feature_promo_history_evidence_strength=[0.5, 0.5],
        )

        result = apply_ft_target_stock_logic(frame)

        self.assertEqual(result.loc[0, "feature_month_end_cash_runoff_pressure_flag"], 1.0)
        self.assertEqual(result.loc[0, "feature_month_end_inventory_efficiency_target"], 10.5)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_units"], 10.5)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_days_cover"], 7.0)
        self.assertGreaterEqual(result.loc[0, "feature_excess_month_end_capital_drag"], 0.0)
        self.assertLessEqual(result.loc[0, "feature_cashflow_efficiency_score"], 1.0)
        self.assertEqual(result.loc[0, "feature_end_of_promo_target_regime"], "month_end_runoff_max_7d_cover")
        self.assertEqual(result.loc[1, "feature_end_of_promo_target_units"], 2.0)
        self.assertEqual(result.loc[1, "feature_end_of_promo_target_floor_units"], 2.0)

    def test_target_stock_columns_are_registered_and_regime_is_review_only(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertTrue(set(TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(TARGET_STOCK_MODEL_USE_FEATURE_COLUMNS).issubset(default_model_use_columns))
        self.assertTrue(set(TARGET_STOCK_REVIEW_ONLY_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(TARGET_STOCK_REVIEW_ONLY_FEATURE_COLUMNS).isdisjoint(default_model_use_columns))


def _base_frame(**overrides: list[object]) -> pd.DataFrame:
    row_count = max((len(values) for values in overrides.values()), default=1)
    data: dict[str, list[object]] = {
        "promotion_start_date_date": ["2024-06-01"] * row_count,
        "promotional_end_date_date": ["2024-06-14"] * row_count,
        "baseline_daily_units": [0.2] * row_count,
        "feature_historical_promo_events_same_discount": [1.0] * row_count,
        "feature_historical_promo_events_same_or_better_discount": [1.0] * row_count,
        "feature_promo_history_evidence_strength": [0.5] * row_count,
        "feature_base_soh_trust_floor_units": [2.0] * row_count,
    }
    for column_name, values in overrides.items():
        data[column_name] = values
    return pd.DataFrame(data)


if __name__ == "__main__":
    unittest.main()