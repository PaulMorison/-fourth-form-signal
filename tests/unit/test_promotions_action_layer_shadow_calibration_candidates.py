from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_action_layer_shadow_calibration_candidates import (  # noqa: E402
    CATEGORY_OR_BRAND_PATTERN_REVIEW,
    DO_NOT_PROMOTE_TO_AUTO_ORDER,
    FINAL_RECOMMENDATION,
    FORECAST_BLINDSPOT_REVIEW_TRIGGER,
    HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER,
    HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW,
    SHADOW_ONLY_NOT_PRODUCTION,
    TEST_IN_SHADOW_ACROSS_MORE_PROMOTIONS,
    ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW,
    build_promotions_action_layer_shadow_calibration_candidates,
)


def _rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "1001",
                "sku_description": "Hydrating Serum",
                "department": "SKINCARE",
                "action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE",
                "source_rule_flag": "ACTION_TOO_CONSERVATIVE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "recommended_order_units": 0.0,
                "actual_units_sold": 9.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 8.0,
                "actual_gross_profit": 90.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "commercial_priority": "HIGH",
                "inspection_reason": "Commercially strong but suppressed.",
                "recommended_next_action": "TEST_SHADOW_ONLY_ACTION_LAYER_RELAXATION",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 1,
            },
            {
                "sku_number": "1002",
                "sku_description": "Forecast Serum",
                "department": "SKINCARE",
                "action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE",
                "source_rule_flag": "REVIEW_SHOULD_HAVE_TRIGGERED",
                "operator_decision": "REVIEW",
                "operator_action": "MANUAL_REVIEW",
                "recommended_order_units": 0.0,
                "actual_units_sold": 8.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 7.0,
                "actual_gross_profit": 35.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "commercial_priority": "MEDIUM",
                "inspection_reason": "Review should have triggered.",
                "recommended_next_action": "TEST_SHADOW_ONLY_REVIEW_TRIGGER",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 2,
            },
            {
                "sku_number": "1003",
                "sku_description": "The Cleanser",
                "department": "SKINCARE",
                "action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE",
                "source_rule_flag": "ACTION_TOO_CONSERVATIVE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "recommended_order_units": 0.0,
                "actual_units_sold": 6.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": 4.0,
                "actual_gross_profit": 22.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "commercial_priority": "MEDIUM",
                "inspection_reason": "Repeated skincare cluster.",
                "recommended_next_action": "TEST_SHADOW_ONLY_ACTION_LAYER_RELAXATION",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 3,
            },
            {
                "sku_number": "1004",
                "sku_description": "The Toner",
                "department": "SKINCARE",
                "action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE",
                "source_rule_flag": "ACTION_TOO_CONSERVATIVE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "recommended_order_units": 0.0,
                "actual_units_sold": 4.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": 2.0,
                "actual_gross_profit": 8.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "commercial_priority": "LOW",
                "inspection_reason": "Pattern row.",
                "recommended_next_action": "COLLECT_MORE_EVIDENCE_BEFORE_RULE_CHANGE",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 4,
            },
            {
                "sku_number": "1005",
                "sku_description": "Residual Lotion",
                "department": "BODYCARE",
                "action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE",
                "source_rule_flag": "ACTION_TOO_CONSERVATIVE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "recommended_order_units": 0.0,
                "actual_units_sold": 1.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 0.0,
                "actual_gross_profit": 2.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "commercial_priority": "LOW",
                "inspection_reason": "Only low-capital evidence.",
                "recommended_next_action": "COLLECT_MORE_EVIDENCE_BEFORE_RULE_CHANGE",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 5,
            },
            {
                "sku_number": "1006",
                "sku_description": "Not Selected",
                "department": "BODYCARE",
                "action_layer_inspection_bucket": "VALID_CONSERVATIVE_BLOCK",
                "source_rule_flag": "ACTION_TOO_CONSERVATIVE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "recommended_order_units": 0.0,
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 4.0,
                "actual_gross_profit": 15.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "commercial_priority": "MEDIUM",
                "inspection_reason": "Should be filtered out.",
                "recommended_next_action": "KEEP_CONSERVATIVE_BLOCK_AND_GATHER_MORE_CASES",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 6,
            },
        ]
    )


def _summary_frame(selected_rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric_name": "ROWS_INSPECTED", "metric_value": 6},
            {"metric_name": "OVER_SUPPRESSION_CANDIDATE_ROWS", "metric_value": selected_rows},
        ]
    )


def _by_bucket_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE", "row_count": 5},
            {"action_layer_inspection_bucket": "VALID_CONSERVATIVE_BLOCK", "row_count": 1},
        ]
    )


class PromotionsActionLayerShadowCalibrationCandidatesTests(unittest.TestCase):
    def test_build_shadow_calibration_candidates_outputs(self) -> None:
        frame = _rows_frame().drop(columns=["order_units"], errors="ignore")

        result = build_promotions_action_layer_shadow_calibration_candidates(
            action_layer_unresolved_inspection_rows_frame=frame,
            action_layer_unresolved_inspection_summary_frame=_summary_frame(),
            action_layer_unresolved_inspection_by_bucket_frame=_by_bucket_frame(),
        )

        rows = result.rows_frame.set_index("sku_number")
        rules = result.rules_frame.set_index("shadow_calibration_rule_candidate")
        summary = result.summary_frame.set_index("metric_name")

        self.assertEqual(len(result.rows_frame.index), 5)
        self.assertEqual(int(summary.loc["INPUT_ROWS", "metric_value"]), 6)
        self.assertEqual(int(summary.loc["OVER_SUPPRESSION_CANDIDATE_ROWS_SELECTED", "metric_value"]), 5)
        self.assertEqual(int(summary.loc["UNIQUE_SKUS", "metric_value"]), 5)
        self.assertEqual(int(summary.loc["HIGH_PRIORITY_CANDIDATE_ROWS", "metric_value"]), 1)
        self.assertEqual(int(summary.loc["CANDIDATE_RULE_FAMILIES_COUNT", "metric_value"]), 5)
        self.assertEqual(summary.loc["FINAL_RECOMMENDATION", "metric_value"], FINAL_RECOMMENDATION)

        self.assertEqual(rows.loc["1001", "shadow_rule_family"], HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW)
        self.assertEqual(rows.loc["1002", "shadow_rule_family"], FORECAST_BLINDSPOT_REVIEW_TRIGGER)
        self.assertEqual(rows.loc["1003", "shadow_rule_family"], HIGH_GP_POSITIVE_DEMAND_REVIEW_TRIGGER)
        self.assertEqual(rows.loc["1004", "shadow_rule_family"], CATEGORY_OR_BRAND_PATTERN_REVIEW)
        self.assertEqual(rows.loc["1005", "shadow_rule_family"], ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW)
        self.assertTrue((result.rows_frame["shadow_rule_test_status"] == SHADOW_ONLY_NOT_PRODUCTION).all())
        self.assertEqual(rows.loc["1001", "recommended_shadow_test_action"], TEST_IN_SHADOW_ACROSS_MORE_PROMOTIONS)
        self.assertEqual(rows.loc["1005", "recommended_shadow_test_action"], DO_NOT_PROMOTE_TO_AUTO_ORDER)
        self.assertIn("order_units", result.rows_frame.columns)
        self.assertEqual(float(rows.loc["1001", "order_units"]), 0.0)
        self.assertEqual(int(pd.to_numeric(result.rows_frame["production_order_change_flag"], errors="coerce").fillna(0).sum()), 0)
        self.assertEqual(int(pd.to_numeric(result.rows_frame["stage_12_change_flag"], errors="coerce").fillna(0).sum()), 0)

        self.assertIn("HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW__ACTION_TOO_CONSERVATIVE", rules.index)
        self.assertEqual(int(rules.loc["HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW__ACTION_TOO_CONSERVATIVE", "row_count"]), 1)
        self.assertIn("FORECAST_BLINDSPOT_REVIEW_TRIGGER__REVIEW_SHOULD_HAVE_TRIGGERED", rules.index)

        memo_text = result.memo_markdown
        self.assertIn("This is not an order file.", memo_text)
        self.assertIn("No training was started.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("shadow-only", memo_text)

    def test_build_shadow_calibration_candidates_handles_empty_rows(self) -> None:
        empty_frame = pd.DataFrame(columns=_rows_frame().columns)
        result = build_promotions_action_layer_shadow_calibration_candidates(
            action_layer_unresolved_inspection_rows_frame=empty_frame,
            action_layer_unresolved_inspection_summary_frame=_summary_frame(selected_rows=0),
            action_layer_unresolved_inspection_by_bucket_frame=_by_bucket_frame(),
        )

        summary = result.summary_frame.set_index("metric_name")

        self.assertTrue(result.rows_frame.empty)
        self.assertTrue(result.rules_frame.empty)
        self.assertEqual(int(summary.loc["OVER_SUPPRESSION_CANDIDATE_ROWS_SELECTED", "metric_value"]), 0)
        self.assertEqual(summary.loc["FINAL_RECOMMENDATION", "metric_value"], FINAL_RECOMMENDATION)
        self.assertIn("No shadow calibration candidates were available", result.memo_markdown)


if __name__ == "__main__":
    unittest.main()