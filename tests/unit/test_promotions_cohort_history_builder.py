from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.cohorts import PromotionCohortAssigner, PromotionCohortHistoryBuilder  # noqa: E402
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


class PromotionCohortHistoryBuilderTests(unittest.TestCase):
    def test_history_builder_uses_only_rows_completed_before_as_of_date(self) -> None:
        dataset = _build_cohort_dataset()
        assigned = PromotionCohortAssigner().assign(dataset).frame

        history = PromotionCohortHistoryBuilder().build(
            assigned,
            as_of_date="2024-05-01",
            minimum_sample_size=1,
        )

        self.assertTrue(
            pd.to_datetime(history.historical_frame["promotional_end_date_date"], errors="coerce").lt(
                pd.Timestamp("2024-05-01")
            ).all()
        )
        mega_sale_key = assigned.loc[
            assigned["promotion_name"] == "Mega Sale",
            "cohort_key_promotion_name",
        ].iloc[0]
        expected_count = int(
            assigned.loc[
                (assigned["promotion_name"] == "Mega Sale")
                & (pd.to_datetime(assigned["promotional_end_date_date"], errors="coerce") < pd.Timestamp("2024-05-01")),
                "promotion_row_key",
            ].count()
        )
        mega_sale_summary = history.summary_frame.loc[
            (history.summary_frame["cohort_family"] == "cohort_key_promotion_name")
            & (history.summary_frame["cohort_key"] == mega_sale_key)
        ].iloc[0]
        self.assertEqual(int(mega_sale_summary["promo_count"]), expected_count)
