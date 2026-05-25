from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def build_completed_promotions_base_frame() -> pd.DataFrame:
    scenarios = [
        (1, 100, 1, 60.0, 100.0, 82.0, 72.0, "Skin Care", "Beauty", 10),
        (1, 100, 2, 68.0, 90.0, 93.0, 88.0, "Skin Care", "Beauty", 10),
        (1, 100, 3, 58.0, 125.0, 38.0, 54.0, "Skin Care", "Beauty", 10),
        (2, 100, 4, 62.0, 82.0, 74.0, 70.0, "Skin Care", "Beauty", 10),
        (1, 101, 5, 34.0, 62.0, 28.0, 32.0, "Wellness", "Health", 11),
        (2, 101, 6, 48.0, 80.0, 86.0, 78.0, "Wellness", "Health", 11),
        (1, 102, 7, 42.0, 92.0, 39.0, 40.0, "Cosmetics", "Beauty", 12),
        (2, 102, 8, 45.0, 70.0, 72.0, 69.0, "Cosmetics", "Beauty", 12),
    ]
    return _build_rows(scenarios=scenarios, future=False)


def build_future_promotions_base_frame() -> pd.DataFrame:
    scenarios = [
        (1, 100, 9, 70.0, 95.0, 0.0, 82.0, "Skin Care", "Beauty", 10),
        (2, 101, 10, 52.0, 78.0, 0.0, 83.0, "Wellness", "Health", 11),
    ]
    return _build_rows(scenarios=scenarios, future=True)


def build_repeating_promotions_base_frame() -> pd.DataFrame:
    frame = build_completed_promotions_base_frame().copy()
    frame["promotion_name"] = [
        "Mega Sale",
        "Mega Sale",
        "Glow Reset",
        "Mega Sale",
        "Wellness Week",
        "Wellness Week",
        "Glow Reset",
        "Clearance Push",
    ]
    frame["promo_type"] = [
        "catalogue",
        "catalogue",
        "multi_buy",
        "catalogue",
        "amount_off",
        "amount_off",
        "multi_buy",
        "clearance",
    ]
    frame["customer_offer"] = [
        "20 percent off",
        "20 percent off",
        "buy 2 get 1 bonus",
        "20 percent off",
        "$5 off",
        "$5 off",
        "buy 2 get 1 bonus",
        "30 percent off",
    ]
    frame["source_file"] = [
        "campaign_alpha.csv",
        "campaign_alpha.csv",
        "campaign_beta.csv",
        "campaign_alpha.csv",
        "campaign_gamma.csv",
        "campaign_gamma.csv",
        "campaign_beta.csv",
        "campaign_delta.csv",
    ]
    frame.loc[frame["promotion_name"] == "Mega Sale", "inferred_supplier_number"] = 10
    frame.loc[frame["promotion_name"] == "Wellness Week", "inferred_supplier_number"] = 11
    frame.loc[frame["promotion_name"] == "Glow Reset", "inferred_supplier_number"] = 12
    frame.loc[frame["promotion_name"] == "Clearance Push", "inferred_supplier_number"] = 15
    return frame


def build_repeating_promotions_training_ready_frame() -> pd.DataFrame:
    from state.promotions.feature_engineering import PromotionFeatureEngineer
    from state.promotions.targets import PromotionTargetEngineer

    base_frame = build_repeating_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    return target_result.frame.merge(
        feature_result.frame[["promotion_row_key", *feature_result.feature_columns]],
        on="promotion_row_key",
        how="left",
    )


def _build_rows(*, scenarios: list[tuple[int, int, int, float, float, float, float, str, str, int]], future: bool) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for store_number, sku_number, month_number, baseline_units, stock_basis, actual_units, required_units, category, department, supplier in scenarios:
        start_date = date(2024, month_number, 1)
        end_date = start_date + timedelta(days=6)
        promo_price = 15.0 + (sku_number % 3)
        regular_price = promo_price + 5.0
        promo_gst_component = promo_price * (1.0 / 11.0)
        promo_retail_inc_gst = promo_price + promo_gst_component
        norm_retail_inc_gst = regular_price + (regular_price * (1.0 / 11.0))
        actual_sales_ex_gst = actual_units * promo_price
        actual_sales_inc_gst = actual_sales_ex_gst * 1.1
        actual_transaction_count = max(int(actual_units // 2), 1) if actual_units else 0
        promo_sales_day_count = 7 if actual_units else 0
        actual_avg_units_per_selling_day = actual_units / max(promo_sales_day_count, 1) if actual_units else 0.0
        actual_avg_sales_per_selling_day = actual_sales_ex_gst / max(promo_sales_day_count, 1) if actual_units else 0.0
        pre_56d_days_with_sales = 42.0
        pre_28d_days_with_sales = 21.0
        pre_7d_days_with_sales = 6.0
        pre_56d_units = baseline_units * 2.0
        pre_28d_units = baseline_units
        pre_7d_units = baseline_units * 0.3
        pre_56d_sales_ex_gst = baseline_units * promo_price * 2.0
        pre_28d_sales_ex_gst = baseline_units * promo_price
        pre_7d_sales_ex_gst = baseline_units * promo_price * 0.35
        post_14d_units = 4.0 if not future and actual_units >= stock_basis * 0.95 else 0.0
        post_14d_sales_ex_gst = 4.0 * promo_price if not future and actual_units >= stock_basis * 0.95 else 0.0
        post_14d_days_with_sales = 4.0 if not future and actual_units >= stock_basis * 0.95 else 0.0
        rows.append(
            {
                "promotion_row_key": f"{store_number}|{sku_number}|{start_date.isoformat()}|{end_date.isoformat()}",
                "store_number": store_number,
                "store_number_key": store_number,
                "sku_number": sku_number,
                "sku_number_key": sku_number,
                "promotional_sku_id": sku_number * 10,
                "promotional_sku_id_key": sku_number * 10,
                "promotion_name": f"Promo {sku_number}",
                "promo_type": "catalogue",
                "customer_offer": "20 percent off",
                "sku_description": f"SKU {sku_number}",
                "department": department,
                "category": category,
                "source_file": f"promo_batch_{month_number}.csv",
                "ingested_at": f"{start_date.isoformat()}T06:00:00Z",
                "promotion_start_date": start_date.isoformat(),
                "promotional_end_date": end_date.isoformat(),
                "promotion_start_date_date": start_date.isoformat(),
                "promotional_end_date_date": end_date.isoformat(),
                "regular_price": regular_price,
                "promo_price": promo_price,
                "norm_retail_inc_gst": norm_retail_inc_gst,
                "promo_retail_inc_gst": promo_retail_inc_gst,
                "promo_gst_component": promo_gst_component,
                "promo_price_ex_gst": promo_price,
                "discount_amount": regular_price - promo_price,
                "discount_percent": ((regular_price - promo_price) / regular_price) * 100.0,
                "customer_discount": regular_price - promo_price,
                "scan_rebate_dollars": 1.0,
                "scan_rebate_pct_last_cost": 0.125,
                "last_received_cost": 8.0,
                "promo_cost_price": 7.5,
                "promo_effective_cost": 7.0,
                "gm_normal_pct": 0.42,
                "gm_promo_pct": 0.28,
                "promo_gm_unit": promo_price - 7.0,
                "promo_gm_pct": (promo_price - 7.0) / promo_price,
                "gross_profit_normal": 12.0,
                "gross_profit_promo": 8.0,
                "gross_profit_promo_dollars": 8.0 * max(baseline_units, 1.0),
                "franchise_fees": 0.35,
                "pack_size": 1.0,
                "bar_units": 1.0,
                "current_soh": stock_basis,
                "qty_on_order": 0.0,
                "pl_allocation_qty": stock_basis,
                "pl_allocated": stock_basis,
                "store_adjusted_qty": stock_basis,
                "total_units_commited": stock_basis,
                "total_stock_available": stock_basis,
                "avg_8_wk_unit_sales": baseline_units,
                "avg_daily_units": baseline_units / 7.0,
                "avg_1_wk_units": baseline_units,
                "promo_days": 7.0,
                "tot_days_cover": stock_basis / max(baseline_units / 7.0, 1.0),
                "stock_turnover": baseline_units / max(stock_basis, 1.0),
                "pl_extended_cost": stock_basis * 7.0,
                "inventory_carrying_cost": stock_basis * 0.05,
                "coverage_ratio_8w": stock_basis / max(baseline_units, 1.0),
                "utilisation_ratio_8w": baseline_units / max(stock_basis, 1.0),
                "gmroi_8w": 1.5,
                "sales_promo_period_avg": baseline_units * promo_price,
                "has_baseline_demand": 1.0,
                "required_implied_daily": required_units / 7.0,
                "pl_allocations_implied_multiple": stock_basis / max(baseline_units, 1.0),
                "required_implied_multiple": required_units / max(baseline_units, 1.0),
                "implied_uplift_in_sales": max(required_units - baseline_units, 0.0),
                "live_promo_window_days": 7.0,
                "pre_56d_units": pre_56d_units,
                "pre_28d_units": pre_28d_units,
                "pre_7d_units": pre_7d_units,
                "actual_units_pre_56d": pre_56d_units,
                "actual_units_pre_28d": pre_28d_units,
                "actual_units_pre_7d": pre_7d_units,
                "pre_56d_sales_ex_gst": pre_56d_sales_ex_gst,
                "pre_28d_sales_ex_gst": pre_28d_sales_ex_gst,
                "pre_7d_sales_ex_gst": pre_7d_sales_ex_gst,
                "actual_sales_ex_gst_pre_56d": pre_56d_sales_ex_gst,
                "actual_sales_ex_gst_pre_28d": pre_28d_sales_ex_gst,
                "actual_sales_ex_gst_pre_7d": pre_7d_sales_ex_gst,
                "pre_56d_days_with_sales": pre_56d_days_with_sales,
                "pre_28d_days_with_sales": pre_28d_days_with_sales,
                "pre_7d_days_with_sales": pre_7d_days_with_sales,
                "pre_56d_avg_daily_units": baseline_units / 7.0,
                "pre_28d_avg_daily_units": baseline_units / 7.0,
                "pre_7d_avg_daily_units": baseline_units / 7.0 * 1.05,
                "pre_prior_21d_avg_daily_units": baseline_units / 7.0 * 0.95,
                "pre_56d_std_daily_units": baseline_units / 28.0,
                "pre_28d_std_daily_units": baseline_units / 30.0,
                "pre_56d_avg_sales_ex_gst_per_selling_day": pre_56d_sales_ex_gst / max(pre_56d_days_with_sales, 1.0),
                "pre_28d_avg_sales_ex_gst_per_selling_day": pre_28d_sales_ex_gst / max(pre_28d_days_with_sales, 1.0),
                "pre_7d_avg_sales_ex_gst_per_selling_day": pre_7d_sales_ex_gst / max(pre_7d_days_with_sales, 1.0),
                "post_14d_units": post_14d_units,
                "post_14d_sales_ex_gst": post_14d_sales_ex_gst,
                "actual_units_post_14d": post_14d_units,
                "actual_sales_ex_gst_post_14d": post_14d_sales_ex_gst,
                "post_14d_avg_daily_units": 0.3,
                "post_14d_days_with_sales": post_14d_days_with_sales,
                "post_14d_avg_sales_ex_gst_per_selling_day": post_14d_sales_ex_gst / max(post_14d_days_with_sales, 1.0) if post_14d_days_with_sales else 0.0,
                "actual_units_sold": actual_units,
                "actual_units_sold_promo": actual_units,
                "actual_sales_ex_gst": actual_sales_ex_gst,
                "actual_sales_ex_gst_promo": actual_sales_ex_gst,
                "actual_sales_inc_gst": actual_sales_inc_gst,
                "actual_sales_inc_gst_promo": actual_sales_inc_gst,
                "actual_refund_sales_ex_gst": 0.0,
                "actual_avg_daily_units": actual_units / 7.0 if actual_units else 0.0,
                "actual_std_daily_units": actual_units / 35.0 if actual_units else 0.0,
                "actual_peak_daily_units": actual_units / 5.0 if actual_units else 0.0,
                "actual_avg_sales_ex_gst_per_selling_day": actual_sales_ex_gst / max(promo_sales_day_count, 1) if actual_units else 0.0,
                "actual_avg_sales_inc_gst_per_selling_day": actual_sales_inc_gst / max(promo_sales_day_count, 1) if actual_units else 0.0,
                "actual_avg_units_per_selling_day_promo": actual_avg_units_per_selling_day,
                "actual_avg_sales_per_selling_day_promo": actual_avg_sales_per_selling_day,
                "actual_units_per_transaction": actual_units / max(actual_transaction_count, 1) if actual_units else 0.0,
                "actual_sales_ex_gst_per_transaction": actual_sales_ex_gst / max(actual_transaction_count, 1) if actual_units else 0.0,
                "realised_transaction_count": actual_transaction_count,
                "realised_promo_transaction_count": actual_transaction_count,
                "actual_transaction_count_promo": actual_transaction_count,
                "actual_days_with_sales_promo": promo_sales_day_count,
                "actual_transaction_intensity": actual_transaction_count / 7.0 if actual_units else 0.0,
                "actual_promo_transaction_intensity": actual_transaction_count / 7.0 if actual_units else 0.0,
                "promo_sales_day_count": promo_sales_day_count,
                "actual_refund_units": 0.0,
                "actual_refund_units_promo": 0.0,
                "actual_refund_sales_ex_gst_promo": 0.0,
                "actual_flagged_promo_units": actual_units,
                "inferred_supplier_number": supplier,
            }
        )
    return pd.DataFrame(rows)
