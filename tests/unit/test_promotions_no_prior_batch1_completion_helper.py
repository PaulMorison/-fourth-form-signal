from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_no_prior_batch1_completion_helper import (  # noqa: E402
    build_promotions_no_prior_batch1_completion_helper,
)
from runtime.promotions.run_promotions_no_prior_manual_inspection_ingest import (  # noqa: E402
    build_promotions_no_prior_manual_inspection_ingest,
)


def _operator_review_sequence_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "operator_review_sequence_rank": 1,
                "review_sequence_group": "BATCH_1_FAST_HIGH_VALUE",
                "review_sequence_reason": "High gross profit and large forecast miss.",
                "expected_learning_value": "VERY_HIGH",
                "estimated_review_difficulty": "HIGH",
                "recommended_review_time_minutes": 8,
                "review_batch": "BATCH_1",
                "sku_number": "3001",
                "sku_description": "Hydrating Serum",
                "department": "SKINCARE",
                "actual_units_sold": 8.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -9.0,
                "actual_gross_profit": 120.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 3.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "inspection_priority": "HIGH",
                "primary_evidence_to_check": "Check whether the demand was real and repeatable rather than a one-off surprise.",
                "secondary_evidence_to_check": "Check brand strength and availability.",
                "possible_cause_labels_to_consider": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED, ONLINE_OR_AVAILABILITY_EFFECT",
                "candidate_caution_note": "Availability may be masking the cause.",
                "shadow_only_note": "Any candidate remains shadow-only until repeated evidence appears across more promotions.",
                "operator_decision_prompt": "Choose the final manual_cause_label yourself.",
                "do_not_auto_label_flag": 1,
                "manual_cause_label": "SHOULD_BE_BLANKED",
                "manual_confidence_score": "90",
                "manual_notes": "Should be blanked.",
                "manual_next_action": "ADD_TO_REVIEW_RULE_CANDIDATES",
                "should_add_review_rule_candidate": "Yes",
                "should_remain_shadow_only": "No",
            },
            {
                "operator_review_sequence_rank": 2,
                "review_sequence_group": "BATCH_1_FAST_HIGH_VALUE",
                "review_sequence_reason": "High gross profit and fast learning potential.",
                "expected_learning_value": "HIGH",
                "estimated_review_difficulty": "MEDIUM",
                "recommended_review_time_minutes": 5,
                "review_batch": "BATCH_1",
                "sku_number": "3002",
                "sku_description": "Peptide Serum",
                "department": "SKINCARE",
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -4.0,
                "actual_gross_profit": 75.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 5.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 5.0,
                "target_stock_day_one_units": 3.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "inspection_priority": "HIGH",
                "primary_evidence_to_check": "Check brand strength and category trust.",
                "secondary_evidence_to_check": "Check nearby stores and promo mechanic.",
                "possible_cause_labels_to_consider": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED, PRICE_OR_PROMO_MECHANIC_EFFECT",
                "candidate_caution_note": "Keep candidate judgement conservative.",
                "shadow_only_note": "Any candidate remains shadow-only until repeated evidence appears across more promotions.",
                "operator_decision_prompt": "Choose the final manual_cause_label yourself.",
                "do_not_auto_label_flag": 1,
                "manual_cause_label": "SHOULD_BE_BLANKED",
                "manual_confidence_score": "80",
                "manual_notes": "Should be blanked.",
                "manual_next_action": "ADD_TO_REVIEW_RULE_CANDIDATES",
                "should_add_review_rule_candidate": "Yes",
                "should_remain_shadow_only": "No",
            },
            {
                "operator_review_sequence_rank": 9,
                "review_sequence_group": "BATCH_2_CATEGORY_PATTERN_CHECK",
                "review_sequence_reason": "Review similar category rows together.",
                "expected_learning_value": "HIGH",
                "estimated_review_difficulty": "MEDIUM",
                "recommended_review_time_minutes": 5,
                "review_batch": "BATCH_2",
                "sku_number": "3003",
                "sku_description": "Vitamin C Serum",
                "department": "SKINCARE",
                "actual_units_sold": 7.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -6.0,
                "actual_gross_profit": 30.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 6.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 6.0,
                "target_stock_day_one_units": 3.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "inspection_priority": "NORMAL",
                "primary_evidence_to_check": "Check category pattern.",
                "secondary_evidence_to_check": "Check nearby stores.",
                "possible_cause_labels_to_consider": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
                "candidate_caution_note": "Keep candidate judgement conservative.",
                "shadow_only_note": "Any candidate remains shadow-only until repeated evidence appears across more promotions.",
                "operator_decision_prompt": "Choose the final manual_cause_label yourself.",
                "do_not_auto_label_flag": 1,
                "manual_cause_label": "SHOULD_BE_BLANKED",
                "manual_confidence_score": "70",
                "manual_notes": "Should be blanked.",
                "manual_next_action": "KEEP_SHADOW_ONLY",
                "should_add_review_rule_candidate": "No",
                "should_remain_shadow_only": "Yes",
            },
        ]
    )


def _manual_completion_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "review_priority_rank": 11,
                "sku_number": "3001",
                "operator_decision": "NO_DEMAND",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
            },
            {
                "review_priority_rank": 12,
                "sku_number": "3002",
                "operator_decision": "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
            },
            {
                "review_priority_rank": 21,
                "sku_number": "3003",
                "operator_decision": "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
            },
        ]
    )


class PromotionsNoPriorBatch1CompletionHelperTests(unittest.TestCase):
    def test_build_batch1_helper_filters_rows_and_keeps_manual_fields_blank(self) -> None:
        result = build_promotions_no_prior_batch1_completion_helper(
            operator_review_sequence_rows_frame=_operator_review_sequence_rows_frame(),
            manual_completion_rows_frame=_manual_completion_rows_frame(),
        )

        rows = result.rows_frame.set_index("sku_number")
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])

        self.assertEqual(result.rows_frame["sku_number"].tolist(), ["3001", "3002"])
        self.assertEqual(result.rows_frame["operator_review_sequence_rank"].tolist(), [1, 2])
        self.assertEqual(result.rows_frame["review_priority_rank"].tolist(), [1.0, 2.0])
        self.assertTrue(rows["manual_cause_label"].eq("").all())
        self.assertTrue(rows["manual_confidence_score"].eq("").all())
        self.assertTrue(rows["manual_notes"].eq("").all())
        self.assertTrue(rows["manual_next_action"].eq("").all())
        self.assertTrue(rows["should_add_review_rule_candidate"].eq("").all())
        self.assertTrue(rows["should_remain_shadow_only"].eq("").all())
        self.assertTrue(rows["do_not_auto_label_flag"].eq(1).all())
        self.assertTrue(rows["completion_required_flag"].eq(1).all())
        self.assertTrue(rows["review_sequence_group"].eq("BATCH_1_FAST_HIGH_VALUE").all())
        self.assertTrue(rows["review_batch"].eq("BATCH_1").all())
        self.assertEqual(rows.loc["3001", "operator_decision"], "NO_DEMAND")
        self.assertEqual(rows.loc["3001", "operator_action"], "REVIEW")
        self.assertEqual(float(rows.loc["3001", "order_units"]), 0.0)
        self.assertEqual(rows.loc["3001", "proposed_review_action"], "INSPECT_NO_PRIOR_DEMAND_SURPRISE")

        self.assertIn("Complete the manual fields for Batch 1 rank 1 first", rows.loc["3001", "batch1_review_instruction"])
        self.assertIn("Start with:", rows.loc["3001", "what_to_check_first"])
        self.assertIn("ADD_TO_REVIEW_RULE_CANDIDATES", rows.loc["3001", "candidate_threshold_reminder"])
        self.assertIn("KEEP_SHADOW_ONLY", rows.loc["3001", "candidate_threshold_reminder"])

        self.assertEqual(int(summary.loc[("BATCH1_COMPLETION_HELPER", "ROWS_PREPARED"), "metric_value"]), 2)
        self.assertEqual(int(summary.loc[("BATCH1_COMPLETION_HELPER", "DO_NOT_AUTO_LABEL_ROWS"), "metric_value"]), 2)
        self.assertEqual(int(summary.loc[("BATCH1_COMPLETION_HELPER", "MANUAL_FIELDS_BLANK_ROWS"), "metric_value"]), 2)
        self.assertEqual(int(summary.loc[("BATCH1_COMPLETION_HELPER", "COMPLETION_REQUIRED_ROWS"), "metric_value"]), 2)
        self.assertEqual(float(summary.loc[("BATCH1_COMPLETION_HELPER", "TOTAL_GROSS_PROFIT_REPRESENTED"), "metric_value"]), 195.0)
        self.assertEqual(int(summary.loc[("BATCH1_COMPLETION_HELPER", "FIRST_SEQUENCE_RANK"), "metric_value"]), 1)
        self.assertEqual(int(summary.loc[("BATCH1_COMPLETION_HELPER", "LAST_SEQUENCE_RANK"), "metric_value"]), 2)
        self.assertEqual(int(summary.loc[("BATCH1_COMPLETION_HELPER", "SEQUENCE_RANK_GAP_COUNT"), "metric_value"]), 0)
        self.assertEqual(str(summary.loc[("BATCH1_COMPLETION_HELPER", "RECOMMENDATION"), "metric_value"]), "COMPLETE_BATCH1_FIRST")
        self.assertEqual(int(summary.loc[("VALIDATION", "DO_NOT_AUTO_LABEL_WARNING_ROWS"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "PRODUCTION_ORDER_CHANGES"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "STAGE12_CHANGES"), "metric_value"]), 0)

        guide_text = result.guide_markdown
        self.assertIn("This is not an order file.", guide_text)
        self.assertIn("This does not infer labels.", guide_text)
        self.assertIn("Production order changes = 0.", guide_text)
        self.assertIn("Stage 12 changes = 0.", guide_text)
        self.assertIn("The purpose is to complete only Batch 1 first", guide_text)
        self.assertIn("fastest high-value learning potential", guide_text)
        self.assertIn("paste those manual fields back into the main no_prior_manual_completion_rows.csv file", guide_text)
        self.assertIn("--worksheet-path", guide_text)
        self.assertIn("Candidate decisions remain shadow-only until repeated evidence appears across more promotions.", guide_text)
        self.assertIn("BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED", guide_text)
        self.assertIn("ADD_TO_REVIEW_RULE_CANDIDATES", guide_text)

        validated = build_promotions_no_prior_manual_inspection_ingest(
            manual_inspection_rows_frame=result.rows_frame,
        )
        validated_rows = validated.validated_rows_frame.set_index("sku_number")
        self.assertEqual(validated_rows.loc["3001", "manual_review_status"], "INCOMPLETE")
        self.assertEqual(validated_rows.loc["3002", "manual_review_status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()