from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.model_input_quality import (  # noqa: E402
    BOUNDED_ZERO_ONE_COLUMNS,
    iter_default_model_use_feature_columns,
)
from models.promotions.allocation_calibration import compute_allocation_aware_cap_units  # noqa: E402
from state.promotions.feature_engineering.demand.ft_allocation_discipline import (  # noqa: E402
    ALLOCATION_DISCIPLINE_FEATURE_COLUMNS,
    apply_ft_allocation_discipline,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


class PromotionAllocationDisciplineFeatureTests(unittest.TestCase):
    def test_allocation_discipline_features_price_probability_backed_excess(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [120.0, 50.0, 120.0],
                "effective_cost_per_unit": [2.5, 3.0, 4.0],
                "feature_baseline_units_expected_promo_window": [20.0, 20.0, 20.0],
                "feature_probability_expected_units_consensus": [80.0, 100.0, 80.0],
                "feature_probability_uplift_supported_units": [40.0, 40.0, 40.0],
                "feature_probability_uplift_upper_units": [55.0, 50.0, 55.0],
                "feature_probability_uplift_confidence": [0.8, 0.7, 0.9],
                "feature_window_blend_conflict_score": [0.1, 0.2, 0.1],
                "feature_probability_demand_confidence_score": [0.75, 0.60, 0.90],
                "feature_probability_model_use_flag": [1.0, 1.0, 0.0],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        self.assertEqual(
            list(ALLOCATION_DISCIPLINE_FEATURE_COLUMNS),
            [column_name for column_name in ALLOCATION_DISCIPLINE_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertAlmostEqual(result.loc[0, "feature_allocation_vs_probability_expected_units_ratio"], 1.5)
        self.assertAlmostEqual(result.loc[0, "feature_allocated_units_minus_probability_expected_units"], 40.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_expected_excess_units"], 40.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_expected_excess_units_pct"], 0.5)
        self.assertAlmostEqual(result.loc[0, "feature_probability_expected_sell_through_pct"], 80.0 / 120.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_excess_capital_at_risk"], 100.0)
        self.assertAlmostEqual(result.loc[0, "feature_probability_allocation_discipline_score"], 0.27)
        self.assertAlmostEqual(result.loc[0, "feature_allocation_vs_uplift_supported_units_ratio"], 2.0)
        self.assertAlmostEqual(result.loc[0, "feature_allocated_units_minus_uplift_supported_units"], 60.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_supported_excess_units"], 45.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_supported_excess_units_pct"], 45.0 / 75.0)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_supported_sell_through_pct"], 0.5)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_supported_excess_capital_at_risk"], 112.5)
        self.assertAlmostEqual(result.loc[0, "feature_uplift_allocation_discipline_score"], 0.27)
        self.assertAlmostEqual(result.loc[1, "feature_probability_expected_excess_units"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_probability_expected_sell_through_pct"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_uplift_supported_excess_units"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_uplift_supported_sell_through_pct"], 1.0)
        legacy_support_columns = [
            "feature_allocation_vs_probability_expected_units_ratio",
            "feature_allocated_units_minus_probability_expected_units",
            "feature_probability_expected_excess_units",
            "feature_probability_expected_excess_units_pct",
            "feature_probability_expected_sell_through_pct",
            "feature_probability_excess_capital_at_risk",
            "feature_probability_allocation_discipline_score",
            "feature_allocation_vs_uplift_supported_units_ratio",
            "feature_allocated_units_minus_uplift_supported_units",
            "feature_uplift_supported_excess_units",
            "feature_uplift_supported_excess_units_pct",
            "feature_uplift_supported_sell_through_pct",
            "feature_uplift_supported_excess_capital_at_risk",
            "feature_uplift_allocation_discipline_score",
            "feature_allocation_vs_baseline_gap_units",
            "feature_allocation_vs_uplift_supported_gap_units",
            "feature_allocation_vs_supported_total_gap_units",
            "feature_supported_sell_through_score",
            "feature_discount_evidence_strength_score",
            "feature_allocation_risk_over_uplift_score",
            "feature_launch_stock_support_score",
            "feature_total_window_pressure_vs_launch_support_conflict_score",
        ]
        self.assertTrue(result.loc[2, legacy_support_columns].isna().all())

    def test_allocation_discipline_uses_inventory_fallback_and_allows_legitimate_nulls(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_expected_baseline_units_promo_window": [0.933333, 0.933333],
                "feature_expected_incremental_uplift_units_same_discount": [14.939683, 0.0],
                "feature_probability_expected_units_consensus": [15.873016, 0.933333],
                "feature_probability_model_use_flag": [1.0, 0.0],
                "feature_same_discount_history_available_flag": [1.0, 0.0],
                "feature_same_discount_prior_event_count": [2.0, 0.0],
                "feature_uplift_confidence_score": [0.527186, 0.0],
                "feature_discount_elasticity_confidence_score": [0.0, 0.0],
                "feature_probability_demand_confidence_score": [0.5, 0.0],
                "feature_probability_uplift_supported_units": [14.939683, 0.0],
                "feature_probability_uplift_upper_units": [14.939683, 0.0],
                "feature_expected_total_units_from_baseline_plus_uplift": [15.873016, 0.933333],
                "feature_expected_total_units_first_7_days": [5.0, 0.25],
                "total_stock_available": [25.0, 25.0],
                "current_soh": [25.0, 25.0],
                "qty_on_order": [0.0, 0.0],
                "feature_pre_promo_baseline_daily_units": [0.0666667, 0.0666667],
                "as_of_date": ["2026-05-01", "2026-05-01"],
                "promotion_start_date_date": ["2026-05-07", "2026-05-07"],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        self.assertNotIn("stock_basis_units", frame.columns)
        self.assertFalse(pd.isna(result.loc[0, "feature_uplift_allocation_discipline_score"]))
        self.assertAlmostEqual(
            float(result.loc[0, "feature_uplift_allocation_discipline_score"]),
            round(((25.0 - (0.933333 + 14.939683)) / 25.0) * 0.527186, 6),
            places=5,
        )
        self.assertTrue(pd.isna(result.loc[1, "feature_uplift_allocation_discipline_score"]))

    def test_allocation_discipline_features_are_registered_model_use_outputs(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertTrue(set(ALLOCATION_DISCIPLINE_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(ALLOCATION_DISCIPLINE_FEATURE_COLUMNS).issubset(default_model_use_columns))
        self.assertIn("feature_probability_expected_sell_through_pct", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_probability_allocation_discipline_score", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_uplift_supported_sell_through_pct", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_uplift_allocation_discipline_score", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_stock_below_trust_floor_flag", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_trust_floor_missed_demand_risk_score", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_expected_bill_cycle_capital_drag_ratio", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_speculative_above_trust_floor_risk_flag", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_inventory_sufficiency_flag", BOUNDED_ZERO_ONE_COLUMNS)
        self.assertIn("feature_weak_promo_low_value_flag", BOUNDED_ZERO_ONE_COLUMNS)

    def test_allocation_discipline_derives_inventory_cover_and_low_value_flags(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [10.0, 10.0],
                "effective_cost_per_unit": [2.0, 2.0],
                "feature_capital_at_risk": [20.0, 20.0],
                "feature_expected_baseline_units_promo_window": [2.5, 5.0],
                "feature_expected_total_units_from_baseline_plus_uplift": [3.0, 12.0],
                "feature_expected_incremental_uplift_units_same_discount": [0.5, 6.0],
                "feature_expected_incremental_uplift_units_first_7_days": [0.25, 3.0],
                "feature_probability_expected_units_consensus": [3.0, 12.0],
                "feature_probability_model_use_flag": [1.0, 1.0],
                "feature_probability_demand_confidence_score": [0.8, 0.8],
                "feature_probability_uplift_supported_units": [0.5, 6.0],
                "feature_probability_uplift_upper_units": [1.0, 7.0],
                "feature_probability_uplift_confidence": [0.8, 0.8],
                "feature_uplift_confidence_score": [0.8, 0.8],
                "feature_discount_elasticity_confidence_score": [0.8, 0.8],
                "feature_same_discount_history_available_flag": [1.0, 1.0],
                "feature_same_discount_prior_event_count": [3.0, 3.0],
                "feature_total_window_pressure_vs_launch_support_conflict_score": [0.1, 0.1],
                "feature_expected_total_units_first_7_days": [1.0, 6.0],
                "current_soh": [8.0, 2.0],
                "qty_on_order": [4.0, 0.0],
                "feature_pre_promo_baseline_daily_units": [1.0, 1.0],
                "as_of_date": ["2024-05-29", "2024-05-29"],
                "promotion_start_date_date": ["2024-06-02", "2024-06-02"],
                "promo_gm_unit": [0.8, 3.0],
                "feature_historical_comparable_promo_event_count": [3.0, 3.0],
                "feature_historical_zero_sale_after_buy_rate": [0.5, 0.0],
                "feature_same_discount_success_rate_56d": [0.2, 1.0],
                "feature_historical_trapped_capital_rate": [0.7, 0.1],
                "feature_historical_sell_through_on_accepted_qty": [0.3, 0.9],
                "feature_historical_overforecast_bias": [0.6, 0.0],
                "feature_historical_allocation_efficiency_rate": [0.4, 0.9],
                "feature_historical_overallocation_above_floor_rate": [0.6, 0.0],
                "feature_historical_under_floor_missed_demand_rate": [0.0, 0.8],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        self.assertAlmostEqual(result.loc[0, "feature_pre_promo_cover_ratio"], 8.0 / 3.0)
        self.assertEqual(result.loc[0, "feature_inventory_sufficiency_flag"], 1.0)
        self.assertEqual(result.loc[0, "feature_stock_below_trust_floor_flag"], 0.0)
        self.assertAlmostEqual(result.loc[0, "feature_units_needed_for_trust_floor"], 0.0)
        self.assertAlmostEqual(result.loc[0, "feature_units_needed_for_high_demand_cover"], 0.0)
        self.assertAlmostEqual(result.loc[0, "feature_units_above_trust_floor"], 6.0)
        self.assertAlmostEqual(result.loc[0, "feature_units_above_trust_target"], 3.0)
        self.assertAlmostEqual(result.loc[0, "feature_expected_residual_stock_units"], 5.0)
        self.assertAlmostEqual(result.loc[0, "feature_expected_leftover_above_trust_floor_units"], 3.0)
        self.assertAlmostEqual(result.loc[0, "feature_expected_bill_cycle_capital_drag_dollars"], 6.0)
        self.assertAlmostEqual(result.loc[0, "feature_capital_tied_above_trust_target"], 6.0)
        self.assertAlmostEqual(result.loc[0, "feature_expected_bill_cycle_capital_drag_ratio"], 0.3)
        self.assertEqual(result.loc[0, "feature_speculative_above_trust_floor_risk_flag"], 1.0)
        self.assertAlmostEqual(result.loc[0, "feature_capital_at_risk_per_expected_unit"], 20.0 / 3.0)
        self.assertAlmostEqual(result.loc[0, "feature_gross_profit_per_incremental_unit_expected"], 0.8)
        self.assertAlmostEqual(result.loc[0, "feature_expected_gp_on_trust_floor_units"], 1.6)
        self.assertAlmostEqual(result.loc[0, "feature_expected_gp_on_speculative_units"], 0.8)
        self.assertAlmostEqual(result.loc[0, "feature_expected_gp_per_capital_committed"], 0.02)
        self.assertAlmostEqual(result.loc[0, "feature_risk_adjusted_value_of_speculative_units"], -5.2)
        self.assertEqual(result.loc[0, "feature_weak_promo_low_value_flag"], 1.0)

        self.assertAlmostEqual(result.loc[1, "feature_pre_promo_cover_ratio"], 0.0)
        self.assertEqual(result.loc[1, "feature_inventory_sufficiency_flag"], 0.0)
        self.assertEqual(result.loc[1, "feature_stock_below_trust_floor_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_units_needed_for_trust_floor"], 14.0)
        self.assertGreater(result.loc[1, "feature_trust_floor_missed_demand_risk_score"], 0.5)
        self.assertGreater(result.loc[1, "feature_expected_lost_units_below_trust_floor"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_units_above_trust_target"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_expected_gp_on_trust_floor_units"], 6.0)
        self.assertAlmostEqual(result.loc[1, "feature_expected_gp_on_speculative_units"], 0.0)
        self.assertEqual(result.loc[1, "feature_speculative_above_trust_floor_risk_flag"], 0.0)
        self.assertEqual(result.loc[1, "feature_weak_promo_low_value_flag"], 0.0)

    def test_allocation_discipline_missing_economics_remain_unavailable(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [20.0],
                "feature_capital_at_risk": [pd.NA],
                "feature_expected_baseline_units_promo_window": [2.0],
                "feature_expected_total_units_from_baseline_plus_uplift": [4.0],
                "feature_expected_incremental_uplift_units_same_discount": [1.0],
                "feature_probability_expected_units_consensus": [4.0],
                "feature_probability_model_use_flag": [1.0],
                "feature_probability_demand_confidence_score": [0.8],
                "feature_probability_uplift_supported_units": [1.0],
                "feature_probability_uplift_upper_units": [1.5],
                "feature_probability_uplift_confidence": [0.8],
                "feature_uplift_confidence_score": [0.8],
                "feature_discount_elasticity_confidence_score": [0.8],
                "feature_same_discount_history_available_flag": [1.0],
                "feature_same_discount_prior_event_count": [3.0],
                "feature_total_window_pressure_vs_launch_support_conflict_score": [0.1],
                "feature_expected_total_units_first_7_days": [2.0],
                "current_soh": [20.0],
                "qty_on_order": [0.0],
                "feature_pre_promo_baseline_daily_units": [0.0],
                "as_of_date": ["2024-05-29"],
                "promotion_start_date_date": ["2024-06-02"],
                "feature_historical_comparable_promo_event_count": [3.0],
                "feature_historical_trapped_capital_rate": [0.7],
                "feature_historical_sell_through_on_accepted_qty": [0.3],
                "feature_historical_allocation_efficiency_rate": [0.4],
                "feature_historical_overallocation_above_floor_rate": [0.6],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        unavailable_columns = [
            "feature_probability_excess_capital_at_risk",
            "feature_uplift_supported_excess_capital_at_risk",
            "feature_expected_bill_cycle_capital_drag_dollars",
            "feature_capital_tied_above_trust_target",
            "feature_expected_bill_cycle_capital_drag_ratio",
            "feature_expected_gp_on_trust_floor_units",
            "feature_expected_gp_on_speculative_units",
            "feature_expected_gp_per_capital_committed",
            "feature_risk_adjusted_value_of_speculative_units",
            "feature_speculative_above_trust_floor_risk_flag",
            "feature_capital_at_risk_per_expected_unit",
            "feature_gross_profit_per_incremental_unit_expected",
            "feature_weak_promo_low_value_flag",
        ]
        self.assertTrue(result.loc[0, unavailable_columns].isna().all())
        self.assertAlmostEqual(result.loc[0, "feature_pre_promo_cover_ratio"], 5.0)
        self.assertEqual(result.loc[0, "feature_inventory_sufficiency_flag"], 1.0)

    def test_allocation_discipline_trust_floor_boundary_is_exact(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [2.0, 1.99],
                "effective_cost_per_unit": [2.0, 2.0],
                "feature_capital_at_risk": [4.0, 3.98],
                "feature_expected_baseline_units_promo_window": [1.0, 1.0],
                "feature_expected_total_units_from_baseline_plus_uplift": [1.0, 1.0],
                "feature_expected_incremental_uplift_units_same_discount": [0.25, 0.25],
                "feature_probability_expected_units_consensus": [1.0, 1.0],
                "feature_probability_model_use_flag": [1.0, 1.0],
                "feature_probability_demand_confidence_score": [0.8, 0.8],
                "feature_probability_uplift_supported_units": [0.25, 0.25],
                "feature_probability_uplift_upper_units": [0.50, 0.50],
                "feature_probability_uplift_confidence": [0.8, 0.8],
                "feature_uplift_confidence_score": [0.8, 0.8],
                "feature_discount_elasticity_confidence_score": [0.8, 0.8],
                "feature_same_discount_history_available_flag": [1.0, 1.0],
                "feature_same_discount_prior_event_count": [3.0, 3.0],
                "feature_total_window_pressure_vs_launch_support_conflict_score": [0.1, 0.1],
                "feature_expected_total_units_first_7_days": [0.5, 0.5],
                "current_soh": [2.0, 1.99],
                "qty_on_order": [0.0, 0.0],
                "feature_pre_promo_baseline_daily_units": [0.0, 0.0],
                "as_of_date": ["2024-05-29", "2024-05-29"],
                "promotion_start_date_date": ["2024-06-02", "2024-06-02"],
                "promo_gm_unit": [0.5, 0.5],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        self.assertEqual(result.loc[0, "feature_stock_below_trust_floor_flag"], 0.0)
        self.assertEqual(result.loc[0, "feature_projected_stock_gap_to_trust_floor_units"], 0.0)
        self.assertEqual(result.loc[0, "feature_trust_floor_missed_demand_risk_score"], 0.0)
        self.assertEqual(result.loc[1, "feature_stock_below_trust_floor_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_projected_stock_gap_to_trust_floor_units"], 0.01)
        self.assertGreater(result.loc[1, "feature_trust_floor_missed_demand_risk_score"], 0.0)

    def test_allocation_discipline_low_value_stays_off_without_speculative_above_floor(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [5.0],
                "effective_cost_per_unit": [2.0],
                "feature_capital_at_risk": [10.0],
                "feature_expected_baseline_units_promo_window": [3.5],
                "feature_expected_total_units_from_baseline_plus_uplift": [4.0],
                "feature_expected_incremental_uplift_units_same_discount": [0.5],
                "feature_probability_expected_units_consensus": [4.0],
                "feature_probability_model_use_flag": [1.0],
                "feature_probability_demand_confidence_score": [0.8],
                "feature_probability_uplift_supported_units": [0.5],
                "feature_probability_uplift_upper_units": [1.0],
                "feature_probability_uplift_confidence": [0.8],
                "feature_uplift_confidence_score": [0.8],
                "feature_discount_elasticity_confidence_score": [0.8],
                "feature_same_discount_history_available_flag": [1.0],
                "feature_same_discount_prior_event_count": [3.0],
                "feature_total_window_pressure_vs_launch_support_conflict_score": [0.1],
                "feature_expected_total_units_first_7_days": [2.0],
                "current_soh": [5.0],
                "qty_on_order": [0.0],
                "feature_pre_promo_baseline_daily_units": [0.0],
                "as_of_date": ["2024-05-29"],
                "promotion_start_date_date": ["2024-06-02"],
                "promo_gm_unit": [0.0],
                "feature_historical_comparable_promo_event_count": [3.0],
                "feature_historical_zero_sale_after_buy_rate": [0.5],
                "feature_same_discount_success_rate_56d": [0.2],
                "feature_historical_trapped_capital_rate": [0.7],
                "feature_historical_sell_through_on_accepted_qty": [0.3],
                "feature_historical_overforecast_bias": [0.6],
                "feature_historical_allocation_efficiency_rate": [0.4],
                "feature_historical_overallocation_above_floor_rate": [0.7],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        self.assertAlmostEqual(result.loc[0, "feature_units_above_trust_floor"], 3.0)
        self.assertAlmostEqual(result.loc[0, "feature_expected_leftover_above_trust_floor_units"], 0.0)
        self.assertEqual(result.loc[0, "feature_speculative_above_trust_floor_risk_flag"], 0.0)
        self.assertEqual(result.loc[0, "feature_weak_promo_low_value_flag"], 0.0)

    def test_allocation_discipline_flags_only_material_speculative_above_floor_rows(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [5.0, 10.0],
                "effective_cost_per_unit": [2.0, 2.0],
                "feature_capital_at_risk": [10.0, 20.0],
                "feature_expected_baseline_units_promo_window": [3.0, 2.0],
                "feature_expected_total_units_from_baseline_plus_uplift": [4.0, 3.0],
                "feature_expected_incremental_uplift_units_same_discount": [1.0, 1.0],
                "feature_probability_expected_units_consensus": [4.0, 3.0],
                "feature_probability_model_use_flag": [1.0, 1.0],
                "feature_probability_demand_confidence_score": [0.8, 0.8],
                "feature_probability_uplift_supported_units": [1.0, 1.0],
                "feature_probability_uplift_upper_units": [1.5, 1.5],
                "feature_probability_uplift_confidence": [0.8, 0.8],
                "feature_uplift_confidence_score": [0.8, 0.8],
                "feature_discount_elasticity_confidence_score": [0.8, 0.8],
                "feature_same_discount_history_available_flag": [1.0, 1.0],
                "feature_same_discount_prior_event_count": [3.0, 3.0],
                "feature_total_window_pressure_vs_launch_support_conflict_score": [0.1, 0.1],
                "feature_expected_total_units_first_7_days": [2.0, 1.5],
                "current_soh": [5.0, 10.0],
                "qty_on_order": [0.0, 0.0],
                "feature_pre_promo_baseline_daily_units": [0.0, 0.0],
                "as_of_date": ["2024-05-29", "2024-05-29"],
                "promotion_start_date_date": ["2024-06-02", "2024-06-02"],
                "promo_gm_unit": [0.5, 0.5],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        self.assertEqual(result.loc[0, "feature_stock_below_trust_floor_flag"], 0.0)
        self.assertAlmostEqual(result.loc[0, "feature_expected_leftover_above_trust_floor_units"], 0.0)
        self.assertEqual(result.loc[0, "feature_speculative_above_trust_floor_risk_flag"], 0.0)
        self.assertEqual(result.loc[1, "feature_stock_below_trust_floor_flag"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_expected_leftover_above_trust_floor_units"], 5.0)
        self.assertEqual(result.loc[1, "feature_speculative_above_trust_floor_risk_flag"], 1.0)

    def test_allocation_discipline_splits_high_demand_cover_from_trust_floor_need(self) -> None:
        frame = pd.DataFrame(
            {
                "stock_basis_units": [1.0, 20.0],
                "effective_cost_per_unit": [2.0, 2.0],
                "feature_capital_at_risk": [2.0, 40.0],
                "feature_expected_baseline_units_promo_window": [12.0, 12.0],
                "feature_expected_total_units_from_baseline_plus_uplift": [12.0, 12.0],
                "feature_expected_incremental_uplift_units_same_discount": [1.0, 1.0],
                "feature_probability_expected_units_consensus": [12.0, 12.0],
                "feature_probability_model_use_flag": [1.0, 1.0],
                "feature_probability_demand_confidence_score": [0.8, 0.8],
                "feature_probability_uplift_supported_units": [1.0, 1.0],
                "feature_probability_uplift_upper_units": [1.5, 1.5],
                "feature_probability_uplift_confidence": [0.8, 0.8],
                "feature_uplift_confidence_score": [0.8, 0.8],
                "feature_discount_elasticity_confidence_score": [0.8, 0.8],
                "feature_same_discount_history_available_flag": [1.0, 1.0],
                "feature_same_discount_prior_event_count": [3.0, 3.0],
                "feature_total_window_pressure_vs_launch_support_conflict_score": [0.1, 0.1],
                "feature_expected_total_units_first_7_days": [6.0, 6.0],
                "feature_end_of_promo_target_units": [21.0, 21.0],
                "feature_high_base_demand_end_cover_flag": [1.0, 1.0],
                "current_soh": [1.0, 20.0],
                "qty_on_order": [0.0, 0.0],
                "feature_pre_promo_baseline_daily_units": [0.0, 0.0],
                "as_of_date": ["2024-05-29", "2024-05-29"],
                "promotion_start_date_date": ["2024-06-02", "2024-06-02"],
                "promo_gm_unit": [3.0, 3.0],
            }
        )

        result = apply_ft_allocation_discipline(frame)

        self.assertAlmostEqual(result.loc[0, "feature_units_needed_for_trust_floor"], 13.0)
        self.assertAlmostEqual(result.loc[0, "feature_units_needed_for_high_demand_cover"], 19.0)
        self.assertAlmostEqual(result.loc[0, "feature_units_above_trust_target"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_units_needed_for_trust_floor"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_units_needed_for_high_demand_cover"], 13.0)
        self.assertAlmostEqual(result.loc[1, "feature_units_above_trust_target"], 0.0)

    def test_allocation_aware_units_cap_is_one_way_and_evidence_gated(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_baseline_units_expected_promo_window": [20.0, 20.0, 20.0, 20.0],
                "feature_probability_expected_units_consensus": [60.0, 60.0, 60.0, 60.0],
                "feature_probability_uplift_supported_units": [30.0, 30.0, 30.0, 30.0],
                "feature_probability_uplift_upper_units": [40.0, 40.0, 40.0, 40.0],
                "feature_probability_tail_risk_consensus": [0.0, 0.0, 0.0, 0.0],
                "feature_probability_demand_confidence_score": [1.0, 1.0, 1.0, 1.0],
                "feature_probability_uplift_confidence": [1.0, 1.0, 1.0, 1.0],
                "feature_probability_allocation_discipline_score": [0.2, 0.1, 0.2, 0.2],
                "feature_uplift_allocation_discipline_score": [0.2, 0.1, 0.2, 0.2],
                "feature_probability_model_use_flag": [1.0, 1.0, 0.0, 1.0],
            }
        )
        raw_prediction = pd.Series([90.0, 90.0, 90.0, 50.0], index=frame.index)

        capped = compute_allocation_aware_cap_units(frame, raw_prediction)

        self.assertEqual(capped.tolist(), [60.0, 90.0, 90.0, 50.0])


if __name__ == "__main__":
    unittest.main()