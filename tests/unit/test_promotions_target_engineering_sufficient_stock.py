from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.sufficient_stock_demand_target import (  # noqa: E402
    APPROVED_TARGET_QUALITY_LABELS,
    SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS,
)
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class PromotionTargetEngineeringSufficientStockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_frame = build_completed_promotions_base_frame()
        self.result = PromotionTargetEngineer().engineer(self.base_frame)

    def test_appends_all_sufficient_stock_target_fields(self) -> None:
        for column_name in SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS:
            self.assertIn(column_name, self.result.frame.columns)

    def test_legacy_target_actual_units_sold_remains_present_and_unchanged(self) -> None:
        self.assertIn("target_actual_units_sold", self.result.target_columns)
        expected = pd.to_numeric(self.base_frame["actual_units_sold"], errors="coerce").clip(lower=0.0)
        pd.testing.assert_series_equal(
            expected.reset_index(drop=True),
            self.result.frame["target_actual_units_sold"].reset_index(drop=True),
            check_names=False,
        )

    def test_new_target_is_not_live_training_target_yet(self) -> None:
        self.assertEqual(self.result.live_units_training_target_column, "target_actual_units_sold")
        self.assertNotIn("sufficient_stock_demand_units_target", self.result.target_columns)
        self.assertIn(
            "sufficient_stock_demand_units_target",
            self.result.sufficient_stock_target_columns,
        )

    def test_missing_stock_evidence_does_not_become_clean_target(self) -> None:
        frame = self.base_frame.copy()
        frame["stock_basis_units"] = pd.NA
        frame["store_adjusted_qty"] = pd.NA
        frame["pl_allocation_qty"] = pd.NA
        frame["total_units_commited"] = pd.NA
        frame["total_stock_available"] = pd.NA
        frame["current_soh"] = pd.NA
        engineered = PromotionTargetEngineer().engineer(frame).frame
        self.assertFalse(
            (engineered["target_quality_label"] == "CLEAN_REALIZED_DEMAND").any(),
        )

    def test_negative_soh_rows_are_labelled_contaminated(self) -> None:
        frame = self.base_frame.copy()
        frame.loc[frame.index[0], "current_soh"] = -3.0
        engineered = PromotionTargetEngineer().engineer(frame).frame
        row = engineered.iloc[0]
        self.assertEqual(row["target_quality_label"], "INVENTORY_INTEGRITY_CONTAMINATED")
        self.assertEqual(int(row["stock_integrity_issue_flag"]), 1)

    def test_target_weights_are_between_zero_and_one(self) -> None:
        weights = self.result.frame["target_weight"]
        self.assertTrue(((weights >= 0.0) & (weights <= 1.0)).all())

    def test_target_quality_labels_are_approved_values_only(self) -> None:
        labels = set(self.result.frame["target_quality_label"].astype(str))
        self.assertTrue(labels.issubset(set(APPROVED_TARGET_QUALITY_LABELS)))


if __name__ == "__main__":
    unittest.main()
