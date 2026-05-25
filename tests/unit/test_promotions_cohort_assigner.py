from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.cohorts import PromotionCohortAssigner  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_repeating_promotions_base_frame  # noqa: E402


def _build_cohort_dataset() -> object:
    base_frame = build_repeating_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    return target_result.frame.merge(
        feature_result.frame[["promotion_row_key", *feature_result.feature_columns]],
        on="promotion_row_key",
        how="left",
    )


class PromotionCohortAssignerTests(unittest.TestCase):
    def test_assigner_builds_deterministic_keys(self) -> None:
        dataset = _build_cohort_dataset()

        first_assignment = PromotionCohortAssigner().assign(dataset).frame
        second_assignment = PromotionCohortAssigner().assign(dataset).frame

        self.assertTrue(
            first_assignment[
                [
                    "cohort_key_promotion_name",
                    "cohort_key_name_supplier",
                    "cohort_key_archetype_primary",
                    "cohort_key_archetype_secondary",
                ]
            ].equals(
                second_assignment[
                    [
                        "cohort_key_promotion_name",
                        "cohort_key_name_supplier",
                        "cohort_key_archetype_primary",
                        "cohort_key_archetype_secondary",
                    ]
                ]
            )
        )
        mega_sale_key = first_assignment.loc[
            first_assignment["promotion_name"] == "Mega Sale",
            "cohort_key_promotion_name",
        ].iloc[0]
        self.assertEqual(
            mega_sale_key,
            "cohort_key_promotion_name|promotion_name=mega_sale",
        )

    def test_assigner_maps_expected_archetype_buckets(self) -> None:
        dataset = _build_cohort_dataset()
        dataset.loc[0, "feature_discount_depth_pct"] = 0.42
        dataset.loc[0, "feature_price_gap_pct_vs_normal"] = 0.33
        dataset.loc[0, "feature_offer_text_percent_flag"] = 0.0
        dataset.loc[0, "feature_offer_text_amount_flag"] = 0.0
        dataset.loc[0, "feature_offer_text_bonus_flag"] = 0.0
        dataset.loc[0, "feature_offer_text_multi_buy_flag"] = 1.0
        dataset.loc[0, "feature_effective_margin_compression_pct"] = 0.35
        dataset.loc[0, "feature_rebate_dependency_score"] = 0.65
        dataset.loc[0, "feature_total_stock_pressure_ratio"] = 1.45
        dataset.loc[0, "feature_allocation_vs_baseline_demand_ratio"] = 1.40
        dataset.loc[0, "feature_overhang_risk"] = 0.55
        dataset.loc[0, "feature_pre_promo_baseline_daily_units"] = 18.0
        dataset.loc[0, "feature_recent_acceleration_ratio"] = 1.18
        dataset.loc[0, "feature_composite_promo_instability"] = 0.60
        dataset.loc[0, "feature_short_long_demand_phase_alignment"] = 0.95
        dataset.loc[0, "feature_promo_window_alignment_score"] = 0.92
        dataset.loc[0, "feature_category_sync_score"] = 0.91
        dataset.loc[0, "feature_store_sync_score"] = 0.88
        dataset.loc[0, "feature_category_gravity"] = 0.65
        dataset.loc[0, "feature_supplier_gravity"] = 0.68
        dataset.loc[0, "feature_promo_crowding_gravity"] = 0.66
        dataset.loc[0, "feature_field_density_score"] = 0.70
        dataset.loc[0, "feature_store_category_promo_density"] = 0.58
        dataset.loc[0, "feature_supplier_promo_density"] = 0.52
        dataset.loc[0, "feature_store_level_promo_load"] = 0.60

        assigned = PromotionCohortAssigner().assign(dataset).frame.iloc[0]

        self.assertEqual(assigned["archetype_discount_depth_regime"], "extreme")
        self.assertEqual(assigned["archetype_offer_mechanic_regime"], "multi_buy")
        self.assertEqual(assigned["archetype_margin_pressure_regime"], "critical")
        self.assertEqual(assigned["archetype_stock_pressure_regime"], "heavy")
        self.assertEqual(assigned["archetype_allocation_pressure_regime"], "surplus")
        self.assertEqual(assigned["archetype_overhang_risk_regime"], "severe")
        self.assertEqual(assigned["archetype_baseline_demand_regime"], "intense")
        self.assertEqual(assigned["archetype_demand_acceleration_regime"], "surging")
        self.assertEqual(assigned["archetype_zeta_instability_regime"], "critical")
        self.assertEqual(assigned["archetype_kuramoto_sync_regime"], "high_sync")
