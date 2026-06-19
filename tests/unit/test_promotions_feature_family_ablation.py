from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.run_promotions_feature_family_ablation import (  # noqa: E402
    FeatureFamilyAblationScenario,
    PROMO_TYPE_BUCKET_NEW_LINE,
    PROMO_TYPE_BUCKET_NORMAL,
    PROMO_TYPE_BUCKET_ONLINE,
    PROMO_TYPE_BUCKET_SALES_EVENT,
    _normalize_promo_type_bucket,
    build_feature_family_ablation_scenarios,
    run_feature_family_ablation,
)
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class PromotionFeatureFamilyAblationScenarioTests(unittest.TestCase):
    def test_scenarios_include_requested_base_core_and_interaction_runs(self) -> None:
        feature_columns = (
            "feature_basket_anchor_sku_score",
            "feature_basket_conditional_dependency_score",
            "feature_sparse_demand_noise_regime_score",
            "feature_micro_market_clearing_pressure",
            "feature_end_of_promo_target_floor_units",
            "feature_uplift_allocation_discipline_score",
            "feature_probability_expected_units_consensus",
            "feature_historical_promo_events_same_discount",
            "feature_historical_units_same_discount_avg",
        )

        scenarios = build_feature_family_ablation_scenarios(feature_columns)
        scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}

        self.assertIn("control_full_model_visible", scenario_by_id)
        self.assertIn("base_core_only", scenario_by_id)
        self.assertIn("base_core_plus_micro_interaction", scenario_by_id)
        self.assertIn("base_core_plus_target_stock_shape", scenario_by_id)
        self.assertIn("base_core_plus_allocation_discipline", scenario_by_id)
        self.assertIn("base_core_plus_micro_market_equilibrium", scenario_by_id)
        self.assertIn(
            "feature_micro_interaction_anchor_market_pressure",
            scenario_by_id["base_core_plus_micro_interaction"].feature_columns,
        )
        self.assertNotIn(
            "feature_micro_market_clearing_pressure",
            scenario_by_id["base_core_plus_micro_interaction"].feature_columns,
        )
        self.assertIn(
            "feature_micro_market_clearing_pressure",
            scenario_by_id["base_core_plus_micro_market_equilibrium"].feature_columns,
        )

    def test_normalize_promo_type_bucket(self) -> None:
        self.assertEqual(_normalize_promo_type_bucket("online event", ""), PROMO_TYPE_BUCKET_ONLINE)
        self.assertEqual(_normalize_promo_type_bucket("sales event", ""), PROMO_TYPE_BUCKET_SALES_EVENT)
        self.assertEqual(_normalize_promo_type_bucket("catalogue", "new line launch"), PROMO_TYPE_BUCKET_NEW_LINE)
        self.assertEqual(_normalize_promo_type_bucket("catalogue", "week 19"), PROMO_TYPE_BUCKET_NORMAL)


class PromotionFeatureFamilyAblationRuntimeTests(unittest.TestCase):
    def test_runtime_writes_required_ablation_artifacts(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="ablation-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )

            selected_scenarios = (
                FeatureFamilyAblationScenario(
                    scenario_id="control_full_model_visible",
                    scenario_kind="control_full",
                    description="full",
                    feature_columns=tuple(dataset.manifest.feature_columns),
                    included_families=("allocation_discipline",),
                    excluded_families=(),
                ),
                FeatureFamilyAblationScenario(
                    scenario_id="base_core_only",
                    scenario_kind="base_core_only",
                    description="base core",
                    feature_columns=tuple(
                        column_name
                        for column_name in dataset.manifest.feature_columns
                        if column_name in {
                            "feature_probability_expected_units_consensus",
                            "feature_historical_promo_events_same_discount",
                            "feature_historical_units_same_discount_avg",
                        }
                    ),
                    included_families=("probability", "same_discount_promo_history"),
                    excluded_families=(),
                ),
                FeatureFamilyAblationScenario(
                    scenario_id="base_core_plus_micro_interaction",
                    scenario_kind="base_core_plus_interaction_bundle",
                    description="micro interaction",
                    feature_columns=(
                        "feature_probability_expected_units_consensus",
                        "feature_historical_promo_events_same_discount",
                        "feature_historical_units_same_discount_avg",
                        "feature_micro_interaction_anchor_market_pressure",
                    ),
                    included_families=("basket_structure_dependency", "micro_interaction"),
                    excluded_families=(),
                ),
            )

            with patch(
                "runtime.promotions.run_promotions_feature_family_ablation.build_feature_family_ablation_scenarios",
                return_value=selected_scenarios,
            ):
                artifacts = run_feature_family_ablation(
                    run_id="ablation-run",
                    artifact_paths=artifact_paths,
                    output_root=artifact_paths.inspection_run_root("ablation-run") / "feature_family_ablation",
                )

            self.assertTrue(Path(artifacts.summary_csv_path).exists())
            self.assertTrue(Path(artifacts.summary_json_path).exists())
            self.assertTrue(Path(artifacts.promo_type_breakdown_csv_path).exists())
            self.assertTrue(Path(artifacts.store_level_robustness_csv_path).exists())
            self.assertTrue(Path(artifacts.sparse_demand_breakdown_csv_path).exists())
            self.assertTrue(Path(artifacts.trust_capital_breakdown_csv_path).exists())
            self.assertTrue(Path(artifacts.conclusion_json_path).exists())
            self.assertTrue(Path(artifacts.runtime_manifest_json_path).exists())

            payload = json.loads(Path(artifacts.summary_json_path).read_text(encoding="utf-8"))
            self.assertEqual(len(payload["scenario_rows"]), 3)
            self.assertIn("sparse_demand_breakdown_rows", payload)
            self.assertIn("trust_capital_breakdown_rows", payload)
            self.assertIn("ranked_conclusion", payload)
            self.assertEqual(
                payload["ranked_conclusion"]["recommendation"],
                "insufficient_scenarios",
            )
            conclusion = json.loads(Path(artifacts.conclusion_json_path).read_text(encoding="utf-8"))
            self.assertIn("recommendation", conclusion)


if __name__ == "__main__":
    unittest.main()