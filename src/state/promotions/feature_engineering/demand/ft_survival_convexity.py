from __future__ import annotations

"""Survival and convex-upside demand features for promotions.

Business meaning:
- estimates where staying in stock late in a promotion may create nonlinear
  upside through internal scarcity, continuity, and repeat-trust proxies
- does not claim direct competitor stock knowledge; competitor pressure is
  represented only by clearly named internal proxies

Leakage guard:
- current-row features use only decision-time inventory, baseline, and demand
  evidence
- prior-promotion evidence is restricted to rows whose promotional end date is
  strictly before the candidate promotion start date

Output columns are declared in SURVIVAL_CONVEXITY_FEATURE_COLUMNS.
"""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series, first_non_null_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio
from state.promotions.feature_engineering.shared.ft_schema_helpers import coerce_promotions_frame_types, resolve_promo_window_days


SURVIVAL_CONVEXITY_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_survival_internal_late_stockout_opportunity_proxy_score",
    "feature_survival_internal_convex_upside_proxy_score",
    "feature_survival_late_promo_capture_proxy_score",
    "feature_survival_inventory_continuity_trust_proxy_score",
    "feature_survival_internal_scarcity_capture_proxy_score",
    "feature_survival_full_promo_fulfillment_criticality_score",
    "feature_survival_prior_late_window_importance_score",
    "feature_survival_prior_availability_lift_proxy_score",
    "feature_survival_min_stock_depth_sensitivity_score",
    "feature_survival_inventory_continuity_win_rate",
    "feature_survival_convexity_confidence_score",
    "feature_survival_must_not_stock_out_flag",
)

FEATURE_COLUMNS: tuple[str, ...] = SURVIVAL_CONVEXITY_FEATURE_COLUMNS

REQUIRED_COLUMNS: tuple[str, ...] = (
    "store_number_key",
    "sku_number_key",
    "promotion_start_date_date",
    "promotional_end_date_date",
    "baseline_expected_units",
    "baseline_daily_units",
    "pre_28d_units",
    "pre_7d_units",
    "pre_7d_days_with_sales",
    "stock_basis_units",
    "total_stock_available",
    "required_implied_units",
    "pl_allocation_qty",
)

_MAX_HISTORY_EVENTS_FOR_CONFIDENCE = 4.0
_PRIOR_HISTORY_WINDOW_EVENTS = 6


def apply_ft_survival_convexity(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Append late-promo survival and convex-upside proxy features."""

    _validate_required_columns(frame)

    candidate = frame.copy()
    history_source = reference_frame if reference_frame is not None else candidate
    candidate_typed = coerce_promotions_frame_types(candidate)
    history_typed = coerce_promotions_frame_types(history_source)

    baseline_expected_units = ensure_numeric_series(candidate_typed, "baseline_expected_units").clip(lower=0.0)
    baseline_daily_units = ensure_numeric_series(candidate_typed, "baseline_daily_units").clip(lower=0.0)
    stock_basis_units = ensure_numeric_series(candidate_typed, "stock_basis_units").clip(lower=0.0)
    total_stock_available = ensure_numeric_series(candidate_typed, "total_stock_available").clip(lower=0.0)
    total_stock_available = total_stock_available.where(total_stock_available > 0.0, stock_basis_units)
    required_implied_units = ensure_numeric_series(candidate_typed, "required_implied_units").clip(lower=0.0)
    allocation_qty = ensure_numeric_series(candidate_typed, "pl_allocation_qty").clip(lower=0.0)
    pre_7d_units = ensure_numeric_series(candidate_typed, "pre_7d_units").clip(lower=0.0)
    pre_28d_units = ensure_numeric_series(candidate_typed, "pre_28d_units").clip(lower=0.0)
    pre_7d_days_with_sales = ensure_numeric_series(candidate_typed, "pre_7d_days_with_sales").clip(lower=0.0, upper=7.0)

    expected_units_anchor = pd.concat(
        [required_implied_units.where(required_implied_units > 0.0), baseline_expected_units.where(baseline_expected_units > 0.0)],
        axis=1,
    ).max(axis=1, skipna=True).fillna(0.0)
    recent_daily_units = pre_7d_units / 7.0
    prior_21d_daily_units = (pre_28d_units - pre_7d_units).clip(lower=0.0) / 21.0
    recent_momentum_score = safe_ratio(
        recent_daily_units - prior_21d_daily_units,
        baseline_daily_units.where(baseline_daily_units > 0.0, np.nan),
    ).clip(lower=0.0, upper=1.0)
    recent_selling_continuity = (pre_7d_days_with_sales / 7.0).clip(lower=0.0, upper=1.0)
    stock_depth_ratio = safe_ratio(total_stock_available, expected_units_anchor.where(expected_units_anchor > 0.0, np.nan)).clip(
        lower=0.0,
        upper=3.0,
    )
    stockout_gap_score = safe_ratio(
        (required_implied_units - total_stock_available).clip(lower=0.0),
        required_implied_units.where(required_implied_units > 0.0, np.nan),
    ).clip(lower=0.0, upper=1.0)
    allocation_depth_score = safe_ratio(
        allocation_qty,
        expected_units_anchor.where(expected_units_anchor > 0.0, np.nan),
    ).clip(lower=0.0, upper=2.0) / 2.0

    prior_features = _build_prior_survival_feature_frame(
        candidate_typed=candidate_typed,
        history_typed=history_typed,
        output_index=candidate.index,
    )
    prior_event_count = prior_features["_prior_event_count"]
    prior_late_window_importance = prior_features["feature_survival_prior_late_window_importance_score"]
    prior_availability_lift_proxy = prior_features["feature_survival_prior_availability_lift_proxy_score"]
    inventory_continuity_win_rate = prior_features["feature_survival_inventory_continuity_win_rate"]
    prior_trust_proxy = prior_features["_prior_inventory_continuity_trust_proxy"]

    historical_evidence_strength = (prior_event_count / _MAX_HISTORY_EVENTS_FOR_CONFIDENCE).clip(lower=0.0, upper=1.0)
    internal_scarcity_capture_proxy = (
        0.35 * recent_momentum_score
        + 0.25 * stockout_gap_score
        + 0.20 * prior_late_window_importance
        + 0.20 * recent_selling_continuity
    ).clip(lower=0.0, upper=1.0)
    full_promo_fulfillment_criticality = (
        0.40 * stockout_gap_score
        + 0.25 * prior_late_window_importance
        + 0.20 * recent_selling_continuity
        + 0.15 * safe_ratio(required_implied_units, baseline_expected_units.where(baseline_expected_units > 0.0, np.nan)).clip(lower=0.0, upper=2.0) / 2.0
    ).clip(lower=0.0, upper=1.0)
    min_stock_depth_sensitivity = (
        0.60 * stockout_gap_score
        + 0.25 * (1.0 - stock_depth_ratio.clip(lower=0.0, upper=1.0))
        + 0.15 * recent_momentum_score
    ).clip(lower=0.0, upper=1.0)
    late_promo_capture_proxy = (
        0.45 * prior_late_window_importance
        + 0.30 * recent_momentum_score
        + 0.25 * allocation_depth_score
    ).clip(lower=0.0, upper=1.0)
    inventory_continuity_trust_proxy = (
        0.35 * prior_trust_proxy
        + 0.25 * inventory_continuity_win_rate
        + 0.20 * prior_availability_lift_proxy
        + 0.20 * recent_selling_continuity
    ).clip(lower=0.0, upper=1.0)
    late_stockout_opportunity_proxy = (
        0.35 * stockout_gap_score
        + 0.25 * internal_scarcity_capture_proxy
        + 0.20 * late_promo_capture_proxy
        + 0.20 * prior_late_window_importance
    ).clip(lower=0.0, upper=1.0)
    convexity_confidence = (
        0.45 * historical_evidence_strength
        + 0.25 * recent_selling_continuity
        + 0.20 * ensure_numeric_series(candidate_typed, "feature_growth_curve_confidence_score").clip(lower=0.0, upper=1.0)
        + 0.10 * (baseline_expected_units.gt(0.0) & required_implied_units.gt(0.0)).astype(float)
    ).clip(lower=0.0, upper=1.0)
    internal_convex_upside_proxy = (
        0.35 * late_stockout_opportunity_proxy
        + 0.30 * late_promo_capture_proxy
        + 0.25 * inventory_continuity_trust_proxy
        + 0.10 * min_stock_depth_sensitivity
    ).mul(0.50 + 0.50 * convexity_confidence).clip(lower=0.0, upper=1.0)
    must_not_stock_out_flag = (
        full_promo_fulfillment_criticality.ge(0.60)
        & min_stock_depth_sensitivity.ge(0.45)
    ).astype(float)

    derived_columns = pd.DataFrame(
        {
            "feature_survival_internal_late_stockout_opportunity_proxy_score": late_stockout_opportunity_proxy,
            "feature_survival_internal_convex_upside_proxy_score": internal_convex_upside_proxy,
            "feature_survival_late_promo_capture_proxy_score": late_promo_capture_proxy,
            "feature_survival_inventory_continuity_trust_proxy_score": inventory_continuity_trust_proxy,
            "feature_survival_internal_scarcity_capture_proxy_score": internal_scarcity_capture_proxy,
            "feature_survival_full_promo_fulfillment_criticality_score": full_promo_fulfillment_criticality,
            "feature_survival_prior_late_window_importance_score": prior_late_window_importance,
            "feature_survival_prior_availability_lift_proxy_score": prior_availability_lift_proxy,
            "feature_survival_min_stock_depth_sensitivity_score": min_stock_depth_sensitivity,
            "feature_survival_inventory_continuity_win_rate": inventory_continuity_win_rate,
            "feature_survival_convexity_confidence_score": convexity_confidence,
            "feature_survival_must_not_stock_out_flag": must_not_stock_out_flag,
        },
        index=candidate.index,
    )
    base_columns = candidate.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _build_prior_survival_feature_frame(
    *,
    candidate_typed: pd.DataFrame,
    history_typed: pd.DataFrame,
    output_index: pd.Index,
) -> pd.DataFrame:
    output_columns = (
        "_prior_event_count",
        "feature_survival_prior_late_window_importance_score",
        "feature_survival_prior_availability_lift_proxy_score",
        "feature_survival_inventory_continuity_win_rate",
        "_prior_inventory_continuity_trust_proxy",
    )
    if candidate_typed.empty:
        return pd.DataFrame({column_name: pd.Series(dtype="float64") for column_name in output_columns}, index=output_index)

    history = history_typed.copy()
    history["_promotion_end"] = pd.to_datetime(history.get("promotional_end_date_date"), errors="coerce")
    history["_baseline_expected_units"] = first_non_null_series(
        history,
        ("baseline_expected_units", "pre_28d_units", "pre_56d_units"),
    ).clip(lower=0.0)
    history["_actual_promo_units"] = ensure_numeric_series(history, "actual_units_sold_promo").clip(lower=0.0)
    history["_stock_basis_units"] = ensure_numeric_series(history, "stock_basis_units").clip(lower=0.0)
    history["_actual_days_with_sales_promo"] = ensure_numeric_series(history, "actual_days_with_sales_promo").clip(lower=0.0)
    history["_promo_days"] = resolve_promo_window_days(history).clip(lower=1.0)

    actual_units = pd.to_numeric(history["_actual_promo_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    baseline_units = pd.to_numeric(history["_baseline_expected_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    stock_basis_units = pd.to_numeric(history["_stock_basis_units"], errors="coerce").fillna(0.0).clip(lower=0.0)
    days_with_sales_ratio = safe_ratio(
        pd.to_numeric(history["_actual_days_with_sales_promo"], errors="coerce").fillna(0.0),
        pd.to_numeric(history["_promo_days"], errors="coerce").fillna(1.0).where(lambda values: values > 0.0),
    ).clip(lower=0.0, upper=1.0)
    uplift_vs_baseline = safe_ratio(
        (actual_units - baseline_units).clip(lower=0.0),
        baseline_units.where(baseline_units > 0.0),
    ).clip(lower=0.0, upper=1.0)
    continuity_flag = (stock_basis_units.ge(actual_units) & actual_units.gt(0.0)).astype(float)
    near_sellout_flag = safe_ratio(actual_units, stock_basis_units.where(stock_basis_units > 0.0, np.nan)).ge(0.85).astype(float)
    history_metrics = pd.DataFrame(
        {
            "store_number_key": history.get("store_number_key"),
            "sku_number_key": history.get("sku_number_key"),
            "_promotion_end": history["_promotion_end"],
            "feature_survival_prior_late_window_importance_score": (0.55 * days_with_sales_ratio + 0.45 * near_sellout_flag).clip(lower=0.0, upper=1.0),
            "feature_survival_prior_availability_lift_proxy_score": (continuity_flag * uplift_vs_baseline).clip(lower=0.0, upper=1.0),
            "feature_survival_inventory_continuity_win_rate": continuity_flag.clip(lower=0.0, upper=1.0),
            "_prior_inventory_continuity_trust_proxy": (continuity_flag * days_with_sales_ratio * (0.5 + uplift_vs_baseline * 0.5)).clip(lower=0.0, upper=1.0),
        },
        index=history.index,
    ).loc[lambda values: values["_promotion_end"].notna()].copy()
    if history_metrics.empty:
        return pd.DataFrame(0.0, index=output_index, columns=output_columns)

    metric_columns = [column_name for column_name in output_columns if column_name != "_prior_event_count"]
    sort_columns = ["store_number_key", "sku_number_key", "_promotion_end"]
    history_metrics = history_metrics.sort_values(sort_columns, kind="mergesort")
    grouped_metrics = history_metrics.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False)
    rolling_metrics = grouped_metrics[metric_columns].transform(
        lambda values: values.rolling(_PRIOR_HISTORY_WINDOW_EVENTS, min_periods=1).mean()
    )
    rolling_count = grouped_metrics["_promotion_end"].transform(
        lambda values: values.rolling(_PRIOR_HISTORY_WINDOW_EVENTS, min_periods=1).count()
    )
    history_rollup = pd.concat(
        [history_metrics[["store_number_key", "sku_number_key", "_promotion_end"]], rolling_count.rename("_prior_event_count"), rolling_metrics],
        axis=1,
    )

    candidate_lookup = pd.DataFrame(
        {
            "store_number_key": candidate_typed.get("store_number_key"),
            "sku_number_key": candidate_typed.get("sku_number_key"),
            "_candidate_start": pd.to_datetime(candidate_typed.get("promotion_start_date_date"), errors="coerce"),
            "_candidate_position": range(len(candidate_typed.index)),
        },
        index=candidate_typed.index,
    ).loc[lambda values: values["_candidate_start"].notna()].copy()
    output = pd.DataFrame(0.0, index=output_index, columns=output_columns)
    if candidate_lookup.empty:
        return output

    history_by_key = {
        key: group.sort_values("_promotion_end", kind="mergesort")
        for key, group in history_rollup.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False)
    }
    for key, candidate_group in candidate_lookup.groupby(["store_number_key", "sku_number_key"], dropna=False, sort=False):
        history_group = history_by_key.get(key)
        if history_group is None or history_group.empty:
            continue
        merged = pd.merge_asof(
            candidate_group.sort_values("_candidate_start", kind="mergesort"),
            history_group,
            left_on="_candidate_start",
            right_on="_promotion_end",
            direction="backward",
            allow_exact_matches=False,
        )
        matched = merged.loc[merged["_promotion_end"].notna()].copy()
        if matched.empty:
            continue
        candidate_positions = matched["_candidate_position"].astype(int).to_numpy()
        output.iloc[candidate_positions, :] = matched.loc[:, output_columns].fillna(0.0).to_numpy()
    output["_prior_event_count"] = output["_prior_event_count"].clip(lower=0.0)
    output.loc[:, metric_columns] = output.loc[:, metric_columns].clip(lower=0.0, upper=1.0)
    return output


def _validate_required_columns(frame: pd.DataFrame) -> None:
    missing_columns = [column_name for column_name in REQUIRED_COLUMNS if column_name not in frame.columns]
    if missing_columns:
        raise ValueError(
            "ft_survival_convexity missing required columns: "
            + ", ".join(missing_columns)
        )