from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_pretrain_readiness_inspection import (  # noqa: E402
    build_promotions_pretrain_readiness_inspection,
)


def _metric_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class PromotionsPretrainReadinessInspectionTests(unittest.TestCase):
    def test_build_pretrain_readiness_outputs_for_blocked_full_train(self) -> None:
        model_vs_actual_summary_frame = pd.DataFrame(
            [
                {
                    "forecast_correlation": 0.343344,
                    "forecast_bias_units": 1235.0,
                }
            ]
        )
        action_layer_recalibration_summary_frame = pd.DataFrame(
            [
                {"summary_kind": "RULE_FLAG", "label_name": "ACTION_TOO_CONSERVATIVE", "row_count": 69},
                {"summary_kind": "RULE_FLAG", "label_name": "REVIEW_SHOULD_HAVE_TRIGGERED", "row_count": 30},
                {"summary_kind": "RULE_FLAG", "label_name": "ACTION_TOO_AGGRESSIVE", "row_count": 1},
            ]
        )
        report_contract_cleanup_summary_frame = pd.DataFrame(
            [
                {
                    "issue_type": "TOTAL_REMAINING_CLEANUP_ISSUES",
                    "issue_count": 84,
                }
            ]
        )
        learning_scoreboard_summary_frame = _metric_frame(
            [
                {"metric_name": "CLEANUP_ISSUES_REDUCED", "metric_value": 693.0},
                {"metric_name": "MULTIPLE_ACTION_CONFLICTS_REMAINING", "metric_value": 0.0},
                {"metric_name": "SHADOW_FIELDS_VISIBLE_REMAINING", "metric_value": 0.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGE_COUNT", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGE_COUNT", "metric_value": 0.0},
            ]
        )
        review_overlay_packet_summary_frame = _metric_frame(
            [
                {"metric_name": "TOTAL_REVIEW_ROWS", "metric_value": 99.0},
                {"metric_name": "NO_PRIOR_DEMAND_SURPRISE_REVIEW", "metric_value": 18.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGES", "metric_value": 0.0},
            ]
        )
        operator_review_summary_frame = _metric_frame(
            [
                {"metric_name": "TOTAL_REVIEW_ROWS", "metric_value": 99.0},
                {"metric_name": "PRIORITY_ONE_ROWS", "metric_value": 18.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGES", "metric_value": 0.0},
            ]
        )
        manual_inspection_summary_frame = _metric_frame(
            [
                {"metric_name": "INPUT_ROWS", "metric_value": 18.0},
                {"metric_name": "COMPLETE_ROWS", "metric_value": 0.0},
                {"metric_name": "INCOMPLETE_ROWS", "metric_value": 18.0},
                {"metric_name": "INVALID_ROWS", "metric_value": 0.0},
                {"metric_name": "CANDIDATE_READY_ROWS", "metric_value": 0.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGES", "metric_value": 0.0},
                {"metric_name": "EXPECTED_SCOPE_ROWS", "metric_value": 18.0},
                {"metric_name": "ACTUAL_SCOPE_ROWS", "metric_value": 18.0},
            ]
        )
        review_rule_candidates_frame = pd.DataFrame(
            columns=[
                "sku_number",
                "actual_gross_profit",
                "production_order_change_flag",
                "stage_12_change_flag",
            ]
        )

        result = build_promotions_pretrain_readiness_inspection(
            model_vs_actual_summary_frame=model_vs_actual_summary_frame,
            action_layer_recalibration_summary_frame=action_layer_recalibration_summary_frame,
            report_contract_cleanup_summary_frame=report_contract_cleanup_summary_frame,
            learning_scoreboard_summary_frame=learning_scoreboard_summary_frame,
            review_overlay_packet_summary_frame=review_overlay_packet_summary_frame,
            operator_review_summary_frame=operator_review_summary_frame,
            full_manual_inspection_summary_frame=manual_inspection_summary_frame,
            full_review_rule_candidates_frame=review_rule_candidates_frame,
        )

        summary = result.summary_frame.set_index("readiness_check")
        blockers = result.blockers_frame
        recommendations = result.recommendations_frame.set_index("recommendation_scope")

        self.assertEqual(summary.loc["manual_no_prior_labels_complete", "status"], "BLOCK")
        self.assertEqual(summary.loc["candidate_rows_available", "status"], "BLOCK")
        self.assertEqual(summary.loc["forecast_head_reliability", "status"], "BLOCK")
        self.assertEqual(summary.loc["action_layer_calibration_ready", "status"], "BLOCK")
        self.assertEqual(summary.loc["report_contract_clean_enough", "status"], "WARN")
        self.assertEqual(summary.loc["review_overlay_packet_ready", "status"], "PASS")
        self.assertEqual(summary.loc["production_order_guardrails_unchanged", "status"], "PASS")
        self.assertEqual(summary.loc["stage_12_unchanged", "status"], "PASS")
        self.assertIn("full=0/18 complete; batch1=0/8 complete", summary.loc["manual_no_prior_labels_complete", "metric_value"])
        self.assertIn("correlation=0.343", summary.loc["forecast_head_reliability", "metric_value"])
        self.assertIn("777 -> 84", summary.loc["report_contract_clean_enough", "metric_value"])
        self.assertEqual(summary.loc["full_manual_rows_expected", "metric_value"], "18")
        self.assertEqual(summary.loc["full_manual_rows_complete", "metric_value"], "0")
        self.assertEqual(summary.loc["batch1_rows_expected", "metric_value"], "8")
        self.assertEqual(summary.loc["batch1_rows_complete", "metric_value"], "0")
        self.assertEqual(summary.loc["batch1_candidate_ready_rows", "metric_value"], "0")
        self.assertEqual(summary.loc["partial_manual_review_flag", "metric_value"], "0")

        self.assertEqual(
            blockers["readiness_check"].tolist(),
            [
                "manual_no_prior_labels_complete",
                "candidate_rows_available",
                "forecast_head_reliability",
                "action_layer_calibration_ready",
            ],
        )
        self.assertEqual(result.final_recommendation, "DO_NOT_RUN_FULL_TRAIN_YET")
        self.assertFalse(result.full_train_allowed_flag)
        self.assertFalse(result.shadow_only_dry_run_allowed_flag)

        self.assertEqual(recommendations.loc["FULL_TRAIN", "recommendation"], "DO_NOT_RUN_FULL_TRAIN_YET")
        self.assertEqual(int(recommendations.loc["FULL_TRAIN", "allowed_flag"]), 0)
        self.assertEqual(recommendations.loc["NEXT_HIGH_VALUE_ACTION", "recommendation"], "COMPLETE_MANUAL_WORKSHEET_FIRST")
        self.assertEqual(recommendations.loc["DATA_INSPECTION", "recommendation"], "RUN_SHADOW_ONLY_DATA_INSPECTION")
        self.assertEqual(recommendations.loc["SHADOW_ONLY_DRY_RUN", "recommendation"], "RUN_END_TO_END_DRY_RUN_ONLY")
        self.assertEqual(int(recommendations.loc["SHADOW_ONLY_DRY_RUN", "allowed_flag"]), 0)

        memo_text = result.memo_markdown
        self.assertIn("This is a diagnostic gate only. No training was started.", memo_text)
        self.assertIn("Run full train now: NO.", memo_text)
        self.assertIn("Run shadow-only dry run now: NO.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("Final recommendation: DO_NOT_RUN_FULL_TRAIN_YET.", memo_text)
        self.assertIn("Blocking checks: manual_no_prior_labels_complete, candidate_rows_available, forecast_head_reliability, action_layer_calibration_ready.", memo_text)
        self.assertIn("Next highest-value action: COMPLETE_MANUAL_WORKSHEET_FIRST.", memo_text)

    def test_build_pretrain_readiness_outputs_for_partial_batch1_scope(self) -> None:
        model_vs_actual_summary_frame = pd.DataFrame(
            [{"forecast_correlation": 0.343344, "forecast_bias_units": 1235.0}]
        )
        action_layer_recalibration_summary_frame = pd.DataFrame(
            [
                {"summary_kind": "RULE_FLAG", "label_name": "ACTION_TOO_CONSERVATIVE", "row_count": 69},
                {"summary_kind": "RULE_FLAG", "label_name": "REVIEW_SHOULD_HAVE_TRIGGERED", "row_count": 30},
                {"summary_kind": "RULE_FLAG", "label_name": "ACTION_TOO_AGGRESSIVE", "row_count": 1},
            ]
        )
        report_contract_cleanup_summary_frame = pd.DataFrame(
            [{"issue_type": "TOTAL_REMAINING_CLEANUP_ISSUES", "issue_count": 84}]
        )
        learning_scoreboard_summary_frame = _metric_frame(
            [
                {"metric_name": "CLEANUP_ISSUES_REDUCED", "metric_value": 693.0},
                {"metric_name": "MULTIPLE_ACTION_CONFLICTS_REMAINING", "metric_value": 0.0},
                {"metric_name": "SHADOW_FIELDS_VISIBLE_REMAINING", "metric_value": 0.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGE_COUNT", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGE_COUNT", "metric_value": 0.0},
            ]
        )
        review_overlay_packet_summary_frame = _metric_frame(
            [
                {"metric_name": "TOTAL_REVIEW_ROWS", "metric_value": 99.0},
                {"metric_name": "NO_PRIOR_DEMAND_SURPRISE_REVIEW", "metric_value": 18.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGES", "metric_value": 0.0},
            ]
        )
        operator_review_summary_frame = _metric_frame(
            [
                {"metric_name": "TOTAL_REVIEW_ROWS", "metric_value": 99.0},
                {"metric_name": "PRIORITY_ONE_ROWS", "metric_value": 18.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGES", "metric_value": 0.0},
            ]
        )
        full_manual_inspection_summary_frame = _metric_frame(
            [
                {"metric_name": "INPUT_ROWS", "metric_value": 18.0},
                {"metric_name": "COMPLETE_ROWS", "metric_value": 0.0},
                {"metric_name": "INCOMPLETE_ROWS", "metric_value": 18.0},
                {"metric_name": "INVALID_ROWS", "metric_value": 0.0},
                {"metric_name": "CANDIDATE_READY_ROWS", "metric_value": 0.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGES", "metric_value": 0.0},
                {"metric_name": "EXPECTED_SCOPE_ROWS", "metric_value": 18.0},
                {"metric_name": "ACTUAL_SCOPE_ROWS", "metric_value": 18.0},
            ]
        )
        batch1_manual_inspection_summary_frame = _metric_frame(
            [
                {"metric_name": "INPUT_ROWS", "metric_value": 8.0},
                {"metric_name": "COMPLETE_ROWS", "metric_value": 8.0},
                {"metric_name": "INCOMPLETE_ROWS", "metric_value": 0.0},
                {"metric_name": "INVALID_ROWS", "metric_value": 0.0},
                {"metric_name": "CANDIDATE_READY_ROWS", "metric_value": 8.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGES", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGES", "metric_value": 0.0},
                {"metric_name": "EXPECTED_SCOPE_ROWS", "metric_value": 8.0},
                {"metric_name": "ACTUAL_SCOPE_ROWS", "metric_value": 8.0},
            ]
        )
        batch1_manual_inspection_summary_frame["inspection_scope"] = "BATCH_1_FAST_HIGH_VALUE"
        batch1_review_rule_candidates_frame = pd.DataFrame(
            [
                {
                    "sku_number": "88081",
                    "actual_gross_profit": 132.86,
                    "production_order_change_flag": 0,
                    "stage_12_change_flag": 0,
                },
                {
                    "sku_number": "92312",
                    "actual_gross_profit": 69.30,
                    "production_order_change_flag": 0,
                    "stage_12_change_flag": 0,
                },
            ]
        )

        result = build_promotions_pretrain_readiness_inspection(
            model_vs_actual_summary_frame=model_vs_actual_summary_frame,
            action_layer_recalibration_summary_frame=action_layer_recalibration_summary_frame,
            report_contract_cleanup_summary_frame=report_contract_cleanup_summary_frame,
            learning_scoreboard_summary_frame=learning_scoreboard_summary_frame,
            review_overlay_packet_summary_frame=review_overlay_packet_summary_frame,
            operator_review_summary_frame=operator_review_summary_frame,
            full_manual_inspection_summary_frame=full_manual_inspection_summary_frame,
            full_review_rule_candidates_frame=pd.DataFrame(
                columns=[
                    "sku_number",
                    "actual_gross_profit",
                    "production_order_change_flag",
                    "stage_12_change_flag",
                ]
            ),
            batch1_manual_inspection_summary_frame=batch1_manual_inspection_summary_frame,
            batch1_review_rule_candidates_frame=batch1_review_rule_candidates_frame,
        )

        summary = result.summary_frame.set_index("readiness_check")
        recommendations = result.recommendations_frame.set_index("recommendation_scope")

        self.assertEqual(summary.loc["manual_no_prior_labels_complete", "status"], "WARN")
        self.assertEqual(summary.loc["candidate_rows_available", "status"], "PASS")
        self.assertEqual(summary.loc["review_overlay_packet_ready", "status"], "WARN")
        self.assertEqual(
            summary.loc["review_overlay_packet_ready", "reason"],
            "Batch 1 partial review completed; full 18-row manual review remains incomplete.",
        )
        self.assertIn("Batch 1 candidate-ready shadow-only learning rows exist", summary.loc["candidate_rows_available", "reason"])
        self.assertEqual(summary.loc["full_manual_rows_expected", "metric_value"], "18")
        self.assertEqual(summary.loc["full_manual_rows_complete", "metric_value"], "0")
        self.assertEqual(summary.loc["batch1_rows_expected", "metric_value"], "8")
        self.assertEqual(summary.loc["batch1_rows_complete", "metric_value"], "8")
        self.assertEqual(summary.loc["batch1_candidate_ready_rows", "metric_value"], "2")
        self.assertEqual(summary.loc["partial_manual_review_flag", "metric_value"], "1")
        self.assertFalse(result.full_train_allowed_flag)
        self.assertFalse(result.shadow_only_dry_run_allowed_flag)
        self.assertEqual(recommendations.loc["FULL_TRAIN", "recommendation"], "DO_NOT_RUN_FULL_TRAIN_YET")
        self.assertEqual(int(recommendations.loc["FULL_TRAIN", "allowed_flag"]), 0)
        self.assertEqual(recommendations.loc["DATA_INSPECTION", "recommendation"], "RUN_SHADOW_ONLY_DATA_INSPECTION")
        self.assertEqual(int(recommendations.loc["DATA_INSPECTION", "allowed_flag"]), 1)
        self.assertEqual(int(recommendations.loc["SHADOW_ONLY_DRY_RUN", "allowed_flag"]), 0)


if __name__ == "__main__":
    unittest.main()