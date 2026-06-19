from __future__ import annotations

"""Governed basket-equilibrium features for promotions.

The basket-equilibrium layer treats the promotion as a local micro-market where
each SKU's demand support depends on anchor presence, companion structure,
substitute pressure, basket depth, and sparse solo-purchase noise. It is not a
literal Nash equilibrium model; it is a governed conditional-demand layer built
from prior-safe upstream basket and market features.

The module consumes only decision-time or already prior-safe engineered inputs.
It performs no I/O, does not infer actions, and does not widen BUY/ORDER or
publishability logic.
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_anchor_centrality_score",
    "feature_anchor_presence_support_score",
    "feature_top_anchor_dependency_score",
    "feature_anchor_absence_risk_score",
    "feature_drag_along_probability",
    "feature_companion_cluster_support_score",
    "feature_companion_concentration_score",
    "feature_multi_sku_promo_basket_rate",
    "feature_three_plus_promo_sku_basket_rate",
    "feature_solo_purchase_rate",
    "feature_sparse_random_purchase_score",
    "feature_basket_noise_score",
    "feature_transaction_object_uncertainty_score",
    "feature_conditional_sale_rate_with_anchor",
    "feature_conditional_sale_rate_without_anchor",
    "feature_substitution_pressure_score",
    "feature_promo_basket_depth_alignment_score",
    "feature_anchor_mix_stability_score",
)

BASKET_EQUILIBRIUM_REVIEW_ONLY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_conditional_lift_with_anchor",
    "feature_conditional_lift_with_companion_cluster",
    "feature_basket_equilibrium_regime_class",
    "feature_basket_equilibrium_score",
    "feature_basket_equilibrium_fragility_score",
)

BASKET_EQUILIBRIUM_FEATURE_COLUMNS: tuple[str, ...] = (
    *BASKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS,
    *BASKET_EQUILIBRIUM_REVIEW_ONLY_FEATURE_COLUMNS,
)

REGIME_LONE_NOISY = 0.0
REGIME_DRAG_ALONG = 1.0
REGIME_BALANCED = 2.0
REGIME_ANCHOR_LED = 3.0

ANCHOR_CENTRALITY_THRESHOLD = 0.60
DRAG_ALONG_THRESHOLD = 0.45
LONE_NOISE_THRESHOLD = 0.65
THREE_PLUS_BASKET_UNITS_THRESHOLD = 2.0


def apply_ft_basket_equilibrium(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append basket-equilibrium features from prior-safe upstream signals.

    Purpose:
        Build a store-generalisable conditional-demand layer that distinguishes
        standalone demand, anchor-led demand, drag-along demand, substitute
        pressure, and sparse/noisy transaction behavior.

    Inputs:
        frame: candidate promotion rows after prior-safe basket-history,
            basket-structure, sparse/noise, and market-context features have
            already been engineered.
        reference_frame: accepted for registry compatibility and deliberately
            unused because this layer operates only on already prior-safe
            upstream features and same-promo composition.

    Outputs:
        A copy of ``frame`` with ``BASKET_EQUILIBRIUM_FEATURE_COLUMNS``
        appended.

    Important assumptions:
        The upstream basket and market features were computed using strictly
        prior history. Same-promo grouping is legitimate decision-time context,
        not future outcome leakage.

    Failure behavior:
        Missing upstream evidence lowers support and raises uncertainty; it is
        never coerced into safe action evidence.
    """

    del reference_frame
    working = frame.copy()
    if working.empty:
        for column_name in BASKET_EQUILIBRIUM_FEATURE_COLUMNS:
            working[column_name] = pd.Series(index=working.index, dtype="float64")
        return working
    groups = _promotion_group_series(working)

    target_units = _first_optional_numeric_series(
        working,
        ("required_implied_units", "baseline_expected_units", "feature_promo_period_target_units"),
    ).clip(lower=0.0).fillna(0.0)
    total_target_units = target_units.groupby(groups, sort=False).transform("sum")
    target_share = safe_ratio(target_units, total_target_units.where(total_target_units.gt(0.0))).clip(0.0, 1.0)

    anchor_base = _first_optional_numeric_series(
        working,
        ("feature_basket_anchor_sku_score", "feature_top_20pct_driver_flag"),
    ).clip(0.0, 1.0).fillna(0.0)
    drag_base = _first_optional_numeric_series(
        working,
        ("feature_basket_drag_along_dependency_score", "feature_basket_conditional_dependency_score"),
    ).clip(0.0, 1.0).fillna(0.0)
    solo_rate = _first_optional_numeric_series(
        working,
        ("feature_sku_solo_purchase_rate", "feature_probability_sku_solo_purchase"),
    ).clip(0.0, 1.0).fillna(0.0)
    sparse_noise = _first_optional_numeric_series(
        working,
        ("feature_sparse_demand_randomness_score", "feature_basket_lone_random_purchase_score"),
    ).clip(0.0, 1.0).fillna(0.0)
    low_signal = _first_optional_numeric_series(
        working,
        ("feature_sparse_demand_low_signal_flag", "feature_basket_history_missing_evidence_flag"),
    ).clip(0.0, 1.0).fillna(0.0)
    multi_sku_rate = _first_optional_numeric_series(
        working,
        ("feature_probability_sku_in_multi_item_basket", "feature_basket_attach_rate"),
    ).clip(0.0, 1.0).fillna(0.0)
    units_per_transaction = _first_optional_numeric_series(
        working,
        ("feature_units_per_transaction_when_sku_present",),
    ).clip(lower=0.0).fillna(0.0)
    companion_presence = _first_optional_numeric_series(
        working,
        ("feature_high_seller_companion_presence_probability", "feature_basket_attach_rate"),
    ).clip(0.0, 1.0).fillna(0.0)
    companion_concentration = _first_optional_numeric_series(
        working,
        ("feature_companion_concentration_index", "feature_top_companion_sku_1_share"),
    ).clip(0.0, 1.0).fillna(0.0)
    companion_diversity = _first_optional_numeric_series(
        working,
        ("feature_basket_diversity_when_sku_present",),
    ).clip(0.0, 1.0).fillna(0.0)
    evidence_promos = _first_optional_numeric_series(
        working,
        ("feature_basket_history_evidence_promo_count",),
    ).clip(lower=0.0).fillna(0.0)
    evidence_transactions = _first_optional_numeric_series(
        working,
        ("feature_basket_history_transaction_count",),
    ).clip(lower=0.0).fillna(0.0)
    substitute_pressure_base = _first_optional_numeric_series(
        working,
        ("feature_substitute_overlap_discount_sum", "feature_local_competition_pressure"),
    ).clip(lower=0.0).fillna(0.0)
    complement_support = _first_optional_numeric_series(
        working,
        ("feature_category_sync_score", "feature_store_sync_score"),
    ).clip(0.0, 1.0).fillna(0.0)
    field_density = _first_optional_numeric_series(
        working,
        ("feature_local_promotional_field_density_score", "feature_field_density_score"),
    ).clip(lower=0.0).fillna(0.0)

    top_anchor_strength = anchor_base.groupby(groups, sort=False).transform("max")
    top_anchor_dependency = (drag_base * top_anchor_strength * (1.0 - anchor_base)).clip(0.0, 1.0)
    anchor_presence_support = (top_anchor_strength * companion_presence).clip(0.0, 1.0)
    anchor_absence_risk = pd.concat(
        [top_anchor_dependency, _first_optional_numeric_series(working, ("feature_promo_anchor_absence_risk", "feature_companion_absence_risk_score"))],
        axis=1,
    ).max(axis=1, skipna=True).clip(0.0, 1.0).fillna(0.0)
    anchor_centrality = (
        0.45 * anchor_base
        + 0.30 * target_share
        + 0.25 * companion_presence
    ).clip(0.0, 1.0)
    drag_along_probability = (
        0.45 * drag_base
        + 0.35 * top_anchor_dependency
        + 0.20 * companion_presence
    ).clip(0.0, 1.0)
    companion_cluster_support = (
        0.40 * companion_presence
        + 0.35 * companion_diversity
        + 0.25 * multi_sku_rate
    ).clip(0.0, 1.0)
    three_plus_basket_rate = (
        multi_sku_rate
        * safe_ratio(
            units_per_transaction.sub(1.0).clip(lower=0.0),
            pd.Series(THREE_PLUS_BASKET_UNITS_THRESHOLD, index=working.index, dtype="float64"),
        )
    ).clip(0.0, 1.0)
    sparse_random_purchase = (
        0.45 * solo_rate
        + 0.35 * sparse_noise
        + 0.20 * low_signal
    ).clip(0.0, 1.0)
    support_strength = (
        safe_ratio(evidence_promos, evidence_promos.add(2.0))
        * safe_ratio(evidence_transactions, evidence_transactions.add(10.0))
    ).clip(0.0, 1.0)
    transaction_uncertainty = (1.0 - support_strength + 0.25 * sparse_noise).clip(0.0, 1.0)
    basket_noise = (
        0.50 * sparse_random_purchase
        + 0.25 * transaction_uncertainty
        + 0.25 * (1.0 - multi_sku_rate)
    ).clip(0.0, 1.0)
    conditional_sale_with_anchor = (anchor_presence_support * multi_sku_rate).clip(0.0, 1.0)
    conditional_sale_without_anchor = (solo_rate * (1.0 - top_anchor_strength)).clip(0.0, 1.0)
    conditional_lift_with_anchor = (conditional_sale_with_anchor - conditional_sale_without_anchor).clip(-1.0, 1.0)
    conditional_lift_with_companion_cluster = (companion_cluster_support - solo_rate).clip(-1.0, 1.0)
    substitution_pressure = safe_ratio(
        substitute_pressure_base.add(field_density),
        substitute_pressure_base.add(field_density).add(1.0),
    ).clip(0.0, 1.0)

    group_mean_units_per_txn = units_per_transaction.groupby(groups, sort=False).transform("mean")
    depth_alignment = (
        1.0
        - safe_ratio(
            (units_per_transaction - group_mean_units_per_txn).abs(),
            group_mean_units_per_txn.abs().add(1.0),
        )
    ).clip(0.0, 1.0)
    group_mean_anchor = anchor_centrality.groupby(groups, sort=False).transform("mean")
    anchor_mix_stability = (
        1.0
        - safe_ratio(
            (anchor_centrality - group_mean_anchor).abs(),
            group_mean_anchor.abs().add(1.0),
        )
    ).clip(0.0, 1.0)
    basket_equilibrium_score = (
        0.30 * anchor_mix_stability
        + 0.25 * depth_alignment
        + 0.25 * companion_cluster_support
        + 0.20 * (1.0 - substitution_pressure)
    ).clip(0.0, 1.0)
    basket_equilibrium_fragility = (
        0.35 * anchor_absence_risk
        + 0.25 * basket_noise
        + 0.20 * (1.0 - anchor_mix_stability)
        + 0.20 * substitution_pressure
    ).clip(0.0, 1.0)
    regime_class = _regime_class(
        anchor_centrality=anchor_centrality,
        drag_along_probability=drag_along_probability,
        sparse_random_purchase=sparse_random_purchase,
    )

    derived = pd.DataFrame(
        {
            "feature_anchor_centrality_score": anchor_centrality,
            "feature_anchor_presence_support_score": anchor_presence_support,
            "feature_top_anchor_dependency_score": top_anchor_dependency,
            "feature_anchor_absence_risk_score": anchor_absence_risk,
            "feature_drag_along_probability": drag_along_probability,
            "feature_companion_cluster_support_score": companion_cluster_support,
            "feature_companion_concentration_score": companion_concentration,
            "feature_multi_sku_promo_basket_rate": multi_sku_rate,
            "feature_three_plus_promo_sku_basket_rate": three_plus_basket_rate,
            "feature_solo_purchase_rate": solo_rate,
            "feature_sparse_random_purchase_score": sparse_random_purchase,
            "feature_basket_noise_score": basket_noise,
            "feature_transaction_object_uncertainty_score": transaction_uncertainty,
            "feature_conditional_sale_rate_with_anchor": conditional_sale_with_anchor,
            "feature_conditional_sale_rate_without_anchor": conditional_sale_without_anchor,
            "feature_conditional_lift_with_anchor": conditional_lift_with_anchor,
            "feature_conditional_lift_with_companion_cluster": conditional_lift_with_companion_cluster,
            "feature_substitution_pressure_score": substitution_pressure,
            "feature_promo_basket_depth_alignment_score": depth_alignment,
            "feature_anchor_mix_stability_score": anchor_mix_stability,
            "feature_basket_equilibrium_regime_class": regime_class,
            "feature_basket_equilibrium_score": basket_equilibrium_score,
            "feature_basket_equilibrium_fragility_score": basket_equilibrium_fragility,
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived.columns), errors="ignore")
    return pd.concat([base_columns, derived], axis=1)


def _regime_class(
    *,
    anchor_centrality: pd.Series,
    drag_along_probability: pd.Series,
    sparse_random_purchase: pd.Series,
) -> pd.Series:
    """Return a numeric basket regime class for analyst review surfaces."""

    regime = pd.Series(REGIME_BALANCED, index=anchor_centrality.index, dtype="float64")
    regime = regime.where(sparse_random_purchase.lt(LONE_NOISE_THRESHOLD), REGIME_LONE_NOISY)
    regime = regime.where(drag_along_probability.lt(DRAG_ALONG_THRESHOLD), REGIME_DRAG_ALONG)
    regime = regime.where(anchor_centrality.lt(ANCHOR_CENTRALITY_THRESHOLD), REGIME_ANCHOR_LED)
    return regime


def _promotion_group_series(frame: pd.DataFrame) -> pd.Series:
    """Build a stable decision-time promotion group key."""

    key_columns = [
        column_name
        for column_name in (
            "store_number_key",
            "store_number",
            "promotion_header_key",
            "promotion_name",
            "promotion_start_date_date",
            "promotion_start_date",
        )
        if column_name in frame.columns
    ]
    if not key_columns:
        return pd.Series("__all_rows__", index=frame.index, dtype="object")
    key_frame = frame.loc[:, key_columns].fillna("").astype(str)
    return key_frame.agg("|".join, axis=1)


def _first_optional_numeric_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
) -> pd.Series:
    """Return the first non-null numeric evidence from candidate columns."""

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return frame[present_columns].apply(pd.to_numeric, errors="coerce").bfill(axis=1).iloc[:, 0]