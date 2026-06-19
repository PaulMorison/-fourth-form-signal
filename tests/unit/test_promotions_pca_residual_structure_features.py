from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.model_input_quality import (  # noqa: E402
    BOUNDED_ZERO_ONE_COLUMNS,
    iter_default_model_use_feature_columns,
)
from state.promotions.feature_engineering import (  # noqa: E402
    PromotionFeatureEngineer,
    iter_registered_feature_modules,
)
from state.promotions.feature_engineering.demand.ft_pca_residual_structure import (  # noqa: E402
    PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS,
    PCA_RESIDUAL_STRUCTURE_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_pca_residual_structure,
)
from tests.unit.promotions_test_data import (  # noqa: E402
    build_completed_promotions_base_frame,
    build_future_promotions_base_frame,
)


def _build_date_only_frame(
    row_count: int,
    *,
    start_date: str,
) -> pd.DataFrame:
    start_dates = pd.date_range(start=start_date, periods=row_count, freq="7D")
    return pd.DataFrame(
        {
            "promotion_start_date_date": start_dates,
            "promotional_end_date_date": start_dates + pd.Timedelta(days=6),
            "actual_units_sold": np.linspace(12.0, 12.0 + row_count - 1, row_count),
        }
    )


def _with_pca_source_columns(
    frame: pd.DataFrame,
    *,
    seed_offset: float = 0.0,
    outlier_rows: tuple[int, ...] = (),
) -> pd.DataFrame:
    working = frame.copy()
    latent_index = pd.Series(np.arange(len(working.index), dtype="float64"), index=working.index)
    latent_a = 1.0 + (latent_index + seed_offset) * 0.07
    latent_b = 0.2 + ((latent_index + seed_offset) % 5.0) * 0.04
    working["feature_pre_promo_cover_ratio"] = latent_a
    working["feature_inventory_sufficiency_flag"] = latent_a.ge(1.7).astype("float64")
    working["feature_units_above_trust_floor"] = 5.0 + (latent_a * 4.0) + (latent_b * 2.0)
    working["feature_expected_residual_stock_units"] = 2.0 + (latent_a * 2.5) + latent_b
    working["feature_expected_bill_cycle_capital_drag_ratio"] = (0.08 + (latent_a * 0.05) + (latent_b * 0.04)).clip(0.0, 0.95)
    working["feature_expected_gp_per_capital_committed"] = (0.18 + (latent_a * 0.04) - (latent_b * 0.03)).clip(0.02, 0.95)
    working["feature_capital_at_risk_per_expected_unit"] = 2.5 + (latent_a * 0.8) + (latent_b * 1.8)
    working["feature_gross_profit_per_incremental_unit_expected"] = 0.6 + (latent_a * 0.2) - (latent_b * 0.08)
    working["feature_trust_floor_missed_demand_risk_score"] = (0.16 + (latent_b * 0.4) - (latent_a * 0.02)).clip(0.0, 1.0)
    working["feature_historical_allocation_efficiency_rate"] = (0.58 + (latent_a * 0.04) - (latent_b * 0.05)).clip(0.0, 1.0)
    working["feature_historical_overallocation_above_floor_rate"] = (0.28 - (latent_a * 0.02) + (latent_b * 0.08)).clip(0.0, 1.0)
    if outlier_rows:
        row_index = list(outlier_rows)
        working.loc[row_index, "feature_pre_promo_cover_ratio"] = 0.15
        working.loc[row_index, "feature_inventory_sufficiency_flag"] = 0.0
        working.loc[row_index, "feature_units_above_trust_floor"] = 0.25
        working.loc[row_index, "feature_expected_residual_stock_units"] = 18.0
        working.loc[row_index, "feature_expected_bill_cycle_capital_drag_ratio"] = 0.98
        working.loc[row_index, "feature_expected_gp_per_capital_committed"] = 0.01
        working.loc[row_index, "feature_capital_at_risk_per_expected_unit"] = 18.0
        working.loc[row_index, "feature_gross_profit_per_incremental_unit_expected"] = 0.05
        working.loc[row_index, "feature_trust_floor_missed_demand_risk_score"] = 0.96
        working.loc[row_index, "feature_historical_allocation_efficiency_rate"] = 0.05
        working.loc[row_index, "feature_historical_overallocation_above_floor_rate"] = 0.94
    return working


def _build_completed_reference_frame() -> pd.DataFrame:
    base = build_completed_promotions_base_frame()
    repeated = pd.concat([base.copy() for _ in range(4)], ignore_index=True)
    return _with_pca_source_columns(repeated, seed_offset=0.0)


class PromotionPcaResidualStructureFeatureTests(unittest.TestCase):
    def test_pca_residual_structure_scores_stable_rows_and_flags_outlier(self) -> None:
        reference_frame = _with_pca_source_columns(
            _build_date_only_frame(30, start_date="2024-01-01"),
            seed_offset=0.0,
        )
        candidate_frame = _with_pca_source_columns(
            _build_date_only_frame(2, start_date="2024-10-01"),
            seed_offset=10.0,
            outlier_rows=(1,),
        )

        result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=reference_frame)

        self.assertEqual(
            list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS),
            [column_name for column_name in PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS if column_name in result.columns],
        )
        self.assertLess(result.loc[0, "feature_pca_structure_residual_score"], 0.35)
        self.assertGreater(result.loc[0, "feature_pca_structure_fit_score"], 0.65)
        self.assertEqual(result.loc[0, "feature_pca_structure_outlier_flag"], 0.0)
        self.assertEqual(result.loc[0, "feature_pca_allocation_outlier_flag"], 0.0)
        self.assertEqual(result.loc[1, "feature_pca_structure_outlier_flag"], 1.0)
        self.assertEqual(result.loc[1, "feature_pca_allocation_outlier_flag"], 1.0)
        self.assertGreater(
            result.loc[1, "feature_pca_structure_residual_score"],
            result.loc[0, "feature_pca_structure_residual_score"],
        )
        self.assertLess(
            result.loc[1, "feature_pca_structure_fit_score"],
            result.loc[0, "feature_pca_structure_fit_score"],
        )

    def test_pca_residual_structure_ignores_non_prior_reference_rows(self) -> None:
        reference_frame = _with_pca_source_columns(
            _build_date_only_frame(30, start_date="2024-01-01"),
            seed_offset=0.0,
        )
        candidate_frame = _with_pca_source_columns(
            _build_date_only_frame(1, start_date="2024-10-01"),
            seed_offset=8.0,
        )
        non_prior_leak_row = _with_pca_source_columns(
            _build_date_only_frame(1, start_date="2024-10-08"),
            seed_offset=50.0,
            outlier_rows=(0,),
        )
        leaky_reference = pd.concat([reference_frame, non_prior_leak_row], ignore_index=True)

        safe_result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=reference_frame)
        leaky_result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=leaky_reference)

        pd.testing.assert_frame_equal(
            safe_result.loc[:, PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS],
            leaky_result.loc[:, PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS],
            check_dtype=False,
        )

    def test_pca_residual_structure_is_invariant_to_target_row_outcomes(self) -> None:
        reference_frame = _with_pca_source_columns(
            _build_date_only_frame(30, start_date="2024-01-01"),
            seed_offset=0.0,
        )
        candidate_frame = _with_pca_source_columns(
            _build_date_only_frame(1, start_date="2024-10-01"),
            seed_offset=11.0,
        )
        altered_outcome_frame = candidate_frame.copy()
        altered_outcome_frame.loc[:, "actual_units_sold"] = 9999.0

        baseline_result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=reference_frame)
        altered_result = apply_ft_pca_residual_structure(altered_outcome_frame, reference_frame=reference_frame)

        pd.testing.assert_frame_equal(
            baseline_result.loc[:, PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS],
            altered_result.loc[:, PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS],
            check_dtype=False,
        )

    def test_pca_residual_structure_returns_unavailable_when_reference_is_insufficient(self) -> None:
        reference_frame = _with_pca_source_columns(
            _build_date_only_frame(8, start_date="2024-01-01"),
            seed_offset=0.0,
        )
        candidate_frame = _with_pca_source_columns(
            _build_date_only_frame(1, start_date="2024-10-01"),
            seed_offset=10.0,
        )

        result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=reference_frame)

        self.assertTrue(result.loc[0, list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS)].isna().all())

    def test_pca_residual_structure_returns_unavailable_when_candidate_inputs_are_missing(self) -> None:
        reference_frame = _with_pca_source_columns(
            _build_date_only_frame(30, start_date="2024-01-01"),
            seed_offset=0.0,
        )
        candidate_frame = _with_pca_source_columns(
            _build_date_only_frame(2, start_date="2024-10-01"),
            seed_offset=10.0,
        )
        candidate_frame.loc[1, "feature_expected_residual_stock_units"] = np.nan

        result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=reference_frame)

        self.assertFalse(result.loc[0, list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS)].isna().all())
        self.assertTrue(result.loc[1, list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS)].isna().all())

    def test_pca_residual_structure_returns_unavailable_when_explicit_reference_is_raw(self) -> None:
        candidate_frame = _with_pca_source_columns(
            _build_date_only_frame(30, start_date="2024-01-01"),
            seed_offset=0.0,
        )
        raw_reference_frame = candidate_frame.loc[:, [
            "promotion_start_date_date",
            "promotional_end_date_date",
            "actual_units_sold",
        ]].copy()

        result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=raw_reference_frame)

        self.assertTrue(result.loc[:, list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS)].isna().all(axis=None))

    def test_pca_residual_structure_does_not_fit_from_future_candidate_rows_when_explicit_reference_is_unusable(self) -> None:
        candidate_frame = _with_pca_source_columns(
            _build_date_only_frame(2, start_date="2024-10-01"),
            seed_offset=15.0,
        )
        raw_reference_frame = candidate_frame.loc[:, [
            "promotion_start_date_date",
            "promotional_end_date_date",
            "actual_units_sold",
        ]].copy()

        result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=raw_reference_frame)

        self.assertTrue(result.loc[0, list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS)].isna().all())
        self.assertTrue(result.loc[1, list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS)].isna().all())

    def test_pca_residual_structure_returns_unavailable_when_explicit_reference_lacks_required_features(self) -> None:
        reference_frame = _with_pca_source_columns(
            _build_date_only_frame(30, start_date="2024-01-01"),
            seed_offset=0.0,
        ).drop(columns=[
            "feature_expected_residual_stock_units",
            "feature_trust_floor_missed_demand_risk_score",
        ])
        candidate_frame = _with_pca_source_columns(
            _build_date_only_frame(2, start_date="2024-10-01"),
            seed_offset=12.0,
        )

        result = apply_ft_pca_residual_structure(candidate_frame, reference_frame=reference_frame)

        self.assertTrue(result.loc[:, list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS)].isna().all(axis=None))

    def test_pca_residual_structure_registry_quality_and_pipeline_contracts(self) -> None:
        registered_modules = list(iter_registered_feature_modules())
        registered_module_names = [definition.name for definition in registered_modules]
        default_model_use_columns = set(iter_default_model_use_feature_columns())

        self.assertIn("ft_pca_residual_structure", registered_module_names)
        self.assertLess(
            registered_module_names.index("ft_allocation_discipline"),
            registered_module_names.index("ft_pca_residual_structure"),
        )
        self.assertLess(
            registered_module_names.index("ft_pca_residual_structure"),
            registered_module_names.index("ft_order_decision_diagnostics"),
        )
        self.assertTrue(
            set(PCA_RESIDUAL_STRUCTURE_REVIEW_ONLY_FEATURE_COLUMNS).issubset(BOUNDED_ZERO_ONE_COLUMNS)
        )
        self.assertTrue(
            set(PCA_RESIDUAL_STRUCTURE_REVIEW_ONLY_FEATURE_COLUMNS).isdisjoint(default_model_use_columns)
        )

        candidate_frame = build_future_promotions_base_frame().copy()
        candidate_frame = _with_pca_source_columns(candidate_frame, seed_offset=12.0)
        reference_frame = _build_completed_reference_frame()
        result = PromotionFeatureEngineer().engineer(
            candidate_frame,
            historical_reference_frame=reference_frame,
            selected_modules=("ft_pca_residual_structure",),
        )

        self.assertEqual(result.applied_modules, ("ft_pca_residual_structure",))
        self.assertTrue(set(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS).issubset(result.frame.columns))
        self.assertFalse(result.frame.loc[:, list(PCA_RESIDUAL_STRUCTURE_FEATURE_COLUMNS)].isna().all(axis=None))


if __name__ == "__main__":
    unittest.main()