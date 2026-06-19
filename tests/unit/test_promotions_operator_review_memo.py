from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_operator_review_memo import (  # noqa: E402
    build_promotions_operator_review_memo,
)


def _review_overlay_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sku_number": "3002",
                "sku_description": "No Prior Surprise Higher GP",
                "department": "BABY CARE",
                "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "order_units": 0.0,
                "actual_units_sold": 9.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": 7.0,
                "actual_gross_profit": 125.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 1.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "3001",
                "sku_description": "No Prior Surprise",
                "department": "BABY CARE",
                "overlay_category": "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "order_units": 0.0,
                "actual_units_sold": 8.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": 6.0,
                "actual_gross_profit": 95.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 1.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 3.0,
                "proposed_review_action": "INSPECT_NO_PRIOR_DEMAND_SURPRISE",
                "why_review_required": "Material demand landed without strong prior promo evidence.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "1001",
                "sku_description": "True Missed Demand",
                "department": "SKINCARE",
                "overlay_category": "TRUE_LOW_SOH_MISSED_DEMAND_REVIEW",
                "operator_decision": "LOW_SOH_NO_AUTO_BUY",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0.0,
                "actual_units_sold": 6.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 5.0,
                "actual_gross_profit": 70.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 1.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 4.0,
                "proposed_review_action": "INSPECT_TRUE_MISSED_DEMAND",
                "why_review_required": "Material demand landed while the row stayed low-SOH suppressed.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "2001",
                "sku_description": "Online Floor Risk",
                "department": "SKINCARE",
                "overlay_category": "ONLINE_FLOOR_PROTECTION_REVIEW",
                "operator_decision": "LOW_SOH_NO_AUTO_BUY",
                "operator_action": "DO_NOT_BUY",
                "order_units": 0.0,
                "actual_units_sold": 5.0,
                "expected_promo_demand": 1.0,
                "forecast_error_units": 4.0,
                "actual_gross_profit": 70.0,
                "capital_left_in_unsold_store_allocation": 12.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 5.0,
                "proposed_review_action": "INSPECT_ONLINE_FLOOR_RISK",
                "why_review_required": "The row needs a human floor-risk check because low-SOH or floor-protection context stayed review-only.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "4001",
                "sku_description": "Capital Drag Review",
                "department": "HAIRCARE",
                "overlay_category": "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW",
                "operator_decision": "REVIEW",
                "operator_action": "REVIEW",
                "order_units": 0.0,
                "actual_units_sold": 8.0,
                "expected_promo_demand": 2.0,
                "forecast_error_units": 6.0,
                "actual_gross_profit": 90.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 2.0,
                "proposed_review_action": "INSPECT_STRONG_CONVERTER_CAPITAL_DRAG_HEADLINE",
                "why_review_required": "Strong sell-through contradicted the visible capital-drag headline.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "5001",
                "sku_description": "Shadow Calibration",
                "department": "FRAGRANCE",
                "overlay_category": "ACTION_LAYER_SHADOW_CALIBRATION_REVIEW",
                "operator_decision": "DO_NOT_BUY",
                "operator_action": "NO_ORDER",
                "order_units": 0.0,
                "actual_units_sold": 7.0,
                "expected_promo_demand": 3.0,
                "forecast_error_units": 4.0,
                "actual_gross_profit": 55.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 1.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 1.0,
                "target_stock_day_one_units": 4.0,
                "proposed_review_action": "KEEP_SHADOW_ONLY_FOR_ACTION_LAYER",
                "why_review_required": "The action layer was too conservative.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
            {
                "sku_number": "6001",
                "sku_description": "Zero Order Text",
                "department": "ORAL HEALTH",
                "overlay_category": "ZERO_ORDER_TEXT_CLEANUP_REVIEW",
                "operator_decision": "BUY",
                "operator_action": "ORDER",
                "order_units": 0.0,
                "actual_units_sold": 1.0,
                "expected_promo_demand": 0.0,
                "forecast_error_units": 1.0,
                "actual_gross_profit": 12.0,
                "capital_left_in_unsold_store_allocation": 0.0,
                "current_soh_units": 2.0,
                "on_order_units": 0.0,
                "projected_on_hand_at_promo_start": 2.0,
                "target_stock_day_one_units": 2.0,
                "proposed_review_action": "FIX_VISIBLE_REASON_TEXT",
                "why_review_required": "Visible wording still implies buy or order.",
                "production_order_change_flag": 0,
                "stage_12_change_flag": 0,
            },
        ]
    )


def _review_overlay_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric_group": "SCOREBOARD", "metric_name": "FORECAST_CORRELATION", "metric_value": 0.343344},
            {"metric_group": "SCOREBOARD", "metric_name": "FORECAST_BIAS_UNITS", "metric_value": 1235},
            {"metric_group": "PACKET", "metric_name": "TOTAL_REVIEW_ROWS", "metric_value": 7},
            {"metric_group": "PACKET", "metric_name": "TOTAL_GROSS_PROFIT_REPRESENTED", "metric_value": 517.0},
            {"metric_group": "PACKET", "metric_name": "TOTAL_CAPITAL_LEFT_REPRESENTED", "metric_value": 12.0},
            {"metric_group": "PACKET", "metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0},
            {"metric_group": "PACKET", "metric_name": "STAGE12_CHANGES", "metric_value": 0},
        ]
    )


def _review_overlay_by_reason_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    return (
        rows_frame.groupby("overlay_category", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            actual_gross_profit_total=("actual_gross_profit", "sum"),
            capital_left_total=("capital_left_in_unsold_store_allocation", "sum"),
        )
        .reset_index()
    )


def _review_overlay_by_department_frame(rows_frame: pd.DataFrame) -> pd.DataFrame:
    return (
        rows_frame.groupby("department", dropna=False)
        .agg(
            row_count=("sku_number", "count"),
            actual_gross_profit_total=("actual_gross_profit", "sum"),
            capital_left_total=("capital_left_in_unsold_store_allocation", "sum"),
        )
        .reset_index()
    )


class PromotionsOperatorReviewMemoTests(unittest.TestCase):
    def test_build_operator_review_memo_orders_rows_and_writes_required_guidance(self) -> None:
        rows_frame = _review_overlay_rows_frame()
        result = build_promotions_operator_review_memo(
            review_overlay_summary_frame=_review_overlay_summary_frame(),
            review_overlay_rows_frame=rows_frame,
            review_overlay_by_reason_frame=_review_overlay_by_reason_frame(rows_frame),
            review_overlay_by_department_frame=_review_overlay_by_department_frame(rows_frame),
            review_overlay_memo_text="# Review Overlay Packet\n\nThis remains review-only.\n",
            manifest={"source_certification_status": "CERTIFIED_EXACT"},
        )

        priority_list = result.priority_list_frame
        by_category = result.by_category_frame.set_index("overlay_category")
        by_department = result.by_department_frame.set_index("department")
        summary = result.summary_frame.set_index(["metric_group", "metric_name"])

        self.assertEqual(
            priority_list["sku_number"].tolist(),
            ["3002", "3001", "1001", "2001", "4001", "5001", "6001"],
        )
        self.assertEqual(
            priority_list["review_priority_rank"].tolist(),
            [1, 1, 2, 3, 4, 5, 6],
        )
        self.assertEqual(
            str(priority_list.iloc[0]["human_review_question"]),
            "Why did this SKU sell despite weak/no prior promo evidence?",
        )
        self.assertEqual(
            str(priority_list.iloc[2]["human_review_question"]),
            "Would a small review-only floor have protected sales without overstocking?",
        )
        self.assertEqual(
            str(priority_list.iloc[4]["human_review_question"]),
            "Is the capital-drag headline too harsh given strong conversion and low residual capital?",
        )
        self.assertEqual(int(pd.to_numeric(priority_list["production_order_change_flag"], errors="coerce").sum()), 0)
        self.assertEqual(int(pd.to_numeric(priority_list["stage_12_change_flag"], errors="coerce").sum()), 0)

        self.assertEqual(int(by_category.loc["NO_PRIOR_DEMAND_SURPRISE_REVIEW", "review_priority_rank"]), 1)
        self.assertEqual(int(by_category.loc["NO_PRIOR_DEMAND_SURPRISE_REVIEW", "row_count"]), 2)
        self.assertEqual(
            str(by_category.loc["NO_PRIOR_DEMAND_SURPRISE_REVIEW", "human_review_question"]),
            "Why did this SKU sell despite weak/no prior promo evidence?",
        )
        self.assertEqual(int(by_department.loc["BABY CARE", "row_count"]), 2)
        self.assertEqual(
            str(by_department.loc["BABY CARE", "top_overlay_category"]),
            "NO_PRIOR_DEMAND_SURPRISE_REVIEW",
        )

        self.assertEqual(int(summary.loc[("MEMO_SCOPE", "TOTAL_REVIEW_ROWS"), "metric_value"]), 7)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "PRODUCTION_ORDER_CHANGES"), "metric_value"]), 0)
        self.assertEqual(int(summary.loc[("GUARDRAIL", "STAGE12_CHANGES"), "metric_value"]), 0)
        self.assertEqual(
            str(summary.loc[("AUTO_ORDERING", "STATUS"), "metric_display"]),
            "BLOCKED",
        )

        memo_text = result.memo_markdown
        self.assertIn("This is not an order file.", memo_text)
        self.assertIn("Start with NO_PRIOR_DEMAND_SURPRISE_REVIEW.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("Auto-ordering remains blocked.", memo_text)
        self.assertIn("3002 No Prior Surprise Higher GP", memo_text)
        self.assertIn("Keep action-layer calibration shadow-only", memo_text)


if __name__ == "__main__":
    unittest.main()