from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.feature_engineering.demand.ft_basket_context_feature_bundle import (  # noqa: E402
    apply_ft_basket_context_feature_bundle,
)


def _raw_row(
    *,
    store: int,
    sku: int,
    start: date,
    end: date,
    realised_transaction_count: float = 0.0,
    realised_sku_solo_transaction_count: float = 0.0,
    realised_sku_multi_item_transaction_count: float = 0.0,
    realised_basket_item_count_sum_when_sku_present: float = 0.0,
    realised_basket_item_count_median_when_sku_present: float = 0.0,
    realised_basket_sales_ex_gst_sum_when_sku_present: float = 0.0,
    realised_basket_sales_ex_gst_median_when_sku_present: float = 0.0,
    realised_units_in_multi_item_baskets: float = 0.0,
    realised_multi_item_multi_unit_transaction_count: float = 0.0,
    realised_weekend_transaction_count_with_sku: float = 0.0,
    realised_pay_cycle_transaction_count_with_sku: float = 0.0,
    realised_top_companion_sku_1_share: float = 0.0,
    realised_top_companion_sku_2_share: float = 0.0,
    realised_companion_concentration_index: float = 0.0,
    actual_units_sold_promo: float = 0.0,
    actual_days_with_sales_promo: float = 0.0,
    stock_basis_units: float = 10.0,
    live_promo_window_days: float = 7.0,
) -> dict[str, object]:
    return {
        "promotion_row_key": f"{store}|{sku}|{start.isoformat()}|{end.isoformat()}",
        "store_number_key": store,
        "sku_number_key": sku,
        "promotion_start_date_date": start.isoformat(),
        "promotional_end_date_date": end.isoformat(),
        "realised_transaction_count": realised_transaction_count,
        "realised_sku_solo_transaction_count": realised_sku_solo_transaction_count,
        "realised_sku_multi_item_transaction_count": realised_sku_multi_item_transaction_count,
        "realised_basket_item_count_sum_when_sku_present": realised_basket_item_count_sum_when_sku_present,
        "realised_basket_item_count_median_when_sku_present": realised_basket_item_count_median_when_sku_present,
        "realised_basket_sales_ex_gst_sum_when_sku_present": realised_basket_sales_ex_gst_sum_when_sku_present,
        "realised_basket_sales_ex_gst_median_when_sku_present": realised_basket_sales_ex_gst_median_when_sku_present,
        "realised_units_in_multi_item_baskets": realised_units_in_multi_item_baskets,
        "realised_multi_item_multi_unit_transaction_count": realised_multi_item_multi_unit_transaction_count,
        "realised_weekend_transaction_count_with_sku": realised_weekend_transaction_count_with_sku,
        "realised_pay_cycle_transaction_count_with_sku": realised_pay_cycle_transaction_count_with_sku,
        "realised_top_companion_sku_1_share": realised_top_companion_sku_1_share,
        "realised_top_companion_sku_2_share": realised_top_companion_sku_2_share,
        "realised_companion_concentration_index": realised_companion_concentration_index,
        "actual_units_sold_promo": actual_units_sold_promo,
        "actual_days_with_sales_promo": actual_days_with_sales_promo,
        "stock_basis_units": stock_basis_units,
        "live_promo_window_days": live_promo_window_days,
    }


class BasketContextFeatureBundleTests(unittest.TestCase):
    def test_high_attach_rate_history_emits_strong_basket_dependency(self) -> None:
        reference = pd.DataFrame(
            [
                _raw_row(
                    store=1,
                    sku=100,
                    start=date(2024, 1, 1),
                    end=date(2024, 1, 7),
                    realised_transaction_count=10.0,
                    realised_sku_solo_transaction_count=0.0,
                    realised_sku_multi_item_transaction_count=10.0,
                    realised_basket_item_count_sum_when_sku_present=38.0,
                    realised_basket_item_count_median_when_sku_present=4.0,
                    realised_basket_sales_ex_gst_sum_when_sku_present=220.0,
                    realised_basket_sales_ex_gst_median_when_sku_present=21.0,
                    realised_units_in_multi_item_baskets=14.0,
                    realised_multi_item_multi_unit_transaction_count=4.0,
                    realised_weekend_transaction_count_with_sku=4.0,
                    realised_top_companion_sku_1_share=0.72,
                    realised_top_companion_sku_2_share=0.31,
                    realised_companion_concentration_index=0.64,
                    actual_units_sold_promo=14.0,
                    actual_days_with_sales_promo=7.0,
                ),
                _raw_row(
                    store=1,
                    sku=100,
                    start=date(2024, 2, 1),
                    end=date(2024, 2, 7),
                    realised_transaction_count=9.0,
                    realised_sku_solo_transaction_count=1.0,
                    realised_sku_multi_item_transaction_count=8.0,
                    realised_basket_item_count_sum_when_sku_present=30.0,
                    realised_basket_item_count_median_when_sku_present=3.0,
                    realised_basket_sales_ex_gst_sum_when_sku_present=180.0,
                    realised_basket_sales_ex_gst_median_when_sku_present=18.0,
                    realised_units_in_multi_item_baskets=11.0,
                    realised_multi_item_multi_unit_transaction_count=3.0,
                    realised_weekend_transaction_count_with_sku=3.0,
                    realised_top_companion_sku_1_share=0.68,
                    realised_top_companion_sku_2_share=0.24,
                    realised_companion_concentration_index=0.59,
                    actual_units_sold_promo=12.0,
                    actual_days_with_sales_promo=7.0,
                ),
            ]
        )
        candidates = pd.DataFrame(
            [_raw_row(store=1, sku=100, start=date(2024, 4, 1), end=date(2024, 4, 7))]
        )

        result = apply_ft_basket_context_feature_bundle(candidates, reference_frame=reference)
        row = result.iloc[0]

        self.assertGreater(row["feature_basket_attach_rate"], 0.85)
        self.assertLess(row["feature_sku_solo_purchase_rate"], 0.15)
        self.assertGreater(row["feature_sku_basket_dependency_score"], 0.45)
        self.assertGreater(row["feature_probability_sku_in_multi_item_basket"], 0.85)
        self.assertGreater(row["feature_companion_absence_risk_score"], 0.3)

    def test_mostly_solo_history_emits_low_dependency(self) -> None:
        reference = pd.DataFrame(
            [
                _raw_row(
                    store=1,
                    sku=101,
                    start=date(2024, 1, 1),
                    end=date(2024, 1, 7),
                    realised_transaction_count=8.0,
                    realised_sku_solo_transaction_count=7.0,
                    realised_sku_multi_item_transaction_count=1.0,
                    realised_basket_item_count_sum_when_sku_present=9.0,
                    realised_basket_item_count_median_when_sku_present=1.0,
                    realised_basket_sales_ex_gst_sum_when_sku_present=64.0,
                    realised_basket_sales_ex_gst_median_when_sku_present=7.0,
                    realised_units_in_multi_item_baskets=1.0,
                    realised_multi_item_multi_unit_transaction_count=0.0,
                    realised_weekend_transaction_count_with_sku=2.0,
                    realised_top_companion_sku_1_share=0.12,
                    realised_top_companion_sku_2_share=0.0,
                    realised_companion_concentration_index=0.03,
                    actual_units_sold_promo=8.0,
                    actual_days_with_sales_promo=7.0,
                )
            ]
        )
        candidates = pd.DataFrame(
            [_raw_row(store=1, sku=101, start=date(2024, 3, 1), end=date(2024, 3, 7))]
        )

        result = apply_ft_basket_context_feature_bundle(candidates, reference_frame=reference)
        row = result.iloc[0]

        self.assertLess(row["feature_basket_attach_rate"], 0.2)
        self.assertGreater(row["feature_sku_solo_purchase_rate"], 0.7)
        self.assertLess(row["feature_sku_basket_dependency_score"], 0.1)
        self.assertLess(row["feature_companion_absence_risk_score"], 0.05)

    def test_concentrated_companion_history_emits_high_concentration(self) -> None:
        reference = pd.DataFrame(
            [
                _raw_row(
                    store=2,
                    sku=200,
                    start=date(2024, 1, 1),
                    end=date(2024, 1, 7),
                    realised_transaction_count=12.0,
                    realised_sku_solo_transaction_count=1.0,
                    realised_sku_multi_item_transaction_count=11.0,
                    realised_basket_item_count_sum_when_sku_present=42.0,
                    realised_basket_item_count_median_when_sku_present=4.0,
                    realised_basket_sales_ex_gst_sum_when_sku_present=310.0,
                    realised_basket_sales_ex_gst_median_when_sku_present=24.0,
                    realised_units_in_multi_item_baskets=15.0,
                    realised_multi_item_multi_unit_transaction_count=5.0,
                    realised_top_companion_sku_1_share=0.91,
                    realised_top_companion_sku_2_share=0.08,
                    realised_companion_concentration_index=0.84,
                    actual_units_sold_promo=16.0,
                    actual_days_with_sales_promo=7.0,
                )
            ]
        )
        candidates = pd.DataFrame(
            [_raw_row(store=2, sku=200, start=date(2024, 2, 1), end=date(2024, 2, 7))]
        )

        result = apply_ft_basket_context_feature_bundle(candidates, reference_frame=reference)
        row = result.iloc[0]

        self.assertGreater(row["feature_top_companion_sku_1_share"], 0.85)
        self.assertLess(row["feature_top_companion_sku_2_share"], 0.15)
        self.assertGreater(row["feature_companion_concentration_index"], 0.75)
        self.assertLess(row["feature_basket_diversity_when_sku_present"], 0.25)

    def test_sparse_history_uses_smoothed_probability_outputs(self) -> None:
        reference = pd.DataFrame(
            [
                _raw_row(
                    store=3,
                    sku=300,
                    start=date(2024, 1, 1),
                    end=date(2024, 1, 7),
                    realised_transaction_count=2.0,
                    realised_sku_solo_transaction_count=0.0,
                    realised_sku_multi_item_transaction_count=2.0,
                    realised_basket_item_count_sum_when_sku_present=6.0,
                    realised_basket_item_count_median_when_sku_present=3.0,
                    realised_basket_sales_ex_gst_sum_when_sku_present=32.0,
                    realised_basket_sales_ex_gst_median_when_sku_present=16.0,
                    realised_units_in_multi_item_baskets=2.0,
                    realised_multi_item_multi_unit_transaction_count=0.0,
                    realised_top_companion_sku_1_share=0.50,
                    realised_top_companion_sku_2_share=0.0,
                    realised_companion_concentration_index=0.25,
                    actual_units_sold_promo=2.0,
                    actual_days_with_sales_promo=2.0,
                )
            ]
        )
        candidates = pd.DataFrame(
            [_raw_row(store=3, sku=300, start=date(2024, 2, 1), end=date(2024, 2, 7))]
        )

        result = apply_ft_basket_context_feature_bundle(candidates, reference_frame=reference)
        row = result.iloc[0]

        self.assertAlmostEqual(row["feature_basket_attach_rate"], 1.0)
        self.assertAlmostEqual(row["feature_probability_sku_in_multi_item_basket"], 0.75)
        self.assertAlmostEqual(row["feature_probability_units_given_multi_item_basket"], 0.25)

    def test_no_history_preserves_missingness(self) -> None:
        candidates = pd.DataFrame(
            [_raw_row(store=9, sku=999, start=date(2024, 6, 1), end=date(2024, 6, 7))]
        )

        result = apply_ft_basket_context_feature_bundle(candidates)
        row = result.iloc[0]

        self.assertEqual(row["feature_basket_history_missing_evidence_flag"], 1.0)
        self.assertEqual(row["feature_basket_history_evidence_promo_count"], 0.0)
        self.assertTrue(pd.isna(row["feature_basket_attach_rate"]))
        self.assertTrue(pd.isna(row["feature_top_companion_sku_1_share"]))
        self.assertTrue(pd.isna(row["feature_probability_zero_units_given_low_traffic"]))

    def test_bundle_respects_strict_prior_cutoff_and_preserves_rows(self) -> None:
        prior_included = _raw_row(
            store=4,
            sku=400,
            start=date(2024, 1, 1),
            end=date(2024, 1, 5),
            realised_transaction_count=4.0,
            realised_sku_solo_transaction_count=1.0,
            realised_sku_multi_item_transaction_count=3.0,
            realised_basket_item_count_sum_when_sku_present=11.0,
            realised_basket_item_count_median_when_sku_present=3.0,
            realised_basket_sales_ex_gst_sum_when_sku_present=44.0,
            realised_basket_sales_ex_gst_median_when_sku_present=11.0,
            actual_units_sold_promo=4.0,
            actual_days_with_sales_promo=4.0,
        )
        prior_excluded = _raw_row(
            store=4,
            sku=400,
            start=date(2024, 1, 3),
            end=date(2024, 1, 7),
            realised_transaction_count=8.0,
            realised_sku_solo_transaction_count=0.0,
            realised_sku_multi_item_transaction_count=8.0,
            realised_basket_item_count_sum_when_sku_present=32.0,
            realised_basket_item_count_median_when_sku_present=4.0,
            realised_basket_sales_ex_gst_sum_when_sku_present=120.0,
            realised_basket_sales_ex_gst_median_when_sku_present=15.0,
            actual_units_sold_promo=10.0,
            actual_days_with_sales_promo=5.0,
        )
        candidate = _raw_row(
            store=4,
            sku=400,
            start=date(2024, 1, 7),
            end=date(2024, 1, 13),
        )

        result = apply_ft_basket_context_feature_bundle(
            pd.DataFrame([prior_included, prior_excluded, candidate])
        )
        candidate_row = result.iloc[-1]

        self.assertEqual(len(result.index), 3)
        self.assertEqual(candidate_row["feature_basket_history_evidence_promo_count"], 1.0)
        self.assertAlmostEqual(candidate_row["feature_basket_attach_rate"], 0.75)

    def test_stock_constrained_history_emits_risk_flag(self) -> None:
        reference = pd.DataFrame(
            [
                _raw_row(
                    store=5,
                    sku=500,
                    start=date(2024, 1, 1),
                    end=date(2024, 1, 7),
                    realised_transaction_count=6.0,
                    realised_sku_solo_transaction_count=1.0,
                    realised_sku_multi_item_transaction_count=5.0,
                    realised_basket_item_count_sum_when_sku_present=18.0,
                    realised_basket_item_count_median_when_sku_present=3.0,
                    realised_basket_sales_ex_gst_sum_when_sku_present=84.0,
                    realised_basket_sales_ex_gst_median_when_sku_present=13.0,
                    actual_units_sold_promo=9.8,
                    actual_days_with_sales_promo=4.0,
                    stock_basis_units=10.0,
                    live_promo_window_days=7.0,
                ),
                _raw_row(
                    store=5,
                    sku=500,
                    start=date(2024, 2, 1),
                    end=date(2024, 2, 7),
                    realised_transaction_count=5.0,
                    realised_sku_solo_transaction_count=1.0,
                    realised_sku_multi_item_transaction_count=4.0,
                    realised_basket_item_count_sum_when_sku_present=16.0,
                    realised_basket_item_count_median_when_sku_present=3.0,
                    realised_basket_sales_ex_gst_sum_when_sku_present=70.0,
                    realised_basket_sales_ex_gst_median_when_sku_present=12.0,
                    actual_units_sold_promo=10.0,
                    actual_days_with_sales_promo=3.0,
                    stock_basis_units=10.0,
                    live_promo_window_days=7.0,
                ),
            ]
        )
        candidates = pd.DataFrame(
            [_raw_row(store=5, sku=500, start=date(2024, 3, 1), end=date(2024, 3, 7))]
        )

        result = apply_ft_basket_context_feature_bundle(candidates, reference_frame=reference)
        row = result.iloc[0]

        self.assertEqual(row["feature_stock_constrained_history_flag"], 1.0)
        self.assertGreater(row["feature_lost_sales_risk_score"], 0.3)
        self.assertEqual(row["feature_stock_constrained_evidence_promo_count"], 2.0)

    def test_bundle_has_no_infinite_explosions(self) -> None:
        reference = pd.DataFrame(
            [
                _raw_row(
                    store=6,
                    sku=600,
                    start=date(2024, 1, 1),
                    end=date(2024, 1, 7),
                    realised_transaction_count=0.0,
                    actual_units_sold_promo=0.0,
                    actual_days_with_sales_promo=0.0,
                    stock_basis_units=0.0,
                )
            ]
        )
        candidates = pd.DataFrame(
            [_raw_row(store=6, sku=600, start=date(2024, 2, 1), end=date(2024, 2, 7))]
        )

        result = apply_ft_basket_context_feature_bundle(candidates, reference_frame=reference)
        numeric_columns = [
            column_name
            for column_name in result.columns
            if str(column_name).startswith("feature_")
        ]
        self.assertFalse(
            np.isinf(result.loc[:, numeric_columns].to_numpy(dtype=float, na_value=np.nan)).any()
        )


if __name__ == "__main__":
    unittest.main()