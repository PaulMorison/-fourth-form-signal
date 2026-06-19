from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.model_input_quality import (  # noqa: E402
    iter_default_model_use_feature_columns,
    iter_downstream_decision_support_feature_columns,
    iter_review_only_engineered_feature_columns,
    iter_units_head_core_feature_columns,
)
from state.promotions.feature_engineering.demand.ft_basket_equilibrium import (  # noqa: E402
    BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS,
    BASKET_EQUILIBRIUM_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_basket_equilibrium,
)


class BasketEquilibriumFeatureTests(unittest.TestCase):
    def test_basket_equilibrium_is_prior_safe_and_null_safe(self) -> None:
        frame = _basket_equilibrium_frame()
        original = apply_ft_basket_equilibrium(frame)
        mutated = frame.copy()
        mutated["actual_units_sold_promo"] = [999.0] * len(mutated.index)
        changed_outcome = apply_ft_basket_equilibrium(mutated)

        for column_name in (
            *BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS,
            *BASKET_EQUILIBRIUM_REVIEW_ONLY_FEATURE_COLUMNS,
        ):
            self.assertTrue(original[column_name].equals(changed_outcome[column_name]), column_name)
        self.assertFalse(original.loc[:, BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS].isna().any(axis=None))

    def test_basket_equilibrium_detects_anchor_drag_and_noise_patterns(self) -> None:
        result = apply_ft_basket_equilibrium(_basket_equilibrium_frame()).set_index("row_id")

        self.assertGreater(
            result.loc["anchor", "feature_anchor_centrality_score"],
            result.loc["drag", "feature_anchor_centrality_score"],
        )
        self.assertGreater(
            result.loc["drag", "feature_drag_along_probability"],
            0.45,
        )
        self.assertGreater(
            result.loc["drag", "feature_conditional_lift_with_anchor"],
            0.0,
        )
        self.assertGreater(
            result.loc["solo", "feature_sparse_random_purchase_score"],
            result.loc["drag", "feature_sparse_random_purchase_score"],
        )
        self.assertEqual(result.loc["solo", "feature_basket_equilibrium_regime_class"], 0.0)

    def test_basket_equilibrium_generalises_across_store_groups(self) -> None:
        frame = _basket_equilibrium_frame()
        duplicate = frame.copy()
        duplicate["store_number_key"] = [2, 2, 2, 2]
        duplicate["promotion_header_key"] = ["PROMO_B"] * len(duplicate.index)
        duplicate["row_id"] = [f"store2_{value}" for value in duplicate["row_id"]]
        combined = pd.concat([frame, duplicate], ignore_index=True)

        result = apply_ft_basket_equilibrium(combined).set_index("row_id")
        compare_pairs = (
            ("anchor", "store2_anchor"),
            ("drag", "store2_drag"),
            ("drag_no_anchor", "store2_drag_no_anchor"),
            ("solo", "store2_solo"),
        )
        for left_key, right_key in compare_pairs:
            self.assertAlmostEqual(
                float(result.loc[left_key, "feature_basket_equilibrium_score"]),
                float(result.loc[right_key, "feature_basket_equilibrium_score"]),
                places=10,
            )
            self.assertAlmostEqual(
                float(result.loc[left_key, "feature_conditional_sale_rate_with_anchor"]),
                float(result.loc[right_key, "feature_conditional_sale_rate_with_anchor"]),
                places=10,
            )

    def test_basket_equilibrium_role_split_is_downstream_and_review_only_where_expected(self) -> None:
        default_model_use_columns = set(iter_default_model_use_feature_columns())
        downstream_columns = set(iter_downstream_decision_support_feature_columns())
        review_only_columns = set(iter_review_only_engineered_feature_columns())
        units_head_core_columns = set(iter_units_head_core_feature_columns())

        self.assertTrue(set(BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS).issubset(default_model_use_columns))
        self.assertTrue(set(BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS).issubset(downstream_columns))
        self.assertTrue(set(BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS).isdisjoint(units_head_core_columns))
        self.assertTrue(set(BASKET_EQUILIBRIUM_REVIEW_ONLY_FEATURE_COLUMNS).issubset(review_only_columns))
        self.assertTrue(set(BASKET_EQUILIBRIUM_REVIEW_ONLY_FEATURE_COLUMNS).isdisjoint(units_head_core_columns))


def _basket_equilibrium_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_id": ["anchor", "drag", "drag_no_anchor", "solo"],
            "store_number_key": [1, 1, 1, 1],
            "promotion_header_key": ["PROMO_A", "PROMO_A", "PROMO_C", "PROMO_A"],
            "promotion_start_date_date": ["2024-09-01", "2024-09-01", "2024-09-08", "2024-09-01"],
            "required_implied_units": [16.0, 4.0, 4.0, 1.0],
            "baseline_expected_units": [14.0, 3.0, 3.0, 1.0],
            "feature_basket_anchor_sku_score": [0.90, 0.18, 0.18, 0.05],
            "feature_top_20pct_driver_flag": [1.0, 0.0, 0.0, 0.0],
            "feature_basket_drag_along_dependency_score": [0.10, 0.82, 0.82, 0.05],
            "feature_basket_conditional_dependency_score": [0.15, 0.75, 0.20, 0.02],
            "feature_basket_attach_rate": [0.85, 0.78, 0.20, 0.08],
            "feature_probability_sku_in_multi_item_basket": [0.88, 0.80, 0.18, 0.05],
            "feature_sku_solo_purchase_rate": [0.12, 0.14, 0.55, 0.92],
            "feature_sparse_demand_randomness_score": [0.10, 0.20, 0.40, 0.85],
            "feature_sparse_demand_low_signal_flag": [0.0, 0.0, 0.0, 1.0],
            "feature_high_seller_companion_presence_probability": [0.80, 0.75, 0.20, 0.05],
            "feature_companion_absence_risk_score": [0.10, 0.70, 0.15, 0.25],
            "feature_companion_concentration_index": [0.55, 0.75, 0.30, 0.10],
            "feature_basket_diversity_when_sku_present": [0.45, 0.25, 0.70, 0.90],
            "feature_basket_history_evidence_promo_count": [6.0, 6.0, 2.0, 1.0],
            "feature_basket_history_transaction_count": [60.0, 60.0, 12.0, 2.0],
            "feature_transactions_with_sku_per_day": [5.0, 2.5, 0.7, 0.1],
            "feature_units_per_transaction_when_sku_present": [1.7, 1.4, 1.1, 1.0],
            "feature_local_competition_pressure": [0.20, 0.40, 0.10, 0.05],
            "feature_local_promotional_field_density_score": [0.35, 0.45, 0.20, 0.05],
            "feature_category_sync_score": [0.70, 0.60, 0.55, 0.10],
            "feature_store_sync_score": [0.72, 0.58, 0.50, 0.12],
            "actual_units_sold_promo": [8.0, 3.0, 1.0, 0.0],
        }
    )


if __name__ == "__main__":
    unittest.main()