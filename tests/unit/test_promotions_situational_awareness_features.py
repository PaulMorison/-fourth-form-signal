from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.model_input_quality import iter_default_model_use_feature_columns  # noqa: E402
from state.promotions.feature_engineering.demand.ft_promotion_situational_awareness import (  # noqa: E402
    PROMOTION_SITUATIONAL_AWARENESS_FEATURE_COLUMNS,
    PROMOTION_SITUATIONAL_AWARENESS_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_promotion_situational_awareness,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


class PromotionSituationalAwarenessFeatureTests(unittest.TestCase):
    def test_situational_awareness_interprets_trust_floor_before_capital_suppression(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_stock_below_trust_floor_flag": [1.0],
                "feature_projected_stock_gap_to_trust_floor_units": [1.5],
                "feature_trust_floor_missed_demand_risk_score": [0.70],
                "feature_pre_promo_cover_ratio": [0.40],
                "feature_speculative_above_trust_floor_risk_flag": [1.0],
                "feature_expected_bill_cycle_capital_drag_ratio": [0.30],
                "feature_expected_leftover_above_trust_floor_units": [4.0],
                "feature_pca_allocation_outlier_flag": [1.0],
                "feature_inventory_sufficiency_flag": [0.0],
                "feature_probability_model_use_flag": [1.0],
                "feature_same_discount_history_available_flag": [1.0],
                "feature_same_discount_prior_event_count": [4.0],
                "feature_discount_evidence_strength_score": [0.80],
                "feature_order_review_priority_score": [0.20],
                "feature_pca_structure_outlier_flag": [0.0],
            }
        )

        result = apply_ft_promotion_situational_awareness(frame)

        self.assertEqual(result.loc[0, "feature_trust_floor_pressure_state"], "protect_trust_floor")
        self.assertEqual(result.loc[0, "feature_speculative_capital_pressure_state"], "speculative_capital_high")
        self.assertEqual(result.loc[0, "feature_replenishment_confidence_state"], "replenishment_constrained")
        self.assertEqual(result.loc[0, "feature_promotion_context_quality_state"], "context_evidence_supported")
        self.assertEqual(
            result.loc[0, "feature_capital_deployment_posture"],
            "protect_trust_floor_before_capital_suppression",
        )
        self.assertIn("trust_floor=protect_trust_floor", result.loc[0, "feature_context_reason_summary"])

    def test_situational_awareness_missing_inputs_are_unavailable_not_safe(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_stock_below_trust_floor_flag": [0.0],
                "feature_inventory_sufficiency_flag": [1.0],
            }
        )

        result = apply_ft_promotion_situational_awareness(frame)

        self.assertEqual(result.loc[0, "feature_trust_floor_pressure_state"], "unavailable")
        self.assertEqual(result.loc[0, "feature_speculative_capital_pressure_state"], "unavailable")
        self.assertEqual(result.loc[0, "feature_replenishment_confidence_state"], "unavailable")
        self.assertEqual(result.loc[0, "feature_promotion_context_quality_state"], "unavailable")
        self.assertEqual(result.loc[0, "feature_capital_deployment_posture"], "review_unavailable_context")
        self.assertIn("posture=review_unavailable_context", result.loc[0, "feature_context_reason_summary"])

    def test_situational_awareness_review_only_registry_contract(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertTrue(set(PROMOTION_SITUATIONAL_AWARENESS_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertEqual(
            PROMOTION_SITUATIONAL_AWARENESS_FEATURE_COLUMNS,
            PROMOTION_SITUATIONAL_AWARENESS_REVIEW_ONLY_FEATURE_COLUMNS,
        )
        self.assertTrue(default_model_use_columns.isdisjoint(PROMOTION_SITUATIONAL_AWARENESS_FEATURE_COLUMNS))


if __name__ == "__main__":
    unittest.main()