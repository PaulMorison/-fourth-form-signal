from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.feature_engineering.demand.ft_prior_promo_memory import (  # noqa: E402
    PRIOR_PROMO_MEMORY_FEATURE_COLUMNS,
    apply_ft_prior_promo_memory,
)


def _row(
    *,
    store: int,
    sku: int,
    start: date,
    end: date,
    discount_percent: float,
    promo_price: float = 10.0,
    actual_units_sold_promo: float = 0.0,
    pre_56d_units: float = 200.0,
    pre_28d_units: float = 100.0,
    pre_7d_units: float = 25.0,
    pre_56d_days_with_sales: float = 42.0,
    pre_28d_days_with_sales: float = 21.0,
    pre_7d_days_with_sales: float = 6.0,
    baseline_daily_units: float = 5.0,
    baseline_expected_units: float | None = None,
    live_promo_window_days: float = 7.0,
    pl_allocated: float | None = None,
    stock_basis_units: float | None = None,
) -> dict[str, object]:
    return {
        "promotion_row_key": f"{store}|{sku}|{start.isoformat()}|{end.isoformat()}",
        "store_number_key": store,
        "sku_number_key": sku,
        "promotion_start_date_date": start.isoformat(),
        "promotional_end_date_date": end.isoformat(),
        "discount_percent": discount_percent,
        "promo_price": promo_price,
        "actual_units_sold_promo": actual_units_sold_promo,
        "pre_56d_units": pre_56d_units,
        "pre_28d_units": pre_28d_units,
        "pre_7d_units": pre_7d_units,
        "pre_56d_days_with_sales": pre_56d_days_with_sales,
        "pre_28d_days_with_sales": pre_28d_days_with_sales,
        "pre_7d_days_with_sales": pre_7d_days_with_sales,
        "baseline_daily_units": baseline_daily_units,
        "baseline_expected_units": baseline_expected_units,
        "live_promo_window_days": live_promo_window_days,
        "pl_allocated": pl_allocated,
        "stock_basis_units": stock_basis_units,
    }


class PriorPromoMemoryLeakageSafetyTests(unittest.TestCase):
    def test_candidate_consumes_only_strictly_prior_history(self) -> None:
        """A row whose start equals the prior row's end must NOT see itself as prior."""
        prior = _row(
            store=1, sku=100, start=date(2024, 1, 1), end=date(2024, 1, 7),
            discount_percent=20.0, actual_units_sold_promo=80.0,
        )
        # candidate starts EXACTLY on prior end-date — must be excluded.
        candidate = _row(
            store=1, sku=100, start=date(2024, 1, 7), end=date(2024, 1, 13),
            discount_percent=20.0, actual_units_sold_promo=0.0,
        )
        frame = pd.DataFrame([prior, candidate])
        result = apply_ft_prior_promo_memory(frame)
        cand_row = result.iloc[1]
        self.assertEqual(cand_row["feature_prior_promo_14d_flag"], 0.0)
        self.assertEqual(cand_row["feature_prior_promo_units_14d"], 0.0)

    def test_strictly_prior_history_is_consumed(self) -> None:
        prior = _row(
            store=1, sku=100, start=date(2024, 1, 1), end=date(2024, 1, 7),
            discount_percent=20.0, actual_units_sold_promo=80.0, promo_price=10.0,
        )
        candidate = _row(
            store=1, sku=100, start=date(2024, 1, 8), end=date(2024, 1, 14),
            discount_percent=10.0, actual_units_sold_promo=0.0, promo_price=12.0,
        )
        frame = pd.DataFrame([prior, candidate])
        result = apply_ft_prior_promo_memory(frame)
        cand_row = result.iloc[1]
        self.assertEqual(cand_row["feature_prior_promo_14d_flag"], 1.0)
        self.assertGreater(cand_row["feature_prior_promo_units_14d"], 0.0)
        self.assertEqual(cand_row["feature_prior_promo_days_since_last_promo"], 1.0)

    def test_future_only_candidate_is_all_zero_or_sentinel(self) -> None:
        candidate = _row(
            store=1, sku=100, start=date(2024, 6, 1), end=date(2024, 6, 7),
            discount_percent=20.0,
        )
        result = apply_ft_prior_promo_memory(pd.DataFrame([candidate]))
        row = result.iloc[0]
        self.assertEqual(row["feature_prior_promo_14d_flag"], 0.0)
        self.assertEqual(row["feature_prior_promo_28d_flag"], 0.0)
        self.assertEqual(row["feature_prior_promo_56d_flag"], 0.0)
        self.assertEqual(row["feature_prior_promo_units_56d"], 0.0)
        # days-since-last sentinel should kick in (>= 999)
        self.assertGreaterEqual(row["feature_prior_promo_days_since_last_promo"], 999.0)


class PriorPromoSameOrBetterDiscountTests(unittest.TestCase):
    def test_same_or_better_discount_recognised(self) -> None:
        prior = _row(
            store=1, sku=100, start=date(2024, 1, 1), end=date(2024, 1, 7),
            discount_percent=30.0, actual_units_sold_promo=100.0,
        )
        candidate = _row(
            store=1, sku=100, start=date(2024, 1, 20), end=date(2024, 1, 26),
            discount_percent=20.0,
        )
        result = apply_ft_prior_promo_memory(pd.DataFrame([prior, candidate]))
        cand_row = result.iloc[1]
        # Prior discount 30% is better than candidate 20% -> same_or_better == 1.
        self.assertEqual(cand_row["feature_prior_same_or_better_discount_56d_flag"], 1.0)
        # better-discount sentinel < 999 means a strictly-better prior was seen.
        self.assertLess(cand_row["feature_prior_better_discount_days_since_last_promo"], 999.0)

    def test_strictly_lower_prior_discount_does_not_count(self) -> None:
        prior = _row(
            store=1, sku=100, start=date(2024, 1, 1), end=date(2024, 1, 7),
            discount_percent=10.0,
        )
        candidate = _row(
            store=1, sku=100, start=date(2024, 1, 20), end=date(2024, 1, 26),
            discount_percent=30.0,
        )
        result = apply_ft_prior_promo_memory(pd.DataFrame([prior, candidate]))
        cand_row = result.iloc[1]
        self.assertEqual(cand_row["feature_prior_same_or_better_discount_56d_flag"], 0.0)
        # better-discount sentinel == 999 means no strictly-better prior seen.
        self.assertGreaterEqual(cand_row["feature_prior_better_discount_days_since_last_promo"], 999.0)

    def test_discount_history_features_are_strictly_prior_and_row_grain(self) -> None:
        candidate_start = date(2024, 6, 1)
        rows = [
            _row(
                store=1, sku=100, start=date(2024, 1, 1), end=date(2024, 1, 7),
                discount_percent=20.0, actual_units_sold_promo=100.0,
            ),
            _row(
                store=1, sku=100, start=date(2024, 2, 1), end=date(2024, 2, 7),
                discount_percent=20.0, actual_units_sold_promo=60.0,
            ),
            _row(
                store=1, sku=100, start=date(2024, 3, 1), end=date(2024, 3, 7),
                discount_percent=30.0, actual_units_sold_promo=120.0,
            ),
            _row(
                store=1, sku=100, start=date(2024, 4, 1), end=date(2024, 4, 7),
                discount_percent=10.0, actual_units_sold_promo=30.0,
            ),
            _row(
                store=2, sku=100, start=date(2024, 1, 1), end=date(2024, 1, 7),
                discount_percent=20.0, actual_units_sold_promo=999.0,
            ),
            _row(
                store=1, sku=100, start=candidate_start + timedelta(days=7), end=candidate_start + timedelta(days=13),
                discount_percent=20.0, actual_units_sold_promo=999.0,
            ),
            _row(
                store=1, sku=100, start=candidate_start, end=candidate_start + timedelta(days=6),
                discount_percent=20.0, actual_units_sold_promo=0.0,
            ),
        ]
        result = apply_ft_prior_promo_memory(pd.DataFrame(rows))
        cand_row = result.iloc[-1]

        self.assertEqual(cand_row["feature_historical_promo_events_same_discount"], 2.0)
        self.assertEqual(cand_row["feature_historical_promo_events_same_or_better_discount"], 3.0)
        self.assertAlmostEqual(cand_row["feature_historical_units_same_discount_avg"], 80.0)
        self.assertAlmostEqual(cand_row["feature_historical_units_same_discount_median"], 80.0)
        self.assertAlmostEqual(cand_row["feature_historical_units_same_discount_std"], 20.0)
        self.assertAlmostEqual(cand_row["feature_historical_units_same_or_better_discount_avg"], (100.0 + 60.0 + 120.0) / 3.0)
        self.assertEqual(cand_row["feature_discount_band_event_count"], 3.0)
        self.assertAlmostEqual(cand_row["feature_discount_band_response_avg"], (100.0 + 60.0 + 120.0) / 3.0)
        self.assertAlmostEqual(cand_row["feature_historical_discount_response_confidence"], 0.6)

    def test_empirical_probability_features_use_same_or_better_history(self) -> None:
        candidate_start = date(2024, 6, 1)
        rows = [
            _row(
                store=1, sku=100, start=date(2024, 1, 1), end=date(2024, 1, 7),
                discount_percent=20.0, actual_units_sold_promo=0.0,
            ),
            _row(
                store=1, sku=100, start=date(2024, 2, 1), end=date(2024, 2, 7),
                discount_percent=25.0, actual_units_sold_promo=40.0,
            ),
            _row(
                store=1, sku=100, start=date(2024, 4, 1), end=date(2024, 4, 7),
                discount_percent=30.0, actual_units_sold_promo=120.0,
            ),
            _row(
                store=1, sku=100, start=candidate_start, end=candidate_start + timedelta(days=6),
                discount_percent=20.0, baseline_expected_units=50.0,
                live_promo_window_days=7.0, pl_allocated=80.0, stock_basis_units=100.0,
            ),
        ]

        result = apply_ft_prior_promo_memory(pd.DataFrame(rows))
        cand_row = result.iloc[-1]

        self.assertAlmostEqual(
            cand_row["feature_probability_zero_demand_same_or_better_discount"],
            1.0 / 3.0,
        )
        self.assertAlmostEqual(
            cand_row["feature_probability_low_demand_vs_baseline_same_or_better_discount"],
            2.0 / 3.0,
        )
        self.assertAlmostEqual(
            cand_row["feature_probability_units_below_allocation_same_or_better_discount"],
            2.0 / 3.0,
        )
        self.assertAlmostEqual(
            cand_row["feature_probability_demand_exceeds_allocation_same_or_better_discount"],
            1.0 / 3.0,
        )
        self.assertAlmostEqual(
            cand_row["feature_probability_stockout_vs_stock_basis_same_or_better_discount"],
            1.0 / 3.0,
        )
        self.assertAlmostEqual(cand_row["feature_promo_history_evidence_strength"], 0.6)
        self.assertAlmostEqual(cand_row["feature_sparse_history_penalty"], 0.4)
        self.assertGreater(cand_row["feature_order_evidence_quality_score"], 0.0)
        self.assertLessEqual(cand_row["feature_order_evidence_quality_score"], 1.0)
        self.assertAlmostEqual(cand_row["feature_overallocation_risk_score"], 0.5011111111)

    def test_probability_features_remain_missing_without_comparable_history(self) -> None:
        candidate = _row(
            store=1, sku=100, start=date(2024, 6, 1), end=date(2024, 6, 7),
            discount_percent=20.0, baseline_expected_units=50.0,
            live_promo_window_days=7.0, pl_allocated=80.0, stock_basis_units=100.0,
        )

        result = apply_ft_prior_promo_memory(pd.DataFrame([candidate]))
        row = result.iloc[0]

        self.assertTrue(pd.isna(row["feature_probability_zero_demand_same_or_better_discount"]))
        self.assertTrue(pd.isna(row["feature_probability_low_demand_vs_baseline_same_or_better_discount"]))
        self.assertTrue(pd.isna(row["feature_probability_demand_exceeds_allocation_same_or_better_discount"]))
        self.assertTrue(pd.isna(row["feature_probability_units_below_allocation_same_or_better_discount"]))
        self.assertTrue(pd.isna(row["feature_probability_stockout_vs_stock_basis_same_or_better_discount"]))
        self.assertEqual(row["feature_promo_history_evidence_strength"], 0.0)
        self.assertEqual(row["feature_sparse_history_penalty"], 1.0)
        self.assertEqual(row["feature_order_evidence_quality_score"], 0.0)
        self.assertEqual(row["feature_overallocation_risk_score"], 0.5)


class CannibalisationScoreMonotonicityTests(unittest.TestCase):
    def test_more_recent_prior_promos_increase_cannibalisation_risk(self) -> None:
        anchor_start = date(2024, 6, 1)
        scenarios = []
        for n_priors in (0, 1, 3, 6):
            rows = []
            for i in range(n_priors):
                start = anchor_start - timedelta(days=10 * (i + 1))
                end = start + timedelta(days=6)
                rows.append(_row(
                    store=1, sku=100, start=start, end=end,
                    discount_percent=25.0, actual_units_sold_promo=50.0,
                ))
            cand = _row(
                store=1, sku=100, start=anchor_start, end=anchor_start + timedelta(days=6),
                discount_percent=25.0,
            )
            rows.append(cand)
            scenarios.append((n_priors, rows))
        scores = []
        for n, rows in scenarios:
            frame = pd.DataFrame(rows)
            engineered = apply_ft_prior_promo_memory(frame)
            score = float(engineered.iloc[-1]["feature_prior_promo_cannibalisation_risk_score"])
            scores.append((n, score))
        # Monotonic non-decreasing in number of recent priors.
        for (n1, s1), (n2, s2) in zip(scores, scores[1:]):
            self.assertLessEqual(s1, s2 + 1e-9, msg=f"non-monotonic: n={n1}->{n2} score={s1}->{s2}")
        self.assertGreater(scores[-1][1], scores[0][1])
        for _, s in scores:
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)


class FeatureColumnContractTests(unittest.TestCase):
    def test_all_declared_columns_emitted(self) -> None:
        candidate = _row(
            store=1, sku=100, start=date(2024, 6, 1), end=date(2024, 6, 7),
            discount_percent=20.0,
        )
        result = apply_ft_prior_promo_memory(pd.DataFrame([candidate]))
        for column_name in PRIOR_PROMO_MEMORY_FEATURE_COLUMNS:
            self.assertIn(column_name, result.columns)


if __name__ == "__main__":
    unittest.main()
