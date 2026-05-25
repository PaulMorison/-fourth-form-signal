from __future__ import annotations

"""Deterministic archetype signature construction for promotions cohorts."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


ARCHETYPE_REGIME_COLUMNS = (
    "archetype_discount_depth_regime",
    "archetype_price_gap_regime",
    "archetype_offer_mechanic_regime",
    "archetype_margin_pressure_regime",
    "archetype_rebate_dependency_regime",
    "archetype_stock_pressure_regime",
    "archetype_allocation_pressure_regime",
    "archetype_overhang_risk_regime",
    "archetype_baseline_demand_regime",
    "archetype_demand_acceleration_regime",
    "archetype_zeta_instability_regime",
    "archetype_kuramoto_sync_regime",
    "archetype_gravity_regime",
    "archetype_field_density_regime",
    "archetype_context_regime",
)

PRIMARY_SIGNATURE_COLUMNS = (
    "archetype_discount_depth_regime",
    "archetype_offer_mechanic_regime",
    "archetype_margin_pressure_regime",
    "archetype_stock_pressure_regime",
    "archetype_baseline_demand_regime",
    "archetype_zeta_instability_regime",
)

SECONDARY_SIGNATURE_COLUMNS = ARCHETYPE_REGIME_COLUMNS

ORDERED_REGIME_LEVELS: dict[str, tuple[str, ...]] = {
    "archetype_discount_depth_regime": ("shallow", "moderate", "deep", "extreme"),
    "archetype_price_gap_regime": ("narrow", "meaningful", "wide", "aggressive"),
    "archetype_margin_pressure_regime": ("light", "compressed", "high", "critical"),
    "archetype_rebate_dependency_regime": ("low", "moderate", "high", "extreme"),
    "archetype_stock_pressure_regime": ("tight", "balanced", "buffered", "heavy"),
    "archetype_allocation_pressure_regime": ("lean", "aligned", "buffered", "surplus"),
    "archetype_overhang_risk_regime": ("low", "moderate", "high", "severe"),
    "archetype_baseline_demand_regime": ("low", "steady", "elevated", "intense"),
    "archetype_demand_acceleration_regime": ("cooling", "flat", "building", "surging"),
    "archetype_zeta_instability_regime": ("calm", "elevated", "fragile", "critical"),
    "archetype_kuramoto_sync_regime": ("desynchronised", "mixed", "aligned", "high_sync"),
    "archetype_gravity_regime": ("light", "moderate", "heavy", "extreme"),
    "archetype_field_density_regime": ("sparse", "active", "crowded", "saturated"),
    "archetype_context_regime": ("localised", "shared", "dense", "networked"),
}

CATEGORICAL_REGIME_COLUMNS = ("archetype_offer_mechanic_regime",)


def _ordered_bucket(
    series: pd.Series,
    *,
    thresholds: tuple[float, float, float],
    labels: tuple[str, str, str, str],
    absolute_value: bool = False,
) -> pd.Series:
    values = series.abs() if absolute_value else series
    bucketed = pd.cut(
        values,
        bins=[float("-inf"), *thresholds, float("inf")],
        labels=list(labels),
        right=False,
    )
    return bucketed.astype("object").where(~series.isna(), "unknown").fillna("unknown")


def _mean_anchor(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    return pd.concat(
        [ensure_numeric_series(frame, column_name) for column_name in columns],
        axis=1,
    ).mean(axis=1)


def _offer_mechanic_regime(frame: pd.DataFrame) -> pd.Series:
    offer_mechanic = pd.Series("simple", index=frame.index, dtype="object")
    offer_mechanic = offer_mechanic.mask(
        ensure_numeric_series(frame, "feature_offer_text_percent_flag") > 0.0,
        "percent_off",
    )
    offer_mechanic = offer_mechanic.mask(
        ensure_numeric_series(frame, "feature_offer_text_amount_flag") > 0.0,
        "amount_off",
    )
    offer_mechanic = offer_mechanic.mask(
        ensure_numeric_series(frame, "feature_offer_text_bonus_flag") > 0.0,
        "bonus",
    )
    offer_mechanic = offer_mechanic.mask(
        ensure_numeric_series(frame, "feature_offer_text_multi_buy_flag") > 0.0,
        "multi_buy",
    )
    return offer_mechanic


def build_archetype_signature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Return deterministic regime columns used for cohort archetypes."""

    kuramoto_anchor = _mean_anchor(
        frame,
        (
            "feature_short_long_demand_phase_alignment",
            "feature_promo_window_alignment_score",
            "feature_category_sync_score",
            "feature_store_sync_score",
        ),
    )
    gravity_anchor = _mean_anchor(
        frame,
        (
            "feature_category_gravity",
            "feature_supplier_gravity",
            "feature_promo_crowding_gravity",
        ),
    )
    context_anchor = _mean_anchor(
        frame,
        (
            "feature_store_category_promo_density",
            "feature_supplier_promo_density",
            "feature_store_level_promo_load",
        ),
    )
    return pd.DataFrame(
        {
            "archetype_discount_depth_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_discount_depth_pct"),
                thresholds=(0.10, 0.20, 0.35),
                labels=ORDERED_REGIME_LEVELS["archetype_discount_depth_regime"],
            ),
            "archetype_price_gap_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_price_gap_pct_vs_normal"),
                thresholds=(0.05, 0.15, 0.30),
                labels=ORDERED_REGIME_LEVELS["archetype_price_gap_regime"],
                absolute_value=True,
            ),
            "archetype_offer_mechanic_regime": _offer_mechanic_regime(frame),
            "archetype_margin_pressure_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_effective_margin_compression_pct"),
                thresholds=(0.05, 0.15, 0.30),
                labels=ORDERED_REGIME_LEVELS["archetype_margin_pressure_regime"],
                absolute_value=True,
            ),
            "archetype_rebate_dependency_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_rebate_dependency_score"),
                thresholds=(0.10, 0.30, 0.60),
                labels=ORDERED_REGIME_LEVELS["archetype_rebate_dependency_regime"],
            ),
            "archetype_stock_pressure_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_total_stock_pressure_ratio"),
                thresholds=(0.85, 1.05, 1.35),
                labels=ORDERED_REGIME_LEVELS["archetype_stock_pressure_regime"],
            ),
            "archetype_allocation_pressure_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_allocation_vs_baseline_demand_ratio"),
                thresholds=(0.85, 1.05, 1.35),
                labels=ORDERED_REGIME_LEVELS["archetype_allocation_pressure_regime"],
            ),
            "archetype_overhang_risk_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_overhang_risk"),
                thresholds=(0.10, 0.25, 0.45),
                labels=ORDERED_REGIME_LEVELS["archetype_overhang_risk_regime"],
            ),
            "archetype_baseline_demand_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_pre_promo_baseline_daily_units"),
                thresholds=(3.0, 8.0, 15.0),
                labels=ORDERED_REGIME_LEVELS["archetype_baseline_demand_regime"],
            ),
            "archetype_demand_acceleration_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_recent_acceleration_ratio"),
                thresholds=(0.85, 1.0, 1.15),
                labels=ORDERED_REGIME_LEVELS["archetype_demand_acceleration_regime"],
            ),
            "archetype_zeta_instability_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_composite_promo_instability"),
                thresholds=(0.10, 0.25, 0.45),
                labels=ORDERED_REGIME_LEVELS["archetype_zeta_instability_regime"],
            ),
            "archetype_kuramoto_sync_regime": _ordered_bucket(
                kuramoto_anchor,
                thresholds=(0.25, 0.50, 0.75),
                labels=ORDERED_REGIME_LEVELS["archetype_kuramoto_sync_regime"],
            ),
            "archetype_gravity_regime": _ordered_bucket(
                gravity_anchor,
                thresholds=(0.05, 0.20, 0.50),
                labels=ORDERED_REGIME_LEVELS["archetype_gravity_regime"],
                absolute_value=True,
            ),
            "archetype_field_density_regime": _ordered_bucket(
                ensure_numeric_series(frame, "feature_field_density_score"),
                thresholds=(0.15, 0.35, 0.60),
                labels=ORDERED_REGIME_LEVELS["archetype_field_density_regime"],
            ),
            "archetype_context_regime": _ordered_bucket(
                context_anchor,
                thresholds=(0.10, 0.25, 0.50),
                labels=ORDERED_REGIME_LEVELS["archetype_context_regime"],
            ),
        },
        index=frame.index,
    )