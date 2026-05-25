from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.datasets.completed_dataset_joiner import (  # noqa: E402
    PromotionCompletedDatasetJoiner,
)


class PromotionCompletedDatasetJoinerTests(unittest.TestCase):
    def test_join_reconstructs_completed_metrics_and_metadata(self) -> None:
        joiner = PromotionCompletedDatasetJoiner()
        base_frame = pd.DataFrame(
            {
                "promotion_row_key": ["promo-1"],
                "promotion_name": ["Spring Sale"],
                "promotion_start_date": ["2024-08-01"],
                "promotional_end_date": ["2024-08-07"],
                "promotion_start_date_date": ["2024-08-01"],
                "promotional_end_date_date": ["2024-08-07"],
                "live_promo_window_days": [7],
            }
        )
        window_aggregate_frame = pd.DataFrame(
            {
                "promotion_row_key": ["promo-1"],
                "actual_units_sold": [14.0],
                "actual_refund_units": [2.0],
                "actual_refund_sales_ex_gst": [4.0],
                "actual_sales_ex_gst": [70.0],
                "actual_sales_inc_gst": [77.0],
                "promo_sales_day_count": [7.0],
                "actual_avg_daily_units": [2.0],
                "actual_std_daily_units": [0.5],
                "actual_peak_daily_units": [3.0],
                "inferred_supplier_number": [12345.0],
                "pre_56d_units": [56.0],
                "pre_28d_units": [28.0],
                "pre_7d_units": [7.0],
                "pre_56d_sales_ex_gst": [112.0],
                "pre_28d_sales_ex_gst": [56.0],
                "pre_7d_sales_ex_gst": [14.0],
                "pre_56d_days_with_sales": [56.0],
                "pre_28d_days_with_sales": [28.0],
                "pre_7d_days_with_sales": [7.0],
                "pre_56d_avg_daily_units": [1.0],
                "pre_28d_avg_daily_units": [1.0],
                "pre_7d_avg_daily_units": [1.0],
                "pre_prior_21d_avg_daily_units": [1.0],
                "pre_56d_std_daily_units": [0.2],
                "pre_28d_std_daily_units": [0.2],
                "post_14d_units": [21.0],
                "post_14d_sales_ex_gst": [42.0],
                "post_14d_avg_daily_units": [1.5],
                "post_14d_days_with_sales": [14.0],
            }
        )
        transaction_aggregate_frame = pd.DataFrame(
            {
                "promotion_row_key": ["promo-1"],
                "realised_transaction_count": [7.0],
                "realised_promo_transaction_count": [5.0],
                "actual_flagged_promo_units": [11.0],
                "realised_sku_solo_transaction_count": [2.0],
                "realised_sku_multi_item_transaction_count": [5.0],
                "realised_basket_item_count_sum_when_sku_present": [19.0],
                "realised_basket_item_count_median_when_sku_present": [3.0],
                "realised_basket_sales_ex_gst_sum_when_sku_present": [154.0],
                "realised_basket_sales_ex_gst_median_when_sku_present": [22.0],
                "realised_units_in_multi_item_baskets": [9.0],
                "realised_multi_item_multi_unit_transaction_count": [3.0],
                "realised_weekend_transaction_count_with_sku": [3.0],
                "realised_pay_cycle_transaction_count_with_sku": [2.0],
                "realised_top_companion_sku_1_share": [4.0 / 7.0],
                "realised_top_companion_sku_2_share": [2.0 / 7.0],
                "realised_companion_concentration_index": [20.0 / 49.0],
            }
        )

        joined = joiner.join(
            run_id="completed-batch-1",
            as_of_date="2024-09-01",
            query_version="promotion_completed_enriched_v1",
            advice_source_table_name="dbo.PromotionAdvice",
            realised_sales_source_table_name="dbo.PwlogD",
            base_frame=base_frame,
            window_aggregate_frame=window_aggregate_frame,
            transaction_aggregate_frame=transaction_aggregate_frame,
            extracted_at_utc="2024-09-01T00:00:00+00:00",
        )

        self.assertEqual(float(joined.loc[0, "actual_units_sold_promo"]), 14.0)
        self.assertEqual(float(joined.loc[0, "actual_sales_ex_gst_promo"]), 70.0)
        self.assertEqual(float(joined.loc[0, "actual_transaction_count_promo"]), 7.0)
        self.assertEqual(float(joined.loc[0, "actual_days_with_sales_promo"]), 7.0)
        self.assertAlmostEqual(
            float(joined.loc[0, "actual_avg_sales_per_selling_day_promo"]),
            10.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "pre_56d_avg_sales_ex_gst_per_selling_day"]),
            2.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "post_14d_avg_sales_ex_gst_per_selling_day"]),
            3.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "actual_units_per_transaction"]),
            2.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "actual_transaction_intensity"]),
            1.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "actual_promo_transaction_intensity"]),
            5.0 / 7.0,
        )
        self.assertEqual(float(joined.loc[0, "realised_sku_solo_transaction_count"]), 2.0)
        self.assertEqual(float(joined.loc[0, "realised_sku_multi_item_transaction_count"]), 5.0)
        self.assertAlmostEqual(
            float(joined.loc[0, "realised_basket_item_count_sum_when_sku_present"]),
            19.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "realised_basket_item_count_median_when_sku_present"]),
            3.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "realised_basket_sales_ex_gst_sum_when_sku_present"]),
            154.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "realised_top_companion_sku_1_share"]),
            4.0 / 7.0,
        )
        self.assertAlmostEqual(
            float(joined.loc[0, "realised_companion_concentration_index"]),
            20.0 / 49.0,
        )
        self.assertEqual(joined.loc[0, "extraction_selection_mode"], "completed")
        self.assertEqual(joined.loc[0, "extraction_query_version"], "promotion_completed_enriched_v1")
        self.assertEqual(joined.loc[0, "advice_source_table_name"], "dbo.PromotionAdvice")
        self.assertEqual(joined.loc[0, "realised_sales_source_table_name"], "dbo.PwlogD")
        self.assertEqual(joined.loc[0, "extraction_run_id"], "completed-batch-1")
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(joined["promotion_start_date"]))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(joined["extraction_as_of_date"]))
