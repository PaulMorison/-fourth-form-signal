from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.store_allocation_actual_outcome_backtest import (  # noqa: E402
    build_store_allocation_actual_outcome_backtest,
    write_store_allocation_actual_outcome_backtest,
    _summarize_low_soh_policy_shadow,
)


def _stage11_diagnostic_frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": [1],
        "promotion_name": ["Winter Promo"],
        "promotion_start_date": ["2026-05-20"],
        "promotion_end_date": ["2026-05-27"],
        "sku_number": [1001],
        "sku_description": ["Test SKU"],
        "store_action_label": ["HOLD_STOCK"],
        "raw_model_order_units": [0],
        "provisional_review_order_units": [0],
        "final_store_order_units": [0],
        "raw_model_order_value": [0.0],
        "final_store_order_value": [0.0],
        "current_soh": [5],
        "projected_SOH_at_promo_start": [5],
        "floor_units_required": [2],
        "expected_promo_demand": [2],
        "available_to_sell_before_floor": [3],
        "projected_stock_gap_units": [0],
        "retail_risk_reward_ratio": [0.5],
        "capital_drag_label": ["CAPITAL_DRAG_LOW"],
        "availability_risk_label": ["FLOOR_PROTECTED"],
        "order_reconciliation_reason": [
            "Do not buy. Projected SOH at promotion start is 5, expected demand is 2, and the 2-unit floor is protected."
        ],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _stage11_master_frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": [1],
        "promotion_name": ["Winter Promo"],
        "promotion_start_date": ["2026-05-20"],
        "sku_number": [1001],
        "expected_gp_on_speculative_units": [0.0],
        "predicted_units_total_promo": [2.0],
        "predicted_units_until_promo_start": [0.0],
        "promo_start_target_soh_units": [2.0],
        "promo_type": ["discount"],
        "discount_percent": [20.0],
        "normal_price": [10.0],
        "promo_price": [8.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _actual_review_frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_number": [1],
        "promotion_start_date": ["20/05/2026"],
        "promotional_end_date": ["27/05/2026"],
        "promotion_name": ["Winter Promo"],
        "promo_type": ["discount"],
        "customer_offer": ["20% off"],
        "sku_number": [1001],
        "sku_description": ["Test SKU"],
        "department": ["Beauty"],
        "category": ["Skin Care"],
        "catalogue_position": ["Front"],
        "current_soh": [5],
        "qty_on_order": [0],
        "pl_allocation_qty": [0],
        "store_adjusted_qty": [0],
        "total_stock_available": [5],
        "actual_units_sold": [2],
        "estimated_stock_left_after_promo": [3],
        "avg_8_wk_unit_sales": [1.0],
        "avg_daily_units": [0.2],
        "promo_days": [7],
        "expected_units_during_promo": [2],
        "actual_units_vs_expected_units": [1.0],
        "capital_accepted_by_store_at_cost": [0.0],
        "capital_left_in_unsold_store_allocation": [0.0],
        "estimated_actual_gross_profit": [10.0],
        "allocation_quality_summary": ["COMPLIANT"],
        "customer_sell_through_result": ["COMPLIANT"],
        "capital_effectiveness_result": ["EFFECTIVE"],
        "pack_size": [1],
        "discount_percent": [20.0],
        "promo_price": [8.0],
        "last_received_cost": [4.0],
        "promo_cost_price": [4.0],
        "promo_effective_cost": [4.0],
        "promo_gm_pct": [35.0],
        "estimated_gross_profit_after_priceline_fees": [8.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _run_backtest(
    *,
    diagnostic_overrides: dict[str, object] | None = None,
    master_overrides: dict[str, object] | None = None,
    actual_overrides: dict[str, object] | None = None,
) -> tuple[pd.Series, pd.Series, pd.DataFrame, pd.DataFrame]:
    result = build_store_allocation_actual_outcome_backtest(
        stage11_diagnostic_frame=_stage11_diagnostic_frame(**(diagnostic_overrides or {})),
        stage11_master_frame=_stage11_master_frame(**(master_overrides or {})),
        actual_review_frame=_actual_review_frame(**(actual_overrides or {})),
        max_unmatched_rows=0,
        max_unmatched_rate=0.0,
    )
    return (
        result.rows_frame.iloc[0],
        result.summary_frame.iloc[0],
        result.shadow_comparison_frame,
        result.reason_quality_audit_frame,
    )


class PromotionsAllocationActualOutcomeBacktestTests(unittest.TestCase):
    def test_reason_quality_audit_flags_false_floor_protection_claim(self) -> None:
        row, _, _, reason_audit = _run_backtest(
            diagnostic_overrides={
                "store_action_label": ["NO_DEMAND"],
                "projected_SOH_at_promo_start": [1],
                "floor_units_required": [2],
                "expected_promo_demand": [1],
                "available_to_sell_before_floor": [0],
                "order_reconciliation_reason": [
                    "Do not buy. Demand evidence is weak and projected SOH of 1 already protects the 2-unit availability floor."
                ],
            },
            actual_overrides={
                "current_soh": [1],
                "total_stock_available": [1],
                "actual_units_sold": [0],
                "estimated_stock_left_after_promo": [1],
            },
        )

        self.assertEqual(int(row["current_floor_protected_flag"]), 0)
        self.assertEqual(int(reason_audit.loc[0, "reason_quality_issue_flag"]), 1)
        self.assertEqual(
            str(reason_audit.loc[0, "reason_quality_issue_class"]),
            "FALSE_FLOOR_PROTECTION_CLAIM",
        )

    def test_safe_no_order_success_sets_allocation_correct_flag(self) -> None:
        row, _, _, _ = _run_backtest(
            diagnostic_overrides={
                "store_action_label": ["HOLD_STOCK"],
                "projected_SOH_at_promo_start": [5],
                "expected_promo_demand": [2],
                "available_to_sell_before_floor": [3],
            },
            actual_overrides={
                "total_stock_available": [5],
                "actual_units_sold": [2],
                "estimated_stock_left_after_promo": [3],
            },
        )

        self.assertEqual(str(row["allocation_outcome_label"]), "SAFE_NO_ORDER")
        self.assertEqual(int(row["allocation_correct_flag"]), 1)

    def test_missed_sales_failure_is_incorrect(self) -> None:
        row, _, _, _ = _run_backtest(
            diagnostic_overrides={
                "store_action_label": ["NO_DEMAND"],
                "projected_SOH_at_promo_start": [1],
                "expected_promo_demand": [1],
                "available_to_sell_before_floor": [0],
                "projected_stock_gap_units": [1],
            },
            actual_overrides={
                "current_soh": [1],
                "total_stock_available": [1],
                "actual_units_sold": [3],
                "estimated_stock_left_after_promo": [0],
                "actual_units_vs_expected_units": [3.0],
            },
        )

        self.assertEqual(str(row["allocation_outcome_label"]), "MISSED_SALES_RISK")
        self.assertEqual(int(row["allocation_correct_flag"]), 0)

    def test_capital_drag_failure_is_over_allocated(self) -> None:
        row, _, _, _ = _run_backtest(
            diagnostic_overrides={
                "store_action_label": ["BUY"],
                "raw_model_order_units": [5],
                "final_store_order_units": [5],
                "raw_model_order_value": [25.0],
                "final_store_order_value": [25.0],
                "projected_SOH_at_promo_start": [3],
                "expected_promo_demand": [1],
                "available_to_sell_before_floor": [1],
                "projected_stock_gap_units": [5],
            },
            master_overrides={
                "expected_gp_on_speculative_units": [2.0],
            },
            actual_overrides={
                "current_soh": [3],
                "total_stock_available": [8],
                "actual_units_sold": [0],
                "estimated_stock_left_after_promo": [8],
                "actual_units_vs_expected_units": [0.0],
                "capital_left_in_unsold_store_allocation": [25.0],
                "allocation_quality_summary": ["COMPLIANT BUT NO DEMAND"],
                "customer_sell_through_result": ["POOR SELL THROUGH"],
                "capital_effectiveness_result": ["WEAK"],
            },
        )

        self.assertEqual(str(row["allocation_outcome_label"]), "OVER_ALLOCATED_CAPITAL_DRAG")
        self.assertEqual(int(row["allocation_correct_flag"]), 0)

    def test_gap_overstated_bias_label(self) -> None:
        row, _, _, _ = _run_backtest(
            diagnostic_overrides={
                "projected_SOH_at_promo_start": [5],
                "floor_units_required": [2],
                "projected_stock_gap_units": [5],
            },
            actual_overrides={
                "actual_units_sold": [4],
                "estimated_stock_left_after_promo": [1],
                "total_stock_available": [5],
            },
        )

        self.assertEqual(float(row["actual_stock_gap_units"]), 1.0)
        self.assertEqual(str(row["projected_gap_bias_label"]), "GAP_OVERSTATED")

    def test_gap_understated_bias_label(self) -> None:
        row, _, _, _ = _run_backtest(
            diagnostic_overrides={
                "projected_SOH_at_promo_start": [1],
                "floor_units_required": [2],
                "projected_stock_gap_units": [1],
            },
            actual_overrides={
                "current_soh": [1],
                "total_stock_available": [1],
                "actual_units_sold": [3],
                "estimated_stock_left_after_promo": [0],
            },
        )

        self.assertEqual(float(row["actual_stock_gap_units"]), 4.0)
        self.assertEqual(str(row["projected_gap_bias_label"]), "GAP_UNDERSTATED")

    def test_gap_correct_bias_label_within_one_unit(self) -> None:
        row, _, shadow_frame, _ = _run_backtest(
            diagnostic_overrides={
                "projected_SOH_at_promo_start": [2],
                "floor_units_required": [2],
                "projected_stock_gap_units": [2],
            },
            actual_overrides={
                "current_soh": [2],
                "total_stock_available": [2],
                "actual_units_sold": [1],
                "estimated_stock_left_after_promo": [1],
            },
        )

        self.assertEqual(float(row["actual_stock_gap_units"]), 1.0)
        self.assertEqual(str(row["projected_gap_bias_label"]), "GAP_CORRECT")
        self.assertIn("shadow_final_store_order_units", shadow_frame.columns)
        self.assertIn("current_allocation_correct_flag", shadow_frame.columns)

    def test_target_summary_warns_when_below_seventy_five_percent(self) -> None:
        stage11 = pd.concat(
            [
                _stage11_diagnostic_frame(),
                _stage11_diagnostic_frame(
                    store_number=[2],
                    sku_number=[1002],
                    sku_description=["Missed SKU"],
                    projected_SOH_at_promo_start=[1],
                    expected_promo_demand=[1],
                    available_to_sell_before_floor=[0],
                    store_action_label=["NO_DEMAND"],
                    projected_stock_gap_units=[1],
                    order_reconciliation_reason=["Do not auto-order. Projected SOH is below the 2-unit floor, but demand evidence is weak, so the system is not allocating extra capital automatically."],
                ),
            ],
            ignore_index=True,
        )
        master = pd.concat(
            [
                _stage11_master_frame(),
                _stage11_master_frame(store_number=[2], sku_number=[1002], expected_gp_on_speculative_units=[1.0]),
            ],
            ignore_index=True,
        )
        actual = pd.concat(
            [
                _actual_review_frame(),
                _actual_review_frame(
                    store_number=[2],
                    sku_number=[1002],
                    sku_description=["Missed SKU"],
                    current_soh=[1],
                    total_stock_available=[1],
                    actual_units_sold=[3],
                    estimated_stock_left_after_promo=[0],
                    actual_units_vs_expected_units=[3.0],
                ),
            ],
            ignore_index=True,
        )

        result = build_store_allocation_actual_outcome_backtest(
            stage11_diagnostic_frame=stage11,
            stage11_master_frame=master,
            actual_review_frame=actual,
            max_unmatched_rows=0,
            max_unmatched_rate=0.0,
        )
        summary = result.summary_frame.iloc[0]

        self.assertIn("allocation_correct_rate", result.summary_frame.columns)
        self.assertLess(float(summary["allocation_correct_rate"]), 0.75)
        self.assertEqual(str(summary["allocation_target_status"]), "WARN_BELOW_TARGET")

    def test_low_soh_shadow_candidate_with_baseline_demand_orders_capped_units(self) -> None:
        row, _, _, _ = _run_backtest(
            diagnostic_overrides={
                "store_action_label": ["HOLD_STOCK"],
                "projected_SOH_at_promo_start": [0],
                "expected_promo_demand": [1],
                "available_to_sell_before_floor": [0],
                "projected_stock_gap_units": [1],
                "raw_model_order_units": [0],
                "raw_model_order_value": [0.0],
                "final_store_order_units": [0],
            },
            actual_overrides={
                "current_soh": [0],
                "total_stock_available": [0],
                "actual_units_sold": [1],
                "estimated_stock_left_after_promo": [0],
                "avg_8_wk_unit_sales": [0.5],
                "avg_daily_units": [0.01],
                "pack_size": [1],
                "last_received_cost": [4.0],
                "promo_effective_cost": [4.0],
            },
        )

        self.assertEqual(int(row["low_soh_protection_candidate_flag"]), 1)
        self.assertEqual(str(row["low_soh_policy_shadow_label"]), "LOW_SOH_PROTECT_AVAILABILITY")
        self.assertGreaterEqual(int(row["low_soh_policy_shadow_order_units"]), 1)
        self.assertLessEqual(int(row["low_soh_policy_shadow_order_units"]), 3)

    def test_low_soh_shadow_blocks_high_pack_blowout_to_review_only(self) -> None:
        row, _, _, _ = _run_backtest(
            diagnostic_overrides={
                "store_action_label": ["HOLD_STOCK"],
                "projected_SOH_at_promo_start": [0],
                "expected_promo_demand": [2],
                "available_to_sell_before_floor": [0],
                "projected_stock_gap_units": [2],
                "final_store_order_units": [0],
            },
            actual_overrides={
                "current_soh": [0],
                "total_stock_available": [0],
                "actual_units_sold": [2],
                "estimated_stock_left_after_promo": [0],
                "avg_8_wk_unit_sales": [0.5],
                "avg_daily_units": [0.01],
                "pack_size": [6],
                "last_received_cost": [4.0],
                "promo_effective_cost": [4.0],
            },
        )

        self.assertEqual(int(row["low_soh_protection_candidate_flag"]), 1)
        self.assertEqual(str(row["low_soh_policy_shadow_label"]), "LOW_SOH_BORDERLINE_REVIEW")
        self.assertEqual(int(row["low_soh_policy_shadow_order_units"]), 0)
        self.assertGreaterEqual(int(row["low_soh_protection_shadow_order_units"]), 1)
        self.assertEqual(str(row["low_soh_protection_cap_reason"]), "pack_size_exceeds_3_unit_auto_order_cap")

    def test_reduce_holding_is_not_overridden_by_low_soh_shadow(self) -> None:
        row, _, _, _ = _run_backtest(
            diagnostic_overrides={
                "store_action_label": ["REDUCE_HOLDING"],
                "projected_SOH_at_promo_start": [0],
                "expected_promo_demand": [2],
                "available_to_sell_before_floor": [0],
                "projected_stock_gap_units": [2],
                "final_store_order_units": [0],
                "capital_drag_label": ["CAPITAL_DRAG_HIGH"],
            },
            actual_overrides={
                "current_soh": [0],
                "total_stock_available": [0],
                "actual_units_sold": [2],
                "estimated_stock_left_after_promo": [0],
                "avg_8_wk_unit_sales": [1.0],
                "avg_daily_units": [0.02],
            },
        )

        self.assertEqual(int(row["low_soh_protection_candidate_flag"]), 0)
        self.assertEqual(int(row["low_soh_policy_shadow_order_units"]), 0)
        self.assertEqual(str(row["low_soh_policy_shadow_label"]), "REDUCE_HOLDING")

    def test_low_soh_promotion_gate_requires_lift_without_capital_blowout(self) -> None:
        base = pd.DataFrame(
            {
                "store_action_label": ["HOLD_STOCK"],
                "store_action_label_v2": ["HOLD_STOCK"],
                "low_soh_protection_candidate_flag": [1],
                "current_allocation_correct_flag": [0],
                "low_soh_policy_shadow_allocation_correct_flag": [1],
                "current_missed_sales_risk_flag": [1],
                "low_soh_policy_shadow_missed_sales_risk_flag": [0],
                "current_capital_drag_flag": [0],
                "low_soh_policy_shadow_capital_drag_flag": [0],
                "current_ending_excess_stock_flag": [0],
                "low_soh_policy_shadow_ending_excess_stock_flag": [0],
                "low_soh_policy_shadow_improved_flag": [1],
                "low_soh_policy_shadow_worsened_flag": [0],
                "low_soh_policy_shadow_order_units": [1],
                "current_final_store_order_units": [0],
                "allocation_unit_cost": [5.0],
            }
        )

        promote_summary = _summarize_low_soh_policy_shadow(base).iloc[0]
        self.assertEqual(str(promote_summary["promote_policy_recommendation"]), "PROMOTE_LOW_SOH_POLICY_FROM_SHADOW")

        capital_blowout = pd.concat([base] * 20, ignore_index=True)
        capital_blowout.loc[0:2, "low_soh_policy_shadow_capital_drag_flag"] = 1
        blocked_summary = _summarize_low_soh_policy_shadow(capital_blowout).iloc[0]
        self.assertNotEqual(str(blocked_summary["promote_policy_recommendation"]), "PROMOTE_LOW_SOH_POLICY_FROM_SHADOW")

        worse = base.copy()
        worse["current_allocation_correct_flag"] = [1]
        worse["low_soh_policy_shadow_allocation_correct_flag"] = [0]
        worse["low_soh_policy_shadow_worsened_flag"] = [1]
        worse_summary = _summarize_low_soh_policy_shadow(worse).iloc[0]
        self.assertNotEqual(str(worse_summary["promote_policy_recommendation"]), "PROMOTE_LOW_SOH_POLICY_FROM_SHADOW")

    def test_writer_emits_low_soh_shadow_artifacts_and_required_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            diagnostic_path = Path(temp_dir) / "stage11_diagnostic.csv"
            master_path = Path(temp_dir) / "stage11_master.csv"
            actual_path = Path(temp_dir) / "actual_review.csv"
            output_root = Path(temp_dir) / "allocation_backtest"

            _stage11_diagnostic_frame(
                store_action_label=["HOLD_STOCK"],
                projected_SOH_at_promo_start=[0],
                expected_promo_demand=[1],
                available_to_sell_before_floor=[0],
                final_store_order_units=[0],
            ).to_csv(diagnostic_path, index=False)
            _stage11_master_frame().to_csv(master_path, index=False)
            _actual_review_frame(
                current_soh=[0],
                total_stock_available=[0],
                actual_units_sold=[1],
                estimated_stock_left_after_promo=[0],
                avg_8_wk_unit_sales=[0.5],
                pack_size=[1],
            ).to_csv(actual_path, index=False)

            artifacts = write_store_allocation_actual_outcome_backtest(
                stage11_diagnostic_csv_path=diagnostic_path,
                stage11_master_csv_path=master_path,
                actual_review_csv_path=actual_path,
                output_root=output_root,
                max_unmatched_rows=0,
                max_unmatched_rate=0.0,
            )

            audit = pd.read_csv(artifacts.low_soh_protection_shadow_audit_csv_path)
            summary = pd.read_csv(artifacts.low_soh_protection_shadow_summary_csv_path)
            self.assertTrue(Path(artifacts.low_soh_protection_shadow_audit_csv_path).exists())
            self.assertTrue(Path(artifacts.low_soh_protection_shadow_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.input_source_manifest_json_path).exists())
            outcome_summary = pd.read_csv(artifacts.summary_csv_path)

        for column_name in (
            "low_soh_policy_shadow_order_units",
            "low_soh_policy_shadow_label",
            "low_soh_policy_shadow_allocation_correct_flag",
            "promote_candidate_flag",
            "promote_blocker_reason",
        ):
            self.assertIn(column_name, audit.columns)
        for metric_name in (
            "candidate_rows",
            "shadow_allocation_correct_rate",
            "shadow_missed_sales_risk_rate",
            "shadow_overallocated_capital_drag_rate",
            "promote_policy_recommendation",
        ):
            self.assertIn(metric_name, summary.columns)
        self.assertIn("source_certification_status", outcome_summary.columns)
        self.assertEqual(outcome_summary.loc[0, "source_certification_status"], "CERTIFIED_EXACT")


if __name__ == "__main__":
    unittest.main()