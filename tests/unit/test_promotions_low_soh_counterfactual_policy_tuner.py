from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.low_soh_counterfactual_policy_tuner import (  # noqa: E402
    LowSohCounterfactualConfig,
    build_actual_vs_expected_demand_diagnostic,
    build_counterfactual_base_frame,
    build_low_soh_counterfactual_policy_grid,
    build_low_soh_counterfactual_policy_scorecard,
    build_low_soh_counterfactual_tuner,
    build_low_soh_shadow_policy_recommendations,
    build_low_soh_shadow_segment_scorecard,
    build_missed_demand_diagnostic,
    write_low_soh_counterfactual_tuner,
)


def _feature_rows() -> list[dict[str, object]]:
    return [
        {
            "store_number": "772",
            "promotion_id": "promo-1",
            "promotion_name": "Winter Part 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1001",
            "sku_description": "Zero SOH credible demand",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_label_v2": "REVIEW",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "availability_risk_label": "ZERO_SOH_RISK",
            "capital_drag_label": "LOW",
            "current_soh": 0,
            "projected_SOH_at_promo_start": 0,
            "floor_units_required": 2,
            "available_to_sell_before_floor": 0,
            "expected_promo_demand": 1,
            "avg_daily_units": 0.05,
            "target_end_soh_units": 2,
            "actual_gross_profit_per_unit": 12,
            "unit_cost": 10,
            "pack_size": 1,
            "pl_allocation_qty": 4,
            "ff_current_order_units": 0,
        },
        {
            "store_number": "772",
            "promotion_id": "promo-1",
            "promotion_name": "Winter Part 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1002",
            "sku_description": "High cost low SOH",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_label_v2": "REVIEW",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "availability_risk_label": "ZERO_SOH_RISK",
            "capital_drag_label": "LOW",
            "current_soh": 0,
            "projected_SOH_at_promo_start": 0,
            "floor_units_required": 2,
            "available_to_sell_before_floor": 0,
            "expected_promo_demand": 1,
            "avg_daily_units": 0.05,
            "target_end_soh_units": 2,
            "actual_gross_profit_per_unit": 8,
            "unit_cost": 90,
            "pack_size": 1,
            "pl_allocation_qty": 4,
            "ff_current_order_units": 0,
        },
        {
            "store_number": "772",
            "promotion_id": "promo-1",
            "promotion_name": "Winter Part 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1003",
            "sku_description": "Large pack low SOH",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_label_v2": "REVIEW",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "availability_risk_label": "ZERO_SOH_RISK",
            "capital_drag_label": "LOW",
            "current_soh": 0,
            "projected_SOH_at_promo_start": 0,
            "floor_units_required": 2,
            "available_to_sell_before_floor": 0,
            "expected_promo_demand": 1,
            "avg_daily_units": 0.05,
            "target_end_soh_units": 2,
            "actual_gross_profit_per_unit": 8,
            "unit_cost": 10,
            "pack_size": 6,
            "pl_allocation_qty": 6,
            "ff_current_order_units": 0,
        },
        {
            "store_number": "772",
            "promotion_id": "promo-1",
            "promotion_name": "Winter Part 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1004",
            "sku_description": "Target excess risk",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_label_v2": "REVIEW",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "availability_risk_label": "LOW_SOH_RISK",
            "capital_drag_label": "LOW",
            "current_soh": 1,
            "projected_SOH_at_promo_start": 1,
            "floor_units_required": 2,
            "available_to_sell_before_floor": 1,
            "expected_promo_demand": 1,
            "avg_daily_units": 0.03,
            "target_end_soh_units": 1,
            "actual_gross_profit_per_unit": 6,
            "unit_cost": 30,
            "pack_size": 1,
            "pl_allocation_qty": 5,
            "ff_current_order_units": 0,
        },
        {
            "store_number": "772",
            "promotion_id": "promo-1",
            "promotion_name": "Winter Part 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1005",
            "sku_description": "Compressed demand",
            "store_action_label": "NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND",
            "store_action_label_v2": "REVIEW",
            "demand_evidence_label": "BASELINE_DEMAND",
            "availability_risk_label": "ZERO_SOH_RISK",
            "capital_drag_label": "LOW",
            "current_soh": 0,
            "projected_SOH_at_promo_start": 0,
            "floor_units_required": 2,
            "available_to_sell_before_floor": 0,
            "expected_promo_demand": 0.5,
            "avg_daily_units": 0.08,
            "target_end_soh_units": 2,
            "actual_gross_profit_per_unit": 7,
            "unit_cost": 8,
            "pack_size": 1,
            "pl_allocation_qty": 4,
            "ff_current_order_units": 0,
        },
        {
            "store_number": "772",
            "promotion_id": "promo-1",
            "promotion_name": "Winter Part 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1006",
            "sku_description": "Capital free covered",
            "store_action_label": "MAINTAIN",
            "store_action_label_v2": "NO_ORDER",
            "demand_evidence_label": "CREDIBLE_PROMO_DEMAND",
            "availability_risk_label": "HEALTHY",
            "capital_drag_label": "LOW",
            "current_soh": 3,
            "projected_SOH_at_promo_start": 3,
            "floor_units_required": 2,
            "available_to_sell_before_floor": 3,
            "expected_promo_demand": 1,
            "avg_daily_units": 0.05,
            "target_end_soh_units": 2,
            "actual_gross_profit_per_unit": 5,
            "unit_cost": 5,
            "pack_size": 1,
            "pl_allocation_qty": 0,
            "ff_current_order_units": 0,
        },
        {
            "store_number": "772",
            "promotion_id": "promo-1",
            "promotion_name": "Winter Part 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1007",
            "sku_description": "Weak low SOH",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_label_v2": "REVIEW",
            "demand_evidence_label": "WEAK_DEMAND",
            "availability_risk_label": "LOW_SOH_RISK",
            "capital_drag_label": "LOW",
            "current_soh": 1,
            "projected_SOH_at_promo_start": 1,
            "floor_units_required": 2,
            "available_to_sell_before_floor": 1,
            "expected_promo_demand": 0.4,
            "avg_daily_units": 0,
            "target_end_soh_units": 1,
            "actual_gross_profit_per_unit": 5,
            "unit_cost": 10,
            "pack_size": 1,
            "pl_allocation_qty": 0,
            "ff_current_order_units": 0,
        },
        {
            "store_number": "772",
            "promotion_id": "promo-1",
            "promotion_name": "Winter Part 1",
            "promotion_start_date": "2026-05-21",
            "promotion_end_date": "2026-06-03",
            "sku_number": "1008",
            "sku_description": "High cost weak low SOH",
            "store_action_label": "LOW_SOH_NO_AUTO_BUY",
            "store_action_label_v2": "REVIEW",
            "demand_evidence_label": "WEAK_DEMAND",
            "availability_risk_label": "ZERO_SOH_RISK",
            "capital_drag_label": "LOW",
            "current_soh": 0,
            "projected_SOH_at_promo_start": 0,
            "floor_units_required": 2,
            "available_to_sell_before_floor": 0,
            "expected_promo_demand": 0.4,
            "avg_daily_units": 0,
            "target_end_soh_units": 0,
            "actual_gross_profit_per_unit": 5,
            "unit_cost": 90,
            "pack_size": 1,
            "pl_allocation_qty": 0,
            "ff_current_order_units": 0,
        },
    ]


def _actual_rows() -> list[dict[str, object]]:
    return [
        {"sku_number": "1001", "actual_units_sold": 3, "actual_gross_profit_per_unit": 12, "unit_cost": 10, "pack_size": 1, "pl_allocation_qty": 4},
        {"sku_number": "1002", "actual_units_sold": 2, "actual_gross_profit_per_unit": 8, "unit_cost": 90, "pack_size": 1, "pl_allocation_qty": 4},
        {"sku_number": "1003", "actual_units_sold": 2, "actual_gross_profit_per_unit": 8, "unit_cost": 10, "pack_size": 6, "pl_allocation_qty": 6},
        {"sku_number": "1004", "actual_units_sold": 3, "actual_gross_profit_per_unit": 40, "unit_cost": 30, "pack_size": 1, "pl_allocation_qty": 5},
        {"sku_number": "1005", "actual_units_sold": 3, "actual_gross_profit_per_unit": 7, "unit_cost": 8, "pack_size": 1, "pl_allocation_qty": 4},
        {"sku_number": "1006", "actual_units_sold": 2, "actual_gross_profit_per_unit": 5, "unit_cost": 5, "pack_size": 1, "pl_allocation_qty": 0},
        {"sku_number": "1007", "actual_units_sold": 0, "actual_gross_profit_per_unit": 5, "unit_cost": 10, "pack_size": 1, "pl_allocation_qty": 0},
        {"sku_number": "1008", "actual_units_sold": 0, "actual_gross_profit_per_unit": 5, "unit_cost": 90, "pack_size": 1, "pl_allocation_qty": 0},
    ]


def _base_frame() -> pd.DataFrame:
    return build_counterfactual_base_frame(
        feature_inspection_frame=pd.DataFrame(_feature_rows()),
        actual_review_frame=pd.DataFrame(_actual_rows()),
    )


def _policy_row(grid: pd.DataFrame, policy_name: str, sku_number: str) -> pd.Series:
    rows = grid.loc[grid["candidate_policy_name"].eq(policy_name) & grid["sku_number"].eq(sku_number)]
    if rows.empty:
        raise AssertionError(f"Missing policy row for {policy_name} / {sku_number}")
    return rows.iloc[0]


class PromotionsLowSohCounterfactualPolicyTunerTests(unittest.TestCase):
    def test_current_ff_missed_units_reproduced_from_actuals(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())
        scorecard = build_low_soh_counterfactual_policy_scorecard(grid)

        current = scorecard.loc[scorecard["candidate_policy_name"].eq("CURRENT_FF")].iloc[0]
        self.assertEqual(current["missed_units"], 12.0)
        self.assertEqual(current["missed_sales_rows"], 5)

    def test_zero_soh_order_one_reduces_missed_demand(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())

        current = _policy_row(grid, "CURRENT_FF", "1001")
        candidate = _policy_row(grid, "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND", "1001")
        self.assertEqual(current["candidate_missed_units"], 3.0)
        self.assertEqual(candidate["candidate_order_units"], 1)
        self.assertEqual(candidate["candidate_missed_units"], 2.0)

    def test_high_cost_low_soh_row_blocked(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())

        row = _policy_row(grid, "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND", "1002")
        self.assertEqual(row["candidate_order_units"], 0)
        self.assertIn("unit_cost_exceeds_threshold", row["candidate_blocker_reason"])

    def test_pack_size_above_three_blocked(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())

        row = _policy_row(grid, "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND", "1003")
        self.assertEqual(row["candidate_order_units"], 0)
        self.assertIn("pack_moq_exceeds_3_unit_cap", row["candidate_blocker_reason"])

    def test_ending_stock_above_target_material_excess_label(self) -> None:
        base = _base_frame()
        grid = build_low_soh_counterfactual_policy_grid(base)

        row = _policy_row(grid, "PL_ALLOCATION", "1004")
        self.assertEqual(row["candidate_result_label"], "OVER_ALLOCATED_CAPITAL")
        self.assertEqual(row["candidate_excess_units_above_target"], 2.0)

    def test_positive_protected_gp_and_low_excess_has_positive_net_cash(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())

        row = _policy_row(grid, "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND", "1001")
        self.assertEqual(row["candidate_result_label"], "MISSED_DEMAND")
        self.assertGreater(row["candidate_protected_gp"], 0)
        self.assertEqual(row["candidate_excess_capital_above_target"], 0.0)
        self.assertGreater(row["candidate_net_cash_value"], 0)

    def test_negative_cash_conversion_penalized(self) -> None:
        rows = _base_frame()
        rows.loc[rows["sku_number"].eq("1004"), "actual_units_sold"] = 0
        grid = build_low_soh_counterfactual_policy_grid(rows)
        scorecard = build_low_soh_counterfactual_policy_scorecard(grid)

        row = _policy_row(grid, "PL_ALLOCATION", "1004")
        pl_scorecard = scorecard.loc[scorecard["candidate_policy_name"].eq("PL_ALLOCATION")].iloc[0]
        self.assertEqual(row["candidate_result_label"], "NEGATIVE_CASH_CONVERSION")
        self.assertGreater(pl_scorecard["negative_cash_conversion_rows"], 0)
        self.assertEqual(pl_scorecard["production_recommendation"], "REJECT_TOO_BROAD")

    def test_safer_policy_ranks_above_broad_pl_when_capital_drag_high(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())
        scorecard = build_low_soh_counterfactual_policy_scorecard(grid)

        safer_rank = scorecard.loc[scorecard["candidate_policy_name"].eq("ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND"), "policy_rank"].iloc[0]
        pl_rank = scorecard.loc[scorecard["candidate_policy_name"].eq("PL_ALLOCATION"), "policy_rank"].iloc[0]
        self.assertLess(safer_rank, pl_rank)

    def test_best_recommendation_is_shadow_not_production(self) -> None:
        result = build_low_soh_counterfactual_tuner(
            feature_inspection_frame=pd.DataFrame(_feature_rows()),
            actual_review_frame=pd.DataFrame(_actual_rows()),
        )

        best = result.policy_scorecard_frame.iloc[0]
        self.assertEqual(best["production_recommendation"], "PROMOTE_TO_SHADOW")
        self.assertNotIn("PRODUCTION", set(result.policy_scorecard_frame["production_recommendation"]))

    def test_missed_demand_diagnostic_classifies_zero_soh_real_demand(self) -> None:
        diagnostic = build_missed_demand_diagnostic(_base_frame())

        row = diagnostic.loc[diagnostic["sku_number"].eq("1001")].iloc[0]
        self.assertEqual(row["likely_failure_type"], "ZERO_SOH_REAL_DEMAND")
        self.assertEqual(row["recommended_policy_to_test"], "ORDER_1_IF_ZERO_SOH_AND_EXPECTED_DEMAND")

    def test_actual_vs_expected_diagnostic_flags_expected_le_one_actual_gt_two_compression(self) -> None:
        diagnostic = build_actual_vs_expected_demand_diagnostic(_base_frame())

        row = diagnostic.loc[diagnostic["sku_number"].eq("1005")].iloc[0]
        self.assertEqual(row["failure_type"], "DEMAND_COMPRESSED_TO_0_1_RANGE")
        self.assertEqual(row["expected_bucket"], "LE_1")
        self.assertEqual(row["actual_bucket"], "LE_5")

    def test_zero_soh_repeat_demand_classified_correctly(self) -> None:
        row = _base_frame().loc[lambda frame: frame["sku_number"].eq("1001")].iloc[0]

        self.assertEqual(row["low_soh_shadow_segment"], "ZERO_SOH_REPEAT_DEMAND")

    def test_zero_soh_hidden_demand_classified_correctly(self) -> None:
        row = _base_frame().loc[lambda frame: frame["sku_number"].eq("1005")].iloc[0]

        self.assertEqual(row["low_soh_shadow_segment"], "ZERO_SOH_HIDDEN_DEMAND")

    def test_low_soh_weak_demand_blocked(self) -> None:
        base = _base_frame()
        row = base.loc[base["sku_number"].eq("1007")].iloc[0]
        grid = build_low_soh_counterfactual_policy_grid(base)
        candidate = _policy_row(grid, "SEGMENTED_COMBINED_ORDER_1", "1007")

        self.assertEqual(row["low_soh_shadow_segment"], "LOW_SOH_WEAK_DEMAND")
        self.assertEqual(candidate["candidate_order_units"], 0)

    def test_high_pack_moq_classified_as_uneconomic(self) -> None:
        row = _base_frame().loc[lambda frame: frame["sku_number"].eq("1003")].iloc[0]

        self.assertEqual(row["low_soh_shadow_segment"], "PACK_MOQ_UNECONOMIC")

    def test_high_cost_weak_demand_classified_as_high_cost_low_confidence(self) -> None:
        row = _base_frame().loc[lambda frame: frame["sku_number"].eq("1008")].iloc[0]

        self.assertEqual(row["low_soh_shadow_segment"], "HIGH_COST_LOW_CONFIDENCE")

    def test_pl_proved_demand_but_overbought_classified_correctly(self) -> None:
        row = _base_frame().loc[lambda frame: frame["sku_number"].eq("1004")].iloc[0]

        self.assertEqual(row["low_soh_shadow_segment"], "PL_PROVED_DEMAND_BUT_OVERBOUGHT")

    def test_segmented_zero_soh_order_one_orders_only_one_unit(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())
        ordered = grid.loc[grid["candidate_policy_name"].eq("SEGMENTED_ZERO_SOH_ORDER_1") & grid["candidate_order_units"].gt(0)]

        self.assertFalse(ordered.empty)
        self.assertEqual(int(ordered["candidate_order_units"].max()), 1)
        self.assertTrue(set(ordered["low_soh_shadow_segment"]).issubset({"ZERO_SOH_REPEAT_DEMAND", "ZERO_SOH_HIDDEN_DEMAND"}))

    def test_segmented_combined_order_one_does_not_exceed_one_unit(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())
        combined = grid.loc[grid["candidate_policy_name"].eq("SEGMENTED_COMBINED_ORDER_1")]

        self.assertLessEqual(int(combined["candidate_order_units"].max()), 1)

    def test_segment_scorecard_is_produced(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())
        segment_scorecard = build_low_soh_shadow_segment_scorecard(grid)

        self.assertIn("low_soh_shadow_segment", segment_scorecard.columns)
        self.assertIn("ZERO_SOH_REPEAT_DEMAND", set(segment_scorecard["low_soh_shadow_segment"]))

    def test_shadow_recommendation_artifact_is_produced(self) -> None:
        grid = build_low_soh_counterfactual_policy_grid(_base_frame())
        scorecard = build_low_soh_counterfactual_policy_scorecard(grid)
        recommendations = build_low_soh_shadow_policy_recommendations(scorecard)

        self.assertIn("SEGMENTED_COMBINED_ORDER_1", set(recommendations["candidate_policy_name"]))
        self.assertIn("should_promote_to_shadow", recommendations.columns)

    def test_no_segmented_policy_promotes_directly_to_stage11(self) -> None:
        result = build_low_soh_counterfactual_tuner(
            feature_inspection_frame=pd.DataFrame(_feature_rows()),
            actual_review_frame=pd.DataFrame(_actual_rows()),
        )

        self.assertFalse(result.shadow_policy_recommendations_frame["should_promote_to_stage11"].any())

    def test_best_acceptable_segmented_policy_can_promote_to_shadow_only(self) -> None:
        result = build_low_soh_counterfactual_tuner(
            feature_inspection_frame=pd.DataFrame(_feature_rows()),
            actual_review_frame=pd.DataFrame(_actual_rows()),
        )
        promoted = result.shadow_policy_recommendations_frame.loc[result.shadow_policy_recommendations_frame["should_promote_to_shadow"]]

        self.assertEqual(len(promoted), 1)
        self.assertTrue(str(promoted.iloc[0]["candidate_policy_name"]).startswith("SEGMENTED_"))
        self.assertFalse(bool(promoted.iloc[0]["should_promote_to_stage11"]))

    def test_cli_writer_emits_required_four_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            feature_csv = tmp_dir / "feature.csv"
            actual_csv = tmp_dir / "actual.csv"
            output_root = tmp_dir / "out"
            pd.DataFrame(_feature_rows()).to_csv(feature_csv, index=False)
            pd.DataFrame(_actual_rows()).to_csv(actual_csv, index=False)

            artifacts = write_low_soh_counterfactual_tuner(
                feature_inspection_csv_path=feature_csv,
                actual_review_csv_path=actual_csv,
                output_root=output_root,
            )

            self.assertTrue(Path(artifacts.policy_grid_csv_path).exists())
            self.assertTrue(Path(artifacts.policy_scorecard_csv_path).exists())
            self.assertTrue(Path(artifacts.segment_scorecard_csv_path).exists())
            self.assertTrue(Path(artifacts.shadow_policy_recommendations_csv_path).exists())
            self.assertTrue(Path(artifacts.missed_demand_diagnostic_csv_path).exists())
            self.assertTrue(Path(artifacts.actual_vs_expected_demand_diagnostic_csv_path).exists())


if __name__ == "__main__":
    unittest.main()
