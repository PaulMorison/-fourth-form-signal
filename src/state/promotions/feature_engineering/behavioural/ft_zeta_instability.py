from __future__ import annotations

"""Zeta-style instability ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_zeta_instability(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add measurable instability and fragility features around the promo boundary."""

    del reference_frame
    working = frame.copy()
    baseline_daily = ensure_numeric_series(working, "baseline_daily_units")
    baseline_trend = safe_ratio(
        ensure_numeric_series(working, "pre_7d_avg_daily_units")
        - ensure_numeric_series(working, "pre_prior_21d_avg_daily_units"),
        baseline_daily,
    )
    promo_instability = safe_ratio(
        ensure_numeric_series(working, "actual_std_daily_units"),
        ensure_numeric_series(working, "actual_avg_daily_units"),
    )
    expected_lift = safe_ratio(
        ensure_numeric_series(working, "required_implied_units")
        - ensure_numeric_series(working, "baseline_expected_units"),
        ensure_numeric_series(working, "baseline_expected_units"),
    )
    baseline_instability = safe_ratio(
        (
            ensure_numeric_series(working, "pre_7d_avg_daily_units")
            - ensure_numeric_series(working, "pre_56d_avg_daily_units")
        ).abs(),
        ensure_numeric_series(working, "pre_56d_avg_daily_units"),
    )
    margin_fragility = (
        ensure_numeric_series(working, "feature_effective_margin_compression_pct").abs()
        * ensure_numeric_series(working, "feature_discount_depth_pct")
    )
    stock_fragility = (
        ensure_numeric_series(working, "feature_allocation_vs_required_implied_demand_ratio") - 1.0
    ).abs()
    working["feature_demand_regime_instability_before_promo"] = baseline_trend.abs()
    working["feature_realised_during_promo_instability"] = promo_instability.where(
        promo_instability > 0.0,
        ensure_numeric_series(working, "feature_baseline_volatility_cv"),
    )
    working["feature_baseline_to_promo_transition_volatility"] = safe_ratio(
        (ensure_numeric_series(working, "actual_avg_daily_units") - baseline_daily).abs(),
        baseline_daily,
    ).where(
        ensure_numeric_series(working, "actual_avg_daily_units") > 0.0,
        expected_lift.abs(),
    )
    working["feature_boundary_volatility_clustering_score"] = (
        working["feature_demand_regime_instability_before_promo"]
        * ensure_numeric_series(working, "feature_baseline_volatility_cv")
    )
    working["feature_uplift_fragility_score"] = (
        expected_lift.abs() * ensure_numeric_series(working, "feature_baseline_volatility_cv")
    )
    working["feature_baseline_instability_ratio"] = baseline_instability
    working["feature_margin_fragility_score"] = margin_fragility
    working["feature_stock_fragility_score"] = stock_fragility
    working["feature_composite_promo_instability"] = (
        baseline_instability
        + working["feature_uplift_fragility_score"]
        + margin_fragility
        + stock_fragility
    ) / 4.0
    return working
