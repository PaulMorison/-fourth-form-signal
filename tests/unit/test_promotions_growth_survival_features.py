from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.feature_engineering import PromotionFeatureEngineer, iter_registered_feature_modules  # noqa: E402
from state.promotions.feature_engineering.demand.ft_growth_curve_shape import (  # noqa: E402
    FEATURE_COLUMNS as GROWTH_FEATURE_COLUMNS_ALIAS,
    GROWTH_CURVE_SHAPE_FEATURE_COLUMNS,
    REQUIRED_COLUMNS as GROWTH_REQUIRED_COLUMNS,
    apply_ft_growth_curve_shape,
)
from state.promotions.feature_engineering.demand.ft_growth_survival_interactions import (  # noqa: E402
    FEATURE_COLUMNS as INTERACTION_FEATURE_COLUMNS_ALIAS,
    GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS,
    apply_ft_growth_survival_interactions,
)
from state.promotions.feature_engineering.demand.ft_survival_convexity import (  # noqa: E402
    FEATURE_COLUMNS as SURVIVAL_FEATURE_COLUMNS_ALIAS,
    SURVIVAL_CONVEXITY_FEATURE_COLUMNS,
    apply_ft_survival_convexity,
)
from state.promotions.feature_engineering.stock.ft_overhang_risk import apply_ft_overhang_risk  # noqa: E402
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)


NEW_MODULE_NAMES = (
    "ft_growth_curve_shape",
    "ft_survival_convexity",
    "ft_growth_survival_interactions",
)
ALL_NEW_FEATURE_COLUMNS = (
    *GROWTH_CURVE_SHAPE_FEATURE_COLUMNS,
    *SURVIVAL_CONVEXITY_FEATURE_COLUMNS,
    *GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS,
)
DELETED_FEATURE_COLUMNS = (
    "feature_growth_curve_linear_fit_quality_score",
    "feature_growth_curve_exponential_fit_quality_score",
    "feature_growth_curve_exponential_vs_linear_preference_score",
    "feature_growth_curve_recent_demand_half_life_proxy",
    "feature_growth_curve_compounding_demand_score",
    "feature_growth_curve_demand_destruction_score",
    "feature_survival_convex_upside_score",
    "feature_survival_trust_compounding_score",
    "feature_survival_payoff_asymmetry_score",
    "feature_survival_winner_take_more_flag",
    "feature_growth_survival_stable_trust_compounding_score",
    "feature_growth_survival_noisy_weak_confidence_score",
    "feature_growth_survival_flattening_high_order_qty_score",
)


class PromotionsGrowthSurvivalFeatureTests(unittest.TestCase):
    def test_increasing_synthetic_demand_has_stronger_acceleration_and_convexity_than_flat_demand(self) -> None:
        frame = pd.DataFrame(
            [
                _row_from_daily_segments("flat", (2.0, 2.0, 2.0)),
                _row_from_daily_segments("accelerating", (1.0, 2.0, 5.0)),
            ]
        )

        result = apply_ft_growth_curve_shape(frame).set_index("promotion_row_key")

        self.assertGreater(
            result.loc["accelerating", "feature_growth_curve_acceleration_score"],
            result.loc["flat", "feature_growth_curve_acceleration_score"],
        )
        self.assertGreater(
            result.loc["accelerating", "feature_growth_curve_convexity_score"],
            result.loc["flat", "feature_growth_curve_convexity_score"],
        )

    def test_declining_synthetic_demand_has_stronger_decay_and_destruction_than_flat_demand(self) -> None:
        frame = pd.DataFrame(
            [
                _row_from_daily_segments("flat", (2.0, 2.0, 2.0)),
                _row_from_daily_segments("declining", (5.0, 2.0, 1.0)),
            ]
        )

        result = apply_ft_growth_curve_shape(frame).set_index("promotion_row_key")

        self.assertGreater(
            result.loc["declining", "feature_growth_curve_decay_persistence_score"],
            result.loc["flat", "feature_growth_curve_decay_persistence_score"],
        )
        self.assertEqual(result.loc["declining", "feature_growth_curve_monotonic_decline_flag"], 1.0)

    def test_noisy_demand_lowers_growth_curve_confidence(self) -> None:
        smooth_row = _row_from_daily_segments("smooth", (2.0, 3.0, 4.0), pre_56d_std_daily_units=0.15)
        noisy_row = _row_from_daily_segments("noisy", (1.0, 8.0, 1.0), pre_56d_std_daily_units=7.0)
        frame = pd.DataFrame([smooth_row, noisy_row])

        result = apply_ft_growth_curve_shape(frame).set_index("promotion_row_key")

        self.assertGreater(
            result.loc["noisy", "feature_growth_curve_noise_penalty_score"],
            result.loc["smooth", "feature_growth_curve_noise_penalty_score"],
        )
        self.assertLess(
            result.loc["noisy", "feature_growth_curve_confidence_score"],
            result.loc["smooth", "feature_growth_curve_confidence_score"],
        )

    def test_convex_upside_features_increase_when_prior_late_window_importance_is_higher(self) -> None:
        candidate = pd.DataFrame(
            [_row_from_daily_segments("candidate", (2.0, 3.0, 5.0), start_date=date(2024, 5, 1), stock_basis_units=35.0, required_implied_units=70.0)]
        )
        high_late_reference = pd.DataFrame(
            [
                _prior_row("high-1", start_date=date(2024, 1, 1), actual_units_sold_promo=58.0, post_14d_units=22.0, actual_days_with_sales_promo=7.0, stock_basis_units=62.0),
                _prior_row("high-2", start_date=date(2024, 2, 1), actual_units_sold_promo=61.0, post_14d_units=20.0, actual_days_with_sales_promo=7.0, stock_basis_units=64.0),
            ]
        )
        low_late_reference = pd.DataFrame(
            [
                _prior_row("low-1", start_date=date(2024, 1, 1), actual_units_sold_promo=24.0, post_14d_units=0.0, actual_days_with_sales_promo=2.0, stock_basis_units=70.0),
                _prior_row("low-2", start_date=date(2024, 2, 1), actual_units_sold_promo=25.0, post_14d_units=0.0, actual_days_with_sales_promo=3.0, stock_basis_units=72.0),
            ]
        )

        candidate_with_growth = apply_ft_growth_curve_shape(candidate)
        high_result = apply_ft_survival_convexity(candidate_with_growth, reference_frame=high_late_reference)
        low_result = apply_ft_survival_convexity(candidate_with_growth, reference_frame=low_late_reference)

        self.assertGreater(
            high_result.loc[0, "feature_survival_prior_late_window_importance_score"],
            low_result.loc[0, "feature_survival_prior_late_window_importance_score"],
        )
        self.assertGreater(
            high_result.loc[0, "feature_survival_internal_convex_upside_proxy_score"],
            low_result.loc[0, "feature_survival_internal_convex_upside_proxy_score"],
        )

    def test_prior_post_14_values_inside_forbidden_window_do_not_change_features(self) -> None:
        candidate = pd.DataFrame(
            [_row_from_daily_segments("candidate", (2.0, 3.0, 5.0), start_date=date(2024, 4, 28), stock_basis_units=35.0, required_implied_units=70.0)]
        )
        reference = pd.DataFrame(
            [_prior_row("recent-prior", start_date=date(2024, 4, 15), actual_units_sold_promo=58.0, post_14d_units=0.0, actual_days_with_sales_promo=7.0, stock_basis_units=62.0)]
        )
        mutated_reference = reference.copy()
        mutated_reference.loc[:, "post_14d_units"] = 9999.0
        mutated_reference.loc[:, "actual_units_post_14d"] = 9999.0

        candidate_with_growth = apply_ft_growth_curve_shape(candidate)
        original_features = apply_ft_survival_convexity(candidate_with_growth, reference_frame=reference)[list(SURVIVAL_CONVEXITY_FEATURE_COLUMNS)]
        mutated_features = apply_ft_survival_convexity(candidate_with_growth, reference_frame=mutated_reference)[list(SURVIVAL_CONVEXITY_FEATURE_COLUMNS)]

        pd.testing.assert_frame_equal(original_features, mutated_features)

    def test_multiple_candidate_rows_use_shared_prior_history_without_row_loop_semantics(self) -> None:
        candidates = pd.DataFrame(
            [
                _row_from_daily_segments("candidate-early", (2.0, 3.0, 5.0), start_date=date(2024, 2, 15), stock_basis_units=35.0, required_implied_units=70.0),
                _row_from_daily_segments("candidate-late", (2.0, 3.0, 5.0), start_date=date(2024, 4, 15), stock_basis_units=35.0, required_implied_units=70.0),
            ]
        )
        reference = pd.DataFrame(
            [
                _prior_row("prior-1", start_date=date(2024, 1, 1), actual_units_sold_promo=58.0, post_14d_units=0.0, actual_days_with_sales_promo=7.0, stock_basis_units=62.0),
                _prior_row("prior-2", start_date=date(2024, 3, 1), actual_units_sold_promo=61.0, post_14d_units=0.0, actual_days_with_sales_promo=7.0, stock_basis_units=64.0),
            ]
        )

        result = apply_ft_survival_convexity(apply_ft_growth_curve_shape(candidates), reference_frame=reference).set_index("promotion_row_key")

        self.assertGreater(
            result.loc["candidate-late", "feature_survival_convexity_confidence_score"],
            result.loc["candidate-early", "feature_survival_convexity_confidence_score"],
        )

    def test_future_only_current_values_do_not_change_feature_outputs(self) -> None:
        reference = pd.DataFrame(
            [_prior_row("prior", start_date=date(2024, 1, 1), actual_units_sold_promo=55.0, post_14d_units=18.0, actual_days_with_sales_promo=7.0)]
        )
        original = pd.DataFrame(
            [_row_from_daily_segments("candidate", (2.0, 3.0, 5.0), start_date=date(2024, 5, 1), actual_units_sold_promo=0.0, post_14d_units=0.0)]
        )
        mutated = original.copy()
        mutated.loc[:, "actual_units_sold_promo"] = 9999.0
        mutated.loc[:, "actual_units_sold"] = 9999.0
        mutated.loc[:, "post_14d_units"] = 9999.0
        mutated.loc[:, "actual_days_with_sales_promo"] = 7.0

        original_features = _apply_all_new_modules(original, reference_frame=reference)[list(ALL_NEW_FEATURE_COLUMNS)]
        mutated_features = _apply_all_new_modules(mutated, reference_frame=reference)[list(ALL_NEW_FEATURE_COLUMNS)]

        pd.testing.assert_frame_equal(original_features, mutated_features)

    def test_empty_frames_preserve_declared_columns_and_missing_required_columns_fail_loud(self) -> None:
        empty = pd.DataFrame(columns=_base_columns())

        result = _apply_all_new_modules(empty, reference_frame=empty)

        self.assertEqual(len(result.index), 0)
        for column_name in ALL_NEW_FEATURE_COLUMNS:
            self.assertIn(column_name, result.columns)
        with self.assertRaisesRegex(ValueError, "ft_growth_curve_shape missing required columns"):
            apply_ft_growth_curve_shape(pd.DataFrame(columns=[column for column in GROWTH_REQUIRED_COLUMNS if column != "pre_7d_units"]))

    def test_new_features_are_numeric_and_have_stable_null_handling(self) -> None:
        candidate = pd.DataFrame([_row_from_daily_segments("candidate", (2.0, 3.0, 5.0), start_date=date(2024, 5, 1))])
        reference = pd.DataFrame([_prior_row("prior", start_date=date(2024, 1, 1), actual_units_sold_promo=52.0, post_14d_units=16.0)])

        result = _apply_all_new_modules(candidate, reference_frame=reference)

        for column_name in ALL_NEW_FEATURE_COLUMNS:
            self.assertTrue(is_numeric_dtype(result[column_name]), column_name)
            self.assertFalse(result[column_name].isna().any(), column_name)
            self.assertTrue(np.isfinite(result[column_name]).all(), column_name)
        for flag_column in (
            "feature_growth_curve_monotonic_improvement_flag",
            "feature_growth_curve_monotonic_decline_flag",
            "feature_survival_must_not_stock_out_flag",
        ):
            self.assertTrue(set(result[flag_column].unique()).issubset({0.0, 1.0}), flag_column)

    def test_interaction_features_behave_directionally(self) -> None:
        frame = pd.DataFrame(
            [
                _interaction_input_row("accelerating", acceleration=0.9, convex_upside_proxy=0.8, allocation_qty=20.0, baseline_expected_units=40.0),
                _interaction_input_row("weak", acceleration=0.1, convex_upside_proxy=0.8, allocation_qty=20.0, baseline_expected_units=40.0),
                _interaction_input_row("declining", decay=0.8, overhang_risk=0.9),
            ]
        )

        result = apply_ft_growth_survival_interactions(frame).set_index("promotion_row_key")

        self.assertGreater(
            result.loc["accelerating", "feature_growth_survival_acceleration_x_internal_convex_upside_proxy_score"],
            result.loc["weak", "feature_growth_survival_acceleration_x_internal_convex_upside_proxy_score"],
        )
        self.assertGreater(result.loc["declining", "feature_growth_survival_decay_x_inventory_risk_score"], 0.5)

    def test_feature_names_are_stable_explicit_and_registry_integrates_schema(self) -> None:
        registered = {definition.name: definition for definition in iter_registered_feature_modules()}

        self.assertEqual(
            tuple(registered[module_name].output_columns for module_name in NEW_MODULE_NAMES),
            (
                GROWTH_CURVE_SHAPE_FEATURE_COLUMNS,
                SURVIVAL_CONVEXITY_FEATURE_COLUMNS,
                GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS,
            ),
        )
        self.assertEqual(GROWTH_FEATURE_COLUMNS_ALIAS, GROWTH_CURVE_SHAPE_FEATURE_COLUMNS)
        self.assertEqual(SURVIVAL_FEATURE_COLUMNS_ALIAS, SURVIVAL_CONVEXITY_FEATURE_COLUMNS)
        self.assertEqual(INTERACTION_FEATURE_COLUMNS_ALIAS, GROWTH_SURVIVAL_INTERACTION_FEATURE_COLUMNS)
        self.assertEqual(len(ALL_NEW_FEATURE_COLUMNS), 28)
        self.assertTrue(all(column_name.startswith("feature_") for column_name in ALL_NEW_FEATURE_COLUMNS))
        self.assertTrue(all("pct" not in column_name for column_name in ALL_NEW_FEATURE_COLUMNS))
        self.assertIn("feature_survival_internal_scarcity_capture_proxy_score", ALL_NEW_FEATURE_COLUMNS)
        self.assertIn("feature_survival_internal_convex_upside_proxy_score", ALL_NEW_FEATURE_COLUMNS)
        self.assertIn("feature_survival_inventory_continuity_trust_proxy_score", ALL_NEW_FEATURE_COLUMNS)
        for column_name in DELETED_FEATURE_COLUMNS:
            self.assertNotIn(column_name, ALL_NEW_FEATURE_COLUMNS)

    def test_selected_module_pipeline_returns_new_output_schema(self) -> None:
        candidate = pd.DataFrame([_row_from_daily_segments("candidate", (2.0, 3.0, 5.0), start_date=date(2024, 5, 1))])
        reference = pd.DataFrame([_prior_row("prior", start_date=date(2024, 1, 1), actual_units_sold_promo=52.0, post_14d_units=16.0)])
        selected_modules = ("ft_overhang_risk", *NEW_MODULE_NAMES)

        result = PromotionFeatureEngineer().engineer(
            candidate,
            historical_reference_frame=reference,
            selected_modules=selected_modules,
        )

        self.assertEqual(result.applied_modules, selected_modules)
        for column_name in ALL_NEW_FEATURE_COLUMNS:
            self.assertIn(column_name, result.frame.columns)
            self.assertIn(column_name, result.feature_columns)

    def test_training_and_scoring_feature_contracts_match_for_trimmed_family(self) -> None:
        completed = build_completed_promotions_base_frame()
        future = build_future_promotions_base_frame()

        training = PromotionFeatureEngineer().engineer(completed, historical_reference_frame=completed)
        scoring = PromotionFeatureEngineer().engineer(future, historical_reference_frame=completed)

        self.assertEqual(training.feature_columns, scoring.feature_columns)
        for column_name in ALL_NEW_FEATURE_COLUMNS:
            self.assertIn(column_name, training.frame.columns)
            self.assertIn(column_name, scoring.frame.columns)


def _apply_all_new_modules(frame: pd.DataFrame, *, reference_frame: pd.DataFrame | None = None) -> pd.DataFrame:
    with_growth = apply_ft_growth_curve_shape(frame)
    with_inventory_risk = apply_ft_overhang_risk(with_growth)
    with_survival = apply_ft_survival_convexity(with_inventory_risk, reference_frame=reference_frame)
    return apply_ft_growth_survival_interactions(with_survival)


def _prior_row(
    promotion_row_key: str,
    *,
    start_date: date,
    actual_units_sold_promo: float,
    post_14d_units: float,
    actual_days_with_sales_promo: float = 7.0,
    stock_basis_units: float = 64.0,
) -> dict[str, object]:
    row = _row_from_daily_segments(
        promotion_row_key,
        (2.0, 3.0, 4.0),
        start_date=start_date,
        stock_basis_units=stock_basis_units,
        required_implied_units=56.0,
    )
    row["actual_units_sold_promo"] = actual_units_sold_promo
    row["actual_units_sold"] = actual_units_sold_promo
    row["actual_days_with_sales_promo"] = actual_days_with_sales_promo
    row["post_14d_units"] = post_14d_units
    row["actual_units_post_14d"] = post_14d_units
    return row


def _row_from_daily_segments(
    promotion_row_key: str,
    daily_segments: tuple[float, float, float],
    *,
    start_date: date = date(2024, 4, 1),
    store_number_key: int = 1,
    sku_number_key: int = 100,
    stock_basis_units: float = 64.0,
    required_implied_units: float = 56.0,
    allocation_qty: float | None = None,
    pre_56d_std_daily_units: float = 0.25,
    actual_units_sold_promo: float = 0.0,
    post_14d_units: float = 0.0,
) -> dict[str, object]:
    early_daily_units, middle_daily_units, late_daily_units = daily_segments
    pre_7d_units = late_daily_units * 7.0
    pre_28d_units = middle_daily_units * 21.0 + pre_7d_units
    pre_56d_units = early_daily_units * 28.0 + pre_28d_units
    end_date = start_date + timedelta(days=6)
    promo_days = 7.0
    baseline_daily_units = pre_28d_units / 28.0
    allocation_qty = stock_basis_units if allocation_qty is None else allocation_qty
    return {
        "promotion_row_key": promotion_row_key,
        "store_number": store_number_key,
        "store_number_key": store_number_key,
        "sku_number": sku_number_key,
        "sku_number_key": sku_number_key,
        "promotion_name": "Synthetic Promo",
        "promo_type": "catalogue",
        "customer_offer": "20 percent off",
        "promotion_start_date": start_date.isoformat(),
        "promotional_end_date": end_date.isoformat(),
        "promotion_start_date_date": start_date.isoformat(),
        "promotional_end_date_date": end_date.isoformat(),
        "promo_days": promo_days,
        "regular_price": 20.0,
        "promo_price": 15.0,
        "promo_price_ex_gst": 15.0,
        "discount_percent": 0.25,
        "current_soh": stock_basis_units,
        "qty_on_order": 0.0,
        "pl_allocation_qty": allocation_qty,
        "pl_allocated": allocation_qty,
        "store_adjusted_qty": allocation_qty,
        "total_units_commited": allocation_qty,
        "total_stock_available": stock_basis_units,
        "avg_daily_units": baseline_daily_units,
        "avg_1_wk_units": baseline_daily_units * 7.0,
        "avg_8_wk_unit_sales": pre_56d_units,
        "pre_56d_units": pre_56d_units,
        "pre_28d_units": pre_28d_units,
        "pre_7d_units": pre_7d_units,
        "pre_56d_days_with_sales": 42.0,
        "pre_28d_days_with_sales": 21.0,
        "pre_7d_days_with_sales": 7.0,
        "pre_56d_avg_daily_units": pre_56d_units / 56.0,
        "pre_28d_avg_daily_units": baseline_daily_units,
        "pre_7d_avg_daily_units": late_daily_units,
        "pre_prior_21d_avg_daily_units": early_daily_units,
        "pre_56d_std_daily_units": pre_56d_std_daily_units,
        "pre_28d_std_daily_units": pre_56d_std_daily_units,
        "baseline_daily_units": baseline_daily_units,
        "baseline_expected_units": baseline_daily_units * promo_days,
        "stock_basis_units": stock_basis_units,
        "required_implied_daily": required_implied_units / promo_days,
        "required_implied_units": required_implied_units,
        "actual_units_sold": actual_units_sold_promo,
        "actual_units_sold_promo": actual_units_sold_promo,
        "actual_days_with_sales_promo": 0.0,
        "post_14d_units": post_14d_units,
        "actual_units_post_14d": post_14d_units,
    }


def _interaction_input_row(
    promotion_row_key: str,
    *,
    acceleration: float = 0.0,
    decay: float = 0.0,
    convex_upside_proxy: float = 0.0,
    overhang_risk: float = 0.0,
    allocation_qty: float = 40.0,
    baseline_expected_units: float = 40.0,
) -> dict[str, float | str]:
    return {
        "promotion_row_key": promotion_row_key,
        "feature_growth_curve_acceleration_score": acceleration,
        "feature_growth_curve_decay_persistence_score": decay,
        "feature_survival_internal_convex_upside_proxy_score": convex_upside_proxy,
        "feature_overhang_risk": overhang_risk,
        "pl_allocation_qty": allocation_qty,
        "baseline_expected_units": baseline_expected_units,
    }


def _base_columns() -> list[str]:
    return list(_row_from_daily_segments("template", (2.0, 2.0, 2.0)).keys())


if __name__ == "__main__":
    unittest.main()