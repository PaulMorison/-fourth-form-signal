from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_low_soh_material_demand_review import (  # noqa: E402
    build_promotions_low_soh_material_demand_review,
)


def _cleanup_issue_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1005],
            "issue_type": [
                "LOW_SOH_NO_AUTO_BUY_BUT_ACTUAL_DEMAND",
                "LOW_SOH_OR_FLOOR_RISK_WITH_MATERIAL_DEMAND_NO_REVIEW_ACTION",
                "LOW_SOH_OR_FLOOR_RISK_WITH_MATERIAL_DEMAND_NO_REVIEW_ACTION",
            ],
        }
    )


def _recalibration_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005, 1006, 1007],
            "department": [
                "SKINCARE",
                "FEMININE CARE",
                "SKINCARE",
                "HAIRCARE",
                "SKINCARE",
                "FRAGRANCE",
                "SKINCARE",
            ],
            "actual_units_sold": [7.0, 6.0, 5.0, 9.0, 8.0, 5.0, 7.0],
            "store_adjusted_units": [3.0, 4.0, 4.0, 3.0, 8.0, 2.0, 5.0],
            "actual_sell_through_vs_store_adjusted": [2.3333, 1.5, 1.25, 3.0, 1.0, 2.5, 1.4],
            "estimated_actual_gross_profit": [50.0, 20.0, 15.0, 30.0, 18.0, 9.0, 22.0],
            "capital_left_unsold": [0.0, 0.0, 10.0, 15.0, 80.0, 0.0, 5.0],
            "expected_promo_demand": [1.0, 1.0, 3.0, 2.0, 6.0, 4.0, 4.0],
            "forecast_abs_error_units": [6.0, 5.0, 2.0, 7.0, 2.0, 1.0, 3.0],
            "availability_risk_label": [
                "BELOW_2_UNIT_FLOOR_RISK",
                "FLOOR_PROTECTION_NEEDED",
                "NEVER_SOLD_IN_PROMO",
                "AVAILABILITY_REVIEW",
                "NEVER_SOLD_IN_PROMO",
                "AVAILABILITY_CHECK",
                "STOCK_OK",
            ],
            "store_action_label": [
                "LOW_SOH_NO_AUTO_BUY",
                "NO_DEMAND",
                "HOLD_STOCK_FLOOR_SAFE",
                "AVAILABILITY_REVIEW",
                "HOLD_STOCK_FLOOR_SAFE",
                "AVAILABILITY_CHECK",
                "REDUCE_HOLDING",
            ],
            "demand_label": [
                "LOW_SOH_NO_AUTO_BUY",
                "NO_DEMAND",
                "HOLD_STOCK_FLOOR_SAFE",
                "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
                "HOLD_STOCK_FLOOR_SAFE",
                "UNKNOWN",
                "CREDIBLE_PROMO_DEMAND",
            ],
        }
    )


def _visible_report_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005, 1006, 1007],
            "sku_description": [
                "True Low SOH Miss",
                "Floor Protection Review",
                "Covered By Inbound",
                "Forecast Underforecast",
                "Capital Protected",
                "Conflict Row",
                "Audit Floor Protected Only",
            ],
            "operator_decision": [
                "DO_NOT_BUY",
                "DO_NOT_BUY",
                "DO_NOT_BUY",
                "DO_NOT_BUY",
                "DO_NOT_BUY",
                "DO_NOT_BUY",
                "DO_NOT_BUY",
            ],
            "operator_action": [
                "NO_ORDER",
                "NO_ORDER",
                "NO_ORDER",
                "NO_ORDER",
                "NO_ORDER",
                "NO_ORDER",
                "NO_ORDER",
            ],
            "order_units": [0, 0, 0, 0, 0, 0, 0],
            "reason_short": [
                "Do not auto-order.",
                "Do not auto-order.",
                "Do not auto-order.",
                "Do not auto-order.",
                "Do not auto-order.",
                "Do not auto-order.",
                "Do not auto-order.",
            ],
            "risk_flag": [
                "BELOW_2_UNIT_FLOOR_RISK",
                "FLOOR_PROTECTION_NEEDED",
                "NEVER_SOLD_IN_PROMO",
                "AVAILABILITY_REVIEW",
                "NEVER_SOLD_IN_PROMO",
                "AVAILABILITY_CHECK",
                "CAPITAL_DRAG_HIGH",
            ],
            "review_flag": [0, 0, 0, 0, 0, 0, 0],
            "audit_notes": ["", "", "", "", "", "", ""],
        }
    )


def _audit_report_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005, 1006, 1007],
            "recommended_order_units": [0, 0, 0, 0, 0, 0, 0],
            "final_store_order_units": [0, 0, 0, 0, 0, 0, 0],
            "availability_risk_label": [
                "BELOW_2_UNIT_FLOOR_RISK",
                "FLOOR_PROTECTION_NEEDED",
                "NEVER_SOLD_IN_PROMO",
                "AVAILABILITY_REVIEW",
                "NEVER_SOLD_IN_PROMO",
                "AVAILABILITY_CHECK",
                "FLOOR_PROTECTED",
            ],
            "demand_evidence_label": [
                "LOW_SOH_NO_AUTO_BUY",
                "NO_DEMAND",
                "HOLD_STOCK_FLOOR_SAFE",
                "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
                "HOLD_STOCK_FLOOR_SAFE",
                "UNKNOWN",
                "CREDIBLE_PROMO_DEMAND",
            ],
            "current_soh": [1, 2, 1, 2, 20, 0, 8],
            "on_order_at_advice_time": [0, 0, 3, 0, 0, 0, 0],
            "projected_on_hand_at_promo_start": [1, 2, 4, 2, 20, 0, 8],
            "projected_SOH_at_promo_start": [1, 2, 4, 2, 20, 0, 8],
            "target_stock_day_one_units": [4, 3, 3, 5, 10, 2, 4],
            "target_SOH_at_promo_start": [4, 3, 3, 5, 10, 2, 4],
            "minimum_launch_stock_units": [0, 0, 0, 0, 0, 0, 0],
            "floor_units_required": [3, 3, 3, 3, 3, 2, 2],
            "available_to_sell_before_floor": [0, 0, 1, 0, 17, 0, 6],
            "projected_stock_gap_units": [3, 1, 0, 3, 0, 2, 0],
        }
    )


def _review_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "row_count": 7,
                "actual_review_source_status": "EXACT_REQUESTED_FILE_USED",
                "source_certification_status": "CERTIFIED_EXACT",
                "source_certification_reason": "unit test",
                "actual_review_csv_path_used": "/tmp/actual.csv",
                "actual_review_file_hash_sha256": "abc123",
            }
        ]
    )


def _cleanup_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue_type": "TOTAL_REMAINING_CLEANUP_ISSUES",
                "issue_count": 12,
            }
        ]
    )


class PromotionsLowSohMaterialDemandReviewTests(unittest.TestCase):
    def test_build_review_rows_and_summaries(self) -> None:
        result = build_promotions_low_soh_material_demand_review(
            cleanup_issue_frame=_cleanup_issue_frame(),
            recalibration_rows_frame=_recalibration_rows_frame(),
            visible_report_frame=_visible_report_frame(),
            audit_report_frame=_audit_report_frame(),
            review_summary_frame=_review_summary_frame(),
            cleanup_summary_frame=_cleanup_summary_frame(),
            manifest={
                "source_certification_status": "CERTIFIED_EXACT",
                "actual_review_csv_path_used": "/tmp/actual.csv",
            },
        )

        rows = result.rows_frame.set_index("sku_number")
        summary = result.summary_frame.set_index(["summary_kind", "label_name"])
        by_department = result.by_department_frame.set_index("department")
        recommendations = result.action_recommendations_frame

        self.assertEqual(int(len(result.rows_frame.index)), 6)
        self.assertNotIn("1007", rows.index)
        self.assertEqual(
            str(rows.loc["1001", "diagnostic_classification"]),
            "TRUE_LOW_SOH_MISSED_DEMAND",
        )
        self.assertEqual(
            str(rows.loc["1002", "diagnostic_classification"]),
            "ONLINE_FLOOR_PROTECTION_REVIEW",
        )
        self.assertEqual(
            str(rows.loc["1003", "diagnostic_classification"]),
            "LOW_SOH_BUT_COVERED_BY_ON_ORDER",
        )
        self.assertEqual(
            str(rows.loc["1004", "diagnostic_classification"]),
            "FORECAST_UNDERCALIBRATION_LOW_SOH",
        )
        self.assertEqual(
            str(rows.loc["1005", "diagnostic_classification"]),
            "NO_CHANGE_CAPITAL_PROTECTED",
        )
        self.assertEqual(
            str(rows.loc["1006", "diagnostic_classification"]),
            "DATA_OR_LABEL_CONFLICT",
        )

        self.assertEqual(
            str(rows.loc["1001", "proposed_next_action"]),
            "ADD_LOW_SOH_REVIEW_FLAG",
        )
        self.assertEqual(
            str(rows.loc["1002", "proposed_next_action"]),
            "ADD_ONLINE_FLOOR_REVIEW_FLAG",
        )
        self.assertEqual(
            str(rows.loc["1004", "proposed_next_action"]),
            "IMPROVE_LOW_SOH_DEMAND_CALIBRATION",
        )
        self.assertEqual(
            str(rows.loc["1005", "proposed_next_action"]),
            "KEEP_CURRENT_GUARDRAIL",
        )
        self.assertEqual(
            str(rows.loc["1003", "proposed_next_action"]),
            "NO_CHANGE",
        )
        self.assertEqual(
            str(rows.loc["1006", "proposed_next_action"]),
            "INSPECT_DATA_CONFLICT",
        )

        self.assertEqual(int(rows.loc["1001", "explicit_issue_alias_flag"]), 1)
        self.assertEqual(int(rows.loc["1003", "covered_by_on_order_flag"]), 1)
        self.assertEqual(int(rows.loc["1005", "covered_by_on_order_flag"]), 1)
        self.assertEqual(int(rows.loc["1005", "projected_covers_target_flag"]), 1)
        self.assertEqual(
            str(rows.loc["1002", "issue_type_evidence"]),
            "LOW_SOH_OR_FLOOR_RISK_WITH_MATERIAL_DEMAND_NO_REVIEW_ACTION",
        )

        self.assertEqual(int(summary.loc[("TOTAL", "ALL_ROWS"), "row_count"]), 6)
        self.assertEqual(
            int(summary.loc[("TOTAL", "ALL_ROWS"), "explicit_issue_alias_rows"]),
            3,
        )
        self.assertEqual(
            int(summary.loc[("CLASSIFICATION", "ONLINE_FLOOR_PROTECTION_REVIEW"), "row_count"]),
            1,
        )
        self.assertAlmostEqual(
            float(summary.loc[("TOTAL", "ALL_ROWS"), "share_of_remaining_cleanup_issues"]),
            0.5,
            places=6,
        )

        self.assertEqual(int(by_department.loc["SKINCARE", "row_count"]), 3)
        self.assertEqual(
            str(by_department.loc["SKINCARE", "top_proposed_next_action"]),
            "ADD_LOW_SOH_REVIEW_FLAG",
        )

        department_pattern_rows = recommendations.loc[
            recommendations["recommendation_scope"].eq("DEPARTMENT_PATTERN")
        ]
        self.assertEqual(int(len(department_pattern_rows.index)), 1)
        self.assertEqual(
            str(department_pattern_rows.iloc[0]["department"]),
            "SKINCARE",
        )

        memo_text = result.memo_markdown
        self.assertIn("## 5. Recommendation", memo_text)
        self.assertIn("Explicit legacy issue-alias rows inside this governed slice: 3", memo_text)
        self.assertIn("not auto-ordering", memo_text)


if __name__ == "__main__":
    unittest.main()