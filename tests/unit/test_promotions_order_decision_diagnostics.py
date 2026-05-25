from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.model_input_quality import iter_default_model_use_feature_columns  # noqa: E402
from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (  # noqa: E402
    ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS,
    apply_ft_order_decision_diagnostics,
    build_live_order_decision_diagnostics,
    build_order_decision_bucket_frame,
)
from state.promotions.feature_engineering.registry import iter_registered_feature_modules  # noqa: E402


def _diagnostic_row(
    *,
    promotion_row_key: str,
    feature_same_discount_prior_event_count: float,
    feature_same_discount_history_available_flag: float,
    feature_discount_evidence_strength_score: float,
    feature_discount_elasticity_confidence_score: float,
    feature_discount_response_event_count: float,
    feature_discount_response_direction_consistent_flag: float,
    feature_discount_elasticity_abs: float,
    feature_uplift_confidence_score: float,
    feature_uplift_demand_support_flag: float,
    feature_non_promo_recent_acceleration_score: float,
    feature_non_promo_base_trend_30d_vs_56d: float,
    feature_non_promo_base_trend_30d_vs_84d: float,
    feature_non_promo_base_demand_growing_flag: float,
    feature_non_promo_history_available_flag: float,
    feature_non_promo_low_history_flag: float,
    feature_sparse_history_penalty: float,
    feature_total_window_pressure_vs_launch_support_conflict_score: float,
    feature_allocation_vs_supported_total_gap_units: float,
    feature_allocation_risk_over_uplift_score: float,
    feature_expected_baseline_units_promo_window: float,
    feature_expected_incremental_uplift_units_same_discount: float,
    feature_expected_total_units_from_baseline_plus_uplift: float,
    stock_basis_units: float,
    feature_probability_model_use_flag: float = 1.0,
) -> dict[str, object]:
    return {
        "promotion_row_key": promotion_row_key,
        "store_number": 1,
        "sku_number": 1001,
        "feature_same_discount_prior_event_count": feature_same_discount_prior_event_count,
        "feature_same_discount_history_available_flag": feature_same_discount_history_available_flag,
        "feature_discount_evidence_strength_score": feature_discount_evidence_strength_score,
        "feature_discount_elasticity_confidence_score": feature_discount_elasticity_confidence_score,
        "feature_discount_response_event_count": feature_discount_response_event_count,
        "feature_discount_response_direction_consistent_flag": feature_discount_response_direction_consistent_flag,
        "feature_discount_elasticity_abs": feature_discount_elasticity_abs,
        "feature_uplift_confidence_score": feature_uplift_confidence_score,
        "feature_uplift_demand_support_flag": feature_uplift_demand_support_flag,
        "feature_non_promo_recent_acceleration_score": feature_non_promo_recent_acceleration_score,
        "feature_non_promo_base_trend_30d_vs_56d": feature_non_promo_base_trend_30d_vs_56d,
        "feature_non_promo_base_trend_30d_vs_84d": feature_non_promo_base_trend_30d_vs_84d,
        "feature_non_promo_base_demand_growing_flag": feature_non_promo_base_demand_growing_flag,
        "feature_non_promo_history_available_flag": feature_non_promo_history_available_flag,
        "feature_non_promo_low_history_flag": feature_non_promo_low_history_flag,
        "feature_sparse_history_penalty": feature_sparse_history_penalty,
        "feature_total_window_pressure_vs_launch_support_conflict_score": feature_total_window_pressure_vs_launch_support_conflict_score,
        "feature_allocation_vs_supported_total_gap_units": feature_allocation_vs_supported_total_gap_units,
        "feature_allocation_risk_over_uplift_score": feature_allocation_risk_over_uplift_score,
        "feature_expected_baseline_units_promo_window": feature_expected_baseline_units_promo_window,
        "feature_expected_incremental_uplift_units_same_discount": feature_expected_incremental_uplift_units_same_discount,
        "feature_expected_total_units_from_baseline_plus_uplift": feature_expected_total_units_from_baseline_plus_uplift,
        "stock_basis_units": stock_basis_units,
        "feature_probability_model_use_flag": feature_probability_model_use_flag,
    }


class PromotionOrderDecisionDiagnosticsTests(unittest.TestCase):
    def test_order_decision_diagnostics_bucket_and_flag_high_risk_rows(self) -> None:
        frame = pd.DataFrame(
            [
                _diagnostic_row(
                    promotion_row_key="strong",
                    feature_same_discount_prior_event_count=5.0,
                    feature_same_discount_history_available_flag=1.0,
                    feature_discount_evidence_strength_score=0.85,
                    feature_discount_elasticity_confidence_score=0.75,
                    feature_discount_response_event_count=5.0,
                    feature_discount_response_direction_consistent_flag=1.0,
                    feature_discount_elasticity_abs=0.30,
                    feature_uplift_confidence_score=0.80,
                    feature_uplift_demand_support_flag=1.0,
                    feature_non_promo_recent_acceleration_score=0.10,
                    feature_non_promo_base_trend_30d_vs_56d=0.08,
                    feature_non_promo_base_trend_30d_vs_84d=0.09,
                    feature_non_promo_base_demand_growing_flag=1.0,
                    feature_non_promo_history_available_flag=1.0,
                    feature_non_promo_low_history_flag=0.0,
                    feature_sparse_history_penalty=0.10,
                    feature_total_window_pressure_vs_launch_support_conflict_score=0.10,
                    feature_allocation_vs_supported_total_gap_units=8.0,
                    feature_allocation_risk_over_uplift_score=0.20,
                    feature_expected_baseline_units_promo_window=30.0,
                    feature_expected_incremental_uplift_units_same_discount=15.0,
                    feature_expected_total_units_from_baseline_plus_uplift=45.0,
                    stock_basis_units=50.0,
                ),
                _diagnostic_row(
                    promotion_row_key="weak",
                    feature_same_discount_prior_event_count=0.0,
                    feature_same_discount_history_available_flag=0.0,
                    feature_discount_evidence_strength_score=0.20,
                    feature_discount_elasticity_confidence_score=0.10,
                    feature_discount_response_event_count=1.0,
                    feature_discount_response_direction_consistent_flag=0.0,
                    feature_discount_elasticity_abs=0.05,
                    feature_uplift_confidence_score=0.20,
                    feature_uplift_demand_support_flag=0.0,
                    feature_non_promo_recent_acceleration_score=-0.20,
                    feature_non_promo_base_trend_30d_vs_56d=-0.15,
                    feature_non_promo_base_trend_30d_vs_84d=-0.10,
                    feature_non_promo_base_demand_growing_flag=0.0,
                    feature_non_promo_history_available_flag=1.0,
                    feature_non_promo_low_history_flag=1.0,
                    feature_sparse_history_penalty=0.80,
                    feature_total_window_pressure_vs_launch_support_conflict_score=0.80,
                    feature_allocation_vs_supported_total_gap_units=40.0,
                    feature_allocation_risk_over_uplift_score=0.90,
                    feature_expected_baseline_units_promo_window=20.0,
                    feature_expected_incremental_uplift_units_same_discount=0.0,
                    feature_expected_total_units_from_baseline_plus_uplift=20.0,
                    stock_basis_units=80.0,
                ),
            ]
        )

        result = apply_ft_order_decision_diagnostics(frame)
        buckets = build_order_decision_bucket_frame(result)

        self.assertEqual(
            list(ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS),
            [column_name for column_name in ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertAlmostEqual(result.loc[0, "feature_order_risk_reason_multi_driver_count"], 0.0)
        self.assertAlmostEqual(result.loc[1, "feature_order_risk_reason_same_discount_weak_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_order_risk_reason_elasticity_weak_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_order_risk_reason_uplift_weak_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_order_risk_reason_base_trend_falling_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_order_risk_reason_launch_total_conflict_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_order_risk_reason_stock_vs_supported_gap_high_flag"], 1.0)
        self.assertAlmostEqual(result.loc[1, "feature_order_risk_reason_sparse_history_flag"], 1.0)
        self.assertGreaterEqual(result.loc[1, "feature_order_risk_reason_multi_driver_count"], 7.0)
        self.assertGreater(result.loc[1, "feature_order_risk_overallocation_score"], 0.70)
        self.assertLess(result.loc[1, "feature_order_support_strength_score"], 0.30)
        self.assertGreater(result.loc[1, "feature_order_review_priority_score"], 0.75)
        self.assertEqual(buckets.loc[0, "same_discount_history_bucket"], "strong_history")
        self.assertEqual(buckets.loc[1, "same_discount_history_bucket"], "no_history")
        self.assertEqual(buckets.loc[0, "elasticity_confidence_bucket"], "high_confidence")
        self.assertEqual(buckets.loc[1, "elasticity_confidence_bucket"], "low_confidence")
        self.assertEqual(buckets.loc[0, "base_demand_growth_bucket"], "growing_base")
        self.assertEqual(buckets.loc[1, "base_demand_growth_bucket"], "falling_base")
        self.assertEqual(buckets.loc[0, "window_conflict_bucket"], "no_conflict")
        self.assertEqual(buckets.loc[1, "window_conflict_bucket"], "high_conflict")

    def test_live_order_decision_diagnostics_stay_stable_without_outcome_columns(self) -> None:
        frame = pd.DataFrame(
            [
                _diagnostic_row(
                    promotion_row_key="fallback",
                    feature_same_discount_prior_event_count=0.0,
                    feature_same_discount_history_available_flag=0.0,
                    feature_discount_evidence_strength_score=0.0,
                    feature_discount_elasticity_confidence_score=0.0,
                    feature_discount_response_event_count=0.0,
                    feature_discount_response_direction_consistent_flag=0.0,
                    feature_discount_elasticity_abs=0.0,
                    feature_uplift_confidence_score=0.0,
                    feature_uplift_demand_support_flag=0.0,
                    feature_non_promo_recent_acceleration_score=0.0,
                    feature_non_promo_base_trend_30d_vs_56d=0.0,
                    feature_non_promo_base_trend_30d_vs_84d=0.0,
                    feature_non_promo_base_demand_growing_flag=0.0,
                    feature_non_promo_history_available_flag=0.0,
                    feature_non_promo_low_history_flag=1.0,
                    feature_sparse_history_penalty=1.0,
                    feature_total_window_pressure_vs_launch_support_conflict_score=0.20,
                    feature_allocation_vs_supported_total_gap_units=0.0,
                    feature_allocation_risk_over_uplift_score=0.10,
                    feature_expected_baseline_units_promo_window=0.0,
                    feature_expected_incremental_uplift_units_same_discount=0.0,
                    feature_expected_total_units_from_baseline_plus_uplift=0.0,
                    stock_basis_units=0.0,
                    feature_probability_model_use_flag=0.0,
                )
            ]
        )

        diagnostics = build_live_order_decision_diagnostics(
            frame,
            raw_predicted_units=pd.Series([5.0], index=frame.index),
            predicted_units=pd.Series([5.0], index=frame.index),
        )

        self.assertEqual(diagnostics.loc[0, "order_sizing_driver"], "fallback")
        self.assertEqual(diagnostics.loc[0, "order_cap_reason"], "fallback")
        self.assertAlmostEqual(diagnostics.loc[0, "weak_fallback_logic_flag"], 1.0)
        self.assertAlmostEqual(diagnostics.loc[0, "evidence_same_discount_present_flag"], 0.0)
        self.assertAlmostEqual(diagnostics.loc[0, "evidence_usable_elasticity_flag"], 0.0)
        self.assertAlmostEqual(diagnostics.loc[0, "evidence_strong_uplift_support_flag"], 0.0)
        self.assertGreaterEqual(diagnostics.loc[0, "feature_order_review_priority_score"], 0.0)
        self.assertLessEqual(diagnostics.loc[0, "feature_order_review_priority_score"], 1.0)
        self.assertFalse(any(column_name.startswith("target_") for column_name in diagnostics.columns))

    def test_order_decision_diagnostics_are_registered_but_review_only(self) -> None:
        registered_columns = {
            column_name
            for definition in iter_registered_feature_modules()
            for column_name in definition.output_columns
        }
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertEqual(
            len(ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS),
            len(set(ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS)),
        )
        self.assertTrue(set(ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS).issubset(registered_columns))
        self.assertTrue(set(ORDER_DECISION_DIAGNOSTICS_FEATURE_COLUMNS).isdisjoint(default_model_use_columns))


if __name__ == "__main__":
    unittest.main()