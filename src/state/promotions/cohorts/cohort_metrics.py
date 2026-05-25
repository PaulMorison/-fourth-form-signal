from __future__ import annotations

"""Reusable aggregation and weighting helpers for promotions cohort history."""

from datetime import date

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


_SIMILARITY_ANCHOR_COLUMN_MAP = {
    "anchor_mean_discount_depth_pct": "feature_discount_depth_pct",
    "anchor_mean_price_gap_pct_vs_normal": "feature_price_gap_pct_vs_normal",
    "anchor_mean_margin_pressure": "feature_effective_margin_compression_pct",
    "anchor_mean_rebate_dependency": "feature_rebate_dependency_score",
    "anchor_mean_stock_pressure": "feature_total_stock_pressure_ratio",
    "anchor_mean_allocation_pressure": "feature_allocation_vs_baseline_demand_ratio",
    "anchor_mean_overhang_risk": "feature_overhang_risk",
    "anchor_mean_baseline_demand": "feature_pre_promo_baseline_daily_units",
    "anchor_mean_demand_acceleration": "feature_recent_acceleration_ratio",
    "anchor_mean_zeta_instability": "feature_composite_promo_instability",
    "anchor_mean_field_density": "feature_field_density_score",
    "anchor_mean_context_density": "cohort_context_anchor",
    "anchor_mean_kuramoto_sync": "cohort_kuramoto_sync_anchor",
    "anchor_mean_gravity_score": "cohort_gravity_anchor",
}


def prepare_cohort_metric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Add row-level anchor columns used for cohort aggregation and similarity."""

    working = frame.copy()
    working["cohort_kuramoto_sync_anchor"] = pd.concat(
        [
            ensure_numeric_series(working, "feature_short_long_demand_phase_alignment"),
            ensure_numeric_series(working, "feature_promo_window_alignment_score"),
            ensure_numeric_series(working, "feature_category_sync_score"),
            ensure_numeric_series(working, "feature_store_sync_score"),
        ],
        axis=1,
    ).mean(axis=1)
    working["cohort_gravity_anchor"] = pd.concat(
        [
            ensure_numeric_series(working, "feature_category_gravity"),
            ensure_numeric_series(working, "feature_supplier_gravity"),
            ensure_numeric_series(working, "feature_promo_crowding_gravity"),
        ],
        axis=1,
    ).mean(axis=1)
    working["cohort_context_anchor"] = pd.concat(
        [
            ensure_numeric_series(working, "feature_store_category_promo_density"),
            ensure_numeric_series(working, "feature_supplier_promo_density"),
            ensure_numeric_series(working, "feature_store_level_promo_load"),
        ],
        axis=1,
    ).mean(axis=1)
    return working


def aggregate_cohort_metrics(
    frame: pd.DataFrame,
    *,
    group_column: str,
    as_of_date: date | str | pd.Timestamp,
    minimum_sample_size: int,
    first_value_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Aggregate cohort metrics for one cohort family at one historical cutoff."""

    working = prepare_cohort_metric_frame(frame)
    aggregation_map: dict[str, tuple[str, str]] = {
        "promo_count": ("promotion_row_key", "count"),
        "distinct_store_count": ("store_number_key", "nunique"),
        "distinct_sku_count": ("sku_number_key", "nunique"),
        "supplier_count": ("inferred_supplier_number", "nunique"),
        "department_count": ("department", "nunique"),
        "avg_units_sold": ("target_actual_units_sold", "mean"),
        "median_units_sold": ("target_actual_units_sold", "median"),
        "avg_sales_ex_gst": ("target_actual_sales_ex_gst", "mean"),
        "avg_gross_profit": ("target_actual_gross_profit_dollars", "mean"),
        "avg_sell_through_pct": ("target_sell_through_pct", "mean"),
        "avg_leftover_stock_pct": ("target_leftover_stock_pct", "mean"),
        "stockout_rate": ("target_stockout_flag", "mean"),
        "overallocation_rate": ("target_overallocation_flag", "mean"),
        "underallocation_rate": ("target_underallocation_flag", "mean"),
        "avg_realised_uplift": ("target_realised_uplift_vs_baseline", "mean"),
        "avg_post_promo_followthrough_units": ("target_post_promo_followthrough_units", "mean"),
        "avg_post_promo_followthrough_sales_ex_gst": (
            "target_post_promo_followthrough_sales_ex_gst",
            "mean",
        ),
        "avg_discount_depth_pct": ("feature_discount_depth_pct", "mean"),
        "avg_margin_pressure": ("feature_effective_margin_compression_pct", "mean"),
        "avg_overhang_risk": ("feature_overhang_risk", "mean"),
        "avg_zeta_instability": ("feature_composite_promo_instability", "mean"),
        "avg_kuramoto_sync": ("cohort_kuramoto_sync_anchor", "mean"),
        "avg_gravity_score": ("cohort_gravity_anchor", "mean"),
        "last_seen_date": ("promotional_end_date_date", "max"),
    }
    for output_name, input_column in _SIMILARITY_ANCHOR_COLUMN_MAP.items():
        aggregation_map[output_name] = (input_column, "mean")
    for column_name in first_value_columns:
        aggregation_map[column_name] = (column_name, "first")
    summary = working.groupby(group_column, dropna=False).agg(**aggregation_map).reset_index()
    as_of_timestamp = pd.Timestamp(as_of_date).normalize()
    last_seen = pd.to_datetime(summary["last_seen_date"], errors="coerce")
    days_since_last_seen = (as_of_timestamp - last_seen).dt.days.clip(lower=0)
    summary["last_seen_date"] = last_seen.dt.strftime("%Y-%m-%d")
    summary["days_since_last_seen"] = days_since_last_seen.fillna(0).astype(int)
    if minimum_sample_size > 0:
        summary["cohort_sample_weight"] = (
            summary["promo_count"].astype(float) / float(minimum_sample_size)
        ).clip(lower=0.0, upper=1.0)
    else:
        summary["cohort_sample_weight"] = 1.0
    summary["cohort_recency_weight"] = 1.0 / (1.0 + summary["days_since_last_seen"].astype(float) / 180.0)
    summary["meets_minimum_sample_size"] = (
        summary["promo_count"].astype(int) >= int(minimum_sample_size)
    ).astype(int)
    return summary


def add_prefixed_trailing_metrics(
    summary: pd.DataFrame,
    *,
    frame: pd.DataFrame,
    group_column: str,
    as_of_date: date | str | pd.Timestamp,
    minimum_sample_size: int,
    months: int,
    first_value_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Join trailing-window cohort metrics onto a base cohort summary frame."""

    as_of_timestamp = pd.Timestamp(as_of_date).normalize()
    window_start = as_of_timestamp - pd.DateOffset(months=months)
    history_dates = pd.to_datetime(frame["promotional_end_date_date"], errors="coerce")
    window_frame = frame.loc[history_dates >= window_start].copy()
    if window_frame.empty:
        return summary
    trailing_summary = aggregate_cohort_metrics(
        window_frame,
        group_column=group_column,
        as_of_date=as_of_date,
        minimum_sample_size=minimum_sample_size,
        first_value_columns=first_value_columns,
    )
    prefix = f"trailing_{months}m_"
    rename_map = {
        column_name: prefix + column_name
        for column_name in trailing_summary.columns
        if column_name not in {group_column, *first_value_columns}
    }
    trailing_summary = trailing_summary.rename(columns=rename_map)
    return summary.merge(trailing_summary, on=[group_column, *first_value_columns], how="left")