from __future__ import annotations

"""Prior-promo memory and promo-vs-baseline separation features.

Leakage rules (governed):
- Each candidate row may only consider PRIOR promotions whose
  `promotional_end_date_date` is STRICTLY BEFORE the candidate's
  `promotion_start_date_date` for the same `(store_number_key, sku_number_key)`.
- Same-or-better discount means the prior promotion's `discount_percent` is
  greater than or equal to the candidate's `discount_percent`.
- Better discount means strictly greater.
- Realised volumes from prior completed promotions are read from
  `actual_units_sold_promo` (already an aggregate of completed prior promos
  and therefore a non-future signal at the time of the candidate's start).
- Future rows for which only a `promotion_start_date_date` exists in the
  candidate window cannot leak into prior windows because we filter strictly
  on `promotional_end_date_date < candidate.promotion_start_date_date`.

The module emits these `feature_*` columns (model contract):
    feature_prior_promo_14d_flag
    feature_prior_promo_28d_flag
    feature_prior_promo_56d_flag
    feature_prior_promo_units_14d
    feature_prior_promo_units_28d
    feature_prior_promo_units_56d
    feature_prior_promo_days_since_last_promo
    feature_prior_same_or_better_discount_14d_flag
    feature_prior_same_or_better_discount_28d_flag
    feature_prior_same_or_better_discount_56d_flag
    feature_prior_same_or_better_discount_units_56d
    feature_prior_same_discount_days_since_last_promo
    feature_prior_better_discount_days_since_last_promo
    feature_prior_promo_price_memory_score
    feature_prior_promo_discount_memory_score
    feature_prior_promo_cannibalisation_risk_score
    feature_historical_promo_events_same_discount
    feature_historical_promo_events_same_or_better_discount
    feature_historical_units_same_discount_avg
    feature_historical_units_same_or_better_discount_avg
    feature_historical_units_same_discount_median
    feature_historical_units_same_or_better_discount_median
    feature_historical_units_same_discount_std
    feature_historical_discount_response_confidence
    feature_discount_band_response_avg
    feature_discount_band_response_median
    feature_discount_band_event_count
    feature_probability_zero_demand_same_or_better_discount
    feature_probability_low_demand_vs_baseline_same_or_better_discount
    feature_probability_demand_exceeds_allocation_same_or_better_discount
    feature_probability_units_below_allocation_same_or_better_discount
    feature_probability_stockout_vs_stock_basis_same_or_better_discount
    feature_promo_history_evidence_strength
    feature_sparse_history_penalty
    feature_order_evidence_quality_score
    feature_overallocation_risk_score
    feature_historical_comparable_promo_event_count
    feature_historical_zero_sale_after_buy_rate
    feature_same_discount_success_rate_56d
    feature_historical_trapped_capital_rate
    feature_historical_sell_through_on_accepted_qty
    feature_historical_overforecast_bias
    feature_historical_allocation_efficiency_rate
    feature_historical_overallocation_above_floor_rate
    feature_historical_residual_above_floor_units_avg
    feature_historical_under_floor_missed_demand_rate
    feature_historical_under_floor_lost_units_avg
    feature_historical_memory_category_fallback_flag
    feature_historical_memory_department_fallback_flag
    feature_non_promo_units_28d
    feature_non_promo_units_56d
    feature_promo_units_28d
    feature_promo_units_56d
    feature_non_promo_avg_daily_units_28d
    feature_non_promo_avg_daily_units_56d
    feature_promo_avg_daily_units_28d
    feature_promo_avg_daily_units_56d
    feature_promo_to_nonpromo_demand_ratio_28d
    feature_promo_to_nonpromo_demand_ratio_56d
    feature_discount_elasticity_proxy
    feature_realised_prior_promo_lift_proxy
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import (
    ensure_numeric_series,
    first_non_null_series,
)
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    coerce_promotions_frame_types,
    discount_band_from_decimal,
    normalize_discount_decimal,
)


PRIOR_PROMO_MEMORY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_prior_promo_14d_flag",
    "feature_prior_promo_28d_flag",
    "feature_prior_promo_56d_flag",
    "feature_prior_promo_units_14d",
    "feature_prior_promo_units_28d",
    "feature_prior_promo_units_56d",
    "feature_prior_promo_days_since_last_promo",
    "feature_prior_same_or_better_discount_14d_flag",
    "feature_prior_same_or_better_discount_28d_flag",
    "feature_prior_same_or_better_discount_56d_flag",
    "feature_prior_same_or_better_discount_units_56d",
    "feature_prior_same_discount_days_since_last_promo",
    "feature_prior_better_discount_days_since_last_promo",
    "feature_prior_promo_price_memory_score",
    "feature_prior_promo_discount_memory_score",
    "feature_prior_promo_cannibalisation_risk_score",
    "feature_historical_promo_events_same_discount",
    "feature_historical_promo_events_same_or_better_discount",
    "feature_historical_units_same_discount_avg",
    "feature_historical_units_same_or_better_discount_avg",
    "feature_historical_units_same_discount_median",
    "feature_historical_units_same_or_better_discount_median",
    "feature_historical_units_same_discount_std",
    "feature_historical_discount_response_confidence",
    "feature_discount_band_response_avg",
    "feature_discount_band_response_median",
    "feature_discount_band_event_count",
    "feature_probability_zero_demand_same_or_better_discount",
    "feature_probability_low_demand_vs_baseline_same_or_better_discount",
    "feature_probability_demand_exceeds_allocation_same_or_better_discount",
    "feature_probability_units_below_allocation_same_or_better_discount",
    "feature_probability_stockout_vs_stock_basis_same_or_better_discount",
    "feature_promo_history_evidence_strength",
    "feature_sparse_history_penalty",
    "feature_order_evidence_quality_score",
    "feature_overallocation_risk_score",
    "feature_historical_comparable_promo_event_count",
    "feature_historical_zero_sale_after_buy_rate",
    "feature_same_discount_success_rate_56d",
    "feature_historical_trapped_capital_rate",
    "feature_historical_sell_through_on_accepted_qty",
    "feature_historical_overforecast_bias",
    "feature_historical_allocation_efficiency_rate",
    "feature_historical_overallocation_above_floor_rate",
    "feature_historical_residual_above_floor_units_avg",
    "feature_historical_under_floor_missed_demand_rate",
    "feature_historical_under_floor_lost_units_avg",
    "feature_historical_memory_category_fallback_flag",
    "feature_historical_memory_department_fallback_flag",
    "feature_non_promo_units_28d",
    "feature_non_promo_units_56d",
    "feature_promo_units_28d",
    "feature_promo_units_56d",
    "feature_non_promo_avg_daily_units_28d",
    "feature_non_promo_avg_daily_units_56d",
    "feature_promo_avg_daily_units_28d",
    "feature_promo_avg_daily_units_56d",
    "feature_promo_to_nonpromo_demand_ratio_28d",
    "feature_promo_to_nonpromo_demand_ratio_56d",
    "feature_discount_elasticity_proxy",
    "feature_realised_prior_promo_lift_proxy",
)

# Same-or-better-discount tolerance in decimal discount units. A prior at 19.5%
# is treated as same-or-better as a candidate at 20%.
_DISCOUNT_TOLERANCE_DECIMAL = 0.005


@dataclass(frozen=True)
class _PriorWindow:
    promo_units_14d: float
    promo_units_28d: float
    promo_units_56d: float
    promo_count_14d: int
    promo_count_28d: int
    promo_count_56d: int
    same_or_better_count_14d: int
    same_or_better_count_28d: int
    same_or_better_count_56d: int
    same_or_better_units_56d: float
    same_discount_event_count: int
    same_or_better_event_count: int
    same_discount_units_avg: float
    same_or_better_units_avg: float
    same_discount_units_median: float
    same_or_better_units_median: float
    same_discount_units_std: float
    discount_response_confidence: float
    discount_band_units_avg: float
    discount_band_units_median: float
    discount_band_event_count: int
    probability_zero_demand_same_or_better_discount: float
    probability_low_demand_vs_baseline_same_or_better_discount: float
    probability_demand_exceeds_allocation_same_or_better_discount: float
    probability_units_below_allocation_same_or_better_discount: float
    probability_stockout_vs_stock_basis_same_or_better_discount: float
    promo_history_evidence_strength: float
    sparse_history_penalty: float
    order_evidence_quality_score: float
    overallocation_risk_score: float
    historical_comparable_promo_event_count: int
    historical_zero_sale_after_buy_rate: float
    same_discount_success_rate_56d: float
    historical_trapped_capital_rate: float
    historical_sell_through_on_accepted_qty: float
    historical_overforecast_bias: float
    historical_allocation_efficiency_rate: float
    historical_overallocation_above_floor_rate: float
    historical_residual_above_floor_units_avg: float
    historical_under_floor_missed_demand_rate: float
    historical_under_floor_lost_units_avg: float
    historical_memory_category_fallback_flag: float
    historical_memory_department_fallback_flag: float
    days_since_last_promo: float  # NaN when none
    days_since_last_same_discount: float  # NaN when none
    days_since_last_better_discount: float  # NaN when none
    last_prior_promo_price: float  # NaN when none
    last_prior_discount_percent: float  # NaN when none
    last_prior_units_per_day: float  # NaN when none


@dataclass(frozen=True)
class _HistoricalComparableMemory:
    event_count: int
    zero_sale_after_buy_rate: float
    same_discount_success_rate_56d: float
    trapped_capital_rate: float
    sell_through_on_accepted_qty: float
    overforecast_bias: float
    allocation_efficiency_rate: float
    overallocation_above_floor_rate: float
    residual_above_floor_units_avg: float
    under_floor_missed_demand_rate: float
    under_floor_lost_units_avg: float
    category_fallback_flag: float
    department_fallback_flag: float


def apply_ft_prior_promo_memory(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append leakage-safe prior promo memory and historical allocation features.

    Purpose:
        Build row-grain prior-promotion memory, comparable-promotion actuals,
        and trust-floor / over-allocation history features using only completed
        promotions that ended strictly before each candidate starts.

    Inputs:
        frame: candidate promotion rows that need engineered history features.
        reference_frame: optional governed historical universe to use instead of
            the candidate frame for prior lookups during future scoring.

    Outputs:
        A copy of ``frame`` with the declared ``feature_*`` memory columns
        appended.

    Important assumptions:
        Required promotion dates and store / SKU keys can be coerced by the
        shared schema helpers. Historical actuals are valid only for completed
        prior promotions and must never come from the candidate horizon.

    Side effects:
        None. The input frames are copied before feature columns are added.

    Failure behaviour:
        Propagates schema and coercion failures from the shared schema helpers.
        Missing historical evidence yields explicit ``NaN`` / zero defaults
        rather than mixing future rows into the memory windows.
    """

    candidate = frame.copy()
    history_source = reference_frame if reference_frame is not None else candidate
    candidate_typed = coerce_promotions_frame_types(candidate)
    history_typed = coerce_promotions_frame_types(history_source)

    # Build per-row prior windows.
    windows = _compute_prior_windows(candidate_typed=candidate_typed, history_typed=history_typed)

    # Construct feature columns.
    candidate_promo_price = ensure_numeric_series(candidate_typed, "promo_price")
    candidate_discount_pct = normalize_discount_decimal(ensure_numeric_series(candidate_typed, "discount_percent"))

    last_prior_price = pd.Series([w.last_prior_promo_price for w in windows], index=candidate.index)
    last_prior_discount = pd.Series(
        [w.last_prior_discount_percent for w in windows], index=candidate.index
    )
    last_prior_upd = pd.Series(
        [w.last_prior_units_per_day for w in windows], index=candidate.index
    )
    promo_units_14 = pd.Series([w.promo_units_14d for w in windows], index=candidate.index, dtype="float64")
    promo_units_28 = pd.Series([w.promo_units_28d for w in windows], index=candidate.index, dtype="float64")
    promo_units_56 = pd.Series([w.promo_units_56d for w in windows], index=candidate.index, dtype="float64")
    promo_count_14 = pd.Series([w.promo_count_14d for w in windows], index=candidate.index, dtype="float64")
    promo_count_28 = pd.Series([w.promo_count_28d for w in windows], index=candidate.index, dtype="float64")
    promo_count_56 = pd.Series([w.promo_count_56d for w in windows], index=candidate.index, dtype="float64")
    sob_count_14 = pd.Series([w.same_or_better_count_14d for w in windows], index=candidate.index, dtype="float64")
    sob_count_28 = pd.Series([w.same_or_better_count_28d for w in windows], index=candidate.index, dtype="float64")
    sob_count_56 = pd.Series([w.same_or_better_count_56d for w in windows], index=candidate.index, dtype="float64")
    sob_units_56 = pd.Series([w.same_or_better_units_56d for w in windows], index=candidate.index, dtype="float64")
    same_discount_events = pd.Series([w.same_discount_event_count for w in windows], index=candidate.index, dtype="float64")
    same_or_better_events = pd.Series([w.same_or_better_event_count for w in windows], index=candidate.index, dtype="float64")
    same_discount_avg = pd.Series([w.same_discount_units_avg for w in windows], index=candidate.index, dtype="float64")
    same_or_better_avg = pd.Series([w.same_or_better_units_avg for w in windows], index=candidate.index, dtype="float64")
    same_discount_median = pd.Series([w.same_discount_units_median for w in windows], index=candidate.index, dtype="float64")
    same_or_better_median = pd.Series([w.same_or_better_units_median for w in windows], index=candidate.index, dtype="float64")
    same_discount_std = pd.Series([w.same_discount_units_std for w in windows], index=candidate.index, dtype="float64")
    discount_response_confidence = pd.Series([w.discount_response_confidence for w in windows], index=candidate.index, dtype="float64")
    discount_band_avg = pd.Series([w.discount_band_units_avg for w in windows], index=candidate.index, dtype="float64")
    discount_band_median = pd.Series([w.discount_band_units_median for w in windows], index=candidate.index, dtype="float64")
    discount_band_events = pd.Series([w.discount_band_event_count for w in windows], index=candidate.index, dtype="float64")
    probability_zero_demand = pd.Series(
        [w.probability_zero_demand_same_or_better_discount for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    probability_low_demand_vs_baseline = pd.Series(
        [w.probability_low_demand_vs_baseline_same_or_better_discount for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    probability_demand_exceeds_allocation = pd.Series(
        [w.probability_demand_exceeds_allocation_same_or_better_discount for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    probability_units_below_allocation = pd.Series(
        [w.probability_units_below_allocation_same_or_better_discount for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    probability_stockout_vs_stock_basis = pd.Series(
        [w.probability_stockout_vs_stock_basis_same_or_better_discount for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    evidence_strength = pd.Series(
        [w.promo_history_evidence_strength for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    sparse_history_penalty = pd.Series(
        [w.sparse_history_penalty for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    order_evidence_quality = pd.Series(
        [w.order_evidence_quality_score for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    overallocation_risk = pd.Series(
        [w.overallocation_risk_score for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_comparable_event_count = pd.Series(
        [w.historical_comparable_promo_event_count for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_zero_sale_after_buy_rate = pd.Series(
        [w.historical_zero_sale_after_buy_rate for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    same_discount_success_rate_56d = pd.Series(
        [w.same_discount_success_rate_56d for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_trapped_capital_rate = pd.Series(
        [w.historical_trapped_capital_rate for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_sell_through_on_accepted_qty = pd.Series(
        [w.historical_sell_through_on_accepted_qty for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_overforecast_bias = pd.Series(
        [w.historical_overforecast_bias for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_allocation_efficiency_rate = pd.Series(
        [w.historical_allocation_efficiency_rate for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_overallocation_above_floor_rate = pd.Series(
        [w.historical_overallocation_above_floor_rate for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_residual_above_floor_units_avg = pd.Series(
        [w.historical_residual_above_floor_units_avg for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_under_floor_missed_demand_rate = pd.Series(
        [w.historical_under_floor_missed_demand_rate for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_under_floor_lost_units_avg = pd.Series(
        [w.historical_under_floor_lost_units_avg for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_memory_category_fallback_flag = pd.Series(
        [w.historical_memory_category_fallback_flag for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    historical_memory_department_fallback_flag = pd.Series(
        [w.historical_memory_department_fallback_flag for w in windows],
        index=candidate.index,
        dtype="float64",
    )
    days_since_last_any = pd.Series([w.days_since_last_promo for w in windows], index=candidate.index)
    days_since_last_same = pd.Series([w.days_since_last_same_discount for w in windows], index=candidate.index)
    days_since_last_better = pd.Series([w.days_since_last_better_discount for w in windows], index=candidate.index)

    # Days-since features: when no prior promo exists, fill with a large sentinel
    # (999) so tree models can split it cleanly without NaN handling.
    NO_PRIOR_DAYS_SENTINEL = 999.0
    days_since_last_any_filled = days_since_last_any.fillna(NO_PRIOR_DAYS_SENTINEL).astype(float)
    days_since_last_same_filled = days_since_last_same.fillna(NO_PRIOR_DAYS_SENTINEL).astype(float)
    days_since_last_better_filled = days_since_last_better.fillna(NO_PRIOR_DAYS_SENTINEL).astype(float)

    # Memory scores in [0, 1]: closer in time and stronger relative depth = higher recall.
    # price_memory: 1 if last prior promo_price is at or below candidate price (more memorable
    # because customers anchored on cheaper price); decays with time-since.
    price_at_or_below = (last_prior_price.fillna(np.inf) <= candidate_promo_price).astype(float)
    discount_at_or_above = (
        last_prior_discount.fillna(-np.inf) + _DISCOUNT_TOLERANCE_DECIMAL >= candidate_discount_pct
    ).astype(float)
    time_decay = 1.0 / (1.0 + days_since_last_any_filled.clip(lower=0.0) / 14.0)
    price_memory_score = (price_at_or_below * time_decay).clip(0.0, 1.0)
    discount_memory_score = (discount_at_or_above * time_decay).clip(0.0, 1.0)

    # Cannibalisation risk: rises with recent promo count, recent same-or-better
    # discount count, and last-prior intensity. Bounded [0, 1].
    cannibal_raw = (
        0.4 * (promo_count_56 / 6.0).clip(upper=1.0)
        + 0.4 * (sob_count_56 / 4.0).clip(upper=1.0)
        + 0.2 * time_decay
    )
    cannibalisation_risk_score = cannibal_raw.clip(0.0, 1.0)

    # Promo-vs-baseline separation. Baseline pre-window units come from
    # the row's own pre_28d_units / pre_56d_units (already aligned strictly
    # before promo start). promo_units_*d come from prior completed promotions.
    pre_28_units = ensure_numeric_series(candidate_typed, "pre_28d_units")
    pre_56_units = ensure_numeric_series(candidate_typed, "pre_56d_units")
    non_promo_28 = (pre_28_units - promo_units_28).clip(lower=0.0)
    non_promo_56 = (pre_56_units - promo_units_56).clip(lower=0.0)
    # Days denominator: 28/56, but if all 28/56 days were on-promo we use the
    # observed days_with_sales as a denominator floor.
    pre_28_dws = ensure_numeric_series(candidate_typed, "pre_28d_days_with_sales")
    pre_56_dws = ensure_numeric_series(candidate_typed, "pre_56d_days_with_sales")
    non_promo_avg_daily_28 = safe_ratio(non_promo_28, pd.Series(28.0, index=candidate.index))
    non_promo_avg_daily_56 = safe_ratio(non_promo_56, pd.Series(56.0, index=candidate.index))
    promo_avg_daily_28 = safe_ratio(
        promo_units_28,
        pre_28_dws.where(pre_28_dws > 0, 1.0).clip(upper=28.0),
    )
    promo_avg_daily_56 = safe_ratio(
        promo_units_56,
        pre_56_dws.where(pre_56_dws > 0, 1.0).clip(upper=56.0),
    )
    promo_to_nonpromo_28 = safe_ratio(promo_avg_daily_28, non_promo_avg_daily_28)
    promo_to_nonpromo_56 = safe_ratio(promo_avg_daily_56, non_promo_avg_daily_56)

    # Discount elasticity proxy: realised lift per percentage point of discount.
    # last_prior_units_per_day vs candidate baseline daily, divided by last_prior
    # discount percent. NaN-safe by construction; falls back to 0 when no prior.
    candidate_baseline_daily = ensure_numeric_series(candidate_typed, "baseline_daily_units")
    realised_prior_lift = (
        (last_prior_upd - candidate_baseline_daily)
        / candidate_baseline_daily.where(candidate_baseline_daily > 0, np.nan)
    ).clip(lower=-1.0, upper=10.0)
    realised_prior_lift_filled = realised_prior_lift.fillna(0.0)
    elasticity_proxy = (
        realised_prior_lift_filled
        / last_prior_discount.where(last_prior_discount > 0, np.nan)
    ).clip(lower=-1.0, upper=10.0).fillna(0.0)

    out = candidate.copy()
    out["feature_prior_promo_14d_flag"] = (promo_count_14 > 0).astype(float)
    out["feature_prior_promo_28d_flag"] = (promo_count_28 > 0).astype(float)
    out["feature_prior_promo_56d_flag"] = (promo_count_56 > 0).astype(float)
    out["feature_prior_promo_units_14d"] = promo_units_14.fillna(0.0).astype(float)
    out["feature_prior_promo_units_28d"] = promo_units_28.fillna(0.0).astype(float)
    out["feature_prior_promo_units_56d"] = promo_units_56.fillna(0.0).astype(float)
    out["feature_prior_promo_days_since_last_promo"] = days_since_last_any_filled
    out["feature_prior_same_or_better_discount_14d_flag"] = (sob_count_14 > 0).astype(float)
    out["feature_prior_same_or_better_discount_28d_flag"] = (sob_count_28 > 0).astype(float)
    out["feature_prior_same_or_better_discount_56d_flag"] = (sob_count_56 > 0).astype(float)
    out["feature_prior_same_or_better_discount_units_56d"] = sob_units_56.fillna(0.0).astype(float)
    out["feature_prior_same_discount_days_since_last_promo"] = days_since_last_same_filled
    out["feature_prior_better_discount_days_since_last_promo"] = days_since_last_better_filled
    out["feature_prior_promo_price_memory_score"] = price_memory_score.fillna(0.0).astype(float)
    out["feature_prior_promo_discount_memory_score"] = discount_memory_score.fillna(0.0).astype(float)
    out["feature_prior_promo_cannibalisation_risk_score"] = cannibalisation_risk_score.fillna(0.0).astype(float)
    out["feature_historical_promo_events_same_discount"] = same_discount_events.fillna(0.0).astype(float)
    out["feature_historical_promo_events_same_or_better_discount"] = same_or_better_events.fillna(0.0).astype(float)
    out["feature_historical_units_same_discount_avg"] = same_discount_avg.fillna(0.0).astype(float)
    out["feature_historical_units_same_or_better_discount_avg"] = same_or_better_avg.fillna(0.0).astype(float)
    out["feature_historical_units_same_discount_median"] = same_discount_median.fillna(0.0).astype(float)
    out["feature_historical_units_same_or_better_discount_median"] = same_or_better_median.fillna(0.0).astype(float)
    out["feature_historical_units_same_discount_std"] = same_discount_std.fillna(0.0).astype(float)
    out["feature_historical_discount_response_confidence"] = discount_response_confidence.fillna(0.0).clip(0.0, 1.0).astype(float)
    out["feature_discount_band_response_avg"] = discount_band_avg.fillna(0.0).astype(float)
    out["feature_discount_band_response_median"] = discount_band_median.fillna(0.0).astype(float)
    out["feature_discount_band_event_count"] = discount_band_events.fillna(0.0).astype(float)
    out["feature_probability_zero_demand_same_or_better_discount"] = probability_zero_demand.clip(0.0, 1.0)
    out["feature_probability_low_demand_vs_baseline_same_or_better_discount"] = probability_low_demand_vs_baseline.clip(0.0, 1.0)
    out["feature_probability_demand_exceeds_allocation_same_or_better_discount"] = probability_demand_exceeds_allocation.clip(0.0, 1.0)
    out["feature_probability_units_below_allocation_same_or_better_discount"] = probability_units_below_allocation.clip(0.0, 1.0)
    out["feature_probability_stockout_vs_stock_basis_same_or_better_discount"] = probability_stockout_vs_stock_basis.clip(0.0, 1.0)
    out["feature_promo_history_evidence_strength"] = evidence_strength.fillna(0.0).clip(0.0, 1.0).astype(float)
    out["feature_sparse_history_penalty"] = sparse_history_penalty.fillna(1.0).clip(0.0, 1.0).astype(float)
    out["feature_order_evidence_quality_score"] = order_evidence_quality.fillna(0.0).clip(0.0, 1.0).astype(float)
    out["feature_overallocation_risk_score"] = overallocation_risk.fillna(0.5).clip(0.0, 1.0).astype(float)
    out["feature_historical_comparable_promo_event_count"] = historical_comparable_event_count.fillna(0.0).astype(float)
    out["feature_historical_zero_sale_after_buy_rate"] = historical_zero_sale_after_buy_rate.clip(0.0, 1.0)
    out["feature_same_discount_success_rate_56d"] = same_discount_success_rate_56d.clip(0.0, 1.0)
    out["feature_historical_trapped_capital_rate"] = historical_trapped_capital_rate.clip(0.0, 1.0)
    out["feature_historical_sell_through_on_accepted_qty"] = historical_sell_through_on_accepted_qty.clip(0.0, 1.0)
    out["feature_historical_overforecast_bias"] = historical_overforecast_bias.clip(-1.0, 1.0)
    out["feature_historical_allocation_efficiency_rate"] = historical_allocation_efficiency_rate.clip(0.0, 1.0)
    out["feature_historical_overallocation_above_floor_rate"] = historical_overallocation_above_floor_rate.clip(0.0, 1.0)
    out["feature_historical_residual_above_floor_units_avg"] = historical_residual_above_floor_units_avg.clip(lower=0.0)
    out["feature_historical_under_floor_missed_demand_rate"] = historical_under_floor_missed_demand_rate.clip(0.0, 1.0)
    out["feature_historical_under_floor_lost_units_avg"] = historical_under_floor_lost_units_avg.clip(lower=0.0)
    out["feature_historical_memory_category_fallback_flag"] = historical_memory_category_fallback_flag.clip(0.0, 1.0)
    out["feature_historical_memory_department_fallback_flag"] = historical_memory_department_fallback_flag.clip(0.0, 1.0)
    out["feature_non_promo_units_28d"] = non_promo_28.astype(float)
    out["feature_non_promo_units_56d"] = non_promo_56.astype(float)
    out["feature_promo_units_28d"] = promo_units_28.fillna(0.0).astype(float)
    out["feature_promo_units_56d"] = promo_units_56.fillna(0.0).astype(float)
    out["feature_non_promo_avg_daily_units_28d"] = non_promo_avg_daily_28.fillna(0.0).astype(float)
    out["feature_non_promo_avg_daily_units_56d"] = non_promo_avg_daily_56.fillna(0.0).astype(float)
    out["feature_promo_avg_daily_units_28d"] = promo_avg_daily_28.fillna(0.0).astype(float)
    out["feature_promo_avg_daily_units_56d"] = promo_avg_daily_56.fillna(0.0).astype(float)
    out["feature_promo_to_nonpromo_demand_ratio_28d"] = promo_to_nonpromo_28.fillna(0.0).astype(float)
    out["feature_promo_to_nonpromo_demand_ratio_56d"] = promo_to_nonpromo_56.fillna(0.0).astype(float)
    out["feature_discount_elasticity_proxy"] = elasticity_proxy.astype(float)
    out["feature_realised_prior_promo_lift_proxy"] = realised_prior_lift_filled.astype(float)
    return out


def _compute_prior_windows(
    *,
    candidate_typed: pd.DataFrame,
    history_typed: pd.DataFrame,
) -> list[_PriorWindow]:
    """Walk per-(store, sku) histories and compute leakage-safe prior windows."""

    # Index candidate rows by their (store, sku) for grouped iteration.
    history = history_typed.copy()
    history = history.assign(
        _start=pd.to_datetime(history.get("promotion_start_date_date"), errors="coerce"),
        _end=pd.to_datetime(history.get("promotional_end_date_date"), errors="coerce"),
        _units=ensure_numeric_series(history, "actual_units_sold_promo"),
        _disc=normalize_discount_decimal(ensure_numeric_series(history, "discount_percent")),
        _price=ensure_numeric_series(history, "promo_price").replace(0.0, np.nan),
        _days=ensure_numeric_series(history, "live_promo_window_days").replace(0.0, np.nan),
    )
    history_baseline_expected_units = ensure_numeric_series(
        history,
        "baseline_expected_units",
        default=float("nan"),
    )
    history_baseline_daily_units = ensure_numeric_series(
        history,
        "baseline_daily_units",
        default=float("nan"),
    )
    history = history.assign(
        _accepted_units=first_non_null_series(
            history,
            (
                "pl_allocated",
                "pl_allocation_qty",
                "store_adjusted_qty",
                "required_implied_units",
                "stock_basis_units",
                "total_stock_available",
            ),
            positive_only=True,
        ).replace(0.0, np.nan),
        _cost=first_non_null_series(
            history,
            (
                "effective_cost_per_unit",
                "promo_effective_cost",
                "promo_cost_price",
                "last_received_cost",
            ),
            positive_only=True,
        ).replace(0.0, np.nan),
        _baseline_reference_units=history_baseline_expected_units.where(
            history_baseline_expected_units.notna(),
            history_baseline_daily_units * history["_days"],
        ),
        _category_key=_first_present_object_series(history, ("category", "category_name")),
        _department_key=_first_present_object_series(history, ("department", "department_name")),
    )
    history["_discount_band"] = history["_disc"].map(discount_band_from_decimal)

    # Build a per-(store, sku) sorted list of completed prior promotions.
    grouped = _build_grouped_history(history, ("store_number_key", "sku_number_key"))
    grouped_by_category = _build_grouped_history(history, ("store_number_key", "_category_key"))
    grouped_by_department = _build_grouped_history(history, ("store_number_key", "_department_key"))

    candidate = candidate_typed
    candidate_starts = pd.to_datetime(candidate.get("promotion_start_date_date"), errors="coerce")
    candidate_disc = normalize_discount_decimal(ensure_numeric_series(candidate, "discount_percent"))
    store_keys = candidate.get("store_number_key")
    sku_keys = candidate.get("sku_number_key")
    candidate_category_keys = _first_present_object_series(candidate, ("category", "category_name"))
    candidate_department_keys = _first_present_object_series(candidate, ("department", "department_name"))
    candidate_live_days = first_non_null_series(
        candidate,
        ("live_promo_window_days", "promo_days"),
        positive_only=True,
    ).replace(0.0, np.nan)
    candidate_baseline_expected_units = ensure_numeric_series(
        candidate,
        "baseline_expected_units",
        default=float("nan"),
    )
    candidate_baseline_daily = ensure_numeric_series(
        candidate,
        "baseline_daily_units",
        default=float("nan"),
    )
    candidate_baseline_reference_units = candidate_baseline_expected_units.where(
        candidate_baseline_expected_units.notna(),
        candidate_baseline_daily * candidate_live_days,
    )
    candidate_allocation_units = first_non_null_series(
        candidate,
        ("pl_allocated", "pl_allocation_qty", "store_adjusted_qty", "required_implied_units"),
        positive_only=True,
    ).replace(0.0, np.nan)
    candidate_stock_basis_units = first_non_null_series(
        candidate,
        ("stock_basis_units", "total_stock_available"),
        positive_only=True,
    ).replace(0.0, np.nan)

    windows: list[_PriorWindow] = []
    for row_index in range(len(candidate.index)):
        cand_start = candidate_starts.iloc[row_index]
        if pd.isna(cand_start):
            windows.append(_empty_window())
            continue
        key = (
            store_keys.iloc[row_index] if store_keys is not None else None,
            sku_keys.iloc[row_index] if sku_keys is not None else None,
        )
        priors = grouped.get(key)
        prior_rows = _strictly_prior_rows(priors, candidate_start=cand_start)
        cand_discount_value = float(candidate_disc.iloc[row_index])
        historical_memory = _select_historical_comparable_memory(
            sku_prior_rows=prior_rows,
            category_grouped_history=grouped_by_category,
            department_grouped_history=grouped_by_department,
            store_key=key[0],
            category_key=candidate_category_keys.iloc[row_index],
            department_key=candidate_department_keys.iloc[row_index],
            candidate_start=cand_start,
            candidate_discount_value=cand_discount_value,
        )
        baseline_reference_units = candidate_baseline_reference_units.iloc[row_index]
        allocation_reference_units = candidate_allocation_units.iloc[row_index]
        stock_basis_reference_units = candidate_stock_basis_units.iloc[row_index]

        promo_units_14d = 0.0
        promo_units_28d = 0.0
        promo_units_56d = 0.0
        promo_count_14d = 0
        promo_count_28d = 0
        promo_count_56d = 0
        same_or_better_count_14d = 0
        same_or_better_count_28d = 0
        same_or_better_count_56d = 0
        same_or_better_units_56d = 0.0
        same_count = 0
        same_or_better_count = 0
        same_discount_units_avg = 0.0
        same_or_better_units_avg = 0.0
        same_discount_units_median = 0.0
        same_or_better_units_median = 0.0
        same_discount_units_std = 0.0
        response_confidence = 0.0
        discount_band_units_avg = 0.0
        discount_band_units_median = 0.0
        discount_band_event_count = 0
        zero_demand_probability = float("nan")
        low_demand_vs_baseline_probability = float("nan")
        demand_exceeds_allocation_probability = float("nan")
        units_below_allocation_probability = float("nan")
        stockout_vs_stock_basis_probability = float("nan")
        evidence_strength = 0.0
        sparse_penalty = 1.0
        order_evidence_quality = 0.0
        overallocation_risk = 0.5
        last_price = float("nan")
        last_disc = float("nan")
        last_upd = float("nan")
        days_since_last = float("nan")
        days_since_same = float("nan")
        days_since_better = float("nan")

        if not prior_rows.empty:
            days_back = (cand_start - prior_rows["_end"]).dt.days
            same_or_better_mask = (
                prior_rows["_disc"].fillna(-np.inf) + _DISCOUNT_TOLERANCE_DECIMAL >= cand_discount_value
            )
            better_mask = prior_rows["_disc"].fillna(-np.inf) > cand_discount_value + _DISCOUNT_TOLERANCE_DECIMAL
            same_mask = same_or_better_mask & ~better_mask
            candidate_band = discount_band_from_decimal(cand_discount_value)
            band_mask = prior_rows["_discount_band"].astype(str).eq(candidate_band)
            same_units = prior_rows.loc[same_mask, "_units"].fillna(0.0).clip(lower=0.0)
            same_or_better_units = prior_rows.loc[same_or_better_mask, "_units"].fillna(0.0).clip(lower=0.0)
            band_units = prior_rows.loc[band_mask, "_units"].fillna(0.0).clip(lower=0.0)
            same_count = int(same_units.count())
            same_or_better_count = int(same_or_better_units.count())
            band_count = int(band_units.count())
            response_confidence = min(1.0, float(same_or_better_count) / 5.0)

            in_14 = days_back <= 14
            in_28 = days_back <= 28
            in_56 = days_back <= 56

            promo_units_14d = float(prior_rows.loc[in_14, "_units"].sum())
            promo_units_28d = float(prior_rows.loc[in_28, "_units"].sum())
            promo_units_56d = float(prior_rows.loc[in_56, "_units"].sum())
            promo_count_14d = int(in_14.sum())
            promo_count_28d = int(in_28.sum())
            promo_count_56d = int(in_56.sum())
            same_or_better_count_14d = int((in_14 & same_or_better_mask).sum())
            same_or_better_count_28d = int((in_28 & same_or_better_mask).sum())
            same_or_better_count_56d = int((in_56 & same_or_better_mask).sum())
            same_or_better_units_56d = float(prior_rows.loc[in_56 & same_or_better_mask, "_units"].sum())
            same_discount_units_avg = float(same_units.mean()) if same_count > 0 else 0.0
            same_or_better_units_avg = float(same_or_better_units.mean()) if same_or_better_count > 0 else 0.0
            same_discount_units_median = float(same_units.median()) if same_count > 0 else 0.0
            same_or_better_units_median = float(same_or_better_units.median()) if same_or_better_count > 0 else 0.0
            same_discount_units_std = float(same_units.std(ddof=0)) if same_count > 1 else 0.0
            discount_band_units_avg = float(band_units.mean()) if band_count > 0 else 0.0
            discount_band_units_median = float(band_units.median()) if band_count > 0 else 0.0
            discount_band_event_count = band_count

            # Last-prior values (nearest in time).
            last_prior_idx = prior_rows.sort_values("_end", kind="mergesort").index[-1]
            last_units = float(prior_rows.at[last_prior_idx, "_units"])
            last_days = float(prior_rows.at[last_prior_idx, "_days"]) if not pd.isna(prior_rows.at[last_prior_idx, "_days"]) else np.nan
            last_upd = (last_units / last_days) if (last_days and not np.isnan(last_days) and last_days > 0) else np.nan
            last_price = float(prior_rows.at[last_prior_idx, "_price"]) if not pd.isna(prior_rows.at[last_prior_idx, "_price"]) else np.nan
            last_disc = float(prior_rows.at[last_prior_idx, "_disc"]) if not pd.isna(prior_rows.at[last_prior_idx, "_disc"]) else np.nan
            days_since_last = float(days_back.loc[last_prior_idx])

            same_disc_days = days_back.loc[same_mask]
            better_disc_days = days_back.loc[better_mask]
            days_since_same = float(same_disc_days.min()) if not same_disc_days.empty else float("nan")
            days_since_better = float(better_disc_days.min()) if not better_disc_days.empty else float("nan")
            zero_demand_probability = _probability_at_or_below(same_or_better_units, 0.0)
            low_demand_vs_baseline_probability = _probability_at_or_below(
                same_or_better_units,
                baseline_reference_units,
            )
            demand_exceeds_allocation_probability = _probability_above(
                same_or_better_units,
                allocation_reference_units,
            )
            units_below_allocation_probability = _probability_below(
                same_or_better_units,
                allocation_reference_units,
            )
            stockout_vs_stock_basis_probability = _probability_above(
                same_or_better_units,
                stock_basis_reference_units,
            )
            evidence_strength = min(1.0, float(same_or_better_count) / 5.0)
            sparse_penalty = 1.0 - evidence_strength
            recency_score = 0.0 if np.isnan(days_since_last) else 1.0 / (1.0 + max(days_since_last, 0.0) / 56.0)
            order_evidence_quality = (0.7 * evidence_strength + 0.3 * recency_score) if same_or_better_count > 0 else 0.0
            empirical_risk_components = [
                probability
                for probability in (
                    zero_demand_probability,
                    low_demand_vs_baseline_probability,
                    units_below_allocation_probability,
                )
                if not np.isnan(probability)
            ]
            empirical_risk = (
                float(np.mean(empirical_risk_components))
                if empirical_risk_components
                else float("nan")
            )
            if np.isnan(empirical_risk):
                overallocation_risk = 0.5 * sparse_penalty
            else:
                overallocation_risk = float(
                    np.clip(
                        0.65 * empirical_risk + 0.35 * sparse_penalty,
                        0.0,
                        1.0,
                    )
                )

        windows.append(
            _PriorWindow(
                promo_units_14d=promo_units_14d,
                promo_units_28d=promo_units_28d,
                promo_units_56d=promo_units_56d,
                promo_count_14d=promo_count_14d,
                promo_count_28d=promo_count_28d,
                promo_count_56d=promo_count_56d,
                same_or_better_count_14d=same_or_better_count_14d,
                same_or_better_count_28d=same_or_better_count_28d,
                same_or_better_count_56d=same_or_better_count_56d,
                same_or_better_units_56d=same_or_better_units_56d,
                same_discount_event_count=same_count,
                same_or_better_event_count=same_or_better_count,
                same_discount_units_avg=same_discount_units_avg,
                same_or_better_units_avg=same_or_better_units_avg,
                same_discount_units_median=same_discount_units_median,
                same_or_better_units_median=same_or_better_units_median,
                same_discount_units_std=same_discount_units_std,
                discount_response_confidence=response_confidence,
                discount_band_units_avg=discount_band_units_avg,
                discount_band_units_median=discount_band_units_median,
                discount_band_event_count=discount_band_event_count,
                probability_zero_demand_same_or_better_discount=zero_demand_probability,
                probability_low_demand_vs_baseline_same_or_better_discount=low_demand_vs_baseline_probability,
                probability_demand_exceeds_allocation_same_or_better_discount=demand_exceeds_allocation_probability,
                probability_units_below_allocation_same_or_better_discount=units_below_allocation_probability,
                probability_stockout_vs_stock_basis_same_or_better_discount=stockout_vs_stock_basis_probability,
                promo_history_evidence_strength=evidence_strength,
                sparse_history_penalty=sparse_penalty,
                order_evidence_quality_score=order_evidence_quality,
                overallocation_risk_score=overallocation_risk,
                historical_comparable_promo_event_count=historical_memory.event_count,
                historical_zero_sale_after_buy_rate=historical_memory.zero_sale_after_buy_rate,
                same_discount_success_rate_56d=historical_memory.same_discount_success_rate_56d,
                historical_trapped_capital_rate=historical_memory.trapped_capital_rate,
                historical_sell_through_on_accepted_qty=historical_memory.sell_through_on_accepted_qty,
                historical_overforecast_bias=historical_memory.overforecast_bias,
                historical_allocation_efficiency_rate=historical_memory.allocation_efficiency_rate,
                historical_overallocation_above_floor_rate=historical_memory.overallocation_above_floor_rate,
                historical_residual_above_floor_units_avg=historical_memory.residual_above_floor_units_avg,
                historical_under_floor_missed_demand_rate=historical_memory.under_floor_missed_demand_rate,
                historical_under_floor_lost_units_avg=historical_memory.under_floor_lost_units_avg,
                historical_memory_category_fallback_flag=historical_memory.category_fallback_flag,
                historical_memory_department_fallback_flag=historical_memory.department_fallback_flag,
                days_since_last_promo=days_since_last,
                days_since_last_same_discount=days_since_same,
                days_since_last_better_discount=days_since_better,
                last_prior_promo_price=last_price,
                last_prior_discount_percent=last_disc,
                last_prior_units_per_day=last_upd if not (last_upd is None or (isinstance(last_upd, float) and np.isnan(last_upd))) else float("nan"),
            )
        )
    # `_compute_prior_windows` end.
    return windows


def _empty_window() -> _PriorWindow:
    return _PriorWindow(
        promo_units_14d=0.0,
        promo_units_28d=0.0,
        promo_units_56d=0.0,
        promo_count_14d=0,
        promo_count_28d=0,
        promo_count_56d=0,
        same_or_better_count_14d=0,
        same_or_better_count_28d=0,
        same_or_better_count_56d=0,
        same_or_better_units_56d=0.0,
        same_discount_event_count=0,
        same_or_better_event_count=0,
        same_discount_units_avg=0.0,
        same_or_better_units_avg=0.0,
        same_discount_units_median=0.0,
        same_or_better_units_median=0.0,
        same_discount_units_std=0.0,
        discount_response_confidence=0.0,
        discount_band_units_avg=0.0,
        discount_band_units_median=0.0,
        discount_band_event_count=0,
        probability_zero_demand_same_or_better_discount=float("nan"),
        probability_low_demand_vs_baseline_same_or_better_discount=float("nan"),
        probability_demand_exceeds_allocation_same_or_better_discount=float("nan"),
        probability_units_below_allocation_same_or_better_discount=float("nan"),
        probability_stockout_vs_stock_basis_same_or_better_discount=float("nan"),
        promo_history_evidence_strength=0.0,
        sparse_history_penalty=1.0,
        order_evidence_quality_score=0.0,
        overallocation_risk_score=0.5,
        historical_comparable_promo_event_count=0,
        historical_zero_sale_after_buy_rate=float("nan"),
        same_discount_success_rate_56d=float("nan"),
        historical_trapped_capital_rate=float("nan"),
        historical_sell_through_on_accepted_qty=float("nan"),
        historical_overforecast_bias=float("nan"),
        historical_allocation_efficiency_rate=float("nan"),
        historical_overallocation_above_floor_rate=float("nan"),
        historical_residual_above_floor_units_avg=float("nan"),
        historical_under_floor_missed_demand_rate=float("nan"),
        historical_under_floor_lost_units_avg=float("nan"),
        historical_memory_category_fallback_flag=0.0,
        historical_memory_department_fallback_flag=0.0,
        days_since_last_promo=float("nan"),
        days_since_last_same_discount=float("nan"),
        days_since_last_better_discount=float("nan"),
        last_prior_promo_price=float("nan"),
        last_prior_discount_percent=float("nan"),
        last_prior_units_per_day=float("nan"),
    )


def _probability_at_or_below(values: pd.Series, threshold: float) -> float:
    if values.empty or pd.isna(threshold):
        return float("nan")
    return float((values <= float(threshold)).mean())


def _probability_below(values: pd.Series, threshold: float) -> float:
    if values.empty or pd.isna(threshold):
        return float("nan")
    return float((values < float(threshold)).mean())


def _probability_above(values: pd.Series, threshold: float) -> float:
    if values.empty or pd.isna(threshold):
        return float("nan")
    return float((values > float(threshold)).mean())


def _build_grouped_history(
    history: pd.DataFrame,
    key_columns: tuple[str, ...],
) -> dict[tuple[object, ...], pd.DataFrame]:
    grouped_history: dict[tuple[object, ...], pd.DataFrame] = {}
    for key, group in history.groupby(list(key_columns), dropna=False, sort=False):
        key_tuple = key if isinstance(key, tuple) else (key,)
        grouped_history[tuple(key_tuple)] = group.sort_values("_end", kind="mergesort")
    return grouped_history


def _strictly_prior_rows(
    priors: pd.DataFrame | None,
    *,
    candidate_start: pd.Timestamp,
) -> pd.DataFrame:
    if priors is None or priors.empty:
        return pd.DataFrame()
    prior_mask = priors["_end"].notna() & (priors["_end"] < candidate_start)
    return priors.loc[prior_mask]


def _select_historical_comparable_memory(
    *,
    sku_prior_rows: pd.DataFrame,
    category_grouped_history: dict[tuple[object, ...], pd.DataFrame],
    department_grouped_history: dict[tuple[object, ...], pd.DataFrame],
    store_key: object,
    category_key: object,
    department_key: object,
    candidate_start: pd.Timestamp,
    candidate_discount_value: float,
) -> _HistoricalComparableMemory:
    sku_rows = _recent_comparable_rows(
        sku_prior_rows,
        candidate_start=candidate_start,
        candidate_discount_value=candidate_discount_value,
    )
    if not sku_rows.empty:
        return _summarize_historical_comparable_memory(
            sku_rows,
            category_fallback=False,
            department_fallback=False,
        )
    if not _is_missing_key(store_key) and not _is_missing_key(category_key):
        category_rows = _recent_comparable_rows(
            category_grouped_history.get((store_key, category_key)),
            candidate_start=candidate_start,
            candidate_discount_value=candidate_discount_value,
        )
        if not category_rows.empty:
            return _summarize_historical_comparable_memory(
                category_rows,
                category_fallback=True,
                department_fallback=False,
            )
    if not _is_missing_key(store_key) and not _is_missing_key(department_key):
        department_rows = _recent_comparable_rows(
            department_grouped_history.get((store_key, department_key)),
            candidate_start=candidate_start,
            candidate_discount_value=candidate_discount_value,
        )
        if not department_rows.empty:
            return _summarize_historical_comparable_memory(
                department_rows,
                category_fallback=False,
                department_fallback=True,
            )
    return _empty_historical_comparable_memory()


def _recent_comparable_rows(
    priors: pd.DataFrame | None,
    *,
    candidate_start: pd.Timestamp,
    candidate_discount_value: float,
) -> pd.DataFrame:
    prior_rows = _strictly_prior_rows(priors, candidate_start=candidate_start)
    if prior_rows.empty:
        return pd.DataFrame()
    days_back = (candidate_start - prior_rows["_end"]).dt.days
    same_or_better_mask = prior_rows["_disc"].fillna(-np.inf) + _DISCOUNT_TOLERANCE_DECIMAL >= candidate_discount_value
    return prior_rows.loc[(days_back <= 56) & same_or_better_mask].copy()


def _summarize_historical_comparable_memory(
    comparable_rows: pd.DataFrame,
    *,
    category_fallback: bool,
    department_fallback: bool,
) -> _HistoricalComparableMemory:
    """Summarize comparable-promotion actuals into leak-safe memory features.

    Purpose:
        Convert strictly prior comparable promo rows into stable historical
        allocation-efficiency, over-allocation, and under-floor trust-risk
        signals for a candidate row.

    Inputs:
        comparable_rows: completed comparable promotions for one candidate.
        category_fallback: whether the rows came from the category fallback.
        department_fallback: whether the rows came from the department fallback.

    Outputs:
        A ``_HistoricalComparableMemory`` payload containing aggregated actuals
        metrics and fallback lineage flags.

    Important assumptions:
        ``comparable_rows`` already satisfy the strict-prior and same-or-better
        discount rules. Accepted units are the best governed proxy for starting
        promo availability in the historical rows.

    Side effects:
        None.

    Failure behaviour:
        Empty or non-buy comparable sets return explicit ``NaN`` metrics instead
        of fabricating certainty.
    """
    if comparable_rows.empty:
        return _empty_historical_comparable_memory()

    actual_units = comparable_rows["_units"].fillna(0.0).clip(lower=0.0)
    accepted_units = pd.to_numeric(comparable_rows["_accepted_units"], errors="coerce")
    valid_buy_mask = accepted_units.gt(0.0)
    buy_rows = comparable_rows.loc[valid_buy_mask].copy()
    if buy_rows.empty:
        return _HistoricalComparableMemory(
            event_count=int(len(comparable_rows.index)),
            zero_sale_after_buy_rate=float("nan"),
            same_discount_success_rate_56d=float("nan"),
            trapped_capital_rate=float("nan"),
            sell_through_on_accepted_qty=float("nan"),
            overforecast_bias=float("nan"),
            allocation_efficiency_rate=float("nan"),
            overallocation_above_floor_rate=float("nan"),
            residual_above_floor_units_avg=float("nan"),
            under_floor_missed_demand_rate=float("nan"),
            under_floor_lost_units_avg=float("nan"),
            category_fallback_flag=float(category_fallback),
            department_fallback_flag=float(department_fallback),
        )

    accepted_units = pd.to_numeric(buy_rows["_accepted_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    actual_units = pd.to_numeric(buy_rows["_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    clipped_actual_units = np.minimum(actual_units, accepted_units)
    leftover_units = (accepted_units - actual_units).clip(lower=0.0)
    denominator_units = accepted_units.where(accepted_units.gt(0.0))
    row_sell_through = clipped_actual_units.divide(denominator_units).replace([np.inf, -np.inf], np.nan)
    row_trapped_rate = leftover_units.divide(denominator_units).replace([np.inf, -np.inf], np.nan)
    residual_above_floor_units = (accepted_units - clipped_actual_units - 2.0).clip(lower=0.0)
    under_floor_mask = accepted_units.lt(2.0)
    under_floor_lost_units = (actual_units - accepted_units).clip(lower=0.0).where(under_floor_mask)
    unit_cost = pd.to_numeric(buy_rows["_cost"], errors="coerce").fillna(1.0).clip(lower=0.0)
    weighted_accepted_capital = accepted_units * unit_cost
    weighted_leftover_capital = leftover_units * unit_cost
    trapped_capital_denominator = weighted_accepted_capital.sum()
    if trapped_capital_denominator > 0.0:
        trapped_capital_rate = float(weighted_leftover_capital.sum() / trapped_capital_denominator)
    else:
        trapped_capital_rate = float(leftover_units.sum() / accepted_units.sum()) if accepted_units.sum() > 0.0 else float("nan")
    overforecast_denominator = accepted_units.sum()
    overforecast_bias = float((accepted_units - actual_units).sum() / overforecast_denominator) if overforecast_denominator > 0.0 else float("nan")
    success_mask = row_sell_through.ge(0.80) & row_trapped_rate.le(0.20) & actual_units.gt(0.0)

    return _HistoricalComparableMemory(
        event_count=int(len(comparable_rows.index)),
        zero_sale_after_buy_rate=float(actual_units.le(0.0).mean()),
        same_discount_success_rate_56d=float(success_mask.mean()),
        trapped_capital_rate=trapped_capital_rate,
        sell_through_on_accepted_qty=float(clipped_actual_units.sum() / accepted_units.sum()),
        overforecast_bias=overforecast_bias,
        allocation_efficiency_rate=float(clipped_actual_units.sum() / accepted_units.sum()),
        overallocation_above_floor_rate=float(residual_above_floor_units.gt(0.0).mean()),
        residual_above_floor_units_avg=float(residual_above_floor_units.mean()),
        under_floor_missed_demand_rate=float(under_floor_lost_units.gt(0.0).mean()) if under_floor_mask.any() else float("nan"),
        under_floor_lost_units_avg=float(under_floor_lost_units.mean()) if under_floor_mask.any() else float("nan"),
        category_fallback_flag=float(category_fallback),
        department_fallback_flag=float(department_fallback),
    )


def _empty_historical_comparable_memory() -> _HistoricalComparableMemory:
    """Return the explicit empty comparable-memory payload.

    Purpose:
        Provide a single governed default for candidate rows that have no valid
        comparable promo history.

    Inputs:
        None.

    Outputs:
        A ``_HistoricalComparableMemory`` instance with zero event count and
        missing metrics.

    Important assumptions:
        Missing history should remain missing rather than being coerced into a
        false zero-risk signal.

    Side effects:
        None.

    Failure behaviour:
        None.
    """
    return _HistoricalComparableMemory(
        event_count=0,
        zero_sale_after_buy_rate=float("nan"),
        same_discount_success_rate_56d=float("nan"),
        trapped_capital_rate=float("nan"),
        sell_through_on_accepted_qty=float("nan"),
        overforecast_bias=float("nan"),
        allocation_efficiency_rate=float("nan"),
        overallocation_above_floor_rate=float("nan"),
        residual_above_floor_units_avg=float("nan"),
        under_floor_missed_demand_rate=float("nan"),
        under_floor_lost_units_avg=float("nan"),
        category_fallback_flag=0.0,
        department_fallback_flag=0.0,
    )


def _first_present_object_series(
    frame: pd.DataFrame,
    column_names: tuple[str, ...],
) -> pd.Series:
    for column_name in column_names:
        if column_name in frame.columns:
            return frame[column_name].astype("object")
    return pd.Series(np.nan, index=frame.index, dtype="object")


def _is_missing_key(value: object) -> bool:
    return value is None or bool(pd.isna(value))
