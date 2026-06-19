from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_no_prior_manual_inspection_ingest import (  # noqa: E402
    BATCH_1_FAST_HIGH_VALUE,
    FULL_NO_PRIOR_18,
    build_promotions_no_prior_manual_inspection_ingest,
)


def _manual_inspection_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "review_priority_rank": 1,
                "sku_number": "2001",
                "sku_description": "Brand Repeatable Candidate",
                "department": "SKINCARE",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 10.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": -8.0,
                "actual_gross_profit": 120.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 3.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 3.0,
                "target_stock_day_one_units": 4.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "manual_cause_label": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
                "manual_confidence_score": "85",
                "manual_notes": "Repeated prestige demand pattern.",
                "manual_next_action": "ADD_TO_REVIEW_RULE_CANDIDATES",
                "should_add_review_rule_candidate": "Yes",
                "should_remain_shadow_only": "TRUE",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 1,
                "sku_number": "2002",
                "sku_description": "Data Quality Investigation",
                "department": "SKINCARE",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 6.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -5.0,
                "actual_gross_profit": 55.0,
                "capital_left_in_unsold_store_allocation": 4.0,
                "current_soh_units": 1.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 2.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "manual_cause_label": "DATA_GAP_OR_LABEL_ERROR",
                "manual_confidence_score": "72",
                "manual_notes": "Promo flag looked incomplete.",
                "manual_next_action": "INSPECT_DATA_QUALITY",
                "should_add_review_rule_candidate": "No",
                "should_remain_shadow_only": "Yes",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 1,
                "sku_number": "2003",
                "sku_description": "One Off Demand",
                "department": "NUTRITION WELLBEIN",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 4.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -3.0,
                "actual_gross_profit": 25.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 2.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "manual_cause_label": "RANDOM_ONE_OFF_DEMAND",
                "manual_confidence_score": "90",
                "manual_notes": "Single-store anomaly.",
                "manual_next_action": "NO_CHANGE",
                "should_add_review_rule_candidate": "0",
                "should_remain_shadow_only": "1",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 1,
                "sku_number": "2004",
                "sku_description": "Incomplete Review",
                "department": "ORAL HEALTH",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 3.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -2.0,
                "actual_gross_profit": 12.0,
                "capital_left_in_unsold_store_allocation": 1.0,
                "current_soh_units": 1.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 1.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
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
                "sku_number": "2005",
                "sku_description": "Invalid Review",
                "department": "SKINCARE",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -4.0,
                "actual_gross_profit": 15.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 2.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "manual_cause_label": "MAYBE_REPEATABLE",
                "manual_confidence_score": "abc",
                "manual_notes": "Freeform invalid entry.",
                "manual_next_action": "BUY_NOW",
                "should_add_review_rule_candidate": "maybe",
                "should_remain_shadow_only": "later",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "review_priority_rank": 1,
                "sku_number": "2006",
                "sku_description": "Low Confidence Store Specific",
                "department": "SKINCARE",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 7.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": -5.0,
                "actual_gross_profit": 40.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "human_review_question": "Why did this SKU sell despite weak/no prior promo evidence?",
                "manual_cause_label": "STORE_SPECIFIC_DEMAND_NOT_CAPTURED",
                "manual_confidence_score": "69",
                "manual_notes": "Looks local but not strong enough.",
                "manual_next_action": "ADD_TO_REVIEW_RULE_CANDIDATES",
                "should_add_review_rule_candidate": "1",
                "should_remain_shadow_only": "1",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
        ]
    )


class PromotionsNoPriorManualInspectionIngestTests(unittest.TestCase):
    def test_build_ingest_outputs_with_complete_incomplete_invalid_and_candidates(self) -> None:
        result = build_promotions_no_prior_manual_inspection_ingest(
            manual_inspection_rows_frame=_manual_inspection_rows_frame(),
            inspection_scope=FULL_NO_PRIOR_18,
        )

        validated_rows = result.validated_rows_frame.set_index("sku_number")
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])
        by_cause = result.by_cause_frame.set_index("manual_cause_label_group")
        candidates = result.candidate_frame

        self.assertEqual(validated_rows.loc["2001", "manual_review_status"], "COMPLETE")
        self.assertEqual(validated_rows.loc["2004", "manual_review_status"], "INCOMPLETE")
        self.assertEqual(validated_rows.loc["2005", "manual_review_status"], "INVALID")
        self.assertTrue(validated_rows["inspection_scope"].eq(FULL_NO_PRIOR_18).all())
        self.assertTrue(validated_rows["expected_scope_rows"].eq(18).all())
        self.assertTrue(validated_rows["actual_scope_rows"].eq(6).all())
        self.assertTrue(validated_rows["partial_review_flag"].eq(0).all())
        self.assertIn("manual_cause_label is not an allowed value", validated_rows.loc["2005", "validation_issue"])
        self.assertEqual(validated_rows.loc["2001", "candidate_ready_flag"], 1)
        self.assertEqual(validated_rows.loc["2006", "candidate_ready_flag"], 0)
        self.assertEqual(validated_rows.loc["2001", "normalized_should_add_review_rule_candidate"], 1)
        self.assertEqual(
            validated_rows.loc["2001", "proposed_review_rule_candidate"],
            "NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE",
        )

        self.assertEqual(int(summary.loc[("MANUAL_INSPECTION_INGEST", "INPUT_ROWS"), "metric_value"]), 6)
        self.assertEqual(int(summary.loc[("MANUAL_INSPECTION_INGEST", "COMPLETE_ROWS"), "metric_value"]), 4)
        self.assertEqual(int(summary.loc[("MANUAL_INSPECTION_INGEST", "INCOMPLETE_ROWS"), "metric_value"]), 1)
        self.assertEqual(int(summary.loc[("MANUAL_INSPECTION_INGEST", "INVALID_ROWS"), "metric_value"]), 1)
        self.assertEqual(int(summary.loc[("MANUAL_INSPECTION_INGEST", "CANDIDATE_READY_ROWS"), "metric_value"]), 1)
        self.assertTrue(result.summary_frame["inspection_scope"].eq(FULL_NO_PRIOR_18).all())
        self.assertTrue(result.summary_frame["expected_scope_rows"].eq(18).all())
        self.assertTrue(result.summary_frame["actual_scope_rows"].eq(6).all())
        self.assertTrue(result.summary_frame["partial_review_flag"].eq(0).all())
        self.assertAlmostEqual(
            float(summary.loc[("CANDIDATE_FINANCIALS", "CANDIDATE_GROSS_PROFIT_REPRESENTED"), "metric_value"]),
            120.0,
            places=2,
        )
        self.assertAlmostEqual(
            float(summary.loc[("CANDIDATE_FINANCIALS", "CANDIDATE_CAPITAL_LEFT_REPRESENTED"), "metric_value"]),
            0.0,
            places=2,
        )
        self.assertEqual(int(summary.loc[("GUARDRAIL", "PRODUCTION_ORDER_CHANGES"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "STAGE12_CHANGES"), "metric_value"]), 0)

        self.assertEqual(int(by_cause.loc["UNASSIGNED", "incomplete_rows"]), 1)
        self.assertEqual(int(by_cause.loc["BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED", "candidate_ready_rows"]), 1)
        self.assertEqual(str(by_cause.loc["RANDOM_ONE_OFF_DEMAND", "cause_group_type"]), "ONE_OFF_DEMAND")

        self.assertEqual(candidates["sku_number"].tolist(), ["2001"])
        self.assertEqual(
            candidates.loc[0, "proposed_review_rule_candidate"],
            "NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE",
        )
        self.assertIn("shadow-only review-rule candidate", candidates.loc[0, "candidate_reason"])

        memo_text = result.memo_markdown
        self.assertIn("This is not an order file.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("classified 4 complete, 1 incomplete, and 1 invalid rows", memo_text)
        self.assertIn("Candidate-ready rows = 1", memo_text)
        self.assertIn("Repeatable manual causes:", memo_text)
        self.assertIn("One-off demand labels:", memo_text)
        self.assertIn("keep any review-rule candidates shadow-only until repeated evidence appears", memo_text)

    def test_build_ingest_adds_batch1_scope_metadata(self) -> None:
        result = build_promotions_no_prior_manual_inspection_ingest(
            manual_inspection_rows_frame=_manual_inspection_rows_frame().head(2).copy(),
            inspection_scope=BATCH_1_FAST_HIGH_VALUE,
        )

        self.assertTrue(result.validated_rows_frame["inspection_scope"].eq(BATCH_1_FAST_HIGH_VALUE).all())
        self.assertTrue(result.validated_rows_frame["expected_scope_rows"].eq(8).all())
        self.assertTrue(result.validated_rows_frame["actual_scope_rows"].eq(2).all())
        self.assertTrue(result.validated_rows_frame["partial_review_flag"].eq(1).all())
        self.assertTrue(result.by_cause_frame["inspection_scope"].eq(BATCH_1_FAST_HIGH_VALUE).all())
        self.assertTrue(result.summary_frame["inspection_scope"].eq(BATCH_1_FAST_HIGH_VALUE).all())
        self.assertTrue(result.summary_frame["expected_scope_rows"].eq(8).all())
        self.assertTrue(result.summary_frame["actual_scope_rows"].eq(2).all())
        self.assertTrue(result.summary_frame["partial_review_flag"].eq(1).all())
        self.assertTrue(result.candidate_frame["inspection_scope"].eq(BATCH_1_FAST_HIGH_VALUE).all())
        self.assertTrue(result.candidate_frame["expected_scope_rows"].eq(8).all())
        self.assertTrue(result.candidate_frame["actual_scope_rows"].eq(2).all())
        self.assertTrue(result.candidate_frame["partial_review_flag"].eq(1).all())

    def test_build_ingest_backfills_missing_guardrail_columns_to_zero(self) -> None:
        rows_frame = _manual_inspection_rows_frame().drop(
            columns=["production_order_change_flag", "stage_12_change_flag"]
        )

        result = build_promotions_no_prior_manual_inspection_ingest(
            manual_inspection_rows_frame=rows_frame,
            inspection_scope=FULL_NO_PRIOR_18,
        )

        self.assertTrue(result.validated_rows_frame["production_order_change_flag"].eq(0).all())
        self.assertTrue(result.validated_rows_frame["stage_12_change_flag"].eq(0).all())
        self.assertTrue(result.candidate_frame["production_order_change_flag"].eq(0).all())
        self.assertTrue(result.candidate_frame["stage_12_change_flag"].eq(0).all())


if __name__ == "__main__":
    unittest.main()