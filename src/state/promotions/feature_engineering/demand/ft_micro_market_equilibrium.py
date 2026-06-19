from __future__ import annotations

"""Governed micro-market equilibrium features for promotions.

This module scores a SKU inside its local promotion market using prior-safe
basket, companion, sparse/noise, target-stock, gravity, and capital signals. It
adds numeric model-use features only; it does not infer actions, publishability,
or BUY/ORDER widening.
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


MICRO_MARKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_anchor_presence_dependency_score",
    "feature_anchor_absence_suppressed_demand_score",
    "feature_drag_along_probability",
    "feature_conditional_sale_probability_given_anchor",
    "feature_lone_purchase_noise_score",
    "feature_transaction_object_stability_score",
    "feature_basket_regime_class",
    "feature_basket_anchor_strength_score",
    "feature_basket_dependency_fragility_score",
    "feature_companion_presence_support_score",
    "feature_basket_depth_conditional_units_score",
    "feature_micro_market_clearing_pressure",
    "feature_local_equilibrium_gap_units",
    "feature_local_equilibrium_gap_dollars",
    "feature_substitute_pressure_score",
    "feature_complement_support_score",
    "feature_attention_competition_score",
    "feature_promo_field_equilibrium_state",
    "feature_inventory_constrained_demand_proxy",
    "feature_small_unit_option_value",
    "feature_convexity_to_capital_score",
    "feature_trust_floor_convexity_score",
    "feature_high_demand_underprotection_score",
    "feature_end_shape_fragility_score",
)

MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS: tuple[str, ...] = (
    *MICRO_MARKET_EQUILIBRIUM_MODEL_USE_FEATURE_COLUMNS,
)

BASKET_REGIME_LONE_NOISY = 0.0
BASKET_REGIME_DRAG_ALONG = 1.0
BASKET_REGIME_BALANCED = 2.0
BASKET_REGIME_ANCHOR = 3.0
EQUILIBRIUM_STATE_OVER_SUPPLIED = -1.0
EQUILIBRIUM_STATE_BALANCED = 0.0
EQUILIBRIUM_STATE_UNDER_PROTECTED = 1.0

ANCHOR_SCORE_THRESHOLD = 0.55
DRAG_ALONG_SCORE_THRESHOLD = 0.45
LONE_NOISE_SCORE_THRESHOLD = 0.60
SMALL_UNIT_OPTION_MAX_UNITS = 2.0


def apply_ft_micro_market_equilibrium(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append micro-market equilibrium features from prior-safe signals.

    Purpose:
        Represent anchor/driver, drag-along, local-clearing, companion support,
        and inventory-constrained convexity structure so the model can
        generalise beyond isolated SKU averages.

    Inputs:
        frame: candidate promotion rows after existing basket, sparse/noise,
            target-stock, capital, and field-density features have been applied.
        reference_frame: accepted for registry compatibility and deliberately
            unused because this layer consumes only row-local prior-safe signals.

    Outputs:
        A copy of ``frame`` with ``MICRO_MARKET_EQUILIBRIUM_FEATURE_COLUMNS``
        appended as numeric features.

    Failure behavior:
        Missing optional upstream evidence is kept as low-support context rather
        than converted into safe or unsafe action evidence.
    """

    del reference_frame
    working = frame.copy()

    anchor_score = _first_optional_numeric_series(
        working,
        ("feature_basket_anchor_sku_score", "feature_top_20pct_driver_flag"),
    ).clip(0.0, 1.0).fillna(0.0)
    drag_score = _first_optional_numeric_series(
        working,
        ("feature_basket_drag_along_dependency_score", "feature_basket_conditional_dependency_score"),
    ).clip(0.0, 1.0).fillna(0.0)
    lone_noise = _first_optional_numeric_series(
        working,
        ("feature_basket_lone_random_purchase_score", "feature_sparse_demand_randomness_score"),
    ).clip(0.0, 1.0).fillna(0.0)
    sparse_stable = _optional_numeric_series(
        working,
        "feature_sparse_demand_stable_low_trust_flag",
    ).clip(0.0, 1.0).fillna(0.0)
    companion_support = _first_optional_numeric_series(
        working,
        (
            "feature_high_seller_companion_presence_probability",
            "feature_basket_attach_rate",
            "feature_probability_sku_in_multi_item_basket",
        ),
    ).clip(0.0, 1.0).fillna(0.0)
    companion_absence_risk = _first_optional_numeric_series(
        working,
        ("feature_companion_absence_risk_score", "feature_promo_anchor_absence_risk"),
    ).clip(0.0, 1.0).fillna(0.0)
    basket_fragility = _optional_numeric_series(
        working,
        "feature_basket_fragility_score",
    ).clip(0.0, 1.0).fillna(0.0)
    basket_convexity = _optional_numeric_series(
        working,
        "feature_basket_convexity_support_score",
    ).clip(0.0, 1.0).fillna(0.0)
    transactions_per_day = _optional_numeric_series(
        working,
        "feature_transactions_with_sku_per_day",
    ).clip(lower=0.0).fillna(0.0)
    units_per_transaction = _optional_numeric_series(
        working,
        "feature_units_per_transaction_when_sku_present",
    ).clip(lower=0.0).fillna(0.0)
    target_units = _first_optional_numeric_series(
        working,
        ("feature_promo_period_target_units", "required_implied_units", "baseline_expected_units"),
    ).clip(lower=0.0).fillna(0.0)
    available_units = _first_optional_numeric_series(
        working,
        ("total_stock_available", "stock_basis_units", "pl_allocation_qty", "current_soh"),
    ).clip(lower=0.0).fillna(0.0)
    target_floor_units = _first_optional_numeric_series(
        working,
        ("feature_trust_floor_units_dynamic", "feature_end_of_promo_target_floor_units"),
    ).clip(lower=0.0).fillna(0.0)
    high_demand_gap = _optional_numeric_series(
        working,
        "feature_units_needed_for_high_demand_cover",
    ).clip(lower=0.0).fillna(0.0)
    trust_gap = _optional_numeric_series(
        working,
        "feature_units_needed_for_trust_floor",
    ).clip(lower=0.0).fillna(0.0)
    unit_cost = _first_optional_numeric_series(
        working,
        ("effective_cost_per_unit", "promo_unit_cost", "unit_cost", "cost_per_unit"),
    ).clip(lower=0.0).fillna(0.0)
    capital_drag = _first_optional_numeric_series(
        working,
        ("feature_excess_month_end_capital_drag", "feature_capital_tied_above_trust_target"),
    ).clip(lower=0.0).fillna(0.0)
    substitute_pressure = _first_optional_numeric_series(
        working,
        ("feature_substitute_overlap_discount_sum", "feature_local_competition_pressure"),
    ).clip(lower=0.0).fillna(0.0)
    field_density = _first_optional_numeric_series(
        working,
        (
            "feature_local_promotional_field_density_score",
            "feature_field_density_score",
            "feature_store_overlap_count",
        ),
    ).clip(lower=0.0).fillna(0.0)
    complement_support = _first_optional_numeric_series(
        working,
        ("feature_category_sync_score", "feature_store_sync_score", "feature_promo_window_alignment_score"),
    ).clip(0.0, 1.0).fillna(0.0)

    anchor_dependency = (anchor_score * companion_support).clip(0.0, 1.0)
    suppressed_demand = (companion_absence_risk * (1.0 - anchor_score) * (0.5 + 0.5 * drag_score)).clip(0.0, 1.0)
    conditional_sale_given_anchor = (
        0.45 * anchor_dependency
        + 0.30 * companion_support
        + 0.25 * basket_convexity
    ).clip(0.0, 1.0)
    transaction_stability = (
        0.40 * safe_ratio(transactions_per_day, transactions_per_day.add(1.0))
        + 0.30 * sparse_stable
        + 0.30 * (1.0 - lone_noise)
    ).clip(0.0, 1.0)
    basket_regime = _basket_regime_class(
        anchor_score=anchor_score,
        drag_score=drag_score,
        lone_noise=lone_noise,
    )
    basket_depth_units = (units_per_transaction * companion_support).clip(lower=0.0)
    clearing_gap_units = (target_units - available_units).round(4)
    clearing_pressure = safe_ratio(
        clearing_gap_units.clip(lower=0.0),
        target_units.where(target_units > 0.0),
    ).clip(0.0, 1.0)
    clearing_gap_dollars = clearing_gap_units * unit_cost
    attention_competition = safe_ratio(
        field_density,
        field_density.add(1.0),
    ).clip(0.0, 1.0)
    equilibrium_state = _equilibrium_state(
        clearing_gap_units=clearing_gap_units,
        capital_drag=capital_drag,
    )
    inventory_constrained_proxy = pd.concat([clearing_pressure, trust_gap, high_demand_gap], axis=1).max(axis=1)
    small_unit_option = (
        clearing_gap_units.clip(lower=0.0, upper=SMALL_UNIT_OPTION_MAX_UNITS)
        * (0.5 + 0.5 * conditional_sale_given_anchor)
    ).clip(lower=0.0)
    convexity_to_capital = safe_ratio(
        basket_convexity.add(small_unit_option),
        capital_drag.add(1.0),
    ).clip(0.0, 1.0)
    trust_floor_convexity = safe_ratio(
        trust_gap.add(small_unit_option),
        target_floor_units.add(1.0),
    ).clip(0.0, 1.0)
    high_demand_underprotection = safe_ratio(
        high_demand_gap,
        target_units.add(1.0),
    ).clip(0.0, 1.0)
    end_shape_fragility = (
        0.40 * clearing_pressure
        + 0.25 * basket_fragility
        + 0.20 * companion_absence_risk
        + 0.15 * attention_competition
    ).clip(0.0, 1.0)

    derived = pd.DataFrame(
        {
            "feature_anchor_presence_dependency_score": anchor_dependency,
            "feature_anchor_absence_suppressed_demand_score": suppressed_demand,
            "feature_drag_along_probability": drag_score,
            "feature_conditional_sale_probability_given_anchor": conditional_sale_given_anchor,
            "feature_lone_purchase_noise_score": lone_noise,
            "feature_transaction_object_stability_score": transaction_stability,
            "feature_basket_regime_class": basket_regime,
            "feature_basket_anchor_strength_score": anchor_score,
            "feature_basket_dependency_fragility_score": basket_fragility,
            "feature_companion_presence_support_score": companion_support,
            "feature_basket_depth_conditional_units_score": basket_depth_units,
            "feature_micro_market_clearing_pressure": clearing_pressure,
            "feature_local_equilibrium_gap_units": clearing_gap_units,
            "feature_local_equilibrium_gap_dollars": clearing_gap_dollars,
            "feature_substitute_pressure_score": safe_ratio(substitute_pressure, substitute_pressure.add(1.0)).clip(0.0, 1.0),
            "feature_complement_support_score": complement_support,
            "feature_attention_competition_score": attention_competition,
            "feature_promo_field_equilibrium_state": equilibrium_state,
            "feature_inventory_constrained_demand_proxy": inventory_constrained_proxy,
            "feature_small_unit_option_value": small_unit_option,
            "feature_convexity_to_capital_score": convexity_to_capital,
            "feature_trust_floor_convexity_score": trust_floor_convexity,
            "feature_high_demand_underprotection_score": high_demand_underprotection,
            "feature_end_shape_fragility_score": end_shape_fragility,
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived.columns), errors="ignore")
    return pd.concat([base_columns, derived], axis=1)


def _basket_regime_class(
    *,
    anchor_score: pd.Series,
    drag_score: pd.Series,
    lone_noise: pd.Series,
) -> pd.Series:
    """Classify rows into numeric basket-equilibrium regimes."""

    regime = pd.Series(BASKET_REGIME_BALANCED, index=anchor_score.index, dtype="float64")
    regime = regime.where(lone_noise.lt(LONE_NOISE_SCORE_THRESHOLD), BASKET_REGIME_LONE_NOISY)
    regime = regime.where(drag_score.lt(DRAG_ALONG_SCORE_THRESHOLD), BASKET_REGIME_DRAG_ALONG)
    regime = regime.where(anchor_score.lt(ANCHOR_SCORE_THRESHOLD), BASKET_REGIME_ANCHOR)
    return regime


def _equilibrium_state(*, clearing_gap_units: pd.Series, capital_drag: pd.Series) -> pd.Series:
    """Classify local clearing state without action inference."""

    state = pd.Series(EQUILIBRIUM_STATE_BALANCED, index=clearing_gap_units.index, dtype="float64")
    state = state.where(capital_drag.le(0.0), EQUILIBRIUM_STATE_OVER_SUPPLIED)
    state = state.where(clearing_gap_units.le(0.0), EQUILIBRIUM_STATE_UNDER_PROTECTED)
    return state


def _optional_numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    """Return a numeric series preserving missing evidence as NaN."""

    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def _first_optional_numeric_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
) -> pd.Series:
    """Return the first non-null numeric evidence from candidate columns."""

    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return frame[present_columns].apply(pd.to_numeric, errors="coerce").bfill(axis=1).iloc[:, 0]