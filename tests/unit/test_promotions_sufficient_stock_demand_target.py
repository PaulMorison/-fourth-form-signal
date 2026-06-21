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
    SufficientStockDemandTargetError,
    build_sufficient_stock_demand_target_frame,
)


def _base_row(**overrides: object) -> pd.DataFrame:
    row = {
        "actual_units_sold": 40.0,
        "stock_basis_units": 100.0,
        "demand_reference_units": 55.0,
        "baseline_expected_units": 45.0,
        "promo_sales_day_count": 7.0,
        "live_promo_window_days": 7.0,
        "post_14d_units": 0.0,
        "current_soh": 25.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


class SufficientStockDemandTargetTests(unittest.TestCase):
    def test_clean_sufficient_stock_row_uses_realized_sales(self) -> None:
        result = build_sufficient_stock_demand_target_frame(_base_row())

        self.assertEqual(result.loc[0, "target_quality_label"], "CLEAN_REALIZED_DEMAND")
        self.assertEqual(float(result.loc[0, "sufficient_stock_demand_units_target"]), 40.0)
        self.assertEqual(float(result.loc[0, "target_weight"]), 1.0)
        self.assertEqual(int(result.loc[0, "sufficient_stock_observed_flag"]), 1)
        self.assertEqual(int(result.loc[0, "stock_constrained_flag"]), 0)

    def test_stockout_row_is_not_clean_demand(self) -> None:
        result = build_sufficient_stock_demand_target_frame(
            _base_row(
                actual_units_sold=99.0,
                stock_basis_units=100.0,
                post_14d_units=4.0,
                target_stockout_flag=1,
                demand_reference_units=120.0,
            )
        )

        self.assertNotEqual(result.loc[0, "target_quality_label"], "CLEAN_REALIZED_DEMAND")
        self.assertEqual(int(result.loc[0, "stock_constrained_flag"]), 1)
        self.assertEqual(result.loc[0, "target_quality_label"], "STOCK_CONSTRAINED_REPAIRED")
        self.assertGreater(float(result.loc[0, "sufficient_stock_demand_units_target"]), 99.0)

    def test_negative_soh_row_is_inventory_integrity_contaminated(self) -> None:
        result = build_sufficient_stock_demand_target_frame(_base_row(current_soh=-2.0))

        self.assertEqual(result.loc[0, "target_quality_label"], "INVENTORY_INTEGRITY_CONTAMINATED")
        self.assertEqual(int(result.loc[0, "stock_integrity_issue_flag"]), 1)
        self.assertEqual(float(result.loc[0, "target_weight"]), 0.0)
        self.assertTrue(pd.isna(result.loc[0, "sufficient_stock_demand_units_target"]))

    def test_missing_stock_evidence_does_not_become_clean(self) -> None:
        frame = pd.DataFrame(
            {
                "actual_units_sold": [12.0],
                "demand_reference_units": [20.0],
            }
        )
        result = build_sufficient_stock_demand_target_frame(frame)

        self.assertNotEqual(result.loc[0, "target_quality_label"], "CLEAN_REALIZED_DEMAND")
        self.assertEqual(int(result.loc[0, "sufficient_stock_observed_flag"]), 0)

    def test_missing_realized_sales_field_fails_loudly(self) -> None:
        with self.assertRaises(SufficientStockDemandTargetError):
            build_sufficient_stock_demand_target_frame(pd.DataFrame({"stock_basis_units": [10.0]}))

    def test_null_realized_sales_does_not_become_zero_clean_demand(self) -> None:
        result = build_sufficient_stock_demand_target_frame(_base_row(actual_units_sold=pd.NA))

        self.assertEqual(result.loc[0, "target_quality_label"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(pd.isna(result.loc[0, "sufficient_stock_demand_units_target"]))
        self.assertEqual(float(result.loc[0, "target_weight"]), 0.0)
        self.assertIn("NULL_REALIZED_SALES", str(result.loc[0, "target_warning"]))

    def test_feature_consensus_does_not_overwrite_target(self) -> None:
        result = build_sufficient_stock_demand_target_frame(
            _base_row(feature_probability_expected_units_consensus=500.0)
        )

        self.assertEqual(float(result.loc[0, "sufficient_stock_demand_units_target"]), 40.0)
        self.assertIn("FEATURE_CONSENSUS_DIAGNOSTIC_ONLY", str(result.loc[0, "target_warning"]))

    def test_target_units_are_never_negative(self) -> None:
        frames = [
            _base_row(),
            _base_row(actual_units_sold=99.0, stock_basis_units=100.0, post_14d_units=4.0, target_stockout_flag=1),
            _base_row(current_soh=-1.0),
        ]
        for frame in frames:
            result = build_sufficient_stock_demand_target_frame(frame)
            target = result["sufficient_stock_demand_units_target"]
            non_null = target.dropna()
            if not non_null.empty:
                self.assertTrue((non_null >= 0.0).all())

    def test_target_labels_are_restricted_to_approved_labels(self) -> None:
        result = build_sufficient_stock_demand_target_frame(_base_row())
        self.assertIn(result.loc[0, "target_quality_label"], APPROVED_TARGET_QUALITY_LABELS)

    def test_target_weights_are_between_zero_and_one(self) -> None:
        scenarios = [
            _base_row(),
            _base_row(actual_units_sold=99.0, stock_basis_units=100.0, post_14d_units=4.0, target_stockout_flag=1),
            _base_row(current_soh=-1.0),
            _base_row(actual_units_sold=0.0, promo_sales_day_count=0.0, stock_basis_units=0.0),
        ]
        for frame in scenarios:
            weights = build_sufficient_stock_demand_target_frame(frame)["target_weight"]
            self.assertTrue(((weights >= 0.0) & (weights <= 1.0)).all())

    def test_stock_constrained_repair_requires_repair_evidence(self) -> None:
        unrepaired = build_sufficient_stock_demand_target_frame(
            _base_row(
                actual_units_sold=99.0,
                stock_basis_units=100.0,
                target_stockout_flag=1,
                post_14d_units=0.0,
                demand_reference_units=pd.NA,
            )
        )
        self.assertEqual(unrepaired.loc[0, "target_quality_label"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(pd.isna(unrepaired.loc[0, "sufficient_stock_demand_units_target"]))

        repaired = build_sufficient_stock_demand_target_frame(
            _base_row(
                actual_units_sold=99.0,
                stock_basis_units=100.0,
                target_stockout_flag=1,
                post_14d_units=4.0,
                demand_reference_units=120.0,
            )
        )
        self.assertEqual(repaired.loc[0, "target_quality_label"], "STOCK_CONSTRAINED_REPAIRED")
        self.assertEqual(repaired.loc[0, "target_repair_basis"], "REPAIR_POST14_FOLLOWTHROUGH")

    def test_output_includes_all_required_canonical_fields(self) -> None:
        result = build_sufficient_stock_demand_target_frame(_base_row())
        for column_name in SUFFICIENT_STOCK_DEMAND_TARGET_COLUMNS:
            self.assertIn(column_name, result.columns)


if __name__ == "__main__":
    unittest.main()
