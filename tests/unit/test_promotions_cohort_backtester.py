from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.cohorts import (  # noqa: E402
    CohortSimilarityConfig,
    PromotionCohortBacktester,
    PromotionCohortSimilarity,
)
from state.promotions.cohorts import PromotionCohortAssigner  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_repeating_promotions_base_frame  # noqa: E402


def _build_cohort_dataset() -> object:
    base_frame = build_repeating_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    return target_result.frame.merge(
        feature_result.frame[["promotion_row_key", *feature_result.feature_columns]],
        on="promotion_row_key",
        how="left",
    )


class PromotionCohortBacktesterTests(unittest.TestCase):
    def test_similarity_score_prefers_closer_historical_archetypes(self) -> None:
        dataset = PromotionCohortAssigner().assign(_build_cohort_dataset()).frame
        planned_row = dataset.iloc[[0]].copy()
        planned_signature = planned_row.iloc[0]
        good_candidate = {
            "cohort_family": "cohort_key_archetype_secondary",
            "cohort_key": "good-archetype",
            "promo_count": 5,
            "cohort_recency_weight": 0.9,
            "cohort_sample_weight": 1.0,
            "avg_units_sold": 70.0,
            "avg_sales_ex_gst": 1120.0,
            "avg_sell_through_pct": 0.82,
            "avg_leftover_stock_pct": 0.08,
            "avg_gross_profit": 210.0,
            "avg_realised_uplift": 0.24,
            "stockout_rate": 0.10,
            "overallocation_rate": 0.12,
            "underallocation_rate": 0.08,
        }
        for regime_column in [
            "archetype_discount_depth_regime",
            "archetype_price_gap_regime",
            "archetype_offer_mechanic_regime",
            "archetype_margin_pressure_regime",
            "archetype_rebate_dependency_regime",
            "archetype_stock_pressure_regime",
            "archetype_allocation_pressure_regime",
            "archetype_overhang_risk_regime",
            "archetype_baseline_demand_regime",
            "archetype_demand_acceleration_regime",
            "archetype_zeta_instability_regime",
            "archetype_kuramoto_sync_regime",
            "archetype_gravity_regime",
            "archetype_field_density_regime",
            "archetype_context_regime",
        ]:
            good_candidate[regime_column] = planned_signature[regime_column]
        good_candidate.update(
            {
                "anchor_mean_discount_depth_pct": float(planned_signature["feature_discount_depth_pct"]),
                "anchor_mean_price_gap_pct_vs_normal": float(planned_signature["feature_price_gap_pct_vs_normal"]),
                "anchor_mean_margin_pressure": float(planned_signature["feature_effective_margin_compression_pct"]),
                "anchor_mean_rebate_dependency": float(planned_signature["feature_rebate_dependency_score"]),
                "anchor_mean_stock_pressure": float(planned_signature["feature_total_stock_pressure_ratio"]),
                "anchor_mean_allocation_pressure": float(planned_signature["feature_allocation_vs_baseline_demand_ratio"]),
                "anchor_mean_overhang_risk": float(planned_signature["feature_overhang_risk"]),
                "anchor_mean_baseline_demand": float(planned_signature["feature_pre_promo_baseline_daily_units"]),
                "anchor_mean_demand_acceleration": float(planned_signature["feature_recent_acceleration_ratio"]),
                "anchor_mean_zeta_instability": float(planned_signature["feature_composite_promo_instability"]),
                "anchor_mean_field_density": float(planned_signature["feature_field_density_score"]),
                "anchor_mean_context_density": float(planned_signature["feature_store_category_promo_density"]),
                "anchor_mean_kuramoto_sync": float(planned_signature["feature_category_sync_score"]),
                "anchor_mean_gravity_score": float(planned_signature["feature_category_gravity"]),
            }
        )
        bad_candidate = good_candidate | {
            "cohort_key": "bad-archetype",
            "archetype_discount_depth_regime": "shallow",
            "archetype_offer_mechanic_regime": "bonus",
            "archetype_margin_pressure_regime": "light",
            "anchor_mean_discount_depth_pct": 0.01,
            "anchor_mean_margin_pressure": 0.01,
            "anchor_mean_stock_pressure": 0.40,
            "anchor_mean_zeta_instability": 0.01,
            "anchor_mean_kuramoto_sync": 0.05,
        }
        candidate_history = pd.DataFrame([bad_candidate, good_candidate])

        similarity_frame = PromotionCohortSimilarity().score(
            planned_row,
            candidate_history,
            config=CohortSimilarityConfig(minimum_sample_size=1, similarity_threshold=0.50),
        )

        match = similarity_frame.iloc[0]
        self.assertEqual(match["nearest_archetype_key"], "good-archetype")
        self.assertGreater(match["nearest_archetype_similarity"], 0.75)

    def test_backtester_reports_sparse_cohort_handling_and_metrics(self) -> None:
        dataset = _build_cohort_dataset()

        backtest_result = PromotionCohortBacktester().backtest(
            dataset,
            as_of_date="2024-09-01",
            minimum_sample_size=4,
            similarity_threshold=0.55,
        )

        self.assertIn("cohort_coverage_rate", backtest_result.metrics)
        self.assertIn("regression", backtest_result.metrics)
        self.assertIn("classification", backtest_result.metrics)
        self.assertGreaterEqual(backtest_result.metrics["sparse_cohort_failure_rate"], 0.0)
        self.assertLessEqual(backtest_result.metrics["cohort_coverage_rate"], 1.0)
        self.assertIn("nearest_archetype_key", backtest_result.row_matches_frame.columns)
        self.assertIn("sparse_cohort_flag", backtest_result.row_matches_frame.columns)

    def test_backtester_generates_regression_metrics_when_history_covers_rows(self) -> None:
        dataset = _build_cohort_dataset()

        backtest_result = PromotionCohortBacktester().backtest(
            dataset,
            as_of_date="2024-09-01",
            minimum_sample_size=1,
            similarity_threshold=0.50,
        )

        self.assertGreater(backtest_result.metrics["covered_row_count"], 0)
        self.assertGreater(
            backtest_result.metrics["regression"]["units"]["row_count"],
            0,
        )
        self.assertGreaterEqual(
            backtest_result.metrics["regression"]["units"]["rmse"],
            0.0,
        )
