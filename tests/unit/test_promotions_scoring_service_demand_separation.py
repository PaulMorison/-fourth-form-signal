"""Phase 1: demand forecast must not be overwritten by order policy caps in scoring."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.order_policy_adjustments import ORDER_POLICY_ADJUSTMENT_COLUMNS  # noqa: E402
from models.promotions.trainer import PromotionModelTrainer  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.scoring_service import PromotionModelScorer  # noqa: E402
from state.promotions.datasets.dataset_assembler import PromotionDatasetAssembler  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)


def _train_and_score() -> pd.DataFrame:
    completed_base_frame = build_completed_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(completed_base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    temp_dir = tempfile.mkdtemp()
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
    PromotionModelTrainer().train(
        run_id="promotions-train-run",
        dataset=dataset.frame,
        dataset_path=dataset.dataset_path,
        artifact_paths=artifact_paths,
    )
    future_base_frame = build_future_promotions_base_frame()
    scoring_artifacts = PromotionModelScorer().score(
        run_id="promotions-score-run",
        model_run_id="promotions-train-run",
        future_base_frame=future_base_frame,
        historical_reference_frame=dataset.frame,
        artifact_paths=artifact_paths,
    )
    return scoring_artifacts.row_frame.copy()


class ScoringServiceDemandSeparationTests(unittest.TestCase):
    row_frame: pd.DataFrame

    @classmethod
    def setUpClass(cls) -> None:
        cls.row_frame = _train_and_score()

    def test_scoring_predicted_units_sold_equals_calibrated_when_policy_fires(self) -> None:
        row_frame = self.row_frame
        policy_fired = pd.to_numeric(
            row_frame["policy_adjustment_fired_flag"],
            errors="coerce",
        ).fillna(0.0).ge(1.0)
        self.assertTrue(policy_fired.any(), "expected at least one policy-fired row in fixture score")
        fired = row_frame.loc[policy_fired]
        pd.testing.assert_series_equal(
            fired["predicted_units_sold"],
            fired["calibrated_predicted_units_sold"],
            check_names=False,
        )
        capped = fired["adjusted_order_cap_units"].lt(fired["calibrated_predicted_units_sold"])
        self.assertTrue(capped.any(), "expected at least one row where order cap < calibrated demand")
        self.assertTrue(
            (fired.loc[capped, "predicted_units_sold"] > fired.loc[capped, "adjusted_order_cap_units"]).all()
        )

    def test_policy_adjusted_differs_from_predicted_units_sold_when_capped(self) -> None:
        row_frame = self.row_frame
        capped_mask = row_frame["adjusted_order_cap_units"].lt(row_frame["calibrated_predicted_units_sold"])
        self.assertTrue(capped_mask.any())
        capped = row_frame.loc[capped_mask]
        self.assertTrue(
            (capped["policy_adjusted_predicted_units_sold"] != capped["predicted_units_sold"]).all()
        )

    def test_predicted_units_first_day_derived_from_demand_not_cap(self) -> None:
        row_frame = self.row_frame
        promo_days = pd.to_numeric(
            row_frame["live_promo_window_days"].where(
                row_frame["live_promo_window_days"].notna(),
                row_frame.get("promo_days", pd.Series(7, index=row_frame.index)),
            ),
            errors="coerce",
        ).replace(0, 7).fillna(7)
        expected_first_day = (
            row_frame["predicted_units_sold"] / promo_days
        ).clip(lower=0.0)
        pd.testing.assert_series_equal(
            row_frame["predicted_units_first_day"],
            expected_first_day,
            check_names=False,
            rtol=1e-9,
            atol=1e-9,
        )
        capped_mask = row_frame["adjusted_order_cap_units"].lt(row_frame["calibrated_predicted_units_sold"])
        if capped_mask.any():
            capped = row_frame.loc[capped_mask]
            cap_first_day = (capped["adjusted_order_cap_units"] / promo_days.loc[capped.index]).clip(lower=0.0)
            self.assertTrue((capped["predicted_units_first_day"] != cap_first_day).any())

    def test_order_policy_columns_preserved_after_demand_separation(self) -> None:
        row_frame = self.row_frame
        for column_name in (
            "adjusted_order_cap_units",
            *ORDER_POLICY_ADJUSTMENT_COLUMNS,
            "policy_adjusted_predicted_units_sold",
            "policy_adjustment_reason",
            "review_override_flag",
        ):
            self.assertIn(column_name, row_frame.columns)
        self.assertFalse(row_frame["adjusted_order_cap_units"].isna().all())

    @patch("runtime.promotions.scoring_service.write_model_input_audit_artifacts")
    @patch("runtime.promotions.scoring_service.build_order_policy_adjustments")
    @patch("runtime.promotions.scoring_service.compute_allocation_aware_cap_units")
    @patch("runtime.promotions.scoring_service.joblib.load")
    def test_scoring_assignment_uses_calibrated_not_order_cap(
        self,
        mock_joblib_load: MagicMock,
        mock_apply_cap: MagicMock,
        mock_build_policy: MagicMock,
        mock_write_audit: MagicMock,
    ) -> None:
        """Direct assignment-path test with controlled raw/calibrated/cap values."""
        del mock_write_audit
        index = pd.Index([0])
        raw = pd.Series([12.0], index=index)
        allocation_cap = pd.Series([9.0], index=index)
        mock_apply_cap.return_value = allocation_cap

        policy_frame = pd.DataFrame(
            {
                "adjusted_supported_total_units": [2.0],
                "adjusted_launch_units": [1.0],
                "adjusted_order_cap_units": [2.0],
                "review_override_flag": [0.0],
                "review_override_reason": ["no_review_override"],
                "policy_adjustment_reason": ["weak_elasticity_uplift_restraint"],
                "policy_adjustment_strength": [0.35],
                "policy_adjustment_fired_flag": [1.0],
                "policy_units_removed": [7.0],
                "policy_capital_at_risk_removed": [0.0],
            },
            index=index,
        )
        mock_build_policy.return_value = policy_frame

        mock_model = MagicMock()
        mock_model.predict.return_value = raw.values
        mock_model.predict_proba.return_value = np.array([[0.1, 0.9]])
        mock_joblib_load.return_value = mock_model

        completed_base_frame = build_completed_promotions_base_frame()
        target_result = PromotionTargetEngineer().engineer(completed_base_frame)
        feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
        temp_dir = tempfile.mkdtemp()
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
        PromotionModelTrainer().train(
            run_id="promotions-train-run",
            dataset=dataset.frame,
            dataset_path=dataset.dataset_path,
            artifact_paths=artifact_paths,
        )
        future_base_frame = build_future_promotions_base_frame().iloc[:1].copy()
        scored = PromotionModelScorer().score(
            run_id="promotions-score-run-controlled",
            model_run_id="promotions-train-run",
            future_base_frame=future_base_frame,
            historical_reference_frame=dataset.frame,
            artifact_paths=artifact_paths,
        )
        out = scored.row_frame.iloc[0]
        self.assertEqual(float(out["predicted_units_sold"]), 12.0)
        self.assertEqual(float(out["calibrated_predicted_units_sold"]), 12.0)
        self.assertEqual(float(out["allocation_cap_units"]), 9.0)
        self.assertEqual(float(out["adjusted_order_cap_units"]), 2.0)
        self.assertEqual(float(out["policy_adjusted_predicted_units_sold"]), 2.0)
        self.assertEqual(float(out["predicted_units_first_day"]), 12.0 / float(out["live_promo_window_days"] or out["promo_days"] or 7))


if __name__ == "__main__":
    unittest.main()
