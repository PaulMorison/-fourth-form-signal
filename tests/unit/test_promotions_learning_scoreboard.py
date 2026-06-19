from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_learning_scoreboard import (  # noqa: E402
    build_promotions_learning_scoreboard,
)


def _review_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "row_count": 3597,
                "actual_units_total": 2450.0,
                "expected_promo_demand_total": 3685.0,
                "forecast_bias_units": 1235.0,
                "forecast_mae": 0.993884,
                "forecast_rmse": 1.424302,
                "forecast_correlation": 0.343344,
                "recommended_order_units_total": 1.0,
                "pl_allocation_units_total": 2233.0,
                "actual_sell_through_vs_store_adjusted": 1.097179,
                "actual_gross_profit_total": 11712.01,
                "capital_left_unsold_total": 15064.87,
            }
        ]
    )


def _cleanup_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue_type": "TOTAL_REMAINING_CLEANUP_ISSUES",
                "issue_count": 84,
                "sample_skus": "",
            },
            {
                "issue_type": "BUY_OR_ORDER_TEXT_WITH_ZERO_ORDER_UNITS",
                "issue_count": 2,
                "sample_skus": "199343, 354929",
            },
            {
                "issue_type": "LOW_SOH_OR_FLOOR_RISK_WITH_MATERIAL_DEMAND_NO_REVIEW_ACTION",
                "issue_count": 21,
                "sample_skus": "185498, 191100, 195106, 195108, 196346",
            },
            {
                "issue_type": "NO_PRIOR_PROMO_EVIDENCE_WITH_MATERIAL_ACTUAL_UNITS",
                "issue_count": 18,
                "sample_skus": "186539, 187200, 187204, 192034, 192040",
            },
            {
                "issue_type": "NO_DEMAND_WITH_MATERIAL_ACTUAL_UNITS",
                "issue_count": 12,
                "sample_skus": "191100, 196346, 19983, 275859, 30845",
            },
            {
                "issue_type": "CAPITAL_DRAG_HIGH_WITH_STRONG_SELL_THROUGH",
                "issue_count": 31,
                "sample_skus": "1485, 192168, 194737, 194747, 195592",
            },
        ]
    )


def _action_layer_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "summary_kind": "TOTAL",
                "label_name": "ALL_ROWS",
                "row_count": 3597,
                "actual_units_total": 2450.0,
                "capital_left_unsold_total": 15064.87,
                "sample_skus": "",
            },
            {
                "summary_kind": "RULE_FLAG",
                "label_name": "ACTION_TOO_CONSERVATIVE",
                "row_count": 69,
                "actual_units_total": 473.0,
                "capital_left_unsold_total": 0.0,
                "sample_skus": "71410, 94926, 195108, 185498, 199841",
            },
            {
                "summary_kind": "RULE_FLAG",
                "label_name": "REVIEW_SHOULD_HAVE_TRIGGERED",
                "row_count": 30,
                "actual_units_total": 200.0,
                "capital_left_unsold_total": 34.22,
                "sample_skus": "186539, 187200, 187204, 192034, 192040",
            },
            {
                "summary_kind": "RULE_FLAG",
                "label_name": "CAPITAL_GUARDRAIL_CORRECT",
                "row_count": 87,
                "actual_units_total": 72.0,
                "capital_left_unsold_total": 6699.03,
                "sample_skus": "1485, 192168, 194737, 194747, 195592",
            },
        ]
    )


def _capital_drag_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "summary_kind": "CLASSIFICATION",
                "label_name": "REVIEW_NOT_AUTO_BUY",
                "row_count": 20,
                "actual_gross_profit_total": 330.87,
                "capital_left_total": 18.23,
                "sample_skus": "33115, 482870, 75618, 194747, 67621",
            },
            {
                "summary_kind": "CLASSIFICATION",
                "label_name": "STRONG_CONVERTER_WRONG_RISK_HEADLINE",
                "row_count": 11,
                "actual_gross_profit_total": 119.57,
                "capital_left_total": 0.0,
                "sample_skus": "24553, 88112, 74931, 192168, 195592",
            },
            {
                "summary_kind": "TOTAL",
                "label_name": "ALL_ROWS",
                "row_count": 31,
                "actual_gross_profit_total": 450.44,
                "capital_left_total": 18.23,
                "sample_skus": "33115, 482870, 75618, 194747, 67621",
            },
        ]
    )


def _capital_drag_override_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "summary_kind": "TOTAL",
                "label_name": "ALL_ROWS",
                "row_count": 31,
                "override_candidate_rows": 31,
                "rows_updated_to_strong_conversion_capital_drag_review": 31,
                "production_order_change_count": 0,
                "stage12_change_count": 0,
                "remaining_true_capital_drag_rows": 0,
                "sample_skus": "67621, 24553, 88112, 33092, 48510",
            }
        ]
    )


def _low_soh_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "summary_kind": "CLASSIFICATION",
                "label_name": "ONLINE_FLOOR_PROTECTION_REVIEW",
                "row_count": 12,
                "actual_gross_profit_total": 267.39,
                "capital_left_total": 34.22,
                "sample_skus": "87729, 638781, 196346, 275859, 33264",
            },
            {
                "summary_kind": "CLASSIFICATION",
                "label_name": "TRUE_LOW_SOH_MISSED_DEMAND",
                "row_count": 5,
                "actual_gross_profit_total": 177.45,
                "capital_left_total": 0.0,
                "sample_skus": "71410, 94926, 195108, 185498, 199841",
            },
            {
                "summary_kind": "CLASSIFICATION",
                "label_name": "LOW_SOH_BUT_COVERED_BY_ON_ORDER",
                "row_count": 3,
                "actual_gross_profit_total": 135.33,
                "capital_left_total": 10.73,
                "sample_skus": "74457, 195106, 613487",
            },
            {
                "summary_kind": "CLASSIFICATION",
                "label_name": "NO_CHANGE_CAPITAL_PROTECTED",
                "row_count": 1,
                "actual_gross_profit_total": 97.16,
                "capital_left_total": 86.16,
                "sample_skus": "74028",
            },
            {
                "summary_kind": "TOTAL",
                "label_name": "ALL_ROWS",
                "row_count": 21,
                "actual_gross_profit_total": 677.33,
                "capital_left_total": 131.11,
                "sample_skus": "71410, 94926, 195108, 185498, 199841",
            },
        ]
    )


def _no_prior_demand_surprise_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "demand_evidence_label": "TOTAL",
                "row_count": 30,
                "actual_units_total": 200.0,
                "expected_promo_demand_total": 32.0,
                "actual_gross_profit_total": 924.74,
                "capital_left_total": 34.22,
            }
        ]
    )


class PromotionsLearningScoreboardTests(unittest.TestCase):
    def test_build_learning_scoreboard_tables_and_memo(self) -> None:
        result = build_promotions_learning_scoreboard(
            review_summary_frame=_review_summary_frame(),
            cleanup_summary_frame=_cleanup_summary_frame(),
            action_layer_summary_frame=_action_layer_summary_frame(),
            capital_drag_summary_frame=_capital_drag_summary_frame(),
            capital_drag_override_summary_frame=_capital_drag_override_summary_frame(),
            low_soh_summary_frame=_low_soh_summary_frame(),
            no_prior_demand_surprise_summary_frame=_no_prior_demand_surprise_summary_frame(),
            manifest={
                "source_certification_status": "CERTIFIED_EXACT",
                "actual_review_csv_path_used": "/tmp/actual.csv",
            },
        )

        summary = result.summary_frame.set_index(["metric_group", "metric_name"])
        decision_table = result.decision_table_frame.set_index("decision_category")
        issue_backlog = result.issue_backlog_frame.set_index("issue_backlog_category")
        next_actions = result.next_actions_frame.set_index("next_action_recommendation")

        self.assertEqual(int(summary.loc[("REVIEW_SCOPE", "TOTAL_ROWS_REVIEWED"), "metric_value"]), 3597)
        self.assertAlmostEqual(
            float(summary.loc[("FORECAST_HEAD", "FORECAST_CORRELATION"), "metric_value"]),
            0.343344,
            places=6,
        )
        self.assertEqual(
            int(summary.loc[("REPORT_CLEANUP", "CLEANUP_ISSUES_REDUCED"), "metric_value"]),
            693,
        )
        self.assertEqual(
            int(summary.loc[("CAPITAL_DRAG_OVERLAY", "OVERLAY_ROWS"), "metric_value"]),
            31,
        )
        self.assertEqual(
            int(summary.loc[("LOW_SOH_OVERLAY", "OVERLAY_ROWS"), "metric_value"]),
            21,
        )

        self.assertEqual(
            set(decision_table.index.tolist()),
            {
                "REPORT_CONTRACT_FIXED",
                "FORECAST_HEAD_NOT_READY",
                "ACTION_LAYER_TOO_CONSERVATIVE",
                "CAPITAL_DRAG_REVIEW_OVERLAY_READY",
                "LOW_SOH_REVIEW_OVERLAY_READY",
                "AUTO_ORDERING_NOT_READY",
                "STAGE_12_UNCHANGED",
                "PRODUCTION_ORDERING_UNCHANGED",
            },
        )
        self.assertEqual(
            str(decision_table.loc["REPORT_CONTRACT_FIXED", "decision_status"]),
            "READY_WITH_BACKLOG",
        )
        self.assertEqual(
            str(decision_table.loc["AUTO_ORDERING_NOT_READY", "decision_status"]),
            "BLOCKED",
        )

        self.assertEqual(
            set(issue_backlog.index.tolist()),
            {
                "FORECAST_CORRELATION_LOW",
                "FORECAST_BIAS_HIGH",
                "ACTION_LAYER_SUPPRESSION",
                "LOW_SOH_REVIEW_ROUTING",
                "ONLINE_FLOOR_PROTECTION",
                "NO_PRIOR_DEMAND_SURPRISE",
                "ZERO_ORDER_TEXT_RESIDUAL",
                "PANDAS_FRAGMENTATION_WARNING",
            },
        )
        self.assertEqual(int(issue_backlog.loc["ACTION_LAYER_SUPPRESSION", "issue_count"]), 69)
        self.assertEqual(int(issue_backlog.loc["NO_PRIOR_DEMAND_SURPRISE", "issue_count"]), 30)
        self.assertEqual(
            str(issue_backlog.loc["ZERO_ORDER_TEXT_RESIDUAL", "sample_skus"]),
            "199343, 354929",
        )

        self.assertEqual(
            set(next_actions.index.tolist()),
            {
                "BUILD_REVIEW_OVERLAY_PACKET",
                "INSPECT_TRUE_LOW_SOH_MISSED_DEMAND_SKUS",
                "INSPECT_NO_PRIOR_DEMAND_SURPRISE_SKUS",
                "CALIBRATE_ACTION_LAYER_SHADOW_ONLY",
                "KEEP_CAPITAL_GUARDRAIL_ACTIVE",
                "KEEP_AUTO_ORDERING_BLOCKED",
            },
        )
        self.assertEqual(int(next_actions.loc["BUILD_REVIEW_OVERLAY_PACKET", "row_count"]), 52)
        self.assertEqual(
            int(next_actions.loc["INSPECT_TRUE_LOW_SOH_MISSED_DEMAND_SKUS", "row_count"]),
            5,
        )
        self.assertEqual(
            int(next_actions.loc["CALIBRATE_ACTION_LAYER_SHADOW_ONLY", "row_count"]),
            99,
        )

        memo_text = result.memo_markdown
        self.assertIn("## 1. Forecast-Head Weakness", memo_text)
        self.assertIn("## 4. Review-Only Diagnostic Overlays", memo_text)
        self.assertIn("Do not change production ordering logic.", memo_text)
        self.assertIn("Build the review overlay packet next", memo_text)
        self.assertIn("Source certification: CERTIFIED_EXACT.", memo_text)


if __name__ == "__main__":
    unittest.main()