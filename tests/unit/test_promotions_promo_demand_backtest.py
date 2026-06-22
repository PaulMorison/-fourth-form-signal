from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.promo_demand_backtest import (  # noqa: E402
    BACKTEST_OUTPUT_COLUMNS,
    assign_error_bucket,
    build_promo_demand_backtest_frame,
    compute_accuracy_summary,
    compute_wape,
    dedupe_promo_sku_events,
    recommend_customer_release,
)


def _sample_source() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "store_number": [772, 772, 772, 772],
            "sku_number": [100, 200, 300, 400],
            "promotion_id": ["p1", "p1", "p2", "p2"],
            "promotion_name": ["Spring", "Spring", "Winter", "Winter"],
            "promotion_start_date": ["2024-01-01", "2024-01-01", "2024-02-01", "2024-02-01"],
            "promotional_end_date": ["2024-01-07", "2024-01-07", "2024-02-07", "2024-02-07"],
            "sku_description": ["A", "B", "C", "D"],
            "actual_units_sold_promo": [10.0, 0.0, 20.0, 5.0],
            "discount_percent": [15.0, 15.0, 25.0, 25.0],
            "promo_days": [7, 7, 7, 7],
            "feature_historical_units_same_discount_avg": [8.0, 0.0, 18.0, 4.0],
            "feature_historical_units_same_discount_count": [3, 0, 4, 2],
            "feature_historical_units_same_discount_max": [12.0, 0.0, 22.0, 6.0],
            "feature_historical_units_same_discount_min": [5.0, 0.0, 14.0, 3.0],
            "feature_historical_units_same_discount_std": [2.0, 0.0, 3.0, 1.0],
            "feature_non_promo_avg_daily_units": [1.0, 0.5, 2.0, 0.5],
            "feature_lead_up_avg_daily_units": [1.2, 0.0, 2.5, 0.6],
            "feature_promo_uplift_ratio": [1.4, 1.0, 1.3, 1.1],
            "feature_promo_confidence_score": [0.8, 0.2, 0.7, 0.5],
            "feature_stock_momentum_ratio": [1.0, 1.0, 1.0, 1.0],
            "store_adjusted_qty": [12.0, 2.0, 18.0, 8.0],
            "promo_effective_cost": [5.0, 5.0, 4.0, 4.0],
            "promo_gm_unit": [3.0, 3.0, 2.5, 2.5],
            "total_stock_available": [12.0, 2.0, 18.0, 8.0],
        }
    )


class PromoDemandBacktestTests(unittest.TestCase):
    def test_wape_mae_rmse_and_mape(self) -> None:
        actual = pd.Series([10.0, 20.0, 0.0])
        forecast = pd.Series([12.0, 15.0, 5.0])
        backtest = pd.DataFrame(
            {
                "actual_units_sold_promo": actual,
                "model_expected_units_total_promo": forecast,
                "baseline_expected_units_total_promo": [11.0, 22.0, 1.0],
                "historical_proxy_expected_units_total_promo": [10.0, 18.0, 2.0],
                "forecast_error_units": forecast - actual,
                "forecast_abs_error_units": (forecast - actual).abs(),
                "forecast_abs_pct_error": [20.0, 25.0, 0.0],
                "model_bias_units": forecast - actual,
                "model_beats_baseline_flag": [1, 1, 0],
                "model_beats_historical_proxy_flag": [0, 1, 0],
                "promo_demand_release_ready_flag": ["YES", "YES", "NO"],
                "promo_demand_source_quality": ["HIGH", "MEDIUM", "UNSAFE"],
                "stockout_suspected_flag": [0, 0, 0],
                "leftover_units_estimate": [0.0, 0.0, 0.0],
            }
        )
        summary = compute_accuracy_summary(backtest)
        total = summary[summary["segment"].eq("total")].iloc[0]
        self.assertAlmostEqual(float(total["mae"]), 4.0, places=4)
        self.assertAlmostEqual(float(total["rmse"]), np.sqrt((4 + 25 + 25) / 3), places=4)
        self.assertAlmostEqual(compute_wape(actual, forecast), (2 + 5 + 5) / 30.0, places=4)
        self.assertAlmostEqual(float(total["mape"]), 22.5, places=4)
        self.assertAlmostEqual(float(total["bias_pct"]), (2 - 5 + 5) / 30.0 * 100.0, places=4)

    def test_backtest_frame_integrity(self) -> None:
        source = _sample_source()
        duped = pd.concat([source, source.iloc[[0]]], ignore_index=True)
        backtest = build_promo_demand_backtest_frame(duped)
        self.assertEqual(len(backtest), 4)
        self.assertTrue(set(BACKTEST_OUTPUT_COLUMNS).issubset(backtest.columns))
        self.assertFalse(backtest[list(BACKTEST_OUTPUT_COLUMNS)].select_dtypes(include="number").isna().any().any())
        keys = ["store_number", "sku_number", "promotion_start_date"]
        self.assertEqual(backtest.duplicated(subset=keys).sum(), 0)

    def test_comparison_and_risk_flags(self) -> None:
        backtest = build_promo_demand_backtest_frame(_sample_source())
        row = backtest[backtest["sku_number"].astype(str).eq("100")].iloc[0]
        self.assertIn(int(row["model_beats_baseline_flag"]), (0, 1))
        self.assertIn(int(row["model_beats_historical_proxy_flag"]), (0, 1))
        self.assertGreaterEqual(float(row["under_order_risk_units"]), 0.0)
        self.assertGreaterEqual(float(row["over_order_risk_units"]), 0.0)

    def test_stockout_and_leftover_buckets(self) -> None:
        stockout_row = pd.Series(
            {
                "actual_units_sold_promo": 10.0,
                "model_expected_units_total_promo": 9.0,
                "forecast_abs_pct_error": 10.0,
                "stockout_suspected_flag": 1,
                "leftover_units_estimate": 0.0,
            }
        )
        leftover_row = pd.Series(
            {
                "actual_units_sold_promo": 2.0,
                "model_expected_units_total_promo": 8.0,
                "forecast_abs_pct_error": 200.0,
                "stockout_suspected_flag": 0,
                "leftover_units_estimate": 10.0,
            }
        )
        self.assertEqual(assign_error_bucket(stockout_row), "stockout_suspected")
        self.assertEqual(assign_error_bucket(leftover_row), "leftover_suspected")

    def test_governance_no_customer_release_when_poor(self) -> None:
        backtest = pd.DataFrame({"promo_demand_source_quality": ["HIGH"], "promo_demand_release_ready_flag": ["YES"]})
        accuracy = pd.DataFrame(
            [
                {
                    "segment": "total",
                    "wape": 1.5,
                    "baseline_wape": 0.5,
                    "model_beats_baseline_pct": 30.0,
                    "bias_pct": 5.0,
                },
                {"segment": "release_ready=YES", "wape": 1.2, "baseline_wape": 0.5},
            ]
        )
        economic = pd.DataFrame([{"metric": "net_value_proxy", "value": 100.0}])
        rec, _ = recommend_customer_release(backtest, accuracy, economic)
        self.assertEqual(rec, "NO_RELEASE")

    def test_governance_no_release_when_unsafe_dominates(self) -> None:
        backtest = pd.DataFrame(
            {
                "promo_demand_source_quality": ["UNSAFE"] * 8 + ["HIGH"] * 2,
                "promo_demand_release_ready_flag": ["NO"] * 10,
            }
        )
        accuracy = pd.DataFrame(
            [
                {
                    "segment": "total",
                    "wape": 0.4,
                    "baseline_wape": 0.7,
                    "model_beats_baseline_pct": 60.0,
                    "bias_pct": 5.0,
                },
                {"segment": "release_ready=YES", "wape": 0.35, "baseline_wape": 0.6},
            ]
        )
        economic = pd.DataFrame([{"metric": "net_value_proxy", "value": 1000.0}])
        rec, blocker = recommend_customer_release(backtest, accuracy, economic)
        self.assertIn(rec, {"NO_RELEASE", "INTERNAL_SHADOW_ONLY"})
        self.assertNotEqual(rec, "CUSTOMER_RELEASE_READY")

    def test_model_beats_baseline_flag(self) -> None:
        backtest = build_promo_demand_backtest_frame(_sample_source())
        expected = (
            backtest["forecast_abs_error_units"].lt(backtest["baseline_abs_error_units"]).astype(int)
        )
        pd.testing.assert_series_equal(backtest["model_beats_baseline_flag"], expected, check_names=False)

    def test_governance_limited_release_only_for_better_ready_subset(self) -> None:
        backtest = pd.DataFrame(
            {
                "promo_demand_source_quality": ["HIGH", "MEDIUM", "UNSAFE"],
                "promo_demand_release_ready_flag": ["YES", "YES", "NO"],
            }
        )
        accuracy = pd.DataFrame(
            [
                {
                    "segment": "total",
                    "wape": 0.55,
                    "baseline_wape": 0.65,
                    "model_beats_baseline_pct": 58.0,
                    "bias_pct": 8.0,
                },
                {
                    "segment": "release_ready=YES",
                    "wape": 0.45,
                    "baseline_wape": 0.60,
                },
            ]
        )
        economic = pd.DataFrame([{"metric": "net_value_proxy", "value": 5000.0}])
        rec, _ = recommend_customer_release(backtest, accuracy, economic)
        self.assertIn(rec, {"LIMITED_RELEASE_HIGH_CONFIDENCE_ONLY", "INTERNAL_SHADOW_ONLY"})


if __name__ == "__main__":
    unittest.main()
