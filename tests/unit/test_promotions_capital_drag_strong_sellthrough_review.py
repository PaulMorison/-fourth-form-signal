from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_capital_drag_strong_sellthrough_review import (  # noqa: E402
    build_promotions_capital_drag_strong_sellthrough_review,
)


def _cleanup_issue_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005],
            "issue_type": [
                "CAPITAL_DRAG_HIGH_BUT_STRONG_SELL_THROUGH",
                "CAPITAL_DRAG_HIGH_BUT_STRONG_SELL_THROUGH",
                "CAPITAL_DRAG_HIGH_BUT_STRONG_SELL_THROUGH",
                "CAPITAL_DRAG_HIGH_BUT_STRONG_SELL_THROUGH",
                "CAPITAL_DRAG_HIGH_BUT_STRONG_SELL_THROUGH",
            ],
        }
    )


def _recalibration_rows_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005],
            "department": ["SKINCARE", "SKINCARE", "SKINCARE", "HAIRCARE", "HAIRCARE"],
            "actual_units_sold": [2.0, 7.0, 3.0, 1.0, 1.0],
            "store_adjusted_units": [2.0, 4.0, 3.0, 10.0, 2.0],
            "actual_sell_through_vs_store_adjusted": [1.0, 1.75, 1.0, 0.2, 1.0],
            "estimated_actual_gross_profit": [12.0, 28.0, 9.0, 3.0, 4.0],
            "capital_left_unsold": [0.0, 0.0, 0.0, 120.0, 75.0],
            "expected_promo_demand": [2.0, 1.0, 2.0, 2.0, 1.0],
            "forecast_abs_error_units": [1.0, 4.0, 1.0, 1.0, 1.0],
        }
    )


def _visible_report_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005],
            "sku_description": [
                "Headline Review SKU",
                "Review Override SKU",
                "Conflict SKU",
                "True Capital Drag SKU",
                "Keep Guardrail SKU",
            ],
            "operator_decision": [
                "REDUCE_HOLDING",
                "REDUCE_HOLDING",
                "BUY",
                "REDUCE_HOLDING",
                "REDUCE_HOLDING",
            ],
            "operator_action": [
                "DO_NOT_BUY",
                "DO_NOT_BUY",
                "BUY",
                "DO_NOT_BUY",
                "DO_NOT_BUY",
            ],
            "order_units": [0, 0, 0, 0, 0],
            "reason_short": [
                "Do not buy.",
                "Do not buy.",
                "Buy now.",
                "Do not buy.",
                "Do not buy.",
            ],
            "risk_flag": [
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_HIGH",
                "LOW_SOH_NO_AUTO_BUY",
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_HIGH",
            ],
            "review_flag": [0, 0, 0, 0, 0],
        }
    )


def _audit_report_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005],
            "recommended_order_units": [0, 0, 0, 0, 0],
            "final_store_order_units": [0, 0, 0, 0, 0],
            "capital_drag_label": [
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_HIGH",
            ],
            "availability_risk_label": [
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
            ],
            "demand_evidence_label": [
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
            ],
        }
    )


def _review_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "row_count": 5,
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


class PromotionsCapitalDragStrongSellthroughReviewTests(unittest.TestCase):
    def test_build_review_rows_and_summaries(self) -> None:
        result = build_promotions_capital_drag_strong_sellthrough_review(
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
        override_rows = result.override_validation_rows_frame.set_index("sku_number")
        override_summary = result.override_validation_summary_frame.set_index(
            ["summary_kind", "label_name"]
        )

        self.assertEqual(int(len(result.rows_frame.index)), 5)
        self.assertEqual(
            str(rows.loc["1001", "diagnostic_classification"]),
            "STRONG_CONVERTER_WRONG_RISK_HEADLINE",
        )
        self.assertEqual(
            str(rows.loc["1002", "diagnostic_classification"]),
            "REVIEW_NOT_AUTO_BUY",
        )
        self.assertEqual(
            str(rows.loc["1003", "diagnostic_classification"]),
            "DATA_OR_LABEL_CONFLICT",
        )
        self.assertEqual(
            str(rows.loc["1004", "diagnostic_classification"]),
            "TRUE_CAPITAL_DRAG",
        )
        self.assertEqual(
            str(rows.loc["1005", "diagnostic_classification"]),
            "KEEP_GUARDRAIL_ACTIVE",
        )

        self.assertEqual(
            str(rows.loc["1002", "proposed_next_action"]),
            "ADD_CAPITAL_DRAG_OVERRIDE_REVIEW_FLAG",
        )
        self.assertEqual(
            str(rows.loc["1001", "proposed_next_action"]),
            "CHANGE_VISIBLE_RISK_TO_STRONG_CONVERSION_REVIEW",
        )
        self.assertEqual(
            str(rows.loc["1004", "proposed_next_action"]),
            "KEEP_CAPITAL_GUARDRAIL",
        )

        self.assertEqual(int(summary.loc[("TOTAL", "ALL_ROWS"), "row_count"]), 5)
        self.assertEqual(
            int(summary.loc[("CLASSIFICATION", "REVIEW_NOT_AUTO_BUY"), "row_count"]),
            1,
        )
        self.assertAlmostEqual(
            float(summary.loc[("TOTAL", "ALL_ROWS"), "share_of_remaining_cleanup_issues"]),
            5 / 12,
            places=6,
        )

        self.assertEqual(int(by_department.loc["SKINCARE", "row_count"]), 3)
        self.assertEqual(
            str(by_department.loc["SKINCARE", "top_proposed_next_action"]),
            "ADD_CAPITAL_DRAG_OVERRIDE_REVIEW_FLAG",
        )

        self.assertEqual(int(override_rows.loc["1001", "override_candidate_flag"]), 1)
        self.assertEqual(int(override_rows.loc["1002", "override_candidate_flag"]), 1)
        self.assertEqual(int(override_rows.loc["1003", "override_candidate_flag"]), 0)
        self.assertEqual(int(override_rows.loc["1004", "override_candidate_flag"]), 0)
        self.assertEqual(int(override_rows.loc["1005", "override_candidate_flag"]), 0)
        self.assertEqual(str(override_rows.loc["1001", "operator_action"]), "REVIEW")
        self.assertEqual(str(override_rows.loc["1001", "risk_flag"]), "STRONG_CONVERSION_CAPITAL_DRAG_REVIEW")
        self.assertEqual(int(override_rows.loc["1001", "review_flag"]), 1)
        self.assertEqual(
            str(override_rows.loc["1001", "reason_short"]),
            "Strong sell-through with low residual capital. Review capital-drag headline; do not auto-buy.",
        )
        self.assertEqual(float(override_rows.loc["1001", "order_units"]), 0.0)
        self.assertEqual(int(override_rows.loc["1001", "production_order_changed_flag"]), 0)
        self.assertEqual(
            str(override_rows.loc["1003", "operator_action"]),
            "BUY",
        )
        self.assertEqual(
            str(override_rows.loc["1003", "risk_flag"]),
            "LOW_SOH_NO_AUTO_BUY",
        )

        self.assertEqual(
            int(override_summary.loc[("TOTAL", "ALL_ROWS"), "override_candidate_rows"]),
            2,
        )
        self.assertEqual(
            int(
                override_summary.loc[
                    ("OVERRIDE", "OVERRIDE_CANDIDATE"),
                    "rows_updated_to_strong_conversion_capital_drag_review",
                ]
            ),
            2,
        )
        self.assertEqual(
            int(override_summary.loc[("TOTAL", "ALL_ROWS"), "production_order_change_count"]),
            0,
        )
        self.assertEqual(
            int(override_summary.loc[("TOTAL", "ALL_ROWS"), "remaining_true_capital_drag_rows"]),
            1,
        )

        department_pattern_rows = recommendations.loc[
            recommendations["proposed_next_action"].eq("INSPECT_DEPARTMENT_PATTERN")
        ]
        self.assertEqual(int(len(department_pattern_rows.index)), 1)
        self.assertEqual(
            str(department_pattern_rows.iloc[0]["department"]),
            "SKINCARE",
        )

        memo_text = result.memo_markdown
        self.assertIn("## 5. Recommendation", memo_text)
        self.assertIn("review-only override state", memo_text)
        self.assertIn("do not remove capital drag", memo_text)

        override_memo_text = result.override_validation_memo_markdown
        self.assertIn("visible/reporting review logic only", override_memo_text)
        self.assertIn("Normal Stage 11 generation still does not require actual outcome data", override_memo_text)
        self.assertIn("Rows updated to `STRONG_CONVERSION_CAPITAL_DRAG_REVIEW`: 2", override_memo_text)


if __name__ == "__main__":
    unittest.main()