WITH advice_ranked_source AS (
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
        ) AS promotion_row_key
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
sales_line_items AS (
    SELECT
        CAST(pw.Calendar_Date AS date) AS calendar_date,
        TRY_CAST(pw.Store_Number AS bigint) AS store_number,
        TRY_CAST(pw.SKU_Number AS bigint) AS sku_number,
        TRY_CAST(pw.Supplier_Number AS bigint) AS supplier_number,
        CAST(pw.Promotional_Id AS varchar(128)) AS promotional_id,
        CASE
            WHEN TRY_CAST(pw.Promotional_Flag AS int) = 1 THEN 1
            ELSE 0
        END AS promotional_flag,
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
    FROM {{PWLOGD_TABLE}} AS pw
    INNER JOIN candidate_store_sku_windows AS candidate_scope
        ON TRY_CAST(pw.Store_Number AS bigint) = candidate_scope.store_number_key
       AND TRY_CAST(pw.SKU_Number AS bigint) = candidate_scope.sku_number_key
       AND CAST(pw.Calendar_Date AS date) BETWEEN candidate_scope.min_relevant_date AND candidate_scope.max_relevant_date
        WHERE CAST(pw.Calendar_Date AS date) <= CAST(:as_of_date AS date){{COMPLETED_SALES_HISTORY_FILTER_CLAUSE}}
),
sales_transactions AS (
    SELECT
        store_number,
        sku_number,
        calendar_date,
        transaction_key,
        MAX(promotional_flag) AS promotional_flag,
        MAX(promotional_id) AS promotional_id,
        SUM(net_unit_quantity) AS net_unit_quantity
    FROM sales_line_items
    GROUP BY
        store_number,
        sku_number,
        calendar_date,
        transaction_key
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
        SUM(net_sale_inc_gst) AS net_sales_inc_gst,
        MAX(promotional_flag) AS has_promotional_flag,
        MAX(promotional_id) AS last_promotional_id
    FROM sales_line_items
    GROUP BY
        store_number,
        sku_number,
        calendar_date
),
live_window AS (
    SELECT
        ar.promotion_row_key,
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
    FROM advice_source AS ar
    LEFT JOIN sales_daily AS sd
        ON sd.store_number = ar.store_number_key
       AND sd.sku_number = ar.sku_number_key
       AND sd.calendar_date BETWEEN ar.promotion_start_date_date AND ar.promotional_end_date_date
    GROUP BY ar.promotion_row_key
),
live_transactions AS (
    SELECT
        ar.promotion_row_key,
        COUNT(CASE WHEN COALESCE(st.net_unit_quantity, 0.0) <> 0.0 THEN 1 END) AS realised_transaction_count,
        COUNT(
            CASE
                WHEN COALESCE(st.net_unit_quantity, 0.0) <> 0.0
                    AND (
                        st.promotional_flag = 1
                        OR st.promotional_id = ar.promotional_sku_id_key
                    )
                THEN 1
            END
        ) AS realised_promo_transaction_count,
        SUM(
            CASE
                WHEN st.promotional_flag = 1 OR st.promotional_id = ar.promotional_sku_id_key
                    THEN COALESCE(st.net_unit_quantity, 0.0)
                ELSE 0.0
            END
        ) AS actual_flagged_promo_units
    FROM advice_source AS ar
    LEFT JOIN sales_transactions AS st
        ON st.store_number = ar.store_number_key
       AND st.sku_number = ar.sku_number_key
       AND st.calendar_date BETWEEN ar.promotion_start_date_date AND ar.promotional_end_date_date
    GROUP BY ar.promotion_row_key
),
pre_window AS (
    SELECT
        ar.promotion_row_key,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN COALESCE(sd.net_units, 0.0)
                ELSE 0.0
            END
        ) AS pre_56d_units,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN COALESCE(sd.net_units, 0.0)
                ELSE 0.0
            END
        ) AS pre_28d_units,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:immediate_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN COALESCE(sd.net_units, 0.0)
                ELSE 0.0
            END
        ) AS pre_7d_units,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN COALESCE(sd.net_sales_ex_gst, 0.0)
                ELSE 0.0
            END
        ) AS pre_56d_sales_ex_gst,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN COALESCE(sd.net_sales_ex_gst, 0.0)
                ELSE 0.0
            END
        ) AS pre_28d_sales_ex_gst,
        SUM(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:immediate_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN COALESCE(sd.net_sales_ex_gst, 0.0)
                ELSE 0.0
            END
        ) AS pre_7d_sales_ex_gst,
        COUNT(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                 AND COALESCE(sd.net_units, 0.0) > 0.0
                THEN 1
            END
        ) AS pre_56d_days_with_sales,
        COUNT(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                 AND COALESCE(sd.net_units, 0.0) > 0.0
                THEN 1
            END
        ) AS pre_28d_days_with_sales,
        COUNT(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:immediate_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                 AND COALESCE(sd.net_units, 0.0) > 0.0
                THEN 1
            END
        ) AS pre_7d_days_with_sales,
        AVG(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_56d_avg_daily_units,
        AVG(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_28d_avg_daily_units,
        AVG(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:immediate_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_7d_avg_daily_units,
        AVG(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -21, ar.promotion_start_date_date)
                 AND sd.calendar_date < DATEADD(day, -7, ar.promotion_start_date_date)
                THEN sd.net_units
            END
        ) AS pre_prior_21d_avg_daily_units,
        STDEV(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_56d_std_daily_units,
        STDEV(
            CASE
                WHEN sd.calendar_date >= DATEADD(day, -1 * CAST(:short_baseline_days AS int), ar.promotion_start_date_date)
                 AND sd.calendar_date < ar.promotion_start_date_date
                THEN sd.net_units
            END
        ) AS pre_28d_std_daily_units
    FROM advice_source AS ar
    LEFT JOIN sales_daily AS sd
        ON sd.store_number = ar.store_number_key
       AND sd.sku_number = ar.sku_number_key
       AND sd.calendar_date >= DATEADD(day, -1 * CAST(:baseline_lookback_days AS int), ar.promotion_start_date_date)
       AND sd.calendar_date < ar.promotion_start_date_date
    GROUP BY ar.promotion_row_key
),
post_window AS (
    SELECT
        ar.promotion_row_key,
        SUM(COALESCE(sd.net_units, 0.0)) AS post_14d_units,
        SUM(COALESCE(sd.net_sales_ex_gst, 0.0)) AS post_14d_sales_ex_gst,
        AVG(sd.net_units) AS post_14d_avg_daily_units,
        COUNT(CASE WHEN COALESCE(sd.net_units, 0.0) > 0.0 THEN 1 END) AS post_14d_days_with_sales
    FROM advice_source AS ar
    LEFT JOIN sales_daily AS sd
        ON sd.store_number = ar.store_number_key
       AND sd.sku_number = ar.sku_number_key
       AND sd.calendar_date > ar.promotional_end_date_date
       AND sd.calendar_date <= DATEADD(day, CAST(:post_promo_days AS int), ar.promotional_end_date_date)
    GROUP BY ar.promotion_row_key
)
SELECT
    ar.*, 
    DATEDIFF(day, ar.promotion_start_date_date, ar.promotional_end_date_date) + 1 AS live_promo_window_days,
    CAST(:as_of_date AS date) AS extraction_as_of_date,
    CAST(:selection_mode AS varchar(32)) AS extraction_selection_mode,
    CAST(:query_version AS varchar(32)) AS extraction_query_version,
    SYSUTCDATETIME() AS extracted_at_utc,
    COALESCE(lw.actual_units_sold, 0.0) AS actual_units_sold,
    COALESCE(lw.actual_refund_units, 0.0) AS actual_refund_units,
    COALESCE(lw.actual_refund_sales_ex_gst, 0.0) AS actual_refund_sales_ex_gst,
    COALESCE(lw.actual_sales_ex_gst, 0.0) AS actual_sales_ex_gst,
    COALESCE(lw.actual_sales_inc_gst, 0.0) AS actual_sales_inc_gst,
    COALESCE(lw.actual_units_sold, 0.0) AS actual_units_sold_promo,
    COALESCE(lw.actual_sales_ex_gst, 0.0) AS actual_sales_ex_gst_promo,
    COALESCE(lw.actual_sales_inc_gst, 0.0) AS actual_sales_inc_gst_promo,
    COALESCE(lt.realised_transaction_count, 0) AS actual_transaction_count_promo,
    COALESCE(lw.promo_sales_day_count, 0) AS actual_days_with_sales_promo,
    COALESCE(lw.actual_units_sold, 0.0) / NULLIF(COALESCE(lw.promo_sales_day_count, 0), 0) AS actual_avg_units_per_selling_day_promo,
    COALESCE(lw.actual_sales_ex_gst, 0.0) / NULLIF(COALESCE(lw.promo_sales_day_count, 0), 0) AS actual_avg_sales_per_selling_day_promo,
    COALESCE(lw.promo_sales_day_count, 0) AS promo_sales_day_count,
    COALESCE(lw.actual_avg_daily_units, 0.0) AS actual_avg_daily_units,
    COALESCE(lw.actual_std_daily_units, 0.0) AS actual_std_daily_units,
    COALESCE(lw.actual_peak_daily_units, 0.0) AS actual_peak_daily_units,
    COALESCE(lt.realised_transaction_count, 0) AS realised_transaction_count,
    COALESCE(lt.realised_promo_transaction_count, 0) AS realised_promo_transaction_count,
    COALESCE(lt.actual_flagged_promo_units, 0.0) AS actual_flagged_promo_units,
    COALESCE(pw.pre_56d_units, 0.0) AS pre_56d_units,
    COALESCE(pw.pre_28d_units, 0.0) AS pre_28d_units,
    COALESCE(pw.pre_7d_units, 0.0) AS pre_7d_units,
    COALESCE(pw.pre_56d_units, 0.0) AS actual_units_pre_56d,
    COALESCE(pw.pre_28d_units, 0.0) AS actual_units_pre_28d,
    COALESCE(pw.pre_7d_units, 0.0) AS actual_units_pre_7d,
    COALESCE(pw.pre_56d_sales_ex_gst, 0.0) AS pre_56d_sales_ex_gst,
    COALESCE(pw.pre_28d_sales_ex_gst, 0.0) AS pre_28d_sales_ex_gst,
    COALESCE(pw.pre_7d_sales_ex_gst, 0.0) AS pre_7d_sales_ex_gst,
    COALESCE(pw.pre_56d_sales_ex_gst, 0.0) AS actual_sales_ex_gst_pre_56d,
    COALESCE(pw.pre_28d_sales_ex_gst, 0.0) AS actual_sales_ex_gst_pre_28d,
    COALESCE(pw.pre_7d_sales_ex_gst, 0.0) AS actual_sales_ex_gst_pre_7d,
    COALESCE(pw.pre_56d_days_with_sales, 0) AS pre_56d_days_with_sales,
    COALESCE(pw.pre_28d_days_with_sales, 0) AS pre_28d_days_with_sales,
    COALESCE(pw.pre_7d_days_with_sales, 0) AS pre_7d_days_with_sales,
    COALESCE(pw.pre_56d_avg_daily_units, 0.0) AS pre_56d_avg_daily_units,
    COALESCE(pw.pre_28d_avg_daily_units, 0.0) AS pre_28d_avg_daily_units,
    COALESCE(pw.pre_7d_avg_daily_units, 0.0) AS pre_7d_avg_daily_units,
    COALESCE(pw.pre_prior_21d_avg_daily_units, 0.0) AS pre_prior_21d_avg_daily_units,
    COALESCE(pw.pre_56d_std_daily_units, 0.0) AS pre_56d_std_daily_units,
    COALESCE(pw.pre_28d_std_daily_units, 0.0) AS pre_28d_std_daily_units,
    COALESCE(pw.pre_56d_sales_ex_gst, 0.0) / NULLIF(COALESCE(pw.pre_56d_days_with_sales, 0), 0) AS pre_56d_avg_sales_ex_gst_per_selling_day,
    COALESCE(pw.pre_28d_sales_ex_gst, 0.0) / NULLIF(COALESCE(pw.pre_28d_days_with_sales, 0), 0) AS pre_28d_avg_sales_ex_gst_per_selling_day,
    COALESCE(pw.pre_7d_sales_ex_gst, 0.0) / NULLIF(COALESCE(pw.pre_7d_days_with_sales, 0), 0) AS pre_7d_avg_sales_ex_gst_per_selling_day,
    COALESCE(pt.post_14d_units, 0.0) AS post_14d_units,
    COALESCE(pt.post_14d_sales_ex_gst, 0.0) AS post_14d_sales_ex_gst,
    COALESCE(pt.post_14d_units, 0.0) AS actual_units_post_14d,
    COALESCE(pt.post_14d_sales_ex_gst, 0.0) AS actual_sales_ex_gst_post_14d,
    COALESCE(pt.post_14d_avg_daily_units, 0.0) AS post_14d_avg_daily_units,
    COALESCE(pt.post_14d_days_with_sales, 0) AS post_14d_days_with_sales,
    COALESCE(pt.post_14d_sales_ex_gst, 0.0) / NULLIF(COALESCE(pt.post_14d_days_with_sales, 0), 0) AS post_14d_avg_sales_ex_gst_per_selling_day,
    COALESCE(lw.actual_sales_ex_gst, 0.0) / NULLIF(COALESCE(lw.promo_sales_day_count, 0), 0) AS actual_avg_sales_ex_gst_per_selling_day,
    COALESCE(lw.actual_sales_inc_gst, 0.0) / NULLIF(COALESCE(lw.promo_sales_day_count, 0), 0) AS actual_avg_sales_inc_gst_per_selling_day,
    COALESCE(lw.actual_units_sold, 0.0) / NULLIF(COALESCE(lt.realised_transaction_count, 0), 0) AS actual_units_per_transaction,
    COALESCE(lw.actual_sales_ex_gst, 0.0) / NULLIF(COALESCE(lt.realised_transaction_count, 0), 0) AS actual_sales_ex_gst_per_transaction,
    COALESCE(lw.actual_refund_units, 0.0) AS actual_refund_units_promo,
    COALESCE(lw.actual_refund_sales_ex_gst, 0.0) AS actual_refund_sales_ex_gst_promo,
    COALESCE(lt.realised_transaction_count, 0) / NULLIF(DATEDIFF(day, ar.promotion_start_date_date, ar.promotional_end_date_date) + 1, 0) AS actual_transaction_intensity,
    COALESCE(lt.realised_promo_transaction_count, 0) / NULLIF(DATEDIFF(day, ar.promotion_start_date_date, ar.promotional_end_date_date) + 1, 0) AS actual_promo_transaction_intensity,
    COALESCE(lw.inferred_supplier_number, 0) AS inferred_supplier_number,
    CAST('{{PROMOTION_ADVICE_TABLE}}' AS varchar(255)) AS advice_source_table_name,
    CAST('{{PWLOGD_TABLE}}' AS varchar(255)) AS realised_sales_source_table_name
FROM advice_source AS ar
LEFT JOIN live_window AS lw
    ON lw.promotion_row_key = ar.promotion_row_key
LEFT JOIN live_transactions AS lt
    ON lt.promotion_row_key = ar.promotion_row_key
LEFT JOIN pre_window AS pw
    ON pw.promotion_row_key = ar.promotion_row_key
LEFT JOIN post_window AS pt
    ON pt.promotion_row_key = ar.promotion_row_key;
