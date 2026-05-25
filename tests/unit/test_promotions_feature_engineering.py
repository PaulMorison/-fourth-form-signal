from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.feature_engineering import (  # noqa: E402
    PromotionFeatureEngineer,
    iter_registered_feature_modules,
)
from state.promotions.feature_engineering.pricing.ft_discount_depth import (  # noqa: E402
    apply_ft_discount_depth,
)
from state.promotions.feature_engineering.pricing.ft_price_gap import apply_ft_price_gap  # noqa: E402
from state.promotions.feature_engineering.shared.ft_group_windows import (  # noqa: E402
    apply_ft_baseline_windows,
)
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)


class PromotionFeatureEngineeringTests(unittest.TestCase):
    def test_registry_exposes_requested_ft_modules(self) -> None:
        registered_module_names = {
            definition.name for definition in iter_registered_feature_modules()
        }
        expected_modules = {
            "ft_discount_depth",
            "ft_price_gap",
            "ft_offer_strength",
            "ft_offer_text_flags",
            "ft_catalogue_position",
            "ft_margin_pressure",
            "ft_rebate_economics",
            "ft_unit_profitability",
            "ft_fee_burden",
            "ft_inventory_capital_risk",
            "ft_allocation_pressure",
            "ft_stock_posture",
            "ft_cover_and_exposure",
            "ft_commitment_pressure",
            "ft_overhang_risk",
            "ft_baseline_demand",
            "ft_near_term_demand_shift",
            "ft_sales_velocity",
            "ft_history_regime",
            "ft_basket_context_feature_bundle",
            "ft_store_context",
            "ft_category_context",
            "ft_supplier_context",
            "ft_promo_field_context",
            "ft_zeta_instability",
            "ft_kuramoto_sync",
            "ft_gravity_field",
            "ft_friction_signals",
            "ft_compensation_signals",
            "ft_reality_gap",
        }
        self.assertTrue(expected_modules.issubset(registered_module_names))

    def test_future_rows_use_historical_prior_response(self) -> None:
        completed_frame = PromotionTargetEngineer().engineer(
            build_completed_promotions_base_frame()
        ).frame
        future_frame = build_future_promotions_base_frame()

        result = PromotionFeatureEngineer().engineer(
            future_frame,
            historical_reference_frame=completed_frame,
        ).frame

        first_future_row = result.loc[result["sku_number_key"] == 100].iloc[0]
        self.assertIn("feature_prior_promo_response_same_sku_store", result.columns)
        self.assertIn("feature_offer_strength_score", result.columns)
        self.assertIn("feature_compensation_needed_score", result.columns)
        self.assertIn("feature_reality_gap_score", result.columns)
        self.assertGreater(first_future_row["feature_prior_promo_response_same_sku_store"], 0.0)
        self.assertGreaterEqual(first_future_row["feature_network_synchronisation_score"], 0.0)

    def test_promo_field_context_preserves_overlap_semantics(self) -> None:
        frame = build_completed_promotions_base_frame().iloc[[0, 4, 6]].copy().reset_index(drop=True)
        frame.loc[:, "store_number"] = 1
        frame.loc[:, "store_number_key"] = 1
        frame.loc[0, "promotion_start_date"] = "2024-01-01"
        frame.loc[0, "promotion_start_date_date"] = "2024-01-01"
        frame.loc[0, "promotional_end_date"] = "2024-01-07"
        frame.loc[0, "promotional_end_date_date"] = "2024-01-07"
        frame.loc[0, "category"] = "Skin Care"
        frame.loc[0, "inferred_supplier_number"] = 10
        frame.loc[0, "promotion_row_key"] = "row-a"
        frame.loc[1, "promotion_start_date"] = "2024-01-05"
        frame.loc[1, "promotion_start_date_date"] = "2024-01-05"
        frame.loc[1, "promotional_end_date"] = "2024-01-09"
        frame.loc[1, "promotional_end_date_date"] = "2024-01-09"
        frame.loc[1, "category"] = "Skin Care"
        frame.loc[1, "inferred_supplier_number"] = 11
        frame.loc[1, "promotion_row_key"] = "row-b"
        frame.loc[2, "promotion_start_date"] = "2024-01-02"
        frame.loc[2, "promotion_start_date_date"] = "2024-01-02"
        frame.loc[2, "promotional_end_date"] = "2024-01-03"
        frame.loc[2, "promotional_end_date_date"] = "2024-01-03"
        frame.loc[2, "category"] = "Cosmetics"
        frame.loc[2, "inferred_supplier_number"] = 10
        frame.loc[2, "promotion_row_key"] = "row-c"

        with_pricing = apply_ft_price_gap(apply_ft_discount_depth(apply_ft_baseline_windows(frame)))
        expected_discount_a = with_pricing.loc[0, "feature_discount_depth_pct"]
        expected_discount_b = with_pricing.loc[1, "feature_discount_depth_pct"]
        expected_discount_c = with_pricing.loc[2, "feature_discount_depth_pct"]
        expected_density_a = (
            expected_discount_b * with_pricing.loc[1, "baseline_expected_units"]
            + expected_discount_c * with_pricing.loc[2, "baseline_expected_units"]
        )
        expected_density_b = expected_discount_a * with_pricing.loc[0, "baseline_expected_units"]

        result = PromotionFeatureEngineer().engineer(
            frame,
            selected_modules=(
                "ft_discount_depth",
                "ft_price_gap",
                "ft_promo_field_context",
            ),
        ).frame.set_index("promotion_row_key")

        self.assertEqual(result.loc["row-a", "feature_store_overlap_count"], 2.0)
        self.assertAlmostEqual(
            result.loc["row-a", "feature_category_overlap_discount_sum"],
            expected_discount_b,
        )
        self.assertAlmostEqual(
            result.loc["row-a", "feature_supplier_overlap_discount_sum"],
            expected_discount_c,
        )
        self.assertAlmostEqual(
            result.loc["row-a", "feature_substitute_overlap_discount_sum"],
            expected_discount_b,
        )
        self.assertAlmostEqual(
            result.loc["row-a", "feature_local_promotional_field_density_score"],
            expected_density_a,
        )
        self.assertEqual(result.loc["row-b", "feature_store_overlap_count"], 1.0)
        self.assertAlmostEqual(
            result.loc["row-b", "feature_local_promotional_field_density_score"],
            expected_density_b,
        )
        self.assertEqual(result.loc["row-c", "feature_store_overlap_count"], 1.0)
        self.assertAlmostEqual(
            result.loc["row-c", "feature_supplier_overlap_discount_sum"],
            expected_discount_a,
        )
