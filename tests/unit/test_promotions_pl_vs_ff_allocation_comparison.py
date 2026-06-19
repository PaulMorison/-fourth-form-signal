from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.store_allocation_actual_outcome_backtest import (  # noqa: E402
    build_store_allocation_actual_outcome_backtest,
)
from surfaces.promotions.reporting.store_prediction_download_builder import (  # noqa: E402
    _build_store_order_reconciliation_frame,
)


def _minimal_order_reconciliation_input_frame(**overrides: object) -> pd.DataFrame:
    base = {
        "store_action_label": ["LOW_SOH_PROTECT_AVAILABILITY"],
        "raw_model_order_units": [3],
        "raw_model_order_value": [30.0],
        "projected_SOH_at_promo_start": [0],
        "floor_units_required": [2],
        "expected_promo_demand": [2],
        "available_to_sell_before_floor": [0],
        "projected_stock_gap_units": [2],
        "retail_risk_reward_ratio": [1.5],
        "availability_risk_label": ["BELOW_2_UNIT_FLOOR_RISK"],
        "demand_evidence_label": ["CREDIBLE_PROMO_DEMAND"],
        "capital_drag_label": ["CAPITAL_DRAG_LOW"],
        "blocker_reason": [""],
        "promo_allocated_units": [9],
        "pack_size": [1],
        "avg_daily_units": [0.05],
        "expected_gp_on_speculative_units": [20.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


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
        "order_reconciliation_reason": ["Do not buy. Floor is protected."],
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
        "avg_daily_units": [0.05],
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


def _build_result(
    *,
    diagnostic_overrides: dict[str, object] | None = None,
    master_overrides: dict[str, object] | None = None,
    actual_overrides: dict[str, object] | None = None,
):
    return build_store_allocation_actual_outcome_backtest(
        stage11_diagnostic_frame=_stage11_diagnostic_frame(**(diagnostic_overrides or {})),
        stage11_master_frame=_stage11_master_frame(**(master_overrides or {})),
        actual_review_frame=_actual_review_frame(**(actual_overrides or {})),
        max_unmatched_rows=0,
        max_unmatched_rate=0.0,
    )


class PromotionsPlVsFfAllocationComparisonTests(unittest.TestCase):
    def test_segmented_shadow_policy_records_shadow_order_without_execution(self) -> None:
        reconciled = _build_store_order_reconciliation_frame(
            store_frame=_minimal_order_reconciliation_input_frame()
        )

        self.assertEqual(int(reconciled.loc[0, "low_soh_policy_candidate_flag"]), 1)
        self.assertEqual(int(reconciled.loc[0, "low_soh_policy_production_eligible_flag"]), 0)
        self.assertEqual(int(reconciled.loc[0, "low_soh_policy_final_order_units"]), 0)
        self.assertEqual(int(reconciled.loc[0, "low_soh_policy_shadow_order_units"]), 1)
        self.assertEqual(int(reconciled.loc[0, "shadow_policy_candidate_flag"]), 1)
        self.assertEqual(int(reconciled.loc[0, "shadow_policy_order_units"]), 1)
        self.assertEqual(int(reconciled.loc[0, "shadow_policy_should_publish_flag"]), 0)
        self.assertEqual(int(reconciled.loc[0, "shadow_policy_should_affect_final_order_flag"]), 0)
        self.assertEqual(int(reconciled.loc[0, "final_store_order_units"]), 0)
        self.assertEqual(str(reconciled.loc[0, "shadow_policy_name"]), "SEGMENTED_PL_PROVED_ORDER_1")
        self.assertEqual(
            str(reconciled.loc[0, "shadow_policy_segment"]),
            "PL_PROVED_DEMAND_BUT_OVERBOUGHT",
        )
        self.assertEqual(
            str(reconciled.loc[0, "low_soh_policy_guardrail_status"]),
            "PASS_SHADOW_ONLY",
        )

    def test_pack_moq_blocker_keeps_low_soh_row_non_executable(self) -> None:
        reconciled = _build_store_order_reconciliation_frame(
            store_frame=_minimal_order_reconciliation_input_frame(pack_size=[6])
        )

        self.assertEqual(int(reconciled.loc[0, "low_soh_policy_candidate_flag"]), 1)
        self.assertEqual(int(reconciled.loc[0, "low_soh_policy_production_eligible_flag"]), 0)
        self.assertEqual(int(reconciled.loc[0, "low_soh_policy_final_order_units"]), 0)
        self.assertEqual(int(reconciled.loc[0, "low_soh_policy_shadow_order_units"]), 0)
        self.assertEqual(int(reconciled.loc[0, "shadow_policy_candidate_flag"]), 1)
        self.assertEqual(int(reconciled.loc[0, "shadow_policy_order_units"]), 0)
        self.assertEqual(int(reconciled.loc[0, "final_store_order_units"]), 0)
        self.assertIn("PACK_MOQ_UNECONOMIC", str(reconciled.loc[0, "low_soh_policy_blocker_reason"]))
        self.assertIn("PACK_MOQ_UNECONOMIC", str(reconciled.loc[0, "shadow_policy_blocker_reason"]))

    def test_comparison_reports_30_day_target_excess(self) -> None:
        result = _build_result(
            actual_overrides={
                "pl_allocation_qty": [10],
                "actual_units_sold": [1],
                "avg_daily_units": [0.1],
                "last_received_cost": [4.0],
                "promo_effective_cost": [4.0],
            }
        )
        row = result.pl_vs_ff_allocation_mistake_comparison_frame.iloc[0]

        self.assertEqual(float(row["target_end_soh_units"]), 3.0)
        self.assertEqual(str(row["target_end_soh_basis"]), "30_DAY_SUPPLY")
        self.assertGreater(float(row["pl_excess_target_units"]), 0.0)

    def test_capital_free_success_is_identified(self) -> None:
        result = _build_result(
            actual_overrides={
                "pl_allocation_qty": [0],
                "actual_units_sold": [2],
                "avg_daily_units": [0.1],
            }
        )
        row = result.pl_vs_ff_allocation_mistake_comparison_frame.iloc[0]

        self.assertEqual(int(row["ff_low_soh_capital_free_success_flag"]), 1)
        self.assertEqual(str(row["ff_low_soh_mistake_label"]), "CAPITAL_FREE_SUCCESS")

    def test_pl_false_success_is_not_counted_as_clean_allocation(self) -> None:
        result = _build_result(
            actual_overrides={
                "pl_allocation_qty": [6],
                "actual_units_sold": [1],
                "total_stock_available": [11],
                "estimated_stock_left_after_promo": [10],
                "avg_daily_units": [0.0],
                "last_received_cost": [4.0],
                "promo_effective_cost": [4.0],
                "estimated_gross_profit_after_priceline_fees": [120.0],
            }
        )
        row = result.pl_vs_ff_allocation_mistake_comparison_frame.iloc[0]

        self.assertEqual(int(row["pl_false_success_flag"]), 1)
        self.assertEqual(str(row["pl_mistake_label"]), "PL_ALLOCATED_WHEN_SOH_ALREADY_SUFFICIENT")
        self.assertEqual(int(row["pl_allocation_correct_flag"]), 0)

    def test_negative_cash_conversion_is_flagged(self) -> None:
        result = _build_result(
            diagnostic_overrides={
                "projected_SOH_at_promo_start": [0],
                "current_soh": [0],
                "available_to_sell_before_floor": [0],
            },
            actual_overrides={
                "current_soh": [0],
                "pl_allocation_qty": [6],
                "total_stock_available": [6],
                "actual_units_sold": [0],
                "estimated_stock_left_after_promo": [6],
                "avg_daily_units": [0.0],
                "last_received_cost": [4.0],
                "promo_effective_cost": [4.0],
                "estimated_gross_profit_after_priceline_fees": [0.0],
            },
        )
        row = result.pl_vs_ff_allocation_mistake_comparison_frame.iloc[0]

        self.assertEqual(int(row["pl_negative_cash_conversion_flag"]), 1)
        self.assertLess(float(row["pl_cash_conversion_rate"]), 0.0)
        self.assertIn(str(row["pl_mistake_label"]), {"NEGATIVE_CASH_CONVERSION", "PL_ALLOCATED_NO_DEMAND"})

    def test_new_blocker_and_readiness_artifacts_are_built(self) -> None:
        result = _build_result(
            actual_overrides={
                "pl_allocation_qty": [6],
                "actual_units_sold": [1],
                "avg_daily_units": [0.0],
                "last_received_cost": [4.0],
                "promo_effective_cost": [4.0],
            }
        )

        self.assertFalse(result.score_98_blocker_diagnostic_frame.empty)
        self.assertIn("blocker_type", result.score_98_blocker_diagnostic_frame.columns)
        self.assertFalse(result.model_98_readiness_scorecard_frame.empty)
        self.assertIn("overall_score", set(result.model_98_readiness_scorecard_frame["metric_name"]))
        self.assertFalse(result.executive_premeeting_summary_frame.empty)
        self.assertIn("meeting_talk_track", result.executive_premeeting_summary_frame.columns)

    def test_scorecard_reports_annualised_effect(self) -> None:
        result = _build_result(
            actual_overrides={
                "pl_allocation_qty": [6],
                "actual_units_sold": [1],
                "avg_daily_units": [0.0],
                "last_received_cost": [4.0],
                "promo_effective_cost": [4.0],
            }
        )
        scorecard = result.pl_vs_ff_allocation_scorecard_frame.iloc[0]
        waterfall = result.capital_reallocation_waterfall_frame

        self.assertIn("annualised_net_cash_delta_vs_pl", result.pl_vs_ff_allocation_scorecard_frame.columns)
        self.assertGreater(float(scorecard["annualised_net_cash_delta_vs_pl"]), 0.0)
        self.assertIn("06_annualised_net_cash_delta_vs_pl", set(waterfall["waterfall_step"]))

    def test_scorecard_is_capped_below_98_unless_all_thresholds_pass(self) -> None:
        result = _build_result(
            actual_overrides={
                "pl_allocation_qty": [6],
                "actual_units_sold": [1],
                "avg_daily_units": [0.0],
                "last_received_cost": [4.0],
                "promo_effective_cost": [4.0],
            }
        )
        scorecard = result.pl_vs_ff_allocation_scorecard_frame.iloc[0]

        self.assertEqual(int(scorecard["all_98_thresholds_pass_flag"]), 0)
        self.assertLess(float(scorecard["model_progress_score_100"]), 98.0)
        self.assertIn("pl_false_success_rate", str(scorecard["next_lift_to_98"]))


if __name__ == "__main__":
    unittest.main()
