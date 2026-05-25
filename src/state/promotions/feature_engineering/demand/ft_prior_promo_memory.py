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
    days_since_last_promo: float  # NaN when none
    days_since_last_same_discount: float  # NaN when none
    days_since_last_better_discount: float  # NaN when none
    last_prior_promo_price: float  # NaN when none
    last_prior_discount_percent: float  # NaN when none
    last_prior_units_per_day: float  # NaN when none


def apply_ft_prior_promo_memory(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append prior-promo memory and promo-vs-baseline features.

    Parameters
    ----------
    frame:
        Candidate rows to score (training rows or future-prediction rows).
    reference_frame:
        Optional historical-promotion universe. When provided, prior history is
        sourced from `reference_frame` only — candidate rows in `frame` cannot
        appear as prior context for each other unless they are also in
        `reference_frame`. This keeps a future-scoring run from accidentally
        leaking other future rows into the prior windows.
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
    history["_discount_band"] = history["_disc"].map(discount_band_from_decimal)

    # Build a per-(store, sku) sorted list of completed prior promotions.
    grouped: dict[tuple[object, object], pd.DataFrame] = {}
    for key, group in history.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False):
        sorted_group = group.sort_values("_end", kind="mergesort")
        grouped[tuple(key)] = sorted_group

    candidate = candidate_typed
    candidate_starts = pd.to_datetime(candidate.get("promotion_start_date_date"), errors="coerce")
    candidate_disc = normalize_discount_decimal(ensure_numeric_series(candidate, "discount_percent"))
    store_keys = candidate.get("store_number_key")
    sku_keys = candidate.get("sku_number_key")
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
        if priors is None or priors.empty:
            windows.append(_empty_window())
            continue
        # Strictly-prior filter: end < candidate_start (no overlap, no same-day reuse).
        prior_mask = priors["_end"].notna() & (priors["_end"] < cand_start)
        prior_rows = priors.loc[prior_mask]
        if prior_rows.empty:
            windows.append(_empty_window())
            continue
        days_back = (cand_start - prior_rows["_end"]).dt.days
        cand_discount_value = float(candidate_disc.iloc[row_index])
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
        baseline_reference_units = candidate_baseline_reference_units.iloc[row_index]
        allocation_reference_units = candidate_allocation_units.iloc[row_index]
        stock_basis_reference_units = candidate_stock_basis_units.iloc[row_index]

        in_14 = days_back <= 14
        in_28 = days_back <= 28
        in_56 = days_back <= 56

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
                promo_units_14d=float(prior_rows.loc[in_14, "_units"].sum()),
                promo_units_28d=float(prior_rows.loc[in_28, "_units"].sum()),
                promo_units_56d=float(prior_rows.loc[in_56, "_units"].sum()),
                promo_count_14d=int(in_14.sum()),
                promo_count_28d=int(in_28.sum()),
                promo_count_56d=int(in_56.sum()),
                same_or_better_count_14d=int((in_14 & same_or_better_mask).sum()),
                same_or_better_count_28d=int((in_28 & same_or_better_mask).sum()),
                same_or_better_count_56d=int((in_56 & same_or_better_mask).sum()),
                same_or_better_units_56d=float(prior_rows.loc[in_56 & same_or_better_mask, "_units"].sum()),
                same_discount_event_count=same_count,
                same_or_better_event_count=same_or_better_count,
                same_discount_units_avg=float(same_units.mean()) if same_count > 0 else 0.0,
                same_or_better_units_avg=float(same_or_better_units.mean()) if same_or_better_count > 0 else 0.0,
                same_discount_units_median=float(same_units.median()) if same_count > 0 else 0.0,
                same_or_better_units_median=float(same_or_better_units.median()) if same_or_better_count > 0 else 0.0,
                same_discount_units_std=float(same_units.std(ddof=0)) if same_count > 1 else 0.0,
                discount_response_confidence=response_confidence,
                discount_band_units_avg=float(band_units.mean()) if band_count > 0 else 0.0,
                discount_band_units_median=float(band_units.median()) if band_count > 0 else 0.0,
                discount_band_event_count=band_count,
                probability_zero_demand_same_or_better_discount=zero_demand_probability,
                probability_low_demand_vs_baseline_same_or_better_discount=low_demand_vs_baseline_probability,
                probability_demand_exceeds_allocation_same_or_better_discount=demand_exceeds_allocation_probability,
                probability_units_below_allocation_same_or_better_discount=units_below_allocation_probability,
                probability_stockout_vs_stock_basis_same_or_better_discount=stockout_vs_stock_basis_probability,
                promo_history_evidence_strength=evidence_strength,
                sparse_history_penalty=sparse_penalty,
                order_evidence_quality_score=order_evidence_quality,
                overallocation_risk_score=overallocation_risk,
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
