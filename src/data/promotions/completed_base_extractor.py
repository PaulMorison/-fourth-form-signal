from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import re

from data.promotions.completed_stage_executor import (
    PromotionCompletedRenderedStageQuery,
    PromotionCompletedStageArtifact,
    execute_completed_sql_stage,
)
from data.promotions.mssql_query_executor import PromotionQueryExecutor
from data.promotions.sql import PromotionBaseQueryOptions
from runtime.promotions.config import PromotionPartitionStrategy, PromotionPipelineSettings


_QUERY_VERSION = "promotion_completed_base_v1"
_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}$"
)
_COMPLETED_SELECTION_FILTER = (
    "CAST(ar.promotional_end_date AS date) "
    "< DATEADD(day, -1 * CAST(:completed_promotion_buffer_days AS int), CAST(:as_of_date AS date))"
)
_SQL_TEMPLATE = """WITH advice_ranked_source AS (
    SELECT
        ar.*, 
        ROW_NUMBER() OVER (
            ORDER BY {{ADVICE_RANK_ORDER_BY_CLAUSE}}
        ) AS advice_batch_row_number
    FROM {{PROMOTION_ADVICE_TABLE}} AS ar
    WHERE {{ADVICE_FILTER_CLAUSE}}{{ADVICE_DIAGNOSTIC_FILTER_CLAUSE}}{{ADVICE_PARTITION_FILTER_CLAUSE}}
),
advice_source AS (
    SELECT
        {{ADVICE_LIMIT_CLAUSE}}ar.*,
        CAST(ar.promotion_start_date AS date) AS promotion_start_date_date,
        CAST(ar.promotional_end_date AS date) AS promotional_end_date_date,
        TRY_CAST(ar.store_number AS bigint) AS store_number_key,
        TRY_CAST(ar.sku_number AS bigint) AS sku_number_key,
        CAST(ar.promotional_sku_id AS varchar(128)) AS promotional_sku_id_key,
        CONCAT(
            COALESCE(CAST(ar.store_number AS varchar(64)), ''),
            '|',
            COALESCE(CAST(ar.sku_number AS varchar(64)), ''),
            '|',
            COALESCE(CONVERT(varchar(10), CAST(ar.promotion_start_date AS date), 23), ''),
            '|',
            COALESCE(CONVERT(varchar(10), CAST(ar.promotional_end_date AS date), 23), ''),
            '|',
            COALESCE(CAST(ar.promotional_sku_id AS varchar(128)), ''),
            '|',
            COALESCE(CAST(ar.promotion_name AS varchar(255)), '')
        ) AS promotion_row_key,
        DATEDIFF(day, CAST(ar.promotion_start_date AS date), CAST(ar.promotional_end_date AS date)) + 1 AS live_promo_window_days
    FROM advice_ranked_source AS ar
    WHERE 1 = 1{{ADVICE_BATCH_FILTER_CLAUSE}}
    {{ADVICE_ORDER_BY_CLAUSE}}
)
SELECT *
FROM advice_source;
"""


@dataclass(frozen=True)
class PromotionCompletedBaseExtractor:
    executor: PromotionQueryExecutor

    def extract_stage(
        self,
        *,
        settings: PromotionPipelineSettings,
        run_id: str,
        query_options: PromotionBaseQueryOptions,
        phase_callback: Callable[[str], None] | None = None,
        candidate_promotion_row_count: int | None = None,
    ) -> PromotionCompletedStageArtifact:
        rendered_query = render_completed_base_stage_query(
            settings=settings,
            query_options=query_options,
        )
        return execute_completed_sql_stage(
            settings=settings,
            run_id=run_id,
            stage_name="completed_base",
            executor=self.executor,
            rendered_query=rendered_query,
            candidate_promotion_row_count=candidate_promotion_row_count,
            phase_callback=phase_callback,
        )


def render_completed_base_stage_query(
    *,
    settings: PromotionPipelineSettings,
    query_options: PromotionBaseQueryOptions | None = None,
) -> PromotionCompletedRenderedStageQuery:
    resolved_query_options = query_options or PromotionBaseQueryOptions()
    _validate_query_options(resolved_query_options)
    diagnostic_filter_clause, diagnostic_parameters = _build_diagnostic_filter_clause(
        resolved_query_options
    )
    partition_filter_clause, partition_parameters = _build_partition_filter_clause(
        resolved_query_options
    )
    batch_filter_clause, batch_parameters = _build_completed_batch_filter_clause(
        resolved_query_options
    )
    advice_limit_clause, advice_order_by_clause = _build_limit_clause(
        query_options=resolved_query_options,
    )
    parameters = {
        "as_of_date": settings.as_of_date.isoformat(),
        "completed_promotion_buffer_days": settings.completed_promotion_buffer_days,
        "query_version": _QUERY_VERSION,
        **diagnostic_parameters,
        **partition_parameters,
        **batch_parameters,
    }
    if resolved_query_options.limit_promotions is not None:
        parameters["limit_promotions"] = int(resolved_query_options.limit_promotions)
    sql = (
        _SQL_TEMPLATE.replace(
            "{{PROMOTION_ADVICE_TABLE}}",
            _validate_identifier(settings.sql.promotion_advice_table),
        )
        .replace("{{ADVICE_FILTER_CLAUSE}}", _COMPLETED_SELECTION_FILTER)
        .replace("{{ADVICE_DIAGNOSTIC_FILTER_CLAUSE}}", diagnostic_filter_clause)
        .replace("{{ADVICE_PARTITION_FILTER_CLAUSE}}", partition_filter_clause)
        .replace("{{ADVICE_BATCH_FILTER_CLAUSE}}", batch_filter_clause)
        .replace("{{ADVICE_LIMIT_CLAUSE}}", advice_limit_clause)
        .replace("{{ADVICE_ORDER_BY_CLAUSE}}", advice_order_by_clause)
        .replace(
            "{{ADVICE_RANK_ORDER_BY_CLAUSE}}",
            "CAST(ar.promotional_end_date AS date) DESC, "
            "CAST(ar.promotion_start_date AS date) DESC, "
            "CAST(ar.promotion_name AS varchar(255)) ASC, "
            "CAST(ar.store_number AS varchar(64)) ASC, "
            "CAST(ar.sku_number AS varchar(64)) ASC, "
            "CAST(ar.promotional_sku_id AS varchar(128)) ASC",
        )
    )
    return PromotionCompletedRenderedStageQuery(
        sql=sql,
        parameters=parameters,
        query_version=_QUERY_VERSION,
        stage_name="completed_base",
        diagnostic_filter_summary={
            **resolved_query_options.diagnostic_filter_summary(),
            "staged_extraction_enabled": True,
            "completed_extraction_stage_mode": "completed_staged_enrichment_v1",
            "extraction_stage": "completed_base",
        },
        estimated_window_summary={
            "selection_mode": "completed",
            "completed_promotion_buffer_days": settings.completed_promotion_buffer_days,
            "completed_sales_history_start_date": (
                settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
            ),
            "as_of_date": settings.as_of_date.isoformat(),
            "query_version": _QUERY_VERSION,
        },
    )


def _validate_query_options(query_options: PromotionBaseQueryOptions) -> None:
    if query_options.limit_promotions is not None and query_options.limit_promotions < 1:
        raise ValueError("limit_promotions must be >= 1 when provided.")
    if (
        query_options.extraction_mode == "diagnostic_topn"
        and query_options.limit_promotions is None
    ):
        raise ValueError(
            "diagnostic_topn extraction mode requires limit_promotions so the narrowed probe remains bounded."
        )
    if (
        query_options.extraction_mode == "live_sql"
        and query_options.limit_promotions is not None
    ):
        raise ValueError(
            "limit_promotions is only supported with extraction_mode='diagnostic_topn'."
        )
    if query_options.completed_batch is not None and query_options.extraction_mode != "live_sql":
        raise ValueError(
            "Completed extraction batching is only supported with extraction_mode='live_sql'."
        )


def _build_diagnostic_filter_clause(
    query_options: PromotionBaseQueryOptions,
) -> tuple[str, dict[str, object]]:
    filter_parts: list[str] = []
    parameters: dict[str, object] = {}
    if query_options.promotion_name_like:
        filter_parts.append(
            "UPPER(CAST(ar.promotion_name AS varchar(255))) LIKE UPPER(CAST(:promotion_name_like AS varchar(255)))"
        )
        parameters["promotion_name_like"] = _normalize_like_pattern(
            query_options.promotion_name_like
        )
    if query_options.store_number is not None:
        filter_parts.append(
            "TRY_CAST(ar.store_number AS bigint) = CAST(:diagnostic_store_number AS bigint)"
        )
        parameters["diagnostic_store_number"] = int(query_options.store_number)
    if query_options.supplier_number is not None:
        filter_parts.append(
            "TRY_CAST(ar.supplier_number AS bigint) = CAST(:diagnostic_supplier_number AS bigint)"
        )
        parameters["diagnostic_supplier_number"] = int(query_options.supplier_number)
    if not filter_parts:
        return "", parameters
    return "\n      AND " + "\n      AND ".join(filter_parts), parameters


def _build_partition_filter_clause(
    query_options: PromotionBaseQueryOptions,
) -> tuple[str, dict[str, object]]:
    if query_options.completed_partition is None:
        return "", {}
    partition_settings = query_options.completed_partition
    if partition_settings.partition_index is None:
        raise ValueError(
            "completed_partition.partition_index must be provided when rendering a single partition query."
        )
    bucket_index = partition_settings.partition_index - 1
    expression = _partition_filter_expression(partition_settings.strategy)
    return (
        "\n      AND " + expression,
        {
            "partition_strategy": partition_settings.strategy,
            "partition_count": partition_settings.partition_count,
            "partition_index": partition_settings.partition_index,
            "partition_bucket_index": bucket_index,
        },
    )


def _build_completed_batch_filter_clause(
    query_options: PromotionBaseQueryOptions,
) -> tuple[str, dict[str, object]]:
    if query_options.completed_batch is None:
        return "", {}
    batch_slice = query_options.completed_batch
    return (
        "\n      AND ar.advice_batch_row_number BETWEEN "
        "CAST(:completed_batch_row_start AS int) AND CAST(:completed_batch_row_end AS int)",
        {
            "completed_batch_index": batch_slice.batch_index,
            "completed_batch_row_start": batch_slice.row_start,
            "completed_batch_row_end": batch_slice.row_end,
            "completed_batch_ordering_key": batch_slice.ordering_key,
        },
    )


def _partition_filter_expression(strategy: PromotionPartitionStrategy) -> str:
    if strategy == "store_number":
        value_expression = "COALESCE(CAST(ar.store_number AS nvarchar(64)), N'')"
        return (
            f"((CHECKSUM({value_expression}) & 2147483647) % CAST(:partition_count AS int)) "
            f"= CAST(:partition_bucket_index AS int)"
        )
    if strategy == "supplier_number":
        value_expression = "COALESCE(CAST(ar.supplier_number AS nvarchar(64)), N'')"
        return (
            f"((CHECKSUM({value_expression}) & 2147483647) % CAST(:partition_count AS int)) "
            f"= CAST(:partition_bucket_index AS int)"
        )
    if strategy == "store_sku_hash_bucket":
        return (
            "((CHECKSUM("
            "COALESCE(CAST(ar.store_number AS nvarchar(64)), N''), "
            "COALESCE(CAST(ar.sku_number AS nvarchar(64)), N'')) & 2147483647) "
            "% CAST(:partition_count AS int)) = CAST(:partition_bucket_index AS int)"
        )
    if strategy == "promotion_name_hash_bucket":
        return (
            "((CHECKSUM(COALESCE(CAST(ar.promotion_name AS nvarchar(255)), N'')) & 2147483647) "
            "% CAST(:partition_count AS int)) = CAST(:partition_bucket_index AS int)"
        )
    if strategy == "promotion_row_key_hash_bucket":
        return (
            "((CHECKSUM("
            "COALESCE(CAST(ar.store_number AS nvarchar(64)), N''), "
            "COALESCE(CAST(ar.sku_number AS nvarchar(64)), N''), "
            "COALESCE(CONVERT(varchar(10), CAST(ar.promotion_start_date AS date), 23), ''), "
            "COALESCE(CONVERT(varchar(10), CAST(ar.promotional_end_date AS date), 23), ''), "
            "COALESCE(CAST(ar.promotional_sku_id AS nvarchar(128)), N''), "
            "COALESCE(CAST(ar.promotion_name AS nvarchar(255)), N'')) & 2147483647) "
            "% CAST(:partition_count AS int)) = CAST(:partition_bucket_index AS int)"
        )
    raise ValueError(f"Unsupported completed partition strategy: {strategy}")


def _build_limit_clause(
    *,
    query_options: PromotionBaseQueryOptions,
) -> tuple[str, str]:
    if query_options.limit_promotions is None:
        return "", ""
    return "TOP (CAST(:limit_promotions AS int)) ", "ORDER BY ar.advice_batch_row_number ASC"


def _normalize_like_pattern(raw_value: str) -> str:
    normalized = raw_value.strip()
    if normalized == "":
        raise ValueError("promotion_name_like must not be empty when provided.")
    if "%" in normalized or "_" in normalized:
        return normalized
    return f"%{normalized}%"


def _validate_identifier(identifier: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(
            f"Unsafe SQL identifier '{identifier}'. Use schema-qualified table names only."
        )
    return identifier