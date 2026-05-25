from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.cohorts import PromotionDecisionFusion, PromotionDecisionFusionConfig  # noqa: E402


def _fusion_input_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "promotion_row_key": "high-confidence",
                "predicted_units_sold": 90.0,
                "predicted_sales_ex_gst": 1350.0,
                "predicted_gross_profit_dollars": 280.0,
                "predicted_sell_through_pct": 0.88,
                "predicted_overallocation_risk": 0.12,
                "predicted_underallocation_risk": 0.10,
                "predicted_stockout_risk": 0.14,
                "row_model_confidence_score": 0.82,
                "nearest_archetype_similarity": 0.84,
                "nearest_archetype_sample_size": 12,
                "nearest_archetype_expected_units": 88.0,
                "nearest_archetype_expected_sales_ex_gst": 1320.0,
                "nearest_archetype_expected_gp": 255.0,
                "nearest_archetype_expected_sell_through": 0.85,
                "nearest_archetype_expected_leftover": 0.08,
                "nearest_archetype_expected_uplift": 0.24,
                "nearest_archetype_expected_overallocation_rate": 0.10,
                "nearest_archetype_expected_underallocation_rate": 0.08,
                "nearest_archetype_expected_stockout_rate": 0.15,
                "nearest_archetype_confidence_score": 0.79,
                "nearest_archetype_destructiveness_score": 0.18,
                "nearest_archetype_repeatability_score": 0.85,
                "nearest_archetype_fragility_score": 0.18,
                "feature_composite_promo_instability": 0.12,
                "cohort_coverage_flag": 1,
                "sparse_cohort_flag": 0,
            },
            {
                "promotion_row_key": "sparse-history",
                "predicted_units_sold": 90.0,
                "predicted_sales_ex_gst": 1350.0,
                "predicted_gross_profit_dollars": 280.0,
                "predicted_sell_through_pct": 0.88,
                "predicted_overallocation_risk": 0.12,
                "predicted_underallocation_risk": 0.10,
                "predicted_stockout_risk": 0.14,
                "row_model_confidence_score": 0.82,
                "nearest_archetype_similarity": 0.84,
                "nearest_archetype_sample_size": 1,
                "nearest_archetype_expected_units": 88.0,
                "nearest_archetype_expected_sales_ex_gst": 1320.0,
                "nearest_archetype_expected_gp": 255.0,
                "nearest_archetype_expected_sell_through": 0.85,
                "nearest_archetype_expected_leftover": 0.08,
                "nearest_archetype_expected_uplift": 0.24,
                "nearest_archetype_expected_overallocation_rate": 0.10,
                "nearest_archetype_expected_underallocation_rate": 0.08,
                "nearest_archetype_expected_stockout_rate": 0.15,
                "nearest_archetype_confidence_score": 0.25,
                "nearest_archetype_destructiveness_score": 0.18,
                "nearest_archetype_repeatability_score": 0.40,
                "nearest_archetype_fragility_score": 0.48,
                "feature_composite_promo_instability": 0.12,
                "cohort_coverage_flag": 1,
                "sparse_cohort_flag": 1,
            },
            {
                "promotion_row_key": "disagreement",
                "predicted_units_sold": 98.0,
                "predicted_sales_ex_gst": 1500.0,
                "predicted_gross_profit_dollars": 310.0,
                "predicted_sell_through_pct": 0.92,
                "predicted_overallocation_risk": 0.08,
                "predicted_underallocation_risk": 0.08,
                "predicted_stockout_risk": 0.10,
                "row_model_confidence_score": 0.78,
                "nearest_archetype_similarity": 0.74,
                "nearest_archetype_sample_size": 9,
                "nearest_archetype_expected_units": 34.0,
                "nearest_archetype_expected_sales_ex_gst": 490.0,
                "nearest_archetype_expected_gp": -25.0,
                "nearest_archetype_expected_sell_through": 0.28,
                "nearest_archetype_expected_leftover": 0.46,
                "nearest_archetype_expected_uplift": 0.02,
                "nearest_archetype_expected_overallocation_rate": 0.72,
                "nearest_archetype_expected_underallocation_rate": 0.14,
                "nearest_archetype_expected_stockout_rate": 0.20,
                "nearest_archetype_confidence_score": 0.70,
                "nearest_archetype_destructiveness_score": 0.82,
                "nearest_archetype_repeatability_score": 0.18,
                "nearest_archetype_fragility_score": 0.72,
                "feature_composite_promo_instability": 0.64,
                "cohort_coverage_flag": 1,
                "sparse_cohort_flag": 0,
            },
        ]
    )


class PromotionDecisionFusionTests(unittest.TestCase):
    def test_fusion_weighting_behaves_monotonically(self) -> None:
        result = PromotionDecisionFusion().fuse(
            _fusion_input_frame(),
            config=PromotionDecisionFusionConfig(),
        )

        fused = result.decision_surface_frame.set_index("promotion_row_key")
        self.assertGreater(
            fused.loc["high-confidence", "final_decision_score"],
            fused.loc["disagreement", "final_decision_score"],
        )
        self.assertGreater(
            fused.loc["high-confidence", "final_confidence_score"],
            fused.loc["disagreement", "final_confidence_score"],
        )

    def test_sparse_history_reduces_confidence(self) -> None:
        result = PromotionDecisionFusion().fuse(_fusion_input_frame())
        fused = result.decision_surface_frame.set_index("promotion_row_key")

        self.assertGreater(
            fused.loc["sparse-history", "sparse_history_penalty"],
            fused.loc["high-confidence", "sparse_history_penalty"],
        )
        self.assertLess(
            fused.loc["sparse-history", "final_confidence_score"],
            fused.loc["high-confidence", "final_confidence_score"],
        )

    def test_row_cohort_disagreement_is_surfaced(self) -> None:
        result = PromotionDecisionFusion().fuse(_fusion_input_frame())
        fused = result.decision_surface_frame.set_index("promotion_row_key")

        self.assertGreater(
            fused.loc["disagreement", "row_cohort_disagreement_score"],
            0.50,
        )
        self.assertLess(
            fused.loc["disagreement", "decision_alignment_score"],
            0.50,
        )
        self.assertIn(
            "disagree",
            fused.loc["disagreement", "decision_recommendation_reason"],
        )
