from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.trainer import (  # noqa: E402
    DEFAULT_PROMOTION_UNITS_TARGET_MODE,
    LIVE_UNITS_TRAINING_TARGET_COLUMN,
    SUFFICIENT_STOCK_SHADOW_GB_MODEL_NAME,
    SUFFICIENT_STOCK_SHADOW_LINEAR_MODEL_NAME,
    SUFFICIENT_STOCK_SHADOW_TEST_PREDICTIONS_FILENAME,
    SUFFICIENT_STOCK_SHADOW_UNITS_TARGET_COLUMN,
    SUFFICIENT_STOCK_SHADOW_WEIGHT_COLUMN,
    PromotionModelTrainer,
    _build_sufficient_stock_shadow_units_training_sets,
    _resolve_units_target_mode,
    _resolve_units_training_target_column,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import build_completed_promotions_base_frame  # noqa: E402


def _assembled_dataset(temp_dir: str):
    base_frame = build_completed_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
    dataset = PromotionDatasetAssembler().assemble_training_dataset(
        run_id="shadow-trainer-test",
        base_frame=base_frame,
        target_frame=target_result.frame,
        feature_frame=feature_result.frame,
        target_columns=target_result.target_columns,
        feature_columns=feature_result.feature_columns,
        artifact_paths=artifact_paths,
    )
    return dataset, artifact_paths


class PromotionTrainerSufficientStockShadowTests(unittest.TestCase):
    def test_default_units_target_mode_is_legacy_realized_sales(self) -> None:
        self.assertEqual(_resolve_units_target_mode(None), "legacy_realized_sales")
        self.assertEqual(DEFAULT_PROMOTION_UNITS_TARGET_MODE, "legacy_realized_sales")

    def test_default_mode_uses_target_actual_units_sold(self) -> None:
        self.assertEqual(
            _resolve_units_training_target_column("legacy_realized_sales"),
            LIVE_UNITS_TRAINING_TARGET_COLUMN,
        )

    def test_feature_consensus_not_used_as_shadow_target(self) -> None:
        self.assertNotEqual(
            SUFFICIENT_STOCK_SHADOW_UNITS_TARGET_COLUMN,
            "feature_probability_expected_units_consensus",
        )

    def test_default_mode_trains_without_requiring_sufficient_stock_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_dataset(temp_dir)
            slim = dataset.frame.drop(
                columns=[
                    c
                    for c in (
                        SUFFICIENT_STOCK_SHADOW_UNITS_TARGET_COLUMN,
                        SUFFICIENT_STOCK_SHADOW_WEIGHT_COLUMN,
                        "target_quality_label",
                    )
                    if c in dataset.frame.columns
                ]
            )
            artifacts = PromotionModelTrainer().train(
                run_id="legacy-units-test",
                dataset=slim,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            manifest = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["units_target_mode"], "legacy_realized_sales")
            self.assertEqual(manifest["units_target_column"], LIVE_UNITS_TRAINING_TARGET_COLUMN)
            self.assertFalse(manifest["units_target_weight_used"])
            self.assertTrue(Path(artifacts.artifact_files["units_gradient_boosting"]).exists())
            self.assertNotIn(
                "target_mode_shadow_sufficient_stock_units_gb",
                artifacts.artifact_files,
            )

    def test_default_mode_preserves_live_artifact_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_dataset(temp_dir)
            artifacts = PromotionModelTrainer().train(
                run_id="legacy-artifacts-test",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
            )
            gb_path = Path(artifacts.artifact_files["units_gradient_boosting"])
            self.assertEqual(gb_path.name, "units_gradient_boosting.joblib")
            self.assertTrue(gb_path.exists())
            manifest = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            self.assertTrue(manifest["live_units_model_is_production_default"])

    def test_shadow_mode_uses_sufficient_stock_target_and_writes_shadow_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_dataset(temp_dir)
            artifacts = PromotionModelTrainer().train(
                run_id="shadow-units-test",
                dataset=dataset.frame,
                dataset_path=dataset.dataset_path,
                artifact_paths=artifact_paths,
                units_target_mode="sufficient_stock_shadow",
            )
            manifest = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["units_target_mode"], "sufficient_stock_shadow")
            self.assertEqual(manifest["units_target_column"], SUFFICIENT_STOCK_SHADOW_UNITS_TARGET_COLUMN)
            self.assertTrue(manifest["units_target_weight_used"])
            self.assertEqual(manifest["live_units_training_target_column"], LIVE_UNITS_TRAINING_TARGET_COLUMN)
            self.assertTrue(manifest["live_units_model_is_production_default"])
            self.assertIn("target_mode_shadow_sufficient_stock_units_gb", artifacts.artifact_files)
            gb_shadow = Path(artifacts.artifact_files["target_mode_shadow_sufficient_stock_units_gb"])
            self.assertTrue(gb_shadow.name.endswith(f"target_mode_{SUFFICIENT_STOCK_SHADOW_GB_MODEL_NAME}.joblib"))
            self.assertTrue(gb_shadow.exists())
            self.assertTrue(Path(artifacts.artifact_files["units_gradient_boosting"]).exists())
            shadow_pred = Path(artifacts.artifact_root) / SUFFICIENT_STOCK_SHADOW_TEST_PREDICTIONS_FILENAME
            self.assertTrue(shadow_pred.exists())
            self.assertTrue(Path(artifacts.test_set_predictions_path).exists())

    def test_shadow_mode_filters_positive_target_weight_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_dataset(temp_dir)
            frame = dataset.frame.copy()
            frame.loc[frame.index[0], SUFFICIENT_STOCK_SHADOW_WEIGHT_COLUMN] = 0.0
            trainer = PromotionModelTrainer()
            model_input, _schema = __import__(
                "models.promotions.preprocessing",
                fromlist=["prepare_model_input_frame"],
            ).prepare_model_input_frame(frame)
            split = trainer._time_splitter.split(frame)
            shadow_sets = _build_sufficient_stock_shadow_units_training_sets(
                dataset=frame,
                model_input=model_input,
                split=split,
            )
            train_count = int(shadow_sets["positive_train_row_count"])
            self.assertGreater(train_count, 0)
            self.assertTrue(shadow_sets["train_sample_weights"].gt(0.0).all())

    def test_shadow_mode_passes_sample_weight_to_units_fit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_dataset(temp_dir)
            calls: list[dict[str, object]] = []
            original = __import__(
                "models.promotions.trainer",
                fromlist=["_fit_units_pipeline_with_sample_weight"],
            )._fit_units_pipeline_with_sample_weight

            def _recording_fit(pipeline, features, targets, sample_weights):
                calls.append({"weights": sample_weights.copy()})
                return original(pipeline, features, targets, sample_weights)

            with patch(
                "models.promotions.trainer._fit_units_pipeline_with_sample_weight",
                side_effect=_recording_fit,
            ):
                PromotionModelTrainer().train(
                    run_id="shadow-weight-test",
                    dataset=dataset.frame,
                    dataset_path=dataset.dataset_path,
                    artifact_paths=artifact_paths,
                    units_target_mode="sufficient_stock_shadow",
                )
            self.assertGreaterEqual(len(calls), 2)
            self.assertTrue(all(call["weights"].gt(0.0).all() for call in calls))

    def test_shadow_mode_missing_target_column_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_dataset(temp_dir)
            frame = dataset.frame.drop(columns=[SUFFICIENT_STOCK_SHADOW_UNITS_TARGET_COLUMN])
            with self.assertRaises(ValueError):
                PromotionModelTrainer().train(
                    run_id="shadow-missing-target",
                    dataset=frame,
                    dataset_path=dataset.dataset_path,
                    artifact_paths=artifact_paths,
                    units_target_mode="sufficient_stock_shadow",
                )

    def test_shadow_mode_missing_target_weight_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_dataset(temp_dir)
            frame = dataset.frame.drop(columns=[SUFFICIENT_STOCK_SHADOW_WEIGHT_COLUMN])
            with self.assertRaises(ValueError):
                PromotionModelTrainer().train(
                    run_id="shadow-missing-weight",
                    dataset=frame,
                    dataset_path=dataset.dataset_path,
                    artifact_paths=artifact_paths,
                    units_target_mode="sufficient_stock_shadow",
                )

    def test_shadow_mode_zero_positive_weight_rows_fail_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset, artifact_paths = _assembled_dataset(temp_dir)
            frame = dataset.frame.copy()
            frame[SUFFICIENT_STOCK_SHADOW_WEIGHT_COLUMN] = 0.0
            with self.assertRaises(ValueError):
                PromotionModelTrainer().train(
                    run_id="shadow-zero-weight",
                    dataset=frame,
                    dataset_path=dataset.dataset_path,
                    artifact_paths=artifact_paths,
                    units_target_mode="sufficient_stock_shadow",
                )


if __name__ == "__main__":
    unittest.main()
