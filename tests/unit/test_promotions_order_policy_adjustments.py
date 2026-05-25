from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.order_policy_adjustments import (  # noqa: E402
    build_order_policy_adjustments,
    build_order_policy_major_bucket_frame,
)
from state.promotions.feature_engineering.demand.ft_order_decision_diagnostics import (  # noqa: E402
    build_live_order_decision_diagnostics,
)


def _policy_row(**overrides: object) -> dict[str, object]:
    row = {
        "promotion_row_key": "row-1",
        "store_number": 1,
        "sku_number": 1001,
        "live_promo_window_days": 14.0,
        "feature_same_discount_prior_event_count": 5.0,
        "feature_same_discount_history_available_flag": 1.0,
        "feature_discount_evidence_strength_score": 0.85,
        "feature_discount_elasticity_confidence_score": 0.85,
        "feature_discount_response_event_count": 5.0,
        "feature_discount_response_direction_consistent_flag": 1.0,
        "feature_discount_elasticity_abs": 0.30,
        "feature_uplift_confidence_score": 0.80,
        "feature_uplift_demand_support_flag": 1.0,
        "feature_non_promo_recent_acceleration_score": 0.08,
        "feature_non_promo_base_trend_30d_vs_56d": 0.06,
        "feature_non_promo_base_trend_30d_vs_84d": 0.05,
        "feature_non_promo_base_demand_growing_flag": 1.0,
        "feature_non_promo_history_available_flag": 1.0,
        "feature_non_promo_low_history_flag": 0.0,
        "feature_sparse_history_penalty": 0.10,
        "feature_total_window_pressure_vs_launch_support_conflict_score": 0.10,
        "feature_allocation_vs_supported_total_gap_units": 4.0,
        "feature_allocation_risk_over_uplift_score": 0.10,
        "feature_expected_baseline_units_promo_window": 20.0,
        "feature_expected_baseline_units_first_7_days": 10.0,
        "feature_expected_incremental_uplift_units_same_discount": 20.0,
        "feature_expected_incremental_uplift_units_first_7_days": 10.0,
        "feature_expected_total_units_from_baseline_plus_uplift": 40.0,
        "effective_cost_per_unit": 2.0,
        "stock_basis_units": 60.0,
        "feature_probability_model_use_flag": 1.0,
    }
    row.update(overrides)
    return row


def _policy_outputs(frame: pd.DataFrame, *, raw_units: float, calibrated_units: float) -> pd.DataFrame:
    diagnostics = build_live_order_decision_diagnostics(
        frame,
        raw_predicted_units=pd.Series([raw_units], index=frame.index),
        predicted_units=pd.Series([calibrated_units], index=frame.index),
    )
    return build_order_policy_adjustments(
        frame,
        raw_predicted_units=pd.Series([raw_units], index=frame.index),
        calibrated_predicted_units=pd.Series([calibrated_units], index=frame.index),
        diagnostics_frame=diagnostics,
    )


class PromotionOrderPolicyAdjustmentTests(unittest.TestCase):
    def test_weak_same_discount_and_uplift_caps_harder_toward_baseline(self) -> None:
        frame = pd.DataFrame(
            [
                _policy_row(
                    feature_same_discount_prior_event_count=0.0,
                    feature_same_discount_history_available_flag=0.0,
                    feature_discount_evidence_strength_score=0.20,
                    feature_uplift_confidence_score=0.20,
                    feature_uplift_demand_support_flag=0.0,
                )
            ]
        )

        outputs = _policy_outputs(frame, raw_units=56.0, calibrated_units=52.0)

        self.assertEqual(outputs.loc[0, "policy_adjustment_reason"], "weak_same_discount_and_uplift_cap")
        self.assertAlmostEqual(outputs.loc[0, "policy_adjustment_strength"], 0.60)
        self.assertAlmostEqual(outputs.loc[0, "review_override_flag"], 0.0)
        self.assertAlmostEqual(outputs.loc[0, "adjusted_order_cap_units"], 25.0)
        self.assertGreater(outputs.loc[0, "policy_units_removed"], 0.0)

    def test_weak_elasticity_reduces_discount_led_uplift_without_forcing_review(self) -> None:
        frame = pd.DataFrame(
            [
                _policy_row(
                    feature_discount_elasticity_confidence_score=0.10,
                    feature_discount_response_event_count=1.0,
                )
            ]
        )

        outputs = _policy_outputs(frame, raw_units=55.0, calibrated_units=50.0)

        self.assertEqual(outputs.loc[0, "policy_adjustment_reason"], "weak_elasticity_uplift_restraint")
        self.assertAlmostEqual(outputs.loc[0, "policy_adjustment_strength"], 0.35)
        self.assertAlmostEqual(outputs.loc[0, "review_override_flag"], 0.0)
        self.assertAlmostEqual(outputs.loc[0, "adjusted_order_cap_units"], 32.0)

    def test_falling_base_and_launch_conflict_forces_review(self) -> None:
        frame = pd.DataFrame(
            [
                _policy_row(
                    feature_non_promo_recent_acceleration_score=-0.20,
                    feature_non_promo_base_trend_30d_vs_56d=-0.15,
                    feature_non_promo_base_trend_30d_vs_84d=-0.10,
                    feature_non_promo_base_demand_growing_flag=0.0,
                    feature_total_window_pressure_vs_launch_support_conflict_score=0.80,
                )
            ]
        )

        outputs = _policy_outputs(frame, raw_units=48.0, calibrated_units=42.0)

        self.assertEqual(outputs.loc[0, "policy_adjustment_reason"], "falling_base_launch_conflict_review")
        self.assertAlmostEqual(outputs.loc[0, "review_override_flag"], 1.0)
        self.assertEqual(outputs.loc[0, "review_override_reason"], "policy_falling_base_launch_total_conflict")
        self.assertLessEqual(outputs.loc[0, "adjusted_launch_units"], 10.0)

    def test_stock_gap_high_forces_review_and_caps_units(self) -> None:
        frame = pd.DataFrame(
            [
                _policy_row(
                    feature_allocation_vs_supported_total_gap_units=30.0,
                    feature_allocation_risk_over_uplift_score=0.90,
                )
            ]
        )

        outputs = _policy_outputs(frame, raw_units=54.0, calibrated_units=50.0)

        self.assertEqual(outputs.loc[0, "policy_adjustment_reason"], "stock_gap_high_review_cap")
        self.assertAlmostEqual(outputs.loc[0, "review_override_flag"], 1.0)
        self.assertEqual(outputs.loc[0, "review_override_reason"], "policy_stock_gap_high")
        self.assertLess(outputs.loc[0, "adjusted_order_cap_units"], 50.0)

    def test_sparse_history_multi_driver_uses_baseline_only_and_sets_major_bucket(self) -> None:
        frame = pd.DataFrame(
            [
                _policy_row(
                    feature_same_discount_prior_event_count=0.0,
                    feature_same_discount_history_available_flag=0.0,
                    feature_discount_evidence_strength_score=0.20,
                    feature_discount_elasticity_confidence_score=0.10,
                    feature_discount_response_event_count=0.0,
                    feature_discount_response_direction_consistent_flag=0.0,
                    feature_uplift_confidence_score=0.10,
                    feature_uplift_demand_support_flag=0.0,
                    feature_non_promo_base_demand_growing_flag=0.0,
                    feature_non_promo_low_history_flag=1.0,
                    feature_sparse_history_penalty=0.90,
                    feature_total_window_pressure_vs_launch_support_conflict_score=0.70,
                    feature_allocation_vs_supported_total_gap_units=35.0,
                    feature_allocation_risk_over_uplift_score=0.90,
                )
            ]
        )
        diagnostics = build_live_order_decision_diagnostics(
            frame,
            raw_predicted_units=pd.Series([60.0], index=frame.index),
            predicted_units=pd.Series([50.0], index=frame.index),
        )

        outputs = build_order_policy_adjustments(
            frame,
            raw_predicted_units=pd.Series([60.0], index=frame.index),
            calibrated_predicted_units=pd.Series([50.0], index=frame.index),
            diagnostics_frame=diagnostics,
        )
        major_buckets = build_order_policy_major_bucket_frame(diagnostics)

        self.assertEqual(outputs.loc[0, "policy_adjustment_reason"], "sparse_history_multi_driver_baseline_only")
        self.assertAlmostEqual(outputs.loc[0, "policy_adjustment_strength"], 0.90)
        self.assertAlmostEqual(outputs.loc[0, "review_override_flag"], 1.0)
        self.assertAlmostEqual(outputs.loc[0, "adjusted_order_cap_units"], 20.0)
        self.assertAlmostEqual(major_buckets.loc[0, "sparse_history_multi_driver"], 1.0)

    def test_strong_evidence_rows_take_no_policy_action(self) -> None:
        frame = pd.DataFrame([_policy_row()])

        outputs = _policy_outputs(frame, raw_units=44.0, calibrated_units=40.0)

        self.assertEqual(outputs.loc[0, "policy_adjustment_reason"], "no_policy_adjustment")
        self.assertEqual(outputs.loc[0, "review_override_reason"], "no_review_override")
        self.assertAlmostEqual(outputs.loc[0, "policy_adjustment_fired_flag"], 0.0)
        self.assertAlmostEqual(outputs.loc[0, "policy_units_removed"], 0.0)
        self.assertAlmostEqual(outputs.loc[0, "policy_capital_at_risk_removed"], 0.0)


if __name__ == "__main__":
    unittest.main()