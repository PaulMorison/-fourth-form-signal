from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.feature_engineering.targets.ft_target_stockout_flag import (  # noqa: E402
    apply_ft_target_stockout_flag,
)
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class PromotionTargetEngineeringTests(unittest.TestCase):
    def test_targets_capture_stockout_and_overallocation_cases(self) -> None:
        base_frame = build_completed_promotions_base_frame()
        result = PromotionTargetEngineer().engineer(base_frame).frame

        stockout_row = result.loc[result["promotion_row_key"].str.contains("|100|2024-02-01", regex=False)].iloc[0]
        overalloc_row = result.loc[result["promotion_row_key"].str.contains("|100|2024-03-01", regex=False)].iloc[0]

        self.assertEqual(int(stockout_row["target_stockout_flag"]), 1)
        self.assertEqual(int(stockout_row["target_underallocation_flag"]), 1)
        self.assertEqual(int(overalloc_row["target_overallocation_flag"]), 1)
        self.assertGreaterEqual(stockout_row["target_post_promo_followthrough_units"], 0.0)
        self.assertGreater(overalloc_row["target_leftover_stock_pct"], 0.4)

    def test_stockout_ft_module_flags_depletion_and_followthrough_cases(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [100.0, 100.0, 100.0],
                "target_actual_units_sold": [99.0, 65.0, 40.0],
                "target_sell_through_pct": [0.99, 0.91, 0.4],
                "post_14d_units": [0.0, 4.0, 0.0],
            }
        )

        result = apply_ft_target_stockout_flag(frame)

        self.assertListEqual(result["target_stockout_flag"].tolist(), [1, 1, 0])
