from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_no_prior_demand_manual_inspection import (  # noqa: E402
    build_promotions_no_prior_demand_manual_inspection,
)


def _operator_review_priority_list_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "review_priority_rank": 1,
                "sku_number": "3002",
                "sku_description": "No Prior Surprise Higher GP",
                "department": "BABY CARE",
                "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "order_units": 0.0,
                "actual_units_sold": 9.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": 4.0,
                "actual_gross_profit": 120.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 1.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 1,
                "sku_number": "3001",
                "sku_description": "No Prior Surprise Tie GP",
                "department": "SKINCARE",
                "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "order_units": 0.0,
                "actual_units_sold": 8.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": 2.0,
                "actual_gross_profit": 120.0,
                "capital_left_in_unsold_store_allocation": 5.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 1,
                "sku_number": "3003",
                "sku_description": "No Prior Surprise Lower GP",
                "department": "SKINCARE",
                "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 6.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 7.0,
                "actual_gross_profit": 80.0,
                "capital_left_in_unsold_store_allocation": 2.0,
                "current_soh_units": 1.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 4,
                "sku_number": "4001",
                "sku_description": "Capital Drag Review",
                "department": "HAIRCARE",
                "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 8.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": 6.0,
                "actual_gross_profit": 90.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 2.0,
                "proposed_review_action": "INSPECT_STRONG_CONVERTER_CAPITAL_DRAG_HEADLINE",
                "why_review_required": "Strong sell-through contradicted the visible capital-drag headline.",
                "human_review_question": "Is the capital-drag headline too harsh given strong conversion and low residual capital?",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
        ]
    )


class PromotionsNoPriorDemandManualInspectionTests(unittest.TestCase):
    def test_build_manual_inspection_rows_summary_and_memo(self) -> None:
        result = build_promotions_no_prior_demand_manual_inspection(
            operator_review_priority_list_frame=_operator_review_priority_list_frame(),
        )

        rows = result.rows_frame
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])

        self.assertEqual(rows["sku_number"].tolist(), ["3002", "3001", "3003"])
        self.assertEqual(rows["review_priority_rank"].tolist(), [1, 1, 1])
        self.assertTrue(rows["manual_cause_label"].eq("").all())
        self.assertTrue(rows["manual_confidence_score"].eq("").all())
        self.assertTrue(rows["manual_notes"].eq("").all())
        self.assertTrue(rows["manual_next_action"].eq("").all())
        self.assertTrue(rows["should_add_review_rule_candidate"].eq("").all())
        self.assertTrue(rows["should_remain_shadow_only"].eq("").all())

        self.assertEqual(int(summary.loc[("MANUAL_INSPECTION", "ROWS_PREPARED"), "metric_value"]), 3)
        self.assertAlmostEqual(
            float(summary.loc[("MANUAL_INSPECTION", "TOTAL_GROSS_PROFIT_REPRESENTED"), "metric_value"]),
            320.0,
            places=2,
        )
        self.assertAlmostEqual(
            float(summary.loc[("MANUAL_INSPECTION", "TOTAL_CAPITAL_LEFT_REPRESENTED"), "metric_value"]),
            7.0,
            places=2,
        )
        self.assertEqual(int(summary.loc[("GUARDRAIL", "PRODUCTION_ORDER_CHANGES"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "STAGE12_CHANGES"), "metric_value"]), 0)
        self.assertEqual(
            str(summary.loc[("TOP_DEPARTMENT", "RANK_1"), "metric_display"]),
            "SKINCARE (2)",
        )

        memo_text = result.memo_markdown
        self.assertIn("This is not an order file.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("learn why prior promo evidence failed", memo_text)
        self.assertIn("review these 3 rows before making any model or action-layer change", memo_text)
        self.assertIn("manual_cause_label", memo_text)
        self.assertIn("ADD_TO_REVIEW_RULE_CANDIDATES", memo_text)


if __name__ == "__main__":
    unittest.main()