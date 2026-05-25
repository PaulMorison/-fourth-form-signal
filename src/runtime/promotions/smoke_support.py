from __future__ import annotations

"""Synthetic and patched extraction helpers for promotions system smoke runs."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from data.promotions.extracted_dataset_writer import PromotionExtractionWriter
from data.promotions.promotion_base_extractor import (
    PromotionExtractionManifest,
    PromotionExtractionTelemetry,
    write_extraction_observability,
)
from runtime.promotions.run_promotions_operational_cycle import (
    PromotionOperationalCycleExtractionArtifacts,
)
from runtime.promotions.config import PromotionPipelineSettings


PromotionOperationalCycleExtractionProvider = Callable[..., PromotionOperationalCycleExtractionArtifacts]


_SMOKE_COMPLETED_SCENARIOS: tuple[
    tuple[int, int, int, float, float, float, float, str, str, int],
    ...,
] = (
    (1, 100, 1, 60.0, 100.0, 82.0, 72.0, "Skin Care", "Beauty", 10),
    (1, 100, 2, 68.0, 90.0, 93.0, 88.0, "Skin Care", "Beauty", 10),
    (1, 100, 3, 58.0, 125.0, 38.0, 54.0, "Skin Care", "Beauty", 10),
    (2, 100, 4, 62.0, 82.0, 74.0, 70.0, "Skin Care", "Beauty", 10),
    (1, 101, 5, 34.0, 62.0, 28.0, 32.0, "Wellness", "Health", 11),
    (2, 101, 6, 48.0, 80.0, 86.0, 78.0, "Wellness", "Health", 11),
    (1, 102, 7, 42.0, 92.0, 39.0, 40.0, "Cosmetics", "Beauty", 12),
    (2, 102, 8, 45.0, 70.0, 72.0, 69.0, "Cosmetics", "Beauty", 12),
)

_SMOKE_FUTURE_SCENARIOS: tuple[
    tuple[int, int, int, float, float, float, float, str, str, int],
    ...,
] = (
    (1, 100, 9, 70.0, 95.0, 0.0, 82.0, "Skin Care", "Beauty", 10),
    (2, 101, 10, 52.0, 78.0, 0.0, 83.0, "Wellness", "Health", 11),
)


def smoke_synthetic_default_as_of_date() -> date:
    earliest_future_month = min(scenario[2] for scenario in _SMOKE_FUTURE_SCENARIOS)
    return date(2024, earliest_future_month, 1)


def build_smoke_extraction_provider(
    *,
    execution_mode: str,
    completed_base_path: str | None = None,
    future_base_path: str | None = None,
) -> PromotionOperationalCycleExtractionProvider | None:
    if execution_mode == "live_sql":
        return None
    if execution_mode == "smoke_synthetic":
        return _synthetic_extraction_provider
    if execution_mode == "smoke_patched_extraction":
        if not completed_base_path or not future_base_path:
            raise ValueError(
                "Smoke runs using smoke_patched_extraction require both completed and future base paths."
            )
        completed_frame = _load_base_frame(Path(completed_base_path))
        future_frame = _load_base_frame(Path(future_base_path))
        return _patched_extraction_provider(
            completed_frame=completed_frame,
            future_frame=future_frame,
        )
    raise ValueError(
        "Unsupported smoke execution mode. Use live_sql, smoke_synthetic, or smoke_patched_extraction."
    )


def _synthetic_extraction_provider(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    selection_mode: str,
    query_options: object | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> PromotionOperationalCycleExtractionArtifacts:
    base_frame = (
        build_smoke_completed_promotions_base_frame()
        if selection_mode == "completed"
        else build_smoke_future_promotions_base_frame()
    )
    return _persist_smoke_extraction_artifact(
        settings=settings,
        run_id=run_id,
        selection_mode=selection_mode,
        base_frame=base_frame,
        query_version="promotions_system_smoke_synthetic_v1",
        advice_source_table="smoke.synthetic.promotions",
        realised_sales_source_table="smoke.synthetic.PwlogD",
        progress_callback=progress_callback,
    )


def _patched_extraction_provider(
    *,
    completed_frame: pd.DataFrame,
    future_frame: pd.DataFrame,
) -> PromotionOperationalCycleExtractionProvider:
    def _provider(
        *,
        settings: PromotionPipelineSettings,
        run_id: str,
        selection_mode: str,
        query_options: object | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> PromotionOperationalCycleExtractionArtifacts:
        return _persist_smoke_extraction_artifact(
            settings=settings,
            run_id=run_id,
            selection_mode=selection_mode,
            base_frame=completed_frame.copy() if selection_mode == "completed" else future_frame.copy(),
            query_version="promotions_system_smoke_patched_extraction_v1",
            advice_source_table="smoke.patched.promotions",
            realised_sales_source_table="smoke.patched.PwlogD",
            progress_callback=progress_callback,
        )

    return _provider


def _persist_smoke_extraction_artifact(
    *,
    settings: PromotionPipelineSettings,
    run_id: str,
    selection_mode: str,
    base_frame: pd.DataFrame,
    query_version: str,
    advice_source_table: str,
    realised_sales_source_table: str,
    progress_callback: Callable[[str], None] | None = None,
) -> PromotionOperationalCycleExtractionArtifacts:
    normalized_frame = base_frame.copy()
    extracted_at_utc = datetime.now(tz=UTC).isoformat()
    normalized_frame["extraction_run_id"] = run_id
    normalized_frame["extraction_selection_mode"] = selection_mode
    normalized_frame["extraction_materialized_at_utc"] = extracted_at_utc
    normalized_frame["extraction_materialized_as_of_date"] = settings.as_of_date.isoformat()
    manifest = PromotionExtractionManifest(
        run_id=run_id,
        selection_mode=selection_mode,
        query_version=query_version,
        as_of_date=settings.as_of_date.isoformat(),
        extracted_at_utc=extracted_at_utc,
        row_count=int(len(normalized_frame.index)),
        column_count=int(len(normalized_frame.columns)),
        duplicate_promotion_row_keys=int(normalized_frame["promotion_row_key"].duplicated().sum()),
        advice_source_table=advice_source_table,
        realised_sales_source_table=realised_sales_source_table,
        columns=tuple(str(column_name) for column_name in normalized_frame.columns),
        candidate_promotion_row_count=int(len(normalized_frame.index)),
    )
    telemetry = PromotionExtractionTelemetry(
        run_id=run_id,
        selection_mode=selection_mode,
        as_of_date=settings.as_of_date.isoformat(),
        query_version=query_version,
        advice_source_table=advice_source_table,
        realised_sales_source_table=realised_sales_source_table,
        rendered_query_parameter_summary={
            "selection_mode": selection_mode,
            "query_version": query_version,
            "execution_mode": "smoke",
        },
        extracted_at_utc=extracted_at_utc,
        extraction_mode="smoke",
        row_count=int(len(normalized_frame.index)),
        candidate_promotion_row_count=int(len(normalized_frame.index)),
        column_count=int(len(normalized_frame.columns)),
        duplicate_promotion_row_keys=int(normalized_frame["promotion_row_key"].duplicated().sum()),
        extraction_status="ready_to_write",
        current_sql_subphase="writing extracted parquet and manifest",
        query_timeout_seconds=settings.sql.query_timeout_seconds,
        query_timeout_applied=False,
    )
    if progress_callback is not None:
        progress_callback("writing extracted parquet and manifest")
    telemetry.dataframe_write_started_at_utc = datetime.now(tz=UTC).isoformat()
    persisted = PromotionExtractionWriter().write(
        base_frame=normalized_frame,
        manifest=manifest,
        artifact_paths=settings.artifacts,
    )
    telemetry.output_parquet_path = str(persisted.base_path)
    telemetry.output_manifest_path = str(persisted.manifest_path)
    telemetry.dataframe_write_completed_at_utc = datetime.now(tz=UTC).isoformat()
    telemetry.mark_success()
    observability = write_extraction_observability(
        telemetry=telemetry,
        settings=settings,
        artifact_paths=settings.artifacts,
    )
    return PromotionOperationalCycleExtractionArtifacts(
        selection_mode=selection_mode,
        frame=normalized_frame,
        base_path=str(persisted.base_path),
        manifest_path=str(persisted.manifest_path),
        rendered_sql_path=None,
        rendered_sql_parameters_path=None,
        telemetry_json_path=observability.telemetry_json_path,
        telemetry_csv_path=observability.telemetry_csv_path,
        diagnostics_summary_json_path=observability.diagnostics_summary_json_path,
        diagnostics_summary_txt_path=observability.diagnostics_summary_txt_path,
        candidate_promotion_row_count=int(len(normalized_frame.index)),
        manifest=manifest.to_dict(),
    )


def _load_base_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing smoke extraction input file: {path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(
        f"Unsupported smoke extraction input format for {path}. Use .csv or .parquet."
    )


def build_smoke_completed_promotions_base_frame() -> pd.DataFrame:
    return _build_rows(scenarios=list(_SMOKE_COMPLETED_SCENARIOS), future=False)


def build_smoke_future_promotions_base_frame() -> pd.DataFrame:
    return _build_rows(scenarios=list(_SMOKE_FUTURE_SCENARIOS), future=True)


def _build_rows(
    *,
    scenarios: list[tuple[int, int, int, float, float, float, float, str, str, int]],
    future: bool,
) -> pd.DataFrame:
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
