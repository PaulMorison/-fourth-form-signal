from __future__ import annotations

"""Safe renderer for the promotions base extraction SQL template.

Canon ownership:
- Loads the governed promotions extraction SQL template from disk.
- Substitutes only validated table identifiers and fixed selection clauses.
- Keeps dynamic values as bound parameters so extraction code does not inline
  runtime dates, windows, or mode-specific controls into executable SQL.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

from runtime.promotions.config import (
    PromotionCompletedPartitionSettings,
    PromotionPartitionStrategy,
    PromotionPipelineSettings,
)


PromotionSelectionMode = Literal["completed", "future"]
PromotionExtractionMode = Literal["live_sql", "diagnostic_topn"]

_SQL_FILE = Path(__file__).with_name("promotion_base_extraction.sql")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}$")
_QUERY_VERSION = "promotion_base_v4"
_SELECTION_FILTERS: dict[PromotionSelectionMode, str] = {
    "completed": (
        "CAST(ar.promotional_end_date AS date) "
        "< DATEADD(day, -1 * CAST(:completed_promotion_buffer_days AS int), CAST(:as_of_date AS date))"
    ),
    "future": "CAST(ar.promotion_start_date AS date) > CAST(:as_of_date AS date)",
}
_CANDIDATE_COUNT_SQL_TEMPLATE = """WITH advice_ranked_source AS (
    SELECT
        ar.*, 
        ROW_NUMBER() OVER (
            ORDER BY {{ADVICE_RANK_ORDER_BY_CLAUSE}}
        ) AS advice_batch_row_number{{ADVICE_PROOF_SLICE_RANK_COLUMNS}}
    FROM {{PROMOTION_ADVICE_TABLE}} AS ar
    WHERE {{ADVICE_FILTER_CLAUSE}}{{ADVICE_DIAGNOSTIC_FILTER_CLAUSE}}{{ADVICE_PARTITION_FILTER_CLAUSE}}
),
advice_source AS (
    SELECT
        {{ADVICE_LIMIT_CLAUSE}}1 AS candidate_row_marker
    FROM advice_ranked_source AS ar
    WHERE 1 = 1{{ADVICE_BATCH_FILTER_CLAUSE}}{{ADVICE_PROOF_SLICE_FILTER_CLAUSE}}
    {{ADVICE_ORDER_BY_CLAUSE}}
)
SELECT COUNT(*) AS candidate_promotion_row_count
FROM advice_source;
"""
_PREFLIGHT_SQL_TEMPLATE = """WITH advice_ranked_source AS (
    SELECT
        ar.*, 
        ROW_NUMBER() OVER (
            ORDER BY {{ADVICE_RANK_ORDER_BY_CLAUSE}}
        ) AS advice_batch_row_number{{ADVICE_PROOF_SLICE_RANK_COLUMNS}}
    FROM {{PROMOTION_ADVICE_TABLE}} AS ar
    WHERE {{ADVICE_FILTER_CLAUSE}}{{ADVICE_DIAGNOSTIC_FILTER_CLAUSE}}{{ADVICE_PARTITION_FILTER_CLAUSE}}
),
advice_source AS (
    SELECT
        {{ADVICE_LIMIT_CLAUSE}}ar.*,
        CAST(ar.promotion_start_date AS date) AS promotion_start_date_date,
        CAST(ar.promotional_end_date AS date) AS promotional_end_date_date,
        TRY_CAST(ar.store_number AS bigint) AS store_number_key,
        TRY_CAST(ar.sku_number AS bigint) AS sku_number_key
    FROM advice_ranked_source AS ar
    WHERE 1 = 1{{ADVICE_BATCH_FILTER_CLAUSE}}{{ADVICE_PROOF_SLICE_FILTER_CLAUSE}}
    {{ADVICE_ORDER_BY_CLAUSE}}
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
    FROM advice_source
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
candidate_store_sku_pairs AS (
    SELECT DISTINCT
        store_number_key,
        sku_number_key
    FROM candidate_store_sku_windows
),
candidate_live_promo_spans AS (
    SELECT
        DATEDIFF(day, promotion_start_date_date, promotional_end_date_date) + 1 AS live_promo_days
    FROM advice_source
    WHERE promotion_start_date_date IS NOT NULL
      AND promotional_end_date_date IS NOT NULL
),
candidate_window_spans AS (
    SELECT
        store_number_key,
        sku_number_key,
        min_relevant_date,
        max_relevant_date,
        DATEDIFF(day, min_relevant_date, max_relevant_date) + 1 AS window_span_days
    FROM candidate_store_sku_windows
),
candidate_grouped_live_window_spans AS (
    SELECT
        store_number_key,
        sku_number_key,
        DATEDIFF(
            day,
            DATEADD(day, CAST(:baseline_lookback_days AS int), min_relevant_date),
            DATEADD(day, -1 * CAST(:post_promo_days AS int), max_relevant_date)
        ) + 1 AS grouped_live_window_span_days
    FROM candidate_store_sku_windows
)
SELECT
    (SELECT COUNT(*) FROM advice_source) AS candidate_promotion_row_count,
    (SELECT COUNT(*) FROM candidate_store_sku_pairs) AS candidate_store_sku_count,
    (SELECT COUNT(*) FROM candidate_window_spans) AS candidate_window_count,
    COALESCE((SELECT SUM(window_span_days) FROM candidate_window_spans), 0) AS candidate_window_span_days_total,
    COALESCE((SELECT MAX(window_span_days) FROM candidate_window_spans), 0) AS candidate_window_span_days_max,
    CAST(
        COALESCE(
            (SELECT AVG(CAST(window_span_days AS float)) FROM candidate_window_spans),
            0.0
        ) AS float
    ) AS candidate_window_span_days_avg,
    (SELECT MIN(min_relevant_date) FROM candidate_window_spans) AS candidate_global_min_date,
    (SELECT MAX(max_relevant_date) FROM candidate_window_spans) AS candidate_global_max_date,
    COALESCE((SELECT MAX(grouped_live_window_span_days) FROM candidate_grouped_live_window_spans), 0) AS observed_max_grouped_live_window_span_days,
    COALESCE((SELECT MAX(live_promo_days) FROM candidate_live_promo_spans), 0) AS observed_max_live_promo_days,
    COALESCE((SELECT COUNT(DISTINCT store_number_key) FROM candidate_store_sku_pairs), 0) AS distinct_store_count,
    COALESCE((SELECT COUNT(DISTINCT sku_number_key) FROM candidate_store_sku_pairs), 0) AS distinct_sku_count;
"""


@dataclass(frozen=True)
class PromotionCompletedBatchSlice:
    batch_index: int
    row_start: int
    row_end: int
    ordering_key: str = "completed_advice_row_number_v1"

    def __post_init__(self) -> None:
        if self.batch_index < 1:
            raise ValueError("batch_index must be >= 1.")
        if self.row_start < 1:
            raise ValueError("row_start must be >= 1.")
        if self.row_end < self.row_start:
            raise ValueError("row_end must be >= row_start.")

    def to_dict(self) -> dict[str, object]:
        return {
            "batch_index": self.batch_index,
            "row_start": self.row_start,
            "row_end": self.row_end,
            "ordering_key": self.ordering_key,
        }


@dataclass(frozen=True)
class PromotionBaseQueryOptions:
    extraction_mode: PromotionExtractionMode = "live_sql"
    limit_promotions: int | None = None
    promotion_name_like: str | None = None
    store_number: int | None = None
    supplier_number: int | None = None
    completed_partition: PromotionCompletedPartitionSettings | None = None
    completed_batch: PromotionCompletedBatchSlice | None = None
    completed_proof_slice_date_count: int | None = None

    def diagnostic_filter_summary(self) -> dict[str, object]:
        partition_summary = self.completed_partition.to_dict() if self.completed_partition else {}
        batch_summary = self.completed_batch.to_dict() if self.completed_batch else {}
        return {
            "extraction_mode": self.extraction_mode,
            "limit_promotions": self.limit_promotions,
            "promotion_name_like": self.promotion_name_like,
            "store_number": self.store_number,
            "supplier_number": self.supplier_number,
            "partition_strategy": partition_summary.get("strategy"),
            "partition_count": partition_summary.get("partition_count"),
            "partition_index": partition_summary.get("partition_index"),
            "batch_index": batch_summary.get("batch_index"),
            "batch_row_start": batch_summary.get("row_start"),
            "batch_row_end": batch_summary.get("row_end"),
            "batch_ordering_key": batch_summary.get("ordering_key"),
            "completed_proof_slice_date_count": self.completed_proof_slice_date_count,
        }


@dataclass(frozen=True)
class RenderedPromotionBaseQuery:
    sql: str
    parameters: dict[str, object]
    candidate_count_sql: str
    preflight_sql: str
    selection_mode: PromotionSelectionMode
    extraction_mode: PromotionExtractionMode
    diagnostic_filter_summary: dict[str, object]
    estimated_window_summary: dict[str, object]
    query_version: str = _QUERY_VERSION


def _validate_identifier(identifier: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(
            f"Unsafe SQL identifier '{identifier}'. Use schema-qualified table names only."
        )
    return identifier


def render_promotion_base_query(
    *,
    settings: PromotionPipelineSettings,
    selection_mode: PromotionSelectionMode,
    query_options: PromotionBaseQueryOptions | None = None,
) -> RenderedPromotionBaseQuery:
    """Render the extraction SQL with validated identifiers and bound parameters."""

    resolved_options = query_options or PromotionBaseQueryOptions()
    _validate_query_options(resolved_options, selection_mode=selection_mode)
    template = _SQL_FILE.read_text(encoding="utf-8")
    diagnostic_filter_clause, diagnostic_parameters = _build_diagnostic_filter_clause(
        resolved_options
    )
    partition_filter_clause, partition_parameters = _build_partition_filter_clause(
        resolved_options
    )
    batch_filter_clause, batch_parameters = _build_completed_batch_filter_clause(
        resolved_options
    )
    completed_sales_history_filter_clause = _build_completed_sales_history_filter_clause(
        selection_mode=selection_mode,
    )
    advice_rank_order_by_clause = _build_advice_rank_order_by_clause(
        selection_mode=selection_mode,
    )
    advice_limit_clause, advice_order_by_clause = _build_limit_clause(
        selection_mode=selection_mode,
        query_options=resolved_options,
    )
    proof_slice_filter_clause, proof_slice_parameters = _build_completed_proof_slice_filter_clause(
        selection_mode=selection_mode,
        query_options=resolved_options,
    )
    proof_slice_rank_columns = _build_completed_proof_slice_rank_columns(
        query_options=resolved_options,
        advice_rank_order_by_clause=advice_rank_order_by_clause,
    )
    parameters = {
        "as_of_date": settings.as_of_date.isoformat(),
        "baseline_lookback_days": settings.windows.baseline_lookback_days,
        "short_baseline_days": settings.windows.short_baseline_days,
        "immediate_baseline_days": settings.windows.immediate_baseline_days,
        "post_promo_days": settings.windows.post_promo_days,
        "completed_promotion_buffer_days": settings.completed_promotion_buffer_days,
        "selection_mode": selection_mode,
        "query_version": _QUERY_VERSION,
        **diagnostic_parameters,
        **partition_parameters,
        **batch_parameters,
        **proof_slice_parameters,
    }
    if selection_mode == "completed":
        parameters["completed_sales_history_start_date"] = (
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
        )
    if resolved_options.limit_promotions is not None:
        parameters["limit_promotions"] = int(resolved_options.limit_promotions)
    sql = _render_sql_template(
        template=template,
        selection_mode=selection_mode,
        advice_diagnostic_filter_clause=diagnostic_filter_clause,
        advice_partition_filter_clause=partition_filter_clause,
        advice_batch_filter_clause=batch_filter_clause,
        advice_proof_slice_filter_clause=proof_slice_filter_clause,
        completed_sales_history_filter_clause=completed_sales_history_filter_clause,
        advice_limit_clause=advice_limit_clause,
        advice_order_by_clause=advice_order_by_clause,
        advice_rank_order_by_clause=advice_rank_order_by_clause,
        advice_proof_slice_rank_columns=proof_slice_rank_columns,
        promotion_advice_table=settings.sql.promotion_advice_table,
        pwlogd_table=settings.sql.pwlogd_table,
    )
    candidate_count_sql = _render_sql_template(
        template=_CANDIDATE_COUNT_SQL_TEMPLATE,
        selection_mode=selection_mode,
        advice_diagnostic_filter_clause=diagnostic_filter_clause,
        advice_partition_filter_clause=partition_filter_clause,
        advice_batch_filter_clause=batch_filter_clause,
        advice_proof_slice_filter_clause=proof_slice_filter_clause,
        completed_sales_history_filter_clause=completed_sales_history_filter_clause,
        advice_limit_clause=advice_limit_clause,
        advice_order_by_clause=advice_order_by_clause,
        advice_rank_order_by_clause=advice_rank_order_by_clause,
        advice_proof_slice_rank_columns=proof_slice_rank_columns,
        promotion_advice_table=settings.sql.promotion_advice_table,
        pwlogd_table=settings.sql.pwlogd_table,
    )
    preflight_sql = _render_sql_template(
        template=_PREFLIGHT_SQL_TEMPLATE,
        selection_mode=selection_mode,
        advice_diagnostic_filter_clause=diagnostic_filter_clause,
        advice_partition_filter_clause=partition_filter_clause,
        advice_batch_filter_clause=batch_filter_clause,
        advice_proof_slice_filter_clause=proof_slice_filter_clause,
        completed_sales_history_filter_clause=completed_sales_history_filter_clause,
        advice_limit_clause=advice_limit_clause,
        advice_order_by_clause=advice_order_by_clause,
        advice_rank_order_by_clause=advice_rank_order_by_clause,
        advice_proof_slice_rank_columns=proof_slice_rank_columns,
        promotion_advice_table=settings.sql.promotion_advice_table,
        pwlogd_table=settings.sql.pwlogd_table,
    )
    return RenderedPromotionBaseQuery(
        sql=sql,
        parameters=parameters,
        candidate_count_sql=candidate_count_sql,
        preflight_sql=preflight_sql,
        selection_mode=selection_mode,
        extraction_mode=resolved_options.extraction_mode,
        diagnostic_filter_summary=resolved_options.diagnostic_filter_summary(),
        estimated_window_summary=_build_estimated_window_summary(
            settings=settings,
            selection_mode=selection_mode,
        ),
    )


def _validate_query_options(
    query_options: PromotionBaseQueryOptions,
    *,
    selection_mode: PromotionSelectionMode,
) -> None:
    if query_options.limit_promotions is not None and query_options.limit_promotions < 1:
        raise ValueError("limit_promotions must be >= 1 when provided.")
    if (
        query_options.completed_proof_slice_date_count is not None
        and query_options.completed_proof_slice_date_count < 1
    ):
        raise ValueError("completed_proof_slice_date_count must be >= 1 when provided.")
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
    if query_options.completed_proof_slice_date_count is not None:
        if selection_mode != "completed":
            raise ValueError("completed proof slicing is only supported for selection_mode='completed'.")
        if query_options.extraction_mode != "diagnostic_topn":
            raise ValueError("completed proof slicing requires extraction_mode='diagnostic_topn'.")
        if query_options.limit_promotions is None:
            raise ValueError("completed proof slicing requires limit_promotions as the per-date-pair row cap.")
    if query_options.completed_partition is not None and selection_mode != "completed":
        raise ValueError("Completed extraction partitioning is only supported for selection_mode='completed'.")
    if query_options.completed_batch is not None and selection_mode != "completed":
        raise ValueError("Completed extraction batching is only supported for selection_mode='completed'.")
    if (
        query_options.completed_batch is not None
        and query_options.extraction_mode != "live_sql"
    ):
        raise ValueError("Completed extraction batching is only supported with extraction_mode='live_sql'.")


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


def _build_completed_proof_slice_filter_clause(
    *,
    selection_mode: PromotionSelectionMode,
    query_options: PromotionBaseQueryOptions,
) -> tuple[str, dict[str, object]]:
    if query_options.completed_proof_slice_date_count is None:
        return "", {}
    return (
        "\n      AND ar.advice_date_rank <= CAST(:completed_proof_slice_date_count AS int)"
        "\n      AND ar.advice_date_row_number <= CAST(:limit_promotions AS int)",
        {
            "completed_proof_slice_date_count": int(
                query_options.completed_proof_slice_date_count
            )
        },
    )


def _build_completed_proof_slice_rank_columns(
    *,
    query_options: PromotionBaseQueryOptions,
    advice_rank_order_by_clause: str,
) -> str:
    if query_options.completed_proof_slice_date_count is None:
        return ""
    return (
        ",\n        DENSE_RANK() OVER ("
        "\n            ORDER BY CAST(ar.promotion_start_date AS date) DESC"
        "\n        ) AS advice_date_rank,"
        "\n        ROW_NUMBER() OVER ("
        "\n            PARTITION BY CAST(ar.promotion_start_date AS date)"
        f"\n            ORDER BY {advice_rank_order_by_clause}"
        "\n        ) AS advice_date_row_number"
    )


def _build_completed_sales_history_filter_clause(
    *,
    selection_mode: PromotionSelectionMode,
) -> str:
    if selection_mode != "completed":
        return ""
    return (
        "\n      AND CAST(pw.Calendar_Date AS date) >= "
        "CAST(:completed_sales_history_start_date AS date)"
    )


def _partition_filter_expression(strategy: PromotionPartitionStrategy) -> str:
    if strategy == "store_number":
        value_expression = "COALESCE(CAST(ar.store_number AS nvarchar(64)), N'')"
        return (
            f"((CHECKSUM({value_expression}) & 2147483647) % CAST(:partition_count AS int)) "
            f"= CAST(:partition_bucket_index AS int)"
        )
    elif strategy == "supplier_number":
        value_expression = "COALESCE(CAST(ar.supplier_number AS nvarchar(64)), N'')"
        return (
            f"((CHECKSUM({value_expression}) & 2147483647) % CAST(:partition_count AS int)) "
            f"= CAST(:partition_bucket_index AS int)"
        )
    elif strategy == "store_sku_hash_bucket":
        return (
            "((CHECKSUM("
            "COALESCE(CAST(ar.store_number AS nvarchar(64)), N''), "
            "COALESCE(CAST(ar.sku_number AS nvarchar(64)), N'')) & 2147483647) "
            "% CAST(:partition_count AS int)) = CAST(:partition_bucket_index AS int)"
        )
    elif strategy == "promotion_name_hash_bucket":
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
    selection_mode: PromotionSelectionMode,
    query_options: PromotionBaseQueryOptions,
) -> tuple[str, str]:
    if query_options.limit_promotions is None:
        return "", ""
    if query_options.completed_proof_slice_date_count is not None:
        return "", ""
    return "TOP (CAST(:limit_promotions AS int)) ", "ORDER BY ar.advice_batch_row_number ASC"


def _build_advice_rank_order_by_clause(
    *,
    selection_mode: PromotionSelectionMode,
) -> str:
    if selection_mode == "completed":
        return (
            "CAST(ar.promotional_end_date AS date) DESC, "
            "CAST(ar.promotion_start_date AS date) DESC, "
            "CAST(ar.promotion_name AS varchar(255)) ASC, "
            "CAST(ar.store_number AS varchar(64)) ASC, "
            "CAST(ar.sku_number AS varchar(64)) ASC, "
            "CAST(ar.promotional_sku_id AS varchar(128)) ASC"
        )
    return (
        "CAST(ar.promotion_start_date AS date) ASC, "
        "CAST(ar.promotional_end_date AS date) ASC, "
        "CAST(ar.promotion_name AS varchar(255)) ASC, "
        "CAST(ar.store_number AS varchar(64)) ASC, "
        "CAST(ar.sku_number AS varchar(64)) ASC, "
        "CAST(ar.promotional_sku_id AS varchar(128)) ASC"
    )


def _render_sql_template(
    *,
    template: str,
    selection_mode: PromotionSelectionMode,
    advice_diagnostic_filter_clause: str,
    advice_partition_filter_clause: str,
    advice_batch_filter_clause: str,
    advice_proof_slice_filter_clause: str,
    completed_sales_history_filter_clause: str,
    advice_limit_clause: str,
    advice_order_by_clause: str,
    advice_rank_order_by_clause: str,
    advice_proof_slice_rank_columns: str,
    promotion_advice_table: str,
    pwlogd_table: str,
) -> str:
    return (
        template.replace(
            "{{PROMOTION_ADVICE_TABLE}}",
            _validate_identifier(promotion_advice_table),
        )
        .replace(
            "{{PWLOGD_TABLE}}",
            _validate_identifier(pwlogd_table),
        )
        .replace("{{ADVICE_FILTER_CLAUSE}}", _SELECTION_FILTERS[selection_mode])
        .replace("{{ADVICE_DIAGNOSTIC_FILTER_CLAUSE}}", advice_diagnostic_filter_clause)
        .replace("{{ADVICE_PARTITION_FILTER_CLAUSE}}", advice_partition_filter_clause)
        .replace("{{ADVICE_BATCH_FILTER_CLAUSE}}", advice_batch_filter_clause)
        .replace("{{ADVICE_PROOF_SLICE_FILTER_CLAUSE}}", advice_proof_slice_filter_clause)
        .replace(
            "{{COMPLETED_SALES_HISTORY_FILTER_CLAUSE}}",
            completed_sales_history_filter_clause,
        )
        .replace("{{ADVICE_LIMIT_CLAUSE}}", advice_limit_clause)
        .replace("{{ADVICE_ORDER_BY_CLAUSE}}", advice_order_by_clause)
        .replace("{{ADVICE_RANK_ORDER_BY_CLAUSE}}", advice_rank_order_by_clause)
        .replace("{{ADVICE_PROOF_SLICE_RANK_COLUMNS}}", advice_proof_slice_rank_columns)
    )


def _build_estimated_window_summary(
    *,
    settings: PromotionPipelineSettings,
    selection_mode: PromotionSelectionMode,
) -> dict[str, object]:
    return {
        "selection_mode": selection_mode,
        "estimated_sales_lookback_days": settings.windows.baseline_lookback_days,
        "estimated_sales_lookforward_days": (
            settings.windows.post_promo_days if selection_mode == "completed" else 0
        ),
        "completed_promotion_buffer_days": settings.completed_promotion_buffer_days,
        "completed_sales_history_start_date": (
            settings.completed_extraction_runtime.completed_sales_history_start_date.isoformat()
            if selection_mode == "completed"
            else None
        ),
        "as_of_date": settings.as_of_date.isoformat(),
    }


def _normalize_like_pattern(raw_value: str) -> str:
    normalized = raw_value.strip()
    if normalized == "":
        raise ValueError("promotion_name_like must not be empty when provided.")
    if "%" in normalized or "_" in normalized:
        return normalized
    return f"%{normalized}%"
