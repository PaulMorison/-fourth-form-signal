from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_action_layer_shadow_vs_baseline_simulation import (  # noqa: E402
    FAVOURS_SHADOW_REVIEW_TRIGGER,
)
from runtime.promotions.run_promotions_shadow_review_trigger_leaderboard import (  # noqa: E402
    FINAL_RECOMMENDATION,
    KEEP_AS_SHADOW_REVIEW_TRIGGER,
    REQUIRE_MORE_EVIDENCE,
    TEST_FIRST_ACROSS_MORE_PROMOTIONS,
    TIER_1_TEST_FIRST,
    TIER_3_REQUIRE_MORE_EVIDENCE,
    build_promotions_shadow_review_trigger_leaderboard,
)


def _simulation_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "1001",
                "sku_description": "Glow Serum",
                "department": "SKINCARE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "actual_units_sold": 8.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 7.0,
                "actual_gross_profit": 80.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "shadow_calibration_rule_candidate": "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW__ACTION_TOO_CONSERVATIVE",
                "shadow_rule_family": "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW",
                "shadow_rule_strength": "HIGH",
                "shadow_rule_risk_level": "LOW",
                "commercial_priority": "HIGH",
                "shadow_notional_commercial_opportunity": 80.0,
                "shadow_notional_capital_risk": 0.0,
                "shadow_net_review_value_proxy": 80.0,
                "simulation_reason": "Strong value.",
                "recommended_next_action": "KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS",
                "shadow_incremental_review_trigger_flag": 1,
                "shadow_simulation_status": FAVOURS_SHADOW_REVIEW_TRIGGER,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "1002",
                "sku_description": "Glow Lotion",
                "department": "SKINCARE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "actual_units_sold": 6.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 5.0,
                "actual_gross_profit": 60.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "shadow_calibration_rule_candidate": "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW__REVIEW_SHOULD_HAVE_TRIGGERED",
                "shadow_rule_family": "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW",
                "shadow_rule_strength": "HIGH",
                "shadow_rule_risk_level": "LOW",
                "commercial_priority": "MEDIUM",
                "shadow_notional_commercial_opportunity": 60.0,
                "shadow_notional_capital_risk": 0.0,
                "shadow_net_review_value_proxy": 60.0,
                "simulation_reason": "Repeatable pattern.",
                "recommended_next_action": "KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS",
                "shadow_incremental_review_trigger_flag": 1,
                "shadow_simulation_status": FAVOURS_SHADOW_REVIEW_TRIGGER,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "1003",
                "sku_description": "Mint Paste",
                "department": "ORAL HEALTH",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "actual_units_sold": 3.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 2.0,
                "actual_gross_profit": 15.0,
                "capital_left_in_unsold_store_allocation": 2.0,
                "shadow_calibration_rule_candidate": "FORECAST_BLINDSPOT_REVIEW_TRIGGER__ACTION_TOO_CONSERVATIVE",
                "shadow_rule_family": "FORECAST_BLINDSPOT_REVIEW_TRIGGER",
                "shadow_rule_strength": "MEDIUM",
                "shadow_rule_risk_level": "MEDIUM",
                "commercial_priority": "LOW",
                "shadow_notional_commercial_opportunity": 15.0,
                "shadow_notional_capital_risk": 2.0,
                "shadow_net_review_value_proxy": 13.0,
                "simulation_reason": "Lower evidence.",
                "recommended_next_action": "REQUIRE_REPEAT_EVIDENCE",
                "shadow_incremental_review_trigger_flag": 1,
                "shadow_simulation_status": FAVOURS_SHADOW_REVIEW_TRIGGER,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "1004",
                "sku_description": "Blocked Row",
                "department": "SKINCARE",
                "operator_decision": "REVIEW",
                "operator_action": "MANUAL_REVIEW",
                "actual_units_sold": 7.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 4.0,
                "actual_gross_profit": 55.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "shadow_calibration_rule_candidate": "CATEGORY_OR_BRAND_PATTERN_REVIEW__REVIEW_SHOULD_HAVE_TRIGGERED",
                "shadow_rule_family": "CATEGORY_OR_BRAND_PATTERN_REVIEW",
                "shadow_rule_strength": "MEDIUM",
                "shadow_rule_risk_level": "LOW",
                "commercial_priority": "MEDIUM",
                "shadow_notional_commercial_opportunity": 55.0,
                "shadow_notional_capital_risk": 0.0,
                "shadow_net_review_value_proxy": 55.0,
                "simulation_reason": "Not incremental.",
                "recommended_next_action": "KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS",
                "shadow_incremental_review_trigger_flag": 0,
                "shadow_simulation_status": "INCONCLUSIVE",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
        ]
    )


def _simulation_by_rule_family_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"shadow_rule_family": "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW", "row_count": 2},
            {"shadow_rule_family": "FORECAST_BLINDSPOT_REVIEW_TRIGGER", "row_count": 1},
        ]
    )


def _simulation_summary_frame(input_rows: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric_name": "INPUT_CANDIDATE_ROWS", "metric_value": input_rows},
        ]
    )


class PromotionsShadowReviewTriggerLeaderboardTests(unittest.TestCase):
    def test_build_shadow_review_trigger_leaderboard_outputs(self) -> None:
        frame = _simulation_rows_frame().drop(
            columns=["operator_action", "capital_left_in_unsold_store_allocation", "shadow_notional_capital_risk"],
            errors="ignore",
        )

        result = build_promotions_shadow_review_trigger_leaderboard(
            action_layer_shadow_vs_baseline_rows_frame=frame,
            action_layer_shadow_vs_baseline_by_rule_family_frame=_simulation_by_rule_family_frame(),
            action_layer_shadow_vs_baseline_summary_frame=_simulation_summary_frame(),
        )

        rows = result.rows_frame.set_index("sku_number")
        by_family = result.by_rule_family_frame.set_index("shadow_rule_family")
        by_department = result.by_department_frame.set_index("department")
        summary = result.summary_frame.set_index("metric_name")

        self.assertEqual(len(result.rows_frame.index), 3)
        self.assertEqual(int(summary.loc["INPUT_SIMULATION_ROWS", "metric_value"]), 4)
        self.assertEqual(int(summary.loc["ELIGIBLE_LEADERBOARD_ROWS", "metric_value"]), 3)
        self.assertEqual(int(summary.loc["UNIQUE_SKUS", "metric_value"]), 3)
        self.assertEqual(int(summary.loc["TIER_1_COUNT", "metric_value"]), 2)
        self.assertEqual(int(summary.loc["HIGH_PRIORITY_TIER_1_COUNT", "metric_value"]), 1)
        self.assertEqual(float(summary.loc["NET_REVIEW_VALUE_PROXY", "metric_value"]), 153.0)
        self.assertEqual(summary.loc["DOMINANT_RULE_FAMILY", "metric_value"], "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW")
        self.assertEqual(summary.loc["DOMINANT_DEPARTMENT", "metric_value"], "SKINCARE")
        self.assertEqual(summary.loc["FINAL_RECOMMENDATION", "metric_value"], FINAL_RECOMMENDATION)

        self.assertEqual(int(rows.loc["1001", "leaderboard_rank"]), 1)
        self.assertEqual(rows.loc["1001", "leaderboard_tier"], TIER_1_TEST_FIRST)
        self.assertEqual(rows.loc["1001", "recommended_leaderboard_action"], TEST_FIRST_ACROSS_MORE_PROMOTIONS)
        self.assertGreater(float(rows.loc["1001", "shadow_review_trigger_score"]), float(rows.loc["1002", "shadow_review_trigger_score"]))

        self.assertEqual(rows.loc["1002", "leaderboard_tier"], TIER_1_TEST_FIRST)
        self.assertEqual(rows.loc["1002", "recommended_leaderboard_action"], TEST_FIRST_ACROSS_MORE_PROMOTIONS)
        self.assertEqual(rows.loc["1003", "leaderboard_tier"], TIER_3_REQUIRE_MORE_EVIDENCE)
        self.assertEqual(rows.loc["1003", "recommended_leaderboard_action"], REQUIRE_MORE_EVIDENCE)

        self.assertIn("operator_action", result.rows_frame.columns)
        self.assertEqual(rows.loc["1001", "operator_action"], "")
        self.assertEqual(float(rows.loc["1001", "capital_left_in_unsold_store_allocation"]), 0.0)

        self.assertEqual(int(by_family.loc["HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW", "tier_1_count"]), 2)
        self.assertEqual(int(by_department.loc["SKINCARE", "tier_1_count"]), 2)
        self.assertEqual(int(pd.to_numeric(result.rows_frame["production_order_change_flag"], errors="coerce").fillna(0).sum()), 0)
        self.assertEqual(int(pd.to_numeric(result.rows_frame["stage_12_change_flag"], errors="coerce").fillna(0).sum()), 0)

        memo_text = result.memo_markdown
        self.assertIn("This is not an order file.", memo_text)
        self.assertIn("No training was started.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("Tier 1 means test first in shadow, not promote to production.", memo_text)

    def test_build_shadow_review_trigger_leaderboard_handles_empty_rows(self) -> None:
        empty_frame = pd.DataFrame(columns=_simulation_rows_frame().columns)

        result = build_promotions_shadow_review_trigger_leaderboard(
            action_layer_shadow_vs_baseline_rows_frame=empty_frame,
            action_layer_shadow_vs_baseline_by_rule_family_frame=_simulation_by_rule_family_frame(),
            action_layer_shadow_vs_baseline_summary_frame=_simulation_summary_frame(input_rows=0),
        )

        summary = result.summary_frame.set_index("metric_name")

        self.assertTrue(result.rows_frame.empty)
        self.assertTrue(result.by_rule_family_frame.empty)
        self.assertTrue(result.by_department_frame.empty)
        self.assertEqual(int(summary.loc["ELIGIBLE_LEADERBOARD_ROWS", "metric_value"]), 0)
        self.assertEqual(float(summary.loc["NET_REVIEW_VALUE_PROXY", "metric_value"]), 0.0)
        self.assertEqual(summary.loc["FINAL_RECOMMENDATION", "metric_value"], REQUIRE_MORE_EVIDENCE)
        self.assertIn("No rule-family leaderboard rows were available", result.memo_markdown)


if __name__ == "__main__":
    unittest.main()