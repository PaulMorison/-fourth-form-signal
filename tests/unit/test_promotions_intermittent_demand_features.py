from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.feature_engineering.demand.ft_intermittent_demand import (  # noqa: E402
    INTERMITTENT_DEMAND_FEATURE_COLUMNS,
    apply_ft_intermittent_demand,
)


def _row(
    *,
    pre_56d_units: float,
    pre_28d_units: float,
    pre_56d_days_with_sales: float,
    pre_28d_days_with_sales: float,
    pre_7d_days_with_sales: float = 0.0,
    pre_56d_avg_daily_units: float = 1.0,
    pre_56d_std_daily_units: float = 0.5,
) -> dict[str, object]:
    return {
        "pre_56d_units": pre_56d_units,
        "pre_28d_units": pre_28d_units,
        "pre_56d_days_with_sales": pre_56d_days_with_sales,
        "pre_28d_days_with_sales": pre_28d_days_with_sales,
        "pre_7d_days_with_sales": pre_7d_days_with_sales,
        "pre_56d_avg_daily_units": pre_56d_avg_daily_units,
        "pre_56d_std_daily_units": pre_56d_std_daily_units,
    }


class IntermittentDemandFeaturesTests(unittest.TestCase):
    def test_dense_steady_seller_is_not_intermittent(self) -> None:
        # 50/56 days had a sale, ~1 unit/day -> dense, NOT intermittent.
        frame = pd.DataFrame([_row(
            pre_56d_units=56.0, pre_28d_units=28.0,
            pre_56d_days_with_sales=50.0, pre_28d_days_with_sales=25.0,
            pre_7d_days_with_sales=6.0,
            pre_56d_avg_daily_units=1.0, pre_56d_std_daily_units=0.2,
        )])
        out = apply_ft_intermittent_demand(frame)
        self.assertEqual(out.iloc[0]["feature_intermittent_demand_flag"], 0.0)
        self.assertGreaterEqual(out.iloc[0]["feature_sales_day_density_56d"], 0.85)

    def test_sparse_seller_is_intermittent_and_sparse(self) -> None:
        # 5/56 days had a sale, ~1 unit each -> intermittent + sparse-repeat.
        frame = pd.DataFrame([_row(
            pre_56d_units=5.0, pre_28d_units=2.0,
            pre_56d_days_with_sales=5.0, pre_28d_days_with_sales=2.0,
            pre_7d_days_with_sales=0.0,
            pre_56d_avg_daily_units=0.09, pre_56d_std_daily_units=0.3,
        )])
        out = apply_ft_intermittent_demand(frame)
        self.assertEqual(out.iloc[0]["feature_intermittent_demand_flag"], 1.0)
        self.assertEqual(out.iloc[0]["feature_sparse_repeat_purchase_flag"], 1.0)
        self.assertLessEqual(out.iloc[0]["feature_sales_day_density_56d"], 0.25)

    def test_zero_history_does_not_crash_and_density_is_zero(self) -> None:
        frame = pd.DataFrame([_row(
            pre_56d_units=0.0, pre_28d_units=0.0,
            pre_56d_days_with_sales=0.0, pre_28d_days_with_sales=0.0,
        )])
        out = apply_ft_intermittent_demand(frame)
        row = out.iloc[0]
        self.assertEqual(row["feature_sales_day_density_56d"], 0.0)
        self.assertEqual(row["feature_sales_day_density_28d"], 0.0)

    def test_all_declared_columns_emitted(self) -> None:
        frame = pd.DataFrame([_row(
            pre_56d_units=10.0, pre_28d_units=5.0,
            pre_56d_days_with_sales=10.0, pre_28d_days_with_sales=5.0,
        )])
        out = apply_ft_intermittent_demand(frame)
        for column_name in INTERMITTENT_DEMAND_FEATURE_COLUMNS:
            self.assertIn(column_name, out.columns)


if __name__ == "__main__":
    unittest.main()
