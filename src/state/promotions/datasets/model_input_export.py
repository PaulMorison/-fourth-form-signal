from __future__ import annotations

"""Governed model-input export and feature-lineage audit.

Canon ownership:
- Persists the EXACT dataframe handed to the trained model for both training
  and scoring as parquet plus a row-capped human-inspectable CSV with consistent
  4-decimal-place rounding for non-integer numeric columns.
- Writes a feature-lineage audit (`feature_lineage_audit.{csv,json}`) showing
  per-column presence across raw/cleaned/engineered/model-input stages plus
  target and suspected-leakage flags.
- Writes a fail-loud final-model contract validation summary
  (`final_model_contract_validation.json`).
- Does not own feature definitions, target definitions, training, or scoring.

Lineage trace (for governed audit reference):

    raw extract              -> data/promotions/mssql_query_executor.py
    cleaned/extracted base   -> state/promotions/extraction/...
                                artifact: extracted/<run_id>/promotion_base.parquet
    targets                  -> state/promotions/targets/* (PromotionTargetEngineer)
    engineered features      -> state/promotions/feature_engineering/* (PromotionFeatureEngineer)
    train-ready dataset      -> state/promotions/datasets/dataset_assembler.py
                                artifact: training/datasets/<run_id>/training_ready.parquet
    model input (training)   -> models/promotions/preprocessing.prepare_model_input_frame
                                artifact: inspection/<run_id>/model_training_input.parquet
    model input (scoring)    -> runtime/promotions/scoring_service.PromotionModelScorer
                                artifact: inspection/<run_id>/model_scoring_input.parquet
    scored rows              -> runtime/promotions/scoring_service.PromotionModelScorer
                                artifact: prediction/scoring/<run_id>/promotion_row_predictions.parquet
    store-facing reporting   -> surfaces/promotions/reporting/store_prediction_download_builder.py

Row/column count checks live in the metadata JSON beside each artifact and in
PromotionDatasetManifest.row_count / training_metrics for stage-to-stage deltas.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.demand.ft_allocation_discipline import (
    ALLOCATION_DISCIPLINE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_basket_context_feature_bundle import (
    BASKET_MODEL_USE_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_baseline_demand_orientation import (
    BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_discount_conditioned_demand import (
    DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_discount_elasticity import (
    DISCOUNT_ELASTICITY_FEATURE_COLUMNS,
)
from state.promotions.feature_engineering.demand.ft_uplift_decomposition import (
    UPLIFT_DECOMPOSITION_FEATURE_COLUMNS,
)
from models.promotions.model_input_quality import build_model_input_quality_summary_text
from state.promotions.feature_engineering.demand.probability import (
    PROBABILITY_MODEL_USE_FEATURE_COLUMNS,
    PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS,
)


LOGGER = logging.getLogger(__name__)

# User-governed standards (do not weaken without an explicit decision):
INSPECTION_SAMPLE_ROWS = 10_000
NUMERIC_EXPORT_DECIMALS = 4
TARGET_COLUMN_PREFIX = "target_"
ENGINEERED_FEATURE_PREFIX = "feature_"
NULL_WARNING_RATE_THRESHOLD = 0.5

# Raw advice columns that must NOT reach the model as direct features.
# (They may exist in the dataset for joinability/diagnostics but should never
# appear as a column in the model-input frame.)
RAW_ADVICE_LEAKAGE_DENYLIST: tuple[str, ...] = (
    "actual_units_sold",
    "actual_units_sold_promo",
    "actual_gross_profit_dollars",
    "actual_sales_ex_gst",
    "actual_units_sold_first_day",
    "actual_units_sold_first_7_days",
    "promo_actual_units_sold",
    "post_promo_units",
)

# Governed engineered features that must survive into the final model-input frame
# on every training and scoring run. Review-only probability diagnostics remain
# in the engineered dataset and audit surfaces, but they are intentionally
# excluded from the trained schema unless explicitly promoted later.
REQUIRED_NEW_ENGINEERED_FEATURES: tuple[str, ...] = (
    # prior-promo memory
    "feature_prior_promo_14d_flag",
    "feature_prior_promo_28d_flag",
    "feature_prior_promo_56d_flag",
    "feature_prior_promo_units_56d",
    "feature_prior_promo_days_since_last_promo",
    "feature_prior_same_or_better_discount_56d_flag",
    "feature_prior_promo_price_memory_score",
    "feature_prior_promo_cannibalisation_risk_score",
    "feature_historical_promo_events_same_discount",
    "feature_historical_promo_events_same_or_better_discount",
    "feature_historical_units_same_discount_avg",
    "feature_historical_units_same_or_better_discount_avg",
    "feature_historical_discount_response_confidence",
    "feature_discount_band_response_avg",
    "feature_discount_band_event_count",
    "feature_probability_zero_demand_same_or_better_discount",
    "feature_probability_low_demand_vs_baseline_same_or_better_discount",
    "feature_probability_demand_exceeds_allocation_same_or_better_discount",
    "feature_probability_units_below_allocation_same_or_better_discount",
    "feature_probability_stockout_vs_stock_basis_same_or_better_discount",
    "feature_promo_history_evidence_strength",
    "feature_sparse_history_penalty",
    "feature_order_evidence_quality_score",
    "feature_overallocation_risk_score",
    # governed probability layer: explicit model-use subset only
    *PROBABILITY_MODEL_USE_FEATURE_COLUMNS,
    # governed allocation discipline: probability-backed model-use subset only
    *ALLOCATION_DISCIPLINE_FEATURE_COLUMNS,
    # governed baseline orientation / same-discount / elasticity / uplift decomposition
    *BASELINE_DEMAND_ORIENTATION_FEATURE_COLUMNS,
    *DISCOUNT_CONDITIONED_DEMAND_FEATURE_COLUMNS,
    *DISCOUNT_ELASTICITY_FEATURE_COLUMNS,
    *UPLIFT_DECOMPOSITION_FEATURE_COLUMNS,
    # promo-vs-baseline separation
    "feature_non_promo_units_56d",
    "feature_promo_units_56d",
    "feature_promo_to_nonpromo_demand_ratio_56d",
    "feature_discount_elasticity_proxy",
    # intermittent-demand cadence
    "feature_sales_interval_days_cv_56d",
    "feature_intermittent_demand_flag",
    "feature_sparse_repeat_purchase_flag",
    "feature_sales_day_density_56d",
    # governed basket / mission layer: explicit model-use subset only
    *BASKET_MODEL_USE_FEATURE_COLUMNS,
)

REVIEW_ONLY_PROBABILITY_ENGINEERED_FEATURES: tuple[str, ...] = (
    *PROBABILITY_REVIEW_ONLY_FEATURE_COLUMNS,
)

MODEL_INPUT_FEATURE_LIST_COLUMNS: tuple[str, ...] = (
    "ordinal",
    "column_name",
    "dtype",
    "is_feature_column",
    "is_target_column",
    "is_discount_related_feature",
    "is_same_discount_history_feature",
    "is_intermittent_demand_feature",
    "is_suspected_leakage_column",
)

MODEL_INPUT_CSV_DICTIONARY_COLUMNS: tuple[str, ...] = (
    "column_name",
    "column_role",
    "source_module",
    "description",
    "nullable_flag",
    "example_value",
    "whether_used_in_training",
    "whether_used_in_scoring",
    "source_family",
)

TRACE_IDENTIFIER_PREFIX = "trace_"

MODEL_INPUT_TRACE_IDENTIFIER_COLUMNS: tuple[str, ...] = (
    "promotion_row_key",
    "store_number",
    "store_number_key",
    "promotion_header_key",
    "promotion_name",
    "promotion_start_date_date",
    "promotional_end_date_date",
    "sku_number",
    "sku_number_key",
    "promotional_sku_id",
    "promotional_sku_id_key",
    "sku_description",
    "department",
    "category",
    "supplier_name",
    "inferred_supplier_number",
)

MODEL_INPUT_DIAGNOSIS_PRIORITY_COLUMNS: tuple[str, ...] = (
    "target_actual_units_sold",
    "target_actual_gross_profit_dollars",
    "target_overallocation_flag",
    "target_underallocation_flag",
    "target_stockout_flag",
    "actual_units_sold",
    "actual_units_sold_promo",
    "actual_gross_profit_dollars",
    "regular_price",
    "promo_price",
    "discount_percent",
    "customer_discount",
    "promo_gm_pct",
    "promo_gm_unit",
    "scan_rebate_dollars",
    "current_soh",
    "qty_on_order",
    "pl_allocation_qty",
    "bar_units",
    "stock_basis_units",
    "required_implied_units",
    "baseline_daily_units",
    "baseline_expected_units",
    "pre_56d_units",
    "pre_28d_units",
    "pre_7d_units",
    "pre_56d_avg_daily_units",
    "pre_28d_avg_daily_units",
    "pre_7d_avg_daily_units",
    "feature_historical_promo_events_same_discount",
    "feature_historical_units_same_discount_avg",
    "feature_historical_promo_events_same_or_better_discount",
    "feature_historical_units_same_or_better_discount_avg",
    "feature_prior_promo_units_56d",
    "feature_prior_promo_days_since_last_promo",
    "feature_prior_same_or_better_discount_56d_flag",
    "feature_same_discount_prior_event_count",
    "feature_same_discount_prior_units_avg",
    "feature_same_discount_prior_uplift_ratio_avg",
    "feature_same_discount_days_since_last_event",
    "feature_non_promo_30d_avg_daily_units",
    "feature_non_promo_56d_avg_daily_units",
    "feature_non_promo_84d_avg_daily_units",
    "feature_non_promo_base_trend_30d_vs_56d",
    "feature_discount_elasticity_estimate",
    "feature_discount_elasticity_confidence_score",
    "feature_expected_baseline_units_promo_window",
    "feature_expected_incremental_uplift_units_same_discount",
    "feature_expected_total_units_from_baseline_plus_uplift",
    "feature_uplift_confidence_score",
    "feature_uplift_demand_support_flag",
    "feature_discount_band_response_avg",
    "feature_discount_band_event_count",
    "feature_basket_attach_rate",
    "feature_sku_basket_dependency_score",
    "feature_top_companion_sku_1_share",
    "feature_transactions_with_sku_per_day",
    "feature_weekend_share_with_sku",
    "feature_stock_constrained_history_flag",
    "feature_lost_sales_risk_score",
    "feature_companion_absence_risk_score",
    "feature_capital_at_risk",
    "feature_total_stock_pressure_ratio",
    "feature_supported_sell_through_score",
    "feature_discount_evidence_strength_score",
    "feature_launch_stock_support_score",
    "feature_total_window_pressure_vs_launch_support_conflict_score",
)


def _is_discount_related_feature(column_name: str) -> bool:
    if not column_name.startswith(ENGINEERED_FEATURE_PREFIX):
        return False
    lowered = column_name.lower()
    return "discount" in lowered or "price" in lowered


def _is_same_discount_history_feature(column_name: str) -> bool:
    if not column_name.startswith(ENGINEERED_FEATURE_PREFIX):
        return False
    lowered = column_name.lower()
    return "same_discount" in lowered or "same_or_better_discount" in lowered


def _is_intermittent_demand_feature(column_name: str) -> bool:
    if not column_name.startswith(ENGINEERED_FEATURE_PREFIX):
        return False
    lowered = column_name.lower()
    return any(
        token in lowered
        for token in (
            "intermittent",
            "sales_interval",
            "sparse_repeat_purchase",
            "sales_day_density",
        )
    )


@dataclass(frozen=True)
class ModelInputAuditPaths:
    parquet_path: str
    sample_csv_path: str
    metadata_json_path: str
    feature_lineage_csv_path: str
    feature_lineage_json_path: str
    contract_validation_json_path: str
    feature_quality_audit_csv_path: str | None = None
    feature_quality_audit_json_path: str | None = None
    feature_leakage_review_csv_path: str | None = None
    feature_correlation_review_csv_path: str | None = None
    model_input_quality_summary_csv_path: str | None = None
    model_input_quality_summary_json_path: str | None = None
    model_input_quality_summary_txt_path: str | None = None


@dataclass(frozen=True)
class ModelInputInspectionExportPaths:
    full_parquet_path: str
    sample_csv_path: str
    metadata_json_path: str
    null_profile_csv_path: str
    constant_columns_csv_path: str
    feature_list_csv_path: str


@dataclass(frozen=True)
class ModelInputCsvDiagnosisExportPaths:
    output_root: str
    completed_raw_csv_path: str | None
    completed_features_csv_path: str | None
    future_raw_csv_path: str | None
    future_features_csv_path: str | None
    column_dictionary_csv_path: str
    manifest_json_path: str


class PromotionFinalModelContractError(ValueError):
    """Raised when the final model-input frame violates the governed contract."""


class PromotionModelInputCsvExportError(ValueError):
    """Raised when the governed full CSV diagnosis export cannot be written safely."""


def _is_integer_dtype(series: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(series):
        return True
    if pd.api.types.is_integer_dtype(series):
        return True
    # Pandas nullable Int64 etc.
    try:
        kind = series.dtype.kind  # type: ignore[attr-defined]
    except AttributeError:
        return False
    return kind in {"i", "u", "b"}


def _round_for_export(frame: pd.DataFrame, *, decimals: int = NUMERIC_EXPORT_DECIMALS) -> pd.DataFrame:
    """Return a copy of `frame` with float-like columns rounded to `decimals`.

    Integer-typed columns are preserved exactly. Object/categorical columns
    are passed through unchanged.
    """

    rounded = frame.copy()
    for column_name in rounded.columns:
        series = rounded[column_name]
        if _is_integer_dtype(series):
            continue
        if pd.api.types.is_float_dtype(series):
            rounded[column_name] = series.round(decimals)
            continue
        if pd.api.types.is_numeric_dtype(series):
            # Mixed/object numeric — coerce-and-round defensively.
            coerced = pd.to_numeric(series, errors="coerce")
            if coerced.notna().any():
                rounded[column_name] = coerced.round(decimals)
    return rounded


def _apply_inspection_filters(
    frame: pd.DataFrame,
    *,
    filters: Mapping[str, Sequence[str]] | None,
) -> pd.DataFrame:
    if not filters:
        return frame.copy()
    working = frame.copy()
    for column_name, raw_values in filters.items():
        if column_name not in working.columns:
            raise PromotionFinalModelContractError(
                f"Model-input inspection filter column is missing from exact model input: {column_name}"
            )
        values = [str(value) for value in raw_values if str(value) != ""]
        if not values:
            continue
        working = working.loc[working[column_name].astype(str).isin(values)].copy()
    return working


def _model_input_null_profile(frame: pd.DataFrame) -> pd.DataFrame:
    row_count = max(int(len(frame.index)), 1)
    rows = []
    for column_name in frame.columns:
        null_count = int(frame[column_name].isna().sum())
        rows.append(
            {
                "column_name": column_name,
                "dtype": str(frame[column_name].dtype),
                "null_count": null_count,
                "null_rate": round(float(null_count / row_count), 6),
                "non_null_count": int(frame[column_name].notna().sum()),
            }
        )
    return pd.DataFrame(rows)


def _model_input_constant_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column_name in frame.columns:
        non_null = frame[column_name].dropna()
        unique_count = int(non_null.nunique(dropna=True))
        if unique_count <= 1:
            value = "" if non_null.empty else str(non_null.iloc[0])
            rows.append(
                {
                    "column_name": column_name,
                    "dtype": str(frame[column_name].dtype),
                    "non_null_count": int(non_null.shape[0]),
                    "unique_non_null_count": unique_count,
                    "constant_value": value[:256],
                }
            )
    return pd.DataFrame(
        rows,
        columns=(
            "column_name",
            "dtype",
            "non_null_count",
            "unique_non_null_count",
            "constant_value",
        ),
    )


def _model_input_feature_list(frame: pd.DataFrame) -> pd.DataFrame:
    denylist = set(RAW_ADVICE_LEAKAGE_DENYLIST)
    rows = []
    for position, column_name in enumerate(frame.columns, start=1):
        rows.append(
            {
                "ordinal": position,
                "column_name": column_name,
                "dtype": str(frame[column_name].dtype),
                "is_feature_column": bool(column_name.startswith(ENGINEERED_FEATURE_PREFIX)),
                "is_target_column": bool(column_name.startswith(TARGET_COLUMN_PREFIX)),
                "is_discount_related_feature": _is_discount_related_feature(column_name),
                "is_same_discount_history_feature": _is_same_discount_history_feature(column_name),
                "is_intermittent_demand_feature": _is_intermittent_demand_feature(column_name),
                "is_suspected_leakage_column": bool(column_name in denylist),
            }
        )
    return pd.DataFrame(rows, columns=MODEL_INPUT_FEATURE_LIST_COLUMNS)


def _feature_names_by_flag(feature_list: pd.DataFrame, flag_column: str) -> list[str]:
    if feature_list.empty or flag_column not in feature_list.columns:
        return []
    return feature_list.loc[
        feature_list[flag_column].astype(bool), "column_name"
    ].astype(str).tolist()


def write_model_input_inspection_artifacts(
    *,
    model_input_frame: pd.DataFrame,
    output_root: str | Path,
    run_id: str | None = None,
    source_path: str | Path | None = None,
    stage: str | None = None,
    filters: Mapping[str, Sequence[str]] | None = None,
    sample_rows: int = INSPECTION_SAMPLE_ROWS,
) -> ModelInputInspectionExportPaths:
    """Write the governed operator/debug inspection pack for exact model input.

    The full parquet remains exact after filtering; rounded CSV/profile files are
    derived views for inspection only.
    """

    filtered = _apply_inspection_filters(model_input_frame, filters=filters)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)

    full_parquet_path = root / "model_input_full.parquet"
    sample_csv_path = root / "model_input_sample_10000.csv"
    metadata_json_path = root / "model_input_metadata.json"
    null_profile_csv_path = root / "model_input_null_profile.csv"
    constant_columns_csv_path = root / "model_input_constant_columns.csv"
    feature_list_csv_path = root / "model_input_feature_list.csv"

    filtered.to_parquet(full_parquet_path, index=False)
    _round_for_export(filtered.head(sample_rows)).to_csv(sample_csv_path, index=False)
    null_profile = _model_input_null_profile(filtered)
    null_profile.to_csv(null_profile_csv_path, index=False)
    constant_columns = _model_input_constant_columns(filtered)
    constant_columns.to_csv(constant_columns_csv_path, index=False)
    feature_list = _model_input_feature_list(filtered)
    feature_list.to_csv(feature_list_csv_path, index=False)

    suspected_leakage_columns = _feature_names_by_flag(
        feature_list,
        "is_suspected_leakage_column",
    )
    engineered_feature_names = _feature_names_by_flag(feature_list, "is_feature_column")
    target_column_names = _feature_names_by_flag(feature_list, "is_target_column")
    discount_related_feature_names = _feature_names_by_flag(
        feature_list,
        "is_discount_related_feature",
    )
    same_discount_history_feature_names = _feature_names_by_flag(
        feature_list,
        "is_same_discount_history_feature",
    )
    intermittent_demand_feature_names = _feature_names_by_flag(
        feature_list,
        "is_intermittent_demand_feature",
    )
    high_null_warning_columns = (
        null_profile.loc[
            null_profile["null_rate"].astype(float) >= NULL_WARNING_RATE_THRESHOLD,
            "column_name",
        ]
        .astype(str)
        .tolist()
    )
    constant_column_names = constant_columns["column_name"].astype(str).tolist()
    suspicious_column_warnings = {
        "high_null_columns": high_null_warning_columns,
        "constant_columns": constant_column_names,
        "suspected_leakage_columns": suspected_leakage_columns,
    }
    metadata = {
        "run_id": run_id,
        "stage": stage,
        "source_path": str(source_path) if source_path is not None else None,
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "row_count": int(len(filtered.index)),
        "source_row_count": int(len(model_input_frame.index)),
        "column_count": int(len(filtered.columns)),
        "sample_row_count": int(min(sample_rows, len(filtered.index))),
        "filters_applied": {key: [str(value) for value in values] for key, values in (filters or {}).items()},
        "null_profile_row_count": int(len(null_profile.index)),
        "constant_column_count": int(len(constant_columns.index)),
        "feature_column_count": int(feature_list["is_feature_column"].sum()) if not feature_list.empty else 0,
        "target_column_count": int(feature_list["is_target_column"].sum()) if not feature_list.empty else 0,
        "engineered_feature_names": engineered_feature_names,
        "target_column_names": target_column_names,
        "discount_related_feature_names": discount_related_feature_names,
        "same_discount_history_feature_names": same_discount_history_feature_names,
        "intermittent_demand_feature_names": intermittent_demand_feature_names,
        "null_warning_rate_threshold": NULL_WARNING_RATE_THRESHOLD,
        "high_null_warning_columns": high_null_warning_columns,
        "constant_columns": constant_column_names,
        "suspected_leakage_columns": suspected_leakage_columns,
        "suspicious_column_warnings": suspicious_column_warnings,
        "artifact_files": {
            "model_input_full.parquet": str(full_parquet_path),
            "model_input_sample_10000.csv": str(sample_csv_path),
            "model_input_metadata.json": str(metadata_json_path),
            "model_input_null_profile.csv": str(null_profile_csv_path),
            "model_input_constant_columns.csv": str(constant_columns_csv_path),
            "model_input_feature_list.csv": str(feature_list_csv_path),
        },
    }
    metadata_json_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    return ModelInputInspectionExportPaths(
        full_parquet_path=str(full_parquet_path),
        sample_csv_path=str(sample_csv_path),
        metadata_json_path=str(metadata_json_path),
        null_profile_csv_path=str(null_profile_csv_path),
        constant_columns_csv_path=str(constant_columns_csv_path),
        feature_list_csv_path=str(feature_list_csv_path),
    )


def _selected_columns(columns: Sequence[str], preferred_order: Sequence[str]) -> list[str]:
    column_set = set(columns)
    ordered = [column_name for column_name in preferred_order if column_name in column_set]
    ordered.extend(column_name for column_name in columns if column_name not in set(ordered))
    return ordered


def _trace_identifier_columns(frame: pd.DataFrame) -> list[str]:
    return [
        column_name
        for column_name in MODEL_INPUT_TRACE_IDENTIFIER_COLUMNS
        if column_name in frame.columns
    ]


def _is_trace_identifier_column(column_name: str) -> bool:
    if column_name in MODEL_INPUT_TRACE_IDENTIFIER_COLUMNS:
        return True
    if not column_name.startswith(TRACE_IDENTIFIER_PREFIX):
        return False
    return column_name.removeprefix(TRACE_IDENTIFIER_PREFIX) in MODEL_INPUT_TRACE_IDENTIFIER_COLUMNS


def _trace_identifier_export_name(column_name: str, occupied_columns: set[str]) -> str:
    proposed_name = f"{TRACE_IDENTIFIER_PREFIX}{column_name}"
    if proposed_name not in occupied_columns:
        return proposed_name
    suffix = 2
    while f"{proposed_name}_{suffix}" in occupied_columns:
        suffix += 1
    return f"{proposed_name}_{suffix}"


def _order_raw_model_input_columns(frame: pd.DataFrame) -> list[str]:
    identifiers = _trace_identifier_columns(frame)
    target_columns = [column_name for column_name in frame.columns if column_name.startswith(TARGET_COLUMN_PREFIX)]
    priority_columns = [
        column_name
        for column_name in MODEL_INPUT_DIAGNOSIS_PRIORITY_COLUMNS
        if column_name in frame.columns and column_name not in set(identifiers) | set(target_columns)
    ]
    feature_columns = [
        column_name
        for column_name in frame.columns
        if column_name.startswith(ENGINEERED_FEATURE_PREFIX)
        and column_name not in set(identifiers) | set(target_columns) | set(priority_columns)
    ]
    leading_columns = [*identifiers, *target_columns, *priority_columns, *feature_columns]
    return _selected_columns(tuple(frame.columns), leading_columns)


def _filter_mask_for_model_input_export(
    frame: pd.DataFrame,
    *,
    filters: Mapping[str, Sequence[str]] | None,
) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for column_name, raw_values in (filters or {}).items():
        values = [str(value) for value in raw_values if str(value) != ""]
        if not values:
            continue
        if column_name not in frame.columns:
            raise PromotionModelInputCsvExportError(
                f"Model-input CSV export filter column is missing from raw/source frame: {column_name}"
            )
        mask = mask & frame[column_name].astype(str).isin(values)
    return mask


def _build_feature_export_frame(
    *,
    raw_frame: pd.DataFrame,
    feature_frame: pd.DataFrame,
) -> pd.DataFrame:
    identifier_columns = _trace_identifier_columns(raw_frame)
    model_feature_columns = list(feature_frame.columns)
    model_feature_column_set = set(model_feature_columns)
    occupied_columns = set(model_feature_columns)
    identifier_rename_map: dict[str, str] = {}
    for column_name in identifier_columns:
        if column_name not in model_feature_column_set:
            occupied_columns.add(column_name)
            continue
        export_name = _trace_identifier_export_name(column_name, occupied_columns)
        identifier_rename_map[column_name] = export_name
        occupied_columns.add(export_name)
    identifier_frame = (
        raw_frame.loc[:, identifier_columns]
        .rename(columns=identifier_rename_map)
        .reset_index(drop=True)
    )
    model_features = feature_frame.loc[:, model_feature_columns].reset_index(drop=True)
    return pd.concat([identifier_frame, model_features], axis=1)


def _prepare_model_input_stage_export(
    *,
    stage_label: str,
    raw_frame: pd.DataFrame | None,
    feature_frame: pd.DataFrame | None,
    filters: Mapping[str, Sequence[str]] | None,
    export_raw: bool,
    export_features: bool,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    if raw_frame is None:
        raise PromotionModelInputCsvExportError(
            f"{stage_label} model-input CSV export requires a raw/source frame for traceability and filtering"
        )
    if export_features and feature_frame is None:
        raise PromotionModelInputCsvExportError(
            f"{stage_label} model-input CSV export requires the exact model feature frame"
        )
    if feature_frame is not None and len(raw_frame.index) != len(feature_frame.index):
        raise PromotionModelInputCsvExportError(
            f"{stage_label} raw/source rows ({len(raw_frame.index)}) do not align to exact model feature rows ({len(feature_frame.index)})"
        )

    mask = _filter_mask_for_model_input_export(raw_frame, filters=filters)
    raw_filtered = raw_frame.loc[mask].copy().reset_index(drop=True)
    feature_filtered: pd.DataFrame | None = None
    if feature_frame is not None:
        feature_filtered = feature_frame.iloc[mask.to_numpy()].copy().reset_index(drop=True)

    raw_export: pd.DataFrame | None = None
    feature_export: pd.DataFrame | None = None
    if export_raw:
        raw_export = raw_filtered.loc[:, _order_raw_model_input_columns(raw_filtered)].copy()
    if export_features:
        assert feature_filtered is not None
        feature_export = _build_feature_export_frame(
            raw_frame=raw_filtered,
            feature_frame=feature_filtered,
        )
    return raw_export, feature_export


def _source_family_for_model_input_column(column_name: str) -> str:
    if column_name.startswith(TRACE_IDENTIFIER_PREFIX) and _is_trace_identifier_column(column_name):
        return "identifier"
    lowered = column_name.lower()
    if "promotion_backtest" in lowered or "forecast_trust" in lowered:
        return "backtest_promotion_level_trust"
    if column_name.startswith(ENGINEERED_FEATURE_PREFIX) and any(
        token in lowered
        for token in (
            "basket",
            "companion",
            "weekend",
            "pay_cycle",
            "mission",
            "transaction",
            "solo_purchase",
            "low_traffic",
            "stock_constrained",
            "lost_sales",
        )
    ):
        if "probability_" in lowered:
            return "demand_basket_mission_probability"
        return "demand_basket_mission"
    if (
        "prior_promo" in lowered
        or "same_or_better_discount" in lowered
        or "same_discount" in lowered
        or "discount_band" in lowered
        or "historical_discount_response" in lowered
    ):
        return "prior_promotion_memory"
    if any(
        token in lowered
        for token in (
            "poisson",
            "negative_binomial",
            "bayesian_poisson",
            "zero_inflated",
            "structural_zero",
            "probability_",
        )
    ):
        return "demand_probability"
    if "historical" in lowered or "demand" in lowered or "baseline" in lowered or "pre_" in lowered:
        return "demand_history"
    if any(token in lowered for token in ("stock", "soh", "inventory", "allocation", "cover", "qty_on_order")):
        return "stock_inventory"
    if any(token in lowered for token in ("price", "discount", "promo", "gm", "margin", "rebate", "cost")):
        return "price_promo_economics"
    if any(token in lowered for token in ("review", "exclude", "flag", "quality")):
        return "exclusions_review_flags"
    if column_name in MODEL_INPUT_TRACE_IDENTIFIER_COLUMNS:
        return "identifier"
    return "operational_flags"


def _column_role_for_model_input_dictionary(
    *,
    column_name: str,
    training_model_columns: set[str],
    scoring_model_columns: set[str],
) -> str:
    if column_name.startswith(TRACE_IDENTIFIER_PREFIX) and _is_trace_identifier_column(column_name):
        return "identifier"
    if column_name.startswith(TARGET_COLUMN_PREFIX):
        return "target"
    if column_name.startswith(ENGINEERED_FEATURE_PREFIX):
        return "engineered_feature"
    if column_name in training_model_columns or column_name in scoring_model_columns:
        return "raw_input"
    if column_name in MODEL_INPUT_TRACE_IDENTIFIER_COLUMNS:
        return "identifier"
    if column_name.endswith("_path") or column_name.endswith("_at_utc"):
        return "metadata"
    return "raw_input"


def _source_module_for_model_input_column(column_name: str, column_role: str) -> str:
    if column_role == "target":
        return "state.promotions.targets"
    if column_name.startswith(ENGINEERED_FEATURE_PREFIX):
        return "state.promotions.feature_engineering"
    if column_role == "identifier":
        return "state.promotions.datasets.dataset_assembler"
    if column_role == "raw_input":
        return "models.promotions.preprocessing"
    return "state.promotions.datasets.model_input_export"


def _description_for_model_input_column(column_name: str, column_role: str, source_family: str) -> str:
    if column_role == "identifier":
        return "Traceability identifier retained at the front of diagnostic exports."
    if column_role == "target":
        return "Completed-promotion target or label available for training diagnostics only."
    if column_name.startswith(ENGINEERED_FEATURE_PREFIX):
        return f"Engineered feature used for model diagnosis; source family {source_family}."
    if column_role == "raw_input":
        return f"Raw or base predictor available at the model-input boundary; source family {source_family}."
    return "Export metadata column."


def _example_value_for_column(column_name: str, frames: Sequence[pd.DataFrame]) -> str:
    for frame in frames:
        if column_name not in frame.columns:
            continue
        non_null = frame[column_name].dropna()
        if non_null.empty:
            continue
        return str(non_null.iloc[0])[:256]
    return ""


def _nullable_flag_for_column(column_name: str, frames: Sequence[pd.DataFrame]) -> bool:
    for frame in frames:
        if column_name in frame.columns and bool(frame[column_name].isna().any()):
            return True
    return False


def _build_model_input_column_dictionary(
    *,
    completed_raw_export: pd.DataFrame | None,
    completed_feature_export: pd.DataFrame | None,
    completed_feature_frame: pd.DataFrame | None,
    future_raw_export: pd.DataFrame | None,
    future_feature_export: pd.DataFrame | None,
    future_feature_frame: pd.DataFrame | None,
) -> pd.DataFrame:
    visible_frames = [
        frame
        for frame in (
            completed_raw_export,
            completed_feature_export,
            future_raw_export,
            future_feature_export,
        )
        if frame is not None
    ]
    training_model_columns = set(completed_feature_frame.columns) if completed_feature_frame is not None else set()
    scoring_model_columns = set(future_feature_frame.columns) if future_feature_frame is not None else set()
    all_columns: list[str] = []
    seen: set[str] = set()
    for frame in visible_frames:
        for column_name in frame.columns:
            if column_name in seen:
                continue
            seen.add(column_name)
            all_columns.append(column_name)

    rows: list[dict[str, object]] = []
    for column_name in all_columns:
        source_family = _source_family_for_model_input_column(column_name)
        column_role = _column_role_for_model_input_dictionary(
            column_name=column_name,
            training_model_columns=training_model_columns,
            scoring_model_columns=scoring_model_columns,
        )
        rows.append(
            {
                "column_name": column_name,
                "column_role": column_role,
                "source_module": _source_module_for_model_input_column(column_name, column_role),
                "description": _description_for_model_input_column(column_name, column_role, source_family),
                "nullable_flag": _nullable_flag_for_column(column_name, visible_frames),
                "example_value": _example_value_for_column(column_name, visible_frames),
                "whether_used_in_training": column_name in training_model_columns,
                "whether_used_in_scoring": column_name in scoring_model_columns,
                "source_family": source_family,
            }
        )
    return pd.DataFrame(rows, columns=MODEL_INPUT_CSV_DICTIONARY_COLUMNS)


def _ensure_model_input_csv_export_can_write(paths: Sequence[Path], *, overwrite: bool) -> None:
    existing_paths = [path for path in paths if path.exists()]
    if existing_paths and not overwrite:
        raise PromotionModelInputCsvExportError(
            "Model-input CSV export target already exists; pass overwrite=True to replace: "
            + ", ".join(str(path) for path in existing_paths)
        )


def write_model_input_csv_diagnosis_bundle(
    *,
    output_root: str | Path,
    run_id: str,
    completed_raw_frame: pd.DataFrame | None = None,
    completed_feature_frame: pd.DataFrame | None = None,
    future_raw_frame: pd.DataFrame | None = None,
    future_feature_frame: pd.DataFrame | None = None,
    filters: Mapping[str, Sequence[str]] | None = None,
    source_paths: Mapping[str, str | None] | None = None,
    as_of_date: str | None = None,
    export_raw: bool = True,
    export_features: bool = True,
    overwrite: bool = False,
) -> ModelInputCsvDiagnosisExportPaths:
    """Write full CSV exports for row-aligned raw/source and exact model-input features.

    Feature CSVs are pre-scale views of the persisted model-input parquet. Raw
    CSVs are row-aligned source frames used to trace those feature rows back to
    promotion/store/SKU context.
    """

    if not export_raw and not export_features:
        raise PromotionModelInputCsvExportError("At least one of export_raw or export_features must be true.")
    if completed_raw_frame is None and completed_feature_frame is None and future_raw_frame is None and future_feature_frame is None:
        raise PromotionModelInputCsvExportError("No completed or future model-input frames were supplied for CSV export.")

    root = Path(output_root)
    completed_raw_csv_path = root / "completed_model_input_raw.csv" if completed_raw_frame is not None and export_raw else None
    completed_features_csv_path = root / "completed_model_input_features.csv" if completed_raw_frame is not None and export_features else None
    future_raw_csv_path = root / "future_model_input_raw.csv" if future_raw_frame is not None and export_raw else None
    future_features_csv_path = root / "future_model_input_features.csv" if future_raw_frame is not None and export_features else None
    column_dictionary_csv_path = root / "model_input_column_dictionary.csv"
    manifest_json_path = root / "model_input_csv_export_manifest.json"

    output_paths = [
        path
        for path in (
            completed_raw_csv_path,
            completed_features_csv_path,
            future_raw_csv_path,
            future_features_csv_path,
            column_dictionary_csv_path,
            manifest_json_path,
        )
        if path is not None
    ]
    _ensure_model_input_csv_export_can_write(output_paths, overwrite=overwrite)
    root.mkdir(parents=True, exist_ok=True)

    completed_raw_export: pd.DataFrame | None = None
    completed_feature_export: pd.DataFrame | None = None
    if completed_raw_frame is not None or completed_feature_frame is not None:
        completed_raw_export, completed_feature_export = _prepare_model_input_stage_export(
            stage_label="completed",
            raw_frame=completed_raw_frame,
            feature_frame=completed_feature_frame,
            filters=filters,
            export_raw=export_raw,
            export_features=export_features,
        )

    future_raw_export: pd.DataFrame | None = None
    future_feature_export: pd.DataFrame | None = None
    if future_raw_frame is not None or future_feature_frame is not None:
        future_raw_export, future_feature_export = _prepare_model_input_stage_export(
            stage_label="future",
            raw_frame=future_raw_frame,
            feature_frame=future_feature_frame,
            filters=filters,
            export_raw=export_raw,
            export_features=export_features,
        )

    if completed_raw_csv_path is not None and completed_raw_export is not None:
        _round_for_export(completed_raw_export).to_csv(completed_raw_csv_path, index=False)
    if completed_features_csv_path is not None and completed_feature_export is not None:
        _round_for_export(completed_feature_export).to_csv(completed_features_csv_path, index=False)
    if future_raw_csv_path is not None and future_raw_export is not None:
        _round_for_export(future_raw_export).to_csv(future_raw_csv_path, index=False)
    if future_features_csv_path is not None and future_feature_export is not None:
        _round_for_export(future_feature_export).to_csv(future_features_csv_path, index=False)

    column_dictionary = _build_model_input_column_dictionary(
        completed_raw_export=completed_raw_export,
        completed_feature_export=completed_feature_export,
        completed_feature_frame=completed_feature_frame,
        future_raw_export=future_raw_export,
        future_feature_export=future_feature_export,
        future_feature_frame=future_feature_frame,
    )
    column_dictionary.to_csv(column_dictionary_csv_path, index=False)

    source_paths_payload = {key: value for key, value in (source_paths or {}).items() if value is not None}
    manifest = {
        "run_id": run_id,
        "as_of_date": as_of_date,
        "created_at_utc": datetime.now(tz=UTC).isoformat(),
        "export_root": str(root),
        "pre_scale_feature_export": True,
        "filters_applied": {key: [str(value) for value in values] for key, values in (filters or {}).items()},
        "source_paths": source_paths_payload,
        "row_counts": {
            "completed_raw_rows": int(len(completed_raw_export.index)) if completed_raw_export is not None else None,
            "completed_feature_rows": int(len(completed_feature_export.index)) if completed_feature_export is not None else None,
            "future_raw_rows": int(len(future_raw_export.index)) if future_raw_export is not None else None,
            "future_feature_rows": int(len(future_feature_export.index)) if future_feature_export is not None else None,
        },
        "column_counts": {
            "completed_raw_columns": int(len(completed_raw_export.columns)) if completed_raw_export is not None else None,
            "completed_feature_columns": int(len(completed_feature_export.columns)) if completed_feature_export is not None else None,
            "future_raw_columns": int(len(future_raw_export.columns)) if future_raw_export is not None else None,
            "future_feature_columns": int(len(future_feature_export.columns)) if future_feature_export is not None else None,
            "dictionary_rows": int(len(column_dictionary.index)),
        },
        "artifact_files": {
            "completed_model_input_raw.csv": str(completed_raw_csv_path) if completed_raw_csv_path is not None else None,
            "completed_model_input_features.csv": str(completed_features_csv_path) if completed_features_csv_path is not None else None,
            "future_model_input_raw.csv": str(future_raw_csv_path) if future_raw_csv_path is not None else None,
            "future_model_input_features.csv": str(future_features_csv_path) if future_features_csv_path is not None else None,
            "model_input_column_dictionary.csv": str(column_dictionary_csv_path),
            "model_input_csv_export_manifest.json": str(manifest_json_path),
        },
    }
    manifest_json_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return ModelInputCsvDiagnosisExportPaths(
        output_root=str(root),
        completed_raw_csv_path=str(completed_raw_csv_path) if completed_raw_csv_path is not None else None,
        completed_features_csv_path=str(completed_features_csv_path) if completed_features_csv_path is not None else None,
        future_raw_csv_path=str(future_raw_csv_path) if future_raw_csv_path is not None else None,
        future_features_csv_path=str(future_features_csv_path) if future_features_csv_path is not None else None,
        column_dictionary_csv_path=str(column_dictionary_csv_path),
        manifest_json_path=str(manifest_json_path),
    )


def _validate_final_model_contract(
    *,
    model_input: pd.DataFrame,
    expected_feature_columns: Sequence[str],
    target_columns: Sequence[str],
    allow_constant_columns: Iterable[str] = (),
    required_engineered_features: Sequence[str] | None = None,
    quality_report=None,
) -> dict[str, object]:
    """Run governed assertions and return a serializable validation report.

    Raises PromotionFinalModelContractError on hard violations.
    """

    issues: list[str] = []
    columns = list(model_input.columns)
    duplicate_columns = sorted({name for name in columns if columns.count(name) > 1})
    if duplicate_columns:
        issues.append(f"duplicate_feature_columns:{duplicate_columns}")

    missing_expected = [name for name in expected_feature_columns if name not in columns]
    if missing_expected:
        issues.append(f"missing_expected_columns:{missing_expected}")

    # Fail loud when the governed prior-promo memory / intermittent-demand
    # features are not reaching the model. They MUST be in the model input.
    # `required_engineered_features=None` means "use the production registry"
    # (`REQUIRED_NEW_ENGINEERED_FEATURES`); unit tests can pass `()` to opt out
    # when validating tiny synthetic frames.
    required_new_features = (
        REQUIRED_NEW_ENGINEERED_FEATURES
        if required_engineered_features is None
        else tuple(required_engineered_features)
    )
    explicitly_removed_columns = (
        set(getattr(quality_report, "removed_feature_columns", ()))
        if quality_report is not None
        else set()
    )
    missing_required_new = [
        name
        for name in required_new_features
        if name not in columns and name not in explicitly_removed_columns
    ]
    if missing_required_new:
        issues.append(
            f"missing_required_new_engineered_features:{missing_required_new}"
        )

    target_in_features = [name for name in columns if name in set(target_columns)]
    if target_in_features:
        issues.append(f"target_leaking_into_features:{target_in_features}")

    leakage_denylist_present = [
        name for name in columns if name in set(RAW_ADVICE_LEAKAGE_DENYLIST)
    ]
    if leakage_denylist_present:
        issues.append(f"raw_advice_columns_in_features:{leakage_denylist_present}")

    all_null_columns = [
        name for name in columns if len(model_input.index) > 0 and model_input[name].isna().all()
    ]
    if all_null_columns:
        issues.append(f"all_null_columns:{all_null_columns}")

    constant_columns: list[str] = []
    allow_constant = set(allow_constant_columns)
    for name in columns:
        series = model_input[name]
        if not pd.api.types.is_numeric_dtype(series):
            continue
        non_null = series.dropna()
        if len(non_null) > 1 and non_null.nunique(dropna=True) <= 1 and name not in allow_constant:
            constant_columns.append(name)
    # Constant columns are reported as a non-fatal warning. They can be a real
    # signal of dead features in production, but they also legitimately occur
    # in small training samples (e.g. a flag that happens to be uniformly 0 in
    # the in-sample window). Operators inspect via the audit artifact.
    unexpected_constant_columns = [name for name in constant_columns if name not in allow_constant]
    constant_column_warning = bool(unexpected_constant_columns)

    object_dtype_columns = [
        name for name in columns if model_input[name].dtype == object
    ]
    # The trainer's ColumnTransformer encodes a fixed allow-listed set of categorical
    # columns. Any OTHER object-dtype column reaching the model is a contract break.
    # We accept the trainer's known categorical contract here.
    from models.promotions.preprocessing import _BASE_CATEGORICAL_COLUMNS  # local import to avoid cycles

    unexpected_object_columns = [
        name for name in object_dtype_columns if name not in set(_BASE_CATEGORICAL_COLUMNS)
    ]
    if unexpected_object_columns:
        issues.append(f"unexpected_object_dtype_columns:{unexpected_object_columns}")

    inf_columns: list[str] = []
    nan_only_numeric_columns: list[str] = []
    for name in columns:
        series = model_input[name]
        if not pd.api.types.is_numeric_dtype(series):
            continue
        as_float = series.astype(float, errors="ignore")
        if np.isinf(as_float.to_numpy(dtype=float, na_value=np.nan)).any():
            inf_columns.append(name)
    if inf_columns:
        issues.append(f"inf_in_feature_columns:{inf_columns}")

    report = {
        "passed": not issues,
        "issues": issues,
        "warnings": (
            ["unexpected_constant_columns"] if constant_column_warning else []
        ),
        "duplicate_feature_columns": duplicate_columns,
        "missing_expected_columns": missing_expected,
        "missing_required_new_engineered_features": missing_required_new,
        "explicitly_removed_feature_columns": sorted(explicitly_removed_columns),
        "required_new_engineered_features": list(required_new_features),
        "target_leaking_into_features": target_in_features,
        "raw_advice_columns_in_features": leakage_denylist_present,
        "all_null_columns": all_null_columns,
        "constant_columns": constant_columns,
        "unexpected_constant_columns": unexpected_constant_columns,
        "object_dtype_columns": object_dtype_columns,
        "unexpected_object_dtype_columns": unexpected_object_columns,
        "inf_in_feature_columns": inf_columns,
        "nan_only_numeric_columns": nan_only_numeric_columns,
        "row_count": int(len(model_input.index)),
        "feature_count": int(model_input.shape[1]),
    }
    if issues:
        raise PromotionFinalModelContractError(
            f"Final model-input contract failed: {issues}"
        )
    return report


def _build_feature_lineage_table(
    *,
    raw_columns: Sequence[str],
    cleaned_columns: Sequence[str],
    engineered_columns: Sequence[str],
    model_input_columns: Sequence[str],
    target_columns: Sequence[str],
    stage_label: str,
) -> pd.DataFrame:
    """Build a row-per-column lineage table.

    `stage_label` is either "training" or "scoring" and toggles which model-input
    flag column is populated.
    """

    raw_set = set(raw_columns)
    cleaned_set = set(cleaned_columns)
    engineered_set = set(engineered_columns)
    model_input_set = set(model_input_columns)
    target_set = set(target_columns)
    leakage_denylist_set = set(RAW_ADVICE_LEAKAGE_DENYLIST)

    all_columns = sorted(
        raw_set | cleaned_set | engineered_set | model_input_set | target_set
    )

    is_training = stage_label == "training"
    rows: list[dict[str, object]] = []
    for column_name in all_columns:
        is_target = column_name in target_set or column_name.startswith(TARGET_COLUMN_PREFIX)
        present_engineered = column_name in engineered_set
        present_model_input = column_name in model_input_set
        suspected_leakage = bool(
            (is_target and present_model_input)
            or (column_name in leakage_denylist_set and present_model_input)
        )
        notes: list[str] = []
        if column_name in engineered_set and not present_model_input and column_name.startswith(
            ENGINEERED_FEATURE_PREFIX
        ):
            notes.append("engineered_feature_not_passed_to_model")
        if present_model_input and not (column_name in raw_set or column_name in engineered_set):
            notes.append("in_model_input_but_not_in_raw_or_engineered")
        if is_target and present_model_input:
            notes.append("TARGET_LEAKAGE")
        if column_name in leakage_denylist_set and present_model_input:
            notes.append("RAW_ADVICE_LEAKAGE")
        rows.append(
            {
                "column_name": column_name,
                "stage_present_raw": column_name in raw_set,
                "stage_present_cleaned": column_name in cleaned_set,
                "stage_present_engineered": present_engineered,
                "stage_present_model_input": present_model_input if is_training else False,
                "stage_present_model_scoring": present_model_input if not is_training else False,
                "is_target": is_target,
                "suspected_leakage_flag": suspected_leakage,
                "notes": "|".join(notes) if notes else "",
            }
        )
    return pd.DataFrame(rows)


def _frame_records_for_json(
    frame: pd.DataFrame,
    *,
    decimals: int = NUMERIC_EXPORT_DECIMALS,
) -> list[dict[str, object]]:
    rounded = _round_for_export(frame, decimals=decimals)
    return rounded.where(pd.notna(rounded), None).to_dict(orient="records")


def _write_model_input_quality_artifacts(
    *,
    run_id: str,
    stage_label: str,
    inspection_root: Path,
    quality_report,
    decimals: int = NUMERIC_EXPORT_DECIMALS,
) -> dict[str, str]:
    feature_quality_audit_csv_path = inspection_root / f"feature_quality_audit_{stage_label}.csv"
    feature_quality_audit_json_path = inspection_root / f"feature_quality_audit_{stage_label}.json"
    feature_leakage_review_csv_path = inspection_root / f"feature_leakage_review_{stage_label}.csv"
    feature_correlation_review_csv_path = inspection_root / f"feature_correlation_review_{stage_label}.csv"
    model_input_quality_summary_csv_path = inspection_root / f"model_input_quality_summary_{stage_label}.csv"
    model_input_quality_summary_json_path = inspection_root / f"model_input_quality_summary_{stage_label}.json"
    model_input_quality_summary_txt_path = inspection_root / f"model_input_quality_summary_{stage_label}.txt"

    column_audit_frame = _round_for_export(quality_report.column_audit, decimals=decimals)
    column_audit_frame.to_csv(feature_quality_audit_csv_path, index=False)
    feature_quality_audit_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": stage_label,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "removed_feature_columns": list(quality_report.removed_feature_columns),
                "mixed_type_key_columns": list(quality_report.mixed_type_key_columns),
                "rows": _frame_records_for_json(
                    quality_report.column_audit,
                    decimals=decimals,
                ),
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )

    leakage_review_frame = _round_for_export(quality_report.leakage_review, decimals=decimals)
    leakage_review_frame.to_csv(feature_leakage_review_csv_path, index=False)

    correlation_review_frame = _round_for_export(
        quality_report.correlation_review,
        decimals=decimals,
    )
    correlation_review_frame.to_csv(feature_correlation_review_csv_path, index=False)

    summary_frame = _round_for_export(quality_report.summary_frame, decimals=decimals)
    summary_frame.to_csv(model_input_quality_summary_csv_path, index=False)
    model_input_quality_summary_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": stage_label,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "summary": quality_report.summary_payload,
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    model_input_quality_summary_txt_path.write_text(
        build_model_input_quality_summary_text(
            stage_label=stage_label,
            report=quality_report,
        ),
        encoding="utf-8",
    )

    return {
        "feature_quality_audit_csv_path": str(feature_quality_audit_csv_path),
        "feature_quality_audit_json_path": str(feature_quality_audit_json_path),
        "feature_leakage_review_csv_path": str(feature_leakage_review_csv_path),
        "feature_correlation_review_csv_path": str(feature_correlation_review_csv_path),
        "model_input_quality_summary_csv_path": str(model_input_quality_summary_csv_path),
        "model_input_quality_summary_json_path": str(model_input_quality_summary_json_path),
        "model_input_quality_summary_txt_path": str(model_input_quality_summary_txt_path),
    }


def write_model_input_audit_artifacts(
    *,
    run_id: str,
    stage_label: str,
    inspection_root: Path,
    model_input: pd.DataFrame,
    feature_columns: Sequence[str],
    target_columns: Sequence[str],
    raw_columns: Sequence[str],
    cleaned_columns: Sequence[str],
    engineered_columns: Sequence[str],
    source_artifact_path: str | None,
    quality_report=None,
    sample_rows: int = INSPECTION_SAMPLE_ROWS,
    decimals: int = NUMERIC_EXPORT_DECIMALS,
) -> ModelInputAuditPaths:
    """Write parquet + capped CSV sample + metadata + lineage + contract artifacts.

    `stage_label` must be either "training" or "scoring"; it determines artifact
    filenames and which lineage flag column is populated.
    """

    if stage_label not in {"training", "scoring"}:
        raise ValueError(f"stage_label must be 'training' or 'scoring', got {stage_label!r}")

    inspection_root.mkdir(parents=True, exist_ok=True)

    parquet_path = inspection_root / f"model_{stage_label}_input.parquet"
    sample_csv_path = inspection_root / f"model_{stage_label}_input_sample.csv"
    metadata_json_path = inspection_root / f"model_{stage_label}_input_metadata.json"
    feature_lineage_csv_path = inspection_root / f"feature_lineage_audit_{stage_label}.csv"
    feature_lineage_json_path = inspection_root / f"feature_lineage_audit_{stage_label}.json"
    contract_validation_json_path = (
        inspection_root / f"final_model_contract_validation_{stage_label}.json"
    )
    quality_artifact_paths: dict[str, str] = {}

    # Persist the EXACT model input frame (full precision for parquet).
    model_input.to_parquet(parquet_path, index=False)

    # Human-inspectable sample with consistent 4dp rounding for non-integer numerics.
    sample_frame = model_input.head(sample_rows)
    rounded_sample = _round_for_export(sample_frame, decimals=decimals)
    rounded_sample.to_csv(sample_csv_path, index=False)

    # Contract validation (fails loud).
    required_engineered_features = None
    if stage_label == "scoring":
        required_engineered_features = tuple(
            column_name
            for column_name in REQUIRED_NEW_ENGINEERED_FEATURES
            if column_name in set(feature_columns)
        )
    validation_report = _validate_final_model_contract(
        model_input=model_input,
        expected_feature_columns=feature_columns,
        target_columns=target_columns,
        required_engineered_features=required_engineered_features,
        quality_report=quality_report,
    )
    contract_validation_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": stage_label,
                "validated_at_utc": datetime.now(tz=UTC).isoformat(),
                **validation_report,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    # Feature lineage audit.
    lineage_frame = _build_feature_lineage_table(
        raw_columns=raw_columns,
        cleaned_columns=cleaned_columns,
        engineered_columns=engineered_columns,
        model_input_columns=tuple(model_input.columns),
        target_columns=target_columns,
        stage_label=stage_label,
    )
    lineage_frame.to_csv(feature_lineage_csv_path, index=False)
    feature_lineage_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": stage_label,
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "engineered_columns_not_passed_to_model": sorted(
                    name
                    for name in engineered_columns
                    if name.startswith(ENGINEERED_FEATURE_PREFIX) and name not in set(model_input.columns)
                ),
                "model_input_columns_not_in_engineered_or_raw": sorted(
                    name
                    for name in model_input.columns
                    if name not in set(engineered_columns) and name not in set(raw_columns)
                ),
                "rows": lineage_frame.to_dict(orient="records"),
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )

    if quality_report is not None:
        quality_artifact_paths = _write_model_input_quality_artifacts(
            run_id=run_id,
            stage_label=stage_label,
            inspection_root=inspection_root,
            quality_report=quality_report,
            decimals=decimals,
        )

    # Metadata JSON beside the parquet.
    metadata_json_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "stage": stage_label,
                "row_count": int(len(model_input.index)),
                "feature_count": int(len(feature_columns)),
                "target_count": int(len(target_columns)),
                "feature_column_names": list(feature_columns),
                "target_column_names": list(target_columns),
                "model_input_columns_in_order": list(model_input.columns),
                "source_artifact_path": source_artifact_path,
                "parquet_path": str(parquet_path),
                "sample_csv_path": str(sample_csv_path),
                "sample_csv_row_cap": int(sample_rows),
                "sample_csv_numeric_decimals": int(decimals),
                "feature_lineage_csv_path": str(feature_lineage_csv_path),
                "feature_lineage_json_path": str(feature_lineage_json_path),
                "contract_validation_json_path": str(contract_validation_json_path),
                **quality_artifact_paths,
                "created_at_utc": datetime.now(tz=UTC).isoformat(),
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )

    LOGGER.info(
        "Wrote model-input audit artifacts: stage=%s run_id=%s rows=%s features=%s sample_rows=%s",
        stage_label,
        run_id,
        int(len(model_input.index)),
        int(len(feature_columns)),
        min(int(len(model_input.index)), int(sample_rows)),
    )

    return ModelInputAuditPaths(
        parquet_path=str(parquet_path),
        sample_csv_path=str(sample_csv_path),
        metadata_json_path=str(metadata_json_path),
        feature_lineage_csv_path=str(feature_lineage_csv_path),
        feature_lineage_json_path=str(feature_lineage_json_path),
        contract_validation_json_path=str(contract_validation_json_path),
        feature_quality_audit_csv_path=quality_artifact_paths.get("feature_quality_audit_csv_path"),
        feature_quality_audit_json_path=quality_artifact_paths.get("feature_quality_audit_json_path"),
        feature_leakage_review_csv_path=quality_artifact_paths.get("feature_leakage_review_csv_path"),
        feature_correlation_review_csv_path=quality_artifact_paths.get("feature_correlation_review_csv_path"),
        model_input_quality_summary_csv_path=quality_artifact_paths.get("model_input_quality_summary_csv_path"),
        model_input_quality_summary_json_path=quality_artifact_paths.get("model_input_quality_summary_json_path"),
        model_input_quality_summary_txt_path=quality_artifact_paths.get("model_input_quality_summary_txt_path"),
    )
