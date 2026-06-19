from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_policy_slice_replay import (  # noqa: E402
    GovernedReplayAttributionError,
    REPLAY_MODE_BASELINE_COMPARISON,
    REPLAY_MODE_FUTURE_STAGE12,
    REPLAY_MODE_HISTORICAL_ONLY,
    build_policy_slice_replay_tables,
    run_policy_slice_replay,
)


class PromotionPolicySliceReplayTests(unittest.TestCase):
    def test_policy_slice_replay_identical_baseline_current_has_zero_deltas(self) -> None:
        frame = pd.DataFrame(
            {
                "promotion_row_key": ["row-1", "row-2", "row-3", "row-4"],
                "store_action": ["BUY", "HOLD", "DO NOT BUY", "REVIEW"],
                "decision_recommendation": ["ORDER", "HOLD", "DO_NOT_ORDER", "REVIEW"],
                "suggested_order_units": [8.0, 0.0, 0.0, 0.0],
                "review_reason": ["", "", "", "manager_review"],
                "publish_eligibility_reason": ["publishable", "excluded_hold", "excluded_do_not_order", "review_only"],
                "policy_adjustment_reason": [
                    "no_policy_adjustment",
                    "no_policy_adjustment",
                    "no_policy_adjustment",
                    "no_policy_adjustment",
                ],
                "feature_capital_deployment_posture": [
                    "no_new_policy_signal",
                    "no_new_policy_signal",
                    "no_new_policy_signal",
                    "review_unavailable_context",
                ],
            }
        )

        summary, row_deltas, policy_reason_delta, review_only_deltas = build_policy_slice_replay_tables(
            current_frame=frame,
            baseline_frame=frame,
            replay_mode=REPLAY_MODE_BASELINE_COMPARISON,
        )

        self.assertEqual(summary.affected_row_count, 0)
        self.assertEqual(summary.baseline_publishable_row_count, 1)
        self.assertEqual(summary.current_publishable_row_count, 1)
        self.assertEqual(summary.baseline_review_only_row_count, 1)
        self.assertEqual(summary.current_review_only_row_count, 1)
        self.assertFalse(summary.buy_order_widening_flag)
        self.assertTrue(all(delta == 0 for delta in summary.operator_action_deltas.values()))
        self.assertTrue(all(delta == 0 for delta in summary.decision_recommendation_deltas.values()))
        self.assertTrue(all(delta == 0 for delta in summary.stage12_publishability_deltas.values()))
        self.assertTrue(policy_reason_delta.empty)
        self.assertTrue(review_only_deltas.empty)
        self.assertFalse(row_deltas["affected_row_flag"].any())

    def test_policy_slice_replay_reduced_capital_without_buy_widening(self) -> None:
        baseline = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["BUY"],
                "decision_recommendation": ["ORDER"],
                "suggested_order_units": [8.0],
                "suggested_order_value": [32.0],
                "publish_eligibility_reason": ["publishable"],
                "policy_adjustment_reason": ["no_policy_adjustment"],
            }
        )
        current = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["BUY"],
                "decision_recommendation": ["ORDER"],
                "suggested_order_units": [5.0],
                "suggested_order_value": [20.0],
                "publish_eligibility_reason": ["publishable"],
                "policy_adjustment_reason": ["weak_same_discount_and_uplift_cap"],
            }
        )

        summary, row_deltas, policy_reason_delta, _ = build_policy_slice_replay_tables(
            current_frame=current,
            baseline_frame=baseline,
            replay_mode=REPLAY_MODE_FUTURE_STAGE12,
        )

        self.assertFalse(summary.buy_order_widening_flag)
        self.assertEqual(summary.operator_action_deltas["BUY"], 0)
        self.assertEqual(summary.decision_recommendation_deltas["ORDER"], 0)
        self.assertEqual(summary.stage12_publishability_deltas["publishable"], 0)
        self.assertAlmostEqual(summary.units_removed_total, 3.0)
        self.assertAlmostEqual(summary.capital_removed_total, 12.0)
        self.assertAlmostEqual(row_deltas.loc[0, "suggested_order_units_delta"], -3.0)
        self.assertAlmostEqual(row_deltas.loc[0, "order_value_delta"], -12.0)
        self.assertEqual(row_deltas.loc[0, "current_policy_units_removed_source"], "baseline_current_order_units_delta")
        self.assertEqual(
            row_deltas.loc[0, "current_policy_capital_at_risk_removed_source"],
            "baseline_current_order_value_delta",
        )
        self.assertEqual(policy_reason_delta.loc[0, "policy_adjustment_reason"], "weak_same_discount_and_uplift_cap")
        self.assertAlmostEqual(policy_reason_delta.loc[0, "capital_removed_delta"], 12.0)

    def test_policy_slice_replay_detects_buy_order_widening_and_policy_reason_hits(self) -> None:
        baseline = pd.DataFrame(
            {
                "promotion_row_key": ["row-1", "row-2"],
                "store_action": ["REVIEW", "BUY"],
                "decision_recommendation": ["REVIEW", "ORDER"],
                "suggested_order_units": [0.0, 8.0],
                "review_reason": ["manager_review", ""],
                "publish_eligibility_reason": ["review_only", "publishable"],
                "policy_adjustment_reason": ["no_policy_adjustment", "no_policy_adjustment"],
                "feature_capital_deployment_posture": ["review_unavailable_context", "no_new_policy_signal"],
            }
        )
        current = pd.DataFrame(
            {
                "promotion_row_key": ["row-1", "row-2"],
                "store_action": ["BUY", "BUY"],
                "decision_recommendation": ["ORDER", "ORDER"],
                "suggested_order_units": [4.0, 6.0],
                "review_reason": ["", ""],
                "publish_eligibility_reason": ["publishable", "publishable"],
                "policy_adjustment_reason": ["inventory_sufficient_low_value_history_review", "no_policy_adjustment"],
                "policy_units_removed": [3.0, 0.0],
                "policy_capital_at_risk_removed": [9.0, 0.0],
                "feature_capital_deployment_posture": ["review_speculative_capital_suppression", "no_new_policy_signal"],
            }
        )

        summary, row_deltas, policy_reason_summary, review_only_deltas = build_policy_slice_replay_tables(
            current_frame=current,
            baseline_frame=baseline,
            replay_mode=REPLAY_MODE_BASELINE_COMPARISON,
        )

        self.assertTrue(summary.buy_order_widening_flag)
        self.assertEqual(summary.buy_order_row_delta, 1)
        self.assertEqual(summary.publishable_row_delta, 1)
        self.assertEqual(summary.review_only_row_delta, -1)
        self.assertEqual(summary.operator_action_deltas["BUY"], 1)
        self.assertEqual(summary.operator_action_deltas["REVIEW"], -1)
        self.assertEqual(summary.decision_recommendation_deltas["ORDER"], 1)
        self.assertEqual(summary.stage12_publishability_deltas["publishable"], 1)
        self.assertEqual(summary.rows_hit_by_policy_reason_count, 1)
        self.assertAlmostEqual(summary.units_removed_total, 3.0)
        self.assertAlmostEqual(summary.capital_removed_total, 9.0)
        self.assertEqual(int(row_deltas.loc[row_deltas["row_key"].eq("row-1"), "buy_order_widened_flag"].iloc[0]), 1)
        self.assertEqual(policy_reason_summary.loc[0, "policy_adjustment_reason"], "inventory_sufficient_low_value_history_review")
        self.assertEqual(review_only_deltas.loc[0, "column_name"], "feature_capital_deployment_posture")

    def test_policy_slice_replay_writes_json_and_csv_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            baseline_path = temp_root / "baseline.csv"
            current_path = temp_root / "current.csv"
            output_root = temp_root / "replay"
            pd.DataFrame(
                {
                    "promotion_row_key": ["row-1"],
                    "decision_recommendation": ["ORDER"],
                    "suggested_order_units": [8.0],
                    "publish_eligibility_reason": ["publishable"],
                }
            ).to_csv(baseline_path, index=False)
            pd.DataFrame(
                {
                    "promotion_row_key": ["row-1"],
                    "decision_recommendation": ["ORDER"],
                    "suggested_order_units": [6.0],
                    "publish_eligibility_reason": ["publishable"],
                    "policy_adjustment_reason": ["weak_same_discount_and_uplift_cap"],
                    "policy_units_removed": [2.0],
                    "policy_capital_at_risk_removed": [5.0],
                }
            ).to_csv(current_path, index=False)

            artifacts = run_policy_slice_replay(
                current_csv_path=current_path,
                baseline_csv_path=baseline_path,
                output_root=output_root,
                run_id="unit-test-replay",
                replay_mode=REPLAY_MODE_FUTURE_STAGE12,
            )

            for output_path in (
                artifacts.runtime_manifest_path,
                artifacts.summary_json_path,
                artifacts.action_delta_csv_path,
                artifacts.publishability_delta_csv_path,
                artifacts.policy_reason_delta_csv_path,
                artifacts.row_deltas_csv_path,
                artifacts.widened_row_attribution_csv_path,
                artifacts.widened_row_attribution_json_path,
                artifacts.policy_reason_summary_csv_path,
                artifacts.review_only_deltas_csv_path,
            ):
                self.assertTrue(Path(output_path).exists())
            summary_payload = json.loads(Path(artifacts.summary_json_path).read_text(encoding="utf-8"))
            manifest_payload = json.loads(Path(artifacts.runtime_manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(summary_payload["replay_mode"], REPLAY_MODE_FUTURE_STAGE12)
            self.assertTrue(summary_payload["diagnostics_only"])
            self.assertIn("operator_action_deltas", summary_payload)
            self.assertIn("stage12_publishability_deltas", summary_payload)
            self.assertIn("action_delta_csv_path", manifest_payload["output_artifact_paths"])
            self.assertIn("publishability_delta_csv_path", manifest_payload["output_artifact_paths"])
            self.assertIn("policy_reason_delta_csv_path", manifest_payload["output_artifact_paths"])
            self.assertIn("widened_row_attribution_csv_path", manifest_payload["output_artifact_paths"])
            self.assertIn("widened_row_attribution_json_path", manifest_payload["output_artifact_paths"])
            self.assertFalse(manifest_payload["publish_tree_created"])
            self.assertFalse(manifest_payload["store_facing_csv_changed"])

    def test_policy_slice_replay_writes_widened_row_attribution_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            baseline_path = temp_root / "baseline.csv"
            current_path = temp_root / "current.csv"
            output_root = temp_root / "replay"
            pd.DataFrame(
                {
                    "promotion_row_key": ["row-1"],
                    "decision_recommendation": ["REVIEW"],
                    "suggested_order_units": [0.0],
                    "suggested_order_value": [0.0],
                    "review_reason": ["manager_review"],
                    "publish_eligibility_reason": ["review_only"],
                    "policy_adjustment_reason": ["no_policy_adjustment"],
                }
            ).to_csv(baseline_path, index=False)
            pd.DataFrame(
                {
                    "promotion_row_key": ["row-1"],
                    "decision_recommendation": ["ORDER"],
                    "suggested_order_units": [4.0],
                    "suggested_order_value": [20.0],
                    "review_reason": [""],
                    "publish_eligibility_reason": ["publishable"],
                    "policy_adjustment_reason": ["no_policy_adjustment"],
                    "feature_units_needed_for_trust_floor": [2.0],
                    "feature_capital_tied_above_trust_target": [5.0],
                    "feature_historical_promo_events_same_discount": [1.0],
                }
            ).to_csv(current_path, index=False)

            artifacts = run_policy_slice_replay(
                current_csv_path=current_path,
                baseline_csv_path=baseline_path,
                output_root=output_root,
                run_id="unit-test-widened-row",
                replay_mode=REPLAY_MODE_BASELINE_COMPARISON,
            )

            attribution = pd.read_csv(artifacts.widened_row_attribution_csv_path)
            attribution_payload = json.loads(Path(artifacts.widened_row_attribution_json_path).read_text())
            self.assertEqual(len(attribution.index), 1)
            self.assertEqual(attribution.loc[0, "row_key"], "row-1")
            self.assertEqual(attribution.loc[0, "baseline_decision_action"], "REVIEW")
            self.assertEqual(attribution.loc[0, "baseline_review_reason"], "manager_review")
            self.assertEqual(attribution.loc[0, "current_decision_action"], "ORDER")
            self.assertAlmostEqual(float(attribution.loc[0, "suggested_order_units_delta"]), 4.0)
            self.assertAlmostEqual(float(attribution.loc[0, "order_value_delta"]), 20.0)
            self.assertEqual(attribution.loc[0, "trust_floor_state"], "trust_floor_signal_present")
            self.assertEqual(attribution.loc[0, "speculative_capital_state"], "speculative_capital_signal_present")
            self.assertEqual(attribution.loc[0, "same_discount_evidence"], "same_discount_history_present")
            self.assertEqual(attribution.loc[0, "no_history_sparse_state"], "missing_no_history_sparse_evidence")
            self.assertEqual(attribution.loc[0, "equilibrium_signal_state"], "missing_equilibrium_signal_evidence")
            self.assertTrue(attribution_payload["diagnostics_only"])
            self.assertEqual(attribution_payload["widened_row_count"], 1)

    def test_policy_slice_replay_missing_required_artifact_fails_loud(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            current_path = temp_root / "current.csv"
            missing_baseline_path = temp_root / "missing-baseline.csv"
            pd.DataFrame(
                {
                    "promotion_row_key": ["row-1"],
                    "decision_recommendation": ["ORDER"],
                    "suggested_order_units": [5.0],
                }
            ).to_csv(current_path, index=False)

            with self.assertRaises(FileNotFoundError):
                run_policy_slice_replay(
                    current_csv_path=current_path,
                    baseline_csv_path=missing_baseline_path,
                    output_root=temp_root / "replay",
                    replay_mode=REPLAY_MODE_FUTURE_STAGE12,
                )

    def test_policy_slice_replay_missing_governed_action_basis_fails_loud(self) -> None:
        baseline = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "predicted_units": [12.0],
                "policy_adjustment_reason": ["no_policy_adjustment"],
            }
        )
        current = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "predicted_units": [10.0],
                "policy_adjustment_reason": ["weak_same_discount_and_uplift_cap"],
            }
        )

        with self.assertRaisesRegex(GovernedReplayAttributionError, "Governed replay action unavailable"):
            build_policy_slice_replay_tables(
                current_frame=current,
                baseline_frame=baseline,
                replay_mode=REPLAY_MODE_FUTURE_STAGE12,
            )

    def test_policy_slice_replay_missing_removal_basis_fails_loud(self) -> None:
        baseline = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["BUY"],
                "decision_recommendation": ["ORDER"],
                "publish_eligibility_reason": ["publishable"],
                "policy_adjustment_reason": ["no_policy_adjustment"],
            }
        )
        current = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["BUY"],
                "decision_recommendation": ["ORDER"],
                "publish_eligibility_reason": ["publishable"],
                "policy_adjustment_reason": ["weak_same_discount_and_uplift_cap"],
            }
        )

        with self.assertRaisesRegex(GovernedReplayAttributionError, "Governed units removed unavailable"):
            build_policy_slice_replay_tables(
                current_frame=current,
                baseline_frame=baseline,
                replay_mode=REPLAY_MODE_FUTURE_STAGE12,
            )

    def test_policy_slice_replay_missing_capital_basis_fails_loud(self) -> None:
        baseline = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["BUY"],
                "decision_recommendation": ["ORDER"],
                "suggested_order_units": [8.0],
                "publish_eligibility_reason": ["publishable"],
                "policy_adjustment_reason": ["no_policy_adjustment"],
            }
        )
        current = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["BUY"],
                "decision_recommendation": ["ORDER"],
                "suggested_order_units": [5.0],
                "publish_eligibility_reason": ["publishable"],
                "policy_adjustment_reason": ["weak_same_discount_and_uplift_cap"],
            }
        )

        with self.assertRaisesRegex(GovernedReplayAttributionError, "Governed capital removed unavailable"):
            build_policy_slice_replay_tables(
                current_frame=current,
                baseline_frame=baseline,
                replay_mode=REPLAY_MODE_FUTURE_STAGE12,
            )

    def test_policy_slice_replay_positive_technical_forecast_does_not_imply_buy_or_publish(self) -> None:
        frame = pd.DataFrame(
            {
                "promotion_row_key": ["row-1", "row-2"],
                "store_action": ["HOLD", "DO NOT BUY"],
                "decision_recommendation": ["HOLD", "DO_NOT_ORDER"],
                "predicted_units": [25.0, 30.0],
                "predicted_units_total_promo": [100.0, 120.0],
                "publish_eligibility_reason": ["excluded_hold", "excluded_do_not_order"],
                "policy_adjustment_reason": ["no_policy_adjustment", "no_policy_adjustment"],
            }
        )

        summary, row_deltas, _, _ = build_policy_slice_replay_tables(
            current_frame=frame,
            baseline_frame=frame,
            replay_mode=REPLAY_MODE_BASELINE_COMPARISON,
        )

        self.assertEqual(summary.current_buy_order_row_count, 0)
        self.assertEqual(summary.current_publishable_row_count, 0)
        self.assertEqual(summary.current_review_only_row_count, 0)
        self.assertFalse(summary.buy_order_widening_flag)
        self.assertEqual(summary.stage12_publishability_deltas["excluded"], 0)
        self.assertTrue(row_deltas["suggested_order_units_delta"].isna().all())

    def test_policy_slice_replay_duplicate_promotion_row_key_fails_loud(self) -> None:
        current = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["BUY"],
                "decision_recommendation": ["ORDER"],
                "suggested_order_units": [5.0],
                "suggested_order_value": [20.0],
                "publish_eligibility_reason": ["publishable"],
            }
        )
        duplicate_baseline = pd.DataFrame(
            {
                "promotion_row_key": ["row-1", "row-1"],
                "store_action": ["BUY", "BUY"],
                "decision_recommendation": ["ORDER", "ORDER"],
                "suggested_order_units": [5.0, 5.0],
                "suggested_order_value": [20.0, 20.0],
                "publish_eligibility_reason": ["publishable", "publishable"],
            }
        )
        duplicate_current = duplicate_baseline.copy()

        with self.assertRaisesRegex(GovernedReplayAttributionError, "Duplicate replay row_key values in baseline: row-1"):
            build_policy_slice_replay_tables(
                current_frame=current,
                baseline_frame=duplicate_baseline,
                replay_mode=REPLAY_MODE_FUTURE_STAGE12,
            )
        with self.assertRaisesRegex(GovernedReplayAttributionError, "Duplicate replay row_key values in current: row-1"):
            build_policy_slice_replay_tables(
                current_frame=duplicate_current,
                baseline_frame=current,
                replay_mode=REPLAY_MODE_FUTURE_STAGE12,
            )

    def test_policy_slice_replay_review_only_added_column_appears_in_deltas(self) -> None:
        baseline = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["HOLD"],
                "decision_recommendation": ["HOLD"],
                "publish_eligibility_reason": ["excluded_hold"],
                "policy_adjustment_reason": ["no_policy_adjustment"],
            }
        )
        current = baseline.copy()
        current["feature_capital_deployment_posture"] = ["protect_trust_floor_before_capital"]

        _, _, _, review_only_deltas = build_policy_slice_replay_tables(
            current_frame=current,
            baseline_frame=baseline,
            replay_mode=REPLAY_MODE_BASELINE_COMPARISON,
        )

        delta = review_only_deltas.loc[
            review_only_deltas["column_name"].eq("feature_capital_deployment_posture")
        ].iloc[0]
        self.assertTrue(pd.isna(delta["baseline_value"]))
        self.assertEqual(delta["current_value"], "protect_trust_floor_before_capital")

    def test_policy_slice_replay_review_only_removed_column_appears_in_deltas(self) -> None:
        baseline = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["HOLD"],
                "decision_recommendation": ["HOLD"],
                "publish_eligibility_reason": ["excluded_hold"],
                "policy_adjustment_reason": ["no_policy_adjustment"],
                "feature_capital_deployment_posture": ["protect_trust_floor_before_capital"],
            }
        )
        current = baseline.drop(columns=["feature_capital_deployment_posture"])

        _, _, _, review_only_deltas = build_policy_slice_replay_tables(
            current_frame=current,
            baseline_frame=baseline,
            replay_mode=REPLAY_MODE_BASELINE_COMPARISON,
        )

        delta = review_only_deltas.loc[
            review_only_deltas["column_name"].eq("feature_capital_deployment_posture")
        ].iloc[0]
        self.assertEqual(delta["baseline_value"], "protect_trust_floor_before_capital")
        self.assertTrue(pd.isna(delta["current_value"]))

    def test_policy_slice_replay_publishability_bucket_integrity(self) -> None:
        frame = pd.DataFrame(
            {
                "promotion_row_key": ["row-1", "row-2", "row-3"],
                "store_action": ["HOLD", "DO NOT BUY", "HOLD"],
                "decision_recommendation": ["HOLD", "DO_NOT_ORDER", "HOLD"],
                "publish_eligibility_reason": [
                    "excluded_hold",
                    "excluded_do_not_order",
                    "excluded_review_required",
                ],
                "policy_adjustment_reason": [
                    "no_policy_adjustment",
                    "no_policy_adjustment",
                    "no_policy_adjustment",
                ],
            }
        )

        summary, _, _, _ = build_policy_slice_replay_tables(
            current_frame=frame,
            baseline_frame=frame,
            replay_mode=REPLAY_MODE_BASELINE_COMPARISON,
        )

        self.assertEqual(summary.current_publishable_row_count, 0)
        self.assertEqual(summary.current_review_only_row_count, 1)
        self.assertEqual(summary.stage12_publishability_deltas["publishable"], 0)
        self.assertEqual(summary.stage12_publishability_deltas["review_only"], 0)
        self.assertEqual(summary.stage12_publishability_deltas["excluded"], 0)

    def test_policy_slice_replay_future_mode_without_baseline_fails_loud(self) -> None:
        current = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "store_action": ["BUY"],
                "decision_recommendation": ["ORDER"],
                "suggested_order_units": [5.0],
                "publish_eligibility_reason": ["publishable"],
            }
        )

        with self.assertRaisesRegex(GovernedReplayAttributionError, "requires baseline_frame"):
            build_policy_slice_replay_tables(
                current_frame=current,
                replay_mode=REPLAY_MODE_FUTURE_STAGE12,
            )

    def test_policy_slice_replay_historical_only_current_slice_without_baseline(self) -> None:
        current = pd.DataFrame(
            {
                "promotion_row_key": ["row-1"],
                "decision_recommendation": ["REVIEW"],
                "suggested_order_units": [0.0],
                "review_reason": ["manager_review"],
                "policy_adjustment_reason": ["no_policy_adjustment"],
            }
        )

        summary, row_deltas, policy_reason_summary, review_only_deltas = build_policy_slice_replay_tables(
            current_frame=current,
            replay_mode=REPLAY_MODE_HISTORICAL_ONLY,
        )

        self.assertEqual(summary.replay_mode, REPLAY_MODE_HISTORICAL_ONLY)
        self.assertEqual(summary.baseline_row_count, 0)
        self.assertEqual(summary.current_review_only_row_count, 1)
        self.assertFalse(summary.buy_order_widening_flag)
        self.assertEqual(len(row_deltas.index), 1)
        self.assertTrue(policy_reason_summary.empty)
        self.assertTrue(review_only_deltas.empty)


if __name__ == "__main__":
    unittest.main()