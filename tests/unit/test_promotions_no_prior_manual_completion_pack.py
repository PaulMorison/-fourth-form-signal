from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_no_prior_manual_completion_pack import (  # noqa: E402
    build_promotions_no_prior_manual_completion_pack,
)


def _manual_inspection_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "review_priority_rank": 1,
                "sku_number": "3001",
                "sku_description": "Hydrating Serum",
                "department": "SKINCARE",
                "operator_decision": "NO_DEMAND",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 7.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -6.0,
                "actual_gross_profit": 100.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "manual_cause_label": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
                "manual_confidence_score": "80",
                "manual_notes": "Should be blanked in the completion pack.",
                "manual_next_action": "ADD_TO_REVIEW_RULE_CANDIDATES",
                "should_add_review_rule_candidate": "Yes",
                "should_remain_shadow_only": "No",
            },
            {
                "review_priority_rank": 1,
                "sku_number": "3002",
                "sku_description": "Night Cream",
                "department": "SKINCARE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -4.0,
                "actual_gross_profit": 75.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 3.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 3.0,
                "target_stock_day_one_units": 4.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "manual_cause_label": "",
                "manual_confidence_score": "",
                "manual_notes": "",
                "manual_next_action": "",
                "should_add_review_rule_candidate": "",
                "should_remain_shadow_only": "",
            },
        ]
    )


class PromotionsNoPriorManualCompletionPackTests(unittest.TestCase):
    def test_build_completion_pack_rows_allowed_values_checklist_summary_and_guide(self) -> None:
        result = build_promotions_no_prior_manual_completion_pack(
            manual_inspection_rows_frame=_manual_inspection_rows_frame(),
        )

        rows = result.rows_frame
        allowed_values = result.allowed_values_frame
        checklist = result.checklist_frame.set_index("sku_number")
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])

        self.assertTrue(rows["overlay_category"].eq("NO_PRIOR_DEMAND_SURPRISE_REVIEW").all())
        self.assertTrue(rows["manual_cause_label"].eq("").all())
        self.assertTrue(rows["manual_confidence_score"].eq("").all())
        self.assertTrue(rows["manual_notes"].eq("").all())
        self.assertTrue(rows["manual_next_action"].eq("").all())
        self.assertTrue(rows["should_add_review_rule_candidate"].eq("").all())
        self.assertTrue(rows["should_remain_shadow_only"].eq("").all())
        self.assertTrue(rows["cause_label_guidance"].str.len().gt(0).all())
        self.assertTrue(rows["review_completion_status"].eq("NOT_STARTED").all())

        data_gap_row = allowed_values.loc[
            (allowed_values["field_name"] == "manual_cause_label")
            & (allowed_values["allowed_value"] == "DATA_GAP_OR_LABEL_ERROR")
        ].iloc[0]
        self.assertEqual(data_gap_row["recommended_manual_next_action"], "INSPECT_DATA_QUALITY")
        random_row = allowed_values.loc[
            (allowed_values["field_name"] == "manual_cause_label")
            & (allowed_values["allowed_value"] == "RANDOM_ONE_OFF_DEMAND")
        ].iloc[0]
        self.assertEqual(str(random_row["recommended_should_add_review_rule_candidate"]), "0")

        self.assertEqual(int(checklist.loc["3001", "completion_required"]), 1)
        self.assertEqual(int(checklist.loc["3001", "has_manual_cause_label"]), 0)
        self.assertEqual(int(checklist.loc["3001", "has_confidence_score"]), 0)
        self.assertEqual(int(checklist.loc["3001", "has_manual_next_action"]), 0)
        self.assertEqual(int(checklist.loc["3001", "has_rule_candidate_flag"]), 0)
        self.assertEqual(int(checklist.loc["3001", "has_shadow_only_flag"]), 0)
        self.assertEqual(int(checklist.loc["3001", "ready_for_ingest"]), 0)
        self.assertTrue(checklist["ready_for_ingest"].eq(0).all())

        self.assertEqual(int(summary.loc[("MANUAL_COMPLETION_PACK", "ROWS_PREPARED"), "metric_value"]), 2)
        self.assertEqual(int(summary.loc[("MANUAL_COMPLETION_PACK", "READY_FOR_INGEST_ROWS"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("MANUAL_COMPLETION_PACK", "NOT_READY_ROWS"), "metric_value"]), 2)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "PRODUCTION_ORDER_CHANGES"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "STAGE12_CHANGES"), "metric_value"]), 0)

        guide_text = result.guide_markdown
        self.assertIn("This is not an order file.", guide_text)
        self.assertIn("Production order changes = 0.", guide_text)
        self.assertIn("Stage 12 changes = 0.", guide_text)
        self.assertIn("identify why these 2 SKUs sold despite weak or no prior promo evidence", guide_text)
        self.assertIn("not auto-buying", guide_text)
        self.assertIn("--worksheet-path", guide_text)
        self.assertIn("no Excel writer engine is installed", guide_text)


if __name__ == "__main__":
    unittest.main()