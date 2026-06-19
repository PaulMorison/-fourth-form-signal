from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_action_layer_shadow_vs_baseline_simulation import (  # noqa: E402
    BASELINE_CONSERVATISM_SUPPORTED,
    BASELINE_REVIEW_ONLY,
    BASELINE_SUPPRESSED_OR_UNDER_REVIEW,
    DO_NOT_PROMOTE_TO_AUTO_ORDER,
    DO_NOT_PROMOTE_TO_PRODUCTION,
    FAVOURS_SHADOW_REVIEW_TRIGGER,
    FINAL_RECOMMENDATION,
    INCONCLUSIVE,
    KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS,
    REMOVE_WEAK_SHADOW_RULE,
    SHADOW_NO_CHANGE,
    SHADOW_ONLY_NOT_PRODUCTION,
    SHADOW_REJECTED,
    SHADOW_REVIEW_TRIGGERED,
    build_promotions_action_layer_shadow_vs_baseline_simulation,
)


def _candidate_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "1001",
                "sku_description": "Hydrating Serum",
                "department": "SKINCARE",
                "source_rule_flag": "ACTION_TOO_CONSERVATIVE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "actual_units_sold": 8.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 7.0,
                "actual_gross_profit": 80.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "commercial_priority": "HIGH",
                "action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE",
                "shadow_calibration_rule_candidate": "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW__ACTION_TOO_CONSERVATIVE",
                "shadow_rule_family": "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW",
                "shadow_rule_strength": "HIGH",
                "shadow_rule_risk_level": "LOW",
                "shadow_rule_test_status": SHADOW_ONLY_NOT_PRODUCTION,
                "recommended_shadow_test_action": "TEST_IN_SHADOW_ACROSS_MORE_PROMOTIONS",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 1,
            },
            {
                "sku_number": "1002",
                "sku_description": "Forecast Serum",
                "department": "SKINCARE",
                "source_rule_flag": "REVIEW_SHOULD_HAVE_TRIGGERED",
                "operator_decision": "REVIEW",
                "operator_action": "MANUAL_REVIEW",
                "actual_units_sold": 6.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 5.0,
                "actual_gross_profit": 35.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "commercial_priority": "MEDIUM",
                "action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE",
                "shadow_calibration_rule_candidate": "FORECAST_BLINDSPOT_REVIEW_TRIGGER__REVIEW_SHOULD_HAVE_TRIGGERED",
                "shadow_rule_family": "FORECAST_BLINDSPOT_REVIEW_TRIGGER",
                "shadow_rule_strength": "MEDIUM",
                "shadow_rule_risk_level": "LOW",
                "shadow_rule_test_status": SHADOW_ONLY_NOT_PRODUCTION,
                "recommended_shadow_test_action": "KEEP_AS_REVIEW_TRIGGER_ONLY",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 2,
            },
            {
                "sku_number": "1003",
                "sku_description": "Weak Lotion",
                "department": "BODYCARE",
                "source_rule_flag": "ACTION_TOO_CONSERVATIVE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "actual_units_sold": 1.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 0.0,
                "actual_gross_profit": 2.0,
                "capital_left_in_unsold_store_allocation": 4.0,
                "commercial_priority": "LOW",
                "action_layer_inspection_bucket": "OVER_SUPPRESSION_CANDIDATE",
                "shadow_calibration_rule_candidate": "ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW__ACTION_TOO_CONSERVATIVE",
                "shadow_rule_family": "ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW",
                "shadow_rule_strength": "LOW",
                "shadow_rule_risk_level": "HIGH",
                "shadow_rule_test_status": SHADOW_ONLY_NOT_PRODUCTION,
                "recommended_shadow_test_action": DO_NOT_PROMOTE_TO_AUTO_ORDER,
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
                "source_row_number": 3,
            },
        ]
    )


def _candidate_summary_frame(selected_rows: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric_name": "OVER_SUPPRESSION_CANDIDATE_ROWS_SELECTED", "metric_value": selected_rows},
        ]
    )


def _candidate_rules_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"shadow_rule_family": "HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW", "row_count": 1},
            {"shadow_rule_family": "FORECAST_BLINDSPOT_REVIEW_TRIGGER", "row_count": 1},
            {"shadow_rule_family": "ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW", "row_count": 1},
        ]
    )


def _unresolved_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"sku_number": "1001", "source_row_number": 1},
            {"sku_number": "1002", "source_row_number": 2},
            {"sku_number": "1003", "source_row_number": 3},
        ]
    )


class PromotionsActionLayerShadowVsBaselineSimulationTests(unittest.TestCase):
    def test_build_shadow_vs_baseline_simulation_outputs(self) -> None:
        frame = _candidate_rows_frame().drop(columns=["order_units"], errors="ignore")

        result = build_promotions_action_layer_shadow_vs_baseline_simulation(
            action_layer_shadow_calibration_candidate_rows_frame=frame,
            action_layer_shadow_calibration_candidate_summary_frame=_candidate_summary_frame(),
            action_layer_shadow_calibration_candidate_rules_frame=_candidate_rules_frame(),
            action_layer_unresolved_inspection_rows_frame=_unresolved_rows_frame(),
        )

        rows = result.rows_frame.set_index("sku_number")
        by_family = result.by_rule_family_frame.set_index("shadow_rule_family")
        summary = result.summary_frame.set_index("metric_name")

        self.assertEqual(len(result.rows_frame.index), 3)
        self.assertEqual(int(summary.loc["INPUT_CANDIDATE_ROWS", "metric_value"]), 3)
        self.assertEqual(int(summary.loc["UNIQUE_SKUS", "metric_value"]), 3)
        self.assertEqual(int(summary.loc["INCREMENTAL_SHADOW_REVIEW_TRIGGERS", "metric_value"]), 1)
        self.assertEqual(int(summary.loc["HIGH_PRIORITY_INCREMENTAL_TRIGGERS", "metric_value"]), 1)
        self.assertEqual(float(summary.loc["NET_REVIEW_VALUE_PROXY", "metric_value"]), 113.0)
        self.assertEqual(summary.loc["FINAL_RECOMMENDATION", "metric_value"], FINAL_RECOMMENDATION)

        self.assertEqual(rows.loc["1001", "baseline_action_layer_outcome"], BASELINE_SUPPRESSED_OR_UNDER_REVIEW)
        self.assertEqual(rows.loc["1001", "shadow_review_trigger_outcome"], SHADOW_REVIEW_TRIGGERED)
        self.assertEqual(int(rows.loc["1001", "shadow_incremental_review_trigger_flag"]), 1)
        self.assertEqual(rows.loc["1001", "shadow_simulation_status"], FAVOURS_SHADOW_REVIEW_TRIGGER)
        self.assertEqual(rows.loc["1001", "recommended_next_action"], KEEP_SHADOW_REVIEW_TRIGGER_FOR_MORE_PROMOTIONS)

        self.assertEqual(rows.loc["1002", "baseline_action_layer_outcome"], BASELINE_REVIEW_ONLY)
        self.assertEqual(rows.loc["1002", "shadow_review_trigger_outcome"], SHADOW_NO_CHANGE)
        self.assertEqual(rows.loc["1002", "shadow_simulation_status"], INCONCLUSIVE)

        self.assertEqual(rows.loc["1003", "shadow_review_trigger_outcome"], SHADOW_REJECTED)
        self.assertEqual(rows.loc["1003", "shadow_simulation_status"], BASELINE_CONSERVATISM_SUPPORTED)
        self.assertEqual(rows.loc["1003", "recommended_next_action"], REMOVE_WEAK_SHADOW_RULE)

        self.assertIn("order_units", result.rows_frame.columns)
        self.assertEqual(float(rows.loc["1001", "order_units"]), 0.0)
        self.assertEqual(int(pd.to_numeric(result.rows_frame["production_order_change_flag"], errors="coerce").fillna(0).sum()), 0)
        self.assertEqual(int(pd.to_numeric(result.rows_frame["stage_12_change_flag"], errors="coerce").fillna(0).sum()), 0)

        self.assertEqual(int(by_family.loc["HIGH_PRIORITY_OVER_SUPPRESSION_REVIEW", "incremental_shadow_review_triggers"]), 1)
        self.assertEqual(int(by_family.loc["ZERO_OR_LOW_CAPITAL_LEFT_SUPPRESSION_REVIEW", "baseline_conservatism_supported_rows"]), 1)

        memo_text = result.memo_markdown
        self.assertIn("This is not an order file.", memo_text)
        self.assertIn("No training was started.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("review triggers", memo_text)

    def test_build_shadow_vs_baseline_simulation_handles_empty_rows(self) -> None:
        empty_frame = pd.DataFrame(columns=_candidate_rows_frame().columns)

        result = build_promotions_action_layer_shadow_vs_baseline_simulation(
            action_layer_shadow_calibration_candidate_rows_frame=empty_frame,
            action_layer_shadow_calibration_candidate_summary_frame=_candidate_summary_frame(selected_rows=0),
            action_layer_shadow_calibration_candidate_rules_frame=_candidate_rules_frame(),
            action_layer_unresolved_inspection_rows_frame=pd.DataFrame(columns=["sku_number", "source_row_number"]),
        )

        summary = result.summary_frame.set_index("metric_name")

        self.assertTrue(result.rows_frame.empty)
        self.assertTrue(result.by_rule_family_frame.empty)
        self.assertEqual(int(summary.loc["INPUT_CANDIDATE_ROWS", "metric_value"]), 0)
        self.assertEqual(float(summary.loc["NET_REVIEW_VALUE_PROXY", "metric_value"]), 0.0)
        self.assertEqual(summary.loc["FINAL_RECOMMENDATION", "metric_value"], FINAL_RECOMMENDATION)
        self.assertIn("No rule-family simulation rows were available", result.memo_markdown)


if __name__ == "__main__":
    unittest.main()