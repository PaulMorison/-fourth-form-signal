from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_review_overlay_packet import (  # noqa: E402
    build_promotions_review_overlay_packet,
)


def _scoreboard_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "metric_group": "REVIEW_SCOPE",
                "metric_name": "TOTAL_ROWS_REVIEWED",
                "metric_value": 3597,
            },
            {
                "metric_group": "FORECAST_HEAD",
                "metric_name": "FORECAST_CORRELATION",
                "metric_value": 0.343344,
            },
            {
                "metric_group": "FORECAST_HEAD",
                "metric_name": "FORECAST_BIAS_UNITS",
                "metric_value": 1235,
            },
            {
                "metric_group": "REPORT_CLEANUP",
                "metric_name": "CLEANUP_ISSUES_REDUCED",
                "metric_value": 693,
            },
            {
                "metric_group": "CAPITAL_DRAG_OVERLAY",
                "metric_name": "OVERLAY_ROWS",
                "metric_value": 2,
            },
            {
                "metric_group": "LOW_SOH_OVERLAY",
                "metric_name": "OVERLAY_ROWS",
                "metric_value": 3,
            },
        ]
    )


def _decision_table_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"decision_category": "PRODUCTION_ORDERING_UNCHANGED", "decision_status": "LOCKED"},
            {"decision_category": "STAGE_12_UNCHANGED", "decision_status": "LOCKED"},
            {"decision_category": "AUTO_ORDERING_NOT_READY", "decision_status": "BLOCKED"},
        ]
    )


def _issue_backlog_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"issue_backlog_category": "NO_PRIOR_DEMAND_SURPRISE", "issue_count": 2},
            {"issue_backlog_category": "ZERO_ORDER_TEXT_RESIDUAL", "issue_count": 1},
        ]
    )


def _next_actions_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "next_action_recommendation": "BUILD_REVIEW_OVERLAY_PACKET",
                "action_status": "READY",
                "row_count": 5,
            },
            {
                "next_action_recommendation": "INSPECT_NO_PRIOR_DEMAND_SURPRISE_SKUS",
                "action_status": "RECOMMENDED",
                "row_count": 2,
            },
            {
                "next_action_recommendation": "CALIBRATE_ACTION_LAYER_SHADOW_ONLY",
                "action_status": "RECOMMENDED",
                "row_count": 3,
            },
        ]
    )


def _cleanup_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue_type": "BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS",
                "issue_count": 1,
                "sample_skus": "5001",
            }
        ]
    )


def _cleanup_issues_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "5001",
                "issue_type": "BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS",
            }
        ]
    )


def _capital_drag_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "2001",
                "sku_description": "Capital Drag Review A",
                "department": "HAIRCARE",
                "operator_decision": "REDUCE_HOLDING",
                "operator_action": "REVIEW",
                "order_units": 0,
                "reason_short": "Review capital-drag headline.",
                "risk_flag": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
                "review_flag": 1,
                "actual_units_sold": 9,
                "expected_promo_demand": 2,
                "forecast_error_units": 7,
                "actual_gross_profit": 90.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "override_candidate_flag": 1,
            },
            {
                "sku_number": "2002",
                "sku_description": "Capital Drag Review B",
                "department": "HAIRCARE",
                "operator_decision": "REDUCE_HOLDING",
                "operator_action": "REVIEW",
                "order_units": 0,
                "reason_short": "Review capital-drag headline.",
                "risk_flag": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
                "review_flag": 1,
                "actual_units_sold": 7,
                "expected_promo_demand": 1,
                "forecast_error_units": 6,
                "actual_gross_profit": 80.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "override_candidate_flag": 1,
            },
        ]
    )


def _low_soh_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "1001",
                "sku_description": "True Missed Demand",
                "department": "SKINCARE",
                "operator_decision": "LOW_SOH_NO_AUTO_BUY",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "BELOW_2_UNIT_FLOOR_RISK",
                "review_flag": 0,
                "actual_units_sold": 6,
                "expected_promo_demand": 1,
                "forecast_error_units": 5,
                "actual_gross_profit": 70.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 1,
                "on_order_units": 0,
                "projected_on_hand_at_promo_start": 1,
                "target_stock_day_one_units": 4,
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "diagnostic_classification": "TRUE_LOW_SOH_MISSED_DEMAND",
            },
            {
                "sku_number": "1002",
                "sku_description": "Online Floor Review",
                "department": "SKINCARE",
                "operator_decision": "LOW_SOH_NO_AUTO_BUY",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "FLOOR_PROTECTION_NEEDED",
                "review_flag": 0,
                "actual_units_sold": 5,
                "expected_promo_demand": 1,
                "forecast_error_units": 4,
                "actual_gross_profit": 60.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2,
                "on_order_units": 0,
                "projected_on_hand_at_promo_start": 1,
                "target_stock_day_one_units": 5,
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "diagnostic_classification": "ONLINE_FLOOR_PROTECTION_REVIEW",
            },
            {
                "sku_number": "1003",
                "sku_description": "Covered By On Order",
                "department": "SKINCARE",
                "operator_decision": "LOW_SOH_NO_AUTO_BUY",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "FLOOR_PROTECTION_NEEDED",
                "review_flag": 0,
                "actual_units_sold": 4,
                "expected_promo_demand": 1,
                "forecast_error_units": 3,
                "actual_gross_profit": 50.0,
                "capital_left_in_unsold_store_allocation": 10.0,
                "current_soh_units": 2,
                "on_order_units": 2,
                "projected_on_hand_at_promo_start": 4,
                "target_stock_day_one_units": 4,
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "diagnostic_classification": "LOW_SOH_BUT_COVERED_BY_ON_ORDER",
            },
        ]
    )


def _no_prior_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "1002",
                "sku_description": "Online Floor Review",
                "department": "SKINCARE",
                "demand_evidence_label": "NO_DEMAND",
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": -4.0,
                "actual_gross_profit": 60.0,
                "capital_left": 0.0,
            },
            {
                "sku_number": "3001",
                "sku_description": "No Prior Surprise",
                "department": "BABY CARE",
                "demand_evidence_label": "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
                "actual_units_sold": 8.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": -6.0,
                "actual_gross_profit": 95.0,
                "capital_left": 5.0,
            },
        ]
    )


def _action_layer_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "2001",
                "sku_description": "Capital Drag Review A",
                "department": "HAIRCARE",
                "operator_decision": "REVIEW",
                "operator_action": "MANUAL_REVIEW",
                "recommended_order_units": 0.0,
                "reason_short": "Manual review required.",
                "risk_flag": "CAPITAL_DRAG_HIGH",
                "review_flag": "REVIEW",
                "expected_promo_demand": 2.0,
                "actual_units_sold": 9.0,
                "forecast_abs_error_units": 7.0,
                "estimated_actual_gross_profit": 90.0,
                "capital_left_unsold": 0.0,
                "action_too_conservative_flag": 1,
                "review_should_have_triggered_flag": 0,
            },
            {
                "sku_number": "3001",
                "sku_description": "No Prior Surprise",
                "department": "BABY CARE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "recommended_order_units": 0.0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "NO_DEMAND",
                "review_flag": 0,
                "expected_promo_demand": 2.0,
                "actual_units_sold": 8.0,
                "forecast_abs_error_units": 6.0,
                "estimated_actual_gross_profit": 95.0,
                "capital_left_unsold": 5.0,
                "action_too_conservative_flag": 0,
                "review_should_have_triggered_flag": 1,
            },
            {
                "sku_number": "4001",
                "sku_description": "Shadow Calibration Only",
                "department": "FRAGRANCE",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "recommended_order_units": 0.0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "NO_DEMAND",
                "review_flag": 0,
                "expected_promo_demand": 3.0,
                "actual_units_sold": 7.0,
                "forecast_abs_error_units": 4.0,
                "estimated_actual_gross_profit": 75.0,
                "capital_left_unsold": 0.0,
                "action_too_conservative_flag": 1,
                "review_should_have_triggered_flag": 0,
            },
            {
                "sku_number": "5001",
                "sku_description": "Zero Order Text",
                "department": "ORAL HEALTH",
                "operator_decision": "BUY",
                "operator_action": "ORDER",
                "recommended_order_units": 0.0,
                "reason_short": "Order now.",
                "risk_flag": "LOW_RISK",
                "review_flag": 0,
                "expected_promo_demand": 1.0,
                "actual_units_sold": 2.0,
                "forecast_abs_error_units": 1.0,
                "estimated_actual_gross_profit": 15.0,
                "capital_left_unsold": 0.0,
                "action_too_conservative_flag": 0,
                "review_should_have_triggered_flag": 0,
            },
        ]
    )


def _visible_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "1001",
                "sku_description": "True Missed Demand",
                "operator_decision": "LOW_SOH_NO_AUTO_BUY",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "BELOW_2_UNIT_FLOOR_RISK",
                "review_flag": 0,
                "current_soh": 1,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 1,
                "target_SOH_at_promo_start": 4,
            },
            {
                "sku_number": "1002",
                "sku_description": "Online Floor Review",
                "operator_decision": "LOW_SOH_NO_AUTO_BUY",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "FLOOR_PROTECTION_NEEDED",
                "review_flag": 0,
                "current_soh": 2,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 1,
                "target_SOH_at_promo_start": 5,
            },
            {
                "sku_number": "1003",
                "sku_description": "Covered By On Order",
                "operator_decision": "LOW_SOH_NO_AUTO_BUY",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "FLOOR_PROTECTION_NEEDED",
                "review_flag": 0,
                "current_soh": 2,
                "on_order_at_advice_time": 2,
                "projected_SOH_at_promo_start": 4,
                "target_SOH_at_promo_start": 4,
            },
            {
                "sku_number": "2001",
                "sku_description": "Capital Drag Review A",
                "operator_decision": "REDUCE_HOLDING",
                "operator_action": "REVIEW",
                "order_units": 0,
                "reason_short": "Review capital-drag headline.",
                "risk_flag": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
                "review_flag": 1,
                "current_soh": 3,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 3,
                "target_SOH_at_promo_start": 3,
            },
            {
                "sku_number": "2002",
                "sku_description": "Capital Drag Review B",
                "operator_decision": "REDUCE_HOLDING",
                "operator_action": "REVIEW",
                "order_units": 0,
                "reason_short": "Review capital-drag headline.",
                "risk_flag": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
                "review_flag": 1,
                "current_soh": 2,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 2,
                "target_SOH_at_promo_start": 2,
            },
            {
                "sku_number": "3001",
                "sku_description": "No Prior Surprise",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "order_units": 0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "NO_DEMAND",
                "review_flag": 0,
                "current_soh": 1,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 1,
                "target_SOH_at_promo_start": 3,
            },
            {
                "sku_number": "4001",
                "sku_description": "Shadow Calibration Only",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "order_units": 0,
                "reason_short": "Do not auto-order.",
                "risk_flag": "NO_DEMAND",
                "review_flag": 0,
                "current_soh": 1,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 1,
                "target_SOH_at_promo_start": 4,
            },
            {
                "sku_number": "5001",
                "sku_description": "Zero Order Text",
                "operator_decision": "BUY",
                "operator_action": "ORDER",
                "order_units": 0,
                "reason_short": "Order now.",
                "risk_flag": "LOW_RISK",
                "review_flag": 0,
                "current_soh": 2,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 2,
                "target_SOH_at_promo_start": 2,
            },
        ]
    )


def _audit_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "1001",
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "order_reconciliation_reason": "Do not auto-order.",
                "current_soh": 1,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 1,
                "target_SOH_at_promo_start": 4,
                "recommended_action": "DO_NOT_BUY",
                "decision_reason": "Do not auto-order.",
            },
            {
                "sku_number": "1002",
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "order_reconciliation_reason": "Do not auto-order.",
                "current_soh": 2,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 1,
                "target_SOH_at_promo_start": 5,
                "recommended_action": "DO_NOT_BUY",
                "decision_reason": "Do not auto-order.",
            },
            {
                "sku_number": "1003",
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "order_reconciliation_reason": "Do not auto-order.",
                "current_soh": 2,
                "on_order_at_advice_time": 2,
                "projected_SOH_at_promo_start": 4,
                "target_SOH_at_promo_start": 4,
                "recommended_action": "DO_NOT_BUY",
                "decision_reason": "Do not auto-order.",
            },
            {
                "sku_number": "2001",
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "order_reconciliation_reason": "Review capital-drag headline.",
                "current_soh": 3,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 3,
                "target_SOH_at_promo_start": 3,
                "recommended_action": "REVIEW",
                "decision_reason": "Review capital-drag headline.",
            },
            {
                "sku_number": "2002",
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "order_reconciliation_reason": "Review capital-drag headline.",
                "current_soh": 2,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 2,
                "target_SOH_at_promo_start": 2,
                "recommended_action": "REVIEW",
                "decision_reason": "Review capital-drag headline.",
            },
            {
                "sku_number": "3001",
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "order_reconciliation_reason": "Do not auto-order.",
                "current_soh": 1,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 1,
                "target_SOH_at_promo_start": 3,
                "recommended_action": "DO_NOT_BUY",
                "decision_reason": "Do not auto-order.",
            },
            {
                "sku_number": "4001",
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "order_reconciliation_reason": "Do not auto-order.",
                "current_soh": 1,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 1,
                "target_SOH_at_promo_start": 4,
                "recommended_action": "DO_NOT_BUY",
                "decision_reason": "Do not auto-order.",
            },
            {
                "sku_number": "5001",
                "recommended_order_units": 0,
                "final_store_order_units": 0,
                "order_reconciliation_reason": "Order now.",
                "current_soh": 2,
                "on_order_at_advice_time": 0,
                "projected_SOH_at_promo_start": 2,
                "target_SOH_at_promo_start": 2,
                "recommended_action": "ORDER",
                "decision_reason": "Order now.",
            },
        ]
    )


class PromotionsReviewOverlayPacketTests(unittest.TestCase):
    def test_build_review_overlay_packet_dedupes_by_priority(self) -> None:
        result = build_promotions_review_overlay_packet(
            scoreboard_summary_frame=_scoreboard_summary_frame(),
            decision_table_frame=_decision_table_frame(),
            issue_backlog_frame=_issue_backlog_frame(),
            next_actions_frame=_next_actions_frame(),
            cleanup_summary_frame=_cleanup_summary_frame(),
            cleanup_issues_frame=_cleanup_issues_frame(),
            capital_drag_rows_frame=_capital_drag_rows_frame(),
            low_soh_rows_frame=_low_soh_rows_frame(),
            no_prior_rows_frame=_no_prior_rows_frame(),
            action_layer_rows_frame=_action_layer_rows_frame(),
            visible_frame=_visible_frame(),
            audit_frame=_audit_frame(),
            manifest={"source_certification_status": "CERTIFIED_EXACT"},
        )

        rows = result.rows_frame.set_index("sku_number")
        by_reason = result.by_reason_frame.set_index("overlay_category")
        by_department = result.by_department_frame.set_index("department")
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])

        self.assertEqual(len(rows.index), 8)
        self.assertEqual(
            str(rows.loc["1001", "overlay_category"]),
            "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
        )
        self.assertEqual(
            str(rows.loc["1002", "overlay_category"]),
            "ONLINE_FLOOR_PROTECTION_REVIEW",
        )
        self.assertEqual(
            str(rows.loc["3001", "overlay_category"]),
            "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
        )
        self.assertEqual(
            str(rows.loc["2001", "overlay_category"]),
            "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
        )
        self.assertEqual(
            str(rows.loc["4001", "overlay_category"]),
            "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
        )
        self.assertEqual(
            str(rows.loc["5001", "overlay_category"]),
            "ZERO_ORDER_TEXT_CLEANUP_REVIEW",
        )

        self.assertEqual(
            str(rows.loc["1001", "proposed_review_action"]),
            "INSPECT_TRUE_MISSED_DEMAND",
        )
        self.assertEqual(
            str(rows.loc["2001", "proposed_review_action"]),
            "INSPECT_STRONG_CONVERTER_CAPITAL_DRAG_HEADLINE",
        )
        self.assertEqual(
            str(rows.loc["4001", "proposed_review_action"]),
            "KEEP_SHADOW_ONLY_FOR_ACTION_LAYER",
        )
        self.assertEqual(int(rows["production_order_change_flag"].sum()), 0)
        self.assertEqual(int(rows["stage_12_change_flag"].sum()), 0)

        self.assertEqual(int(by_reason.loc["ONLINE_FLOOR_PROTECTION_REVIEW", "row_count"]), 2)
        self.assertEqual(int(by_reason.loc["STRONG_CONVERSION_CAPITAL_DRAG_REVIEW", "row_count"]), 2)
        self.assertEqual(int(by_reason.loc["NO_PRIOR_DEMAND_SURPRISE_REVIEW", "row_count"]), 1)
        self.assertEqual(int(by_reason.loc["ZERO_ORDER_TEXT_CLEANUP_REVIEW", "row_count"]), 1)

        self.assertEqual(int(by_department.loc["SKINCARE", "row_count"]), 3)
        self.assertEqual(
            str(by_department.loc["SKINCARE", "top_overlay_category"]),
            "ONLINE_FLOOR_PROTECTION_REVIEW",
        )

        self.assertEqual(
            int(summary.loc[("PACKET", "TOTAL_REVIEW_ROWS"), "metric_value"]),
            8,
        )
        self.assertEqual(
            int(summary.loc[("PACKET", "PRODUCTION_ORDER_CHANGES"), "metric_value"]),
            0,
        )
        self.assertEqual(
            int(summary.loc[("PACKET", "STAGE12_CHANGES"), "metric_value"]),
            0,
        )

        memo_text = result.memo_markdown
        self.assertIn("This file is a governed review packet, not an order file.", memo_text)
        self.assertIn("Production order changes: 0.", memo_text)
        self.assertIn("Stage 12 changes: 0.", memo_text)
        self.assertIn("Why auto-ordering remains blocked", memo_text)
        self.assertIn("Start with STRONG_CONVERSION_CAPITAL_DRAG_REVIEW", memo_text)


if __name__ == "__main__":
    unittest.main()