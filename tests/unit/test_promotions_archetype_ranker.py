from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.cohorts import PromotionArchetypeRanker  # noqa: E402
from state.promotions.cohorts import PromotionCohortHistoryBuilder  # noqa: E402
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


class PromotionArchetypeRankerTests(unittest.TestCase):
    def test_ranker_emits_required_scores_and_failure_flags(self) -> None:
        dataset = _build_cohort_dataset()
        history = PromotionCohortHistoryBuilder().build(
            dataset,
            as_of_date="2024-09-01",
            minimum_sample_size=1,
        )
        archetype_history = history.archetype_history_frame.copy().reset_index(drop=True)
        archetype_history.loc[0, "avg_gross_profit"] = -25.0
        archetype_history.loc[0, "avg_leftover_stock_pct"] = 0.45
        archetype_history.loc[0, "overallocation_rate"] = 0.75
        archetype_history.loc[0, "avg_zeta_instability"] = 0.85
        archetype_history.loc[0, "avg_gravity_score"] = 0.80
        archetype_history.loc[0, "promo_count"] = 5
        archetype_history.loc[1, "avg_gross_profit"] = 40.0
        archetype_history.loc[1, "avg_sell_through_pct"] = 0.90
        archetype_history.loc[1, "avg_realised_uplift"] = 0.35
        archetype_history.loc[1, "avg_leftover_stock_pct"] = 0.05
        archetype_history.loc[1, "overallocation_rate"] = 0.05
        archetype_history.loc[1, "avg_kuramoto_sync"] = 0.90
        archetype_history.loc[1, "promo_count"] = 5

        ranking_result = PromotionArchetypeRanker().rank(archetype_history, minimum_sample_size=1)

        self.assertIn("archetype_strength_score", ranking_result.rankings_frame.columns)
        self.assertIn("archetype_destructiveness_score", ranking_result.rankings_frame.columns)
        self.assertIn("archetype_fragility_score", ranking_result.rankings_frame.columns)
        self.assertIn("archetype_repeatability_score", ranking_result.rankings_frame.columns)
        self.assertIn("archetype_confidence_score", ranking_result.rankings_frame.columns)
        self.assertGreaterEqual(len(ranking_result.failure_watchlist_frame.index), 1)
