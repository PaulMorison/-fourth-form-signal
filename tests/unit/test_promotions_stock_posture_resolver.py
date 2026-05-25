from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.stock_posture_resolver import (  # noqa: E402
    resolve_stock_posture_integrity,
)


class PromotionStockPostureResolverTests(unittest.TestCase):
    def test_resolver_classifies_source_transform_missing_and_edge_rows(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "promotion_row_key": "row-source",
                    "store_number": "772",
                    "sku_number": "100",
                    "promotion_start_date": "2024-09-01",
                    "promotional_end_date": "2024-09-14",
                    "current_soh": -5.0,
                    "qty_on_order": 0.0,
                    "pl_allocation_qty": 10.0,
                    "store_adjusted_qty": 10.0,
                    "total_units_commited": 10.0,
                    "total_stock_available": -5.0,
                    "required_implied_daily": 1.0,
                },
                {
                    "promotion_row_key": "row-transform",
                    "store_number": "772",
                    "sku_number": "101",
                    "promotion_start_date": "2024-09-01",
                    "promotional_end_date": "2024-09-14",
                    "current_soh": -3.0,
                    "qty_on_order": 0.0,
                    "pl_allocation_qty": 5.0,
                    "store_adjusted_qty": 5.0,
                    "total_units_commited": 5.0,
                    "total_stock_available": 5.0,
                    "required_implied_daily": 1.0,
                },
                {
                    "promotion_row_key": "row-missing",
                    "store_number": "772",
                    "sku_number": "102",
                    "promotion_start_date": "2024-09-01",
                    "promotional_end_date": "2024-09-14",
                    "current_soh": -2.0,
                    "qty_on_order": pd.NA,
                    "pl_allocation_qty": 3.0,
                    "store_adjusted_qty": 3.0,
                    "total_units_commited": 3.0,
                    "total_stock_available": 2.0,
                    "required_implied_daily": 1.0,
                },
                {
                    "promotion_row_key": "row-edge",
                    "store_number": "772",
                    "sku_number": "103",
                    "promotion_start_date": "2024-09-01",
                    "promotional_end_date": "2024-09-14",
                    "current_soh": -2.0,
                    "qty_on_order": 4.0,
                    "pl_allocation_qty": 6.0,
                    "store_adjusted_qty": 6.0,
                    "total_units_commited": 6.0,
                    "total_stock_available": 6.0,
                    "required_implied_daily": 1.0,
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = resolve_stock_posture_integrity(
                frame,
                run_id="resolver-classification-test",
                artifact_paths=PromotionArtifactPaths(root=Path(temp_dir)),
            )

            self.assertEqual(result.failing_row_count, 4)
            class_by_row = dict(
                zip(
                    result.classified_rows["promotion_row_key"],
                    result.classified_rows["stock_posture_failure_class"],
                    strict=False,
                )
            )
            self.assertEqual(class_by_row["row-source"], "source_data_negative_inventory")
            self.assertEqual(class_by_row["row-transform"], "transform_inconsistency")
            self.assertEqual(class_by_row["row-missing"], "missing_inventory_inputs")
            self.assertEqual(class_by_row["row-edge"], "business_edge_case_requires_review")

            details = result.details
            self.assertTrue(Path(str(details["negative_stock_posture_rows_csv_path"])).exists())
            self.assertTrue(Path(str(details["negative_stock_posture_rows_parquet_path"])).exists())
            self.assertTrue(Path(str(details["negative_stock_posture_summary_path"])).exists())
            self.assertTrue(Path(str(details["negative_stock_posture_by_reason_path"])).exists())
            self.assertTrue(Path(str(details["stage4_stock_posture_diagnostics_path"])).exists())
            self.assertTrue(Path(str(details["negative_stock_posture_repairs_or_escalations_path"])).exists())

    def test_resolver_does_not_repair_or_clip_negative_inputs(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "promotion_row_key": "row-no-clip",
                    "store_number": "772",
                    "sku_number": "200",
                    "promotion_start_date": "2024-09-01",
                    "promotional_end_date": "2024-09-14",
                    "current_soh": -9.0,
                    "qty_on_order": 0.0,
                    "pl_allocation_qty": 0.0,
                    "store_adjusted_qty": 0.0,
                    "total_units_commited": 0.0,
                    "total_stock_available": -9.0,
                    "required_implied_daily": 1.0,
                }
            ]
        )

        result = resolve_stock_posture_integrity(
            frame,
            run_id=None,
            artifact_paths=None,
        )

        row = result.classified_rows.iloc[0]
        self.assertEqual(float(row["current_soh"]), -9.0)
        self.assertEqual(float(row["total_stock_available"]), -9.0)
        self.assertEqual(row["repair_status"], "not_repaired_fail_loud")
        self.assertEqual(result.summary["repair_policy"], "fail_loud_no_silent_repair")
