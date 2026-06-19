from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_batch1_shadow_candidate_inspection import (  # noqa: E402
    KEEP_AS_SHADOW_REVIEW_RULE_CANDIDATE,
    KEEP_SHADOW_CANDIDATE,
    NEEDS_MORE_EVIDENCE,
    REVIEW_MORE_PROMOTIONS_FOR_REPEATABILITY,
    REJECT_CANDIDATE,
    build_promotions_batch1_shadow_candidate_inspection,
)


def _candidate_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "3001",
                "sku_description": "Hydrating Serum",
                "department": "SKINCARE",
                "manual_cause_label": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
                "manual_confidence_score": 75.0,
                "manual_notes": "Brand/category demand looks stronger than prior promo evidence.",
                "actual_units_sold": 8.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -7.0,
                "actual_gross_profit": 120.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_rule_candidate": "NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE",
                "candidate_reason": "Strong no-prior brand/category pattern; keep shadow-only until repeated.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "inspection_scope": "BATCH_1_FAST_HIGH_VALUE",
                "expected_scope_rows": 8,
                "actual_scope_rows": 8,
                "partial_review_flag": 1,
            },
            {
                "sku_number": "3002",
                "sku_description": "Peptide Serum",
                "department": "SKINCARE",
                "manual_cause_label": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
                "manual_confidence_score": 80.0,
                "manual_notes": "Another similar brand/category demand pattern.",
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -4.0,
                "actual_gross_profit": 75.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 5.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 5.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_rule_candidate": "NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE",
                "candidate_reason": "Strong no-prior brand/category pattern; keep shadow-only until repeated.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "inspection_scope": "BATCH_1_FAST_HIGH_VALUE",
                "expected_scope_rows": 8,
                "actual_scope_rows": 8,
                "partial_review_flag": 1,
            },
            {
                "sku_number": "3003",
                "sku_description": "Trial SKU",
                "department": "SKINCARE",
                "manual_cause_label": "BRAND_OR_CATEGORY_STRENGTH_NOT_CAPTURED",
                "manual_confidence_score": 55.0,
                "manual_notes": "Weak commercial evidence and no clean blindspot.",
                "actual_units_sold": 1.0,
                "expected_promo_demand": 3.0,
                "forecast_error_units": 2.0,
                "actual_gross_profit": -5.0,
                "capital_left_in_unsold_store_allocation": 20.0,
                "current_soh_units": 10.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 10.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_rule_candidate": "NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE",
                "candidate_reason": "Insufficient commercial quality for a safe shadow-only carry-forward.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "inspection_scope": "BATCH_1_FAST_HIGH_VALUE",
                "expected_scope_rows": 8,
                "actual_scope_rows": 8,
                "partial_review_flag": 1,
            },
        ]
    )


class PromotionsBatch1ShadowCandidateInspectionTests(unittest.TestCase):
    def test_build_shadow_candidate_inspection_outputs(self) -> None:
        result = build_promotions_batch1_shadow_candidate_inspection(
            candidate_rows_frame=_candidate_rows_frame(),
        )

        rows = result.rows_frame.set_index("sku_number")
        summary = result.summary_frame.set_index("metric_name")
        by_rule = result.by_rule_frame.set_index("proposed_review_rule_candidate")

        self.assertEqual(result.rows_frame["sku_number"].tolist(), ["3001", "3002", "3003"])
        self.assertEqual(rows.loc["3001", "shadow_candidate_inspection_status"], KEEP_SHADOW_CANDIDATE)
        self.assertEqual(rows.loc["3002", "shadow_candidate_inspection_status"], KEEP_SHADOW_CANDIDATE)
        self.assertEqual(rows.loc["3003", "shadow_candidate_inspection_status"], REJECT_CANDIDATE)
        self.assertEqual(int(rows.loc["3001", "rule_concentration_flag"]), 1)
        self.assertEqual(int(rows.loc["3001", "brand_category_pattern_flag"]), 1)
        self.assertEqual(int(rows.loc["3001", "low_capital_risk_flag"]), 1)
        self.assertEqual(int(rows.loc["3001", "positive_gross_profit_flag"]), 1)
        self.assertEqual(int(rows.loc["3001", "forecast_blindspot_flag"]), 1)
        self.assertEqual(int(rows.loc["3001", "shadow_only_keep_flag"]), 1)
        self.assertEqual(rows.loc["3001", "recommended_next_action"], KEEP_AS_SHADOW_REVIEW_RULE_CANDIDATE)
        self.assertIn("dominant proposed rule", rows.loc["3001", "inspection_reason"])
        self.assertEqual(int(rows.loc["3003", "positive_gross_profit_flag"]), 0)
        self.assertEqual(int(rows.loc["3003", "forecast_blindspot_flag"]), 0)
        self.assertEqual(int(rows.loc["3003", "shadow_only_keep_flag"]), 0)

        self.assertEqual(int(summary.loc["ROWS_INSPECTED", "metric_value"]), 3)
        self.assertEqual(int(summary.loc["CANDIDATE_RULE_COUNT", "metric_value"]), 1)
        self.assertEqual(summary.loc["DOMINANT_PROPOSED_RULE", "metric_value"], "NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE")
        self.assertEqual(float(summary.loc["GROSS_PROFIT_REPRESENTED", "metric_value"]), 190.0)
        self.assertEqual(float(summary.loc["CAPITAL_LEFT_REPRESENTED", "metric_value"]), 20.0)
        self.assertEqual(int(summary.loc["KEEP_SHADOW_CANDIDATE_ROWS", "metric_value"]), 2)
        self.assertEqual(int(summary.loc["NEEDS_MORE_EVIDENCE_ROWS", "metric_value"]), 0)
        self.assertEqual(int(summary.loc["REJECT_CANDIDATE_ROWS", "metric_value"]), 1)
        self.assertEqual(summary.loc["OVERALL_INSPECTION_STATUS", "metric_value"], NEEDS_MORE_EVIDENCE)
        self.assertEqual(summary.loc["RECOMMENDATION", "metric_value"], REVIEW_MORE_PROMOTIONS_FOR_REPEATABILITY)
        self.assertEqual(int(summary.loc["PRODUCTION_ORDER_CHANGES", "metric_value"]), 0)
        self.assertEqual(int(summary.loc["STAGE12_CHANGES", "metric_value"]), 0)

        self.assertEqual(int(by_rule.loc["NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE", "row_count"]), 3)
        self.assertEqual(int(by_rule.loc["NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE", "keep_shadow_candidate_rows"]), 2)
        self.assertEqual(int(by_rule.loc["NO_PRIOR_BRAND_CATEGORY_REVIEW_RULE", "reject_candidate_rows"]), 1)

        memo_text = result.memo_markdown
        self.assertIn("This is not an order file.", memo_text)
        self.assertIn("No training was started.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("Full train remains blocked.", memo_text)
        self.assertIn("Shadow-only data inspection remains allowed.", memo_text)
        self.assertIn("Production promotion still requires repeated evidence across more promotions", memo_text)

    def test_build_shadow_candidate_inspection_handles_empty_candidates(self) -> None:
        empty_frame = pd.DataFrame(columns=_candidate_rows_frame().columns)

        result = build_promotions_batch1_shadow_candidate_inspection(
            candidate_rows_frame=empty_frame,
        )

        summary = result.summary_frame.set_index("metric_name")

        self.assertTrue(result.rows_frame.empty)
        self.assertTrue(result.by_rule_frame.empty)
        self.assertEqual(int(summary.loc["ROWS_INSPECTED", "metric_value"]), 0)
        self.assertEqual(summary.loc["OVERALL_INSPECTION_STATUS", "metric_value"], NEEDS_MORE_EVIDENCE)
        self.assertEqual(summary.loc["RECOMMENDATION", "metric_value"], REVIEW_MORE_PROMOTIONS_FOR_REPEATABILITY)
        self.assertIn("No Batch 1 candidate-ready rows were available to inspect", result.memo_markdown)


if __name__ == "__main__":
    unittest.main()