from __future__ import annotations

"""Schema coercion and commercial-basis helpers for promotions ft modules."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import (
    ensure_numeric_series,
    ensure_text_series,
    first_non_null_series,
)


PROMOTION_GRAIN_COLUMNS = (
    "promotion_row_key",
    "store_number_key",
    "sku_number_key",
    "promotion_start_date_date",
    "promotional_end_date_date",
)

DATE_COLUMNS = (
    "promotion_start_date",
    "promotional_end_date",
    "promotion_start_date_date",
    "promotional_end_date_date",
    "ingested_at",
    "extracted_at_utc",
    "extraction_as_of_date",
)

NUMERIC_COLUMNS = (
    "store_number",
    "sku_number",
    "promotional_sku_id",
    "catalogue_position",
    "normal_price",
    "regular_price",
    "promo_price",
    "norm_retail_inc_gst",
    "promo_retail_inc_gst",
    "promo_gst_component",
    "promo_price_ex_gst",
    "discount_amount",
    "discount_percent",
    "customer_discount",
    "scan_rebate_dollars",
    "scan_rebate_pct_last_cost",
    "last_received_cost",
    "promo_cost_price",
    "promo_effective_cost",
    "gm_normal_pct",
    "gm_promo_pct",
    "promo_gm_unit",
    "promo_gm_pct",
    "gross_profit_normal",
    "gross_profit_promo",
    "gross_profit_promo_dollars",
    "franchise_fees",
    "pack_size",
    "bar_units",
    "current_soh",
    "qty_on_order",
    "pl_allocation_qty",
    "pl_allocated",
    "store_adjusted_qty",
    "total_units_commited",
    "total_stock_available",
    "avg_8_wk_unit_sales",
    "avg_daily_units",
    "avg_1_wk_units",
    "promo_days",
    "tot_days_cover",
    "stock_turnover",
    "pl_extended_cost",
    "inventory_carrying_cost",
    "coverage_ratio_8w",
    "utilisation_ratio_8w",
    "gmroi_8w",
    "sales_promo_period_avg",
    "has_baseline_demand",
    "required_implied_daily",
    "pl_allocations_implied_multiple",
    "required_implied_multiple",
    "implied_uplift_in_sales",
    "store_number_key",
    "sku_number_key",
    "promotional_sku_id_key",
    "live_promo_window_days",
    "actual_units_sold",
    "actual_refund_units",
    "actual_refund_sales_ex_gst",
    "actual_sales_ex_gst",
    "actual_sales_inc_gst",
    "actual_units_sold_promo",
    "actual_sales_ex_gst_promo",
    "actual_sales_inc_gst_promo",
    "actual_transaction_count_promo",
    "actual_days_with_sales_promo",
    "actual_avg_units_per_selling_day_promo",
    "actual_avg_sales_per_selling_day_promo",
    "promo_sales_day_count",
    "actual_avg_daily_units",
    "actual_std_daily_units",
    "actual_peak_daily_units",
    "realised_transaction_count",
    "realised_promo_transaction_count",
    "actual_flagged_promo_units",
    "realised_sku_solo_transaction_count",
    "realised_sku_multi_item_transaction_count",
    "realised_basket_item_count_sum_when_sku_present",
    "realised_basket_item_count_median_when_sku_present",
    "realised_basket_sales_ex_gst_sum_when_sku_present",
    "realised_basket_sales_ex_gst_median_when_sku_present",
    "realised_units_in_multi_item_baskets",
    "realised_multi_item_multi_unit_transaction_count",
    "realised_weekend_transaction_count_with_sku",
    "realised_pay_cycle_transaction_count_with_sku",
    "realised_top_companion_sku_1_share",
    "realised_top_companion_sku_2_share",
    "realised_companion_concentration_index",
    "pre_56d_units",
    "pre_28d_units",
    "pre_7d_units",
    "actual_units_pre_56d",
    "actual_units_pre_28d",
    "actual_units_pre_7d",
    "pre_56d_sales_ex_gst",
    "pre_28d_sales_ex_gst",
    "pre_7d_sales_ex_gst",
    "actual_sales_ex_gst_pre_56d",
    "actual_sales_ex_gst_pre_28d",
    "actual_sales_ex_gst_pre_7d",
    "pre_56d_days_with_sales",
    "pre_28d_days_with_sales",
    "pre_7d_days_with_sales",
    "pre_56d_avg_daily_units",
    "pre_28d_avg_daily_units",
    "pre_7d_avg_daily_units",
    "pre_prior_21d_avg_daily_units",
    "pre_56d_std_daily_units",
    "pre_28d_std_daily_units",
    "pre_56d_avg_sales_ex_gst_per_selling_day",
    "pre_28d_avg_sales_ex_gst_per_selling_day",
    "pre_7d_avg_sales_ex_gst_per_selling_day",
    "post_14d_units",
    "post_14d_sales_ex_gst",
    "actual_units_post_14d",
    "actual_sales_ex_gst_post_14d",
    "post_14d_avg_daily_units",
    "post_14d_days_with_sales",
    "post_14d_avg_sales_ex_gst_per_selling_day",
    "actual_avg_sales_ex_gst_per_selling_day",
    "actual_avg_sales_inc_gst_per_selling_day",
    "actual_units_per_transaction",
    "actual_sales_ex_gst_per_transaction",
    "actual_refund_units_promo",
    "actual_refund_sales_ex_gst_promo",
    "actual_transaction_intensity",
    "actual_promo_transaction_intensity",
    "inferred_supplier_number",
    "baseline_daily_units",
    "baseline_expected_units",
    "baseline_expected_sales_ex_gst",
    "stock_basis_units",
    "required_implied_units",
    "demand_reference_units",
    "effective_cost_per_unit",
    "promo_price_ex_gst_effective",
    "regular_price_ex_gst_effective",
)


def normalize_discount_decimal(series: pd.Series) -> pd.Series:
    """Return discount values in decimal form (0.20 means 20%)."""

    numeric = pd.to_numeric(series, errors="coerce")
    non_null = numeric.dropna()
    if non_null.empty:
        return pd.Series(0.0, index=series.index, dtype="float64")
    normalized = numeric.where(numeric.abs() <= 1.0, numeric / 100.0)
    return normalized.fillna(0.0).clip(lower=0.0, upper=1.0).astype(float)


def discount_band_from_decimal(value: object) -> str:
    """Map a decimal discount into the canonical modelling/reporting band."""

    try:
        discount = float(value)
    except (TypeError, ValueError):
        discount = 0.0
    if pd.isna(discount):
        discount = 0.0
    if discount > 1.0 and discount <= 100.0:
        discount = discount / 100.0
    discount = max(discount, 0.0)
    if discount <= 0.05:
        return "none"
    if discount <= 0.15:
        return "shallow"
    if discount <= 0.30:
        return "moderate"
    if discount <= 0.50:
        return "deep"
    return "extreme"


def apply_canonical_pricing_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Resolve canonical price/discount columns used by modelling and reporting.

    Model-facing percentages stay decimal-safe: ``discount_percent`` is 0..1.
    Operator-facing surfaces may display this as 0..100 later.
    """

    working = frame.copy()
    promo_price = resolve_promo_price_ex_gst(working)
    normal_price = first_non_null_series(
        working,
        ("normal_price", "regular_price", "norm_retail_inc_gst"),
        positive_only=True,
    )
    raw_discount = normalize_discount_decimal(ensure_numeric_series(working, "discount_percent"))
    derived_discount = ((normal_price - promo_price) / normal_price.where(normal_price > 0.0)).clip(
        lower=0.0,
        upper=1.0,
    )
    canonical_discount = raw_discount.where(raw_discount > 0.0, derived_discount.fillna(0.0))

    working["promo_price"] = promo_price.fillna(0.0).clip(lower=0.0)
    working["normal_price"] = normal_price.fillna(0.0).clip(lower=0.0)
    working["discount_percent"] = canonical_discount.fillna(0.0).clip(lower=0.0, upper=1.0)
    working["discount_band"] = working["discount_percent"].map(discount_band_from_decimal)
    return working


def coerce_promotions_frame_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce known promotion columns to stable numeric and datetime types."""

    normalized = frame.copy()
    for column_name in DATE_COLUMNS:
        if column_name in normalized.columns:
            normalized[column_name] = pd.to_datetime(normalized[column_name], errors="coerce")
    for column_name in NUMERIC_COLUMNS:
        if column_name in normalized.columns:
            normalized[column_name] = pd.to_numeric(normalized[column_name], errors="coerce")
    if "promotion_row_key" not in normalized.columns:
        normalized["promotion_row_key"] = build_promotion_row_key(normalized)
    return normalized


def build_promotion_row_key(frame: pd.DataFrame) -> pd.Series:
    """Build the stable promotion x sku x store key when upstream extraction did not."""

    start_date = pd.to_datetime(
        frame.get("promotion_start_date_date", frame.get("promotion_start_date")),
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")
    end_date = pd.to_datetime(
        frame.get("promotional_end_date_date", frame.get("promotional_end_date")),
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")
    components = (
        ensure_text_series(frame, "store_number").where(lambda values: values != "", ensure_text_series(frame, "store_number_key")),
        ensure_text_series(frame, "sku_number").where(lambda values: values != "", ensure_text_series(frame, "sku_number_key")),
        start_date.fillna(""),
        end_date.fillna(""),
        ensure_text_series(frame, "promotional_sku_id").where(lambda values: values != "", ensure_text_series(frame, "promotional_sku_id_key")),
        ensure_text_series(frame, "promotion_name"),
    )
    return pd.Series(
        "|".join(str(value) for value in values)
        for values in zip(*components, strict=False)
    )


def build_promotion_network_key(frame: pd.DataFrame) -> pd.Series:
    """Return the network-level promotion key shared across stores for one event."""

    start_date = pd.to_datetime(
        frame.get("promotion_start_date_date", frame.get("promotion_start_date")),
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")
    end_date = pd.to_datetime(
        frame.get("promotional_end_date_date", frame.get("promotional_end_date")),
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")
    return (
        start_date.fillna("")
        + "|"
        + end_date.fillna("")
        + "|"
        + ensure_text_series(frame, "promotion_name")
        + "|"
        + ensure_text_series(frame, "promo_type")
    )


def build_promotion_store_event_key(frame: pd.DataFrame) -> pd.Series:
    """Return the store-scoped event key used for overlap and mix features."""

    store_number = ensure_text_series(frame, "store_number_key").where(
        lambda values: values != "",
        ensure_text_series(frame, "store_number"),
    )
    return store_number + "|" + build_promotion_network_key(frame)


def resolve_promo_window_days(frame: pd.DataFrame) -> pd.Series:
    """Resolve the live promotion length using extracted dates or source fields."""

    live_days = ensure_numeric_series(frame, "live_promo_window_days")
    fallback = live_days.where(live_days > 0.0)
    fallback = fallback.fillna(ensure_numeric_series(frame, "promo_days").where(lambda values: values > 0.0))
    if {"promotion_start_date_date", "promotional_end_date_date"}.issubset(frame.columns):
        date_days = (
            pd.to_datetime(frame["promotional_end_date_date"], errors="coerce")
            - pd.to_datetime(frame["promotion_start_date_date"], errors="coerce")
        ).dt.days.add(1)
        fallback = fallback.fillna(date_days)
    return fallback.fillna(0.0)


def resolve_allocation_basis_units(frame: pd.DataFrame) -> pd.Series:
    """Resolve the stock basis used for sell-through and allocation-risk math."""

    current_stock_plus_order = ensure_numeric_series(frame, "current_soh") + ensure_numeric_series(frame, "qty_on_order")
    working = frame.copy()
    working["__current_stock_plus_order"] = current_stock_plus_order
    return first_non_null_series(
        working,
        (
            "store_adjusted_qty",
            "pl_allocation_qty",
            "total_units_commited",
            "total_stock_available",
            "__current_stock_plus_order",
        ),
        positive_only=True,
    )


def resolve_effective_cost_per_unit(frame: pd.DataFrame) -> pd.Series:
    """Resolve the commercial cost basis used for gross-profit calculations."""

    return first_non_null_series(
        frame,
        ("promo_effective_cost", "promo_cost_price", "last_received_cost"),
        positive_only=True,
    )


def resolve_promo_price_ex_gst(frame: pd.DataFrame) -> pd.Series:
    """Resolve the ex-GST promo selling price used for sales and margin features."""

    working = frame.copy()
    working["__promo_price_ex_gst_from_inc"] = ensure_numeric_series(frame, "promo_retail_inc_gst") - ensure_numeric_series(frame, "promo_gst_component")
    return first_non_null_series(
        working,
        ("promo_price_ex_gst", "__promo_price_ex_gst_from_inc", "promo_price"),
        positive_only=True,
    )


def resolve_regular_price_ex_gst(frame: pd.DataFrame) -> pd.Series:
    """Resolve the ex-GST regular selling price used for discount features."""

    return first_non_null_series(
        frame,
        ("regular_price", "norm_retail_inc_gst"),
        positive_only=True,
    )
