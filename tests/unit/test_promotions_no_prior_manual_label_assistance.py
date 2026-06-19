from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_no_prior_manual_label_assistance import (  # noqa: E402
    build_promotions_no_prior_manual_label_assistance,
)


def _manual_completion_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "review_priority_rank": 1,
                "sku_number": "3001",
                "sku_description": "Hydrating Serum",
                "department": "SKINCARE",
                "actual_units_sold": 7.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -6.0,
                "actual_gross_profit": 100.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 3.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "manual_cause_label": "SHOULD_BE_BLANKED",
                "manual_confidence_score": "80",
                "manual_notes": "Should be blanked.",
                "manual_next_action": "ADD_TO_REVIEW_RULE_CANDIDATES",
                "should_add_review_rule_candidate": "Yes",
                "should_remain_shadow_only": "No",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 1,
                "sku_number": "3002",
                "sku_description": "Oral Care Pack",
                "department": "ORAL HEALTH",
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -4.0,
                "actual_gross_profit": 8.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 5.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 5.0,
                "target_stock_day_one_units": 3.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "manual_cause_label": "",
                "manual_confidence_score": "",
                "manual_notes": "",
                "manual_next_action": "",
                "should_add_review_rule_candidate": "",
                "should_remain_shadow_only": "",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 1,
                "sku_number": "3003",
                "sku_description": "Protein Bar",
                "department": "NUTRITION WELLBEIN",
                "actual_units_sold": 6.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -4.0,
                "actual_gross_profit": 4.0,
                "capital_left_in_unsold_store_allocation": 1.5,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 3.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "manual_cause_label": "",
                "manual_confidence_score": "",
                "manual_notes": "",
                "manual_next_action": "",
                "should_add_review_rule_candidate": "",
                "should_remain_shadow_only": "",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
        ]
    )


class PromotionsNoPriorManualLabelAssistanceTests(unittest.TestCase):
    def test_build_assistance_pack_keeps_manual_fields_blank_and_adds_prompts(self) -> None:
        result = build_promotions_no_prior_manual_label_assistance(
            manual_completion_rows_frame=_manual_completion_rows_frame(),
        )

        rows = result.rows_frame.set_index("sku_number")
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])
        by_department = result.by_department_frame.set_index("department")

        self.assertTrue(rows["manual_cause_label"].eq("").all())
        self.assertTrue(rows["manual_confidence_score"].eq("").all())
        self.assertTrue(rows["manual_notes"].eq("").all())
        self.assertTrue(rows["manual_next_action"].eq("").all())
        self.assertTrue(rows["should_add_review_rule_candidate"].eq("").all())
        self.assertTrue(rows["should_remain_shadow_only"].eq("").all())
        self.assertTrue(rows["do_not_auto_label_flag"].eq(1).all())

        self.assertEqual(rows.loc["3001", "inspection_priority"], "HIGH")
        self.assertIn("real and repeatable", rows.loc["3001", "primary_evidence_to_check"])
        self.assertIn("brand strength", rows.loc["3001", "secondary_evidence_to_check"])
        self.assertIn("ONLINE_OR_AVAILABILITY_EFFECT", rows.loc["3001", "possible_cause_labels_to_consider"])
        self.assertIn("choose the final manual_cause_label yourself", rows.loc["3001", "operator_decision_prompt"])

        self.assertEqual(rows.loc["3002", "inspection_priority"], "NORMAL")
        self.assertIn("essential-item demand", rows.loc["3002", "primary_evidence_to_check"])
        self.assertIn("RANDOM_ONE_OFF_DEMAND", rows.loc["3002", "possible_cause_labels_to_consider"])
        self.assertIn("Low gross profit means the operator should be especially cautious", rows.loc["3002", "candidate_caution_note"])

        self.assertIn("constrained sales", rows.loc["3003", "primary_evidence_to_check"])
        self.assertIn("health-mission demand", rows.loc["3003", "secondary_evidence_to_check"])
        self.assertIn("ONLINE_OR_AVAILABILITY_EFFECT", rows.loc["3003", "possible_cause_labels_to_consider"])

        self.assertEqual(int(summary.loc[("MANUAL_LABEL_ASSISTANCE", "ROWS_PREPARED"), "metric_value"]), 3)
        self.assertEqual(int(summary.loc[("MANUAL_LABEL_ASSISTANCE", "HIGH_PRIORITY_ROWS"), "metric_value"]), 1)
        self.assertEqual(int(summary.loc[("MANUAL_LABEL_ASSISTANCE", "DO_NOT_AUTO_LABEL_ROWS"), "metric_value"]), 3)
        self.assertEqual(int(summary.loc[("MANUAL_LABEL_ASSISTANCE", "MANUAL_FIELDS_BLANK_ROWS"), "metric_value"]), 3)
        self.assertEqual(str(summary.loc[("MANUAL_LABEL_ASSISTANCE", "RECOMMENDATION"), "metric_value"]), "COMPLETE_MANUAL_WORKSHEET_FIRST")
        self.assertEqual(int(summary.loc[("GUARDRAIL", "PRODUCTION_ORDER_CHANGES"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "STAGE12_CHANGES"), "metric_value"]), 0)

        self.assertEqual(int(by_department.loc["SKINCARE", "row_count"]), 1)
        self.assertEqual(int(by_department.loc["SKINCARE", "high_priority_rows"]), 1)
        self.assertEqual(int(by_department.loc["NUTRITION WELLBEIN", "low_availability_rows"]), 1)

        guide_text = result.guide_markdown
        self.assertIn("This is not an order file.", guide_text)
        self.assertIn("This does not complete the manual labels.", guide_text)
        self.assertIn("Production order changes = 0.", guide_text)
        self.assertIn("Stage 12 changes = 0.", guide_text)
        self.assertIn("help the operator classify the 3 rows faster and more consistently", guide_text)
        self.assertIn("The operator must still choose the final `manual_cause_label`", guide_text)
        self.assertIn("Any candidate remains shadow-only until repeated evidence appears across more promotions.", guide_text)


if __name__ == "__main__":
    unittest.main()