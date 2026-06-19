from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_no_prior_operator_review_sequence import (  # noqa: E402
    build_promotions_no_prior_operator_review_sequence,
)


def _assistance_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "3001",
                "sku_description": "Hydrating Serum",
                "department": "SKINCARE",
                "actual_units_sold": 8.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -9.0,
                "actual_gross_profit": 120.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 8.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 8.0,
                "target_stock_day_one_units": 4.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "inspection_priority": "HIGH",
                "primary_evidence_to_check": "Check whether the demand was real and repeatable rather than a one-off surprise.",
                "secondary_evidence_to_check": "Check brand strength, category trust, gift or beauty mission, and promo mechanic.",
                "possible_cause_labels_to_consider": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED, PRICE_OR_PROMO_MECHANIC_EFFECT",
                "candidate_caution_note": "Keep candidate judgement conservative.",
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
                "sku_number": "3002",
                "sku_description": "Oral Care Pack",
                "department": "ORAL HEALTH",
                "actual_units_sold": 9.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -8.0,
                "actual_gross_profit": 75.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 9.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 9.0,
                "target_stock_day_one_units": 4.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "inspection_priority": "HIGH",
                "primary_evidence_to_check": "Check whether the demand was real and repeatable rather than a one-off surprise.",
                "secondary_evidence_to_check": "Check essential-item demand, basket completion, and price sensitivity.",
                "possible_cause_labels_to_consider": "BASKET_OR_MISSION_EFFECT, PRICE_OR_PROMO_MECHANIC_EFFECT",
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
                "sku_number": "3003",
                "sku_description": "Vitamin C Serum",
                "department": "SKINCARE",
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -4.0,
                "actual_gross_profit": 30.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 10.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 10.0,
                "target_stock_day_one_units": 4.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "inspection_priority": "NORMAL",
                "primary_evidence_to_check": "Check brand strength, category trust, gift or beauty mission, and promo mechanic.",
                "secondary_evidence_to_check": "Check nearby stores, promo mechanic, and any data gaps before choosing the final cause label.",
                "possible_cause_labels_to_consider": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED, BASKET_OR_MISSION_EFFECT",
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
            {
                "sku_number": "3004",
                "sku_description": "Pocket Tissues",
                "department": "PAPER COTTON",
                "actual_units_sold": 6.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -6.0,
                "actual_gross_profit": 18.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 4.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "inspection_priority": "NORMAL",
                "primary_evidence_to_check": "Check whether low stock or projected on-hand may have constrained sales.",
                "secondary_evidence_to_check": "Check store context, promo mechanic, and whether demand looks repeatable.",
                "possible_cause_labels_to_consider": "ONLINE_OR_AVAILABILITY_EFFECT, STORE_SPECIFIC_DEMAND_NOT_CAPTURED",
                "candidate_caution_note": "Availability may be masking the cause.",
                "shadow_only_note": "Any candidate remains shadow-only until repeated evidence appears across more promotions.",
                "operator_decision_prompt": "Choose the final manual_cause_label yourself.",
                "do_not_auto_label_flag": 1,
                "manual_cause_label": "SHOULD_BE_BLANKED",
                "manual_confidence_score": "60",
                "manual_notes": "Should be blanked.",
                "manual_next_action": "KEEP_SHADOW_ONLY",
                "should_add_review_rule_candidate": "No",
                "should_remain_shadow_only": "Yes",
            },
            {
                "sku_number": "3005",
                "sku_description": "Protein Bar",
                "department": "NUTRITION WELLBEIN",
                "actual_units_sold": 4.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -2.0,
                "actual_gross_profit": 6.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 9.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 9.0,
                "target_stock_day_one_units": 4.0,
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "inspection_priority": "NORMAL",
                "primary_evidence_to_check": "Check health-mission demand and stock availability.",
                "secondary_evidence_to_check": "Check nearby stores and any data gaps before choosing the final cause label.",
                "possible_cause_labels_to_consider": "BASKET_OR_MISSION_EFFECT, RANDOM_ONE_OFF_DEMAND",
                "candidate_caution_note": "Low gross profit means the operator should be especially cautious.",
                "shadow_only_note": "Any candidate remains shadow-only until repeated evidence appears across more promotions.",
                "operator_decision_prompt": "Choose the final manual_cause_label yourself.",
                "do_not_auto_label_flag": 1,
                "manual_cause_label": "SHOULD_BE_BLANKED",
                "manual_confidence_score": "50",
                "manual_notes": "Should be blanked.",
                "manual_next_action": "KEEP_SHADOW_ONLY",
                "should_add_review_rule_candidate": "No",
                "should_remain_shadow_only": "Yes",
            },
        ]
    )


class PromotionsNoPriorOperatorReviewSequenceTests(unittest.TestCase):
    def test_build_sequence_ranks_rows_without_filling_manual_labels(self) -> None:
        result = build_promotions_no_prior_operator_review_sequence(
            manual_label_assistance_rows_frame=_assistance_rows_frame(),
        )

        rows = result.rows_frame.set_index("sku_number")
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])
        by_department = result.by_department_frame.set_index("department")

        self.assertEqual(result.rows_frame["operator_review_sequence_rank"].tolist(), [1, 2, 3, 4, 5])
        self.assertEqual(result.rows_frame["sku_number"].tolist(), ["3001", "3002", "3003", "3004", "3005"])

        self.assertTrue(rows["manual_cause_label"].eq("").all())
        self.assertTrue(rows["manual_confidence_score"].eq("").all())
        self.assertTrue(rows["manual_notes"].eq("").all())
        self.assertTrue(rows["manual_next_action"].eq("").all())
        self.assertTrue(rows["should_add_review_rule_candidate"].eq("").all())
        self.assertTrue(rows["should_remain_shadow_only"].eq("").all())
        self.assertTrue(rows["do_not_auto_label_flag"].eq(1).all())

        self.assertEqual(rows.loc["3001", "review_sequence_group"], "BATCH_1_FAST_HIGH_VALUE")
        self.assertEqual(rows.loc["3001", "expected_learning_value"], "VERY_HIGH")
        self.assertEqual(int(rows.loc["3001", "recommended_review_time_minutes"]), 5)

        self.assertEqual(rows.loc["3002", "review_sequence_group"], "BATCH_1_FAST_HIGH_VALUE")
        self.assertEqual(rows.loc["3002", "review_batch"], "BATCH_1")

        self.assertEqual(rows.loc["3003", "review_sequence_group"], "BATCH_2_CATEGORY_PATTERN_CHECK")
        self.assertEqual(rows.loc["3003", "estimated_review_difficulty"], "LOW")
        self.assertEqual(int(rows.loc["3003", "recommended_review_time_minutes"]), 3)

        self.assertEqual(rows.loc["3004", "review_sequence_group"], "BATCH_3_OPERATIONAL_OR_AVAILABILITY_CHECK")
        self.assertEqual(rows.loc["3004", "estimated_review_difficulty"], "HIGH")
        self.assertEqual(int(rows.loc["3004", "recommended_review_time_minutes"]), 8)

        self.assertEqual(rows.loc["3005", "review_sequence_group"], "BATCH_4_LOW_VALUE_OR_UNCLEAR")
        self.assertEqual(rows.loc["3005", "expected_learning_value"], "LOW")

        self.assertEqual(int(summary.loc[("OPERATOR_REVIEW_SEQUENCE", "ROWS_SEQUENCED"), "metric_value"]), 5)
        self.assertEqual(int(summary.loc[("OPERATOR_REVIEW_SEQUENCE", "BATCH_1_ROWS"), "metric_value"]), 2)
        self.assertEqual(int(summary.loc[("OPERATOR_REVIEW_SEQUENCE", "BATCH_2_ROWS"), "metric_value"]), 1)
        self.assertEqual(int(summary.loc[("OPERATOR_REVIEW_SEQUENCE", "BATCH_3_ROWS"), "metric_value"]), 1)
        self.assertEqual(int(summary.loc[("OPERATOR_REVIEW_SEQUENCE", "BATCH_4_ROWS"), "metric_value"]), 1)
        self.assertEqual(int(summary.loc[("OPERATOR_REVIEW_SEQUENCE", "MANUAL_FIELDS_BLANK_ROWS"), "metric_value"]), 5)
        self.assertEqual(int(summary.loc[("OPERATOR_REVIEW_SEQUENCE", "SEQUENCE_RANK_GAP_COUNT"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("VALIDATION", "DO_NOT_AUTO_LABEL_WARNING_ROWS"), "metric_value"]), 0)
        self.assertEqual(str(summary.loc[("OPERATOR_REVIEW_SEQUENCE", "RECOMMENDATION"), "metric_value"]), "START_WITH_BATCH_1_FAST_HIGH_VALUE")
        self.assertEqual(int(summary.loc[("GUARDRAIL", "PRODUCTION_ORDER_CHANGES"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "STAGE12_CHANGES"), "metric_value"]), 0)

        self.assertEqual(int(by_department.loc["SKINCARE", "row_count"]), 2)
        self.assertEqual(int(by_department.loc["SKINCARE", "batch_1_rows"]), 1)
        self.assertEqual(int(by_department.loc["SKINCARE", "batch_2_rows"]), 1)
        self.assertEqual(int(by_department.loc["ORAL HEALTH", "first_sequence_rank"]), 2)

        guide_text = result.guide_markdown
        self.assertIn("This is not an order file.", guide_text)
        self.assertIn("This does not infer labels.", guide_text)
        self.assertIn("Production order changes = 0.", guide_text)
        self.assertIn("Stage 12 changes = 0.", guide_text)
        self.assertIn("The goal is to complete the 5 manual labels efficiently.", guide_text)
        self.assertIn("Recommend starting with BATCH_1_FAST_HIGH_VALUE.", guide_text)
        self.assertIn("Candidate decisions remain shadow-only until repeated evidence appears across more promotions.", guide_text)

    def test_build_sequence_surfaces_do_not_auto_label_warning(self) -> None:
        source = _assistance_rows_frame()
        source.loc[source["sku_number"] == "3005", "do_not_auto_label_flag"] = 0

        result = build_promotions_no_prior_operator_review_sequence(
            manual_label_assistance_rows_frame=source,
        )

        rows = result.rows_frame.set_index("sku_number")
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])

        self.assertEqual(int(rows.loc["3005", "do_not_auto_label_flag"]), 0)
        self.assertEqual(int(summary.loc[("VALIDATION", "DO_NOT_AUTO_LABEL_WARNING_ROWS"), "metric_value"]), 1)


if __name__ == "__main__":
    unittest.main()