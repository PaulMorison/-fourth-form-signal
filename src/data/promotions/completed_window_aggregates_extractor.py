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


_QUERY_VERSION = "promotion_completed_window_aggregates_v1"
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
        pw.Calendar_Date,
        pw.Supplier_Number,
        pw.Promotional_Flag,
        pw.Promotional_Id,
        pw.Sold_Refund_Flag,
        pw.Quantity,
        pw.Sale_ExGST,
        pw.Sale_IncGST,
        TRY_CAST(pw.Store_Number AS bigint) AS store_number_key,
        TRY_CAST(pw.SKU_Number AS bigint) AS sku_number_key
    FROM {{PWLOGD_TABLE}} AS pw
    WHERE TRY_CAST(pw.Store_Number AS bigint) IS NOT NULL
      AND TRY_CAST(pw.SKU_Number AS bigint) IS NOT NULL
),
sales_line_items AS (
    SELECT
        CAST(pw.Calendar_Date AS date) AS calendar_date,
        pw.store_number_key AS store_number,
        pw.sku_number_key AS sku_number,
        TRY_CAST(pw.Supplier_Number AS bigint) AS supplier_number,
        CASE
            WHEN TRY_CAST(pw.Promotional_Flag AS int) = 1 THEN 1
            ELSE 0
        END AS promotional_flag,
        CAST(pw.Promotional_Id AS varchar(128)) AS promotional_id,
        CASE
            WHEN UPPER(COALESCE(CAST(pw.Sold_Refund_Flag AS varchar(32)), '')) IN ('R', 'REFUND')
                THEN -1.0 * ABS(COALESCE(TRY_CAST(pw.Quantity AS float), 0.0))
            WHEN COALESCE(TRY_CAST(pw.Quantity AS float), 0.0) < 0.0
                THEN COALESCE(TRY_CAST(pw.Quantity AS float), 0.0)
            ELSE ABS(COALESCE(TRY_CAST(pw.Quantity AS float), 0.0))
        END AS net_unit_quantity,
        CASE
            WHEN UPPER(COALESCE(CAST(pw.Sold_Refund_Flag AS varchar(32)), '')) IN ('R', 'REFUND')
                THEN ABS(COALESCE(TRY_CAST(pw.Quantity AS float), 0.0))
            WHEN COALESCE(TRY_CAST(pw.Quantity AS float), 0.0) < 0.0
                THEN ABS(COALESCE(TRY_CAST(pw.Quantity AS float), 0.0))
            ELSE 0.0
        END AS refund_unit_quantity,
        CASE
            WHEN UPPER(COALESCE(CAST(pw.Sold_Refund_Flag AS varchar(32)), '')) IN ('R', 'REFUND')
                THEN ABS(COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0))
            WHEN COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0) < 0.0
                THEN ABS(COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0))
            ELSE 0.0
        END AS refund_sale_ex_gst,
        CASE
            WHEN UPPER(COALESCE(CAST(pw.Sold_Refund_Flag AS varchar(32)), '')) IN ('R', 'REFUND')
                THEN -1.0 * ABS(COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0))
            WHEN COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0) < 0.0
                THEN COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0)
            ELSE ABS(COALESCE(TRY_CAST(pw.Sale_ExGST AS float), 0.0))
        END AS net_sale_ex_gst,
        CASE
            WHEN UPPER(COALESCE(CAST(pw.Sold_Refund_Flag AS varchar(32)), '')) IN ('R', 'REFUND')
                THEN -1.0 * ABS(COALESCE(TRY_CAST(pw.Sale_IncGST AS float), 0.0))
            WHEN COALESCE(TRY_CAST(pw.Sale_IncGST AS float), 0.0) < 0.0
                THEN COALESCE(TRY_CAST(pw.Sale_IncGST AS float), 0.0)
            ELSE ABS(COALESCE(TRY_CAST(pw.Sale_IncGST AS float), 0.0))
        END AS net_sale_inc_gst
    FROM pwlogd_typed AS pw
    INNER JOIN candidate_store_sku_windows AS candidate_scope
        ON pw.store_number_key = candidate_scope.store_number_key
       AND pw.sku_number_key = candidate_scope.sku_number_key
       AND CAST(pw.Calendar_Date AS date) BETWEEN candidate_scope.min_relevant_date AND candidate_scope.max_relevant_date
    WHERE CAST(pw.Calendar_Date AS date) <= CAST(:as_of_date AS date)
      AND CAST(pw.Calendar_Date AS date) >= CAST(:completed_sales_history_start_date AS date)
),
sales_daily AS (
    SELECT
        store_number,
        sku_number,
        calendar_date,
        MAX(supplier_number) AS inferred_supplier_number,
        SUM(net_unit_quantity) AS net_units,
        SUM(refund_unit_quantity) AS refund_units,
        SUM(refund_sale_ex_gst) AS refund_sales_ex_gst,
        SUM(net_sale_ex_gst) AS net_sales_ex_gst,
        SUM(net_sale_inc_gst) AS net_sales_inc_gst
    FROM sales_line_items
    GROUP BY
        store_number,
        sku_number,
        calendar_date
),
live_window AS (
    SELECT
        base.promotion_row_key,
        SUM(COALESCE(sd.net_units, 0.0)) AS actual_units_sold,
        SUM(COALESCE(sd.refund_units, 0.0)) AS actual_refund_units,
        SUM(COALESCE(sd.refund_sales_ex_gst, 0.0)) AS actual_refund_sales_ex_gst,
        SUM(COALESCE(sd.net_sales_ex_gst, 0.0)) AS actual_sales_ex_gst,
        SUM(COALESCE(sd.net_sales_inc_gst, 0.0)) AS actual_sales_inc_gst,
        COUNT(CASE WHEN COALESCE(sd.net_units, 0.0) > 0.0 THEN 1 END) AS promo_sales_day_count,
        AVG(sd.net_units) AS actual_avg_daily_units,
        STDEV(sd.net_units) AS actual_std_daily_units,
        MAX(sd.net_units) AS actual_peak_daily_units,
        MAX(sd.inferred_supplier_number) AS inferred_supplier_number
    FROM completed_base_scope AS base
    LEFT JOIN sales_daily AS sd
        ON sd.store_number = base.store_number_key
       AND sd.sku_number = base.sku_number_key
       AND sd.calendar_date BETWEEN base.promotion_start_date_date AND base.promotional_end_date_date
    GROUP BY base.promotion_row_key
),
pre_window AS (
    SELECT
        base.promotion_row_key,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN COALESCE(sd.net_units, 0.0)
                ELSE 0.0
            END
        ) AS pre_56d_units,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN COALESCE(sd.net_units, 0.0)
                ELSE 0.0
            END
        ) AS pre_28d_units,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:immediate_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN COALESCE(sd.net_units, 0.0)
                ELSE 0.0
            END
        ) AS pre_7d_units,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN COALESCE(sd.net_sales_ex_gst, 0.0)
                ELSE 0.0
            END
        ) AS pre_56d_sales_ex_gst,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN COALESCE(sd.net_sales_ex_gst, 0.0)
                ELSE 0.0
            END
        ) AS pre_28d_sales_ex_gst,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:immediate_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN COALESCE(sd.net_sales_ex_gst, 0.0)
                ELSE 0.0
            END
        ) AS pre_7d_sales_ex_gst,
        COUNT(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                 AND COALESCE(sd.net_units, 0.0) > 0.0
                THEN 1
            END
        ) AS pre_56d_days_with_sales,
        COUNT(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                 AND COALESCE(sd.net_units, 0.0) > 0.0
                THEN 1
            END
        ) AS pre_28d_days_with_sales,
        COUNT(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:immediate_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                 AND COALESCE(sd.net_units, 0.0) > 0.0
                THEN 1
            END
        ) AS pre_7d_days_with_sales,
        AVG(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_56d_avg_daily_units,
        AVG(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_28d_avg_daily_units,
        AVG(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:immediate_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_7d_avg_daily_units,
        AVG(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -21, base.promotion_start_date_date)
                 AND sd.calendar_date < DATEADD(day, -7, base.promotion_start_date_date)
                THEN sd.net_units
            END
        ) AS pre_prior_21d_avg_daily_units,
        STDEV(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_56d_std_daily_units,
        STDEV(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), base.promotion_start_date_date)
                 AND sd.calendar_date < base.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_28d_std_daily_units
    FROM completed_base_scope AS base
    LEFT JOIN sales_daily AS sd
        ON sd.store_number = base.store_number_key
       AND sd.sku_number = base.sku_number_key
       AND sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), base.promotion_start_date_date)
       AND sd.calendar_date < base.promotion_start_date_date
    GROUP BY base.promotion_row_key
),
post_window AS (
    SELECT
        base.promotion_row_key,
        SUM(COALESCE(sd.net_units, 0.0)) AS post_14d_units,
        SUM(COALESCE(sd.net_sales_ex_gst, 0.0)) AS post_14d_sales_ex_gst,
        AVG(sd.net_units) AS post_14d_avg_daily_units,
        COUNT(CASE WHEN COALESCE(sd.net_units, 0.0) > 0.0 THEN 1 END) AS post_14d_days_with_sales
    FROM completed_base_scope AS base
    LEFT JOIN sales_daily AS sd
        ON sd.store_number = base.store_number_key
       AND sd.sku_number = base.sku_number_key
       AND sd.calendar_date > base.promotional_end_date_date
       AND sd.calendar_date <= DATEADD(day, CAST(:post_promo_days AS int), base.promotional_end_date_date)
    GROUP BY base.promotion_row_key
)
SELECT
    base.promotion_row_key,
    COALESCE(lw.actual_units_sold, 0.0) AS actual_units_sold,
    COALESCE(lw.actual_refund_units, 0.0) AS actual_refund_units,
    COALESCE(lw.actual_refund_sales_ex_gst, 0.0) AS actual_refund_sales_ex_gst,
    COALESCE(lw.actual_sales_ex_gst, 0.0) AS actual_sales_ex_gst,
    COALESCE(lw.actual_sales_inc_gst, 0.0) AS actual_sales_inc_gst,
    COALESCE(lw.promo_sales_day_count, 0) AS promo_sales_day_count,
    COALESCE(lw.actual_avg_daily_units, 0.0) AS actual_avg_daily_units,
    COALESCE(lw.actual_std_daily_units, 0.0) AS actual_std_daily_units,
    COALESCE(lw.actual_peak_daily_units, 0.0) AS actual_peak_daily_units,
    COALESCE(lw.inferred_supplier_number, 0) AS inferred_supplier_number,
    COALESCE(pw.pre_56d_units, 0.0) AS pre_56d_units,
    COALESCE(pw.pre_28d_units, 0.0) AS pre_28d_units,
    COALESCE(pw.pre_7d_units, 0.0) AS pre_7d_units,
    COALESCE(pw.pre_56d_sales_ex_gst, 0.0) AS pre_56d_sales_ex_gst,
    COALESCE(pw.pre_28d_sales_ex_gst, 0.0) AS pre_28d_sales_ex_gst,
    COALESCE(pw.pre_7d_sales_ex_gst, 0.0) AS pre_7d_sales_ex_gst,
    COALESCE(pw.pre_56d_days_with_sales, 0) AS pre_56d_days_with_sales,
    COALESCE(pw.pre_28d_days_with_sales, 0) AS pre_28d_days_with_sales,
    COALESCE(pw.pre_7d_days_with_sales, 0) AS pre_7d_days_with_sales,
    COALESCE(pw.pre_56d_avg_daily_units, 0.0) AS pre_56d_avg_daily_units,
    COALESCE(pw.pre_28d_avg_daily_units, 0.0) AS pre_28d_avg_daily_units,
    COALESCE(pw.pre_7d_avg_daily_units, 0.0) AS pre_7d_avg_daily_units,
    COALESCE(pw.pre_prior_21d_avg_daily_units, 0.0) AS pre_prior_21d_avg_daily_units,
    COALESCE(pw.pre_56d_std_daily_units, 0.0) AS pre_56d_std_daily_units,
    COALESCE(pw.pre_28d_std_daily_units, 0.0) AS pre_28d_std_daily_units,
    COALESCE(pt.post_14d_units, 0.0) AS post_14d_units,
    COALESCE(pt.post_14d_sales_ex_gst, 0.0) AS post_14d_sales_ex_gst,
    COALESCE(pt.post_14d_avg_daily_units, 0.0) AS post_14d_avg_daily_units,
    COALESCE(pt.post_14d_days_with_sales, 0) AS post_14d_days_with_sales
FROM completed_base_scope AS base
LEFT JOIN live_window AS lw
    ON lw.promotion_row_key = base.promotion_row_key
LEFT JOIN pre_window AS pw
    ON pw.promotion_row_key = base.promotion_row_key
LEFT JOIN post_window AS pt
    ON pt.promotion_row_key = base.promotion_row_key;
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
class PromotionCompletedWindowAggregatesExtractor:
    executor: PromotionQueryExecutor

    def extract_stage(
        self,
        *,
        settings: PromotionPipelineSettings,
        run_id: str,
        base_frame: pd.DataFrame,
        phase_callback: Callable[[str], None] | None = None,
    ) -> PromotionCompletedStageArtifact:
        rendered_query = render_completed_window_aggregates_query(
            settings=settings,
            base_frame=base_frame,
        )
        return execute_completed_sql_stage(
            settings=settings,
            run_id=run_id,
            stage_name="completed_window_aggregates",
            executor=self.executor,
            rendered_query=rendered_query,
            candidate_promotion_row_count=int(len(base_frame.index)),
            phase_callback=phase_callback,
        )


def render_completed_window_aggregates_query(
    *,
    settings: PromotionPipelineSettings,
    base_frame: pd.DataFrame,
) -> PromotionCompletedRenderedStageQuery:
    scope_rows_json = _build_scope_rows_json(base_frame)
    sql = _SQL_TEMPLATE.replace(
        "{{PWLOGD_TABLE}}",
        _validate_identifier(settings.sql.pwlogd_table),
    )
    return PromotionCompletedRenderedStageQuery(
        sql=sql,
        parameters={
            "completed_base_scope_rows_json": scope_rows_json,
            "as_of_date": settings.as_of_date.isoformat(),
            "baseline_lookback_days": settings.windows.baseline_lookback_days,
            "short_baseline_days": settings.windows.short_baseline_days,
            "immediate_baseline_days": settings.windows.immediate_baseline_days,
            "post_promo_days": settings.windows.post_promo_days,
            "completed_sales_history_start_date": (
                settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
            ),
            "query_version": _QUERY_VERSION,
        },
        query_version=_QUERY_VERSION,
        stage_name="completed_window_aggregates",
        diagnostic_filter_summary={
            "staged_extraction_enabled": True,
            "completed_extraction_stage_mode": "completed_staged_enrichment_v1",
            "extraction_stage": "completed_window_aggregates",
            "scope_row_count": int(len(base_frame.index)),
        },
        estimated_window_summary={
            "selection_mode": "completed",
            "scope_row_count": int(len(base_frame.index)),
            "baseline_lookback_days": settings.windows.baseline_lookback_days,
            "short_baseline_days": settings.windows.short_baseline_days,
            "immediate_baseline_days": settings.windows.immediate_baseline_days,
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
            "Completed window aggregates require landed base scope columns: "
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