from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.preprocessing import prepare_model_input_frame  # noqa: E402
from models.promotions.model_input_quality import PromotionModelInputQualityError  # noqa: E402
from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


class PromotionPreprocessingTests(unittest.TestCase):
    def test_prepare_model_input_treats_sku_number_as_display_safe(self) -> None:
        frame = build_completed_promotions_base_frame().copy()
        frame["sku_number"] = frame["sku_number"].astype(object)
        frame["sku_number_key"] = frame["sku_number_key"].astype(float).astype(str)
        frame.loc[0, "sku_number"] = "TUESDAY, 24 SEPTEMBER 2024 4:03 PM"
        frame.loc[1, "sku_number"] = "12345.0"
        frame.loc[2, "sku_number"] = ""
        frame.loc[3, "sku_number"] = None
        frame.loc[4, "sku_number"] = "NA"
        frame.loc[1, "sku_number_key"] = "12345.0"

        model_input, schema = prepare_model_input_frame(frame)

        self.assertEqual(len(model_input.index), len(frame.index))
        self.assertNotIn("sku_number", model_input.columns)
        self.assertNotIn("sku_number", schema.feature_columns)
        self.assertIn("sku_number_key", model_input.columns)
        self.assertIn("sku_number_key", schema.numeric_columns)
        self.assertTrue(pd.api.types.is_numeric_dtype(model_input["sku_number_key"]))
        self.assertAlmostEqual(model_input.loc[frame.index[1], "sku_number_key"], 12345.0)

    def test_prepare_model_input_fails_loud_for_invalid_sku_number_key(self) -> None:
        for invalid_value in ("", None, "NA", "12345.5"):
            with self.subTest(invalid_value=invalid_value):
                frame = build_completed_promotions_base_frame().copy()
                frame["sku_number"] = frame["sku_number"].astype(object)
                frame["sku_number_key"] = frame["sku_number_key"].astype(object)
                frame.loc[0, "sku_number"] = "display-only"
                frame.loc[0, "sku_number_key"] = invalid_value

                with self.assertRaisesRegex(
                    PromotionModelInputQualityError,
                    "Invalid governed numeric key fields detected: sku_number_key",
                ):
                    prepare_model_input_frame(frame)

    def test_prepare_model_input_excludes_identifier_strings_from_numeric_columns(self) -> None:
        frame = build_completed_promotions_base_frame().copy()
        frame["promotional_sku_id_key"] = frame["promotional_sku_id_key"].map(
            lambda value: f"772-{int(value)}-20240716"
        )

        model_input, schema = prepare_model_input_frame(frame)

        self.assertNotIn("promotional_sku_id_key", schema.numeric_columns)
        self.assertNotIn("promotional_sku_id_key", schema.feature_columns)
        self.assertNotIn("promotional_sku_id_key", model_input.columns)

    def test_prepare_model_input_keeps_true_numeric_columns_after_string_coercion(self) -> None:
        frame = build_completed_promotions_base_frame().copy()
        frame["current_soh"] = frame["current_soh"].astype(str)
        frame.loc[frame.index[0], "current_soh"] = "not-a-number"

        model_input, schema = prepare_model_input_frame(frame)

        self.assertIn("current_soh", schema.numeric_columns)
        self.assertTrue(pd.api.types.is_numeric_dtype(model_input["current_soh"]))
        self.assertTrue(pd.isna(model_input.loc[frame.index[0], "current_soh"]))

    def test_prepare_model_input_excludes_review_only_probability_features(self) -> None:
        frame = pd.DataFrame(
            {
                "promotion_start_date_date": ["2024-07-16", "2024-07-23"],
                "promotion_name": ["Week 29", "Week 30"],
                "promo_type": ["Catalogue", "Catalogue"],
                "customer_offer": ["Half Price", "2 for 1"],
                "sku_description": ["Widget", "Widget Plus"],
                "department": ["Skincare", "Skincare"],
                "category": ["Moisturiser", "Serum"],
                "feature_probability_overallocation_risk_score": [0.82, 0.31],
                "feature_probability_expected_units_consensus": [6.0, 2.5],
                "feature_probability_poisson_expected_units": [6.25, 2.75],
                "feature_units_lift_p_value": [0.021, 0.341],
            }
        )

        model_input, schema = prepare_model_input_frame(
            frame,
            feature_columns=(
                "feature_probability_overallocation_risk_score",
                "feature_probability_expected_units_consensus",
                "feature_probability_poisson_expected_units",
                "feature_units_lift_p_value",
            ),
        )

        self.assertIn("feature_probability_overallocation_risk_score", model_input.columns)
        self.assertIn("feature_probability_expected_units_consensus", model_input.columns)
        self.assertNotIn("feature_probability_poisson_expected_units", model_input.columns)
        self.assertNotIn("feature_units_lift_p_value", model_input.columns)
        self.assertIn(
            "feature_probability_poisson_expected_units",
            schema.quality_report.summary_payload["review_only_probability_columns_removed"],
        )
        self.assertIn(
            "feature_units_lift_p_value",
            schema.quality_report.summary_payload["review_only_probability_columns_removed"],
        )

    def test_prepare_model_input_excludes_review_only_basket_features(self) -> None:
        frame = pd.DataFrame(
            {
                "promotion_start_date_date": ["2024-07-16", "2024-07-23"],
                "promotion_name": ["Week 29", "Week 30"],
                "promo_type": ["Catalogue", "Catalogue"],
                "customer_offer": ["Half Price", "2 for 1"],
                "sku_description": ["Widget", "Widget Plus"],
                "department": ["Skincare", "Skincare"],
                "category": ["Moisturiser", "Serum"],
                "feature_basket_attach_rate": [0.82, 0.27],
                "feature_companion_absence_risk_score": [0.44, 0.11],
                "feature_basket_avg_items_when_sku_present": [3.8, 1.4],
                "feature_top_companion_sku_2_share": [0.21, 0.02],
                "feature_probability_units_given_multi_item_basket": [0.37, 0.18],
            }
        )

        model_input, schema = prepare_model_input_frame(
            frame,
            feature_columns=(
                "feature_basket_attach_rate",
                "feature_companion_absence_risk_score",
                "feature_basket_avg_items_when_sku_present",
                "feature_top_companion_sku_2_share",
                "feature_probability_units_given_multi_item_basket",
            ),
        )

        self.assertIn("feature_basket_attach_rate", model_input.columns)
        self.assertIn("feature_companion_absence_risk_score", model_input.columns)
        self.assertNotIn("feature_basket_avg_items_when_sku_present", model_input.columns)
        self.assertNotIn("feature_top_companion_sku_2_share", model_input.columns)
        self.assertNotIn("feature_probability_units_given_multi_item_basket", model_input.columns)
        self.assertIn(
            "feature_basket_avg_items_when_sku_present",
            schema.quality_report.summary_payload["review_only_basket_columns_removed"],
        )
        self.assertIn(
            "feature_top_companion_sku_2_share",
            schema.quality_report.summary_payload["review_only_basket_columns_removed"],
        )
        self.assertIn(
            "feature_probability_units_given_multi_item_basket",
            schema.quality_report.summary_payload["review_only_basket_columns_removed"],
        )

    def test_prepare_model_input_excludes_downstream_basket_equilibrium_from_default_units_head(self) -> None:
        frame = pd.DataFrame(
            {
                "promotion_start_date_date": ["2024-07-16", "2024-07-23"],
                "promotion_name": ["Week 29", "Week 30"],
                "promo_type": ["Catalogue", "Catalogue"],
                "customer_offer": ["Half Price", "2 for 1"],
                "sku_description": ["Widget", "Widget Plus"],
                "department": ["Skincare", "Skincare"],
                "category": ["Moisturiser", "Serum"],
                "feature_basket_anchor_sku_score": [0.82, 0.27],
                "feature_anchor_centrality_score": [0.77, 0.19],
                "feature_basket_equilibrium_score": [0.61, 0.22],
            }
        )

        model_input, schema = prepare_model_input_frame(frame)

        self.assertIn("feature_basket_anchor_sku_score", model_input.columns)
        self.assertNotIn("feature_anchor_centrality_score", model_input.columns)
        self.assertNotIn("feature_basket_equilibrium_score", model_input.columns)
        self.assertIn("feature_basket_anchor_sku_score", schema.feature_columns)
        self.assertNotIn("feature_anchor_centrality_score", schema.feature_columns)
        self.assertNotIn("feature_basket_equilibrium_score", schema.feature_columns)

    def test_prepare_model_input_defaults_to_slim_units_head_core(self) -> None:
        frame = pd.DataFrame(
            {
                "promotion_start_date_date": ["2024-07-16", "2024-07-23"],
                "promotion_name": ["Week 29", "Week 30"],
                "promo_type": ["Catalogue", "Catalogue"],
                "customer_offer": ["Half Price", "2 for 1"],
                "sku_description": ["Widget", "Widget Plus"],
                "department": ["Skincare", "Skincare"],
                "category": ["Moisturiser", "Serum"],
                "feature_basket_anchor_sku_score": [0.82, 0.27],
                "feature_sparse_demand_noise_regime_score": [0.61, 0.33],
                "feature_probability_expected_units_consensus": [6.4, 2.7],
                "feature_historical_promo_events_same_discount": [8.0, 3.0],
                "feature_historical_units_same_discount_avg": [5.8, 2.1],
                "feature_micro_market_clearing_pressure": [0.44, 0.18],
                "feature_end_of_promo_target_floor_units": [2.0, 1.0],
                "feature_uplift_allocation_discipline_score": [0.71, 0.29],
            }
        )

        model_input, schema = prepare_model_input_frame(frame)

        self.assertIn("feature_basket_anchor_sku_score", model_input.columns)
        self.assertIn("feature_sparse_demand_noise_regime_score", model_input.columns)
        self.assertIn("feature_probability_expected_units_consensus", model_input.columns)
        self.assertIn("feature_historical_promo_events_same_discount", model_input.columns)
        self.assertIn("feature_historical_units_same_discount_avg", model_input.columns)
        self.assertNotIn("feature_micro_market_clearing_pressure", model_input.columns)
        self.assertNotIn("feature_end_of_promo_target_floor_units", model_input.columns)
        self.assertNotIn("feature_uplift_allocation_discipline_score", model_input.columns)
        self.assertIn("feature_basket_anchor_sku_score", schema.feature_columns)
        self.assertNotIn("feature_micro_market_clearing_pressure", schema.feature_columns)

    def test_trainer_fits_with_string_identifier_columns_present(self) -> None:
        completed_base_frame = build_completed_promotions_base_frame()
        completed_base_frame["promotional_sku_id_key"] = completed_base_frame[
            "promotional_sku_id_key"
        ].map(lambda value: f"772-{int(value)}-20240716")

        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            dataset = PromotionDatasetAssembler().assemble_training_dataset(
                run_id="promotions-train-run",
                base_frame=completed_base_frame,
                target_frame=target_result.frame,
                feature_frame=feature_result.frame,
                target_columns=target_result.target_columns,
                feature_columns=feature_result.feature_columns,
                artifact_paths=artifact_paths,
            )

            training_artifacts = PromotionModelTrainer().train(
                run_id="promotions-train-run",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )

            self.assertTrue(Path(training_artifacts.manifest_path).exists())
