from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable

import pandas as pd

from data.promotions.completed_stage_executor import (
    PromotionCompletedRenderedStageQuery,
    PromotionCompletedStageArtifact,
    execute_completed_sql_stage,
)
from data.promotions.mssql_query_executor import PromotionQueryExecutor
from runtime.promotions.config import PromotionPipelineSettings


_QUERY_VERSION = "promotion_completed_transaction_aggregates_v2"
_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}$"
)
_SQL_TEMPLATE = """WITH completed_base_scope_raw AS (
    SELECT
        js.promotion_row_key,
        js.store_number_key_raw,
        js.sku_number_key_raw,
        js.promotion_start_date_date,
        js.promotional_end_date_date,
        js.promotional_sku_id_key
    FROM OPENJSON(CAST(:completed_base_scope_rows_json AS nvarchar(max))) WITH (
        promotion_row_key nvarchar(255) '$.promotion_row_key',
        store_number_key_raw nvarchar(128) '$.store_number_key',
        sku_number_key_raw nvarchar(128) '$.sku_number_key',
        promotion_start_date_date date '$.promotion_start_date_date',
        promotional_end_date_date date '$.promotional_end_date_date',
        promotional_sku_id_key nvarchar(128) '$.promotional_sku_id_key'
    ) AS js
),
completed_base_scope AS (
    SELECT
        scope_raw.promotion_row_key,
        TRY_CAST(scope_raw.store_number_key_raw AS bigint) AS store_number_key,
        TRY_CAST(scope_raw.sku_number_key_raw AS bigint) AS sku_number_key,
        scope_raw.promotion_start_date_date,
        scope_raw.promotional_end_date_date,
        scope_raw.promotional_sku_id_key
    FROM completed_base_scope_raw AS scope_raw
    WHERE TRY_CAST(scope_raw.store_number_key_raw AS bigint) IS NOT NULL
      AND TRY_CAST(scope_raw.sku_number_key_raw AS bigint) IS NOT NULL
),
candidate_promotion_windows AS (
    SELECT
        store_number_key,
        sku_number_key,
        DATEADD(
            day,
            -1 * CAST(:baseline_lookback_days AS int),
            promotion_start_date_date
        ) AS min_relevant_date,
        CASE
            WHEN promotional_end_date_date < CAST(:as_of_date AS date)
                THEN DATEADD(
                    day,
                    CAST(:post_promo_days AS int),
                    promotional_end_date_date
                )
            ELSE CAST(:as_of_date AS date)
        END AS max_relevant_date
    FROM completed_base_scope
    WHERE store_number_key IS NOT NULL
      AND sku_number_key IS NOT NULL
),
candidate_ranked_windows AS (
    SELECT
        store_number_key,
        sku_number_key,
        min_relevant_date,
        max_relevant_date,
        MAX(max_relevant_date) OVER (
            PARTITION BY store_number_key, sku_number_key
            ORDER BY min_relevant_date, max_relevant_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS prior_max_relevant_date
    FROM candidate_promotion_windows
),
candidate_window_groups AS (
    SELECT
        store_number_key,
        sku_number_key,
        min_relevant_date,
        max_relevant_date,
        SUM(
            CASE
                WHEN prior_max_relevant_date IS NULL
                    OR min_relevant_date > DATEADD(day, 1, prior_max_relevant_date)
                    THEN 1
                ELSE 0
            END
        ) OVER (
            PARTITION BY store_number_key, sku_number_key
            ORDER BY min_relevant_date, max_relevant_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS window_group
    FROM candidate_ranked_windows
),
candidate_store_sku_windows AS (
    SELECT
        store_number_key,
        sku_number_key,
        MIN(min_relevant_date) AS min_relevant_date,
        MAX(max_relevant_date) AS max_relevant_date
    FROM candidate_window_groups
    GROUP BY
        store_number_key,
        sku_number_key,
        window_group
),
pwlogd_typed AS (
    SELECT
        CAST(pw.Calendar_Date AS date) AS calendar_date,
        TRY_CAST(pw.Store_Number AS bigint) AS store_number_key,
        TRY_CAST(pw.SKU_Number AS bigint) AS sku_number_key,
        TRY_CAST(pw.Supplier_Number AS bigint) AS supplier_number,
        CAST(pw.Promotional_Id AS varchar(128)) AS promotional_id,
        CAST(pw.Operator_Number AS varchar(32)) AS operator_number,
        CAST(pw.Register_Number AS varchar(32)) AS register_number,
        CAST(pw.Transaction_Number AS varchar(32)) AS transaction_number,
        CAST(pw.Store_Number AS varchar(32)) AS store_number_str,
        CONCAT(
            COALESCE(CAST(pw.Store_Number AS varchar(32)), ''),
            '|',
            COALESCE(CONVERT(varchar(10), CAST(pw.Calendar_Date AS date), 23), ''),
            '|',
            COALESCE(CAST(pw.Operator_Number AS varchar(32)), ''),
            '|',
            COALESCE(CAST(pw.Register_Number AS varchar(32)), ''),
            '|',
            COALESCE(CAST(pw.Transaction_Number AS varchar(32)), '')
        ) AS transaction_key,
        CASE
            WHEN TRY_CAST(pw.Promotional_Flag AS int) = 1 THEN 1
            ELSE 0
        END AS promotional_flag,
        UPPER(COALESCE(CAST(pw.Sold_Refund_Flag AS varchar(32)), '')) AS sold_refund_flag,
        COALESCE(TRY_CAST(pw.Quantity AS float), 0.0) AS raw_quantity,
        COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0) AS raw_sale_ex_gst,
        CASE
            WHEN UPPER(COALESCE(CAST(pw.Sold_Refund_Flag AS varchar(32)), '')) IN ('R', 'REFUND')
                THEN -1.0 * ABS(COALESCE(TRY_CAST(pw.Quantity AS float), 0.0))
            WHEN COALESCE(TRY_CAST(pw.Quantity AS float), 0.0) < 0.0
                THEN COALESCE(TRY_CAST(pw.Quantity AS float), 0.0)
            ELSE ABS(COALESCE(TRY_CAST(pw.Quantity AS float), 0.0))
        END AS net_unit_quantity,
        CASE
            WHEN UPPER(COALESCE(CAST(pw.Sold_Refund_Flag AS varchar(32)), '')) IN ('R', 'REFUND')
                THEN -1.0 * ABS(COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0))
            WHEN COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0) < 0.0
                THEN COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0)
            ELSE ABS(COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0))
        END AS net_sale_ex_gst
    FROM {{PWLOGD_TABLE}} AS pw
    WHERE TRY_CAST(pw.Store_Number AS bigint) IS NOT NULL
      AND TRY_CAST(pw.SKU_Number AS bigint) IS NOT NULL
),
candidate_sku_line_items AS (
    SELECT
        pw.calendar_date,
        pw.store_number_key AS store_number,
        pw.sku_number_key AS sku_number,
        pw.promotional_id,
        pw.promotional_flag,
        pw.transaction_key,
        pw.net_unit_quantity
    FROM pwlogd_typed AS pw
    INNER JOIN candidate_store_sku_windows AS candidate_scope
        ON pw.store_number_key = candidate_scope.store_number_key
       AND pw.sku_number_key = candidate_scope.sku_number_key
       AND pw.calendar_date BETWEEN candidate_scope.min_relevant_date AND candidate_scope.max_relevant_date
    WHERE pw.calendar_date <= CAST(:as_of_date AS date)
      AND pw.calendar_date >= CAST(:completed_sales_history_start_date AS date)
),
candidate_transactions AS (
    SELECT
        base.promotion_row_key,
        base.store_number_key AS store_number,
        base.sku_number_key AS candidate_sku_number,
        base.promotional_sku_id_key,
        line_item.calendar_date,
        line_item.transaction_key,
        MAX(line_item.promotional_flag) AS promotional_flag,
        MAX(line_item.promotional_id) AS promotional_id,
        SUM(line_item.net_unit_quantity) AS candidate_sku_units
    FROM completed_base_scope AS base
    INNER JOIN candidate_sku_line_items AS line_item
        ON line_item.store_number = base.store_number_key
       AND line_item.sku_number = base.sku_number_key
       AND line_item.calendar_date BETWEEN base.promotion_start_date_date AND base.promotional_end_date_date
    GROUP BY
        base.promotion_row_key,
        base.store_number_key,
        base.sku_number_key,
        base.promotional_sku_id_key,
        line_item.calendar_date,
        line_item.transaction_key
),
transaction_outcomes AS (
    SELECT
        promotion_row_key,
        COUNT(CASE WHEN COALESCE(candidate_sku_units, 0.0) <> 0.0 THEN 1 END) AS realised_transaction_count,
        COUNT(
            CASE
                WHEN COALESCE(candidate_sku_units, 0.0) <> 0.0
                    AND (
                        promotional_flag = 1
                        OR promotional_id = promotional_sku_id_key
                    )
                THEN 1
            END
        ) AS realised_promo_transaction_count,
        SUM(
            CASE
                WHEN promotional_flag = 1 OR promotional_id = promotional_sku_id_key
                    THEN COALESCE(candidate_sku_units, 0.0)
                ELSE 0.0
            END
        ) AS actual_flagged_promo_units
    FROM candidate_transactions
    GROUP BY promotion_row_key
),
candidate_positive_transactions AS (
    SELECT
        promotion_row_key,
        store_number,
        candidate_sku_number,
        calendar_date,
        transaction_key,
        candidate_sku_units
    FROM candidate_transactions
    WHERE COALESCE(candidate_sku_units, 0.0) > 0.0
),
basket_line_items AS (
    SELECT
        candidate_tx.promotion_row_key,
        candidate_tx.candidate_sku_number,
        candidate_tx.calendar_date,
        candidate_tx.transaction_key,
        candidate_tx.candidate_sku_units,
        pw.sku_number_key AS line_sku_number,
        pw.supplier_number AS line_supplier_number,
        pw.net_unit_quantity,
        pw.net_sale_ex_gst
    FROM candidate_positive_transactions AS candidate_tx
    INNER JOIN pwlogd_typed AS pw
        ON pw.store_number_key = candidate_tx.store_number
       AND pw.calendar_date = candidate_tx.calendar_date
       AND pw.transaction_key = candidate_tx.transaction_key
),
basket_transaction_sku_lines AS (
    SELECT
        promotion_row_key,
        candidate_sku_number,
        calendar_date,
        transaction_key,
        line_sku_number,
        MAX(line_supplier_number) AS line_supplier_number,
        SUM(net_unit_quantity) AS sku_net_units,
        SUM(net_sale_ex_gst) AS sku_net_sales_ex_gst,
        MAX(candidate_sku_units) AS candidate_sku_units
    FROM basket_line_items
    GROUP BY
        promotion_row_key,
        candidate_sku_number,
        calendar_date,
        transaction_key,
        line_sku_number
),
basket_transactions AS (
    SELECT
        promotion_row_key,
        candidate_sku_number,
        calendar_date,
        transaction_key,
        MAX(candidate_sku_units) AS candidate_sku_units,
        COUNT(CASE WHEN COALESCE(sku_net_units, 0.0) > 0.0 THEN 1 END) AS basket_item_count,
        SUM(CASE WHEN COALESCE(sku_net_units, 0.0) > 0.0 THEN COALESCE(sku_net_sales_ex_gst, 0.0) ELSE 0.0 END) AS basket_sales_ex_gst,
        MAX(
            CASE
                WHEN DATEDIFF(day, '19000101', calendar_date) % 7 IN (5, 6) THEN 1
                ELSE 0
            END
        ) AS weekend_flag,
        MAX(
            CASE
                WHEN DAY(calendar_date) >= 25 OR DAY(calendar_date) <= 3 THEN 1
                ELSE 0
            END
        ) AS pay_cycle_flag
    FROM basket_transaction_sku_lines
    GROUP BY
        promotion_row_key,
        candidate_sku_number,
        calendar_date,
        transaction_key
),
basket_transaction_stats AS (
    SELECT
        promotion_row_key,
        candidate_sku_number,
        calendar_date,
        transaction_key,
        candidate_sku_units,
        basket_item_count,
        basket_sales_ex_gst,
        weekend_flag,
        pay_cycle_flag,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(basket_item_count AS float)) OVER (PARTITION BY promotion_row_key) AS basket_item_count_median,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY basket_sales_ex_gst) OVER (PARTITION BY promotion_row_key) AS basket_sales_ex_gst_median
    FROM basket_transactions
),
basket_transaction_summary AS (
    SELECT
        promotion_row_key,
        SUM(CASE WHEN basket_item_count = 1 THEN 1 ELSE 0 END) AS realised_sku_solo_transaction_count,
        SUM(CASE WHEN basket_item_count > 1 THEN 1 ELSE 0 END) AS realised_sku_multi_item_transaction_count,
        SUM(CAST(basket_item_count AS float)) AS realised_basket_item_count_sum_when_sku_present,
        MAX(basket_item_count_median) AS realised_basket_item_count_median_when_sku_present,
        SUM(COALESCE(basket_sales_ex_gst, 0.0)) AS realised_basket_sales_ex_gst_sum_when_sku_present,
        MAX(basket_sales_ex_gst_median) AS realised_basket_sales_ex_gst_median_when_sku_present,
        SUM(CASE WHEN basket_item_count > 1 THEN COALESCE(candidate_sku_units, 0.0) ELSE 0.0 END) AS realised_units_in_multi_item_baskets,
        SUM(CASE WHEN basket_item_count > 1 AND COALESCE(candidate_sku_units, 0.0) > 1.0 THEN 1 ELSE 0 END) AS realised_multi_item_multi_unit_transaction_count,
        SUM(CASE WHEN weekend_flag = 1 THEN 1 ELSE 0 END) AS realised_weekend_transaction_count_with_sku,
        SUM(CASE WHEN pay_cycle_flag = 1 THEN 1 ELSE 0 END) AS realised_pay_cycle_transaction_count_with_sku,
        COUNT(*) AS realised_positive_transaction_count_with_sku
    FROM basket_transaction_stats
    GROUP BY promotion_row_key
),
companion_presence AS (
    SELECT DISTINCT
        promotion_row_key,
        transaction_key,
        line_sku_number AS companion_sku_number
    FROM basket_transaction_sku_lines
    WHERE COALESCE(sku_net_units, 0.0) > 0.0
      AND line_sku_number <> candidate_sku_number
),
companion_counts AS (
    SELECT
        promotion_row_key,
        companion_sku_number,
        COUNT(*) AS companion_transaction_count
    FROM companion_presence
    GROUP BY promotion_row_key, companion_sku_number
),
companion_ranked AS (
    SELECT
        promotion_row_key,
        companion_sku_number,
        companion_transaction_count,
        ROW_NUMBER() OVER (
            PARTITION BY promotion_row_key
            ORDER BY companion_transaction_count DESC, companion_sku_number
        ) AS companion_rank
    FROM companion_counts
),
companion_summary AS (
    SELECT
        ranked.promotion_row_key,
        MAX(CASE WHEN ranked.companion_rank = 1 THEN ranked.companion_transaction_count END) AS top_companion_sku_1_transaction_count,
        MAX(CASE WHEN ranked.companion_rank = 2 THEN ranked.companion_transaction_count END) AS top_companion_sku_2_transaction_count,
        SUM(CAST(ranked.companion_transaction_count AS float) * CAST(ranked.companion_transaction_count AS float)) AS companion_concentration_numerator
    FROM companion_ranked AS ranked
    GROUP BY ranked.promotion_row_key
)
SELECT
    base.promotion_row_key,
    COALESCE(tx.realised_transaction_count, 0.0) AS realised_transaction_count,
    COALESCE(tx.realised_promo_transaction_count, 0.0) AS realised_promo_transaction_count,
    COALESCE(tx.actual_flagged_promo_units, 0.0) AS actual_flagged_promo_units,
    COALESCE(basket.realised_sku_solo_transaction_count, 0.0) AS realised_sku_solo_transaction_count,
    COALESCE(basket.realised_sku_multi_item_transaction_count, 0.0) AS realised_sku_multi_item_transaction_count,
    COALESCE(basket.realised_basket_item_count_sum_when_sku_present, 0.0) AS realised_basket_item_count_sum_when_sku_present,
    COALESCE(basket.realised_basket_item_count_median_when_sku_present, 0.0) AS realised_basket_item_count_median_when_sku_present,
    COALESCE(basket.realised_basket_sales_ex_gst_sum_when_sku_present, 0.0) AS realised_basket_sales_ex_gst_sum_when_sku_present,
    COALESCE(basket.realised_basket_sales_ex_gst_median_when_sku_present, 0.0) AS realised_basket_sales_ex_gst_median_when_sku_present,
    COALESCE(basket.realised_units_in_multi_item_baskets, 0.0) AS realised_units_in_multi_item_baskets,
    COALESCE(basket.realised_multi_item_multi_unit_transaction_count, 0.0) AS realised_multi_item_multi_unit_transaction_count,
    COALESCE(basket.realised_weekend_transaction_count_with_sku, 0.0) AS realised_weekend_transaction_count_with_sku,
    COALESCE(basket.realised_pay_cycle_transaction_count_with_sku, 0.0) AS realised_pay_cycle_transaction_count_with_sku,
    COALESCE(
        CAST(companion.top_companion_sku_1_transaction_count AS float)
        / NULLIF(CAST(basket.realised_positive_transaction_count_with_sku AS float), 0.0),
        0.0
    ) AS realised_top_companion_sku_1_share,
    COALESCE(
        CAST(companion.top_companion_sku_2_transaction_count AS float)
        / NULLIF(CAST(basket.realised_positive_transaction_count_with_sku AS float), 0.0),
        0.0
    ) AS realised_top_companion_sku_2_share,
    COALESCE(
        companion.companion_concentration_numerator
        / NULLIF(
            CAST(basket.realised_positive_transaction_count_with_sku AS float)
            * CAST(basket.realised_positive_transaction_count_with_sku AS float),
            0.0
        ),
        0.0
    ) AS realised_companion_concentration_index
FROM completed_base_scope AS base
LEFT JOIN transaction_outcomes AS tx
    ON tx.promotion_row_key = base.promotion_row_key
LEFT JOIN basket_transaction_summary AS basket
    ON basket.promotion_row_key = base.promotion_row_key
LEFT JOIN companion_summary AS companion
    ON companion.promotion_row_key = base.promotion_row_key;
"""

_SCOPE_COLUMNS = (
    "promotion_row_key",
    "store_number_key",
    "sku_number_key",
    "promotion_start_date_date",
    "promotional_end_date_date",
    "promotional_sku_id_key",
)


@dataclass(frozen=True)
class PromotionCompletedTransactionAggregatesExtractor:
    executor: PromotionQueryExecutor

    def extract_stage(
        self,
        *,
        settings: PromotionPipelineSettings,
        run_id: str,
        base_frame: pd.DataFrame,
        phase_callback: Callable[[str], None] | None = None,
    ) -> PromotionCompletedStageArtifact:
        rendered_query = render_completed_transaction_aggregates_query(
            settings=settings,
            base_frame=base_frame,
        )
        return execute_completed_sql_stage(
            settings=settings,
            run_id=run_id,
            stage_name="completed_transaction_aggregates",
            executor=self.executor,
            rendered_query=rendered_query,
            candidate_promotion_row_count=int(len(base_frame.index)),
            phase_callback=phase_callback,
        )


def render_completed_transaction_aggregates_query(
    *,
    settings: PromotionPipelineSettings,
    base_frame: pd.DataFrame,
) -> PromotionCompletedRenderedStageQuery:
    return PromotionCompletedRenderedStageQuery(
        sql=_SQL_TEMPLATE.replace(
            "{{PWLOGD_TABLE}}",
            _validate_identifier(settings.sql.pwlogd_table),
        ),
        parameters={
            "completed_base_scope_rows_json": _build_scope_rows_json(base_frame),
            "as_of_date": settings.as_of_date.isoformat(),
            "baseline_lookback_days": settings.windows.baseline_lookback_days,
            "post_promo_days": settings.windows.post_promo_days,
            "completed_sales_history_start_date": (
                settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
            ),
            "query_version": _QUERY_VERSION,
        },
        query_version=_QUERY_VERSION,
        stage_name="completed_transaction_aggregates",
        diagnostic_filter_summary={
            "staged_extraction_enabled": True,
            "completed_extraction_stage_mode": "completed_staged_enrichment_v1",
            "extraction_stage": "completed_transaction_aggregates",
            "scope_row_count": int(len(base_frame.index)),
        },
        estimated_window_summary={
            "selection_mode": "completed",
            "scope_row_count": int(len(base_frame.index)),
            "baseline_lookback_days": settings.windows.baseline_lookback_days,
            "post_promo_days": settings.windows.post_promo_days,
            "completed_sales_history_start_date": (
                settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
            ),
            "as_of_date": settings.as_of_date.isoformat(),
            "query_version": _QUERY_VERSION,
        },
    )


def _build_scope_rows_json(base_frame: pd.DataFrame) -> str:
    missing_columns = [column_name for column_name in _SCOPE_COLUMNS if column_name not in base_frame.columns]
    if missing_columns:
        raise ValueError(
            "Completed transaction aggregates require landed base scope columns: "
            f"{', '.join(missing_columns)}."
        )
    rows: list[dict[str, object | None]] = []
    for record in base_frame.loc[:, list(_SCOPE_COLUMNS)].to_dict(orient="records"):
        rows.append({key: _to_json_scalar(value) for key, value in record.items()})
    return json.dumps(rows, separators=(",", ":"), sort_keys=True)


def _to_json_scalar(value: object) -> object | None:
    if pd.isna(value):
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _validate_identifier(identifier: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(
            f"Unsafe SQL identifier '{identifier}'. Use schema-qualified table names only."
        )
    return identifier