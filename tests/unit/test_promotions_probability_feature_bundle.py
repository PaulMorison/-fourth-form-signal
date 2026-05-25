from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from state.promotions.datasets.model_input_export import _round_for_export  # noqa: E402
from state.promotions.feature_engineering.demand.probability.ft_probability_bayesian_poisson_features import (  # noqa: E402
    build_probability_bayesian_poisson_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_companion_features import (  # noqa: E402
    build_probability_companion_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_feature_bundle import (  # noqa: E402
    PROBABILITY_FEATURE_BUNDLE_COLUMNS,
    PROBABILITY_MODEL_USE_FEATURE_COLUMNS,
    PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS,
    apply_ft_probability_feature_bundle,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_hypothesis_test_features import (  # noqa: E402
    build_probability_hypothesis_test_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_negative_binomial_features import (  # noqa: E402
    build_probability_negative_binomial_features,
)
from state.promotions.feature_engineering.demand.probability.ft_probability_zero_inflated_features import (  # noqa: E402
    build_probability_zero_inflated_features,
)


def _summary_row(**overrides: float) -> dict[str, float]:
    row: dict[str, float] = {
        "probability_same_discount_event_count": 0.0,
        "probability_same_or_better_event_count": 0.0,
        "probability_same_discount_units_sum": float("nan"),
        "probability_same_or_better_units_sum": float("nan"),
        "probability_same_discount_units_mean": float("nan"),
        "probability_same_or_better_units_mean": float("nan"),
        "probability_same_discount_units_variance": float("nan"),
        "probability_same_or_better_units_variance": float("nan"),
        "probability_same_or_better_zero_count": float("nan"),
        "probability_same_or_better_zero_rate": float("nan"),
        "probability_days_since_last_same_or_better_promo": float("nan"),
        "probability_order_threshold_units": float("nan"),
        "probability_stock_basis_units": float("nan"),
        "probability_baseline_prior_mean_units": float("nan"),
        "probability_promo_window_days": float("nan"),
        "probability_bayesian_prior_rate": float("nan"),
        "probability_bayesian_prior_event_count": 0.0,
        "probability_bayesian_recent_units_sum": 0.0,
        "probability_bayesian_recent_event_count": 0.0,
        "probability_bayesian_recent_mean_units": float("nan"),
        "probability_bayesian_recent_variance": float("nan"),
        "probability_units_lift_mean": float("nan"),
        "probability_units_lift_variance": float("nan"),
        "probability_units_lift_sample_size": 0.0,
        "probability_basket_attach_rate_lift_mean": float("nan"),
        "probability_basket_attach_rate_lift_variance": float("nan"),
        "probability_basket_attach_rate_lift_sample_size": 0.0,
        "probability_same_discount_response_mean": float("nan"),
        "probability_same_discount_response_variance": float("nan"),
        "probability_same_discount_response_sample_size": 0.0,
        "probability_sold_in_multi_item_basket_rate": float("nan"),
        "probability_sold_as_solo_item_rate": float("nan"),
        "probability_companion_dependency_score_prior_mean": float("nan"),
        "probability_basket_depth_when_sold_mean": float("nan"),
        "probability_companion_overallocation_risk_proxy": float("nan"),
    }
    row.update(overrides)
    return row


def _raw_row(
    *,
    store: int,
    sku: int,
    start: date,
    end: date,
    discount_percent: float,
    actual_units_sold_promo: float = 0.0,
    baseline_expected_units: float = 2.0,
    baseline_daily_units: float = 0.5,
    live_promo_window_days: float = 7.0,
    pl_allocated: float = 4.0,
    stock_basis_units: float = 5.0,
    transaction_count: float | None = None,
    multi_item_transaction_count: float | None = None,
    solo_transaction_count: float | None = None,
    basket_depth_when_sold: float = 1.0,
    top_companion_sku_1_share: float = 0.0,
    top_companion_sku_2_share: float = 0.0,
    companion_concentration_index: float = 0.0,
) -> dict[str, object]:
    resolved_transaction_count = (
        transaction_count
        if transaction_count is not None
        else (max(int(actual_units_sold_promo // 2), 1) if actual_units_sold_promo > 0.0 else 0.0)
    )
    resolved_multi_item_transaction_count = (
        multi_item_transaction_count
        if multi_item_transaction_count is not None
        else float(resolved_transaction_count) * 0.5
    )
    resolved_solo_transaction_count = (
        solo_transaction_count
        if solo_transaction_count is not None
        else max(float(resolved_transaction_count) - float(resolved_multi_item_transaction_count), 0.0)
    )
    return {
        "promotion_row_key": f"{store}|{sku}|{start.isoformat()}|{end.isoformat()}",
        "store_number_key": store,
        "sku_number_key": sku,
        "promotion_start_date_date": start.isoformat(),
        "promotional_end_date_date": end.isoformat(),
        "discount_percent": discount_percent,
        "actual_units_sold_promo": actual_units_sold_promo,
        "baseline_expected_units": baseline_expected_units,
        "baseline_daily_units": baseline_daily_units,
        "live_promo_window_days": live_promo_window_days,
        "pl_allocated": pl_allocated,
        "stock_basis_units": stock_basis_units,
        "realised_transaction_count": resolved_transaction_count,
        "realised_promo_transaction_count": resolved_transaction_count,
        "actual_transaction_count_promo": resolved_transaction_count,
        "realised_sku_solo_transaction_count": resolved_solo_transaction_count,
        "realised_sku_multi_item_transaction_count": resolved_multi_item_transaction_count,
        "realised_basket_item_count_sum_when_sku_present": basket_depth_when_sold
        * float(resolved_transaction_count),
        "realised_top_companion_sku_1_share": top_companion_sku_1_share,
        "realised_top_companion_sku_2_share": top_companion_sku_2_share,
        "realised_companion_concentration_index": companion_concentration_index,
    }


class NegativeBinomialProbabilityFeatureTests(unittest.TestCase):
    def test_lumpy_history_emits_new_negative_binomial_contract(self) -> None:
        summary = pd.DataFrame(
            [
                _summary_row(
                    probability_same_or_better_event_count=5.0,
                    probability_same_or_better_units_mean=4.0,
                    probability_same_or_better_units_variance=20.0,
                    probability_order_threshold_units=6.0,
                )
            ]
        )

        features = build_probability_negative_binomial_features(summary).iloc[0]

        self.assertAlmostEqual(features["feature_probability_negative_binomial_expected_units"], 4.0)
        self.assertGreater(features["feature_probability_negative_binomial_dispersion_score"], 0.0)
        self.assertGreater(features["feature_probability_negative_binomial_zero_sale_probability"], 0.0)
        self.assertLessEqual(features["feature_probability_negative_binomial_tail_probability"], 1.0)
        self.assertLessEqual(
            features["feature_probability_negative_binomial_overallocation_risk_score"],
            1.0,
        )


class BayesianPoissonProbabilityFeatureTests(unittest.TestCase):
    def test_recent_evidence_updates_the_bayesian_posterior(self) -> None:
        summary = pd.DataFrame(
            [
                _summary_row(
                    probability_bayesian_prior_rate=1.0,
                    probability_bayesian_prior_event_count=2.0,
                    probability_bayesian_recent_units_sum=6.0,
                    probability_bayesian_recent_event_count=2.0,
                    probability_order_threshold_units=4.0,
                )
            ]
        )

        features = build_probability_bayesian_poisson_features(summary).iloc[0]

        self.assertAlmostEqual(features["feature_probability_bayesian_poisson_prior_rate"], 1.0)
        self.assertAlmostEqual(features["feature_probability_bayesian_poisson_posterior_rate"], 2.0)
        self.assertAlmostEqual(features["feature_probability_bayesian_poisson_expected_units"], 2.0)
        self.assertGreater(features["feature_probability_bayesian_poisson_tail_probability"], 0.0)
        self.assertGreater(features["feature_probability_bayesian_poisson_confidence_score"], 0.0)


class ZeroInflatedProbabilityFeatureTests(unittest.TestCase):
    def test_many_zero_history_emits_zero_inflated_features(self) -> None:
        summary = pd.DataFrame(
            [
                _summary_row(
                    probability_same_or_better_event_count=6.0,
                    probability_same_or_better_units_mean=0.5,
                    probability_same_or_better_zero_rate=5.0 / 6.0,
                    probability_order_threshold_units=2.0,
                )
            ]
        )

        features = build_probability_zero_inflated_features(summary).iloc[0]

        self.assertGreater(features["feature_probability_zero_inflation_rate"], 0.5)
        self.assertAlmostEqual(features["feature_probability_zero_inflated_expected_units"], 0.5)
        self.assertAlmostEqual(
            features["feature_probability_zero_inflated_nonzero_probability"],
            1.0 - features["feature_probability_zero_inflated_zero_sale_probability"],
        )
        self.assertGreater(features["feature_probability_zero_inflated_overallocation_risk_score"], 0.0)


class HypothesisAndCompanionProbabilityFeatureTests(unittest.TestCase):
    def test_hypothesis_and_companion_outputs_are_bounded_and_explainable(self) -> None:
        summary = pd.DataFrame(
            [
                _summary_row(
                    probability_units_lift_mean=2.0,
                    probability_units_lift_variance=1.0,
                    probability_units_lift_sample_size=4.0,
                    probability_basket_attach_rate_lift_mean=0.30,
                    probability_basket_attach_rate_lift_variance=0.01,
                    probability_basket_attach_rate_lift_sample_size=4.0,
                    probability_same_discount_response_mean=1.5,
                    probability_same_discount_response_variance=0.25,
                    probability_same_discount_response_sample_size=4.0,
                    probability_sold_in_multi_item_basket_rate=0.75,
                    probability_sold_as_solo_item_rate=0.25,
                    probability_companion_dependency_score_prior_mean=0.60,
                    probability_basket_depth_when_sold_mean=3.2,
                    probability_companion_overallocation_risk_proxy=0.55,
                )
            ]
        )

        hypothesis_features = build_probability_hypothesis_test_features(summary).iloc[0]
        companion_features = build_probability_companion_features(summary).iloc[0]

        self.assertAlmostEqual(hypothesis_features["feature_units_lift_effect_size"], 2.0)
        self.assertGreaterEqual(hypothesis_features["feature_units_lift_p_value"], 0.0)
        self.assertLessEqual(hypothesis_features["feature_units_lift_p_value"], 1.0)
        self.assertGreater(hypothesis_features["feature_units_lift_stability_score"], 0.0)
        self.assertGreater(hypothesis_features["feature_same_discount_repeatability_score"], 0.0)
        self.assertAlmostEqual(
            companion_features["feature_probability_sold_in_multi_item_basket_rate"],
            0.75,
        )
        self.assertAlmostEqual(
            companion_features["feature_probability_companion_dependency_score"],
            0.60,
        )
        self.assertGreater(
            companion_features["feature_probability_companion_overallocation_risk_score"],
            0.0,
        )


class ProbabilityFeatureBundleTests(unittest.TestCase):
    def test_bundle_respects_strict_prior_cutoff_and_preserves_rows(self) -> None:
        prior_included = _raw_row(
            store=1,
            sku=100,
            start=date(2024, 1, 1),
            end=date(2024, 1, 6),
            discount_percent=20.0,
            actual_units_sold_promo=2.0,
            baseline_expected_units=2.0,
            transaction_count=2.0,
            multi_item_transaction_count=1.0,
            solo_transaction_count=1.0,
            basket_depth_when_sold=2.0,
            top_companion_sku_1_share=0.4,
            companion_concentration_index=0.5,
        )
        prior_excluded = _raw_row(
            store=1,
            sku=100,
            start=date(2024, 1, 2),
            end=date(2024, 1, 7),
            discount_percent=20.0,
            actual_units_sold_promo=8.0,
            baseline_expected_units=2.0,
        )
        candidate = _raw_row(
            store=1,
            sku=100,
            start=date(2024, 1, 7),
            end=date(2024, 1, 13),
            discount_percent=20.0,
            baseline_expected_units=2.0,
        )

        result = apply_ft_probability_feature_bundle(
            pd.DataFrame([prior_included, prior_excluded, candidate])
        )

        self.assertEqual(len(result.index), 3)
        candidate_row = result.iloc[-1]
        self.assertAlmostEqual(candidate_row["feature_probability_expected_units_consensus"], 2.0)
        self.assertEqual(candidate_row["feature_probability_model_use_flag"], 1.0)

    def test_bundle_overallocation_risk_rises_with_zero_heavy_companion_dependence(self) -> None:
        reference = pd.DataFrame(
            [
                _raw_row(
                    store=1,
                    sku=100,
                    start=date(2024, 1, 1),
                    end=date(2024, 1, 7),
                    discount_percent=20.0,
                    actual_units_sold_promo=7.0,
                    baseline_expected_units=7.0,
                    pl_allocated=7.0,
                    transaction_count=4.0,
                    multi_item_transaction_count=1.0,
                    solo_transaction_count=3.0,
                    basket_depth_when_sold=1.3,
                    top_companion_sku_1_share=0.15,
                    companion_concentration_index=0.20,
                ),
                _raw_row(
                    store=1,
                    sku=100,
                    start=date(2024, 2, 1),
                    end=date(2024, 2, 7),
                    discount_percent=20.0,
                    actual_units_sold_promo=8.0,
                    baseline_expected_units=7.0,
                    pl_allocated=7.0,
                    transaction_count=4.0,
                    multi_item_transaction_count=1.0,
                    solo_transaction_count=3.0,
                    basket_depth_when_sold=1.2,
                    top_companion_sku_1_share=0.10,
                    companion_concentration_index=0.18,
                ),
                _raw_row(
                    store=1,
                    sku=100,
                    start=date(2024, 3, 1),
                    end=date(2024, 3, 7),
                    discount_percent=20.0,
                    actual_units_sold_promo=6.0,
                    baseline_expected_units=7.0,
                    pl_allocated=7.0,
                    transaction_count=4.0,
                    multi_item_transaction_count=1.0,
                    solo_transaction_count=3.0,
                    basket_depth_when_sold=1.2,
                    top_companion_sku_1_share=0.12,
                    companion_concentration_index=0.18,
                ),
                _raw_row(
                    store=1,
                    sku=100,
                    start=date(2024, 4, 1),
                    end=date(2024, 4, 7),
                    discount_percent=20.0,
                    actual_units_sold_promo=7.0,
                    baseline_expected_units=7.0,
                    pl_allocated=7.0,
                    transaction_count=4.0,
                    multi_item_transaction_count=1.0,
                    solo_transaction_count=3.0,
                    basket_depth_when_sold=1.4,
                    top_companion_sku_1_share=0.16,
                    companion_concentration_index=0.22,
                ),
                _raw_row(
                    store=1,
                    sku=101,
                    start=date(2024, 1, 1),
                    end=date(2024, 1, 7),
                    discount_percent=20.0,
                    actual_units_sold_promo=0.0,
                    baseline_expected_units=2.0,
                    pl_allocated=6.0,
                    transaction_count=0.0,
                ),
                _raw_row(
                    store=1,
                    sku=101,
                    start=date(2024, 2, 1),
                    end=date(2024, 2, 7),
                    discount_percent=20.0,
                    actual_units_sold_promo=0.0,
                    baseline_expected_units=2.0,
                    pl_allocated=6.0,
                    transaction_count=0.0,
                ),
                _raw_row(
                    store=1,
                    sku=101,
                    start=date(2024, 3, 1),
                    end=date(2024, 3, 7),
                    discount_percent=20.0,
                    actual_units_sold_promo=2.0,
                    baseline_expected_units=2.0,
                    pl_allocated=6.0,
                    transaction_count=2.0,
                    multi_item_transaction_count=2.0,
                    solo_transaction_count=0.0,
                    basket_depth_when_sold=3.6,
                    top_companion_sku_1_share=0.55,
                    top_companion_sku_2_share=0.25,
                    companion_concentration_index=0.70,
                ),
                _raw_row(
                    store=1,
                    sku=101,
                    start=date(2024, 4, 1),
                    end=date(2024, 4, 7),
                    discount_percent=20.0,
                    actual_units_sold_promo=0.0,
                    baseline_expected_units=2.0,
                    pl_allocated=6.0,
                    transaction_count=0.0,
                ),
            ]
        )
        candidates = pd.DataFrame(
            [
                _raw_row(
                    store=1,
                    sku=100,
                    start=date(2024, 6, 1),
                    end=date(2024, 6, 7),
                    discount_percent=20.0,
                    baseline_expected_units=7.0,
                    pl_allocated=7.0,
                ),
                _raw_row(
                    store=1,
                    sku=101,
                    start=date(2024, 6, 1),
                    end=date(2024, 6, 7),
                    discount_percent=20.0,
                    baseline_expected_units=2.0,
                    pl_allocated=6.0,
                ),
            ]
        )

        result = apply_ft_probability_feature_bundle(candidates, reference_frame=reference)

        stable_row = result.iloc[0]
        risky_row = result.iloc[1]
        self.assertLess(
            stable_row["feature_probability_overallocation_risk_score"],
            risky_row["feature_probability_overallocation_risk_score"],
        )
        self.assertLess(
            stable_row["feature_probability_companion_overallocation_risk_score"],
            risky_row["feature_probability_companion_overallocation_risk_score"],
        )
        self.assertGreater(risky_row["feature_probability_zero_inflation_rate"], 0.0)

    def test_bundle_has_unique_columns_and_explicit_model_use_split(self) -> None:
        self.assertEqual(len(PROBABILITY_FEATURE_BUNDLE_COLUMNS), len(set(PROBABILITY_FEATURE_BUNDLE_COLUMNS)))
        self.assertFalse(set(PROBABILITY_MODEL_USE_FEATURE_COLUMNS) & set(PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS))
        self.assertTrue(set(PROBABILITY_MODEL_USE_FEATURE_COLUMNS) <= set(PROBABILITY_FEATURE_BUNDLE_COLUMNS))
        self.assertTrue(set(PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS) <= set(PROBABILITY_FEATURE_BUNDLE_COLUMNS))

    def test_bundle_export_view_rounds_probability_outputs_to_four_decimals(self) -> None:
        prior = _raw_row(
            store=1,
            sku=100,
            start=date(2024, 1, 1),
            end=date(2024, 1, 6),
            discount_percent=20.0,
            actual_units_sold_promo=2.0,
            baseline_expected_units=2.0,
            transaction_count=2.0,
            multi_item_transaction_count=1.0,
            solo_transaction_count=1.0,
            basket_depth_when_sold=2.0,
            top_companion_sku_1_share=0.4,
            companion_concentration_index=0.5,
        )
        candidate = _raw_row(
            store=1,
            sku=100,
            start=date(2024, 1, 7),
            end=date(2024, 1, 13),
            discount_percent=20.0,
            baseline_expected_units=2.0,
        )

        result = apply_ft_probability_feature_bundle(pd.DataFrame([prior, candidate]))
        rounded = _round_for_export(
            result.loc[
                [result.index[-1]],
                [
                    "feature_probability_zero_sale_consensus",
                    "feature_probability_demand_confidence_score",
                ],
            ]
        )

        self.assertAlmostEqual(
            rounded.iloc[0]["feature_probability_zero_sale_consensus"],
            0.1353,
            places=4,
        )
        self.assertEqual(
            rounded.iloc[0]["feature_probability_demand_confidence_score"],
            round(result.iloc[-1]["feature_probability_demand_confidence_score"], 4),
        )

    def test_bundle_leaves_unsupported_outputs_blank_without_inf(self) -> None:
        candidates = pd.DataFrame(
            [
                _raw_row(
                    store=1,
                    sku=999,
                    start=date(2024, 6, 1),
                    end=date(2024, 6, 7),
                    discount_percent=20.0,
                    baseline_expected_units=1.5,
                    pl_allocated=4.0,
                )
            ]
        )

        result = apply_ft_probability_feature_bundle(candidates)
        row = result.iloc[0]

        self.assertTrue(pd.isna(row["feature_probability_poisson_zero_sale_probability"]))
        self.assertTrue(pd.isna(row["feature_probability_negative_binomial_zero_sale_probability"]))
        self.assertTrue(pd.isna(row["feature_probability_zero_inflated_zero_sale_probability"]))
        probability_columns = [
            column_name for column_name in result.columns if column_name.startswith("feature_probability_")
        ]
        self.assertFalse(
            np.isinf(result.loc[:, probability_columns].to_numpy(dtype=float, na_value=np.nan)).any()
        )


if __name__ == "__main__":
    unittest.main()