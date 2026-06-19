from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_model_reliability_next_pass import (  # noqa: E402
    build_promotions_model_reliability_next_pass,
    write_promotions_model_reliability_next_pass,
)
from runtime.promotions.run_promotions_model_vs_actual_review import (  # noqa: E402
    write_promotions_model_vs_actual_review,
)


def _model_report_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010],
            "sku_description": [
                "Good Forecast SKU",
                "Buy Zero SKU",
                "Missed Demand SKU",
                "Capital Drag SKU",
                "No Prior Surprise SKU",
                "Low SOH Demand SKU",
                "Strong Sell Through SKU",
                "No Action SKU",
                "Guardrail Correct SKU",
                "Forecast Head Error SKU",
            ],
            "store_action_label": [
                "HOLD_STOCK",
                "BUY",
                "BORDERLINE_OOS_REVIEW",
                "BUY",
                "NO_PRIOR_PROMO_EVIDENCE_LOW_RISK",
                "LOW_SOH_NO_AUTO_BUY",
                "LOW_SOH_PROTECT_AVAILABILITY",
                "HOLD_STOCK",
                "REDUCE_HOLDING",
                "LOW_SOH_NO_AUTO_BUY",
            ],
            "raw_model_order_units": [0, 2, 0, 5, 2, 0, 1, 0, 0, 0],
            "provisional_review_order_units": [0, 0, 0, 5, 0, 0, 1, 0, 0, 0],
            "final_store_order_units": [0, 0, 0, 5, 0, 0, 1, 0, 0, 0],
            "expected_promo_demand": [2, 5, 2, 4, 3, 1, 3, 0, 2, 6],
            "demand_evidence_label": [
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
                "NEVER_SOLD_IN_PROMO",
                "NO_DEMAND",
                "PROVEN_DEMAND",
                "NO_DEMAND",
                "PROVEN_DEMAND",
                "PROVEN_DEMAND",
            ],
            "capital_drag_label": [
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_LOW",
                "CAPITAL_DRAG_HIGH",
                "CAPITAL_DRAG_LOW",
            ],
            "availability_risk_label": [
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "BELOW_2_UNIT_FLOOR_RISK",
                "BELOW_2_UNIT_FLOOR_RISK",
                "FLOOR_PROTECTED",
                "FLOOR_PROTECTED",
                "BELOW_2_UNIT_FLOOR_RISK",
            ],
            "order_reconciliation_reason": [
                "Hold stock. Expected demand is already covered.",
                "Buy signal remains visible in the raw model output.",
                "Order 3 units because the promotion should lift demand.",
                "Buy 5 units; the expected uplift justifies the order.",
                "Do not order by default because no prior promo evidence is available.",
                "Do not auto-order because the low-SOH rule suppressed the row.",
                "Protect the floor with a small order and keep availability visible.",
                "No action required.",
                "Do not buy. Current holding is high relative to expected demand and creates capital drag.",
                "Do not auto-order because low SOH is already visible and the forecast needs monitoring.",
            ],
            "human_review_required_flag": [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            "shadow_policy_name": ["shadow"] * 10,
            "shadow_policy_version": ["v1"] * 10,
            "shadow_policy_candidate_flag": [0] * 10,
            "shadow_policy_segment": [""] * 10,
            "shadow_policy_order_units": [0] * 10,
            "shadow_policy_guardrail_status": [""] * 10,
            "shadow_policy_blocker_reason": [""] * 10,
            "shadow_policy_should_publish_flag": [0] * 10,
            "shadow_policy_should_affect_final_order_flag": [0] * 10,
        }
    )


def _actual_outcome_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_number": [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010],
            "sku_description": [
                "Good Forecast SKU",
                "Buy Zero SKU",
                "Missed Demand SKU",
                "Capital Drag SKU",
                "No Prior Surprise SKU",
                "Low SOH Demand SKU",
                "Strong Sell Through SKU",
                "No Action SKU",
                "Guardrail Correct SKU",
                "Forecast Head Error SKU",
            ],
            "department": [
                "SKINCARE",
                "SKINCARE",
                "COSMETICS",
                "FRAGRANCE",
                "HAIRCARE",
                "SKINCARE",
                "COSMETICS",
                "FRAGRANCE",
                "HEALTH",
                "VITAMINS",
            ],
            "pl_allocation_qty": [0, 0, 0, 5, 0, 0, 1, 0, 10, 0],
            "store_adjusted_qty": [0, 0, 0, 5, 0, 0, 1, 0, 10, 0],
            "actual_units_sold": [2, 0, 6, 1, 6, 5, 5, 0, 1, 1],
            "estimated_actual_gross_profit": [8.0, 0.0, 14.0, 3.0, 16.0, 11.0, 10.0, 0.0, 1.5, 2.5],
            "capital_left_in_unsold_store_allocation": [0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 200.0, 0.0],
            "sell_through_pct_vs_store_adjusted_qty": [0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 5.0, 0.0, 0.1, 0.0],
            "customer_sell_through_result": [
                "GOOD SELL THROUGH",
                "NO SELL THROUGH",
                "GOOD SELL THROUGH",
                "POOR SELL THROUGH",
                "GOOD SELL THROUGH",
                "GOOD SELL THROUGH",
                "GOOD SELL THROUGH",
                "NO SELL THROUGH",
                "POOR SELL THROUGH",
                "LOW SELL THROUGH",
            ],
            "capital_effectiveness_result": [
                "EFFECTIVE",
                "WEAK",
                "EFFECTIVE",
                "WEAK",
                "EFFECTIVE",
                "EFFECTIVE",
                "EFFECTIVE",
                "WEAK",
                "WEAK",
                "WEAK",
            ],
            "allocation_quality_summary": [
                "GOOD ALLOCATION",
                "NO DEMAND",
                "MISSED DEMAND",
                "CAPITAL DRAG",
                "SURPRISE DEMAND",
                "SURPRISE DEMAND",
                "STRONG SELL THROUGH",
                "NO ACTION",
                "CAPITAL GUARDRAIL CORRECT",
                "FORECAST ERROR",
            ],
        }
    )


class PromotionsModelReliabilityNextPassTests(unittest.TestCase):
    def test_build_next_pass_labels_and_counts(self) -> None:
        result = build_promotions_model_reliability_next_pass(
            model_allocation_report_frame=_model_report_frame(),
            actual_outcome_report_frame=_actual_outcome_frame(),
            manifest={
                "source_certification_status": "CERTIFIED_EXACT",
                "source_certification_reason": "unit test",
            },
        )

        recalibration_rows = result.action_layer_recalibration_rows_frame.set_index("sku_number")
        no_prior_rows = result.no_prior_demand_surprise_rows_frame
        cleanup_summary = result.cleanup_summary_frame
        plan_fields = set(result.cleanup_plan_frame["proposed_field"].tolist())

        self.assertEqual(str(recalibration_rows.loc["1003", "action_layer_recalibration_label"]), "ACTION_TOO_CONSERVATIVE")
        self.assertEqual(str(recalibration_rows.loc["1004", "action_layer_recalibration_label"]), "ACTION_TOO_AGGRESSIVE")
        self.assertEqual(str(recalibration_rows.loc["1005", "action_layer_recalibration_label"]), "REVIEW_SHOULD_HAVE_TRIGGERED")
        self.assertEqual(str(recalibration_rows.loc["1006", "action_layer_recalibration_label"]), "REVIEW_SHOULD_HAVE_TRIGGERED")
        self.assertEqual(str(recalibration_rows.loc["1009", "action_layer_recalibration_label"]), "CAPITAL_GUARDRAIL_CORRECT")
        self.assertEqual(str(recalibration_rows.loc["1010", "action_layer_recalibration_label"]), "FORECAST_HEAD_ERROR_NOT_ACTION_ERROR")

        self.assertEqual(int(recalibration_rows["action_too_conservative_flag"].sum()), 3)
        self.assertEqual(int(recalibration_rows["review_should_have_triggered_flag"].sum()), 2)
        self.assertEqual(int(recalibration_rows["capital_guardrail_correct_flag"].sum()), 1)
        self.assertEqual(int(len(no_prior_rows.index)), 2)

        summary_counts = {
            row["issue_type"]: int(row["issue_count"])
            for _, row in cleanup_summary.iterrows()
        }
        self.assertGreater(summary_counts["TOTAL_REMAINING_CLEANUP_ISSUES"], 0)
        self.assertIn("operator_decision", plan_fields)
        self.assertIn("audit_only_shadow_fields", plan_fields)

        memo_text = result.model_reliability_next_step_memo_markdown
        self.assertIn("## 1. Executive conclusion", memo_text)
        self.assertIn("## 9. Next implementation recommendation", memo_text)

    def test_write_next_pass_outputs_from_review_folder(self) -> None:
        model_frame = _model_report_frame()
        actual_frame = _actual_outcome_frame()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            model_csv_path = temp_path / "model_report.csv"
            actual_csv_path = temp_path / "actual_report.csv"
            review_output = temp_path / "review_output"
            model_frame.to_csv(model_csv_path, index=False)
            actual_frame.to_csv(actual_csv_path, index=False)

            write_promotions_model_vs_actual_review(
                model_allocation_report_csv_path=model_csv_path,
                actual_outcome_report_csv_path=actual_csv_path,
                output_root=review_output,
                run_id="unit-test-review-root",
            )

            artifacts = write_promotions_model_reliability_next_pass(
                review_artifact_root=review_output,
            )

            expected_paths = [
                artifacts.report_contract_cleanup_plan_csv_path,
                artifacts.report_contract_cleanup_summary_csv_path,
                artifacts.report_contract_cleanup_memo_md_path,
                artifacts.action_layer_recalibration_rows_csv_path,
                artifacts.action_layer_recalibration_summary_csv_path,
                artifacts.action_layer_recalibration_memo_md_path,
                artifacts.no_prior_demand_surprise_rows_csv_path,
                artifacts.no_prior_demand_surprise_summary_csv_path,
                artifacts.model_reliability_next_step_memo_md_path,
            ]
            for expected_path in expected_paths:
                self.assertTrue(Path(expected_path).exists(), expected_path)

            recalibration_summary = pd.read_csv(
                artifacts.action_layer_recalibration_summary_csv_path,
                keep_default_na=False,
            )
            self.assertIn("ACTION_TOO_CONSERVATIVE", recalibration_summary["label_name"].tolist())

            next_step_memo = Path(artifacts.model_reliability_next_step_memo_md_path).read_text(
                encoding="utf-8"
            )
            self.assertIn("Keep units-head core unchanged.", next_step_memo)
            self.assertIn("Clean the operator report into one decision hierarchy.", next_step_memo)