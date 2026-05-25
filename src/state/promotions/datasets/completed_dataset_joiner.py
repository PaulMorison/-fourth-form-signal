from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd


_DATE_COLUMNS = (
    "promotion_start_date",
    "promotional_end_date",
    "promotion_start_date_date",
    "promotional_end_date_date",
    "ingested_at",
    "extracted_at_utc",
    "extraction_as_of_date",
)
_WINDOW_COLUMNS = (
    "actual_units_sold",
    "actual_refund_units",
    "actual_refund_sales_ex_gst",
    "actual_sales_ex_gst",
    "actual_sales_inc_gst",
    "promo_sales_day_count",
    "actual_avg_daily_units",
    "actual_std_daily_units",
    "actual_peak_daily_units",
    "inferred_supplier_number",
    "pre_56d_units",
    "pre_28d_units",
    "pre_7d_units",
    "pre_56d_sales_ex_gst",
    "pre_28d_sales_ex_gst",
    "pre_7d_sales_ex_gst",
    "pre_56d_days_with_sales",
    "pre_28d_days_with_sales",
    "pre_7d_days_with_sales",
    "pre_56d_avg_daily_units",
    "pre_28d_avg_daily_units",
    "pre_7d_avg_daily_units",
    "pre_prior_21d_avg_daily_units",
    "pre_56d_std_daily_units",
    "pre_28d_std_daily_units",
    "post_14d_units",
    "post_14d_sales_ex_gst",
    "post_14d_avg_daily_units",
    "post_14d_days_with_sales",
)
_TRANSACTION_COLUMNS = (
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
)
_DERIVED_COLUMNS = (
    "actual_units_sold_promo",
    "actual_sales_ex_gst_promo",
    "actual_sales_inc_gst_promo",
    "actual_transaction_count_promo",
    "actual_days_with_sales_promo",
    "actual_avg_units_per_selling_day_promo",
    "actual_avg_sales_per_selling_day_promo",
    "actual_units_pre_56d",
    "actual_units_pre_28d",
    "actual_units_pre_7d",
    "actual_sales_ex_gst_pre_56d",
    "actual_sales_ex_gst_pre_28d",
    "actual_sales_ex_gst_pre_7d",
    "pre_56d_avg_sales_ex_gst_per_selling_day",
    "pre_28d_avg_sales_ex_gst_per_selling_day",
    "pre_7d_avg_sales_ex_gst_per_selling_day",
    "actual_units_post_14d",
    "actual_sales_ex_gst_post_14d",
    "post_14d_avg_sales_ex_gst_per_selling_day",
    "actual_avg_sales_ex_gst_per_selling_day",
    "actual_avg_sales_inc_gst_per_selling_day",
    "actual_units_per_transaction",
    "actual_sales_ex_gst_per_transaction",
    "actual_refund_units_promo",
    "actual_refund_sales_ex_gst_promo",
    "actual_transaction_intensity",
    "actual_promo_transaction_intensity",
)


@dataclass(frozen=True)
class PromotionCompletedDatasetJoiner:
    def join(
        self,
        *,
        run_id: str,
        as_of_date: str,
        query_version: str,
        advice_source_table_name: str,
        realised_sales_source_table_name: str,
        base_frame: pd.DataFrame,
        window_aggregate_frame: pd.DataFrame,
        transaction_aggregate_frame: pd.DataFrame,
        extracted_at_utc: str | None = None,
    ) -> pd.DataFrame:
        if "promotion_row_key" not in base_frame.columns:
            raise ValueError("Completed base frame must include promotion_row_key before assembly.")
        merged = base_frame.copy()
        merged = merged.merge(
            window_aggregate_frame,
            on="promotion_row_key",
            how="left",
            validate="one_to_one",
        )
        merged = merged.merge(
            transaction_aggregate_frame,
            on="promotion_row_key",
            how="left",
            validate="one_to_one",
        )
        for column_name in (*_WINDOW_COLUMNS, *_TRANSACTION_COLUMNS):
            if column_name not in merged.columns:
                merged[column_name] = 0.0
            merged[column_name] = pd.to_numeric(merged[column_name], errors="coerce").fillna(0.0)

        resolved_extracted_at_utc = extracted_at_utc or datetime.now(tz=UTC).isoformat()
        merged["extraction_as_of_date"] = as_of_date
        merged["extraction_selection_mode"] = "completed"
        merged["extraction_query_version"] = query_version
        merged["extracted_at_utc"] = resolved_extracted_at_utc

        merged["actual_units_sold_promo"] = merged["actual_units_sold"]
        merged["actual_sales_ex_gst_promo"] = merged["actual_sales_ex_gst"]
        merged["actual_sales_inc_gst_promo"] = merged["actual_sales_inc_gst"]
        merged["actual_transaction_count_promo"] = merged["realised_transaction_count"]
        merged["actual_days_with_sales_promo"] = merged["promo_sales_day_count"]
        merged["actual_avg_units_per_selling_day_promo"] = _safe_divide(
            merged["actual_units_sold"],
            merged["promo_sales_day_count"],
        )
        merged["actual_avg_sales_per_selling_day_promo"] = _safe_divide(
            merged["actual_sales_ex_gst"],
            merged["promo_sales_day_count"],
        )
        merged["actual_units_pre_56d"] = merged["pre_56d_units"]
        merged["actual_units_pre_28d"] = merged["pre_28d_units"]
        merged["actual_units_pre_7d"] = merged["pre_7d_units"]
        merged["actual_sales_ex_gst_pre_56d"] = merged["pre_56d_sales_ex_gst"]
        merged["actual_sales_ex_gst_pre_28d"] = merged["pre_28d_sales_ex_gst"]
        merged["actual_sales_ex_gst_pre_7d"] = merged["pre_7d_sales_ex_gst"]
        merged["pre_56d_avg_sales_ex_gst_per_selling_day"] = _safe_divide(
            merged["pre_56d_sales_ex_gst"],
            merged["pre_56d_days_with_sales"],
        )
        merged["pre_28d_avg_sales_ex_gst_per_selling_day"] = _safe_divide(
            merged["pre_28d_sales_ex_gst"],
            merged["pre_28d_days_with_sales"],
        )
        merged["pre_7d_avg_sales_ex_gst_per_selling_day"] = _safe_divide(
            merged["pre_7d_sales_ex_gst"],
            merged["pre_7d_days_with_sales"],
        )
        merged["actual_units_post_14d"] = merged["post_14d_units"]
        merged["actual_sales_ex_gst_post_14d"] = merged["post_14d_sales_ex_gst"]
        merged["post_14d_avg_sales_ex_gst_per_selling_day"] = _safe_divide(
            merged["post_14d_sales_ex_gst"],
            merged["post_14d_days_with_sales"],
        )
        merged["actual_avg_sales_ex_gst_per_selling_day"] = _safe_divide(
            merged["actual_sales_ex_gst"],
            merged["promo_sales_day_count"],
        )
        merged["actual_avg_sales_inc_gst_per_selling_day"] = _safe_divide(
            merged["actual_sales_inc_gst"],
            merged["promo_sales_day_count"],
        )
        merged["actual_units_per_transaction"] = _safe_divide(
            merged["actual_units_sold"],
            merged["realised_transaction_count"],
        )
        merged["actual_sales_ex_gst_per_transaction"] = _safe_divide(
            merged["actual_sales_ex_gst"],
            merged["realised_transaction_count"],
        )
        merged["actual_refund_units_promo"] = merged["actual_refund_units"]
        merged["actual_refund_sales_ex_gst_promo"] = merged["actual_refund_sales_ex_gst"]
        merged["actual_transaction_intensity"] = _safe_divide(
            merged["realised_transaction_count"],
            merged["live_promo_window_days"],
        )
        merged["actual_promo_transaction_intensity"] = _safe_divide(
            merged["realised_promo_transaction_count"],
            merged["live_promo_window_days"],
        )
        merged["advice_source_table_name"] = advice_source_table_name
        merged["realised_sales_source_table_name"] = realised_sales_source_table_name

        for column_name in _DATE_COLUMNS:
            if column_name in merged.columns:
                merged[column_name] = pd.to_datetime(
                    merged[column_name],
                    utc=False,
                    errors="coerce",
                )
        merged["extraction_run_id"] = run_id
        merged["extraction_materialized_at_utc"] = resolved_extracted_at_utc
        merged["extraction_materialized_as_of_date"] = as_of_date

        ordered_columns = _ordered_columns(base_frame.columns, merged.columns)
        return merged.reindex(columns=ordered_columns)


def _safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    resolved_denominator = pd.to_numeric(denominator, errors="coerce").replace(0, pd.NA)
    resolved_numerator = pd.to_numeric(numerator, errors="coerce")
    return resolved_numerator.divide(resolved_denominator).fillna(0.0)


def _ordered_columns(
    base_columns: pd.Index,
    all_columns: pd.Index,
) -> list[str]:
    preferred_columns = [
        *[str(column_name) for column_name in base_columns],
        "extraction_as_of_date",
        "extraction_selection_mode",
        "extraction_query_version",
        "extracted_at_utc",
        *_WINDOW_COLUMNS,
        *_TRANSACTION_COLUMNS,
        *_DERIVED_COLUMNS,
        "advice_source_table_name",
        "realised_sales_source_table_name",
        "extraction_run_id",
        "extraction_materialized_at_utc",
        "extraction_materialized_as_of_date",
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for column_name in preferred_columns:
        if column_name in all_columns and column_name not in seen:
            ordered.append(column_name)
            seen.add(column_name)
    for column_name in all_columns:
        normalized = str(column_name)
        if normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    return ordered