from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_shadow_training_roadmap import (  # noqa: E402
    build_promotions_shadow_training_roadmap,
)


def _metric_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class PromotionsShadowTrainingRoadmapTests(unittest.TestCase):
    def test_build_shadow_training_roadmap_for_blocked_train_and_allowed_shadow(self) -> None:
        pretrain_readiness_summary_frame = pd.DataFrame(
            [
                {
                    "readiness_check": "manual_no_prior_labels_complete",
                    "status": "BLOCK",
                    "metric_value": "0 complete / 18 incomplete / 0 invalid",
                    "threshold": "> 0 complete rows required; all 18 complete preferred",
                    "blocking_flag": 1,
                    "reason": "No manual no-prior rows are complete yet; 18 rows still need governed human labels.",
                    "recommended_next_action": "COMPLETE_MANUAL_WORKSHEET_FIRST",
                },
                {
                    "readiness_check": "candidate_rows_available",
                    "status": "BLOCK",
                    "metric_value": "0 candidate rows / $0.00 candidate gross profit",
                    "threshold": ">= 1 candidate-ready row",
                    "blocking_flag": 1,
                    "reason": "No candidate-ready rows exist yet, so there is no governed learning slice to carry into a rerun.",
                    "recommended_next_action": "COMPLETE_MANUAL_WORKSHEET_FIRST",
                },
                {
                    "readiness_check": "forecast_head_reliability",
                    "status": "BLOCK",
                    "metric_value": "correlation=0.343; bias=+1,235 units",
                    "threshold": "correlation >= 0.50",
                    "blocking_flag": 1,
                    "reason": "Forecast correlation 0.343 is below the 0.50 floor and bias remains +1,235 units.",
                    "recommended_next_action": "RUN_SHADOW_ONLY_DATA_INSPECTION",
                },
                {
                    "readiness_check": "action_layer_calibration_ready",
                    "status": "BLOCK",
                    "metric_value": "100 unresolved action-layer rule-flag rows",
                    "threshold": "0 unresolved rule-flag rows",
                    "blocking_flag": 1,
                    "reason": "Action-layer calibration is unresolved with 100 rule-flag rows still open.",
                    "recommended_next_action": "RUN_SHADOW_ONLY_DATA_INSPECTION",
                },
                {
                    "readiness_check": "report_contract_clean_enough",
                    "status": "WARN",
                    "metric_value": "777 -> 84 residual issues",
                    "threshold": "0 structural conflicts required; residual backlog should continue falling",
                    "blocking_flag": 0,
                    "reason": "Cleanup improved from 777 to 84 residual issues, but a review-only backlog remains.",
                    "recommended_next_action": "RUN_END_TO_END_DRY_RUN_ONLY",
                },
                {
                    "readiness_check": "production_order_guardrails_unchanged",
                    "status": "PASS",
                    "metric_value": "0",
                    "threshold": "0 production-order changes",
                    "blocking_flag": 0,
                    "reason": "Production-order guardrails remain unchanged at 0 across all governed diagnostic artifacts.",
                    "recommended_next_action": "DO_NOT_RUN_FULL_TRAIN_YET",
                },
                {
                    "readiness_check": "stage_12_unchanged",
                    "status": "PASS",
                    "metric_value": "0",
                    "threshold": "0 Stage 12 changes",
                    "blocking_flag": 0,
                    "reason": "Stage 12 guardrails remain unchanged at 0 across all governed diagnostic artifacts.",
                    "recommended_next_action": "DO_NOT_RUN_FULL_TRAIN_YET",
                },
            ]
        )
        pretrain_readiness_blockers_frame = pd.DataFrame(
            [
                {
                    "blocker_rank": 1,
                    "readiness_check": "manual_no_prior_labels_complete",
                    "status": "BLOCK",
                    "metric_value": "0 complete / 18 incomplete / 0 invalid",
                    "threshold": "> 0 complete rows required; all 18 complete preferred",
                    "blocking_flag": 1,
                    "reason": "No manual no-prior rows are complete yet; 18 rows still need governed human labels.",
                    "recommended_next_action": "COMPLETE_MANUAL_WORKSHEET_FIRST",
                },
                {
                    "blocker_rank": 2,
                    "readiness_check": "candidate_rows_available",
                    "status": "BLOCK",
                    "metric_value": "0 candidate rows / $0.00 candidate gross profit",
                    "threshold": ">= 1 candidate-ready row",
                    "blocking_flag": 1,
                    "reason": "No candidate-ready rows exist yet, so there is no governed learning slice to carry into a rerun.",
                    "recommended_next_action": "COMPLETE_MANUAL_WORKSHEET_FIRST",
                },
            ]
        )
        pretrain_readiness_recommendations_frame = pd.DataFrame(
            [
                {
                    "recommendation_rank": 1,
                    "recommendation_scope": "FULL_TRAIN",
                    "recommendation": "DO_NOT_RUN_FULL_TRAIN_YET",
                    "allowed_flag": 0,
                    "reason": "Full train is blocked by the current readiness blockers and should not be started now.",
                },
                {
                    "recommendation_rank": 2,
                    "recommendation_scope": "NEXT_HIGH_VALUE_ACTION",
                    "recommendation": "COMPLETE_MANUAL_WORKSHEET_FIRST",
                    "allowed_flag": 1,
                    "reason": "Finish the no-prior manual worksheet so governed labels can create or rule out shadow-only learning candidates.",
                },
                {
                    "recommendation_rank": 3,
                    "recommendation_scope": "DATA_INSPECTION",
                    "recommendation": "RUN_SHADOW_ONLY_DATA_INSPECTION",
                    "allowed_flag": 1,
                    "reason": "Keep the next pass diagnostic-only while forecast reliability and action-layer calibration remain unresolved.",
                },
                {
                    "recommendation_rank": 4,
                    "recommendation_scope": "SHADOW_ONLY_DRY_RUN",
                    "recommendation": "RUN_END_TO_END_DRY_RUN_ONLY",
                    "allowed_flag": 1,
                    "reason": "A shadow-only end-to-end dry run is allowed because review artifacts are aligned and production/Stage 12 guardrails remain unchanged.",
                },
            ]
        )
        model_vs_actual_summary_frame = pd.DataFrame(
            [
                {
                    "row_count": 3597,
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
        learning_scoreboard_summary_frame = _metric_frame(
            [
                {"metric_name": "TOTAL_ROWS_REVIEWED", "metric_value": 3597.0},
                {"metric_name": "CLEANUP_ISSUES_REDUCED", "metric_value": 693.0},
                {"metric_name": "PRODUCTION_ORDER_CHANGE_COUNT", "metric_value": 0.0},
                {"metric_name": "STAGE12_CHANGE_COUNT", "metric_value": 0.0},
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

        result = build_promotions_shadow_training_roadmap(
            pretrain_readiness_summary_frame=pretrain_readiness_summary_frame,
            pretrain_readiness_blockers_frame=pretrain_readiness_blockers_frame,
            pretrain_readiness_recommendations_frame=pretrain_readiness_recommendations_frame,
            model_vs_actual_summary_frame=model_vs_actual_summary_frame,
            action_layer_recalibration_summary_frame=action_layer_recalibration_summary_frame,
            learning_scoreboard_summary_frame=learning_scoreboard_summary_frame,
            manual_inspection_summary_frame=manual_inspection_summary_frame,
            review_rule_candidates_frame=review_rule_candidates_frame,
        )

        self.assertEqual(result.final_recommendation, "DO_NOT_RUN_FULL_TRAIN_YET")
        self.assertFalse(result.full_train_allowed_flag)
        self.assertTrue(result.shadow_only_dry_run_allowed_flag)
        self.assertEqual(result.top_blocker, "manual_no_prior_labels_complete")
        self.assertEqual(result.next_immediate_action, "COMPLETE_MANUAL_WORKSHEET_FIRST")

        summary = result.summary_frame.set_index("metric_name")
        self.assertEqual(int(summary.loc["ROADMAP_STEP_COUNT", "metric_value"]), 9)
        self.assertEqual(int(summary.loc["PRODUCTION_ORDER_CHANGES", "metric_value"]), 0)
        self.assertEqual(int(summary.loc["STAGE12_CHANGES", "metric_value"]), 0)
        self.assertEqual(float(summary.loc["TRAINING_READINESS_CURRENT_SCORE", "metric_value"]), 5.2)
        self.assertEqual(float(summary.loc["TRAINING_READINESS_TARGET_SCORE", "metric_value"]), 9.0)
        self.assertEqual(float(summary.loc["AUTO_ORDERING_CURRENT_SCORE", "metric_value"]), 5.0)
        self.assertEqual(float(summary.loc["AUTO_ORDERING_TARGET_SCORE", "metric_value"]), 9.0)

        steps = result.steps_frame.set_index("roadmap_step")
        self.assertEqual(len(steps.index), 9)
        self.assertEqual(steps.loc["COMPLETE_MANUAL_NO_PRIOR_LABELS", "current_status"], "BLOCKED_INCOMPLETE_LABELS")
        self.assertEqual(int(steps.loc["COMPLETE_MANUAL_NO_PRIOR_LABELS", "blocking_flag"]), 1)
        self.assertEqual(steps.loc["RUN_SHADOW_ONLY_DRY_TRAIN", "current_status"], "ALLOWED_SHADOW_ONLY_AFTER_DATA_INSPECTION")
        self.assertEqual(int(steps.loc["RUN_SHADOW_ONLY_DRY_TRAIN", "blocking_flag"]), 0)

        evidence = result.evidence_requirements_frame.set_index("evidence_requirement")
        self.assertEqual(len(evidence.index), 7)
        self.assertIn("18/18 complete", evidence.loc["MANUAL_LABELS_COMPLETE_FOR_NO_PRIOR_ROWS", "minimum_threshold"])
        self.assertIn("lower overstock risk and lower missed-sales risk", evidence.loc["SHADOW_ONLY_COMPARISON_BEATS_BASELINE_RISK", "minimum_threshold"])

        scores = result.score_lift_targets_frame.set_index("score_area")
        self.assertEqual(float(scores.loc["TRAINING_READINESS", "current_score"]), 5.2)
        self.assertEqual(float(scores.loc["TRAINING_READINESS", "target_score"]), 9.0)
        self.assertEqual(float(scores.loc["AUTO_ORDERING_READINESS", "current_score"]), 5.0)
        self.assertEqual(float(scores.loc["AUTO_ORDERING_READINESS", "target_score"]), 9.0)
        self.assertEqual(float(scores.loc["OPERATOR_REVIEW", "current_score"]), 9.2)
        self.assertEqual(float(scores.loc["GOVERNANCE", "current_score"]), 9.5)

        memo_text = result.memo_markdown
        self.assertIn("This roadmap does not start training.", memo_text)
        self.assertIn("Full train remains blocked.", memo_text)
        self.assertIn("Shadow-only dry run remains allowed.", memo_text)
        self.assertIn("Production order changes = 0.", memo_text)
        self.assertIn("Stage 12 changes = 0.", memo_text)
        self.assertIn("The path to 9/10 is evidence accumulation, not looser guardrails.", memo_text)
        self.assertIn("Training readiness can improve faster than auto-ordering readiness", memo_text)
        self.assertIn("Auto-ordering to 9/10 requires repeated shadow evidence across multiple promotions.", memo_text)
        self.assertTrue(memo_text.rstrip().endswith("Next immediate action: complete the 18-row manual worksheet."))


if __name__ == "__main__":
    unittest.main()