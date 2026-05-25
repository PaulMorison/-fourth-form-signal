from __future__ import annotations

"""Kuramoto-style synchronisation ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import bounded_score, ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_kuramoto_sync(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add store-network and baseline-promo synchronisation features."""

    del reference_frame
    working = frame.copy()
    baseline_daily = ensure_numeric_series(working, "baseline_daily_units")
    baseline_trend = safe_ratio(
        ensure_numeric_series(working, "pre_7d_avg_daily_units")
        - ensure_numeric_series(working, "pre_prior_21d_avg_daily_units"),
        baseline_daily,
    )
    expected_lift = safe_ratio(
        ensure_numeric_series(working, "required_implied_units")
        - ensure_numeric_series(working, "baseline_expected_units"),
        ensure_numeric_series(working, "baseline_expected_units"),
    )
    store_sync_gap = (
        ensure_numeric_series(working, "feature_prior_promo_response_same_sku_store")
        - ensure_numeric_series(working, "feature_prior_promo_response_same_sku_network")
    ).abs()
    short_long_phase_gap = (
        safe_ratio(
            ensure_numeric_series(working, "pre_7d_avg_daily_units"),
            ensure_numeric_series(working, "pre_56d_avg_daily_units"),
        )
        - safe_ratio(
            ensure_numeric_series(working, "pre_28d_avg_daily_units"),
            ensure_numeric_series(working, "pre_56d_avg_daily_units"),
        )
    ).abs()
    promo_window_gap = (
        safe_ratio(
            ensure_numeric_series(working, "tot_days_cover"),
            ensure_numeric_series(working, "live_promo_window_days").where(
                lambda values: values > 0.0,
                ensure_numeric_series(working, "promo_days"),
            ),
        )
        - ensure_numeric_series(working, "required_implied_multiple")
    ).abs()
    category_sync = bounded_score(
        (
            ensure_numeric_series(working, "feature_category_share_in_store")
            - ensure_numeric_series(working, "feature_store_baseline_share_in_event")
        ).abs()
    )
    store_sync = bounded_score(store_sync_gap)
    short_long_alignment = bounded_score(short_long_phase_gap)
    promo_window_alignment = bounded_score(promo_window_gap)
    misalignment_penalty = 1.0 - (
        short_long_alignment + promo_window_alignment + category_sync + store_sync
    ) / 4.0
    working["feature_short_long_demand_phase_alignment"] = short_long_alignment
    working["feature_promo_window_alignment_score"] = promo_window_alignment
    working["feature_category_sync_score"] = category_sync
    working["feature_store_sync_score"] = store_sync
    working["feature_sync_misalignment_penalty"] = misalignment_penalty.clip(lower=0.0)
    working["feature_store_category_synchronisation_score"] = category_sync
    working["feature_network_synchronisation_score"] = store_sync
    working["feature_desynchronisation_score"] = misalignment_penalty.clip(lower=0.0)
    working["feature_demand_wave_alignment_score"] = bounded_score((baseline_trend - expected_lift).abs())
    return working
