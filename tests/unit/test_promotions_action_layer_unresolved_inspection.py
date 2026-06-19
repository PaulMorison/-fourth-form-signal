from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_action_layer_unresolved_inspection import (  # noqa: E402
    COLLECT_MORE_EVIDENCE_BEFORE_RULE_CHANGE,
    GATHER_MORE_EVIDENCE_SHADOW_ONLY,
    HIGH,
    MIXED_REVIEW_DEBT,
    NEEDS_MORE_EVIDENCE,
    OVER_SUPPRESSION_CANDIDATE,
    REPORTING_OR_TEXT_ISSUE,
    SHADOW_ONLY_TARGETED_ACTION_LAYER_REVIEW,
    VALID_CONSERVATIVE_BLOCK,
    build_promotions_action_layer_unresolved_inspection,
)


def _rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "1001",
                "sku_description": "High Value Serum",
                "department": "SKINCARE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "reason_short": "Do not buy.",
                "store_action_label": "NO_DEMAND",
                "demand_label": "NO_DEMAND",
                "availability_risk_label": "FLOOR_PROTECTION_NEEDED",
                "actual_units_sold": 9.0,
                "expected_promo_demand": 1.0,
                "estimated_actual_gross_profit": 120.0,
                "capital_left_unsold": 0.0,
                "store_adjusted_units": 0.0,
                "recommended_order_units": 0.0,
                "action_too_conservative_flag": 1,
                "review_should_have_triggered_flag": 1,
                "action_too_aggressive_flag": 0,
                "action_layer_recalibration_label": "REVIEW_SHOULD_HAVE_TRIGGERED",
            },
            {
                "sku_number": "1002",
                "sku_description": "Low Margin Pad",
                "department": "FEMININE CARE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "reason_short": "Do not auto-order.",
                "store_action_label": "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
                "demand_label": "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
                "availability_risk_label": "FLOOR_PROTECTION_NEEDED",
                "actual_units_sold": 6.0,
                "expected_promo_demand": 1.0,
                "estimated_actual_gross_profit": 4.0,
                "capital_left_unsold": 25.0,
                "store_adjusted_units": 0.0,
                "recommended_order_units": 0.0,
                "action_too_conservative_flag": 0,
                "review_should_have_triggered_flag": 1,
                "action_too_aggressive_flag": 0,
                "action_layer_recalibration_label": "REVIEW_SHOULD_HAVE_TRIGGERED",
            },
            {
                "sku_number": "1003",
                "sku_description": "Conflicting Buy Row",
                "department": "VITAMINS",
                "operator_decision": "BUY",
                "operator_action": "ORDER_1_UNITS",
                "reason_short": "Forecast requires manager review.",
                "store_action_label": "PROTECT_AVAILABILITY",
                "demand_label": "PROTECT_AVAILABILITY",
                "availability_risk_label": "BELOW_2_UNIT_FLOOR_RISK",
                "actual_units_sold": 0.0,
                "expected_promo_demand": 14.0,
                "estimated_actual_gross_profit": 0.0,
                "capital_left_unsold": 0.0,
                "store_adjusted_units": 1.0,
                "recommended_order_units": 1.0,
                "action_too_conservative_flag": 0,
                "review_should_have_triggered_flag": 0,
                "action_too_aggressive_flag": 1,
                "action_layer_recalibration_label": "ACTION_TOO_AGGRESSIVE",
            },
            {
                "sku_number": "1004",
                "sku_description": "Borderline Lotion",
                "department": "SKINCARE",
                "operator_decision": "REVIEW",
                "operator_action": "MANUAL_REVIEW",
                "reason_short": "Forecast requires manager review.",
                "store_action_label": "LOW_SOH_NO_AUTO_BUY",
                "demand_label": "LOW_SOH_NO_AUTO_BUY",
                "availability_risk_label": "BELOW_2_UNIT_FLOOR_RISK",
                "actual_units_sold": 4.0,
                "expected_promo_demand": 3.0,
                "estimated_actual_gross_profit": 8.0,
                "capital_left_unsold": 0.0,
                "store_adjusted_units": 0.0,
                "recommended_order_units": 0.0,
                "action_too_conservative_flag": 1,
                "review_should_have_triggered_flag": 0,
                "action_too_aggressive_flag": 0,
                "action_layer_recalibration_label": "ACTION_TOO_CONSERVATIVE",
            },
        ]
    )


def _summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"summary_kind": "RULE_FLAG", "label_name": "ACTION_TOO_CONSERVATIVE", "row_count": 2},
            {"summary_kind": "RULE_FLAG", "label_name": "REVIEW_SHOULD_HAVE_TRIGGERED", "row_count": 2},
            {"summary_kind": "RULE_FLAG", "label_name": "ACTION_TOO_AGGRESSIVE", "row_count": 1},
        ]
    )


class PromotionsActionLayerUnresolvedInspectionTests(unittest.TestCase):
    def test_build_action_layer_unresolved_inspection_outputs(self) -> None:
        result = build_promotions_action_layer_unresolved_inspection(
            action_layer_recalibration_rows_frame=_rows_frame(),
            action_layer_recalibration_summary_frame=_summary_frame(),
        )

        rows = result.rows_frame
        summary = result.summary_frame.set_index("metric_name")
        by_bucket = result.by_bucket_frame.set_index("action_layer_inspection_bucket")

        self.assertEqual(len(rows.index), 5)
        self.assertEqual(int(summary.loc["ROWS_INSPECTED", "metric_value"]), 5)
        self.assertEqual(int(summary.loc["UNIQUE_SOURCE_ROWS", "metric_value"]), 4)
        self.assertEqual(int(summary.loc["EXPECTED_UNRESOLVED_RULE_FLAG_ROWS", "metric_value"]), 5)
        self.assertEqual(int(summary.loc["OVER_SUPPRESSION_CANDIDATE_ROWS", "metric_value"]), 2)
        self.assertEqual(int(summary.loc["VALID_CONSERVATIVE_BLOCK_ROWS", "metric_value"]), 1)
        self.assertEqual(int(summary.loc["REPORTING_OR_TEXT_ISSUE_ROWS", "metric_value"]), 1)
        self.assertEqual(int(summary.loc["NEEDS_MORE_EVIDENCE_ROWS", "metric_value"]), 1)
        self.assertEqual(int(summary.loc["HIGH_PRIORITY_ROWS", "metric_value"]), 2)
        self.assertEqual(summary.loc["OVERALL_INSPECTION_STATUS", "metric_value"], MIXED_REVIEW_DEBT)
        self.assertEqual(
            summary.loc["RECOMMENDATION", "metric_value"],
            SHADOW_ONLY_TARGETED_ACTION_LAYER_REVIEW,
        )

        overlap_conservative = rows.loc[
            rows["sku_number"].astype(str).eq("1001")
            & rows["source_rule_flag"].astype(str).eq("ACTION_TOO_CONSERVATIVE")
        ].iloc[0]
        overlap_review = rows.loc[
            rows["sku_number"].astype(str).eq("1001")
            & rows["source_rule_flag"].astype(str).eq("REVIEW_SHOULD_HAVE_TRIGGERED")
        ].iloc[0]
        weak_review = rows.loc[
            rows["sku_number"].astype(str).eq("1002")
            & rows["source_rule_flag"].astype(str).eq("REVIEW_SHOULD_HAVE_TRIGGERED")
        ].iloc[0]
        aggressive = rows.loc[
            rows["sku_number"].astype(str).eq("1003")
            & rows["source_rule_flag"].astype(str).eq("ACTION_TOO_AGGRESSIVE")
        ].iloc[0]
        inconclusive = rows.loc[
            rows["sku_number"].astype(str).eq("1004")
            & rows["source_rule_flag"].astype(str).eq("ACTION_TOO_CONSERVATIVE")
        ].iloc[0]

        self.assertEqual(overlap_conservative["action_layer_inspection_bucket"], OVER_SUPPRESSION_CANDIDATE)
        self.assertEqual(overlap_review["action_layer_inspection_bucket"], OVER_SUPPRESSION_CANDIDATE)
        self.assertEqual(overlap_conservative["commercial_priority"], HIGH)
        self.assertEqual(_rows_frame().shape[0], 4)
        self.assertEqual(float(overlap_conservative["forecast_error_units"]), 8.0)
        self.assertEqual(weak_review["action_layer_inspection_bucket"], VALID_CONSERVATIVE_BLOCK)
        self.assertEqual(aggressive["action_layer_inspection_bucket"], REPORTING_OR_TEXT_ISSUE)
        self.assertEqual(inconclusive["action_layer_inspection_bucket"], NEEDS_MORE_EVIDENCE)
        self.assertEqual(inconclusive["recommended_next_action"], COLLECT_MORE_EVIDENCE_BEFORE_RULE_CHANGE)

        self.assertIn("production_order_change_flag", rows.columns)
        self.assertIn("stage_12_change_flag", rows.columns)
        self.assertEqual(int(pd.to_numeric(rows["production_order_change_flag"], errors="coerce").fillna(0).sum()), 0)
        self.assertEqual(int(pd.to_numeric(rows["stage_12_change_flag"], errors="coerce").fillna(0).sum()), 0)
        self.assertEqual(int(by_bucket.loc[OVER_SUPPRESSION_CANDIDATE, "row_count"]), 2)
        self.assertEqual(int(by_bucket.loc[VALID_CONSERVATIVE_BLOCK, "unique_source_rows"]), 1)

        memo_text = result.memo_markdown
        self.assertIn("This is not an order file.", memo_text)
        self.assertIn("No training was started.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("shadow-only", memo_text)

    def test_build_action_layer_unresolved_inspection_handles_empty_rows(self) -> None:
        empty_frame = pd.DataFrame(columns=_rows_frame().columns)
        empty_summary = pd.DataFrame(
            [
                {"summary_kind": "RULE_FLAG", "label_name": "ACTION_TOO_CONSERVATIVE", "row_count": 0},
                {"summary_kind": "RULE_FLAG", "label_name": "REVIEW_SHOULD_HAVE_TRIGGERED", "row_count": 0},
                {"summary_kind": "RULE_FLAG", "label_name": "ACTION_TOO_AGGRESSIVE", "row_count": 0},
            ]
        )

        result = build_promotions_action_layer_unresolved_inspection(
            action_layer_recalibration_rows_frame=empty_frame,
            action_layer_recalibration_summary_frame=empty_summary,
        )

        summary = result.summary_frame.set_index("metric_name")

        self.assertTrue(result.rows_frame.empty)
        self.assertTrue(result.by_bucket_frame.empty)
        self.assertEqual(int(summary.loc["ROWS_INSPECTED", "metric_value"]), 0)
        self.assertEqual(summary.loc["OVERALL_INSPECTION_STATUS", "metric_value"], MIXED_REVIEW_DEBT)
        self.assertEqual(summary.loc["RECOMMENDATION", "metric_value"], GATHER_MORE_EVIDENCE_SHADOW_ONLY)
        self.assertIn("No high-priority rows were present", result.memo_markdown)


if __name__ == "__main__":
    unittest.main()