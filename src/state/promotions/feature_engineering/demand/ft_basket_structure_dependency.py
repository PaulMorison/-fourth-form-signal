from __future__ import annotations

"""Governed basket-structure dependency features.

This module treats a promotion row as part of a transaction object rather than
as an isolated SKU. It uses only decision-time or prior-safe basket/history
features already available on the candidate frame and appends numeric columns
for model use and diagnostics. It performs no I/O and does not alter action or
publishability policy.
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_basket_anchor_sku_score",
    "feature_basket_drag_along_dependency_score",
    "feature_basket_lone_random_purchase_score",
    "feature_basket_conditional_dependency_score",
    "feature_high_seller_companion_presence_probability",
    "feature_promo_anchor_absence_risk",
    "feature_top_20pct_driver_flag",
    "feature_long_tail_dependency_flag",
    "feature_basket_fragility_score",
    "feature_basket_convexity_support_score",
    "feature_basket_structure_evidence_available_flag",
)

BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS: tuple[str, ...] = (
    *BASKET_STRUCTURE_DEPENDENCY_MODEL_USE_FEATURE_COLUMNS,
)

_LOW_EVIDENCE_PROMO_COUNT = 1.0
_LOW_TRANSACTION_RATE_PER_DAY = 0.5


def apply_ft_basket_structure_dependency(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append basket-graph dependency features without realised promo leakage.

    Purpose:
        Summarise anchor, drag-along, lone-purchase, and companion dependence
        structure from prior-safe basket and pre-promo demand evidence.

    Inputs:
        frame: candidate promotion rows after basket/history features have been
            engineered. The function tolerates missing upstream basket fields by
            emitting explicit low evidence flags rather than reading realised
            promo outcomes.
        reference_frame: accepted for registry compatibility and deliberately
            unused because all source signals are row-local prior-safe features.

    Outputs:
        A copy of ``frame`` with ``BASKET_STRUCTURE_DEPENDENCY_FEATURE_COLUMNS``
        appended.

    Failure behavior:
        Missing optional basket evidence lowers the evidence-availability flag;
        no missing value is converted into an order or publishability decision.
    """

    del reference_frame
    working = frame.copy()

    demand_anchor_units = _demand_anchor_units(working)
    top_driver_flag = _top_driver_flag(working, demand_anchor_units=demand_anchor_units)
    demand_share_score = _within_group_demand_share_score(
        working,
        demand_anchor_units=demand_anchor_units,
    )
    basket_attach_rate = _optional_numeric_series(working, "feature_basket_attach_rate").clip(0.0, 1.0)
    multi_item_probability = _first_optional_numeric_series(
        working,
        (
            "feature_probability_sku_in_multi_item_basket",
            "feature_probability_sold_in_multi_item_basket_rate",
            "feature_basket_attach_rate",
        ),
    ).clip(0.0, 1.0)
    solo_purchase_rate = _first_optional_numeric_series(
        working,
        (
            "feature_sku_solo_purchase_rate",
            "feature_probability_sku_solo_purchase",
            "feature_probability_sold_as_solo_item_rate",
        ),
    ).clip(0.0, 1.0)
    dependency_score = _first_optional_numeric_series(
        working,
        (
            "feature_sku_basket_dependency_score",
            "feature_probability_companion_dependency_score",
            "feature_companion_absence_risk_score",
        ),
    ).clip(0.0, 1.0)
    companion_concentration = _first_optional_numeric_series(
        working,
        (
            "feature_companion_concentration_index",
            "feature_top_companion_sku_1_share",
            "feature_top_companion_sku_2_share",
        ),
    ).clip(0.0, 1.0)
    transactions_per_day = _optional_numeric_series(
        working,
        "feature_transactions_with_sku_per_day",
    ).clip(lower=0.0)
    transaction_depth_score = safe_ratio(
        transactions_per_day,
        transactions_per_day.add(1.0),
    ).clip(0.0, 1.0)
    evidence_promo_count = _optional_numeric_series(
        working,
        "feature_basket_history_evidence_promo_count",
    ).clip(lower=0.0)
    evidence_transaction_count = _optional_numeric_series(
        working,
        "feature_basket_history_transaction_count",
    ).clip(lower=0.0)
    evidence_available = (
        basket_attach_rate.notna()
        | multi_item_probability.notna()
        | dependency_score.notna()
        | companion_concentration.notna()
        | evidence_transaction_count.gt(0.0)
    )

    basket_attach_rate = basket_attach_rate.fillna(0.0)
    multi_item_probability = multi_item_probability.fillna(0.0)
    solo_purchase_rate = solo_purchase_rate.fillna(0.0)
    dependency_score = dependency_score.fillna(0.0)
    companion_concentration = companion_concentration.fillna(0.0)
    transactions_per_day = transactions_per_day.fillna(0.0)
    transaction_depth_score = transaction_depth_score.fillna(0.0)
    evidence_promo_count = evidence_promo_count.fillna(0.0)
    evidence_missing_score = (
        evidence_promo_count.lt(_LOW_EVIDENCE_PROMO_COUNT)
        & transactions_per_day.lt(_LOW_TRANSACTION_RATE_PER_DAY)
    ).astype(float)

    companion_presence_probability = pd.concat(
        [multi_item_probability, basket_attach_rate, companion_concentration],
        axis=1,
    ).max(axis=1).clip(0.0, 1.0)
    anchor_score = (
        0.45 * demand_share_score
        + 0.25 * top_driver_flag
        + 0.20 * transaction_depth_score
        + 0.10 * companion_presence_probability
    ).clip(0.0, 1.0)
    drag_along_dependency_score = (
        0.35 * dependency_score
        + 0.25 * multi_item_probability
        + 0.25 * companion_concentration
        + 0.15 * (1.0 - top_driver_flag)
    ).clip(0.0, 1.0)
    lone_random_purchase_score = (
        0.45 * solo_purchase_rate
        + 0.25 * evidence_missing_score
        + 0.20 * (1.0 - transaction_depth_score)
        + 0.10 * (1.0 - demand_share_score)
    ).clip(0.0, 1.0)
    conditional_dependency_score = pd.concat(
        [dependency_score, drag_along_dependency_score * companion_presence_probability],
        axis=1,
    ).max(axis=1).clip(0.0, 1.0)
    anchor_absence_risk = ((1.0 - anchor_score) * conditional_dependency_score).clip(0.0, 1.0)
    long_tail_dependency_flag = (
        drag_along_dependency_score.ge(0.5) & top_driver_flag.lt(1.0)
    ).astype(float)
    basket_fragility_score = (
        0.35 * anchor_absence_risk
        + 0.25 * conditional_dependency_score
        + 0.20 * evidence_missing_score
        + 0.20 * (1.0 - transaction_depth_score)
    ).clip(0.0, 1.0)
    basket_convexity_support_score = pd.concat(
        [anchor_score * companion_presence_probability, drag_along_dependency_score * demand_share_score],
        axis=1,
    ).max(axis=1).clip(0.0, 1.0)

    derived = pd.DataFrame(
        {
            "feature_basket_anchor_sku_score": anchor_score,
            "feature_basket_drag_along_dependency_score": drag_along_dependency_score,
            "feature_basket_lone_random_purchase_score": lone_random_purchase_score,
            "feature_basket_conditional_dependency_score": conditional_dependency_score,
            "feature_high_seller_companion_presence_probability": companion_presence_probability,
            "feature_promo_anchor_absence_risk": anchor_absence_risk,
            "feature_top_20pct_driver_flag": top_driver_flag,
            "feature_long_tail_dependency_flag": long_tail_dependency_flag,
            "feature_basket_fragility_score": basket_fragility_score,
            "feature_basket_convexity_support_score": basket_convexity_support_score,
            "feature_basket_structure_evidence_available_flag": evidence_available.astype(float),
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived.columns), errors="ignore")
    return pd.concat([base_columns, derived], axis=1)


def _demand_anchor_units(frame: pd.DataFrame) -> pd.Series:
    """Return a prior-safe demand magnitude proxy for anchor classification."""

    candidates = pd.DataFrame(
        {
            "required_implied_units": ensure_numeric_series(frame, "required_implied_units", default=float("nan")),
            "baseline_expected_units": ensure_numeric_series(frame, "baseline_expected_units", default=float("nan")),
            "pre_28d_units": ensure_numeric_series(frame, "pre_28d_units", default=float("nan")),
            "pre_56d_units_half": ensure_numeric_series(frame, "pre_56d_units", default=float("nan")).divide(2.0),
        },
        index=frame.index,
    )
    return candidates.max(axis=1, skipna=True).fillna(0.0).clip(lower=0.0)


def _top_driver_flag(frame: pd.DataFrame, *, demand_anchor_units: pd.Series) -> pd.Series:
    """Flag top-20-percent demand drivers within each known promotion group."""

    groups = _promotion_group_series(frame)
    ranks = demand_anchor_units.groupby(groups, sort=False).rank(method="first", ascending=False)
    group_sizes = demand_anchor_units.groupby(groups, sort=False).transform("size").astype(float)
    top_n = np.ceil(group_sizes * 0.2).clip(lower=1.0)
    return (ranks <= top_n).astype(float)


def _within_group_demand_share_score(
    frame: pd.DataFrame,
    *,
    demand_anchor_units: pd.Series,
) -> pd.Series:
    """Return demand share against the strongest prior-safe row in the group."""

    groups = _promotion_group_series(frame)
    group_max = demand_anchor_units.groupby(groups, sort=False).transform("max")
    return safe_ratio(demand_anchor_units, group_max.where(group_max > 0.0)).clip(0.0, 1.0)


def _promotion_group_series(frame: pd.DataFrame) -> pd.Series:
    """Build a stable promotion group key from available prior-known fields."""

    if frame.empty:
        return pd.Series(index=frame.index, dtype="object")

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