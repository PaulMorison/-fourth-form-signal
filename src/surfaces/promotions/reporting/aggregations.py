from __future__ import annotations

"""Aggregated summary tables for promotions scoring outputs."""

import pandas as pd

from state.promotions.promotion_frame_schema import build_promotion_network_key


def build_summary_tables(row_frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build promotion, store, category, and supplier summaries from row scores."""

    working = row_frame.copy()
    working["promotion_network_key"] = build_promotion_network_key(working)
    promotion_summary = (
        working.groupby(
            [
                "promotion_network_key",
                "promotion_name",
                "promo_type",
                "promotion_start_date_date",
                "promotional_end_date_date",
            ],
            dropna=False,
        )
        .agg(
            predicted_units_sold=("predicted_units_sold", "sum"),
            predicted_sales_ex_gst=("predicted_sales_ex_gst", "sum"),
            predicted_gross_profit_dollars=("predicted_gross_profit_dollars", "sum"),
            predicted_sell_through_pct=("predicted_sell_through_pct", "mean"),
            predicted_overallocation_risk=("predicted_overallocation_risk", "mean"),
            predicted_underallocation_risk=("predicted_underallocation_risk", "mean"),
            predicted_stockout_risk=("predicted_stockout_risk", "mean"),
            row_count=("promotion_row_key", "count"),
            store_count=("store_number_key", "nunique"),
            sku_count=("sku_number_key", "nunique"),
        )
        .reset_index()
    )
    store_summary = (
        working.groupby("store_number_key", dropna=False)
        .agg(
            predicted_units_sold=("predicted_units_sold", "sum"),
            predicted_sales_ex_gst=("predicted_sales_ex_gst", "sum"),
            predicted_gross_profit_dollars=("predicted_gross_profit_dollars", "sum"),
            predicted_overallocation_risk=("predicted_overallocation_risk", "mean"),
            predicted_underallocation_risk=("predicted_underallocation_risk", "mean"),
            predicted_stockout_risk=("predicted_stockout_risk", "mean"),
            promotion_count=("promotion_network_key", "nunique"),
        )
        .reset_index()
    )
    category_summary = (
        working.groupby("category", dropna=False)
        .agg(
            predicted_units_sold=("predicted_units_sold", "sum"),
            predicted_sales_ex_gst=("predicted_sales_ex_gst", "sum"),
            predicted_gross_profit_dollars=("predicted_gross_profit_dollars", "sum"),
            predicted_sell_through_pct=("predicted_sell_through_pct", "mean"),
            predicted_overallocation_risk=("predicted_overallocation_risk", "mean"),
            predicted_underallocation_risk=("predicted_underallocation_risk", "mean"),
            predicted_stockout_risk=("predicted_stockout_risk", "mean"),
        )
        .reset_index()
    )
    supplier_summary = (
        working.groupby("inferred_supplier_number", dropna=False)
        .agg(
            predicted_units_sold=("predicted_units_sold", "sum"),
            predicted_sales_ex_gst=("predicted_sales_ex_gst", "sum"),
            predicted_gross_profit_dollars=("predicted_gross_profit_dollars", "sum"),
            predicted_sell_through_pct=("predicted_sell_through_pct", "mean"),
            predicted_overallocation_risk=("predicted_overallocation_risk", "mean"),
            predicted_underallocation_risk=("predicted_underallocation_risk", "mean"),
            predicted_stockout_risk=("predicted_stockout_risk", "mean"),
        )
        .reset_index()
    )
    return {
        "promotion_summary": promotion_summary,
        "store_summary": store_summary,
        "category_summary": category_summary,
        "supplier_summary": supplier_summary,
    }
