from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.model_input_quality import (  # noqa: E402
    iter_default_model_use_feature_columns,
    iter_review_only_engineered_feature_columns,
)
from models.promotions.target_stock_policy import (  # noqa: E402
    build_target_stock_policy_frame,
)
from state.promotions.feature_engineering.demand.ft_basket_structure_dependency import (  # noqa: E402
    BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS,
    apply_ft_basket_structure_dependency,
)
from state.promotions.feature_engineering.demand.ft_distribution_shape_distance import (  # noqa: E402
    DISTRIBUTION_SHAPE_DISTANCE_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_distribution_shape_distance,
)
from state.promotions.feature_engineering.demand.ft_fragility_adjusted_opportunity import (  # noqa: E402
    FRAGILITY_ADJUSTED_OPPORTUNITY_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_fragility_adjusted_opportunity,
)
from state.promotions.feature_engineering.demand.ft_kalman_state import (  # noqa: E402
    KALMAN_STATE_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_kalman_state,
)
from state.promotions.feature_engineering.demand.ft_micro_market_equilibrium import (  # noqa: E402
    MICRO_MARKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS,
    apply_ft_micro_market_equilibrium,
)
from state.promotions.feature_engineering.demand.ft_sparse_demand_noise import (  # noqa: E402
    SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS,
    apply_ft_sparse_demand_noise,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.scoring_service import PromotionModelScorer  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)
import tempfile


class BasketStructureDependencyFeatureTests(unittest.TestCase):
    def test_basket_structure_uses_prior_safe_context_not_realised_outcome(self) -> None:
        frame = _basket_frame()
        original = apply_ft_basket_structure_dependency(frame)
        mutated = frame.copy()
        mutated["actual_units_sold_promo"] = [0.0, 999.0, 999.0]
        changed_outcome = apply_ft_basket_structure_dependency(mutated)

        for column_name in BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS:
            self.assertTrue(original[column_name].equals(changed_outcome[column_name]), column_name)
        self.assertEqual(original.loc[0, "feature_top_20pct_driver_flag"], 1.0)
        self.assertGreater(original.loc[1, "feature_basket_drag_along_dependency_score"], 0.45)
        self.assertEqual(original.loc[1, "feature_long_tail_dependency_flag"], 1.0)

    def test_basket_structure_columns_are_model_use(self) -> None:
        default_model_use_columns = set(iter_default_model_use_feature_columns())
        self.assertTrue(
            set(BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS).issubset(default_model_use_columns)
        )


class SparseDemandNoiseFeatureTests(unittest.TestCase):
    def test_sparse_noise_distinguishes_random_tail_from_stable_low_demand(self) -> None:
        frame = pd.DataFrame(
            {
                "pre_56d_units": [1.0, 10.0],
                "pre_28d_units": [0.0, 5.0],
                "pre_7d_units": [0.0, 1.2],
                "pre_56d_days_with_sales": [1.0, 20.0],
                "pre_28d_days_with_sales": [0.0, 10.0],
                "pre_56d_std_daily_units": [2.0, 0.05],
                "baseline_daily_units": [0.02, 0.22],
                "feature_historical_promo_events_same_discount": [0.0, 2.0],
                "feature_basket_conditional_dependency_score": [0.0, 0.6],
                "feature_basket_anchor_sku_score": [0.0, 0.4],
                "actual_units_sold_promo": [50.0, 0.0],
            }
        )

        original = apply_ft_sparse_demand_noise(frame)
        mutated = frame.copy()
        mutated["actual_units_sold_promo"] = [0.0, 50.0]
        changed_outcome = apply_ft_sparse_demand_noise(mutated)

        for column_name in SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS:
            self.assertTrue(original[column_name].equals(changed_outcome[column_name]), column_name)
        self.assertEqual(original.loc[0, "feature_sparse_demand_random_tail_flag"], 1.0)
        self.assertEqual(original.loc[1, "feature_sparse_demand_stable_low_trust_flag"], 1.0)

    def test_sparse_noise_columns_are_model_use(self) -> None:
        default_model_use_columns = set(iter_default_model_use_feature_columns())
        self.assertTrue(set(SPARSE_DEMAND_NOISE_MODEL_USE_FEATURE_COLUMNS).issubset(default_model_use_columns))


class ExperimentalDiagnosticsFeatureTests(unittest.TestCase):
    def test_experimental_diagnostics_are_review_only(self) -> None:
        frame = pd.DataFrame(
            {
                "pre_prior_21d_avg_daily_units": [0.2],
                "pre_28d_avg_daily_units": [0.3],
                "pre_7d_avg_daily_units": [0.5],
                "pre_56d_avg_daily_units": [0.25],
                "pre_56d_std_daily_units": [0.1],
                "pre_28d_std_daily_units": [0.08],
                "pre_56d_days_with_sales": [12.0],
                "feature_basket_convexity_support_score": [0.6],
                "feature_basket_anchor_sku_score": [0.5],
                "feature_sparse_demand_stable_low_trust_flag": [1.0],
                "feature_sparse_demand_random_tail_flag": [0.0],
                "feature_distribution_tail_pressure_score": [0.4],
                "feature_survival_internal_convex_upside_proxy_score": [0.7],
                "feature_units_needed_for_trust_floor": [2.0],
            }
        )

        with_kalman = apply_ft_kalman_state(frame)
        with_distribution = apply_ft_distribution_shape_distance(with_kalman)
        with_opportunity = apply_ft_fragility_adjusted_opportunity(with_distribution)
        for column_name in (
            *KALMAN_STATE_REVIEW_ONLY_FEATURE_COLUMNS,
            *DISTRIBUTION_SHAPE_DISTANCE_REVIEW_ONLY_FEATURE_COLUMNS,
            *FRAGILITY_ADJUSTED_OPPORTUNITY_REVIEW_ONLY_FEATURE_COLUMNS,
        ):
            self.assertIn(column_name, with_opportunity.columns)

        review_only_columns = set(iter_review_only_engineered_feature_columns())
        model_use_columns = set(iter_default_model_use_feature_columns())
        self.assertTrue(set(KALMAN_STATE_REVIEW_ONLY_FEATURE_COLUMNS).issubset(review_only_columns))
        self.assertTrue(set(DISTRIBUTION_SHAPE_DISTANCE_REVIEW_ONLY_FEATURE_COLUMNS).issubset(review_only_columns))
        self.assertTrue(set(FRAGILITY_ADJUSTED_OPPORTUNITY_REVIEW_ONLY_FEATURE_COLUMNS).issubset(review_only_columns))
        self.assertTrue(set(KALMAN_STATE_REVIEW_ONLY_FEATURE_COLUMNS).isdisjoint(model_use_columns))
        self.assertTrue(set(DISTRIBUTION_SHAPE_DISTANCE_REVIEW_ONLY_FEATURE_COLUMNS).isdisjoint(model_use_columns))
        self.assertTrue(set(FRAGILITY_ADJUSTED_OPPORTUNITY_REVIEW_ONLY_FEATURE_COLUMNS).isdisjoint(model_use_columns))


class MicroMarketEquilibriumFeatureTests(unittest.TestCase):
    def test_micro_market_equilibrium_registers_deterministically_and_is_null_safe(self) -> None:
        frame = pd.DataFrame(
            {
                "feature_basket_anchor_sku_score": [0.8, 0.2, pd.NA],
                "feature_basket_drag_along_dependency_score": [0.1, 0.7, pd.NA],
                "feature_basket_lone_random_purchase_score": [0.1, 0.2, 0.9],
                "feature_sparse_demand_randomness_score": [0.1, 0.2, 0.9],
                "feature_sparse_demand_stable_low_trust_flag": [0.0, 1.0, 0.0],
                "feature_high_seller_companion_presence_probability": [0.8, 0.6, pd.NA],
                "feature_companion_absence_risk_score": [0.2, 0.7, pd.NA],
                "feature_basket_fragility_score": [0.1, 0.6, 0.4],
                "feature_basket_convexity_support_score": [0.7, 0.4, 0.1],
                "feature_transactions_with_sku_per_day": [4.0, 0.8, 0.0],
                "feature_units_per_transaction_when_sku_present": [1.6, 1.1, 0.0],
                "required_implied_units": [12.0, 3.0, 1.0],
                "baseline_expected_units": [10.0, 3.0, 1.0],
                "total_stock_available": [8.0, 5.0, 5.0],
                "feature_trust_floor_units_dynamic": [2.0, 2.0, 1.0],
                "feature_units_needed_for_trust_floor": [0.0, 1.0, 0.0],
                "feature_units_needed_for_high_demand_cover": [4.0, 0.0, 0.0],
                "effective_cost_per_unit": [2.0, 2.0, 2.0],
                "feature_excess_month_end_capital_drag": [0.0, 2.0, 0.0],
                "feature_local_promotional_field_density_score": [3.0, 1.0, 0.0],
                "feature_store_sync_score": [0.7, 0.4, 0.0],
                "actual_units_sold_promo": [0.0, 999.0, 999.0],
            }
        )

        original = apply_ft_micro_market_equilibrium(frame)
        mutated = frame.copy()
        mutated["actual_units_sold_promo"] = [999.0, 0.0, 0.0]
        changed_outcome = apply_ft_micro_market_equilibrium(mutated)

        for column_name in MICRO_MARKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS:
            self.assertTrue(original[column_name].equals(changed_outcome[column_name]), column_name)
            self.assertFalse(original[column_name].isna().any(), column_name)

    def test_micro_market_equilibrium_columns_are_model_use(self) -> None:
        default_model_use_columns = set(iter_default_model_use_feature_columns())
        self.assertTrue(set(MICRO_MARKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS).issubset(default_model_use_columns))


class ModelVisibleFamilySplitTests(unittest.TestCase):
    def test_model_use_and_review_only_families_resolve_in_training_and_scoring(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="family-visibility-train",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )
            training = PromotionModelTrainer().train(
                run_id="family-visibility-train",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            PromotionModelScorer().score(
                run_id="family-visibility-score",
                model_run_id="family-visibility-train",
                future_base_frame=build_future_promotions_base_frame(),
                historical_reference_frame=dataset.frame,
                artifact_paths=artifact_paths,
            )

            training_model_input = pd.read_parquet(training.model_input_audit_paths.parquet_path)
            scoring_model_input = pd.read_parquet(
                artifact_paths.inspection_run_root("family-visibility-score") / "model_scoring_input.parquet"
            )

            for column_name in (
                "feature_basket_anchor_sku_score",
                "feature_sparse_demand_noise_regime_score",
                "feature_probability_expected_units_consensus",
                "feature_historical_promo_events_same_discount",
                "feature_historical_units_same_discount_avg",
            ):
                self.assertIn(column_name, training_model_input.columns)
                self.assertIn(column_name, scoring_model_input.columns)

            for column_name in (
                "feature_micro_market_clearing_pressure",
                "feature_promo_period_target_units",
                "feature_cashflow_efficiency_score",
                "feature_kalman_demand_state_level",
                "feature_wasserstein_recent_vs_baseline_distance",
                "feature_fragility_adjusted_opportunity_score",
                "feature_dag_dependency_support_indicator",
            ):
                self.assertNotIn(column_name, training_model_input.columns)
                self.assertNotIn(column_name, scoring_model_input.columns)


class TargetStockPolicyTests(unittest.TestCase):
    def test_target_stock_policy_respects_duration_trust_and_month_end_rules(self) -> None:
        frame = pd.DataFrame(
            {
                "promo_type": ["sales event", "online event", "normal catalogue", "new line"],
                "promotion_start_date_date": ["2024-06-01", "2024-06-01", "2024-06-20", "2024-06-01"],
                "promotional_end_date_date": [pd.NA, pd.NA, "2024-06-28", pd.NA],
                "baseline_daily_units": [0.2, 1.5, 1.5, 0.1],
                "feature_historical_promo_events_same_discount": [2.0, 2.0, 2.0, 0.0],
                "feature_historical_promo_events_same_or_better_discount": [2.0, 2.0, 2.0, 0.0],
                "feature_promo_history_evidence_strength": [0.5, 0.5, 0.5, 0.0],
            }
        )

        policy = build_target_stock_policy_frame(frame)

        self.assertEqual(policy["promotion_duration_days"].tolist(), [7.0, 1.0, 14.0, 30.0])
        self.assertEqual(policy.loc[0, "trust_floor_target_units"], 2.0)
        self.assertEqual(policy.loc[1, "target_soh_at_promo_end_units"], 21.0)
        self.assertEqual(policy.loc[2, "target_soh_at_promo_end_units"], 10.5)
        self.assertGreaterEqual(policy.loc[2, "target_soh_at_promo_end_units"], 3.0)
        self.assertEqual(policy.loc[3, "trust_floor_target_units"], 1.0)
        self.assertEqual(policy.loc[3, "target_soh_at_promo_end_units"], 1.0)

    def test_target_stock_policy_fails_loud_without_duration(self) -> None:
        frame = pd.DataFrame(
            {
                "baseline_daily_units": [0.2],
                "feature_historical_promo_events_same_discount": [1.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "positive promotion duration"):
            build_target_stock_policy_frame(frame)


def _basket_frame() -> pd.DataFrame:
    """Return a compact prior-safe basket structure test frame."""

    return pd.DataFrame(
        {
            "store_number_key": [772, 772, 772],
            "promotion_header_key": ["PROMO", "PROMO", "PROMO"],
            "promotion_start_date_date": ["2024-06-01", "2024-06-01", "2024-06-01"],
            "required_implied_units": [50.0, 4.0, 2.0],
            "baseline_expected_units": [45.0, 3.0, 1.0],
            "pre_28d_units": [40.0, 2.0, 1.0],
            "feature_basket_attach_rate": [0.8, 0.7, 0.1],
            "feature_sku_basket_dependency_score": [0.3, 0.8, 0.1],
            "feature_sku_solo_purchase_rate": [0.1, 0.2, 0.9],
            "feature_top_companion_sku_1_share": [0.5, 0.7, 0.0],
            "feature_companion_concentration_index": [0.5, 0.8, 0.0],
            "feature_transactions_with_sku_per_day": [5.0, 0.7, 0.1],
            "feature_basket_history_evidence_promo_count": [5.0, 4.0, 0.0],
            "feature_basket_history_transaction_count": [50.0, 20.0, 0.0],
            "actual_units_sold_promo": [0.0, 0.0, 0.0],
        }
    )


if __name__ == "__main__":
    unittest.main()